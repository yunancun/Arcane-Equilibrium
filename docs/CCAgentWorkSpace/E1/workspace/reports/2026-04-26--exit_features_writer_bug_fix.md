# E1 — EXIT-FEATURES-WRITER-BUG-1-FIX cohesive 1+2 RCA repair

**Date**: 2026-04-26
**Task**: EXIT-FEATURES-WRITER-BUG-1-FIX (P1, MIT audit driven)
**Commits**: `af48ee1` (main, 10 files / +755 / −19) + `83456e5` (regression-guard follow-up, 1 file / +18 / −13)
**Status**: implementation DONE, awaiting E2 → E4 → QA → PM
**Linux release lib baseline**: 2198 → **2210 / 0 failed** (+12 lib tests)
**Integration**: micro_profit_fix_integration **12 / 0 failed** (+5 new EXIT-FEATURES tests)

## 任務範圍嚴守

- ✅ 修 RCA-A（dust spiral）+ RCA-B（partial reduce 寫 EF）符合 MIT §5 推薦
- ✅ 不擴範圍：不動 healthcheck SQL（路徑 3）/ ML training cleanup（隔壁 P2）/ MICRO-PROFIT-FIX-1-HEALTHCHECK / docs/CCAgentWorkSpace/QA
- ✅ 不 merge / rebase / reset / pull
- ✅ commit-即-push（CLAUDE.md §七 強制）

## 修法（cohesive 1+2 PR）

### 路徑 1 RCA-A（dust spiral）
1. **A1** layered Gate 1+2 `step_0_fast_track.rs`：取代原 line 317 bare `entry_notional <= 0.0` fail-open。Gate 1 = absolute USD floor（active in ALL branches）；Gate 2 = ratio gate（only when `entry_notional > 0`）
2. **A3** defence-in-depth backfill `event_consumer/bootstrap.rs`：import_positions 後追加 `migrate_legacy_entry_notional()` (idempotent；對 Bybit REST avg_price=0 殘留兜底)
3. **schema** 新 `RiskConfig.limits.ft_dust_qty_floor_usd: f64`（default 1.0 USD，range [0, 100_000]，NaN/Inf reject）+ live TOML 顯式 + demo/paper serde default 繼承

### 路徑 2 RCA-B（partial reduce 寫 EF）
- **B1** `is_partial_reduce_tag()` helper in `on_tick/helpers.rs`：當前唯一 partial reduce 路徑 = `risk_close:fast_track_reduce_half`
- `emit_close_fill` 在 `try_emit_exit_feature_row` 呼叫前過 `is_partial_reduce_tag` 檢查 → partial reduce skip EF emit；trading.fills 仍寫（操作員可見度 + PnL 帳務不受影響）

## 17 new tests（lib 12 + integration 5）

詳列在 `.claude_reports/20260426_155130_exit_features_writer_bug_fix.md` §附錄。

## 不確定 / followup

1. healthcheck [3] 仍 FAIL ~24h（歷史 37 noise rows age out 期）；2026-04-27 07:37 CEST 後預期 PASS（前提：本 commit deploy 後無新 dust spiral）
2. `migrate_legacy_entry_notional` 在 bootstrap 中觸發頻率預期常為 0（純 defence-in-depth）
3. dust floor 1.0 USD 預期不誤殺真實小幣（Bybit min order notional 普遍 ≥ 5 USD）
4. ML-TRAINING-DATA-HYGIENE-1 P2 ticket 處理歷史 noise cleanup（隔壁，本 fix 不擴）

## 給 E2 review 的重點

1. `is_partial_reduce_tag` taxonomy 完整性（其他 partial reduce 路徑無遺漏）
2. layered Gate 1+2 與既有 MICRO-PROFIT-FIX-1 ratio gate 行為差異（特別 `entry_notional > 0 && current_notional < dust_floor` 邊界）
3. migrate_legacy_entry_notional 在 bootstrap 順序（在 import_positions 後、orphan triage 前）
4. RUST-DOUBLE-PREFIX-1 regression guard 兼容（follow-up 已將 `phys_lock_gate4_giveback` 字面量換為 `halt_session_drawdown`）

## 跨平台 / 治理對照

- 雙語注釋全達標（每 fn / config field / test mod 中英對照）
- 無新硬編碼路徑 / 無新 singleton
- §九 行數規範：所有檔案均在 1200 硬上限內
- CLAUDE.md §七 commit-即-push 嚴守 + Linux git pull --ff-only synced
