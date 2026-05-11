# E1 IMPLEMENTATION — LG-2 T2 Startup Pricing Binding Assertion

Date: 2026-05-11
Owner: E1
Wave: Sprint N+1 Wave 2.2 (LG-2 T2 — final LG-2 task)
PA tech plan: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--lg_2_3_4_design_plan.md` §2.4 (LG2-T2)
Status: DONE — awaiting E2 + E4 + A3 review chain

---

## 1. 任務性質

PA tech plan §2.4 LG-2 T2 (Rust hot path)：對 build_exchange_pipeline 在 Live
(Mainnet + LiveDemo) 路徑加裝 pricing binding 三項斷言 pre-check，與既有 5
Live gate（HMAC + freshness + env_allowed + secret slot + OPENCLAW_ALLOW_MAINNET）
並列為第 6 個 gate；任一失敗即 fail-closed reject spawn。

依賴：
- LG-2 T3 `FeeSource enum + fee_source(symbol) getter` (已 land in `account_manager.rs`)
- LG-2 T4 `PricingConfig + RiskConfig.pricing Option field + 3 TOML [pricing] sections`
  (已 land in `openclaw_types::risk` + `openclaw_engine::config::risk_config`)

---

## 2. 必要 push back（PA plan 與代碼真實狀態 drift）

### Push back 1：`build_exchange_pipeline` 真實位置

PA plan §2.4 寫 `bybit_rest_client.rs::build_exchange_pipeline` — 真實
位置是 `rust/openclaw_engine/src/startup/mod.rs:496`，定義在 startup module
而非 bybit_rest_client。`grep -rn 'fn build_exchange_pipeline'` 確認。

採取行動：以代碼真實位置為準（同 LG2-T1 教訓 + memory `feedback_v_migration_pg_dry_run`）。

### Push back 2：新 module 放 lib crate

原 startup 是 binary crate（`main.rs` 內 `mod startup;`）；若把 pricing_assert
放 `startup/pricing_assert.rs` 則 AccountManager 的 `pub(crate)
set_last_fee_refresh_ms_for_test`（在 lib crate）對 binary 不可見，無法測試。

採取行動：整個 module 放 lib crate `openclaw_engine/src/live_spawn_assert.rs`，
binary 端 `use openclaw_engine::live_spawn_assert::...` 引用。

### Push back 3：Audit log 用 tracing 不用 PG row

PA spec §2.4 寫「audit write」但未指明 storage。實測：
1. build_exchange_pipeline 是 startup-time pre-check，在 db_pool 連線**之前**
   呼叫（main.rs L313-L376 vs db_pool 在 L944+ 建立）。
2. `learning.governance_audit_log` (V035) schema 強耦合 R2/R3/R4 candidate
   review fields，event_type CHECK enum 是 ['review_live_candidate', 'lease_*',
   'audit_write_failed'] 等 — 不適合塞「live spawn pricing assert」。

採取行動：
- 走 `tracing::error!` / `tracing::warn!` / `tracing::info!`，target =
  `openclaw_engine::live_spawn_audit`（穩定 grep contract）。
- structured fields: event / env / engine_mode / fee_rate_count /
  last_fee_refresh_ms / reason_code / error。
- 寫 systemd journalctl + engine.log（restart_all.sh stdout 重定向）；
  下游 healthcheck `[45]` pricing_binding 接力做 runtime drift detection。

### Push back 4：LiveDemo + ColdDefault 邏輯解讀

PA spec acceptance 寫：
> LiveDemo + 1 symbol FeeSource = DemoConservativeDefault → spawn OK
> LiveDemo + 1 symbol FeeSource = ColdDefault → reject (不在 cold_default_acceptable_modes)

但 T4 land 的 `risk_config_live.toml` 是 `cold_default_acceptable_modes =
["demo", "live_demo"]` — **含** "live_demo"。LiveDemo 走此 TOML，按字面義
ColdDefault 應 accept（"live_demo" 在 list 內）。

採取行動：採取統一邏輯「mode_label 在 acceptable_modes 內 → 不檢查 source；
不在 → 任一 symbol 非 BybitApi reject」。spec 的「ColdDefault → reject」是
**測試 fixture 故意設 modes 不含 live_demo 的場景**，IMPL 用此邏輯都涵蓋。
test_live_demo_rejects_cold_default_when_not_in_modes（嚴格場景 reject）+
test_live_demo_accepts_cold_default_when_in_modes（寬鬆場景 accept）兩個
test 各驗一面。

---

## 3. 修改清單

### 3.1 Rust source（6 檔）

| 檔 | 改動類型 | LOC delta |
|---|---|---|
| `rust/openclaw_engine/src/live_spawn_assert.rs` | **新檔**：核心 module（enum LivePricingBindingError + wait_for_first_refresh + assert_pricing_binding + write_audit_log + 11 tests） | +540 |
| `rust/openclaw_engine/src/lib.rs` | `pub mod live_spawn_assert;` re-export | +3 |
| `rust/openclaw_engine/src/startup/mod.rs` | `build_exchange_pipeline` 加 `pricing_config: PricingConfig` param + Live kind pre-check call site (~60 LOC) | +66 |
| `rust/openclaw_engine/src/pipeline_slot.rs` | `SpawnConfig.pricing_config` field + `try_spawn` 內 clone pass-through | +12 |
| `rust/openclaw_engine/src/main.rs` | 2 處 SpawnConfig (live/demo) 加 `pricing_config` field 構造 + LiveAuthWatcher::from_parts 加 `risk_live_store` param | +20 |
| `rust/openclaw_engine/src/live_auth_watcher.rs` | LiveAuthWatcher 加 `risk_live_store: Option<Arc<ConfigStore<RiskConfig>>>` field + 3 ctor 對齊 + run loop try_spawn 取 pricing | +35 |

### 3.2 不改

- ❌ LG-2 T1/T3/T4 已 land 部分（不破契約）
- ❌ TOML config（沿用 T4 land 的 3 個 [pricing] section）
- ❌ PG migration（採 tracing audit 不寫 PG row）
- ❌ healthcheck `[45]` Python（T3 已 ship dual-source compare；T2 reason_code 對齊但 healthcheck 無需改動）
- ❌ engine restart / deploy（per CLAUDE.md §七 強制鏈：等 E2/E4/A3 + PM 統一）

---

## 4. live_spawn_assert.rs 核心 API

### 4.1 Module structure

```rust
pub const MIN_REQUIRED_FEE_RATE_COUNT: usize = 25;
pub const DEFAULT_FIRST_REFRESH_TIMEOUT: Duration = Duration::from_secs(30);

