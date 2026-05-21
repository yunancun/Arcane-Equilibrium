# 玄衡 · Arcane Equilibrium — 策略與架構完整重設計建議

**日期**：2026-05-20
**Author**：Claude（外部第三方 review，無利害關係）
**Status**：DRAFT — 待 operator 批准後分解為 PA spec / amendment
**範圍**：5 textbook 策略、ML/Learning 基座、5-Agent 框架、Risk/Execution path 的完整重設計
**依據**：4 條並行 audit（strategy / ML / multi-agent / risk-execution）+ TODO.md §11.4 micro-profit 根因 + AMD-2026-05-15-01 / -02 governance 邊界

---

## §0 TL;DR — 三層問題、三層解法、三條紅線

你的系統有 **三個獨立的失敗點疊加**，每一條單獨拆都不夠：

| 層 | 真實狀態 | 影響 |
|---|---|---|
| **L1 策略層** | 5 textbook 策略全部 EV<0 或 ≈0；alpha 已 commoditized | **-15~+10 bps gross**（依策略） |
| **L2 ML/Hypothesis 層** | 表結構完整但 0 active writer；scorer/ONNX 寫了沒接；hypothesis pipeline 排到 N+5 | **無法量產替換策略** |
| **L3 物理 / Account 層** | $591 帳戶被 Bybit $5 min_order_notional 卡死，Kelly 計算的 $0.037 完全被壓制 | **net edge 物理下限 ≈ -33 bps，execution 全力優化救到 -3 bps** |

三層全要動，但**順序錯了就白做**。正確順序是：**L3 → L1 → L2**（先解物理，再解策略，最後建發現流水線）。當前 W-AUDIT-8a 路徑是 L1+L2 先行、L3 不動——這是在沙上蓋樓。

**三條紅線（不可違背）**：
1. **$591 不增資、不上 live、不繼續 polish textbook 策略**（任何方向都是燒時間）
2. **不啟動 W-AUDIT-8b funding skew / 8d BTC lead-lag 復活路線**（兩條已 RED_FINAL，第三次失敗機率 > 70%）
3. **不在沒有 hypothesis factory 之前增加任何 static strategy**（否則就是繼續往沙堆裡丟磚）

---

## §1 現狀深度診斷

### §1.1 策略層真實 edge 表（4 audit 合成）

| 策略 | 訊號本質 | Alpha 歸因 | 設計缺陷 | 2026 真實 edge | 命運 |
|---|---|---|---|---|---|
| **MA Crossover** | KAMA × SMA20 + ADX gate | Momentum（已過時） | `regime_filter` 反向：Hurst=mean_reverting 時跳過，但 KAMA crossover **本來在 mean reversion 表現更好** | ~0 bps | **Baseline 對照組** |
| **BB Reversion** | Band ±2σ + RSI 30/70 + MA 確認 | Mean reversion | `require_ma_confirmation=true` 雙重過濾，砍掉大部分有效訊號；無 funding rate gate | -10~+5 bps | **拆解 A/B**（gate on/off） |
| **BB Breakout** | BW 壓縮→擴張 + Volume + Donchian | Volatility expansion（滯後） | `enable_oi_signal=false`（OI confluence **預設關閉**）；ATR×2 trailing 在強趨勢中太寬 | -5~+10 bps | **拆解 A/B**（OI 強制 ON） |
| **Grid Trading** | OU spacing + 10 layers | Liquidity provision | 34 bps cost / 10 layers = 3.4 bps/層，物理上無法克服；trending hard-stop 在高點清倉 | -15~0 bps | **Retire 或改 micro-grid** |
| **Funding Arb** | Funding > 5 bps + basis < 0.5% | Carry | 34 bps cost vs 多數 < 8 bps funding | DEAD（已 dormant） | **Permanent retire**（ADR-0018） |

**最致命的發現（audit 1 報告原文）**：「current codebase 在『工程品質』上已達 production grade，但在『alpha 質量』上已是負值。」這是一個「**製作精良的死局**」(well-engineered death spiral)。Confluence scoring、persistence filter、regime gate、maker rejection handler 全是高品質工程，但都是在已經是負 EV 的訊號上做精細的縮放——縮放 0 仍然是 0，縮放 -10 bps 還是負的。

### §1.2 ML / Learning 基座的「骨架無身體」狀態

`learning.*` schema 有完整設計（V004 起），但運行時實際狀態：

