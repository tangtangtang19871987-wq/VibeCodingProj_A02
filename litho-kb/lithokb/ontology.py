"""Ontology loop — gather evidence → model proposes → people review, refine, approve.

    topics (representative sections) ─┐
    golden questions (what must be     ├→ propose (LLM, GENERATE flow) → proposal (cited, checked)
      answered) ──────────────────────┘        ↑                           │
                                               └──── refine (feedback) ────┤
                                                                           ↓
                                        approve (admin, comment) → new SCHEMA.md version (section 8)

* Query first, be selective: the model sees the golden questions and must say which question
  needs each entity / relation type; types no question needs are left out.
* Every proposed type and relation cites evidence — a verbatim quote from a representative
  section — which is mechanically verified like card evidence.
* A proposal is a full candidate SCHEMA.md (only the ontology section changes) with a diff; it
  becomes effective only when an admin approves it, as a new, versioned schema.
* OWL/Turtle export of the current ontology, and Turtle import (which creates a proposal).

Files: ontology/proposals/<id>.json
"""
from __future__ import annotations

import difflib
import json
import re
import uuid

from . import graph as G
from . import pageindex as PI
from . import schema as SC
from . import sources as S
from .cards import verify_evidence
from .flows import generate
from .store import KB, LOCK, atomic_write, now

PROMPT_VERSION = "lkb-ontology/1"

SYSTEM = """[[LKB:ONTOLOGY]]
You design the domain ontology of a knowledge graph built from technical documents. The graph exists to answer
the GOLDEN QUESTIONS listed below; design only what those questions need (be selective). Entity types are kinds of
things that appear in the documents as named instances (e.g. methods, representations, algorithms, cost terms,
constraints, steps, tools, equipment); entity relations are typed links between instances, with domain → range.
Evidence: for every entity type and every relation give 1-2 verbatim quotes (<= 120 chars, copied exactly from
the section text, without the line-number prefix) from the EVIDENCE sections, with the section handle.
Rules: ids are snake_case English; labels in English; definitions one sentence; examples are instance names as
written in the documents. 5-12 entity types, 4-14 relations. List for each type/relation the question ids it
serves. Under "uncovered" list questions the documents cannot support, with why.
Return exactly one JSON object in a ```json block:
{"entity_types":[{"id":"mask_representation","label":"Mask representation","definition":"...","examples":["..."],
   "evidence":[{"handle":"D3.n4","quote":"..."}],"questions":["q01"]}],
 "entity_relations":[{"id":"optimizes","label":"Optimizes","domain":["optimizer"],"range":["cost_term"],
   "definition":"...","evidence":[{"handle":"D3.n4","quote":"..."}],"questions":["q03"]}],
 "uncovered":[{"question":"q05","why":"..."}],"notes":"..."}
Think briefly."""


def _dir(kb: KB):
    return kb.root / "ontology" / "proposals"


def proposals(kb: KB) -> list[dict]:
    d = _dir(kb)
    out = []
    for p in sorted(d.glob("*.json"), reverse=True) if d.exists() else []:
        r = json.loads(p.read_text("utf-8"))
        out.append({k: r.get(k) for k in ("id", "status", "by", "at", "origin", "parent", "schema_version",
                                         "summary", "decided_by", "decided_at")})
    return out


def get(kb: KB, pid: str) -> dict:
    if not re.fullmatch(r"onto-[0-9a-f]{8}", pid):
        raise ValueError("bad proposal id")
    return json.loads((_dir(kb) / f"{pid}.json").read_text("utf-8"))


def _save(kb: KB, rec: dict) -> None:
    atomic_write(_dir(kb) / f"{rec['id']}.json", json.dumps(rec, ensure_ascii=False, indent=1))