pub enum LivePricingBindingError {
    NoRefresh,
    InsufficientSymbolCoverage { count: usize },
    MainnetNonApiSource { symbol: &'static str, source: FeeSource },
    LiveDemoNonApiSourceWhenStrict { symbol: &'static str, source: FeeSource },
}

impl LivePricingBindingError {
    pub fn reason_code(&self) -> &'static str { /* 4 種對應字串 */ }
}

pub async fn wait_for_first_refresh_or_timeout(
    account_manager: &AccountManager,
    timeout: Duration,
) -> Result<(), LivePricingBindingError>;

pub fn assert_pricing_binding_for_live_spawn(
    env: BybitEnvironment,
    account_manager: &AccountManager,
    pricing_config: &PricingConfig,
) -> Result<(), LivePricingBindingError>;

pub fn write_audit_log(env, result, fee_rate_count, last_fee_refresh_ms);
pub fn write_wait_timeout_audit(env, elapsed_secs);
```

### 4.2 wait_for_first_refresh_or_timeout（PA §2.5 risk #2）

設計：30s defensive net。fee refresh 已在 build_exchange_pipeline 內
`refresh_fee_rates` 同步 await 過（line 666-715）；demo/LiveDemo 不支援端點
fallback 走 `seed_default_fee_rates`。本函式作為 backup：若 refresh await 拋
異常（網路超時、Bybit 500），允許 30s 重試窗。

- Fast path：`last_fee_refresh_ms > 0` 立即回 Ok 不 sleep
- Poll loop：每 200ms 檢查一次，最差 30s = 150 次 poll
- 30s 後仍 0 → `Err(NoRefresh)`

選擇 poll-based 而非 oneshot channel：避免在 account_manager.rs 加 cross-thread
notify 接線（broadcast / mpsc / oneshot），keep account_manager API surface 小。

### 4.3 assert_pricing_binding_for_live_spawn

三項 assertion 順序：

1. **B. fee_rate_count >= 25**：cache size 異常小（< 25）→
   `Err(InsufficientSymbolCoverage { count })`。
2. **C. per-symbol FeeSource**：對 SYMBOLS const（5 個）逐一 check：
   - `is_mainnet`：任一 symbol 之 `fee_source()` != `BybitApi` →
     `Err(MainnetNonApiSource { symbol, source })`。
   - LiveDemo (`!is_mainnet`)：
     - `mode_in_acceptable = pricing_config.cold_default_acceptable_modes.contains(mode_label)`
     - `mode_in_acceptable = true` → 不檢查 source，全 accept
     - `mode_in_acceptable = false` → 任一 symbol 非 BybitApi →
       `Err(LiveDemoNonApiSourceWhenStrict { symbol, source })`。

注意 **A. (NoRefresh)** 不在本函式內驗 — 由 caller 在 wait 階段先驗。本函式
expects last_fee_refresh_ms > 0（caller contract）。

### 4.4 mode_label mapping

```rust
let mode_label = effective_engine_mode(PipelineKind::Live, Some(env));
// Mainnet → "live"
// LiveDemo → "live_demo"
// (Demo / Testnet 在 Live kind 下也可能映射到 "live_demo")
```

與 engine_mode tag 寫 PG（per memory `engine_mode_tag_live_demo`）字串集
完全一致；下游 healthcheck `[45]` Python 端 `_infer_source` 取相同字串集。

---

## 5. build_exchange_pipeline 整合（startup/mod.rs）

### 5.1 Signature 變更

```rust
pub(crate) async fn build_exchange_pipeline(
    kind: PipelineKind,
    env: BybitEnvironment,
    cancel: CancellationToken,
    cfg_snapshot: &openclaw_engine::config::EngineBootstrap,
    pricing_config: openclaw_types::PricingConfig,  // LG-2 T2 新增
) -> Option<(ExchangePipelineBindings, Vec<JoinHandle<()>>)>;
```

### 5.2 Pre-check 插入點

位置：fee_rate refresh block 之後（line 716 後），balance fetch 之前。

```rust
let taker_fee = match acct.refresh_fee_rates(&*client_arc, "linear").await {
    Ok(count) => { /* 既有路徑：log + Some(rate) */ }
    Err(e) => {
        // 既有：demo/LiveDemo unsupported endpoint → seed_default fallback
        // 既有：mainnet 真錯 → None
    }
};

// LG-2 T2 (2026-05-11) NEW BLOCK
if kind == PipelineKind::Live {
    use openclaw_engine::live_spawn_assert::{...};

    // Step A: wait_for_first_refresh_or_timeout(30s)
    if let Err(_e) = wait_for_first_refresh_or_timeout(&acct, DEFAULT_FIRST_REFRESH_TIMEOUT).await {
        write_wait_timeout_audit(env, wait_start.elapsed().as_secs());
        warn!(...);
        return None;  // ← reject spawn
    }

    // Step B + C: assert_pricing_binding_for_live_spawn
    let assert_result = assert_pricing_binding_for_live_spawn(env, &acct, &pricing_config);
    write_audit_log(env, &assert_result, acct.fee_rate_count(), acct.last_fee_refresh_ms());
    if let Err(e) = assert_result {
        warn!(...);
        return None;  // ← reject spawn
    }
}

// 既有：balance fetch + WS spawn 繼續
```

### 5.3 Live gate 第 6 順位

```
HMAC verify (build_exchange_pipeline:511-538, LIVE-GATE-BINDING-1)
        ↓
BybitRestClient::new credentials + OPENCLAW_ALLOW_MAINNET (540-553, LIVE-GUARD-1 SEC-17)
        ↓
fee_rate refresh + seed_default fallback (666-715, existing)
        ↓
LG-2 T2 pricing binding pre-check (NEW, 716+)
        ↓
balance fetch + WS spawn (717+)
```

既有 5 gate **不破**（HMAC + freshness + env_allowed + secret slot +
OPENCLAW_ALLOW_MAINNET），LG-2 T2 為第 6 gate（fee binding-source enforcement）。

---

## 6. SpawnConfig + try_spawn pass-through (pipeline_slot.rs)

```rust
pub struct SpawnConfig<'a> {
    pub kind: SlotKind,
    pub env: BybitEnvironment,
    pub parent_shutdown_token: CancellationToken,
    pub cfg_snapshot: &'a EngineBootstrap,
    pub pricing_config: openclaw_types::PricingConfig,  // LG-2 T2 owned clone
}

impl PipelineSlot {
    pub async fn try_spawn<'a>(&self, cfg: &SpawnConfig<'a>) -> ... {
        // ...
        let built = build_exchange_pipeline(
            cfg.kind.to_pipeline_kind(),
            cfg.env,
            slot_cancel_token.clone(),
            cfg.cfg_snapshot,
            cfg.pricing_config.clone(),  // clone pass-through
        )
        .await;
        // ...
    }
}
```

`pricing_config` 用 `owned` 是因為 SpawnConfig 內 borrowed 跨 `try_spawn`
await 會限制 caller lifetime；clone 給 build_exchange_pipeline 避免生命週期糾結。
PricingConfig clone cost negligible（3 個 field，1 個 Vec<String>）。

---

## 7. main.rs SpawnConfig 構造 (2 處)

```rust
// LG-2 T2：boot 路徑 Live spawn
let live_pricing_config = risk_stores
    .live
    .load()
    .pricing
    .clone()
    .unwrap_or_default();  // PricingConfig::default() if TOML 無 [pricing]
