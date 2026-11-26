"""Operations, robustness and agent UX: answer cache, asynchronous questions with progress, the concurrency
limit, pre-warming, doctor / refresh, extended fsck, HTML code blocks and re-conversion. Offline (mock)."""
import json
import shutil
import sys
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

from test_lkb import EXAMPLES, fresh_kb, user  # noqa: E402

from lithokb import sources as S  # noqa: E402
from lithokb.ask import Asker  # noqa: E402
from lithokb.cards import Cards  # noqa: E402
from lithokb.compiler import Compiler  # noqa: E402
from lithokb.doctor import doctor, refresh  # noqa: E402
from lithokb.fsck import fsck  # noqa: E402
from lithokb.html2md import convert  # noqa: E402
from lithokb.server import App, make_handler  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        self.kb = fresh_kb()
        S.put_dir(self.kb, "rev", str(EXAMPLES))
        self.cards = Cards(self.kb)
        self.comp = Compiler(self.kb, self.cards)
        self.comp.start("admin", self.comp.plan(None), backend="mock", background=False)
        self.cfg = {**self.kb.config["llm"], "backend": "mock"}

    def tearDown(self):
        shutil.rmtree(self.kb.root)


class TestAnswerCache(Base):
    def test_same_question_same_state_is_served_from_cache(self):
        a = Asker(self.kb, self.cards, self.comp)
        rev = user(self.kb, "rev")
        r1 = a.ask(rev, "threshold model resist", self.cfg, include_unpublished=True, use_cache=True)
        r2 = a.ask(rev, "threshold   model resist ", self.cfg, include_unpublished=True, use_cache=True)  # whitespace ignored
        self.assertTrue(r2.get("cached"))
        self.assertEqual(r2["id"], r1["id"])
        r3 = a.ask(rev, "threshold model resist", self.cfg, include_unpublished=False, use_cache=True)  # other scope
        self.assertFalse(r3.get("cached"))
        # the knowledge base changed → the cached answer is no longer exact
        cid = next(iter(self.cards.index()))
        self.cards.human_edit(rev, cid, {"summary": "edited"})
        r4 = a.ask(rev, "threshold model resist", self.cfg, include_unpublished=True, use_cache=True)
        self.assertFalse(r4.get("cached"))
        self.assertNotIn("cached", a.ask(rev, "threshold model resist", self.cfg, include_unpublished=True))  # off by default


class TestHTTPAsync(Base):
    def setUp(self):
        super().setUp()
        cfgp = self.kb.root / "config.json"
        c = json.loads(cfgp.read_text())
        c["query"] = {**c.get("query", {}), "max_concurrent": 1}
        cfgp.write_text(json.dumps(c))
        self.app = App(self.kb)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.app))
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}/api/"
        self.tok = self.call("POST", "login", {"name": "rev", "password": "pw-rev"})[1]["token"]

    def tearDown(self):
        self.httpd.shutdown()
        super().tearDown()

    def call(self, method, path, body=None):
        req = urllib.request.Request(self.base + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json", **({"Authorization": "Bearer " + self.tok}
                                                                                      if getattr(self, "tok", None) else {})})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_async_question_progress_cache_and_limit(self):
        code, r = self.call("POST", "ask", {"question": "model-based OPC segments", "async": True, "cache": False})
        self.assertEqual((code, r["status"]), (202, "running"))
        for _ in range(100):
            code, run = self.call("GET", "queries/" + r["id"])
            if code == 200 and run.get("status") != "running":
                break
            time.sleep(0.05)
        self.assertEqual(run["status"], "done", run.get("error"))
        self.assertTrue(any(g["graph"] == "ask" for g in run["graph"]))
        # cached: the same question returns at once, without a model call
        self.call("POST", "ask", {"question": "resist threshold model"})
        code, hit = self.call("POST", "ask", {"question": "resist threshold model"})
        self.assertTrue(hit.get("cached"))
        # concurrency limit: with every slot taken, a new question is refused with 429 (not queued forever)
        self.assertTrue(self.app.llm_slots.acquire(blocking=False))
        try:
            code, err = self.call("POST", "ask", {"question": "a brand new question", "cache": False})
            self.assertEqual(code, 429)
        finally:
            self.app.llm_slots.release()
        self.assertEqual(self.call("POST", "ask", {"question": "  "})[0], 400)

    def test_prewarm_and_retrieve_and_doctor_endpoints(self):
        pw = self.app.prewarm()
        self.assertTrue(all(isinstance(v, float) for k, v in pw.items()), pw)
        code, r = self.call("GET", "retrieve?q=threshold%20model")
        self.assertEqual(code, 200)
        self.assertIn("sections", r)
        code, d = self.call("GET", "doctor")
        self.assertEqual(code, 200)
        self.assertIn(d["status"], ("ok", "warn", "error"))


