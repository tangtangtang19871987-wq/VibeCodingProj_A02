"""Shared geometry / palette / icons for `diagram` slides — used by BOTH the HTML renderer and the PPTX builder,
so the two outputs are identical in layout.

Logical canvas: 1000 x 490 units. Every element has x,y,(w,h) in units.

element kinds
  node    id,x,y,w,h, shape(round|pill|diamond), tone, icon?, label, sub?, layout(row|stack), dashed?
  group   x,y,w,h, tone, label, scale?                 (lane container with header pill)
  note    x,y,w,h, n, text, tone?              (numbered annotation card)
  chip    x,y, text, tone                      (small label pill; w auto)
  panel   x,y,w,h, tone, title?, icon?, in?, dashed?, body: one of
            {"code": "..."} | {"bullets": [...]} | {"items": [{icon,tone,title,sub?}]} |
            {"rows": [{chip,tone,text:[...]}]} | {"legend": [{style,tone,text}]} | {"text": "..."}
  text    x,y,w,h, text, size?, bold?, tone?   (free text)
  heading x,y,w, kicker?, title (\\n ok), tagline?
  cubes   x,y,w,h                              (3D glass-cube cluster)
edges: from,to, style(solid|dashed), tone?, fs/ts (l|r|t|b), fo/ti (0..1 position along the source / target side), mid (0..1), via [[x,y],..],
       bulge, label, label_tone, label_at [x,y]
"""
import math

CW, CH = 1000, 490

# Semantic palette — MEASURED from the user's reference images:
#   page #fdfdfe (near white) · titles deep navy · card fills = pale tints · borders = clear mid/vivid tone colour (1.5px)
#   icons / labels / edges = vivid tone colour · lane header pills = solid tone with white text.
#   blue   = input / data / general flow / branching         purple = model / agent / runtime / instructions
#   green  = tools / storage / success                       orange = state / progress / answer / retry
#   pink   = memory / long-term knowledge                    gray   = start / end / neutral          dark = navy lines
TONES = {  # border, tint (fill), solid (icon / label / line)
    "blue":   {"border": (140, 184, 236), "soft": (208, 226, 247), "fill": (230, 241, 253), "solid": (20, 112, 232)},
    "purple": {"border": (172, 160, 232), "soft": (216, 203, 247), "fill": (233, 226, 252), "solid": (108, 60, 236)},
    "green":  {"border": (56, 180, 124), "soft": (192, 233, 215),  "fill": (224, 245, 234), "solid": (8, 148, 100)},
    "orange": {"border": (250, 150, 70), "soft": (250, 216, 180),  "fill": (254, 237, 221), "solid": (240, 138, 28)},
    "pink":   {"border": (240, 140, 175), "soft": (250, 204, 221), "fill": (254, 231, 239), "solid": (232, 62, 116)},
    "gray":   {"border": (168, 178, 202), "soft": (204, 211, 229), "fill": (224, 231, 245), "solid": (92, 108, 142)},
    "dark":   {"border": (16, 44, 88), "soft": (160, 174, 200),    "fill": (238, 242, 249), "solid": (16, 44, 88)},
}
NEUTRAL = {"gray", "dark"}
RETIRED = {"teal": "blue"}   # not in the reference palette — validate() tells the author what to use

