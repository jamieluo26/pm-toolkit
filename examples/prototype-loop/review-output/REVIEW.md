# 评审增量证据

状态：DECLARED_DECISIONS_COVERED

只核对给定决定与字面差异。声明标签不证明真实人员/公司审批，也不证明需求合理、意图完整或实际验收。
冲突、缺失和待定保留为 HOLD。检查通过后仍需用 after.json 生成新目录并逐项检查原型。

前版本：1.0；后版本：1.1

## 精确输入绑定

- before.json：c9d7ce75759e8e7df20d7e7734b2e84b8ee4fb05656cfa4f9027af1c10b54b44
- after.json：40385fea82f37e8dcb98567ce708a3b88264eb324967eaf254ddfa83a6130967
- feedback.json：85adb2e364eaaddcaa894d1bcb4014666d47eafd0ea0634429c5e2328abe0e82
- decisions.json：5c95fde02481e2f162a2c969f74c82e1c54ea64e1314ae7df9fef0a178f011b9

## 字面变更路径

- /layout ← f_toolbar
- /requirements ← f_toolbar

## 给定反馈与决定

- f_toolbar：将筛选从侧栏移到顶部工具栏，保留进度/主题筛选、空态与重置。
  状态：adopted；理由：合成决定：本次只调整承载位置，保留原功能意图并增加相应检查声明。
- f_cloud：希望跨设备自动同步阅读清单。
  状态：declined；理由：合成决定：首版只支持页面会话，云端同步需要独立的数据与权限设计，不纳入本增量。

## 待处理

给定范围内无未覆盖路径或待定项；不代表真实评审完成。
