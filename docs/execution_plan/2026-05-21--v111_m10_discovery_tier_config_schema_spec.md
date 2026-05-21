---
spec: V111 — M10 Discovery Tier Config + Capital Triggers Schema
date: 2026-05-21
author: MIT consultant draft for PA Sprint 1A-γ dispatch (placeholder reserve)
phase: v5.8 Sprint 1A-γ schema prerequisite (per assignment)
status: SPEC-PLACEHOLDER (frontmatter + 大綱 reserve; full DDL land Sprint 1A-γ)
parent specs:
  - srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md §2 M10 Discovery Tier
  - srv/docs/adr/0036-anomaly-detection-atr-vol-funding.md (Tier D dependency)
mirror precedent:
  - srv/docs/execution_plan/2026-05-21--v103_v104_earn_hypotheses_schema_spec.md (format reference)
scope: placeholder spec — 不寫 V111.sql, 不在 Mac 跑 SQL, 不執行 PG, full DDL 在 Sprint 1A-γ 補完
---

# V111 M10 Discovery Tier Config + Capital Triggers Schema Migration Spec (PLACEHOLDER)

## §0 TL;DR

- **V111 新增 2 個 regular table**：`learning.discovery_tier_config`（per-tier discovery 規則 + 解鎖條件）+ `learning.capital_triggers`（AUM-based tier unlock 觸發 ledger）。
- **Tier A-E ladder（5 級）**：Y1 限 A；Y2 開 A+B+C；Y3+ 開 +D+E（per v5.8 §2 M10 module ladder）。
- **Tier D 限定**：用 ATR-vol + funding axis（per ADR-0036 黑名單），**禁 HMM / GARCH / Markov-switching**。
- **AUM trigger 條件**：7d moving AUM > tier-specific threshold 必持續 30d（sustained，非 spike）→ tier 解鎖；解鎖後落 capital_triggers audit。
- **engine_mode CHECK 4 值齊全**；AUM threshold 限 live/live_demo（不含 paper/demo — virtual capital 不 trigger）。
- **Sprint 1A-γ schedule**：M10 是 strategic capacity expansion 層；不阻擋 Sprint 1A critical path。

---

## §1 Background

### 1.1 v5.8 §2 M10 module 出處

v5.8 §2 M10 Discovery Tier module 列出：
- 5-tier ladder（A 最保守 / E 最 aggressive）
- Tier A：5 既有策略 reuse only
- Tier B：5 既有 + parameter sweep variants
- Tier C：5 既有 + 1 cointegration / pairs trading 新策略
- Tier D：跨 regime（ATR-vol + funding axis based）adaptive strategies — **不採 HMM 等 state-based 方法**
- Tier E：multi-strategy portfolio overlay + cross-asset rebalance
- 解鎖：sustained AUM threshold for 30d；Y1 限 A；Y2 開 B/C；Y3+ 開 D/E

### 1.2 Audit 來源

- MIT 2026-05-21 v5.8 audit Risk 11「M10 schema spec missing + Tier D ADR-0036 黑名單需在 schema 明示」
- R4 5.21 ADR alignment audit「M10 對應 ADR 待補」
- ADR-0036 alignment：Tier D schema 必反映 ATR-vol + funding axis 約束

---

## §2 Schema Outline (placeholder)

### 2.1 `learning.discovery_tier_config`

**Tables 大綱**：
- PK: `tier_config_id BIGSERIAL`
- Columns 大綱（12 fields）：
  - `tier_config_id`, `tier TEXT NOT NULL` (ENUM: A / B / C / D / E)
  - `effective_from TIMESTAMPTZ NOT NULL`, `effective_to TIMESTAMPTZ NULL`
  - `aum_threshold_usdt BIGINT NOT NULL` (sustained AUM trigger amount)
  - `sustained_window_days INTEGER NOT NULL DEFAULT 30` (per v5.8 — 30d sustained mandate)
  - `aum_window_smoothing_days INTEGER NOT NULL DEFAULT 7` (7d moving AUM)
  - `enabled_year INTEGER` (1=Y1 A only; 2=Y2 A+B+C; 3=Y3+ all)
  - `allowed_strategy_types JSONB NOT NULL` (per-tier strategy whitelist e.g. Tier A = ["grid","ma","bb_breakout","bb_reversion","funding_arb"])
  - `regime_detection_method TEXT` (Tier D only — must = `atr_vol_funding_dual_axis` per ADR-0036; 禁 `hmm` / `garch` / `markov_switching`)
  - `governance_approval_id BIGINT` (FK to `governance.audit_log.id`)
  - `engine_mode TEXT NOT NULL`