# 24x24 stroke icons (stroke-width 2, round caps). Own simple geometry.
ICONS = {
    "sliders": "M4 6h9 M17 6h3 M13 4v4 M4 12h3 M11 12h9 M7 10v4 M4 18h11 M19 18h1 M15 16v4",
    "doc": "M6 3h8l4 4v14H6z M14 3v4h4 M9 12h6 M9 16h6",
    "chat": "M4 5h16v11H9l-5 4z M8 10.5h.01 M12 10.5h.01 M16 10.5h.01",
    "wrench": "M14.5 6.5a4 4 0 0 0-5 5L4 17l3 3 5.5-5.5a4 4 0 0 0 5-5l-2.5 2.5-2.5-.5-.5-2.5z",
    "database": "M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3z M4 6v6c0 1.7 3.6 3 8 3s8-1.3 8-3V6 M4 12v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6",
    "memory": "M7 7h10v10H7z M10 3v4 M14 3v4 M10 17v4 M14 17v4 M3 10h4 M3 14h4 M17 10h4 M17 14h4",
    "gear": "M12 8.5a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7z M12 2.5v3 M12 18.5v3 M2.5 12h3 M18.5 12h3 M5.3 5.3l2.1 2.1 M16.6 16.6l2.1 2.1 M18.7 5.3l-2.1 2.1 M7.4 16.6l-2.1 2.1",
    "robot": "M6 8h12a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2z M12 8V4 M12 4h.01 M9 13h.01 M15 13h.01 M2 12v3 M22 12v3",
    "bulb": "M9 18h6 M10 21h4 M12 3a6 6 0 0 0-3.5 10.9c.6.5 1 1.2 1 2.1h5c0-.9.4-1.6 1-2.1A6 6 0 0 0 12 3z",
    "code": "M8 7l-5 5 5 5 M16 7l5 5-5 5 M14 4l-4 16",
    "layers": "M12 3l9 5-9 5-9-5z M3 13l9 5 9-5",
    "search": "M10.5 4a6.5 6.5 0 1 0 0 13 6.5 6.5 0 0 0 0-13z M16 16l5 5",
    "filter": "M3 5h18l-7 8v6l-4 2v-8z",
    "refresh": "M20 11a8 8 0 0 0-14-4L4 9 M4 4v5h5 M4 13a8 8 0 0 0 14 4l2-2 M20 20v-5h-5",
    "cube": "M12 3l8 4.5v9L12 21l-8-4.5v-9z M12 12l8-4.5 M12 12v9 M12 12L4 7.5",
    "share": "M15.5 5a2.5 2.5 0 1 0 5 0 2.5 2.5 0 1 0-5 0 M3.5 12a2.5 2.5 0 1 0 5 0 2.5 2.5 0 1 0-5 0 M15.5 19a2.5 2.5 0 1 0 5 0 2.5 2.5 0 1 0-5 0 M8.2 10.8l7.6-4.4 M8.2 13.2l7.6 4.4",
    "history": "M12 7v5l3 2 M3 12a9 9 0 1 0 3-6.7L3 8 M3 3v5h5",
    "play": "M8 5l11 7-11 7z",
    "flag": "M5 21V4 M5 4h12l-2 4 2 4H5",
    "split": "M12 3v6 M12 9L6 15v6 M12 9l6 6v6",
    "bolt": "M13 2L4 14h7l-1 8 9-12h-7z",
    "shield": "M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z",
    "user": "M8 8a4 4 0 1 0 8 0 4 4 0 1 0-8 0 M4 21a8 8 0 0 1 16 0",
    "check": "M5 12l5 5 9-10",
    "lock": "M6 11h12v10H6z M8 11V7a4 4 0 0 1 8 0v4",
    "globe": "M3 12a9 9 0 1 0 18 0 9 9 0 1 0-18 0 M3 12h18 M12 3c3 3 3 15 0 18 M12 3c-3 3-3 15 0 18",
    "server": "M4 4h16v6H4z M4 14h16v6H4z M8 7h.01 M8 17h.01",
    "terminal": "M4 5h16v14H4z M8 10l3 2-3 2 M13 15h4",
    "cloud": "M7 18a4 4 0 0 1-.5-8A6 6 0 0 1 18 9.5 4.3 4.3 0 0 1 17 18z",
    "link": "M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1 M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1",
}


def tone(name): return TONES.get(name) or TONES["blue"]


def rgbhex(c): return "#%02x%02x%02x" % tuple(c)


# ---------------------------------------------------------------- geometry
def rect(e):
    if e["kind"] == "chip": return (e["x"], e["y"], chip_w(e), 22)
    if e["kind"] == "heading": return (e["x"], e["y"], e["w"], e.get("h", 190))
    return (e["x"], e["y"], e.get("w", 0), e.get("h", 0))


def chip_w(e): return max(50, sum(13 if ord(c) > 255 else 7.4 for c in e["text"]) + 26)


def anchor(e, side, frac=.5):
    x, y, w, h = rect(e)
    return {"l": (x, y + h * frac), "r": (x + w, y + h * frac), "t": (x + w * frac, y), "b": (x + w * frac, y + h)}[side]


def side_toward(e, p):
    x, y, w, h = rect(e); dx, dy = p[0] - (x + w / 2), p[1] - (y + h / 2)
    return ("r" if dx > 0 else "l") if abs(dx) / max(w, 1) >= abs(dy) / max(h, 1) else ("b" if dy > 0 else "t")


def auto_sides(a, b):
    ax, ay, aw, ah = rect(a); bx, by, bw, bh = rect(b)
    gx = abs((ax + aw / 2) - (bx + bw / 2)) - (aw + bw) / 2; gy = abs((ay + ah / 2) - (by + bh / 2)) - (ah + bh) / 2
    if gx >= gy: return ("r", "l") if (bx + bw / 2) >= (ax + aw / 2) else ("l", "r")
    return ("b", "t") if (by + bh / 2) >= (ay + ah / 2) else ("t", "b")


