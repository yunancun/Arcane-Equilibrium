# PA Report — Alpha-Edge Research Execution Plan（dispatch packet 設計）

| 項目 | 內容 |
|------|------|
| Date | 2026-05-31 |
| Author | PA |
| Status | DONE — awaiting PM 2nd sign-off |
| Deliverable | `docs/execution_plan/2026-05-31--alpha_edge_research_execution_plan.md`（正式工程安排：4 track × wave/sprint/session + work-chain + acceptance + 並行圖 + gate 表 + 既有資產整合 + NOW-dispatch session）|
| Upstream | `docs/audits/2026-05-31--p0_edge_cost_wall_investigation.md`（PM findings）+ QC 4-track 提議（PM 1-簽）+ 3 E1-ready spec |

## 交付摘要
把 QC 已 PM-1-簽的 4-track 解決方案研究提議寫成正式 dispatch packet。對齊專案 Sprint/Wave 用法並補 **Track** 頂層層級（研究 program 特有，4 條獨立機率/kill 線的主線）。逐 track 拆 wave/session，每 session 標 owner chain / 輸入 / 輸出 / 可證偽 acceptance / 估時 / blocked-on。並行圖驗 ≤7 ceiling（最大 4，NOW 3）。

## 最 load-bearing 判斷
1. **survivorship 硬修（覆蓋 backfill spec）**：grep 自證 delisted SoT 已存在 DB（`market.symbol_universe_snapshots` V058:31-50 含 delisted 欄位 + cron 已採 `Delivering/Closed`）。backfill spec §2「Symbol source = live scanner universe」= 致命倖存者偏差，計劃覆蓋為 active∪delisted∪Bybit-historical（AC-S1-W1-S1.3 硬修，純 survivor = FAIL）。
2. **Gate-A kill-gate 先於 collector IMPL**：Track 2 maker-fill<30% → KILL，省高風險 Rust 模組 + 5-6mo 累積（PM 1-簽 #2 / A2 教訓）。
3. **leak-free shift(1) 每回測 session day-1 acceptance**（PM 1-簽 #3，成本牆壓 edge 到 1-3bps）。

## PM 2-簽 5 條檢查（詳見計劃 §0）
survivorship 含 delisted / Gate-A 排序先於 IMPL / leak-free day-1 / 並行≤7（NOW 3）/ retention operator-gate 硬卡回填前。

## 既有資產整合
M7 V116（held，解凍=首 candidate stage0_ready）/ collector spec（Gate-B 前置，Gate-A PASS 解凍）/ backfill spec（Track 1 前置，須補 delisted）/ V### reconcile（本計劃 0 新 migration）。

## 紀律
全 read-only 設計；fact/inference/assumption 分離；硬邊界 0 觸碰；不寫 feature code / 不執行回填 / 不改 TODO。NO-OP 確認通過（無同名檔/branch/ticket）。

**PA DESIGN DONE: report path: docs/execution_plan/2026-05-31--alpha_edge_research_execution_plan.md**
