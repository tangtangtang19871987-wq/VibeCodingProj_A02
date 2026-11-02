# Tech-report PPTX agent — architecture

An [opencode](https://opencode.ai) agent system that turns a conversation about technical material into an **editable PowerPoint** (plus a presentable HTML draft), in one consistent house style.

## 1. Requirements → mechanisms → proof
| requirement (from the user) | mechanism | proof |
|---|---|---|
| Output is a **real, editable .pptx**, never screenshots | python-pptx builder emits only native text boxes / shapes / connectors-as-freeforms / charts / tables; icons are freeform vectors; `verify_pptx.py` fails on any `<p:pic>` | `evals/selftest.py` (0 pictures, 0 media) · `deck_verify` |
| House style: **pure-white page**, true blue / violet / green / amber / pink, pale gradient fills + vivid outlines + coloured soft shadows + glass cubes (**`vivid`**, default); flat Tailwind variant kept as **`flat`** | **style profiles as data** (`html-ppt-studio/assets/styles/*.json`) read by `diagram_geom.use()`; `gen_modern_themes.py` generates the HTML theme CSS from the same JSON | verify (white bg, palette audit) + **colour regression**: hue coverage + distance to the golden reference image (`evals/golden/`) |
| Colours that **vary by meaning**, consistent across slides | tone cycle for parallel items; semantic tones for diagrams; `check_outline` warns when one icon changes colour | selftest + check |
| Rich architecture / flow diagrams like the reference images | `diagram` slide type on a 1000×490 canvas: nodes (round/pill/diamond), lanes, notes, panels, cubes, rounded coloured edges | validation: overlaps, out-of-canvas, edges crossing nodes |
| The agent works **with the user interactively** | staged protocol with two approval gates, feedback classification, slash commands | `reference/interaction.md`, `evals/cases.md` |
| Reliable behaviour, not luck | typed tools instead of free-form shell; validators that refuse bad input; subagents with narrow jobs; visual self-check; evals | `evals/` |

## 2. Shape of the system
```
user ─ chat / slash commands (/deck /revise /diagram /review /colors)
        │
 ┌──────▼────────────────────────────────────────────────────────────────────┐
 │ primary agent  tech-report-pptx     (prompt = hard rules, workflow, style) │
 │   ├─ subagent deck-planner        materials → outline.json (story arc, notes, TODOs)
 │   ├─ subagent diagram-designer    description → one `diagram` slide, validated + looked at
 │   └─ subagent deck-reviewer       read-only visual / style / content critique
 └──────┬────────────────────────────────────────────────────────────────────┘
        │ typed tools  (.opencode/tools/deck.ts → deck.py subcommands)
        ▼
 deck_catalog · deck_create · deck_check · deck_edit · deck_build · deck_preview · deck_compare · deck_verify · deck_lint · deck_colors
        │
        ▼                     outline.json  = single source of truth (schema + examples)
 ┌──────────────┬─────────────────────────┬─────────────────────────────┐
 │ check_outline│ outline_to_html (draft)  │ outline_to_pptx (python-pptx) │ → deck.pptx (native, editable)
 └──────────────┴─────────────────────────┴─────────────────────────────┘
        shared geometry/palette/icons: diagram_geom.py · svgpath.py · theme_tokens.py · _fit.py
        QA: verify_pptx.py (editable + style) · lint_pptx.py (layout) · LibreOffice+pdftoppm render (preview)
```

## 3. Components
- **Agent prompt** (`.opencode/agents/tech-report-pptx.md`): non-negotiable rules (editable-only, no fabrication, measure colours, look at renders, outline is the source of truth), workflow, style table, reply style.
- **Subagents** (`.opencode/agents/*.md`): narrow prompts + restricted tools (reviewer is read-only; planner/designer cannot run shell).
- **Commands** (`.opencode/commands/*.md`): the user's entry points.
- **Tools** (`.opencode/tools/deck.ts`): 10 typed wrappers around `deck.py`. Style judgement is **vision-first**: `deck_compare` puts reference and output in one image for the model to look at; `deck_colors` is supporting evidence only. The Python CLI is the tested layer; the TS file is thin.
- **Skills** (`.opencode/skills/`): `tech-report-pptx` (orchestration, outline contract, diagram manual, interaction protocol, examples) · `python-pptx` (builder, linter, verifier, surgical-edit recipes) · `html-ppt-studio` (25 themes, 34 layouts, 26 animations; HTML draft) · `ppt-master` (optional third-party route, installed by `setup.sh`, never edited).
- **Data contract**: `outline.json` (`schema/outline.schema.json`, 17 slide types). Humans and agents edit this; both outputs are regenerated from it.

## 4. What is (and is not) used to produce the PPTX
| tool | used? | role |
|---|---|---|
| **python-pptx** (+ lxml via python-pptx) | **yes — the builder** | creates every slide object; XML touch-ups for bullets, alpha, shadows, round caps |
| LibreOffice (`soffice`) + poppler (`pdftoppm`) | optional, QA only | render slides to PNG so the agent can look; nothing from this enters the deck |
| Pillow | optional | contact sheet, `deck_colors` |
| Playwright / Chromium | dev/QA only | screenshots of the HTML draft; not needed at run time |
| PptxGenJS (Node) | **no** | not needed — python-pptx covers charts, tables, freeforms, groups, notes |
| ppt-master | optional route | third-party skill with its own pipeline; not installed here, never modified |
| images / screenshots inside the PPTX | **never** | `deck_verify` fails the build |

## 5. Interaction protocol (summary — full text in `reference/interaction.md`)
intake (≤5 questions, defaults offered) → storyboard table → **gate A** → diagrams → build + *look* → review → deliver → **gate B** feedback loop. Feedback is classified (content / layout / order / new slide / colour / typography / external edit) and mapped to a targeted tool call; colour complaints trigger *measuring*, not guessing.

## 5b. Style profiles (why the look can no longer drift silently)
A look is a JSON file: tones (fill / border / solid), cycle order, gradients on/off, shadow kind, gradient heading, glass-cube gradients. Renderers call `G.use_for_theme(theme)`; `theme_tokens` reads `--deck-style` from the theme CSS. Adding a look = new JSON + `python3 html-ppt-studio/scripts/gen_modern_themes.py`. `evals/selftest.py` guards the default look: blue must be a real blue (hue 195–235°, ≥25° from purple), all five hues present, and the colour-mix of a rendered deck must stay within 0.25 of `evals/golden/vivid-reference.png` (flat scores 0.43).

## 6. Quality gates
`deck_check` (input) → `deck_build` (refuses on errors) → `deck_verify` (editable + style) → `deck_lint` (layout) → visual inspection → reviewer. `python3 evals/selftest.py` runs 45 checks incl. negative cases and colour-regression guards (two golden reference renders in `evals/golden/`); `evals/cases.md` holds 8 behaviour evals with a rubric.

## 7. Known limits (be honest with users)
- **Not exercised inside a real opencode session** (not installed in the dev sandbox). Verified instead: the Python CLI end-to-end, and the TypeScript tools executed through a shim that stubs `tool()` and `Bun.spawn`. Directory names follow current opencode conventions (`agents/ commands/ tools/ skills/`); if your version expects singular names, rename.
- Rendering was checked with LibreOffice, not PowerPoint — fonts and shadows differ slightly.
- Connectors are freeform polylines with arrowheads (editable, but not glued to nodes). Cubes are flat isometric shapes, not real 3D. Icons are our own simple vector set.
- `ppt-master` route untested (needs `./setup.sh`).

## 8. Extending
- **New slide type**: add handler in `outline_to_pptx.py` + `outline_to_html.py`, entry in `deck.py SPECS`, `check_outline.TYPES/REQ`, schema enum, example slide, selftest picks it up via the example.
- **New icon**: add its 24×24 stroke path to `diagram_geom.ICONS` (rendering is automatic — vector).
- **Palette change** (developer action): edit `TONES`, the CSS block generated in `themes.all.css`, `verify_pptx` allowances; run selftest.
- **New tool**: add a subcommand to `deck.py`, a wrapper export in `deck.ts`, mention it in the agent prompt.
