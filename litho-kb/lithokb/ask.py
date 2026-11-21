"""Query the knowledge base — reasoning-based navigation, no vectors (PageIndex),
answers that compound back into the wiki (LLM Wiki).

Step 1 · navigate: the model sees the question, the knowledge tree (topic hierarchy
         of cards with one-line summaries) and the documents' table-of-contents
         trees, and decides — explaining why — which cards and which document
         sections to read. Like a person using an index, not a similarity score.
Step 2 · answer:   the model reads exactly those cards (full text) and sections
         (line-numbered) and answers with [[card]] links and [S1] source quotes.
         Quotes are mechanically verified against the source lines.
Step 3 · file back (optional, reviewer+): a good answer becomes a `synthesis`
         card in the review queue — knowledge compounds through use.

Each query is a traced run (kind "query") with both LLM calls on disk.
"""
from __future__ import annotations

import json
import re

from . import doctree
from . import pageindex as PI
from . import sources as S
from .cards import Cards, _norm, grounding, is_public, slug, verify_evidence
from .compiler import Compiler, new_run_id, parse_response
from .store import KB, atomic_write, now

PROMPT_VERSION = "lkb-ask/2"
MAX_CARDS, MAX_SECTIONS = 12, 8

NAV_SYSTEM = """[[LKB:NAVIGATE]]
You are the navigator of LithoKB, a curated computational-lithography knowledge base. You do not answer yet.
Given a question, a knowledge tree (cards grouped under topics, with one-line summaries) and the table of contents
of each source document (node id, line range, heading, gist), decide what must be read to answer well.
Reason like an expert using an index: follow topics, aliases, prerequisites and contrasts; prefer compiled cards,
add source sections when the cards may be incomplete, when exact numbers/conditions matter, or when no card fits.
Return exactly one JSON object in a ```json block:
{"reasoning":"short explanation of your reading plan","cards":["card-id", ...],
 "sections":[{"path":"doc path","node":"n3","why":"…"}]}
At most %d cards and %d sections. Only ids/nodes that appear in the material. Think briefly; do not draft
the answer — only choose what to read.""" % (MAX_CARDS, MAX_SECTIONS)

ANS_SYSTEM = """[[LKB:ANSWER]]
You answer questions for computational-lithography engineers using ONLY the provided knowledge cards and source
sections. Be precise and concise; keep formulas in LaTeX; state conditions (node, NA, wavelength…) when relevant.
- Facts taken from a knowledge card: link the card as [[card-id]] (the card's own evidence already grounds it);
  do NOT create an [S] item for card content.
- Facts taken from a <section> of a source document: add an evidence marker [S1], [S2]…; each evidence item
  quotes that section verbatim (path = the section's document path, never a card id): {"id":"S1","path":"…","lines":"a-b","quote":"…"} (≤ 300 chars, copied exactly,
  without the "NNNN|" prefix). Quotes are machine-checked.
- If the material is insufficient or contradictory, say so explicitly and list what is missing under "gaps".
- State under which conditions (node, wavelength, layer…) your statements hold when the material says so; never
  carry a statement over to conditions the material does not cover.
Return exactly one JSON object in a ```json block:
{"answer_md":"…","evidence":[…],"used_cards":["…"],"confidence":0.0,"gaps":"…"}"""


def _tree_text(cards: list[dict]) -> str:
    ids = {c["id"] for c in cards}
    kids: dict[str, list] = {}
    for c in cards:
        kids.setdefault(c.get("parent") if c.get("parent") in ids else "", []).append(c)
    out: list[str] = []

    def walk(pid, depth, seen):
        for c in sorted(kids.get(pid, []), key=lambda x: (x["type"] != "topic", x["title"])):
            if c["id"] in seen:
                continue
            seen.add(c["id"])
            al = f" (aka {', '.join(c.get('aliases', [])[:4])})" if c.get("aliases") else ""
            out.append(f"{'  ' * depth}- {c['id']} [{c['type']}] {c['title']}{al} — {c.get('summary', '')[:160]}")
            walk(c["id"], depth + 1, seen)

    seen: set = set()
    walk("", 0, seen)
    for c in cards:
        if c["id"] not in seen:
            out.append(f"- {c['id']} [{c['type']}] {c['title']} — {c.get('summary', '')[:160]}")
    return "\n".join(out)


