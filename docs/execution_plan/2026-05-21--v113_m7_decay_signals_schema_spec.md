---
spec: V113 — M7 Decay Signals + Strategy Lifecycle Schema (Single Decay Authority)
date: 2026-05-21
author: MIT consultant draft for PA Sprint 1A-β dispatch (placeholder reserve)
phase: v5.8 Sprint 1A-β schema prerequisite (per assignment)
status: SPEC-PLACEHOLDER (frontmatter + 大綱 reserve; full DDL land Sprint 1A-β)
parent specs:
  - srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md §2 M7 Decay
  - CR-7 contract — M7 是 single decay authority (PA dispatch consolidation)
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

## §7 Sign-off Table

| Role | Status | Date | Note |
|---|---|---|---|
| MIT Drafted (placeholder) | DONE | 2026-05-21 | Placeholder frontmatter + 大綱 reserve only |
| PA | PENDING | — | Full DDL Sprint 1A-β |
| E4 | PENDING | — | Regression after IMPL |
| E5 | PENDING | — | Hypertable + retention 180d 驗 critical |
| PM | PENDING | — | Sprint 1A-β closure |

**END V113 spec placeholder**
