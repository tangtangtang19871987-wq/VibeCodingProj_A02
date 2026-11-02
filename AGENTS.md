# Project: tech-report PPTX agent (opencode)

Start here: `ARCHITECTURE.md` (design, requirements→mechanisms, limits) · `evals/` (self-test + behaviour evals).

- Primary agent: `.opencode/agents/tech-report-pptx.md` (default via `opencode.json`). Subagents: `deck-planner`, `diagram-designer`, `deck-reviewer`. Commands: `/deck /revise /diagram /review /colors`.
- Tools: `.opencode/tools/deck.ts` → `deck_catalog deck_create deck_check deck_edit deck_build deck_preview deck_compare deck_verify deck_lint deck_colors` (all call `.opencode/skills/tech-report-pptx/scripts/deck.py`).
- Skills (`.opencode/skills/`): `tech-report-pptx` · `python-pptx` · `html-ppt-studio` (→ `html-ppt-studio/`) · `ppt-master` (optional, `./setup.sh`, never edit).
- Contract: `output/<slug>/outline.json`. Deliverable: `deck.pptx` — **native and editable, zero pictures** (`deck_verify`).
- Check everything: `python3 evals/selftest.py`
