"""fsck — integrity check of the knowledge base files.

The files are the database, so they get a checker: heads vs immutable revisions,
published revisions present, evidence pointing at known sources, source files matching
their recorded sha256, parseable reviews / traces / logs, leftovers of interrupted
writes, orphaned derived caches. `--repair` only removes leftovers and rebuilds
derived caches; it never edits knowledge, reviews or sources.
"""
from __future__ import annotations

import json
import time

from . import sources as S
from .store import KB, sha256


def fsck(kb: KB, cards, repair: bool = False) -> dict:
    t0 = time.perf_counter()
    problems: list[dict] = []
    fixed: list[str] = []

    def bad(kind, target, detail):
        problems.append({"kind": kind, "target": target, "detail": detail})

    meta = S.load_meta(kb)
    for p, rec in meta.items():
        if rec.get("deleted"):
            continue
        f = kb.sources / p
        if not f.exists():
            bad("source_missing", p, "recorded in meta/sources.json but file is missing")
        elif sha256(f.read_bytes()) != rec.get("sha256"):
            bad("source_sha_mismatch", p, "file content differs from the recorded sha256 (edited outside LithoKB?)")
        for h in rec.get("history", [])[:-1]:
            hp = kb.history / f"{p}@{h['version']}"
            if not hp.exists():
                bad("source_history_missing", p, f"version {h['version']} not in history/")
    idx = cards.index()
    for cid, m in idx.items():
        rev = m.get("rev", 0)
        for r in range(1, rev + 1):
            if not (kb.revs_dir / cid / f"r{r:04d}.md").exists():
                bad("revision_missing", cid, f"r{r:04d} missing")
        try:
            rm, rb = cards.load_rev(cid, rev)
            if any(rm.get(k) != m.get(k) for k in ("title", "type", "summary")) or rb != m.get("_body"):
                bad("head_differs_from_revision", cid, f"head content ≠ r{rev:04d}")
        except Exception as e:  # noqa: BLE001
            bad("revision_unreadable", cid, str(e))
        if m.get("published_rev") and not (kb.revs_dir / cid / f"r{m['published_rev']:04d}.md").exists():
            bad("published_revision_missing", cid, f"published r{m['published_rev']} missing")
        for e in m.get("evidence", []):
            if e.get("path") and e["path"] not in meta:
                bad("evidence_unknown_source", cid, e["path"])
    rv = kb.reviews_dir
    for f in rv.glob("*.jsonl") if rv.exists() else []:
        raw = f.read_text("utf-8").splitlines()
        n_bad = sum(1 for ln in raw if ln.strip() and not _ok_json(ln))
        if n_bad:
            bad("review_lines_unparseable", f.stem, f"{n_bad} lines")
        if f.stem not in idx:
            bad("review_for_unknown_card", f.stem, "reviews exist but the card does not")
    raw = kb.events_path.read_text("utf-8").splitlines() if kb.events_path.exists() else []
    n_bad = sum(1 for ln in raw if ln.strip() and not _ok_json(ln))
    if n_bad:
        bad("events_lines_unparseable", "log/events.jsonl", f"{n_bad} lines (a crash during append?)")
    traces = 0
    for f in kb.traces_dir.glob("*/run.json") if kb.traces_dir.exists() else []:
        traces += 1
        if not _ok_json(f.read_text("utf-8")):
            bad("trace_unparseable", f.parent.name, "run.json")
    leftovers = [p for p in kb.root.rglob(".tmp-*")]
    for p in leftovers:
        bad("interrupted_write", str(p.relative_to(kb.root)), "temporary file from an interrupted write")
        if repair:
            p.unlink(missing_ok=True)
            fixed.append(f"removed {p.relative_to(kb.root)}")
    pi = kb.root / "compiled" / "pageindex"
    live = {rec["sha256"][:24] for rec in meta.values() if not rec.get("deleted")}
    for f in pi.glob("*.json") if pi.exists() else []:
        if f.stem not in live:
            bad("orphan_pageindex", f.name, "summary of a document version no longer current (harmless)")
            if repair:
                f.unlink()
                fixed.append(f"removed {f.name}")
    # derived structures added later: topic graph, entity-extraction cache, ontology proposals, evaluation runs,
    # answer cache — parseable, and caches that no longer correspond to current documents/ontology are orphans
    tp = kb.root / "compiled" / "topics.json"
    if tp.exists() and not _ok_json(tp.read_text("utf-8")):
        bad("topics_unparseable", "compiled/topics.json", "rebuild with lkb topics build")
    ed = kb.root / "compiled" / "entities"
    if ed.exists():
        from . import graph as G
        from .entities import fingerprint
        fp = fingerprint(G.ontology(kb))
        for f in ed.glob("*.json"):
            sha24, _, efp = f.stem.partition("-")
            if efp != fp or sha24 not in live:
                bad("orphan_entities", f.name, "extraction for an old document version or ontology (harmless)")
                if repair:
                    f.unlink()
                    fixed.append(f"removed {f.name}")
            elif not _ok_json(f.read_text("utf-8")):
                bad("entities_unparseable", f.name, "re-extract with lkb extract --force")
    for sub, kind in (("ontology/proposals", "proposal_unparseable"), ("eval/runs", "eval_run_unparseable")):
        d = kb.root / sub
        for f in d.glob("*.json") if d.exists() else []:
            if not _ok_json(f.read_text("utf-8")):
                bad(kind, f"{sub}/{f.name}", "unparseable JSON")
    cd = kb.traces_dir / "_cache"
    for f in cd.glob("*.json") if cd.exists() else []:
        try:
            rid = json.loads(f.read_text("utf-8"))["run"]
            ok = (kb.traces_dir / rid / "run.json").exists()
        except (json.JSONDecodeError, KeyError):
            ok = False
        if not ok:
            bad("stale_answer_cache", f.name, "points to a missing trace")
            if repair:
                f.unlink()
                fixed.append(f"removed cache entry {f.name}")
    if repair:
        from . import graph as G, pageindex as PI
        G._CACHE.clear()
        PI._TREE_CACHE.clear()
        PI._SEC_IDX.clear()
        cards._index = None
        cards._files = {}
        cards.index()
        fixed.append("rebuilt in-memory indexes")
    return {"ok": not [p for p in problems if p["kind"] not in ("orphan_pageindex", "orphan_entities")], "cards": len(idx),
            "sources": sum(1 for r in meta.values() if not r.get("deleted")), "traces": traces,
            "problems": problems, "fixed": fixed, "seconds": round(time.perf_counter() - t0, 3)}


def _ok_json(s: str) -> bool:
    try:
        json.loads(s)
        return True
    except json.JSONDecodeError:
        return False


__all__ = ["fsck"]
