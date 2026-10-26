# 从方向讨论到一次可核对的评审增量

1. **先写方向。** 在规格写清定位、痛点、价值假设和本轮范围，选择能落入固定集合交互的字段与要求。样例使用全新合成资料。
2. **生成前版。** build到新目录；对照PRD和检查计划体验 prototype.html。没有实现的任意自定义要求不得因为它出现在PRD就视为完成。
3. **记录反馈。** 将原始反馈单独列入feedback，保留引用；调用者在decisions声明采纳、拒绝及理由或待定。Skill可以审阅文字，不替人拍板。
4. **修改唯一规格。** 建立after文件、更新版本、填写parent SHA。后规格应只包含本轮给定已采纳范围；待定或拒绝项不得自动带入。
5. **核对承接。** review检查四份文件绑定与精确路径；HOLD必须保留。通过只表示给定范围的字面承接成立，再用after生成一个新目录。
6. **执行检查。** check证明同源；真实浏览器逐项核空态、重置、反复筛选、详情和会话编辑。记录环境、原始制品SHA、截图和失败；真实用户/业务验收另记。

## 合成阅读清单：筛选从侧栏移到工具栏

前后原型分别在[前版](../examples/prototype-loop/before-output/prototype.html)与[后版](../examples/prototype-loop/after-output/prototype.html)。f_toolbar合成决定采纳：移动位置并保留进度、主题、空态与重置；f_cloud合成决定拒绝：本次不建设跨设备同步。程序没有把云端能力自动加入规格。

`/layout`和`/requirements`由f_toolbar精确承接，版本与父SHA另行绑定。可对照[评审证据](../examples/prototype-loop/review-output/REVIEW.md)、[后版PRD](../examples/prototype-loop/after-output/PRD.md)和[后版检查计划](../examples/prototype-loop/after-output/acceptance.md)。数组整体承接无法证明每一语句意图，应继续逐条人工审阅。

另一份[个人任务板](../examples/personal-tasks/output/prototype.html)使用任务、状态、优先级与小时字段，演示同一生成器处理不同集合。它不具备复杂看板拖拽、排期或多人协作。

## Skill如何接入

复用既有两项Skill。将before/after两份PRD、feedback、decisions和review.json显式提供给[反馈意图审阅](../skills/feedback-intent-preservation-review/SKILL.md)；把后版requirements与acceptance/trace给[需求验收追踪](../skills/requirement-acceptance-trace-review/SKILL.md)。

它们只形成文字草案，不改规格、不执行页面、不把人工声明升级成真实审批。宿主若未加载Skill，要显式提供相关文件；本工具CLI没有隐式模型调用。
