---
spec: V108 — M9 A/B Testing Framework Schema (FULL DDL)
date: 2026-05-21
author: MIT (Sprint 1A-γ CRITICAL DESIGN; placeholder → full DDL upgrade)
phase: v5.8 Sprint 1A-γ ADD-per-operator schema prerequisite
status: SPEC-DRAFT-V1（full DDL；對齊 ADR-0037 5 Decisions + sibling M9 DESIGN spec；待 PA C9 Linux PG dry-run + PM sign-off → SPEC-FINAL）
parent specs:
  - srv/docs/adr/0037-m9-ab-framework-and-statistical-methodology.md (ADR 權威 5 Decisions；本 spec 100% 對齊)
  - srv/docs/execution_plan/2026-05-21--m9_ab_framework_design_spec.md (sibling M9 DESIGN spec；本 V108 full DDL 為其 schema land)
  - srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md §2 M9 (line 319-355) + §9 V108 schema (line 789-791)
  - srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md §Sprint 1A-γ + §HIGH H-17 (M9-FRAMEWORK-VALIDATION harness)
mirror precedent:
  - srv/docs/execution_plan/2026-05-21--v103_v104_earn_hypotheses_schema_spec.md (Guard A/B/C + Linux PG dry-run protocol format)
  - srv/docs/execution_plan/2026-05-21--v110_m6_reward_weight_history_schema_spec.md (full DDL upgrade 結構範式)
  - srv/sql/migrations/V094__fills_close_maker_audit.sql (Guard A/B/C + partial index 範式)
  - srv/sql/migrations/V083__fills_entry_context_id_close_check.sql (ALTER ADD COLUMN + NOT VALID CHECK 範式)
scope: schema DDL design only — 不寫 V108.sql 實檔，不在 Mac 跑 SQL，不改 Rust/Python writer，不執行 PG，不寫業務 code
---
> ⚠️ 归档历史文档 — 非当前权威。active 状态见 repo 根 `TODO.md`；本文件仅供历史/审计参考。（2026-07-18 审计批量补入）


# V108 M9 A/B Testing Framework Schema Migration Spec (FULL DDL)

## §0 TL;DR

- **V108 新增 3 個 regular table**：
  - `learning.ab_tests`（A/B test definition + preregistration FK + statistical method config）
  - `learning.ab_assignments`（per-decision variant assignment ledger + lease_id 綁定）
  - `learning.ab_results`（mSPRT sequential evaluation outcome + M11 replay cross-ref）
- **核心 ENUM**：
  - `cluster_type` 4 值（per ADR-0037 Decision 3）：`parameter_sweep` / `signal_source_swap` / `risk_profile` / `exit_logic`
  - `statistical_method` 3 值（per ADR-0037 Decision 4）：`mSPRT_with_AVI` / `Bayesian_AB` / `fixed_horizon`
  - `assignment_method` 3 值（per sibling M9 DESIGN spec §7）：`deterministic_hash` / `stratified_random` / `sequential_balance`
  - `ab_test_status` 6 值：`preregistered` / `running` / `concluded_efficacy` / `concluded_futility` / `concluded_inconclusive` / `aborted`
  - `engine_mode` 5 值：`paper / demo / live_demo / live / replay`（增 replay 為 M11 continuous replay 用，對齊 V110）
- **FK chain**：
  - V108 `ab_tests.hypothesis_id NOT NULL` → V103 `learning.hypotheses(hypothesis_id)` （preregistration mandate，per ADR-0026 v3 + sibling M9 DESIGN §6.2）
  - V108 `ab_assignments.test_id NOT NULL` → V108 `learning.ab_tests(test_id)` ON DELETE CASCADE
  - V108 `ab_results.test_id NOT NULL` → V108 `learning.ab_tests(test_id)` ON DELETE CASCADE
- **無 FK to V107 (M11 divergence)** **PATCHED 2026-05-22 per MIT 紅線 3**：V107 final type 經 empirical verify = `BIGINT bigserial`（`V107__replay_divergence_log.sql:81-87` PK）；本 spec `m11_replay_divergence_ref` type 從 UUID 更正為 **BIGINT NULL**；FK 仍 deferred 到 M11 land（per V107/V108 cross-V### dependency）；應用層 join validation 不變
- **無 FK to V110 (M6 weight) / V113 (M7 decay) / V109 (M8 anomaly) / V111 (M10 discovery)**：cross-1A-β/γ decoupled，per CR-9 cross-V### dependency graph + sibling M9 DESIGN §12.1
- **Hypertable on ab_assignments.assigned_at + ab_results.evaluation_ts**：7d chunk / 30d compress / 180d retention（per operator prompt + 對齊 V107 hypertable 設計）
- **ab_tests 是 regular table**（低基數 ~hundreds row total per-test config）
- **Guard A/B/C 完整**：3 NEW table 走 CREATE TABLE IF NOT EXISTS + Guard A column 完整性驗 + Guard B 不適用（無 ALTER）+ Guard C CHECK constraint + ENUM 值齊全 + index 對齊驗證
- **engine_mode CHECK 5 值齊全**（含 replay）；A/B test 限 demo + live_demo + live + replay 跑（paper 失真不採；CHECK 進一步限 `engine_mode IN ('demo','live_demo','live','replay')`）
- **Linux PG empirical dry-run mandatory**（per CLAUDE.md §Data, Migrations, And Validation + feedback_v_migration_pg_dry_run.md）— 本 spec §4 列出 PA C9 待補的 4 條 SQL；spec sign-off 前必補
- **Materialized view (optional)**：`mv_latest_winner_per_test`（最新 winner per test）；per operator prompt + V110 §2.6 範式
- **Sprint 1A-γ land schedule**：V108 屬中位 priority（DESIGN initial；Sprint 4 read-only logging IMPL）；先於 V109 (M8) + V111 (M10) 但同 Sprint 1A-γ 並行

---

## §1 Background + Scope

### 1.1 動機

v5.8 §9 schema roster line 791「V108: ab_tests + ab_assignments + ab_results」全 placeholder（per MIT 2026-05-21 v5.8 audit Risk 1，9 V### CRITICAL 級全空）。MIT 2026-05-21 v58 dispatch consolidation 派發 packet 行 153 列 Sprint 1A-γ deliverable 含「M9 A/B framework schema + ADR-0037 + V108 spec doc」三件耦合。

本 spec 對 placeholder doc（`2026-05-21--v108_m9_ab_testing_framework_schema_spec.md` placeholder 版 215 行）升級為 full DDL（~1100 行），land Sprint 1A-γ E1 IMPL 之前的 hard precondition。

### 1.2 ADR-0037 5 Decisions 對齊

| ADR-0037 Decision | 本 spec 對齊章節 |
|---|---|
| Decision 1 V108 三表 schema 草案 | §2 全（三表 full DDL） |
| Decision 2 Variant Stage 路徑 | §2.1 `lal_level` smallint + `cluster_type` ENUM 對齊 cluster-Stage 紀律 |
| Decision 3 4 Variant Cluster 規範 | §2.1 `cluster_type` ENUM CHECK 4 值 |
| Decision 4 Statistical Methodology | §2.1 `statistical_method` ENUM CHECK 3 值 + `bonferroni_correction_n` column + `min_sample_size_per_arm` column |
| Decision 5 Fair Execution Clause | §2.2 `ab_assignments.lease_id` NOT NULL + 對齊 ADR-0008 Decision Lease |
| Decision 6 Sprint 4 First Live A/B Gate | §6 IMPL Plan 對齊 + §7 Cross-V### dependency Sprint dispatch ordering |

### 1.3 Sibling M9 DESIGN spec 對齊

per `srv/docs/execution_plan/2026-05-21--m9_ab_framework_design_spec.md`（同日 land）：

| Sibling M9 DESIGN spec 章節 | 本 V108 spec 對齊 |
|---|---|
| §2 4 Variant Cluster 詳細規範 | §2.1 `cluster_type` ENUM CHECK 4 值 |
| §3 mSPRT + AVI + Bonferroni | §2.1 `statistical_method` ENUM + §2.3 `mSPRT_statistic` / `AVI_lower_ci` / `AVI_upper_ci` / `bonferroni_adjusted_p` column |
| §4 Variant Stage 路徑 | §2.1 `lal_level` smallint + §2.2 `ab_assignments.lease_id` 對齊 ADR-0008 |
| §5 Fair Execution Clause | §2.2 `lease_id` NOT NULL + `assignment_method` ENUM + UNIQUE (test_id, decision_id) |
| §6 Preregistration | §2.1 `hypothesis_id BIGINT NOT NULL REFERENCES V103 hypotheses(hypothesis_id)` |
| §7 Hash Algorithm | §2.1 `hash_seed BIGINT NOT NULL` + §2.2 `hash_value NUMERIC NOT NULL` + `stratification_keys JSONB` |
| §8 M11 Cross-ref | §2.3 `m11_replay_divergence_ref BIGINT` (not FK) + §8.3 caveat |
| §9 M9 ↔ M7 Integration | §2.1 `cluster_type` 對應 M7 decay treated equal as same-strategy |
| §10 AC 7 條 | §6.2 E2 Review 重點 + AC 對應 SQL empirical test |
| §11 IMPL phase | §6 IMPL Plan Sprint 1A-γ + Sprint 3 + Sprint 4 + Sprint 7-8 + Y2 對齊 |
| §12 Cross-V### + Open Q | §7 Cross-V### Dependencies + §10 Open Q / Caveat |

### 1.4 不在本 spec 範圍

- ❌ V108.sql 實檔寫作（E1 IMPL 工作；Sprint 1A-γ ~150-200 LOC SQL）
- ❌ Mac 跑 V108 SQL（必 Linux PG empirical）
- ❌ M9 IMPL Rust/Python code（Sprint 4 / 7-8 / Y2 三階段 IMPL；sibling M9 DESIGN spec §11）
- ❌ M9 framework validation harness IMPL（Sprint 3 + Sprint 4 早期；sibling M9 DESIGN §3.9 + AC-7）
- ❌ Auto-Allocator reward function 細節（Sprint 7+ IMPL；M6 sibling spec 範圍）
- ❌ healthcheck Python integration（E1 IMPL Sprint 4+ 工作）
- ❌ V107 (M11) / V110 (M6) / V113 (M7) 對應 schema（sibling V107/V110/V113 spec 範圍）

---

## §2 Schema Changes

### 2.1 `learning.ab_tests` — A/B Test Definition + Preregistration

#### 2.1.1 表定義