def route(ed, M):
    """-> (points, label_point) in units."""
    a, b = M[ed["from"]], M[ed["to"]]; fo, ti = ed.get("fo", .5), ed.get("ti", .5); mid = ed.get("mid", .5)
    if ed.get("via"):
        via = [tuple(p) for p in ed["via"]]
        fs = ed.get("fs") or side_toward(a, via[0]); ts = ed.get("ts") or side_toward(b, via[-1])
        pts = [anchor(a, fs, fo)] + via + [anchor(b, ts, ti)]
    else:
        fs, ts = ed.get("fs"), ed.get("ts")
        if not (fs and ts): fs, ts = auto_sides(a, b)
        (x1, y1), (x2, y2) = anchor(a, fs, fo), anchor(b, ts, ti)
        hz = lambda s: s in "lr"
        if fs == ts:
            bl = ed.get("bulge", 30)
            if fs == "t": y = min(y1, y2) - bl; pts = [(x1, y1), (x1, y), (x2, y), (x2, y2)]
            elif fs == "b": y = max(y1, y2) + bl; pts = [(x1, y1), (x1, y), (x2, y), (x2, y2)]
            elif fs == "l": x = min(x1, x2) - bl; pts = [(x1, y1), (x, y1), (x, y2), (x2, y2)]
            else: x = max(x1, x2) + bl; pts = [(x1, y1), (x, y1), (x, y2), (x2, y2)]
        elif hz(fs) and hz(ts):
            xm = x1 + (x2 - x1) * mid; pts = [(x1, y1), (x2, y2)] if abs(y1 - y2) < .5 else [(x1, y1), (xm, y1), (xm, y2), (x2, y2)]
        elif not hz(fs) and not hz(ts):
            ym = y1 + (y2 - y1) * mid; pts = [(x1, y1), (x2, y2)] if abs(x1 - x2) < .5 else [(x1, y1), (x1, ym), (x2, ym), (x2, y2)]
        elif hz(fs): pts = [(x1, y1), (x2, y1), (x2, y2)]
        else: pts = [(x1, y1), (x1, y2), (x2, y2)]
    if ed.get("label_at"): lab = tuple(ed["label_at"])
    elif len(pts) == 2: lab = ((pts[0][0] + pts[1][0]) / 2, (pts[0][1] + pts[1][1]) / 2)
    elif len(pts) == 3: lab = pts[1]
    else: lab = ((pts[1][0] + pts[2][0]) / 2, (pts[1][1] + pts[2][1]) / 2)
    return pts, lab


def round_poly(pts, r=9, n=5):
    """Replace sharp corners by sampled quadratic curves (works in SVG and PPTX freeforms)."""
    if len(pts) < 3 or r <= 0: return list(pts)
    out = [pts[0]]
    for i in range(1, len(pts) - 1):
        p0, v, p2 = pts[i - 1], pts[i], pts[i + 1]
        l1, l2 = math.dist(p0, v), math.dist(v, p2)
        if l1 < 1e-6 or l2 < 1e-6: out.append(v); continue
        rr = min(r, l1 / 2, l2 / 2)
        a = (v[0] + (p0[0] - v[0]) * rr / l1, v[1] + (p0[1] - v[1]) * rr / l1); b = (v[0] + (p2[0] - v[0]) * rr / l2, v[1] + (p2[1] - v[1]) * rr / l2)
        for k in range(n + 1):
            t = k / n; out.append(((1 - t) ** 2 * a[0] + 2 * t * (1 - t) * v[0] + t * t * b[0], (1 - t) ** 2 * a[1] + 2 * t * (1 - t) * v[1] + t * t * b[1]))
    out.append(pts[-1]); return out


def edge_color(ed, M, default="source"):
    t = ed.get("tone")
    if not t:
        if ed.get("style") == "dashed" and default != "source": t = "purple"
        elif default == "source": t = M[ed["from"]].get("tone") or "blue"
        else: t = default
    return tone(t)["solid"] if t in TONES else (47, 107, 255)


def cube_faces(cx, cy, e):
    k = 0.866 * e
    T, R, C, L = (cx, cy - e), (cx + k, cy - e / 2), (cx, cy), (cx - k, cy - e / 2)
    B, BL, BR = (cx, cy + e), (cx - k, cy + e / 2), (cx + k, cy + e / 2)
    return {"top": [T, R, C, L], "left": [L, C, B, BL], "right": [C, R, BR, B]}


