# V101 + V102 Track Attribution Migration Spec (v3 — 2nd reviewer audit corrections)

**日期**: 2026-05-20（v3 — 2nd reviewer audit incorporated）
**對應 AMD**: AMD-2026-05-20-01 + AMD-2026-05-20-02 + **AMD-2026-05-20-03**
**對應 ADR**: ADR-0024-lite + ADR-0025 v3 + ADR-0026 v3
**Status**: SPEC READY v3 — Phase 0 catch-up V097/V098 必先完成 + v56 P0 完整 cycle 收口
**Owner chain**: PA → E1 → E2 → E4 → MIT
**Hard preconditions**:
1. **Phase 0 V097/V098 catch-up apply on Linux DB**（reviewer ssh verified Linux head = V096, repo head = V098；V098 含 governance.audit_log ALTER constraint，須低寫入窗口）
2. v56 P0-ENGINE-HALTSESSION-STUCK-FIX 完整 cycle 收口
3. **V096 (drop_dead_learning_tables) 已 apply 且不可逆**——任何 rollback spec **不得依賴 V096 reversal**

---

## 1. Goal

部署 `strategy_track` PG enum 為一等公民 attribution 維度，貫穿 **12 個真實存在的表 + 2 個新建表**（grep verified 2026-05-20 v3）。

分兩條 migration（real V### 號碼 PA dispatch 時 final 鎖定，預期 V101 / V102 但若 LG-3 與 W-AUDIT-8a 殘留 reserve V099/V100，可能順延 V103/V104）：

- **V101**：CREATE TYPE + ADD COLUMN nullable on 12 existing tables + CREATE TABLE 2 new tables + backfill `baseline`
- **V102**：ALTER NOT NULL + DEFAULT + per-table-tailored indexes + 4 P&L views (with `net_edge_bps` computed) + `governance.track_kill_events`

---

## 2. Phase 0 — Migration Drift Reconcile

### 2.1 Reviewer-verified state

```
Repo (sql/migrations/):   V001 ... V096 V097 V098 (head)
Linux DB (_sqlx_migrations head):  V096  ← drift = 2 missing
```

### 2.2 Catch-up sequence

```bash
# Pre-catch-up safety check
ssh trade-core "psql -d openclaw -c \"SELECT version, installed_on FROM _sqlx_migrations ORDER BY version DESC LIMIT 5\""

# Schedule low-write window (UTC 04-06 recommended)
# Apply V097 (lg5_attribution_healthcheck_indexes)
ssh trade-core "cd /home/ncyu/srv && sqlx migrate run --target-version 97"
# Healthcheck post-V097: query attribution healthcheck views

# Apply V098 (governance_audit_log_halt_event_types)
# WARNING: V098 alters governance.audit_log constraint — lock risk
# Verify no active halt event before apply
ssh trade-core "psql -d openclaw -c \"SELECT COUNT(*) FROM governance.audit_log WHERE created_at > now() - INTERVAL '1 hour'\""
ssh trade-core "cd /home/ncyu/srv && sqlx migrate run --target-version 98"

# Post-catch-up verify drift = 0
ssh trade-core "psql -d openclaw -c \"SELECT version FROM _sqlx_migrations ORDER BY version DESC LIMIT 3\""
# Expected: V098 V097 V096

# Healthcheck full system
ssh trade-core "bash helper_scripts/db/passive_wait_healthcheck.sh"
```

### 2.3 Irreversibility note

V096 (`drop_dead_learning_tables`) is irreversible — dropped tables (e.g.
`learning.scorer_predictions`) cannot be restored within rollback. v3 spec
language: **all rollback paths for V101/V102 stop at V096 boundary; no
attempt to cross V096 backwards**.

### 2.4 Phase 0 task ID

`PHASE-0-MIGRATION-DRIFT-RECONCILE` (P1 PENDING, hard precondition for
V101 dispatch)

---

## 3. V101 內容 (v3 — 12 real tables + 2 new)

### 3.1 CREATE TYPE

```sql
DO $$ BEGIN
    CREATE TYPE strategy_track AS ENUM (
        'direct_exploit',
        'asds_factory',
        'baseline'
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;
```

### 3.2 ALTER TABLE — 12 既存表（Guard B `ADD COLUMN IF NOT EXISTS`）

