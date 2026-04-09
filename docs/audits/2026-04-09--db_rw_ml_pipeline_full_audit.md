# DB Read/Write + ML Pipeline Full Audit Report
# DB 讀寫 + ML 管線全面審計報告
# Date: 2026-04-09
# Auditor: MIT (Main Integration Tester) — 3-way parallel audit

---

## Executive Summary / 總結

Architecture is sound — single-write-source enforced, read/write separation clean, Rust trading loop has zero DB dependency. Problems concentrate on "last-mile wiring": DDL not executed, FeatureCollector not dispatched, cost_gate logic divergence between Python and Rust.

架構設計正確 — 單一寫入口、讀寫分離、Rust 交易循環零 DB 依賴。問題集中在「最後一公里接線」：DDL 未執行、FeatureCollector 未分派、cost_gate Python/Rust 邏輯分歧。

---

## I. Architecture Health Scorecard / 架構健康度總評

| Dimension / 維度 | Status / 狀態 | Grade |
|-------------------|---------------|-------|
| DB Write single-source / 單一寫入口 | **PASS** — core trading tables exclusively written by Rust | A |
| DB Read/Write separation / 讀寫分離 | **PASS** — GUI all GET, Python ML read-only on core tables | A |
| ML code completeness / ML 代碼完備性 | **PASS** — 18 modules all importable, ~8500 lines ML code | A- |
| End-to-end runnability / 端到端可運行性 | **FAIL** — multiple blockers | D |
| Rust ↔ Python wiring / 接線完整性 | **PARTIAL** — gaps exist | C+ |

---

## II. 5 Critical/High Gaps / 5 個關鍵 Gap

### GAP-1: V004+ DDL Not Executed (CRITICAL — blocks entire ML chain)
### V004+ DDL 未執行（CRITICAL — 阻塞 ML 全鏈路）

V004 header explicitly states: "DRAFT — Phase 0a DDL（尚未執行）, planned 2026-04-11"

**Blocked tables / 被阻塞的表：**

| Table | Affected Module | Phase |
|-------|----------------|-------|
| `learning.james_stein_estimates` | james_stein_estimator.py write path | **Phase 5 P0** |
| `learning.ml_parameter_suggestions` | optuna_optimizer.py write path | Phase 3 |
| `learning.bayesian_posteriors` | thompson_sampling.py write path | Phase 3 |
| `learning.cpcv_results` | cpcv_validator.py write path | Phase 3 |
| `learning.linucb_state` (V009) | linucb warm-start | Phase 4 |
| `observability.feature_baselines` | drift_detector.rs read path | Phase 1 |
| `features.online_latest` | feature_writer.rs write path | Phase 2 |

**Conclusion**: ML pipeline code is all written, but no module can persist results to DB. Current workaround: JSON files (`edge_estimates.json`).

---

### GAP-2: cost_gate Logic Divergence (HIGH — Phase 5 P0 core)
### cost_gate 邏輯分歧（HIGH — Phase 5 P0 核心）

Python `cost_gate.py` and Rust `intent_processor.rs::cost_gate_paper()` have **inconsistent logic**:

| Feature | Python cost_gate.py | Rust cost_gate_paper() |
|---------|---------------------|----------------------|
| ATR% normalization | ATR / price | Uses absolute ATR |
| win_rate weighted threshold | threshold / max(0.3, win_rate) | None |
| daily_trade_count safety valve | Zero-trade-day relaxation | None |
| slippage tier lookup | BTC 1bps -> Meme 30bps | None |
| James-Stein edge query | Not directly used | edge_estimates.get() |

**Consequence**: Production cost_gate is NOT executing the designed policy. Phase 5 edge crisis fix may be ineffective.

**Key files**:
- `program_code/local_model_tools/cost_gate.py` (lines 120-185)
- `rust/openclaw_engine/src/intent_processor.rs` (~line 450-500)

---

### GAP-3: FeatureCollector Implemented But Not Wired (HIGH — Phase 2 blocker)
### FeatureCollector 已實現但未接線（HIGH — Phase 2 阻塞）

- `feature_collector.rs`: 34-dim feature vector, `to_feature_vector()` fully implemented
- `tick_pipeline.rs`: **No call site** — features never dispatched to feature_writer
- `features.online_latest`: Schema in V004 (not executed), even if wired there's nowhere to write

**Impact chain**: tick produces features -> discarded -> scorer training cannot use real-time features -> falls back to historical parquet synthetic data only

**Key files**:
- `rust/openclaw_engine/src/feature_collector.rs` (lines 34-40: FEATURE_NAMES, lines 81-101: to_feature_vector())
- `rust/openclaw_engine/src/tick_pipeline.rs` (missing feature dispatch)

---

### GAP-4: Python Has No Connection Pooling (HIGH — Dashboard reliability)
### Python 端無連接池（HIGH — Dashboard 可靠性）

All Python DB reads (Dashboard, ML training) use per-request `psycopg2.connect()`:
- New connection per request, 3-5s timeout
- No retry logic
- Silent empty return on failure (user sees blank Dashboard without knowing DB is down)

