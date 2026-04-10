# ML Pipeline Remediation — Complete Engineering Record
# ML 管線修復 — 完整工程記錄
# 2026-04-10

> Based on 2026-04-09 DB R/W + ML Pipeline Full Audit
> 基於 2026-04-09 DB 讀寫 + ML 管線全面審計
> Audit report: `docs/audits/2026-04-09--db_rw_ml_pipeline_full_audit.md`

---

## Executive Summary / 執行摘要

7 個 Session（S0-S6）中，**S0/S1/S2/S3/S5 全部可執行項已完成**。S4（Teacher-Student/LinUCB）和 S6（Calibration/ONNX）需要引擎累積數據後才能執行，屬於後續 Phase 4/6 工作。

**Commits**: `7178059`（主體 15 files, +831/-333）, 後續修復 commit（audit gap fixes, 6 files）

**Test baselines after final fix**:
- Python control_api: **2678 passed**, 1 pre-existing fail, 15 skipped
- Python ml_training: **135 passed**, 6 skipped
- Rust lib: **838 passed**

---

## Session 0 — Foundation Layer ✅

| Item | Status | Evidence |
|------|--------|----------|
| 0-1: V001-V014 DDL | All 14 migration files exist in `sql/migrations/` | Static verified |
| 0-2: LightGBM 4.6.0 | Installed in venv, imported by `scorer_trainer.py` + `onnx_exporter.py` | `requirements-ml.txt: lightgbm>=4.0.0` |
| 0-3: Data baseline | `trading.fills` written by `trading_writer.rs:226`, `decision_context_snapshots` by `context_writer.rs` | Rust wiring confirmed |

---

## Session 1 — Phase 5 P0 Edge Crisis Fix ✅

### 1-1: cost_gate Unification
- `cost_gate_paper()`: `intent_processor.rs:845`
- `cost_gate_live()`: `intent_processor.rs:929`
- `SLIPPAGE_TIERS`: 5-tier const at `intent_processor.rs:69`
  - `(1B, 1bps), (100M, 2bps), (10M, 5bps), (1M, 15bps), (<1M, 30bps)`
- ATR% normalization: `intent_processor.rs:902` — `atr_pct = (atr / price) * 100`
- win_rate weighting: `intent_processor.rs:867-868` — `threshold = fee_bps / wr.clamp(0.3, 1.0) * 1.3`

### 1-3: CellEstimate Extension
- `edge_estimates.rs:20-33`: `shrunk_bps`, `win_rate`, `n_trades`, `std_bps`
- `load_from_str()`: `edge_estimates.rs:116` — JSON parser with `win_rate_shrunk` / `win_rate` fallback
- cost_gate consumption: both functions read `cell.win_rate` (lines 867, 944)
- **Note**: `std_bps` is stored but not yet consumed by gate logic (future uncertainty-adjusted gating)

### 1-2: Realized Edge Verification
- **Deferred**: DB fresh-start reset done 2026-04-10; run `--days 2` on 2026-04-11, then daily +1 until Day 7

---

## Session 2 — ML Inference Pipeline Wiring ✅

### 2-1: FeatureCollector Full Chain
1. `tick_pipeline.rs:1389-1402` — `tx.try_send(snap)` dispatches FeatureSnapshot
2. `main.rs:1276-1281` — `mpsc::channel(2048)` creation
3. `main.rs:1294-1303` — `tokio::spawn(run_feature_writer(...))`
4. `feature_writer.rs:44-123` — HashMap dedup + `INSERT ON CONFLICT DO UPDATE` UPSERT
5. Wiring: `event_consumer/setup.rs:91-93` → `pipeline.set_feature_channel(tx)`

### 2-2: Parquet ETL Time Filter
- `parquet_etl.py:92-98` — `WHERE updated_ts_ms >= {start_epoch_ms}`
- **2-2b deferred**: end-to-end verification needs engine running

---

## Session 3 — Parameter Optimization Pipeline ✅

### 3-1: Optuna Persistence
- `_get_ml_pg_conn()`: `optuna_optimizer.py:361-381` — DSN/env fallback, standalone connection (not shared pool, correct for batch ML)
- `_persist_suggestion()`: `optuna_optimizer.py:384-426` — INSERT into `learning.ml_parameter_suggestions`
  - Columns: `strategy_name, symbol, regime, model_name, suggested_params, expected_improvement`
- Call site: `optuna_optimizer.py:595-602` — unconditional on success path of `run_optimization()`
- **3-1c deferred**: dry-run needs engine fills data

### 3-2: Thompson Sampling Positioning
- Confirmed as **(A) offline training tool** — Python-only, Phase 3b
- `thompson_sampling.py:381-440` — `save_posteriors_to_pg()` UPSERT into `learning.bayesian_posteriors`
- Zero Rust references (grep verified) — not called at runtime
- Rust inference deferred to Phase 4 (E5-D3)

### 3-3: CPCV Persistence
- `_persist_cpcv_result()`: `cpcv_validator.py:301-358` — INSERT into `learning.cpcv_results`
  - 11 columns all match V004 DDL
- Call site: `cpcv_validator.py:296` — called before return in `validate_cpcv()`
- **Fixed in audit**: `model_name` / `model_version` now parameterized through `validate_cpcv()` signature (was hardcoded defaults)

### 3-4: Strategy Parameter Update Mechanism
- **Deferred**: Optuna → IPC → Rust hot-reload path needs separate implementation

---

## Session 5 — DB Infrastructure Hardening ✅

