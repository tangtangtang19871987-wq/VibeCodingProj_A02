"""SCHEMA.md — the knowledge base's own "compiler source" (the LLM-Wiki idea).

The compiler prompt has two parts:
  * a fixed *protocol* in code (grounding rules, epistemic labels, JSON contract) —
    what the machinery needs to verify and store the output;
  * this *schema*, a Markdown file owned by the domain experts: ontology (topics,
    card types, relation meanings), naming and writing conventions, what to compile
    and what to ignore. Editing it changes how knowledge is compiled, without code.

Every edit is versioned (history/schema/vN.md) and every compile/query trace
records the schema version + sha it ran with, so behaviour changes are attributable.
"""
from __future__ import annotations

import difflib
import json
import re

from .store import KB, LOCK, atomic_write, now, sha256

DEFAULT_SCHEMA = """# LithoKB Compilation Schema (SCHEMA)

This file defines the structure and writing conventions of the computational lithography knowledge base. The knowledge compiler (LLM) reads it in full on every compile.
Admins can edit it on the "Schema" page; every edit is versioned, and each compile record notes the version it used.

## 1. Topic skeleton (topic cards; reuse these ids)
- `imaging-models` Imaging models: Abbe / Hopkins, TCC, SOCS, vector imaging, polarization
- `resist-models` Resist and etch models: threshold, diffusion, development, compact models, etch bias
- `opc` Optical proximity correction: rule-based / model-based, fragmentation, EPE, convergence
- `ilt` Inverse lithography: curvilinear masks, gradient optimization, level sets, mask rule constraints
- `smo` Source-mask optimization
- `mask-3d` Mask 3D effects (M3D) and EUV-specific effects: shadowing, absorber, stochastics
- `hotspot-dfm` Hotspot detection and design for manufacturability
- `metrology-calibration` Metrology and model calibration: CD-SEM, contours, calibration flow, error metrics
- `ml-litho` Machine learning in computational lithography
- `compute-platform` Compute platforms and acceleration: GPU, distributed computing, full-chip runtime
New topics are allowed, but must sit under one of the topics above or state a reason (in notes).

## 2. Using card types
- `summary`: one per source document, describing what the document covers and which knowledge points it contains (the OpenKB summaries layer).
- `concept / method / model / algorithm`: core cross-document knowledge (the OpenKB concepts layer). One concept, one card.
- `parameter / metric`: must state the unit, the typical value range and where it comes from; no source, no number.
- `issue`: known problems, failure modes, limitations.
- `result`: experimental / simulation findings; must state the conditions (node, NA, wavelength, illumination...).

## 3. Naming and writing
- id: English kebab-case using the industry-standard name, e.g. `optical-proximity-correction`, not `opc-method-1`.
- Title: the full name with the abbreviation in parentheses, e.g. "Optical Proximity Correction (OPC)".
- Body: a one-sentence definition first, then key points; keep formulas in LaTeX; distil, do not paste the source.
- aliases: list abbreviations, full English names and common alternative names (including Chinese ones), for deduplication and search.

## 4. Meaning of relations
- `uses`: A's computation uses B; `depends_on`: A's correctness depends on B (e.g. OPC depends on a calibrated model).
- `improves / alternative_to / contrasts_with`: mark as extracted only when the source compares them explicitly; otherwise inferred.
- `contradicts`: two sources disagree; the body must state both positions and where each comes from.

## 5. Card granularity (what deserves its own card)
- One card = one concept, read in one sitting (about 1–3 minutes) and loaded by an agent in one go (about 1–2k tokens).
- The body is roughly 60–900 units (Chinese characters or English words); beyond about 1600 it must be consolidated or split.
- A one-sentence fact (a parameter's typical value, a tool's name) does not get its own card; merge it into the related concept card.
- When a concept's content comes from several documents, merge it into the same card (append); when a card nears the limit, create a child concept card for the new content (parent = the original card).
- Topic cards and document summary cards are for navigation and have no minimum length.

## 6. Applicability condition dimensions (under which conditions a conclusion holds)
Almost every computational lithography conclusion depends on conditions. Annotate them only when the source states them explicitly, and cite evidence; otherwise the conclusion is treated as general.
- `node` Process node: e.g. ≥28nm, 7nm, 5nm and below, 65nm–5nm
- `wavelength` Source wavelength: e.g. EUV (13.5nm), ArF immersion (193i), ArF (193nm), KrF (248nm)
- `na` Numerical aperture: e.g. 0.33, 0.55 (High-NA), 1.35
- `layer` Layer type: e.g. contact, via, metal, fin, gate
- `mask` Mask type: e.g. binary mask, phase-shift mask, EUV reflective mask, curvilinear mask
- `application` Application: e.g. logic, memory (DRAM/NAND), full-chip, critical layers

## 7. What not to compile
- Table-of-contents pages, navigation pages, copyright notices, pure link lists (at most a summary card).
- Administrative information unrelated to computational lithography; ads, promotion, social-media / WeChat contact details, copyright footers.
- In documents converted from HTML, "Figure text: ..." lines are labels from diagrams; use them only as auxiliary hints, never as standalone factual evidence.

## 8. Graph ontology (entity types and relation constraints)
Entities are named objects that appear in the source but do not get their own card. The document index recognises them (the name must appear verbatim in the source); they are used for the graph and navigation:
- `tool` Software/tool: e.g. Tachyon, Calibre, Proteus, Mentor
- `equipment` Equipment: e.g. NXE:3400, EXE:5000, CD-SEM, scanner
- `organization` Organization/company: e.g. ASML, imec, TSMC, Brion
- `material` Material: e.g. chemically amplified resist, metal-oxide resist, absorber material
- `standard` Format/standard: e.g. GDSII, OASIS
- `product` Product/chip: e.g. a processor generation, a memory part
- `person` Person
Relation constraints (subject card type → object card type; `*` = any; lint reports violations):
- `parameter_of`: parameter|metric → *
- `measured_by`: *  → metric|parameter|tool|equipment|method|process
- `implements`: algorithm|method|tool|model|process → *
- `example_of`: * → *
"""


