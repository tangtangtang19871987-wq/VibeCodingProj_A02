"""The knowledge graph — typed, layered, queryable; derived from files, never stored as truth.

Layers (each edge carries `layer` and an epistemic `basis`):

  reviewed    card —rel→ card            typed relations written by the compiler and approved by
                                          reviewers (basis extracted / inferred / ambiguous), parent
                                          (subtopic_of) and [[wikilinks]]
  linked      card —mentions→ card        deterministic entity linking: the card's text names another
              section —mentions→ card     card's title or alias (dictionary = reviewed titles/aliases)
  indexed     section —mentions→ entity   named entities (tools, equipment, organisations, materials …)
              card —mentions→ entity      found by the PageIndex pass; every entity name is verified
                                          verbatim in its document, then linked to cards by name
  provenance  card —derived_from→ doc     the card's evidence sources

Entities that are named like a card (title / alias) *are* that card (entity resolution).
Ontology constraints come from SCHEMA.md ("Graph ontology", or its legacy Chinese heading): entity types and the allowed subject →
object card types of each relation; violations are reported by lint, never silently dropped.

Queries: neighbours (k hops, relation / layer filters), shortest explained path, ego subgraph,
communities (label propagation), centrality (PageRank) — for the UI, the CLI, MCP agents and
for graph-augmented navigation in Q&A.
"""
from __future__ import annotations

import math
import re
import threading
from collections import Counter, defaultdict, deque

from . import schema as SC
from . import sources as S

DEFAULT_ENTITY_TYPES = {"tool": "Software/tool", "equipment": "Equipment", "organization": "Organization/company",
                        "material": "Material", "standard": "Format/standard", "person": "Person", "product": "Product/chip"}
STRONG = {"is_a", "part_of", "subtopic_of", "uses", "depends_on", "implements", "improves", "alternative_to",
          "contrasts_with", "causes", "mitigates", "measured_by", "parameter_of", "input_to", "output_of",
          "example_of", "contradicts", "covers"}
_LOCK = threading.RLock()
_CACHE: dict = {}
_SCAN_CACHE: dict = {}


# ---- ontology (from SCHEMA) ------------------------------------------------------------
def ontology(kb) -> dict:
    """{"entity_types": {type: label}, "constraints": {rel: (set(subject types)|{'*'}, set(object types)|{'*'})}}"""
    text = SC.current(kb)["text"]
    # section heading: "Graph ontology" (or its legacy Chinese heading); constraints follow
    # "Relation constraints" (or the legacy Chinese label); full-width and ASCII colons are accepted
    m = re.search(r"^#+[^\n]*(?:\u672c\u4f53|ontology)[^\n]*\n(.*?)(?=^#{1,2} |\Z)", text, re.M | re.S | re.I)
    et, cons = {}, {}
    if m:
        part = m.group(1)
        cm = re.search(r"\u5173\u7cfb\u7ea6\u675f|relation constraints", part, re.I)
        cpos = cm.start() if cm else -1
        ent_part = part[:cpos] if cpos >= 0 else part
        for mm in re.finditer(r"^[ \t]*[-*][ \t]+`([a-z][a-z0-9_]*)`[ \t]+([^\uff1a:\n]+)", ent_part, re.M):
            et[mm.group(1)] = mm.group(2).strip()
        if cpos >= 0:
            for mm in re.finditer(r"^[ \t]*[-*][ \t]+`([a-z_]+)`[ \t]*[\uff1a:][ \t]*([\w|*]+)[ \t]*(?:→|->)[ \t]*([\w|*]+)",
                                  part[cpos:], re.M):
                cons[mm.group(1)] = (set(mm.group(2).split("|")), set(mm.group(3).split("|")))
    return {"entity_types": et or dict(DEFAULT_ENTITY_TYPES), "constraints": cons}


# ---- deterministic entity linking ------------------------------------------------------------
def _key(s: str) -> str:
    """Matching key: NFKC, lower case, Markdown emphasis removed, whitespace collapsed (word boundaries kept)."""
    import unicodedata
    s = unicodedata.normalize("NFKC", s or "").lower()
    s = re.sub(r"[*_`]+", "", s)
    return re.sub(r"\s+", " ", s).strip()