```sql
-- ─── trading.* schema (7 tables) ──────────────────────────
ALTER TABLE IF EXISTS trading.fills
    ADD COLUMN IF NOT EXISTS track strategy_track NULL;

ALTER TABLE IF EXISTS trading.intents
    ADD COLUMN IF NOT EXISTS track strategy_track NULL;

ALTER TABLE IF EXISTS trading.orders
    ADD COLUMN IF NOT EXISTS track strategy_track NULL;

ALTER TABLE IF EXISTS trading.signals
    ADD COLUMN IF NOT EXISTS track strategy_track NULL;

ALTER TABLE IF EXISTS trading.decision_outcomes
    ADD COLUMN IF NOT EXISTS track strategy_track NULL;

ALTER TABLE IF EXISTS trading.risk_verdicts
    ADD COLUMN IF NOT EXISTS track strategy_track NULL;

ALTER TABLE IF EXISTS trading.position_snapshots
    ADD COLUMN IF NOT EXISTS track strategy_track NULL;

-- ─── learning.* schema (3 tables) ─────────────────────────
ALTER TABLE IF EXISTS learning.lease_transitions
    ADD COLUMN IF NOT EXISTS track strategy_track NULL;

ALTER TABLE IF EXISTS learning.strategy_trial_ledger
    ADD COLUMN IF NOT EXISTS track strategy_track NULL;

ALTER TABLE IF EXISTS learning.cost_edge_advisor_log
    ADD COLUMN IF NOT EXISTS track strategy_track NULL;

-- ─── agent.* schema (2 tables) ────────────────────────────
ALTER TABLE IF EXISTS agent.ai_invocations
    ADD COLUMN IF NOT EXISTS track strategy_track NULL;

ALTER TABLE IF EXISTS agent.decision_objects
    ADD COLUMN IF NOT EXISTS track strategy_track NULL;
```

### 3.3 CREATE TABLE — 2 新表

#### 3.3.1 learning.hypotheses

```sql
CREATE TABLE IF NOT EXISTS learning.hypotheses (
    hypothesis_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                    TEXT NOT NULL UNIQUE,
    version                 INT NOT NULL DEFAULT 1,
    track                   strategy_track NOT NULL DEFAULT 'asds_factory'
                            CHECK (track = 'asds_factory'),
    generator               JSONB,
    thesis                  TEXT,
    spec_json               JSONB NOT NULL,
    state                   TEXT NOT NULL DEFAULT 'DRAFT'
                            CHECK (state IN ('DRAFT','REGISTERED','EXPERIMENTING',
                                             'EVIDENCE_GATE','PROMOTED','REJECTED','EXPIRED')),
    source                  TEXT,  -- 'cowork_assistant' / 'pa_manual' / 'ai_invocation_uuid'
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    state_changed_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    expiry_at               TIMESTAMPTZ,
    paper_pnl_bps           NUMERIC,
    demo_pnl_bps            NUMERIC,
    sharpe                  NUMERIC,
    dsr                     NUMERIC,
    originating_alpha_sources JSONB,
    parent_hypothesis_id    UUID REFERENCES learning.hypotheses(hypothesis_id),
    mutation_of             UUID REFERENCES learning.hypotheses(hypothesis_id)
);

CREATE INDEX IF NOT EXISTS idx_hypotheses_state ON learning.hypotheses (state);
CREATE INDEX IF NOT EXISTS idx_hypotheses_state_changed_at ON learning.hypotheses (state_changed_at DESC);
```

#### 3.3.2 learning.hypothesis_preregistration (per ADR-0026 v3, 15 fields)