# ---- rendering: ontology dict ↔ SCHEMA section 8 ----------------------------------------------
def render_section(types: list[dict], rels: list[dict], constraints_block: str) -> str:
    lines = ["## 8. Graph ontology (entity types and relation constraints)",
             "Entity types: kinds of named things in the sources; the extraction pass finds their instances "
             "(names must appear verbatim in the source):"]
    for t in types:
        ex = f" (e.g. {', '.join(t.get('examples', [])[:4])})" if t.get("examples") else ""
        lines.append(f"- `{t['id']}` {t['label']}: {t.get('definition', '').rstrip('.')}{ex}")
    if rels:
        lines.append("Entity relations (subject type → object type — meaning):")
        for r in rels:
            lines.append(f"- `{r['id']}` {r['label']}: {'|'.join(r['domain'])} → {'|'.join(r['range'])} — {r.get('definition', '')}")
    if constraints_block.strip():
        lines.append(constraints_block.strip())
    return "\n".join(lines) + "\n"


def _constraints_block(text: str) -> str:
    m = re.search(r"^#+[^\n]*(?:\u672c\u4f53|ontology)[^\n]*\n(.*?)(?=^#{1,2} |\Z)", text, re.M | re.S | re.I)
    if not m:
        return ""
    part = m.group(1)
    cm = re.search(r"^[^\n]*(?:\u5173\u7cfb\u7ea6\u675f|relation constraints)[^\n]*$", part, re.I | re.M)
    return part[cm.start():].strip() if cm else ""


def replace_section(text: str, section: str) -> str:
    m = re.search(r"^#+[^\n]*(?:\u672c\u4f53|ontology)[^\n]*\n(.*?)(?=^#{1,2} |\Z)", text, re.M | re.S | re.I)
    if not m:
        return text.rstrip("\n") + "\n\n" + section
    return text[:m.start()] + section + ("\n" if text[m.end():].strip() else "") + text[m.end():]


