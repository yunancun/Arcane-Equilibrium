---
spec: V111 — M10 Discovery Tier Config + Activations Schema(governance schema + hypertable)
date: 2026-05-21
author: PA(full DDL spec;lifts placeholder;replaces SPEC-PLACEHOLDER v0)
phase: v5.8 Sprint 1A-γ schema prerequisite CRITICAL deliverable
status: SPEC-FULL-V0(PA 起草;待 MIT C9 Linux PG dry-run 實測補資料 + Sprint 1A-γ reviewer 對齊後 SPEC-FINAL)
sprint: Sprint 1A-γ(DESIGN phase;IMPL 後續 sprint)
size estimate: 180-240 LOC SQL(2 tables + 1 hypertable + 3 indexes + 5 INSERT seed rows + Guard A/B/C + retention 180d compress 30d)+ 70-110 hr E1 IMPL(含 Linux PG dry-run x 2 round + healthcheck wiring deferred to Sprint 1B)
depend on:
  - V098(governance.audit_log;assigned_by audit cross-ref;非 FK)
  - V091(P0 portfolio_var.usdt_var_15m;application-layer cross-ref for capital_observed_usdt)
depended by:
  - V112(M1 LAL tiers;`approval_lal_ref` placeholder FK ← `lease_lal_assignments.id`;V112 land 後 ALTER ADD CONSTRAINT)
  - V106(M3 health observations;HEALTH_DEGRADED 60min sustained → M10 demote 一階,application-layer cross-ref)
  - V107(M11 replay;tier transition replay reproducibility check;engine_mode='replay')
parent specs:
  - srv/docs/execution_plan/2026-05-21--m10_discovery_tier_design_spec.md(M10 DESIGN spec;500+ line 姊妹檔)
  - srv/docs/adr/0036-m8-anomaly-detection-and-m10-tier-d-model-blacklist.md(Tier D 黑名單 + 9 cell matrix source of truth)
  - srv/docs/adr/0034-decision-lease-layered-approval-lal.md(LAL 0-4 authoritative)
  - srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md §2 M10 Discovery Tier(line 364-389)
  - srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md §1 CR-5 + §6 cross-V###
mirror precedent:
  - srv/docs/execution_plan/2026-05-21--v112_m1_decision_lease_lal_tiers_schema_spec.md(V112 full DDL 範式;5 audit field + Guard A/B/C + Linux PG dry-run protocol)
  - srv/docs/execution_plan/2026-05-21--v103_v104_earn_hypotheses_schema_spec.md(14 section structure)
  - srv/docs/execution_plan/2026-05-21--v106_m3_health_observations_schema_spec.md(hypertable + 30d compress + 180d retention 範式)
  - srv/sql/migrations/V094__fills_close_maker_audit.sql(Guard A/B/C + NOT VALID CHECK + partial index 範式)
  - srv/sql/migrations/templates/schema_guard_template.sql(Guard A/B/C template)
scope: design / spec only — 不寫 V111.sql 實檔,不在 Mac 跑 SQL,不改 Rust/Python writer,不執行 PG,不擴張到 V107/V112 schema 細節(placeholder FK 標)
---
> ⚠️ 归档历史文档 — 非当前权威。active 状态见 repo 根 `TODO.md`；本文件仅供历史/审计参考。（2026-07-18 审计批量补入）


# V111 M10 Discovery Tier Config + Activations Schema Migration Spec(FULL DDL)

## §0 TL;DR

- **V111 新增 2 個 table on `governance` schema**:`governance.discovery_tier_config`(per-tier discovery 規則 config / 5 row seed Tier A-E)+ `governance.discovery_tier_activations`(tier transition activation ledger / hypertable / append-only audit)。
- **Tier A-E 5 級 ladder**(per M10 DESIGN spec §2.1 + v5.8 §2 M10):
  - Tier A = $500 baseline / 5 既有策略 / Y1 default
  - Tier B = $10k / +parameter sweep variants / Y2
  - Tier C = $30k / +cointegration pairs / Y2
  - Tier D = $50k / +9 cell regime adaptive / Y3+(per ADR-0036 ATR-vol+funding 唯一 allowlist)
  - Tier E = $100k / +portfolio overlay / Y3+
- **Tier D 黑名單 hardening per ADR-0036**:`regime_detection_method` CHECK 強制 `IN ('atr_vol_funding','pelt_reserved','none')` — **HMM / Markov-switching / GARCH 全 hard reject**;違反 INSERT RAISE。
- **discovery_tier_activations 為 hypertable**(per V106 範式):on `activated_at` / 7d chunk / 30d compress / 180d retention;append-only ledger;5-200 row/yr in Y1-Y3。
- **engine_mode CHECK 5 值齊全**(paper / demo / live_demo / live / replay);per CLAUDE.md §Data + MIT memory baseline;ML training filter 必含 `IN ('live','live_demo')`;`replay` 為 M11 replay engine 寫入時 tag。
- **5 audit field** per V103 EXTEND / V112 範式:`created_by` / `created_at` / `updated_by` / `updated_at` / `source_version`。
- **Hot-path indexes 3 個**:activated_at DESC(時序)/ (tier_to, activated_at DESC) / (approval_lal_ref) partial。
- **`approval_lal_ref` placeholder FK**(待 V112 land 後 ALTER ADD CONSTRAINT)— V112 schema 由 PA 同 Sprint 1A-β 派工待 land;當前 V111 不寫 FK CONSTRAINT。
- **Linux PG empirical dry-run mandatory**(per CLAUDE.md §Data, Migrations, And Validation + V055 5-round loop precedent)。

---

## §1 Context + 為什麼

### 1.1 V111 placeholder v0 schema 字段集偏離修正(CRITICAL)

V111 placeholder v0(本檔前一版 frontmatter)採:
- `learning.discovery_tier_config`(learning schema;PK `tier_config_id BIGSERIAL`)
- `learning.capital_triggers`(learning schema;PK `trigger_id BIGSERIAL`)
- 12 + 11 column 字段集

**本 spec full DDL 採 operator prompt 對齊路徑**:
- `governance.discovery_tier_config`(governance schema;PK `tier_level TEXT`)
- `governance.discovery_tier_activations`(governance schema;PK `id BIGSERIAL`;hypertable on `activated_at`)
- 重新對齊 V112 LAL tiers 同 schema 範式

**修正理由**:
1. M10 tier change 是 **governance event**(approval + audit + clawback governance 行為),非 ML learning observation;對齊 §二 原則 2「讀寫分離;research, GUI, and learning are mostly read-only」
2. 對齊 V112(`governance.lease_lal_tiers` + `governance.lease_lal_assignments`)兄弟 schema patterns
3. operator prompt 明示「`governance.discovery_tier_config` PK `tier_level TEXT`」與「`governance.discovery_tier_activations` hypertable」採此路徑
4. placeholder v0 之 learning schema 路徑廢棄;本 spec full DDL 為單一真實來源

### 1.2 v5.8 §2 M10 module + ADR-0036 driver

per M10 DESIGN spec §1.1 + v5.8 §2 M10:
- 5-tier ladder(A 最寬 → E 最嚴)+ capital threshold trigger
- Tier D regime detection per ADR-0036(ATR-vol + funding 雙 axis 9 cell;HMM/GARCH 黑名單)
- per-tier strategy enable list 必反映 archetype expansion(A→B 加 parameter sweep / B→C 加 pairs / D 加 regime cell adaptive)

### 1.3 為什麼 schema 用 `governance` schema(非 `learning`)

per ADR-0034 + M1 LAL design spec §3 state machine + V112 §1.3:
- Tier 升降是 governance object(approval policy enforcement + LAL gate),非 ML observation
- 既有 `governance.audit_log` / `governance.lease_lal_tiers` / `governance.lease_lal_assignments` 同 schema
- 避 schema 混淆(learning schema 主要為 ML feature / training / shadow):per CLAUDE.md §二 原則 2

### 1.4 Cross-V### 影響

| 下游 | M10 觸發路徑 | 是否 FK |
|---|---|---|
| **V112(M1 LAL tiers)** | tier transition 必 emit lease 經 `lal_gate` → 寫 `lease_lal_assignments`(tier=2/3/4 對應 M10 transition LAL level);M10 `discovery_tier_activations.approval_lal_ref` cross-ref V112 lease_lal_assignments.id | **placeholder FK**(V112 land 後 ALTER ADD CONSTRAINT)|
| **V106(M3 health)** | M3 HEALTH_DEGRADED 60min sustained → M10 demote 一階 | 否(cross-ref query) |
| **V091(P0 portfolio_var)** | `capital_observed_usdt` 從 `portfolio_var.usdt_var_15m` 7d MA application-layer compute | 否(application-layer cross-ref)|
| **V107(M11 replay)** | M11 replay 重放 tier transition 驗 reproducibility | 否(cross-ref query;engine_mode='replay')|
| **V109(M8 anomaly)** | M8 不直接 emit tier transition;經 M3 health 中介 | 否 |

### 1.5 不在本 spec 範圍

