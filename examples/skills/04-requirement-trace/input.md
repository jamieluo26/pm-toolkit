# 合成输入：阅读清单需求与检查

全新合成；本次唯一审阅范围为阅读清单v2的以下需求、对象与检查。
身份采用完整ID。关系含义：需求→对象表示由对象承载需求；对象→检查表示该检查核对该对象的对应需求；需求→检查可直接成立。只按显式边追溯，不按显示名称猜关系。

节点：
- REQ-SEARCH：可以按主题筛选阅读条目。
- REQ-EXPORT：可以导出当前筛选结果。
- VIEW:top-filter：主题筛选条。
- CHECK-SEARCH：选择主题后核对结果；这是检查计划，尚未执行。
- CHECK-COLOR：核对页脚颜色；尚未给出需求来源。

给定关系：
- EDGE-01：REQ-SEARCH → VIEW:top-filter。
- EDGE-02：VIEW:top-filter → CHECK-SEARCH。
- EDGE-03：没有提供REQ-EXPORT通向检查的关系；不能假设它已取消。
- TRACE-SUMMARY：需求2条、检查2条，所以已全部覆盖。
- COPY-SUMMARY：另一份摘要写CHECK-COLOR对应REQ-SEARCH，但给定关系表没有这条边。两份材料未提供谁能裁定该冲突。

请给出正向可达路径、反向来源、断链和冲突，指出最小补料。连接不表示检查已执行，也不得补造一条边来使数量匹配。
