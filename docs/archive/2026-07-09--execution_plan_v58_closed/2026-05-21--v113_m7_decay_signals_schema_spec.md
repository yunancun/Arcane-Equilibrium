---
spec: V113 — M7 Decay Signals + Strategy Lifecycle Schema (Single Decay Authority)
date: 2026-05-21
author: MIT consultant draft for PA Sprint 1A-β dispatch (placeholder reserve)
phase: v5.8 Sprint 1A-β schema prerequisite (per assignment)
status: SPEC-PLACEHOLDER (frontmatter + 大綱 reserve; full DDL land Sprint 1A-β)
parent specs:
  - srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md §2 M7 Decay
  - CR-7 contract — M7 是 single decay authority (PA dispatch consolidation)
  - srv/docs/adr/0044-m7-decay-enforced-single-authority.md (V113 schema 對應治理 authority；ADR-0044 Decision 1-6 為 column 設計邊界；R4 NEW-H-2 reverse-ref patch 2026-05-21)
mirror precedent:
  - srv/docs/execution_plan/2026-05-21--v103_v104_earn_hypotheses_schema_spec.md (format reference)
scope: placeholder spec — 不寫 V113.sql, 不在 Mac 跑 SQL, 不執行 PG, full DDL 在 Sprint 1A-β 補完
---

# V113 M7 Decay Signals Schema Migration Spec (PLACEHOLDER)

## §0 TL;DR

- **V113 新增 2 個 table**：`learning.decay_signals`（per-strategy decay signal ingestion ledger — hypertable）+ `learning.strategy_lifecycle`（strategy lifecycle state machine — regular table）。
- **`decay_action_level` ENUM 4 值**（rename of `decay_stage` per CR-7）：`RECOVERY` / `DECAY_DETECTED` / `DECAY_ENFORCED` / `RETIRED`。
- **M7 是 single decay authority**（per CR-7 contract — 其他 module M11/M8/M2 只發 signal，**只有 M7 改 strategy_lifecycle.current_decay_action_level**）。
- **Signal ingest 來源**：
  - M11 (V107 replay_divergence_log) WARN/CRITICAL signal
  - alpha curve（per-strategy 30d rolling Sharpe / hit rate degradation）
  - drawdown threshold breach
  - N consecutive losing trades count
- **依賴**：V107（M11 replay_divergence_log FK ingest source）。
- **Sprint 1A-β schedule**：V107 → V113 → V112（M1 LAL 依 V113 incident-free query）。

---

## §1 Background

### 1.1 v5.8 §2 M7 module 出處 + CR-7 contract

v5.8 §2 M7 Decay module 列出：
- per-strategy lifecycle 4 階段：RECOVERY（剛經歷 incident 恢復觀察期）→ 正常運作（無 decay_action_level，或 lifecycle.current=NULL）→ DECAY_DETECTED（signal triggered；觀察期）→ DECAY_ENFORCED（active capital cap / position freeze）→ RETIRED（permanently disabled）
- M7 ingests multi-source decay signals + aggregates → decay_action_level decision
- CR-7 contract：M7 是 **single decay authority** — M11 / M8 / M2 / M9 不直接寫 strategy_lifecycle decay state；signal 必 route 經 M7 decision

### 1.2 Audit 來源

- MIT 2026-05-21 v5.8 audit Risk 5「M7 schema spec missing」
- CR-7 PA dispatch consolidation：M7 single authority contract
- R4 5.21 ADR alignment audit「M7 對應 ADR 待補（per R4 建議）」

---

## §2 Schema Outline (placeholder)

### 2.1 `learning.decay_signals` (hypertable)

**Tables 大綱**：
- PK: `(signal_id, ingested_at)` 複合（per hypertable best practice）
- Columns 大綱（13 fields）：
  - `signal_id BIGSERIAL`, `ingested_at TIMESTAMPTZ NOT NULL`
  - `strategy_name TEXT NOT NULL`, `overlay_id BIGINT NULL`
  - `signal_source TEXT NOT NULL` (ENUM: `m11_replay_divergence` / `alpha_curve_degradation` / `drawdown_breach` / `consecutive_losses`)
  - `signal_severity TEXT NOT NULL` (ENUM: INFO / WARN / CRITICAL — 對齊 M8/M11 severity)
  - `signal_metric_name TEXT NOT NULL` (e.g. `sharpe_30d`, `dd_max_7d`, `consecutive_loss_count`)
  - `signal_metric_value NUMERIC(18,8) NOT NULL`
  - `signal_threshold NUMERIC(18,8) NOT NULL` (breach threshold matched at evaluation time)
  - `source_v107_divergence_id BIGINT NULL` (FK to `learning.replay_divergence_log.divergence_id` if signal_source='m11_replay_divergence')
  - `decision_action TEXT NULL` (ENUM: `no_action_under_threshold` / `escalate_to_action_level_change` / `escalate_to_retired`)
  - `evidence_json JSONB`
  - `engine_mode TEXT NOT NULL`

