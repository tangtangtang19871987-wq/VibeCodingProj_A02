"""HTML → Markdown for Layer 0 ingestion (stdlib only).

Real-world source material often arrives as HTML (course pages, exported wikis).
Policy: the original HTML is stored verbatim (it *is* the source of record and can
always be viewed/downloaded); a derived Markdown rendition is generated next to it
and is what navigation, outlines and the compiler work on. The derived file's
frontmatter records `converted_from`, the converter version and the source sha,
so provenance is explicit and conversion can be redone when the converter improves.

Handled: headings, paragraphs/blocks, line breaks, bold/italic/code, pre, nested
lists, tables (→ GFM), links (sibling .html → .md), images, blockquotes, hr.
Inline SVG diagrams: graphics are dropped, their <text> labels are kept as a
"Figure text" line so the knowledge they carry is not lost. style/script/head ignored.
"""
from __future__ import annotations

import json
import re
from html.parser import HTMLParser

CONVERTER = "lkb-html2md/1"
_BLOCK = {"p", "div", "section", "article", "header", "footer", "main", "aside", "nav", "figure",
          "figcaption", "form", "fieldset", "details", "summary", "dl", "dt", "dd", "center"}
_SKIP = {"style", "script", "head", "noscript", "template", "button", "select", "option", "iframe"}
_WS = re.compile(r"[ \t\r\n\f ]+")


