---
spec: V112 — M1 Decision Lease LAL Tiers (config + assignments + eligibility MV)
date: 2026-05-21
author: MIT (full DDL spec; lifts placeholder; replaces SPEC-PLACEHOLDER v0)
phase: v5.8 Sprint 1A-β schema prerequisite CRITICAL deliverable
status: SPEC-FULL-V0 (MIT 起草;待 PA C9 Linux PG dry-run 實測補資料 + Sprint 1A-β reviewer 對齊後 SPEC-FINAL)
sprint: Sprint 1A-β (DESIGN phase; IMPL 後續 sprint)
size estimate: 130-180 LOC SQL (2 tables + 1 materialized view + 3 indexes + 5 INSERT seed rows + Guard A/C + retention deferred) + 70-110 hr E1 IMPL (含 Linux PG dry-run x 2 round + healthcheck wiring deferred to Sprint 1B)
depend on:
  - V099/V100 (Decision Lease state machine baseline; lease_id FK source — assumed land Sprint 1A-α per PA dispatch consolidation)
  - V113 (M7 decay_signals; no_incident_check_v113_ref FK source — assumed land before V112 per PA cross-V### dep graph)
  - V098 (governance.audit_log; assigned_by audit cross-ref;非 FK)
depended by:
  - V109 (M8 anomaly) — γ track:M8 → LAL tier_change_reason='health_degraded' demote (cross-ref query 非 FK)
  - M3 V106 (HEALTH_DEGRADED → LAL 1 reparam halt) — cross-ref query 非 FK
parent specs:
  - srv/docs/adr/0034-decision-lease-layered-approval-lal.md (authoritative LAL 0-4 semantic source of truth)
  - srv/docs/execution_plan/2026-05-21--m1_lal_layered_approval_lease_design_spec.md (697 line M1 module design spec; §11 cross-V### + §6 反向 attack mitigation)
  - srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md §2 M1 Decision Lease LAL module
  - srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md §6 cross-V### dependency graph
mirror precedent:
  - srv/docs/execution_plan/2026-05-21--v103_v104_earn_hypotheses_schema_spec.md (format reference; 940 line baseline; 14 section structure)
  - srv/docs/execution_plan/2026-05-21--v106_m3_health_observations_schema_spec.md (sister V### spec same Sprint 1A-β batch)
  - srv/docs/execution_plan/2026-05-21--v103_v104_linux_pg_dry_run.md (Linux PG dry-run protocol reference)
  - srv/sql/migrations/V094__fills_close_maker_audit.sql (Guard A/B/C + NOT VALID CHECK + partial index 範式)
  - srv/sql/migrations/templates/schema_guard_template.sql (Guard A/B/C template)
scope: design / spec only — 不寫 V112.sql 實檔,不在 Mac 跑 SQL,不改 Rust/Python writer,不執行 PG,不擴張到 V107/V113 schema 細節 (placeholder FK 標)
---

# V112 M1 Decision Lease LAL Tiers Schema Migration Spec (FULL DDL)

## §0 TL;DR

- **V112 新增 2 個 regular table on `governance` schema**:`governance.lease_lal_tiers`(per-LAL-level config / 5 row seed) + `governance.lease_lal_assignments`(per-lease LAL tier assignment history / append-only audit ledger)。
- **加 1 個 materialized view**:`governance.mv_lease_lal_eligibility`(per (strategy_id, symbol) latest LAL tier + 90d incident-free check;`REFRESH MATERIALIZED VIEW CONCURRENTLY` 後續 cron Sprint 1B 跑)。
- **LAL 0-4 語義方向以 ADR-0034 為 single source of truth**(數字越大越嚴):
  - LAL 0 = `LAL_0_AUTO`:per-fill / always autonomous(風險最低 / auto-approve allowed;Guardian fast path)
  - LAL 1 = `LAL_1_LIGHT_REVIEW`:intra-strategy reparam(Stage 4 + 30d stable 後 auto-approve;6 hard gate)
  - LAL 2 = `LAL_2_FULL_REVIEW`:cross-strategy reweight(Y2 gate + Console opt-in)
  - LAL 3 = `LAL_3_OPERATOR_APPROVAL`:new strategy promotion(**永遠 operator manual approval**)
  - LAL 4 = `LAL_4_OPERATOR_ATTESTATION`:capital structure / venue change(**永遠 operator manual attestation + 0 clawback after attest**)
- **⚠️ V112 placeholder v0 既有錯誤已修正**:placeholder §1.1 line 34 寫「LAL 0 = full manual approval / LAL 4 = bypass」與 ADR-0034 line 41 + line 137-143 對齊矩陣**反向**;本 spec full DDL 採 ADR-0034 為準。
- **2 表均 regular table**(非 hypertable):`lease_lal_tiers` 5 row 固定 config / `lease_lal_assignments` 預計 ≤ 5k row/yr(per-lease assign + 偶發 tier change);無時序壓力。
- **5 audit field** per V103 EXTEND 範式:`created_by` / `created_at` / `updated_by` / `updated_at` / `source_version`。
- **engine_mode CHECK 5 值齊全**(paper / demo / live_demo / live / replay);training filter 必含 `IN ('live','live_demo')`(per CLAUDE.md §Data + MIT memory baseline);`replay` 為 M11 replay engine 寫入時的 mode tag。
- **Hot-path indexes 3 個**:lease_id / assigned_at DESC / (tier_level, assigned_at DESC)。
- **Linux PG empirical dry-run mandatory**(per CLAUDE.md §Data, Migrations, And Validation + V055 5-round loop precedent)。

---

## §1 Context + 為什麼

### 1.1 V112 placeholder v0 反向錯誤修正(CRITICAL)

V112 placeholder v0(本檔前一版 frontmatter)line 34 寫:

> 「5 級 0-4:LAL 0 = full manual approval / LAL 1 = governance auto-approve / LAL 2 = governance bypass-with-audit / LAL 3 = full auto / LAL 4 = bypass even audit (emergency only)」

**此語義與 ADR-0034 對齊矩陣完全反向**:

ADR-0034 line 41:「LAL 數字越大越嚴」
ADR-0034 line 137-143 對齊矩陣:
- LAL 0(per-fill)→ always Guardian auto(風險最低)
- LAL 4(capital structure / venue change)→ **never auto, always operator approve**(風險最高)

placeholder v0 的反向描述源於 PA placeholder dispatch 階段未深讀 ADR-0034;本 full DDL spec **以 ADR-0034 為單一真實來源**(per CLAUDE.md §五:「Accepted decisions in `docs/adr/*`」)。

下游所有 sub-agent 派工 / IMPL writer / consumer 必依本 spec(對齊 ADR-0034)語義方向,placeholder v0 之文字廢棄。

### 1.2 v5.8 §2 M1 module + ADR-0034 driver

v5.8 §2 M1 Decision Lease LAL module 列:

- LAL = Lease Approval Level(per ADR-0034 + CR-2:rename from Tier 以避 AMD-2026-05-15-01 Stage 0R-4 字面碰撞)
- 5 級 0-4 對應 5 種 approval depth(數字越大越嚴)
- per-strategy LAL config 由 6 條 hard gate(per ADR-0034 §Decision 5)決定能否升級至 auto-approve

ADR-0034 對齊矩陣明示:

| LAL | Approval depth | Compatible Stages | Auto-approve eligibility |
|---|---|---|---|
| **LAL 0** | per-fill | Stage 0 / 0R / 1 / 2 / 3 / 4 | always(既有 Guardian auto)|
| **LAL 1** | intra-strategy reparam | Stage 4 only(30d stable) | yes after eligibility |
| **LAL 2** | cross-strategy reweight | Stage 4 only(Y2 gate) | Y2 only + Console opt-in |
| **LAL 3** | new strategy promotion | n/a(gate to Stage 0R+) | **never auto** |
| **LAL 4** | capital structure / venue change | n/a(gate to ADR-debt) | **never auto** |

### 1.3 為什麼 schema 用 `governance` schema(非 `learning`)

per ADR-0034 + M1 LAL design spec §3 state machine:
- LAL tier 是 governance object(approval policy enforcement),非 learning observation
- 既有 `governance.audit_log` / `governance.unblock_candidates` / `governance.canary_stage_metric_seed` 同 schema
- 避 schema 混淆(learning schema 主要為 ML feature / training / shadow):per CLAUDE.md §二 原則 2「讀寫分離;research, GUI, and learning are mostly read-only」

### 1.4 Cross-V### 影響

| 下游 | M1 LAL 觸發路徑 | 是否 FK |
|---|---|---|
| **V109 (M8 anomaly)** | M8 emit → 寫 `lease_lal_assignments.tier_change_reason='health_degraded'` demote(γ track) | 否(cross-ref;assigned_by writer 寫) |
| **V106 (M3 health)** | M3 `HEALTH_DEGRADED` → LAL 1 reparam halt(per ADR-0034 + v5.8 §2 M3 line 140)| 否(cross-ref query)|
| **V107 (M11 replay)** | M11 replay 重放 LAL gate decision → reproducibility check | 否(cross-ref query)|
| **V113 (M7 decay_signals)** | LAL eligibility check `no_incident_check_v113_ref` 查 V113 90d incident-free | **placeholder FK**(V113 land 後啟用)|

### 1.5 不在本 spec 範圍

- ❌ V112.sql 實檔寫作(E1 IMPL 工作)
- ❌ Mac 跑 V112 SQL(必 Linux PG empirical)
- ❌ Rust LAL gate code(`rust/openclaw_engine/src/governance/lal_gate.rs`;E1 IMPL 工作 Sprint 4+)
- ❌ Python LAL toggle GUI(`control_api_v1` endpoint + `console_assets` panel;Sprint 4+)
- ❌ healthcheck wiring(Sprint 1B 加 `check_lal_assignments_writer()`)
- ❌ Console toggle 2FA / Slack notification IMPL(per ADR-0034 Decision 4 + 5;Sprint 4-8 IMPL)
- ❌ V107(M11 replay) / V109(M8 anomaly) / V113(M7 decay) schema 設計細節(各自 spec 寫)
- ❌ M5 / M9 / M10 schema(各自 V### 自寫)

---

## §2 Schema Design

### 2.1 Table 1: `governance.lease_lal_tiers`(config)

#### 2.1.1 表定義

```sql
CREATE TABLE IF NOT EXISTS governance.lease_lal_tiers (
    tier_level                  INT PRIMARY KEY
                                CHECK (tier_level BETWEEN 0 AND 4),
    tier_name                   TEXT NOT NULL UNIQUE
                                CHECK (tier_name IN (
                                    'LAL_0_AUTO',
                                    'LAL_1_LIGHT_REVIEW',
                                    'LAL_2_FULL_REVIEW',
                                    'LAL_3_OPERATOR_APPROVAL',
                                    'LAL_4_OPERATOR_ATTESTATION'
                                )),
    auto_approve                BOOLEAN NOT NULL,
    approval_quorum             INT NOT NULL
                                CHECK (approval_quorum >= 0),
    clawback_ttl_sec            INT NOT NULL
                                CHECK (clawback_ttl_sec >= 0),
    cohort_min_n                INT NOT NULL
                                CHECK (cohort_min_n >= 0),
    resource_quota_cpu_pct      NUMERIC(5,2)
                                CHECK (resource_quota_cpu_pct IS NULL OR
                                       (resource_quota_cpu_pct > 0 AND resource_quota_cpu_pct <= 100)),
    risk_envelope_usdt          NUMERIC(20,8)
                                CHECK (risk_envelope_usdt IS NULL OR risk_envelope_usdt > 0),
    human_final_review          BOOLEAN NOT NULL,
    description                 TEXT,
    created_by                  TEXT NOT NULL DEFAULT 'system_seed',
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by                  TEXT,
    updated_at                  TIMESTAMPTZ,
    source_version              TEXT NOT NULL DEFAULT 'V112'
);
```

#### 2.1.2 Column 設計理由

| Column | Type | NULL | 設計理由 |
|---|---|---|---|
| `tier_level` | INT PRIMARY KEY | NOT NULL | 0-4 整數(per ADR-0034);PK 唯一鍵;CHECK BETWEEN 防越界 |
| `tier_name` | TEXT + CHECK 5 值 + UNIQUE | NOT NULL | per operator prompt 命名:LAL_0_AUTO / LAL_1_LIGHT_REVIEW / LAL_2_FULL_REVIEW / LAL_3_OPERATOR_APPROVAL / LAL_4_OPERATOR_ATTESTATION;UNIQUE 防 seed 重複 |
| `auto_approve` | BOOLEAN | NOT NULL | LAL 0/1/2 = true(auto-approve allowed);LAL 3/4 = false(per ADR-0034 對齊矩陣) |
| `approval_quorum` | INT | NOT NULL | 需要的 operator 簽署數;LAL 0 = 0(no human)/ LAL 3 = 1 operator / LAL 4 = 1 operator + 2FA attest |
| `clawback_ttl_sec` | INT | NOT NULL | clawback 窗口秒數;LAL 0 = 60s(快速 auto-rollback)/ LAL 3 = 3600s(operator 反悔窗口)/ LAL 4 = 0(**不可 clawback after attestation**;per operator prompt + ADR-0034 Decision 5)|
| `cohort_min_n` | INT | NOT NULL | Tier 升降需 cohort sample N;對齊 ADR-0034 §Decision 3 rolling 30d ≥ 30 sample |
| `resource_quota_cpu_pct` | NUMERIC(5,2) | NULLABLE | 該 tier 可使用的 CPU% 上限;NULL = 不限;CHECK 0-100 |
| `risk_envelope_usdt` | NUMERIC(20,8) | NULLABLE | 該 tier 可影響的 USDT 風險上限(per AMD-2026-05-09-03 RuntimeMaxEnvelope);NULL = 不限 |
| `human_final_review` | BOOLEAN | NOT NULL | per CLAUDE.md §二 第 5 條「human final review」優先序;LAL 3/4 = true(必 review);LAL 0/1/2 = false(post-hoc audit only)|
| `description` | TEXT | NULLABLE | 業務語意描述(audit trail 用) |
| 5 audit field | per V103 EXTEND | mixed | created_by / created_at / updated_by / updated_at / source_version |

#### 2.1.3 5 row seed INSERT

```sql
INSERT INTO governance.lease_lal_tiers
    (tier_level, tier_name, auto_approve, approval_quorum, clawback_ttl_sec,
     cohort_min_n, resource_quota_cpu_pct, risk_envelope_usdt, human_final_review,
     description, created_by, source_version)
VALUES
    (0, 'LAL_0_AUTO', true, 0, 60,
     0, 80.00, 5000.00000000, false,
     'Per-fill autonomous; always Guardian fast path; per ADR-0034 對齊矩陣 LAL 0',
     'system_seed', 'V112'),
    (1, 'LAL_1_LIGHT_REVIEW', true, 0, 300,
     30, 60.00, 25000.00000000, false,
     'Intra-strategy reparam; Stage 4 + 30d stable + 6 hard gate; per ADR-0034 對齊矩陣 LAL 1',
     'system_seed', 'V112'),
    (2, 'LAL_2_FULL_REVIEW', true, 0, 600,
     50, 40.00, 100000.00000000, false,
     'Cross-strategy reweight; Y2 gate + Console opt-in + 6 hard gate; per ADR-0034 對齊矩陣 LAL 2',
     'system_seed', 'V112'),
    (3, 'LAL_3_OPERATOR_APPROVAL', false, 1, 3600,
     100, 20.00, NULL, true,
     'New strategy promotion; always operator manual approve; per ADR-0034 對齊矩陣 LAL 3',
     'system_seed', 'V112'),
    (4, 'LAL_4_OPERATOR_ATTESTATION', false, 1, 0,
     200, 10.00, NULL, true,
     'Capital structure / venue change; always operator manual attest + 2FA; clawback 0 (immutable after attest); per ADR-0034 對齊矩陣 LAL 4',
     'system_seed', 'V112')
ON CONFLICT (tier_level) DO NOTHING;
```

**理由**:
- LAL 0:60s clawback(Guardian auto-rollback 窗口)/ CPU 80%(per-fill 路徑大頭)/ 5000 USDT(per-fill risk envelope)
- LAL 1:300s clawback(reparam 反悔窗口)/ 60% / 25000 USDT(intra-strategy reparam 上限)
- LAL 2:600s clawback / 40% / 100000 USDT(cross-strategy reweight 上限)
- LAL 3:3600s clawback(operator 反悔 1hr)/ 20% / risk_envelope NULL(strategy promotion 不設 USDT 上限,走 Stage gate)
- LAL 4:**0 clawback**(per operator prompt;capital structure 不可逆)/ 10% / risk_envelope NULL

`ON CONFLICT (tier_level) DO NOTHING`:idempotent;重跑 V112 不 double insert。

#### 2.1.4 row 量級

- 5 row 固定 config;不擴張
- regular table;無 hypertable / retention 需求

### 2.2 Table 2: `governance.lease_lal_assignments`(history)

#### 2.2.1 表定義

```sql
CREATE TABLE IF NOT EXISTS governance.lease_lal_assignments (
    id                              BIGSERIAL PRIMARY KEY,
    lease_id                        UUID NOT NULL,
    tier_level                      INT NOT NULL
                                    REFERENCES governance.lease_lal_tiers(tier_level),
    assigned_by                     TEXT NOT NULL,
    assigned_at                     TIMESTAMPTZ NOT NULL DEFAULT now(),
    prev_tier_level                 INT
                                    REFERENCES governance.lease_lal_tiers(tier_level),
    tier_change_reason              TEXT
                                    CHECK (tier_change_reason IS NULL OR tier_change_reason IN (
                                        'auto',
                                        'manual',
                                        'health_degraded',
                                        'decay_signal',
                                        'operator_override',
                                        'initial_seed'
                                    )),
    no_incident_check_v113_ref      BIGINT,
    no_incident_check_pass          BOOLEAN,
    no_incident_check_window_days   INT NOT NULL DEFAULT 90,
    state_machine_step              INT NOT NULL
                                    CHECK (state_machine_step BETWEEN 0 AND 8),
    clawback_executed               BOOLEAN NOT NULL DEFAULT FALSE,
    clawback_at                     TIMESTAMPTZ,
    engine_mode                     TEXT NOT NULL
                                    CHECK (engine_mode IN ('paper','demo','live_demo','live','replay')),
    evidence_json                   JSONB,
    created_by                      TEXT NOT NULL DEFAULT 'lal_gate',
    created_at                      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by                      TEXT,
    updated_at                      TIMESTAMPTZ,
    source_version                  TEXT NOT NULL DEFAULT 'V112',
    CONSTRAINT chk_clawback_consistency CHECK (
        (clawback_executed = FALSE AND clawback_at IS NULL) OR
        (clawback_executed = TRUE AND clawback_at IS NOT NULL)
    ),
    CONSTRAINT chk_no_incident_consistency CHECK (
        (no_incident_check_v113_ref IS NULL AND no_incident_check_pass IS NULL) OR
        (no_incident_check_v113_ref IS NOT NULL AND no_incident_check_pass IS NOT NULL)
    )
);
```

#### 2.2.2 Column 設計理由

| Column | Type | NULL | 設計理由 |
|---|---|---|---|
| `id` | BIGSERIAL PK | NOT NULL | sequential audit ID |
| `lease_id` | UUID | NOT NULL | per ADR-0008 lease_id;FK ref V099/V100 lease 表(本 spec 不寫 FK constraint,因 V099/V100 schema 由 PA 同 Sprint 1A-α 派工待 land;cross-ref query 走 application layer)|
| `tier_level` | INT FK → `lease_lal_tiers` | NOT NULL | 該 lease 當下 LAL tier(0-4) |
| `assigned_by` | TEXT | NOT NULL | actor:operator id / agent id / 'system' / 'lal_gate' / 'health_monitor' / 'm8_anomaly_detector' |
| `assigned_at` | TIMESTAMPTZ DEFAULT now() | NOT NULL | assign 時間 |
| `prev_tier_level` | INT FK → `lease_lal_tiers` | NULLABLE | 前一個 tier(initial assign 時 NULL) |
| `tier_change_reason` | TEXT + CHECK 6 值 | NULLABLE | auto / manual / health_degraded / decay_signal / operator_override / initial_seed;initial assign 時可 'initial_seed' |
| `no_incident_check_v113_ref` | BIGINT | NULLABLE | **placeholder FK** to V113 `decay_signals.id`(V113 land 後 ALTER TABLE ADD CONSTRAINT FK;本 V112 不寫 FK constraint 因 V113 schema 未 land) |
| `no_incident_check_pass` | BOOLEAN | NULLABLE | 90d incident-free 檢查結果;NULL = 未檢查;true = pass(eligibility OK)/ false = fail(triggered downgrade) |
| `no_incident_check_window_days` | INT DEFAULT 90 | NOT NULL | per ADR-0034 90d eligibility |
| `state_machine_step` | INT + CHECK 0-8 | NOT NULL | per M1 LAL design spec §3 state machine(emit / evaluate / approve / sign / settle / clawback / archive / error / replay) |
| `clawback_executed` | BOOLEAN DEFAULT FALSE | NOT NULL | clawback 是否執行 |
| `clawback_at` | TIMESTAMPTZ | NULLABLE | clawback 時間;chk_clawback_consistency CHECK 保 clawback_executed=TRUE 必有 clawback_at |
| `engine_mode` | TEXT + CHECK 5 值 | NOT NULL | paper / demo / live_demo / live / **replay**(M11 replay engine 寫入時的 mode tag;區分 live 真實寫入 vs replay 重放) |
| `evidence_json` | JSONB | NULLABLE | 富 context:6 hard gate 評估快照、operator approval source(Console / Slack)、2FA result、Slack notification ID |
| 5 audit field | per V103 EXTEND | mixed | created_by / created_at / updated_by / updated_at / source_version |

#### 2.2.3 2 個 CHECK constraint 理由

- `chk_clawback_consistency`:防 `clawback_executed=TRUE` 但 `clawback_at=NULL`(audit trail 不完整)/ 或 `clawback_executed=FALSE` 但 `clawback_at NOT NULL`(語意不一致)
- `chk_no_incident_consistency`:防 `no_incident_check_v113_ref` 與 `no_incident_check_pass` 一致(同時 NULL 或同時 NOT NULL);避免 ref ID 有但 pass 沒填(audit 不完整)

#### 2.2.4 為什麼 engine_mode 5 值(含 'replay')

per ADR-0038 M11 replay 設計:
- M11 nightly replay 透過 replay engine 重放 lease decision 驗 reproducibility
- replay 寫入 `lease_lal_assignments` 必標 `engine_mode='replay'` 區分 live 真實 assign
- 訓練 filter 仍 `IN ('live','live_demo')`(per CLAUDE.md §二 + MIT memory baseline);replay rows 不混 ML training

CLAUDE.md §Data section 列出的 4 值(paper/demo/live_demo/live)是 baseline;M11 replay 屬於 M1 LAL 之外的 module 擴張,需於本 V112 schema 顯式涵蓋 'replay' 否則 M11 寫入會 RAISE。

#### 2.2.5 row 量級估算

- 5 strategy × 25 symbol × per-strategy/symbol ~1 assign/day = 125 row/day
- tier change 罕見(per ADR-0034 + ADR-0008:tier change 走 6 hard gate evaluation,~per-strategy 1-2/month)~10 row/month
- replay rows(per ADR-0038 nightly replay):假設 5% live 比例 replay:~6 row/day
- 合計 ~125 + 10 + 6 = ~141 row/day = ~51k row/yr → ~50 GB/yr(每 row ~250 byte)? 不對,實則 ~12.5 MB/yr(每 row ~250 byte × 51k row = 12.75 MB)

regular table 可承載;無 hypertable 需求。

### 2.3 Materialized View: `governance.mv_lease_lal_eligibility`

#### 2.3.1 MV 定義

```sql
CREATE MATERIALIZED VIEW IF NOT EXISTS governance.mv_lease_lal_eligibility AS
WITH latest_per_lease AS (
    SELECT DISTINCT ON (lease_id)
        lease_id,
        tier_level AS current_tier_level,
        assigned_at AS last_assigned_at,
        no_incident_check_pass AS last_incident_free_pass,
        no_incident_check_window_days,
        engine_mode
    FROM governance.lease_lal_assignments
    WHERE engine_mode IN ('live', 'live_demo')
    ORDER BY lease_id, assigned_at DESC
),
incident_free_90d AS (
    SELECT
        lease_id,
        BOOL_AND(no_incident_check_pass) FILTER (WHERE no_incident_check_pass IS NOT NULL) AS all_checks_pass_90d,
        COUNT(*) FILTER (WHERE no_incident_check_pass = false) AS incident_count_90d
    FROM governance.lease_lal_assignments
    WHERE engine_mode IN ('live', 'live_demo')
      AND assigned_at > now() - INTERVAL '90 days'
    GROUP BY lease_id
)
SELECT
    l.lease_id,
    l.current_tier_level,
    t.tier_name AS current_tier_name,
    t.auto_approve AS current_auto_approve,
    t.human_final_review AS current_human_final_review,
    l.last_assigned_at,
    l.last_incident_free_pass,
    i.all_checks_pass_90d,
    COALESCE(i.incident_count_90d, 0) AS incident_count_90d,
    CASE
        WHEN i.incident_count_90d IS NULL THEN 'eligible_no_history'
        WHEN i.incident_count_90d = 0 THEN 'eligible_clean_90d'
        ELSE 'ineligible_incident_in_90d'
    END AS eligibility_status,
    l.engine_mode,
    now() AS refreshed_at
FROM latest_per_lease l
LEFT JOIN governance.lease_lal_tiers t ON l.current_tier_level = t.tier_level
LEFT JOIN incident_free_90d i ON l.lease_id = i.lease_id;

CREATE UNIQUE INDEX IF NOT EXISTS mv_lease_lal_eligibility_pkey
    ON governance.mv_lease_lal_eligibility (lease_id);
```

#### 2.3.2 MV 設計理由

- **per-lease latest tier**:`DISTINCT ON (lease_id)` + `ORDER BY assigned_at DESC` 取每 lease 最新 tier
- **90d incident-free 聚合**:`BOOL_AND(no_incident_check_pass) FILTER (...)` + `COUNT(*) FILTER (WHERE pass=false)` 雙路檢查
- **eligibility_status** 3 值 ENUM(CASE expression):`eligible_no_history` / `eligible_clean_90d` / `ineligible_incident_in_90d`
- **UNIQUE INDEX on lease_id**:支援 `REFRESH MATERIALIZED VIEW CONCURRENTLY`(非 blocking refresh;per PG MV best practice)
- **engine_mode filter `IN ('live', 'live_demo')`**:per CLAUDE.md §二 + MIT memory baseline;replay rows 不入 eligibility 評估

#### 2.3.3 Refresh 策略

```sql
-- Sprint 1B+ 加 cron(本 spec 不含)
REFRESH MATERIALIZED VIEW CONCURRENTLY governance.mv_lease_lal_eligibility;
```

- Refresh 頻率:hourly(per LAL 1 reparam evaluation cadence)
- CONCURRENTLY:非 blocking,但需 UNIQUE INDEX(已建)

#### 2.3.4 為什麼用 MV 而非 view

- view 每次 query 都跑完整 aggregation(per ~51k row/yr 不算大但 90d window scan 對 hot path 不友)
- MV 預計算結果存表,query 直接 SELECT(<1ms)
- refresh cost 在 cron 時段集中

---

## §3 Index Strategy

### 3.1 Hot-path query → index map

| Query pattern | 命中 index | 範例 SQL |
|---|---|---|
| per-lease tier history | `idx_lal_lease_id` | `SELECT * FROM governance.lease_lal_assignments WHERE lease_id=$1 ORDER BY assigned_at DESC` |
| recent assignments | `idx_lal_assigned_at` | `SELECT * FROM governance.lease_lal_assignments ORDER BY assigned_at DESC LIMIT 100` |
| per-tier audit | `idx_lal_tier_assigned` | `SELECT * FROM governance.lease_lal_assignments WHERE tier_level=$1 ORDER BY assigned_at DESC` |

### 3.2 Index DDL

```sql
-- 主要 hot-path: per-lease history lookup
CREATE INDEX IF NOT EXISTS idx_lal_lease_id
    ON governance.lease_lal_assignments (lease_id);

-- Recent assignments timeline
CREATE INDEX IF NOT EXISTS idx_lal_assigned_at
    ON governance.lease_lal_assignments (assigned_at DESC);

-- per-tier audit
CREATE INDEX IF NOT EXISTS idx_lal_tier_assigned
    ON governance.lease_lal_assignments (tier_level, assigned_at DESC);
```

### 3.3 為什麼不用 CONCURRENTLY

- `lease_lal_assignments` 表 Sprint 1A-β land 時為空 → CONCURRENTLY 沒必要(本 spec greenfield)
- `IF NOT EXISTS` 已 idempotent
- 若 Sprint 1B+ row 累積後需新 index,屆時 CONCURRENTLY

### 3.4 為什麼不加 `(engine_mode, assigned_at)` partial index

engine_mode CHECK 5 值 + 預期 `IN ('live','live_demo')` filter 在 query 中常見;但 cardinality 太低(5 值)→ index selectivity 不佳;PG 會用 bitmap scan;不需顯式 index。

---

## §4 Guard A / B / C(per CLAUDE.md §Data, Migrations, And Validation + V094 mirror)

### 4.1 Guard A — table existence + 既有 schema 對齊驗證

```sql
-- ============================================================
-- Guard A: V112 預檢 — 若 governance.lease_lal_tiers / lease_lal_assignments
-- 已存在,必驗 V112 spec column 全俱在;缺即 RAISE。同時驗 V098 / V099 / V100 prereq。
-- ============================================================
DO $$
DECLARE v_missing TEXT[];
BEGIN
    -- governance schema 存在驗
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.schemata WHERE schema_name='governance'
    ) THEN
        RAISE EXCEPTION
            'V112 Guard A FAIL: governance schema missing. '
            'Apply baseline schema migration before V112.';
    END IF;

    -- governance.audit_log 必須存在(M1 LAL cross-ref audit query target)
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='governance' AND table_name='audit_log'
    ) THEN
        RAISE EXCEPTION
            'V112 Guard A FAIL: governance.audit_log missing — '
            'V098 must apply before V112 (cross-ref audit). Verify _sqlx_migrations.';
    END IF;

    -- governance.lease_lal_tiers 已存在的情境下 check column 完整性
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='governance' AND table_name='lease_lal_tiers'
    ) THEN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'tier_level', 'tier_name', 'auto_approve', 'approval_quorum',
            'clawback_ttl_sec', 'cohort_min_n', 'resource_quota_cpu_pct',
            'risk_envelope_usdt', 'human_final_review', 'description',
            'created_by', 'created_at', 'updated_by', 'updated_at',
            'source_version'
        ]) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema='governance' AND table_name='lease_lal_tiers'
              AND column_name=c
        );
        IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
            RAISE EXCEPTION
                'V112 Guard A FAIL: governance.lease_lal_tiers exists but missing columns: %. '
                'Possible legacy stub conflict — resolve schema reconciliation before applying V112.',
                v_missing;
        END IF;
    END IF;

    -- governance.lease_lal_assignments 已存在的情境
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='governance' AND table_name='lease_lal_assignments'
    ) THEN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'id', 'lease_id', 'tier_level', 'assigned_by', 'assigned_at',
            'prev_tier_level', 'tier_change_reason',
            'no_incident_check_v113_ref', 'no_incident_check_pass',
            'no_incident_check_window_days', 'state_machine_step',
            'clawback_executed', 'clawback_at', 'engine_mode',
            'evidence_json', 'created_by', 'created_at',
            'updated_by', 'updated_at', 'source_version'
        ]) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema='governance' AND table_name='lease_lal_assignments'
              AND column_name=c
        );
        IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
            RAISE EXCEPTION
                'V112 Guard A FAIL: governance.lease_lal_assignments exists but missing columns: %. '
                'Resolve schema drift before applying V112.',
                v_missing;
        END IF;
    END IF;
END $$;
```

### 4.2 Guard B — 不適用

V112 不 ALTER 既有 column type;無 type-sensitive 檢查需求。本 spec 不設 Guard B 段。

### 4.3 Guard C — CHECK constraint + ENUM 值齊全 + UNIQUE + index 對齊驗證

```sql
-- ============================================================
-- Guard C: V112 預檢 — 重跑 V112 時 idempotent 檢查 CHECK constraint + 
-- tier_name UNIQUE + 5 seed rows 完整 + 3 index + materialized view
-- ============================================================
DO $$
DECLARE v_actual TEXT;
DECLARE v_seed_count INT;
BEGIN
    -- tier_name CHECK 5 值齊全
    SELECT pg_get_constraintdef(oid) INTO v_actual
    FROM pg_constraint
    WHERE conrelid='governance.lease_lal_tiers'::regclass
      AND conname LIKE '%tier_name%check%';
    IF v_actual IS NOT NULL THEN
        IF position('LAL_0_AUTO' IN v_actual) = 0
           OR position('LAL_1_LIGHT_REVIEW' IN v_actual) = 0
           OR position('LAL_2_FULL_REVIEW' IN v_actual) = 0
           OR position('LAL_3_OPERATOR_APPROVAL' IN v_actual) = 0
           OR position('LAL_4_OPERATOR_ATTESTATION' IN v_actual) = 0
        THEN
            RAISE EXCEPTION
                'V112 Guard C FAIL: governance.lease_lal_tiers tier_name CHECK enum mismatch. '
                'Actual: %. Expected to contain all 5 LAL tier names per ADR-0034.',
                v_actual;
        END IF;
    END IF;

    -- tier_change_reason CHECK 6 值齊全
    SELECT pg_get_constraintdef(oid) INTO v_actual
    FROM pg_constraint
    WHERE conrelid='governance.lease_lal_assignments'::regclass
      AND conname LIKE '%tier_change_reason%check%';
    IF v_actual IS NOT NULL THEN
        IF position('auto' IN v_actual) = 0
           OR position('manual' IN v_actual) = 0
           OR position('health_degraded' IN v_actual) = 0
           OR position('decay_signal' IN v_actual) = 0
           OR position('operator_override' IN v_actual) = 0
           OR position('initial_seed' IN v_actual) = 0
        THEN
            RAISE EXCEPTION
                'V112 Guard C FAIL: lease_lal_assignments tier_change_reason CHECK enum mismatch. '
                'Actual: %. Expected auto/manual/health_degraded/decay_signal/operator_override/initial_seed.',
                v_actual;
        END IF;
    END IF;

    -- engine_mode CHECK 5 值齊全(含 'replay')
    SELECT pg_get_constraintdef(oid) INTO v_actual
    FROM pg_constraint
    WHERE conrelid='governance.lease_lal_assignments'::regclass
      AND conname LIKE '%engine_mode%check%';
    IF v_actual IS NOT NULL THEN
        IF position('paper' IN v_actual) = 0
           OR position('demo' IN v_actual) = 0
           OR position('live_demo' IN v_actual) = 0
           OR position('live' IN v_actual) = 0
           OR position('replay' IN v_actual) = 0
        THEN
            RAISE EXCEPTION
                'V112 Guard C FAIL: lease_lal_assignments engine_mode CHECK enum mismatch. '
                'Actual: %. Expected paper/demo/live_demo/live/replay (replay for M11).',
                v_actual;
        END IF;
    END IF;

    -- tier_level CHECK 0-4(tiers + assignments + assignments.prev_tier_level)
    SELECT pg_get_constraintdef(oid) INTO v_actual
    FROM pg_constraint
    WHERE conrelid='governance.lease_lal_tiers'::regclass
      AND conname LIKE '%tier_level%check%';
    IF v_actual IS NOT NULL THEN
        IF position('0' IN v_actual) = 0
           OR position('4' IN v_actual) = 0
        THEN
            RAISE EXCEPTION
                'V112 Guard C FAIL: governance.lease_lal_tiers tier_level CHECK BETWEEN 0 AND 4 missing. '
                'Actual: %.',
                v_actual;
        END IF;
    END IF;

    -- 5 seed rows 完整(若 lease_lal_tiers 已存在)
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='governance' AND table_name='lease_lal_tiers'
    ) THEN
        SELECT count(*) INTO v_seed_count FROM governance.lease_lal_tiers;
        IF v_seed_count > 0 AND v_seed_count != 5 THEN
            RAISE EXCEPTION
                'V112 Guard C FAIL: governance.lease_lal_tiers seed row count mismatch. '
                'Actual: %. Expected: 5 rows (LAL 0-4 per ADR-0034).',
                v_seed_count;
        END IF;
    END IF;

    -- materialized view 存在驗(若 lease_lal_assignments 已存在 + MV 已建)
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='governance' AND table_name='lease_lal_assignments'
    ) AND NOT EXISTS (
        SELECT 1 FROM pg_matviews
        WHERE schemaname='governance' AND matviewname='mv_lease_lal_eligibility'
    ) THEN
        RAISE NOTICE 'V112 Guard C NOTE: mv_lease_lal_eligibility not yet built. '
                     'Will be added by main migration body.';
    END IF;
END $$;
```

### 4.4 Guard 設計理念(per V094 mirror)

| Guard | 觸發場景 | RAISE 條件 | NOT RAISE 條件(idempotent)|
|---|---|---|---|
| A | NEW table 已存在但 column 缺;governance.audit_log 缺(V098)| RAISE | 全 column 俱在 / table 不存在(首次跑)|
| C | CHECK constraint 缺 enum 值;seed rows count 不對 | RAISE | constraint 不存在(首次跑)/ constraint 完整(重跑)|
| C MV | materialized view 首次跑不存在 | NOTICE(不 RAISE,migration body 會建)| MV 已存在重跑(skip)|

重跑 V112 第二次必不 RAISE(idempotency per CLAUDE.md §Data, Migrations, And Validation V055/V083/V084 incident precedent)。

---

## §5 Migration up + down SQL

### 5.1 Migration UP(完整 V112.sql 設計)

```sql
-- ============================================================
-- V112: governance.lease_lal_tiers + governance.lease_lal_assignments
--       + governance.mv_lease_lal_eligibility (materialized view)
-- M1 Decision Lease Layered Approval (LAL) — 5 tier config + per-lease audit
-- per ADR-0034 (Tier 0 lowest risk / Tier 4 highest risk; numbers monotonic)
-- ============================================================

-- Step 1: Guard A (per §4.1)
-- [全文見 §4.1]

-- Step 2: Guard C 預檢 (per §4.3 重跑 idempotency)
-- [全文見 §4.3]

-- Step 3: CREATE TABLE governance.lease_lal_tiers (config)
CREATE TABLE IF NOT EXISTS governance.lease_lal_tiers (
    tier_level                  INT PRIMARY KEY
                                CHECK (tier_level BETWEEN 0 AND 4),
    tier_name                   TEXT NOT NULL UNIQUE
                                CHECK (tier_name IN (
                                    'LAL_0_AUTO',
                                    'LAL_1_LIGHT_REVIEW',
                                    'LAL_2_FULL_REVIEW',
                                    'LAL_3_OPERATOR_APPROVAL',
                                    'LAL_4_OPERATOR_ATTESTATION'
                                )),
    auto_approve                BOOLEAN NOT NULL,
    approval_quorum             INT NOT NULL CHECK (approval_quorum >= 0),
    clawback_ttl_sec            INT NOT NULL CHECK (clawback_ttl_sec >= 0),
    cohort_min_n                INT NOT NULL CHECK (cohort_min_n >= 0),
    resource_quota_cpu_pct      NUMERIC(5,2)
                                CHECK (resource_quota_cpu_pct IS NULL OR
                                       (resource_quota_cpu_pct > 0 AND resource_quota_cpu_pct <= 100)),
    risk_envelope_usdt          NUMERIC(20,8)
                                CHECK (risk_envelope_usdt IS NULL OR risk_envelope_usdt > 0),
    human_final_review          BOOLEAN NOT NULL,
    description                 TEXT,
    created_by                  TEXT NOT NULL DEFAULT 'system_seed',
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by                  TEXT,
    updated_at                  TIMESTAMPTZ,
    source_version              TEXT NOT NULL DEFAULT 'V112'
);

-- Step 4: Seed 5 tier rows (idempotent via ON CONFLICT)
INSERT INTO governance.lease_lal_tiers
    (tier_level, tier_name, auto_approve, approval_quorum, clawback_ttl_sec,
     cohort_min_n, resource_quota_cpu_pct, risk_envelope_usdt, human_final_review,
     description, created_by, source_version)
VALUES
    (0, 'LAL_0_AUTO', true, 0, 60, 0, 80.00, 5000.00000000, false,
     'Per-fill autonomous; always Guardian fast path; per ADR-0034 對齊矩陣 LAL 0',
     'system_seed', 'V112'),
    (1, 'LAL_1_LIGHT_REVIEW', true, 0, 300, 30, 60.00, 25000.00000000, false,
     'Intra-strategy reparam; Stage 4 + 30d stable + 6 hard gate; per ADR-0034 對齊矩陣 LAL 1',
     'system_seed', 'V112'),
    (2, 'LAL_2_FULL_REVIEW', true, 0, 600, 50, 40.00, 100000.00000000, false,
     'Cross-strategy reweight; Y2 gate + Console opt-in + 6 hard gate; per ADR-0034 對齊矩陣 LAL 2',
     'system_seed', 'V112'),
    (3, 'LAL_3_OPERATOR_APPROVAL', false, 1, 3600, 100, 20.00, NULL, true,
     'New strategy promotion; always operator manual approve; per ADR-0034 對齊矩陣 LAL 3',
     'system_seed', 'V112'),
    (4, 'LAL_4_OPERATOR_ATTESTATION', false, 1, 0, 200, 10.00, NULL, true,
     'Capital structure / venue change; always operator manual attest + 2FA; clawback 0 (immutable after attest); per ADR-0034 對齊矩陣 LAL 4',
     'system_seed', 'V112')
ON CONFLICT (tier_level) DO NOTHING;

-- Step 5: CREATE TABLE governance.lease_lal_assignments (history)
CREATE TABLE IF NOT EXISTS governance.lease_lal_assignments (
    id                              BIGSERIAL PRIMARY KEY,
    lease_id                        UUID NOT NULL,
    tier_level                      INT NOT NULL
                                    REFERENCES governance.lease_lal_tiers(tier_level),
    assigned_by                     TEXT NOT NULL,
    assigned_at                     TIMESTAMPTZ NOT NULL DEFAULT now(),
    prev_tier_level                 INT
                                    REFERENCES governance.lease_lal_tiers(tier_level),
    tier_change_reason              TEXT
                                    CHECK (tier_change_reason IS NULL OR tier_change_reason IN (
                                        'auto', 'manual', 'health_degraded',
                                        'decay_signal', 'operator_override', 'initial_seed'
                                    )),
    no_incident_check_v113_ref      BIGINT,
    no_incident_check_pass          BOOLEAN,
    no_incident_check_window_days   INT NOT NULL DEFAULT 90,
    state_machine_step              INT NOT NULL CHECK (state_machine_step BETWEEN 0 AND 8),
    clawback_executed               BOOLEAN NOT NULL DEFAULT FALSE,
    clawback_at                     TIMESTAMPTZ,
    engine_mode                     TEXT NOT NULL
                                    CHECK (engine_mode IN ('paper','demo','live_demo','live','replay')),
    evidence_json                   JSONB,
    created_by                      TEXT NOT NULL DEFAULT 'lal_gate',
    created_at                      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by                      TEXT,
    updated_at                      TIMESTAMPTZ,
    source_version                  TEXT NOT NULL DEFAULT 'V112',
    CONSTRAINT chk_clawback_consistency CHECK (
        (clawback_executed = FALSE AND clawback_at IS NULL) OR
        (clawback_executed = TRUE AND clawback_at IS NOT NULL)
    ),
    CONSTRAINT chk_no_incident_consistency CHECK (
        (no_incident_check_v113_ref IS NULL AND no_incident_check_pass IS NULL) OR
        (no_incident_check_v113_ref IS NOT NULL AND no_incident_check_pass IS NOT NULL)
    )
);

-- Step 6: Hot-path indexes
CREATE INDEX IF NOT EXISTS idx_lal_lease_id
    ON governance.lease_lal_assignments (lease_id);

CREATE INDEX IF NOT EXISTS idx_lal_assigned_at
    ON governance.lease_lal_assignments (assigned_at DESC);

CREATE INDEX IF NOT EXISTS idx_lal_tier_assigned
    ON governance.lease_lal_assignments (tier_level, assigned_at DESC);

-- Step 7: Materialized view (per §2.3)
CREATE MATERIALIZED VIEW IF NOT EXISTS governance.mv_lease_lal_eligibility AS
WITH latest_per_lease AS (
    SELECT DISTINCT ON (lease_id)
        lease_id, tier_level AS current_tier_level,
        assigned_at AS last_assigned_at,
        no_incident_check_pass AS last_incident_free_pass,
        no_incident_check_window_days, engine_mode
    FROM governance.lease_lal_assignments
    WHERE engine_mode IN ('live', 'live_demo')
    ORDER BY lease_id, assigned_at DESC
),
incident_free_90d AS (
    SELECT lease_id,
           BOOL_AND(no_incident_check_pass) FILTER (WHERE no_incident_check_pass IS NOT NULL) AS all_checks_pass_90d,
           COUNT(*) FILTER (WHERE no_incident_check_pass = false) AS incident_count_90d
    FROM governance.lease_lal_assignments
    WHERE engine_mode IN ('live', 'live_demo')
      AND assigned_at > now() - INTERVAL '90 days'
    GROUP BY lease_id
)
SELECT
    l.lease_id, l.current_tier_level,
    t.tier_name AS current_tier_name,
    t.auto_approve AS current_auto_approve,
    t.human_final_review AS current_human_final_review,
    l.last_assigned_at, l.last_incident_free_pass,
    i.all_checks_pass_90d,
    COALESCE(i.incident_count_90d, 0) AS incident_count_90d,
    CASE
        WHEN i.incident_count_90d IS NULL THEN 'eligible_no_history'
        WHEN i.incident_count_90d = 0 THEN 'eligible_clean_90d'
        ELSE 'ineligible_incident_in_90d'
    END AS eligibility_status,
    l.engine_mode,
    now() AS refreshed_at
FROM latest_per_lease l
LEFT JOIN governance.lease_lal_tiers t ON l.current_tier_level = t.tier_level
LEFT JOIN incident_free_90d i ON l.lease_id = i.lease_id;

-- UNIQUE INDEX 支援 REFRESH MATERIALIZED VIEW CONCURRENTLY
CREATE UNIQUE INDEX IF NOT EXISTS mv_lease_lal_eligibility_pkey
    ON governance.mv_lease_lal_eligibility (lease_id);

-- Step 8: COMMENT (audit metadata)
COMMENT ON TABLE governance.lease_lal_tiers IS
    'M1 LAL Tier Config (V112). 5 row seed per ADR-0034. tier_level 0 lowest risk / 4 highest risk; auto_approve=true for 0/1/2; human_final_review=true for 3/4.';

COMMENT ON TABLE governance.lease_lal_assignments IS
    'M1 LAL Per-Lease Assignment History (V112). Append-only audit ledger; tier_change_reason 6 values (auto/manual/health_degraded/decay_signal/operator_override/initial_seed); clawback_consistency + no_incident_consistency CHECK enforced.';

COMMENT ON MATERIALIZED VIEW governance.mv_lease_lal_eligibility IS
    'M1 LAL Eligibility MV (V112). Per-lease latest tier + 90d incident-free check; eligibility_status 3 values (eligible_no_history / eligible_clean_90d / ineligible_incident_in_90d); REFRESH CONCURRENTLY hourly via cron (Sprint 1B).';

COMMENT ON COLUMN governance.lease_lal_assignments.no_incident_check_v113_ref IS
    'Placeholder FK to V113 decay_signals.id; V113 land 後 ALTER TABLE ADD CONSTRAINT FK.';

COMMENT ON COLUMN governance.lease_lal_assignments.engine_mode IS
    'paper/demo/live_demo/live/replay. replay 為 M11 replay engine 寫入時 tag; training filter 仍 IN (live, live_demo).';
```

### 5.2 Migration DOWN(rollback;dev-only,production 慎用)

```sql
-- ============================================================
-- V112 ROLLBACK: 刪 MV + assignments + tiers
-- ⚠️ DESTRUCTIVE: 所有 lease assignment history 丟失;不可恢復。
-- 僅 dev/staging 使用;production rollback 走 V### 升級而非 down。
-- ============================================================

-- Step 1: Drop MV first (依賴 lease_lal_assignments + lease_lal_tiers)
DROP MATERIALIZED VIEW IF EXISTS governance.mv_lease_lal_eligibility;

-- Step 2: Drop indexes
DROP INDEX IF EXISTS governance.idx_lal_tier_assigned;
DROP INDEX IF EXISTS governance.idx_lal_assigned_at;
DROP INDEX IF EXISTS governance.idx_lal_lease_id;

-- Step 3: Drop tables (順序: assignments 先 drop 因 FK)
DROP TABLE IF EXISTS governance.lease_lal_assignments;
DROP TABLE IF EXISTS governance.lease_lal_tiers;
```

### 5.3 Idempotency 驗證

per V055 5-round loop + V083/V084 incident precedent,V112.sql 必跑兩次:
- 第一次:CREATE TABLE × 2 + INSERT seed 5 row + 3 index + MV + UNIQUE index → 0 RAISE / 0 ERROR
- 第二次:全 IF NOT EXISTS / ON CONFLICT DO NOTHING / MV 已存在 → 0 RAISE / 0 重複 row

---

## §6 Cross-V### Dependency + Cross-Ref Schema

### 6.1 Cross-V### dependency 圖

```
V098 (governance.audit_log)             ← V112 (cross-ref audit;非 FK)
V099/V100 (Decision Lease state machine baseline)  ← V112 (lease_id source;application-layer ref;非 schema FK)
V113 (M7 decay_signals)                  ← V112 (no_incident_check_v113_ref;placeholder FK,V113 land 後 ALTER ADD CONSTRAINT)

V112 (M1 LAL config + history + MV)
    │
    ├─→ V109 (M8 anomaly) γ track — M8 emit → 寫 lease_lal_assignments.tier_change_reason='health_degraded' demote
    ├─→ V106 (M3 health) — HEALTH_DEGRADED → LAL 1 reparam halt (cross-ref query)
    └─→ V107 (M11 replay) — replay engine 重放 lease decision (engine_mode='replay')
```

### 6.2 為什麼 V112 與 V099/V100 lease 表用 application-layer cross-ref(非 schema FK)

per `db-schema-design-financial-time-series` skill §5(engine_mode 隔離 + FK 設計):
- V099/V100 schema 由 PA 同 Sprint 1A-α 派工待 land;此刻寫 FK CONSTRAINT 會 RAISE(target 不存在)
- 即使 V099/V100 land,FK CONSTRAINT 對 ~141 row/day INSERT 來說有 overhead(per INSERT 查 FK target)
- application layer(Rust lal_gate)責任維持 referential integrity;healthcheck Sprint 1B 補 `check_lal_lease_id_orphan()`

### 6.3 V113 placeholder FK 策略

```sql
-- Sprint 後續 V113 land + 確認 decay_signals.id BIGINT PK 後:
ALTER TABLE governance.lease_lal_assignments
    ADD CONSTRAINT fk_lal_no_incident_v113
    FOREIGN KEY (no_incident_check_v113_ref)
    REFERENCES learning.decay_signals(id);
-- 屆時走另一個 V### migration ALTER ADD CONSTRAINT
```

本 V112 不寫此 FK;`no_incident_check_v113_ref` BIGINT column comment 標 placeholder。

### 6.4 V109 (M8 anomaly) γ track cross-ref pattern

```sql
-- 例: M8 anomaly emit → 對應 strategy 的 LAL tier demote
-- (M8 writer 不直接寫 lease_lal_assignments;走 governance lal_gate Rust module)
INSERT INTO governance.lease_lal_assignments
    (lease_id, tier_level, assigned_by, prev_tier_level, tier_change_reason,
     state_machine_step, engine_mode, evidence_json)
VALUES
    ($1, 0, 'm8_anomaly_detector', 2, 'health_degraded',
     5, 'live',
     jsonb_build_object('source','m8','anomaly_id',$2,'demote_reason','liquidation_cascade'));
```

### 6.5 V106 (M3 health) cross-ref pattern

```sql
-- 例: M3 HEALTH_DEGRADED → LAL 1 reparam halt
-- (M3 writer 不直接寫;走 governance lal_gate 評估)
SELECT current_tier_level, current_tier_name, eligibility_status
FROM governance.mv_lease_lal_eligibility
WHERE lease_id = $1;
-- current_tier_level >= 1 + M3 state=HEALTH_DEGRADED → halt reparam
```

### 6.6 V107 (M11 replay) cross-ref pattern

```sql
-- 例: M11 nightly replay 重放 lease assign
INSERT INTO governance.lease_lal_assignments
    (lease_id, tier_level, assigned_by, prev_tier_level, tier_change_reason,
     state_machine_step, engine_mode, evidence_json)
VALUES
    ($1, $2, 'm11_replay_engine', $3, $4,
     8, 'replay',  -- ← engine_mode='replay' 區分 live
     jsonb_build_object('source','m11','original_assignment_id',$5,'replay_at',now()));
```

---

## §7 Linux PG Empirical Dry-Run Protocol(mandatory)

per CLAUDE.md §Data, Migrations, And Validation + `feedback_v_migration_pg_dry_run.md` + V055 5-round loop / V083 / V084 incident chain,V112 涉及:
- governance schema 新表(2 個)+ MV(1 個)
- FK constraint(tier_level → lease_lal_tiers)+ CHECK constraint runtime ENUM semantic
- materialized view CONCURRENTLY refresh prerequisite(UNIQUE INDEX)
- 5 row seed INSERT ON CONFLICT idempotency
- composite CHECK constraint(chk_clawback_consistency / chk_no_incident_consistency)

**必先 Linux PG empirical 驗證**,禁 Mac mock pytest 代替。

### 7.1 PA C9 待補的 PG reflection query(spec sign-off 前必補)

per CLAUDE.md `docs/agents/context-loading.md` "PG Connection Examples"(Linux runtime authoritative):

```bash
# Connection (per V103/V104 dry-run §1):
# Host: 127.0.0.1 Port: 5432 User: trading_admin DB: trading_ai
# Auth: ~/.pgpass *:5432:trading_ai:trading_admin:****

# Query 1: _sqlx_migrations head 確認 V112 dispatch 前提
ssh trade-core "PGPASSWORD=\$(cat ~/.pgpass | grep trading_ai | cut -d: -f5) psql -h 127.0.0.1 -p 5432 -U trading_admin -d trading_ai -c 'SELECT max(version), array_agg(version ORDER BY version DESC) FROM (SELECT version FROM _sqlx_migrations ORDER BY version DESC LIMIT 15) sub'"
# Expected: ≥ V098 (V098 governance.audit_log land 是 V112 prereq);理想 V099/V100/V106/V107/V109/V113 也 land

# Query 2: governance schema + audit_log 已 land 驗
ssh trade-core "PGPASSWORD=\$(cat ~/.pgpass | grep trading_ai | cut -d: -f5) psql -h 127.0.0.1 -p 5432 -U trading_admin -d trading_ai -c \"SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema='governance' ORDER BY table_name\""
# Expected: 含 audit_log (V098 land 後);可能含 unblock_candidates / canary_stage_metric_seed (V089/V090)

# Query 3: V099/V100 lease 表是否 land(application-layer FK target)
ssh trade-core "PGPASSWORD=\$(cat ~/.pgpass | grep trading_ai | cut -d: -f5) psql -h 127.0.0.1 -p 5432 -U trading_admin -d trading_ai -c \"SELECT table_schema, table_name FROM information_schema.tables WHERE table_name LIKE '%lease%' AND table_schema IN ('governance','learning','trading')\""
# Expected: 列出所有含 'lease' 表;若 V099/V100 已 land,governance.leases / governance.lease_state_machine 等表會出現

# Query 4: V113 decay_signals 是否 land(placeholder FK target)
ssh trade-core "PGPASSWORD=\$(cat ~/.pgpass | grep trading_ai | cut -d: -f5) psql -h 127.0.0.1 -p 5432 -U trading_admin -d trading_ai -c \"SELECT column_name, data_type FROM information_schema.columns WHERE table_schema='learning' AND table_name='decay_signals' AND column_name='id'\""
# Expected: 若 V113 已 land:1 row(id BIGINT/BIGSERIAL);若未 land:0 row

# Query 5: governance.lease_lal_tiers / lease_lal_assignments stub 不存在驗
ssh trade-core "PGPASSWORD=\$(cat ~/.pgpass | grep trading_ai | cut -d: -f5) psql -h 127.0.0.1 -p 5432 -U trading_admin -d trading_ai -c \"SELECT table_name FROM information_schema.tables WHERE table_schema='governance' AND table_name LIKE 'lease_lal%'\""
# Expected: 0 rows (greenfield); 若 1+ rows → 觸 Guard A 反向檢查
```

**待 PA C9 補資料的 5 處 placeholder**(spec sign-off 前必更新):
1. `_sqlx_migrations` head 真實 = ?(spec 假設 ≥ V098)
2. governance.audit_log 已 land 確認 = ?
3. V099/V100 lease 表 land 狀態 = ?(影響 application-layer cross-ref readiness)
4. V113 decay_signals 已 land 確認 = ?(影響 placeholder FK 何時 ALTER ADD)
5. governance.lease_lal_tiers / lease_lal_assignments stub 不存在確認 = ?

### 7.2 Round 1 — V112 SQL 真實 PG semantic empirical 驗證

```bash
# ssh trade-core 執行(不在 Mac 跑)
ssh trade-core "
  cd ~/BybitOpenClaw/srv && \
  PGPASSWORD=\$(cat ~/.pgpass | grep trading_ai | cut -d: -f5) \
  psql -h 127.0.0.1 -p 5432 -U trading_admin -d trading_ai \
    -v ON_ERROR_STOP=1 -f sql/migrations/V112__m1_decision_lease_lal_tiers.sql
"
```

**Round 1 必驗 11 項**(empirical SELECT verify after V112 apply):

```sql
-- 1. governance.lease_lal_tiers 表存在 + 15 columns
SELECT count(*) FROM information_schema.columns
WHERE table_schema='governance' AND table_name='lease_lal_tiers';
-- Expected: 15

-- 2. governance.lease_lal_assignments 表存在 + 20 columns
SELECT count(*) FROM information_schema.columns
WHERE table_schema='governance' AND table_name='lease_lal_assignments';
-- Expected: 20

-- 3. 5 row seed 完整(LAL 0-4)
SELECT tier_level, tier_name, auto_approve, human_final_review, clawback_ttl_sec
FROM governance.lease_lal_tiers ORDER BY tier_level;
-- Expected: 5 rows;
--   0|LAL_0_AUTO|true|false|60
--   1|LAL_1_LIGHT_REVIEW|true|false|300
--   2|LAL_2_FULL_REVIEW|true|false|600
--   3|LAL_3_OPERATOR_APPROVAL|false|true|3600
--   4|LAL_4_OPERATOR_ATTESTATION|false|true|0

-- 4. tier_name CHECK 5 值齊全
SELECT pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid='governance.lease_lal_tiers'::regclass AND conname LIKE '%tier_name%check%';
-- Expected: 含 LAL_0_AUTO/LAL_1_LIGHT_REVIEW/LAL_2_FULL_REVIEW/LAL_3_OPERATOR_APPROVAL/LAL_4_OPERATOR_ATTESTATION

-- 5. tier_change_reason CHECK 6 值齊全
SELECT pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid='governance.lease_lal_assignments'::regclass AND conname LIKE '%tier_change_reason%check%';
-- Expected: 含 auto/manual/health_degraded/decay_signal/operator_override/initial_seed

-- 6. engine_mode CHECK 5 值齊全(含 replay)
SELECT pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid='governance.lease_lal_assignments'::regclass AND conname LIKE '%engine_mode%check%';
-- Expected: 含 paper/demo/live_demo/live/replay

-- 7. FK constraint 真存在(assignments.tier_level → tiers + prev_tier_level → tiers)
SELECT conname, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid='governance.lease_lal_assignments'::regclass AND contype='f';
-- Expected: 2 rows(tier_level + prev_tier_level 各 1 FK)

-- 8. 3 indexes 真建立
SELECT indexname FROM pg_indexes
WHERE schemaname='governance' AND tablename='lease_lal_assignments'
ORDER BY indexname;
-- Expected: ≥ 4(1 PK + idx_lal_lease_id + idx_lal_assigned_at + idx_lal_tier_assigned)

-- 9. Materialized view 存在 + UNIQUE INDEX 支援 REFRESH CONCURRENTLY
SELECT matviewname FROM pg_matviews
WHERE schemaname='governance' AND matviewname='mv_lease_lal_eligibility';
-- Expected: 1 row

SELECT indexname FROM pg_indexes
WHERE schemaname='governance' AND tablename='mv_lease_lal_eligibility'
  AND indexname='mv_lease_lal_eligibility_pkey';
-- Expected: 1 row(UNIQUE index for REFRESH CONCURRENTLY)

-- 10. CHECK constraints (clawback_consistency / no_incident_consistency) 真存在
SELECT conname, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid='governance.lease_lal_assignments'::regclass
  AND conname IN ('chk_clawback_consistency', 'chk_no_incident_consistency');
-- Expected: 2 rows

-- 11. tier_level CHECK 真 reject 5 (empirical INSERT test)
BEGIN;
SAVEPOINT test_tier_level;
INSERT INTO governance.lease_lal_tiers
    (tier_level, tier_name, auto_approve, approval_quorum, clawback_ttl_sec,
     cohort_min_n, human_final_review)
VALUES
    (5, 'INVALID', true, 0, 0, 0, false);
-- Expected: ERROR: violates check constraint (BETWEEN 0 AND 4)
ROLLBACK TO SAVEPOINT test_tier_level;

-- 同時測 engine_mode CHECK reject 非 5 值
SAVEPOINT test_engine_mode;
INSERT INTO governance.lease_lal_assignments
    (lease_id, tier_level, assigned_by, state_machine_step, engine_mode)
VALUES
    (gen_random_uuid(), 0, 'test', 0, 'INVALID_MODE');
-- Expected: ERROR: violates check constraint
ROLLBACK TO SAVEPOINT test_engine_mode;

-- 同時測 clawback_consistency CHECK
SAVEPOINT test_clawback;
INSERT INTO governance.lease_lal_assignments
    (lease_id, tier_level, assigned_by, state_machine_step, engine_mode,
     clawback_executed, clawback_at)
VALUES
    (gen_random_uuid(), 0, 'test', 0, 'live',
     TRUE, NULL);  -- clawback=TRUE 但 clawback_at=NULL → CHECK fail
-- Expected: ERROR: violates check constraint
ROLLBACK TO SAVEPOINT test_clawback;

ROLLBACK;
```

### 7.3 Round 2 — Idempotency 驗證

重跑 V112.sql 第二次必不 RAISE / 必不重複 INSERT seed / 必不重複建 MV:

```bash
ssh trade-core "
  cd ~/BybitOpenClaw/srv && \
  PGPASSWORD=\$(cat ~/.pgpass | grep trading_ai | cut -d: -f5) \
  psql -h 127.0.0.1 -p 5432 -U trading_admin -d trading_ai \
    -v ON_ERROR_STOP=1 -f sql/migrations/V112__m1_decision_lease_lal_tiers.sql
"
# Expected exit code 0; all DO blocks output NOTICE-only PASS; 0 RAISE EXCEPTION
```

**Round 2 後驗證**:
```sql
-- 確認 V112 不 double-create
SELECT count(*) FROM information_schema.tables
WHERE table_schema='governance' AND table_name IN ('lease_lal_tiers', 'lease_lal_assignments');
-- Expected: 2

-- 確認 seed rows 仍 5(ON CONFLICT DO NOTHING 生效)
SELECT count(*) FROM governance.lease_lal_tiers;
-- Expected: 5(非 10)

-- 確認 MV 仍 1
SELECT count(*) FROM pg_matviews
WHERE schemaname='governance' AND matviewname='mv_lease_lal_eligibility';
-- Expected: 1

-- 確認 indexes 仍 3 + 1 UNIQUE(MV)
SELECT count(*) FROM pg_indexes
WHERE schemaname='governance' AND tablename='lease_lal_assignments';
-- Expected: ≥ 4(1 PK + 3 hot path)
```

### 7.4 為何 Mac mock pytest 不夠(V055 5-round loop 教訓)

per memory `feedback_v_migration_pg_dry_run.md` + `project_2026_05_02_p0_sqlx_hash_drift`:
- Mac mock pytest 無法捕捉 PG composite CHECK constraint(`chk_clawback_consistency` / `chk_no_incident_consistency`)runtime semantic
- Mac static parse review 無法驗 MV `DISTINCT ON` + `FILTER` aggregation 真實行為
- Mac 無法驗 FK CONSTRAINT(tier_level + prev_tier_level 雙 FK 到同表)PG 載入時的順序處理
- Mac 無法驗 `gen_random_uuid()` 在 INSERT test 的可用性(需 PG extension pgcrypto / 或 PG 13+)
- V055 chain 5 round 都 Mac false-pass 後 Linux 撞 bug;V094 / V106 / V112 全須遵守 V055 mandate

**E2 / E4 / A3 review 必含 Linux PG dry-run gate 證據 ID**(per CLAUDE.md §Data, Migrations, And Validation + V094 §4.3 範式)。

---

## §8 Engine Restart 實測 SOP(per 2026-05-02 sqlx hash drift 教訓)

per memory `project_2026_05_02_p0_sqlx_hash_drift`(commit `3681f83`),V112 file edit 後 DB checksum 必同步:

```bash
# E1 IMPL: 寫 V112.sql 完成後跑 Linux dry-run (per §7.2)
# 若 V112.sql 落地後又被 edit → DB checksum drift
# 必跑 repair binary 同步 checksum 到 _sqlx_migrations table

ssh trade-core "
  cd ~/BybitOpenClaw/srv && \
  cargo run --release --bin repair_migration_checksum -- --version 112
"
# Expected: V112 checksum updated in _sqlx_migrations table to match new file SHA
```

### 8.1 Engine restart 後驗證 sqlx migrate 不 panic

```bash
ssh trade-core "bash ~/BybitOpenClaw/srv/helper_scripts/restart_all.sh --rebuild"

ssh trade-core "tail -200 ~/BybitOpenClaw/srv/program_code/exchange_connectors/bybit_connector/openclaw_engine/logs/engine.log 2>&1 | grep -E 'sqlx|migration|panic'"
# Expected: 0 panic; 'Applied migrations' 正常 log; V112 success=t in _sqlx_migrations

ssh trade-core "PGPASSWORD=\$(cat ~/.pgpass | grep trading_ai | cut -d: -f5) psql -h 127.0.0.1 -p 5432 -U trading_admin -d trading_ai -c 'SELECT version, success, description FROM _sqlx_migrations WHERE version=112'"
# Expected: 1 row, success=t
```

### 8.2 治理盲點防範

per `project_2026_05_02_p0_sqlx_hash_drift` + V094 §5.3:cargo test PASS ≠ runtime sqlx migrate 驗證。E2 / E4 review 必含「engine restart 實測 + sqlx migrate runtime 不 panic」driver evidence。

---

## §9 Rollback Plan + Reversibility Analysis

### 9.1 V112 rollback DDL

詳見 §5.2(`DROP MV` + `DROP INDEX` + `DROP TABLE` 順序處理 FK)。

### 9.2 Reversibility 分析

| 操作 | 可逆? | 風險 |
|---|---|---|
| `DROP MATERIALIZED VIEW mv_lease_lal_eligibility` | 可逆(rerun V112 重建)| LOW |
| `DROP TABLE governance.lease_lal_assignments` | 邏輯可逆(rerun V112)但 row data 不可逆(全 drop)| **HIGH** — 所有 lease assignment history 丟失 |
| `DROP TABLE governance.lease_lal_tiers` | 可逆(rerun V112 重 seed)| MED — 若 IMPL 期 operator override 改過 seed 值,rerun 會還原 default |
| `DROP INDEX` | 可逆(rerun V112 重建)| LOW |

### 9.3 Rollback 觸發條件

- 僅 dev / staging
- production rollback 走 V### 升級(e.g. V###+1 加 ADD COLUMN / 改 CHECK constraint;不走 V112 down)

### 9.4 V096 boundary

per V101 spec v3 §7:rollback 路徑不跨 V096(V096 drop dead tables 不可逆)。V112 rollback 全在 V096 之後(V096 < V098 < V112),無 boundary 風險。

---

## §10 Audit Field(per V103 EXTEND 範式)

V112 兩表均採 V103 EXTEND §14 同範式 5 audit field:

| Column | DEFAULT | NOT NULL | 設計 |
|---|---|---|---|
| `created_by` | `'system_seed'`(tiers)/ `'lal_gate'`(assignments) | NOT NULL | writer / actor;允許 'system_seed' / 'lal_gate' / 'operator' / 'm8_anomaly_detector' / 'health_monitor' / 'm11_replay_engine' |
| `created_at` | now() | NOT NULL | row insert 時間(server trusted)|
| `updated_by` | NULL | NULLABLE | 後續 update 的 actor(若 tier config 改 / clawback_executed update)|
| `updated_at` | NULL | NULLABLE | last update 時間 |
| `source_version` | `'V112'` | NOT NULL | schema version tag;未來 schema migration audit;當前固定 V112 |

### 10.1 為什麼 lease_lal_tiers + lease_lal_assignments 都需 audit field

per DOC-08 §12 #8 安全不變量「交易可解釋」:LAL tier config + assignment 是 decision lease approval 的決定 input;每筆必有 audit trail 才能 reproduce(per ADR-0034 Decision 1)。

### 10.2 update_at / update_by 何時填

`lease_lal_assignments`:
- clawback 執行時 UPDATE `clawback_executed=TRUE` + `clawback_at=now()` + `updated_by='lal_gate'` + `updated_at=now()`
- no_incident_check backfill(V113 land 後)UPDATE `no_incident_check_v113_ref` + `no_incident_check_pass` + `updated_by='lal_backfill_v113'` + `updated_at=now()`

`lease_lal_tiers`:
- operator override 改 risk_envelope_usdt 或 cohort_min_n(罕見;走 Console toggle 2FA per ADR-0034 Decision 4)→ UPDATE `updated_by='operator'` + `updated_at=now()`

---

## §11 Acceptance Criteria(5-7 條 sign-off 標準)

### 11.1 Schema acceptance(MIT + E2)

| # | 標準 | 驗證方法 |
|---|---|---|
| 1 | `governance.lease_lal_tiers` 15 column 全俱在 + 5 seed rows 完整 | `SELECT count(*) FROM information_schema.columns WHERE table_schema='governance' AND table_name='lease_lal_tiers'` = 15;`SELECT count(*) FROM governance.lease_lal_tiers` = 5 |
| 2 | `governance.lease_lal_assignments` 20 column 全俱在 + 2 composite CHECK + 2 FK | `SELECT count(*) FROM information_schema.columns ...` = 20;`SELECT count(*) FROM pg_constraint WHERE conrelid=...assignments::regclass AND contype IN ('c','f')` = 2 + 2 |
| 3 | 5 row seed 對應 ADR-0034 對齊矩陣語義方向 | empirical SELECT 驗 `tier_level=0 → auto_approve=true human_final_review=false clawback_ttl_sec=60`;`tier_level=4 → auto_approve=false human_final_review=true clawback_ttl_sec=0` |
| 4 | engine_mode CHECK 5 值齊全(含 'replay'); tier_change_reason CHECK 6 值齊全;tier_name CHECK 5 值齊全 | empirical INSERT test reject INVALID(per §7.2 step 11)|
| 5 | Materialized view + UNIQUE INDEX 真建立 + REFRESH CONCURRENTLY 可跑 | `REFRESH MATERIALIZED VIEW CONCURRENTLY governance.mv_lease_lal_eligibility` 成功 0 error |
| 6 | V112.sql idempotent 雙跑 0 RAISE + seed rows 仍 5(非 10)| `psql -f V112.sql` x 2 + `SELECT count(*) FROM governance.lease_lal_tiers` = 5 |
| 7 | sqlx checksum 對齊 + engine restart 後 success=t | per §8 SOP |

### 11.2 Cross-V### acceptance(PA)

| # | 標準 | 驗證方法 |
|---|---|---|
| 1 | V098 prereq 滿足 + governance.audit_log 存在 | `SELECT version FROM _sqlx_migrations WHERE version=98` |
| 2 | V099/V100/V106/V107/V109/V113 cross-ref query 不破壞 V112 schema | per §6 範例 query 預跑 |

### 11.3 治理 acceptance(QA + R4)

| # | 標準 | 驗證方法 |
|---|---|---|
| 1 | engine_mode IN ('live','live_demo') filter 在 MV 中出現 | per §2.3 MV 定義對齊 |
| 2 | 5 audit field 預設值 reasonable | INSERT row 不填 audit field 後 SELECT 驗 DEFAULT |
| 3 | docs/README.md 加 V112 spec 入 index | per CLAUDE.md §七 docs/README 規則 |

---

## §12 開放問題 + Caveat

### 12.1 待 PA C9 確認

1. **`_sqlx_migrations` head 真實**(per §7.1 Query 1)— spec 假設 ≥ V098
2. **V099/V100 lease 表 land 狀態**(per §7.1 Query 3)— spec 採 application-layer cross-ref(不寫 FK CONSTRAINT)
3. **V113 decay_signals 已 land 確認**(per §7.1 Query 4)— spec 寫 placeholder FK column;V113 land 後另起 V### ALTER ADD CONSTRAINT
4. **legacy stub conflict**(per §7.1 Query 5)— spec 假設 greenfield
5. **governance.audit_log.id column 是否 BIGSERIAL** — V112 不直接 FK 但 `evidence_json` 可能 ref;PA 驗證後 spec 對齊

### 12.2 已知 caveat

1. **5 seed rows 預設值是 baseline,operator 可後續 UPDATE 改 risk_envelope_usdt / cohort_min_n**(走 Console 2FA path per ADR-0034 Decision 4);本 spec 不預設 operator override
2. **`no_incident_check_v113_ref` placeholder FK** 在 V113 land 前無 FK constraint;application layer 寫入時需自行確保 ref 真存在(否則 dangling reference)
3. **MV refresh cadence** 在 Sprint 1B 補(hourly cron via `helper_scripts/refresh_lal_mv.sh`);本 spec 不含 cron
4. **`risk_envelope_usdt NULL` for LAL 3/4** 意義 = 不設 USDT 上限(strategy promotion 走 Stage gate;capital structure 走 ADR-debt);非「無限風險」
5. **engine_mode='replay'** 是 M11 replay engine 寫入時 tag;ML training filter `IN ('live','live_demo')` 不含 replay(per CLAUDE.md §二 + MIT memory baseline)
6. **`assigned_by` 不 enum**:actor identity 動態擴增(operator id 字串 + agent id 字串);writer 端責任維持 naming consistency
7. **state_machine_step 0-8** 對應 M1 LAL design spec §3 state machine 9 個狀態(emit / evaluate / approve / sign / settle / clawback / archive / error / replay);若 design spec §3 後續修訂,本 V112 schema 需 ALTER CHECK BETWEEN

### 12.3 Sprint 1B writer 路徑未在本 spec 範圍

V112 apply 後立即 0 row(Foundation stage per MIT pipeline maturity);Sprint 1B 補 writer 後升 Skeleton。

---

## §13 後續行動(給 PM 派發)

| Action | Owner | Track | Priority |
|---|---|---|---|
| Sign-off 本 V112 spec full DDL v0 | PM | Sprint 1A-β schema prereq closure | P0 |
| PA C9 跑 §7.1 5 條 ssh PG query + 補 5 處 placeholder | PA | Sprint 1A-β pre-dispatch | P0 |
| Reconcile cross-V### dependency(V099/V100/V106/V107/V109/V113 對 V112 cross-ref 對齊)| PA | Sprint 1A-β pre-dispatch | P0 |
| Reconcile V112 placeholder v0 反向錯誤之 downstream contamination 風險 — 凡 v0 placeholder 之引用方(若 v0 已被 sub-agent 派工讀過)需追補 errata | PM | Sprint 1A-β pre-dispatch | P0 |
| IMPL kickoff:派 E1 寫 V112.sql + Linux PG dry-run × 2 + E2/E4 + restart_all 部署 | PM | Sprint 1A-β IMPL | P1 |
| Sprint 1B writer 上線:`lal_gate` writer + healthcheck `check_lal_assignments_writer()` | E1 (Sprint 1B) | Sprint 1B | P2 |
| Sprint 1B MV refresh cron `refresh_lal_mv.sh`(hourly REFRESH CONCURRENTLY)| E1 (Sprint 1B) | Sprint 1B | P2 |
| Sprint 4+ LAL gate Rust IMPL + Console toggle 2FA | E1 (Sprint 4) | Sprint 4 | P3 |

### 13.1 Sprint 1A-β schema prereq closure 標誌

本 spec PM sign-off + PA C9 dry-run 補資料 land + V099/V100/V106/V107/V109/V113 cross-ref reconciliation 完成 → Sprint 1A-β V112 schema prereq 解除 → IMPL kickoff 派 E1。

---

## §14 關鍵文件指針

- 本 V112 spec:本檔
- **ADR-0034 (LAL 0-4 authoritative source of truth)**:`srv/docs/adr/0034-decision-lease-layered-approval-lal.md`
- M1 LAL design spec(697 line;§11 cross-V### + §6 反向 attack mitigation):`srv/docs/execution_plan/2026-05-21--m1_lal_layered_approval_lease_design_spec.md`
- v5.8 主檔 §2 M1:`srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md`
- PA dispatch consolidation §6 cross-V### dep graph:`srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md`
- ADR-0008 (Decision Lease state machine baseline; lease emit/sign/settle/replay):`srv/docs/adr/0008-decision-lease-state-machine.md`
- ADR-0016 (Decision Lease Router evidence mode):`srv/docs/adr/0016-decision-lease-router-evidence-mode.md`
- ADR-0036 (M8 + M10 Tier D blacklist; γ track demote source):`srv/docs/adr/0036-m8-anomaly-detection-and-m10-tier-d-model-blacklist.md`
- ADR-0038 (M11 Continuous Counterfactual Replay; engine_mode='replay' source):`srv/docs/adr/0038-m11-continuous-counterfactual-replay-and-liquidations-source.md`
- V103 spec(範式 + 5 audit field EXTEND):`srv/docs/execution_plan/2026-05-21--v103_v104_earn_hypotheses_schema_spec.md`
- V106 spec(姊妹 V### + 14 section structure):`srv/docs/execution_plan/2026-05-21--v106_m3_health_observations_schema_spec.md`
- V103/V104 Linux PG dry-run protocol(範式):`srv/docs/execution_plan/2026-05-21--v103_v104_linux_pg_dry_run.md`
- V094 spec(Guard A/B/C + 範式):`srv/docs/execution_plan/2026-05-15--v094_close_maker_first_audit_schema_spec.md`
- schema_guard_template:`srv/sql/migrations/templates/schema_guard_template.sql`
- repair binary:`srv/rust/openclaw_engine/src/bin/repair_migration_checksum.rs`
- V055 5-round loop + sqlx hash drift incident lessons:`memory/feedback_v_migration_pg_dry_run.md` + `memory/project_2026_05_02_p0_sqlx_hash_drift.md`
- CLAUDE.md §Data, Migrations, And Validation:`srv/CLAUDE.md`

---

**END V112 spec full DDL v0**