| 表 / 模組 | 設計 | 實際 |
|---|---|---|
| `strategy_trial_ledger` | Edge estimation 循環 | ✅ Active，16,212 rows |
| `cost_edge_advisor_log` | Cost gate evidence | ✅ Active 但 `[cost_edge].enabled=false`，ratio=NULL |
| `bayesian_posteriors` | Thompson Sampling | ⛔ **0 writer**（表存在沒人寫） |
| `cpcv_results` | Combinatorial Purged CV | ⛔ **0 writer** |
| `james_stein_estimates` | Shrinkage | ⛔ **0 writer** |
| `model_registry.onnx_artifact_path` | ONNX inference | ⛔ **grep 不到任何 reader** |
| `scorer_predictions` | Scoring | ⛔ **V069 已 DROP** |
| `drift_events` | ADWIN drift detection | ⚠️ 表 retained，writer 邏輯 Rust 端找不到 |
| `feature_baselines` | Drift baseline | ⚠️ 表 retained，0 bootstrap workflow |
| `hypotheses` (W-AUDIT-8f) | Hypothesis state machine | ⛔ **不存在**（spec only，DEFER N+5） |
| `teacher_directives` / `directive_executions` | RL/teacher signals | ⛔ **0 producer** |

**最關鍵的事實**：你想做的「策略發現工廠 / hypothesis factory」**底層基礎設施 0% 完工**。`learning.hypotheses` 表不存在，state machine 0 行代碼，attribution chain 沒接，scorer 沒人寫沒人讀。當前所謂「ML 基座」是一個展示用骨架——表創建了、ADR 寫了，但 trading decision 完全不被 ML 觸碰。

唯一 live 的 ML element 是 `cost_edge_advisor.py` 的純數學閾值（不是 ML）。

### §1.3 5-Agent 框架的真實價值

| Agent | Authority | 實際做的事 | Alpha 還是 Moat |
|---|---|---|---|
| **Scout** | 0 decision | 號稱 650+ scanner，**實際只跑 25 symbols active**（`max_symbols=25`）；產生 IntelObject | Universe management，不是 alpha |
| **Strategist** | Advisory only | H1/H3/H4 gates → 包裝 TradeIntent | **沒有 pattern discovery**；只是 wrapper |
| **Guardian** | **Veto authority** | 5 項決定性檢查；APPROVED/REJECTED/MODIFIED | **Pure defensive moat** |
| **Executor** | 0 decision | 執行 Guardian 批准的 intent | Pure execution |
| **Analyst** | 0 trading authority | Post-hoc L1/L2 統計 | **事後分析**，不是事前 hypothesis |

**結論**：這套框架的全部價值在 **Guardian 的否決權 + H0 Gate 的 fail-closed**，是 **執行紀律 defensive moat**。它**不是 alpha 引擎**，從來不是。

但這意味著兩件事：
- ✅ **保留價值**：當你之後跑任何高頻 / 反共識 / 容量受限策略時，這套 defensive moat 是 asset（Guardian 仲裁、Decision Lease、Replay 可追溯、H0 fail-closed 全有用）
- ❌ **錯位期待**：「再寫一個 agent / 再加一個 SM 能產生 alpha」是錯的；要產 alpha 必須做 retrofit（Scout 動態擴展、Analyst hypothesis-driven、Guardian contra-consensus mode）

### §1.4 Risk / Sizing / Execution 的物理上限

**$591 帳戶 net edge 公式**（audit 4 精確計算）：

```
当前 net_edge_bps = 30 (alpha) - (25 taker - (-3) rebate) - 20 slip - 10 missed - 5 shrink
                  = 30 - 28 - 20 - 10 - 5
                  = -33 bps
```

關鍵約束：
- **per_trade_risk_pct = 0.05% × $591 = $0.30** ← 完全低於 Bybit `min_order_notional_usdt = 5`
- 系統被強制以 $5 下單（**0.85% of balance**），這是 **per_trade_risk_pct 17 倍**
- **Kelly young-tier (1/8) = 0.625% sizing = $0.037** ← 被 min_order_notional 完全壓制
- 換言之：你跑的「Kelly sizing」根本沒在運行，每筆交易都被 exchange floor 強制放大 6.7 倍以上

**Execution 全力優化能救多少**（audit 4 三槓桿合計）：