# 3 soft flat cubes inside a w x h box: (cx frac, cy frac, edge frac of w, (top, left, right) flat colours)
CUBE_SET = [
    (0.34, 0.30, 0.17, [(178, 230, 212), (140, 212, 188), (112, 196, 170)]),
    (0.58, 0.64, 0.30, [(216, 209, 245), (180, 168, 232), (152, 138, 218)]),
    (0.18, 0.72, 0.12, [(196, 218, 245), (156, 190, 238), (126, 168, 228)]),
]
CUBE_DOTS = [(0.80, 0.34, 0.035, (150, 138, 218)), (0.12, 0.38, 0.02, (112, 196, 170)), (0.86, 0.80, 0.018, (126, 168, 228))]


# ---------------------------------------------------------------- validation
def elements(s): return s.get("elements", [])


def validate(s):
    """Return list of (severity, message) for one diagram slide."""
    probs = []; els = elements(s); M = {e["id"]: e for e in els if e.get("id")}
    for e in els:
        k = e.get("kind")
        if k not in ("node", "group", "note", "chip", "panel", "text", "heading", "cubes"): probs.append(("ERROR", "unknown element kind %r" % k)); continue
        if e.get("tone") in RETIRED: probs.append(("ERROR", "tone %r is not in the palette — use %r (palette: blue, purple, green, orange, gray, dark)" % (e["tone"], RETIRED[e["tone"]])))
        elif e.get("tone") and e["tone"] not in TONES: probs.append(("ERROR", "unknown tone %r" % e["tone"]))
        if e.get("icon") and e["icon"] not in ICONS: probs.append(("ERROR", "unknown icon %r (valid: %s)" % (e["icon"], ", ".join(sorted(ICONS)))))
        x, y, w, h = rect(e)
        if x < -0.5 or y < -0.5 or x + w > CW + 0.5 or y + h > CH + 0.5: probs.append(("ERROR", "%s %r out of canvas (%.0f,%.0f,%.0f,%.0f) — canvas is %dx%d" % (k, e.get("id") or e.get("label") or e.get("title") or e.get("text", "")[:12], x, y, w, h, CW, CH)))
    flat = [e for e in els if e.get("kind") not in ("group",)]
    for i, a in enumerate(flat):
        for b in flat[i + 1:]:
            if a.get("in") == b.get("id") or b.get("in") == a.get("id") and a.get("id"): continue
            ax, ay, aw, ah = rect(a); bx, by, bw, bh = rect(b)
            ox, oy = min(ax + aw, bx + bw) - max(ax, bx), min(ay + ah, by + bh) - max(ay, by)
            if ox > 2 and oy > 2:
                nm = lambda e: "%s %r" % (e["kind"], e.get("id") or e.get("label") or e.get("title") or e.get("text", "")[:12])
                probs.append(("ERROR", "overlap: %s x %s" % (nm(a), nm(b))))
    for ed in s.get("edges", []):
        if ed.get("from") not in M or ed.get("to") not in M: probs.append(("ERROR", "edge %s->%s references unknown id" % (ed.get("from"), ed.get("to")))); continue
        pts, _ = route(ed, M)
        for e in els:
            if e.get("kind") not in ("node", "panel") or e.get("id") in (ed["from"], ed["to"]) or e.get("in") in (ed["from"], ed["to"]): continue
            x, y, w, h = rect(e)
            for p, q in zip(pts, pts[1:]):
                lx0, lx1, ly0, ly1 = min(p[0], q[0]), max(p[0], q[0]), min(p[1], q[1]), max(p[1], q[1])
                if lx1 > x + 3 and lx0 < x + w - 3 and ly1 > y + 3 and ly0 < y + h - 3:
                    probs.append(("WARN", "edge %s->%s crosses %s %r" % (ed["from"], ed["to"], e["kind"], e.get("id") or e.get("label") or e.get("title")))); break
    return probs


def tones_used(s):
    """Non-neutral tones used on one diagram slide."""
    used = set()
    def add(t):
        if t and t not in NEUTRAL: used.add(t)
    for e in s.get("elements", []):
        if e.get("kind") in ("node", "group", "note", "chip", "panel"): add(e.get("tone", "blue"))
        b = e.get("body", {})
        for k in ("items", "rows", "legend"):
            for it in b.get(k, []): add(it.get("tone", e.get("tone", "blue")))
    for ed in s.get("edges", []):
        for k in ("tone", "label_tone"): add(ed.get(k))
    return used