let (live_bindings, live_slot_cancel) = match live_slot
    .try_spawn(&pipeline_slot::SpawnConfig {
        kind: pipeline_slot::SlotKind::Live,
        env: live_bybit_environment(),
        parent_shutdown_token: cancel.clone(),
        cfg_snapshot: &cfg_snapshot_pipelines,
        pricing_config: live_pricing_config,
    })
    .await
{ /* ... */ };

// LG-2 T2：boot 路徑 Demo spawn（不 enforce 但傳 keep API 對齊）
let demo_pricing_config = risk_stores
    .demo
    .load()
    .pricing
    .clone()
    .unwrap_or_default();
let (demo_bindings, demo_slot_cancel) = match demo_slot
    .try_spawn(&pipeline_slot::SpawnConfig {
        kind: pipeline_slot::SlotKind::Demo,
        env: BybitEnvironment::Demo,
        parent_shutdown_token: cancel.clone(),
        cfg_snapshot: &cfg_snapshot_pipelines,
        pricing_config: demo_pricing_config,  // 不 enforce, kind!=Live skip
    })
    .await
{ /* ... */ };
```

---

## 8. LiveAuthWatcher respawn 路徑 (live_auth_watcher.rs)

### 8.1 新 field

```rust
pub struct LiveAuthWatcher {
    // ... existing fields
    risk_live_store: Option<Arc<ConfigStore<RiskConfig>>>,  // LG-2 T2
}
```

`Option` 因 unit test 不需 risk_live_store；prod from_parts 必傳。

### 8.2 三條 ctor 對齊

- `with_params`（test + pre-2026-05-11 callers）：內部 set `risk_live_store: None`
- `with_pipeline_spawner`（過渡期）：內部 set `risk_live_store: None`
- `from_parts`（prod 路徑）：強制 param + main.rs 傳 `Some(Arc::clone(&risk_stores.live))`

### 8.3 run loop respawn 取 pricing

```rust
// LiveAuthWatcher::decide_once → (false, Ok(auth)) branch（auth valid + slot empty）
let cfg_snapshot = self.config.get();
let pricing_config = self
    .risk_live_store
    .as_ref()
    .and_then(|s| s.load().pricing.clone())
    .unwrap_or_default();  // None / no [pricing] section → PricingConfig::default()