| 槓桿 | Current | Target | 救回 bps |
|---|---|---|---|
| A. PostOnly success rate | 60% | 85% | +6.75 |
| B. Slippage tier（集中流動性對） | 20 bps | 12 bps | +8 |
| C. Missed fill reduction | 10 bps | 6 bps | +4 |
| **合計** | — | — | **+18.75 bps** |

```
優化後 net_edge_bps = 30 - 11 - 12 - 6 - 4 = -3 bps  ← 仍然負
```

**真正 unlock 帳戶大小**（audit 4 cross-table）：

| Account | per_trade max | Kelly 是否解封 | Slippage tier | Breakeven α |
|---|---|---|---|---|
| **$591** | $5（exchange floor） | ⛔ 完全壓制 | 30 bps | 40 bps |
| **$5,000** | $50+ | ✅ Young tier 解封 | 10-15 bps | 35 bps |
| **$50,000** | $500+ | ✅ Mature tier 完整 | 5 bps | 30 bps |

**這是物理事實，不是策略問題**：即使你今天找到 40 bps alpha（這已經是 institutional-grade，retail 拿不到），在 $591 上 net edge 還是接近 0；同樣的 alpha 在 $5,000 上是 +18 bps，在 $50,000 上是 +24 bps。**alpha 不變，size 變了，net 直接從 -3 跳到 +24。**

---

## §2 核心判斷

從這 4 條 audit 推出的硬結論：

**A. 5 textbook 策略無「修復」路徑。** 不是 parameter 調不對、不是 indicator 用錯、不是 regime gate 缺，是 alpha 本身已被市場 commoditize。再 polish 6 個月也是 0。**接受 retire，不要再 invest 在「下一個 regime gate」上。**

**B. W-AUDIT-8a Tier 2-4 是 50% 死局。** 其中 8b/8d 已 RED_FINAL；剩下 funding skew / OI delta / basis / sentiment 都是 institutional 已工業化套利的訊號。**唯一還有 retail 可達 edge 的是 Tier 3 LiquidationCascade + OrderflowImbalance，其他凍結。**

**C. W-AUDIT-8f Hypothesis Pipeline 排得太晚（N+5）。** 這條才是真正能救你的路徑——不是再寫一個策略，而是**建造能持續產生短命策略的工廠**。但 ML 基座 0% 完工狀態下，這條 ETA 至少 6-8 sprint。**必須拉前。**

**D. Multi-agent 框架是 asset 但被誤用。** 它的本質是 defensive moat，不是 alpha 引擎。**保留架構，但 Scout/Analyst 必須 retrofit 才能支撐 hypothesis factory；Guardian 必須開 contra-consensus mode 才能支撐反共識策略。**

**E. $591 帳戶不該繼續實驗。** 物理上限 -33 bps，optimization ceiling -3 bps。所有「alpha 救援」工作的 ROI 都被 size 物理壓制 6-10 倍。**Pre-condition：補資金到 $5,000+ 才動下一步。否則整個架構在做免費 stress test。**

---

## §3 重設計藍圖（5 Phase）

### Phase 0 — Pre-condition（W0，不耗 engineering）

**Operator decision，無 spec 需要**：

1. **資金決議**：補到 $5,000（min viable）或 $10,000（comfortable）。若不補，跳到 Phase 0-alt。
2. **5 策略狀態凍結**：保持 demo 跑做 baseline，不再分配 engineering capacity 在「優化現有 5 策略 alpha」上（execution 改進 OK，alpha 改進 NO）。
3. **W-AUDIT-8b/8d permanent tombstone confirm**（已 done，紀錄一遍）。

**Phase 0-alt（若不補資金）**：
- 把整個系統定位改為 **「治理框架 staging environment + 教育材料」**，承認當前 size 下不可能盈利
- 撤回所有 supervised live 計畫
- 把 engineering 投入轉向 **框架本身**（governance / replay / lineage），這些是可以複用到任何未來規模的 asset

### Phase 1 — Execution Hardening（Sprint N+1，1 sprint）

**目標**：在現有 5 策略上把 net edge 從 -33 bps 救到 -3 bps（不動 alpha）。這個 ROI 比任何 alpha 工作都高，因為**execution 改進是 alpha-agnostic 槓桿**。

