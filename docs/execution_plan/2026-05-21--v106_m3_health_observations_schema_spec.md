---
spec: V106 — M3 Health Observations Schema (Hypertable Required)
date: 2026-05-21
author: MIT consultant draft for PA Sprint 1A-β dispatch (placeholder reserve)
phase: v5.8 Sprint 1A-β schema prerequisite (per assignment)
status: SPEC-PLACEHOLDER (frontmatter + 大綱 reserve; full DDL land Sprint 1A-β)
parent specs:
  - srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md §2 M3 Health domain
  - srv/docs/CCAgentWorkSpace/E5/workspace/reports/2026-05-21--v58_hypertable_audit.md (per E5 hypertable + retention 驗)
mirror precedent:
  - srv/docs/execution_plan/2026-05-21--v103_v104_earn_hypotheses_schema_spec.md (format reference)
  - srv/sql/migrations/templates/schema_guard_template.sql (Guard A/B/C 範式)
scope: placeholder spec — 不寫 V106.sql, 不在 Mac 跑 SQL, 不執行 PG, full DDL 在 Sprint 1A-β 補完
---

# V106 M3 Health Observations Schema Migration Spec (PLACEHOLDER)

## §0 TL;DR

- **V106 新增 1 個 hypertable**：`learning.health_observations`（high-frequency per-domain health metric snapshots）。
- **Hot domains 6 類**：WS latency / REST success rate / DB backlog / disk usage / CPU+mem / strategy-level（per v5.8 §2 M3 domain spec）。
- **Hypertable mandatory**：7d chunk + 7d compression policy + 90d retention（per E5 5.21 audit；6mo +1.25-2.5 GB 占 buffer 16-63% 必 hypertable + compression）。
- **engine_mode CHECK 4 值齊全**；training filter 必含 `IN ('live','live_demo')`。
- **Sprint 1A-β schedule**：M3 hypertable 是高頻表，必在 M11 / M2 / 其他 module writer wire 前 land（避免 row backlog）。
- **依賴 V096 boundary**（TimescaleDB extension 已 ready；既有 hypertable infra 已驗）。

---

## §1 Background

### 1.1 v5.8 §2 M3 module 出處

v5.8 主檔 §2 M3 Health domain 列出 6 hot domain：
- **ws_latency**（WS heartbeat → tick arrival latency；per-symbol）
- **rest_success_rate**（per-endpoint API call success/total ratio）
- **db_backlog**（INSERT queue depth / writer queue size）
- **disk_usage**（PG data dir + log dir + binary backup dir）
- **cpu_mem**（per-process RSS + CPU%）
- **strategy_level**（per-strategy active count / signal rate / position count）

每 domain 多 metric / 多 symbol / 多 strategy → row 量級高（per 5min sampling × 6 domain × 5 strategy × 25 symbol ≈ 8.6k row/day base）。

### 1.2 Audit 來源

- MIT 2026-05-21 v5.8 audit 列為 high-frequency table risk
- E4 5.21 audit「M3 health 是 cross-domain 觀測層；必需以 unify governance + ml-pipeline + bybit-connector 監控」
- E5 5.21 hypertable audit「6 month +1.25-2.5 GB 占 PG buffer 16-63% → 必 hypertable + 7d compression + 90d retention」

---

## §2 Schema Outline (placeholder)

### 2.1 `learning.health_observations`

**Tables 大綱**：
- PK: `(observation_id, observed_at)` 複合（per hypertable best practice）
- Columns 大綱（10 fields）：
  - `observation_id BIGSERIAL`, `observed_at TIMESTAMPTZ NOT NULL`
  - `domain TEXT` (ENUM 6 值)
  - `metric_name TEXT` (e.g. `ws_latency_ms_p99`, `rest_success_rate_24h`, `db_writer_queue_depth`)
  - `symbol TEXT NULL` (domain=ws_latency / strategy_level 時非 null；其他 null)
  - `strategy_name TEXT NULL` (domain=strategy_level 時非 null；其他 null)
  - `metric_value NUMERIC(18,8)` (高精度，避 FLOAT 精度誤差)
  - `severity TEXT` ENUM (`INFO` / `WARN` / `CRITICAL`)
  - `engine_mode TEXT NOT NULL`
  - `evidence_json JSONB` (metric context 含 sampling window / threshold / raw computation)

**Constraints 大綱**：
- CHECK: `domain` ∈ 6 值 ENUM
- CHECK: `severity` ∈ 3 值 ENUM
- CHECK: `engine_mode` ∈ 4 值 ENUM
- NOT NULL: `observed_at`, `domain`, `metric_name`, `metric_value`, `severity`, `engine_mode`
- CHECK: `(domain='ws_latency' AND symbol IS NOT NULL) OR (domain<>'ws_latency')` (domain-specific symbol 必填)

**Indexes 大綱**：
- Hypertable time index 內建（`observed_at`）
- `(domain, metric_name, observed_at DESC)` — per-metric 時間序列 query
- `(symbol, observed_at DESC) WHERE symbol IS NOT NULL` — per-symbol metric query
- `(severity, observed_at DESC) WHERE severity IN ('WARN','CRITICAL')` — alert dashboard hot query
- `(strategy_name, observed_at DESC) WHERE strategy_name IS NOT NULL` — per-strategy metric query

### 2.2 ENUM 列表 (per CR-X 對齊規則)

