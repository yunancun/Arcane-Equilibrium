# Sprint 2 Day 0 Business Dispatch Packet — Alpha Tournament + M4 stage 1 + M10 Tier A + M8 schema

**Date**: 2026-05-25
**Author**: PA（Project Architect）
**Source SoT**: v5.8 主檔 `srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md` §2 + §4 line 624 + v5.7 §8 line 282；**Alpha Tournament SSOT**: `srv/docs/execution_plan/2026-05-26--alpha_tournament_ssot_spec.md`
**Predecessor**: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md`（v5.8 13 prerequisite + 16 CRITICAL + 24 HIGH）
**Day -1 closure**: H-1 atomic deploy（PID 598276 SHA b005bb00）✅ + H-2 cron 10/13（4 HIGH/MED + 6 SHOULD）✅ + EA-2 N/A confirmed ✅ + EA-4 P0-EDGE-1 AC-A amend ✅ + 4 false-positive declassify ✅ + M-4 hygiene SOP land ✅
**Format**: PnL-led per `feedback_pnl_priority_over_governance.md`
**Status**: PA DESIGN — packet 給 PM 接 7 並行 sub-agent 派 IMPL

---

## §0 TL;DR — Verdict

### Sprint 2 Day 0 dispatch readiness verdict — **DISPATCH-PARTIAL-READY**

| Stream | Spec readiness | Schema readiness | Cron readiness | Verdict |
|---|---|---|---|---|
| **A: Alpha Tournament** | ✅ Alpha SSOT landed 2026-05-26；candidate-level PA/MIT spec still required | ✅ V101/V102/V103 land | ✅ ml_training daily | READY FOR CANDIDATE-SPEC → IMPL |
| **B: M4 pattern miner stage 1** | ✅ v5.8 §2.M4 line 158-184 + V103 EXTEND land | ✅ V103 hypotheses + V103 EXTEND land | ✅ edge_label_backfill */30min | READY |
| **C: M10 Tier A productionize** | ✅ v5.8 §2.M10 line 357-388 | 🔴 V111 NOT LANDED | ✅ ref21_symbol_universe @20 | PARTIAL — V111 spec→IMPL 同 sprint |
| **D: M8 read-only schema land** | ✅ v5.8 §2.M8 line 279-314 + ADR-0036 spec'd | 🔴 V109 NOT LANDED | ✅ feature_baseline @04:41 | READY — schema-only Sprint 2 |
| **E: AC-19 ALT bucket monitor** | ✅ PA 5/25 §4.4 + FA + QA reconcile | n/a (read-only SQL) | n/a | READY |

**核心結論**：
- **Stream B + D + E** Day 0 即可派（spec + schema/SQL ready）；總 ~150-200 hr / 5-7 並行 sub-agent Wave 1
- **Stream A** Alpha Tournament SSOT 已補（2026-05-26）；不再是 implicit scope。Wave 1 仍需 PA/MIT per-candidate spec（A1 funding short-only v2 + A2 liquidation cascade fade 優先；A3 BTC/ETH pairs DRAFT；A4 C13 / A5 token unlock defer）後 Wave 2 才 IMPL
- **Stream C** V111 schema + cron + Optuna IMPL 同 sprint，依賴 §1A-γ V111 spec land；建議 D+3 V111 schema spec + Day 0 起 Optuna 後端 IMPL（不依賴 V111）

**total hr estimate**：240-380 hr / Sprint 2 wall-clock 3w（W12-14.5 per v5.8 §4 CR-13 整合 11.5-14.5w 真實 calendar）

**3 條 PM decision point 待拍**（§9）：
1. Stream A Alpha Tournament scope 仲裁 — **superseded by 2026-05-26 Alpha SSOT**：A1+A2 Sprint 2 primary；A3 DRAFT/stats-first；A4/A5 defer unless data gate passes
2. Stream C V111 spec land cadence（Sprint 2 內或 Sprint 1A-γ 推遲）
3. Sprint 2 close_maker_audit P1 missing table land 順序（Sprint 1B follow-up 或 Sprint 2 cross-cutting）

---

## §1 Sub-Agent 並行 Ceiling 預警 + Wave Staging

### §1.1 並行 ceiling = 7 並行 sub-agent + PM hands-on coordination（hard cap）

per memory `project_multi_session_memory_race`（2026-04-23 教訓 + v5.7 12 prefix DONE 經驗）：
- > 7 並行 → cross-session memory race（隔壁 session 誤 revert 風險）
- 7 並行需 PM 主會話 hands-on coordination + commit-first 協議
- 派發前必 `git fetch` + `git branch -r | grep <topic>`（per `feedback_fetch_before_dispatch`）

### §1.2 Sprint 2 Wave 1（Day 0 → D+5 wall-clock）— 7 並行 sub-agent

| Wave 1 Track | Sub-agent | 角色 | Hours | Stream | Dependency |
|---|---|---|---|---|---|
| W1-A | sa-1 | **PA + MIT spec** Stream A candidate-level spec + Alpha SSOT §3 candidate pre-screen（A1/A2 primary；A3 DRAFT；A4/A5 defer） | 10-15 | A | Alpha SSOT §3-§8 |
| W1-B | sa-2 | **MIT** Stream B M4 pattern miner stage 1 algorithm spec（cross-correlation + event-window）+ leakage protocol（per CR-6） | 15-20 | B | V103 EXTEND land ✅ |
| W1-C | sa-3 | **E1 IMPL** Stream B M4 pattern miner Rust+Python hybrid scaffold + DRAFT writeback to V103 | 30-40 | B | W1-B spec land |
| W1-D | sa-4 | **MIT spec + E1 IMPL** Stream C M10 Tier A Optuna walk-forward cron skeleton（後端，不依賴 V111） | 20-30 | C | ml_training cron ✅ |
| W1-E | sa-5 | **MIT** Stream D M8 anomaly schema V109 DDL + ADR-0036 alignment + statistical method 選擇 spec | 25-35 | D | ADR-0036 baseline land |
| W1-F | sa-6 | **E1 IMPL** Stream D V109 schema land（Linux PG dry-run + Guard A/B/C + idempotent） | 15-20 | D | W1-E spec |
| W1-G | sa-7 | **QA + FA** Stream E AC-19 ALT bucket monitor 14d empirical SOP + bucket-split SQL daily fire | 10-15 | E | none |

**Wave 1 總 hr**：125-175 hr / 5d wall-clock（5-7 並行 + PM coordination）

### §1.3 Sprint 2 Wave 2（D+5 → D+12 wall-clock）— 5-6 並行 sub-agent

| Wave 2 Track | Sub-agent | 角色 | Hours | Stream | Dependency |
|---|---|---|---|---|---|
| W2-A | sa-1 | **PA + MIT** Stream A: A1/A2 implementation spec + scoring/gate acceptance packet against Alpha SSOT §5-§10 | 20-30 | A | W1-A candidate spec |
| W2-B | sa-2 | **E1 IMPL** Stream A: alpha_tournament_runner scaffold（Rust + Python harness）+ 14d demo data 累積 hook | 30-40 | A | W2-A spec |
| W2-C | sa-3 | **E1 IMPL** Stream C M10 Tier A V111 schema land + Optuna cron 接線 V111 config table | 15-20 | C | V111 spec land (PM #2) |
| W2-D | sa-4 | **E1 IMPL** Stream D V109 anomaly_events read-only writer skeleton（Sprint 3 detector 不在 scope） | 10-15 | D | W1-F V109 land |
| W2-E | sa-5 | **E2 + E4** Stream B+C+D Wave 1 IMPL 對抗式 review + Mac cargo test --workspace + node --check | 15-20 | B+C+D | W1-C/D/F IMPL DONE |
| W2-F | sa-6 | **QA empirical + FA business acceptance** Stream E bucket-split monitor daily evidence accumulation + Stream B M4 leakage post-IMPL audit | 15-25 | B+E | W1-C IMPL + ALT bucket data |

**Wave 2 總 hr**：105-150 hr / 7d wall-clock（5-6 並行 + PM coordination）

### §1.4 Sprint 2 Wave 3（D+12 → D+21）— Sign-off + 6/2 ALT bucket gate verdict

| Wave 3 Track | Sub-agent | 角色 | Hours | Stream |
|---|---|---|---|---|
| W3-A | sa-1 | **PA + MIT** Stream A 14d demo evidence accumulation review + DRAFT hypothesis writeback verify | 8-10 | A |
| W3-B | sa-2 | **QA** 14d ALT bucket gate verdict — pass / escalate spec §4.3 Option α/β | 5-8 | E |
| W3-C | sa-3 | **TW + PM** Sprint 2 acceptance sign-off + Sprint 3 M8 read-only detector prerequisite check | 5-8 | all |

**Wave 3 總 hr**：18-26 hr / 9d wall-clock（single-thread 收口）

**Sprint 2 總 hr**：248-351 hr / 3w wall-clock ≈ v5.8 §4 280-400 hr 估算對齊

---

## §2 Stream A: Alpha Tournament（核心 — 新 source 是 P0-EDGE-1 closure 路徑）

### §2.1 Scope 仲裁（PA verdict）

**v5.8 §4 line 624 寫**："Alpha Tournament + M4 pattern miner stage 1 + M10 Tier A productionize + M8 read-only"

**v5.8 §2 沒有 single Alpha Tournament block**（這是 v5.7 §7 衍生 + EA-4 amend implicit scope）。PA 仲裁 Sprint 2 Day 0 起 Stream A 拆 3 軌：

| 軌 | Scope | AC | Dependency |
|---|---|---|---|
| **A1 5 textbook retry** | 5 textbook 殭屍策略 demo 7d avg_net > 5bps（Wilson CI lower > 0），n ≥ 30 per-strategy | per P0-EDGE-1 AC-A (i)；QC 5/11 verdict 已標 alpha-deficient 結構性結論 stable | not blocking — 自然 demo 累積 |
| **A2 新 alpha source candidate** | ≥ 3 個 alpha-bearing 新 source 過 demo 7d threshold | per P0-EDGE-1 AC-A (ii) amend；Sprint 2 內過 PA 5-source pre-screening + IMPL 1-2 source + 14d demo accumulation | depends on PM #1 decision + Stream B M4 pattern miner stage 1 自動發現的 DRAFT |
| **A3 portfolio attribution** | M11 counterfactual replay + Sprint 2 新 source 顯示 7d gross 正向且歸因明確 | per P0-EDGE-1 AC-A (iii) amend | depends on M11 daily replay enable（Sprint 3 才 deploy） |

**Sprint 2 重點 = A2 IMPL（A1 自動累積；A3 Sprint 3 才能 IMPL）**

### §2.2 候選 5-6 新 alpha source pre-screening（PA 提，待 PM 拍）

| # | Candidate | Source | Sprint 2 可行性 |
|---|---|---|---|
| 1 | **Funding rate dislocation arbitrage v2 — short-only > 30% annualized** | v5.7 §8 line 304 + funding_arb V2 dormant 教訓（V2 已 retired per AMD-2026-05-26-01；本 candidate 為 funding_short_v2 窄 short-only carve-out，與 V2 directional bi-side 不同設計） | 設 funding > 30% annualized 為 gate；只開 short side（per memory `project_funding_arb_v2_deprecation_path`）；可 Sprint 2 IMPL |
| 2 | **Token unlock event-window short alpha** | v5.8 §2.M4 line 162-163；Tokenomist trial calendar | 過 unlock 前 4h 開 short bias；Sprint 2 demo 累積；MIT bar 30 events min |
| 3 | **Cross-symbol cointegration pairs (BTC/ETH)** | v5.7 §8 Pairs trading；TODO §1.2 line 112 | KalmanFilter pairs；需 BTC + ETH 同時 active；可 Sprint 2 IMPL |
| 4 | **Microstructure liquidation cascade fade** | v5.7 §7 microstructure + market.liquidations writer | Liquidation > $X / 5min → fade short；需 liquidation writer 5d+ stable；Sprint 2 可 IMPL |
| 5 | **Macro halt overlay anti-pattern**（避免 macro event 期間開新 position） | v5.8 §2.M2 + macro feed | 純 overlay 不 produce alpha 而 reduce DD；非 source 而 risk mgmt；defer Sprint 3+ |
| 6 | **Bybit Earn yield-bearing fallback variant**（per Stage 0R Earn variant design） | `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-25--stage_0r_earn_variant_design.md` | Stage 0R 已 DESIGN；Sprint 1B Earn first stake 已 dispatch；Sprint 2 可結合 portfolio attribution |

**PA pre-screening verdict（建議 PM 採用）**：
- **Sprint 2 IMPL 2 個**：#1 funding > 30% short-only（高 expected edge + 簡單 IMPL）+ #4 liquidation cascade fade（已有 writer + 高 frequency）
- **Sprint 2 DRAFT 1 個**：#3 BTC/ETH pairs（IMPL 較重 + 需先 cointegration 統計驗）
- **Sprint 3+ defer**：#2 token unlock（依賴 Tokenomist trial calendar） + #5 macro overlay
- **不在 Stream A scope**：#6 Earn variant（屬 Sprint 1B follow-up）

### §2.3 AC for Stream A

| AC | 內容 | 達標路徑 |
|---|---|---|
| AC-S2-A-1 | Sprint 2 內 IMPL ≥ 2 個新 alpha source candidate（per PA pre-screening + PM #1） | W2-B E1 IMPL 收口 |
| AC-S2-A-2 | 14d demo data accumulation per candidate ≥ 30 n_fills（per CR-6 minimum bar） | Wave 3 W3-A review |
| AC-S2-A-3 | ≥ 1 個 candidate 達 demo 7d avg_net > 5bps + Wilson CI lower > 0 | Sprint 3+ verdict（Sprint 2 內未必 ready） |
| AC-S2-A-4 | DRAFT writeback to V103 hypotheses table 完整（per CR-6 minimum bar 6 attribute） | W3-A review |
| AC-S2-A-5 | 5 textbook 自然累積 monitor（每日 SQL bucket-split + Wilson CI projection） | QA daily SOP |

### §2.4 Dispatch design — Stream A IMPL chain

```
W1-A PA spec scope 仲裁 + 5-source pre-screening
  ↓ PM #1 decision land
