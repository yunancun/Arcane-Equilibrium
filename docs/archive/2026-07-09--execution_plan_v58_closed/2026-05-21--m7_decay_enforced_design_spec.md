---
spec: M7 Decay Detection + Single Decay Authority + DECAY_ENFORCED Lifecycle Design
date: 2026-05-21
author: QC consultant draft (transcribed by PM 主會話 due to QC sub-agent tool boundary)
phase: v5.8 Sprint 1A-β CRITICAL DESIGN
status: SPEC-DRAFT-V0
parent specs:
  - docs/execution_plan/2026-05-20--execution-plan-v5.8.md §2 M7
  - docs/adr/0044-m7-decay-enforced-single-authority.md（M7 single decay authority；R4 audit H-3 reverse-ref patch 2026-05-21）
  - docs/execution_plan/2026-05-21--m11_threshold_m7_dedup_decay_enforced_rename.md
  - docs/execution_plan/2026-05-21--v113_m7_decay_signals_schema_spec.md
  - docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md §CR-7 + §H-11
scope: design / spec only — 不寫 IMPL code；不假設 V107/V112 schema 細節；不違背 14d × 50% mitigation
---
> ⚠️ 归档历史文档 — 非当前权威。active 状态见 repo 根 `TODO.md`；本文件仅供历史/审计参考。（2026-07-18 审计批量补入）


# M7 Decay Detection + Single Decay Authority + DECAY_ENFORCED Lifecycle Design

## §1 Context + 為什麼

### 1.1 v5.8 §2 M7 module 出處

v5.8 §2 line 253-277 列出 4 種 decay signal + 6 state lifecycle（NORMAL_LIVE / DECAY_DETECTED / DEMOTE_PROPOSED / DECAY_ENFORCED / RECOVERY / RETIRED；註：STAGE_DEMOTED 改名 per CR-7）。Reviewer round-16 + CR-7 共識 catch：
- M7/M8/M11 三 module 各自獨立 decay decision → 雙 demote 反模式（alert fatigue + recovery path 模糊）
- M7 應為 single decay authority；M11 只 emit signal，不寫 strategy_lifecycle
- ad-hoc per-strategy decay 評估（各 strategy 自評 30d Sharpe + drawdown + N consecutive loss）缺統一 governance + audit trail

### 1.2 為什麼 single decay authority

1. **Traceability**：任一 demote / retire decision 都能追溯到唯一 `strategy_lifecycle.lifecycle_id`（CR-7 contract）
2. **Dedup**：M11 daily nightly replay divergence event 與 M7 30d Sharpe degradation 在 empirical study 信號重疊 60-70%（QC 5.21 v58 audit Risk 3）→ 各自獨立 demote 等於同事件 alert × 2
3. **Recovery path clarity**：single state machine 才能定義「何時 promote 回 NORMAL_LIVE」；多 authority 各自 demote 各自 recovery 邏輯衝突
4. **Operator 心智負擔**：5 strategy × 4 signal type × 6 lifecycle state = 120 combinatorial event source；single authority 收斂為 5 × 6 = 30 active state visibility

### 1.3 DECAY_ENFORCED rename motivation（per CR-7）

原 v5.8 `STAGE_DEMOTED` 字面含「STAGE」三字，與：
- AMD-2026-05-15-01 Stage 0 / 0R / 1 / 2 / 3 / 4（canary promotion gate）
- ADR-0034 LAL 0 / 1 / 2 / 3 / 4（Decision Lease Layered Approval）

跨領域字面碰撞。SQL query（`WHERE state = 'STAGE_DEMOTED'`）在 ETL / dashboard 易與 `stage_history.stage = 'Stage 1'` 邏輯混淆。

`DECAY_ENFORCED` 直接對應 M7 decay action 域，無跨域字面重疊。

---

## §2 Decay Signal 4 種 — 數學推導

### 2.1 Signal A: Sharpe Decay（rolling 30d）

**公式**：
```
sharpe_30d(t) = (mean_R_30d(t) - rf) / std_R_30d(t) * sqrt(N_trade_per_30d)
```

- `R` = per-trade net PnL（扣 fee + slippage + funding）
- `rf` = risk-free rate = 0（crypto convention）
- `N_trade_per_30d` annualization factor（per-strategy 不同；high-freq strategy 如 grid > 1000 trade/30d，swing strategy < 100）
- **Leak-free**：30d window 必 `.shift(1)` 避 current bar 污染（per memory `feedback_indicator_lookahead_bias`）