| Task | 改動 | Owner | 預估 LOC | Acceptance |
|---|---|---|---|---|
| **E1.1 PostOnly success rate 拉到 85%** | 動態 offset + per-symbol queue model + slot prediction | PA→E1 | ~300 | 7d demo PostOnly fill rate ≥ 85% |
| **E1.2 Liquidity-band universe gate** | Scanner 加 `tier_A`（vol > $50M/d）vs `tier_B`（$500k-$5M）；textbook 策略只能跑 tier_B | PA→E1a | ~150 | universe split 落 PG；策略 dispatch 對齊 |
| **E1.3 Missed-fill timeout 重調** | Phase 1b 90s 對 $591 size 過長；split：tier_A 30s / tier_B 60s | E1 | ~50 | per-symbol routing 對應 timeout |
| **E1.4 Slippage tier surfacing** | `query_slippage_tier` IPC + Guardian 在 ≥20 bps tier 拒絕新倉 | E1 | ~80 | execution_reports.slippage_tier 落 PG |

**Acceptance**：7d demo run net edge ≥ -5 bps（vs current -33 bps），且 PostOnly fill rate ≥ 85%。

**為什麼這個 sprint 第一**：因為它 alpha-agnostic、和 hypothesis factory 不衝突、是任何後續路徑的前置條件。

### Phase 2 — Strategy Triage（Sprint N+2，1 sprint）

**目標**：對 5 策略做明確的 retire / baseline / redesign 決策，stop bleeding engineering time on dead horses。

| 策略 | 決定 | 理由 |
|---|---|---|
| `funding_arb` | ⛔ **Permanent retire** | ADR-0018 已 confirm；無救援數學 |
| `grid_trading` | ⛔ **Retire current version**，留 **micro-grid v2** spec slot | 10-layer OU 在 $591 / $5000 都不 viable；v2 改 100-layer micro-grid + 限 tier_B（容量受限角落） |
| `ma_crossover` | 🟡 **Baseline keep + regime_filter 反向實驗** | audit 1 發現 regime_filter 在 mean_reverting regime 跳過實際 hurt performance；做 A/B：regime_filter on/off/inverted，1-sprint experiment |
| `bb_reversion` | 🟡 **Baseline keep + MA confirmation gate A/B** | `require_ma_confirmation=true` 砍訊號過多；做 A/B：on/off |
| `bb_breakout` | 🟡 **Baseline keep + OI confluence 強制 ON** | `enable_oi_signal=false` 預設關 OI 是設計缺陷；強制 ON 看 7d 是否轉正 |

**Task**：
- E2.1 寫 ADR 記錄 retire 決定（funding_arb, grid_v1）
- E2.2 三個 A/B test design（PA→QC →E1）
- E2.3 增加 strategy-A/B 對照 dashboard（`/console/strategy` tab）

**Acceptance**：3 個 A/B 各 7d demo run，產出 Bayesian posterior。

**這個 sprint 不寫新策略**——只是清理 + 用既有材料做最後一輪 honest experiment。如果這 3 個 A/B 都不轉正，就 confirm「textbook signal 已死」這個 hypothesis，給 Phase 3 提供 evidence。

### Phase 3 — Multi-Agent Retrofit（Sprint N+2 ~ N+3，2 sprint，並行 Phase 2）

**目標**：把 Scout / Analyst / Guardian 從「執行紀律 moat」retrofit 成「能支撐策略發現工廠」的基座。

#### 3.1 Scout：從 25-symbol 靜態 → 動態 alpha-seeking

當前 `MarketScanner(max_symbols=25)` 是 hardcoded 上限。需改為：

- **Dynamic alpha-seeking band**：每 1h re-rank universe；tier_A pin top-20 流動性、tier_B 浮動採樣 30-50 個（per Sprint 反共識策略 + 容量受限策略需要 long-tail visibility）
- **New listing watcher**：Bybit announcement API → 自動加入觀察池 72h，產出 EventAlert
- **Cross-venue divergence detector**（後期）：Bybit vs Binance / OKX 同 perp 價差 / funding 差

LOC 估計：~500，PA→E1a，2 sprint。

#### 3.2 Analyst：從 post-hoc 統計 → hypothesis-driven Thompson sampling

當前 Analyst 是純事後分析。需新增：

- **Hypothesis generator**（H4 cloud LLM 可選；ADR-0020 manual+supervisor-only）：消費 IntelObject + market regime → 提議新 hypothesis（feature combination / regime condition / direction）
- **Thompson sampling allocator**：對 active hypothesis 做 multi-armed bandit，動態分配 paper budget
- **CPCV walk-forward**：把當前 dormant 的 `learning.cpcv_results` 表接上 writer

