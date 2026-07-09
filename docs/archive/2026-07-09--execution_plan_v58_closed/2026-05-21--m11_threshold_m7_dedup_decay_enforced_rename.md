---
spec: M11 Threshold Statistical Derivation + M7 Dedup Contract + DECAY_ENFORCED Rename
date: 2026-05-21
author: MIT + QC consultant for PA Sprint 1A-β dispatch
phase: v5.8 Sprint 1A-β M11 + M7 schema prerequisite
status: SPEC-DRAFT-V0
parent specs:
  - srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md §2 M7 + M11
  - srv/docs/CCAgentWorkSpace/QC/workspace/reports/2026-05-21--v58_executability_audit.md
  - srv/docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-21--v58_executability_audit.md
  - srv/docs/adr/0038-m11-continuous-counterfactual-replay-and-liquidations-source.md (CR-14 已 land)
scope: spec only — 不寫 V107 / V113 SQL 實檔，不改業務代碼
---

# M11 Threshold 統計推導 + M7 Dedup Contract + DECAY_ENFORCED 改名

## §0 TL;DR

本 spec 在 v5.8 Sprint 1A-β（PA dispatch）階段一次性收口 3 件互相耦合的設計缺口：

1. **M11 三級 threshold 統計推導**（NOISE / WARN / CRITICAL）取代 v5.8 §2 M11 line 401-404 的 ad-hoc「PnL > $X / decision count > Y / slippage > Z bps」字面占位；基線 = 5d empirical noise floor + 2.5σ / 3σ 統計覆蓋。
2. **M11 ↔ M7 dedup contract**：M11 daily divergence event 是 **input to M7**，不獨立 demote；M7 為 single decay authority。配合 H-8 multi-module trigger mutual exclusion contract 防止雙 demote 反模式。
3. **M7 STAGE_DEMOTED → DECAY_ENFORCED 改名**：原字串含「STAGE」與 AMD-2026-05-15-01 Stage 0/0R/1/2/3/4 + ADR-0034 LAL 0/1/2/3/4 字面碰撞；改名同步 V113 schema column `decay_stage` → `decay_action_level`。

3 件改動均**僅落 spec 級**；V107（M11 replay divergence）與 V113（M7 decay）schema 實檔由 CR-8 sub-agent 在 dispatch 階段獨立 land；v5.8 主檔 §2 由主會話 CR-7 統一收口。

---

## §1 Background

### §1.1 v5.8 §2 M11 threshold ad-hoc 風險

v5.8 §2 M11 line 401-404 字面列：

```
4. Flag divergences:
   - PnL divergence > $X
   - Decision count divergence > Y
   - Slippage divergence > Z bps
```

`$X / Y / Z` 是占位符。若 dispatch 不收口：

- 各 sub-agent（PA / E1 / E4）IMPL 階段各自填數，cohort-level threshold 不一致 → false positive 不可控、無 statistical robustness。
- 5 策略（C10 grid / Unlock / Pairs / C13 / Funding short）vol scale 差 5-10×；單一絕對 bps threshold 對 grid 低 vol 過敏、對 bb_breakout 高 vol 不敏 → 違 §二 #12「行為演化基於證據」。
- QC 5.21 v5.8 audit Risk 3 已 catch：「3 個 threshold 純 ad-hoc + 與 M7 30d Sharpe 信號重複 60-70%」。

### §1.2 v5.8 §2 M7 demote authority 與 M11 信號重疊

v5.8 §2 M7 列 4 個 decay 信號源：

```
- Rolling 30d Sharpe < threshold
- Drawdown exceeds Stage 4 envelope max
- N consecutive losing trades > 2σ historical max
- Counterfactual replay (M11) shows strategy underperforming baseline by ≥ X bps
```

第 4 條已聲明 M11 是 M7 input。但 v5.8 §2 M11 line 406-410「Use cases」同時列 M11 自身可 trigger M3 HEALTH_WARN + 提供 M7/M8 input。若 M11 與 M7 各自獨立 demote → QC empirical via M11 simulation 顯示信號重疊 60-70% → **alert fatigue + 雙 demote 反模式**。