**Threshold**：
- per-strategy baseline = expanding window mean + 1.5 σ（extrapolating first 90d strategy data）
- decay trigger：`sharpe_30d(t) < baseline_mean - 1.5 × baseline_std`（約覆蓋 lower 6.7% tail）
- **多重檢驗校正**：5 strategy × 90d window × 4 signal type = 1,800 evaluation；Bonferroni α=0.05/1800=2.8e-5 → 對應單側 z=4.0；故 1.5σ trigger 必加 **second confirmation**（連續 5 trading day 都觸發才 escalate）

**Window 為何 30d**：
- 短於 30d → 樣本量不足；< 30d 估計 sharpe 標準誤過大
- 長於 30d（如 90d）→ regime shift 反應慢；crypto regime 5-10d 可完整轉換
- **OOS context**：walk-forward train 90d / test 30d 的 test 部分；30d Sharpe 是 OOS performance proxy

### 2.2 Signal B: Drawdown Widening

**公式**：
```
dd_max_7d(t) = max over k in [0, 6]: (peak_pnl(t-k) - pnl(t-k)) / peak_pnl(t-k)
```

- `peak_pnl(t-k)` = running max PnL from strategy inception to t-k
- 7d window 捕捉短期 cluster losing trade

**Threshold**：
- per-strategy Stage 4 envelope max DD（per AMD-2026-05-15-01 stage envelope）
- decay trigger：`dd_max_7d(t) > envelope_max_dd × 0.8`（80% envelope warning）/ `> envelope_max_dd × 1.0`（envelope breach → automatic CRITICAL）

**Window 為何 7d**：
- 短於 7d → 單日大 drawdown 可能 noise；7d 強制 sustained pressure
- 長於 7d → 已嚴重，預警晚

### 2.3 Signal C: OOS Degradation

**公式**：
```
oos_deg = (live_30d_Sharpe - backtest_OOS_Sharpe) / backtest_OOS_Sharpe
```

- `live_30d_Sharpe` 同 §2.1
- `backtest_OOS_Sharpe` = strategy promotion 前 walk-forward OOS Sharpe（recorded in `learning.hypotheses.expected_sharpe`）

**Threshold**：
- normal degradation expected：live/OOS Sharpe ratio ~0.5-0.8（per `walk-forward-validation-protocol` §6.3）
- decay trigger：`oos_deg < -0.6`（live < 40% × backtest OOS）
- **OOS window**：90d backtest OOS vs 30d live — 不同 window length 比較有 bias，故 V113 schema 必同時記錄 `live_window_days` + `oos_window_days` 兩 column

### 2.4 Signal D: Hit-rate Plummet

**公式**：
```
hit_rate_30d = (sum I[R_i > 0] for i in last 30d) / N_trade_30d
```

**Threshold**：
- per-strategy baseline hit rate（Sprint 1B Alpha Tournament dataset 提供 baseline）
- decay trigger：`hit_rate_30d < baseline_hit_rate - 0.15`（絕對 15% 下降）
- **Caveat**：hit rate 單獨無法判定 edge（memory `feedback_pushback`：MA 64% 勝率折算為實質 37.8%）；故 §3 multi-source confirmation 必納

### 2.5 為什麼 4 signal 並用而非單 signal

QC 5.21 v58 audit 證 4 signal 兩兩 Spearman 相關 0.4-0.6（中相關，未到融合無價值的 0.7 redundant 閾值）。Multi-source confirmation 設計：
- 單 signal trigger → DRAFT advisory，no state transition（per CR-7 dedup contract）
- 2+ signal trigger → NORMAL_LIVE → DECAY_DETECTED transition
- 3+ signal trigger → DECAY_DETECTED → DEMOTE_PROPOSED automatically（cuts operator approval lag）

---

## §3 Lifecycle FSM — 6 enum + Transition Rule + Dwell Time

### 3.1 6 enum（per CR-7 rename）

