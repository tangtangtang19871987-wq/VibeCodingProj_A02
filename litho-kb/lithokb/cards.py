"""Layer 1 — compiled knowledge cards, their revisions, and the governance workflow.

A card is one Markdown file with frontmatter. Every change (LLM compile or human
edit) creates an immutable revision snapshot; reviews attach to a specific
revision. Readers only ever see the *published* revision.

Review status of the head revision:
    draft ─submit→ in_review ─approve(xN)→ approved ─publish→ published
                       │ request_changes        │ return (打回)
                       ▼                        ▼
                changes_requested ◀────────────┘   ─edit/recompile→ in_review
                       reject → rejected ─reopen→ in_review
Lifecycle of the card as a whole (admin):  active | withdrawn (下架) | superseded (被替换)
A new revision of a published card goes through review again while the old
published revision stays visible to readers until the new one is published.
"""
from __future__ import annotations

import difflib
import unicodedata
import json
import re
from pathlib import Path

from . import fm
from . import sources as S
from .store import KB, LOCK, append_jsonl, atomic_write, now, read_jsonl

CARD_TYPES = ("topic", "summary", "concept", "method", "model", "algorithm", "parameter", "metric",
              "process", "tool", "material", "equipment", "issue", "result", "synthesis", "person_or_org")
RELATIONS = ("is_a", "part_of", "subtopic_of", "uses", "depends_on", "implements", "improves",
             "alternative_to", "contrasts_with", "causes", "mitigates", "measured_by",
             "parameter_of", "input_to", "output_of", "example_of", "contradicts", "covers", "related_to")
BASES = ("extracted", "inferred", "ambiguous")  # epistemic status of a relation
STATUSES = ("draft", "in_review", "changes_requested", "approved", "rejected", "published")
VERDICTS = ("approve", "request_changes", "reject", "comment")
_ID_RE = re.compile(r"[^a-z0-9]+")
WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")


class CardError(Exception):
    pass


def slug(s: str) -> str:
    s = _ID_RE.sub("-", s.lower()).strip("-")
    return s[:80]


def summary_id(path: str) -> str:
    """Deterministic id of a document's summary card (OpenKB's per-document layer)."""
    return slug("summary-" + path)[:80].strip("-")


# ---- evidence grounding: mechanical check that quotes really are in the source ----
_MARKS = re.compile(r"[`*_>#|~]|^\s*(?:[-+]|\d+[.)])\s+", re.M)
# segment separators inside a quote: ellipses, line breaks (multi-line quotes often keep only the start of each
# line) and the " — " the outline uses between heading and gist (models sometimes quote the outline view)
_ELLIPSIS = re.compile(r"…+|\.{3,}|。。。|\n+| — ")
_QUOTES = str.maketrans({"“": '"', "”": '"', "„": '"', "‟": '"', "「": '"', "」": '"', "‘": "'", "’": "'", "『": '"', "』": '"'})


def _norm(s: str) -> str:
    """Comparison form: Markdown markers and list bullets removed, ALL whitespace removed,
    lower-cased. Removing (not replacing) markers matters for CJK text, where a marker
    turned into a space would break an otherwise verbatim match."""
    s = unicodedata.normalize("NFKC", s).translate(_QUOTES)  # full/half width, curly/straight quotes
    s = re.sub(r"\\([\\`*_{}\[\]()#+\-.!|>~])", r"\1", s)  # Markdown escapes (e.g. "\|" in converted tables)
    return re.sub(r"\s+", "", _MARKS.sub("", s)).lower()


def _find_in_order(segs: list[str], hay: str) -> bool:
    pos = 0
    for sg in segs:
        k = hay.find(sg, pos)
        if k < 0:
            return False
        pos = k + len(sg)
    return True


