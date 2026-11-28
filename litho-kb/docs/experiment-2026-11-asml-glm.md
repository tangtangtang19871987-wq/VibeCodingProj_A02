# Experiment log: ASML computational lithography course × glm-5.3-flash (2026-11-21)

**Material**: the course "ASML Computational Lithography and Optical Proximity Correction" (Chinese-language), 33 HTML pages (3 table-of-contents pages + 30 chapters, about 700 KB; about 100 000 characters of Markdown after conversion). The material itself is not committed to the repository.
**Model**: OpenRouter `z-ai/glm-5.3-flash` ($0.04 / $0.078 per million tokens), `reasoning.effort = low`.

## How the results evolved

| Run | Change | Succeeded | Cards | Cross-chapter cards | Citations verifiable | Dangling refs | Cost | Time |
|---|---|---|---|---|---|---|---|---|
| Trial 1 (5 chapters) | Initial prompt lkb-compile/2 | 5/5 | 21 | 0 | 64% → 94% after fixing the verifier | 8 | $0.010 | 158 s |
| Trial 2 (5 chapters) | Prompt v3: ban "…" truncation, merge instead of replace | 3/5 | 13 | 0 | 99% | 2 | $0.005 | 96 s |
| Full run 2 (33 docs) | + automatic retry on invalid JSON | 32/33 | 101 | **1** | 97% | 12 | $0.077 | 945 s |
| Full run 3 (33 docs) | Prompt v4: mention detection + append action + creating cards for the topic skeleton | 33/33* | 93 | **14** | **100%** (665/668 exact) | 3 | $0.128 | 1110 s |

\* 2 documents failed in the first pass because of truncated output / broken JSON structure; they succeeded on rerun after "truncation and corruption also trigger a correction retry" was added.

Typical cross-chapter cards: Process window (7 chapters), OPC technique taxonomy (5 chapters), Computational lithography (5 chapters), ILT (4 chapters), SMO (3 chapters), OPC cost function (3 chapters).

## Findings and corresponding fixes

| Symptom | Root cause | Fix |
|---|---|---|
| With unlimited reasoning, no output for > 5 minutes per document | The reasoning model thinks for a long time first | `openrouter_reasoning: low`, streaming + stall detection → about 20–40 s per document |
| 64% of citations "unverifiable" | The verifier replaced formatting markers with spaces (breaking Chinese matching), full-width/quote-mark differences; the model truncated with "…", took only the start of multi-line quotes, quoted the outline view | Delete markers + strip whitespace + NFKC + unify quote marks; new `elided` check (segments matched in order); prompt forbids truncation and splicing |
| Updated cards lost evidence from other chapters | When rewriting a whole card the model kept only the current chapter's content | Evidence from other documents is carried forward deterministically by the system |
| Occasional degenerate output `{"": [""]}`, JSON wrapped as a string, broken structure, looping truncated output | Random failures of a cheap model in JSON mode | One correction retry; stringified JSON is unwrapped automatically; ≥ 50% invalid entries counts as failure |
| Almost no merging (only 1 of 101 cards cross-chapter) | The model only saw the title index; "update" required rewriting the whole card | **Mention detection** (string matching on title/abbreviation/alias, not vectors) supplies the full text of related cards; the **append** action writes only the increment, merged by the system |
| Topics referenced in the compile schema were not created as cards | The model did not follow "create topics when needed" | Topics in the schema's topic skeleton are created as cards automatically by the system |

## Q&A (real model)

Question (asked in Chinese): "What are the advantages and costs of ILT compared with model-based OPC? How do they differ in process window?"
- Sensible reading plan: located Lecture 14 (comparison/advantages/challenges), Lecture 15 (complexity figures), Lecture 19 (FEM/process window), Lecture 8 (MB-OPC cost function), Lecture 4 (comparison table).
- The answer was clearly structured and proactively listed source gaps (no quantitative process-window comparison data). 10 of 12 citations verified; 2 were correctly blocked (one cited a card as if it were a file, one cited a section that had not been provided). 18 s, < $0.01.

