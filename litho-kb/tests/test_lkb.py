"""End-to-end checks (stdlib unittest, offline: uses the mock LLM backend).

    python3 -m unittest discover -s litho-kb/tests -v
"""
import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from lithokb import auth as A  # noqa: E402
from lithokb import fm  # noqa: E402
from lithokb import sources as S  # noqa: E402
from lithokb.cards import CardError, Cards, is_public  # noqa: E402
from lithokb.compiler import Compiler, parse_response, validate  # noqa: E402
from lithokb.server import App, make_handler  # noqa: E402
from lithokb.store import KB  # noqa: E402

EXAMPLES = ROOT / "examples" / "litho-docs"


def fresh_kb():
    d = tempfile.mkdtemp(prefix="lkb-test-")
    kb = KB(d)
    kb.init()
    A.add_user(kb, "system", "admin", "pw-admin", "admin")
    A.add_user(kb, "system", "rev", "pw-rev", "reviewer")
    A.add_user(kb, "system", "rev2", "pw-rev2", "reviewer")
    A.add_user(kb, "system", "bob", "pw-bob", "reader")
    return kb


def user(kb, name):
    return A.public(A.load_users(kb)[name])


class TestFrontmatter(unittest.TestCase):
    def test_roundtrip_and_handwritten(self):
        meta = {"id": "x", "evidence": [{"quote": "a: b \"c\""}], "n": None, "t": "中文"}
        m2, body, _ = fm.split(fm.dump(meta, "# body\n"))
        self.assertEqual(m2, meta)
        self.assertEqual(body, "# body\n")
        m3, _, off = fm.split("---\ntitle: Hello: world\nweight: 2\ntags:\n  - a\n  - b\n---\ntext")
        self.assertEqual(m3, {"title": "Hello: world", "weight": 2, "tags": ["a", "b"]})
        self.assertEqual(off, 7)


class TestSources(unittest.TestCase):
    def setUp(self):
        self.kb = fresh_kb()

    def tearDown(self):
        shutil.rmtree(self.kb.root)

    def test_upload_versions_provenance_and_tree(self):
        res = S.put_dir(self.kb, "rev", str(EXAMPLES))
        self.assertTrue(all(r["status"] == "added" for r in res))
        self.assertEqual(S.put_dir(self.kb, "rev", str(EXAMPLES))[0]["status"], "unchanged")
        S.put(self.kb, "admin", [{"path": "opc/ilt.md", "text": "# ILT v2\n"}])
        meta = S.load_meta(self.kb)["opc/ilt.md"]
        self.assertEqual((meta["version"], meta["by"], meta["first_by"]), (2, "admin", "rev"))
        self.assertIn("逆向光刻", S.read_text(self.kb, "opc/ilt.md", version=1))  # old bytes kept
        self.assertEqual(S.read_text(self.kb, "opc/ilt.md"), "# ILT v2\n")
        tree = S.tree(self.kb)
        imaging = next(c for c in tree["children"] if c["name"] == "imaging")
        names = [c["name"] for c in imaging["children"]]
        self.assertEqual(names[:3], ["README.md", "hopkins.md", "resist.md"])  # index-file order respected
        top = [c["name"] for c in tree["children"]]
        self.assertEqual(top[:3], ["README.md", "imaging", "opc"])
        self.assertEqual(top[-1], "glossary.md")  # weight: 99

    def test_path_safety(self):
        for bad in ("../x.md", "/etc/../../x.md", ".git/config.md", "a/../../b.md"):
            with self.assertRaises(S.SourceError):
                S.clean_path(bad)


class TestWorkflow(unittest.TestCase):
    def setUp(self):
        self.kb = fresh_kb()
        S.put_dir(self.kb, "rev", str(EXAMPLES))
        self.cards = Cards(self.kb)
        self.comp = Compiler(self.kb, self.cards)
        job = self.comp.start("admin", self.comp.plan(None), backend="mock", background=False)
        self.runs = job["runs"]
        self.cid = next(c for c in self.cards.index() if "tcc" in c)

    def tearDown(self):
        shutil.rmtree(self.kb.root)

    def test_compile_traces_and_incremental_plan(self):
        self.assertEqual(len(self.runs), 8)
        t = self.comp.trace(self.runs[0])
        for part in ("system.md", "prompt.md", "response.md", "thinking.md", "parsed.json"):
            self.assertIn(part, t)
        self.assertIn("    1|", t["prompt.md"])  # whole document, line-numbered
        self.assertEqual(self.comp.plan(None), [])  # nothing changed
        S.put(self.kb, "rev", [{"path": "imaging/hopkins.md", "text": S.read_text(self.kb, "imaging/hopkins.md") + "\n更多内容。\n"}])
        self.assertEqual(self.comp.plan(None), ["imaging/hopkins.md"])
        self.assertIn("imaging/hopkins.md", self.cards.index()[self.cid]["stale_sources"])
        # recompiling sends the existing derived cards back to the model for update
        self.assertIn(self.cid, self.comp.trace(self.comp.run_once("admin", ["imaging/hopkins.md"],
                                                                       {**self.kb.config["llm"], "backend": "mock"})["id"])["run"]["context"]["related_cards"])
        self.assertEqual(self.cards.load(self.cid)[0]["rev"], 2)

    def test_full_lifecycle_and_permissions(self):
        admin, rev, rev2, bob = (user(self.kb, n) for n in ("admin", "rev", "rev2", "bob"))
        c = self.cid
        with self.assertRaises(PermissionError):
            self.cards.act(bob, c, "approve")
        with self.assertRaises(CardError):
            self.cards.act(admin, c, "publish")  # not approved yet
        with self.assertRaises(PermissionError):
            self.cards.act(rev, c, "publish")
        self.cards.act(rev, c, "request_changes", "E1 引用不完整")
        self.assertEqual(self.cards.load(c)[0]["status"], "changes_requested")
        # human edit → new revision, back in review, votes reset
        m = self.cards.human_edit(rev, c, {"summary": "TCC 是四维核函数。", "change_note": "fix"})
        self.assertEqual((m["rev"], m["status"]), (2, "in_review"))
        with self.assertRaises(CardError):
            self.cards.act(rev, c, "approve")  # self-approval blocked
        self.cards.act(rev2, c, "approve", "ok")
        self.assertEqual(self.cards.load(c)[0]["status"], "approved")
        self.cards.act(admin, c, "publish")
        head = self.cards.load(c)[0]
        self.assertTrue(is_public(head))
        self.assertEqual(head["published_rev"], 2)
        # new revision of a published card: old one stays visible
        self.cards.human_edit(rev2, c, {"body": "new body [E1]"})
        head = self.cards.load(c)[0]
        self.assertEqual((head["rev"], head["published_rev"], head["status"]), (3, 2, "in_review"))
        self.assertTrue(is_public(head))
        self.cards.act(admin, c, "return", "打回")
        self.assertEqual(self.cards.load(c)[0]["status"], "changes_requested")
        self.cards.act(admin, c, "withdraw", "下架")
        self.assertFalse(is_public(self.cards.load(c)[0]))
        self.cards.act(admin, c, "restore")
        other = next(x for x in self.cards.index() if x != c)
        self.cards.act(admin, c, "supersede", target=other)
        h = self.cards.load(c)[0]
        self.assertEqual((h["lifecycle"], h["replaced_by"]), ("superseded", other))
        kinds = [r["verdict"] for r in self.cards.reviews(c)]
        self.assertEqual(kinds, ["request_changes", "approve", "publish", "return", "withdraw", "restore", "supersede"])
        diff = self.cards.diff(c, 1, 2)
        self.assertIn('+summary: "TCC 是四维核函数。"', diff)
        self.assertIn("-summary:", diff)

    def test_evidence_grounding(self):
        good = {"cards": [{"id": "hopkins-imaging-model", "title": "Hopkins", "type": "model", "parent": "",
                           "summary": "s", "body_md": "x [E1] y [E2] z [E3] [E4]", "relations": [{"rel": "uses", "target": "nope"}],
                           "evidence": [
                               {"id": "E1", "path": "imaging/hopkins.md", "lines": "3-3", "quote": "Hopkins 公式是计算光刻中描述部分相干照明成像的标准模型。"},
                               {"id": "E2", "path": "imaging/hopkins.md", "lines": "1-1", "quote": "典型做法保留 10 到 30 个核"},  # wrong lines
                               {"id": "E3", "path": "imaging/hopkins.md", "lines": "3-3", "quote": "Hopkins 模型是唯一正确的模型"},  # invented
                               {"id": "E4", "path": "nowhere.md", "lines": "1", "quote": "x"}]}]}
        norm, findings = validate(self.cards, good, ["imaging/hopkins.md"])
        msgs = " ".join(f["msg"] for f in findings)
        self.assertIn("does not exist", msgs)
        self.assertIn("not a source of this run", msgs)
        body = norm[0].pop("body")
        norm[0].pop("change_note"), norm[0].pop("exists")
        m = self.cards.new_revision("admin", norm[0], body, {"kind": "llm", "run": "t"})
        checks = [e["check"] for e in m["evidence"]]
        self.assertEqual(checks[0], "exact")
        self.assertEqual(checks[1], "moved")
        self.assertIn(checks[2], ("missing", "fuzzy"))
        self.assertEqual(checks[3], "no_source")
        self.assertLess(m["grounding"]["score"], 0.75)

    def test_parse_response_tolerates_prose(self):
        d = parse_response('Here you go:\n```json\n{"cards": [], "notes": "n"}\n```\n')
        self.assertEqual(d["notes"], "n")
        self.assertEqual(parse_response('{"cards": []}')["cards"], [])


