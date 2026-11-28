"""Evidence forms (artifact types) of source sections, and the forms a question needs.

Function-aware retrieval for technical documentation (Qiu et al., 2026, "From Chunks to Functional Evidence")
observes that the answer to a technical question needs particular *evidence forms* — a parameter table, a code
block, an ordered procedure, a constraint — and that semantically similar passages often lack the form that
carries the answer (a descriptive paragraph instead of the table row with the default value). They learn this
with a fine-tuned encoder; LithoKB does it without vectors or training:

  section_types(text)   deterministic detection of the forms present in a section's own text
  needed_types(question) rule-based cues in the question (Chinese and English) → forms that can answer it
  coverage(needed, have) the share of needed forms a candidate offers (the paper's κ)

The forms are shown to the navigator next to every section, used to re-rank lexical section hints, to pick
which grounding sections to add, and scored in the evaluation ("did we read a table when the question asks for
a value?").
"""
from __future__ import annotations

import re

TYPES = ("table", "code", "formula", "procedure", "value", "constraint", "diagnostic", "figure")
LABEL = {"table": "table", "code": "code", "formula": "formula", "procedure": "steps", "value": "values",
         "constraint": "constraints", "diagnostic": "diagnostics", "figure": "figure"}

_TABLE = re.compile(r"^\s*\|.*\|\s*$", re.M)
_FENCE = re.compile(r"^\s*(```|~~~)", re.M)
_FORMULA = re.compile(r"\$\$|\\\[|\\(?:frac|sum|int|nabla|partial|lambda|sigma|phi|alpha|cdot|sqrt|mathrm|left|right)\b"
                      r"|[=≈]\s*[-+]?\s*\w+\s*[·×*/^]\s*\w+|[‖‖]|\|\|[^|\n]+\|\|")
_PROC = re.compile(r"^\s*(?:\d+[.)]|step\s*\d+|\u6b65\u9aa4\s*\d+)\s+", re.M | re.I)
_VALUE = re.compile(r"\d+(?:\.\d+)?\s*(?:nm|μm|um|mm|ms|s\b|%|x\b|\u500d|mj|mw|w\b|ghz|tb|gb|na\b|°)", re.I)
_CONSTR = re.compile(r"\u5fc5\u987b|\u4e0d\u5f97|\u4e0d\u80fd|\u9650\u5236|\u7ea6\u675f|\u6700\u5c0f|\u6700\u5927|\u4e0d\u8d85\u8fc7|\u81f3\u5c11"
                     r"|\bmust\b|\bshall\b|\bat (?:least|most)\b|\bminimum\b|\bmaximum\b|[≤≥<>]\s*\d", re.I)
_DIAG = re.compile(r"\u8b66\u544a|\u62a5\u9519|\u9519\u8bef|\u5931\u8d25|\u5f02\u5e38|\u70ed\u70b9|\u7f3a\u9677|\bwarning\b|\berror\b|\bfail(?:s|ed|ure)?\b|\bhotspot\b", re.I)
_FIG = re.compile(r"^\s*>\s*(?:Figure text:|\u56fe\u793a\u6587\u5b57)|!\[", re.M)


def section_types(text: str) -> list[str]:
    """Evidence forms present in a section's own text (deterministic)."""
    t = text or ""
    out = []
    if len(_TABLE.findall(t)) >= 2:
        out.append("table")
    if _FENCE.search(t):
        out.append("code")
    if _FORMULA.search(t):
        out.append("formula")
    if len(_PROC.findall(t)) >= 2:
        out.append("procedure")
    if len(_VALUE.findall(t)) >= 1:
        out.append("value")
    if _CONSTR.search(t):
        out.append("constraint")
    if _DIAG.search(t):
        out.append("diagnostic")
    if _FIG.search(t):
        out.append("figure")
    return out


# question cues → evidence forms that can carry the answer (Chinese cues written as escapes, meaning in comments)
_CUES = [
    # value, default, range, how much / how many, typical, numbers
    ("value", r"\u53d6\u503c|\u9ed8\u8ba4|\u8303\u56f4|\u591a\u5c11|\u591a\u5927|\u591a\u5feb|\u5178\u578b\u503c|\u6570\u503c|\u53c2\u6570"
              r"|\bvalue|\bdefault|\brange\b|\bhow (?:much|many|fast|large)|\btypical\b|\bparameter"),
    ("table", r"\u53d6\u503c|\u9ed8\u8ba4|\u5bf9\u6bd4|\u6bd4\u8f83|\u533a\u522b|\u53c2\u6570|\bcompar|\bdefault|\bparameter|\bdifference"),
    # formula, how is it computed, expression, physical meaning of a term
    ("formula", r"\u516c\u5f0f|\u5982\u4f55\u8ba1\u7b97|\u600e\u4e48\u7b97|\u8868\u8fbe\u5f0f|\u68af\u5ea6|\u4ee3\u4ef7|\u76ee\u6807\u51fd\u6570|\u7269\u7406\u542b\u4e49"
                r"|\bformula|\bequation|\bcompute|\bgradient|\bcost (?:function|term)|\bobjective"),
    # code, syntax, pseudo-code, command, implementation
    ("code", r"\u4ee3\u7801|\u8bed\u6cd5|\u4f2a\u4ee3\u7801|\u547d\u4ee4|\u811a\u672c|\u5b9e\u73b0|\bcode\b|\bsyntax|\bpseudo|\bcommand|\bscript|\bimplement"),
    # steps, procedure, flow, how is it done, intermediate steps
    ("procedure", r"\u6b65\u9aa4|\u6d41\u7a0b|\u5982\u4f55\u8fdb\u884c|\u600e\u4e48\u505a|\u4e2d\u95f4\u6b65\u9aa4|\u8fc7\u7a0b|\bsteps?\b|\bprocedure|\bworkflow|\bpipeline|\bhow (?:is|do|does|to)\b"),
    # constraints, limits, rules, conflicts, trade-offs, manufacturability
    ("constraint", r"\u7ea6\u675f|\u9650\u5236|\u89c4\u5219|\u51b2\u7a81|\u6743\u8861|\u53ef\u5236\u9020|\u5fc5\u987b|\bconstraint|\blimit|\brule\b|\bconflict|\btrade-?off|\bmanufactur"),
    # errors, failures, warnings, problems, debugging, hotspots
    ("diagnostic", r"\u62a5\u9519|\u9519\u8bef|\u5931\u8d25|\u8b66\u544a|\u95ee\u9898|\u8c03\u8bd5|\u70ed\u70b9|\u5c40\u9650|\berror|\bfail|\bwarning|\bdebug|\bhotspot|\blimitation"),
]
_CUE_RE = [(t, re.compile(p, re.I)) for t, p in _CUES]


def needed_types(question: str) -> list[str]:
    """Evidence forms the question asks for, from its wording (empty = no particular form)."""
    q = question or ""
    return [t for t, rx in _CUE_RE if rx.search(q)]


def coverage(needed, have) -> float:
    needed = set(needed or [])
    if not needed:
        return 1.0
    return len(needed & set(have or [])) / len(needed)


def tags(types) -> str:
    return "·".join(LABEL[t] for t in types if t in LABEL)


__all__ = ["TYPES", "LABEL", "section_types", "needed_types", "coverage", "tags"]
