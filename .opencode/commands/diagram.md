---
description: 为一页设计架构图 / 流程图 / 概念图（交给 diagram-designer 子 agent）
agent: tech-report-pptx
---
为下面的内容设计一页 `diagram` 幻灯片，并插入到 deck 中（位置若我没说就追加在末尾）：

$ARGUMENTS

委托 diagram-designer 子 agent；它会先读 diagram 手册、写坐标、跑 deck_check 直到 0 错误、预览看图后返回。
