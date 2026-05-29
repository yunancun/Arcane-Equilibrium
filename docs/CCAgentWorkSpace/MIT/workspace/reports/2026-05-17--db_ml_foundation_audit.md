# MIT Database / ML Foundation Audit

Audit prefix: 2026-05-17  
Actual inspection time: 2026-05-29 CEST, against repo/runtime HEAD `b964876415adabcf8c745aec8528553f4823aefe`  
Role: MIT(default), read-only audit  
Scope: database schema/migration alignment, ML feature/label/training foundations, CV/leakage controls, and ML deployment stage

## Boundary

- No code, docs, TODO, memory, runtime config, schema, or data changes were made, except this report file.
- Runtime inspection used SELECT-only/read-only commands over `ssh trade-core`, plus read-only log/status/source inspection.
- One own long-running SELECT over `learning.mlde_edge_training_rows` was cancelled with `pg_cancel_backend` after the local SSH query was terminated; no data or schema mutation was performed.

## Executive Verdict

- P0 findings: 0.
- P1 findings: 1.
- P2 findings: 3.
- P3 findings: 1.
- Current ML stage: **mixed shadow/advisory plus demo apply; live ML is blocked**.

The database foundation is no longer the empty/skeletal state from older MIT memories: `learning.decision_features` is large and fresh, labels are populated, feature baselines are being written, and scheduled training/advisory jobs are running. The blocker is the promotion foundation: current quantile/scorer training is demo-scoped, the latest shadow-only model artifacts are not represented in `learning.model_registry`, canary/production registry rows are absent, model performance/drift evidence remains empty, and replay evidence is still smoke/incomplete.

## Deployment Stage Answer

**FACT:** ML is currently at **shadow/advisory + demo apply**, not live/canary production.

Evidence:

- `program_code/ml_training/mlde_demo_applier.py:1` says the applier consumes `learning.mlde_shadow_recommendations` and applies only demo-scoped parameter changes; live/live_demo rows are never applied by this module.
- `program_code/ml_training/mlde_demo_applier.py:141` and `program_code/ml_training/mlde_demo_applier.py:179` default the applier to enabled, `engine_mode=demo`, and non-dry-run.
- Runtime `/tmp/openclaw/status/ml_training_maintenance_status.json` reported `mlde_demo_applier` OK with `engine_mode=demo`, `dry_run=0`, `applied=4`, `live_candidates=0`.
- `helper_scripts/cron/ml_training_maintenance.py:57` defaults scheduled supervised/quantile training to `demo`; `helper_scripts/cron/ml_training_maintenance.py:58` defaults shadow advisor to `demo,live_demo`.
- Runtime status showed scorer and quantile trainer runs only for `engine_mode=demo`; quantile runs ended with `verdict=shadow_only` and `model_registry_skipped`.
- Runtime SELECT showed `learning.model_registry` has `count=3`, `max(created_at)=2026-04-24 00:02:42.84884+02`, `canary_status='production' count=0`, and `canary_status='promoting' count=0`.
- `program_code/ml_training/canary_promoter.py:617` keeps auto-promotion default-off unless an explicit environment gate is enabled.

**INFERENCE:** live ML is blocked by current evidence because there is no fresh registry-backed candidate, no canary/production model row, no populated model-performance table, and the only observed non-shadow mutation path is demo parameter application.

## Runtime / Schema Snapshot

Read-only evidence commands and inspections:

- `git rev-parse HEAD`; `git status --porcelain=v1 -b`; `git ls-remote --heads origin main`.
- `ssh trade-core 'cd /home/ncyu/BybitOpenClaw/srv && git rev-parse HEAD && git status --porcelain=v1 -b'`.
- Local migration inventory over `sql/migrations/V*.sql`.
- Runtime SELECT from `_sqlx_migrations`, `information_schema.tables`, `information_schema.columns`, and aggregate SELECTs over learning/observability/replay/trading tables.
- Runtime read-only inspection of `crontab -l`, `/tmp/openclaw/status/ml_training_maintenance_status.json`, `/tmp/openclaw/logs/feature_baseline_writer_cron.log`, and cron heartbeat mtimes.

Key runtime facts:

