"""Facet annotation: add applicability conditions, dated events and structured facts to
existing cards (backfill), using only each card's own verified evidence.

New compiles produce facets directly; this pass brings cards compiled earlier up to date.
One small LLM call per card; results that change a card become a new revision in review
(origin op "annotate"). Every facet item must cite one of the card's evidence ids.
"""
from __future__ import annotations

import json
import traceback

from . import facets as F
from .cards import Cards
from .compiler import Compiler, new_run_id
from .consolidate import parse_response_any
from .store import KB, atomic_write, now

PROMPT_VERSION = "lkb-annotate/2"

SYSTEM = """[[LKB:ANNOTATE]]
You annotate one knowledge card of a computational-lithography knowledge base with facets. Use ONLY the card's
evidence quotes (listed with ids); never add knowledge from elsewhere. Every item cites exactly one evidence id
whose quote states it. If the evidence states nothing for a facet, return an empty list for it.
Values are machine-checked against the cited quote: copy numbers, units and terms VERBATIM in the quote's own
language — do not translate, paraphrase, count, sum or derive. Names may be short labels in the card's language.

- conditions: under which conditions the card's statements hold. Allowed dimensions:
{dims}
  Item: {{"dim":"node","value":"7nm and below","evidence":"E3"}}. Only explicit statements (not guesses).
- events: dated milestones or evolution steps. Item: {{"when":"2019","what":"…","evidence":"E2"}}.
- facts: values worth comparing across cards — parameters, metrics, typical ranges, counts.
  Item: {{"name":"DOF","value":"> 100","unit":"nm","conditions":{{"node":"7nm"}},"evidence":"E4"}}.

Think briefly. Return exactly one JSON object in a ```json block: {{"conditions":[…],"events":[…],"facts":[…]}}"""


class Annotator:
    def __init__(self, kb: KB, cards: Cards, comp: Compiler):
        self.kb, self.cards, self.comp = kb, cards, comp

    def unsupported(self) -> list[str]:
        """Cards with at least one facet whose cited quote does not state it."""
        return sorted(cid for cid, m in self.cards.index().items()
                      if any(x.get("supported") is False for k in ("conditions", "events", "facts") for x in m.get(k, []) or []))

    def candidates(self, only_missing: bool = True) -> list[str]:
        out = []
        for cid, m in self.cards.index().items():
            if m.get("lifecycle", "active") != "active" or m.get("status") == "rejected" or not m.get("evidence"):
                continue
            if m["type"] in ("topic",):
                continue
            if only_missing and any(m.get(k) for k in ("conditions", "events", "facts")):
                continue
            if only_missing and (m.get("origin") or {}).get("op") == "annotate":
                continue
            out.append(cid)
        return sorted(out)

    def run(self, user: dict, cid: str, cfg: dict) -> dict:
        rid = new_run_id()
        head, body = self.cards.load(cid)
        run = {"id": rid, "kind": "annotate", "by": user["name"], "started": now(), "status": "running",
               "backend": cfg["backend"], "model": cfg.get("model"), "prompt_version": PROMPT_VERSION, "card": cid,
               "sources": sorted({s["path"] for s in head.get("sources", [])}), "source_shas": {}, "timeline": [],
               "written": [], "findings": []}
        try:
            dims = F.dims(self.kb)
            system = SYSTEM.format(dims="\n".join(f"  - {k}: {v[0]} ({v[1]})" for k, v in dims.items()) or "  (none declared)")
            ev = head.get("evidence", [])
            user_msg = (f"<card id=\"{cid}\" type=\"{head['type']}\">\n# {head['title']}\n{head.get('summary', '')}\n\n{body}\n</card>\n\n"
                        "# Evidence (id | source | verbatim quote)\n" + "\n".join(f"{e['id']} | {e['path']} | {e['quote']}" for e in ev))
            res = self.comp.llm_step(run, cfg, system, user_msg)
            data = parse_response_any(res.text)
            atomic_write(self.comp._trace_dir(rid) / "parsed.json", json.dumps(data, ensure_ascii=False, indent=1))
            fac = F.normalize(data, {e["id"] for e in ev}, dims, run["findings"], cid)
            run["facets"] = {k: len(v) for k, v in fac.items()}
            changed = any(fac[k] != (head.get(k) or []) for k in fac) and any(fac.values())
            if changed:
                card = {k: head.get(k) for k in ("id", "title", "type", "parent", "aliases", "summary", "relations",
                                                 "confidence")}
                card["evidence"] = [{k: e[k] for k in ("id", "path", "lines", "quote")} for e in ev]
                card["sources"] = [s["path"] for s in head.get("sources", [])]
                card.update(fac)
                h = self.cards.new_revision(user["name"], card, body, {"kind": "llm", "op": "annotate", "run": rid,
                                                                       "model": res.model, "by": user["name"]},
                                            change_note="added facets: " + ", ".join(f"{k} {len(v)}" for k, v in fac.items() if v))
                run["written"].append({"id": cid, "rev": h["rev"], "action": "annotate", "grounding": h["grounding"]})
            run["status"] = "done"
        except Exception as e:
            run["status"] = "failed"
            run["error"] = f"{type(e).__name__}: {e}"
            atomic_write(self.comp._trace_dir(rid) / "error.txt", traceback.format_exc())
        run["finished"] = now()
        self.comp._save_run(run)
        self.kb.event(user["name"], f"card.annotate.{run['status']}", cid, run=rid, facets=run.get("facets", {}),
                      error=run.get("error", ""))
        return run
