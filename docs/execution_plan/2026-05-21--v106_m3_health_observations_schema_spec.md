---
spec: V106 — M3 Health Observations Schema (Hypertable Mandatory)
date: 2026-05-21
author: MIT (full DDL spec; lifts placeholder from earlier same-day frontmatter)
phase: v5.8 Sprint 1A-β schema prerequisite CRITICAL deliverable
status: SPEC-FULL-V0(MIT 起草;待 PA C9 Linux PG dry-run 實測補資料 + Sprint 1A-β reviewer 對齊後 SPEC-FINAL)
sprint: Sprint 1A-β (DESIGN phase; IMPL 後續 sprint)
size estimate: 80-120 LOC SQL (CREATE TABLE 1 hypertable + 3 indexes + 1 ENUM + Guard A/C + compression + retention) + 60-90 hr E1 IMPL (含 Linux PG dry-run x 2 round + healthcheck wiring deferred to Sprint 1B)
depend on:
  - V096 boundary (TimescaleDB extension; drop dead learning tables)
  - V098 (governance.audit_log; referenced by M3 amplification cap H-11 audit trail cross-ref)
depended by:
  - V112 (M1 LAL) — HEALTH_DEGRADED state 透過 amplification cap H-11 觸發 LAL Tier 降階 (cross-ref 非 FK,單向 query)
  - M8 anomaly amplification cap H-11 (cross-ref 非 FK,單向 query;1-anomaly = 1-state-change/24h)
  - M11 replay (V107) wall-clock budget overrun (per ADR-0038 §Decision 5) emit HEALTH_WARN
parent specs:
  - srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md §2 M3 Health domain
  - srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md §6 cross-V### dependency graph
  - srv/docs/CCAgentWorkSpace/E5/workspace/reports/2026-05-21--v58_hypertable_audit.md (E5 hypertable + retention 驗)
  - srv/docs/adr/0042-m3-health-monitoring.md (V106 schema 對應治理 authority；ADR-0042 Decision 3+4 為 column 設計邊界；R4 NEW-H-2 reverse-ref patch 2026-05-21)
mirror precedent:
  - srv/docs/execution_plan/2026-05-21--v103_v104_earn_hypotheses_schema_spec.md (format reference; 940 行 baseline)
  - srv/docs/execution_plan/2026-05-21--v103_v104_linux_pg_dry_run.md (Linux PG dry-run protocol 範式)
  - srv/sql/migrations/V094__fills_close_maker_audit.sql (Guard A/B/C + partial index 範式)
  - srv/sql/migrations/templates/schema_guard_template.sql (Guard A/B/C template)
scope: design / spec only — 不寫 V106.sql 實檔,不在 Mac 跑 SQL,不改 Rust/Python writer,不執行 PG,不擴張到 module 行為(PA/QC sub-agent 同時段在寫)
---

# V106 M3 Health Observations Schema Migration Spec

## §0 TL;DR

- **V106 新增 1 個 hypertable**:`learning.health_observations`(high-frequency per-domain health metric snapshots)。
- **6 hot domains**(per v5.8 §2 M3):`ws_latency` / `rest_success_rate` / `db_backlog` / `disk_usage` / `cpu_mem` / `strategy_level`。
- **4 health state ENUM**:`HEALTH_OK` / `HEALTH_WARN` / `HEALTH_DEGRADED` / `HEALTH_CRITICAL`(per v5.8 §2 M3 + ADR-0036 severity taxonomy 對齊 — M8 採 INFO/WARN/CRITICAL 三級,M3 加 OK + 升 DEGRADED 中間層做 amplification cap H-11 限流)。
- **`amplification_loop_24h_count` 欄位**(per H-11 cap):同一 domain 24h 內 state change 計數,exceeded ≥ 2 → fail-closed 拒絕新 state transition + WARN(防 M8 anomaly → M3 state change → 觸 M11 replay → 更多 anomaly 的雪球)。
- **Hypertable mandatory**:7d chunk + 7d compression policy + 90d retention(per E5 5.21 audit;6mo +1.25-2.5 GB 占 PG buffer 16-63% 必 hypertable + compression)。
- **engine_mode CHECK 4 值齊全**(paper / demo / live_demo / live);training filter 必含 `IN ('live','live_demo')`(per CLAUDE.md §七 + MIT memory baseline)。
- **Cross-V### dependencies**:V096 boundary(TimescaleDB extension)+ V098(governance.audit_log cross-ref);**無 hard FK**(M3 是觀測層,FK 太重;cross-ref 走 query-time JOIN)。
- **5 audit field** per V103 EXTEND 範式:`created_by` / `created_at` / `updated_by` / `updated_at` / `source_version`。
- **Hot-path indexes 4 個**:domain-time / state-time / symbol-time(partial)/ strategy-time(partial)。
- **Sprint 1A-β scheduling**:M3 hypertable 是高頻表,必在 M2 / M11 module writer wire 前 land(避免 row backlog;per E5 hypertable audit)。
- **Linux PG empirical dry-run mandatory**(per CLAUDE.md §Data, Migrations, And Validation + V055 5-round loop precedent)。

---

## §1 Context + 為什麼

### 1.1 v5.8 §2 M3 module 出處 + 動機

v5.8 §2 M3 Health-Aware Degradation module 列出 6 個健康觀測 domain,跨 OpenClaw 多個子系統:

| Domain | 採樣源 | 採樣頻率 | 樣本基數 |
|---|---|---|---|
| **ws_latency** | bybit_connector WS heartbeat → tick arrival latency(per-symbol) | 30s | 25 symbol × 1 metric (p99) = 25 row/sample |
| **rest_success_rate** | per-endpoint API call success/total ratio(rolling 1h window) | 60s | ~20 endpoint × 1 metric = 20 row/sample |
| **db_backlog** | INSERT queue depth / writer queue size(per-writer) | 30s | ~10 writer × 2 metric = 20 row/sample |
| **disk_usage** | PG data dir + log dir + binary backup dir | 300s | 3 path × 1 metric = 3 row/sample |
| **cpu_mem** | per-process RSS + CPU%(engine / python-api / health-monitor / etc) | 60s | ~6 process × 2 metric = 12 row/sample |
| **strategy_level** | per-strategy active count / signal rate / position count | 60s | 5 strategy × 25 symbol × 3 metric = 375 row/sample |

**row 量級估算**(per E5 hypertable audit):
- ws_latency:25 row/30s × 2880 sample/day = 72k row/day
- rest_success_rate:20 row/60s × 1440 = 28.8k row/day
- db_backlog:20 row/30s × 2880 = 57.6k row/day
- disk_usage:3 row/300s × 288 = 0.8k row/day
- cpu_mem:12 row/60s × 1440 = 17.3k row/day
- strategy_level:375 row/60s × 1440 = 540k row/day(**最大**)
- **合計 ~716k row/day = ~261M row/yr** (每 row 估 ~250 byte) = ~65 GB/yr (uncompressed)

**6 month +1.25-2.5 GB(已 compress 後)估算占 PG buffer (4-8 GB) 16-63%** → hypertable + compression mandatory。

### 1.2 H-11 amplification cap 設計

per PA dispatch consolidation §1 H-11 + E3 + CC 共識:M8 anomaly → M3 state change → M11 replay → 更多 anomaly 的雪球效應風險。

**Cap rule**:同一 `(domain, observed_at::date)` 24h 內 `state_prev → state` transitions ≥ 2 → 新 transition emit FAIL-CLOSED rejection(write `state='HEALTH_CRITICAL'` + log,但不更新 active state machine)。

V106 schema 提供 `amplification_loop_24h_count` 欄位讓 writer 預計算(避免每次 INSERT 都 retry SELECT count(*));writer 端 query `SELECT count(DISTINCT state) FROM health_observations WHERE domain=$1 AND observed_at > now() - INTERVAL '24 hours'` 後寫入。