| State | 語意 | 對應 strategy 行為 |
|---|---|---|
| **NORMAL_LIVE** | healthy，full size | Stage 4 sizing per Stage envelope |
| **DECAY_DETECTED** | 2+ signal triggered，in observation | full size（不改 sizing 但 alert + 14d clock 啟動）|
| **DEMOTE_PROPOSED** | 3+ signal triggered OR DECAY_DETECTED 14d 未 recovery | Allocator generates demote proposal；awaits LAL approval |
| **DECAY_ENFORCED** | 50% sizing scaled；14d review observation window | live size × 0.5 |
| **RECOVERY** | DECAY_ENFORCED 14d 結束 + recovery criteria pass | transition back to NORMAL_LIVE（full size 不立即還原；漸進 7d gradient back to 100%）|
| **RETIRED** | DECAY_ENFORCED 14d 結束 + recovery criteria fail OR §9 14d × 50% 累積虧損 | size = 0；strategy halt；30d cooling period 後可 re-Stage 0R promotion path |

### 3.2 Transition Rule + Dwell Time

| Transition | Trigger | Dwell time | Approval requirement |
|---|---|---|---|
| NORMAL_LIVE → DECAY_DETECTED | 2+ signal source trigger | min 0，max ∞ | none（M7 自動）|
| DECAY_DETECTED → DEMOTE_PROPOSED | 3+ signal source trigger OR dwell ≥ 14d still triggered | min 14d（sustained）；max 30d | M7 自動 emit proposal |
| DEMOTE_PROPOSED → DECAY_ENFORCED | LAL approval（Y1 operator；Y2 LAL 1 auto-approve 30d-stable strategy per ADR-0034）| min 0 hr；max 72 hr（else escalate to operator）| LAL 0/1 approval |
| DECAY_ENFORCED → RECOVERY | 14d observation + recovery criteria pass（§3.3）| exactly 14d | M7 自動 |
| DECAY_ENFORCED → RETIRED | 14d observation + recovery criteria fail OR §9 trigger | exactly 14d（normal）OR 即時（§9 反向 attack mitigation）| M7 自動；retired 需 operator opt-in 才 re-Stage 0R |
| RECOVERY → NORMAL_LIVE | 7d gradient back to 100% size + no new decay signal | exactly 7d | M7 自動 |
| RETIRED → NORMAL_LIVE | 30d cooling + operator manual re-promotion through Stage 0R/1/2/3/4 path | min 30d | operator + Stage gate |

### 3.3 Recovery Criteria（DECAY_ENFORCED → RECOVERY）

DECAY_ENFORCED 14d 觀察期內必同時滿足 4 條：
1. **No new decay signal trigger** in last 7d（signal A/B/C/D 全 below threshold）
2. **Sharpe 30d > 0**（rolling 30d 含 14d at reduced size + before）
3. **Hit rate 30d > baseline - 0.05**（允許 5% 退化 vs 原 baseline）
4. **No M11 CRITICAL divergence** in last 14d（per §6 M7 ↔ M11 dedup）

任一條 fail → DECAY_ENFORCED → RETIRED。

### 3.4 為什麼 14d window

14d 選擇基於：
- crypto regime shift cycle 估計 5-10d（per QC `quant-strategy-design` skill §半衰期 analysis）
- 14d > 1 regime cycle 確保 observation 涵蓋 regime transition 完整
- < 14d → 過早 retire；> 14d → 過長（50% size 期間 capital 機會成本）

---

## §4 Retrain Trigger — 何時 / Cooldown / 不可循環

### 4.1 Trigger Map

| Signal | retrain trigger? | rationale |
|---|---|---|
| A Sharpe decay | YES（gated）| 可能是 regime shift；retrain on new regime data 可能 recover |
| B Drawdown widening | NO | drawdown 是 risk 指標非 edge 退化指標；retrain 不改 risk model |
| C OOS degradation | YES（gated）| live/OOS gap 可能是 backtest overfitting 或 regime shift |
| D Hit rate plummet | YES（gated）| 常與 Sharpe decay 共現 |

### 4.2 Cooldown

- **per-strategy retrain cooldown**：7d minimum between retrains
- **per-trigger cooldown**：同 signal 30d 內 retrain ≤ 2 次（避免循環）

### 4.3 不可循環觸發 protection

防 retrain → fail to recover → retrain again 死循環：
- **retrain attempt counter**：per strategy 30d window 內 retrain ≥ 2 次仍未 recover → 強制 transition DECAY_ENFORCED 不進 RECOVERY
- **mandatory RETIRE after 3 failed retrain**：30d 內 3 次 retrain 仍未 recover → 跳過 14d observation 直接 RETIRED
- **retrain rollback gate**：新 retrain model OOS Sharpe 必 > 舊 model OOS Sharpe × 0.95；否則 retrain 視為失敗（per memory `feedback_pushback` 統計顯著性原則）

