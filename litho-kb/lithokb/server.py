"""HTTP server: JSON API + static single-page UI. Stdlib ThreadingHTTPServer, no framework.

Auth: `Authorization: Bearer <token>` for API calls (no CSRF surface); the same token
in an HttpOnly cookie is accepted only for GET (so <img> in source docs can load).
"""
from __future__ import annotations

import gzip
import json
import mimetypes
import re
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from . import __version__
from . import auth as A
from . import doctree
from . import schema as SC
from . import sources as S
from .ask import Asker
from .cards import CardError, Cards, is_public
from .compiler import Compiler, card_history
from .store import KB

WEB = Path(__file__).parent / "web"
MAX_BODY = 200 * 1024 * 1024


class App:
    def __init__(self, kb: KB):
        self.kb = kb
        self.cards = Cards(kb)
        self.compiler = Compiler(kb, self.cards)
        self.asker = Asker(kb, self.cards, self.compiler)
        from .consolidate import Consolidator
        self.consolidator = Consolidator(kb, self.cards, self.compiler)


def card_source_paths(meta: dict, body: str) -> set:
    """Every source document a card refers to: sources, evidence, and links in its body."""
    paths = {x["path"] for x in meta.get("sources", [])} | {e.get("path", "") for e in meta.get("evidence", [])}
    paths |= set(re.findall(r"\(src:([^)\s]+)\)", body))
    paths |= set(re.findall(r"补充（来自 ([^）\[\]]+?\.(?:md|markdown|mdx))）", body))
    return {p for p in paths if p}


class HTTPError(Exception):
    def __init__(self, code: int, msg: str):
        super().__init__(msg)
        self.code, self.msg = code, msg


