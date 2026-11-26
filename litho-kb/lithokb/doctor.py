"""`lkb doctor` and `lkb refresh` — one place to see and fix what is out of date or misconfigured.

doctor  checks configuration (backend, API key present), the schema/ontology (relations reference declared
        types), every derived structure (PageIndex summaries, topic graph, entity extraction, card index vs.
        changed sources), review backlog, open issues, evaluation coverage, and file integrity (fsck).
        Each finding: {level: ok|info|warn|error, area, message, fix} — `fix` is the command that resolves it.
refresh brings the derived structures up to date in dependency order:
        PageIndex summaries (changed documents) → topic graph (if stale) → entity extraction (pending
        documents for the approved ontology). Dry run by default; LLM calls only for what is out of date.
"""
from __future__ import annotations

import json
import os
import time

from . import graph as G
from . import sources as S
from .cards import CARD_TYPES
from .store import KB


def _f(level, area, message, fix=""):
    return {"level": level, "area": area, "message": message, "fix": fix}


def doctor(kb: KB, cards, comp) -> dict:
    from . import evalset as E
    from . import pageindex as PI
    from . import topics as T
    from .entities import Extractor
    from .fsck import fsck
    t0 = time.perf_counter()
    out = []
    llm = kb.config["llm"]
    be = llm.get("backend", "mock")
    if be == "mock":
        out.append(_f("info", "config", "LLM backend is 'mock' (offline, deterministic): fine for tests, not for real compilation",
                      "set llm.backend in config.json"))
    elif be == "openrouter" and not (os.environ.get("OPEN_ROUTER_API_KEY") or os.environ.get("OPENROUTER_API_KEY")):
        out.append(_f("error", "config", "backend 'openrouter' but no OPEN_ROUTER_API_KEY in the environment", "export OPEN_ROUTER_API_KEY=…"))
    elif be == "anthropic" and not os.environ.get("ANTHROPIC_API_KEY"):
        out.append(_f("warn", "config", "backend 'anthropic' and no ANTHROPIC_API_KEY (an `ant auth` profile may still work)"))
    else:
        out.append(_f("ok", "config", f"LLM backend {be}"))
    onto = G.ontology(kb)
    types = set(onto["entity_types"])
    bad = [f"{r}: {sorted((v['domain'] | v['range']) - types - {'*'})}" for r, v in onto["entity_relations"].items()
           if (v["domain"] | v["range"]) - types - {"*"}]
    if bad:
        out.append(_f("error", "ontology", "entity relations reference undeclared types: " + "; ".join(bad), "lkb ontology propose / edit SCHEMA.md"))
    cbad = [r for r, (a, b) in onto["constraints"].items() if (a | b) - set(CARD_TYPES) - {"*"}]
    if cbad:
        out.append(_f("warn", "ontology", f"card-relation constraints use unknown card types: {', '.join(cbad)}"))
    out.append(_f("ok", "ontology", f"{len(types)} entity types, {len(onto['entity_relations'])} entity relations, "
                                    f"{len(onto['constraints'])} card constraints"))
    st = PI.Indexer(kb, comp).status()
    out.append(_f("warn" if st["pending"] else "ok", "pageindex",
                  f"{st['compiled']}/{st['documents']} documents have compiled node summaries" +
                  (f"; {len(st['pending'])} pending" if st["pending"] else ""), "lkb refresh --apply" if st["pending"] else ""))
    ts = T.status(kb)
    if not ts["built"]:
        out.append(_f("warn", "topics", "topic graph not built (broad questions cannot fan out over themes)", "lkb refresh --apply"))
    elif ts["stale"]:
        out.append(_f("warn", "topics", "topic graph is stale (sources or summaries changed since it was built)", "lkb refresh --apply"))
    else:
        out.append(_f("ok", "topics", f"{ts['topics']} topics / {ts['subtopics']} subtopics, coverage {ts['coverage']}"))
    if onto["entity_relations"]:
        xs = Extractor(kb, comp).status()
        out.append(_f("warn" if xs["pending"] else "ok", "entities",
                      f"{xs['extracted']}/{xs['documents']} documents extracted for the current ontology "
                      f"({xs['entities']} instances, {xs['relations']} relations)" +
                      (f"; {len(xs['pending'])} pending" if xs["pending"] else ""), "lkb refresh --apply" if xs["pending"] else ""))
    else:
        out.append(_f("info", "entities", "no entity relations in the ontology yet: the entity graph is not extracted",
                      "lkb eval import … then lkb ontology propose"))
    idx = cards.index()
    stale = [c for c, m in idx.items() if m.get("stale_sources") and m.get("lifecycle", "active") == "active"]
    if stale:
        out.append(_f("warn", "cards", f"{len(stale)} cards cite sources that changed after compilation", "lkb compile (changed sources)"))
    queue = sum(m["status"] in ("in_review", "approved", "changes_requested") for m in idx.values())
    out.append(_f("info" if queue else "ok", "review", f"{len(idx)} cards; {queue} waiting in the review/publish queue"))
    from .issues import Issues
    iss = Issues(kb).stats()
    out.append(_f("info", "issues", f"open issues: {json.dumps(iss.get('open', iss), ensure_ascii=False)}"))
    qs = E.load(kb)
    runs = E.runs(kb)
    if not qs:
        out.append(_f("warn", "evaluation", "no golden questions: changes to schema, ontology, model or retrieval are untested",
                      "lkb eval import questions.json"))
    else:
        last = runs[0] if runs else None
        out.append(_f("ok" if last else "warn", "evaluation", f"{len(qs)} golden questions; " +
                      (f"last run {last['at']} key points {last['aggregate'].get('key_points')}" if last else "never evaluated"),
                      "" if last else "lkb eval run --repeat 3"))
    fs = fsck(kb, cards)
    real = [p for p in fs["problems"] if p["kind"] not in ("orphan_pageindex", "orphan_entities")]
    out.append(_f("error" if real else "ok", "files", f"fsck: {len(real)} problem(s)" +
                  (": " + ", ".join(sorted({p['kind'] for p in real})) if real else ""), "lkb fsck" if real else ""))
    levels = [f["level"] for f in out]
    return {"status": "error" if "error" in levels else "warn" if "warn" in levels else "ok",
            "findings": out, "seconds": round(time.perf_counter() - t0, 2)}


