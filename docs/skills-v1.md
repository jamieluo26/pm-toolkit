# 六项文字 Skill 的使用与当前状态

本文件对应 v1.0 本地工作包。两项沿用原公开树，四项为本版新增；四项新增树完整治理与六次实际显式调用均已通过。不要把目录存在解释为已安装。

本轮已完成六次准确树的实际显式供料调用，均有真实 final；产品手册调用实际接收前五份新草案。四项新增树目前均取得当前完整治理PASS，原18个用例逐套通过，未拼接历史结果。调用成功与草案内容、完整治理分别记录；草案中的未知和证据缺口不升级为已批准或已验收。准确层次见[验证摘要](verification-v1.md)。

## 按任务选一项

| Skill | 提供哪些材料 | 得到什么草案 | 人工核对位置 |
|---|---|---|---|
| [meeting-decision-evidence](../skills/meeting-decision-evidence/SKILL.md) | 明确范围的讨论/会议文字及来源位置 | 决定、分歧、提议、上下文演变与引用 | 原句、完整人物/说话人标签、决定状态与待确认人 |
| [declared-impact-coverage-review](../skills/declared-impact-coverage-review/SKILL.md) | 给定对象、消费者、纳入/排除及理由 | 范围关系、缺口和冲突 | 清单是否真实完整、未给消费者未知、排除依据 |
| [requirement-acceptance-trace-review](../skills/requirement-acceptance-trace-review/SKILL.md) | 需求、检查、关系及版本 | 正反向缺口与冲突 | 是否是正确任务与版本、关系的业务意义 |
| [feedback-intent-preservation-review](../skills/feedback-intent-preservation-review/SKILL.md) | 前后功能/载体、反馈、适用处理决定 | 功能意图承接、取消依据与未决项 | 载体移除是否误取消意图、真实操作是否仍可用 |
| [supplied-acceptance-evidence-review](../skills/supplied-acceptance-evidence-review/SKILL.md) | 条件×状态、预期与给定实际观察 | 证据覆盖、错层、缺失与未知 | 引用目标、实际执行、动态值与未覆盖条件 |
| [product-asset-handbook](../skills/product-asset-handbook/SKILL.md) | 版本、规则、决定、制品和已给证据 | 手册、历史变化与交接索引 | 当前需求声明/实际能力/生产状态的区别、过期材料 |

## 显式供料

在自己的获准 AI 宿主中，提供完整 SKILL.md 与准确材料，并明确这次只审什么。例如：

```text
请按给定的 requirement-acceptance-trace-review/SKILL.md 审阅。
本次材料：task.json、PRD.md、trace.json、acceptance.md。
只核对给定范围的关系与引用，区分声明、已给证据和未验证。
保留缺失、冲突与待确认项；不要操作原项目或把草案当批准。
```

材料可以是你明确提供的文件或文字；目录本身不会让工具自动读取整个项目。先确认宿主支持的供料方式、账号、权限和费用；不要提供超出授权的公司或个人资料。本地生成 CLI 不调用模型。

## 阅读任务的供料位置

- 讨论/证据：`examples/lifecycle/source-notes.md`、before.json、evidence.md。
- 影响范围：before.json / after.json 中的 scope、rules 和 requirements。
- 需求追踪：当前任务的 PRD.md、trace.json 与 acceptance.md。
- 意图承接：前后任务、feedback.json、decisions.json、REVIEW.md。
- 验收证据：当前版本 observations.json、acceptance-results、browser-observations.md。
- 产品资产：原始任务与决定、delivery、release-notes、product-handbook、retrospective，以及明确标为 AI 草案的前序审阅输出。

不要只给最后一份摘要便推定它已包含全部权威材料。任何来源未见、版本未知或引用无法核实的部分，继续保留未知；前序 AI 草案不成为新的事实来源。

## 验证分层

| 层次 | 能证明什么 | 不能替代什么 |
|---|---|---|
| 准确树静态与依赖检查 | 文件、引用与依赖是否闭合 | 真实行为与质量 |
| 完整树治理回放 | 该树在规定用例/裁判下的结果 | 所有任务质量、来源资格和业务验收 |
| 指定宿主实际调用 | 该宿主以明确输入执行过该任务 | 自动安装、发现或其他宿主兼容 |
| 组合工作包回放 | 当前输入/输出链在该范围内的实际表现 | 原始材料真实性、真人批准或生产认证 |
| 人工核对与真实使用 | 对实际目标与条件的判断 | 未观察到的环境或范围 |

两项既有 Skill 的历史公开回放与调用边界保留在[历史说明](skills-v02.md)。四项新增树的当前完整治理与本轮显式调用已通过。使用评测采用独立代理，真人反馈未采集。请以绑定当前准确树的验证摘要为准。

## 结果怎样回到工作包

逐条核对引用，保留草案、采用决定和未决项。确认改动后回到任务源，生成新目录并重新检查；Skill 输出不会自动修改原型、PRD、真实验收或产品资产。是否采纳和由谁批准，仍需明确证据。
