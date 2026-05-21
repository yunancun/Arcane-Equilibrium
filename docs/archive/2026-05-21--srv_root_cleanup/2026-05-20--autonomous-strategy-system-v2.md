# 玄衡 · Arcane Equilibrium — 全自動策略發現系統（ASDS）設計 v2

**日期**：2026-05-20
**Author**：Claude（外部第三方 review）
**Status**：DRAFT — 取代 `2026-05-20--strategy-architecture-redesign-recommendation.md` v1（v1 中「discipline execution layer」分支已 operator REJECT）
**範圍**：完整重設計為 **Autonomous Strategy Discovery System (ASDS)**——auto-trade + auto-analyze + auto-draft strategy
**依據**：
- Operator 拍板 2026-05-20：demo 補到 $10,000、live 設 $1,000、必須全自動
- v1 4 條 audit 結論（保留）：5 textbook 策略 EV<0、ML 基座空殼、multi-agent 是 defensive moat、$591 net edge -33 bps
- ADR-0020（Layer 2 manual-only）需要 carve-out 才能達成全自動目標——本文件附 ADR-0024 草稿

---

## §0 TL;DR — 從「策略 library」轉成「策略生產工廠 + 自動經理人」

**問題重申**（operator 拒絕的 v1 路徑）：v1 §3 Phase F「把 bot 重新定位為紀律執行層」要求人工分析提供訊號，operator 沒時間也不擅長。**REJECTED。**

**新方向**：系統本身必須是研究員 + 風控官 + 交易員 + 復盤員的合體。我把這個系統稱為 **Autonomous Strategy Discovery System (ASDS)**。

**ASDS 的核心 3 個 loop**：

```
Loop A — Market Sensing Loop（秒級）
  Tick → Regime Classifier → MarketState → 分配給 active strategies

Loop B — Strategy Execution Loop（分鐘級）
  active Strategy → on_tick → Hypothesis-bound StrategyIntent → Guardian → Decision Lease → Order

Loop C — Discovery Loop（小時 / 天級）
  Hypothesis Generator (L1+L2 LLM) → Replay Validator → Stage 0 Paper → Stage 1 Demo → 自動 Promote/Retire
```

**最關鍵的設計轉變**：你現在有的 5 個 textbook 策略不再是「程式碼裡 hardcoded 的 Rust struct」，而是 **hypothesis registry 裡的 5 條 row**。新 hypothesis 不需要寫 Rust——LLM 產 JSON spec，engine 把 spec 編譯成 Strategy trait 實例。

這把「加策略需要 sprint」變成「加 hypothesis 需要 LLM 一次推理」。Alpha decay 周期從幾個月縮到幾天時的關鍵基礎設施。

**3 個現實前提**（不接受就停在這）：

1. **接受 governance 變更**：ADR-0024（新）必須通過——Layer 2 LLM 可以**在預批准 budget envelope 內** autonomous 產 hypothesis spec，但完全不碰 risk config / live auth / order submission（這些仍走 Rust 權威 + Guardian + Decision Lease + Stage 0/1/2 gates）。

2. **接受誠實預期**：$1k live 即使 ASDS 完美運作，第一年期望 P&L 約 **$50-300 net**（Sharpe 0.5-1.0，retail 規模上限）。系統的真實價值是 **驗證架構 + 擴展準備**——當 demo evidence 顯示 ASDS 真的 work，operator 才放大 live size。**不是賺錢機器，是 alpha 工廠原型。**

3. **接受多級 LLM 經濟學**：L1 Ollama 本地（無成本）跑連續決策；L2 Claude/GPT 雲端（有成本，預算 envelope ~$30-50/月）只在 hypothesis generation cycle、regime shift 偵測、failed-hypothesis postmortem 用。**LLM 成本必須 < 系統 P&L 的 20%**，否則 ROI 為負。

---

## §1 重申 v1 4-audit 關鍵發現（仍適用）

| 層 | 發現 | $10k demo + $1k live 後 |
|---|---|---|
| **策略層** | 5 textbook EV<0；alpha commoditized | 仍要 retire；但 **新策略由 hypothesis factory 產生**，不是手寫 |
| **ML 基座** | 表結構完整但 0 writer；ONNX/scorer 未接線 | **必須 build out**——hypothesis factory 是 ML 基座的真實 consumer |
| **Multi-agent 框架** | Defensive moat，不是 alpha 引擎 | **保留 moat，retrofit 為 alpha factory 的執行底盤** |
| **物理層（$591）** | net edge -33 bps，Kelly 被壓制 | **$1k 邊界：Kelly young @ $6.25 剛跨過 $5 min order**；$10k demo Kelly + slippage 完全解封 |

**$1k live 真實數字**（修訂 audit 4 公式）：

```
per_trade_risk = 0.05% × $1000 = $0.50 → 被 Bybit min_order $5 強制放大 10x
Kelly young (1/8 × 0.625% × $1000) = $6.25 → 剛跨過 min order ✅
daily_loss_max = 7% × $1000 = $70 → ~20-30 失敗交易容量
Slippage tier: $5 order 仍在最差 tier (~25 bps)

breakeven α @ $1k live = 38 bps（仍緊）
breakeven α @ $10k demo = 24 bps（可達）
```

**結論**：$10k demo 是 honest evidence environment；$1k live 是 PoC（proof-of-concept）小規模實彈，期望結果是「不大虧 + 證明 ASDS 在實彈下也成立」。如果 ASDS 在 demo 證明 alpha 真實，operator 再決定是否擴 live size。

