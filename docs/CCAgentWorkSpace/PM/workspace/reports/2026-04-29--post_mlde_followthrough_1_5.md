# Post-MLDE Follow-Through 1-5

Date: 2026-04-29 19:26 CEST

## Scope

Operator asked to execute the recommended 1-5 follow-through after the latest repair round:

1. `[37] mlde_demo_applier` follow-through.
2. `[33] maker_fill_rate` RCA / immediate fix.
3. `[12] bb_breakout` Phase 2 sweep / 5m evaluation.
4. G8-01 W2/W3 tests.
5. Low-priority maintenance items that are safe now.

No sub-agents were used because this Codex turn did not have explicit operator authorization to spawn agents. PM executed a shortened local PA/E1/E2/E4/QA loop.

## Results

- `[37]` root cause was not schema/deploy failure. Runtime had V031/V032 applied and recent shadow rows, but no recommendation met `min_confidence=0.35` + `min_samples=5`, so the applier produced no application audit rows. Fix: `mlde_demo_applier` now records a deduped `status=skipped`, `reason=no_eligible_recommendations` row when it runs with zero eligible candidates.
- `[33]` recent fills already show maker-like settlement improving, but `trading.orders.time_in_force` was never persisted, so PostOnly diagnostics stayed at 0%. Fix: order audit rows now persist `time_in_force`; intent details now include `time_in_force`, `post_only`, `maker_timeout_ms`, and `limit_price`.
- `[12]` 5m sweep was run on Linux over 14d / 5 symbols. Only 24 of 84 combos had at least 20 signals. Best 5m fwd6 (30min) raw mean was about +8bps with t-stat 0.62; high-sample combos were mostly negative. Verdict: no runtime timeframe switch.
- G8-01 W2/W3 were stale TODO entries. Existing W2 has 26 CognitiveModulator unit cases; existing W3 has 8 Strategist integration scenarios. Targeted pytest passed.
- Maintenance: `verify_ipc_token` now rejects empty secrets even when the HMAC token matches an empty key. `G3-09-PA-DOCSTRING-CLARIFY` was already fixed in code; TODO was stale and is marked complete.

## Verification

- `python3 -m pytest -q program_code/ml_training/tests/test_mlde_demo_applier.py helper_scripts/db/test_mlde_healthchecks.py helper_scripts/db/test_maker_fill_rate.py` → 26 passed.
- `python3 -m pytest -q .../test_cognitive_modulator_coverage.py .../test_strategist_cognitive_integration.py .../test_g8_01_fup_losses_wiring.py` → 42 passed.
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_engine --lib verify_ipc_token` → 5 passed.
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_engine --lib pending_registration_order_type_tests` → 8 passed.
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_engine --lib test_persist_intent_helper` → 2 passed.

Coverage note: this local Python environment lacks `pytest-cov` and `coverage.py`, so W2 coverage was not regenerated in this turn. Existing Wave B sign-off records W2 at 100% coverage.

## Boundaries

- No live/live_demo autonomous application path was added.
- No risk parameter or strategy parameter was loosened.
- `[12]` sweep stayed read-only.
- Live parameter mutation remains gated by GovernanceHub, Decision Lease, and the existing live gates.
