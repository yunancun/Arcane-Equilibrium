---
spec: V103 EXTEND M4 — Hypothesis Source / Leakage / Cowork Review Schema
date: 2026-05-21
author: MIT inline draft (a4d52063) → PM transcribed (MIT tool boundary 禁 Write/Edit)
phase: v5.8 Sprint 1A-γ M4 module DDL prerequisite — Gap I-A patch
status: SPEC-DRAFT-V0（MIT 起草；待 PA Linux PG dry-run 補資料 + PM sign-off）
parent specs:
  - srv/docs/execution_plan/2026-05-21--m4_hypothesis_discovery_design_spec.md §10 V103 EXTEND outline
  - srv/docs/execution_plan/2026-05-21--v103_v104_earn_hypotheses_schema_spec.md（base V103 spec；本 EXTEND 加 column 至 既有 learning.hypotheses 表）
  - srv/docs/execution_plan/2026-05-21--v103_v104_linux_pg_dry_run.md（empirical PG state + V### race-aware re-number Q1 verdict pending）
  - srv/docs/adr/0045-m4-hypothesis-discovery-governance.md (M4 governance authority reserved；per R4 C-1 patch)
scope: design / spec only — 不寫 .sql 實檔；不在 Mac 跑 SQL；不改 Rust/Python writer；不執行 PG
---

# V103 EXTEND for M4 Hypothesis Discovery Columns — Schema Spec

## §0 TL;DR

- **第二組 EXTEND**：base V103 §14 已 land 5 audit field；本 EXTEND 是 M4 專用 6 column per M4 spec §10。
- **6 new column**：`hypothesis_source_module` (M4_AUTO/OPERATOR/HISTORIC enum) + `leakage_scan_pass` (BOOLEAN DEFAULT FALSE) + `bonferroni_corrected_p` (NUMERIC(10,8) CHECK [0,1]) + `replicability_score` (NUMERIC(5,4) CHECK [0,1]) + `decision_lease_draft_id` (UUID FK placeholder) + `cowork_review_status` (NONE/PENDING/APPROVED/REJECTED enum).
- **Guard B 強制**：6 段 DO block 預檢 type/CHECK/DEFAULT mismatch 觸發 RAISE EXCEPTION + base V103 prereq (hypothesis_id 必存在) 驗.
- **3 hot-path index** CREATE CONCURRENTLY IF NOT EXISTS：source_module + created_at DESC / leakage_scan_pass partial WHERE TRUE / cowork_review_status partial WHERE != 'NONE'.
- **Linux PG empirical dry-run mandatory**（per CLAUDE.md §Data + V055 mandate）：5 reflection SQL + Round 1/2 idempotency + engine restart 實測.
- **V### race-aware caveat**：per PA dry-run option A 若採 V099/V100=Track v3 → V101/V102=Earn schema，本 EXTEND 須 rename V103 → V101；待 PM Q1 verdict 後 final 鎖定.
- **DEFAULT 'OPERATOR'** for `hypothesis_source_module` (vs M4 outline 寫 'M4_AUTO')：既有 row 100% operator source；backfill 'M4_AUTO' 會 silent contamination；MIT 推薦 Path A.

## §1 Background + Scope

### §1.1 Gap I-A — Sprint 4+ M4 IMPL 阻塞 prerequisite

M4 spec §10 列「V103 EXTEND for M4 column（Outline Only — Not Implementation）」明示「本 spec 不寫實 ALTER SQL；完整 DDL 由後續 sub-agent 補」。本 spec 即 outline 升 full DDL deliverable。Sprint 4+ M4 Pattern miner Stage 4 DRAFT writeback 需 V103 EXTEND 6 column 已 land 才 INSERT；缺即阻塞 IMPL kickoff.

### §1.2 與 base V103 §14 並存 (2 EXTEND 不重疊)

| EXTEND | 用途 | column 集合 |
|---|---|---|
| base V103 §14 | 通用 audit trail | lease_id / approval_id / actor_id / bybit_request_payload / rationale |
| **本 V103 EXTEND M4** | M4 discovery 專用 statistical/lineage | hypothesis_source_module / leakage_scan_pass / bonferroni_corrected_p / replicability_score / decision_lease_draft_id / cowork_review_status |

