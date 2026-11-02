# 改共享组件，有没有漏掉使用它的页面？

只改了一个页面，方案摘要却写“共享控件影响范围完整”。

本案例输入为新编合成材料；`result.md`是一次明确供料调用的未编辑最终正文；本页的摘要与解读由Codex整理，待维护者核定。它们不是同一层证据，也不代表真实业务已经决定或修改。

## 直接试用

1. 打开[完整调用文本](prompt.md)，复制全部内容到自己的、支持该长度文本的AI助手。
2. 首次可以原样试；用于自己任务时，替换其中材料，保留范围、来源位置和未知项。
3. 对照[本次实际输出](result.md)阅读结果，再自行核对依据与处理取舍。不同宿主可能给出不同表述。

完整调用文本已含准确的[Skill入口](../../../skills/declared-impact-coverage-review/SKILL.md)和下列全部输入，不必先启动服务、填写规格或运行脚本。完整Skill目录仍保留可选模板与验证材料；提示词供料不等于原生安装。

## 给什么，得到什么

- **最低材料：**对象与变体身份、给定消费者母表、覆盖方法、纳入与排除依据。
- **结果形式：**逐关系处理、漏项、孤立排除和未知范围。
- **使用的Skill：**`declared-impact-coverage-review`。

## 合成输入

```text
# 合成输入：共享筛选条影响范围

全新合成；只核对给定关系，不等于发现了真实应用全部页面。
本次对象：OBJ:FILTER-BAR:desktop；移动变体OBJ:FILTER-BAR:mobile是独立身份。
消费者身份使用完整入口引用，名称相似不能合并。覆盖方法：给定桌面对象的每条消费者关系，必须明确纳入，或有适用于该关系的排除依据。

给定母表：
- REL-01：OBJ:FILTER-BAR:desktop → ENTRY:reading-list。
- REL-02：OBJ:FILTER-BAR:desktop → ENTRY:favorites-list。
- REL-03：OBJ:FILTER-BAR:mobile → ENTRY:reading-list-mobile；本次对象范围外。

拟改方案：
- INC-01：纳入REL-01 / ENTRY:reading-list。
- EX-01：排除OBJ:FILTER-BAR:mobile / ENTRY:reading-list-mobile，理由是本次仅桌面；给定范围记录SCOPE-01适用于此移动关系。
- EX-02：排除OBJ:ACCOUNT-PANEL:desktop / ENTRY:account-settings，理由是账号页本次不改；母表未声明该对象的消费者关系。
- SUMMARY-01：方案摘要写“桌面筛选条影响范围完整”。
- SCOPE-01：本合成场景只比较母表中的桌面对象消费者；对真实系统是否还存在未列消费者没有证据。

请逐关系核对：明确缺的处理、孤立排除及摘要是否有依据；不要把EX-02用于抵消REL-02，也不要运行源码发现或认证真实审批。
```

## 看实际输出

[阅读未编辑的AI最终草案 →](result.md) · [输入原文件](input.md) · [准确调用文本](prompt.md) · [输入/Skill/输出摘要绑定](run.json)

输出引用的`input.md:L数字`指本目录输入的实际行号。可见文本不证明原型已经运行，关系审阅也不代替批准或验收。

## 怎样理解结果（编辑解读）

- REL-01被纳入；REL-02的ENTRY:favorites-list尚未说明处理。
- 移动变体REL-03按给定范围单独处理，不能合并成桌面身份。
- EX-02不对应给定母表关系，不能抵消REL-02，也不能支持全系统完整的结论。

## PM接下来决定什么

为REL-02补纳入方案或适用排除依据；另行核对真实消费者是否完整。

## 验证边界

本次验证的是完整Skill与准确输入的显式文字供料，具体宿主与版本见`run.json`。没有自动安装、全宿主兼容或真人收益结论。原始调用日志留在维护控制区；分发的是原始final正文及不含账号、线程或本地路径的来源摘要。

[返回六个案例](../README.md) · [直接使用说明](../../../docs/skill-quickstart.md) · [返回首页](../../../README.md)