def verify_evidence(kb: KB, ev: dict, text_cache: dict | None = None) -> dict:
    """Return ev + {check, found_lines, sha}. check:
    exact   – quote found verbatim (modulo Markdown markers/whitespace) in the cited lines
    moved   – found verbatim, but elsewhere in the document (citation drift)
    elided  – quote abbreviated with "…": every segment found, in order, in the cited lines
    fuzzy   – substantial overlap only (likely paraphrase) → needs human eyes
    missing – not found;  no_source – the cited document does not exist"""
    text_cache = text_cache if text_cache is not None else {}
    path = ev.get("path", "")
    out = dict(ev)
    try:
        if path not in text_cache:
            text_cache[path] = S.read_text(kb, path)
        text = text_cache[path]
    except Exception:
        out["check"] = "no_source"
        return out
    lines = text.splitlines()
    out["sha"] = S.load_meta(kb).get(path, {}).get("sha256", "")
    raw = ev.get("quote", "")
    whole = _norm(raw)  # line breaks vanish in the comparison form: a verbatim multi-line quote is one string
    segs = [x for x in (_norm(t) for t in _ELLIPSIS.split(raw)) if len(x) >= 2]
    multi = len(segs) > 1 or bool(re.search(r"…|\.{3,}|。。。", raw))  # a trailing "…" also marks an abbreviation
    a, b = _parse_lines(ev.get("lines", ""), len(lines))
    window = _norm("\n".join(lines[a - 1:b])) if a else ""
    if not whole:
        out["check"] = "missing"
        return out
    if window and whole in window:
        out["check"], out["found_lines"] = "exact", f"{a}-{b}"
        return out
    if multi and window and _find_in_order(segs, window):
        out["check"], out["found_lines"] = "elided", f"{a}-{b}"
        return out
    # citation drift: search the document with a sliding line window
    norm_lines = [_norm(x) for x in lines]
    for i in range(len(lines)):
        acc = ""
        for j in range(i, min(i + 60, len(lines))):
            acc += norm_lines[j]
            if whole in acc:
                out["check"], out["found_lines"] = "moved", f"{i + 1}-{j + 1}"
                return out
            if multi and _find_in_order(segs, acc):
                out["check"], out["found_lines"] = "elided", f"{i + 1}-{j + 1}"
                return out
            if len(acc) > len(whole) * 3 + 300:
                break
    if window:
        sm = difflib.SequenceMatcher(None, whole, window, autojunk=False)
        covered = sum(blk.size for blk in sm.get_matching_blocks() if blk.size >= 4)
        ratio = covered / max(1, len(whole))
        if ratio >= 0.6:
            out["check"], out["found_lines"], out["overlap"] = "fuzzy", f"{a}-{b}", round(ratio, 2)
            return out
    out["check"] = "missing"
    return out


def _parse_lines(spec, n: int) -> tuple[int, int]:
    m = re.match(r"\s*L?(\d+)\s*(?:[-–:]\s*L?(\d+))?", str(spec or ""))
    if not m:
        return 0, 0
    a = max(1, int(m.group(1)))
    b = min(n, int(m.group(2) or a))
    return (a, max(a, b)) if a <= n else (0, 0)


def grounding(evidence: list[dict]) -> dict:
    c = {"exact": 0, "moved": 0, "elided": 0, "card": 0, "fuzzy": 0, "missing": 0, "no_source": 0}
    for e in evidence:
        c[e.get("check", "missing")] = c.get(e.get("check", "missing"), 0) + 1
    total = len(evidence)
    c["total"] = total
    c["score"] = round((c["exact"] + c["moved"] + c["elided"] + c["card"] + 0.5 * c["fuzzy"]) / total, 2) if total else 0.0
    return c


