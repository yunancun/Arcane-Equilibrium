# Batch F ML / Agent Autonomy Readiness Sign-off

Date: 2026-04-29 CEST
Owner: PM
Status: fixed locally, uncommitted

## Scope

Batch F closes 10 findings:

- `MLM-001`
- `MLM-002`
- `MLM-003`
- `MLM-004`
- `MLM-005`
- `SADF-001`
- `SADF-004`
- `SADF-005`
- `SADF-006`
- `LP-003`

Execution note:

- No sub-agents were dispatched in this implementation pass. The worktree already contained broad A-E dirty changes in adjacent files, so PM kept ownership local to preserve existing diffs and avoid cross-worker collisions.
- Effective chain: PM(local) -> QC/MIT/PA local review -> E1/E1a implementation -> E4 targeted verification -> PM sign-off.

## Changes

- Feature compatibility now has two independent contracts:
  - schema hash for feature names/order.
  - definition hash for feature semantics.
- Runtime ONNX metadata validation rejects artifacts whose feature-definition hash drifts from the runtime definition.
- Training ETL now filters by row-level `feature_schema_version`, `feature_schema_hash`, and `feature_definition_hash`; malformed or missing feature JSON rows are rejected instead of silently zero-filled.
- Quantile training/export/reporting now carries `feature_definition_hash`.
- Model registry canary transition now promotes a q10/q50/q90 serving trio atomically for one `(strategy, engine_mode, schema_version, train_date)` unit.
- `model_info` rejects incomplete serving trios instead of reporting a lone quantile as active.
- Edge label backfill finalizes labels only when close quantity fully covers the entry quantity.
- LinUCB Python trainer now uses the Rust-aligned 15-arm space and psycopg-compatible SQL placeholders.
- LinUCB runtime now warm-starts from compatible `learning.linucb_state`, with explicit cold-start fallback when state is missing or incompatible.
- Teacher command routing no longer defaults to Paper:
  - command sink defaults to Demo.
  - disabled Paper drains response-bearing commands with explicit errors instead of silently dropping oneshot responders.
- Decision payloads mark LinUCB metadata as `signal_observation_only` and `accepted_intent_bound=false`.
- `boost_arm` now returns unsupported/invalid directive instead of a false `Applied` success.
- Strategist Live metrics path now fails fast in release mode until Live scaffold is explicitly supported.
- Paper auto-start path now requires `OPENCLAW_ENABLE_PAPER=1` and parses current API response shapes; deploy README no longer recommends automatic Paper startup through `ExecStartPost`.

## Verification

- `python3 -m py_compile program_code/ml_training/parquet_etl.py program_code/ml_training/quantile_trainer.py program_code/ml_training/quantile_reports.py program_code/ml_training/run_training_pipeline.py program_code/ml_training/model_registry.py program_code/ml_training/edge_label_backfill.py program_code/ml_training/linucb_trainer.py program_code/exchange_connectors/bybit_connector/control_api_v1/app/ml_routes.py` -> passed.
- `bash -n helper_scripts/start_paper_trading.sh` -> passed.
- `cargo check -p openclaw_engine` from `rust/` -> passed with existing warnings.
- Bundled Python targeted suite:
  - `program_code/ml_training/tests/test_parquet_etl.py`
  - `program_code/ml_training/tests/test_quantile_trainer.py`
  - `program_code/ml_training/tests/test_quantile_reports.py`
  - `program_code/ml_training/tests/test_model_registry.py`
  - `program_code/ml_training/tests/test_edge_label_backfill.py`
  - `program_code/ml_training/tests/test_linucb_trainer.py`
  - result: 78 passed, 7 skipped.
- Rust targeted tests:
  - `claude_teacher::strategy_ipc_impl::tests` -> 6 passed.
  - `boost_arm` -> 3 passed.
  - `linucb::runtime::tests` -> 11 passed.
  - `decision_context_producer::tests` -> 6 passed.
  - `edge_predictor::features::tests` -> 20 passed.
  - `edge_predictor_ort` metadata drift test -> 1 passed.

## Residual Gaps

- Not deployed, not restarted, not committed, and not pushed.
- PostgreSQL integration coverage for the model registry trio path was updated, but a live PG integration run still needs `OPENCLAW_DATABASE_URL`.
- No full real-artifact ONNX load was run; the ORT metadata mismatch test validates the new runtime guard.
- LinUCB boot warm-start is covered by unit/helper tests and compile checks, not by a live engine boot smoke.
- Existing Rust warnings remain; they were already present and not part of Batch F.

## PM Verdict

Batch F is fixed locally and the 62-finding ledger is now fully represented as fixed in the working tree. It is not production-ready until the residual integration checks above are run and the full A-F worktree is committed, pushed, deployed, and smoke-tested on the target runtime.
