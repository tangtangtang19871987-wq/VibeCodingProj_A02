"""Query-first loop: golden questions + evaluation, topic graph, ontology proposals (review / refine /
approve, Turtle), ontology-guided entity extraction, entity facts in navigation. Offline (mock backend)."""
import json
import shutil
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

from test_lkb import EXAMPLES, fresh_kb, user  # noqa: E402

from lithokb import evalset as E  # noqa: E402
from lithokb import graph as G  # noqa: E402
from lithokb import ontology as O  # noqa: E402
from lithokb import pageindex as PI  # noqa: E402
from lithokb import schema as SC  # noqa: E402
from lithokb import sources as S  # noqa: E402
from lithokb import topics as T  # noqa: E402
from lithokb.ask import Asker  # noqa: E402
from lithokb.cards import Cards  # noqa: E402
from lithokb.compiler import Compiler  # noqa: E402
from lithokb.entities import Extractor  # noqa: E402

GOLDEN = [
    {"id": "q01", "type": "procedural", "question": "How does model-based OPC move the segments?",
     "expected_sources": ["opc/opc-basics.md"], "expected_sections": [{"path": "opc/opc-basics.md", "title_contains": "Model-based"}],
     "key_points": [{"label": "EPE", "any": ["EPE"]}, {"label": "segments", "any": ["segment"]}]},
    {"id": "q02", "type": "lookup", "question": "What does the Hopkins model assume about the mask?",
     "expected_sources": ["imaging/hopkins.md"], "key_points": ["thin mask"]},
]


class Base(unittest.TestCase):
    def setUp(self):
        self.kb = fresh_kb()
        S.put_dir(self.kb, "rev", str(EXAMPLES))
        self.cards = Cards(self.kb)
        self.comp = Compiler(self.kb, self.cards)
        self.comp.start("admin", self.comp.plan(None), backend="mock", background=False)
        self.cfg = {**self.kb.config["llm"], "backend": "mock"}
        self.rev, self.admin = user(self.kb, "rev"), user(self.kb, "admin")

    def tearDown(self):
        shutil.rmtree(self.kb.root)


class TestEvaluation(Base):
    def test_golden_questions_and_runs(self):
        qs = E.save_all(self.kb, "rev", GOLDEN)
        self.assertEqual(qs[1]["key_points"], [{"label": "thin mask", "any": ["thin mask"]}])  # string shorthand
        with self.assertRaises(ValueError):
            E.save_all(self.kb, "rev", GOLDEN + [GOLDEN[0]])  # duplicate id
        rec = E.run_eval(self.kb, Asker(self.kb, self.cards, self.comp), self.cards, self.rev, self.cfg,
                         include_unpublished=True, label="t1")
        self.assertEqual(len(rec["questions"]), 2)
        q1 = rec["questions"][0]
        self.assertEqual(q1["doc_recall"], 1.0)
        self.assertIsNotNone(q1["key_points"])
        self.assertEqual(E.runs(self.kb)[0]["id"], rec["id"])
        rec2 = E.run_eval(self.kb, Asker(self.kb, self.cards, self.comp), self.cards, self.rev, self.cfg,
                          ids=["q02"], include_unpublished=True, features={"themes": False, "facts": False})
        self.assertEqual(rec2["features"], {"themes": False, "facts": False})
        cmp = E.compare(self.kb, rec["id"], rec2["id"])
        self.assertEqual([r["id"] for r in cmp["questions"]], ["q02"])

    def test_bugs_found_by_the_first_real_eval_stay_fixed(self):
        asker = Asker(self.kb, self.cards, self.comp)
        # 1) leaf sections listed under "expand" must be read, not silently dropped
        r = asker.ask(self.rev, "[[MOCK:LEAFEXPAND]] model-based OPC segments EPE", self.cfg, include_unpublished=True)
        self.assertEqual(r["status"], "done", r.get("error"))
        self.assertTrue(r["navigation"]["sections"])
        # 2) a placeholder answer ("...") is rejected by the GENERATE graph and retried
        r = asker.ask(self.rev, "[[MOCK:PLACEHOLDER]] model-based OPC segments", self.cfg, include_unpublished=True)
        self.assertEqual(r["status"], "done", r.get("error"))
        self.assertNotEqual(r["answer"]["answer_md"].strip(), "...")
        self.assertIn(("answer", "correct"), [(g["graph"], g["node"]) for g in r["graph"]])


