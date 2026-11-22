"""Document tree index (the PageIndex idea, done deterministically).

Every Markdown document already carries its author's own structure: the heading
hierarchy. We turn it into a table-of-contents tree whose nodes carry exact line
ranges. That tree is used to

  * let the LLM *navigate* documents by reasoning over a ToC (query time), instead
    of similarity search over chunks;
  * compile documents that exceed one call's budget section-by-section along the
    author's structure (never arbitrary fixed-size chunks), with the whole-document
    outline always in view;
  * show readers an outline with line ranges.

No LLM, no embeddings: pure parsing, cached by content hash.
"""
from __future__ import annotations

import re

from . import fm

_H = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_FENCE = re.compile(r"^\s*(```|~~~)")
_CACHE: dict[str, dict] = {}


def _first_sentence(lines: list[str]) -> str:
    for ln in lines:
        s = ln.strip()
        if not s or s.startswith(("#", "|", "```", "~~~", "![", "<", "$$", "---")):
            continue
        s = re.sub(r"^[-*+>]\s+|^\d+[.)]\s+", "", s)
        s = re.sub(r"\*\*|__|`|^(?:图示文字：|Figure text:\s*)", "", s).strip()
        return re.split(r"(?<=[.。!?！？；;])\s*", s)[0][:160]
    return ""


def build(text: str, key: str | None = None) -> dict:
    """Return {"title", "lines", "nodes": [tree]} where node = {id, title, level, start, end, chars, gist, children}."""
    if key and key in _CACHE:
        return _CACHE[key]
    lines = text.splitlines()
    meta, _, offset = fm.split(text)
    heads = []
    in_code = False
    for i, ln in enumerate(lines, 1):
        if i <= offset:
            continue
        if _FENCE.match(ln):
            in_code = not in_code
            continue
        m = None if in_code else _H.match(ln)
        if m:
            heads.append((i, len(m.group(1)), m.group(2).strip()))
    n = len(lines)
    root = {"id": "root", "title": str(meta.get("title", "")), "level": 0, "start": offset + 1, "end": n, "children": []}
    stack = [root]
    flat = []
    for k, (line, level, title) in enumerate(heads):
        end = n
        for line2, level2, _ in heads[k + 1:]:
            if level2 <= level:
                end = line2 - 1
                break
        node = {"id": f"n{k + 1}", "title": title, "level": level, "start": line, "end": end, "children": []}
        nxt = heads[k + 1][0] - 1 if k + 1 < len(heads) else n
        node["gist"] = _first_sentence(lines[line:nxt])
        node["chars"] = sum(len(x) + 1 for x in lines[line - 1:end])
        while stack[-1]["level"] >= level:
            stack.pop()
        stack[-1]["children"].append(node)
        stack.append(node)
        flat.append(node)
    if not root["title"]:
        root["title"] = flat[0]["title"] if flat else ""
    # preamble before the first heading becomes its own node, so nothing is unreachable
    first = heads[0][0] if heads else n + 1
    if first - 1 > offset and any(x.strip() for x in lines[offset:first - 1]):
        pre = {"id": "n0", "title": "(preamble)", "level": 1, "start": offset + 1, "end": first - 1, "children": [],
               "gist": _first_sentence(lines[offset:first - 1]), "chars": sum(len(x) + 1 for x in lines[offset:first - 1])}
        root["children"].insert(0, pre)
    tree = {"title": root["title"], "lines": n, "chars": len(text), "nodes": root["children"]}
    if key:
        _CACHE[key] = tree
    return tree


def outline(tree: dict, max_depth: int = 6, gists: bool = True) -> str:
    """Compact textual ToC for prompts: `n3 [L12-40] ## Title — gist`."""
    out = []

    def walk(nodes, depth):
        for nd in nodes:
            if nd["level"] > max_depth:
                continue
            g = f" — {nd['gist']}" if gists and nd.get("gist") else ""
            out.append(f"{'  ' * depth}{nd['id']} [L{nd['start']}-{nd['end']}] {'#' * nd['level']} {nd['title']}{g}")
            walk(nd["children"], depth + 1)

    walk(tree["nodes"], 0)
    return "\n".join(out)


def find(tree: dict, node_id: str) -> dict | None:
    stack = list(tree["nodes"])
    while stack:
        nd = stack.pop()
        if nd["id"] == node_id:
            return nd
        stack.extend(nd["children"])
    return None


def sections(tree: dict, budget_chars: int) -> list[tuple[int, int, list[str]]]:
    """Partition a document along its heading structure into line ranges of at most
    ~budget_chars each. A section that is too large is opened up into its children;
    only a leaf section that alone exceeds the budget is split by paragraph lines (rare,
    reported as such). Returns [(start, end, [node titles])]."""
    if tree["chars"] <= budget_chars:
        return [(1, tree["lines"], ["(whole document)"])]
    units: list[tuple[int, int, str]] = []

    def expand(nodes):
        for nd in nodes:
            if nd.get("chars", 0) <= budget_chars or not nd["children"]:
                units.append((nd["start"], nd["end"], nd["title"]))
            else:
                first_child = nd["children"][0]["start"]
                if first_child > nd["start"]:
                    units.append((nd["start"], first_child - 1, nd["title"] + " (intro)"))
                expand(nd["children"])

    expand(tree["nodes"])
    if units and units[0][0] > 1:
        units.insert(0, (1, units[0][0] - 1, "(front matter)"))
    groups: list[tuple[int, int, list[str]]] = []
    cur: list = []
    size = 0
    avg = tree["chars"] / max(1, tree["lines"])
    for a, b, t in units:
        s = (b - a + 1) * avg
        if cur and size + s > budget_chars:
            groups.append((cur[0][0], cur[-1][1], [x[2] for x in cur]))
            cur, size = [], 0
        cur.append((a, b, t))
        size += s
    if cur:
        groups.append((cur[0][0], cur[-1][1], [x[2] for x in cur]))
    out = []
    for a, b, titles in groups:  # last resort for an oversized single leaf
        span = int(budget_chars / max(avg, 1))
        if (b - a + 1) * avg > budget_chars * 1.5 and len(titles) == 1:
            for s in range(a, b + 1, span):
                out.append((s, min(b, s + span - 1), [titles[0] + f" (part, L{s}+)"]))
        else:
            out.append((a, b, titles))
    return out
