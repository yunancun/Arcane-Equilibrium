---
spec: V108 — M9 A/B Testing Framework Schema
date: 2026-05-21
author: MIT consultant draft for PA Sprint 1A-γ dispatch (placeholder reserve)
phase: v5.8 Sprint 1A-γ schema prerequisite (per assignment)
status: SPEC-PLACEHOLDER (frontmatter + 大綱 reserve; full DDL land Sprint 1A-γ)
parent specs:
  - srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md §2 M9 A/B + §8 ADR-0037
  - srv/docs/adr/0037-ab-testing-msprt.md (per v5.8 §8)
mirror precedent:
  - srv/docs/execution_plan/2026-05-21--v103_v104_earn_hypotheses_schema_spec.md (format reference)
  - srv/sql/migrations/V094__fills_close_maker_audit.sql (Guard A/B/C 範式)
scope: placeholder spec — 不寫 V108.sql, 不在 Mac 跑 SQL, 不執行 PG, full DDL 在 Sprint 1A-γ 補完
---

# V108 M9 A/B Testing Framework Schema Migration Spec (PLACEHOLDER)

## §0 TL;DR

- **V108 新增 3 個 regular table**：`learning.ab_tests`（A/B test config）+ `learning.ab_assignments`（per-decision variant assignment）+ `learning.ab_results`（aggregated test statistics）。
- **`variant_type` 4 值 ENUM**：`parameter` / `sizing` / `trigger` / `overlay`（per H-5 — v5.8 §2 M9 module H-5 alignment）。
- **統計方法 = mSPRT + multiple comparisons correction**（per ADR-0037 — mSPRT = mixture Sequential Probability Ratio Test，支援 sequential testing 不 inflated false discovery rate）。
- **`ab_assignments` 是 high-cardinality table**（per-decision 1 row），但 retention 短（90d），仍可 regular table；ab_tests + ab_results 是 low-cardinality config/aggregation table。
- **依賴 V103**（hypothesis_id FK — per M9 share M4 hypothesis schema；A/B test 是 hypothesis subset）。
- **engine_mode CHECK 4 值齊全**；A/B test 限 demo+live_demo+live 跑（paper 失真不採）。

---

## §1 Background

### 1.1 v5.8 §2 M9 module 出處 + §8 ADR-0037

v5.8 §2 M9 A/B framework 列出：
- A/B test 為 hypothesis testing 之 finer-grained variant comparison
- 4 variant types：parameter (e.g. SL/TP ratio) / sizing (e.g. position size ladder) / trigger (e.g. entry threshold) / overlay (e.g. M2 overlay activation rule)
- mSPRT 是 default 統計方法（per ADR-0037）— 支援 peeking 不 inflated Type I error
- multiple comparisons correction：Bonferroni or Benjamini-Hochberg FDR control

### 1.2 Audit 來源

- MIT 2026-05-21 v5.8 audit Risk 8「M9 schema spec missing」
- ADR-0037 mSPRT mandate
- CR-9 cross-V### dependency：M9 share V103 hypotheses table（A/B test 必有 hypothesis_id FK）

---

## §2 Schema Outline (placeholder)

### 2.1 `learning.ab_tests`

**Tables 大綱**：
- PK: `test_id BIGSERIAL`
- FK: `hypothesis_id BIGINT` → `learning.hypotheses.hypothesis_id` (V103 prereq)
- Columns 大綱（11 fields）：
  - `test_id`, `hypothesis_id`, `test_name`, `variant_type` (ENUM 4 值)
  - `control_config_json JSONB`, `treatment_config_json JSONB`
  - `traffic_split_ratio NUMERIC(5,4)` (e.g. 0.5000 = 50/50; 0.1000 = 10% canary)
  - `started_at TIMESTAMPTZ NOT NULL`, `ended_at TIMESTAMPTZ NULL`
  - `status TEXT` (ENUM: `running` / `concluded_treatment_win` / `concluded_control_win` / `concluded_no_diff` / `halted`)
  - `engine_mode TEXT NOT NULL`

