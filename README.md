# HTML PPT Studio

An AgentSkill for building professional HTML presentations — **25 themes, 34 layouts, 26 animations**, zero dependencies.

- Skill entry point: [`html-ppt-studio/SKILL.md`](html-ppt-studio/SKILL.md)
- Live demo (all layouts, press `T` to switch themes, `O` for overview): open `html-ppt-studio/examples/demo-all-layouts.html`
- Quick start: `python3 html-ppt-studio/scripts/new_deck.py --out my-deck.html --inline --theme aurora --layouts cover,bullets,kpi-row,closing`
- Install as a Claude skill: copy the `html-ppt-studio/` folder into `~/.claude/skills/` (or a project's `.claude/skills/`).

## Technical-report PPTX agent (opencode)

An agent *system* (not just a script): primary agent + 3 subagents + 5 slash commands + 9 typed tools + 4 skills, producing a **native, editable .pptx** (zero pictures) and a presentable HTML draft from one `outline.json`, in a pure-white house style with indigo / violet / emerald / amber / rose pale fills and deep borders.

- Design, requirements→mechanisms, tool inventory, limits: [`ARCHITECTURE.md`](ARCHITECTURE.md)
- Check it works: `python3 evals/selftest.py` (35 deterministic checks) · behaviour evals: [`evals/cases.md`](evals/cases.md)
- Use it: `./setup.sh` (installs python-pptx; fetches optional ppt-master) → `opencode` → `/deck <your topic or materials>`
- Without opencode, the same pipeline: `python3 .opencode/skills/tech-report-pptx/scripts/deck.py build output/<slug>/outline.json`
