#!/usr/bin/env python3
"""outline.json -> html-ppt-studio deck (the visual design draft / live-presentation version).

  python3 outline_to_html.py outline.json out.html [--theme NAME] [--transition fade|slide|zoom|none]

Uses the same slide types and theme names as python-pptx/outline_to_pptx.py, so the two outputs match.
"""
import argparse, html, json, os, subprocess, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "python-pptx", "scripts"))
import diagram_geom as G

HERE = os.path.dirname(os.path.abspath(__file__))
STUDIO = os.path.normpath(os.path.join(HERE, "..", "..", "html-ppt-studio"))
e = lambda x: html.escape(str(x), quote=True)

EXTRA_CSS = """
.layout-layers .ly{display:flex;flex-direction:column;gap:20px}
.layout-layers .row-l{display:grid;grid-template-columns:260px 1fr;gap:24px;align-items:stretch}
.layout-layers .lab{display:grid;place-items:center;border-radius:var(--radius);background:linear-gradient(135deg,var(--accent),var(--accent2));color:var(--bg);font-weight:800;font-size:34px;padding:20px}
.layout-layers .its{display:flex;gap:20px}.layout-layers .it{flex:1;display:grid;place-items:center;text-align:center;padding:22px;font-size:30px}
.layout-layers .arrow{text-align:center;color:var(--muted);font-size:26px;line-height:.7}
.layout-line .chart{flex:1;min-height:0}.layout-line svg{width:100%;height:100%}
.layout-pie .pie{display:flex;gap:80px;align-items:center;justify-content:center;height:100%}
.layout-pie .disc{width:520px;height:520px;border-radius:50%}
.layout-pie .lg div{font-size:34px;margin:14px 0;display:flex;gap:16px;align-items:center}.layout-pie .lg i{width:28px;height:28px;border-radius:6px;display:inline-block}
.takeaway{margin-top:28px;padding-left:28px;border-left:8px solid var(--accent);font-size:36px}
.src{position:absolute;left:120px;bottom:70px;font-size:20px;color:var(--muted)}
.layout-code pre{font-size:28px}
"""
PAL = ["var(--accent)", "var(--accent2)", "var(--good)", "var(--warn)", "var(--muted)"]



CUBE = """<svg viewBox="0 0 560 620" xmlns="http://www.w3.org/2000/svg">
<defs>
<linearGradient id="gt" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#1fd6a0"/><stop offset="1" stop-color="#2f7bff"/></linearGradient>
<linearGradient id="gl" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#2f7bff"/><stop offset="1" stop-color="#7c4dff"/></linearGradient>
<linearGradient id="gr" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#7c4dff"/><stop offset="1" stop-color="#b38cff"/></linearGradient>
<radialGradient id="sh"><stop offset="0" stop-color="#3c5ac8" stop-opacity=".30"/><stop offset="1" stop-color="#3c5ac8" stop-opacity="0"/></radialGradient>
</defs>
<ellipse cx="280" cy="560" rx="170" ry="30" fill="url(#sh)"/>
<g stroke="#8aa0e6" stroke-width="2.5" stroke-dasharray="9 8" fill="none" opacity=".75">
<path d="M150 260 L40 170"/><path d="M410 260 L520 160"/><path d="M410 380 L525 470"/><path d="M150 380 L45 480"/><path d="M280 140 L280 40"/></g>
<g fill="rgba(255,255,255,.9)" stroke="#9fb3f0" stroke-width="2">
<circle cx="40" cy="170" r="20"/><circle cx="520" cy="160" r="20"/><circle cx="525" cy="470" r="20"/><circle cx="45" cy="480" r="20"/><circle cx="280" cy="40" r="20"/></g>
<g fill="#2f7bff"><circle cx="40" cy="170" r="8"/><circle cx="520" cy="160" r="8" fill="#7c4dff"/><circle cx="525" cy="470" r="8" fill="#1fd6a0"/><circle cx="45" cy="480" r="8" fill="#7c4dff"/><circle cx="280" cy="40" r="8" fill="#1fd6a0"/></g>
<g data-anim="float" style="--t:5s">
<polygon points="280,150 410,225 280,300 150,225" fill="url(#gt)" fill-opacity=".92" stroke="#fff" stroke-opacity=".85" stroke-width="3"/>
<polygon points="150,225 280,300 280,455 150,380" fill="url(#gl)" fill-opacity=".90" stroke="#fff" stroke-opacity=".7" stroke-width="3"/>
<polygon points="410,225 280,300 280,455 410,380" fill="url(#gr)" fill-opacity=".88" stroke="#fff" stroke-opacity=".7" stroke-width="3"/>
<polygon points="280,215 340,250 280,285 220,250" fill="#fff" fill-opacity=".28" stroke="#fff" stroke-opacity=".8" stroke-width="2"/>
<path d="M280 300 V455" stroke="#fff" stroke-opacity=".6" stroke-width="2"/></g>
</svg>"""


