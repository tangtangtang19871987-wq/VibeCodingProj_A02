"""Text-fit estimation shared by build + lint. Heuristic (no font metrics): good enough to catch overflow."""
import math, unicodedata


def _w(ch, pt):
    if unicodedata.east_asian_width(ch) in ("W", "F"):
        return pt / 72.0 * 1.0
    if ch in "iljtfI.,:;'| ":
        return pt / 72.0 * 0.32
    if ch.isupper() or ch in "mwMW@%":
        return pt / 72.0 * 0.68
    return pt / 72.0 * 0.52


def lines(text, pt, width_in):
    """Number of wrapped lines for one paragraph."""
    if not text:
        return 1
    n, cur = 1, 0.0
    for ch in text:
        w = _w(ch, pt)
        if cur + w > width_in:
            n, cur = n + 1, w
        else:
            cur += w
    return n


def height(paras, pt, width_in, spacing=1.2, gap_pt=0, mono=False):
    """Needed height (inches) for paragraphs [(text, indent_in), ...] or [text, ...]."""
    total = 0.0
    for p in paras:
        text, ind = (p if isinstance(p, tuple) else (p, 0.0))
        if mono:
            n = max(1, math.ceil(len(text) * pt / 72.0 * 0.6 / max(width_in - ind, 0.3))) if text else 1
        else:
            n = lines(text, pt, max(width_in - ind, 0.3))
        total += n * pt * spacing / 72.0 + gap_pt / 72.0
    return total


def fit(paras, w, h, start, minimum=12, spacing=1.2, gap_ratio=0.0, mono=False):
    """Largest font size (pt) <= start whose text fits w x h (inches)."""
    pt = start
    while pt > minimum:
        if height(paras, pt, w, spacing, pt * gap_ratio, mono) <= h:
            return pt
        pt -= 1
    return minimum