# ---- persistence --------------------------------------------------------------
class Cards:
    def __init__(self, kb: KB):
        self.kb = kb
        self._index: dict[str, dict] | None = None
        self._stamp = None

    def _card_path(self, cid: str) -> Path:
        return self.kb.cards_dir / f"{cid}.md"

    def _rev_path(self, cid: str, rev: int) -> Path:
        return self.kb.revs_dir / cid / f"r{rev:04d}.md"

    def load(self, cid: str) -> tuple[dict, str]:
        p = self._card_path(cid)
        if not p.exists():
            raise CardError(f"no card {cid}")
        meta, body, _ = fm.split(p.read_text("utf-8"))
        return meta, body

    def load_rev(self, cid: str, rev: int) -> tuple[dict, str]:
        p = self._rev_path(cid, rev)
        if not p.exists():
            raise CardError(f"no revision {cid}@r{rev}")
        meta, body, _ = fm.split(p.read_text("utf-8"))
        return meta, body

    def exists(self, cid: str) -> bool:
        return self._card_path(cid).exists()

    def _write_head(self, meta: dict, body: str) -> None:
        atomic_write(self._card_path(meta["id"]), fm.dump(meta, body))
        self._index = None

    # ---- in-memory index (rebuilt lazily when files change) -----------------
    def index(self) -> dict[str, dict]:
        d = self.kb.cards_dir
        sm = self.kb.meta / "sources.json"
        stamp = ((d.stat().st_mtime_ns, len(list(d.glob("*.md"))),
                  sm.stat().st_mtime_ns if sm.exists() else 0) if d.exists() else None)
        if self._index is not None and stamp == self._stamp:
            return self._index
        idx = {}
        src_meta = S.load_meta(self.kb)
        for p in sorted(d.glob("*.md")) if d.exists() else []:
            meta, body, _ = fm.split(p.read_text("utf-8"))
            meta["stale_sources"] = [s["path"] for s in meta.get("sources", [])
                                     if src_meta.get(s["path"], {}).get("sha256") != s.get("sha")
                                     or src_meta.get(s["path"], {}).get("deleted")]
            meta["_links"] = sorted({slug(x) for x in WIKILINK_RE.findall(body)})
            meta["_text"] = (meta.get("title", "") + " " + " ".join(meta.get("aliases", [])) + " "
                             + meta.get("summary", "") + " " + body).lower()
            idx[meta["id"]] = meta
        self._index, self._stamp = idx, stamp
        return idx

    def listing(self, status: str | None = None, visible_only: bool = False) -> list[dict]:
        out = []
        for m in self.index().values():
            if visible_only and not is_public(m):
                continue
            if status and m.get("status") != status and m.get("lifecycle") != status:
                continue
            out.append({k: v for k, v in m.items() if not k.startswith("_")})
        return sorted(out, key=lambda m: (m.get("type") != "topic", m.get("title", "").lower()))

    # ---- write a new revision ---------------------------------------------------
    def new_revision(self, actor: str, card: dict, body: str, origin: dict, change_note: str = "",
                     status: str = "in_review") -> dict:
        """card: id,title,type,parent,aliases,summary,relations,evidence,sources,confidence."""
        cid = card["id"]
        if not cid or slug(cid) != cid:
            raise CardError(f"bad card id {cid!r}")
        with LOCK:
            head = self.load(cid)[0] if self.exists(cid) else None
            rev = (head["rev"] + 1) if head else 1
            cache: dict = {}
            evidence = [verify_evidence(self.kb, e, cache) for e in card.get("evidence", [])]
            src_meta = S.load_meta(self.kb)
            srcs = sorted({e["path"] for e in evidence} | {s if isinstance(s, str) else s["path"]
                                                           for s in card.get("sources", [])})
            meta = {
                "id": cid,
                "title": card.get("title") or cid,
                "type": card.get("type") if card.get("type") in CARD_TYPES else "concept",
                "parent": card.get("parent", "") or "",
                "aliases": list(card.get("aliases", [])),
                "summary": card.get("summary", ""),
                "relations": [{**r, "target": slug(str(r["target"])),
                               "basis": r.get("basis") if r.get("basis") in BASES else
                               ("extracted" if origin.get("kind") == "human" else "inferred")}
                              for r in card.get("relations", []) if r.get("target")],
                "evidence": evidence,
                "grounding": grounding(evidence),
                "sources": [{"path": p, "sha": src_meta.get(p, {}).get("sha256", ""),
                             "version": src_meta.get(p, {}).get("version")} for p in srcs],
                "confidence": card.get("confidence", None),
                "rev": rev,
                "parent_rev": head["rev"] if head else None,
                "origin": origin,  # {"kind":"llm","run":..,"model":..} | {"kind":"human","user":..}
                "change_note": change_note,
                "created": now(),
            }
            atomic_write(self._rev_path(cid, rev), fm.dump(meta, body))
            head_meta = dict(meta)
            head_meta.update(
                status=status,
                published_rev=head.get("published_rev") if head else None,
                lifecycle=head.get("lifecycle", "active") if head else "active",
                replaced_by=head.get("replaced_by", "") if head else "",
                created_first=head.get("created_first", meta["created"]) if head else meta["created"],
                updated=meta["created"],
            )
            self._write_head(head_meta, body)
        self.kb.event(actor, "card.revision", cid, rev=rev, origin=origin.get("kind"), run=origin.get("run", ""),
                      grounding=meta["grounding"]["score"], note=change_note)
        return head_meta

    def human_edit(self, user: dict, cid: str, changes: dict) -> dict:
        meta, body = self.load(cid)
        card = {k: meta.get(k) for k in ("id", "title", "type", "parent", "aliases", "summary",
                                         "relations", "evidence", "sources", "confidence")}
        card["evidence"] = [{k: v for k, v in e.items() if k in ("id", "path", "lines", "quote")}
                            for e in card["evidence"] or []]
        for k in ("title", "type", "parent", "aliases", "summary", "relations", "evidence"):
            if k in changes:
                card[k] = changes[k]
        new_body = changes.get("body", body)
        return self.new_revision(user["name"], card, new_body, {"kind": "human", "user": user["name"]},
                                 change_note=changes.get("change_note", "human edit"))

    def reverify(self, actor: str) -> dict:
        """Re-run evidence verification on every head revision (the checks are derived data:
        when the verifier improves, stored results can be refreshed without a new revision)."""
        changed, total = [], 0
        cache: dict = {}
        with LOCK:
            for cid in list(self.index()):
                meta, body = self.load(cid)
                ev = [verify_evidence(self.kb, {k: e[k] for k in ("id", "path", "lines", "quote") if k in e}, cache)
                      for e in meta.get("evidence", [])]
                total += len(ev)
                if [e.get("check") for e in ev] != [e.get("check") for e in meta.get("evidence", [])]:
                    meta["evidence"], meta["grounding"] = ev, grounding(ev)
                    self._write_head(meta, body)
                    changed.append(cid)
        self.kb.event(actor, "cards.reverify", "*", evidence=total, changed=changed[:200])
        return {"evidence": total, "cards_changed": changed}

    # ---- reviews -----------------------------------------------------------------
    def reviews(self, cid: str) -> list[dict]:
        return read_jsonl(self.kb.reviews_dir / f"{cid}.jsonl")

    def review_summary(self, cid: str, rev: int) -> dict:
        rs = [r for r in self.reviews(cid) if r.get("rev") == rev and r["kind"] == "review"]
        latest: dict[str, dict] = {}
        for r in rs:  # a reviewer's latest verdict on this revision counts
            if r["verdict"] != "comment":
                latest[r["user"]] = r
        votes = {"approve": 0, "request_changes": 0, "reject": 0}
        for r in latest.values():
            votes[r["verdict"]] += 1
        return {"votes": votes, "reviewers": sorted(latest), "comments": len(rs)}

    def act(self, user: dict, cid: str, action: str, comment: str = "", target: str = "",
            anchor: str = "") -> dict:
        """The single entry point for every workflow transition (UI, API and CLI)."""
        from .auth import require
        cfg = self.kb.config["review"]
        with LOCK:
            meta, body = self.load(cid)
            st, rev = meta["status"], meta["rev"]
            rec = {"ts": now(), "user": user["name"], "role": user["role"], "rev": rev, "kind": "review",
                   "verdict": action, "comment": comment}
            if anchor:
                rec["anchor"] = anchor
            if action in VERDICTS:
                require(user, "reviewer")
                if action != "comment" and st not in ("in_review", "approved"):
                    raise CardError(f"cannot {action}: revision r{rev} is '{st}', not under review")
                if action == "approve" and not cfg["allow_self_approval"] and \
                        meta.get("origin", {}).get("user") == user["name"]:
                    raise CardError("self-approval of your own edit is disabled by policy")
                append_jsonl(self.kb.reviews_dir / f"{cid}.jsonl", rec)
                if action != "comment":
                    summ = self.review_summary(cid, rev)
                    v = summ["votes"]
                    if v["reject"]:
                        meta["status"] = "rejected"
                    elif v["request_changes"]:
                        meta["status"] = "changes_requested"
                    elif v["approve"] >= cfg["required_approvals"]:
                        meta["status"] = "approved"
                    else:
                        meta["status"] = "in_review"
            else:
                require(user, "admin") if action not in ("submit",) else require(user, "reviewer")
                rec["kind"] = "decision"
                if action == "submit":
                    if st not in ("draft", "changes_requested"):
                        raise CardError(f"cannot submit from '{st}'")
                    meta["status"] = "in_review"
                elif action == "publish":
                    if st != "approved":
                        raise CardError(f"only approved revisions can be published (r{rev} is '{st}')")
                    meta["status"], meta["published_rev"] = "published", rev
                    meta["lifecycle"], meta["replaced_by"], meta["published_at"] = "active", "", now()
                    meta["published_by"] = user["name"]
                    atomic_write(self._rev_path(cid, rev), fm.dump({**self.load_rev(cid, rev)[0],
                                                                   "published_at": meta["published_at"],
                                                                   "published_by": user["name"]},
                                                                  self.load_rev(cid, rev)[1]))
                elif action == "return":  # 打回
                    if st not in ("approved", "in_review", "rejected"):
                        raise CardError(f"cannot return from '{st}'")
                    meta["status"] = "changes_requested"
                elif action == "reject":
                    meta["status"] = "rejected"
                elif action == "reopen":
                    if st not in ("rejected", "changes_requested"):
                        raise CardError(f"cannot reopen from '{st}'")
                    meta["status"] = "in_review"
                elif action == "withdraw":  # 下架
                    if not meta.get("published_rev"):
                        raise CardError("card was never published")
                    meta["lifecycle"] = "withdrawn"
                elif action == "restore":
                    if meta.get("lifecycle") == "active":
                        raise CardError("card is already active")
                    meta["lifecycle"], meta["replaced_by"] = "active", ""
                elif action == "supersede":  # 被替换
                    target = slug(target)
                    if not target or target == cid or not self.exists(target):
                        raise CardError("supersede needs an existing target card id")
                    meta["lifecycle"], meta["replaced_by"] = "superseded", target
                else:
                    raise CardError(f"unknown action {action}")
                rec["verdict"] = action
                if target:
                    rec["target"] = target
                append_jsonl(self.kb.reviews_dir / f"{cid}.jsonl", rec)
            meta["updated"] = now()
            self._write_head(meta, body)
        self.kb.event(user["name"], f"card.{action}", cid, rev=rev, status=meta["status"],
                      lifecycle=meta.get("lifecycle"), comment=comment[:500], to=target)
        return meta

    # ---- derived views -------------------------------------------------------
    def diff(self, cid: str, a: int, b: int) -> str:
        ta = fm.dump(*self.load_rev(cid, a)) if a else ""
        tb = fm.dump(*self.load_rev(cid, b))
        return "".join(difflib.unified_diff(ta.splitlines(True), tb.splitlines(True), f"r{a}", f"r{b}", n=2))

    def semantic_diff(self, cid: str, a: int, b: int) -> dict:
        """Reviewer-oriented diff: field by field (compared by value, so 1.0 == 1),
        relations and evidence as added/removed sets, body as a line diff."""
        ma, ba = self.load_rev(cid, a) if a else ({}, "")
        mb, bb = self.load_rev(cid, b)
        fields = []
        for k in ("title", "type", "parent", "summary", "aliases", "confidence"):
            if ma.get(k) != mb.get(k) and not (ma.get(k) in (None, "", []) and mb.get(k) in (None, "", [])):
                fields.append({"field": k, "before": ma.get(k), "after": mb.get(k)})

        def rkey(r):
            return (r.get("rel"), r.get("target"))
        ra = {rkey(r): r for r in ma.get("relations", [])}
        rb = {rkey(r): r for r in mb.get("relations", [])}
        rel_changed = [{"before": ra[k], "after": rb[k]} for k in ra.keys() & rb.keys()
                       if (ra[k].get("basis"), float(ra[k].get("confidence") or 0)) != (rb[k].get("basis"), float(rb[k].get("confidence") or 0))]

        def ekey(e):
            return (e.get("path"), _norm(e.get("quote", "")))
        ea = {ekey(e): e for e in ma.get("evidence", [])}
        eb = {ekey(e): e for e in mb.get("evidence", [])}
        body = "".join(difflib.unified_diff(ba.splitlines(True), bb.splitlines(True), f"r{a}", f"r{b}", n=2))
        return {"a": a, "b": b, "fields": fields,
                "relations_added": [rb[k] for k in rb.keys() - ra.keys()],
                "relations_removed": [ra[k] for k in ra.keys() - rb.keys()],
                "relations_changed": rel_changed,
                "evidence_added": [eb[k] for k in eb.keys() - ea.keys()],
                "evidence_removed": [ea[k] for k in ea.keys() - eb.keys()],
                "evidence_renumbered": sum(1 for k in ea.keys() & eb.keys() if ea[k].get("id") != eb[k].get("id")),
                "body": body, "change_note": mb.get("change_note", ""), "origin": mb.get("origin", {})}

    def graph(self, visible_only: bool) -> dict:
        idx = self.index()
        nodes, edges = [], []
        ids = {i for i, m in idx.items() if not visible_only or is_public(m)}
        for i in ids:
            m = idx[i]
            nodes.append({"id": i, "title": m["title"], "type": m["type"], "status": m["status"],
                          "ambiguous": sum(r.get("basis") == "ambiguous" for r in m.get("relations", [])),
                          "lifecycle": m.get("lifecycle"), "parent": m.get("parent", ""),
                          "grounding": m.get("grounding", {}).get("score", 0)})
            if m.get("parent") in ids:
                edges.append({"s": i, "t": m["parent"], "rel": "subtopic_of"})
            for r in m.get("relations", []):
                t = slug(r["target"])
                if t in ids and t != i:
                    edges.append({"s": i, "t": t, "rel": r.get("rel", "related_to"),
                                  "basis": r.get("basis", "inferred"), "conf": r.get("confidence")})
            for t in m.get("_links", []):
                if t in ids and t != i:
                    edges.append({"s": i, "t": t, "rel": "links_to"})
        return {"nodes": nodes, "edges": edges}

    def search(self, q: str, visible_only: bool, limit: int = 50) -> list[dict]:
        terms = [t for t in q.lower().split() if t]
        if not terms:
            return []
        hits = []
        for m in self.index().values():
            if visible_only and not is_public(m):
                continue
            text = m["_text"]
            if all(t in text for t in terms):
                title = (m.get("title", "") + " " + " ".join(m.get("aliases", []))).lower()
                score = sum(5 * (t in title) + text.count(t) for t in terms)
                hits.append((score, {"id": m["id"], "title": m["title"], "type": m["type"],
                                     "summary": m.get("summary", ""), "status": m["status"]}))
        return [h for _, h in sorted(hits, key=lambda x: -x[0])[:limit]]

    def lint(self) -> list[dict]:
        """Integrity report: dangling links/relations/parents, stale sources, weak grounding."""
        idx = self.index()
        issues = []
        for cid, m in idx.items():
            for r in m.get("relations", []):
                if slug(r["target"]) not in idx:
                    issues.append({"card": cid, "kind": "dangling_relation", "detail": f"{r.get('rel')} → {r['target']}"})
            for t in m.get("_links", []):
                if t not in idx:
                    issues.append({"card": cid, "kind": "dangling_wikilink", "detail": t})
            if m.get("parent") and m["parent"] not in idx:
                issues.append({"card": cid, "kind": "dangling_parent", "detail": m["parent"]})
            if m.get("stale_sources"):
                issues.append({"card": cid, "kind": "stale_source", "detail": ", ".join(m["stale_sources"])})
            g = m.get("grounding", {})
            if g.get("missing"):
                issues.append({"card": cid, "kind": "ungrounded_evidence", "detail": f"{g['missing']} of {g['total']} quotes not found in source"})
            if not m.get("evidence") and m.get("origin", {}).get("kind") != "schema":
                issues.append({"card": cid, "kind": "no_evidence", "detail": "card cites nothing"})
            amb = [f"{r.get('rel')} → {r['target']}" for r in m.get("relations", []) if r.get("basis") == "ambiguous"]
            if amb and m.get("status") != "published":
                issues.append({"card": cid, "kind": "ambiguous_relation", "detail": "; ".join(amb)})
            if m.get("lifecycle") == "superseded" and m.get("replaced_by") not in idx:
                issues.append({"card": cid, "kind": "dangling_replacement", "detail": m.get("replaced_by")})
        for d in S.near_duplicates(self.kb):
            issues.append({"card": summary_id(d["b"]), "kind": "duplicate_source",
                           "detail": f"{d['b']} ≈ {d['a']} (similarity {d['similarity']}, containment {d['containment']}) — consider retiring one"})
        for p in S.list_md(self.kb):
            if summary_id(p) not in idx and any(s["path"] == p for m in idx.values() for s in m.get("sources", [])):
                issues.append({"card": summary_id(p), "kind": "missing_summary", "detail": p})
        return issues

    def write_log(self) -> None:
        """compiled/log.md — the LLM-Wiki style human-readable chronicle (newest day first)."""
        days: dict[str, list[str]] = {}
        for e in read_jsonl(self.kb.events_path):
            line = _log_line(e)
            if line:
                days.setdefault(e["ts"][:10], []).append(line)
        out = ["# Knowledge base log", "", "_ingest · compile · publish · withdraw · schema changes — generated from log/events.jsonl_", ""]
        for day in sorted(days, reverse=True)[:120]:
            out.append(f"## {day}")
            out.extend(reversed(days[day]))
            out.append("")
        atomic_write(self.kb.root / "compiled" / "log.md", "\n".join(out))

    def write_exports(self) -> None:
        """compiled/index.md and graph.json — the published wiki, for humans and agents."""
        pub = [m for m in self.index().values() if is_public(m)]
        by_parent: dict[str, list] = {}
        for m in pub:
            by_parent.setdefault(m.get("parent") or "", []).append(m)
        lines = ["# Knowledge index (published)", "", f"_generated {now()} · {len(pub)} cards_", ""]

        def walk(pid: str, depth: int, seen: set):
            for m in sorted(by_parent.get(pid, []), key=lambda x: x["title"].lower()):
                if m["id"] in seen:
                    continue
                seen.add(m["id"])
                lines.append(f"{'  ' * depth}- [[{m['id']}|{m['title']}]] ({m['type']}) — {m.get('summary', '')}")
                walk(m["id"], depth + 1, seen)

        summaries = [m for m in pub if m["type"] == "summary"]
        by_parent = {k: [m for m in v if m["type"] != "summary"] for k, v in by_parent.items()}
        lines.append("## Knowledge (concepts by topic)")
        lines.append("")
        seen: set = set()
        walk("", 0, seen)
        for m in pub:  # orphans whose parent is unpublished
            if m["id"] not in seen and m["type"] != "summary":
                lines.append(f"- [[{m['id']}|{m['title']}]] ({m['type']}) — {m.get('summary', '')}")
        lines += ["", "## Source documents (one summary per document)", ""]
        for m in sorted(summaries, key=lambda x: x["id"]):
            src = ", ".join(s["path"] for s in m.get("sources", []))
            lines.append(f"- [[{m['id']}|{m['title']}]] — `{src}` — {m.get('summary', '')}")
        atomic_write(self.kb.root / "compiled" / "index.md", "\n".join(lines) + "\n")
        self.write_log()
        atomic_write(self.kb.root / "compiled" / "graph.json",
                     json.dumps(self.graph(visible_only=True), ensure_ascii=False, indent=1))