# ---- evidence for the model ---------------------------------------------------------------------
def _evidence_block(kb: KB, budget: int) -> tuple[str, dict]:
    """Representative sections of every leaf topic (text bounded), with handles → (path, a, b)."""
    from .topics import leaf_topics, load as load_topics
    t = load_topics(kb)
    meta = S.meta_ro(kb)
    if not t:
        raise ValueError("build the topic graph first (lkb topics build): the ontology is proposed from topic evidence")
    leaves = leaf_topics(t)
    per = max(400, budget // max(1, sum(len(x["representative"]) for x in leaves)))
    hmap, parts, n = {}, [], 0
    texts: dict = {}
    for x in leaves:
        parts.append(f"## Theme: {x['title']} — {x.get('summary', '')}")
        for m in x["representative"]:
            path, nid = m[2:].split("#")
            nd = PI.find(PI.doc_tree(kb, path, meta), nid)
            if not nd:
                continue
            n += 1
            h = f"E{n}"
            a, b = PI.own_lines(nd)
            if path not in texts:
                texts[path] = S.read_text(kb, path).splitlines()
            body, size = [], 0
            for i in range(a, b + 1):
                ln = texts[path][i - 1]
                if size + len(ln) > per:
                    break
                body.append(ln)
                size += len(ln)
            end = a + len(body) - 1 if body else a
            hmap[h] = (path, a, max(a, end))
            parts.append(f"<section handle=\"{h}\" title=\"{nd['title']}\">\n" + "\n".join(body) + "\n</section>")
    return "\n".join(parts), hmap


def _validate(raw: dict, hmap: dict, kb: KB, qids: set) -> tuple[dict, dict]:
    cache: dict = {}
    checks = {"verified": 0, "unverified": 0}

    def ev(items):
        out = []
        for e in items or []:
            if not isinstance(e, dict) or e.get("handle") not in hmap:
                continue
            path, a, b = hmap[e["handle"]]
            r = verify_evidence(kb, {"path": path, "lines": f"{a}-{b}", "quote": str(e.get("quote", ""))[:300]}, cache)
            ok = r.get("check") in ("exact", "moved", "elided")
            checks["verified" if ok else "unverified"] += 1
            out.append({"path": path, "lines": r.get("found_lines") or f"{a}-{b}", "quote": r["quote"], "check": r.get("check")})
        return out

    sid = lambda x: re.sub(r"[^a-z0-9_]+", "_", str(x).lower()).strip("_")  # noqa: E731
    types, seen = [], set()
    for t in raw.get("entity_types") or []:
        if not isinstance(t, dict) or not sid(t.get("id")) or sid(t.get("id")) in seen:
            continue
        seen.add(sid(t["id"]))
        types.append({"id": sid(t["id"]), "label": str(t.get("label") or t["id"])[:60],
                      "definition": str(t.get("definition", ""))[:240], "examples": [str(x)[:60] for x in t.get("examples", [])][:6],
                      "evidence": ev(t.get("evidence")), "questions": [q for q in t.get("questions", []) if q in qids]})
    rels, rseen = [], set()
    tids = {t["id"] for t in types} | {"*"}
    for r in raw.get("entity_relations") or []:
        if not isinstance(r, dict) or not sid(r.get("id")) or sid(r.get("id")) in rseen:
            continue
        dom = [sid(x) for x in r.get("domain", []) if sid(x) in tids] or []
        rng = [sid(x) for x in r.get("range", []) if sid(x) in tids] or []
        if not dom or not rng:
            continue  # relations must connect declared types
        rseen.add(sid(r["id"]))
        rels.append({"id": sid(r["id"]), "label": str(r.get("label") or r["id"])[:60], "domain": dom, "range": rng,
                     "definition": str(r.get("definition", ""))[:240], "evidence": ev(r.get("evidence")),
                     "questions": [q for q in r.get("questions", []) if q in qids]})
    if len(types) < 2:
        raise ValueError("fewer than two usable entity types")
    served = {q for x in types + rels for q in x["questions"]}
    checks["questions_served"] = sorted(served)
    checks["questions_unserved"] = sorted(qids - served)
    checks["types_without_evidence"] = [t["id"] for t in types if not any(e["check"] in ("exact", "moved", "elided") for e in t["evidence"])]
    return {"entity_types": types, "entity_relations": rels,
            "uncovered": [u for u in raw.get("uncovered") or [] if isinstance(u, dict)][:20],
            "notes": str(raw.get("notes", ""))[:600]}, checks


class OntologyLoop:
    def __init__(self, kb: KB, comp):
        self.kb, self.comp = kb, comp

    def propose(self, actor: str, cfg: dict, parent: str | None = None, feedback: str = "") -> dict:
        from . import evalset as E
        from .compiler import new_run_id
        from .pageindex import parse_obj
        qs = E.load(self.kb)
        evidence, hmap = _evidence_block(self.kb, int(self.kb.config.get("ontology", {}).get("evidence_chars", 40000)))
        cur = SC.current(self.kb)
        onto = G.ontology(self.kb)
        prev = get(self.kb, parent) if parent else None
        user = ("# GOLDEN QUESTIONS\n" + ("\n".join(f"{q['id']}: {q['question']}" for q in qs) or "(none — propose a general ontology)") +
                "\n\n# CURRENT ONTOLOGY\n" + json.dumps({"entity_types": onto["entity_types"],
                                                        "entity_relations": {k: {**v, "domain": sorted(v["domain"]), "range": sorted(v["range"])}
                                                                             for k, v in onto["entity_relations"].items()}},
                                                       ensure_ascii=False) +
                (f"\n\n# PREVIOUS PROPOSAL ({parent})\n" + json.dumps({k: prev["ontology"][k] for k in ("entity_types", "entity_relations")},
                                                                    ensure_ascii=False)[:12000] if prev else "") +
                (f"\n\n# REVIEWER FEEDBACK — revise the proposal accordingly\n{feedback}" if feedback else "") +
                "\n\n# EVIDENCE (representative sections of each theme)\n" + evidence)
        rid = new_run_id()
        run = {"id": rid, "kind": "ontology", "by": actor, "started": now(), "status": "running", "backend": cfg["backend"],
               "prompt_version": PROMPT_VERSION, "sources": sorted({v[0] for v in hmap.values()}), "source_shas": {},
               "timeline": [], "parent": parent}
        qids = {q["id"] for q in qs}
        try:
            (onto_new, checks), res, _ = generate(
                comp=self.comp, run=run, cfg=cfg, system=SYSTEM, user=user, max_attempts=2, graph="ontology",
                check=lambda r: _validate(parse_obj(r.text), hmap, self.kb, qids),
                correction=lambda e: f"\n\n# Correction\nYour previous answer was not usable ({e[:160]}). Return the JSON object "
                                     "exactly as specified; relations must use declared entity type ids.")
            section = render_section(onto_new["entity_types"], onto_new["entity_relations"], _constraints_block(cur["text"]))
            new_text = replace_section(cur["text"], section)
            pid = "onto-" + uuid.uuid4().hex[:8]
            rec = {"id": pid, "status": "proposed", "by": actor, "at": now(), "origin": {"kind": "llm", "run": rid, "model": res.model},
                   "parent": parent, "feedback": feedback, "base_schema_version": cur["version"], "ontology": onto_new,
                   "checks": checks, "section": section, "schema_text": new_text,
                   "diff": "".join(difflib.unified_diff(cur["text"].splitlines(True), new_text.splitlines(True),
                                                        f"SCHEMA v{cur['version']}", "proposal", n=2)),
                   "summary": f"{len(onto_new['entity_types'])} types, {len(onto_new['entity_relations'])} relations; "
                              f"evidence {checks['verified']}/{checks['verified'] + checks['unverified']} verified; "
                              f"questions served {len(checks['questions_served'])}/{len(qids)}",
                   "reviews": []}
            with LOCK:
                if parent and prev and prev["status"] == "proposed":
                    prev["status"] = "superseded"
                    _save(self.kb, prev)
                _save(self.kb, rec)
            run.update(status="done", proposal=pid, summary=rec["summary"])
        except Exception as e:  # noqa: BLE001
            run.update(status="failed", error=f"{type(e).__name__}: {e}")
        run["finished"] = now()
        self.comp._save_run(run)
        self.kb.event(actor, f"ontology.propose.{run['status']}", run.get("proposal", ""), run=rid, parent=parent or "",
                      error=run.get("error", ""))
        return run

    def decide(self, user: dict, pid: str, verdict: str, comment: str) -> dict:
        from . import auth as A
        if verdict not in ("approve", "reject", "comment"):
            raise ValueError("verdict must be approve | reject | comment")
        if len(comment.strip()) < 5:
            raise ValueError("a comment is required (≥ 5 characters)")
        A.require(user, "admin" if verdict == "approve" else "reviewer")
        with LOCK:
            rec = get(self.kb, pid)
            if rec["status"] != "proposed" and verdict != "comment":
                raise ValueError(f"proposal is {rec['status']}")
            rec["reviews"].append({"by": user["name"], "at": now(), "verdict": verdict, "comment": comment})
            if verdict == "approve":
                cur = SC.current(self.kb)
                text = rec["schema_text"] if cur["version"] == rec["base_schema_version"] else replace_section(cur["text"], rec["section"])
                e = SC.save(self.kb, user["name"], text, note=f"ontology proposal {pid}: {comment[:120]}")
                rec.update(status="approved", schema_version=e["version"], decided_by=user["name"], decided_at=now())
            elif verdict == "reject":
                rec.update(status="rejected", decided_by=user["name"], decided_at=now())
            _save(self.kb, rec)
        self.kb.event(user["name"], f"ontology.{verdict}", pid, comment=comment[:300], schema_version=rec.get("schema_version"))
        return rec


# ---- OWL / Turtle ----------------------------------------------------------------------------------
NS = "https://lithokb.local/ontology#"


def to_turtle(kb: KB) -> str:
    o = G.ontology(kb)
    q = lambda s: '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'  # noqa: E731
    out = ["@prefix owl: <http://www.w3.org/2002/07/owl#> .", "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .",
           f"@prefix lkb: <{NS}> .", "", f"<{NS[:-1]}> a owl:Ontology ; rdfs:label {q('LithoKB ontology (SCHEMA v' + str(SC.current(kb)['version']) + ')')} .", ""]
    for tid, label in o["entity_types"].items():
        out.append(f"lkb:{tid} a owl:Class ; rdfs:label {q(label)}" + (f" ; rdfs:comment {q(o['type_defs'][tid])}" if o["type_defs"].get(tid) else "") + " .")

    def cls(ids):
        ids = sorted(i for i in ids if i != "*")
        if not ids:
            return "owl:Thing"
        return f"lkb:{ids[0]}" if len(ids) == 1 else "[ a owl:Class ; owl:unionOf ( " + " ".join(f"lkb:{i}" for i in ids) + " ) ]"
    out.append("")
    for rid, r in o["entity_relations"].items():
        out.append(f"lkb:{rid} a owl:ObjectProperty ; rdfs:label {q(r['label'])} ; rdfs:domain {cls(r['domain'])} ; "
                   f"rdfs:range {cls(r['range'])}" + (f" ; rdfs:comment {q(r['definition'])}" if r.get("definition") else "") + " .")
    return "\n".join(out) + "\n"


def from_turtle(kb: KB, actor: str, text: str) -> dict:
    """Import classes and object properties from Turtle (a pragmatic subset) as a proposal for review."""
    stmts = re.split(r"\s\.\s*(?:\n|$)", text)
    lab = lambda st: (re.search(r'rdfs:label\s+"((?:[^"\\]|\\.)*)"', st) or [None, None])[1]  # noqa: E731
    com = lambda st: (re.search(r'rdfs:comment\s+"((?:[^"\\]|\\.)*)"', st) or [None, ""])[1]  # noqa: E731
    local = lambda x: re.sub(r"^.*[:#/]", "", x.strip("<>"))  # noqa: E731

    def rng(st, key):
        m = re.search(rf"rdfs:{key}\s+(\[[^\]]*\]|\S+)", st)
        if not m:
            return ["*"]
        v = m.group(1)
        if v.startswith("["):
            return [local(x) for x in re.findall(r"[\w\-]*:[\w\-]+|<[^>]+>", v.split("unionOf", 1)[-1])]
        return ["*"] if local(v) == "Thing" else [local(v)]
    types, rels = [], []
    for st in stmts:
        m = re.match(r"\s*(\S+)\s+a\s+owl:(Class|ObjectProperty)\b", st)
        if not m:
            continue
        ident = re.sub(r"[^a-z0-9_]+", "_", local(m.group(1)).lower()).strip("_")
        if m.group(2) == "Class":
            types.append({"id": ident, "label": lab(st) or ident, "definition": com(st), "examples": [], "evidence": [], "questions": []})
        else:
            rels.append({"id": ident, "label": lab(st) or ident, "domain": [re.sub(r"[^a-z0-9_]+", "_", x.lower()) for x in rng(st, "domain")],
                         "range": [re.sub(r"[^a-z0-9_]+", "_", x.lower()) for x in rng(st, "range")],
                         "definition": com(st), "evidence": [], "questions": []})
    if not types:
        raise ValueError("no owl:Class found")
    cur = SC.current(kb)
    section = render_section(types, rels, _constraints_block(cur["text"]))
    new_text = replace_section(cur["text"], section)
    pid = "onto-" + uuid.uuid4().hex[:8]
    rec = {"id": pid, "status": "proposed", "by": actor, "at": now(), "origin": {"kind": "import", "format": "turtle"},
           "parent": None, "feedback": "", "base_schema_version": cur["version"],
           "ontology": {"entity_types": types, "entity_relations": rels, "uncovered": [], "notes": "imported from Turtle"},
           "checks": {"verified": 0, "unverified": 0}, "section": section, "schema_text": new_text,
           "diff": "".join(difflib.unified_diff(cur["text"].splitlines(True), new_text.splitlines(True),
                                                f"SCHEMA v{cur['version']}", "proposal", n=2)),
           "summary": f"imported: {len(types)} types, {len(rels)} relations", "reviews": []}
    _save(kb, rec)
    kb.event(actor, "ontology.import", pid, types=len(types), relations=len(rels))
    return rec


__all__ = ["OntologyLoop", "proposals", "get", "to_turtle", "from_turtle", "render_section", "replace_section"]
