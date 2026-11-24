# LithoKB — a lightweight knowledge compiler for computational lithography

Takes a pile of Markdown documents and has an LLM "compile" them into a **reviewable, traceable, publishable** network of knowledge cards (knowledge graph + topic hierarchy),
while the source documents are always kept verbatim, browsable and accountable. The Web UI serves three roles (Reader / Reviewer / Admin); the CLI can run the whole workflow headless.

```
./lkb init                         # create the knowledge base (and the admin user)
./lkb upload examples/litho-docs   # layer 1: upload a folder of MD files
./lkb compile --backend mock       # layer 2: LLM compilation (mock = offline; anthropic = real model)
./lkb serve                        # Web UI → http://127.0.0.1:8765
python3 -m unittest discover -s tests -v
```

**Dependencies: Python ≥ 3.10 + `langgraph` (`pip install -r requirements.txt`).** All LLM calls run as LangGraph state graphs (`lithokb/flows.py`): the CALL graph `invoke → step_down/backoff → finish`; the GENERATE graph `generate → check → correct`; the ask graph `navigate → read → answer → verify`; the navigation graph `decide → open`. Everything else uses only the standard library. Claude models additionally need `pip install anthropic`. The interface and backend are in English; knowledge content stays in the source documents' language.
No database, no vector store, no document chunking, no frontend build chain. The frontend is 4 static files (about 60 KB).

---

## 0. Ideas it combines

| Source | Core value | How LithoKB implements it |
|---|---|---|
| **LLM Wiki** (Karpathy) | Sources are immutable; the LLM maintains a persistent, interlinked wiki; **the rules file (schema) is "the compiler's source code"**; three operations: ingest / query / lint; knowledge accumulates with use | Layer-1 sources are never rewritten; `SCHEMA.md` is edited by the admin and versioned, and every compilation records the version it used; good answers from **query** can be **filed back** as "Q&A synthesis" cards that enter review; `lkb lint` health checks; a human-readable `compiled/log.md` |
| **OpenKB** | Two-level wiki: one `summaries/` page per document + cross-document `concepts/` pages; new documents **enrich** existing pages instead of standing alone; `index.md` / `log.md` | Every source document is forced to produce one `summary` card (deterministic id, e.g. `summary-opc-ilt-md`) that points with `covers` relations to the concept cards it contributes to; concept cards are shared across documents; the exported `index.md` has two parts, "Knowledge" and "Document summaries" |
| **PageIndex** | No vectors, no chunks: use the document's own **table-of-contents tree** and let the LLM **navigate by reasoning**, the way a person reads a table of contents | Every document deterministically gets a heading tree (nodes carry exact line numbers); **Q&A navigates first, then answers**: the model reads the knowledge tree and document outline trees, writes a reading plan, then reads the selected content closely; **very long documents are compiled section by section along their outline** (not mechanically chunked by length), and each section sees the full outline and the cards already produced by earlier sections |
| (extra) Graphify | Every relation carries an epistemic status | Relations must be labeled `extracted / inferred / ambiguous` + confidence; a relation labeled "explicit in source" without valid evidence is automatically downgraded to "inferred"; "ambiguous" relations go to the front of the review queue and are drawn with a different line style in the graph |

## 1. Design principles

| Principle | Implementation |
|---|---|
| **Human-friendly ⇒ agent-friendly** | All data are files people can read directly: sources are verbatim `.md`, knowledge cards are `.md` with frontmatter, reviews and logs are JSONL with one entry per line. Humans can `cat`/`grep`/`git diff`, and so can agents. `compiled/index.md` and `graph.json` are also exported so an agent can read the whole base in one go. |
| **Compile, don't retrieve** | No chunking, no embeddings. Each call gives the LLM the **whole document** (with line numbers) + the index of all cards + the full text of cards already compiled from that document, so the model **updates** existing knowledge instead of creating duplicates (Karpathy "LLM Wiki"-style knowledge compilation). |
| **The LLM proposes, humans decide** | Every revision the LLM produces enters the review queue; readers see only revisions an admin has published. While a new revision of a published card is under review, the old published version stays visible to readers. |
| **Verifiable, not trusted** | Every claim from the model must carry `[E1]` evidence: source path + line numbers + **verbatim quote**. The system mechanically checks whether the quote really is on those lines (exact / shifted / approximate / not found) and puts the result in front of the reviewer. |
| **Observable end to end** | Every LLM call is saved to disk: system prompt, user prompt (verbatim), raw output, the model's thinking summary, usage, latency, cost, parse result, validation findings, and which cards were written. |
| **Lightweight** | Single-process `ThreadingHTTPServer`; the card index lives in memory and is updated incrementally per file; derived structures are cached by state; static assets are gzipped. Measured results for tens of thousands of cards and two thousand documents are in the Section 1.5 benchmark. |

