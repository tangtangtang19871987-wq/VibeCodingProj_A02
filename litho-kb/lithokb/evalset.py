"""Golden question set and evaluation runs — "start with the query".

The questions a knowledge base must answer decide what it has to capture (which entity
and relation types the ontology needs, which topics matter) and they are the regression
test for every change: schema edits, model switches, retrieval changes.

Storage (plain files in the knowledge base, editable by people):
  eval/golden.jsonl        one question per line:
      {"id": "q01", "question": "...", "type": "broad|procedural|relational|comparative|numeric",
       "expected_sources": ["docs/a.md", ...],                     # documents a good answer draws on
       "expected_sections": [{"path": "docs/a.md", "title_contains": "..."}],
       "key_points": [{"label": "pixelated mask", "any": ["pixel", "..."]}],  # mechanically checked in the answer
       "notes": "...", "by": "...", "updated": "..."}
  eval/runs/<run>.json     one evaluation run: configuration snapshot, per-question metrics, aggregates

Metrics per question (all deterministic; the answer itself stays available for human judgement):
  doc_recall        expected documents that were read (sections read, or sources of cards read)
  section_recall    expected sections that were read
  key_points        share of key-point groups whose terms appear in the answer
  grounding         share of verifiable quotes in the answer (existing verifier)
  gap_reported      the answer declared missing material (good when the corpus lacks it)
"""
from __future__ import annotations

import json
import time

from .store import KB, LOCK, atomic_write, now

TYPES = ("broad", "procedural", "relational", "comparative", "numeric", "lookup")


def _path(kb: KB):
    return kb.root / "eval" / "golden.jsonl"


def _runs_dir(kb: KB):
    return kb.root / "eval" / "runs"


def load(kb: KB) -> list[dict]:
    p = _path(kb)
    if not p.exists():
        return []
    out = []
    for ln in p.read_text("utf-8").splitlines():
        if ln.strip():
            out.append(json.loads(ln))
    return out


def _normalize(q: dict, actor: str) -> dict:
    if not str(q.get("question", "")).strip():
        raise ValueError("question text is required")
    kp = []
    for k in q.get("key_points", []) or []:
        if isinstance(k, str):
            k = {"label": k, "any": [k]}
        terms = [str(t) for t in k.get("any", []) if str(t).strip()]
        if terms:
            kp.append({"label": str(k.get("label") or terms[0]), "any": terms})
    typ = q.get("type", "broad")
    return {"id": str(q.get("id", "")).strip(), "question": str(q["question"]).strip(),
            "type": typ if typ in TYPES else "broad",
            "expected_sources": [str(x) for x in q.get("expected_sources", []) or []],
            "expected_sections": [{"path": str(s.get("path", "")), "title_contains": str(s.get("title_contains", ""))}
                                  for s in q.get("expected_sections", []) or [] if isinstance(s, dict)],
            "key_points": kp, "notes": str(q.get("notes", "")), "by": q.get("by") or actor,
            "updated": now()}


def save_all(kb: KB, actor: str, questions: list[dict]) -> list[dict]:
    with LOCK:
        out, seen = [], set()
        for i, q in enumerate(questions, 1):
            n = _normalize(q, actor)
            n["id"] = n["id"] or f"q{i:02d}"
            if n["id"] in seen:
                raise ValueError(f"duplicate question id {n['id']}")
            seen.add(n["id"])
            out.append(n)
        atomic_write(_path(kb), "".join(json.dumps(q, ensure_ascii=False) + "\n" for q in out))
    kb.event(actor, "eval.questions.save", "", count=len(out))
    return out


def upsert(kb: KB, actor: str, q: dict) -> dict:
    qs = load(kb)
    n = _normalize(q, actor)
    if not n["id"]:
        n["id"] = f"q{len(qs) + 1:02d}"
    qs = [x for x in qs if x["id"] != n["id"]] + [n]
    qs.sort(key=lambda x: x["id"])
    save_all(kb, actor, qs)
    return n


