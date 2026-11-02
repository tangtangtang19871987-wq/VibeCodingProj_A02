---
description: 按我的反馈修改已有的 PPT（改内容 / 版式 / 顺序），自动重建并预览
agent: tech-report-pptx
---
修改已有的 deck。目标 outline（若没写就用 output/ 下最近修改的 outline.json）和我的反馈：

$ARGUMENTS

用 deck_edit 做结构化修改（不要整份重写 JSON），然后 deck_build → deck_preview，看图确认，再汇报改了什么。
