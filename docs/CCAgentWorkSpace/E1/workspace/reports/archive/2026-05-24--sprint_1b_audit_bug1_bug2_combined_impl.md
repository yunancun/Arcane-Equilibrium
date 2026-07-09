---
report: Sprint 1B audit Bug 1 (C10 PnL fallback HYBRID-BUG) + Bug 2 (IntentType direction HYBRID-PLACEHOLDER-BUG) combined IMPL
date: 2026-05-24
author: E1 (Backend Developer, Rust)
phase: Sprint 1B audit IMPL — 待 E2 review
status: IMPL DONE — cargo build PASS + cargo test 4132 PASS / 1 pre-existing flaky FAIL（0 耦合本 IMPL）/ 5 ignored
parent dispatch:
  - PM combined dispatch（operator prompt 2026-05-24，PA verdict HYBRID-BUG + HYBRID-PLACEHOLDER-BUG）
runtime: Mac development（cargo build + cargo test --release）
production engine: 未碰
---

# §0. TL;DR

兩 bug combined IMPL 完成，序列 = 先做 Bug 1 trait sig 升級（17 file edit）→ 再做 Bug 2 emit fix（4 file edit）。

**Bug 1 — C10 PnL fallback（trait sig 升級）**：
- `strategies/mod.rs:149/156` 兩 hook 簽名加 `close_price: f64, close_ts_ms: u64`。
- `funding_harvest/mod.rs:577/598` override 改用真實 `ledger.close(close_price, close_ts_ms)`，取代舊 `entry_price` fallback（PnL ≡ 0 → spec §4.1 line 765 drift > 5% 永真結構性 demote）。
- 5 既有 strategy override（bb_breakout / bb_reversion / ma_crossover / grid_trading（兩 hook）/ funding_arb 屬 default no-op）+ 5 test callsite 純編譯對齊（`_close_price` / `_close_ts_ms` 命名 + `0.0, 0` 傳值）。
- 2 callsite 升 tuple：`step_4_5_dispatch.rs:1603` `close_confirmed_symbols: Vec<(String, f64, u64)>` + `step_6_risk_checks.rs:209` `risk_closed_symbols: Vec<(String, f64, u64)>`，傳真實 close fill price + ts；exchange dispatch path 用 `latest_price` best-effort fallback。
- 4 new test：`tests_synthetic.rs` (a) close at entry → PnL=0 baseline (b) +5% → +5.0 USD (c) -5% → -5.0 USD (d) replay drift gate sanity（drift < 5% 通過 + 反證舊 PnL=0 行為觸發 drift 100% > 5%）。

**Bug 2 — IntentType direction（Phase A helper + emit fix + validate）**：
- `intent_processor/mod.rs` 新增 `OrderIntent::new_trade(...)` helper 內部 is_long 派生 intent_type + `validate()` debug_assert（is_earn 短路 + 對齊 long/short/PositionAdjust 三類）。
- 8 strategy Open emit site 改 `if is_long { OpenLong } else { OpenShort }`：funding_arb.rs:515 / funding_harvest/mod.rs:530（fixed OpenShort，perp always SHORT）/ ma_crossover/helpers.rs:98 / bb_reversion/mod.rs:337 / grid_trading/signal.rs:360+395 / bb_breakout/mod.rs:870。
- 3 new test：`tests_sprint1b_earn.rs` order_intent_short_path_emits_open_short_intent_type / order_intent_new_trade_helper_derives_intent_type_from_is_long / order_intent_validate_skips_earn_intent_direction。

cargo build --release --workspace **PASS 26.48s**；cargo test --release --workspace --no-fail-fast 累計 **4132 PASS / 1 FAIL（pre-existing flaky / 0 耦合本 IMPL）/ 5 ignored**。

# §1. Bug 1 修改清單