```sql
CREATE TABLE IF NOT EXISTS learning.hypothesis_preregistration (
    preregistration_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    strategy_name               TEXT NOT NULL,
    track                       strategy_track NOT NULL
                                CHECK (track = 'direct_exploit'),
    registered_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    registered_by               TEXT NOT NULL,
    hypothesis_text             TEXT NOT NULL,

    -- Statistical thresholds
    expected_alpha_bps_min      NUMERIC NOT NULL,
    expected_alpha_bps_max      NUMERIC NOT NULL,
    expected_n_events_min       INT NOT NULL,
    expected_sharpe_min         NUMERIC NOT NULL,
    expected_win_rate_min       NUMERIC NOT NULL,
    expected_max_drawdown_pct   NUMERIC NOT NULL,
    expected_holding_period_sec INT NOT NULL,
    decision_alpha              NUMERIC NOT NULL DEFAULT 0.05,

    -- Strategy identity locks (per ADR-0026 v3)
    code_hash                   TEXT NOT NULL,
    config_hash                 TEXT NOT NULL,
    trigger_rule                JSONB NOT NULL,
    side_rule                   TEXT NOT NULL,

    -- Cost & dedup
    cost_assumption             JSONB NOT NULL,
    dedup_rule                  TEXT NOT NULL,

    -- Variance estimator
    variance_estimator          TEXT NOT NULL
                                CHECK (variance_estimator IN (
                                    'newey_west', 'garch_1_1',
                                    'bootstrap', 'realized_variance'
                                )),

    -- Data window
    estimation_window_days      INT NOT NULL,
    event_window_seconds        INT NOT NULL,
    post_event_window_sec       INT NOT NULL,
    data_window_start_ts        TIMESTAMPTZ NOT NULL,
    data_window_end_ts          TIMESTAMPTZ NOT NULL,

    -- Immutability
    immutable_trigger_hash      TEXT NOT NULL,
    locked                      BOOLEAN NOT NULL DEFAULT TRUE,
    unlock_reason               TEXT,
    unlock_at                   TIMESTAMPTZ,
    superseded_by               UUID REFERENCES learning.hypothesis_preregistration(preregistration_id)
);

CREATE INDEX IF NOT EXISTS idx_prereg_strategy
    ON learning.hypothesis_preregistration (strategy_name, registered_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_prereg_immutable_trigger
    ON learning.hypothesis_preregistration (immutable_trigger_hash);
```

### 3.4 Backfill — 12 既存表

```sql
-- trading.* (with ts column where applicable)
UPDATE trading.fills              SET track = 'baseline' WHERE track IS NULL;
UPDATE trading.intents            SET track = 'baseline' WHERE track IS NULL;
UPDATE trading.orders             SET track = 'baseline' WHERE track IS NULL;
UPDATE trading.signals            SET track = 'baseline' WHERE track IS NULL;
UPDATE trading.risk_verdicts      SET track = 'baseline' WHERE track IS NULL;
UPDATE trading.position_snapshots SET track = 'baseline' WHERE track IS NULL;

-- trading.decision_outcomes: PK = context_id, no ts
-- Strategy attribution via JOIN to decision_context_snapshots
UPDATE trading.decision_outcomes do
SET track = 'baseline'
WHERE track IS NULL
  AND context_id IN (
    SELECT context_id FROM trading.decision_context_snapshots
    -- 既有 5 textbook 策略 context 全 → baseline
  );
-- Fallback: any row without resolvable context → 'baseline' as default
UPDATE trading.decision_outcomes SET track = 'baseline' WHERE track IS NULL;

-- learning.*
UPDATE learning.lease_transitions     SET track = 'baseline' WHERE track IS NULL;
UPDATE learning.strategy_trial_ledger SET track = 'baseline' WHERE track IS NULL;
UPDATE learning.cost_edge_advisor_log SET track = 'baseline' WHERE track IS NULL;

-- agent.*
UPDATE agent.ai_invocations    SET track = 'baseline' WHERE track IS NULL;
UPDATE agent.decision_objects  SET track = 'baseline' WHERE track IS NULL;

-- learning.hypotheses, learning.hypothesis_preregistration:
-- 0 rows (newly created)
```

**Batched UPDATE warning**: 大表（fills 估計 ~100k+ rows, lease_transitions
~50k rows）需 batch 10000 + sleep 100ms 防 lock。PA dispatch 加 batch loop。

### 3.5 V101 結尾 assert

```sql
DO $$
DECLARE
    null_count INT := 0;
    tmp INT;
BEGIN
    SELECT COUNT(*) INTO tmp FROM trading.fills WHERE track IS NULL;              null_count := null_count + tmp;
    SELECT COUNT(*) INTO tmp FROM trading.intents WHERE track IS NULL;            null_count := null_count + tmp;
    SELECT COUNT(*) INTO tmp FROM trading.orders WHERE track IS NULL;             null_count := null_count + tmp;
    SELECT COUNT(*) INTO tmp FROM trading.signals WHERE track IS NULL;            null_count := null_count + tmp;
    SELECT COUNT(*) INTO tmp FROM trading.decision_outcomes WHERE track IS NULL;  null_count := null_count + tmp;
    SELECT COUNT(*) INTO tmp FROM trading.risk_verdicts WHERE track IS NULL;      null_count := null_count + tmp;
    SELECT COUNT(*) INTO tmp FROM trading.position_snapshots WHERE track IS NULL; null_count := null_count + tmp;
    SELECT COUNT(*) INTO tmp FROM learning.lease_transitions WHERE track IS NULL; null_count := null_count + tmp;
    SELECT COUNT(*) INTO tmp FROM learning.strategy_trial_ledger WHERE track IS NULL; null_count := null_count + tmp;
    SELECT COUNT(*) INTO tmp FROM learning.cost_edge_advisor_log WHERE track IS NULL; null_count := null_count + tmp;
    SELECT COUNT(*) INTO tmp FROM agent.ai_invocations WHERE track IS NULL;       null_count := null_count + tmp;
    SELECT COUNT(*) INTO tmp FROM agent.decision_objects WHERE track IS NULL;     null_count := null_count + tmp;

    IF null_count > 0 THEN
        RAISE EXCEPTION 'V101 backfill incomplete: % rows still have track=NULL', null_count;
    END IF;
END $$;
```

