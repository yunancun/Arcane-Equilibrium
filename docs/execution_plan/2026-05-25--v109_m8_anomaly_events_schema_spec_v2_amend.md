# V109 M8 anomaly_events schema spec v2 amend

**Date**: 2026-05-25
**Author**: PM transcribed from MIT W1-E inline delivery (Sprint 2 Wave 1 sub-agent `a5ac0b20b4312385b`)
**Base spec**: `docs/execution_plan/2026-05-21--v109_m8_anomaly_events_schema_spec.md` (1413 lines, SPEC-FULL-V0)
**Amend scope**: 3 P0 BLOCKER fix + 7 P1 reconcile + 1 new column

**MIT Linux PG empirical probe (2026-05-25 12:30 UTC)**：
- `_sqlx_migrations max(version)` = **112**（V109 not landed）
- TimescaleDB version = **2.26.1** (≥2.13 PASS)
- `governance.audit_log` (schema=governance) = **0 rows / 表不存在** ❌
- `learning.governance_audit_log` (schema=learning) = **1 row, 23 columns** ✅（真實表名 per V035+V098 chain）
- `learning.anomaly_events` = **0 rows / 表不存在**（greenfield）
- V106 / V107 sister landed

---

## §1 3 P0 BLOCKER（W1-F E1 派發前必修）

### P0-1: Guard A 表名修正（migration apply 立即 RAISE EXCEPTION）

5-21 spec §5.1 Line 406-414 寫 `governance.audit_log`（empirical 不存在）。真實表為 `learning.governance_audit_log`（23-column hypertable; V035 baseline + V098 extension）。同 sister V107 PA-DRIFT-1 patch 範式。

**修正**：
```sql
-- v2: learning.governance_audit_log 必須存在 (M8 → audit cross-ref query target)
IF NOT EXISTS (
    SELECT 1 FROM information_schema.tables
    WHERE table_schema='learning' AND table_name='governance_audit_log'
) THEN
    RAISE EXCEPTION
        'V109 Guard A FAIL: learning.governance_audit_log missing — '
        'V098 must apply before V109 (cross-ref query target). Verify _sqlx_migrations.';
END IF;
```

同步修正：
- §1.4 表 line 104 「governance.audit_log」→ 「learning.governance_audit_log」
- §9.1 Query 3 SQL `table_schema='governance' AND table_name='audit_log'` → `table_schema='learning' AND table_name='governance_audit_log'`
- §14.1 Caveat #3 更新

**Impact 未修**：V109 Linux PG empirical apply 立即 Guard A RAISE → migration FAIL → engine startup panic / sqlx checksum drift。

### P0-2: severity 4 級 vs 3 級衝突

| Source | severity 列舉 |
|---|---|
| Sprint 2 dispatch §5.2 line 266 | `INFO / WARNING / CRITICAL` (3 級) — **typo** |
| 5-21 V109 spec §2.1 line 144-149 | `INFO / WARN / CRITICAL / HALT` (4 級) |
| W1-E prompt + M8 design spec + ADR-0036 + CR-7 §5 | 4 級 |

**PM 拍板**：採 **4 級 (INFO/WARN/CRITICAL/HALT)**。HALT Y2+ 不寫 row 但 ENUM value 必先 land 避免 future ALTER。

### P0-3: engine_mode 5 值 vs 3 值衝突

| Source | engine_mode 列舉 |
|---|---|
| Sprint 2 dispatch §5.2 line 267 | `paper / demo / live` (3 值) — **typo 缺 live_demo + replay** |
| 5-21 V109 spec §2.1 line 179 | `paper / demo / live_demo / live / replay` (5 值) |
| CLAUDE.md §四 LiveDemo 不降級 + memory `project_engine_mode_tag_live_demo` | 4 標準值 + replay 例外 |

**PM 拍板**：採 **5 值** (paper/demo/live_demo/live/replay)；`replay` 是 ADR-0036 Decision 1 例外條款（read-only counterfactual via M11 replay surface）。

---

## §2 7 P1 Reconcile（v2 採用 5-21 spec naming + W1-E prompt 補強）

### P1-1: event_taxonomy 9 enum（剔除 own behavior 3 enum 走 M3）