---

## §5 Decay Window — Sharpe 30d vs OOS 90d Rationale

### 5.1 Sharpe 30d（live）

- 樣本量考量：high-freq strategy 30d ~300-1000 trade，swing 50-100 trade；≥ 30 trade 是 t-test power ≥ 0.5 最低門檻
- regime responsiveness：crypto regime 5-10d 完整轉換；30d 涵蓋至少 3 個完整 regime 但仍 timely
- **trade-off**：短於 30d → std 不穩；長於 30d → regime shift lag

### 5.2 OOS 90d（backtest）

- backtest OOS 段標準長度：walk-forward train 90d / test 30d；累計 OOS Sharpe 通常 90-180d
- 樣本量充足供 PSR(0) > 0.95 + DSR multiple testing 修正
- **比較 caveat**：live 30d vs backtest 90d 是不同 window length，故 V113 schema 必同時記錄 `live_window_days` + `oos_window_days`

### 5.3 Drawdown 7d（live）vs envelope（backtest）

- 7d short window 捕短期 cluster losing trade
- envelope max DD = backtest Stage 4 期間最大 DD（per AMD-2026-05-15-01）
- **Caveat**：envelope 是 backtest 估計，真實 fat tail 下 envelope 可能低估；故 §2.2 80% envelope = warning，100% envelope = automatic CRITICAL

### 5.4 Hit rate 30d（live）vs baseline（Sprint 1B Alpha Tournament）

- baseline 來自 Sprint 1B Alpha Tournament dataset
- 30d window 對齊 Sharpe 30d 一致性

---

## §6 M7 ↔ M11 Dedup（per CR-7 contract）

### 6.1 Authority 邊界（per m11_threshold_m7_dedup_decay_enforced_rename §3.1）

| Module | Role | 不可做 |
|---|---|---|
| **M11** | counterfactual replay engine + divergence detector + signal emitter | 不 trigger demote；不寫 `strategy_lifecycle`；不改 sizing |
| **M7** | sole decay authority；ingest M11 signal + 自身 4 signal source | 不 own replay；不寫 `replay_divergence_log` |

### 6.2 M11 → M7 Signal Flow

```
M11 nightly replay → 計算 5d baseline + 評估 Δ vs μ + σ
  ├── Δ < μ + 0.5σ → NOISE（silent）
  ├── Δ < μ + 2.5σ → noise band（silent）
  ├── Δ ≥ μ + 2.5σ → WARN（write replay_divergence_log）
  └── Δ ≥ μ + 3.0σ → CRITICAL（write log + emit M7 signal source 5）

M7 ingest signals（5 source: A/B/C/D + M11 WARN/CRITICAL）：
  - M11 WARN single occurrence: NO M7 signal（under noise band edge）
  - M11 CRITICAL or M11 WARN 持續 14d: count as M7 1-of-5 signal source
  - 2+ source trigger（含 M11）→ DECAY_DETECTED
```

### 6.3 M7 不重複計算 M11 已驗 signal（per CR-7）

V107 schema 必含 column `persistent_days` 計算 same strategy 連續 days with WARN/CRITICAL；M7 query when `persistent_days >= 14` count as 1-of-5 signal source。

### 6.4 雙 demote 反模式 mitigation

- M11 結構上不可 demote（V107 schema 無 `auto_demote` / `target_state` / `demote_proposal_id` field）
- 同 strategy 同日同時被 M11 CRITICAL + 自身 Sharpe trigger → M7 multi-source confirm 一次 transition（不是 2 transition）
- Recovery 時 M11 stale signal TTL 14d（與 §3 observation window 對齊）

---

## §7 M7 ↔ M6 Reward — DEGRADING auto downweight，SUSPENDED out of portfolio

### 7.1 M6 Reward context

M6 = multi-objective reward function tuning（v5.8 §2 line 215-251）；λ_dd / λ_tail / λ_turnover / λ_slippage / λ_decay 動態調整 strategy weight in Auto-Allocator capital allocation。

### 7.2 M7 state → M6 weight mapping

