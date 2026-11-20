"""Layer 0 — original Markdown documents.

* Kept verbatim; never rewritten by the system. Re-uploading a changed file
  archives the previous bytes under history/ and bumps the version.
* Provenance per file: who uploaded each version, when, sha256, size.
* Navigation respects the author's own indexing: a folder's SUMMARY.md /
  index.md / README.md / _index.md link order, then frontmatter
  weight / nav_order / sidebar_position, then title. Relative links between
  documents keep working because paths are preserved exactly.
"""
from __future__ import annotations

import base64
import json
import posixpath
import re
from pathlib import Path

from . import fm
from . import html2md
from .store import KB, LOCK, atomic_write, now, sha256

MD_EXT = (".md", ".markdown", ".mdx")
HTML_EXT = (".html", ".htm")
ASSET_EXT = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".pdf", ".csv", ".txt", ".json", ".yaml", ".yml")
INDEX_NAMES = ("SUMMARY.md", "index.md", "README.md", "_index.md", "readme.md")
MAX_FILE = 20 * 1024 * 1024
_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
_H1_RE = re.compile(r"^#\s+(.+?)\s*#*\s*$", re.M)


class SourceError(Exception):
    pass


def clean_path(p: str) -> str:
    """Normalise a user-supplied relative path; reject anything escaping the root."""
    p = p.replace("\\", "/").strip().lstrip("/")
    norm = posixpath.normpath(p)
    if norm in ("", ".") or norm.startswith("..") or "/../" in f"/{norm}/":
        raise SourceError(f"bad path: {p!r}")
    parts = norm.split("/")
    if any(x.startswith(".") for x in parts):
        raise SourceError(f"hidden path not allowed: {p!r}")
    return norm


def _meta_path(kb: KB) -> Path:
    return kb.meta / "sources.json"


def load_meta(kb: KB) -> dict:
    p = _meta_path(kb)
    return json.loads(p.read_text("utf-8")) if p.exists() else {}


def _save_meta(kb: KB, meta: dict) -> None:
    atomic_write(_meta_path(kb), json.dumps(meta, ensure_ascii=False, indent=1, sort_keys=True))


