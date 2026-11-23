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
