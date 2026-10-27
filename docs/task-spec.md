# 同一产品任务的输入合同

`pm_task.py` 把任务背景、规则、规格、交接文档和给定检查记录关联起来。输入是 UTF-8 JSON，最大 2 MB，拒绝重复键、非有限数值、未知字段和符号链接路径。标识为小写字母起始的 `[a-z][a-z0-9_]{0,39}`。输出目录必须不存在，父目录须已存在；检查不会改写输入或产物。

先复制 [空白任务](../templates/task.json)，或阅读 [两版合成任务](../examples/lifecycle/before.json)。顶层字段必须完整：

| 字段 | 内容 |
|---|---|
| schema | `pm-task/v1` |
| id / version | 同一任务的稳定 ID 与版本，须与 prototype 对应 |
| parent_task_sha256 | 首版 null，修订版为前任务文件原始字节 SHA-256 |
| source_kind | 调用者声明 `synthetic` 或 `user-supplied`；工具不鉴定来源 |
| title | 本任务标题 |
| brief | audience、problem、positioning、value_hypothesis、goal、success_metric、priority_basis |
| evidence | id、kind、text、source；kind 只能为 supplied_observation / hypothesis / synthetic |
| decisions | id、statement、status、evidence_ids；status 为 declared / proposed / pending / conflict |
| scope | included、excluded 字符串数组；consumers 为 id、included 布尔、reason、evidence_ids |
| rules | id、statement、default、exception、boundary、evidence_ids、requirement_ids |
| requirements | id、statement、priority、priority_reason、evidence_ids、decision_ids、rule_ids、checks |
| prototype | 完整集合规格或表单规格；它是同一任务文件的一部分 |
| pending | 未决文字数组；没有时为空数组 |

`success_metric` 必须含 statement、baseline、target、measurement。没有真实结果时明确写“未采集/待验证”，不从合成案例填收益。

每条 requirement 的 priority 为 must / should / could；每条 check 含 id、condition、expected、evidence_level。检查 ID 固定为 `需求id_c1`、`需求id_c2`，以此类推；evidence_level 为 browser / manual / content / static。证据、决定、消费者、规则、需求、检查的 ID 不能互相重名。所有关系引用必须存在，规则与需求引用双向一致。

任务层保存证据与取舍，prototype 层保存有限的界面规格。二者在同一个 task.json 中受一致性约束：

- id/version 对应；prototype.positioning、pain、value 分别等于 brief.positioning、problem、value_hypothesis。
- 任务与规格的 parent 绑定必须同时为空或同时非空；修订版不能只清空任务前版绑定来省略评审。
- requirements 的 id、statement、顺序对应；prototype.acceptance 每项须为 `condition；预期：expected` 的准确文字。
- 生成的 spec.json 是 prototype 的确定性投影，原型、PRD、Word 与 trace 都带任务和规格的内容标识。
- Word 经固定上游组件生成，是本版完整 PRD 的有序文本投影；源模型为 document-source.json。原型/PRD/Word 单独改动不能回灌 task.json，check 会拒绝漂移。

集合规格见 [原型合同](prototype-spec.md)；表单规格见 [表单合同](form-spec.md)。多个规格的实际页面内容与合理性仍需人核对；关系完整不证明业务正确。任意 HTML、Word 或 PRD 的反向合并不在合同内。

## 修订与反馈

推荐先用 `prepare-review`，无需手填版本哈希：给定 --before、--after 编辑稿、--version 和新 --output；工具绑定两层前版及新版本，并把任务权威层的定位/痛点/价值/需求投影同步到 prototype。准确原稿保留为 edited-input.json，对齐路径写入 preparation.json。任务 ID、原型类型和其他配置不自动迁移；无关的非空前版引用会被拒绝。

首轮生成 pending 的 review-notes.json，合同为 schema=`pm-task-review-notes/v1`、before_task_sha256、after_task_sha256、items。每项为 id、text、source、status、rationale、paths；状态为 adopted / declined / pending / conflict，后四项含义与下方决定合同一致。复制 notes 到自己的材料目录后填写 items，保留生成目录不变；使用相同前后版和版本，附 --notes 生成另一个新目录。工具会生成准确 feedback/decisions 引用；`prepare-review-check` 使用相同参数只读检查整个准备目录。

notes 的顶层绑定冻结该前后配对。修改 after 后不能把旧决定自动重绑；须先不带 --notes 重新生成 pending 草案，再由人重新填写处理记录。默认占位原意/来源/理由不能作为已采纳或已拒绝提交。工具不推断决定，不清除任务 pending，不生成实际观察。完整操作见 [自定义任务修订](lifecycle.md#修订自己的任务无需手填哈希)。

反馈包含 schema=`pm-task-feedback/v1`、before_task_sha256、items；每项为 id、text、source。

决定包含 schema=`pm-task-decisions/v1`、before_task_sha256、after_task_sha256、feedback_sha256、items；每项为 feedback_id、status、rationale、paths。状态为 adopted / declined / pending / conflict；仅 adopted 可有变更路径。数组按整个数组比较；paths 为准确 JSON Pointer，不支持父路径、通配符或猜测语义等价。

每条反馈必须有唯一处理记录；除版本与前版绑定外，每条字面变更路径须恰好被一项 adopted 决定覆盖。after 的任务及规格前版绑定必须匹配。过期绑定、缺失处理、待定、冲突或未承接变更返回 HOLD。`declared` 和 `adopted` 都是输入标签，不是人的身份或审批证明。

## 检查观察与复验

从生成目录复制 observations-template.json，再填写实际观察。顶层为 schema=`pm-task-observations/v1`、task_sha256、prototype_sha256、rows。每行包含：

| 字段 | 说明 |
|---|---|
| id / check_id | 唯一观察 ID，以及存在的检查 ID |
| status | pass / fail / not_run；表示调用者给定的观察状态 |
| level | browser / manual / content / static，须对应该检查所需证据层 |
| observed / evidence_ref | 已执行时必须有实际描述和引用；工具不读取或认证引用目标 |
| supersedes | 本检查首条观察 null，后续必须引用该检查的上一条观察 ID |
| defect | fail 时非空问题描述，其余可为 null |

失败不删记录；追加一条同检查的复验，supersedes 引用上一条。最后一条 pass 且证据层匹配，工具才记录“给定证据已覆盖”；原失败继续保留为复验链。缺项、未执行、失败、层次不符、过期版本和任务未决都保留 HOLD。修订版交付还须提供准确前版、反馈与决定供重新核对，不能只提交可编辑的 review.json。

观察记录最多10000行，整个输入文件仍受2 MB限制；允许完整的最多600条声明检查以及保留失败/复验链。任何显式提供的评审中的HOLD都计入交付状态，首版也不忽略。

## 命令结果

退出 0：生成/一致性检查或给定关系覆盖成立，具体 status 见 stdout；不等于业务验收。退出 2：输入、依赖或输出合同失败。退出 3：合法材料仍有未决/冲突/缺失，生成的 HOLD 目录可用于继续处理。发生写入中断时保留 INCOMPLETE.txt，换新目录重试。