### 5-1: Connection Pool
- `db_pool.py` (NEW): `psycopg2.pool.ThreadedConnectionPool`
  - Singleton pattern, min=2 / max=10 (env var configurable)
  - API: `get_conn()`, `put_conn()`, `get_pg_conn()` (context manager), `pool_stats()`
- **Migrated callers**:
  - `grafana_data_writer.py` — delegated via `_get_pg_conn()` / `_put_pg_conn()` wrappers
  - `strategy_read_routes.py` — delegated via same pattern
  - `phase4_routes.py` — all 6 DB helpers migrated (linucb/teacher/news/dl3/weekly_review ×2)
  - `bybit_demo_sync.py` — `_get_conn()` prefers db_pool, falls back to direct connect; `_release_conn()` returns to pool or closes
- **ML training scripts** intentionally use standalone `psycopg2.connect()` (batch jobs, not web app)

### 5-2: Dashboard Silent Failure Fix
- `strategy_read_routes.py`: 6 DB failure paths now return **HTTP 503** + `{"error": "database_unavailable"}`
  - 3 null-conn paths + 3 exception paths, zero silent failures remaining
- `/api/v1/health/db` endpoint: `legacy_routes.py:452-475`
  - `pool_stats()` + `SELECT 1` liveness probe
  - Returns `{ok: true/false, pool: {...}}`

### 5-3/5-4: Orders Writer + Cleanup
- **Deferred**: Rust `batch_order_manager.rs` order lifecycle + deprecated code cleanup

---

## Test Impact — Before/After

| Suite | Before (pre-audit) | After (final) | Delta |
|-------|-------------------|---------------|-------|
| Rust lib | 835 | 838 | +3 (slippage_tier, js_win_rate, high_volume) |
| Python control_api | ~2680 pass, 1 fail | 2678 pass, 1 fail, 15 skip | Stable (pre-existing: test_risk_view_client) |
| Python ml_training | 135 pass | 135 pass, 6 skip | Stable |

---

## Remaining Work (Needs Engine / Separate Scope)

### Needs Engine Running
- **S1-2**: Realized edge verification — `--days 2` on 2026-04-11 (Day 2 post fresh-start)
- **S2-2b**: Parquet ETL end-to-end
- **S2-3**: Scorer training end-to-end
- **S3-1c**: Optuna dry-run

### Separate Scope (Phase 4/6)
- **S3-4**: Optuna → IPC → Rust hot-reload param path
- **S4-1**: LinUCB warm-start deployment (`linucb/state_io.rs::load_arms()` exists, needs integration test)
- **S4-2**: Teacher directive consumer (`claude_teacher/mod.rs` has full pipeline, needs consumption wiring)
- **S4-3**: Directive outcome backfill (`helper_scripts/phase4/backfill_directive_outcomes.py` exists)
- **S5-2b**: Frontend JS 503 banner
- **S5-3**: trading.orders writer in Rust
- **S5-4**: Deprecated code cleanup
- **S6-1**: Calibration (Platt scaling + isotonic regression)
- **S6-2**: DL-3 foundation model evaluation
- **S6-3**: ONNX export + ort crate integration

---

## Files Modified (Cumulative)

### Rust
- `rust/openclaw_engine/src/edge_estimates.rs` — CellEstimate struct + load_from_str()
- `rust/openclaw_engine/src/intent_processor.rs` — SLIPPAGE_TIERS + cost_gate unification

### Python — ML Training
- `program_code/ml_training/optuna_optimizer.py` — `_get_ml_pg_conn()` + `_persist_suggestion()`
- `program_code/ml_training/cpcv_validator.py` — `_persist_cpcv_result()` + model_name/version params
- `program_code/ml_training/parquet_etl.py` — temporal WHERE filter
- `program_code/ml_training/label_generator.py` — zero-ATR floor fix

### Python — Control API
- `app/db_pool.py` (NEW) — ThreadedConnectionPool singleton
- `app/grafana_data_writer.py` — pool delegation
- `app/strategy_read_routes.py` — pool delegation + HTTP 503
- `app/phase4_routes.py` — pool delegation (6 helpers)
- `app/legacy_routes.py` — `/api/v1/health/db` endpoint
- `app/bybit_demo_sync.py` — pool delegation + `_release_conn()`

### Tests
- `tests/test_grafana_data_writer.py` — pool mock updates
- `tests/test_bybit_demo_sync.py` — `_release_conn` assertions
- `tests/test_phase4_routes.py` — `db_pool.get_conn` mock for no-PG tests
- `ml_training/tests/test_label_generator.py` — edge case fixes

---

## Architectural Decisions

1. **ML training scripts use standalone connections, not db_pool** — Correct. Batch ML jobs run outside the web app process; sharing the pool would create cross-process issues and unnecessary coupling.

2. **bybit_demo_sync uses pool-first + direct-connect fallback** — The sync worker runs in the web app thread; using the pool is proper. Fallback ensures resilience if pool fails.

3. **HTTP 503 replaces silent 200** — Breaking change for any frontend that assumes 200 = valid data. Frontend JS banner (S5-2b) is logged as follow-up.

4. **CPCV model_name/version parameterized** — Future multi-model support won't write incorrect metadata.

---

## Cross References
- Main TODO: `TODO.md` (Phase 5/6/Live Gate)
- Audit report: `docs/audits/2026-04-09--db_rw_ml_pipeline_full_audit.md`
- ML architecture: `docs/references/2026-04-03--ml_dl_learning_architecture_v0.4.md`
- DB Schema: `sql/migrations/V001-V014`