**Constraints 大綱**：
- CHECK: `tier` ∈ 5 值 ENUM (A / B / C / D / E)
- CHECK: `enabled_year` ∈ {1, 2, 3}
- **CHECK: `tier='D' IMPLIES regime_detection_method='atr_vol_funding_dual_axis'`** (per ADR-0036 — 禁 HMM/GARCH/Markov)
- **CHECK: `regime_detection_method NOT IN ('hmm','garch','markov_switching')`** (ADR-0036 黑名單 hard rejection)
- CHECK: `engine_mode` ∈ 4 值
- CHECK: `aum_threshold_usdt > 0`
- NOT NULL: tier, effective_from, aum_threshold_usdt, sustained_window_days, aum_window_smoothing_days, allowed_strategy_types, engine_mode

**Indexes 大綱**：
- `(tier, effective_from DESC)` — per-tier config history
- `(tier, effective_to) WHERE effective_to IS NULL` — current-active partial index hot path

### 2.2 `learning.capital_triggers`

**Tables 大綱**：
- PK: `trigger_id BIGSERIAL`
- Columns 大綱（11 fields）：
  - `trigger_id`, `triggered_at TIMESTAMPTZ NOT NULL`
  - `tier_from TEXT NOT NULL`, `tier_to TEXT NOT NULL` (e.g. A→B)
  - `aum_window_start TIMESTAMPTZ NOT NULL`, `aum_window_end TIMESTAMPTZ NOT NULL`
  - `aum_min_observed_usdt BIGINT NOT NULL`, `aum_max_observed_usdt BIGINT NOT NULL`
  - `aum_threshold_required_usdt BIGINT NOT NULL` (matched config snapshot)
  - `sustained_days_observed INTEGER NOT NULL` (must ≥ sustained_window_days)
  - `governance_approval_id BIGINT NULL` (FK to `governance.audit_log.id` — 待 Decision Lease approve)
  - `engine_mode TEXT NOT NULL`

**Constraints 大綱**：
- CHECK: `tier_from` ∈ 5 值 ENUM, `tier_to` ∈ 5 值 ENUM
- CHECK: `tier_to <> tier_from` (no-op trigger 拒)
- CHECK: `engine_mode` IN ('live','live_demo')` (paper/demo virtual capital 不 trigger)
- CHECK: `aum_min_observed_usdt ≤ aum_max_observed_usdt`
- NOT NULL: triggered_at, tier_from, tier_to, aum_*, sustained_days_observed, engine_mode

**Indexes 大綱**：
- `(triggered_at DESC)` — recent trigger audit
- `(tier_to)` — per-tier trigger aggregation

### 2.3 ENUM 列表 (per CR-X 對齊規則)

- `discovery_tier` ENUM 5 值 (A / B / C / D / E)
- `regime_detection_method` ENUM (atr_vol_funding_dual_axis = only allowed; HMM/GARCH/markov_switching 黑名單 by CHECK constraint)

### 2.4 ADR-0036 黑名單 schema 反映（Tier D 重點）

per ADR-0036，本 schema 明示 Tier D regime detection 只允許 `atr_vol_funding_dual_axis`：
- ❌ `hmm` — Hidden Markov Model
- ❌ `garch` — GARCH 系列
- ❌ `markov_switching` — Markov-switching regression

CHECK constraint 兩處硬封：
1. `tier='D'` 必對應 `regime_detection_method='atr_vol_funding_dual_axis'`（IMPLIES rule）
2. `regime_detection_method` 不論 tier 都不可 ∈ 黑名單（hard rejection）

### 2.5 Hypertable 判斷

**結論：2 表均 regular table**。理由：
- `discovery_tier_config`：低基數 ~5 tier × few config update/yr = ~tens row total
- `capital_triggers`：低基數 ~few trigger/yr（tier 解鎖是稀有事件）
- 無時序壓力；regular table + index 即足

---

## §3 Guard A/B/C Templates 大綱

### Guard A — table existence + FK target 對齊驗證

- 若 2 表已存在：驗 column 完整；缺即 RAISE
- 驗 `governance.audit_log` 存在（V098 prereq）

### Guard B — 不適用

V111 不 ALTER 既有 column type；本 spec 不設 Guard B 段。

### Guard C — CHECK constraint + ENUM 值齊全 + ADR-0036 黑名單 + index 對齊驗證

- `discovery_tier` ENUM 5 值齊全 (A / B / C / D / E)
- **CHECK constraint `tier='D' IMPLIES regime_detection_method='atr_vol_funding_dual_axis'` 真存在**
- **CHECK constraint `regime_detection_method NOT IN ('hmm','garch','markov_switching')` 真存在**
- `engine_mode` CHECK 4 值齊全（config）/ 2 值（triggers — live + live_demo only）
- Indexes 對齊

---

## §4 Linux PG Empirical Dry-Run Checklist (placeholder)

### 4.1 必跑 SQL (3-5 條 placeholder query)

```bash
# Query 1: _sqlx_migrations head + governance.audit_log V098 land 確認
ssh trade-core "psql -d trading_ai -c \"SELECT count(*) FROM information_schema.tables WHERE table_schema='governance' AND table_name='audit_log'\""