let spawn_cfg = SpawnConfig {
    kind: SlotKind::Live,
    env: self.env,
    parent_shutdown_token: self.engine_shutdown.clone(),
    cfg_snapshot: &cfg_snapshot,
    pricing_config,  // ArcSwap 熱重載：每次 respawn 取最新
};
match self.slot_op.try_spawn(&spawn_cfg).await { /* ... */ };
```

---

## 9. Unit tests (11 個)

| Test | Description | Verdict |
|---|---|---|
| 1. test_wait_first_refresh_timeout_when_never_refreshed | last_fee_refresh_ms=0 timeout 500ms → Err(NoRefresh) | PASS |
| 2. test_wait_first_refresh_fast_path_when_already_refreshed | refresh 已完成 → 立即 Ok 不 sleep | PASS |
| 3. test_wait_first_refresh_midwait_completion | spawn task 600ms 後 set，wait 5s → Ok（poll 邏輯） | PASS |
| 4. test_live_demo_accepts_demo_conservative_default_when_in_modes | LiveDemo + DemoConservativeDefault + modes 含 live_demo → Ok | PASS |
| 5. test_live_demo_accepts_cold_default_when_in_modes | LiveDemo + ColdDefault + modes 含 live_demo → Ok（寬鬆） | PASS |
| 6. test_live_demo_rejects_cold_default_when_not_in_modes | LiveDemo + ColdDefault + modes 不含 live_demo → Err(LiveDemoNonApiSourceWhenStrict) | PASS |
| 7. test_mainnet_rejects_cold_default_always | Mainnet + ColdDefault + modes 含 "live" → Err(MainnetNonApiSource) （硬規則無視 modes） | PASS |
| 8. test_mainnet_rejects_demo_conservative_default | Mainnet + DemoConservativeDefault + modes 全 → Err(MainnetNonApiSource { source: DemoConservativeDefault }) | PASS |
| 9. test_rejects_when_fee_rate_count_below_min | 只 seed 5 個 SYMBOLS → Err(InsufficientSymbolCoverage { count: 5 }) | PASS |
| 10. test_reason_code_strings_aligned | 4 種 reason_code 字串完全對齊 healthcheck contract | PASS |
| 11. test_display_format_safe | Display impl 中英對照 + 4 種錯誤格式不爆破 | PASS |

### 為什麼沒有「Mainnet + 全 BybitApi → Ok」test

要讓 fee_source 推斷為 BybitApi 必須 cache 內 rate != DEFAULT_MAKER_FEE/TAKER_FEE，
但 AccountManager 無 `insert_real_rate_for_test` API（只有 seed_default_fee_rates
寫 default）。需 mock Bybit client 真實調用 — 該邏輯已在 LG-2 T1 contract tests
覆蓋（integration tests/lg3_contract.rs）。本 module 重點測 reject path 邏輯，
完整 happy path BybitApi 在 integration suite 驗。

---

## 10. Test 結果

### 10.1 Build
```
$ cargo build --release -p openclaw_engine
   Finished `release` profile [optimized] target(s) in 23.98s
   (warnings: 20 既有；0 new from LG-2 T2)
