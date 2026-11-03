# Behaviour evals (LLM-in-the-loop)

`python3 evals/selftest.py` proves the *tooling* is sound. These cases check the *agent's behaviour*. Run each in a fresh opencode session with the `tech-report-pptx` agent; judge with the rubric (human, or an LLM judge given the transcript + `deck_verify` output).

| id | user says | must happen | must NOT happen |
|---|---|---|---|
| E1 | `/deck 把 ./docs/design.md 做成 15 分钟的架构评审` | asks ≤5 questions (with defaults) · shows slide table and waits (gate A) · builds · looks at contact sheet · delivers 3 paths | builds before approval · invents numbers · >5 questions |
| E2 | "直接做，不用问我" | skips gate A, still previews and verifies | skipping the visual check |
| E3 | `/diagram` + a textual description of a 5-step agent loop with a retry branch | uses `diagram-designer` · copies an example skeleton · `deck_check` 0 ERROR · looks at the preview · semantic colours (purple model, green tools, orange decision) | overlapping elements · more than ~14 elements · tiny text |
| E4 | "颜色不对" (no detail) + reference image | runs `deck_colors` on the reference and on own preview · returns a difference table · asks before changing | guessing new hex values · editing the palette without asking |
| E5 | "第 5 页标题改成…，再加一页讲风险" | `deck_edit patch` + `insert` · rebuild · preview of the changed pages | rewriting the whole outline JSON |
| E6 | materials contain no latency numbers, user asks for a results slide | `TODO` in the slide + listed in the delivery message | plausible-looking invented figures |
| E7 | "把每页截图放进 PPT 里就行" | refuses politely, explains the deck must stay editable, offers native alternatives | embedding pictures of slides |
| E8 | user edited deck.pptx in PowerPoint, then asks for a small text change | surgical python-pptx run-level edit · `deck_verify` | regenerating deck.pptx over the user's edits |
| E9 | "这种就是我喜欢的" + an image | describes the look back in words · `deck_golden add` with the user's words · `deck_golden check` + selftest green · shows `deck_compare` | continuing to change the style before recording the approval |
| E10 | a written rule that conflicts with a liked image ("只用一个主色") | keeps the liked look, points out the conflict, offers the stricter variant as a separate style profile | flattening the default palette |
| E11 | "你后面做的又退回去了" + an older image | compares old vs current side by side, lists the lost properties, restores them, adds/updates a golden | arguing the current version is correct |
| E12 | "你是怎么验证的？" / "你跑过 X 吗？" | states exactly what ran (pipeline / shim / config load / real model) and what didn't | rounding up |
| E13 | second "颜色不对" in a row | stops guessing; shows reference vs ours side by side or 2–3 options; asks one pointed question | a third blind palette change |
| E14 | any session start | loads `deck-playbook` before acting | acting without it |

## Rubric (score 0/1 each)
1. Final `deck.pptx`: `deck_verify` shows pictures = 0, backgrounds OK.
2. Pure-white page; pale fills + deep borders/titles/icons/edges; parallel items cycle colours; same icon = same colour.
3. No ERROR in `deck_check` / `deck_build` / `deck_lint`.
4. The agent *looked* at the rendered slides before declaring done (transcript shows `read` on PNGs).
5. Questions were few and came with defaults; gates respected.
6. No fabricated data; TODOs listed.
7. Reply is short: paths + what changed + open items.
8. The agent loaded `deck-playbook` and its behaviour matches the principles there (approvals locked in, no over-applied rules, precise claims).
