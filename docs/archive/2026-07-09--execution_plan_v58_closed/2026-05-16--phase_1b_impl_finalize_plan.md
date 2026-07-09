# EDGE-P2-3 Phase 1b IMPL Finalize Plan

- Date: 2026-05-16
- Author: PA(default)
- Status: PLAN-FINAL / E1 dispatch-ready for source + test implementation
- Scope: planning only. This file does not authorize live enablement, deployment, or frozen spec/AMD edits.

## 0. Inputs And Decision Delta

Required inputs read:

- `AGENTS.md`, `CLAUDE.md`, `TODO.md`, `.codex/MEMORY.md`
- `.codex/agents/PA.md`, `.claude/agents/PA.md`
- `docs/execution_plan/2026-05-15--edge_p2_3_phase_1b_close_maker_first_spec.md`
- `docs/governance_dev/amendments/2026-05-15--AMD-2026-05-15-02-edge-p2-3-phase-1b-close-maker-first.md`
- `docs/execution_plan/2026-05-15--v094_close_maker_first_audit_schema_spec.md`
- `docs/archive/2026-05-16--close_maker_first_phase_1b_round1_archive.md`
- Current TODO v40 Phase 1b rows and active healthcheck registry state.

Operator delta for this plan:

- Source + test IMPL may be dispatched now.
- Deploy, live enablement, and Phase 2a remain gated by the existing 3-gate policy.
- Wave 3.5 Linux migration backlog is closed and no longer blocks IMPL dispatch.
- Bundle `P1-EDGE-P2-3-PH1B-DYNAMIC-BACKOFF-FOLLOWUP` is included in the initial Phase 1b IMPL, not deferred.
- Production BB-MF-3 callback wiring from `P1-BBMF3-WIRE-1` is included in the initial Phase 1b IMPL.

Hard forbidden actions preserved:

- No live mainnet.
- No `phys_lock` live land.
- No production `allLiquidation` subscription.
- No `OPENCLAW_ENABLE_PAPER=1`.
- No runtime config, risk config, SQL production apply, or deploy action in E1 source/test worktrees.

## 1. Pre-Deploy Condition

Source + test implementation can start now, but pre-deploy remains blocked until all of the following are true:

- Wave 3.5 migration backlog remains closed.
- E2 review approves spec/AMD/V094 conformance and no-go guard preservation.
- E4 regression gate passes.
- QA signs off on evidence and healthcheck semantics.
- PM signs off on the dispatch bundle and conflict resolution.
- Existing 3-gate policy is green:
  - `P0-EDGE-1` status reviewed by PM.
  - `W-AUDIT-8b` Stage 0R green.
  - `W-AUDIT-8a` C1 full proof and BB/MIT signoff complete.

No Phase 1b deploy may proceed from this plan alone.

## 2. E1 Worktree Breakdown

| Worktree | Owner | Primary Files | LOC Estimate | Dependencies | Parallelism |
| --- | --- | --- | ---: | --- | --- |
| A. V094 schema + writer | E1-A | `sql/migrations/V094__fills_close_maker_audit.sql`, `rust/openclaw_engine/src/database/mod.rs`, `rust/openclaw_engine/src/database/trading_writer.rs`, fill caller sites | 240-360 source, 120-180 tests | None for schema shape; must land before B/C final writer calls | Can start immediately. Blocks final integration for B/C audit fields. |
| B. Close-maker eligibility + dispatch | E1-B | `rust/openclaw_engine/src/tick_pipeline/commands.rs`, `rust/openclaw_engine/src/strategies/common/maker_price.rs`, strategy parameter surfaces as needed, close-maker tests | 350-450 source, 300-420 tests | Needs A field shape for audit emit; can stub locally if rebased | Starts after A interface draft or branches atop A. Shares `commands.rs`, so serialize with any other command edits. |
| C. Rejection fallback + dynamic backoff | E1-C | `rust/openclaw_engine/src/event_consumer/dispatch.rs`, `rust/openclaw_engine/src/event_consumer/pending_sweep.rs`, event callback glue, `rust/openclaw_engine/src/strategies/maker_rejection.rs`, `rust/openclaw_engine/src/strategies/grid_trading/position_mgmt.rs`, `rust/openclaw_engine/src/strategies/grid_trading/tests.rs` | 350-500 source, 180-260 tests | Needs A audit enums before final fill details; interacts with B fallback trigger tags | Can start immediately on helper/state tests. Final callback integration after B trigger contract is fixed. |
| D. Healthcheck observability | E1-D | `helper_scripts/db/passive_wait_healthcheck/runner.py`, `helper_scripts/db/passive_wait_healthcheck/__init__.py`, new close-maker audit check module, healthcheck unit tests | 320-450 source/tests | Needs V094 column names from A; no Rust dependency | Can start immediately with query/unit fixtures. Numeric IDs must be rebased before merge. |
| E. Regression guard + evidence pack | E1-E | non-training grep guards, targeted regression script/report skeletons under owned workspace/report paths, optional unit guard files if existing pattern supports them | 180-260 source/docs/tests | Needs A/B/C/D paths and labels finalized | Starts after A/B/C interface names settle; runs last as merge/regression pass. |

