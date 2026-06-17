# E1-A — Phase 2 EDGE-ANCHORED promote criteria gate（Rust 純函數 + 唯讀 IPC）

日期：2026-06-17 · 角色：E1-A（Backend，Rust）· 狀態：IMPLEMENTATION DONE，待 E2 審查
方案來源：`srv/docs/execution_plan/2026-06-17--intelligent-param-adjusting-agent-master-spec.md` §2.4 / §2.10 E1-A

## 任務摘要

實作 Phase 2 demo→live 促升管線的 **EDGE-ANCHORED criteria gate**：Rust 純邏輯判定 +
唯讀 IPC。判定不靠 demo PnL（down-beta 假陽性源頭），anchor 在既有 battle-tested 顯著性
防線（live `edge_estimates.validation_passed` OOS 鏈 + `cost_gate_live_with_slippage` 成本牆 +
canary Stage3→4 可移植 soak/boundary metric）。

## 修改清單（嚴守 wave 邊界：只動 4 檔，全 Rust，與 E1-B/E1-C 不重疊）

| 檔 | 改動 |
|---|---|
| `rust/openclaw_engine/src/strategist_scheduler/promotion_criteria.rs` | **新檔**。`PromotionCriteriaInput` + `ActiveCellEdge` struct + `PromotionVerdict{Eligible/Pending/Reject}` enum + 純函數 `evaluate_promotion_criteria`（10-step）+ const allowlist + 21 inline tests。 |
| `rust/openclaw_engine/src/strategist_scheduler/mod.rs` | 加 `mod promotion_criteria;` + re-export 4 個型別/函數。 |
| `rust/openclaw_engine/src/ipc_server/dispatch.rs` | 加唯讀 IPC arm `"evaluate_promotion_criteria"` + handler `handle_evaluate_promotion_criteria` + 程序級 `static PROMOTION_EDGE_SLOT` + `set_promotion_edge_slot`。 |
| `rust/openclaw_engine/src/ipc_server/method_registry.rs` | 加 `EVALUATE_PROMOTION_CRITERIA`（readonly=true, slot=None）+ 2 個不變量測試。 |

## 關鍵實作

### 判定邏輯（§2.4.E，fail-closed 短路）
1 direction bound（denylist param→Reject）→ 2 active 空→Reject(no_active_symbols)→ 3 boundary>0→Reject(demo_breached_live_drawdown_envelope)→ 4 stale→Pending→ 5 fills<30→Pending→ 6 soak<21d→Pending→ 7 since-change<72h→Pending→ **8 edge coverage（binding）** → 9 attribution(None/<0.7→Pending) → 10 Eligible。

per-cell 8 條（全真才 qualified）：`present && validation_passed && validation_reason=="passed" && edge_estimates_fresh && from_runtime_field && shrunk_bps>0 && n_trades>=30 && 清 live cost wall`。
coverage = weighted-by-n_trades；要求 `coverage >= 0.6` AND `qualified_count >= max(2, ceil(active/2))`（雙閘擋單 cell cherry-pick）。

### live cost wall = REUSE，不另造成本模型
`clears_live_cost_wall` 鏡像 `intent_processor::gates::cost_gate_live_with_slippage:329`：
`threshold_bps = fee_bps_round_trip / clamp(win_rate, floor, 1.0) × safety_multiplier`，通過 `shrunk_bps >= threshold_bps`。fee_bps/safety_multiplier/win_rate_floor 由 caller 從 `risk_config_live.toml` slippage SSOT 傳入。