### §1.3 v5.8 §2 M7 STAGE_DEMOTED 字面碰撞

v5.8 §2 M7 line 264-268 列 state machine：

```
STAGE_LIVE → DECAY_DETECTED → STAGE_DEMOTE_PROPOSED → STAGE_DEMOTED
```

QC + FA + QA 5.21 audit 共識：

- `STAGE_DEMOTED` 字面含「STAGE」三字 → 與 AMD-2026-05-15-01 Stage 0/0R/1/2/3/4（demo / canary promotion gate）+ ADR-0034 LAL 0/1/2/3/4（Decision Lease Layered Approval）字面碰撞 → SQL query / Rust state enum / dashboard 標籤跨領域混用時 ambiguous。
- 同 LAL 改名理由（將「Tier」→「Layer」避 Decision Lease Tier 混淆），M7 demote state 改名 `DECAY_ENFORCED` 字面語意清楚對應「decay action」域、不與 Stage 字面互覆。

---

## §2 M11 Threshold 統計推導

### §2.1 5d empirical baseline 計算

| 元素 | 設計 |
|---|---|
| 樣本窗 | 過去 5 個 trading day 的 M11 nightly replay divergence distribution |
| 樣本單位 | per (asset, strategy) pair；不跨 strategy 平均 |
| 統計量 | mean (μ) + std (σ) of Δ = `replay_pnl − live_pnl`（PnL divergence 主指標）；decision count / slippage 同樣 derive σ |
| 排除規則 | (a) M8 `anomaly_severity ≥ HIGH` 標記日；(b) Stage transition 日（promotion / demote / pause）；(c) liquidity halt / exchange-side outage 日 |
| 排除為什麼 | (1) anomaly day Δ 在 noise 統計中是 contamination（fat tail right-skew）→ μ + σ 都會被拉高 → 真實 noise floor 被掩蓋 (2) Stage transition 當日 sizing 結構性變化 → Δ 來自策略本身而非 replay drift (3) outage 日 live 不執行而 replay 跑空 → Δ 本質上是 missing data 非 divergence |

### §2.2 三級 threshold（per ADR-0038 Decision 3）

| 級別 | Threshold | 統計覆蓋 | 預期觸發頻率 | 行為 |
|---|---|---|---|---|
| **NOISE floor** | μ + 0.5σ | 約 66%（正態 inside ±0.5σ）| 每月 ~10 次 / strategy | **不記 log**（避免 V107 表灌爆 daily noise）|
| **WARN** | μ + 2.5σ | 約 99.4%（單尾 outside +2.5σ ≈ 0.6%）| 每月 ~2 次 / strategy | emit `replay_divergence_log` with `divergence_level='WARN'` + Slack daily digest；**不打斷 nightly run**；**不獨立 trigger M7 decay**（只 feed M7 為候選 input）|
| **CRITICAL** | μ + 3.0σ | 約 99.7%（單尾 outside +3σ ≈ 0.27%）| 每月 ~0.7 次 / strategy | emit log + Slack immediate alert + **升級為 M7 input** + **可觸發 M3 HEALTH_WARN**（per CR-7 contract）；仍**不獨立 demote**，per §3 dedup contract |

### §2.3 為什麼採 σ 而非絕對 bps

- 5 策略 vol scale 差異顯著：grid daily PnL volatility ≈ $1-3 / bb_breakout / Unlock ≈ $10-30；若用統一絕對 bps threshold（如「PnL divergence > $5」）：
  - grid 觸發頻率被高估 → false positive 灌爆
  - bb_breakout 高 vol 真 divergence 被吸收進 noise → false negative
- σ-based threshold 自適應 strategy 真實 noise structure → 每策略獨立校準
- 並對齊 ADR-0038 Decision 3「為什麼用 σ 而非絕對 bps」(line 120) 立場一致

### §2.4 為什麼採 5d rolling baseline 而非 1d / 30d

