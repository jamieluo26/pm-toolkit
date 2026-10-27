# 验证与交付

任务与版本统一记录在 task.json。输入保留调用者内容，公开前须自行核对来源与脱敏。

## 输入

准确当前任务、待执行检查、实际观察和失败/复验记录。

## 操作

复制 observations-template.json，逐项执行后填写观察与引用；保留失败链；用deliver重新核对当前版本、证据层与评审输入，交给接手者。

## 输出

acceptance-results.md/json、defects.json、delivery.md、handoff.docx及完整目录清单。

## AI 与人工停点

supplied-acceptance-evidence-review 仅审给定证据；浏览器、内容、视觉和人的验收分别记录。

## 空白与已填材料

空白材料：templates/delivery-and-release.md；输出自带 observations-template.json；已填技术例仅在实际执行后形成。

## 成功 缺失 冲突

成功：每项当前观察与检查相符且引用可核。缺失：not_run/缺引用保持HOLD。冲突：旧SHA或证据层不符保持HOLD；fail到pass须追加supersedes复验链。

[完整步骤](../../docs/lifecycle.md) · [统一输入合同](../../docs/task-spec.md)
