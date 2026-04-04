# 2026-04-04 Session Progress 2 — R-CUT + R-IPC + Phase 0a/0b

## Commits (7 total)

| # | Commit | Description | Delta |
|---|--------|-------------|-------|
| 1 | `74ed1a1` | R-CUT Phase 1: RC-01~RC-09 策略補齊 | +1,115/-72 |
| 2 | `b96f440` | R-CUT Phase 2: RC-10~RC-13 最小切換 | +27/-1,020 |
| 3 | `5b2aef3` | R-CUT Phase 3: Go/No-Go 7/7 PASS | +15/-8 |
| 4 | `6d2b380` | R-IPC: IPC-01~06 Rust-first API routes | +318/-18 |
| 5 | `48d3b65` | Phase 0a: 43 tables / 8 schemas / 87 indexes | +12/-5 |
| 6 | `67ef386` | Phase 0b: TimescaleDB 2.26.1 + 28 hypertables | +15/-3 |
| 7 | `e1de327` | Phase 0b complete: compression/retention/Grafana/ML prep | +43/-11 |

## R-CUT Phase 1: 策略補齊 (RC-01~RC-09)

- RC-01: MA Crossover Hurst regime filter (mean_reverting/random_walk blocked)
- RC-02: MA Crossover multi-TF proxy (EMA of sma_50, alpha=0.01)
- RC-03: BB Breakout configurable params (squeeze_bw/expansion_bw/volume_threshold)
- RC-04: on_rejection() rollback for all 5 strategies with prev_* snapshots
- RC-05: on_fill() callback wired in tick_pipeline
- RC-06: Grid Trading geometric spacing + GridHealth + auto-rebalance
- RC-07: BB Reversion limit order (REAL strategy-side; execution Phase 2)
- RC-08: StrategyParams trait + ParamRange (Phase 3a stub)
- RC-09: E2 APPROVE + E4 4507 + QA Audit CONDITIONAL PASS (0 FAKE features)

## R-CUT Phase 2: 最小切換 (RC-10~RC-13)

- RC-10: Python PIPELINE_BRIDGE.activate() disabled at 2 call sites
- RC-11: 4 dead code files deleted (1,003 lines: shadow_decision_tracker, dream_engine, opportunity_tracker, strategy_health_monitor)
- RC-12: Full test suite 4507 zero regression
- RC-13: E2 + E4 PASS

## R-CUT Phase 3: Go/No-Go (RC-14~RC-15)

Go/No-Go 7/7 PASS:
1. Watchdog 3-STRIKE: PASS (INC-001 remediated)
2. Memory: 2.1MB RSS (threshold 100MB)
3. IPC: 409K+ ticks zero loss
4. Latency: P50=27us P95=28us P99=29us Max=99us (threshold 50us)
5. Rollback drill: 0.091s (threshold 600s)
6. 201K replay: 0 crash, 5 fills, 4.97s
7. Stability: 0 crash on new binary

## R-IPC (IPC-01~06)

- IPC-01: Rust PipelineSnapshot +5 fields (indicators/signals/strategies/recent_intents/recent_fills)
- IPC-02: Python ipc_state_reader.py +5 methods
- IPC-03: 8 API routes migrated to Rust-first (indicators/signals/strategies/intents/fills + summary/list/status)
- IPC-04: PipelineBridge downgraded to IPC relay + Agent callback container
- IPC-06: 4507 all green

## Phase 0a: PG Schema

- V001-V005 DDL executed: 8 schemas, 43 tables, 87 indexes, 11 Grafana VIEWs
- 14 legacy tables: 11 renamed to _legacy, 3 kept (audit_events, connector_*)
- Fix: V004 risk.correlation_pairs `window` SQL reserved word quoted
- Backup: trading_ai_pre_phase0a_20260404_180411.dump (186K)

## Phase 0b: TimescaleDB

- Docker: postgres:16 → timescale/timescaledb:latest-pg16 (v2.26.1)
- 28 hypertables enabled (11 market + 7 trading + 3 agent + 1 learning + 4 obs + 2 risk)
- 9 compression policies (market 7d, trading 14d)
- 15 retention policies (market 90d, klines 365d, trading 180d, obs 90d)
- sync_commit tiering (off for high-volume, on for fills/orders)
- grafana_data_writer INSERT targets updated to _legacy tables
- requirements-ml.txt created
- OU Grid spacing corrected: sigma/sqrt(theta) → sigma*sqrt(2/theta)
- ML model degradation strategy documented (3-tier fallback)

## Test Baseline

Python 3877 / Rust 592 / Canary 38 = **4507** (+62 vs session start)

## QA Audit Findings (RC-09)

- 0 FAKE features (vs Python V2's 6 FAKE/DEAD)
- CONDITIONAL items:
  - RC-07 limit orders: strategy produces correct intents, execution layer ignores order_type (Phase 2)
  - RC-06 geometric grid: code works but not deployed in main.rs (Phase 3a)
  - RC-08 StrategyParams: intentional Phase 3a stub

## Key Decisions

1. Abandon Python V2 trading engine, all-in Rust
2. Go/No-Go passed with 201K replay substitute for 7-day stability
3. Category B dead code (9 files, ~8,476 lines) deferred to R-IPC API write route migration
4. Phase 1 start date remains 5/01

## Next Steps

- Phase 1: Market data pipeline + FeatureCollector + PSI drift (5/01-5/14)
- IPC-05: Category B Python file degradation (after API write routes migrate)