def refresh(kb: KB, cards, comp, actor: str, cfg: dict, apply: bool = False, limit: int = 0) -> dict:
    """Bring derived structures up to date in dependency order. Dry run unless apply=True."""
    from . import pageindex as PI
    from . import topics as T
    from .entities import Extractor
    plan, done = [], []
    st = PI.Indexer(kb, comp).status()
    if st["pending"]:
        plan.append({"step": "pageindex", "documents": st["pending"]})
    ts = T.status(kb)
    if st["pending"] or not ts["built"] or ts["stale"]:
        plan.append({"step": "topics", "why": "pending summaries" if st["pending"] else "not built" if not ts["built"] else "stale"})
    if G.ontology(kb)["entity_relations"]:
        xs = Extractor(kb, comp).status()
        if xs["pending"] or st["pending"]:
            plan.append({"step": "entities", "documents": xs["pending"][:limit] if limit else xs["pending"]})
    if not apply:
        return {"apply": False, "plan": plan}
    for p in plan:
        if p["step"] == "pageindex":
            r = PI.Indexer(kb, comp).run(actor, cfg, p["documents"])
            done.append({"step": "pageindex", "indexed": len(r["indexed"]), "failed": r["failed"], "cost_usd": r["cost_usd"]})
        elif p["step"] == "topics":
            r = T.TopicBuilder(kb, comp).build(actor, cfg)
            done.append({"step": "topics", "status": r["status"], "error": r.get("error"), "cost_usd": r.get("cost_usd")})
        elif p["step"] == "entities":
            r = Extractor(kb, comp).run(actor, cfg, limit=limit)
            done.append({"step": "entities", "extracted": len(r["extracted"]), "failed": r["failed"], "cost_usd": r["cost_usd"]})
    kb.event(actor, "refresh", "", steps=[d["step"] for d in done])
    return {"apply": True, "plan": plan, "done": done}


__all__ = ["doctor", "refresh"]