Rust side has proper sqlx PgPool (5 max / 2 min) — good design.

**Key files**:
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategy_read_routes.py` (lines 419-431: `_get_pg_conn()`)
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/grafana_data_writer.py` (lines 69-83)

---

### GAP-5: trading.orders + order_state_changes Empty Tables (MEDIUM)
### trading.orders + order_state_changes 空表（MEDIUM）

V003 created `trading.orders` and `trading.order_state_changes` but **no writer exists**. OMS state machine lives in Python, doesn't write to DB.

**Impact**: Order lifecycle cannot be reconstructed from DB. Audit chain incomplete. Phase 5+ deliverable.

---

## III. Write Path Matrix / 寫入路徑矩陣

### Core Tables — No Conflicts / 核心表 — 無衝突

| Schema.Table | Rust Writer | Python Writer | Conflict? |
|-------------|-------------|---------------|-----------|
| trading.fills | trading_writer (exclusive) | Read-only | **Safe** |
| trading.signals | trading_writer | Read-only | **Safe** |
| trading.intents | trading_writer | Read-only | **Safe** |
| trading.decision_context_snapshots | context_writer | Read-only | **Safe** |
| trading.position_snapshots | trading_writer | Read-only | **Safe** |
| market.* (all) | market_writer | deprecated | **Safe** |
| learning.linucb_state | state_io.rs UPSERT | linucb_trainer.py | **Dual-write** (UPSERT + version isolation, acceptable) |
| learning.ai_usage_log | ai_budget/usage_io.rs | None | **Safe** |
| learning.teacher_directives | claude_teacher/writer.rs | None | **Safe** |
| learning.directive_executions | claude_teacher/writer.rs | None | **Safe** |
| features.online_latest | feature_writer.rs UPSERT | None | **Safe** |
| observability.engine_events | position_reconciler.rs + main.rs | None | **Safe** |
| observability.drift_events | drift_detector.rs | None | **Safe** |
| trading_raw.* | None | Python snapshot scripts | **Safe** (Rust never touches raw schema) |

### Rust Write Details / Rust 寫入細節

| Writer | File | Pattern | Batch Size | Error Handling |
|--------|------|---------|-----------|----------------|
| trading_writer | `database/trading_writer.rs` | mpsc -> batch buffer -> flush on timer | 4000-5000 | pool stats + warn, non-fatal |
| context_writer | `database/context_writer.rs` | mpsc -> HashMap dedup -> flush | configurable | DB-RUN-6 guard (epoch-0 reject) |
| market_writer | `database/market_writer.rs` | BatchAggregatorsMsg -> QueryBuilder | varies | pool stats + warn |
| feature_writer | `database/feature_writer.rs` | batch UPSERT (symbol + ts_ms) | configurable | graceful degradation |
| news/pipeline | `news/pipeline.rs` | single INSERT per item after dedup | 1 | fail-soft if pool unavailable |

### Fill Writing Specifics / Fill 寫入細節

```
trading.fills columns (V008):
  ts, fill_id, order_id, symbol, side, qty, price, fee, fee_rate,
  realized_pnl, is_paper, strategy_name, context_id

- fee_rate captured (V008 addition)
- All numeric fields NaN-sanitized via sanitize_f64_or_zero()
- is_paper = always TRUE in demo mode
- ON CONFLICT (fill_id, ts) DO NOTHING — idempotent
- Immutable after insertion (no UPDATE)
```

---

## IV. Read Path Health / 讀取路徑健康度

| Reader | Data Source | Pool? | Latency Risk | Silent Fail? |
|--------|-----------|-------|-------------|-------------|
| Dashboard klines/signals | Rust IPC snapshot (primary) -> Python fallback | N/A | 60s fallback | Yes |
| Dashboard fills/features | PostgreSQL direct | No pool | 3s timeout | Yes (returns empty) |
| Phase4 Dashboard | PostgreSQL direct | No pool | 3s timeout | Yes |
| Parquet ETL | DuckDB -> PG (READ_ONLY) | N/A | Batch | No (raises error) |
| ML Training (linucb/edge) | psycopg2 per-call | No pool | varies | Yes (lazy import skip) |
| Rust Drift Detection | sqlx PgPool | Yes (5 conn) | Real-time | Yes (fail-open) |
| **Rust Trading Loop** | **None (all in-memory)** | N/A | **0ms** | N/A |

### Data Staleness Matrix / 數據新鮮度

| Read Path | Staleness | Mitigation |
|-----------|-----------|-----------|
| Dashboard klines | 60s (Python fallback) | Rust IPC primary (real-time) |
| Dashboard signals | Depends on Rust writer | Fallback to Python SignalEngine |
| ML training fills | 24h lag | Daily batch (parquet_etl) |
| Feature vectors | 5s lag (UPSERT interval) | Written by Rust engine real-time |
| Edge statistics | 1h lag | Computed from historical fills |

### Known Issue: Parquet ETL Feature Staleness
`parquet_etl.py` reads `features.online_latest` with NO time filter — gets ALL features including potentially stale ones. Should add temporal window.

---