## 1.5 Core technology: three knowledge structures + one engine

Cards are just "pages". The real core of the system is maintaining three complementary structures over the same reviewed knowledge, backed by one lightweight engine:

| Structure | Question it answers | Implementation (all derived from files, rebuildable at any time) |
|---|---|---|
| **PageIndex index tree** (`pageindex.py`) | "Where is the answer?" — find what to read level by level, like using a manual's table of contents | **Unified knowledge tree**: `Knowledge` (topic → card) + `Sources` (folder → document → section, with line numbers). Node summaries come in two tiers: structural summaries (heading + first sentence, free) and **LLM-written node summaries** (`lkb index`: one call per document, cached by sha256, **incremental** — an unchanged document is never called again). For long documents with no usable heading structure, the model proposes **virtual sections**. Q&A does a **multi-round tree search**: the tree is rendered breadth-first within a character budget (collapsed nodes marked `[+N]`) and the model returns `read / expand / done`; a small base is seen in one round, a large one takes one or two more small calls — **prompt size is bounded and does not grow with the base**. |
| **Wiki** (`wiki.py`) | "What is the full picture of this concept?" — every page is a navigation hub | Each card is assembled into a wiki page: breadcrumbs (topic path), child pages, reviewed bidirectional typed relations, mutually mentioning cards, **source sections that discuss this concept**, entities involved, backlinks, pages that do not exist yet (red links). **Entity pages**: named objects such as tools, equipment and organizations that are not cards. **Topic overviews**: the LLM writes a "topic map" from the published child cards (op `hub`), which is mechanically verified (links must exist, numbers must appear in the child cards) and then **enters review**. **Structural gaps**: topics with child pages but no overview, and clusters of tightly connected cards that belong to different topics. `lkb export` exports a static Markdown wiki (`compiled/wiki/`). |
| **Knowledge graph** (`graph.py`) | "How are they related? How do they connect?" | A **layered typed graph**; every edge carries a layer and an epistemic label: `reviewed` (reviewed typed relations, parent/child, wiki links) · `linked` (**deterministic entity linking**: a card's title or alias appears in the text; ambiguous names are not linked; ranked by idf, at most N kept per source — no "mention explosion") · `indexed` (entities recognized during indexing; the name must appear **verbatim** in the source, and an entity with the same name as a card is that card) · `provenance`. **Ontology constraints** are in Section 8 of `SCHEMA.md` (entity types; subject → object types for relations); violations are reported by lint. Queries: k-hop neighbors, **explanatory shortest path** (prefers reviewed relations), ego subgraph, PageRank centrality, label-propagation communities. The graph also takes part in Q&A navigation (strong-relation neighbors of cards hit by term matching are offered as hints). |
| **Engine** (`textindex.py`, `store.py`, `fsck.py`, `bench.py`) | Fast, stable, reliable | **BM25 full-text search** (Chinese bigram tokenization: no segmentation dictionary, no spaces needed) over cards and source sections, updated incrementally. **Incremental card index** (by file mtime/size; only changed files are re-parsed). All derived structures (search, tree, graph) are cached by "card generation + source state + schema version". **Cross-process write lock** (fcntl.flock; the Web server, CLI and MCP can write the same data directory concurrently) + **atomic replace after fsync**. `lkb fsck` checks file consistency (current revision vs. immutable revisions, source sha, parseability, leftovers from interrupted writes); `--repair` only cleans leftovers and rebuilds caches, never touching knowledge. `lkb bench` runs a synthetic-base benchmark. |

**Benchmark** (`lkb bench`, single process, pure Python, no LLM):

| Scale | Card index (cold / after editing one) | Card search p50 | Source section search p50 | Graph query (2-hop / path) | Wiki page | Graph cold build / after editing one | Peak memory |
|---|---|---|---|---|---|---|---|
| 2 000 cards · 400 docs · 6 011 sections | 155 ms / 9 ms | 4.6 ms | 7 ms | 0.1 / 1 ms | 0.09 ms | 1.0 s / — | 118 MB |
| 10 000 cards · 2 000 docs · 29 577 sections | 640 ms / 52 ms | 24 ms | 46 ms | 0.2 / 8 ms | 0.1 ms | 4.7 s / 1.1 s | 532 MB |

Problems found and fixed during benchmarking: a "mention-edge explosion" caused by generic aliases (5.3 million edges, 1.7 GB → 12 thousand edges, 118 MB); re-classifying all sources on every call (403 ms → 7 ms section search); linear prefix comparison in name scanning (graph cold build 10 s → 4.7 s, now cached per text, so editing one card only rescans that card).

## 1.6 Query first: golden questions → topics → ontology → entity graph

The questions the knowledge base must answer decide what it captures. The loop:

1. **Golden questions** (`evalset.py`, `eval/golden.jsonl`): real questions with expected documents/sections and key points. `lkb eval run` scores every question mechanically (documents and sections read, key points present in the answer, verifiable quotes), stores the run with a configuration snapshot, and `lkb eval compare` shows the change. Feature switches (`--features themes=0,facts=0`) allow ablations on the same knowledge-base state. Web: *Evaluation*.
2. **Topic graph** (`topics.py`, `lkb topics build`): a two-level theme hierarchy over all source sections with 2–4 representative sections per theme — "centroids" without vectors. Themes become a third root of the unified tree, so broad questions fan out over themes instead of repeating one point.
3. **Ontology loop** (`ontology.py`, `lkb ontology propose`): the model proposes entity types and typed relations (domain → range) for the golden questions from the themes' representative sections; every item cites quotes that are verified mechanically. Reviewers comment or ask for a refinement (a new proposal that addresses the feedback); an admin approves one version, which becomes a new SCHEMA.md version (section 8). OWL/Turtle export and import. Web: *Ontology*.
4. **Entity graph** (`entities.py`, `lkb extract [--limit N]`): per document, instances of the approved types and typed relations between them; names must occur verbatim, quotes are verified, domain/range is enforced, invalid items are dropped and reported. Cached per (document, ontology fingerprint): incremental; start small with `--limit`. The graph gets an `extracted` layer; entity pages show relations with evidence; facts and type instances relevant to a question become navigation hints that point to their source sections.

## 2. Two-layer knowledge structure

```
Layer 1  sources/        original Markdown (verbatim, versioned, with uploader)
            │  whole document + line numbers
            ▼
        LLM knowledge compiler  ──→ traces/<run>/  (full process record)
            │  JSON: cards + relations + evidence
            ▼
Layer 2  compiled/cards/   ① document summary layer: one summary card per document (OpenKB)
                           ② knowledge layer: concepts / methods / models / parameters… (topic hierarchy + typed relations + [[links]] + evidence)
            │  review → publish
            ▼
        reader-visible knowledge base / graph / compiled/index.md / graph.json
```

### Layer 1: source documents (Layer 0)
- Upload a single file, several files or a whole folder (the Web UI supports folder selection; CLI `lkb upload <dir>`), preserving the directory structure.
- **Never rewritten**: when the same path is re-uploaded with changed content, the old bytes go to `history/` and the version number is incremented; each version records uploader, time, sha256 and a note. Retiring a document only archives it; nothing is deleted.
- **Respects the author's index**: navigation order follows, in turn, the order of links in `SUMMARY.md / index.md / README.md / _index.md` in the directory, then frontmatter `weight / nav_order / sidebar_position`, and finally the title. A document's title is the frontmatter `title` or its first `#` heading.
- **Links just work**: relative links (including `../` and `#anchors`) and images are resolved to the corresponding documents / assets in the Web UI; you can switch between "rendered view" and "source with line numbers", and view any historical version.
- Each document page shows "Knowledge compiled from this document"; when the source changes, the affected cards are automatically marked **stale**.
- **HTML originals** (course web pages, exported wikis, etc.): stored verbatim as the source of record (viewable / downloadable at any time, served with `sandbox`, so scripts never run), while the built-in converter (`html2md.py`, standard library only) generates a `.md` of the same name as the compilation target. Conversion keeps heading levels, lists, tables, code and links (links to `.html` in the same directory are rewritten to `.md`); text labels of embedded SVG diagrams are kept as "diagram text"; the frontmatter records `converted_from`, the original's sha256 and the converter version. Navigation shows only the converted document, with a link to the original at the top of the page; a same-named `.md` written by the author is never overwritten by a conversion result.

### Layer 2: knowledge cards (Layer 1)
One card = one concept / method / model / parameter / metric / problem… (types in `cards.py: CARD_TYPES`), for example (title, summary, quote and body were written in Chinese in the source):

```markdown
---
id: "hopkins-imaging-model"
title: "Hopkins partially coherent imaging model"
type: "model"
parent: "imaging-models"                      ← topic hierarchy (topics can nest)
aliases: ["Hopkins formula", "TCC"]
summary: "The standard partially coherent imaging model that combines source and pupil into the TCC."
relations: [{"rel": "uses", "target": "socs-decomposition"}, ...]   ← typed relations (graph edges)
evidence: [{"id": "E1", "path": "imaging/hopkins.md", "lines": "3-3",
            "quote": "The Hopkins formula is, in computational lithography, …", "check": "exact", ...}]
grounding: {"exact": 3, "missing": 0, "total": 3, "score": 1.0}
rev: 2                 status: "in_review"     published_rev: 1     lifecycle: "active"
origin: {"kind": "llm", "run": "20261120T…", "model": "claude-opus-5-5"}
---
The Hopkins model combines the illumination source and the projection pupil into the transmission cross coefficient TCC [E1], commonly accelerated with SOCS decomposition [[socs-decomposition]] [E2]…
```

- **Graph** = `parent` (hierarchy edges) + `relations` (18 typed relations, including `contradicts` for flagging conflicts) + body `[[wikilink]]`s. Generated live from the in-memory index; no graph database needed.
- **Hierarchy** = the topic tree formed by topic cards (imaging models → Hopkins → TCC decomposition…); the left-hand navigation in the Web UI is this tree.
- Every change (LLM compilation or manual edit) creates an immutable revision `compiled/revisions/<id>/rNNNN.md`; any two revisions can be diffed.

## 3. Review and publishing governance

```
            submit            approve × N (configurable)   publish (admin)
  draft ───────────▶ in_review ───────────────▶ approved ─────────────▶ published
                       │ request_changes          │ return
                       ▼                          ▼
               changes_requested ◀────────────────┘ ── edit/recompile → new revision → in_review
                       reject ─▶ rejected ── reopen (admin) ─▶ in_review

  Card lifecycle (admin): active ──withdraw──▶ withdrawn ──restore──▶ active
                          active ──supersede with X──▶ superseded (readers are redirected to X)
```

- **Reviewer**: approve / request changes / reject / comment only; comments can be anchored to a piece of evidence or a paragraph (e.g. `E2`); can edit a card directly (creates a new revision attributed to them; **cannot approve their own change** — configurable).
- **Admin**: publish, return, reject, reopen, withdraw, restore, supersede; manages users and roles (role changes take effect immediately for logged-in users; the system refuses to remove the last admin).
- Votes count per **revision**: a new revision invalidates old votes. Rules: any reject → rejected; any request for changes → changes_requested; approvals ≥ `review.required_approvals` → approved.
- All actions are written to `reviews/<id>.jsonl` (per card) and `log/events.jsonl` (global audit), append-only.

## 4. LLM knowledge compiler (`compiler.py`)

The system prompt has two parts: a **fixed protocol** (in code: evidence rules, epistemic labels, output JSON format; the system relies on it to verify and store results) + **`SCHEMA.md`** (maintained by domain experts: topic skeleton, how to use card types, naming and writing conventions, meaning of relations, what not to compile).

Input of each call (no chunking, no retrieval):
1. **Index of all cards**: `id | type | parent | title | summary`, so the model reuses existing ids, builds relations and avoids duplicates;
2. **Full text of cards already compiled from these documents** (chosen deterministically by provenance, not by similarity) — on recompilation the model updates on top of them;
3. **Document outline tree** (heading levels + line ranges + first sentence of each section);
4. **Full source text** (or one section of a very long document), every line numbered, with version, sha256 and uploader;
5. Optional extra instructions from the operator.

**Very long documents** (over `compile.max_doc_chars`, default 300 000 characters): split into sections along the outline tree and compiled **in order**, section by section. Oversized sections are split further at sub-headings; only when a single leaf section is itself too long is it split by lines (explicitly flagged). Each section's compilation sees the full outline plus the full text of cards produced by earlier sections (they count as "cards compiled from this document"), so the model **updates** rather than starting from scratch. A document counts as compiled only after its last section succeeds; a failure midway stops the remaining sections of that document.

**Epistemic labels on relations**: each relation is `{rel, target, basis, confidence, evidence}`, where `basis ∈ extracted (explicit in the source, evidence required) / inferred / ambiguous (left to human judgment)`.

The output is one JSON: `cards[]` (create/update, fields, relations, evidence, confidence, change note) + `notes` (uncertainties / conflicts for reviewers).
The system prompt (`SYSTEM_PROMPT`) requires: atomic cards, stable English kebab-case ids, keeping the source language, **verbatim evidence for every fact**, no asserting facts from the model's own knowledge, and flagging conflicts with `contradicts` at lowered confidence.

Post-compilation pipeline: parse → **validate** (id normalization, in-batch duplicates, unknown types/relations, targets that do not exist, evidence citing a source outside this run, body citing undefined evidence… all recorded as findings, never silently dropped) → **evidence verification** → write new revision (`in_review`) → update exports.

**Incremental**: only documents whose sha256 changed since the last successful compilation are compiled (`lkb compile` default; `--all` forces). `compile.files_per_call` lets several whole documents be compiled in one call, which helps cross-document linking.

**ID normalization**: if the model references an id that does not exist, it is deterministically mapped to an existing card via "slug of the card's English name / abbreviation / alias → hyphen-initial acronym (`optical-proximity-correction` → `opc`)"; every mapping is recorded as a validation finding.

**Reasoning budget** (a common problem with reasoning models: with long input + long structured output + many constraints, they "draft" the whole JSON inside their reasoning first):
- `openrouter_reasoning` defaults to `low`; `reasoning_by_stage` sets compile / Q&A navigation / answering separately;
- the protocol asks for "brief planning, no drafting of the output in reasoning";
- **reasoning watchdog**: when streaming, if reasoning exceeds `reasoning_watchdog_chars` (default 20 000 characters) while the content is still empty, the call is aborted and retried one level lower; this is written to the call record;
- a further direction (not implemented): split "decision" (which cards to create, what to merge into, relations) and "transcription" (body, evidence) into two calls.

**Backends** (`config.json → llm.backend`):
- `anthropic`: official SDK, default `claude-opus-5-5`, streaming, adaptive thinking with a returned **thinking summary** (so reviewers understand why the model compiled things this way), configurable `effort`, server-side fallback enabled. Requires `ANTHROPIC_API_KEY`.
- `openrouter`: any OpenRouter model (default `z-ai/glm-5.3-flash`, very low cost), standard library only, streaming, records reasoning text and platform-reported cost. Requires the environment variable `OPEN_ROUTER_API_KEY`.
- `command`: any command line (prompt on stdin, result on stdout); can connect local models / intranet gateways.
- `mock`: deterministic heuristics (heading → card, first sentence → evidence), for offline testing and demos; **does not represent real compilation quality**.

## 4.5 Card granularity: what deserves to be a card (`quality.py`, `consolidate.py`)

One card = one concept: a reader finishes it in one sitting (about 1–3 minutes), an agent loads it in one go (about 1–2 thousand tokens). Length is counted in "reading units" (one Chinese character or one English word, fair for mixed Chinese/English text):

| Limit | Default | Meaning |
|---|---|---|
| `min_units` | 60 | Below this it is a single fact, not a concept → merge into a related card |
| `target_max` | 900 | About 2–3 minutes, about 1.2k tokens; comfortable upper bound |
| `hard_max` | 1600 | About 4 minutes, about 2k tokens; beyond this it must be consolidated or split |
| `max_evidence` | 24 | Too much evidence usually means one card holds several concepts |
| `max_appends` | 3 | Too many addendum sections ("Addendum (from …)", written in Chinese in older cards) → reads like a pile of excerpts |

Three mechanisms:
1. **Prevention**: `SCHEMA.md` states the granularity rules; the compile prompt gives the limits and annotates each existing card with its current length (`units=…`); when a card nears the limit, new content goes into a child concept card (parent = the original card) instead of being appended; out-of-bounds lengths at compile time are recorded as validation findings.
2. **Correction (LLM, consolidating rewrite / split)**: `lkb consolidate --list | ID | --auto [--from-rev N]` or the button in the review workbench. Only the card's existing, verified evidence may be used (no new facts); uncited evidence stays on the parent card, so provenance is never lost; results enter review as a new revision. If the consolidated body cites less than half of the evidence, it is rated **high risk** ("content may be lost, consider splitting"). The semantic diff shows "evidence moved to child cards" separately from "evidence actually removed".
3. **Merge (deterministic, admin)**: `lkb merge THIN_CARD --into TARGET_CARD`; the thin card is marked "superseded" and readers are redirected automatically.

Measured with a real model (glm-5.3-flash): "Process window" 1143 → a 274-unit overview + 3 child concept cards (FEM/PWQ, SMO mechanism, sign-off criteria); "OPC technique taxonomy" 1568 → 323 + rule-based OPC (448) + model-based OPC (562), evidence coverage 97%, all 100% verifiable.

## 4.6 Tiered review and batch approval (`quality.assess`, `Cards.batch`)

Every card has a **review risk** (low / medium / high) with actionable reasons:
- High: unverifiable evidence (approximate / not found / missing source), ambiguous or contradicting relations, source updated, no evidence, confidence < 0.5, length over the hard limit, evidence coverage below half after consolidation.
- Medium: elided quotes, cross-document merges, manual edits, Q&A file-backs, consolidating rewrites, changes to published content, confidence 0.5–0.7, mostly inferred relations, numeric/conclusion-type knowledge, granularity too long / too thin / too many addenda.
- Low: none of the above.

**Only low-risk cards can be batch-approved (enforced server-side)**; a batch requires a comment (≥ 10 characters); each card gets its own review record (with a batch id), and the audit log records a `review.batch_approve` event (approved / skipped lists and a snapshot of the criteria). Admins can batch-publish approved cards (likewise with a mandatory comment and audit trail). CLI: `lkb risk [ID]`, `lkb batch-approve --low-risk -m …`, `lkb batch-publish --all-approved -m …`.

## 4.7 Many ways to present knowledge: facets and views (`facets.py`, `annotate.py`)

The same reviewed knowledge is shown in eight views (switched at the top of the Knowledge page, sharing one applicability-condition filter bar):

| View | Question it answers | Data source |
|---|---|---|
| Wiki / Cards | What is this concept | Card body + evidence |
| Index tree | How the knowledge is organized | parent hierarchy |
| Graph | How concepts relate | Typed relations (epistemic line styles) |
| Mind map | The full picture around a topic | Child concepts + related concepts, expandable level by level |
| Timeline | How the technology evolved | Event facets (by year; without a year, by process node from large to small) |
| Comparison table | Values of parameters / metrics across methods and conditions | Fact facets (value, unit, conditions, each linked to the source) |
| Document outlines | Structure of the sources | Document outline trees (PageIndex) |

**Facets** (structured add-on information on a card); each entry must cite evidence already verified on the card:
- **Applicability conditions** `conditions [{dim, value, evidence}]`: dimensions are declared in the "applicability condition dimensions" section of `SCHEMA.md` (default: process node, wavelength, NA, layer, mask, application). Process nodes match as ranges ("≤7nm" covers "5nm"); wavelengths have synonyms (EUV = 13.5nm). When filtering: explicit matches are shown, knowledge whose source states no condition is treated as **general** and still shown, and knowledge stated to apply to other conditions is excluded. Q&A navigates by condition and requires the answer to state the conditions under which conclusions hold.
- **Events** `events [{when, what, evidence}]` → Timeline; **facts** `facts [{name, value, unit, conditions, evidence}]` → Comparison table.
- **Support check (mechanical)**: numbers must appear in the cited source, and most of the words must too; events and conditions may also appear within 3 lines before or after the cited lines (same table row, section heading). Facets that fail are not deleted (governance trail), but views and filters do not use them and readers do not see them; reviewers see a "not supported by source" marker and the risk rises to medium. `lkb reverify` refreshes the support markers.
- New compilations produce facets directly; existing cards are filled in with `lkb annotate --auto` (backfill) and `--unsupported` (redo), and the results enter review as new revisions.

## 4.8 Issue register (`issues.py`)

Contradictions, open questions, knowledge gaps and reader reports are separate entries (`issues/*.json`) with a status (open / resolved / won't fix) and a handling record; the same issue is deduplicated automatically (recorded as "seen N times"):
- contradictions and open questions reported by the compiler, and every `contradicts` relation → registered automatically;
- "source gaps" found in Q&A → knowledge gaps (telling the admin which documents to add);
- a reader's "Report an issue" on a card → reader report.
Open contradictions and open questions are shown on the related cards, **visible to all readers** (the knowledge base does not hide contradictions). CLI: `lkb issues`, `lkb issue ID resolve -m …`, `lkb report CARD TITLE`.

## 4.9 Source handling policy

Each source has a handling policy: **compile**, **reference only** (browsable and navigable in Q&A, but not compiled into cards), or **exclude**. Table-of-contents pages / navigation pages / link lists are automatically detected as "reference only" (as with the course table-of-contents pages in the ASML material); admins can override: `lkb policy PATH compile|reference|exclude|auto`.

## 4.10 For agents: MCP server (`mcp.py`)

`lkb --user reader1 mcp` provides MCP tools over stdin/stdout (standard library only): `search_knowledge`, `get_card`, `knowledge_tree`, `list_documents`, `document_outline`, `read_source`, `verify_quote`, `facts`, `timeline`, `list_issues`, `search_sections` (BM25 over source sections), `browse_tree` (level-by-level PageIndex browsing), `wiki_page`, `graph_neighbors`, `graph_path`, `ask`. Permissions follow the configured user: a reader sees only **published revisions**; all tools support applicability conditions; every call is written to the audit log. To connect Claude Code:
```
claude mcp add lithokb -- python3 /path/to/litho-kb/lkb --root /path/to/kbdata --user reader1 mcp
```

## 5. Q&A: navigate → read → answer → file back (`ask.py`)

1. **Navigate** (PageIndex tree search, `lkb-ask/2`): the model reasons over the **unified knowledge tree** (see 1.5), also seeing hints (cards and source sections hit by BM25, strong-relation neighbors in the graph), and selects **with stated reasons** the cards (≤ 12) and source sections (≤ 8) to read; when the tree does not fit, it first expands collapsed nodes, for at most `query.nav_max_rounds` rounds, each prompt no larger than `query.nav_budget_chars`. Every round (what was expanded, what was read, prompt size) is recorded in the trace. No vectors, no similarity thresholds.
2. **Read and answer**: only the full text of the selected cards and the source text of the selected sections (with line numbers) are read; the answer links with `[[card]]` and cites source facts with `[S1]` — these citations are verified verbatim too. When the material is insufficient, the answer must state the gap.
3. **File back** (LLM Wiki's compounding knowledge): a reviewer can submit a good answer as a `synthesis` (Q&A synthesis) card; `[S1]` is converted to `[E1]` evidence automatically, and the card goes through the normal review → publish flow.
- Readers can only ask against **published** knowledge; reviewers can choose to include cards under review. Both LLM calls are fully recorded (`nav-*` and `ans-*` files). The flow runs as the ask graph `navigate → read → answer → verify` in `lithokb/flows.py`.

## 6. Observability ("what did the LLM do")

`traces/<run>/`: `run.json` (type compile/query, model, effort, prompt version, **SCHEMA version**, section info, source sha, context size, usage, latency, cost estimate, stop_reason, timeline, validation findings, verification stats, cards written) · `system.md` · `prompt.md` · `response.md` · `thinking.md` · `parsed.json` · `error.txt`.

The Web **LLM traces** page: total calls / tokens / cost / average latency / citation verifiability rate, ranking of common validation problems, distribution of relation epistemic status, **verifiability by SCHEMA version** (whether a schema change made things better is visible at a glance), per-model statistics; for a single run, the raw prompts and outputs can be viewed page by page.
The right side of the review workbench shows directly: the card's evidence verification (lines the model claimed vs. lines actually found, highlighted in the source), the compiler's validation findings for this card, compile notes and thinking summary.
The **Health** page (`lkb lint`): dangling relations / links / parents, changed sources, quotes not found, missing evidence, ambiguous relations, missing summary cards, **highly duplicated source documents** (character 4-gram fingerprints: Jaccard similarity or containment, ignoring formatting and links), and more.

## 7. Three kinds of users and the Web UI

| Pages | Reader | Reviewer | Admin |
|---|:-:|:-:|:-:|
| Home, Knowledge (Wiki / Cards / Index tree / Graph / Mind map / Timeline / Comparison table / Document outlines, including the document summary layer), Sources (tree / outline / rendered / line numbers / version history), search | ✓ | ✓ | ✓ |
| Ask (against published knowledge; reading plan and citation verification visible) | ✓ when logged in | ✓ (may include unpublished) | ✓ |
| Upload documents; Review (queue with ambiguous relations first, and workbench: card / diff / edit / review history + evidence verification + epistemic status); Issues; Q&A file-back; LLM traces; Health; view the compile Schema | | ✓ | ✓ |
| Publish (publish / return / withdraw / restore / supersede); Compile (choose documents, backend, extra instructions, job progress); **edit the compile Schema**; Users; Audit log; retire sources | | | ✓ |

`config.json → public_read`: when `true`, anonymous visitors can read published knowledge and sources; set to `false` to require login.

## 8. CLI (headless, full workflow)

```
lkb init [--admin NAME]                     lkb serve [--host H --port P]
lkb user add|list|set NAME [--role R --password P --disable --enable]
lkb upload PATH [--prefix DIR --note TXT]   lkb sources tree|ls|show|history|retire [PATH] [--version N]
lkb compile [PATHS…] [--all --backend B --files-per-call N --instructions TXT --dry-run]
lkb queue | cards [--status S] | show ID [--rev N|--published] | diff ID A B | reviews ID
lkb approve|request-changes|reject|comment|submit ID -m "comment"
lkb publish|return|reopen|withdraw|restore ID [-m ...]   lkb supersede ID --by OTHER
lkb traces [ls|show RUN [--part prompt|response|thinking|system|parsed]|stats]
lkb ask QUESTION… [--all --file-back [TITLE]]   lkb queries   lkb file-back RUN [--title T --parent P]
lkb schema [show|set FILE -m NOTE|history|diff --a N --b M]   lkb outline PATH
lkb search TERMS…   lkb lint   lkb log [--target ID]   lkb export      (global: --root --user --json)
lkb index [PATHS…] [--status --force]      PageIndex: write node summaries + recognize entities for changed documents (incremental)
lkb tree [--budget N --open ID…]           the unified knowledge tree as the navigation model sees it
lkb wiki home|page ID|entities|entity ID|gaps|export|hubs [ID|--auto]
lkb kg stats|neighbors ID|path A B|central|communities|findings [--depth N --layers reviewed,linked]
lkb fsck [--repair]   lkb bench [--cards N --docs M]   lkb ask … --cond wavelength:EUV,node:5nm
lkb eval list|import FILE|export|run [--ids --all-cards --features themes=0,facts=0 --label]|runs|show RUN|compare A B
lkb topics status|build|show     lkb extract [PATHS…] [--status --limit N --force]
lkb ontology propose [--from PID --feedback TXT]|list|show PID|approve|reject|comment PID -m TXT|export|import FILE
```
The CLI acts as `--user` (or `LKB_USER`) under the same role and workflow rules (anyone who can run the CLI already has file permissions on the data directory, so its claimed identity is trusted).

## 9. Data directory

```
kbdata/
  config.json  users.json  secret.key
  SCHEMA.md                       compile schema (history/schema/vN.md keeps every version)
  sources/…                       sources (current version)
  meta/sources.json               provenance: version, uploader, time, sha256, history
  history/sources/<path>@<v>      all old versions
  compiled/cards/<id>.md          current card revision + workflow state
  compiled/revisions/<id>/rNNNN.md immutable revision snapshots
  compiled/index.md  graph.json   export of published knowledge (for humans / agents)
  compiled/log.md                 human-readable timeline: ingest / compile / publish / withdraw / schema change
  reviews/<id>.jsonl              review records
  traces/<run>/…                  full record of LLM calls
  log/events.jsonl                audit log
```
The whole directory can go straight into git for backup and diff-based auditing.

## 10. Code structure

| File | Responsibility |
|---|---|
| `lithokb/store.py` | Data directory, config, atomic writes, write lock, audit log |
| `lithokb/fm.py` | Frontmatter read/write (no YAML dependency) |
| `lithokb/sources.py` | Layer 1: upload, versions, provenance, index-respecting hierarchy tree, path safety, HTML ingest |
| `lithokb/html2md.py` | HTML → Markdown conversion (original kept, conversion result carries provenance) |
| `lithokb/cards.py` | Layer 2: cards, revisions, review state machine, evidence verification, graph, search, lint, export |
| `lithokb/compiler.py` | Protocol + SCHEMA prompt construction, sectioned compilation, parsing, validation (including epistemic labels), writing, trace, statistics |
| `lithokb/flows.py` | LangGraph state graphs for all LLM calls: CALL (`invoke → step_down/backoff → finish`), GENERATE (`generate → check → correct`), ask (`navigate → read → answer → verify`), navigation (`decide → open`) |
| `lithokb/doctree.py` | Document outline tree (deterministic), outline text, structure-based sectioning |
| `lithokb/pageindex.py` | Unified knowledge tree, LLM node summaries and entities (incremental), in-budget rendering, BM25 over source sections |
| `lithokb/wiki.py` | Wiki pages / entity pages / home page / structural gaps, topic overviews (LLM + mechanical verification), static export |
| `lithokb/graph.py` | Layered knowledge graph: deterministic entity linking, ontology constraints, neighbors / paths / centrality / communities |
| `lithokb/textindex.py` | BM25 inverted index (Chinese bigram tokenization, incremental) |
| `lithokb/evalset.py` | Golden questions, evaluation runs, comparison |
| `lithokb/topics.py` | Topic graph over source sections (themes, representative sections) |
| `lithokb/ontology.py` | Ontology loop: evidence-cited proposals, review / refine / approve, OWL/Turtle |
| `lithokb/entities.py` | Ontology-guided extraction of instances and typed relations |
| `lithokb/fsck.py` · `bench.py` | File consistency check and repair · performance benchmark |
| `lithokb/schema.py` | Versioning and diffs of `SCHEMA.md` |
| `lithokb/ask.py` | Q&A: navigate → read → answer → file back |
| `lithokb/quality.py` | Card granularity metrics and review risk tiers |
| `lithokb/consolidate.py` | Consolidating rewrite / split (LLM) and merge (deterministic) |
| `lithokb/facets.py` | Facets: applicability-condition matching, support check, filtering |
| `lithokb/annotate.py` | Facet backfill for existing cards (LLM) |
| `lithokb/issues.py` | Issue register |
| `lithokb/mcp.py` | MCP server (agent tools) |
| `lithokb/llm.py` | anthropic / command / mock backends |
| `lithokb/auth.py` | Users, roles, pbkdf2 passwords, HMAC tokens |
| `lithokb/server.py` | JSON API + static frontend |
| `lithokb/web/` | Single-page frontend (own safe Markdown renderer and force-directed graph, no framework) |
| `lithokb/cli.py` | CLI |
| `tests/test_lkb.py` · `test_core.py` | End-to-end tests · core engine tests (tree search, graph, wiki, cross-process lock, fsck; offline) |
| `tests/test_flows.py` | Tests for the LangGraph flows in `lithokb/flows.py` |

## 11. Current limits and next steps

- Formulas are shown as raw TeX (KaTeX is not bundled, to stay offline with zero dependencies; it can be added locally later if needed). Raw HTML in sources is shown escaped (safety first).
- The write lock is cross-process (fcntl.flock, POSIX); reads take no lock (all writes are atomic replaces after fsync). On Windows it falls back to an in-process lock.
- The graph is rebuilt as a whole after card changes (text-scan results are cached; about 1 second for 10 000 cards); larger scales could use a per-card incremental graph.
- The mock backend is only for workflow validation; real compilation quality requires connecting `anthropic` (or `command`) and evaluating on real material — that is exactly the next stage of "real testing": compilation quality (evidence verification rate, duplication rate, review approval rate), performance (indexing / compilation throughput on large bases) and prompt iteration (`PROMPT_VERSION` is recorded in every trace for comparison).
