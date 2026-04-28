# Strategy and Agent Decision Flow Audit

Created: 2026-04-28
Status: complete

## Scope

This segment reviewed the non-test strategy and agent decision path:

- Strategy signal generation and active-strategy dispatch.
- Intent construction, close-intent bypass behavior, sizing gates, risk gates, predictor gates, and fallback behavior.
- Runtime strategy parameter loading, hot updates, and snapshot persistence.
- LinUCB and edge predictor interaction with decision metadata.
- Strategist scheduler tuning, DB restore, and promotion scaffolding.
- Claude Teacher directive parsing, application, execution audit rows, and IPC sink routing.

Tests were excluded except where search output named test-only call sites; no live database, exchange account, or secret material was inspected.

## Reviewed Runtime Paths

- `rust/openclaw_engine/src/tick_pipeline/on_tick/step_3_signals.rs`
- `rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs`
- `rust/openclaw_engine/src/intent_processor/mod.rs`
- `rust/openclaw_engine/src/intent_processor/gates.rs`
- `rust/openclaw_engine/src/intent_processor/router.rs`
- `rust/openclaw_engine/src/strategies/mod.rs`
- `rust/openclaw_engine/src/strategies/params.rs`
- `rust/openclaw_engine/src/strategies/registry.rs`
- `rust/openclaw_engine/src/strategies/strategy_params.rs`
- `rust/openclaw_engine/src/event_consumer/handlers/strategy_params.rs`
- `rust/openclaw_engine/src/ipc_server/handlers/strategy.rs`
- `rust/openclaw_engine/src/strategist_scheduler/mod.rs`
- `rust/openclaw_engine/src/strategist_scheduler/persist.rs`
- `rust/openclaw_engine/src/main_boot_tasks.rs`
- `rust/openclaw_engine/src/claude_teacher/applier.rs`
- `rust/openclaw_engine/src/claude_teacher/consumer_loop.rs`
- `rust/openclaw_engine/src/claude_teacher/governance_impl.rs`
- `rust/openclaw_engine/src/claude_teacher/parser.rs`
- `rust/openclaw_engine/src/claude_teacher/strategy_ipc_impl.rs`
- `rust/openclaw_engine/src/claude_teacher/writer.rs`
- `rust/openclaw_engine/src/decision_context_producer.rs`
- `rust/openclaw_engine/src/linucb/runtime.rs`
- `rust/openclaw_engine/src/linucb/inference.rs`
- `rust/openclaw_engine/src/edge_predictor/gate.rs`
- `rust/openclaw_engine/src/main.rs`
- `rust/openclaw_engine/src/main_pipelines.rs`
- `rust/openclaw_engine/src/tasks.rs`

## Decision Flow Summary

Step 3 evaluates signal rules and persists signal/context records only when the signal persistence throttle allows a write. Step 4 dispatches active strategies for open intents, while close intents are handled on the risk-reducing path and intentionally bypass most opening gates.

Open intents then enter `IntentProcessor`, where the effective path is layered: governance authorization, duplicate and balance checks, Guardian halt check, Kelly sizing, P1 risk cap, per-engine risk checks, global notional cap, edge predictor gate, JavaScript shrinkage cost gate, maker-entry KPI checks, and finally exchange dispatch or paper simulation.

Agent-driven tuning is split across two independent mechanisms. The `StrategistScheduler` is Demo-primary, restores latest Demo-applied params from DB at boot, and has a Live promotion method that is present but not internally invoked. The Claude Teacher loop is default-off and operator-enabled through IPC; it applies parsed directives through governance checks and a strategy IPC sink.

## Findings

### SADF-001

Severity: P1
Status: open
Area: Teacher directive routing / disabled Paper channel
Files:

- `rust/openclaw_engine/src/main.rs`
- `rust/openclaw_engine/src/tasks.rs`
- `rust/openclaw_engine/src/main_pipelines.rs`

Summary:

Claude Teacher production directives are routed to `paper_cmd_tx`, but Paper is disabled by default and its disabled-mode task drains and drops commands without sending command responses.

Evidence:

- `main.rs:398` sets `phase4_consumer_cmd_tx = paper_cmd_tx.clone()`.
- `main.rs:631-639` passes that sender to `tasks::spawn_teacher_consumer_loop`.
- `tasks.rs:195` wraps the sender in `PipelineCommandSink`.
- `main_pipelines.rs:154-158` disables Paper unless `OPENCLAW_ENABLE_PAPER=1`.
- `main_pipelines.rs:232-249` starts a minimal drain task that consumes `paper_cmd_rx` and drops received commands.