### 1.3 v5.8 §2 M3 與本 spec 衝突仲裁

v5.8 §2 M3 列「Health domain 5 domain」(漏 strategy_level);本 spec 採 PA dispatch §6 共識 6 domain(加 strategy_level)。**理由**:strategy_level 是 M3 → M7 decay signal source(per ADR-0038 OQ-4 + CR-7 dedup contract);M3 不含 strategy_level → M7 失去 single decay authority 的 health input。

### 1.4 Cross-V### 影響

| 下游 | M3 觸發路徑 | 是否 FK |
|---|---|---|
| **V112 M1 LAL** | HEALTH_DEGRADED → LAL 1 reparam halt(per ADR-0034 + v5.8 §2 M3 line 140) | 否(cross-ref query;FK 太重) |
| **M8 anomaly amplification cap** | M8 anomaly emit → M3 state change → H-11 cap 拒(若 ≥ 2 in 24h) | 否(cross-ref query) |
| **M11 replay wall-clock budget**(per ADR-0038 §Decision 5) | replay > 4h → emit M3 HEALTH_WARN(per CR-7 dedup contract M3 為 single health authority) | 否(cross-ref query) |

### 1.5 不在本 spec 範圍

- ❌ V106.sql 實檔寫作(E1 IMPL 工作)
- ❌ Mac 跑 V106 SQL(必 Linux PG empirical)
- ❌ Rust health writer code(`rust/openclaw_engine/src/health/observation_writer.rs`;E1 IMPL 工作)
- ❌ Python healthcheck wiring(`helper_scripts/passive_wait_healthcheck.py` 加 `check_health_observations_writer()`;Sprint 1B 工作)
- ❌ ML training pipeline integration(M3 是治理層,非 ML training feature)
- ❌ State machine logic implementation(per ADR-0036 + ADR-0008 既有 state machine infra;本 spec 只定義 schema)
- ❌ M8 / M11 / M2 cross-module trigger spec(對應 V109 / V107 / V105 各自 spec 寫;本 spec 只列 cross-ref 不擴張)

---

## §2 Schema Design

### 2.1 `learning.health_observations` 表定義

```sql
CREATE TABLE IF NOT EXISTS learning.health_observations (
    observation_id              BIGSERIAL,
    observed_at                 TIMESTAMPTZ NOT NULL,
    domain                      TEXT NOT NULL
                                CHECK (domain IN (
                                    'ws_latency',
                                    'rest_success_rate',
                                    'db_backlog',
                                    'disk_usage',
                                    'cpu_mem',
                                    'strategy_level'
                                )),
    metric_name                 TEXT NOT NULL,
    state                       TEXT NOT NULL
                                CHECK (state IN (
                                    'HEALTH_OK',
                                    'HEALTH_WARN',
                                    'HEALTH_DEGRADED',
                                    'HEALTH_CRITICAL'
                                )),
    state_prev                  TEXT
                                CHECK (state_prev IS NULL OR state_prev IN (
                                    'HEALTH_OK',
                                    'HEALTH_WARN',
                                    'HEALTH_DEGRADED',
                                    'HEALTH_CRITICAL'
                                )),
    dwell_time_sec              INTEGER,
    metric_value                NUMERIC(18,8) NOT NULL,
    metric_threshold            NUMERIC(18,8),
    amplification_loop_24h_count INTEGER NOT NULL DEFAULT 0,
    symbol                      TEXT,
    strategy_name               TEXT,
    evidence_json               JSONB,
    engine_mode                 TEXT NOT NULL
                                CHECK (engine_mode IN ('paper','demo','live_demo','live')),
    created_by                  TEXT NOT NULL DEFAULT 'health_monitor',
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by                  TEXT,
    updated_at                  TIMESTAMPTZ,
    source_version              TEXT NOT NULL DEFAULT 'V106',
    PRIMARY KEY (observation_id, observed_at)
);
```

### 2.2 Column 設計理由

| Column | Type | NULL | 設計理由 |
|---|---|---|---|
| `observation_id` | BIGSERIAL | NOT NULL | sequential ID(per hypertable best practice;PK 必含 partition column,因此複合 `(observation_id, observed_at)`) |
| `observed_at` | TIMESTAMPTZ | NOT NULL | hypertable time dimension;UTC 統一(per CLAUDE.md §六 Mac/Linux runtime) |
| `domain` | TEXT + CHECK 6 值 | NOT NULL | 6 hot domain 顯式枚舉;crypto + OpenClaw 子系統觀測層完整覆蓋;新 domain 需 amend ENUM(controlled drift) |
| `metric_name` | TEXT | NOT NULL | metric 名稱(e.g. `ws_latency_ms_p99`、`rest_success_rate_24h`、`db_writer_queue_depth`)— 不 enum 因 metric 名稱動態擴增,enum 易過時;writer 端責任維持 naming consistency |
| `state` | TEXT + CHECK 4 值 | NOT NULL | 4 state ENUM:`HEALTH_OK` < `HEALTH_WARN` < `HEALTH_DEGRADED` < `HEALTH_CRITICAL`;DEGRADED 是 M3 → M1 LAL halt trigger 中間層,WARN 是 alert-only 不觸 halt |
| `state_prev` | TEXT + CHECK 4 值 + NULL | YES | 前一次 state(用於 H-11 amplification count + state transition audit);第一次觀測 NULL |
| `dwell_time_sec` | INTEGER | YES | 上次 state 停留時間(秒);用於 transition rate analysis;第一次觀測 NULL |
| `metric_value` | NUMERIC(18,8) | NOT NULL | 高精度(避 FLOAT 精度誤差;crypto funding rate 小數 6 位、latency ms 整數、CPU% 小數 4 位皆能容);per `db-schema-design-financial-time-series` skill |
| `metric_threshold` | NUMERIC(18,8) | YES | 觸發 state transition 的閾值(reference 當下 active config);用於 audit trail;config 可變但 historical row 鎖當下 threshold |
| `amplification_loop_24h_count` | INTEGER + DEFAULT 0 | NOT NULL | per H-11 cap;writer 預計算 24h 同 domain state transition 次數;≥ 2 觸 fail-closed reject |
| `symbol` | TEXT | YES | domain ∈ (ws_latency, strategy_level) 時非 null;其他 domain null;CHECK constraint 不強制(domain-specific NULL 容忍) |
| `strategy_name` | TEXT | YES | domain='strategy_level' 時非 null;其他 null |
| `evidence_json` | JSONB | YES | 富 context:採樣 window、threshold derivation、raw computation、上下文時間戳;debug 用 |
| `engine_mode` | TEXT + CHECK 4 值 | NOT NULL | 4 值齊全(per CLAUDE.md §七 + MIT memory baseline);training filter 必 `IN ('live','live_demo')` |
| `created_by` | TEXT + DEFAULT 'health_monitor' | NOT NULL | per V103 EXTEND 範式;預設 writer process 名;允許 `cowork-agent` / `operator` / `m11_replay_engine` 多 actor |
| `created_at` | TIMESTAMPTZ + DEFAULT now() | NOT NULL | row insert 時間(server-side trusted) |
| `updated_by` | TEXT | YES | 後續 update(若 state transition 後 backfill amplification count)|
| `updated_at` | TIMESTAMPTZ | YES | last update 時間 |
| `source_version` | TEXT + DEFAULT 'V106' | NOT NULL | schema version tag;未來 schema migration audit;預設 V106 |

### 2.3 為什麼不採 health_severity ENUM `(INFO / WARN / CRITICAL)`(與 M8 對齊)

