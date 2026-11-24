"""PageIndex — one reasoning-navigable tree over *all* knowledge, and tree search over it.

The PageIndex idea is: do not embed and similarity-search chunks; give the model a
table of contents with good node summaries and let it *reason* its way down, the way
an expert uses the index of a handbook. We apply that to the whole knowledge base:

    ⌂ root
    ├─ Knowledge (wiki)          topic cards → their child cards → …     (Layer 1, reviewed)
    └─ Sources (documents)       folders → documents → sections → …      (Layer 0, verbatim)
                              (a document's summary card hangs on its document node)

Node summaries
    * structural (free, always):  heading + first sentence (doctree gists)
    * compiled (`lkb index`):     one LLM call per document writes a one-line summary for
      the document and every section, plus keywords; for documents with no usable heading
      structure it proposes *virtual sections* (line ranges) — PageIndex's structure
      inference. Cached by the document's sha256 → incremental, never recomputed for an
      unchanged document; traced like every other LLM call (run kind "index").

Tree search (query time, `navigate`)
    round 1: the tree is rendered top-down within a character budget (breadth first, so
             the upper levels always fit; collapsed nodes show "+N"), together with
             lexical hints (BM25 over cards and sections) and graph neighbours of those
             hints. The model answers {"read": [...], "expand": [...], "done": bool}.
    round k: the requested nodes are opened (their children, with summaries), and the
             model decides again — at most `max_rounds` rounds.
    A small knowledge base fits in round 1 (one call, everything visible); a large one
    costs one or two extra small calls instead of a prompt that grows with the corpus.

No vectors, no chunks: every readable unit is an author-defined section or a card.
"""
from __future__ import annotations

import json
import posixpath
import re
import threading

from . import doctree
from . import sources as S
from .store import KB, atomic_write, now

PROMPT_VERSION = "lkb-index/1"
_LOCK = threading.RLock()

INDEX_SYSTEM = """[[LKB:INDEX]]
You write the navigation summaries of a document's table of contents for a computational-lithography knowledge base.
Readers and an AI navigator will decide what to open *only* from these summaries, so each must say concretely what
the section contains (the specific concepts, methods, numbers, conditions) — not vague phrases like "introduces related content".
Write in the document's language. Each node summary ≤ 60 characters (Chinese) / 25 words. Use only the document.
If the document has fewer than two headings but is long, propose "virtual_sections": contiguous line ranges that
follow its natural topic boundaries, each with a title.
Also list the named entities the document mentions that a reader may look up — of these types:
{types}
Write each name exactly as it appears in the text (it is machine-checked), add aliases that also appear, and the
node ids where it is mentioned. Skip generic words; concepts/methods are not entities.
Return exactly one JSON object in a ```json block:
{{"doc_summary":"≤120 chars: what this document is and what knowledge it holds","keywords":["…"],
 "nodes":{{"n1":"…","n2":"…"}},"virtual_sections":[{{"start":12,"end":80,"title":"…"}}],
 "entities":[{{"name":"Tachyon","type":"tool","aliases":[],"nodes":["n3"]}}]}}
Think briefly."""


def _cache_dir(kb: KB):
    return kb.root / "compiled" / "pageindex"


def _cache_path(kb: KB, sha: str):
    return _cache_dir(kb) / f"{sha[:24]}.json"


_PI_FILES: dict[str, tuple] = {}


def pi_stamp(kb: KB):
    try:
        return _cache_dir(kb).stat().st_mtime_ns
    except FileNotFoundError:
        return None


