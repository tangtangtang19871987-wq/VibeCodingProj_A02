---
description: 我喜欢这个样子 —— 立刻把它锁定为金标准，以后任何改动都不能偏离
agent: tech-report-pptx
---
我认可的样子（图片路径 / 截图，以及我说的话）：

$ARGUMENTS

做法（见 deck-playbook）：
1. 先看图，用 3–5 句话说出你从图里看到的风格要点，确认你理解对了。
2. 找出它对应 `tech-report-pptx/examples/` 里哪个示例的哪几页（没有就先把示例做成对应的样子）。
3. `deck_golden add`（id、slides、必要时 crop、note 写我的原话和日期）。
4. `deck_golden check` 和 `python3 evals/selftest.py` 都要通过；报告当前输出与它的差距，并用 `deck_compare` 并排给我看。