| 候選 | 拒絕理由 |
|---|---|
| 1d (N=1) | 樣本量不可靠；單日 outlier 即構成全部 baseline；不適合 σ 計算 |
| 5d (N=5) | nightly job 每日 1 run × 5d = 5 sample；對 regime shift react quick（5d 滾動）；σ 可信但對 anomaly day 仍敏感 → 配合 §2.1 排除規則處理 |
| 30d (N=30) | 樣本量大但 lag 大；regime shift detection 偏弱；crypto regime 可能 5-10d 完整轉換 → 30d baseline 在 regime shift 後仍包含 stale noise |

**選 5d**：在 sample reliability vs regime responsiveness 之間 best 折衷；與 ADR-0038 §Decision 3 line 113 「5d rolling mean Δ」對齊。

### §2.5 cold start 處理

| 場景 | 行為 |
|---|---|
| 新 strategy 首 5 日（baseline 樣本不足）| **不**從 vendor backfill 補洞（per ADR-0038 Decision 1 例外條款）；用 degraded sample（N < 5）並在 `replay_divergence_log.flags` 標 `cold_start=true`；threshold 暫採全 cohort median μ + σ 作為 proxy；Slack warn 但不阻 nightly run |
| 排除規則命中超過 50% 樣本（baseline 不可信）| 同 cold_start 處置；額外加 `noise_floor_unstable=true` flag；CRITICAL 降級為 WARN 直到 baseline stable |

---

## §3 M11 ↔ M7 Dedup Contract

### §3.1 Authority 邊界

| Module | 角色 | 不可做 |
|---|---|---|
| **M11** | counterfactual replay engine + divergence detector + signal emitter | 不 trigger demote；不寫 `decay_signals` table；不改 strategy sizing；不調 capital allocation |
| **M7** | sole decay authority；ingest signals from M11 + own signals | 不 own replay；不寫 `replay_divergence_log` table |

### §3.2 Signal Flow

```
┌────────────── M11 Nightly Replay (cron T+0 UTC night) ──────────────┐
│                                                                       │
│  pull 24h market data (self-hosted PG only, per ADR-0038 Decision 1) │
│  run 5 strategies replay → compare with live fills                    │
│  compute Δ = replay − live (PnL / decision_count / slippage)         │
│                                                                       │
│  evaluate against 5d baseline (per §2.1-§2.2)                        │
│       │                                                               │
│       ├── Δ < μ + 0.5σ  → NOISE     (silent, no log)                 │
│       ├── Δ < μ + 2.5σ  → (still within noise band, no log)          │
│       ├── Δ ≥ μ + 2.5σ  → WARN      (log + Slack digest)             │
│       └── Δ ≥ μ + 3.0σ  → CRITICAL  (log + immediate alert)          │
│                                                                       │
│  WARN/CRITICAL → write learning.replay_divergence_log                │
│                  + emit signal to M7 ingestion queue                  │
│  CRITICAL only → also emit M3 HEALTH_WARN (per CR-7)                 │
│                                                                       │
└───────────────────────────────────────────────────────────────────────┘
                              │
                              │ signal (read-only ingestion)
                              ▼
┌────────────── M7 Decay Detector (cron T+0 UTC + 1h) ─────────────────┐
│                                                                       │
│  ingest signals:                                                     │
│    (1) M11 divergence WARN/CRITICAL events (this nightly window)     │
│    (2) own: rolling 30d Sharpe < strategy-specific threshold          │
│    (3) own: drawdown > Stage 4 envelope max                          │
│    (4) own: N consecutive losing trades > 3σ historical (QC tighten   │
│        from v5.8 §2 M7 line 261 的 2σ → 3σ for fat tail crypto)      │
│                                                                       │
│  multi-source confirmation (≥ 2 signal sources triggered) →          │
│       transition: NORMAL_LIVE → DECAY_DETECTED                       │
│                                                                       │
│  single-source signal (1 of 4) → DRAFT advisory only, no transition  │
│                                                                       │
│  single decision output: { NORMAL_LIVE | DECAY_DETECTED |             │
│                            DECAY_ENFORCED | RETIRED }                 │
│                                                                       │
└───────────────────────────────────────────────────────────────────────┘
```

### §3.3 V107 schema 必不包含 demote field

per CR-8 sub-agent 在 V107 land 階段必須遵守：