---

## §2 ASDS 整體架構（7-Tier Pipeline）

```
┌──────────────────────────────────────────────────────────────────────┐
│                  Tier 0 — Market Sensing (real-time, Rust engine)     │
│  ├─ Tick pipeline 650+ symbol                                         │
│  ├─ Cross-asset panel: BTC dom, sector flow, funding skew, OI delta   │
│  ├─ Microstructure: liquidation pulse, orderflow imbalance            │
│  └─ Output: AlphaSurface snapshot per tick (Tier 1-4 unified)         │
├──────────────────────────────────────────────────────────────────────┤
│         Tier 1 — Regime Classifier (continuous, hybrid)               │
│  ├─ Classical: HMM / ADWIN / ATR percentile / ADX (L0 ~ ms)           │
│  ├─ Local LLM (Ollama): regime narrative (L1 ~ sec)                   │
│  └─ Output: MarketRegime = {trending/ranging/chop, vol_band, ...}     │
├──────────────────────────────────────────────────────────────────────┤
│      Tier 2 — Hypothesis Generator (cadence: hour / day)              │
│  ├─ L1 Ollama (cheap, frequent): parameter mutation, A/B variant      │
│  ├─ L2 Claude/GPT (envelope, daily): novel hypothesis synthesis       │
│  └─ Output: HypothesisSpec JSON → learning.hypotheses table           │
├──────────────────────────────────────────────────────────────────────┤
│      Tier 3 — Auto-Validator (per new hypothesis)                     │
│  ├─ Replay 30d backtest with synthetic fills (existing replay engine) │
│  ├─ CPCV walk-forward (3 fold purged)                                 │
│  ├─ Deflated Sharpe Ratio gate                                        │
│  └─ Verdict: ELIGIBLE_FOR_PAPER / REJECTED                            │
├──────────────────────────────────────────────────────────────────────┤
│      Tier 4 — Stage 0 Paper (auto, 7d)                                │
│  ├─ Hypothesis loaded as Strategy trait instance                      │
│  ├─ Shadow / paper engine emit (no real fills)                        │
│  ├─ Thompson Sampling allocator over active paper hypothesis          │
│  └─ Gate: paper_sharpe > θ + paper_pnl_bps > 5 → Stage 0R replay      │
├──────────────────────────────────────────────────────────────────────┤
│      Tier 5 — Stage 1 Demo Canary (auto, 14d)                         │
│  ├─ 1 hypothesis × 1 symbol × $10k demo budget allocation             │
│  ├─ Existing Stage 0R replay preflight → Stage 1 micro-canary         │
│  └─ Gate: demo_sharpe > θ' + demo_dsr > 0.95 → Stage 2 demo extended  │
├──────────────────────────────────────────────────────────────────────┤
│      Tier 6 — Live Promotion (operator + per-hypothesis budget)       │
│  ├─ 5-gate live boundary unchanged                                    │
│  ├─ Per-hypothesis live budget (W-AUDIT-8g)                           │
│  └─ Live live_budget(hypothesis_id) ≤ $200 initially                  │
├──────────────────────────────────────────────────────────────────────┤
│      Tier 7 — Auto-Retire (continuous)                                │
│  ├─ ADWIN drift on hypothesis PnL                                     │
│  ├─ DSR re-check on rolling window                                    │
│  └─ Auto-tombstone if alpha decay detected                            │
└──────────────────────────────────────────────────────────────────────┘
```

**Loop A vs Loop B vs Loop C 對應**：
- Loop A（Market Sensing）= Tier 0 + Tier 1
- Loop B（Strategy Execution）= Tier 4-6 active hypothesis 的 `on_tick`
- Loop C（Discovery）= Tier 2-3 + Tier 7

---

## §3 各 Tier 詳細設計

### §3.1 Tier 0 — Market Sensing（既有 + 擴展）

**現有可用**：
- Rust tick pipeline 已支援 650+ symbol
- AlphaSurface Tier 1-4 trait 已 land（Phase A done）
- AllLiquidation writer 已 revive

**新增**：
- **Cross-asset panel** (`market_state/cross_asset_panel.rs`)：BTC dominance / sector flow / funding skew aggregate / OI delta panel；每 1m refresh，per tick snapshot
- **Microstructure features** (`market_state/microstructure.rs`)：orderflow imbalance、large trade rate、queue depth proxy（從 publicTrade WS 推導，不需 L3 數據）
- **Universe tier classification** (`market_state/universe_tier.rs`)：tier_A (vol > $50M/d) / tier_B ($500k-$5M) / tier_C (低於 $500k 自動排除)

**輸出**：每個 tick 一個 `MarketStateSnapshot` 結構，包含當前 symbol 的完整觀察 + 跨資產 panel + universe tier。

LOC: ~600 Rust，1.5 sprint。

### §3.2 Tier 1 — Regime Classifier（混合，新增）

**L0 Classical**（per-tick，<1ms SLA）：
```rust
struct RegimeFeatures {
    atr_percentile_30d: f64,    // 高 / 中 / 低 vol
    adx_14: f64,                // trend strength
    hurst_50: f64,              // mean reversion vs trending
    bb_width_percentile: f64,   // squeeze vs expansion
    realized_vol_1h_vs_24h: f64,// vol regime shift
}
```
→ classify into `RegimeTag` enum：`{LowVolTrending, HighVolTrending, LowVolChop, HighVolChop, RegimeShift}` 共 5 class。