| M7 state | M6 weight adjustment |
|---|---|
| NORMAL_LIVE | full weight（per Auto-Allocator base）|
| DECAY_DETECTED | weight × 0.8（預警）|
| DEMOTE_PROPOSED | weight × 0.6（進入 pending）|
| DECAY_ENFORCED | weight × 0.5（與 sizing 50% 同步）|
| RECOVERY（7d gradient）| weight ramp 0.5 → 1.0 over 7d |
| RETIRED | weight = 0（out of allocation pool）|

### 7.3 Enforce path

- M7 emit `decay_action_level` change event
- M6 Reward 訂閱 event → recompute portfolio weight + emit Allocator proposal
- Allocator proposal 走 LAL approval（Y1 operator；Y2 LAL 1/2 per ADR-0034）

---

## §8 M7 ↔ M1 LAL — RETIRED → Tier 0 active blocker（per CR-2）

### 8.1 LAL Tier mapping（per ADR-0034）

| LAL Tier | Authority | Auto-approval criteria |
|---|---|---|
| LAL 0（per-fill）| always autonomous（Guardian）| base 5-gate |
| LAL 1（intra-strategy reparam）| auto after Stage 4 + 30d stable | 80% yes-rate window |
| LAL 2（cross-strategy reweight）| Advisory Y1 / Auto Y2 | gate criteria |
| LAL 3（new strategy promotion）| always operator | — |
| LAL 4（capital structure）| always operator | — |

### 8.2 RETIRED strategy active blocker

per CR-2：strategy RETIRED state → **all LAL Tier 0 fill attempts on that strategy MUST fail-closed**。

V112（M1 LAL schema）必含 query path：
```sql
-- 5-gate Tier 0 fill 必含 strategy decay state check
SELECT current_decay_action_level
FROM learning.strategy_lifecycle
WHERE strategy_name = $1
ORDER BY entered_at DESC
LIMIT 1;
-- IF current_decay_action_level = 'RETIRED' → fill rejected
```

### 8.3 為什麼 active blocker not opt-in

per ADR-0034 + AMD-2026-05-21-01：
- LAL 0 是 always autonomous Guardian 域
- RETIRED 是 strategy 已被判定為 alpha-deficient 永久退役
- 若 RETIRED 仍允許 LAL 0 fill → 等同 retire 形同虛設
- LAL 4 operator manual override 也禁用（per AMD-2026-05-21-01 protected scope）

僅 operator manual re-promotion through Stage 0R 路徑可從 RETIRED 拉回 NORMAL_LIVE。

---

## §9 反向 Attack — 14d × 50% 持續虧 Mitigation（per H-11 + AMD-2026-05-21-01）

### 9.1 攻擊場景

per H-11 反向 attack 第 4 條 + reviewer round-16 catch：

**場景**：strategy 進入 DECAY_ENFORCED（50% sizing）後，14d observation window 內持續虧損 → 累積 -50% account drawdown（within strategy scope）→ operator（per LAL 4 manual override path）仍可繞 M7 自動 retire 將 strategy 拉回 full size 並期待 mean revert。

**為什麼必 mitigation**：
- 50% sizing × 14d × per-trade -2% loss = ~-25% to -50% cumulative within strategy capital（per QC empirical via 5 strategy fat-tail simulation）
- 已被 M7 判定 decay 的 strategy 拉回 full size 期待反彈 = 賭博（memory `feedback_pushback`：「策略無 edge 時加倉是反指標」）
- LAL 4 operator override 設計初衷 = 處理 emergency，不是繞 M7 decay decision

### 9.2 Mitigation Spec

per AMD-2026-05-21-01 `protected scope`：
- **Trigger condition**：`cumulative_pnl_in_decay_enforced_state < -0.5 × pre_decay_account_value_of_strategy`（within 14d observation）
- **Action**：強制 transition `DECAY_ENFORCED → RETIRED` 即時（不等 14d 結束）
- **Operator LAL 4 manual override 邊界**：AMD-2026-05-21-01 寫入 protected scope；operator 不可 override `RETIRED → NORMAL_LIVE`（只能走 30d cooling + Stage 0R re-promotion 路徑）

### 9.3 Mathematical justification