def _anchor(n, side, nw, nh):
    x, y = n["_x"], n["_y"]
    return {"r": (x + nw, y + nh / 2), "l": (x, y + nh / 2), "t": (x + nw / 2, y), "b": (x + nw / 2, y + nh)}[side]


_DAG_N = [0]


def dag(nodes, edges, W, H, nw, nh, cls=""):
    _DAG_N[0] += 1; uid = _DAG_N[0]
    """Positioned glass nodes + SVG edges. nodes: id,label,icon?,sub?,x,y in 0..1 ; edges: from,to,style(solid|dashed),label?,route(above|below)?"""
    byid = {}
    for n in nodes:
        n["_x"] = n.get("x", 0) * (W - nw); n["_y"] = n.get("y", 0.5) * (H - nh); byid[n["id"]] = n
    paths, labels = [], []
    for ed in edges:
        a, b = byid[ed["from"]], byid[ed["to"]]; st = ed.get("style", "solid"); route = ed.get("route")
        if route in ("above", "below"):
            s_, t_ = ("t", "t") if route == "above" else ("b", "b"); (x1, y1), (x2, y2) = _anchor(a, s_, nw, nh), _anchor(b, t_, nw, nh)
            off = -46 if route == "above" else 46; d = "M%.0f %.0f V%.0f H%.0f V%.0f" % (x1, y1, y1 + off, x2, y2); lx, ly = (x1 + x2) / 2, y1 + off
        elif ed.get("fs") and ed.get("ts"):   # explicit sides: orthogonal elbow
            s_, t_ = ed["fs"], ed["ts"]; (x1, y1), (x2, y2) = _anchor(a, s_, nw, nh), _anchor(b, t_, nw, nh)
            if s_ in "tb" and t_ in "lr": d = "M%.0f %.0f V%.0f H%.0f" % (x1, y1, y2, x2)
            elif s_ in "lr" and t_ in "tb": d = "M%.0f %.0f H%.0f V%.0f" % (x1, y1, x2, y2)
            else: d = "M%.0f %.0f L%.0f %.0f" % (x1, y1, x2, y2)
            lx, ly = (x1 + x2) / 2, (y1 + y2) / 2
        else:
            dx, dy = (b["_x"] - a["_x"]), (b["_y"] - a["_y"])
            if abs(dx) >= abs(dy) * 0.6 or abs(dx) > nw:
                s_, t_ = ("r", "l") if dx >= 0 else ("l", "r"); (x1, y1), (x2, y2) = _anchor(a, s_, nw, nh), _anchor(b, t_, nw, nh); xm = (x1 + x2) / 2
                d = "M%.0f %.0f L%.0f %.0f" % (x1, y1, x2, y2) if abs(y1 - y2) < 2 else "M%.0f %.0f H%.0f V%.0f H%.0f" % (x1, y1, xm, y2, x2)
            else:
                s_, t_ = ("b", "t") if dy >= 0 else ("t", "b"); (x1, y1), (x2, y2) = _anchor(a, s_, nw, nh), _anchor(b, t_, nw, nh); ym = (y1 + y2) / 2
                d = "M%.0f %.0f L%.0f %.0f" % (x1, y1, x2, y2) if abs(x1 - x2) < 2 else "M%.0f %.0f V%.0f H%.0f V%.0f" % (x1, y1, ym, x2, y2)
            lx, ly = (x1 + x2) / 2, (y1 + y2) / 2
        paths.append('<path class="e-%s" d="%s" marker-end="url(#ah%d-%s)"/>' % (st, d, uid, st))
        if ed.get("label"): labels.append('<div class="elabel" style="left:%.0fpx;top:%.0fpx">%s</div>' % (lx, ly, e(ed["label"])))
    defs = ('<defs><marker id="ah%d-solid" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto"><path d="M0,0 L7,3.5 L0,7 z" style="fill:var(--accent)"/></marker>'
            '<marker id="ah%d-dashed" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto"><path d="M0,0 L7,3.5 L0,7 z" style="fill:var(--accent2)"/></marker></defs>') % (uid, uid)
    nd = "".join('<div class="node" style="left:%.0fpx;top:%.0fpx;width:%dpx;height:%dpx"><div class="ni">%s</div><div><b>%s</b>%s</div></div>' % (
        n["_x"], n["_y"], nw, nh, e(n.get("icon", "◆")), e(n["label"]), "<small>%s</small>" % e(n["sub"]) if n.get("sub") else "") for n in nodes)
    return '<div class="dag %s" style="width:%dpx;height:%dpx"><svg viewBox="0 0 %d %d">%s%s</svg>%s%s</div>' % (cls, W, H, W, H, defs, "".join(paths), nd, "".join(labels))