W2-A PA + MIT pre-spec ≥ 2 新 candidate（含 §10 P0 precondition 對照）
  ↓
W2-B E1 IMPL alpha_tournament_runner Rust+Python scaffold
  ↓
14d demo accumulation
  ↓
W3-A PA + MIT post-IMPL evidence review
  ↓
Sprint 3+ 進入 Stage 0 → 0R verdict（per AMD-2026-05-15-01）
```

**HR estimate**：80-120 hr（PA spec 10-15 + MIT spec 25-30 + E1 IMPL 30-40 + QA 累積 + Wave 3 review 15-25 + buffer）

**對抗式 review 5 重點**（W2-E E2 必查）：
1. **Look-ahead bias**：candidate #4 liquidation cascade fade 用 `rolling(N).max()` 含 current bar → shift(1) leak-free 強制（per memory `feedback_indicator_lookahead_bias`）
2. **Hard boundary 0 觸碰**：5-gate auto path inheritance 不繞 P0/P1 風控（per CR-15）
3. **Decision Lease 路徑**：所有 candidate alpha 寫 live 必經 Lease + LAL Tier（per CR-2 / 16 原則 #3）
4. **Funding short-only #1 gate**：annualized funding > 30% 是硬 gate；不能在程式碼中 silent override
5. **Liquidation cascade #4**：5min window 是否含 self-fills（剔除 own fills 必須）

---

## §3 Stream B: M4 Pattern Miner Stage 1（v5.8 §2.M4 line 158-184）

### §3.1 Scope（v5.8 §2.M4 line 176-184 已 spec'd 80-120 hr Sprint 2-3）

- **演算法**：statistical pattern miner（cross-correlation + event-window analysis）
- **Ingestion**: market.kline / trading.fills / market.liquidations / market.funding / token unlocks
- **Output**: DRAFT pattern → V103 hypotheses table（V103 EXTEND 已 land per Sprint 1A-α DONE）
- **State**: DRAFT only（per 16 原則 #7 學習 ≠ Live；per ADR-0024-lite Cowork 是 operator-assistant 非 L2 autonomous）

### §3.2 AC for Stream B

| AC | 內容 | 達標路徑 |
|---|---|---|
| AC-S2-B-1 | Pattern miner stage 1 IMPL（cross-correlation + event-window）覆蓋 4 個 input source（kline / fills / liquidations / funding）；token unlock 留 Sprint 3+ | W1-C E1 IMPL |
| AC-S2-B-2 | V103 DRAFT writeback schema 對齊 per CR-6 minimum bar 6 attribute（N ≥ 30 / Bonferroni p < 0.05/K / effect size ≥ 0.2 / 6mo sub-period stability / Harvey-Liu-Zhu graveyard flag / cluster K silhouette 5-fold CV） | W1-C IMPL + W2-F MIT audit |
| AC-S2-B-3 | Rolling stat 強制 shift(1) leak-free（per memory `feedback_indicator_lookahead_bias` + CR-6）；所有 feature 並列 leak-free 對比 | W2-E E2 review + E4 cross-language fixture |
| AC-S2-B-4 | Pattern miner output 不直接 trigger trading（per 16 原則 #7 / #11）；DRAFT writeback only | W1-C IMPL |
| AC-S2-B-5 | 4 Track 並行查 leakage scan + anti-mock leakage scan（per H-17）| W2-F MIT post-IMPL audit |

### §3.3 Dispatch design — Stream B IMPL chain

```
W1-B MIT algorithm spec（cross-correlation + event-window leakage protocol）
  ↓
