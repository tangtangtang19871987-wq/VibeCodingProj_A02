"""Entity graph extraction — instances and typed relations, guided by the approved ontology.

Per document (LangGraph GENERATE flow, one call per document or per outline section group):
  input   the approved ontology (entity types with definitions, relations with domain → range),
          the document with line numbers, and instance names already extracted elsewhere
          (so the same thing gets the same name across documents)
  output  entities  [{name, type, aliases, evidence:{lines, quote}}]
          relations [{subject, predicate, object, evidence:{lines, quote}}]
  checks  type and predicate must be in the ontology; names must occur verbatim in the document;
          evidence quotes are verified against the cited lines; subject/object types must satisfy
          the relation's domain → range — violations are dropped and reported, never silently kept.

Cached per (document sha256, ontology fingerprint) in compiled/entities/ → incremental: a document
is re-extracted only when it changes or when the approved ontology changes.
"""
from __future__ import annotations

import hashlib
import json

from . import doctree
from . import graph as G
from . import sources as S
from .cards import verify_evidence
from .flows import generate
from .store import KB, atomic_write, now

PROMPT_VERSION = "lkb-extract/1"

SYSTEM = """[[LKB:EXTRACT]]
You extract a knowledge graph from one technical document, strictly following the ONTOLOGY below.
- entities: named instances of the ontology's entity types that the document actually discusses. Write each name
  exactly as in the text (it is machine-checked); prefer a name from KNOWN NAMES when the document refers to the
  same thing. Give the type id and one evidence quote.
- relations: typed links between those instances, only with the ontology's relation ids, and only when the
  subject/object types fit the relation's domain -> range. Each relation cites one evidence quote that states it.
- evidence: {"lines":"a-b","quote":"..."} — the quote copied verbatim (<= 160 chars) from those numbered lines,
  without the "NNNN|" prefix.
Skip generic words; extract what a reader would look up. Do not invent anything the document does not say.
Return exactly one JSON object in a ```json block:
{"entities":[{"name":"...","type":"...","aliases":[],"evidence":{"lines":"12-13","quote":"..."}}],
 "relations":[{"subject":"...","predicate":"...","object":"...","evidence":{"lines":"20","quote":"..."}}]}
Think briefly."""


def _dir(kb: KB):
    return kb.root / "compiled" / "entities"


def fingerprint(onto: dict) -> str:
    j = json.dumps({"t": sorted(onto["entity_types"].items()),
                    "r": sorted((k, sorted(v["domain"]), sorted(v["range"])) for k, v in onto["entity_relations"].items())},
                   ensure_ascii=False)
    return hashlib.sha256(j.encode()).hexdigest()[:10]


def _cache(kb: KB, sha: str, fp: str):
    return _dir(kb) / f"{sha[:24]}-{fp}.json"


def load_all(kb: KB) -> dict[str, dict]:
    """path → extraction record, for the current documents and the current ontology."""
    onto = G.ontology(kb)
    fp = fingerprint(onto)
    meta = S.meta_ro(kb)
    out = {}
    for p in S.list_md_by_policy(kb, "compile", "reference"):
        f = _cache(kb, meta[p]["sha256"], fp)
        if f.exists():
            try:
                out[p] = json.loads(f.read_text("utf-8"))
            except json.JSONDecodeError:
                pass
    return out


def _ontology_text(onto: dict) -> str:
    lines = ["Entity types:"]
    for t, label in onto["entity_types"].items():
        d = onto["type_defs"].get(t, "")
        lines.append(f"- `{t}` {label}: {d}")
    lines.append("Relations (subject type -> object type):")
    for r, v in onto["entity_relations"].items():
        lines.append(f"- `{r}`: {'|'.join(sorted(v['domain']))} -> {'|'.join(sorted(v['range']))} ({v['label']}: {v.get('definition', '')})")
    return "\n".join(lines)


def _validate(raw: dict, kb: KB, path: str, text: str, onto: dict, known: dict, findings: list) -> dict:
    hay = G._key(text)
    cache = {path: text}
    types, rels = onto["entity_types"], onto["entity_relations"]
    ents: dict[str, dict] = {}
    dropped = {"type": 0, "not_verbatim": 0, "predicate": 0, "endpoint": 0, "domain_range": 0, "evidence": 0}

    def ev(e):
        if not isinstance(e, dict):
            return None
        r = verify_evidence(kb, {"path": path, "lines": str(e.get("lines", "")), "quote": str(e.get("quote", ""))[:300]}, cache)
        return {"lines": r.get("found_lines") or r.get("lines"), "quote": r["quote"], "check": r.get("check")}

    for e in raw.get("entities") or []:
        if not isinstance(e, dict) or not str(e.get("name", "")).strip():
            continue
        name, typ = str(e["name"]).strip()[:80], str(e.get("type", "")).strip()
        if typ not in types:
            dropped["type"] += 1
            continue
        if G._key(name) not in hay:
            dropped["not_verbatim"] += 1
            continue
        k = G._key(name)
        if k in ents:
            continue
        evd = ev(e.get("evidence"))
        ents[k] = {"name": name, "type": typ, "aliases": [str(a)[:80] for a in e.get("aliases") or [] if G._key(str(a)) in hay][:5],
                   "evidence": evd}
    names = {**{k: v["type"] for k, v in known.items()}, **{k: v["type"] for k, v in ents.items()}}
    out_rels = []
    for r in raw.get("relations") or []:
        if not isinstance(r, dict):
            continue
        pred = str(r.get("predicate", "")).strip()
        if pred not in rels:
            dropped["predicate"] += 1
            continue
        s, o = G._key(str(r.get("subject", ""))), G._key(str(r.get("object", "")))
        if s not in names or o not in names or s == o:
            dropped["endpoint"] += 1
            continue
        dom, rng = rels[pred]["domain"], rels[pred]["range"]
        if ("*" not in dom and names[s] not in dom) or ("*" not in rng and names[o] not in rng):
            dropped["domain_range"] += 1
            continue
        evd = ev(r.get("evidence"))
        if not evd or evd["check"] not in ("exact", "moved", "elided"):
            dropped["evidence"] += 1
            continue
        out_rels.append({"subject": s, "predicate": pred, "object": o, "evidence": evd})
    if any(dropped.values()):
        findings.append({"path": path, "dropped": {k: v for k, v in dropped.items() if v}})
    return {"entities": list(ents.values()), "relations": out_rels, "dropped": dropped}