per ADR-0036 + v5.8 §2 M8 anomaly severity 採 `INFO / WARN / CRITICAL / HALT` 4 級(per CR-X PA dispatch consolidation);M3 採 `HEALTH_OK / HEALTH_WARN / HEALTH_DEGRADED / HEALTH_CRITICAL` 是因:

- **M3 是 continuous-state observation**:每個 metric 必有當前 state(包括「正常」),OK 必須是 enum 值
- **M8 是 event-discrete anomaly**:沒有「正常 anomaly」概念,INFO 即可代表 baseline noise
- **DEGRADED 是 M3 對 LAL halt 中間層**:WARN 不 halt(只 alert) + DEGRADED 觸 LAL 1 halt + CRITICAL 觸 LAL 全 halt;M8 不需此中間層

兩 enum 不同對齊規則由 PA dispatch §1 CR-X 仲裁;本 spec 採 PA verdict(M3 4 state / M8 4 severity 各自 enum)。

### 2.4 為什麼 `metric_threshold` NULL allowed

部分 metric 是 stateful drift detection(無單點 threshold,如 `correlation_eigendecomp_shift`),不適用固定 threshold;NULL 容忍。

---

## §3 Hypertable / Partitioning

### 3.1 Hypertable 設定

```sql
SELECT create_hypertable(
    'learning.health_observations',
    'observed_at',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists => TRUE
);
```

**chunk_time_interval = 7d 理由**(per `db-schema-design-financial-time-series` skill):
- 716k row/day × 7d = ~5M row/chunk
- chunk size ~1.25 GB (uncompressed)→ 適合 PG memory hint
- 7d 對齊 weekly rollup query pattern

### 3.2 Compression policy

```sql
ALTER TABLE learning.health_observations SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'domain, metric_name',
    timescaledb.compress_orderby = 'observed_at DESC, observation_id DESC'
);

SELECT add_compression_policy(
    'learning.health_observations',
    INTERVAL '7 days'
);
```

- `compress_segmentby = 'domain, metric_name'`:同 domain × metric 連續 row segment 壓縮率最高(80-90%)
- `compress_orderby = 'observed_at DESC, observation_id DESC'`:time-DESC 最近資料 close 在 chunk 邊界,decompress 成本最低
- 7d 後自動壓縮(避免 hot data 壓縮影響寫入)

### 3.3 Retention policy

```sql
SELECT add_retention_policy(
    'learning.health_observations',
    INTERVAL '90 days'
);
```

- 90d 後自動 drop chunk
- 對 long-term trend 分析需求走 daily aggregate 表(本 spec 不含,Sprint 1B+ 補)

### 3.4 為什麼不採 30d 或 365d retention

- **30d 過短**:M3 wall-clock budget overrun(per ADR-0038 §Decision 5)需 30d audit 連續 7d 超 budget → operator 仲裁;30d 退保留無法覆蓋 dual-cycle observation
- **365d 過長**:占 storage 過多(~65 GB compress 後仍占大量 buffer);M3 是 operational metric 非 strategy alpha,90d 足夠 trend analysis;long-term trend 走 aggregate 表

---

## §4 Index Strategy

### 4.1 Hot-path query → index map

per OpenClaw `db-schema-design-financial-time-series` skill + v5.8 §2 M3 query pattern:

| Query pattern | 命中 index | 範例 SQL |
|---|---|---|
| per-domain metric timeline | `idx_health_domain_metric_observed` | `SELECT * FROM learning.health_observations WHERE domain='ws_latency' AND metric_name='p99' ORDER BY observed_at DESC LIMIT 100` |
| per-state alert dashboard | `idx_health_state_observed` (partial) | `SELECT * FROM learning.health_observations WHERE state IN ('HEALTH_DEGRADED','HEALTH_CRITICAL') ORDER BY observed_at DESC` |
| per-symbol metric query | `idx_health_symbol_observed` (partial) | `SELECT * FROM learning.health_observations WHERE symbol='BTCUSDT' AND domain='ws_latency' ORDER BY observed_at DESC` |
| per-strategy health query | `idx_health_strategy_observed` (partial) | `SELECT * FROM learning.health_observations WHERE strategy_name='grid' AND domain='strategy_level' ORDER BY observed_at DESC` |

### 4.2 Index DDL

```sql
-- 主要 hot-path: per-domain metric timeline (covering 6 domains × ~10 metric_name avg)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_health_domain_metric_observed
    ON learning.health_observations (domain, metric_name, observed_at DESC);

-- Alert dashboard hot-path: state-degraded query (partial,絕大多數 row state=OK 不索引)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_health_state_observed
    ON learning.health_observations (state, observed_at DESC)
    WHERE state IN ('HEALTH_DEGRADED', 'HEALTH_CRITICAL');

-- per-symbol query (partial,僅 ws_latency / strategy_level 兩 domain 有 symbol)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_health_symbol_observed
    ON learning.health_observations (symbol, observed_at DESC)
    WHERE symbol IS NOT NULL;

-- per-strategy query (partial,僅 strategy_level domain 有 strategy_name)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_health_strategy_observed
    ON learning.health_observations (strategy_name, observed_at DESC)
    WHERE strategy_name IS NOT NULL;
```

### 4.3 Partial index 理由

per `db-schema-design-financial-time-series` skill §4.2:partial index 對 filter 條件穩定的場景大幅縮小索引(60-80% 空間節省):
- state DEGRADED/CRITICAL 預期 < 1% 整體 row → partial index 縮 99%
- symbol IS NOT NULL 約 50% row (ws_latency + strategy_level 兩 domain)→ partial index 縮 50%
- strategy_name IS NOT NULL 約 75% row (strategy_level domain ~540k/716k daily)→ partial index 縮 25%(仍值得做,加速 query)

### 4.4 為什麼不加 `(engine_mode, observed_at)` index

engine_mode CHECK 4 值 + 預期 `IN ('live','live_demo')` filter 在 99% query 中出現;但 cardinality 太低(4 值)→ index selectivity 不佳;PG 會用 bitmap scan 或全表 scan;不需顯式 index。

---

## §5 Guard A / B / C(per CLAUDE.md §Data, Migrations, And Validation + V094 mirror)

V106 涉及 1 個 NEW hypertable CREATE,需 Guard A + Guard C(無 ALTER 既有 column 不需 Guard B)。

### 5.1 Guard A — table existence + 既有 schema 對齊驗證

```sql
-- ============================================================
-- Guard A: V106 預檢 — 若 learning.health_observations 已存在,必驗 V106 spec
-- column 全俱在;缺即 RAISE。同時驗 TimescaleDB extension + V096 boundary。
-- ============================================================
DO $$
DECLARE v_missing TEXT[];
DECLARE v_ts_ver TEXT;
BEGIN
    -- TimescaleDB extension prereq (V096 boundary)
    SELECT extversion INTO v_ts_ver
    FROM pg_extension WHERE extname='timescaledb';
    IF v_ts_ver IS NULL THEN
        RAISE EXCEPTION
            'V106 Guard A FAIL: TimescaleDB extension missing. '
            'V096 boundary not satisfied. Apply V096 first.';
    END IF;

    -- learning.health_observations 已存在的情境下 check column 完整性
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='learning' AND table_name='health_observations'
    ) THEN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'observation_id', 'observed_at', 'domain', 'metric_name',
            'state', 'state_prev', 'dwell_time_sec',
            'metric_value', 'metric_threshold',
            'amplification_loop_24h_count', 'symbol', 'strategy_name',
            'evidence_json', 'engine_mode',
            'created_by', 'created_at', 'updated_by', 'updated_at',
            'source_version'
        ]) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema='learning' AND table_name='health_observations'
              AND column_name=c
        );
        IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
            RAISE EXCEPTION
                'V106 Guard A FAIL: learning.health_observations exists but missing columns: %. '
                'Possible legacy stub conflict — resolve schema reconciliation before applying V106.',
                v_missing;
        END IF;
    END IF;

    -- governance.audit_log 必須存在(M3 → governance cross-ref 雖無 FK 但 query JOIN 需要)
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='governance' AND table_name='audit_log'
    ) THEN
        RAISE EXCEPTION
            'V106 Guard A FAIL: governance.audit_log missing — '
            'V098 must apply before V106 (cross-ref query target). Verify _sqlx_migrations.';
    END IF;
END $$;
```