Impact:

If an operator enables the Teacher loop expecting Demo or Live parameter changes, production directives can be drained by the disabled Paper task. `UpdateStrategyParams` and `SetStrategyActive` responses are dropped with the command, so the directive path can time out or appear failed while no engine is changed. This reintroduces the class of Paper-orphan routing problem that the Strategist scheduler already avoided by targeting Demo.

Trigger:

Run with default Paper-disabled settings, enable the Teacher loop through IPC, and let a directive that requires strategy IPC application reach the applier.

Recommended fix:

Route Teacher directive application through `EngineCommandChannels` with an explicit target engine, defaulting to Demo for learning/tuning and requiring a separate authorized Live promotion path. Disabled Paper should reject commands with an explicit response instead of drain-dropping oneshot-bearing commands.

Verification:

Static trace only.

### SADF-002

Severity: P2
Status: open
Area: Strategy parameter hot update atomicity
Files:

- `rust/openclaw_engine/src/event_consumer/handlers/strategy_params.rs`

Summary:

`handle_update_strategy_params` applies `conf_scale` before validating the remaining typed JSON. If typed validation fails, the response reports failure and no snapshot is written, but the runtime `conf_scale` mutation remains active.

Evidence:

- `strategy_params.rs:35-43` strips optional `conf_scale` out of the JSON payload.
- `strategy_params.rs:47-48` applies `strategy.set_conf_scale(scale)` immediately.
- `strategy_params.rs:52-64` validates and applies the remaining typed JSON afterward.
- The error branch at `strategy_params.rs:64` returns `validation failed` without rolling back the already-applied scale.

Impact:

A rejected mixed update can still alter live runtime confidence scaling until restart or a later successful update. Because no snapshot is forced on the failure path, durable state and caller-visible result disagree with runtime behavior.

Trigger:

Send an update payload containing a valid `conf_scale` and an invalid typed strategy field.

Recommended fix:

Stage the full update before mutating the live strategy. Either validate typed JSON first and then apply `conf_scale`, clone-and-validate a candidate strategy, or explicitly roll back `conf_scale` on typed validation failure.

Verification:

Static trace only.

### SADF-003

Severity: P1
Status: open
Area: Strategy config fail-open behavior
Files:

- `rust/openclaw_engine/src/strategies/params.rs`
- `rust/openclaw_engine/src/strategies/strategy_params.rs`
- `rust/openclaw_engine/src/strategies/registry.rs`

Summary:

Strategy parameter loading fail-opens to full defaults for every pipeline kind when the per-engine TOML file is missing or unparseable. The comment documents Paper fail-open behavior, but the implementation does not limit the fallback to Paper.

Evidence:

- `params.rs:97-134` returns `StrategyParamsConfig::default()` on missing or parse-failed TOML for any `PipelineKind`.
- Default strategy parameters mark major strategies active by default, for example `MaCrossoverParams.active` at `strategy_params.rs:24-25` and `MaCrossoverParams::default()` at `strategy_params.rs:154-158`.
- `registry.rs:75-77`, `registry.rs:95-97`, `registry.rs:159-161`, and `registry.rs:189-191` apply configured `active` flags and push those strategies into the runtime registry.

Impact:

A missing or syntactically broken `settings/strategy_params_demo.toml` or `settings/strategy_params_live.toml` can silently resurrect default-active strategies and default thresholds. In Demo or Live, that can materially change which strategies are eligible to trade while startup appears successful.

Trigger:

Start a Demo or Live-capable engine with a missing or invalid per-engine strategy TOML file.

Recommended fix:

Fail closed for Demo and Live strategy config load errors, or load the last known valid persisted strategy config. Keep Paper fail-open only if that remains intentional, and make startup logs distinguish intentional Paper defaults from unsafe Demo/Live fallback.

Verification:

Static trace only.

### SADF-004

Severity: P2
Status: open
Area: LinUCB decision metadata fidelity
Files:

- `rust/openclaw_engine/src/linucb/runtime.rs`
- `rust/openclaw_engine/src/intent_processor/mod.rs`
- `rust/openclaw_engine/src/decision_context_producer.rs`
- `rust/openclaw_engine/src/tick_pipeline/on_tick/step_3_signals.rs`

Summary:

LinUCB is described as live-path per-decision arm selection, but the wired path is observation-only and not tied to accepted `OrderIntent`s. The post-gate selection API is not called outside its own definition, while decision contexts derive LinUCB metadata from the first persisted signal and a two-strategy signal-source mapping.

