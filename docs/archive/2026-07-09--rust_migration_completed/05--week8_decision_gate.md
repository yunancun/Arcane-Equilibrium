# Phase R-05：Week 8 硬決策點
# Week 8 Go/No-Go Decision Gate

**時間**：Week 8 最後一天
**決策者**：Operator
**輸入**：`04--engine_full_path.md` 的 Go/No-Go 結果

---

## 決策矩陣

| 條件 | Go 標準 | 實際結果 | PASS/FAIL |
|------|---------|---------|-----------|
| Engine 獨立運行 24h | 零崩潰 | 571s (10min) 零崩潰，38,389 ticks | **⚠️ 部分達標**（時長不足，見下方風險備註） |
| Paper 交易正確記錄 | ≥ 5 筆 | 8 筆（4 BTC + 2 ETH + 1 SOL + 1 DOGE）+ JSONL 審計 | **PASS** |
| tick P50 | < 100μs | 26.9μs (release) | **PASS** |
| 快速通道 | 觸發正確 | 5 unit test + pipeline wired | **PASS** |
| core 單元測試 | 全部通過 | 548 passed / 0 failed / 0 warnings | **PASS** |
| 集成測試 | ≥ 20 場景 PASS | 56 場景（29 stress + 27 golden） | **PASS** |

---

## Go → 繼續完整遷移

全部 PASS → 進入 `06--python_ipc_integration.md`（W9-10 Python 改造）

預期交付：W14 結束時完整雙進程架構上線。

---

## No-Go → 降級 PyO3 漸進式

任一 FAIL → 降級為 PyO3 部分遷移。

### 復用率分析 [V3-PM-3]

| 已完成代碼 | 可復用？ | 行數 |
|-----------|---------|------|
| openclaw_types | **100%** — 作為 PyO3 types | 4,500 |
| openclaw_core（indicators/signals/klines） | **100%** — PyO3 包裝 | ~6,000 |
| openclaw_core（SM/execution/governance） | **~30%** — 需要 PyO3 適配 | ~2,700 中 ~800 可用 |
| openclaw_engine（pipeline/strategies） | **0%** — 廢棄 | 0 |
| 測試代碼 | **~60%** — 單元測試可保留 | ~3,300 |

**復用率：~50%（~14,600 / 32,500 行）**
**沉沒成本：~4-5 人週**

### 降級路徑具體步驟

1. 新建 `openclaw_pyo3` crate（~2,500 行）
2. 用 PyO3 包裝 indicators + signals + klines + h0_gate
3. Python 側 `import openclaw_pyo3` 替代原 Python 模組
4. 保留 Python 的 pipeline_bridge / governance_hub / paper_trading_engine
5. 預計額外 3-4 週完成 PyO3 整合

---

## 未驗證風險

> 詳見 **`docs/KNOWN_ISSUES.md`**（3 項：記憶體洩漏 / WS 斷線重連 / UTC 日切）
> R-06 期間後台並行 24h soak test 驗證，若發現問題回溯修復後再進 R-07。

---

## 決策記錄

**日期**：2026-04-03
**決策**：**Conditional Go**
**理由**：5/6 條件完全 PASS（多數大幅超標），條件 1 運行時長不足（10min vs 24h）但壓力測試覆蓋度充分（56 場景、38,389 ticks、零崩潰）。9 項 Bybit API 兼容性修復已驗證。QC 審計 45+ 公式全部 CORRECT。
**附帶條件**：R-06 期間後台並行執行 24h soak test，驗證上述 3 項風險。若發現問題，回溯修復後再進 R-07 灰度。
**Operator 簽核**：✅ Conditional Go（2026-04-03）

---

## 問題與變更

- 2026-04-03：原定 24h 運行改為 10 分鐘實測 + 56 場景壓力測試替代，Operator 批准 Conditional Go
