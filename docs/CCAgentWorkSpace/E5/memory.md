# E5 Memory — 工作記憶

## 項目上下文（2026-04-01）

- 當前 Phase：Phase 3 Batch 3A 完成
- 測試基準：3289 passed
- 系統模式：demo_only
- 代碼規模：~67,544 行（62 Python app + 25 local_model_tools + 20 前端）

## 工作記憶

### 2026-04-01 全程序優化審計

**報告位置：**
- `docs/CCAgentWorkSpace/E5/workspace/reports/2026-04-01--optimization_audit.md`
- `docs/audit/April01/E5_optimization_report_2026-04-01.md`

**關鍵發現：**
- March 31 報告 49 項，修復 14 項（含全部 3 個 Critical），殘留 35 項
- 新發現 19 項，當前總計 54 項（1C / 12H / 26M / 15L）
- 最大新風險：backtest_engine O(n^2) 切片 + 兩個無界 dict（truth_source_registry / experiment_ledger）
- main_legacy.py 持續惡化（4,973→5,113 行）
- _process_pending_intents 顯著惡化（~300→462 行）
- 前端認證/CSS 統一債務完全未動

**持續追蹤趨勢（跨 session 比較用）：**
| 指標 | March 31 | April 1 |
|------|----------|---------|
| main_legacy.py 行數 | 4,973 | 5,113 |
| pipeline_bridge.py 行數 | ~1,500 | 1,937 |
| f-string logger 調用 | 192 | 182 |
| int(time.time()*1000) 內聯 | 128 | 156 |
| 前端 TOKEN_KEY 重複 | 4 | 4 |
| sys.path dirname 重複 | 1 | 4 |
| tab-governance inline styles | ~150 | 200 |

## 報告索引

| 日期 | 任務 | 文件位置 |
|------|------|---------|
| 2026-04-01 | 全程序優化審計 v2 | `docs/CCAgentWorkSpace/E5/workspace/reports/2026-04-01--optimization_audit.md` |