```sql
CREATE TABLE IF NOT EXISTS learning.ab_tests (
    test_id                         BIGSERIAL PRIMARY KEY,
    test_name                       TEXT NOT NULL UNIQUE,
    cluster_type                    TEXT NOT NULL
                                    CHECK (cluster_type IN (
                                        'parameter_sweep',
                                        'signal_source_swap',
                                        'risk_profile',
                                        'exit_logic'
                                    )),
    hypothesis_id                   BIGINT NOT NULL
                                    REFERENCES learning.hypotheses(hypothesis_id),
    strategy_name                   TEXT NOT NULL,
    control_config_hash             TEXT NOT NULL,
    variant_count                   INTEGER NOT NULL
                                    CHECK (variant_count BETWEEN 2 AND 10),
    statistical_method              TEXT NOT NULL
                                    CHECK (statistical_method IN (
                                        'mSPRT_with_AVI',
                                        'Bayesian_AB',
                                        'fixed_horizon'
                                    )),
    msprt_target_significance       NUMERIC(8,6) NOT NULL DEFAULT 0.05,
    msprt_target_power              NUMERIC(8,6) NOT NULL DEFAULT 0.8,
    min_sample_size_per_arm         INTEGER NOT NULL CHECK (min_sample_size_per_arm > 0),
    max_test_duration_days          INTEGER NOT NULL CHECK (max_test_duration_days > 0),
    bonferroni_correction_n         INTEGER NOT NULL CHECK (bonferroni_correction_n > 0),
    hash_seed                       BIGINT NOT NULL,
    fair_execution_lease_bucket     TEXT NOT NULL,
    lal_level                       SMALLINT NOT NULL CHECK (lal_level BETWEEN 1 AND 4),
    status                          TEXT NOT NULL DEFAULT 'preregistered'
                                    CHECK (status IN (
                                        'preregistered',
                                        'running',
                                        'concluded_efficacy',
                                        'concluded_futility',
                                        'concluded_inconclusive',
                                        'aborted'
                                    )),
    engine_mode                     TEXT NOT NULL
                                    CHECK (engine_mode IN ('demo','live_demo','live','replay')),
    created_by                      TEXT NOT NULL,
    created_at                      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at                      TIMESTAMPTZ NULL,
    ended_at                        TIMESTAMPTZ NULL,
    lease_id                        BIGINT NULL
                                    REFERENCES governance.decision_lease(lease_id),
    approval_id                     BIGINT NULL
                                    REFERENCES governance.audit_log(id),
    actor_id                        TEXT NOT NULL DEFAULT 'operator',
    rationale                       TEXT NULL,
    CONSTRAINT chk_significance_bounds  CHECK (msprt_target_significance > 0 AND msprt_target_significance < 1),
    CONSTRAINT chk_power_bounds         CHECK (msprt_target_power > 0 AND msprt_target_power < 1),
    CONSTRAINT chk_started_after_created CHECK (started_at IS NULL OR started_at >= created_at),
    CONSTRAINT chk_ended_after_started   CHECK (ended_at IS NULL OR (started_at IS NOT NULL AND ended_at >= started_at))
);
```

#### 2.1.2 設計理由（per column）

| Column | 設計 | 理由 |
|---|---|---|
| `test_id` BIGSERIAL PK | sequential | audit log temporal ordering；per V103 hypotheses + V110 reward_weight_history 範式 mirror |
| `test_name` TEXT NOT NULL UNIQUE | 人類可讀名稱 | e.g. `grid_trailing_pct_sweep_2026_06`；UNIQUE 防 duplicate test creation |
| `cluster_type` TEXT NOT NULL CHECK 4 值 | per ADR-0037 Decision 3 | 4 variant cluster 治理 surface 分類；sibling M9 DESIGN §2 詳論 |
| `hypothesis_id` BIGINT NOT NULL FK → V103 hypotheses | preregistration mandate | per ADR-0026 v3 + sibling M9 DESIGN §6.2；A/B test 必 reference preregistered hypothesis |
| `strategy_name` TEXT NOT NULL | 動態擴增 | 5 既有 + Sprint 2+ 新策略；CHECK enum 易過時（per V103 §2.1.2）|
| `control_config_hash` TEXT NOT NULL | canonical config SHA-256 | control 組 config snapshot；audit trail 可重現；per sibling M9 DESIGN §7.2 |
| `variant_count` INTEGER CHECK [2, 10] | 變更深度上限 | per ADR-0037 Decision 3 「每策略 5-15 個並行 sweep」；hard cap 10 防 over-engineering；Sprint 4 起以 5 開始（per sibling M9 DESIGN §12 Open Q 4） |
| `statistical_method` TEXT NOT NULL CHECK 3 值 | per ADR-0037 Decision 4 | mSPRT_with_AVI 主路徑 / Bayesian_AB 樣本量小場景 / fixed_horizon 變更深度小場景 |
| `msprt_target_significance` NUMERIC(8,6) DEFAULT 0.05 | α 預設 | 通用 statistical convention；bonferroni 校正前的 raw α |
| `msprt_target_power` NUMERIC(8,6) DEFAULT 0.8 | 1-β 預設 | 通用 statistical convention |
| `min_sample_size_per_arm` INTEGER NOT NULL CHECK > 0 | per power analysis derive | per sibling M9 DESIGN §3.5 公式；不寫死 magic number（per §3.8 反模式 d）|
| `max_test_duration_days` INTEGER NOT NULL CHECK > 0 | 防 test 無限延長 | per sibling M9 DESIGN §4.4 inconclusive 處置 |
| `bonferroni_correction_n` INTEGER NOT NULL CHECK > 0 | variant 數 + 並行 test 數 | α / (variant_count × parallel_test_count) 校正分母；per sibling M9 DESIGN §3.4 |
| `hash_seed` BIGINT NOT NULL | server-side seeded random | per sibling M9 DESIGN §7 + E3 must-fix；preregister 期 commit；rerun replay 必同 seed |
| `fair_execution_lease_bucket` TEXT NOT NULL | LAL Tier 對齊 | per ADR-0037 Decision 5 + sibling M9 DESIGN §5.1；對齊 ADR-0034 LAL Tier 字串 |
| `lal_level` SMALLINT CHECK [1, 4] | per ADR-0034 + sibling M9 DESIGN §2.5 cluster-LAL 對齊矩陣 | LAL 1/2/3/4；4 cluster 對應 LAL 1 (1+4) / LAL 2 (2+3)；promotion to Stage 4 永遠 LAL 3 |
| `status` TEXT NOT NULL DEFAULT 'preregistered' CHECK 6 值 | test lifecycle | preregistered → running → concluded_{efficacy/futility/inconclusive} / aborted |
| `engine_mode` NOT NULL CHECK 4 值 | TEXT + CHECK | A/B test 限 demo + live_demo + live + replay 跑；**不含 paper**（失真不採；sibling M9 DESIGN §1.6 + per CLAUDE.md §Data Migrations validation rule）|
| `created_by` TEXT NOT NULL | actor (agent role / operator) | audit trail；e.g. 'operator' / 'MIT-agent' / 'PA-dispatch' |
| `created_at` DEFAULT NOW() | audit timestamp | preregistration 時點 |
| `started_at` NULL | mSPRT 啟動時點 | running 進入時填；preregistered 階段 NULL |
| `ended_at` NULL | concluded 時點 | concluded_* / aborted 時填 |
| `lease_id` BIGINT NULL FK → governance.decision_lease | Decision Lease | per ADR-0008 + V103 §14 audit field 範式；preregistered 階段 NULL 因尚無 lease |
| `approval_id` BIGINT NULL FK → governance.audit_log | Operator approval audit | per V103 §14 範式；LAL 3 approval 寫入時填 |
| `actor_id` TEXT NOT NULL DEFAULT 'operator' | per V103 §14 範式 | preregistration 期 operator / running 期可能 'auto-allocator' (Y2) |
| `rationale` TEXT NULL | 人類可讀理由 | per V103 §14 範式；preregistration / status transition 的 reason |
| `chk_significance_bounds` CHECK | (0, 1) | α 數學範圍 |
| `chk_power_bounds` CHECK | (0, 1) | power 數學範圍 |
| `chk_started_after_created` CHECK | timeline 不變式 | started_at NULL OR >= created_at |
| `chk_ended_after_started` CHECK | timeline 不變式 | ended_at NULL OR (started_at NOT NULL AND ended_at >= started_at) |

#### 2.1.3 Indexes

```sql
-- 主 hot-path: per-strategy running test query
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_ab_tests_strategy_status_running
    ON learning.ab_tests (strategy_name, status)
    WHERE status = 'running';

-- preregistration governance review timeline
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_ab_tests_cluster_created
    ON learning.ab_tests (cluster_type, created_at DESC);

-- hypothesis_id reverse lookup (V103 → V108)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_ab_tests_hypothesis
    ON learning.ab_tests (hypothesis_id);

-- engine_mode filter (Live A/B isolation)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_ab_tests_engine_mode_live
    ON learning.ab_tests (strategy_name, created_at DESC)
    WHERE engine_mode IN ('live', 'live_demo');

-- audit trail temporal scan (lease_id + approval_id)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_ab_tests_lease_approval
    ON learning.ab_tests (lease_id, approval_id)
    WHERE lease_id IS NOT NULL;
```

**理由**：
- `(strategy_name, status) WHERE status='running'` partial：高頻 query `SELECT * FROM ab_tests WHERE strategy_name=$1 AND status='running'` for active test dashboard
- `(cluster_type, created_at DESC)`：governance review per cluster timeline
- `(hypothesis_id)`：V103 hypothesis ↔ V108 ab_tests 雙向 lookup
- `(strategy_name, created_at DESC) WHERE engine_mode IN ('live','live_demo')` partial：Live A/B isolation；對齊 MIT memory baseline ML training filter
- `(lease_id, approval_id) WHERE lease_id IS NOT NULL` partial：audit trail；NULL 不索引省空間

#### 2.1.4 Row 量級估算

- Sprint 4 read-only logging：5 strategy × ~5 parallel Cluster 1+4 test = ~25 active test
- Sprint 7-8 manual A/B：5 strategy × ~10 parallel test (含 Cluster 2+3) = ~50 active test
- Y2 auto-test：5 strategy × ~15 parallel test = ~75 active test
- 加 concluded / aborted history：~hundreds row total per yr
- **總量 ~hundreds row/yr**（regular table，無 hypertable 需求）

### 2.2 `learning.ab_assignments` — Per-Decision Variant Assignment Ledger

#### 2.2.1 表定義

```sql
CREATE TABLE IF NOT EXISTS learning.ab_assignments (
    assignment_id           BIGSERIAL PRIMARY KEY,
    test_id                 BIGINT NOT NULL
                            REFERENCES learning.ab_tests(test_id) ON DELETE CASCADE,
    decision_id             UUID NOT NULL,
    arm                     SMALLINT NOT NULL CHECK (arm >= 0),
    hash_value              NUMERIC(20,0) NOT NULL,
    assignment_method       TEXT NOT NULL
                            CHECK (assignment_method IN (
                                'deterministic_hash',
                                'stratified_random',
                                'sequential_balance'
                            )),
    stratification_keys     JSONB NULL,
    lease_id                BIGINT NOT NULL
                            REFERENCES governance.decision_lease(lease_id),
    engine_mode             TEXT NOT NULL
                            CHECK (engine_mode IN ('demo','live_demo','live','replay')),
    assigned_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_ab_assignment_test_decision UNIQUE (test_id, decision_id)
);

-- Hypertable on assigned_at (high-cardinality time-series)
SELECT create_hypertable(
    'learning.ab_assignments',
    'assigned_at',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists => TRUE
);

-- Compression policy (30d+)
ALTER TABLE learning.ab_assignments SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'test_id, arm',
    timescaledb.compress_orderby = 'assigned_at DESC'
);
SELECT add_compression_policy(
    'learning.ab_assignments',
    INTERVAL '30 days',
    if_not_exists => TRUE
);

-- Retention policy (180d)
SELECT add_retention_policy(
    'learning.ab_assignments',
    INTERVAL '180 days',
    if_not_exists => TRUE
);
```

#### 2.2.2 設計理由（per column）

| Column | 設計 | 理由 |
|---|---|---|
| `assignment_id` BIGSERIAL PK | sequential | audit log temporal ordering |
| `test_id` BIGINT NOT NULL FK ON DELETE CASCADE | 對應 test | test 撤掉 → assignment 連同 drop（per V108 placeholder §2.2 範式）|
| `decision_id` UUID NOT NULL | trade decision UUID | join `trading.fills` / `learning.decision_lease` 用 trace id |
| `arm` SMALLINT CHECK >= 0 | 0 = control / 1+ = variant index | per ADR-0037 Decision 1 schema 草案 |
| `hash_value` NUMERIC(20,0) NOT NULL | hash output | per sibling M9 DESIGN §7.2 `SHA-256(hash_seed || cryptographic_random_nonce) mod variant_count`；NUMERIC(20,0) 容納 256-bit hash 大整數 |
| `assignment_method` TEXT NOT NULL CHECK 3 值 | per sibling M9 DESIGN §7 | deterministic_hash 主路徑 / stratified_random with confounder keys / sequential_balance |
| `stratification_keys` JSONB NULL | confounder control | symbol / regime cell / time-of-day；assignment_method='stratified_random' 時必填；per sibling M9 DESIGN §7.4 |
| `lease_id` BIGINT NOT NULL FK → governance.decision_lease | fair execution 強制 | per ADR-0037 Decision 5 + sibling M9 DESIGN §5.1 + §5.5；NOT NULL 強制每 assignment 必綁 lease |
| `engine_mode` NOT NULL CHECK 4 值 | TEXT + CHECK | 對齊 ab_tests §2.1.1；不含 paper |
| `assigned_at` DEFAULT NOW() | 分配時點 | hypertable time column |
| `uq_ab_assignment_test_decision` UNIQUE | (test_id, decision_id) | 同 decision 不重複 assign（per V108 placeholder §2.2 範式）|