**L1 Ollama**（每 5 分鐘，narrative 生成）：
- Input: classical features + recent price action + cross-asset panel
- Output: "現在 BTC dominance 在上升，alts 進 risk-off；funding skew negative；建議 fade BTC strength on alt longs"
- Used as **soft context** for hypothesis allocator，不直接影響 trading decision

**L2 Claude**（每 24 小時或 regime shift 觸發，預算 envelope 內）：
- Input: 24h regime evolution + active hypothesis performance
- Output: hypothesis allocation recommendation（Thompson prior 調整建議）
- 完全不碰交易執行；只調 paper allocator 的 Bayesian prior

**為什麼三層**：
- L0 必須在 hot path（per-tick），不能引入 LLM 延遲
- L1 提供 explainable narrative（for GUI display + audit），不影響 critical decisions
- L2 提供 hypothesis-level 戰略建議，但僅 advisory，所有 trade 仍走 Guardian

LOC: ~400 Rust + ~300 Python，1 sprint。

### §3.3 Tier 2 — Hypothesis Generator（**ASDS 心臟**）

這是整個系統最關鍵的新組件。設計目標：LLM 產出 **constrained DSL 而非 free-form code**，engine 安全編譯為可執行 Strategy。

#### §3.3.1 Strategy DSL / Hypothesis Spec 格式

```json
{
  "hypothesis_id": "uuid-v4",
  "name": "btc_liquidation_micro_reversion_v1",
  "version": 1,
  "generator": { "tier": "L2_claude", "model": "claude-opus-4-6", "cost_usd": 0.012 },
  "thesis": "短時間內大量 long liquidation 後，30s 內價格 micro-reversion 機率提升",

  "universe_filter": {
    "tier": ["tier_A", "tier_B"],
    "exclude_symbols": [],
    "min_volume_24h_usd": 5000000
  },

  "trigger_conditions": [
    { "feature": "liquidation_pulse_long_1m", "op": ">=", "value": "z_score(2.0)" },
    { "feature": "funding_rate_8h", "op": ">=", "value": 5, "unit": "bps" },
    { "feature": "btc_1m_return", "op": "<=", "value": -50, "unit": "bps" }
  ],

  "regime_filter": {
    "allowed_regimes": ["HighVolChop", "HighVolTrending"],
    "blocked_regimes": ["LowVolChop"]
  },

  "entry_action": {
    "direction": "long",
    "confidence": 0.65,
    "size_cap_pct": 1.5,
    "order_type": "post_only_maker",
    "offset_bps": 2
  },

  "exit_conditions": [
    { "type": "time_elapsed", "value": 300, "unit": "sec" },
    { "type": "pnl_bps", "op": ">=", "value": 25 },
    { "type": "pnl_bps", "op": "<=", "value": -15 },
    { "type": "regime_shift", "to_block": ["LowVolChop"] }
  ],

  "expected": {
    "alpha_bps": 18,
    "trades_per_day": 3.5,
    "sharpe_demo_target": 1.2,
    "max_drawdown_pct": 4
  },

  "lifecycle": {
    "expiry_days": 30,
    "auto_retire_on_drift": true,
    "drift_window_days": 7
  },

  "lineage": {
    "originating_alpha_sources": ["liquidation_cascade", "funding_skew", "cross_asset"],
    "parent_hypothesis_id": null,
    "mutation_of": null
  }
}
```

#### §3.3.2 LLM 角色分工

**L1 Ollama**（每小時，連續，無成本）做的事：
- **Parameter mutation**：對現有 active hypothesis 微調參數（如 z_score 從 2.0 → 1.8、time_elapsed 從 300s → 240s），產生 mutation hypothesis
- **A/B variant generation**：把現有 hypothesis 的單一條件翻轉產 A/B（如 regime_filter on/off）
- **Hypothesis pruning**：對 paper-stage 表現差的 hypothesis 建議 retire

**L2 Claude/GPT**（每天 1 次 + regime-shift 觸發，預算 envelope）做的事：
- **Novel hypothesis synthesis**：基於最近市場數據 + 失敗 hypothesis 教訓，產 3-5 個新 hypothesis spec
- **Cross-asset / regime 分析**：寫 daily market memo（GUI 顯示，audit 留證）
- **Failed-hypothesis postmortem**：每週 retire 的 hypothesis 寫 root cause 分析

#### §3.3.3 Safety / Sandbox

LLM 產出的 spec **絕對不直接編譯為 Rust code**。流程：

1. LLM 產 JSON spec → 寫入 `learning.hypotheses` 表，state=DRAFT
2. `hypothesis_validator.rs`（Rust）做 schema validation + bounds check（size_cap_pct ≤ 5%、alpha_bps in [1, 100]、blocked features blacklist 等）
3. Pass → state=REGISTERED，編譯為 `GenericHypothesisStrategy` Rust struct（已存在的 Strategy trait 的通用實現）
4. 該 struct 的 `on_tick` 是一個 **interpreter**：讀 spec.trigger_conditions 對 AlphaSurface 求值，無 free-form 計算

**這意味著 LLM 永遠不寫 Rust，永遠不碰 risk config，永遠不發 order。** 只是寫 declarative spec。

LOC: ~1500 Python + ~800 Rust，2-3 sprint。**這是 ASDS 最大的單一工程投入。**

### §3.4 Tier 3 — Auto-Validator

每個 REGISTERED hypothesis 自動進入 validator：