class TestHTTP(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kb = fresh_kb()
        S.put_dir(cls.kb, "rev", str(EXAMPLES))
        cls.app = App(cls.kb)
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(cls.app))
        cls.base = f"http://127.0.0.1:{cls.httpd.server_port}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        shutil.rmtree(cls.kb.root)

    def call(self, method, path, body=None, token=None):
        req = urllib.request.Request(self.base + path, method=method,
                                     data=json.dumps(body).encode() if body is not None else None)
        req.add_header("Content-Type", "application/json")
        if token:
            req.add_header("Authorization", "Bearer " + token)
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read() or b"null")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"null")

    def login(self, n, p):
        return self.call("POST", "/api/login", {"name": n, "password": p})[1]["token"]

    def test_end_to_end_over_http(self):
        self.assertEqual(self.call("POST", "/api/login", {"name": "admin", "password": "bad"})[0], 400)
        adm, rev, bob = self.login("admin", "pw-admin"), self.login("rev", "pw-rev"), self.login("bob", "pw-bob")
        self.assertEqual(self.call("POST", "/api/compile", {"paths": ["opc/ilt.md"]}, rev)[0], 403)
        st, job = self.call("POST", "/api/compile", {"paths": ["opc/ilt.md"], "backend": "mock"}, adm)
        self.assertEqual(st, 200)
        for _ in range(100):
            jobs = self.call("GET", "/api/compile/jobs", token=adm)[1]
            if jobs[0]["status"] == "done":
                break
            threading.Event().wait(0.05)
        cards = self.call("GET", "/api/cards", token=rev)[1]
        self.assertTrue(cards)
        self.assertEqual(self.call("GET", "/api/cards", token=bob)[1], [])  # nothing published yet
        cid = cards[0]["id"]
        self.assertEqual(self.call("GET", f"/api/cards/{cid}", token=bob)[0], 404)
        self.assertEqual(self.call("POST", f"/api/cards/{cid}/action", {"action": "approve"}, bob)[0], 403)
        self.assertEqual(self.call("POST", f"/api/cards/{cid}/action", {"action": "approve", "comment": "ok"}, rev)[0], 200)
        self.assertEqual(self.call("POST", f"/api/cards/{cid}/action", {"action": "publish"}, adm)[0], 200)
        st, d = self.call("GET", f"/api/cards/{cid}", token=bob)
        self.assertEqual((st, d["published"]["rev"]), (200, 1))
        self.assertNotIn("review_log", d)  # readers do not see review internals
        self.assertEqual(self.call("GET", "/api/traces", token=bob)[0], 403)
        runs = self.call("GET", "/api/traces", token=rev)[1]
        self.assertIn("prompt.md", self.call("GET", f"/api/traces/{runs[0]['id']}", token=rev)[1])
        st, up = self.call("POST", "/api/sources/upload", {"files": [{"path": "new/a.md", "text": "# A\n[b](../opc/ilt.md)"},
                                                                     {"path": "new/x.exe", "b64": base64.b64encode(b"MZ").decode()}]}, rev)
        self.assertEqual([r["status"] for r in up["results"]], ["added", "skipped"])
        self.assertEqual(self.call("POST", "/api/sources/upload", {"files": [{"path": "../evil.md", "text": "x"}]}, rev)[0], 400)
        f = self.call("GET", "/api/sources/file?path=new/a.md")[1]
        self.assertEqual(f["meta"]["by"], "rev")
        self.assertTrue(self.call("GET", "/api/search?q=ILT")[1]["sources"])
        self.assertEqual(self.call("GET", "/api/graph")[0], 200)
        # demoting a user takes effect immediately on existing tokens
        self.call("PUT", "/api/users/rev", {"role": "reader"}, adm)
        self.assertEqual(self.call("GET", "/api/traces", token=rev)[0], 403)
        self.assertEqual(self.call("PUT", "/api/users/admin", {"role": "reader"}, adm)[0], 400)  # last admin protected
        with urllib.request.urlopen(self.base + "/") as r:
            self.assertIn(b"LithoKB", r.read())


class TestHTTPFusion(TestHTTP):
    def test_end_to_end_over_http(self):  # parent's test runs in TestHTTP only
        pass

    def test_ask_schema_outline_endpoints(self):
        adm, bob = self.login("admin", "pw-admin"), self.login("bob", "pw-bob")
        self.assertEqual(self.call("POST", "/api/ask", {"question": "OPC"})[0], 403)  # anonymous
        st, run = self.call("POST", "/api/ask", {"question": "ILT 与 OPC", "include_unpublished": True}, bob)
        self.assertEqual((st, run["status"], run["scope"]), (200, "done", "published"))  # readers can't widen scope
        self.assertEqual(self.call("POST", f"/api/queries/{run['id']}/file", {}, bob)[0], 403)
        self.assertEqual(self.call("GET", f"/api/queries/{run['id']}", token=bob)[0], 200)
        self.assertEqual(self.call("GET", "/api/schema", token=bob)[0], 403)
        st, sc = self.call("GET", "/api/schema", token=adm)
        self.assertEqual(st, 200)
        self.assertEqual(self.call("PUT", "/api/schema", {"text": sc["text"] + "\nx\n", "note": "t"}, adm)[1]["version"], sc["version"] + 1)
        f = self.call("GET", "/api/sources/file?path=imaging/hopkins.md")[1]
        self.assertEqual([n["title"] for n in f["tree"]["nodes"]], ["Hopkins 部分相干成像"])