**採 5-21 spec 9 taxonomy（v5.8 §2.M8 完整覆蓋）**：
- regime_shift / liquidation_cascade / orderbook_imbalance
- funding_outlier / volume_spike / spread_widening
- price_dislocation / ws_disconnect / fee_anomaly

**剔除 W1-E prompt own behavior 3 enum（走 M3 strategy_quality domain，不寫 V109）**：
- fill_rate_drift / slippage_outlier / lease_grant_anomaly → M3

**剔除 W1-E prompt `replay_divergence` enum**：走 V107 M11 replay_divergence_log（CR-7 dedup contract）。

### P1-2: detection_method 4 enum（per ADR-0036 Decision 2）

**採 5-21 spec 4 替代算法**：
- `atr_vol_funding_9cell` (regime + funding domain)
- `rv_percentile` (RV 統計)
- `block_bootstrap` (threshold 估計)
- `manual_operator` (rule-based fee/ws)

**剔除 W1-E prompt `arima_residual` / `isolation_forest`**：own behavior anomaly 方法，走 M3。

**剔除 W1-E prompt `autoencoder_Y2` 字面值**：Y2+ ML detector 走 ADR-0036 Decision 1 amendment 路徑（先 amend skill → amend ADR-0036 → amend V109 ENUM；不在 Sprint 2 scope）。

### P1-3: 命名對齊 `event_taxonomy`（不採 W1-E prompt `event_class`）

`taxonomy` 是金融時序 anomaly literature canonical term。

### P1-4: 時間 column 命名對齊 `observed_at`（不採 W1-E prompt `ts`）

對齊 V106/V107 sister `..._at` pattern + hypertable time dimension。

### P1-5: metric column 新增 `metric_baseline`（吸收 W1-E prompt `value_baseline`）

**v2 schema delta**：
```sql
metric_value      NUMERIC(18,8),  -- 5-21 spec 既有；當下觀測值
metric_baseline   NUMERIC(18,8),  -- v2 新增；30d rolling block bootstrap baseline；drift PSI 比對用
metric_threshold  NUMERIC(18,8),  -- 5-21 spec 既有；當下 active threshold
```

理由：三者語意分離有 audit value（per `data-drift-detection` skill §3.1 reference distribution 必存）。

### P1-6: 不採 W1-E prompt `audit_chain_ref` TEXT column

保留 5-21 spec 既有 `evidence_json` JSONB + 3 BIGINT cross-ref（m3_health_observation_ref / m7_decay_signal_ref / m1_lal_demote_ref）。理由：BIGINT id ref 比 TEXT 字串解析高效；`learning.governance_audit_log` 用 BIGINT id 反向 ref。

W1-F E1 IMPL 期若 PA 仍堅持 audit_chain_ref → amend 加 `audit_chain_id BIGINT REFERENCES learning.governance_audit_log(id) NULL` 作為 v3（soft ref 不 hard FK）。

### P1-7: strategy column 命名對齊 `strategy_id`（不採 W1-E prompt `strategy`）

對齊 V094 / V101 / V102 / V083 / V084 全 sister table 一致使用 `strategy_id` TEXT。

---

## §3 v2 Final Schema (23 column = 5-21 spec 22 + new `metric_baseline`)

