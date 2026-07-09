# Phase 1b E1 Dispatch Packet

- Date: 2026-05-16
- Author: PA(default)
- Status: DISPATCH-READY for E1 source + test worktrees
- Companion plan: `docs/execution_plan/2026-05-16--phase_1b_impl_finalize_plan.md`
- Dispatch scope: implementation planning packet only. PM performs actual assignment, branch/worktree management, commit, and push.

## 0. Global Dispatch Rules

Every E1 worktree must read before editing:

- `AGENTS.md`
- `CLAUDE.md`
- `.codex/MEMORY.md`
- `.codex/AGENT_DISPATCH_PROTOCOL.md`
- `.codex/SUBAGENT_EXECUTION_RULES.md`
- `docs/execution_plan/2026-05-16--phase_1b_impl_finalize_plan.md`
- `docs/execution_plan/2026-05-15--edge_p2_3_phase_1b_close_maker_first_spec.md`
- `docs/governance_dev/amendments/2026-05-15--AMD-2026-05-15-02-edge-p2-3-phase-1b-close-maker-first.md`
- `docs/execution_plan/2026-05-15--v094_close_maker_first_audit_schema_spec.md`
- `docs/archive/2026-05-16--close_maker_first_phase_1b_round1_archive.md`

Shared hard boundaries:

- Do not edit frozen spec/AMD, TODO, CLAUDE, shared PA memory, runtime config, risk config, or deploy manifests.
- Do not run production SQL migrations.
- Do not enable live mainnet.
- Do not land `phys_lock` live behavior.
- Do not add production `allLiquidation` subscription.
- Do not set or require `OPENCLAW_ENABLE_PAPER=1`.
- Do not commit, push, stash-pop, stash-drop, clean, reset, or revert unrelated files.

Required source baseline:

- PM initial race check reported local `main` aligned with `origin/main` at `abaa4de7`.
- PM C-1 checkpoint later advanced `origin/main` to `197ca14d`; E1 worktrees must fetch and base on current `origin/main`, not the stale initial baseline.
- Each worktree must re-check local status before editing and report unrelated dirt without touching it.

## 1. Worktree A: V094 Schema + Writer

Bound role: `E1(worker)`

Mission:

- Implement V094 close-maker audit persistence without changing runtime behavior.

Owned files:

- `sql/migrations/V094__fills_close_maker_audit.sql`
- `rust/openclaw_engine/src/database/mod.rs`
- `rust/openclaw_engine/src/database/trading_writer.rs`
- Fill caller sites required by the `TradingMsg::Fill` signature update
- Focused database/writer tests following existing local patterns

Deliverables:

- `close_maker_attempt boolean not null default false`
- `close_maker_fallback_reason text` with V094 enum CHECK
- Fill details keys supported:
  - `close_initial_limit_price`
  - `close_final_fill_price`
  - `close_maker_eligible_reason`
  - `rate_limit_scope`
- Existing fill writes still bind all pre-existing columns correctly.
- Local report under E1 workspace with changed files and tests.

LOC estimate: 240-360 source, 120-180 tests.

Dependencies:

- Starts immediately.
- B/C consume this audit interface; do not let other worktrees redefine `TradingMsg::Fill`.

Minimum tests:

- Writer unit/compile coverage for default false audit fields.
- Migration dry-run instructions captured for Linux PostgreSQL x2; do not apply production SQL.

## 2. Worktree B: Close-Maker Eligibility + Dispatch

Bound role: `E1(worker)`

Mission:

- Convert eligible close paths to optional PostOnly maker-first attempts while preserving market safety paths.

Owned files:

- `rust/openclaw_engine/src/tick_pipeline/commands.rs`
- `rust/openclaw_engine/src/strategies/common/maker_price.rs`
- Strategy parameter/config type surfaces required for cold-default `use_maker_close=false`
- Close-maker dispatch tests

Deliverables:

- Positive whitelist only:
  - `grid_close_short`
  - `grid_close_long`
  - `bb_mean_revert`
  - `phys_lock_gate4_giveback`
  - `phys_lock_gate4_stale_roc_neg`
  - `ma_reverse_cross`
  - `bw_squeeze`
  - `pctb_revert`
- Safety/risk/operator/shutdown/unknown reasons remain market.
- `compute_post_only_price` reused with inverted close direction.
- Per-reason timeout: 30s normal, 15s giveback, 10s stale ROC.
- Spread `> 50 bps` strict maker skip.
- Small-tick 1000-prefix widening/skip covered.
- Spine IDs remain `None` on close dispatch.

LOC estimate: 350-450 source, 300-420 tests.

Dependencies:

- Start after A publishes fill/audit interface, or stack directly on A branch if PM chooses stacked integration.
- Coordinate with C on fallback trigger tags and enum reason strings.

Minimum tests:

- Add close-maker tests 1-5 from the plan.
- Prove cold default remains market-only.

## 3. Worktree C: Rejection Fallback + Dynamic Backoff

Bound role: `E1(worker)`

Mission:

- Wire production close-maker fallback behavior and include dynamic TooManyPending backoff in initial IMPL.

Owned files:

- `rust/openclaw_engine/src/event_consumer/dispatch.rs`
- `rust/openclaw_engine/src/event_consumer/pending_sweep.rs`
- Event callback glue/types as required
- `rust/openclaw_engine/src/strategies/maker_rejection.rs`
- `rust/openclaw_engine/src/strategies/grid_trading/position_mgmt.rs`
- `rust/openclaw_engine/src/strategies/grid_trading/tests.rs`

Deliverables:

