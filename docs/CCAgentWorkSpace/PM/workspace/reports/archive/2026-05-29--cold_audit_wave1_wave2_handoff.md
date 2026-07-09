# Cold Audit Wave1/Wave2 PM Handoff

Date: 2026-05-29. Owner: PM(default). Repo root: `/Users/ncyu/Projects/TradeBot/srv`.

## Status

Two local source checkpoints exist:

- `b93d3210` — Wave1 PkgA/PkgB: live-auth truthfulness, live session readback, Rust-authority cancel-all, create-order fail-closed retry policy, Bybit stop/amend/rate-limit/LiveDemo credential semantics.
- `11b9531f` — Wave2 PkgC/PkgD: edge evidence freshness, paper promotion freeze, stub backtest guard, AI route/cost/model-registry lineage.

These are source checkpoints only. They have not been deployed or loaded into the Linux runtime binary.

## Verification Recorded

- Wave1 commit records E2/A3/E4 green: Python control API `4229 + 18` pass pattern and Rust `3584/0`.
- Wave2 commit records E2/E4 green: Rust `3599/0`, AI lineage `42/0`, promotion/backtest pass.
- PM handoff rerun on Mac after TODO/doc sync:
  - `cargo test -p openclaw_engine --lib` from `rust/`: `3598 passed / 0 failed / 1 ignored`.
  - `PYTHONPATH=. OPENCLAW_CSRF_SHADOW=1 python3 -m pytest ...test_api_contract.py ...test_session_stop_cancel_verify.py ...test_promotion_pipeline.py ...test_backtest_routes.py`: `93 passed`.
  - `python3 -m pytest` for bybit_thought_gate + model_registry focused tests: `42 passed`.
  - First control API attempt from the subdirectory failed with `ModuleNotFoundError: program_code`; rerun from repo root fixed the invocation artifact.
- Current doc-sync quick checks:
  - `SPECIFICATION_REGISTER.md` active-path check: `0` missing paths after ADR-0036..0041 corrections.
  - Operator mirrors for PkgB/PkgC are byte-identical to PA canonical reports (`cmp=0`).

## PM Decisions

- `P1-LEARNING-CLOSE-MAKER-AUDIT-TABLE-MISSING` is closed as spec drift, not a bug. Canonical close-maker evidence is V094 `trading.fills.close_maker_attempt` + `close_maker_fallback_reason`; the missing `learning.close_maker_audit` table has no writer or reader and must not be created as dead schema.
- PkgB remains source-done but not fully deployment-cleared until a Bybit-facing BB-style spot-check is recorded.
- PkgD remains source-done but not deployment-cleared until Linux PG empirical verification covers durable ledger idempotency / `ON CONFLICT` behavior.

## Next Actions

1. Run BB-style pre-deploy spot-check for PkgB against Bybit V5 semantics.
2. Run Linux PG empirical check for PkgD ledger idempotency before deploy.
3. Finish P1-16 Alpha/M11 Stage A-vs-Stage B doc split and scaffold `promotion_evidence=false` marker.
4. Keep P2-06/P2-07 as deferred evidence-writer / cohort-replay follow-ups.