def put(kb: KB, actor: str, items: list[dict], prefix: str = "", note: str = "") -> list[dict]:
    """items: [{path, text}|{path, b64}]. Returns per-file results."""
    results = []
    with LOCK:
        meta = load_meta(kb)
        for it in items:
            rel = clean_path(posixpath.join(prefix, it["path"]) if prefix else it["path"])
            if not rel.lower().endswith(MD_EXT + ASSET_EXT + HTML_EXT):
                results.append({"path": rel, "status": "skipped", "reason": "unsupported type"})
                continue
            data = it["text"].encode("utf-8") if "text" in it else base64.b64decode(it.get("b64", ""))
            if len(data) > MAX_FILE:
                results.append({"path": rel, "status": "skipped", "reason": "too large"})
                continue
            digest = sha256(data)
            rec = meta.get(rel)
            dest = kb.sources / rel
            if rec and rec.get("deleted") is not True and rec["sha256"] == digest:
                results.append({"path": rel, "status": "unchanged", "version": rec["version"]})
                continue
            if rec and dest.exists():  # archive previous version, verbatim
                atomic_write(kb.history / f"{rel}@{rec['version']}", dest.read_bytes())
            version = (rec["version"] + 1) if rec else 1
            atomic_write(dest, data)
            entry = {"version": version, "sha256": digest, "size": len(data), "by": actor, "at": now(), "note": note}
            hist = (rec or {}).get("history", [])
            hist.append(entry)
            meta[rel] = {**entry, "first_by": (rec or {}).get("first_by", actor),
                         "first_at": (rec or {}).get("first_at", entry["at"]), "history": hist, "deleted": False}
            results.append({"path": rel, "status": "updated" if rec else "added", "version": version})
        # HTML originals: keep verbatim (above) and derive a Markdown rendition to compile
        explicit = {clean_path(posixpath.join(prefix, it["path"]) if prefix else it["path"]) for it in items}
        for r in list(results):
            rel = r["path"]
            if not rel.lower().endswith(HTML_EXT) or r["status"] == "skipped":
                continue
            md_rel = rel.rsplit(".", 1)[0] + ".md"
            if md_rel in explicit and not meta.get(md_rel, {}).get("derived_from"):
                r["note"] = f"{md_rel} uploaded explicitly; no conversion"
                continue
            if meta.get(md_rel) and not meta[md_rel].get("derived_from") and not meta[md_rel].get("deleted"):
                r["note"] = f"{md_rel} is an authored document; not overwritten by conversion"
                continue
            html = (kb.sources / rel).read_bytes()
            md = html2md.convert(html.decode("utf-8", errors="replace"), source_name=posixpath.basename(rel),
                                 source_sha=sha256(html)).encode("utf-8")
            digest = sha256(md)
            mrec = meta.get(md_rel)
            if mrec and not mrec.get("deleted") and mrec["sha256"] == digest:
                r["derived"] = {"path": md_rel, "status": "unchanged"}
                continue
            dest = kb.sources / md_rel
            if mrec and dest.exists():
                atomic_write(kb.history / f"{md_rel}@{mrec['version']}", dest.read_bytes())
            version = (mrec["version"] + 1) if mrec else 1
            atomic_write(dest, md)
            entry = {"version": version, "sha256": digest, "size": len(md), "by": actor, "at": now(),
                     "note": f"converted from {posixpath.basename(rel)} v{meta[rel]['version']} ({html2md.CONVERTER})"}
            hist = (mrec or {}).get("history", [])
            hist.append(entry)
            meta[md_rel] = {**entry, "first_by": (mrec or {}).get("first_by", actor),
                            "first_at": (mrec or {}).get("first_at", entry["at"]), "history": hist, "deleted": False,
                            "derived_from": rel, "converter": html2md.CONVERTER}
            meta[rel]["rendition"] = md_rel
            r["derived"] = {"path": md_rel, "status": "updated" if mrec else "added", "version": version}
        _save_meta(kb, meta)
    changed = [r["path"] for r in results if r["status"] in ("added", "updated")] + \
              [r["derived"]["path"] for r in results if r.get("derived", {}).get("status") in ("added", "updated")]
    kb.event(actor, "source.upload", prefix or "/", files=len(items), changed=changed[:200], note=note)
    return results


def put_dir(kb: KB, actor: str, directory: str, prefix: str = "", note: str = "") -> list[dict]:
    base = Path(directory).resolve()
    items = []
    for f in sorted(base.rglob("*")):
        if f.is_file() and not any(p.startswith(".") for p in f.relative_to(base).parts) \
                and f.name.lower().endswith(MD_EXT + ASSET_EXT + HTML_EXT):
            items.append({"path": f.relative_to(base).as_posix(), "b64": base64.b64encode(f.read_bytes()).decode()})
    if base.is_file():
        items = [{"path": base.name, "b64": base64.b64encode(base.read_bytes()).decode()}]
    return put(kb, actor, items, prefix=prefix, note=note)


def remove(kb: KB, actor: str, rel: str) -> None:
    """Retire a source (archived, never destroyed). Cards citing it become 'stale'."""
    rel = clean_path(rel)
    with LOCK:
        meta = load_meta(kb)
        rec = meta.get(rel)
        dest = kb.sources / rel
        if not rec or not dest.exists():
            raise SourceError(f"no source {rel}")
        atomic_write(kb.history / f"{rel}@{rec['version']}", dest.read_bytes())
        dest.unlink()
        rec["deleted"] = True
        rec["deleted_by"], rec["deleted_at"] = actor, now()
        _save_meta(kb, meta)
    kb.event(actor, "source.retire", rel)