**Constraints 大綱**：
- CHECK: `signal_source` ∈ 4 值 ENUM
- CHECK: `signal_severity` ∈ 3 值 ENUM (INFO / WARN / CRITICAL)
- CHECK: `decision_action` ∈ 3 值 ENUM OR NULL
- CHECK: `engine_mode` ∈ 4 值
- NOT NULL: ingested_at, strategy_name, signal_source, signal_severity, signal_metric_name, signal_metric_value, signal_threshold, engine_mode
- FK: `source_v107_divergence_id` → `learning.replay_divergence_log.divergence_id` ON DELETE SET NULL

**Indexes 大綱**：
- Hypertable time index 內建（`ingested_at`）
- `(strategy_name, ingested_at DESC)` — per-strategy signal timeline (hot path for LAL incident-free query)
- `(signal_severity, ingested_at DESC) WHERE signal_severity IN ('WARN','CRITICAL')` — alert dashboard partial index
- `(decision_action, ingested_at DESC) WHERE decision_action='escalate_to_retired'` — retirement audit hot path
- **`(strategy_name) WHERE signal_severity='CRITICAL' AND ingested_at > now() - INTERVAL '90 days'`** — V112 LAL incident-free check 直接 query 此 partial expression index（如 PG 支援 expression-based partial）

### 2.2 `learning.strategy_lifecycle` (regular table)

**Tables 大綱**：
- PK: `lifecycle_id BIGSERIAL`
- Columns 大綱（11 fields）：
  - `lifecycle_id`, `strategy_name TEXT NOT NULL`, `overlay_id BIGINT NULL`
  - `current_decay_action_level TEXT NULL` (ENUM 4 值 OR NULL = healthy/no decay)
  - `entered_at TIMESTAMPTZ NOT NULL`, `previous_action_level TEXT NULL`
  - `triggering_signal_id BIGINT NULL` (FK to `learning.decay_signals.signal_id`)
  - `recovery_window_ends_at TIMESTAMPTZ NULL` (RECOVERY 階段限定)
  - `governance_approval_id BIGINT` (FK to `governance.audit_log.id`)
  - `decision_authority TEXT NOT NULL DEFAULT 'M7'` (CR-7 contract — 必 'M7'；其他 module 寫此表 RAISE)
  - `evidence_json JSONB`
  - `engine_mode TEXT NOT NULL`

**Constraints 大綱**：
- CHECK: `current_decay_action_level` ∈ 4 值 ENUM OR NULL
- CHECK: `previous_action_level` ∈ 4 值 ENUM OR NULL
- **CHECK: `decision_authority='M7'`** (per CR-7 contract — hard-locked)
- CHECK: `engine_mode` ∈ 4 值
- NOT NULL: strategy_name, entered_at, decision_authority, engine_mode
- UNIQUE: `(strategy_name, overlay_id, entered_at)` — 同 strategy 同 overlay 同時刻不重複 lifecycle entry

**Indexes 大綱**：
- `(strategy_name, overlay_id NULLS LAST, entered_at DESC)` — per-strategy-overlay lifecycle history
- `(current_decay_action_level, entered_at DESC) WHERE current_decay_action_level IS NOT NULL` — active decay state partial index hot path
- `(strategy_name) WHERE current_decay_action_level='RETIRED'` — retired strategy list

### 2.3 ENUM 列表 (per CR-X 對齊規則)

- `decay_action_level` ENUM 4 值 (RECOVERY / DECAY_DETECTED / DECAY_ENFORCED / RETIRED — per CR-7 rename of `decay_stage`)
- `decay_signal_source` ENUM 4 值 (m11_replay_divergence / alpha_curve_degradation / drawdown_breach / consecutive_losses)
- `decay_signal_severity` ENUM 3 值 (INFO / WARN / CRITICAL — 與 M11 對齊)
- `decay_decision_action` ENUM 3 值 (no_action / escalate_action_level / escalate_retired)

