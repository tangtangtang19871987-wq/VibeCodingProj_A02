"""Frontmatter: human-readable YAML subset that is also trivially machine-parseable.

We *write* each key on one line as `key: <JSON value>` — valid YAML, readable,
diff-friendly, and parseable without a YAML library. We *read* that format plus
the common hand-written YAML scalars/flow lists that Markdown authors use
(title: Foo, weight: 3, tags: [a, b]) so source documents' frontmatter is respected.
"""
from __future__ import annotations

import json
import re

_PENDING = object()  # "key:" with empty value; a block list may follow
_FM_RE = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.S)


def split(text: str) -> tuple[dict, str, int]:
    """Return (meta, body, body_line_offset)."""
    m = _FM_RE.match(text)
    if not m:
        return {}, text, 0
    meta = parse_block(m.group(1))
    offset = text[: m.end()].count("\n")
    return meta, text[m.end():], offset


def _scalar(v: str):
    v = v.strip()
    if v == "":
        return ""
    try:
        return json.loads(v)
    except Exception:
        pass
    if v[0] in "'\"" and v[-1] == v[0]:
        return v[1:-1]
    if v.startswith("[") and v.endswith("]"):
        inner = v[1:-1].strip()
        return [_scalar(x) for x in inner.split(",")] if inner else []
    low = v.lower()
    if low in ("true", "yes"):
        return True
    if low in ("false", "no"):
        return False
    if low in ("null", "~"):
        return None
    return v


def parse_block(block: str) -> dict:
    meta: dict = {}
    key = None
    for line in block.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line[0] in " \t" or line.startswith("- "):
            # block-style list item for the previous key (hand-written YAML)
            item = line.strip()
            if key and item.startswith("- "):
                if meta.get(key) is _PENDING:
                    meta[key] = []
                if isinstance(meta[key], list):
                    meta[key].append(_scalar(item[2:]))
            continue
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        key = k.strip()
        meta[key] = _scalar(v) if v.strip() else _PENDING
    return {k: ("" if v is _PENDING else v) for k, v in meta.items()}


def dump(meta: dict, body: str) -> str:
    lines = ["---"]
    for k, v in meta.items():
        lines.append(f"{k}: {json.dumps(v, ensure_ascii=False)}")
    lines.append("---")
    return "\n".join(lines) + "\n" + body.lstrip("\n")