### 5.2 Guard B — 不適用

V106 不 ALTER 既有 column;無 type-sensitive 檢查需求。

### 5.3 Guard C — CHECK constraint + ENUM 值齊全 + hypertable + index 對齊驗證

```sql
-- ============================================================
-- Guard C: V106 預檢 — 重跑 V106 時 idempotent 檢查 CHECK constraint + 
-- hypertable + compression policy + retention policy + index 對齊
-- ============================================================
DO $$
DECLARE v_actual TEXT;
DECLARE v_chunk_interval BIGINT;
DECLARE v_compress_after BIGINT;
DECLARE v_retention_after BIGINT;
BEGIN
    -- domain CHECK constraint 6 值齊全
    SELECT pg_get_constraintdef(oid) INTO v_actual
    FROM pg_constraint
    WHERE conrelid='learning.health_observations'::regclass
      AND conname LIKE '%domain%check%';
    IF v_actual IS NOT NULL THEN
        IF position('ws_latency' IN v_actual) = 0
           OR position('rest_success_rate' IN v_actual) = 0
           OR position('db_backlog' IN v_actual) = 0
           OR position('disk_usage' IN v_actual) = 0
           OR position('cpu_mem' IN v_actual) = 0
           OR position('strategy_level' IN v_actual) = 0
        THEN
            RAISE EXCEPTION
                'V106 Guard C FAIL: learning.health_observations domain CHECK enum mismatch. '
                'Actual: %. Expected to contain all 6 domain values '
                '(ws_latency/rest_success_rate/db_backlog/disk_usage/cpu_mem/strategy_level).',
                v_actual;
        END IF;
    END IF;

    -- state CHECK 4 值齊全
    SELECT pg_get_constraintdef(oid) INTO v_actual
    FROM pg_constraint
    WHERE conrelid='learning.health_observations'::regclass
      AND conname LIKE '%state%check%'
      AND conname NOT LIKE '%state_prev%';
    IF v_actual IS NOT NULL THEN
        IF position('HEALTH_OK' IN v_actual) = 0
           OR position('HEALTH_WARN' IN v_actual) = 0
           OR position('HEALTH_DEGRADED' IN v_actual) = 0
           OR position('HEALTH_CRITICAL' IN v_actual) = 0
        THEN
            RAISE EXCEPTION
                'V106 Guard C FAIL: learning.health_observations state CHECK enum mismatch. '
                'Actual: %. Expected HEALTH_OK/HEALTH_WARN/HEALTH_DEGRADED/HEALTH_CRITICAL.',
                v_actual;
        END IF;
    END IF;

    -- engine_mode CHECK 4 值齊全
    SELECT pg_get_constraintdef(oid) INTO v_actual
    FROM pg_constraint
    WHERE conrelid='learning.health_observations'::regclass
      AND conname LIKE '%engine_mode%check%';
    IF v_actual IS NOT NULL THEN
        IF position('paper' IN v_actual) = 0
           OR position('demo' IN v_actual) = 0
           OR position('live_demo' IN v_actual) = 0
           OR position('live' IN v_actual) = 0
        THEN
            RAISE EXCEPTION
                'V106 Guard C FAIL: engine_mode CHECK enum mismatch. '
                'Actual: %. Expected paper/demo/live_demo/live.',
                v_actual;
        END IF;
    END IF;

    -- Hypertable 已建立 + chunk_time_interval = 7 days
    SELECT
        EXTRACT(EPOCH FROM time_interval) * 1000000  -- 轉 microseconds
    INTO v_chunk_interval
    FROM timescaledb_information.dimensions
    WHERE hypertable_name='health_observations'
      AND column_name='observed_at';
    -- 7 days = 604800 sec = 604800000000 microseconds
    IF v_chunk_interval IS NOT NULL AND v_chunk_interval != 604800000000 THEN
        RAISE EXCEPTION
            'V106 Guard C FAIL: learning.health_observations chunk_time_interval mismatch. '
            'Actual: % microseconds. Expected: 604800000000 (7 days).',
            v_chunk_interval;
    END IF;

    -- Compression policy 存在(7 day after)
    IF NOT EXISTS (
        SELECT 1 FROM timescaledb_information.jobs
        WHERE proc_name='policy_compression'
          AND hypertable_name='health_observations'
    ) THEN
        -- 注意: 重跑時 add_compression_policy IF NOT EXISTS;首次 apply 必檢查
        RAISE NOTICE 'V106 Guard C NOTE: compression policy not yet applied for health_observations. '
                     'Will be added by main migration body.';
    END IF;

    -- Retention policy 存在(90 day after)
    IF NOT EXISTS (
        SELECT 1 FROM timescaledb_information.jobs
        WHERE proc_name='policy_retention'
          AND hypertable_name='health_observations'
    ) THEN
        RAISE NOTICE 'V106 Guard C NOTE: retention policy not yet applied for health_observations. '
                     'Will be added by main migration body.';
    END IF;
END $$;
```

### 5.4 Guard 設計理念(per V094 mirror)

| Guard | 觸發場景 | RAISE 條件 | NOT RAISE 條件(idempotent)|
|---|---|---|---|
| A | NEW table 已存在但 column 缺;TimescaleDB extension 缺;governance.audit_log 缺 | RAISE | 全 column 俱在 / table 不存在(首次跑)|
| C | CHECK constraint 缺 enum 值;hypertable interval 不對 | RAISE | constraint 不存在(首次跑)/ constraint 完整(重跑) |
| C policy | compression / retention policy 首次跑不存在 | NOTICE(不 RAISE,migration body 會建)| policy 已存在重跑(skip)|

重跑 V106 第二次必不 RAISE(idempotency per CLAUDE.md §Data, Migrations, And Validation V055/V083/V084 incident precedent)。

---

## §6 Migration up + down SQL

### 6.1 Migration UP(完整 V106.sql 設計)

