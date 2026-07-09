# Phase 1b B-3B Close-Maker Healthchecks

- Date: 2026-05-16
- Bound role: E1(worker)
- Workgroup: B-3B / Phase 1b close-maker healthcheck observability
- Scope: source/test only; no deploy, no SQL apply, no Rust edits, no commit/push.

## Summary

Implemented the V094 close-maker healthcheck module under the active runner slots `[70]`-`[73]`, preserving the frozen V094 semantics without registering literal `[62]`-`[65]`.

New active registrations:

- `[70] close_maker_fill_rate`: 24h Wilson CI fill-rate gate, plus MIT-AC-19 diagnostic strategy x symbol weak-cell output.
- `[71] close_maker_zero_spine_lineage`: W-C Caveat 2 guard for zero close-path spine rows.
- `[72] close_maker_fallback_null_ladder`: fallback enum / `close_maker_attempt` NULL-ladder / JSON audit completeness, plus MIT-AC-19 diagnostic reject/fallback samples by strategy x symbol.
- `[73] close_maker_rate_limit_backoff_coverage`: per-symbol/global rate-limit scope coverage and pause pressure thresholds.

Missing V094 schema behavior:

- Before V094 is expected: `WARN` with `NEEDS_SCHEMA`.
- After V094 is expected via `_sqlx_migrations.version >= 94`, or when `OPENCLAW_CLOSE_MAKER_HEALTH_REQUIRED=1`: `FAIL` with `V094_EXPECTED_SCHEMA_MISSING`.

## Files Changed

- `helper_scripts/db/passive_wait_healthcheck/checks_close_maker_audit.py` new module.
- `helper_scripts/db/passive_wait_healthcheck/runner.py` imports and registers `[70]`-`[73]`.
- `helper_scripts/db/passive_wait_healthcheck/__init__.py` re-exports the four checks.
- `helper_scripts/db/test_close_maker_audit_healthcheck.py` new unit tests and registration collision guard.

## Tests / Commands

- `git status --short --branch` → local `main...origin/main`; unrelated parallel Rust/SQL files present after implementation.
- `git log --oneline -5` → HEAD `0155dab9`.
- `./venvs/mac_dev/bin/python -m pytest helper_scripts/db/test_close_maker_audit_healthcheck.py -q` → `6 passed, 11 subtests passed`.
- `./venvs/mac_dev/bin/python -m py_compile helper_scripts/db/passive_wait_healthcheck/checks_close_maker_audit.py helper_scripts/db/passive_wait_healthcheck/runner.py helper_scripts/db/passive_wait_healthcheck/__init__.py helper_scripts/db/test_close_maker_audit_healthcheck.py` → PASS.
- `./venvs/mac_dev/bin/python -m pytest helper_scripts/db/test_chain_integrity_post_audit_4b_m3.py helper_scripts/db/test_wp03_deploy_gate_healthcheck.py helper_scripts/db/test_portfolio_resting_exposure_healthcheck.py helper_scripts/db/test_close_maker_audit_healthcheck.py -q` → `52 passed, 11 subtests passed`.
- `./venvs/mac_dev/bin/python -m pytest helper_scripts/db/test_*healthcheck.py -q` → `143 passed, 11 subtests passed`.
- `./venvs/mac_dev/bin/python -m helper_scripts.db.passive_wait_healthcheck.runner --help` → help renders with `[70]`-`[73]`; Python emitted the existing runpy warning caused by package import of `runner`.
- `rg -n "OPENCLAW_ENABLE_PAPER=1|allLiquidation|phys_lock.*live|/home/ncyu|/Users/" ...touched files...` → no matches.
- `wc -l ...touched files...` → new module 557 LOC, new test 176 LOC, runner 1356 LOC, `__init__.py` 311 LOC.
- `git diff --cached --stat` → empty; nothing staged.

## Race / Scope Notes

`git status --short` shows parallel work outside this E1 slice:

- Rust files under `rust/openclaw_engine/src/...`
- `sql/migrations/V094__fills_close_maker_audit.sql`
- `tests/migrations/test_v094_fills_close_maker_audit.py`

I did not inspect, revert, stage, clean, stash, commit, push, or modify those files. This patch only touches the owned Python healthcheck package, its tests, and this E1 report.

## Residual Risk

- The check assumes rate-limit `details->>'rate_limit_scope'` uses `global` for global pause and accepts `per_symbol`, `per-symbol`, or `symbol` for per-symbol backoff.
- Runtime DB validation was not run; this was source/test only per dispatch.

E1 IMPLEMENTATION DONE: awaiting E2 review and E4 regression.