```

### 10.2 live_spawn_assert tests
```
$ cargo test --lib --release -p openclaw_engine live_spawn_assert
running 11 tests
test live_spawn_assert::tests::test_reason_code_strings_aligned ... ok
test live_spawn_assert::tests::test_display_format_safe ... ok
test live_spawn_assert::tests::test_live_demo_accepts_demo_conservative_default_when_in_modes ... ok
test live_spawn_assert::tests::test_mainnet_rejects_cold_default_always ... ok
test live_spawn_assert::tests::test_live_demo_rejects_cold_default_when_not_in_modes ... ok
test live_spawn_assert::tests::test_mainnet_rejects_demo_conservative_default ... ok
test live_spawn_assert::tests::test_live_demo_accepts_cold_default_when_in_modes ... ok
test live_spawn_assert::tests::test_rejects_when_fee_rate_count_below_min ... ok
test live_spawn_assert::tests::test_wait_first_refresh_fast_path_when_already_refreshed ... ok
test live_spawn_assert::tests::test_wait_first_refresh_timeout_when_never_refreshed ... ok
test live_spawn_assert::tests::test_wait_first_refresh_midwait_completion ... ok

test result: ok. 11 passed; 0 failed; 0 ignored; 0 measured; 2850 filtered out; finished in 0.61s
```

### 10.3 整體 lib regression
```
$ cargo test --lib --release -p openclaw_engine
test result: ok. 2860 passed; 0 failed; 1 ignored; 0 measured; 0 filtered out; finished in 0.69s
```

baseline = LG-2 T3 ship 後 2849 + 11 new LG-2 T2 tests = 2860 完全對齊。
**0 regression**。

### 10.4 Binary tests
```
$ cargo test --release --bin openclaw-engine
test result: ok. 58 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.46s

  Including:
  test live_auth_watcher::tests::watcher_tears_down_when_auth_invalidates ... ok
  test live_auth_watcher::tests::watcher_respects_backoff_on_spawn_failure ... ok
  test live_auth_watcher::tests::watcher_without_spawner_keeps_handle_slot_empty ... ok