```sql
CREATE TABLE IF NOT EXISTS learning.anomaly_events (
    id                              BIGSERIAL,
    observed_at                     TIMESTAMPTZ NOT NULL,
    event_taxonomy                  TEXT NOT NULL
                                    CHECK (event_taxonomy IN (
                                        'regime_shift', 'liquidation_cascade', 'orderbook_imbalance',
                                        'funding_outlier', 'volume_spike', 'spread_widening',
                                        'price_dislocation', 'ws_disconnect', 'fee_anomaly'
                                    )),  -- 9 taxonomy per M8 design spec §2.1
    severity                        TEXT NOT NULL
                                    CHECK (severity IN ('INFO','WARN','CRITICAL','HALT')),
    detection_method                TEXT NOT NULL
                                    CHECK (detection_method IN (
                                        'atr_vol_funding_9cell','rv_percentile',
                                        'block_bootstrap','manual_operator'
                                    )),  -- 4 per ADR-0036 Decision 2; NO hmm/markov/garch
    atr_vol_state                   TEXT CHECK (atr_vol_state IS NULL OR atr_vol_state IN ('LOW','MED','HIGH')),
    funding_state                   TEXT CHECK (funding_state IS NULL OR funding_state IN ('NEGATIVE','NEUTRAL','POSITIVE')),
    strategy_id                     TEXT,
    symbol                          TEXT,
    metric_value                    NUMERIC(18,8),
    metric_baseline                 NUMERIC(18,8),   -- v2 新增
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

**Guard A `v_missing` array 必加 `'metric_baseline'`**（5-21 spec line 423-431 amend）。

---

## §4 Hypertable / Compression / Retention / Index — 採 5-21 spec 原案

- chunk_time_interval = 7 days ✅
- compression segmentby = `event_taxonomy, severity` / orderby = `observed_at DESC, id DESC` / after 30 days ✅
- retention 180 days（vs V106 90d；對齊 M1 LAL 90d incident-free + M7 14d persistent + safety margin）✅
- 4 hot-path index：taxonomy / severity partial / symbol partial / strategy partial ✅

---

## §5 Guard A/B/C v2 amend list

5 處 amend：
1. **Guard A line 411-414**：表名修 `governance.audit_log` → `learning.governance_audit_log`（P0-1）
2. **Guard A line 423-431** `v_missing` array：加 `'metric_baseline'`（P1-5）
3. **Guard C line 498-622** 不變；metric_baseline column 不 enum 不需 CHECK
4. **§9.1 Query 3** SQL 修正表名（P0-1）
5. **§9.2 Round 1 step 1**：column count 22 → 23

ADR-0036 forbidden algorithm 雙重反向防護（line 449-477 + 558-568）完整保留；AC-S2-D-3 compliance PASS。

---

## §6 Migration filename + Linux PG dry-run plan (for W1-F E1)

**Filename**: `sql/migrations/V109__m8_anomaly_events_hypertable.sql`（對齊 V106/V107 sister pattern）

**Linux PG dry-run** (per 5-21 spec §9.1-§9.3 + v2 amend):
```bash
ssh trade-core "psql 'postgresql://trading_admin@127.0.0.1:5432/trading_ai' \
    -v ON_ERROR_STOP=1 -f sql/migrations/V109__m8_anomaly_events_hypertable.sql"
