# Phase 0b — TimescaleDB 啟用（W2-3，4/18-4/30，10 工作日）

> 前置：Phase 0a 完成
> DoD：TimescaleDB hypertable 可壓縮/retention · 連續聚合正常 · Grafana 正常 · OU 修正 · 4429+ tests

## 工作分解

| ID | 任務 | Agent | 依賴 | 並行組 | 時間 |
|----|------|-------|------|--------|------|
| 0b-01 | Docker image 切換腳本 + checklist（postgres:16 → timescale/timescaledb:latest-pg16） | E1-A | 0a | G1 | 4h |
| 0b-02 | 備�� → 切 image → 驗�� extension loaded | E1-A | 0b-01 | G1 | 2h |
| 0b-13 | requirements-ml.txt（scikit-learn/lightgbm/duckdb，try/except 降級） | E1-B | — | G1 | 2h |
| 0b-15 | OU Grid 公式修正 `sigma/sqrt(2*theta)` Python + Rust | E1-D | ��� | G1 | 2h |
| 0b-03~05 | 啟用 hypertable（3 路：market/trading/learning+obs+risk） | E1-B/C/D | 0b-02 | G2 | 2h ea |
| 0b-06 | 壓縮策略（segmentby + compress_after） | E1-E | G2 | G3 | 3h |
| 0b-07 | Retention policy（tickers 30d/ob 30d/trade_agg 90d/klines 永久） | E1-A | G2 | G3 | 2h |
| 0b-08 | sync_commit 分層（全局 OFF，Live 階段 orders/fills per-session ON） | E1-B | 0b-02 | G3 | 1h |
| 0b-12 | PG shared_buffers=8GB + OS 調優（vm.swappiness=1 等） | E1-A | 0b-02 | G3 | 1h |
| 0b-09 | grafana_data_writer 改寫（6 處 docker exec psql → psycopg2 直連 + 新 schema） | E1-C | 0b-06 | G4 | 6h |
| 0b-10 | Grafana datasource timescaledb:true | E1-D | 0b-02 | G4 | 1h |
| 0b-11 | 連續聚合（klines 1m → 5m/15m/1h/4h/1d） | E1-E | 0b-03 | G4 | 4h |
| 0b-14 | ML ��級分層策略（L0 LightGBM / L1 sklearn GBR / L2 CognitiveModulator + 硬編碼） | E1-C | 0b-13 | G4 | 4h |
| 0b-16 | **E2 代碼審查** | E2 | G4 | — | 4h |
| 0b-17 | **E4 回歸** | E4 | 0b-16 | — | 3h |
| 0b-18 | E3 安全審查 | E3 | 0b-16 | — | 1h |
| 0b-19 | **E5 優化���查**（Phase 0 全體） | E5 | 0b-17 | — | 3h |

## Docker 切換 Checklist

1. pg_dump 全量備份
2. 修改 Docker image → `timescale/timescaledb:latest-pg16`
3. 保持容���名 `trading_postgres` 不變
4. 保持 port 5432 不變
5. `CREATE EXTENSION IF NOT EXISTS timescaledb;`
6. Grafana datasource: `timescaledb: true`
7. 驗證所有 dashboard 正常
8. 驗證 grafana_data_writer.py 寫入正常
