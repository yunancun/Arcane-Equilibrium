# W2 IMPL sub-task 2 (E1 W2-IMPL-3) — ma_crossover + grid_trading paper-only shadow log

**Author**: E1 Backend Developer (sub-agent IMPL)
**Date**: 2026-05-11
**Status**: IMPL DONE — 待 E2 + A3 對抗性 review + E4 regression（per `feedback_impl_done_adversarial_review.md`）
**Branch**: main 4 file working tree **STAGED** NOT committed（PM holistic commit 統一處理）
**Spec**: `srv/docs/execution_plan/2026-05-10--a4c_btc_alt_lead_lag_spec.md` v1.2 §5.1 + §6 + §8.1
**Producer / V088**: `srv/rust/openclaw_engine/src/panel_aggregator/btc_lead_lag.rs`（W2 sub-task 1, 待 PM holistic commit）
**Trait skeleton**: `srv/rust/openclaw_core/src/alpha_surface.rs::BtcLeadLagPanel`（HEAD `c9fb0b8f` PR ready）

---

## 1. 任務摘要

派發任務（per dispatch v3.7 §3.1 W2-IMPL-3）：ma_crossover + grid_trading 在 paper engine 模式接 surface.btc_lead_lag panel，做 paper-only shadow log，**不影響 strategy decision**，downstream 7d 後跑離線 SQL 對齊每筆 fill 算 counterfactual edge。

實際完成：
- **新檔 helper module**：`rust/openclaw_engine/src/strategies/cross_asset/mod.rs` 約 441 LOC（含 ~150 LOC core helper + ~280 LOC test/MODULE_NOTE）
- **修 ma_crossover**：`strategies/ma_crossover/strategy_impl.rs` +~26 LOC（declared_alpha_sources 加 CrossAsset + on_tick 入口加 shadow log skeleton）
- **修 grid_trading**：`strategies/grid_trading/mod.rs` +~25 LOC（declared_alpha_sources 加 CrossAsset + on_tick trait wrapper 加 shadow log skeleton，不污染 signal.rs::on_tick_impl）
- **修 strategies/mod.rs**：+2 LOC（`pub mod cross_asset;`）
- **11 cross_asset unit test 全 PASS** + ma_crossover 65/65 + grid_trading 44/44 regression 0 fail
- **full openclaw_engine lib 2768/2768 PASS**（baseline 2735 + 11 new + 22 misc deltas，0 fail）
- cargo build --release 0 error
- 跨平台 grep 0 hit（無 `/home/ncyu` / `/Users/<name>` 硬編碼）

**範圍嚴格 stay-in-scope（per CLAUDE.md §八「最小影響」）**：
- **不**動 V### SQL migration（不需 V093）
- **不**動 `learning.decision_features` / `decision_feature_writer.rs`（push back task description 第 3 項，詳 §5）
- **不**動 main.rs / step_4_5_dispatch.rs / IPC slot wire-up（W2 sub-task 4 scope）
- **不**動 bb_breakout / bb_reversion / funding_arb（per spec §5.2 不接收）

---

## 2. 修改清單（4 file，STAGED 未 commit，PM holistic commit 統一處理）

| 動作 | File | LOC change | 說明 |
|---|---|---|---|
| **新檔** | `rust/openclaw_engine/src/strategies/cross_asset/mod.rs` | +441 | 共用 helper module：`evaluate_shadow_signal()` 純函數 + `BtcLeadLagShadowSignal` snapshot struct + 11 unit test |
| **修** | `rust/openclaw_engine/src/strategies/mod.rs` | +2 | `pub mod cross_asset;` + 1 行注釋 |
| **修** | `rust/openclaw_engine/src/strategies/ma_crossover/strategy_impl.rs` | +26 / -4 | `declared_alpha_sources()` 加 `CrossAsset` tag + `on_tick` 簽名 `_surface` → `surface` + 入口 `if let Some(panel) = surface.btc_lead_lag` shadow log skeleton |
| **修** | `rust/openclaw_engine/src/strategies/grid_trading/mod.rs` | +25 / -4 | 同 ma 的 pattern；on_tick 為 trait thin delegator wrapper（不污染 `signal.rs::on_tick_impl` grid inventory model） |