## Follow-up fixes (same day)

| Problem | Fix | Verification |
|---|---|---|
| Inconsistent IDs (`optical-proximity-correction` vs `opc`) | Deterministic ID normalization (English name/abbreviation/alias → acronym), applied to parent, relations and body links | Unit tests |
| Q&A cited cards as files | Prompt distinguishes "card → [[link]]" from "source section → [S]"; content quoted from a card is verified against the card text (`card`), and citations of unread sections are marked "not in the reading plan" | Same question asked again: 4/4 exact, 13 s |
| Three duplicate table-of-contents pages | lint adds source-document duplicate detection (4-gram Jaccard / containment, ignoring formatting and links) | All 3 pairs of TOC pages detected, no false positives among the 30 chapters, 0.11 s |
| Systematic protection against overlong reasoning | Per-stage reasoning effort + protocol "brief planning" + reasoning watchdog (abort and step down when the threshold is exceeded with no content) | Real model: the high level was aborted at 4001 characters → the medium level finished in 41.7 s |

## Still to improve

- Two-phase "decision / transcription" compilation (see README); evaluate on a larger corpus whether the extra call is worth it.
- Retiring the three TOC pages is left to the admin (lint already flags them).

## Core-structure round (PageIndex / Wiki / graph, same knowledge base, glm-5.3-flash)

**PageIndex node summaries** (`lkb index`): 32 documents, 32 calls, 0 failures, **$0.021**, 2.5 minutes. 166 entities recognized (all verified verbatim in the sources; 2 entities not present in the sources were dropped automatically). Once the model nested `entities` inside `nodes` → automatically lifted during parsing (fixed; rerun cost $0.0006). Summary quality example (same section of Lecture 20, both in Chinese in the source): structural summary "Main 3D effects:" → LLM summary "Four 3D effects: shadowing from the Ta absorber layer, edge near-field disturbance, phase shift, polarization response differences; especially pronounced at EUV 13.5nm".

**Graph** (reader view, published only): 50 cards · 32 documents · 378 sections · 76 entities; edges: reviewed 147 · concept mentions 667 · entities 406 · provenance 436; 0 isolated cards. The ontology constraints (Section 8, new in schema v3) found 4 violations, e.g. `edge-placement-error measured_by opc` (metric → topic), left to reviewers.
Example path: mask pattern fragmentation —depends on→ mask manufacturing constraints ←mentioned by— level-set methods for ILT.

**Wiki topic overviews**: 5 topics "with child pages but no overview", 5 calls (1 returned only a summary → succeeded after adding a correction retry), **$0.002** in total. Mechanical verification: all links exist, no new numbers; published after human review (rev2).

**Q&A: flat navigation → tree search** (same questions, asked in Chinese):

| Question | Navigation prompt (old → new) | Citation verification rate (old → new) | Cost (new) |
|---|---|---|---|
| ILT vs model-based OPC | 46 208 → 28 905 characters | 0.83 / 1.0 → 1.0 | $0.0034 |
| Common process window | 31 673 → 28 217 | 1.0 → 1.0 | $0.0014 |
| Mask 3D effects under EUV (condition EUV) | 38 578 → 28 375 | 0.75 → 0.86 | $0.0030 |
| Same, budget squeezed to 6 000 characters (simulating a 5× larger base) | 38 578 → 10 072 + 4 391 (two rounds) | 0.75 → **1.0** | $0.0027 |

With the squeezed budget the model first read the topic card and expanded `mask-3d`; in the second round it found the Lecture 20 summary and the "Summary and outlook" section — tree search still finds the right material when it cannot see the whole base.

**Real defects found and fixed in this round**: the CLI's `cards` / `show` showed unpublished revisions to readers (Web and MCP were already correct) → readers now see only published revisions, and `diff` / `reviews` require reviewer permission; concurrent writes to the same card lost revisions (two processes writing 12 times each left only some) → cross-process file lock; the test fails with the lock disabled and passes with it enabled.

