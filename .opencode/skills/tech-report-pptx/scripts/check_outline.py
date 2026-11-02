#!/usr/bin/env python3
"""Validate outline.json BEFORE building: structure, slide types, and `diagram` geometry
(unknown ids/icons/tones, out-of-canvas, element overlaps, edges crossing nodes)
and the house colour rules (colour-count hint per slide; same icon = same colour across the deck).

  python3 check_outline.py outline.json        # exit 1 on ERROR
"""
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "python-pptx", "scripts"))
import diagram_geom as G

TYPES = {"cover", "section", "agenda", "bullets", "two-col", "kpi", "chart", "table", "timeline", "process", "comparison", "layers", "code", "closing", "hero", "workflow", "diagram"}
REQ = {"agenda": ["items"], "bullets": ["bullets"], "two-col": ["left", "right"], "kpi": ["items"], "chart": ["chart"], "table": ["columns", "rows"], "timeline": ["events"],
       "process": ["steps"], "comparison": ["a", "b"], "layers": ["layers"], "code": ["code"], "workflow": ["nodes"], "diagram": ["elements"], "hero": ["title"]}


def main():
    o = json.load(open(sys.argv[1], encoding="utf-8")); errs = warns = 0
    def say(sev, i, msg):
        nonlocal errs, warns
        print("%-5s slide %s: %s" % (sev, i, msg)); errs += sev == "ERROR"; warns += sev == "WARN"
    icon_tones = {}
    if "meta" not in o or "title" not in o.get("meta", {}): say("ERROR", "-", "meta.title missing")
    for i, s in enumerate(o.get("slides", []), 1):
        t = s.get("type")
        if t not in TYPES: say("ERROR", i, "unknown type %r" % t); continue
        for k in REQ.get(t, []):
            if k not in s: say("ERROR", i, "%s slide needs %r" % (t, k))
        if t not in ("cover", "section", "closing", "hero") and not s.get("title") and not s.get("cover"): say("WARN", i, "no title")
        if not s.get("notes"): say("WARN", i, "no speaker notes")
        if t == "diagram":
            for sev, m in G.validate(s): say(sev, i, m)
            u = G.tones_used(s)
            if len(u) > 5: say("WARN", i, "uses %d colours (%s) — usually 3-4 is enough" % (len(u), ", ".join(sorted(u))))
            elif len(u) == 5: say("INFO", i, "5 colours in use (%s) — fine for a dense architecture map, otherwise reduce" % ", ".join(sorted(u)))
            for e in s.get("elements", []):
                if e.get("kind") == "node" and e.get("key") and e.get("w", 0) * e.get("h", 0) > 16000: say("WARN", i, "key node %r is large — emphasis should stay small" % e.get("id"))
                if e.get("icon"): icon_tones.setdefault(e["icon"], {}).setdefault(e.get("tone", "blue"), []).append(i)
    for ic, tm in icon_tones.items():
        if len(tm) > 1: say("WARN", "-", "icon %r used with different colours %s — same component type should keep the same semantic colour" % (ic, {k: v for k, v in tm.items()}))
    print("result: %d error(s), %d warning(s)" % (errs, warns)); sys.exit(1 if errs else 0)


if __name__ == "__main__": main()