#### 2.2.3 Hypertable 判斷

**結論：hypertable + 7d chunk + 30d compress + 180d retention**。理由：
- per-decision 1 row → 高 cardinality time-series
- 預估 ~1k decision/day × ~10 active test × ~3 avg arm 採樣率（不 100% 都 enroll）= ~3k row/day × 180d retention = ~540k row max
- 7d chunk → ~21k row/chunk（合適 query performance）
- 30d compression → 老資料壓縮 80-90%
- 180d retention → 超期 auto-drop
- 對齊 V107 (M11 divergence) hypertable 範式 + operator prompt 規範

#### 2.2.4 Indexes

```sql
-- 主 hot-path: per-test arm sample 統計
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_ab_assignments_test_arm
    ON learning.ab_assignments (test_id, arm, assigned_at DESC);

-- decision_id 反向 lookup (trading.fills join)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_ab_assignments_decision
    ON learning.ab_assignments (decision_id);

-- lease_id audit trail
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_ab_assignments_lease
    ON learning.ab_assignments (lease_id, assigned_at DESC);

-- engine_mode filter (Live A/B isolation)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_ab_assignments_engine_mode_live
    ON learning.ab_assignments (test_id, assigned_at DESC)
    WHERE engine_mode IN ('live', 'live_demo');
```

**理由**：
- `(test_id, arm, assigned_at DESC)`：sample size count + mSPRT sequential update
- `(decision_id)`：trading.fills 反向 join 找 assignment
- `(lease_id, assigned_at DESC)`：fair execution audit trail
- `(test_id, assigned_at DESC) WHERE engine_mode IN ('live','live_demo')` partial：Live A/B isolation

#### 2.2.5 Row 量級估算

- Sprint 4 read-only logging：5 strategy × ~5 test × ~30% enrollment = ~10% × 1k decision/day = ~100 assignment/day = ~36k/yr
- Sprint 7-8 manual A/B：~300 assignment/day = ~110k/yr
- Y2 auto-test：~500 assignment/day = ~180k/yr peak (180d retention truncate)
- **Peak 180d retention ~180k row total**（hypertable + compression + retention 必要）

### 2.3 `learning.ab_results` — mSPRT Sequential Evaluation Outcome

#### 2.3.1 表定義

```sql
CREATE TABLE IF NOT EXISTS learning.ab_results (
    result_id                       BIGSERIAL,
    test_id                         BIGINT NOT NULL
                                    REFERENCES learning.ab_tests(test_id) ON DELETE CASCADE,
    arm                             SMALLINT NOT NULL CHECK (arm >= 0),
    evaluation_ts                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    n_samples                       INTEGER NOT NULL CHECK (n_samples >= 0),
    mean_metric                     NUMERIC(18,8) NOT NULL,
    std_metric                      NUMERIC(18,8) NOT NULL CHECK (std_metric >= 0),
    cumulative_pnl_usd              NUMERIC(18,8) NOT NULL,
    msprt_statistic                 NUMERIC(18,8) NULL,
    msprt_decision                  TEXT NOT NULL DEFAULT 'continue'
                                    CHECK (msprt_decision IN (
                                        'continue',
                                        'reject_h0_treatment_win',
                                        'accept_h0_no_diff',
                                        'reject_h0_control_win'
                                    )),
    avi_lower_ci                    NUMERIC(18,8) NULL,
    avi_upper_ci                    NUMERIC(18,8) NULL,
    bonferroni_adjusted_p           NUMERIC(18,8) NULL,
    efficacy_boundary_crossed       BOOLEAN NOT NULL DEFAULT FALSE,
    futility_boundary_crossed       BOOLEAN NOT NULL DEFAULT FALSE,
    is_winner                       BOOLEAN NOT NULL DEFAULT FALSE,
    m11_replay_divergence_ref       BIGINT NULL,  -- PATCHED 2026-05-22 per MIT 紅線 3：V107 PK 確認 BIGINT bigserial（V107__replay_divergence_log.sql:81-87）
    engine_mode                     TEXT NOT NULL
                                    CHECK (engine_mode IN ('demo','live_demo','live','replay')),
    created_by                      TEXT NOT NULL DEFAULT 'msprt_evaluator',
    rationale                       TEXT NULL,
    PRIMARY KEY (result_id, evaluation_ts),
    CONSTRAINT chk_avi_ci_order CHECK (
        avi_lower_ci IS NULL OR avi_upper_ci IS NULL OR avi_lower_ci <= avi_upper_ci
    ),
    CONSTRAINT chk_p_value_bounds CHECK (
        bonferroni_adjusted_p IS NULL OR (bonferroni_adjusted_p >= 0 AND bonferroni_adjusted_p <= 1)
    ),
    CONSTRAINT chk_boundary_xor CHECK (
        NOT (efficacy_boundary_crossed = TRUE AND futility_boundary_crossed = TRUE)
    )
);

-- Hypertable on evaluation_ts (high-cardinality time-series)
SELECT create_hypertable(
    'learning.ab_results',
    'evaluation_ts',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists => TRUE
);

-- Compression policy (30d+)
ALTER TABLE learning.ab_results SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'test_id, arm',
    timescaledb.compress_orderby = 'evaluation_ts DESC'
);
SELECT add_compression_policy(
    'learning.ab_results',
    INTERVAL '30 days',
    if_not_exists => TRUE
);

-- Retention policy (180d)
SELECT add_retention_policy(
    'learning.ab_results',
    INTERVAL '180 days',
    if_not_exists => TRUE
);
```

#### 2.3.2 設計理由（per column）

| Column | 設計 | 理由 |
|---|---|---|
| `result_id` BIGSERIAL | sequential | result audit ordering |
| `(result_id, evaluation_ts)` PK | 複合 PK | hypertable required PK 含 partition column |
| `test_id` BIGINT NOT NULL FK ON DELETE CASCADE | 對應 test | test 撤掉 → results 連同 drop |
| `arm` SMALLINT CHECK >= 0 | 0 = control / 1+ = variant | 同 ab_assignments |
| `evaluation_ts` DEFAULT NOW() | mSPRT sequential update 時點 | hypertable time column |
| `n_samples` INTEGER CHECK >= 0 | 累積樣本數 | 從 ab_assignments count |
| `mean_metric` NUMERIC(18,8) NOT NULL | per assignment 累積平均 | metric 通用為 net_return_bps；high precision |
| `std_metric` NUMERIC(18,8) NOT NULL CHECK >= 0 | 累積標準差 | block bootstrap 5-10d block 估計（per sibling M9 DESIGN §3.6）|
| `cumulative_pnl_usd` NUMERIC(18,8) NOT NULL | 累積 PnL USD | governance review 用 |
| `msprt_statistic` NUMERIC(18,8) NULL | mSPRT 累積統計量 | per sibling M9 DESIGN §3；NULL allowed for initial evaluation |
| `msprt_decision` TEXT NOT NULL DEFAULT 'continue' CHECK 4 值 | mSPRT lifecycle | continue / reject_h0_treatment_win / accept_h0_no_diff / reject_h0_control_win（per V108 placeholder §2.3 範式）|
| `avi_lower_ci` / `avi_upper_ci` NUMERIC(18,8) NULL | Always-Valid Inference anytime-valid CI | per ADR-0037 Decision 4 + sibling M9 DESIGN §3.3；Howard et al 2021 |
| `bonferroni_adjusted_p` NUMERIC(18,8) NULL CHECK [0, 1] | Bonferroni 校正後 p-value | per sibling M9 DESIGN §3.4 |
| `efficacy_boundary_crossed` BOOLEAN NOT NULL DEFAULT FALSE | mSPRT efficacy boundary | TRUE → 觸發 variant winner 候選 + Stage 3 live canary 啟動 |
| `futility_boundary_crossed` BOOLEAN NOT NULL DEFAULT FALSE | mSPRT futility boundary | TRUE → 觸發 test concluded_futility |
| `is_winner` BOOLEAN NOT NULL DEFAULT FALSE | variant winner flag | concluded_efficacy 時 set for winning arm |
| `m11_replay_divergence_ref` BIGINT NULL | M11 cross-ref | PATCHED 2026-05-22 per MIT 紅線 3：V107 PK = BIGINT bigserial（V107.sql:81-87 empirical verified）；UUID → BIGINT 對齊 V107 final schema |
| `engine_mode` NOT NULL CHECK 4 值 | TEXT + CHECK | 對齊 ab_tests + ab_assignments；不含 paper |
| `created_by` TEXT NOT NULL DEFAULT 'msprt_evaluator' | evaluator identity | per V103 §14 範式；可能 'auto-evaluator' (Y2) |
| `rationale` TEXT NULL | 人類可讀理由 | per V103 §14 範式；boundary_crossed 時填 "efficacy boundary at n=500 with mSPRT=4.2" |
| `chk_avi_ci_order` CHECK | CI 順序不變式 | lower_ci <= upper_ci |
| `chk_p_value_bounds` CHECK | p [0, 1] 數學範圍 | |
| `chk_boundary_xor` CHECK | efficacy XOR futility 不變式 | 兩者不能同時 TRUE（防 race condition）|

#### 2.3.3 Hypertable 判斷

**結論：hypertable + 7d chunk + 30d compress + 180d retention**。理由：
- 對齊 ab_assignments 設計 + operator prompt 規範
- 預估 ~10 test × ~24 hourly evaluation = ~240 row/day × 180d = ~43k row max
- 7d chunk → ~1.7k row/chunk
- 30d compression
- 180d retention 對齊 ab_assignments

#### 2.3.4 Indexes

```sql
-- 主 hot-path: per-test arm 最新 evaluation
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_ab_results_test_arm_eval
    ON learning.ab_results (test_id, arm, evaluation_ts DESC);

-- efficacy / futility boundary crossed partial index
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_ab_results_boundary_crossed
    ON learning.ab_results (test_id, arm, evaluation_ts DESC)
    WHERE efficacy_boundary_crossed = TRUE OR futility_boundary_crossed = TRUE;

-- winner partial index
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_ab_results_winner
    ON learning.ab_results (test_id, evaluation_ts DESC)
    WHERE is_winner = TRUE;

-- m11 replay divergence_ref reverse lookup
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_ab_results_m11_ref
    ON learning.ab_results (m11_replay_divergence_ref)
    WHERE m11_replay_divergence_ref IS NOT NULL;

-- engine_mode filter (Live A/B isolation)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_ab_results_engine_mode_live
    ON learning.ab_results (test_id, evaluation_ts DESC)
    WHERE engine_mode IN ('live', 'live_demo');
```

**理由**：
- `(test_id, arm, evaluation_ts DESC)`：governance dashboard 最新 result 查詢
- `WHERE boundary_crossed=TRUE` partial：boundary event audit hot path
- `WHERE is_winner=TRUE` partial：winner history 查詢
- `(m11_replay_divergence_ref) WHERE NOT NULL` partial：M11 cross-ref reverse lookup
- `WHERE engine_mode IN ('live','live_demo')` partial：Live A/B isolation