- `_sqlx_migrations`: `max(version)=113`, `success count=105`, `total count=105`.
- Local source migrations: 106 `V###` files, min `V001`, max `V114`, no duplicate versions; missing numeric slots are historical gaps.
- Linux runtime repo HEAD equals local/origin HEAD `b964876415adabcf8c745aec8528553f4823aefe`.
- `learning.decision_features`: 11,611,272 rows; max `ts=2026-05-29 01:46:34.646+02`; `label_net_edge_bps` non-null 2,097,891; `label_close_tag` non-null 6,091,631.
- `learning.exit_features`: 2,879 rows; max `ts=2026-05-29 01:42:29.665+02`.
- `learning.mlde_shadow_recommendations`: 16,986 rows; max `ts=2026-05-28 22:57:13.902565+02`; demo 10,968; live/live_demo 6,018.
- `learning.mlde_param_applications`: 7,381 rows; max `ts=2026-05-28 22:57:09.790003+02`; status applied 1,180.
- `observability.feature_baselines`: 2,108 rows; max `created_ts=2026-05-28 04:42:34.424983+02`; 25 symbols; 34 feature names.
- `observability.drift_events`: 0 rows.
- `observability.model_performance`: 0 rows.
- `replay.experiments`: 24 rows; max `created_at=2026-05-28 18:53:51.78058+02`; completed 0; live_demo 0.
- `replay.simulated_fills`: 46 rows; max `ts=2026-05-11 12:49:00+02`; calibrated_replay 45; synthetic_replay 1.
- `replay.mlde_replay_veto_log`: 0 rows.
- `trading.fills`: 14,373 rows; max `ts=2026-05-29 01:42:29.665+02`; live_demo 3,230; live 0.
- `trading.decision_outcomes`: 2,340,600 rows; max `backfilled_ts=2026-05-29 01:43:03.200593+02`; live_demo 825,286; live 89,734.

## Foundation Matrix

| Component | Current stage | Evidence |
|---|---:|---|
| Decision feature / label store | Shadow data foundation, active | Fresh `learning.decision_features`, non-null net-edge and close-tag labels, schema/hash filters in `program_code/ml_training/parquet_etl.py:439`. |
| Exit feature store | Foundation, active but small | Fresh `learning.exit_features` with 2,879 rows. |
| Feature baseline writer | Foundation active | Cron log PASS; 2,108 baseline rows; 34/34 feature names. |
| Drift events | Foundation only | Table exists, 0 rows. |
| Model performance | Foundation only | Table exists, 0 rows. |
| Shadow advisor | Shadow/advisory | Status OK; modes demo and live_demo; 16,986 recommendations. |
| Demo applier | Demo apply | Status OK; `applied=4`; source says demo only. |
| Supervised scorer | Shadow/demo training | Runtime status OK for demo grid/MA; legacy calibration skipped. |
| Quantile trainer | Shadow/demo training | Runtime status OK for demo grid/MA; `verdict=shadow_only`; ONNX export; registry skipped. |
| Model registry / canary | Blocked/stale shadow catalogue | 3 old rows from 2026-04-24; 0 promoting/production. |
| Replay foundation | Smoke/incomplete | Cron installed; experiments have no completed/live_demo rows; simulated fills stale. |

## Findings

### MIT-DBML-001 - Fresh shadow models are not registered for canary promotion

- Classification: **FACT**
- Severity: **P1**
- Affected path+line: `program_code/ml_training/model_registry.py:17`, `program_code/ml_training/model_registry.py:139`, `program_code/ml_training/model_registry.py:201`, `program_code/ml_training/model_registry.py:332`, `program_code/ml_training/canary_promoter.py:617`
- Evidence command / inspection method: runtime status JSON showed quantile trainer `verdict=shadow_only` with `model_registry_skipped`; runtime SELECT showed `learning.model_registry count=3`, max created at 2026-04-24, and 0 promoting/production rows; source read shows registry writes can gracefully return `None` and canary transitions operate from registry rows.
- Impact: current shadow-only ONNX artifacts are not represented as fresh DB candidates, so the canary/promoter path has no current unit to promote or reject. This blocks live ML graduation even if training artifacts exist.
- Why real, not false positive: this is not just a missing production decision. The scheduled runtime status explicitly says `model_registry_skipped`, and the table timestamp is more than a month older than the current training runs. `model_registry.py` documents that skipped DB writes still let ONNX artifacts continue, so "training succeeded" does not imply "promotion foundation exists."
- Suggested fix direction: make registry persistence required for scheduled non-`no_ship` quantile artifacts in the live-readiness lane, or fail the scheduled job loudly when registry prerequisites are missing. Preserve the current shadow-only verdict semantics, but require DB catalogue lineage before any canary/promoter review.
- Fix owner role: **E1(worker)** with **PA(default)** acceptance semantics for what must be registry-backed.
- Verification owner role: **MIT(default)** for DB/runtime verification; **E4(worker)** for deployment/runtime evidence.

