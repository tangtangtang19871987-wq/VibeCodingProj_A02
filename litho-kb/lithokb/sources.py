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


_META_RO: dict[str, tuple] = {}
_NAV_CACHE: dict[tuple, bool] = {}


def meta_stamp(kb: KB):
    try:
        st = _meta_path(kb).stat()
        return (st.st_mtime_ns, st.st_size)
    except FileNotFoundError:
        return None


def meta_ro(kb: KB) -> dict:
    """Read-only, cached view of meta/sources.json (re-parsed only when the file changes).
    Never mutate the result — writers use load_meta()."""
    sig = meta_stamp(kb)
    if sig is None:
        return {}
    key = str(_meta_path(kb))
    ent = _META_RO.get(key)
    if ent and ent[0] == sig:
        return ent[1]
    m = json.loads(_meta_path(kb).read_text("utf-8"))
    _META_RO[key] = (sig, m)
    return m


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
    meta = meta_ro(kb).get(rel)
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
    rec = meta_ro(kb).get(rel)
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
    meta = meta_ro(kb)
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
    meta = meta_ro(kb)
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


def _shingles(text: str, k: int = 4) -> set:
    _, body, _ = fm.split(text)
    body = re.sub(r"\]\([^)]*\)", "]", body)  # link targets are layout, not content
    t = "".join(ch for ch in body.lower() if ch.isalnum())  # compare words only: no punctuation / markup / spaces
    return {t[i:i + k] for i in range(0, max(0, len(t) - k + 1))}


def near_duplicates(kb: KB, threshold: float = 0.6, containment: float = 0.8, max_docs: int = 3000) -> list[dict]:
    """Pairs of live Markdown documents whose content largely overlaps (character 4-gram Jaccard).
    Typical cause: the same page exported twice (e.g. index.html / index1.html / index2.html)."""
    paths = list_md(kb)
    if len(paths) > max_docs:
        return []
    sh = {p: _shingles((kb.sources / p).read_text("utf-8", errors="replace")) for p in paths}
    out = []
    for i, a in enumerate(paths):
        for b in paths[i + 1:]:
            sa, sb = sh[a], sh[b]
            if not sa or not sb:
                continue
            inter = len(sa & sb)
            j = inter / len(sa | sb)
            contain = inter / min(len(sa), len(sb))  # one document largely contained in the other
            if j >= threshold or (contain >= containment and min(len(sa), len(sb)) >= 200):
                out.append({"a": a, "b": b, "similarity": round(j, 2), "containment": round(contain, 2)})
    return sorted(out, key=lambda x: -x["similarity"])


_TITLE_CACHE: dict[tuple, str] = {}


def doc_titles(kb: KB, paths) -> dict[str, str]:
    """Human titles of source documents (frontmatter title or first H1), cached by content hash.
    Readers must see document names linked to the original, never bare file paths."""
    meta = meta_ro(kb)
    out = {}
    for p in {p for p in paths if p}:
        rec = meta.get(p)
        if not rec:
            continue
        key = (p, rec["sha256"])
        if key not in _TITLE_CACHE:
            try:
                _TITLE_CACHE[key] = title_of(read_text(kb, p), posixpath.basename(p))
            except SourceError:
                _TITLE_CACHE[key] = posixpath.basename(p)
        out[p] = _TITLE_CACHE[key]
    return out


# ---- per-document processing policy -------------------------------------------------
POLICIES = ("compile", "reference", "exclude")
POLICY_ZH = {"compile": "compile into knowledge", "reference": "reference only (browsable and navigable, not compiled)",
             "exclude": "exclude (not compiled, not used in Q&A)"}


def looks_like_navigation(text: str) -> bool:
    """Index / table-of-contents / link-list pages carry structure, not knowledge."""
    _, body, _ = fm.split(text)
    lines = [ln.strip() for ln in body.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    if not lines:
        return True
    linky = sum(1 for ln in lines if _LINK_RE.search(ln) and len(_LINK_RE.sub("", ln).strip(" -*0-9.\u3001:\uff1a|")) < 60)
    prose = sum(len(ln) for ln in lines if not _LINK_RE.search(ln))
    if linky >= 5 and linky / len(lines) >= 0.5 and prose < 1500:
        return True
    # card-style tables of contents: many links to sibling documents, little prose per link
    internal = {h.split("#")[0] for _, h in _LINK_RE.findall(body)
                if "://" not in h and h.split("#")[0].lower().endswith(MD_EXT)}
    return len(internal) >= 8 and prose / len(internal) < 120


def policy_of(kb: KB, rel: str, meta: dict | None = None) -> dict:
    """{"policy": compile|reference|exclude, "auto": bool, "reason": str}. An explicit choice by a
    person always wins; otherwise navigation-like pages default to 'reference'."""
    rec = (meta or meta_ro(kb)).get(rel, {})
    if rec.get("policy") in POLICIES:
        return {"policy": rec["policy"], "auto": False, "reason": rec.get("policy_note", ""), "by": rec.get("policy_by", "")}
    if rel.lower().endswith(MD_EXT):
        key = (str(kb.root), rel, rec.get("sha256"))
        if key not in _NAV_CACHE:  # content-addressed: a document is classified once per version
            try:
                _NAV_CACHE[key] = looks_like_navigation(read_text(kb, rel))
            except SourceError:
                _NAV_CACHE[key] = False
        if _NAV_CACHE[key]:
            return {"policy": "reference", "auto": True, "reason": "auto-detected as a table-of-contents / navigation page"}
    return {"policy": "compile", "auto": True, "reason": ""}


def set_policy(kb: KB, actor: str, rel: str, policy: str, note: str = "") -> dict:
    rel = clean_path(rel)
    if policy not in POLICIES + ("auto",):
        raise SourceError(f"policy must be one of {POLICIES + ('auto',)}")
    with LOCK:
        meta = load_meta(kb)
        if rel not in meta:
            raise SourceError(f"no source {rel}")
        if policy == "auto":
            for k in ("policy", "policy_note", "policy_by"):
                meta[rel].pop(k, None)
        else:
            meta[rel].update(policy=policy, policy_note=note, policy_by=actor)
        _save_meta(kb, meta)
    kb.event(actor, "source.policy", rel, policy=policy, note=note)
    return policy_of(kb, rel)


def list_md_by_policy(kb: KB, *policies: str) -> list[str]:
    meta = meta_ro(kb)
    return [p for p in list_md(kb) if policy_of(kb, p, meta)["policy"] in policies]