class TestTopicsOntologyEntities(Base):
    def setUp(self):
        super().setUp()
        PI.Indexer(self.kb, self.comp).run("admin", self.cfg)
        E.save_all(self.kb, "rev", GOLDEN)

    def _topics(self):
        run = T.TopicBuilder(self.kb, self.comp).build("admin", self.cfg)
        self.assertEqual(run["status"], "done", run.get("error"))
        return run

    def test_topic_graph_and_themes_in_tree(self):
        run = self._topics()
        st = T.status(self.kb)
        self.assertTrue(st["built"])
        self.assertFalse(st["stale"])
        self.assertGreaterEqual(st["topics"], 2)
        self.assertGreater(run["coverage"], 0.5)
        t = PI.knowledge_tree(self.kb, self.cards, readers=False)
        self.assertIn("t", t.roots())
        refs = [n for n in t.nodes.values() if n["kind"] == "ref"]
        self.assertTrue(refs and all(r["target"] in t.nodes for r in refs))
        H = PI.Handles(t)
        self.assertEqual(H.get(refs[0]["id"]), H.get(refs[0]["target"]))  # a reference reads as its section
        S.put(self.kb, "rev", [{"path": "opc/ilt.md", "text": S.read_text(self.kb, "opc/ilt.md") + "\n## New\n\nMore text.\n"}])
        self.assertTrue(T.status(self.kb)["stale"])

    def test_ontology_loop_propose_refine_approve_and_turtle(self):
        self._topics()
        loop = O.OntologyLoop(self.kb, self.comp)
        r1 = loop.propose("rev", self.cfg)
        self.assertEqual(r1["status"], "done", r1.get("error"))
        p1 = O.get(self.kb, r1["proposal"])
        self.assertEqual(p1["status"], "proposed")
        self.assertGreater(p1["checks"]["verified"], 0)  # evidence verified against the sources
        self.assertIn("Entity relations", p1["section"])
        with self.assertRaises(ValueError):
            loop.decide(self.rev, p1["id"], "approve", "")  # comment required
        with self.assertRaises(PermissionError):
            loop.decide(self.rev, p1["id"], "approve", "looks good")  # only admins approve
        r2 = loop.propose("rev", self.cfg, parent=p1["id"], feedback="rename the relation")
        self.assertEqual(O.get(self.kb, p1["id"])["status"], "superseded")
        v0 = SC.current(self.kb)["version"]
        rec = loop.decide(self.admin, r2["proposal"], "approve", "approved for the test")
        self.assertEqual(rec["status"], "approved")
        self.assertEqual(SC.current(self.kb)["version"], v0 + 1)
        onto = G.ontology(self.kb)
        self.assertIn("depends_on_model", onto["entity_relations"])
        self.assertEqual(onto["entity_relations"]["depends_on_model"]["domain"], {"method"})
        ttl = O.to_turtle(self.kb)
        self.assertIn("lkb:depends_on_model a owl:ObjectProperty", ttl)
        imp = O.from_turtle(self.kb, "rev", ttl)  # round trip → a new proposal for review
        self.assertEqual({t["id"] for t in imp["ontology"]["entity_types"]}, set(onto["entity_types"]))
        self.assertEqual(imp["ontology"]["entity_relations"][0]["domain"], ["method"])

    def test_extraction_graph_layer_and_facts(self):
        self._topics()
        loop = O.OntologyLoop(self.kb, self.comp)
        loop.decide(self.admin, loop.propose("rev", self.cfg)["proposal"], "approve", "ok for test")
        ex = Extractor(self.kb, self.comp)
        rep = ex.run("admin", self.cfg, limit=2)  # start small
        self.assertEqual(rep["documents"], 2)
        self.assertFalse(rep["failed"])
        self.assertEqual(ex.status()["extracted"], 2)
        pending = len(ex.status()["pending"])
        self.assertEqual(ex.run("admin", self.cfg)["documents"], pending)  # only the rest; nothing re-extracted
        self.assertEqual(ex.run("admin", self.cfg)["documents"], 0)
        st = ex.status()
        self.assertEqual(st["pending"], [])
        g = G.build(self.kb, self.cards, readers=False)
        self.assertGreater(sum(1 for e in g.edges if e["layer"] == "extracted"), 0)
        self.assertTrue(all(ev["check"] in ("exact", "moved", "elided")
                            for e in g.edges if e["layer"] == "extracted" and e.get("evidence") for ev in e["evidence"]))
        # the approved ontology changed → everything is pending again (cache keyed by ontology fingerprint)
        text = SC.current(self.kb)["text"].replace("- `depends_on_model`", "- `needs_model`")
        SC.save(self.kb, "admin", text, "rename relation")
        self.assertEqual(len(Extractor(self.kb, self.comp).status()["pending"]), st["documents"])

    def test_facts_reach_the_navigator(self):
        self._topics()
        loop = O.OntologyLoop(self.kb, self.comp)
        loop.decide(self.admin, loop.propose("rev", self.cfg)["proposal"], "approve", "ok for test")
        Extractor(self.kb, self.comp).run("admin", self.cfg)
        g = G.build(self.kb, self.cards, readers=False)
        ent = next(d for d in g.nodes.values() if d.get("kind") == "entity" and d.get("type") in ("method", "model"))
        facts = G.facts_for(self.kb, self.cards, False, f"what is {ent['title']}?")
        self.assertTrue(facts)
        r = Asker(self.kb, self.cards, self.comp).ask(self.rev, f"what is {ent['title']}?", self.cfg, include_unpublished=True)
        self.assertEqual(r["status"], "done", r.get("error"))
        self.assertTrue(r["navigation"]["facts"])
        self.assertIn("entity graph", self.comp.trace(r["id"])["nav-prompt.md"])


if __name__ == "__main__":
    unittest.main()
