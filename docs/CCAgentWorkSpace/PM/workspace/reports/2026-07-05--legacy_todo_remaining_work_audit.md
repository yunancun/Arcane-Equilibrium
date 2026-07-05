# Legacy TODO Remaining Work Audit

Date: 2026-07-05
Owner: PM
Scope:

- `docs/architecture/multi_agent_rework_2026-05-05/AgentTodo.md`
- `docs/references/2026-04-10--signal_diamond_db_todo.md`

## Verdict

The two legacy TODO documents no longer contain clean, directly dispatchable
remaining work. The safe action is documentation closure and routing clarity,
not runtime implementation.

## AgentTodo Residuals

- MAG-002 / MAG-003 were the only remaining `CONDITIONAL` milestone rows.
- MAG-015 explicitly resolves the M0 conditional gaps from MAG-002 and
  MAG-003 for Sprint A, so both rows are now marked historically closed by the
  MAG-015 contract addendum.
- The historical Open Questions are answered, superseded, or routed to a fresh
  root `TODO.md` / PM dispatch if reopened.
- The Definition of Done is retained as historical target text only. It does
  not authorize Stage 3/4, true-live, Executor unlock, Telegram/WebChat,
  proposal relay, or new runtime authority work.

## Signal Diamond Residuals

- Phase 5 strategy params are already complete through
  `settings/strategy_params_{paper,demo,live}.toml`,
  `load_strategy_params(PipelineKind)`, and
  `StrategyFactory::create_for_engine(...)`.
- The old single-pipeline `mode_states` / `active_modes` design is superseded
  by 3E-4 per-pipeline architecture: immutable `PipelineKind` at construction,
  independent `TickPipeline` instances, independent `Orchestrator` / strategy
  instances, and `effective_engine_mode()` DB tagging.
- The old writerless-table audit is stale for at least
  `trading.orders`, `trading.decision_outcomes`, and
  `agent.ai_invocations`: current code has writer/backfiller paths for those.
- If the project wants shared market/indicator compute with multi-engine
  fan-out in the future, that is a new architecture task and must be opened
  from root `TODO.md` / ADR / PM dispatch.

## Actions Taken

- Closed AgentTodo residual historical rows and reclassified open questions /
  DoD text as historical context.
- Updated Signal Diamond to make 3E-4 per-pipeline supersession explicit and
  remove stale Phase 5 / writerless / `is_paper` blocker language.
- No code, DB, runtime, service, config, secret, Cost Gate, live/mainnet,
  order, or restart action was performed.

## Verification Evidence

- `MAG-015` contract addendum states it resolves the M0 conditional gaps from
  MAG-002 and MAG-003.
- `TickPipeline::with_kind(...)` and 3E-4 comments show `mode_states` /
  `active_modes` removal and immutable per-pipeline identity.
- `StrategyFactory::create_for_engine(...)` loads per-engine strategy params.
- `trading_writer.rs` derives compatibility `is_paper` from
  `engine_mode != "live"`.
- `database/outcome_backfiller.rs` inserts `engine_mode` into
  `trading.decision_outcomes`.
- `AgentEventStore.record_ai_invocation(...)` inserts `engine_mode` into
  `agent.ai_invocations`.