```

PA C9 4-placeholder 已 MIT empirical fill：
- `_sqlx_migrations max` = 112 ✅
- TimescaleDB version = 2.26.1 ✅
- `learning.governance_audit_log` landed = YES (23 column) ✅
- `learning.anomaly_events` stub 不存在 = CONFIRMED ✅

---

## §7 Stream D AC（v2 amend Sprint 2 dispatch §5.3 + 5-21 spec §13）

| # | AC | Owner | 驗證方法 |
|---|---|---|---|
| AC-S2-D-1 | V109 schema land (hypertable + Guard A/B/C + v2 amend) | W1-F E1 IMPL → Linux PG | `_sqlx_migrations.success=t` |
| AC-S2-D-2 | Idempotency 雙跑 0 RAISE / 0 duplicate | W1-F E1 + W2-E E2 | 雙 round empirical |
| AC-S2-D-3 | ADR-0036 黑名單 compliance (grep `hmm\|markov_switching\|garch` 0 hits) | W1-E spec + W2-E E2 | grep V109.sql + Round 3 RAISE test |
| AC-S2-D-4 | Hypertable 7d chunk + 4 partial index + 30d compression + 180d retention 生效 | W1-F E1 + Linux PG verify | `timescaledb_information.*` query |
| AC-S2-D-5 | Sprint 3 detector IMPL prerequisite ready | W3-C PM sign-off | spec + empirical evidence |
| AC-S2-D-6 | engine_mode CHECK 5 值齊全 + training filter rule preserve | W1-F E1 + MIT review | empirical INSERT test |
| **AC-S2-D-7** | **23 column 全俱在（含 v2 amend `metric_baseline`）** | W1-F E1 | `SELECT count(*) FROM information_schema.columns ...` = 23 |

---

## §8 W1-F E1 Dispatch readiness

**DISPATCH-READY-AFTER-P0-CLOSURE** (本 v2 spec amend land 完成後即可派發)：

1. 本 v2 amend spec 已 land ✅
2. PA amend Sprint 2 dispatch packet §5.2 lines 266-267 統一 4 級 + 5 值（待 PA 後續 sub-agent 或 PM 同步）
3. 派 W1-F E1 IMPL：拉 5-21 spec + 本 v2 delta 寫 `sql/migrations/V109__m8_anomaly_events_hypertable.sql`
4. E1 跑 Linux PG dry-run Round 1+2
5. PA + MIT cross-review V109.sql；W2-D E1 IMPL writer skeleton

**hr re-estimate**: 15-20 hr（5-21 spec §0 估計保持；v2 delta 工程量 < 2 hr：表名 patch + 1 column add + Guard array 加 1 字串）

---

## §9 對齊驗證（v5.8 + ADR + CR + memory）

| 對齊維度 | v2 verdict |
|---|---|
| ADR-0036 Decision 1（HMM/Markov/GARCH 黑名單）| Guard A + C 雙重反向防護完整 ✅ |
| ADR-0036 Decision 2-4（替代算法 4 種）| detection_method CHECK 4 enum 對齊 ✅ |
| ADR-0036 例外段（replay surface read-only counterfactual）| engine_mode 加 'replay' 第 5 值 ✅ |
| ADR-0034 數字越大越嚴方向 | m1_lal_demote_ref 為 demote 方向 ✅ |
| CR-5（M10 Tier D 黑名單）| 9-cell axis 對齊 ✅ |
| CR-7（M11 → M7 dedup；M3 single health authority）| Own behavior anomaly 走 M3；replay divergence 走 V107 ✅ |
| CR-7 §5 severity 4-level | INFO/WARN/CRITICAL/HALT 對齊 ✅ |
| H-11（M8 → M3 amplification cap 24h）| amplification_loop_24h_count INTEGER + writer 預計算 ✅ |
| CR-15（5-gate auto path inheritance）| m1_lal_demote_ref BIGINT soft ref ✅ |
| CLAUDE.md §七 engine_mode IN ('live','live_demo') ML filter | training query filter rule retained ✅ |
| Sprint 2 dispatch §5.2 line 256-258 schema-only scope | NO detector IMPL；Sprint 3 wire writer skeleton ✅ |

---

## §10 後續 PM 派發行動

1. ✅ **PM 拍板採 v2 amend spec**（本 file land）
2. **PA 後續 sub-agent amend Sprint 2 dispatch packet §5.2 lines 266-267**（4 級 severity + 5 值 engine_mode）— 可同 W1-A return 時 batch
3. **派 W1-F E1**：寫 V109.sql 對齊 5-21 spec + 本 v2 delta + Linux PG dry-run × 2 round
4. **W2-E E2 對抗式 review**：V109.sql idempotency + ADR-0036 grep gate + 23 column + cross-ref pattern
5. **MIT post-IMPL audit** (W2-E)：runtime empirical verify 7 AC + healthcheck `check_anomaly_writer()` Sprint 3 wire 前置

---

## §11 Reference

- Base spec (1413 lines): `docs/execution_plan/2026-05-21--v109_m8_anomaly_events_schema_spec.md`
- M8 design spec sister: `docs/execution_plan/2026-05-21--m8_anomaly_detection_design_spec.md`
- v5.8 §2.M8: `docs/execution_plan/2026-05-20--execution-plan-v5.8.md` line 279-318
- ADR-0036: `docs/adr/0036-m8-anomaly-detection-and-m10-tier-d-model-blacklist.md`
- Sprint 2 dispatch §5: `docs/execution_plan/2026-05-25--sprint_2_business_dispatch_packet.md` lines 252-298
- V106 / V107 / V112 sister hypertable spec
- V098 governance_audit_log baseline
- MIT W1-E sub-agent inline delivery: agent `a5ac0b20b4312385b` (2026-05-25)

---

**v2 amend SoT**：本 file（PM transcribed from MIT W1-E inline）。W1-F E1 IMPL 拉 5-21 spec + 本 v2 delta IMPL V109.sql。
