---
spec: V105 — M2 Overlay State Transitions Schema (Hypertable Mandatory)
date: 2026-05-21
author: MIT (full DDL spec; lifts placeholder from earlier same-day frontmatter)
phase: v5.8 Sprint 1A-γ schema prerequisite CRITICAL deliverable
status: SPEC-FULL-V0(MIT 起草;待 PA C9 Linux PG dry-run 實測補資料 + Sprint 1A-γ reviewer 對齊後 SPEC-FINAL)
sprint: Sprint 1A-γ (DESIGN phase; IMPL 後續 sprint)
size estimate: 90-130 LOC SQL (CREATE TABLE 1 hypertable + 3 indexes + 1 mv + Guard A/C + compression + retention) + 70-100 hr E1 IMPL (含 Linux PG dry-run x 2 round + healthcheck wiring deferred to Sprint 1B)
depend on:
  - V096 boundary (TimescaleDB extension; drop dead learning tables)
  - V098 (governance.audit_log;FK target via counterfactual_log_ref placeholder uuid;cross-ref 非 hard FK)
  - V107 (M11 replay_divergence_log;state advance trigger source = m11_divergence;cross-ref query)
depended by:
  - V112 (M1 LAL) — overlay state ACTIVE 為 LAL Tier ≥ 2 reparam halt 之 prereq input(cross-ref 非 FK)
  - V109 (M8 anomaly) — overlay state COOLDOWN 觸發 source 之一 = m8_anomaly(cross-ref)
  - V107 (M11 replay) — divergence-driven WATCHING→ARMED 升階(cross-ref)
parent specs:
  - srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md §2 M2 Overlay
  - srv/docs/adr/0034-decision-lease-lal-rename.md (LAL Tier 0-4 對齊 per CR-2)
  - srv/docs/adr/0038-replay-divergence-noise-floor.md (M11 → M2 dependency per CR-7)
  - srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md §6 cross-V### dependency graph
