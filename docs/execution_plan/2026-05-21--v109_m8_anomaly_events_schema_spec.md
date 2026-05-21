---
spec: V109 — M8 Anomaly Events Schema (Hypertable Mandatory; ATR-vol × Funding 9-cell + RV pct + Block Bootstrap;HMM/Markov/GARCH 永久禁用)
date: 2026-05-21
author: MIT (full DDL spec; lifts placeholder from earlier same-day frontmatter)
phase: v5.8 Sprint 1A-γ schema prerequisite CRITICAL deliverable
status: SPEC-FULL-V0 (MIT 起草;待 PA C9 Linux PG dry-run 實測補資料 + Sprint 1A-γ reviewer 對齊後 SPEC-FINAL)
sprint: Sprint 1A-γ (DESIGN phase;IMPL 後續 sprint 3)
size estimate: 200-280 LOC SQL (CREATE TABLE 1 hypertable + 4 indexes + 6 ENUM 結構 + Guard A/C 含 ADR-0036 forbidden algorithm reverse pattern + compression + retention) + 60-90 hr E1 IMPL (含 Linux PG dry-run × 2 round + healthcheck wiring deferred to Sprint 3)
depend on:
  - V096 boundary (TimescaleDB extension; drop dead learning tables)
  - V098 (governance.audit_log; referenced cross-ref 非 FK)
depended by:
  - V106 (M3 health_observations) — M8 CRITICAL → M3 HEALTH_DEGRADED (cross-ref query 非 FK)
  - V112 (M1 LAL) — anomaly 90d incident-free → eligibility check (cross-ref query 非 FK;m1_lal_demote_ref BIGINT 弱關聯)
  - V113 (M7 decay_signals) — persistent anomaly 14d → source 5 (cross-ref query 非 FK;m7_decay_signal_ref BIGINT 弱關聯)
  - V107 (M11 replay_divergence_log) — CR-7 dedup contract;M11 不直接 emit M8 (cross-ref only)
  - V108 (M9 ab_test_assignments) — anomaly 期間 A/B 暫停 (cross-ref query 非 FK)
parent specs:
  - srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md §2 M8 Anomaly Detection (lines 279-318)
  - srv/docs/adr/0036-m8-anomaly-detection-and-m10-tier-d-model-blacklist.md (Decision 1 HMM/Markov/GARCH 永久禁用 + Decision 2 替代算法 + Decision 4 block bootstrap threshold)
  - srv/docs/execution_plan/2026-05-21--m8_anomaly_detection_design_spec.md (sister DESIGN spec;same-day land;cross-ref §1-§16)
  - srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md §1 CR-5 + §6 cross-V### dependency graph
mirror precedent:
  - srv/docs/execution_plan/2026-05-21--v106_m3_health_observations_schema_spec.md (1087 行 baseline;same-wave 範式)
  - srv/docs/execution_plan/2026-05-21--v103_v104_earn_hypotheses_schema_spec.md (format reference)
  - srv/docs/execution_plan/2026-05-21--v103_v104_linux_pg_dry_run.md (Linux PG dry-run protocol 範式)
  - srv/sql/migrations/V094__fills_close_maker_audit.sql (Guard A/B/C + partial index 範式)
  - srv/sql/migrations/templates/schema_guard_template.sql (Guard A/B/C template)
scope: design / spec only — 不寫 V109.sql 實檔,不在 Mac 跑 SQL,不改 Rust/Python writer,不執行 PG,不擴張到 module 行為 (M8 design spec 主責)
---

# V109 M8 Anomaly Events Schema Migration Spec

## §0 TL;DR

- **V109 新增 1 個 hypertable**:`learning.anomaly_events`(market regime + microstructure + infrastructure anomaly snapshots)。
- **9 event_taxonomy ENUM**(per M8 design spec §2.1):`regime_shift` / `liquidation_cascade` / `orderbook_imbalance` / `funding_outlier` / `volume_spike` / `spread_widening` / `price_dislocation` / `ws_disconnect` / `fee_anomaly`。
- **4 severity ENUM**:`INFO` / `WARN` / `CRITICAL` / `HALT` (per ADR-0036 + M8 design spec §4.1)。
- **4 detection_method ENUM**:`atr_vol_funding_9cell` / `rv_percentile` / `block_bootstrap` / `manual_operator` (per ADR-0036 Decision 2-4)。
- **3 atr_vol_state ENUM**(LOW/MED/HIGH) + **3 funding_state ENUM**(NEGATIVE/NEUTRAL/POSITIVE) per ADR-0036 §3.1 9-cell matrix axis。
- **Guard A forbidden algorithm 反向防護**:detection_method CHECK 不可含 `hmm` / `markov_switching` / `garch` per ADR-0036 Decision 1;Guard A RAISE EXCEPTION 強制。
- **`amplification_loop_24h_count` 欄位**(per M8 design spec §5):同一 event_taxonomy 24h 內 CRITICAL/HALT 計數;writer 預計算;≥ 2 → evidence_json 標 `cap_suppressed=true` 不 emit M3 cascade event。
- **Hypertable mandatory**:7d chunk + 30d compression policy + 180d retention(per E5 audit 範式 + M8 anomaly retention 比 M3 health 長因 anomaly event 稀疏需保留長期供 M7 14d persistent + 90d incident-free check)。
- **engine_mode CHECK 4 值齊全**(paper / demo / live_demo / live);training filter 必含 `IN ('live','live_demo')`(per CLAUDE.md §七)。
- **Cross-V### dependencies**:V096 boundary (TimescaleDB extension) + V098 (governance.audit_log);**無 hard FK**(M8 是觀測層;cross-ref 走 query-time JOIN per V106 spec §8.2 範式)。
- **5 audit field** per V103 EXTEND 範式:`created_by` / `created_at` / `updated_by` / `updated_at` / `source_version`。
- **Hot-path indexes 4 個**:domain-time / severity-time (partial) / symbol-time / strategy-time (partial)。
- **Linux PG empirical dry-run mandatory**(per CLAUDE.md §Data, Migrations, And Validation + V055 5-round loop precedent)。

---

## §1 Context + 為什麼

### 1.1 v5.8 §2 M8 module 出處 + 動機

per M8 design spec §1 + v5.8 §2 M8 (lines 279-318):

| Anomaly 來源層 | 範圍 | M8 detection_method | 對應 event_taxonomy |
|---|---|---|---|
| **Market regime** (4 子類) | Vol regime shift / liquidation cascade / orderbook imbalance / funding outlier | `atr_vol_funding_9cell` + `rv_percentile` + `block_bootstrap` | regime_shift / liquidation_cascade / orderbook_imbalance / funding_outlier |
| **Market microstructure** (3 子類) | volume spike / spread widening / price dislocation | `rv_percentile` + `block_bootstrap` | volume_spike / spread_widening / price_dislocation |
| **Infrastructure** (2 子類) | WS disconnect / fee anomaly | `manual_operator` (rule-based) | ws_disconnect / fee_anomaly |

**Own behavior anomaly**(v5.8 原文 4 子類 — strategy fill rate / order rejection / slippage outlier / decision lease grant rate)**走 M3 strategy_quality domain**,不寫入 V109(per CR-7 dedup contract;M3 single health authority;M8 專注 market + infrastructure)。

### 1.2 row 量級估算

per M8 design spec §2.3 + ADR-0036 Decision 3 9-cell sample 量估計:

| Severity | typical rate (per 25 symbols, per day) |
|---|---|
| INFO | ~50-200 row/day (baseline noise + low-severity microstructure) |
| WARN | ~5-20 row/day |
| CRITICAL | ~0-5 row/day |
| HALT (Y2+) | ~0-1 row/day (catastrophic event;極稀) |

- typical = ~60-225 row/day
- conservative upper bound (high vol regime) = ~300 row/day
- 1y = ~110k row;5y = ~550k row (對比 V106 health_observations ~261M row/yr,V109 量級顯著小)
- **6mo row 量 < 50k → uncompressed ~12 MB → 占 PG buffer < 1%**

雖然量級遠小於 V106,但 hypertable + compression mandatory 仍採用(per `db-schema-design-financial-time-series` skill §1.1)因:
- Anomaly event 是 time-series 性質(時間維度 query 為主)
- 90d incident-free check (per V112 M1 LAL eligibility) + 14d persistent check (per V113 M7 source 5) 都是 time-range query → hypertable chunk pruning 加速
- Compression 30d 後省 storage(雖然 V109 量小,但避免 future 高 vol regime cycle 突發 spike)
- **Retention 180d 比 V106 90d 長因 anomaly 是 governance evidence 需保留長期**(M7 source 5 / M1 LAL eligibility 都需 ≥ 90d window)

### 1.3 ADR-0036 黑名單 schema-level enforcement

per M8 design spec §3.2 + ADR-0036 Decision 1:

- HMM (含所有變形:HSMM / HHMM / Factorial HMM 等) **永久禁用**
- Markov-switching regression (Hamilton 1989 起所有變形) **永久禁用**
- GARCH 家族 (EGARCH / TGARCH / IGARCH / FIGARCH / Multivariate GARCH 等) **永久禁用**

V109 schema 層強制 enforcement:
- `detection_method` CHECK ENUM 4 值不含 `hmm` / `markov_switching` / `garch`
- Guard A 反向防護:若未來 amend 加入黑名單字眼 → RAISE EXCEPTION 阻擋 migration
- 對齊 PA + MIT + E2 dispatch grep gate(per ADR-0036 Decision 1 §「Sub-agent dispatch 階段 grep」)

### 1.4 Cross-V### 影響

| 下游 | M8 觸發路徑 | 是否 FK |
|---|---|---|
| **V106 M3** | CRITICAL/HALT → M3 HEALTH_DEGRADED/CRITICAL (per M3 spec §8 + M8 design §6.1) | 否 (cross-ref query;FK 太重) |
| **V112 M1 LAL** | anomaly 90d incident-free check → eligibility (per V112 spec §「lease_lal_assignments」mv_lease_lal_eligibility) | 否 (cross-ref query;m1_lal_demote_ref BIGINT 弱關聯 column) |
| **V113 M7** | persistent anomaly 14d ≥ 7d distinct → M7 source 5 (per V113 spec §「decay_source ENUM」 + M8 design §7.2) | 否 (cross-ref query;m7_decay_signal_ref BIGINT 弱關聯 column) |
| **V107 M11** | M11 不直接 emit M8 (per CR-7 dedup;M11 → M3 + M7) | 否 (純 application 層 cross-ref) |
| **V108 M9** | CRITICAL anomaly → M9 mark `paused_until_anomaly_resolved` (per M8 design §8) | 否 (cross-ref query) |

### 1.5 不在本 spec 範圍