§14 `lease_id` = promotion lease；本 EXTEND `decision_lease_draft_id` = M4 DRAFT writeback lease；兩個 lease 不同。

### §1.3 V### naming race

per PA dry-run option A：若 V099/V100=Track v3 + V101/V102=Earn schema 採納，本 EXTEND 應 V101 EXTEND M4 而非 V103 EXTEND M4。**暫用 V103** per operator prompt 文字；PM Q1 verdict 後 final.

---

## §2 Schema EXTEND — 6 New Column

### §2.1 完整 ALTER TABLE DDL

```sql
-- V103 EXTEND M4 — Hypothesis Discovery 專用 6 column ADD
-- 對既有 learning.hypotheses 表（base V103 §2.1.1 創建）EXTEND
-- 每條 ADD COLUMN 含 Guard B IF NOT EXISTS + DEFAULT（避空表 NOT NULL fail）

ALTER TABLE learning.hypotheses
    ADD COLUMN IF NOT EXISTS hypothesis_source_module TEXT
        NOT NULL DEFAULT 'OPERATOR'
        CHECK (hypothesis_source_module IN ('M4_AUTO', 'OPERATOR', 'HISTORIC'));

ALTER TABLE learning.hypotheses
    ADD COLUMN IF NOT EXISTS leakage_scan_pass BOOLEAN
        NOT NULL DEFAULT FALSE;

ALTER TABLE learning.hypotheses
    ADD COLUMN IF NOT EXISTS bonferroni_corrected_p NUMERIC(10, 8)
        CHECK (bonferroni_corrected_p IS NULL
               OR (bonferroni_corrected_p >= 0 AND bonferroni_corrected_p <= 1));

ALTER TABLE learning.hypotheses
    ADD COLUMN IF NOT EXISTS replicability_score NUMERIC(5, 4)
        CHECK (replicability_score IS NULL
               OR (replicability_score >= 0 AND replicability_score <= 1));

ALTER TABLE learning.hypotheses
    ADD COLUMN IF NOT EXISTS decision_lease_draft_id UUID;
    -- FK 暫不加；待 V099/V100 lease tables land + PA 確認 FK target column name 後
    -- 由後續 EXTEND 加 REFERENCES governance.decision_lease(lease_id)

ALTER TABLE learning.hypotheses
    ADD COLUMN IF NOT EXISTS cowork_review_status TEXT
        NOT NULL DEFAULT 'NONE'
        CHECK (cowork_review_status IN ('NONE', 'PENDING', 'APPROVED', 'REJECTED'));
```

### §2.2 Column 對照 + 設計理由