class TestCLI(unittest.TestCase):
    def test_headless_flow(self):
        d = tempfile.mkdtemp(prefix="lkb-cli-")
        env = {**os.environ, "LKB_ROOT": d, "LKB_ADMIN_PASSWORD": "x"}
        run = lambda *a: subprocess.run([sys.executable, str(ROOT / "lkb"), *a], env=env, capture_output=True, text=True)
        try:
            self.assertEqual(run("init").returncode, 0)
            self.assertEqual(run("upload", str(EXAMPLES)).returncode, 0)
            self.assertIn("[done]", run("compile", "--backend", "mock").stdout)
            cid = json.loads(run("--json", "cards").stdout)[0]["id"]
            self.assertEqual(run("user", "add", "r", "--role", "reviewer", "--password", "p").returncode, 0)
            self.assertIn("approved", run("--user", "r", "approve", cid, "-m", "ok").stdout)
            self.assertIn("published", run("publish", cid).stdout)
            self.assertIn("error:", run("publish", cid).stderr)  # clean error, no traceback
            self.assertIn(cid, Path(d, "compiled", "index.md").read_text("utf-8"))
            self.assertEqual(run("traces", "stats").returncode, 0)
        finally:
            shutil.rmtree(d)


if __name__ == "__main__":
    unittest.main()


# ---------------------------------------------------------------------------------
# Fusion features: PageIndex doc trees, OpenKB summary layer, LLM-Wiki schema / query
# compounding / log, epistemic labels.
from lithokb import doctree  # noqa: E402
from lithokb import schema as SC  # noqa: E402
from lithokb.ask import Asker  # noqa: E402
from lithokb.cards import summary_id  # noqa: E402
from lithokb.compiler import normalize_relation  # noqa: E402

LONG_DOC = "# SMO\n\nSMO 同时优化光源与掩模。\n\n" + "".join(
    f"## 第{i}节\n\n第{i}节：光源像素化与掩模联合求解。{'补充。' * 40}\n\n```\n# not a heading {i}\n```\n\n" for i in range(1, 7))


class TestDocTree(unittest.TestCase):
    def test_tree_and_sections(self):
        t = doctree.build("---\ntitle: T\n---\nintro line\n# A\n\ntext a.\n\n## A1\n\n```\n# code\n```\nx\n# B\ny\n")
        self.assertEqual(t["title"], "T")
        titles = [(n["id"], n["title"], n["start"], n["end"]) for n in t["nodes"]]
        self.assertEqual(titles[0][1], "(preamble)")  # text before first heading stays reachable
        a = next(n for n in t["nodes"] if n["title"] == "A")
        self.assertEqual([c["title"] for c in a["children"]], ["A1"])  # '# code' inside fence ignored
        self.assertEqual(a["gist"], "text a.")
        self.assertIn("[L", doctree.outline(t))
        big = doctree.build(LONG_DOC)
        secs = doctree.sections(big, 500)
        self.assertGreater(len(secs), 2)
        self.assertEqual(secs[0][0], 1)
        self.assertEqual(secs[-1][1], big["lines"])
        for (a1, b1, _), (a2, _, _) in zip(secs, secs[1:]):
            self.assertEqual(b1 + 1, a2)  # contiguous, complete coverage along the outline
        self.assertEqual(len(doctree.sections(big, 10 ** 9)), 1)


class TestFusion(unittest.TestCase):
    def setUp(self):
        self.kb = fresh_kb()
        S.put_dir(self.kb, "rev", str(EXAMPLES))
        self.cards = Cards(self.kb)
        self.comp = Compiler(self.kb, self.cards)
        self.comp.start("admin", self.comp.plan(None), backend="mock", background=False)

    def tearDown(self):
        shutil.rmtree(self.kb.root)

    def test_summary_layer_and_epistemic_labels(self):
        idx = self.cards.index()
        for p in S.list_md(self.kb):
            self.assertIn(summary_id(p), idx)
            self.assertEqual(idx[summary_id(p)]["type"], "summary")
        rels = [r for m in idx.values() for r in m["relations"]]
        self.assertTrue(rels and all(r["basis"] in ("extracted", "inferred", "ambiguous") for r in rels))
        self.assertTrue(any(r["rel"] == "covers" for r in rels))
        f = []
        self.assertEqual(normalize_relation({"rel": "uses", "target": "X", "basis": "extracted"}, "c", set(), f)["basis"], "inferred")
        self.assertEqual(normalize_relation({"rel": "uses", "target": "X", "basis": "extracted", "evidence": "E1"}, "c", {"E1"}, f)["basis"], "extracted")
        self.assertEqual(normalize_relation({"rel": "zzz", "target": "X", "basis": "ambiguous"}, "c", set(), f)["rel"], "related_to")
        self.assertTrue(any("ambiguous" in x["msg"] for x in f))
        self.cards.write_exports()
        index_md = (self.kb.root / "compiled" / "index.md").read_text("utf-8")
        self.assertIn("## Source documents", index_md)
        self.assertIn("**compile**", (self.kb.root / "compiled" / "log.md").read_text("utf-8"))

    def test_schema_versioned_and_traced(self):
        self.assertEqual(SC.current(self.kb)["version"], 1)
        e = SC.save(self.kb, "admin", SC.current(self.kb)["text"] + "\n## extra rule\n", "add rule")
        self.assertEqual(e["version"], 2)
        self.assertEqual(SC.save(self.kb, "admin", SC.current(self.kb)["text"], "noop")["version"], 2)  # unchanged → no new version
        self.assertIn("+## extra rule", SC.diff(self.kb, 1, 2))
        run = self.comp.run_once("admin", ["opc/ilt.md"], {**self.kb.config["llm"], "backend": "mock"})
        self.assertEqual(run["schema"]["version"], 2)
        t = self.comp.trace(run["id"])
        self.assertIn("extra rule", t["system.md"])
        self.assertIn('<outline path="opc/ilt.md">', t["prompt.md"])

    def test_long_document_compiled_along_outline(self):
        cfg = json.loads((self.kb.root / "config.json").read_text())
        cfg["compile"] = {"files_per_call": 1, "max_doc_chars": 700}
        (self.kb.root / "config.json").write_text(json.dumps(cfg))
        S.put(self.kb, "rev", [{"path": "smo/long.md", "text": LONG_DOC}])
        job = self.comp.start("admin", ["smo/long.md"], backend="mock", background=False)
        runs = [self.comp.trace(r)["run"] for r in job["runs"]]
        self.assertGreater(len(runs), 1)
        self.assertTrue(all(r["status"] == "done" and r["sections"] for r in runs))
        self.assertEqual(runs[0]["source_complete"], [])
        self.assertEqual(runs[-1]["source_complete"], ["smo/long.md"])
        self.assertIn('section="1/', self.comp.trace(runs[0]["id"])["prompt.md"])
        # later sections see the cards produced by earlier ones (they are "related")
        self.assertTrue(runs[-1]["context"]["related_cards"])
        self.assertEqual(self.comp.plan(["smo/long.md"]), [])
        self.assertEqual(self.cards.load(summary_id("smo/long.md"))[0]["rev"], len(runs))

    def test_ask_navigate_answer_and_file_back(self):
        admin, rev, bob = (user(self.kb, n) for n in ("admin", "rev", "bob"))
        asker = Asker(self.kb, self.cards, self.comp)
        cfg = {**self.kb.config["llm"], "backend": "mock"}
        # readers see published knowledge only: nothing published yet → no cards read
        r0 = asker.ask(bob, "Hopkins 模型的局限", cfg)
        self.assertEqual(r0["navigation"]["cards"], [])
        self.assertTrue(r0["navigation"]["sections"])  # but source ToCs are navigable
        r = asker.ask(rev, "Hopkins 模型的局限", cfg, include_unpublished=True)
        self.assertEqual(r["status"], "done")
        self.assertTrue(r["navigation"]["cards"])
        self.assertTrue(all(e["check"] == "exact" for e in r["answer"]["evidence"]))
        t = self.comp.trace(r["id"])
        for part in ("nav-prompt.md", "nav-response.md", "ans-prompt.md", "ans-response.md"):
            self.assertIn(part, t)
        self.assertIn("<card-index>", t["nav-prompt.md"])
        self.assertEqual(len(t["run"]["calls"]), 2)
        with self.assertRaises(PermissionError):
            from lithokb.auth import require
            require(bob, "reviewer")
        h = asker.file_back(rev, r["id"], "Hopkins limitations")
        self.assertEqual((h["type"], h["status"], h["origin"]["kind"]), ("synthesis", "in_review", "query"))
        self.assertTrue(all(e["check"] == "exact" for e in h["evidence"]))
        with self.assertRaises(ValueError):
            asker.file_back(rev, r["id"])  # only once
        # the filed answer then follows the normal governance path
        self.cards.act(user(self.kb, "rev2"), h["id"], "approve")
        self.cards.act(admin, h["id"], "publish")
        self.assertTrue(is_public(self.cards.load(h["id"])[0]))
        self.assertEqual(self.comp.runs(kind="query")[0]["filed_as"], h["id"])


