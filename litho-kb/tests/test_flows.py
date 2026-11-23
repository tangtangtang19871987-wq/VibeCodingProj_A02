"""LangGraph flows: every LLM call runs through the CALL graph; pipelines are graphs (offline, mock backend)."""
import shutil
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

from test_lkb import EXAMPLES, fresh_kb, user  # noqa: E402

from lithokb import llm  # noqa: E402
from lithokb import sources as S  # noqa: E402
from lithokb.ask import Asker  # noqa: E402
from lithokb.cards import Cards  # noqa: E402
from lithokb.compiler import Compiler  # noqa: E402

MOCK = {"backend": "mock", "backoff_s": 0}


class TestCallGraph(unittest.TestCase):
    def test_plain_call_goes_through_the_graph(self):
        r = llm.call(MOCK, "[[LKB:INDEX]]", '<doc path="a.md" title="T" lines="1">\n# Table of contents\n\n# Text\n    1|x\n</doc>')
        self.assertEqual(r.raw_meta["graph_path"], ["invoke", "finish"])

    def test_watchdog_abort_steps_down_reasoning_effort(self):
        r = llm.call({**MOCK, "openrouter_reasoning": "high"}, "sys", "[[MOCK:WATCHDOG]] <source path=\"x.md\">\n    1|# A\n</source>")
        self.assertEqual(r.raw_meta["graph_path"], ["invoke", "step_down", "invoke", "step_down", "invoke", "finish"])
        self.assertEqual([a["effort"] for a in r.raw_meta["watchdog_aborts"]], ["high", "medium"])
        self.assertEqual(r.raw_meta["watchdog_aborts"][-1]["retry_with"], "low")

    def test_transient_error_backs_off_and_retries(self):
        r = llm.call(MOCK, "sys", "[[MOCK:FLAKY]] unique-1 <source path=\"x.md\">\n    1|# A\n</source>")
        self.assertEqual(r.raw_meta["graph_path"], ["invoke", "backoff", "invoke", "finish"])
        self.assertEqual(r.raw_meta["transient_retries"], 1)

    def test_fatal_error_is_raised(self):
        with self.assertRaises(llm.LLMError):
            llm.call({"backend": "nope"}, "s", "u")


class TestPipelineGraphs(unittest.TestCase):
    def setUp(self):
        self.kb = fresh_kb()
        S.put_dir(self.kb, "rev", str(EXAMPLES))
        self.cards = Cards(self.kb)
        self.comp = Compiler(self.kb, self.cards)

    def tearDown(self):
        shutil.rmtree(self.kb.root)

    def test_compile_retry_is_a_graph_edge(self):
        S.put(self.kb, "rev", [{"path": "x/degenerate.md", "text": "# Degenerate\n\n[[MOCK:DEGENERATE]] Some text here.\n"}])
        run = self.comp.run_once("admin", ["x/degenerate.md"], {**self.kb.config["llm"], **MOCK})
        self.assertEqual(run["status"], "done", run.get("error"))
        nodes = [(g["graph"], g["node"]) for g in run["graph"]]
        self.assertEqual(nodes, [("compile", "generate"), ("compile", "check"), ("compile", "correct"),
                                 ("compile", "generate"), ("compile", "check")])
        self.assertEqual(run["attempts"], 2)
        self.assertTrue(all(c["graph_path"][-1] == "finish" for c in run["calls"]))

    def test_ask_runs_navigate_read_answer_verify(self):
        self.comp.start("admin", self.comp.plan(None), backend="mock", background=False)
        r = Asker(self.kb, self.cards, self.comp).ask(user(self.kb, "rev"), "limitations of the Hopkins model",
                                                      {**self.kb.config["llm"], **MOCK}, include_unpublished=True)
        self.assertEqual(r["status"], "done", r.get("error"))
        ask_nodes = [g["node"] for g in r["graph"] if g["graph"] == "ask"]
        self.assertEqual(ask_nodes, ["navigate", "read", "answer", "verify"])
        self.assertTrue(any(g["graph"] == "navigate" and g["node"] == "decide" for g in r["graph"]))
        self.assertEqual(r["navigation"]["method"], "tree-search/langgraph")


if __name__ == "__main__":
    unittest.main()
