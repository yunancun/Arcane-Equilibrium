# Risk Controls and Kill Switches Audit

Created: 2026-04-28
Status: complete for this audit slice
Scope: per-engine risk config loading, H0 gate, runtime config mutation, risk governor tiers, pause/halt/cooldown behavior, emergency close paths, and operator/API control surfaces.

## Flow Summary

Per-engine risk config is loaded at startup from `settings/risk_control_rules/risk_config_{paper,demo,live}.toml`, with env-var overrides. Runtime updates are split between the current `patch_risk_config` ConfigStore path and the legacy `update_risk_config` IPC path.

On each tick, emergency controls run in this order: Step 0 fast-track risk-level actions, Step 0.5 H0 pre-gate, Step 3 pause gate, Step 4+5 strategy dispatch and order admission, then Step 6 per-position risk checks. H0 checks freshness, health, eligibility, exposure, cooldown, and `kill_switch_active`. Step 6 handles hard stop, dynamic stop, take profit, trailing/time exits, physical-lock exits, session drawdown halt, consecutive-loss cooldown, and daily-loss halt.

Manual live close-all uses an API route that calls IPC `close_all_positions`; the Rust IPC close-all path dispatches reduce-only market orders for demo/live and clears paper state only in paper mode. This is safer than several automatic emergency close paths found below.

## Confirmed Findings

### RC-001

Severity: P1
Status: open
Area: Emergency close / exchange flattening
Files:

- `rust/openclaw_engine/src/tick_pipeline/on_tick/step_0_5_h0_gate.rs`
- `rust/openclaw_engine/src/tick_pipeline/on_tick/step_0_fast_track.rs`
- `rust/openclaw_engine/src/tick_pipeline/on_tick/step_3_signals.rs`
- `rust/openclaw_engine/src/tick_pipeline/commands.rs`

Summary:

Two automatic emergency close paths flatten local `paper_state` and emit close fills without dispatching reduce-only exchange orders: H0 hard-block protective stops and fast-track `CloseAll`.

Evidence:

- H0 hard-block runs `check_stops()`, calls `close_position_at_symbol_market()`, emits a close fill, increments stop stats, and returns early at `step_0_5_h0_gate.rs:43-84`. There is no `execute_position_close()` call.
- The pause-gate protective stop path does call `execute_position_close()` after the local close at `step_3_signals.rs:58-74`, proving the expected exchange close pattern exists.
- Fast-track `CloseAll` closes every local position and emits `risk_close:fast_track` at `step_0_fast_track.rs:497-570`, then returns early without an exchange dispatch.
- The exchange-safe IPC close-all path explicitly sends `OrderDispatchRequest` reduce-only market orders when `pipeline_kind.is_exchange()` at `commands.rs:727-790`.

Impact:

In demo/live mode, H0 hard-block stops or fast-track CloseAll can make the engine believe it is flat while the exchange position remains open. That creates false safety state, missed follow-up closes, wrong PnL/fill history, and live money exposure during the exact conditions where emergency flattening is expected to be most reliable.

Reproduction or trigger:

Run demo/live with an open position, trigger an H0 hard block while a protective stop is true, or trigger fast-track `CloseAll` via CircuitBreaker, margin-utilization, or held-symbol drop conditions.

Recommended fix:

Make every automatic full-close path share the same exchange-aware primitive as `ipc_close_all()` or call `execute_position_close()` before/with local flattening. Only mark the local position closed after dispatch is accepted or after a confirmed fill, or explicitly track a pending emergency close state.

Verification:

Static trace only. Add demo/live tests that assert H0 hard-block stops and fast-track CloseAll enqueue primary reduce-only close orders.

### RC-002

Severity: P1
Status: open
Area: H0 cooldown and kill switch state
Files:

- `rust/openclaw_types/src/risk.rs`
- `rust/openclaw_core/src/h0_gate.rs`
- `rust/openclaw_engine/src/tick_pipeline/on_tick/step_6_risk_checks.rs`
- `rust/openclaw_engine/src/event_consumer/loop_handlers.rs`
- `rust/openclaw_engine/src/event_consumer/types.rs`

