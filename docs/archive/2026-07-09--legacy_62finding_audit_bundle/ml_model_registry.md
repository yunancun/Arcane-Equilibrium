# ML and Model Registry Audit

Created: 2026-04-28
Status: complete for this audit slice

## Scope

This segment reviewed non-test ML/model-registry runtime and operator paths:

- Edge predictor feature capture, ONNX trio loading, schema/version/definition hashes, null fallback, hot swap, age gates, and shadow-fill handling.
- `learning.model_registry` schema, Python writer, Control API resolver/promote routes, canary promoter, and Rust registry resolver.
- Decision-feature writes, label backfill, training-data loading, quantile ONNX export, and artifact registration under `program_code/ml_training`.
- LinUCB arm-space definitions, runtime selection, PG state IO, batch reward trainer, and active-version/migration scaffolding.
- Shadow/decision-feature/label integrity for training rows.

Tests were excluded from the review except where static search output identified test-only call sites. No live database, exchange account, or model artifact was loaded.

## Reviewed Runtime Paths

- `rust/openclaw_engine/src/edge_predictor/mod.rs`
- `rust/openclaw_engine/src/edge_predictor/features.rs`
- `rust/openclaw_engine/src/edge_predictor/feature_builder.rs`
- `rust/openclaw_engine/src/edge_predictor/gate.rs`
- `rust/openclaw_engine/src/edge_predictor/null_backend.rs`
- `rust/openclaw_engine/src/edge_predictor/ort_backend.rs`
- `rust/openclaw_engine/src/event_consumer/handlers/edge_predictor.rs`
- `rust/openclaw_engine/src/intent_processor/mod.rs`
- `rust/openclaw_engine/src/database/decision_feature_writer.rs`
- `rust/openclaw_engine/src/database/shadow_fill_writer.rs`
- `rust/openclaw_engine/src/ml/registry.rs`
- `rust/openclaw_engine/src/ml/model_manager.rs`
- `rust/openclaw_engine/src/ml/scorer.rs`
- `rust/openclaw_engine/src/linucb/runtime.rs`
- `rust/openclaw_engine/src/linucb/state_io.rs`
- `rust/openclaw_engine/src/linucb/arms_v1_15.rs`
- `rust/openclaw_engine/src/decision_context_producer.rs`
- `rust/openclaw_engine/src/main.rs`
- `program_code/ml_training/run_training_pipeline.py`
- `program_code/ml_training/parquet_etl.py`
- `program_code/ml_training/onnx_exporter.py`
- `program_code/ml_training/model_registry.py`
- `program_code/ml_training/canary_promoter.py`
- `program_code/ml_training/edge_label_backfill.py`
- `program_code/ml_training/linucb_trainer.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/ml_routes.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/engine_capabilities_routes.py`
- `sql/migrations/V017__edge_predictor_tables.sql`
- `sql/migrations/V023__model_registry.sql`

## Flow Summary

Decision feature rows are emitted before the edge predictor short-circuit, so the system collects `learning.decision_features` even while `use_edge_predictor=false`. The writer stores schema/version hashes and JSONB features; `edge_label_backfill.py` later joins fills to populate labels; `parquet_etl.load_training_data()` consumes labeled rows for the quantile training path. Training exports q10/q50/q90 ONNX artifacts, stamps metadata, writes `_current` symlinks, and registers one `learning.model_registry` row per quantile when the verdict is not `no_ship`.

The live edge predictor runtime is an `EdgePredictorStore` per engine. Default builds use the null backend and fall back to the legacy shrinkage gate. With `edge_predictor_ort`, `ReloadEdgePredictor` can load a q50 path, derive q10/q90 sibling paths, validate metadata, then hot-swap the strategy slot. Stale, missing, schema-mismatched, or inference-failing models fall back according to `edge_predictor.fallback_on_error`, which defaults to shrinkage.

The model registry is mostly a catalog/control plane. Python registry routes and canary promoter mutate `learning.model_registry`; Rust has a resolver helper, but the reviewed hot-reload path still accepts a filesystem path and calls the ONNX loader directly. Registry promotion state is therefore not yet an enforced serving contract.