### 2.4 ENUM 列表（per CR-X 對齊規則）

| ENUM column | Values | Count | 來源 |
|---|---|---|---|
| `cluster_type` | parameter_sweep / signal_source_swap / risk_profile / exit_logic | 4 | ADR-0037 Decision 3 |
| `statistical_method` | mSPRT_with_AVI / Bayesian_AB / fixed_horizon | 3 | ADR-0037 Decision 4 |
| `ab_test_status` | preregistered / running / concluded_efficacy / concluded_futility / concluded_inconclusive / aborted | 6 | sibling M9 DESIGN §4.4 |
| `assignment_method` | deterministic_hash / stratified_random / sequential_balance | 3 | sibling M9 DESIGN §7 |
| `msprt_decision` | continue / reject_h0_treatment_win / accept_h0_no_diff / reject_h0_control_win | 4 | V108 placeholder §2.3 範式 |
| `engine_mode` | demo / live_demo / live / replay | 4 | CLAUDE.md §Data Migrations + V110 §2.1.1 (含 replay)；A/B test 不含 paper |

### 2.5 Materialized View (optional) — `mv_latest_winner_per_test`

operator prompt §V108 full DDL 必含「Materialized view (latest winner per test)」：

```sql
CREATE MATERIALIZED VIEW IF NOT EXISTS learning.mv_latest_winner_per_test AS
SELECT DISTINCT ON (test_id)
    test_id,
    arm AS winner_arm,
    evaluation_ts AS winner_decided_at,
    n_samples,
    mean_metric AS winner_mean_metric,
    cumulative_pnl_usd AS winner_cumulative_pnl,
    avi_lower_ci,
    avi_upper_ci,
    bonferroni_adjusted_p,
    m11_replay_divergence_ref,
    engine_mode
FROM learning.ab_results
WHERE is_winner = TRUE
  AND engine_mode IN ('live', 'live_demo')
ORDER BY test_id, evaluation_ts DESC;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_winner_per_test
    ON learning.mv_latest_winner_per_test (test_id);

-- Refresh policy: per A/B test concluded + manual REFRESH MATERIALIZED VIEW CONCURRENTLY
-- 應用層 cron 每 evaluation event 後 refresh；或 nightly batch refresh
```

**caveat**：optional；Sprint 4 read-only logging 期 evaluate 是否 land；本 spec 不強制（avoid over-engineering）。若 query pattern 顯示 hot path（governance dashboard 高頻 query winner），IMPL 期 ADD 一條 small V### migration。

### 2.6 對齊 ADR-0037 Decision 1 schema 草案

| ADR-0037 Decision 1 column | 本 spec column | 對齊 |
|---|---|---|
| `test_id UUID PRIMARY KEY` | `test_id BIGSERIAL PRIMARY KEY` | **變更**：本 spec 採 BIGSERIAL（operator prompt 明示 + 對齊 V103/V110 範式）；ADR 不 enforce UUID（注：本 spec 採 BIGSERIAL 為實作便利；UUID 為 ADR 原始建議；differ 不破 ADR）|
| `test_name text NOT NULL` | `test_name TEXT NOT NULL UNIQUE` | 本 spec 加 UNIQUE 防 duplicate |
| `cluster_type text NOT NULL CHECK IN (4 values)` | 同 | ✅ |
| `strategy_name text NOT NULL` | 同 | ✅ |
| `control_config_hash text NOT NULL` | 同 | ✅ |
| `variant_configs_hash text[] NOT NULL` | **本 spec 替為 `variant_count INTEGER CHECK [2,10]`** | variant_configs_hash array 移到應用層 / 走 V103 hypothesis spec_json；schema 級用 variant_count int 簡化 |
| `preregistered_at timestamptz NOT NULL DEFAULT now()` | `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()` | naming differ but same semantic |
| `min_sample_size_per_arm integer NOT NULL` | 同 | ✅ |
| `max_test_duration_days integer NOT NULL` | 同 | ✅ |
| `statistical_method text NOT NULL CHECK IN (3 values)` | 同 | ✅ |
| `bonferroni_correction_n integer NOT NULL` | 同 | ✅ |
| `lal_level smallint NOT NULL` | 同 | ✅ |
| `created_by text NOT NULL` | 同 | ✅ |
| `status text NOT NULL CHECK IN (6 values)` | 同 | ✅ |

**注**：本 spec PK 採 BIGSERIAL（operator prompt 明示 + V103/V110 範式 + 與既有 V### 規範一致），與 ADR-0037 Decision 1 UUID 建議 differ；不破 ADR 邏輯（type 變動為實作便利；audit trail / FK 邏輯不變）。

---

## §3 Guard A/B/C Templates（per CLAUDE.md §Data Migrations + V094 mirror）

V108 涉及 3 個 NEW table CREATE + optional MV：
- **Guard A**：表已存在但 schema 不符 → RAISE
- **Guard B**：不適用（V108 無 ALTER 既有 column）
- **Guard C**：CHECK constraint + ENUM 值齊全 + index 對齊驗證 → RAISE on mismatch

### 3.1 Guard A — table existence + 既有 schema 對齊驗證

```sql
-- ============================================================
-- Guard A: V108 預檢 — 若 3 ab_* 表已存在，必驗 V108 spec column 全俱在；缺即 RAISE
-- ============================================================
DO $$
DECLARE v_missing TEXT[];
BEGIN
    -- learning.ab_tests 已存在的情境下 check column 完整性
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='learning' AND table_name='ab_tests'
    ) THEN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'test_id', 'test_name', 'cluster_type', 'hypothesis_id',
            'strategy_name', 'control_config_hash', 'variant_count',
            'statistical_method', 'msprt_target_significance', 'msprt_target_power',
            'min_sample_size_per_arm', 'max_test_duration_days', 'bonferroni_correction_n',
            'hash_seed', 'fair_execution_lease_bucket', 'lal_level',
            'status', 'engine_mode', 'created_by', 'created_at',
            'started_at', 'ended_at', 'lease_id', 'approval_id',
            'actor_id', 'rationale'
        ]) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema='learning' AND table_name='ab_tests'
              AND column_name=c
        );
        IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
            RAISE EXCEPTION
                'V108 Guard A FAIL: learning.ab_tests exists but missing columns: %. '
                'Possible stale stub from earlier placeholder version — resolve schema reconciliation before applying V108.',
                v_missing;
        END IF;
    END IF;

    -- learning.ab_assignments 已存在的情境
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='learning' AND table_name='ab_assignments'
    ) THEN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'assignment_id', 'test_id', 'decision_id', 'arm',
            'hash_value', 'assignment_method', 'stratification_keys',
            'lease_id', 'engine_mode', 'assigned_at'
        ]) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema='learning' AND table_name='ab_assignments'
              AND column_name=c
        );
        IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
            RAISE EXCEPTION
                'V108 Guard A FAIL: learning.ab_assignments exists but missing columns: %. '
                'Resolve schema drift before applying V108.',
                v_missing;
        END IF;
    END IF;

    -- learning.ab_results 已存在的情境
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='learning' AND table_name='ab_results'
    ) THEN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'result_id', 'test_id', 'arm', 'evaluation_ts',
            'n_samples', 'mean_metric', 'std_metric', 'cumulative_pnl_usd',
            'msprt_statistic', 'msprt_decision', 'avi_lower_ci', 'avi_upper_ci',
            'bonferroni_adjusted_p', 'efficacy_boundary_crossed',
            'futility_boundary_crossed', 'is_winner',
            'm11_replay_divergence_ref', 'engine_mode',
            'created_by', 'rationale'
        ]) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema='learning' AND table_name='ab_results'
              AND column_name=c
        );
        IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
            RAISE EXCEPTION
                'V108 Guard A FAIL: learning.ab_results exists but missing columns: %. '
                'Resolve schema drift before applying V108.',
                v_missing;
        END IF;
    END IF;

    -- learning.hypotheses 必須存在（ab_tests.hypothesis_id FK target，V103 prereq）
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='learning' AND table_name='hypotheses'
    ) THEN
        RAISE EXCEPTION
            'V108 Guard A FAIL: learning.hypotheses missing — '
            'V103 must apply before V108. Verify _sqlx_migrations.';
    END IF;

    -- governance.decision_lease 必須存在（ab_assignments.lease_id FK target）
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='governance' AND table_name='decision_lease'
    ) THEN
        RAISE EXCEPTION
            'V108 Guard A FAIL: governance.decision_lease missing — '
            'Decision Lease infra (ADR-0008) must apply before V108. Verify _sqlx_migrations.';
    END IF;

    -- governance.audit_log 必須存在（ab_tests.approval_id FK target）
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='governance' AND table_name='audit_log'
    ) THEN
        RAISE EXCEPTION
            'V108 Guard A FAIL: governance.audit_log missing — '
            'V098 must apply before V108. Verify _sqlx_migrations.';
    END IF;
END $$;
```

### 3.2 Guard B — 不適用

V108 不 ALTER 既有 column type；無 type-sensitive 檢查需求。本 spec 不設 Guard B 段。

### 3.3 Guard C — CHECK constraint + ENUM 值齊全 + index 對齊驗證