- `health_domain` ENUM 6 值
- `health_severity` ENUM 3 值（per CR-5 anomaly severity taxonomy 對齊 — M8 採 4 級 INFO/WARN/CRITICAL/HALT，M3 不含 HALT）

### 2.3 Hypertable 判斷

**結論：MUST hypertable**。理由（per E5 5.21 audit）：
- 估算 row 量：5min sampling × 6 domain × ~10 metric_name avg × 5 strategy × 25 symbol = ~21k row/day = ~7.6M row/yr
- 表大小估算（每 row ~250 byte）= ~1.9 GB/yr
- 6 month +1.25-2.5 GB（含 index）→ 占 PG buffer (4-8 GB) 16-63%
- Hypertable 7d chunk + 7d compression policy（80-90% compression ratio 預期）
- Retention 90d auto-drop policy（cold data 不留）

```sql
SELECT create_hypertable('learning.health_observations', 'observed_at',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists => TRUE);

ALTER TABLE learning.health_observations SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'domain, metric_name',
    timescaledb.compress_orderby = 'observed_at DESC'
);

SELECT add_compression_policy('learning.health_observations', INTERVAL '7 days');
SELECT add_retention_policy('learning.health_observations', INTERVAL '90 days');
```

---

## §3 Guard A/B/C Templates 大綱

### Guard A — table existence + 既有 schema 對齊驗證

- 若 `learning.health_observations` 已存在：驗 10 column 完整；缺即 RAISE
- 驗 TimescaleDB extension 存在（V096 prereq）

### Guard B — 不適用

V106 不 ALTER 既有 column type；本 spec 不設 Guard B 段。

### Guard C — CHECK constraint + ENUM 值齊全 + hypertable + index 對齊驗證

- `health_domain` ENUM 6 值齊全
- `health_severity` ENUM 3 值齊全（INFO / WARN / CRITICAL）
- `engine_mode` CHECK 4 值齊全
- Hypertable 已建立 + chunk_time_interval = 7 days 驗（query `timescaledb_information.hypertables`）
- Compression policy 存在驗（query `timescaledb_information.compression_settings`）
- Retention policy 存在驗（query `timescaledb_information.policy_stats`）
- Indexes (≥ 4 partial + base) 對齊

---

## §4 Linux PG Empirical Dry-Run Checklist (placeholder)

### 4.1 必跑 SQL (3-5 條 placeholder query)

```bash
# Query 1: _sqlx_migrations head 確認
ssh trade-core "psql -d trading_ai -c 'SELECT max(version) FROM _sqlx_migrations'"

# Query 2: TimescaleDB extension 確認
ssh trade-core "psql -d trading_ai -c \"SELECT extversion FROM pg_extension WHERE extname='timescaledb'\""

# Query 3: V106 apply 後驗 hypertable 真建立
ssh trade-core "psql -d trading_ai -c \"SELECT hypertable_name, num_dimensions, num_chunks FROM timescaledb_information.hypertables WHERE hypertable_name='health_observations'\""

# Query 4: compression policy 真設
ssh trade-core "psql -d trading_ai -c \"SELECT * FROM timescaledb_information.compression_settings WHERE hypertable_name='health_observations'\""

# Query 5: retention policy 真設
ssh trade-core "psql -d trading_ai -c \"SELECT * FROM timescaledb_information.policy_stats WHERE hypertable_name='health_observations'\""
```

### 4.2 Idempotent 雙跑驗

per V055 5-round loop + V083/V084 incident precedent，V106.sql 必跑兩次：
- 第一次：CREATE TABLE + hypertable + policies → 0 RAISE
- 第二次：全 IF NOT EXISTS / IF NOT existing policy → 0 RAISE / 0 重複 policy

### 4.3 engine restart 實測

per a19797d 教訓：
- `restart_all.sh --rebuild` 後驗 engine.log 無 sqlx panic
- 驗 health writer spawn log（Sprint 1A-β writer 接線後）

---

## §5 Cross-V### Dependencies

per CR-9 cross-V### dependency graph：

| V### | 依賴 | 理由 |
|---|---|---|
| V106 | V096 boundary (TimescaleDB extension ready) | hypertable infra prereq |
| V106 | 無 FK 依賴 | health_observations 是觀測層，無 FK to other tables |

**Sprint 1A-β dispatch ordering**：V106 (M3) 可獨立 land；不阻擋其他 module。

---

## §6 Cross-References

- v5.8 §2 M3 Health domain: `srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md`
- E5 5.21 hypertable audit: `srv/docs/CCAgentWorkSpace/E5/workspace/reports/2026-05-21--v58_hypertable_audit.md`
- ADR-alignment: per R4 建議補（M3 對應 ADR 待 PA dispatch 期 land）
- CR-X 對應 PA dispatch consolidation: per v5.8 §11
- 範式參考 V103/V104 spec: `srv/docs/execution_plan/2026-05-21--v103_v104_earn_hypotheses_schema_spec.md`

---

## §7 Sign-off Table

| Role | Status | Date | Note |
|---|---|---|---|
| MIT Drafted (placeholder) | DONE | 2026-05-21 | Placeholder frontmatter + 大綱 reserve only |
| PA | PENDING | — | Full DDL Sprint 1A-β |
| E4 | PENDING | — | Regression after IMPL |
| E5 | PENDING | — | Hypertable + retention 驗 critical (high-frequency table) |
| PM | PENDING | — | Sprint 1A-β closure |

**END V106 spec placeholder**
