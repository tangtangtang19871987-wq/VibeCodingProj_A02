"""Knowledge compiler: whole Markdown documents → LLM → knowledge-card revisions.

No chunking, no embeddings, no retrieval heuristics. Each call sees
  (1) the compact index of the whole knowledge base (id/type/parent/title/summary),
  (2) the full current text of the cards already derived from these documents,
  (3) the complete source document(s), line-numbered so citations are checkable.
The model answers with one JSON object; we validate it, mechanically verify every
evidence quote against the cited lines, and write *revisions* that enter review.
Nothing an LLM produces is ever visible to readers before a human publishes it.

Every run leaves a full trace on disk (traces/<run>/): the exact system and user
prompts, raw response, the model's summarized thinking, usage, latency, cost
estimate, the parsed output, validation findings and what was written.
"""
from __future__ import annotations

import json
import re
import threading
import traceback
import uuid

from . import llm
from . import sources as S
from .cards import CARD_TYPES, RELATIONS, Cards, slug
from .store import KB, atomic_write, now, read_jsonl

PROMPT_VERSION = "lkb-compile/1"

SYSTEM_PROMPT = """You are the knowledge compiler of LithoKB, a curated knowledge base for computational lithography
(imaging/optical models, resist & etch models, OPC, ILT, SMO, mask 3D effects, EUV-specific effects,
hotspot detection/DFM, metrology & model calibration, ML for lithography, compute platforms).

Your job: read the source document(s) and compile them into atomic, interlinked knowledge cards that a
lithography engineer can read in a minute and trust. Humans will review every card you write against the
sources, so faithfulness beats coverage.

## What a card is
- One concept / method / model / parameter / metric / issue per card. Topic cards (type "topic") group them.
- Fields: id, title, type, parent, aliases, summary, body_md, relations, evidence, confidence, change_note.
- type ∈ {types}.
- relation rel ∈ {relations}.
- id: stable lowercase English kebab-case (e.g. "optical-proximity-correction", "hopkins-imaging-model"),
  even when the source is Chinese. Titles and body stay in the source language (keep the English term in
  parentheses for Chinese titles, e.g. "光学邻近效应修正 (OPC)").
- parent: id of the topic card this belongs under (create the topic card if needed). Topics may nest.
- summary: one sentence, ≤ 200 characters.
- body_md: Markdown, ≤ ~400 words. Suggested sections: definition / key points / formulas (keep LaTeX as
  written) / parameters & typical values / pitfalls / relations. Link other cards with [[card-id]].
  Put evidence markers like [E1] right after the statements they support.

## Grounding rules (strict)
1. Every factual statement must be supported by an evidence item. Do not assert facts from outside
   knowledge; you may use domain knowledge only to name, organise and link.
2. evidence item: {{"id":"E1","path":"<exact source path>","lines":"<a>-<b>","quote":"<verbatim text>"}}.
   The quote must be copied character-for-character from those numbered lines (without the line-number
   prefix), ≤ 300 characters. Quotes are machine-checked; a wrong quote is flagged to reviewers.
3. If sources are ambiguous, inconsistent, or contradict an existing card, say so in the body and add a
   "contradicts" relation, and explain in "notes". Lower "confidence" (0–1) accordingly.

## Working with the existing knowledge base
- You get the index of all existing cards. Reuse ids; do NOT create a duplicate of an existing concept.
- To improve an existing card use action "update" with the same id and return the COMPLETE new card
  (it becomes a new revision; keep valid existing content and evidence unless the source supersedes it).
- Relations and [[links]] may only target ids in the index or created in this output.
- Do not emit cards that would be unchanged.

## Output
Return exactly one JSON object in a ```json fenced block and nothing else:
{{"cards":[{{"action":"create|update","id":"…","title":"…","type":"…","parent":"…","aliases":["…"],
"summary":"…","body_md":"…","relations":[{{"rel":"uses","target":"…"}}],"evidence":[…],
"confidence":0.0,"change_note":"what you did and why"}}],
"notes":"compiler notes for the human reviewers: uncertainties, conflicts, things you chose not to compile"}}
""".format(types=", ".join(CARD_TYPES), relations=", ".join(RELATIONS))


def _numbered(text: str) -> str:
    return "\n".join(f"{i:5d}|{ln}" for i, ln in enumerate(text.splitlines(), 1))


