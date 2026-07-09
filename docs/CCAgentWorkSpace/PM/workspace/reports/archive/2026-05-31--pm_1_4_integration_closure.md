# PM 1-4 Integration Closure — 2026-05-31

## Scope

Operator request: complete items 1-4 in order:

1. LG-3 integration closeout.
2. Reconciler pagination continuation.
3. GUI/QC WIP fix pack verification and sync.
4. Reports/memory triage.

Canonical working branch: `integration/pm-1-4` in clean worktree `/private/tmp/wt-pm-1-4`.

## Result

Status: SOURCE INTEGRATED, NOT RUNTIME DEPLOYED.

The branch integrates LG-3 T1/T4, completes the reconciler pagination/audit semantics batch, lands the narrow GUI/QC WIP fixes, and updates TODO/PM memory with a canonical closure record. Runtime deploy/rebuild remains a separate operator gate after E2/E4/QA review.

## 1. LG-3 Integration

Integrated commits:

- `deb3f3af` `feat(lg3-t1): supervised-live 7-state SM core (state/transition/reconciler)`
- `2bbe5f24`..`7520d205` LG-3 T4 V104 SQL/writer/healthcheck/grep-guard batch
- `0802d52b` `fix(lg3): validate V104 timestamptz chunk interval`

Important correction: the untracked 2026-05-30 MIT V104 report said APPROVE, but a real Linux rollback dry-run against the integrated V104 file exposed a blocker:

- Before fix: `ERROR: V104 Guard C FAIL: hypertable not created on created_at.`
- Cause: Timescale reports `time_interval` for a `timestamptz` hypertable, not `integer_interval`.
- Fix: Guard C now reads `time_interval`, converts via `EXTRACT(EPOCH FROM time_interval)`, and checks 604800 seconds.

Post-fix Linux rollback dry-run:

- exit status 0
- `_sqlx_migrations` before/after unchanged at max 115 / count 107 / V104 absent
- error count 0
- `V104: all guards PASS` observed twice
- transaction ended with `ROLLBACK`

Verification:

- `cargo test -p openclaw_engine --lib supervised_live -- --nocapture` = 26 passed
- `python3 -m py_compile helper_scripts/healthchecks/checks_supervised_live_audit.py`
- `bash -n helper_scripts/healthchecks/e3_grep_non_training_surface.sh`
- V104 SQL action CHECK values match Rust `SmAction.as_str()` count/order: 17/17

## 2. Reconciler Pagination

Integrated `ba2090ad` as `bb7e9efc`, then completed missing docs/audit/error handling in `baf46a69`.

Completed behavior:

- `get_positions(category, Some(symbol))` remains a single point query for the S-6 safety gate.
- `get_positions(category, None)` now performs a full scan using `settleCoin=USDT`, `limit=200`, and `nextPageCursor` until empty.
- Cursor non-advance and page-cap exceed are client-side invariant failures, surfaced as `BybitApiError::Other`.
- `BybitApiError::Other` is explicitly classified at dispatch/sync callsites, not left as a wildcard accident.
- D2 ghost converge audit now marks dispatch-stage observation as `confirmed=false` and `removed_position_semantics="dispatched-not-confirmed"`.
- Bybit reference doc now states the point-query/full-scan contract.

Verification:

- `cargo check -p openclaw_engine --lib` = PASS with 3 pre-existing warnings
- `cargo test -p openclaw_engine --lib cursor -- --nocapture` = 9 passed
- `cargo test -p openclaw_engine --lib test_classify_client_side_invariant_error -- --nocapture` = 1 passed
- `cargo test -p openclaw_engine --lib map_client_side_invariant_to_transport -- --nocapture` = 1 passed
- `cargo test -p openclaw_engine --lib position_reconciler -- --nocapture` = 81 passed

## 3. GUI/QC Fix Pack

Committed as `b85ac3f3`.

Changes:

- Earn stake response with `submitted=true` and `wave_d_pending=true` now shows a warning state instead of complete-success green toast.
- Settings config mutation now uses `classifyLiveMutation` and persistent residual-risk banner semantics.
- System paper start/stop no longer flips local UI state unless the backend call returns a truthy result.
- Strategy confluence config built from DB/TOML params now validates before use and falls back to the existing verified default profile on invalid weights. `bb_breakout.confluence_as_gate` semantics are preserved on fallback.

Verification:

- `node --check program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/earn-tab.js`
- VM parse of inline scripts in `tab-settings.html` and `tab-system.html`
- `cargo test -p openclaw_engine --lib confluence -- --nocapture` = 52 passed
- `cargo test -p openclaw_engine --lib strategy_params -- --nocapture` = 16 passed
- `cargo test -p openclaw_engine --lib ma_crossover -- --nocapture` = 72 passed
- `cargo test -p openclaw_engine --lib bb_reversion -- --nocapture` = 50 passed
- `cargo test -p openclaw_engine --lib bb_breakout -- --nocapture` = 89 passed
- `git diff --cached --check` = PASS before commit
- `cargo check -p openclaw_engine --lib` = PASS with the same 3 pre-existing warnings

## 4. Reports And Memory Triage

I did not bulk-stage the raw 2026-05-30 report/memory WIP from the original dirty worktree.

Reasons:

- `docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-30--v104_real_file_gate2b_dry_run.md` is stale for integration: it missed the real `time_interval` Guard C blocker found by this run.
- The E1 reconciler report describes the earlier branch state; this run completed missing dictionary/audit semantics/error classification in a new integration commit.
- E4 first-pass and deep-dive reports conflict on whether dispatch retry remained a P1. They need consolidation before becoming durable memory.
- The root-level `2026-05-30--cold_audit_pm_final.md` is in the wrong location for canonical reports.
- Operator duplicate copies should only be added when byte-identical canonical report mirroring is intentionally required.

Canonical closure artifacts from this run:

- `TODO.md` v86 active state update
- `docs/CCAgentWorkSpace/PM/memory.md` durable PM lesson
- this report

## Next Action

Run E2/E4/QA review on `integration/pm-1-4`, then decide whether to push to `origin/main` and perform a Linux rebuild/restart. Do not treat source integration as runtime deployment.