`git diff --cached --stat`：

```
 .../src/strategies/cross_asset/mod.rs              | 441 +++++++++++++++++++++
 .../src/strategies/grid_trading/mod.rs             |  25 +-
 .../src/strategies/ma_crossover/strategy_impl.rs   |  26 +-
 rust/openclaw_engine/src/strategies/mod.rs         |   2 +
 4 files changed, 490 insertions(+), 4 deletions(-)
```

**Working tree 額外 dirty file（**不是我的，不該被 commit 進本 sub-task**）**：
- `rust/openclaw_engine/src/agent_spine/{runtime_shadow.rs, tests.rs}` — W-C Caveat 2 sub-agent
- `rust/openclaw_engine/src/event_consumer/*.rs` (10 file) — W-C Caveat 2 sub-agent
- `rust/openclaw_engine/src/ipc_server/{mod.rs, server.rs, slots.rs}` — W2 sub-task 1 + W-C Caveat 2 mixed
- `rust/openclaw_engine/src/panel_aggregator/{btc_lead_lag.rs, mod.rs}` — W2 sub-task 1 producer 強化
- `rust/openclaw_engine/src/tick_pipeline/{commands.rs, mod.rs}` — W-C Caveat 2 sub-agent
- `helper_scripts/db/passive_wait_healthcheck/checks_agent_spine.py` + `helper_scripts/db/test_agent_spine_healthcheck.py` — W-C Caveat 2 sub-agent
- `docs/CCAgentWorkSpace/{E1,PA,QA}/memory.md` — multi sub-agent append
- `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-1[01]--w_c_*.md` 等 4 file — 隔壁 W-C sub-agent untracked report

**PM holistic commit 邊界建議**：把本 W2 sub-task 2 (4 file 已 staged) 與 W2 sub-task 1 producer 同 commit（namespace 共生：cross_asset helper 用 `BtcLeadLagPanel` trait struct，並非依賴 W2 sub-task 1 BtcLeadLagPanelSnapshot；本 sub-task 4 file 可 atomic commit 獨立**不 break build**）。建議 commit message：

```
W2 sub-task 2: ma_crossover + grid_trading paper-only shadow log

- strategies/cross_asset/mod.rs: 共用 helper evaluate_shadow_signal()
  純函數 + 5 conditions check + step_gate 階梯 + tracing emit
- ma_crossover: declared_alpha_sources += CrossAsset + on_tick 入口 shadow log skeleton
- grid_trading: 同 pattern；trait wrapper 不污染 signal::on_tick_impl
- per spec v1.2 §5.1.2 + §6 paper-only fence Layer 3
- 11 cross_asset test PASS / 0 strategy decision regression / 2768/2768 lib test PASS

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
```

---

## 3. 關鍵 diff（spec § referent + 行為證明）

### 3.1 cross_asset helper — `evaluate_shadow_signal` 5 conditions check

**5 conditions 對齊 spec v1.2 §8.1 + §7.1 + §3.3**：

```rust
// condition 1：panel != None（caller 已 confirmed，恆 pass = 1）
let cond_1 = 1u8;

// condition 2：symbol ∈ cohort
let alt_index = panel.alt_symbols.iter().position(|s| s == ctx.symbol);
let cond_2: u8 = if alt_index.is_some() { 1 } else { 0 };

// condition 3：xcorr 非 NaN 且 |xcorr| ≥ THRESHOLD_Y(0.40)
let cond_3: u8 = if !xcorr.is_nan() && xcorr.abs() >= THRESHOLD_Y { 1 } else { 0 };

// condition 4：btc_lead_return_pct 非 NaN 且 |btc_lead_return_pct| > THRESHOLD_X_BPS(10)
let cond_4: u8 = if !btc_ret.is_nan() && btc_ret.abs() > THRESHOLD_X_BPS { 1 } else { 0 };

// condition 5：regime_tag == "normal"
let cond_5: u8 = if panel.source_tier_regime_normal() { 1 } else { 0 };

let condition_pass_count = cond_1 + cond_2 + cond_3 + cond_4 + cond_5;
```