- ❌ V109.sql 實檔寫作 (E1 IMPL 工作)
- ❌ Mac 跑 V109 SQL (必 Linux PG empirical)
- ❌ Rust anomaly detector code (`rust/openclaw_engine/src/anomaly/detector.rs`;E1 Sprint 3 IMPL 工作)
- ❌ Python healthcheck wiring (`helper_scripts/passive_wait_healthcheck.py` 加 `check_anomaly_writer()`;Sprint 3 工作)
- ❌ ML autoencoder training pipeline (Y2+ 工作,per ADR-0036 §「Y2+ ML detector」)
- ❌ M3 / M7 / M9 / M1 LAL cross-module integration code (E1 Sprint 5+ 工作;本 spec 只列 cross-ref query 範例不擴張)
- ❌ Block bootstrap threshold estimator (Sprint 3 工作;per ADR-0036 Decision 4)

---

## §2 Schema Design

### 2.1 `learning.anomaly_events` 表定義

```sql
CREATE TABLE IF NOT EXISTS learning.anomaly_events (
    id                              BIGSERIAL,
    observed_at                     TIMESTAMPTZ NOT NULL,
    event_taxonomy                  TEXT NOT NULL
                                    CHECK (event_taxonomy IN (
                                        'regime_shift',
                                        'liquidation_cascade',
                                        'orderbook_imbalance',
                                        'funding_outlier',
                                        'volume_spike',
                                        'spread_widening',
                                        'price_dislocation',
                                        'ws_disconnect',
                                        'fee_anomaly'
                                    )),
    severity                        TEXT NOT NULL
                                    CHECK (severity IN (
                                        'INFO',
                                        'WARN',
                                        'CRITICAL',
                                        'HALT'
                                    )),
    detection_method                TEXT NOT NULL
                                    CHECK (detection_method IN (
                                        'atr_vol_funding_9cell',
                                        'rv_percentile',
                                        'block_bootstrap',
                                        'manual_operator'
                                    )),
    atr_vol_state                   TEXT
                                    CHECK (atr_vol_state IS NULL OR atr_vol_state IN (
                                        'LOW',
                                        'MED',
                                        'HIGH'
                                    )),
    funding_state                   TEXT
                                    CHECK (funding_state IS NULL OR funding_state IN (
                                        'NEGATIVE',
                                        'NEUTRAL',
                                        'POSITIVE'
                                    )),
    strategy_id                     TEXT,
    symbol                          TEXT,
    metric_value                    NUMERIC(18,8),
    metric_threshold                NUMERIC(18,8),
    amplification_loop_24h_count    INTEGER NOT NULL DEFAULT 0,
    m3_health_observation_ref       BIGINT,
    m7_decay_signal_ref             BIGINT,
    m1_lal_demote_ref               BIGINT,
    evidence_json                   JSONB,
    engine_mode                     TEXT NOT NULL
                                    CHECK (engine_mode IN ('paper','demo','live_demo','live','replay')),
    created_by                      TEXT NOT NULL DEFAULT 'anomaly_detector',
    created_at                      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by                      TEXT,
    updated_at                      TIMESTAMPTZ,
    source_version                  TEXT NOT NULL DEFAULT 'V109',
    PRIMARY KEY (id, observed_at)
);
```

### 2.2 Column 設計理由

| Column | Type | NULL | 設計理由 |
|---|---|---|---|
| `id` | BIGSERIAL | NOT NULL | sequential ID(per hypertable best practice;PK 必含 partition column 因此複合 `(id, observed_at)`)|
| `observed_at` | TIMESTAMPTZ | NOT NULL | hypertable time dimension;UTC 統一(per CLAUDE.md §六)|
| `event_taxonomy` | TEXT + CHECK 9 值 | NOT NULL | 9 anomaly 子類顯式枚舉(per M8 design spec §2.1);crypto market regime + microstructure + infrastructure 三大來源完整覆蓋;新 taxonomy 需 amend ENUM(controlled drift) |
| `severity` | TEXT + CHECK 4 值 | NOT NULL | 4 級 severity:INFO < WARN < CRITICAL < HALT;HALT 為 Y2+ active gate(per M8 design spec §4.4)|
| `detection_method` | TEXT + CHECK 4 值 | NOT NULL | per ADR-0036 Decision 2-4 替代算法;`atr_vol_funding_9cell` / `rv_percentile` / `block_bootstrap` / `manual_operator`;**不含 hmm/markov/garch**(per Guard A 反向防護)|
| `atr_vol_state` | TEXT + CHECK 3 值 + NULL | YES | per ADR-0036 §3.1 9-cell axis 1;非 9cell 類 detection 不填(如 ws_disconnect / fee_anomaly NULL allowed) |
| `funding_state` | TEXT + CHECK 3 值 + NULL | YES | per ADR-0036 §3.1 9-cell axis 2;同 atr_vol_state NULL allowed |
| `strategy_id` | TEXT | YES | per-strategy 特定 anomaly(如 strategy_specific own behavior 走 M3 不在 V109,但 cross-strategy aggregated anomaly 如 cross_symbol_correlation_spike 可填);多 strategy 通用 anomaly NULL |
| `symbol` | TEXT | YES | per-symbol 特定 anomaly;非 per-symbol(如全 universe regime_shift)NULL allowed |
| `metric_value` | NUMERIC(18,8) | YES | anomaly 觸發 metric 真實值(如 ATR percentile / RV / funding rate);per `db-schema-design-financial-time-series` skill 高精度 |
| `metric_threshold` | NUMERIC(18,8) | YES | 觸發 anomaly 的 threshold(reference 當下 active config);用於 audit trail;config 可變但 historical row 鎖當下 threshold |
| `amplification_loop_24h_count` | INTEGER + DEFAULT 0 | NOT NULL | per H-11 cap + M8 design spec §5;writer 預計算 24h 同 event_taxonomy CRITICAL/HALT count;≥ 2 → 雖寫入但 evidence_json 標 cap_suppressed |
| `m3_health_observation_ref` | BIGINT | YES | M8 → M3 cascade 後 V106 INSERT 的 row id 反向 ref(cross-ref query 用;非 FK 因 V106 是另 hypertable);用於追溯「此 anomaly 觸發了哪個 M3 health state change」 |
| `m7_decay_signal_ref` | BIGINT | YES | persistent anomaly 14d 觸發 M7 source 5 後 V113 INSERT 的 signal_id 反向 ref;cross-ref query 用 |
| `m1_lal_demote_ref` | BIGINT | YES | anomaly 觸發 M1 LAL Tier 降階後 V112 INSERT 的 row id 反向 ref;**對齊 ADR-0034 數字越大越嚴方向**(per 啟動 prompt §「⚠️ 注意」)— ref 指向 Tier 降低後的 row 而非升 |
| `evidence_json` | JSONB | YES | 富 context:detector raw output / atr percentile 計算 window / funding state derivation / block bootstrap resample distribution / cap_suppressed flag / cascade_actions_taken;debug 用 |
| `engine_mode` | TEXT + CHECK 5 值 | NOT NULL | 5 值含 replay(支援 M11 read-only counterfactual 走 replay surface per ADR-0036 Decision 1 例外段);training filter 必 `IN ('live','live_demo')`;paper 仍寫入 schema 但 cap_suppressed 走 application layer 過濾 |
| `created_by` | TEXT + DEFAULT 'anomaly_detector' | NOT NULL | per V103 EXTEND 範式;預設 writer process 名;允許 'anomaly_detector' / 'cowork-agent' / 'operator' / 'm11_replay_engine' 多 actor |
| `created_at` | TIMESTAMPTZ + DEFAULT now() | NOT NULL | row insert 時間(server-side trusted)|
| `updated_by` | TEXT | YES | 後續 update 的 actor(若 amplification cap backfill;若 cross-module ref 補填)|
| `updated_at` | TIMESTAMPTZ | YES | last update 時間 |
| `source_version` | TEXT + DEFAULT 'V109' | NOT NULL | schema version tag;未來 schema migration audit;預設 V109 |

### 2.3 為什麼 engine_mode 採 5 值含 'replay'(V106 是 4 值)

V106 `learning.health_observations` engine_mode 4 值(paper/demo/live_demo/live);V109 加 5th 值 `replay` 因:

- per ADR-0036 Decision 1 例外段:HMM / GARCH read-only counterfactual analysis 允許 read-only run 但必走 M11 replay surface
- M11 replay engine 跑 counterfactual 時若有 anomaly 落地需有 engine_mode 標籤區分 live vs replay
- V106 health_observation 是 continuous-state 觀測,replay 引擎不 emit health state(replay 是 batch job 非 live system),因此 V106 不需 replay enum
- V109 anomaly event 在 replay 期可能被 detector 重 emit(背景:nightly counterfactual replay 重跑 detector),需 schema 區分

### 2.4 為什麼 atr_vol_state / funding_state NULL allowed

per M8 design spec §2.4 detection_method × event_taxonomy 對應表:
- `regime_shift` + `funding_outlier` 採 `atr_vol_funding_9cell` → 必填 atr_vol_state + funding_state
- `volume_spike` + `orderbook_imbalance` 採 `rv_percentile` → 不必填 9-cell axis(rolling percentile 不依賴 9-cell)
- `liquidation_cascade` + `spread_widening` + `price_dislocation` 採 `block_bootstrap` → 不必填 9-cell axis
- `ws_disconnect` + `fee_anomaly` 採 `manual_operator` → 不必填 9-cell axis

NULL allowed 是設計決策;Guard C 不強制 detection_method × atr_vol_state cross-check(避免 schema-level 過 rigid;靠 application 層 enforcement)。

### 2.5 為什麼 amplification_loop_24h_count 是 INTEGER 而非 BOOLEAN cap_suppressed

per M8 design spec §5.3:
- count 本身有 analytical value(用於 24h trend / per-symbol burst rate analysis)
- cap_suppressed boolean 由 application layer 從 count ≥ 2 derive,寫入 evidence_json
- 保留 INTEGER 允許未來 amplification 規則調整(如改 cap = 3 / 24h),不需 schema migration
- 對齊 V106 spec §2.2 `amplification_loop_24h_count INTEGER DEFAULT 0` 同範式

### 2.6 為什麼採 4 detection_method ENUM 而非 detection_method 自由 TEXT

per `db-schema-design-financial-time-series` skill §1 + ADR-0036 Decision 1 強制 enforcement:
- ENUM 限制 4 值是 schema-level 反向防護 — 避免 future drift 加入 hmm/garch
- 自由 TEXT 即使 application 層 reject,schema 仍允許寫入,Guard A 無法在 migration 時 catch
- 未來新增合法 detection_method(如 isolation forest)走 V### amendment 加入 ENUM 值,並必先 amend ADR-0036(per ADR-0036 Decision 1 「未來新增黑名單方法」對偶程序)

### 2.7 為什麼 m3 / m7 / m1_lal _ref 是 BIGINT 而非 FK

per V106 spec §1.4 + §8.2 + `db-schema-design-financial-time-series` skill §5:
- M8 是 observational sensor,FK 太重(每 INSERT 都查 FK target)
- V106 / V113 / V112 各自是 hypertable,FK 跨 hypertable 在 TimescaleDB 不支援 partition-aware
- FK cascade delete 風險(若 V106 retention drop chunk 觸 V109 row 被 CASCADE)
- BIGINT 弱關聯允許 application 層維持 referential integrity + healthcheck 補(per `passive_wait_healthcheck.py` 新增 `check_anomaly_cross_ref_integrity()`,Sprint 3+ 工作)

