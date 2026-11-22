"""The wiki — every page a navigation hub; topic pages that synthesise their children.

LLM-Wiki's point is that knowledge lives as an interlinked, LLM-maintained wiki that
compounds, not as isolated answers. Our cards are the wiki's pages; this module adds
what makes them a *wiki*:

  page(id)       a card assembled with everything around it — breadcrumbs (topic path),
                 sub-pages, typed relations both ways (reviewed), "also mentioned in"
                 (deterministic entity linking), the source sections that discuss it,
                 entities it names, open issues. Deterministic, always current.
  entity(id)     entity pages for named things that are not concepts (tools, equipment,
                 organisations …): where they appear, in documents and in cards.
  home()         the wiki's entry: topic tree, most central pages (PageRank), recently
                 published, hub gaps.
  hubs           LLM-written topic overviews synthesised from the topic's *published*
                 children (op "hub"). Mechanically checked — every [[link]] must exist and
                 every number must occur in a child — then reviewed like any revision.
  export         a static Markdown wiki (compiled/wiki/) for git, grep and agents.
"""
from __future__ import annotations

import json
import re
import traceback

from . import graph as G
from . import sources as S
from .cards import WIKILINK_RE, Cards, is_public, slug
from .compiler import Compiler, new_run_id
from .flows import generate
from .store import KB, atomic_write, now

PROMPT_VERSION = "lkb-hub/1"

HUB_SYSTEM = """[[LKB:HUB]]
You write the overview page of one topic in a computational-lithography wiki. You get the topic card and its
published sub-pages (title, summary, key facts, conditions). Write a compact overview (Markdown, 150–500 words/characters):
1) one-sentence definition of the topic; 2) how the sub-pages fit together (a short structured map: groups,
order to read, how they relate / differ); 3) when which applies (conditions) if the sub-pages say so.
Link every sub-page you mention as [[page-id]]. Use ONLY what the sub-pages say — numbers must be copied from them;
no new facts. Do not repeat each sub-page's full content; this page is a map, not a copy.
Return exactly one JSON object in a ```json block: {"summary":"one line","body_md":"…"}"""


STUB_MARKS = ("主题来自编译规范", "Topic from the SCHEMA.md topic skeleton")  # legacy Chinese + current stub text


def has_overview(v: dict) -> bool:
    """A topic page has an overview when its body is more than the schema stub."""
    body = (v.get("_body") or "").strip()
    return len(body) > 40 and not any(m in body for m in STUB_MARKS)


def _view(cards: Cards, cid: str, readers: bool):
    m = cards.index().get(cid)
    if m is None:
        return None
    return (m.get("_pub") if is_public(m) else None) if readers else m