---

## 4. V102 內容 (v3 — real column names per-table)

**前置**：V101 已 apply + 驗證；7d soak（Rust/Python writer 開始填 track 後）。

### 4.1 ALTER COLUMN NOT NULL + DEFAULT

```sql
ALTER TABLE trading.fills              ALTER COLUMN track SET NOT NULL, ALTER COLUMN track SET DEFAULT 'baseline';
ALTER TABLE trading.intents            ALTER COLUMN track SET NOT NULL, ALTER COLUMN track SET DEFAULT 'baseline';
ALTER TABLE trading.orders             ALTER COLUMN track SET NOT NULL, ALTER COLUMN track SET DEFAULT 'baseline';
ALTER TABLE trading.signals            ALTER COLUMN track SET NOT NULL, ALTER COLUMN track SET DEFAULT 'baseline';
ALTER TABLE trading.decision_outcomes  ALTER COLUMN track SET NOT NULL, ALTER COLUMN track SET DEFAULT 'baseline';
ALTER TABLE trading.risk_verdicts      ALTER COLUMN track SET NOT NULL, ALTER COLUMN track SET DEFAULT 'baseline';
ALTER TABLE trading.position_snapshots ALTER COLUMN track SET NOT NULL, ALTER COLUMN track SET DEFAULT 'baseline';
ALTER TABLE learning.lease_transitions ALTER COLUMN track SET NOT NULL, ALTER COLUMN track SET DEFAULT 'baseline';
ALTER TABLE learning.strategy_trial_ledger ALTER COLUMN track SET NOT NULL, ALTER COLUMN track SET DEFAULT 'baseline';
ALTER TABLE learning.cost_edge_advisor_log ALTER COLUMN track SET NOT NULL, ALTER COLUMN track SET DEFAULT 'baseline';
ALTER TABLE agent.ai_invocations       ALTER COLUMN track SET NOT NULL, ALTER COLUMN track SET DEFAULT 'baseline';
ALTER TABLE agent.decision_objects     ALTER COLUMN track SET NOT NULL, ALTER COLUMN track SET DEFAULT 'baseline';
```

### 4.2 CREATE INDEX (per-table tailored to REAL time column)

**Time column heterogeneity**: trading.* use `ts`; agent.decision_objects
uses `created_at`; learning.lease_transitions uses `ts_ms BIGINT`; some
learning tables vary — PA dispatch verifies each.

```sql
-- trading.* with `ts` time column
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_fills_track_ts              ON trading.fills (track, ts);
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_intents_track_ts            ON trading.intents (track, ts);
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_orders_track_ts             ON trading.orders (track, ts);
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_signals_track_ts            ON trading.signals (track, ts);
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_risk_verdicts_track_ts      ON trading.risk_verdicts (track, ts);
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_position_snapshots_track_ts ON trading.position_snapshots (track, ts);

-- trading.decision_outcomes: no time column, index on (track, context_id)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_decision_outcomes_track     ON trading.decision_outcomes (track, context_id);

-- learning.lease_transitions: ts_ms BIGINT (NOT TIMESTAMPTZ)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_lease_transitions_track_ts  ON learning.lease_transitions (track, ts_ms);

-- learning.strategy_trial_ledger, learning.cost_edge_advisor_log:
-- PA dispatch verifies real time column name (likely 'created_at' or 'trial_ts'/'log_ts')
-- Placeholder — final at dispatch:
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_strategy_trial_track        ON learning.strategy_trial_ledger (track /*, REAL_TIME_COL */);
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_cost_edge_advisor_track     ON learning.cost_edge_advisor_log (track /*, REAL_TIME_COL */);

-- agent.ai_invocations: PA dispatch verifies real time column
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_ai_invocations_track        ON agent.ai_invocations (track /*, REAL_TIME_COL */);

-- agent.decision_objects: created_at TIMESTAMPTZ
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_decision_objects_track      ON agent.decision_objects (track, created_at);
```