class TestHTMLIngest(unittest.TestCase):
    PAGE = """<!doctype html><html><head><title>OPC 章节 - 某课程网站</title><style>h1{color:red}</style>
<script>alert(1)</script></head><body><header><h1><i class="fa fa-x"></i> OPC 章节</h1></header>
<section><h2>一、概述</h2><p>OPC 通过修改<strong>掩模图形</strong>补偿失真。<i class="icon"></i></p>
<ol><li>涂胶：均匀涂覆。</li><li>曝光</li></ol>
<table><tr><th>节点</th><th>波长</th></tr><tr><td>ArF</td><td>193nm | 浸没</td></tr></table>
<svg><rect/><text>初始掩模</text><text>EPE计算</text></svg>
<pre>for i in range(3):
    step()</pre>
<a href="ch2.html#sec"><div><h3>下一章</h3><p>卡片式链接</p></div></a> <p>见 <a href="ch2.html">第二章</a></p></section>
<footer>公众号: xxx</footer></body></html>"""

    def setUp(self):
        self.kb = fresh_kb()

    def tearDown(self):
        shutil.rmtree(self.kb.root)

    def test_convert(self):
        from lithokb.html2md import convert
        md = convert(self.PAGE, source_name="ch1.html")
        meta, body, _ = fm.split(md)
        self.assertEqual(meta["title"], "OPC 章节")  # h1 preferred over <title> with site suffix
        self.assertEqual(meta["html_title"], "OPC 章节 - 某课程网站")
        self.assertNotIn("alert", md)
        self.assertNotIn("color:red", md)
        self.assertIn("## 一、概述", body)
        self.assertIn("OPC 通过修改**掩模图形**补偿失真。", body)
        self.assertIn("1. 涂胶：均匀涂覆。\n2. 曝光", body)
        self.assertIn("| ArF | 193nm \\| 浸没 |", body)
        self.assertIn("> 图示文字：初始掩模 · EPE计算", body)
        self.assertIn("```\nfor i in range(3):\n    step()\n```", body)
        self.assertIn("### [下一章](ch2.md#sec)", body)  # block-level card link → linked heading
        self.assertIn("[第二章](ch2.md)", body)
        self.assertNotIn("**\n", body)

    def test_ingest_keeps_original_and_derives_markdown(self):
        res = S.put(self.kb, "rev", [{"path": "course/ch1.html", "text": self.PAGE}])
        self.assertEqual(res[0]["derived"]["path"], "course/ch1.md")
        meta = S.load_meta(self.kb)
        self.assertEqual(meta["course/ch1.md"]["derived_from"], "course/ch1.html")
        self.assertEqual(S.read_text(self.kb, "course/ch1.html"), self.PAGE)  # original verbatim
        self.assertIn("course/ch1.md", S.list_md(self.kb))
        names = [c["name"] for c in S.tree(self.kb)["children"][0]["children"]]
        self.assertEqual(names, ["ch1.md"])  # the HTML original is reachable from its rendition, not duplicated in nav
        again = S.put(self.kb, "rev", [{"path": "course/ch1.html", "text": self.PAGE}])
        self.assertEqual((again[0]["status"], again[0]["derived"]["status"]), ("unchanged", "unchanged"))
        S.put(self.kb, "rev", [{"path": "course/ch1.html", "text": self.PAGE.replace("曝光", "曝光与显影")}])
        self.assertEqual(S.load_meta(self.kb)["course/ch1.md"]["version"], 2)
        # an authored Markdown file is never overwritten by a conversion
        S.put(self.kb, "rev", [{"path": "course/ch3.md", "text": "# authored\n"}])
        r = S.put(self.kb, "rev", [{"path": "course/ch3.html", "text": self.PAGE}])
        self.assertIn("authored", r[0]["note"])
        self.assertEqual(S.read_text(self.kb, "course/ch3.md"), "# authored\n")


class TestGroundingRealCases(unittest.TestCase):
    """Cases observed when compiling real course material with a cheap LLM."""

    def setUp(self):
        self.kb = fresh_kb()
        S.put(self.kb, "rev", [{"path": "d.md", "text": (
            "# ILT\n\n而ILT是**逆向求解**：直接计算出*最优或近似最优的掩模图形*。\n\n"
            "- **解析梯度：**通过光刻模型的解析表达式求导，计算精确但复杂\n"
            "- **数值梯度：**通过有限差分法近似计算，简单但计算量大\n\n"
            "**核心价值：**利用物理模型进行“预失真”补偿。\n\n"
            "| 维度 | 规则型 | 模型型 |\n|---|---|---|\n| 灵活性 | 低 | 高，可处理任意二维图形 |\n| 计算成本 | 低 | 高，需要大量仿真迭代 |\n")}])

    def tearDown(self):
        shutil.rmtree(self.kb.root)

    def check(self, quote, lines):
        from lithokb.cards import verify_evidence
        return verify_evidence(self.kb, {"id": "E1", "path": "d.md", "lines": lines, "quote": quote})["check"]

    def test_cases(self):
        self.assertEqual(self.check("而ILT是逆向求解：直接计算出最优或近似最优的掩模图形。", "3"), "exact")  # markers removed, not spaced (CJK)
        self.assertEqual(self.check('**核心价值：** 利用物理模型进行"预失真"补偿。', "8"), "exact")  # curly vs straight quotes, width
        self.assertEqual(self.check("**解析梯度：**通过光刻模型的解析表达式求导…", "5"), "elided")  # trailing ellipsis
        self.assertEqual(self.check("**解析梯度：**通过光刻模型的解析表达式求导\n**数值梯度：**通过有限差分法近似计算", "5-6"), "elided")
        self.assertEqual(self.check("- **解析梯度：**通过光刻模型的解析表达式求导，计算精确但复杂\n- **数值梯度：**通过有限差分法近似计算，简单但计算量大", "5-6"), "exact")
        self.assertEqual(self.check("## ILT — 而ILT是逆向求解", "1-3"), "elided")  # quoted from the outline view
        self.assertEqual(self.check("而ILT是逆向求解", "1"), "moved")
        self.assertIn(self.check("高，可处理任意二维图形 | 高，需要大量仿真迭代", "12-13"), ("fuzzy", "missing"))  # stitched table cells
        self.assertEqual(self.check("ILT 是唯一正确的方法", "3"), "missing")


