"""Consolidate / split over-grown cards; merge thin cards (granularity correction).

Cards grow by `append` as more documents mention a concept. Past the granularity
bounds (see quality.py) a card stops being readable in one sitting and stops being
cheap for an agent to load. Two corrections:

* consolidate (LLM): rewrite the card into one coherent text within the target size,
  or — when it really covers several sub-concepts — split it into a parent plus child
  cards. Hard rule: only the card's EXISTING, already-verified evidence may be used
  (no new facts); evidence not cited by any output stays with the parent, so no
  provenance is ever lost. Results are new revisions in review (risk: medium).
* merge (deterministic, admin): fold a thin card into a related one; the thin card is
  superseded (readers following its link are redirected).
"""
from __future__ import annotations

import json
import re
import traceback

from .cards import Cards, CardError, slug
from .compiler import Compiler, new_run_id
from .quality import granularity_cfg, measure, units
from .store import KB, atomic_write, now

PROMPT_VERSION = "lkb-consolidate/1"

SYSTEM = """[[LKB:CONSOLIDATE]]
You are the editor of LithoKB, a curated computational-lithography knowledge base. One knowledge card has grown
by accretion (several "补充（来自…）" additions from different documents) and is now too long or fragmented.
Rewrite it so that a domain engineer can read it in one sitting and an agent can load it cheaply.

Size targets (reading units = CJK characters + Latin words): each card body between {min_units} and {target_max}
units; never above {hard_max}.

Decide:
- "rewrite": the card is ONE concept → produce one coherent body (definition first, then organised key points;
  merge duplicates; keep formulas; remove the per-source "补充" headings — provenance stays in the evidence).
- "split": the card covers SEVERAL distinct sub-concepts that each deserve a card → keep a shorter parent body
  (overview + links [[child-id]]) and create child cards (2–5) for the sub-concepts.

Strict rules:
- Use ONLY the evidence ids listed. Do not introduce facts that are not supported by them. Put [E#] markers after
  the statements they support. A child card lists the evidence ids it uses in "evidence".
- Child ids: new lowercase English kebab-case ids, not already in the list of existing ids.
- Keep the card's language (Chinese with English terms in parentheses).
- Think briefly; write the JSON once, directly.

Return exactly one JSON object in a ```json block:
{{"decision":"rewrite|split","card":{{"title":"…","summary":"≤200 chars","body_md":"…","aliases":["…"]}},
"children":[{{"id":"…","title":"…","type":"concept|method|model|algorithm|parameter|metric|process|issue|result",
"summary":"…","body_md":"…","evidence":["E3","E7"]}}],"notes":"what you merged, dropped as duplicate, or split, and why"}}"""


