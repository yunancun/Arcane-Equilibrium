# 2026-05-17 Strategy / Risk / Math Audit

Role: QC(default)  
Repo root: `/Users/ncyu/Projects/TradeBot/srv`  
Audit mode: read-only, except this report file. No config, runtime, trading, migration, TODO, memory, or source edits were made.

Required startup/context read:
- `AGENTS.md`, `CLAUDE.md`, `TODO.md`, `.codex/MEMORY.md`
- `.codex/agents/INDEX.md`, `.codex/AGENT_DISPATCH_PROTOCOL.md`, `.codex/SUBAGENT_EXECUTION_RULES.md`
- `.codex/agents/QC.md`, `.claude/agents/QC.md`, QC profile/memory
- PM baseline: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-17--cold_audit_baseline_freeze.md`
- R4 report: `docs/CCAgentWorkSpace/R4/workspace/reports/2026-05-17--index_integrity_audit.md`
- TW report: `docs/CCAgentWorkSpace/TW/workspace/reports/2026-05-17--doc_inventory_dedup_audit.md`

## Executive Summary

P0 findings: 0.

P1 findings: 3.

No P0 was found. P1 blockers remain for production promotion/live-risk confidence:
1. Live/demo cost gate can accept positive legacy/stale/unvalidated edge snapshots because `runtime_bps`, validation, and snapshot freshness are not fail-closed inputs.
2. Exchange-side stop sync sends raw stop prices to `/v5/position/trading-stop`, unlike order create TP/SL paths that round to instrument tick size.
3. Mutating order-create retry policy still retries ambiguous exchange-send outcomes, relying on idempotency as a policy assumption instead of an explicitly ratified fail-closed/reconcile boundary.

## Findings

### QC-SRMA-001 — Live cost gate accepts legacy/stale/unvalidated edge snapshots

Classification: FACT + INFERENCE  
Severity: P1

Affected path+line:
- `rust/openclaw_engine/src/edge_estimates.rs:80` parses `_meta.grand_mean_bps` but does not parse/use `_meta.updated_at`.
- `rust/openclaw_engine/src/edge_estimates.rs:91` and `rust/openclaw_engine/src/edge_estimates.rs:162` accept `runtime_bps` or fall back to legacy `shrunk_bps`.
- `rust/openclaw_engine/src/edge_estimates.rs:104` and `rust/openclaw_engine/src/edge_estimates.rs:175` parse `validation_passed`, but downstream live gating does not use it.
- `rust/openclaw_engine/src/edge_estimates.rs:232` maps demo/live to shared `edge_estimates.json`.
- `rust/openclaw_engine/src/intent_processor/gates.rs:240` accepts any positive `cell.shrunk_bps` into the live cost gate path.
- `rust/openclaw_engine/src/intent_processor/gates.rs:245` through `rust/openclaw_engine/src/intent_processor/gates.rs:260` compare only edge-vs-cost threshold, without validation/freshness checks.
- `rust/openclaw_engine/src/event_consumer/handlers/edge_estimates.rs:103` through `rust/openclaw_engine/src/event_consumer/handlers/edge_estimates.rs:114` retain prior populated estimates on empty/corrupt/missing reload.
- `settings/edge_estimates.json:3` shows current snapshot timestamp `2026-04-20T23:50:17.941867+00:00`.
- `settings/edge_estimates.json:8` through `settings/edge_estimates.json:10` show current production cell has only legacy `shrunk_bps`, no `runtime_bps`, and only `n=3`.

Evidence command/inspection method:
- `nl -ba rust/openclaw_engine/src/edge_estimates.rs | sed -n '60,190p'`
- `nl -ba rust/openclaw_engine/src/edge_estimates.rs | sed -n '190,270p'`
- `nl -ba rust/openclaw_engine/src/intent_processor/gates.rs | sed -n '220,285p'`
- `nl -ba rust/openclaw_engine/src/event_consumer/handlers/edge_estimates.rs | sed -n '1,130p'`
- `nl -ba settings/edge_estimates.json | sed -n '1,80p'`

Impact:
Live/demo cost gating can treat a positive legacy `shrunk_bps` value as production edge even when `runtime_bps` is absent, validation did not pass, or the snapshot is stale. The current checked-in snapshot is negative, so it blocks rather than passes today; the bypass condition is still real for any stale or legacy positive snapshot. Because this gate is the strategy alpha evidence gate, it can allow trading on evidence that is not fresh, not runtime-qualified, and not promotion-validated.

Why real, not false positive:
The parser explicitly stores `validation_passed`, but `cost_gate_live_with_slippage` never checks it. The loader explicitly falls back from `runtime_bps` to `shrunk_bps`. The reload handler explicitly keeps the prior snapshot on missing/corrupt reload. There is no TTL check against `_meta.updated_at`. These are direct control-flow facts, not documentation interpretation.

Suggested fix direction:
For demo/live promotion and cost gating, require fresh `_meta.updated_at` within a configured TTL, require `runtime_bps`, and require `validation_passed=true` before positive edge can pass. Treat positive legacy `shrunk_bps` without `runtime_bps` as reject/defer in demo/live. Keep paper exploration isolated, but do not allow paper/legacy schema values to become production edge.

Fix owner role: E1 + MIT  
Verification owner role: QC + E4

### QC-SRMA-002 — Exchange-side trading-stop rail bypasses instrument tick rounding

Classification: FACT  
Severity: P1

Affected path+line:
- `rust/openclaw_engine/src/position_manager.rs:226` starts `/v5/position/trading-stop` request construction.
- `rust/openclaw_engine/src/position_manager.rs:232` through `rust/openclaw_engine/src/position_manager.rs:248` stringify raw TP/SL/trailing/active prices with `format!("{}", value)`.
- `rust/openclaw_engine/src/notification_failsafe/providers/exchange_stop_sync.rs:76` through `rust/openclaw_engine/src/notification_failsafe/providers/exchange_stop_sync.rs:92` forward `adjustment.new_sl` directly into `TradingStopRequest`.
- `rust/openclaw_engine/src/event_consumer/bootstrap.rs:757` through `rust/openclaw_engine/src/event_consumer/bootstrap.rs:768` forward `req.stop_loss` directly to `set_trading_stop`.
- `rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs:1302` through `rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs:1310` compute `sl_price` arithmetically and enqueue it without tick rounding.
- Contrast: `rust/openclaw_engine/src/order_manager.rs:354` through `rust/openclaw_engine/src/order_manager.rs:423` pre-validates and formats order-create prices.
- Contrast: `rust/openclaw_engine/src/order_manager.rs:661` through `rust/openclaw_engine/src/order_manager.rs:742` uses instrument specs for qty/price rounding and validation.

Evidence command/inspection method:
- `nl -ba rust/openclaw_engine/src/position_manager.rs | sed -n '210,275p'`
- `nl -ba rust/openclaw_engine/src/notification_failsafe/providers/exchange_stop_sync.rs | sed -n '60,120p'`
- `nl -ba rust/openclaw_engine/src/event_consumer/bootstrap.rs | sed -n '745,775p'`
- `nl -ba rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs | sed -n '1288,1315p'`
- `nl -ba rust/openclaw_engine/src/order_manager.rs | sed -n '330,430p;650,745p'`

Impact:
The dual-rail stop path can send a stop price that violates Bybit tick-size precision. If Bybit rejects the conditional stop, exchange-side protection is absent and only local stop handling remains. This weakens the fail-closed risk-control design exactly where protection should be most deterministic.

Why real, not false positive:
The order-create path already proves the repo has an instrument-spec rounding boundary for exchange-mutating prices. The trading-stop path does not call it and uses raw string formatting. The affected values are externally submitted to `/v5/position/trading-stop`, not internal-only marks.

Suggested fix direction:
Route trading-stop TP/SL/trailing/active prices through the same instrument precision/cache validation used by `OrderManager`, or introduce an equivalent shared exchange-price formatter for trading-stop requests. Fail closed if the symbol spec cannot be loaded.

Fix owner role: E1 + PA  
Verification owner role: BB + E4 + QC

### QC-SRMA-003 — Mutating order-create retries remain a fail-closed policy risk

Classification: FACT + INFERENCE  
Severity: P1

Affected path+line:
- `rust/openclaw_engine/src/event_consumer/dispatch.rs:28` through `rust/openclaw_engine/src/event_consumer/dispatch.rs:34` define open-intent retry delays with 4 total attempts.
- `rust/openclaw_engine/src/event_consumer/dispatch.rs:36` through `rust/openclaw_engine/src/event_consumer/dispatch.rs:51` define close retry and timeout behavior.
- `rust/openclaw_engine/src/event_consumer/dispatch.rs:201` through `rust/openclaw_engine/src/event_consumer/dispatch.rs:220` classify transport/parse errors as transient.
- `rust/openclaw_engine/src/event_consumer/dispatch.rs:352` through `rust/openclaw_engine/src/event_consumer/dispatch.rs:423` retry transient outcomes after `place_fn(attempt).await`.
- `rust/openclaw_engine/src/event_consumer/dispatch.rs:638` through `rust/openclaw_engine/src/event_consumer/dispatch.rs:668` applies the retry loop around `order_mgr.place_order(...)`.

Evidence command/inspection method:
- `nl -ba rust/openclaw_engine/src/event_consumer/dispatch.rs | sed -n '20,65p;190,245p;300,425p;620,680p'`

Impact:
For exchange-mutating order-create calls, transport/parse/timeout errors after the request may represent an unknown exchange-side state. Retrying open creates or close creates can be safe only if the exchange and client idempotency contract is complete and verified for every ambiguous failure mode. Otherwise the policy can amplify duplicate/unknown exposure, which conflicts with fail-closed risk-control expectations.

Why real, not false positive:
The code intentionally classifies `Transport` and `JsonParse` as transient and retries. Comments assert `order_link_id` idempotency is sufficient, but the runtime code still performs exchange-mutating retries after ambiguous send outcomes. This is a policy/math-of-state issue even if Bybit usually deduplicates correctly.

Suggested fix direction:
Ratify the retry policy in PA with exact Bybit idempotency guarantees and reconciliation behavior, or change ambiguous post-send failures to a reconcile-before-retry path. For close paths, ensure timeout does not retry without first determining whether the prior request reached the exchange.

Fix owner role: PA + CC + E1  
Verification owner role: BB + E2 + E4

### QC-SRMA-004 — Guardian scoring constants are not externally tunable

Classification: FACT  
Severity: P2

Affected path+line:
- `rust/openclaw_core/src/guardian.rs:26` through `rust/openclaw_core/src/guardian.rs:32` list tunable `GuardianConfig` fields but omit risk-score weights and reject thresholds.
- `rust/openclaw_core/src/guardian.rs:121` through `rust/openclaw_core/src/guardian.rs:124` hard-code direction-conflict weight `0.4`.
- `rust/openclaw_core/src/guardian.rs:132` through `rust/openclaw_core/src/guardian.rs:138` hard-code position-count weight `0.3`.
- `rust/openclaw_core/src/guardian.rs:141` through `rust/openclaw_core/src/guardian.rs:157` hard-code `2.0` excessive-leverage ratio, `0.4` reject weight, and `0.15` modify weight.
- `rust/openclaw_core/src/guardian.rs:161` through `rust/openclaw_core/src/guardian.rs:177` hard-code drawdown weight `0.35` and reject threshold `risk_score >= 0.3`.

Evidence command/inspection method:
- `nl -ba rust/openclaw_core/src/guardian.rs | sed -n '1,210p'`

Impact:
The core veto reasons still reject in the current branch, so this is not an observed bypass. The risk is operational: weights, ratio breakpoints, and the aggregate rejection threshold cannot be tuned or validated from runtime risk policy, so promotion/risk calibration can drift from configured market regime and leverage rules.

Why real, not false positive:
The values are literals inside `Guardian::review`, while the surrounding config struct only exposes caps and modification parameters. No TOML/RiskConfig source was found for these scoring constants in the inspected path.

Suggested fix direction:
Move guardian weights, excessive-leverage ratio, and reject threshold into validated risk config, or document them as invariant constants with tests that assert the intended reject/modify matrix.

Fix owner role: PA + E1  
Verification owner role: QC + E2

### QC-SRMA-005 — DSR can report promote with tiny samples, relying on PBO to defer final promotion

Classification: FACT + INFERENCE  
Severity: P3

Affected path+line:
- `program_code/ml_training/promotion_evidence.py:126` through `program_code/ml_training/promotion_evidence.py:131` default `min_candidate_observations=2`.
- `program_code/ml_training/promotion_evidence.py:142` through `program_code/ml_training/promotion_evidence.py:170` build DSR/PBO evidence from those low-count candidate returns.
- `program_code/learning_engine/dsr_gate.py:394` through `program_code/learning_engine/dsr_gate.py:399` allows `n_observations >= 2`.
- `program_code/learning_engine/dsr_gate.py:435` through `program_code/learning_engine/dsr_gate.py:466` can return DSR verdict `promote` on the DSR component alone.
- `program_code/learning_engine/pbo_gate.py:91` through `program_code/learning_engine/pbo_gate.py:101` define stronger PBO power constants.
- `program_code/learning_engine/pbo_gate.py:420` through `program_code/learning_engine/pbo_gate.py:445` marks insufficient power and blocks `passes_threshold`.
- `program_code/learning_engine/promotion_gate.py:113` through `program_code/learning_engine/promotion_gate.py:126` maps insufficient PBO power to final `defer_data`.

Evidence command/inspection method:
- `nl -ba program_code/ml_training/promotion_evidence.py | sed -n '120,180p'`
- `nl -ba program_code/learning_engine/dsr_gate.py | sed -n '280,520p'`
- `nl -ba program_code/learning_engine/pbo_gate.py | sed -n '320,540p'`
- `nl -ba program_code/learning_engine/promotion_gate.py | sed -n '60,150p'`

Impact:
Final promotion is protected because PBO insufficiency becomes `defer_data`; no promotion bypass was found here. However, the component-level DSR verdict can still say `promote` on as few as two observations, which can mislead reports, operator review, or future call sites that consume DSR separately.

Why real, not false positive:
The DSR gate has only a mathematical denominator guard (`>=2`), while PBO carries the actual power gate. The composite promotion gate uses PBO to defer, but DSR remains a public component with a potentially overconfident standalone verdict.

Suggested fix direction:
Add a DSR power/min-observation policy consistent with promotion requirements, or rename/report component verdicts so low-power DSR is explicitly `defer_data` rather than `promote`.

Fix owner role: MIT + PA  
Verification owner role: QC + E2

### QC-SRMA-006 — Grid OU residual-sigma comments are stale after hot-path wiring

Classification: FACT  
Severity: P3

Affected path+line:
- `rust/openclaw_engine/src/strategies/grid_helpers.rs:140` through `rust/openclaw_engine/src/strategies/grid_helpers.rs:158` show current hot path computes residual sigma from OLS residuals.
- `rust/openclaw_engine/src/strategies/grid_helpers.rs:184` through `rust/openclaw_engine/src/strategies/grid_helpers.rs:216` still documents the residual estimator as “Phase A” and says `compute_ou_step` remains on raw-delta sigma.

Evidence command/inspection method:
- `nl -ba rust/openclaw_engine/src/strategies/grid_helpers.rs | sed -n '130,225p'`

Impact:
No runtime math bug was found in the current inspected hot path. The issue is documentation/comment drift inside strategy math code, which can cause later reviewers to believe the old biased estimator is still active.

Why real, not false positive:
The code at lines 140-158 contradicts the later comments at lines 184-216 in the same file.

Suggested fix direction:
Update the stale comments/tests to reflect that residual sigma is wired into the current OU step path.

Fix owner role: TW + E1  
Verification owner role: R4 + QC

## Non-Findings / Cleared Checks

- No current production Donchian look-ahead finding was raised. `rust/openclaw_core/src/indicators/trend.rs` marks the old current-bar `donchian()` as deprecated and production indicator aggregation uses `donchian_prior`.
- No current Kelly hard-coded tier finding was raised. `rust/openclaw_engine/src/ml/kelly_sizer.rs` now sources thresholds/fractions through `KellyConfig` and `RiskConfig`.
- No current FastTrack hard-coded threshold finding was raised. `rust/openclaw_engine/src/config/risk_config_fast_track.rs` and `rust/openclaw_engine/src/tick_pipeline/on_tick/step_0_fast_track.rs` show tunable config wiring.
- No paper-to-demo/live filename contamination finding was raised for edge-estimate file selection. `edge_estimates.rs:232` routes paper to `edge_estimates_paper.json` and demo/live to `edge_estimates.json`; the remaining P1 is validation/freshness/schema fail-closed, not filename isolation.

## Read-Only Evidence Notes

Representative read-only commands used:
- `git status --porcelain=v1 -b`
- `git rev-parse HEAD`
- `rg -n "donchian|KellyConfig|FastTrack|cost_gate|runtime_bps|validation_passed|trading-stop|run_dispatch_retry|Guardian" ...`
- `nl -ba ... | sed -n ...`

No tests were run because this was a read-only audit and the task explicitly forbade runtime mutation.