## Query-first loop (golden questions, topics, ontology, entity graph), same KB, glm-5.3-flash

**Golden questions.** Ten ILT questions written with the owner (mask representations, gradient pipeline, optimizers, representations that handle holes, parallel processing and tile stitching, cost function vs. fields, classic cost terms, conflicting objectives, MRC and mask writing, ILT vs. OPC/SMO), each with expected documents/sections and key points. Stored in the KB (`eval/golden.jsonl`); scored mechanically.

**The first evaluation run found two real bugs**: (1) the navigator put leaf sections under `expand`, which were silently dropped, so no source text was read; (2) an answer consisting of `"..."` passed validation. Both fixed (and tested); q09 key-point coverage went from 0 to 1.0.

**Topic graph.** One call, $0.0045: 14 topics / 18 subtopics over 346 sections, coverage 100%. Because this corpus is one lecture per document, most topics follow lectures; some (advanced nodes, HPC and model accuracy) group several.

**Ontology loop.** Proposal from topic evidence + golden questions: 12 entity types, 14 relations, 51/52 evidence quotes verified, all 10 questions served, 3 questions flagged as not supported by the documents (tile stitching, which layers ILT is used for, an explicit velocity-field definition). One refine round with reviewer feedback (remove an abstract type; add `conflicts_with` and `precedes`) → 11 types / 14 relations, approved as SCHEMA v4 (provisionally, for the experiment). Cost $0.008 for both proposals.

**Entity graph.** Pilot on 6 documents, then the remaining 24: 177 instances, 121 typed relations, all with verified quotes; dropped as invalid: names not found verbatim, endpoints missing, one domain/range violation. Cost $0.026.

**Ablation** (same KB state, switches for themes and entity facts; means over runs; 10 questions):

| Configuration | Runs | Doc recall | Section recall | Key points | Grounding |
|---|---|---|---|---|---|
| themes off, facts off | 2 | 0.825 | 0.383 | 0.867 | 0.930 |
| themes only | 1 | 0.767 | 0.500 | 0.925 | 0.940 |
| facts only | 1 | 0.751 | 0.284 | 0.900 | 0.918 |
| themes + facts | 2 | 0.812 | **0.666** | 0.875 | 0.893 |

Reading: the combination reliably finds more of the expected source sections (0.32/0.45 vs. 0.63/0.70 per run); key-point coverage and document recall do not change beyond run-to-run noise (key points varied 0.78–0.95 between two identical runs). Ten questions and one or two runs per configuration are not enough for fine conclusions; the key-point check is coarse (term presence).

## Fixing what the evaluation exposed (ask/3, verifier v2), 3 repeats per configuration

**Diagnosis of the previous runs.** Of 27 missed key points, 15 were present in the reading material (the answer left them out) and 12 were not (retrieval missed sections such as lecture 13 §3.1, where the adjoint method and conjugate gradient / L-BFGS are named; one key point, "chain rule", is not in the corpus at all and was removed from the golden set). 26 of 28 unverifiable quotes were genuine quotes the verifier rejected: list markers in the middle of a quote, lines skipped without an ellipsis, part of a table row, a literal backslash-n. The model reported gaps for every answer, so evaluation queries had filed 55 gap issues.

