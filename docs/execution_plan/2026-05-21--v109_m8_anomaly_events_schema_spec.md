---
spec: V109 — M8 Anomaly Events Schema (ATR-vol + Funding Dual-Axis)
date: 2026-05-21
author: MIT consultant draft for PA Sprint 1A-γ dispatch (placeholder reserve)
phase: v5.8 Sprint 1A-γ schema prerequisite (per assignment)
status: SPEC-PLACEHOLDER (frontmatter + 大綱 reserve; full DDL land Sprint 1A-γ)
parent specs:
  - srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md §2 M8 Anomaly + §8 ADR-0036
  - srv/docs/adr/0036-anomaly-detection-atr-vol-funding.md (CR-5 已 land)
mirror precedent:
  - srv/docs/execution_plan/2026-05-21--v103_v104_earn_hypotheses_schema_spec.md (format reference)
scope: placeholder spec — 不寫 V109.sql, 不在 Mac 跑 SQL, 不執行 PG, full DDL 在 Sprint 1A-γ 補完
---

# V109 M8 Anomaly Events Schema Migration Spec (PLACEHOLDER)

## §0 TL;DR

- **V109 新增 2 個 table**：`learning.anomaly_events`（hypertable — high-frequency anomaly snapshots）+ `learning.anomaly_severity_taxonomy`（regular table — 4 級 severity 定義 + threshold registry）。
- **`anomaly_severity` 4 值 ENUM**：`INFO` / `WARN` / `CRITICAL` / `HALT`（per CR-5 + CR-7 dedup — 與 M11 V107 NOISE/WARN/CRITICAL 對齊但 M8 多 HALT 級）。
- **不採 HMM / GARCH / Markov-switching 任何 state-based regime detection**（per ADR-0036 黑名單 — 這些方法 OpenClaw context 過 brittle）。
- **採 ATR-vol regime + funding state 雙 axis**（per ADR-0036 — 簡單 robust，threshold-based）。
- **依賴 V112**（M1 LAL cross-reference — anomaly HALT 觸 LAL 0→1 demote）。
- **Sprint 1A-γ schedule**：M8 是 cross-cutting observability 層；不阻擋其他 module（無 outgoing FK）。

---

## §1 Background

### 1.1 v5.8 §2 M8 module 出處 + §8 ADR-0036

v5.8 §2 M8 Anomaly events module 列出：
- ATR-vol regime axis：ATR (Average True Range) percentile 對 historical baseline
- Funding state axis：funding rate sign + magnitude + persistence
- 雙 axis 交叉 → regime classification（normal / high-vol / extreme-funding / squeeze 等）
- 4 級 severity 分層觸發不同 action（INFO log only / WARN audit / CRITICAL demote / HALT pause）

ADR-0036 明示黑名單：
- ❌ HMM（Hidden Markov Model）— crypto 條件下 transition matrix 不穩
- ❌ GARCH 系列 — 對 fat tail 校準差
- ❌ Markov-switching regression — 假設 violated
- ✅ ATR-vol + funding state 雙 axis — 簡單 threshold-based + robust

### 1.2 Audit 來源

- MIT 2026-05-21 v5.8 audit Risk 9「M8 schema spec missing + ADR-0036 黑名單未在 schema 明示」
- ADR-0036 ATR-vol + funding mandate（CR-5 已 land）
- CR-7 lifecycle alignment：M8 severity 4 級 (INFO/WARN/CRITICAL/HALT) 與 M11 divergence_level 3 級 (NOISE/WARN/CRITICAL) 對齊（M8 多 HALT 級）

---

## §2 Schema Outline (placeholder)

### 2.1 `learning.anomaly_events` (hypertable)

**Tables 大綱**：
- PK: `(event_id, detected_at)` 複合（per hypertable best practice）
- Columns 大綱（13 fields）：
  - `event_id BIGSERIAL`, `detected_at TIMESTAMPTZ NOT NULL`
  - `symbol TEXT NOT NULL`, `strategy_name TEXT NULL`
  - `anomaly_type TEXT NOT NULL` (ENUM: `atr_vol_spike` / `funding_extreme` / `funding_persistence` / `cross_axis_squeeze` / `liquidity_drop` / `cross_symbol_correlation_spike`)
  - `anomaly_severity TEXT NOT NULL` (ENUM 4 值: INFO / WARN / CRITICAL / HALT)
  - `atr_vol_percentile NUMERIC(5,4) NULL` (0-1 normalized)
  - `funding_rate_value NUMERIC(18,8) NULL`
  - `funding_state TEXT NULL` (ENUM: `positive_normal` / `positive_extreme` / `negative_normal` / `negative_extreme` / `flip_recent`)
  - `triggering_threshold_id BIGINT` (FK to `learning.anomaly_severity_taxonomy.threshold_id`)
  - `evidence_json JSONB` (raw market data snapshot + computed regime + ADR-0036 axis values)
  - `engine_mode TEXT NOT NULL`