per QC `quant-strategy-design` skill §半衰期 analysis：
- crypto regime shift 5-10d；strategy decay 14d × 50% sizing 仍累積 -50% account drawdown → 結構性 edge 已 dead，不是 transient regime
- Kelly fractional 反推：若策略真有 edge `p × b - q > 0`，50% sizing × 14d 應 break-even or positive；持續 -50% drawdown → empirical evidence f* ≤ 0
- per CLAUDE.md priority order：「account survival > 風控 > system health > ... > real net PnL > autonomy evolution」— operator override 屬 autonomy evolution 邊界，不可越 account survival 上邊界

### 9.4 Schema enforcement

V113 `strategy_lifecycle` table 必含：
- column `cumulative_pnl_during_decay` NUMERIC 即時追蹤
- CHECK constraint enforcement：若 transition 至 RETIRED 是 §9 trigger，`triggering_signal_id` 必 reference 一個 special `decay_signal_source = 'cumulative_loss_50pct_in_decay_enforced'`
- M7 IMPL 階段 reject LAL 4 operator override 任何 `RETIRED → NORMAL_LIVE` 嘗試

---

## §10 Acceptance Criteria

| # | Criteria | Test |
|---|---|---|
| **AC-1** | M7 6-state FSM 完整 proptest | E4 cargo test：proptest 100 random transition sequence；invalid transition（如 NORMAL_LIVE → RECOVERY skip 步驟）必 RAISE |
| **AC-2** | 4 decay signal threshold 1e-4 cross-language fixture | Rust IMPL + Python replay 同一（strategy，symbol，30d data）算 sharpe_30d / dd_max_7d / oos_deg / hit_rate_30d 差 < 1e-4 |
| **AC-3** | 14d × 50% cumulative loss test | proptest：simulate DECAY_ENFORCED state + 14d daily -3.5% strategy P&L（cumulative -49%）→ M7 必 transition RETIRED 不待 14d 結束 |
| **AC-4** | M11 CRITICAL → M7 ingest（dedup）test | empirical INSERT V107 row with `persistent_days=14` → M7 query path 必 count as 1-of-5 signal source；同日 M7 自身 Sharpe trigger → multi-source confirm 一次 transition（not 2）|
| **AC-5** | RETIRED → LAL 0 fill fail-closed test | empirical insert V113 row `current_decay_action_level='RETIRED'` → LAL 0 5-gate query path 必 reject fill attempt + audit log record |
| **AC-6** | retrain cooldown enforcement | 7d 內 2 次 retrain attempt 必有 second attempt 必 reject + 30d 內 3 次 retrain 失敗必強制 RETIRED |
| **AC-7** | Engine restart sqlx migrate runtime pass | per V094 §5 範式：restart_all.sh --rebuild → V113 _sqlx_migrations.success=t + engine.log 0 panic |

---

## §11 IMPL Phase

### 11.1 Sprint 4-5：M7 Read-only

- V107 + V113 schema land（Sprint 1A-β）
- M7 ingest 5 signal source + 寫 `learning.decay_signals`（signal observation only）
- 不寫 `strategy_lifecycle`（no state transition）
- daily summary Slack to operator（transparency only，no action）

### 11.2 Sprint 7+：M7 Advisory

- M7 state machine activated；transitions written to `learning.strategy_lifecycle`
- DECAY_DETECTED → DEMOTE_PROPOSED 自動 emit proposal
- DEMOTE_PROPOSED → DECAY_ENFORCED 需 LAL 0 operator approve（Y1）
- 14d observation + recovery / retire 自動 evaluate

### 11.3 Sprint 8：M7 Auto-suspend

- LAL 1 auto-approve 30d-stable strategy decay（per ADR-0034 Decision 3）
- DEMOTE_PROPOSED → DECAY_ENFORCED 可 LAL 1 auto-approve
- §9 14d × 50% cumulative loss mitigation hard-coded enforcement
- M6 Reward weight auto downweight per §7.2 mapping

---

## §12 Cross-V### Dependency

| V### | 依賴 | 理由 |
|---|---|---|
| V113（own）| — | M7 decay_signals + strategy_lifecycle |
| V107（M11 replay_divergence_log）| source 5 ingest with `persistent_days` column | M7 不重複計算 M11 已驗 signal |
| V112（M1 LAL）| RETIRED → Tier 0 active blocker query | per CR-2 + §8 |
| V108（M9 A/B test）| A/B variant 若 DECAY → 同 strategy 同等對待 | Sprint 1A-γ |
| V098（governance.audit_log）| governance_approval_id FK target | already land |

