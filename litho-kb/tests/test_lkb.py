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