**Constraints 大綱**：
- CHECK: `anomaly_type` ∈ 6 值 ENUM
- CHECK: `anomaly_severity` ∈ 4 值 ENUM (INFO / WARN / CRITICAL / HALT)
- CHECK: `funding_state` ∈ 5 值 ENUM (NULL allowed for atr_vol_spike-only anomaly)
- CHECK: `engine_mode` ∈ 4 值
- NOT NULL: detected_at, symbol, anomaly_type, anomaly_severity, triggering_threshold_id, engine_mode
- FK: `triggering_threshold_id` → `learning.anomaly_severity_taxonomy.threshold_id` ON DELETE RESTRICT

**Indexes 大綱**：
- Hypertable time index 內建（`detected_at`）
- `(anomaly_severity, detected_at DESC) WHERE anomaly_severity IN ('CRITICAL','HALT')` — alert dashboard partial index hot path
- `(symbol, detected_at DESC)` — per-symbol anomaly timeline
- `(strategy_name, detected_at DESC) WHERE strategy_name IS NOT NULL` — per-strategy anomaly drill-down
- `(anomaly_type, detected_at DESC)` — per-type aggregation

### 2.2 `learning.anomaly_severity_taxonomy` (regular table)

**Tables 大綱**：
- PK: `threshold_id BIGSERIAL`
- Columns 大綱（9 fields）：
  - `threshold_id`, `anomaly_type TEXT NOT NULL`, `severity TEXT NOT NULL`
  - `atr_vol_percentile_threshold NUMERIC(5,4) NULL`
  - `funding_rate_abs_threshold NUMERIC(18,8) NULL`
  - `funding_persistence_periods_threshold INTEGER NULL`
  - `cross_axis_condition_json JSONB NULL` (例如 atr_vol_percentile > 0.9 AND funding_state IN ('positive_extreme', 'negative_extreme'))
  - `defined_at TIMESTAMPTZ NOT NULL DEFAULT now()`
  - `active BOOLEAN NOT NULL DEFAULT true`

**Constraints 大綱**：
- CHECK: `severity` ∈ 4 值 ENUM
- CHECK: `anomaly_type` ∈ 6 值 ENUM（與 anomaly_events 對齊）
- UNIQUE: `(anomaly_type, severity)` WHERE `active=true` — 每組 (type, severity) 只一 active threshold

### 2.3 ENUM 列表 (per CR-X 對齊規則)

- `anomaly_type` ENUM 6 值
- `anomaly_severity` ENUM 4 值 (INFO / WARN / CRITICAL / HALT — per CR-5)
- `funding_state` ENUM 5 值

### 2.4 ADR-0036 黑名單 schema 反映

per ADR-0036，本 schema **明示不採**以下 column / pattern：
- ❌ `hmm_state` / `hmm_transition_prob` — HMM 路徑
- ❌ `garch_volatility` / `garch_residual` — GARCH 路徑
- ❌ `markov_switching_regime` — Markov-switching 路徑

僅採 ATR-vol percentile + funding state 雙 axis 為 column 主結構。

### 2.5 Hypertable 判斷

**結論**：
- `anomaly_events`：**MUST hypertable**（high-frequency；估算 ~hundreds-thousands event/day 隨 market vol）
- `anomaly_severity_taxonomy`：regular table（low cardinality ~dozens row total）

```sql
SELECT create_hypertable('learning.anomaly_events', 'detected_at',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists => TRUE);

ALTER TABLE learning.anomaly_events SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'symbol, anomaly_type',
    timescaledb.compress_orderby = 'detected_at DESC'
);

SELECT add_compression_policy('learning.anomaly_events', INTERVAL '7 days');
SELECT add_retention_policy('learning.anomaly_events', INTERVAL '90 days');
```

---

## §3 Guard A/B/C Templates 大綱

### Guard A — table existence + 既有 schema 對齊驗證

- 若 `learning.anomaly_events` 已存在：驗 13 column 完整；缺即 RAISE
- 若 `learning.anomaly_severity_taxonomy` 已存在：驗 9 column 完整；缺即 RAISE
- 驗 TimescaleDB extension 存在