**Constraints 大綱**：
- CHECK: `variant_type` ∈ 4 值 ENUM
- CHECK: `status` ∈ 5 值 ENUM
- CHECK: `engine_mode` ∈ 4 值（per A/B test 限 demo+live_demo+live 跑，CHECK 可進一步限 `engine_mode IN ('demo','live_demo','live')`）
- CHECK: `traffic_split_ratio` ∈ (0, 1)
- NOT NULL: hypothesis_id, test_name, variant_type, control_config_json, treatment_config_json, traffic_split_ratio, started_at, status, engine_mode

### 2.2 `learning.ab_assignments`

**Tables 大綱**：
- PK: `assignment_id BIGSERIAL`
- FK: `test_id BIGINT` → `learning.ab_tests.test_id`
- Columns 大綱（7 fields）：
  - `assignment_id`, `test_id`, `decision_id TEXT` (live decision UUID / trace id)
  - `variant TEXT` (ENUM: `control` / `treatment`)
  - `assigned_at TIMESTAMPTZ NOT NULL`
  - `outcome_metric_value NUMERIC(18,8) NULL` (backfill after outcome known — e.g. PnL bps / hit rate)
  - `engine_mode TEXT NOT NULL`

**Constraints 大綱**：
- CHECK: `variant` ∈ 2 值 ENUM
- CHECK: `engine_mode` ∈ 4 值
- UNIQUE: `(test_id, decision_id)` — 同 decision 不重複 assign
- FK ON DELETE CASCADE: `test_id`（test 撤掉 → assignment 連同 drop）

**Indexes 大綱**：
- `(test_id, variant, assigned_at DESC)` — per-test variant timeline
- `(test_id, outcome_metric_value) WHERE outcome_metric_value IS NOT NULL` — backfilled outcome statistical query

### 2.3 `learning.ab_results`

**Tables 大綱**：
- PK: `(result_id, computed_at)` 複合
- FK: `test_id BIGINT` → `learning.ab_tests.test_id`
- Columns 大綱（10 fields）：
  - `result_id BIGSERIAL`, `test_id`, `computed_at TIMESTAMPTZ NOT NULL`
  - `n_control INTEGER`, `n_treatment INTEGER`
  - `mean_control NUMERIC(18,8)`, `mean_treatment NUMERIC(18,8)`
  - `effect_size NUMERIC(18,8)`, `msprt_log_likelihood_ratio NUMERIC(18,8)`
  - `msprt_decision TEXT` (ENUM: `continue` / `reject_h0_treatment_win` / `accept_h0_no_diff` / `reject_h0_control_win`)
  - `multiple_comparison_adjusted_p_value NUMERIC(18,8) NULL`
  - `engine_mode TEXT NOT NULL`

**Constraints 大綱**：
- CHECK: `msprt_decision` ∈ 4 值 ENUM
- CHECK: `engine_mode` ∈ 4 值
- NOT NULL: test_id, computed_at, n_control, n_treatment, msprt_decision, engine_mode

### 2.4 ENUM 列表 (per CR-X 對齊規則)

- `variant_type` ENUM 4 值 (parameter / sizing / trigger / overlay) — per H-5
- `ab_test_status` ENUM 5 值
- `ab_variant` ENUM 2 值 (control / treatment)
- `msprt_decision` ENUM 4 值

### 2.5 Hypertable 判斷

**結論：3 表均 regular table**。理由：
- `ab_tests`：低基數 ~hundreds row total（per-test config 行）
- `ab_assignments`：high cardinality per-decision row → 預估 ~1k decision/day × ~5 active test = ~5k row/day × 90d retention = ~450k row max；regular table + index 即足，且 retention 短可手動 truncate（不必 hypertable infra cost）
- `ab_results`：computed periodic snapshot ~daily × n_test = ~hundreds row/yr

---

