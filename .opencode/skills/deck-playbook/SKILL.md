---
name: deck-playbook
description: The complete methodology, house-style knowledge, feedback playbook, troubleshooting notes and lessons learned from building this tech-report PPTX system with the user. Load FIRST in every session that makes, revises, restyles or reviews a deck, handles a colour/style complaint, or changes the system itself (prompts, tools, styles, scripts).
---

# Deck playbook — how to do this job right (read before acting)

This skill is the memory of how the system was built, step by step, with this user: what they want, what they rejected, what went wrong and how it was fixed. The tools (`deck_*`) do the mechanics; **this playbook is the judgement**. Skipping it means repeating mistakes that already cost the user many rounds.

## Read order
1. The **principles** below (always).
2. `STYLE_GUIDE.md` + look at `references/` and `evals/golden/` images (always before any visual work).
3. `METHOD.md` — the end-to-end procedure (new deck, diagram design, build/look loop, delivery).
4. `FEEDBACK_PLAYBOOK.md` — what the user's typical sentences mean and what to do (whenever the user gives feedback).
5. `TROUBLESHOOTING.md` — known technical traps (whenever something looks wrong or fails).
6. `DEV_PLAYBOOK.md` — how to change the system safely (only when changing prompts / tools / styles / scripts).
7. `RETROSPECTIVE.md` — the full story of the build, mistakes included (when in doubt why a rule exists).

## The principles (each one was learned the hard way — see RETROSPECTIVE.md)
1. **The deliverable is a native, editable .pptx.** Text boxes, native charts/tables, shapes, vector icons. Never a picture of a slide, never screenshots inside the deck. `deck_verify` must report `pictures: 0`.
2. **Look first, measure second.** You are multimodal: judge style by LOOKING (`deck_compare` puts reference and ours side by side; read the PNG). Pixel statistics (`deck_colors`, golden signatures) are supporting evidence and tripwires, never the main judgement. The colour mistakes in this project were all visible to the eye and were missed while staring at numbers.
3. **What the user says they like is the specification.** Images they approve beat any written rule. When they approve a look, lock it in immediately: `deck_golden add` with their words in the note — before changing anything else.
4. **Never over-apply a constraint.** A written rule ("一个主色加一两个辅助色", "不要渐变") is the user describing taste; it is not a licence to flatten everything. If a rule seems to conflict with an image they liked, keep the liked look and ask; or offer the stricter version as a separate style profile. Flattening the whole palette once made every page washed-out and single-coloured — the user had to fight to get colour back.
5. **Don't regress.** Before and after any style change: compare against the goldens (`deck_golden check`) and against what the user last approved (git history). "你后面做的又退回去了" happened because each fix silently undid an earlier liked property.
6. **Colour richness with meaning.** Pages are never one colour. Parallel items cycle blue → purple → green → orange → pink; components keep a semantic colour (purple = model/agent, green = tools/storage, orange = decision/state/answer, pink = memory, blue = input/data); the same icon keeps the same colour across the deck. "Blue" must be a real blue (hue ≈ 210–230°), clearly different from purple — indigo is not blue to this user.
7. **Style is data.** Palettes and looks live in `html-ppt-studio/assets/styles/*.json`; theme CSS is generated (`gen_modern_themes.py`). Never hand-edit hex values in renderers or prompts; never invent hexes in conversation.
8. **Every build is followed by a visual check.** `deck_build` → `deck_preview` → read the contact sheet and the changed pages → fix → repeat. Do not say "完成" without having looked.
9. **Say exactly what was verified.** Distinguish: "the Python pipeline ran", "the TS tool wrappers ran through a shim", "opencode loaded the config", "a real model session ran". Never let a reader infer a stronger claim than what happened. When the environment blocks something (e.g. network), say so plainly and do not substitute mocked results.
10. **Green before commit.** Run `python3 evals/selftest.py` and only commit when it reports 0 failed (a red commit happened once because a shell pipeline ignored the exit code).
11. **Small, structured edits.** Use `deck_edit` (patch / insert / move) instead of rewriting outline JSON; the outline is the single source of truth; regenerate outputs from it.
12. **Few questions, with defaults; respect the gates.** ≤5 questions in one message, each with a proposed default; show the storyboard and wait (gate A) unless the user said "直接做"; deliver and wait for feedback (gate B).
13. **No fabricated data.** Missing numbers → `TODO` in the slide and listed in the delivery message.
14. **When unsure what the user means, show, don't guess repeatedly.** Two failed guesses in a row = stop, produce a side-by-side or a small set of options, and ask a pointed question.

## Files in this skill
| file | what it holds |
|---|---|
| `STYLE_GUIDE.md` | the liked look in words, what was rejected, palette roles, reference images and goldens |
| `METHOD.md` | the full procedure: intake → storyboard → diagrams → build/look loop → review → delivery → iteration |
| `FEEDBACK_PLAYBOOK.md` | the user's real sentences → meaning → correct action |
| `TROUBLESHOOTING.md` | technical traps found while building (HTML, PPTX, LibreOffice, opencode, environment) |
| `DEV_PLAYBOOK.md` | where everything lives and how to change it safely (styles, slide types, icons, tools, goldens, packaging) |
| `RETROSPECTIVE.md` | the chronological story with commit ids, mistakes and fixes |
| `references/` | the user's original reference images (the source of the style) |