class Consolidator:
    def __init__(self, kb: KB, cards: Cards, comp: Compiler):
        self.kb, self.cards, self.comp = kb, cards, comp

    def candidates(self) -> list[dict]:
        cfg = granularity_cfg(self.kb)
        out = []
        for cid, m in self.cards.index().items():
            if m.get("lifecycle", "active") != "active" or m.get("status") == "rejected":
                continue
            g = measure(m, m.get("_body", ""), cfg)
            if g["needs_consolidation"]:
                out.append({"id": cid, "title": m["title"], **g})
        return sorted(out, key=lambda x: -x["units"])

    def run(self, user: dict, cid: str, cfg: dict, from_rev: int | None = None) -> dict:
        """Consolidate the head revision — or an earlier revision (e.g. when a previous
        consolidation lost content and should be redone from the richer version)."""
        gcfg = granularity_cfg(self.kb)
        head, body = self.cards.load(cid)
        if from_rev and from_rev != head["rev"]:
            base, body = self.cards.load_rev(cid, from_rev)
            head = {**base, "rev": head["rev"], "published_rev": head.get("published_rev"), "base_rev": from_rev}
        rid = new_run_id()
        run = {"id": rid, "kind": "consolidate", "by": user["name"], "started": now(), "status": "running",
               "backend": cfg["backend"], "model": cfg.get("model"), "prompt_version": PROMPT_VERSION,
               "card": cid, "card_rev": head["rev"], "from_rev": from_rev or head["rev"], "sources": sorted({s["path"] for s in head.get("sources", [])}),
               "source_shas": {}, "timeline": [], "written": [], "findings": []}

        def step(name, **kw):
            run["timeline"].append({"ts": now(), "step": name, **kw})
            self.comp._save_run(run)

        try:
            before = measure(head, body, gcfg)
            run["before"] = before
            ev = head.get("evidence", [])
            ev_ids = {e["id"] for e in ev}
            siblings = [f"{m['id']} | {m['title']}" for m in self.cards.index().values()
                        if m.get("parent") in (cid, head.get("parent")) and m["id"] != cid][:60]
            system = SYSTEM.format(**gcfg)
            user_msg = (f"# Card to consolidate (current size {before['units']} units, {before['appends']} additions, "
                        f"{before['evidence']} evidence items)\n<card id=\"{cid}\">\n"
                        f"title: {head['title']}\ntype: {head['type']}\nsummary: {head.get('summary', '')}\n"
                        f"aliases: {json.dumps(head.get('aliases', []), ensure_ascii=False)}\n\n{body}\n</card>\n\n"
                        "# Evidence available (id | source | lines | verbatim quote)\n" +
                        "\n".join(f"{e['id']} | {e['path']} | {e['lines']} | {e['quote']}" for e in ev) +
                        "\n\n# Existing ids nearby (do not reuse for children)\n" + ("\n".join(siblings) or "(none)") +
                        "\n\n# Task\nConsolidate this card following the rules.")
            step("prompt_built", units=before["units"])
            prompt_now = user_msg
            for attempt in (1, 2):  # one corrective retry on unusable output, as in compilation
                res = self.comp.llm_step(run, cfg, system, prompt_now, prefix="" if attempt == 1 else "retry1-")
                try:
                    if res.stop_reason == "max_tokens":
                        raise ValueError("output truncated at max_tokens")
                    data = parse_response_any(res.text)
                    atomic_write(self.comp._trace_dir(rid) / "parsed.json", json.dumps(data, ensure_ascii=False, indent=1))
                    plan = self._validate(cid, head, data, ev_ids, gcfg, run["findings"])
                    break
                except (ValueError, json.JSONDecodeError) as e:
                    run.setdefault("attempt_errors", []).append(f"attempt {attempt}: {e}")
                    if attempt == 2:
                        raise
                    prompt_now = (user_msg + f"\n\n# Correction\nYour previous answer was not usable ({str(e)[:160]}). "
                                  'Return exactly {"decision":…,"card":{"title","summary","body_md","aliases"},"children":[…],"notes":…} '
                                  "with body_md INSIDE card.")
            run["attempts"] = attempt
            step("validated", decision=plan["decision"], children=len(plan["children"]))
            self._apply(user, cid, head, plan, rid, res.model, run)
            run["after"] = measure(self.cards.load(cid)[0], self.cards.load(cid)[1], gcfg)
            run["notes"] = str(data.get("notes", ""))
            run["status"] = "done"
            step("written", cards=len(run["written"]))
        except Exception as e:
            run["status"] = "failed"
            run["error"] = f"{type(e).__name__}: {e}"
            atomic_write(self.comp._trace_dir(rid) / "error.txt", traceback.format_exc())
            step("failed", error=run["error"])
        run["finished"] = now()
        self.comp._save_run(run)
        self.kb.event(user["name"], f"card.consolidate.{run['status']}", cid, run=rid,
                      decision=run.get("timeline", [{}])[-1].get("decision", ""), error=run.get("error", ""))
        return run

    def _validate(self, cid, head, data, ev_ids, gcfg, findings) -> dict:
        decision = data.get("decision") if data.get("decision") in ("rewrite", "split") else "rewrite"
        card = dict(data.get("card")) if isinstance(data.get("card"), dict) else {}
        for k in ("title", "summary", "body_md", "aliases"):  # tolerate fields placed beside "card" (observed)
            if not card.get(k) and data.get(k):
                card[k] = data[k]
        for k in ("children", "notes"):  # ... and children/notes nested inside "card" (observed)
            if not data.get(k) and card.get(k):
                data[k] = card[k]
        body = str(card.get("body_md", "") or "").strip()
        if not body:
            raise ValueError("consolidation returned an empty card body")

        def check_markers(text, where, allowed):
            bad = sorted(set(re.findall(r"\[(E\d+)\]", text)) - allowed)
            if bad:
                findings.append({"level": "error", "card": where, "msg": f"cites evidence not on the card: {bad} — removed"})
                text = re.sub(r"\[(E\d+)\]", lambda m: "" if m.group(1) in bad else m.group(0), text)
            return text

        body = check_markers(body, cid, ev_ids)
        children = []
        existing = set(self.cards.index())
        for ch in (data.get("children") or []) if decision == "split" else []:
            if not isinstance(ch, dict):
                continue
            chid = slug(str(ch.get("id", "") or ch.get("title", "")))
            if not chid or chid in existing or chid == cid or any(c["id"] == chid for c in children):
                findings.append({"level": "error", "card": chid or "?", "msg": "child id missing or already exists — dropped"})
                continue
            ids = [x for x in (ch.get("evidence") or []) if x in ev_ids]
            cbody = check_markers(str(ch.get("body_md", "") or ""), chid, set(ids) or ev_ids)
            ids = ids or sorted(set(re.findall(r"\[(E\d+)\]", cbody)) & ev_ids)
            if not ids:
                findings.append({"level": "error", "card": chid, "msg": "child card has no evidence — dropped"})
                continue
            u = units(cbody)
            if u < gcfg["min_units"] or u > gcfg["hard_max"]:
                findings.append({"level": "warn", "card": chid, "msg": f"child size {u} units outside [{gcfg['min_units']}, {gcfg['hard_max']}]"})
            children.append({"id": chid, "title": str(ch.get("title", chid)), "type": ch.get("type", "concept"),
                             "summary": str(ch.get("summary", ""))[:300], "body": cbody, "evidence_ids": ids})
        if decision == "split" and not children:
            findings.append({"level": "warn", "card": cid, "msg": "split requested but no valid child — treated as rewrite"})
            decision = "rewrite"
        u = units(body)
        if u > gcfg["hard_max"]:
            findings.append({"level": "warn", "card": cid, "msg": f"rewritten body still {u} units (> hard max {gcfg['hard_max']})"})
        return {"decision": decision, "title": str(card.get("title") or head["title"]),
                "summary": str(card.get("summary") or head.get("summary", ""))[:300],
                "aliases": list(dict.fromkeys(list(head.get("aliases", [])) + [a for a in card.get("aliases", []) or [] if isinstance(a, str)])),
                "body": body, "children": children}

    def _apply(self, user, cid, head, plan, rid, model, run):
        ev = {e["id"]: e for e in head.get("evidence", [])}
        origin = {"kind": "llm", "op": "consolidate", "run": rid, "model": model, "by": user["name"]}
        used_by_children = set()
        for ch in plan["children"]:
            mapping = {old: f"E{i + 1}" for i, old in enumerate(ch["evidence_ids"])}
            used_by_children |= set(ch["evidence_ids"])
            cbody = re.sub(r"\[(E\d+)\]", lambda m: f"[{mapping.get(m.group(1), m.group(1))}]", ch["body"])
            card = {"id": ch["id"], "title": ch["title"], "type": ch["type"], "parent": cid, "aliases": [],
                    "summary": ch["summary"],
                    "relations": [{"rel": "part_of", "target": cid, "basis": "inferred", "confidence": 0.9}],
                    "evidence": [{**{k: ev[o][k] for k in ("path", "lines", "quote")}, "id": mapping[o]} for o in ch["evidence_ids"]],
                    # facets follow their evidence into the child card
                    **{k: [{**x, "evidence": mapping[x["evidence"]]} for x in head.get(k, []) or []
                           if x.get("evidence") in mapping] for k in ("conditions", "events", "facts")},
                    "sources": sorted({ev[o]["path"] for o in ch["evidence_ids"]}), "confidence": head.get("confidence")}
            h = self.cards.new_revision(user["name"], card, cbody, origin, change_note=f"split from {cid} (consolidation {rid})")
            run["written"].append({"id": ch["id"], "rev": h["rev"], "action": "create", "grounding": h["grounding"]})
        body = plan["body"]
        if plan["children"]:
            missing = [c for c in plan["children"] if f"[[{c['id']}" not in body]
            if missing:
                body += "\n\n## 子概念\n" + "".join(f"\n- [[{c['id']}|{c['title']}]] — {c['summary']}" for c in missing)
        cited = set(re.findall(r"\[(E\d+)\]", body))
        child_cited = set().union(*[set(c["evidence_ids"]) for c in plan["children"]]) if plan["children"] else set()
        coverage = len((cited | child_cited) & set(ev)) / max(1, len(ev))
        run["evidence_coverage"] = round(coverage, 2)
        if coverage < 0.5:
            run["findings"].append({"level": "warn", "card": cid, "msg": f"consolidated text cites only {len(cited | child_cited)}/{len(ev)} "
                                    "evidence items — content may have been dropped; consider a split"})
        origin = {**origin, "evidence_coverage": round(coverage, 2)}
        # provenance is never lost: evidence not moved to a child stays with the parent
        keep = [e for eid, e in ev.items() if eid in cited or eid not in used_by_children]
        card = {"id": cid, "title": plan["title"], "type": head["type"], "parent": head.get("parent", ""),
                "aliases": plan["aliases"], "summary": plan["summary"], "relations": head.get("relations", []),
                "evidence": [{k: e[k] for k in ("id", "path", "lines", "quote")} for e in keep],
                **{k: [x for x in head.get(k, []) or [] if x.get("evidence") in {e["id"] for e in keep}]
                   for k in ("conditions", "events", "facts")},
                "sources": sorted({e["path"] for e in keep}), "confidence": head.get("confidence")}
        note = f"consolidation {rid}: {plan['decision']}" + (f" into {len(plan['children'])} child card(s)" if plan["children"] else "")
        h = self.cards.new_revision(user["name"], card, body, origin, change_note=note)
        run["written"].append({"id": cid, "rev": h["rev"], "action": plan["decision"], "grounding": h["grounding"]})