def read(kb: KB, rel: str, version: int | None = None) -> bytes:
    rel = clean_path(rel)
    meta = load_meta(kb).get(rel)
    if version and meta and version != meta["version"]:
        p = kb.history / f"{rel}@{version}"
    else:
        p = kb.sources / rel
    if not p.exists():
        raise SourceError(f"not found: {rel}")
    return p.read_bytes()


def read_text(kb: KB, rel: str, version: int | None = None) -> str:
    return read(kb, rel, version).decode("utf-8", errors="replace")


def version_by_sha(kb: KB, rel: str, sha: str) -> int | None:
    rec = load_meta(kb).get(rel)
    for h in (rec or {}).get("history", []):
        if h["sha256"] == sha:
            return h["version"]
    return None


def title_of(text: str, fallback: str) -> str:
    meta, body, _ = fm.split(text)
    if meta.get("title"):
        return str(meta["title"])
    m = _H1_RE.search(body)
    return m.group(1).strip() if m else fallback


def list_md(kb: KB) -> list[str]:
    meta = load_meta(kb)
    return sorted(p for p, r in meta.items() if not r.get("deleted") and p.lower().endswith(MD_EXT))


# ---- hierarchical navigation that respects the author's own index -------------
def _index_order(kb: KB, folder: str, names: set[str]) -> list[str]:
    for idx in INDEX_NAMES:
        p = kb.sources / folder / idx if folder else kb.sources / idx
        if p.exists():
            order = []
            for _, href in _LINK_RE.findall(p.read_text("utf-8", errors="replace")):
                href = href.split("#")[0]
                if not href or "://" in href:
                    continue
                target = posixpath.normpath(posixpath.join(folder, href)) if folder else posixpath.normpath(href)
                first = target[len(folder) + 1:].split("/")[0] if folder else target.split("/")[0]
                if first in names and first not in order:
                    order.append(first)
            return order
    return []


def tree(kb: KB) -> dict:
    meta = load_meta(kb)
    live = {p: r for p, r in meta.items() if not r.get("deleted")
            and not (r.get("rendition") and not meta.get(r["rendition"], {}).get("deleted"))}
    root: dict = {"name": "", "path": "", "type": "dir", "children": {}}
    for p in live:
        node = root
        parts = p.split("/")
        for i, part in enumerate(parts[:-1]):
            node = node["children"].setdefault(part, {"name": part, "path": "/".join(parts[: i + 1]),
                                                      "type": "dir", "children": {}})
        node["children"][parts[-1]] = {"name": parts[-1], "path": p, "type": "file"}

    def finish(node: dict) -> dict:
        kids = node["children"]
        weights = {}
        for name, ch in kids.items():
            if ch["type"] == "file" and name.lower().endswith(MD_EXT):
                text = (kb.sources / ch["path"]).read_text("utf-8", errors="replace")
                m, _, _ = fm.split(text)
                ch["title"] = title_of(text, name)
                for k in ("weight", "nav_order", "sidebar_position", "order"):
                    if isinstance(m.get(k), (int, float)):
                        weights[name] = m[k]
                rec = live[ch["path"]]
                ch.update(version=rec["version"], by=rec["by"], at=rec["at"])
            elif ch["type"] == "dir":
                finish(ch)
                ch["title"] = ch.get("title") or name
        index_name = next((n for n in INDEX_NAMES if n in kids), None)
        order = _index_order(kb, node["path"], set(kids))
        rank = {n: i for i, n in enumerate(order)}

        def key(n):
            ch = kids[n]
            return (0 if n == index_name else 1, rank.get(n, 10_000), weights.get(n, 10_000),
                    0 if ch["type"] == "dir" else 1, str(ch.get("title", n)).lower())

        node["index"] = kids[index_name]["path"] if index_name else None
        if index_name and node["path"]:
            node["title"] = kids[index_name].get("title", node["name"])
        node["children"] = [kids[n] for n in sorted(kids, key=key)]
        return node

    return finish(root)
