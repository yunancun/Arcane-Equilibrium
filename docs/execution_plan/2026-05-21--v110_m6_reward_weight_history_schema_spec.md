---
spec: V110 — M6 Reward Weight History + Bayesian Opt Runs Schema
date: 2026-05-21
author: MIT consultant draft for PA Sprint 1A-β dispatch (placeholder reserve)
phase: v5.8 Sprint 1A-β schema prerequisite (per assignment)
status: SPEC-PLACEHOLDER (frontmatter + 大綱 reserve; full DDL land Sprint 1A-β)
parent specs:
  - srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md §2 M6 Reward Weight
mirror precedent:
  - srv/docs/execution_plan/2026-05-21--v103_v104_earn_hypotheses_schema_spec.md (format reference)
  - srv/sql/migrations/V094__fills_close_maker_audit.sql (Guard A/B/C 範式)
scope: placeholder spec — 不寫 V110.sql, 不在 Mac 跑 SQL, 不執行 PG, full DDL 在 Sprint 1A-β 補完
---

# V110 M6 Reward Weight History + Bayesian Opt Runs Schema Migration Spec (PLACEHOLDER)

## §0 TL;DR

- **V110 新增 2 個 regular table**：`learning.reward_weight_history`（per-strategy reward function weight time-series ledger）+ `learning.bayesian_opt_runs`（Bayesian optimization run audit + suggested-weight propose ledger）。
- **核心 weight columns 5 個**：`λ_dd`（drawdown penalty）+ `λ_tail`（tail risk penalty）+ `λ_turnover`（turnover penalty）+ `λ_slippage`（slippage penalty）+ `λ_decay`（decay penalty）— per v5.8 §2 M6 module。
- **Bounds + change rate enforcement**：每 weight 必有 lower/upper bound + per-update max_delta（防 wild swing）。
- **30% rollback 累積 cap**（per H-2）：M6 weight 自動 propose 之後 7 day window 內累積 reverted change ≥ 30% → 凍結 auto-propose，落 M6 → M2/M7 demote signal。
- **engine_mode CHECK 4 值齊全**；training filter 必 `IN ('live','live_demo')`。
- **Sprint 1A-β schedule**：M6 屬 governance + ML pipeline 中間層；不阻擋 critical path 但 reward weight tuning 是 alpha discovery 啟動條件。

---

## §1 Background

### 1.1 v5.8 §2 M6 module 出處

v5.8 §2 M6 Reward Weight module 列出：
- 每 strategy / per-overlay 有 5 weight：drawdown / tail / turnover / slippage / decay
- weight 由 Bayesian optimization（per-strategy 跑）每 N day 提 candidate update
- candidate 必走 governance approval + 不超 bounds + per-update delta cap
- 落 reward_weight_history audit trail
- 累積 7d window reverted ≥ 30% → 自動凍結 (H-2 rollback cap)

### 1.2 Audit 來源

- MIT 2026-05-21 v5.8 audit Risk 10「M6 schema spec missing」
- R4 5.21 ADR alignment audit「M6 ADR 待補（per R4 建議）」
- H-2 reward weight 30% rollback cap mandate

---

## §2 Schema Outline (placeholder)

### 2.1 `learning.reward_weight_history`

**Tables 大綱**：
- PK: `weight_history_id BIGSERIAL`
- Columns 大綱（13 fields）：
  - `weight_history_id`, `strategy_name TEXT NOT NULL`
  - `overlay_id BIGINT NULL` (FK to `learning.overlays.id`; NULL = strategy-base weight)
  - `effective_from TIMESTAMPTZ NOT NULL`, `effective_to TIMESTAMPTZ NULL` (NULL = current active)
  - `lambda_dd NUMERIC(18,8) NOT NULL`, `lambda_tail NUMERIC(18,8) NOT NULL`
  - `lambda_turnover NUMERIC(18,8) NOT NULL`, `lambda_slippage NUMERIC(18,8) NOT NULL`
  - `lambda_decay NUMERIC(18,8) NOT NULL`
  - `proposed_by TEXT` (ENUM: `bayesian_opt` / `manual_operator` / `governance_override` / `rollback_revert`)
  - `bayesian_run_id BIGINT NULL` (FK to `learning.bayesian_opt_runs.run_id` if proposed by bayesian_opt)
  - `governance_approval_id BIGINT NULL` (FK to `governance.audit_log.id`)
  - `engine_mode TEXT NOT NULL`

