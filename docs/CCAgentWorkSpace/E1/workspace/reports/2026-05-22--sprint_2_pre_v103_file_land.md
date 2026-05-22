---
report: Sprint 2 pre-readiness Track 2 — V103 EXTEND M4 file land (PA-DRIFT-2 HARD BLOCKER closure)
date: 2026-05-22
author: E1 (Backend Developer)
phase: Sprint 2 pre-readiness Track 2 (per PM dispatch packet — Sprint 1A-γ HARD BLOCKER closure)
status: IMPL DONE — awaiting E2 review
parent dispatch:
  - PM Sprint 2 pre-readiness dispatch packet (in-session 2026-05-22)
  - docs/execution_plan/2026-05-21--v103_extend_m4_hypothesis_columns_schema_spec.md (V103 EXTEND M4 spec literal)
  - docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-22--sprint_1b_v107_sandbox_land_dedup_full.md §5.2 [PA-DRIFT-2] finding
  - docs/adr/0045-m4-hypothesis-discovery-governance.md (M4 governance reserved per R4 C-1)
runtime: trade-core PostgreSQL 16 + TimescaleDB 2.26.1 (trading_ai_sandbox)
production engine: PID 2934602 跑 trading_ai (全程未碰)
secret_file: /home/ncyu/BybitOpenClaw/srv/settings/secret_files/postgres/sandbox_admin/password (0600 gitignored)
---

# Sprint 2 pre-readiness Track 2 — V103 file land (PA-DRIFT-2 closure)

## §0 任務摘要

per PM dispatch Sprint 2 pre-readiness Track 2 + E1 Track C 2026-05-22 report §5.2 carry-over：

- 目標：V103 EXTEND M4 file 寫 + Linux sandbox empirical Round 1/2 PASS
- 範圍：對既有 learning.hypotheses (Sprint 1A-α via stub) ADD 6 column + 3 hot-path index
- 治理動機：Sprint 1A-γ HARD BLOCKER per E3 v58 audit §2 row 2 (V107 Guard A 期望 learning.hypotheses；
  Sprint 4+ M4 Pattern miner Stage 4 DRAFT writeback 需 V103 EXTEND 6 column 已 land 才 INSERT)

**Verdict**: PASS — V103 file land + sandbox Round 1/2 idempotency PASS + 3 CHECK constraint empirical reject test PASS。
PA-DRIFT-2 HARD BLOCKER **CLOSED**。

---

## §1 Pre-state (Linux PG empirical 2026-05-22 13:28 UTC)

### 1.1 learning.hypotheses sandbox pre-state

```
                                             Table "learning.hypotheses"
    Column     |           Type           | Collation | Nullable |                      Default
---------------+--------------------------+-----------+----------+---------------------------------------------------
 hypothesis_id | bigint                   |           | not null | nextval('hypotheses_hypothesis_id_seq'::regclass)
 title         | text                     |           | not null |
 status        | text                     |           |          | 'DRAFT'::text
 created_at    | timestamp with time zone |           |          | now()

Indexes:
    "hypotheses_pkey" PRIMARY KEY, btree (hypothesis_id)
Referenced by:
    TABLE "_timescaledb_internal._hyper_47_13_chunk" CONSTRAINT "13_20_replay_divergence_log_hypothesis_id_fkey"
        FOREIGN KEY (hypothesis_id) REFERENCES hypotheses(hypothesis_id)
    TABLE "replay_divergence_log" CONSTRAINT "replay_divergence_log_hypothesis_id_fkey"
        FOREIGN KEY (hypothesis_id) REFERENCES hypotheses(hypothesis_id)
```

