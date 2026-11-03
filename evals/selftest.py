#!/usr/bin/env python3
"""Deterministic self-test of everything the agent's tools stand on (no LLM, no opencode needed).

  python3 evals/selftest.py            # exit 1 if any check fails

Covers: catalog · outline validation (positive + negative) · build · editable-PPTX guarantees (0 pictures, 0 media, pure-white bg,
palette audit) · lint · structured edits · colour measuring · icons as native shapes · multi-theme builds."""
import json, os, re, subprocess, sys, tempfile, zipfile, shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SK = os.path.join(ROOT, ".opencode", "skills"); DECK = os.path.join(SK, "tech-report-pptx", "scripts", "deck.py"); PP = os.path.join(SK, "python-pptx", "scripts")
EX = os.path.join(SK, "tech-report-pptx", "examples"); PY = sys.executable
results = []


def run(*a): r = subprocess.run([PY, *a], capture_output=True, text=True, cwd=tmp); return r.returncode, (r.stdout + r.stderr)
def check(name, ok, detail=""): results.append((name, bool(ok), detail)); print(("PASS " if ok else "FAIL ") + name + ("  — " + detail if (detail and not ok) else ""))
def pptx_stats(p):
    z = zipfile.ZipFile(p); xs = [z.read(n).decode("utf8") for n in z.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n)]
    return {"pics": sum(len(re.findall(r"<p:pic[ >]", x)) for x in xs), "media": [n for n in z.namelist() if n.startswith("ppt/media/")],
            "charts": len([n for n in z.namelist() if n.startswith("ppt/charts/chart")]), "tables": sum(x.count("<a:tbl>") for x in xs), "groups": sum(x.count("<p:grpSp>") for x in xs)}