---

## §3 Hypertable / Partitioning

### 3.1 Hypertable 設定

```sql
SELECT create_hypertable(
    'learning.anomaly_events',
    'observed_at',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists => TRUE
);
```

**chunk_time_interval = 7d 理由**(per `db-schema-design-financial-time-series` skill):
- 60-225 row/day × 7d = ~420-1.6k row/chunk(對比 V106 5M row/chunk)
- chunk size ~100 KB-400 KB (uncompressed)→ 雖小但保持 7d 對齊 weekly rollup query pattern + 與 V106 / V107 chunk 邊界對齊便於 cross-V### JOIN
- 7d 對齊 M7 14d persistent anomaly check window(2 個 chunk pruning)
- 7d 對齊 V107 M11 replay weekly job

### 3.2 Compression policy

```sql
ALTER TABLE learning.anomaly_events SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'event_taxonomy, severity',
    timescaledb.compress_orderby = 'observed_at DESC, id DESC'
);

SELECT add_compression_policy(
    'learning.anomaly_events',
    INTERVAL '30 days'
);
```

- `compress_segmentby = 'event_taxonomy, severity'`:同 taxonomy × severity 連續 row segment 壓縮率最高(80-90%);per V106 spec §3.2 同範式但 segment 維度不同(V106 是 domain + metric_name,V109 是 event_taxonomy + severity)
- `compress_orderby = 'observed_at DESC, id DESC'`:time-DESC 最近資料 close 在 chunk 邊界,decompress 成本最低
- **30d 後自動壓縮**(對比 V106 7d compression)因:
  - V109 row 量小,30d 內未壓縮全表 ~1.5-7 MB,buffer 影響忽略
  - 30d 內 anomaly event 高頻訪問(M3 cascade re-check / M7 14d persistent check / M1 LAL incident-free check)；7d 壓縮過早觸 decompress overhead
  - 對齊 ADR-0036 Decision 4 30d block bootstrap re-estimate cadence(壓縮時序與 threshold re-estimate cadence 對齊)

### 3.3 Retention policy

```sql
SELECT add_retention_policy(
    'learning.anomaly_events',
    INTERVAL '180 days'
);
```

- 180d 後自動 drop chunk
- **對比 V106 90d retention 更長**因:
  - M1 LAL eligibility 必須 90d incident-free → 90d retention 是邊界,180d 提供 2 倍 safety margin
  - M7 source 5 persistent anomaly 14d window → 180d 提供 ~13 倍 retention margin
  - M11 nightly replay 跑回看 30d historical → 180d 覆蓋
  - Anomaly event 是 governance evidence,保留長期 audit value > storage cost(V109 量小)
- 對 long-term trend 分析(> 180d)走 daily aggregate 表(本 spec 不含,Sprint 3+ 補)

### 3.4 為什麼不採 90d 或 365d retention

- **90d 過短**:M1 LAL eligibility 必須 90d incident-free,90d retention 是邊界 — 一旦 chunk drop 在 query 後 LAL eligibility 失準
- **365d 過長**:雖然量小,但 anomaly aggregated stats > 1y 通常已 stale(market regime 變動快);180d 是 90d eligibility + 14d M7 persistent + 30d block bootstrap re-estimate 的 union(取 max + 安全 margin)

---

## §4 Index Strategy

### 4.1 Hot-path query → index map

per OpenClaw `db-schema-design-financial-time-series` skill + M8 design spec query pattern:

| Query pattern | 命中 index | 範例 SQL |
|---|---|---|
| per-taxonomy timeline | `idx_anomaly_taxonomy_observed` | `SELECT * FROM learning.anomaly_events WHERE event_taxonomy='regime_shift' ORDER BY observed_at DESC LIMIT 100` |
| per-severity alert dashboard | `idx_anomaly_severity_observed` (partial) | `SELECT * FROM learning.anomaly_events WHERE severity IN ('CRITICAL','HALT') AND observed_at > now() - INTERVAL '24 hours'` |
| per-symbol anomaly drill-down | `idx_anomaly_symbol_observed` (partial) | `SELECT * FROM learning.anomaly_events WHERE symbol='BTCUSDT' AND observed_at > now() - INTERVAL '14 days'` |
| per-strategy anomaly aggregation | `idx_anomaly_strategy_observed` (partial) | `SELECT * FROM learning.anomaly_events WHERE strategy_id='grid' AND severity >= 'WARN' ORDER BY observed_at DESC` |

### 4.2 Index DDL

```sql
-- 主要 hot-path: per-taxonomy timeline (covering 9 taxonomy)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_anomaly_taxonomy_observed
    ON learning.anomaly_events (event_taxonomy, observed_at DESC);

-- Alert dashboard hot-path: severity CRITICAL/HALT (partial)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_anomaly_severity_observed
    ON learning.anomaly_events (severity, observed_at DESC)
    WHERE severity IN ('CRITICAL', 'HALT');

-- per-symbol query (partial;非 per-symbol event NULL 不索引)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_anomaly_symbol_observed
    ON learning.anomaly_events (symbol, observed_at DESC)
    WHERE symbol IS NOT NULL;

-- per-strategy query (partial;非 per-strategy event NULL 不索引)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_anomaly_strategy_observed
    ON learning.anomaly_events (strategy_id, observed_at DESC)
    WHERE strategy_id IS NOT NULL;
```

### 4.3 Partial index 理由

per V106 spec §4.3 同範式 + `db-schema-design-financial-time-series` skill §4.2:
- severity CRITICAL/HALT 預期 < 5% 整體 row → partial index 縮 95%
- symbol IS NOT NULL 預期 ~60% row(非 per-symbol regime_shift 等 NULL,per-symbol funding_outlier 等填)→ partial index 縮 40%
- strategy_id IS NOT NULL 預期 ~10% row(極少 strategy-specific anomaly;大多走 M3 strategy_quality domain)→ partial index 縮 90%

### 4.4 為什麼不加 `(engine_mode, observed_at)` index

per V106 spec §4.4 同範式:engine_mode 5 值 cardinality 太低 → index selectivity 不佳;PG 會用 bitmap scan;不需顯式 index。

### 4.5 為什麼不加 `(amplification_loop_24h_count, observed_at)` index

amplification_loop_24h_count 是 writer-side 預計算值不是 query filter;query pattern 用 `severity` + `observed_at` 已涵蓋。

---

## §5 Guard A / B / C(per CLAUDE.md §Data, Migrations, And Validation + V094 mirror + ADR-0036 forbidden algorithm reverse pattern)

V109 涉及 1 個 NEW hypertable CREATE + ADR-0036 黑名單反向防護,需 Guard A + Guard C(無 ALTER 既有 column 不需 Guard B)。

### 5.1 Guard A — table existence + 既有 schema 對齊驗證 + ADR-0036 forbidden algorithm reverse pattern

```sql
-- ============================================================
-- Guard A: V109 預檢 — 若 learning.anomaly_events 已存在,必驗 V109 spec column
-- 全俱在;缺即 RAISE。同時驗 TimescaleDB extension + V096 boundary + V098
-- governance.audit_log 存在。
-- 額外:反向防護 ADR-0036 Decision 1 黑名單(detection_method CHECK 不可含
-- hmm/markov_switching/garch)。
-- ============================================================
DO $$
DECLARE v_missing TEXT[];
DECLARE v_ts_ver TEXT;
DECLARE v_check_def TEXT;
BEGIN
    -- TimescaleDB extension prereq (V096 boundary)
    SELECT extversion INTO v_ts_ver
    FROM pg_extension WHERE extname='timescaledb';
    IF v_ts_ver IS NULL THEN
        RAISE EXCEPTION
            'V109 Guard A FAIL: TimescaleDB extension missing. '
            'V096 boundary not satisfied. Apply V096 first.';
    END IF;

    -- governance.audit_log 必須存在(M8 → governance cross-ref 雖無 FK 但 query JOIN 需要)
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='governance' AND table_name='audit_log'
    ) THEN
        RAISE EXCEPTION
            'V109 Guard A FAIL: governance.audit_log missing — '
            'V098 must apply before V109 (cross-ref query target). Verify _sqlx_migrations.';
    END IF;

    -- learning.anomaly_events 已存在的情境下 check column 完整性
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='learning' AND table_name='anomaly_events'
    ) THEN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'id', 'observed_at', 'event_taxonomy', 'severity', 'detection_method',
            'atr_vol_state', 'funding_state', 'strategy_id', 'symbol',
            'metric_value', 'metric_threshold',
            'amplification_loop_24h_count',
            'm3_health_observation_ref', 'm7_decay_signal_ref', 'm1_lal_demote_ref',
            'evidence_json', 'engine_mode',
            'created_by', 'created_at', 'updated_by', 'updated_at',
            'source_version'
        ]) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema='learning' AND table_name='anomaly_events'
              AND column_name=c
        );
        IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
            RAISE EXCEPTION
                'V109 Guard A FAIL: learning.anomaly_events exists but missing columns: %. '
                'Possible legacy stub conflict — resolve schema reconciliation before applying V109.',
                v_missing;
        END IF;

        -- 反向防護: detection_method CHECK 不可含 ADR-0036 Decision 1 黑名單
        SELECT pg_get_constraintdef(oid) INTO v_check_def
        FROM pg_constraint
        WHERE conrelid='learning.anomaly_events'::regclass
          AND conname LIKE '%detection_method%check%';
        IF v_check_def IS NOT NULL THEN
            IF position('hmm' IN lower(v_check_def)) > 0
               OR position('markov_switching' IN lower(v_check_def)) > 0
               OR position('garch' IN lower(v_check_def)) > 0
            THEN
                RAISE EXCEPTION
                    'V109 Guard A FAIL (ADR-0036 Decision 1 forbidden algorithm reverse pattern): '
                    'detection_method CHECK constraint contains forbidden algorithm. '
                    'HMM / Markov-switching / GARCH 永久禁用 per ADR-0036 Decision 1. '
                    'Any amendment to add such algorithm requires amend ADR-0036 first. '
                    'Actual CHECK definition: %', v_check_def;
            END IF;
        END IF;

        -- 同樣反向防護: column name 不可含 hmm_ / markov_ / garch_ prefix
        IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema='learning' AND table_name='anomaly_events'
              AND (column_name LIKE 'hmm_%'
                   OR column_name LIKE 'markov_%'
                   OR column_name LIKE 'garch_%'
                   OR column_name LIKE '%_hmm%'
                   OR column_name LIKE '%_garch%')
        ) THEN
            RAISE EXCEPTION
                'V109 Guard A FAIL (ADR-0036 Decision 1 forbidden algorithm reverse pattern): '
                'learning.anomaly_events contains column name matching forbidden algorithm pattern '
                '(hmm_* / markov_* / garch_*). Per ADR-0036 Decision 1 永久禁用 schema-level enforcement.';
        END IF;
    END IF;
END $$;
```

