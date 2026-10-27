# 单表单与四状态规格

`pm-request/v1` 只描述一个本地表单与四个固定演示状态。它不表达后台、人员权限、持久化、真实审批或任意条件流程。调用者内容会进入制品，工具不验证来源、脱敏或生产适用性。

完整例子：[协作请求规格](../examples/request-flow/spec.json)。这个仓库例子是人工合成材料；生成器不把调用者的任意输入都认定为合成。

## 顶层字段

所有下列字段必需，不接受额外字段。标识使用小写字母开头、其后小写字母/数字/下划线，最多40字符。

|字段|合同|
|---|---|
|schema|固定 `pm-request/v1`|
|id|本表单的稳定标识|
|version|非空单行版本文字；不自动推导业务版本|
|parent_sha256|null或前一份规格原始字节的64位小写SHA256|
|title / positioning / pain / value|标题、定位、痛点与价值假设；非空、最多1000字符的单行文字|
|fields|1–16个字段，按给定顺序显示|
|initial_values|必须逐项包含全部字段key，不多、不少|
|initial_state|`draft`、`submitted`、`needs_info`、`done`之一|
|requirements|1–30条 `{id, statement, acceptance:[string]}`；id唯一，1–20条检查声明|

文字不接受控制字符、孤立代理项或Unicode行/段分隔符。标签最多80字符。要求是调用者声明，生成器不会实现超出下述固定交互的新业务规则；trace始终为 `NOT_EXECUTED`。

## 字段与初值

每个字段必须含 `key`、`label`、`type`、`required`、`choices`。key唯一，required必须是布尔值。

|type|choices|初值与填写校验|
|---|---|---|
|text|空数组|最多1000字符的单行字符串；空字符串表示未填|
|number|空数组|null或有限JSON数值，绝对值不超过9007199254740991；布尔值不是数值|
|choice|1–30个唯一非空字符串|给定选项中的字符串；空字符串表示未选|
|tags|1–30个唯一非空字符串|给定选项的无重复子集，最多30项；空数组表示未选|

只有number字段可额外声明 `minimum`、`maximum`，它们可省略或为null；非空边界必须是上述安全范围内的有限数值，且minimum≤maximum。边界外的已填数值在任何状态都不合法。

草稿和待补充允许必填项尚未填写，但已有值仍须满足类型/允许值/范围。已提交与已完成的给定初值必须满足全部必填项；页面提交和重提也执行必填检查。可选字段允许空文本、null数值、空单选、空标签。初始状态是输入声明，不证明之前真实发生过提交或审批。

## 固定状态合同

|前状态|action|后状态|条件|
|---|---|---|---|
|draft 草稿|submit 提交|submitted 已提交|全部字段合法且必填满足|
|submitted 已提交|return 退回补充|needs_info 待补充|给出非空单行理由，当前数据仍合法|
|needs_info 待补充|resubmit 重新提交|submitted 已提交|全部字段合法且必填满足|
|submitted 已提交|complete 完成|done 已完成|当前数据完整合法|

未列出的转换全部拒绝。草稿与待补充可编辑；已提交与已完成只读；done没有后续业务动作。恢复源样例/刷新只是清除本页面会话并载入给定初值，不是一个业务回退转换。会话记录不是不可篡改日志，状态标签不证明真人批准。

## 配置与导出

“配置字段与导出规格”可修改标题、背景、版本、字段类型/名称/选项/数值范围和初值，增删配置字段。标签初值使用JSON数组；选项每行一项，文本初值直接填写。配置有错误时展示原因并阻止导出。

导出固定以draft作为新初始状态，保留requirements声明，并将parent_sha256绑定当前源SHA；版本必须不同。改变字段后，调用者仍须检查原requirements是否适用。导出只产生JSON，不会自动修改上方演示、源文件、PRD或检查计划；必须保存JSON并重新build/check。该入口不声称无代码生成任意业务表单。

## Python复用接口

`form_core.validate_spec(spec)` 返回原规格或抛 `form_core.Invalid`；`read_json(path)` 返回 `(spec, raw_bytes)`；`build_payload(spec, raw_bytes)` 返回与集合生成器同名的六份 `dict[str,bytes]`。requirements合同相同，便于任务层关联同一任务/版本/需求ID。

`transition(spec, state, values, action, reason="")` 是无副作用的有限演示状态函数，返回新state/values/action/reason。它不执行外部操作。现有 `pm_flow.py review` 的集合协议不会自动接受本表单；表单评审应走对应任务层合同，不用改名绕过校验。