def parse_response_any(text: str) -> dict:
    m = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.S)
    raw = m.group(1) if m else text[text.find("{"): text.rfind("}") + 1]
    data = json.loads(raw)
    if isinstance(data, str):
        data = json.loads(data)
    if not isinstance(data, dict):
        raise ValueError("expected a JSON object")
    return data


def merge(cards: Cards, user: dict, src: str, into: str) -> dict:
    """Fold a (thin) card into another one, deterministically; the source card is superseded."""
    from .auth import require
    require(user, "admin")
    if src == into:
        raise CardError("cannot merge a card into itself")
    a, abody = cards.load(into)
    b, bbody = cards.load(src)
    used = {e["id"] for e in a.get("evidence", [])}
    n = max([int(x[1:]) for x in used if re.fullmatch(r"E\d+", x)] or [0])
    mapping, new_ev = {}, []
    for e in b.get("evidence", []):
        n += 1
        mapping[e["id"]] = f"E{n}"
        new_ev.append({**{k: e[k] for k in ("path", "lines", "quote")}, "id": f"E{n}"})
    add = re.sub(r"\[(E\d+)\]", lambda m: f"[{mapping.get(m.group(1), m.group(1))}]", bbody).strip()
    body = abody.rstrip() + f"\n\n### 并入：{b['title']}\n\n{add}\n"
    rels = list(a.get("relations", []))
    have = {(r["rel"], r["target"]) for r in rels}
    for r in b.get("relations", []):
        if r["target"] != into and (r["rel"], r["target"]) not in have:
            rels.append(r)
            have.add((r["rel"], r["target"]))
    card = {"id": into, "title": a["title"], "type": a["type"], "parent": a.get("parent", ""),
            "aliases": list(dict.fromkeys(list(a.get("aliases", [])) + [b["title"]] + list(b.get("aliases", [])))),
            "summary": a.get("summary", ""), "relations": rels,
            "evidence": [{k: e[k] for k in ("id", "path", "lines", "quote")} for e in a.get("evidence", [])] + new_ev,
            **{k: list(a.get(k, []) or []) + [{**x, "evidence": mapping[x["evidence"]]} for x in b.get(k, []) or []
                                              if x.get("evidence") in mapping] for k in ("conditions", "events", "facts")},
            "sources": sorted({s["path"] for s in a.get("sources", [])} | {s["path"] for s in b.get("sources", [])}),
            "confidence": a.get("confidence")}
    h = cards.new_revision(user["name"], card, body, {"kind": "human", "op": "merge", "user": user["name"], "merged": src},
                           change_note=f"merged {src} into {into}")
    cards.act(user, src, "supersede", f"merged into {into}", target=into)
    return h
