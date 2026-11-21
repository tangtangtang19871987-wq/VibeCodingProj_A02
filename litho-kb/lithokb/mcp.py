"""MCP server (stdio, JSON-RPC 2.0, stdlib only): LithoKB as a trustworthy tool for agents.

    claude mcp add lithokb -- python3 /path/to/litho-kb/lkb --root /path/to/kbdata --user reader1 mcp

Agents get the same discipline as human readers: published knowledge only (unless the
configured user is a reviewer and asks for unpublished), applicability conditions,
evidence with document titles and line numbers, open contradictions, and tools to read
and verify the original text themselves — no embeddings, no hidden context.
"""
from __future__ import annotations

import json
import sys

from . import __version__
from . import auth as A
from . import doctree
from . import facets as F
from . import sources as S
from .cards import Cards, is_public, slug, verify_evidence
from .compiler import Compiler, llm_config
from .issues import PUBLIC_KINDS, Issues
from .store import KB

PROTOCOL = "2025-06-18"
INSTRUCTIONS = ("LithoKB is a curated computational-lithography knowledge base. Knowledge cards are compiled from "
                "original documents and published only after human review. Every statement cites verbatim evidence "
                "(document + line numbers) that you can check with read_source / verify_quote. Statements may only hold "
                "under stated conditions (process node, wavelength, NA, layer, mask, application) — pass `conditions` "
                "and respect them. Open contradictions are reported with each card; do not hide them.")

COND = {"type": "object", "description": "applicability filter, e.g. {\"wavelength\": \"EUV\", \"node\": \"5nm\"}",
        "additionalProperties": {"type": "string"}}
TOOLS = [
    {"name": "search_knowledge", "description": "Search knowledge cards by words (titles, aliases, summaries, bodies).",
     "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "conditions": COND,
                                                      "limit": {"type": "integer", "default": 20}}, "required": ["query"]}},
    {"name": "get_card", "description": "Full knowledge card: body (Markdown, [[links]], [E#] evidence markers), evidence "
     "with document titles and line numbers, applicability conditions, facts, events, relations, open issues.",
     "inputSchema": {"type": "object", "properties": {"id": {"type": "string"},
                                                      "include_unpublished": {"type": "boolean", "default": False}},
                     "required": ["id"]}},
    {"name": "knowledge_tree", "description": "Topic hierarchy of the knowledge base: id, type, title, one-line summary.",
     "inputSchema": {"type": "object", "properties": {"conditions": COND}}},
    {"name": "list_documents", "description": "Original source documents (path, title, version, uploader, processing policy).",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "document_outline", "description": "Table-of-contents tree of one source document with line ranges.",
     "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
    {"name": "read_source", "description": "Read lines of an original document (line-numbered, max 400 lines).",
     "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}, "start": {"type": "integer"},
                                                      "end": {"type": "integer"}}, "required": ["path"]}},
    {"name": "verify_quote", "description": "Check that a quote really appears in a document at the given lines.",
     "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}, "lines": {"type": "string"},
                                                      "quote": {"type": "string"}}, "required": ["path", "quote"]}},
    {"name": "facts", "description": "Structured facts (parameter/metric values with units and conditions) across cards.",
     "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}, "conditions": COND}}},
    {"name": "timeline", "description": "Dated events extracted from the cards, chronologically.",
     "inputSchema": {"type": "object", "properties": {"conditions": COND}}},
    {"name": "list_issues", "description": "Open contradictions and open questions in the knowledge base.",
     "inputSchema": {"type": "object", "properties": {"card": {"type": "string"}}}},
    {"name": "ask", "description": "Ask a question: the knowledge base navigates its trees, reads cards and source sections, "
     "and answers with verified quotes (one LLM-backed query; slower than the other tools).",
     "inputSchema": {"type": "object", "properties": {"question": {"type": "string"}, "conditions": COND},
                     "required": ["question"]}},
]