def build_prompt(kb: KB, cards: Cards, paths: list[str], instructions: str = "") -> tuple[str, str, list[str]]:
    idx = cards.index()
    rows = [f"{m['id']} | {m['type']} | {m.get('parent', '')} | {m['title']} | {m.get('summary', '')[:160]}"
            for m in sorted(idx.values(), key=lambda m: m["id"])
            if m.get("lifecycle", "active") == "active" and m.get("status") != "rejected"]
    related = sorted({cid for cid, m in idx.items() for s in m.get("sources", []) if s["path"] in paths})
    parts = [f"# Knowledge base index ({len(rows)} cards)\nid | type | parent | title | summary\n" +
             ("\n".join(rows) if rows else "(empty — you are starting the knowledge base)")]
    if related:
        blocks = []
        for cid in related:
            p = kb.cards_dir / f"{cid}.md"
            blocks.append(f'<card id="{cid}">\n{p.read_text("utf-8")}\n</card>')
        parts.append("# Existing cards compiled from these sources (full text)\n" + "\n".join(blocks))
    meta = S.load_meta(kb)
    for p in paths:
        text = S.read_text(kb, p)
        rec = meta.get(p, {})
        parts.append(f'<source path="{p}" version="{rec.get("version")}" sha256="{rec.get("sha256", "")[:12]}" '
                     f'uploaded_by="{rec.get("by", "")}">\n{_numbered(text)}\n</source>')
    task = ("# Task\nCompile the source document(s) above into knowledge cards following the rules. "
            "Line numbers are the numbers before '|'.")
    if instructions:
        task += f"\n\nAdditional instructions from the operator:\n{instructions}"
    parts.append(task)
    return SYSTEM_PROMPT, "\n\n".join(parts), related


def parse_response(text: str) -> dict:
    m = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.S)
    raw = m.group(1) if m else text[text.find("{"): text.rfind("}") + 1]
    data = json.loads(raw)
    if not isinstance(data, dict) or not isinstance(data.get("cards"), list):
        raise ValueError("response JSON must be an object with a 'cards' list")
    return data


def validate(cards: Cards, data: dict, paths: list[str]) -> tuple[list[dict], list[dict]]:
    """Return (normalised cards, findings). Findings are shown to reviewers, never hidden."""
    idx = cards.index()
    findings: list[dict] = []
    out = []
    batch_ids = {slug(c.get("id", "") or c.get("title", "")) for c in data["cards"]}
    for i, c in enumerate(data["cards"]):
        raw_id = c.get("id", "") or c.get("title", "")
        cid = slug(raw_id)
        where = cid or f"#{i}"
        if not cid:
            findings.append({"level": "error", "card": where, "msg": "missing id — card dropped"})
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
        rels = []
        for r in c.get("relations", []) or []:
            t = slug(str(r.get("target", "")))
            if r.get("rel") not in RELATIONS:
                findings.append({"level": "warn", "card": cid, "msg": f"unknown relation {r.get('rel')!r} → related_to"})
                r["rel"] = "related_to"
            if t not in idx and t not in batch_ids:
                findings.append({"level": "warn", "card": cid, "msg": f"relation target {t!r} does not exist"})
            rels.append({"rel": r["rel"], "target": t, **({"note": r["note"]} if r.get("note") else {})})
        c["relations"] = rels
        if c.get("parent"):
            c["parent"] = slug(c["parent"])
            if c["parent"] not in idx and c["parent"] not in batch_ids:
                findings.append({"level": "warn", "card": cid, "msg": f"parent {c['parent']!r} does not exist"})
            if c["parent"] == cid:
                c["parent"] = ""
        ev = []
        for e in c.get("evidence", []) or []:
            if e.get("path") not in paths:
                findings.append({"level": "warn", "card": cid, "msg": f"evidence cites {e.get('path')!r}, not a source of this run"})
            ev.append({"id": str(e.get("id", f"E{len(ev) + 1}")), "path": e.get("path", ""),
                       "lines": str(e.get("lines", "")), "quote": str(e.get("quote", ""))[:600]})
        if not ev:
            findings.append({"level": "warn", "card": cid, "msg": "no evidence"})
        body = c.get("body_md", "") or ""
        cited = set(re.findall(r"\[(E\d+)\]", body))
        unused = {e["id"] for e in ev} - cited
        if cited - {e["id"] for e in ev}:
            findings.append({"level": "warn", "card": cid, "msg": f"body cites undefined evidence {sorted(cited - {e['id'] for e in ev})}"})
        if unused:
            findings.append({"level": "info", "card": cid, "msg": f"evidence not referenced in body: {sorted(unused)}"})
        out.append({"id": cid, "title": c.get("title", cid), "type": c["type"], "parent": c.get("parent", ""),
                    "aliases": c.get("aliases", []) or [], "summary": c.get("summary", ""),
                    "relations": rels, "evidence": ev, "sources": paths, "confidence": c.get("confidence"),
                    "body": body, "change_note": c.get("change_note", ""), "exists": exists})
    return out, findings