US = 1.76   # px per logical unit


def _svgicon(name): return '<svg viewBox="0 0 24 24"><path d="%s"/></svg>' % G.ICONS.get(name, G.ICONS["cube"])


def _tv(tn):
    t = G.tone(tn); return "--tb:%s;--tf:%s;--ts:%s" % (G.rgbhex(t["border"]), G.rgbhex(t["fill"]), G.rgbhex(t["solid"]))


def _pos(e, extra=""):
    x, y, w, h = G.rect(e); return 'style="left:%.1fpx;top:%.1fpx;width:%.1fpx;height:%.1fpx;--u:%spx;%s%s"' % (x * US, y * US, w * US, h * US, US, _tv(e.get("tone", "blue")), extra)


def _cubes_svg(e):
    x, y, w, h = G.rect(e); S = US; uid = "cb%d" % id(e); defs = []; out = []
    for ci, (fx, fy, fe, cols) in enumerate(G.CUBE_SET):
        faces = G.cube_faces(x + fx * w, y + fy * h, fe * w)
        for fi, (fname, pts) in enumerate(faces.items()):
            gid = "%s-%d-%d" % (uid, ci, fi); c0, c1 = cols[fi]
            defs.append('<linearGradient id="%s" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="%s"/><stop offset="1" stop-color="%s"/></linearGradient>' % (gid, G.rgbhex(c0), G.rgbhex(c1)))
            out.append('<polygon points="%s" fill="url(#%s)" fill-opacity=".86" stroke="#fff" stroke-opacity=".9" stroke-width="2"/>' % (" ".join("%.1f,%.1f" % (a * S, b * S) for a, b in pts), gid))
    for fx, fy, fr, col in G.CUBE_DOTS: out.append('<circle cx="%.1f" cy="%.1f" r="%.1f" fill="%s" fill-opacity=".85"/>' % ((x + fx * w) * S, (y + fy * h) * S, fr * w * S, G.rgbhex(col)))
    return '<g data-anim="float" style="--t:6s"><defs>%s</defs>%s</g>' % ("".join(defs), "".join(out))


_DG_N = [0]