**Changes.** Verifier: middle-of-quote list markers, stitched pieces within the cited lines, table cells only within one row, literal \n (re-verifying all earlier evaluation quotes: fuzzy 30 → 7). Answer prompt: enumerate every item for "which / what kinds" questions; `answerable` full / partial / none, gaps only when not full; evaluation never files gap issues (49 evaluation-generated issues closed as won't-fix with a comment). Ask graph: a `complete` node lists entity-graph items that appear in the reading material but not in the draft, and the model revises once. Navigation: up to 3 sections that ground relevant facts are read even if the navigator did not pick them. Evaluation: `--repeat`.

| Configuration (×3 repeats, 30 answers each) | Doc recall | Section recall | Key points | Grounding | Cost / answer | Latency / answer |
|---|---|---|---|---|---|---|
| themes, facts, expansion, completion all off | 0.789 (0.66–0.88) | 0.366 (0.30–0.40) | 0.914 (0.88–0.94) | 0.993 | $0.0029 | 9.5 s |
| themes + facts (the previous v3) | 0.823 (0.76–0.88) | 0.567 (0.50–0.65) | 0.844 (0.81–0.92) | 0.990 | $0.0029 | 9.1 s |
| **all on** | **0.884** (0.88–0.88) | **0.589** (0.52–0.65) | **0.950** (0.93–0.98) | **0.998** | $0.0043 | 16.8 s |

Reading: with all changes, key-point coverage is higher than both other configurations in every repeat, document recall is higher and stable, grounding is almost perfect. q02 (adjoint, resist model) and q03 (conjugate gradient / L-BFGS) went to 1.0 because the grounding sections are now read and the completeness check catches omissions. Themes + facts *without* completion lowered key-point coverage (more material, more omissions) — the completion step is what turns the extra material into coverage. Cost: one extra call when omissions are found (+50% cost, +80% latency). Still missed: q08 "accuracy vs runtime" and "process window" as conflicting objectives, q01 "curvilinear" (only in one table of lecture 22), q04 "polygon".

## Evidence forms and functional units (after Qiu et al. 2026, "From Chunks to Functional Evidence")

**What was built.** Deterministic evidence forms per section (table, code, formula, steps, values, constraints, diagnostics, figure; ASML corpus: 52 tables, 36 code blocks, 16 formulas, 38 procedures in 346 sections), question cues → needed forms, form tags for the navigator, form-coverage re-ranking of section hints, functional units built from the entity graph (66 units, 41 cross-document, at most 8 occurrences each), unit hints and form-aware evidence expansion, a `form_coverage` metric, and `required_forms` on the golden questions. No vectors, no training (the paper's fine-tuned encoder was its smallest gain: +0.012 ROUGE-L).

**Result: no measurable gain on this corpus.**

| Configuration (×3 repeats, 10 questions) | Doc recall | Section recall | Key points | Grounding | Form coverage |
|---|---|---|---|---|---|
| previous (no forms, no units) | 0.862 (0.86–0.87) | 0.689 (0.65–0.73) | 0.939 (0.89–0.98) | 0.983 | 1.00 |
| forms + units | 0.837 (0.83–0.86) | 0.639 (0.62–0.65) | 0.922 (0.89–0.98) | 0.988 | 1.00 |

Form coverage is already 1.0 without the feature: the material the navigator reads for these questions already contains the needed forms, so the failure the paper targets (a related paragraph instead of the table row with the value) is not the bottleneck here. A targeted test with four value-lookup questions added to the golden set (MFS of e-beam/laser writers, vertex/angle limits, σ range, MEEF limit; ×2 repeats) gave key points 1.0 in both configurations. Remaining misses are specific terms in conceptual answers (resist model, quasi-Newton / CG, polygon, process window).

**Decision.** Form-aware *navigation* is opt-in (`query.form_aware`, default off). The forms stay where they help without risk: index-tree badges, entity pages ("evidence by form"), and the agent `retrieve` pack (`needed_forms`, `units`).

**Robustness bug found in the same runs.** One answer call degenerated into a whitespace loop: ~190,000 blank characters until the 32,000-token cap, 249 s, answer lost (then rescued by the corrective retry). Fixes: a degenerate-output watchdog in the streaming client (a 3,000-character tail of whitespace or of one short repeated pattern aborts the call; the CALL graph retries once as a transient error) and per-stage output caps (`llm.max_tokens_by_stage`: navigate 4,000, answer 12,000, index 16,000).

Cost of this round: about $0.25 (OpenRouter, glm-5.3-flash).
