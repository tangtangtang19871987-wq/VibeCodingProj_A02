"""Card facets: applicability conditions, dated events, structured facts.

Knowledge in computational lithography is condition-dependent — a statement true for
EUV at 3 nm may be false for ArF immersion at 28 nm. Facets make that explicit and
power additional views of the same knowledge:

  conditions [{dim, value, evidence}]          → filtering in every view and in Q&A
  events     [{when, what, evidence}]          → timeline view
  facts      [{name, value, unit, conditions, evidence}] → comparison-table view

Every facet item must cite an evidence id of the card (already verified against the
source); items that cannot be grounded are dropped. Condition dimensions are declared
by the domain team in SCHEMA.md ("Applicability condition dimensions"; legacy
heading "Applicability condition dimensions"), not in code.
"""
from __future__ import annotations

import re

from . import schema as SC

# synonyms so that "EUV" matches "13.5nm" and "ArF immersion" matches "193nm"
_WAVELENGTH = [("euv", ("euv", "13.5nm", "13.5 nm", "extreme ultraviolet", "extreme-ultraviolet", "\u6781\u7d2b\u5916")), ("arfi", ("arfi", "\u6d78\u6ca1", "immersion", "193i")),
               ("arf", ("arf", "193nm", "193 nm", "duv")), ("krf", ("krf", "248nm", "248 nm")),
               ("i-line", ("i-line", "i\u7ebf", "365nm")), ("g-line", ("g-line", "g\u7ebf", "436nm"))]


def dims(kb) -> dict[str, tuple[str, str]]:
    """Condition dimensions from SCHEMA.md: lines '- `dim` Name: e.g. …' (a full-width colon is also accepted)
    under a heading containing "Applicability" (or its legacy Chinese equivalent)."""
    text = SC.current(kb)["text"]
    m = re.search(r"^#+[^\n]*(?:\u9002\u7528\u6761\u4ef6|applicability)[^\n]*\n(.*?)(?=^#+ |\Z)", text, re.M | re.S | re.I)
    out = {}
    for mm in re.finditer(r"^[ \t]*[-*][ \t]+`([a-z][a-z0-9_]*)`[ \t]+([^\uff1a:\n]+)[\uff1a:]?[ \t]*([^\n]*)$", m.group(1) if m else "", re.M):
        out[mm.group(1)] = (mm.group(2).strip(), mm.group(3).strip())
    return out


def _nm_interval(v: str):
    """'≤7nm' / '7nm and below' → (0,7); '≥28nm' / '28nm and above' → (28,inf); '65nm–5nm' → (5,65); '5nm' → (5,5).
    Chinese qualifiers ("and below", "and above", "to", …) in existing data are matched too."""
    s = v.replace(" ", "").lower()
    nums = [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)(?=nm|\u7eb3\u7c73|n\b|$|[^\d.])", s)]
    if not nums:
        return None
    if len(nums) >= 2 and re.search(r"[-–~\u81f3\u5230]|(?<=[\dm])to(?=\d)", s):
        return (min(nums[:2]), max(nums[:2]))
    n = nums[0]
    if re.search(r"≤|<=|<|\u53ca\u4ee5\u4e0b|\u4ee5\u4e0b|\u4ee5\u5185|\u53ca\u66f4\u5148\u8fdb|beyond|below|orless|orsmaller|andsmaller", s):
        return (0.0, n)
    if re.search(r"≥|>=|>|\u53ca\u4ee5\u4e0a|\u4ee5\u4e0a|\u6210\u719f|above|orlarger|andlarger|mature", s):
        return (n, float("inf"))
    return (n, n)


def _canon_wavelength(v: str) -> set:
    s = v.lower()
    return {k for k, keys in _WAVELENGTH if any(x in s for x in keys)}


def value_matches(dim: str, card_value: str, wanted: str) -> bool:
    if dim == "node":
        a, b = _nm_interval(card_value), _nm_interval(wanted)
        if a and b:
            return a[0] <= b[1] and b[0] <= a[1]
    if dim == "wavelength":
        a, b = _canon_wavelength(card_value), _canon_wavelength(wanted)
        if a and b:
            return bool(a & b) or ("arf" in a | b and "arfi" in a | b)
    cv, wv = card_value.lower().strip(), wanted.lower().strip()
    return bool(cv) and bool(wv) and (wv in cv or cv in wv)


def applies(conditions: list[dict], wanted: dict[str, str]) -> str:
    """'yes' (matches), 'general' (no condition stated on the requested dimensions), 'no'."""
    if not wanted:
        return "yes"
    stated = False
    for dim, w in wanted.items():
        vals = [c.get("value", "") for c in conditions or [] if c.get("dim") == dim]
        if not vals:
            continue
        stated = True
        if not any(value_matches(dim, v, w) for v in vals):
            return "no"
    return "yes" if stated else "general"


def parse_filter(q: str) -> dict[str, str]:
    """'wavelength:EUV,node:5nm' → {"wavelength": "EUV", "node": "5nm"}"""
    out = {}
    for part in (q or "").split(","):
        if ":" in part:
            k, _, v = part.partition(":")
            if k.strip() and v.strip():
                out[k.strip()] = v.strip()
    return out


