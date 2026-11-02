# HTML PPT Studio

An AgentSkill for building professional HTML presentations — **25 themes, 34 layouts, 26 animations**, zero dependencies.

- Skill entry point: [`html-ppt-studio/SKILL.md`](html-ppt-studio/SKILL.md)
- Live demo (all layouts, press `T` to switch themes, `O` for overview): open `html-ppt-studio/examples/demo-all-layouts.html`
- Quick start: `python3 html-ppt-studio/scripts/new_deck.py --out my-deck.html --inline --theme aurora --layouts cover,bullets,kpi-row,closing`
- Install as a Claude skill: copy the `html-ppt-studio/` folder into `~/.claude/skills/` (or a project's `.claude/skills/`).

## Technical-report PPTX agent (opencode)

An opencode agent that fuses three engines around one `outline.json`:

| Engine | Role |
|---|---|
| `html-ppt-studio` | HTML design draft / live presenter; theme source of truth (25 themes) |
| `python-pptx` skill | deterministic native PPTX (charts, tables, code, architecture layers) + lint/render QA |
| [`ppt-master`](https://github.com/hugohe3/ppt-master) (third-party, MIT) | high-design native PPTX route (templates, imagery, animation, narration) |

```
./setup.sh            # installs python deps, fetches ppt-master (unmodified) into vendor/, links it as a skill
opencode              # agent `tech-report-pptx` is the default (see opencode.json)
```
Pipeline: intake → `outline.json` → HTML draft → ⛔ your approval → Route A (python-pptx) or B (ppt-master) → lint + render QA → deliver.
Without `setup.sh` Route A and the HTML draft still work; Route B is reported as unavailable.
See `.opencode/agents/tech-report-pptx.md`, `.opencode/skills/tech-report-pptx/SKILL.md`.
