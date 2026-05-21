---
spec: V107 — M11 Replay Divergence Log Schema
date: 2026-05-21
author: MIT consultant draft for PA Sprint 1A-β dispatch (placeholder reserve)
phase: v5.8 Sprint 1A-β schema prerequisite (per assignment)
status: SPEC-PLACEHOLDER (frontmatter + 大綱 reserve; full DDL land Sprint 1A-β)
parent specs:
  - srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md §2 M11 Replay
  - srv/docs/adr/0038-replay-divergence-noise-floor.md (CR-14 已 land)
mirror precedent:
  - srv/docs/execution_plan/2026-05-21--v103_v104_earn_hypotheses_schema_spec.md (format reference)
  - srv/sql/migrations/V094__fills_close_maker_audit.sql (Guard A/B/C 範式)
scope: placeholder spec — 不寫 V107.sql, 不在 Mac 跑 SQL, 不執行 PG, full DDL 在 Sprint 1A-β 補完
---

# V107 M11 Replay Divergence Log Schema Migration Spec (PLACEHOLDER)

## §0 TL;DR

- **V107 新增 1 個 hypertable**：`learning.replay_divergence_log`（counterfactual replay execution vs live execution divergence audit trail）。
- **`divergence_level` ENUM 3 值**：`NOISE` / `WARN` / `CRITICAL`（per ADR-0038 + CR-7 spec）。
- **不含 `auto_demote` / `target_state` column**（per CR-7 contract — **M7 是 single decay authority**；M11 只發 signal 不發 action）。
- **Hot index `(replay_id ASC, ts DESC)`** — per-replay divergence timeline query 是 hot path。
- **Retention 90d auto-drop**（per E5 5.21 hypertable audit）。
- **依賴**：V103（hypothesis_id reference for hypothesis-grounded replay）+ V109（M8 anomaly cross-reference per CR-7 §5 4 級對齊）+ V113（M7 reference — M11 divergence signal 餵入 M7 decay authority）。
- **Sprint 1A-β schedule**：V107 是 M2（V105）+ M7（V113）的 prereq；必先 land。

---

## §1 Background

### 1.1 v5.8 §2 M11 module 出處

v5.8 主檔 §2 M11 Replay module 列出 counterfactual replay 系統：
- live execution trace → counterfactual replay engine
- replay 模擬 live 條件下 strategy decision + position + PnL
- 比對 replay output vs live actual → divergence metric
- divergence_level 分級（NOISE 屬正常 floating-point + ordering / WARN 屬可疑 / CRITICAL 屬 strategy logic drift）
- 信號餵 M7 decay authority + M2 overlay state machine + M8 anomaly events

### 1.2 Audit 來源

- MIT 2026-05-21 v5.8 audit Risk 6「M11 schema spec missing」
- ADR-0038 noise floor mandate（CR-14 已 land）
- CR-7 lifecycle alignment：M11 是 signal source，M7 是 single decay authority；M11 schema 不含 action column

---

## §2 Schema Outline (placeholder)

### 2.1 `learning.replay_divergence_log`

**Tables 大綱**：
- PK: `(divergence_id, ts)` 複合（per hypertable best practice）
- Columns 大綱（12 fields）：
  - `divergence_id BIGSERIAL`, `ts TIMESTAMPTZ NOT NULL`
  - `replay_id BIGINT NOT NULL` (FK to `learning.replay_runs.id` — 待 Sprint 1A-β 確認表)
  - `hypothesis_id BIGINT NULL` (FK to `learning.hypotheses.hypothesis_id` per V103 — hypothesis-grounded replay)
  - `strategy_name TEXT NOT NULL`
  - `symbol TEXT NOT NULL`
  - `divergence_metric_name TEXT NOT NULL` (e.g. `pnl_diff_bps`, `position_diff_qty`, `signal_logic_drift_score`)
  - `divergence_value NUMERIC(18,8) NOT NULL`
  - `divergence_level TEXT NOT NULL` (ENUM: `NOISE` / `WARN` / `CRITICAL`)
  - `noise_floor_threshold NUMERIC(18,8)` (per ADR-0038 — value < threshold 必標 NOISE)
  - `evidence_json JSONB` (含 raw live trace ID + replay output + diff breakdown)
  - `engine_mode TEXT NOT NULL`