class Gazetteer:
    """Dictionary matcher: name → ids, scanned by 2-character buckets (O(text length × bucket))."""

    def __init__(self):
        self.names: dict[str, set] = defaultdict(set)
        self.buckets: dict[str, list[str]] = defaultdict(list)

    @staticmethod
    def usable(name: str) -> bool:
        k = _key(name)
        if len(k) < 2:
            return False
        if re.fullmatch(r"[a-z0-9.\-]+", k):  # ASCII: acronyms ≥ 2 letters with a letter, words ≥ 3
            return bool(re.search(r"[a-z]", k)) and (len(k) >= 3 or name.isupper())
        return len(k) >= 2 and not re.fullmatch(r"[\d.\-]+", k)

    def add(self, name: str, ident: str):
        if not self.usable(name):
            return
        k = _key(name)
        if ident not in self.names[k]:
            if not self.names[k]:
                self.buckets[k[:2]].append(k)
            self.names[k].add(ident)

    def finalize(self):
        # per 2-char prefix: the distinct name lengths, longest first → O(#lengths) dict lookups per position
        self.lens = {pre: sorted({len(k) for k in b}, reverse=True) for pre, b in self.buckets.items()}
        self.sig = hash(tuple(sorted((k, tuple(sorted(v))) for k, v in self.names.items())))
        return self

    def scan(self, text: str) -> Counter:
        """ids mentioned in `text` (longest-match, non-overlapping; ASCII names need word boundaries).
        Results are memoised by (dictionary signature, text) — unchanged texts are never rescanned."""
        ck = (self.sig, hash(text), len(text))
        hit = _SCAN_CACHE.get(ck)
        if hit is not None:
            return hit
        t = _key(text)
        hits: Counter = Counter()
        i, n = 0, len(t)
        names = self.names
        while i < n - 1:
            lens = self.lens.get(t[i:i + 2])
            step = 1
            if lens:
                for L in lens:
                    k = t[i:i + L]
                    if len(k) == L and k in names:
                        if re.match(r"[a-z0-9]", k[0]) and ((i > 0 and t[i - 1].isalnum() and t[i - 1].isascii()) or
                                                           (i + len(k) < n and t[i + len(k)].isascii() and t[i + len(k)].isalnum())):
                            continue
                        ids = self.names[k]
                        if len(ids) == 1:  # an ambiguous name (two cards share it) is not evidence of either
                            hits[next(iter(ids))] += 1
                        step = len(k)
                        break
            i += step
        if len(_SCAN_CACHE) > 200_000:
            _SCAN_CACHE.clear()
        _SCAN_CACHE[ck] = hits
        return hits


