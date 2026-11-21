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
