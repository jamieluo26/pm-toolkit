# 评审与修订

任务与版本统一记录在 task.json。输入保留调用者内容，公开前须自行核对来源与脱敏。

## 输入

前版任务、反馈、人工处理决定、修订版任务。

## 操作

逐条记录反馈及处理理由；采纳项关联准确变更路径；拒绝项保留理由；待定与冲突继续可见；修订后重生成并复核功能意图。

## 输出

feedback.json、decisions.json、review.json、REVIEW.md，修订版原型及PRD。

## AI 与人工停点

feedback-intent-preservation-review 辅助核对载体变化后的功能承接；决定和真实批准由人提供。

## 空白与已填材料

空白材料：templates/design-handoff.md；已填例：examples/lifecycle/feedback.json 与 decisions.json。

## 成功 缺失 冲突

成功：顶部筛选承接原进度/主题/空态意图。缺失：未处理反馈返回HOLD。冲突：运行 pending-decisions.json、conflict-decisions.json 两个反例；不能删反馈换取完成。

[完整步骤](../../docs/lifecycle.md) · [统一输入合同](../../docs/task-spec.md)