### A. V094 Schema + Writer

Responsibilities:

- Add migration `V094__fills_close_maker_audit.sql`.
- Add `trading.fills.close_maker_attempt boolean not null default false`.
- Add `trading.fills.close_maker_fallback_reason text` with the V094 CHECK enum.
- Preserve existing `trading.fills.details` JSONB for:
  - `close_initial_limit_price`
  - `close_final_fill_price`
  - `close_maker_eligible_reason`
  - `rate_limit_scope`
- Extend `TradingMsg::Fill` and every fill call site without losing existing 23-column semantics.
- Update writer insert column order and bind order atomically.

Required schema enum values:

- `timeout_taker`
- `postonly_reject`
- `cancel_grace_expired`
- `ack_lost`
- `rate_limit_pause_global`
- `rate_limit_backoff_per_symbol`
- `fast_escalate_safety_upgrade`
- `not_attempted_safety_path`
- `engine_shutdown_safety`
- `fallback_to_taker_mandatory`

Review focus:

- No nullable audit ambiguity for `close_maker_attempt`.
- No ad hoc JSON string construction when a structured JSON API is available.
- Linux PostgreSQL dry-run x2 is required before deploy, but E1 must not apply production SQL.

### B. Close-Maker Eligibility + Dispatch

Responsibilities:

- Implement close-maker eligibility in the close path only.
- Keep cold-boot default `use_maker_close=false`.
- Reuse `compute_post_only_price` for close limit price with inverted close direction.
- Preserve W-C Caveat 2: close dispatch uses `strategy_id=None`, `signal_id=None`, `position_lock_id=None`, `portfolio_decision_id=None`.
- Convert only positive whitelist close reasons to PostOnly limit attempts when enabled.
- Leave all safety/risk/operator/shutdown paths as market.

Positive whitelist:

- `grid_close_short`
- `grid_close_long`
- `bb_mean_revert`
- `phys_lock_gate4_giveback`
- `phys_lock_gate4_stale_roc_neg`
- `ma_reverse_cross`
- `bw_squeeze`
- `pctb_revert`

Negative/market-only examples:

- `risk_close HARD/TRAILING/TIME/DYNAMIC STOP`
- `fast_track*`
- `halt_session*`
- `TAKE PROFIT`
- `COST EDGE`
- daily loss, drawdown, consecutive loss
- bybit sync/orphan/dust closes
- operator override IPC
- shutdown, circuit breaker, auth expiry
- BB breakout internal `trailing_stop`
- unknown reasons

Required pricing behavior:

- Normal close-maker timeout: 30s.
- `phys_lock_gate4_giveback` timeout: 15s.
- `phys_lock_gate4_stale_roc_neg` timeout: 10s.
- Spread guard `> 50 bps`: strict maker skip and market fallback.
- Small-tick 1000-prefix handling: bounded widening or strict skip, with no taker-crossing PostOnly price.

### C. Rejection Fallback + Dynamic Backoff

Responsibilities:

- Wire production callback handling for close PostOnly rejects and pending sweep outcomes.
- Ensure every close-maker fallback returns to taker market; no silent abandon.
- Include `P1-BBMF3-WIRE-1` production rejectReason/callback wiring.
- Include `P1-EDGE-P2-3-PH1B-DYNAMIC-BACKOFF-FOLLOWUP` in initial IMPL.

Mandatory fallback races:

- A: Pending close maker + risk trigger cancels maker and market re-submits with `fast_escalate_safety_upgrade`.
- B: Maker timeout cancels; after ack/grace it market re-dispatches with `timeout_taker`, `cancel_grace_expired`, or `ack_lost`.
- C: PostOnly reject immediately markets with `postonly_reject` and no cooldown.
- D: TooManyPending uses per-symbol exponential backoff from 1s up to 60s; when at least 10 symbols hit in 1 minute, apply 5 minute global pause with `rate_limit_pause_global`.
- E: Shutdown/auth/circuit interruption records safety reason and does not leave a maker close orphan.

Dynamic backoff requirements:

- Replace fixed 5 minute close TooManyPending cooldown for the Phase 1b close-maker path with per-symbol 1s exponential backoff capped at 60s.
- Add 5 minute global pause when the 10-symbol/1-minute threshold is hit.
- Record rate-limit scope in `details.rate_limit_scope`.
- Preserve existing BB-MF-3 entry/close cooldown isolation.

### D. Healthcheck Observability

Responsibilities:

- Add close-maker audit healthcheck module and unit tests.
- Register checks only after confirming active IDs.
- Preserve existing active healthcheck IDs `[64]`, `[65]`, `[68]`, and `[69]`.

ID handling:

- Frozen V094/spec text names semantic checks as `[62]`-`[65]`.
- Current runner already uses `[64]` and `[65]`; historical docs also mention `[62]`/`[63]`.
- E1-D must rebase numeric IDs to the next free contiguous slots, currently expected `[70]`-`[73]`, unless PM assigns a different registry range before implementation.
- Semantic labels from V094 must be preserved even if numeric IDs are rebased.

Required semantic checks:

- Close maker fill-rate Wilson interval.
- Close maker audit lineage guard: close-maker rows must have no spine IDs.
- Close maker fallback completeness and NULL ladder.
- Close maker rate-limit/backoff scope and global pause coverage.

### E. Regression Guard + Evidence Pack

Responsibilities:

- Add no-training/no-spine grep guard coverage where local patterns exist.
- Add regression command pack and evidence template for E4/QA.
- Validate no forbidden runtime enablement landed.
- Validate no frozen spec/AMD/TODO/shared-memory edits were required by E1.

## 3. Dependency Order

1. PM creates five E1 worktrees from the same aligned `origin/main` baseline.
2. E1-A starts first and defines V094 schema/writer interfaces.
3. E1-D starts in parallel using A's intended column names; rebases numeric healthcheck IDs before final patch.
4. E1-C starts dynamic backoff state and BB-MF-3 callback tests in parallel.
5. E1-B starts close-maker dispatch after A's fill/audit interface is visible, or branches atop A if PM chooses a stacked integration.
6. E1-E starts after A/B/C/D stabilize names and paths.
7. Integration order: A, B/C, D, E.
8. E2 reviews integrated source/test diffs before E4 regression.
9. E4 runs regression gate.
10. QA and PM sign off before any deploy decision.

Parallelism constraints:

- `commands.rs` edits are exclusive to E1-B.
- `TradingMsg::Fill` shape is owned by E1-A; other worktrees must consume rather than redefine it.
- `grid_trading/tests.rs` BB-MF-3 updates are owned by E1-C; B may add close-maker tests in a separate module or coordinate exact test file ownership with PM.
- Healthcheck runner registration is owned by E1-D.

## 4. Required Tests

### 4.1 BB-MF-3 Baseline Tests

The E4 gate must keep all eight baseline tests passing:

1. `test_entry_reject_does_not_freeze_close_path`
2. `test_close_reject_does_not_freeze_entry_path`
3. `test_close_too_many_pending_5min_cooldown`
4. `test_close_postonly_cross_no_cooldown_immediate_market`
5. `test_close_default_reject_categories_1min_cooldown`
6. `test_grid_short_circuits_when_both_cooldowns_active`
7. `test_cooldown_isolation_multi_symbol`
8. `test_arm_close_cooldown_saturating_add_overflow_safe`

If dynamic backoff replaces the fixed 5 minute close TooManyPending expectation, E1-C must either update the test name/expectation under PM-approved semantics or add a compatibility baseline that proves old entry-path behavior remains isolated.

### 4.2 Close-Maker Tests

E1-B/E1-C must add eight close-maker tests:

1. Whitelist classifier accepts the eight positive reasons and rejects safety/risk/operator/shutdown/unknown reasons.
2. Close limit price uses inverted side, bounded PostOnly price, and per-reason timeout.
3. Spread guard `> 50 bps` skips maker and falls back to market.
4. Small-tick 1000-prefix handling widens safely or strictly skips without crossing.
5. All three close dispatchers emit PostOnly only when eligible and keep all spine IDs `None`.
6. Timeout path cancels maker, waits ack/grace, and market re-dispatches without abandon.
7. PostOnly reject immediately market re-dispatches with `postonly_reject` and no close cooldown.
8. Shutdown/auth/cancel interruption records safety fallback and does not enable live behavior.

### 4.3 Healthcheck Unit Tests

E1-D must add five healthcheck unit tests:

1. Fill-rate Wilson PASS/NEUTRAL/WARN/FAIL classification.
2. Audit lineage guard passes zero-spine rows and fails any close-maker row with spine IDs.
3. Fallback completeness and NULL-ladder behavior, excluding safety enum exceptions where specified.
4. Dynamic backoff/rate-limit scope coverage, including per-symbol and global pause cases.
5. Healthcheck registration static guard: no duplicate IDs/labels and close-maker semantic checks occupy the PM-approved next-free IDs.

## 5. E2 Review Gate

E2 must review the integrated source/test diff before E4. Required checks:

- Close-maker eligibility exactly matches spec v1.3 + AMD v0.4.
- Dynamic backoff is included in the initial IMPL and does not leave fixed-only production behavior on the close-maker TooManyPending path.
- V094 writer/schema fields are present and populated without breaking existing fill writes.
- W-C Caveat 2 is preserved: no ML/spine lineage IDs on close-maker audit rows.
- Safety/risk/operator/shutdown paths remain market.
- `phys_lock` live remains deferred.
- No live mainnet, no production `allLiquidation`, and no `OPENCLAW_ENABLE_PAPER=1`.
- Healthcheck numeric IDs do not collide with current runner registrations.
- No frozen spec/AMD/TODO/CLAUDE/shared-memory edits were included in E1 source/test worktrees.

## 6. E4 Regression Gate

E4 must run or explicitly record why it cannot run:

- `cargo fmt --check`
- Rust compile/check for `openclaw_engine`
- Eight BB-MF-3 baseline tests
- Eight close-maker tests
- Five healthcheck unit tests
- V094 migration dry-run on Linux PostgreSQL x2 before deploy consideration
- Static grep guard for forbidden live enablement and forbidden production `allLiquidation`
- Static grep guard proving close-maker audit rows do not carry spine IDs

E4 output must include exact commands, environment, pass/fail result, and any skipped test rationale.

## 7. QA And PM Sign-Off Checklist

QA checklist:

- Evidence pack includes all E4 command output or skip rationale.
- Healthcheck IDs are non-colliding in the active runner.
- Audit schema fields and JSON detail keys match V094 semantics.
- Close-maker failure modes always fall back to taker market or record an engine shutdown safety reason.
- No runtime enablement/config mutation is included.

PM checklist:

- Confirm source/test IMPL dispatch happens after a fresh PM race check against current `origin/main`; the initial Wave A-D race check baseline was `abaa4de7`, and C-1 later advanced `origin/main` to `197ca14d`.
- Confirm no E1 agent committed, pushed, reverted unrelated files, or edited frozen/shared documents.
- Confirm dynamic backoff follow-up is intentionally merged into initial IMPL despite TODO/archive drift.
- Confirm deploy remains blocked until E2, E4, QA, PM, and 3-gate signoff are complete.
- Confirm Phase 2a remains blocked until the 14 day close-maker demo pass and PM authorization.

## 8. Current Conflicts And Drift To Track

- TODO v40 still says Phase 1b IMPL is paused/gated behind audit proof. This operator prompt overrides that for source/test IMPL dispatch only; deploy remains gated.
- TODO/archive text places `P1-EDGE-P2-3-PH1B-DYNAMIC-BACKOFF-FOLLOWUP` after Phase 2a. This operator prompt requires it in the initial IMPL bundle.
- Frozen V094/spec healthcheck IDs `[62]`-`[65]` conflict with current active runner IDs `[64]` and `[65]`, and historical docs mention `[62]`/`[63]`. Implementation must rebase numeric IDs while preserving semantic check labels.
- Archive v36 still describes Wave 3.5 Linux migration backlog as pending; current TODO v40 and this plan treat it as closed.
- At B-1 drafting time, the local working tree contained an unrelated dirty `.claude/agents/E3.md`; B-1 did not touch it. PM later committed that C-1 guard separately as `197ca14d`.