Summary:

The H0 risk snapshot carries both cooldown and kill-switch fields, but the periodic status update overwrites them with `0` and `false` every 30 seconds.

Evidence:

- `H0GateRiskSnapshot` includes `cooldown_until_ts_ms` and `kill_switch_active` at `risk.rs:75-80`.
- H0 rejects when `kill_switch_active` is true or when cooldown has not expired at `h0_gate.rs:400-430`.
- Consecutive-loss cooldown writes a future `cooldown_until_ts_ms` through `update_risk()` at `step_6_risk_checks.rs:525-538`.
- The status loop runs every `STATUS_INTERVAL_SECS = 30` and calls `update_risk()` with `cooldown_until_ts_ms: 0` and `kill_switch_active: false` at `loop_handlers.rs:1003-1031`.

Impact:

A configured 15/30/45-minute consecutive-loss cooldown can be erased within 30 seconds. Any future kill switch implemented through the same H0 risk snapshot would also be cleared by the status heartbeat.

Reproduction or trigger:

Reach the consecutive-loss threshold so Step 6 sets cooldown, then wait for the next status interval.

Recommended fix:

Do not use a full replacement snapshot for independently owned risk fields. Preserve non-expired cooldown and active kill-switch state during exposure/count refresh, or split H0 risk state into separate setters with clear ownership.

Verification:

Static trace only. Add a test that sets cooldown, runs the status snapshot update, and asserts cooldown remains active.

### RC-003

