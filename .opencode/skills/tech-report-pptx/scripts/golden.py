#!/usr/bin/env python3
"""Golden references = images the USER said they like. They are locked in as regression tests so the look can never drift silently.

  golden.py list
  golden.py add IMAGE --id NAME --slides 2,3,4 [--example diagrams.example.json] [--crop x0,y0,x1,y1] [--note "user said: ..."]
  golden.py check [--id NAME]          # needs LibreOffice + pdftoppm + Pillow; exit 1 if any golden drifts

How it works: a colour signature = histogram of hues over the saturated pixels (borders, icons, titles, edges). The current build of the
example outline is rendered, the chosen slides are averaged, and the L1 distance to the golden image's signature must stay <= max_distance.
Signature distance is a TRIPWIRE, not taste: always also LOOK at the images (deck.py compare) before concluding anything."""
import argparse, colorsys, glob, json, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", "..", "..", ".."))
GOLD = os.path.join(ROOT, "evals", "golden"); MAN = os.path.join(GOLD, "manifest.json"); EX = os.path.normpath(os.path.join(HERE, "..", "examples"))
PY = sys.executable


def signature(img, bins=12):
    from PIL import Image
    im = (Image.open(img) if isinstance(img, str) else img).convert("RGB"); w, h = im.size; px = im.load(); hist = [0] * bins; n = 0
    for y in range(0, h, 2):
        for x in range(0, w, 2):
            hh, s, v = colorsys.rgb_to_hsv(*[q / 255 for q in px[x, y]])
            if s >= .45 and v >= .45: hist[int(hh * bins) % bins] += 1; n += 1
    return [c / max(n, 1) for c in hist]


def distance(a, b): return sum(abs(x - y) for x, y in zip(a, b)) / 2


def load(): return json.load(open(MAN, encoding="utf-8")) if os.path.exists(MAN) else []
def save(m): json.dump(m, open(MAN, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def render_signature(example, slides, theme=None):
    """Build the example with the current code, render it, return the averaged signature of the given slides."""
    d = tempfile.mkdtemp(prefix="golden-"); deck = os.path.join(HERE, "deck.py")
    try:
        args = [PY, deck, "build", os.path.join(EX, example), "--out", d, "--no-html"] + (["--theme", theme] if theme else [])
        r = subprocess.run(args, capture_output=True, text=True)
        if not os.path.exists(os.path.join(d, "deck.pptx")): raise SystemExit("build failed:\n" + r.stdout[-800:] + r.stderr[-800:])
        subprocess.run([PY, deck, "preview", os.path.join(d, "deck.pptx"), "--dpi", "100"], capture_output=True, text=True)
        tot = [0] * 12
        for i in slides:
            p = os.path.join(d, "preview", "slide-%d.png" % i)
            if not os.path.exists(p): raise SystemExit("slide %d was not rendered (is LibreOffice installed?)" % i)
            for k, v in enumerate(signature(p)): tot[k] += v / len(slides)
        return tot
    finally: shutil.rmtree(d, ignore_errors=True)


def cmd_list(a):
    m = load()
    if not m: print("no goldens yet"); return
    for g in m: print("%-24s %-28s slides %-10s max %.2f  %s" % (g["id"], g["file"], ",".join(map(str, g["slides"])), g["max_distance"], g.get("note", "")))


def cmd_add(a):
    from PIL import Image
    im = Image.open(a.image).convert("RGB")
    if a.crop: im = im.crop(tuple(int(v) for v in a.crop.split(",")))
    os.makedirs(GOLD, exist_ok=True); fn = a.id + ".png"; im.save(os.path.join(GOLD, fn))
    slides = [int(s) for s in a.slides.split(",")]
    cur = distance(signature(im), render_signature(a.example, slides))
    mx = round(max(0.20, cur + 0.05), 2)
    m = [g for g in load() if g["id"] != a.id] + [{"id": a.id, "file": fn, "example": a.example, "slides": slides, "max_distance": mx, "note": a.note or ""}]
    save(m); print("golden '%s' saved (current distance %.3f, threshold %.2f). Run `golden.py check` after every style change." % (a.id, cur, mx))
    if cur > 0.20: print("WARNING: the current output is already far from this golden (%.2f). LOOK at both (deck.py compare) and fix the style first." % cur)


def cmd_check(a):
    missing = [t for t in ("soffice", "pdftoppm") if not shutil.which(t)]
    if missing: print("SKIP golden check (missing %s)" % ", ".join(missing)); return
    bad = 0
    for g in load():
        if a.id and g["id"] != a.id: continue
        d = distance(signature(os.path.join(GOLD, g["file"])), render_signature(g["example"], g["slides"]))
        ok = d <= g["max_distance"]; bad += not ok
        print("%s golden %-24s distance %.3f (max %.2f)  %s" % ("PASS" if ok else "FAIL", g["id"], d, g["max_distance"], g.get("note", "")))
    sys.exit(1 if bad else 0)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter); sub = ap.add_subparsers(dest="c", required=True)
    s = sub.add_parser("list"); s.set_defaults(f=cmd_list)
    s = sub.add_parser("add"); s.add_argument("image"); s.add_argument("--id", required=True); s.add_argument("--slides", required=True); s.add_argument("--example", default="diagrams.example.json")
    s.add_argument("--crop"); s.add_argument("--note"); s.set_defaults(f=cmd_add)
    s = sub.add_parser("check"); s.add_argument("--id"); s.set_defaults(f=cmd_check)
    a = ap.parse_args(); a.f(a)


if __name__ == "__main__": main()