LOC 估計：~800，PA→E1+MIT，2 sprint。**這條 unlock 後，hypothesis factory 真正啟動。**

#### 3.3 Guardian：增加 contra-consensus mode

當前 Guardian 5 項檢查全是保守方向（拒絕高槓桿、拒絕高相關性）。新增：

- **Contra-consensus flag**：當策略明確聲明 `contra_consensus=true`（即反 textbook 訊號 fade），Guardian 不應該以「方向與 ma_crossover 衝突」拒絕
- **Hypothesis-stage 認證**：DRAFT 階段 hypothesis 允許小 size paper；REGISTERED 進 demo；EVIDENCE_GATE 才能 demo canary

LOC 估計：~200，PA→E1，1 sprint（並行 3.2）。

#### 3.4 Conductor：保持不動

Conductor 設計合理（Guardian wins over Strategist），不需改。

### Phase 4 — Hypothesis Factory & Real Alpha Sources（Sprint N+3 ~ N+5，3 sprint）

**目標**：建造真正的策略發現流水線，並接上 3 條 retail 可達的 alpha source。

#### 4.1 Hypothesis Pipeline 第一階段（W-AUDIT-8f 從 N+5 拉前到 N+3）

最 minimal viable hypothesis factory：

```
learning.hypotheses table (new V### migration)
  id, name, hypothesis_text, feature_spec_json,
  state ENUM (DRAFT, REGISTERED, EXPERIMENTING, EVIDENCE_GATE, PROMOTED, REJECTED, EXPIRED),
  created_at, state_changed_at, expiry_at,
  paper_pnl_bps, demo_pnl_bps, sharpe, dsr,
  originating_alpha_sources jsonb,
  decision_lease_count INT, demo_canary_eligible bool

Python: hypothesis_state_machine.py + REST endpoints + GUI tab
Rust: originating_hypothesis_id on Decision Lease + ExecutionPlan + fills
```

LOC：~1200 跨 Python + Rust + migration，2 sprint。

**這條 land 後，每週能跑 10-30 hypothesis（不是 50-200，那是 long-tail），每條死得快活得快，alpha decay 不再致命。**

#### 4.2 三條真實 alpha source 接入

按 ROI / 可行性排序：

**(a) 容量受限角落（new listings + tier_B mean reversion）**——**最高 ROI，最低風險**

- 新 perp 上市首 72h pattern（spread 失控、price discovery、reversion 概率高）
- tier_B 流動性對的 BB Reversion（沒人在這些 pair 上做 textbook，textbook 反而 work）
- LOC: ~400 新策略 + universe gate (Phase 1 已準備)，1 sprint
- **預期 alpha**: +20~50 bps（capacity-constrained means crowded competition absent）

**(b) Liquidation Cascade Reaction**（W-AUDIT-8c 已 source/test ready，只待 strategy launch）

- 利用已 revived 的 `allLiquidation` writer
- 大型 liquidation cluster → 2-30 秒內 micro-reversion 機率提升
- LOC: ~300 新策略 + state machine，1 sprint
- **預期 alpha**: +10~30 bps（unstable，需頻繁 retune，正好用 hypothesis factory）

**(c) 反共識 meta-strategy**（regime-conditioned signal flip）

- ATR percentile + ADX classifier
- BB breakout 在 low-vol regime fade（false breakout 主導）
- BB reversion 在 trending regime fade
- LOC: ~250 regime classifier + signal flipper，1 sprint
- **預期 alpha**: +5~20 bps（reliable, capacity-light）

#### 4.3 凍結 W-AUDIT-8a Tier 2-4 大部分

- ⛔ Tier 2 Funding Skew / Basis：已工業化套利，凍結
- ⛔ Tier 4 Sentiment：數據源延遲 + 雜訊比差，凍結
- ✅ Tier 2 OI Delta Panel：保留為 **filter/confluence**（不獨立策略）
- ✅ Tier 3 LiquidationCascade：上面 (b)
- ✅ Tier 3 OrderflowImbalance：留 Phase 5（需 paid 數據源評估）
- ✅ Tier 4 EventDriven：留 Phase 5（needs onchain integration）

### Phase 5 — Long Tail（Sprint N+5+，opt-in）

- ML training loop（Bayesian posteriors / James-Stein / Thompson sampling 接 writer）
- ONNX inference hotpath 整合
- Paid data source evaluation（Glassnode、Kaiko、CoinAPI）
- Onchain flow tracking
- Live promotion gate per alpha source（W-AUDIT-8g）