class _Conv(HTMLParser):
    def __init__(self, link_map):
        super().__init__(convert_charrefs=True)
        self.link_map = link_map
        self.out: list[str] = []      # finished blocks
        self.buf: list[str] = []      # current inline text
        self.skip = 0
        self.title = ""
        self._in_title = False
        self.pre = 0
        self.lists: list[list] = []   # stack of [kind, counter]
        self.table = None             # {"rows": [[cells]], "row": [...], "cell": [...], "head": bool}
        self.svg = 0
        self.svg_text: list[str] = []
        self.link_stack: list[str | None] = []
        self.quote = 0

    # ---- helpers -----------------------------------------------------------
    def _text(self) -> str:
        t = "".join(self.buf)
        self.buf = []
        return t if self.pre else _WS.sub(" ", t).strip()

    def flush(self, prefix: str = ""):
        t = self._text()
        if not self.pre and re.fullmatch(r"[*`\s]*", t):  # dangling markers from malformed HTML
            t = ""
        if t:
            lead = "> " * self.quote
            self.out.append(lead + prefix + t)

    def emit(self, s: str):
        self.out.append(s)

    # ---- parser callbacks -----------------------------------------------------
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "title":
            self._in_title = True
            return
        if tag in _SKIP:
            self.skip += 1
            return
        if self.skip:
            return
        if tag == "svg":
            self.svg += 1
            return
        if self.svg:
            return
        if self.table is not None and tag in ("td", "th"):
            self.table["cell"] = []
            self.table["head"] |= tag == "th"
            return
        if self.table is not None and tag == "tr":
            self.table["row"] = []
            return
        if tag == "table":
            self.flush()
            self.table = {"rows": [], "row": [], "cell": None, "head": False}
            return
        if re.fullmatch(r"h[1-6]", tag):
            self.flush()
            self.buf.append("")
            self._heading = int(tag[1])
        elif tag in _BLOCK:
            self.flush(self._li_prefix(cont=True))
        elif tag == "br":
            if self.pre:
                self.buf.append("\n")
            else:
                self.flush(self._li_prefix(cont=True))
        elif tag == "hr":
            self.flush()
            self.emit("---")
        elif tag in ("ul", "ol"):
            self.flush(self._li_prefix(cont=True))
            self.lists.append([tag, 0])
        elif tag == "li":
            self.flush(self._li_prefix(cont=True))
            if self.lists:
                self.lists[-1][1] += 1
            self._li_pending = True
        elif tag == "pre":
            self.flush()
            self.pre += 1
        elif tag == "blockquote":
            self.flush()
            self.quote += 1
        elif tag in ("strong", "b", "em", "i") or (tag == "code" and not self.pre):
            self._open_mark(tag)
        elif tag == "a":
            href = self._map_link(a.get("href") or "")
            # remember where the link text starts; wrap only if it stays inline
            self.link_stack.append({"href": href, "out": len(self.out), "buf": len(self.buf),
                                    "cell": len(self.table["cell"]) if self.table and self.table["cell"] is not None else None})
        elif tag == "img":
            src = a.get("src") or ""
            if src and not src.startswith("data:"):
                self._put(f"![{a.get('alt', '')}]({self._map_link(src) or src})")

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
            return
        if tag in _SKIP:
            self.skip = max(0, self.skip - 1)
            return
        if self.skip:
            return
        if tag == "svg":
            self.svg = max(0, self.svg - 1)
            if not self.svg and self.svg_text:
                labels = [t for t in (_WS.sub(" ", x).strip() for x in self.svg_text) if t]
                if labels:
                    self.flush(self._li_prefix(cont=True))
                    self.emit("> Figure text: " + " · ".join(labels))
                self.svg_text = []
            return
        if self.svg:
            return
        if self.table is not None and self.table["cell"] is not None and \
                (tag in ("strong", "b", "em", "i", "code") or tag == "a"):
            if tag == "a" and self.link_stack:
                self._close_link(self.link_stack.pop())
            elif tag != "a":
                self._close_mark(tag)
            return
        if self.table is not None:
            if tag in ("td", "th") and self.table["cell"] is not None:
                cell = _WS.sub(" ", "".join(self.table["cell"])).strip().replace("|", "\\|")
                self.table["row"].append(cell)
                self.table["cell"] = None
            elif tag == "tr":
                if self.table["row"]:
                    self.table["rows"].append(self.table["row"])
                self.table["row"] = []
            elif tag == "table":
                self._emit_table()
            return
        if re.fullmatch(r"h[1-6]", tag):
            t = self._text().lstrip("# ")
            if t:
                self.emit("#" * getattr(self, "_heading", 2) + " " + t)
        elif tag in _BLOCK:
            self.flush(self._li_prefix(cont=True))
        elif tag in ("ul", "ol"):
            self.flush(self._li_prefix())
            if self.lists:
                self.lists.pop()
        elif tag == "li":
            self.flush(self._li_prefix())
        elif tag == "pre":
            code = "".join(self.buf).strip("\n")
            self.buf = []
            self.pre = max(0, self.pre - 1)
            self.emit("```\n" + code + "\n```")
        elif tag == "blockquote":
            self.flush()
            self.quote = max(0, self.quote - 1)
        elif tag in ("strong", "b", "em", "i") or (tag == "code" and not self.pre):
            self._close_mark(tag)
        elif tag == "a" and self.link_stack:
            self._close_link(self.link_stack.pop())

    def handle_data(self, data):
        if self._in_title:
            self.title += data
            return
        if self.skip:
            return
        if self.svg:
            self.svg_text.append(data)
            return
        if self.table is not None:
            if self.table["cell"] is not None:
                self.table["cell"].append(data)
            return
        self.buf.append(data)

    # ---- inline marks & links ---------------------------------------------------
    _MARK = {"strong": "**", "b": "**", "em": "*", "i": "*", "code": "`"}

    def _target(self) -> list:
        return self.table["cell"] if self.table is not None and self.table["cell"] is not None else self.buf

    def _open_mark(self, tag):
        t = self._target()
        self.marks = getattr(self, "marks", [])
        self.marks.append((tag, len(self.out), len(t), id(t)))
        t.append(self._MARK[tag])

    def _close_mark(self, tag):
        marks = getattr(self, "marks", [])
        if not marks:
            return
        otag, out_n, pos, tid = marks.pop()
        t = self._target()
        if id(t) == tid and out_n == len(self.out) and pos < len(t):
            if not "".join(t[pos + 1:]).strip():  # empty element (e.g. an icon <i class=fa…>)
                del t[pos:]
                return
            # move surrounding whitespace outside the markers so Markdown still parses
            inner = "".join(t[pos + 1:])
            del t[pos + 1:]
            lead, core, trail = inner[:len(inner) - len(inner.lstrip())], inner.strip(), inner[len(inner.rstrip()):]
            t[pos] = lead + self._MARK[otag] + core + self._MARK[otag] + trail
        # a block boundary happened inside the mark: the opener was already flushed; drop the closer

    def _close_link(self, ln: dict):
        href = ln["href"]
        t = self._target()
        if not href:
            return
        if ln["out"] == len(self.out) and (ln["cell"] is not None or True):
            start = ln["cell"] if ln["cell"] is not None else ln["buf"]
            if start <= len(t):
                inner = "".join(t[start:]).strip()
                del t[start:]
                if inner:
                    t.append(f"[{inner}]({href})")
                return
        # block content inside <a> (a "card" link): link the first heading of the card,
        # otherwise add an explicit link line after it
        self.flush(self._li_prefix(cont=True))
        for i in range(ln["out"], len(self.out)):
            m = re.match(r"(#{1,6}) (.+)$", self.out[i])
            if m:
                self.out[i] = f"{m.group(1)} [{m.group(2)}]({href})"
                return
        self.emit(f"[→ {href}]({href})")

    # ---- pieces -------------------------------------------------------------------
    def _put(self, s: str):
        if self.table is not None and self.table["cell"] is not None:
            self.table["cell"].append(s)
        elif not self.svg:
            self.buf.append(s)

    def _li_prefix(self, cont: bool = False) -> str:
        if not self.lists or not getattr(self, "_li_pending", False):
            return "  " * max(0, len(self.lists) - 1) + ("  " if self.lists and cont else "") if self.lists else ""
        self._li_pending = False
        kind, n = self.lists[-1]
        return "  " * (len(self.lists) - 1) + ("- " if kind == "ul" else f"{n}. ")

    def _map_link(self, href: str) -> str | None:
        if not href or href.startswith(("javascript:", "#")) and len(href) <= 1:
            return None
        if href.startswith("javascript:"):
            return None
        base, frag = (href.split("#", 1) + [""])[:2]
        if base in self.link_map:
            return self.link_map[base] + (f"#{frag}" if frag else "")
        if base and "://" not in base and not base.startswith(("mailto:", "//")) and \
                base.lower().endswith((".html", ".htm")):
            # sibling pages are ingested the same way, so link to their Markdown rendition
            return base.rsplit(".", 1)[0] + ".md" + (f"#{frag}" if frag else "")
        return href

    def _emit_table(self):
        rows = self.table["rows"]
        self.table = None
        if not rows:
            return
        width = max(len(r) for r in rows)
        rows = [r + [""] * (width - len(r)) for r in rows]
        lines = ["| " + " | ".join(rows[0]) + " |", "|" + "---|" * width]
        lines += ["| " + " | ".join(r) + " |" for r in rows[1:]]
        self.emit("\n".join(lines))