```sql
-- ============================================================
-- V106: learning.health_observations + hypertable + compression + retention
-- M3 Health Observations Schema (6 domain × 4 state × hypertable)
-- ============================================================

-- Step 1: Guard A (per §5.1)
-- [全文見 §5.1]

-- Step 2: Guard C 預檢 (per §5.3 重跑 idempotency)
-- [全文見 §5.3]

-- Step 3: CREATE TABLE
CREATE TABLE IF NOT EXISTS learning.health_observations (
    -- (per §2.1 完整 DDL)
    observation_id              BIGSERIAL,
    observed_at                 TIMESTAMPTZ NOT NULL,
    domain                      TEXT NOT NULL CHECK (domain IN (...)),
    metric_name                 TEXT NOT NULL,
    state                       TEXT NOT NULL CHECK (state IN (...)),
    state_prev                  TEXT CHECK (state_prev IS NULL OR state_prev IN (...)),
    dwell_time_sec              INTEGER,
    metric_value                NUMERIC(18,8) NOT NULL,
    metric_threshold            NUMERIC(18,8),
    amplification_loop_24h_count INTEGER NOT NULL DEFAULT 0,
    symbol                      TEXT,
    strategy_name               TEXT,
    evidence_json               JSONB,
    engine_mode                 TEXT NOT NULL CHECK (engine_mode IN ('paper','demo','live_demo','live')),
    created_by                  TEXT NOT NULL DEFAULT 'health_monitor',
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by                  TEXT,
    updated_at                  TIMESTAMPTZ,
    source_version              TEXT NOT NULL DEFAULT 'V106',
    PRIMARY KEY (observation_id, observed_at)
);

-- Step 4: Hypertable
SELECT create_hypertable(
    'learning.health_observations',
    'observed_at',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists => TRUE
);

-- Step 5: Compression
ALTER TABLE learning.health_observations SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'domain, metric_name',
    timescaledb.compress_orderby = 'observed_at DESC, observation_id DESC'
);

-- Step 6: Compression + Retention policies (idempotent)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM timescaledb_information.jobs
        WHERE proc_name='policy_compression' AND hypertable_name='health_observations'
    ) THEN
        PERFORM add_compression_policy('learning.health_observations', INTERVAL '7 days');
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM timescaledb_information.jobs
        WHERE proc_name='policy_retention' AND hypertable_name='health_observations'
    ) THEN
        PERFORM add_retention_policy('learning.health_observations', INTERVAL '90 days');
    END IF;
END $$;

-- Step 7: Hot-path indexes (CONCURRENTLY for non-blocking)
-- (per §4.2)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_health_domain_metric_observed
    ON learning.health_observations (domain, metric_name, observed_at DESC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_health_state_observed
    ON learning.health_observations (state, observed_at DESC)
    WHERE state IN ('HEALTH_DEGRADED', 'HEALTH_CRITICAL');

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_health_symbol_observed
    ON learning.health_observations (symbol, observed_at DESC)
    WHERE symbol IS NOT NULL;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_health_strategy_observed
    ON learning.health_observations (strategy_name, observed_at DESC)
    WHERE strategy_name IS NOT NULL;

-- Step 8: COMMENT (audit metadata)
COMMENT ON TABLE learning.health_observations IS
    'M3 Health Observations Hypertable (V106). 6 domain × 4 state × per-symbol/strategy 觀測;'
    'amplification cap H-11 enforced via writer-side query; 7d chunk + 7d compression + 90d retention.';

COMMENT ON COLUMN learning.health_observations.amplification_loop_24h_count IS
    'H-11 cap: 24h 同 domain state change 計數;writer 預計算;≥ 2 fail-closed reject 新 transition。';
```

### 6.2 Migration DOWN(rollback;dev-only,production 慎用)

```sql
-- ============================================================
-- V106 ROLLBACK: 刪 hypertable + policies + indexes + table
-- ⚠️ DESTRUCTIVE: 90d 之內所有 health observations 全 drop;不可恢復。
-- 僅 dev/staging 使用;production rollback 走 V### 升級而非 down。
-- ============================================================

-- Step 1: Remove policies first (避免 dangling jobs)
SELECT remove_compression_policy('learning.health_observations', if_exists => TRUE);
SELECT remove_retention_policy('learning.health_observations', if_exists => TRUE);

-- Step 2: Drop indexes (CONCURRENTLY 不能在 transaction 內;rollback 走獨立 statement)
DROP INDEX CONCURRENTLY IF EXISTS learning.idx_health_strategy_observed;
DROP INDEX CONCURRENTLY IF EXISTS learning.idx_health_symbol_observed;
DROP INDEX CONCURRENTLY IF EXISTS learning.idx_health_state_observed;
DROP INDEX CONCURRENTLY IF EXISTS learning.idx_health_domain_metric_observed;

-- Step 3: Drop hypertable + table (CASCADE 處理 chunks)
DROP TABLE IF EXISTS learning.health_observations CASCADE;
```

### 6.3 Idempotency 驗證

per V055 5-round loop + V083/V084 incident precedent,V106.sql 必跑兩次:
- 第一次:CREATE TABLE + hypertable + policies + indexes → 0 RAISE / 0 ERROR
- 第二次:全 IF NOT EXISTS / 已 hypertable / 已 policies → 0 RAISE / 0 重複 policy

---

## §7 Materialized View(本 spec 不需)

V106 不含 materialized view。理由:
- long-term trend aggregation 非本 spec scope(Sprint 1B+ 補 daily/weekly aggregate 表)
- M3 hot path query 走 partial index + hypertable chunk pruning,無需 mv 加速

未來 Sprint 1B+ 若加 daily aggregate:
```sql
-- 例(Sprint 1B+ 後續):
-- CREATE MATERIALIZED VIEW learning.health_observations_daily_agg AS
-- SELECT date_trunc('day', observed_at) AS day, domain, metric_name, state, count(*), avg(metric_value)
-- FROM learning.health_observations
-- WHERE engine_mode IN ('live','live_demo')
-- GROUP BY 1, 2, 3, 4;
```

---

## §8 Cross-V### Dependency + Cross-Ref Schema

### 8.1 Cross-V### dependency 圖

```
V096 (drop dead learning tables; TimescaleDB extension) ← V106 (prereq;hypertable infra)
V098 (governance.audit_log)                              ← V106 (cross-ref query target;非 FK)
V106 (M3 health observations; standalone)
       │
       ├─→ V112 (M1 LAL) — HEALTH_DEGRADED → LAL 1 reparam halt (cross-ref query)
       ├─→ V107 (M11 replay) — wall-clock > 4h → emit HEALTH_WARN (cross-ref query)
       └─→ V109 (M8 anomaly) — amplification cap H-11 (cross-ref query 1-anomaly = 1-state-change/24h)
```

### 8.2 為什麼 M3 是 standalone(無 hard FK)

per `db-schema-design-financial-time-series` skill §5 (engine_mode 隔離 + FK 設計):
- M3 是 observational sensor 不是 governance object
- FK 太重(每 INSERT 都查 FK target;30k+ INSERT/min 過熱)
- cross-ref query 走 join-time fetch(per pattern V094 + V083 既有)

### 8.3 V112 (M1 LAL) cross-ref pattern

```sql
-- 例: M1 LAL Tier 升階 eligibility check 需查 M3 incident-free 90d
SELECT COUNT(*) FROM learning.health_observations
WHERE strategy_name = 'grid'
  AND state IN ('HEALTH_DEGRADED', 'HEALTH_CRITICAL')
  AND observed_at > now() - INTERVAL '90 days'
  AND engine_mode IN ('live','live_demo');
-- > 0 → eligibility fail
```

### 8.4 M11 (V107) cross-ref pattern

```sql
-- 例: M11 nightly replay wall-clock > 4h → emit M3 HEALTH_WARN
INSERT INTO learning.health_observations
    (observed_at, domain, metric_name, state, state_prev, metric_value, 
     metric_threshold, engine_mode, evidence_json)
VALUES
    (now(), 'cpu_mem', 'm11_replay_wall_clock_sec', 'HEALTH_WARN', 'HEALTH_OK',
     15000, 14400, 'live',
     jsonb_build_object('source','m11_replay','replay_id', $1, 'budget_exceeded', true));
```

### 8.5 M8 anomaly amplification cap H-11 cross-ref pattern

```sql
-- 例: M8 anomaly emit → 查 M3 24h 同 domain state change 計數
SELECT COUNT(DISTINCT state) FROM learning.health_observations
WHERE domain = 'ws_latency'
  AND observed_at > now() - INTERVAL '24 hours'
  AND state != 'HEALTH_OK'
  AND engine_mode = 'live';
-- ≥ 2 → H-11 cap fail-closed,reject new M8 anomaly trigger
```

### 8.6 為什麼 V112 / V107 / V109 走 cross-ref 而非 FK

| 設計選擇 | 優 | 缺 | 採用 |
|---|---|---|---|
| **FK constraint** | 強約束;join 簡單 | INSERT cost(每筆查 FK target);schema drift 風險;hard dependency 鎖 dispatch sequence | ❌ 不採 |
| **Cross-ref query (本 spec)** | INSERT 0 overhead;dispatch sequence 解耦 | 弱約束;依 application logic 維持 referential integrity;需 healthcheck 補 | ✅ 採 |