1. **Replay 30d backtest**：用 existing replay engine + synthetic fill model（已有 paper engine 的 queue-aware sim）
2. **CPCV walk-forward**：3-fold purged combinatorial cross-validation（filling V004 預留的 `learning.cpcv_results` 表）
3. **Deflated Sharpe Ratio**：accounting for multiple testing（trials count from `strategy_trial_ledger`）
4. **Cost-edge gate**：使用既有 `cost_edge_advisor` 確認 net edge > 0
5. **Verdict**：寫入 `learning.hypotheses.validation_verdict`
   - PASS → state=EXPERIMENTING（進 paper）
   - REJECT → state=REJECTED（permanent，log reason）

**統計嚴格性是這層的核心**：retail bot 失敗最大原因是 overfitting。CPCV + DSR + multiple-testing correction 是學術標準（Bailey & López de Prado 2014）。

LOC: ~600 Python，1 sprint（CPCV writer + DSR calc + verdict propagation）。

### §3.5 Tier 4 — Stage 0 Paper（Auto + Thompson Sampling）

paper stage 是 ASDS 的 **多臂老虎機**：

- 每個 EXPERIMENTING hypothesis 都在 paper engine 跑
- **Thompson Sampling allocator**（per `bayesian_posteriors` 表，最終接上 writer）：
  - 維持每個 hypothesis 的 PnL Beta distribution
  - Per-tick：draw from posterior → 對最高 sample value 的 hypothesis 分配 next signal
  - 自然平衡 exploration（新 hypothesis 拿 prior）vs exploitation（成熟好 hypothesis 拿更多）
- 7-14d minimum observation → gate：`paper_sharpe > 0.8 + dsr > 0.90 + n_trades >= 30` → state=EVIDENCE_GATE

LOC: ~400 Python (Thompson allocator) + ~200 Rust (paper-side hypothesis routing)，1 sprint。

### §3.6 Tier 5 — Stage 1 Demo Canary

接到既有 Stage 0R replay → Stage 1 Demo micro-canary 流程（AMD-2026-05-15-01）：

- 一次只 1 hypothesis × 1 symbol × $10k demo budget × 14d
- 既有 5-gate 全保留（Decision Lease、Guardian、H0 fail-closed）
- Gate: `demo_sharpe > 1.0 + dsr > 0.95 + max_dd < 5%` → state=PROMOTED

**這層 0 新工程**，純複用 existing canary。只需 hypothesis_id 接到 Decision Lease attribution。

LOC: ~100 (Rust attribution wire-up)，0.3 sprint。

### §3.7 Tier 6 — Live Promotion

operator 仍需 review PROMOTED hypothesis 決定是否啟動 live。但**不需要設計策略**——operator 只是 yes/no 簽核。

新引入：**Per-hypothesis live budget**（W-AUDIT-8g 的 lite 版本）：

```
LiveBudget {
  hypothesis_id: String,
  max_notional_usd: $200 (initial),
  max_daily_loss_usd: $20,
  auto_revoke_on_drawdown_pct: 10,
}
```

`live_reserved` 系統級 flag 仍是硬閘門；新增 per-hypothesis 細分配。

LOC: ~300 Rust + ~200 Python，1 sprint。

### §3.8 Tier 7 — Auto-Retire

連續監控所有 EXPERIMENTING / PROMOTED hypothesis：

- **ADWIN drift** on hypothesis PnL：alpha decay detection
- **Rolling DSR**：7d rolling window，掉到 < 0.85 → flag for retire
- **Position-level guardrail**：個別 hypothesis 連續 5d 虧損 → 自動 PAUSED（不 PROMOTED retire，等 cooldown）
- **Action**：state=EXPIRED，從 paper/demo/live 全部拉下；落 `auto_retire_log`

LOC: ~400 Python (drift + retire logic) + ~150 Rust (state propagation)，1 sprint。

---

## §4 Multi-Agent 框架 retrofit（從 v1 §3.3 升級）

v1 提到的 Scout / Analyst / Guardian retrofit 仍適用，但 **role 重新定義**：

### §4.1 Scout — 從靜態 25-symbol → 動態 alpha-seeking scanner

| Before | After |
|---|---|
| `max_symbols=25` hardcoded | tier_A pin top-50 + tier_B 浮動採樣 50-100 |
| 純被動掃描 | 主動觸發 EventAlert：new listing / large funding flip / cross-venue divergence |
| 0 hypothesis trigger | scout 可在 IntelObject 觸發 **L1 hypothesis mutation request** |

LOC: ~500 Python，1 sprint。

### §4.2 Strategist — 從 H1/H3/H4 gate → Hypothesis Orchestrator

| Before | After |
|---|---|
| 包裝 IntelObject 為 TradeIntent | 接 Tier 1 RegimeTag + Tier 2 active hypothesis → 對每個 tick 篩出 eligible hypothesis |
| 無 pattern discovery | 委派 hypothesis generation 給 Tier 2 LLM 層 |
| 1 → 1 mapping | n hypothesis → m signals per tick，由 Thompson allocator 仲裁 |

LOC: ~600 Python，1 sprint。

### §4.3 Guardian — 增加 contra-consensus + hypothesis-aware

| Before | After |
|---|---|
| 5 項 conservative-only check | 同上 + `contra_consensus_allowed` flag（反共識策略不再被 "方向衝突" 拒絕） |
| 系統級 live_reserved | 同上 + per-hypothesis live budget enforcement |
| 拒絕高相關性 | hypothesis 之間若 lineage 標 `independent_alpha=true` 不算 correlation conflict |

