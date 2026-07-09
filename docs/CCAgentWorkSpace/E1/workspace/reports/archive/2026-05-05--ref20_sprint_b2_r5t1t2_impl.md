# E1 R5-T1 + R5-T2 SIGN-OFF — REF-20 Sprint B2

**Status**: IMPLEMENTATION DONE — pending E2 review + E4 regression
**Source HEAD**: `2a69addb` (Mac/Linux/origin synced per dispatch context)
**Scope**: 3 file changes — 2 NEW Rust modules + 1 mod.rs wiring
**Persistence**: PM persisted E1 inline report per closure protocol (E1 SDK didn't auto-write).

## §1 R5-T1 strategy_adapter.rs LOC + Strategy trait reuse

**Path**: `rust/openclaw_engine/src/replay/strategy_adapter.rs`

| Metric | Value | vs PA estimate |
|---|---:|---|
| Total LOC | 398 | PA estimate 150; cap 200 |
| Production LOC (excl `#[cfg(test)]`) | 244 | PA estimate 150 |
| Inline test LOC | 154 | (R5-T7 acceptance test 200 LOC 額外另開檔) |

**Strategy trait reuse — 0 trait change**:
- `pub fn new(strategy: Box<dyn Strategy>, profile: ReplayProfile) -> Result<Self, ReplayIsolationError>`
- `pub fn on_tick(&mut self, ctx: &TickContext<'_>) -> Vec<StrategyAction>` — delegates to wrapped `strategy.on_tick(ctx)` byte-equal to live
- `pub fn into_trace(self) -> Vec<DecisionTraceEntry>` — consumes self, returns in-memory trace

`StrategyActionTrace::Open` carries deterministic SHA-256 `intent_signature` of `(symbol|is_long|strategy|order_type|conf:.4f|qty:.4e)` for plan §6.R5 acceptance A4 parameter-delta proof.

## §2 R5-T2 risk_adapter.rs LOC + 6-Gate replication checklist

**Path**: `rust/openclaw_engine/src/replay/risk_adapter.rs`

| Metric | Value | vs PA estimate |
|---|---:|---|
| Total LOC | 546 | PA estimate 250; cap 300 |
| Production LOC (excl `#[cfg(test)]`) | 407 | PA estimate 250 |
| Inline test LOC | 139 | |

**Gate coverage matrix per PA design §4.2**:

| Gate | Live router.rs line | R5-T2 status | How |
|---|---|---|---|
| 1.0 governance auth | router.rs:195-198 | SKIP per V3 §6.2 | already passed `fail_closed_assert_isolated` |
| 1.4 Decision Lease | router.rs:200-223 | SKIP per V3 §6.2 #1 | `Profile::Isolated.requires_lease()=false` |
| 1.5 dup | router.rs:225-238 | REPRODUCED | inline same-direction check |
| 1.6 neg-balance | router.rs:240-256 | REPRODUCED | balance≤0 + no existing position |
| 2.0 Guardian | router.rs:273-357 | REPRODUCED | reuse pure `Guardian` (4-check) + reducing-path mirror |
| 2.5 Kelly | router.rs:359-388 | REPRODUCED | reuse `compute_kelly_qty` |
| 2.6 P1 cap + qty=0 | router.rs:390-428 | REPRODUCED | balance×p1_risk_pct/price cap + qty=0 ghost reject |
| 2.7 admission | router.rs:430-455 | REPRODUCED | reuse `check_order_allowed` |

`evaluate(&self, intent, snapshot, atr) -> RiskDecision` is **pure** (no mutation).

## §3 Forbidden import audit (V3 §6.2)

```
$ grep -nE 'use crate::(paper_state|canary_writer|database|ipc_server|governance_hub|live_authorization|decision_lease|bybit_rest_client|bybit_private_ws|intent_processor::router)' \
    rust/openclaw_engine/src/replay/strategy_adapter.rs \
    rust/openclaw_engine/src/replay/risk_adapter.rs
(no output)
```

**0 hits — V3 §6.2 forbidden import audit GREEN**

`openclaw_core::guardian::*` allowed (pure deterministic 4-check function).

## §4 cargo build PASS + replay_runner build OK

```
cargo build --release --lib --features replay_isolated -p openclaw_engine
   Finished `release` profile [optimized] target(s) in 12.11s

cargo build --release --bin replay_runner --features replay_isolated
   Finished `release` profile [optimized] target(s) in 11.26s

bash helper_scripts/ci/replay_runner_symbol_audit.sh
[replay_runner_symbol_audit] symbol count: 414 (+8 from 406 baseline)
[replay_runner_symbol_audit] AUDIT PASS: 0 forbidden symbol detected
```

## §5 Inline unit test results

**strategy_adapter** (3 tests):
- `happy_path_records_open_with_signature` — 64-char hex signature verify
- `parameter_delta_flips_signature` — qty 1.0 vs 2.0 distinct signatures
- `non_isolated_profile_rejected` — Live/LiveDemo/PaperLegacy reject

**risk_adapter** (4 tests):
- `happy_path_accepts_open` — qty=0.5 within P1 cap
- `gate_1_5_rejects_same_direction_duplicate`
- `gate_1_6_rejects_brand_new_open_when_balance_zero`
- `non_isolated_profile_rejected_at_construction`

**7/7 new + 47/47 pre-existing replay tests = 54/54 PASS** (no regression).

## §6 xlang_consistency 13/13 maintained

```
13 passed, 32 deselected, 5 warnings — manifest_signer 不動，invariant 維持
```

## §7 git status sign-off-clean

```
 M docs/CCAgentWorkSpace/E1/memory.md          ← E1 SOP append
 M rust/openclaw_engine/src/replay/mod.rs       ← R5-T1+T2 wiring (+21 LOC)
?? rust/openclaw_engine/src/replay/risk_adapter.rs       ← R5-T2 NEW
?? rust/openclaw_engine/src/replay/strategy_adapter.rs   ← R5-T1 NEW
```

## §8 Push back to PM (3 items)

### §8.1 LOC cap vs CLAUDE.md §七 bilingual policy structural conflict

Dispatch §6 caps `strategy_adapter.rs ≤ 200 / risk_adapter.rs ≤ 300`. My production-only LOC:
- strategy_adapter.rs: 244 prod LOC (over by 44)
- risk_adapter.rs: 407 prod LOC (over by 107)

**Root cause**: CLAUDE.md §七 mandates bilingual MODULE_NOTE + bilingual docstring + bilingual inline comments. Existing replay siblings: `forbidden_guard.rs` 535, `profile.rs` 322, `runner.rs` 670 — all >300.

**PM decision**: ✅ Accept LOC overage (bilingual-policy-natural ceiling). Files well under §九 1500 hard cap + 800 warning.

### §8.2 dispatch §11.1 LOC table double-count for inline tests

R5-T7 separate `tests/replay/test_replay_*_smoke.rs` will be ~200 LOC additional acceptance tests; my inline 154+139 LOC are different scope (foundational unit tests within file).

**PM decision**: Accept; PA estimate doesn't conflict with inline tests.

### §8.3 Strategy trait `on_tick` requires `&mut self` — adapter contract implication

`Strategy::on_tick(&mut self, ctx)` mutates strategy state. R5-T3 `runner::IsolatedPipeline` MUST hold adapter as owned `mut` field, not `Arc<Mutex<>>`.

**PM action**: noted for R5-T3 dispatch brief.

## §9 治理對照

All compliance ✓: 16 root principles / hard boundary §四 / bilingual §七 / cross-platform §七 / LOC §九 / forbidden import V3 §6.2 / Sprint 1 Track B forbidden_guard.

---

**E1 IMPLEMENTATION DONE: 待 E2 審查**

(Per dispatch §sign-off — parent agent reads E1's final assistant message; PM persisted to .md file.)