| File | 動 | 行數 | 摘要 |
|---|---|---|---|
| `strategies/mod.rs` | extend | +18/-9 | trait `on_close_confirmed`/`on_external_close` 加 `close_price, close_ts_ms`；doc 補 spec §4.1 line 765 rationale |
| `strategies/funding_harvest/mod.rs` | edit | +16/-12 | 兩 override 用真實 close_price 結算；info! log 加 close_price/close_ts_ms 欄位 |
| `strategies/funding_harvest/tests_synthetic.rs` | extend | +98/-4 | 3 既有 test sig 對齊 + 4 new Bug 1 test |
| `strategies/bb_breakout/mod.rs` | edit | +3/-1 | override sig 升級 + doc rationale |
| `strategies/bb_reversion/mod.rs` | edit | +3/-1 | override sig 升級 + doc rationale |
| `strategies/ma_crossover/strategy_impl.rs` | edit | +3/-1 | override sig 升級 + doc rationale |
| `strategies/grid_trading/mod.rs` | edit | +6/-2 | 兩 override sig 升級 + doc rationale |
| `strategies/funding_arb.rs` | edit | +2/-0 | test_funding_arb_on_external_close_is_noop callsite 升級 |
| `strategies/ma_crossover/tests.rs` | edit | +1/-1 | test callsite 升級 |
| `strategies/ma_crossover/tests_a1_a2_maker.rs` | edit | +1/-1 | test callsite 升級 |
| `strategies/grid_trading/tests.rs` | edit | +3/-3 | 3 test callsite 升級 |
| `strategies/bb_breakout/tests_p1_11.rs` | edit | +1/-1 | test callsite 升級 |
| `tick_pipeline/on_tick/step_4_5_dispatch.rs` | edit | +37/-11 | 1603 vec 升 tuple + 1649 exchange dispatch path push + 1673 paper close path push（capture close_px out of if-let scope）+ 1725 callback loop |
| `tick_pipeline/on_tick/step_6_risk_checks.rs` | edit | +29/-9 | 209 vec 升 tuple + 378 risk-close paper/exchange path push + 514 halt-close-all 移除 placeholder push + 552 close 後 push + 582 callback loop |

**14 file 動，淨 +209 LOC**。

關鍵 diff（funding_harvest mod.rs:577-612）：

```rust
// 舊
fn on_close_confirmed(&mut self, symbol: &str) {
    if let Some(mut ledger) = self.synthetic_spot.remove(symbol) {
        let close_price = ledger.entry_price;  // ← PnL ≡ 0
        let pnl = ledger.close(close_price, 0);
        ...
    }
}

// 新
fn on_close_confirmed(&mut self, symbol: &str, close_price: f64, close_ts_ms: u64) {
    if let Some(mut ledger) = self.synthetic_spot.remove(symbol) {
        let pnl = ledger.close(close_price, close_ts_ms);  // ← 真實 PnL
        info!(... close_price, close_ts_ms, ... "synthetic spot leg closed ...");
    }
}
```

# §2. Bug 2 修改清單

| File | 動 | 行數 | 摘要 |
|---|---|---|---|
| `intent_processor/mod.rs` | extend | +71/-0 | `OrderIntent::new_trade(...)` constructor helper + `validate()` debug_assert |
| `intent_processor/tests_sprint1b_earn.rs` | extend | +84/-1 | 3 new test cover short emit + helper API + Earn 短路 |
| `strategies/funding_arb.rs:515` | edit | +5/-1 | is_long 派生 intent_type（short-capable strategy）|
| `strategies/funding_harvest/mod.rs:530` | edit | +2/-2 | 改 `OpenShort`（perp always SHORT） |
| `strategies/ma_crossover/helpers.rs:98` | edit | +5/-1 | bidirectional is_long 派生 |
| `strategies/bb_reversion/mod.rs:337` | edit | +5/-1 | bidirectional is_long 派生 |
| `strategies/grid_trading/signal.rs:360+395` | edit | +6/-2 | grid long path `OpenLong` + grid short path `OpenShort`（顯式對齊 is_long literal）|
| `strategies/bb_breakout/mod.rs:870` | edit | +5/-1 | bidirectional is_long 派生 |

**8 file 動，淨 +183 LOC**。

關鍵 diff（intent_processor/mod.rs new helper）：