### direction allowlist（§2.4.F，PROVISIONAL — QC 須釘死）
exact: `cooldown_ms/reject_cooldown_ms/churn_breaker_cooldown_ms/funding_threshold/adx_threshold`；prefix `min_*`；suffix `*_threshold_usd`。其餘（weight_*/take_profit_pct/max_hold_ms/*_ratio/sizing）→ Reject。名稱親查 `strategies/*/params.rs` 對齊真實 param_ranges。

### 唯讀 IPC + edge snapshot 取得（實作決策）
- **放 Rust IPC（首選，非 Python-inline）**：純邏輯 Rust-first，與 Phase 3 RiskConfig promote 共用同模塊（headroom）。
- **edge snapshot 取得 = 程序級 `static OnceLock<Arc<parking_lot::RwLock<EdgeEstimates>>>`**，鏡像同檔 `live_authz::nonce_ledger()` 的先例（doc 明示「用 OnceLock 而非穿過 dispatch_request 已龐大的參數鏈」）。理由：per-engine EdgeEstimates 在 `main_scanner_init.rs:68` 構造但**不在 dispatch 簽名內**；穿參數鏈會改 connection.rs/mod.rs/main_*.rs（跨 wave 檔，dirty tree 風險高）。slot 未注入→`criteria_engine_uninitialized` fail-soft（鏡像 cost_edge_advisor/account_manager 語意），route 視為 Pending。
- **token 豁免**：method 不在 `LIVE_WRITE_METHODS`（live_authz.rs:50），`requires_live_authz` 對它回 false，自動豁免。加 `evaluate_promotion_criteria_not_in_live_write_methods` 測試自證此不變量。

### 契約分工（§2.4.G 變體，釘死）
route 傳入：`strategy` + `active_symbols`（Python 端解 `strategy_params_live.allowed_symbols ∩ scanner_config.pinned_symbols`）+ soak/fills/boundary/attribution metric + live cost 參數（fee_bps_round_trip/safety_multiplier/win_rate_floor 讀 risk_config_live.toml）+ `edge_ttl_secs` + `tuned_param_names`。engine 自查：per-symbol `get_cell(strategy, sym)` + snapshot freshness（保證與 live cost_gate 同一份記憶體 snapshot）。缺欄 fail-closed 保守（fee 缺→`f64::INFINITY` 成本牆、boundary 缺→1 越界、edge_ttl 缺→0=非 fresh）。

## 治理對照

- 硬邊界：未碰 max_retries / live_execution_allowed / execution_authority / system_mode（dispatch.rs 4 個 token 全 pre-existing set_system_mode 區，非我新增區）。
- 未改 `LIVE_WRITE_METHODS`、未接 `promote_params_to_live` stub、無自動 caller（純函數 + 唯讀 IPC，0 cmd/0 ConfigStore/0 EdgeEstimates 寫）。
- 註釋中文優先（bilingual-comment-style）；MODULE_NOTE 完整（用途/型別/依賴/4 條硬邊界）。
- 0 hardcoded user path（grep 自證）。新檔 ~560 行（<800 治理線）。
- Rust-first（feedback_new_code_rust_first）。新 singleton `PROMOTION_EDGE_SLOT`=程序級 OnceLock late-inject（鏡像 nonce_ledger，無 DB row；登記落本報告 + 下方 follow-up）。

## 測試（Mac 親跑，全綠）

- `promotion_criteria` 21 tests：0-validated→Pending（非 Eligible，DESIRED）/ all-validated-majority→Eligible / explore-grace reason→非 Eligible / denylist param→Reject / live-cost-wall fail→Pending / boundary→Reject / soak·fills·since-change·freshness·attribution Pending 分支 / **mutation-bite**：single-cherry-pick（巨 n_trades 但 q=1<2→Pending）、cost-wall 邊界 inclusive、win_rate_floor clamp。
- `method_registry` 5 tests（含 2 新：readonly+slot / 不在 LIVE_WRITE_METHODS）。
- 回歸：`strategist_scheduler` 82 + `ipc_server::` 134 全綠 0 回歸；`cargo build --lib` clean 無新 warning（3 個 pre-existing warning 與我無關）。

## 不確定之處 / Operator + 後續角色下一步

1. **QC MANDATORY 釘死 6 項**（§2.4「待 QC 釘死」）：COVERAGE_FLOOR(0.6) / MIN_QUALIFIED_CELLS(2) / per-cell n_trades(30 vs runtime 60) / soak·since-change·fills 值 / **v1 direction allowlist 最終名單** / attribution gate 是否啟用。全標 PROVISIONAL，改 const 不改判定結構。
2. **整合 seam（E1-C / main_boot_tasks）owed**：`set_promotion_edge_slot` 暫 `#[allow(dead_code)]`，須在 boot 取 **live** pipeline 的 `scanner_edge_estimates`（main_scanner_init.rs:68）注入一次後移除 allow。**未注入時 handler 永遠回 Pending/uninitialized**（fail-closed，但無真實判定）—— E4 Linux 須驗注入後在 0-validated-cell 真回 Pending（誠實標 §2.9）。
3. **E1-C 契約**：route 須傳齊上述 IPC params（含 Python 端解 active_symbols + 讀 risk_config_live slippage 算 fee_bps/multiplier/floor + edge_ttl_secs）。回應 payload：`{verdict,tag,reason,strategy,active_count,edge_estimates_fresh,per_cell:[...]}`（route 寫 audit criteria_input_json）。
4. **singleton 登記 follow-up**：`PROMOTION_EDGE_SLOT`（程序級 OnceLock）須在 singleton-registry 落地（PA/E2 report + TODO follow-up）。

E1 IMPLEMENTATION DONE: 待 E2 審查（report path: srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-06-17--phase2-e1a-promotion-criteria-gate.md）