### Guard B — 不適用

V109 不 ALTER 既有 column type；本 spec 不設 Guard B 段。

### Guard C — CHECK constraint + ENUM 值齊全 + ADR-0036 黑名單檢 + hypertable + index 對齊驗證

- `anomaly_severity` ENUM 4 值齊全（INFO / WARN / CRITICAL / HALT）
- `anomaly_type` ENUM 6 值齊全
- `funding_state` ENUM 5 值齊全
- `engine_mode` CHECK 4 值齊全（2 表共用）
- **ADR-0036 黑名單檢查**：if 任何 column name LIKE `hmm_%` OR `garch_%` OR `markov_%` → RAISE EXCEPTION
- Hypertable + compression policy + retention policy 存在
- Indexes 對齊

---

## §4 Linux PG Empirical Dry-Run Checklist (placeholder)

### 4.1 必跑 SQL (3-5 條 placeholder query)

```bash
# Query 1: _sqlx_migrations head 確認
ssh trade-core "psql -d trading_ai -c 'SELECT max(version) FROM _sqlx_migrations'"

# Query 2: TimescaleDB extension 確認
ssh trade-core "psql -d trading_ai -c \"SELECT extversion FROM pg_extension WHERE extname='timescaledb'\""

# Query 3: V109 apply 後驗 2 表 + hypertable + 3 ENUM 真建立
ssh trade-core "psql -d trading_ai -c \"SELECT table_name FROM information_schema.tables WHERE table_schema='learning' AND table_name LIKE 'anomaly_%' ORDER BY table_name\""

# Query 4: 4 severity 值真 reject 第 5 個 (empirical INSERT test)

# Query 5: ADR-0036 黑名單驗 (應 0 row)
ssh trade-core "psql -d trading_ai -c \"SELECT column_name FROM information_schema.columns WHERE table_schema='learning' AND table_name='anomaly_events' AND (column_name LIKE 'hmm_%' OR column_name LIKE 'garch_%' OR column_name LIKE 'markov_%')\""
```

### 4.2 Idempotent 雙跑驗

per V055 5-round loop + V083/V084 incident precedent，V109.sql 必跑兩次：第二次必 0 RAISE / 0 重複 hypertable / 0 重複 policy。

### 4.3 engine restart 實測

per a19797d 教訓：
- `restart_all.sh --rebuild` 後驗 engine.log 無 sqlx panic
- 驗 anomaly detector spawn log（Sprint 1A-γ writer 接線後）

---

## §5 Cross-V### Dependencies

per CR-9 cross-V### dependency graph：

| V### | 依賴 | 理由 |
|---|---|---|
| V109 | V112 (M1 LAL cross-reference) | anomaly HALT 觸 LAL 0→1 demote；M8 → M1 signal flow |
| V109 | V096 boundary (TimescaleDB extension) | hypertable infra prereq |

**注**：V109 不 FK depend V107（M11）— M11 divergence CRITICAL 在 application layer 同步寫 V109 anomaly event（per CR-7 §5 4 級對齊），不在 schema layer 強制 FK。

**Sprint 1A-γ dispatch ordering**：V109 可與 V105 (M2) / V108 (M9) / V111 (M10) 並行；V112 (M1 LAL) 必先 land for cross-reference 使用。

---

## §6 Cross-References

- v5.8 §2 M8 Anomaly module: `srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md`
- ADR-0036 ATR-vol + funding dual-axis: `srv/docs/adr/0036-anomaly-detection-atr-vol-funding.md` (CR-5 已 land)
- CR-7 lifecycle alignment（M8 severity 4 級 vs M11 divergence_level 3 級對齊）: PA dispatch consolidation
- V112 spec (M1 LAL): `srv/docs/execution_plan/2026-05-21--v112_m1_decision_lease_lal_tiers_schema_spec.md`
- 範式參考 V103/V104 spec: `srv/docs/execution_plan/2026-05-21--v103_v104_earn_hypotheses_schema_spec.md`

---

## §7 Sign-off Table

| Role | Status | Date | Note |
|---|---|---|---|
| MIT Drafted (placeholder) | DONE | 2026-05-21 | Placeholder frontmatter + 大綱 reserve only |
| PA | PENDING | — | Full DDL Sprint 1A-γ |
| E4 | PENDING | — | Regression after IMPL |
| E5 | PENDING | — | Hypertable + retention 驗 critical（anomaly_events） |
| PM | PENDING | — | Sprint 1A-γ closure |

**END V109 spec placeholder**