# ---- running -------------------------------------------------------------------------------
def _score(q: dict, run: dict, cards) -> dict:
    nav = run.get("navigation", {})
    ans = (run.get("answer") or {}).get("answer_md", "")
    read_docs = {s["path"] for s in nav.get("sections", [])}
    for cid in nav.get("cards", []):
        try:
            head, _ = cards.load(cid)
            read_docs |= {s["path"] if isinstance(s, dict) else s for s in head.get("sources", [])}
        except Exception:  # noqa: BLE001
            pass
    exp = q.get("expected_sources", [])
    doc_hits = [p for p in exp if p in read_docs]
    sec_exp = q.get("expected_sections", [])
    sec_hits = [s for s in sec_exp if any(r["path"] == s["path"] and s["title_contains"].lower() in r["title"].lower()
                                          for r in nav.get("sections", []))]
    low = ans.lower()
    kp_hits = [k["label"] for k in q.get("key_points", []) if any(t.lower() in low for t in k["any"])]
    kp_miss = [k["label"] for k in q.get("key_points", []) if k["label"] not in kp_hits]
    ratio = lambda a, b: round(len(a) / len(b), 2) if b else None  # noqa: E731
    return {"id": q["id"], "question": q["question"], "type": q.get("type"), "run": run["id"],
            "status": run.get("status"), "error": run.get("error"),
            "doc_recall": ratio(doc_hits, exp), "docs_missed": [p for p in exp if p not in read_docs],
            "section_recall": ratio(sec_hits, sec_exp),
            "key_points": ratio(kp_hits, q.get("key_points", [])), "key_points_missed": kp_miss,
            "grounding": (run.get("grounding") or {}).get("score") if (run.get("grounding") or {}).get("total") else None,
            "gap_reported": bool(((run.get("answer") or {}).get("gaps") or "").strip()),
            "answerable": (run.get("answer") or {}).get("answerable"),
            "cards_read": len(nav.get("cards", [])), "sections_read": len(nav.get("sections", [])),
            "nav_rounds": len(nav.get("rounds", [])), "latency_s": run.get("latency_s"),
            "cost_usd": run.get("cost_usd"), "answer_chars": len(ans)}


METRICS = ("doc_recall", "section_recall", "key_points", "grounding")


def _aggregate(rows: list[dict]) -> dict:
    agg = {}
    for k in METRICS:
        vals = [r[k] for r in rows if isinstance(r.get(k), (int, float))]
        agg[k] = round(sum(vals) / len(vals), 3) if vals else None
    agg["failed"] = sum(r["status"] != "done" for r in rows)
    agg["not_fully_answerable"] = sum((r.get("answerable") or "full") != "full" for r in rows)
    agg["cost_usd"] = round(sum(r["cost_usd"] or 0 for r in rows), 6)
    agg["latency_s"] = round(sum(r["latency_s"] or 0 for r in rows), 1)
    return agg


