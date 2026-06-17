# E1 IMPL — Phase 1 strategist rich-input: 兩 additive 修（observability + 註釋訂正）

- 日期：2026-06-17
- 角色：E1（後端開發）
- 狀態：IMPL DONE，待 E2 審查（未 commit）
- 來源：Phase 1 rich-input tuner adversarial review follow-up（1 confirmed MEDIUM 可觀測性 + 1 LOW 註釋）
- Repo root：`/Users/ncyu/Projects/TradeBot/srv`

## 任務摘要

對已建好且 review-clean 的 Phase 1（rich-input tuner）做兩處 surgical additive 修，
**不改 gate 邏輯、不擴 scope**：

- FIX-1（MEDIUM，可觀測性）：每輪 emit 一行 edge 可達面 log，讓 operator 看得到
  quant gate 是否真的有 validated+fresh cell 可調參（區分 runtime 資料狀態 vs 代碼 bug）。
- FIX-2（LOW，純註釋）：訂正 regime self-compute 把 leak-free 歸因於 SQL 謂詞的錯誤註釋。

## 修改清單

| 檔 | 改動 | 類型 |
|---|---|---|
| `rust/openclaw_engine/src/edge_estimates.rs` | 新 `reachable_surface_counts(now,ttl)` 唯讀 helper + 3 單元測試 | FIX-1 |
| `rust/openclaw_engine/src/strategist_scheduler/evaluate.rs` | `evaluate_cycle` 開頭 flag-gate emit；新 `log_edge_reachable_surface` + `resolve_edge_reachable_surface`；FIX-2 訂正 2 處 regime 註釋 | FIX-1+FIX-2 |
| `rust/openclaw_engine/src/strategist_scheduler/tests.rs` | 4 新 observability 測試 + `obs_edge_store` fixture | FIX-1 |
| `docs/CCAgentWorkSpace/E1/memory.md` | 完成序列條目 | meta |

## 關鍵 diff（load-bearing 摘要）

### FIX-1a：唯讀計數 helper（edge_estimates.rs）
```rust
pub fn reachable_surface_counts(&self, now: i64, ttl: i64) -> (usize, usize, usize, usize) {
    let n_cells = self.data.len();
    let n_validated = self.data.values().filter(|c| c.validation_passed).count();
    let snapshot_fresh = self.is_fresh(now, ttl);          // is_fresh 是快照層級
    let n_fresh = if snapshot_fresh { n_cells } else { 0 };
    let n_usable = if snapshot_fresh { n_validated } else { 0 };  // validated AND fresh
    (n_cells, n_validated, n_fresh, n_usable)
}
```
**設計決策**：`is_fresh` 是 snapshot 層級單一 `_meta.updated_at`（非 per-cell），故 n_fresh
要嘛=n_cells 要嘛=0。這如實反映 gate 的真實 freshness 語意（quant gate 用同一 snapshot-level
`edge.is_fresh`），不偽造 per-cell freshness。

### FIX-1b：emit site（evaluate.rs，evaluate_cycle 開頭）
```rust
if self.rich_input_enabled {
    self.log_edge_reachable_surface();
}
```
emit 在 `metrics.is_empty()` early-return **之前** → flag-ON 時保證每輪恰一行。

### log 格式
```
STRATEGIST-RICH-INPUT edge surface: cells={} validated={} fresh={} usable={} / 策略師 rich-input edge 可達面
```
結構化欄位：`cells / validated / fresh / usable / edge_store_wired`（tracing structured fields）+
human message（中英）。level=info。

### FIX-2：regime leak-free 註釋訂正（evaluate.rs）
原註釋誤稱 leak-free 來自 `ts < now()` SQL 謂詞；訂正為：
- 真保護=`market.klines` **只**由 `MarketDataMsg::KlineClose` 寫入（market_writer.rs::flush_klines
  實證：kline_buf 只 push KlineClose，flush 只 bind KlineClose）→ 表內永遠只有 finalized
  closed bar，無 forming bar。
