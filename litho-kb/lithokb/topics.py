"""Topic graph — what the passages are about, across documents (no vectors).

Topics answer *broad* questions ("what else…", "what kinds of…", "overview of…"): instead of
reading many near-identical passages about one point, a query fans out over themes and reads
the representative sections of each. Topics are also the evidence base from which the
ontology is proposed (ontology.py).

Build (`lkb topics build`, LangGraph GENERATE flow, one LLM call per input chunk + one merge call
when the corpus does not fit one call):
  input   every section of every compiled document as one line:
          `D3.n5 | “Document title” › section heading — PageIndex summary`
  output  a two-level hierarchy: topics → subtopics, each with member sections (a section may
          belong to two themes) and 2–4 representative sections ("centroids" without vectors);
          navigation / boilerplate sections stay unassigned.
  checks  handles must exist; representatives must be members; empty topics are dropped;
          coverage (assigned / content sections) is recorded.

Stored as compiled/topics.json (derived index, like PageIndex summaries: navigation aid, not
reviewed knowledge), keyed by the state of its inputs — `status()` says when it is stale.
"""
from __future__ import annotations

import hashlib
import json

from . import pageindex as PI
from . import sources as S
from .cards import slug
from .flows import generate
from .store import KB, atomic_write, now

PROMPT_VERSION = "lkb-topics/1"

SYSTEM = """[[LKB:TOPICS]]
You organise the sections of a document collection into a two-level topic hierarchy: what the passages are
about. Each input line is `HANDLE | "Document" > section heading - summary`.
Rules:
- 6 to 14 topics; a topic may have up to 5 subtopics. Topics are themes that recur across documents, not
  document titles. Use the documents' language for titles; summaries <= 80 characters, concrete.
- Every content section belongs to at least one leaf (a subtopic, or a topic without subtopics); a section
  may belong to two leaves when it clearly discusses both. Navigation, table-of-contents, boilerplate and
  promotional sections go to "unassigned".
- For each leaf give 2-4 "representative" handles: the sections that best capture the theme.
- Only use handles from the input.
Return exactly one JSON object in a ```json block:
{"topics":[{"id":"kebab-case","title":"...","summary":"...",
  "subtopics":[{"id":"kebab-case","title":"...","summary":"...","sections":["D1.n2"],"representative":["D1.n2"]}],
  "sections":[],"representative":[]}],
 "unassigned":["D9.n1"],"notes":"..."}
Think briefly."""

MERGE_SYSTEM = """[[LKB:TOPICS]]
You merge topic hierarchies that were built separately for parts of one document collection into one
hierarchy of 6 to 14 topics (each with up to 5 subtopics). Input: the partial hierarchies with their leaf ids.
Map every input leaf id to exactly one leaf of the merged hierarchy.
Return exactly one JSON object in a ```json block:
{"topics":[{"id":"kebab-case","title":"...","summary":"...","subtopics":[{"id":"kebab-case","title":"...","summary":"..."}]}],
 "mapping":{"input-leaf-id":"merged-leaf-id"}}"""


def _path(kb: KB):
    return kb.root / "compiled" / "topics.json"


def load(kb: KB) -> dict | None:
    p = _path(kb)
    return json.loads(p.read_text("utf-8")) if p.exists() else None


def _inputs(kb: KB) -> tuple[list[str], dict[str, str], str]:
    """Section lines, handle → section node id ("s:<path>#<node>"), and a hash of the input state."""
    meta = S.meta_ro(kb)
    lines, hmap, h = [], {}, hashlib.sha256()
    for i, p in enumerate(S.list_md_by_policy(kb, "compile"), 1):
        tree = PI.doc_tree(kb, p, meta)
        title = tree.get("title") or p
        h.update(f"{p}:{meta[p]['sha256']}:{(tree.get('compiled') or {}).get('at')}".encode())

        def walk(nodes, trail):
            for nd in nodes:
                hd = f"D{i}.{nd['id']}"
                hmap[hd] = f"s:{p}#{nd['id']}"
                summ = (nd.get("summary") or nd.get("gist") or "")[:110]
                lines.append(f"{hd} | \"{title[:40]}\" > {' > '.join(trail + [nd['title']])[:80]} - {summ}")
                walk(nd.get("children", []), trail + [nd["title"]])

        walk(tree["nodes"], [])
    return lines, hmap, h.hexdigest()[:16]