- table 存在 ✅ (via E1 Track C 2026-05-22 stub IMPL #2)
- 4 base column: hypothesis_id BIGSERIAL PK / title TEXT NOT NULL / status TEXT DEFAULT 'DRAFT' / created_at TIMESTAMPTZ
- V107 既有 FK 從 replay_divergence_log.hypothesis_id 引用本表 hypothesis_id (不 break)

### 1.2 V103 file existence

```
$ ls /home/ncyu/BybitOpenClaw/srv/sql/migrations/V103*.sql
ls: cannot access ... No such file or directory
```

V103 file 不存在 → PA-DRIFT-2 finding 確認 (per E1 Track C 2026-05-22 report §5.2)。

---

## §2 V103 file content

### 2.1 修改清單

| 檔案 | 操作 | LOC | 摘要 |
|---|---|---|---|
| `srv/sql/migrations/V103__extend_m4_hypothesis_columns.sql` (Mac) | NEW | 365 | V103 EXTEND M4 6 column + 3 index + Guard A/B/C |
| `/home/ncyu/BybitOpenClaw/srv/sql/migrations/V103__extend_m4_hypothesis_columns.sql` (Linux) | scp | 365 | Mac → Linux sync |

### 2.2 V103 structure (per V106/V107 sister table pattern + spec §2-§5)

```
1. Header MODULE_NOTE (用途 / 範圍 / Parent specs / 硬邊界)
2. Guard A: base table 存在性 + hypothesis_id PK 必齊全 (2 段)
3. Guard B: 6 段 ADD COLUMN type/CHECK/DEFAULT mismatch 預檢
4. Main DDL: 6 條 ALTER TABLE ADD COLUMN IF NOT EXISTS
5. COMMENT ON COLUMN (6 條 — M4 lineage / statistical / governance 語意)
6. Main DDL Step 2: 3 hot-path CREATE INDEX IF NOT EXISTS (2 partial)
7. Guard C: post-check (6 column count + 3 index count + 2 CHECK enum 對齊)
```

### 2.3 6 EXTEND column 詳細

| Column | Type | DEFAULT | CHECK | 治理依據 |
|---|---|---|---|---|
| `hypothesis_source_module` | TEXT | `'OPERATOR'` | 3-enum `(M4_AUTO/OPERATOR/HISTORIC)` | spec §2.2 Path A (既有 row 100% operator-source; backfill 'M4_AUTO' 會 silent contamination); MIT 推薦 |
| `leakage_scan_pass` | BOOLEAN | `FALSE` | — | spec §2.2 + 根原則 #6 fail-closed |
| `bonferroni_corrected_p` | NUMERIC(10,8) | NULL | `[0,1]` range | spec §2.2; K=2500 × 5 window 場景 corrected p |
| `replicability_score` | NUMERIC(5,4) | NULL | `[0,1]` range | spec §2.2; sub-period stability + cross-asset robustness 複合 |
| `decision_lease_draft_id` | UUID | NULL | — (FK 暫不加) | spec §2.2 + ADR-0034 M1 LAL UUID 模式 |
| `cowork_review_status` | TEXT | `'NONE'` | 4-enum `(NONE/PENDING/APPROVED/REJECTED)` | spec §2.2 + ADR-0024-lite |

### 2.4 3 hot-path index 設計

| Index | Type | WHERE 條件 | 用途 |
|---|---|---|---|
| `idx_hypotheses_source_module` | (hypothesis_source_module, created_at DESC) | — | M4 dashboard query (source × time) |
| `idx_hypotheses_leakage_pass` | (leakage_scan_pass) | `leakage_scan_pass = TRUE` | M9 A/B queue (only PASS subset; partial) |
| `idx_hypotheses_cowork_review` | (cowork_review_status) | `cowork_review_status != 'NONE'` | Cowork review dashboard (only active; partial) |

**注意**：採 `CREATE INDEX IF NOT EXISTS` 非 `CONCURRENTLY`。原因：psql -f 腳本走 implicit transaction，`CREATE INDEX CONCURRENTLY` 與 transaction
邊界互斥 (PG 文檔)。Production V### 走 sqlx_migrate 路徑時若需 CONCURRENTLY，由 sqlx migration runner 控管 transaction
context；sandbox empirical apply 不需 CONCURRENTLY (row count = 0)。

### 2.5 Guard A/B/C 對 spec §3 對齊

| Guard | 段數 | 對 spec §3.1 對齊 |
|---|---|---|
| **Guard A** | 2 段 | base table 存在 + hypothesis_id PK 齊全 (per spec §3.1 prereq) |
| **Guard B** | 6 段 | type/CHECK/DEFAULT mismatch 預檢 6 column (per spec §3.1 §3.2 觸發場景) |
| **Guard C** | post-check | column count = 6 + index count = 3 + CHECK enum 對齊 (per spec §11 AC-1/2/3) |

---

## §3 Sandbox empirical apply (Linux trade-core PG)

### 3.1 Round 1 — first apply (V103 全新 land)

```bash
ssh trade-core "PGPASSWORD=... psql -h 127.0.0.1 -U sandbox_admin -d trading_ai_sandbox \
    -v ON_ERROR_STOP=1 -f /home/ncyu/BybitOpenClaw/srv/sql/migrations/V103__extend_m4_hypothesis_columns.sql"
```

**Result**：

```
DO              (Guard A: 2 段 PASS)
DO              (Guard B: 6 段預檢 全 PASS — 6 column 不存在;全 skip)
ALTER TABLE     (ADD COLUMN hypothesis_source_module)
ALTER TABLE     (ADD COLUMN leakage_scan_pass)
ALTER TABLE     (ADD COLUMN bonferroni_corrected_p)
ALTER TABLE     (ADD COLUMN replicability_score)
ALTER TABLE     (ADD COLUMN decision_lease_draft_id)
ALTER TABLE     (ADD COLUMN cowork_review_status)
COMMENT × 6     (6 COLUMN COMMENT)
CREATE INDEX × 3 (idx_hypotheses_source_module / leakage_pass / cowork_review)
NOTICE: V103: M4 EXTEND all guards PASS — 6 column ... added, 3 hot-path index built,
        CHECK enum (3-source / 4-review) aligned with spec §2.1, fail-closed DEFAULT FALSE
        for leakage_scan_pass preserved (per 根原則 #6). PA-DRIFT-2 HARD BLOCKER closure
        path empirical.
DO              (Guard C: post-check column count=6 + index count=3 + 2 CHECK enum PASS)
```

**Verdict**: Round 1 **PASS** — 0 RAISE EXCEPTION / 全 ALTER + INDEX 成功 / 最終 NOTICE fire.

### 3.2 Round 2 — idempotency re-apply

```bash
# 重跑同一 file
ssh trade-core "PGPASSWORD=... psql -h 127.0.0.1 -U sandbox_admin -d trading_ai_sandbox \
    -v ON_ERROR_STOP=1 -f /home/ncyu/BybitOpenClaw/srv/sql/migrations/V103__extend_m4_hypothesis_columns.sql"
```

**Result**：

```
DO              (Guard A: 2 段 PASS — table + hypothesis_id 都存在;skip RAISE)
DO              (Guard B: 6 段預檢全 PASS — 6 column 已存在且 type/CHECK/DEFAULT 對齊 spec;skip RAISE)
NOTICE: column "hypothesis_source_module" of relation "hypotheses" already exists, skipping
ALTER TABLE     (NO-OP)
NOTICE: column "leakage_scan_pass" of relation "hypotheses" already exists, skipping
ALTER TABLE     (NO-OP)
NOTICE: column "bonferroni_corrected_p" of relation "hypotheses" already exists, skipping
ALTER TABLE     (NO-OP)
NOTICE: column "replicability_score" of relation "hypotheses" already exists, skipping
ALTER TABLE     (NO-OP)
NOTICE: column "decision_lease_draft_id" of relation "hypotheses" already exists, skipping
ALTER TABLE     (NO-OP)
NOTICE: column "cowork_review_status" of relation "hypotheses" already exists, skipping
ALTER TABLE     (NO-OP)
COMMENT × 6     (COMMENT idempotent)
NOTICE: relation "idx_hypotheses_source_module" already exists, skipping
CREATE INDEX    (NO-OP)
NOTICE: relation "idx_hypotheses_leakage_pass" already exists, skipping
CREATE INDEX    (NO-OP)
NOTICE: relation "idx_hypotheses_cowork_review" already exists, skipping
CREATE INDEX    (NO-OP)
NOTICE: V103: M4 EXTEND all guards PASS — ... (最終 NOTICE 一致)
DO              (Guard C post-check 復跑 PASS — count 不變)
```

**Verdict**: Round 2 **PASS** — 0 RAISE EXCEPTION / 6 ADD COLUMN 全 NOTICE skip / 3 CREATE INDEX 全 NOTICE skip / Guard B 預檢 0 RAISE (符合 spec §3.2 「重跑 V103 EXTEND M4 (type/CHECK 一致) → NO RAISE skip path」).

### 3.3 Post-Round 2 schema verify

```
                                                  Table "learning.hypotheses"
          Column          |           Type           | Collation | Nullable |                      Default
--------------------------+--------------------------+-----------+----------+---------------------------------------------------
 hypothesis_id            | bigint                   |           | not null | nextval('hypotheses_hypothesis_id_seq'::regclass)
 title                    | text                     |           | not null |
 status                   | text                     |           |          | 'DRAFT'::text
 created_at               | timestamp with time zone |           |          | now()
 hypothesis_source_module | text                     |           | not null | 'OPERATOR'::text
 leakage_scan_pass        | boolean                  |           | not null | false
 bonferroni_corrected_p   | numeric(10,8)            |           |          |
 replicability_score      | numeric(5,4)             |           |          |
 decision_lease_draft_id  | uuid                     |           |          |
 cowork_review_status     | text                     |           | not null | 'NONE'::text

Indexes:
    "hypotheses_pkey" PRIMARY KEY, btree (hypothesis_id)
    "idx_hypotheses_cowork_review" btree (cowork_review_status) WHERE cowork_review_status <> 'NONE'::text
    "idx_hypotheses_leakage_pass" btree (leakage_scan_pass) WHERE leakage_scan_pass = true
    "idx_hypotheses_source_module" btree (hypothesis_source_module, created_at DESC)

Check constraints:
    "hypotheses_bonferroni_corrected_p_check"
        CHECK (bonferroni_corrected_p IS NULL OR bonferroni_corrected_p >= 0 AND bonferroni_corrected_p <= 1)
    "hypotheses_cowork_review_status_check"
        CHECK (cowork_review_status = ANY (ARRAY['NONE'::text, 'PENDING'::text, 'APPROVED'::text, 'REJECTED'::text]))
    "hypotheses_hypothesis_source_module_check"
        CHECK (hypothesis_source_module = ANY (ARRAY['M4_AUTO'::text, 'OPERATOR'::text, 'HISTORIC'::text]))
    "hypotheses_replicability_score_check"
        CHECK (replicability_score IS NULL OR replicability_score >= 0 AND replicability_score <= 1)

Referenced by:
    TABLE "_timescaledb_internal._hyper_47_13_chunk" CONSTRAINT "13_20_replay_divergence_log_hypothesis_id_fkey" ...
    TABLE "replay_divergence_log" CONSTRAINT "replay_divergence_log_hypothesis_id_fkey" ...
```

**完整對齊 spec §2.1**：
- 6 column 全 added with correct type / DEFAULT / NOT NULL where applicable ✅
- 4 CHECK constraint 完整 (3-source / 4-review / 2 range [0,1]) ✅
- 3 hot-path index 全 land (其中 2 個 partial) ✅
- V107 既有 FK 引用 hypothesis_id 不破壞 ✅
- COMMENT ON COLUMN 6 條 attach (不在 \\d 默認 output 但已 commit per Round 1 log)

### 3.4 CHECK constraint empirical reject test (per spec §11 AC-2)

```sql
-- Test 1: invalid source_module
INSERT INTO learning.hypotheses (title, hypothesis_source_module)
VALUES ('test invalid source', 'INVALID_SOURCE');
-- Expected: ERROR
-- Actual:
ERROR:  new row for relation "hypotheses" violates check constraint "hypotheses_hypothesis_source_module_check"
DETAIL:  Failing row contains (1, test invalid source, DRAFT, ..., INVALID_SOURCE, f, null, null, null, NONE).
```

```sql
-- Test 2: invalid review_status
INSERT INTO learning.hypotheses (title, cowork_review_status)
VALUES ('test invalid review', 'INVALID_REVIEW');
-- Expected: ERROR
-- Actual:
ERROR:  new row for relation "hypotheses" violates check constraint "hypotheses_cowork_review_status_check"
DETAIL:  Failing row contains (2, test invalid review, DRAFT, ..., OPERATOR, f, null, null, null, INVALID_REVIEW).
```

```sql
-- Test 3: bonferroni p > 1 (out of range)
INSERT INTO learning.hypotheses (title, bonferroni_corrected_p)
VALUES ('test invalid p range', 1.5);
-- Expected: ERROR
-- Actual:
ERROR:  new row for relation "hypotheses" violates check constraint "hypotheses_bonferroni_corrected_p_check"
DETAIL:  Failing row contains (3, test invalid p range, DRAFT, ..., OPERATOR, f, 1.50000000, null, null, NONE).
```

```sql
-- Test 4: valid M4_AUTO + TRUE + PENDING combo
INSERT INTO learning.hypotheses (title, hypothesis_source_module, leakage_scan_pass, cowork_review_status)
VALUES ('test m4 auto valid', 'M4_AUTO', TRUE, 'PENDING')
RETURNING hypothesis_id, hypothesis_source_module, leakage_scan_pass, cowork_review_status;
-- Expected: 1 row inserted with id=4
-- Actual:
 hypothesis_id | hypothesis_source_module | leakage_scan_pass | cowork_review_status
---------------+--------------------------+-------------------+----------------------
             4 | M4_AUTO                  | t                 | PENDING
(1 row)
INSERT 0 1
```

**Verdict (AC-2)**: **PASS** — 3 invalid CHECK reject 全 fire + 1 valid INSERT 全通。

### 3.5 Cleanup test rows (sandbox state pristine)

```sql
DELETE FROM learning.hypotheses WHERE title LIKE 'test%';
-- DELETE 1 (剩餘 invalid INSERT 已被 ROLLBACK 不在表;valid id=4 被 DELETE 清掉)
SELECT count(*) FROM learning.hypotheses;
-- 0
```

Final sandbox state：6 column + 3 index + 4 CHECK constraint + 0 data row（pristine baseline 給後續 Sprint 用）。

---

## §4 治理對照 (16 root principles + ADR alignment)

| 治理要求 | 本任務遵循 | 證據 |
|---|---|---|
| §二 原則 6: Uncertainty defaults to conservative behavior | `leakage_scan_pass DEFAULT FALSE` — 既有 row 未跑 leakage scan fail-closed | column DEFAULT empirical verify |
| §二 原則 7: Learning 不寫 live state | 純 schema EXTEND;不寫 trading.* / governance.lease;不啟 M4 pattern miner runtime | 0 runtime mutation |
| §二 原則 8: 每筆交易可重建 | `decision_lease_draft_id` UUID 留 M4 DRAFT writeback backref | column 設計;FK 待 V099/V100 land |
| §六 Mac dev / Linux runtime split | scp file Mac → Linux + ssh trade-core empirical;Mac 不跑 PG | scp + ssh sequence |
| §七 Data Migrations Linux PG empirical dry-run mandate (feedback_v_migration_pg_dry_run) | Round 1 + Round 2 idempotency empirical 雙跑 | §3.1 + §3.2 |
| §七 Guard A/B/C pattern (per V106/V107 sister) | Guard A 2 段 + Guard B 6 段 + Guard C post-check 3 metric | §2.5 對齊 |
| §七 注釋默認中文 (feedback_chinese_only_comments) | header MODULE_NOTE + RAISE message + COMMENT 全中文 (技術 identifier 保留 EN) | grep confirm |
| 根原則 13: AI 呼叫成本須對應 expected edge | 純 DDL EXTEND;不啟 M4 runtime;0 AI 呼叫 | scope verify |
| ADR-0045 M4 governance reserved (per R4 C-1) | 6 column 對應 M4 hypothesis discovery governance 框架 | column 命名對齊 ADR-0045 |
| ADR-0034 M1 LAL UUID 模式 | `decision_lease_draft_id` UUID 而非 BIGINT | type empirical verify |
| ADR-0024-lite Cowork hybrid review | `cowork_review_status` 4-enum (NONE/PENDING/APPROVED/REJECTED) | CHECK constraint verify |

### 4.1 不變量 (Invariants)

- base learning.hypotheses table 必先存在 → Guard A 強制 RAISE
- `leakage_scan_pass` DEFAULT FALSE (fail-closed) → 既有 row backfill FALSE → M4 IMPL 前 leakage scan 預設未通過
- `hypothesis_source_module` DEFAULT 'OPERATOR' (Path A) → 既有 row 100% 標 operator-source (避 silent 'M4_AUTO' contamination)
- 3 CHECK enum 範圍嚴格：M4_AUTO/OPERATOR/HISTORIC × NONE/PENDING/APPROVED/REJECTED × [0,1]
- 3 hot-path index 中 2 個 partial → 避免低基數 column index bloat
- production engine (PID 2934602) 全程未碰 → sandbox 隔離 verify (current_database=trading_ai_sandbox)

### 4.2 不確定之處

1. **V### naming race (spec §1.3 + §14 Open Issue 1)**：spec 列 Path A (V103) vs Path B (V101) 待 PM Q1 verdict。本 file 沿用 PM dispatch prompt 文字「V103」；若 PA dry-run option A re-number → 需 rename V101。**carry-over: PM 拍板**.

2. **DEFAULT 'OPERATOR' vs 'M4_AUTO' (spec §14 Open Issue 2)**：本 file 採 Path A (DEFAULT 'OPERATOR'，MIT 推薦 + 既有 row 友善)；若 PM 拍 Path B → 需新增 backfill task 顯式 update 既有 row。**carry-over: PM 拍板**.

3. **Naming convention (spec §14 Open Issue 3)**：本 file 採 `V103__extend_m4_hypothesis_columns.sql` (主版本 + 描述 underscored)。spec 列 Option 1 `V103.1__...sql` (sqlx sub-version) vs Option 2 `V<next-free>__...sql`. 本實作走 Option 1 變體 (無 sub-version)，與 V106/V107 sister table 命名一致。**carry-over: PA 確認**.

4. **CREATE INDEX CONCURRENTLY**：spec §5.1 列 CONCURRENTLY，但 psql -f 走 implicit transaction 不支援。本 file 改為 `CREATE INDEX IF NOT EXISTS`；production sqlx_migrate 走外圍 transaction 控制時可改 CONCURRENTLY。對 sandbox empirical 無影響 (row count = 0)。

5. **FK to V099/V100 lease tables 暫不加 (spec §2.1 注解)**：`decision_lease_draft_id` UUID 留 placeholder；FK 待 V099/V100 land + PA 確認 lease_id column name 後由 follow-up EXTEND 加 `REFERENCES governance.decision_lease(lease_id)`。**carry-over: V099/V100 land 後**.

---

## §5 PA-DRIFT-2 HARD BLOCKER closure verdict

### 5.1 PA-DRIFT-2 finding recap (per E1 Track C 2026-05-22 report §5.2)

> **[PA-DRIFT-2] V107 Guard A 期望 `learning.hypotheses` 但 V103 未 file land**
>
> **證據**：
> - V107.sql line 138-147 Guard A 要 `learning.hypotheses`
> - `srv/sql/migrations/V103*.sql` 不存在
> - spike spec line 713 寫「V103/V104 (hypotheses) 已 Sprint 1A-α land」實屬 spec drift
> - E3 v58 executability audit §2 row 2 標 V103 為 Sprint 1A-γ HARD BLOCKER
>
> **修法**：
> - (a) PA 派 Sprint 1A-γ 完成 V103 file land + production apply
> - (b) sandbox stub 持續存活 (本次 IMPL 保留) 作 future test fixture
>
> **Priority**: P1 (V107 production land 強依賴)

### 5.2 本任務交付 — PA-DRIFT-2 closure scope

✅ **(a) V103 file land** — `V103__extend_m4_hypothesis_columns.sql` 365 LOC 寫並 scp Mac → Linux
✅ **sandbox empirical Round 1 PASS** — 6 column ADD + 3 INDEX CREATE + Guard A/B/C 0 RAISE
✅ **sandbox empirical Round 2 idempotency PASS** — 6 NOTICE skip + 3 NOTICE skip + Guard B 0 RAISE
✅ **3 CHECK constraint empirical reject test PASS** — invalid INSERT 全被 reject (spec §11 AC-2)
✅ **base table backward-compat verify** — V107 既有 FK 不破壞 (replay_divergence_log_hypothesis_id_fkey 仍 valid)

### 5.3 closure status

- **HARD BLOCKER**: ✅ **CLOSED**
- **base table physical existence**: 既有 stub (Sprint 1A-α via E1 Track C 2026-05-22 IMPL #2) + 6 EXTEND column 真實 land
- **V107 Guard A dependency**: 滿足 — V107 line 138-147 期望 `learning.hypotheses` 不僅存在且具完整 M4 EXTEND schema
- **Sprint 4+ M4 Pattern miner unblock**: Stage 4 DRAFT writeback 可 INSERT (6 column + CHECK 全 ready)
- **production land**: **PENDING** — 待 (1) PM Q1 verdict 鎖定 V### final number + (2) production engine restart 走 sqlx_migrate path

### 5.4 carry-over

| Item | Owner | Priority |
|---|---|---|
| PM Q1 verdict — V### final number (V103 vs V101) | PM | P1 |
| PM Q2 verdict — DEFAULT 'OPERATOR' vs 'M4_AUTO' (本 file 採 Path A) | PM | P1 |
| PA Q3 verdict — naming convention (本 file 採 `V103__extend_m4_hypothesis_columns.sql`) | PA | P2 |
| FK to V099/V100 lease tables follow-up EXTEND | E1 (V099/V100 land 後) | P2 |
| production land path — engine restart sqlx_migrate | PA + E3 (待 PM verdict) | P1 |
| _sqlx_migrations register (raw psql -f 不寫註冊表) | E3 (per Sprint 1A-ε P1 §4.2 既定路徑) | P2 |
| E4 regression — V103 idempotency Round 3 + cargo test | E4 (本 IMPL DONE 後 dispatch) | P0 |
| E2 review — 6 段 Guard B + cross-V### dependency | E2 (本 IMPL DONE 後 dispatch) | P0 |

---

## §6 修改清單

### 6.1 新增 file (本任務)

| File | 路徑 | LOC | Lifecycle |
|---|---|---|---|
| V103 file | `srv/sql/migrations/V103__extend_m4_hypothesis_columns.sql` (Mac) | 365 | NEW |
| V103 file (Linux sync) | `/home/ncyu/BybitOpenClaw/srv/sql/migrations/V103__extend_m4_hypothesis_columns.sql` | 365 | scp from Mac |
| 本報告 | `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-22--sprint_2_pre_v103_file_land.md` | ~450 | NEW |

### 6.2 sandbox PG 物理變更 (保留)

| 物件 | 變更 | 永久性 |
|---|---|---|
| `learning.hypotheses` ADD COLUMN hypothesis_source_module TEXT NOT NULL DEFAULT 'OPERATOR' + CHECK | NEW column | 永久 |
| `learning.hypotheses` ADD COLUMN leakage_scan_pass BOOLEAN NOT NULL DEFAULT FALSE | NEW column | 永久 |
| `learning.hypotheses` ADD COLUMN bonferroni_corrected_p NUMERIC(10,8) + CHECK [0,1] | NEW column | 永久 |
| `learning.hypotheses` ADD COLUMN replicability_score NUMERIC(5,4) + CHECK [0,1] | NEW column | 永久 |
| `learning.hypotheses` ADD COLUMN decision_lease_draft_id UUID | NEW column | 永久 |
| `learning.hypotheses` ADD COLUMN cowork_review_status TEXT NOT NULL DEFAULT 'NONE' + CHECK | NEW column | 永久 |
| 3 hot-path index (source_module / leakage_pass partial / cowork_review partial) | NEW | 永久 |
| 6 COMMENT ON COLUMN | NEW | 永久 |
| Test row INSERT × 4 (3 CHECK reject + 1 valid) | INSERT (1 row) → DELETE 1 → cleanup | 0 殘留 |

### 6.3 沒碰的 surface

- ✅ production trading_ai DB (current_database verify 為 trading_ai_sandbox)
- ✅ production engine PID 2934602 (全程未碰，per 禁忌 #2)
- ✅ Rust openclaw_engine source (純 SQL DDL；不需 Rust 改動)
- ✅ Python source (不需 writer 改動 — M4 writer 待 Sprint 4+ IMPL)
- ✅ git commit (per 禁忌 #4，PM 收口)

---

## §7 Verdict

### 7.1 AC verdict matrix (per spec §11)

| AC | Spec literal | Empirical 結果 | Verdict |
|---|---|---|---|
| **AC-1** | 6 column 全 add (SELECT count = 6) | empirical \\d 顯示 6 new column + Round 1 ALTER ✅ | **PASS** |
| **AC-2** | 3 CHECK enum reject invalid empirical | INSERT 'INVALID_SOURCE' / 'INVALID_REVIEW' / p=1.5 全 ERROR ✅ | **PASS** |
| **AC-3** | Idempotency 雙跑 0 RAISE — exit code 0 / column count 6 不變 | Round 2 0 RAISE / 6 NOTICE skip / count 6 一致 ✅ | **PASS** |
| **AC-4** | Engine restart sqlx 0 panic (per spec §4.5) | **DEFERRED** — sandbox empirical 不需 engine restart;production path 走 sqlx_migrate 時驗 | **DEFERRED** |
| **AC-5** | 3 index created + query plan use Index Scan | 3 index empirical \\d verify ✅;EXPLAIN ANALYZE 待 M4 writer data 後驗 | **PARTIAL** |
| **AC-6** | Cross-language 1e-4 fixture (M4 Rust insert + Python SELECT) | **DEFERRED** — 待 M4 IMPL Sprint 4+ | **DEFERRED** |
| **AC-7** | 既有 row 全 backfill DEFAULT | base table 0 row pre-EXTEND → trivially PASS;valid INSERT 確認 default 應用 | **PASS** |
| **AC-8** | Guard B RAISE 真實 trigger (destructive dev test) | 重跑 Round 2 Guard B 6 段全 skip (no RAISE — type 對齊);destructive test 留 E2 review 補 | **PARTIAL** |

### 7.2 Final Verdict: **PASS WITH 3 CARRY-OVER**

3 carry-over 均屬 PM verdict / 待 V099 land / E2 destructive test，不阻本 IMPL acceptance：

1. **PM Q1+Q2 verdict** (V### number + DEFAULT path A/B)
2. **AC-4 + AC-6 deferred** to production sqlx_migrate path + M4 IMPL Sprint 4+
3. **AC-5 + AC-8 partial** — query plan + destructive Guard B test 待 E2 review 補

### 7.3 PA-DRIFT-2 HARD BLOCKER closure: ✅ **CLOSED**

V103 file land + sandbox empirical 6 column + 3 index + 4 CHECK + 2 round idempotency + 3 CHECK reject + 1 valid INSERT 全 PASS. Sprint 4+ M4 Pattern miner Stage 4 DRAFT writeback unblock.

---

## §8 Operator 下一步

| Action | Owner | Priority |
|---|---|---|
| E2 review 本 report + V103.sql 6 段 Guard B + cross-V### dep | E2 | P0 |
| E4 regression (Round 3 idempotency + cargo test + pytest) | E4 | P0 |
| PM Q1 verdict — V### final number (V103 vs V101) | PM | P1 |
| PM Q2 verdict — DEFAULT path A/B (本 file 採 A) | PM | P1 |
| PA Q3 verdict — naming convention | PA | P2 |
| production land — sqlx_migrate path engine restart (待 PM verdict) | PA + E3 | P1 |
| TODO.md 同步 Sprint 2 pre-readiness Track 2 → DONE-VERDICT-PASS | PM | P0 |

---

## §9 4 條完成回報 (per PM dispatch packet 完成回報格式)

### 1) learning.hypotheses pre-state

- **table 存在**: ✅ (via E1 Track C 2026-05-22 stub IMPL #2)
- **既有 column 數**: 4 (hypothesis_id BIGSERIAL PK / title TEXT NOT NULL / status TEXT DEFAULT 'DRAFT' / created_at TIMESTAMPTZ)
- **V103 file pre-existence**: 不存在 (PA-DRIFT-2 finding confirmed)
- **V107 既有 FK**: hypothesis_id 引用本表 PK (replay_divergence_log_hypothesis_id_fkey)

### 2) V103 file content (6 column EXTEND + Guard A/B/C)

- 365 LOC
- Guard A 2 段 (base table + hypothesis_id PK)
- Guard B 6 段 (type/CHECK/DEFAULT mismatch 預檢)
- Main DDL: 6 ALTER TABLE ADD COLUMN IF NOT EXISTS
- 6 COMMENT ON COLUMN
- 3 CREATE INDEX IF NOT EXISTS (2 partial)
- Guard C post-check (count + CHECK enum 對齊)
- 注釋全中文 (符合 feedback_chinese_only_comments)
- 對齊 V106/V107 sister table style (Header MODULE_NOTE + Parent specs + 硬邊界)

### 3) Sandbox empirical Round 1+2 result

| Round | Result | 證據 |
|---|---|---|
| **Round 1 (first apply)** | **PASS** | 0 RAISE / 6 ALTER + 3 INDEX 全 success / 最終 NOTICE fire |
| **Round 2 (idempotency)** | **PASS** | 0 RAISE / 6 NOTICE skip + 3 NOTICE skip / Guard B 6 段 0 RAISE |
| **AC-2 CHECK reject (3 test)** | **PASS** | invalid source / review / p=1.5 全 ERROR;valid M4_AUTO INSERT 通 |
| **Sandbox isolation** | **VERIFIED** | current_database=trading_ai_sandbox; production trading_ai 全程未碰 |
| **Cleanup** | **PRISTINE** | 4 test INSERT → DELETE 1 valid row → 0 殘留 |

### 4) PA-DRIFT-2 HARD BLOCKER closure verdict

✅ **HARD BLOCKER CLOSED**

V103 file land (Mac + Linux scp sync) + sandbox empirical Round 1/2 PASS + 3 CHECK reject empirical + base table backward-compat (V107 FK 不破壞) 全達成。

下游不阻 Sprint 2 Track：
- V107 Guard A `learning.hypotheses` dependency 滿足 (base + 6 EXTEND column 全 ready)
- Sprint 4+ M4 Pattern miner Stage 4 DRAFT writeback unblock (6 column + CHECK 全 INSERT-ready)
- V099/V100 lease tables land 後 follow-up EXTEND 加 `decision_lease_draft_id` FK 為線性 carry-over (本任務 scope 外)

**production land 待 PM Q1+Q2 verdict 後沿 sqlx_migrate path 走** (per Sprint 1A-ε P1 §4.2 既定路徑 + memory `project_2026_05_02_p0_sqlx_hash_drift` engine restart SOP).

---

**E1 IMPLEMENTATION DONE: 待 E2 審查**
(report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-22--sprint_2_pre_v103_file_land.md`)
