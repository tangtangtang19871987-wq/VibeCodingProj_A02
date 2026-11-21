"""Headless CLI — every Web UI capability is available here (same code paths).

Identity: the CLI acts as `--user` (default: $LKB_USER). Whoever can run the CLI
on the data directory already has filesystem access, so the user is trusted to be
who they say; their role is still enforced by the same workflow rules.
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import sys

from . import auth as A
from . import sources as S
from .cards import Cards
from .compiler import Compiler
from .store import KB


def _kb(args) -> KB:
    kb = KB(args.root)
    if args.cmd != "init" and not kb.exists():
        sys.exit(f"no knowledge base at {kb.root} — run `lkb init` first (or set --root / LKB_ROOT)")
    return kb


def _me(kb: KB, args) -> dict:
    name = args.user or os.environ.get("LKB_USER")
    users = A.load_users(kb)
    if not name:
        admins = [u for u in users.values() if u["role"] == "admin" and u.get("active")]
        if len(admins) == 1:
            name = admins[0]["name"]
        else:
            sys.exit("specify --user (or LKB_USER)")
    u = users.get(name)
    if not u or not u.get("active"):
        sys.exit(f"unknown or disabled user {name}")
    return A.public(u)


def _out(obj, args) -> None:
    if args.json:
        print(json.dumps(obj, ensure_ascii=False, indent=1))
    elif isinstance(obj, list):
        for row in obj:
            print(row if isinstance(row, str) else "  ".join(str(row.get(k, "")) for k in row if not isinstance(row.get(k), (dict, list))))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if not str(k).startswith("_"):
                print(f"{k}: {v if not isinstance(v, (dict, list)) else json.dumps(v, ensure_ascii=False)}")
    else:
        print(obj)


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="lkb", description="LithoKB — computational lithography knowledge compiler")
    p.add_argument("--root", default=os.environ.get("LKB_ROOT", "./kbdata"), help="data directory")
    p.add_argument("--user", help="act as this user")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="create a knowledge base")
    s.add_argument("--admin", default="admin")
    s.add_argument("--password")

    s = sub.add_parser("user", help="manage users (admin)")
    s.add_argument("op", choices=["add", "list", "set"])
    s.add_argument("name", nargs="?")
    s.add_argument("--role", choices=A.ROLES)
    s.add_argument("--password")
    s.add_argument("--display")
    s.add_argument("--disable", action="store_true")
    s.add_argument("--enable", action="store_true")

    s = sub.add_parser("upload", help="upload a Markdown file or folder (Layer 0)")
    s.add_argument("path")
    s.add_argument("--prefix", default="", help="destination folder inside the KB")
    s.add_argument("--note", default="")

    s = sub.add_parser("sources", help="list / show / retire source documents")
    s.add_argument("op", choices=["tree", "ls", "show", "history", "retire"])
    s.add_argument("path", nargs="?")
    s.add_argument("--version", type=int)

    s = sub.add_parser("compile", help="compile sources into knowledge cards via the LLM")
    s.add_argument("paths", nargs="*", help="source paths (default: all changed)")
    s.add_argument("--all", action="store_true", help="recompile even unchanged sources")
    s.add_argument("--backend", choices=["mock", "anthropic", "openrouter", "command"])
    s.add_argument("--files-per-call", type=int)
    s.add_argument("--model", help="model id for the chosen backend (e.g. z-ai/glm-5.3-flash)")
    s.add_argument("--instructions", default="")
    s.add_argument("--dry-run", action="store_true", help="show plan and prompt size only")

    s = sub.add_parser("cards", help="list cards")
    s.add_argument("--status")

    s = sub.add_parser("show", help="show a card (head, or --rev N, or --published)")
    s.add_argument("id")
    s.add_argument("--rev", type=int)
    s.add_argument("--published", action="store_true")

    s = sub.add_parser("diff", help="diff two revisions of a card")
    s.add_argument("id")
    s.add_argument("a", type=int)
    s.add_argument("b", type=int)

    for verb in ("approve", "request_changes", "reject", "comment", "submit", "publish", "return",
                 "reopen", "withdraw", "restore", "supersede"):
        s = sub.add_parser(verb.replace("_", "-"), help=f"workflow: {verb}")
        s.add_argument("id")
        s.add_argument("-m", "--comment", default="")
        if verb == "supersede":
            s.add_argument("--by", required=True, help="replacement card id")

    s = sub.add_parser("reviews", help="review log of a card")
    s.add_argument("id")
    s = sub.add_parser("queue", help="review queue (in_review / approved / changes_requested)")
    s = sub.add_parser("traces", help="LLM runs: list, show one, or stats")
    s.add_argument("op", choices=["ls", "show", "stats"], nargs="?", default="ls")
    s.add_argument("run", nargs="?")
    s.add_argument("--part", choices=["system", "prompt", "response", "thinking", "parsed", "error"])
    s = sub.add_parser("ask", help="ask the knowledge base (navigate → read → answer with verified quotes)")
    s.add_argument("question", nargs="+")
    s.add_argument("--all", action="store_true", help="include unpublished cards (reviewer+)")
    s.add_argument("--backend", choices=["mock", "anthropic", "openrouter", "command"])
    s.add_argument("--model", help="model id for the chosen backend")
    s.add_argument("--file-back", metavar="TITLE", nargs="?", const="", help="file the answer as a synthesis card (reviewer+)")
    s = sub.add_parser("file-back", help="file an earlier query answer as a synthesis card (reviewer+)")
    s.add_argument("run")
    s.add_argument("--title", default="")
    s.add_argument("--parent", default="")
    s = sub.add_parser("queries", help="list past queries")
    s = sub.add_parser("schema", help="the domain schema that steers compilation")
    s.add_argument("op", choices=["show", "set", "history", "diff"], nargs="?", default="show")
    s.add_argument("file", nargs="?", help="for set: Markdown file with the new schema")
    s.add_argument("-m", "--note", default="")
    s.add_argument("--a", type=int, default=0)
    s.add_argument("--b", type=int)
    s = sub.add_parser("outline", help="show a document's table-of-contents tree (line ranges)")
    s.add_argument("path")
    s = sub.add_parser("search", help="search cards and sources")
    s.add_argument("q", nargs="+")
    s = sub.add_parser("lint", help="integrity report")
    s = sub.add_parser("reverify", help="re-run evidence verification on all cards (after verifier upgrades)")
    s = sub.add_parser("log", help="audit log")
    s.add_argument("--target")
    s.add_argument("--limit", type=int, default=50)
    s = sub.add_parser("export", help="regenerate compiled/index.md and graph.json")
    s = sub.add_parser("serve", help="start the Web UI")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8765)

    args = p.parse_args(argv)
    kb = _kb(args)
    cmd = args.cmd

    if cmd == "init":
        kb.init()
        if not A.load_users(kb):
            pw = args.password or os.environ.get("LKB_ADMIN_PASSWORD") or getpass.getpass("admin password: ")
            A.add_user(kb, "system", args.admin, pw, "admin")
        print(f"initialised {kb.root}")
        return
    if cmd == "serve":
        from .server import serve
        return serve(kb, args.host, args.port)

    me = _me(kb, args)
    cards = Cards(kb)
    comp = Compiler(kb, cards)

    if cmd == "user":
        A.require(me, "admin")
        if args.op == "list":
            return _out([{k: u[k] for k in ("name", "role", "active", "display")} for u in A.load_users(kb).values()], args)
        if args.op == "add":
            pw = args.password or getpass.getpass(f"password for {args.name}: ")
            return _out(A.add_user(kb, me["name"], args.name, pw, args.role or "reader", args.display or ""), args)
        active = True if args.enable else (False if args.disable else None)
        return _out(A.update_user(kb, me["name"], args.name, role=args.role, active=active,
                                  password=args.password, display=args.display), args)
    if cmd == "upload":
        A.require(me, "reviewer")
        res = S.put_dir(kb, me["name"], args.path, prefix=args.prefix, note=args.note)
        return _out([f"{r['status']:9s} v{r.get('version', '-')}  {r['path']}" + (f"  ({r['reason']})" if r.get("reason") else "")
                     for r in res] if not args.json else res, args)
    if cmd == "sources":
        if args.op == "tree":
            def walk(n, d=0):
                for ch in n["children"]:
                    tag = "/" if ch["type"] == "dir" else ""
                    print("  " * d + f"{ch['name']}{tag}" + (f"  — {ch.get('title')}" if ch.get("title") and ch["type"] == "file" else ""))
                    if ch["type"] == "dir":
                        walk(ch, d + 1)
            return walk(S.tree(kb)) if not args.json else _out(S.tree(kb), args)
        if args.op == "ls":
            meta = S.load_meta(kb)
            return _out([{"path": k, "v": v["version"], "by": v["by"], "at": v["at"], "sha": v["sha256"][:10]}
                         for k, v in sorted(meta.items()) if not v.get("deleted")], args)
        if args.op == "show":
            return print(S.read_text(kb, args.path, args.version))
        if args.op == "history":
            return _out(S.load_meta(kb)[S.clean_path(args.path)]["history"], args)
        if args.op == "retire":
            A.require(me, "admin")
            return S.remove(kb, me["name"], args.path)
    if cmd == "compile":
        A.require(me, "admin")
        paths = comp.plan(args.paths or None, only_changed=not args.all and not args.paths)
        if not paths:
            return print("nothing to compile (all sources unchanged; use --all to force)")
        if args.dry_run:
            from .compiler import build_prompt
            sysp, user, rel, _ = build_prompt(kb, cards, comp.work_units(paths[:1])[0])
            return _out({"plan": paths, "first_call_prompt_chars": len(sysp) + len(user), "related_cards": rel}, args)
        job = comp.start(me["name"], paths, backend=args.backend, model=args.model, instructions=args.instructions,
                         background=False, files_per_call=args.files_per_call)
        for rid in job["runs"]:
            r = comp.trace(rid)["run"]
            print(f"[{r['status']}] {rid}  {', '.join(r['sources'])}  model={r.get('model')}  "
                  f"latency={r.get('latency_s')}s  cards={len(r.get('written', []))}  "
                  f"grounding={r.get('grounding', {}).get('score')}  findings={len(r.get('findings', []))}"
                  + (f"  ERROR {r['error']}" if r.get("error") else ""))
        return
    if cmd == "cards":
        A.require(me, "reader")
        return _out([{"id": m["id"], "status": m["status"], "life": m.get("lifecycle"), "rev": m["rev"],
                      "pub": m.get("published_rev") or "-", "type": m["type"], "title": m["title"]}
                     for m in cards.listing(status=args.status)], args)
    if cmd == "show":
        from . import fm
        if args.rev or args.published:
            head, _ = cards.load(args.id)
            rev = args.rev or head.get("published_rev")
            if not rev:
                sys.exit("not published")
            return print(fm.dump(*cards.load_rev(args.id, rev)))
        return print(fm.dump(*cards.load(args.id)))
    if cmd == "diff":
        return print(cards.diff(args.id, args.a, args.b))
    if cmd.replace("-", "_") in ("approve", "request_changes", "reject", "comment", "submit", "publish", "return",
                                 "reopen", "withdraw", "restore", "supersede"):
        action = cmd.replace("-", "_")
        m = cards.act(me, args.id, action, args.comment, getattr(args, "by", "") or "")
        if action in ("publish", "withdraw", "restore", "supersede"):
            cards.write_exports()
        return print(f"{args.id}: r{m['rev']} status={m['status']} lifecycle={m.get('lifecycle')} published_rev={m.get('published_rev')}")
    if cmd == "reviews":
        return _out(cards.reviews(args.id), args)
    if cmd == "queue":
        A.require(me, "reviewer")
        rows = [m for m in cards.listing() if m["status"] in ("in_review", "approved", "changes_requested", "draft")]
        return _out([{"status": m["status"], "id": m["id"], "rev": m["rev"], "grounding": m.get("grounding", {}).get("score"),
                      "title": m["title"]} for m in rows], args)
    if cmd == "traces":
        A.require(me, "reviewer")
        if args.op == "stats":
            return _out(comp.stats(), args)
        if args.op == "show":
            t = comp.trace(args.run)
            if args.part:
                key = {"parsed": "parsed.json", "error": "error.txt"}.get(args.part, f"{args.part}.md")
                return print(t.get(key, ""))
            return _out(t["run"], args)
        return _out([{"id": r["id"], "status": r["status"], "model": r.get("model"), "latency": r.get("latency_s"),
                      "cards": len(r.get("written", [])), "grounding": r.get("grounding", {}).get("score"),
                      "sources": ",".join(r["sources"])} for r in comp.runs()], args)
    if cmd == "ask":
        from .ask import Asker
        A.require(me, kb.config["query"]["min_role"])
        from .compiler import llm_config
        cfg = llm_config(kb, args.backend, args.model)
        run = Asker(kb, cards, comp).ask(me, " ".join(args.question), cfg,
                                         include_unpublished=args.all and A.RANK[me["role"]] >= 2)
        if args.json:
            return _out(run, args)
        if run["status"] != "done":
            sys.exit(f"query failed: {run.get('error')}  (trace {run['id']})")
        nav, ans = run["navigation"], run["answer"]
        print(f"# 阅读计划  {nav['reasoning']}")
        print("  卡片: " + (", ".join(nav["cards"]) or "—"))
        for s_ in nav["sections"]:
            print(f"  章节: {s_['path']} {s_['node']} [L{s_['lines']}] {s_['title']}")
        print("\n" + ans["answer_md"] + "\n")
        for e in ans["evidence"]:
            print(f"  [{e['id']}] {e['check']:9s} {e['path']}:L{e.get('found_lines') or e['lines']}  “{e['quote'][:80]}”")
        if ans.get("gaps"):
            print(f"\n缺口: {ans['gaps']}")
        print(f"\ntrace {run['id']} · grounding {run['grounding']['score']} · {run.get('latency_s')}s")
        if args.file_back is not None:
            A.require(me, "reviewer")
            h = Asker(kb, cards, comp).file_back(me, run["id"], args.file_back)
            print(f"filed as {h['id']} r{h['rev']} ({h['status']})")
        return
    if cmd == "file-back":
        from .ask import Asker
        A.require(me, "reviewer")
        h = Asker(kb, cards, comp).file_back(me, args.run, args.title, args.parent)
        return print(f"filed as {h['id']} r{h['rev']} ({h['status']})")
    if cmd == "queries":
        rows = comp.runs(kind="query")
        if A.RANK[me["role"]] < 2:
            rows = [r for r in rows if r["by"] == me["name"]]
        return _out([{"id": r["id"], "by": r["by"], "status": r["status"], "filed": r.get("filed_as") or "-",
                      "question": r["question"][:60]} for r in rows], args)
    if cmd == "schema":
        from . import schema as SC
        if args.op == "show":
            return print(SC.current(kb)["text"])
        if args.op == "history":
            return _out(SC.history(kb), args)
        if args.op == "diff":
            return print(SC.diff(kb, args.a, args.b or SC.current(kb)["version"]))
        A.require(me, "admin")
        if not args.file:
            sys.exit("schema set FILE")
        e = SC.save(kb, me["name"], open(args.file, encoding="utf-8").read(), args.note)
        return print(f"schema v{e['version']} ({e['sha']})")
    if cmd == "outline":
        from . import doctree
        meta = S.load_meta(kb).get(S.clean_path(args.path))
        if not meta:
            sys.exit(f"no source {args.path}")
        tree = doctree.build(S.read_text(kb, args.path), meta["sha256"])
        return _out(tree, args) if args.json else print(doctree.outline(tree) or "(no headings)")
    if cmd == "search":
        return _out(cards.search(" ".join(args.q), visible_only=A.RANK[me["role"]] < 2), args)
    if cmd == "reverify":
        A.require(me, "admin")
        return _out(cards.reverify(me["name"]), args)
    if cmd == "lint":
        issues = cards.lint()
        _out(issues if issues else ["no issues"], args)
        return
    if cmd == "log":
        return _out(kb.events(limit=args.limit, target=args.target), args)
    if cmd == "export":
        cards.write_exports()
        return print("wrote compiled/index.md and compiled/graph.json")


def run(argv=None) -> None:
    from .cards import CardError
    try:
        main(argv)
    except (CardError, S.SourceError, A.AuthError, PermissionError, ValueError, FileNotFoundError, KeyError) as e:
        sys.exit(f"error: {e}")


if __name__ == "__main__":
    run()