Evidence:

- `runtime.rs:1-8` says `select_for_intent` returns an arm without changing trading decisions.
- `intent_processor/mod.rs:495-531` exposes `select_arm_after_gates`, but a non-test search found only the method definition.
- `decision_context_producer.rs:54-63` maps only `ma_crossover` and `bollinger_reversion` to LinUCB strategies.
- `decision_context_producer.rs:137-153` uses `signals[0]` for arm metadata and strategy name.
- `step_3_signals.rs:153-186` emits decision context only when a signal was persisted this tick.

Impact:

LinUCB telemetry can be incomplete or detached from the actual order admission decision. Grid, breakout, funding, and tick-driven intents can have no arm metadata, and multi-signal ticks record only the first persisted signal. Dashboards or training jobs that interpret this as accepted-intent LinUCB behavior can learn from mislabeled or missing decision context.

Trigger:

Any accepted order intent from a strategy without a unique mapped signal source, or a tick where the accepted strategy is not `signals[0]` in the persisted context.

Recommended fix:

Either document LinUCB as signal-level observation-only telemetry, or wire `select_arm_after_gates` into the accepted-intent path after risk and cost gates using `OrderIntent.strategy`, the actual regime context, and the decision context ID that will be persisted.

Verification:

Static trace only.

### SADF-005

Severity: P2
Status: open
Area: Teacher directive execution audit fidelity
Files:

- `rust/openclaw_engine/src/claude_teacher/applier.rs`
- `rust/openclaw_engine/src/claude_teacher/writer.rs`

Summary:

The `boost_arm` Teacher directive is a stub with no LinUCB state side effect, but it returns `Applied` and is written to `learning.directive_executions` as `success = true`.

Evidence:

- `applier.rs:471-484` logs that `boost_arm` wiring is deferred and returns `ApplyOutcome::Applied`.
- `writer.rs:175-183` maps `ApplyOutcome::Applied` to `action_taken = "applied"` and `success = true`.
- `writer.rs:221-230` persists that successful execution row.

Impact:

Operators and reports can believe an arm boost was executed when no model or arm state changed. This weakens directive auditability and can make subsequent learning/reporting analysis attribute outcomes to a nonexistent intervention.

Trigger:

A valid Teacher directive with action `boost_arm` and a boost factor within the hard cap.

Recommended fix:

Until the LinUCB state mutation is implemented, return a non-success outcome such as `InvalidDirective`, `NotImplemented`, or a dedicated skipped outcome that persists `success = false`.

Verification:

Static trace only.

### SADF-006

Severity: P3
Status: open
Area: Strategist Live promotion and metric guard
Files:

- `rust/openclaw_engine/src/main_boot_tasks.rs`
- `rust/openclaw_engine/src/strategist_scheduler/mod.rs`

Summary:

The Strategist scheduler is correctly Demo-primary today, but Live promotion and Live metrics are only scaffolded. Restore loads latest applied params for Demo only, `promote_params_to_live` is explicitly not invoked internally, and the Live metric-path guard is a `debug_assert`.

Evidence:

- `main_boot_tasks.rs:143-155` documents the Demo target and optional Live promotion channel.
- `main_boot_tasks.rs:217-220` restores latest applied params using Demo mode only.
- `strategist_scheduler/mod.rs:361-400` implements `promote_params_to_live` but documents that no internal trigger or criteria calls it.
- `strategist_scheduler/mod.rs:650-668` says Live tune is not supported because the SQL would miss `live_demo` rows, but the enforcement is only `debug_assert`.
- `strategist_scheduler/mod.rs:681-695` filters metrics with `engine_mode = $2`.

Impact:

This is mostly an implementation gap rather than a current production defect because the scheduler is spawned as Demo-primary. If future wiring enables Live tuning without changing the release-mode guard and metric query, the scheduler can restore/promote only part of the expected Live state or learn from an empty/incorrect fill set.

Trigger:

Enabling a Live tune target or assuming Demo-applied scheduler params are automatically promoted/restored into Live.

Recommended fix:

Before enabling Live strategist tuning, replace the `debug_assert` with a release-mode fail-fast check, widen Live metric filters to the real live engine-mode set, and add an explicit promotion trigger with acceptance criteria and operator audit.

Verification:

Static trace only.

## Residual Risk

The audit did not execute the strategy pipeline or issue IPC commands. The findings above are based on static control-flow tracing. Runtime validation should be added after fixes, especially for disabled-channel command responses, strategy update atomicity, and Teacher directive audit rows.
