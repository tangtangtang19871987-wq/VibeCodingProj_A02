#!/usr/bin/env python3
"""Assemble an HTML PPT Studio deck from layout templates.

Examples
  python3 scripts/new_deck.py --out my-deck/index.html --theme aurora --title "Q4 Review" \
      --layouts cover,agenda,bullets,kpi-row,closing
  python3 scripts/new_deck.py --out demo.html --all --inline          # single self-contained file
  python3 scripts/new_deck.py --list                                   # show layouts, themes, animations
  python3 scripts/new_deck.py --out d.html --slides-file slides.html   # your own <section> markup

Without --inline the deck links to ../assets via a relative path (assets are NOT copied).
"""
import argparse, json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
A = os.path.join(ROOT, "assets")


def load_layouts():
    return json.load(open(os.path.join(ROOT, "templates/layouts/layouts.json")))


def load_themes():
    return json.load(open(os.path.join(A, "themes/themes.json")))


def animations():
    css = open(os.path.join(A, "animations.css")).read()
    return sorted(set(re.findall(r'data-anim="([a-z0-9-]+)"\]\{animation-name', css)) | {"count-up"})


def read(p):
    return open(p, encoding="utf-8").read()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out"); ap.add_argument("--title", default="Untitled Deck")
    ap.add_argument("--theme", default="modern-tech"); ap.add_argument("--layouts", default="")
    ap.add_argument("--all", action="store_true", help="include all 34 layouts")
    ap.add_argument("--slides-file", help="file with custom <section class='slide ...'> markup (appended after --layouts)")
    ap.add_argument("--transition", default="fade", choices=["fade", "slide", "zoom", "none"])
    ap.add_argument("--lang", default="en"); ap.add_argument("--inline", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--extra-css", help="extra CSS file appended after the built-in styles (custom layouts)")
    a = ap.parse_args()

    layouts, themes = load_layouts(), load_themes()
    names = [l["name"] for l in layouts]
    if a.list:
        print("LAYOUTS (%d):" % len(layouts)); [print("  %-15s %s" % (l["name"], l["description"])) for l in layouts]
        print("\nTHEMES (%d): %s" % (len(themes), ", ".join(t["name"] for t in themes)))
        an = animations(); print("\nANIMATIONS (%d): %s" % (len(an), ", ".join(an))); return
    if not a.out: ap.error("--out is required")
    if a.theme not in [t["name"] for t in themes]: sys.exit("unknown theme %r; use --list" % a.theme)
    pick = names if a.all else [x.strip() for x in a.layouts.split(",") if x.strip()]
    bad = [p for p in pick if p not in names]
    if bad: sys.exit("unknown layout(s): %s; use --list" % ", ".join(bad))
    if not pick and not a.slides_file: sys.exit("give --layouts, --all or --slides-file")

    byname = {l["name"]: l["file"] for l in layouts}
    body = "".join(read(os.path.join(ROOT, "templates/layouts", byname[p])) for p in pick)
    if a.slides_file: body += read(a.slides_file)

    css_files = ["base.css", "layouts.css", "animations.css", "themes.all.css"]
    out_dir = os.path.dirname(os.path.abspath(a.out)) or "."
    if a.inline:
        head = "<style>\n" + "\n".join(read(os.path.join(A, f)) for f in css_files) + "\n</style>"
        tail = "<script>\n" + read(os.path.join(A, "runtime.js")) + "\n</script>"
    else:
        rel = os.path.relpath(A, out_dir).replace(os.sep, "/")
        head = "\n".join('<link rel="stylesheet" href="%s/%s">' % (rel, f) for f in css_files)
        tail = '<script src="%s/runtime.js"></script>' % rel
    if a.extra_css:
        head += "\n<style>\n" + read(a.extra_css) + "\n</style>"
    html = f"""<!doctype html>
<html lang="{a.lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{a.title}</title>
{head}
</head>
<body data-theme="{a.theme}" data-themes="{",".join(t["name"] for t in themes)}">
<main class="deck" data-transition="{a.transition}">
{body}</main>
{tail}
</body>
</html>
"""
    os.makedirs(out_dir, exist_ok=True)
    open(a.out, "w", encoding="utf-8").write(html)
    print("wrote %s  (%d slides, theme=%s, %s)" % (a.out, body.count("<section class=\"slide"), a.theme, "inline" if a.inline else "linked"))


if __name__ == "__main__":
    main()
