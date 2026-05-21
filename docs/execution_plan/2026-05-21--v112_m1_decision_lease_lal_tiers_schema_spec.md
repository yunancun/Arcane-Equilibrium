---
spec: V112 — M1 Decision Lease LAL Tiers + Eligibility Log + Toggle Audit Schema
date: 2026-05-21
author: MIT consultant draft for PA Sprint 1A-β dispatch (placeholder reserve)
phase: v5.8 Sprint 1A-β schema prerequisite (per assignment)
status: SPEC-PLACEHOLDER (frontmatter + 大綱 reserve; full DDL land Sprint 1A-β)
parent specs:
  - srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md §2 M1 LAL
  - srv/docs/adr/0034-decision-lease-lal-rename.md (CR-2 已 land — Tier → LAL naming)
mirror precedent:
  - srv/docs/execution_plan/2026-05-21--v103_v104_earn_hypotheses_schema_spec.md (format reference)
scope: placeholder spec — 不寫 V112.sql, 不在 Mac 跑 SQL, 不執行 PG, full DDL 在 Sprint 1A-β 補完
---

# V112 M1 Decision Lease LAL Tiers Schema Migration Spec (PLACEHOLDER)

## §0 TL;DR

- **V112 新增 3 個 regular table**：`learning.decision_lease_lal_tiers`（per-strategy / per-overlay LAL config）+ `learning.lal_eligibility_log`（LAL evaluation event ledger）+ `learning.lal_toggle_audit`（LAL level transition audit trail）。
- **LAL 0-4（5 級）rename from Tier**（per ADR-0034 + CR-2 — naming change Tier 0-4 → LAL 0-4 以避免與 M10 discovery_tier A-E 命名衝突）。
- **核心 columns**：`lal_level INT` (0-4) / `lal_yes_rate_window_days INT` / `lal_min_advisory_sample INT` / `lal_pre_proposal_config_snapshot JSONB`。
- **UNIQUE constraint `(strategy, proposal_hash, lease_window_start)`**：同一 proposal hash 同 lease window 不重複 evaluate。
- **依賴 V113（M7 decay reference）**：LAL eligibility check 含「no incident last 90d」query → 必查 V113 `decay_signals` table。
- **Sprint 1A-β schedule**：M1 LAL 是 Decision Lease infra 核心；V112 必先於 M2 / M9 / M10 land。

---

## §1 Background

### 1.1 v5.8 §2 M1 module 出處 + ADR-0034

v5.8 §2 M1 Decision Lease LAL module 列出：
- LAL = Lease Approval Level（rename from Tier per ADR-0034 + CR-2）
- 5 級 0-4：LAL 0 = full manual approval / LAL 1 = governance auto-approve / LAL 2 = governance bypass-with-audit / LAL 3 = full auto / LAL 4 = bypass even audit (emergency only)
- per-strategy LAL config 由 cumulative yes-rate + sample size + recent incident free 三條件升級
- 命名 rename 動因：ADR-0034 解 M10 discovery_tier A-E 與 M1 tier 0-4 命名混淆

### 1.2 Audit 來源

- MIT 2026-05-21 v5.8 audit Risk 4「M1 LAL schema spec missing」
- ADR-0034 Tier → LAL rename mandate（CR-2 已 land）
- CR-2 PA dispatch consolidation

---

## §2 Schema Outline (placeholder)

### 2.1 `learning.decision_lease_lal_tiers`

**Tables 大綱**：
- PK: `lal_config_id BIGSERIAL`
- Columns 大綱（11 fields）：
  - `lal_config_id`, `strategy_name TEXT NOT NULL`, `overlay_id BIGINT NULL`
  - `lal_level INTEGER NOT NULL` (0-4)
  - `effective_from TIMESTAMPTZ NOT NULL`, `effective_to TIMESTAMPTZ NULL`
  - `lal_yes_rate_window_days INTEGER NOT NULL` (e.g. 30 days)
  - `lal_min_advisory_sample INTEGER NOT NULL` (per-level minimum sample count to qualify)
  - `lal_pre_proposal_config_snapshot JSONB NOT NULL` (config at upgrade evaluation time)
  - `governance_approval_id BIGINT` (FK to `governance.audit_log.id`)
  - `engine_mode TEXT NOT NULL`

**Constraints 大綱**：
- CHECK: `lal_level` ∈ {0, 1, 2, 3, 4}
- CHECK: `engine_mode` ∈ 4 值
- CHECK: `effective_to IS NULL OR effective_to > effective_from`
- NOT NULL: strategy_name, lal_level, effective_from, lal_yes_rate_window_days, lal_min_advisory_sample, lal_pre_proposal_config_snapshot, engine_mode

