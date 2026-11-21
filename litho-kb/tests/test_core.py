"""Core engine: PageIndex (tree + summaries + tree search), knowledge graph, wiki, lexical index,
cross-process writer lock, incremental index, fsck. Offline (mock LLM backend)."""
import json
import shutil
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

from test_lkb import EXAMPLES, fresh_kb, user  # noqa: E402

from lithokb import graph as G  # noqa: E402
from lithokb import pageindex as PI  # noqa: E402
from lithokb import schema as SC  # noqa: E402
from lithokb import sources as S  # noqa: E402
from lithokb.ask import Asker  # noqa: E402
from lithokb.cards import Cards  # noqa: E402
from lithokb.compiler import Compiler  # noqa: E402
from lithokb.fsck import fsck  # noqa: E402
from lithokb.textindex import BM25, tokens  # noqa: E402
from lithokb.wiki import Wiki  # noqa: E402

MOCK = {"backend": "mock"}


def publish_all(kb, cards):
    rev2, admin = user(kb, "rev2"), user(kb, "admin")
    for cid, m in list(cards.index().items()):
        if m["status"] == "in_review":
            cards.act(rev2, cid, "approve")
            cards.act(admin, cid, "publish")


class Base(unittest.TestCase):
    def setUp(self):
        self.kb = fresh_kb()
        S.put_dir(self.kb, "rev", str(EXAMPLES))
        self.cards = Cards(self.kb)
        self.comp = Compiler(self.kb, self.cards)
        self.comp.start("admin", self.comp.plan(None), backend="mock", background=False)
        self.cfg = {**self.kb.config["llm"], **MOCK}

    def tearDown(self):
        shutil.rmtree(self.kb.root)


class TestLexical(Base):
    def test_cjk_tokens_and_ranked_search_without_spaces(self):
        self.assertIn("掩模", tokens("掩模三维效应"))
        self.assertIn("13.5nm", tokens("EUV 13.5nm"))
        hits = self.cards.search("邻近效应修正", visible_only=False)  # no spaces, Chinese
        self.assertTrue(hits and "opc" in hits[0]["id"])
        self.assertTrue(all("score" in h for h in hits))
        b = BM25()
        b.put("a", 1, [("光学邻近效应修正", 1)])
        self.assertFalse(b.put("a", 1, [("x", 1)]))  # unchanged signature → not re-tokenised
        b.sync(set())
        self.assertEqual(len(b), 0)
        self.assertEqual(b.post, {})

    def test_incremental_index_reuses_unchanged_entries(self):
        i1 = self.cards.index()
        some = sorted(i1)[0]
        other = sorted(i1)[1]
        obj_other = i1[other]
        g1 = self.cards.generation
        self.cards.human_edit(user(self.kb, "rev"), some, {"summary": "改过的摘要"})
        i2 = self.cards.index()
        self.assertGreater(self.cards.generation, g1)
        self.assertIs(i2[other], obj_other)  # not re-parsed
        self.assertEqual(i2[some]["summary"], "改过的摘要")
        self.assertIs(self.cards.index(), i2)  # warm: nothing changed


class TestWriterLock(unittest.TestCase):
    def test_two_processes_writing_revisions_of_one_card_never_collide(self):
        kb = fresh_kb()
        try:
            script = textwrap.dedent(f"""
                import sys; sys.path.insert(0, {str(ROOT)!r})
                from lithokb.store import KB
                from lithokb.cards import Cards
                kb = KB({str(kb.root)!r}); c = Cards(kb)
                for i in range(12):
                    c.new_revision("p" + sys.argv[1], {{"id": "x", "title": "X", "type": "concept", "summary": sys.argv[1] + str(i),
                                   "evidence": [], "relations": []}}, "body " + sys.argv[1] + str(i), {{"kind": "llm"}})
            """)
            procs = [subprocess.Popen([sys.executable, "-c", script, str(n)]) for n in (1, 2)]
            self.assertEqual([p.wait(60) for p in procs], [0, 0])
            head, _ = Cards(kb).load("x")
            self.assertEqual(head["rev"], 24)
            self.assertEqual(len(list((kb.revs_dir / "x").glob("r*.md"))), 24)
            self.assertTrue(fsck(kb, Cards(kb))["ok"])
        finally:
            shutil.rmtree(kb.root)