class TestCarryForward(unittest.TestCase):
    def test_update_keeps_evidence_from_other_documents(self):
        from lithokb.compiler import carry_forward_evidence
        kb = fresh_kb()
        try:
            S.put(kb, "rev", [{"path": "a.md", "text": "# A\n\nOPC 修改掩模。\n"}, {"path": "b.md", "text": "# B\n\nOPC 依赖模型。\n"}])
            cards = Cards(kb)
            cards.new_revision("x", {"id": "opc", "title": "OPC", "type": "method",
                                     "evidence": [{"id": "E1", "path": "a.md", "lines": "3", "quote": "OPC 修改掩模。"}],
                                     "sources": ["a.md"]}, "body [E1]", {"kind": "llm"})
            upd = {"id": "opc", "title": "OPC", "type": "method", "relations": [], "sources": ["b.md"],
                   "evidence": [{"id": "E1", "path": "b.md", "lines": "3", "quote": "OPC 依赖模型。"}]}
            self.assertEqual(carry_forward_evidence(cards, upd, ["b.md"]), 1)
            self.assertEqual({e["path"] for e in upd["evidence"]}, {"a.md", "b.md"})
            self.assertEqual(len({e["id"] for e in upd["evidence"]}), 2)  # id collision renumbered
            self.assertEqual(sorted(upd["sources"]), ["a.md", "b.md"])
            m = cards.new_revision("x", upd, "body", {"kind": "llm"})
            self.assertEqual(m["grounding"]["exact"], 2)
        finally:
            shutil.rmtree(kb.root)


class TestRetry(unittest.TestCase):
    def test_degenerate_json_is_retried_once(self):
        kb = fresh_kb()
        try:
            S.put(kb, "rev", [{"path": "a.md", "text": "# A\n\nOPC 修改掩模图形。\n"}])
            comp = Compiler(kb, Cards(kb))
            run = comp.run_once("admin", ["a.md"], {**kb.config["llm"], "backend": "mock"}, instructions="[[MOCK:DEGENERATE]]")
            self.assertEqual((run["status"], run["attempts"]), ("done", 2))
            self.assertEqual(len(run["calls"]), 2)
            t = comp.trace(run["id"])
            self.assertIn('{"": [""]', t["response.md"])        # the bad answer is kept in the trace
            self.assertIn("# Correction", t["retry1-prompt.md"])
            cfg = json.loads((kb.root / "config.json").read_text())
            cfg["compile"] = {"max_attempts": 1}
            (kb.root / "config.json").write_text(json.dumps(cfg))
            run = comp.run_once("admin", ["a.md"], {**kb.config["llm"], "backend": "mock"}, instructions="[[MOCK:DEGENERATE]]")
            self.assertEqual(run["status"], "failed")
        finally:
            shutil.rmtree(kb.root)


class TestMergeMechanisms(unittest.TestCase):
    """Cross-document merging: mention detection, append action, schema topic stubs."""

    def setUp(self):
        self.kb = fresh_kb()
        S.put(self.kb, "rev", [{"path": "a.md", "text": "# A\n\nEPE 是边缘放置误差。\n"},
                               {"path": "b.md", "text": "# B\n\n模型型OPC 以 EPE 为目标，EPE 越小越好。\n"}])
        self.cards = Cards(self.kb)
        self.cards.new_revision("x", {"id": "edge-placement-error", "title": "边缘放置误差 (EPE)", "type": "metric",
                                      "aliases": ["Edge Placement Error"], "relations": [],
                                      "evidence": [{"id": "E1", "path": "a.md", "lines": "3", "quote": "EPE 是边缘放置误差。"}],
                                      "sources": ["a.md"]}, "定义 [E1]", {"kind": "llm"})

    def tearDown(self):
        shutil.rmtree(self.kb.root)

    def test_mentioned_cards_and_prompt(self):
        from lithokb.compiler import build_prompt, mentioned_cards
        self.assertEqual(mentioned_cards(self.cards, S.read_text(self.kb, "b.md"), set()), [("edge-placement-error", 2)])
        _, user, related, _ = build_prompt(self.kb, self.cards, [{"path": "b.md", "start": None, "end": None}])
        self.assertIn('<card id="edge-placement-error" units="2" mentions="2">', user)  # size shown so the model can respect granularity
        self.assertIn("edge-placement-error", related)

    def test_append_merges_deterministically(self):
        data = {"cards": [{"action": "append", "id": "edge-placement-error", "add_md": "模型型 OPC 以它为目标 [E1]。",
                           "evidence": [{"id": "E1", "path": "b.md", "lines": "3", "quote": "模型型OPC 以 EPE 为目标"}],
                           "relations": [{"rel": "measured_by", "target": "edge-placement-error", "basis": "inferred"}],
                           "aliases": ["边放误差"]}, "not a card"]}
        norm, findings = validate(self.cards, data, ["b.md"])
        self.assertTrue(norm[0]["append"])
        self.assertTrue(any("not an object" in f["msg"] for f in findings))  # robust to junk items
        from lithokb.compiler import apply_append
        card, body = apply_append(self.cards, norm[0], norm[0]["add_md"], ["b.md"])
        self.assertIn("定义 [E1]", body)                       # existing content kept
        self.assertIn("### 补充（来自 [《B》](src:b.md)）\n\n模型型 OPC 以它为目标 [E2]。", body)  # titled link, not a path  # new evidence renumbered
        self.assertEqual([e["id"] for e in card["evidence"]], ["E1", "E2"])
        self.assertEqual(card["sources"], ["a.md", "b.md"])
        self.assertIn("边放误差", card["aliases"])
        m = self.cards.new_revision("x", card, body, {"kind": "llm"})
        self.assertEqual((m["rev"], m["grounding"]["exact"]), (2, 2))

    def test_schema_topic_stubs(self):
        from lithokb.compiler import schema_topic_stubs
        norm = [{"id": "x", "parent": "mask-3d", "relations": [{"rel": "uses", "target": "smo"}, {"rel": "uses", "target": "not-in-schema"}]}]
        stubs = schema_topic_stubs(self.kb, self.cards, norm)
        self.assertEqual([s_["card"]["id"] for s_ in stubs], ["mask-3d", "smo"])
        self.assertEqual(stubs[0]["card"]["title"], "掩模三维效应（M3D）与 EUV 特有效应")


