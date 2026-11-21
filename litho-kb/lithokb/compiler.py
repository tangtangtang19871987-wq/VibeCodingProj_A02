"""Knowledge compiler: Markdown documents → LLM → knowledge-card revisions.

Three ideas fused here:

* LLM Wiki (Karpathy): raw sources are immutable; the LLM maintains a persistent,
  interlinked wiki; a human-owned SCHEMA.md steers it; knowledge compounds because
  every compile sees — and updates — what already exists.
* OpenKB: two knowledge layers — one `summary` card per source document, plus
  cross-document `concept`-type cards that many documents enrich.
* PageIndex: documents are navigated by their own table-of-contents tree, not by
  embedding similarity. The compiler always gets the document outline; a document
  too large for one call is compiled section-by-section along that tree.

No embeddings, no fixed-size chunking. Each call sees
  (1) the compact index of the whole knowledge base (id/type/parent/title/summary),
  (2) the full current text of the cards already derived from these documents,
  (3) the document outline (ToC tree with line ranges),
  (4) the complete document — or one structural section of it — line-numbered.
The model answers with one JSON object; we validate it, mechanically verify every
evidence quote against the cited lines, and write *revisions* that enter review.
Nothing an LLM produces is ever visible to readers before a human publishes it.

Every call leaves a full trace on disk (traces/<run>/).
"""
from __future__ import annotations

import json
import re
import threading
import traceback
import uuid

from . import doctree
from . import llm
from . import schema as SC
from . import sources as S
from .cards import BASES, CARD_TYPES, RELATIONS, Cards, slug, summary_id
from .store import KB, atomic_write, now, read_jsonl

PROMPT_VERSION = "lkb-compile/3"

PROTOCOL = """You are the knowledge compiler of LithoKB, a curated knowledge base for computational lithography.
You read source documents and maintain a persistent wiki of atomic, interlinked knowledge cards that domain
engineers can read in a minute and trust. Humans review every card against the sources, so faithfulness beats
coverage. The domain SCHEMA (ontology, conventions, what to compile) follows this protocol and is authoritative
for content decisions; this protocol is authoritative for format and grounding.

## Card fields
id, title, type, parent, aliases, summary, body_md, relations, evidence, confidence, change_note, action.
- type ∈ {types}
- relation rel ∈ {relations}
- id: stable lowercase English kebab-case. parent: the id of a topic card (create it if needed).
- summary: one sentence ≤ 200 chars. body_md: Markdown ≤ ~400 words; link cards with [[card-id]]; put evidence
  markers like [E1] right after the statements they support.

## Two layers (always)
1. Exactly one `summary` card per source document, with the id given in the task (e.g. "summary-opc-ilt-md"):
   what the document covers, its structure, and which concept cards it contributes to (relation "covers").
2. Cross-document knowledge cards (concept/method/model/…). Prefer enriching an existing card over creating a
   near-duplicate; one concept = one card, whatever document it came from.

## Grounding (strict, machine-checked)
- Every factual statement needs an evidence item {{"id":"E1","path":"<exact path>","lines":"a-b","quote":"…"}};
  the quote is copied character-for-character from those numbered lines (without the "NNNN|" prefix), ≤ 300 chars.
  Never shorten a quote with "…" and never stitch non-adjacent fragments (e.g. cells from different table rows):
  quote one shorter contiguous span instead, and use several evidence items if needed.
- Never assert facts from outside knowledge; domain knowledge may only be used to name, organise and link.

## Epistemic labels (required on every relation)
relation = {{"rel":"…","target":"…","basis":"extracted|inferred|ambiguous","confidence":0.0-1.0,"evidence":"E2"}}
- extracted: the source states this relation explicitly — cite the evidence id. confidence 1.0.
- inferred: you concluded it from the sources but they do not state it — confidence 0.5–0.95.
- ambiguous: plausible but uncertain or conflicting — flag it for human review; explain in "notes".
Card-level "confidence" (0–1) reflects how well the whole card is supported.

## Working with the existing wiki
- The index lists every existing card; reuse ids. Every parent, relation target and [[link]] must be an id in the
  index or a card created in this output — if you want to point to a topic from the domain schema that is not in
  the index yet, create that topic card (short summary) in this output.
- To change an existing card use action "update", same id, and return the COMPLETE new card. Cards are shared by
  many documents: keep the existing content and ALL existing evidence items that cite OTHER documents unchanged
  (same ids, same quotes); add the new document's evidence with new ids (continue the numbering). Merge, do not
  replace. Do not emit unchanged cards.
- If a source contradicts an existing card, say so in the body, add a "contradicts" relation, lower confidence.

## Output
Exactly one JSON object in a ```json fenced block, nothing else:
{{"cards":[{{"action":"create|update","id":"…","title":"…","type":"…","parent":"…","aliases":["…"],
"summary":"…","body_md":"…","relations":[…],"evidence":[…],"confidence":0.0,"change_note":"…"}}],
"notes":"for the human reviewers: uncertainties, conflicts, ambiguous relations, what you chose not to compile"}}
""".format(types=", ".join(CARD_TYPES), relations=", ".join(RELATIONS))