Severity: P1
Status: open
Area: API authorization for risk controls
Files:

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/risk_routes.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/governance_routes.py`

Summary:

Several state-changing risk routes require authentication but do not enforce the operator role, including live per-engine risk config changes, cooldown reset, and session unhalt.

Evidence:

- `POST /config/global` only depends on `base.current_actor` at `risk_routes.py:215-235`.
- `POST /agent-adjust` and `POST /reset-cooldown` also only depend on `base.current_actor` at `risk_routes.py:338-374`.
- `POST /config/engine/{engine}/global` documents “Operator role required” and can target `live`, but it only validates the engine string before calling `patch_risk_config` at `risk_routes.py:635-673`.
- `POST /unhalt-session` clears Rust `session_halted + paper_paused` through `resume_paper` with no operator role check at `risk_routes.py:676-694`.
- The same file shows the intended pattern on `reset_drawdown_baseline`, which checks `actor.roles` and rejects non-operators at `risk_routes.py:477-487`. Shared operator helpers also exist in `governance_routes.py`.

Impact:

Any authenticated non-operator role can alter risk limits, patch live-engine global risk config, clear cooldown/loss counters, or unhalt a session. That undermines the intended separation between viewer/authenticated access and operational control.

Reproduction or trigger:

Authenticate as an actor without `operator` and call one of the listed routes.

Recommended fix:

Add a single risk-route operator guard and apply it to all mutating risk/session endpoints. Keep read-only risk endpoints on authenticated access if desired. Add route tests for viewer vs operator behavior, especially `engine=live`.

Verification:

Static trace only.

### RC-004

Severity: P1
Status: open
Area: Startup fail-safe defaults
Files:

- `rust/openclaw_engine/src/startup/mod.rs`
- `rust/openclaw_engine/src/config/io.rs`
- `rust/openclaw_engine/src/config/risk_config_advanced.rs`
- `settings/risk_control_rules/risk_config_live.toml`

Summary:

Missing per-engine risk config files are treated as valid defaults. For live, that means a missing or mispointed `risk_config_live.toml` can start with `RuntimeKnobs::default().h0_shadow_mode == true`, while the committed live config explicitly sets H0 hard-blocking to `false`.

Evidence:

- Startup resolves `risk_config_live.toml` and loads it through `load_toml_or_default()` at `startup/mod.rs:188-250`.
- `load_toml_or_default()` returns `T::default()` when the path does not exist at `config/io.rs:25-40`.
- `RuntimeKnobs` defaults `h0_shadow_mode` to `true` at `risk_config_advanced.rs:355-378`.
- The live TOML intentionally sets `h0_shadow_mode = false` at `risk_config_live.toml:175-178`.

Impact:

If the live config path is wrong or the file is absent, live can boot with H0 in observe-only mode instead of hard-block mode. That is a fail-open behavior for a startup safety dependency.

Reproduction or trigger:

Set `OPENCLAW_RISK_CONFIG_LIVE` to a nonexistent path, or deploy without `settings/risk_control_rules/risk_config_live.toml`.

Recommended fix:

Require the live and demo risk config files to exist, or make the loader mode-aware so live cannot default into shadow-mode H0. If defaults are still needed for paper, keep that fallback scoped to paper only.

Verification:

Static trace only. Add startup tests for missing live config and missing paper config with different expected outcomes.

### RC-005

Severity: P1
Status: open
Area: Risk governor tier enforcement
Files:

- `rust/openclaw_core/src/sm/risk_gov.rs`
- `rust/openclaw_core/src/governance_core.rs`
- `rust/openclaw_engine/src/event_consumer/handlers/risk.rs`
- `rust/openclaw_engine/src/event_consumer/loop_handlers.rs`
- `rust/openclaw_engine/src/intent_processor/router.rs`
- `rust/openclaw_engine/src/tick_pipeline/commands.rs`
- `rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs`

Summary:

The risk governor defines restrictive tier constraints, and `GovernanceCore::execute_risk_cascade()` can restrict/freeze auth and revoke leases, but runtime escalations in the engine mutate only `governance.risk`. The admission path mostly checks `governance.is_authorized()` and does not enforce `constraints_for(level)`.

Evidence:

- `constraints_for()` says `Reduced`, `Defensive`, `CircuitBreaker`, and `ManualReview` should disable new entries or require operator action at `risk_gov.rs:172-203`.
- `execute_risk_cascade()` restricts auth at `Reduced` and freezes auth/revokes leases at `CircuitBreaker` at `governance_core.rs:171-246`.
- Operator escalation calls `pipeline.governance.risk.escalate_to(...)` directly at `event_consumer/handlers/risk.rs:76-84`.
- Reconciler and cross-engine escalations also call `risk.reconciler_escalate_to(...)` directly at `event_consumer/handlers/risk.rs:520-527` and `loop_handlers.rs:117-134`.
- `IntentProcessor::process_with_features()` only rejects on `!governance.is_authorized()` at `intent_processor/router.rs:38-40`; `is_authorized()` only checks disabled/frozen/no-effective-auth at `governance_core.rs:156-163`.
- External order submission checks `paper_paused` and `session_halted`, then calls the same intent processor at `tick_pipeline/commands.rs:53-58` and `:92-98`.
- Strategy tick dispatch separately blocks entries when fast-track returns a pause flag at `step_4_5_dispatch.rs:194-204`, but that is not a general governor-admission check.

Impact:

Risk tier escalation can diverge from actual authorization and order admission. For example, operator/reconciler escalation does not automatically freeze live auth, revoke leases, update governance mode, or block external order submission through the same tier constraints. Strategy ticks partially observe risk levels through fast-track, but the broader governance contract is not enforced consistently.

Reproduction or trigger:

Force a governor tier through the IPC escalation path, then inspect governance auth/mode and attempt an external order while `paper_paused` and `session_halted` are false.

Recommended fix:

Route all risk escalations through `GovernanceCore::execute_risk_cascade()` or enforce `constraints_for(governance.risk.snapshot_level())` inside `process_with_features()` and `submit_external_order()`. Ensure risk transitions update governance mode, auth, and leases atomically. Add tests for Reduced, Defensive, CircuitBreaker, and ManualReview admission behavior.

Verification:

Static trace only.

### RC-006

Severity: P2
Status: open
Area: Legacy runtime risk config IPC
Files:

- `rust/openclaw_engine/src/ipc_server/handlers/risk.rs`
- `rust/openclaw_engine/src/event_consumer/handlers/risk.rs`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/ipc_client.py`