class TestPageIndex(Base):
    def test_index_pass_is_incremental_and_verifies_entities(self):
        ix = PI.Indexer(self.kb, self.comp)
        self.assertEqual(ix.status()["compiled"], 0)
        rep = ix.run("admin", self.cfg)
        self.assertEqual(len(rep["indexed"]), rep["documents"])
        self.assertFalse(rep["failed"])
        self.assertEqual(ix.status()["pending"], [])
        self.assertEqual(ix.run("admin", self.cfg)["indexed"], [])  # nothing changed → no LLM calls
        meta = S.meta_ro(self.kb)
        tree = PI.doc_tree(self.kb, "opc/opc-basics.md", meta)
        self.assertTrue(tree["summary"])
        self.assertTrue(all(n.get("summary") for n in PI.walk(tree["nodes"])))
        # entity verification: an invented name is dropped
        t = doc = S.read_text(self.kb, "opc/opc-basics.md")
        base = PI.doctree.build(t)
        data, findings = PI._validate({"nodes": {}, "entities": [{"name": "EPE", "type": "tool"},
                                                                 {"name": "NoSuchTool9000", "type": "tool"}]},
                                      base, len(doc.splitlines()), doc, {"tool": "x"})
        self.assertEqual([e["name"] for e in data["entities"]], ["EPE"])
        self.assertTrue(any("not found verbatim" in f for f in findings))
        # changing a document re-indexes only that document
        S.put(self.kb, "rev", [{"path": "opc/opc-basics.md", "text": t + "\n## 新节\n\n新增内容。\n"}])
        self.assertEqual(ix.status()["pending"], ["opc/opc-basics.md"])

    def test_tree_render_respects_budget_and_collapses(self):
        t = PI.knowledge_tree(self.kb, self.cards, readers=False)
        H = PI.Handles(t)
        full, col_full = t.render(["k", "d"], H, 100000)
        small, col_small = t.render(["k", "d"], H, 900)
        self.assertLessEqual(len(small), 1200)
        self.assertIn("[+", small)
        self.assertTrue(col_small)
        self.assertFalse(col_full)
        self.assertIs(PI.knowledge_tree(self.kb, self.cards, readers=False), t)  # cached
        # every document section and every visible card is a node
        self.assertTrue(any(n["kind"] == "section" for n in t.nodes.values()))
        self.assertTrue(set(t.visible_cards) <= set(t.nodes))

    def test_tree_search_takes_extra_rounds_when_the_tree_does_not_fit(self):
        asker = Asker(self.kb, self.cards, self.comp)
        r1 = asker.ask(user(self.kb, "rev"), "基于模型的 OPC 片段", self.cfg, include_unpublished=True)
        self.assertEqual(r1["status"], "done")
        self.assertEqual(len(r1["navigation"]["rounds"]), 1)  # small KB: everything visible in round 1
        cfgp = self.kb.root / "config.json"
        c = json.loads(cfgp.read_text())
        c["query"] = {**c.get("query", {}), "nav_budget_chars": 500}
        cfgp.write_text(json.dumps(c))
        r2 = asker.ask(user(self.kb, "rev"), "基于模型的 OPC 片段", self.cfg, include_unpublished=True)
        self.assertEqual(r2["status"], "done", r2.get("error"))
        nav = r2["navigation"]
        self.assertGreaterEqual(len(nav["rounds"]), 2)
        self.assertTrue(nav["rounds"][0]["expand"])
        self.assertTrue(nav["cards"] or nav["sections"])
        self.assertTrue(all(c["prompt_chars"] < 6000 for c in nav["rounds"]))
        t = self.comp.trace(r2["id"])
        self.assertIn("nav2-prompt.md", t)