```

既有 watcher tests 全綠（我加 risk_live_store=None 對 with_params /
with_pipeline_spawner 路徑無破壞）。

### 10.5 Integration tests
```
$ cargo test --release -p openclaw_engine --tests
... [21 個 test target，全綠]
test stress_bb_reversion_extreme_oversold_bounce ... FAILED
test result: FAILED. 34 passed; 1 failed; 0 ignored; 0 measured; 0 filtered out
```

**stress_bb_reversion_extreme_oversold_bounce** failure 是 **pre-existing
sibling W7-2 P0 Option A-Lite paper_state SSoT refactor 後 fixture 未同步更新**
（owns_self filter + position_state SSoT requires test to set position_state
during exit phase）。Working dir `git status` 顯示 `bb_reversion/mod.rs` /
`bb_reversion/tests.rs` / `ma_crossover/strategy_impl.rs` / `ma_crossover/tests.rs`
都被 sibling W7-2 改過，與 LG-2 T2 完全無 overlap：

```
$ git diff --name-only rust/openclaw_engine/src/strategies/
rust/openclaw_engine/src/strategies/bb_reversion/mod.rs
rust/openclaw_engine/src/strategies/bb_reversion/tests.rs
rust/openclaw_engine/src/strategies/ma_crossover/strategy_impl.rs
rust/openclaw_engine/src/strategies/ma_crossover/tests.rs