def render_diagram(s):
    global US
    US = 1.76 if s.get("cover") else 1.6; _DG_N[0] += 1; pre = "m%d" % _DG_N[0]
    els = s.get("elements", []); M = {e["id"]: e for e in els if e.get("id")}; parts = []; svg_art = []
    for e in els:
        k = e["kind"]; tn = e.get("tone", "blue")
        if k == "group":
            x, y, w, h = G.rect(e); parts.append('<div class="grp" %s></div>' % _pos(e))
            lw = max(120, sum(18 if ord(c) > 255 else 10 for c in e.get("label", "")) + 56)
            parts.append('<div class="gh" style="left:%.1fpx;top:%.1fpx;width:%.1fpx;height:%.1fpx;--u:%spx;%s">%s</div>' % ((x + 18) * US, (y - 15) * US, lw * US, 30 * US, US, _tv(tn), html.escape(e.get("label", ""))))
        elif k == "node":
            shp = e.get("shape", "round"); lay = "stack" if (e.get("layout") == "stack" or (shp == "diamond" and e.get("icon"))) else "row"
            x, y, w, h = G.rect(e); isz = 30 if lay == "row" else 30
            ic = '<span class="ico" style="width:calc(var(--u)*%d);height:calc(var(--u)*%d)">%s</span>' % (isz, isz, _svgicon(e["icon"])) if e.get("icon") else ""
            tx = '<div class="tx"><b>%s</b>%s</div>' % (html.escape(e.get("label", "")), "<small>%s</small>" % html.escape(e["sub"]) if e.get("sub") else "")
            if shp == "diamond":
                W_, H_ = w * US, h * US; poly = "%.0f,2 %.0f,%.0f %.0f,%.0f 2,%.0f" % (W_ / 2, W_ - 2, H_ / 2, W_ / 2, H_ - 2, H_ / 2); t = G.tone(tn)
                bg = '<svg class="bg" viewBox="0 0 %.0f %.0f"><polygon points="%s" fill="%s" stroke="%s" stroke-width="2.5"/></svg>' % (W_, H_, poly, G.rgbhex(t["fill"]), G.rgbhex(t["border"]))
                parts.append('<div class="dn diamond" %s>%s<div class="tx" style="position:relative;display:flex;flex-direction:column;align-items:center">%s%s</div></div>' % (_pos(e), bg, ic, tx.replace('<div class="tx">', '<div style="text-align:center">', 1)))
            else:
                cls = "dn %s%s%s%s" % ("pill " if shp == "pill" else "", "stack " if lay == "stack" else "", "top " if e.get("valign") == "top" else "", "dashed" if e.get("dashed") else "")
                parts.append('<div class="%s" %s>%s%s</div>' % (cls, _pos(e), ic, tx))
        elif k == "note":
            n = e.get("n"); badge = '<span class="ico">%s</span>' % n if n is not None else ""
            parts.append('<div class="note" %s>%s<span>%s</span></div>' % (_pos(e), badge, html.escape(e["text"])))
        elif k == "chip":
            x, y, w, h = G.rect(e); parts.append('<div class="chip2" style="left:%.1fpx;top:%.1fpx;width:%.1fpx;height:%.1fpx;--u:%spx;%s">%s</div>' % (x * US, y * US, w * US, h * US, US, _tv(tn), html.escape(e["text"])))
        elif k == "panel":
            b = e.get("body", {}); ttl = ""
            if e.get("title"): ttl = '<h4>%s%s</h4>' % ('<span class="ico">%s</span>' % _svgicon(e["icon"]) if e.get("icon") and not e.get("stack") else "", html.escape(e["title"]))
            if e.get("stack"):
                ttl = ('<span class="ico">%s</span>' % _svgicon(e["icon"]) if e.get("icon") else "") + ttl
            if "code" in b: body = "<pre>%s</pre>" % html.escape(b["code"])
            elif "bullets" in b: body = "<ul>%s</ul>" % "".join("<li>%s</li>" % html.escape(i) for i in b["bullets"])
            elif "items" in b: body = "".join('<div class="it" style="%s"><span class="ico">%s</span><div><b>%s</b>%s</div></div>' % (_tv(i.get("tone", tn)), _svgicon(i.get("icon", "cube")), html.escape(i["title"]), "<small>%s</small>" % html.escape(i["sub"]) if i.get("sub") else "") for i in b["items"])
            elif "rows" in b: body = "".join('<div class="rw" style="%s"><div class="c">%s</div><ul>%s</ul></div>' % (_tv(r.get("tone", tn)), html.escape(r["chip"]), "".join("<li>%s</li>" % html.escape(t_) for t_ in r["text"])) for r in b["rows"])
            elif "legend" in b: body = "".join('<div class="lg" style="%s"><i class="%s"></i>%s</div>' % (_tv(l.get("tone", "dark")), "d" if l.get("style") == "dashed" else "", html.escape(l["text"])) for l in b["legend"])
            elif "text" in b: body = "<p>%s</p>" % html.escape(b["text"])
            else: body = ""
            parts.append('<div class="pn %s%s" %s>%s%s</div>' % ("dashed " if e.get("dashed") else "", "stk" if e.get("stack") else "", _pos(e), ttl, body))
        elif k == "text":
            parts.append('<div class="txt" %s style="font-size:%.1fpx">%s</div>' % ("", e.get("size", 13) * US, html.escape(e["text"])) if False else '<div class="txt" style="left:%.1fpx;top:%.1fpx;width:%.1fpx;height:%.1fpx;font-size:%.1fpx;font-weight:%s;color:%s">%s</div>' % (e["x"] * US, e["y"] * US, e["w"] * US, e.get("h", 20) * US, e.get("size", 13) * US, 800 if e.get("bold") else 400, G.rgbhex(G.tone(tn)["solid"]) if e.get("tone") else "#35416b", html.escape(e["text"])))
        elif k == "heading":
            parts.append('<div class="hd" style="left:%.1fpx;top:%.1fpx;width:%.1fpx;--u:%spx">%s<h1 class="grad-text" data-anim="fade-up">%s</h1>%s</div>' % (
                e["x"] * US, e["y"] * US, e["w"] * US, US, '<div class="k">%s</div>' % html.escape(e["kicker"]) if e.get("kicker") else "", html.escape(e["title"]), "<p>%s</p>" % html.escape(e["tagline"]) if e.get("tagline") else ""))
        elif k == "cubes": svg_art.append(_cubes_svg(e))
    # edges
    cols = {}; edge_svg = []; labels = []; ec = s.get("edge_color", "source")
    for ed in s.get("edges", []):
        pts, lab = G.route(ed, M); col = G.edge_color(ed, M, ec); hx = G.rgbhex(col); cols[hx] = 1
        rp = G.round_poly(pts, 9 if ed.get("round", True) else 0)
        d = "M" + " L".join("%.1f %.1f" % (a * US, b * US) for a, b in rp)
        edge_svg.append('<path d="%s" fill="none" stroke="%s" stroke-width="3" %s marker-end="url(#%s%s)"/>' % (d, hx, 'stroke-dasharray="10 7"' if ed.get("style") == "dashed" else "", pre, hx[1:]))
        if ed.get("label"):
            cw = G.chip_w({"text": ed["label"]}); lt = ed.get("label_tone") or ed.get("tone") or (M[ed["from"]].get("tone") or "blue")
            labels.append('<div class="chip2" style="left:%.1fpx;top:%.1fpx;width:%.1fpx;height:%.1fpx;--u:%spx;%s">%s</div>' % ((lab[0] - cw / 2) * US, (lab[1] - 11) * US, cw * US, 22 * US, US, _tv(lt), html.escape(ed["label"])))
    marks = "".join('<marker id="%s%s" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto" markerUnits="strokeWidth"><path d="M0,0 L6,3 L0,6 z" fill="#%s"/></marker>' % (pre, c[1:], c[1:]) for c in cols)
    W_, H_ = G.CW * US, G.CH * US
    # edges drawn BELOW nodes but above groups: groups first, then svg, then rest
    grp = [p for p in parts if p.startswith('<div class="grp"') or p.startswith('<div class="gh"')]; rest = [p for p in parts if p not in grp]
    art = '<svg class="art" width="%d" height="%d" viewBox="0 0 %d %d">%s</svg>' % (W_, H_, W_, H_, "".join(svg_art)) if svg_art else ""
    esv = '<svg class="edges" width="%d" height="%d" viewBox="0 0 %d %d"><defs>%s</defs>%s</svg>' % (W_, H_, W_, H_, marks, "".join(edge_svg))
    sub = '<div class="sub">%s</div>' % html.escape(s["subtitle"]) if s.get("subtitle") else ""
    hdr = "" if s.get("cover") else '<header class="slide-head"><div class="kicker" data-anim="fade-down">%s</div><h2 data-anim="fade-up">%s</h2>%s</header>' % (html.escape(s.get("kicker", "")), html.escape(s.get("title", "")), sub)
    return hdr + '<div class="dg" data-anim="fade-in" style="width:%dpx;height:%dpx;--u:%spx">%s%s%s%s%s</div>' % (
        W_, H_, US, "".join(grp), art, esv, "".join(rest), "".join(labels))