LinUCB is currently observation/metadata oriented. The Rust runtime cold-starts v1_15 arms at boot and writes arm metadata into decision contexts for a limited signal-rule mapping. Batch Python training is intended to rebuild `learning.linucb_state`, but the reviewed runtime path does not warm-start from that state.

## Findings

### MLM-001

Severity: P1
Status: open
Area: Edge predictor schema/version hash enforcement
Files:

- `rust/openclaw_engine/src/edge_predictor/features.rs`
- `rust/openclaw_engine/src/edge_predictor/ort_backend.rs`
- `program_code/ml_training/run_training_pipeline.py`
- `program_code/ml_training/onnx_exporter.py`

Summary:

The ONNX loader extracts and stores `edge_p3_feature_definition_hash`, but it never compares that artifact hash to the runtime `feature_definition_hash()`. The training pipeline also stamps `feature_definition_hash` as the feature-schema hash, so feature formula/window drift can pass the loader as long as the ordered feature names stay unchanged.

Evidence:

- `features.rs:107-111` defines `feature_definition_hash()` as an alias of `feature_schema_hash()`.
- `ort_backend.rs:50-60` defines metadata keys including `edge_p3_feature_definition_hash`, and `ort_backend.rs:100-109` extracts the definition hash from the ONNX file.
- `ort_backend.rs:150-171` validates only `schema_hash`, `schema_version`, and `n_features` against runtime values.
- `ort_backend.rs:315-342` checks that q10/q50/q90 agree with each other on `definition_hash`, but not that the trio matches runtime feature definitions.
- `run_training_pipeline.py:336-341` passes `feature_definition_hash=train_result.feature_schema_hash`.
- `onnx_exporter.py:332-335` stamps `_META_DEFINITION_HASH` from that value.

Impact:

A model trained with changed feature formulas, time windows, or normalization can be served against the current Rust feature builder if the feature-name list did not change. This defeats the intended semantic hash guard and can produce silent train/serve skew while the loader reports success.

Trigger:

Change the definition of an existing feature, such as ATR windowing, funding-window logic, or confluence scoring, without renaming/reordering the feature list; then export and reload an ONNX trio.

Recommended fix:

Make feature-definition hashing real on both sides. Compute a deterministic definition hash from the runtime feature formulas/windows, stamp that value during training, and fail ONNX load when artifact definition hash differs from `edge_predictor::features::feature_definition_hash()`. Keep the schema-name hash as a separate dimension/order guard.

Verification:

Static trace only. Add a loader test with matching schema hash but mismatched definition hash and assert the trio is rejected.

### MLM-002

Severity: P1
Status: open
Area: Model registry canary state / ONNX trio atomicity
Files:

- `sql/migrations/V023__model_registry.sql`
- `program_code/ml_training/model_registry.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/ml_routes.py`
- `rust/openclaw_engine/src/edge_predictor/ort_backend.rs`

Summary:

`learning.model_registry` promotes one quantile row at a time, but the runtime loading unit is a q10/q50/q90 trio derived from the q50 path. A q50 row can become `production` while q10/q90 sibling rows remain `shadow`, `rejected`, or stale, yet loading q50 will still pull the sibling files from disk.

Evidence:

- `V023__model_registry.sql:103-105` stores a single `quantile` per row, and `V023__model_registry.sql:136-140` makes `(strategy, engine_mode, quantile, schema_version, train_date)` the unique key.
- `model_registry.py:300-324` registers q10, q50, and q90 by iterating quantile entries and inserting/updating separate rows.
- `model_registry.py:330-336` defines `transition_canary_status(row_id=...)`, and `model_registry.py:390-417` updates only that row's `canary_status`.
- `ml_routes.py:328-379` exposes promotion as a single `row_id` transition.
- `ml_routes.py:256-291` resolves a single quantile row, defaulting the request surface to q50.
- `ort_backend.rs:264-276` loads q10 and q90 by deriving sibling filenames from the q50 artifact path.