**Constraints 大綱**：
- CHECK: `divergence_level` ∈ 3 值 ENUM
- CHECK: `engine_mode` ∈ 4 值 ENUM
- NOT NULL: `ts`, `replay_id`, `strategy_name`, `symbol`, `divergence_metric_name`, `divergence_value`, `divergence_level`, `engine_mode`
- FK: `replay_id` → `learning.replay_runs.id`（待確認）
- FK: `hypothesis_id` → `learning.hypotheses.hypothesis_id` NULL allowed（V103 prereq）

**Indexes 大綱**：
- Hypertable time index 內建（`ts`）
- **`(replay_id ASC, ts DESC)`** — hot path: per-replay timeline query
- `(divergence_level, ts DESC) WHERE divergence_level IN ('WARN','CRITICAL')` — alert dashboard partial index
- `(strategy_name, symbol, ts DESC)` — per-strategy-symbol divergence aggregation
- `(hypothesis_id, ts DESC) WHERE hypothesis_id IS NOT NULL` — hypothesis-grounded replay drill-down

### 2.2 ENUM 列表 (per CR-X 對齊規則)

- `divergence_level` ENUM 3 值（NOISE / WARN / CRITICAL — per ADR-0038 + CR-7）
- **不採 `target_state` ENUM**（per CR-7 — M7 single decay authority；M11 schema 只 signal 不 action）

### 2.3 Hypertable 判斷

**結論：MUST hypertable**。理由：
- Replay 頻率：每 live decision → 1 counterfactual replay → N divergence metric (typically 3-5 metric/replay)
- 估算 row 量：~1000 live decision/day × 5 strategy × 25 symbol × 4 metric avg = ~50k row/day = ~18M row/yr
- Hypertable 7d chunk + 7d compression + 90d retention（per E5 audit）

```sql
SELECT create_hypertable('learning.replay_divergence_log', 'ts',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists => TRUE);

ALTER TABLE learning.replay_divergence_log SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'strategy_name, symbol',
    timescaledb.compress_orderby = 'ts DESC'
);

SELECT add_compression_policy('learning.replay_divergence_log', INTERVAL '7 days');
SELECT add_retention_policy('learning.replay_divergence_log', INTERVAL '90 days');
```

### 2.4 CR-7 contract — NOT in V107 schema

**明示**：V107 schema 不含以下 column（per CR-7 single decay authority alignment）：
- ❌ `auto_demote_trigger` (M7 own this — V113)
- ❌ `target_state` (M2 own this — V105；M7 own decay_action_level — V113)
- ❌ `decay_recommendation` (M7 own — V113)

V107 只是 raw signal source；下游 M7/M2 consume signal 後決定 action。

---

## §3 Guard A/B/C Templates 大綱

### Guard A — table existence + 既有 schema 對齊驗證

- 若 `learning.replay_divergence_log` 已存在：驗 12 column 完整；缺即 RAISE
- 驗 `learning.hypotheses` 表存在（V103 prereq for hypothesis_id FK）
- 驗 `learning.replay_runs` 表存在（待 Sprint 1A-β 確認；可能在 V096/V097 之前 land 或在 V107 同 migration 內定義）
- 驗 TimescaleDB extension 存在

### Guard B — 不適用

V107 不 ALTER 既有 column type；本 spec 不設 Guard B 段。

### Guard C — CHECK constraint + ENUM 值齊全 + hypertable + index 對齊驗證