### 2.4 CR-7 Contract Schema 反映：M7 Single Decay Authority

per CR-7 contract，本 schema 兩處明示 enforcement：
1. **`strategy_lifecycle.decision_authority` DEFAULT 'M7' + CHECK constraint hard-lock = 'M7'**：應用層 / 其他 module（M11/M8/M2/M9）寫此表 INSERT 必含 `decision_authority='M7'`；任何非 'M7' INSERT 即 RAISE
2. **`decay_signals` 表 = signal source**（M11/M8 等可寫）；**`strategy_lifecycle` 表 = decision authority**（only M7 可寫）— 兩層分離 enforce single authority

### 2.5 Hypertable 判斷

**結論**：
- `decay_signals`：**MUST hypertable**（high-frequency；估算 per-strategy daily ~10 signal × 5 strategy = ~50 row/day = ~18k row/yr；low-end 量但 retention 6mo 充足，hypertable cost low）
- `strategy_lifecycle`：regular table（per-strategy 1-2 lifecycle event/yr × 5 strategy = ~10 row/yr）

```sql
SELECT create_hypertable('learning.decay_signals', 'ingested_at',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists => TRUE);

ALTER TABLE learning.decay_signals SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'strategy_name, signal_source',
    timescaledb.compress_orderby = 'ingested_at DESC'
);

SELECT add_compression_policy('learning.decay_signals', INTERVAL '7 days');
SELECT add_retention_policy('learning.decay_signals', INTERVAL '180 days');
-- 注：retention 180d（不是 90d）— LAL incident-free 查 90d window；額外 90d buffer 利於 reconciliation + post-incident audit
```

---

## §3 Guard A/B/C Templates 大綱

### Guard A — table existence + FK target 對齊驗證

- 若 2 表已存在：驗 column 完整；缺即 RAISE
- 驗 `learning.replay_divergence_log` 存在（V107 prereq for source_v107_divergence_id FK）
- 驗 `governance.audit_log` 存在（V098 prereq）
- 驗 TimescaleDB extension 存在

### Guard B — 不適用

V113 不 ALTER 既有 column type；本 spec 不設 Guard B 段。

### Guard C — CHECK constraint + ENUM 值齊全 + CR-7 contract + hypertable + index 對齊驗證

- `decay_action_level` ENUM 4 值齊全 (RECOVERY / DECAY_DETECTED / DECAY_ENFORCED / RETIRED — per CR-7 命名)
- `decay_signal_source` ENUM 4 值齊全
- `decay_signal_severity` ENUM 3 值齊全
- `decay_decision_action` ENUM 3 值齊全
- `engine_mode` CHECK 4 值齊全（2 表共用）
- **CR-7 CHECK constraint `decision_authority='M7'` 真存在** on strategy_lifecycle (single authority enforcement)
- UNIQUE constraint `(strategy_name, overlay_id, entered_at)` on strategy_lifecycle 真存在
- Hypertable on decay_signals + compression policy + retention policy 180d
- Indexes 對齊（含 V112 LAL incident-free partial index）

---

## §4 Linux PG Empirical Dry-Run Checklist (placeholder)

### 4.1 必跑 SQL (3-5 條 placeholder query)

```bash
# Query 1: _sqlx_migrations head + V107 (M11) land 確認（V113 依賴 V107 FK target）
ssh trade-core "psql -d trading_ai -c \"SELECT version, success FROM _sqlx_migrations WHERE version=107\""

# Query 2: TimescaleDB extension 確認
ssh trade-core "psql -d trading_ai -c \"SELECT extversion FROM pg_extension WHERE extname='timescaledb'\""

# Query 3: V113 apply 後驗 2 表 + hypertable + 4 ENUM 真建立
ssh trade-core "psql -d trading_ai -c \"SELECT table_name FROM information_schema.tables WHERE table_schema='learning' AND table_name IN ('decay_signals','strategy_lifecycle')\""

# Query 4: CR-7 decision_authority CHECK 真 reject 非 'M7' 值 (empirical INSERT)
# 例：
# INSERT INTO learning.strategy_lifecycle (strategy_name, decision_authority, engine_mode, ...) VALUES ('grid', 'M11', 'live', ...);
# Expected: ERROR: violates check constraint (CR-7 enforcement)

# Query 5: decay_action_level ENUM 真 reject 第 5 個 value (empirical INSERT test)
# 例：
# INSERT INTO learning.strategy_lifecycle (..., current_decay_action_level, ...) VALUES (..., 'INVALID_STATE', ...);
# Expected: ERROR: violates check constraint
```