tmp = tempfile.mkdtemp(prefix="deckselftest-")
try:
    # --- catalog
    for t in ("types", "palette", "icons", "themes", "diagram"):
        rc, out = run(DECK, "catalog", t); check("catalog " + t, rc == 0 and len(out) > 80)
    # --- positive: examples
    for f in ("outline.example.json", "diagrams.example.json"):
        src = os.path.join(EX, f); rc, out = run(DECK, "check", src); check("check %s: 0 errors" % f, rc == 0, out[-200:])
        d = os.path.join(tmp, f.split(".")[0]); rc, out = run(DECK, "build", src, "--out", d); check("build %s" % f, rc == 0, out[-300:])
        p = os.path.join(d, "deck.pptx"); st = pptx_stats(p)
        check("%s: zero pictures / zero media (fully native)" % f, st["pics"] == 0 and not st["media"], str(st))
        rc, out = run(os.path.join(PP, "verify_pptx.py"), p, "--json"); v = json.loads(out); check("%s: verify (white bg, 0 pictures)" % f, rc == 0 and v["background_ok"], out[-200:])
        check("%s: palette clean (no off-palette colours)" % f, not v["off_palette"], str(v["off_palette"]))
        rc, out = run(os.path.join(PP, "lint_pptx.py"), p); check("%s: lint 0 errors" % f, rc == 0, out[-200:])
        check("%s: draft.html written" % f, os.path.getsize(os.path.join(d, "draft.html")) > 20000)
        if f.startswith("outline"): check("outline example has a native chart and a native table", st["charts"] >= 1 and st["tables"] >= 1, str(st))
        else: check("diagram example draws icons as native groups", st["groups"] >= 20, str(st))
    # --- negative: validation must catch real mistakes
    bad = json.load(open(os.path.join(EX, "diagrams.example.json"), encoding="utf-8")); s = bad["slides"][3]
    s["elements"].append({"kind": "node", "id": "x1", "x": 10, "y": 100, "w": 300, "h": 60, "label": "overlap", "tone": "teal", "icon": "nope"}); s["elements"].append({"kind": "node", "id": "x2", "x": 950, "y": 450, "w": 200, "h": 80, "label": "off canvas"})
    bad["slides"].append({"type": "nonsense"}); bp = os.path.join(tmp, "bad.json"); json.dump(bad, open(bp, "w", encoding="utf-8"), ensure_ascii=False)
    rc, out = run(DECK, "check", bp); need = ["overlap", "out of canvas", "unknown icon", "teal", "unknown type"]
    check("check catches overlap / off-canvas / bad icon / retired tone / bad type", rc != 0 and all(k in out for k in need), out[-400:])
    rc, out = run(DECK, "build", bp); check("build refuses an outline with errors", rc != 0 and "ABORTED" in out)
    from pptx import Presentation  # picture detector
    pr = Presentation(); sl = pr.slides.add_slide(pr.slide_layouts[6]); png = os.path.join(tmp, "x.png")
    from PIL import Image; Image.new("RGB", (40, 40), (200, 30, 30)).save(png); sl.shapes.add_picture(png, 0, 0); pp = os.path.join(tmp, "pic.pptx"); pr.save(pp)
    rc, out = run(os.path.join(PP, "verify_pptx.py"), pp); check("verify rejects a deck containing a picture", rc != 0 and "picture" in out)
    # --- edit round trip
    os.chdir(tmp); rc, _ = run(DECK, "new", "t1", "--title", "T"); op = os.path.join(tmp, "output", "t1", "outline.json")
    for args in (["append", '{"type":"bullets","title":"A","bullets":["x"],"notes":"n"}'], ["patch", "3", '{"title":"B"}'], ["move", "3", "2"], ["set-theme", "paper"], ["delete", "2"]):
        rc, out = run(DECK, "edit", op, *args); check("edit " + args[0], rc == 0, out[-150:])
    o = json.load(open(op, encoding="utf-8")); check("edit result consistent", len(o["slides"]) == 2 and o["meta"]["theme"] == "paper", str(o["meta"]))
    # --- colour measuring
    sys.path.insert(0, PP); import diagram_geom as _G; _G.use("vivid"); bf = _G.TONES["blue"]["fill"]
    im = Image.new("RGB", (200, 100), (255, 255, 255)); im.paste(bf, (0, 0, 100, 100)); ip = os.path.join(tmp, "swatch.png"); im.save(ip)
    rc, out = run(DECK, "colors", ip); check("colors maps the blue tint %s to 'blue fill'" % (bf,), rc == 0 and re.search(r"->\s+blue\s+fill", out), out[-200:])
    # --- vision-first helper: reference | ours side-by-side image
    from PIL import Image as _I
    _I.new("RGB", (300, 200), (240, 245, 255)).save(os.path.join(tmp, "ref.png")); _I.new("RGB", (320, 180), (255, 250, 240)).save(os.path.join(tmp, "our.png"))
    rc, out = run(DECK, "compare", os.path.join(tmp, "ref.png"), os.path.join(tmp, "our.png")); cp = os.path.join(tmp, "compare.png")
    check("compare builds a side-by-side image of reference and ours", rc == 0 and os.path.exists(cp) and _I.open(cp).width > 2000, out[-200:])
    # --- style profiles (data-driven look) + regression guards against the "indigo looks purple / flat look" drift
    sys.path.insert(0, PP); import diagram_geom as G, colorsys
    for name in G.style_names():
        G.use(name); ok = all(t in G.TONES for t in ("blue", "purple", "green", "orange", "pink", "gray", "dark")) and all(c in G.TONES for c in G.CYCLE) and len(G.CUBE_SET) == 3
        check("style profile '%s' is complete" % name, ok)
    G.use("vivid"); hue = lambda c: colorsys.rgb_to_hsv(*[v / 255 for v in c])[0] * 360
    hb, hp = hue(G.TONES["blue"]["solid"]), hue(G.TONES["purple"]["solid"])
    check("vivid: 'blue' is a real blue (hue %.0f°) clearly apart from purple (%.0f°)" % (hb, hp), 195 <= hb <= 235 and hp - hb >= 25)
    check("vivid is the default style of the default theme", G.style_for_theme("modern-tech") == "vivid" and G.style_for_theme("modern-tech-flat") == "flat")
    buckets = {"blue": (195, 235), "purple": (250, 290), "green": (140, 175), "orange": (20, 45), "pink": (325, 350)}
    for f in ("outline", "diagrams"):
        x = zipfile.ZipFile(os.path.join(tmp, f, "deck.pptx")); cols = []
        for n in x.namelist():
            if re.match(r"ppt/slides/slide\d+\.xml$", n): cols += re.findall(r'srgbClr val="([0-9A-F]{6})"', x.read(n).decode("utf8"))
        hs = [hue(tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))) for c in cols if colorsys.rgb_to_hsv(*[int(c[i:i + 2], 16) / 255 for i in (0, 2, 4)])[1] > .55]
        miss = [k for k, (a, b) in buckets.items() if sum(a <= h <= b for h in hs) < 3]
        check("%s deck uses all five hues (blue/purple/green/orange/pink)" % f, not miss, "missing: %s" % miss)
    d = os.path.join(tmp, "flatstyle"); rc, out = run(DECK, "build", os.path.join(EX, "diagrams.example.json"), "--out", d, "--theme", "modern-tech-flat", "--no-html")
    rc2, out2 = run(os.path.join(PP, "verify_pptx.py"), os.path.join(d, "deck.pptx"), "--theme", "modern-tech-flat"); check("flat style builds and verifies", rc == 0 and rc2 == 0, out[-150:] + out2[-150:])
    import shutil as _sh
    if _sh.which("soffice") and _sh.which("pdftoppm"):
        try:
            from PIL import Image
            def sig(im, bins=12):
                im = im.convert("RGB"); W, H = im.size; px = im.load(); h = [0] * bins; n = 0
                for y in range(0, H, 2):
                    for x in range(0, W, 2):
                        hh, ss, vv = colorsys.rgb_to_hsv(*[q / 255 for q in px[x, y]])
                        if ss >= .45 and vv >= .45: h[int(hh * bins) % bins] += 1; n += 1
                return [c / max(n, 1) for c in h]
            l1 = lambda a, b: sum(abs(x - y) for x, y in zip(a, b)) / 2
            rc, out = run(DECK, "golden", "check"); print(out)
            check("every golden reference the user liked still matches (golden check)", rc == 0, out[-300:])
            sys.path.insert(0, os.path.join(SK, "tech-report-pptx", "scripts")); import golden as GD
            for g in GD.load():
                gs = GD.signature(os.path.join(ROOT, "evals", "golden", g["file"])); fl = GD.distance(gs, GD.render_signature(g["example"], g["slides"], theme="modern-tech-flat"))
                check("golden '%s' is discriminative: flat style is far from it (%.2f)" % (g["id"], fl), fl > g["max_distance"] + 0.1)
        except ImportError: print("SKIP golden image test (Pillow missing)")
    else: print("SKIP golden image test (needs LibreOffice + pdftoppm)")
    # --- the judgement layer: playbook present, referenced by every agent, loaded by opencode (if installed)
    PB = os.path.join(SK, "deck-playbook")
    need = ["SKILL.md", "STYLE_GUIDE.md", "METHOD.md", "FEEDBACK_PLAYBOOK.md", "TROUBLESHOOTING.md", "DEV_PLAYBOOK.md", "RETROSPECTIVE.md"]
    check("deck-playbook skill has all its documents", all(os.path.getsize(os.path.join(PB, f)) > 1500 for f in need))
    check("deck-playbook ships the user's reference images", len(__import__("glob").glob(os.path.join(PB, "references", "ref-*.png"))) >= 4)
    head = open(os.path.join(PB, "SKILL.md"), encoding="utf-8").read().split("---")[1]
    check("deck-playbook frontmatter: name matches folder + description", "name: deck-playbook" in head and "description:" in head)
    AG = os.path.join(ROOT, ".opencode", "agents")
    check("every agent prompt tells the model to load deck-playbook", all("deck-playbook" in open(os.path.join(AG, f), encoding="utf-8").read() for f in os.listdir(AG)))
    check("deck_golden tool exported", "export const golden" in open(os.path.join(ROOT, ".opencode", "tools", "deck.ts")).read())
    import shutil as _sh2
    if _sh2.which("opencode"):
        def oc(*a):
            f = os.path.join(tmp, "oc.out"); subprocess.run("opencode " + " ".join(a) + " > " + f + " 2>/dev/null", shell=True, cwd=ROOT, timeout=180); return open(f, encoding="utf-8", errors="ignore").read()
        sk = oc("debug", "skill"); ag = oc("debug", "agent", "tech-report-pptx")
        check("opencode discovers the deck-playbook skill", "deck-playbook/SKILL.md" in sk)
        check("opencode attaches deck_golden + deck_compare to the primary agent", '"deck_golden"' in ag and '"deck_compare"' in ag)
    else: print("SKIP opencode loading checks (opencode not installed)")
    # --- other themes still build, still native
    for th in ("paper", "nord", "aurora", "mono-light"):
        d = os.path.join(tmp, "th-" + th); rc, out = run(DECK, "build", os.path.join(EX, "outline.example.json"), "--out", d, "--theme", th, "--no-html")
        check("theme %s builds natively" % th, os.path.exists(os.path.join(d, "deck.pptx")) and pptx_stats(os.path.join(d, "deck.pptx"))["pics"] == 0, out[-200:])
finally:
    os.chdir(ROOT); shutil.rmtree(tmp, ignore_errors=True)

fails = [r for r in results if not r[1]]
print("\n%d checks, %d failed" % (len(results), len(fails))); sys.exit(1 if fails else 0)
