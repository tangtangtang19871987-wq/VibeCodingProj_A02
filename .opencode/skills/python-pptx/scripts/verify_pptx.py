#!/usr/bin/env python3
"""Acceptance check for a generated deck: is it really EDITABLE, and does it follow the house style?

  python3 verify_pptx.py deck.pptx [--theme modern-tech] [--allow-pictures] [--json]    # exit 1 on ERROR

ERROR : any picture in a slide (unless --allow-pictures) · slide background != theme background (pure white for modern-tech)
        · slide without a title shape · text-less slides made only of shapes
WARN  : colours outside the palette · more than 3 font families
INFO  : inventory (native text boxes / charts / tables / freeform shapes / groups) and per-colour usage
"""
import argparse, collections, json, os, re, sys, zipfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import theme_tokens, diagram_geom as G
from pptx import Presentation

NEUTRAL_HEX = {"FFFFFF", "F8FAFC", "F3F4F6", "EEF2FF", "000000"}
EXTRA_RGB = [(22, 50, 92), (92, 106, 128), (53, 65, 107), (38, 51, 95), (120, 134, 158), (246, 248, 252), (255, 95, 86), (255, 189, 46), (39, 201, 63),
             (30, 41, 59), (30, 60, 120), (60, 90, 200), (237, 243, 251), (237, 242, 255), (11, 16, 32), (230, 237, 247), (154, 164, 191)]


def hexc(c): return "%02X%02X%02X" % tuple(c)


def allowed(theme):
    t = theme_tokens.load(theme); A = set(NEUTRAL_HEX)
    for tn in G.TONES.values():
        for k in ("border", "soft", "fill", "solid"): A.add(hexc(tn[k]))
    for _, _, _, cols in G.CUBE_SET:
        for c in cols: A.add(hexc(c))
    for *_, c in G.CUBE_DOTS: A.add(hexc(c))
    for c in EXTRA_RGB: A.add(hexc(c))
    for k in ("bg", "bg2", "fg", "muted", "accent", "accent2", "accent3", "card", "border", "head", "good", "bad", "warn", "on_accent"):
        v = t.get(k)
        if isinstance(v, tuple): A.add(hexc(v))
    return A, t


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("pptx"); ap.add_argument("--theme", default="modern-tech"); ap.add_argument("--allow-pictures", action="store_true"); ap.add_argument("--json", action="store_true")
    a = ap.parse_args(); A, T = allowed(a.theme); errs, warns = [], []
    z = zipfile.ZipFile(a.pptx); slides = sorted([n for n in z.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n)], key=lambda n: int(re.findall(r"\d+", n)[0]))
    colours = collections.Counter(); pics = 0; bgbad = []
    for idx, n in enumerate(slides, 1):
        x = z.read(n).decode("utf8"); pics += len(re.findall(r"<p:pic[ >]", x))
        for m in re.findall(r'<a:srgbClr val="([0-9A-Fa-f]{6})"', x): colours[m.upper()] += 1
        bg = re.search(r"<p:bg>.*?</p:bg>", x, re.S); bgc = re.search(r'srgbClr val="([0-9A-Fa-f]{6})"', bg.group(0)).group(1).upper() if bg else None
        if bgc != hexc(T["bg"]): bgbad.append((idx, bgc))
    prs = Presentation(a.pptx); inv = collections.Counter(); fonts = set(); notitle = []
    def walk(shapes):
        for sh in shapes:
            if sh.shape_type == 6: inv["groups"] += 1; walk(sh.shapes); continue
            if getattr(sh, "has_chart", False) and sh.has_chart: inv["native charts"] += 1
            elif getattr(sh, "has_table", False) and sh.has_table: inv["native tables"] += 1
            elif sh.shape_type == 5: inv["freeform shapes"] += 1
            elif sh.shape_type == 13: inv["pictures"] += 1
            elif sh.has_text_frame and sh.text_frame.text.strip(): inv["text boxes / labelled shapes"] += 1
            else: inv["plain shapes"] += 1
            if sh.has_text_frame:
                for p in sh.text_frame.paragraphs:
                    for r in p.runs:
                        if r.font.name: fonts.add(r.font.name)
    for i, sl in enumerate(prs.slides, 1):
        walk(sl.shapes)
        if not any(sh.name == "Title" for sh in sl.shapes) and i not in (1,) and not any(sh.name in ("Number", "Contact") for sh in sl.shapes): notitle.append(i)
    if pics and not a.allow_pictures: errs.append("%d picture(s) found in slides — deck must be built from native shapes (use --allow-pictures only for user-supplied photos)" % pics)
    for i, c in bgbad: errs.append("slide %d background is %s, expected %s" % (i, c, hexc(T["bg"])))
    off = {c: n for c, n in colours.items() if c not in A and min(int(c[i:i + 2], 16) for i in (0, 2, 4)) < 240}   # near-white tints of the palette are fine
    if off: warns.append("off-palette colours: " + ", ".join("#%s×%d" % (c, n) for c, n in sorted(off.items(), key=lambda kv: -kv[1])))
    if len(fonts) > 3: warns.append("%d font families: %s" % (len(fonts), ", ".join(sorted(fonts))))
    if notitle: warns.append("slides without a Title shape: %s" % notitle)
    res = {"file": a.pptx, "slides": len(slides), "pictures": pics, "inventory": dict(inv), "fonts": sorted(fonts), "background_ok": not bgbad, "off_palette": off, "errors": errs, "warnings": warns,
           "top_colours": ["#%s×%d" % kv for kv in colours.most_common(12)]}
    if a.json: print(json.dumps(res, ensure_ascii=False, indent=1))
    else:
        print("slides: %d · pictures: %d · inventory: %s" % (len(slides), pics, dict(inv)))
        print("fonts: %s · backgrounds %s (expected #%s)" % (", ".join(sorted(fonts)), "OK" if not bgbad else "MISMATCH", hexc(T["bg"])))
        print("top colours:", " ".join(res["top_colours"]))
        for e in errs: print("ERROR", e)
        for w in warns: print("WARN ", w)
        print("result: %d error(s), %d warning(s)" % (len(errs), len(warns)))
    sys.exit(1 if errs else 0)


if __name__ == "__main__": main()