W1-C E1 IMPL Rust+Python hybrid scaffold（Rust ndarray-stats for high-volume stats; Python pandas for event-window aggregation; Hybrid via PyO3 binding）
  ↓
DRAFT writeback to V103
  ↓
W2-E E2 對抗式 review（leakage / shift(1) / anti-mock leakage scan）
  ↓
W2-F MIT post-IMPL audit + FA business acceptance（DRAFT 質量）
  ↓
Sprint 3 Cowork + operator review 起跑（不在 Sprint 2 scope）
```

**HR estimate**：80-120 hr per v5.8 §2.M4 line 178（W1-B 15-20 + W1-C 30-40 + W2-E 15-20 + W2-F 15-25 + buffer）

**對抗式 review 重點（W2-E E2 + W2-F MIT post-IMPL）**：
1. **Look-ahead bias scan**：所有 rolling 統計必 shift(1) + 並列 leak-free 對比；catch G1-01 pre-bug pattern（per memory `feedback_indicator_lookahead_bias`）
2. **Minimum bar enforcement**：DRAFT 必含 6 attribute（per CR-6）；缺一不寫 V103
3. **PyO3 binding 1e-4 容差**：cross-language fixture harness（per H-18）
4. **Anti-mock leakage**：test fixture 不可用 mock 替 production data；per `feedback_v_migration_pg_dry_run` 教訓延伸

---

## §4 Stream C: M10 Tier A Productionize（v5.8 §2.M10 40-60 hr）

### §4.1 Scope（v5.8 §2.M10 line 376-380）

- **Tier A** = Strategy parameter discovery via Optuna + walk-forward（already exists 的 cron 化）
- **目標**：cron + auto-walk-forward；Sprint 2 內 productionize（v5.8 §2.M10 Sprint 2 40-60 hr）
- **Schema**: V111 `learning.discovery_tier_config`（per v5.8 §3 line 604）

### §4.2 V111 spec land — 依賴 Sprint 1A-γ（PM #2 decision）

**v5.8 consolidation report §1.A `CR-8`**: V111 (M10 discovery tier) 是 Sprint 1A-γ DESIGN deliverable。如 Sprint 1A-γ 尚未開（Sprint 1A timeline W0-8.5 + 1A-γ W3.5-5.5 重疊 Sprint 2 W12-14.5）—> 須仲裁順序。

**PA 推薦**：Sprint 1A-γ V111 spec land 必先於 Sprint 2 V111 schema deploy；建議排 Sprint 1A-γ Wave 1（Stream C 與 Sprint 1A-γ 共用 sub-agent budget）

### §4.3 AC for Stream C

| AC | 內容 | 達標路徑 |
|---|---|---|
| AC-S2-C-1 | Optuna walk-forward cron + auto-trigger | W1-D E1 IMPL Optuna 後端 |
| AC-S2-C-2 | V111 schema land（Linux PG dry-run + Guard A/B/C） | W2-C E1 IMPL（V111 spec land 前置） |
| AC-S2-C-3 | walk-forward window 防 look-ahead bias（per CR-6 + memory `feedback_indicator_lookahead_bias`）—> train/validate/test 嚴格切分 | W2-E E2 review |
| AC-S2-C-4 | Tier A productionize 不破現有 5 textbook 策略 demo runtime | W2-E E4 regression + QA empirical |
| AC-S2-C-5 | capital-tier hook 留 Tier B/C/D/E（per v5.8 §2.M10 + ADR-0036） | W2-C IMPL + V111 schema design |

### §4.4 Dispatch design — Stream C IMPL chain

```
W1-D MIT walk-forward spec + E1 IMPL Optuna cron skeleton（Python only；不依賴 V111）
  ↓