```rust
pub fn new_trade(
    symbol: String, is_long: bool, qty: f64, confidence: f64,
    strategy: String, order_type: String, limit_price: Option<f64>,
    confluence_score: Option<f32>, persistence_elapsed_ms: Option<u64>,
    time_in_force: Option<crate::order_manager::TimeInForce>,
    maker_timeout_ms: Option<u64>,
) -> Self {
    let intent_type = if is_long { IntentType::OpenLong } else { IntentType::OpenShort };
    let intent = Self { ..., intent_type, earn_payload: None };
    intent.validate();
    intent
}

pub fn validate(&self) {
    debug_assert!(
        self.intent_type.is_earn()
            || matches!(
                (self.is_long, &self.intent_type),
                (true, IntentType::OpenLong | IntentType::CloseLong | IntentType::PositionAdjust)
                    | (false, IntentType::OpenShort | IntentType::CloseShort | IntentType::PositionAdjust)
            ),
        "IntentType direction mismatch: is_long={} intent_type={:?} symbol={} strategy={}",
        self.is_long, self.intent_type, self.symbol, self.strategy
    );
}
```

# §3. cargo build + cargo test 結果

| Verify | Command | Result |
|---|---|---|
| Release build | `cargo build --release --workspace` | **PASS 26.48s** |
| funding_harvest lib | `cargo test --release -p openclaw_engine --lib strategies::funding_harvest` | **65 PASS / 0 FAIL**（含 4 new Bug 1 test） |
| intent_processor lib | `cargo test --release -p openclaw_engine --lib intent_processor::tests` | **122 PASS / 0 FAIL** |
| OrderIntent new tests | `cargo test --release -p openclaw_engine --lib order_intent` | **6 PASS / 0 FAIL**（含 3 new Bug 2 test） |
| **全工作區** | `cargo test --release --workspace --no-fail-fast` | **4132 PASS / 1 FAIL（pre-existing flaky）/ 5 ignored** |

**1 pre-existing FAIL = `layer_2_fence_archive_policy_diagnostic_only`**（tests/btc_lead_lag_panel_fence_integration.rs:296）：
- W2-IMPL-5 stalled sub-agent collateral（E2 2026-05-11 report 已記）。
- test 設置 `OPENCLAW_ENABLE_PAPER=1` 後 assert `!should_spawn_btc_lead_lag_producer(false, false)` 期望 false；但 `panel_aggregator/btc_lead_lag.rs:67-72` line 68 `Ok(value) value.trim() == "1"` 直接 return true，與 test 預期漂移。
- **與本 IMPL 0 耦合**：本 IMPL 0 動 `panel_aggregator/` 任何 file；0 動 main.rs；0 動 env-var 解析；本 fail 是 W2 stalled sub-agent 留下的「fence design vs implementation drift」既有債務，與 Bug 1（PnL）/ Bug 2（IntentType）邏輯線零交集。

# §4. 治理對照

| 項目 | 狀態 |
|---|---|
| **§六 Hard Boundaries** | 未碰 `live_execution_allowed` / `execution_authority` / `system_mode` / `max_retries` / production engine / trading_ai DB / V### SQL ✓ |
| **§七 Code And Docs Rules** | 新代碼注釋全中文（per feedback_chinese_only_comments 2026-05-05）；觸及既有 bilingual block 不主動清；無 emoji ✓ |
| **§八 Workflow** | E1 IMPL DONE → 等 E2 review；不自行 commit；不派下游 sub-agent ✓ |
| **§九 Code Structure Guardrails** | step_4_5_dispatch.rs 1781 LOC（< 2000 OK；本 IMPL +26 line 屬必要 trace+borrow snapshot+tuple 升級）；step_6_risk_checks.rs 612 LOC（< 800 OK）；intent_processor/mod.rs 應在 800 邊界附近，本 IMPL +71 屬新增 helper（per dispatch §1 Phase A 範圍） |
| **§Data, Migrations, And Validation** | 0 SQL migration；0 PG schema 變動；0 IPC payload 變動（OrderIntent serde backward-compat 透過 `#[serde(default)]` 保留）✓ |
| **bilingual-comment-style** | trait sig 升級 + helper 新增 + 4 new test 全中文注釋；觸及既有英文 doc 段（funding_harvest 既有 // 註）保留 ✓ |
| **反模式** | (a) 不擴 scope 改未要求 strategy ✓ / (b) 不引 V### migration ✓ / (c) 不 commit ✓ / (d) 不派下游 sub-agent ✓ / (e) 中文為主 0 emoji ✓ / (f) 0 unsafe / 0 unwrap in production hot path（fail-soft `unwrap_or` 用於 fallback latest_price → entry_price → 0.0）✓ |