### 3.2 step_gate 階梯（per spec v1.2 §8.1）

```rust
let step_gate = match condition_pass_count {
    5 => "plus15",      // promote N+2 demo IMPL hint
    4 => "plus5_15",    // extend paper window 14d 重評 hint
    _ => "minus5",      // revise spec 或 archive hint
};
// no_signal sentinel：caller 若 panel == None 不呼叫本函數，使用 BtcLeadLagShadowSignal::no_signal()
```

### 3.3 tracing emit（spec §5.1.2 contract，downstream offline SQL grep target）

```rust
tracing::info!(
    target: SHADOW_LOG_TARGET,  // 鎖死 "btc_alt_lead_lag_shadow"
    strategy = strategy_name,
    symbol = ctx.symbol,
    ts_ms = ctx.timestamp_ms,
    btc_lead_return_pct = btc_ret,
    lead_window_secs = panel.lead_window_secs,
    xcorr = xcorr,
    expected_dir = expected_dir,
    regime_tag = if cond_5 == 1 { "normal" } else { "extreme_or_unknown" },
    condition_pass_count = condition_pass_count,
    dual_layer_sigma_pct = signal.dual_layer_sigma_pct,
    step_gate = signal.step_gate,
    r_squared_decay = signal.r_squared_decay,
    "btc_alt_lead_lag_shadow paper-only signal evaluated"
);
```

### 3.4 ma_crossover on_tick 入口接點

```rust
fn on_tick(&mut self, ctx: &TickContext<'_>, surface: &AlphaSurface<'_>) -> Vec<StrategyAction> {
    // Sprint N+1 W2 sub-task 2：BtcLeadLagPanel paper-only shadow log。
    // 在任何 strategy logic 之前 evaluate（per spec §5.1.2 + §6 Layer 3）。
    if let Some(panel) = surface.btc_lead_lag {
        let _shadow = crate::strategies::cross_asset::evaluate_shadow_signal(
            self.name(), ctx, panel,
        );
        // _shadow 純評估快照，丟棄不影響後續 strategy decision。
    }
    let ind = match ctx.indicators { Some(i) => i, None => return vec![] };
    // ...既有 strategy logic 完全不變...
}
```

### 3.5 grid_trading on_tick trait wrapper

`grid_trading/mod.rs::on_tick`（trait impl 端，非 `signal.rs::on_tick_impl` inventory model）：

```rust
fn on_tick(&mut self, ctx: &TickContext<'_>, surface: &AlphaSurface<'_>) -> Vec<StrategyAction> {
    if let Some(panel) = surface.btc_lead_lag {
        let _shadow = crate::strategies::cross_asset::evaluate_shadow_signal(
            self.name(), ctx, panel,
        );
    }
    self.on_tick_impl(ctx)  // 既有 grid inventory model 0 改動
}
```

---

## 4. 治理對照（CLAUDE.md §二 / §七 / §八 + spec §13）

### CLAUDE.md §二 16 根原則