def status(kb: KB) -> dict:
    t = load(kb)
    _, hmap, state = _inputs(kb)
    return {"built": bool(t), "stale": bool(t) and t.get("state") != state, "sections": len(hmap),
            "topics": len([x for x in (t or {}).get("topics", []) if not x.get("parent")]),
            "subtopics": len([x for x in (t or {}).get("topics", []) if x.get("parent")]),
            "coverage": (t or {}).get("coverage"), "at": (t or {}).get("at"), "run": (t or {}).get("run")}


def _flatten(raw: dict, hmap: dict, findings: list) -> list[dict]:
    out, ids = [], set()

    def uid(x):
        b = slug(str(x)) or "topic"
        u, n = b, 2
        while u in ids:
            u, n = f"{b}-{n}", n + 1
        ids.add(u)
        return u

    def members(lst):
        good = [hmap[h] for h in (lst or []) if isinstance(h, str) and h in hmap]
        bad = [h for h in (lst or []) if not (isinstance(h, str) and h in hmap)]
        if bad:
            findings.append(f"{len(bad)} unknown section handle(s) dropped")
        return list(dict.fromkeys(good))

    for t in raw.get("topics", []) or []:
        if not isinstance(t, dict) or not str(t.get("title", "")).strip():
            continue
        tid = uid(t.get("id") or t["title"])
        subs = []
        for st in t.get("subtopics", []) or []:
            if not isinstance(st, dict):
                continue
            mem = members(st.get("sections"))
            if not mem:
                continue
            rep = [x for x in members(st.get("representative")) if x in mem][:4] or mem[:3]
            subs.append({"id": uid(st.get("id") or st.get("title")), "title": str(st.get("title", ""))[:80],
                         "summary": str(st.get("summary", ""))[:160], "parent": tid, "members": mem,
                         "representative": rep})
        own = members(t.get("sections"))
        if not subs and not own:
            continue
        rep = [x for x in members(t.get("representative")) if x in own][:4] or own[:3]
        allm = list(dict.fromkeys(own + [m for s_ in subs for m in s_["members"]]))
        out.append({"id": tid, "title": str(t["title"])[:80], "summary": str(t.get("summary", ""))[:160], "parent": None,
                    "members": allm, "own": own, "representative": rep or [s_["representative"][0] for s_ in subs][:4]})
        out.extend(subs)
    return out


def _check(text_res, hmap):
    from .pageindex import parse_obj
    d = parse_obj(text_res.text)
    if not isinstance(d.get("topics"), list) or not d["topics"]:
        raise ValueError("no 'topics' list")
    findings: list = []
    flat = _flatten(d, hmap, findings)
    if len([t for t in flat if not t["parent"]]) < 2:
        raise ValueError("fewer than two usable topics")
    return {"flat": flat, "raw": d, "findings": findings}