# ---- graph ---------------------------------------------------------------------------------------
class Graph:
    def __init__(self):
        self.nodes: dict[str, dict] = {}
        self.out: dict[str, list[dict]] = defaultdict(list)
        self.inc: dict[str, list[dict]] = defaultdict(list)
        self.edges: list[dict] = []
        self.findings: list[dict] = []

    def node(self, nid, **kw):
        nd = self.nodes.setdefault(nid, {"id": nid})
        nd.update(kw)
        return nd

    def edge(self, s, t, rel, layer, **kw):
        if s == t or s not in self.nodes or t not in self.nodes:
            return None
        e = {"s": s, "t": t, "rel": rel, "layer": layer, **kw}
        self.edges.append(e)
        self.out[s].append(e)
        self.inc[t].append(e)
        return e

    # -- queries ------------------------------------------------------------------------------
    def adj(self, nid, layers=None, rels=None, undirected=True):
        for e in self.out.get(nid, []):
            if (not layers or e["layer"] in layers) and (not rels or e["rel"] in rels):
                yield e["t"], e, "out"
        if undirected:
            for e in self.inc.get(nid, []):
                if (not layers or e["layer"] in layers) and (not rels or e["rel"] in rels):
                    yield e["s"], e, "in"

    def neighbors(self, nid: str, depth: int = 1, layers=None, rels=None, kinds=None, limit: int = 200) -> list[dict]:
        if nid not in self.nodes:
            return []
        seen = {nid: 0}
        out = []
        q = deque([nid])
        while q and len(out) < limit:
            cur = q.popleft()
            if seen[cur] >= depth:
                continue
            for nb, e, d in self.adj(cur, layers, rels):
                if nb in seen:
                    continue
                seen[nb] = seen[cur] + 1
                if not kinds or self.nodes[nb].get("kind") in kinds:
                    out.append({"id": nb, "hops": seen[nb], "via": cur, "rel": e["rel"], "dir": d, "layer": e["layer"],
                                "basis": e.get("basis"), "title": self.nodes[nb].get("title"),
                                "kind": self.nodes[nb].get("kind")})
                q.append(nb)
        return out

    def path(self, a: str, b: str, max_hops: int = 6, layers=None) -> list[dict] | None:
        """Shortest path preferring reviewed relations (0-1 BFS: reviewed edges cost 1, others 2)."""
        if a not in self.nodes or b not in self.nodes:
            return None
        cost = {a: 0}
        prev: dict = {}
        dq = deque([(0, a)])
        while dq:
            c, cur = dq.popleft()
            if cur == b:
                break
            if c > cost.get(cur, 1e9) or c > max_hops * 2:
                continue
            for nb, e, d in self.adj(cur, layers):
                w = 1 if e["layer"] == "reviewed" else 2
                if c + w < cost.get(nb, 1e9):
                    cost[nb] = c + w
                    prev[nb] = (cur, e, d)
                    if w == 1:
                        dq.appendleft((c + w, nb))
                    else:
                        dq.append((c + w, nb))
        if b not in prev and a != b:
            return None
        steps, cur = [], b
        while cur != a:
            p, e, d = prev[cur]
            steps.append({"from": p, "to": cur, "rel": e["rel"], "dir": d, "layer": e["layer"], "basis": e.get("basis"),
                          "from_title": self.nodes[p].get("title"), "to_title": self.nodes[cur].get("title")})
            cur = p
        return steps[::-1]

    def subgraph(self, seeds: list[str], depth: int = 1, layers=None, limit: int = 120) -> dict:
        keep = [s for s in seeds if s in self.nodes]
        for s in list(keep):
            keep += [n["id"] for n in self.neighbors(s, depth, layers, limit=limit)]
        keep_set = set(list(dict.fromkeys(keep))[:limit])
        return {"nodes": [self.nodes[n] for n in keep_set],
                "edges": [e for e in self.edges if e["s"] in keep_set and e["t"] in keep_set
                          and (not layers or e["layer"] in layers)]}

    def pagerank(self, kinds=("card",), iters: int = 30, d: float = 0.85) -> dict[str, float]:
        ids = [n for n, nd in self.nodes.items() if nd.get("kind") in kinds]
        if not ids:
            return {}
        idset = set(ids)
        pr = {n: 1 / len(ids) for n in ids}
        nbrs = {n: [m for m, e, _ in self.adj(n) if m in idset] for n in ids}
        for _ in range(iters):
            nxt = {n: (1 - d) / len(ids) for n in ids}
            for n in ids:
                if nbrs[n]:
                    share = d * pr[n] / len(nbrs[n])
                    for m in nbrs[n]:
                        nxt[m] += share
                else:
                    for m in ids:
                        nxt[m] += d * pr[n] / len(ids)
            pr = nxt
        return pr

    def communities(self, kinds=("card",), layers=("reviewed", "linked"), iters: int = 20) -> dict[str, int]:
        """Deterministic label propagation over cards (weighted: reviewed 2, linked 1)."""
        ids = sorted(n for n, nd in self.nodes.items() if nd.get("kind") in kinds)
        idset = set(ids)
        label = {n: i for i, n in enumerate(ids)}
        for _ in range(iters):
            changed = 0
            for n in ids:
                w: Counter = Counter()
                for m, e, _ in self.adj(n, layers):
                    if m in idset:
                        w[label[m]] += 2 if e["layer"] == "reviewed" else 1
                if w:
                    best = max(sorted(w.items()), key=lambda kv: kv[1])[0]
                    if best != label[n] and w[best] > w.get(label[n], 0):
                        label[n] = best
                        changed += 1
            if not changed:
                break
        remap = {lab: i for i, lab in enumerate(sorted(set(label.values()), key=lambda x: -list(label.values()).count(x)))}
        return {n: remap[l] for n, l in label.items()}

    def stats(self) -> dict:
        kinds = Counter(nd.get("kind") for nd in self.nodes.values())
        layers = Counter(e["layer"] for e in self.edges)
        rels = Counter(e["rel"] for e in self.edges)
        isolated = [n for n, nd in self.nodes.items() if nd.get("kind") == "card"
                    and not any(True for _ in self.adj(n, ("reviewed", "linked")))]
        return {"nodes": dict(kinds), "edges": dict(layers), "relations": dict(rels.most_common(30)),
                "isolated_cards": isolated[:50], "isolated_count": len(isolated)}