## V. ML Pipeline End-to-End Runnability / ML 管線端到端可運行性

| Step | Module | Can Run? | Blocker |
|------|--------|----------|---------|
| 1. ETL | parquet_etl.py | Yes | — |
| 2. Label generation | label_generator.py | Yes | — |
| 3. CPCV validation | cpcv_validator.py | Yes | — |
| 4. LightGBM training | scorer_trainer.py | **No** | `pip install lightgbm` |
| 5. Calibration | calibration.py | **No** | stub, not implemented |
| 6. Optuna optimization | optuna_optimizer.py | **No** | V004 DDL |
| 7. Thompson Sampling | thompson_sampling.py | **No** | V004 DDL |
| 8. LinUCB training | linucb_trainer.py | **No** | V009 DDL |
| 9. James-Stein | james_stein_estimator.py | Partial | Can write JSON; V004 blocks PG persistence |
| 10. Edge Stats | realized_edge_stats.py | Yes | — |
| 11. ONNX export | — | **No** | ort crate not added, Phase 4 |

### ML Module Inventory (18 modules, all importable)
- parquet_etl.py, label_generator.py, scorer_trainer.py, cpcv_validator.py
- optuna_optimizer.py, thompson_sampling.py, linucb_trainer.py
- linucb_shadow_compare.py, linucb_arm_migration.py
- james_stein_estimator.py, realized_edge_stats.py, edge_cluster_analysis.py
- calibration.py, leakage_check.py
- dl3_foundation.py, dl3_ab_runner.py, dl3_go_no_go.py
- weekly_report_generator.py, run_training_pipeline.py

### Rust ML Modules
- `ml/model_manager.rs` — ONNX hot-swap via ArcSwap (ort deferred, 3-tier fallback)
- `ml/scorer.rs` — inference wrapper with tier-based degradation
- `ml/kelly_sizer.rs` — fractional Kelly with sample-size adjustment
- `linucb/inference.rs` — ridge regression theta + UCB arm selection
- `linucb/state_io.rs` — BYTEA serialization for A/b matrices
- `linucb/runtime.rs` — in-memory arm registry + cold-start v1_15
- `edge_estimates.rs` — PH5-WIRE-1: load JSON edge snapshot
- `feature_collector.rs` — 34-dim feature vector (NOT WIRED)
- `intent_processor.rs` — cost_gate integration (~line 450+)

---

## VI. Database Schema Summary / 數據庫 Schema 概覽

14 migrations (V001-V014), 30+ tables across 8 schemas:

| Schema | Purpose | Tables | Status |
|--------|---------|--------|--------|
| market | Market data (tickers, klines, OB, funding, OI, liquidations, regime, news) | 11 | V002 executed |
| trading | Core trading (signals, intents, fills, orders, positions, decisions) | 8 | V003 executed |
| trading_raw | Raw Bybit snapshots (decisions, verdicts, WS events, account) | 6 | Auto-created by Python |
| agent | Agent state (messages, AI invocations, state changes) | 3 | V003 executed |
| learning | ML state (linucb, directives, experiments, budget, posteriors) | 10+ | **V004/V009/V010 NOT executed** |
| features | Online feature store | 2 | **V004 NOT executed** |
| observability | Drift, quality, engine events | 4 | **V004 partial, V014 executed** |
| risk | Risk management tables | TBD | V004 NOT executed |

---

## VII. Recommended Action Priority / 建議行動優先級

| Priority | Action | Impact | Est. Effort |
|----------|--------|--------|-------------|
| **P0** | Review + execute V004 DDL | Unblocks entire ML chain | 1h review + 5min execute |
| **P0** | Unify cost_gate logic (backport Python formula to Rust) | Phase 5 edge fix effectiveness | 1d |
| **P1** | `pip install lightgbm` | Unblocks scorer training | 5min |
| **P1** | Wire FeatureCollector in tick_pipeline + feature_writer | Unblocks Phase 2 | 2-3d |
| **P2** | Python DB connection pooling (psycopg2.pool or asyncpg) | Dashboard reliability | 0.5d |
| **P2** | Dashboard silent failure -> 503 + alert | User awareness of DB issues | 0.5d |
| **P3** | Implement trading.orders writer | Audit completeness | Phase 5+ |
| **P3** | Implement calibration.py | Kelly sizing accuracy | 1-2d |

---

## VIII. Appendix: Connection Configuration / 連接配置

### Rust (sqlx PgPool)
- pool_max_connections: 5 (default)
- pool_min_connections: 2 (default)
- connect_timeout_ms: 5000
- batch_flush_interval_ms: 2000
- db_writes_enabled: true (hot reload)
- Graceful degradation when PG unavailable (optional DB)

### Python (per-request psycopg2)
- connect_timeout: 3-5s
- No pooling
- Credentials from: PG_PASS env var -> secrets files (multiple fallback locations)
- No retry logic
- Silent return None on failure

---

*Generated by 3-way parallel audit: DB Write paths + DB Read paths + ML Pipeline wiring*
*Audit methodology: Exhaustive code search across Rust (openclaw_engine/src/) and Python (program_code/, helper_scripts/)*