V111 spec land（Sprint 1A-γ 或 Sprint 2 內 PM #2）
  ↓
W2-C E1 IMPL V111 schema land + Optuna cron 接線 V111 config table
  ↓
W2-E E2 review walk-forward look-ahead bias scan + E4 regression
  ↓
Sprint 3+ Tier A active runtime evidence accumulation
```

**HR estimate**：40-60 hr per v5.8 §2.M10 line 379（W1-D 20-30 + W2-C 15-20 + W2-E 5-10 + buffer）

**對抗式 review 重點（W2-E E2）**：
1. **Walk-forward look-ahead bias**：strictly train < validate < test in time；不可 future leak
2. **Optuna trial cache**：cache 不 leak 跨 walk-forward window
3. **V111 schema migration idempotency**：apply twice 驗 PG empirical
4. **5 textbook 策略 demo runtime 不破**：E4 regression Mac cargo test --workspace

---

## §5 Stream D: M8 Read-Only Schema Land + ADR-0036（v5.8 §2.M8 40-60 hr）

### §5.1 Scope（v5.8 §2.M8 line 307-314）

- **Sprint 2 scope**: V109 `learning.anomaly_events` schema + ADR-0036 alignment（**Sprint 2 schema-only**）
- **NOT in Sprint 2 scope**: Statistical detector IMPL（Sprint 3 才開始；per v5.8 §2.M8 line 309）
- **Detection method（Sprint 3+）**：statistical（rolling z, ARIMA）— **不**用 HMM/GARCH（per CR-5）

### §5.2 V109 schema spec（per v5.8 §3 line 602 V109 → V112 cross-ref）

- **Anomaly domain coverage**:
  - Market regime: vol regime shift, correlation structure break, funding rate / basis dislocation
  - Own behavior: fill rate divergence, order rejection spike, slippage outlier, lease grant anomaly
- **Hypertable 必**（per v5.8 §3 line 602 "(hypertable 必)"）
- **CHECK constraint**: `severity IN ('INFO','WARNING','CRITICAL')`
- **engine_mode CHECK**: `engine_mode IN ('paper','demo','live')`（per V094 範式）

### §5.3 AC for Stream D

| AC | 內容 | 達標路徑 |
|---|---|---|
| AC-S2-D-1 | V109 anomaly_events schema land（hypertable + Guard A/B/C） | W1-F E1 IMPL |
| AC-S2-D-2 | ADR-0036 align（含 HMM/GARCH 黑名單 per CR-5）；ATR-vol + funding state 雙 axis 為 Sprint 3+ detector baseline | W1-E MIT spec |
| AC-S2-D-3 | V109 → V112 cross-ref 確立（per CR-15 5-gate auto path inheritance 為 Sprint 4+ M1 LAL spec）| W2-D E1 + PA review |
| AC-S2-D-4 | Read-only writer skeleton（Sprint 3 detector wire 進來） | W2-D E1 IMPL |
| AC-S2-D-5 | Idempotency test（apply twice）per `feedback_v_migration_pg_dry_run` | W1-F E1 + W2-E E2 review |

### §5.4 Dispatch design — Stream D IMPL chain

```
W1-E MIT V109 schema spec + ADR-0036 align + statistical method 選擇（NOT HMM/GARCH）
  ↓
W1-F E1 IMPL V109 schema land（Linux PG dry-run）
  ↓
W2-D E1 IMPL read-only writer skeleton（Sprint 3 detector 接線）
  ↓