### 5.2 Guard B — 不適用

V109 不 ALTER 既有 column;無 type-sensitive 檢查需求。

### 5.3 Guard C — CHECK constraint + ENUM 值齊全 + hypertable + index + ADR-0036 forbidden algorithm hardening

```sql
-- ============================================================
-- Guard C: V109 預檢 — 重跑 V109 時 idempotent 檢查 CHECK constraint + 
-- hypertable + compression policy + retention policy + index 對齊。
-- 額外:ADR-0036 Decision 1 黑名單 hardening 二次驗(catch future amend drift)。
-- ============================================================
DO $$
DECLARE v_actual TEXT;
DECLARE v_chunk_interval BIGINT;
BEGIN
    -- event_taxonomy CHECK constraint 9 值齊全
    SELECT pg_get_constraintdef(oid) INTO v_actual
    FROM pg_constraint
    WHERE conrelid='learning.anomaly_events'::regclass
      AND conname LIKE '%event_taxonomy%check%';
    IF v_actual IS NOT NULL THEN
        IF position('regime_shift' IN v_actual) = 0
           OR position('liquidation_cascade' IN v_actual) = 0
           OR position('orderbook_imbalance' IN v_actual) = 0
           OR position('funding_outlier' IN v_actual) = 0
           OR position('volume_spike' IN v_actual) = 0
           OR position('spread_widening' IN v_actual) = 0
           OR position('price_dislocation' IN v_actual) = 0
           OR position('ws_disconnect' IN v_actual) = 0
           OR position('fee_anomaly' IN v_actual) = 0
        THEN
            RAISE EXCEPTION
                'V109 Guard C FAIL: learning.anomaly_events event_taxonomy CHECK enum mismatch. '
                'Actual: %. Expected to contain all 9 taxonomy values '
                '(regime_shift/liquidation_cascade/orderbook_imbalance/funding_outlier/'
                'volume_spike/spread_widening/price_dislocation/ws_disconnect/fee_anomaly).',
                v_actual;
        END IF;
    END IF;

    -- severity CHECK 4 值齊全
    SELECT pg_get_constraintdef(oid) INTO v_actual
    FROM pg_constraint
    WHERE conrelid='learning.anomaly_events'::regclass
      AND conname LIKE '%severity%check%';
    IF v_actual IS NOT NULL THEN
        IF position('INFO' IN v_actual) = 0
           OR position('WARN' IN v_actual) = 0
           OR position('CRITICAL' IN v_actual) = 0
           OR position('HALT' IN v_actual) = 0
        THEN
            RAISE EXCEPTION
                'V109 Guard C FAIL: severity CHECK enum mismatch. '
                'Actual: %. Expected INFO/WARN/CRITICAL/HALT.',
                v_actual;
        END IF;
    END IF;

    -- detection_method CHECK 4 值齊全 + ADR-0036 黑名單 hardening 二次驗
    SELECT pg_get_constraintdef(oid) INTO v_actual
    FROM pg_constraint
    WHERE conrelid='learning.anomaly_events'::regclass
      AND conname LIKE '%detection_method%check%';
    IF v_actual IS NOT NULL THEN
        IF position('atr_vol_funding_9cell' IN v_actual) = 0
           OR position('rv_percentile' IN v_actual) = 0
           OR position('block_bootstrap' IN v_actual) = 0
           OR position('manual_operator' IN v_actual) = 0
        THEN
            RAISE EXCEPTION
                'V109 Guard C FAIL: detection_method CHECK enum mismatch. '
                'Actual: %. Expected atr_vol_funding_9cell/rv_percentile/block_bootstrap/manual_operator.',
                v_actual;
        END IF;

        -- 二次驗:detection_method CHECK 不可含 ADR-0036 黑名單(同 Guard A 但 Guard C 重跑也驗)
        IF position('hmm' IN lower(v_actual)) > 0
           OR position('markov_switching' IN lower(v_actual)) > 0
           OR position('garch' IN lower(v_actual)) > 0
        THEN
            RAISE EXCEPTION
                'V109 Guard C FAIL (ADR-0036 Decision 1 forbidden algorithm hardening): '
                'detection_method CHECK constraint contains forbidden algorithm. '
                'HMM / Markov-switching / GARCH 永久禁用 per ADR-0036 Decision 1. '
                'Actual: %', v_actual;
        END IF;
    END IF;

    -- atr_vol_state CHECK 3 值齊全(NULL allowed)
    SELECT pg_get_constraintdef(oid) INTO v_actual
    FROM pg_constraint
    WHERE conrelid='learning.anomaly_events'::regclass
      AND conname LIKE '%atr_vol_state%check%';
    IF v_actual IS NOT NULL THEN
        IF position('LOW' IN v_actual) = 0
           OR position('MED' IN v_actual) = 0
           OR position('HIGH' IN v_actual) = 0
        THEN
            RAISE EXCEPTION
                'V109 Guard C FAIL: atr_vol_state CHECK enum mismatch. '
                'Actual: %. Expected LOW/MED/HIGH (per ADR-0036 §3.1 9-cell axis 1).',
                v_actual;
        END IF;
    END IF;

    -- funding_state CHECK 3 值齊全(NULL allowed)
    SELECT pg_get_constraintdef(oid) INTO v_actual
    FROM pg_constraint
    WHERE conrelid='learning.anomaly_events'::regclass
      AND conname LIKE '%funding_state%check%';
    IF v_actual IS NOT NULL THEN
        IF position('NEGATIVE' IN v_actual) = 0
           OR position('NEUTRAL' IN v_actual) = 0
           OR position('POSITIVE' IN v_actual) = 0
        THEN
            RAISE EXCEPTION
                'V109 Guard C FAIL: funding_state CHECK enum mismatch. '
                'Actual: %. Expected NEGATIVE/NEUTRAL/POSITIVE (per ADR-0036 §3.1 9-cell axis 2).',
                v_actual;
        END IF;
    END IF;

    -- engine_mode CHECK 5 值齊全(含 replay)
    SELECT pg_get_constraintdef(oid) INTO v_actual
    FROM pg_constraint
    WHERE conrelid='learning.anomaly_events'::regclass
      AND conname LIKE '%engine_mode%check%';
    IF v_actual IS NOT NULL THEN
        IF position('paper' IN v_actual) = 0
           OR position('demo' IN v_actual) = 0
           OR position('live_demo' IN v_actual) = 0
           OR position('live' IN v_actual) = 0
           OR position('replay' IN v_actual) = 0
        THEN
            RAISE EXCEPTION
                'V109 Guard C FAIL: engine_mode CHECK enum mismatch. '
                'Actual: %. Expected paper/demo/live_demo/live/replay (replay added per ADR-0036 Decision 1 例外段).',
                v_actual;
        END IF;
    END IF;

    -- Hypertable 已建立 + chunk_time_interval = 7 days (604800000000 microseconds)
    SELECT
        EXTRACT(EPOCH FROM time_interval) * 1000000
    INTO v_chunk_interval
    FROM timescaledb_information.dimensions
    WHERE hypertable_name='anomaly_events'
      AND column_name='observed_at';
    IF v_chunk_interval IS NOT NULL AND v_chunk_interval != 604800000000 THEN
        RAISE EXCEPTION
            'V109 Guard C FAIL: learning.anomaly_events chunk_time_interval mismatch. '
            'Actual: % microseconds. Expected: 604800000000 (7 days).',
            v_chunk_interval;
    END IF;

    -- Compression policy 存在(30 day after)
    IF NOT EXISTS (
        SELECT 1 FROM timescaledb_information.jobs
        WHERE proc_name='policy_compression'
          AND hypertable_name='anomaly_events'
    ) THEN
        RAISE NOTICE 'V109 Guard C NOTE: compression policy not yet applied for anomaly_events. '
                     'Will be added by main migration body.';
    END IF;

    -- Retention policy 存在(180 day after)
    IF NOT EXISTS (
        SELECT 1 FROM timescaledb_information.jobs
        WHERE proc_name='policy_retention'
          AND hypertable_name='anomaly_events'
    ) THEN
        RAISE NOTICE 'V109 Guard C NOTE: retention policy not yet applied for anomaly_events. '
                     'Will be added by main migration body.';
    END IF;
END $$;
```

### 5.4 Guard 設計理念(per V106 mirror + ADR-0036 forbidden algorithm hardening)

| Guard | 觸發場景 | RAISE 條件 | NOT RAISE 條件(idempotent)|
|---|---|---|---|
| A | NEW table 已存在但 column 缺;TimescaleDB extension 缺;governance.audit_log 缺;**detection_method CHECK 含黑名單算法**;**column name 含 hmm_/markov_/garch_ pattern** | RAISE | 全 column 俱在 / table 不存在(首次跑)/ CHECK 不含黑名單 |
| C | CHECK constraint 缺 enum 值;hypertable interval 不對;**detection_method CHECK 二次驗黑名單**| RAISE | constraint 不存在(首次跑)/ constraint 完整(重跑) |
| C policy | compression / retention policy 首次跑不存在 | NOTICE(不 RAISE,migration body 會建)| policy 已存在重跑(skip) |

重跑 V109 第二次必不 RAISE(idempotency per CLAUDE.md §Data, Migrations, And Validation V055/V083/V084 incident precedent)。

### 5.5 為什麼 Guard A + Guard C 二次驗黑名單(redundant 為 fail-safe)

per ADR-0036 Decision 1 + M8 design spec §3:
- HMM / Markov / GARCH 黑名單是 ADR 級永久禁用,任何 future amend drift 必先 amend ADR-0036
- Guard A 在 table existence check 內驗黑名單(catch 既有 schema drift)
- Guard C 在 idempotent re-run 內二次驗(catch CI / staging amend drift)
- 兩次驗是 cost-effective(每次 V109 migration 跑 < 10ms);failure 成本(HMM 進 production)遠高於 redundant guard cost

---

## §6 Migration up + down SQL

### 6.1 Migration UP(完整 V109.sql 設計)