**這些都不解 short-term 痛點，留長尾。**

---

## §4 Sprint 級執行計畫（替換現有 N+1 ~ N+5）

**重要**：以下計畫**取代** TODO.md §1 現有的 N+1 ~ N+5 sprint banner。改動點用 ⭐ 標示。

| Sprint | Week | 主題 | E1 capacity | 業務鏈 milestone |
|---|---|---|---|---|
| **N+0** | 已過 | FOUNDATION HEAVY（保留）| 5+1 | 65% |
| **N+1** ⭐ | W3-W4 | **Execution Hardening + Strategy Triage 設計** | 4/6 | 65→67%（execution 加成）|
| **N+2** ⭐ | W5-W6 | **Strategy A/B Tests + Multi-Agent Retrofit Phase A** | 5+1 | 67→70% |
| **N+3** ⭐ | W7-W8 | **Hypothesis Pipeline V1 + 容量受限角落策略 + Scout dynamic** | 4/6 | 70→75% |
| **N+4** ⭐ | W9-W10 | **Analyst Thompson Sampling + Liquidation Cascade 策略 + Reverse-Consensus** | 4/6 | 75→80% |
| **N+5** ⭐ | W11-W12 | **Hypothesis Factory full + 首個 hypothesis-promoted demo canary** | 5+1 | 80-85% |

**對應任務（替換 TODO.md §4.1 Wave Roster 的 alpha-bearing wave）**：

```
NEW-1 Execution Hardening                    [N+1]  PA→E1+E1a→E2→E4
NEW-2 Strategy Triage (3 A/B)                [N+2]  PA→QC→E1→E4
NEW-3 Multi-Agent Retrofit Phase A           [N+2]  PA→E1+E1a→E2
  - Scout dynamic universe
  - Guardian contra-consensus mode
NEW-4 Hypothesis Pipeline V1                 [N+3]  PA→E1→MIT→E2→E4
  - learning.hypotheses table
  - state machine
  - originating_hypothesis_id propagation
NEW-5 容量受限角落策略                       [N+3]  PA→E1
  - new listing watcher
  - tier_B BB reversion variant
NEW-6 Multi-Agent Retrofit Phase B           [N+4]  PA→E1+MIT
  - Analyst hypothesis-driven
  - Thompson sampling allocator
NEW-7 Liquidation Cascade Strategy           [N+4]  PA→E1→QC
  - 接已 revived allLiquidation writer
NEW-8 反共識 Meta-Strategy                    [N+4]  PA→E1
  - regime classifier + signal flipper
NEW-9 Hypothesis Factory Full                [N+5]  PA→E1+MIT+E2
  - GUI tab
  - CPCV writer 接上
  - 首個 promoted hypothesis 進 demo canary
```

**已凍結 / retire 任務**：

```
W-AUDIT-8b Funding Skew                      ⛔ Tombstoned（已 done）
W-AUDIT-8d BTC Lead-Lag                      ⛔ Tombstoned（已 done）
W-AUDIT-8a Tier 2 (FundingSkew/Basis)        ⛔ FROZEN（institutional 已套利）
W-AUDIT-8a Tier 4 Sentiment                  ⛔ FROZEN
funding_arb strategy                         ⛔ Retire confirm
grid_trading v1                              ⛔ Retire；micro-grid v2 進 N+5+ backlog
```

**保留任務**：

```
W-AUDIT-8a Tier 3 LiquidationCascade         ✅ → NEW-7
W-AUDIT-8a Tier 3 OrderflowImbalance         ✅ → N+5+ (paid data eval)
W-AUDIT-8c                                   ✅（source/test 已 done）→ NEW-7
W-AUDIT-8e Strategist Orchestrator           ✅ → 拆進 NEW-6
W-AUDIT-8f Hypothesis Pipeline               ✅ → NEW-4 + NEW-9 (拉前 2 sprint)
```

---

## §5 Acceptance Criteria（每階段 binary）

### Phase 1 Exit（N+1 結束）
- ✅ 7d demo PostOnly fill rate ≥ 85%（vs current ~60%）
- ✅ tier_A/tier_B universe split 落 PG（`scanner.symbol_tier` enum）
- ✅ Slippage tier surface 在 `execution_reports` 表
- ✅ 7d demo net edge ≥ **-5 bps**（從 -33 bps）

