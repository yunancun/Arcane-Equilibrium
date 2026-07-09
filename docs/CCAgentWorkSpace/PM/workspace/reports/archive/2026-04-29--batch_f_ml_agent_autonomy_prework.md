# Batch F ML / Agent Autonomy Readiness Prework

Date: 2026-04-29 CEST
Owner: PM
Status: F0 prework complete; implementation not started

## Decision

Batch F is now the only open remediation batch in the tracking ledger. This report completes F0 prework only; it does not start code implementation.

Facts:

- B, C, D, and E are tracked as fixed locally, uncommitted, and not deployed.
- A is also fixed locally from the earlier sign-off path.
- F remains open.
- The worktree is still broadly dirty, so F implementation must preserve all existing batch edits.

PM call:

- F implementation may start in the next execution step under the required ML/data chain.
- Do not mix F code with unrelated cleanup, deploy, commit, or branch operations.
- Keep ML / Teacher / Strategist / LinUCB paths observation-only, explicitly disabled, or explicitly bounded until F implementation, E2 review, and E4 verification are complete.

## Scope

Batch F closes 10 findings:

| ID | Severity | Area | PM intent |
| --- | --- | --- | --- |
| `MLM-001` | P1 | Feature definition hash | Enforce real train/serve feature-definition compatibility. |
| `MLM-002` | P1 | Model registry trio atomicity | Make q10/q50/q90 one serving contract. |
| `MLM-003` | P1 | Training row schema drift | Train only on matching complete row-level schema/hash data. |
| `MLM-004` | P1 | Label finality | Do not finalize labels on partial closes. |
| `MLM-005` | P1 | LinUCB reward/state loop | Align arm space, trainer reward query, and runtime state loading. |
| `SADF-001` | P1 | Teacher directive routing | Route directives to explicit active targets; disabled Paper must reject with response. |
| `SADF-004` | P2 | LinUCB metadata fidelity | Stop representing signal-level metadata as accepted-intent decision evidence. |
| `SADF-005` | P2 | `boost_arm` audit truth | Return non-success until real LinUCB mutation exists. |
| `SADF-006` | P3 | Strategist Live scaffold | Add release-mode guard before Live promotion/metrics can be trusted. |
| `LP-003` | P3 | Paper auto-start script | Update or retire stale Paper auto-start path. |

Relevant root principles:

- #3 AI output is not an immediate command.
- #6 failure defaults to contraction.
- #7 learning must not rewrite Live.
- #8 every trading decision must be reconstructable.
- #10 reports must distinguish fact, inference, and assumption.
- #12 learning is allowed, but only with coherent feedback contracts.

## Dirty-File Collision Map

The following Batch F-relevant files are already dirty before F implementation:

- `helper_scripts/start_paper_trading.sh`
- `helper_scripts/deploy/README.md`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/ml_routes.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/paper_trading_routes.py`
- `rust/openclaw_engine/src/database/decision_feature_writer.rs`
- `rust/openclaw_engine/src/main.rs`
- `rust/openclaw_engine/src/tick_pipeline/on_tick/step_3_signals.rs`

PM constraint:

- F workers must read these diffs before editing.
- F implementation must not overwrite Batch B/C/D/E changes in those files.
- `SADF-001` and `SADF-006` should be implemented after reading the Batch D risk/config changes because they touch adjacent strategy command and promotion behavior.

## Workstream Plan

Required chain for implementation:

- PM -> QC(default) + MIT(default) + AI-E(default) + PA(default) -> E1/E1a(worker) -> E2(explorer) -> E4(worker) -> QA(worker) -> PM

No sub-agents were dispatched during F0. The chain below is the dispatch plan for the later implementation pass.

### F-A Autonomy Containment

Findings: `SADF-001`, `SADF-005`, `SADF-006`, `LP-003`

Owners:

- PA(default): target semantics and guard design.
- QC(default): confirms no autonomy path becomes authoritative accidentally.
- E1(worker): Rust Teacher / Strategist / Paper command target changes.
- E1a(worker): Paper startup script and deploy docs.

Exit:

- Teacher directives have explicit active target selection.
- Disabled Paper command path returns a response instead of drain-dropping oneshot commands.
- `boost_arm` is persisted as skipped / unsupported / non-success until real arm mutation exists.
- Strategist Live promotion and Live metrics fail fast in release mode unless explicitly supported.
- Paper startup script is either retired or requires `OPENCLAW_ENABLE_PAPER=1` plus current response-shape checks.

### F-B ML Schema And Label Hygiene

Findings: `MLM-001`, `MLM-003`, `MLM-004`

Owners:

- MIT(default): feature contract, training-row eligibility, label-finality acceptance criteria.
- E1(worker): Rust feature-definition hash and ONNX loader enforcement.
- E1a(worker): Python training, ETL, exporter, and label backfill changes.

Exit:

- Runtime and training compute a real feature-definition hash, separate from feature-name schema hash.
- ONNX loading rejects matching-name but mismatched-definition artifacts.
- Training data selection filters by exact row-level schema version, schema hash, and definition hash.
- Missing/malformed feature JSON rows are rejected unless explicitly migrated.
- Label backfill does not set final `label_filled_at` until full close quantity coverage is known, or it writes clearly provisional labels that can be recomputed.

### F-C Model Registry Serving Unit

Finding: `MLM-002`

Owners:

- MIT(default): serving-unit contract.
- PA(default): migration/API compatibility plan.
- E1a(worker): registry/API/training registration implementation.
- E1(worker): Rust resolver / loader integration if runtime starts resolving through registry.

Exit:

- Operator cannot promote only q50 while runtime implicitly consumes q10/q50/q90.
- Registry transition is atomic for the trio, or a single serving-unit row owns all three artifact paths.
- Loader/resolver requires all three quantiles to share compatible identity, train date, verdict, and canary state.

### F-D LinUCB Coherent Loop

Findings: `MLM-005`, `SADF-004`

Owners:

- QC(default): arm/reward semantics and whether LinUCB remains observation-only.
- MIT(default): shared arm-space manifest and state schema compatibility.
- E1(worker): Rust LinUCB runtime/state load and accepted-intent metadata boundary.
- E1a(worker): Python trainer SQL and arm-space generation.

PM default decision for F implementation:

- Keep LinUCB non-authoritative unless QC and MIT explicitly approve promotion.
- If staying observation-only, mark it as observation-only in persisted/reporting surfaces and prevent downstream code from treating it as accepted order evidence.
- If wiring accepted-intent metadata, do it only after arm-space/state loading is coherent.

Exit:

- Rust and Python use one arm-space manifest or generated source.
- Python trainer SQL placeholders are compatible with psycopg2.
- Runtime loads active compatible `learning.linucb_state` at boot, with cold-start only as explicit logged fallback.
- Metadata is either tied to accepted `OrderIntent.strategy` after gates or clearly labeled as signal-level observation telemetry.

## Verification Plan

Minimum local verification for F implementation:

- `git diff --check`
- `cargo check -p openclaw_engine --manifest-path rust/Cargo.toml`
- Targeted Rust tests:
  - `cargo test -p openclaw_engine --manifest-path rust/Cargo.toml edge_predictor --lib`
  - `cargo test -p openclaw_engine --manifest-path rust/Cargo.toml linucb --lib`
  - `cargo test -p openclaw_engine --manifest-path rust/Cargo.toml intent_processor --lib`
  - `cargo test -p openclaw_engine --manifest-path rust/Cargo.toml teacher --lib`
  - `cargo test -p openclaw_engine --manifest-path rust/Cargo.toml strategist_scheduler --lib`
- Python syntax:
  - `python -m py_compile program_code/ml_training/*.py program_code/exchange_connectors/bybit_connector/control_api_v1/app/ml_routes.py`
- Targeted Python tests:
  - `program_code/ml_training/tests/test_onnx_exporter_quantile.py`
  - `program_code/ml_training/tests/test_model_registry.py`
  - `program_code/ml_training/tests/test_parquet_etl.py`
  - `program_code/ml_training/tests/test_quantile_trainer.py`
  - `program_code/ml_training/tests/test_edge_label_backfill.py`
  - `program_code/ml_training/tests/test_linucb_trainer.py`
  - `program_code/ml_training/tests/test_run_training_pipeline.py`
- Static sweeps:
  - no q50-only production promotion path
  - no `boost_arm` persisted as success without mutation
  - no training zero-fill for missing required current features
  - no Paper auto-start claim without `OPENCLAW_ENABLE_PAPER=1`

Linux `trade-core` verification remains required before any deploy. F0 does not deploy or restart anything.

## Open Gates Before F Implementation

1. Preserve current B/C/D/E dirty changes; do not overwrite the collision files listed above.
2. PM must choose final model-registry shape: atomic trio transitions on existing per-quantile rows versus new serving-unit row.
3. QC/MIT must confirm whether LinUCB remains observation-only or starts producing accepted-intent metadata in this batch.
4. E2/E4 must be separate from implementation.
5. No deploy/restart until all 62 findings are fixed, verified, committed, pushed, and Linux `trade-core` checks are green.

## Estimate

Using the existing six-batch schedule:

- optimistic: 5 days
- median: 8 days
- pessimistic: 12 days

Risk is highest in `MLM-005` because it spans Rust runtime, Python trainer, DB state, and decision metadata semantics.

## PM Status

PM SIGN-OFF: CONDITIONAL

Condition:

- Batch F implementation can start next only with explicit scope ownership and dirty-file preservation. F0 itself is complete.
