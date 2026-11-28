"""Functional units — one anchor, its evidence in every form, with exact provenance.

After Qiu et al. (2026): the evidence for one function (an algorithm, a cost term, a mask representation…) is
spread over a definition here, a parameter table there, pseudo-code in another lecture. A functional unit groups
the *occurrences* of one anchor — an instance of the approved ontology, from the entity graph — together with
the evidence forms of each occurrence and its exact source location:

    unit = (anchor, type, occurrences [(section, document, lines, forms)], forms ∪, documents)

Rules (conservative, as in the paper): occurrences come from sections where the extraction found the anchor or
its relations' evidence; a unit is *cross-document* only with ≥ 2 documents and ≥ 2 evidence forms; at most 8
occurrences per unit, chosen to cover as many forms as possible (no hub anchors pulling in everything).

Units are retrieved lexically (BM25 over anchor names, type and section titles/summaries) and expanded only to
their own sections — never to graph neighbours. Derived from the graph; rebuilt with it.
"""
from __future__ import annotations

import threading

from . import graph as G
from . import pageindex as PI
from . import sources as S
from .artifacts import coverage
from .textindex import BM25

MAX_OCC = 8
_LOCK = threading.RLock()
_CACHE: dict = {}


def build(kb, cards, readers: bool) -> tuple[dict, BM25]:
    g = G.build(kb, cards, readers)
    key = (str(kb.root), readers, id(g))
    with _LOCK:
        if key in _CACHE:
            return _CACHE[key]
    meta = S.meta_ro(kb)
    onto = G.ontology(kb)
    trees: dict = {}

    def node(sid):
        path, nid = sid[2:].split("#")
        if path not in trees:
            trees[path] = PI.doc_tree(kb, path, meta)
        return PI.find(trees[path], nid), path

    units = {}
    for eid, d in g.nodes.items():
        if d.get("kind") != "entity" or not d.get("type"):
            continue
        occ: dict[str, int] = {}
        for e in g.inc.get(eid, []):  # sections in which the extraction found the anchor
            if e["layer"] in ("extracted", "indexed") and e["s"].startswith("s:"):
                occ[e["s"]] = occ.get(e["s"], 0) + 2
        for e in g.out.get(eid, []) + g.inc.get(eid, []):  # sections that ground the anchor's relations
            for ev in e.get("evidence") or []:
                try:
                    tree = trees.get(ev["path"]) or PI.doc_tree(kb, ev["path"], meta)
                except Exception:  # noqa: BLE001
                    continue
                trees[ev["path"]] = tree
                s = G.section_at(tree, ev.get("lines"))
                if s:
                    sid = f"s:{ev['path']}#{s}"
                    occ[sid] = occ.get(sid, 0) + 1
        items = []
        for sid, w in occ.items():
            nd, path = node(sid)
            if nd:
                items.append({"section": sid, "path": path, "title": nd["title"], "start": nd["start"], "end": nd["end"],
                              "summary": nd.get("summary") or nd.get("gist", ""), "types": nd.get("types", []), "weight": w})
        if not items:
            continue
        # greedy: cover as many evidence forms as possible, then by weight; at most MAX_OCC occurrences
        items.sort(key=lambda x: -x["weight"])
        chosen, have = [], set()
        for it in sorted(items, key=lambda x: (-len(set(x["types"]) - have), -x["weight"])):
            if len(chosen) >= MAX_OCC:
                break
            chosen.append(it)
            have |= set(it["types"])
        docs = sorted({x["path"] for x in chosen})
        units[eid] = {"id": eid, "anchor": d["title"], "aliases": d.get("aliases", []), "type": d["type"],
                      "type_label": onto["entity_types"].get(d["type"], d["type"]), "occurrences": chosen,
                      "forms": sorted(have), "documents": docs, "cross_document": len(docs) >= 2 and len(have) >= 2}
    bm = BM25()
    for uid, u in units.items():
        bm.put(uid, 1, [(u["anchor"] + " " + " ".join(u["aliases"]), 4), (u["type_label"], 2),
                        (" ".join(o["title"] + " " + o["summary"] for o in u["occurrences"]), 1)], payload=uid)
    with _LOCK:
        if len(_CACHE) > 8:
            _CACHE.clear()
        _CACHE[key] = (units, bm)
    return units, bm


def search(kb, cards, readers: bool, question: str, need=None, k: int = 4) -> list[dict]:
    """Units for a question, BM25 re-ranked by how well their evidence forms cover the needed forms."""
    units, bm = build(kb, cards, readers)
    hits = bm.search(question, k * 4)
    ranked = sorted(hits, key=lambda h: -h[0] * (0.5 + 0.5 * coverage(need, units[h[1]]["forms"])))
    return [units[uid] for _, uid in ranked[:k]]


__all__ = ["build", "search", "MAX_OCC"]