Summary:

The legacy `update_risk_config` IPC method reports success after enqueueing a command, not after the event consumer applies the update. It ignores send failure and cannot surface validation failure for exit config patches.

Evidence:

- The IPC handler ignores the result of `tx.send(...)` and immediately returns `{"updated": true}` at `ipc_server/handlers/risk.rs:150-181`.
- The consumer-side exit config update can reject a patch through `apply_patch()` validation and only logs the rejection at `event_consumer/handlers/risk.rs:412-473`.
- If the risk store is unwired, the same handler logs and skips the exit patch at `event_consumer/handlers/risk.rs:476-481`.
- The Python `EngineIPCClient.update_risk_config()` wrapper still exposes this method at `ipc_client.py:444-543`.

Impact:

Operators or tools using the legacy method can receive a successful response even when the command was not delivered, the update was rejected, or the store was unavailable. Current GUI risk writes mostly use `patch_risk_config`, but the legacy method remains callable and documented by the client wrapper.

Reproduction or trigger:

Close the pipeline command receiver, send an invalid exit patch, or call the method in a path where `risk_store()` is `None`.

Recommended fix:

Deprecate external use of `update_risk_config` in favor of `patch_risk_config`, or add an acknowledgement channel so the IPC response reflects delivery and application result. At minimum, return an error on `tx.send` failure.

Verification:

Static trace only.

## Controls Confirmed

- Pause-gate protective stops do dispatch exchange closes in demo/live through `execute_position_close()`.
- Step 6 session halt sets both `session_halted` and `paper_paused`, and its close-all loop dispatches exchange closes.
- Manual live close-all requires operator role and includes an orphan-position REST sweep after IPC close-all.
- Order admission rejects non-reducing orders when daily loss is above `limits.daily_loss_max_pct`; reducing orders remain allowed for survival-first unwinds.

## Files Reviewed

- `rust/openclaw_engine/src/startup/mod.rs`
- `rust/openclaw_engine/src/config/io.rs`
- `rust/openclaw_engine/src/config/risk_config.rs`
- `rust/openclaw_engine/src/config/risk_config_advanced.rs`
- `rust/openclaw_engine/src/risk_checks.rs`
- `rust/openclaw_engine/src/position_risk_evaluator.rs`
- `rust/openclaw_engine/src/fast_track.rs`
- `rust/openclaw_engine/src/ipc_server/handlers/risk.rs`
- `rust/openclaw_engine/src/event_consumer/handlers/risk.rs`
- `rust/openclaw_engine/src/event_consumer/handlers/lifecycle.rs`
- `rust/openclaw_engine/src/event_consumer/loop_handlers.rs`
- `rust/openclaw_engine/src/event_consumer/types.rs`
- `rust/openclaw_engine/src/intent_processor/router.rs`
- `rust/openclaw_engine/src/tick_pipeline/commands.rs`
- `rust/openclaw_engine/src/tick_pipeline/on_tick/step_0_fast_track.rs`
- `rust/openclaw_engine/src/tick_pipeline/on_tick/step_0_5_h0_gate.rs`
- `rust/openclaw_engine/src/tick_pipeline/on_tick/step_3_signals.rs`
- `rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs`
- `rust/openclaw_engine/src/tick_pipeline/on_tick/step_6_risk_checks.rs`
- `rust/openclaw_core/src/h0_gate.rs`
- `rust/openclaw_core/src/governance_core.rs`
- `rust/openclaw_core/src/sm/risk_gov.rs`
- `rust/openclaw_types/src/risk.rs`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/risk_routes.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/governance_routes.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_session_endpoints.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_session_account_routes.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/ipc_client.py`
- `settings/risk_control_rules/risk_config_paper.toml`
- `settings/risk_control_rules/risk_config_demo.toml`
- `settings/risk_control_rules/risk_config_live.toml`