- `ts < now()` 只排除「open_time 在未來」的退化資料，**非** leak-free 來源。

## 測試結果

- `cargo test -p openclaw_engine --lib strategist`：**69 passed / 0 failed**（含 4 新 obs 測試）
  - `t_p1_obs_flag_on_fresh_store_reports_correct_surface`：cells=3/validated=2/fresh=3/usable=2 ✓
  - `t_p1_obs_flag_on_stale_store_zeroes_fresh_and_usable`：fresh=0/usable=0（validated 仍=2）✓
  - `t_p1_obs_flag_on_no_store_all_zero`：edge_store 未接 → (0,0,0,0) ✓
  - `t_p1_obs_flag_off_emit_is_gated`：flag-OFF rich_input_enabled=false + 源碼 grep 鎖死 emit 在 gate 內 ✓
- `cargo test -p openclaw_engine --lib edge_estimates`：**38 passed / 0 failed**（含 3 新 reachable_surface 測試）
- **mutation bite 雙證**：
  1. `n_usable` 去掉 freshness gate（=n_validated）→ stale 測（unit + scheduler）雙紅 → 還原綠。
  2. emit 移出 `if self.rich_input_enabled` gate → flag-off-gate 測紅 → 還原綠。
- 0 新編譯 warning（engine 既有 3 warning 在 btc_lead_lag/single_watcher/ma_crossover，非我檔）。

### flag-OFF byte-identical 確認
- flag-OFF（`rich_input_enabled=false`）→ `evaluate_cycle` 的 `if self.rich_input_enabled` gate
  短路 → `log_edge_reachable_surface` 不可達 → **不 emit、不讀 edge_store**。
- `build_strategist_eval_payload` 路徑與 validate 路徑完全未動（既有 T-P1-1 flag-OFF byte-identical
  測試仍綠）。emit 是 cycle 開頭的旁路 log，與 payload/gate 解耦。

## 治理對照

- 硬邊界：未碰 max_retries / live_execution_allowed / execution_authority / system_mode。
- **零 gate 邏輯改**：`verify_quant_justification` / `validate_recommendation*` 簽名與行為 byte-unchanged；
  log 純旁路觀測，與放行判定解耦（gate 仍逐 cell 自查真值，不信 payload/log）。
- 註釋規範：新註釋中文為主，技術識別子（KlineClose / market.klines / ts / now()）保留英文。
- 唯讀 helper：`reachable_surface_counts` / `resolve_edge_reachable_surface` 皆 `&self` 零突變。
- 無新 migration、無新 singleton、無跨平台硬編碼路徑、無新檔（皆改既有檔，最大 evaluate.rs 仍 <800 行門檻內）。
- 「使用既有 EdgeEstimates API」：count 取自既有 `validation_passed` 欄 + 既有 `is_fresh`；
  新 helper 只彙總既有欄位（READ-ONLY，未改任何 gate）。

## 不確定之處 / 偏差

- `n_fresh` 語意：因 `is_fresh` 是 snapshot 層級（單一 updated_at），n_fresh 必然為 n_cells 或 0，
  不存在「部分 cell fresh」。這如實對齊 quant gate 的真實行為（同用 snapshot-level freshness），
  非 bug；已在 helper doc-comment 明述。若 review 期望 per-cell freshness，需先改 EdgeEstimates
  的 freshness 模型（超出本任務 scope，且會改 gate 語意 → 不做）。
- 無 Linux/PG 需求：純記憶體邏輯 + log，Mac 可完整驗證。

## Operator 下一步

1. E2 對抗審查（重點：確認 emit 與 gate 解耦、flag-OFF byte-identical、reachable_surface 計數正確）。
2. E4 Linux 回歸（`cargo test --release` 全套；emit 在真引擎跑 demo cycle 時 log 行可見性 smoke）。
3. 通過後 PM 統一 commit（強制鏈 E1→E2→E4→PM，未 commit）。
