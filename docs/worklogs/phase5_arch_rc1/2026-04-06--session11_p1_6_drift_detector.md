# Session 11 — WP-MIT P1-6 drift_detector PG wiring

日期：2026-04-06
Commit：`8d5793b`（pushed `4d2bb3e..8d5793b` to origin/main）

## 目標
收尾 R1 最後一項 deferred — WP-MIT P1-6 drift_detector PG 接線。

## 變更

### `feature_collector.rs`
- 新增 `pub const FEATURE_NAMES: [&str; FEATURE_DIM]`（與 `to_feature_vector` 順序對齊）
- 用途：drift_detector 將 baseline `feature_name` 解析回特徵向量索引

### `database/drift_detector.rs`
- 新增 `BaselineKey` / `BaselineEntry` types
- `feature_index(name)` 名稱→索引解析
- `fetch_active_baselines(pool)` — `SELECT WHERE valid_until IS NULL`，schema-defensive
- `fetch_latest_features(pool)` — `DISTINCT ON (symbol)` 從 `features.online_latest`
- `DriftMonitorState` — per-(symbol, feature) `VecDeque<f64>` 滑動緩衝（capacity = `min_width * 4`）
- `run_drift_detector` 主迴圈取代 TODO：
  1. 拉 baseline（每個 cycle，~tens of rows）
  2. 拉 latest features
  3. 對齊 (symbol, feature_name) → vector idx → 累積觀測
  4. buffer ≥ `adwin_min_width` 時計算 PSI（histogram + compute_psi）
  5. PSI ≥ `psi_alert` → ALERT，≥ `psi_warning` → WARNING，否則 debug log
  6. burn-in 期僅記錄不寫事件
  7. 寫入 `observability.drift_events`（沿用既有 `write_drift_event`）

## 測試
- drift_detector: 15 → **18**（+3）
  - `test_feature_index_known_names`
  - `test_drift_monitor_state_sliding`（容量 3，第 4 觀測淘汰最舊）
  - `test_drift_monitor_state_rejects_nonfinite`（NaN/Inf 不入 buffer）
- engine 全量：428 → **431** · 0 failures

## R1 狀態
WP-MIT P1 全部閉合（P1-3 / P1-4 / P1-5 / P1-6 ✅）。R1 完全收尾。

## 下一步候選（R2）
- I-22 完整拆分 event_consumer mod.rs 912 → <800（需 loop state 結構化）
- Idle writers #1/2/3/5/6（producer 端補寫）
- Phase 3b Pre-fixes（PF-1 IPC update_strategy_params 等）
- WP-E4 P1 tests 6 項