class TestFixRound(unittest.TestCase):
    """ID resolution, card citations in answers, duplicate sources, reasoning watchdog."""

    def test_id_resolver(self):
        from lithokb.compiler import IdResolver
        kb = fresh_kb()
        try:
            cards = Cards(kb)
            for cid, title in (("opc", "光学邻近效应修正"), ("process-window", "工艺窗口 (Process Window)"),
                               ("edge-placement-error", "边缘放置误差 (EPE)")):
                cards.new_revision("x", {"id": cid, "title": title, "type": "concept", "evidence": []}, "", {"kind": "llm"})
            r = IdResolver(cards, set())
            self.assertEqual(r.resolve("optical-proximity-correction"), ("opc", "acronym"))
            self.assertEqual(r.resolve("epe"), ("edge-placement-error", "name"))
            self.assertEqual(r.resolve("process-window"), ("process-window", ""))
            self.assertEqual(r.resolve("totally-unknown"), ("totally-unknown", ""))
            data = {"cards": [{"id": "x1", "title": "X", "type": "concept", "parent": "optical-proximity-correction",
                               "body_md": "见 [[epe]] 与 [[nothing-here]]", "relations": [{"rel": "uses", "target": "epe", "basis": "inferred"}],
                               "evidence": []}]}
            norm, findings = validate(cards, data, [])
            self.assertEqual(norm[0]["parent"], "opc")
            self.assertEqual(norm[0]["relations"][0]["target"], "edge-placement-error")
            self.assertIn("[[edge-placement-error]]", norm[0]["body"])
            self.assertIn("[[nothing-here]]", norm[0]["body"])  # unresolvable links left as written
            self.assertTrue(any("resolved" in f["msg"] for f in findings))
        finally:
            shutil.rmtree(kb.root)

    def test_near_duplicates(self):
        kb = fresh_kb()
        try:
            toc = "".join(f"\n- [{i}、第{i}章：光刻原理与OPC方法第{i}部分]({i:02d}.md)" for i in range(1, 25))
            S.put(kb, "rev", [{"path": "index.md", "text": "# 目录" + toc},
                              {"path": "index1.md", "text": "# 课程目录\n" + toc.replace("\n- ", "\n").replace("](", "](./")},
                              {"path": "ch1.md", "text": "# 第一章\n\n" + "光刻胶模型描述显影过程。" * 30}])
            pairs = {(d["a"], d["b"]) for d in S.near_duplicates(kb)}
            self.assertEqual(pairs, {("index.md", "index1.md")})
            self.assertTrue(any(i["kind"] == "duplicate_source" for i in Cards(kb).lint()))
        finally:
            shutil.rmtree(kb.root)

    def test_reasoning_watchdog_steps_down(self):
        import http.server
        from lithokb import llm

        class Fake(http.server.BaseHTTPRequestHandler):
            efforts = []

            def log_message(self, *a):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                eff = body.get("reasoning", {}).get("effort", "none")
                Fake.efforts.append(eff)
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                chunks = ([{"reasoning": "想" * 500}] * 20) if eff == "high" else [{"reasoning": "ok"}, {"content": '{"cards": []}'}]
                try:
                    for d in chunks:
                        self.wfile.write(b"data: " + json.dumps({"id": "g", "model": "m", "choices": [{"delta": d}]}).encode() + b"\n\n")
                    self.wfile.write(b"data: " + json.dumps({"choices": [{"delta": {}, "finish_reason": "stop"}],
                                                              "usage": {"prompt_tokens": 1, "completion_tokens": 2}}).encode() + b"\n\n")
                    self.wfile.write(b"data: [DONE]\n\n")
                except (BrokenPipeError, ConnectionResetError):
                    pass

        srv = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        old_url, old_key = llm.OPENROUTER_URL, os.environ.get("OPEN_ROUTER_API_KEY")
        llm.OPENROUTER_URL = f"http://127.0.0.1:{srv.server_port}/v1/chat/completions"
        os.environ["OPEN_ROUTER_API_KEY"] = "test"
        try:
            r = llm.call({"backend": "openrouter", "openrouter_reasoning": "high", "reasoning_watchdog_chars": 3000}, "s", "u")
            self.assertEqual(Fake.efforts, ["high", "medium"])
            self.assertEqual(r.text, '{"cards": []}')
            self.assertEqual(r.raw_meta["reasoning_effort"], "medium")
            self.assertEqual(r.raw_meta["watchdog_aborts"][0]["effort"], "high")
        finally:
            llm.OPENROUTER_URL = old_url
            if old_key is None:
                os.environ.pop("OPEN_ROUTER_API_KEY", None)
            else:
                os.environ["OPEN_ROUTER_API_KEY"] = old_key
            srv.shutdown()


class TestReviewUX(unittest.TestCase):
    """Fixes found while walking the review/publish workflow on real compiled cards."""

    def setUp(self):
        self.kb = fresh_kb()
        S.put(self.kb, "rev", [{"path": "a.md", "text": "# A\n\n工艺窗口定义。\n\n| 模型 | 轮廓 |\n|---|---|\n| 阈值 | Contour = { (x,y) \\| I = Ith } |\n"},
                               {"path": "b.md", "text": "# B\n\nSMO 扩大工艺窗口。\n"}])
        self.cards = Cards(self.kb)
        self.cards.new_revision("x", {"id": "pw", "title": "工艺窗口", "type": "concept",
                                      "relations": [{"rel": "uses", "target": "smo", "basis": "extracted", "confidence": 1.0, "evidence": "E1"}],
                                      "evidence": [{"id": "E1", "path": "a.md", "lines": "3", "quote": "工艺窗口定义。"}]},
                                "定义 [E1]", {"kind": "llm"})

    def tearDown(self):
        shutil.rmtree(self.kb.root)

    def test_escaped_pipe_in_converted_table_is_exact(self):
        from lithokb.cards import verify_evidence
        r = verify_evidence(self.kb, {"id": "E", "path": "a.md", "lines": "7", "quote": "| 阈值 | Contour = { (x,y) | I = Ith } |"})
        self.assertEqual(r["check"], "exact")

    def test_append_heading_not_duplicated_and_ids_monotonic(self):
        from lithokb.compiler import apply_append
        c = {"id": "pw", "aliases": [], "relations": [],
             "evidence": [{"id": "E1", "path": "b.md", "lines": "3", "quote": "SMO 扩大工艺窗口。"}]}
        card, body = apply_append(self.cards, c, "### 补充（来自 b.md）\n\nSMO 的作用 [E1]。", ["b.md"])
        self.assertEqual(body.count("补充（来自"), 1)
        self.assertEqual([e["id"] for e in card["evidence"]], ["E1", "E2"])

    def test_semantic_diff_ignores_number_formatting(self):
        m, body = self.cards.load("pw")
        rel = [{**m["relations"][0], "confidence": 1}]  # browser round-trip turns 1.0 into 1
        self.cards.human_edit({"name": "rev"}, "pw", {"relations": rel, "body": body.replace("定义", "定义（修订）")})
        sd = self.cards.semantic_diff("pw", 1, 2)
        self.assertEqual((sd["fields"], sd["relations_changed"], sd["relations_added"]), ([], [], []))
        self.assertIn("+定义（修订） [E1]", sd["body"])
        self.assertEqual(self.cards.reverify("admin")["evidence"], 1)