**Indexes 大綱**：
- `(strategy_name, overlay_id NULLS LAST, effective_from DESC)` — per-strategy-overlay LAL history
- `(strategy_name, effective_to) WHERE effective_to IS NULL` — current-active partial index hot path
- `(lal_level, effective_to) WHERE effective_to IS NULL AND lal_level >= 3` — high-LAL strategy audit (LAL 3+ 是 full auto，必額外監控)

### 2.2 `learning.lal_eligibility_log`

**Tables 大綱**：
- PK: `eligibility_id BIGSERIAL`
- Columns 大綱（13 fields）：
  - `eligibility_id`, `strategy_name TEXT NOT NULL`, `overlay_id BIGINT NULL`
  - `proposal_hash TEXT NOT NULL` (content hash of pre-proposal evaluation)
  - `lease_window_start TIMESTAMPTZ NOT NULL`, `lease_window_end TIMESTAMPTZ NOT NULL`
  - `current_lal_level INTEGER NOT NULL`, `proposed_lal_level INTEGER NULL` (NULL = no upgrade proposed)
  - `yes_rate_observed NUMERIC(5,4)`, `advisory_sample_observed INTEGER`
  - `incident_free_check_pass BOOLEAN NOT NULL` (依 V113 decay_signals query「no incident last 90d」)
  - `decision TEXT` (ENUM: `upgrade_approved` / `upgrade_rejected_insufficient` / `upgrade_rejected_incident` / `downgrade_triggered`)
  - `evidence_json JSONB`
  - `engine_mode TEXT NOT NULL`

**Constraints 大綱**：
- **UNIQUE: `(strategy_name, proposal_hash, lease_window_start)`** — 同 proposal hash 同 window 不重複 evaluate
- CHECK: `current_lal_level` ∈ {0, 1, 2, 3, 4}, `proposed_lal_level` ∈ {0, 1, 2, 3, 4} OR NULL
- CHECK: `decision` ∈ 4 值 ENUM
- CHECK: `engine_mode` ∈ 4 值
- NOT NULL: strategy_name, proposal_hash, lease_window_start, lease_window_end, current_lal_level, incident_free_check_pass, decision, engine_mode

**Indexes 大綱**：
- `(strategy_name, lease_window_start DESC)` — per-strategy eligibility timeline
- `(decision, lease_window_start DESC) WHERE decision LIKE '%rejected%'` — rejection audit hot path

### 2.3 `learning.lal_toggle_audit`

**Tables 大綱**：
- PK: `toggle_id BIGSERIAL`
- Columns 大綱（11 fields）：
  - `toggle_id`, `strategy_name TEXT NOT NULL`, `overlay_id BIGINT NULL`
  - `toggled_at TIMESTAMPTZ NOT NULL`
  - `from_lal_level INTEGER NOT NULL`, `to_lal_level INTEGER NOT NULL`
  - `direction TEXT NOT NULL` (ENUM: `upgrade` / `downgrade` / `emergency_demote`)
  - `triggering_eligibility_id BIGINT NULL` (FK to `learning.lal_eligibility_log.eligibility_id`)
  - `governance_approval_id BIGINT` (FK to `governance.audit_log.id`)
  - `evidence_json JSONB`
  - `engine_mode TEXT NOT NULL`

**Constraints 大綱**：
- CHECK: `from_lal_level` + `to_lal_level` ∈ {0,1,2,3,4}
- CHECK: `direction` ∈ 3 值 ENUM
- CHECK: `from_lal_level <> to_lal_level` (no-op toggle 拒)
- CHECK: `engine_mode` ∈ 4 值
- NOT NULL: strategy_name, toggled_at, from_lal_level, to_lal_level, direction, engine_mode

**Indexes 大綱**：
- `(strategy_name, toggled_at DESC)` — per-strategy toggle timeline
- `(direction, toggled_at DESC) WHERE direction='emergency_demote'` — emergency demote audit hot path

### 2.4 ENUM 列表 (per CR-X 對齊規則)

- `lal_eligibility_decision` ENUM 4 值
- `lal_toggle_direction` ENUM 3 值
- LAL level integer 0-4（CHECK constraint，非 TEXT ENUM — integer 利於 ORDER BY）

### 2.5 Hypertable 判斷

**結論：3 表均 regular table**。理由：
- `decision_lease_lal_tiers`：低基數 ~per-strategy 1-2 upgrade/yr × 5 strategy = ~10 row/yr
- `lal_eligibility_log`：medium ~daily evaluation × 5 strategy = ~2k row/yr；retention 短可 truncate
- `lal_toggle_audit`：稀有 ~hundreds row/yr 全域
- 無時序壓力；regular table + index 即足