```sql
-- ============================================================
-- Guard C: V108 預檢 — 重跑 V108 時 idempotent 檢查
-- CHECK constraint + ENUM 值齊全 + bounds + index 對齊
-- ============================================================
DO $$
DECLARE v_actual TEXT;
BEGIN
    -- ab_tests.cluster_type CHECK 4 值齊全
    SELECT pg_get_constraintdef(oid) INTO v_actual
    FROM pg_constraint
    WHERE conrelid='learning.ab_tests'::regclass
      AND conname LIKE '%cluster_type%check%';
    IF v_actual IS NOT NULL THEN
        IF position('parameter_sweep' IN v_actual) = 0
           OR position('signal_source_swap' IN v_actual) = 0
           OR position('risk_profile' IN v_actual) = 0
           OR position('exit_logic' IN v_actual) = 0
        THEN
            RAISE EXCEPTION
                'V108 Guard C FAIL: learning.ab_tests cluster_type CHECK enum mismatch. '
                'Actual: %. Expected parameter_sweep/signal_source_swap/risk_profile/exit_logic.',
                v_actual;
        END IF;
    END IF;

    -- ab_tests.statistical_method CHECK 3 值齊全
    SELECT pg_get_constraintdef(oid) INTO v_actual
    FROM pg_constraint
    WHERE conrelid='learning.ab_tests'::regclass
      AND conname LIKE '%statistical_method%check%';
    IF v_actual IS NOT NULL THEN
        IF position('mSPRT_with_AVI' IN v_actual) = 0
           OR position('Bayesian_AB' IN v_actual) = 0
           OR position('fixed_horizon' IN v_actual) = 0
        THEN
            RAISE EXCEPTION
                'V108 Guard C FAIL: learning.ab_tests statistical_method CHECK enum mismatch. '
                'Actual: %. Expected mSPRT_with_AVI/Bayesian_AB/fixed_horizon.',
                v_actual;
        END IF;
    END IF;

    -- ab_tests.status CHECK 6 值齊全
    SELECT pg_get_constraintdef(oid) INTO v_actual
    FROM pg_constraint
    WHERE conrelid='learning.ab_tests'::regclass
      AND conname LIKE '%status%check%';
    IF v_actual IS NOT NULL THEN
        IF position('preregistered' IN v_actual) = 0
           OR position('running' IN v_actual) = 0
           OR position('concluded_efficacy' IN v_actual) = 0
           OR position('concluded_futility' IN v_actual) = 0
           OR position('concluded_inconclusive' IN v_actual) = 0
           OR position('aborted' IN v_actual) = 0
        THEN
            RAISE EXCEPTION
                'V108 Guard C FAIL: learning.ab_tests status CHECK enum mismatch. '
                'Actual: %. Expected preregistered/running/concluded_efficacy/concluded_futility/concluded_inconclusive/aborted.',
                v_actual;
        END IF;
    END IF;

    -- ab_assignments.assignment_method CHECK 3 值齊全
    SELECT pg_get_constraintdef(oid) INTO v_actual
    FROM pg_constraint
    WHERE conrelid='learning.ab_assignments'::regclass
      AND conname LIKE '%assignment_method%check%';
    IF v_actual IS NOT NULL THEN
        IF position('deterministic_hash' IN v_actual) = 0
           OR position('stratified_random' IN v_actual) = 0
           OR position('sequential_balance' IN v_actual) = 0
        THEN
            RAISE EXCEPTION
                'V108 Guard C FAIL: learning.ab_assignments assignment_method CHECK enum mismatch. '
                'Actual: %. Expected deterministic_hash/stratified_random/sequential_balance.',
                v_actual;
        END IF;
    END IF;

    -- ab_results.msprt_decision CHECK 4 值齊全
    SELECT pg_get_constraintdef(oid) INTO v_actual
    FROM pg_constraint
    WHERE conrelid='learning.ab_results'::regclass
      AND conname LIKE '%msprt_decision%check%';
    IF v_actual IS NOT NULL THEN
        IF position('continue' IN v_actual) = 0
           OR position('reject_h0_treatment_win' IN v_actual) = 0
           OR position('accept_h0_no_diff' IN v_actual) = 0
           OR position('reject_h0_control_win' IN v_actual) = 0
        THEN
            RAISE EXCEPTION
                'V108 Guard C FAIL: learning.ab_results msprt_decision CHECK enum mismatch. '
                'Actual: %. Expected continue/reject_h0_treatment_win/accept_h0_no_diff/reject_h0_control_win.',
                v_actual;
        END IF;
    END IF;

    -- engine_mode CHECK 4 值齊全（3 表共用；不含 paper）
    FOR v_actual IN
        SELECT pg_get_constraintdef(c.oid)
        FROM pg_constraint c
        JOIN pg_class r ON c.conrelid = r.oid
        JOIN pg_namespace n ON r.relnamespace = n.oid
        WHERE n.nspname='learning'
          AND r.relname IN ('ab_tests', 'ab_assignments', 'ab_results')
          AND c.conname LIKE '%engine_mode%check%'
    LOOP
        IF position('demo' IN v_actual) = 0
           OR position('live_demo' IN v_actual) = 0
           OR position('live' IN v_actual) = 0
           OR position('replay' IN v_actual) = 0
        THEN
            RAISE EXCEPTION
                'V108 Guard C FAIL: engine_mode CHECK enum mismatch on 3 V108 tables. '
                'Actual: %. Expected demo/live_demo/live/replay (paper excluded).',
                v_actual;
        END IF;
        -- 額外驗 paper 不在 CHECK 內
        IF position('paper' IN v_actual) > 0 THEN
            RAISE EXCEPTION
                'V108 Guard C FAIL: engine_mode CHECK includes paper, which is excluded for A/B test. '
                'Actual: %. A/B test 失真不採 paper.',
                v_actual;
        END IF;
    END LOOP;

    -- ab_tests.variant_count CHECK bounds [2, 10]
    SELECT pg_get_constraintdef(oid) INTO v_actual
    FROM pg_constraint
    WHERE conrelid='learning.ab_tests'::regclass
      AND conname LIKE '%variant_count%check%';
    IF v_actual IS NOT NULL THEN
        IF position('BETWEEN 2 AND 10' IN v_actual) = 0 
           AND (position('>= 2' IN v_actual) = 0 OR position('<= 10' IN v_actual) = 0) THEN
            RAISE EXCEPTION
                'V108 Guard C FAIL: ab_tests variant_count CHECK bounds [2, 10] missing. '
                'Actual: %.',
                v_actual;
        END IF;
    END IF;

    -- ab_tests.lal_level CHECK bounds [1, 4]
    SELECT pg_get_constraintdef(oid) INTO v_actual
    FROM pg_constraint
    WHERE conrelid='learning.ab_tests'::regclass
      AND conname LIKE '%lal_level%check%';
    IF v_actual IS NOT NULL THEN
        IF position('BETWEEN 1 AND 4' IN v_actual) = 0 
           AND (position('>= 1' IN v_actual) = 0 OR position('<= 4' IN v_actual) = 0) THEN
            RAISE EXCEPTION
                'V108 Guard C FAIL: ab_tests lal_level CHECK bounds [1, 4] missing. '
                'Actual: %.',
                v_actual;
        END IF;
    END IF;

    -- ab_assignments UNIQUE (test_id, decision_id) constraint
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid='learning.ab_assignments'::regclass
          AND conname = 'uq_ab_assignment_test_decision'
          AND contype = 'u'
    ) THEN
        RAISE EXCEPTION
            'V108 Guard C FAIL: ab_assignments UNIQUE (test_id, decision_id) missing. '
            'Fair execution invariant violated — same decision could be assigned to multiple arms.';
    END IF;

    -- ab_results chk_boundary_xor 不變式 CHECK
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid='learning.ab_results'::regclass
          AND conname = 'chk_boundary_xor'
    ) THEN
        RAISE EXCEPTION
            'V108 Guard C FAIL: chk_boundary_xor missing. '
            'efficacy_boundary_crossed and futility_boundary_crossed must not both be TRUE simultaneously.';
    END IF;

    -- 各表 index 存在驗證（spot check 主 hot-path index）
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE schemaname='learning' AND tablename='ab_tests'
          AND indexname='idx_ab_tests_strategy_status_running'
    ) THEN
        RAISE EXCEPTION
            'V108 Guard C FAIL: idx_ab_tests_strategy_status_running missing. Hot-path index violated.';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE schemaname='learning' AND tablename='ab_assignments'
          AND indexname='idx_ab_assignments_test_arm'
    ) THEN
        RAISE EXCEPTION
            'V108 Guard C FAIL: idx_ab_assignments_test_arm missing. Hot-path index violated.';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE schemaname='learning' AND tablename='ab_results'
          AND indexname='idx_ab_results_test_arm_eval'
    ) THEN
        RAISE EXCEPTION
            'V108 Guard C FAIL: idx_ab_results_test_arm_eval missing. Hot-path index violated.';
    END IF;
END $$;
```

### 3.4 Guard 設計理念（per V094 mirror）

| Guard | 觸發場景 | RAISE 條件 | NOT RAISE 條件（idempotent）|
|---|---|---|---|
| A | 3 NEW table 已存在但 column 缺；or V103 hypotheses / decision_lease / audit_log 缺 | RAISE | 全 column 俱在 / table 不存在（首次跑）|
| C | CHECK constraint 缺 enum / bounds 缺 / index 缺 / paper 誤入 engine_mode | RAISE | constraint+index 完整（重跑）|

**重跑 V108 第二次必不 RAISE**（idempotency per CLAUDE.md §Data Migrations + V055/V083/V084 incident precedent）。

---

## §4 Linux PG Empirical Dry-Run Protocol（mandatory）

per CLAUDE.md §Data Migrations + `feedback_v_migration_pg_dry_run.md` + V055 5-round loop / V083 / V084 incident chain，V108 涉及：
- PG reflection（information_schema for Guard A）
- CHECK constraint ENUM runtime semantic（Guard C）
- FK constraint to V103 hypotheses + governance.decision_lease + governance.audit_log（multi-target FK）
- TimescaleDB hypertable 操作（2 表：ab_assignments + ab_results）
- compression + retention policy（hypertable 2 表）
- materialized view (optional)

**必先 Linux PG empirical 驗證**，禁 Mac mock pytest 代替。

### 4.1 PA C9 待跑的 4 條 SQL（spec sign-off 前必補資料）

per operator prompt + MIT 5.21 audit Risk 2，PA 在 dispatch 前必執行以下 ssh trade-core PG query：

```bash
# Query 1: _sqlx_migrations head + recent versions
ssh trade-core "PGPASSWORD='<REDACTED>' psql -h localhost -U trading_admin -d trading_ai -c \"SELECT max(version), array_agg(version ORDER BY version DESC) FROM (SELECT version FROM _sqlx_migrations ORDER BY version DESC LIMIT 15) sub\""
# Expected: V107 already applied (Sprint 1A-β); V108 = next slot OR after V109/V110/V112/V113 batch

# Query 2: V103 hypotheses + governance.decision_lease + governance.audit_log FK targets 確認
ssh trade-core "PGPASSWORD='<REDACTED>' psql -h localhost -U trading_admin -d trading_ai -c \"SELECT table_schema, table_name FROM information_schema.tables WHERE (table_schema='learning' AND table_name='hypotheses') OR (table_schema='governance' AND table_name IN ('decision_lease','audit_log')) ORDER BY table_schema, table_name\""
# Expected: 3 rows (learning.hypotheses + governance.decision_lease + governance.audit_log) all exist

# Query 3: ab_* 表是否已存在
ssh trade-core "PGPASSWORD='<REDACTED>' psql -h localhost -U trading_admin -d trading_ai -c \"SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema='learning' AND table_name LIKE 'ab_%' ORDER BY table_name\""
# Expected: 0 row (first apply) / 3 rows (Guard A 驗證 column 全俱在)

# Query 4: PG 容量 + TimescaleDB extension 已 install 驗證
ssh trade-core "PGPASSWORD='<REDACTED>' psql -h localhost -U trading_admin -d trading_ai -c \"SELECT extname, extversion FROM pg_extension WHERE extname IN ('timescaledb', 'uuid-ossp', 'pgcrypto')\""
# Expected: timescaledb 已 install (V001 land 期已 enable); uuid-ossp 或 pgcrypto 已 install for UUID generation

# Query 5 (extra): governance.decision_lease column 確認 FK target
ssh trade-core "PGPASSWORD='<REDACTED>' psql -h localhost -U trading_admin -d trading_ai -c \"SELECT column_name, data_type FROM information_schema.columns WHERE table_schema='governance' AND table_name='decision_lease' AND column_name='lease_id'\""
# Expected: 1 row, lease_id BIGINT
```

**待 PA C9 補資料的 4 處 placeholder**（spec sign-off 前必更新）：

1. `_sqlx_migrations` head 真實 = ?（spec 假設 V107 後 V108；若 V108-V113 並行 land 順序需 PA 仲裁）
2. V103 hypotheses + governance.decision_lease + governance.audit_log FK target 確認（V108 Guard A 引用）
3. TimescaleDB extension version 確認（V108 hypertable 設計 + compression policy）
4. UUID extension 名稱（`uuid-ossp` vs `pgcrypto` — IMPL 期決定）

### 4.2 Round 1 — V108 SQL 真實 PG semantic empirical 驗證

```bash
# ssh trade-core 執行（不在 Mac 跑）
ssh trade-core "
  cd ~/BybitOpenClaw/srv && \
  PGPASSWORD='<REDACTED>' psql -h localhost -U trading_admin -d trading_ai \
    -v ON_ERROR_STOP=1 -f sql/migrations/V108__ab_testing_framework.sql
"
```

**Round 1 必驗 12 項**（empirical SELECT verify after V108 apply）：