class TestRiskBatchGranularity(unittest.TestCase):
    def setUp(self):
        self.kb = fresh_kb()
        text = "# A\n\n" + "".join(f"第{i}点：光刻工艺窗口与掩模优化的关系说明，包含较多的描述性文字。\n\n" for i in range(1, 61))
        S.put(self.kb, "rev", [{"path": "a.md", "text": text}, {"path": "b.md", "text": "# B\n\nSMO 扩大工艺窗口。\n"}])
        self.cards = Cards(self.kb)
        self.rev, self.rev2, self.admin = (user(self.kb, n) for n in ("rev", "rev2", "admin"))

    def tearDown(self):
        shutil.rmtree(self.kb.root)

    def mk(self, cid, body, ev, **kw):
        card = {"id": cid, "title": kw.pop("title", cid), "type": kw.pop("type", "concept"), "relations": kw.pop("relations", []),
                "evidence": ev, "confidence": kw.pop("confidence", 0.9)}
        return self.cards.new_revision("x", card, body, kw.pop("origin", {"kind": "llm"}))

    def test_risk_levels(self):
        from lithokb.quality import units
        self.assertEqual(units("光刻 OPC model [E1] [[x]]"), 4)  # 2 CJK + 2 words; markers ignored
        good = [{"id": "E1", "path": "a.md", "lines": "3", "quote": "第1点：光刻工艺窗口与掩模优化的关系说明，包含较多的描述性文字。"}]
        self.mk("low1", "工艺窗口与掩模优化之间的关系：" + "说明文字" * 20 + " [E1]", good)
        self.assertEqual(self.cards.risk("low1")["level"], "low")
        self.mk("amb", "工艺窗口" * 30 + " [E1]", good, relations=[{"rel": "uses", "target": "low1", "basis": "ambiguous"}])
        self.assertEqual(self.cards.risk("amb")["level"], "high")
        bad = [{"id": "E1", "path": "a.md", "lines": "3", "quote": "原文中不存在的一句话"}]
        self.mk("bad", "工艺窗口" * 30 + " [E1]", bad)
        self.assertIn("无法核验", self.cards.risk("bad")["reasons"][0])
        self.mk("thin", "一句话 [E1]", good)
        r = self.cards.risk("thin")
        self.assertEqual(r["level"], "medium")
        self.assertIn("thin", r["granularity"]["issues"])

    def test_batch_requires_comment_low_risk_and_audits(self):
        good = [{"id": "E1", "path": "a.md", "lines": "3", "quote": "第1点：光刻工艺窗口与掩模优化的关系说明，包含较多的描述性文字。"}]
        self.mk("c1", "关系说明" * 30 + " [E1]", good)
        self.mk("c2", "关系说明" * 30 + " [E1]", good, relations=[{"rel": "uses", "target": "c1", "basis": "ambiguous"}])
        with self.assertRaises(CardError):
            self.cards.batch(self.rev, ["c1"], "approve", "太短")
        with self.assertRaises(PermissionError):
            self.cards.batch(self.rev, ["c1"], "publish", "这是一条足够长的发布评语。")
        res = self.cards.batch(self.rev, ["c1", "c2", "nope"], "approve", "抽查原文一致，证据全部精确匹配。")
        self.assertEqual(res["done"], ["c1"])
        self.assertEqual({x["id"] for x in res["skipped"]}, {"c2", "nope"})
        rec = self.cards.reviews("c1")[-1]
        self.assertEqual((rec["verdict"], rec["batch"]), ("approve", res["batch"]))
        self.assertIn(res["batch"], rec["comment"])
        ev = [e for e in self.kb.events(50) if e["action"] == "review.batch_approve"][0]
        self.assertEqual(ev["detail"]["done"], ["c1"])
        self.assertIn("rules", ev["detail"]["criteria"])
        pub = self.cards.batch(self.admin, ["c1", "c2"], "publish", "第一批低风险卡片，已审阅通过。")
        self.assertEqual(pub["done"], ["c1"])
        self.assertTrue(is_public(self.cards.load("c1")[0]))

    def test_consolidate_split_keeps_evidence_and_merge(self):
        from lithokb.consolidate import Consolidator, merge
        ev = [{"id": f"E{i}", "path": "a.md", "lines": str(1 + 2 * i), "quote": f"第{i}点：光刻工艺窗口与掩模优化的关系说明，包含较多的描述性文字。"}
              for i in range(1, 31)]
        body = "定义段落 [E1]\n\n" + "".join(f"### 补充（来自 [《A》](src:a.md)）\n\n第{i}点的展开说明，" + "细节描述" * 40 + f" [E{i}]\n\n"
                                         for i in range(2, 31))
        self.mk("big", body, ev, title="工艺窗口")
        con = Consolidator(self.kb, self.cards, Compiler(self.kb, self.cards))
        self.assertEqual([c["id"] for c in con.candidates()], ["big"])
        run = con.run(self.admin, "big", {**self.kb.config["llm"], "backend": "mock"})
        self.assertEqual(run["status"], "done", run.get("error"))
        self.assertLess(run["after"]["units"], run["before"]["units"])
        head, hbody = self.cards.load("big")
        self.assertEqual(head["origin"]["op"], "consolidate")
        self.assertNotIn("补充（来自", hbody)
        self.assertIn("[[big-details", hbody)  # parent links its child
        child, _ = self.cards.load("big-details")
        self.assertEqual((child["parent"], child["status"]), ("big", "in_review"))
        quotes = {e["quote"] for e in head["evidence"]} | {e["quote"] for e in child["evidence"]}
        self.assertEqual(quotes, {e["quote"] for e in ev})  # no provenance lost
        self.assertEqual(child["grounding"]["score"], 1.0)
        self.assertIn("整合重写，需通读", self.cards.risk("big")["reasons"])
        # merge a thin card into another
        self.mk("thin", "SMO 扩大工艺窗口 [E1]", [{"id": "E1", "path": "b.md", "lines": "3", "quote": "SMO 扩大工艺窗口。"}], title="SMO 作用")
        with self.assertRaises(PermissionError):
            merge(self.cards, self.rev, "thin", "big")
        h = merge(self.cards, self.admin, "thin", "big")
        self.assertIn("### 并入：SMO 作用", self.cards.load("big")[1])
        self.assertIn("SMO 作用", h["aliases"])
        t, _ = self.cards.load("thin")
        self.assertEqual((t["lifecycle"], t["replaced_by"]), ("superseded", "big"))