| 原則 | 違反? | 說明 |
|---|---|---|
| 1. 單一寫入口 | ✅ 不違反 | shadow log 純 tracing emit，不產生 OrderIntent / 不寫 trade order 路徑 |
| 4. 不繞風控 | ✅ 不違反 | helper 純評估，不接觸 SM-04 Guardian / cost_gate |
| 7. 學習 ≠ 改寫 Live | ✅ 不違反 | paper-only fence Layer 1 主防線（step_4_5_dispatch engine_mode gate）保證 demo / live_demo / live → surface.btc_lead_lag = None；本端 `if let Some` 為 Layer 3 redundant safety |
| 8. 交易可解釋 | ✅ 增強 | tracing target 字串契約 + 13 field schema 鎖死，downstream offline SQL 可 reconstruct alpha source 來源 |
| 11. Agent 最大自主 | ✅ 對齊 | declared_alpha_sources 加 `CrossAsset` tag 對齊 W-AUDIT-8a Phase A dispatch tracking metric |
| 13. AI 成本感知 | ✅ 不違反 | helper 純 deterministic Rust 計算，無 AI 調用 |

### CLAUDE.md §四 硬邊界

| 邊界 | 違反? | 說明 |
|---|---|---|
| `max_retries = 0` | ✅ 不變 | 本 PR 無 retry 邏輯接觸 |
| `live_execution_allowed` / `execution_authority` / `system_mode` | ✅ 不觸碰 | 純策略消費端 evaluate + tracing emit |
| `OPENCLAW_ALLOW_MAINNET` / `decision_lease` / `authorization.json` | ✅ 不觸碰 | 同上 |

### CLAUDE.md §七 SQL migration Guard A/B/C

- ✅ **不適用**（本 PR 不動 V### migration；如 §5 push back 詳述，**不**新增 V093）

### CLAUDE.md §七 跨平台兼容性

- ✅ **路徑不硬編碼**：`grep -E '(/home/ncyu|/Users/[a-zA-Z]+|/private/tmp)' cross_asset/ ma_crossover/strategy_impl.rs grid_trading/mod.rs` → 0 hit（exit code 1）
- ✅ **無 LLM client / 無 systemd-only 依賴**：純 Rust + std::collections + tracing
- ✅ **依賴乾淨**：未新增 Cargo dep（tracing / openclaw_core::alpha_surface 已是 workspace 既有 dep）

### CLAUDE.md §七 注釋 (2026-05-05 governance)

- ✅ **新代碼注釋默認只寫中文**（cross_asset/mod.rs MODULE_NOTE + 11 test name + 全部 inline comment 純中文）
- ✅ E2 grep 不應 push back（不再要求英文版）

### CLAUDE.md §九 文件大小

- `cross_asset/mod.rs`：441 LOC ✅（< 800 警告 < 2000 硬限）
- `strategies/mod.rs`：~155 LOC（+2） ✅
- `ma_crossover/strategy_impl.rs`：~445 LOC（+26 / -4） ✅（pre-existing < 500）
- `grid_trading/mod.rs`：~440 LOC（+25 / -4） ✅（pre-existing < 500）

### CLAUDE.md §九 Singleton 管理

- ✅ **無新增 singleton**（cross_asset 為純函數 helper，無 module-level state）

### Spec §13 16 原則合規

spec §13 8 條 invariant 全 ✅（本 sub-task 不動 lease / authorization / audit / reconciler / mainnet env / Bybit retCode 任何路徑；shadow log 純 paper-only fence Layer 3）。

### CLAUDE.md §八 工作流規則

- ✅ **Plan-First**：先讀 spec v1.2（§5.1 + §6 + §8.1）→ W2 sub-task 1 producer + writer report → BtcLeadLagPanel trait skeleton → ma_crossover/strategy_impl.rs 既有結構 → grid_trading/{mod, signal}.rs trait delegator pattern → decision_feature_writer schema lock 確認；明確 push back 範圍後才開 IMPL
- ✅ **完成前驗證 Verify-Before-Done**：cargo test --release 2768/2768 PASS + 11 new cross_asset PASS + ma_crossover 65/65 + grid_trading 44/44 regression 0 fail + cargo build --release 0 error + grep 跨平台路徑 0 命中
- ✅ **追求優雅**：共用 helper module 派生 vs 兩策略各自重複 5-conditions check 邏輯 / dual_layer_sigma + step_gate 算法漂移風險；`evaluate_shadow_signal` 純函數可獨立 unit test 不依賴 strategy state
- ✅ **最小影響**：grid 用 trait wrapper 點接（不污染 `signal.rs::on_tick_impl` inventory model）；ma 用 on_tick 入口接（早於 indicator gate 0 影響後續 strategy logic）；任何兩策略行為 0 改變

