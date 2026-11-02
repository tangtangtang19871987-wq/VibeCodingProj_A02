# Project: tech-report PPTX agent

- Agent: `.opencode/agents/tech-report-pptx.md` (select with Tab in opencode, or default via `opencode.json`).
- Skills (`.opencode/skills/`): `tech-report-pptx` (orchestrator) · `html-ppt-studio` (→ `html-ppt-studio/`) · `python-pptx` · `ppt-master` (third-party, installed by `./setup.sh` into `vendor/`, never edit).
- Contract between engines: `output/<slug>/outline.json` (schema: `.opencode/skills/tech-report-pptx/schema/outline.schema.json`).
- Quick check: `python3 .opencode/skills/python-pptx/scripts/outline_to_pptx.py .opencode/skills/tech-report-pptx/examples/outline.example.json /tmp/ex.pptx && python3 .opencode/skills/python-pptx/scripts/lint_pptx.py /tmp/ex.pptx --render`
