"""Minimal SVG path -> polylines (for drawing icons as NATIVE PowerPoint freeform shapes instead of pictures).
Supports M m L l H h V v C c S s Q q T t A a Z z. Curves and arcs are flattened to short line segments."""
import math, re

_TOK = re.compile(r"[MmLlHhVvCcSsQqTtAaZz]|[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")


def _arc(x1, y1, rx, ry, phi, fa, fs, x2, y2, n=14):
    if rx == 0 or ry == 0 or (x1 == x2 and y1 == y2): return [(x2, y2)]
    rx, ry = abs(rx), abs(ry); ph = math.radians(phi); c, s = math.cos(ph), math.sin(ph)
    dx, dy = (x1 - x2) / 2, (y1 - y2) / 2; x1p, y1p = c * dx + s * dy, -s * dx + c * dy
    lam = x1p ** 2 / rx ** 2 + y1p ** 2 / ry ** 2
    if lam > 1: rx *= math.sqrt(lam); ry *= math.sqrt(lam)
    num = rx ** 2 * ry ** 2 - rx ** 2 * y1p ** 2 - ry ** 2 * x1p ** 2; den = rx ** 2 * y1p ** 2 + ry ** 2 * x1p ** 2
    co = math.sqrt(max(0, num / den)) * (-1 if fa == fs else 1)
    cxp, cyp = co * rx * y1p / ry, -co * ry * x1p / rx
    cx, cy = c * cxp - s * cyp + (x1 + x2) / 2, s * cxp + c * cyp + (y1 + y2) / 2
    ang = lambda ux, uy, vx, vy: math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)
    t1 = ang(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry); dt = ang((x1p - cxp) / rx, (y1p - cyp) / ry, (-x1p - cxp) / rx, (-y1p - cyp) / ry)
    if not fs and dt > 0: dt -= 2 * math.pi
    elif fs and dt < 0: dt += 2 * math.pi
    out = []
    for i in range(1, n + 1):
        t = t1 + dt * i / n; px, py = rx * math.cos(t), ry * math.sin(t)
        out.append((c * px - s * py + cx, s * px + c * py + cy))
    return out


def _bez(p0, p1, p2, p3, n=10):
    return [tuple((1 - t) ** 3 * p0[k] + 3 * (1 - t) ** 2 * t * p1[k] + 3 * (1 - t) * t * t * p2[k] + t ** 3 * p3[k] for k in (0, 1)) for t in [i / n for i in range(1, n + 1)]]


def parse(d):
    """-> list of (points, closed)."""
    tk = _TOK.findall(d); i = 0; subs = []; cur = []; x = y = sx = sy = 0.0; cmd = None; lc = None
    def flush(closed=False):
        nonlocal cur
        if len(cur) >= 2: subs.append((cur, closed))
        cur = []
    def nums(k):
        nonlocal i
        v = [float(tk[i + j]) for j in range(k)]; i += k; return v
    while i < len(tk):
        if tk[i].isalpha(): cmd = tk[i]; i += 1
        if cmd in "Zz":
            if cur: flush(True)
            x, y = sx, sy; lc = None; continue
        rel = cmd.islower(); C = cmd.upper()
        if C == "M":
            a, b = nums(2); flush(); x, y = (x + a, y + b) if rel else (a, b); sx, sy = x, y; cur = [(x, y)]; cmd = "l" if rel else "L"; lc = None
        elif C == "L":
            a, b = nums(2); x, y = (x + a, y + b) if rel else (a, b); cur.append((x, y)); lc = None
        elif C == "H":
            (a,) = nums(1); x = x + a if rel else a; cur.append((x, y)); lc = None
        elif C == "V":
            (b,) = nums(1); y = y + b if rel else b; cur.append((x, y)); lc = None
        elif C == "C":
            v = nums(6); p = [(x + v[k], y + v[k + 1]) if rel else (v[k], v[k + 1]) for k in (0, 2, 4)]; cur += _bez((x, y), *p); lc = p[1]; x, y = p[2]
        elif C == "S":
            v = nums(4); p = [(x + v[k], y + v[k + 1]) if rel else (v[k], v[k + 1]) for k in (0, 2)]
            c1 = (2 * x - lc[0], 2 * y - lc[1]) if lc else (x, y); cur += _bez((x, y), c1, p[0], p[1]); lc = p[0]; x, y = p[1]
        elif C == "Q":
            v = nums(4); q = (x + v[0], y + v[1]) if rel else (v[0], v[1]); e = (x + v[2], y + v[3]) if rel else (v[2], v[3])
            c1 = (x + 2 / 3 * (q[0] - x), y + 2 / 3 * (q[1] - y)); c2 = (e[0] + 2 / 3 * (q[0] - e[0]), e[1] + 2 / 3 * (q[1] - e[1])); cur += _bez((x, y), c1, c2, e); x, y = e; lc = None
        elif C == "A":
            rx, ry, phi, fa, fs, a, b = nums(7); ex, ey = (x + a, y + b) if rel else (a, b); cur += _arc(x, y, rx, ry, phi, int(fa), int(fs), ex, ey); x, y = ex, ey; lc = None
        else: i += 1
    flush(); return subs
