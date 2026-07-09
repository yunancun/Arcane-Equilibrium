# E1 R6-T1 + R6-T2 SIGN-OFF — REF-20 Sprint C

**Status**: IMPLEMENTATION DONE — pending E2 review + E4 regression
**Source HEAD**: Mac=Linux=origin sync `d7a85932` (V055 closed + governance commit baseline)
**Scope**: 1 production file modified + 1 test fixture file touched (constructor backward compat)
- R6-T1+T2 main IMPL: `rust/openclaw_engine/src/replay/runner.rs`
- R6-T1+T2 test fixture compat: `rust/openclaw_engine/src/replay/report_writer.rs` (new SimulatedFill fields default in fixture builder)

**R0-T0 拆檔 SKIPPED per PM authority** (dispatch §3): runner.rs 1466 + R6-T1+T2 < 2000 cap (governance change `e5b5227c` 2026-05-05 raised cap from 1500→2000); cohesion-driven R0-T0 is now P3 ticket.

**Persistence**: PM persists this E1 inline report per closure protocol.

---

## §1 R6-T1 fee model IMPL summary

### Helper functions added (~30 LOC; runner.rs:583-624)

| Helper | LOC | 職責 |
|---|---:|---|
| `DEFAULT_TAKER_FEE_RATE = 0.00055` | 2 (incl. doc) | 鏡射 `account_manager::DEFAULT_TAKER_FEE` |
| `DEFAULT_MAKER_FEE_RATE = 0.0002` | 2 | 鏡射 `account_manager::DEFAULT_MAKER_FEE` |
| `replay_fee_rate_for_tif(am, symbol, tif) -> (f64, &'static str)` | 18 | 鏡射 `IntentProcessor::fee_rate_for_tif` (intent_processor/mod.rs:1200)。PostOnly→maker / 非PostOnly→taker。`am=Some` 走 `am.maker_fee/taker_fee`；`am=None` 走 `DEFAULT_*_FEE_RATE`。 |

### IsolatedPipeline 新欄位（runner.rs:496-507）

| Field | Type | Default |
|---|---|---|
| `account_manager` | `Option<Arc<crate::account_manager::AccountManager>>` | `None` (cold-boot 路徑：DEFAULT_*_FEE_RATE fallback) |

### `with_replay_fee_context(am, slippage_cfg, vol_24h)` builder (runner.rs:683-697)

opt-in builder mirror `with_adapter_pipeline`，0 break R5-T4 callers (`bin/replay_runner.rs` + 6 hermetic Sprint B test)。

### SimulatedFill 4 column 寫入

| Column | R6-T1 path | R6-T2 path | 說明 |
|---|---|---|---|
| `fee` (f64) | qty × fill_price × fee_rate | (depends on fill_price from R6-T2) | qty=0 ghost row → 0 |
| `fee_rate` (f64) | DEFAULT_*_FEE_RATE or AM.maker_fee/taker_fee | n/a | PostOnly→maker / else→taker |
| `liquidity_role` (String) | "maker" / "taker" / "unknown" | n/a | V050 CHECK enum |
| `slippage_bps` (f64) | n/a | signed bps via lookup_slippage | PostOnly→0; buy→+bps; sell→-bps |

### 4 SimulatedFill push site 改動

| Site | Line | Path | fee | fee_rate | slippage_bps | liquidity_role |
|---|---:|---|---|---|---|---|
| 1. Synthetic walker open | ~700 | `execute_synthetic_walker` | 0.0 | 0.0 | 0.0 | "unknown" |
| 2. Adapter Open Accept | ~838 | `process_open_intent` | qty × fill_price × fee_rate | from TIF | from TIF + vol_24h | from TIF |
| 3. Adapter Open Reject ghost | ~855 | `process_open_intent` | 0.0 (qty=0) | from TIF (counterfactual) | from TIF (counterfactual) | from TIF (counterfactual) |
| 4. Adapter Close | ~895 | `process_close_intent` | pos.qty × fill_price × taker_rate | DEFAULT_TAKER_FEE_RATE (no TIF) | turnover-tier signed by closing leg | "taker" |

