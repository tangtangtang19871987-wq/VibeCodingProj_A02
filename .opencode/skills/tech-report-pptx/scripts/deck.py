#!/usr/bin/env python3
"""deck — the single CLI behind the agent's tools. Every subcommand prints plain text and exits non-zero on failure.

  deck.py catalog [types|palette|icons|themes|diagram|all]      what the agent may use (self-documenting)
  deck.py new SLUG [--title T] [--theme NAME] [--lang zh]         create output/SLUG/outline.json skeleton
  deck.py check OUTLINE                                           structure + diagram geometry + colour rules
  deck.py build OUTLINE [--out DIR] [--no-html] [--no-pptx]       check -> draft.html + deck.pptx -> verify -> lint  (JSON summary at the end)
  deck.py preview FILE [--pages 1,3] [--dpi 70]                   render slides to PNG (+ contact sheet) for visual review
  deck.py edit OUTLINE OP ...                                     structured outline edits (see below)
  deck.py verify DECK.pptx                                        editable + house-style acceptance check
  deck.py lint DECK.pptx [--render]                               overflow / off-slide / notes / fonts
  deck.py colors IMAGE [--crop x0,y0,x1,y1] [--top 12]            MEASURE the colours in a reference image and map them to the palette (use this instead of guessing)

edit ops:  show [N] | set-meta KEY VALUE | set-theme NAME | replace N JSON | insert N JSON | append JSON | delete N | move FROM TO | patch N JSON
           (N is the 1-based slide number; JSON may be '@file.json'; patch = deep merge, null deletes a key)
"""
import argparse, copy, glob, json, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__)); SK = os.path.normpath(os.path.join(HERE, "..", ".."))
PP = os.path.join(SK, "python-pptx", "scripts"); sys.path.insert(0, PP)
import diagram_geom as G  # noqa: E402
PY = sys.executable
EX = os.path.join(HERE, "..", "examples")


def run(cmd, check=False):
    r = subprocess.run(cmd, capture_output=True, text=True)
    out = (r.stdout + r.stderr).strip()
    if check and r.returncode: print(out); sys.exit(r.returncode)
    return r.returncode, out


