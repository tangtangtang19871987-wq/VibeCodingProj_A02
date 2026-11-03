# Dev playbook — changing the system without breaking what the user likes

## Map
| what | where |
|---|---|
| primary agent / subagents | `.opencode/agents/*.md` |
| slash commands | `.opencode/commands/*.md` |
| typed tools (thin TS wrappers) | `.opencode/tools/deck.ts` → `.opencode/skills/tech-report-pptx/scripts/deck.py` |
| outline contract | `tech-report-pptx/schema/outline.schema.json`, `scripts/check_outline.py`, examples in `tech-report-pptx/examples/` |
| HTML renderer | `tech-report-pptx/scripts/outline_to_html.py` (+ `html-ppt-studio/assets/*.css`, `runtime.js`, `scripts/new_deck.py`) |
| PPTX builder | `python-pptx/scripts/outline_to_pptx.py` |
| shared geometry / palette / icons | `python-pptx/scripts/diagram_geom.py`, `svgpath.py`, `theme_tokens.py`, `_fit.py` |
| style profiles (the look) | `html-ppt-studio/assets/styles/{vivid,flat}.json` → `html-ppt-studio/scripts/gen_modern_themes.py` → `assets/themes.modern.css`, `assets/themes/modern-tech*.css` |
| QA | `python-pptx/scripts/verify_pptx.py` (editable + style), `lint_pptx.py` (layout) |
| goldens | `evals/golden/manifest.json` + images; `tech-report-pptx/scripts/golden.py` |
| self-test | `evals/selftest.py` (46+ checks) · behaviour evals `evals/cases.md` |

## Golden rule of changes
1. Before: `python3 evals/selftest.py` green; `deck_golden check` green.
2. Change the smallest thing.
3. After: rebuild both examples, `deck_preview`, **look** (and `deck_compare` against the goldens), then `python3 evals/selftest.py`. Commit only with "0 failed".

## Recipes
- **Change / add a look**: edit or add `assets/styles/<name>.json` (tones fill/border/soft/solid, cycle, accent, head_color, gradients, shadow, gradient_heading, cubes, dots, theme) → `python3 html-ppt-studio/scripts/gen_modern_themes.py` → build examples → look → selftest. Never hand-edit `themes.modern.css`.
- **The user approves a look** → `deck_golden add <image> --id <name> --slides <n,…> --note "<user's words, date>"`; check the reported distance; selftest now guards it.
- **New slide type**: handler in `outline_to_pptx.py` (use `tn(i)`/`tcard` for colour cycling, `G.tone()` for semantic colours) + renderer in `outline_to_html.py` + entry in `deck.py SPECS` + `check_outline.TYPES/REQ` + schema enum + an example slide in `examples/` (selftest builds it automatically).
- **New icon**: add a 24×24 stroke path to `diagram_geom.ICONS` (must parse in `svgpath.parse`; rendered natively, no PNG step).
- **New tool**: subcommand in `deck.py` → export in `deck.ts` (`tool({description,args,execute})`, call `deck(ctx.worktree, [...])`) → mention in the agent prompt → selftest case.
- **Verify opencode loads everything**: `opencode debug config` (agents/commands/default_agent), `opencode debug skill > f.json` (parse the file — piping truncates), `opencode debug agent tech-report-pptx > f.json` and grep `deck_`.
- **Real model run**: `OPENROUTER_API_KEY=... opencode run --agent tech-report-pptx --model openrouter/anthropic/claude-sonnet-5.5 "…"` (needs network access to openrouter.ai).
- **Package for local use**: `git archive --format=zip --prefix=VibeCodingProj_A02/ -o <out>.zip HEAD`, unzip into a clean dir, run selftest there.

## Reporting discipline
Every summary separates: built · rendered & looked at · tested by selftest · loaded by opencode · run with a real model · not verified. Never round up.