**PA dispatch action**: 4 placeholder `/* REAL_TIME_COL */` 必須在 dispatch
時 grep 真實 column 並替換。失敗 dispatch (column 假設錯誤) 是已知風險。

### 4.3 P&L Views (with computed `net_edge_bps`)

`trading.fills` real columns: `ts, fill_id, order_id, symbol, side, qty,
price, fee, fee_currency, realized_pnl, is_paper, strategy_name,
context_id, details`. **NO `net_edge_bps`** — compute in view.

```sql
CREATE OR REPLACE VIEW track_direct_exploit_daily AS
SELECT
    date_trunc('day', ts)                                                AS day,
    SUM(realized_pnl)                                                    AS daily_pnl_usdt,
    COUNT(*)                                                             AS n_fills,
    -- net_edge_bps computed: (realized_pnl - fee) / (qty * price) * 10000
    AVG(((realized_pnl - fee) / NULLIF(qty * price, 0)) * 10000.0)       AS avg_net_edge_bps,
    SUM(fee)                                                             AS daily_fee_usdt
FROM trading.fills
WHERE track = 'direct_exploit'
GROUP BY 1;

CREATE OR REPLACE VIEW track_asds_factory_daily AS
SELECT
    date_trunc('day', ts)                                                AS day,
    SUM(realized_pnl)                                                    AS daily_pnl_usdt,
    COUNT(*)                                                             AS n_fills,
    AVG(((realized_pnl - fee) / NULLIF(qty * price, 0)) * 10000.0)       AS avg_net_edge_bps,
    SUM(fee)                                                             AS daily_fee_usdt
FROM trading.fills
WHERE track = 'asds_factory'
GROUP BY 1;

CREATE OR REPLACE VIEW track_baseline_daily AS
SELECT
    date_trunc('day', ts)                                                AS day,
    SUM(realized_pnl)                                                    AS daily_pnl_usdt,
    COUNT(*)                                                             AS n_fills,
    AVG(((realized_pnl - fee) / NULLIF(qty * price, 0)) * 10000.0)       AS avg_net_edge_bps,
    SUM(fee)                                                             AS daily_fee_usdt
FROM trading.fills
WHERE track = 'baseline'
GROUP BY 1;

CREATE OR REPLACE VIEW track_summary_daily AS
SELECT day, 'direct_exploit'::strategy_track AS track, daily_pnl_usdt, n_fills, avg_net_edge_bps, daily_fee_usdt FROM track_direct_exploit_daily
UNION ALL
SELECT day, 'asds_factory'::strategy_track    AS track, daily_pnl_usdt, n_fills, avg_net_edge_bps, daily_fee_usdt FROM track_asds_factory_daily
UNION ALL
SELECT day, 'baseline'::strategy_track        AS track, daily_pnl_usdt, n_fills, avg_net_edge_bps, daily_fee_usdt FROM track_baseline_daily;
```

### 4.4 Kill events 表

```sql
CREATE TABLE IF NOT EXISTS governance.track_kill_events (
    event_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    track               strategy_track NOT NULL,
    event_ts            TIMESTAMPTZ NOT NULL DEFAULT now(),
    trigger             TEXT NOT NULL,
    threshold_value     NUMERIC,
    actual_value        NUMERIC,
    affected_strategies TEXT[] NOT NULL,
    action              TEXT NOT NULL CHECK (action IN
                        ('WARN','PAUSE','KILL','CONTINUE','PIVOT','SCALE','GRADUATE')),
    operator_signoff    TEXT,
    signoff_ts          TIMESTAMPTZ
);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_track_kill_events_track_ts
    ON governance.track_kill_events (track, event_ts DESC);
```

---

## 5. Acceptance Criteria (v3)

### 5.1 Phase 0 acceptance

| AC | 驗證 |
|---|---|
| P0-AC1 | ssh trade-core SELECT version FROM _sqlx_migrations 返回 head |
| P0-AC2 | Drift list 列出（≥ V097, V098 missing）|
| P0-AC3 | V097 apply success + healthcheck pass |
| P0-AC4 | V098 apply during low-write window (UTC 04-06) + no governance.audit_log lock incident |
| P0-AC5 | Post-catch-up head = V098 confirmed |

