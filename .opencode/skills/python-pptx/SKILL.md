---
name: python-pptx
description: Build, edit and QA native editable .pptx files with python-pptx — outline.json → deck with native charts/tables/shapes/notes, theme-matched to html-ppt-studio, plus a linter (overflow, off-slide, notes, fonts) and LibreOffice render check. Use for data-heavy / technical decks, deterministic rebuilds, surgical edits to an existing .pptx, or QA of any .pptx (including ppt-master output).
---

# python-pptx skill

Scripts (run with `python3`, paths relative to this skill dir):

| script | purpose |
|---|---|
| `scripts/outline_to_pptx.py outline.json out.pptx [--theme NAME]` | Build a 16:9 deck. 17 slide types: diagram (free canvas — see tech-report-pptx/reference/diagram.md), hero (left concept / centre 3D cube / right mini-workflow), workflow (DAG with solid/dashed edges, icon nodes), cover, section, agenda, bullets, two-col, kpi, chart (bar/hbar/stacked/line/pie), table, timeline, process, comparison, layers (architecture), code, closing. |
| `scripts/lint_pptx.py deck.pptx [--render]` | QA any pptx. Exit 1 on ERROR. `--render` → `<deck>_render/slide-NN.png` via LibreOffice for visual review. |
| `scripts/theme_tokens.py` | Reads `html-ppt-studio/assets/themes/NAME.css` → RGB tokens (so PPTX == HTML theme). |
| `scripts/diagram_geom.py` | Shared palette / icons / edge routing / validation for `diagram` slides (HTML + PPTX use the same geometry). |
| `scripts/render_icons.py` | Dev-time: re-render `assets/icons/*.png` (white icons for PPTX badges) after adding to `ICONS`. |
| `scripts/_fit.py` | Text-fit estimator used by builder and linter (CJK-aware). |

Clean themes (`--style:clean` in the theme CSS, e.g. `modern-tech`): flat solid fills only (all gradients are suppressed), cards / steps / KPI tiles / chart series cycle through the tone set (blue, purple, green, yellow, orange, pink) as pale tint + tone border; solid near-white background, deep-blue headlines, very light shadows. Cube = native freeform faces; workflow edges = freeform polylines with arrowheads (editable, not glued to nodes — move a node ⇒ re-run the builder). Icons are Unicode glyphs (font "Segoe UI Symbol").

## Guarantees of the builder
Native objects only (editable text, real `buChar` bullets, native charts/tables, no images of text); titles are shapes named `Title`; speaker notes from `notes`; auto-shrinks text (min 11–12pt) instead of overflowing; document properties filled; theme colors from the chosen html-ppt-studio theme.

## Editing an existing deck (surgical)
```python
from pptx import Presentation
prs = Presentation("in.pptx")
for sl in prs.slides:
    for sh in sl.shapes:
        if sh.has_text_frame and "OLD" in sh.text_frame.text:
            for p in sh.text_frame.paragraphs:
                for r in p.runs: r.text = r.text.replace("OLD", "NEW")   # keep runs → keeps formatting
prs.save("out.pptx")
```
Rules: edit run text, not `text_frame.text` (it drops formatting); never reorder slides by hand-editing XML IDs unless you know `sldIdLst`; always re-run `lint_pptx.py --render` and look at the PNGs after any edit.

## python-pptx gotchas
- Units are EMU (914400/in); use `Inches()/Pt()`.
- Blank layout = `prs.slide_layouts[6]`; the default template is 4:3 — set `slide_width/height` for 16:9 (done in the builder).
- Charts: `CategoryChartData`; style via `chart.font`, `plot.series[i].format.fill`; pie colors are per `point`.
- Tables: set `a:tableStyleId` to the "No Style, No Grid" GUID and fill cells yourself for consistent theming.
- LibreOffice rendering ≠ PowerPoint exactly (fonts differ); treat render as a sanity check, not pixel truth.