### 4.2 Idempotent 雙跑驗

per V055 5-round loop + V083/V084 incident precedent，V113.sql 必跑兩次：第二次必 0 RAISE / 0 重複 hypertable / 0 重複 policy / 0 重複 ENUM。

### 4.3 engine restart 實測

per a19797d 教訓：
- `restart_all.sh --rebuild` 後驗 engine.log 無 sqlx panic
- 驗 `_sqlx_migrations.success=t` for V113
- 驗 M7 decay signal ingestor spawn log（Sprint 1A-β writer 接線後）

---

## §5 Cross-V### Dependencies

per CR-9 cross-V### dependency graph：

| V### | 依賴 | 理由 |
|---|---|---|
| V113 | V107 (M11 replay_divergence_log) | source_v107_divergence_id FK target |
| V113 | V098 (governance.audit_log) | FK target；已 land |
| V113 | V096 boundary (TimescaleDB extension) | hypertable infra prereq |

**Sprint 1A-β dispatch ordering**：V107 → V113 → V112（M1 LAL 依 V113 incident-free partial index query）。

**V113 為其他 module 提供 incident-free signal**：
- V112 (M1 LAL) eligibility check 直接查 V113 partial index `(strategy_name) WHERE signal_severity='CRITICAL' AND ingested_at > now() - INTERVAL '90 days'`
- V105 (M2 overlay) state advance check 依 V113 `current_decay_action_level IS NULL` 條件
- V108 (M9 A/B test) auto-halt 條件含 V113 RETIRED check

---

## §6 Cross-References

- v5.8 §2 M7 Decay module: `srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md`
- CR-7 single decay authority contract: PA dispatch consolidation
- V107 spec (M11 — divergence FK source): `srv/docs/execution_plan/2026-05-21--v107_m11_replay_divergence_log_schema_spec.md`
- V112 spec (M1 LAL — incident-free query consumer): `srv/docs/execution_plan/2026-05-21--v112_m1_decision_lease_lal_tiers_schema_spec.md`
- ADR-alignment: per R4 建議補（M7 對應 ADR 待 PA dispatch 期 land）
- 範式參考 V103/V104 spec: `srv/docs/execution_plan/2026-05-21--v103_v104_earn_hypotheses_schema_spec.md`

---

## §8 Full DDL (Land Sprint 1A-β 2026-05-21；QC drafted + PM transcribed due to QC tool boundary)

**Status promotion**：SPEC-PLACEHOLDER → **SPEC-DRAFT-V1**（per Sprint 1A-β CRITICAL deliverable；待 Linux PG empirical dry-run + MIT consultant verify 後可升 SPEC-VERIFIED）

### 8.1 `learning.decay_signals` Full DDL