---

## §3 Guard A/B/C Templates 大綱

### Guard A — table existence + FK target 對齊驗證

- 若 3 表已存在：驗 column 完整；缺即 RAISE
- 驗 `governance.audit_log` 存在（V098 prereq）
- 驗 `learning.decay_signals` 存在（V113 prereq for incident_free_check_pass query；如 V112 dispatch 在 V113 前需先 reserve placeholder）

### Guard B — 不適用

V112 不 ALTER 既有 column type；本 spec 不設 Guard B 段。

### Guard C — CHECK constraint + ENUM 值齊全 + UNIQUE + index 對齊驗證

- `lal_eligibility_decision` ENUM 4 值齊全
- `lal_toggle_direction` ENUM 3 值齊全
- `lal_level` CHECK [0, 4] integer bounds
- `engine_mode` CHECK 4 值齊全（3 表共用）
- **UNIQUE constraint `(strategy_name, proposal_hash, lease_window_start)` 真存在** on lal_eligibility_log
- Indexes 對齊

---

## §4 Linux PG Empirical Dry-Run Checklist (placeholder)

### 4.1 必跑 SQL (3-5 條 placeholder query)

```bash
# Query 1: _sqlx_migrations head + governance.audit_log V098 land 確認
ssh trade-core "psql -d trading_ai -c \"SELECT count(*) FROM information_schema.tables WHERE table_schema='governance' AND table_name='audit_log'\""

# Query 2: V113 (M7) land 確認（V112 依賴 V113 for decay_signals incident-free query）
ssh trade-core "psql -d trading_ai -c \"SELECT version, success FROM _sqlx_migrations WHERE version=113\""

# Query 3: V112 apply 後驗 3 表 + 2 ENUM + UNIQUE constraint 真建立
ssh trade-core "psql -d trading_ai -c \"SELECT table_name FROM information_schema.tables WHERE table_schema='learning' AND table_name IN ('decision_lease_lal_tiers','lal_eligibility_log','lal_toggle_audit')\""

# Query 4: lal_level CHECK 真 reject 5 (empirical INSERT test)
# 例：
# INSERT INTO learning.decision_lease_lal_tiers (..., lal_level, ...) VALUES (..., 5, ...);
# Expected: ERROR: violates check constraint

# Query 5: UNIQUE constraint 真 reject duplicate (empirical 2nd INSERT same key combo)
```

### 4.2 Idempotent 雙跑驗

per V055 5-round loop + V083/V084 incident precedent，V112.sql 必跑兩次：第二次必 0 RAISE / 0 重複 ENUM / 0 重複 UNIQUE / 0 重複 index。

### 4.3 engine restart 實測

per a19797d 教訓：
- `restart_all.sh --rebuild` 後驗 engine.log 無 sqlx panic
- 驗 `_sqlx_migrations.success=t` for V112

---

## §5 Cross-V### Dependencies

per CR-9 cross-V### dependency graph：

| V### | 依賴 | 理由 |
|---|---|---|
| V112 | V113 (M7 decay_signals) | LAL eligibility check `incident_free_check_pass` 依 V113 「no incident last 90d」query |
| V112 | V098 (governance.audit_log) | FK target；已 land |
| V112 | 無其他 V### M-module 直接 FK | M1 LAL 是獨立 governance 層 |

**Sprint 1A-β dispatch ordering**：V113 (M7) → V112 (M1 LAL)；M1 LAL 為其他 module 提供 lease infra → V112 必先於 M2 / M9 / M10 land。

---

## §6 Cross-References

- v5.8 §2 M1 LAL module: `srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md`
- ADR-0034 Tier → LAL rename: `srv/docs/adr/0034-decision-lease-lal-rename.md` (CR-2 已 land)
- V113 spec (M7 — decay_signals FK source): `srv/docs/execution_plan/2026-05-21--v113_m7_decay_signals_schema_spec.md`
- CR-2 PA dispatch consolidation: per v5.8 §11
- 範式參考 V103/V104 spec: `srv/docs/execution_plan/2026-05-21--v103_v104_earn_hypotheses_schema_spec.md`

---

## §7 Sign-off Table

| Role | Status | Date | Note |
|---|---|---|---|
| MIT Drafted (placeholder) | DONE | 2026-05-21 | Placeholder frontmatter + 大綱 reserve only |
| PA | PENDING | — | Full DDL Sprint 1A-β |
| E4 | PENDING | — | Regression after IMPL |
| E5 | N/A | — | 3 表均 regular table; 無 hypertable/retention 驗需求 |
| PM | PENDING | — | Sprint 1A-β closure |

**END V112 spec placeholder**
