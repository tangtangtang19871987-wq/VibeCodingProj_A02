"""Issue register: contradictions, open questions, knowledge gaps, reader reports.

A knowledge base should not paper over disagreement or ignorance. These become
first-class items with a lifecycle (open → resolved | wontfix, reopen), owners'
comments and links to the cards / sources / evidence concerned:

  contradiction  two sources (or a source and a card) say different things   ← compiler, "contradicts" relations
  open_question  something the sources leave unanswered                       ← compiler
  gap            a question users asked that the knowledge base cannot answer ← Q&A ("gaps")
  report         a reader flags an error / unclear passage on a card          ← any signed-in user

Open contradictions and open questions are shown on the card to every reader
(transparency); the full register is a reviewer/admin work list that also tells
admins which documents to add next. One readable JSON file per issue (issues/).
"""
from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

from .store import KB, LOCK, atomic_write, now

KINDS = ("contradiction", "open_question", "gap", "report")
STATUSES = ("open", "resolved", "wontfix")
PUBLIC_KINDS = ("contradiction", "open_question")


class IssueError(Exception):
    pass


def _sig(kind: str, title: str, cards: list) -> str:
    t = re.sub(r"\W+", "", (title or "").lower())[:60]
    return f"{kind}|{t}|{','.join(sorted(cards or []))}"


class Issues:
    def __init__(self, kb: KB):
        self.kb = kb
        self.dir = kb.root / "issues"

    def _path(self, iid: str) -> Path:
        if not re.fullmatch(r"iss-[0-9a-f]{10}", iid):
            raise IssueError(f"bad issue id {iid!r}")
        return self.dir / f"{iid}.json"

    def _save(self, it: dict) -> None:
        atomic_write(self._path(it["id"]), json.dumps(it, ensure_ascii=False, indent=1))

    def all(self) -> list[dict]:
        if not self.dir.exists():
            return []
        out = []
        for p in self.dir.glob("iss-*.json"):
            try:
                out.append(json.loads(p.read_text("utf-8")))
            except json.JSONDecodeError:
                pass
        return sorted(out, key=lambda x: x.get("updated", ""), reverse=True)

    def get(self, iid: str) -> dict:
        p = self._path(iid)
        if not p.exists():
            raise FileNotFoundError(iid)
        return json.loads(p.read_text("utf-8"))

    def query(self, status: str | None = None, kind: str | None = None, card: str | None = None,
              by: str | None = None) -> list[dict]:
        return [i for i in self.all() if (not status or i["status"] == status) and (not kind or i["kind"] == kind)
                and (not card or card in i.get("cards", [])) and (not by or i.get("by") == by)]

    def create(self, actor: str, kind: str, title: str, detail: str = "", cards: list | None = None,
               sources: list | None = None, evidence: list | None = None, origin: dict | None = None) -> dict:
        if kind not in KINDS:
            raise IssueError(f"kind must be one of {KINDS}")
        title = (title or "").strip()
        if len(title) < 4:
            raise IssueError("issue title too short")
        cards = sorted({c for c in (cards or []) if c})
        sig = _sig(kind, title, cards)
        with LOCK:
            for it in self.all():  # the same issue seen again → note it on the existing item
                if it.get("sig") == sig and it["status"] == "open":
                    it["history"].append({"ts": now(), "user": actor, "action": "seen_again",
                                          "comment": (detail or "")[:500], "origin": origin or {}})
                    it["seen"] = it.get("seen", 1) + 1
                    it["updated"] = now()
                    self._save(it)
                    return it
            it = {"id": "iss-" + uuid.uuid4().hex[:10], "kind": kind, "title": title[:200], "detail": (detail or "")[:4000],
                  "cards": cards, "sources": sorted({s for s in (sources or []) if s}), "evidence": evidence or [],
                  "status": "open", "by": actor, "created": now(), "updated": now(), "origin": origin or {},
                  "sig": sig, "seen": 1, "history": [{"ts": now(), "user": actor, "action": "open", "comment": (detail or "")[:500]}]}
            self._save(it)
        self.kb.event(actor, f"issue.open.{kind}", it["id"], title=title[:200], cards=cards)
        return it

    def act(self, user: dict, iid: str, action: str, comment: str = "", resolution: str = "") -> dict:
        from .auth import RANK
        it = self.get(iid)
        if action == "comment":
            if RANK[user["role"]] < RANK["reviewer"] and it.get("by") != user["name"]:
                raise PermissionError("only reviewers or the reporter can comment")
        elif RANK[user["role"]] < RANK["reviewer"]:
            raise PermissionError("requires role reviewer")
        if action in ("resolve", "wontfix") and len((comment or resolution).strip()) < 4:
            raise IssueError("resolving needs a short explanation")
        with LOCK:
            if action == "resolve":
                it["status"], it["resolution"] = "resolved", resolution or comment
            elif action == "wontfix":
                it["status"], it["resolution"] = "wontfix", resolution or comment
            elif action == "reopen":
                it["status"] = "open"
            elif action != "comment":
                raise IssueError(f"unknown action {action}")
            it["history"].append({"ts": now(), "user": user["name"], "action": action, "comment": comment[:2000]})
            it["updated"] = now()
            self._save(it)
        self.kb.event(user["name"], f"issue.{action}", iid, comment=comment[:300])
        return it

    def stats(self) -> dict:
        s: dict = {"open": 0, "by_kind": {}}
        for it in self.all():
            if it["status"] == "open":
                s["open"] += 1
                s["by_kind"][it["kind"]] = s["by_kind"].get(it["kind"], 0) + 1
        return s