**Synthetic walker 設計理由**：synthetic_replay tier non-actionable + walker 無 OrderIntent context → claim maker/taker false positive；fee=0 / slippage_bps=0 確保 proof_1/4/5 e2e `price` 欄位 byte-equal。

**Ghost row 設計理由**：被拒 intent qty=0 → fee=0；但保 fee_rate / liquidity_role / slippage_bps 反映 intent TIF + 方向（counterfactual：「如未拒 caller 應付」），供下游 attribution writer 反事實分析。

**Close 設計理由**：`StrategyAction::Close { symbol, confidence, reason }` 不帶 OrderIntent / TIF → 走 taker path（live engine 預設 close 走市價）。closing leg 方向與 open 相反（long pos→sell→-bps / short pos→buy→+bps）。

---

## §2 R6-T2 slippage model IMPL summary

### Helper functions added (~22 LOC; runner.rs:626-657)

| Helper | LOC | 職責 |
|---|---:|---|
| `replay_slippage_bps_for_tif(slippage_cfg, tif, vol_24h, is_long) -> f64` | 12 | 鏡射 `IntentProcessor::slippage_rate_for_tif` (intent_processor/mod.rs:1179)。PostOnly→0；非PostOnly→`SlippageConfig::lookup_rate(vol_24h)` × 10000。Sign：is_long=true → +bps；is_long=false → -bps。 |
| `apply_slippage_to_price(reference_price, slippage_bps) -> f64` | 4 | fill_price = reference_price × (1 + slippage_bps / 10_000.0)。slippage_bps=0 (PostOnly) → fill_price == reference_price (byte-equal Sprint A/B baseline)。 |

### IsolatedPipeline 新欄位（runner.rs:498-507）

| Field | Type | Default |
|---|---|---|
| `slippage_config` | `crate::config::SlippageConfig` | `SlippageConfig::default()` (= pre-G7-07 SLIPPAGE_TIERS) |
| `volume_24h` | `Option<f64>` | `None` → graceful 0.0 → 5 bps default_rate fallback |

### Slippage tier table (reused live `SlippageConfig::default_slippage_tiers`)

| min_turnover_usd | rate | bps |
|---:|---:|---:|
| ≥$1B | 0.0001 | 1 bps |
| ≥$100M | 0.0002 | 2 bps |
| ≥$10M | 0.0005 | 5 bps |
| ≥$1M | 0.0015 | 15 bps |
| <$1M | 0.0030 | 30 bps |
| `volume_24h <= 0` fallback | 0.0005 | 5 bps |

---

## §3 SimulatedFill 4 column 寫入 mapping

| Column | Rust serde key | V050 schema | Python writer (R6-T5 separate task) |
|---|---|---|---|
| `fee` | `fee` (f64) | `fee NUMERIC` | will read from Rust JSON (R6-T5 scope) |
| `fee_rate` | `fee_rate` (f64) | `fee_rate NUMERIC` | will read from Rust JSON (R6-T5 scope) |
| `slippage_bps` | `slippage_bps` (f64) | `slippage_bps NUMERIC` (V050 既有) | will read from Rust JSON (R6-T5 scope) |
| `liquidity_role` | `liquidity_role` (String) | `liquidity_role TEXT CHECK ∈ {'maker','taker','unknown'}` (V050 既有) | will read from Rust JSON (R6-T5 scope) |

**R6-T1+T2 不寫 ci_low_bps / ci_mid_bps / ci_high_bps / execution_model_version**：留給 R6-T4 CalibrationLabelProducer（單獨 task）。Sprint A 既有預設值維持（NULL / 'synthetic_v1'）。

**SimulatedFill struct 完整 schema** (runner.rs:218-235):

```rust
#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct SimulatedFill {
    pub ts_ms: i64,
    pub symbol: String,
    pub side: String,
    pub qty: f64,
    pub price: f64,
    pub evidence_source_tier: String,
    /// Sprint C R6-T1
    pub fee: f64,
    pub fee_rate: f64,
    /// Sprint C R6-T2
    pub slippage_bps: f64,
    /// Sprint C R6-T1
    pub liquidity_role: String,
}
```

---

## §4 Mac cargo build + test 結果

### Build

