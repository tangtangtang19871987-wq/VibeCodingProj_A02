"""Model-free retrieval: one call, a complete context pack for an agent (or a person).

`ask` spends one to four model calls to navigate, read and write an answer. Agents that write their
own answers need something else: fast, deterministic, citable context. `retrieve(question)` returns

  cards     published knowledge cards ranked by BM25, with summary and applicability
  sections  source sections (author-defined, not chunks) ranked by BM25, with line ranges and
            PageIndex summaries — read them with read_source(path, start, end)
  facts     entity-graph relations / instances relevant to the question, each with the verified
            quote, document and lines it was extracted from
  themes    topics whose title or summary match, with their representative sections

No LLM, no vectors; typically a few milliseconds on a warm server.
"""
from __future__ import annotations

from . import facets as F
from . import graph as G
from . import pageindex as PI
from . import sources as S
from .textindex import BM25


def retrieve(kb, cards, question: str, readers: bool = True, conditions: dict | None = None, limit: int = 8) -> dict:
    question = (question or "").strip()
    if not question:
        raise ValueError("empty question")
    limit = max(1, min(int(limit), 30))
    idx = cards.index()
    out_cards = []
    for h in cards.search(question, visible_only=readers, limit=limit * 3):
        m = cards.view(idx[h["id"]], readers)
        if m is None or m.get("lifecycle", "active") != "active":
            continue
        conds = F.ok(m.get("conditions", []))
        a = F.applies(conds, conditions or {})
        if a == "no":
            continue
        out_cards.append({"id": h["id"], "title": m["title"], "type": m["type"], "summary": m.get("summary", ""),
                          "applies": a, "conditions": [f"{c['dim']}={c['value']}" for c in conds], "score": h["score"]})
        if len(out_cards) >= limit:
            break
    meta = S.meta_ro(kb)
    bm = PI.section_index(kb)
    secs = []
    for sc, key in bm.search(question, limit):
        pl = bm.payload(key)
        nd = PI.find(PI.doc_tree(kb, pl["path"], meta), pl["node"])
        if nd:
            secs.append({"path": pl["path"], "document": S.doc_titles(kb, [pl["path"]]).get(pl["path"], pl["path"]),
                         "section": nd["title"], "start": nd["start"], "end": nd["end"],
                         "summary": nd.get("summary") or nd.get("gist", ""), "score": sc})
    facts = []
    for f in G.facts_for(kb, cards, readers, question, limit=limit)[:limit * 2]:
        ev = f.get("evidence") or {}
        item = ({"relation": f"{f['subject']} —{f['rel']}→ {f['object']}"} if f["kind"] == "relation"
                else {"instance": f["name"], "type": f.get("type_label") or f.get("type")})
        item.update({"path": ev.get("path"), "lines": ev.get("lines"), "quote": ev.get("quote")})
        facts.append(item)
    themes = []
    from .topics import load as load_topics
    t = load_topics(kb)
    if t:
        tb = BM25()
        for x in t["topics"]:
            tb.put(x["id"], 1, [(x["title"], 3), (x.get("summary", ""), 1)], payload=x)
        for sc, tid in tb.search(question, 3):
            x = tb.payload(tid)
            reps = []
            for m in x.get("representative", [])[:4]:
                path, nid = m[2:].split("#")
                nd = PI.find(PI.doc_tree(kb, path, meta), nid)
                if nd:
                    reps.append({"path": path, "section": nd["title"], "start": nd["start"], "end": nd["end"]})
            themes.append({"id": x["id"], "title": x["title"], "summary": x.get("summary", ""),
                           "sections": len(x["members"]), "representative": reps})
    return {"question": question, "scope": "published" if readers else "all", "cards": out_cards, "sections": secs,
            "facts": facts, "themes": themes,
            "next": "Read cards with get_card(id), sections with read_source(path, start, end); check quotes with verify_quote."}


__all__ = ["retrieve"]