```sql
-- learning.replay_divergence_log columns (必含)
divergence_level   text NOT NULL CHECK (divergence_level IN ('WARN','CRITICAL'))
delta_pnl_usd      numeric(20,6) NOT NULL
delta_decisions    integer NOT NULL
delta_slippage_bps numeric(10,4) NOT NULL
baseline_mu        numeric(20,6) NOT NULL
baseline_sigma     numeric(20,6) NOT NULL
sigma_multiplier   numeric(4,2) NOT NULL  -- 實際觸發的 σ 倍率
flags              jsonb            -- cold_start / noise_floor_unstable 等

-- 禁止欄位（CR-8 sub-agent 須拒絕任何引入以下欄位的 PR）
-- auto_demote        BOOLEAN   ❌
-- target_state       TEXT      ❌
-- demote_proposal_id BIGINT    ❌
```

對應 SQL constraint：

```sql
CHECK (divergence_level IN ('WARN','CRITICAL'))
-- 不允許 'DEMOTED' / 'RETIRED' / 任何 M7 state 字面值
```

### §3.4 為什麼避雙 demote — H-8 mutual exclusion contract 應用

FA 5.21 audit Risk 3 已 catch「M3 / M8 / M11 風控三 module trigger 邊界 overlap」。本 spec 應用 H-8 contract 於 M11 ↔ M7：

| 場景 | 反模式 | 本 spec 處置 |
|---|---|---|
| 同 strategy 同日同時被 M11 CRITICAL + M7 30d Sharpe 觸發 demote | M11 + M7 各自寫 `decay_signals` → audit log 雙 entry + recovery path 模糊 | M11 只 emit signal；M7 ingest signal + 自身 3 signal source 一起 multi-source confirm → 單一 transition |
| 隔 1h M11 → M7 兩步信號鏈 | M11 已 demote、M7 後追加 demote | M11 結構上**不可 demote**（V107 無 demote field）；只有 M7 寫 transition |
| recovery 時 M11 stale signal 滯留 | M7 promote 回 NORMAL_LIVE 但 M11 仍 emit historical CRITICAL | M7 在 promote 時必須 acknowledge M11 last-N signals 為「stale post-recovery」；M11 signal TTL = 14d（與 §4 review window 對齊）|

Single authority pattern 帶來的 traceability：

- 任一 demote 都能追溯到唯一一筆 `decay_signals.transition_id`
- recovery path 單一 entry：M7 RECOVERY → NORMAL_LIVE
- E4 regression 只需測 M7 state machine，無需測 M11 state（M11 無 state）

---

## §4 M7 STAGE_DEMOTED → DECAY_ENFORCED 改名

### §4.1 為什麼改名

| 比較 | STAGE_DEMOTED | DECAY_ENFORCED |
|---|---|---|
| 字面語意 | 「Stage 被降級」— 含「Stage」字眼 | 「衰減已強制」— 直接對應 M7 decay action 域 |
| 跨域字面碰撞 | 與 AMD-2026-05-15-01 Stage 0/0R/1/2/3/4 + ADR-0034 LAL 0/1/2/3/4 字面重疊 | 無碰撞 |
| SQL query | `WHERE state = 'STAGE_DEMOTED'` 在 ETL / dashboard 易與 `stage_history.stage = 'Stage 1'` 邏輯混淆 | `WHERE state = 'DECAY_ENFORCED'` 語意自明 |
| Rust enum | `enum DecayState { StageLive, DecayDetected, StageDemoteProposed, StageDemoted }` 半域名沾染 | `enum DecayState { NormalLive, DecayDetected, DemoteProposed, DecayEnforced, Retired }` 純域 |

### §4.2 V113 schema column rename

per CR-8 sub-agent 在 V113 land 階段必須執行：