Impact:

Registry state can say only one quantile is promoted, while runtime inference consumes all three artifacts. Operators can accidentally serve an unpromoted or rejected sibling quantile, and registry/UI state will not accurately describe the model actually loaded into the predictor gate.

Trigger:

Promote only the q50 registry row for a strategy/engine/train_date, then reload the q50 artifact path with the ORT backend enabled.

Recommended fix:

Make the registry transition unit match the serving unit. Either store one trio row with three artifact paths and one canary state, or enforce transactional q10/q50/q90 state transitions keyed by a shared `model_id`/train_date. The resolver/reload path should require all three quantiles to have the same model id, train date, verdict, and eligible canary state before loading.

Verification:

Static trace only. Add registry tests that attempt a single-row q50 promotion and assert the API rejects it or atomically updates all trio rows.

### MLM-003

Severity: P1
Status: open
Area: Decision-feature schema drift in training data
Files:

- `sql/migrations/V017__edge_predictor_tables.sql`
- `rust/openclaw_engine/src/database/decision_feature_writer.rs`
- `program_code/ml_training/parquet_etl.py`
- `program_code/ml_training/quantile_trainer.py`
- `program_code/ml_training/run_training_pipeline.py`

Summary:

Training data loading ignores the per-row schema/version/definition hashes stored in `learning.decision_features` and zero-fills missing or malformed feature keys. The quantile trainer then stamps the current feature-name hash onto the output model, even if some training rows were produced by an older or malformed feature contract.

Evidence:

- `V017__edge_predictor_tables.sql:36-39` defines `feature_schema_version`, `feature_schema_hash`, and `feature_definition_hash` as non-null row metadata.
- `decision_feature_writer.rs:116-131` writes those three hashes alongside each `features_jsonb` payload.
- `parquet_etl.py:402-417` selects `context_id`, `ts_ms`, `features_jsonb`, label, symbol, and strategy, but not the stored schema/version/definition hashes.
- `parquet_etl.py:432-435` documents that missing/non-numeric JSON fields stay in the dataset and that schema mismatch checking is deferred to Rust inference.
- `parquet_etl.py:494-506` converts every configured feature name, defaulting absent, null, or invalid values to `0.0`.
- `quantile_trainer.py:652-654` computes the model `feature_schema_hash` from the current `feature_names`, and `run_training_pipeline.py:336-341` stamps that hash into ONNX metadata.

Impact:

After a feature contract change or a writer regression, older rows can silently enter the current training set with zero-filled columns. The resulting ONNX artifact advertises the current schema hash even though its training distribution may contain mixed-schema samples. Runtime hash checks will not catch this because the artifact metadata was stamped from the current name list, not from row-level provenance.

Trigger:

Train after `learning.decision_features` contains labeled rows from an older `feature_schema_hash` or rows whose JSONB lacks one or more current feature names.

Recommended fix:

Filter training rows by exact `feature_schema_version`, `feature_schema_hash`, and `feature_definition_hash` before materializing arrays. Treat missing required feature keys as row rejects, not zeros, unless an explicit migration/backfill produced those zeros and stamped a new definition hash. Include rejected-row counts and hash distribution in the acceptance report.

Verification:

Static trace only. Add a loader test with mixed hash rows and missing feature keys; assert only matching, complete rows are trainable.

### MLM-004

Severity: P1
Status: open
Area: Label backfill finality / partial close integrity
Files:

- `program_code/ml_training/edge_label_backfill.py`

Summary:

The label backfill marks a decision feature row as permanently labeled after any close fill exists. It does not require the position to be fully closed or `total_close_qty` to match the entry quantity, so partial exits can become final training labels and later closes are ignored.

Evidence:

- `edge_label_backfill.py:141-152` selects unlabeled entries when any fill exists with `entry_context_id = l.context_id`.
- `edge_label_backfill.py:196-206` aggregates current close fills but does not compare `SUM(close_qty)` with the entry fill quantity.
- `edge_label_backfill.py:223-228` computes `label_net_edge_bps` by normalizing current realized PnL and fees by full entry notional.
- `edge_label_backfill.py:238-247` writes the label and sets `label_filled_at = now()`.
- `edge_label_backfill.py:142-145` makes future backfill passes skip rows whose `label_filled_at` is already set.

Impact:

Partial take-profit, partial stop, reduce-only, or split-close flows can train the edge predictor on incomplete trade outcomes. The label can be biased toward the first partial exit, normalized by the full entry notional, and the rest of the lifecycle cannot correct it because the row is no longer eligible for backfill.

Trigger:

Any entry receives one close fill while part of the position remains open, then a later close fill realizes the remaining PnL.

Recommended fix:

Make backfill finality explicit. Require full close quantity coverage before setting `label_filled_at`, or introduce provisional labels that are recomputed until the entry is fully closed. Persist `total_close_qty`, `entry_qty`, and a completion flag for auditability, and include a replay path for rows already labeled from partial closes.

Verification:

Static trace only. Add a DB-level or SQL-unit fixture with one entry and two partial closes; assert the first pass does not finalize the label until the second close is present.

### MLM-005

Severity: P1
Status: open
Area: LinUCB state persistence / reward feedback / arm-space versioning
Files:

- `rust/openclaw_engine/src/linucb/arms_v1_15.rs`
- `rust/openclaw_engine/src/linucb/runtime.rs`
- `rust/openclaw_engine/src/linucb/state_io.rs`
- `rust/openclaw_engine/src/main.rs`
- `program_code/ml_training/linucb_trainer.py`

Summary:

LinUCB is not an end-to-end persisted reward loop. Rust always starts with cold v1_15 arms, the Python batch trainer enumerates a different v1_15 arm space than Rust, and its reward query uses PostgreSQL `$2` placeholders inside a psycopg2 query. Even if the trainer writes state, the reviewed runtime path does not load it.

Evidence:

- `arms_v1_15.rs:12-26` defines Rust v1_15 as strategies `ma_crossover`, `bb_breakout`, `bb_reversion`, `grid_trading`, `funding_arb` across regimes `trending`, `mean_reverting`, `random_walk`.
- `linucb_trainer.py:293-309` defines Python v1_15 as strategies `ma_crossover`, `bb_reversion`, `bb_breakout`, `grid_trading`, `donchian_breakout` across regimes `trending`, `ranging`, `volatile`.
- `linucb_trainer.py:212-219` builds a psycopg2 SQL string with `$2::BIGINT` placeholders, while `linucb_trainer.py:223` executes it with psycopg2 parameters.
- `linucb_trainer.py:320-325` catches observation-fetch failures per arm and continues, so this can quietly yield no trained arms.
- `state_io.rs:85-89` and `state_io.rs:146-151` implement PG load/upsert helpers, and `state_io.rs:184-203` can read the active arm-space version.
- `main.rs:607-612` constructs and logs `LinUcbRuntime::cold_start_v1_15()` at startup instead of loading the active version from `learning.linucb_state`.

Impact:

LinUCB telemetry, reward training, dashboard state, and runtime arm selection can all describe different arm spaces or state vintages. Reward feedback may fail before writing state; if it succeeds, Rust still uses identity-prior cold arms, so learned A/b matrices and migration rows do not affect runtime selection metadata.

Trigger:

Run `program_code/ml_training/linucb_trainer.py` against logged decision contexts, then restart the engine and inspect runtime LinUCB selections or `learning.linucb_state` pull counts.

Recommended fix:

Create one shared arm-space manifest for Rust and Python, or generate both sides from the same source. Fix the trainer SQL placeholders to psycopg2 `%s` style. At engine boot, read `current_active_version()`, `load_arms()` with the runtime schema hash, and only cold-start under an explicit, logged fallback when no compatible state exists.

Verification:

Static trace only. Add an integration test that trains one arm into `learning.linucb_state`, restarts/constructs the runtime from PG, and verifies the selected arm's UCB reflects the persisted A/b state.