```sql
-- ============================================================
-- V109: learning.anomaly_events + hypertable + compression + retention
-- M8 Anomaly Events Schema (9 event_taxonomy × 4 severity × 4 detection_method)
-- ADR-0036 Decision 1 forbidden algorithm hardening (HMM/Markov/GARCH 永久禁用)
-- ============================================================

-- Step 1: Guard A (per §5.1; 含 ADR-0036 forbidden algorithm reverse pattern)
-- [全文見 §5.1]

-- Step 2: Guard C 預檢 (per §5.3; 重跑 idempotency + 二次驗黑名單)
-- [全文見 §5.3]

-- Step 3: CREATE TABLE
CREATE TABLE IF NOT EXISTS learning.anomaly_events (
    -- (per §2.1 完整 DDL)
    id                              BIGSERIAL,
    observed_at                     TIMESTAMPTZ NOT NULL,
    event_taxonomy                  TEXT NOT NULL CHECK (event_taxonomy IN (...)),
    severity                        TEXT NOT NULL CHECK (severity IN (...)),
    detection_method                TEXT NOT NULL CHECK (detection_method IN (...)),
    atr_vol_state                   TEXT CHECK (atr_vol_state IS NULL OR atr_vol_state IN (...)),
    funding_state                   TEXT CHECK (funding_state IS NULL OR funding_state IN (...)),
    strategy_id                     TEXT,
    symbol                          TEXT,
    metric_value                    NUMERIC(18,8),
    metric_threshold                NUMERIC(18,8),
    amplification_loop_24h_count    INTEGER NOT NULL DEFAULT 0,
    m3_health_observation_ref       BIGINT,
    m7_decay_signal_ref             BIGINT,
    m1_lal_demote_ref               BIGINT,
    evidence_json                   JSONB,
    engine_mode                     TEXT NOT NULL CHECK (engine_mode IN ('paper','demo','live_demo','live','replay')),
    created_by                      TEXT NOT NULL DEFAULT 'anomaly_detector',
    created_at                      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by                      TEXT,
    updated_at                      TIMESTAMPTZ,
    source_version                  TEXT NOT NULL DEFAULT 'V109',
    PRIMARY KEY (id, observed_at)
);

-- Step 4: Hypertable
SELECT create_hypertable(
    'learning.anomaly_events',
    'observed_at',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists => TRUE
);

-- Step 5: Compression
ALTER TABLE learning.anomaly_events SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'event_taxonomy, severity',
    timescaledb.compress_orderby = 'observed_at DESC, id DESC'
);

-- Step 6: Compression + Retention policies (idempotent)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM timescaledb_information.jobs
        WHERE proc_name='policy_compression' AND hypertable_name='anomaly_events'
    ) THEN
        PERFORM add_compression_policy('learning.anomaly_events', INTERVAL '30 days');
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM timescaledb_information.jobs
        WHERE proc_name='policy_retention' AND hypertable_name='anomaly_events'
    ) THEN
        PERFORM add_retention_policy('learning.anomaly_events', INTERVAL '180 days');
    END IF;
END $$;

-- Step 7: Hot-path indexes (CONCURRENTLY for non-blocking)
-- (per §4.2)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_anomaly_taxonomy_observed
    ON learning.anomaly_events (event_taxonomy, observed_at DESC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_anomaly_severity_observed
    ON learning.anomaly_events (severity, observed_at DESC)
    WHERE severity IN ('CRITICAL', 'HALT');

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_anomaly_symbol_observed
    ON learning.anomaly_events (symbol, observed_at DESC)
    WHERE symbol IS NOT NULL;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_anomaly_strategy_observed
    ON learning.anomaly_events (strategy_id, observed_at DESC)
    WHERE strategy_id IS NOT NULL;

-- Step 8: COMMENT (audit metadata)
COMMENT ON TABLE learning.anomaly_events IS
    'M8 Anomaly Events Hypertable (V109). 9 event_taxonomy × 4 severity × 4 detection_method '
    '× per-symbol/strategy 觀測; '
    'ADR-0036 Decision 1 黑名單: HMM/Markov-switching/GARCH 永久禁用 schema-level enforcement '
    '(Guard A/C 反向防護); '
    'ADR-0036 Decision 2-4 替代算法: ATR-vol × Funding 9-cell + RV percentile + block bootstrap; '
    'amplification cap H-11 enforced via writer-side query; '
    '7d chunk + 30d compression + 180d retention.';

COMMENT ON COLUMN learning.anomaly_events.detection_method IS
    'ADR-0036 Decision 1 黑名單算法 schema-level enforcement: 不可含 hmm/markov_switching/garch '
    '(Guard A + C 雙重反向防護)。任何 future amend 必先 amend ADR-0036 Decision 1。';

COMMENT ON COLUMN learning.anomaly_events.amplification_loop_24h_count IS
    'H-11 cap (per M8 design spec §5): 24h 同 event_taxonomy CRITICAL/HALT count; '
    'writer 預計算; ≥ 2 雖 INSERT 但 evidence_json 標 cap_suppressed=true 不 emit M3 cascade。';

COMMENT ON COLUMN learning.anomaly_events.m1_lal_demote_ref IS
    'M1 LAL Tier 降階 V112 row id 反向 ref (per M8 design spec §9.3)。'
    '對齊 ADR-0034 數字越大越嚴方向 — ref 指向 Tier 降低後 row。';
```

### 6.2 Migration DOWN(rollback;dev-only,production 慎用)

```sql
-- ============================================================
-- V109 ROLLBACK: 刪 hypertable + policies + indexes + table
-- ⚠️ DESTRUCTIVE: 180d 之內所有 anomaly events 全 drop;不可恢復。
-- 僅 dev/staging 使用;production rollback 走 V### 升級而非 down。
-- ============================================================

-- Step 1: Remove policies first
SELECT remove_compression_policy('learning.anomaly_events', if_exists => TRUE);
SELECT remove_retention_policy('learning.anomaly_events', if_exists => TRUE);

-- Step 2: Drop indexes
DROP INDEX CONCURRENTLY IF EXISTS learning.idx_anomaly_strategy_observed;
DROP INDEX CONCURRENTLY IF EXISTS learning.idx_anomaly_symbol_observed;
DROP INDEX CONCURRENTLY IF EXISTS learning.idx_anomaly_severity_observed;
DROP INDEX CONCURRENTLY IF EXISTS learning.idx_anomaly_taxonomy_observed;

-- Step 3: Drop hypertable + table (CASCADE 處理 chunks)
DROP TABLE IF EXISTS learning.anomaly_events CASCADE;
```

### 6.3 Idempotency 驗證

per V055 5-round loop + V083/V084 incident precedent,V109.sql 必跑兩次:
- 第一次:CREATE TABLE + hypertable + policies + indexes → 0 RAISE / 0 ERROR
- 第二次:全 IF NOT EXISTS / 已 hypertable / 已 policies → 0 RAISE / 0 重複 policy

---

## §7 Materialized View(本 spec 不需)

V109 不含 materialized view。理由:
- anomaly event row 量小(180d 內 < 50k row),query 直接走 hypertable + partial index 已快
- long-term trend aggregation 非本 spec scope(Sprint 3+ 補 daily aggregate 表)
- M8 hot path query 走 partial index + chunk pruning,無需 mv 加速

未來 Sprint 3+ 若加 daily aggregate:
```sql
-- 例(Sprint 3+ 後續):
-- CREATE MATERIALIZED VIEW learning.anomaly_events_daily_agg AS
-- SELECT date_trunc('day', observed_at) AS day,
--        event_taxonomy, severity, count(*),
--        max(metric_value), avg(amplification_loop_24h_count)
-- FROM learning.anomaly_events
-- WHERE engine_mode IN ('live','live_demo')
-- GROUP BY 1, 2, 3;
```

---

## §8 Cross-V### Dependency + Cross-Ref Schema

### 8.1 Cross-V### dependency 圖

```
V096 (drop dead learning tables; TimescaleDB extension) ← V109 (prereq; hypertable infra)
V098 (governance.audit_log)                              ← V109 (cross-ref query target; 非 FK)
V109 (M8 anomaly events; standalone)
       │
       ├─→ V106 (M3 health_observations) — CRITICAL/HALT → M3 HEALTH_DEGRADED/CRITICAL (cross-ref query)
       ├─→ V112 (M1 LAL) — anomaly 90d incident-free → eligibility (cross-ref query;m1_lal_demote_ref BIGINT 弱關聯)
       ├─→ V113 (M7 decay_signals) — persistent anomaly 14d → source 5 (cross-ref query;m7_decay_signal_ref BIGINT 弱關聯)
       ├─→ V107 (M11 replay) — CR-7 dedup contract; M11 不直接 emit M8 (純 application 層 cross-ref)
       └─→ V108 (M9 ab_test_assignments) — CRITICAL anomaly → mark paused (cross-ref query)
```

### 8.2 為什麼 M8 是 standalone(無 hard FK)

per V106 spec §8.2 同範式 + `db-schema-design-financial-time-series` skill §5:
- M8 是 observational sensor 不是 governance object
- FK 太重(每 INSERT 都查 FK target;90-300 INSERT/min 過熱)
- FK 跨 hypertable 在 TimescaleDB 不支援 partition-aware
- cross-ref query 走 join-time fetch(per pattern V094 + V083 既有 + V106 spec §8.4 範式)
- `m3_health_observation_ref` / `m7_decay_signal_ref` / `m1_lal_demote_ref` 為 BIGINT 弱關聯 — application 層維持 integrity + healthcheck 補

### 8.3 V106 (M3) cross-ref pattern

```sql
-- 例 1: M8 CRITICAL anomaly emit 後 application 層 trigger M3 HEALTH_DEGRADED INSERT
-- 後將 V106 INSERT 返回的 observation_id 寫回 V109 的 m3_health_observation_ref
UPDATE learning.anomaly_events
SET m3_health_observation_ref = $v106_inserted_observation_id,
    updated_at = now(),
    updated_by = 'anomaly_detector'
WHERE id = $v109_inserted_id;

-- 例 2: 查 anomaly 影響的 M3 health observation
SELECT a.id AS anomaly_id, a.event_taxonomy, a.severity,
       h.observation_id, h.domain, h.state
FROM learning.anomaly_events a
LEFT JOIN learning.health_observations h ON a.m3_health_observation_ref = h.observation_id
WHERE a.severity IN ('CRITICAL', 'HALT')
  AND a.observed_at > now() - INTERVAL '24 hours'
  AND a.engine_mode IN ('live', 'live_demo');
```

### 8.4 V112 (M1 LAL) cross-ref pattern

```sql
-- 例: M1 LAL Tier 升階 eligibility check 需查 V109 incident-free 90d (per M8 design spec §9.4)
SELECT COUNT(*) FROM learning.anomaly_events
WHERE strategy_id = 'grid'
  AND severity IN ('CRITICAL', 'HALT')
  AND observed_at > now() - INTERVAL '90 days'
  AND engine_mode IN ('live', 'live_demo')
  AND (evidence_json->>'cap_suppressed' IS NULL OR (evidence_json->>'cap_suppressed')::boolean = false);
-- > 0 → eligibility fail
-- 注意: cap_suppressed=true 的 row 不計入 (amplification cap 抑制的同 type 重複 trigger)
```

### 8.5 V113 (M7) cross-ref pattern

```sql
-- 例: M7 source 5 persistent anomaly 14d cron 計算 (per M8 design spec §7)
SELECT symbol, event_taxonomy,
       COUNT(DISTINCT date_trunc('day', observed_at)) AS distinct_days_in_14d
FROM learning.anomaly_events
WHERE severity >= 'WARN'  -- 含 WARN+CRITICAL+HALT;INFO 不計
  AND observed_at > now() - INTERVAL '14 days'
  AND engine_mode IN ('live', 'live_demo')
GROUP BY symbol, event_taxonomy
HAVING COUNT(DISTINCT date_trunc('day', observed_at)) >= 7;
-- 結果每 row → INSERT 1 V113 row source 5 + m7_decay_signal_ref 寫回 V109 anomaly_events
```

