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
from . import facets as F
from . import schema as SC
from . import sources as S
from .ask import Asker
from .cards import CardError, Cards, is_public, slug
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
        from .wiki import Wiki
        self.consolidator = Consolidator(kb, self.cards, self.compiler)
        self.wiki = Wiki(kb, self.cards)
        import threading
        # model-backed requests (questions) run concurrently up to this limit; beyond it the API answers 429
        self.llm_slots = threading.BoundedSemaphore(int(kb.config.get("query", {}).get("max_concurrent", 4)))

    def prewarm(self) -> dict:
        """Build every derived index once (card index, BM25 for both scopes, section index, unified trees,
        graphs) so that the first visitor does not pay for it. Safe to run in a background thread."""
        import time
        from . import graph as G
        from . import pageindex as PI
        t0 = time.perf_counter()
        out = {}
        for name, fn in (("cards", self.cards.index), ("bm25_readers", lambda: self.cards.text_index(True)),
                         ("bm25_reviewers", lambda: self.cards.text_index(False)), ("sections", lambda: PI.section_index(self.kb)),
                         ("tree_readers", lambda: PI.knowledge_tree(self.kb, self.cards, True)),
                         ("tree_reviewers", lambda: PI.knowledge_tree(self.kb, self.cards, False)),
                         ("graph_readers", lambda: G.build(self.kb, self.cards, True)),
                         ("graph_reviewers", lambda: G.build(self.kb, self.cards, False))):
            t = time.perf_counter()
            try:
                fn()
                out[name] = round((time.perf_counter() - t) * 1000, 1)
            except Exception as e:  # noqa: BLE001 — prewarming is best effort
                out[name] = f"failed: {type(e).__name__}: {e}"
        out["total_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        return out


def card_source_paths(meta: dict, body: str) -> set:
    """Every source document a card refers to: sources, evidence, and links in its body."""
    paths = {x["path"] for x in meta.get("sources", [])} | {e.get("path", "") for e in meta.get("evidence", [])}
    paths |= set(re.findall(r"\(src:([^)\s]+)\)", body))
    paths |= set(re.findall(r"\u8865\u5145\uff08\u6765\u81ea ([^\uff09\[\]]+?\.(?:md|markdown|mdx))\uff09", body))  # legacy Chinese heading
    paths |= set(re.findall(r"Addendum \(from ([^)\[\]]+?\.(?:md|markdown|mdx))\)", body))
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

        # ---- golden questions, ontology loop, topics (reviewers) ----------------------------------
        def _loop(self, method, head, parts, q, user):
            A.require(user, "reviewer")
            if head == "eval":
                from . import evalset as E
                if parts[1:2] == ["runs"] and len(parts) == 3:
                    return self._json(E.get_run(kb, parts[2]))
                if parts[1:2] == ["compare"]:
                    return self._json(E.compare(kb, q.get("a", ""), q.get("b", "")))
                if method == "PUT":
                    return self._json(E.upsert(kb, user["name"], self._body()))
                return self._json({"questions": E.load(kb), "runs": E.runs(kb)})
            if head == "ontology":
                from . import ontology as O
                from . import graph as G
                if len(parts) == 1:
                    o = G.ontology(kb)
                    return self._json({"proposals": O.proposals(kb),
                                       "current": {"entity_types": o["entity_types"], "type_defs": o["type_defs"],
                                                   "entity_relations": {k: {**v, "domain": sorted(v["domain"]), "range": sorted(v["range"])}
                                                                        for k, v in o["entity_relations"].items()}}})
                if parts[1] == "turtle":
                    return self._send(200, O.to_turtle(kb).encode(), "text/turtle; charset=utf-8")
                pid = parts[1]
                if method == "POST" and len(parts) == 3:
                    b = self._body()
                    loop = O.OntologyLoop(kb, app.compiler)
                    if parts[2] == "refine":
                        from .compiler import llm_config
                        run = loop.propose(user["name"], llm_config(kb, None, None), parent=pid, feedback=b.get("feedback", ""))
                        return self._json(run, 200 if run["status"] == "done" else 400)
                    return self._json(loop.decide(user, pid, parts[2], b.get("comment", "")))
                rec = O.get(kb, pid)
                rec["source_titles"] = S.doc_titles(kb, {e["path"] for x in rec["ontology"]["entity_types"] + rec["ontology"]["entity_relations"]
                                                         for e in x["evidence"]})
                return self._json(rec)
            if head == "topics":
                from . import topics as T
                return self._json({"status": T.status(kb), "topics": (T.load(kb) or {}).get("topics", [])})
            raise HTTPError(404, "not found")

        # ---- wiki / knowledge graph / page index -----------------------------------------
        def _knowledge(self, method, head, parts, q, user, reviewer):
            from . import graph as G
            from . import pageindex as PI
            readers = not (reviewer and q.get("view") == "head")
            W = app.wiki
            if head == "wiki":
                if len(parts) == 1:
                    return self._json(W.home(readers))
                cid = slug(parts[1])
                if len(parts) == 3 and parts[2] == "hub" and method == "POST":
                    A.require(user, "reviewer")
                    from .compiler import llm_config
                    run = W.write_hub(user, cid, llm_config(kb, None, None), app.compiler)
                    return self._json(run, 200 if run["status"] == "done" else 400)
                page = W.page(cid, readers)
                if page is None:
                    raise HTTPError(404, "no such page")
                return self._json(page)
            if head == "entities":
                if len(parts) == 1:
                    return self._json(W.entities(readers))
                e = W.entity("e:" + parts[1] if not parts[1].startswith("e:") else parts[1], readers)
                if e is None:
                    raise HTTPError(404, "no such entity")
                return self._json(e)
            if head == "kg":
                g = G.build(kb, app.cards, readers)
                op = parts[1] if len(parts) > 1 else "stats"
                layers = tuple(x for x in q.get("layers", "").split(",") if x) or None
                if op == "stats":
                    out = g.stats()
                    if reviewer:
                        out["findings"] = g.findings[:200]
                    return self._json(out)
                if op == "neighbors":
                    return self._json(g.neighbors(q.get("id", ""), int(q.get("depth", 1)), layers,
                                                  limit=min(500, int(q.get("limit", 100)))))
                if op == "path":
                    steps = g.path(q.get("a", ""), q.get("b", ""), layers=layers)
                    return self._json({"steps": steps, "text": G.explain_path(steps or [])})
                if op == "ego":
                    sub = g.subgraph([q.get("id", "")], int(q.get("depth", 1)), layers, limit=int(q.get("limit", 80)))
                    return self._json(sub)
                if op == "central":
                    pr = g.pagerank()
                    return self._json([{"id": c, "title": g.nodes[c]["title"], "score": round(v * len(pr), 3)}
                                       for c, v in sorted(pr.items(), key=lambda kv: -kv[1])[:int(q.get("limit", 30))]])
                if op == "communities":
                    comm = g.communities()
                    groups: dict = {}
                    for c, lab in comm.items():
                        groups.setdefault(lab, []).append({"id": c, "title": g.nodes[c]["title"]})
                    return self._json(sorted(groups.values(), key=len, reverse=True))
                raise HTTPError(404, "unknown graph query")
            if head == "pageindex":
                if parts[1:] == ["status"]:
                    A.require(user, "reviewer")
                    return self._json(PI.Indexer(kb, app.compiler).status())
                if parts[1:] == ["search"]:
                    hits = PI.section_index(kb).search(q.get("q", ""), int(q.get("limit", 20)))
                    meta = S.load_meta(kb)
                    out = []
                    for sc, key in hits:
                        pl = PI.section_index(kb).payload(key)
                        nd = PI.find(PI.doc_tree(kb, pl["path"], meta), pl["node"])
                        if nd:
                            out.append({"path": pl["path"], "node": pl["node"], "title": nd["title"], "start": nd["start"],
                                        "end": nd["end"], "summary": nd.get("summary") or nd.get("gist", ""), "score": sc})
                    return self._json({"sections": out, "source_titles": S.doc_titles(kb, {o["path"] for o in out})})
                tree = PI.knowledge_tree(kb, app.cards, readers)
                return self._json({"nodes": {k: {kk: vv for kk, vv in v.items() if kk not in ("aliases",)}
                                             for k, v in tree.nodes.items()}})
            raise HTTPError(404, "not found")

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
                    want = F.parse_filter(q.get("cond", ""))
                    if want:  # applicability filter: keep matching + general (no condition stated) cards
                        for row in rows:
                            row["applies"] = F.applies(F.ok(row.get("conditions", [])), want)
                        rows = [r for r in rows if r["applies"] != "no"]
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
                    from .issues import PUBLIC_KINDS, Issues
                    iss = Issues(kb).query(status="open", card=cid)
                    out["issues"] = iss if reviewer else [i for i in iss if i["kind"] in PUBLIC_KINDS]
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
                cond = F.parse_filter(b.get("cond", "")) if isinstance(b.get("cond", ""), str) else dict(b.get("cond") or {})
                question = str(b.get("question", "")).strip()
                if not question:
                    raise HTTPError(400, "empty question")
                use_cache = b.get("cache", True) is not False
                if use_cache:  # an exact earlier answer for the same knowledge-base state costs nothing
                    hit = app.asker.cached(app.asker.cache_key(question, cfg, incl, cond, None))
                    if hit:
                        kb.event(user["name"], "query.cache_hit", hit["id"], question=question[:300])
                        return self._json({**hit, "cached": True})
                if not app.llm_slots.acquire(blocking=False):
                    raise HTTPError(429, "the knowledge base is answering other questions — please retry in a moment")
                from .compiler import new_run_id
                rid = new_run_id()

                def work():
                    try:
                        app.asker.ask(user, question, cfg, include_unpublished=incl, conditions=cond, use_cache=use_cache,
                                      run_id=rid)
                    finally:
                        app.llm_slots.release()
                if b.get("async"):  # the UI polls /api/queries/<id> and shows the graph steps as they happen
                    import threading
                    threading.Thread(target=work, daemon=True, name=f"ask-{rid}").start()
                    return self._json({"id": rid, "status": "running"}, 202)
                work()
                return self._json(app.compiler.trace(rid)["run"])
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

            if head == "issues":
                from .issues import Issues, PUBLIC_KINDS
                reg = Issues(kb)
                if method == "POST" and len(parts) == 1:
                    A.require(user, "reader")
                    b = self._body()
                    kind = b.get("kind", "report")
                    if kind != "report":
                        A.require(user, "reviewer")
                    cid_ = slug(b.get("card", ""))
                    return self._json(reg.create(user["name"], kind, b.get("title", ""), b.get("detail", ""),
                                                 cards=[cid_] if cid_ else b.get("cards", []),
                                                 origin={"kind": "user", "role": user["role"]}))
                if method == "POST" and parts[2:3] == ["action"]:
                    A.require(user, "reader")
                    b = self._body()
                    return self._json(reg.act(user, parts[1], b.get("action", ""), b.get("comment", ""), b.get("resolution", "")))
                if method == "GET" and len(parts) == 1:
                    if reviewer:
                        return self._json({"items": reg.query(q.get("status") or None, q.get("kind") or None,
                                                              q.get("card") or None), "stats": reg.stats()})
                    A.require(user, "reader")  # readers: their own reports
                    return self._json({"items": reg.query(q.get("status") or None, by=user["name"]), "stats": {}})
                if method == "GET" and len(parts) == 2:
                    it = reg.get(parts[1])
                    if not reviewer and it.get("by") != (user or {}).get("name") and it["kind"] not in PUBLIC_KINDS:
                        raise FileNotFoundError(parts[1])
                    return self._json({**it, "source_titles": S.doc_titles(kb, it.get("sources", []))})

            if head in ("eval", "ontology", "topics"):
                return self._loop(method, head, parts, q, user)
            if head in ("wiki", "entities", "kg", "pageindex"):
                return self._knowledge(method, head, parts, q, user, reviewer)
            if head == "graph":
                g = C.graph(visible_only=not (reviewer and q.get("all") == "1"))
                want = F.parse_filter(q.get("cond", ""))
                if want:
                    idx = C.index()
                    keep = {n["id"] for n in g["nodes"] if F.applies(F.ok(idx[n["id"]].get("conditions", [])), want) != "no"}
                    for n in g["nodes"]:
                        n["applies"] = F.applies(F.ok(idx[n["id"]].get("conditions", [])), want)
                    g = {"nodes": [n for n in g["nodes"] if n["id"] in keep],
                         "edges": [e for e in g["edges"] if e["s"] in keep and e["t"] in keep]}
                return self._json(g)
            if head == "dims":
                return self._json(F.dims(kb))
            if head in ("timeline", "facts"):
                want = F.parse_filter(q.get("cond", ""))
                rows = []
                for m in C.index().values():
                    if not (reviewer and q.get("all") == "1") and not is_public(m):
                        continue
                    if m.get("lifecycle", "active") != "active" or F.applies(F.ok(m.get("conditions", [])), want) == "no":
                        continue
                    evs = {e["id"]: e for e in m.get("evidence", [])}
                    for it in F.ok(m.get("events" if head == "timeline" else "facts", [])):
                        e = evs.get(it.get("evidence"), {})
                        row = {**it, "card": m["id"], "card_title": m["title"], "card_type": m["type"],
                               "path": e.get("path", ""), "lines": e.get("found_lines") or e.get("lines", ""),
                               "quote": e.get("quote", ""), "check": e.get("check", "")}
                        if head == "timeline":
                            row["year"] = F.year_of(it.get("when", ""))
                        else:
                            row["card_conditions"] = F.ok(m.get("conditions", []))
                        rows.append(row)
                if head == "timeline":
                    rows.sort(key=lambda r: (r["year"] is None, r["year"] or 0, r["when"]))
                else:
                    rows.sort(key=lambda r: (r["name"].lower(), r["card_title"]))
                return self._json({"rows": rows, "source_titles": S.doc_titles(kb, {r["path"] for r in rows})})
            if head == "retrieve":
                from .retrieve import retrieve
                return self._json(retrieve(kb, C, q.get("q", ""), readers=not (reviewer and q.get("view") == "head"),
                                           conditions=F.parse_filter(q.get("cond", "")) or None, limit=int(q.get("limit", 8))))
            if head == "search":
                qq = q.get("q", "")
                res = {"cards": C.search(qq, visible_only=not reviewer), "sources": []}
                if qq.strip():  # ranked section search over the original documents (author-defined sections)
                    from . import pageindex as PI
                    bm, meta = PI.section_index(kb), S.load_meta(kb)
                    for sc, key in bm.search(qq, 30):
                        pl = bm.payload(key)
                        nd = PI.find(PI.doc_tree(kb, pl["path"], meta), pl["node"])
                        if nd:
                            res["sources"].append({"path": pl["path"], "line": nd["start"], "node": pl["node"],
                                                   "title": nd["title"], "end": nd["end"], "score": sc,
                                                   "snippet": nd.get("summary") or nd.get("gist", "")})
                    res["source_titles"] = S.doc_titles(kb, {x["path"] for x in res["sources"]})
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
            if head == "doctor":
                A.require(user, "reviewer")
                from .doctor import doctor
                return self._json(doctor(kb, C, app.compiler))
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
    import threading
    threading.Thread(target=lambda: print("prewarmed:", app.prewarm(), flush=True), daemon=True, name="prewarm").start()
    print(f"LithoKB {__version__} serving {kb.root} on http://{host}:{port}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