- ❌ V111.sql 實檔寫作(E1 IMPL 工作)
- ❌ Mac 跑 V111 SQL(必 Linux PG empirical)
- ❌ Rust lal_gate / discovery_tier_gate code(E1 IMPL 工作 Sprint 4+)
- ❌ Python tier UI(`control_api_v1` endpoint + `console_assets` panel;Sprint 4-8 IMPL)
- ❌ healthcheck wiring(Sprint 1B 加 `check_discovery_tier_writer()`)
- ❌ Sustained AUM monitor(7d MA + 30d sustained)Rust 模組(Sprint 4+ IMPL)
- ❌ Tier D 9 cell allocator IMPL(Y3+ IMPL per ADR-0036 Decision 3.1)
- ❌ V091/V106/V107/V112 schema 設計細節(各自 spec 寫)
- ❌ M5 / M8 / M9 schema(各自 V### 自寫)

---

## §2 Schema Design

### 2.1 Table 1: `governance.discovery_tier_config`(config)

#### 2.1.1 表定義

```sql
CREATE TABLE IF NOT EXISTS governance.discovery_tier_config (
    tier_level                  TEXT PRIMARY KEY
                                CHECK (tier_level IN ('A','B','C','D','E')),
    capital_threshold_min_usdt  NUMERIC(18,2) NOT NULL
                                CHECK (capital_threshold_min_usdt > 0),
    capital_threshold_max_usdt  NUMERIC(18,2)
                                CHECK (capital_threshold_max_usdt IS NULL OR
                                       capital_threshold_max_usdt > capital_threshold_min_usdt),
    enable_strategy_list        TEXT[] NOT NULL
                                CHECK (array_length(enable_strategy_list, 1) >= 1),
    disable_strategy_list       TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    regime_detection_method     TEXT NOT NULL
                                CHECK (regime_detection_method IN (
                                    'atr_vol_funding',
                                    'pelt_reserved',
                                    'none'
                                )),
    activation_year_min         INT NOT NULL
                                CHECK (activation_year_min BETWEEN 1 AND 3),
    sustained_window_days       INT NOT NULL DEFAULT 30
                                CHECK (sustained_window_days >= 7),
    aum_smoothing_days          INT NOT NULL DEFAULT 7
                                CHECK (aum_smoothing_days >= 1),
    description                 TEXT,
    created_by                  TEXT NOT NULL DEFAULT 'system_seed',
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by                  TEXT,
    updated_at                  TIMESTAMPTZ,
    source_version              TEXT NOT NULL DEFAULT 'V111'
);
```

#### 2.1.2 Column 設計理由

| Column | Type | NULL | 設計理由 |
|---|---|---|---|
| `tier_level` | TEXT PRIMARY KEY + CHECK 5 值 | NOT NULL | A/B/C/D/E 5 級(per M10 DESIGN §2.1);PK 唯一鍵;CHECK 防越界 |
| `capital_threshold_min_usdt` | NUMERIC(18,2) | NOT NULL | sustained AUM 入門條件(per M10 DESIGN §3.1);A=$500 / B=$10k / C=$30k / D=$50k / E=$100k;NUMERIC(18,2) cents precision 對齊 P&L 表 |
| `capital_threshold_max_usdt` | NUMERIC(18,2) | NULLABLE | 上限(tier 跨越下一級時 tier_to upgrade);Tier E NULL = open-ended;CHECK 強制 max > min |
| `enable_strategy_list` | TEXT[] | NOT NULL + CHECK ≥1 | 該 tier 容許 strategy_name 列表(per M10 DESIGN §7.1);array of strategy_name 字串;A=5 既有 / B/C/D/E 累積 expand |
| `disable_strategy_list` | TEXT[] DEFAULT [] | NOT NULL | 該 tier 顯式禁用 strategy_name(罕用;主要 enable_strategy_list 已 cover)|
| `regime_detection_method` | TEXT + CHECK 3 值 | NOT NULL | **Tier D hardening per ADR-0036** — allowlist `'atr_vol_funding'` 主路徑 / `'pelt_reserved'` Y3+ ADR-debt / `'none'` 非 Tier D;HMM/GARCH/Markov-switching 全 reject |
| `activation_year_min` | INT + CHECK 1-3 | NOT NULL | 最早 activation year;A=1 / B/C=2 / D/E=3 |
| `sustained_window_days` | INT DEFAULT 30 | NOT NULL | per v5.8 §2 M10 sustained mandate;30d default;CHECK ≥7 |
| `aum_smoothing_days` | INT DEFAULT 7 | NOT NULL | 7d moving average;CHECK ≥1 |
| `description` | TEXT | NULLABLE | 業務語意描述(audit trail 用)|
| 5 audit field | per V103 EXTEND / V112 範式 | mixed | created_by / created_at / updated_by / updated_at / source_version |

#### 2.1.3 5 row seed INSERT

```sql
INSERT INTO governance.discovery_tier_config
    (tier_level, capital_threshold_min_usdt, capital_threshold_max_usdt,
     enable_strategy_list, disable_strategy_list, regime_detection_method,
     activation_year_min, sustained_window_days, aum_smoothing_days,
     description, created_by, source_version)
VALUES
    -- Tier A: Y1 default; 5 既有策略 baseline
    ('A',
     500.00, 10000.00,
     ARRAY['grid','ma','bb_breakout','bb_reversion','funding_arb']::TEXT[],
     ARRAY[]::TEXT[],
     'none',
     1, 30, 7,
     'Tier A: Y1 default; 5 既有策略 baseline; capital $500-$10k; per M10 DESIGN §2.1 + v5.8 §2 M10',
     'system_seed', 'V111'),

    -- Tier B: Y2; A + parameter sweep variants
    ('B',
     10000.00, 30000.00,
     ARRAY['grid','ma','bb_breakout','bb_reversion','funding_arb',
           'grid_fine','grid_coarse','ma_fast','ma_slow','bb_tight','bb_wide']::TEXT[],
     ARRAY[]::TEXT[],
     'none',
     2, 30, 7,
     'Tier B: Y2 activation; A baseline + parameter sweep variants (grid-fine/coarse, ma-fast/slow, bb-tight/wide); capital $10k-$30k; per M10 DESIGN §7.1',
     'system_seed', 'V111'),

    -- Tier C: Y2; B + 1 cointegration / pairs strategy
    ('C',
     30000.00, 50000.00,
     ARRAY['grid','ma','bb_breakout','bb_reversion','funding_arb',
           'grid_fine','grid_coarse','ma_fast','ma_slow','bb_tight','bb_wide',
           'cointegration_pairs']::TEXT[],
     ARRAY[]::TEXT[],
     'none',
     2, 30, 7,
     'Tier C: Y2 activation; B + 1 cointegration/pairs trading strategy (ASDS Sprint 6 candidate); capital $30k-$50k; per M10 DESIGN §7.1',
     'system_seed', 'V111'),

    -- Tier D: Y3+; C + 9 cell regime adaptive (per ADR-0036)
    ('D',
     50000.00, 100000.00,
     ARRAY['grid','ma','bb_breakout','bb_reversion','funding_arb',
           'grid_fine','grid_coarse','ma_fast','ma_slow','bb_tight','bb_wide',
           'cointegration_pairs','regime_adaptive_9cell']::TEXT[],
     ARRAY[]::TEXT[],
     'atr_vol_funding',
     3, 30, 7,
     'Tier D: Y3+ activation; C + 9 cell regime adaptive per ADR-0036 (ATR-vol+funding dual axis; HMM/GARCH/Markov-switching hard reject); capital $50k-$100k; cell stability ≥30 sample/cell required',
     'system_seed', 'V111'),

    -- Tier E: Y3+; D + multi-strategy portfolio overlay
    ('E',
     100000.00, NULL,  -- open-ended max
     ARRAY['grid','ma','bb_breakout','bb_reversion','funding_arb',
           'grid_fine','grid_coarse','ma_fast','ma_slow','bb_tight','bb_wide',
           'cointegration_pairs','regime_adaptive_9cell',
           'portfolio_overlay_meanvar']::TEXT[],
     ARRAY[]::TEXT[],
     'atr_vol_funding',
     3, 30, 7,
     'Tier E: Y3+ activation; D + multi-strategy portfolio overlay (mean-var optimization + cross-asset rebalance); capital $100k+; LAL 3 per rebalance epoch + LAL 4 for cross-venue (per ADR-0034)',
     'system_seed', 'V111')
ON CONFLICT (tier_level) DO NOTHING;
```

**理由**:
- Tier A: 5 既有策略;`'none'` regime detection;Y1 activation;capital 範圍 $500-$10k
- Tier B-C: 累積 strategy(sweep variants / pairs);`'none'` regime detection(尚未 active);Y2 activation
- Tier D-E: 累積 +regime_adaptive_9cell / +portfolio_overlay;`'atr_vol_funding'` regime detection per ADR-0036;Y3+ activation
- Tier E max NULL = open-ended

`ON CONFLICT (tier_level) DO NOTHING`:idempotent;重跑 V111 不 double insert。

#### 2.1.4 row 量級

- 5 row 固定 config;不擴張
- regular table(非 hypertable);無 retention 需求

### 2.2 Table 2: `governance.discovery_tier_activations`(activation ledger)

#### 2.2.1 表定義

```sql
CREATE TABLE IF NOT EXISTS governance.discovery_tier_activations (
    id                              BIGSERIAL,
    tier_from                       TEXT
                                    CHECK (tier_from IS NULL OR tier_from IN ('A','B','C','D','E')),
    tier_to                         TEXT NOT NULL
                                    REFERENCES governance.discovery_tier_config(tier_level),
    capital_observed_usdt           NUMERIC(18,2) NOT NULL
                                    CHECK (capital_observed_usdt >= 0),
    trigger_threshold_id            INT NOT NULL
                                    CHECK (trigger_threshold_id BETWEEN 1 AND 7),
    sustained_days_observed         INT NOT NULL
                                    CHECK (sustained_days_observed >= 0),
    activated_by                    TEXT NOT NULL,
    activated_at                    TIMESTAMPTZ NOT NULL DEFAULT now(),
    approval_lal_ref                BIGINT,
    tier_change_reason              TEXT NOT NULL
                                    CHECK (tier_change_reason IN (
                                        'capital_trigger',
                                        'operator_approval',
                                        'm3_health_degraded',
                                        'operator_override',
                                        'clawback',
                                        'initial_seed'
                                    )),
    engine_mode                     TEXT NOT NULL
                                    CHECK (engine_mode IN ('paper','demo','live_demo','live','replay')),
    evidence_json                   JSONB,
    created_by                      TEXT NOT NULL DEFAULT 'lal_gate',
    created_at                      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by                      TEXT,
    updated_at                      TIMESTAMPTZ,
    source_version                  TEXT NOT NULL DEFAULT 'V111',
    PRIMARY KEY (id, activated_at),
    CONSTRAINT chk_tier_transition_distinct CHECK (
        tier_from IS NULL OR tier_from != tier_to
    ),
    CONSTRAINT chk_engine_mode_capital CHECK (
        engine_mode IN ('live','live_demo','replay') OR
        tier_change_reason IN ('initial_seed','operator_override','clawback')
    )
);
```

#### 2.2.2 Column 設計理由

| Column | Type | NULL | 設計理由 |
|---|---|---|---|
| `id` | BIGSERIAL | NOT NULL | sequential audit ID(hypertable PK 必含 partition column `activated_at`,故 PK 為 (id, activated_at))|
| `tier_from` | TEXT FK → `discovery_tier_config` | NULLABLE | 升級時源 tier;initial activation 為 NULL;`chk_tier_transition_distinct` 強制 != tier_to |
| `tier_to` | TEXT NOT NULL FK | NOT NULL | 目標 tier;不 NULL |
| `capital_observed_usdt` | NUMERIC(18,2) | NOT NULL | 觸發時 7d moving AUM 真實值;CHECK >= 0 |
| `trigger_threshold_id` | INT + CHECK 1-7 | NOT NULL | matched §3.1 7 級之中哪個 step(1=$500 / 2=$2k / 3=$10k / 4=$30k / 5=$50k / 6=$100k / 7=$500k);per M10 DESIGN §3.1 7 級 capital threshold |
| `sustained_days_observed` | INT + CHECK ≥0 | NOT NULL | 觀察到 sustained 連續天數(必 ≥ tier_to 對應 `sustained_window_days` 才算合規)|
| `activated_by` | TEXT | NOT NULL | actor allowlist:`'lal_gate'` / `'operator'` / `'m3_health_degraded_demoter'` / `'system_seed'` / `'operator_override'`(application-layer enforce)|
| `activated_at` | TIMESTAMPTZ DEFAULT now() | NOT NULL | activation 時間;hypertable partition column |
| `approval_lal_ref` | BIGINT | NULLABLE | **placeholder FK** to V112 `lease_lal_assignments.id`(V112 land 後 ALTER ADD CONSTRAINT FK);M10 DESIGN §6.1 LAL 2/3/4 對應路徑;LAL 1 auto demote 時可 NULL |
| `tier_change_reason` | TEXT + CHECK 6 值 | NOT NULL | capital_trigger / operator_approval / m3_health_degraded / operator_override / clawback / initial_seed(per M10 DESIGN §5.3 demote vs clawback 區分)|
| `engine_mode` | TEXT + CHECK 5 值 | NOT NULL | paper / demo / live_demo / live / replay;`chk_engine_mode_capital` 強制 capital_trigger 必 live/live_demo/replay(防 demo/paper tier spike 攻擊 per M10 DESIGN §9.3)|
| `evidence_json` | JSONB | NULLABLE | 富 context(per M10 DESIGN §5.4):sustained_metric / regime_cell_snapshot(Tier D)/ demote_reason / lal_attestation_2fa(LAL 4)|
| 5 audit field | per V103 EXTEND / V112 範式 | mixed | created_by / created_at / updated_by / updated_at / source_version |

#### 2.2.3 2 個 CHECK constraint 理由

- `chk_tier_transition_distinct`:防 `tier_from = tier_to`(no-op transition 拒)
- `chk_engine_mode_capital`:防 demo/paper capital_trigger 升 tier(per M10 DESIGN §9.3 反向 attack);initial_seed / operator_override / clawback 例外允許

#### 2.2.4 row 量級估算

- Y1:Tier A 預設;~5-10 row/yr(initial_seed + 偶發 operator_override)
- Y2:Tier B/C 累積;~10-30 row/yr(capital_trigger + LAL 2 approval + M3 demote)
- Y3+:Tier D/E + portfolio overlay rebalance epoch;~50-200 row/yr
- M11 replay rows:per ADR-0038 nightly replay;假設 5% live activation 比例 replay:額外 ~10-20 row/yr
- 合計 Y1-Y3 ~75-260 row total;hypertable 7d chunk 對齊 V106 範式 future growth path

### 2.3 Hypertable 配置(per V106 範式)

#### 2.3.1 為什麼 hypertable(非 regular table)

per V106 + db-schema-design-financial-time-series skill + M10 DESIGN §5.2:
- tier transition 是 timeseries event(activated_at DESC dominant query)
- V112 lease_lal_assignments 用 regular table 因 audit field heavy + 預期 ~141 row/day high frequency
- V111 discovery_tier_activations 用 hypertable 因 timeseries dominant + 未來 D/E activation frequency 可能 high + 7d chunk + 30d compress 對齊 V106 範式
- compress 30d + retention 180d 對齊 V106 範式;older data 可直接 archive

#### 2.3.2 Hypertable + compress + retention DDL

```sql
-- Step: 創建 hypertable(必在 CREATE TABLE 後)
SELECT create_hypertable(
    'governance.discovery_tier_activations',
    'activated_at',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists => TRUE
);

-- Step: 啟用 compression(30d 後 compress)
ALTER TABLE governance.discovery_tier_activations
    SET (
        timescaledb.compress,
        timescaledb.compress_orderby = 'activated_at DESC',
        timescaledb.compress_segmentby = 'tier_to'
    );

-- Step: 添加 compression policy
SELECT add_compression_policy(
    'governance.discovery_tier_activations',
    INTERVAL '30 days',
    if_not_exists => TRUE
);

-- Step: 添加 retention policy(180d 後 drop)
SELECT add_retention_policy(
    'governance.discovery_tier_activations',
    INTERVAL '180 days',
    if_not_exists => TRUE
);
```

#### 2.3.3 為什麼 7d chunk(非 1d / 30d)

per V106 範式 + tier transition cadence:
- tier transition 是 low-frequency event(non-OHLC tick scale)
- 1d chunk → 太多 chunk(365 chunk/yr)overhead 高
- 30d chunk → 太少 chunk(12 chunk/yr)compress benefits 低
- **7d chunk**(採用)→ ~52 chunk/yr;chunk size 適中;對齊 V106 health observations 範式

#### 2.3.4 為什麼 compress 30d / retention 180d

per V106 範式:
- 30d compress: 近 1 month tier transition 需 hot read access(operator audit / debug);30d 後 compress 省 ~80% storage
- 180d retention: 半年 audit trail 對齊 governance audit 需求;old data drop 對齊 §二 #8 audit trail acceptable scope;若未來 governance requires 1y+ retention,ALTER POLICY 即可

---

## §3 Index Strategy

### 3.1 Hot-path query → index map

| Query pattern | 命中 index | 範例 SQL |
|---|---|---|
| recent activations timeline | `idx_tier_activations_activated_at`(隱式 hypertable 預設) | `SELECT * FROM governance.discovery_tier_activations ORDER BY activated_at DESC LIMIT 100` |
| per-tier audit history | `idx_tier_activations_tier_to_at` | `SELECT * FROM governance.discovery_tier_activations WHERE tier_to=$1 ORDER BY activated_at DESC` |
| LAL approval cross-ref | `idx_tier_activations_lal_ref` partial | `SELECT * FROM governance.discovery_tier_activations WHERE approval_lal_ref IS NOT NULL ORDER BY activated_at DESC` |

### 3.2 Index DDL

```sql
-- Note: hypertable 預設在 (activated_at DESC) 上有隱式 chunk index;
-- 但 (tier_to, activated_at DESC) 是 hot-path 必需

-- Per-tier audit history
CREATE INDEX IF NOT EXISTS idx_tier_activations_tier_to_at
    ON governance.discovery_tier_activations (tier_to, activated_at DESC);

-- LAL approval cross-ref partial
CREATE INDEX IF NOT EXISTS idx_tier_activations_lal_ref
    ON governance.discovery_tier_activations (approval_lal_ref, activated_at DESC)
    WHERE approval_lal_ref IS NOT NULL;

-- tier_change_reason audit query(demote vs clawback vs trigger)
CREATE INDEX IF NOT EXISTS idx_tier_activations_change_reason
    ON governance.discovery_tier_activations (tier_change_reason, activated_at DESC);
```

### 3.3 為什麼不用 CONCURRENTLY

- hypertable index 建立時不能直接用 CONCURRENTLY(per TimescaleDB best practice;會在 chunk 上自動 propagate);`IF NOT EXISTS` 已 idempotent
- V111 land 時 activations table 為空 → 不會 lock production query

### 3.4 為什麼不加 `(tier_from, tier_to)` composite index

cardinality 低(5×5=25 combination,實際只 ~10 valid transition);PG 用 bitmap scan 在 partition 內已足夠;不需顯式 index。

---

## §4 Guard A / B / C(per CLAUDE.md §Data, Migrations, And Validation + V094/V112 mirror)

### 4.1 Guard A — table existence + 既有 schema 對齊驗證

```sql
-- ============================================================
-- Guard A: V111 預檢 — 若 governance.discovery_tier_config /
-- discovery_tier_activations 已存在,必驗 V111 spec column 全俱在;
-- 缺即 RAISE。同時驗 V098 + TimescaleDB extension prereq。
-- ============================================================
DO $$
DECLARE v_missing TEXT[];
BEGIN
    -- governance schema 存在驗
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.schemata WHERE schema_name='governance'
    ) THEN
        RAISE EXCEPTION
            'V111 Guard A FAIL: governance schema missing. '
            'Apply baseline schema migration before V111.';
    END IF;

    -- governance.audit_log 必須存在(M10 audit cross-ref;V098 prereq)
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='governance' AND table_name='audit_log'
    ) THEN
        RAISE EXCEPTION
            'V111 Guard A FAIL: governance.audit_log missing — '
            'V098 must apply before V111 (cross-ref audit). Verify _sqlx_migrations.';
    END IF;

    -- TimescaleDB extension 必須 land(hypertable prereq)
    IF NOT EXISTS (
        SELECT 1 FROM pg_extension WHERE extname='timescaledb'
    ) THEN
        RAISE EXCEPTION
            'V111 Guard A FAIL: timescaledb extension missing — '
            'Required for discovery_tier_activations hypertable. '
            'Apply CREATE EXTENSION IF NOT EXISTS timescaledb before V111.';
    END IF;

    -- governance.discovery_tier_config 已存在的情境
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='governance' AND table_name='discovery_tier_config'
    ) THEN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'tier_level', 'capital_threshold_min_usdt', 'capital_threshold_max_usdt',
            'enable_strategy_list', 'disable_strategy_list', 'regime_detection_method',
            'activation_year_min', 'sustained_window_days', 'aum_smoothing_days',
            'description', 'created_by', 'created_at',
            'updated_by', 'updated_at', 'source_version'
        ]) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema='governance' AND table_name='discovery_tier_config'
              AND column_name=c
        );
        IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
            RAISE EXCEPTION
                'V111 Guard A FAIL: governance.discovery_tier_config exists but missing columns: %. '
                'Possible legacy V111 placeholder v0 (learning schema) conflict — '
                'resolve schema reconciliation before applying V111.',
                v_missing;
        END IF;
    END IF;

    -- governance.discovery_tier_activations 已存在的情境
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='governance' AND table_name='discovery_tier_activations'
    ) THEN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'id', 'tier_from', 'tier_to', 'capital_observed_usdt',
            'trigger_threshold_id', 'sustained_days_observed', 'activated_by',
            'activated_at', 'approval_lal_ref', 'tier_change_reason',
            'engine_mode', 'evidence_json', 'created_by', 'created_at',
            'updated_by', 'updated_at', 'source_version'
        ]) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema='governance' AND table_name='discovery_tier_activations'
              AND column_name=c
        );
        IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
            RAISE EXCEPTION
                'V111 Guard A FAIL: governance.discovery_tier_activations exists but missing columns: %. '
                'Resolve schema drift before applying V111.',
                v_missing;
        END IF;
    END IF;

    -- 反向衝突檢查:legacy learning.discovery_tier_config / capital_triggers stub 不存在
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='learning'
          AND table_name IN ('discovery_tier_config','capital_triggers')
    ) THEN
        RAISE EXCEPTION
            'V111 Guard A FAIL: legacy V111 placeholder v0 stub '
            '(learning.discovery_tier_config or learning.capital_triggers) detected — '
            'spec full DDL v0 moves to governance schema. '
            'Resolve via DROP TABLE learning.discovery_tier_config / learning.capital_triggers '
            'and re-apply V111. See V111 spec §1.1 for migration rationale.';
    END IF;
END $$;
```

### 4.2 Guard B — 不適用

V111 不 ALTER 既有 column type;無 type-sensitive 檢查需求。本 spec 不設 Guard B 段。

### 4.3 Guard C — CHECK constraint + ENUM 值齊全 + hypertable + index 對齊驗證

```sql
-- ============================================================
-- Guard C: V111 預檢 — 重跑 V111 時 idempotent 檢查 CHECK constraint + 
-- 5 seed rows + hypertable + 3 index 對齊驗證
-- ============================================================
DO $$
DECLARE v_actual TEXT;
DECLARE v_seed_count INT;
BEGIN
    -- regime_detection_method CHECK 強制 3 allowlist(ADR-0036 hard reject HMM/GARCH/Markov)
    SELECT pg_get_constraintdef(oid) INTO v_actual
    FROM pg_constraint
    WHERE conrelid='governance.discovery_tier_config'::regclass
      AND conname LIKE '%regime_detection_method%check%';
    IF v_actual IS NOT NULL THEN
        IF position('atr_vol_funding' IN v_actual) = 0
           OR position('pelt_reserved' IN v_actual) = 0
           OR position('none' IN v_actual) = 0
        THEN
            RAISE EXCEPTION
                'V111 Guard C FAIL: discovery_tier_config regime_detection_method CHECK enum mismatch. '
                'Actual: %. Expected to contain atr_vol_funding/pelt_reserved/none (per ADR-0036).',
                v_actual;
        END IF;
        -- 強制 HMM/GARCH/Markov 不在 allowlist
        IF position('hmm' IN v_actual) > 0
           OR position('garch' IN v_actual) > 0
           OR position('markov_switching' IN v_actual) > 0
        THEN
            RAISE EXCEPTION
                'V111 Guard C FAIL: discovery_tier_config regime_detection_method CHECK contains forbidden value '
                '(hmm/garch/markov_switching). Per ADR-0036 these are permanently blacklisted. '
                'Actual: %.',
                v_actual;
        END IF;
    END IF;

    -- tier_level CHECK 5 值齊全
    SELECT pg_get_constraintdef(oid) INTO v_actual
    FROM pg_constraint
    WHERE conrelid='governance.discovery_tier_config'::regclass
      AND conname LIKE '%tier_level%check%';
    IF v_actual IS NOT NULL THEN
        IF position('A' IN v_actual) = 0
           OR position('B' IN v_actual) = 0
           OR position('C' IN v_actual) = 0
           OR position('D' IN v_actual) = 0
           OR position('E' IN v_actual) = 0
        THEN
            RAISE EXCEPTION
                'V111 Guard C FAIL: discovery_tier_config tier_level CHECK enum mismatch. '
                'Actual: %. Expected A/B/C/D/E.',
                v_actual;
        END IF;
    END IF;

    -- tier_change_reason CHECK 6 值齊全
    SELECT pg_get_constraintdef(oid) INTO v_actual
    FROM pg_constraint
    WHERE conrelid='governance.discovery_tier_activations'::regclass
      AND conname LIKE '%tier_change_reason%check%';
    IF v_actual IS NOT NULL THEN
        IF position('capital_trigger' IN v_actual) = 0
           OR position('operator_approval' IN v_actual) = 0
           OR position('m3_health_degraded' IN v_actual) = 0
           OR position('operator_override' IN v_actual) = 0
           OR position('clawback' IN v_actual) = 0
           OR position('initial_seed' IN v_actual) = 0
        THEN
            RAISE EXCEPTION
                'V111 Guard C FAIL: discovery_tier_activations tier_change_reason CHECK enum mismatch. '
                'Actual: %. Expected capital_trigger/operator_approval/m3_health_degraded/operator_override/clawback/initial_seed.',
                v_actual;
        END IF;
    END IF;

    -- engine_mode CHECK 5 值齊全(含 'replay')
    SELECT pg_get_constraintdef(oid) INTO v_actual
    FROM pg_constraint
    WHERE conrelid='governance.discovery_tier_activations'::regclass
      AND conname LIKE '%engine_mode%check%';
    IF v_actual IS NOT NULL THEN
        IF position('paper' IN v_actual) = 0
           OR position('demo' IN v_actual) = 0
           OR position('live_demo' IN v_actual) = 0
           OR position('live' IN v_actual) = 0
           OR position('replay' IN v_actual) = 0
        THEN
            RAISE EXCEPTION
                'V111 Guard C FAIL: discovery_tier_activations engine_mode CHECK enum mismatch. '
                'Actual: %. Expected paper/demo/live_demo/live/replay (replay for M11).',
                v_actual;
        END IF;
    END IF;

    -- 5 seed rows 完整(若 discovery_tier_config 已存在)
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='governance' AND table_name='discovery_tier_config'
    ) THEN
        SELECT count(*) INTO v_seed_count FROM governance.discovery_tier_config;
        IF v_seed_count > 0 AND v_seed_count != 5 THEN
            RAISE EXCEPTION
                'V111 Guard C FAIL: governance.discovery_tier_config seed row count mismatch. '
                'Actual: %. Expected: 5 rows (Tier A/B/C/D/E per M10 DESIGN §2.1).',
                v_seed_count;
        END IF;
    END IF;

    -- hypertable 配置驗(若 discovery_tier_activations 已存在 + hypertable 已建)
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='governance' AND table_name='discovery_tier_activations'
    ) AND NOT EXISTS (
        SELECT 1 FROM timescaledb_information.hypertables
        WHERE hypertable_schema='governance'
          AND hypertable_name='discovery_tier_activations'
    ) THEN
        RAISE NOTICE 'V111 Guard C NOTE: discovery_tier_activations not yet hypertable. '
                     'Will be configured by main migration body via create_hypertable.';
    END IF;
END $$;
```

### 4.4 Guard 設計理念(per V094 / V112 mirror)

| Guard | 觸發場景 | RAISE 條件 | NOT RAISE 條件(idempotent)|
|---|---|---|---|
| A | NEW table 已存在但 column 缺;governance.audit_log 缺;TimescaleDB extension 缺;legacy learning schema stub 存在 | RAISE | 全 column 俱在 / table 不存在(首次跑)/ extension 存在 / 無 legacy stub |
| C | CHECK constraint 缺 enum 值;CHECK 含 HMM/GARCH/Markov forbidden value;seed rows count 不對 | RAISE | constraint 不存在(首次跑)/ constraint 完整(重跑)|
| C hypertable | hypertable 首次跑不存在 | NOTICE(不 RAISE,migration body 會建)| hypertable 已存在重跑(skip)|

重跑 V111 第二次必不 RAISE(idempotency per CLAUDE.md §Data, Migrations, And Validation V055/V083/V084 incident precedent)。

---

## §5 Migration up + down SQL

### 5.1 Migration UP(完整 V111.sql 設計)

```sql
-- ============================================================
-- V111: governance.discovery_tier_config + governance.discovery_tier_activations
--       (hypertable on activated_at; 7d chunk; 30d compress; 180d retention)
-- M10 Discovery Tier — Capital-Triggered Strategy Discovery Tier Ladder
-- per M10 DESIGN spec §2-§9 + ADR-0036 Tier D 黑名單 (HMM/GARCH/Markov hard reject)
-- ============================================================

-- Step 1: Guard A (per §4.1)
-- [全文見 §4.1]

-- Step 2: Guard C 預檢 (per §4.3 重跑 idempotency)
-- [全文見 §4.3]

-- Step 3: CREATE TABLE governance.discovery_tier_config (config; 5 row seed)
CREATE TABLE IF NOT EXISTS governance.discovery_tier_config (
    tier_level                  TEXT PRIMARY KEY
                                CHECK (tier_level IN ('A','B','C','D','E')),
    capital_threshold_min_usdt  NUMERIC(18,2) NOT NULL
                                CHECK (capital_threshold_min_usdt > 0),
    capital_threshold_max_usdt  NUMERIC(18,2)
                                CHECK (capital_threshold_max_usdt IS NULL OR
                                       capital_threshold_max_usdt > capital_threshold_min_usdt),
    enable_strategy_list        TEXT[] NOT NULL
                                CHECK (array_length(enable_strategy_list, 1) >= 1),
    disable_strategy_list       TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    regime_detection_method     TEXT NOT NULL
                                CHECK (regime_detection_method IN (
                                    'atr_vol_funding',
                                    'pelt_reserved',
                                    'none'
                                )),
    activation_year_min         INT NOT NULL
                                CHECK (activation_year_min BETWEEN 1 AND 3),
    sustained_window_days       INT NOT NULL DEFAULT 30
                                CHECK (sustained_window_days >= 7),
    aum_smoothing_days          INT NOT NULL DEFAULT 7
                                CHECK (aum_smoothing_days >= 1),
    description                 TEXT,
    created_by                  TEXT NOT NULL DEFAULT 'system_seed',
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by                  TEXT,
    updated_at                  TIMESTAMPTZ,
    source_version              TEXT NOT NULL DEFAULT 'V111'
);

-- Step 4: Seed 5 tier rows (idempotent via ON CONFLICT)
INSERT INTO governance.discovery_tier_config
    (tier_level, capital_threshold_min_usdt, capital_threshold_max_usdt,
     enable_strategy_list, disable_strategy_list, regime_detection_method,
     activation_year_min, sustained_window_days, aum_smoothing_days,
     description, created_by, source_version)
VALUES
    ('A',
     500.00, 10000.00,
     ARRAY['grid','ma','bb_breakout','bb_reversion','funding_arb']::TEXT[],
     ARRAY[]::TEXT[],
     'none',
     1, 30, 7,
     'Tier A: Y1 default; 5 既有策略 baseline; capital $500-$10k; per M10 DESIGN §2.1 + v5.8 §2 M10',
     'system_seed', 'V111'),
    ('B',
     10000.00, 30000.00,
     ARRAY['grid','ma','bb_breakout','bb_reversion','funding_arb',
           'grid_fine','grid_coarse','ma_fast','ma_slow','bb_tight','bb_wide']::TEXT[],
     ARRAY[]::TEXT[],
     'none',
     2, 30, 7,
     'Tier B: Y2 activation; A baseline + parameter sweep variants; capital $10k-$30k',
     'system_seed', 'V111'),
    ('C',
     30000.00, 50000.00,
     ARRAY['grid','ma','bb_breakout','bb_reversion','funding_arb',
           'grid_fine','grid_coarse','ma_fast','ma_slow','bb_tight','bb_wide',
           'cointegration_pairs']::TEXT[],
     ARRAY[]::TEXT[],
     'none',
     2, 30, 7,
     'Tier C: Y2 activation; B + 1 cointegration/pairs strategy; capital $30k-$50k',
     'system_seed', 'V111'),
    ('D',
     50000.00, 100000.00,
     ARRAY['grid','ma','bb_breakout','bb_reversion','funding_arb',
           'grid_fine','grid_coarse','ma_fast','ma_slow','bb_tight','bb_wide',
           'cointegration_pairs','regime_adaptive_9cell']::TEXT[],
     ARRAY[]::TEXT[],
     'atr_vol_funding',
     3, 30, 7,
     'Tier D: Y3+ activation; C + 9 cell regime adaptive per ADR-0036 (ATR-vol+funding dual axis; HMM/GARCH/Markov hard reject); capital $50k-$100k; cell stability ≥30 sample/cell required',
     'system_seed', 'V111'),
    ('E',
     100000.00, NULL,
     ARRAY['grid','ma','bb_breakout','bb_reversion','funding_arb',
           'grid_fine','grid_coarse','ma_fast','ma_slow','bb_tight','bb_wide',
           'cointegration_pairs','regime_adaptive_9cell',
           'portfolio_overlay_meanvar']::TEXT[],
     ARRAY[]::TEXT[],
     'atr_vol_funding',
     3, 30, 7,
     'Tier E: Y3+ activation; D + multi-strategy portfolio overlay; capital $100k+; LAL 3/4 per rebalance epoch',
     'system_seed', 'V111')
ON CONFLICT (tier_level) DO NOTHING;

-- Step 5: CREATE TABLE governance.discovery_tier_activations (activation ledger)
CREATE TABLE IF NOT EXISTS governance.discovery_tier_activations (
    id                              BIGSERIAL,
    tier_from                       TEXT
                                    CHECK (tier_from IS NULL OR tier_from IN ('A','B','C','D','E')),
    tier_to                         TEXT NOT NULL
                                    REFERENCES governance.discovery_tier_config(tier_level),
    capital_observed_usdt           NUMERIC(18,2) NOT NULL
                                    CHECK (capital_observed_usdt >= 0),
    trigger_threshold_id            INT NOT NULL
                                    CHECK (trigger_threshold_id BETWEEN 1 AND 7),
    sustained_days_observed         INT NOT NULL
                                    CHECK (sustained_days_observed >= 0),
    activated_by                    TEXT NOT NULL,
    activated_at                    TIMESTAMPTZ NOT NULL DEFAULT now(),
    approval_lal_ref                BIGINT,
    tier_change_reason              TEXT NOT NULL
                                    CHECK (tier_change_reason IN (
                                        'capital_trigger',
                                        'operator_approval',
                                        'm3_health_degraded',
                                        'operator_override',
                                        'clawback',
                                        'initial_seed'
                                    )),
    engine_mode                     TEXT NOT NULL
                                    CHECK (engine_mode IN ('paper','demo','live_demo','live','replay')),
    evidence_json                   JSONB,
    created_by                      TEXT NOT NULL DEFAULT 'lal_gate',
    created_at                      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by                      TEXT,
    updated_at                      TIMESTAMPTZ,
    source_version                  TEXT NOT NULL DEFAULT 'V111',
    PRIMARY KEY (id, activated_at),
    CONSTRAINT chk_tier_transition_distinct CHECK (
        tier_from IS NULL OR tier_from != tier_to
    ),
    CONSTRAINT chk_engine_mode_capital CHECK (
        engine_mode IN ('live','live_demo','replay') OR
        tier_change_reason IN ('initial_seed','operator_override','clawback')
    )
);

-- Step 6: 創建 hypertable on activated_at (7d chunk)
SELECT create_hypertable(
    'governance.discovery_tier_activations',
    'activated_at',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists => TRUE
);

-- Step 7: 啟用 compression (30d 後 compress)
ALTER TABLE governance.discovery_tier_activations
    SET (
        timescaledb.compress,
        timescaledb.compress_orderby = 'activated_at DESC',
        timescaledb.compress_segmentby = 'tier_to'
    );

-- Step 8: 添加 compression policy (30d 後 compress)
SELECT add_compression_policy(
    'governance.discovery_tier_activations',
    INTERVAL '30 days',
    if_not_exists => TRUE
);

-- Step 9: 添加 retention policy (180d 後 drop)
SELECT add_retention_policy(
    'governance.discovery_tier_activations',
    INTERVAL '180 days',
    if_not_exists => TRUE
);

-- Step 10: Hot-path indexes (per §3.2)
CREATE INDEX IF NOT EXISTS idx_tier_activations_tier_to_at
    ON governance.discovery_tier_activations (tier_to, activated_at DESC);

CREATE INDEX IF NOT EXISTS idx_tier_activations_lal_ref
    ON governance.discovery_tier_activations (approval_lal_ref, activated_at DESC)
    WHERE approval_lal_ref IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_tier_activations_change_reason
    ON governance.discovery_tier_activations (tier_change_reason, activated_at DESC);

-- Step 11: COMMENT (audit metadata)
COMMENT ON TABLE governance.discovery_tier_config IS
    'M10 Discovery Tier Config (V111). 5 row seed Tier A/B/C/D/E per M10 DESIGN §2.1. regime_detection_method allowlist atr_vol_funding/pelt_reserved/none per ADR-0036 (HMM/GARCH/Markov-switching hard reject).';

COMMENT ON TABLE governance.discovery_tier_activations IS
    'M10 Tier Activation Ledger (V111). Hypertable on activated_at (7d chunk; 30d compress; 180d retention). Append-only audit; tier_change_reason 6 values; engine_mode CHECK enforces capital_trigger live/live_demo only (anti-mock per M10 DESIGN §9.3).';

COMMENT ON COLUMN governance.discovery_tier_activations.approval_lal_ref IS
    'Placeholder FK to V112 lease_lal_assignments.id; V112 land 後 ALTER TABLE ADD CONSTRAINT FK (per M10 DESIGN §6.1 LAL 2/3/4 對應路徑).';

COMMENT ON COLUMN governance.discovery_tier_activations.engine_mode IS
    'paper/demo/live_demo/live/replay. replay 為 M11 replay engine 寫入時 tag; training filter 仍 IN (live, live_demo).';

COMMENT ON COLUMN governance.discovery_tier_config.regime_detection_method IS
    'Allowlist per ADR-0036 Decision 1: atr_vol_funding (Y2-Y3 主路徑) / pelt_reserved (Y3+ ADR-debt) / none (非 Tier D). HMM/Markov-switching/GARCH 全 hard reject (永久黑名單).';
```

### 5.2 Migration DOWN(rollback;dev-only,production 慎用)

```sql
-- ============================================================
-- V111 ROLLBACK: 刪 hypertable + activations + config
-- ⚠️ DESTRUCTIVE: 所有 tier activation history 丟失;不可恢復。
-- 僅 dev/staging 使用;production rollback 走 V### 升級而非 down。
-- ============================================================

-- Step 1: Drop retention + compression policies
SELECT remove_retention_policy('governance.discovery_tier_activations', if_exists => TRUE);
SELECT remove_compression_policy('governance.discovery_tier_activations', if_exists => TRUE);

-- Step 2: Drop indexes
DROP INDEX IF EXISTS governance.idx_tier_activations_change_reason;
DROP INDEX IF EXISTS governance.idx_tier_activations_lal_ref;
DROP INDEX IF EXISTS governance.idx_tier_activations_tier_to_at;

-- Step 3: Drop tables (順序: activations 先 drop 因 FK to config)
DROP TABLE IF EXISTS governance.discovery_tier_activations;
DROP TABLE IF EXISTS governance.discovery_tier_config;
```

### 5.3 Idempotency 驗證

per V055 5-round loop + V083/V084 incident precedent,V111.sql 必跑兩次:
- 第一次:CREATE TABLE × 2 + INSERT seed 5 row + hypertable + policies + 3 index → 0 RAISE / 0 ERROR
- 第二次:全 IF NOT EXISTS / ON CONFLICT DO NOTHING / hypertable if_not_exists / policies if_not_exists → 0 RAISE / 0 重複 row

---

## §6 Cross-V### Dependency + Cross-Ref Schema

### 6.1 Cross-V### dependency 圖

```
V098 (governance.audit_log)             ← V111 (cross-ref audit;非 FK)
V091 (P0 portfolio_var)                  ← V111 (capital_observed_usdt application-layer compute)
TimescaleDB extension                    ← V111 (hypertable prereq)

V111 (M10 discovery_tier config + activations)
    │
    ├─→ V112 (M1 LAL tiers) — tier transition 必 emit lease 走 lal_gate → 寫 lease_lal_assignments
    │   approval_lal_ref placeholder FK (V112 land 後 ALTER ADD CONSTRAINT FK)
    │
    ├─→ V106 (M3 health) — HEALTH_DEGRADED 60min sustained → M10 demote 一階 (cross-ref query)
    │
    └─→ V107 (M11 replay) — replay engine 重放 tier transition (engine_mode='replay')
```

### 6.2 為什麼 V111 與 V112 lease 表用 placeholder FK(非立即 FK)

per `db-schema-design-financial-time-series` skill §5 + V112 §6.2:
- V112 schema 由 PA 同 Sprint 1A-β 派工待 land;V111 寫 FK CONSTRAINT 此刻會 RAISE(target 不存在)
- V112 land 後 ALTER ADD CONSTRAINT 補:`ALTER TABLE governance.discovery_tier_activations ADD CONSTRAINT fk_tier_activations_lal_ref FOREIGN KEY (approval_lal_ref) REFERENCES governance.lease_lal_assignments(id);`
- 屆時走另一個 V### migration ALTER ADD CONSTRAINT
- application layer(Rust lal_gate)責任維持 referential integrity;healthcheck Sprint 1B 補 `check_tier_activations_lal_ref_orphan()`

### 6.3 V112 (M1 LAL) cross-ref pattern

```sql
-- 例: A→B tier transition 走 LAL 2 approval
-- 1. lal_gate Rust module 觸發 lease emit → 寫 lease_lal_assignments tier=2
-- 2. lease approve 後寫 discovery_tier_activations 並 ref lease_lal_assignments.id
INSERT INTO governance.discovery_tier_activations
    (tier_from, tier_to, capital_observed_usdt, trigger_threshold_id,
     sustained_days_observed, activated_by, approval_lal_ref, tier_change_reason,
     engine_mode, evidence_json)
VALUES
    ('A', 'B', 12500.00, 3, 30, 'lal_gate',
     <lease_lal_assignments.id from previous insert>, 'capital_trigger', 'live',
     jsonb_build_object(
         'source', 'lal_gate',
         'sustained_metric', jsonb_build_object(
             'smoothing_window_days', 7,
             'sustained_window_days', 30,
             'aum_min_in_window_usdt', 11200,
             'aum_avg_in_window_usdt', 12500
         )
     ));
```

### 6.4 V106 (M3 health) cross-ref pattern

```sql
-- 例: M3 HEALTH_DEGRADED 60min sustained → M10 demote 一階 (C→B)
-- M3 emit → lal_gate Rust module 走 LAL 1 LIGHT_REVIEW auto-approve → 寫 demote row
INSERT INTO governance.discovery_tier_activations
    (tier_from, tier_to, capital_observed_usdt, trigger_threshold_id,
     sustained_days_observed, activated_by, approval_lal_ref, tier_change_reason,
     engine_mode, evidence_json)
VALUES
    ('C', 'B', 32100.00, 3, 30, 'm3_health_degraded_demoter',
     <lease_lal_assignments.id LAL 1 auto>, 'm3_health_degraded', 'live',
     jsonb_build_object(
         'source', 'm3_health_degraded_demoter',
         'demote_reason', 'liquidation_buffer_breach',
         'm3_health_observation_id', <V106 health_observations.id>
     ));
```

### 6.5 V107 (M11 replay) cross-ref pattern

```sql
-- 例: M11 nightly replay 重放 tier transition
INSERT INTO governance.discovery_tier_activations
    (tier_from, tier_to, capital_observed_usdt, trigger_threshold_id,
     sustained_days_observed, activated_by, approval_lal_ref, tier_change_reason,
     engine_mode, evidence_json)
VALUES
    ('A', 'B', 12500.00, 3, 30, 'm11_replay_engine',
     <lease_lal_assignments.id replay>, 'capital_trigger', 'replay',  -- ← engine_mode='replay'
     jsonb_build_object(
         'source', 'm11',
         'original_activation_id', <V111 discovery_tier_activations.id replayed>,
         'replay_at', now()
     ));
```

---

## §7 Linux PG Empirical Dry-Run Protocol(mandatory)

per CLAUDE.md §Data, Migrations, And Validation + `feedback_v_migration_pg_dry_run.md` + V055 5-round loop / V083 / V084 incident chain,V111 涉及:
- governance schema 新表(2 個)+ TimescaleDB hypertable(1 個)
- TimescaleDB extension prereq + create_hypertable + add_compression_policy + add_retention_policy
- CHECK constraint runtime ENUM semantic(特別 regime_detection_method 黑名單反向驗)
- 5 row seed INSERT ON CONFLICT idempotency
- composite CHECK constraint(chk_tier_transition_distinct / chk_engine_mode_capital)
- legacy learning schema stub detection(Guard A)

**必先 Linux PG empirical 驗證**,禁 Mac mock pytest 代替。

### 7.1 MIT C9 待補的 PG reflection query(spec sign-off 前必補)

per CLAUDE.md `docs/agents/context-loading.md` "PG Connection Examples"(Linux runtime authoritative):

```bash
# Connection (per V112 dry-run §7.1):
# Host: 127.0.0.1 Port: 5432 User: trading_admin DB: trading_ai
# Auth: ~/.pgpass *:5432:trading_ai:trading_admin:****

# Query 1: _sqlx_migrations head 確認 V111 dispatch 前提
ssh trade-core "PGPASSWORD=\$(cat ~/.pgpass | grep trading_ai | cut -d: -f5) psql -h 127.0.0.1 -p 5432 -U trading_admin -d trading_ai -c 'SELECT max(version), array_agg(version ORDER BY version DESC) FROM (SELECT version FROM _sqlx_migrations ORDER BY version DESC LIMIT 15) sub'"
# Expected: ≥ V098 (V098 governance.audit_log land 是 V111 prereq); 理想 V091/V106 已 land

# Query 2: governance schema 已 land 驗
ssh trade-core "PGPASSWORD=\$(cat ~/.pgpass | grep trading_ai | cut -d: -f5) psql -h 127.0.0.1 -p 5432 -U trading_admin -d trading_ai -c \"SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema='governance' ORDER BY table_name\""
# Expected: 含 audit_log (V098); 可能含 lease_lal_tiers / lease_lal_assignments (V112) 已 land 時

# Query 3: TimescaleDB extension 已 land 驗
ssh trade-core "PGPASSWORD=\$(cat ~/.pgpass | grep trading_ai | cut -d: -f5) psql -h 127.0.0.1 -p 5432 -U trading_admin -d trading_ai -c \"SELECT extname, extversion FROM pg_extension WHERE extname='timescaledb'\""
# Expected: 1 row (timescaledb ≥ 2.10)

# Query 4: legacy V111 placeholder v0 learning schema stub 不存在驗
ssh trade-core "PGPASSWORD=\$(cat ~/.pgpass | grep trading_ai | cut -d: -f5) psql -h 127.0.0.1 -p 5432 -U trading_admin -d trading_ai -c \"SELECT table_name FROM information_schema.tables WHERE table_schema='learning' AND table_name IN ('discovery_tier_config','capital_triggers')\""
# Expected: 0 rows (clean greenfield); 若 1+ rows → 觸 Guard A 反向衝突 RAISE

# Query 5: V091 portfolio_var land 驗 (application-layer capital_observed_usdt source)
ssh trade-core "PGPASSWORD=\$(cat ~/.pgpass | grep trading_ai | cut -d: -f5) psql -h 127.0.0.1 -p 5432 -U trading_admin -d trading_ai -c \"SELECT column_name, data_type FROM information_schema.columns WHERE table_schema='trading' AND table_name='portfolio_var' AND column_name='usdt_var_15m'\""
# Expected: 1 row (NUMERIC); 若 0 rows → V091 未 land,M10 IMPL 期 application-layer capital source 路徑 patch
```

**待 MIT C9 補資料的 5 處 placeholder**(spec sign-off 前必更新):
1. `_sqlx_migrations` head 真實 = ?(spec 假設 ≥ V098)
2. governance.audit_log 已 land 確認 = ?
3. TimescaleDB extension 已 land + version = ?(影響 hypertable + compression policy 可用性)
4. legacy learning.discovery_tier_config / capital_triggers stub 不存在確認 = ?(若存在 → Guard A 反向 RAISE)
5. V091 portfolio_var.usdt_var_15m column name + type 確認(影響 IMPL 期 capital source 路徑)

### 7.2 Round 1 — V111 SQL 真實 PG semantic empirical 驗證

```bash
# ssh trade-core 執行(不在 Mac 跑)
ssh trade-core "
  cd ~/BybitOpenClaw/srv && \
  PGPASSWORD=\$(cat ~/.pgpass | grep trading_ai | cut -d: -f5) \
  psql -h 127.0.0.1 -p 5432 -U trading_admin -d trading_ai \
    -v ON_ERROR_STOP=1 -f sql/migrations/V111__m10_discovery_tier_config.sql
"
```

**Round 1 必驗 13 項**(empirical SELECT verify after V111 apply):

```sql
-- 1. governance.discovery_tier_config 表存在 + 15 columns
SELECT count(*) FROM information_schema.columns
WHERE table_schema='governance' AND table_name='discovery_tier_config';
-- Expected: 15

-- 2. governance.discovery_tier_activations 表存在 + 17 columns
SELECT count(*) FROM information_schema.columns
WHERE table_schema='governance' AND table_name='discovery_tier_activations';
-- Expected: 17

-- 3. 5 row seed 完整 (Tier A/B/C/D/E)
SELECT tier_level, capital_threshold_min_usdt, capital_threshold_max_usdt,
       regime_detection_method, activation_year_min
FROM governance.discovery_tier_config ORDER BY tier_level;
-- Expected: 5 rows
--   A|500.00|10000.00|none|1
--   B|10000.00|30000.00|none|2
--   C|30000.00|50000.00|none|2
--   D|50000.00|100000.00|atr_vol_funding|3
--   E|100000.00|NULL|atr_vol_funding|3

-- 4. tier_level CHECK 5 值齊全 + regime_detection_method 3 allowlist
SELECT pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid='governance.discovery_tier_config'::regclass
  AND conname LIKE '%tier_level%check%';
-- Expected: 含 A/B/C/D/E

SELECT pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid='governance.discovery_tier_config'::regclass
  AND conname LIKE '%regime_detection_method%check%';
-- Expected: 含 atr_vol_funding/pelt_reserved/none; 不含 hmm/garch/markov_switching

-- 5. tier_change_reason CHECK 6 值齊全
SELECT pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid='governance.discovery_tier_activations'::regclass
  AND conname LIKE '%tier_change_reason%check%';
-- Expected: 含 capital_trigger/operator_approval/m3_health_degraded/operator_override/clawback/initial_seed

-- 6. engine_mode CHECK 5 值齊全(含 replay)
SELECT pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid='governance.discovery_tier_activations'::regclass
  AND conname LIKE '%engine_mode%check%';
-- Expected: 含 paper/demo/live_demo/live/replay

-- 7. FK constraint 真存在 (activations.tier_to → config.tier_level)
SELECT conname, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid='governance.discovery_tier_activations'::regclass AND contype='f';
-- Expected: 1 row (tier_to → config.tier_level)

-- 8. 3 indexes 真建立
SELECT indexname FROM pg_indexes
WHERE schemaname='governance' AND tablename='discovery_tier_activations'
ORDER BY indexname;
-- Expected: ≥ 4 (1 PK + idx_tier_activations_tier_to_at + idx_tier_activations_lal_ref + idx_tier_activations_change_reason)

-- 9. Hypertable 存在 + chunk_time_interval 7d
SELECT hypertable_name, num_chunks
FROM timescaledb_information.hypertables
WHERE hypertable_schema='governance' AND hypertable_name='discovery_tier_activations';
-- Expected: 1 row, num_chunks ≥ 0

SELECT integer_interval, time_interval
FROM timescaledb_information.dimensions
WHERE hypertable_schema='governance' AND hypertable_name='discovery_tier_activations';
-- Expected: time_interval = '7 days'

-- 10. Compression policy 真添加
SELECT *
FROM timescaledb_information.jobs
WHERE proc_name LIKE '%compress%'
  AND hypertable_name='discovery_tier_activations';
-- Expected: 1 row

-- 11. Retention policy 真添加
SELECT *
FROM timescaledb_information.jobs
WHERE proc_name LIKE '%retention%'
  AND hypertable_name='discovery_tier_activations';
-- Expected: 1 row

-- 12. CHECK constraints (tier_transition_distinct / engine_mode_capital) 真存在
SELECT conname, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid='governance.discovery_tier_activations'::regclass
  AND conname IN ('chk_tier_transition_distinct', 'chk_engine_mode_capital');
-- Expected: 2 rows

-- 13. ADR-0036 黑名單 hard reject empirical INSERT test
BEGIN;
SAVEPOINT test_blacklist_hmm;
INSERT INTO governance.discovery_tier_config
    (tier_level, capital_threshold_min_usdt, enable_strategy_list,
     regime_detection_method, activation_year_min)
VALUES
    ('A', 500.00, ARRAY['grid']::TEXT[], 'hmm', 1);
-- Expected: ERROR: violates check constraint
ROLLBACK TO SAVEPOINT test_blacklist_hmm;

SAVEPOINT test_blacklist_garch;
INSERT INTO governance.discovery_tier_config
    (tier_level, capital_threshold_min_usdt, enable_strategy_list,
     regime_detection_method, activation_year_min)
VALUES
    ('A', 500.00, ARRAY['grid']::TEXT[], 'garch', 1);
-- Expected: ERROR: violates check constraint
ROLLBACK TO SAVEPOINT test_blacklist_garch;

SAVEPOINT test_blacklist_markov;
INSERT INTO governance.discovery_tier_config
    (tier_level, capital_threshold_min_usdt, enable_strategy_list,
     regime_detection_method, activation_year_min)
VALUES
    ('A', 500.00, ARRAY['grid']::TEXT[], 'markov_switching', 1);
-- Expected: ERROR: violates check constraint
ROLLBACK TO SAVEPOINT test_blacklist_markov;

-- engine_mode capital_trigger paper/demo reject empirical test
SAVEPOINT test_engine_mode_paper;
INSERT INTO governance.discovery_tier_activations
    (tier_from, tier_to, capital_observed_usdt, trigger_threshold_id,
     sustained_days_observed, activated_by, tier_change_reason, engine_mode)
VALUES
    ('A', 'B', 12500.00, 3, 30, 'lal_gate', 'capital_trigger', 'paper');
-- Expected: ERROR: violates chk_engine_mode_capital
ROLLBACK TO SAVEPOINT test_engine_mode_paper;

SAVEPOINT test_engine_mode_demo;
INSERT INTO governance.discovery_tier_activations
    (tier_from, tier_to, capital_observed_usdt, trigger_threshold_id,
     sustained_days_observed, activated_by, tier_change_reason, engine_mode)
VALUES
    ('A', 'B', 12500.00, 3, 30, 'lal_gate', 'capital_trigger', 'demo');
-- Expected: ERROR: violates chk_engine_mode_capital
ROLLBACK TO SAVEPOINT test_engine_mode_demo;

-- 同時測 tier_transition_distinct CHECK
SAVEPOINT test_transition_distinct;
INSERT INTO governance.discovery_tier_activations
    (tier_from, tier_to, capital_observed_usdt, trigger_threshold_id,
     sustained_days_observed, activated_by, tier_change_reason, engine_mode)
VALUES
    ('A', 'A', 500.00, 1, 0, 'system', 'initial_seed', 'live');
-- Expected: ERROR: violates chk_tier_transition_distinct (A != A)
ROLLBACK TO SAVEPOINT test_transition_distinct;

ROLLBACK;
```

### 7.3 Round 2 — Idempotency 驗證

重跑 V111.sql 第二次必不 RAISE / 必不重複 INSERT seed / 必不重複建 hypertable:

```bash
ssh trade-core "
  cd ~/BybitOpenClaw/srv && \
  PGPASSWORD=\$(cat ~/.pgpass | grep trading_ai | cut -d: -f5) \
  psql -h 127.0.0.1 -p 5432 -U trading_admin -d trading_ai \
    -v ON_ERROR_STOP=1 -f sql/migrations/V111__m10_discovery_tier_config.sql
"
# Expected exit code 0; all DO blocks output NOTICE-only PASS; 0 RAISE EXCEPTION
```

**Round 2 後驗證**:
```sql
-- 確認 V111 不 double-create
SELECT count(*) FROM information_schema.tables
WHERE table_schema='governance'
  AND table_name IN ('discovery_tier_config', 'discovery_tier_activations');
-- Expected: 2

-- 確認 seed rows 仍 5(ON CONFLICT DO NOTHING 生效)
SELECT count(*) FROM governance.discovery_tier_config;
-- Expected: 5(非 10)

-- 確認 hypertable 仍 1
SELECT count(*) FROM timescaledb_information.hypertables
WHERE hypertable_schema='governance' AND hypertable_name='discovery_tier_activations';
-- Expected: 1

-- 確認 compression / retention policies 仍各 1
SELECT count(*) FROM timescaledb_information.jobs
WHERE hypertable_name='discovery_tier_activations';
-- Expected: 2 (compression + retention)

-- 確認 indexes 仍 3 + 1 PK
SELECT count(*) FROM pg_indexes
WHERE schemaname='governance' AND tablename='discovery_tier_activations';
-- Expected: ≥ 4
```

### 7.4 為何 Mac mock pytest 不夠(V055 5-round loop 教訓)

per memory `feedback_v_migration_pg_dry_run.md` + `project_2026_05_02_p0_sqlx_hash_drift`:
- Mac mock pytest 無法捕捉 TimescaleDB hypertable + compression policy + retention policy 真實 runtime semantic
- Mac static parse review 無法驗 `create_hypertable` / `add_compression_policy` / `add_retention_policy` 在 trading_ai DB 是否真可呼叫(extension version mismatch / permission issue)
- Mac 無法驗 composite CHECK constraint(`chk_engine_mode_capital` 含 OR + IN ()) 在 INSERT 時真 reject
- Mac 無法驗 ARRAY[]::TEXT[] 在 PG runtime 是否與 V111 spec assumption 一致
- V055 chain 5 round 都 Mac false-pass 後 Linux 撞 bug;V094 / V106 / V112 / V111 全須遵守 V055 mandate

**E2 / E4 / A3 review 必含 Linux PG dry-run gate 證據 ID**(per CLAUDE.md §Data, Migrations, And Validation + V094 §4.3 範式)。

---

## §8 Engine Restart 實測 SOP(per 2026-05-02 sqlx hash drift 教訓)

per memory `project_2026_05_02_p0_sqlx_hash_drift`(commit `3681f83`),V111 file edit 後 DB checksum 必同步:

```bash
# E1 IMPL: 寫 V111.sql 完成後跑 Linux dry-run (per §7.2)
# 若 V111.sql 落地後又被 edit → DB checksum drift
# 必跑 repair binary 同步 checksum 到 _sqlx_migrations table

ssh trade-core "
  cd ~/BybitOpenClaw/srv && \
  cargo run --release --bin repair_migration_checksum -- --version 111
"
# Expected: V111 checksum updated in _sqlx_migrations table to match new file SHA
```

### 8.1 Engine restart 後驗證 sqlx migrate 不 panic

```bash
ssh trade-core "bash ~/BybitOpenClaw/srv/helper_scripts/restart_all.sh --rebuild"

ssh trade-core "tail -200 ~/BybitOpenClaw/srv/program_code/exchange_connectors/bybit_connector/openclaw_engine/logs/engine.log 2>&1 | grep -E 'sqlx|migration|panic|timescale|hypertable'"
# Expected: 0 panic; 'Applied migrations' 正常 log; V111 success=t in _sqlx_migrations;
#           hypertable / compression policy / retention policy 配置 log 正常

ssh trade-core "PGPASSWORD=\$(cat ~/.pgpass | grep trading_ai | cut -d: -f5) psql -h 127.0.0.1 -p 5432 -U trading_admin -d trading_ai -c 'SELECT version, success, description FROM _sqlx_migrations WHERE version=111'"
# Expected: 1 row, success=t
```

### 8.2 治理盲點防範

per `project_2026_05_02_p0_sqlx_hash_drift` + V094 §5.3:cargo test PASS ≠ runtime sqlx migrate 驗證。E2 / E4 review 必含「engine restart 實測 + sqlx migrate runtime 不 panic」driver evidence。特別 TimescaleDB hypertable + compression / retention policy 配置可能在 restart_all 後第一次 chunk creation 才暴露錯誤;E4 regression 必含 24h 後 first chunk 創建 verify。

---

## §9 Rollback Plan + Reversibility Analysis

### 9.1 V111 rollback DDL

詳見 §5.2(remove policies + `DROP INDEX` + `DROP TABLE` 順序處理 FK)。

### 9.2 Reversibility 分析

| 操作 | 可逆? | 風險 |
|---|---|---|
| `remove_retention_policy` + `remove_compression_policy` | 可逆(rerun V111 重建)| LOW |
| `DROP TABLE governance.discovery_tier_activations` | 邏輯可逆(rerun V111)但 row data 不可逆(全 drop + hypertable chunk 全 drop)| **HIGH** — 所有 tier activation history 丟失 |
| `DROP TABLE governance.discovery_tier_config` | 可逆(rerun V111 重 seed)| MED — 若 IMPL 期 operator override 改過 seed 值,rerun 會還原 default |
| `DROP INDEX` | 可逆(rerun V111 重建)| LOW |

### 9.3 Rollback 觸發條件

- 僅 dev / staging
- production rollback 走 V### 升級(e.g. V###+1 加 ADD COLUMN / 改 CHECK constraint;不走 V111 down)

### 9.4 V096 boundary

per V101 spec v3 §7 + V112 §9.4:rollback 路徑不跨 V096(V096 drop dead tables 不可逆)。V111 rollback 全在 V096 之後(V096 < V098 < V111),無 boundary 風險。

---

## §10 Audit Field(per V103 EXTEND / V112 範式)

V111 兩表均採 V103 EXTEND §14 + V112 §10 同範式 5 audit field:

| Column | DEFAULT | NOT NULL | 設計 |
|---|---|---|---|
| `created_by` | `'system_seed'`(config)/ `'lal_gate'`(activations)| NOT NULL | writer / actor;allowlist 'system_seed' / 'lal_gate' / 'operator' / 'm3_health_degraded_demoter' / 'm11_replay_engine' / 'operator_override' |
| `created_at` | now() | NOT NULL | row insert 時間(server trusted)|
| `updated_by` | NULL | NULLABLE | 後續 update 的 actor(主要 config UPDATE / activations clawback UPDATE)|
| `updated_at` | NULL | NULLABLE | last update 時間 |
| `source_version` | `'V111'` | NOT NULL | schema version tag |

### 10.1 為什麼 discovery_tier_config + discovery_tier_activations 都需 audit field

per DOC-08 §12 #8 安全不變量「交易可解釋」+ §二 #8:
- tier config 是 governance approval 的 ground truth;每次 config 改動必有 audit trail
- tier activation 是 lease emit 的 decision input;每筆必可 reproduce(per M10 DESIGN §5.1)

### 10.2 update_at / update_by 何時填

`discovery_tier_activations`:
- clawback 執行時不 UPDATE 既有 row;新寫 row(tier_from=B tier_to=A activated_by='operator_override' tier_change_reason='clawback')— 對齊 M10 DESIGN §5.3 append-only
- evidence_json 補背景時可 UPDATE 但需 audit trail 留 updated_by

`discovery_tier_config`:
- operator override 改 capital_threshold(罕見;走 V### migration per M10 DESIGN §9.4)→ UPDATE `updated_by='operator'` + `updated_at=now()`
- enable_strategy_list 增刪 strategy_name(走 V### migration)→ UPDATE

---

## §11 Acceptance Criteria(7 條 sign-off 標準)

### 11.1 Schema acceptance(MIT + E2)

| # | 標準 | 驗證方法 |
|---|---|---|
| 1 | `governance.discovery_tier_config` 15 column 全俱在 + 5 seed rows 完整 + Tier A-E ladder 對應 M10 DESIGN §2.1 | `SELECT count(*) FROM information_schema.columns WHERE table_schema='governance' AND table_name='discovery_tier_config'` = 15;5 seed row 對齊 M10 DESIGN §2.1 |
| 2 | `governance.discovery_tier_activations` 17 column 全俱在 + hypertable on activated_at (7d chunk) + 2 composite CHECK + 1 FK | `SELECT * FROM timescaledb_information.hypertables WHERE hypertable_name='discovery_tier_activations'` 返 1 row;CHECK + FK count empirical 對齊 |
| 3 | regime_detection_method CHECK 強制 hard reject 'hmm' / 'garch' / 'markov_switching'(per ADR-0036)| empirical INSERT test reject all 3 forbidden values(per §7.2 step 13)|
| 4 | engine_mode CHECK 5 值齊全(含 'replay'); chk_engine_mode_capital 強制 capital_trigger 必 live/live_demo/replay | empirical INSERT test reject 'paper'/'demo' for capital_trigger |
| 5 | 5 row seed 對應 v5.8 §2 M10 ladder + ADR-0036 Tier D 'atr_vol_funding' / Tier A/B/C 'none' | empirical SELECT 驗 `tier_level='D' AND regime_detection_method='atr_vol_funding'`;`tier_level='A' AND regime_detection_method='none'` |
| 6 | Compression policy + retention policy 真添加(30d compress / 180d retention)| `SELECT count(*) FROM timescaledb_information.jobs WHERE hypertable_name='discovery_tier_activations'` = 2 |
| 7 | V111.sql idempotent 雙跑 0 RAISE + seed rows 仍 5(非 10) + hypertable / policies 不重複 | `psql -f V111.sql` × 2 + verify 全部 count 不變 |

### 11.2 Cross-V### acceptance(PA)

| # | 標準 | 驗證方法 |
|---|---|---|
| 1 | V098 prereq 滿足 + governance.audit_log 存在 + TimescaleDB extension land | `SELECT version FROM _sqlx_migrations WHERE version=98`;`SELECT extname FROM pg_extension WHERE extname='timescaledb'` |
| 2 | V112 placeholder FK 待 V112 land 後 ALTER ADD CONSTRAINT 邏輯預留 | placeholder FK column 存在;application layer cross-ref query 可跑 |
| 3 | V091 / V106 / V107 cross-ref query 不破壞 V111 schema | per §6 範例 query 預跑 |

### 11.3 治理 acceptance(QA + R4)

| # | 標準 | 驗證方法 |
|---|---|---|
| 1 | sqlx checksum 對齊 + engine restart 後 success=t | per §8 SOP |
| 2 | ML training filter `IN ('live','live_demo')` 在 future ML consumer 反映 | per CLAUDE.md §Data + MIT memory baseline;MV / consumer 不引 V111 但對齊原則 |
| 3 | docs/README.md 加 V111 spec 入 index | per CLAUDE.md §七 docs/README 規則 |
| 4 | legacy V111 placeholder v0 learning schema stub 不存在(per Guard A 反向)| empirical SELECT 驗 `learning.discovery_tier_config` + `learning.capital_triggers` 不存在 |

---

## §12 開放問題 + Caveat

### 12.1 待 MIT C9 確認

1. **`_sqlx_migrations` head 真實**(per §7.1 Query 1)— spec 假設 ≥ V098
2. **TimescaleDB extension version**(per §7.1 Query 3)— ≥ 2.10 才有 add_retention_policy 完整 API;spec 假設 ≥ 2.10
3. **legacy V111 placeholder v0 stub 是否存在**(per §7.1 Query 4)— spec 假設 greenfield;若 stub 存在需 V### migration DROP 後再 V111 apply
4. **V091 portfolio_var.usdt_var_15m column 確認**(per §7.1 Query 5)— spec 假設 column 存在 + NUMERIC type;影響 IMPL 期 capital_observed_usdt source 路徑
5. **V112 land 時點**(per §6.2)— V111 寫 placeholder FK column;V112 land 後 ALTER ADD CONSTRAINT FK 路徑由 PA Sprint 1A-β 派工確認

### 12.2 已知 caveat

1. **5 seed rows 預設值是 baseline,operator 可後續 UPDATE 改 enable_strategy_list / capital_threshold 等**(走 V### migration per M10 DESIGN §9.4;非 hot-edit SQL);本 spec 不預設 operator override 路徑
2. **`approval_lal_ref` placeholder FK** 在 V112 land 前無 FK constraint;application layer(lal_gate Rust module)寫入時需自行確保 ref 真存在(否則 dangling reference);healthcheck Sprint 1B 補 `check_tier_activations_lal_ref_orphan()`
3. **Tier D 9 cell × strategy weight matrix** 不在本 V111 schema(per M10 DESIGN §12.2 Q4 open);Sprint 6+ IMPL 期決定走獨立 V### table 還是 JSONB column;當前 V111 留 enable_strategy_list 含 `'regime_adaptive_9cell'` strategy_name placeholder
4. **`engine_mode='replay'`** 是 M11 replay engine 寫入時 tag;ML training filter `IN ('live','live_demo')` 不含 replay(per CLAUDE.md §二 + MIT memory baseline)
5. **`activated_by` 不 enum**:actor identity 動態擴增(lal_gate / operator / m3_health_degraded_demoter / m11_replay_engine 等);writer 端(lal_gate Rust module Sprint 4+ IMPL)責任維持 naming consistency
6. **`trigger_threshold_id` 1-7** 對應 M10 DESIGN §3.1 7 級 capital threshold step;若 ladder 後續修訂(如 Y4+ 加 step 8 = $1M),本 V111 schema 需 ALTER CHECK BETWEEN
7. **hypertable + compression segment by `tier_to`** — Tier E activation 可能很罕見(< 10 row total in Y1-Y3);compression segment_by 對 sparse tier 效益低;但對齊 V106 範式設計,future Y3+ growth 後生效
8. **180d retention** 對齊 V106 範式;但 governance audit 可能需更長(e.g. 1y+)— ALTER POLICY 即可,當前 180d 設計可接受

### 12.3 Sprint 1B writer 路徑未在本 spec 範圍

V111 apply 後立即 0 row (Foundation stage per MIT pipeline maturity);Sprint 1B 補 writer 後升 Skeleton。`lal_gate` Rust module Sprint 4+ IMPL。

---

## §13 後續行動(給 PM 派發)

| Action | Owner | Track | Priority |
|---|---|---|---|
| Sign-off 本 V111 spec full DDL v0 + M10 DESIGN spec | PM | Sprint 1A-γ schema prereq closure | P0 |
| MIT C9 跑 §7.1 5 條 ssh PG query + 補 5 處 placeholder | MIT | Sprint 1A-γ pre-dispatch | P0 |
| Reconcile cross-V### dependency(V091/V106/V107/V112 對 V111 cross-ref 對齊)| PA | Sprint 1A-γ pre-dispatch | P0 |
| Reconcile V111 placeholder v0 反向錯誤之 downstream contamination 風險 — 凡 v0 placeholder(learning schema)若被 sub-agent 派工讀過需追補 errata | PM | Sprint 1A-γ pre-dispatch | P0 |
| IMPL kickoff:派 E1 寫 V111.sql + Linux PG dry-run × 2 + E2/E4 + restart_all 部署 | PM | Sprint 1A-γ IMPL | P1 |
| Sprint 1B writer 上線:`tier_activation_writer` + healthcheck `check_tier_activations_writer()` | E1 (Sprint 1B) | Sprint 1B | P2 |
| Sprint 4+ lal_gate Rust IMPL + sustained AUM monitor + 9 cell matrix(Y2-Y3+)| E1 (Sprint 4+) | Sprint 4-Y3 | P3 |

### 13.1 Sprint 1A-γ schema prereq closure 標誌

本 spec PM sign-off + MIT C9 dry-run 補資料 land + V091/V106/V107/V112 cross-ref reconciliation 完成 → Sprint 1A-γ V111 schema prereq 解除 → IMPL kickoff 派 E1。

---

## §14 關鍵文件指針

- 本 V111 spec:本檔
- **M10 DESIGN spec 姊妹檔**:`srv/docs/execution_plan/2026-05-21--m10_discovery_tier_design_spec.md`
- **ADR-0036(Tier D 黑名單 + 9 cell matrix source of truth)**:`srv/docs/adr/0036-m8-anomaly-detection-and-m10-tier-d-model-blacklist.md`
- **ADR-0034(LAL 0-4 authoritative source of truth)**:`srv/docs/adr/0034-decision-lease-layered-approval-lal.md`
- v5.8 主檔 §2 M10:`srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md`(line 364-389)
- PA dispatch consolidation §6 cross-V### dep graph:`srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md`
- V112 spec(full DDL 範式 + LAL tiers + 5 audit field):`srv/docs/execution_plan/2026-05-21--v112_m1_decision_lease_lal_tiers_schema_spec.md`
- V103 spec(14 section + 5 audit field EXTEND 範式):`srv/docs/execution_plan/2026-05-21--v103_v104_earn_hypotheses_schema_spec.md`
- V106 spec(hypertable + 30d compress + 180d retention 範式):`srv/docs/execution_plan/2026-05-21--v106_m3_health_observations_schema_spec.md`
- math-model-audit skill(HMM/GARCH 黑名單 source of truth):`srv/.claude/skills/math-model-audit/SKILL.md`
- walk-forward-validation-protocol skill(block bootstrap + OOS SOP):`srv/.claude/skills/walk-forward-validation-protocol/SKILL.md`
- V094 spec(Guard A/B/C + Linux PG dry-run × 2 範式):`srv/docs/execution_plan/2026-05-15--v094_close_maker_first_audit_schema_spec.md`
- schema_guard_template:`srv/sql/migrations/templates/schema_guard_template.sql`
- repair binary:`srv/rust/openclaw_engine/src/bin/repair_migration_checksum.rs`
- V055 5-round loop + sqlx hash drift incident lessons:`memory/feedback_v_migration_pg_dry_run.md` + `memory/project_2026_05_02_p0_sqlx_hash_drift.md`
- CLAUDE.md §Data, Migrations, And Validation:`srv/CLAUDE.md`

---

**END V111 spec full DDL v0**