class TestGraphAndWiki(Base):
    def setUp(self):
        super().setUp()
        PI.Indexer(self.kb, self.comp).run("admin", self.cfg)
        publish_all(self.kb, self.cards)

    def test_layers_queries_and_ontology(self):
        g = G.build(self.kb, self.cards, readers=True)
        st = g.stats()
        self.assertGreater(st["edges"].get("reviewed", 0), 0)
        self.assertGreater(st["edges"].get("linked", 0), 0)  # sections/cards mention reviewed names
        self.assertGreater(st["nodes"].get("section", 0), 0)
        self.assertIs(G.build(self.kb, self.cards, readers=True), g)  # cached
        cards = [n for n, d in g.nodes.items() if d["kind"] == "card" and d["type"] != "summary"]
        a, b = cards[0], cards[-1]
        p = g.path(a, b)
        if p:
            self.assertEqual(p[0]["from"], a)
            self.assertEqual(p[-1]["to"], b)
        self.assertTrue(g.neighbors(a, 2))
        self.assertTrue(g.pagerank())
        self.assertTrue(g.communities())
        # ontology: a constraint in SCHEMA is enforced as lint findings
        text = SC.current(self.kb)["text"].replace("- `example_of`：* → *", "- `example_of`：* → *\n- `covers`：topic → topic")
        self.assertIn("`covers`：topic", text)
        SC.save(self.kb, "admin", text, "test ontology")
        g2 = G.build(self.kb, self.cards, readers=True)
        self.assertIsNot(g2, g)
        self.assertTrue(any(f["kind"] == "ontology_violation" for f in g2.findings))
        self.assertTrue(any(i.get("kind") == "ontology_violation" for i in self.cards.lint()))

    def test_ambiguous_and_generic_names_do_not_explode_mentions(self):
        gz = G.Gazetteer()
        gz.add("OPC", "a")
        gz.add("OPC", "b")  # same name, two cards
        gz.add("逆向光刻", "c")
        gz.finalize()
        hits = gz.scan("OPC 与 逆向光刻 的比较；HOPC 不算")
        self.assertNotIn("a", hits)
        self.assertEqual(hits["c"], 1)
        g = G.build(self.kb, self.cards, readers=True)
        per_src = {}
        for e in g.edges:
            if e["layer"] == "linked":
                per_src[e["s"]] = per_src.get(e["s"], 0) + 1
        self.assertLessEqual(max(per_src.values()), self.kb.config.get("graph", {}).get("max_mentions_per_source", 10))

    def test_wiki_page_home_and_export(self):
        W = Wiki(self.kb, self.cards)
        h = W.home(readers=True)
        self.assertTrue(h["topics"])
        topic = next(t for t in h["topics"] if t["children"] >= 1)
        p = W.page(topic["id"], readers=True)
        self.assertTrue(p["children"])
        child = W.page(p["children"][0]["id"], readers=True)
        self.assertEqual(child["breadcrumbs"][-1]["id"], topic["id"])
        self.assertTrue(any(W.page(c, True)["sections"] for c in self.cards.index() if W.page(c, True)))
        out = W.export()
        self.assertGreater(out["pages"], 5)
        self.assertTrue((self.kb.root / "compiled" / "wiki" / "index.md").exists())

    def test_hub_overview_is_checked_and_reviewed(self):
        W = Wiki(self.kb, self.cards)
        topic = next(t["id"] for t in W.home(True)["topics"] if t["children"] >= 2)
        run = W.write_hub(user(self.kb, "rev"), topic, self.cfg, self.comp)
        self.assertEqual(run["status"], "done", run.get("error"))
        head, body = self.cards.load(topic)
        self.assertEqual((head["status"], head["origin"]["op"]), ("in_review", "hub"))
        self.assertEqual(head["origin"]["children_cited"], 1.0)
        self.assertIn("[[", body)
        self.assertEqual(self.cards.risk(topic)["level"], "medium")
        # readers still see the published (pre-hub) revision until the overview is approved
        self.assertNotEqual(W.page(topic, readers=True)["body"], body)


class TestFsck(Base):
    def test_detects_and_repairs_only_derived_state(self):
        r = fsck(self.kb, self.cards)
        self.assertTrue(r["ok"], r["problems"])
        (self.kb.root / "compiled" / ".tmp-crash").write_text("x")
        (self.kb.sources / "opc" / "ilt.md").write_text("tampered", "utf-8")
        r = fsck(self.kb, self.cards)
        kinds = {p["kind"] for p in r["problems"]}
        self.assertIn("interrupted_write", kinds)
        self.assertIn("source_sha_mismatch", kinds)
        r = fsck(self.kb, self.cards, repair=True)
        self.assertFalse((self.kb.root / "compiled" / ".tmp-crash").exists())
        self.assertTrue((self.kb.sources / "opc" / "ilt.md").exists())  # never touches sources


class TestMCPCore(Base):
    def test_tree_sections_wiki_graph_tools(self):
        from lithokb.mcp import Server
        publish_all(self.kb, self.cards)
        s = Server(self.kb, user(self.kb, "bob"))
        top = s.browse_tree()["tree"]
        self.assertIn("k ", top)
        self.assertIn("d ", top)
        secs = s.search_sections("阈值模型")
        self.assertTrue(secs and secs[0]["lines"])
        cid = next(c for c, m in self.cards.index().items() if m["type"] == "concept")
        self.assertEqual(s.wiki_page(cid)["id"], cid)
        self.assertIsInstance(s.graph_neighbors(cid), list)
        node = "d:opc/opc-basics.md"
        self.assertIn("基于模型", s.browse_tree(node=node)["tree"])


if __name__ == "__main__":
    unittest.main()