class TopicBuilder:
    def __init__(self, kb: KB, comp):
        self.kb, self.comp = kb, comp

    def build(self, actor: str, cfg: dict) -> dict:
        from .compiler import new_run_id
        lines, hmap, state = _inputs(self.kb)
        if not lines:
            raise ValueError("no compiled documents to build topics from")
        budget = int(self.kb.config.get("topics", {}).get("max_input_chars", 60000))
        chunks, cur, size = [], [], 0
        for ln in lines:
            if cur and size + len(ln) > budget:
                chunks.append(cur)
                cur, size = [], 0
            cur.append(ln)
            size += len(ln) + 1
        chunks.append(cur)
        rid = new_run_id()
        run = {"id": rid, "kind": "topics", "by": actor, "started": now(), "status": "running", "backend": cfg["backend"],
               "prompt_version": PROMPT_VERSION, "sources": sorted({h.split("#")[0][2:] for h in hmap.values()}),
               "source_shas": {}, "timeline": [], "chunks": len(chunks), "findings": []}
        try:
            parts = []
            for k, ch in enumerate(chunks, 1):
                user = f"# Sections ({len(ch)}){f' — part {k} of {len(chunks)}' if len(chunks) > 1 else ''}\n" + "\n".join(ch)
                res_d, res, _ = generate(comp=self.comp, run=run, cfg=cfg, system=SYSTEM, user=user,
                                         check=lambda r: _check(r, hmap), max_attempts=2,
                                         prefix="" if len(chunks) == 1 else f"part{k}-", graph="topics",
                                         correction=lambda e: f"\n\n# Correction\nYour previous answer was not usable ({e[:160]}). "
                                                              "Return the JSON object exactly as specified, using only input handles.")
                run["findings"] += res_d["findings"]
                parts.append(res_d["flat"])
                run["model"] = res.model
            flat = parts[0] if len(parts) == 1 else self._merge(run, cfg, parts)
            content = set(hmap.values())
            assigned = {m for t in flat for m in t["members"]}
            rec = {"version": PROMPT_VERSION, "run": rid, "model": run.get("model"), "at": now(), "state": state,
                   "coverage": round(len(assigned & content) / max(1, len(content)), 3),
                   "unassigned": sorted(content - assigned), "topics": flat, "findings": run["findings"]}
            atomic_write(_path(self.kb), json.dumps(rec, ensure_ascii=False, indent=1))
            run.update(status="done", topics=len([t for t in flat if not t["parent"]]),
                       subtopics=len([t for t in flat if t["parent"]]), coverage=rec["coverage"])
        except Exception as e:  # noqa: BLE001
            run.update(status="failed", error=f"{type(e).__name__}: {e}")
        run["finished"] = now()
        self.comp._save_run(run)
        self.kb.event(actor, f"topics.build.{run['status']}", rid, topics=run.get("topics"), coverage=run.get("coverage"),
                      error=run.get("error", ""))
        return run

    def _merge(self, run, cfg, parts):
        leaves = {}
        desc = []
        for k, flat in enumerate(parts, 1):
            for t in flat:
                is_leaf = t["parent"] is not None or not any(x["parent"] == t["id"] for x in flat)
                if is_leaf:
                    lid = f"p{k}-{t['id']}"
                    leaves[lid] = t
                    desc.append(f"{lid} | {t['title']} - {t['summary']}")
        from .pageindex import parse_obj

        def check(res):
            d = parse_obj(res.text)
            if not isinstance(d.get("mapping"), dict) or not d.get("topics"):
                raise ValueError("need 'topics' and 'mapping'")
            return d

        d, _, _ = generate(comp=self.comp, run=run, cfg=cfg, system=MERGE_SYSTEM, user="# Partial leaves\n" + "\n".join(desc),
                           check=check, max_attempts=2, prefix="merge-", graph="topics",
                           correction=lambda e: f"\n\n# Correction\n({e[:160]}) Return topics and a complete mapping.")
        merged = {"topics": []}
        by_leaf: dict[str, list] = {}
        for lid, target in d["mapping"].items():
            if lid in leaves:
                by_leaf.setdefault(str(target), []).append(leaves[lid])
        for t in d["topics"]:
            subs = []
            for st in t.get("subtopics", []) or []:
                src = by_leaf.get(st.get("id"), [])
                subs.append({**st, "sections": [], "representative": [], "_src": src})
            merged["topics"].append({**t, "subtopics": subs, "_src": by_leaf.get(t.get("id"), [])})
        # rebuild flat directly from the source leaves' resolved members
        out, ids = [], set()
        for t in merged["topics"]:
            tid = slug(t.get("id") or t.get("title")) or f"topic-{len(ids)}"
            ids.add(tid)
            subs = []
            for st in t["subtopics"]:
                mem = list(dict.fromkeys(m for s_ in st["_src"] for m in s_["members"]))
                if mem:
                    rep = list(dict.fromkeys(r for s_ in st["_src"] for r in s_["representative"]))[:4]
                    subs.append({"id": slug(st.get("id") or st.get("title")), "title": st.get("title", ""),
                                 "summary": st.get("summary", ""), "parent": tid, "members": mem, "representative": rep})
            own = list(dict.fromkeys(m for s_ in t["_src"] for m in s_["members"]))
            if subs or own:
                allm = list(dict.fromkeys(own + [m for s_ in subs for m in s_["members"]]))
                out.append({"id": tid, "title": t.get("title", ""), "summary": t.get("summary", ""), "parent": None,
                            "members": allm, "own": own,
                            "representative": (list(dict.fromkeys(r for s_ in t["_src"] for r in s_["representative"]))
                                               or [s_["representative"][0] for s_ in subs if s_["representative"]])[:4]})
                out.extend(subs)
        return out


def leaf_topics(t: dict) -> list[dict]:
    flat = t.get("topics", [])
    return [x for x in flat if x["parent"] or not any(y["parent"] == x["id"] for y in flat)]


__all__ = ["TopicBuilder", "load", "status", "leaf_topics", "SYSTEM", "PROMPT_VERSION"]