---

## §9 Linux PG Empirical Dry-Run Protocol(mandatory)

per CLAUDE.md §Data, Migrations, And Validation + `feedback_v_migration_pg_dry_run.md` + V055 5-round loop / V083 / V084 incident chain,V106 涉及:
- TimescaleDB extension hypertable creation (PG-specific syntax)
- compression / retention policy add_*_policy() function 真實返回
- partial index CONCURRENTLY 在 hypertable chunks 上的行為
- CHECK constraint ENUM runtime semantic

**必先 Linux PG empirical 驗證**,禁 Mac mock pytest 代替。

### 9.1 PA C9 待補的 PG reflection query(spec sign-off 前必補)

per CLAUDE.md `docs/agents/context-loading.md` "PG Connection Examples"(Linux runtime authoritative):

```bash
# Connection (per V103/V104 dry-run §1):
# psql -h 127.0.0.1 -p 5432 -U trading_admin -d trading_ai
# .pgpass: *:5432:trading_ai:trading_admin:****

# Query 1: _sqlx_migrations head 確認
ssh trade-core "PGPASSWORD=\$(cat ~/.pgpass | grep trading_ai | cut -d: -f5) psql -h 127.0.0.1 -p 5432 -U trading_admin -d trading_ai -c 'SELECT max(version) FROM _sqlx_migrations'"
# Expected: ≥ V098 (V096 boundary + V097 LG-5 + V098 governance.audit_log 都 land)

# Query 2: TimescaleDB extension 確認
ssh trade-core "PGPASSWORD=\$(cat ~/.pgpass | grep trading_ai | cut -d: -f5) psql -h 127.0.0.1 -p 5432 -U trading_admin -d trading_ai -c \"SELECT extversion FROM pg_extension WHERE extname='timescaledb'\""
# Expected: ≥ 2.13 (per OpenClaw TimescaleDB minimum)

# Query 3: governance.audit_log 已 land 驗
ssh trade-core "PGPASSWORD=\$(cat ~/.pgpass | grep trading_ai | cut -d: -f5) psql -h 127.0.0.1 -p 5432 -U trading_admin -d trading_ai -c \"SELECT count(*) FROM information_schema.tables WHERE table_schema='governance' AND table_name='audit_log'\""
# Expected: 1 (V098 land 後)

# Query 4: learning.health_observations 是否已存在(legacy stub conflict 檢測)
ssh trade-core "PGPASSWORD=\$(cat ~/.pgpass | grep trading_ai | cut -d: -f5) psql -h 127.0.0.1 -p 5432 -U trading_admin -d trading_ai -c \"SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema='learning' AND table_name='health_observations'\""
# Expected: 0 rows (greenfield); 若 1 row → 觸 Guard A 反向檢查
```

**待 PA C9 補資料的 4 處 placeholder**(spec sign-off 前必更新):
1. `_sqlx_migrations` head 真實 = ?
2. TimescaleDB extension version 真實 = ?
3. governance.audit_log 已 land 確認 = ?
4. learning.health_observations stub 不存在確認 = ?

### 9.2 Round 1 — V106 SQL 真實 PG semantic empirical 驗證

```bash
# ssh trade-core 執行(不在 Mac 跑)
ssh trade-core "
  cd ~/BybitOpenClaw/srv && \
  PGPASSWORD=\$(cat ~/.pgpass | grep trading_ai | cut -d: -f5) \
  psql -h 127.0.0.1 -p 5432 -U trading_admin -d trading_ai \
    -v ON_ERROR_STOP=1 -f sql/migrations/V106__m3_health_observations_hypertable.sql
"
```

**Round 1 必驗 8 項**(empirical SELECT verify after V106 apply):

```sql
-- 1. learning.health_observations 表存在 + 19 columns
SELECT count(*) FROM information_schema.columns
WHERE table_schema='learning' AND table_name='health_observations';
-- Expected: 19

-- 2. Hypertable 真建立 + chunk_time_interval = 7 days
SELECT hypertable_name, time_interval, column_name
FROM timescaledb_information.dimensions
WHERE hypertable_name='health_observations';
-- Expected: 1 row; time_interval = '7 days'; column_name = 'observed_at'

-- 3. Compression policy 真設定
SELECT proc_name, hypertable_name, schedule_interval, config
FROM timescaledb_information.jobs
WHERE proc_name='policy_compression' AND hypertable_name='health_observations';
-- Expected: 1 row; config 含 compress_after = '7 days'

-- 4. Retention policy 真設定
SELECT proc_name, hypertable_name, config
FROM timescaledb_information.jobs
WHERE proc_name='policy_retention' AND hypertable_name='health_observations';
-- Expected: 1 row; config 含 drop_after = '90 days'

-- 5. domain CHECK 6 值齊全
SELECT pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid='learning.health_observations'::regclass AND conname LIKE '%domain%check%';
-- Expected: 含 ws_latency/rest_success_rate/db_backlog/disk_usage/cpu_mem/strategy_level

-- 6. state CHECK 4 值齊全(HEALTH_OK/WARN/DEGRADED/CRITICAL)
SELECT pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid='learning.health_observations'::regclass AND conname LIKE '%state%check%'
  AND conname NOT LIKE '%state_prev%';

-- 7. 4 hot-path indexes 確認
SELECT indexname FROM pg_indexes
WHERE schemaname='learning' AND tablename='health_observations'
ORDER BY indexname;
-- Expected: ≥ 5 (1 PK + idx_health_domain_metric_observed + idx_health_state_observed
--                + idx_health_symbol_observed + idx_health_strategy_observed)

-- 8. engine_mode CHECK 真 reject 5th value (empirical INSERT test)
BEGIN;
SAVEPOINT test_engine_mode;
INSERT INTO learning.health_observations
    (observed_at, domain, metric_name, state, metric_value, engine_mode)
VALUES
    (NOW(), 'ws_latency', 'test', 'HEALTH_OK', 100, 'INVALID_MODE');
-- Expected: ERROR: violates check constraint
ROLLBACK TO SAVEPOINT test_engine_mode;

-- 同時測 domain CHECK
SAVEPOINT test_domain;
INSERT INTO learning.health_observations
    (observed_at, domain, metric_name, state, metric_value, engine_mode)
VALUES
    (NOW(), 'INVALID_DOMAIN', 'test', 'HEALTH_OK', 100, 'live');
-- Expected: ERROR: violates check constraint
ROLLBACK TO SAVEPOINT test_domain;

-- 同時測 state CHECK
SAVEPOINT test_state;
INSERT INTO learning.health_observations
    (observed_at, domain, metric_name, state, metric_value, engine_mode)
VALUES
    (NOW(), 'ws_latency', 'test', 'INVALID_STATE', 100, 'live');
-- Expected: ERROR: violates check constraint
ROLLBACK TO SAVEPOINT test_state;

ROLLBACK;
```

### 9.3 Round 2 — Idempotency 驗證

重跑 V106.sql 第二次必不 RAISE / 必不重複建 hypertable / 必不重複 policy:

```bash
ssh trade-core "
  cd ~/BybitOpenClaw/srv && \
  PGPASSWORD=\$(cat ~/.pgpass | grep trading_ai | cut -d: -f5) \
  psql -h 127.0.0.1 -p 5432 -U trading_admin -d trading_ai \
    -v ON_ERROR_STOP=1 -f sql/migrations/V106__m3_health_observations_hypertable.sql
"
# Expected exit code 0; all DO blocks output NOTICE-only PASS; 0 RAISE EXCEPTION
```