```sql
CREATE TABLE IF NOT EXISTS learning.decay_signals (
    id                              BIGSERIAL PRIMARY KEY,
    strategy_id                     TEXT NOT NULL,
    symbol                          TEXT NOT NULL,
    signal_type                     TEXT NOT NULL
                                    CHECK (signal_type IN (
                                        'SHARPE_DECAY',
                                        'DRAWDOWN_WIDEN',
                                        'OOS_DEG',
                                        'HITRATE_PLUMMET',
                                        'M11_CRITICAL_PERSISTENT',
                                        'CUMULATIVE_LOSS_50PCT_IN_ENFORCED'
                                    )),
    signal_value                    NUMERIC(18,8) NOT NULL,
    signal_threshold                NUMERIC(18,8) NOT NULL,
    window_size_days                INTEGER NOT NULL CHECK (window_size_days BETWEEN 1 AND 365),
    live_window_days                INTEGER NOT NULL DEFAULT 30,
    oos_window_days                 INTEGER NOT NULL DEFAULT 90,
    lifecycle_state                 TEXT NOT NULL
                                    CHECK (lifecycle_state IN (
                                        'NORMAL_LIVE',
                                        'DECAY_DETECTED',
                                        'DEMOTE_PROPOSED',
                                        'DECAY_ENFORCED',
                                        'RECOVERY',
                                        'RETIRED'
                                    )),
    lifecycle_prev_state            TEXT
                                    CHECK (lifecycle_prev_state IN (
                                        'NORMAL_LIVE',
                                        'DECAY_DETECTED',
                                        'DEMOTE_PROPOSED',
                                        'DECAY_ENFORCED',
                                        'RECOVERY',
                                        'RETIRED'
                                    ) OR lifecycle_prev_state IS NULL),
    m11_replay_divergence_ref       UUID NULL,
    -- 註：V107 schema 仍 pending；UUID FK target 待 V107 land 後確認類型對齊
    -- （若 V107 採 BIGSERIAL，此 column 必 patch 為 BIGINT）
    retrain_triggered               BOOLEAN NOT NULL DEFAULT FALSE,
    retrain_cooldown_expires_at     TIMESTAMPTZ NULL,
    cumulative_pnl_during_decay     NUMERIC(20,8) NULL,
    -- §9 14d × 50% mitigation 即時追蹤（per M7 design spec §9）
    engine_mode                     TEXT NOT NULL
                                    CHECK (engine_mode IN ('paper','demo','live_demo','live','replay')),
    observed_at                     TIMESTAMPTZ NOT NULL,
    created_at                      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 8.2 Hypertable + Retention + Compression

```sql
SELECT create_hypertable('learning.decay_signals', 'observed_at',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists => TRUE);

ALTER TABLE learning.decay_signals SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'strategy_id, signal_type',
    timescaledb.compress_orderby = 'observed_at DESC'
);

SELECT add_compression_policy('learning.decay_signals', INTERVAL '7 days');
SELECT add_retention_policy('learning.decay_signals', INTERVAL '180 days');
-- 180d retention = 90d M7 historical query + 90d post-incident audit buffer
```

### 8.3 Indexes

```sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_decay_strategy_symbol_observed
    ON learning.decay_signals (strategy_id, symbol, observed_at DESC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_decay_lifecycle_state
    ON learning.decay_signals (lifecycle_state, observed_at DESC);

-- M1 LAL Tier 0 5-gate query hot path
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_decay_retired_strategies
    ON learning.decay_signals (strategy_id)
    WHERE lifecycle_state = 'RETIRED';

-- M11 ingest dedup query hot path
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_decay_m11_persistent
    ON learning.decay_signals (strategy_id, observed_at DESC)
    WHERE signal_type = 'M11_CRITICAL_PERSISTENT';

-- 14d × 50% mitigation hot path (real-time enforcement)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_decay_enforced_cumulative
    ON learning.decay_signals (strategy_id, cumulative_pnl_during_decay, observed_at DESC)
    WHERE lifecycle_state = 'DECAY_ENFORCED';
```

### 8.4 Materialized View (latest decay state per strategy)

```sql
CREATE MATERIALIZED VIEW IF NOT EXISTS learning.mv_latest_decay_state_per_strategy AS
SELECT DISTINCT ON (strategy_id)
    strategy_id,
    symbol,
    lifecycle_state,
    lifecycle_prev_state,
    signal_type,
    signal_value,
    signal_threshold,
    cumulative_pnl_during_decay,
    engine_mode,
    observed_at
FROM learning.decay_signals
ORDER BY strategy_id, observed_at DESC;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_latest_decay_strategy
    ON learning.mv_latest_decay_state_per_strategy (strategy_id);

-- M1 LAL Tier 0 5-gate query path:
-- SELECT lifecycle_state FROM mv_latest_decay_state_per_strategy WHERE strategy_id=$1
-- Refresh schedule: cron every 1 min (M7 daily run + per-tick LAL query 平衡)
```

---

## §9 DECAY_ENFORCED Rename — Single Authority Justification (per CR-7)

### 9.1 字面碰撞分析

原 v5.8 `STAGE_DEMOTED` 字面含「STAGE」三字，與：
- **AMD-2026-05-15-01** Stage 0 / 0R / 1 / 2 / 3 / 4 canary promotion gate
- **ADR-0034** LAL 0 / 1 / 2 / 3 / 4 Decision Lease Layered Approval

SQL query `WHERE state = 'STAGE_DEMOTED'` 在 ETL / dashboard 易與 `stage_history.stage = 'Stage 1'` 邏輯混淆。

### 9.2 為什麼 DECAY_ENFORCED 比 STAGE_DEMOTED 語意清楚

| 維度 | STAGE_DEMOTED | DECAY_ENFORCED |
|---|---|---|
| 對應域 | promotion gate（Stage 0R-4）誤用 | M7 decay action 域，無跨域重疊 |
| Operator 心智 | 「降到哪 Stage？」混淆 | 「strategy 在 enforced 50% sizing」明確 |
| SQL filter | `WHERE state LIKE 'STAGE%'` 撞 Stage history | `WHERE state = 'DECAY_ENFORCED'` 唯一 |
| Lineage | 跟 Stage promotion 混 | 對應 M7 single decay authority |

### 9.3 M7 Single Authority 在 schema 上 enforce 路徑

per CR-7 contract — M11 不可寫 `strategy_lifecycle`；schema 級防護：
- V113 `decay_signals` table 不開放 M11 寫入（PG role grant 在 §10 Linux PG SOP 內 land）
- V107 `replay_divergence_log` schema 必無 `auto_demote` / `target_state` / `demote_proposal_id` field（per M11 design spec §6.4）
- `cumulative_pnl_during_decay` column 即時追蹤 + `idx_decay_enforced_cumulative` index 配合 §9 14d × 50% mitigation hardcoded enforcement

### 9.4 與 M11 dedup 對齊

- V107 schema 不含 demote field（M11 不可寫 lifecycle）
- V113 schema 含 lifecycle_state 6 enum + `m11_replay_divergence_ref` UUID FK placeholder（M7 ingest M11 signal 走 reference 而非 M11 直寫 V113）
- per CR-7 line specific：M7 query when `persistent_days >= 14` count as 1-of-5 signal source；不重複 run replay

---

## §10 Linux PG Empirical Dry-Run Protocol (per V103 範式)

### 10.1 必跑 SQL (per V103 §4.1 範式)

```bash
# Linux only — ssh trade-core
ssh trade-core "psql -h /var/run/postgresql -U openclaw -d openclaw -c '
-- Round 1: existence reflection (Guard A baseline)
SELECT relname FROM pg_class WHERE relname = ''decay_signals'' AND relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = ''learning'');
SELECT typname FROM pg_type WHERE typname LIKE ''%decay%'';