### Phase 2 Exit（N+2 結束）
- ✅ 3 個 A/B test 各 7d evidence，Bayesian posterior 落表
- ✅ `funding_arb` ADR-confirm retire
- ✅ `grid_trading` v1 frozen，v2 spec slot 進 backlog

### Phase 3 Exit（N+2 + N+3 並行）
- ✅ Scout 動態 universe 上線（25 hardcoded → dynamic ≥50 sampling）
- ✅ Guardian contra-consensus flag 接線
- ✅ New listing watcher 7d run，產出 ≥10 個 watch entries

### Phase 4 Exit（N+5 結束）
- ✅ `learning.hypotheses` 表 + state machine + GUI tab 上線
- ✅ `originating_hypothesis_id` 接到 Decision Lease + ExecutionPlan + Fills
- ✅ Thompson sampling allocator 跑 ≥4 個 active hypothesis
- ✅ 至少 1 個 hypothesis 從 DRAFT 走完 → DEMO canary（不要求 PROMOTED）
- ✅ 容量受限角落策略 + 反共識策略各 1 個跑滿 14d demo
- ✅ Liquidation Cascade 策略 14d demo evidence

### Phase 5 Exit（N+6+，opt-in）
- Live promotion gate per alpha source
- Paid data source 評估 verdict
- ML training loop 真實接線

---

## §6 風險登記與中止標準

### 6.1 Phase-level abort criteria

| Phase | Abort if... | 中止後做什麼 |
|---|---|---|
| Phase 1 | 7d post-deploy net edge < -20 bps（沒到 -5 目標） | 回到 audit 4 公式重算，可能是 alpha 估計過樂觀 |
| Phase 2 | 3 A/B 都 RED，且 confidence 高（DSR > 0.95） | confirm「textbook signal 已死」，加速 Phase 4 |
| Phase 3 | Scout 動態 universe 引發 alpha source attribution chaos | 退回 25-symbol，但保留 dynamic shadow mode |
| Phase 4 | Hypothesis pipeline 第一個 cycle 6-8 weeks 完全 0 promotion | 重檢視 hypothesis generator quality；考慮 H4 cloud LLM 介入 |

### 6.2 已知風險與緩解

**R1：Audit 4 alpha 30 bps 估計可能樂觀**
- Mitigation: Phase 1 提供 honest measure，若 actual alpha < 20 bps 則重新校準後續所有 ROI
- Owner: QC

**R2：Hypothesis Pipeline N+3 launch 太早，ML 基座未準備**
- Mitigation: V1 只做 manual + paper，不接 ML scoring；Phase 5 才接 Thompson sampling 真實作動
- Owner: PA

**R3：新策略（NEW-5/7/8）在 fail 後沒有 fallback**
- Mitigation: 都先 Stage 0 shadow → Stage 0R replay → Stage 1 Demo 走完，與 W-AUDIT-8a 同 governance level；任何 RED FINAL 直接 tombstone（不留戀）
- Owner: PA + QC

**R4：Operator 不補資金 → 整個方案的物理基礎不成立**
- Mitigation: Phase 0-alt（governance staging environment）；明示告知 operator 此路徑下 「不可能盈利」是設計前提，不是 bug
- Owner: Operator（business decision）

**R5：v56 P0-ENGINE-HALTSESSION-STUCK 還沒收口**
- Mitigation: Phase 1 dispatch 必須序列化在 v56 P0 完整 cycle 之後（per TODO §10 + §11.3）
- Owner: PM

### 6.3 governance 不變式（不被本方案碰）

以下 16 條根原則 + 5 gate live boundary + DOC-08 §12 9 條安全 invariant + AMD-2026-05-15-01 graduated canary，**全部繼續強制 binary fail-closed**。本方案不引入任何放寬。

特別強調：
- 任何新策略（NEW-5/7/8）都要走完整 Stage 0 → 0R → 1 Demo → 2/3/4 canary
- Hypothesis Factory 的 PROMOTED state **不等於 live**，仍需通過 5 live gate
- contra-consensus mode 不是 Guardian 失效，只是 conflict-detection rule 加 carve-out
- 容量受限角落策略不繞 Guardian / Decision Lease

---

## §7 不做的事（Anti-Recommendations）

明確列出**不該做**的事，防止 sprint planning 誤分配：