**Round 2 後驗證**:
```sql
-- 確認 V106 不 double-create
SELECT count(*) FROM information_schema.tables
WHERE table_schema='learning' AND table_name='health_observations';
-- Expected: 1

-- 確認 hypertable 不 double
SELECT count(*) FROM timescaledb_information.dimensions
WHERE hypertable_name='health_observations';
-- Expected: 1

-- 確認 policies 不 double
SELECT count(*) FROM timescaledb_information.jobs
WHERE hypertable_name='health_observations';
-- Expected: 2 (compression + retention)

-- 確認 indexes 不 double
SELECT count(*) FROM pg_indexes
WHERE schemaname='learning' AND tablename='health_observations'
  AND indexname IN (
    'idx_health_domain_metric_observed',
    'idx_health_state_observed',
    'idx_health_symbol_observed',
    'idx_health_strategy_observed'
  );
-- Expected: 4
```

### 9.4 為何 Mac mock pytest 不夠(V055 5-round loop 教訓)

per memory `feedback_v_migration_pg_dry_run.md` + `project_2026_05_02_p0_sqlx_hash_drift`:
- Mac mock pytest 無法捕捉 TimescaleDB `create_hypertable()` 真實返回 metadata
- Mac static parse review 無法驗 `add_compression_policy()` / `add_retention_policy()` 對既有 job 衝突的處理
- Mac 無法驗 CHECK constraint runtime ENUM behavior
- V055 chain 5 round 都 Mac false-pass 後 Linux 撞 bug;V094 / V106 全須遵守 V055 mandate

**E2 / E4 / A3 review 必含 Linux PG dry-run gate 證據 ID**(per CLAUDE.md §Data, Migrations, And Validation + V094 §4.3 範式)。

---

## §10 Engine Restart 實測 SOP(per 2026-05-02 sqlx hash drift 教訓)

per memory `project_2026_05_02_p0_sqlx_hash_drift`(commit `3681f83`),V106 file edit 後 DB checksum 必同步:

```bash
# E1 IMPL: 寫 V106.sql 完成後跑 Linux dry-run (per §9.2)
# 若 V106.sql 落地後又被 edit → DB checksum drift
# 必跑 repair binary 同步 checksum 到 _sqlx_migrations table

ssh trade-core "
  cd ~/BybitOpenClaw/srv && \
  cargo run --release --bin repair_migration_checksum -- --version 106
"
# Expected: V106 checksum updated in _sqlx_migrations table to match new file SHA
```

### 10.1 Engine restart 後驗證 sqlx migrate 不 panic

```bash
ssh trade-core "bash ~/BybitOpenClaw/srv/helper_scripts/restart_all.sh --rebuild"

ssh trade-core "tail -200 ~/BybitOpenClaw/srv/program_code/exchange_connectors/bybit_connector/openclaw_engine/logs/engine.log 2>&1 | grep -E 'sqlx|migration|panic'"
# Expected: 0 panic; 'Applied migrations' 正常 log; V106 success=t in _sqlx_migrations

ssh trade-core "PGPASSWORD=\$(cat ~/.pgpass | grep trading_ai | cut -d: -f5) psql -h 127.0.0.1 -p 5432 -U trading_admin -d trading_ai -c 'SELECT version, success, description FROM _sqlx_migrations WHERE version=106'"
# Expected: 1 row, success=t
```

### 10.2 治理盲點防範

per `project_2026_05_02_p0_sqlx_hash_drift` + V094 §5.3:cargo test PASS ≠ runtime sqlx migrate 驗證。E2 / E4 review 必含「engine restart 實測 + sqlx migrate runtime 不 panic」driver evidence。

---

## §11 Rollback Plan + Reversibility Analysis

### 11.1 V106 rollback DDL

詳見 §6.2(`DROP TABLE ... CASCADE` + drop policies + drop indexes)。

### 11.2 Reversibility 分析

| 操作 | 可逆? | 風險 |
|---|---|---|
| `DROP TABLE learning.health_observations CASCADE` | 邏輯可逆(rerun V106)但 row data 不可逆(全 drop)| **HIGH** — 90d 全 health observation 資料丟失 |
| `remove_compression_policy()` / `remove_retention_policy()` | 可逆(rerun V106 重設) | LOW |
| `DROP INDEX CONCURRENTLY` | 可逆(rerun V106 重建) | LOW |

### 11.3 Rollback 觸發條件

- 僅 dev / staging
- production rollback 走 V### 升級(e.g. V###+1 加 ADD COLUMN / 改 CHECK constraint;不走 V106 down)

### 11.4 V096 boundary

per V101 spec v3 §7:rollback 路徑不跨 V096(V096 drop dead tables 不可逆)。V106 rollback 全在 V096 之後(V096 < V098 < V106),無 boundary 風險。

---

## §12 Audit Field(per V103 EXTEND 範式)

V106 採 V103 EXTEND §14 同範式 5 audit field:

| Column | DEFAULT | NOT NULL | 設計 |
|---|---|---|---|
| `created_by` | 'health_monitor' | NOT NULL | writer process 名;允許 'health_monitor' / 'cowork-agent' / 'operator' / 'm11_replay_engine' / 'm8_anomaly_detector' / 'system' |
| `created_at` | now() | NOT NULL | row insert 時間(server trusted) |
| `updated_by` | NULL | NULLABLE | 後續 update 的 actor(若 H-11 amplification count backfill) |
| `updated_at` | NULL | NULLABLE | last update 時間 |
| `source_version` | 'V106' | NOT NULL | schema version tag;未來 schema migration audit;當前固定 V106 |

### 12.1 為什麼 health_observations 需 audit field

per DOC-08 §12 #8 安全不變量「交易可解釋」:health state 是 M1 LAL halt / M11 budget overrun 的決定 input;每個 observation 必有 audit trail 才能 reproduce。

### 12.2 update_at / update_by 何時填

H-11 amplification cap backfill 場景:
1. M8 anomaly emit → writer INSERT V106 row state=DEGRADED, amplification_loop_24h_count=initial
2. 5 min 後 M8 emit 第 2 個 → writer 必 UPDATE 既有 row 的 amplification_loop_24h_count + 1
3. UPDATE 時 set `updated_at = now()` + `updated_by = 'm8_anomaly_detector'`

---

## §13 Acceptance Criteria(5-7 條 sign-off 標準)

### 13.1 Schema acceptance(MIT + E5)

| # | 標準 | 驗證方法 |
|---|---|---|
| 1 | `learning.health_observations` 表 19 column 全俱在 | `SELECT count(*) FROM information_schema.columns WHERE ...` = 19 |
| 2 | Hypertable + chunk_time_interval=7d 真建立 | `SELECT time_interval FROM timescaledb_information.dimensions WHERE ...` |
| 3 | Compression policy 7d after + retention policy 90d after 真設 | `SELECT * FROM timescaledb_information.jobs WHERE ...` (2 jobs) |
| 4 | 4 ENUM (domain 6 / state 4 / state_prev 4 / engine_mode 4) CHECK constraint 真 reject invalid | empirical INSERT test(per §9.2 step 8)|
| 5 | 4 hot-path index + 1 PK 真建立 | `SELECT indexname FROM pg_indexes WHERE ...` ≥ 5 |
| 6 | V106.sql idempotent 雙跑 0 RAISE | `psql -f V106.sql` x 2 |
| 7 | sqlx checksum 對齊 + engine restart 後 success=t | per §10 SOP |

### 13.2 Cross-V### acceptance(PA)

| # | 標準 | 驗證方法 |
|---|---|---|
| 1 | V096 + V098 prereq 滿足 | `SELECT version FROM _sqlx_migrations WHERE version IN (96, 98)` |
| 2 | V112 / V107 / V109 cross-ref query pattern 不破壞 V106 schema | per §8.3-§8.5 範例 query 預跑 |