def system_prompt(kb: KB) -> tuple[str, dict]:
    sc = SC.current(kb)
    return PROTOCOL + f"\n\n---\n# DOMAIN SCHEMA (SCHEMA.md v{sc['version']}, sha {sc['sha']})\n\n" + sc["text"], sc


def _numbered(text: str, start: int = 1, end: int | None = None) -> str:
    lines = text.splitlines()
    end = end or len(lines)
    return "\n".join(f"{i:5d}|{lines[i - 1]}" for i in range(start, min(end, len(lines)) + 1))


def kb_index_rows(cards: Cards, public_only: bool = False) -> list[str]:
    from .cards import is_public
    idx = cards.index()
    return [f"{m['id']} | {m['type']} | {m.get('parent', '')} | {m['title']} | {m.get('summary', '')[:160]}"
            for m in sorted(idx.values(), key=lambda m: m["id"])
            if m.get("lifecycle", "active") == "active" and m.get("status") != "rejected"
            and (not public_only or is_public(m))]


def build_prompt(kb: KB, cards: Cards, units: list[dict], instructions: str = "") -> tuple[str, str, list[str], dict]:
    """units: [{"path": p, "start": a, "end": b, "part": "i/n", "titles": [...]}] (start/end None = whole doc)."""
    system, sc = system_prompt(kb)
    idx = cards.index()
    paths = [u["path"] for u in units]
    rows = kb_index_rows(cards)
    parts = [f"# Knowledge base index ({len(rows)} cards)\nid | type | parent | title | summary\n" +
             ("\n".join(rows) if rows else "(empty — you are starting the knowledge base)")]
    related = sorted({cid for cid, m in idx.items() for s in m.get("sources", []) if s["path"] in paths})
    if related:
        blocks = [f'<card id="{cid}">\n{(kb.cards_dir / f"{cid}.md").read_text("utf-8")}\n</card>' for cid in related]
        parts.append("# Existing cards compiled from these sources (full text — update them, do not duplicate)\n"
                     + "\n".join(blocks))
    meta = S.load_meta(kb)
    task_lines = []
    for u in units:
        p = u["path"]
        text = S.read_text(kb, p)
        rec = meta.get(p, {})
        tree = doctree.build(text, rec.get("sha256"))
        whole = u.get("start") is None
        attrs = (f'path="{p}" version="{rec.get("version")}" sha256="{rec.get("sha256", "")[:12]}" '
                 f'uploaded_by="{rec.get("by", "")}" lines="{tree["lines"]}"')
        parts.append(f'<outline path="{p}">\n{doctree.outline(tree) or "(no headings)"}\n</outline>')
        if whole:
            parts.append(f"<source {attrs}>\n{_numbered(text)}\n</source>")
            task_lines.append(f"- `{p}` (whole document) → summary card id `{summary_id(p)}`")
        else:
            parts.append(f'<source {attrs} section="{u["part"]}" section_lines="{u["start"]}-{u["end"]}">\n'
                         f"{_numbered(text, u['start'], u['end'])}\n</source>")
            task_lines.append(f"- `{p}` SECTION {u['part']} (lines {u['start']}-{u['end']}: {', '.join(u['titles'])[:300]}). "
                              f"The document is too long for one call and is compiled along its outline; earlier sections "
                              f"are already reflected in the existing cards above. Compile this section, and create/update "
                              f"the summary card `{summary_id(p)}` so it describes the whole document as far as compiled.")
    task = ("# Task\nCompile the following into knowledge cards, following the protocol and the domain schema. "
            "Line numbers are the numbers before '|'.\n" + "\n".join(task_lines))
    if instructions:
        task += f"\n\nAdditional instructions from the operator:\n{instructions}"
    parts.append(task)
    return system, "\n\n".join(parts), related, sc