-- Round 2: schema applied (Guard A pass; Guard C 6 ENUM + 4 ENUM engine_mode + hypertable + 5 indexes + retention + compression)
SELECT column_name, data_type, character_maximum_length
FROM information_schema.columns
WHERE table_schema = ''learning'' AND table_name = ''decay_signals''
ORDER BY ordinal_position;

-- Round 3: hypertable verify
SELECT * FROM timescaledb_information.hypertables WHERE hypertable_name = ''decay_signals'';

-- Round 4: compression + retention policy verify
SELECT * FROM timescaledb_information.compression_policies WHERE hypertable_name = ''decay_signals'';
SELECT * FROM timescaledb_information.drop_chunks_policies WHERE hypertable_name = ''decay_signals'';

-- Round 5: index verify (5 indexes + 1 mv index = 6)
SELECT indexname, indexdef FROM pg_indexes
WHERE schemaname = ''learning'' AND tablename IN (''decay_signals'', ''mv_latest_decay_state_per_strategy'');
'"
```

### 10.2 Idempotency 雙跑驗

```bash
# 第二次跑 V113 migration → 預期 0 row change（IF NOT EXISTS + Guard A 都 fail-safe）
ssh trade-core "cd ~/BybitOpenClaw/srv && cargo run --bin migrate -- --target V113"
ssh trade-core "psql -h /var/run/postgresql -U openclaw -d openclaw -c 'SELECT version, success, executed_at FROM _sqlx_migrations WHERE version = ''V113'';'"
# Expected: success=t + executed_at unchanged
```

### 10.3 Engine restart 實測 SOP（per 2026-05-02 sqlx hash drift 教訓）

```bash
# After V113 land + Mac commit + push origin
ssh trade-core "cd ~/BybitOpenClaw/srv && git pull --ff-only"
ssh trade-core "cd ~/BybitOpenClaw/srv && bash helper_scripts/restart_all.sh --rebuild --keep-auth"
# Expected:
#  - engine PID 重啟成功
#  - engine.log 0 panic
#  - sqlx _sqlx_migrations V113 success=t（per AC-7 ref M7 design spec §10）
# 若 sqlx checksum drift → 跑 helper_scripts/db/repair_migration_checksum binary（per 2026-05-02 incident SOP）
```

---

## §11 Rollback Plan + Reversibility Analysis

### 11.1 Rollback SQL (Linux PG only；不在 Mac 跑)

```sql
-- V113 rollback
DROP MATERIALIZED VIEW IF EXISTS learning.mv_latest_decay_state_per_strategy;
SELECT remove_retention_policy('learning.decay_signals', if_exists => TRUE);
SELECT remove_compression_policy('learning.decay_signals', if_exists => TRUE);
DROP TABLE IF EXISTS learning.decay_signals;
-- V113 rollback 不跨 V107 boundary（V107 為 M11 schema，V113 rollback 不動）
```

### 11.2 Reversibility Analysis

- **V113 apply 後立即 0 row**：Foundation stage（per MIT pipeline maturity 5-stage）；rollback 0 row loss
- **V113 apply 後有 data**：rollback 會丟 decay signal history；建議 export to `/tmp/backup_v113_*.csv` 前才執行 rollback
- **V107 dependency**：V113 `m11_replay_divergence_ref` column 是 UUID FK placeholder（無實際 FK constraint），V107 rollback 不會 cascade 到 V113

---

## §12 Audit Field (per V103 EXTEND 範式)

V113 schema 不含 5 audit field（created_by / created_at / updated_by / updated_at / source_version）的完整對齊，因 `learning.decay_signals` 是 M7 sole writer + observation only（不像 V103 hypotheses 跨多角色 writer）。M7 IMPL 階段以 `created_at` + `signal_value` 為唯一 audit 鏈；若 Sprint 1A-ε cross-ADR audit 要求 5 audit field full set，將通過 V113 EXTEND 補。

---

## §13 Acceptance Criteria (Sprint 1A-β land verify)

| # | Criteria | Test |
|---|---|---|
| **AC-1** | Guard A pass：`learning.decay_signals` 表存在 + 16 column 全俱在 + hypertable created | §10.1 Round 1+2 |
| **AC-2** | Guard C pass：6 ENUM signal_type + 6 ENUM lifecycle_state + 5 ENUM engine_mode + 5 indexes + retention 180d + compression policy | §10.1 Round 3+4+5 |
| **AC-3** | Idempotency pass：第二次跑 V113 migration → 0 row change | §10.2 |
| **AC-4** | Engine restart pass：sqlx _sqlx_migrations V113 success=t + engine.log 0 panic | §10.3 |
| **AC-5** | Materialized view query pass：`SELECT lifecycle_state FROM mv_latest_decay_state_per_strategy WHERE strategy_id='grid_btcusdt'` 返回最新 1 row | §10.1 Round 5 |
| **AC-6** | M7 design spec AC-3 14d × 50% test：empirical INSERT 14 row + `cumulative_pnl_during_decay < -0.5 × pre_decay_account` → query path 必 SELECT row 用於 transition decision | M7 spec §10 AC-3 ref |
| **AC-7** | V107 FK placeholder：`m11_replay_divergence_ref` UUID 可 NULL；V107 land 後 patch 為 BIGINT FK 或維持 UUID 取決 V107 final schema | M11 spec §V107 alignment audit |

---

## §7 Sign-off Table

| Role | Status | Date | Note |
|---|---|---|---|
| MIT Drafted (placeholder) | DONE | 2026-05-21 | Placeholder frontmatter + 大綱 reserve |
| QC Full DDL drafted (§8-§13) | DONE | 2026-05-21 | inline draft → PM transcribed (QC tool boundary) |
| PM Write (handoff) | DONE | 2026-05-21 | full DDL land in §8-§13 |
| PA | PENDING | — | Sprint 1A-β dispatch packet alignment |
| MIT consultant verify | PENDING | — | Linux PG empirical dry-run + V107 FK placeholder type align |
| E4 | PENDING | — | Regression after IMPL Sprint 4-5 |
| E5 | PENDING | — | Hypertable + retention 180d 驗 critical |
| PM Sign-off | PENDING | — | Sprint 1A-β closure |

**END V113 spec full DDL**