def sec(cls, inner, s):
    notes = e(s.get("notes", ""))
    src = '<div class="src">来源 / Source: %s</div>' % e(s["source"]) if s.get("source") else ""
    return '<section class="slide layout-%s" data-notes="%s">\n%s\n%s\n</section>\n' % (cls, notes, inner, src)


def head(s, kicker=None):
    k = kicker or s.get("kicker", "")
    return '<header class="slide-head"><div class="kicker" data-anim="fade-down">%s</div><h2 data-anim="fade-up">%s</h2></header>' % (e(k), e(s.get("title", "")))


def take(s, key="takeaway"):
    return '<div class="takeaway" data-anim="fade-up" style="--d:.5s">%s</div>' % e(s[key]) if s.get(key) else ""


def bl(items):
    out = []
    for it in items:
        if isinstance(it, dict): out.append("<li>%s%s</li>" % (e(it["text"]), "<small>%s</small>" % e(it["sub"]) if it.get("sub") else ""))
        else: out.append("<li>%s</li>" % e(it))
    return "".join(out)


def card_list(h, items): return '<div class="card"><h3>%s</h3><p>%s</p></div>' % (e(h), "<br>".join("• " + e(x if isinstance(x, str) else x["text"]) for x in items))


def meta_line(m): return "".join("<span>%s</span>" % e(x) for x in [m.get("author"), m.get("org"), m.get("date")] if x)


