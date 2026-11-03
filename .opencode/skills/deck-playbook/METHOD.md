# Method — from request to delivered deck

## 0. Before anything
- Load this playbook; skim `STYLE_GUIDE.md`; look at `references/` and `evals/golden/` images once per session.
- `deck_catalog all` to know slide types, palette, icons.

## 1. Intake (one message, ≤5 questions, each with a default)
Ask only what you cannot infer from the materials:
- 目标：听众要做什么决定？（暂定：…）
- 听众与时长（默认：工程负责人，20 分钟 ≈ 12 页）
- 材料路径（代码库 / 文档 / 数据）；没有来源的数字会标 TODO
- 必须出现的图（架构图、流程图、对比表…）
- 语言与风格（默认：中文，modern-tech / vivid，纯白页面）
If the user attaches a reference image: look at it, describe its style in 3–5 bullets back to them, and say which golden/profile it matches.

## 2. Storyboard (delegate to `deck-planner`)
- Arc for technical reports: decision wanted → problem with evidence → approach/architecture → results (numbers) → trade-offs/risks → plan → decision/ask.
- One idea per slide; title = full-sentence takeaway (≤24 CJK chars); ≤5 bullets; ≤30 words per card; `notes` 60–120 words (how to say it).
- Slide type by content shape: numbers → kpi/chart/table; sequence → timeline/process; system → layers or diagram; branches/loops/lanes/annotations → diagram; contrast → comparison; snippet → code; opener → hero; end → closing.
- Show the table (序号 | 页型 | 标题), list TODOs, **wait for approval** (skip only if the user said "直接做").

## 3. Diagram slides (delegate to `diagram-designer`)
Canvas 1000×490 units. The method that worked:
1. **Start from an example skeleton** in `tech-report-pptx/examples/diagrams.example.json` (opener / sources→builder→model→output / decision flow / lanes) — copy coordinates, then change content. Designing from scratch produced overlaps every time.
2. **Inventory first**: list every element with kind, tone (by meaning), icon (same icon = same colour), label (≤14 CJK) and sub (≤24 CJK).
3. **Then coordinates**: gaps ≥ 8 units; text ≥ 12 units (≈10 pt); node height ≥ 36; keep ≤ ~14 elements; on sparse slides set `scale: 1.3–1.6` on nodes and lanes instead of leaving tiny text in big boxes.
4. **Edges**: fan-in = same `ts`, different `ti` (0.1…0.9) and different `mid`; merge = same `ti` + same `mid`; loop = dashed with `fs:l, ts:l, bulge:30` or explicit orthogonal `via`; use `fs/ts` when an edge would overlap another (e.g. leave from the bottom, enter at the side). Never call the target-side fraction `to` — `to` is the target id; the fraction key is `ti`.
5. `deck_check` → fix every ERROR (overlap, out-of-canvas, unknown icon/tone, edge crossing a node).
6. `deck_preview` the page and **look**: overlaps, clipping, arrows through nodes, label chips covering lines, colours matching meaning, balanced whitespace. Up to 4 rounds. Too dense → split the slide, never shrink below 10 pt.

## 4. Build / look loop (every time)
`deck_build` → read the JSON summary (verify: pictures 0, background OK; lint: 0 ERROR) → `deck_preview` → **read contact_sheet.png** and every changed page → fix via `deck_edit` → rebuild. Typical things only the eye catches: a single-colour page, indigo that looks purple, a wrapped title, a cube overlapping text, a gradient that turned into a hard-edged blob in LibreOffice.

## 5. Review (delegate to `deck-reviewer`)
Reviewer compares against references/goldens with `deck_compare`, runs verify + lint, reads every page and returns a numbered fix list (page · symptom · concrete fix). Apply, rebuild, re-review once.

## 6. Delivery (short)
Paths (`deck.pptx`, `draft.html`, `outline.json`), slide count, style used, TODOs/assumptions, what you could not verify. No re-narration of the slides, no JSON dumps.

## 7. Iteration
Classify the feedback with `FEEDBACK_PLAYBOOK.md`, make the smallest change that addresses it, rebuild, preview, look, report what changed. If the user approves a look → `deck_golden add` right away.

## 8. Editing a deck the user already changed in PowerPoint
Do not regenerate over it. Use python-pptx run-level edits (see `python-pptx` skill), then `deck_verify` and `deck_preview`.