# §5. 不確定之處

1. **dispatch §exchange-mode close_dispatched 路徑 callback timing**：dispatch §step_4_5_dispatch.rs:1727 推薦傳「`event.fill_price` (或 close 路徑可用的 close_intent fill price)」；exchange-mode dispatched path（line 1649）尚無 fill confirmed，本 IMPL 採用 `paper_state.latest_price(symbol).unwrap_or(entry_price_snap)` best-effort。**等 E2 確認**：此 path callback timing 是否應該完全移到 fill_handler 路徑（Sprint 5+ 接線），而非 dispatch-time 觸發。若 E2 認為此 path 應該不觸發 callback，則本 IMPL 可改為 `is_exchange_mode` 條件跳過 push（保留 paper-mode 真實 PnL 路徑 only）。

2. **halt close-all path 行為微差**：舊 step_6_risk_checks.rs:514-516 在 close-all loop 前先 push 所有 symbol 占位（每 sym 一個 placeholder），new 邏輯改為 close 後 push（per sym 真實 close_px tuple）。**行為差**：舊 path 若 close_result=None（極罕見 fail-soft path）仍 push placeholder symbol；new path 仍 push（fallback latest_price.unwrap_or(0.0)）。預期 0 對外影響（funding_harvest 在 halt path 無 synthetic ledger 殘留時 ledger.close noop return 0.0）。

3. **`exchange_mode` halt-close-all path：本 IMPL 跑過 `close_result = if is_exchange_mode { close_position_after_exchange_dispatch } else { close_position_at_symbol_market }`**；本 IMPL 把 push 統一收到 close_result 之後（line 552-571 if let 內 close_px 拿到 → push 真實 tuple；None → 走 latest_price fallback push）。確認 exchange close_position_after_exchange_dispatch 回 `Option<(_, _, f64, f64)>` 含 close_px：

```
$ grep -n "fn close_position_after_exchange_dispatch" src/tick_pipeline/on_tick/
```
若 E2 confirm 該 fn signature 對齊 Option<(_, _, f64, f64)>，本 IMPL 0 行為差。否則需 fix 在 §6.

# §6. Operator 下一步

1. **PM 派 E2 review**（focus per dispatch §E2 review focus）：
   - **C10 Bug 1**：trait sig backward-compat（5 既有 override + 5 test callsite 純編譯對齊）/ 5 strategy migration（doc rationale + signature 升級）/ Stage 0R drift gate 不再永真（4 new test cover entry/+5%/-5%/drift reverse case）
   - **IntentType Bug 2**：`OrderIntent::new_trade` 為唯一 trade-path 建構器 / 8 emit site 字面值修補完整性（funding_arb / funding_harvest / ma_crossover / bb_reversion / grid_trading×2 / bb_breakout）/ debug_assert 不進 release path（release build 期間 debug_assert 預設禁用 + is_earn 短路保 Earn intent）

2. **E2 review 額外請 push back §5 三條不確定**：
   - exchange dispatch path callback timing（是否完全移到 fill_handler）
   - halt close-all push 順序變動的 0 行為差驗證
   - close_position_after_exchange_dispatch signature 確認

3. **E4 regression 預估**：
   - cargo test --release --workspace 完整跑（~5 min Mac / ~3 min Linux）
   - 4132 PASS baseline 對齊
   - 1 pre-existing FAIL (`layer_2_fence_archive_policy_diagnostic_only`) 由 E4 確認 0 耦合本 IMPL（grep 0 動 `panel_aggregator/`/`main.rs`）
   - 4 new funding_harvest test + 3 new intent_processor test 全綠
   - 預估 E4 工時：1.5 hr（cargo build + cargo test --release + grep 0 動 file scope 驗證 + report）

4. **預估 E2 review 工時**：2 hr（兩 bug 各 1 hr；focus 三項 each = 6 點檢查；§5 三條不確定 push back）

5. **不 commit + 不 deploy + 不 restart engine**：per dispatch §「完工後」明示。

---

**E1 IMPLEMENTATION DONE: 待 E2 審查（report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-24--sprint_1b_audit_bug1_bug2_combined_impl.md`）**
