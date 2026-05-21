---
spec: V105 — M2 Overlay State Transitions Schema
date: 2026-05-21
author: MIT consultant draft for PA Sprint 1A-γ dispatch (placeholder reserve)
phase: v5.8 Sprint 1A-γ schema prerequisite (per assignment)
status: SPEC-PLACEHOLDER (frontmatter + 大綱 reserve; full DDL land Sprint 1A-γ)
parent specs:
  - srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md §2 M2 Overlay
  - srv/docs/adr/0034-decision-lease-lal-rename.md (LAL naming alignment per CR-2)
  - srv/docs/adr/0038-replay-divergence-noise-floor.md (M11 → M2 dependency per CR-7)
mirror precedent:
  - srv/docs/execution_plan/2026-05-21--v103_v104_earn_hypotheses_schema_spec.md (format reference)
  - srv/sql/migrations/V094__fills_close_maker_audit.sql (Guard A/B/C 範式)
scope: placeholder spec — 不寫 V105.sql, 不在 Mac 跑 SQL, 不執行 PG, full DDL 在 Sprint 1A-γ 補完
---

# V105 M2 Overlay State Transitions Schema Migration Spec (PLACEHOLDER)

## §0 TL;DR

- **V105 新增 2 個 regular table**：`learning.overlay_state_transitions`（Overlay 5-state finite state machine ledger）+ `learning.overlay_counterfactual_to_state_hooks`（counterfactual replay → state advance trigger 紀錄）。
- **State machine 5 值**：`STATE_COUNTERFACTUAL_ONLY` → `SHADOW` → `ADVISORY` → `PRODUCTION` ↔ `DISABLED_AUTO`（per v5.8 §2 M2 module + CR-7 lifecycle alignment）。
- **Guard A/B/C 範式 mandatory**（per CLAUDE.md §七 V### migration 規範 + V055/V083/V084 incident chain）。
- **Hypertable 判斷 = 2 表均 regular table**（state transition events 屬低基數 hundreds/yr 級；無時序壓力）。
- **engine_mode CHECK 4 值齊全**（paper / demo / live_demo / live）；training filter `IN ('live','live_demo')` 必含兩值（per MIT memory baseline）。
- **依賴 V107（M11 replay_divergence_log）**：state advance condition 之一 = replay divergence < NOISE_FLOOR（per ADR-0038 CR-14）。
- **Sprint 1A-γ schedule**：M11（V107）先 land；M2（V105）跟後（state machine depends on replay signal）。

---

## §1 Background

### 1.1 v5.8 §2 module 出處

v5.8 主檔 §2 M2 Overlay module 列出 4-stage promotion ladder（counterfactual-only → shadow → advisory → production）+ disabled_auto auto-pause path。每 stage transition 必落 audit log（state_transitions table）+ trigger source 必標（counterfactual replay / advisory window pass / production canary pass 等）。

### 1.2 Audit 來源

- MIT 2026-05-21 v5.8 audit Risk 7「M2 state machine spec missing」
- E4 5.21 governance audit「overlay 5-state ledger 必需以避免 state inconsistency」
- E5 5.21 hypertable audit「state transitions 屬低基數無 hypertable 必要」
- R4 5.21 ADR alignment audit「ADR-0034 LAL naming + ADR-0038 replay floor 對應」

---

## §2 Schema Outline (placeholder)

### 2.1 `learning.overlay_state_transitions`

**Tables 大綱**：
- PK: `transition_id BIGSERIAL`
- FK: `overlay_id BIGINT` → `learning.overlays.id`（待 V107/V108 期確認 overlay registry table）
- Columns 大綱（10 fields）：
  - `transition_id`, `overlay_id`, `from_state`, `to_state`, `transition_ts`
  - `trigger_source` (ENUM: `manual_promote`, `counterfactual_pass`, `shadow_window_pass`, `advisory_canary_pass`, `auto_demote_replay_divergence`, `auto_demote_drawdown`)
  - `evidence_json` (JSONB 含 statistical thresholds / sample size / divergence level)
  - `governance_approval_id` (FK to governance.audit_log)
  - `engine_mode`, `created_at`

**Constraints 大綱**：
- CHECK: `from_state` + `to_state` ∈ 5 值 ENUM (`STATE_COUNTERFACTUAL_ONLY` / `SHADOW` / `ADVISORY` / `PRODUCTION` / `DISABLED_AUTO`)
- CHECK: `engine_mode` ∈ 4 值
- NOT NULL: `overlay_id`, `from_state`, `to_state`, `transition_ts`, `trigger_source`, `engine_mode`
- FK: `governance_approval_id` REFERENCES `governance.audit_log(id)` ON DELETE SET NULL

**Indexes 大綱**：
- `(overlay_id, transition_ts DESC)` — recent transitions per overlay
- `(to_state, transition_ts DESC) WHERE to_state IN ('PRODUCTION', 'DISABLED_AUTO')` — partial index hot-path
- `(trigger_source, transition_ts DESC) WHERE trigger_source LIKE 'auto_demote_%'` — auto-demote audit lookups

### 2.2 `learning.overlay_counterfactual_to_state_hooks`

**Tables 大綱**：
- PK: `hook_id BIGSERIAL`
- FK: `overlay_id BIGINT`, `counterfactual_replay_id BIGINT` → `learning.replay_runs.id`（待確認 replay registry 表名）
- Columns 大綱（7 fields）：
  - `hook_id`, `overlay_id`, `counterfactual_replay_id`, `evaluation_ts`
  - `pass_criteria_met` (BOOLEAN), `evidence_summary` (JSONB)
  - `engine_mode`