```bash
cd /Users/ncyu/Projects/TradeBot/srv/rust
cargo build --release --bin replay_runner --features replay_isolated
# Finished `release` profile [optimized] target(s) in 13.04s — PASS
```

### Replay lib unit tests (focus subset, dispatch §5)

```bash
cargo test --release --features replay_isolated -p openclaw_engine --lib replay::
# test result: ok. 67 passed; 0 failed
```

**新 R6-T1+T2 unit test 9/9 PASS**（dispatch §5 6 mandatory + 3 cross-check）：

| Test | Path | 狀態 |
|---|---|---|
| `test_apply_fill_postonly_uses_maker_fee` | runner.rs:1788 | ✅ PASS |
| `test_apply_fill_non_postonly_uses_taker_fee` | runner.rs:1796 | ✅ PASS |
| `test_apply_fill_long_slippage_increases_fill_price` | runner.rs:1810 | ✅ PASS |
| `test_apply_fill_short_slippage_decreases_fill_price` | runner.rs:1822 | ✅ PASS |
| `test_apply_fill_zero_volume_24h_graceful_fallback` | runner.rs:1834 | ✅ PASS |
| `test_apply_fill_simulated_fill_fee_field_populated` | runner.rs:1853 | ✅ PASS |
| **Cross-check 1** `test_apply_fill_postonly_path_emits_maker_zero_slippage` | runner.rs:1881 | ✅ PASS |
| **Cross-check 2** `test_apply_fill_synthetic_walker_emits_unknown_role_zero_fee` | runner.rs:1909 | ✅ PASS |
| **Cross-check 3** `test_apply_fill_ghost_row_records_zero_fee_with_intent_metadata` | runner.rs:1929 | ✅ PASS |

### Replay e2e regression（無破）

```bash
cargo test --release --features replay_isolated -p openclaw_engine \
  --test replay_runner_e2e \
  --test replay_runner_e2e_param_delta \
  --test replay_manifest_signer_xlang_consistency \
  --test replay_forbidden_guard_acceptance \
  --test replay_profile_acceptance \
  --test replay_mac_policy_acceptance
```

| Test bin | Test count | 結果 |
|---|---:|---|
| replay_runner_e2e | 6 | 6/6 ✅ (proof_1/2/3/4/5 + helper round_trip) |
| replay_runner_e2e_param_delta | 2 | 2/2 ✅ (proof_7 strategy + proof_8 risk) |
| replay_manifest_signer_xlang_consistency | 8 | 8/8 ✅ (xlang_signature byte-equal 維持) |
| replay_forbidden_guard_acceptance | 4 | 4/4 ✅ |
| replay_profile_acceptance | 5 | 5/5 ✅ |
| replay_mac_policy_acceptance | 4 | 4/4 ✅ |

**Replay 全測試套件 96/96 GREEN**（67 lib + 29 e2e）。

### Full lib regression（無破）

```bash
cargo test --release --features replay_isolated -p openclaw_engine --lib
# test result: ok. 2487 passed; 0 failed
```

**全 lib 2487/2487 GREEN**。

---

## §5 LOC compliance

| File | Pre-R6 | Post-R6 | Delta | 限制 |
|---|---:|---:|---:|---|
| `rust/openclaw_engine/src/replay/runner.rs` | 1466 | **1992** | +526 | < 2000 cap (governance change `e5b5227c`) ✅ |
| `rust/openclaw_engine/src/replay/report_writer.rs` | (touched test fixture) | (touched test fixture) | +6 | <800 warning ✅ |

**LOC 構成 (+526 LOC)**：
- 4 SimulatedFill 新欄位 + 雙語 docstring：~25 LOC
- 3 helper fn (replay_fee_rate_for_tif / replay_slippage_bps_for_tif / apply_slippage_to_price) + 2 const + helper section 雙語 doc：~95 LOC
- 3 IsolatedPipeline 新欄位 + 雙語 doc：~15 LOC
- `with_replay_fee_context` builder + 雙語 doc：~30 LOC
- `build_isolated_pipeline` 新欄位 init + 雙語 註解：~10 LOC
- 4 SimulatedFill push site 改動 + 雙語 註解：~115 LOC
- 9 unit test (含 TifStub + r6_single_event helper)：~226 LOC
- apply_fill_open / apply_fill_close docstring 補 fee 邏輯說明：~10 LOC

