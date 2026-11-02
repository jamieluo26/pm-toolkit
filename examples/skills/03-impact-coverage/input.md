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