def normalize(card: dict, ev_ids: set, known_dims: dict, findings: list | None = None, cid: str = "") -> dict:
    """Keep only grounded, well-formed facet items. Returns {"conditions","events","facts"}."""
    findings = findings if findings is not None else []
    out = {"conditions": [], "events": [], "facts": []}
    seen = set()
    for c in card.get("conditions", []) or []:
        if not isinstance(c, dict):
            continue
        dim, val, ev = str(c.get("dim", "")).strip(), str(c.get("value", "")).strip(), c.get("evidence")
        if known_dims and dim not in known_dims:
            findings.append({"level": "info", "card": cid, "msg": f"condition dimension {dim!r} not in SCHEMA — dropped"})
            continue
        if not val or ev not in ev_ids:
            findings.append({"level": "info", "card": cid, "msg": f"condition {dim}={val!r} without valid evidence — dropped"})
            continue
        if (dim, val.lower()) not in seen:
            seen.add((dim, val.lower()))
            out["conditions"].append({"dim": dim, "value": val[:80], "evidence": ev})
    for e in card.get("events", []) or []:
        if isinstance(e, dict) and str(e.get("when", "")).strip() and str(e.get("what", "")).strip():
            if e.get("evidence") in ev_ids:
                out["events"].append({"when": str(e["when"]).strip()[:40], "what": str(e["what"]).strip()[:200],
                                      "evidence": e["evidence"]})
            else:
                findings.append({"level": "info", "card": cid, "msg": f"event {e.get('when')!r} without valid evidence — dropped"})
    for f in card.get("facts", []) or []:
        if not isinstance(f, dict) or not str(f.get("name", "")).strip() or str(f.get("value", "")).strip() == "":
            continue
        if f.get("evidence") not in ev_ids:
            findings.append({"level": "info", "card": cid, "msg": f"fact {f.get('name')!r} without valid evidence — dropped"})
            continue
        conds = f.get("conditions") if isinstance(f.get("conditions"), dict) else {}
        out["facts"].append({"name": str(f["name"]).strip()[:80], "value": str(f["value"]).strip()[:80],
                             "unit": str(f.get("unit", "") or "").strip()[:20],
                             "conditions": {k: str(v)[:60] for k, v in conds.items() if not known_dims or k in known_dims},
                             "evidence": f["evidence"]})
    return out


def year_of(when: str) -> float | None:
    m = re.search(r"(1[89]\d\d|20\d\d)", when or "")
    if not m:
        return None
    y = float(m.group(1))
    mo = re.search(r"(1[89]\d\d|20\d\d)[-./\u5e74](\d{1,2})", when)
    return y + (int(mo.group(2)) - 1) / 12 if mo else y


# ---- support check: does the cited quote actually state the facet? -------------------
_CJK = re.compile(r"[\u4e00-\u9fff]")


def _tokens(text: str) -> tuple[list[str], list[str]]:
    t = (text or "").lower()
    nums = re.findall(r"\d+(?:\.\d+)?", t)
    words = [w for w in re.findall(r"[a-z][a-z\-]{1,}", t) if w not in ("nm", "and", "or", "the", "of", "to", "x")]
    cjk = "".join(_CJK.findall(t))
    words += [cjk[i:i + 2] for i in range(0, max(0, len(cjk) - 1))]
    return nums, words


def supported(kind: str, item: dict, quote: str) -> bool:
    """Mechanical check that the evidence quote states the facet (numbers must all appear; most words must)."""
    from .cards import _norm
    q = _norm(quote)
    if kind == "events":
        when = str(item.get("when", ""))
        if not re.search(r"\d", when):
            return False  # 'next lecture' is not a date
        return all(n in q for n in re.findall(r"\d{2,4}", when))
    if kind == "conditions":
        val = str(item.get("value", ""))
        if item.get("dim") == "wavelength" and _canon_wavelength(val) & _canon_wavelength(quote):
            return True
        if item.get("dim") in ("node", "na"):  # numeric dimensions: the numbers must be stated; qualifiers vary
            nums = re.findall(r"\d+(?:\.\d+)?", val)
            return bool(nums) and all(n in q for n in nums)
        text = val
    else:
        val = str(item.get("value", ""))
        if len(val) > 60:
            return False  # paragraphs are not comparable facts
        text = val
    nums, words = _tokens(text)
    if nums and not all(n in q for n in nums):
        return False
    if words:
        hit = sum(1 for w in words if _norm(w) in q)
        return hit / len(words) >= 0.6
    return bool(nums)


def _context(kb, e: dict, cache: dict, pad: int = 3) -> str:
    """The cited lines ±pad in the source: dates and conditions often sit in the same table row or heading."""
    from . import sources as S
    from .cards import _parse_lines
    try:
        if e["path"] not in cache:
            cache[e["path"]] = S.read_text(kb, e["path"]).splitlines()
        lines = cache[e["path"]]
        a, b = _parse_lines(e.get("found_lines") or e.get("lines", ""), len(lines))
        return "\n".join(lines[max(0, a - 1 - pad): b + pad]) if a else ""
    except Exception:
        return ""


def mark_support(card_meta: dict, kb=None) -> dict:
    """Return {kind: [items with 'supported': bool]}. Facts must be stated by the quote itself;
    events and conditions may also be stated in the quote's immediate context (same row/heading)."""
    ev = {e["id"]: e for e in card_meta.get("evidence", [])}
    cache: dict = {}
    out = {}
    for k in ("conditions", "events", "facts"):
        items = []
        for x in card_meta.get(k, []) or []:
            e = ev.get(x.get("evidence"), {})
            okq = supported(k, x, e.get("quote", ""))
            if not okq and kb is not None and k in ("conditions", "events") and e:
                okq = supported(k, x, e.get("quote", "") + "\n" + _context(kb, e, cache))
            items.append({**x, "supported": okq})
        out[k] = items
    return out


def ok(items) -> list:
    """Only items whose support check passed (what views and filters use)."""
    return [x for x in items or [] if x.get("supported", True)]