W2-E E2 review schema migration idempotency + ADR-0036 alignment
```

**HR estimate**：40-60 hr per v5.8 §2.M8 line 308（W1-E 25-35 + W1-F 15-20 + W2-D 10-15 + W2-E 5 + buffer）

**對抗式 review 重點（W2-E E2）**：
1. **Hypertable retention + compression policy** 必設（per CR-8 V106 範式：7d chunk + 7d compression + 90d retention）
2. **HMM/GARCH 黑名單 enforcement**（per CR-5 + memory `feedback_v_migration_pg_dry_run`）
3. **V109 → V112 cross-ref FK**：V112 (M1 LAL) 引用 V109 必 soft ref（per V107 PG empirical 教訓）
4. **engine_mode CHECK**：production trading role 禁寫 learning.* table（per H-22 E3 governance）

---

## §6 Stream E: AC-19 ALT Bucket Monitor（Sprint 2 內 cross-cutting）

### §6.1 Scope（per PA Phase 1b 5/25 §4.4 + FA + QA reconcile）

- **背景**：fresh sweep 76.7% maker fill rate vs real demo 32.4%（2.4x optimistic）；BTC/ETH 66.7% vs ALT 25.8%（2.6x gap）
- **Sprint 2 期間每日 SQL bucket-split monitor**：bucket-split healthcheck [71]（per PA 5/25 §5.5）
- **6/2 14d 結束 ALT gate**：if ALT bucket < 30% → escalate spec §4.3 Option α/β

### §6.2 AC for Stream E

| AC | 內容 | 達標路徑 |
|---|---|---|
| AC-S2-E-1 | Daily SQL bucket-split SOP land（QA） | W1-G QA spec |
| AC-S2-E-2 | BTC/ETH bucket Wilson CI lower ≥ 50% sustained 14d | W3-B QA 14d verdict |
| AC-S2-E-3 | ALT bucket Wilson CI lower ≥ 15%（per spec v1.3 AC-14） | W3-B QA 14d verdict |
| AC-S2-E-4 | 6/2 ALT gate verdict — 若 < 30% → escalate spec §4.3 | W3-B PA + PM |
| AC-S2-E-5 | close_maker_audit table missing P1 carry-over（per Sprint 1B 5/25 + QA verify）| Sprint 2 cross-cutting carry-over（PM #3） |

### §6.3 Dispatch design — Stream E

```
W1-G QA + FA 14d empirical monitoring SOP land（bucket-split SQL daily fire）
  ↓
