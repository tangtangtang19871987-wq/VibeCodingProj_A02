"""Evidence forms (artifact types), form-aware retrieval and functional units. Offline (mock backend)."""
import shutil
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

from test_lkb import EXAMPLES, fresh_kb, user  # noqa: E402

from lithokb import artifacts as AF  # noqa: E402
from lithokb import ontology as O  # noqa: E402
from lithokb import pageindex as PI  # noqa: E402
from lithokb import sources as S  # noqa: E402
from lithokb import topics as T  # noqa: E402
from lithokb import units as U  # noqa: E402
from lithokb.ask import Asker  # noqa: E402
from lithokb.cards import Cards  # noqa: E402
from lithokb.compiler import Compiler  # noqa: E402
from lithokb.entities import Extractor  # noqa: E402
from lithokb.retrieve import retrieve  # noqa: E402


class TestDetectors(unittest.TestCase):
    def test_section_types(self):
        text = ("| a | b |\n|---|---|\n| 1 | 2 |\n\n```\nx = 1\n```\n$$ I = \\sum_k \\lambda_k $$\n"
                "1. first\n2. second\nThe minimum spacing is 10 nm and must not be smaller.\nA warning is raised.\n")
        self.assertEqual(set(AF.section_types(text)),
                         {"table", "code", "formula", "procedure", "value", "constraint", "diagnostic"})
        self.assertEqual(AF.section_types("Plain descriptive prose without anything special."), [])

    def test_needed_types_and_coverage(self):
        self.assertIn("value", AF.needed_types("What is the default value of the threshold?"))
        self.assertIn("procedure", AF.needed_types("What are the steps of the flow?"))
        self.assertIn("formula", AF.needed_types("How is the gradient computed?"))
        self.assertIn("constraint", AF.needed_types("Which constraints conflict?"))
        self.assertIn("procedure", AF.needed_types("\u6709\u54ea\u4e9b\u4e2d\u95f4\u6b65\u9aa4"))  # Chinese: "which intermediate steps"
        self.assertEqual(AF.coverage(["table", "value"], ["value"]), 0.5)
        self.assertEqual(AF.coverage([], ["value"]), 1.0)


class TestFormAwareRetrieval(unittest.TestCase):
    def setUp(self):
        self.kb = fresh_kb()
        S.put_dir(self.kb, "rev", str(EXAMPLES))
        self.cards = Cards(self.kb)
        self.comp = Compiler(self.kb, self.cards)
        self.comp.start("admin", self.comp.plan(None), backend="mock", background=False)
        self.cfg = {**self.kb.config["llm"], "backend": "mock"}

    def tearDown(self):
        shutil.rmtree(self.kb.root)

    def test_tree_shows_forms_and_navigation_records_needed_forms(self):
        t = PI.knowledge_tree(self.kb, self.cards, readers=False)
        hop = next(n for n in t.nodes.values() if n["kind"] == "section" and "formula" in n.get("types", []))
        H = PI.Handles(t)
        self.assertIn("formula", t.line(hop["id"], H.get(hop["id"]), 0))
        H.show_forms = False
        self.assertNotIn("formula", t.line(hop["id"], H.get(hop["id"]), 0, forms=False))
        r = Asker(self.kb, self.cards, self.comp).ask(user(self.kb, "rev"), "How is the TCC decomposition computed?",
                                                      self.cfg, include_unpublished=True)
        self.assertEqual(r["status"], "done", r.get("error"))
        self.assertIn("formula", r["navigation"]["needed_types"])
        off = Asker(self.kb, self.cards, self.comp).ask(user(self.kb, "rev"), "How is the TCC decomposition computed?",
                                                        self.cfg, include_unpublished=True, features={"types": False})
        self.assertEqual(off["navigation"]["needed_types"], [])

    def test_units_built_from_entity_graph_and_in_retrieve(self):
        PI.Indexer(self.kb, self.comp).run("admin", self.cfg)
        T.TopicBuilder(self.kb, self.comp).build("admin", self.cfg)
        loop = O.OntologyLoop(self.kb, self.comp)
        loop.decide(user(self.kb, "admin"), loop.propose("rev", self.cfg)["proposal"], "approve", "ok for test")
        Extractor(self.kb, self.comp).run("admin", self.cfg)
        units, _ = U.build(self.kb, self.cards, readers=False)
        self.assertTrue(units)
        for u in units.values():
            self.assertLessEqual(len(u["occurrences"]), U.MAX_OCC)
            self.assertTrue(all(o["section"].startswith("s:") and o["start"] <= o["end"] for o in u["occurrences"]))
            self.assertEqual(u["cross_document"], len(u["documents"]) >= 2 and len(u["forms"]) >= 2)
        anchor = next(iter(units.values()))["anchor"]
        r = retrieve(self.kb, self.cards, anchor, readers=False)
        self.assertIn("units", r)
        self.assertIn("needed_forms", r)


if __name__ == "__main__":
    unittest.main()