**Guardian 仍是唯一 veto authority**——LLM 產出的任何 hypothesis 都不能繞過 Guardian。

LOC: ~250 Rust + ~100 Python，0.5 sprint。

### §4.4 Analyst — 從 post-hoc 統計 → Hypothesis Postmortem + Drift Engine

| Before | After |
|---|---|
| 純事後統計 | 同上 + 對 retire 的 hypothesis 觸發 L2 postmortem |
| 0 hypothesis-driven analysis | 為每個 active hypothesis 維持 Bayesian posterior + ADWIN drift state |

LOC: ~500 Python，1 sprint。

### §4.5 Executor — 0 change

Executor 已經設計合理，只需接 `originating_hypothesis_id` 到 ExecutionReport（已 Phase 4 covered）。

### §4.6 Conductor — 增加 Hypothesis-Level Scheduling

新職責：管理 hypothesis pool 的 lifecycle 狀態轉移（DRAFT → ... → EXPIRED）+ LLM call scheduling within budget envelope。

LOC: ~300 Python，0.5 sprint。

---

## §5 LLM 經濟學（成本必須 < 系統 P&L 的 20%）

### §5.1 L1 Ollama（本地，無 marginal cost）

- 已 deployed（`ollama_client.py`）
- 模型：llama3.1:8b 或 qwen2.5:7b（local，~5 GB）
- 用途：parameter mutation、A/B variant、regime narrative
- Cost: 0（僅 trade-core CPU/GPU）
- Cadence: 連續 / 每小時 / per-event

### §5.2 L2 Cloud（envelope 預算）

| Provider | Model | Input $/M tok | Output $/M tok | 用途 |
|---|---|---|---|---|
| Anthropic | claude-opus-4-6 | $15 | $75 | 重要 hypothesis synthesis、postmortem |
| Anthropic | claude-sonnet-4-6 | $3 | $15 | 日常 hypothesis generation |
| OpenAI | gpt-5 | $10 | $30 | backup / 對比 |

**Monthly budget envelope**：

```
假設 daily 1 hypothesis cycle:
  - input: 8k tokens (market state + active hypothesis + recent fails)
  - output: 3k tokens (3-5 new spec JSON)
  - per call (Sonnet): 8 × $0.003 + 3 × $0.015 = $0.069 = ~$0.07
  - per call (Opus): 8 × $0.015 + 3 × $0.075 = $0.345 = ~$0.35

Daily strategy:
  - 1 Sonnet hypothesis gen: $0.07
  - 1 Sonnet regime memo: $0.05
  - 1 Sonnet postmortem (weekly avg): $0.05/7 ≈ $0.007
  - Total daily: ~$0.13
  - Monthly: ~$4

加 buffer for special triggers (regime shift, drift detected):
  - Monthly envelope: $20-50 hard cap
```

**Budget enforcement**：
- `learning.ai_invocations` ledger 已存在
- 新增 `monthly_envelope_check` 在每個 L2 call 前 query：if month-to-date spend > envelope → 退回 L1 / skip
- ALERT operator 在月度 80% threshold

### §5.3 ROI check

```
Worst case: $1k live × Sharpe 0.5 × annual = $50 P&L/yr
Best case: $1k live × Sharpe 1.5 × annual = $150 P&L/yr
LLM cost: $20-50/mo × 12 = $240-600/yr

可能 LLM cost > P&L！
```

**這是真實警報。** $1k live 規模下，LLM 成本可能吃掉所有 P&L。

兩條解：

**(a)** ASDS 的真實 reward 不是 $1k live 的 P&L，是 **demo evidence 證明架構成立，operator 才放大 live size**。即「研究投資」階段，不期望 live P&L 覆蓋成本。

**(b)** LLM 預算 tight 收：monthly envelope $10-15，主要靠 L1 Ollama，L2 只在重大事件觸發。代價是 hypothesis 質量降。

我建議 **(a)**：6 個月 PoC 期接受 LLM cost > live P&L；6 個月後評估是否擴 live size 到 $5k+ 讓 P&L 跨過成本線。

---

## §6 ADR-0024 草稿（新 ADR，必須通過才能執行 ASDS）

```markdown
# ADR 0024: Layer 2 Autonomous Hypothesis Generation Within Budget Envelope

Date: 2026-05-20
Status: PROPOSED (supersedes ADR-0020 §Decision clause partially)

## Context

ADR-0020 (2026-05-09) decided Layer 2 cloud LLM is manual+supervisor-only,
prohibiting autonomous loops. Operator decision 2026-05-20 mandates fully
autonomous trading system requiring Layer 2 to participate in continuous
hypothesis generation cycle without per-call operator approval.

## Decision

Layer 2 cloud LLM MAY run as autonomous component of Hypothesis Generation
cycle IFF ALL of the following hold:

1. Pre-authorized monthly USD budget envelope; ledger enforced
2. Layer 2 output is RESTRICTED to: hypothesis spec JSON, regime narrative,
   postmortem text. Layer 2 NEVER writes risk config, NEVER grants live
   authorization, NEVER submits orders, NEVER mutates Rust strategy/risk
   configuration at runtime.
3. Every Layer 2-generated hypothesis spec MUST pass through:
   - Tier 3 Auto-Validator (CPCV + DSR + cost-edge gate)
   - Tier 4 Stage 0 Paper (7-14d minimum)
   - Tier 5 Stage 1 Demo Canary (operator-reviewed promotion)
   - Tier 6 Live (operator-explicit yes/no per hypothesis)
4. Layer 2 model + temperature + system prompt are version-controlled in
   `docs/llm_specs/` and changes require AMD-level review
5. All Layer 2 invocations logged in `learning.ai_invocations` with
   full prompt + response audit trail
6. Operator may pause Layer 2 autonomous mode at any time via
   `IPC PauseL2Autonomous` (kill switch, < 5 sec effect)

ADR-0020's prohibition on Layer 2 mutating live config, granting live auth,
submitting orders, or bypassing Rust execution authority REMAINS IN FORCE.
This ADR only carves out the hypothesis-spec generation surface.

## Consequences

- Hypothesis Factory (W-AUDIT-8f) can run autonomously within above bounds
- Monthly LLM cost predictable (envelope ledger)
- All trade-affecting decisions still go through Guardian + Decision Lease
- W-AUDIT-7 manual escalation path remains valid for ad-hoc operator use
- Kill switch IPC required (new IPC command + tests)
```