class TestViewsFacetsIssuesMCP(unittest.TestCase):
    def setUp(self):
        self.kb = fresh_kb()
        S.put(self.kb, "rev", [
            {"path": "a.md", "text": "# EUV\n\n随着工艺节点进入5nm以下，EUV光刻成为主流。\n\n2019年 EUV 进入量产。\n\nDOF > 100 nm 是典型签核目标。\n"},
            {"path": "toc.md", "text": "# 目录\n" + "".join(f"\n- [第{i}章]({i:02d}.md)" for i in range(1, 12))}])
        self.cards = Cards(self.kb)
        self.admin, self.rev, self.rev2, self.bob = (user(self.kb, n) for n in ("admin", "rev", "rev2", "bob"))
        ev = [{"id": "E1", "path": "a.md", "lines": "3", "quote": "随着工艺节点进入5nm以下，EUV光刻成为主流。"},
              {"id": "E2", "path": "a.md", "lines": "5", "quote": "2019年 EUV 进入量产。"},
              {"id": "E3", "path": "a.md", "lines": "7", "quote": "DOF > 100 nm 是典型签核目标。"}]
        self.cards.new_revision("x", {"id": "euv", "title": "EUV 光刻", "type": "concept", "evidence": ev,
                                      "conditions": [{"dim": "wavelength", "value": "EUV", "evidence": "E1"},
                                                     {"dim": "node", "value": "5nm 及以下", "evidence": "E1"},
                                                     {"dim": "node", "value": "<7nm", "evidence": "E3"}],
                                      "events": [{"when": "2019", "what": "EUV 进入量产", "evidence": "E2"},
                                                 {"when": "下一讲", "what": "x", "evidence": "E2"}],
                                      "facts": [{"name": "DOF", "value": "> 100", "unit": "nm", "evidence": "E3"},
                                                {"name": "缺陷类型", "value": "Micro-bridging", "evidence": "E1"}]},
                                "EUV 成为主流 [E1]，2019 年量产 [E2]，DOF [E3]。", {"kind": "llm"})
        self.cards.new_revision("x", {"id": "arf", "title": "ArF 浸没", "type": "concept", "evidence": ev[:1],
                                      "conditions": [{"dim": "wavelength", "value": "193nm", "evidence": "E1"}]},
                                "ArF [E1]", {"kind": "llm"})

    def tearDown(self):
        shutil.rmtree(self.kb.root)

    def test_policy_detection_and_plan(self):
        self.assertEqual(S.policy_of(self.kb, "toc.md")["policy"], "reference")
        self.assertEqual(S.policy_of(self.kb, "a.md")["policy"], "compile")
        comp = Compiler(self.kb, self.cards)
        self.assertEqual(comp.plan(None), ["a.md"])
        S.set_policy(self.kb, "admin", "toc.md", "compile", "test")
        self.assertIn("toc.md", comp.plan(None))
        S.set_policy(self.kb, "admin", "a.md", "exclude")
        self.assertNotIn("a.md", S.list_md_by_policy(self.kb, "compile", "reference"))

    def test_facets_support_and_conditions(self):
        from lithokb import facets as F
        m, _ = self.cards.load("euv")
        sup = {(k, x.get("value", x.get("when"))): x["supported"] for k in ("conditions", "events", "facts") for x in m[k]}
        self.assertTrue(sup[("conditions", "EUV")] and sup[("conditions", "5nm 及以下")])
        self.assertFalse(sup[("conditions", "<7nm")])          # quote does not mention 7 nm
        self.assertTrue(sup[("events", "2019")])
        self.assertFalse(sup[("events", "下一讲")])              # not a date
        self.assertTrue(sup[("facts", "> 100")])
        self.assertFalse(sup[("facts", "Micro-bridging")])     # cited quote does not state it
        self.assertEqual(F.applies(F.ok(m["conditions"]), {"node": "3nm"}), "yes")
        self.assertEqual(F.applies(F.ok(m["conditions"]), {"node": "28nm"}), "no")
        self.assertEqual(F.applies(F.ok(m["conditions"]), {"wavelength": "13.5nm"}), "yes")
        self.assertEqual(F.applies([], {"wavelength": "EUV"}), "general")
        self.assertEqual(F.applies(self.cards.load("arf")[0]["conditions"], {"wavelength": "EUV"}), "no")
        self.assertEqual(F._nm_interval("65nm–5nm"), (5.0, 65.0))
        self.assertEqual(F._nm_interval("≥28nm"), (28.0, float("inf")))
        self.assertIn("node", F.dims(self.kb))
        self.assertIn("1 条刻面", " ".join(self.cards.risk("euv")["reasons"]).replace("3 条刻面", "1 条刻面"))

    def test_issue_register(self):
        from lithokb.issues import Issues
        reg = Issues(self.kb)
        a = reg.create("rev", "contradiction", "DOF 目标两处说法不同", "a.md 说 >100nm，b.md 说 >80nm", cards=["euv"])
        b = reg.create("rev", "contradiction", "DOF 目标两处说法不同！", "again", cards=["euv"])
        self.assertEqual((a["id"], b["seen"]), (b["id"], 2))     # deduplicated
        r = reg.create("bob", "report", "E3 数值与原文不一致", cards=["euv"])
        with self.assertRaises(PermissionError):
            reg.act(self.bob, a["id"], "resolve", "x")
        reg.act(self.bob, r["id"], "comment", "补充：原文第7行")   # reporter may comment
        with self.assertRaises(Exception):
            reg.act(self.rev, a["id"], "resolve", "")             # needs an explanation
        x = reg.act(self.rev, a["id"], "resolve", "不同节点的目标，已在卡片中注明条件")
        self.assertEqual(x["status"], "resolved")
        self.assertEqual(reg.stats()["open"], 1)

    def test_reader_never_sees_unpublished_revision(self):
        self.cards.act(self.rev, "euv", "approve")
        self.cards.act(self.admin, "euv", "publish")
        self.cards.human_edit(self.rev2, "euv", {"title": "EUV 光刻（草稿新标题）", "summary": "SECRET-DRAFT",
                                                 "body": "SECRET-DRAFT 正文 [E1]"})
        idx_view = [c for c in self.cards.listing(visible_only=True) if c["id"] == "euv"][0]
        self.assertEqual((idx_view["title"], idx_view["rev"]), ("EUV 光刻", 1))
        self.assertEqual(self.cards.search("SECRET-DRAFT", visible_only=True), [])
        self.assertTrue(self.cards.search("SECRET-DRAFT", visible_only=False))
        g = self.cards.graph(visible_only=True)
        self.assertEqual([n["title"] for n in g["nodes"] if n["id"] == "euv"], ["EUV 光刻"])
        from lithokb.mcp import Server
        srv = Server(self.kb, self.bob)
        out = json.dumps(srv.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                     "params": {"name": "get_card", "arguments": {"id": "euv"}}}), ensure_ascii=False)
        self.assertNotIn("SECRET-DRAFT", out)
        self.assertIn("EUV 成为主流", out)

    def test_mcp_protocol(self):
        import io
        from lithokb.mcp import Server
        self.cards.act(self.rev, "euv", "approve")
        self.cards.act(self.admin, "euv", "publish")
        msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "facts", "arguments": {"name": "DOF"}}},
                {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "search_knowledge", "arguments": {"query": "EUV", "conditions": {"node": "28nm"}}}},
                {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "read_source", "arguments": {"path": "a.md", "start": 3, "end": 3}}},
                {"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {"name": "get_card", "arguments": {"id": "arf"}}},
                {"jsonrpc": "2.0", "id": 7, "method": "nope"}]
        out = io.StringIO()
        Server(self.kb, self.bob).serve(io.StringIO("\n".join(json.dumps(m) for m in msgs) + "\n"), out)
        res = {r["id"]: r for r in map(json.loads, out.getvalue().splitlines())}
        self.assertNotIn(None, res)                              # notification got no response
        self.assertEqual(res[1]["result"]["serverInfo"]["name"], "lithokb")
        self.assertEqual(len(res[2]["result"]["tools"]), 11)
        self.assertIn('"value": "> 100"', res[3]["result"]["content"][0]["text"])
        self.assertEqual(json.loads(res[4]["result"]["content"][0]["text"]), [])   # EUV card does not apply to 28nm
        self.assertIn("    3|随着工艺节点", res[5]["result"]["content"][0]["text"])
        self.assertTrue(res[6]["result"]["isError"])             # unpublished → refused, as a tool error
        self.assertEqual(res[7]["error"]["code"], -32601)

    def test_annotate_backfill_mock(self):
        from lithokb.annotate import Annotator
        self.cards.new_revision("x", {"id": "bare", "title": "Bare", "type": "concept",
                                      "evidence": [{"id": "E1", "path": "a.md", "lines": "5", "quote": "2019年 EUV 进入量产。"}]},
                                "bare [E1]", {"kind": "llm"})
        an = Annotator(self.kb, self.cards, Compiler(self.kb, self.cards))
        self.assertIn("bare", an.candidates())
        r = an.run(self.admin, "bare", {**self.kb.config["llm"], "backend": "mock"})
        self.assertEqual(r["status"], "done")
        m, _ = self.cards.load("bare")
        self.assertEqual(m["origin"]["op"], "annotate")
        self.assertEqual([(c["dim"], c["value"]) for c in m["conditions"]], [("wavelength", "EUV")])
        self.assertEqual(m["events"][0]["when"], "2019")