**Trim 過程**（2300 → 1992，trim 308 LOC）：
- helper section 模組頭收斂（多行 bilingual paragraph → 8-line summary）
- 3 helper fn docstring 從 list-form 收成 paragraph
- 9 test 多行 `assert!(...)` 改單行
- 4 push site 雙語註解多行 paragraph 收成 2-3 line summary
- 抽 `r6_single_event()` fixture 函數消除 3 處 7-LOC 重複構造

---

## §6 Forbidden import audit

```bash
grep -E "^use |^[[:space:]]+use " rust/openclaw_engine/src/replay/runner.rs | \
  grep -E "paper_state|canary_writer|ipc_server|governance_hub|live_authorization|decision_lease"
# 0 hits
```

**0 forbidden import** in changed code. All references to `paper_state` / `canary_writer` / etc. are within `///` docstring / `//` comment lines explaining why these forbidden surfaces are NOT used (V3 §6.2 forbidden surface contract preserved).

**Allowed dependencies (replay-pure)**:
- `crate::account_manager::AccountManager` (read-only fee rates; not actionable)
- `crate::config::SlippageConfig` (config snapshot; immutable)
- `crate::order_manager::TimeInForce` (enum only; structural type)
- `crate::intent_processor::OrderIntent` (struct only; no IntentProcessor logic)
- `crate::strategies::StrategyAction` (replay-pure)

---

## §7 跨平台 grep audit

```bash
grep -nE "(/home/ncyu|/Users/[a-z]+)" rust/openclaw_engine/src/replay/runner.rs \
                                       rust/openclaw_engine/src/replay/report_writer.rs
# 0 hits
```

**0 hardcoded paths** in changed files. All path references go via `OPENCLAW_BASE_DIR` / `OPENCLAW_DATA_DIR` (Sprint B inherited path discipline). Mac aarch64 + Linux x86_64 same Rust toolchain.

---

## §8 Git status

```bash
git status --short
 M docs/CCAgentWorkSpace/E1/memory.md            # E1 memory append (mine)
 M memory/MEMORY.md                              # not mine; sibling session
 M helper_scripts/db/passive_wait_healthcheck/__init__.py     # not mine; R6-T7 sibling sub-agent
 M helper_scripts/db/passive_wait_healthcheck/runner.py       # not mine; R6-T7 sibling sub-agent
 M rust/openclaw_engine/src/replay/runner.rs     # R6-T1+T2 main IMPL (mine)
 M rust/openclaw_engine/src/replay/report_writer.rs  # R6-T1+T2 fixture compat (mine)
?? docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-05--ref20_sprint_c_r6t7_impl.md  # not mine; R6-T7 sibling
?? helper_scripts/db/passive_wait_healthcheck/checks_pricing_binding.py  # not mine; R6-T7 sibling
?? helper_scripts/db/test_pricing_binding_healthcheck.py     # not mine; R6-T7 sibling
?? memory/feedback_v_migration_pg_dry_run.md    # not mine; V055 prior session
```

**My changes (R6-T1+T2 scope)**:
- `rust/openclaw_engine/src/replay/runner.rs` (main IMPL)
- `rust/openclaw_engine/src/replay/report_writer.rs` (test fixture backward compat — SimulatedFill new fields)
- `docs/CCAgentWorkSpace/E1/memory.md` (memory append)
- this report file: `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-05--ref20_sprint_c_r6t1t2_impl.md`

**Other entries are sibling sessions** (R6-T7 LG-3 healthcheck parallel sub-agent + V055 prior session memory drift). Not in my scope per dispatch §8 boundary.

**E1 不直接 commit** per CLAUDE.md §七 強制鏈 E1→E2→E4→QA→PM。等 E2 review + E4 regression PASS → PM 統一 commit + push。

---

## §9 Acceptance contract 對照（PA report §5）

### A6 (Fee-aware PnL) — partial coverage by R6-T1+T2

