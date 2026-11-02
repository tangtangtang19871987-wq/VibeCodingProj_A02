#!/usr/bin/env python3
"""outline.json -> source markdown for ppt-master (one '## ' section per slide, notes kept as 'Speaker notes').

  python3 outline_to_markdown.py outline.json source.md
"""
import json, sys


def bl(items, ind=""):
    out = []
    for it in items:
        if isinstance(it, dict):
            out.append("%s- %s" % (ind, it["text"]))
            if it.get("sub"): out.append("%s  - %s" % (ind, it["sub"]))
        else: out.append("%s- %s" % (ind, it))
    return out


def tbl(cols, rows):
    return ["| " + " | ".join(map(str, cols)) + " |", "|" + "---|" * len(cols)] + ["| " + " | ".join(map(str, r)) + " |" for r in rows]


def main():
    o = json.load(open(sys.argv[1], encoding="utf-8")); m = o.get("meta", {}); L = ["# " + m.get("title", "Untitled"), ""]
    if m.get("subtitle"): L += [m["subtitle"], ""]
    L += ["- Audience: %s" % m.get("audience", "-"), "- Duration: %s min" % m.get("duration_min", "-"), "- Language: %s" % m.get("lang", "-"), "- Author: %s" % m.get("author", "-"), ""]
    for i, s in enumerate(o["slides"], 1):
        t = s["type"]; L += ["## Slide %d — %s [%s]" % (i, s.get("title", t), t), ""]
        if s.get("subtitle"): L += [s["subtitle"], ""]
        if t == "agenda": L += bl(s["items"])
        elif t == "bullets": L += bl(s["bullets"])
        elif t == "two-col":
            for k in ("left", "right"): L += ["**%s**" % s[k].get("heading", "")] + bl(s[k].get("bullets", [])) + [""]
        elif t == "kpi": L += tbl(["Metric", "Value", "Delta"], [[x["label"], x["value"], x.get("delta", "")] for x in s["items"]])
        elif t == "chart":
            c = s["chart"]; L += ["Chart (%s)%s — use native chart:" % (c.get("kind", "bar"), ", unit: " + c["unit"] if c.get("unit") else ""), ""]
            L += tbl([""] + [x["name"] for x in c["series"]], [[cat] + [x["values"][j] for x in c["series"]] for j, cat in enumerate(c["categories"])])
        elif t == "table": L += tbl(s["columns"], s["rows"])
        elif t == "timeline": L += ["- **%s** %s: %s" % (x["when"], x["title"], x.get("text", "")) for x in s["events"]]
        elif t == "process": L += ["%d. **%s** — %s" % (j, x["title"], x.get("text", "")) for j, x in enumerate(s["steps"], 1)]
        elif t == "comparison":
            for k in ("a", "b"): L += ["**%s** (%s)" % (s[k]["name"], s[k].get("tag", ""))] + bl(s[k]["points"]) + [""]
        elif t == "layers": L += ["Layered architecture diagram (top → bottom):"] + ["- **%s**: %s" % (x["name"], ", ".join(x["items"])) for x in s["layers"]]
        elif t == "code": L += ["```%s" % s.get("language", ""), s["code"], "```"]
        elif t == "hero":
            L += [s.get("tagline", "")] + ["- **%s**: %s" % (c["name"], c.get("desc", "")) for c in s.get("concepts", [])] + ["", "Mini workflow: " + ", ".join(n["label"] for n in s.get("nodes", []))]
        elif t == "workflow":
            L += ["Workflow / DAG diagram. Nodes: " + ", ".join(n["label"] for n in s["nodes"]), "Edges (solid = sequential, dashed = conditional/loop):"]
            idn = {n["id"]: n["label"] for n in s["nodes"]}
            L += ["- %s -> %s [%s]%s" % (idn[e_["from"]], idn[e_["to"]], e_.get("style", "solid"), " " + e_["label"] if e_.get("label") else "") for e_ in s.get("edges", [])]
        elif t == "diagram":
            els = s.get("elements", []); idn = {e_["id"]: (e_.get("label") or e_.get("title")) for e_ in els if e_.get("id")}
            L += ["Diagram (nodes, lanes, panels) — draw as a flow diagram with tinted colour-coded nodes and icons:"]
            L += ["- %s: %s%s" % (e_["kind"], e_.get("label") or e_.get("title") or e_.get("text", ""), " — " + e_["sub"] if e_.get("sub") else "") for e_ in els if e_["kind"] in ("node", "panel", "group", "note", "heading")]
            L += ["Edges:"] + ["- %s -> %s [%s]%s" % (idn.get(e_["from"]), idn.get(e_["to"]), e_.get("style", "solid"), " " + e_["label"] if e_.get("label") else "") for e_ in s.get("edges", [])]
        elif t == "closing": L += bl(s.get("contact", []))
        if s.get("takeaway") or s.get("caption"): L += ["", "Takeaway: " + (s.get("takeaway") or s["caption"])]
        if s.get("source"): L += ["", "Source: " + s["source"]]
        if s.get("notes"): L += ["", "Speaker notes: " + s["notes"]]
        L.append("")
    open(sys.argv[2], "w", encoding="utf-8").write("\n".join(L)); print("wrote", sys.argv[2])


if __name__ == "__main__": main()
