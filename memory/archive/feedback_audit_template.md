---
name: 全面審查喚醒模版
description: 大里程碑完成後的 L3 全面審查流程：5 路並行 9 角色（PA+PM / FA+QC / CC+E3 / E2+E5 / E4）
type: feedback
---

大塊程序完成後，按觸發級別喚醒審計 Agent：

- **L1 輕量**（單 Phase）：E2 + E4 + E5
- **L2 標準**（策略/模型改動）：E2 + E4 + E5 + QA Audit
- **L3 全面**（跨多 Phase 大里程碑）：PA + PM + FA + QC + CC + E2 + E3 + E4 + E5

**Why:** Python V2 的 6 項 FAKE/DEAD 功能就是缺乏全面審計的後果。多角色審計能從不同視角發現盲點。

**How to apply:** L3 審查分 5 路並行派發：
1. PA+PM（架構+項目管理）
2. FA+QC（功能+量化正確性）
3. CC+E3（合規+安全）
4. E2+E5（代碼+優化）
5. E4（全量回歸測試）

**條件性附加角色：**
- DL/Learning/ML 改動 → 額外加 **MIT（ML/DL 專家）**：模型架構/訓練管線/數據洩漏/過擬合/部署安全/回聲室防護
- 數據庫改動 → 額外加 **E5-DB（DB 性能）**：EXPLAIN ANALYZE/索引有效性/壓縮比/連接池/寫放大/vacuum

詳細清單見：`docs/references/2026-04-04--comprehensive_audit_template_v1.md`