| Column | Type | DEFAULT | CHECK | 用途 |
|---|---|---|---|---|
| `hypothesis_source_module` | TEXT | `'OPERATOR'` | 3 enum | DRAFT 來源 — M4 vs Cowork vs HISTORIC import |
| `leakage_scan_pass` | BOOLEAN | `FALSE` | — | Stage 3 leakage scan 結果；fail-closed (per 根原則 #6) |
| `bonferroni_corrected_p` | NUMERIC(10,8) | NULL | [0,1] | K=2500 × 5 window 場景 corrected p 範圍 |
| `replicability_score` | NUMERIC(5,4) | NULL | [0,1] | sub-period stability + cross-asset robustness composite |
| `decision_lease_draft_id` | UUID | NULL | — | M4 DRAFT writeback lease backref；FK 暫不加 |
| `cowork_review_status` | TEXT | `'NONE'` | 4 enum | Cowork hybrid review state |

**關鍵設計**：
- `hypothesis_source_module DEFAULT 'OPERATOR'` 而非 'M4_AUTO' — 既有 row 100% 是 operator/Cowork 寫；backfill 'M4_AUTO' 會錯標 silent contamination
- `leakage_scan_pass DEFAULT FALSE` — Fail-closed per 根原則 #6；既有 row 未跑 leakage scan 預設 FALSE
- `decision_lease_draft_id` UUID 非 BIGINT — 對齊 ADR-0034 M1 Decision Lease UUID 模式

---

## §3 Guard B — Type-Sensitive ADD COLUMN

### §3.1 6 段 Guard B DO Block

```sql
DO $$
DECLARE
    v_col_type TEXT;
    v_col_default TEXT;
    v_constraint_def TEXT;
BEGIN
    -- Guard B-prereq: base V103 既有 column 必齊全
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='learning' AND table_name='hypotheses'
          AND column_name='hypothesis_id'
    ) THEN
        RAISE EXCEPTION 'V103 EXTEND M4 Guard B FAIL: base V103 not yet applied';
    END IF;

    -- Guard B-1: hypothesis_source_module type + CHECK enum (M4_AUTO/OPERATOR/HISTORIC) 驗
    SELECT data_type INTO v_col_type FROM information_schema.columns
    WHERE table_schema='learning' AND table_name='hypotheses' AND column_name='hypothesis_source_module';
    IF v_col_type IS NOT NULL AND v_col_type != 'text' THEN
        RAISE EXCEPTION 'V103 EXTEND M4 Guard B-1 FAIL: hypothesis_source_module type % (expected text)', v_col_type;
    END IF;

    -- Guard B-2: leakage_scan_pass type=boolean + DEFAULT must be FALSE (fail-closed)
    SELECT data_type, column_default INTO v_col_type, v_col_default FROM information_schema.columns
    WHERE table_schema='learning' AND table_name='hypotheses' AND column_name='leakage_scan_pass';
    IF v_col_type IS NOT NULL AND v_col_type != 'boolean' THEN
        RAISE EXCEPTION 'V103 EXTEND M4 Guard B-2 FAIL: leakage_scan_pass type % (expected boolean)', v_col_type;
    END IF;
    IF v_col_type = 'boolean' AND v_col_default IS NOT NULL AND position('false' IN lower(v_col_default)) = 0 THEN
        RAISE EXCEPTION 'V103 EXTEND M4 Guard B-2 FAIL: leakage_scan_pass DEFAULT %  (expected FALSE for fail-closed)', v_col_default;
    END IF;

    -- Guard B-3/4: bonferroni_corrected_p + replicability_score type=numeric 驗
    -- (省略；同模式)

    -- Guard B-5: decision_lease_draft_id type=uuid 驗
    SELECT data_type INTO v_col_type FROM information_schema.columns
    WHERE table_schema='learning' AND table_name='hypotheses' AND column_name='decision_lease_draft_id';
    IF v_col_type IS NOT NULL AND v_col_type != 'uuid' THEN
        RAISE EXCEPTION 'V103 EXTEND M4 Guard B-5 FAIL: decision_lease_draft_id type % (expected uuid)', v_col_type;
    END IF;

    -- Guard B-6: cowork_review_status type + CHECK enum (NONE/PENDING/APPROVED/REJECTED) 驗
    -- (省略；同 B-1 模式 driving NONE/PENDING/APPROVED/REJECTED enum 4 values)
END $$;
```

### §3.2 Guard B 觸發場景

| 場景 | RAISE? |
|---|---|
| 首次 apply 6 column 全不存在 | NO (idempotent) |
| 重跑 V103 EXTEND M4 (type/CHECK 一致) | NO (skip RAISE) |
| `hypothesis_source_module` 已存在但 VARCHAR(50) 非 TEXT | RAISE |
| `leakage_scan_pass` DEFAULT TRUE | RAISE (違反 fail-closed) |
| base V103 未 apply (hypothesis_id 不存在) | RAISE (dependency 缺失) |

---

## §4 Linux PG Empirical Dry-Run Protocol

### §4.1 PG 連線 (per PA dry-run §1)

```
Host:     127.0.0.1
Port:     5432
User:     trading_admin
Database: trading_ai
Auth:     ~/.pgpass (chmod 600)
```

### §4.2 Pre-dry-run reflection (5 SQL)

```bash
# Query 1: base V103 既有 column 確認
ssh trade-core "psql -h 127.0.0.1 -p 5432 -U trading_admin -d trading_ai -c \"
SELECT column_name, data_type FROM information_schema.columns
WHERE table_schema='learning' AND table_name='hypotheses' ORDER BY ordinal_position;
\""
# Expected: 13 base + 5 §14 audit = 18 row

# Query 2: 6 column 不存在驗 (首次 apply 前)
# Expected: 0 (首次 apply 前); 6 (apply 後)

# Query 3: governance.decision_lease lease_id column 確認 (FK target placeholder)
# Expected: 'lease_id' UUID

# Query 4: 既有 row count
# Expected: 0-100 row

# Query 5: _sqlx_migrations head
```

### §4.3 Round 1 — V103 EXTEND M4 SQL apply + 6 項 verify

```bash
ssh trade-core "cd ~/BybitOpenClaw/srv && psql -h 127.0.0.1 -p 5432 -U trading_admin -d trading_ai \
  -v ON_ERROR_STOP=1 -f sql/migrations/V103_EXTEND__m4_hypothesis_columns.sql"
```

**6 verify SQL** (per V094 §5 範式):
1. 6 column count = 6
2. 3 CHECK enum constraint 齊全 (M4_AUTO/OPERATOR/HISTORIC + NONE/PENDING/APPROVED/REJECTED + [0,1] range)
3. CHECK constraint empirical reject test (INSERT 'INVALID_SOURCE' → ERROR)
4. DEFAULT 正確 (OPERATOR / FALSE / NONE)
5. 既有 row 全 backfill DEFAULT
6. 3 hot-path index CREATE

### §4.4 Round 2 — Idempotency

重跑 V103 EXTEND M4.sql 必：exit code 0 + Guard B 6 段全 skip RAISE + column/index/constraint count 不變.

### §4.5 Engine restart sqlx 0 panic

```bash
ssh trade-core "bash ~/BybitOpenClaw/srv/helper_scripts/restart_all.sh --rebuild"
ssh trade-core "tail -200 ~/BybitOpenClaw/srv/program_code/.../engine.log 2>&1 | grep -E 'sqlx|panic|V103|EXTEND'"
# Expected: 0 panic
ssh trade-core "psql ... -c \"SELECT version, success FROM _sqlx_migrations WHERE description LIKE '%EXTEND%m4%';\""
# Expected: 1 row success=t
```

---

## §5 Index Strategy

### §5.1 3 hot-path index

```sql
-- Hot-path 1: M4 dashboard query
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_hypotheses_source_module
    ON learning.hypotheses (hypothesis_source_module, created_at DESC);

-- Hot-path 2: M9 A/B queue (only PASS subset)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_hypotheses_leakage_pass
    ON learning.hypotheses (leakage_scan_pass)
    WHERE leakage_scan_pass = TRUE;

-- Hot-path 3: Cowork review dashboard (only active subset)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_hypotheses_cowork_review
    ON learning.hypotheses (cowork_review_status)
    WHERE cowork_review_status != 'NONE';
```

### §5.2 Query Plan 驗 (Round 1 後)

3 EXPLAIN ANALYZE 全顯示 Index Scan 非 Seq Scan.

---

## §6 Migration up + down

### §6.1 Migration up (file outline)

```sql
-- V103_EXTEND__m4_hypothesis_columns.sql
BEGIN;
DO $$ ... Guard B 6 段 ... END $$;
ALTER TABLE learning.hypotheses ADD COLUMN IF NOT EXISTS ... 6 條 ...;
COMMIT;
-- CREATE INDEX CONCURRENTLY 不能 in transaction
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_hypotheses_source_module ...;
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_hypotheses_leakage_pass ...;
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_hypotheses_cowork_review ...;
INSERT INTO learning.migration_marker (marker, applied_at) VALUES ('V103_EXTEND_M4', now())
ON CONFLICT (marker) DO NOTHING;
```

### §6.2 Migration down (dev only)

```sql
-- DROP INDEX CONCURRENTLY 3 條 + DROP COLUMN 6 條 + DELETE marker
-- Warning: production rollback 不建議 (5/6 column 不可逆 — leakage_scan_pass / bonferroni_corrected_p / replicability_score / decision_lease_draft_id 全失重建需 retroactive 重跑)
```

---

## §7 Cross-V### Dependency

```
base V103 (existing learning.hypotheses)
  ↓
本 EXTEND (V103 EXTEND M4 — 6 column)
  ↓
V108 (M9 A/B framework) — FK references hypothesis_id (M9 worker 讀 hypothesis 完整 metadata)
  
decision_lease_draft_id UUID = placeholder FK → V099/V100 lease tables (governance.decision_lease.lease_id)
  待 V099/V100 land 後加 ALTER ADD CONSTRAINT NOT VALID
V111 (M10 discovery tier) — 不直接 ref hypothesis_id
```

### §7.1 V108 約束

V108 IMPL 前本 EXTEND 必 land；否則 V108 FK target 缺 6 column = M9 worker 讀 metadata 不全.

---

## §8 Engine Restart SOP + sqlx Checksum Repair

per memory `project_2026_05_02_p0_sqlx_hash_drift` + commit `3681f83`:

```bash
# Step 1: E1 寫 V103_EXTEND__m4_hypothesis_columns.sql
# Step 2: Linux PG dry-run × 2 round (per §4.3 + §4.4)
# Step 3: 若 file edit 後 DB checksum drift → 跑 repair binary 同步
ssh trade-core "cd ~/BybitOpenClaw/srv && cargo run --release --bin repair_migration_checksum -- --version <V103_EXTEND_actual_version_number>"
# Step 4: engine restart 驗 sqlx migrate runtime
ssh trade-core "bash ~/BybitOpenClaw/srv/helper_scripts/restart_all.sh --rebuild"
# Step 5: 驗 _sqlx_migrations success=t
```

**Naming convention 待 PM 拍板**: `V103.1__m4_hypothesis_columns_extend.sql` (sqlx sub-version) vs `V<next-free>__m4_hypothesis_columns_extend.sql` (option A 重編後).

---

## §9 Rollback Plan + Reversibility Analysis

### §9.1 Rollback 三 Tier

| Tier | 場景 | 動作 | 風險 |
|---|---|---|---|
| **Tier 1 (dev/staging)** | schema 設計錯 | §6.2 down | 0 |
| **Tier 2 (production hotfix)** | apply 後 M4 寫入 fail | 不 DROP；patch code or disable M4 cron | 低 |
| **Tier 3 (production schema reversal)** | base V103 重設計 | §6.2 down + ADR-level + 24h freeze | 高 (5/6 不可逆) |

### §9.2 Reversibility per Column

| Column | Reversible? | 不可逆風險 |
|---|---|---|
| `hypothesis_source_module` | YES | DROP 後重建錯標 |
| `leakage_scan_pass` | NO | 已 PASS 重建需重跑 leakage scan |
| `bonferroni_corrected_p` | NO | 重建需重跑 K hypothesis × statistical engine |
| `replicability_score` | NO | 同上 |
| `decision_lease_draft_id` | NO | audit chain 永久缺口 |
| `cowork_review_status` | PARTIAL | Y2 啟用後 review history 全失 |

**Production reversal 不建議**：替代路徑 = patch M4 Pattern miner code 或 disable M4 cron job → 0 schema 改動.

---

## §10 Audit Field

本 EXTEND 6 column 已含 lifecycle 屬性 (`cowork_review_status` / `leakage_scan_pass`)；不需單獨 audit field. 借用 base V103 §14 5 audit field (`actor_id` / `rationale` 等). 不重疊 (per §1.2).

---

## §11 Acceptance Criteria

| AC | 驗收方式 |
|---|---|
| **AC-1** | 6 column 全 add — `SELECT count(*) ... WHERE column_name IN (...)` = 6 |
| **AC-2** | 3 CHECK ENUM reject invalid empirical — INSERT 'INVALID_SOURCE' / 'INVALID_REVIEW_STATE' / p=1.5 全 ERROR |
| **AC-3** | Idempotency 雙跑驗 0 RAISE — 第二次 exit code 0 / column count 6 不變 |
| **AC-4** | Engine restart sqlx 0 panic — engine.log 0 'panic' + `_sqlx_migrations` success=t |
| **AC-5** | 3 index created + query plan use — 3 EXPLAIN ANALYZE 全 Index Scan |
| **AC-6** | Cross-language 1e-4 fixture — M4 Pattern miner Rust insert + Python SELECT 6 column 值 max diff < 1e-4 |
| **AC-7** | 既有 row 全 backfill DEFAULT — Round 1 #5 |
| **AC-8** | Guard B RAISE 真實 trigger (destructive dev test) — manual CREATE 不同 type → re-apply → Guard B-1 RAISE |

---

## §12 IMPL Plan + Sign-off

### §12.1 E1 工作鏈

```
本 spec PM sign-off + PA Linux PG dry-run 補資料
  ↓
PA dispatch decide V### final number (option A → V101 EXTEND M4 或保留 V103 EXTEND M4)
  ↓
E1 IMPL: 寫 V103_EXTEND__m4_hypothesis_columns.sql (~165 LOC)
  ↓
E2 review (查 Guard B 6 段 + cross-V### dep)
  ↓
E4 regression (cargo test + pytest)
  ↓
ssh trade-core Linux PG dry-run × 2 round
  ↓
restart_all --rebuild deploy
  ↓
engine restart verify sqlx migrate runtime PASS
  ↓
PM sign-off
```

### §12.2 Sign-off Status

| Agent | Status | Note |
|---|---|---|
| **MIT** | **Drafted** | inline a4d52063 → PM transcribed 2026-05-21 |
| **PM** | **PENDING** | V### final number Q1 verdict + DEFAULT 'OPERATOR' vs 'M4_AUTO' Path A/B 拍板 |
| **PA** | **PENDING** | Linux PG dry-run × 2 round + V### naming 拍板 |
| **E2** | **PENDING** | Guard B 6 段 + cross-V### dep 驗 |
| **E4** | **PENDING** | regression after IMPL |
| **E3** | **PENDING** | rationale field secret leak audit |

---

## §13 Cross-References

- M4 spec §10 outline: `srv/docs/execution_plan/2026-05-21--m4_hypothesis_discovery_design_spec.md`
- base V103 spec: `srv/docs/execution_plan/2026-05-21--v103_v104_earn_hypotheses_schema_spec.md`
- PA Linux PG dry-run: `srv/docs/execution_plan/2026-05-21--v103_v104_linux_pg_dry_run.md`
- ADR-0024-lite: `srv/docs/adr/0024-cowork-subscription-operator-assistant.md`
- AMD-2026-05-21-01: `srv/docs/governance_dev/amendments/2026-05-21--AMD-2026-05-21-01*.md`
- ADR-0034 M1 LAL: `srv/docs/adr/0034-decision-lease-layered-approval-lal.md`
- ADR-0045 M4 governance: `srv/docs/adr/0045-m4-hypothesis-discovery-governance.md` (reserved)
- Memory: `feedback_v_migration_pg_dry_run.md` / `feedback_indicator_lookahead_bias.md` / `project_2026_05_02_p0_sqlx_hash_drift.md`

---

## §14 Open Issues — PM Decisions Needed

### Issue 1: V### final number (V103 vs V101)

- Path A: V103 EXTEND M4 (按 operator prompt 文字)
- Path B: V101 EXTEND M4 (per PA dry-run option A re-number)

**PA dispatch consolidation 待 finalize.**

### Issue 2: DEFAULT 'OPERATOR' vs 'M4_AUTO' (本 spec §2.2 vs M4 outline §10.2)

- Path A (本 spec): DEFAULT 'OPERATOR'，既有 row 自動正確 backfill (對既有 row 友善 + 0 follow-up task)
- Path B (嚴格對齊 M4 outline): DEFAULT 'M4_AUTO'，Sprint 1B 加 backfill task 顯式 update 既有 row 'OPERATOR'

**MIT 推薦 Path A**；PM 拍板.

### Issue 3: Naming convention

- Option 1: `V103.1__m4_hypothesis_columns_extend.sql` (sqlx sub-version)
- Option 2: `V<next-free>__m4_hypothesis_columns_extend.sql` (option A re-number 後)
- Option 3: 合 base V103 + EXTEND 單檔 (不推薦)

**PA dispatch 前必 PM 拍板.**

---

**END V103 EXTEND M4 schema spec**

**MIT inline draft a4d52063 → PM transcribed 2026-05-21 per Gap I-A**