```sql
-- V113 spec doc 必含 column rename + CHECK constraint 改寫

ALTER TABLE learning.decay_signals
  RENAME COLUMN decay_stage TO decay_action_level;

-- 舊 CHECK constraint（v5.8 §2 M7 字面命名）
-- CHECK (decay_stage IN ('STAGE_LIVE','DECAY_DETECTED',
--                        'STAGE_DEMOTE_PROPOSED','STAGE_DEMOTED','RETIRED'))

-- 新 CHECK constraint（本 spec rename 後）
ALTER TABLE learning.decay_signals
  DROP CONSTRAINT IF EXISTS decay_signals_decay_stage_check;

ALTER TABLE learning.decay_signals
  ADD CONSTRAINT decay_signals_decay_action_level_check
  CHECK (decay_action_level IN (
    'NORMAL_LIVE',
    'DECAY_DETECTED',
    'DEMOTE_PROPOSED',
    'DECAY_ENFORCED',  -- 替換原 STAGE_DEMOTED
    'RECOVERY',        -- 顯式 transition entry（v5.8 §2 M7 只列「RECOVER」隱式）
    'RETIRED'
  ));
```

### §4.3 M7 state machine 改寫

```
NORMAL_LIVE
   │ (multi-source signal confirm: ≥ 2 of [M11 CRITICAL, 30d Sharpe<thr,
   │   DD>envelope, N consecutive losing>3σ])
   ▼
DECAY_DETECTED
   │ (Allocator generates demote proposal; per §五 architecture)
   ▼
DEMOTE_PROPOSED
   │ (operator approve OR LAL 1 auto-approve via M1, per ADR-0034)
   ▼
DECAY_ENFORCED  ←─────── (live size scaled to 50% pending 14d review)
   │
   ├── 14d review window → recovery criteria pass → RECOVERY → NORMAL_LIVE
   │
   └── 14d review window → recovery criteria fail → RETIRED (size = 0)
```

關鍵語意對齊：

- **DEMOTE_PROPOSED**（取代 v5.8 `STAGE_DEMOTE_PROPOSED`）— 仍是 transition 中間 state，等待 operator / LAL 1 approval
- **DECAY_ENFORCED**（取代 v5.8 `STAGE_DEMOTED`）— terminal action state，size scaled，進入 14d observation
- **RECOVERY** 顯式登場（v5.8 line 269 只列「RECOVER」隱式）— 對應 M7 14d 結束時 promote 回 NORMAL_LIVE 的 transition entry
- **RETIRED**（與 v5.8 line 269 一致）— size = 0，終態

### §4.4 改名 search/replace 影響範圍

| 範圍 | 字面 | 改動方 | 時機 |
|---|---|---|---|
| v5.8 主檔 §2 M7 line 264-269 | `STAGE_DEMOTED` × 2 / `STAGE_DEMOTE_PROPOSED` × 1 / `STAGE_LIVE` × 1 | 主會話 CR-7 統一收口 | Sprint 1A-β dispatch 階段 |
| V113 spec doc placeholder | column name + ENUM 6 值 | CR-8 sub-agent | Sprint 1A-β dispatch 階段 |
| ADR M7（per R4 H-9 建議補）| M7 ADR draft 引述舊 state name | 新 ADR-XXXX M7 Decay Detection 落地時 reflect | 主會話 H-9 land 路徑 |
| Rust enum 引用 | `StageDemoted` / `StageDemotePoposed` 等 PascalCase | E1 Sprint 8 IMPL | Sprint 8（M7 detector IMPL） |
| Python state string 引用 | `'STAGE_DEMOTED'` 等字串字面 | E1 Sprint 8 IMPL | Sprint 8 |
| Dashboard label / Slack template | 「降級」「Stage demote」中文 / 英文 label | TW Sprint 8 | Sprint 8 GUI 落地階段 |

**Sprint 1A-β 不觸及 code-level rename**；本 spec land 的只是 schema + spec + ADR 設計面 rename，code IMPL 在 Sprint 8 才出現。

---

## §5 M11 Divergence severity 4 級對齊 M8 anomaly severity

per CR-15 5-gate auto path inheritance + 治理紀律統一（per QC + FA 5.21 audit must-fix），M11 severity 必須能映射到 M8 anomaly severity taxonomy，便於 downstream M3 health gate / Slack routing 一致。

| M11 divergence level | M8 `anomaly_severity` 對齊 | M7 action | M3 action |
|---|---|---|---|
| NOISE | `INFO` | none | none |
| WARN | `WARN` | feed M7 signal (decay candidate, 1-of-4 source) | none |
| CRITICAL | `CRITICAL` | feed M7 signal (1-of-4 source; strong evidence) | trigger M3 HEALTH_WARN（per CR-7） |
| —（未定義 HALT 級）| `HALT` | reserved for future Y2+ correlation-break preemptive halt（per v5.8 §2 M8 line 305-306）| reserved |