class Navigator:
    """Reasoning-based tree search over the unified knowledge tree (see pageindex.py)."""

    def __init__(self, kb: KB, cards: Cards, comp: Compiler):
        self.kb, self.cards, self.comp = kb, cards, comp

    def hints(self, tree, H, question: str, readers: bool) -> list[str]:
        """Lexical (BM25 over cards and sections) and graph-neighbour hints — suggestions for the navigator."""
        from . import graph as G
        out, seen = [], set()
        lex = [cid for _, cid in self.cards.text_index(readers).search(question, 8) if cid in tree.nodes]
        for cid in lex:
            seen.add(cid)
            out.append(tree.line(cid, H.get(cid), 0) + "   ← 词匹配")
        try:
            sec = [k for _, k in PI.section_index(self.kb).search(question, 8) if k in tree.nodes]
        except Exception:  # noqa: BLE001 — hints are optional
            sec = []
        for k in sec:
            seen.add(k)
            out.append(tree.line(k, H.get(k), 0) + f"   ← 原文词匹配（{tree.nodes[tree.nodes[k]['parent']]['title'][:30] if tree.nodes[k]['parent'] else ''}）")
        try:
            g = G.build(self.kb, self.cards, readers)
            for cid in lex[:3]:
                for nb in g.neighbors(cid, 1, layers=("reviewed",), kinds=("card",))[:4]:
                    if nb["id"] in tree.nodes and nb["id"] not in seen and nb["rel"] in G.STRONG:
                        seen.add(nb["id"])
                        out.append(tree.line(nb["id"], H.get(nb["id"]), 0) +
                                   f"   ← 图谱：{tree.nodes[cid]['title'][:20]} {nb['rel']}")
        except Exception:  # noqa: BLE001
            pass
        return out

    def run(self, run: dict, cfg: dict, question: str, cond_txt: str, readers: bool, conditions: dict | None) -> dict:
        qc = self.kb.config.get("query", {})
        budget = int(qc.get("nav_budget_chars", 24000))
        max_rounds = int(qc.get("nav_max_rounds", 3))
        tree = PI.knowledge_tree(self.kb, self.cards, readers, conditions)
        H = PI.Handles(tree)
        hints = self.hints(tree, H, question, readers)
        system = PI.NAV_SYSTEM % (MAX_CARDS, MAX_SECTIONS)
        view, _ = tree.render(["k", "d"], H, budget)
        cards, secs, dropped, rounds, reasoning = [], [], [], [], []
        for r in range(1, max_rounds + 1):
            sel = ""
            if cards or secs:
                sel = "\n<selected>\n" + "\n".join(H.get(c) for c in cards) + "\n" + \
                      "\n".join(H.get(f"s:{s['path']}#{s['node']}") if s["node"] != "root" else H.get(f"d:{s['path']}")
                                for s in secs) + "\n</selected>\n"
            user = (f"<question>{question}</question>{cond_txt}\n<round n=\"{r}\" of=\"{max_rounds}\"/>\n"
                    f"# Knowledge tree ({len(tree.visible_cards)} cards, {sum(1 for n in tree.nodes.values() if n['kind'] == 'doc')} documents)\n"
                    f"<tree>\n{view}\n</tree>\n\n<hints>\n" + ("\n".join(hints) or "(none)") + "\n</hints>\n" + sel)
            res = self.comp.llm_step(run, cfg, system, user, prefix="nav-" if r == 1 else f"nav{r}-")
            d = parse_response_obj(res.text)
            reasoning.append(str(d.get("reasoning", "")))
            reads, bad = [], []
            for h in d.get("read", []) or d.get("cards", []) or []:
                nid = H.resolve(h)
                if nid is None:
                    bad.append(h)
                    continue
                nd = tree.nodes[nid]
                if nd["kind"] == "card" and nid not in cards and len(cards) < MAX_CARDS:
                    cards.append(nid)
                elif nd["kind"] == "section" and len(secs) < MAX_SECTIONS and \
                        not any(s["path"] == nd["path"] and s["node"] == nd["node"] for s in secs):
                    secs.append({"path": nd["path"], "node": nd["node"], "title": nd["title"],
                                 "lines": f"{nd['start']}-{nd['end']}", "why": str(d.get("reasoning", ""))[:200]})
                elif nd["kind"] == "doc" and len(secs) < MAX_SECTIONS:
                    if nd["size"] <= 16000:
                        secs.append({"path": nd["path"], "node": "root", "title": nd["title"],
                                     "lines": f"1-{nd['lines']}", "why": "whole (small) document"})
                    else:
                        d.setdefault("expand", []).append(h)  # too large to read whole: open it instead
                        continue
                else:
                    continue
                reads.append(nid)
            exp = [x for x in (H.resolve(h) for h in d.get("expand", []) or []) if x and tree.nodes[x]["children"]]
            dropped += bad
            rounds.append({"round": r, "prompt_chars": len(system) + len(user), "read": [H.get(x) for x in reads],
                           "expand": [H.get(x) for x in exp], "invalid": bad[:20], "done": bool(d.get("done", True))})
            if d.get("done", True) is True or not exp or r == max_rounds:
                break
            parts = []
            for x in exp[:6]:
                trail = tree.path_to(x)
                parts += [tree.line(y, H.get(y), i) for i, y in enumerate(trail[:-1])]
                txt, _ = tree.render([x], H, max(2000, budget // max(1, len(exp[:6]))), len(trail) - 1)
                parts.append(txt)
            view = "\n".join(parts)
        return {"reasoning": " / ".join(x for x in reasoning if x), "cards": cards, "sections": secs,
                "dropped": dropped[:20], "rounds": rounds, "hints": len(hints), "method": "tree-search/1",
                "_visible": list(tree.visible_cards)}


class Asker:
    def __init__(self, kb: KB, cards: Cards, compiler: Compiler):
        self.kb, self.cards, self.comp = kb, cards, compiler

    def _visible(self, include_unpublished: bool) -> list[dict]:
        out = []
        for m in self.cards.index().values():
            if m.get("lifecycle", "active") != "active" or m.get("status") == "rejected":
                continue
            if not include_unpublished:
                m = m.get("_pub") if is_public(m) else None  # readers: published revision content only
            if m:
                out.append(m)
        return out

    def _card_text(self, cid: str, include_unpublished: bool) -> str:
        head, body = self.cards.load(cid)
        if not include_unpublished:
            head, body = self.cards.load_rev(cid, head["published_rev"])
        rels = ", ".join(f"{r['rel']}→{r['target']}" for r in head.get("relations", []))
        from .facets import ok
        conds = "; ".join(f"{c['dim']}={c['value']}" for c in ok(head.get("conditions", []))) or "general (none stated)"
        return (f'<card id="{cid}" type="{head["type"]}" rev="{head["rev"]}">\n# {head["title"]}\n{head.get("summary", "")}\n\n'
                f"{body}\n\nrelations: {rels}\napplies under: {conds}\n</card>")

    def ask(self, user: dict, question: str, cfg: dict, include_unpublished: bool = False,
            conditions: dict | None = None) -> dict:
        question = question.strip()
        if not question:
            raise ValueError("empty question")
        rid = new_run_id()
        run = {"id": rid, "kind": "query", "by": user["name"], "started": now(), "status": "running",
               "backend": cfg["backend"], "model": cfg.get("model"), "effort": cfg.get("effort"),
               "prompt_version": PROMPT_VERSION, "question": question, "scope": "all" if include_unpublished else "published",
               "conditions": conditions or {},
               "sources": [], "source_shas": {}, "timeline": [], "written": []}

        def step(name, **kw):
            run["timeline"].append({"ts": now(), "step": name, **kw})
            self.comp._save_run(run)

        try:
            meta = S.load_meta(self.kb)
            cond_txt = ("\n<conditions>The user asks about: " + ", ".join(f"{k}={v}" for k, v in conditions.items()) +
                        ". Prefer knowledge stated for these conditions; general knowledge (no condition stated) may "
                        "still apply.</conditions>\n") if conditions else ""
            nav = Navigator(self.kb, self.cards, self.comp).run(run, cfg, question, cond_txt,
                                                                readers=not include_unpublished, conditions=conditions)
            chosen, secs = nav["cards"], nav["sections"]
            vis_ids = set(nav.pop("_visible"))
            run["navigation"] = nav
            step("navigated", cards=len(chosen), sections=len(secs), rounds=len(nav["rounds"]),
                 dropped=len(nav["dropped"]))

            blocks = [self._card_text(c, include_unpublished) for c in chosen]
            texts = {}
            for s in secs:
                texts.setdefault(s["path"], S.read_text(self.kb, s["path"]))
                lines = texts[s["path"]].splitlines()
                a, b = (int(x) for x in s["lines"].split("-"))
                b = min(b, a + 400)  # keep a single section bounded
                num = "\n".join(f"{i:5d}|{lines[i - 1]}" for i in range(a, min(b, len(lines)) + 1))
                blocks.append(f'<section path="{s["path"]}" node="{s["node"]}" lines="{a}-{b}" title="{s["title"]}">\n{num}\n</section>')
            run["sources"] = sorted({s["path"] for s in secs})
            run["source_shas"] = {p: meta[p]["sha256"] for p in run["sources"]}
            ans_user = f"<question>{question}</question>{cond_txt}\n\n# Reading material\n" + ("\n\n".join(blocks) or "(nothing selected)")
            res = self.comp.llm_step(run, cfg, ANS_SYSTEM, ans_user, prefix="ans-")
            ans = parse_response_obj(res.text)
            cache: dict = {}
            read_paths = {s["path"] for s in secs}
            ev = []
            for i, e in enumerate(ans.get("evidence", []) or []):
                if not isinstance(e, dict):
                    continue
                item = {"id": str(e.get("id", f"S{i + 1}")), "path": str(e.get("path", "")),
                        "lines": str(e.get("lines", "")), "quote": str(e.get("quote", ""))[:600]}
                cid = slug(item["path"])
                if cid in chosen and item["path"] not in read_paths:
                    # quoted from a card it read: check against that card's text (second-hand, card is grounded)
                    head, body = self.cards.load(cid)
                    if not include_unpublished:
                        head, body = self.cards.load_rev(cid, head["published_rev"])
                    hay = _norm(" ".join([head.get("title", ""), head.get("summary", ""), body] +
                                         [x.get("quote", "") for x in head.get("evidence", [])]))
                    item["check"] = "card" if _norm(item["quote"]) and _norm(item["quote"]) in hay else "missing"
                    item["card"] = cid
                    ev.append(item)
                    continue
                r = verify_evidence(self.kb, item, cache)
                if r["path"] not in read_paths:
                    r["not_read"] = True  # cites a document section the navigator did not select
                ev.append(r)
            used = [c for c in (slug(str(x)) for x in ans.get("used_cards", []) or []) if c in vis_ids]
            run["answer"] = {"answer_md": str(ans.get("answer_md", "")), "evidence": ev, "used_cards": used,
                             "confidence": ans.get("confidence"), "gaps": str(ans.get("gaps", "") or "")}
            run["grounding"] = grounding(ev)
            if run["answer"]["gaps"].strip() and run["answer"]["gaps"].strip() not in ("无", "none", "None", "-"):
                from .issues import Issues  # what users need but the knowledge base cannot answer → gap register
                gap = Issues(self.kb).create(user["name"], "gap", question[:120], run["answer"]["gaps"],
                                             cards=used, sources=run["sources"], origin={"kind": "query", "run": rid})
                run["gap_issue"] = gap["id"]
            run["status"] = "done"
            step("answered", evidence=len(ev), grounding=run["grounding"]["score"])
        except Exception as e:
            import traceback
            run["status"] = "failed"
            run["error"] = f"{type(e).__name__}: {e}"
            atomic_write(self.comp._trace_dir(rid) / "error.txt", traceback.format_exc())
            step("failed", error=run["error"])
        run["finished"] = now()
        self.comp._save_run(run)
        self.kb.event(user["name"], f"query.{run['status']}", rid, question=question[:300])
        return run

    def file_back(self, user: dict, rid: str, title: str = "", parent: str = "") -> dict:
        """Turn a query answer into a `synthesis` card proposal (enters review)."""
        run = self.comp.trace(rid)["run"]
        if run.get("kind") != "query" or run.get("status") != "done":
            raise ValueError("only completed queries can be filed back")
        if run.get("filed_as"):
            raise ValueError(f"already filed as {run['filed_as']}")
        ans = run["answer"]
        base = slug(title) or slug(run["question"])
        cid = slug("q-" + (base[:50] if len(base) >= 6 else rid[-6:]))
        while self.cards.exists(cid):
            cid = slug(cid + "-" + rid[-4:])
        mapping = {e["id"]: f"E{i + 1}" for i, e in enumerate(ans["evidence"])}
        body = re.sub(r"\[(S\d+)\]", lambda m: f"[{mapping.get(m.group(1), m.group(1))}]", ans["answer_md"])
        body = f"> **问题**：{run['question']}\n\n{body}"
        if ans.get("gaps"):
            body += f"\n\n**尚不明确 / 资料缺口**：{ans['gaps']}"
        evidence = [{"id": mapping[e["id"]], "path": e["path"], "lines": e["lines"], "quote": e["quote"]} for e in ans["evidence"]]
        card = {"id": cid, "title": title or run["question"][:80], "type": "synthesis", "parent": slug(parent),
                "aliases": [], "summary": ans["answer_md"].strip().splitlines()[0][:200] if ans["answer_md"].strip() else "",
                "relations": [{"rel": "related_to", "target": c, "basis": "inferred", "confidence": 0.8} for c in ans["used_cards"]],
                "evidence": evidence, "sources": sorted({e["path"] for e in evidence}),
                "confidence": ans.get("confidence")}
        head = self.cards.new_revision(user["name"], card, body, {"kind": "query", "run": rid, "user": user["name"],
                                                                   "model": run.get("model")},
                                       change_note=f"filed from query {rid} by {user['name']}")
        run["filed_as"] = cid
        self.comp._save_run(run)
        self.kb.event(user["name"], "query.filed", cid, run=rid, rev=head["rev"])
        return head


def parse_response_obj(text: str) -> dict:
    m = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.S)
    raw = m.group(1) if m else text[text.find("{"): text.rfind("}") + 1]
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("expected a JSON object")
    return data


__all__ = ["Asker", "parse_response", "parse_response_obj"]
