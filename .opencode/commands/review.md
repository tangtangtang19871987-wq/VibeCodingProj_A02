---
description: 对 deck 做一次独立的视觉与风格评审（deck-reviewer 子 agent），并逐条修复
agent: tech-report-pptx
---
评审并修复这份 deck：

$ARGUMENTS

委托 deck-reviewer 子 agent 渲染并逐页看图，按评审清单给出问题列表；然后你按清单逐条修复（deck_edit → deck_build），再复审一次。