class Server:
    def __init__(self, kb: KB, user: dict):
        self.kb, self.user = kb, user
        self.cards = Cards(kb)
        self.comp = Compiler(kb, self.cards)
        self.reviewer = A.RANK[user["role"]] >= A.RANK["reviewer"]

    def _visible(self, m: dict, unpublished: bool = False) -> bool:
        return (unpublished and self.reviewer) or is_public(m)

    def _cards(self, conditions=None, unpublished=False):
        for m in self.cards.index().values():
            if m.get("lifecycle", "active") != "active" or not self._visible(m, unpublished):
                continue
            m = self.cards.view(m, not (unpublished and self.reviewer))
            if m is None:
                continue
            a = F.applies(F.ok(m.get("conditions", [])), conditions or {})
            if a != "no":
                yield m, a

    # ---- tools ------------------------------------------------------------------------
    def search_knowledge(self, query, conditions=None, limit=20):
        hits = self.cards.search(query, visible_only=True, limit=200)  # agents see published content
        allowed = {m["id"]: a for m, a in self._cards(conditions)}
        return [{**h, "applies": allowed[h["id"]]} for h in hits if h["id"] in allowed][:limit]

    def get_card(self, id, include_unpublished=False):
        cid = slug(id)
        head, body = self.cards.load(cid)
        if head.get("lifecycle") == "superseded":
            return {"id": cid, "superseded_by": head.get("replaced_by")}
        if include_unpublished and self.reviewer:
            meta = head
        elif is_public(head):
            meta, body = self.cards.load_rev(cid, head["published_rev"])
        else:
            raise ValueError(f"card {cid} is not published")
        titles = S.doc_titles(self.kb, [e["path"] for e in meta.get("evidence", [])])
        issues = [{"kind": i["kind"], "title": i["title"], "detail": i["detail"]}
                  for i in Issues(self.kb).query(status="open", card=cid) if i["kind"] in PUBLIC_KINDS]
        return {"id": cid, "title": meta["title"], "type": meta["type"], "parent": meta.get("parent", ""),
                "summary": meta.get("summary", ""), "body": body, "rev": meta["rev"],
                "status": "published" if not (include_unpublished and self.reviewer) else head["status"],
                "conditions": F.ok(meta.get("conditions", [])) or "general (no condition stated)",
                "facts": F.ok(meta.get("facts", [])), "events": F.ok(meta.get("events", [])),
                "relations": meta.get("relations", []),
                "evidence": [{"id": e["id"], "document": titles.get(e["path"], e["path"]), "path": e["path"],
                              "lines": e.get("found_lines") or e["lines"], "quote": e["quote"], "check": e.get("check")}
                             for e in meta.get("evidence", [])],
                "open_issues": issues}

    def knowledge_tree(self, conditions=None):
        rows = [(m, a) for m, a in self._cards(conditions) if m["type"] != "summary"]
        ids = {m["id"] for m, _ in rows}
        kids: dict = {}
        for m, a in rows:
            kids.setdefault(m.get("parent") if m.get("parent") in ids else "", []).append((m, a))
        out: list = []

        def walk(pid, d, seen):
            for m, a in sorted(kids.get(pid, []), key=lambda x: (x[0]["type"] != "topic", x[0]["title"])):
                if m["id"] in seen:
                    continue
                seen.add(m["id"])
                out.append(f"{'  ' * d}- {m['id']} [{m['type']}] {m['title']} — {m.get('summary', '')[:120]}"
                           + (" (general)" if a == "general" and conditions else ""))
                walk(m["id"], d + 1, seen)
        walk("", 0, set())
        return "\n".join(out) or "(no published knowledge)"

    def list_documents(self):
        meta = S.load_meta(self.kb)
        titles = S.doc_titles(self.kb, S.list_md(self.kb))
        return [{"path": p, "title": titles.get(p, p), "version": meta[p]["version"], "uploaded_by": meta[p]["by"],
                 "policy": S.policy_of(self.kb, p, meta)["policy"]} for p in S.list_md_by_policy(self.kb, "compile", "reference")]

    def document_outline(self, path):
        p = S.clean_path(path)
        if S.policy_of(self.kb, p)["policy"] == "exclude":
            raise ValueError("document excluded")
        return doctree.outline(doctree.build(S.read_text(self.kb, p), S.load_meta(self.kb)[p]["sha256"]))

    def read_source(self, path, start=1, end=None):
        p = S.clean_path(path)
        if S.policy_of(self.kb, p)["policy"] == "exclude":
            raise ValueError("document excluded")
        lines = S.read_text(self.kb, p).splitlines()
        start = max(1, int(start or 1))
        end = min(len(lines), int(end or start + 199), start + 399)
        return "\n".join(f"{i:5d}|{lines[i - 1]}" for i in range(start, end + 1))

    def verify_quote(self, path, quote, lines=""):
        r = verify_evidence(self.kb, {"id": "Q", "path": S.clean_path(path), "lines": lines or "", "quote": quote})
        return {k: r.get(k) for k in ("check", "found_lines")}

    def _rows(self, kind, conditions=None, name=""):
        out = []
        for m, _ in self._cards(conditions):
            evs = {e["id"]: e for e in m.get("evidence", [])}
            for it in F.ok(m.get(kind, [])):
                if name and name.lower() not in str(it.get("name", "")).lower():
                    continue
                e = evs.get(it.get("evidence"), {})
                out.append({**{k: v for k, v in it.items() if k != "supported"}, "card": m["id"], "card_title": m["title"],
                            "path": e.get("path"), "lines": e.get("found_lines") or e.get("lines"), "quote": e.get("quote")})
        return out

    def facts(self, name="", conditions=None):
        return sorted(self._rows("facts", conditions, name), key=lambda r: r["name"])

    def timeline(self, conditions=None):
        return sorted(self._rows("events", conditions), key=lambda r: (F.year_of(r["when"]) is None, F.year_of(r["when"]) or 0))

    def list_issues(self, card=""):
        return [{"id": i["id"], "kind": i["kind"], "title": i["title"], "detail": i["detail"], "cards": i["cards"]}
                for i in Issues(self.kb).query(status="open", card=slug(card) if card else None) if i["kind"] in PUBLIC_KINDS]

    def ask(self, question, conditions=None):
        from .ask import Asker
        run = Asker(self.kb, self.cards, self.comp).ask(self.user, question, llm_config(self.kb), conditions=conditions or {})
        if run["status"] != "done":
            raise ValueError(run.get("error", "query failed"))
        return {"answer": run["answer"]["answer_md"], "evidence": run["answer"]["evidence"], "gaps": run["answer"]["gaps"],
                "reading_plan": run["navigation"], "trace": run["id"]}

    # ---- JSON-RPC ---------------------------------------------------------------------
    def handle(self, msg: dict):
        mid, method, params = msg.get("id"), msg.get("method"), msg.get("params") or {}
        if method == "initialize":
            return {"jsonrpc": "2.0", "id": mid, "result": {
                "protocolVersion": params.get("protocolVersion", PROTOCOL), "capabilities": {"tools": {}},
                "serverInfo": {"name": "lithokb", "version": __version__}, "instructions": INSTRUCTIONS}}
        if method and method.startswith("notifications/"):
            return None
        if method == "ping":
            return {"jsonrpc": "2.0", "id": mid, "result": {}}
        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS}}
        if method == "tools/call":
            name, args = params.get("name"), params.get("arguments") or {}
            if name not in {t["name"] for t in TOOLS}:
                return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": f"unknown tool {name}"}}
            try:
                res = getattr(self, name)(**args)
                text = res if isinstance(res, str) else json.dumps(res, ensure_ascii=False, indent=1)
                self.kb.event(self.user["name"], "mcp.call", name, args={k: str(v)[:100] for k, v in args.items()})
                return {"jsonrpc": "2.0", "id": mid, "result": {"content": [{"type": "text", "text": text}], "isError": False}}
            except Exception as e:  # tool errors are results the agent can read, not protocol errors
                return {"jsonrpc": "2.0", "id": mid, "result": {"content": [{"type": "text", "text": f"error: {e}"}], "isError": True}}
        if mid is None:
            return None
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"method not found: {method}"}}

    def serve(self, inp=sys.stdin, out=sys.stdout):
        for line in inp:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                out.write(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}) + "\n")
                out.flush()
                continue
            resp = self.handle(msg)
            if resp is not None:
                out.write(json.dumps(resp, ensure_ascii=False) + "\n")
                out.flush()