def run_eval(kb: KB, asker, cards, user: dict, cfg: dict, ids: list[str] | None = None,
             include_unpublished: bool = False, label: str = "", features: dict | None = None,
             repeat: int = 1) -> dict:
    """Ask every question `repeat` times (LLM answers vary from run to run); the aggregate is the mean over
    repeats and `spread` gives min–max per metric, so changes can be told apart from noise."""
    from . import pageindex as PI
    from . import schema as SC
    from .ask import PROMPT_VERSION as ASK_PV
    qs = [q for q in load(kb) if not ids or q["id"] in ids]
    if not qs:
        raise ValueError("no questions to evaluate (eval/golden.jsonl is empty or ids not found)")
    rid = "eval-" + time.strftime("%Y%m%dT%H%M%S")
    t0 = time.time()
    reps = []
    for _ in range(max(1, int(repeat))):
        rows = []
        for q in qs:
            r = asker.ask(user, q["question"], cfg, include_unpublished=include_unpublished, features=features,
                          record_gaps=False)  # evaluation must not write knowledge-gap issues
            rows.append(_score(q, r, cards))
        reps.append(rows)
    per_rep = [_aggregate(rows) for rows in reps]
    agg = {k: (round(sum(a[k] for a in per_rep if a[k] is not None) / max(1, sum(a[k] is not None for a in per_rep)), 3)
               if any(a[k] is not None for a in per_rep) else None) for k in METRICS}
    for k in ("failed", "not_fully_answerable", "cost_usd", "latency_s"):
        agg[k] = round(sum(a[k] for a in per_rep), 6)
    spread = {k: [min(a[k] for a in per_rep if a[k] is not None), max(a[k] for a in per_rep if a[k] is not None)]
              for k in METRICS if any(a[k] is not None for a in per_rep)}
    questions = []
    for i, q in enumerate(qs):  # per question: mean over repeats, plus every repeat's run id
        rs = [rows[i] for rows in reps]
        row = dict(rs[-1])
        for k in METRICS:
            vals = [r[k] for r in rs if isinstance(r.get(k), (int, float))]
            row[k] = round(sum(vals) / len(vals), 2) if vals else None
        row["key_points_missed"] = sorted({m for r in rs for m in r["key_points_missed"]})
        row["runs"] = [r["run"] for r in rs]
        questions.append(row)
    st = PI.Indexer(kb, asker.comp).status()
    rec = {"id": rid, "label": label, "by": user["name"], "at": now(), "seconds": round(time.time() - t0, 1),
           "scope": "all" if include_unpublished else "published", "features": features or {}, "repeat": len(reps),
           "config": {"backend": cfg.get("backend"), "model": cfg.get("openrouter_model") if cfg.get("backend") == "openrouter"
                      else cfg.get("model"), "schema_version": SC.current(kb)["version"], "ask_prompt": ASK_PV,
                      "cards": len(cards.index()), "pageindex_compiled": f"{st['compiled']}/{st['documents']}"},
           "aggregate": agg, "spread": spread, "per_repeat": per_rep, "questions": questions}
    atomic_write(_runs_dir(kb) / f"{rid}.json", json.dumps(rec, ensure_ascii=False, indent=1))
    kb.event(user["name"], "eval.run", rid, questions=len(qs), repeat=len(reps), **{k: v for k, v in agg.items() if v is not None})
    return rec


def runs(kb: KB) -> list[dict]:
    d = _runs_dir(kb)
    out = []
    for p in sorted(d.glob("*.json"), reverse=True) if d.exists() else []:
        r = json.loads(p.read_text("utf-8"))
        out.append({k: r.get(k) for k in ("id", "label", "by", "at", "scope", "config", "aggregate", "spread", "repeat", "features")})
    return out


def get_run(kb: KB, rid: str) -> dict:
    if not rid.startswith("eval-") or "/" in rid:
        raise ValueError("bad run id")
    return json.loads((_runs_dir(kb) / f"{rid}.json").read_text("utf-8"))


def compare(kb: KB, a: str, b: str) -> dict:
    ra, rb = get_run(kb, a), get_run(kb, b)
    qa = {q["id"]: q for q in ra["questions"]}
    rows = []
    for q in rb["questions"]:
        p = qa.get(q["id"])
        row = {"id": q["id"], "question": q["question"]}
        for k in ("doc_recall", "section_recall", "key_points", "grounding"):
            row[k] = (p.get(k) if p else None, q.get(k))
        rows.append(row)
    return {"a": a, "b": b, "aggregate": {k: (ra["aggregate"].get(k), rb["aggregate"].get(k)) for k in rb["aggregate"]},
            "questions": rows}


__all__ = ["load", "save_all", "upsert", "run_eval", "runs", "get_run", "compare", "TYPES"]