## §3 Guard A/B/C Templates 大綱

### Guard A — table existence + FK target 對齊驗證

- 若 3 表已存在：驗 column 完整；缺即 RAISE
- 驗 `learning.hypotheses` 存在（V103 prereq for hypothesis_id FK）

### Guard B — 不適用

V108 不 ALTER 既有 column type；本 spec 不設 Guard B 段。

### Guard C — CHECK constraint + ENUM 值齊全 + index 對齊驗證

- `variant_type` ENUM 4 值齊全
- `ab_test_status` ENUM 5 值齊全
- `ab_variant` ENUM 2 值齊全
- `msprt_decision` ENUM 4 值齊全
- `engine_mode` CHECK 4 值齊全（3 表共用）
- UNIQUE constraint `(test_id, decision_id)` on ab_assignments 存在
- Indexes (≥ 2 partial + base) 對齊

---

## §4 Linux PG Empirical Dry-Run Checklist (placeholder)

### 4.1 必跑 SQL (3-5 條 placeholder query)

```bash
# Query 1: _sqlx_migrations head + V103 land 確認
ssh trade-core "psql -d trading_ai -c 'SELECT version, success FROM _sqlx_migrations WHERE version=103'"

# Query 2: V108 apply 後驗 3 表 + 4 ENUM 真建立
ssh trade-core "psql -d trading_ai -c \"SELECT table_name FROM information_schema.tables WHERE table_schema='learning' AND table_name LIKE 'ab_%' ORDER BY table_name\""

# Query 3: FK constraint 真設立
ssh trade-core "psql -d trading_ai -c \"SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid::regclass::text LIKE 'learning.ab_%' AND contype='f' ORDER BY conname\""

# Query 4: UNIQUE constraint (test_id, decision_id) 確認
ssh trade-core "psql -d trading_ai -c \"SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid='learning.ab_assignments'::regclass AND contype='u'\""

# Query 5: ENUM 真 reject 第 5 個 variant_type 值 (empirical INSERT test)
```

### 4.2 Idempotent 雙跑驗

per V055 5-round loop + V083/V084 incident precedent，V108.sql 必跑兩次：第二次必 0 RAISE / 0 重複 ENUM / 0 重複 index。

### 4.3 engine restart 實測

per a19797d 教訓：
- `restart_all.sh --rebuild` 後驗 engine.log 無 sqlx panic
- 驗 `_sqlx_migrations.success=t` for V108

---

## §5 Cross-V### Dependencies

per CR-9 cross-V### dependency graph：

| V### | 依賴 | 理由 |
|---|---|---|
| V108 | V103 (hypothesis_id FK) | per M9 share M4 hypothesis schema |
| V108 | 無其他 FK 依賴 | A/B framework 是獨立 governance layer |

**Sprint 1A-γ dispatch ordering**：V103 → V108；V108 可與 V105 (M2) / V109 (M8) / V111 (M10) 並行（無互相 FK）。

---

## §6 Cross-References

- v5.8 §2 M9 A/B framework: `srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md`
- ADR-0037 mSPRT mandate: `srv/docs/adr/0037-ab-testing-msprt.md`
- V103 spec (hypotheses FK target): `srv/docs/execution_plan/2026-05-21--v103_v104_earn_hypotheses_schema_spec.md`
- CR-9 cross-V### dependency graph: PA dispatch consolidation
- 範式參考 V103/V104 spec: 同上

---

## §7 Sign-off Table

| Role | Status | Date | Note |
|---|---|---|---|
| MIT Drafted (placeholder) | DONE | 2026-05-21 | Placeholder frontmatter + 大綱 reserve only |
| PA | PENDING | — | Full DDL Sprint 1A-γ |
| E4 | PENDING | — | Regression after IMPL |
| E5 | N/A | — | 3 表均 regular table; 無 hypertable/retention 驗需求 |
| PM | PENDING | — | Sprint 1A-γ closure |

**END V108 spec placeholder**
