# Feedback playbook — the user's real sentences and the right response

All entries below happened while building this system. The "wrong move" column is what was actually done first; the "right move" is what finally worked.

| the user said | what it really meant | wrong move (don't) | right move |
|---|---|---|---|
| "HTML PPT Studio — AgentSkill with 24 themes…" (just a title) | build that skill | — | build it, verify by rendering, commit |
| "把三者相容有机地结合在一个 opencode 的 agent 里" | one agent orchestrating html-ppt-studio + python-pptx + ppt-master | — | shared outline.json contract, clear role per engine, routes, QA gate |
| "我最常用的风格是…（长描述）… 完全错误的配色" | the demo colours (dark/default) are wrong; they described a light AI-tech look | — | make a light default theme; ask for / use reference images |
| "我给你一些例子" + images | the images ARE the spec | approximating from memory | reproduce the reference slides as examples, side by side |
| "配色约束：…一个主强调色和一至两个辅助色…" | taste guidance (clean, not flashy) | flattening every colour, cutting to 3 tones, removing pink, greying borders | keep the liked multi-colour look; apply the spirit (white page, pale fills, no neon/dark) and ask if a rule conflicts with an image |
| "再仔细看看颜色" / "颜色还不太对" | colours visibly differ from the images | more pixel statistics, more guesses | LOOK at reference vs ours (`deck_compare`), describe the differences in words, then fix |
| "你这里头什么也没有啊 … 有黄色、紫色、蓝色、绿色" | ordinary slides are one colour | — | cycle tones on every card-based layout; check every page type, not only diagrams |
| (pastes a palette table from Gemini) | a concrete palette to try | — | implement it exactly — but as a style profile, so it can be compared with the previous look |
| "非常好，但是我希望背景色是纯白" | keep everything, page background → #FFFFFF | — | change only the background; verify bg in `deck_verify` |
| "你后面做的又退回去了，我要的是你之前做出来的这种" + old image | a later change lost liked properties | arguing that the current one follows the constraints | diff old vs new by eye, list what was lost (true blue, gradient headline, glass cubes, colour variety), restore them, lock the old image in as a golden |
| "这种就是我喜欢的" + image | approval | — | `deck_golden add` immediately with the user's words; confirm the current output matches it by `deck_compare` |
| "你是多模态大模型，你可以直接看图片" | stop relying on pixel numbers | — | vision first; numbers only as supporting evidence |
| "你知道我的 opencode 用的 api key 吗" | asking whether you have access | searching for secrets | say no, explain where opencode keeps keys, warn not to paste/commit them |
| "那你怎么说你跑了 opencode 的" | a previous summary implied more than was done | — | state precisely what ran (pipeline / shim / config load / real model) and what didn't |
| "我没有看到有什么环境菜单" / "我在手机端" | can't change cloud settings now | repeating desktop instructions | give the mobile-browser path, the "later on a computer" path and the local-run path; continue other work |
| "打包成可下载的压缩包" | wants to run locally | — | `git archive` the committed tree, unzip into a clean dir, run selftest, then send |
| "你必须要教会他所有你之前做过的事情" | the agent must inherit the method, not just tools | shipping only tools | this playbook + golden tool + prompts that reference it + evals for the lessons |

## Generic rules derived from the table
- A short complaint ("不对") after two attempts means you are guessing: switch to showing (side-by-side, 2–3 options) and ask one pointed question.
- Approval is an event: record it (golden + note) before doing anything else.
- When the user restates a preference with an image, the image wins over every earlier sentence.
- Answer questions about yourself and the environment literally and precisely.