LOG_ACTIONS = {"source.upload": "ingest", "source.retire": "retire", "compile.run.done": "compile",
               "compile.run.failed": "compile-failed", "card.publish": "publish", "card.withdraw": "withdraw",
               "card.supersede": "supersede", "card.restore": "restore", "card.return": "return",
               "query.filed": "query→card", "schema.update": "schema"}


def _log_line(e: dict) -> str | None:
    kind = LOG_ACTIONS.get(e["action"])
    if not kind:
        return None
    d = e.get("detail", {})
    what = e["target"]
    if kind == "ingest":
        what = f"{len(d.get('changed', []))} changed file(s) under {e['target']}" + (f" — {d['note']}" if d.get("note") else "")
    elif kind.startswith("compile"):
        what = f"{', '.join(d.get('sources', []))} → {len(d.get('cards', []))} card revision(s) (run {e['target']})"
    elif kind in ("publish", "withdraw", "restore", "return", "supersede"):
        what = f"[[{e['target']}]] r{d.get('rev')}" + (f" → [[{d['to']}]]" if d.get("to") else "") + \
               (f" — {d['comment']}" if d.get("comment") else "")
    return f"- `{e['ts'][11:16]}` **{kind}** · {e['actor']} · {what}"


def is_public(m: dict) -> bool:
    return bool(m.get("published_rev")) and m.get("lifecycle", "active") == "active"

