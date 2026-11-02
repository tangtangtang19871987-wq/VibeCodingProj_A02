"""Read an html-ppt-studio theme (assets/themes/NAME.css) and expose it as PPTX-ready RGB tokens.
This is the bridge that keeps the HTML preview and the PPTX visually consistent."""
import os, re

HERE = os.path.dirname(os.path.abspath(__file__))
THEME_DIRS = [
    os.path.join(HERE, "..", "..", "html-ppt-studio", "assets", "themes"),
    os.path.join(HERE, "..", "..", "..", "..", "html-ppt-studio", "assets", "themes"),
]


def _hex(c):
    c = c.strip().lstrip("#")
    if len(c) == 3:
        c = "".join(x * 2 for x in c)
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def _mix(a, b, t):
    return tuple(round(a[i] * (1 - t) + b[i] * t) for i in range(3))


def _var(css, name):
    m = re.search(r"--%s:\s*([^;]+?)\s*(?:;|\n|})" % re.escape(name), css)
    return m.group(1) if m else None


def load(name):
    css = None
    for d in THEME_DIRS:
        p = os.path.join(d, name + ".css")
        if os.path.exists(p):
            css = open(p, encoding="utf-8").read()
            break
    if css is None:
        raise SystemExit("unknown theme %r (expected assets/themes/%s.css)" % (name, name))
    g = lambda k: _hex(_var(css, k))
    bg, bg2, fg, muted, ac, ac2 = g("bg"), g("bg2"), g("fg"), g("muted"), g("accent"), g("accent2")
    dark = (_var(css, "color-scheme") or "").startswith("dark")
    # card / border are rgba in CSS; precompute opaque equivalents
    cv = _var(css, "card") or ""
    card = _hex(cv) if cv.startswith("#") else _mix(bg, fg, 0.07)
    border = _mix(bg, fg, 0.18)
    head = _var(css, "font-head") or ""
    serif = "Georgia" in head
    mono = "ui-monospace" in head
    ds = (_var(css, "deck-style") or "").strip(); glass = ds in ("vivid", "flat")   # multi-colour tinted-card styles
    flat = ds == "flat"
    hc = _var(css, "head-color"); head_c = _hex(hc) if hc and hc.startswith("#") else fg
    a3 = _var(css, "accent3")
    ac3 = _hex(a3) if a3 and a3.startswith("#") else ac2
    if glass:
        card = (255, 255, 255)
        bc = _var(css, "border") or ""
        border = _hex(bc) if bc.startswith("#") else (221, 229, 239)
    return {
        "glass": glass, "flat": flat, "style_name": ds or None, "head": head_c, "accent3": ac3,
        "name": name, "dark": dark, "bg": bg, "bg2": bg2, "fg": fg, "muted": muted,
        "accent": ac, "accent2": ac2, "card": card, "border": border,
        "good": (34, 197, 94), "bad": (239, 68, 68), "warn": (245, 158, 11),
        "on_accent": (255, 255, 255) if glass else bg,  # text on accent fills
        "font_head": "Consolas" if mono else ("Georgia" if serif else "Calibri"),
        "font_body": "Calibri", "font_mono": "Consolas",
        "radius": min(int(re.search(r"(\d+)px", _var(css, "radius") or "12px").group(1)), 32),
        "heavy": int(_var(css, "head-weight") or 800) >= 700,
        "upper": (_var(css, "head-transform") or "") == "uppercase",
    }
