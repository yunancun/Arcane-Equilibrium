# P2-PORTFOLIO-RESTING-REPLAY-PARALLEL — Design Note Only

- **Status**: design only, no IMPL
- **Date**: 2026-05-18
- **Owner**: PM + PA (跟 P1-PORTFOLIO-RESTING-EXPOSURE-1 follow-up)
- **Source TODO row**: `srv/TODO.md` §11.3
- **Parent IMPL commit**: `9980448a` (P1-PORTFOLIO-RESTING-EXPOSURE-1)

## 1. 為何不在本期動 replay surface

`replay/risk_adapter.rs` 中的 `ReplayPaperSnapshot` 是**刻意並行 surface**
（檔頭 SAFETY 不變量：「絕不可匯入 `crate::paper_state::PaperState`」）。
本不變量是 R5-T2 在替 replay 與 runtime 解耦時建立，避免 replay 引入未來
資訊或 mutable runtime 狀態。

P1-PORTFOLIO-RESTING-EXPOSURE-1（`9980448a`）只動 runtime path：
`IntentProcessor::compute_effective_long_short_notional` 共享 SoT 給
`compute_exposure_pct` / `compute_correlated_exposure_pct` / `compute_leverage`。

`ReplayPaperSnapshot.exposure_pct` / `correlated_exposure_pct` / `leverage`
鏡射欄位由 `replay/runner.rs` 在 replay tick 推進時**直接計算寫入**，
不走 runtime helper。本期刻意不感染 replay，避免：

1. 違反 R5-T2 並行不變量（runtime helper 漏導入 PaperState）
2. Replay 與 runtime 對 resting maker pending 的處理時序差異（replay 沒有
   maker reject / timeout 真實事件）導致 exposure_pct mismatch 偽 finding
3. Replay 既有 backtest baseline 數值漂移（影響 walk-forward CV / DSR 樣本）

## 2. 後續啟動條件（任一觸發 → 開 P1 設計）

| 觸發 | 來源 | 動作 |
|---|---|---|
| Replay 要支援 maker-first close 模擬 | EDGE-P2-3 Phase 2c+ 規劃 | 新 P1：replay-side close-maker simulator + exposure 並行計算 |
| Replay backtest 對 resting maker pending 出現 ≥5bps 偏差告警 | E4 walk-forward 監控 | 新 P1：runtime/replay 並行 SoT 一致性 audit |
| `compute_effective_long_short_notional` 被新需求改動（router 之外）| code review | 同步檢視 replay 對應欄位是否需擴充 |

## 3. 短期 hygiene（本期不做，但記入 backlog）

- 在 `risk_adapter.rs:115` SAFETY 註解下新增一行：
  「**並行欄位 invariant**：`exposure_pct` / `correlated_exposure_pct` /
   `leverage` 不得回呼 runtime helper；若需要 effective-notional 語義，
   由 `replay/runner.rs` 在寫入 snapshot 時自行計算等價值。」
- 移入 `P2-PORTFOLIO-RESTING-REPLAY-DOC-NOTE` 子卡（≤10 LOC，下次 hygiene
  sweep 帶上）

## 4. 不做的事

- 不新增 replay-side resting maker simulator
- 不修改 `ReplayPaperSnapshot` 任何欄位
- 不在 runtime helper 嘗試 dual-call replay path
- 不引入 `cfg(test)` 共享 helper（會破壞 SAFETY 不變量）

## 5. Audit chain

- Spec source row: `srv/TODO.md` line 356（P2-PORTFOLIO-RESTING-REPLAY-PARALLEL）
- E4 §7 + E1 self-report §6 P2 #2（IMPL commit `9980448a` round 2 review）
- SAFETY origin: `risk_adapter.rs:108-114`（R5-T2 並行 surface 不變量）

## 6. PM Sign-off

本檔為 design-only 結案；TODO §11.3 對應行可標 ✅ DONE 2026-05-18（design note land，無代碼動）；後續 backlog 子卡 `P2-PORTFOLIO-RESTING-REPLAY-DOC-NOTE` 由下次 hygiene sweep 處理。