### 8.6 V108 (M9) cross-ref pattern

```sql
-- 例: M9 A/B sampling query 自動 exclude anomaly window (per M8 design spec §8.4)
SELECT ab.assignment_id, ab.strategy_id, ab.symbol, ab.sample_value
FROM learning.ab_test_assignments ab
LEFT JOIN learning.anomaly_events ae 
  ON ab.symbol = ae.symbol 
  AND ab.strategy_id = ae.strategy_id
  AND ae.severity IN ('CRITICAL', 'HALT')
  AND ae.observed_at BETWEEN ab.sample_at - INTERVAL '5 minutes' AND ab.sample_at + INTERVAL '30 minutes'
WHERE ae.id IS NULL  -- 排除 anomaly window 內 sample
  AND ab.engine_mode IN ('live', 'live_demo');
```

### 8.7 為什麼 V112 / V113 / V108 走 cross-ref 而非 FK

per V106 spec §8.6 同範式:

| 設計選擇 | 優 | 缺 | 採用 |
|---|---|---|---|
| **FK constraint** | 強約束;join 簡單 | INSERT cost(每筆查 FK target);schema drift 風險;hard dependency 鎖 dispatch sequence;TimescaleDB hypertable FK 不支援 partition-aware | ❌ 不採 |
| **Cross-ref query + BIGINT 弱關聯**(本 spec) | INSERT 0 overhead;dispatch sequence 解耦;hypertable 互不耦合 | 弱約束;依 application logic 維持 referential integrity;需 healthcheck 補 | ✅ 採 |

---

## §9 Linux PG Empirical Dry-Run Protocol(mandatory)

per CLAUDE.md §Data, Migrations, And Validation + `feedback_v_migration_pg_dry_run.md` + V055 5-round loop / V083 / V084 incident chain,V109 涉及:
- TimescaleDB extension hypertable creation (PG-specific syntax)
- compression / retention policy add_*_policy() function 真實返回
- partial index CONCURRENTLY 在 hypertable chunks 上的行為
- CHECK constraint ENUM runtime semantic(尤其 9 event_taxonomy 9 值齊全 + 4 detection_method + ADR-0036 forbidden algorithm 反向防護 RAISE 真觸發)

**必先 Linux PG empirical 驗證**,禁 Mac mock pytest 代替。

### 9.1 PA C9 待補的 PG reflection query(spec sign-off 前必補)

per CLAUDE.md `docs/agents/context-loading.md` "PG Connection Examples"(Linux runtime authoritative):

```bash
# Connection (per V106 dry-run §9.1):
# psql -h 127.0.0.1 -p 5432 -U trading_admin -d trading_ai

# Query 1: _sqlx_migrations head 確認
ssh trade-core "PGPASSWORD=\$(cat ~/.pgpass | grep trading_ai | cut -d: -f5) psql -h 127.0.0.1 -p 5432 -U trading_admin -d trading_ai -c 'SELECT max(version) FROM _sqlx_migrations'"
# Expected: ≥ V108 (V106 + V107 + V108 + V112 都 land Sprint 1A-β/γ wave)

# Query 2: TimescaleDB extension 確認
ssh trade-core "PGPASSWORD=\$(cat ~/.pgpass | grep trading_ai | cut -d: -f5) psql -h 127.0.0.1 -p 5432 -U trading_admin -d trading_ai -c \"SELECT extversion FROM pg_extension WHERE extname='timescaledb'\""
# Expected: ≥ 2.13

# Query 3: governance.audit_log 已 land 驗
ssh trade-core "PGPASSWORD=\$(cat ~/.pgpass | grep trading_ai | cut -d: -f5) psql -h 127.0.0.1 -p 5432 -U trading_admin -d trading_ai -c \"SELECT count(*) FROM information_schema.tables WHERE table_schema='governance' AND table_name='audit_log'\""
# Expected: 1

# Query 4: learning.anomaly_events 是否已存在(legacy stub conflict 檢測)
ssh trade-core "PGPASSWORD=\$(cat ~/.pgpass | grep trading_ai | cut -d: -f5) psql -h 127.0.0.1 -p 5432 -U trading_admin -d trading_ai -c \"SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema='learning' AND table_name='anomaly_events'\""
# Expected: 0 rows (greenfield); 若 1 row → 觸 Guard A 反向檢查
```

**待 PA C9 補資料的 4 處 placeholder**(spec sign-off 前必更新):
1. `_sqlx_migrations` head 真實 = ?
2. TimescaleDB extension version 真實 = ?
3. governance.audit_log 已 land 確認 = ?
4. learning.anomaly_events stub 不存在確認 = ?

### 9.2 Round 1 — V109 SQL 真實 PG semantic empirical 驗證

```bash
ssh trade-core "
  cd ~/BybitOpenClaw/srv && \
  PGPASSWORD=\$(cat ~/.pgpass | grep trading_ai | cut -d: -f5) \
  psql -h 127.0.0.1 -p 5432 -U trading_admin -d trading_ai \
    -v ON_ERROR_STOP=1 -f sql/migrations/V109__m8_anomaly_events_hypertable.sql
"
```

**Round 1 必驗 10 項**(empirical SELECT verify after V109 apply):

```sql
-- 1. learning.anomaly_events 表存在 + 22 columns
SELECT count(*) FROM information_schema.columns
WHERE table_schema='learning' AND table_name='anomaly_events';
-- Expected: 22

-- 2. Hypertable 真建立 + chunk_time_interval = 7 days
SELECT hypertable_name, time_interval, column_name
FROM timescaledb_information.dimensions
WHERE hypertable_name='anomaly_events';
-- Expected: 1 row; time_interval = '7 days'; column_name = 'observed_at'

-- 3. Compression policy 真設定(30 day after;對比 V106 7 day)
SELECT proc_name, hypertable_name, schedule_interval, config
FROM timescaledb_information.jobs
WHERE proc_name='policy_compression' AND hypertable_name='anomaly_events';
-- Expected: 1 row; config 含 compress_after = '30 days'

-- 4. Retention policy 真設定(180 day;對比 V106 90 day)
SELECT proc_name, hypertable_name, config
FROM timescaledb_information.jobs
WHERE proc_name='policy_retention' AND hypertable_name='anomaly_events';
-- Expected: 1 row; config 含 drop_after = '180 days'

-- 5. event_taxonomy CHECK 9 值齊全
SELECT pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid='learning.anomaly_events'::regclass AND conname LIKE '%event_taxonomy%check%';
-- Expected: 含 regime_shift / liquidation_cascade / orderbook_imbalance / funding_outlier /
--          volume_spike / spread_widening / price_dislocation / ws_disconnect / fee_anomaly

-- 6. severity CHECK 4 值齊全(INFO/WARN/CRITICAL/HALT)
SELECT pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid='learning.anomaly_events'::regclass AND conname LIKE '%severity%check%';

-- 7. detection_method CHECK 4 值齊全 + 不含 ADR-0036 黑名單
SELECT pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid='learning.anomaly_events'::regclass AND conname LIKE '%detection_method%check%';
-- Expected: 含 atr_vol_funding_9cell / rv_percentile / block_bootstrap / manual_operator
-- Expected: 不含 hmm / markov_switching / garch (任一 substring)

-- 8. ADR-0036 forbidden algorithm column name 反向防護 verify
SELECT column_name FROM information_schema.columns
WHERE table_schema='learning' AND table_name='anomaly_events'
  AND (column_name LIKE 'hmm_%' OR column_name LIKE 'markov_%' OR column_name LIKE 'garch_%'
       OR column_name LIKE '%_hmm%' OR column_name LIKE '%_garch%');
-- Expected: 0 row

-- 9. 4 hot-path indexes 確認
SELECT indexname FROM pg_indexes
WHERE schemaname='learning' AND tablename='anomaly_events'
ORDER BY indexname;
-- Expected: ≥ 5 (1 PK + idx_anomaly_taxonomy_observed + idx_anomaly_severity_observed
--                + idx_anomaly_symbol_observed + idx_anomaly_strategy_observed)

-- 10. engine_mode CHECK 5 值齊全(含 replay) + reject 第 6 個 (empirical INSERT test)
BEGIN;
SAVEPOINT test_engine_mode;
INSERT INTO learning.anomaly_events
    (observed_at, event_taxonomy, severity, detection_method, engine_mode)
VALUES
    (NOW(), 'regime_shift', 'INFO', 'rv_percentile', 'INVALID_MODE');
-- Expected: ERROR: violates check constraint
ROLLBACK TO SAVEPOINT test_engine_mode;

-- 10a. 同時測 event_taxonomy CHECK
SAVEPOINT test_taxonomy;
INSERT INTO learning.anomaly_events
    (observed_at, event_taxonomy, severity, detection_method, engine_mode)
VALUES
    (NOW(), 'INVALID_TAXONOMY', 'INFO', 'rv_percentile', 'live');
-- Expected: ERROR: violates check constraint
ROLLBACK TO SAVEPOINT test_taxonomy;

-- 10b. 同時測 severity CHECK
SAVEPOINT test_severity;
INSERT INTO learning.anomaly_events
    (observed_at, event_taxonomy, severity, detection_method, engine_mode)
VALUES
    (NOW(), 'regime_shift', 'INVALID_SEVERITY', 'rv_percentile', 'live');
-- Expected: ERROR: violates check constraint
ROLLBACK TO SAVEPOINT test_severity;

-- 10c. 同時測 detection_method CHECK(嘗試 hmm)
SAVEPOINT test_detection_method;
INSERT INTO learning.anomaly_events
    (observed_at, event_taxonomy, severity, detection_method, engine_mode)
VALUES
    (NOW(), 'regime_shift', 'INFO', 'hmm', 'live');
-- Expected: ERROR: violates check constraint
ROLLBACK TO SAVEPOINT test_detection_method;

-- 10d. 同時測 atr_vol_state CHECK
SAVEPOINT test_atr_vol_state;
INSERT INTO learning.anomaly_events
    (observed_at, event_taxonomy, severity, detection_method, atr_vol_state, engine_mode)
VALUES
    (NOW(), 'regime_shift', 'INFO', 'atr_vol_funding_9cell', 'INVALID_STATE', 'live');
-- Expected: ERROR: violates check constraint
ROLLBACK TO SAVEPOINT test_atr_vol_state;

-- 10e. 同時測 funding_state CHECK
SAVEPOINT test_funding_state;
INSERT INTO learning.anomaly_events
    (observed_at, event_taxonomy, severity, detection_method, funding_state, engine_mode)
VALUES
    (NOW(), 'regime_shift', 'INFO', 'atr_vol_funding_9cell', 'INVALID_FUNDING', 'live');
-- Expected: ERROR: violates check constraint
ROLLBACK TO SAVEPOINT test_funding_state;

ROLLBACK;
```