1. ❌ **不要在 $591 上 supervised live**（物理上限 -33 bps；live gate 全綠也不會盈利）
2. ❌ **不要繼續優化 5 textbook 策略的 alpha**（execution 改 OK，alpha 不要動，alpha 救不回）
3. ❌ **不要寫第 6 個 textbook 策略**（如 MACD、RSI divergence、Ichimoku——任何 retail 教科書出現過的都死）
4. ❌ **不要復活 funding_arb 或 grid v1**（除非數學前提變了：fee 大降 OR funding rate regime 全變）
5. ❌ **不要花 sprint 在 Bayesian posteriors / CPCV / James-Stein writer**，直到 hypothesis pipeline V1 land（否則是空殼 writing 空殼）
6. ❌ **不要動 Guardian 的 5 項否決檢查**（H0+Guardian 是整個 framework 的 moat，碰一下都會打破 fail-closed 保證）
7. ❌ **不要把 Scout 從 25 → 650 一步到位**（先 dynamic 50-symbol sampling，dispatch race condition 已踩過坑）
8. ❌ **不要把 ML / hypothesis factory 賣為「能找到 alpha 的黑盒」**——它能做的是**比手工快 10 倍地試錯**，不是發明 alpha；alpha 的來源仍是 (a) 容量受限角落 (b) 反共識負空間 (c) 真實微結構訊號
9. ❌ **不要 chase Tier 4 sentiment / event-driven alpha 直到 paid data source budget approved**（free tier 延遲 + 雜訊讓任何 sentiment 訊號失效）
10. ❌ **不要省 E2 review / E4 regression**（CLAUDE.md §八 明示）

---

## §8 對 CLAUDE.md / TODO.md 的同步建議

本方案 land 後，需同步更新：

| 文件 | 改動 |
|---|---|
| `TODO.md §1 Sprint Banner` | 替換 N+1~N+5 milestones 為本方案 §4 |
| `TODO.md §4.1 Wave Roster` | 標 W-AUDIT-8a Tier 2/4 為 FROZEN；W-AUDIT-8f 拉前；新增 NEW-1~9 |
| `TODO.md §11.4 P0-MICRO-PROFIT` | 更新 ETA（從 12-17 sprint 降到 5 sprint）+ 增加「物理 size threshold $5,000」結論 |
| `CLAUDE.md §三 Active State` | 更新「業務根因」段：補上「+ size physics, + ML 空殼, + multi-agent moat 錯位」 |
| `docs/adr/` | 新增 ADR：retire funding_arb v1 + grid v1；新 ADR：alpha-source frozen list |
| `docs/governance_dev/amendments/` | 新 AMD：strategy redesign 2026-05-20（取代 N+1~N+5 既有 plan） |

---

## §9 一段話總結

**問題**：你的系統是「精緻死局」——工程品質高，但 5 textbook 策略 EV<0，ML 基座空殼，multi-agent 是 defensive moat 不是 alpha 引擎，$591 帳戶被 Bybit min order 卡死到根本沒在跑 Kelly。

**解法**：先 **Phase 0 補資金到 $5k+**（這是物理前提，不是工程問題）；然後 **Phase 1 execution hardening**（不動 alpha 救 30 bps）；**Phase 2 strategy triage**（retire 2 留 3 baseline）；**Phase 3 multi-agent retrofit**（Scout dynamic / Guardian contra-mode）；**Phase 4 hypothesis factory + 3 條真實 alpha source**（容量受限角落 + liquidation cascade + 反共識）；**Phase 5 長尾**。

**ETA**：5 sprint（10 週），對比原 W-AUDIT-8 路徑的 12-17 sprint 縮短一半，且更可能真實 unlock net-positive edge。

**最重要的一條**：alpha 不來自「再加一個 indicator」，alpha 來自 (a) 別人不能做的角落 (b) 別人在做的反面 (c) 別人沒接的微結構訊號。你不需要更聰明的 textbook，你需要更聰明地選戰場。

---

**附：4 條原始 audit 報告完整版本**請見：
- Strategy audit: 本 session 對話 (Agent 1 output)
- ML audit: 本 session 對話 (Agent 2 output)
- Multi-agent audit: 本 session 對話 (Agent 3 output)
- Risk/execution audit: 本 session 對話 (Agent 4 output)

（待 PM 批准後，這 4 條 audit 應該分別歸檔到 `docs/CCAgentWorkSpace/QC/`, `docs/CCAgentWorkSpace/MIT/`, `docs/CCAgentWorkSpace/FA/`, `docs/CCAgentWorkSpace/PA/` 對應 reports。）