### 5.2 V101 acceptance (v3)

| AC | 驗證 |
|---|---|
| V101-AC1 | Linux PG dry-run PASS（ADR-0011）|
| V101-AC2 | 12 既存表 + 2 新表 schema 存在 |
| V101-AC3 | 12 既存表 全部 backfilled（0 NULL row）|
| V101-AC4 | trading.decision_outcomes JOIN to decision_context_snapshots 成功 backfill |
| V101-AC5 | learning.hypothesis_preregistration 15 fields constraints 全部生效 |
| V101-AC6 | learning.hypotheses CHECK (track='asds_factory') enforced |
| V101-AC7 | learning.hypothesis_preregistration CHECK (track='direct_exploit') enforced |
| V101-AC8 | Re-apply V101 idempotent |
| V101-AC9 | Rust enum + Python enum + PG enum 三方一致 |

### 5.3 V102 acceptance (v3)

| AC | 驗證 |
|---|---|
| V102-AC1 | Linux PG dry-run PASS |
| V102-AC2 | 7d soak 0 NULL row |
| V102-AC3 | NOT NULL + DEFAULT 'baseline' 生效 |
| V102-AC4 | 12 indexes 全建立（注意 4 個 placeholder time column 在 dispatch 時 final 鎖定）|
| V102-AC5 | 4 views 查詢成功 + `net_edge_bps` 計算正確 |
| V102-AC6 | `governance.track_kill_events` 可手動 INSERT/DELETE |

### 5.4 Cross-spec acceptance

| AC | 驗證 |
|---|---|
| X-AC1 | Rust `strategies/mod.rs` 5 既有策略全 declare `track = Baseline` |
| X-AC2 | Decision Lease (`agent.decision_objects.track`) 與 `learning.lease_transitions.track` JOIN 一致 |
| X-AC3 | cost_edge_advisor daemon 寫 row 帶 track |
| X-AC4 | REST endpoint `/api/v1/tracks/summary` 返回 JSON（N+1 land）|
| X-AC5 | `trading.fills.strategy_name` 既有 5 策略全部對應 `track = baseline` |
| X-AC6 | `trading.decision_outcomes.track` 與 `trading.decision_context_snapshots` strategy attribution 一致 |

---

## 6. Sequencing

```
v56 P0-ENGINE-HALTSESSION-STUCK-FIX 完整 cycle 收口
   ↓
PHASE-0-MIGRATION-DRIFT-RECONCILE（V097 + V098 catch-up serial）
   ↓
PA refresh dispatch plan（V### final 鎖定 + 4 placeholder time column grep 校對）
   ↓
V101 apply（Linux PG dry-run → Mac 同步驗證 → trade-core apply）
   ↓
7d soak（Rust/Python writer 上線後填 track）
   ↓
V102 apply（CONCURRENTLY index during low-IO window）
   ↓
REST endpoint /api/v1/tracks/summary（read views）go-live
   ↓
N+2: GUI summary tab 上線（讀 endpoint）
   ↓
LCS isolated cluster IMPL（per ADR-0026 v3 thesis）
   ↓
NLE listing watcher shadow
```

---

## 7. Rollback

- **V102 rollback**: `ALTER COLUMN track DROP NOT NULL` + `DROP INDEX ...
  CONCURRENTLY` + `DROP VIEW ...` + `DROP TABLE governance.track_kill_events`
- **V101 rollback**: `ALTER TABLE ... DROP COLUMN IF EXISTS track` (12 tables) +
  `DROP TABLE IF EXISTS learning.hypotheses, learning.hypothesis_preregistration`
- **V096 boundary**: rollback 路徑不跨 V096（V096 drop dead tables 不可逆）
- Pre-V101 state recoverable; zero data loss in rollback path

---

## 8. References

- AMD-2026-05-20-01 / -02 / -03
- ADR-0024-lite Cowork subscription operator-assistant
- ADR-0025 v3 Track-based attribution (12 tables)
- ADR-0026 v3 Direct Exploit bypass CPCV (event-study + prereg + future replay match)
- ADR-0011 V### migration mandatory Linux PG dry-run
- v4.2 spec authority: `srv/2026-05-20--dual-track-architecture-v4.2.md`
- 2nd reviewer audit confirmed Linux V096 vs repo V098 + market.liquidations 2.12d sample

---

**END V101/V102 spec v3**