```sql
-- 1. 3 ab_* tables 存在
SELECT table_name FROM information_schema.tables
WHERE table_schema='learning' AND table_name LIKE 'ab_%'
ORDER BY table_name;
-- Expected: ab_assignments, ab_results, ab_tests (3 rows)

-- 2. ab_tests 26 columns
SELECT count(*) FROM information_schema.columns
WHERE table_schema='learning' AND table_name='ab_tests';
-- Expected: 26

-- 3. ab_assignments 10 columns
SELECT count(*) FROM information_schema.columns
WHERE table_schema='learning' AND table_name='ab_assignments';
-- Expected: 10

-- 4. ab_results 20 columns
SELECT count(*) FROM information_schema.columns
WHERE table_schema='learning' AND table_name='ab_results';
-- Expected: 20

-- 5. CHECK constraint 4 cluster_type values
SELECT pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid='learning.ab_tests'::regclass AND conname LIKE '%cluster_type%check%';
-- Expected: 含 4 個 cluster_type 值 (parameter_sweep, signal_source_swap, risk_profile, exit_logic)

-- 6. FK constraint chain
SELECT conname, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid IN (
    'learning.ab_tests'::regclass,
    'learning.ab_assignments'::regclass,
    'learning.ab_results'::regclass
) AND contype='f'
ORDER BY conname;
-- Expected: 5 FK rows
--   ab_tests.hypothesis_id → learning.hypotheses(hypothesis_id)
--   ab_tests.lease_id → governance.decision_lease(lease_id)
--   ab_tests.approval_id → governance.audit_log(id)
--   ab_assignments.test_id → learning.ab_tests(test_id) ON DELETE CASCADE
--   ab_assignments.lease_id → governance.decision_lease(lease_id)
--   ab_results.test_id → learning.ab_tests(test_id) ON DELETE CASCADE

-- 7. Hypertable 確認（ab_assignments + ab_results）
SELECT hypertable_name, num_dimensions
FROM timescaledb_information.hypertables
WHERE hypertable_schema='learning'
  AND hypertable_name IN ('ab_assignments', 'ab_results')
ORDER BY hypertable_name;
-- Expected: 2 rows, each num_dimensions=1

-- 8. Index 確認
SELECT indexname FROM pg_indexes
WHERE schemaname='learning'
  AND tablename IN ('ab_tests', 'ab_assignments', 'ab_results')
ORDER BY indexname;
-- Expected: ≥ 13 indexes
--   ab_tests_pkey + 5 user indexes
--   ab_assignments_pkey + 1 UNIQUE + 4 user indexes
--   ab_results_pkey + 5 user indexes

-- 9. engine_mode CHECK 真 reject 非 4 值 (empirical INSERT test)
BEGIN;
SAVEPOINT test_engine_mode;
INSERT INTO learning.ab_tests
    (test_name, cluster_type, hypothesis_id, strategy_name,
     control_config_hash, variant_count, statistical_method,
     min_sample_size_per_arm, max_test_duration_days,
     bonferroni_correction_n, hash_seed,
     fair_execution_lease_bucket, lal_level, engine_mode, created_by)
VALUES
    ('test_engine_mode_paper', 'parameter_sweep', 1, 'grid_trading',
     'hash_abc', 2, 'mSPRT_with_AVI', 100, 30, 5, 12345,
     'tier_a', 1, 'paper', 'test');
-- Expected: ERROR: violates check constraint (paper excluded)
ROLLBACK TO SAVEPOINT test_engine_mode;

-- 10. variant_count CHECK reject < 2 (boundary test)
SAVEPOINT test_variant_count_low;
INSERT INTO learning.ab_tests
    (test_name, cluster_type, hypothesis_id, strategy_name,
     control_config_hash, variant_count, statistical_method,
     min_sample_size_per_arm, max_test_duration_days,
     bonferroni_correction_n, hash_seed,
     fair_execution_lease_bucket, lal_level, engine_mode, created_by)
VALUES
    ('test_variant_count_low', 'parameter_sweep', 1, 'grid_trading',
     'hash_abc', 1, 'mSPRT_with_AVI', 100, 30, 5, 12345,
     'tier_a', 1, 'live', 'test');
-- Expected: ERROR: violates chk variant_count
ROLLBACK TO SAVEPOINT test_variant_count_low;

-- 11. UNIQUE (test_id, decision_id) reject duplicate assignment
SAVEPOINT test_duplicate_assignment;
-- 假設 test_id=1 + decision_id='xxx' 已存在某 row
-- 嘗試 second insert 同 (test_id, decision_id) 不同 arm
INSERT INTO learning.ab_assignments
    (test_id, decision_id, arm, hash_value, assignment_method,
     lease_id, engine_mode)
VALUES
    (1, 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee', 0, 12345,
     'deterministic_hash', 1, 'live');
INSERT INTO learning.ab_assignments
    (test_id, decision_id, arm, hash_value, assignment_method,
     lease_id, engine_mode)
VALUES
    (1, 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee', 1, 67890,
     'deterministic_hash', 1, 'live');
-- Expected: ERROR: duplicate key violates UNIQUE constraint uq_ab_assignment_test_decision
ROLLBACK TO SAVEPOINT test_duplicate_assignment;

-- 12. chk_boundary_xor reject 同時 efficacy + futility TRUE
SAVEPOINT test_boundary_xor;
INSERT INTO learning.ab_results
    (test_id, arm, n_samples, mean_metric, std_metric, cumulative_pnl_usd,
     msprt_decision, efficacy_boundary_crossed, futility_boundary_crossed,
     engine_mode)
VALUES
    (1, 1, 100, 0.05, 0.1, 50.0, 'continue', TRUE, TRUE, 'live');
-- Expected: ERROR: violates chk_boundary_xor
ROLLBACK TO SAVEPOINT test_boundary_xor;
ROLLBACK;
```

### 4.3 Round 2 — Idempotency 驗證

重跑 V108.sql 第二次必不 RAISE / 必不重複建 index / 必不 fail：

```bash
ssh trade-core "
  cd ~/BybitOpenClaw/srv && \
  PGPASSWORD='<REDACTED>' psql -h localhost -U trading_admin -d trading_ai \
    -v ON_ERROR_STOP=1 -f sql/migrations/V108__ab_testing_framework.sql
"
# Expected exit code 0; all DO blocks output NOTICE-only PASS; 0 RAISE EXCEPTION
```

**Round 2 後驗證**：
```sql
-- 確認 V108 不 double-create
SELECT count(*) FROM information_schema.tables
WHERE table_schema='learning' AND table_name LIKE 'ab_%';
-- Expected: 3

-- 確認 index 不 double-create
SELECT count(*) FROM pg_indexes
WHERE schemaname='learning' AND tablename LIKE 'ab_%';
-- Expected: ≥ 13 (3 PK + 1 UNIQUE + ≥ 14 user indexes)

-- 確認 hypertable 不 double-create
SELECT count(*) FROM timescaledb_information.hypertables
WHERE hypertable_schema='learning'
  AND hypertable_name IN ('ab_assignments', 'ab_results');
-- Expected: 2
```

### 4.4 為何 Mac mock pytest 不夠（V055 5-round loop 教訓）

per memory `feedback_v_migration_pg_dry_run.md` + `project_2026_05_02_p0_sqlx_hash_drift`：
- Mac mock pytest 無法捕捉 PG runtime 真實 PL/pgSQL DO block semantic（特別是 Guard A `array_agg` + `unnest`）
- Mac static parse review 無法驗 `pg_get_constraintdef` 真實輸出對齊 spec
- Mac 無法驗 TimescaleDB hypertable 真建立（hypertable function 需 PG runtime）
- Mac 無法驗 FK constraint cross-schema target（governance.decision_lease + governance.audit_log + learning.hypotheses）真存在
- V055 chain 5 round 都 Mac false-pass 後 Linux 撞 bug；V108 / V094 / V083 / V084 / V103 / V110 全須遵守 V055 mandate

**E2 / E4 / A3 review 必含 Linux PG dry-run gate 證據 ID**（per CLAUDE.md §Data Migrations + V094 §4.3 範式）。

---

## §5 sqlx Checksum Repair SOP

per memory `project_2026_05_02_p0_sqlx_hash_drift`（commit `3681f83`），V108 file edit 後 DB checksum 必同步：

```bash
# E1 IMPL：寫 V108.sql 完成後跑 Linux dry-run（per §4.2）
# 若 V108.sql 落地後又被 edit → DB checksum drift
# 必跑 repair binary 同步 checksum 到 _sqlx_migrations table

ssh trade-core "
  cd ~/BybitOpenClaw/srv && \
  cargo run --release --bin repair_migration_checksum -- --version 108
"
# Expected: V108 checksum updated in _sqlx_migrations table to match new file SHA
```

### 5.1 Engine restart 後驗證 sqlx migrate 不 panic

```bash
ssh trade-core "bash ~/BybitOpenClaw/srv/helper_scripts/restart_all.sh --rebuild"

ssh trade-core "tail -200 ~/BybitOpenClaw/srv/program_code/exchange_connectors/bybit_connector/openclaw_engine/logs/engine.log 2>&1 | grep -E 'sqlx|migration|panic'"
# Expected: 0 panic; 'Applied migrations' 正常 log; V108 success=t in _sqlx_migrations

ssh trade-core "PGPASSWORD='<REDACTED>' psql -h localhost -U trading_admin -d trading_ai -c 'SELECT version, success, description FROM _sqlx_migrations WHERE version=108;'"
# Expected: 1 row, success=t
```

### 5.2 治理盲點防範

per `project_2026_05_02_p0_sqlx_hash_drift` + V094 §5.3：cargo test PASS ≠ runtime sqlx migrate 驗證。E2 / E4 review 必含「engine restart 實測 + sqlx migrate runtime 不 panic」driver evidence。

---

## §6 IMPL Plan（簡）

### 6.1 E1 工作鏈

```
本 V108 spec PM sign-off + PA C9 dry-run 補資料 land
  ↓
PA dispatch decide V108 ordering（V108 在 Sprint 1A-γ 與 V105 + V109 + V111 並行，per §7 cross-V### dependency）
  ↓
E1 IMPL (1 worktree)：
  └─ Worktree A: 寫 V108.sql 含 Guard A/C + 3 CREATE TABLE + 2 hypertable + 2 compression policy
     + 2 retention policy + 14 CONCURRENTLY index + optional MV
     (~250 LOC SQL, 1-1.5 E1-day，含 Linux PG dry-run × 2 round)
  ↓
E2 review (≥45min, 重點查 §6.2 5 高風險點)
  ↓
E4 regression (cargo test --release + pytest healthcheck)
  ↓
ssh trade-core 跑 V108.sql Linux PG dry-run × 2 round + 12 empirical 驗
  ↓
restart_all --rebuild deploy
  ↓
engine restart verify sqlx migrate runtime PASS
  ↓
QA cycle（Sprint 1A-γ 整體 closure）
  ↓
PM sign-off
```

### 6.2 E2 Review 重點 5 項

#### 6.2.1 Linux PG dry-run gate 證據 ID 必出現

E2 PR 審查必拒「無 Linux PG dry-run × 2 round 證據 ID」的 V108 PR：
- E1 IMPL commit message 含 dry-run round 1 + round 2 commit ID 或 ssh trade-core 操作 ID
- 重跑 V108 SQL 第二次的 NOTICE 輸出 attached（idempotency 證明）
- empirical INSERT test 12 條 reject 結果 attached（engine_mode paper / variant_count low / UNIQUE duplicate / boundary XOR 等）

#### 6.2.2 4 cluster_type ENUM 對齊 ADR-0037 Decision 3

E2 必驗 V108 SQL `cluster_type` CHECK 4 值 = `parameter_sweep / signal_source_swap / risk_profile / exit_logic`：
- 對齊 ADR-0037 Decision 3 + sibling M9 DESIGN §2
- 命名不一致（如 `signal_swap` vs `signal_source_swap`）→ REJECT

#### 6.2.3 engine_mode CHECK 4 值（不含 paper；含 replay）

E2 必跑 Guard C SQL 確認 engine_mode CHECK 含 `'demo','live_demo','live','replay'` 4 值 + 不含 'paper'：
- `replay` 為 M11 continuous replay hookup 用（per V110 §2.1.1）
- `paper` 失真不採（per sibling M9 DESIGN §1.6 + CLAUDE.md §Data Migrations rule）
- 任一缺漏 / paper 誤入 → REJECT

