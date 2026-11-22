"""Card quality signals used by governance: granularity and review risk.

Granularity — what deserves to be a card
---------------------------------------
A card is one concept that a person can read in one sitting and an agent can load
cheaply. Size is measured in *reading units*: one CJK character or one word of
Latin script (so mixed Chinese/English text is measured fairly).

  min_units   (60)    below: a single fact, not a concept → fold it into a related card
  target_max  (900)   ≈ 2–3 minutes of reading, ≈ 1.2k tokens — the comfortable ceiling
  hard_max    (1600)  ≈ 4 minutes, ≈ 2k tokens — beyond this the card must be
                      consolidated (rewritten) or split into sub-concept cards
  max_evidence (24)   more evidence than this usually means several concepts in one card
  max_appends  (3)    more "Addendum (from …)" sections than this means the card reads as a
                      pile of excerpts and should be consolidated into one coherent text

Thresholds live in config.json → "granularity" (domain teams can tune them); the
writing rule lives in SCHEMA.md so the compiler aims for it in the first place.

Review risk — what may be approved in batch
-------------------------------------------
Every card gets a risk level with human-readable reasons. Only LOW risk cards may be
batch-approved (enforced on the server), and a batch always requires a comment and
leaves one review record per card plus a batch event in the audit log.
"""
from __future__ import annotations

import re

RISK_RULES_VERSION = "risk/2"
DEFAULT_GRANULARITY = {"min_units": 60, "target_max": 900, "hard_max": 1600, "max_evidence": 24, "max_appends": 3}
_CJK = re.compile(r"[㐀-䶿一-鿿豈-﫿]")
_WORD = re.compile(r"[A-Za-z0-9]+(?:[.'\-][A-Za-z0-9]+)*")
_APPEND = re.compile(r"^#{1,6}\s*(?:补充（来自|Addendum \(from\b)", re.M | re.I)  # legacy Chinese + English headings


def units(text: str) -> int:
    text = re.sub(r"\[(E|S)\d+(?:-\d+)?\]|\[\[[^\]]*\]\]|\(src:[^)]*\)", "", text or "")
    return len(_CJK.findall(text)) + len(_WORD.findall(_CJK.sub(" ", text)))


def granularity_cfg(kb) -> dict:
    return {**DEFAULT_GRANULARITY, **(kb.config.get("granularity") or {})}


def measure(meta: dict, body: str, cfg: dict) -> dict:
    """Size of a card and whether it is within the granularity policy."""
    u = units(body)
    appends = len(_APPEND.findall(body or ""))
    ev = len(meta.get("evidence", []))
    issues = []
    exempt = meta.get("type") in ("topic", "summary")  # topics/summaries are navigation, not knowledge units
    if not exempt and u < cfg["min_units"]:
        issues.append("thin")
    if u > cfg["hard_max"]:
        issues.append("too_long")
    elif u > cfg["target_max"]:
        issues.append("long")
    if appends > cfg["max_appends"]:
        issues.append("fragmented")
    if ev > cfg["max_evidence"] and not exempt:
        issues.append("broad")
    return {"units": u, "minutes": round(u / 400, 1), "appends": appends, "evidence": ev, "issues": issues,
            "needs_consolidation": bool({"too_long", "fragmented", "broad"} & set(issues)) or
            ("long" in issues and appends > 1)}


ISSUE_ZH = {"thin": "too thin (a single fact; merge into a related card)", "long": "on the long side",
            "too_long": "too long (consolidate or split)", "fragmented": "too many addenda (consolidate into one text)",
            "broad": "too much evidence (may cover several concepts)"}


def assess(meta: dict, body: str, cfg: dict) -> dict:
    """Review risk: low | medium | high, with reasons a reviewer can act on."""
    high, medium = [], []
    ev = meta.get("evidence", [])
    unsure = [e for e in ev if e.get("check") in ("fuzzy", "missing", "no_source")]
    if unsure:
        high.append(f"{len(unsure)} evidence quote(s) could not be verified (fuzzy/not found/source missing)")
    elided = [e for e in ev if e.get("check") == "elided"]
    if elided:
        medium.append(f"{len(elided)} elided quote(s); confirm the omission does not change the meaning")
    bad_facets = sum(1 for k in ("conditions", "events", "facts") for x in meta.get(k, []) or [] if x.get("supported") is False)
    if bad_facets:
        medium.append(f"{bad_facets} facet(s) do not match the cited source (hidden in views)")
    rels = meta.get("relations", [])
    if any(r.get("basis") == "ambiguous" for r in rels):
        high.append("has an ambiguous relation")
    if any(r.get("rel") == "contradicts" for r in rels):
        high.append("has a contradicts relation")
    if meta.get("stale_sources"):
        high.append("source document updated after compilation")
    if not ev and meta.get("type") not in ("topic", "summary"):
        high.append("no evidence")
    conf = meta.get("confidence")
    if isinstance(conf, (int, float)) and conf < 0.5:
        high.append(f"low model confidence ({conf})")
    g = measure(meta, body, cfg)
    if "too_long" in g["issues"]:
        high.append(f"too long ({g['units']} units, about {g['minutes']} min)")
    for k in ("long", "fragmented", "broad", "thin"):
        if k in g["issues"]:
            medium.append(ISSUE_ZH[k])
    srcs = {s.get("path") for s in meta.get("sources", [])}
    if len(srcs) > 1:
        medium.append(f"merged from {len(srcs)} source documents; read in full")
    origin = meta.get("origin", {})
    if origin.get("kind") == "human":
        medium.append("edited by a person; another reviewer must confirm it card by card")
    if origin.get("kind") == "query":
        medium.append("synthesis written back from Q&A")
    if origin.get("op") == "consolidate":
        cov = origin.get("evidence_coverage")
        if isinstance(cov, (int, float)) and cov < 0.5:
            high.append(f"consolidated body cites only {round(cov * 100)}% of the evidence; content may be lost (consider splitting)")
        else:
            medium.append("consolidated rewrite; read in full")
    if origin.get("op") == "hub":
        if origin.get("unknown_numbers") or origin.get("bad_links"):
            high.append("topic overview has numbers not found in child cards or links to missing cards")
        else:
            medium.append(f"topic overview (cites {round((origin.get('children_cited') or 0) * 100)}% of child cards); verify it")
    if meta.get("published_rev") and meta.get("rev") != meta.get("published_rev"):
        medium.append("changes published content")
    if isinstance(conf, (int, float)) and 0.5 <= conf < 0.7:
        medium.append(f"moderate model confidence ({conf})")
    inferred = [r for r in rels if r.get("basis") == "inferred"]
    if len(inferred) >= 3 and len(inferred) * 2 > len(rels):
        medium.append("mostly inferred relations")
    if meta.get("type") in ("parameter", "metric", "result"):
        medium.append("numeric / result-type knowledge")
    level = "high" if high else "medium" if medium else "low"
    return {"level": level, "reasons": high + medium, "granularity": g, "rules": RISK_RULES_VERSION}
