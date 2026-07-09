# RFC — LG-2 H0 Blocking Verification

Date: 2026-05-01
Owner: PA
Status: Ready for PM/E2/E4 review
Scope: Wave 4 pre-stage RFC for H0 Gate shadow-to-blocking verification before P0-3 live-gate implementation.

## Executive Summary

LG-2 is not a request to enable mainnet or relax any live boundary. It is the verification package that proves H0 hard-blocking behaves correctly before LG-4/LG-5 can build supervised or constrained autonomous live flows on top of it.

Current code fact:

- `rust/openclaw_engine/src/tick_pipeline/on_tick/step_0_5_h0_gate.rs` already routes every tick through H0 before strategy dispatch.
- When `H0CheckResult.allowed=false`, the pipeline logs `H0 BLOCKED`, processes stops only, emits a canary record, and returns before Step 4/5 open-intent dispatch.
- Demo and live risk TOML currently carry `runtime.h0_shadow_mode=false`; paper keeps `true`.

Decision: implement LG-2 as an acceptance and rollback package around existing H0 behavior, plus one E2E mock blocked-intent test. Do not add a new trading path.

## Non-Goals

- No true live/mainnet enablement.
- No Decision Lease issuance.
- No strategy/risk parameter loosening.
- No restart-to-apply requirement for the eventual flip.
- No bypass around Guardian, RiskConfig, or exchange auth gates.

## Required Metrics

The LG-2 acceptance window must report these five metrics for `demo` and `live_demo`; `live/mainnet` remains out of scope until LG-4:

| Metric | PASS Threshold | WARN | FAIL |
|---|---:|---:|---:|
| H0 latency | p99 < 1ms over 24h | p99 1-3ms | p99 > 3ms |
| False-positive block rate | 0 confirmed false blocks over 24h replay | 1 disputed block | >1 confirmed false block |
| Fail-closed proof count | >=3 synthetic blocked cases in tests | missing one case | no E2E proof |
| Open-order leakage | 0 exchange dispatches after H0 block | any ambiguous audit row | any confirmed dispatch |
| Lease consumption | 0 leases consumed by H0-blocked intents | any ambiguous lease row | any confirmed lease |

Notes:

- Lease consumption is expected to be zero because H0 is pre-lease.
- If no natural H0 blocks occur in the observation window, synthetic E2E blocked-intent tests become the hard acceptance evidence.

## Implementation Plan

### T1 — E2E Mock Blocked Intent Test

Add a focused Rust test that forces H0 to reject before Step 4/5:

- construct a `TickPipeline` with an H0 config that makes the current tick stale or category-disallowed;
- run `on_tick_step_0_5_h0_gate`;
- assert `ControlFlow::Break`;
- assert no `TradingMsg::Intent`, no order dispatch request, and no Decision Lease side effect.

Suggested files:

- `rust/openclaw_engine/src/tick_pipeline/tests/h0_blocking.rs`
- optional helper in existing tick pipeline test support.

### T2 — Operator Verification Query

Add or document a read-only query that summarizes H0 blocked records from canary/status data:

- count of H0 checks;
- count of hard blocks;
- count of shadow would-blocks;
- latest block reason by symbol;
- matching order/intents count after the same tick timestamp.

No DB write is needed for this RFC unless E1 finds current canary rows are insufficient.

### T3 — Flip / Rollback SOP

The operator-facing control should use the existing audited RiskConfig path:

```json
{
  "method": "patch_risk_config",
  "params": {
    "engine": "demo",
    "source": "operator",
    "patch": { "runtime": { "h0_shadow_mode": false } }
  }
}
```

Rollback sets `runtime.h0_shadow_mode=true` for the affected engine. If the runtime already has hard-blocking enabled, the SOP still documents the reversible path and verifies hot-reload semantics.

## Acceptance

LG-2 is accepted when all are true:

- T1 E2E mock blocked-intent test passes.
- 24h demo/live_demo observation shows no open-order leakage after H0 blocks.
- H0 latency remains below the threshold.
- Manual rollback command is tested on demo or a test engine and restores shadow behavior without rebuild.
- E2 confirms no live auth, Decision Lease, or exchange credential boundary changed.

## Rollback

Rollback is configuration-only:

1. `patch_risk_config(engine=<mode>, patch={"runtime":{"h0_shadow_mode":true}})`.
2. Verify latest canary/status reports shadow would-block rather than hard-block.
3. Keep existing stop handling active.

No database rollback is needed because the verification should be read-only except test artifacts.

## Root-Principle Check

| Principle | Verdict |
|---|---|
| #1 Single write entry | Preserved; no new order writer. |
| #3 AI output is not command | Preserved; H0 remains pre-AI and pre-lease. |
| #4 Strategy cannot bypass risk | Strengthened by proving H0 stops open dispatch. |
| #5 Survival over profit | Strengthened; H0 failure mode is stops-only. |
| #6 Fail conservative | Preserved through fail-closed H0 block and rollback. |
| #11 Agent autonomy | Not reduced; this verifies hard boundaries, not strategy choice. |

## Open Questions

- Whether current canary/status rows are enough for a clean H0 block audit query or need a small read-only aggregation helper.
- Whether LG-4 wants the same H0 block audit mirrored into SM-04 change/audit logs; this can be deferred to LG-4.