#### 6.2.4 Hypertable + Compression + Retention 對齊

E2 必驗 V108 SQL：
- ab_assignments + ab_results 都 hypertable（per operator prompt）
- 7d chunk + 30d compress + 180d retention 對齊（per operator prompt + V107 範式）
- chunk_time_interval 設 `'7 days'` interval（不 `7 * 86400` 或其他形式）

#### 6.2.5 FK chain 對齊 ADR-0037 Decision 1 + Decision 5

E2 必驗 V108 SQL FK：
- `ab_tests.hypothesis_id → learning.hypotheses(hypothesis_id) NOT NULL`（preregistration 強制；per ADR-0037 Decision 1 + sibling M9 DESIGN §6.2）
- `ab_assignments.lease_id → governance.decision_lease(lease_id) NOT NULL`（fair execution 強制；per ADR-0037 Decision 5 + sibling M9 DESIGN §5.5）
- `ab_assignments.test_id ON DELETE CASCADE`（test 撤掉 → assignment 連同 drop）
- `ab_results.test_id ON DELETE CASCADE`（test 撤掉 → results 連同 drop）
- `ab_results.m11_replay_divergence_ref` 不 FK（BIGINT 純 reference；PATCHED 2026-05-22 — V107 type empirical verify = BIGINT bigserial；FK 待 M11 land 時補 cross-V### dependency）

---

## §7 Cross-V### Dependencies

per CR-9 cross-V### dependency graph + sibling M9 DESIGN §12.1：

| V### | Direction | 關係 | Schema-level FK? |
|---|---|---|---|
| V108 (own) | 主 spec | M9 framework schema | — |
| V103 (hypotheses) | V108 → V103 | `ab_tests.hypothesis_id NOT NULL FK` per §6.2 | ✅ FK NOT NULL |
| V110 (M6 reward) | V108 → V110 | Cluster 3 risk profile variant ref M6 weight_set_id；應用層 join | ❌ No FK (cross-1A-β/γ decoupled) |
| V109 (M8 anomaly) | V108 → V109 | M9 variant 若觸發 M8 anomaly → variant abort；應用層 cron | ❌ No FK |
| V113 (M7 decay) | V108 → V113 | per sibling M9 DESIGN §9 M7 single decay authority；應用層 join | ❌ No FK |
| V107 (M11 replay) | V108 → V107 | per sibling M9 DESIGN §8；BIGINT reference, not FK | ⚠️ No FK yet (BIGINT type confirmed 2026-05-22；FK 待 M11 land) |
| V111 (M10 discovery) | V108 → V111 | M9 variant 若為 M10 discovery generated → 走 LAL 3 elevated approval | ❌ No FK |
| governance.decision_lease | V108 → governance | ab_tests.lease_id + ab_assignments.lease_id | ✅ FK |
| governance.audit_log | V108 → governance | ab_tests.approval_id | ✅ FK NULL |

### 7.1 Sprint dispatch ordering

- **Sprint 1A-β** 必先 land V103 (已 land 2026-05-21) + V107 + V110 + V112 + V113
- **Sprint 1A-γ** 才能 land V105 (M2) + V108 (M9) + V109 (M8) + V111 (M10)
- β → γ 不可重疊（per E5 + MIT 共識，per PA report 行 352）

### 7.2 V108 在 1A-γ 並行 schedule

V108 與 V105 + V109 + V111 同 1A-γ 並行 land；沒有 cross-1A-γ FK，可獨立 dispatch。

---

## §8 Backward Compat

### 8.1 Append-only 設計

V108 是 **append-only schema migration**：
- 加 3 個 NEW table（learning schema 既有 + 1 optional MV）
- 加 2 hypertable + 2 compression policy + 2 retention policy
- 加 14 user index + 1 UNIQUE constraint
- 0 ALTER 既有 column
- 0 DROP 既有 schema
- 0 RENAME

### 8.2 不破現有 SELECT / INSERT / UPDATE

| 既有操作 | V108 影響 |
|---|---|
| `SELECT * FROM learning.*` | new tables 不影響既有 21+ learning tables |
| `INSERT INTO learning.hypotheses` | V108 加 FK reference 但不改 hypotheses 結構（V103 已 land 為 prereq）|
| `INSERT INTO governance.decision_lease` | V108 加 FK reference 但不改 decision_lease 結構（ADR-0008 infra 已 land）|
| `SELECT FROM trading.fills` | V108 不改 fills 寫入路徑；ab_assignments.decision_id 是反向 ref |
| 既有 healthcheck（55 個 check per V094 §7.5）| 0 影響（沒有 check 引用 V108 新表）；新 healthcheck Sprint 4+ 才加 |

### 8.3 對 future writer behaviour

| Table | 第一個 row 來源 | Sprint |
|---|---|---|
| learning.ab_tests | E1 IMPL Sprint 4 read-only logging 期 preregistration writer | 1A-γ land schema → Sprint 4 first writer row |
| learning.ab_assignments | E1 IMPL Sprint 4 read-only logging 期 assignment writer | 1A-γ land schema → Sprint 4 first writer row |
| learning.ab_results | E1 IMPL Sprint 4 read-only logging 期 mSPRT evaluation cron writer | 1A-γ land schema → Sprint 4 first writer row |

**Empty-table 期間**：3 表 V108 apply 後立即 0 row（Foundation stage per MIT pipeline maturity）；writer code spawn 是 Sprint 4 工作（per MIT pipeline maturity audit Skeleton stage）。

---

## §9 Rollback Path

### 9.1 V108 rollback

```sql
-- Drop hypertable retention + compression policies first
SELECT remove_retention_policy('learning.ab_assignments', if_exists => TRUE);
SELECT remove_retention_policy('learning.ab_results', if_exists => TRUE);
SELECT remove_compression_policy('learning.ab_assignments', if_exists => TRUE);
SELECT remove_compression_policy('learning.ab_results', if_exists => TRUE);

-- Drop optional materialized view
DROP MATERIALIZED VIEW IF EXISTS learning.mv_latest_winner_per_test;

-- Drop tables (FK CASCADE handles ab_assignments + ab_results 自動 drop)
DROP TABLE IF EXISTS learning.ab_results;
DROP TABLE IF EXISTS learning.ab_assignments;
DROP TABLE IF EXISTS learning.ab_tests;
-- 0 row loss（V108 apply 後立即 0 row）
-- 14 index 隨 table DROP 自動 drop
-- 5 FK 隨 table DROP 自動 drop
```

### 9.2 V096 boundary

per V103 spec §8.3 + V110 §10.2：rollback 路徑不跨 V096（V096 drop dead tables 不可逆）。V108 rollback 全在 V096 之後（V096 < V098 < V103 < V108），無 boundary 風險。

---

## §10 開放問題 / Caveat

### 10.1 待 PA C9 確認 + Open Q（per sibling M9 DESIGN §12.3）

1. **`_sqlx_migrations` head 真實 = ?**：spec 假設 V107 後 V108；若 V108-V113 並行 land 順序需 PA 仲裁
2. **V107 final schema type (UUID vs BIGINT)** **✅ RESOLVED 2026-05-22**：empirical verify V107__replay_divergence_log.sql:81-87 PK = id BIGINT bigserial；本 spec ab_results.m11_replay_divergence_ref type 已 patch UUID → BIGINT NULL；FK 仍 deferred 到 M11 land
3. **TimescaleDB extension version**：影響 hypertable + compression + retention policy 語法（不同版本 chunk_time_interval 參數名差異）
4. **UUID extension 名稱**：`uuid-ossp` (`uuid_generate_v4()`) vs `pgcrypto` (`gen_random_uuid()`) — IMPL 期 V108.sql 對應函數呼叫（與 V110 共用）
5. **mSPRT AVI 具體 closed-form 公式**：per sibling M9 DESIGN §12.3 Open Q 2；V108 spec doc IMPL 期決策；本 spec 只列 schema 對應 column；IMPL 期 land
6. **Bonferroni 替代 FDR 切換 trigger**：per sibling M9 DESIGN §12.3 Open Q 3；V108 `statistical_method` ENUM 是否擴 FDR 第四值（`Benjamini_Hochberg`）；Sprint 7-8 期 evaluate
7. **Cluster 1 parameter sweep parallel test 上限**：per sibling M9 DESIGN §12.3 Open Q 4；max parallel test count 由 PA 仲裁；建議起點每策略 5 個並行 sweep

### 10.2 已知 caveat

1. **採 BIGSERIAL PK 而非 UUID（ADR-0037 Decision 1 原建議 UUID）**：實作便利 + 對齊 V103/V110 範式 + 既有 V### 規範；audit trail / FK 邏輯不變
2. **`variant_count` integer 而非 ADR-0037 Decision 1 `variant_configs_hash text[]`**：簡化 schema；variant config hash 移到應用層 / 走 V103 hypothesis spec_json
3. **engine_mode 不含 paper**：A/B test 限 demo + live_demo + live + replay 跑；paper 失真不採；CHECK constraint 額外 enforce
4. **無 FK to V107 / V110 / V113 / V109 / V111**：cross-1A-β/γ decoupled；應用層 join；schema-level integrity 較弱但避免 cross-sprint race
5. **min_sample_size_per_arm 由 power analysis derive (per §3.5 sibling M9 DESIGN)**：本 spec schema 級存 integer 但不寫 derive 公式；IMPL 期 land；E2 review 必驗不寫 magic number
6. **Materialized view (optional)**：§2.5；IMPL 期 evaluate；不強制 land
7. **Sprint 4+ writer 路徑未在本 spec 範圍**：V108 apply 後立即 0 row；MIT pipeline maturity audit 認列為 Foundation stage；Sprint 4 補 writer 後升 Skeleton

### 10.3 替代設計選項

1. **UUID PK（per ADR-0037 Decision 1 原建議）**：本 spec 採 BIGSERIAL；若 PM 仲裁切替 UUID，§2.1.1 patch test_id type；FK 邏輯不變
2. **engine_mode 含 paper**：本 spec 排除 paper；若 PM 仲裁允許 paper A/B test（不推薦），§2.1.1 CHECK 擴 5 值；不對齊 sibling M9 DESIGN §1.6
3. **不 hypertable ab_assignments**：本 spec hypertable；若 row 量低於預估，IMPL 期可改 regular table；當前預估 ~180k row peak 需 hypertable

---

## §11 風險評估 + 16 原則 / DOC-08 §12 / §四 觸碰

### 11.1 改動風險評級 = **低-中**

| Risk | 評級 | Mitigation |
|---|---|---|
| schema migration 失敗 | 低 | Linux PG empirical dry-run × 2 + sqlx checksum repair SOP（V055/V083/V084 incident precedent）|
| TimescaleDB hypertable + compression + retention 語法不對齊 | 中 | §4.1 Query 4 確認 TimescaleDB extension version + §4.2 Round 1 驗 hypertable 真建立 |
| FK chain 4 target 缺漏（V103 hypotheses / decision_lease / audit_log）| 低-中 | Guard A 強制驗 3 FK target 存在；缺即 RAISE |
| ENUM 6 個 CHECK constraint 漏值 | 低 | Guard C 強制驗 cluster_type/statistical_method/status/assignment_method/msprt_decision/engine_mode 6 個 ENUM 齊全 |
| engine_mode 誤含 paper | 中 | Guard C 額外 RAISE if paper in CHECK；sibling M9 DESIGN §1.6 + §6.2.3 E2 review 重點 |
| Sprint 4 writer 接線延後 | 低 | 3 表 V108 apply 後立即 0 row 屬 Foundation stage 設計預期；MIT pipeline maturity audit 接受 |
| variant Stage 路徑誤實作（variant 繞 Stage）| 中 | sibling M9 DESIGN §4.5 反模式明示；應用層 IMPL 必 invariant check；本 schema 不強制（schema-level 不 enforce 因 cross-table state machine）|
| backward-compat 風險 | 極低 | 全 NEW table，0 ALTER / 0 DROP / 0 RENAME |