def convert(html: str, link_map: dict[str, str] | None = None, source_name: str = "", source_sha: str = "") -> str:
    c = _Conv(link_map or {})
    c.feed(html)
    c.close()
    c.flush()
    blocks, prev = [], None
    for b in c.out:
        b = b.rstrip()
        if not b.strip() or b == prev:
            continue
        blocks.append(b)
        prev = b
    # join: list items / quote lines stay tight, other blocks get a blank line
    out = []
    for b in blocks:
        tight = out and re.match(r"\s*(-|\d+\.|>)\s", b) and re.match(r"\s*(-|\d+\.|>)\s", out[-1].splitlines()[-1])
        out.append(("\n" if tight else "\n\n") + b if out else b)
    body = "".join(out).strip() + "\n"
    html_title = _WS.sub(" ", c.title).strip()
    h1 = re.search(r"^# (.+)$", body, re.M)
    title = re.sub(r"\[(.+?)\]\([^)]*\)", r"\1", h1.group(1)).strip() if h1 else html_title  # page <title> often carries a site suffix
    fm = {"title": title, "html_title": html_title if html_title != title else "", "converted_from": source_name,
          "source_sha256": source_sha, "converter": CONVERTER}
    head = "---\n" + "".join(f"{k}: {json.dumps(v, ensure_ascii=False)}\n" for k, v in fm.items() if v) + "---\n"
    return head + body
