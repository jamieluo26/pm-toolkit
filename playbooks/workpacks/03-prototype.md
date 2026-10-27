# 原型与 PRD

任务与版本统一记录在 task.json。输入保留调用者内容，公开前须自行核对来源与脱敏。

## 输入

同一任务的有效范围、规则、需求和界面规格。

## 操作

运行 pm_task.py build；打开 journey.html 与 prototype.html；对照PRD、检查计划和Word的任务ID/版本。

## 输出

prototype.html、PRD.md、acceptance.md、trace.json、document-source.json、handoff.docx。

## AI 与人工停点

人工操作页面并看排版；工具只核同源和有序内容，不生成真人验收。

## 空白与已填材料

空白材料：templates/task.json；已填例：examples/lifecycle/before.json；第二类：examples/request-flow/spec.json。

## 成功 缺失 冲突

成功：规格变更后所有制品在新目录同源生成。缺失：字段/值非法退出2。冲突：手改PRD或Word后check拒绝；选择回写源规格或保留为评审建议，不自动双向合并。

[完整步骤](../../docs/lifecycle.md) · [统一输入合同](../../docs/task-spec.md)
