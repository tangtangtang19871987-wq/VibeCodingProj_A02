---
name: tech-report-pptx
description: Orchestrates html-ppt-studio + python-pptx + ppt-master into one pipeline for technical-report decks (architecture reviews, postmortems, design reviews, benchmark/progress reports, tech talks). Defines the shared outline.json contract, route selection (A native python-pptx / B ppt-master / HTML-only), and the QA gate. Load this first for any technical presentation request.
---

# Technical-report deck pipeline

Three engines, one contract (`outline.json`, schema in `schema/outline.schema.json`, sample in `examples/outline.example.json`):

| Engine | Role in the pipeline |
|---|---|
| **html-ppt-studio** | *Design draft + live presenter.* 25 themes / 34 layouts / 26 animations. Instant visual review; also the theme source of truth for PPTX. |
| **python-pptx** | *Deterministic native PPTX.* Native charts, tables, code blocks, layered-architecture diagrams, notes; linter + render QA. Route A builder and universal QA. |
| **ppt-master** | *High-design native PPTX.* Template/brand fidelity, imagery, animations/transitions, narration, beautify an existing deck. Route B builder. Has its own gated workflow. |

## Pipeline

1. **Intake** (ask only what's missing, in ≤1 round): audience & decision wanted, duration (≈1.5 min/slide → slides), language, source material (files/repos/data), brand/template, must-have numbers. If the user gave data, never alter it; if a number is missing, put `TODO` in the slide and list it in the final report — do not invent figures or sources.
2. **Storyboard → `outline.json`**. Technical-report arc: *Context & decision wanted → Problem (with evidence) → Approach/architecture → Results (numbers) → Trade-offs/risks → Plan → Ask/decision*. Rules: titles are full-sentence takeaways; one idea per slide; every number carries `source`; `notes` hold the spoken narrative (60–120 words/slide); ≤ 5 bullets, ≤ 30 words per card; pick the slide `type` by content shape (numbers→`kpi`/`chart`/`table`, sequence→`timeline`/`process`, system→`layers`/`hero`, flow with branches/loops/lanes/rich architecture→`diagram` (full manual: `reference/diagram.md`; simple linear flows can use `workflow`) (nodes: id,label,sub?,icon?,x,y∈0..1; edges: from,to,style solid|dashed,label?,route above|below?, fs/ts sides?), contrast→`comparison`, snippet→`code`). Save under `output/<slug>/outline.json`.
2b. **Validate**: `python3 .opencode/skills/tech-report-pptx/scripts/check_outline.py output/<slug>/outline.json` — fix every ERROR (diagram overlaps / out-of-canvas / bad ids) before rendering. For `diagram` slides read `reference/diagram.md` first and imitate `examples/diagrams.example.json`.
3. **HTML draft** (always, it's cheap): `python3 .opencode/skills/tech-report-pptx/scripts/outline_to_html.py output/<slug>/outline.json output/<slug>/draft.html --theme <theme>`. Screenshot with Playwright overview (`PPT.overview(true)`) and review layout; iterate on the outline, not the HTML. Offer 2–3 themes if the user has no preference (guide in `html-ppt-studio/SKILL.md`).
4. **⛔ Gate**: show the outline summary (slide titles) + draft path/screenshot; get the user's OK or edits before building the PPTX. Skip only if the user said "just do it".
5. **Choose route** (state the choice and why in one line):
   - **Route A — python-pptx** (default for technical reports): data-heavy, code/architecture slides, internal review, needs fast iteration or reproducible rebuild. `python3 .opencode/skills/python-pptx/scripts/outline_to_pptx.py output/<slug>/outline.json output/<slug>/deck.pptx`
   - **Route B — ppt-master**: user wants rich visual design, a brand `.pptx` template, generated imagery, animations/narration, or to *beautify/redesign* an existing pptx. Export source: `python3 .opencode/skills/tech-report-pptx/scripts/outline_to_markdown.py output/<slug>/outline.json output/<slug>/source.md`, then follow `.opencode/skills/ppt-master/SKILL.md` **exactly** (see rules below), giving it `source.md`, the language, the audience, and the chosen theme's accent/background colors as the style hint.
   - **HTML-only**: user will present in a browser / wants a shareable link; deliver `draft.html` (`--inline` file) and skip PPTX.
   - Both A and B may be produced when the user wants to compare; label files clearly.
6. **QA gate** (mandatory for any PPTX, including ppt-master output): `python3 .opencode/skills/python-pptx/scripts/lint_pptx.py <deck>.pptx --render` → fix all ERRORs (edit outline & rebuild for A; use ppt-master's own repair loop for B), look at the PNGs yourself (overflow, contrast, orphan titles, empty areas), re-run until 0 errors. Notes missing = WARN to fix unless the user declined notes.
7. **Deliver**: paths of `outline.json`, `draft.html`, `deck.pptx`; slide count; theme; open TODOs/assumptions; what to tweak next. Short — no re-narration of the slides.

## ppt-master rules (it is a third-party skill with an integrity guard)
- Never modify files under `vendor/ppt-master/` and never bypass `attribution_guard.py`; if it fails, stop Route B and tell the user (suggest `./setup.sh`).
- Retain `SKILL_DIR` = absolute path of `.opencode/skills/ppt-master` (resolve symlink with `realpath`), run its scripts by absolute path, never `cd` into it.
- Obey its `⛔ BLOCKING` gates: stop and ask the user; don't answer for them. Its procedure supersedes steps 5–6 for Route B *except* that step 6's lint still runs afterwards.
- If `.opencode/skills/ppt-master` is absent, say Route B is unavailable (not installed) and offer Route A.

## Using python-pptx on ppt-master output
Allowed: `lint_pptx.py` QA, metadata, notes patching, small text fixes (edit run text). Not allowed: merging slides from a python-pptx deck into a ppt-master deck (masters/theme parts differ and corrupt easily). If a data slide is wrong, fix it through ppt-master's own flow.

## Design consistency
**Default visual style = `modern-tech`** (the user's standard): clean & professional — white / light blue-grey page, deep-blue titles, dark-grey body, a multi-colour semantic set — blue / purple / green / yellow / orange / pink — cycled over parallel cards, steps and chart series, each as pale tint fill with clear tone-coloured thin border, vivid colour only for icons / labels / edges, very light shadows; **no gradients, no glows, no neon, no dark backgrounds, same component = same colour** (full rules in `reference/diagram.md`); soft flat 3D cubes + connector motif, card layout, workflow/DAG visuals (solid = sequential, dashed = conditional/loop). Composition: *left = concept & headline, centre = visual focus, right = technical logic*. Use `hero` as the opener (or `cover`) and `workflow` / `layers` for architecture. Never switch to a dark/other theme unless asked.
Theme names are shared across HTML and PPTX (`midnight`, `paper`, `nord`, …). Alternatives only on request: `midnight`, `nord`, `mono-light`, `corporate-blue`, `solarized-*`, `dracula`.