### MIT-DBML-002 - Scheduled supervised/quantile training is demo-only while live_demo evidence exists

- Classification: **FACT**
- Severity: **P2**
- Affected path+line: `helper_scripts/cron/ml_training_maintenance.py:57`, `helper_scripts/cron/ml_training_maintenance.py:58`, `helper_scripts/cron/ml_training_maintenance_cron.sh:79`, `program_code/ml_training/parquet_etl.py:104`, `program_code/ml_training/parquet_etl.py:439`
- Evidence command / inspection method: source read shows `DEFAULT_TRAINING_ENGINE_MODES="demo"` and `DEFAULT_SHADOW_ENGINE_MODES="demo,live_demo"`; runtime status JSON showed scorer/quantile runs for demo only; runtime SELECT showed 3,230 live_demo fills and 825,286 live_demo decision outcomes.
- Impact: the scheduled scorer/quantile lane is learning from demo evidence while shadow advisory evaluates demo/live_demo. That is acceptable for a demo stage, but it is insufficient evidence for live-grade ML readiness because live_demo control-flow labels are not in the scheduled supervised/quantile training lane.
- Why real, not false positive: `parquet_etl.py` supports mode scoping, including live widening to live_demo, so this is not a schema limitation. The current cron/status combination simply does not use that lane for scheduled scorer/quantile training.
- Suggested fix direction: have PA define the next stage lane explicitly: keep demo-only if the project remains demo-apply, or schedule a separate live_demo/live widened training report with isolated metrics, embargo, and no auto-promotion until registry/performance gates pass.
- Fix owner role: **PA(default)** for stage policy; **E1(worker)** for cron/training configuration.
- Verification owner role: **MIT(default)** for status/DB evidence; **QC(worker)** for alpha-evidence interpretation.

### MIT-DBML-003 - Drift and model-performance evidence tables are still empty

- Classification: **FACT**
- Severity: **P2**
- Affected path+line: `helper_scripts/cron/feature_baseline_writer_cron.sh:101`, `program_code/ml_training/canary_promoter.py:81`, `program_code/ml_training/canary_promoter.py:617`
- Evidence command / inspection method: runtime SELECT showed `observability.feature_baselines count=2108` and fresh rows, but `observability.drift_events count=0` and `observability.model_performance count=0`; feature baseline cron log reported healthcheck PASS and "drift_events will activate after configured burn-in."
- Impact: baseline storage is healthy, but downstream drift/model-quality evidence is not yet available. Canary or production review cannot rely on empirical model performance or drift history from these tables.
- Why real, not false positive: this finding does not claim the baseline writer failed. It distinguishes active baseline production from empty downstream evidence tables, confirmed by both DB counts and the cron log wording.
- Suggested fix direction: schedule or enable the drift evaluator and model-performance writer after burn-in, then require non-empty, mode-scoped evidence before any live ML promotion packet.
- Fix owner role: **E1(worker)** for evaluator/writer plumbing; **MIT(default)** for metric/schema acceptance.
- Verification owner role: **MIT(default)** with **E4(worker)** runtime cron/status confirmation.

### MIT-DBML-004 - Replay foundation remains smoke/incomplete for ML promotion evidence

- Classification: **FACT**
- Severity: **P2**
- Affected path+line: `helper_scripts/cron/m11_replay_runner_daily_cron.sh:20`, `helper_scripts/cron/m11_replay_runner_daily_cron.sh:81`
- Evidence command / inspection method: runtime crontab includes daily M11 replay runner; source read says Stage A is a single-fixture smoke heartbeat, not full cohort nightly; runtime SELECT showed `replay.experiments count=24`, completed 0, live_demo 0, `replay.simulated_fills count=46`, max timestamp 2026-05-11, and `replay.mlde_replay_veto_log count=0`.
- Impact: replay is useful as an execution-chain heartbeat, but it is not yet a promotion-grade replay evidence source for ML. Replay-derived veto/performance evidence cannot currently support live ML gates.
- Why real, not false positive: the cron being installed is positive evidence, not a failure. The limitation is stated in the wrapper comments and confirmed by DB state: no completed/live_demo experiment rows and stale simulated fills.
- Suggested fix direction: complete Stage A health accumulation, then add Stage B cohort replay with explicit mode/symbol coverage, completion criteria, and veto/performance materialization before using replay in ML promotion decisions.
- Fix owner role: **E1(worker)** for replay runner chain; **PA(default)** for stage acceptance.
- Verification owner role: **MIT(default)** for DB evidence; **QC(worker)** for replay/alpha validity.