def parse_response(text: str) -> dict:
    m = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.S)
    raw = m.group(1) if m else text[text.find("{"): text.rfind("}") + 1]
    data = json.loads(raw)
    if not isinstance(data, dict) or not isinstance(data.get("cards"), list):
        raise ValueError("response JSON must be an object with a 'cards' list")
    return data


def normalize_relation(r: dict, cid: str, ev_ids: set, findings: list) -> dict | None:
    t = slug(str(r.get("target", "")))
    if not t:
        return None
    rel = r.get("rel")
    if rel not in RELATIONS:
        findings.append({"level": "warn", "card": cid, "msg": f"unknown relation {rel!r} → related_to"})
        rel = "related_to"
    basis = r.get("basis")
    if basis not in BASES:
        findings.append({"level": "info", "card": cid, "msg": f"relation {rel}→{t}: missing epistemic label → inferred"})
        basis = "inferred"
    try:
        conf = max(0.0, min(1.0, float(r.get("confidence", 1.0 if basis == "extracted" else 0.6))))
    except (TypeError, ValueError):
        conf = 0.6
    out = {"rel": rel, "target": t, "basis": basis, "confidence": conf}
    if basis == "extracted":
        if r.get("evidence") not in ev_ids:
            findings.append({"level": "warn", "card": cid, "msg": f"relation {rel}→{t} labelled extracted without valid evidence → inferred"})
            out["basis"], out["confidence"] = "inferred", min(conf, 0.8)
        else:
            out["evidence"] = r["evidence"]
    if basis == "ambiguous":
        findings.append({"level": "info", "card": cid, "msg": f"ambiguous relation {rel}→{t} flagged for review"})
    if r.get("note"):
        out["note"] = str(r["note"])[:300]
    return out


def validate(cards: Cards, data: dict, paths: list[str], expect_summaries: list[str] | None = None) -> tuple[list[dict], list[dict]]:
    """Return (normalised cards, findings). Findings are shown to reviewers, never hidden."""
    idx = cards.index()
    findings: list[dict] = []
    out: list[dict] = []
    batch_ids = {slug(c.get("id", "") or c.get("title", "")) for c in data["cards"]}
    for i, c in enumerate(data["cards"]):
        raw_id = c.get("id", "") or c.get("title", "")
        cid = slug(raw_id)
        if not cid:
            findings.append({"level": "error", "card": f"#{i}", "msg": "missing id — card dropped"})
            continue
        if any(o["id"] == cid for o in out):
            findings.append({"level": "error", "card": cid, "msg": "duplicate id in this output — later copy dropped"})
            continue
        if cid != raw_id:
            findings.append({"level": "warn", "card": cid, "msg": f"id normalised from {raw_id!r}"})
        exists = cid in idx
        action = c.get("action", "update" if exists else "create")
        if action == "create" and exists:
            findings.append({"level": "warn", "card": cid, "msg": "declared create but card exists → treated as update"})
        if action == "update" and not exists:
            findings.append({"level": "warn", "card": cid, "msg": "declared update but card is new → treated as create"})
        if c.get("type") not in CARD_TYPES:
            findings.append({"level": "warn", "card": cid, "msg": f"unknown type {c.get('type')!r} → concept"})
            c["type"] = "concept"
        ev = []
        for e in c.get("evidence", []) or []:
            if e.get("path") not in paths:
                findings.append({"level": "warn", "card": cid, "msg": f"evidence cites {e.get('path')!r}, not a source of this run"})
            ev.append({"id": str(e.get("id", f"E{len(ev) + 1}")), "path": e.get("path", ""),
                       "lines": str(e.get("lines", "")), "quote": str(e.get("quote", ""))[:600]})
        ev_ids = {e["id"] for e in ev}
        rels = []
        for r in c.get("relations", []) or []:
            nr = normalize_relation(r, cid, ev_ids, findings)
            if not nr:
                continue
            if nr["target"] not in idx and nr["target"] not in batch_ids:
                findings.append({"level": "warn", "card": cid, "msg": f"relation target {nr['target']!r} does not exist"})
            rels.append(nr)
        parent = slug(c.get("parent", "") or "")
        if parent == cid:
            parent = ""
        if parent and parent not in idx and parent not in batch_ids:
            findings.append({"level": "warn", "card": cid, "msg": f"parent {parent!r} does not exist"})
        if not ev:
            findings.append({"level": "warn", "card": cid, "msg": "no evidence"})
        body = c.get("body_md", "") or ""
        cited = set(re.findall(r"\[(E\d+)\]", body))
        if cited - ev_ids:
            findings.append({"level": "warn", "card": cid, "msg": f"body cites undefined evidence {sorted(cited - ev_ids)}"})
        if ev_ids - cited:
            findings.append({"level": "info", "card": cid, "msg": f"evidence not referenced in body: {sorted(ev_ids - cited)}"})
        out.append({"id": cid, "title": c.get("title", cid), "type": c["type"], "parent": parent,
                    "aliases": c.get("aliases", []) or [], "summary": c.get("summary", ""),
                    "relations": rels, "evidence": ev, "sources": paths, "confidence": c.get("confidence"),
                    "body": body, "change_note": c.get("change_note", ""), "exists": exists})
    for sid in expect_summaries or []:
        if sid not in {o["id"] for o in out} and sid not in idx:
            findings.append({"level": "warn", "card": sid, "msg": "summary card for this document was not produced"})
    return out, findings