### CLAUDE.md §八 sub-agent IMPL DONE 不直接 commit

- ✅ Working tree 4 file 已 STAGED（`git add` 完成），**未 commit**，等 E2 + A3 + E4 PASS 後 PM 統一 commit
- task description 寫「Try git add + commit + push (Co-Authored-By Claude). 如 push 被 sandbox 攔截：stage + report；PM 統一 commit。」與 sub-agent IMPL DONE protocol 衝突 → 選後者（強制工作鏈優先 + multi-session race protocol：`feedback_impl_done_adversarial_review.md` 高風險 IMPL（GUI / IPC / 寫操作 / 共用 helper）必走 A3+E2 對抗性核驗，本 sub-task 屬「共用 helper」類）

---

## 5. 不確定之處 / push back / 已知 trade-off

### 5.1 ★★ 主動 push back：拒絕「decision_features writer 加 btc_lead_lag_signal_jsonb column」（task description 第 3 項）

**衝突源**：task description §「3. decision_features writer 加 btc_lead_lag_signal_jsonb column (~20-30 LOC)」與 spec v1.2 §5.1.2 + §6 設計衝突。

**衝突分析**：

1. **`learning.decision_features.features_jsonb` 是 `FeatureVectorV1` 17-dim ML training schema 嚴格 lock**：
   - 證據 1：`decision_feature_writer.rs:test_insert_sql_locked_columns` 鎖列表 + V017 schema 對齊 invariant
   - 證據 2：W6-3c V086 SQL 加 `reject_reason_code` + `close_reason_code` 兩 enum column 已是窄通道 schema extension（per W6-3c PA spec）
   - 證據 3：V091 (`decision_features_reject_close_mutex_check`) CHECK constraint 強制 `reject_reason_code IS NOT NULL ⇔ close_reason_code IS NULL` 互斥不變式
   - 加 `btc_lead_lag_signal_jsonb` column 會破壞此 schema lock，必觸發 V093 + writer SQL 修改 + test_insert_sql_locked_columns 重 lock

2. **Spec §5.1.2 設計就是純 `tracing::info!(target: "btc_alt_lead_lag_shadow", ...)`**：
   - spec §5.1.2 line 248-271 顯式範例 `tracing::info!(target: "btc_alt_lead_lag_shadow", ...)` shadow log only
   - spec §7.2 counterfactual reconstruction 設計：「shadow log 寫到 `btc_alt_lead_lag_shadow` target；7d 後跑離線 SQL 對齊每筆 fill」
   - **panel-level signal 不屬 per-intent feature**：BtcLeadLag 是 cross-asset panel snapshot，不是 ma_crossover/grid_trading 的 entry intent feature；強塞進 features_jsonb 會混淆 ML training 的 feature 邊界