### 13.3 治理 acceptance(QA + R4)

| # | 標準 | 驗證方法 |
|---|---|---|
| 1 | engine_mode IN ('live','live_demo') filter 在所有 cross-ref query 出現 | per §8 範例對齊 |
| 2 | 5 audit field 預設值 reasonable | INSERT row 不填 audit field 後 SELECT 驗 DEFAULT |
| 3 | docs/README.md 加 V106 spec 入 index | per CLAUDE.md §七 docs/README 規則 |

---

## §14 開放問題 + Caveat

### 14.1 待 PA C9 確認

1. **`_sqlx_migrations` head 真實**(per §9.1 Query 1)— spec 假設 ≥ V098
2. **TimescaleDB extension version**(per §9.1 Query 2)— spec 假設 ≥ 2.13
3. **governance.audit_log 已 land**(per §9.1 Query 3)— spec 假設已 land
4. **legacy stub conflict**(per §9.1 Query 4)— spec 假設 greenfield

### 14.2 已知 caveat

1. **`amplification_loop_24h_count` writer-side query 成本**:每筆 INSERT 前查 24h 同 domain transition count;在 716k row/day 規模下成本可能高;Sprint 1A-β IMPL 期評估是否需 cache(in-memory)減 query
2. **`evidence_json` JSONB 不索引**:debug-only 欄位;若 future analytics 需要 query JSONB,Sprint 1B+ 加 GIN index
3. **partial index `WHERE state IN (...)` 在 schema migration 時的成本**:CONCURRENTLY 建在 hypertable chunks 上是逐 chunk 建;首次 apply 在 0-row 表上 ms 級;後續 backfill 期會慢
4. **per-strategy `strategy_name` 不 enum**:5 既有策略 + Sprint 2+ 新策略名動態擴增;CHECK enum 易過時
5. **`metric_threshold` config 與 historical row 分離**:writer 寫入時鎖當下 threshold;config 後續變動不溯及既往;符合 audit principle

### 14.3 Sprint 1B writer 路徑未在本 spec 範圍

V106 apply 後立即 0 row(Foundation stage per MIT pipeline maturity);Sprint 1B 補 writer 後升 Skeleton。

---

## §15 後續行動(給 PM 派發)

| Action | Owner | Track | Priority |
|---|---|---|---|
| Sign-off 本 V106 spec | PM | Sprint 1A-β schema prereq closure | P0 |
| PA C9 跑 §9.1 4 條 ssh PG query + 補 4 處 placeholder | PA | Sprint 1A-β pre-dispatch | P0 |
| Reconcile cross-V### dependency(V112 / V107 / V109 對 V106 cross-ref query 對齊)| PA | Sprint 1A-β pre-dispatch | P0 |
| IMPL kickoff:派 E1 寫 V106.sql + Linux PG dry-run × 2 + E2/E4 + restart_all 部署 | PM | Sprint 1A-β IMPL | P1 |
| Sprint 1B writer 上線:`health_monitor` writer + healthcheck `check_health_observations_writer()` | E1 (Sprint 1B) | Sprint 1B | P2 |

### 15.1 Sprint 1A-β schema prereq closure 標誌

本 spec PM sign-off + PA C9 dry-run 補資料 land + V112 / V107 / V109 cross-ref reconciliation 完成 → Sprint 1A-β V106 schema prereq 解除 → IMPL kickoff 派 E1。

---

## §16 關鍵文件指針

- 本 V106 spec:本檔
- v5.8 主檔 §2 M3:`srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md`
- PA dispatch consolidation §6 cross-V### dep graph:`srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md`
- E5 hypertable audit:`srv/docs/CCAgentWorkSpace/E5/workspace/reports/2026-05-21--v58_hypertable_audit.md`
- V103 spec(範式 + 5 audit field EXTEND):`srv/docs/execution_plan/2026-05-21--v103_v104_earn_hypotheses_schema_spec.md`
- V103/V104 Linux PG dry-run protocol(範式):`srv/docs/execution_plan/2026-05-21--v103_v104_linux_pg_dry_run.md`
- V094 spec(Guard A/B/C + 範式):`srv/docs/execution_plan/2026-05-15--v094_close_maker_first_audit_schema_spec.md`
- V083 mirror(ALTER + NOT VALID CHECK 範式):`srv/sql/migrations/V083__fills_entry_context_id_close_check.sql`
- schema_guard_template:`srv/sql/migrations/templates/schema_guard_template.sql`
- repair binary:`srv/rust/openclaw_engine/src/bin/repair_migration_checksum.rs`
- V055 5-round loop + sqlx hash drift incident lessons:`memory/feedback_v_migration_pg_dry_run.md` + `memory/project_2026_05_02_p0_sqlx_hash_drift.md`
- CLAUDE.md §Data, Migrations, And Validation:`srv/CLAUDE.md`
- ADR-0036 (M8 + M10 Tier D blacklist; M3 severity 對齊):`srv/docs/adr/0036-m8-anomaly-detection-and-m10-tier-d-model-blacklist.md`
- ADR-0038 (M11 Continuous Counterfactual Replay; M3 cross-ref):`srv/docs/adr/0038-m11-continuous-counterfactual-replay-and-liquidations-source.md`
- ADR-0034 (M1 LAL; M3 → LAL halt cross-ref):`srv/docs/adr/0034-decision-lease-layered-approval-lal.md`

---

## §17 審計記錄

| Source agent | Role | Audit pattern coverage |
|---|---|---|
| MIT(本文起草)| 起草者 | V058 Risk 4 V106 placeholder closure 路徑 / pipeline maturity 5 階段 / Guard A/C / Linux PG dry-run mandate / H-11 amplification cap design |
| PA dispatch consolidation 5.21(範式參考) | spec 設計 + cross-V### dependency | V106 / V107 / V109 / V112 cross-ref graph / Sprint 1A-β dispatch sequence |
| V103/V104 spec(2026-05-21,範式參考)| 結構 + audit field 範式 | 14 section structure / 5 audit field per V103 EXTEND / Guard A/B/C template / Linux PG dry-run × 2 round protocol / sqlx checksum repair SOP |
| E5 5.21 hypertable audit | hypertable 規格 | 7d chunk + 7d compression + 90d retention / 6mo +1.25-2.5 GB compress 後 buffer 16-63% 占比 |
| db-schema-design-financial-time-series skill | DB schema audit | hypertable 必用 / hot-path index 選用 / engine_mode CHECK 4 值 / Guard A/B/C 規範 / partial index 設計 |
| ml-pipeline-maturity-audit skill | Pipeline stage 評級 | V106 apply 後立即 0 row 屬 Foundation stage;Sprint 1B writer 接線後升 Skeleton |
| ADR-0034 (M1 LAL) | cross-ref query pattern | HEALTH_DEGRADED → LAL 1 halt / LAL eligibility 90d incident-free check |
| ADR-0036 (M8 + M10 Tier D) | severity taxonomy 對齊 | M3 4 state vs M8 4 severity(INFO/WARN/CRITICAL/HALT)的 enum 對齊規則 |
| ADR-0038 (M11 replay) | cross-ref query pattern | wall-clock > 4h → M3 HEALTH_WARN(per CR-7 dedup contract)|

### 17.1 待 PA dispatch 前補充

- [ ] PA C9 dry-run 4 條 ssh query 結果(§9.1)
- [ ] V096 + V098 + TimescaleDB extension 已 land 確認
- [ ] legacy `learning.health_observations` stub 不存在確認
- [ ] H-11 amplification cap writer-side query 成本評估(per §14.2 caveat 1)
- [ ] Sprint 1B writer + healthcheck wiring 工作 owner + dispatch sequence

---

**END V106 spec full DDL v0**