# ---- runs & traces ---------------------------------------------------------------
class Compiler:
    def __init__(self, kb: KB, cards: Cards):
        self.kb, self.cards = kb, cards
        self.jobs: dict[str, dict] = {}

    def _trace_dir(self, run: str):
        return self.kb.traces_dir / run

    def _save_run(self, run: dict) -> None:
        atomic_write(self._trace_dir(run["id"]) / "run.json", json.dumps(run, ensure_ascii=False, indent=1))

    def plan(self, paths: list[str] | None, only_changed: bool = True) -> list[str]:
        """Which documents need compiling: all, or only those whose sha changed since last compile."""
        all_md = S.list_md(self.kb)
        paths = [S.clean_path(p) for p in paths] if paths else all_md
        missing = [p for p in paths if p not in all_md]
        if missing:
            raise ValueError(f"not a source document: {missing}")
        if not only_changed:
            return paths
        done = {}
        for r in self.runs(limit=10_000):
            if r.get("status") == "done":
                for p, sha in r.get("source_shas", {}).items():
                    done.setdefault(p, set()).add(sha)
        meta = S.load_meta(self.kb)
        return [p for p in paths if meta[p]["sha256"] not in done.get(p, set())]

    def start(self, actor: str, paths: list[str], backend: str | None = None, instructions: str = "",
              background: bool = True, files_per_call: int | None = None) -> dict:
        cfg = dict(self.kb.config["llm"])
        if backend:
            cfg["backend"] = backend
        n = files_per_call or self.kb.config["compile"]["files_per_call"]
        groups = [paths[i:i + n] for i in range(0, len(paths), n)] or []
        job = {"id": "job-" + uuid.uuid4().hex[:8], "by": actor, "at": now(), "backend": cfg["backend"],
               "groups": groups, "runs": [], "status": "queued", "done": 0, "total": len(groups)}
        self.jobs[job["id"]] = job
        self.kb.event(actor, "compile.start", job["id"], backend=cfg["backend"], files=len(paths))

        def work():
            job["status"] = "running"
            for g in groups:
                run = self.run_once(actor, g, cfg, instructions, job_id=job["id"])
                job["runs"].append(run["id"])
                job["done"] += 1
            job["status"] = "done"
            self.cards.write_exports()
            self.kb.event(actor, "compile.finish", job["id"], runs=job["runs"])

        if background:
            threading.Thread(target=work, daemon=True).start()
        else:
            work()
        return job

    def run_once(self, actor: str, paths: list[str], cfg: dict, instructions: str = "", job_id: str = "") -> dict:
        rid = now()[:19].replace(":", "").replace("-", "") + "-" + uuid.uuid4().hex[:6]
        meta = S.load_meta(self.kb)
        run = {"id": rid, "job": job_id, "by": actor, "started": now(), "status": "running",
               "backend": cfg["backend"], "model": cfg.get("model"), "effort": cfg.get("effort"),
               "prompt_version": PROMPT_VERSION, "sources": paths,
               "source_shas": {p: meta[p]["sha256"] for p in paths}, "timeline": [], "written": []}
        tdir = self._trace_dir(rid)

        def step(name, **kw):
            run["timeline"].append({"ts": now(), "step": name, **kw})
            self._save_run(run)

        try:
            system, user, related = build_prompt(self.kb, self.cards, paths, instructions)
            atomic_write(tdir / "system.md", system)
            atomic_write(tdir / "prompt.md", user)
            run["context"] = {"related_cards": related, "system_chars": len(system), "prompt_chars": len(user),
                              "index_cards": len(self.cards.index())}
            step("prompt_built")
            res = llm.call(cfg, system, user)
            run.update(model=res.model, usage=res.usage, latency_s=res.latency_s, stop_reason=res.stop_reason,
                       llm_meta=res.raw_meta)
            price = self.kb.config["llm"].get("price_per_mtok", {}).get(res.model)
            if price and "input_tokens" in res.usage:
                run["cost_usd"] = round(res.usage["input_tokens"] / 1e6 * price[0] + res.usage["output_tokens"] / 1e6 * price[1], 4)
            atomic_write(tdir / "response.md", res.text)
            atomic_write(tdir / "thinking.md", res.thinking or "(no thinking returned)")
            step("llm_returned", latency_s=res.latency_s, stop_reason=res.stop_reason)
            if res.stop_reason == "refusal":
                raise llm.LLMError(f"model refused: {res.raw_meta.get('refusal')}")
            data = parse_response(res.text)
            atomic_write(tdir / "parsed.json", json.dumps(data, ensure_ascii=False, indent=1))
            norm, findings = validate(self.cards, data, paths)
            run["notes"] = data.get("notes", "")
            run["findings"] = findings
            step("validated", cards=len(norm), findings=len(findings))
            for c in norm:
                body = c.pop("body")
                note, existed = c.pop("change_note"), c.pop("exists")
                head = self.cards.new_revision(actor, c, body, {"kind": "llm", "run": rid, "model": res.model,
                                                                "backend": cfg["backend"], "by": actor},
                                               change_note=note, status="in_review")
                run["written"].append({"id": c["id"], "rev": head["rev"], "action": "update" if existed else "create",
                                       "grounding": head["grounding"]})
            g = [w["grounding"] for w in run["written"]]
            tot = sum(x["total"] for x in g)
            run["grounding"] = {k: sum(x.get(k, 0) for x in g) for k in ("exact", "moved", "fuzzy", "missing", "no_source")}
            run["grounding"]["total"] = tot
            run["grounding"]["score"] = round((run["grounding"]["exact"] + run["grounding"]["moved"]
                                               + 0.5 * run["grounding"]["fuzzy"]) / tot, 2) if tot else 0.0
            run["status"] = "done"
            step("written", cards=len(run["written"]))
        except Exception as e:  # failures are traced, never swallowed
            run["status"] = "failed"
            run["error"] = f"{type(e).__name__}: {e}"
            atomic_write(tdir / "error.txt", traceback.format_exc())
            step("failed", error=run["error"])
        run["finished"] = now()
        self._save_run(run)
        self.kb.event(actor, f"compile.run.{run['status']}", rid, sources=paths, cards=[w["id"] for w in run["written"]],
                      error=run.get("error", ""))
        return run

    # ---- read traces -------------------------------------------------------------
    def runs(self, limit: int = 200) -> list[dict]:
        out = []
        d = self.kb.traces_dir
        for p in sorted(d.glob("*/run.json"), reverse=True)[:limit] if d.exists() else []:
            try:
                out.append(json.loads(p.read_text("utf-8")))
            except json.JSONDecodeError:
                pass
        return out

    def trace(self, rid: str) -> dict:
        if not re.fullmatch(r"[0-9T+\-a-f]+", rid):
            raise ValueError("bad run id")
        d = self._trace_dir(rid)
        if not (d / "run.json").exists():
            raise FileNotFoundError(rid)
        out = {"run": json.loads((d / "run.json").read_text("utf-8"))}
        for name in ("system.md", "prompt.md", "response.md", "thinking.md", "parsed.json", "error.txt"):
            if (d / name).exists():
                out[name] = (d / name).read_text("utf-8")
        return out

    def stats(self) -> dict:
        runs = self.runs(limit=10_000)
        s = {"runs": len(runs), "done": 0, "failed": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0,
             "latency_s": 0.0, "cards_written": 0, "grounding": {"exact": 0, "moved": 0, "fuzzy": 0, "missing": 0, "total": 0},
             "findings": {}, "by_model": {}}
        for r in runs:
            s[r.get("status", "failed")] = s.get(r.get("status", "failed"), 0) + 1
            u = r.get("usage", {})
            s["input_tokens"] += u.get("input_tokens", u.get("input_tokens_est", 0))
            s["output_tokens"] += u.get("output_tokens", u.get("output_tokens_est", 0))
            s["cost_usd"] += r.get("cost_usd", 0)
            s["latency_s"] += r.get("latency_s", 0)
            s["cards_written"] += len(r.get("written", []))
            for k in s["grounding"]:
                s["grounding"][k] += r.get("grounding", {}).get(k, 0)
            for f in r.get("findings", []):
                key = re.sub(r"'[^']*'|\[[^\]]*\]|\"[^\"]*\"", "…", f["msg"])
                s["findings"][key] = s["findings"].get(key, 0) + 1
            bm = s["by_model"].setdefault(r.get("model") or "?", {"runs": 0, "latency_s": 0.0})
            bm["runs"] += 1
            bm["latency_s"] += r.get("latency_s", 0)
        s["cost_usd"] = round(s["cost_usd"], 4)
        s["latency_s"] = round(s["latency_s"], 2)
        return s


def card_history(kb: KB, cid: str) -> list[dict]:
    return [e for e in read_jsonl(kb.events_path) if e.get("target") == cid]