### 9.3 Round 2 — Idempotency 驗證

重跑 V109.sql 第二次必不 RAISE / 必不重複建 hypertable / 必不重複 policy:

```bash
ssh trade-core "
  cd ~/BybitOpenClaw/srv && \
  PGPASSWORD=\$(cat ~/.pgpass | grep trading_ai | cut -d: -f5) \
  psql -h 127.0.0.1 -p 5432 -U trading_admin -d trading_ai \
    -v ON_ERROR_STOP=1 -f sql/migrations/V109__m8_anomaly_events_hypertable.sql
"
# Expected exit code 0; all DO blocks output NOTICE-only PASS; 0 RAISE EXCEPTION
```

**Round 2 後驗證**:
```sql
-- 確認 V109 不 double-create
SELECT count(*) FROM information_schema.tables
WHERE table_schema='learning' AND table_name='anomaly_events';
-- Expected: 1

-- 確認 hypertable 不 double
SELECT count(*) FROM timescaledb_information.dimensions
WHERE hypertable_name='anomaly_events';
-- Expected: 1

-- 確認 policies 不 double
SELECT count(*) FROM timescaledb_information.jobs
WHERE hypertable_name='anomaly_events';
-- Expected: 2 (compression + retention)

-- 確認 indexes 不 double
SELECT count(*) FROM pg_indexes
WHERE schemaname='learning' AND tablename='anomaly_events'
  AND indexname IN (
    'idx_anomaly_taxonomy_observed',
    'idx_anomaly_severity_observed',
    'idx_anomaly_symbol_observed',
    'idx_anomaly_strategy_observed'
  );
-- Expected: 4
```

### 9.4 Round 3 — ADR-0036 forbidden algorithm 反向防護 RAISE 真觸發 verify

per ADR-0036 Decision 1 + §5.1 Guard A + §5.3 Guard C 黑名單 hardening,必 empirical 驗 RAISE 真觸發:

```bash
# 創建 fake migration 模擬 future drift 加入 hmm:
cat > /tmp/V109_drift_test.sql << 'EOF'
-- 模擬:未來不當 amend 加入 hmm column
ALTER TABLE learning.anomaly_events 
  ALTER CONSTRAINT learning_anomaly_events_detection_method_check 
  ... (假設改 CHECK 加 'hmm');
-- 然後重跑 V109 應 RAISE
EOF

# 預期: Guard A + Guard C 雙重 catch:
# RAISE EXCEPTION 'V109 Guard A FAIL (ADR-0036 Decision 1 forbidden algorithm reverse pattern): ...'
# RAISE EXCEPTION 'V109 Guard C FAIL (ADR-0036 Decision 1 forbidden algorithm hardening): ...'
```

實際 staging 環境 test 期 PA 主責執行;production 不 test(避免污染)。

### 9.5 為何 Mac mock pytest 不夠

per V106 spec §9.4 同教訓 + memory `feedback_v_migration_pg_dry_run.md`:
- Mac mock pytest 無法捕捉 TimescaleDB `create_hypertable()` 真實返回 metadata
- Mac static parse review 無法驗 `add_compression_policy(30d)` vs V106 `add_compression_policy(7d)` 對既有 job 衝突的處理(同 schema 不同 hypertable)
- Mac 無法驗 CHECK constraint runtime ENUM behavior(尤其 5 ENUM × 9+4+4+3+3+5 = 28 values empirical verify)
- Mac 無法驗 Guard A + C 雙重 forbidden algorithm RAISE 是否真觸發
- V055 chain 5 round 都 Mac false-pass 後 Linux 撞 bug;V094 / V106 / V109 全須遵守 V055 mandate

**E2 / E4 / A3 review 必含 Linux PG dry-run gate 證據 ID**(per CLAUDE.md §Data, Migrations, And Validation + V094 §4.3 範式)。

---

## §10 Engine Restart 實測 SOP(per 2026-05-02 sqlx hash drift 教訓)

per memory `project_2026_05_02_p0_sqlx_hash_drift`(commit `3681f83`),V109 file edit 後 DB checksum 必同步:

```bash
# E1 IMPL: 寫 V109.sql 完成後跑 Linux dry-run (per §9.2)
# 若 V109.sql 落地後又被 edit → DB checksum drift
# 必跑 repair binary 同步 checksum 到 _sqlx_migrations table

ssh trade-core "
  cd ~/BybitOpenClaw/srv && \
  cargo run --release --bin repair_migration_checksum -- --version 109
"
# Expected: V109 checksum updated in _sqlx_migrations table to match new file SHA
```

### 10.1 Engine restart 後驗證 sqlx migrate 不 panic

```bash
ssh trade-core "bash ~/BybitOpenClaw/srv/helper_scripts/restart_all.sh --rebuild"

ssh trade-core "tail -200 ~/BybitOpenClaw/srv/program_code/exchange_connectors/bybit_connector/openclaw_engine/logs/engine.log 2>&1 | grep -E 'sqlx|migration|panic|V109'"
# Expected: 0 panic; 'Applied migration V109' 正常 log; V109 success=t in _sqlx_migrations

ssh trade-core "PGPASSWORD=\$(cat ~/.pgpass | grep trading_ai | cut -d: -f5) psql -h 127.0.0.1 -p 5432 -U trading_admin -d trading_ai -c 'SELECT version, success, description FROM _sqlx_migrations WHERE version=109'"
# Expected: 1 row, success=t
```

### 10.2 治理盲點防範

per `project_2026_05_02_p0_sqlx_hash_drift` + V106 §10.2:cargo test PASS ≠ runtime sqlx migrate 驗證。E2 / E4 review 必含「engine restart 實測 + sqlx migrate runtime 不 panic」driver evidence。

---

## §11 Rollback Plan + Reversibility Analysis

### 11.1 V109 rollback DDL

詳見 §6.2(`DROP TABLE ... CASCADE` + drop policies + drop indexes)。

### 11.2 Reversibility 分析

| 操作 | 可逆? | 風險 |
|---|---|---|
| `DROP TABLE learning.anomaly_events CASCADE` | 邏輯可逆(rerun V109)但 row data 不可逆(全 drop)| **HIGH** — 180d 全 anomaly evidence 資料丟失;影響 M7 14d persistent / M1 LAL 90d incident-free check |
| `remove_compression_policy()` / `remove_retention_policy()` | 可逆(rerun V109 重設)| LOW |
| `DROP INDEX CONCURRENTLY` | 可逆(rerun V109 重建)| LOW |

### 11.3 Rollback 觸發條件

- 僅 dev / staging
- production rollback 走 V### 升級(e.g. V###+1 加 ADD COLUMN / 改 CHECK constraint;不走 V109 down)

### 11.4 V096 boundary

per V106 spec §11.4 + V101 spec v3 §7:rollback 路徑不跨 V096(V096 drop dead tables 不可逆)。V109 rollback 全在 V096 之後(V096 < V098 < V106 < V109),無 boundary 風險。

---

## §12 Audit Field(per V103 EXTEND 範式)

V109 採 V103 EXTEND §14 + V106 §12 同範式 5 audit field:

| Column | DEFAULT | NOT NULL | 設計 |
|---|---|---|---|
| `created_by` | 'anomaly_detector' | NOT NULL | writer process 名;允許 'anomaly_detector' / 'cowork-agent' / 'operator' / 'm11_replay_engine' / 'm7_decay_writer' / 'm1_lal_demote_writer' / 'system' |
| `created_at` | now() | NOT NULL | row insert 時間(server trusted)|
| `updated_by` | NULL | NULLABLE | 後續 update 的 actor(若 amplification cap backfill / cross-module ref 補填)|
| `updated_at` | NULL | NULLABLE | last update 時間 |
| `source_version` | 'V109' | NOT NULL | schema version tag;未來 schema migration audit;當前固定 V109 |

### 12.1 為什麼 anomaly_events 需 audit field

per DOC-08 §12 #8 安全不變量「交易可解釋」+ V106 spec §12.1:anomaly event 是 M3 cascade / M7 source 5 / M1 LAL demote 的決定 input;每個 event 必有 audit trail 才能 reproduce。

### 12.2 update_at / update_by 何時填

3 場景:
1. **amplification cap backfill**:M8 writer INSERT 後另一 cron job 重 計算 24h count 並 UPDATE `amplification_loop_24h_count` → set `updated_at = now()` + `updated_by = 'anomaly_detector'`
2. **m3_health_observation_ref 補填**:M8 INSERT V109 row → M3 INSERT V106 row → application 層 UPDATE V109 row `m3_health_observation_ref = $v106_id` → set `updated_at = now()` + `updated_by = 'anomaly_detector'`
3. **m7_decay_signal_ref 補填**:M7 cron(per §8.5)INSERT V113 → UPDATE V109 對應 anomaly row `m7_decay_signal_ref = $v113_id` → set `updated_at = now()` + `updated_by = 'm7_decay_writer'`

---

## §13 Acceptance Criteria(5-7 條 sign-off 標準)

### 13.1 Schema acceptance(MIT + E5)

| # | 標準 | 驗證方法 |
|---|---|---|
| 1 | `learning.anomaly_events` 表 22 column 全俱在 | `SELECT count(*) FROM information_schema.columns WHERE ...` = 22 |
| 2 | Hypertable + chunk_time_interval=7d 真建立 | `SELECT time_interval FROM timescaledb_information.dimensions WHERE ...` |
| 3 | Compression policy 30d after + retention policy 180d after 真設 | `SELECT * FROM timescaledb_information.jobs WHERE ...` (2 jobs) |
| 4 | 6 ENUM(event_taxonomy 9 / severity 4 / detection_method 4 / atr_vol_state 3 / funding_state 3 / engine_mode 5)CHECK constraint 真 reject invalid + ADR-0036 forbidden algorithm reject | empirical INSERT test(per §9.2 step 10a-e)|
| 5 | 4 hot-path index + 1 PK 真建立 | `SELECT indexname FROM pg_indexes WHERE ...` ≥ 5 |
| 6 | V109.sql idempotent 雙跑 0 RAISE | `psql -f V109.sql` × 2 |
| 7 | ADR-0036 forbidden algorithm 反向防護 RAISE 真觸發 + sqlx checksum 對齊 + engine restart 後 success=t | per §9.4 + §10 SOP |

### 13.2 Cross-V### acceptance(PA)

| # | 標準 | 驗證方法 |
|---|---|---|
| 1 | V096 + V098 prereq 滿足 | `SELECT version FROM _sqlx_migrations WHERE version IN (96, 98)` |
| 2 | V106 / V112 / V113 / V107 / V108 cross-ref query pattern 不破壞 V109 schema | per §8.3-§8.6 範例 query 預跑 |

### 13.3 治理 acceptance(QA + R4)