def build(kb, cards, readers: bool) -> Graph:
    """Build (or reuse) the graph for the current state: cache key = card index generation, the
    compiled PageIndex state and the schema version — recomputed only when one of them changes."""
    from .cards import is_public, slug
    from . import pageindex as PI
    idx = cards.index()
    sp = kb.root / "SCHEMA.md"
    key = (str(kb.root), readers, id(cards), cards.generation, PI.state_stamp(kb),
           sp.stat().st_mtime_ns if sp.exists() else 0)
    with _LOCK:
        if key in _CACHE:
            return _CACHE[key]
    meta = S.meta_ro(kb)
    docs = S.list_md_by_policy(kb, "compile", "reference")
    max_m = int(kb.config.get("graph", {}).get("max_mentions_per_source", 10))
    onto = ontology(kb)
    g = Graph()
    vis = {}
    for cid, m in idx.items():
        if m.get("lifecycle", "active") != "active" or m.get("status") == "rejected":
            continue
        v = (m.get("_pub") if is_public(m) else None) if readers else m
        if v is not None:
            vis[cid] = v
    for cid, v in vis.items():
        g.node(cid, kind="card", type=v["type"], title=v["title"], status=v["status"], summary=v.get("summary", ""),
               parent=v.get("parent", ""), grounding=(v.get("grounding") or {}).get("score", 0),
               ambiguous=sum(r.get("basis") == "ambiguous" for r in v.get("relations", [])))
    for p in docs:
        g.node(f"d:{p}", kind="doc", title=S.doc_titles(kb, [p]).get(p, p), path=p)
    # reviewed layer
    for cid, v in vis.items():
        if v.get("parent") in vis:
            g.edge(cid, v["parent"], "subtopic_of", "reviewed", basis="extracted")
        for r in v.get("relations", []):
            t = slug(r.get("target", ""))
            e = g.edge(cid, t, r.get("rel", "related_to"), "reviewed", basis=r.get("basis", "inferred"),
                       conf=r.get("confidence"), note=r.get("note", ""))
            if e:
                con = onto["constraints"].get(e["rel"])
                if con:
                    st, ot = g.nodes[cid]["type"], g.nodes[t]["type"]
                    if ("*" not in con[0] and st not in con[0]) or ("*" not in con[1] and ot not in con[1]):
                        g.findings.append({"kind": "ontology_violation", "card": cid,
                                           "detail": f"{e['rel']}: {st} → {ot} violates constraint {'|'.join(sorted(con[0]))} → {'|'.join(sorted(con[1]))} (target {t})"})
        for t in v.get("_links", []):
            if t in vis:
                g.edge(cid, t, "links_to", "reviewed", basis="extracted")
        for s in v.get("sources", []):
            g.edge(cid, f"d:{s['path'] if isinstance(s, dict) else s}", "derived_from", "provenance")
    # linked layer: deterministic mentions of reviewed names
    gz = Gazetteer()
    for cid, v in vis.items():
        if v["type"] in ("summary", "synthesis"):
            continue
        for name in [v["title"], re.sub(r"[\uff08(].*?[)\uff09]", "", v["title"]).strip()] + list(v.get("aliases", [])):
            gz.add(name, cid)
        for inner in re.findall(r"[\uff08(]([^)\uff09]{2,40})[)\uff09]", v["title"]):  # "Optical Proximity Correction (OPC)" → OPC
            gz.add(inner, cid)
            for part in re.split(r"[,\uff0c/;\uff1b]\s*", inner):  # "(Edge Placement Error, EPE)" → both names
                gz.add(part.strip(), cid)
        if re.fullmatch(r"[a-z]{2,6}", cid):  # acronym-like ids of schema topics: opc, smo, ilt
            gz.add(cid.upper(), cid)
    gz.finalize()
    have = {(e["s"], e["t"]) for e in g.edges if e["layer"] == "reviewed"}
    raw: list[tuple[str, Counter]] = []  # (source node, {target: count}) — ranked below
    for cid, v in vis.items():
        raw.append((cid, gz.scan(v.get("summary", "") + "\n" + v.get("_body", ""))))
    # sections → cards, and indexed entities
    ents: dict[str, dict] = {}
    for p in docs:
        tree = PI.doc_tree(kb, p, meta)
        text_lines = S.read_text(kb, p).splitlines()
        cs = PI.compiled_summary(kb, meta[p]["sha256"]) or {}
        for nd in PI.walk(tree["nodes"]):
            a, b = PI.own_lines(nd)
            sid = f"s:{p}#{nd['id']}"
            g.node(sid, kind="section", title=nd["title"], path=p, node=nd["id"], start=nd["start"], end=nd["end"])
            g.edge(sid, f"d:{p}", "part_of", "provenance")
            raw.append((sid, gz.scan(nd["title"] + "\n" + "\n".join(text_lines[a - 1:b]))))
        for e in cs.get("entities", []) or []:
            name = e.get("name", "")
            k = _key(name)
            if not k:
                continue
            linked = gz.names.get(k) or next((gz.names[_key(a)] for a in e.get("aliases", []) if _key(a) in gz.names), None)
            target = sorted(linked)[0] if linked else None
            if target is None:
                ent = ents.setdefault(k, {"id": "e:" + (slug(name) or k[:30]), "name": name, "type": e.get("type", ""),
                                          "aliases": set(), "docs": set(), "sections": set()})
                ent["aliases"].update(a for a in e.get("aliases", []) if a)
                ent["docs"].add(p)
                target = ent["id"]
                for nid in e.get("nodes", []):
                    ent["sections"].add(f"s:{p}#{nid}")
            else:
                for nid in e.get("nodes", []):
                    g.edge(f"s:{p}#{nid}", target, "mentions", "linked", basis="mention", count=1)
    # rank mentions: a name that occurs everywhere says little (idf); keep the most specific
    # `max_m` targets per source so the linked layer stays informative and bounded (O(sources)).
    df: Counter = Counter(t for _, hits in raw for t in hits)
    n_src = max(1, len(raw))
    for src, hits in raw:
        scored = sorted(((n * math.log(1 + n_src / df[t]), t, n) for t, n in hits.items()
                         if t != src and (src, t) not in have), reverse=True)
        for sc_, t, n in scored[:max_m]:
            g.edge(src, t, "mentions", "linked", basis="mention", count=n, w=round(sc_, 2))
    # entity nodes: deterministic resolution by alias overlap
    merged: dict[str, dict] = {}
    alias_of: dict[str, str] = {}
    for k, ent in sorted(ents.items(), key=lambda kv: -len(kv[1]["docs"])):
        keys = {k} | {_key(a) for a in ent["aliases"]}
        tgt = next((alias_of[x] for x in keys if x in alias_of), None)
        if tgt:
            m = merged[tgt]
            m["aliases"] |= ent["aliases"] | {ent["name"]}
            m["docs"] |= ent["docs"]
            m["sections"] |= ent["sections"]
        else:
            merged[ent["id"]] = ent
            tgt = ent["id"]
        for x in keys:
            alias_of.setdefault(x, tgt)
    egz = Gazetteer()
    for eid, ent in merged.items():
        g.node(eid, kind="entity", title=ent["name"], type=ent["type"] if ent["type"] in onto["entity_types"] else "",
               aliases=sorted(ent["aliases"] - {ent["name"]})[:8], docs=sorted(ent["docs"]))
        for sid in ent["sections"]:
            g.edge(sid, eid, "mentions", "indexed", basis="mention")
        for nm in [ent["name"], *ent["aliases"]]:
            egz.add(nm, eid)
        if ent["type"] and ent["type"] not in onto["entity_types"]:
            g.findings.append({"kind": "untyped_entity", "card": eid, "detail": f"entity type {ent['type']!r} is not in the ontology"})
    egz.finalize()
    for cid, v in vis.items():
        for eid, n in egz.scan(v.get("_body", "")).most_common(max_m):
            g.edge(cid, eid, "mentions", "indexed", basis="mention", count=n)
    with _LOCK:
        if len(_CACHE) > 16:
            _CACHE.clear()
        _CACHE[key] = g
    return g


def explain_path(steps: list[dict]) -> str:
    zh = {"out": "→", "in": "←"}
    return " ".join([steps[0]["from_title"]] + [f"{zh[s['dir']]}{s['rel']}{zh[s['dir']]} {s['to_title']}" for s in steps]) if steps else ""


__all__ = ["Graph", "Gazetteer", "build", "ontology", "explain_path", "STRONG"]