| # | Acceptance | R6-T1+T2 contribution | 狀態 |
|---|---|---|---|
| A6-1 | Fee never omitted | Adapter path Accept fill: `fee = qty × fill_price × fee_rate > 0` | ✅ partial (calibrated_replay tier flow Rust side; SQL acceptance pending Python R6-T5 + DB end-to-end smoke R6-T8) |
| A6-3 | Maker/taker mapped from PostOnly TIF | `replay_fee_rate_for_tif` returns `(rate, "maker")` for PostOnly / `(rate, "taker")` else | ✅ unit test `test_apply_fill_postonly_uses_maker_fee` + `test_apply_fill_non_postonly_uses_taker_fee` |
| A6-4 | execution_model_version ≠ 'synthetic_v1' | Out of scope (R6-T4 CalibrationLabelProducer task) | ⏳ deferred to R6-T4 |
| A6-5 | ci_low ≤ ci_mid ≤ ci_high | Out of scope (R6-T4) | ⏳ deferred to R6-T4 |

### A7 (Confidence Honesty) — out of scope for R6-T1+T2

R6-T1+T2 is the fee/slippage runtime contract. R6-T4 CalibrationLabelProducer derives `execution_confidence` ∈ {none, limited, calibrated} per QC math spec. R6-T1+T2 lays the foundation by populating the 4 V050 columns required as INPUT to R6-T4's confidence computation.

---

## §10 待 E2 review

**E2 重點審查 3 點**（per PA report §7.4 Sprint C1 R6 E2 必查）：

1. **`runner.rs` apply_fill fee/slippage 計算與 live `IntentProcessor::fee_rate_for_tif` + `slippage_rate_for_tif` byte-equal**
   - `replay_fee_rate_for_tif` (runner.rs:564) ↔ `IntentProcessor::fee_rate_for_tif` (intent_processor/mod.rs:1166-1213): both pick maker for PostOnly / taker else; both use `account_manager.maker_fee/taker_fee` if Some, fallback to DEFAULT_*_FEE_RATE constants. **Constants byte-equal** (live: `0.00055` / `0.0002` in account_manager.rs:136-138; replay: same in runner.rs:603-605).
   - `replay_slippage_bps_for_tif` (runner.rs:583) ↔ `IntentProcessor::slippage_rate_for_tif` (intent_processor/mod.rs:1175-1189): both PostOnly → 0; both `SlippageConfig::lookup_rate(volume_24h)` for non-PostOnly. **Direction sign convention**: replay adds explicit signed bps (buy +, sell -); live caller uses unsigned rate + applies direction at downstream cost gate. R6 dispatch §2 specifies signed bps for `SimulatedFill.slippage_bps`, intentional divergence (live writes unsigned to `cost_gate_paper`; replay writes signed to `simulated_fills.slippage_bps`).

2. **CalibrationLabelProducer 不偷推 'calibrated'** — Out of scope for R6-T1+T2 (R6-T4 separate task)

3. **Sprint A QA round 6 lessons retained**:
   - **No new spawn / subprocess**: R6-T1+T2 is pure Rust struct + function — 0 fork() / 0 child process / 0 stderr DEVNULL.
   - **Fail-closed assertions**: `with_replay_fee_context` is opt-in (default = `None` AccountManager + `SlippageConfig::default()`); never silently uses uninitialized fee data — fallback to DEFAULT_*_FEE_RATE constants is explicit and tested (`test_apply_fill_postonly_uses_maker_fee` exercises `am=None` path).
   - **Placeholder string grep**: 0 placeholder strings in IMPL (all values are explicit consts or computed).

**Additional E2 review points**:

4. **Sprint B2 R5-T3 byte-equal contract preserved**: synthetic walker (line ~700) emits `fee=0 / slippage_bps=0` ⇒ proof_1/4/5 e2e `price` field byte-equal. Verified: `replay_runner_e2e` 6/6 PASS unchanged.

5. **R5-T4 CLI caller backward compat**: `bin/replay_runner.rs` does NOT call `with_replay_fee_context` (R6-T3 will wire that in next wave). Default `account_manager=None` + `slippage_config=default()` + `volume_24h=None` produces same fee=0 / slippage_bps=0 walker behaviour as Sprint B for proof_1/4/5 paths; adapter path picks up R6 fee/slippage via `with_replay_fee_context` — but R5-T4 CLI does not yet wire it, so for now adapter path with `with_replay_fee_context(None, None, None)` produces 5 bps fallback slippage (default_rate). When R5-T4 CLI calls `with_replay_fee_context(am, slippage_cfg, vol_24h)` (R6-T3 task), real fee/slippage flows.