**這個 ADR 是 ASDS 的 hard precondition。** 不通過則整個方案退回 v1 §3 Phase 4 的純 L1 路徑（capacity 大降）。

---

## §7 修訂 Sprint 計畫（取代 v1 §4）

| Sprint | 週 | 主題 | E1 cap | Milestone |
|---|---|---|---|---|
| **N+0** | 已過 | FOUNDATION | 5+1 | 65% |
| **N+1** | W3-W4 | ⚡ **Execution Hardening + ADR-0024 ratify + Tier 0 MarketStateSnapshot** | 4/6 | 67% |
| **N+2** | W5-W6 | 🧠 **Tier 1 RegimeClassifier + Tier 7 AutoRetire + Hypothesis schema V0** | 4/6 | 70% |
| **N+3** | W7-W8 | 🤖 **Tier 2 Hypothesis Generator (L1+L2) + Tier 3 Auto-Validator** | 5+1 | 75% |
| **N+4** | W9-W10 | 🎯 **Tier 4 Paper Thompson allocator + Multi-Agent Retrofit (Scout/Strategist/Analyst)** | 5+1 | 80% |
| **N+5** | W11-W12 | 🚀 **Tier 5 Demo canary 自動 + Tier 6 per-hypothesis live budget + 首個 hypothesis live PoC** | 4/6 | 85% |
| **N+6** | W13-W14 | 📊 **6 個月 PoC review + 規模化決議（擴 live 或 abort）** | 4/6 | review |

### §7.1 Sprint N+1 詳細

| Task | LOC | Owner | Acceptance |
|---|---|---|---|
| ADR-0024 draft + operator review + ratify | doc | PM | ADR signed + committed |
| Existing audit 4 execution hardening (PostOnly 85% + tier gates) | ~580 | PA→E1+E1a | 7d demo net edge ≥ -5 bps |
| Tier 0 MarketStateSnapshot（cross-asset panel + microstructure + tier classifier） | ~600 Rust | PA→E1 | snapshot in `tick_pipeline_metrics`，per-tick |
| V### migration: `learning.hypotheses` table（schema only，無 writer） | ~150 SQL | E1 | Linux PG dry-run + idempotent |
| Funding_arb permanent retire + Grid v1 frozen ADRs | docs | PM | 2 new ADRs committed |

### §7.2 Sprint N+2 詳細

| Task | LOC | Owner |
|---|---|---|
| Tier 1 RegimeClassifier L0 (Rust) + L1 (Ollama narrative) | ~400 Rust + 300 Py | PA→E1 |
| Tier 7 AutoRetire (ADWIN drift + DSR rolling + state propagation) | ~550 | PA→E1+MIT |
| HypothesisSpec JSON schema v0 + validator | ~400 Py + Rust | PA→E1 |
| `cost_edge_advisor` enable + writer 落 ratio rows | ~50 config | E1 |

### §7.3 Sprint N+3 詳細

| Task | LOC | Owner |
|---|---|---|
| Tier 2 L1 Ollama hypothesis mutation engine | ~600 Py | PA→AI-E→E1 |
| Tier 2 L2 Claude hypothesis synthesizer + cost ledger enforcement | ~500 Py | PA→AI-E |
| Tier 3 Auto-Validator: replay 30d + CPCV 3-fold + DSR gate | ~600 Py | PA→QC→E1 |
| `learning.cpcv_results` + `learning.bayesian_posteriors` writer 接上 | ~300 Py | E1+MIT |
| GenericHypothesisStrategy Rust struct (DSL interpreter) | ~800 Rust | PA→E1 |

### §7.4 Sprint N+4 詳細

| Task | LOC | Owner |
|---|---|---|
| Tier 4 Stage 0 Paper Thompson allocator | ~400 Py | PA→MIT→E1 |
| Multi-agent retrofit: Scout dynamic universe | ~500 Py | PA→E1a |
| Multi-agent retrofit: Strategist hypothesis orchestrator | ~600 Py | PA→E1 |
| Multi-agent retrofit: Analyst hypothesis-driven | ~500 Py | PA→E1 |
| Guardian contra-consensus + hypothesis-aware | ~350 | PA→E1 |

### §7.5 Sprint N+5 詳細

| Task | LOC | Owner |
|---|---|---|
| Tier 5 auto Demo Canary（接 existing Stage 0R/1）| ~200 Rust attribution | E1 |
| Tier 6 per-hypothesis live budget (W-AUDIT-8g lite) | ~500 | PA→E1+BB |
| Live kill switch IPC: PauseL2Autonomous | ~150 Rust | E1 |
| ASDS dashboard GUI tab（hypothesis tree、active/expired、PnL by hypothesis）| ~600 JS | E1a→A3 |
| 第一個 hypothesis 走完整 pipeline → demo PROMOTED → operator review → 可選 live | flow | PM+ops |

