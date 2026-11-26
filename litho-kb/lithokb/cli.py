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
import re
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
    s.add_argument("op", choices=["tree", "ls", "show", "history", "retire", "reconvert"])
    s.add_argument("path", nargs="?")
    s.add_argument("--version", type=int)
    s.add_argument("--apply", action="store_true", help="reconvert: write the new renditions (default: dry run)")

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

    s = sub.add_parser("risk", help="review risk + granularity of one card, or a summary of the queue")
    s.add_argument("id", nargs="?")
    s = sub.add_parser("batch-approve", help="batch-approve LOW-risk cards in review (comment required)")
    s.add_argument("ids", nargs="*", help="card ids (default with --low-risk: all low-risk cards in review)")
    s.add_argument("--low-risk", action="store_true")
    s.add_argument("--limit", type=int)
    s.add_argument("-m", "--comment", required=True)
    s = sub.add_parser("batch-publish", help="batch-publish approved cards (admin, comment required)")
    s.add_argument("ids", nargs="*")
    s.add_argument("--all-approved", action="store_true")
    s.add_argument("-m", "--comment", required=True)
    s = sub.add_parser("consolidate", help="rewrite / split over-grown cards (LLM; result goes to review)")
    s.add_argument("ids", nargs="*")
    s.add_argument("--auto", action="store_true", help="all cards flagged by the granularity policy")
    s.add_argument("--list", action="store_true", help="only list candidates")
    s.add_argument("--from-rev", type=int, help="consolidate from an earlier revision of the card")
    s.add_argument("--limit", type=int)
    s.add_argument("--backend", choices=["mock", "anthropic", "openrouter", "command"])
    s.add_argument("--model")
    s = sub.add_parser("annotate", help="add facets (conditions / events / facts) to cards from their own evidence (LLM)")
    s.add_argument("ids", nargs="*")
    s.add_argument("--auto", action="store_true", help="all cards without facets")
    s.add_argument("--unsupported", action="store_true", help="re-annotate cards with facets their quotes do not support")
    s.add_argument("--limit", type=int)
    s.add_argument("--backend", choices=["mock", "anthropic", "openrouter", "command"])
    s.add_argument("--model")
    s = sub.add_parser("policy", help="set how a source document is processed: compile | reference | exclude | auto")
    s.add_argument("path")
    s.add_argument("policy", nargs="?", choices=["compile", "reference", "exclude", "auto"])
    s.add_argument("-m", "--note", default="")
    s = sub.add_parser("issues", help="issue register: contradictions, open questions, gaps, reports")
    s.add_argument("--status", choices=["open", "resolved", "wontfix"])
    s.add_argument("--kind", choices=["contradiction", "open_question", "gap", "report"])
    s.add_argument("--card")
    s = sub.add_parser("issue", help="show / act on one issue")
    s.add_argument("id")
    s.add_argument("action", nargs="?", choices=["comment", "resolve", "wontfix", "reopen"])
    s.add_argument("-m", "--comment", default="")
    s = sub.add_parser("report", help="report a problem on a card (any user)")
    s.add_argument("card")
    s.add_argument("title")
    s.add_argument("-m", "--detail", default="")
    s = sub.add_parser("merge", help="fold a (thin) card into another card; the source is superseded (admin)")
    s.add_argument("id")
    s.add_argument("--into", required=True)
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
    s.add_argument("--cond", default="", help="applicability conditions, e.g. wavelength:EUV,node:5nm")
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
    s = sub.add_parser("retrieve", help="model-free context pack for a question: cards, sections, entity facts, themes")
    s.add_argument("question", nargs="+")
    s.add_argument("--cond", default="")
    s.add_argument("--limit", type=int, default=8)
    s = sub.add_parser("lint", help="integrity report")
    s = sub.add_parser("reverify", help="re-run evidence verification on all cards (after verifier upgrades)")
    s = sub.add_parser("log", help="audit log")
    s.add_argument("--target")
    s.add_argument("--limit", type=int, default=50)
    s = sub.add_parser("export", help="regenerate compiled/index.md and graph.json")
    s = sub.add_parser("index", help="PageIndex: compile node summaries + entities for changed documents (LLM, incremental)")
    s.add_argument("paths", nargs="*")
    s.add_argument("--status", action="store_true")
    s.add_argument("--force", action="store_true")
    s.add_argument("--backend")
    s.add_argument("--model")
    s = sub.add_parser("tree", help="the unified knowledge tree (wiki topics + documents → sections) as the navigator sees it")
    s.add_argument("--budget", type=int, default=12000)
    s.add_argument("--open", nargs="*", default=[], help="node ids to expand (e.g. a card id or d:<path>)")
    s = sub.add_parser("wiki", help="wiki: home | page ID | entities | entity ID | hubs [--auto|ID] | gaps | export")
    s.add_argument("op", choices=["home", "page", "entities", "entity", "hubs", "gaps", "export"])
    s.add_argument("id", nargs="?")
    s.add_argument("--auto", action="store_true")
    s.add_argument("--backend")
    s.add_argument("--model")
    s = sub.add_parser("kg", help="knowledge graph: stats | neighbors ID | path A B | central | communities | findings")
    s.add_argument("op", choices=["stats", "neighbors", "path", "central", "communities", "findings"])
    s.add_argument("ids", nargs="*")
    s.add_argument("--depth", type=int, default=1)
    s.add_argument("--layers", default="")
    s = sub.add_parser("bench", help="performance benchmark on a synthetic knowledge base (does not touch --root)")
    s.add_argument("--cards", type=int, default=2000)
    s.add_argument("--docs", type=int, default=400)
    s = sub.add_parser("extract", help="entity graph: extract instances + typed relations per document, guided by the approved ontology")
    s.add_argument("paths", nargs="*")
    s.add_argument("--status", action="store_true")
    s.add_argument("--force", action="store_true")
    s.add_argument("--limit", type=int, default=0, help="pilot on the first N pending documents")
    s.add_argument("--backend")
    s.add_argument("--model")
    s = sub.add_parser("ontology", help="ontology loop: propose [--from PID --feedback TXT] | list | show PID | approve|reject|comment PID -m TXT | export | import FILE")
    s.add_argument("op", choices=["propose", "list", "show", "approve", "reject", "comment", "export", "import"])
    s.add_argument("pid", nargs="?")
    s.add_argument("-m", "--comment", default="")
    s.add_argument("--from", dest="from_pid")
    s.add_argument("--feedback", default="")
    s.add_argument("--backend")
    s.add_argument("--model")
    s = sub.add_parser("topics", help="topic graph over source sections: status | build | show")
    s.add_argument("op", choices=["status", "build", "show"])
    s.add_argument("--backend")
    s.add_argument("--model")
    s = sub.add_parser("eval", help="golden questions + evaluation runs: list | import FILE | export | run | runs | show RUN | compare A B")
    s.add_argument("op", choices=["list", "import", "export", "run", "runs", "show", "compare"])
    s.add_argument("args", nargs="*")
    s.add_argument("--ids", default="", help="comma-separated question ids (run)")
    s.add_argument("--all-cards", action="store_true", help="include unpublished cards (reviewer+)")
    s.add_argument("--features", default="", help="ablation switches, e.g. themes=0,facts=0,expand_facts=0,complete=0")
    s.add_argument("--repeat", type=int, default=1, help="ask every question N times; report mean and min–max")
    s.add_argument("--label", default="")
    s.add_argument("--backend")
    s.add_argument("--model")
    s = sub.add_parser("doctor", help="health check: configuration, ontology, derived structures, backlog, evaluation, files")
    s = sub.add_parser("refresh", help="bring PageIndex summaries, topic graph and entity graph up to date (dry run unless --apply)")
    s.add_argument("--apply", action="store_true")
    s.add_argument("--limit", type=int, default=0, help="entity extraction: at most N documents")
    s.add_argument("--backend")
    s.add_argument("--model")
    s = sub.add_parser("fsck", help="integrity check of the files (heads vs revisions, reviews, traces, caches)")
    s.add_argument("--repair", action="store_true", help="rebuild derived caches; never touches knowledge files")
    s = sub.add_parser("mcp", help="run the MCP server on stdio (tools for agents; acts as --user)")
    s = sub.add_parser("serve", help="start the Web UI")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8765)

    args = p.parse_args(argv)
    if args.cmd == "bench":
        from .bench import run_bench
        return _out(run_bench(args.cards, args.docs), args)
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
    if cmd == "mcp":
        from .mcp import Server
        return Server(kb, me).serve()
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
        if args.op == "reconvert":
            if args.apply:
                A.require(me, "admin")
            res = S.reconvert(kb, me["name"], apply=args.apply)
            if args.json:
                return _out(res, args)
            ch = [r for r in res if r["changed"]]
            for r in ch:
                print(f"  {'updated' if args.apply else 'would change'}  {r['markdown']}  {r['lines_before']} → {r['lines_after']} lines  ({r['converter_was']} → {r['converter']})")
            return print(f"{len(ch)} of {len(res)} HTML renditions {'updated' if args.apply else 'would change (dry run; --apply to write)'}")
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
                     for m in cards.listing(status=args.status, visible_only=A.RANK[me["role"]] < 2)], args)
    if cmd == "show":
        from . import fm
        if A.RANK[me["role"]] < 2:  # readers: the published revision only (same rule as the Web UI)
            head, _ = cards.load(args.id)
            if not head.get("published_rev") or head.get("lifecycle", "active") != "active" or args.rev:
                sys.exit("not published" if not args.rev else "readers can only see the published revision")
            return print(fm.dump(*cards.load_rev(args.id, head["published_rev"])))
        if args.rev or args.published:
            head, _ = cards.load(args.id)
            rev = args.rev or head.get("published_rev")
            if not rev:
                sys.exit("not published")
            return print(fm.dump(*cards.load_rev(args.id, rev)))
        return print(fm.dump(*cards.load(args.id)))
    if cmd == "diff":
        A.require(me, "reviewer")
        return print(cards.diff(args.id, args.a, args.b))
    if cmd.replace("-", "_") in ("approve", "request_changes", "reject", "comment", "submit", "publish", "return",
                                 "reopen", "withdraw", "restore", "supersede"):
        action = cmd.replace("-", "_")
        m = cards.act(me, args.id, action, args.comment, getattr(args, "by", "") or "")
        if action in ("publish", "withdraw", "restore", "supersede"):
            cards.write_exports()
        return print(f"{args.id}: r{m['rev']} status={m['status']} lifecycle={m.get('lifecycle')} published_rev={m.get('published_rev')}")
    if cmd == "risk":
        A.require(me, "reviewer")
        if args.id:
            return _out(cards.risk(args.id), args)
        from collections import Counter
        rows = [(m["id"], cards.risk(m["id"])) for m in cards.listing(status="in_review")]
        print("in review by risk:", dict(Counter(r["level"] for _, r in rows)))
        reasons = Counter(re.split(r" \(|\uff08", x)[0] for _, r in rows for x in r["reasons"])
        for k, v in reasons.most_common(12):
            print(f"  {v:>3}  {k}")
        return
    if cmd in ("batch-approve", "batch-publish"):
        action = "approve" if cmd == "batch-approve" else "publish"
        ids = list(args.ids)
        if action == "approve" and args.low_risk and not ids:
            ids = [m["id"] for m in cards.listing(status="in_review") if cards.risk(m["id"])["level"] == "low"]
            ids = ids[:args.limit] if args.limit else ids
        if action == "publish" and args.all_approved and not ids:
            ids = [m["id"] for m in cards.listing(status="approved")]
        res = cards.batch(me, ids, action, args.comment)
        if args.json:
            return _out(res, args)
        print(f"{res['batch']}: {action} {len(res['done'])} card(s); skipped {len(res['skipped'])}")
        for x in res["skipped"]:
            print(f"  skipped {x['id']}: {x['reason']}")
        return
    if cmd == "consolidate":
        from .compiler import llm_config
        from .consolidate import Consolidator
        A.require(me, "reviewer")
        con = Consolidator(kb, cards, comp)
        cands = con.candidates()
        if args.list or (not args.ids and not args.auto):
            return _out([{"id": c["id"], "units": c["units"], "min": c["minutes"], "appends": c["appends"],
                          "evidence": c["evidence"], "issues": ",".join(c["issues"])} for c in cands], args)
        ids = args.ids or [c["id"] for c in cands][: args.limit or None]
        for cid in ids:
            r = con.run(me, cid, llm_config(kb, args.backend, args.model), from_rev=args.from_rev)
            print(f"[{r['status']}] {cid}: {r.get('before', {}).get('units')} → {r.get('after', {}).get('units')} units; "
                  f"written {[(w['id'], w['action']) for w in r['written']]}" + (f"  ERROR {r['error']}" if r.get("error") else ""))
        return
    if cmd in ("issues", "issue", "report"):
        from .issues import Issues
        reg = Issues(kb)
        if cmd == "issues":
            A.require(me, "reviewer")
            return _out([{"id": i["id"], "kind": i["kind"], "status": i["status"], "seen": i.get("seen", 1),
                          "cards": ",".join(i["cards"]), "title": i["title"][:70]}
                         for i in reg.query(args.status, args.kind, args.card)], args)
        if cmd == "report":
            return _out(reg.create(me["name"], "report", args.title, args.detail, cards=[args.card],
                                   origin={"kind": "user", "role": me["role"]}), args)
        if not args.action:
            return _out(reg.get(args.id), args)
        return _out(reg.act(me, args.id, args.action, args.comment), args)
    if cmd == "annotate":
        from .annotate import Annotator
        from .compiler import llm_config
        A.require(me, "reviewer")
        an = Annotator(kb, cards, comp)
        ids = args.ids or (an.candidates()[: args.limit or None] if args.auto else
                           an.unsupported()[: args.limit or None] if args.unsupported else [])
        if not ids:
            return print(f"{len(an.candidates())} card(s) without facets; pass ids or --auto")
        for cid in ids:
            r = an.run(me, cid, llm_config(kb, args.backend, args.model))
            print(f"[{r['status']}] {cid}: {r.get('facets', {})}" + (" → new revision" if r["written"] else " (no change)")
                  + (f"  ERROR {r['error']}" if r.get("error") else ""), flush=True)
        return
    if cmd == "policy":
        if not args.policy:
            return _out(S.policy_of(kb, S.clean_path(args.path)), args)
        A.require(me, "admin")
        return _out(S.set_policy(kb, me["name"], args.path, args.policy, args.note), args)
    if cmd == "merge":
        from .consolidate import merge
        h = merge(cards, me, args.id, args.into)
        cards.write_exports()
        return print(f"merged {args.id} into {args.into}: r{h['rev']} ({h['status']}); {args.id} superseded")
    if cmd == "reviews":
        A.require(me, "reviewer")
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
        from . import facets as F
        run = Asker(kb, cards, comp).ask(me, " ".join(args.question), cfg,
                                         include_unpublished=args.all and A.RANK[me["role"]] >= 2,
                                         conditions=F.parse_filter(args.cond) or None)
        if args.json:
            return _out(run, args)
        if run["status"] != "done":
            sys.exit(f"query failed: {run.get('error')}  (trace {run['id']})")
        nav, ans = run["navigation"], run["answer"]
        print(f"# Reading plan  {nav['reasoning']}")
        print("  Cards: " + (", ".join(nav["cards"]) or "—"))
        for s_ in nav["sections"]:
            print(f"  Sections: {s_['path']} {s_['node']} [L{s_['lines']}] {s_['title']}")
        print("\n" + ans["answer_md"] + "\n")
        for e in ans["evidence"]:
            print(f"  [{e['id']}] {e['check']:9s} {e['path']}:L{e.get('found_lines') or e['lines']}  “{e['quote'][:80]}”")
        if ans.get("gaps"):
            print(f"\nGaps: {ans['gaps']}")
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
    if cmd == "retrieve":
        from .retrieve import retrieve
        from . import facets as F
        r = retrieve(kb, cards, " ".join(args.question), readers=A.RANK[me["role"]] < 2,
                     conditions=F.parse_filter(args.cond) or None, limit=args.limit)
        if args.json:
            return _out(r, args)
        print("# cards"); [print(f"  {c['id']}  {c['title']} — {c['summary'][:90]}") for c in r["cards"]]
        print("# sections"); [print(f"  {s_['path']} L{s_['start']}-{s_['end']}  {s_['section']} — {s_['summary'][:80]}") for s_ in r["sections"]]
        print("# facts"); [print(f"  {f.get('relation') or f.get('instance')}  ({f['path']} L{f['lines']})") for f in r["facts"]]
        print("# themes"); [print(f"  {t['title']} ({t['sections']} sections)") for t in r["themes"]]
        return
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
        from .wiki import Wiki
        w = Wiki(kb, cards).export()
        return print(f"wrote compiled/index.md, compiled/graph.json and compiled/wiki/ ({w['pages']} pages, {w['entities']} entities)")
    if cmd == "index":
        from . import pageindex as PI
        from .compiler import llm_config
        ix = PI.Indexer(kb, Compiler(kb, cards))
        if args.status:
            return _out(ix.status(), args)
        A.require(me, "admin")
        return _out(ix.run(me["name"], llm_config(kb, args.backend, args.model), args.paths or None, args.force), args)
    if cmd == "tree":
        from . import pageindex as PI
        readers = A.RANK[me["role"]] < 2
        t = PI.knowledge_tree(kb, cards, readers)
        H = PI.Handles(t)
        txt, _ = t.render(t.roots(), H, args.budget)
        print(txt)
        for nid in args.open:
            nid = nid if nid in t.nodes else next((k for k in t.nodes if k.endswith(nid)), None)
            if nid:
                print("\n" + t.render([nid], H, args.budget)[0])
        return
    if cmd == "wiki":
        from .wiki import Wiki
        from .compiler import llm_config
        W = Wiki(kb, cards)
        readers = A.RANK[me["role"]] < 2
        if args.op == "home":
            return _out(W.home(readers), args)
        if args.op == "page":
            return _out(W.page(args.id, readers) or f"no page {args.id}", args)
        if args.op == "entities":
            return _out(W.entities(readers), args)
        if args.op == "entity":
            return _out(W.entity(args.id if args.id.startswith("e:") else "e:" + args.id, readers) or "no such entity", args)
        if args.op == "gaps":
            return _out(W.hub_gaps(readers), args)
        if args.op == "export":
            return _out(W.export(), args)
        A.require(me, "reviewer")
        ids = W.hub_candidates() if args.auto else [args.id]
        if not ids or ids == [None]:
            return print("no topic needs an overview (or pass an id)")
        comp = Compiler(kb, cards)
        cfg = llm_config(kb, args.backend, args.model)
        return _out([{k: r.get(k) for k in ("id", "card", "status", "error", "findings", "written", "cost_usd")}
                     for r in (W.write_hub(me, i, cfg, comp) for i in ids)], args)
    if cmd == "kg":
        from . import graph as G
        g = G.build(kb, cards, A.RANK[me["role"]] < 2)
        layers = tuple(x for x in args.layers.split(",") if x) or None
        if args.op == "stats":
            return _out(g.stats(), args)
        if args.op == "findings":
            return _out(g.findings or ["no findings"], args)
        if args.op == "neighbors":
            return _out(g.neighbors(args.ids[0], args.depth, layers), args)
        if args.op == "path":
            steps = g.path(args.ids[0], args.ids[1], layers=layers)
            return print(G.explain_path(steps) if steps else "no path") if not args.json else _out(steps, args)
        if args.op == "central":
            pr = g.pagerank()
            return _out([{"id": c, "title": g.nodes[c]["title"], "score": round(v * len(pr), 3)}
                         for c, v in sorted(pr.items(), key=lambda kv: -kv[1])[:30]], args)
        if args.op == "communities":
            comm = g.communities()
            groups: dict = {}
            for c, lab in comm.items():
                groups.setdefault(lab, []).append(c)
            return _out(sorted(groups.values(), key=len, reverse=True), args)
    if cmd == "extract":
        from .entities import Extractor
        ex = Extractor(kb, Compiler(kb, cards))
        if args.status:
            return _out(ex.status(), args)
        A.require(me, "admin")
        from .compiler import llm_config
        return _out(ex.run(me["name"], llm_config(kb, args.backend, args.model), args.paths or None, args.force, args.limit), args)
    if cmd == "ontology":
        from . import ontology as O
        if args.op == "list":
            return _out(O.proposals(kb), args)
        if args.op == "show":
            r = O.get(kb, args.pid)
            if args.json:
                return _out(r, args)
            print(f"{r['id']}  {r['status']}  by {r['by']}  {r['summary']}")
            for t in r["ontology"]["entity_types"]:
                ok = sum(e.get("check") in ("exact", "moved", "elided") for e in t["evidence"])
                print(f"  type {t['id']:<24} {t['label']} — {t['definition']}  [evidence {ok}/{len(t['evidence'])}] q={','.join(t['questions'])}")
            for x in r["ontology"]["entity_relations"]:
                ok = sum(e.get("check") in ("exact", "moved", "elided") for e in x["evidence"])
                print(f"  rel  {x['id']:<24} {'|'.join(x['domain'])} → {'|'.join(x['range'])} — {x['definition']}  [evidence {ok}/{len(x['evidence'])}]")
            for u in r["ontology"].get("uncovered", []):
                print(f"  uncovered {u.get('question')}: {u.get('why')}")
            return print("checks:", json.dumps(r["checks"], ensure_ascii=False))
        if args.op == "export":
            return print(O.to_turtle(kb), end="")
        A.require(me, "reviewer")
        loop = O.OntologyLoop(kb, Compiler(kb, cards))
        if args.op == "import":
            return _out(O.from_turtle(kb, me["name"], open(args.pid, encoding="utf-8").read())["summary"], args)
        if args.op == "propose":
            from .compiler import llm_config
            run = loop.propose(me["name"], llm_config(kb, args.backend, args.model), parent=args.from_pid, feedback=args.feedback)
            return _out({k: run.get(k) for k in ("status", "proposal", "summary", "error", "cost_usd", "id")}, args)
        r = loop.decide(me, args.pid, args.op, args.comment)
        return print(f"{r['id']}: {r['status']}" + (f" → SCHEMA v{r['schema_version']}" if r.get("schema_version") else ""))
    if cmd == "topics":
        from . import topics as T
        if args.op == "status":
            return _out(T.status(kb), args)
        if args.op == "show":
            t = T.load(kb) or {"topics": []}
            if args.json:
                return _out(t, args)
            meta = S.meta_ro(kb)
            for x in t["topics"]:
                print(("    " if x["parent"] else "") + f"{x['id']}  {x['title']}  ({len(x['members'])} sections) — {x['summary']}")
                if x["parent"] or not any(y["parent"] == x["id"] for y in t["topics"]):
                    for m in x["representative"]:
                        p_, nid = m[2:].split("#")
                        from . import pageindex as PI
                        nd = PI.find(PI.doc_tree(kb, p_, meta), nid)
                        print(("    " if x["parent"] else "") + f"      ★ {p_} · {nd['title'] if nd else nid}")
            return print(f"coverage {t.get('coverage')}  unassigned {len(t.get('unassigned', []))}")
        A.require(me, "admin")
        from .compiler import llm_config
        return _out(T.TopicBuilder(kb, Compiler(kb, cards)).build(me["name"], llm_config(kb, args.backend, args.model)), args)
    if cmd == "eval":
        from . import evalset as E
        if args.op == "list":
            return _out(E.load(kb), args)
        if args.op == "export":
            return print("".join(json.dumps(q, ensure_ascii=False) + "\n" for q in E.load(kb)), end="")
        if args.op == "runs":
            return _out(E.runs(kb), args)
        if args.op == "show":
            return _out(E.get_run(kb, args.args[0]), args)
        if args.op == "compare":
            return _out(E.compare(kb, args.args[0], args.args[1]), args)
        A.require(me, "reviewer")
        if args.op == "import":
            raw = open(args.args[0], encoding="utf-8").read().strip()
            qs = json.loads(raw) if raw.startswith("[") else [json.loads(x) for x in raw.splitlines() if x.strip()]
            return print(f"saved {len(E.save_all(kb, me['name'], qs))} questions to eval/golden.jsonl")
        from .ask import Asker
        from .compiler import llm_config
        rec = E.run_eval(kb, Asker(kb, cards, comp), cards, me, llm_config(kb, args.backend, args.model),
                         ids=[x for x in args.ids.split(",") if x] or None,
                         include_unpublished=args.all_cards and A.RANK[me["role"]] >= 2, label=args.label,
                         features={k: v not in ("0", "false", "off") for k, v in
                                   (x.split("=", 1) for x in args.features.split(",") if "=" in x)} or None,
                         repeat=args.repeat)
        if args.json:
            return _out(rec, args)
        print(f"{rec['id']}  {rec['label']}  scope={rec['scope']}  {rec['config']}")
        print("aggregate:", json.dumps(rec["aggregate"], ensure_ascii=False))
        print("spread (min–max over repeats):", json.dumps(rec["spread"], ensure_ascii=False))
        for q in rec["questions"]:
            print(f"  {q['id']} docs={q['doc_recall']} secs={q['section_recall']} keypts={q['key_points']} "
                  f"grnd={q['grounding']} gap={'Y' if q['gap_reported'] else '-'}  missed={q['key_points_missed']}")
        return
    if cmd == "doctor":
        from .doctor import doctor
        r = doctor(kb, cards, Compiler(kb, cards))
        if args.json:
            return _out(r, args)
        mark = {"ok": "ok   ", "info": "info ", "warn": "WARN ", "error": "ERROR"}
        for f in r["findings"]:
            print(f"{mark[f['level']]} {f['area']:<11} {f['message']}" + (f"   → {f['fix']}" if f["fix"] else ""))
        print(f"status: {r['status']}  ({r['seconds']} s)")
        if r["status"] == "error":
            sys.exit(1)
        return
    if cmd == "refresh":
        from .doctor import refresh
        from .compiler import llm_config
        if args.apply:
            A.require(me, "admin")
        return _out(refresh(kb, cards, Compiler(kb, cards), me["name"], llm_config(kb, args.backend, args.model),
                            apply=args.apply, limit=args.limit), args)
    if cmd == "fsck":
        from .fsck import fsck
        return _out(fsck(kb, cards, repair=args.repair), args)


def run(argv=None) -> None:
    from .cards import CardError
    try:
        main(argv)
    except (CardError, S.SourceError, A.AuthError, PermissionError, ValueError, FileNotFoundError, KeyError) as e:
        sys.exit(f"error: {e}")


if __name__ == "__main__":
    run()
