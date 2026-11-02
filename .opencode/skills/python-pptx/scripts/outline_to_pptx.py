#!/usr/bin/env python3
"""Build a native, editable 16:9 PPTX from an outline.json using python-pptx.

  python3 outline_to_pptx.py outline.json out.pptx [--theme NAME]

Every slide type is drawn with native shapes / charts / tables (nothing is rasterised), text is auto-fitted
to its box, titles are real title shapes (named "Title"), and speaker notes come from slide["notes"].
Theme = an html-ppt-studio theme, so the HTML preview and the PPTX match.
"""
import argparse, json, os, sys
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
from pptx.oxml.ns import qn
from lxml import etree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _fit, theme_tokens

W, H = 13.333, 7.5
MX, MY = 0.85, 0.7


def rgb(t): return RGBColor(*t)


class Deck:
    def __init__(self, outline, theme):
        self.o, self.t = outline, theme_tokens.load(theme)
        self.p = Presentation()
        self.p.slide_width, self.p.slide_height = Inches(W), Inches(H)
        self.blank = self.p.slide_layouts[6]
        self.n = 0
        self.meta = outline.get("meta", {})
        self.palette = [self.t["accent"], self.t["accent2"], self.t["accent3"], self.t["warn"], self.t["muted"]] if self.t["glass"] else [self.t["accent"], self.t["accent2"], self.t["good"], self.t["warn"], self.t["muted"]]

    # ---------- primitives ----------
    def new_slide(self, s, footer=True):
        sl = self.p.slides.add_slide(self.blank)
        self.n += 1
        bg = sl.background.fill; bg.solid(); bg.fore_color.rgb = rgb(self.t["bg"])
        if s.get("notes"): sl.notes_slide.notes_text_frame.text = s["notes"]
        if self.t["glass"]:   # soft light gradient background (renders identically in PowerPoint / LibreOffice)
            bgf = sl.background.fill; bgf.gradient(); bgf.gradient_angle = 35
            bgf.gradient_stops[0].color.rgb = RGBColor(250, 252, 255); bgf.gradient_stops[1].color.rgb = RGBColor(232, 239, 252)
        if footer:
            self.text(sl, MX, H - 0.5, 8, 0.3, self.meta.get("title", ""), 10, self.t["muted"], name="Footer")
            self.text(sl, W - MX - 1, H - 0.5, 1, 0.3, str(self.n), 10, self.t["muted"], align="r", name="PageNo")
            if s.get("source"):
                self.text(sl, MX, H - 0.82, W - 2 * MX, 0.3, "来源 / Source: " + s["source"], 10, self.t["muted"], name="Source")
        return sl

    def rect(self, sl, x, y, w, h, fill=None, line=None, shape=MSO_SHAPE.RECTANGLE, radius=None, lw=1.0, name=None):
        sh = sl.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
        if shape == MSO_SHAPE.ROUNDED_RECTANGLE:
            r = self.t["radius"] if radius is None else radius
            sh.adjustments[0] = min(0.5, r / 100.0 / max(min(w, h), 0.2) * 1.0 * 1.0) if r else 0
        if fill is None: sh.fill.background()
        else: sh.fill.solid(); sh.fill.fore_color.rgb = rgb(fill)
        if line is None: sh.line.fill.background()
        else: sh.line.color.rgb = rgb(line); sh.line.width = Pt(lw)
        sh.shadow.inherit = False
        if name: sh.name = name
        return sh

    def card(self, sl, x, y, w, h, fill=None):
        if self.t["glass"] and fill is None: return self.glass(sl, x, y, w, h)
        return self.rect(sl, x, y, w, h, fill or self.t["card"], self.t["border"], MSO_SHAPE.ROUNDED_RECTANGLE, name="Card")

    def text(self, sl, x, y, w, h, text, size, color=None, bold=False, font=None, align="l", anchor="t",
             name=None, fit=True, shape=None, spacing=1.1, min_size=11):
        """text: str | list[str] (paragraphs). Auto-shrinks to fit when fit=True."""
        paras = text if isinstance(text, list) else [text]
        if shape is not None:   # text inside an existing shape: measure the shape itself
            w, h = shape.width / 914400.0 * 0.92, shape.height / 914400.0
        wide = (1.2 if bold else 1.0) * (1.15 if (font or self.t["font_body"]) == "Georgia" else 1.0)   # wider glyphs: bold / serif
        if fit:
            fs = _fit.fit(paras, (w - 0.2) / wide, h - 0.1, size, minimum=min_size, spacing=spacing * 1.08, mono=(font == self.t["font_mono"]))
        else:
            fs = size
        tb = shape or sl.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
        tf = tb.text_frame; tf.word_wrap = True
        tf.margin_left = tf.margin_right = Inches(0.08); tf.margin_top = tf.margin_bottom = Inches(0.04)
        tf.vertical_anchor = {"t": MSO_ANCHOR.TOP, "m": MSO_ANCHOR.MIDDLE, "b": MSO_ANCHOR.BOTTOM}[anchor]
        for i, ptxt in enumerate(paras):
            para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            r = para.add_run(); r.text = str(ptxt)
            f = r.font; f.size = Pt(fs); f.bold = bold; f.name = font or self.t["font_body"]
            f.color.rgb = rgb(color or self.t["fg"])
            para.alignment = {"l": PP_ALIGN.LEFT, "c": PP_ALIGN.CENTER, "r": PP_ALIGN.RIGHT}[align]
            para.line_spacing = spacing
        if name: tb.name = name
        return tb

    def bullets(self, sl, x, y, w, h, items, size=22, color=None, sub_color=None, gap=10):
        """items: str | {"text","sub"}; real bullets (buChar)."""
        flat = []
        for it in items:
            if isinstance(it, dict):
                flat.append((it["text"], 0.3));
                if it.get("sub"): flat.append((it["sub"], 0.6))
            else: flat.append((it, 0.3))
        fs = _fit.fit(flat, w - 0.2, h - 0.1, size, minimum=12, spacing=1.2, gap_ratio=gap / size * 0.8)
        tb = sl.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h)); tf = tb.text_frame; tf.word_wrap = True
        tf.margin_left = tf.margin_right = Inches(0.08)
        first = True
        def add(txt, lvl, c, sz):
            nonlocal first
            para = tf.paragraphs[0] if first else tf.add_paragraph(); first = False
            r = para.add_run(); r.text = txt; r.font.size = Pt(sz); r.font.name = self.t["font_body"]; r.font.color.rgb = rgb(c)
            para.space_after = Pt(gap if lvl == 0 else 2); para.line_spacing = 1.1
            pPr = para._p.get_or_add_pPr()
            pPr.set("marL", str(int(Inches(0.3 + 0.3 * lvl)))); pPr.set("indent", str(-int(Inches(0.3))))
            bc = etree.SubElement(pPr, qn("a:buClr")); sc = etree.SubElement(bc, qn("a:srgbClr")); sc.set("val", "%02X%02X%02X" % self.t["accent"])
            bu = etree.SubElement(pPr, qn("a:buChar")); bu.set("char", "•" if lvl == 0 else "–")
        for it in items:
            if isinstance(it, dict):
                add(it["text"], 0, color or self.t["fg"], fs)
                if it.get("sub"): add(it["sub"], 1, sub_color or self.t["muted"], max(fs - 4, 11))
            else: add(it, 0, color or self.t["fg"], fs)
        tb.name = "Body"
        return tb

    def title(self, sl, s, kicker=None, compact=False):
        bar = self.rect(sl, MX, MY, 0.9, 0.07, self.t["accent"], name="AccentBar")
        if self.t["glass"]: self.gfill(bar)
        if kicker or s.get("kicker"):
            self.text(sl, MX, MY + 0.12, 8, 0.35, (kicker or s["kicker"]).upper(), 13, self.t["accent"], True, name="Kicker")
        t = s.get("title", "")
        th = 0.7 if compact else 0.95
        self.text(sl, MX, MY + 0.45, W - 2 * MX, th, t.upper() if self.t["upper"] else t, 34, self.t["fg"], True,
                  font=self.t["font_head"], anchor="m", name="Title", min_size=22)
        return MY + (1.3 if compact else 1.6)   # y where body starts


    # ---------- glass / gradient helpers ----------
    def gfill(self, sh, colors=None, angle=0, alphas=None):
        """Gradient fill (any number of stops). alphas in percent per stop. Replaces existing fill."""
        colors = colors or [self.t["accent"], self.t["accent2"], self.t["accent3"]]
        spPr = sh._element.spPr
        for tag in ("a:solidFill", "a:gradFill", "a:noFill", "a:pattFill", "a:blipFill"):
            for el in spPr.findall(qn(tag)): spPr.remove(el)
        g = etree.Element(qn("a:gradFill")); g.set("rotWithShape", "1"); lst = etree.SubElement(g, qn("a:gsLst"))
        n = len(colors)
        for i, c in enumerate(colors):
            gs = etree.SubElement(lst, qn("a:gs")); gs.set("pos", str(int(100000 * i / max(n - 1, 1))))
            sc = etree.SubElement(gs, qn("a:srgbClr")); sc.set("val", "%02X%02X%02X" % tuple(c))
            if alphas: etree.SubElement(sc, qn("a:alpha")).set("val", str(int(alphas[i] * 1000)))
        lin = etree.SubElement(g, qn("a:lin")); lin.set("ang", str(int(angle * 60000))); lin.set("scaled", "0")
        geom = spPr.find(qn("a:prstGeom"))
        if geom is None: geom = spPr.find(qn("a:custGeom"))
        geom.addnext(g)
        return sh

    def glow_fill(self, sh, color, alpha):
        spPr = sh._element.spPr
        for tag in ("a:solidFill", "a:gradFill", "a:noFill"):
            for el in spPr.findall(qn(tag)): spPr.remove(el)
        g = etree.Element(qn("a:gradFill")); g.set("rotWithShape", "1"); lst = etree.SubElement(g, qn("a:gsLst"))
        for pos, al in ((0, alpha), (100000, 0)):
            gs = etree.SubElement(lst, qn("a:gs")); gs.set("pos", str(pos)); sc = etree.SubElement(gs, qn("a:srgbClr")); sc.set("val", "%02X%02X%02X" % tuple(color))
            etree.SubElement(sc, qn("a:alpha")).set("val", str(int(al * 1000)))
        p = etree.SubElement(g, qn("a:path")); p.set("path", "circle"); fr = etree.SubElement(p, qn("a:fillToRect"))
        for k in "ltrb": fr.set(k, "50000")
        spPr.find(qn("a:prstGeom")).addnext(g)

    def soft_shadow(self, sh, blur=30, dist=8, alpha=14, color=(60, 90, 200)):
        spPr = sh._element.spPr
        for el in spPr.findall(qn("a:effectLst")): spPr.remove(el)
        ef = etree.SubElement(spPr, qn("a:effectLst")); o = etree.SubElement(ef, qn("a:outerShdw"))
        o.set("blurRad", str(int(Pt(blur)))); o.set("dist", str(int(Pt(dist)))); o.set("dir", "5400000"); o.set("algn", "t"); o.set("rotWithShape", "0")
        sc = etree.SubElement(o, qn("a:srgbClr")); sc.set("val", "%02X%02X%02X" % color); etree.SubElement(sc, qn("a:alpha")).set("val", str(alpha * 1000))

    def glass(self, sl, x, y, w, h, name="Card", radius=None):
        sh = self.rect(sl, x, y, w, h, (255, 255, 255), self.t["border"], MSO_SHAPE.ROUNDED_RECTANGLE, radius=radius, lw=1.25, name=name)
        self.gfill(sh, [(255, 255, 255), (255, 255, 255)], 45, [92, 58]); self.soft_shadow(sh)
        return sh

    def poly(self, sl, pts, fill=None, line=None, lw=1.0, closed=True, name=None):
        """Freeform polygon / polyline; pts in inches."""
        E = lambda v: int(Inches(v))
        fb = sl.shapes.build_freeform(E(pts[0][0]), E(pts[0][1]), scale=1.0)
        fb.add_line_segments([(E(a), E(b)) for a, b in pts[1:]], close=closed)
        sh = fb.convert_to_shape()
        if fill is None: sh.fill.background()
        else: sh.fill.solid(); sh.fill.fore_color.rgb = rgb(fill)
        if line is None: sh.line.fill.background()
        else: sh.line.color.rgb = rgb(line); sh.line.width = Pt(lw)
        sh.shadow.inherit = False
        if name: sh.name = name
        return sh

    def arrow_line(self, sl, pts, color, dashed=False, lw=2.25, name="Edge"):
        sh = self.poly(sl, pts, None, color, lw, closed=False, name=name)
        if dashed:
            from pptx.enum.dml import MSO_LINE
            sh.line.dash_style = MSO_LINE.DASH
        ln = sh.line._get_or_add_ln(); te = etree.SubElement(ln, qn("a:tailEnd")); te.set("type", "triangle"); te.set("w", "med"); te.set("len", "med")
        return sh

    # ---------- DAG ----------
    def dag(self, sl, nodes, edges, bx, by, bw, bh, nw, nh, fs=16):
        byid = {}
        for n in nodes:
            n = dict(n); n["_x"] = bx + n.get("x", 0) * (bw - nw); n["_y"] = by + n.get("y", .5) * (bh - nh); byid[n["id"]] = n
        anc = lambda n, s_: {"r": (n["_x"] + nw, n["_y"] + nh / 2), "l": (n["_x"], n["_y"] + nh / 2), "t": (n["_x"] + nw / 2, n["_y"]), "b": (n["_x"] + nw / 2, n["_y"] + nh)}[s_]
        for ed in edges:                       # edges first (drawn under nodes)
            a, b = byid[ed["from"]], byid[ed["to"]]; route = ed.get("route"); off = 0.32
            if route in ("above", "below"):
                s_ = t_ = "t" if route == "above" else "b"; (x1, y1), (x2, y2) = anc(a, s_), anc(b, t_); yo = y1 - off if route == "above" else y1 + off
                pts = [(x1, y1), (x1, yo), (x2, yo), (x2, y2)]; lab = ((x1 + x2) / 2, yo)
            elif ed.get("fs") and ed.get("ts"):
                s_, t_ = ed["fs"], ed["ts"]; (x1, y1), (x2, y2) = anc(a, s_), anc(b, t_)
                pts = [(x1, y1), (x1, y2), (x2, y2)] if (s_ in "tb" and t_ in "lr") else [(x1, y1), (x2, y1), (x2, y2)] if (s_ in "lr" and t_ in "tb") else [(x1, y1), (x2, y2)]
                lab = ((x1 + x2) / 2, (y1 + y2) / 2)
            else:
                dx, dy = b["_x"] - a["_x"], b["_y"] - a["_y"]
                if abs(dx) >= abs(dy) * 0.6 or abs(dx) > nw:
                    s_, t_ = ("r", "l") if dx >= 0 else ("l", "r"); (x1, y1), (x2, y2) = anc(a, s_), anc(b, t_); xm = (x1 + x2) / 2
                    pts = [(x1, y1), (x2, y2)] if abs(y1 - y2) < .02 else [(x1, y1), (xm, y1), (xm, y2), (x2, y2)]
                else:
                    s_, t_ = ("b", "t") if dy >= 0 else ("t", "b"); (x1, y1), (x2, y2) = anc(a, s_), anc(b, t_); ym = (y1 + y2) / 2
                    pts = [(x1, y1), (x2, y2)] if abs(x1 - x2) < .02 else [(x1, y1), (x1, ym), (x2, ym), (x2, y2)]
                lab = ((x1 + x2) / 2, (y1 + y2) / 2)
            dashed = ed.get("style") == "dashed"
            self.arrow_line(sl, pts, self.t["accent2"] if dashed else self.t["accent"], dashed, name="Edge")
            if ed.get("label"):
                lw_ = max(0.5, len(ed["label"]) * 0.16 + 0.3)
                chip = self.rect(sl, lab[0] - lw_ / 2, lab[1] - 0.15, lw_, 0.3, self.t["bg"], self.t["border"], MSO_SHAPE.ROUNDED_RECTANGLE, radius=99, name="EdgeLabel")
                self.text(sl, 0, 0, 0, 0, ed["label"], 11, self.t["muted"], shape=chip, align="c", anchor="m", fit=False)
        for n in byid.values():
            x, y = n["_x"], n["_y"]
            card = self.glass(sl, x, y, nw, nh, name="Node") if self.t["glass"] else self.card(sl, x, y, nw, nh)
            d = nh * 0.58
            bd = self.rect(sl, x + 0.16, y + (nh - d) / 2, d, d, self.t["accent"], shape=MSO_SHAPE.OVAL, name="NodeIcon")
            if self.t["glass"]: self.gfill(bd, None, 45)
            self.text(sl, 0, 0, 0, 0, n.get("icon", "◆"), max(12, int(d * 34)), self.t["on_accent"], True, font="Segoe UI Symbol", shape=bd, align="c", anchor="m", fit=False)
            tx = x + 0.16 + d + 0.1; tw = nw - (tx - x) - 0.08
            tb = sl.shapes.add_textbox(Inches(tx), Inches(y), Inches(tw), Inches(nh)); tf = tb.text_frame; tf.word_wrap = True; tf.vertical_anchor = MSO_ANCHOR.MIDDLE
            tf.margin_left = tf.margin_right = Inches(0.04); tb.name = "NodeText"
            lf = _fit.fit([n["label"]], tw - 0.1, nh * (0.55 if n.get("sub") else 0.8), fs, minimum=11)
            p = tf.paragraphs[0]; r = p.add_run(); r.text = n["label"]; r.font.size = Pt(lf); r.font.bold = True; r.font.name = self.t["font_body"]; r.font.color.rgb = rgb(self.t["fg"])
            if n.get("sub"):
                p2 = tf.add_paragraph(); r2 = p2.add_run(); r2.text = n["sub"]; r2.font.size = Pt(max(10, lf - 4)); r2.font.name = self.t["font_body"]; r2.font.color.rgb = rgb(self.t["muted"])

    # ---------- 3D cube (native freeform faces) ----------
    def cube(self, sl, ox, oy, w):
        k = w / 560.0; P = lambda x, y: (ox + x * k, oy + y * k)
        C = lambda *pts: [P(*p) for p in pts]
        sh = self.rect(sl, ox + 110 * k, oy + 530 * k, 340 * k, 60 * k, (60, 90, 200), shape=MSO_SHAPE.OVAL, name="CubeShadow"); self.glow_fill(sh, (60, 90, 200), 30)
        orbit = [(150, 260, 40, 170, 0), (410, 260, 520, 160, 1), (410, 380, 525, 470, 2), (150, 380, 45, 480, 1), (280, 140, 280, 40, 2)]
        cols = [self.t["accent"], self.t["accent2"], self.t["accent3"]]
        for x1, y1, x2, y2, ci in orbit:
            (a, b), (c, d) = P(x1, y1), P(x2, y2)
            from pptx.enum.dml import MSO_LINE
            ln = self.poly(sl, [(a, b), (c, d)], None, (150, 170, 230), 1.5, closed=False, name="Link"); ln.line.dash_style = MSO_LINE.DASH
            r = 20 * k; n = self.rect(sl, c - r, d - r, 2 * r, 2 * r, (255, 255, 255), (159, 179, 240), MSO_SHAPE.OVAL, lw=1.25, name="Orbit")
            r2 = 8 * k; self.rect(sl, c - r2, d - r2, 2 * r2, 2 * r2, cols[ci], shape=MSO_SHAPE.OVAL, name="OrbitDot")
        faces = [(C((280, 150), (410, 225), (280, 300), (150, 225)), [(31, 214, 160), (47, 123, 255)], 45),
                 (C((150, 225), (280, 300), (280, 455), (150, 380)), [(47, 123, 255), (124, 77, 255)], 70),
                 (C((410, 225), (280, 300), (280, 455), (410, 380)), [(124, 77, 255), (179, 140, 255)], 70)]
        for pts, cs, ang in faces:
            f = self.poly(sl, pts, cs[0], (255, 255, 255), 2.0, name="CubeFace"); self.gfill(f, cs, ang)
        core = self.poly(sl, C((280, 215), (340, 250), (280, 285), (220, 250)), (255, 255, 255), (255, 255, 255), 1.5, name="CubeCore"); self.gfill(core, [(255, 255, 255), (255, 255, 255)], 0, [45, 25])

    def hero(self, s):
        sl = self.new_slide(s, footer=False)
        lx, lw_ = MX, 3.9
        self.text(sl, lx, 1.35, lw_, 0.4, s.get("kicker", ""), 14, self.t["accent"], True, name="Kicker")
        self.text(sl, lx, 1.8, lw_, 1.9, (s.get("title", "")).split("\n"), 40, self.t["fg"], True, self.t["font_head"], name="Title", min_size=26, spacing=1.0)
        self.text(sl, lx, 3.75, lw_, 1.0, s.get("tagline", s.get("subtitle", "")), 17, self.t["muted"], name="Tagline")
        self.cube(sl, 4.95, 0.7, 3.5)
        if s.get("nodes"): self.dag(sl, s["nodes"], s.get("edges", []), 8.85, 1.2, 3.65, 3.7, 1.4, 0.74, 12)
        cons = s.get("concepts", [])[:3]
        if cons:
            gap = 0.3; cw = (W - 2 * MX - gap * (len(cons) - 1)) / len(cons)
            for i, c in enumerate(cons):
                x = MX + i * (cw + gap); y = 5.55; ch = 1.2
                self.glass(sl, x, y, cw, ch) if self.t["glass"] else self.card(sl, x, y, cw, ch)
                bd = self.rect(sl, x + 0.25, y + 0.28, 0.64, 0.64, self.t["accent"], shape=MSO_SHAPE.OVAL, name="ConceptIcon")
                if self.t["glass"]: self.gfill(bd, None, 45)
                self.text(sl, 0, 0, 0, 0, c.get("icon", "◆"), 18, self.t["on_accent"], True, font="Segoe UI Symbol", shape=bd, align="c", anchor="m", fit=False)
                self.text(sl, x + 1.05, y + 0.18, cw - 1.2, 0.45, c["name"], 20, self.t["fg"], True, name="Concept")
                self.text(sl, x + 1.05, y + 0.62, cw - 1.2, 0.5, c.get("desc", ""), 13, self.t["muted"])

    def workflow(self, s):
        sl = self.new_slide(s); y0 = self.title(sl, s, compact=True)
        has_take = bool(s.get("takeaway")); bh = 2.9
        self.dag(sl, s["nodes"], s.get("edges", []), MX, y0 + 0.05, W - 2 * MX, bh, 2.3, 0.82, 15)
        ly = y0 + 0.05 + bh + 0.55
        self.poly(sl, [(MX, ly + 0.15), (MX + 0.6, ly + 0.15)], None, self.t["accent"], 2.25, closed=False, name="LegendSolid")
        self.text(sl, MX + 0.7, ly, 3, 0.3, "顺序 Sequential", 12, self.t["muted"], fit=False)
        from pptx.enum.dml import MSO_LINE
        l2 = self.poly(sl, [(MX + 3.0, ly + 0.15), (MX + 3.6, ly + 0.15)], None, self.t["accent2"], 2.25, closed=False, name="LegendDashed"); l2.line.dash_style = MSO_LINE.DASH
        self.text(sl, MX + 3.7, ly, 5, 0.3, "条件 / 循环 Conditional · Loop", 12, self.t["muted"], fit=False)
        if has_take: self._takeaway(sl, s["takeaway"], ly + 0.55)

    # ---------- slide types ----------
    def cover(self, s):
        sl = self.new_slide(s, footer=False)
        self.rect(sl, W - 4.6, -1.6, 6.6, 6.6, self.t["accent"], shape=MSO_SHAPE.OVAL, name="Deco").fill.fore_color.brightness = 0
        deco = sl.shapes[-1]
        deco.fill.transparency = 0.0
        self._alpha(deco, 28)
        self.rect(sl, MX, 2.35, 1.2, 0.09, self.t["accent"])
        self.text(sl, MX, 2.55, 10.5, 2.0, s.get("title", self.meta.get("title", "")), 54, self.t["fg"], True, self.t["font_head"], anchor="t", name="Title", min_size=32)
        if s.get("subtitle"): self.text(sl, MX, 4.55, 9.5, 0.9, s["subtitle"], 22, self.t["muted"], name="Subtitle")
        meta = " · ".join(x for x in [self.meta.get("author"), self.meta.get("org"), self.meta.get("date")] if x)
        if meta: self.text(sl, MX, 6.2, 10, 0.4, meta, 14, self.t["muted"], name="Meta")

    def section(self, s):
        sl = self.new_slide(s)
        self.text(sl, MX, 1.6, 6, 2.6, s.get("number", ""), 150, self.t["accent"], True, self.t["font_head"], name="Number", fit=False)
        self.text(sl, MX, 4.1, W - 2 * MX, 1.2, s.get("title", ""), 44, self.t["fg"], True, self.t["font_head"], name="Title", min_size=28)
        if s.get("subtitle"): self.text(sl, MX, 5.3, 10, 0.8, s["subtitle"], 20, self.t["muted"])

    def agenda(self, s):
        sl = self.new_slide(s); y0 = self.title(sl, s, s.get("kicker", "Agenda"))
        items = s["items"]; cols = 2 if len(items) > 4 else 1
        per = -(-len(items) // cols); cw = (W - 2 * MX - 0.4 * (cols - 1)) / cols; rh = min(0.95, (H - y0 - 1.0) / per)
        for i, it in enumerate(items):
            c, r = divmod(i, per); x = MX + c * (cw + 0.4); y = y0 + r * (rh + 0.12)
            self.card(sl, x, y, cw, rh)
            self.text(sl, x + 0.15, y, 0.9, rh, "%02d" % (i + 1), 26, self.t["accent"], True, self.t["font_head"], anchor="m", fit=False)
            label = it["text"] if isinstance(it, dict) else it
            self.text(sl, x + 1.05, y, cw - 1.2, rh, label, 20, anchor="m")

    def bullets_slide(self, s):
        sl = self.new_slide(s); y0 = self.title(sl, s)
        self.bullets(sl, MX, y0, W - 2 * MX, H - y0 - 1.1, s["bullets"], 24)

    def two_col(self, s):
        sl = self.new_slide(s); y0 = self.title(sl, s); cw = (W - 2 * MX - 0.5) / 2; ch = H - y0 - 1.1
        for i, k in enumerate(("left", "right")):
            col = s[k]; x = MX + i * (cw + 0.5)
            self.card(sl, x, y0, cw, ch)
            self.text(sl, x + 0.3, y0 + 0.2, cw - 0.6, 0.6, col.get("heading", ""), 24, self.t["accent"], True, self.t["font_head"], name="Heading")
            self.bullets(sl, x + 0.3, y0 + 0.95, cw - 0.6, ch - 1.15, col.get("bullets", []), 20)

    def kpi(self, s):
        sl = self.new_slide(s); y0 = self.title(sl, s); items = s["items"]; n = len(items)
        gap = 0.35; cw = (W - 2 * MX - gap * (n - 1)) / n; ch = 2.9
        kfs = min(_fit.fit([str(i["value"])], (cw - 0.6) / 1.4, 1.1, 48, minimum=24) for i in items)   # one size for all tiles
        for i, it in enumerate(items):
            x = MX + i * (cw + gap); self.card(sl, x, y0 + 0.2, cw, ch)
            self.text(sl, x + 0.2, y0 + 0.4, cw - 0.4, 0.4, it["label"], 16, self.t["muted"])
            self.text(sl, x + 0.2, y0 + 0.95, cw - 0.4, 1.2, str(it["value"]), kfs, self.t["fg"], True, self.t["font_head"], anchor="m", name="KPI", min_size=24, fit=False)
            if it.get("delta"):
                bad = str(it["delta"]).strip().startswith(("▼", "-", "−")) and not it.get("good_down")
                self.text(sl, x + 0.2, y0 + 2.25, cw - 0.4, 0.5, it["delta"], 16, self.t["bad"] if bad else self.t["good"], True)
        if s.get("takeaway"): self._takeaway(sl, s["takeaway"], y0 + 3.4)

    def _takeaway(self, sl, txt, y):
        bar = self.rect(sl, MX, y, 0.08, 0.7, self.t["accent"])
        if self.t["glass"]: self.gfill(bar, None, 90)
        self.text(sl, MX + 0.25, y, W - 2 * MX - 0.3, 0.7, txt, 20, self.t["fg"], anchor="m", name="Takeaway")

    def chart(self, s):
        sl = self.new_slide(s); y0 = self.title(sl, s); c = s["chart"]
        cd = CategoryChartData(); cd.categories = c["categories"]
        for ser in c["series"]: cd.add_series(ser["name"], ser["values"])
        kind = {"bar": XL_CHART_TYPE.COLUMN_CLUSTERED, "hbar": XL_CHART_TYPE.BAR_CLUSTERED, "line": XL_CHART_TYPE.LINE_MARKERS,
                "pie": XL_CHART_TYPE.PIE, "stacked": XL_CHART_TYPE.COLUMN_STACKED}[c.get("kind", "bar")]
        has_take = bool(s.get("takeaway")); ch = H - y0 - (1.95 if has_take else 1.1)
        gf = sl.shapes.add_chart(kind, Inches(MX), Inches(y0), Inches(W - 2 * MX), Inches(ch), cd); gf.name = "Chart"
        ch_ = gf.chart; ch_.font.size = Pt(14); ch_.font.color.rgb = rgb(self.t["fg"]); ch_.font.name = self.t["font_body"]
        ch_.has_legend = len(c["series"]) > 1 or c.get("kind") == "pie"
        if ch_.has_legend: ch_.legend.position = XL_LEGEND_POSITION.BOTTOM; ch_.legend.include_in_layout = False; ch_.legend.font.color.rgb = rgb(self.t["fg"])
        if c.get("title"): ch_.has_title = True; ch_.chart_title.text_frame.text = c["title"]; ch_.chart_title.text_frame.paragraphs[0].runs[0].font.size = Pt(16); ch_.chart_title.text_frame.paragraphs[0].runs[0].font.color.rgb = rgb(self.t["muted"])
        else: ch_.has_title = False
        plot = ch_.plots[0]
        if c.get("kind") == "pie":
            plot.has_data_labels = True; plot.data_labels.font.size = Pt(14); plot.data_labels.font.color.rgb = rgb(self.t["on_accent"]); plot.data_labels.number_format = '0%' if c.get("percent") else 'General'; plot.data_labels.number_format_is_linked = False
            for i, pt in enumerate(plot.series[0].points):
                pt.format.fill.solid(); pt.format.fill.fore_color.rgb = rgb(self.palette[i % len(self.palette)])
        else:
            for i, ser in enumerate(plot.series):
                col = rgb(self.palette[i % len(self.palette)])
                if c.get("kind") == "line": ser.format.line.color.rgb = col; ser.format.line.width = Pt(3); ser.smooth = False; ser.marker.format.fill.solid(); ser.marker.format.fill.fore_color.rgb = col
                else: ser.format.fill.solid(); ser.format.fill.fore_color.rgb = col
            if c.get("data_labels", True) and c.get("kind") != "line":
                plot.has_data_labels = True; plot.data_labels.font.size = Pt(13); plot.data_labels.font.color.rgb = rgb(self.t["fg"])
            va, ca = ch_.value_axis, ch_.category_axis
            va.major_gridlines.format.line.color.rgb = rgb(self.t["border"]); va.format.line.fill.background()
            va.tick_labels.font.color.rgb = rgb(self.t["muted"]); ca.tick_labels.font.color.rgb = rgb(self.t["muted"]); ca.format.line.color.rgb = rgb(self.t["border"])
            if c.get("unit"): va.has_title = True; va.axis_title.text_frame.text = c["unit"]; va.axis_title.text_frame.paragraphs[0].runs[0].font.size = Pt(12); va.axis_title.text_frame.paragraphs[0].runs[0].font.color.rgb = rgb(self.t["muted"])
        if has_take: self._takeaway(sl, s["takeaway"], H - 1.75)

    def table(self, s):
        sl = self.new_slide(s); y0 = self.title(sl, s); cols, rows = s["columns"], s["rows"]
        rh = min(0.62, (H - y0 - 1.3) / (len(rows) + 1)); w = W - 2 * MX
        gf = sl.shapes.add_table(len(rows) + 1, len(cols), Inches(MX), Inches(y0), Inches(w), Inches(rh * (len(rows) + 1))); gf.name = "Table"
        tbl = gf.table; tblPr = tbl._tbl.tblPr; tblPr.set("bandRow", "0"); tblPr.set("firstRow", "0")
        sid = tblPr.find(qn("a:tableStyleId"))
        if sid is not None: sid.text = "{2D5ABB26-0587-4C30-8999-92F81FD0307C}"  # "No Style, No Grid"
        fs = min(_fit.fit([str(c)], w / len(cols) - 0.35, rh - 0.08, 18, minimum=11) for r_ in [cols] + rows for c in r_)
        num = s.get("numeric_cols", [i for i in range(len(cols)) if all(str(r[i]).replace(",", "").replace("%", "").replace("+", "").replace("-", "").replace("$", "").replace(".", "").replace("M", "").replace("k", "").strip().isdigit() for r in rows)])
        for ri in range(len(rows) + 1):
            tbl.rows[ri].height = Inches(rh)
            for ci in range(len(cols)):
                cell = tbl.cell(ri, ci); head = ri == 0
                cell.fill.solid(); cell.fill.fore_color.rgb = rgb(self.t["accent"] if head else (self.t["card"] if ri % 2 else self.t["bg"]))
                cell.vertical_anchor = MSO_ANCHOR.MIDDLE; cell.margin_left = cell.margin_right = Inches(0.15)
                tf = cell.text_frame; tf.word_wrap = True; p = tf.paragraphs[0]; r = p.add_run(); r.text = str(cols[ci] if head else rows[ri - 1][ci])
                r.font.size = Pt(fs); r.font.bold = head; r.font.name = self.t["font_body"]; r.font.color.rgb = rgb(self.t["on_accent"] if head else self.t["fg"])
                p.alignment = PP_ALIGN.RIGHT if ci in num else PP_ALIGN.LEFT
        if s.get("takeaway"): self._takeaway(sl, s["takeaway"], H - 1.75)

    def timeline(self, s):
        sl = self.new_slide(s); y0 = self.title(sl, s); ev = s["events"]; n = len(ev); cw = (W - 2 * MX) / n; ly = y0 + 0.9
        tl_ = self.rect(sl, MX, ly, W - 2 * MX, 0.06, self.t["accent"], name="Line")
        if self.t["glass"]: self.gfill(tl_)
        for i, e in enumerate(ev):
            x = MX + i * cw
            self.rect(sl, x, ly - 0.14, 0.34, 0.34, self.t["bg"], self.t["accent"], MSO_SHAPE.OVAL, lw=3.5)
            self.text(sl, x - 0.05, ly - 0.75, cw - 0.1, 0.5, e["when"], 24, self.t["accent"], True, self.t["font_head"])
            self.text(sl, x - 0.05, ly + 0.4, cw - 0.2, 0.6, e["title"], 18, bold=True)
            self.text(sl, x - 0.05, ly + 1.0, cw - 0.2, 2.2, e.get("text", ""), 15, self.t["muted"])

    def process(self, s):
        sl = self.new_slide(s); y0 = self.title(sl, s); st = s["steps"]; n = len(st); gap = 0.08; cw = (W - 2 * MX - gap * (n - 1)) / n
        for i, e in enumerate(st):
            x = MX + i * (cw + gap)
            sh = self.rect(sl, x, y0 + 0.3, cw, 1.15, self.t["accent"] if i % 2 == 0 else self.t["accent2"], shape=MSO_SHAPE.PENTAGON, name="Step")
            if self.t["glass"]: self.gfill(sh, [self.t["accent"], self.t["accent2"]] if i % 2 == 0 else [self.t["accent2"], self.t["accent3"]], 0)
            self.text(sl, 0, 0, 0, 0, "%d  %s" % (i + 1, e["title"]), 20, self.t["on_accent"], True, shape=sh, anchor="m")
            sh.text_frame.margin_right = Inches(0.35)
            self.text(sl, x, y0 + 1.7, cw - 0.15, 2.8, e.get("text", ""), 16, self.t["muted"])

    def comparison(self, s):
        sl = self.new_slide(s); y0 = self.title(sl, s); cw = (W - 2 * MX - 1.0) / 2; ch = H - y0 - 1.2
        for i, k in enumerate(("a", "b")):
            col = s[k]; x = MX + i * (cw + 1.0); self.card(sl, x, y0, cw, ch)
            self.text(sl, x + 0.3, y0 + 0.2, cw - 0.6, 0.7, col["name"], 28, self.t["accent"] if i == 0 else self.t["accent2"], True, self.t["font_head"], name="Heading")
            if col.get("tag"): self.text(sl, x + 0.3, y0 + 0.9, cw - 0.6, 0.4, col["tag"], 15, self.t["muted"])
            self.bullets(sl, x + 0.3, y0 + 1.4, cw - 0.6, ch - 1.6, col["points"], 20)
        v = self.rect(sl, MX + cw + 0.12, y0 + ch / 2 - 0.38, 0.76, 0.76, self.t["accent"], shape=MSO_SHAPE.OVAL, name="VS")
        if self.t["glass"]: self.gfill(v, None, 45)
        self.text(sl, 0, 0, 0, 0, "VS", 18, self.t["on_accent"], True, shape=v, align="c", anchor="m", fit=False)

    def layers(self, s):
        sl = self.new_slide(s); y0 = self.title(sl, s); L = s["layers"]; n = len(L); avail = H - y0 - 1.15; gap = 0.28
        lh = (avail - gap * (n - 1)) / n; lw = 2.3
        for i, layer in enumerate(L):
            y = y0 + i * (lh + gap)
            lab = self.rect(sl, MX, y, lw, lh, self.palette[i % 2], shape=MSO_SHAPE.ROUNDED_RECTANGLE, name="LayerLabel")
            if self.t["glass"]: self.gfill(lab, None, 20)
            self.text(sl, 0, 0, 0, 0, layer["name"], 18, self.t["on_accent"], True, shape=lab, align="c", anchor="m")
            items = layer["items"]; k = len(items); iw = (W - 2 * MX - lw - 0.25 - 0.18 * (k - 1)) / k
            for j, it in enumerate(items):
                x = MX + lw + 0.25 + j * (iw + 0.18)
                b = self.rect(sl, x, y, iw, lh, self.t["card"], self.t["border"], MSO_SHAPE.ROUNDED_RECTANGLE, name="Component")
                self.text(sl, 0, 0, 0, 0, it, 16, shape=b, align="c", anchor="m")
            if i < n - 1:
                a = self.rect(sl, W / 2 - 0.15, y + lh + 0.02, 0.3, gap - 0.04, self.t["muted"], shape=MSO_SHAPE.DOWN_ARROW, name="Flow")

    def code(self, s):
        sl = self.new_slide(s); y0 = self.title(sl, s); bh = H - y0 - (1.7 if s.get("caption") else 1.15)
        box = self.rect(sl, MX, y0, W - 2 * MX, bh, (11, 16, 32), self.t["border"], MSO_SHAPE.ROUNDED_RECTANGLE, radius=14, name="CodeBox")
        for k, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
            self.rect(sl, MX + 0.25 + k * 0.28, y0 + 0.2, 0.17, 0.17, c, shape=MSO_SHAPE.OVAL)
        if s.get("language"): self.text(sl, W - MX - 2.5, y0 + 0.1, 2.3, 0.35, s["language"], 12, (154, 164, 191), align="r", fit=False)
        lines = s["code"].rstrip("\n").split("\n")
        self.text(sl, MX + 0.2, y0 + 0.6, W - 2 * MX - 0.4, bh - 0.75, lines, 18, (230, 237, 247), font=self.t["font_mono"], name="Code", spacing=1.15, min_size=10)
        if s.get("caption"): self._takeaway(sl, s["caption"], H - 1.65)

    def closing(self, s):
        sl = self.new_slide(s, footer=False)
        self.text(sl, MX, 2.3, W - 2 * MX, 1.6, s.get("title", "Thank you"), 72, self.t["accent"], True, self.t["font_head"], align="c", anchor="m", name="Title", min_size=36)
        if s.get("subtitle"): self.text(sl, MX, 3.9, W - 2 * MX, 0.8, s["subtitle"], 22, self.t["muted"], align="c")
        c = s.get("contact", [])
        if c: self.text(sl, MX, 5.2, W - 2 * MX, 0.6, "   ·   ".join(c), 18, self.t["fg"], align="c", name="Contact")

    @staticmethod
    def _alpha(shape, pct):
        sf = shape.fill._xPr.find(qn("a:solidFill")); clr = sf[0]
        a = etree.SubElement(clr, qn("a:alpha")); a.set("val", str(int(pct * 1000)))

    HANDLERS = {"cover": "cover", "section": "section", "agenda": "agenda", "bullets": "bullets_slide", "two-col": "two_col", "kpi": "kpi",
                "chart": "chart", "table": "table", "timeline": "timeline", "process": "process", "comparison": "comparison",
                "layers": "layers", "code": "code", "closing": "closing", "hero": "hero", "workflow": "workflow"}

    def build(self):
        for i, s in enumerate(self.o["slides"], 1):
            h = self.HANDLERS.get(s.get("type"))
            if not h: raise SystemExit("slide %d: unknown type %r (valid: %s)" % (i, s.get("type"), ", ".join(self.HANDLERS)))
            getattr(self, h)(s)
        cp = self.p.core_properties; cp.title = self.meta.get("title", ""); cp.author = self.meta.get("author", ""); cp.subject = self.meta.get("subtitle", "")
        return self.p


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("outline"); ap.add_argument("out"); ap.add_argument("--theme")
    a = ap.parse_args(); o = json.load(open(a.outline, encoding="utf-8"))
    d = Deck(o, a.theme or o.get("meta", {}).get("theme", "modern-tech")); d.build().save(a.out)
    print("wrote %s (%d slides, theme=%s)" % (a.out, d.n, d.t["name"]))


if __name__ == "__main__":
    main()