def load(path): return json.load(open(path, encoding="utf-8"))
def save(path, o): json.dump(o, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
def jarg(a): return json.load(open(a[1:], encoding="utf-8")) if a.startswith("@") else json.loads(a)


# ------------------------------------------------------------------ catalog
SPECS = {
 "hero": "Opening slide: left headline + tagline, centre soft 3D cubes, right mini flow, 3 concept cards. fields: kicker,title(\\n),tagline,concepts[{name,desc,icon,tone?}],nodes[],edges[]",
 "cover": "Plain title slide. fields: title,subtitle",
 "section": "Section divider. fields: number,title,subtitle",
 "agenda": "Numbered agenda. fields: title,items[str]",
 "bullets": "Headline + 3-5 bullets. fields: title,bullets[str|{text,sub}]",
 "two-col": "Two tinted cards. fields: title,left{heading,bullets[]},right{...}",
 "kpi": "KPI tiles (2-5). fields: title,items[{label,value,delta}],takeaway?",
 "chart": "Native chart. fields: title,chart{kind:bar|hbar|stacked|line|pie,categories[],series[{name,values[]}],unit?},takeaway?,source?",
 "table": "Native table. fields: title,columns[],rows[[]],takeaway?",
 "timeline": "Timeline (3-5 events). fields: title,events[{when,title,text}]",
 "process": "Chevron steps (3-5). fields: title,steps[{title,text}]",
 "comparison": "A vs B cards. fields: title,a{name,tag?,points[]},b{...}",
 "layers": "Layered architecture. fields: title,layers[{name,items[]}]",
 "code": "Code window (<=12 lines). fields: title,language,code,caption?",
 "workflow": "Simple node/edge flow (nodes x,y in 0..1). fields: title,nodes[{id,label,sub?,icon?,x,y,tone?}],edges[{from,to,style?,label?}],takeaway?",
 "diagram": "FREE CANVAS 1000x490 units — rich architecture / flow / lanes / notes / panels. See `catalog diagram`. fields: title,subtitle?,elements[],edges[],cover?",
 "closing": "Closing slide. fields: title,subtitle,contact[]",
}


def cmd_catalog(a):
    t = a.topic
    if t in ("types", "all"):
        ex = {}
        for f in ("outline.example.json", "diagrams.example.json"):
            for s in load(os.path.join(EX, f))["slides"]: ex.setdefault(s["type"], s)
        print("SLIDE TYPES (every slide may also carry notes, source):")
        for k, v in SPECS.items(): print("  %-10s %s" % (k, v))
        print("\nExample of one slide of each type: examples/outline.example.json, examples/diagrams.example.json")
    if t in ("palette", "all"):
        for name in G.style_names():
            G.use(name); print("\nPALETTE — style '%s' (theme %s)%s: %s" % (name, G.STYLE["theme"], "  [DEFAULT]" if name == "vivid" else "", G.STYLE["description"]))
            print("  page = pure white · parallel items cycle: %s" % " > ".join(G.CYCLE))
            for n, c in G.TONES.items(): print("  %-7s fill #%s  border #%s  title/icon #%s" % (n, G.rgbhex(c["fill"])[1:].upper(), G.rgbhex(c["border"])[1:].upper(), G.rgbhex(c["solid"])[1:].upper()))
        G.use("vivid")
        print("  meaning: blue=input/data/general/branch · purple=model/agent/runtime · green=tools/storage/success · orange(amber)=decision/state/answer/warning · pink=memory/error · gray=start/end")
    if t in ("icons", "all"): print("\nICONS (fixed colour per icon across a deck): " + ", ".join(sorted(G.ICONS)))
    if t in ("themes", "all"):
        th = load(os.path.join(SK, "html-ppt-studio", "assets", "themes", "themes.json")); print("\nTHEMES (default modern-tech): " + ", ".join(x["name"] for x in th))
    if t in ("diagram",):
        print(open(os.path.join(HERE, "..", "reference", "diagram.md"), encoding="utf-8").read())


# ------------------------------------------------------------------ new / check / edit
def cmd_new(a):
    d = os.path.join("output", a.slug); os.makedirs(d, exist_ok=True); p = os.path.join(d, "outline.json")
    if os.path.exists(p) and not a.force: print("exists:", p, "(use --force)"); sys.exit(1)
    o = {"meta": {"title": a.title or a.slug, "subtitle": "", "author": "", "date": "", "lang": a.lang, "theme": a.theme, "audience": "", "duration_min": 20},
         "slides": [{"type": "cover", "title": a.title or a.slug, "subtitle": "", "notes": ""}, {"type": "closing", "title": "Thank you", "subtitle": "", "contact": [], "notes": ""}]}
    save(p, o); print("created", p)


def cmd_check(a):
    rc, out = run([PY, os.path.join(HERE, "check_outline.py"), a.outline]); print(out); sys.exit(rc)


def merge(dst, patch):
    for k, v in patch.items():
        if v is None: dst.pop(k, None)
        elif isinstance(v, dict) and isinstance(dst.get(k), dict): merge(dst[k], v)
        else: dst[k] = v
    return dst


def cmd_edit(a):
    o = load(a.outline); S = o["slides"]; op = a.op; r = a.rest
    def idx(n):
        n = int(n)
        if not 1 <= n <= len(S): sys.exit("slide %d out of range (1..%d)" % (n, len(S)))
        return n - 1
    if op == "show":
        if r: print(json.dumps(S[idx(r[0])], ensure_ascii=False, indent=1))
        else:
            print("meta:", json.dumps(o["meta"], ensure_ascii=False))
            for i, s in enumerate(S, 1): print("%2d  %-10s %s" % (i, s["type"], s.get("title") or s.get("subtitle") or ""))
        return
    if op == "set-meta": o["meta"][r[0]] = jarg(r[1]) if r[1][:1] in "[{@" else r[1]
    elif op == "set-theme": o["meta"]["theme"] = r[0]
    elif op == "replace": S[idx(r[0])] = jarg(r[1])
    elif op == "insert": S.insert(idx(r[0]) if int(r[0]) <= len(S) else len(S), jarg(r[1]))
    elif op == "append": S.append(jarg(r[0]))
    elif op == "delete": S.pop(idx(r[0]))
    elif op == "move": s = S.pop(idx(r[0])); S.insert(int(r[1]) - 1, s)
    elif op == "patch": merge(S[idx(r[0])], jarg(r[1]))
    else: sys.exit("unknown edit op %r" % op)
    save(a.outline, o); print("ok — %d slides" % len(S))
    for i, s in enumerate(S, 1): print("%2d  %-10s %s" % (i, s["type"], s.get("title") or ""))


# ------------------------------------------------------------------ build / verify / lint / preview
def cmd_build(a):
    o = load(a.outline); d = a.out or os.path.dirname(os.path.abspath(a.outline)); os.makedirs(d, exist_ok=True); theme = a.theme or o["meta"].get("theme", "modern-tech")
    rc, out = run([PY, os.path.join(HERE, "check_outline.py"), a.outline]); print(out)
    if rc: print("\nBUILD ABORTED: fix the ERRORs above first."); sys.exit(1)
    res = {"outline": os.path.abspath(a.outline), "theme": theme, "slides": len(o["slides"])}
    if not a.no_html:
        h = os.path.join(d, "draft.html"); rc, out = run([PY, os.path.join(HERE, "outline_to_html.py"), a.outline, h, "--theme", theme]); res["html"] = h if rc == 0 else "FAILED: " + out
    if not a.no_pptx:
        p = os.path.join(d, "deck.pptx"); rc, out = run([PY, os.path.join(PP, "outline_to_pptx.py"), a.outline, p, "--theme", theme])
        if rc: print(out); sys.exit(1)
        res["pptx"] = p
        rc, vout = run([PY, os.path.join(PP, "verify_pptx.py"), p, "--theme", theme, "--json"]); v = json.loads(vout[vout.index("{"):]) if "{" in vout else {}
        res["verify"] = {k: v.get(k) for k in ("pictures", "background_ok", "inventory", "errors", "warnings")}
        rc, lout = run([PY, os.path.join(PP, "lint_pptx.py"), p]); res["lint"] = [l for l in lout.splitlines() if l.startswith(("ERROR", "WARN", "result"))]
    print("\n" + json.dumps(res, ensure_ascii=False, indent=1))
    if "pptx" in res and (res["verify"].get("errors") or any(l.startswith("ERROR") for l in res["lint"])): sys.exit(2)


def cmd_verify(a):
    rc, out = run([PY, os.path.join(PP, "verify_pptx.py"), a.deck, "--theme", a.theme] + (["--allow-pictures"] if a.allow_pictures else [])); print(out); sys.exit(rc)


def cmd_lint(a):
    rc, out = run([PY, os.path.join(PP, "lint_pptx.py"), a.deck] + (["--render"] if a.render else [])); print(out); sys.exit(rc)


def cmd_preview(a):
    f = a.file
    if f.endswith(".json"):
        o = load(f); d = os.path.dirname(os.path.abspath(f)); f = os.path.join(d, "deck.pptx")
        rc, out = run([PY, os.path.join(PP, "outline_to_pptx.py"), a.file, f, "--theme", o["meta"].get("theme", "modern-tech")], True)
    if not shutil.which("soffice"): sys.exit("preview needs LibreOffice (soffice) — not installed")
    out_dir = os.path.join(os.path.dirname(os.path.abspath(f)), "preview"); shutil.rmtree(out_dir, ignore_errors=True); os.makedirs(out_dir)
    run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", out_dir, f])
    pdf = os.path.join(out_dir, os.path.splitext(os.path.basename(f))[0] + ".pdf")
    if not os.path.exists(pdf): sys.exit("PDF conversion failed")
    if not shutil.which("pdftoppm"): sys.exit("preview needs pdftoppm (poppler)")
    run(["pdftoppm", "-r", str(a.dpi), "-png", pdf, os.path.join(out_dir, "slide")], True)
    pngs = sorted(glob.glob(os.path.join(out_dir, "slide-*.png")))
    if a.pages:
        want = {int(x) for x in a.pages.split(",")}; keep = [p for p in pngs if int(os.path.basename(p).split("-")[1].split(".")[0]) in want]
        for p in pngs:
            if p not in keep: os.remove(p)
        pngs = keep
    print("slides rendered:", len(pngs)); [print(" ", p) for p in pngs]
    try:
        from PIL import Image
        ims = [Image.open(p) for p in pngs]; w, h = ims[0].size; cols = 3 if len(ims) > 4 else 2; rows = -(-len(ims) // cols)
        sheet = Image.new("RGB", (cols * w, rows * h), "white")
        for i, im in enumerate(ims): sheet.paste(im, ((i % cols) * w, (i // cols) * h))
        sp = os.path.join(out_dir, "contact_sheet.png"); sheet.save(sp); print("contact sheet:", sp)
    except Exception as e: print("(no contact sheet: %s)" % e)


def cmd_colors(a):
    try: from PIL import Image
    except ImportError: sys.exit("colors needs Pillow (pip install pillow)")
    import collections, colorsys
    G.use(a.style); im = Image.open(a.image).convert("RGB")
    if a.crop: x0, y0, x1, y1 = [int(v) for v in a.crop.split(",")]; im = im.crop((x0, y0, x1, y1))
    W, H = im.size; px = im.load(); c = collections.Counter(); bg = collections.Counter(); n = 0
    for y in range(0, H, 2):
        for x in range(0, W, 2):
            r, g, b = px[x, y]; n += 1
            if min(r, g, b) >= 240 and max(r, g, b) - min(r, g, b) <= 14: bg[(r, g, b)] += 1; continue
            if max(r, g, b) < 60: continue            # text / black bars
            c[(r // 8 * 8 + 4, g // 8 * 8 + 4, b // 8 * 8 + 4)] += 1
    nb = sum(bg.values()); print("image %dx%d · near-white background %.0f%% (most common %s)" % (W, H, 100 * nb / max(n, 1), ["#%02x%02x%02x" % k for k, _ in bg.most_common(3)]))
    tot = sum(c.values()) or 1
    def near(rgb):
        """Nearest palette entry. Neutral tones only match as lines/labels (solid) or, for gray, very unsaturated fills — never steal a pale chromatic fill."""
        sat = colorsys.rgb_to_hsv(*[q / 255 for q in rgb])[1]; best = None
        for name, t in G.TONES.items():
            for role in ("fill", "solid"):
                if name == "dark" and role == "fill": continue
                if name == "gray" and role == "fill" and sat > 0.05: continue
                d = sum((rgb[i] - t[role][i]) ** 2 for i in range(3))
                if best is None or d < best[0]: best = (d, name, role)
        return best
    print("dominant non-white colours (share of coloured area) -> nearest palette entry:")
    for col, v in c.most_common(a.top):
        h, sat, val = colorsys.rgb_to_hsv(*[q / 255 for q in col]); d, name, role = near(col)
        print("  #%02x%02x%02x  %4.1f%%  sat %2d%%  ->  %-6s %-5s (distance %d)" % (col + (100 * v / tot, sat * 100, name, role, d ** .5)))
    print("hint: pale fills have sat < 15%; borders / icons / titles are the saturated ones. Compare with `deck.py catalog palette`.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter); sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("catalog"); s.add_argument("topic", nargs="?", default="all", choices=["types", "palette", "icons", "themes", "diagram", "all"]); s.set_defaults(f=cmd_catalog)
    s = sub.add_parser("new"); s.add_argument("slug"); s.add_argument("--title"); s.add_argument("--theme", default="modern-tech"); s.add_argument("--lang", default="zh"); s.add_argument("--force", action="store_true"); s.set_defaults(f=cmd_new)
    s = sub.add_parser("check"); s.add_argument("outline"); s.set_defaults(f=cmd_check)
    s = sub.add_parser("build"); s.add_argument("outline"); s.add_argument("--out"); s.add_argument("--theme"); s.add_argument("--no-html", action="store_true"); s.add_argument("--no-pptx", action="store_true"); s.set_defaults(f=cmd_build)
    s = sub.add_parser("preview"); s.add_argument("file"); s.add_argument("--pages"); s.add_argument("--dpi", type=int, default=70); s.set_defaults(f=cmd_preview)
    s = sub.add_parser("edit"); s.add_argument("outline"); s.add_argument("op"); s.add_argument("rest", nargs="*"); s.set_defaults(f=cmd_edit)
    s = sub.add_parser("verify"); s.add_argument("deck"); s.add_argument("--theme", default="modern-tech"); s.add_argument("--allow-pictures", action="store_true"); s.set_defaults(f=cmd_verify)
    s = sub.add_parser("lint"); s.add_argument("deck"); s.add_argument("--render", action="store_true"); s.set_defaults(f=cmd_lint)
    s = sub.add_parser("colors"); s.add_argument("image"); s.add_argument("--crop"); s.add_argument("--top", type=int, default=12); s.add_argument("--style", default="vivid", choices=G.style_names()); s.set_defaults(f=cmd_colors)
    a = ap.parse_args(); a.f(a)


if __name__ == "__main__": main()