對齊好處：

- M3 / M8 / M11 三 module 共享 severity vocabulary → dashboard label 統一 / Slack template 復用 / E4 regression case matrix 收斂
- 未來 M11 IMPL 發現新異常級別（如 strategy 完全停轉 0 fills）可升 HALT 級而不破壞既有 enum

---

## §6 Engineering Phasing

| Sprint | 任務 | 工時估 | 依賴 |
|---|---|---|---|
| **Sprint 1A-β DESIGN（本 spec）** | V107 schema (M11) + V113 schema (M7 DECAY_ENFORCED rename) + ADR-0038 M11 已 land + ADR M7（per R4 H-9 補）draft | spec only（本 spec 0.5d）| — |
| **Sprint 3** | M11 nightly job IMPL：5d baseline 計算 + 3 threshold 評估 + replay_divergence_log writer | 60-80 hr | V107 land + Stage 0R replay infra（existing v5.7 §6 baseline）|
| **Sprint 5** | M11 → M7 hookup：signal ingestion API + dedup contract enforcement（M11 不寫 decay_signals 之 unit test）| 20-30 hr | Sprint 3 nightly job stable |
| **Sprint 8** | M7 IMPL：decay detector + 4 signal source ingestion + DECAY_ENFORCED state machine + 14d review window | 60-80 hr | Sprint 5 hookup contract enforced |
| **Sprint 10** | LAL 1 auto-demote enablement：LAL 1 auto-approve 30d stable strategy decay 處理（per ADR-0034 Decision 3 Y1 LAL 1 = opt-in conditional）| 30-40 hr | Sprint 8 + LAL 1 production-ready |

**Sprint 1A-β（本 spec）總成本** = spec doc only；不含實檔 SQL（CR-8）+ 不含 ADR M7 draft（R4 H-9）。

---

## §7 Anti-pattern Detection（PA dispatch 階段 sub-agent checklist）

PA 在 dispatch Sprint 1A-β 子任務時必納入以下 grep 紀律於 sub-agent 自審 + E2 review：

### §7.1 STAGE_DEMOTED 字面殘留檢測

```bash
# 在 v5.8 主檔 + 任何 Sprint 1A-β 新 spec / ADR / amendment 中
rg -n 'STAGE_DEMOTED|STAGE_DEMOTE_PROPOSED|STAGE_LIVE' \
   srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md \
   srv/docs/execution_plan/2026-05-21--*.md \
   srv/docs/adr/ \
   srv/docs/governance_dev/amendments/

# 預期：v5.8 主檔 §2 M7 改寫後 0 hit；CR-7 收口後本 spec 與 ADR M7 為唯一 reference point
# 若 hit ≠ 0 → sub-agent 必返回 PA「STAGE_DEMOTED 殘留」push back，要求改為 DECAY_ENFORCED
```

### §7.2 M11 schema demote field 反模式檢測

```bash
# V107 spec 與 IMPL PR 中
rg -n 'auto_demote|target_state|demote_proposal_id|decay_stage|stage_demoted' \
   srv/docs/execution_plan/*v107* \
   srv/migrations/*V107*.sql 2>/dev/null || true

# 預期：V107 land 後 0 hit on M11 schema
# 若 hit ≠ 0 → sub-agent 拒絕 PR（V107 為 M11 schema，不可含 demote field；違 §3.3）
```

### §7.3 hard-coded threshold 反模式檢測

```bash
# Rust / Python code base 中
rg -n 'm11_threshold|m11_divergence_threshold|0\.5\s*\*\s*sigma|2\.5\s*\*\s*sigma|3\.0\s*\*\s*sigma' \
   srv/program_code/ \
   srv/openclaw_engine/

# 預期：threshold 必走 V107 schema column（baseline_mu / baseline_sigma / sigma_multiplier）動態計算
# 若 hit ≠ 0 → sub-agent 返回 E1「hard-coded threshold」push back；threshold 必須來自 5d rolling baseline 計算結果
```

