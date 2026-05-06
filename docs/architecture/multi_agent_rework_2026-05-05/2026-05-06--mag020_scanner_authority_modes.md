# MAG-020 Scanner Authority Modes

Date: 2026-05-06
Status: DONE contract
Owner: PA
Scope: AgentTodo M2 Scanner Advisory Conversion

## 1. Decision

Scanner authority must be expressed as one explicit mode:

- `legacy_gate`
- `advisory_shadow`
- `advisory_enforced`

The current runtime remains `legacy_gate` until MAG-024 wires the Rust hot path
to a real authority-mode config. Do not add a runtime TOML knob before it is
consumed by the tick pipeline; a visible but unused knob would be misleading.

## 2. Current Facts

Current scanner influence points:

| Current path | Current behavior |
|---|---|
| `rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs` | `SymbolRegistry::is_active()` can suppress new opens when a symbol is outside the active scanner universe. |
| `rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs` | `route_mode in {market_gate, exploration_only, risk_policy_gate}` can create a demo/live_demo pre-risk reject. |
| `rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs` | `OpportunityDecision.canary_block_new_entry` can create a demo/live_demo pre-risk reject when `[opportunity].canary_block_new_entries=true`. |
| `rust/openclaw_engine/src/scanner/registry.rs` | open positions are currently deferred from scanner removal, so scanner rotation does not directly close a position. |
| `rust/openclaw_engine/src/scanner/runner.rs` | scanner writes scan snapshots and subscription add/remove changes. |

These facts define the compatibility baseline for `legacy_gate`; they are not
the target Agent Decision Spine behavior.

## 3. Mode Semantics

| Mode | Open admission | Scanner output | Position effect | Intended phase |
|---|---|---|---|---|
| `legacy_gate` | Current behavior is preserved. Scanner active-universe, route-mode, and opportunity canary checks may suppress demo/live_demo new opens before normal risk verdicts. | Existing scan snapshot and intent `details.scanner` fields. | Scanner removal must not directly close positions. Existing open-position removal deferral remains required. | Current default and rollback mode. |
| `advisory_shadow` | Legacy scanner gate result is computed and recorded as `legacy_would_block`, but it must not suppress a new open. H0 hard facts and Guardian/P0/P1 gates still enforce normally. | `OpportunityCandidate` and `OpportunityDecay` are emitted as advisory evidence; legacy would-block reasons are attached for replay comparison. | Decay on an open position creates `PositionReview` input only; no close/reduce dispatch is allowed solely from scanner decay. | Shadow comparison and replay calibration. |
| `advisory_enforced` | Scanner may not directly gate tactical opens. Opens must flow through Agent Decision Spine objects: evidence -> StrategistDecision -> GuardianVerdict -> ExecutionPlan -> Decision Lease. Missing spine persistence fails closed to no new open, not to legacy scanner authority. | `OpportunityCandidate` / `OpportunityDecay` persistence is mandatory before downstream decision use. Legacy fallback is allowed only as recorded advisory evidence or protective H0/Guardian fact. | Open-position decay must produce `PositionReview`; tactical close/reduce requires StrategistDecision + GuardianVerdict. Protective H0/P0/P1 reduce-only paths remain separate and explicit. | Cutover mode after M2/M3 regression and replay proof. |

## 4. Hard Fact Boundary

Scanner-adjacent facts may still be hard eligibility evidence when they are true
H0 or Guardian inputs:

- delisted or suspended instrument;
- missing instrument metadata required for safe sizing;
- impossible order constraints such as below exchange min quantity/notional;
- stale or unusable market data feed;
- abnormal spread or liquidity facts that Guardian treats as non-bypassable risk.

These are not scanner ranking decisions. They must be persisted as hard-fact
evidence with reason codes and must not be hidden inside scanner score sorting.

## 5. Config Contract

Target config shape for MAG-024:

```toml
[authority]
mode = "legacy_gate" # legacy_gate | advisory_shadow | advisory_enforced
```

Required parsing rules:

- missing `[authority]` defaults to `legacy_gate`;
- unknown mode values fail scanner config validation;
- the active mode is persisted in scanner snapshots and new-open intent
  scanner details once MAG-024 wires the hot path;
- `advisory_shadow` and `advisory_enforced` must be rejected by review if
  `OpportunityCandidate` / `OpportunityDecay` serialization is absent;
- `advisory_enforced` must be rejected by review if PositionReview regression
  coverage is absent.

Do not set this field in `settings/risk_control_rules/scanner_config.toml`
until the Rust consumer lands. The current file intentionally has no
`[authority]` section, so current behavior remains `legacy_gate`.

## 6. Object Ownership

| Object | Writer | Reader | Authority |
|---|---|---|---|
| `OpportunityCandidate` | Scanner adapter | Scout, Strategist, replay, OpenClaw status views | Advisory evidence only. |
| `OpportunityDecay` | Scanner adapter | Strategist, Guardian, replay, healthchecks | Advisory evidence; may request review. |
| `PositionReview` | Strategist | Guardian, Executor, OpenClaw status views | Tactical hold/reduce/close/no_action recommendation, not an order. |
| hard H0 scanner-adjacent fact | H0 / Guardian evidence adapter | Guardian / execution gate | Non-bypassable only when classified as H0/P0/P1 fact. |

## 7. Rollout Gates

1. MAG-021 adds Rust/Python serialization contracts for `OpportunityCandidate`
   and `OpportunityDecay`.
2. MAG-022 emits decay events for weakened/displaced/exited symbols.
3. MAG-023 proves active-position market data stays subscribed after scanner
   ranking drops.
4. MAG-024 wires the authority-mode config and records `legacy_would_block` in
   `advisory_shadow`.
5. MAG-025 builds scanner churn replay windows.
6. MAG-026 proves scanner decay creates review input and never dispatches close
   solely from scanner removal.

## 8. Review Verdict

This contract aligns with the 2026-05-06 operator decision:

- scanner becomes evidence, not hidden trade authority;
- Strategist owns tactical open/hold/reduce/close/no_action decisions;
- Guardian remains non-bypassable for risk;
- Rust remains the execution engine, but not an independent hidden decision
  authority;
- `legacy_gate` remains available as a compatibility and rollback mode until
  the advisory spine is proven.