- `P1-BBMF3-WIRE-1` production rejectReason/callback wiring.
- Immediate market fallback for PostOnly reject with `postonly_reject`.
- Timeout cancel ack/grace then market fallback with `timeout_taker`, `cancel_grace_expired`, or `ack_lost`.
- Risk trigger while maker close pending cancels maker and markets with `fast_escalate_safety_upgrade`.
- TooManyPending per-symbol exponential backoff: 1s to 60s cap.
- Global pause: 10 symbols in 1 minute triggers 5 minute global pause.
- Audit details include `rate_limit_scope`.
- No close-maker fallback silently abandons the close.

LOC estimate: 350-500 source, 180-260 tests.

Dependencies:

- Can start dynamic backoff helper/tests immediately.
- Needs B trigger contract and A audit enums before final integration.

Minimum tests:

- Keep the eight BB-MF-3 baseline tests passing.
- Add close-maker tests 6-8 from the plan.
- Update the existing fixed 5 minute close TooManyPending expectation only with explicit note that Phase 1b dynamic backoff supersedes it for close-maker paths.

## 4. Worktree D: Healthcheck Observability

Bound role: `E1(worker)`

Mission:

- Add V094 close-maker healthcheck coverage with non-colliding active IDs.

Owned files:

- `helper_scripts/db/passive_wait_healthcheck/runner.py`
- `helper_scripts/db/passive_wait_healthcheck/__init__.py`
- New close-maker audit healthcheck module
- Healthcheck unit tests

Deliverables:

- Preserve active runner IDs `[64]`, `[65]`, `[68]`, `[69]`.
- Rebase frozen spec semantic checks from `[62]`-`[65]` to next free active IDs, expected `[70]`-`[73]`, unless PM assigns a different range.
- Semantic checks:
  - Fill-rate Wilson classification.
  - Zero-spine lineage guard.
  - Fallback completeness / NULL ladder.
  - Rate-limit scope and global pause coverage.
- Static registration guard against duplicate IDs/labels.

LOC estimate: 320-450 source/tests.

Dependencies:

- Can start with A's planned column names.
- Finalize after verifying current active runner IDs in the worktree.

Minimum tests:

- Five healthcheck unit tests listed in the plan.

## 5. Worktree E: Regression Guard + Evidence Pack

Bound role: `E1(worker)`

Mission:

- Add final regression/guard coverage and assemble evidence hooks for E4/QA.

Owned files:

- Existing regression guard locations if present.
- E1/E4 workspace report templates under owned workspace/report paths.
- Optional focused unit/static guard files, if consistent with repo patterns.

Deliverables:

- Static guard for no live mainnet enablement.
- Static guard for no production `allLiquidation` subscription.
- Static guard for no `OPENCLAW_ENABLE_PAPER=1`.
- Static guard for no close-maker spine lineage.
- E4 command/evidence template covering Rust, healthcheck, and V094 dry-run evidence.

LOC estimate: 180-260 source/docs/tests.

Dependencies:

- Starts after A/B/C/D names and paths stabilize.
- Runs last before E2/E4.

## 6. Required Test Matrix

E4 must require all of the following:

- Eight BB-MF-3 baseline tests:
  - `test_entry_reject_does_not_freeze_close_path`
  - `test_close_reject_does_not_freeze_entry_path`
  - `test_close_too_many_pending_5min_cooldown`
  - `test_close_postonly_cross_no_cooldown_immediate_market`
  - `test_close_default_reject_categories_1min_cooldown`
  - `test_grid_short_circuits_when_both_cooldowns_active`
  - `test_cooldown_isolation_multi_symbol`
  - `test_arm_close_cooldown_saturating_add_overflow_safe`
- Eight close-maker tests:
  - whitelist classifier
  - inverted close limit price and timeout
  - spread guard
  - small-tick behavior
  - dispatcher PostOnly/spine-none behavior
  - timeout cancel ack/grace fallback
  - PostOnly reject immediate market fallback
  - shutdown/auth/cancel safety fallback
- Five healthcheck unit tests:
  - Wilson fill-rate classification
  - zero-spine lineage guard
  - fallback completeness / NULL ladder
  - per-symbol/global rate-limit scope
  - ID/label registration collision guard
- `cargo fmt --check`
- Rust compile/check for `openclaw_engine`
- Linux PostgreSQL V094 dry-run x2 before deploy consideration
- Static forbidden-action grep guards

## 7. E2 Review Gate

E2 must approve before E4:

- Spec v1.3, AMD v0.4, and V094 conformance.
- Dynamic backoff included in initial source/test IMPL.
- No hidden runtime enablement.
- No `phys_lock` live land.
- No ML/spine lineage on close-maker rows.
- No production `allLiquidation`.
- No `OPENCLAW_ENABLE_PAPER=1`.
- Healthcheck IDs rebased and non-colliding.
- Existing TODO/archive drift explicitly reported, not silently patched.

## 8. QA Gate

QA must verify:

- Evidence pack includes exact commands and outputs or explicit skip rationale.
- All required test groups are represented.
- V094 schema, writer, and healthcheck agree on field names.
- Close-maker fallback never abandons close execution.
- Deploy remains blocked until PM clears the 3-gate.

## 9. PM Sign-Off Checklist

PM must confirm:

- Worktrees were based on current `origin/main` after a fresh PM race check or a PM-approved integration branch.
- No E1 committed or pushed.
- No E1 reverted unrelated dirty files.
- Frozen spec/AMD and shared governance files remain untouched.
- Dynamic backoff was intentionally pulled into initial IMPL.
- `P1-BBMF3-WIRE-1` was included.
- Deploy waits for E2, E4, QA, PM, and 3-gate green state.

## 10. Dispatch Footer

This packet authorizes E1 source/test worktree planning and PM dispatch only. It does not authorize deployment, production configuration changes, live trading, paper-mode enablement, or Phase 2a start.