def make_handler(app: App):
    kb = app.kb

    class H(BaseHTTPRequestHandler):
        server_version = f"LithoKB/{__version__}"
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):  # quiet; audit log is the real log
            pass

        # ---- plumbing ---------------------------------------------------------
        def _user(self, allow_cookie: bool):
            h = self.headers.get("Authorization", "")
            tok = h[7:] if h.startswith("Bearer ") else None
            if not tok and allow_cookie:
                m = re.search(r"lkb_token=([^;]+)", self.headers.get("Cookie", ""))
                tok = m.group(1) if m else None
            return A.verify_token(kb, tok)

        def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None):
            gz = len(body) > 1024 and "gzip" in self.headers.get("Accept-Encoding", "") and \
                (ctype.startswith("text/") or "json" in ctype or "javascript" in ctype)
            if gz:
                body = gzip.compress(body, 5)
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            if gz:
                self.send_header("Content-Encoding", "gzip")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _json(self, obj, code=200, extra=None):
            self._send(code, json.dumps(obj, ensure_ascii=False).encode(), "application/json; charset=utf-8", extra)

        def _body(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            if n > MAX_BODY:
                raise HTTPError(413, "upload too large")
            raw = self.rfile.read(n) if n else b"{}"
            try:
                return json.loads(raw or b"{}")
            except json.JSONDecodeError:
                raise HTTPError(400, "invalid JSON")

        def do_HEAD(self):
            self.do_GET()

        def do_GET(self):
            self._dispatch("GET")

        def do_POST(self):
            self._dispatch("POST")

        def do_PUT(self):
            self._dispatch("PUT")

        def do_DELETE(self):
            self._dispatch("DELETE")

        def _dispatch(self, method: str):
            url = urlparse(self.path)
            path = unquote(url.path)
            q = {k: v[-1] for k, v in parse_qs(url.query).items()}
            try:
                if path.startswith("/api/"):
                    user = self._user(allow_cookie=(method == "GET"))
                    self._api(method, path[5:], q, user)
                elif path.startswith("/raw/") and method == "GET":
                    user = self._user(allow_cookie=True)
                    self._readable(user)
                    rel = S.clean_path(path[5:])
                    data = S.read(kb, rel, int(q["v"]) if q.get("v", "").isdigit() else None)
                    ctype = mimetypes.guess_type(rel)[0] or "application/octet-stream"
                    if rel.lower().endswith(S.MD_EXT):
                        ctype = "text/plain; charset=utf-8"
                    self._send(200, data, ctype, {"Cache-Control": "private, max-age=60",
                                                  "Content-Security-Policy": "sandbox"})
                else:
                    self._static(path)
            except HTTPError as e:
                self._json({"error": e.msg}, e.code)
            except PermissionError as e:
                self._json({"error": str(e)}, 403)
            except (CardError, S.SourceError, A.AuthError, ValueError) as e:
                self._json({"error": str(e)}, 400)
            except FileNotFoundError as e:
                self._json({"error": f"not found: {e}"}, 404)
            except Exception as e:  # pragma: no cover
                traceback.print_exc()
                self._json({"error": f"internal error: {e}"}, 500)

        def _static(self, path: str):
            name = "index.html" if path in ("/", "") else path.lstrip("/")
            f = (WEB / name).resolve()
            if not str(f).startswith(str(WEB.resolve())) or not f.is_file():
                f = WEB / "index.html"
            ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype.endswith("javascript"):
                ctype += "; charset=utf-8"
            self._send(200, f.read_bytes(), ctype, {"Cache-Control": "no-cache"})

        def _readable(self, user):
            if not kb.config.get("public_read") and not user:
                raise HTTPError(401, "login required")

        # ---- API ------------------------------------------------------------------
        def _api(self, method: str, route: str, q: dict, user):
            C = app.cards
            parts = route.strip("/").split("/")
            head = parts[0]
            reviewer = user and A.RANK[user["role"]] >= A.RANK["reviewer"]

            if head == "login" and method == "POST":
                b = self._body()
                tok = A.login(kb, b.get("name", ""), b.get("password", ""))
                u = A.verify_token(kb, tok)
                return self._json({"token": tok, "user": u},
                                  extra={"Set-Cookie": f"lkb_token={tok}; Path=/; HttpOnly; SameSite=Strict; Max-Age={A.TOKEN_TTL}"})
            if head == "logout":
                return self._json({"ok": True}, extra={"Set-Cookie": "lkb_token=; Path=/; Max-Age=0"})
            if head == "me":
                return self._json({"user": user, "site": kb.config["site_name"], "public_read": kb.config["public_read"],
                                   "version": __version__})

            self._readable(user)

            # ---- Layer 0: sources ----------------------------------------------
            if head == "sources":
                if method == "GET" and len(parts) == 1:
                    return self._json(S.tree(kb))
                if method == "GET" and parts[1:] == ["file"]:
                    rel = S.clean_path(q.get("path", ""))
                    meta = S.load_meta(kb).get(rel)
                    if not meta:
                        raise FileNotFoundError(rel)
                    v = int(q["v"]) if q.get("v", "").isdigit() else None
                    derived = [{"id": m["id"], "title": m["title"], "status": m["status"],
                                "public": is_public(m), "stale": rel in m.get("stale_sources", [])}
                               for m in C.index().values() if any(s["path"] == rel for s in m.get("sources", []))]
                    if not reviewer:
                        derived = [d for d in derived if d["public"]]
                    is_md = rel.lower().endswith(S.MD_EXT)
                    text = S.read_text(kb, rel, v) if is_md else None
                    sha = meta["sha256"] if not v or v == meta["version"] else f"{rel}@{v}"
                    return self._json({"path": rel, "meta": meta, "text": text, "derived_cards": derived,
                                       "tree": doctree.build(text, sha) if is_md else None})
                if method == "POST" and parts[1:] == ["upload"]:
                    A.require(user, "reviewer")
                    b = self._body()
                    res = S.put(kb, user["name"], b.get("files", []), prefix=b.get("prefix", ""), note=b.get("note", ""))
                    return self._json({"results": res})
                if method == "DELETE" and parts[1:] == ["file"]:
                    A.require(user, "admin")
                    S.remove(kb, user["name"], q.get("path", ""))
                    return self._json({"ok": True})

            # ---- Layer 1: cards ------------------------------------------------
            if head == "cards":
                if method == "GET" and len(parts) == 1:
                    rows = C.listing(status=q.get("status") or None, visible_only=not reviewer)
                    if reviewer:  # risk + granularity are governance signals for reviewers/admins
                        for row in rows:
                            row["risk"] = C.risk(row["id"])
                    return self._json(rows)
                if method == "POST" and parts[1] == "_batch":
                    b = self._body()
                    return self._json(C.batch(user or {"name": "anonymous", "role": "anonymous"}, list(b.get("ids", [])),
                                              b.get("action", ""), b.get("comment", "")))
                cid = parts[1]
                if method == "GET" and len(parts) == 2:
                    meta, body = C.load(cid)
                    if not reviewer:
                        if meta.get("lifecycle") == "superseded":
                            return self._json({"id": cid, "title": meta["title"], "lifecycle": "superseded",
                                               "replaced_by": meta.get("replaced_by")})
                        if not is_public(meta):
                            raise FileNotFoundError(cid)
                    view = q.get("view", "published" if not reviewer else "head")
                    out = {"head": {**meta, "body": body}}
                    paths = card_source_paths(meta, body)
                    if meta.get("published_rev"):
                        pm, pb = C.load_rev(cid, meta["published_rev"])
                        out["published"] = {**pm, "body": pb}
                    if not reviewer:
                        out = {"published": out.get("published"),
                               "head": {k: meta.get(k) for k in ("id", "lifecycle", "published_rev", "replaced_by")}}
                    else:
                        out["reviews"] = C.review_summary(cid, meta["rev"])
                        out["risk"] = C.risk(cid)
                        out["review_log"] = C.reviews(cid)
                        out["revisions"] = list(range(1, meta["rev"] + 1))
                        out["events"] = card_history(kb, cid)[-100:]
                    # backlinks
                    idx = C.index()
                    out["backlinks"] = [{"id": m["id"], "title": m["title"]} for m in idx.values()
                                        if (cid in m.get("_links", []) or any(r["target"] == cid for r in m.get("relations", []))
                                            or m.get("parent") == cid) and (reviewer or is_public(m))]
                    if out.get("published"):
                        paths |= card_source_paths(out["published"], out["published"].get("body", ""))
                    out["source_titles"] = S.doc_titles(kb, paths)
                    out["view"] = view
                    return self._json(out)
                if method == "GET" and parts[2:3] == ["rev"]:
                    A.require(user, "reviewer")
                    m, b = C.load_rev(cid, int(parts[3]))
                    return self._json({**m, "body": b})
                if method == "GET" and parts[2:3] == ["diff"]:
                    A.require(user, "reviewer")
                    a_, b_ = int(q.get("a", 0)), int(q.get("b", 1))
                    return self._json({"diff": C.diff(cid, a_, b_), "semantic": C.semantic_diff(cid, a_, b_)})
                if method == "POST" and parts[2:3] == ["action"]:
                    b = self._body()
                    m = C.act(user or {"name": "anonymous", "role": "anonymous"}, cid, b.get("action", ""),
                              b.get("comment", ""), b.get("target", ""), b.get("anchor", ""))
                    if b.get("action") in ("publish", "withdraw", "restore", "supersede"):
                        C.write_exports()
                    return self._json({k: v for k, v in m.items() if not k.startswith("_")})
                if method == "PUT" and len(parts) == 2:
                    A.require(user, "reviewer")
                    m = C.human_edit(user, cid, self._body())
                    return self._json(m)
                if method == "POST" and parts[2:3] == ["consolidate"]:
                    A.require(user, "reviewer")
                    from .compiler import llm_config
                    b = self._body()
                    adm = user["role"] == "admin"
                    run = app.consolidator.run(user, cid, llm_config(kb, b.get("backend") if adm else None,
                                                                     b.get("model") if adm else None))
                    return self._json(run)
                if method == "POST" and parts[2:3] == ["merge"]:
                    from .consolidate import merge
                    b = self._body()
                    h = merge(C, user, cid, (b.get("into") or "").strip())
                    C.write_exports()
                    return self._json({k: v for k, v in h.items() if not k.startswith("_")})

            # ---- ask: reasoning-based navigation + verified answer ----------------
            if head == "ask" and method == "POST":
                A.require(user, kb.config["query"]["min_role"])
                b = self._body()
                incl = bool(b.get("include_unpublished")) and reviewer and kb.config["query"]["unpublished_for_reviewers"]
                from .compiler import llm_config
                adm = user and user["role"] == "admin"
                cfg = llm_config(kb, b.get("backend") if adm else None, b.get("model") if adm else None)
                return self._json(app.asker.ask(user, b.get("question", ""), cfg, include_unpublished=incl))
            if head == "queries":
                A.require(user, "reader")
                if len(parts) == 1:
                    runs = app.compiler.runs(limit=int(q.get("limit", 100)), kind="query")
                    if not reviewer:
                        runs = [r for r in runs if r["by"] == user["name"]]
                    return self._json([{k: r.get(k) for k in ("id", "by", "started", "status", "question", "scope", "filed_as",
                                                               "grounding", "latency_s", "model")} for r in runs])
                run = app.compiler.trace(parts[1])["run"]
                if run.get("kind") != "query" or (not reviewer and run["by"] != user["name"]):
                    raise FileNotFoundError(parts[1])
                if method == "POST" and parts[2:3] == ["file"]:
                    A.require(user, "reviewer")
                    b = self._body()
                    return self._json(app.asker.file_back(user, parts[1], b.get("title", ""), b.get("parent", "")))
                paths = {s_["path"] for s_ in (run.get("navigation") or {}).get("sections", [])} | \
                    {e.get("path", "") for e in (run.get("answer") or {}).get("evidence", [])}
                return self._json({**run, "source_titles": S.doc_titles(kb, paths)})

            if head == "graph":
                return self._json(C.graph(visible_only=not (reviewer and q.get("all") == "1")))
            if head == "search":
                qq = q.get("q", "")
                res = {"cards": C.search(qq, visible_only=not reviewer), "sources": []}
                terms = [t for t in qq.lower().split() if t]
                if terms:
                    for p in S.list_md(kb):
                        text = (kb.sources / p).read_text("utf-8", errors="replace")
                        low = text.lower()
                        if all(t in low for t in terms):
                            i = low.find(terms[0])
                            line = text.count("\n", 0, i) + 1
                            res["sources"].append({"path": p, "line": line, "snippet": text[max(0, i - 80): i + 160]})
                            if len(res["sources"]) >= 50:
                                break
                return self._json(res)
            if head == "stats":
                idx = C.index()
                by_status, by_type = {}, {}
                for m in idx.values():
                    k = m["status"] if m.get("lifecycle", "active") == "active" else m["lifecycle"]
                    by_status[k] = by_status.get(k, 0) + 1
                    by_type[m["type"]] = by_type.get(m["type"], 0) + 1
                return self._json({"sources": len(S.list_md(kb)), "cards": len(idx),
                                   "published": sum(is_public(m) for m in idx.values()),
                                   "by_status": by_status if reviewer else {}, "by_type": by_type,
                                   "recent": sorted([{"id": m["id"], "title": m["title"], "summary": m.get("summary", ""),
                                                      "at": m.get("published_at", "")} for m in idx.values() if is_public(m)],
                                                    key=lambda x: x["at"], reverse=True)[:12]})

            # ---- reviewer+ ----------------------------------------------------------
            A.require(user, "reviewer")
            if head == "traces":
                if len(parts) == 1:
                    return self._json(app.compiler.runs(limit=int(q.get("limit", 200))))
                if parts[1] == "stats":
                    return self._json(app.compiler.stats())
                return self._json(app.compiler.trace(parts[1]))
            if head == "schema":
                if method == "GET" and len(parts) == 1:
                    return self._json({**SC.current(kb), "history": SC.history(kb)})
                if method == "GET" and parts[1:2] == ["v"]:
                    return self._json({"text": SC.version_text(kb, int(parts[2]))})
                if method == "GET" and parts[1:2] == ["diff"]:
                    return self._json({"diff": SC.diff(kb, int(q.get("a", 0)), int(q.get("b", 1)))})
                if method == "PUT":
                    A.require(user, "admin")
                    b = self._body()
                    return self._json(SC.save(kb, user["name"], b.get("text", ""), b.get("note", "")))
            if head == "consolidate" and parts[1:] == ["candidates"]:
                return self._json(app.consolidator.candidates())
            if head == "lint":
                return self._json(C.lint())
            if head == "events":
                return self._json(kb.events(limit=int(q.get("limit", 300)), target=q.get("target")))

            # ---- admin ------------------------------------------------------------
            A.require(user, "admin")
            if head == "compile":
                if method == "GET" and parts[1:] == ["plan"]:
                    return self._json({"paths": app.compiler.plan(None, only_changed=q.get("all") != "1"),
                                       "backend": kb.config["llm"]["backend"], "model": kb.config["llm"]["model"]})
                if method == "GET" and parts[1:] == ["jobs"]:
                    return self._json(sorted(app.compiler.jobs.values(), key=lambda j: j["at"], reverse=True))
                if method == "POST" and len(parts) == 1:
                    b = self._body()
                    paths = app.compiler.plan(b.get("paths") or None, only_changed=bool(b.get("only_changed", False)))
                    if not paths:
                        return self._json({"error": "nothing to compile"}, 400)
                    job = app.compiler.start(user["name"], paths, backend=b.get("backend") or None, model=b.get("model") or None,
                                             instructions=b.get("instructions", ""),
                                             files_per_call=int(b["files_per_call"]) if b.get("files_per_call") else None)
                    return self._json(job)
            if head == "users":
                if method == "GET":
                    return self._json([A.public(u) for u in A.load_users(kb).values()])
                b = self._body()
                if method == "POST":
                    return self._json(A.add_user(kb, user["name"], b["name"], b["password"], b.get("role", "reader"),
                                                 b.get("display", "")))
                if method == "PUT" and len(parts) == 2:
                    return self._json(A.update_user(kb, user["name"], parts[1], role=b.get("role"), active=b.get("active"),
                                                    password=b.get("password"), display=b.get("display")))
            raise HTTPError(404, f"no route {method} /api/{route}")

    return H


def serve(kb: KB, host: str = "127.0.0.1", port: int = 8765) -> None:
    app = App(kb)
    httpd = ThreadingHTTPServer((host, port), make_handler(app))
    httpd.daemon_threads = True
    print(f"LithoKB {__version__} serving {kb.root} on http://{host}:{port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