class Extractor:
    def __init__(self, kb: KB, comp):
        self.kb, self.comp = kb, comp

    def status(self) -> dict:
        onto = G.ontology(self.kb)
        fp = fingerprint(onto)
        meta = S.meta_ro(self.kb)
        docs = S.list_md_by_policy(self.kb, "compile")
        done = [p for p in docs if _cache(self.kb, meta[p]["sha256"], fp).exists()]
        recs = load_all(self.kb)
        return {"ontology": fp, "documents": len(docs), "extracted": len(done), "pending": sorted(set(docs) - set(done)),
                "entities": sum(len(r["entities"]) for r in recs.values()),
                "relations": sum(len(r["relations"]) for r in recs.values())}

    def run(self, actor: str, cfg: dict, paths: list[str] | None = None, force: bool = False, limit: int = 0) -> dict:
        from .compiler import new_run_id
        from .pageindex import parse_obj
        onto = G.ontology(self.kb)
        if not onto["entity_relations"]:
            raise ValueError("the approved ontology has no entity relations — run the ontology loop first")
        fp = fingerprint(onto)
        meta = S.meta_ro(self.kb)
        todo = paths or [p for p in S.list_md_by_policy(self.kb, "compile")
                         if force or not _cache(self.kb, meta[p]["sha256"], fp).exists()]
        if limit:
            todo = todo[:limit]  # start small: pilot on a few documents first
        known: dict[str, dict] = {}
        for r in load_all(self.kb).values():
            for e in r["entities"]:
                known.setdefault(G._key(e["name"]), e)
        report = {"documents": len(todo), "extracted": [], "failed": [], "cost_usd": 0.0, "ontology": fp}
        budget = int(self.kb.config.get("extract", {}).get("max_doc_chars", 40000))
        for p in todo:
            rid = new_run_id()
            run = {"id": rid, "kind": "extract", "by": actor, "started": now(), "status": "running", "backend": cfg["backend"],
                   "prompt_version": PROMPT_VERSION, "sources": [p], "source_shas": {p: meta[p]["sha256"]},
                   "timeline": [], "ontology": fp, "findings": []}
            try:
                text = S.read_text(self.kb, p)
                lines = text.splitlines()
                tree = doctree.build(text, meta[p]["sha256"])
                parts = doctree.sections(tree, budget)
                ents, rels = [], []
                for k, (a, b, titles) in enumerate(parts, 1):
                    numbered = "\n".join(f"{i:5d}|{lines[i - 1]}" for i in range(a, min(b, len(lines)) + 1))
                    names = sorted({v["name"] for v in known.values()} | {e["name"] for e in ents})[:150]
                    user = (f"# ONTOLOGY\n{_ontology_text(onto)}\n\n# KNOWN NAMES\n" + (", ".join(names) or "(none)") +
                            f'\n\n<document path="{p}" lines="{a}-{b}">\n{numbered}\n</document>')
                    data, res, _ = generate(
                        comp=self.comp, run=run, cfg=cfg, system=SYSTEM, user=user, max_attempts=2, graph="extract",
                        prefix="" if len(parts) == 1 else f"part{k}-",
                        check=lambda r_: _validate(parse_obj(r_.text), self.kb, p, text, onto, known, run["findings"]),
                        correction=lambda e: f"\n\n# Correction\nYour previous answer was not usable ({e[:160]}). "
                                             "Return the JSON object exactly as specified.")
                    for e in data["entities"]:
                        if all(G._key(e["name"]) != G._key(x["name"]) for x in ents):
                            ents.append(e)
                            known.setdefault(G._key(e["name"]), e)
                    rels += data["relations"]
                    run["model"] = res.model
                rec = {"path": p, "sha": meta[p]["sha256"], "ontology": fp, "run": rid, "model": run.get("model"),
                       "prompt_version": PROMPT_VERSION, "at": now(), "entities": ents, "relations": rels,
                       "findings": run["findings"]}
                atomic_write(_cache(self.kb, meta[p]["sha256"], fp), json.dumps(rec, ensure_ascii=False, indent=1))
                run.update(status="done", entities=len(ents), relations=len(rels))
                report["extracted"].append({"path": p, "entities": len(ents), "relations": len(rels)})
            except Exception as e:  # noqa: BLE001 — one document never stops the batch
                run.update(status="failed", error=f"{type(e).__name__}: {e}")
                report["failed"].append({"path": p, "error": run["error"]})
            run["finished"] = now()
            self.comp._save_run(run)
            report["cost_usd"] += run.get("cost_usd", 0) or 0
        report["cost_usd"] = round(report["cost_usd"], 6)
        self.kb.event(actor, "extract.run", "", documents=len(todo), failed=len(report["failed"]), ontology=fp)
        return report


__all__ = ["Extractor", "load_all", "fingerprint", "SYSTEM", "PROMPT_VERSION"]