class Wiki:
    def __init__(self, kb: KB, cards: Cards):
        self.kb, self.cards = kb, cards

    def graph(self, readers: bool) -> G.Graph:
        return G.build(self.kb, self.cards, readers)

    # ---- pages ----------------------------------------------------------------------------
    def page(self, cid: str, readers: bool) -> dict | None:
        v = _view(self.cards, cid, readers)
        if v is None:
            return None
        g = self.graph(readers)
        idx = self.cards.index()
        crumbs, cur, seen = [], v.get("parent"), {cid}
        while cur and cur not in seen:
            pv = _view(self.cards, cur, readers)
            if pv is None:
                break
            crumbs.append({"id": cur, "title": pv["title"]})
            seen.add(cur)
            cur = pv.get("parent")
        crumbs.reverse()
        children = []
        for e in g.inc.get(cid, []):  # graph adjacency: O(degree), not O(cards)
            if e["rel"] != "subtopic_of" or any(c["id"] == e["s"] for c in children):
                continue
            ov = _view(self.cards, e["s"], readers)
            if ov is not None:
                children.append({"id": e["s"], "title": ov["title"], "type": ov["type"], "summary": ov.get("summary", ""),
                                 "conditions": [f"{c['dim']}={c['value']}" for c in ov.get("conditions", []) if c.get("supported", True)]})
        children.sort(key=lambda c: (c["type"] != "topic", c["title"]))
        rel_out, rel_in, mentioned_by, mentions, sections, entities = [], [], [], [], [], []
        for e in g.out.get(cid, []):
            t = g.nodes[e["t"]]
            if e["layer"] == "reviewed" and e["rel"] not in ("subtopic_of", "links_to"):
                rel_out.append({"rel": e["rel"], "id": e["t"], "title": t.get("title"), "basis": e.get("basis")})
            elif e["layer"] == "linked" and t.get("kind") == "card":
                mentions.append({"id": e["t"], "title": t.get("title"), "count": e.get("count", 1)})
            elif t.get("kind") == "entity":
                entities.append({"id": e["t"], "title": t.get("title"), "type": t.get("type")})
        for e in g.inc.get(cid, []):
            s = g.nodes[e["s"]]
            if e["layer"] == "reviewed" and e["rel"] not in ("subtopic_of", "links_to") and s.get("kind") == "card":
                rel_in.append({"rel": e["rel"], "id": e["s"], "title": s.get("title"), "basis": e.get("basis")})
            elif e["layer"] == "linked" and s.get("kind") == "card":
                mentioned_by.append({"id": e["s"], "title": s.get("title"), "count": e.get("count", 1)})
            elif e["layer"] == "linked" and s.get("kind") == "section":
                sections.append({"path": s["path"], "node": s["node"], "title": s["title"], "start": s["start"],
                                 "end": s["end"], "count": e.get("count", 1)})
        own = {x["path"] if isinstance(x, dict) else x for x in v.get("sources", [])}
        ref = {p for p in {s["path"] for s in sections} if S.policy_of(self.kb, p)["policy"] != "compile"}
        sections.sort(key=lambda x: (x["path"] in ref, x["path"] in own, -x["count"]))  # navigation pages last  # other documents first: that is new information
        backlinks = [{"id": e["s"], "title": g.nodes[e["s"]].get("title", e["s"])}
                     for e in g.inc.get(cid, []) if e["rel"] == "links_to"]
        return {"id": cid, "title": v["title"], "type": v["type"], "summary": v.get("summary", ""),
                "body": v.get("_body", ""), "aliases": v.get("aliases", []),
                "conditions": [c for c in v.get("conditions", []) if c.get("supported", True)],
                "evidence": [{k: e.get(k) for k in ("id", "path", "lines", "quote", "check")} for e in v.get("evidence", [])],
                "status": v["status"], "rev": v.get("rev"), "breadcrumbs": crumbs, "children": children,
                "relations_out": rel_out, "relations_in": rel_in,
                "mentions": sorted(mentions, key=lambda x: -x["count"])[:20],
                "mentioned_by": sorted(mentioned_by, key=lambda x: -x["count"])[:20],
                "sections": sections[:20], "entities": entities[:30], "backlinks": backlinks,
                "source_titles": S.doc_titles(self.kb, {s["path"] for s in sections} | own),
                "red_links": [t for t in v.get("_links", []) if t not in idx]}

    def entity(self, eid: str, readers: bool) -> dict | None:
        g = self.graph(readers)
        nd = g.nodes.get(eid)
        if not nd or nd.get("kind") != "entity":
            return None
        secs, cards_ = [], []
        for e in g.inc.get(eid, []):
            s = g.nodes[e["s"]]
            if s.get("kind") == "section":
                secs.append({"path": s["path"], "node": s["node"], "title": s["title"], "start": s["start"], "end": s["end"]})
            elif s.get("kind") == "card":
                cards_.append({"id": e["s"], "title": s["title"], "type": s.get("type"), "count": e.get("count", 1)})
        return {**{k: nd.get(k) for k in ("id", "title", "type", "aliases", "docs")},
                "type_label": G.ontology(self.kb)["entity_types"].get(nd.get("type"), ""),
                "sections": secs, "cards": sorted(cards_, key=lambda x: -x["count"]),
                "source_titles": S.doc_titles(self.kb, {s["path"] for s in secs})}

    def entities(self, readers: bool) -> list[dict]:
        g = self.graph(readers)
        out = []
        for nid, nd in g.nodes.items():
            if nd.get("kind") == "entity":
                out.append({"id": nid, "title": nd["title"], "type": nd.get("type", ""), "docs": len(nd.get("docs", [])),
                            "cards": sum(1 for e in g.inc.get(nid, []) if g.nodes[e["s"]].get("kind") == "card")})
        return sorted(out, key=lambda x: (-(x["docs"] + x["cards"]), x["title"].lower()))

    def home(self, readers: bool) -> dict:
        g = self.graph(readers)
        pr = g.pagerank()
        idx = self.cards.index()
        vis = {cid: v for cid in idx if (v := _view(self.cards, cid, readers)) is not None
               and v.get("lifecycle", "active") == "active" and v.get("status") != "rejected"}
        central = sorted((c for c in pr if vis.get(c, {}).get("type") not in ("summary",)), key=lambda c: -pr[c])[:12]
        recent = sorted((v for v in vis.values() if v.get("published_at") or v.get("updated")),
                        key=lambda v: v.get("published_at") or v.get("updated") or "", reverse=True)[:10]
        topics = [{"id": c, "title": v["title"], "summary": v.get("summary", ""),
                   "children": sum(1 for o in vis.values() if o.get("parent") == c),
                   "has_overview": has_overview(v)}
                  for c, v in sorted(vis.items(), key=lambda kv: kv[1]["title"]) if v["type"] == "topic"]
        return {"pages": len(vis), "topics": topics,
                "central": [{"id": c, "title": vis[c]["title"], "type": vis[c]["type"], "score": round(pr[c] * len(pr), 2)}
                            for c in central if c in vis],
                "recent": [{"id": v["id"], "title": v["title"], "type": v["type"],
                            "at": v.get("published_at") or v.get("updated")} for v in recent],
                "entities": self.entities(readers)[:24], "graph": g.stats(), "hub_gaps": self.hub_gaps(readers)[:10]}

    def hub_gaps(self, readers: bool) -> list[dict]:
        """Topics with ≥3 sub-pages but no overview, and communities of ≥4 cards without a common topic."""
        idx = self.cards.index()
        vis = {cid: v for cid in idx if (v := _view(self.cards, cid, readers)) is not None
               and v.get("lifecycle", "active") == "active"}
        out = []
        for cid, v in vis.items():
            if v["type"] == "topic":
                n = sum(1 for o in vis.values() if o.get("parent") == cid)
                if n >= 2 and not has_overview(v):
                    out.append({"kind": "topic_without_overview", "id": cid, "title": v["title"], "children": n})
        g = self.graph(readers)
        comm = g.communities()
        groups: dict[int, list] = {}
        for c, lab in comm.items():
            if vis.get(c, {}).get("type") not in ("summary", "topic", None):
                groups.setdefault(lab, []).append(c)
        for lab, members in groups.items():
            if len(members) >= 4:
                parents = {vis[m].get("parent") for m in members}
                if len(parents) > 1:
                    out.append({"kind": "community_across_topics", "members": sorted(members)[:12],
                                "parents": sorted(p for p in parents if p),
                                "titles": [vis[m]["title"] for m in sorted(members)[:6]]})
        return out

    # ---- hub overviews (LLM) ------------------------------------------------------------------
    def hub_candidates(self) -> list[str]:
        return [g["id"] for g in self.hub_gaps(readers=True) if g["kind"] == "topic_without_overview"]

    def write_hub(self, user: dict, cid: str, cfg: dict, comp: Compiler) -> dict:
        rid = new_run_id()
        run = {"id": rid, "kind": "hub", "by": user["name"], "started": now(), "status": "running",
               "backend": cfg["backend"], "prompt_version": PROMPT_VERSION, "card": cid, "sources": [],
               "source_shas": {}, "timeline": [], "written": [], "findings": []}
        try:
            head, body = self.cards.load(cid)
            if head["type"] != "topic":
                raise ValueError("hub overviews are written for topic cards only")
            kids = []
            for oid, m in self.cards.index().items():
                v = m.get("_pub") if is_public(m) else None
                if v and v.get("parent") == cid and v.get("lifecycle", "active") == "active":
                    kids.append(v)
            if len(kids) < 2:
                raise ValueError("a topic needs at least two published sub-pages for an overview")
            blocks = []
            for v in sorted(kids, key=lambda x: x["title"]):
                facts = "; ".join(f"{f['name']}={f['value']}{f.get('unit', '')}" for f in v.get("facts", []) if f.get("supported", True))
                conds = "; ".join(f"{c['dim']}={c['value']}" for c in v.get("conditions", []) if c.get("supported", True))
                blocks.append(f'<page id="{v["id"]}" type="{v["type"]}">\n# {v["title"]}\n{v.get("summary", "")}\n'
                              + (f"facts: {facts}\n" if facts else "") + (f"applies under: {conds}\n" if conds else "")
                              + "</page>")
            user_msg = (f'<topic id="{cid}">\n# {head["title"]}\n{head.get("summary", "")}\n{body}\n</topic>\n\n'
                        f"# Published sub-pages ({len(kids)})\n" + "\n".join(blocks))
            from .pageindex import parse_obj

            def check(res):
                d = parse_obj(res.text)
                if not str(d.get("body_md", "")).strip():
                    raise ValueError("no body_md")  # observed: only "summary" returned
                return d

            # LangGraph GENERATE graph: generate → check → (correct → generate)
            data, res, attempt = generate(
                comp=comp, run=run, cfg=cfg, system=HUB_SYSTEM, user=user_msg, check=check, max_attempts=2, graph="hub",
                correction=lambda e: ("\n\n# Correction\nYour previous answer had no \"body_md\". Return BOTH fields: "
                                      '{"summary":"…","body_md":"the overview in Markdown with [[page-id]] links"}'))
            run["attempts"] = attempt
            text = str(data["body_md"]).strip()
            known = set(self.cards.index())
            kid_ids = {v["id"] for v in kids}
            links = {slug(x) for x in WIKILINK_RE.findall(text)}
            bad_links = sorted(links - known)
            hay = " ".join(v["title"] + " " + v.get("summary", "") + " " + v.get("_body", "") + " " +
                           " ".join(f"{f['value']}" for f in v.get("facts", [])) for v in kids) + head.get("summary", "")
            nums = set(re.findall(r"\d+(?:\.\d+)?", re.sub(r"\[\[[^\]]+\]\]", "", text)))
            new_nums = sorted(n for n in nums if n not in hay)
            cited = len(links & kid_ids) / len(kid_ids)
            run["findings"] = ([f"links to missing pages: {', '.join(bad_links)}"] if bad_links else []) + \
                              ([f"numbers not found in any sub-page: {', '.join(new_nums[:10])}"] if new_nums else [])
            card = {k: head.get(k) for k in ("id", "title", "type", "parent", "aliases", "relations", "confidence")}
            card["summary"] = str(data.get("summary") or head.get("summary", ""))[:200]
            card["evidence"] = [{k: e[k] for k in ("id", "path", "lines", "quote")} for e in head.get("evidence", [])]
            card["sources"] = [s["path"] for s in head.get("sources", [])]
            for k in ("conditions", "events", "facts"):
                card[k] = head.get(k, [])
            origin = {"kind": "llm", "op": "hub", "run": rid, "model": res.model, "by": user["name"],
                      "children_cited": round(cited, 2), "children": len(kid_ids),
                      "unknown_numbers": new_nums[:20], "bad_links": bad_links}
            h = self.cards.new_revision(user["name"], card, text, origin,
                                        change_note=f"topic overview (links {len(links & kid_ids)}/{len(kid_ids)} sub-pages)")
            run["written"].append({"id": cid, "rev": h["rev"], "action": "hub"})
            run["status"] = "done"
        except Exception as e:  # noqa: BLE001
            run["status"] = "failed"
            run["error"] = f"{type(e).__name__}: {e}"
            atomic_write(comp._trace_dir(rid) / "error.txt", traceback.format_exc())
        run["finished"] = now()
        comp._save_run(run)
        self.kb.event(user["name"], f"wiki.hub.{run['status']}", cid, run=rid, error=run.get("error", ""))
        return run

    # ---- static export ---------------------------------------------------------------------------
    def export(self) -> dict:
        """compiled/wiki/<id>.md for every published page + entities.md + index.md — plain Markdown."""
        out = self.kb.root / "compiled" / "wiki"
        out.mkdir(parents=True, exist_ok=True)
        idx = self.cards.index()
        n = 0
        keep = set()
        for cid, m in idx.items():
            v = m.get("_pub") if is_public(m) else None
            if v is None or v.get("lifecycle", "active") != "active":
                continue
            p = self.page(cid, readers=True)
            lines = [f"# {v['title']}", ""]
            if p["breadcrumbs"]:
                lines += ["Path: " + " › ".join(f"[{b['title']}]({b['id']}.md)" for b in p["breadcrumbs"]), ""]
            lines += [f"> {v.get('summary', '')}", "", re.sub(r"\[\[([^\]|#]+)(?:\|([^\]]*))?\]\]",
                                                          lambda mm: f"[{mm.group(2) or mm.group(1)}]({slug(mm.group(1))}.md)",
                                                          v.get("_body", "")), ""]
            if p["children"]:
                lines += ["## Sub-pages", ""] + [f"- [{c['title']}]({c['id']}.md) — {c['summary']}" for c in p["children"]] + [""]
            rel = p["relations_out"] + [{**r, "rel": "←" + r["rel"]} for r in p["relations_in"]]
            if rel:
                lines += ["## Relations", ""] + [f"- {r['rel']}: [{r['title']}]({r['id']}.md) ({r.get('basis')})" for r in rel] + [""]
            if p["sections"]:
                lines += ["## Source sections discussing this concept", ""] + [
                    f"- “{p['source_titles'].get(s['path'], s['path'])}” · {s['title']} (../../sources/{s['path']} L{s['start']}-{s['end']})"
                    for s in p["sections"][:10]] + [""]
            ev = v.get("evidence", [])
            if ev:
                lines += ["## Evidence", ""] + [f"- [{e['id']}] ../../sources/{e['path']} L{e.get('lines', '')}: {e['quote'][:200]}" for e in ev] + [""]
            lines += [f"_rev {v.get('rev')} · published · generated by LithoKB, do not edit by hand_", ""]
            atomic_write(out / f"{cid}.md", "\n".join(lines))
            keep.add(f"{cid}.md")
            n += 1
        ents = self.entities(readers=True)
        atomic_write(out / "entities.md", "# Entities\n\n" + "\n".join(f"- {e['title']} ({e['type'] or 'untyped'}): {e['docs']} document(s), {e['cards']} card(s)"
                                                                 for e in ents) + "\n")
        home = self.home(readers=True)
        atomic_write(out / "index.md", "# Knowledge base home\n\n## Topics\n\n" + "\n".join(
            f"- [{t['title']}]({t['id']}.md) ({t['children']} sub-pages) — {t['summary']}" for t in home["topics"]) +
                     "\n\n## Core concepts (graph centrality)\n\n" + "\n".join(f"- [{c['title']}]({c['id']}.md)" for c in home["central"]) + "\n")
        keep |= {"entities.md", "index.md"}
        for f in out.glob("*.md"):
            if f.name not in keep:
                f.unlink()
        return {"pages": n, "entities": len(ents), "dir": str(out)}


__all__ = ["Wiki", "HUB_SYSTEM"]