def _pi_all(kb: KB) -> dict:
    """{sha24: record} of compiled summaries; reloaded only when the directory changes."""
    st = pi_stamp(kb)
    key = str(kb.root)
    ent = _PI_FILES.get(key)
    if ent and ent[0] == st:
        return ent[1]
    recs = {}
    d = _cache_dir(kb)
    if st is not None:
        for f in d.glob("*.json"):
            try:
                recs[f.stem] = json.loads(f.read_text("utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
    _PI_FILES[key] = (st, recs)
    return recs


def compiled_summary(kb: KB, sha: str) -> dict | None:
    return _pi_all(kb).get(sha[:24])


def state_stamp(kb: KB):
    """Changes whenever sources or compiled summaries change (for derived caches)."""
    tp = kb.root / "compiled" / "topics.json"
    ed = kb.root / "compiled" / "entities"
    return (S.meta_stamp(kb), pi_stamp(kb), tp.stat().st_mtime_ns if tp.exists() else 0,
            ed.stat().st_mtime_ns if ed.exists() else 0)


_TREE_CACHE: dict[tuple, dict] = {}


def doc_tree(kb: KB, path: str, meta: dict | None = None) -> dict:
    """The document's tree: structural doctree, enriched with compiled summaries and virtual sections."""
    meta = meta if meta is not None else S.meta_ro(kb)
    sha = meta[path]["sha256"]
    cs = compiled_summary(kb, sha)
    key = (str(kb.root), path, sha, (cs or {}).get("at"))
    with _LOCK:
        if key in _TREE_CACHE:
            return _TREE_CACHE[key]
    text = S.read_text(kb, path)
    base = doctree.build(text, sha)
    tree = json.loads(json.dumps(base))  # never mutate the shared structural cache
    if cs:
        tree["summary"] = cs.get("doc_summary", "")
        tree["keywords"] = cs.get("keywords", [])
        vs = cs.get("virtual_sections") or []
        if vs and _heading_count(tree) < 2:
            lines = text.splitlines()
            nodes = []
            for i, v in enumerate(vs, 1):
                a, b = int(v["start"]), int(v["end"])
                nodes.append({"id": f"v{i}", "title": str(v.get("title", ""))[:80], "level": 1, "start": a, "end": b,
                              "children": [], "virtual": True, "chars": sum(len(x) + 1 for x in lines[a - 1:b]),
                              "gist": doctree._first_sentence(lines[a - 1:b])})
            tree["nodes"] = nodes
        summ = cs.get("nodes") or {}
        for nd in walk(tree["nodes"]):
            if summ.get(nd["id"]):
                nd["summary"] = summ[nd["id"]]
        tree["compiled"] = {"run": cs.get("run"), "model": cs.get("model"), "at": cs.get("at")}
    with _LOCK:
        _TREE_CACHE[key] = tree
    return tree


def _heading_count(tree: dict) -> int:
    return sum(1 for nd in walk(tree["nodes"]) if not nd.get("virtual") and nd["id"] != "n0")


def walk(nodes):
    stack = list(reversed(nodes))
    while stack:
        nd = stack.pop()
        yield nd
        stack.extend(reversed(nd.get("children", [])))


def find(tree: dict, node_id: str) -> dict | None:
    for nd in walk(tree["nodes"]):
        if nd["id"] == node_id:
            return nd
    return None


def own_lines(nd: dict) -> tuple[int, int]:
    """Lines of the node's own text (before its first child)."""
    end = nd["children"][0]["start"] - 1 if nd.get("children") else nd["end"]
    return nd["start"], max(nd["start"], end)


def parse_obj(text: str) -> dict:
    m = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.S)
    raw = m.group(1) if m else text[text.find("{"): text.rfind("}") + 1]
    data = json.loads(raw)
    if isinstance(data, str):
        data = json.loads(data)
    if not isinstance(data, dict):
        raise ValueError("expected a JSON object")
    return data


# ---- compile node summaries (LLM, incremental) -----------------------------------------
def _validate(raw: dict, tree: dict, n_lines: int, text: str = "", types: dict | None = None) -> tuple[dict, list[str]]:
    from .graph import _key
    findings = []
    ids = {nd["id"] for nd in walk(tree["nodes"])}
    if isinstance(raw.get("nodes"), dict):  # observed: top-level keys nested inside "nodes" — lift them
        for k in ("virtual_sections", "entities", "doc_summary", "keywords"):
            if k in raw["nodes"] and k not in raw:
                raw[k] = raw["nodes"].pop(k)
    nodes = {}
    for k, v in (raw.get("nodes") or {}).items() if isinstance(raw.get("nodes"), dict) else []:
        if k in ids and isinstance(v, str) and v.strip():
            nodes[k] = v.strip()[:160]
        elif k not in ids:
            findings.append(f"unknown node {k}")
    vs, last = [], 0
    for v in raw.get("virtual_sections") or []:
        try:
            a, b = int(v["start"]), int(v["end"])
        except (KeyError, TypeError, ValueError):
            findings.append("bad virtual section")
            continue
        if a > last and a <= b <= n_lines:
            vs.append({"start": a, "end": b, "title": str(v.get("title", ""))[:80]})
            last = b
        else:
            findings.append(f"virtual section {a}-{b} out of order/range")
    missing = [i for i in ids if i not in nodes and i != "n0"]
    if missing:
        findings.append(f"{len(missing)} nodes without summary")
    kw = [str(x)[:40] for x in raw.get("keywords") or [] if isinstance(x, (str, int, float))][:12]
    hay = _key(text)
    ents, dropped = [], 0
    for e in raw.get("entities") or []:
        if not isinstance(e, dict) or not str(e.get("name", "")).strip():
            continue
        name = str(e["name"]).strip()[:80]
        if _key(name) not in hay:  # verbatim check: no invented entities
            dropped += 1
            continue
        al = [str(a).strip()[:80] for a in e.get("aliases") or [] if str(a).strip() and _key(str(a)) in hay][:6]
        typ = str(e.get("type", "")).strip()
        ents.append({"name": name, "type": typ if not types or typ in types else "", "aliases": al,
                     "nodes": [str(n) for n in e.get("nodes") or [] if str(n) in ids][:20]})
    if dropped:
        findings.append(f"{dropped} entities not found verbatim — dropped")
    return {"doc_summary": str(raw.get("doc_summary", ""))[:240], "keywords": kw, "nodes": nodes,
            "virtual_sections": vs, "entities": ents}, findings


def _index_prompt(path: str, title: str, text: str, tree: dict, budget: int) -> str:
    lines = text.splitlines()
    head = f'<doc path="{path}" title="{title}" lines="{len(lines)}">\n# Table of contents\n{doctree.outline(tree, 6)}\n'
    if len(text) <= budget:
        body = "\n".join(f"{i:5d}|{ln}" for i, ln in enumerate(lines, 1))
    else:  # very large: each section's opening lines, so every node can still be summarised
        per = max(400, budget // max(1, sum(1 for _ in walk(tree["nodes"]))))
        parts = []
        for nd in walk(tree["nodes"]):
            a, b = own_lines(nd)
            chunk, size = [], 0
            for i in range(a, b + 1):
                ln = lines[i - 1]
                if size + len(ln) > per:
                    chunk.append(f"{i:5d}|…")
                    break
                chunk.append(f"{i:5d}|{ln}")
                size += len(ln)
            parts.append("\n".join(chunk))
        body = "\n".join(parts)
    return head + "# Text\n" + body + "\n</doc>"


class Indexer:
    """`lkb index` — compile PageIndex node summaries for documents whose content changed."""

    def __init__(self, kb: KB, compiler):
        self.kb, self.comp = kb, compiler

    def pending(self, force: bool = False) -> list[str]:
        meta = S.meta_ro(self.kb)
        out = []
        for p in S.list_md_by_policy(self.kb, "compile", "reference"):
            if force or compiled_summary(self.kb, meta[p]["sha256"]) is None:
                out.append(p)
        return out

    def run(self, actor: str, cfg: dict, paths: list[str] | None = None, force: bool = False) -> dict:
        from .compiler import new_run_id
        meta = S.load_meta(self.kb)
        todo = paths if paths else self.pending(force)
        report = {"documents": len(todo), "indexed": [], "failed": [], "cost_usd": 0.0, "runs": []}
        budget = int(self.kb.config.get("index", {}).get("max_doc_chars", 60000))
        for p in todo:
            if p not in meta:
                report["failed"].append({"path": p, "error": "unknown document"})
                continue
            sha = meta[p]["sha256"]
            if not force and compiled_summary(self.kb, sha):
                continue
            rid = new_run_id()
            run = {"id": rid, "kind": "index", "by": actor, "started": now(), "status": "running",
                   "backend": cfg["backend"], "prompt_version": PROMPT_VERSION, "sources": [p],
                   "source_shas": {p: sha}, "timeline": []}
            try:
                text = S.read_text(self.kb, p)
                tree = doctree.build(text, sha)
                title = S.doc_titles(self.kb, [p]).get(p, p)
                user = _index_prompt(p, title, text, tree, budget)
                from .graph import ontology
                types = ontology(self.kb)["entity_types"]
                system = INDEX_SYSTEM.format(types="\n".join(f"  - {k}: {v}" for k, v in types.items()))
                res = self.comp.llm_step(run, cfg, system, user, prefix="idx-")
                data, findings = _validate(parse_obj(res.text), tree, len(text.splitlines()), text, types)
                rec = {"path": p, "sha": sha, "run": rid, "model": res.model, "prompt_version": PROMPT_VERSION,
                       "at": now(), **data, "findings": findings}
                atomic_write(_cache_path(self.kb, sha), json.dumps(rec, ensure_ascii=False, indent=1))
                run.update(status="done", findings=findings, summarized=len(data["nodes"]))
                report["indexed"].append({"path": p, "nodes": len(data["nodes"]), "virtual": len(data["virtual_sections"]),
                                          "entities": len(data["entities"]),
                                          "findings": findings})
            except Exception as e:  # noqa: BLE001 — one bad document never stops the batch
                run.update(status="failed", error=f"{type(e).__name__}: {e}")
                report["failed"].append({"path": p, "error": run["error"]})
            run["finished"] = now()
            self.comp._save_run(run)
            report["runs"].append(rid)
            report["cost_usd"] += run.get("cost_usd", 0) or 0
        report["cost_usd"] = round(report["cost_usd"], 6)
        self.kb.event(actor, "index.run", "", documents=len(todo), indexed=len(report["indexed"]),
                      failed=len(report["failed"]), cost_usd=report["cost_usd"])
        return report

    def status(self) -> dict:
        meta = S.load_meta(self.kb)
        docs = S.list_md_by_policy(self.kb, "compile", "reference")
        done = [p for p in docs if compiled_summary(self.kb, meta[p]["sha256"])]
        return {"documents": len(docs), "compiled": len(done), "pending": sorted(set(docs) - set(done))}


# ---- the unified knowledge tree -----------------------------------------------------------
class KnowledgeTree:
    """Nodes: 'k' (wiki root), card ids, 'd' (documents root), 'f:<folder>', 'd:<path>', 's:<path>#<node>'.
    Each node: {id, kind, title, summary, size, children, parent, ...}."""

    def __init__(self, kb: KB, cards, readers: bool, conditions: dict | None = None):
        self.kb, self.cards, self.readers = kb, cards, readers
        self.nodes: dict[str, dict] = {}
        self.meta = S.meta_ro(kb)
        self._build(conditions)

    def _add(self, nid, kind, title, summary="", parent=None, **kw):
        nd = {"id": nid, "kind": kind, "title": title, "summary": summary, "children": [], "parent": parent, **kw}
        self.nodes[nid] = nd
        if parent is not None:
            self.nodes[parent]["children"].append(nid)
        return nd

    def _build(self, conditions):
        from .cards import is_public
        from . import facets as F
        self._add("k", "root", "Knowledge (reviewed knowledge cards)", "knowledge cards organised by topic")
        idx = self.cards.index()
        vis = {}
        for cid, m in idx.items():
            if m.get("lifecycle", "active") != "active" or m.get("status") == "rejected":
                continue
            v = (m.get("_pub") if is_public(m) else None) if self.readers else m
            if v is None:
                continue
            if conditions and F.applies(F.ok(v.get("conditions", [])), conditions) == "no":
                continue
            vis[cid] = v
        self.visible_cards = vis
        summaries_by_doc: dict[str, str] = {}
        kids: dict[str, list] = {}
        for cid, v in vis.items():
            srcs = [x["path"] if isinstance(x, dict) else x for x in v.get("sources", [])]
            if v["type"] == "summary" and len(srcs) == 1:
                summaries_by_doc[srcs[0]] = cid
                continue
            par = v.get("parent") if v.get("parent") in vis and v.get("parent") != cid else ""
            kids.setdefault(par, []).append(v)

        def add_cards(pid, parent_node, seen):
            for v in sorted(kids.get(pid, []), key=lambda x: (x["type"] != "topic", x["title"])):
                if v["id"] in seen:
                    continue
                seen.add(v["id"])
                self._add(v["id"], "card", v["title"], v.get("summary", ""), parent_node, type=v["type"],
                          aliases=v.get("aliases", [])[:4], size=len(v.get("_body", "")))
                add_cards(v["id"], v["id"], seen)

        seen: set = set()
        add_cards("", "k", seen)
        for cid in vis:  # cycles in parent links: still reachable
            if cid not in seen and cid not in summaries_by_doc.values():
                v = vis[cid]
                self._add(cid, "card", v["title"], v.get("summary", ""), "k", type=v["type"], size=len(v.get("_body", "")))
        # documents
        self._add("d", "root", "Sources (original documents, kept verbatim)", "source documents and their sections, by folder")
        for p in S.list_md_by_policy(self.kb, "compile", "reference"):
            folder = posixpath.dirname(p)
            parent = "d"
            acc = ""
            for part in folder.split("/") if folder else []:
                acc = f"{acc}/{part}" if acc else part
                fid = f"f:{acc}"
                if fid not in self.nodes:
                    self._add(fid, "folder", part, "", parent)
                parent = fid
            tree = doc_tree(self.kb, p, self.meta)
            title = tree.get("title") or posixpath.basename(p)
            sc = summaries_by_doc.get(p)
            summ = tree.get("summary") or (vis[sc].get("summary", "") if sc else "")
            did = f"d:{p}"
            self._add(did, "doc", title, summ, parent, path=p, lines=tree["lines"], size=tree["chars"],
                      keywords=tree.get("keywords", []), summary_card=sc)
            if sc:
                self._add(sc, "card", vis[sc]["title"], vis[sc].get("summary", ""), did, type="summary",
                          size=len(vis[sc].get("_body", "")))

            def add_secs(nodes, parent_id):
                for nd in nodes:
                    sid = f"s:{p}#{nd['id']}"
                    self._add(sid, "section", nd["title"], nd.get("summary") or nd.get("gist", ""), parent_id,
                              path=p, node=nd["id"], start=nd["start"], end=nd["end"], size=nd.get("chars", 0))
                    add_secs(nd.get("children", []), sid)

            add_secs(tree["nodes"], did)
        self._add_topics()
        for nd in self.nodes.values():  # folder summaries: what is inside (structural)
            if nd["kind"] == "folder":
                docs = [self.nodes[c]["title"] for c in nd["children"] if self.nodes[c]["kind"] == "doc"]
                nd["summary"] = f"{len(docs)} document(s): " + ", ".join(docs[:6]) + ("…" if len(docs) > 6 else "")

    def _add_topics(self):
        """Themes root: topic → subtopic → references to member sections (representatives first)."""
        from .topics import load
        t = load(self.kb)
        if not t or not t.get("topics"):
            return
        self._add("t", "root", "Themes (topics across documents)", "what the sections are about, grouped across documents")
        flat = t["topics"]
        for x in flat:
            if x["parent"] is None:
                self._add_topic(x, "t", flat)

    def _add_topic(self, x, parent, flat):
        tid = f"t:{x['id']}"
        if tid in self.nodes:
            return
        self._add(tid, "topic", x["title"], x.get("summary", ""), parent, members=len(x["members"]))
        for c in flat:
            if c["parent"] == x["id"]:
                self._add_topic(c, tid, flat)
        own = x.get("own", x["members"]) if any(c["parent"] == x["id"] for c in flat) else x["members"]
        rep = [m for m in x.get("representative", []) if m in own]
        for m in rep + [m for m in own if m not in rep]:
            if m in self.nodes:
                sec = self.nodes[m]
                self._add(f"r:{x['id']}#{m}", "ref", sec["title"], sec["summary"], tid, target=m,
                          representative=m in rep, path=sec["path"], node=sec["node"], start=sec["start"], end=sec["end"])

    # -- rendering for the navigator --------------------------------------------------
    def descendants(self, nid: str) -> int:
        """Number of nodes below `nid` (memoised; the tree is immutable once built)."""
        memo = self.__dict__.setdefault("_desc", {})
        if nid in memo:
            return memo[nid]
        order, stack = [], [nid]
        while stack:  # iterative post-order fill
            c = stack.pop()
            order.append(c)
            stack.extend(self.nodes[c]["children"])
        for c in reversed(order):
            if c not in memo:
                memo[c] = sum(1 + memo[k] for k in self.nodes[c]["children"])
        return memo[nid]

    def line(self, nid: str, handle: str, depth: int, collapsed: int = 0) -> str:
        nd = self.nodes[nid]
        tag = {"card": f"[{nd.get('type', 'card')}]", "doc": "[doc]", "section": "[§]", "folder": "[dir]",
               "root": "", "topic": "[theme]", "ref": "[§★]" if nd.get("representative") else "[§]"}[nd["kind"]]
        extra = f" (L{nd['start']}-{nd['end']})" if nd["kind"] in ("section", "ref") else ""
        if nd["kind"] == "ref":
            doc = self.nodes.get(f"d:{nd['path']}", {}).get("title", nd["path"])
            extra = f" — in “{doc[:40]}”" + extra
        al = f" aka {', '.join(nd['aliases'])}" if nd.get("aliases") else ""
        s = f" — {nd['summary'][:150]}" if nd.get("summary") else ""
        more = f"  [+{collapsed}]" if collapsed else ""
        return f"{'  ' * depth}{handle} {tag} {nd['title']}{al}{extra}{s}{more}"

    def render(self, roots: list[str], handles: "Handles", budget: int, depth0: int = 0) -> tuple[str, set]:
        """Breadth-first within `budget` characters. Returns (text, set of nodes shown with children hidden)."""
        shown: dict[str, int] = {}
        order: list[str] = []
        used = 0
        frontier = [(r, depth0) for r in roots]
        full = False
        while frontier and not full:
            nxt = []
            for nid, d in frontier:
                ln = len(self.line(nid, handles.get(nid), d)) + 1
                if used + ln > budget and order:
                    full = True  # the rest of this level stays collapsed under its parent ("+N")
                    break
                shown[nid] = d
                order.append(nid)
                used += ln
                nxt.extend((c, d + 1) for c in self.nodes[nid]["children"])
            frontier = nxt
            if used >= budget:
                break
        collapsed = set()
        out = []

        def emit(nid):
            hidden = [c for c in self.nodes[nid]["children"] if c not in shown]
            n_hidden = sum(1 + self.descendants(c) for c in hidden)
            if hidden:
                collapsed.add(nid)
            out.append(self.line(nid, handles.get(nid), shown[nid], n_hidden))
            for c in self.nodes[nid]["children"]:
                if c in shown:
                    emit(c)

        for r in roots:
            if r in shown:
                emit(r)
        return "\n".join(out), collapsed

    def roots(self) -> list[str]:
        return [r for r in ("k", "t", "d") if r in self.nodes]

    def path_to(self, nid: str) -> list[str]:
        out = []
        while nid is not None:
            out.append(nid)
            nid = self.nodes[nid]["parent"]
        return out[::-1]


_KT_CACHE: dict[tuple, "KnowledgeTree"] = {}


def knowledge_tree(kb: KB, cards, readers: bool, conditions: dict | None = None) -> "KnowledgeTree":
    """Cached KnowledgeTree (immutable once built) keyed by everything it depends on."""
    cards.index()
    key = (str(kb.root), id(cards), cards.generation, state_stamp(kb), readers,
           json.dumps(conditions or {}, sort_keys=True, ensure_ascii=False))
    with _LOCK:
        t = _KT_CACHE.get(key)
    if t is None:
        t = KnowledgeTree(kb, cards, readers, conditions)
        with _LOCK:
            if len(_KT_CACHE) > 32:
                _KT_CACHE.clear()
            _KT_CACHE[key] = t
    return t


class Handles:
    """Short, stable per-run names for nodes (doc paths can be long and full of punctuation)."""

    def __init__(self, tree: KnowledgeTree):
        self.tree, self.fwd, self.rev = tree, {}, {}
        self._docs = 0

    def get(self, nid: str) -> str:
        if nid in self.fwd:
            return self.fwd[nid]
        nd = self.tree.nodes[nid]
        if nd["kind"] == "ref":  # a theme's reference to a section reads as that section
            h = self.get(nd["target"])
            self.fwd[nid] = h
            return h
        if nd["kind"] in ("card", "root"):
            h = nid
        elif nd["kind"] == "topic":
            h = "th" + str(sum(1 for v in self.fwd if v.startswith("t:")) + 1)
        elif nd["kind"] == "folder":
            h = "dir" + str(sum(1 for v in self.fwd if v.startswith("f:")) + 1)
        elif nd["kind"] == "doc":
            self._docs += 1
            h = f"doc{self._docs}"
        else:  # section: <doc handle>/<node id>
            h = self.get(f"d:{nd['path']}") + "/" + nd["node"]
        self.fwd[nid], self.rev[h] = h, nid
        return h

    def resolve(self, h: str) -> str | None:
        h = str(h).strip()
        if h in self.rev:
            return self.rev[h]
        if h in self.tree.nodes and self.tree.nodes[h]["kind"] == "card":
            return h
        return None


NAV_SYSTEM = """[[LKB:NAVIGATE]]
You are the navigator of LithoKB, a curated computational-lithography knowledge base. You do not answer yet.
You see a tree of the knowledge base: Knowledge (reviewed knowledge cards under topics), Themes (what the source
sections are about, grouped across documents; ★ marks a theme's representative sections) and Sources (original
documents → sections, with line ranges). Every line starts with a handle, then a tag, a title and a summary. "[+N]" means N
nodes below it are not shown yet — ask to "expand" it to see them. <hints> lists nodes that match the question's
words or are graph neighbours of such nodes; they are suggestions, not answers.
Reason like an expert using the index of a handbook: follow topics, aliases, prerequisites and contrasts. Prefer
knowledge cards; add document sections when exact numbers, conditions or details matter or when no card fits.
For BROAD questions (what kinds / which types / overview / what else / conflicts / comparisons) cover breadth: pick
the relevant themes and read representative (★) sections from several of them, instead of many sections that make
the same point.
Return exactly one JSON object in a ```json block:
{"reasoning":"short reading plan","read":["handle", ...],"expand":["handle", ...],"done":true|false}
- "read": cards or sections (or a whole small document) to read in full. At most %d cards and %d sections in total.
- "expand": collapsed nodes to open first; set "done": false to see them. Set "done": true when your reading list
  is complete. Only use handles that appear above. Think briefly; do not draft the answer."""


__all__ = ["Indexer", "KnowledgeTree", "Handles", "NAV_SYSTEM", "doc_tree", "find", "own_lines",
           "compiled_summary", "walk"]


# ---- lexical index over sections (author-defined sections, not chunks) ----------------------
_SEC_IDX: dict[str, tuple] = {}


def section_index(kb: KB):
    """BM25 over every section's own text + heading path + summary, incremental per document."""
    from .textindex import BM25
    stamp = state_stamp(kb)
    with _LOCK:
        ent = _SEC_IDX.get(str(kb.root))
        if ent and ent[2] == stamp:
            return ent[0]
        meta = S.meta_ro(kb)
        docs = S.list_md_by_policy(kb, "compile", "reference")
        bm, sigs = (ent[0], ent[1]) if ent else (BM25(), {})
        keep = set()
        for p in docs:
            sha = meta[p]["sha256"]
            cs = compiled_summary(kb, sha)
            sig = (sha, (cs or {}).get("at"))
            tree = doc_tree(kb, p, meta)
            keys = []
            fresh = sigs.get(p) != sig
            lines = S.read_text(kb, p).splitlines() if fresh else None

            def visit(nodes, trail):
                for nd in nodes:
                    k = f"s:{p}#{nd['id']}"
                    keys.append(k)
                    if fresh:
                        a, b = own_lines(nd)
                        bm.put(k, sig, [(tree.get("title", "") + " " + " ".join(trail + [nd["title"]]), 4),
                                        (nd.get("summary", ""), 2), ("\n".join(lines[a - 1:b]), 1)],
                               payload={"path": p, "node": nd["id"]})
                    visit(nd.get("children", []), trail + [nd["title"]])

            visit(tree["nodes"], [])
            sigs[p] = sig
            keep.update(keys)
        bm.sync(keep)
        _SEC_IDX[str(kb.root)] = (bm, sigs, stamp)
        return bm
