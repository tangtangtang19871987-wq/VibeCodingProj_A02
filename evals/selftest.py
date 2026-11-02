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
    im = Image.new("RGB", (200, 100), (255, 255, 255)); im.paste((238, 242, 255), (0, 0, 100, 100)); ip = os.path.join(tmp, "swatch.png"); im.save(ip)
    rc, out = run(DECK, "colors", ip); check("colors maps #EEF2FF to blue fill", rc == 0 and "blue" in out and "fill" in out, out[-200:])
    # --- other themes still build, still native
    for th in ("paper", "nord", "aurora", "mono-light"):
        d = os.path.join(tmp, "th-" + th); rc, out = run(DECK, "build", os.path.join(EX, "outline.example.json"), "--out", d, "--theme", th, "--no-html")
        check("theme %s builds natively" % th, os.path.exists(os.path.join(d, "deck.pptx")) and pptx_stats(os.path.join(d, "deck.pptx"))["pics"] == 0, out[-200:])
finally:
    os.chdir(ROOT); shutil.rmtree(tmp, ignore_errors=True)

fails = [r for r in results if not r[1]]
print("\n%d checks, %d failed" % (len(results), len(fails))); sys.exit(1 if fails else 0)
