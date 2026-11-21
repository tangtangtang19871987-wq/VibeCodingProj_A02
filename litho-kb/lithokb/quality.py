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
  max_appends  (3)    more "补充（来自…）" sections than this means the card reads as a
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

RISK_RULES_VERSION = "risk/1"
DEFAULT_GRANULARITY = {"min_units": 60, "target_max": 900, "hard_max": 1600, "max_evidence": 24, "max_appends": 3}
_CJK = re.compile(r"[㐀-䶿一-鿿豈-﫿]")
_WORD = re.compile(r"[A-Za-z0-9]+(?:[.'\-][A-Za-z0-9]+)*")
_APPEND = re.compile(r"^#{1,6}\s*补充（来自", re.M)


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


ISSUE_ZH = {"thin": "过薄（单一事实，宜并入相关卡片）", "long": "偏长", "too_long": "过长（需整合或拆分）",
            "fragmented": "补充段过多（需整合重写）", "broad": "证据过多（可能包含多个概念）"}


def assess(meta: dict, body: str, cfg: dict) -> dict:
    """Review risk: low | medium | high, with reasons a reviewer can act on."""
    high, medium = [], []
    ev = meta.get("evidence", [])
    unsure = [e for e in ev if e.get("check") in ("fuzzy", "missing", "no_source")]
    if unsure:
        high.append(f"{len(unsure)} 条证据无法核验（近似/未找到/来源缺失）")
    elided = [e for e in ev if e.get("check") == "elided"]
    if elided:
        medium.append(f"{len(elided)} 条省略式引用，需确认省略未改变原意")
    rels = meta.get("relations", [])
    if any(r.get("basis") == "ambiguous" for r in rels):
        high.append("含“存疑”关系")
    if any(r.get("rel") == "contradicts" for r in rels):
        high.append("含“矛盾”关系")
    if meta.get("stale_sources"):
        high.append("原文在编译后已更新")
    if not ev and meta.get("type") not in ("topic", "summary"):
        high.append("没有证据")
    conf = meta.get("confidence")
    if isinstance(conf, (int, float)) and conf < 0.5:
        high.append(f"模型置信度低（{conf}）")
    g = measure(meta, body, cfg)
    if "too_long" in g["issues"]:
        high.append(f"篇幅过长（{g['units']} 字/词，约 {g['minutes']} 分钟）")
    for k in ("long", "fragmented", "broad", "thin"):
        if k in g["issues"]:
            medium.append(ISSUE_ZH[k])
    srcs = {s.get("path") for s in meta.get("sources", [])}
    if len(srcs) > 1:
        medium.append(f"跨 {len(srcs)} 篇文档合并，需通读")
    origin = meta.get("origin", {})
    if origin.get("kind") == "human":
        medium.append("人工修改，需另一位审阅者逐张确认")
    if origin.get("kind") == "query":
        medium.append("问答回写的综合内容")
    if origin.get("op") == "consolidate":
        cov = origin.get("evidence_coverage")
        if isinstance(cov, (int, float)) and cov < 0.5:
            high.append(f"整合后正文只引用了 {round(cov * 100)}% 的证据，可能丢失内容（考虑拆分）")
        else:
            medium.append("整合重写，需通读")
    if meta.get("published_rev") and meta.get("rev") != meta.get("published_rev"):
        medium.append("修改已发布内容")
    if isinstance(conf, (int, float)) and 0.5 <= conf < 0.7:
        medium.append(f"模型置信度一般（{conf}）")
    inferred = [r for r in rels if r.get("basis") == "inferred"]
    if len(inferred) >= 3 and len(inferred) * 2 > len(rels):
        medium.append("推断关系占多数")
    if meta.get("type") in ("parameter", "metric", "result"):
        medium.append("数值/结论类知识")
    level = "high" if high else "medium" if medium else "low"
    return {"level": level, "reasons": high + medium, "granularity": g, "rules": RISK_RULES_VERSION}