# ---- runs & traces ---------------------------------------------------------------
_last_id = [""]
_id_lock = threading.Lock()


def new_run_id() -> str:
    """Sortable, unique run id: local timestamp to the microsecond + random suffix.
    (Sorting run directories by name must equal chronological order.)"""
    import datetime as _dt
    with _id_lock:
        while True:
            t = _dt.datetime.now().strftime("%Y%m%dT%H%M%S-%f")
            if t > _last_id[0]:
                _last_id[0] = t
                break
    return t + "-" + uuid.uuid4().hex[:4]


class Compiler:
    def __init__(self, kb: KB, cards: Cards):
        self.kb, self.cards = kb, cards
        self.jobs: dict[str, dict] = {}

    def _trace_dir(self, run: str):
        return self.kb.traces_dir / run

    def _save_run(self, run: dict) -> None:
        atomic_write(self._trace_dir(run["id"]) / "run.json", json.dumps(run, ensure_ascii=False, indent=1))

    def llm_step(self, run: dict, cfg: dict, system: str, user: str, prefix: str = "") -> llm.LLMResult:
        """One traced LLM call: prompts, response, thinking, usage, cost go to the run's trace dir."""
        tdir = self._trace_dir(run["id"])
        atomic_write(tdir / f"{prefix}system.md", system)
        atomic_write(tdir / f"{prefix}prompt.md", user)
        res = llm.call(cfg, system, user)
        calls = run.setdefault("calls", [])
        call = {"step": prefix.rstrip("-") or "compile", "model": res.model, "usage": res.usage,
                "latency_s": res.latency_s, "stop_reason": res.stop_reason, "prompt_chars": len(system) + len(user)}
        price = self.kb.config["llm"].get("price_per_mtok", {}).get(res.model)
        if "cost_usd_reported" in res.usage:
            call["cost_usd"] = round(float(res.usage["cost_usd_reported"]), 6)
        elif price and "input_tokens" in res.usage:
            call["cost_usd"] = round(res.usage["input_tokens"] / 1e6 * price[0] + res.usage["output_tokens"] / 1e6 * price[1], 4)
        calls.append(call)
        # run-level aggregates
        run["model"] = res.model
        run["latency_s"] = round(sum(c["latency_s"] for c in calls), 3)
        agg: dict = {}
        for c in calls:
            for k, v in c["usage"].items():
                if isinstance(v, (int, float)):
                    agg[k] = agg.get(k, 0) + v
        run["usage"] = agg
        if any("cost_usd" in c for c in calls):
            run["cost_usd"] = round(sum(c.get("cost_usd", 0) for c in calls), 6)
        run["stop_reason"] = res.stop_reason
        run["llm_meta"] = res.raw_meta
        atomic_write(tdir / f"{prefix}response.md", res.text)
        atomic_write(tdir / f"{prefix}thinking.md", res.thinking or "(no thinking returned)")
        if res.stop_reason == "max_tokens":
            raise llm.LLMError("output truncated at max_tokens — raise the limit or compile smaller units")
        if res.stop_reason == "refusal":
            raise llm.LLMError(f"model refused: {res.raw_meta.get('refusal')}")
        return res

    def plan(self, paths: list[str] | None, only_changed: bool = True) -> list[str]:
        """Which documents need compiling: all, or only those whose sha changed since last full compile."""
        all_md = S.list_md(self.kb)
        paths = [S.clean_path(p) for p in paths] if paths else all_md
        missing = [p for p in paths if p not in all_md]
        if missing:
            raise ValueError(f"not a source document: {missing}")
        if not only_changed:
            return paths
        done: dict[str, set] = {}
        for r in self.runs(limit=10_000):
            if r.get("status") == "done" and r.get("kind", "compile") == "compile":
                complete = r.get("source_complete", list(r.get("source_shas", {})))
                for p in complete:
                    done.setdefault(p, set()).add(r["source_shas"].get(p))
        meta = S.load_meta(self.kb)
        return [p for p in paths if meta[p]["sha256"] not in done.get(p, set())]

    def work_units(self, paths: list[str], files_per_call: int | None = None) -> list[list[dict]]:
        """Group documents into calls. Small documents: whole, n per call. Documents over the
        budget: one call per structural section (PageIndex-style), in outline order."""
        budget = int(self.kb.config["compile"].get("max_doc_chars", 300_000))
        n = files_per_call or self.kb.config["compile"]["files_per_call"]
        meta = S.load_meta(self.kb)
        calls, small = [], []
        for p in paths:
            text = S.read_text(self.kb, p)
            tree = doctree.build(text, meta[p]["sha256"])
            secs = doctree.sections(tree, budget)
            if len(secs) == 1:
                small.append({"path": p, "start": None, "end": None})
            else:
                for i, (a, b, titles) in enumerate(secs, 1):
                    calls.append([{"path": p, "start": a, "end": b, "part": f"{i}/{len(secs)}", "titles": titles}])
        smalls = [small[i:i + n] for i in range(0, len(small), n)]
        return smalls + calls

    def start(self, actor: str, paths: list[str], backend: str | None = None, instructions: str = "",
              background: bool = True, files_per_call: int | None = None, model: str | None = None) -> dict:
        cfg = llm_config(self.kb, backend, model)
        groups = self.work_units(paths, files_per_call)
        job = {"id": "job-" + uuid.uuid4().hex[:8], "by": actor, "at": now(), "backend": cfg["backend"],
               "groups": [[u["path"] + (f" §{u['part']}" if u.get("part") else "") for u in g] for g in groups],
               "runs": [], "status": "queued", "done": 0, "total": len(groups)}
        self.jobs[job["id"]] = job
        self.kb.event(actor, "compile.start", job["id"], backend=cfg["backend"], files=len(paths), calls=len(groups))

        def work():
            job["status"] = "running"
            failed_docs: set = set()
            for g in groups:
                if any(u["path"] in failed_docs for u in g):  # don't continue a document after a failed section
                    continue
                run = self.run_once(actor, g, cfg, instructions, job_id=job["id"])
                job["runs"].append(run["id"])
                job["done"] += 1
                if run["status"] != "done":
                    failed_docs |= {u["path"] for u in g}
            job["status"] = "done"
            self.cards.write_exports()
            self.kb.event(actor, "compile.finish", job["id"], runs=job["runs"])

        if background:
            threading.Thread(target=work, daemon=True).start()
        else:
            work()
        return job

    def run_once(self, actor: str, units: list | list[dict], cfg: dict, instructions: str = "", job_id: str = "") -> dict:
        units = [u if isinstance(u, dict) else {"path": u, "start": None, "end": None} for u in units]
        paths = [u["path"] for u in units]
        rid = new_run_id()
        meta = S.load_meta(self.kb)
        run = {"id": rid, "kind": "compile", "job": job_id, "by": actor, "started": now(), "status": "running",
               "backend": cfg["backend"], "model": cfg.get("model"), "effort": cfg.get("effort"),
               "prompt_version": PROMPT_VERSION, "sources": paths,
               "sections": [{"path": u["path"], "part": u["part"], "lines": f"{u['start']}-{u['end']}", "titles": u["titles"]}
                            for u in units if u.get("part")],
               "source_shas": {p: meta[p]["sha256"] for p in paths}, "timeline": [], "written": []}
        # a document is fully compiled by this run if it was whole, or this is its last section
        run["source_complete"] = [u["path"] for u in units
                                  if not u.get("part") or u["part"].split("/")[0] == u["part"].split("/")[1]]

        def step(name, **kw):
            run["timeline"].append({"ts": now(), "step": name, **kw})
            self._save_run(run)

        try:
            system, user, related, sc = build_prompt(self.kb, self.cards, units, instructions)
            run["schema"] = {"version": sc["version"], "sha": sc["sha"]}
            run["context"] = {"related_cards": related, "system_chars": len(system), "prompt_chars": len(user),
                              "index_cards": len(self.cards.index())}
            step("prompt_built")
            res = self.llm_step(run, cfg, system, user)
            step("llm_returned", latency_s=res.latency_s, stop_reason=res.stop_reason)
            data = parse_response(res.text)
            atomic_write(self._trace_dir(rid) / "parsed.json", json.dumps(data, ensure_ascii=False, indent=1))
            norm, findings = validate(self.cards, data, paths, [summary_id(p) for p in paths])
            run["notes"] = data.get("notes", "")
            run["findings"] = findings
            step("validated", cards=len(norm), findings=len(findings))
            for c in norm:
                body = c.pop("body")
                note, existed = c.pop("change_note"), c.pop("exists")
                if existed:
                    kept = carry_forward_evidence(self.cards, c, paths)
                    if kept:
                        findings.append({"level": "info", "card": c["id"],
                                         "msg": f"update omitted {kept} evidence item(s) from other documents — kept automatically"})
                head = self.cards.new_revision(actor, c, body, {"kind": "llm", "run": rid, "model": res.model,
                                                                "backend": cfg["backend"], "by": actor,
                                                                "schema": sc["version"]},
                                               change_note=note, status="in_review")
                run["written"].append({"id": c["id"], "rev": head["rev"], "action": "update" if existed else "create",
                                       "type": head["type"], "grounding": head["grounding"],
                                       "bases": _basis_counts(head.get("relations", []))})
            run["grounding"] = _sum_grounding([w["grounding"] for w in run["written"]])
            run["bases"] = _basis_counts([r for c in norm for r in c["relations"]])
            run["status"] = "done"
            step("written", cards=len(run["written"]))
        except Exception as e:  # failures are traced, never swallowed
            run["status"] = "failed"
            run["error"] = f"{type(e).__name__}: {e}"
            atomic_write(self._trace_dir(rid) / "error.txt", traceback.format_exc())
            step("failed", error=run["error"])
        run["finished"] = now()
        self._save_run(run)
        self.kb.event(actor, f"compile.run.{run['status']}", rid, sources=paths, cards=[w["id"] for w in run["written"]],
                      error=run.get("error", ""))
        return run

    # ---- read traces -------------------------------------------------------------
    def runs(self, limit: int = 200, kind: str | None = None) -> list[dict]:
        out = []
        d = self.kb.traces_dir
        for p in sorted(d.glob("*/run.json"), reverse=True) if d.exists() else []:
            try:
                r = json.loads(p.read_text("utf-8"))
            except json.JSONDecodeError:
                continue
            if kind and r.get("kind", "compile") != kind:
                continue
            out.append(r)
            if len(out) >= limit:
                break
        return out

    def trace(self, rid: str) -> dict:
        if not re.fullmatch(r"[0-9T+\-a-f]+", rid):
            raise ValueError("bad run id")
        d = self._trace_dir(rid)
        if not (d / "run.json").exists():
            raise FileNotFoundError(rid)
        out = {"run": json.loads((d / "run.json").read_text("utf-8"))}
        for f in sorted(d.iterdir()):
            if f.name != "run.json" and f.suffix in (".md", ".json", ".txt"):
                out[f.name] = f.read_text("utf-8")
        return out

    def stats(self) -> dict:
        runs = self.runs(limit=10_000)
        s = {"runs": len(runs), "done": 0, "failed": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0,
             "latency_s": 0.0, "cards_written": 0, "grounding": {"exact": 0, "moved": 0, "elided": 0, "fuzzy": 0, "missing": 0, "total": 0},
             "bases": {b: 0 for b in BASES}, "findings": {}, "by_model": {}, "by_kind": {}, "by_schema": {}}
        for r in runs:
            s[r.get("status", "failed")] = s.get(r.get("status", "failed"), 0) + 1
            u = r.get("usage", {})
            s["input_tokens"] += u.get("input_tokens", u.get("input_tokens_est", 0))
            s["output_tokens"] += u.get("output_tokens", u.get("output_tokens_est", 0))
            s["cost_usd"] += r.get("cost_usd", 0)
            s["latency_s"] += r.get("latency_s", 0) or 0
            s["cards_written"] += len(r.get("written", []))
            k = r.get("kind", "compile")
            s["by_kind"][k] = s["by_kind"].get(k, 0) + 1
            if r.get("schema"):
                key = f"v{r['schema']['version']}"
                bs = s["by_schema"].setdefault(key, {"runs": 0, "exact": 0, "total": 0})
                bs["runs"] += 1
                bs["exact"] += r.get("grounding", {}).get("exact", 0) + r.get("grounding", {}).get("moved", 0)
                bs["total"] += r.get("grounding", {}).get("total", 0)
            for g in s["grounding"]:
                s["grounding"][g] += r.get("grounding", {}).get(g, 0)
            for b in BASES:
                s["bases"][b] += r.get("bases", {}).get(b, 0)
            for f in r.get("findings", []):
                key = re.sub(r"'[^']*'|\[[^\]]*\]|\"[^\"]*\"|\S+→\S+", "…", f["msg"])
                s["findings"][key] = s["findings"].get(key, 0) + 1
            bm = s["by_model"].setdefault(r.get("model") or "?", {"runs": 0, "latency_s": 0.0})
            bm["runs"] += 1
            bm["latency_s"] += r.get("latency_s", 0) or 0
        s["cost_usd"] = round(s["cost_usd"], 4)
        s["latency_s"] = round(s["latency_s"], 2)
        return s


