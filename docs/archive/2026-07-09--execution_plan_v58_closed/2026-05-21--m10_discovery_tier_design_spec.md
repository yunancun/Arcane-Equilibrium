---
spec: M10 — Discovery Tier (Capital-Triggered Strategy Discovery Tier Ladder) DESIGN
date: 2026-05-21
author: PA (M10 module design spec; Sprint 1A-γ DESIGN prereq)
phase: v5.8 Sprint 1A-γ DESIGN — IMPL 後續 sprint
status: SPEC-DESIGN-V0 (PA 起草;待 MIT V111 full DDL alignment + QC/FA cross-V### + PM sign-off 後 SPEC-FINAL)
sprint: Sprint 1A-γ DESIGN(本 spec)→ Sprint 1A-γ V111 IMPL → Sprint 4+ M10 gate Rust IMPL → Y2 Tier B/C activation → Y3+ Tier D/E activation
size estimate: ~500 lines design spec + 70-110 hr E1 IMPL(V111 schema 30-50 hr + Tier-gate Rust module Sprint 4+ 40-60 hr)
depend on:
  - ADR-0036 (M8 anomaly detection + M10 Tier D model blacklist HMM/Markov/GARCH 永久禁用;ATR-vol + funding 9 cell 替代)
  - V112 (M1 Decision Lease LAL tiers; tier change 走 LAL 3-4 operator approval/attestation 路徑)
  - V106 (M3 health observations; HEALTH_DEGRADED → tier 降階 source)
  - V091 (P0 portfolio_var.usdt_var_15m as `capital_observed_usdt` proxy)
  - V098 (governance.audit_log; activation evidence cross-ref)
depended by:
  - M6 reward (tier 影響 weight allocation prior;ARG-0021 R-2 Strategist + Sprint 7 Advisory Allocator)
  - M3 health (DEGRADED 自動 demote tier 一階)
  - M9 A/B framework (ATR-vol+funding cell stability metric Y2+ feed M9 promotion evidence)
  - M11 replay (tier transitions 必 replay 重放;reproducibility check)
parent specs:
  - srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md §2 M10 Discovery Tier(line 364-389)
  - srv/docs/adr/0036-m8-anomaly-detection-and-m10-tier-d-model-blacklist.md(Tier D 黑名單 + 9 cell matrix)
  - srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md §1 CR-5 + §6 cross-V###
mirror precedent:
  - srv/docs/execution_plan/2026-05-21--m1_lal_layered_approval_lease_design_spec.md(M1 LAL design spec; LAL 0-4 範式)
  - srv/docs/execution_plan/2026-05-21--v112_m1_decision_lease_lal_tiers_schema_spec.md(V112 full DDL 範式)
  - srv/docs/execution_plan/2026-05-21--v103_v104_earn_hypotheses_schema_spec.md(14 section structure 範式)
scope: design / spec only — 不寫 V111.sql 實檔(V111 spec 另寫)、不寫 Rust tier-gate IMPL、不在 Mac 跑 SQL、不改 trading.fills writer、不執行 PG
---

> **REFERENCE / FROZEN AUTONOMY MODULE SPEC**
>
> 本 spec 保留 v5.8 Sprint 1A module design lineage。当前 active-IMPL 以
> `TODO.md` 和最新 PM/role reports 为准；不得仅凭本 spec 派发 tier activation、
> capital-threshold 或 strategy-discovery runtime work。

# M10 Discovery Tier — Capital-Triggered Strategy Discovery Tier Ladder DESIGN

## §0 TL;DR

- **M10 是 strategy discovery tier**:依當下 **capital threshold** 決定哪些 strategy archetype 可以 active;capital 不足時不允許上線高容量需求策略(防小資金套大策略過度倉位)。
- **5 級 Tier A → E**(A 最寬 / E 最嚴);Y1 限 A;Y2 開 A+B+C;Y3+ 開 +D+E;對齊 v5.8 §2 M10 ladder。
- **7 級 capital threshold trigger**($500 / $2k / $10k / $30k / $50k / $100k / $500k 7 個 step);per-tier 對應 sustained-AUM 入門條件。
- **Tier D 黑名單 hardening per ADR-0036**:Tier D regime auto-classify **永久禁用 HMM / Markov-switching / GARCH**;**唯一允許 = ATR-vol × Funding-state 雙 axis 3×3 = 9 cell matrix**。
- **Activation log audit append-only**:每次 tier transition / capital threshold cross 落 `governance.discovery_tier_activations` ledger(hypertable;30d compress / 180d retention)。
- **M10 ↔ M1 LAL 對齊**:**tier change is governance event** — A→B + B→C 走 **LAL 2(cross-strategy reweight + Y2 gate + Console opt-in)**;C→D + D→E 走 **LAL 3(operator approval)**;capital structure 改 reserve allocation 走 **LAL 4(operator attestation + 2FA + 0 clawback)**;對齊 ADR-0034 LAL 0-4「數字越大越嚴」方向。
- **M10 ↔ M6 reward**:tier 是 weight allocation prior;Tier A → 5 既有策略 baseline weight;Tier B → +parameter sweep variants;Tier C → +cointegration/pairs;Tier D → 9 cell regime-specific reweight;Tier E → multi-strategy portfolio overlay。
- **M10 ↔ M3 health**:M3 emit `HEALTH_DEGRADED` → M10 自動 demote tier 一階(走 LAL 1 reparam halt;不需 operator 確認 — fail-closed)。
- **反向 attack mitigation**:operator override 繞 LAL 4 attestation = 違反 AMD-2026-05-21-01 5-gate;tier 升級不可走 hot-edit `discovery_tier_config` SQL,必走 V### migration + governance audit。
- **Schema V111**:2 table(`governance.discovery_tier_config` 5 row config + `governance.discovery_tier_activations` hypertable ledger);per V103/V112 範式 + Guard A/B/C + Linux PG dry-run mandate。

---

## §1 Context

### 1.1 v5.8 §2 M10 module 出處

v5.8 §2 M10 Discovery Tier module(line 364-389)列:

| Tier | 容量門檻(sustained AUM)| 容許 strategy archetype | activation year |
|---|---|---|---|
| **A** | ≥ $500(min viable trading capital)| 5 既有策略(grid / ma / bb_breakout / bb_reversion / funding_arb)| **Y1**(default) |
| **B** | ≥ $10k | A + parameter sweep variants(per-strategy sweep grid) | **Y2** |
| **C** | ≥ $30k | B + 1 cointegration / pairs trading 新策略 | **Y2** |
| **D** | ≥ $50k | C + regime-adaptive(per ADR-0036 ATR-vol+funding 雙 axis 9 cell)| **Y3+** |
| **E** | ≥ $100k | D + multi-strategy portfolio overlay + cross-asset rebalance | **Y3+** |

v5.8 ladder 設計核心:**小資金不上大策略;大資金時逐級開啟 archetype 多樣性**。防御:
- ❌ 小資金套高容量需求策略 → 倉位過度集中 + 流動性不夠 + 風險爆裂
- ❌ 跳級活化 → tier transition 無 sample 適應期 → operator 看不見證據盲跳
- ❌ Tier D 無證據用 HMM/GARCH 等 black-box regime → academic-toy replication crisis 重演

### 1.2 為什麼是 capital threshold driven(非 PnL / Sharpe driven)

per v5.8 §2 M10 + Sprint 7 Advisory Allocator + MIT memory baseline:

| 替代驅動 | 棄因 |
|---|---|
| **PnL-driven**(累積盈虧 trigger tier 升)| 易被 lucky streak 誤觸發;PnL 不反映 strategy capacity / liquidity headroom |
| **Sharpe-driven**(rolling Sharpe trigger tier 升)| Sharpe 噪音大;短窗口 high Sharpe 可能是 high vol period spike |
| **Trade count-driven** | 與 capacity 解耦;low capital + high trade count 仍會被高容量策略坑 |
| **Capital threshold driven**(採用)| **AUM 是 capacity 的最直接 proxy**;capacity = liquidity * AUM 是 academic alpha-capacity 文獻共識(Berk-Green 2004)|

### 1.3 為什麼用 sustained AUM(non-spike)

7d moving AUM trigger 必持續 ≥ 30d 才算 sustained;30d 防御:
- 加倉 spike(operator 一次性 deposit → AUM 暫破 threshold → tier 升 → 1d 後 withdraw → tier 降)→ flap
- demo / paper virtual capital 不算(`engine_mode IN ('live','live_demo')` 才算)

### 1.4 與 M10 placeholder v0 既有差異

V111 placeholder v0 採用 schema 字段集:`learning.discovery_tier_config` / `learning.capital_triggers`(2 表 learning schema)。

本 spec 對齊 operator prompt 採用 schema:`governance.discovery_tier_config` / `governance.discovery_tier_activations`(2 表 governance schema)。

**理由**:
- M10 tier change 是 **governance event**(approval + audit + clawback governance 行為),非 ML learning observation
- 對齊 V112 LAL tiers 同 schema(`governance.lease_lal_*`)
- 對齊 §二 原則 2 「讀寫分離;research, GUI, and learning are mostly read-only」— governance write 屬 governance schema 而非 learning

V111 placeholder v0 字段集差異:
- placeholder 用 `learning.capital_triggers` PK = `BIGSERIAL trigger_id` + 11 column;本 spec 採 `governance.discovery_tier_activations` PK = `BIGSERIAL id` + 包含 `tier_from`/`tier_to`/`capital_observed_usdt` + 對齊 V112 5 audit field

placeholder v0 全廢棄;本 spec full DDL 為單一真實來源。

### 1.5 為什麼必須在 Sprint 1A-γ DESIGN 階段 land

per PA dispatch consolidation report `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md` §1 CR-5:
- M10 Tier D 進入 Sprint 1A-γ IMPL DESIGN 時,本 DESIGN spec 必須 land 否則 V111 IMPL writer 無 ground truth
- ADR-0036 Tier D 黑名單 + 9 cell 矩陣 spec 必在 V111 schema CHECK constraint 反映
- M10 ↔ M1 LAL 跨 module 對齊必須明示否則 LAL 2/3/4 gate 派工會錯誤

---

## §2 Tier A → E 5 級 Ladder(對應 strategy archetype + capacity 門檻)

### 2.1 Tier 對齊表

| Tier | Activation Year | Capital threshold(sustained 30d)| 容許 strategy archetype | Weight allocation prior |
|---|---|---|---|---|
| **A** | Y1 default | ≥ **$500** | 5 既有策略(`grid` / `ma` / `bb_breakout` / `bb_reversion` / `funding_arb`)| Sprint 1 default weight per ADR-0021 R-2 Strategist |
| **B** | Y2 | ≥ **$10k**(sustained 30d AUM)| A + per-strategy parameter sweep variants(grid-fine / grid-coarse / ma-fast / ma-slow / bb-tight / bb-wide 等)| sweep variant weight 從 0.2x baseline 起步;30d cohort evidence + LAL 2 gate 後升 |
| **C** | Y2 | ≥ **$30k**(sustained 30d AUM)| B + 1 cointegration / pairs trading 新策略(待 ASDS Sprint 2 蒐集 candidate)| pairs strategy 從 0.05x portfolio weight 起步;Stage 4 stable + LAL 2 後升 |
| **D** | Y3+ | ≥ **$50k**(sustained 30d AUM)| C + regime-adaptive(per ADR-0036 ATR-vol+funding 雙 axis 9 cell matrix)| cell-specific reweight per 3×3 matrix;cell stability metric ≥ 30 sample/cell 才生效 |
| **E** | Y3+ | ≥ **$100k**(sustained 30d AUM)| D + multi-strategy portfolio overlay + cross-asset rebalance | portfolio-level mean-var optimization;require LAL 3 operator approval per rebalance epoch |

### 2.2 為什麼 ladder 5 級(非 3 級或 7 級)

per QC v5.8 audit + Sprint 7 Advisory Allocator + 4 多角色 review:

| 分級 | 棄因 / 採用理由 |
|---|---|
| 3 級(only A / C / E) | 缺 B/D 中介 → capacity 從 $500 跳 $30k 後又跳 $100k,中間沒 stepping stone;operator 看不到 evidence 累積 trajectory |
| **5 級(A / B / C / D / E)**(採用)| **採用**;A→B(parameter sweep 多樣性)+ B→C(新 archetype)+ C→D(regime adaptive)+ D→E(portfolio overlay)4 個 transition 對應 4 個 distinctive expansion;capacity 對齊 $500 / $10k / $30k / $50k / $100k 5 個 step |
| 7 級(更多 sub-tier) | 過度細分;sample 量不足以驗證 sub-tier 之間差異;operator audit complexity 過高 |

### 2.3 為什麼 Y1 限 A / Y2 開 B+C / Y3+ 開 D+E

per v5.8 §2 M10 + Sprint 1 Foundation stage + Y2-Y3 expansion timeline:

- **Y1 限 A**:Foundation stage;5 既有策略 alpha 證據累積期;不開新 archetype 避免分散 sample 量
- **Y2 開 B+C**:Sprint 2 Alpha Tournament + Sprint 6 ASDS factory 出 strategy candidate 後;capacity 累積到 $10k+ 才有 statistical power 支持新 archetype
- **Y3+ 開 D+E**:Tier D 需 9 cell × ≥30 sample/cell = ≥270 regime cell-specific sample 才生效(per ADR-0036 cell stability metric);典型累積期 8-12 month;Tier E portfolio overlay 需 Tier D 證據先成立

---

## §3 Capital Threshold 7 級 Trigger

### 3.1 7 級 threshold 對應表

7 級 capital threshold trigger 設計成 **fine-grained step ladder**;每 step 對應一個明確的 tier transition gate 或 sub-tier transition opportunity:

| Step | Threshold | 觸發行為 | 對齊 Tier transition |
|---|---|---|---|
| 1 | **$500** | Tier A activation(default Y1)| — |
| 2 | **$2k** | Tier A → 增加 max position size 多 25%(per LAL 1 reparam)| A intra-tier param |
| 3 | **$10k** | **Tier A → Tier B** 解鎖(parameter sweep variants); LAL 2 gate | A → B |
| 4 | **$30k** | **Tier B → Tier C** 解鎖(cointegration pairs);LAL 2 gate | B → C |
| 5 | **$50k** | **Tier C → Tier D** 解鎖(9 cell regime adaptive);**LAL 3 operator approval**;Y3+ gate | C → D |
| 6 | **$100k** | **Tier D → Tier E** 解鎖(portfolio overlay);**LAL 3 operator approval**;Y3+ gate | D → E |
| 7 | **$500k** | Tier E intra-tier — Earn rebalance threshold + 跨 venue allocation evaluation;**LAL 4 attestation**(capital structure change)| E intra-tier |

### 3.2 為什麼 7 級(非 5 級或 10 級)

| 分級 | 棄因 / 採用理由 |
|---|---|
| 5 級(完全對應 5 tier) | 缺 sub-tier transition step($2k / $500k);A 內 + E 內無 expansion opportunity |
| **7 級**(採用)| **採用**;5 個 tier transition step + 2 個 intra-tier reparam step($2k + $500k);粒度足夠展示 capital growth trajectory |
| 10 級(更細)| 過度細分;每 step 的 evidence cost 不合理;operator review complexity 過高 |

### 3.3 為什麼用 $USDT 整數 BIGINT(非小數 NUMERIC)

per V103 EXTEND § + V112 § + db-schema-design-financial-time-series skill:
- AUM threshold 天然 round to USDT 整數($500 / $10k 等);不需 NUMERIC 8 小數精度
- BIGINT 節省 storage;hot-path query 速度快
- per-trade USDT amount 才用 NUMERIC(18,8)(對齊 V103 earn_movement_log)

### 3.4 為什麼 sustained 30d 而非 spike

per §1.3 + flap mitigation:
- 加倉 spike(operator 一次性 deposit → AUM 暫破 threshold → tier 升 → 1d 後 withdraw → tier 降)→ flap
- sustained 30d 防 spike;對齊 v5.8 §2 M10 ladder 條款
- AUM smoothing window = 7d moving average → 防 1d intraday spike;30d sustained → 防 short-term lucky streak

### 3.5 為什麼 capital threshold 在 demo 不 trigger

per CR-3 demo/live 隔離原則 + `feedback_demo_over_paper_for_edge`:
- demo virtual capital 不反映真實 AUM headroom
- demo AUM 跨 $10k 就升 tier B 會造成 mock-PASS;真實 live 接管後 capacity 對應不上崩
- engine_mode IN ('live','live_demo') 才算;`paper`/`demo`/`replay` 不算

---

## §4 Tier D 黑名單 Hardening per ADR-0036

### 4.1 黑名單 hardening 規則(對齊 ADR-0036 Decision 1)

per ADR-0036 Decision 1 + math-model-audit skill governance promotion:

| 元素 | 規範 |
|---|---|
| 黑名單範圍 | **HMM (Hidden Markov Model)** 含所有變形(HSMM/HHMM/Factorial HMM 等)/ **Markov-switching regression** 含所有變形 / **GARCH** 含所有變形(EGARCH/TGARCH/IGARCH/FIGARCH/Multivariate GARCH 等) |
| 適用範圍 | **任何 Tier D regime classifier**(M10);M8 anomaly detection;M4 hypothesis miner;**無例外** |
| Schema CHECK constraint | V111 `discovery_tier_config.regime_detection_method` CHECK 強制只允許 `'atr_vol_funding'`(主路徑)/ `'pelt_reserved'`(Y3+ ADR-debt)/ `'none'`(非 Tier D)— **HMM/GARCH/Markov-switching 全 hard reject**;違反 INSERT 必 RAISE |
| Sub-agent dispatch grep gate | PA + MIT + E2 必 `grep -rni 'hmm\|markov_switching\|garch'` 在 dispatch 前 + sub-agent IMPL DONE 後雙 round;任一 hit = 拒絕 + push back |
| Cargo dep 黑名單 | `garch-rs` / 任何 GARCH crate / 任何 HMM crate(Rust 端 default 不該有,但留條款防漂移)|
| Python requirements 黑名單 | `arch`(GARCH 主流 package)/ `hmmlearn` / `pomegranate` HMM submodule / `statsmodels.tsa.regime_switching` |
| 例外:read-only counterfactual analysis | 純 read-only counterfactual analysis(如 backtest 對照 HMM 是否真不工作、學術復現練習)允許 read-only run,但結果**不得寫 live state / 不得進入 strategy trigger / 不得進入 promotion evidence** |

### 4.2 為什麼用 ATR-vol × Funding-state 雙 axis 9 cell 替代

per ADR-0036 Decision 3.1 + §3.2 crypto 微結構 native feature 論證:

| Axis | 設計 | 為什麼 |
|---|---|---|
| **Axis 1: ATR-vol** | 3 級分類:**LOW / MID / HIGH** 基於 14-day ATR 對 90d distribution percentile(< 33% = LOW、33-66% = MID、> 66% = HIGH)| ATR 在 OpenClaw 既有 indicator pipeline 有 cache + 計算成本 < 1μs/symbol;volatility regime 是 position sizing / SL/TP 距離核心 driver |
| **Axis 2: Funding state** | 3 級分類:**CONTANGO / NEUTRAL / BACKWARDATION** 基於 funding rate cross-section(24h rolling mean funding rate < -0.005% = BACKWARDATION、-0.005% ~ +0.005% = NEUTRAL、> +0.005% = CONTANGO)| funding 是 crypto perp DNA(spot 沒有);funding sign + magnitude 直接反映 long/short imbalance + leverage stress + funding-arb opportunity |

### 4.3 為什麼 3×3 = 9 cell matrix(非 2×2 / 5×5)

per ADR-0036 Decision 3.3 + statistical power analysis:

| 分級 | 棄因 / 採用理由 |
|---|---|
| 2×2 = 4 cell | 失去 NEUTRAL / MID 信息;多數 trading hour 落在 MID regime,2×2 會把 50%+ 樣本 force 到 LOW 或 HIGH 偏一邊 |
| **3×3 = 9 cell**(採用)| **採用**;33/33/33 percentile split 樣本量平均;9 cell 語義人類可解讀 |
| 5×5 = 25 cell | Y1 樣本量 ~25k decisions 在 25 cell 矩陣下每 cell 平均 ~1000 sample,cell-specific allocation 統計噪音大;Y3+ Tier D 表現好 + AUM > $100k 時可考慮 amend 升 5 級 |

### 4.4 為什麼 Y3+ 才開放 Tier D activation

per ADR-0036 Decision 3.4 + statistical power requirement:

- **Cell stability metric**:Y1 樣本量 ~25k decisions / 9 cell ≈ ~2800 sample/cell(假設均勻);但實際非均勻 — MID-NEUTRAL 可能 > 50% 樣本,其他 cell 可能 < 1000 sample
- **Y3+ 累積期**:Tier D 開放需 9 cell × ≥30 sample/cell = ≥270 regime cell-specific sample 才生效;典型累積期 8-12 month;Y3 Q1 才有統計力
- **AUM trigger gate**:Tier D 需 ≥ $50k sustained AUM(per §3.1 step 5);Y1/Y2 多數情況不滿足

### 4.5 Y3+ PELT change-point detection 評估(ADR-debt)

per ADR-0036 Decision 3.4 — PELT (Pruned Exact Linear Time, Killick 2012) Y3+ ADR-debt:

| 元素 | 設計 |
|---|---|
| 評估時點 | Y3 Q1(Tier D activation 至少 2 cycle ≈ 8 month 樣本後)|
| 評估方法 | PELT on rolling realized return / vol series;對比 ATR-vol+funding 雙 axis 矩陣 |
| PELT 採用觸發條件 | PELT-detected change-point 對應的 regime allocation 在 OOS demo 21d 累積 alpha **≥ +1% absolute** vs ATR-vol+funding 雙 axis 矩陣同期 |
| 不採立即 Y2 | (a) PELT 計算成本比 ATR percentile 高 ~10x,Y1/Y2 hot path budget 緊;(b) Y3+ 樣本量 > 50k decisions 才有統計力對比兩種 regime detection;(c) Y3+ AUM > $50k 才有 Tier D capital scaling,提前評估 wasted bandwidth |

### 4.6 V111 schema regime_detection_method CHECK 對應

```
regime_detection_method TEXT CHECK (regime_detection_method IN (
    'atr_vol_funding',  -- Y2-Y3 主路徑(per ADR-0036 Decision 3.1)
    'pelt_reserved',     -- Y3+ ADR-debt(per ADR-0036 Decision 3.4 evaluation)
    'none'               -- 非 Tier D(Tier A/B/C/E 不適用 regime detection)
))
```

CHECK 強制只 3 個 allowlist 值;HMM/GARCH/Markov-switching 在 schema 層 hard reject。

---

## §5 Activation Log Audit Append-Only

### 5.1 每次 tier transition 必落 audit

per DOC-08 §12 #8 安全不變量「交易可解釋」+ V112 §10 audit field 範式:

**每次 tier transition 必寫 1 row 到 `governance.discovery_tier_activations`**:
- tier_from(降級時源 tier;activation 時 NULL)
- tier_to(目標 tier)
- capital_observed_usdt(觸發時 7d moving AUM 真實值)
- trigger_threshold_id(matched §3.1 7 級之中哪個 step;1-7)
- activated_by(actor:`'lal_gate'` / `'operator'` / `'m3_health_degraded_demoter'` / `'system_seed'`)
- activated_at(timestamp,server trusted)
- approval_lal_ref(FK ← V112 `lease_lal_assignments.id`;ADD CONSTRAINT 待 V112 land 後)
- engine_mode CHECK 5 值(paper/demo/live_demo/live/replay)
- evidence_json(JSONB;7d AUM smoothing curve / sustained 30d 證據 / source M3 anomaly snapshot 等)
- 5 audit field(created_by / created_at / updated_by / updated_at / source_version)

### 5.2 為什麼用 hypertable(非 regular table)

per V106 + db-schema-design-financial-time-series skill:
- tier transition 是 timeseries event(activated_at DESC dominant query);V103/V112 用 regular table 因 row 量 < 5k/yr,V111 activations table 預期 row 量 ~5-20 transitions/yr(low) + M3 demote daily 可能高(per CR-4 demote 是 sustained 60min HEALTH_DEGRADED 才 trigger)— 整體 ~50-200 row/yr;當前可 regular 但 hypertable 保留 future growth 路徑
- compress 30d + retention 180d 對齊 V106 範式;older data 可直接 archive
- 與 V112 lease_lal_assignments(predicted ~141 row/day)區別:V112 用 regular table 因 audit field heavy;V111 用 hypertable 因 timeseries dominant + 未來 D/E activation 可能 frequency 高

### 5.3 為什麼 append-only(0 UPDATE)

per ADR-0008 + ADR-0034 audit immutability:
- activation log 是 immutable ledger;0 UPDATE / 0 DELETE
- demote 不 UPDATE 既有 activation row;新寫 demote row(tier_from='C' tier_to='B' activated_by='m3_health_degraded_demoter')
- clawback 不 UPDATE;若 activation 撤回 → 新寫 row(tier_from='B' tier_to='A' activated_by='operator' tier_change_reason='clawback')

### 5.4 evidence_json 結構(JSONB)

```json
{
  "source": "lal_gate" | "operator" | "m3_health_degraded_demoter" | "system_seed",
  "sustained_metric": {
    "smoothing_window_days": 7,
    "sustained_window_days": 30,
    "aum_min_in_window_usdt": 32100,
    "aum_max_in_window_usdt": 38500,
    "aum_avg_in_window_usdt": 35200,
    "matched_threshold_step": 4,
    "matched_threshold_usdt": 30000
  },
  "regime_cell_snapshot": {  // Tier D only
    "atr_vol": "MID",
    "funding_state": "NEUTRAL",
    "cell_sample_count_90d": 38
  },
  "demote_reason": "liquidation_buffer_breach" | "60min_HEALTH_DEGRADED" | null,
  "lal_attestation_2fa": true | false  // LAL 4 only
}
```

---

## §6 M10 ↔ M1 LAL(tier change governance gate)

### 6.1 Tier transition 對應 LAL 路徑

per ADR-0034 LAL 0-4 對齊矩陣 + V112 M1 LAL design spec §3 state machine:

| Transition | LAL gate | approval requirement | 理由 |
|---|---|---|---|
| **A intra-tier** ($500 → $2k step 2 max position size 改 25%)| **LAL 1 LIGHT_REVIEW** | 6 hard gate auto-approve;30d stable | intra-strategy reparam;cohort_min_n=30 |
| **A → B** ($10k unlock + parameter sweep 多樣性)| **LAL 2 FULL_REVIEW** | Y2 gate + Console opt-in + 6 hard gate;cohort_min_n=50 | cross-strategy reweight(新 archetype 子族)|
| **B → C** ($30k + cointegration/pairs 新策略)| **LAL 2 FULL_REVIEW** | Y2 gate + Console opt-in + 6 hard gate;cohort_min_n=50 | cross-strategy reweight(新 strategy_name)|
| **C → D** ($50k + 9 cell regime adaptive;Y3+ gate)| **LAL 3 OPERATOR_APPROVAL** | **always operator manual approve**;clawback_ttl_sec=3600s;cohort_min_n=100 | new strategy promotion(regime-specific allocation 是新 promotion class)|
| **D → E** ($100k + portfolio overlay;Y3+ gate)| **LAL 3 OPERATOR_APPROVAL** | **always operator manual approve**;clawback_ttl_sec=3600s;cohort_min_n=100 | new strategy promotion(portfolio overlay 是新 archetype) |
| **E intra-tier** ($500k + Earn rebalance;cross-venue allocation)| **LAL 4 OPERATOR_ATTESTATION** | **always operator manual attest + 2FA**;clawback_ttl_sec=0(immutable after attest);cohort_min_n=200 | capital structure change;對齊 ADR-0034 LAL 4 「capital structure / venue change」場景 |
| **M3 HEALTH_DEGRADED 自動 demote**(D→C / C→B 等)| **LAL 1 LIGHT_REVIEW (auto)** | auto-approve fail-closed;0 operator approval(緊急 emergency demote path)| 對齊 §二 #6「Uncertainty defaults to conservative behavior」;§5 「Survival is above profit」 |
| **Operator manual clawback**(任何 tier 撤回)| **LAL 3 OPERATOR_APPROVAL** | operator override path;走 Console + audit | per ADR-0034 Decision 5 operator path |

### 6.2 LAL 0-4 數字方向對齊(per ADR-0034)

per V112 §1.1 placeholder 反向錯誤修正教訓:
- LAL 0 = **per-fill / always autonomous**(風險最低 / auto-approve allowed;Guardian fast path)
- LAL 1 = **intra-strategy reparam**(Stage 4 + 30d stable 後 auto-approve;6 hard gate)
- LAL 2 = **cross-strategy reweight**(Y2 gate + Console opt-in)
- LAL 3 = **new strategy promotion**(永遠 operator manual approval)
- LAL 4 = **capital structure / venue change**(永遠 operator manual attestation + 0 clawback)

**LAL 數字越大越嚴**;本 spec §6.1 路徑對齊 ADR-0034 不反向。

### 6.3 為什麼 M3 demote 走 LAL 1 auto(非 LAL 3 operator)

per §二 #5 + #6 + fail-closed 設計:
- HEALTH_DEGRADED 是 emergency event;0 operator approval delay 才能止血
- demote = 風險收縮方向(per #6 「Uncertainty defaults to conservative behavior」)
- 對齊 V112 placeholder v0 反向錯誤修正:demote = 走向更保守 tier,不破 ADR-0034 矩陣方向

---

## §7 M10 ↔ M6 Reward(tier 影響 weight allocation prior)

### 7.1 tier-specific weight allocation prior

per ADR-0021 R-2 Strategist orchestrator + Sprint 7 Advisory Allocator:

| Tier | Active strategy weight prior |
|---|---|
| **A** | 5 既有策略均勻 baseline(per Sprint 1 default config;each strategy ~20% portfolio weight) |
| **B** | A baseline + parameter sweep variants 從 0.2x 起步;30d cohort evidence 後 incremental 升至 ~0.4-0.8x |
| **C** | B + cointegration/pairs strategy 從 0.05x portfolio weight 起步;Stage 4 stable 後 incremental 升至 ~0.1-0.2x |
| **D** | C + 9 cell regime-specific reweight matrix;cell stability metric ≥ 30 sample/cell 才生效;否則 fallback C weight |
| **E** | D + portfolio-level mean-var optimization;per rebalance epoch operator approval |

### 7.2 為什麼 tier 是 weight prior 而非 weight authority

per ADR-0021 R-2 + 16 原則 #11:
- Tier 給 weight 起步點(prior);Strategist Agent 在 P0/P1 內仍有 reweight 自由(per §二 #11)
- 例:Tier B 給 parameter sweep variants 0.2x baseline;Strategist 觀察 cohort evidence 30d 後可調 0.4-0.8x
- Tier 不取代 Strategist;tier 是 weight bound,不是 weight authority
- Tier 升降 = weight bound change(per LAL 2/3/4 governance);Strategist 在 bound 內自主

### 7.3 為什麼 Tier D regime cell 9 個獨立 weight matrix

per ADR-0036 Decision 3.1 + alpha decomposition:
- 9 cell × 5+ strategies = 45 cell-strategy weight entry
- 每 cell 對應一個 regime label(`LOW-CONTANGO` / `HIGH-BACKWARDATION` 等);cell × strategy 是 governance 仲裁的最小單位
- per cell 平均 ≥ 30 sample 才生效;cell sample < 30 時 fallback C-tier weight

---

## §8 M10 ↔ M3 Health(DEGRADED → tier 降階)

### 8.1 自動 demote 觸發條件

per V106 M3 health observations + §二 #5/#6 + ADR-0034 demote path:

**M3 emit `HEALTH_DEGRADED` 60min sustained → M10 自動 demote tier 一階**:
- B → A
- C → B
- D → C
- E → D
- A → A(已是 baseline,保持但 emit warning + portfolio cap 至 80% baseline)

### 8.2 為什麼 60min sustained(非 instant)

per V106 範式 + flap mitigation:
- 60min sustained 防 transient health spike 觸 false demote
- 對齊 V106 design spec sustained metric 設計
- demote 必走 LAL 1 LIGHT_REVIEW auto-approve(per §6.1);clawback_ttl_sec=300s operator 反悔窗口

### 8.3 demote ≠ tier_change_reason='clawback'

- demote = 風控驅動(per `tier_change_reason='health_degraded'`)
- clawback = operator override 撤回(per `tier_change_reason='operator_override'`)
- 兩種 reason 在 evidence_json 區分;audit trail 各自獨立

---

## §9 反向 attack mitigation

### 9.1 5-gate 對齊 AMD-2026-05-21-01

per AMD-2026-05-21-01 5-gate + §四 5 硬邊界:

**operator override tier 升必過 5-gate**:
1. Python `live_reserved`
2. Python Operator role auth
3. `OPENCLAW_ALLOW_MAINNET=1`
4. valid secret slot
5. signed unexpired `authorization.json` with matching environment

LAL 3/4 approval 不可繞 5-gate;V111 schema + lal_gate Rust module 強制 enforce。

### 9.2 hot-edit `discovery_tier_config` SQL 禁

per V112 §10 audit field + ADR-0008 immutability:
- 直接 `UPDATE governance.discovery_tier_config SET capital_threshold_min_usdt = ...` 繞 LAL gate → 違反 §二 #4「策略不繞風控」+ #7「學習 ≠ 改寫 Live」
- 配置改變必走 V### migration(audit trail 留 migration version + reviewer sign-off)
- 對齊 V103/V112 migration discipline

### 9.3 demo / paper / replay tier 升不算

per §3.5:
- demo / paper / replay 不算 sustained AUM(engine_mode CHECK constraint reject)
- 防 mock-PASS 攻擊路徑(operator 在 demo 加倉繞 sustained 條件)

### 9.4 capital threshold step 不可向下調(except via formal V### migration)

- `governance.discovery_tier_config` 5 row seed 不可 UPDATE capital_threshold_min/max(per V103 ON CONFLICT DO NOTHING)
- 若未來 v6.0 升 Tier B threshold $10k → $5k(放寬),必新 V### migration + LAL 2 governance audit + PM signoff
- 防 operator 暗中放寬 threshold 後 mock activation

### 9.5 反向 attack 範例 + mitigation

| Attack vector | Mitigation |
|---|---|
| 加倉 spike 觸發 tier 升 → 立刻 withdraw 繞 LAL 3 approval | sustained 30d window 防;evidence_json 記 sustained_metric |
| operator 改 `governance.discovery_tier_config.capital_threshold_min_usdt` 繞 step | UPDATE 走 V### migration(audit + signoff)+ ON CONFLICT DO NOTHING 防 INSERT-level 改 |
| 直接 INSERT `discovery_tier_activations` row 繞 lal_gate | `assigned_by` allowlist `('lal_gate','operator_signoff')`;非 allowlist actor INSERT raise WARNING;application layer 拒寫 |
| Tier D regime detection 改 'hmm' 繞 ADR-0036 黑名單 | CHECK constraint hard reject;違反 INSERT RAISE |
| demo 加倉 → tier B activation → 切 live 接管 | engine_mode CHECK reject `'paper'/'demo'/'replay'`;只認 `'live'/'live_demo'` |
| Tier D activation 不走 LAL 3 approval | `approval_lal_ref` FK NOT NULL for tier_to IN ('D','E');缺 FK → RAISE |
| M3 demote bypass | lal_gate Rust module 強制 demote(Sprint 4+ IMPL);non-bypass |

---

## §10 Acceptance Criteria(5-7 條)

### 10.1 Schema acceptance(MIT + E2)

| # | 標準 | 驗證方法 |
|---|---|---|
| 1 | `governance.discovery_tier_config` 5 row seed 對應 Tier A-E full ladder(per §2.1 + ADR-0036 Tier D 對 'atr_vol_funding')| empirical SELECT 驗 `tier_level='D' AND regime_detection_method='atr_vol_funding'`;`tier_level='A' AND regime_detection_method='none'` |
| 2 | `governance.discovery_tier_activations` hypertable 真建立(hypertable on activated_at, 7d chunk, 30d compress, 180d retention)| `SELECT * FROM timescaledb_information.hypertables WHERE hypertable_name='discovery_tier_activations'` 返 1 row |
| 3 | regime_detection_method CHECK 拒 'hmm' / 'garch' / 'markov_switching'(ADR-0036 hard reject 強制)| empirical INSERT test reject INVALID |
| 4 | engine_mode CHECK 5 值齊全(paper/demo/live_demo/live/replay)| empirical INSERT test reject INVALID;`pg_get_constraintdef` 反映 5 值 |
| 5 | V111.sql idempotent 雙跑 0 RAISE + seed rows 仍 5(非 10)| `psql -f V111.sql` × 2 + `SELECT count(*) FROM governance.discovery_tier_config` = 5 |
| 6 | sqlx checksum 對齊 + engine restart 後 success=t | per V112 §8 SOP |

### 10.2 M10 ↔ M1 LAL acceptance(PA)

| # | 標準 | 驗證方法 |
|---|---|---|
| 1 | A→B 和 B→C transition 寫 `discovery_tier_activations.approval_lal_ref` 必對應 V112 lease_lal_assignments tier=2 | application layer test;lal_gate Rust module 強制(Sprint 4+ IMPL)|
| 2 | C→D 和 D→E 必對應 V112 tier=3 | application layer test |
| 3 | E intra($500k 跨 venue)必對應 V112 tier=4 + 2FA evidence | application layer test |
| 4 | M3 HEALTH_DEGRADED 60min sustained 自動 demote 走 LAL 1 + tier_change_reason='health_degraded' | application layer test + V106 M3 emit M10 demote 路徑 verify |

### 10.3 反向 attack acceptance(QA + R4)

| # | 標準 | 驗證方法 |
|---|---|---|
| 1 | demo / paper / replay tier 升 INSERT reject | empirical INSERT test reject |
| 2 | hot-edit `discovery_tier_config.capital_threshold_min_usdt` 不允許 → 走 V### migration | application layer test;ON CONFLICT DO NOTHING 防 seed 改 |
| 3 | non-allowlist actor INSERT `discovery_tier_activations` warning + 拒寫 | lal_gate Rust module 強制(Sprint 4+ IMPL)|

---

## §11 IMPL Phase

### 11.1 Phase 1 — V111 schema IMPL(Sprint 1A-γ)

| Item | Owner | Workload | Track |
|---|---|---|---|
| V111 spec full DDL land(本 spec 之姊妹檔)| MIT | 15-25 hr | Sprint 1A-γ pre-dispatch |
| V111.sql writer(Rust migration adapter)| E1 | 30-50 hr | Sprint 1A-γ IMPL |
| Linux PG dry-run × 2 + sqlx checksum repair | E1 | 5-10 hr | Sprint 1A-γ IMPL |
| E2 review + E4 regression | E2/E4 | 5-10 hr | Sprint 1A-γ closure |
| restart_all --rebuild deploy + engine restart verify | E1 | 2-5 hr | Sprint 1A-γ closure |

### 11.2 Phase 2 — lal_gate Rust module(Sprint 4+)

| Item | Owner | Workload | Track |
|---|---|---|---|
| `lal_gate.rs` writer(tier transition gate + LAL 1-4 dispatch)| E1 | 40-60 hr | Sprint 4 |
| sustained AUM monitor(7d MA + 30d sustained)| E1 | 30-40 hr | Sprint 4 |
| Tier D 9 cell matrix calc(per ADR-0036 ATR-vol+funding)| E1 | 50-70 hr | Y2-Y3 |
| Console UI tier toggle(LAL 2 Console opt-in + LAL 3/4 manual approve)| E1 | 20-30 hr | Sprint 4-8 |
| Healthcheck wiring(`check_discovery_tier_writer()`)| E1 | 5-10 hr | Sprint 1B |

### 11.3 Phase 3 — Y2 Tier B/C activation(Sprint 6+)

| Item | Owner | Workload |
|---|---|---|
| Parameter sweep variants spec + cohort evidence 30d | QC/PA | Y2 evaluation |
| Cointegration / pairs strategy ASDS candidate | AI-E | Y2 Sprint 6 |
| LAL 2 Console toggle deploy | E1 | Y2 deploy |

### 11.4 Phase 4 — Y3+ Tier D/E activation(per ADR-0036)

| Item | Owner | Workload |
|---|---|---|
| 9 cell regime allocator IMPL(per ADR-0036 Decision 3.1)| E1 | Y3 Q1-Q2 |
| Cell stability metric 7d cron(per ADR-0036 Decision 3.1)| E1 | Y3 Q1 |
| PELT change-point evaluation(per ADR-0036 Decision 3.4 ADR-debt)| QC | Y3 Q1 ADR-debt |
| Portfolio overlay mean-var optimization(Tier E)| E1/AI-E | Y3+ |

---

## §12 Cross-V### + Open Questions

### 12.1 Cross-V### dependency

| V### | M10 依賴方式 | 是否 FK |
|---|---|---|
| **V098 (governance.audit_log)** | activation evidence cross-ref(`approval_lal_ref` 走 V112 而非直接 ref V098)| 否 |
| **V112 (M1 LAL tiers)** | `discovery_tier_activations.approval_lal_ref` FK ← `lease_lal_assignments.id`;tier change governance evidence | **placeholder FK**(V112 land 後 ALTER ADD CONSTRAINT)|
| **V106 (M3 health observations)** | M3 emit `HEALTH_DEGRADED` 60min sustained → M10 自動 demote tier 一階 | 否(cross-ref query) |
| **V091 (portfolio_var P0)** | `capital_observed_usdt` = `portfolio_var.usdt_var_15m` 7d MA proxy | 否(application-layer calc) |
| **V107 (M11 replay)** | M11 replay 重放 tier transition evidence 驗 reproducibility | 否(cross-ref query;engine_mode='replay')|
| **V109 (M8 anomaly)** | M8 anomaly trigger 不直接 emit tier transition;經 M3 health 中介 | 否 |

### 12.2 Open Questions(≥3 待 PM / MIT / QC 仲裁)

1. **Q1: `capital_observed_usdt` data source 與精度**:採 V091 `portfolio_var.usdt_var_15m` 7d MA 為 proxy?或單獨 V### writer 寫 `governance.aum_observations` table?(spec 假設 proxy;待 MIT V091 schema 對齊確認;若 V091 column 名不對需 patch)

2. **Q2: Tier E intra($500k cross-venue rebalance)是否真需 LAL 4 attestation**:對齊 ADR-0034 LAL 4 「capital structure / venue change」原則 — Tier E 是 multi-strategy overlay 不一定跨 venue;若僅單 venue intra-tier reweight 可降至 LAL 3 manual approval。等 Y3+ 真實 case 仲裁;當前 spec 採 LAL 4 保守路徑。

3. **Q3: M3 demote 是 tier 降一階,還是降到 baseline A**:per §8.1 採降一階(B→A / C→B / D→C / E→D)是漸進收縮;若 HEALTH_DEGRADED 嚴重程度高,是否一次降到 A 更安全?spec 採漸進路徑(per ADR-0034 LAL 1 reparam 哲學),但 V106 M3 severity 高度可能需要 fast-track 降到 A — 待 M3 severity taxonomy 與 M10 demote 路徑 cross-V### reconciliation。

4. **Q4: 9 cell matrix 第一個 Tier D row 是否在 V111 seed 寫入 default cell × strategy weight matrix**:per §7.3,9 cell × 5+ strategies = 45 weight entry;若 seed 寫入,V111 schema 需含 `cell_strategy_weight_matrix JSONB` column 或單獨 V### table;若 seed 不寫,Sprint 6+ 才 IMPL writer。spec 採後者(Sprint 6+),但 MIT 在 V111 full DDL 階段確認。

5. **Q5: capital threshold 7 級的 $500k Tier E intra-tier 是否會引入跨 venue allocation 範疇外功能**:$500k threshold 是否在 OpenClaw Y2-Y3 timeline 真有實際 case?或屬於 future scope?spec 保留以對齊 v5.8 §2 M10 7-tier ladder 完整性,但 PM 可決定 Y3+ scope 才 active;當前 V111 seed 寫 row 但 Sprint 4+ lal_gate 不 active enforcement。

6. **Q6: ATR-vol / Funding-state percentile threshold per-symbol vs cross-symbol**:per ADR-0036 §Negative Risk「funding state threshold 跨 symbol 異質」— 不同 perp symbol (BTC vs ALT) funding rate baseline 差 5-10x;funding Δ > 2σ threshold per-symbol 估計 vs cross-section threshold(global percentile)cost-effective tradeoff;ADR-0036 採 per-symbol 但本 spec Sprint 4+ IMPL 可能簡化為 cross-section 在 Y2 試點;待 QC Y2 sprint 7 評估。

---

## §13 §二 16 根原則合規確認

| # | 原則 | 是否相容 | 說明 |
|---|---|---|---|
| 1 | 單一寫入口 | PASS | M10 不創寫入口;tier 升降走 lal_gate → LAL 2/3/4 → Decision Lease → Guardian |
| 2 | 讀寫分離 | PASS | M10 schema 屬 governance(非 learning);tier 變動是 governance event;ML training filter 不引 |
| 3 | AI 輸出 ≠ 命令 | PASS | M10 tier transition 走 LAL gate;Strategist Agent 在 tier weight bound 內自主但不直接執行 tier 升 |
| 4 | **策略不繞風控** | PASS | **tier 升必過 LAL 2/3/4 gate**;hot-edit `discovery_tier_config` SQL 禁;反向 attack §9 mitigation 全列 |
| 5 | 生存 > 利潤 | PASS | tier 升保守路徑(sustained 30d / Y2-Y3 gate)+ M3 demote 自動止血;Tier D 9 cell cell sample < 30 fallback C |
| 6 | 失敗默認收縮 | PASS | M3 HEALTH_DEGRADED 自動 demote;cell stability 失敗 fallback;sustained metric 失敗 hold 既有 tier;engine_mode CHECK 拒 paper/demo/replay |
| **7** | **學習 ≠ live** | PASS | **demo / paper / replay tier 升不算**;sustained AUM 只認 live / live_demo;Tier D HMM read-only counterfactual 不得寫 live |
| 8 | 交易可解釋 | PASS | activation log append-only;evidence_json 留 sustained metric / regime cell snapshot / demote reason;5 audit field 完整 |
| 9 | 雙重防線 | PASS | tier gate + Guardian + Decision Lease + lal_gate Rust module 多層 |
| 10 | 分離事實 / 推論 / 假設 | PASS | sustained AUM = 事實(empirical);tier × strategy weight prior = 推論(per Strategist);Y3+ PELT evaluation = 假設(ADR-debt)|
| 11 | Agent 在 P0/P1 內自主 | PASS | tier 是 weight bound 不是 weight authority;Strategist 在 tier bound 內自主 reweight |
| 12 | 行為由 evidence 演化 | PASS | tier 升必 sustained 30d evidence + 6 hard gate;Tier D activation 必 9 cell × ≥30 sample evidence |
| **13** | **cost 感知** | PASS | **ATR-vol+funding 9 cell 計算成本 < 2μs/symbol** vs HMM/GARCH MCMC iteration 100-1000ms;ADR-0036 黑名單即是 cost 治理 |
| 14 | 零外部成本 | PASS | ATR / funding 是 Bybit WS feed;不需付費 data source |
| 15 | 多 Agent 協作 | PASS | M10 + M1 LAL + M3 health + M6 reward + M11 replay 各有明確 surface |
| **16** | **Portfolio > 孤立 trade** | PASS | **tier 升即是 portfolio-level diversification expansion**;Tier E 是 portfolio overlay |

---

## §14 關鍵文件指針

- 本 M10 DESIGN spec:本檔
- V111 full DDL schema spec(姊妹檔):`srv/docs/execution_plan/2026-05-21--v111_m10_discovery_tier_config_schema_spec.md`
- ADR-0036(Tier D 黑名單 + 9 cell matrix source of truth):`srv/docs/adr/0036-m8-anomaly-detection-and-m10-tier-d-model-blacklist.md`
- ADR-0034(LAL 0-4 authoritative source of truth):`srv/docs/adr/0034-decision-lease-layered-approval-lal.md`
- M1 LAL design spec:`srv/docs/execution_plan/2026-05-21--m1_lal_layered_approval_lease_design_spec.md`
- V112 spec(LAL tiers full DDL 範式):`srv/docs/execution_plan/2026-05-21--v112_m1_decision_lease_lal_tiers_schema_spec.md`
- V103 spec(14 section structure 範式 + 5 audit field):`srv/docs/execution_plan/2026-05-21--v103_v104_earn_hypotheses_schema_spec.md`
- V106 spec(hypertable + retention 範式;M3 health observations):`srv/docs/execution_plan/2026-05-21--v106_m3_health_observations_schema_spec.md`
- v5.8 主檔 §2 M10:`srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md`(line 364-389)
- PA dispatch consolidation §6 cross-V### dep graph:`srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md`
- math-model-audit skill(HMM/GARCH 黑名單 source of truth):`srv/.claude/skills/math-model-audit/SKILL.md`
- walk-forward-validation-protocol skill(block bootstrap + OOS SOP):`srv/.claude/skills/walk-forward-validation-protocol/SKILL.md`
- AMD-2026-05-21-01 5-gate:`srv/docs/CCAgentWorkSpace/Operator/...`(待確認檔名)
- CLAUDE.md §四 5 硬邊界 + §Data Migrations And Validation:`srv/CLAUDE.md`

---

**END M10 Discovery Tier DESIGN spec v0**