def _path(kb: KB):
    return kb.root / "SCHEMA.md"


def _hist(kb: KB):
    return kb.root / "history" / "schema"


def ensure(kb: KB) -> None:
    if not _path(kb).exists():
        save(kb, "system", DEFAULT_SCHEMA, note="initial default schema")


def current(kb: KB) -> dict:
    ensure(kb)
    text = _path(kb).read_text("utf-8")
    versions = history(kb)
    v = versions[-1]["version"] if versions else 0
    return {"text": text, "version": v, "sha": sha256(text.encode())[:12]}


def history(kb: KB) -> list[dict]:
    p = _hist(kb) / "versions.json"
    return json.loads(p.read_text("utf-8")) if p.exists() else []


def save(kb: KB, actor: str, text: str, note: str = "") -> dict:
    text = text.replace("\r\n", "\n")
    if not text.strip():
        raise ValueError("schema cannot be empty")
    with LOCK:
        versions = history(kb)
        sha = sha256(text.encode())[:12]
        if versions and versions[-1]["sha"] == sha:
            return versions[-1]
        v = (versions[-1]["version"] + 1) if versions else 1
        atomic_write(_hist(kb) / f"v{v}.md", text)
        atomic_write(_path(kb), text)
        entry = {"version": v, "sha": sha, "by": actor, "at": now(), "note": note, "chars": len(text)}
        versions.append(entry)
        atomic_write(_hist(kb) / "versions.json", json.dumps(versions, ensure_ascii=False, indent=1))
    kb.event(actor, "schema.update", f"v{v}", sha=sha, note=note)
    return entry


def version_text(kb: KB, v: int) -> str:
    p = _hist(kb) / f"v{int(v)}.md"
    if not p.exists():
        raise FileNotFoundError(f"schema v{v}")
    return p.read_text("utf-8")


def diff(kb: KB, a: int, b: int) -> str:
    ta = version_text(kb, a).splitlines(True) if a else []
    tb = version_text(kb, b).splitlines(True)
    return "".join(difflib.unified_diff(ta, tb, f"v{a}", f"v{b}", n=2))


def skeleton(kb: KB) -> dict[str, tuple[str, str]]:
    """Topic skeleton declared in SCHEMA.md as list items: - `topic-id` Name: description.
    Read from the section whose heading contains "Topic skeleton" (or the legacy "领域主题骨架");
    if no such heading exists the whole text is scanned (legacy behaviour)."""
    text = current(kb)["text"]
    m = re.search(r"^#+[^\n]*(?:领域主题骨架|topic skeleton)[^\n]*\n(.*?)(?=^#+ |\Z)", text, re.M | re.S | re.I)
    out = {}
    for m2 in re.finditer(r"^[ \t]*[-*][ \t]+`([a-z0-9][a-z0-9-]*)`[ \t]+([^：:\n]+)[：:]?[ \t]*([^\n]*)$",
                          m.group(1) if m else text, re.M):
        out[m2.group(1)] = (m2.group(2).strip(), m2.group(3).strip())
    return out
