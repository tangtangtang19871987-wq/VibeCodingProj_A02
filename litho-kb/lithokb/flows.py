"""LangGraph flows — every LLM call in LithoKB runs as a LangGraph state graph.

Two reusable graphs, plus the pipeline graphs built on them (compile, ask/navigate,
hub overviews, consolidation; see compiler.py / ask.py / wiki.py / consolidate.py):

1. CALL graph — one model call, with its recovery policy as explicit edges

       START → invoke ──result──────────────→ finish → END
                  │ ├─watchdog abort→ step_down ─┐
                  │ └─transient error→ backoff ──┤
                  └──────────── ↺ invoke ←───────┘

   * step_down: the reasoning watchdog aborted a call that kept thinking without writing
     any answer → retry one reasoning-effort level lower (high → medium → low → none).
   * backoff: HTTP 429/5xx or connection errors → wait and retry (≤ 2 retries).
   The path through the graph is returned in `raw_meta["graph_path"]` and lands in the trace.

2. GENERATE graph — structured generation with validation and corrective retry

       START → generate → check ──ok────────────→ END
                  ↑         └─unusable→ correct ─┐
                  └──────────────────────────────┘

   `check` runs a caller-supplied parser/validator; `correct` appends a correction note
   describing what was wrong. Used for compile (cards JSON), hub overviews, consolidation.

Graphs are compiled once per process and are stateless between runs (no checkpointer):
the knowledge base's files remain the only state.
"""
from __future__ import annotations

import operator
import time
from typing import Annotated, Any, Callable, TypedDict

from langgraph.graph import END, START, StateGraph

LADDER = ["high", "medium", "low", "none"]
MAX_TRANSIENT_RETRIES = 2


# ---------------------------------------------------------------- 1. CALL graph
class CallState(TypedDict, total=False):
    cfg: dict
    system: str
    user: str
    effort: str
    result: Any
    error: str
    outcome: str  # result | abort | transient | fatal
    abort: dict
    aborts: Annotated[list, operator.add]
    transient: int
    path: Annotated[list, operator.add]


def _invoke(state: CallState) -> dict:
    from . import llm
    cfg = dict(state["cfg"])
    if state.get("effort"):
        cfg["openrouter_reasoning"] = state["effort"]
    try:
        r = llm.attempt(cfg, state["system"], state["user"])
        return {"result": r, "outcome": "result", "path": ["invoke"]}
    except llm.WatchdogAbort as e:
        return {"outcome": "abort", "abort": e.info, "path": ["invoke"]}
    except llm.TransientLLMError as e:
        return {"outcome": "transient", "error": str(e), "path": ["invoke"]}
    except llm.LLMError as e:
        return {"outcome": "fatal", "error": str(e), "path": ["invoke"]}


def _route_call(state: CallState) -> str:
    o = state.get("outcome")
    if o == "abort":
        return "step_down"
    if o == "transient" and state.get("transient", 0) < MAX_TRANSIENT_RETRIES:
        return "backoff"
    return "finish"


def _step_down(state: CallState) -> dict:
    cur = state.get("effort") or state["cfg"].get("openrouter_reasoning", "low") or "none"
    lower = LADDER[min(len(LADDER) - 1, LADDER.index(cur) + 1)] if cur in LADDER else "none"
    return {"effort": lower, "aborts": [{**state.get("abort", {}), "effort": cur, "retry_with": lower}],
            "path": ["step_down"]}


def _backoff(state: CallState) -> dict:
    n = state.get("transient", 0) + 1
    time.sleep(float(state["cfg"].get("backoff_s", 4)) * n)
    return {"transient": n, "path": ["backoff"]}


def _finish(state: CallState) -> dict:
    return {"path": ["finish"]}


def _build_call_graph():
    g = StateGraph(CallState)
    g.add_node("invoke", _invoke)
    g.add_node("step_down", _step_down)
    g.add_node("backoff", _backoff)
    g.add_node("finish", _finish)
    g.add_edge(START, "invoke")
    g.add_conditional_edges("invoke", _route_call, {"step_down": "step_down", "backoff": "backoff", "finish": "finish"})
    g.add_edge("step_down", "invoke")
    g.add_edge("backoff", "invoke")
    g.add_edge("finish", END)
    return g.compile()


