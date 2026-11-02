#!/usr/bin/env python3
"""outline.json -> html-ppt-studio deck (the visual design draft / live-presentation version).

  python3 outline_to_html.py outline.json out.html [--theme NAME] [--transition fade|slide|zoom|none]

Uses the same slide types and theme names as python-pptx/outline_to_pptx.py, so the two outputs match.
"""
import argparse, html, json, os, subprocess, sys, tempfile

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
                               "--theme", a.theme or m.get("theme", "midnight"), "--title", m.get("title", "Deck"), "--lang", m.get("lang", "en"), "--transition", a.transition])


if __name__ == "__main__":
    main()