### 11.2 16 根原則合規（16/16）

per sibling M9 DESIGN §13 同表（本 V108 schema 100% 對齊 sibling M9 DESIGN spec），不重述。

### 11.3 DOC-08 §12 9 條安全不變量觸碰（0/9）

| 不變量 | 觸碰 | 評估 |
|---|---|---|
| Pre-trade audit/replay 必開 | NO | V108 不改 pre-trade gate |
| Lease 必在執行前 acquired | NO | V108 ab_assignments.lease_id 是 audit reference，不改 lease acquisition 路徑 |
| 執行回報必落 fills 表 | NO | V108 不改 fills 寫入路徑 |
| 風控降級 → engine 自動止血 | NO | V108 不觸風控；fair execution clause 走 Guardian 同 gate |
| Authorization 過期 → cancel_token shutdown | NO | V108 不觸 authorization |
| Mainnet 無 OPENCLAW_ALLOW_MAINNET → spawn 拒 | NO | V108 不觸 mainnet spawn |
| Bybit retCode != 0 → fail-closed 不重試 | NO | V108 不觸 retry |
| Reconciler 對賬差異 → 自動降級 paper | NO | V108 不觸既有 reconciler |
| Operator 角色與 live_reserved 缺一即拒 | NO | V108 不觸 operator auth；ab_tests.created_by 是 audit reference |

### 11.4 §四 5 硬邊界觸碰（0/5）

`execution_state` / `execution_authority` / `live_execution_allowed` / `decision_lease_emitted` / `max_retries=0` 全 0 觸碰。

---

## §12 後續行動（給 PM 派發）

| Action | Owner | Track | Priority |
|---|---|---|---|
| Sign-off 本 V108 full DDL spec（採 operator prompt 字段集對齊 ADR-0037 Decision 1）| PM | Sprint 1A-γ schema prereq closure | P0 |
| PA C9 跑 §4.1 5 條 ssh PG query + 補 7 處 placeholder（§10.1）| PA | Sprint 1A-γ pre-dispatch | P0 |
| Sign-off sibling M9 DESIGN spec（本 V108 spec land 配對 dependency）| PM | Sprint 1A-γ | P0 |
| IMPL kickoff（Sprint 1A-γ 啟動）：派 E1 寫 V108.sql + Linux PG dry-run × 2 + E2/E4 + restart_all 部署 | PM | Sprint 1A-γ | P1 |
| Sprint 3 mSPRT + AVI validation harness 1000+ simulation IMPL（per sibling M9 DESIGN §3.9 + AC-7）| MIT + E4 (Sprint 3) | Sprint 3 | P2 |
| Sprint 4 read-only logging 上線（Cluster 1 parameter_sweep + Cluster 4 exit_logic）| E1 (Sprint 4) | Sprint 4 | P2 |
| Sprint 4 first Live A/B 啟用 gate 仲裁（v5.8 §10.5 4+1 條 P0 precondition 通過後）| PM (Sprint 4) | Sprint 4 | P2 |
| Healthcheck 加 [56-59] for V108 三表 first-row + freshness + status distribution（Sprint 4 整合）| E1 (Sprint 4) | Sprint 4 | P2 |

### 12.1 Sprint 1A-γ schema prereq closure 標誌

本 V108 spec PM sign-off + sibling M9 DESIGN spec PM sign-off + PA C9 dry-run 補資料 land + Open Q 1 (V107 type) 仲裁完成 → Sprint 1A-γ V108 schema prereq 解除 → IMPL kickoff 派 E1。

---

## §13 關鍵文件指針（後續 IMPL agent / PM / E2 / E4 必讀）

### Parent specs

- **ADR-0037**：`srv/docs/adr/0037-m9-ab-framework-and-statistical-methodology.md`（5 Decisions ADR 權威；本 spec 100% 對齊）
- **sibling M9 DESIGN spec**：`srv/docs/execution_plan/2026-05-21--m9_ab_framework_design_spec.md`（同日 land；本 V108 為其 schema 對應）
- **v5.8 execution plan**：`srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md` §2 M9 (line 319-355) + §9 V108 schema (line 789-791)
- **PA dispatch consolidation**：`srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md` §Sprint 1A-γ (line 146-157) + §QA/QC reconcile (line 368)

### Sibling V### specs

- **V103/V104 spec**（hypotheses FK target + 範式參考）：`srv/docs/execution_plan/2026-05-21--v103_v104_earn_hypotheses_schema_spec.md`
- **V110 M6 reward weight spec**（Cluster 3 risk profile ref + 範式參考）：`srv/docs/execution_plan/2026-05-21--v110_m6_reward_weight_history_schema_spec.md`
- **V094 spec**（Guard A/B/C + Linux PG dry-run 範式）：`srv/docs/execution_plan/2026-05-15--v094_close_maker_first_audit_schema_spec.md`

### Amendments

- **AMD-2026-05-15-01 Stage 0R-4 framework**：`srv/docs/governance_dev/amendments/2026-05-15--AMD-2026-05-15-01-canary-rebase-replay-preflight-demo-micro-canary.md`（sibling M9 DESIGN §4 variant Stage 路徑 100% 引用）
- **AMD-2026-05-09-03 Strategist Wide-Adjustment**：`srv/docs/governance_dev/amendments/2026-05-09--strategist_wide_adjustment_skill.md`（sibling M9 DESIGN §2.3 Cluster 3 RuntimeMaxEnvelope 對齊）

### ADR cross-ref

- **ADR-0008 Decision Lease state machine**：`srv/docs/adr/0008-decision-lease-state-machine.md`（§2.2 ab_assignments.lease_id 對齊）
- **ADR-0021 Alpha Source Architecture Upgrade**：`srv/docs/adr/0021-alpha-source-architecture-upgrade.md`（sibling M9 DESIGN §2.2 Cluster 2 R-1 Alpha Surface Bundle）
- **ADR-0022 Strategist Cap**：`srv/docs/adr/0022-strategist-cap.md`（sibling M9 DESIGN §5 fair execution clause）
- **ADR-0026 Direct Exploit Bypass CPCV**：`srv/docs/adr/0026-direct-exploit-bypass-cpcv.md`（sibling M9 DESIGN §2.2 Cluster 2 Stage 0R replay CPCV）
- **ADR-0034 M1 Decision Lease LAL**：`srv/docs/adr/0034-decision-lease-layered-approval-lal.md`（§2.1 lal_level 對齊）
- **ADR-0036 M8 anomaly + M10 Tier D blacklist**：`srv/docs/adr/0036-m8-anomaly-detection-and-m10-tier-d-model-blacklist.md`（sibling M9 DESIGN §3.8 反模式 (e) HMM/GARCH 適用 M9）
- **ADR-0038 M11 continuous counterfactual replay**：M9 variant outcome 對齊 M11 nightly replay（sibling M9 DESIGN §8）

### Tooling cross-ref

- **schema_guard_template**：`srv/sql/migrations/templates/schema_guard_template.sql`
- **repair binary**：`srv/rust/openclaw_engine/src/bin/repair_migration_checksum.rs`
- **V055 5-round loop + sqlx hash drift incident lessons**：`memory/feedback_v_migration_pg_dry_run.md` + `memory/project_2026_05_02_p0_sqlx_hash_drift.md`
- **CLAUDE.md §Data Migrations**：`srv/CLAUDE.md`
- **MIT 5.21 v58 audit Risk 1+2**：`srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-21--v58_executability_audit.md`

### Skill cross-ref

- **`srv/.claude/skills/db-schema-design-financial-time-series`**：本 spec hypertable + chunk + partial index + Guard A/B/C 規範對齊
- **`srv/.claude/skills/ml-pipeline-maturity-audit`**：V108 apply 後 Foundation stage；Sprint 4+ writer 接線後升 Skeleton/Shadow
- **`srv/.claude/skills/feature-engineering-protocol`**：A/B test variant config 必對齊 leak-free shift(1) 紀律
- **`srv/.claude/skills/time-series-cv-protocol`**：min_sample_size derive + Embargo 規範對齊 sibling M9 DESIGN §3.5

---

## §14 審計記錄

| Source agent | Role | Audit pattern coverage |
|---|---|---|
| MIT 5.21 v58 audit | 起草者 | Risk 1 (V108 placeholder) closure / Risk 2 (M9 mSPRT 算法 spec 缺) closure / pipeline maturity 5 階段 / Guard A/B/C / Linux PG dry-run mandate |
| MIT sibling M9 DESIGN spec (本 V108 spec 配對) | 起草者 | 4 cluster taxonomy / mSPRT+AVI+Bonferroni / variant Stage 路徑 / fair execution clause / preregistration / hash algorithm / M11 cross-ref / M7 integration / 7 AC / IMPL phase / Open Q × 5 |
| PA Sprint 1A-γ dispatch consolidation (2026-05-21) | 範式參考 | Sprint 1A-γ V108/V105/V109/V111 並行 schedule + QA/QC reconcile 對應 |
| PA V103/V104 spec + V110 spec (2026-05-21) | 範式參考 | Guard A/B/C 完整 template / Linux PG dry-run × 2 round protocol / sqlx checksum repair SOP / §11 風險評估 + 16 原則 + DOC-08 §12 / §四 |
| PA Wave 2 Track A2 v094 spec (2026-05-15) | 範式參考 | empirical INSERT test boundary cases / Guard 設計理念 / §12 caveat 列法 / E2 review 重點 |
| ADR-0037 (2026-05-21 Proposed) | 設計權威 | 5 Decisions：schema 草案 / variant Stage 路徑 / 4 cluster / mSPRT+AVI+Bonferroni / fair execution clause |
| db-schema-design-financial-time-series skill | DB schema audit | hypertable + chunk + compression + retention 設計 / hot-path partial index / engine_mode CHECK 4 值（不含 paper）/ Guard A/B/C 規範 |
| ml-pipeline-maturity-audit skill | Pipeline stage 評級 | V108 apply 後立即 0 row 屬 Foundation stage；Sprint 4 read-only logging 期 first writer row 升 Skeleton；Sprint 7-8 manual A/B 期升 Shadow；Y2 auto-test 升 Canary → Production |
| feature-engineering-protocol skill | Leakage 防範 | A/B test variant config 必對齊 leak-free shift(1) 紀律（sibling M9 DESIGN §2.1.1）；CPCV 紀律（sibling M9 DESIGN §2.2.1）|
| time-series-cv-protocol skill | CV 設計 | mSPRT min_sample_size 必從 power analysis derive（sibling M9 DESIGN §3.5）；block bootstrap 5-10d block 配套（§3.6）|
| data-drift-detection skill | Drift 偵測 | Cluster 3 risk profile tail event drift 偵測（sibling M9 DESIGN §2.3.1）|

### 14.1 待 PA dispatch 前補充

- [ ] PA C9 dry-run 5 條 ssh query 結果（§4.1）
- [x] V107 final schema type UUID vs BIGINT 確認（§10.1 #2）— **RESOLVED 2026-05-22 = BIGINT bigserial per V107.sql:81-87；spec 已 patch**
- [ ] TimescaleDB extension version 確認（§10.1 #3）
- [ ] UUID extension 名稱確認（§10.1 #4）
- [ ] mSPRT AVI closed-form 公式 V108 IMPL 期決策（§10.1 #5）
- [ ] Bonferroni vs FDR ENUM 擴展決策（§10.1 #6）
- [ ] Cluster 1 max parallel test count 仲裁（§10.1 #7）

---

**END V108 spec full DDL v1（Sprint 1A-γ；對齊 ADR-0037 5 Decisions + sibling M9 DESIGN spec；待 PA C9 dry-run + PM sign-off → SPEC-FINAL）**