**Indexes 大綱**：
- `(overlay_id, evaluation_ts DESC)` — recent counterfactual evaluations per overlay

### 2.3 ENUM 列表 (per CR-X 對齊規則)

- `overlay_state` ENUM 5 值（per CR-7 lifecycle alignment with M7 decay states）
- `transition_trigger` ENUM 6 值（manual + 4 auto-promote + 2 auto-demote）

### 2.4 Hypertable 判斷

**結論：2 表均 regular table**。理由：
- state transition 事件 ~ low hundreds/yr（per overlay 預估 ~5-10 transitions/yr × ~10 overlays Y1 = ~100 row/yr）
- counterfactual hook 事件 ~ hundreds-thousands/yr（per overlay daily evaluation）
- 無時序壓力；regular table + index 即足

---

## §3 Guard A/B/C Templates 大綱

### Guard A — table existence + 既有 schema 對齊驗證

- 若 `learning.overlay_state_transitions` 已存在：驗 10 column 完整；缺即 RAISE
- 若 `learning.overlay_counterfactual_to_state_hooks` 已存在：驗 7 column 完整；缺即 RAISE
- 驗 `governance.audit_log` 存在（FK target，V098 prereq）
- 驗 overlay registry table 存在（待 Sprint 1A-γ 確認表名 = `learning.overlays` 或別名）

### Guard B — 不適用

V105 不 ALTER 既有 column type；本 spec 不設 Guard B 段。

### Guard C — CHECK constraint + ENUM 值齊全 + index 對齊驗證

- `overlay_state` ENUM 5 值齊全（STATE_COUNTERFACTUAL_ONLY / SHADOW / ADVISORY / PRODUCTION / DISABLED_AUTO）
- `transition_trigger` ENUM 6 值齊全
- `engine_mode` CHECK 4 值齊全（per CLAUDE.md §七 + MIT memory baseline）
- index `(overlay_id, transition_ts DESC)` 存在 + 順序對

---

## §4 Linux PG Empirical Dry-Run Checklist (placeholder)

### 4.1 必跑 SQL (3-5 條 placeholder query)

```bash
# Query 1: _sqlx_migrations head 確認 V103/V104/V105 sequence
ssh trade-core "psql -d trading_ai -c 'SELECT max(version), array_agg(version ORDER BY version DESC) FROM _sqlx_migrations LIMIT 1'"

# Query 2: overlay registry 表名確認（待 PA C9 補資料）
ssh trade-core "psql -d trading_ai -c \"SELECT table_name FROM information_schema.tables WHERE table_schema='learning' AND table_name LIKE '%overlay%'\""

# Query 3: governance.audit_log column 確認 FK target
ssh trade-core "psql -d trading_ai -c \"SELECT column_name, data_type FROM information_schema.columns WHERE table_schema='governance' AND table_name='audit_log' AND column_name='id'\""

# Query 4: V107 (M11) land 狀態確認（V105 依賴 V107）
ssh trade-core "psql -d trading_ai -c \"SELECT version, success FROM _sqlx_migrations WHERE version=107\""

# Query 5 (Round 1 dry-run)：跑 V105.sql 並驗 2 表存在 + 5 ENUM + 3 index
```

### 4.2 Idempotent 雙跑驗

per V055 5-round loop + V083/V084 incident precedent，V105.sql 必跑兩次：第二次必 0 RAISE / 0 重複建 index / exit code 0。

### 4.3 engine restart 實測

per a19797d 教訓 + memory `project_2026_05_02_p0_sqlx_hash_drift`：
- `restart_all.sh --rebuild` 後驗 engine.log 無 sqlx panic
- 驗 `_sqlx_migrations.success=t` for V105

---

## §5 Cross-V### Dependencies

per CR-9 cross-V### dependency graph：

| V### | 依賴 | 理由 |
|---|---|---|
| V105 | V107 (M11 replay_divergence_log) | state advance condition = divergence < NOISE_FLOOR；V107 必先 land |
| V105 | V098 (governance.audit_log) | FK target；已 land |
| V105 | overlay registry table | 待 Sprint 1A-γ 確認表名 / 編號（可能在更早 V### 或 V108）|

**Sprint 1A-γ dispatch ordering**：V107 (M11) → V105 (M2) → V108 (M9) 之 V### 順序。

---

## §6 Cross-References

- v5.8 §2 M2 Overlay module: `srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md`
- ADR-0034 LAL naming alignment (CR-2): `srv/docs/adr/0034-decision-lease-lal-rename.md`
- ADR-0038 replay divergence noise floor (CR-14): `srv/docs/adr/0038-replay-divergence-noise-floor.md`
- CR-7 lifecycle alignment: PA dispatch consolidation
- 範式參考 V103/V104 spec: `srv/docs/execution_plan/2026-05-21--v103_v104_earn_hypotheses_schema_spec.md`

---

## §7 Sign-off Table

| Role | Status | Date | Note |
|---|---|---|---|
| MIT Drafted (placeholder) | DONE | 2026-05-21 | Placeholder frontmatter + 大綱 reserve only |
| PA | PENDING | — | Full DDL Sprint 1A-γ |
| E4 | PENDING | — | Regression after IMPL |
| E5 | N/A | — | 2 表均 regular table; 無 hypertable/retention 驗需求 |
| PM | PENDING | — | Sprint 1A-γ closure |

**END V105 spec placeholder**