def carry_forward_evidence(cards: Cards, c: dict, run_paths: list[str]) -> int:
    """Cross-document cards must not lose provenance when one document updates them.
    Evidence from documents outside this run (which the model could not re-verify) is
    kept deterministically if the model's update dropped it. Returns how many were kept."""
    prev, _ = cards.load(c["id"])
    have = {(e["path"], e["quote"]) for e in c["evidence"]}
    used = {e["id"] for e in c["evidence"]}
    kept = 0
    for e in prev.get("evidence", []):
        if e["path"] in run_paths or (e["path"], e["quote"]) in have:
            continue
        eid, n = e["id"], 1
        while eid in used:
            n += 1
            eid = f"{e['id']}-{n}"
        used.add(eid)
        c["evidence"].append({"id": eid, "path": e["path"], "lines": e["lines"], "quote": e["quote"]})
        kept += 1
    c["sources"] = sorted(set(c["sources"]) | {s["path"] for s in prev.get("sources", []) if s["path"] not in run_paths
                                               and any(e["path"] == s["path"] for e in c["evidence"])})
    return kept


def _basis_counts(rels: list[dict]) -> dict:
    c = {b: 0 for b in BASES}
    for r in rels:
        c[r.get("basis", "inferred")] = c.get(r.get("basis", "inferred"), 0) + 1
    return c


def _sum_grounding(gs: list[dict]) -> dict:
    g = {k: sum(x.get(k, 0) for x in gs) for k in ("exact", "moved", "elided", "fuzzy", "missing", "no_source")}
    g["total"] = sum(x.get("total", 0) for x in gs)
    g["score"] = round((g["exact"] + g["moved"] + g["elided"] + 0.5 * g["fuzzy"]) / g["total"], 2) if g["total"] else 0.0
    return g


def llm_config(kb: KB, backend: str | None = None, model: str | None = None) -> dict:
    """Effective LLM settings: config.json, optionally overridden per job/query."""
    cfg = dict(kb.config["llm"])
    if backend:
        cfg["backend"] = backend
    if model:
        cfg["openrouter_model" if cfg["backend"] == "openrouter" else "model"] = model
    if cfg["backend"] == "openrouter":
        cfg["model"] = cfg.get("openrouter_model")
    return cfg


def card_history(kb: KB, cid: str) -> list[dict]:
    return [e for e in read_jsonl(kb.events_path) if e.get("target") == cid]