### MIT-DBML-005 - Synthetic replay is accepted in demo-applier evidence filtering

- Classification: **FACT**
- Severity: **P3**
- Affected path+line: `program_code/ml_training/mlde_demo_applier_evidence_filter.py:51`, `program_code/ml_training/mlde_demo_applier_evidence_filter.py:60`, `program_code/ml_training/mlde_demo_applier_evidence_filter.py:181`
- Evidence command / inspection method: source read shows `EVIDENCE_SOURCE_TIER_ALLOWLIST` includes `synthetic_replay`; runtime SELECT showed only one `synthetic_replay` simulated fill at current inspection.
- Impact: synthetic evidence can pass the same evidence-source allowlist as real/calibrated replay for demo recommendation filtering. This is low current blast radius because the applier is demo-only and runtime synthetic count is tiny, but it can blur evidence quality if synthetic volume grows.
- Why real, not false positive: the value is explicitly in the allowlist and the filter uses that allowlist in SQL. The finding is not claiming live mutation risk; severity is P3 because the current apply lane is demo-only.
- Suggested fix direction: split synthetic replay into a separate policy bucket, downweight it, or require explicit opt-in per experiment/recommendation type so synthetic evidence cannot silently co-mingle with real/calibrated evidence.
- Fix owner role: **PA(default)** for evidence policy; **MIT(default)** for DB/filter semantics.
- Verification owner role: **MIT(default)**.

## CV / Leakage Controls

Positive controls confirmed:

- `program_code/ml_training/cpcv_validator.py:48` defines CPCV configuration with folds, embargo, and label-window controls; `program_code/ml_training/cpcv_validator.py:113` builds purged/embargoed temporal folds.
- `program_code/ml_training/scorer_trainer.py:168` calls CPCV validation before final fit.
- `program_code/ml_training/quantile_trainer.py:52` defines strategy-specific embargo/holdout settings; `program_code/ml_training/quantile_trainer.py:423` uses tail holdout; `program_code/ml_training/quantile_trainer.py:578` applies split/embargo logic.
- `program_code/ml_training/parquet_etl.py:439` loads labeled rows ordered by timestamp with exact `engine_mode`, strategy/symbol, schema version/hash, and feature definition hash filters.
- `program_code/ml_training/parquet_etl.py:549` validates feature JSON and rejects malformed/non-numeric/non-finite inputs instead of silently zero-filling.
- `program_code/ml_training/quantile_reports.py:233` gates verdicts by sample size and hard metric checks, downgrading to `shadow_only` rather than auto-shipping on weak evidence.

Caveats:

- The active scheduled training lane observed in runtime status is demo-only.
- Legacy scorer status reported `calibration_skipped`; quantile trainer does perform CQR calibration in the observed successful jobs.
- `program_code/ml_training/edge_estimate_validation.py:27` has `purge_days=0` by default for walk-forward edge validation. This was not raised as a primary finding because the main scorer/quantile training paths have CPCV/embargo controls, but live-readiness review should ensure any edge-validation caller sets a nonzero purge when used as promotion evidence.

## Migration / Register Alignment

- Runtime DB is successfully migrated through V113.
- Source contains V114 (`sql/migrations/V114__notification_failsafe_events_hypertable.sql`) while runtime `_sqlx_migrations` max is V113. This is source/runtime drift for a notification-failsafe migration, outside the ML foundation critical path inspected here. It should be tracked by the infra/notification owner before relying on V114 runtime tables, but it is not counted as an ML P1/P2 in this audit.
- R4's register-path P1 and TW's Operator-mirror P1 are inherited documentation/index issues, not re-counted as MIT DB/ML findings here.

## Required Owner Handoff

- Live ML promotion remains blocked until at least MIT-DBML-001 is closed and MIT-DBML-003 has evidence.
- If the project intentionally remains at demo-apply stage, MIT-DBML-002 is a stage declaration requirement rather than a bug fix: PA should mark demo-only scheduled training as intentional.
- No P0 findings were identified.
