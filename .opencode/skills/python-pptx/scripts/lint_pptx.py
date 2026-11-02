#!/usr/bin/env python3
"""Lint any .pptx (ours, ppt-master's, or hand-made) for common delivery problems.

  python3 lint_pptx.py deck.pptx [--render]   # exit 1 if any ERROR

ERROR: shape off-slide, text clearly overflowing its box, font < 10pt, slide with no visible text.
WARN : missing speaker notes, no title shape, > 3 font families, text near-overflow, very long slide text.
--render: convert to PDF via LibreOffice and PNGs via pdftoppm into <deck>_render/ for visual review.
"""
import argparse, os, shutil, subprocess, sys
from pptx import Presentation
from pptx.util import Emu

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _fit


def inches(v): return (v or 0) / 914400.0


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("pptx"); ap.add_argument("--render", action="store_true")
    a = ap.parse_args(); prs = Presentation(a.pptx)
    SW, SH = inches(prs.slide_width), inches(prs.slide_height)
    errs, warns, fonts = [], [], set()
    for i, sl in enumerate(prs.slides, 1):
        words, has_title = 0, False
        for sh in sl.shapes:
            nm = sh.name or sh.shape_type
            if sh.left is not None and sh.width is not None:
                l, t, r, b = inches(sh.left), inches(sh.top), inches(sh.left + sh.width), inches(sh.top + sh.height)
                big_deco = sh.name in ("Deco",)
                if not big_deco and (l < -0.05 or t < -0.05 or r > SW + 0.05 or b > SH + 0.05):
                    errs.append("slide %d: shape %r off-slide (%.1f,%.1f)-(%.1f,%.1f)" % (i, nm, l, t, r, b))
            if sh.is_placeholder and sh.placeholder_format.type is not None and "TITLE" in str(sh.placeholder_format.type): has_title = True
            if sh.name in ("Title",) : has_title = True
            if not sh.has_text_frame: continue
            tf = sh.text_frame; paras = []; sizes = []
            for p in tf.paragraphs:
                txt = "".join(r.text for r in p.runs)
                paras.append(txt); words += len(txt.split())
                for r in p.runs:
                    if r.font.name: fonts.add(r.font.name)
                    if r.font.size: sizes.append(r.font.size.pt)
            if not any(paras): continue
            pt = max(sizes) if sizes else 18
            if sizes and min(sizes) < 10: errs.append("slide %d: %r font %.0fpt < 10pt" % (i, nm, min(sizes)))
            ml, mr = inches(tf.margin_left if tf.margin_left is not None else 91440), inches(tf.margin_right if tf.margin_right is not None else 91440)
            w, h = inches(sh.width) - ml - mr - 0.04, inches(sh.height)
            if w > 0.3 and h > 0.2 and sh.shape_type is not None:
                mono = any((r.font.name or "").lower() in ("consolas", "courier new") for p in tf.paragraphs for r in p.runs)
                need = _fit.height([p for p in paras], min(pt, sum(sizes) / len(sizes)) if sizes else pt, w, 1.15, 0, mono)
                if need > h * 1.25: errs.append("slide %d: text overflows %r \"%s\" (needs %.1fin, box %.1fin)" % (i, nm, " / ".join(paras)[:28], need, h))
                elif need > h * 1.05: warns.append("slide %d: text tight in %r \"%s\" (%.1f/%.1fin)" % (i, nm, " / ".join(paras)[:28], need, h))
        if words == 0 and not any(s.shape_type == 3 or getattr(s, "has_chart", False) for s in sl.shapes) and not any(getattr(s, "has_table", False) for s in sl.shapes):
            errs.append("slide %d: no visible text" % i)
        if words > 140: warns.append("slide %d: %d words — consider splitting" % (i, words))
        if not has_title: warns.append("slide %d: no title shape (hurts accessibility/outline view)" % i)
        if not (sl.has_notes_slide and sl.notes_slide.notes_text_frame.text.strip()): warns.append("slide %d: no speaker notes" % i)
    if len(fonts) > 3: warns.append("%d font families used: %s" % (len(fonts), ", ".join(sorted(fonts))))
    print("slides: %d   fonts: %s" % (len(prs.slides), ", ".join(sorted(fonts)) or "-"))
    for e in errs: print("ERROR", e)
    for w_ in warns: print("WARN ", w_)
    print("result: %d error(s), %d warning(s)" % (len(errs), len(warns)))
    if a.render:
        out = os.path.splitext(a.pptx)[0] + "_render"; os.makedirs(out, exist_ok=True)
        if not shutil.which("soffice"): print("render skipped: soffice not installed")
        else:
            subprocess.run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", out, a.pptx], capture_output=True, timeout=300)
            pdf = os.path.join(out, os.path.basename(os.path.splitext(a.pptx)[0]) + ".pdf")
            if os.path.exists(pdf) and shutil.which("pdftoppm"):
                subprocess.run(["pdftoppm", "-r", "60", "-png", pdf, os.path.join(out, "slide")]); print("rendered ->", out)
            else: print("render: pdf/pdftoppm unavailable; pdf at", pdf)
    sys.exit(1 if errs else 0)


if __name__ == "__main__":
    main()
