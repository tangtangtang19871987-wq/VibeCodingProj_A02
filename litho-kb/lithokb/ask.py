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
from . import sources as S
from .cards import Cards, is_public, slug, verify_evidence, grounding
from .compiler import Compiler, new_run_id, parse_response
from .store import KB, atomic_write, now

PROMPT_VERSION = "lkb-ask/1"
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
At most %d cards and %d sections. Only ids/nodes that appear in the material.""" % (MAX_CARDS, MAX_SECTIONS)

ANS_SYSTEM = """[[LKB:ANSWER]]
You answer questions for computational-lithography engineers using ONLY the provided knowledge cards and source
sections. Be precise and concise; keep formulas in LaTeX; state conditions (node, NA, wavelength…) when relevant.
- Link cards you rely on as [[card-id]].
- Support every factual statement taken from a source section with an evidence marker [S1], [S2]…; each evidence
  item quotes the section verbatim: {"id":"S1","path":"…","lines":"a-b","quote":"…"} (≤ 300 chars, copied exactly,
  without the "NNNN|" prefix). Quotes are machine-checked.
- If the material is insufficient or contradictory, say so explicitly and list what is missing under "gaps".
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


class Asker:
    def __init__(self, kb: KB, cards: Cards, compiler: Compiler):
        self.kb, self.cards, self.comp = kb, cards, compiler

    def _visible(self, include_unpublished: bool) -> list[dict]:
        return [m for m in self.cards.index().values()
                if m.get("lifecycle", "active") == "active" and m.get("status") != "rejected"
                and (include_unpublished or is_public(m))]

    def _card_text(self, cid: str, include_unpublished: bool) -> str:
        head, body = self.cards.load(cid)
        if not include_unpublished:
            head, body = self.cards.load_rev(cid, head["published_rev"])
        rels = ", ".join(f"{r['rel']}→{r['target']}" for r in head.get("relations", []))
        return (f'<card id="{cid}" type="{head["type"]}" rev="{head["rev"]}">\n# {head["title"]}\n{head.get("summary", "")}\n\n'
                f"{body}\n\nrelations: {rels}\n</card>")

    def ask(self, user: dict, question: str, cfg: dict, include_unpublished: bool = False) -> dict:
        question = question.strip()
        if not question:
            raise ValueError("empty question")
        rid = new_run_id()
        run = {"id": rid, "kind": "query", "by": user["name"], "started": now(), "status": "running",
               "backend": cfg["backend"], "model": cfg.get("model"), "effort": cfg.get("effort"),
               "prompt_version": PROMPT_VERSION, "question": question, "scope": "all" if include_unpublished else "published",
               "sources": [], "source_shas": {}, "timeline": [], "written": []}

        def step(name, **kw):
            run["timeline"].append({"ts": now(), "step": name, **kw})
            self.comp._save_run(run)

        try:
            visible = self._visible(include_unpublished)
            vis_ids = {c["id"] for c in visible}
            meta = S.load_meta(self.kb)
            docs = []
            for p in S.list_md(self.kb):
                tree = doctree.build(S.read_text(self.kb, p), meta[p]["sha256"])
                docs.append((p, tree))
            depth = 6 if sum(t["chars"] for _, t in docs) < 2_000_000 else 2
            nav_user = (f"<question>{question}</question>\n\n# Knowledge tree ({len(visible)} cards)\n<card-index>\n"
                        f"{_tree_text(visible) or '(no cards)'}\n</card-index>\n\n# Source documents (tables of contents)\n" +
                        "\n".join(f'<doc path="{p}" title="{t["title"]}" lines="{t["lines"]}">\n{doctree.outline(t, depth)}\n</doc>'
                                  for p, t in docs))
            step("navigate_prompt_built", cards=len(visible), docs=len(docs))
            res = self.comp.llm_step(run, cfg, NAV_SYSTEM, nav_user, prefix="nav-")
            nav = parse_response_obj(res.text)
            chosen = [c for c in dict.fromkeys(slug(str(x)) for x in nav.get("cards", [])) if c in vis_ids][:MAX_CARDS]
            secs, dropped = [], []
            trees = dict(docs)
            for s in nav.get("sections", [])[:MAX_SECTIONS * 2]:
                p, node = str(s.get("path", "")), str(s.get("node", ""))
                nd = doctree.find(trees[p], node) if p in trees else None
                if nd and len(secs) < MAX_SECTIONS:
                    secs.append({"path": p, "node": node, "title": nd["title"], "lines": f"{nd['start']}-{nd['end']}",
                                 "why": str(s.get("why", ""))[:300]})
                else:
                    dropped.append(s)
            run["navigation"] = {"reasoning": nav.get("reasoning", ""), "cards": chosen, "sections": secs,
                                 "dropped": dropped[:20]}
            step("navigated", cards=len(chosen), sections=len(secs), dropped=len(dropped))

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
            ans_user = f"<question>{question}</question>\n\n# Reading material\n" + ("\n\n".join(blocks) or "(nothing selected)")
            res = self.comp.llm_step(run, cfg, ANS_SYSTEM, ans_user, prefix="ans-")
            ans = parse_response_obj(res.text)
            cache: dict = {}
            ev = [verify_evidence(self.kb, {"id": str(e.get("id", f"S{i + 1}")), "path": str(e.get("path", "")),
                                            "lines": str(e.get("lines", "")), "quote": str(e.get("quote", ""))[:600]}, cache)
                  for i, e in enumerate(ans.get("evidence", []) or [])]
            used = [c for c in (slug(str(x)) for x in ans.get("used_cards", []) or []) if c in vis_ids]
            run["answer"] = {"answer_md": str(ans.get("answer_md", "")), "evidence": ev, "used_cards": used,
                             "confidence": ans.get("confidence"), "gaps": str(ans.get("gaps", "") or "")}
            run["grounding"] = grounding(ev)
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