# Query 2: V111 apply 後驗 2 表 + 5 tier ENUM 真建立
ssh trade-core "psql -d trading_ai -c \"SELECT table_name FROM information_schema.tables WHERE table_schema='learning' AND table_name IN ('discovery_tier_config','capital_triggers')\""

# Query 3: ADR-0036 黑名單 CHECK 真 reject (empirical INSERT 'hmm' / 'garch' / 'markov_switching' 都拒)
# 例：
# INSERT INTO learning.discovery_tier_config (..., regime_detection_method, ...) VALUES (..., 'hmm', ...);
# Expected: ERROR: violates check constraint

# Query 4: Tier D IMPLIES rule 真 reject empty regime_detection_method for Tier D
# 例：
# INSERT INTO learning.discovery_tier_config (tier, regime_detection_method, ...) VALUES ('D', NULL, ...);
# Expected: ERROR: violates check constraint

# Query 5: capital_triggers engine_mode CHECK 真 reject 'paper'
# 例：
# INSERT INTO learning.capital_triggers (..., engine_mode) VALUES (..., 'paper');
# Expected: ERROR: violates check constraint
```

### 4.2 Idempotent 雙跑驗

per V055 5-round loop + V083/V084 incident precedent，V111.sql 必跑兩次：第二次必 0 RAISE / 0 重複 ENUM / 0 重複 index。

### 4.3 engine restart 實測

per a19797d 教訓：
- `restart_all.sh --rebuild` 後驗 engine.log 無 sqlx panic
- 驗 `_sqlx_migrations.success=t` for V111

---

## §5 Cross-V### Dependencies

per CR-9 cross-V### dependency graph：

| V### | 依賴 | 理由 |
|---|---|---|
| V111 | V098 (governance.audit_log) | FK target；已 land |
| V111 | 無其他 V### M-module 直接 FK | M10 是獨立 capital governance 層 |

**注**：V111 與 ADR-0036（V109 M8 也引用）schema-level shared rule（regime detection 黑名單）— 兩 V### 在 application layer + governance 層共同 enforce。

**Sprint 1A-γ dispatch ordering**：V111 可獨立 land；不阻擋其他 module。

---

## §6 Cross-References

- v5.8 §2 M10 Discovery Tier module: `srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md`
- ADR-0036 ATR-vol + funding dual-axis (Tier D dependency + 黑名單 source): `srv/docs/adr/0036-anomaly-detection-atr-vol-funding.md`
- ADR-alignment: per R4 建議補（M10 對應 ADR 待 PA dispatch 期 land）
- V109 spec (M8 — shared ADR-0036 黑名單): `srv/docs/execution_plan/2026-05-21--v109_m8_anomaly_events_schema_spec.md`
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

**END V111 spec placeholder**