**Constraints 大綱**：
- CHECK: `lambda_*` ∈ [0, 10] (per H-2 bounds — λ 為 non-negative penalty weight)
- CHECK: `proposed_by` ∈ 4 值 ENUM
- CHECK: `engine_mode` ∈ 4 值
- CHECK: `effective_to IS NULL OR effective_to > effective_from`
- NOT NULL: strategy_name, effective_from, λ_*, proposed_by, engine_mode
- **Trigger / application-layer rule**: per-update Δ(λ_X) ≤ `max_delta_per_update`（per H-2 — wild swing 防護；max_delta 由 risk_config TOML 定）

**Indexes 大綱**：
- `(strategy_name, overlay_id NULLS LAST, effective_from DESC)` — per-strategy-overlay timeline
- `(strategy_name, effective_to) WHERE effective_to IS NULL` — current-active partial index (hot path)
- `(bayesian_run_id) WHERE bayesian_run_id IS NOT NULL` — Bayesian run drill-down

### 2.2 `learning.bayesian_opt_runs`

**Tables 大綱**：
- PK: `run_id BIGSERIAL`
- Columns 大綱（12 fields）：
  - `run_id`, `strategy_name TEXT NOT NULL`, `overlay_id BIGINT NULL`
  - `started_at TIMESTAMPTZ NOT NULL`, `ended_at TIMESTAMPTZ NULL`
  - `status TEXT` (ENUM: `running` / `completed_propose` / `completed_no_change` / `halted_error` / `halted_rollback_cap`)
  - `n_iterations INTEGER`, `objective_function TEXT` (e.g. `sharpe_minus_dd_penalty`)
  - `proposed_lambda_json JSONB NULL` (suggested 5 λ values + posterior mean + std)
  - `current_window_revert_pct NUMERIC(5,4) NULL` (7d window reverted change %; > 0.30 → halted_rollback_cap)
  - `evidence_json JSONB` (full Bayesian posterior + acquisition function trace)
  - `engine_mode TEXT NOT NULL`

**Constraints 大綱**：
- CHECK: `status` ∈ 5 值 ENUM (含 `halted_rollback_cap` per H-2)
- CHECK: `engine_mode` ∈ 4 值
- CHECK: `current_window_revert_pct` ∈ [0, 1]
- NOT NULL: strategy_name, started_at, status, n_iterations, objective_function, engine_mode

**Indexes 大綱**：
- `(strategy_name, started_at DESC)` — per-strategy run history
- `(status, started_at DESC) WHERE status='running'` — active run query
- `(status) WHERE status='halted_rollback_cap'` — H-2 rollback cap incident audit

### 2.3 ENUM 列表 (per CR-X 對齊規則)

- `weight_proposed_by` ENUM 4 值
- `bayesian_run_status` ENUM 5 值

### 2.4 H-2 30% Rollback Cap Schema 反映

H-2 mandate 在 schema layer 反映兩處：
1. `bayesian_opt_runs.status` 含 `halted_rollback_cap` ENUM 值（accounting for cap-triggered halts）
2. `bayesian_opt_runs.current_window_revert_pct` column（runtime compute 7d window reverted change ratio；application-layer 7d cron 跑）

實際 30% threshold 由 risk_config TOML 定（不 hardcode SQL）；schema 只 reserve column + ENUM。

### 2.5 Hypertable 判斷

**結論：2 表均 regular table**。理由：
- `reward_weight_history`：低基數 ~per-strategy 1-2 update/week × 5 strategy = ~500 row/yr
- `bayesian_opt_runs`：低基數 ~per-strategy 1 run/week × 5 strategy = ~250 row/yr
- 無時序壓力；regular table + index 即足

---

## §3 Guard A/B/C Templates 大綱