### §7.6 N+6 Review Gates

6 個月 PoC review，operator 拍板：
- ASDS 在 demo 是否產生 verifiable alpha（≥ 3 個 hypothesis 從 DRAFT 走到 PROMOTED）
- LLM cost 是否落在 envelope
- Live PoC（若有）的真實 P&L vs cost
- Live size 是否擴大到 $5k+ 或繼續 PoC

**Hard abort criteria**：
- 6 個月內 0 個 hypothesis 達 PROMOTED → 撤退到 v1 §3 Phase 1-2 (execution-only + textbook A/B baseline)
- LLM cost 超 envelope 3 次 → 撤退到 L1-only 路徑
- 任何 Guardian-bypass 事件（即使被 Decision Lease 攔下）→ 暫停 ASDS audit 全鏈

---

## §8 Acceptance Criteria（per phase binary）

### Phase 1 Exit（N+1）
- ✅ ADR-0024 ratified + committed
- ✅ 7d demo PostOnly fill rate ≥ 85%；net edge ≥ -5 bps
- ✅ MarketStateSnapshot per-tick on `trade-core`
- ✅ tier_A/B universe split 落 PG
- ✅ `learning.hypotheses` schema deployed (empty)

### Phase 2 Exit（N+2）
- ✅ RegimeClassifier 5-class output 落 `tick_pipeline_metrics`
- ✅ AutoRetire monitor 7d run，0 false positive
- ✅ HypothesisSpec validator pass synthetic test cases

### Phase 3 Exit（N+3）
- ✅ 第一個 L1 mutation hypothesis 通過 validator
- ✅ 第一個 L2 novel hypothesis 通過 validator
- ✅ CPCV writer + Bayesian posterior writer 真實寫 rows
- ✅ LLM ledger cost tracking accurate

### Phase 4 Exit（N+4）
- ✅ Thompson allocator ≥4 hypothesis 並行 paper
- ✅ Scout 動態 universe（≥50 symbol active sample）
- ✅ Strategist orchestrator 接收 RegimeTag + active hypothesis 路由 signal
- ✅ Analyst 為每個 active hypothesis 維持 posterior + drift state

### Phase 5 Exit（N+5）
- ✅ ≥1 hypothesis 從 DRAFT → REGISTERED → EXPERIMENTING → EVIDENCE_GATE → 進 Demo
- ✅ Per-hypothesis live budget 接通
- ✅ L2 kill switch 7d soak 0 issue
- ✅ ASDS dashboard 顯示 active hypothesis tree

### Phase 6 Review（N+6）
- ✅ ≥3 hypothesis PROMOTED to demo
- ✅ 1 个 hypothesis 達 14d Sharpe > 1.0 in demo
- ✅ LLM cost within envelope ≥ 80% 月份
- ✅ Operator review: live 規模化 yes/no

---

## §9 風險登記（更新 v1 §6）

| ID | 風險 | 機率 | 緩解 |
|---|---|---|---|
| R-ASDS-1 | L2 LLM 產 hypothesis 質量太差，CPCV 全 RED | 高 | 多 LLM provider A/B; prompt engineering iteration; 6 個月 abort gate |
| R-ASDS-2 | LLM cost 超 envelope | 中 | hard cap ledger + automatic L1 fallback |
| R-ASDS-3 | Hypothesis DSL 表達力不足，無法描述真實 alpha | 中 | DSL versioning（v0 → v1 → v2 漸進擴展）;明確 anti-pattern 列表 |
| R-ASDS-4 | Thompson allocator over-allocate 假 alpha hypothesis | 中 | DSR + ADWIN drift 雙保險; manual override 在 dashboard |
| R-ASDS-5 | Guardian 過嚴 / 過鬆 | 低 | Stage 0 paper 是 sandbox; 任何 deploy 前回測 |
| R-ASDS-6 | LLM prompt injection（market data 含對抗性內容）| 低 | LLM output 嚴格 schema validate; 任何 malformed → reject |
| R-ASDS-7 | $1k live 規模下 net P&L < LLM cost | **高** | 接受為 PoC investment; 6 個月後規模化決議 |
| R-ASDS-8 | ADR-0024 不通過 | 中 | fallback to L1-only ASDS（質量降，但仍 autonomous） |
| R-ASDS-9 | Overfit to backtest, paper-to-demo collapse | 高 | CPCV 嚴格 + paper 7d minimum + DSR multiple-testing correction |
| R-ASDS-10 | Operator 介入過頻打斷 autonomy | 中 | dashboard + alert 提供 visibility 但 default 不需 operator action |

---

## §10 不做的事（更新 v1 §7）

新增（基於 ASDS）：