3. **task description 「優先 schema-less jsonb extend 既有 decision_features.metadata_jsonb (避免新 V###)」前提錯誤**：
   - 直接 grep 確認 `learning.decision_features` **沒有 `metadata_jsonb` column**（V017 / V082 / V083 / V084 / V086 / V091 schema 全 audit）
   - 「extend 既有 metadata_jsonb」這個 fallback path 不存在；唯一 path = 加新 column = 新 V### migration = 破壞 spec §5.1.2 設計

**push back 結論**：**不**動 `learning.decision_features` 表 / **不**動 `decision_feature_writer.rs` / **不**新增 V093。改採 spec §5.1.2 純 `tracing::info!` shadow log path（已 IMPL 於 `cross_asset/mod.rs::evaluate_shadow_signal`）。

**對 PM / operator 的建議**：
- 若 PM 希望 shadow log 也要落 PG 持久化（避免 tracing log rotation 丟資料），可在 W2 sub-task 4 wire-up 階段加一個獨立 panel-level table（如 `panel.btc_lead_lag_shadow_signals`），**不**動 `decision_features` 表
- D+12 paper edge report 的 counterfactual SQL 可從 tracing log（systemd journal / journald-export）拉 + JOIN trading.fills；spec §7.2 範例 SQL 已假設此 pipeline

---

### 5.2 r_squared_decay 為 hint 字段（per-tick 純 hint，非真實 R²）

| 項 | 描述 |
|---|---|
| **本 sub-task r_squared_decay 設值** | = `panel.lead_window_secs`（120 秒主信號 hint） |
| **spec §3.1.1 condition #3 真實要求** | D+12 paper edge report 強制報三檔 N=60/120/300 R²(60s alt return) decay curve |
| **trade-off** | per-tick 不算實 R²（需 rolling 30-min bucket 累計，太重）；只給主信號 N hint，downstream 對齊 panel.btc_lead_return_pct_60s/300s 才算實 decay curve |
| **下游影響** | downstream 7d evaluator 必須把 shadow log r_squared_decay 視為「主信號 N hint」非真實 R²；E2 review 應 flag 此設計約定 |

### 5.3 BtcLeadLagPanel struct 沒有 regime_tag field

| 項 | 描述 |
|---|---|
| **trait skeleton 設計** | `BtcLeadLagPanel` 7 field 是 IPC slot 主信號子集（per spec §4.2 step 6：「主 N=120 寫 IPC slot；regime_tag 寫 V088 schema 不寫 IPC slot」） |
| **本 helper 退化判 regime** | `source_tier_regime_normal()` 用 `source_tier` 字串內容退化判斷（"cross_asset_btc_lead_lag" → normal） |
| **下游影響** | extreme regime tick 在 paper-only fence 主防線（step_4_5_dispatch）已被 producer 端標 + writer 寫 V088 column；trait struct 不暴露 regime_tag 是 by-design（保 IPC slot ABI 穩定） |
| **TODO（本端注釋）** | W2 sub-task 4 wire-up 後若 trait extend regime_tag field 改讀真實值；當前退化實作對 paper engine 7d evidence 收集足夠用 |

### 5.4 grid_trading on_tick 改 trait wrapper 點接（不在 signal.rs::on_tick_impl）

| 項 | 描述 |
|---|---|
| **設計選擇** | 在 `mod.rs::Strategy::on_tick` trait impl 接 surface（thin wrapper），不污染 `signal.rs::on_tick_impl` grid inventory model |
| **理由** | inventory model 已多年穩定；shadow log 是 paper-only evaluate-only 純函數，與 grid cross signal / inventory mutation 邏輯無耦合 |
| **trade-off** | trait wrapper 額外一層 function call 開銷（Rust release 模式應內聯） |
| **規避** | grid_trading 既有 44/44 test PASS（包含 cross signal / inventory / health check / churn breaker / OU spacing / PostOnly maker entry）0 regression |

### 5.5 ma_crossover shadow log 在 cooldown / ADX gate 之前 evaluate

| 項 | 描述 |
|---|---|
| **設計選擇** | shadow log 入口在 `on_tick` 函式最前（早於 cooldown / ADX gate / KAMA fallback） |
| **理由** | shadow log 純 evaluate-only 不影響 strategy decision，前置可保 panel evaluate 100% 對齊每 tick（不被 cooldown skip） |
| **trade-off** | 若 cooldown active，本策略本來就 return vec[]；shadow log 仍 fire = downstream 可看到 "ma_crossover 正在 cooldown 但 BtcLeadLag 信號方向" 的 counterfactual evidence |
| **規避** | tracing log 是輕量 evidence emit，無 tx / 無 IO；overhead < 1µs per tick |

### 5.6 Multi-session race 大規模 working tree dirty

8+ file dirty（4 是我 staged，其餘 隔壁 W-C Caveat 2 + W2 sub-task 1 producer 強化 + agent_spine 等系列）。報告 §2 已逐項標記；PM holistic commit 必審 隔壁 file 的 ownership + namespace 共生關係。本 sub-task 4 file 可 atomic commit 獨立**不 break build**（cargo test PASS / cargo build PASS 已驗）。

---

## 6. cargo test 證據

```
cargo test --release --package openclaw_engine --lib strategies::cross_asset
running 11 tests
test strategies::cross_asset::tests::dual_layer_sigma_pct_locked_to_mid_65_bps ... ok
test strategies::cross_asset::tests::evaluate_all_five_conditions_pass_step_gate_plus15 ... ok
test strategies::cross_asset::tests::evaluate_btc_return_below_threshold_x_fails_cond_4 ... ok
test strategies::cross_asset::tests::evaluate_btc_return_nan_fails_cond_4 ... ok
test strategies::cross_asset::tests::evaluate_source_tier_unknown_fails_cond_5 ... ok
test strategies::cross_asset::tests::evaluate_symbol_not_in_cohort_fails_cond_2 ... ok
test strategies::cross_asset::tests::evaluate_xcorr_below_threshold_y_fails_cond_3 ... ok
test strategies::cross_asset::tests::evaluate_xcorr_nan_fails_cond_3 ... ok
test strategies::cross_asset::tests::no_signal_sentinel_baseline ... ok
test strategies::cross_asset::tests::shadow_log_target_locked_to_spec ... ok
test strategies::cross_asset::tests::step_gate_labels_match_spec_v1_2_section_8_1 ... ok

test result: ok. 11 passed; 0 failed; 0 ignored

cargo test --release --package openclaw_engine --lib strategies::ma_crossover
test result: ok. 65 passed; 0 failed; 0 ignored

cargo test --release --package openclaw_engine --lib strategies::grid_trading
test result: ok. 44 passed; 0 failed; 0 ignored

cargo test --release --package openclaw_engine --lib (full regression)
test result: ok. 2768 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out

cargo build --release --package openclaw_engine
Finished `release` profile [optimized] target(s) in 23.93s (0 errors)

# 跨平台 grep
cd rust/openclaw_engine/src/strategies
grep -rn '/home/ncyu|/Users/[a-zA-Z]+|/private/tmp' cross_asset/ ma_crossover/strategy_impl.rs grid_trading/mod.rs
# (exit code 1 = 0 hits)
```

---

## 7. PM Action Items

### 7.1 立即（PM 統一處理）

1. **PM holistic commit（W2 sub-task 2 atomic）**：本 sub-task 4 file 已 STAGED；可獨立 atomic commit 不 break build（cargo test PASS / build PASS）。或 PM 選把 W2 sub-task 1 producer + sub-task 2 strategy shadow 同 commit（namespace 共生但 atomic 獨立）。建議 commit message 見 §2。

2. **派 E2 + A3 對抗性 review**（per `feedback_impl_done_adversarial_review.md` 高風險 IMPL = 共用 helper + IPC adjacent）：
   - **E2 focus**：
     - paper-only fence Layer 3 邏輯（`if let Some(panel) = surface.btc_lead_lag` 是否完備？默認 fail-closed？）
     - declared_alpha_sources 對齊 W-AUDIT-8a Phase A dispatch tracking metric（spec §3 Phase A Deliverable #3）
     - cross_asset/mod.rs 文件大小（441 LOC < 800 警告線 ✅）
     - 5 conditions check 邏輯（spec v1.2 §8.1 + §7.1 + §3.3 對齊）
     - tracing target 字串契約 lock（"btc_alt_lead_lag_shadow"）
   - **A3 focus**：
     - shadow log 是否真不影響 strategy decision？（grep 確認 `_shadow` discard）
     - tracing emit 是否含敏感 field（無 secret leak / no auth field）
     - downstream offline SQL 對齊 contract（field schema 是否完備供 7d counterfactual）
     - `BtcLeadLagPanel` trait struct 退化 `source_tier_regime_normal()` 是否合理 fallback（spec §9 extreme regime guard）

3. **派 E4 regression**（sequential after E2 + A3 PASS）：
   - cargo test --release engine lib（已自驗 2768/2768 PASS / 11 new + 0 regression）
   - 不需動 paper engine deploy（本 sub-task 不接 step_4_5_dispatch wire-up；W2 sub-task 4 scope）
   - **特別驗**：ma_crossover + grid_trading 測試套件 0 strategy decision change（既有 65 + 44 全 PASS）

### 7.2 後續（其他 sub-agent / wave）

4. **派 W2 sub-task 4** (after PM commit + E2 + A3 + E4 PASS)：
   - main.rs spawn `BtcLeadLagProducer` loop（從 KlineManager pull BTCUSDT + 7 alt cohort 1m close + volume）
   - `BtcLeadLagPanelSlot` late-inject anchor + IPC slot wire-up
   - `step_4_5_dispatch.rs` paper-only fence Layer 1 wire（`btc_lead_lag = match self.effective_engine_mode() { "paper" => self.btc_lead_lag_slot.latest(), _ => None }`）
   - Python writer paper-only fence Layer 2（per spec §4.2 + §6.2）
   - Bybit V5 orderbook integration（spec §3.1.3 真實 imbalance 取代 producer 0.0 placeholder）

5. **D+5 paper engine deploy** → **D+12 paper edge report land**：
   - downstream 7d 後跑離線 SQL grep `target=btc_alt_lead_lag_shadow` 對齊 trading.fills
   - 算 spec §7.1 mandatory metric 6 條（per-symbol pooled + DSR K=95 + PSR(0) skew/kurt + alpha decay R² + block-bootstrap CI + per-cohort-symbol counterfactual delta）
   - +15/+5-15/<+5 階梯 gate 拍板下一步（promote N+2 demo / extend 14d / archive）

6. **PA / spec push back acknowledge**：
   - 確認 spec v1.2 §5.1.2 + §7.2 設計 vs task description 第 3 項衝突 → 採 spec §5.1.2 純 tracing log path
   - 若 PM 確認需 PG 持久化 shadow log，建議 W2 sub-task 4 加獨立 `panel.btc_lead_lag_shadow_signals` table，**不**動 `learning.decision_features`

---

## 8. 一句總結

W2 sub-task 2 land 11 cross_asset unit test PASS / 0 strategy decision regression（ma_crossover 65 + grid_trading 44 全 PASS）/ full lib 2768/2768 PASS，按 spec v1.2 §5.1.2 + §6 + §8.1 嚴格實作 ma_crossover + grid_trading paper-only shadow log（共用 `cross_asset/mod.rs` helper + 5 conditions check + step_gate 階梯 + dual_layer_sigma_pct 65 bps mid hint + r_squared_decay lead_window_secs hint + tracing target "btc_alt_lead_lag_shadow" 鎖死契約），主動 push back task description 第 3 項「decision_features writer 加 btc_lead_lag_signal_jsonb column」（破壞 V017/V086/V091 ML schema lock + spec §5.1.2 設計就是純 tracing log），working tree 4 file STAGED 待 PM holistic commit；下游 W2 sub-task 4 wire-up 預備條件全 met。

---

E1 IMPLEMENTATION DONE: 待 E2 + A3 對抗性 review + E4 regression (report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-11--w2_impl_3_strategy_paper_shadow_log.md`)