### §7.4 M7 single authority 反模式檢測

```bash
# 確認 M11 path 不直接 mutate decay_signals
rg -n 'INSERT INTO learning\.decay_signals\|UPDATE learning\.decay_signals' \
   srv/program_code/ \
   srv/openclaw_engine/

# 預期：只有 M7 module path 出現；M11 module path（replay engine / divergence detector）0 hit
# 若 M11 path hit ≠ 0 → sub-agent 返回 E1「M11 violated single authority contract」；M11 只 emit signal 不 mutate decay state
```

---

## §8 Cross-References

| 文件 | 對應段落 / 議題 |
|---|---|
| `srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md` | §2 M7 (line 253-277) + §2 M11 (line 391-423) — 本 spec 直接收口對象 |
| `srv/docs/adr/0038-m11-continuous-counterfactual-replay-and-liquidations-source.md` | CR-14 已 land；本 spec §2 threshold 推導對齊 ADR-0038 Decision 3 |
| `srv/docs/adr/0034-decision-lease-layered-approval-lal.md` | LAL 0/1/2/3/4 字面碰撞參考；LAL 1 為 Sprint 10 auto-demote authority |
| `srv/docs/governance_dev/amendments/2026-05-15--AMD-2026-05-15-01-canary-rebase-replay-preflight-demo-micro-canary.md` | Stage 0/0R/1/2/3/4 字面碰撞參考 |
| `srv/docs/CCAgentWorkSpace/QC/workspace/reports/2026-05-21--v58_executability_audit.md` | QC Risk 3「M11 ad-hoc threshold + M7 信號重複 60-70%」must-fix；本 spec 收口 |
| `srv/docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-21--v58_executability_audit.md` | FA Risk 3「M3 / M8 / M11 trigger overlap」+ M11 PARTIAL acceptance「divergence threshold 數字待補」must-fix；本 spec 收口 |
| `srv/docs/execution_plan/2026-05-21--sprint_1a_dispatch_packet.md` | PA Sprint 1A-β dispatch 主檔；CR-7（M11+M7 dedup contract）+ CR-8（V107/V113 schema placeholder land）執行入口 |
| `.claude/skills/walk-forward-validation-protocol/` | M11 nightly replay 採用「leak-free shift(1) + rolling baseline」紀律參考 |
| `.claude/skills/crypto-microstructure-knowledge/` | 5 策略 fat tail 特性 → 為什麼 §3.2 「N consecutive losing > 3σ」而非 v5.8 §2 M7 line 261 的 2σ |
| H-8 trigger mutual exclusion contract（FA 提出，主會話 H-9 land 路徑）| §3.4 雙 demote 反模式應用此 contract |
| CR-7（PA dispatch consolidation §1 CR-7）| M11+M7 dedup contract 在 v5.8 §2 主檔的收口入口 |
| CR-8（PA dispatch consolidation §1 CR-8）| V107 / V113 schema placeholder land 入口；本 spec 為 schema 設計面 reference |

---

## §9 Sign-off Table

| 角色 | 狀態 | 備註 |
|---|---|---|
| **MIT** | DRAFTED | 主撰寫；M11 threshold 統計推導 + M7 dedup contract + DECAY_ENFORCED rename 三件耦合 |
| **QC consultant** | DRAFTED | 對 §2 σ 推導 + §3 multi-source confirm + §5 severity alignment 提供統計與 graveyard filter 紀律 |
| **TW** | DRAFTED | 中文為主敘述 + 英文技術名詞輔；對齊 ADR-0038 風格；無 emoji |
| **PA** | PENDING | 等 V107 / V113 schema placeholder land + Sprint 1A-β dispatch 對應子任務 sub-agent 完成 |
| **E4** | PENDING | M11 nightly job harness 規劃前，先確認 §3.2 signal flow + §3.3 V107 schema constraint 對 IMPL 階段可測 |
| **QA** | PENDING | 4 級 severity alignment（§5）對 M8 anomaly_severity taxonomy audit；確認 M11 / M3 / M8 共享 severity vocabulary 對 audit trail 一致 |