$ git log --oneline -3 rust/openclaw_engine/src/strategies/bb_reversion/
6cdfe0dc P0 Option A-Lite E1-B: bb_reversion paper_state SSoT refactor
77a52796 P0 Phase 0 hot-fix: bb_reversion exit branch owner_strategy gate
df0e2269 P1-1 bb_reversion W7-3 1-tick defense propagation
```

bb_reversion `is_pinned` guard 加在 None branch (entry path)，stress test
fixture `is_pinned: true` 已 set，所以**不是 is_pinned 引起**；是
**P0 Option A-Lite paper_state SSoT** 把 `owns_self = ctx.position_state.filter(owner_strategy==name())`
需要 test 在 ctx2 設 position_state — fixture line 481 `make_ctx("ETHUSDT",
2050.0, 700_000, Some(snap2))` 仍 `position_state: None` → owns_self=None
→ 走 entry branch（不是 exit branch）→ pct_b=0.5 不滿足 oversold → 0 intents
（test 期望 1 exit intent）。

**LG-2 T2 完全不觸碰 bb_reversion / stress_integration / strategies/ 任何
檔案**。此 failure 屬 sibling wave 進行中。

---

## 11. Live 5-gate vs T2 pre-check sequence

```
build_exchange_pipeline 內部順序（startup/mod.rs:496-880）：

  L511-538  Gate 1：LIVE-GATE-BINDING-1 — load_and_verify(env) HMAC + sig + expires_at_ms + env_allowed
    ↓
  L540-553  Gate 2/3：BybitRestClient::new(env, None, None)
              - Mainnet 強制 OPENCLAW_ALLOW_MAINNET=1 (LIVE-GUARD-1 SEC-17)
              - 強制 has_credentials() == true（secret slot 有效）
    ↓
  L569-580  Gate 4：DCP 設置（OPENCLAW_DATA_DIR 內 Disconnected Cancel Protection）
    ↓
  L592-657  Gate 5：startup positions 抓取（雖非 hard gate，依賴憑證有效）
    ↓
  L665-715  既有：fee_rate refresh + demo seed_default fallback
    ↓
  L716-780  LG-2 T2 Gate 6（NEW）：wait_for_first_refresh_or_timeout +
                                  assert_pricing_binding_for_live_spawn +
                                  write_audit_log
    ↓
  L781-...  balance fetch (BALANCE-REAL-1 retry + hard-fail)
    ↓
  L783+     private WS supervisor spawn
```

LG-2 T2 不破既有 5 gate；**only insertion 在 fee refresh 與 balance fetch
之間**。fee refresh path 已成功 OR seed_default fallback 後立即跑斷言；refresh
全失敗 → fee_rate_count=0 → wait 30s 仍 0 → reject。

---

## 12. Audit log target 字串契約

```
target: "openclaw_engine::live_spawn_audit"
events:
  - "lg2_t2_pricing_assert_pass"
  - "lg2_t2_pricing_assert_fail"
  - "lg2_t2_wait_first_refresh_timeout"

structured fields:
  - env: BybitEnvironment (Debug ?)
  - engine_mode: &'static str (mode_label)
  - fee_rate_count: usize
  - last_fee_refresh_ms: u64
  - reason_code: &'static str（4 種）
  - error: Display 字串（中英對照）
  - elapsed_secs: u64（wait timeout 專用）