6. **Ghost row counterfactual transparency**: `process_open_intent` Rejected path now records `fee=0` (qty=0) but `fee_rate / liquidity_role / slippage_bps` reflect the intent's TIF + direction (counterfactual). Downstream attribution writer can use this for "if-not-rejected" analysis. Test: `test_apply_fill_ghost_row_records_zero_fee_with_intent_metadata`.

---

## §11 Open questions for E2

1. **Should `process_open_intent` Reject ghost row carry slippage_bps reflecting counterfactual direction (current IMPL) or 0 (no fill, no slippage)?**
   - Current: counterfactual (e.g. buy ghost → +5 bps default). Argument: downstream attribution writer needs the cost it would have paid; 0 erases that signal.
   - Alternative: 0 (matches "no fill happened"). Argument: ghost = no event = no slippage observed.
   - PA dispatch §3 implies counterfactual (4 columns populated even in ghost row). I went with counterfactual.

2. **Should `process_close_intent` always be 'taker'?**
   - Current: yes (Close has no TIF; live engine routes Close as market by default per `strategies/mod.rs:51`). 
   - Future: a hypothetical `StrategyAction::CloseLimit` (PostOnly close) could exist — but not yet. Sprint D / E might add maker close path.

3. **Should `IsolatedPipeline.account_manager` plumb a thread-safe handle for future R5-T4 CLI to seed?**
   - Current: `Option<Arc<AccountManager>>` (read-only `.maker_fee/.taker_fee`; internal RwLock).
   - R5-T4 CLI (R6-T3 task) will likely create a fresh `Arc::new(AccountManager::new())` + `seed_default_fee_rates(symbols)` and pass via `with_replay_fee_context(Some(am), ..., ...)`.

---

## §12 Hard boundary check (CLAUDE.md §四)

- ❌ 未觸 `live_execution_allowed` (R6-T1+T2 不接 IPC / order dispatch)
- ❌ 未觸 `max_retries=0` (不變)
- ❌ 未觸 `OPENCLAW_ALLOW_MAINNET` (replay binary 不接 mainnet)
- ❌ 未觸 `live_reserved` (不接 live mode)
- ❌ 未觸 `authorization.json` (不接 live_authorization)
- ❌ 未觸 `decision_lease` (ReplayProfile::Isolated.requires_lease=false 強制)
- ❌ 未觸 manifest_signer canonical_bytes (fee/slippage 是 simulated_fills row level, 不是 manifest jsonb)
- ❌ 未動 V### migration (V050 既有 4 column 全 ready)
- ❌ 未動 V055 / V036 / V051 / V050 / V049 (out of scope per dispatch §8)
- ❌ 未動 IntentProcessor / GovernanceCore / paper_state mutable state
- ❌ 未動 R6-T7 healthcheck (sibling sub-agent scope)
- ❌ 未破 Sprint A R3 8 commit chain blockers
- ✅ 0 violation

---

## §13 PM Decision Lease check (CLAUDE.md §五 註 + §四)

R6-T1+T2 is **replay-pure** (ReplayProfile::Isolated → `requires_lease=false`). No `acquire_lease` call needed. Per AMD-2026-05-02-01 Path A, the `OPENCLAW_LEASE_ROUTER_GATE_ENABLED` flag (default OFF) is irrelevant here since replay binary never reaches `intent_processor::router` (forbidden surface). Verified: 0 use of `crate::decision_lease` in changed code.

---

## §14 Forward path

E2 review focus → E4 regression (full Mac + Linux test sweep) → PM commit + push (single commit landing R6-T1+T2 + R6-T7 sibling sub-agent's healthcheck) → R6 W1 partial closed → R6 W2 dispatch (R6-T3 Rust replay_runner KellyConfig wire — depends on this R6-T1+T2 deliverable for fee_rate availability).

---

**END OF REPORT**

E1 IMPLEMENTATION DONE: report path: /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-05--ref20_sprint_c_r6t1t2_impl.md