11. ❌ **不要讓 LLM 寫 Rust code 或 production Python**（只寫 declarative spec）
12. ❌ **不要 skip CPCV / DSR 直接從 backtest 上 paper**（multiple testing 是 retail bot 失敗主因）
13. ❌ **不要把 hypothesis state machine 設計成「能跳階」**（DRAFT → PROMOTED 必須走完每階）
14. ❌ **不要讓 L2 LLM 進 hot path**（per-tick 決策永遠 L0 classical，最多 L1 advisory）
15. ❌ **不要把 LLM 看成 oracle**——它是「快速產生 candidate hypothesis 的 brainstorm 機」，所有 hypothesis 都假設 70%+ 會被 validator 拒絕
16. ❌ **不要繞過 Guardian / Decision Lease 為 hypothesis 開特權通道**（無論 hypothesis 多 promising）
17. ❌ **不要在 envelope cap 達 100% 時手動續杯**——讓系統自動降到 L1，這是 cost discipline
18. ❌ **不要混淆「alpha generation」和「risk taking」**——LLM 設計 alpha，但 size / risk 永遠走 Kelly + Guardian
19. ❌ **不要在 PoC 期承諾 P&L 目標**——目標是「驗證架構 + 累積 evidence」，不是賺錢

---

## §11 對 v1 文件的明確差異

| 議題 | v1 推薦 | v2 推薦 | 原因 |
|---|---|---|---|
| 系統定位 | "Discipline execution layer + human signals" | **"Fully autonomous strategy factory"** | Operator REJECT v1 Phase F |
| Hypothesis Pipeline | 排 N+5 / 拉前到 N+3 | **N+3 全棧 land**（generator + validator + interpreter） | 是 ASDS 的 central plank |
| LLM 使用 | L2 manual only (ADR-0020) | **L2 autonomous within envelope (ADR-0024)** | 全自動要求 |
| Account size | 補到 $5k+ | **demo $10k + live $1k 已 done** | Operator 已執行 |
| Strategy 新增方式 | 工程師寫 Rust | **LLM 寫 DSL spec，engine 自動編譯** | 縮短 alpha 開發週期 |
| 第一個 active alpha source | new listing + tier_B + liquidation cascade | **同上 + hypothesis factory 自動生成** | 範式轉變 |

**v1 仍有效的部分**：execution hardening、5-策略 retire/baseline 決定、Scout dynamic universe、Guardian contra mode、$591 物理上限分析（雖然已升級到 $1k 但結構相同）。**v2 是 v1 的 superset，不是 replacement。**

---

## §12 結論：誠實的期望管理

ASDS 是一個**研究級工程投資**。期望管理：

**1 年內現實的 outcome**：
- ✅ 系統 7×24 自動運行
- ✅ 每週產 5-15 個新 hypothesis，多數被 validator 拒絕
- ✅ 每月有 1-3 個 hypothesis 進 paper stage
- ✅ 每 1-2 個月有 1 個 hypothesis 進 demo
- ✅ 半年內或許有 1 個 hypothesis 進 live
- ❓ Live P&L 不確定（$1k 規模下，期望 ±$100/年）
- ❓ LLM cost 約 $200-600/年（可能 > live P&L）

**真實 unlock 條件**：
- 如果 ASDS 在 demo 證明 alpha 真實（Sharpe > 1.0、DSR > 0.95、≥3 個 hypothesis 經獨立驗證）
- → operator 信心擴 live 到 $5k → $10k → $25k
- → P&L 開始覆蓋 LLM cost
- → 系統真正盈利

**如果 6 個月後 ASDS 沒 deliver**：
- 退回 v1 Phase 1-2（execution hardening + textbook A/B）
- 保留 hypothesis pipeline schema + ADR-0024（為未來重啟保留）
- LLM 退到純 L1（envelope = 0）

**最重要的一條**：你要的不是「能賺錢的 bot」（$1k live 規模下不現實），你要的是「**能持續產生 / 驗證 / 擴展策略的工廠**」。當這個工廠跑起來、demo 證明它能找出真 alpha、operator 願意擴規模時，**這套架構就值錢了**——不在 $1k 階段，而在 $50k+ 階段。

---

## §13 立即下一步（operator decisions needed）

按重要性排序：

1. **批准 ADR-0024 草稿**（§6）——否則 ASDS 整體無法 autonomous
2. **批准 5-sprint 修訂 plan**（§7）取代 TODO §1 N+1 ~ N+5 sprint banner
3. **批准 funding_arb permanent retire + grid v1 frozen**（W-AUDIT-8b 已 tombstone，再加 2 條）
4. **批准 W-AUDIT-8a Tier 2 funding skew / Tier 4 sentiment FROZEN**（沿用 v1 §3）
5. **批准 LLM monthly envelope $30-50/月初始**（§5.2）
6. **批准 6 個月 PoC review gate**（§7.6）+ abort criteria

完成這 6 條，PA 可以開始拆 Sprint N+1 詳細 spec。

---

## §14 References

- v1 deprecated doc: `srv/2026-05-20--strategy-architecture-redesign-recommendation.md`（保留為 audit log，不再 active）
- ADR-0020 (manual-only): `srv/docs/adr/0020-layer2-manual-supervisor-only.md`
- W-AUDIT-8a spec: `srv/docs/execution_plan/2026-05-09--w_audit_8a_alpha_surface_foundation_spec.md`
- W-AUDIT-8f spec: `srv/docs/execution_plan/2026-05-09--w_audit_8c_hypothesis_pipeline_spec.md` (R-3 拉前所需)
- 4 sub-audit reports: 本 session 對話（待 PM 批准後歸檔到 4 個 agent workspace）
- CPCV / DSR 學術依據:
  - Bailey & López de Prado (2014), "The Deflated Sharpe Ratio"
  - López de Prado (2018), "Advances in Financial Machine Learning" Ch. 7 (CPCV)
- Multi-armed bandit 部署參考:
  - Thompson Sampling 經典：Russo et al. (2018), "A Tutorial on Thompson Sampling"

---

**END v2**