_CALL = None


def run_call(cfg: dict, system: str, user: str):
    """Run one LLM call through the CALL graph. Returns an llm.LLMResult or raises llm.LLMError."""
    from . import llm
    global _CALL
    if _CALL is None:
        _CALL = _build_call_graph()
    t0 = time.time()
    out = _CALL.invoke({"cfg": cfg, "system": system, "user": user, "aborts": [], "path": [], "transient": 0},
                       config={"recursion_limit": 40})
    r = out.get("result")
    if r is None or out.get("outcome") != "result":
        raise llm.LLMError(out.get("error") or "LLM call failed")
    r.latency_s = round(time.time() - t0, 3)
    r.raw_meta = {**(r.raw_meta or {}), "graph_path": out.get("path", [])}
    if out.get("aborts"):
        r.raw_meta["watchdog_aborts"] = out["aborts"]
    if out.get("transient"):
        r.raw_meta["transient_retries"] = out["transient"]
    return r


# ---------------------------------------------------------------- 2. GENERATE graph
class GenState(TypedDict, total=False):
    prompt: str
    attempt: int
    result: Any
    data: Any
    error: str
    errors: Annotated[list, operator.add]
    path: Annotated[list, operator.add]


def generate(*, comp, run: dict, cfg: dict, system: str, user: str,
             check: Callable[[Any], Any], correction: Callable[[str], str],
             max_attempts: int = 2, prefix: str = "", graph: str = "generate",
             on_event: Callable[..., None] | None = None):
    """generate → check → (correct → generate)* — returns (data, last LLMResult, attempts).
    `check(result)` returns parsed data or raises ValueError; `correction(error)` returns the
    text appended to the original prompt for the next attempt. Raises the last error when
    every attempt was unusable. Every node visit is recorded in run["graph"]."""
    ev = on_event or (lambda *a, **k: None)

    def n_generate(s: GenState) -> dict:
        a = s.get("attempt", 0) + 1
        p = prefix if a == 1 else f"{prefix}retry{a - 1}-"
        res = comp.llm_step(run, cfg, system, s["prompt"], prefix=p)
        mark(run, graph, "generate", attempt=a)
        ev("llm_returned", attempt=a, latency_s=res.latency_s, stop_reason=res.stop_reason)
        return {"attempt": a, "result": res, "path": ["generate"]}

    def n_check(s: GenState) -> dict:
        try:
            data = check(s["result"])
            mark(run, graph, "check", ok=True)
            return {"data": data, "error": "", "path": ["check"]}
        except (ValueError, TypeError, KeyError) as e:
            msg = f"{type(e).__name__}: {e}"
            mark(run, graph, "check", ok=False, error=msg[:200])
            ev("invalid_response", attempt=s["attempt"], error=str(e)[:200])
            return {"data": None, "error": msg, "errors": [f"attempt {s['attempt']}: {msg}"], "path": ["check"]}

    def route(s: GenState) -> str:
        if not s.get("error"):
            return "done"
        return "correct" if s["attempt"] < max_attempts else "done"

    def n_correct(s: GenState) -> dict:
        mark(run, graph, "correct")
        return {"prompt": user + correction(s["error"]), "path": ["correct"]}

    g = StateGraph(GenState)
    g.add_node("generate", n_generate)
    g.add_node("check", n_check)
    g.add_node("correct", n_correct)
    g.add_edge(START, "generate")
    g.add_edge("generate", "check")
    g.add_conditional_edges("check", route, {"correct": "correct", "done": END})
    g.add_edge("correct", "generate")
    out = g.compile().invoke({"prompt": user, "attempt": 0, "errors": [], "path": []},
                             config={"recursion_limit": 4 * max_attempts + 8})
    if out.get("errors"):
        run.setdefault("attempt_errors", []).extend(out["errors"])
    if out.get("error"):
        raise ValueError(out["error"])
    return out["data"], out["result"], out["attempt"]


def mark(run: dict, graph: str, node: str, **kw) -> None:
    """Record a node visit of a pipeline graph in the run (shown in the LLM-trace UI)."""
    run.setdefault("graph", []).append({"graph": graph, "node": node, **kw})


__all__ = ["run_call", "generate", "mark", "LADDER"]