Daily QA write-up to docs/CCAgentWorkSpace/QA/workspace/reports/*
  ↓
T+7d Wilson CI projection（PA + QA）
  ↓
W3-B 14d ALT gate verdict（PA + PM if escalate）
```

**HR estimate**：10-15 hr per QA + FA inline（W1-G 10-15 + W3-B 5-8）

### §6.4 close_maker_audit missing P1 — 必須在 Sprint 2 內 land 嗎？

**PA verdict**：**屬 Sprint 1B follow-up 而非 Sprint 2 cross-cutting**

理由：
- per QA 5/25 verify report：`learning.close_maker_audit` table NOT deployed PG empirical
- Sprint 1B audit 已標 P1 但 NOT BLOCKING Sprint 2 evidence path
- AC-19 monitor 直接讀 `trading.fills`（close_maker_attempt / close_maker_fallback_reason 兩列已 land）—> 不依賴 close_maker_audit lineage table
- close_maker_audit table 是 V094 SHOULD-FIX 而非 MUST-FIX；P1 carry-over D+5~D+15 內 land 不阻 Sprint 2 evidence

**PM #3 拍**：close_maker_audit P1 是 Sprint 1B follow-up（推薦）或 Sprint 2 cross-cutting；PA 推薦 (a) Sprint 1B follow-up + ~3-5 hr E1 land V094 amend

---

## §7 Phase Chain — Sprint 2 整體流程

### §7.1 Phase 1: PA design（Day -1 → Day 0）

```
W1-A PA Stream A scope 仲裁（10-15 hr）
W1-B MIT Stream B M4 pattern miner stage 1 algorithm spec（15-20 hr）
W1-E MIT Stream D M8 V109 schema spec + ADR-0036 align（25-35 hr）
W1-G QA Stream E AC-19 ALT monitor SOP（10-15 hr）
```

並行 4-5 並行 sub-agent / 2-3 wall-clock day collapse

### §7.2 Phase 2: Wave 1+2 IMPL（Day 0 → D+12）

```
Wave 1（Day 0 → D+5）：
  W1-C E1 IMPL M4 pattern miner Rust+Python scaffold（30-40 hr）
  W1-D E1 IMPL M10 Tier A Optuna cron skeleton（20-30 hr）
  W1-F E1 IMPL V109 schema land（15-20 hr）
Wave 2（D+5 → D+12）：
  W2-A PA + MIT Stream A 新 candidate pre-spec（20-30 hr）
  W2-B E1 IMPL alpha_tournament_runner scaffold（30-40 hr）
  W2-C E1 IMPL V111 schema + Optuna cron 接線（15-20 hr）
  W2-D E1 IMPL V109 read-only writer skeleton（10-15 hr）
```

5-7 並行 sub-agent / 12d wall-clock collapse

### §7.3 Phase 3a: E2 review（D+7 → D+10）

```
W2-E E2 對抗式 review（per §1.3 W2-E）：
  - Stream B leakage scan + shift(1) verify
  - Stream C walk-forward look-ahead bias scan
  - Stream D V109 schema migration idempotency
  - Mac cargo test --workspace + node --check（per `feedback_gui_node_check_sop`）
```

per `feedback_impl_done_adversarial_review`：高風險 IMPL（M4 + M10 + V109）必走 A3+E2 對抗式 review

### §7.4 Phase 3b: E4 regression（D+9 → D+11）

```
E4 regression：
  - Mac cargo test --workspace --release（per hygiene SOP §2.2 必 Mac SSOT）
  - Mac pytest
  - Cross-language 1e-4 fixture harness（per H-18）
  - 5 textbook 策略 demo runtime 不破 verify（per AC-S2-C-4）
```

### §7.5 Phase 3c: QA empirical（D+10 → D+15）

```
W2-F QA + FA：
  - Stream B M4 leakage post-IMPL audit（per H-17 §M4-LEAKAGE-SCAN）
  - Stream D V109 anomaly_events writer skeleton runtime empirical
  - Stream E ALT bucket daily evidence累積
```

### §7.6 Phase 3d: TW Acceptance（D+13 → D+15）

```
TW：
  - 4 stream sign-off documentation（per H-22 R4 + TW 並行補位）
  - CHANGELOG.md Sprint 2 entry
  - V109/V111 ADR cross-ref（per CR-8）
```

### §7.7 Phase 3e: PM Sign-off（D+15 → D+21）

```
W3-A PA + MIT Sprint 2 evidence review
W3-B QA 14d ALT bucket gate verdict
W3-C TW + PM Sprint 2 acceptance sign-off + Sprint 3 prerequisite check
```

---

## §8 Cross-V### Dependency + Sprint 1A-γ 對齊

### §8.1 V### dependency graph

```
[V103 EXTEND (M4)] ─ Sprint 1A-α DONE ✅
  ↓
[V109 (M8 anomaly)] ─ Sprint 2 Wave 1（PA spec → V111 必先 Sprint 1A-γ land）
  ↓ cross-ref
[V112 (M1 LAL)] ─ Sprint 1A-β DONE ✅（health observations land）
  ↓
[V111 (M10 discovery tier)] ─ Sprint 2 Wave 2（V111 spec 在 Sprint 1A-γ；schema land Sprint 2）
```

**順序限制**（per v5.8 §3 line 612）：
1. Sprint 1A-β 必先 land V106/V107/V110/V112/V113 ✅（V106/V107/V112 已 land per 5/25 SSH probe）
2. Sprint 1A-γ 才能 land V105/V108/V109/V111；β → γ 不可重疊
3. **Sprint 2 派 V109 + V111 = 從 Sprint 1A-γ borrow 工時或 Sprint 1A-γ 必先 land**（PM #2）

### §8.2 Cross-Sprint dependency

```
Sprint 1A-γ（W3.5-5.5 預估，per consolidation report）
  ↓ V109/V111 spec land
Sprint 2 Day 0 + Day 1（W12-14.5）
  ↓ V109 schema deploy + V111 schema deploy
Sprint 3（W14.5-17.5）
  ↓ M8 statistical detector IMPL + M11 nightly replay
```

**PA verdict**：Sprint 1A-γ 與 Sprint 2 Day 0 並行的話 Track 1A-γ V109/V111 spec 必先於 Sprint 2 Wave 1 W1-E + W2-C 工作；PM #2 拍順序

---

## §9 PM Decision Points 待拍（3 條）

### §9.1 PM #1 — Stream A Alpha Tournament Scope 仲裁

**選項**：
- (a) PA pre-screening 5-6 candidate 採用「Sprint 2 IMPL 2（funding short + liquidation cascade）+ Sprint 2 DRAFT 1（BTC/ETH pairs）+ Sprint 3+ defer 2」
- (b) Sprint 2 改 IMPL 不同 candidate（PA 等待 PM specify）
- (c) Sprint 2 不 IMPL 新 candidate；專注 5 textbook 自然累積 + M4 自動發現 DRAFT writeback；新 source IMPL 推 Sprint 3+

**PA 推薦**：**(a)** — 平衡 ROI + Sprint 4 first Live precondition + P0-EDGE-1 AC-A (ii) closure 路徑；不阻 5 textbook 自然累積 path

### §9.2 PM #2 — Stream C V111 Spec Land Cadence

**選項**：
- (a) Sprint 1A-γ V111 spec 必先 Sprint 2 Wave 1 W1-D；Stream C 後端 Optuna IMPL 不依賴 V111；W2-C V111 schema deploy 等 1A-γ V111 spec land
- (b) Sprint 2 內 V111 spec + schema 一次 land（從 1A-γ borrow 工時）
- (c) V111 schema land 推 Sprint 3；Sprint 2 Stream C 只做 Optuna 後端 IMPL

**PA 推薦**：**(a)** — 維持 1A-γ → Sprint 2 順序依賴 cleanness；不破 v5.8 §3 line 612 順序限制；Stream C Sprint 2 reasonably scope

### §9.3 PM #3 — close_maker_audit P1 Land Cadence

**選項**：
- (a) Sprint 1B follow-up（D+5~D+15 內 E1 land V094 amend ~3-5 hr）
- (b) Sprint 2 cross-cutting（Wave 2 加一個 sub-agent）
- (c) Defer Sprint 3

**PA 推薦**：**(a)** — close_maker_audit 不阻 Sprint 2 evidence path（trading.fills 已有兩 column）；屬 Sprint 1B follow-up 性質

---

## §10 Cross-Cutting Carry-over（必加每個 sub-agent prompt）

### §10.1 M-4 hygiene SOP 警示段落（per `docs/agents/sub-agent-hygiene-sop.md` §3.5）

**所有 7 sub-agent prompt 開頭加**：
```
# Sub-Agent Hygiene Mandatory（per docs/agents/sub-agent-hygiene-sop.md）

本 prompt 之 ssh trade-core 操作必符合 hygiene SOP：
- read-only probe OK（psql SELECT / ls / cat / tail / crontab -l / fuser）
- 禁 cargo build/test/check --release（本 sprint 已 3 次 race 教訓）
- 禁寫 PG / 禁 sudo / 禁 restart 服務
- 違反 SOP 將被主會話 enforcement 介入修復 + reject 本 sub-agent 工作
```

### §10.2 角色 specific hygiene 提醒（per §3.1-§3.4 hygiene SOP）

| Sub-agent 角色 | hygiene line（per §3.1-§3.4）|
|---|---|
| E1 IMPL（sa-3 / sa-4 / sa-6） | Mac `cargo test --workspace` SSOT；Linux deploy 必經主會話派 `build_then_restart_atomic.sh` |
| E2 review（sa-5） | Mac cargo test + node --check + 讀 diff；禁 ssh trade-core 跑 cargo |
| E4 regression（sa-5） | Mac `cargo test --workspace --release` + Mac pytest + Linux read-only verify |
| MIT spec（sa-2 / sa-4 / sa-5） | psql SELECT / `python3 helper_scripts/ml/*.py --dry-run` OK；禁寫 PG / 禁真實 training |
| QA + FA（sa-7 / sa-5） | psql SELECT / read trade history OK；禁寫 PG / 禁 cargo |
| PA（sa-1） | spec only；ssh read-only probe OK；不跑 cargo |

### §10.3 Multi-session memory race 防護（per memory `project_multi_session_memory_race`）

**所有 sub-agent prompt 必加**：
- 派發前 PM 主會話 `git fetch` + `git branch -r | grep <topic>`
- sub-agent commit 必走 `git commit --only <file>`（per `feedback_git_commit_only_for_metadoc`）
- 不認識的改動禁 revert
- 接手三連加 memory log 檢查

---

## §11 派發 Readiness Checklist

### §11.1 Day -1 全鏈 closure（已 land）

| 項目 | 狀態 | Evidence |
|---|---|---|
| H-1 atomic deploy | ✅ DONE | engine PID 598276 / SHA b005bb00 / FD 200 leak fix |
| H-2 cron restore | ✅ DONE | 10/13 enabled（4 HIGH/MED + 6 SHOULD + 3 defer） |
| EA-2 verify | ✅ N/A confirmed | edge_estimate_snapshots cron active healthy 5 cycle |
| EA-4 P0-EDGE-1 AC-A amend | ✅ DONE | TODO §4 line 240 amend land |
| 4 false-positive declassify | ✅ DONE | H-3 / EA-2 / proc-exe drift / 1 其他 |
| M-4 hygiene SOP land | ✅ DONE | `docs/agents/sub-agent-hygiene-sop.md` |
| V103 EXTEND land | ✅ DONE | sql/migrations/V103__extend_m4_hypothesis_columns.sql |
| V106/V107/V112 land | ✅ DONE | Linux PG empirical verified per Sprint 1A-ζ 5/22 |
| 4 prerequisite cron active | ✅ verified | edge_label_backfill / ref21_symbol_universe / panel_aggregator / feature_baseline_writer |

### §11.2 Day 0 派發前 final go/no-go

| Gate | Status | Owner |
|---|---|---|
| PM #1 Stream A scope 拍 | 🟡 待拍 | PM |
| PM #2 V111 spec land cadence | 🟡 待拍 | PM |
| PM #3 close_maker_audit P1 cadence | 🟡 待拍 | PM |
| 7 sub-agent prompt hygiene SOP 加入 | 🟢 ready（per §10）| PM dispatch |
| Wave 1 7 並行 sub-agent dispatch 準備 | 🟢 ready | PM |
| Cross-V### dependency graph 對齊 | 🟢 ready（per §8）| PA + PM |

**GO 條件**：PM #1 + PM #2 + PM #3 拍完 + 7 sub-agent prompt 加 hygiene → Wave 1 派 Day 0 collapse

**No-go 條件**：PM #1-#3 任一未拍 OR hygiene SOP 未加入 prompt OR Sprint 1A-γ V109/V111 spec readiness 未明朗

### §11.3 Sprint 4 First Live Precondition Impact

**Stream A 14d demo evidence accumulation → P0-EDGE-1 closure 路徑**：

per EA-4 amend P0-EDGE-1 AC-A (ii)：
- ≥ 3 個 alpha-bearing 策略（含 Sprint 2 Alpha Tournament + Sprint 3+ 新 alpha source）達 demo 7d threshold（avg_net > 5bps + Wilson CI lower > 0 + n ≥ 30）

**Sprint 2 期內**：
- W2-B IMPL 2 個 candidate（funding short + liquidation cascade）
- W3-A 14d demo accumulation review（≥ 30 n_fills 達標）
- Sprint 3+ Stage 0 → 0R verdict（≥ 1 達 7d avg_net > 5bps + Wilson CI lower > 0）

**Sprint 4 First Live precondition unblock timeline**：
- Sprint 2 結束 ≈ W14.5 → Stream A 2 candidate 14d demo accumulation 達標
- Sprint 3 ≈ W14.5-17.5 → Stage 0 0R verdict + portfolio attribution
- **Sprint 4 First Live W17.5-20.5 起跑 precondition**: 至少 1 candidate alpha-bearing 7d avg_net > 5bps + Wilson CI lower > 0 +（或）portfolio-level gross 正

**結論**：Sprint 2 Stream A 是 Sprint 4 First Live precondition closure 的**唯一前置工作**之一（P0-EDGE-1 closure 路徑）

---

## §12 Sprint 2 Wave 1 Day 0 Dispatch Sequence（5min stagger）

per memory `project_multi_session_memory_race` + Sprint N+1 D+0 5min stagger 範式：

| 時段 | Dispatch | Action |
|---|---|---|
| T+0 | W1-A PA Stream A scope 仲裁 | PA single-thread 10-15 hr；不 stagger |
| T+5min | W1-B MIT Stream B M4 algorithm spec | MIT single-thread；並行 W1-A |
| T+10min | W1-E MIT Stream D V109 + ADR-0036 | MIT 第二 sub-agent；並行 W1-A+W1-B |
| T+15min | W1-G QA Stream E ALT bucket monitor | QA single-thread；並行前 3 |
| T+20min | W1-D E1 IMPL Stream C Optuna 後端 | E1 第一個（不依賴 W1-D MIT spec — 後端不依賴 V111）|
| T+25min | W1-C E1 IMPL Stream B M4 scaffold | wait W1-B spec ~3-5 hr → 派；非 T+25min |
| T+30min | W1-F E1 IMPL Stream D V109 schema land | wait W1-E spec ~6-10 hr → 派 |

**真實 sequential dispatch**：T+0 → T+20min 並行派 4 個 spec/QA sub-agent（W1-A/B/E/G + W1-D 後端）；W1-C/F 等 spec ready 後 ~5-10 hr 內派

**並行 ceiling**：T+30min 後 max 5-7 sub-agent 同時 active；W1-A/B/D/E/G + W1-C/F 接力

---

## §13 16-Root-Principles Compliance Pre-Check

per `.claude/skills/16-root-principles-checklist` + DOC-01 V2 §5.1-§5.16：

| # | 原則 | 4 stream 整體 status | 驗證點 |
|---|---|---|---|
| 1 | Single controlled write entry | ✅ | 所有 candidate alpha 經 IntentProcessor + Rust order_dispatch_tx |
| 2 | Read/write separation | ✅ | M4 pattern miner DRAFT writeback only；sweep + Optuna 純 read-only |
| 3 | AI output → Decision Lease | ✅ | M4 DRAFT 不直接 trigger trading；Stream A new candidate live 必經 Lease + LAL |
| 4 | Strategies cannot bypass risk | ✅ | candidate alpha 5-gate auto path inheritance per CR-15 |
| 5 | Survival > profit | ✅ | hard stop / liquidation buffer 不受 Sprint 2 改動影響 |
| 6 | Uncertainty → conservative | ✅ | M4 minimum bar 6 attribute；missing → DRAFT 不寫 |
| 7 | Learning ≠ live rewrite | ✅ | V103/V109/V111 全 learning.* schema；production trading role 禁寫（per H-22 E3） |
| 8 | Trade reconstructable | ✅ | trading.fills 已有 close_maker 兩 column；V094 P1 land 後完整 |
| 9 | Local + exchange protection | ✅ | engine cancel_token + Bybit retCode 失敗 fail-closed 不受影響 |
| 10 | Fact / inference / assumption | ✅ | 本 packet 明確 tag Sprint 1B PA Phase 1b PG 跨檢 / sweep predicate vs runtime |
| 11 | Agent autonomy within P0/P1 | ✅ | Sprint 2 不擴張 agent 能力；不改 P0/P1 邊界 |
| 12 | Evolve from evidence | ✅ | 4 stream 全 evidence-driven（per P0-EDGE-1 AC-A amend 解雞蛋論）|
| 13 | AI cost-aware | ⚠️ M4 stage 1 IMPL 階段不破 DOC-08 月 $60 cap；Sprint 3+ Cowork review 才上 LLM | M4 stage 1 = 純 statistical pattern miner |
| 14 | Zero external cost runnable | ✅ | Sprint 2 不依賴 LLM；pattern miner 純 Rust+Python+pandas |
| 15 | Multi-agent collaboration | ✅ | PA → MIT → E1 → E2 → E4 → QA → TW → PM 正式 chain |
| 16 | Portfolio-level risk | ✅ | Stream A candidate alpha 必經 portfolio sizing per 3% risk/trade |

**Hard boundary grep**（per CLAUDE.md hard boundaries）：
```
grep -nE '(execution_state|execution_authority|live_execution_allowed|decision_lease_emitted|max_retries|OPENCLAW_ALLOW_MAINNET|live_reserved|authorization\.json)' <diff>
```
**Sprint 2 IMPL diff 0 觸碰預期**：所有 stream 寫 learning.* schema + Optuna 後端 + alpha_tournament_runner scaffold；不改 execution 路徑

**Compliance rating（pre-IMPL）**：A — 16/16 + 0 hard boundary touch（IMPL 後 Wave 2 E2 review verify）

---

## §14 PA Push-back / Open Questions

### §14.1 Push-back items

1. **Sprint 2 4 stream + Stream A 拆 3 軌（A1/A2/A3）= 真實 5 stream 並行**：超過 v5.8 §4 line 624 "4-stream" naming；本 packet 拆 5 軌但維持 v5.8 §4 命名 "4 stream + Stream A 3 軌"；建議 PM 不破 v5.8 §4 命名 + 接受 5-7 並行 sub-agent capacity

2. **Stream A scope 與 v5.7 §7 Alpha Tournament 概念 vs v5.8 §2 沒明寫衝突**：v5.7 §7 spec'd Alpha Tournament 為「strategy candidates round-robin demo 7d → top picks promote」；v5.8 §2 沒重複定義；本 packet 沿用 v5.7 + EA-4 amend 解讀；建議 PM 接受此解讀 or 標明衝突由 PA 重 spec

3. **Stream C V111 spec land 在 Sprint 1A-γ vs Sprint 2 是 priority conflict**：本 packet PM #2 拍順序但若 Sprint 1A-γ V111 spec timeline 滑（Sprint 1A 真實 8.5w per consolidation report），Stream C Sprint 2 Wave 2 V111 schema deploy 會延後到 Sprint 3 開頭；建議 PM 允許 Sprint 2 Stream C V111 schema deploy 滑至 Sprint 3 Day 0 不阻 Sprint 2 evidence

4. **Stream E ALT bucket monitor 6/2 14d gate 落 Sprint 2 中段 vs Sprint 2 末段**：14d gate clock 從 2026-05-19 起算（commit `820f0532` deploy），6/2 落 Sprint 2 結束前 11-13d；本 packet W3-B 排 D+15~D+21；建議 PM 接受 6/2 verdict timing match Sprint 2 末段

### §14.2 Open questions

1. **Sprint 1A-γ Day 0 / Wave 1 dispatch readiness**：本 packet 假設 Sprint 1A-γ V109/V111 spec 在 Sprint 2 Day 0 起跑前 land；如 1A-γ 未起跑 → Stream D + Stream C Wave 1 W1-E + W1-D MIT spec 需先補 V109/V111 spec draft（額外 30-50 hr）— 待 PM 確認 Sprint 1A-γ 起跑時間

2. **5-6 候選 alpha source pre-screening 經 FA business audit 否定可能性**：本 packet PA pre-screening 推薦 2 candidate IMPL；FA 可能不同意 ROI ranking；建議 W1-A PA scope 仲裁 + W2-A 階段 FA inline review

3. **Sprint 2 結束時 5 textbook 自然累積進度**：5 textbook 殭屍策略 7d demo 累積仍可能不達 P0-EDGE-1 AC-A (i)；Sprint 4 First Live precondition closure 仍依賴 Stream A 至少 1 candidate 達標；建議 PM 接受 P0-EDGE-1 AC-A (ii)/(iii) 為 Sprint 4 First Live closure 主路徑

---

## §15 References

- v5.8 主檔 `srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md` §2 M4/M8/M10 + §4 line 624
- v5.7 主檔 `srv/docs/execution_plan/2026-05-20--execution-plan-v5.7.md` §7-10
- v5.8 dispatch consolidation `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md`
- PA Phase 1b cell selection `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-25--phase_1b_calibration_cell_selection.md`
- H-2 final SOP `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-25--h2_ea2_final_sop_refine.md`
- M-4 hygiene SOP `srv/docs/agents/sub-agent-hygiene-sop.md`
- TODO §1.2 + §4 + §-2 + §0
- Memory: `project_multi_session_memory_race` + `feedback_pnl_priority_over_governance` + `feedback_indicator_lookahead_bias` + `feedback_v_migration_pg_dry_run` + `feedback_impl_done_adversarial_review` + `feedback_fetch_before_dispatch`
- Skills: `spec-compliance`, `quant-strategy-design`, `ml-pipeline-maturity-audit`, `16-root-principles-checklist`

---

## §16 Conclusion

**Sprint 2 Day 0 dispatch packet design verdict**：**DISPATCH-PARTIAL-READY**

- 4 stream 拆 5 軌 + Stream A 拆 3 軌（A1/A2/A3）= 真實 5 work stream
- 總 hr 248-351 / wall-clock 3w（W12-14.5）≈ v5.8 §4 280-400 hr 對齊
- Wave 1 7 並行 sub-agent / Wave 2 5-6 並行 / Wave 3 single-thread 收口
- 3 條 PM decision point 待拍（§9）：Stream A scope + V111 cadence + close_maker_audit P1
- Cross-cutting：M-4 hygiene SOP 全 7 sub-agent prompt 加 + multi-session race 防護
- Sprint 4 First Live precondition：Stream A 14d demo evidence accumulation = P0-EDGE-1 AC-A (ii) closure 唯一前置路徑

**派發 readiness verdict**：PM #1-#3 拍完 + 7 sub-agent prompt 加 hygiene → Wave 1 Day 0 collapse；非阻 5 textbook 自然累積 + EA-2 healthy + M11 nightly replay defer Sprint 3

---

**Report END**

PA DESIGN DONE: report path: `/Users/ncyu/Projects/TradeBot/srv/docs/execution_plan/2026-05-25--sprint_2_business_dispatch_packet.md`
