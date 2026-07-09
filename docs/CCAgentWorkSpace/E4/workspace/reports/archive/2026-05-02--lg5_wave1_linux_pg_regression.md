# E4 LG-5 Wave 1 Linux PG Regression — 2026-05-02

**Verdict**: **PASS** — ready for PM Sign-off

**Scope**: PM commit `9076cc9` — LG-5 Wave 1
- `sql/migrations/V035__governance_audit_log.sql` (288 LOC, new file)
- `program_code/ml_training/mlde_demo_applier.py` (1374 LOC, +401 +102)
- `program_code/ml_training/tests/test_mlde_demo_applier.py` (775 LOC, +332)

**Linux state**: trade-core @ `9076cc9` (ff-only pulled). PG `trading_ai` production.

## Test 結果

| Suite | passed | failed | baseline | delta | verdict |
|---|---|---|---|---|---|
| Cargo migrations_test (release) | **5** | 0 | 5 | +0 | PASS |
| Pytest mlde_demo_applier (IMPL-1) | **15** | 0 | 15 | +0 | PASS |
| Pytest mlde_shadow_advisor | **5** | 0 | 5 | +0 | PASS |
| Pytest control_api_v1 (excl integration) | **3262** | 1 (pre-existing grafana) | 3262/1 | +0 effective | PASS |
| V035 apply 1st run | RAISE=0 | ERROR=0 | — | — | PASS |
| V035 apply 2nd run | RAISE=0 | ERROR=0 | — | — | PASS (idempotent) |
| V035 apply 3rd run | RAISE=0 | ERROR=0 | — | — | PASS (idempotent) |
| CHECK invalid event_type | RAISED | — | — | — | PASS (constraint攔截) |
| CHECK invalid verdict_decision | RAISED | — | — | — | PASS (constraint攔截) |
| Positive INSERT + cleanup | id=3 / DELETE 1 | remaining=0 | — | — | PASS |
| audit_migrations.py V035 | OK | — | — | — | PASS |
| Healthcheck SUMMARY | WARN baseline | new WARN/FAIL=0 | match | == | PASS |

## V035 結構驗證 (Step 4)

- col_count = **23** ✓
- Indexes: `governance_audit_log_pkey`, `governance_audit_log_ts_idx` (timescaledb default), `idx_gov_audit_candidate_ts`, `idx_gov_audit_event_type_ts` — 2 hot-path required ✓
- Hypertable: `governance_audit_log` num_chunks=0 (new table, 0 INSERT yet) — conversion confirmed ✓
- Guard A NOTICE on 2nd run: `learning.governance_audit_log already exists with all required columns; CREATE TABLE will no-op` ✓
- Guard C NOTICE on every run: `both hot-path indexes validated` ✓

## Pre-existing fail clarification

`test_grafana_data_writer.py::TestGrafanaDataWriterLifecycle::test_start_sets_running` — identical assertion fail (`writer._running is True` got `False`) on parent baseline `1f3acc5` (P2 wave run). Zero file overlap with Wave 1 changes. Scope orthogonal.

## Mock 審查

N/A — verification-only, no mock introduced.

## Healthcheck delta

| Check | Baseline | This run |
|---|---|---|
| [4] phys_lock_runtime | WARN | WARN |
| [10] intents_writer_ratio | WARN | WARN |
| [11] counterfactual_clean_window | WARN | WARN |
| [27] intents_counter_freeze | WARN | PASS (improved) |
| [33] maker_fill_rate | WARN | WARN |
| [40] realized_edge_acceptance | WARN | WARN |
| [41] scanner_market_gate_confirmation | WARN | WARN |

新 WARN/FAIL = 0 ✓

## Two-run flakiness

V035 idempotent 透過 3 連發 apply 驗證（first apply + 2 重複）— 比 single 2nd-run 更強的 idempotent proof。Cargo / pytest 套件對純 migration + producer payload 改動非 flaky-prone。

## Reports

- `.claude_reports/20260502_162616_e4_lg5_wave1_linux_pg_regression.md`
- `srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-02--lg5_wave1_linux_pg_regression.md`

## 結論

**PASS** — ready for PM Sign-off。