def render(o):
    m = o.get("meta", {}); out = []
    for s in o["slides"]:
        t = s["type"]
        if t == "cover":
            out.append(sec("cover", '<div class="deco" data-anim="zoom-out" style="--t:1.4s"></div><h1 data-anim="fade-up">%s</h1><p class="lead" data-anim="fade-up" style="--d:.2s">%s</p><div class="meta" data-anim="fade-up" style="--d:.4s">%s</div>' % (e(s.get("title", m.get("title", ""))), e(s.get("subtitle", "")), meta_line(m)), s))
        elif t == "section":
            out.append(sec("section", '<div class="num" data-anim="slide-up-big">%s</div><hr class="rule" data-anim="draw-line" style="--d:.3s;width:200px"><h1 data-anim="fade-up" style="--d:.3s">%s</h1><p class="lead" data-anim="fade-up" style="--d:.45s">%s</p>' % (e(s.get("number", "")), e(s["title"]), e(s.get("subtitle", ""))), s))
        elif t == "agenda":
            lis = "".join("<li><div>%s</div></li>" % e(i["text"] if isinstance(i, dict) else i) for i in s["items"])
            out.append(sec("agenda", head(s, s.get("kicker", "Agenda")) + '<ol class="agenda slide-body" data-anim-stagger="fade-up">%s</ol>' % lis, s))
        elif t == "bullets":
            out.append(sec("bullets", head(s) + '<div class="slide-body"><ul class="bullets" data-anim-stagger="fade-right" data-stagger=".18">%s</ul></div>' % bl(s["bullets"]), s))
        elif t == "two-col":
            out.append(sec("two-col", head(s) + '<div class="slide-body" data-anim-stagger="fade-up">%s%s</div>' % (card_list(s["left"].get("heading", ""), s["left"].get("bullets", [])), card_list(s["right"].get("heading", ""), s["right"].get("bullets", []))), s))
        elif t == "kpi":
            cards = "".join('<div class="card kpi"><div class="l">%s</div><div class="v">%s</div><div class="delta%s">%s</div></div>' % (e(i["label"]), e(i["value"]), " down" if str(i.get("delta", "")).strip().startswith(("▼", "-", "−")) and not i.get("good_down") else "", e(i.get("delta", ""))) for i in s["items"])
            out.append(sec("kpi-row", head(s) + '<div class="kpis" data-anim-stagger="fade-up">%s</div>%s' % (cards, take(s)), s))
        elif t == "chart":
            c = s["chart"]; k = c.get("kind", "bar"); ser = c["series"]; cats = c["categories"]
            if k in ("bar", "hbar", "stacked"):
                mx = max(v for x in ser for v in x["values"]) or 1; rows = []
                for ci, cat in enumerate(cats):
                    bars = "".join('<div class="track" style="height:26px;margin:6px 0"><div class="fill" data-anim="grow-x" style="--v:%.1f%%;--d:%.2fs;background:%s"></div></div>' % (x["values"][ci] / mx * 100, .1 + .12 * ci, PAL[si % 5]) for si, x in enumerate(ser))
                    vals = " / ".join("{:,}".format(x["values"][ci]) if isinstance(x["values"][ci], int) else str(x["values"][ci]) for x in ser)
                    rows.append('<div class="b"><span>%s</span><div>%s</div><span class="val">%s</span></div>' % (e(cat), bars, e(vals)))
                legend = "" if len(ser) < 2 else '<div class="muted small" style="margin-top:16px">%s</div>' % " &nbsp; ".join('<span style="color:%s">■</span> %s' % (PAL[i % 5], e(x["name"])) for i, x in enumerate(ser))
                out.append(sec("bar-chart", head(s) + '<div class="bars slide-body">%s</div>%s%s' % ("".join(rows), legend, take(s)), s))
            elif k == "line":
                allv = [v for x in ser for v in x["values"]]; lo, hi = min(0, min(allv)), max(allv); n = len(cats); X0, X1, Y0, Y1 = 90, 1660, 30, 430
                px = lambda i: X0 + (X1 - X0) * (i / max(n - 1, 1)); py = lambda v: Y1 - (Y1 - Y0) * ((v - lo) / ((hi - lo) or 1))
                svg = ['<svg viewBox="0 0 1720 520" preserveAspectRatio="xMidYMid meet">', '<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="var(--border)" stroke-width="2"/>' % (X0, Y1, X1, Y1)]
                for si, x in enumerate(ser):
                    pts = " ".join("%.0f,%.0f" % (px(i), py(v)) for i, v in enumerate(x["values"]))
                    svg.append('<polyline fill="none" stroke="%s" stroke-width="6" points="%s"/>' % (PAL[si % 5], pts))
                    svg += ['<circle cx="%.0f" cy="%.0f" r="9" fill="%s"/><text x="%.0f" y="%.0f" fill="var(--fg)" font-size="26" text-anchor="middle">%s</text>' % (px(i), py(v), PAL[si % 5], px(i), py(v) - 20, e(v)) for i, v in enumerate(x["values"])]
                svg += ['<text x="%.0f" y="480" fill="var(--muted)" font-size="26" text-anchor="middle">%s</text>' % (px(i), e(c_)) for i, c_ in enumerate(cats)] + ["</svg>"]
                out.append(sec("line", head(s) + '<div class="chart slide-body">%s</div>%s' % ("".join(svg), take(s)), s))
            else:  # pie
                vals = ser[0]["values"]; tot = sum(vals) or 1; acc = 0; stops = []
                for i, v in enumerate(vals): stops.append("%s %.1f%% %.1f%%" % (PAL[i % 5], acc / tot * 100, (acc + v) / tot * 100)); acc += v
                lg = "".join('<div><i style="background:%s"></i>%s — %s</div>' % (PAL[i % 5], e(cats[i]), e(v)) for i, v in enumerate(vals))
                out.append(sec("pie", head(s) + '<div class="pie slide-body"><div class="disc" style="background:conic-gradient(%s)" data-anim="zoom-in"></div><div class="lg">%s</div></div>%s' % (", ".join(stops), lg, take(s)), s))
        elif t == "table":
            th = "".join("<th>%s</th>" % e(c) for c in s["columns"]); tr = "".join("<tr>%s</tr>" % "".join('<td%s>%s</td>' % (' class="num"' if j > 0 and str(c)[:1] in "+-−$0123456789" else "", e(c)) for j, c in enumerate(r)) for r in s["rows"])
            out.append(sec("table", head(s) + '<table data-anim="fade-up"><thead><tr>%s</tr></thead><tbody>%s</tbody></table>%s' % (th, tr, take(s)), s))
        elif t == "timeline":
            ev = "".join('<div class="ev"><div class="yr">%s</div><h4>%s</h4><p>%s</p></div>' % (e(x["when"]), e(x["title"]), e(x.get("text", ""))) for x in s["events"])
            out.append(sec("timeline", head(s) + '<div class="tl" style="grid-template-columns:repeat(%d,1fr)" data-anim-stagger="fade-up" data-stagger=".18">%s</div>' % (len(s["events"]), ev), s))
        elif t == "process":
            st = "".join('<div class="step"><div class="n">0%d</div><h3>%s</h3><p>%s</p></div>' % (i, e(x["title"]), e(x.get("text", ""))) for i, x in enumerate(s["steps"], 1))
            out.append(sec("process", head(s) + '<div class="steps" data-anim-stagger="fade-right" data-stagger=".2">%s</div>' % st, s))
        elif t == "comparison":
            def col(c): return '<div class="card"><h3>%s</h3><div class="price">%s</div><ul>%s</ul></div>' % (e(c["name"]), e(c.get("tag", "")), "".join("<li>%s</li>" % e(p) for p in c["points"]))
            out.append(sec("comparison", head(s) + '<div class="vs slide-body">%s<div class="badge" data-anim="bounce-in" style="--d:.4s">VS</div>%s</div>' % (col(s["a"]), col(s["b"])), s))
        elif t == "layers":
            rows = []
            for i, L in enumerate(s["layers"]):
                its = "".join('<div class="card it">%s</div>' % e(x) for x in L["items"])
                rows.append('<div class="row-l"><div class="lab">%s</div><div class="its">%s</div></div>' % (e(L["name"]), its))
                if i < len(s["layers"]) - 1: rows.append('<div class="arrow">▼</div>')
            out.append(sec("layers", head(s) + '<div class="ly slide-body" data-anim-stagger="fade-up" data-stagger=".15">%s</div>' % "".join(rows), s))
        elif t == "code":
            out.append(sec("code", head(s) + '<div class="win" data-anim="fade-up"><header><i></i><i></i><i></i><span style="margin-left:16px">%s</span></header><pre>%s</pre></div>%s' % (e(s.get("language", "")), e(s["code"]), take(s, "caption")), s))
        elif t == "hero":
            cons = "".join('<div class="card"><div class="icon">%s</div><div><h3>%s</h3><p>%s</p></div></div>' % (e(c.get("icon", "◆")), e(c["name"]), e(c.get("desc", ""))) for c in s.get("concepts", [])[:3])
            right = dag([dict(n) for n in s.get("nodes", [])], s.get("edges", []), 620, 520, 175, 84, "sm") if s.get("nodes") else ""
            out.append(sec("hero", '<div class="h-left"><div class="kicker" data-anim="fade-down">%s</div><h1 data-anim="fade-up">%s</h1><p class="tag" data-anim="fade-up" style="--d:.2s">%s</p></div>'
                           '<div class="cube" data-anim="zoom-in" style="--t:1.1s">%s</div><div class="h-right" data-anim="fade-left" style="--d:.3s">%s</div><div class="concepts" data-anim-stagger="fade-up" style="--d:.5s">%s</div>' % (
                           e(s.get("kicker", "")), e(s.get("title", "")).replace("\n", "<br>"), e(s.get("tagline", s.get("subtitle", ""))), CUBE, right, cons), s))
        elif t == "workflow":
            leg = '<div class="legend"><span><i></i>顺序 Sequential</span><span><i class="d"></i>条件 / 循环 Conditional · Loop</span></div>'
            out.append(sec("workflow", head(s) + '<div class="dag-wrap" data-anim="fade-up"><div style="padding-bottom:64px">%s%s</div></div>%s' % (dag([dict(n) for n in s["nodes"]], s.get("edges", []), 1680, 500, 310, 116), leg, take(s)), s))
        elif t == "diagram":
            out.append(sec("diagram", render_diagram(s), s))
        elif t == "closing":
            ct = "".join('<span class="chip">%s</span>' % e(c) for c in s.get("contact", []))
            out.append(sec("closing", '<h1 class="grad-text" data-anim="bounce-in">%s</h1><p class="lead" data-anim="fade-up" style="--d:.4s">%s</p><div class="contact" data-anim-stagger="fade-up" style="--d:.6s">%s</div>' % (e(s.get("title", "Thank you")), e(s.get("subtitle", "")), ct), s))
        else:
            sys.exit("unknown slide type %r" % t)
    return "".join(out)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("outline"); ap.add_argument("out"); ap.add_argument("--theme"); ap.add_argument("--transition", default="fade")
    a = ap.parse_args(); o = json.load(open(a.outline, encoding="utf-8")); m = o.get("meta", {})
    with tempfile.TemporaryDirectory() as d:
        sf, cf = os.path.join(d, "slides.html"), os.path.join(d, "extra.css")
        open(sf, "w", encoding="utf-8").write(render(o)); open(cf, "w").write(EXTRA_CSS)
        subprocess.check_call([sys.executable, os.path.join(STUDIO, "scripts", "new_deck.py"), "--out", a.out, "--inline", "--slides-file", sf, "--extra-css", cf,
                               "--theme", a.theme or m.get("theme", "modern-tech"), "--title", m.get("title", "Deck"), "--lang", m.get("lang", "en"), "--transition", a.transition])


if __name__ == "__main__":
    main()