```

systemd journalctl 過濾：
```bash
journalctl -u openclaw-engine --grep "live_spawn_audit"
journalctl -u openclaw-engine --grep "lg2_t2_pricing_assert_fail"
```

下游 healthcheck `[45]` 可 parse 此 log 加 audit chain，但目前 [45] 只看 PG
端 trading.fills + IPC dual-source，**未**parse engine.log；後續 Phase B 可加
log audit consumer。

---

## 13. Self-check 8 acceptance ✓

| # | Acceptance | 結果 |
|---|---|---|
| 1 | `cargo build --release -p openclaw_engine` 綠 | PASS — 0 errors |
| 2 | `cargo test --lib --release -p openclaw_engine startup_assert\|pricing_binding\|fee_refresh` 新 test PASS | PASS — 11/11（live_spawn_assert::tests::*） |
| 3 | `cargo test --lib --release` 整體 no regression (baseline 2849+11=2860) | PASS — 2860/0 |
| 4 | live spawn pre-check 三項 OR timeout 之 fail → 拒 spawn + audit row 寫成功 | PASS — tracing audit log target=`live_spawn_audit` |
| 5 | demo / paper spawn 不 enforce（per PA §2.5 risk #1） | PASS — `if kind == PipelineKind::Live` 守衛 |
| 6 | wait_for_first_refresh_or_timeout 30s 後仍無 first refresh → reject | PASS — NoRefresh + write_wait_timeout_audit |
| 7 | 注釋全中文 | PASS — MODULE_NOTE / docstring / inline 全中文（CLAUDE.md §七 2026-05-05 規） |
| 8 | Cross-ref live_authorization.rs 五 gate 對齊（不破既有） | PASS — §11 順序圖；既有 HMAC + freshness + env_allowed + secret + ALLOW_MAINNET 5 gate 全保留，T2 為第 6 |

---

## 14. 不確定之處 + Operator 下一步

### 不確定之處

1. **audit log 是否需 PG row**：spec 寫「audit write」未指明 storage；本 IMPL
   走 tracing（startup 在 db_pool 前無法寫 PG）。若 operator/A3 review 認為
   需 PG persistent — 後續 P2 新 V09x migration（governance.live_spawn_audit
   或 supervised_live_audit）+ engine 啟動 db_pool 後 retrofit insert（從
   `engine.log` parse + 補寫）。**目前 IMPL 不阻 sign-off**，tracing 足以
   做 audit trail（systemd journalctl 持久化）。

2. **mode_label "live_demo" vs "live_testnet"**：`effective_engine_mode`
   對 `(Live, Testnet)` 回 `"live_testnet"` — 但 testnet 在 CLAUDE.md §四
   不是 Bybit 真實 endpoint（Testnet 已 deprecated，代碼仍保留）。本 IMPL
   `mode_in_acceptable` 對 "live_testnet" 走相同邏輯（modes 含 → accept）；
   未來 testnet 真接通需重新 review 是否 enforce。

3. **stress_bb_reversion_extreme_oversold_bounce fail**：100% 確認 pre-existing
   sibling W7-2 改動 + fixture 未同步更新，與 LG-2 T2 無關。Operator 可選擇
   (a) 等 W7-2 sibling 同 wave fix fixture (b) 暫時 ignore 該 test 直到 W7-2
   sign-off。本 IMPL 不主動修（不擴大 scope，per profile.md）。

### Operator 下一步

1. PM 派 E2 + E4 + A3 review chain 對 LG-1 + LG-2 batch（per PA §6.2 wave 2.2
   收口）。E2 必查：
   - `grep -E '(/home/ncyu|/Users/[^/]+)' rust/openclaw_engine/src/live_spawn_assert.rs` → 0 hits（已驗）
   - 注釋全中文（已驗）
   - audit log target 字串穩定（不被未來 rename 破）
2. E4 regression：跑 release lib 2860/0 + binary 58/0 確認 no regression。
3. A3 review：
   - Live gate 第 6 位 ordering 是否合理（fee refresh 後、balance fetch 前）
   - tracing audit 是否足夠（vs 需 PG row）
   - LiveDemo + ColdDefault 寬鬆解讀是否符合 PA spec intent
4. PM 統一 commit + push（per CLAUDE.md §七 強制鏈）。
5. 後續 24h passive observation（wave 2.3）— healthcheck `[45]` runtime
   pricing_binding drift 檢查持續跑。

---

E1 IMPLEMENTATION DONE: 待 E2 審查
（report path: `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-11--lg2_t2_startup_assertion.md`）