Sprint 1A-β dispatch order：V107 → V113 → V112（per PA dispatch consolidation §CR-9）

---

## §13 Open Questions

### Q1：M7 ingest M11 CRITICAL 為 1-of-5 還是 1-of-4 signal source？

§2 文字寫 4 signal（A/B/C/D）；§6 + AC-4 將 M11 升為 5th source。是否與 v5.8 §2 M7 line 262 第 4 條「Counterfactual replay（M11）shows strategy underperforming baseline by ≥ X bps」共用（即 M11 = signal D 替代，仍 4 source）還是新增（5 source）？

**QC 建議**：5 source（避 hit rate vs M11 強行混用）；待 PA + MIT 仲裁。

### Q2：14d × 50% mitigation threshold 是否動態 per strategy 還是統一 -50%？

§9 寫死 -50%。但 5 strategy capacity scale 不同（grid 容量 $1-5k，bb_breakout $10-30k）。若 grid 14d -50% 是 $500-2.5k 損失，bb_breakout 14d -50% 是 $5-15k 損失，operator 心理線不同。

**QC 建議**：per-strategy 設置（default -50%，operator 可調整 -30% to -70%）；schema 加 `mitigation_threshold_pct` per-strategy config。

### Q3：RETIRED strategy 30d cooling 後 re-promotion 是 Stage 0R 開始還是 Stage 1？

§3.2 寫 30d cooling 後 operator manual re-promotion through Stage 0R/1/2/3/4 path。但 strategy 之前 Live 過，Stage 0R replay preflight 是否冗餘？

**QC 建議**：Stage 0R 必跑（因 RETIRED 意味 alpha-deficient 已被驗證，重新上必 replay preflight 確認 regime change 真改善）；待 AMD-2026-05-15-01 + AMD-2026-05-21-01 cross-ADR collision audit（Sprint 1A-ε）。

### Q4：M7 retrain trigger 是否寫 governance.audit_log？

§4 retrain trigger 屬 model parameter change（not strategy sizing change）。是否屬 LAL approval 範圍？

**QC 建議**：LAL 1 範圍（per-strategy reparam，Stage 4 + 30d stable）；待 ADR-0034 細節仲裁。

---

## §14 Cross-References

- v5.8 §2 M7：`docs/execution_plan/2026-05-20--execution-plan-v5.8.md`
- M11 threshold + M7 dedup spec：`docs/execution_plan/2026-05-21--m11_threshold_m7_dedup_decay_enforced_rename.md`
- V113 schema spec：`docs/execution_plan/2026-05-21--v113_m7_decay_signals_schema_spec.md`
- M11 design spec：`docs/execution_plan/2026-05-21--m11_continuous_counterfactual_replay_design_spec.md`
- M1 LAL design spec：`docs/execution_plan/2026-05-21--m1_lal_layered_approval_lease_design_spec.md`
- ADR-0034 LAL：`docs/adr/0034-decision-lease-layered-approval-lal.md`
- ADR-0038 M11 continuous counterfactual replay：`docs/adr/0038-m11-continuous-counterfactual-replay-and-liquidations-source.md`
- AMD-2026-05-15-01 + AMD-2026-05-21-01：`docs/governance_dev/amendments/`
- QC skill cross-ref：`srv/.claude/skills/quant-strategy-design` + `walk-forward-validation-protocol` + `math-model-audit` + `crypto-microstructure-knowledge` + `portfolio-construction-protocol`
- Memory：`feedback_indicator_lookahead_bias` + `feedback_pushback` + `feedback_demo_over_paper_for_edge`

---

## §15 Sign-off

| Role | Status | Date | Note |
|---|---|---|---|
| QC Drafted | DONE | 2026-05-21 | quant 數學推導 / 黑名單迴避 / 14d × 50% mitigation justification |
| PM Write (handoff) | DONE | 2026-05-21 | QC tool boundary → PM 主會話 transcribe |
| MIT | PENDING | — | schema reconciliation with V107/V112 cross-ADR audit |
| PA | PENDING | — | Sprint 1A-β dispatch packet alignment |
| E4 | PENDING | — | Regression after IMPL Sprint 4-5 |
| CC | PENDING | — | governance binding（LAL operator override edge per AMD-2026-05-21-01）|
| PM Sign-off | PENDING | — | Sprint 1A-β closure |

**END M7 Decay Design Spec**
