# Interaction protocol (agent-facing)

The user steers the work in conversation. The agent's job is to **converge fast with few questions**, keep the user in control at two gates, and never surprise them.

## Stages and gates
| # | stage | agent does | user sees | gate |
|---|---|---|---|---|
| 0 | intake | read materials; ask only what is missing (≤5 questions, one message); if a reference image is given → `deck_colors` | questions with proposed defaults ("默认：20 分钟、中文、modern-tech 风格，可以吗？") | — |
| 1 | storyboard | delegate `deck-planner` → outline.json, `deck_check` | slide table: # · type · title (+ TODOs) | **GATE A** — approve / edit |
| 2 | diagrams | `diagram-designer` per diagram slide | one line per diagram: what it shows | — |
| 3 | build | `deck_build` → `deck_preview` → look at PNGs → fix (≤3 rounds) | — | — |
| 4 | review | `deck-reviewer` → fix list → rebuild | — | — |
| 5 | deliver | paths of deck.pptx / draft.html / outline.json, slide count, TODOs/assumptions | short summary | **GATE B** — feedback |
| 6 | iterate | classify feedback → targeted edit → build → preview | what changed | back to GATE B |

Skip gate A only if the user said "直接做" / "just do it". Never skip the visual check in stage 3.

## Question templates (propose defaults; don't interrogate)
- 目标：这份汇报要让听众做什么决定？（我暂定：……）
- 听众与时长：……（默认：工程负责人，20 分钟 ≈ 12 页）
- 材料：有代码库/文档/数据吗？给我路径；没有的数字我会标 TODO。
- 必须出现的图：架构图/流程图/对比表……（我建议：……）
- 语言与品牌：默认中文、modern-tech（纯白、靛蓝/紫/绿/橙/粉）；有品牌模板请说明。

## Feedback classification → action
| user says | class | action |
|---|---|---|
| "第 5 页标题改成…/加一条…" | content | `deck_edit patch N` |
| "太挤 / 拆开 / 换成时间线" | layout | split slide, change type, or move coordinates (diagram) |
| "顺序调一下" | order | `deck_edit move` |
| "加一页讲…" | new slide | planner for the slide → `deck_edit insert` |
| "颜色不对 / 照这张图" | colour | **never guess**: `deck_colors` on reference + on our preview → difference table (hex, area share, border weight, hue assignment, icon style) → propose → confirm. The palette is a constant; changing it is a developer action |
| "字太小 / 太大" | typography | diagram: `scale` on nodes; otherwise shorten text; never < 10pt |
| "我在 PowerPoint 里改过了，帮我继续" | external edit | do NOT rebuild over it: use python-pptx surgical edit (run text only) + `deck_verify` |

## Done means
`deck_build` summary has no ERROR · `deck_verify`: pictures 0, background OK · contact sheet inspected · reviewer verdict "通过" (or remaining items listed to the user).