### Guard A — table existence + FK target 對齊驗證

- 若 2 表已存在：驗 column 完整；缺即 RAISE
- 驗 `governance.audit_log` 存在（V098 prereq）
- 驗 overlay registry table 存在（待 Sprint 1A-β 確認表名）

### Guard B — 不適用

V110 不 ALTER 既有 column type；本 spec 不設 Guard B 段。

### Guard C — CHECK constraint + ENUM 值齊全 + bounds + index 對齊驗證

- `weight_proposed_by` ENUM 4 值齊全
- `bayesian_run_status` ENUM 5 值齊全（含 `halted_rollback_cap`）
- `engine_mode` CHECK 4 值齊全（2 表共用）
- `lambda_*` CHECK [0, 10] bounds（5 column 共用）
- `current_window_revert_pct` CHECK [0, 1] bounds
- Indexes（≥ 3 partial + base on history; ≥ 3 on runs）對齊

---

## §4 Linux PG Empirical Dry-Run Checklist (placeholder)

### 4.1 必跑 SQL (3-5 條 placeholder query)

```bash
# Query 1: _sqlx_migrations head + governance.audit_log V098 land 確認
ssh trade-core "psql -d trading_ai -c \"SELECT count(*) FROM information_schema.tables WHERE table_schema='governance' AND table_name='audit_log'\""

# Query 2: V110 apply 後驗 2 表 + 2 ENUM 真建立
ssh trade-core "psql -d trading_ai -c \"SELECT table_name FROM information_schema.tables WHERE table_schema='learning' AND table_name IN ('reward_weight_history','bayesian_opt_runs')\""

# Query 3: λ bounds CHECK 真 reject 11.0 (empirical INSERT test 5 column 都試)

# Query 4: rollback_cap ENUM 值真存在
ssh trade-core "psql -d trading_ai -c \"SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid='learning.bayesian_opt_runs'::regclass AND conname LIKE '%status%check%'\""

# Query 5: FK constraint (history → runs, history → audit_log) 真設立
ssh trade-core "psql -d trading_ai -c \"SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid='learning.reward_weight_history'::regclass AND contype='f'\""
```

### 4.2 Idempotent 雙跑驗

per V055 5-round loop + V083/V084 incident precedent，V110.sql 必跑兩次：第二次必 0 RAISE / 0 重複 ENUM / 0 重複 index。

### 4.3 engine restart 實測

per a19797d 教訓：
- `restart_all.sh --rebuild` 後驗 engine.log 無 sqlx panic
- 驗 `_sqlx_migrations.success=t` for V110

---

## §5 Cross-V### Dependencies

per CR-9 cross-V### dependency graph：

| V### | 依賴 | 理由 |
|---|---|---|
| V110 | V098 (governance.audit_log) | FK target；已 land |
| V110 | overlay registry table | 待 Sprint 1A-β 確認表名 / 編號 |
| V110 | 無 outgoing FK 到其他 V### M-module | M6 是獨立 reward weight authority |

**Sprint 1A-β dispatch ordering**：V110 可獨立 land；不阻擋其他 module。

---

## §6 Cross-References

- v5.8 §2 M6 Reward Weight module: `srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md`
- ADR-alignment: per R4 建議補（M6 對應 ADR 待 PA dispatch 期 land）
- H-2 30% rollback cap: per v5.8 §2 M6
- CR-X 對應 PA dispatch consolidation: per v5.8 §11
- 範式參考 V103/V104 spec: `srv/docs/execution_plan/2026-05-21--v103_v104_earn_hypotheses_schema_spec.md`

---

## §7 Sign-off Table

| Role | Status | Date | Note |
|---|---|---|---|
| MIT Drafted (placeholder) | DONE | 2026-05-21 | Placeholder frontmatter + 大綱 reserve only |
| PA | PENDING | — | Full DDL Sprint 1A-β |
| E4 | PENDING | — | Regression after IMPL |
| E5 | N/A | — | 2 表均 regular table; 無 hypertable/retention 驗需求 |
| PM | PENDING | — | Sprint 1A-β closure |

**END V110 spec placeholder**
