# 范围与规格

任务与版本统一记录在 task.json。输入保留调用者内容，公开前须自行核对来源与脱敏。

## 输入

产品简报、已给定的对象/消费者、规则与范围决定。

## 操作

列出纳入/排除及理由；定义字段、默认、异常、边界与状态；把需求、规则、依据和检查用稳定ID关联。

## 输出

task.json 的 scope、rules、requirements、prototype；rules.md 与 trace.json。

## AI 与人工停点

用 declared-impact-coverage-review 核对给定关系；用 requirement-acceptance-trace-review 检查正反向追踪。

## 空白与已填材料

空白材料：templates/requirement-and-interaction.md；已填例：before.json 的 scope/rules/requirements。

## 成功 缺失 冲突

成功：每条检查回指需求，规则双向对应。缺失：缺来源/悬空ID拒绝输入。冲突：互斥规则未决时不生成已确认结论；不声称发现清单外的消费者。

[完整步骤](../../docs/lifecycle.md) · [统一输入合同](../../docs/task-spec.md)