- `divergence_level` ENUM 3 值齊全（NOISE / WARN / CRITICAL）
- `engine_mode` CHECK 4 值齊全
- Hypertable 已建立 + chunk_time_interval = 7 days
- Compression policy + retention policy 存在
- Hot index `(replay_id ASC, ts DESC)` 存在 + column 順序對

---

## §4 Linux PG Empirical Dry-Run Checklist (placeholder)

### 4.1 必跑 SQL (3-5 條 placeholder query)

```bash
# Query 1: _sqlx_migrations head + V103/V109/V113 sequence 確認
ssh trade-core "psql -d trading_ai -c 'SELECT version, success FROM _sqlx_migrations WHERE version IN (103, 109, 113) ORDER BY version'"

# Query 2: learning.hypotheses (V103) 已 land 確認
ssh trade-core "psql -d trading_ai -c \"SELECT count(*) FROM information_schema.tables WHERE table_schema='learning' AND table_name='hypotheses'\""

# Query 3: learning.replay_runs 表名確認（待 PA C9 補資料）
ssh trade-core "psql -d trading_ai -c \"SELECT table_name FROM information_schema.tables WHERE table_schema='learning' AND table_name LIKE '%replay%'\""

# Query 4: V107 apply 後驗 hypertable + 3 ENUM + 4 index 真建立
ssh trade-core "psql -d trading_ai -c \"SELECT hypertable_name, num_chunks FROM timescaledb_information.hypertables WHERE hypertable_name='replay_divergence_log'\""

# Query 5: divergence_level ENUM 真 reject 4th value (empirical INSERT test)
```

### 4.2 Idempotent 雙跑驗

per V055 5-round loop + V083/V084 incident precedent，V107.sql 必跑兩次：第二次必 0 RAISE / 0 重複建 index / 0 重複建 hypertable / 0 重複 policy。

### 4.3 engine restart 實測

per a19797d 教訓：
- `restart_all.sh --rebuild` 後驗 engine.log 無 sqlx panic
- 驗 `_sqlx_migrations.success=t` for V107
- 驗 replay engine 接 V107 writer log（Sprint 1A-β writer 接線後）

---

## §5 Cross-V### Dependencies

per CR-9 cross-V### dependency graph：

| V### | 依賴 | 理由 |
|---|---|---|
| V107 | V103 (hypothesis_id FK) | hypothesis-grounded replay 必依 V103 hypotheses 表 |
| V107 | V109 (M8 anomaly cross-reference) | per CR-7 §5 4 級對齊 — divergence CRITICAL 同步寫 M8 anomaly event |
| V107 | V113 (M7 reference) | divergence signal 餵 M7 decay authority |
| V107 | V096 boundary (TimescaleDB extension) | hypertable infra prereq |

**Sprint 1A-β dispatch ordering**：V103 → V107 → V113（M7）→ V105 (M2)；V109 (M8) 與 V107 可並行（不互相 FK）。

---

## §6 Cross-References

- v5.8 §2 M11 Replay module: `srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md`
- ADR-0038 replay divergence noise floor: `srv/docs/adr/0038-replay-divergence-noise-floor.md` (CR-14 已 land)
- CR-7 lifecycle alignment（M7 single decay authority + M11 single signal source）: PA dispatch consolidation
- V103 spec: `srv/docs/execution_plan/2026-05-21--v103_v104_earn_hypotheses_schema_spec.md`
- 範式參考 V103/V104 spec: 同上

---

## §7 Sign-off Table

| Role | Status | Date | Note |
|---|---|---|---|
| MIT Drafted (placeholder) | DONE | 2026-05-21 | Placeholder frontmatter + 大綱 reserve only |
| PA | PENDING | — | Full DDL Sprint 1A-β |
| E4 | PENDING | — | Regression after IMPL |
| E5 | PENDING | — | Hypertable + retention 驗 critical |
| PM | PENDING | — | Sprint 1A-β closure |

**END V107 spec placeholder**