mirror precedent:
  - srv/docs/execution_plan/2026-05-21--v106_m3_health_observations_schema_spec.md (V106 sister-V### 14-section full DDL 範式)
  - srv/docs/execution_plan/2026-05-21--v103_v104_earn_hypotheses_schema_spec.md (range 940 行 baseline)
  - srv/docs/execution_plan/2026-05-21--v103_v104_linux_pg_dry_run.md (Linux PG dry-run protocol 範式)
  - srv/sql/migrations/V094__fills_close_maker_audit.sql (Guard A/B/C + partial index 範式)
  - srv/sql/migrations/templates/schema_guard_template.sql (Guard A/B/C template)
scope: design / spec only — 不寫 V105.sql 實檔,不在 Mac 跑 SQL,不改 Rust/Python writer,不執行 PG,不擴張到 module 行為(PA/QC sub-agent 同時段在寫)
---

# V105 M2 Overlay State Transitions Schema Migration Spec

## §0 TL;DR

- **V105 新增 1 個 hypertable**:`learning.overlay_state_transitions`(per-overlay 5-state finite state machine event ledger)。
- **3 overlay_type**(per v5.8 §2 M2):`macro`(LAL Tier 0 baseline + macro regime)/ `onchain`(BTC/ETH on-chain signal)/ `regime`(volatility regime / trending vs ranging)。
- **5 state ENUM**(per v5.8 §2 M2 + ADR-0034 LAL Tier 0-4 對齊):`INACTIVE`(LAL Tier 0)→ `WATCHING`(LAL Tier 1)→ `ARMED`(LAL Tier 2)→ `ACTIVE`(LAL Tier 3)→ `COOLDOWN`(LAL Tier 4 reparam halt)。
- **5 trigger_type ENUM**:`m3_health`(M3 HEALTH_DEGRADED → COOLDOWN) / `m11_divergence`(M11 replay divergence > NOISE_FLOOR → WATCHING→ARMED) / `m8_anomaly`(M8 anomaly → ACTIVE→COOLDOWN) / `operator`(manual override) / `time_based`(scheduled dwell-time auto-transition)。
- **Hypertable mandatory**(per E5 5.21 audit + V106 範式):7d chunk + 30d compression policy + 90d retention(state transition events 估 ~50-200 row/day × 90d ~5k-18k row;但因 M11 replay 每日 backfill 觸發批次 transition,7d chunk 對 weekly rollup query pattern 對齊)。
- **engine_mode CHECK 5 值齊全**(paper / demo / live_demo / live / **replay**);本 spec 額外加 `replay` 值因 M11 nightly replay 寫入 counterfactual transitions(per ADR-0038 §Decision 5 + CR-7)。
- **`counterfactual_log_ref` UUID 欄位**:M11 replay-driven transition 需指向 counterfactual log;放置 UUID placeholder(non-FK;cross-ref query)。
- **Cross-V### dependencies**:V096 boundary(TimescaleDB extension)+ V098(governance.audit_log cross-ref via operator override 路徑)+ V107(M11 replay 之 cross-ref 路徑)。**無 hard FK**(M2 是觀測層 + state event log;FK 太重;cross-ref 走 query-time JOIN)。
- **5 audit field** per V103 EXTEND 範式:`created_by` / `created_at` / `updated_by` / `updated_at` / `source_version`。
- **Hot-path indexes 3 個**(per task spec):strategy-symbol-time / state_to-time / trigger_type-time。
- **Materialized view**(本 spec 加):`mv_latest_overlay_state_per_strategy` 預設 per-(strategy_id, symbol, overlay_type)最新 state(極熱 query pattern,M1 LAL eligibility check 每秒查)。
- **Sprint 1A-γ scheduling**:V107(M11)先 land → V105(M2)跟後(state advance depends on replay signal)。
- **Linux PG empirical dry-run mandatory**(per CLAUDE.md §Data, Migrations, And Validation + V055 5-round loop precedent)。

---

## §1 Context + 為什麼

### 1.1 v5.8 §2 M2 module 出處 + 動機

v5.8 主檔 §2 M2 Overlay module 列出 3 overlay_type + 5-state finite state machine ledger,跨 OpenClaw 多個 signal source:

| Overlay Type | Signal Source | 採樣頻率 | Active 預期狀態變動 |
|---|---|---|---|
| **macro** | Fed FOMC + CPI + jobs report + macro regime indicator | event-driven + daily | INACTIVE→WATCHING(macro shock 24h before)→ARMED(event window)→COOLDOWN(後 48h)|
| **onchain** | BTC realized vol(24h) + ETH gas + stablecoin flow + exchange netflow | hourly | INACTIVE→WATCHING(信號 PSI > 0.25)→ARMED(confirm > 1h)→ACTIVE(LAL Tier 3)→COOLDOWN |
| **regime** | volatility regime(ATR ratio) + trend vs range(ADX) + cross-asset correlation | per-bar(5m) | INACTIVE↔WATCHING 高頻切換(regime fluctuation) |

**row 量級估算**(per E5 hypertable audit + 5-state finite state):
- macro:每月 ~5 event × 4 state change/event = ~20 transition/month → ~240 row/yr
- onchain:每 day ~5 active signal × 4 transition = ~20 transition/day → ~7300 row/yr
- regime:每 day ~50 transition × 5 strategy × 25 symbol = ~6250 row/day → ~2.3M row/yr(**最大**)
- **合計 ~2.3M row/yr** (每 row 估 ~300 byte) = ~700 MB/yr (uncompressed)

**6 month +350-700 MB(已 compress 後)估算占 PG buffer (4-8 GB) 4-15%** → hypertable + compression mandatory(per E5 5.21 hypertable audit + V106 同精神)。

### 1.2 5-state finite state machine 對齊 ADR-0034 LAL Tier 0-4

per ADR-0034 LAL(Layered Approval Lease)Tier 0-4 + v5.8 §2 M2:

| State | LAL Tier | 描述 | 是否 reparam halt |
|---|---|---|---|
| `INACTIVE` | Tier 0 | overlay dormant(baseline) | NO |
| `WATCHING` | Tier 1 | signal detected 但未 confirm | NO |
| `ARMED` | Tier 2 | signal confirmed,reparam halt 候選 | YES(soft halt) |
| `ACTIVE` | Tier 3 | overlay 影響 strategy production decision | YES(hard halt) |
| `COOLDOWN` | Tier 4 | overlay disabled-auto;48h 後 INACTIVE | YES(hard halt) |

**5 state mutual transition matrix**:
- 正向(promote):INACTIVE → WATCHING → ARMED → ACTIVE(by `m11_divergence` / `m3_health` / `operator`)
- 逆向(demote):ACTIVE → COOLDOWN → INACTIVE(by `m8_anomaly` / `time_based` / `operator`)
- 跳階:INACTIVE → ACTIVE(operator emergency)/ ACTIVE → INACTIVE(operator rollback)

Schema-level **CHECK constraint 不強制 transition matrix**(application-side enforce;writer 負責);僅 enum 列 5 值。

### 1.3 5 trigger_type 動機

per v5.8 §2 M2 + CR-7 dedup contract(M3 = single health authority + M11 = single replay authority + M8 = single anomaly authority):

| Trigger | 來源 | 典型 transition |
|---|---|---|
| `m3_health` | M3 HEALTH_DEGRADED state | ACTIVE → COOLDOWN(reparam halt)|
| `m11_divergence` | M11 replay divergence > NOISE_FLOOR(per ADR-0038)| WATCHING → ARMED(signal confirmed)|
| `m8_anomaly` | M8 anomaly emit | ARMED → COOLDOWN(防雪球)|
| `operator` | Operator manual override(GUI/console)| 任意 transition |
| `time_based` | Scheduled dwell-time 自動 transition | COOLDOWN(>48h)→ INACTIVE |

**trigger_source_id BIGINT** 對應指向觸發來源表 PK(per trigger_type 不同表):
- `m3_health`:指向 `learning.health_observations.observation_id`
- `m11_divergence`:指向 `learning.replay_divergence_log.divergence_id`
- `m8_anomaly`:指向 `learning.anomaly_events.anomaly_id`(V109)
- `operator`:指向 `governance.audit_log.id`
- `time_based`:NULL(無單一 source row,timer 觸發)

**Schema-level FK 不強制**(per §1.5 cross-ref 設計);writer 負責 referential integrity。

### 1.4 `counterfactual_log_ref` UUID 設計

per ADR-0038 §Decision 5 + CR-7:M11 nightly replay → state transition 必走 counterfactual log path(每次 replay-driven transition 帶 UUID reference 指向 replay run)。

| 場景 | counterfactual_log_ref |
|---|---|
| M11 replay 觸發 transition | NOT NULL UUID(指向 replay_runs.replay_uuid)|
| 非 replay 觸發 transition(M3/M8/operator/time)| NULL allowed |

**non-FK placeholder UUID**:V112 (M1 LAL) cross-ref query 時走 join `replay_runs.replay_uuid = overlay_state_transitions.counterfactual_log_ref`;若 replay_runs row 被 retention drop,overlay_state_transitions 不破壞(FK 設計會 cascade 破壞)。

### 1.5 v5.8 §2 M2 與本 spec 衝突仲裁

v5.8 §2 M2 列「Overlay 4-stage promotion ladder(counterfactual-only → shadow → advisory → production)+ disabled_auto」(per Sprint 1A-γ placeholder 早期 draft);本 spec 採 PA dispatch §6 + ADR-0034 共識 **5-state finite state machine**(INACTIVE / WATCHING / ARMED / ACTIVE / COOLDOWN)。

**理由**:
1. 5-state 對齊 ADR-0034 LAL Tier 0-4 + 1 extra(COOLDOWN)= 完美 1:1 mapping
2. 4-stage promotion ladder 是 advisory promotion model,適用 model_registry 但不適用 overlay state machine(overlay 是 state observer 非 promotion candidate)
3. COOLDOWN 是 M3 → LAL hard halt 後的 disabled-auto recovery 中間層(per ADR-0034 Tier 4),原 4-stage ladder 漏此語義

### 1.6 Cross-V### 影響

| 下游 | M2 觸發路徑 | 是否 FK |
|---|---|---|
| **V112 M1 LAL** | overlay state = ACTIVE 為 LAL Tier ≥ 2 reparam halt 之 prereq input(per ADR-0034 + v5.8 §2 M1 line 140) | 否(cross-ref query;FK 太重) |
| **V107 M11 replay** | M11 divergence > NOISE_FLOOR → emit overlay state transition(per ADR-0038 §Decision 5) | 否(cross-ref query via counterfactual_log_ref UUID) |
| **V109 M8 anomaly** | M8 anomaly → 觸發 overlay state COOLDOWN(per CR-7 dedup contract) | 否(cross-ref query) |
| **V106 M3 health** | M3 HEALTH_DEGRADED → 觸發 overlay state COOLDOWN(per v5.8 §2 M3 line 140) | 否(cross-ref query) |
| **governance.audit_log** | operator override transition 必 cross-ref audit_log(per CLAUDE.md §四 hard boundary) | 否(cross-ref query) |

### 1.7 不在本 spec 範圍

- ❌ V105.sql 實檔寫作(E1 IMPL 工作)
- ❌ Mac 跑 V105 SQL(必 Linux PG empirical)
- ❌ Rust overlay state transition writer code(`rust/openclaw_engine/src/overlay/state_machine_writer.rs`;E1 IMPL 工作)
- ❌ Python healthcheck wiring(`helper_scripts/passive_wait_healthcheck.py` 加 `check_overlay_state_writer()`;Sprint 1B 工作)
- ❌ ML training pipeline integration(M2 是治理 + 觀測層,非 ML training feature)
- ❌ State machine transition matrix enforce(schema-level 不寫;writer-side enforce)
- ❌ Counterfactual replay engine 行為 spec(對應 V107 spec;本 spec 只列 cross-ref 不擴張)
- ❌ M8 / M11 / M3 cross-module trigger spec(對應 V109 / V107 / V106 各自 spec 寫;本 spec 只列 cross-ref 不擴張)

---

## §2 Schema Design

### 2.1 `learning.overlay_state_transitions` 表定義

```sql
CREATE TABLE IF NOT EXISTS learning.overlay_state_transitions (
    id                          BIGSERIAL,
    transition_at               TIMESTAMPTZ NOT NULL,
    overlay_type                TEXT NOT NULL
                                CHECK (overlay_type IN (
                                    'macro',
                                    'onchain',
                                    'regime'
                                )),
    strategy_id                 TEXT,
    symbol                      TEXT,
    state_from                  TEXT NOT NULL
                                CHECK (state_from IN (
                                    'INACTIVE',
                                    'WATCHING',
                                    'ARMED',
                                    'ACTIVE',
                                    'COOLDOWN'
                                )),
    state_to                    TEXT NOT NULL
                                CHECK (state_to IN (
                                    'INACTIVE',
                                    'WATCHING',
                                    'ARMED',
                                    'ACTIVE',
                                    'COOLDOWN'
                                )),
    dwell_sec                   INTEGER,
    trigger_type                TEXT NOT NULL
                                CHECK (trigger_type IN (
                                    'm3_health',
                                    'm11_divergence',
                                    'm8_anomaly',
                                    'operator',
                                    'time_based'
                                )),
    trigger_source_id           BIGINT,
    counterfactual_log_ref      UUID,
    evidence_json               JSONB,
    engine_mode                 TEXT NOT NULL
                                CHECK (engine_mode IN ('paper','demo','live_demo','live','replay')),
    created_by                  TEXT NOT NULL DEFAULT 'overlay_state_machine',
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by                  TEXT,
    updated_at                  TIMESTAMPTZ,
    source_version              TEXT NOT NULL DEFAULT 'V105',
    PRIMARY KEY (id, transition_at)
);
```

### 2.2 Column 設計理由

| Column | Type | NULL | 設計理由 |
|---|---|---|---|
| `id` | BIGSERIAL | NOT NULL | sequential ID(per hypertable best practice;PK 必含 partition column,因此複合 `(id, transition_at)`)|
| `transition_at` | TIMESTAMPTZ | NOT NULL | hypertable time dimension;UTC 統一(per CLAUDE.md §六 Mac/Linux runtime) |
| `overlay_type` | TEXT + CHECK 3 值 | NOT NULL | 3 overlay 類型顯式枚舉;crypto + OpenClaw signal source 完整覆蓋;新 overlay_type 需 amend ENUM(controlled drift)|
| `strategy_id` | TEXT | YES | 對應 strategy(如 `grid`、`ma`、`bb_breakout`);overlay_type='macro' 時可 NULL(macro overlay 影響所有 strategy);overlay_type ∈ ('onchain','regime') 時建議非 NULL |
| `symbol` | TEXT | YES | 對應 symbol(如 `BTCUSDT`);overlay_type='macro' 時 NULL(macro overlay 跨 symbol);overlay_type ∈ ('onchain','regime') 時建議非 NULL |
| `state_from` | TEXT + CHECK 5 值 | NOT NULL | 前一 state;ENUM 5 值嚴格 |
| `state_to` | TEXT + CHECK 5 值 | NOT NULL | 後一 state;ENUM 5 值嚴格;CHECK constraint **不強制** state_from ≠ state_to(no-op transition 由 application-side reject)|
| `dwell_sec` | INTEGER | YES | state_from 上次停留時間(秒);第一次觀測 NULL;用於 transition rate analysis + 7-day mean dwell 計算 |
| `trigger_type` | TEXT + CHECK 5 值 | NOT NULL | 5 trigger source 顯式枚舉;CR-7 dedup contract 對齊 M3 / M11 / M8 single authority + operator + time_based |
| `trigger_source_id` | BIGINT | YES | 對應 trigger_type 來源表 PK;trigger_type='time_based' 時 NULL(無 source row);其他 NOT NULL(application-side enforce)|
| `counterfactual_log_ref` | UUID | YES | M11 replay-driven transition 之 UUID reference;non-FK(per §1.5 cross-ref 設計);non-replay transition NULL |
| `evidence_json` | JSONB | YES | 富 context:trigger 詳情、threshold、computation context、上下文時間戳;debug 用 |
| `engine_mode` | TEXT + CHECK 5 值 | NOT NULL | 5 值齊全(paper / demo / live_demo / live / **replay**);本 V105 因 M11 nightly replay 寫 counterfactual transition 必加 `replay` 值(per ADR-0038)|
| `created_by` | TEXT + DEFAULT 'overlay_state_machine' | NOT NULL | per V103 EXTEND 範式;預設 writer process 名;允許 `overlay_state_machine` / `m11_replay_engine` / `m8_anomaly_detector` / `operator` / `system` 多 actor |
| `created_at` | TIMESTAMPTZ + DEFAULT now() | NOT NULL | row insert 時間(server-side trusted)|
| `updated_by` | TEXT | YES | 後續 update(若 evidence_json backfill)|
| `updated_at` | TIMESTAMPTZ | YES | last update 時間 |
| `source_version` | TEXT + DEFAULT 'V105' | NOT NULL | schema version tag;未來 schema migration audit;預設 V105 |

### 2.3 為什麼 engine_mode 加 `replay`(本 spec 唯一不對齊 V106 範式之處)

per ADR-0038 §Decision 5 + CR-7:M11 nightly replay engine 寫 counterfactual state transition 時必標 `engine_mode='replay'`(不污染 live / live_demo / demo / paper 統計)。

| 影響 | 處理 |
|---|---|
| training filter | 必 `IN ('live','live_demo')`(不含 replay,per CLAUDE.md §七 + MIT memory baseline)|
| M1 LAL eligibility check | 必 `IN ('live','live_demo')`(replay 不算 production evidence)|
| QC 統計 / Sharpe 計算 | 必 `IN ('live','live_demo')` |
| M11 replay engine audit | 反向 `engine_mode='replay'` filter |

**5 值 vs V106 4 值**:V106 (M3 health) 不需 replay 值(M3 health 是 live runtime observation,M11 replay 不寫 M3 row);V105 (M2 overlay) 需 replay 值(M11 replay-driven transition 是 counterfactual model 必要 audit trail)。

### 2.4 為什麼 trigger_source_id 不分 5 種 typed FK(per overlay_type 一個 FK)

設計考量:
- 5 種 trigger_type 對應 5 個不同表(M3 / M11 / M8 / governance / NULL)
- 若加 5 個 typed FK column(`trigger_m3_id` / `trigger_m11_id` / 等)→ 5 個 column 之中 4 個必 NULL;schema 浪費
- 若用 single BIGINT + trigger_type 軟連結 → CHECK constraint 不強制 referential integrity;writer 負責
- 採後者 + application-side enforce(per V106 cross-ref 設計 pattern)

### 2.5 為什麼 `state_from = state_to` no-op transition 不 CHECK reject

設計考量:
- M11 replay 寫 counterfactual transition 時偶爾觸發 no-op(state observer reading same state)
- CHECK reject → application-side 必 wrap try/except;增加 writer 複雜度
- application-side reject(writer 判斷 if state_from == state_to: return)更 simple
- audit trail 不丟失(即使 application-side reject,可在 evidence_json 標 no-op skip)

---

## §3 Hypertable / Partitioning

### 3.1 Hypertable 設定

```sql
SELECT create_hypertable(
    'learning.overlay_state_transitions',
    'transition_at',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists => TRUE
);
```

**chunk_time_interval = 7d 理由**(per `db-schema-design-financial-time-series` skill + V106 範式):
- ~6250 row/day(regime overlay 主導) × 7d = ~44k row/chunk
- chunk size ~13 MB (uncompressed)→ 適合 PG memory hint;小於 V106(因 V105 row volume 小)
- 7d 對齊 weekly rollup query pattern(M11 weekly counterfactual audit)
- 7d 對齊 M11 nightly replay 跨週 batch transition emit

### 3.2 Compression policy

```sql
ALTER TABLE learning.overlay_state_transitions SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'overlay_type, strategy_id, symbol',
    timescaledb.compress_orderby = 'transition_at DESC, id DESC'
);

SELECT add_compression_policy(
    'learning.overlay_state_transitions',
    INTERVAL '30 days'
);
```

- `compress_segmentby = 'overlay_type, strategy_id, symbol'`:同 overlay × strategy × symbol 連續 row segment 壓縮率最高(80-90%)
- `compress_orderby = 'transition_at DESC, id DESC'`:time-DESC 最近資料 close 在 chunk 邊界,decompress 成本最低
- 30d 後自動壓縮(per task spec 30d compress;與 V106 7d 差異:V105 hot read window 較長,M1 LAL eligibility query 跨 30d incident-free check 屬熱資料)

### 3.3 Retention policy

```sql
SELECT add_retention_policy(
    'learning.overlay_state_transitions',
    INTERVAL '90 days'
);
```

- 90d 後自動 drop chunk
- M1 LAL eligibility check 跨 90d incident-free 需熱資料(per V106 §8.3 同 pattern)
- long-term trend(>90d)走 daily aggregate 表(Sprint 1B+ 補)

### 3.4 為什麼 30d compress(vs V106 7d)

| 因子 | V106(M3 health)| V105(M2 overlay)|
|---|---|---|
| 寫入頻率 | 716k row/day | 6.3k row/day |
| 熱 query window | 24h(per-domain alert dashboard)| 30-90d(M1 LAL eligibility) |
| Compress 後 query 成本 | 高(decompress 大批量)| 中(decompress 小批量)|
| 推薦 compress 起點 | 7d(避免 hot 24h overlap) | 30d(避免 hot 30d eligibility query overlap)|

### 3.5 為什麼不採 30d 或 365d retention

per V106 §3.4 同邏輯:
- **30d 過短**:M1 LAL 90d incident-free 不可滿足
- **365d 過長**:占 storage 過多;M2 overlay state 是 operational signal 非 strategy alpha,90d 足夠;long-term trend 走 aggregate 表

---

## §4 Index Strategy

### 4.1 Hot-path query → index map

per OpenClaw `db-schema-design-financial-time-series` skill + v5.8 §2 M2 query pattern + task spec:

| Query pattern | 命中 index | 範例 SQL |
|---|---|---|
| per-strategy-symbol overlay timeline | `idx_overlay_strategy_symbol_transition` | `SELECT * FROM learning.overlay_state_transitions WHERE strategy_id='grid' AND symbol='BTCUSDT' ORDER BY transition_at DESC LIMIT 50` |
| state-driven alert dashboard | `idx_overlay_state_transition` | `SELECT * FROM learning.overlay_state_transitions WHERE state_to IN ('ARMED','ACTIVE','COOLDOWN') ORDER BY transition_at DESC` |
| trigger-type audit lookup | `idx_overlay_trigger_type` | `SELECT * FROM learning.overlay_state_transitions WHERE trigger_type='m11_divergence' ORDER BY transition_at DESC` |

### 4.2 Index DDL

```sql
-- 主要 hot-path: per-strategy-symbol overlay timeline (M1 LAL eligibility query)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_overlay_strategy_symbol_transition
    ON learning.overlay_state_transitions (strategy_id, symbol, transition_at DESC)
    WHERE strategy_id IS NOT NULL AND symbol IS NOT NULL;

-- State-driven dashboard hot-path (per state_to;non-INACTIVE 全索引,low cardinality)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_overlay_state_transition
    ON learning.overlay_state_transitions (state_to, transition_at DESC);

-- Trigger-type audit hot-path
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_overlay_trigger_type
    ON learning.overlay_state_transitions (trigger_type, transition_at DESC);
```

### 4.3 Partial index 理由(per V106 §4.3 同 pattern)

per `db-schema-design-financial-time-series` skill §4.2:partial index 對 filter 條件穩定的場景大幅縮小索引(60-80% 空間節省):
- `idx_overlay_strategy_symbol_transition` 採 `WHERE strategy_id IS NOT NULL AND symbol IS NOT NULL` partial:macro overlay 兩值均 NULL → 排除;節省 5-10% 索引空間
- `idx_overlay_state_transition` 不採 partial(state_to ENUM 5 值 cardinality 平均;partial 加複雜度無顯著收益)
- `idx_overlay_trigger_type` 不採 partial(trigger_type ENUM 5 值 cardinality 平均;partial 不需)

### 4.4 為什麼不加 `(counterfactual_log_ref, transition_at)` index

考量:
- `counterfactual_log_ref` UUID 是 M11 replay → M2 cross-ref query 之 join key
- 但 join 方向通常是 `replay_runs → overlay_state_transitions`(M11 主導查 transition)
- M11 replay 表(V107)應有 `replay_uuid` index;join 走 `overlay_state_transitions` 全表 scan + replay_runs index seek
- 若反向 query(per-transition 查 replay)罕見;不需顯式 index
- 若未來 Sprint 1B+ 反向 query 頻繁,加 `(counterfactual_log_ref) WHERE counterfactual_log_ref IS NOT NULL` partial GIN/btree

### 4.5 為什麼不加 `(engine_mode, transition_at)` index

per V106 §4.4 同邏輯:engine_mode CHECK 5 值 + 預期 `IN ('live','live_demo')` filter 在 99% query 中出現;但 cardinality 太低(5 值)→ index selectivity 不佳;PG 會用 bitmap scan;不需顯式 index。

---

## §5 Guard A / B / C(per CLAUDE.md §Data, Migrations, And Validation + V094 / V106 mirror)

V105 涉及 1 個 NEW hypertable CREATE,需 Guard A + Guard C(無 ALTER 既有 column 不需 Guard B)。

### 5.1 Guard A — table existence + 既有 schema 對齊驗證

```sql
-- ============================================================
-- Guard A: V105 預檢 — 若 learning.overlay_state_transitions 已存在,必驗 V105 spec
-- column 全俱在;缺即 RAISE。同時驗 TimescaleDB extension + V096 boundary + governance.audit_log
-- (operator override cross-ref target)。
-- ============================================================
DO $$
DECLARE v_missing TEXT[];
DECLARE v_ts_ver TEXT;
BEGIN
    -- TimescaleDB extension prereq (V096 boundary)
    SELECT extversion INTO v_ts_ver
    FROM pg_extension WHERE extname='timescaledb';
    IF v_ts_ver IS NULL THEN
        RAISE EXCEPTION
            'V105 Guard A FAIL: TimescaleDB extension missing. '
            'V096 boundary not satisfied. Apply V096 first.';
    END IF;

    -- learning.overlay_state_transitions 已存在的情境下 check column 完整性
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='learning' AND table_name='overlay_state_transitions'
    ) THEN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'id', 'transition_at', 'overlay_type',
            'strategy_id', 'symbol',
            'state_from', 'state_to', 'dwell_sec',
            'trigger_type', 'trigger_source_id', 'counterfactual_log_ref',
            'evidence_json', 'engine_mode',
            'created_by', 'created_at', 'updated_by', 'updated_at',
            'source_version'
        ]) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema='learning' AND table_name='overlay_state_transitions'
              AND column_name=c
        );
        IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
            RAISE EXCEPTION
                'V105 Guard A FAIL: learning.overlay_state_transitions exists but missing columns: %. '
                'Possible legacy stub conflict — resolve schema reconciliation before applying V105.',
                v_missing;
        END IF;
    END IF;

    -- governance.audit_log 必須存在(operator override trigger cross-ref target)
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='governance' AND table_name='audit_log'
    ) THEN
        RAISE EXCEPTION
            'V105 Guard A FAIL: governance.audit_log missing — '
            'V098 must apply before V105 (operator override cross-ref target). '
            'Verify _sqlx_migrations.';
    END IF;

    -- V107 replay_runs (M11) 必須存在(counterfactual_log_ref UUID cross-ref target)
    -- NOTE: 若 V107 表名最終 = learning.replay_runs,啟用此 block;否則待 PA C9 確認後 amend
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='learning' AND table_name='replay_runs'
    ) THEN
        RAISE NOTICE
            'V105 Guard A NOTE: learning.replay_runs (V107 M11) not yet land. '
            'counterfactual_log_ref UUID cross-ref will be soft (non-FK). '
            'Acceptable if V107 lands before M11 writer wire (Sprint 1B+).';
    END IF;
END $$;
```

### 5.2 Guard B — 不適用

V105 不 ALTER 既有 column;無 type-sensitive 檢查需求。

### 5.3 Guard C — CHECK constraint + ENUM 值齊全 + hypertable + index 對齊驗證

```sql
-- ============================================================
-- Guard C: V105 預檢 — 重跑 V105 時 idempotent 檢查 CHECK constraint +
-- hypertable + compression policy + retention policy + index 對齊
-- ============================================================
DO $$
DECLARE v_actual TEXT;
DECLARE v_chunk_interval BIGINT;
BEGIN
    -- overlay_type CHECK constraint 3 值齊全
    SELECT pg_get_constraintdef(oid) INTO v_actual
    FROM pg_constraint
    WHERE conrelid='learning.overlay_state_transitions'::regclass
      AND conname LIKE '%overlay_type%check%';
    IF v_actual IS NOT NULL THEN
        IF position('macro' IN v_actual) = 0
           OR position('onchain' IN v_actual) = 0
           OR position('regime' IN v_actual) = 0
        THEN
            RAISE EXCEPTION
                'V105 Guard C FAIL: learning.overlay_state_transitions overlay_type CHECK enum mismatch. '
                'Actual: %. Expected to contain all 3 overlay_type values (macro/onchain/regime).',
                v_actual;
        END IF;
    END IF;

    -- state_from CHECK 5 值齊全
    SELECT pg_get_constraintdef(oid) INTO v_actual
    FROM pg_constraint
    WHERE conrelid='learning.overlay_state_transitions'::regclass
      AND conname LIKE '%state_from%check%';
    IF v_actual IS NOT NULL THEN
        IF position('INACTIVE' IN v_actual) = 0
           OR position('WATCHING' IN v_actual) = 0
           OR position('ARMED' IN v_actual) = 0
           OR position('ACTIVE' IN v_actual) = 0
           OR position('COOLDOWN' IN v_actual) = 0
        THEN
            RAISE EXCEPTION
                'V105 Guard C FAIL: state_from CHECK enum mismatch. '
                'Actual: %. Expected INACTIVE/WATCHING/ARMED/ACTIVE/COOLDOWN.',
                v_actual;
        END IF;
    END IF;

    -- state_to CHECK 5 值齊全
    SELECT pg_get_constraintdef(oid) INTO v_actual
    FROM pg_constraint
    WHERE conrelid='learning.overlay_state_transitions'::regclass
      AND conname LIKE '%state_to%check%';
    IF v_actual IS NOT NULL THEN
        IF position('INACTIVE' IN v_actual) = 0
           OR position('WATCHING' IN v_actual) = 0
           OR position('ARMED' IN v_actual) = 0
           OR position('ACTIVE' IN v_actual) = 0
           OR position('COOLDOWN' IN v_actual) = 0
        THEN
            RAISE EXCEPTION
                'V105 Guard C FAIL: state_to CHECK enum mismatch. '
                'Actual: %. Expected INACTIVE/WATCHING/ARMED/ACTIVE/COOLDOWN.',
                v_actual;
        END IF;
    END IF;

    -- trigger_type CHECK 5 值齊全
    SELECT pg_get_constraintdef(oid) INTO v_actual
    FROM pg_constraint
    WHERE conrelid='learning.overlay_state_transitions'::regclass
      AND conname LIKE '%trigger_type%check%';
    IF v_actual IS NOT NULL THEN
        IF position('m3_health' IN v_actual) = 0
           OR position('m11_divergence' IN v_actual) = 0
           OR position('m8_anomaly' IN v_actual) = 0
           OR position('operator' IN v_actual) = 0
           OR position('time_based' IN v_actual) = 0
        THEN
            RAISE EXCEPTION
                'V105 Guard C FAIL: trigger_type CHECK enum mismatch. '
                'Actual: %. Expected m3_health/m11_divergence/m8_anomaly/operator/time_based.',
                v_actual;
        END IF;
    END IF;

    -- engine_mode CHECK 5 值齊全(本 V105 特有,加 replay)
    SELECT pg_get_constraintdef(oid) INTO v_actual
    FROM pg_constraint
    WHERE conrelid='learning.overlay_state_transitions'::regclass
      AND conname LIKE '%engine_mode%check%';
    IF v_actual IS NOT NULL THEN
        IF position('paper' IN v_actual) = 0
           OR position('demo' IN v_actual) = 0
           OR position('live_demo' IN v_actual) = 0
           OR position('live' IN v_actual) = 0
           OR position('replay' IN v_actual) = 0
        THEN
            RAISE EXCEPTION
                'V105 Guard C FAIL: engine_mode CHECK enum mismatch. '
                'Actual: %. Expected paper/demo/live_demo/live/replay (5 values; '
                'V105 adds replay for M11 counterfactual write path per ADR-0038).',
                v_actual;
        END IF;
    END IF;

    -- Hypertable 已建立 + chunk_time_interval = 7 days
    SELECT
        EXTRACT(EPOCH FROM time_interval) * 1000000  -- 轉 microseconds
    INTO v_chunk_interval
    FROM timescaledb_information.dimensions
    WHERE hypertable_name='overlay_state_transitions'
      AND column_name='transition_at';
    -- 7 days = 604800 sec = 604800000000 microseconds
    IF v_chunk_interval IS NOT NULL AND v_chunk_interval != 604800000000 THEN
        RAISE EXCEPTION
            'V105 Guard C FAIL: learning.overlay_state_transitions chunk_time_interval mismatch. '
            'Actual: % microseconds. Expected: 604800000000 (7 days).',
            v_chunk_interval;
    END IF;

    -- Compression policy 存在(30 day after) -- NOTICE only,migration body 會建
    IF NOT EXISTS (
        SELECT 1 FROM timescaledb_information.jobs
        WHERE proc_name='policy_compression'
          AND hypertable_name='overlay_state_transitions'
    ) THEN
        RAISE NOTICE 'V105 Guard C NOTE: compression policy not yet applied for overlay_state_transitions. '
                     'Will be added by main migration body.';
    END IF;

    -- Retention policy 存在(90 day after) -- NOTICE only,migration body 會建
    IF NOT EXISTS (
        SELECT 1 FROM timescaledb_information.jobs
        WHERE proc_name='policy_retention'
          AND hypertable_name='overlay_state_transitions'
    ) THEN
        RAISE NOTICE 'V105 Guard C NOTE: retention policy not yet applied for overlay_state_transitions. '
                     'Will be added by main migration body.';
    END IF;
END $$;
```

### 5.4 Guard 設計理念(per V094 / V106 mirror)

| Guard | 觸發場景 | RAISE 條件 | NOT RAISE 條件(idempotent)|
|---|---|---|---|
| A | NEW table 已存在但 column 缺;TimescaleDB extension 缺;governance.audit_log 缺 | RAISE | 全 column 俱在 / table 不存在(首次跑)|
| A V107 prereq | V107 replay_runs 不存在 | NOTICE(非 RAISE;soft cross-ref)| V107 已 land(熱路徑) |
| C ENUM | 4 ENUM(overlay_type 3 / state_from 5 / state_to 5 / trigger_type 5 / engine_mode 5)缺值 | RAISE | constraint 不存在(首次跑)/ 完整(重跑)|
| C hypertable | chunk_time_interval 不對 | RAISE | hypertable 不存在(首次跑) |
| C policy | compression / retention policy 首次跑不存在 | NOTICE(不 RAISE,migration body 會建)| policy 已存在重跑(skip)|

重跑 V105 第二次必不 RAISE(idempotency per CLAUDE.md §Data, Migrations, And Validation V055/V083/V084 incident precedent)。

---

## §6 Migration up + down SQL

### 6.1 Migration UP(完整 V105.sql 設計)

```sql
-- ============================================================
-- V105: learning.overlay_state_transitions + hypertable + compression + retention
-- M2 Overlay State Transitions Schema (3 overlay × 5 state × 5 trigger × hypertable)
-- ============================================================

-- Step 1: Guard A (per §5.1)
-- [全文見 §5.1]

-- Step 2: Guard C 預檢 (per §5.3 重跑 idempotency)
-- [全文見 §5.3]

-- Step 3: CREATE TABLE
CREATE TABLE IF NOT EXISTS learning.overlay_state_transitions (
    -- (per §2.1 完整 DDL)
    id                          BIGSERIAL,
    transition_at               TIMESTAMPTZ NOT NULL,
    overlay_type                TEXT NOT NULL CHECK (overlay_type IN ('macro','onchain','regime')),
    strategy_id                 TEXT,
    symbol                      TEXT,
    state_from                  TEXT NOT NULL CHECK (state_from IN ('INACTIVE','WATCHING','ARMED','ACTIVE','COOLDOWN')),
    state_to                    TEXT NOT NULL CHECK (state_to IN ('INACTIVE','WATCHING','ARMED','ACTIVE','COOLDOWN')),
    dwell_sec                   INTEGER,
    trigger_type                TEXT NOT NULL CHECK (trigger_type IN ('m3_health','m11_divergence','m8_anomaly','operator','time_based')),
    trigger_source_id           BIGINT,
    counterfactual_log_ref      UUID,
    evidence_json               JSONB,
    engine_mode                 TEXT NOT NULL CHECK (engine_mode IN ('paper','demo','live_demo','live','replay')),
    created_by                  TEXT NOT NULL DEFAULT 'overlay_state_machine',
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by                  TEXT,
    updated_at                  TIMESTAMPTZ,
    source_version              TEXT NOT NULL DEFAULT 'V105',
    PRIMARY KEY (id, transition_at)
);

-- Step 4: Hypertable
SELECT create_hypertable(
    'learning.overlay_state_transitions',
    'transition_at',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists => TRUE
);

-- Step 5: Compression settings
ALTER TABLE learning.overlay_state_transitions SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'overlay_type, strategy_id, symbol',
    timescaledb.compress_orderby = 'transition_at DESC, id DESC'
);

-- Step 6: Compression + Retention policies (idempotent)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM timescaledb_information.jobs
        WHERE proc_name='policy_compression' AND hypertable_name='overlay_state_transitions'
    ) THEN
        PERFORM add_compression_policy('learning.overlay_state_transitions', INTERVAL '30 days');
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM timescaledb_information.jobs
        WHERE proc_name='policy_retention' AND hypertable_name='overlay_state_transitions'
    ) THEN
        PERFORM add_retention_policy('learning.overlay_state_transitions', INTERVAL '90 days');
    END IF;
END $$;

-- Step 7: Hot-path indexes (CONCURRENTLY for non-blocking)
-- (per §4.2)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_overlay_strategy_symbol_transition
    ON learning.overlay_state_transitions (strategy_id, symbol, transition_at DESC)
    WHERE strategy_id IS NOT NULL AND symbol IS NOT NULL;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_overlay_state_transition
    ON learning.overlay_state_transitions (state_to, transition_at DESC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_overlay_trigger_type
    ON learning.overlay_state_transitions (trigger_type, transition_at DESC);

-- Step 8: Materialized view for latest overlay state per strategy×symbol (per §7)
-- (per §7 mv_latest_overlay_state_per_strategy 完整定義)

-- Step 9: COMMENT (audit metadata)
COMMENT ON TABLE learning.overlay_state_transitions IS
    'M2 Overlay State Transitions Hypertable (V105). 3 overlay × 5 state × 5 trigger event ledger; '
    'LAL Tier 0-4 對齊 per ADR-0034; engine_mode=replay 為 M11 counterfactual path per ADR-0038; '
    '7d chunk + 30d compression + 90d retention.';

COMMENT ON COLUMN learning.overlay_state_transitions.counterfactual_log_ref IS
    'M11 replay-driven transition UUID reference (non-FK; cross-ref to learning.replay_runs.replay_uuid). '
    'NULL for non-replay transitions (M3/M8/operator/time_based).';

COMMENT ON COLUMN learning.overlay_state_transitions.engine_mode IS
    '5 values 比 V106 多 replay; M11 nightly replay 寫 counterfactual transitions 必標 replay (per ADR-0038)。';
```

### 6.2 Migration DOWN(rollback;dev-only,production 慎用)

```sql
-- ============================================================
-- V105 ROLLBACK: 刪 hypertable + policies + indexes + mv + table
-- ⚠️ DESTRUCTIVE: 90d 之內所有 overlay state transitions 全 drop;不可恢復。
-- 僅 dev/staging 使用;production rollback 走 V### 升級而非 down。
-- ============================================================

-- Step 1: Drop materialized view (依賴 table,必先 drop)
DROP MATERIALIZED VIEW IF EXISTS learning.mv_latest_overlay_state_per_strategy CASCADE;

-- Step 2: Remove policies first (避免 dangling jobs)
SELECT remove_compression_policy('learning.overlay_state_transitions', if_exists => TRUE);
SELECT remove_retention_policy('learning.overlay_state_transitions', if_exists => TRUE);

-- Step 3: Drop indexes (CONCURRENTLY 不能在 transaction 內;rollback 走獨立 statement)
DROP INDEX CONCURRENTLY IF EXISTS learning.idx_overlay_trigger_type;
DROP INDEX CONCURRENTLY IF EXISTS learning.idx_overlay_state_transition;
DROP INDEX CONCURRENTLY IF EXISTS learning.idx_overlay_strategy_symbol_transition;

-- Step 4: Drop hypertable + table (CASCADE 處理 chunks)
DROP TABLE IF EXISTS learning.overlay_state_transitions CASCADE;
```

### 6.3 Idempotency 驗證

per V055 5-round loop + V083/V084 incident precedent + V106 §6.3 同 pattern,V105.sql 必跑兩次:
- 第一次:CREATE TABLE + hypertable + policies + indexes + mv → 0 RAISE / 0 ERROR
- 第二次:全 IF NOT EXISTS / 已 hypertable / 已 policies → 0 RAISE / 0 重複 policy

---

## §7 Materialized View `mv_latest_overlay_state_per_strategy`

### 7.1 動機

per v5.8 §2 M1 LAL eligibility query 頻率(每秒查):**per-(strategy_id, symbol, overlay_type) 最新 state** 是極熱 read pattern。直接 query `overlay_state_transitions` 大 hypertable 需 sort + DISTINCT ON,每次成本 ~ms 級;materialized view 預計算後 ~μs 級。

### 7.2 DDL

```sql
CREATE MATERIALIZED VIEW IF NOT EXISTS learning.mv_latest_overlay_state_per_strategy AS
SELECT DISTINCT ON (overlay_type, strategy_id, symbol)
    overlay_type,
    strategy_id,
    symbol,
    state_to AS current_state,
    transition_at AS latest_transition_at,
    trigger_type AS latest_trigger_type,
    dwell_sec AS prev_state_dwell_sec,
    engine_mode
FROM learning.overlay_state_transitions
WHERE engine_mode IN ('live','live_demo')   -- 不含 replay / paper / demo
ORDER BY overlay_type, strategy_id, symbol, transition_at DESC;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_latest_overlay_state_key
    ON learning.mv_latest_overlay_state_per_strategy (overlay_type, strategy_id, symbol);
```

### 7.3 Refresh 策略

```sql
-- 選項 A: 定期 cron refresh(per 5 minute)
-- 由 helper_scripts/cron_overlay_mv_refresh.sh 觸發
REFRESH MATERIALIZED VIEW CONCURRENTLY learning.mv_latest_overlay_state_per_strategy;

-- 選項 B: trigger-driven refresh(寫入時觸發;成本高)
-- ⚠️ 不採;在 6k row/day 寫入頻率下成本可接受但 cron refresh 更 robust
```

**採選項 A** cron 5 min refresh:
- M1 LAL eligibility 對 ≤ 5 min stale 容忍(state transition 非極實時決策)
- CONCURRENTLY refresh 不鎖 read query
- 失敗(refresh job 卡住)→ M3 health 監控(per V106 cross-ref)

### 7.4 為什麼不採 continuous aggregate(TimescaleDB native)

考量:
- continuous aggregate 適合 time-bucket aggregation(SUM/AVG/COUNT per time bucket)
- M2 latest state 是 DISTINCT ON 模式(非 aggregate);continuous aggregate 不適用
- materialized view + cron refresh 更直觀
- 未來 Sprint 1B+ 若加 daily transition count aggregate,用 continuous aggregate

---

## §8 Cross-V### Dependency + Cross-Ref Schema

### 8.1 Cross-V### dependency 圖

```
V096 (drop dead learning tables; TimescaleDB extension) ← V105 (prereq;hypertable infra)
V098 (governance.audit_log)                              ← V105 (operator override cross-ref target;非 FK)
V107 (M11 replay_runs)                                   ← V105 (counterfactual_log_ref UUID cross-ref;非 FK)
V105 (M2 overlay state transitions; standalone hypertable)
       │
       ├─→ V112 (M1 LAL) — state=ACTIVE 為 LAL Tier ≥ 2 reparam halt prereq (cross-ref query)
       ├─→ V109 (M8 anomaly) — trigger_type=m8_anomaly 路徑反向 audit (cross-ref query)
       ├─→ V107 (M11 replay) — trigger_type=m11_divergence + counterfactual_log_ref 對齊 (cross-ref query)
       └─→ V106 (M3 health) — trigger_type=m3_health + M3 HEALTH_DEGRADED 對齊 (cross-ref query)
```

### 8.2 為什麼 M2 是 standalone hypertable(無 hard FK)

per V106 §8.2 同邏輯 + `db-schema-design-financial-time-series` skill §5(engine_mode 隔離 + FK 設計):
- M2 是 event-driven state observer 不是 governance object
- FK 太重(每 INSERT 都查 FK target;state transition 雖 6k/day 但 FK 對 4 個不同表)
- cross-ref query 走 join-time fetch(per V083 / V094 / V106 既有 pattern)

### 8.3 V112 (M1 LAL) cross-ref pattern

```sql
-- 例 1: M1 LAL Tier 升階 eligibility check 需查 M2 overlay state COOLDOWN-free 90d
SELECT COUNT(*) FROM learning.overlay_state_transitions
WHERE strategy_id = 'grid'
  AND symbol = 'BTCUSDT'
  AND state_to = 'COOLDOWN'
  AND transition_at > now() - INTERVAL '90 days'
  AND engine_mode IN ('live','live_demo');
-- > 0 → eligibility fail

-- 例 2: M1 LAL Tier 2+ reparam halt 即時查當前 overlay state
SELECT current_state, latest_transition_at
FROM learning.mv_latest_overlay_state_per_strategy
WHERE overlay_type = 'regime'
  AND strategy_id = 'grid'
  AND symbol = 'BTCUSDT';
-- current_state IN ('ARMED','ACTIVE','COOLDOWN') → reparam halt
```

### 8.4 V107 (M11 replay) cross-ref pattern

```sql
-- 例: M11 replay 觸發 transition;event-driven INSERT
INSERT INTO learning.overlay_state_transitions
    (transition_at, overlay_type, strategy_id, symbol,
     state_from, state_to, dwell_sec,
     trigger_type, trigger_source_id, counterfactual_log_ref,
     evidence_json, engine_mode)
VALUES
    (now(), 'regime', 'grid', 'BTCUSDT',
     'WATCHING', 'ARMED', 7200,
     'm11_divergence', $1, $2,  -- $1 = divergence_log.id, $2 = replay_uuid UUID
     jsonb_build_object(
         'divergence_metric', 0.08,
         'noise_floor', 0.05,
         'replay_run_id', $1
     ),
     'replay');  -- ⚠️ engine_mode='replay' 區分 live counterfactual
```

### 8.5 V109 (M8 anomaly) cross-ref pattern

```sql
-- 例: M8 anomaly emit → M2 COOLDOWN transition
INSERT INTO learning.overlay_state_transitions
    (transition_at, overlay_type, strategy_id, symbol,
     state_from, state_to, dwell_sec,
     trigger_type, trigger_source_id,
     evidence_json, engine_mode)
VALUES
    (now(), 'onchain', 'bb_breakout', 'ETHUSDT',
     'ACTIVE', 'COOLDOWN', 18000,
     'm8_anomaly', $1,  -- $1 = anomaly_events.anomaly_id
     jsonb_build_object('severity', 'CRITICAL', 'anomaly_id', $1),
     'live');
```

### 8.6 V106 (M3 health) cross-ref pattern

```sql
-- 例: M3 HEALTH_DEGRADED → M2 COOLDOWN transition
INSERT INTO learning.overlay_state_transitions
    (transition_at, overlay_type, strategy_id, symbol,
     state_from, state_to, dwell_sec,
     trigger_type, trigger_source_id,
     evidence_json, engine_mode)
VALUES
    (now(), 'macro', NULL, NULL,  -- macro overlay 跨 strategy/symbol
     'ACTIVE', 'COOLDOWN', 86400,
     'm3_health', $1,  -- $1 = health_observations.observation_id
     jsonb_build_object('domain', 'ws_latency', 'state', 'HEALTH_DEGRADED'),
     'live');
```

### 8.7 為什麼 V112 / V107 / V109 / V106 走 cross-ref 而非 FK

per V106 §8.6 同 table:

| 設計選擇 | 優 | 缺 | 採用 |
|---|---|---|---|
| **FK constraint** | 強約束;join 簡單 | INSERT cost(每筆查 FK target);schema drift 風險;hard dependency 鎖 dispatch sequence | ❌ 不採 |
| **Cross-ref query (本 spec)** | INSERT 0 overhead;dispatch sequence 解耦 | 弱約束;依 application logic 維持 referential integrity;需 healthcheck 補 | ✅ 採 |

---

## §9 Linux PG Empirical Dry-Run Protocol(mandatory)

per CLAUDE.md §Data, Migrations, And Validation + `feedback_v_migration_pg_dry_run.md` + V055 5-round loop / V083 / V084 incident chain + V106 §9 範式,V105 涉及:
- TimescaleDB extension hypertable creation (PG-specific syntax)
- compression / retention policy add_*_policy() function 真實返回
- partial index CONCURRENTLY 在 hypertable chunks 上的行為
- CHECK constraint ENUM runtime semantic(5 ENUM × 4-5 值)
- Materialized view CONCURRENTLY refresh 行為
- UUID column non-FK soft reference 行為

**必先 Linux PG empirical 驗證**,禁 Mac mock pytest 代替。

### 9.1 PA C9 待補的 PG reflection query(spec sign-off 前必補)

per CLAUDE.md `docs/agents/context-loading.md` "PG Connection Examples"(Linux runtime authoritative):

```bash
# Connection (per V103/V104/V106 dry-run §1):
# psql -h 127.0.0.1 -p 5432 -U trading_admin -d trading_ai
# .pgpass: *:5432:trading_ai:trading_admin:****

# Query 1: _sqlx_migrations head 確認
ssh trade-core "PGPASSWORD=\$(cat ~/.pgpass | grep trading_ai | cut -d: -f5) psql -h 127.0.0.1 -p 5432 -U trading_admin -d trading_ai -c 'SELECT max(version) FROM _sqlx_migrations'"
# Expected: ≥ V098 (V096 boundary + V097 LG-5 + V098 governance.audit_log 都 land)

# Query 2: TimescaleDB extension 確認
ssh trade-core "PGPASSWORD=\$(cat ~/.pgpass | grep trading_ai | cut -d: -f5) psql -h 127.0.0.1 -p 5432 -U trading_admin -d trading_ai -c \"SELECT extversion FROM pg_extension WHERE extname='timescaledb'\""
# Expected: ≥ 2.13 (per OpenClaw TimescaleDB minimum)

# Query 3: governance.audit_log 已 land 驗
ssh trade-core "PGPASSWORD=\$(cat ~/.pgpass | grep trading_ai | cut -d: -f5) psql -h 127.0.0.1 -p 5432 -U trading_admin -d trading_ai -c \"SELECT count(*) FROM information_schema.tables WHERE table_schema='governance' AND table_name='audit_log'\""
# Expected: 1 (V098 land 後)

# Query 4: V107 (M11) replay_runs table 是否已存在(V105 counterfactual_log_ref cross-ref)
ssh trade-core "PGPASSWORD=\$(cat ~/.pgpass | grep trading_ai | cut -d: -f5) psql -h 127.0.0.1 -p 5432 -U trading_admin -d trading_ai -c \"SELECT table_name FROM information_schema.tables WHERE table_schema='learning' AND table_name='replay_runs'\""
# Expected: 0 rows OR 1 row;0 rows 則 Guard A NOTICE-only(soft cross-ref);1 row 表示 V107 已先 land

# Query 5: learning.overlay_state_transitions 是否已存在(legacy stub conflict 檢測)
ssh trade-core "PGPASSWORD=\$(cat ~/.pgpass | grep trading_ai | cut -d: -f5) psql -h 127.0.0.1 -p 5432 -U trading_admin -d trading_ai -c \"SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema='learning' AND table_name='overlay_state_transitions'\""
# Expected: 0 rows (greenfield); 若 1 row → 觸 Guard A 反向檢查
```

**待 PA C9 補資料的 5 處 placeholder**(spec sign-off 前必更新):
1. `_sqlx_migrations` head 真實 = ?
2. TimescaleDB extension version 真實 = ?
3. governance.audit_log 已 land 確認 = ?
4. V107 (M11) replay_runs land 狀態 = ?(影響 Guard A NOTICE vs HARD enforce 切換)
5. learning.overlay_state_transitions stub 不存在確認 = ?

### 9.2 Round 1 — V105 SQL 真實 PG semantic empirical 驗證

```bash
# ssh trade-core 執行(不在 Mac 跑)
ssh trade-core "
  cd ~/BybitOpenClaw/srv && \
  PGPASSWORD=\$(cat ~/.pgpass | grep trading_ai | cut -d: -f5) \
  psql -h 127.0.0.1 -p 5432 -U trading_admin -d trading_ai \
    -v ON_ERROR_STOP=1 -f sql/migrations/V105__m2_overlay_state_transitions_hypertable.sql
"
```

**Round 1 必驗 10 項**(empirical SELECT verify after V105 apply):

```sql
-- 1. learning.overlay_state_transitions 表存在 + 18 columns
SELECT count(*) FROM information_schema.columns
WHERE table_schema='learning' AND table_name='overlay_state_transitions';
-- Expected: 18

-- 2. Hypertable 真建立 + chunk_time_interval = 7 days
SELECT hypertable_name, time_interval, column_name
FROM timescaledb_information.dimensions
WHERE hypertable_name='overlay_state_transitions';
-- Expected: 1 row; time_interval = '7 days'; column_name = 'transition_at'

-- 3. Compression policy 真設定(30 day after)
SELECT proc_name, hypertable_name, schedule_interval, config
FROM timescaledb_information.jobs
WHERE proc_name='policy_compression' AND hypertable_name='overlay_state_transitions';
-- Expected: 1 row; config 含 compress_after = '30 days'

-- 4. Retention policy 真設定(90 day after)
SELECT proc_name, hypertable_name, config
FROM timescaledb_information.jobs
WHERE proc_name='policy_retention' AND hypertable_name='overlay_state_transitions';
-- Expected: 1 row; config 含 drop_after = '90 days'

-- 5. overlay_type CHECK 3 值齊全
SELECT pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid='learning.overlay_state_transitions'::regclass AND conname LIKE '%overlay_type%check%';
-- Expected: 含 macro/onchain/regime

-- 6. state_from + state_to CHECK 5 值齊全
SELECT conname, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid='learning.overlay_state_transitions'::regclass
  AND (conname LIKE '%state_from%check%' OR conname LIKE '%state_to%check%');
-- Expected: 2 rows; both 含 INACTIVE/WATCHING/ARMED/ACTIVE/COOLDOWN

-- 7. trigger_type CHECK 5 值齊全
SELECT pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid='learning.overlay_state_transitions'::regclass AND conname LIKE '%trigger_type%check%';
-- Expected: 含 m3_health/m11_divergence/m8_anomaly/operator/time_based

-- 8. engine_mode CHECK 5 值齊全(本 V105 特有 replay)
SELECT pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid='learning.overlay_state_transitions'::regclass AND conname LIKE '%engine_mode%check%';
-- Expected: 含 paper/demo/live_demo/live/replay

-- 9. 3 hot-path indexes + 1 PK + 1 partial 條件確認
SELECT indexname, indexdef FROM pg_indexes
WHERE schemaname='learning' AND tablename='overlay_state_transitions'
ORDER BY indexname;
-- Expected: ≥ 4 (1 PK + idx_overlay_strategy_symbol_transition (with WHERE)
--                + idx_overlay_state_transition + idx_overlay_trigger_type)

-- 10. CHECK 真 reject empirical INSERT test
BEGIN;
SAVEPOINT test_overlay_type;
INSERT INTO learning.overlay_state_transitions
    (transition_at, overlay_type, state_from, state_to, trigger_type, engine_mode)
VALUES
    (NOW(), 'INVALID_OVERLAY', 'INACTIVE', 'WATCHING', 'm3_health', 'live');
-- Expected: ERROR: violates check constraint
ROLLBACK TO SAVEPOINT test_overlay_type;

SAVEPOINT test_state;
INSERT INTO learning.overlay_state_transitions
    (transition_at, overlay_type, state_from, state_to, trigger_type, engine_mode)
VALUES
    (NOW(), 'regime', 'INVALID_STATE', 'WATCHING', 'm3_health', 'live');
-- Expected: ERROR: violates check constraint
ROLLBACK TO SAVEPOINT test_state;

SAVEPOINT test_trigger;
INSERT INTO learning.overlay_state_transitions
    (transition_at, overlay_type, state_from, state_to, trigger_type, engine_mode)
VALUES
    (NOW(), 'regime', 'INACTIVE', 'WATCHING', 'INVALID_TRIGGER', 'live');
-- Expected: ERROR: violates check constraint
ROLLBACK TO SAVEPOINT test_trigger;

SAVEPOINT test_engine_mode;
INSERT INTO learning.overlay_state_transitions
    (transition_at, overlay_type, state_from, state_to, trigger_type, engine_mode)
VALUES
    (NOW(), 'regime', 'INACTIVE', 'WATCHING', 'm3_health', 'INVALID_MODE');
-- Expected: ERROR: violates check constraint
ROLLBACK TO SAVEPOINT test_engine_mode;

-- 同時測 replay 值是 valid(本 V105 特有)
SAVEPOINT test_replay_valid;
INSERT INTO learning.overlay_state_transitions
    (transition_at, overlay_type, state_from, state_to, trigger_type, engine_mode)
VALUES
    (NOW(), 'regime', 'INACTIVE', 'WATCHING', 'm11_divergence', 'replay');
-- Expected: PASS (replay 是合法值)
ROLLBACK TO SAVEPOINT test_replay_valid;

ROLLBACK;
```

### 9.3 Round 2 — Idempotency 驗證

重跑 V105.sql 第二次必不 RAISE / 必不重複建 hypertable / 必不重複 policy / 必不重複 mv:

```bash
ssh trade-core "
  cd ~/BybitOpenClaw/srv && \
  PGPASSWORD=\$(cat ~/.pgpass | grep trading_ai | cut -d: -f5) \
  psql -h 127.0.0.1 -p 5432 -U trading_admin -d trading_ai \
    -v ON_ERROR_STOP=1 -f sql/migrations/V105__m2_overlay_state_transitions_hypertable.sql
"
# Expected exit code 0; all DO blocks output NOTICE-only PASS; 0 RAISE EXCEPTION
```

**Round 2 後驗證**:
```sql
-- 確認 V105 不 double-create
SELECT count(*) FROM information_schema.tables
WHERE table_schema='learning' AND table_name='overlay_state_transitions';
-- Expected: 1

-- 確認 hypertable 不 double
SELECT count(*) FROM timescaledb_information.dimensions
WHERE hypertable_name='overlay_state_transitions';
-- Expected: 1

-- 確認 policies 不 double
SELECT count(*) FROM timescaledb_information.jobs
WHERE hypertable_name='overlay_state_transitions';
-- Expected: 2 (compression + retention)

-- 確認 indexes 不 double
SELECT count(*) FROM pg_indexes
WHERE schemaname='learning' AND tablename='overlay_state_transitions'
  AND indexname IN (
    'idx_overlay_strategy_symbol_transition',
    'idx_overlay_state_transition',
    'idx_overlay_trigger_type'
  );
-- Expected: 3

-- 確認 mv 不 double
SELECT count(*) FROM pg_matviews
WHERE schemaname='learning' AND matviewname='mv_latest_overlay_state_per_strategy';
-- Expected: 1
```

### 9.4 為何 Mac mock pytest 不夠(V055 5-round loop 教訓)

per memory `feedback_v_migration_pg_dry_run.md` + `project_2026_05_02_p0_sqlx_hash_drift` + V106 §9.4:
- Mac mock pytest 無法捕捉 TimescaleDB `create_hypertable()` 真實返回 metadata
- Mac static parse review 無法驗 `add_compression_policy()` / `add_retention_policy()` 對既有 job 衝突的處理
- Mac 無法驗 CHECK constraint runtime ENUM behavior(本 V105 5 ENUM × 5 值最多)
- Mac 無法驗 CONCURRENTLY 在 hypertable chunks 上的行為
- Mac 無法驗 Materialized view CONCURRENTLY refresh 行為
- Mac 無法驗 UUID column non-FK soft reference 在 cross-ref query 時的 NULL 處理
- V055 chain 5 round 都 Mac false-pass 後 Linux 撞 bug;V094 / V106 / V105 全須遵守 V055 mandate

**E2 / E4 / A3 review 必含 Linux PG dry-run gate 證據 ID**(per CLAUDE.md §Data, Migrations, And Validation + V094 §4.3 + V106 §9.4 範式)。

---

## §10 Engine Restart 實測 SOP(per 2026-05-02 sqlx hash drift 教訓)

per memory `project_2026_05_02_p0_sqlx_hash_drift`(commit `3681f83`)+ V106 §10 範式,V105 file edit 後 DB checksum 必同步:

```bash
# E1 IMPL: 寫 V105.sql 完成後跑 Linux dry-run (per §9.2)
# 若 V105.sql 落地後又被 edit → DB checksum drift
# 必跑 repair binary 同步 checksum 到 _sqlx_migrations table

ssh trade-core "
  cd ~/BybitOpenClaw/srv && \
  cargo run --release --bin repair_migration_checksum -- --version 105
"
# Expected: V105 checksum updated in _sqlx_migrations table to match new file SHA
```

### 10.1 Engine restart 後驗證 sqlx migrate 不 panic

```bash
ssh trade-core "bash ~/BybitOpenClaw/srv/helper_scripts/restart_all.sh --rebuild"

ssh trade-core "tail -200 ~/BybitOpenClaw/srv/program_code/exchange_connectors/bybit_connector/openclaw_engine/logs/engine.log 2>&1 | grep -E 'sqlx|migration|panic'"
# Expected: 0 panic; 'Applied migrations' 正常 log; V105 success=t in _sqlx_migrations

ssh trade-core "PGPASSWORD=\$(cat ~/.pgpass | grep trading_ai | cut -d: -f5) psql -h 127.0.0.1 -p 5432 -U trading_admin -d trading_ai -c 'SELECT version, success, description FROM _sqlx_migrations WHERE version=105'"
# Expected: 1 row, success=t
```

### 10.2 治理盲點防範

per `project_2026_05_02_p0_sqlx_hash_drift` + V094 §5.3 + V106 §10.2:cargo test PASS ≠ runtime sqlx migrate 驗證。E2 / E4 review 必含「engine restart 實測 + sqlx migrate runtime 不 panic」driver evidence。

---

## §11 Rollback Plan + Reversibility Analysis

### 11.1 V105 rollback DDL

詳見 §6.2(`DROP MATERIALIZED VIEW` + `DROP TABLE ... CASCADE` + drop policies + drop indexes)。

### 11.2 Reversibility 分析

| 操作 | 可逆? | 風險 |
|---|---|---|
| `DROP MATERIALIZED VIEW learning.mv_latest_overlay_state_per_strategy CASCADE` | 邏輯可逆(rerun V105)| LOW(可從 base table 重建)|
| `DROP TABLE learning.overlay_state_transitions CASCADE` | 邏輯可逆(rerun V105)但 row data 不可逆(全 drop)| **HIGH** — 90d 全 overlay state transition 資料丟失;M1 LAL eligibility 90d window 重新累積 |
| `remove_compression_policy()` / `remove_retention_policy()` | 可逆(rerun V105 重設)| LOW |
| `DROP INDEX CONCURRENTLY` | 可逆(rerun V105 重建)| LOW |

### 11.3 Rollback 觸發條件

- 僅 dev / staging
- production rollback 走 V### 升級(e.g. V###+1 加 ADD COLUMN / 改 CHECK constraint;不走 V105 down)

### 11.4 V096 boundary

per V101 spec v3 §7 + V106 §11.4:rollback 路徑不跨 V096(V096 drop dead tables 不可逆)。V105 rollback 全在 V096 之後(V096 < V098 < V105 < V107),無 boundary 風險。

---

## §12 Audit Field(per V103 EXTEND 範式 + V106 §12 同 pattern)

V105 採 V103 EXTEND §14 同範式 5 audit field:

| Column | DEFAULT | NOT NULL | 設計 |
|---|---|---|---|
| `created_by` | 'overlay_state_machine' | NOT NULL | writer process 名;允許 'overlay_state_machine' / 'cowork-agent' / 'operator' / 'm11_replay_engine' / 'm8_anomaly_detector' / 'm3_health_monitor' / 'system' |
| `created_at` | now() | NOT NULL | row insert 時間(server trusted)|
| `updated_by` | NULL | NULLABLE | 後續 update 的 actor(若 evidence_json backfill)|
| `updated_at` | NULL | NULLABLE | last update 時間 |
| `source_version` | 'V105' | NOT NULL | schema version tag;未來 schema migration audit;當前固定 V105 |

### 12.1 為什麼 overlay_state_transitions 需 audit field

per DOC-08 §12 #8 安全不變量「交易可解釋」+ V106 §12.1:overlay state 是 M1 LAL halt 的決定 input;每個 transition 必有 audit trail 才能 reproduce。

### 12.2 update_at / update_by 何時填

evidence_json backfill 場景:
1. M11 replay engine emit transition → INSERT V105 row evidence_json = initial(僅 divergence_metric)
2. 1h 後 M11 後處理計算 statistical bootstrap → 必 UPDATE evidence_json 加 bootstrap_ci
3. UPDATE 時 set `updated_at = now()` + `updated_by = 'm11_replay_engine'`

---

## §13 Acceptance Criteria(5-7 條 sign-off 標準)

### 13.1 Schema acceptance(MIT + E5)

| # | 標準 | 驗證方法 |
|---|---|---|
| 1 | `learning.overlay_state_transitions` 表 18 column 全俱在 | `SELECT count(*) FROM information_schema.columns WHERE ...` = 18 |
| 2 | Hypertable + chunk_time_interval=7d 真建立 | `SELECT time_interval FROM timescaledb_information.dimensions WHERE ...` |
| 3 | Compression policy 30d after + retention policy 90d after 真設 | `SELECT * FROM timescaledb_information.jobs WHERE ...` (2 jobs) |
| 4 | 5 ENUM (overlay_type 3 / state_from 5 / state_to 5 / trigger_type 5 / engine_mode 5) CHECK 真 reject invalid | empirical INSERT test(per §9.2 step 10)|
| 5 | 3 hot-path index + 1 PK + 1 mv 真建立;mv unique index 對齊 | `SELECT indexname FROM pg_indexes WHERE ...` ≥ 4 + `SELECT FROM pg_matviews WHERE ...` |
| 6 | V105.sql idempotent 雙跑 0 RAISE | `psql -f V105.sql` x 2 |
| 7 | sqlx checksum 對齊 + engine restart 後 success=t | per §10 SOP |

### 13.2 Cross-V### acceptance(PA)

| # | 標準 | 驗證方法 |
|---|---|---|
| 1 | V096 + V098 prereq 滿足 | `SELECT version FROM _sqlx_migrations WHERE version IN (96, 98)` |
| 2 | V107 (M11) 若已 land,replay_runs.replay_uuid UUID 對齊驗 | `SELECT pg_typeof(replay_uuid) FROM learning.replay_runs LIMIT 1` |
| 3 | V112 / V109 / V107 / V106 cross-ref query pattern 不破壞 V105 schema | per §8.3-§8.6 範例 query 預跑 |

### 13.3 治理 acceptance(QA + R4)

| # | 標準 | 驗證方法 |
|---|---|---|
| 1 | engine_mode IN ('live','live_demo') filter 在所有 cross-ref query + mv 出現(不含 replay)| per §7.2 mv DDL + §8 範例對齊 |
| 2 | 5 audit field 預設值 reasonable | INSERT row 不填 audit field 後 SELECT 驗 DEFAULT |
| 3 | docs/README.md 加 V105 spec 入 index | per CLAUDE.md §七 docs/README 規則 |
| 4 | ADR-0034 LAL Tier 0-4 對齊 5 state(INACTIVE/WATCHING/ARMED/ACTIVE/COOLDOWN)文檔說明 | 本 spec §1.2 + ADR-0034 cross-link |

---

## §14 開放問題 + Caveat

### 14.1 待 PA C9 確認

1. **`_sqlx_migrations` head 真實**(per §9.1 Query 1)— spec 假設 ≥ V098
2. **TimescaleDB extension version**(per §9.1 Query 2)— spec 假設 ≥ 2.13
3. **governance.audit_log 已 land**(per §9.1 Query 3)— spec 假設已 land
4. **V107 (M11) replay_runs land 狀態**(per §9.1 Query 4)— 影響 Guard A NOTICE-only vs HARD enforce
5. **legacy stub conflict**(per §9.1 Query 5)— spec 假設 greenfield
6. **V107 replay_runs `replay_uuid` column 名 + type**確認 — 假設為 UUID,若 V107 採 TEXT 則 V105 counterfactual_log_ref type 需對齊

### 14.2 已知 caveat

1. **`state_from = state_to` no-op transition writer-side enforce 成本**:writer 每次必判斷;application-side reject 比 CHECK reject 更彈性(per §2.5)
2. **`evidence_json` JSONB 不索引**:debug-only 欄位;若 future analytics 需要 query JSONB,Sprint 1B+ 加 GIN index
3. **partial index `WHERE strategy_id IS NOT NULL AND symbol IS NOT NULL` 在 schema migration 時的成本**:CONCURRENTLY 建在 hypertable chunks 上是逐 chunk 建;首次 apply 在 0-row 表上 ms 級;後續 backfill 期會慢
4. **per-strategy_id 不 enum**:5 既有策略 + Sprint 2+ 新策略名動態擴增;CHECK enum 易過時
5. **`trigger_source_id` 軟連結**(non-typed FK):writer 負責 referential integrity;若 trigger 來源表 row 被 drop,trigger_source_id dangling(application-side 容忍)
6. **`counterfactual_log_ref` UUID non-FK**:同上 referential integrity 軟約束;cross-ref query 用 LEFT JOIN 處理 NULL
7. **mv refresh 失敗時 M1 LAL fallback path**:若 cron refresh 失敗 >5 min,M1 LAL eligibility query 必降級至 base table(成本 +ms 級;application-side switch)— 本 spec 不寫 fallback logic;Sprint 1B writer 設計時補
8. **engine_mode='replay' 影響 retention policy**:replay-driven transition 算入 90d retention;M11 nightly replay 大量寫 replay row 可能加速 chunk 滿;若 replay row volume > live,需 Sprint 1B+ 評估是否分表

### 14.3 Sprint 1B writer 路徑未在本 spec 範圍

V105 apply 後立即 0 row(Foundation stage per MIT pipeline maturity);Sprint 1B 補 writer 後升 Skeleton。

### 14.4 5 vs 6 trigger_type 之 dispatch sequence 影響

本 spec 採 5 trigger_type(m3_health / m11_divergence / m8_anomaly / operator / time_based);未來若 Sprint 2+ 加 7-th trigger(如 `cross_overlay_correlation`),需:
- ALTER CHECK constraint(per V055 sqlx hash drift incident 教訓)
- repair_migration_checksum binary 跑
- engine restart + sqlx migrate 驗

**不建議在本 spec 加 6+ trigger** 提前 future-proof;over-engineering 風險。

---

## §15 後續行動(給 PM 派發)

| Action | Owner | Track | Priority |
|---|---|---|---|
| Sign-off 本 V105 spec | PM | Sprint 1A-γ schema prereq closure | P0 |
| PA C9 跑 §9.1 5 條 ssh PG query + 補 5 處 placeholder | PA | Sprint 1A-γ pre-dispatch | P0 |
| Reconcile cross-V### dependency(V107 對 V105 land 順序;V112 / V109 / V106 對 V105 cross-ref query 對齊) | PA | Sprint 1A-γ pre-dispatch | P0 |
| V107 (M11) replay_runs spec 確認 `replay_uuid` column 名 + type(UUID vs TEXT) | MIT + PA | Sprint 1A-γ pre-dispatch | P0 |
| IMPL kickoff:派 E1 寫 V105.sql + Linux PG dry-run × 2 + E2/E4 + restart_all 部署 | PM | Sprint 1A-γ IMPL | P1 |
| Sprint 1B writer 上線:`overlay_state_machine` writer + healthcheck `check_overlay_state_writer()` + mv refresh cron | E1 (Sprint 1B) | Sprint 1B | P2 |
| Sprint 1B M1 LAL eligibility query 對齊 mv vs base table fallback logic | E1 + MIT (Sprint 1B) | Sprint 1B | P2 |

### 15.1 Sprint 1A-γ schema prereq closure 標誌

本 spec PM sign-off + PA C9 dry-run 補資料 land + V107 / V112 / V109 / V106 cross-ref reconciliation 完成 → Sprint 1A-γ V105 schema prereq 解除 → IMPL kickoff 派 E1。

### 15.2 V105 vs V106 vs V107 dispatch sequence 對齊

per PA dispatch consolidation §6 cross-V### dependency graph + 本 spec §1.6:

```
V096 (boundary) → V097 (LG-5) → V098 (governance.audit_log)
                                     │
                                     ├─→ V106 (M3 health) [Sprint 1A-β]
                                     │       ↓
                                     │   M3 HEALTH_DEGRADED cross-ref
                                     │       ↓
                                     ├─→ V107 (M11 replay) [Sprint 1A-γ FIRST]
                                     │       ↓
                                     │   replay_runs.replay_uuid cross-ref
                                     │       ↓
                                     ├─→ V105 (M2 overlay) [Sprint 1A-γ SECOND] ← 本 spec
                                     │       ↓
                                     │   overlay state cross-ref
                                     │       ↓
                                     ├─→ V109 (M8 anomaly) [Sprint 1A-δ]
                                     │       ↓
                                     │   m8_anomaly trigger cross-ref
                                     │       ↓
                                     └─→ V112 (M1 LAL) [Sprint 1A-ε]
                                             ↓
                                         LAL eligibility cross-ref
```

**V107 必先 V105 land**:因 V105 `counterfactual_log_ref` UUID cross-ref 需 V107 replay_runs.replay_uuid 對齊。若 V107 spec 採 TEXT 不採 UUID,V105 schema 需 amend(per §14.1 caveat 6)。

---

## §16 關鍵文件指針

- 本 V105 spec:本檔
- v5.8 主檔 §2 M2:`srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md`
- PA dispatch consolidation §6 cross-V### dep graph:`srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md`
- E5 hypertable audit:`srv/docs/CCAgentWorkSpace/E5/workspace/reports/2026-05-21--v58_hypertable_audit.md`
- V106 spec(sister-V### 14-section 範式 + 5 audit field EXTEND + Guard A/C + Linux PG dry-run):`srv/docs/execution_plan/2026-05-21--v106_m3_health_observations_schema_spec.md`
- V103 spec(範式起點):`srv/docs/execution_plan/2026-05-21--v103_v104_earn_hypotheses_schema_spec.md`
- V103/V104 Linux PG dry-run protocol(範式):`srv/docs/execution_plan/2026-05-21--v103_v104_linux_pg_dry_run.md`
- V094 spec(Guard A/B/C + 範式):`srv/docs/execution_plan/2026-05-15--v094_close_maker_first_audit_schema_spec.md`
- V083 mirror(ALTER + NOT VALID CHECK 範式):`srv/sql/migrations/V083__fills_entry_context_id_close_check.sql`
- schema_guard_template:`srv/sql/migrations/templates/schema_guard_template.sql`
- repair binary:`srv/rust/openclaw_engine/src/bin/repair_migration_checksum.rs`
- V055 5-round loop + sqlx hash drift incident lessons:`memory/feedback_v_migration_pg_dry_run.md` + `memory/project_2026_05_02_p0_sqlx_hash_drift.md`
- CLAUDE.md §Data, Migrations, And Validation:`srv/CLAUDE.md`
- ADR-0034 (M1 LAL Tier 0-4 對齊 V105 5 state):`srv/docs/adr/0034-decision-lease-layered-approval-lal.md`
- ADR-0036 (M8 + M10 Tier D blacklist;M2 → m8_anomaly trigger):`srv/docs/adr/0036-m8-anomaly-detection-and-m10-tier-d-model-blacklist.md`
- ADR-0038 (M11 Continuous Counterfactual Replay;V105 counterfactual_log_ref UUID + engine_mode=replay 出處):`srv/docs/adr/0038-m11-continuous-counterfactual-replay-and-liquidations-source.md`

---

## §17 審計記錄

| Source agent | Role | Audit pattern coverage |
|---|---|---|
| MIT(本文起草)| 起草者 | V058 Risk 7 V105 placeholder closure 路徑 / pipeline maturity 5 階段 / Guard A/C / Linux PG dry-run mandate / 5 state machine LAL Tier 對齊 / engine_mode=replay 設計 |
| PA dispatch consolidation 5.21(範式參考) | spec 設計 + cross-V### dependency | V105 / V107 / V109 / V112 / V106 cross-ref graph / Sprint 1A-γ dispatch sequence(V107 先 V105 後)|
| V106 spec(2026-05-21,sister-V### 範式)| 結構 + audit field 範式 + Guard A/C + Linux PG dry-run × 2 + sqlx checksum repair SOP | 17 section structure / 5 audit field per V103 EXTEND / Guard A/C template / Linux PG dry-run × 2 round protocol / sqlx checksum repair SOP |
| V103/V104 spec(2026-05-21,範式參考起點)| 5 audit field EXTEND 起點 + 範式 | 5 audit field 起點 + 14 section structure baseline |
| E5 5.21 hypertable audit | hypertable 規格 | 7d chunk + 30d compression(vs V106 7d 不同)+ 90d retention / ~6.3k row/day vs V106 716k row/day 差異 → 30d compress 起點 |
| db-schema-design-financial-time-series skill | DB schema audit | hypertable 必用 / hot-path index 選用 / engine_mode CHECK 5 值(本 V105 加 replay)/ Guard A/B/C 規範 / partial index 設計 |
| ml-pipeline-maturity-audit skill | Pipeline stage 評級 | V105 apply 後立即 0 row 屬 Foundation stage;Sprint 1B writer 接線後升 Skeleton;mv refresh cron 失敗 fallback 路徑屬 Shadow stage |
| ADR-0034 (M1 LAL Tier 0-4) | 5 state LAL Tier 對齊 | INACTIVE/WATCHING/ARMED/ACTIVE/COOLDOWN ↔ Tier 0/1/2/3/4 完美 1:1 mapping |
| ADR-0036 (M8 + M10 Tier D) | trigger_type 對齊 | m8_anomaly trigger 對齊 + COOLDOWN demote 路徑 |
| ADR-0038 (M11 replay + counterfactual) | counterfactual_log_ref UUID + engine_mode=replay 出處 | M11 nightly replay 寫 counterfactual transition 必標 replay / counterfactual_log_ref UUID cross-ref(non-FK)|

### 17.1 待 PA dispatch 前補充

- [ ] PA C9 dry-run 5 條 ssh query 結果(§9.1)
- [ ] V096 + V098 + TimescaleDB extension 已 land 確認
- [ ] V107 (M11) replay_runs 表名 + replay_uuid column type 確認(UUID vs TEXT;影響 V105 counterfactual_log_ref type 對齊)
- [ ] legacy `learning.overlay_state_transitions` stub 不存在確認
- [ ] mv refresh cron 失敗時 M1 LAL fallback 路徑設計(per §14.2 caveat 7)
- [ ] Sprint 1B writer + healthcheck wiring + mv refresh cron 工作 owner + dispatch sequence

---

**END V105 spec full DDL v0**