| # | 標準 | 驗證方法 |
|---|---|---|
| 1 | engine_mode IN ('live','live_demo') filter 在所有 cross-ref query 出現 | per §8 範例對齊 |
| 2 | 5 audit field 預設值 reasonable | INSERT row 不填 audit field 後 SELECT 驗 DEFAULT |
| 3 | docs/README.md 加 V109 spec 入 index | per CLAUDE.md §七 docs/README 規則 |
| 4 | ADR-0036 Decision 1 黑名單 schema-level enforcement (Guard A + C 雙重)真觸發 RAISE | per §9.4 staging test + E4 regression CI |

---

## §14 開放問題 + Caveat

### 14.1 待 PA C9 確認

1. **`_sqlx_migrations` head 真實**(per §9.1 Query 1)— spec 假設 ≥ V108
2. **TimescaleDB extension version**(per §9.1 Query 2)— spec 假設 ≥ 2.13
3. **governance.audit_log 已 land**(per §9.1 Query 3)— spec 假設已 land
4. **legacy stub conflict**(per §9.1 Query 4)— spec 假設 greenfield

### 14.2 已知 caveat

1. **`amplification_loop_24h_count` writer-side query 成本**:每筆 INSERT 前查 24h 同 event_taxonomy CRITICAL/HALT count;在 60-300 row/day 規模下成本低(對比 V106 716k row/day 同 column 設計);Sprint 3 IMPL 期評估
2. **`evidence_json` JSONB 不索引**:debug-only 欄位;若 future analytics 需要 query JSONB(如 cap_suppressed 查詢),Sprint 3+ 加 GIN index
3. **partial index `WHERE severity IN (...)` 在 schema migration 時的成本**:CONCURRENTLY 建在 hypertable chunks 上是逐 chunk 建;首次 apply 在 0-row 表上 ms 級
4. **per-strategy `strategy_id` 不 enum**:5 既有策略 + Sprint 2+ 新策略名動態擴增;CHECK enum 易過時(對比 V106 同設計);特定 anomaly_type(如 ws_disconnect 全 strategy 共享)NULL allowed
5. **`metric_threshold` config 與 historical row 分離**:writer 寫入時鎖當下 threshold;config 後續變動(per ADR-0009 ArcSwap)不溯及既往;符合 audit principle
6. **`m1_lal_demote_ref` 對齊 ADR-0034 方向**:per 啟動 prompt §「⚠️ 注意」LAL Tier ref 對齊 ADR-0034 數字越大越嚴;ref 指向 demote 後 row 而非 promote;V112 spec v0 placeholder 若反向錯誤須 PA 仲裁
7. **`engine_mode='replay'`** vs V106 4 值(不含 replay):是設計決策(per §2.3);application 層 query 若需 cross-V106/V109 join 必處理 replay 在 V109 存在但 V106 不存在的情況

### 14.3 Sprint 3 writer 路徑未在本 spec 範圍

V109 apply 後立即 0 row(Foundation stage per MIT pipeline maturity);Sprint 3 statistical detector IMPL + writer 後升 Skeleton;Sprint 8 alerting 升 Shadow;Y2+ active gate 升 Production。

### 14.4 與 M8 design spec §12 Open Questions 對應

本 spec 不重複 M8 design spec §12 4 個 Open Questions(Q1 9 子類確認 / Q2 amplification 24h window / Q3 ML autoencoder leakage / Q4 paper engine_mode 寫入);所有 OQ 由 PM + PA cross-review Sprint 1A-γ V109 land 前 confirm。

---

## §15 後續行動(給 PM 派發)

| Action | Owner | Track | Priority |
|---|---|---|---|
| Sign-off 本 V109 spec | PM | Sprint 1A-γ schema prereq closure | P0 |
| PA C9 跑 §9.1 4 條 ssh PG query + 補 4 處 placeholder | PA | Sprint 1A-γ pre-dispatch | P0 |
| Reconcile cross-V### dependency(V106 / V112 / V113 / V107 / V108 對 V109 cross-ref query 對齊)| PA | Sprint 1A-γ pre-dispatch | P0 |
| Reconcile M8 design spec §12 4 Open Questions(per §14.4)| PM + PA | Sprint 1A-γ pre-dispatch | P0 |
| IMPL kickoff:派 E1 寫 V109.sql + Linux PG dry-run × 2 + Round 3 forbidden algorithm test + E2/E4 + restart_all 部署 | PM | Sprint 1A-γ IMPL | P1 |
| Sprint 3 detector + writer 上線:`anomaly_detector` writer + healthcheck `check_anomaly_writer()` + cross-module hand-shake protocol | E1 (Sprint 3) | Sprint 3 | P2 |
| ADR-0036 Decision 1 dispatch grep gate 加入 PA + MIT + E2 dispatch SOP | PA | Sprint 1A-γ pre-dispatch | P1 |

### 15.1 Sprint 1A-γ schema prereq closure 標誌

本 spec PM sign-off + PA C9 dry-run 補資料 land + V106 / V112 / V113 cross-ref reconciliation 完成 + ADR-0036 Proposed → Accepted + M8 design spec land → Sprint 1A-γ V109 schema prereq 解除 → IMPL kickoff 派 E1。

---

## §16 關鍵文件指針

- 本 V109 spec:本檔
- M8 design spec(sister spec same-day land):`srv/docs/execution_plan/2026-05-21--m8_anomaly_detection_design_spec.md`
- v5.8 主檔 §2 M8:`srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md` lines 279-318
- ADR-0036(Decision 1 forbidden algorithm + Decision 2-4 替代算法):`srv/docs/adr/0036-m8-anomaly-detection-and-m10-tier-d-model-blacklist.md`
- PA dispatch consolidation §1 CR-5 + §6 cross-V### dep graph:`srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md`
- E5 hypertable audit:`srv/docs/CCAgentWorkSpace/E5/workspace/reports/2026-05-21--v58_hypertable_audit.md`
- V106 spec(姊妹範式 + 5 audit field EXTEND):`srv/docs/execution_plan/2026-05-21--v106_m3_health_observations_schema_spec.md`
- V112 spec(M1 LAL cross-ref):`srv/docs/execution_plan/2026-05-21--v112_m1_decision_lease_lal_tiers_schema_spec.md`
- V113 spec(M7 cross-ref;source 5 persistent_anomaly_14d):`srv/docs/execution_plan/2026-05-21--v113_m7_decay_signals_schema_spec.md`
- V107 spec(M11 cross-ref):`srv/docs/execution_plan/2026-05-21--v107_m11_replay_divergence_log_schema_spec.md`
- V108 spec(M9 cross-ref):`srv/docs/execution_plan/2026-05-21--v108_m9_ab_testing_framework_schema_spec.md`
- V103 spec(範式 + 5 audit field EXTEND):`srv/docs/execution_plan/2026-05-21--v103_v104_earn_hypotheses_schema_spec.md`
- V103/V104 Linux PG dry-run protocol(範式):`srv/docs/execution_plan/2026-05-21--v103_v104_linux_pg_dry_run.md`
- V094 spec(Guard A/B/C + 範式):`srv/docs/execution_plan/2026-05-15--v094_close_maker_first_audit_schema_spec.md`
- V083 mirror(ALTER + NOT VALID CHECK 範式):`srv/sql/migrations/V083__fills_entry_context_id_close_check.sql`
- schema_guard_template:`srv/sql/migrations/templates/schema_guard_template.sql`
- repair binary:`srv/rust/openclaw_engine/src/bin/repair_migration_checksum.rs`
- V055 5-round loop + sqlx hash drift incident lessons:`memory/feedback_v_migration_pg_dry_run.md` + `memory/project_2026_05_02_p0_sqlx_hash_drift.md`
- CLAUDE.md §Data, Migrations, And Validation:`srv/CLAUDE.md`
- ADR-0034 (M1 LAL;m1_lal_demote_ref 方向對齊):`srv/docs/adr/0034-decision-lease-layered-approval-lal.md`
- M3 spec(M3 ↔ M8 amplification cap):`srv/docs/execution_plan/2026-05-21--m3_health_monitoring_design_spec.md`

---

## §17 審計記錄

| Source agent | Role | Audit pattern coverage |
|---|---|---|
| MIT(本文起草)| 起草者 | V058 Risk M8 V109 placeholder closure 路徑 / pipeline maturity 5 階段 / Guard A/C + ADR-0036 forbidden algorithm reverse pattern / Linux PG dry-run mandate / H-11 amplification cap design / 22 column rationale |
| PA dispatch consolidation 5.21(範式參考)| spec 設計 + cross-V### dependency | V106 / V107 / V109 / V112 / V113 / V108 cross-ref graph / Sprint 1A-γ dispatch sequence |
| V106 spec(2026-05-21 sister,範式參考)| 結構 + Guard 範式 | 14 section structure / Guard A/B/C template / Linux PG dry-run × 2 round protocol / sqlx checksum repair SOP / hypertable 7d chunk 範式 |
| V103/V104 spec(2026-05-21,範式參考)| audit field 範式 | 5 audit field per V103 EXTEND |
| E5 5.21 hypertable audit | hypertable 規格 | 7d chunk + 30d compression(對比 V106 7d)+ 180d retention(對比 V106 90d)合理性 |
| db-schema-design-financial-time-series skill | DB schema audit | hypertable 必用 / hot-path index 選用 / engine_mode CHECK 5 值含 replay / Guard A/B/C 規範 / partial index 設計 / BIGINT 弱關聯 vs FK 取捨 |
| ml-pipeline-maturity-audit skill | Pipeline stage 評級 | V109 apply 後立即 0 row 屬 Foundation stage;Sprint 3 detector 接線後升 Skeleton;Sprint 8 alerting 升 Shadow;Y2+ active gate 升 Production |
| ADR-0036(M8 + M10 Tier D)| Decision 1 黑名單 + Decision 2-4 替代算法 | detection_method ENUM 4 值對齊 + Guard A/C 雙重 forbidden algorithm 反向防護;atr_vol_state + funding_state 3+3 ENUM 對齊 9-cell 矩陣 axis |
| ADR-0034(M1 LAL)| m1_lal_demote_ref 方向對齊 | per 啟動 prompt §「⚠️ 注意」LAL Tier ref 對齊 ADR-0034 數字越大越嚴;ref 指向 demote 後 row 而非 promote |
| M8 design spec(本 spec sister)| event taxonomy + severity matrix + amplification cap + cross-module integration | 9 event_taxonomy + 4 severity + amplification cap H-11 + M3/M7/M9/M1 LAL 4 integration contract |

### 17.1 待 PA dispatch 前補充

- [ ] PA C9 dry-run 4 條 ssh query 結果(§9.1)
- [ ] V096 + V098 + TimescaleDB extension 已 land 確認
- [ ] legacy `learning.anomaly_events` stub 不存在確認
- [ ] M8 design spec §12 4 Open Questions reconciliation
- [ ] ADR-0036 Proposed → Accepted closure
- [ ] V112 (M1 LAL) m1_lal_demote_ref 方向確認(ADR-0034 數字越大越嚴 vs V112 spec v0 placeholder)

---

**END V109 spec full DDL v0**