class TestDoctorRefreshFsck(Base):
    def test_doctor_reports_and_refresh_plans_then_applies(self):
        d = doctor(self.kb, self.cards, self.comp)
        areas = {f["area"]: f for f in d["findings"]}
        self.assertEqual(areas["pageindex"]["level"], "warn")  # nothing summarised yet
        self.assertEqual(areas["evaluation"]["level"], "warn")  # no golden questions
        plan = refresh(self.kb, self.cards, self.comp, "admin", self.cfg)
        self.assertFalse(plan["apply"])
        self.assertEqual([p["step"] for p in plan["plan"]], ["pageindex", "topics"])
        done = refresh(self.kb, self.cards, self.comp, "admin", self.cfg, apply=True)
        self.assertEqual([x["step"] for x in done["done"]], ["pageindex", "topics"])
        self.assertEqual(refresh(self.kb, self.cards, self.comp, "admin", self.cfg)["plan"], [])  # up to date
        areas = {f["area"]: f for f in doctor(self.kb, self.cards, self.comp)["findings"]}
        self.assertEqual((areas["pageindex"]["level"], areas["topics"]["level"]), ("ok", "ok"))

    def test_fsck_new_checks(self):
        (self.kb.traces_dir / "_cache").mkdir(parents=True, exist_ok=True)
        (self.kb.traces_dir / "_cache" / "deadbeef.json").write_text('{"run": "20990101T000000-000000-0000"}')
        (self.kb.root / "eval" / "runs").mkdir(parents=True, exist_ok=True)
        (self.kb.root / "eval" / "runs" / "eval-broken.json").write_text("{not json")
        r = fsck(self.kb, self.cards)
        kinds = {p["kind"] for p in r["problems"]}
        self.assertIn("stale_answer_cache", kinds)
        self.assertIn("eval_run_unparseable", kinds)
        fsck(self.kb, self.cards, repair=True)
        self.assertFalse((self.kb.traces_dir / "_cache" / "deadbeef.json").exists())


class TestHTMLCodeBlocks(unittest.TestCase):
    def test_code_div_keeps_lines_and_never_becomes_a_heading(self):
        md = convert('<html><title>Page</title><h2>A</h2><div class="code-block">\n# comment\ndef f(x):\n    return x\n</div>'
                     '<h2>B</h2><div class="note">plain <b>div</b></div>')
        self.assertIn("```\n# comment\ndef f(x):\n    return x\n```", md)
        self.assertIn('title: "Page"', md)
        self.assertNotIn("\n# comment def", md)
        self.assertIn("plain **div**", md)

    def test_reconvert_dry_run_and_apply(self):
        kb = fresh_kb()
        try:
            html = '<html><title>T</title><h1>T</h1><div class="code-block">\nx = 1\ny = 2\n</div></html>'
            S.put(kb, "rev", [{"path": "p/page.html", "text": html}])
            md0 = S.read_text(kb, "p/page.md")
            (kb.sources / "p" / "page.md").write_text(md0.replace("y = 2", "y = 3"), "utf-8")  # simulate an old conversion
            meta = S.load_meta(kb)
            meta["p/page.md"]["sha256"] = __import__("hashlib").sha256((kb.sources / "p" / "page.md").read_bytes()).hexdigest()
            S._save_meta(kb, meta)
            dry = S.reconvert(kb, "admin")
            self.assertTrue(dry[0]["changed"])
            self.assertIn("y = 3", S.read_text(kb, "p/page.md"))  # dry run writes nothing
            S.reconvert(kb, "admin", apply=True)
            self.assertIn("y = 2", S.read_text(kb, "p/page.md"))
            self.assertEqual(S.load_meta(kb)["p/page.md"]["version"], 2)  # old version kept in history
        finally:
            shutil.rmtree(kb.root)


if __name__ == "__main__":
    unittest.main()
