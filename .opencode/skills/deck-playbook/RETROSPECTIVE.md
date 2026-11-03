# Retrospective — how this system was built (2026-11-02/03), mistakes included

Read this to understand *why* the principles exist. Commit ids refer to this repository.

| # | commit | what the user asked / said | what was done | lesson |
|---|---|---|---|---|
| 1 | c1f64c4 | Build "HTML PPT Studio — 24 themes, 31 layouts, 20+ animations" | skill with base CSS, generated themes/layouts, runtime, scaffold script; rendered to check | Render and look before claiming; overview mode first looked empty (animation opacity bug) — found only by looking |
| 2 | 8034cdf | Combine html-ppt-studio + ppt-master + python-pptx into one opencode agent for tech-report PPTX | outline.json contract, python-pptx builder, HTML converter, lint, routes; ppt-master via `setup.sh` (submodule was refused) | One shared data contract makes engines interchangeable; never bypass a refusal, find the clean alternative |
| 3 | 42caa20 | Long description of the preferred look; "完全错误的配色" | light glass theme with gradients, cube hero, workflow DAG | The default demo colours were the problem — ask for/see references early |
| 4 | 2a3f489 | "我给你一些例子" (4 reference images) | `diagram` slide type on a 1000×490 canvas; reproduced all 4 references in HTML + PPTX with shared geometry | Reproducing the references as examples is the fastest way to converge; validators (overlap, off-canvas) catch layout errors before rendering |
| 5 | 088ed25 | Colour constraints (white page, low saturation, 1 main + 1–2 secondary, no gradients…) | flattened the palette, removed pink/teal, ≤3-colour rule, greyed borders | **Over-applied the rule** — the output lost the colour richness the user liked |
| 6 | f0f3883, 0fd3b8b, 6c4549e | "再仔细看看颜色", "颜色还不太对", "看看这里面的颜色和白色背景" | measured reference pixels, recalibrated palette, fixed an HTML CSS-variable bug, adjusted tint coverage | Pixel measurement helped with exact values but missed the obvious: pages had no colour variety. **Look first** |
| 7 | 2fce104 | "你这里头完全没有我图片中的那几个颜色…黄色、紫色、蓝色、绿色" | multi-colour cycle for every card-based layout | Check *every* page type, not just the one you were working on |
| 8 | 8625220 | Palette table from Gemini (indigo/violet/emerald/amber/rose) | implemented exactly | Implementing a spec literally is right — but keep the previous look available to compare |
| 9 | 88437aa | "背景纯白", "不能是截图", "你要设计一个 agent，而不是只做这个" | pure white; native vector icons; `verify_pptx`; `deck.py` CLI + 9 typed tools; subagents; commands; interaction protocol; selftest; architecture doc | The product is the *agent system*; editable-only is a hard, tested rule |
| 10 | b36bdb5 | "不行啊，你后面做的又退回去了，我要的是你之前做出来的这种" | diffed old vs new: indigo ≠ blue, lost gradient headline/glass cubes/shadows/variety; made looks data (`styles/*.json`), restored vivid as default, kept flat; golden regression test | **Regressions come from silent side-effects of fixes** — protect approved looks with goldens |
| 11 | 788bf80, 1817494 | "这种就是我喜欢的" (+ image) | second golden; blended palette so both liked images match; fixed `deck_colors`; **a commit went in with a red selftest** | Record approvals immediately; never commit without "0 failed" |
| 12 | 1721301 | "你是多模态大模型…直接看图片" | `deck_compare`; vision-first rules in prompts | Numbers are evidence, eyes are judgement |
| 13 | 6b9edd3, 6f7bf91 | "你知道我的 api key 吗", "你怎么说你跑了 opencode", "装上 opencode 检查一下" | installed opencode 1.19.5: config, 4 agents, 5 commands, 3 skills, 10 tools load; real model call blocked by network policy (openrouter.ai) | Be literal about what was verified; a truncated pipe once produced a false "skills not loaded" alarm |
| 14 | (this commit) | "你必须要教会他所有你之前做过的事情" | this playbook, golden tool for the agent, prompts/evals updated | Tools without method are not enough — pass down judgement |

## Patterns to remember
- The user communicates mostly by **showing** (images) and by **short reactions**. Treat images as specs and reactions as signals to compare visually, not to guess again.
- Each time a rule was applied globally, something the user liked broke. Prefer adding an option/profile over changing the default.
- The fastest loop that worked: build → preview → look side by side with the reference → fix → lock in.
