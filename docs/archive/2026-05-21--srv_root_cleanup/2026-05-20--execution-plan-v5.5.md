> ⚠️ 归档历史文档 — 非当前权威。active 状态见 repo 根 `TODO.md`；本文件仅供历史/审计参考。（2026-07-18 审计批量补入）

# 玄衡 · Arcane Equilibrium — Execution Plan v5.5

**Self-Trading Primary + Autonomy + Learning + Copy Trading Moat (deferred enable)**

**日期**：2026-05-20
**Status**：FINAL DRAFT — pending dispatch
**Supersedes**: v5.4 (Copy Trading 過早 primary)
**Foundation**：13 rounds reviewer audit + operator final framing「主帳能力高於 Copy Trading 限制；Copy Trading 待 moat 完備後 enable」

---

## §0 v5.5 vs v5.4 核心轉變

| Dimension | v5.4 | v5.5 |
|---|---|---|
| Bot 定位 | Strategy Lab + Copy Trading Engine 雙產品 | **「完整 quant bot」單一產品**，Copy Trading 是後續可選 monetization channel |
| 主帳 ambition | 部分 strategies | **All strategies including those Copy Trading 無法 copy（spot+perp / options multi-leg）** |
| Copy Trading 時點 | Sprint 1 開副帳 | **Y2+ moat 完備後 enable** |
| 工程 focus Y1 | 主帳 + 副帳並行 | **全力主帳 alpha + autonomy + learning** |
| Reverse-snipe moat | 部分提及 | **獨立 moat construction track（Sprint 8+ design, Y2 build before Copy enable）** |

**操作員核心 thesis**: 主帳完整 quant 能力 > Copy Trading 可 copy 子集。先 build 主帳全棧，後續 export 能 copy 的策略到 Copy Trading channel。

---

## §1 Constraints (locked, final)

| ID | Value |
|---|---|
| D1a | Trading: Bybit primary; Binance trading deferred to Y2 review (ADR-0006 amend) |
| D1b | Market data: multi-exchange OK (Bybit + Binance + OKX + Kraken) |
| D1c | Bot never touches bank |
| D1d | API no withdraw permission |
| D2 | $10k initial, max real loss $3,000 (30%) |
| D2-modifier | Y1-2 100% reinvest, Y3-5 50/50, Y6+ 30/70 |
| D3 | No outside consultant |
| D4 | Off-exchange Revolut + Wise $2,500 |
| D5 | NOT US tax |
| D6 | Timeline flexible 36-48 weeks acceptable (operator dev speed faster) |
| D7 | NO content monetization |
| D8 | Subscriptions = sunk life expense |
| D9 | **Master Trader Copy Trading DEFERRED to Y2 after moat ready** |
| D10 | Prop firm deferred |
| D11 | Execute v5.5 |

---

## §2 Capital Structure — Single Account Full Stack

```
$10,000 total — 100% 主帳 focus

Bybit 主帳 ($7,500 active):
├─ C10 funding harvest (spot+perp delta-neutral):    $2,000
│  └─ 4.5-7% APR baseline, structural alpha
│  └─ NOT copy-tradeable (spot leg incompatible)
├─ C13 options VRP (BTC weekly puts + wheel):        $1,500
│  └─ 10-18% APR target, regime-filtered
│  └─ NOT copy-tradeable (options not in Copy product)
├─ Unlock SHORT (perp-only event-driven):            $1,500
│  └─ 15-25% APR target, SSRN verified direction
│  └─ Copy-tradeable when Y2 Copy enables
├─ Pairs trading (perp-perp market-neutral):          $1,000
│  └─ 10-20% APR, multi-pair (BTC/ETH, ETH/SOL, etc)
│  └─ Two-leg copy risk — uses 主帳 freedom
├─ Funding short-only (high-threshold):               $700
│  └─ 20-40% APR (when deployed)
│  └─ Copy-tradeable when Y2 Copy enables
└─ Bybit cash buffer:                                 $800

Off-exchange ($2,500):
├─ Revolut EUR/USD:                                   $1,500
└─ Wise multi-currency:                               $1,000

Master Trader subaccount:           $0 (Y2 review only)
```

**Strategy classification by Copy-Tradeability** (for Y2 future planning):

| Strategy | Copy-Tradeable? | Reason |
|---|---|---|
| C10 funding harvest | ❌ No | Spot leg can't be copied (Copy Trading is perp-only) |
| C13 options VRP | ❌ No | Options not in Bybit Copy product |
| Pairs trading | ⚠️ Risky | Two-leg copy = leg-fail risk for follower |
| Unlock SHORT | ✅ Yes | Perp-only event-driven, copy-friendly |
| Funding short-only | ✅ Yes | Perp-only directional, copy-friendly |

**Y2 Copy Trading 候選**: Unlock SHORT (primary) + Funding short-only (secondary)。**主帳 C10/C13/Pairs 留自己用**——這是「主帳 ambition > Copy Trading 限制」的具體體現。

---

## §3 Market-Driven Trigger Architecture (per Q3)

All 5 strategies use ≥2 market conditions for triggers. No artificial jitter.

```
Data ingestion tiers:

Tier A (real-time, <1s) — WebSocket
├─ Bybit perp price + orderbook (existing)
├─ Binance perp price + orderbook (NEW Sprint 1)
├─ Bybit options ticker (NEW Sprint 4)
└─ Bybit liquidation feed (NEW Sprint 1)

Tier B (medium, 1-60s)
├─ Funding rate updates (1min poll before settle)
└─ Allliquidation cluster detection

Tier C (low, 5-30min)
├─ Options chain full snapshot (5min)
├─ Cross-exchange funding spread (5min)
└─ Microstructure features (orderbook depth ratio, trade flow imbalance)

Tier D (slow, daily)
├─ Token unlock calendar
└─ Strategy decay/DSR rolling stats

Per-strategy trigger logic (multi-condition):

C10 (clock + market hybrid):
- T-1min before funding settlement
- + Basis check: |spot/perp spread| < 0.5%
- + Orderbook depth: 5-level OI > $50k
- + Funding sign confirmed positive
- → Rebalance perp + spot synchronously

C13 options VRP (cycle + state):
- Weekly expiry cycle (T-7d to T-1d)
- + IV - RV gap > 10 vol points
- + BTC 7d return > -10%
- + 14d realized vol < 70%
- + Skew not extreme on target strike
- + Liquidity check (spread < 5%, OI > 100)
- → Sell OTM put with PostOnly maker

Unlock SHORT (pure event-driven):
- Unlock event T-3 days reached
- + Token spread + funding state confirms tradability
- + No opposing whale activity in orderbook
- + Recent 7d not in extreme regime
- → Open short with PostOnly maker, dispersed T-3 to T-1

Pairs trading (pure market-driven):
- Spread z-score > 2.0 from 30d rolling mean
- + Cointegration ADF < -2.5 in rolling 90d
- + Orderbook depth balanced both legs
- + No leg-specific catalyst (news, listing event)
- → Long underperformer + short outperformer

Funding short-only (threshold + microstructure):
- Funding > 15 bps/8h on target symbol
- + Funding trending up (last 3 periods rising)
- + Liquidation pressure on long side
- + No negative news catalyst expected
- + Symbol top-5 liquidity rank
- → Short perp before next funding settle
```

**Execution path natural variance**:
- PostOnly maker orders with 2-30s natural fill time
- Multi-symbol allocation by real-time best-edge ranking
- Position sizing by current risk budget (varies naturally)
- No fixed clock-time logic

---

## §4 Autonomy & Learning Architecture (per operator framing)

**Self-Trading Bot 必須在 Copy Trading enable 前完成**:

### §4.1 Autonomy Tiers (operator approval gates)

```
Tier 1 (Sprint 1-4): Operator-Approved Strategy Lifecycle
- New strategy: operator drafts pre-registration
- Backtest/shadow: operator reviews results
- Stage 0R replay: operator approves promotion
- Demo canary: automatic per existing Stage gate
- Live promotion: operator approves first deployment

Tier 2 (Sprint 5-7): Operator-Approved Allocation Adjustments
- Allocator generates monthly proposals
- Operator approves each adjustment via Console
- Auto-execute approved actions

Tier 3 (Sprint 8-9): Operator-Approved Decay Retirement
- Decay detector flags strategy (event-count based)
- Operator confirms retire/reduce decision
- Auto-execute approved

Tier 4 (Y2+, after Copy Trading moat ready):
- Auto-allocator with hard limits (max single 50%, change ±20%)
- Auto-decay retire (after manual proven 6+ months)
- Operator emergency override always available
```

### §4.2 Learning System Architecture

```
Layer 1: Sensor Data (continuous, Sprint 1+)
- Options chain, funding rates, unlock events, microstructure features
- All strategy fills + outcomes logged
- Historical replay capability

Layer 2: Per-Strategy Performance Tracking (Sprint 3+)
- Event-count based metrics (per cycle/event/trade)
- Rolling Sharpe, DSR, max DD, win rate
- Pre-registered threshold comparison
- Decay signal generation

Layer 3: Strategy Discovery Pipeline (Sprint 7+)
- Operator + Cowork monthly review (per ADR-0024-lite)
- Sensor pattern detection → new hypothesis drafts
- Pre-registration → paper → micro live → scale ladder
- Max 3 concurrent paper-stage hypotheses

Layer 4: Meta Allocator (Sprint 9+)
- Multi-component reward function (per operator Q3):
  reward = realized_return - λ_dd × max_drawdown_30d
                          - λ_tail × p5_return_30d  
                          - λ_turnover × turnover_cost
                          - λ_slippage × slippage_30d
                          - λ_decay × dsr_decay_signal
- Monthly rebalance proposals
- Operator approves first 6 months
- Auto-execute after proven track

Layer 5: Copy Trading Optimization (Y2+, after moat ready)
- Specific to copyable strategies (Unlock + Funding short-only)
- Optimize for follower attractiveness (consistency, low DD)
- Ranking surface tracking
```

### §4.3 Strategy Decay Auto-Retire

Event-count based (not calendar):

```
Per strategy decay rules:

C10: per-quarter
- Quarter Sharpe < 0.5 → manual review
- Sustained < 0.3 for 2 quarters → reduce weight ×0.5

C13: per-cycle (weekly)
- 12 cycles DSR < 0.5 → reduce weight ×0.5
- 24 cycles DSR < 0.3 → auto-retire

Unlock SHORT: per-event
- 30 events DSR < 0.5 → reduce weight ×0.5
- 60 events DSR < 0.3 → auto-retire

Pairs trading: per-trade
- 20 trades DSR < 0.5 → reduce weight ×0.5
- 50 trades DSR < 0.3 → auto-retire

Funding short-only: per-deployment
- 10 deployments DSR < 0.5 → manual review
- 20 deployments DSR < 0.3 → auto-retire
```

---

## §5 Reverse-Snipe Moat Construction (deferred to Sprint 8+)

**操作員核心 requirement**: 防範 Copy Trading enable 後 reverse-snipe 風險。

### §5.1 Moat Components (Sprint 8 design, Y2 build)

```
Defense Layer 1: Strategy Selection Filter
- Only export to Copy Trading: strategies with reverse-snipe resistance
- Required properties:
  ✓ Multi-condition market-driven trigger
  ✓ Not pure directional momentum
  ✓ Event-driven OR market-neutral OR multi-leg complex
  ✗ Avoid: simple mean reversion, momentum, fixed-time triggers
- Y2 Master Trader candidates: Unlock SHORT (yes), Funding short-only (yes, careful)
- Pairs trading: defer until copyability simulator proves two-leg fill rate > 95%

Defense Layer 2: Execution Architecture
- PostOnly maker only (snipers can't preempt sitting orders)
- Natural fill time variance (no rush market orders)
- Multi-symbol rotation (rotation logic market-state-driven not deterministic)
- Position size varies with risk budget (not fixed)

Defense Layer 3: Master Trader Protocol
- Bybit Copy Trading inherent 1-3s position display lag
- Use copy-friendly order types only
- Avoid stop-loss orders (公開可被 hunt)
- Use mental stops with algorithmic exit triggers

Defense Layer 4: Information Architecture
- Bot maintains separate "trading bot" persona on Bybit
- No social media trading commentary
- No public predictions
- Position visible only via Bybit Copy Trading platform

Defense Layer 5: Active Monitoring
- Detect abnormal price action around our entries/exits
- Flag if specific patterns suggest reverse-snipe
- Auto-adjust trigger conditions if detected
- Strategy rotation if persistent attack
```

### §5.2 Moat Build Sequence

**Sprint 8 (Y1 W28-31)**: Moat design + specification
- Document anti-snipe protocols
- Identify copyable strategy subset
- Spec copyability simulator
- Plan Master Trader subaccount setup

**Sprint 9-10 (Y1 W32-39)**: Moat infrastructure (NOT enabled)
- Build copyability simulator (test which strategies have stable fill rates)
- Build Master Trader ranking dashboard (offline)
- Build Bybit Copy Trading API integration (subaccount management)
- Decision documented: which strategies are Y2 Copy candidates

**Y2 Q1 (W40+)**: Master Trader enable
- Open subaccount with 100 USDT minimum (Cadet tier)
- Deploy first Copy candidate (Unlock SHORT)
- Monitor reverse-snipe signals
- Iterate moat based on real attack patterns

---

## §6 Engineering Plan — 10 Sprints (39 weeks)

### Sprint 1 — Governance + Sensors + C10 Minimal (Week 0-3)

**Governance update**:
- ADR-0006 amend: "Bybit primary execution, Binance market data approved, Binance trading deferred Y2"
- ADR-0020 confirm Layer 2 LLM still manual+supervisor (operator approves new hypothesis)
- TODO.md update (operator does)

**Phase 0**:
- V097/V098 catch-up on Linux DB
- V101 minimal schema (hypotheses + preregistration + trading.fills.track)

**Off-exchange**:
- $1,500 Revolut + $1,000 Wise

**Tier 0 Sensors (event-driven priority)**:
- Bybit perp WebSocket subscribed (extend existing for additional symbols)
- Binance perp WebSocket NEW subscribe (market data only, no trading)
- Bybit allLiquidation WebSocket NEW subscribe
- Funding rate aggregator (1min poll Bybit + Binance, top 25 symbol)
- Options chain recorder (5min poll, BTC + ETH initial)
- Token unlock calendar (daily poll Tokenomist trial)

**C10 minimal viable**:
- Top 1 symbol selection (BTCUSDT for initial)
- Simple long spot + short perp + quarterly rebalance
- $2,000 deploy on 主帳

**Engineering**: 80-110 hr

---

### Sprint 2 — Alpha Verification Workbench (Week 4-7)

**Analysis (no live deployment)**:
- Unlock SHORT event study (24mo, T-7/T-3/T+0/T+3/T+7/T+14)
- Pairs trading rolling cointegration (BTC/ETH, ETH/SOL, BTC/BCH, BNB/BTC, ETH/AVAX)
- C13 options data analysis (IV/RV gap, skew distribution)
- Funding short-only high-threshold analysis

**Microstructure feature library**:
- Orderbook depth ratio
- Trade flow imbalance (buy/sell ratio last 100 trades)
- Spread metrics
- Funding rate momentum (3-period delta)
- Cross-exchange spread state

**Pre-registration drafts** (immutable per ADR-0026 v3):
- Unlock SHORT spec locked
- Pairs trading spec locked
- C13 options scope confirmed
- Funding short-only spec drafted

**Engineering**: 80-110 hr

---

### Sprint 3 — Unlock SHORT Build + Shadow (Week 8-11)

**Strategy module on 主帳**:
- Event scheduler (Tokenomist daily poll)
- Multi-condition trigger (T-3d + microstructure + funding state)
- Position planner (50-150 USD per event, diversified 5-10/month)
- Risk rules (max 5 concurrent, halt 5 consecutive losers, squeeze detect)
- ~400 LOC Rust + 200 LOC Python

**Stage 0 shadow 30d**:
- Strategy generates would-have signals
- Compare to real price action
- No capital deployed
- Validate pre-registration thresholds

**Engineering**: 120-150 hr

**Gate**: shadow Sharpe > 1.0 + n_events ≥ 15 → Sprint 4 Demo promotion

---

### Sprint 4 — Unlock SHORT Live + C13 Options Stack Phase 1 (Week 12-15)

**Unlock SHORT promotion**:
- Stage 0R replay preflight
- Stage 1 Demo micro-canary 7d
- Stage 2 Demo extended 14d
- If pass → live $500 initial on 主帳

**C13 Bybit Options Stack Phase 1**:
- Options REST + WS client (Rust)
- Endpoints: instruments-info, tickers, orderbook, order/create
- Options data structures (Greeks, IV, OI, DTE, strikes, moneyness)
- ~600 LOC Rust + 250 LOC Python

**Engineering**: 150-200 hr

---

### Sprint 5 — Pairs Trading + C13 Stack Phase 2 (Week 16-19)

**Pairs Trading on 主帳**:
- Cointegration detector (rolling 90d ADF)
- Z-score triggers (>2σ enter, 0σ exit)
- Kalman filter hedge ratio adjustment
- Multi-condition trigger
- ~450 LOC Rust + 200 LOC Python

**C13 Stack Phase 2**:
- Margin calculator (Bybit UTA portfolio margin)
- Risk engine (Greek aggregation, stress test)
- Execution path (order placement, assignment, rollover)
- ~600 LOC Rust + 200 LOC Python

**Unlock SHORT scaling**: if 15 events Sharpe > 1.0 → $1,000 live

**Engineering**: 140-190 hr

---

### Sprint 6 — Funding Short-Only + C13-VRP Strategy (Week 20-23)

**Funding short-only build on 主帳**:
- High-threshold trigger (funding > 15 bps + multi-condition)
- Position sizing variable
- Tight stops (1.5% per position)
- ~300 LOC Rust + 150 LOC Python

**C13-VRP Strategy**:
- Regime-filtered weekly put-selling
- Full disciplined rule set
- Pre-registration locked
- ~400 LOC Rust + 150 LOC Python

**Pairs Trading promotion**: Stage 0R → Demo → live $500 if pass

**Engineering**: 130-170 hr

---

### Sprint 7 — C13-VRP Live + Advisory Allocator (Week 24-27)

**C13-VRP promotion**:
- Stage 0R + Demo
- If pass → live $500 initial
- Scale: 12 cycles positive → $1,000; 24 → $1,500

**Funding short-only promotion**: live $300 if Demo passes

**Advisory Allocator** (Tier 2 autonomy):
- Multi-component reward function
- Monthly proposals
- Operator approves via Console
- All approved → Decision Lease + Guardian + Stage gate

**Engineering**: 100-140 hr

---

### Sprint 8 — Decay Detector + Discovery + Moat Design (Week 28-31)

**Strategy Decay Detector**:
- Per-strategy event-count metrics
- Auto-reduce / auto-retire rules
- Manual override via Console

**Discovery Pipeline**:
- Operator + Cowork monthly review
- New hypothesis intake
- Max 3 concurrent paper-stage

**Reverse-Snipe Moat Design** (NEW per operator framing):
- Document copyable strategy criteria
- Spec copyability simulator
- Anti-snipe protocols spec
- Master Trader subaccount setup plan
- NO Master Trader account opened yet

**Engineering**: 110-150 hr

---

### Sprint 9 — Auto-Allocator + Copy Trading Infrastructure (Y2 prep) (Week 32-35)

**Auto-Allocator activation** (Tier 4 autonomy):
- After 6+ months advisory + operator approval rate >80%
- Switch to auto with hard limits
- Max single 50% weight, change ±20%
- Operator emergency override

**Copy Trading Infrastructure (build, don't enable)**:
- Copyability simulator (test fill rates per strategy)
- Master Trader ranking dashboard (offline data)
- Bybit Copy Trading API integration (subaccount management code)
- Anti-snipe monitoring system

**Engineering**: 100-140 hr

---

### Sprint 10 — Y1 Review + Y2 Plan + Master Trader Decision (Week 36-39)

**Comprehensive Y1 review**:
- All 5 主帳 strategies real performance
- Strategy retire decisions
- New hypothesis pipeline status

**Master Trader Y2 Decision** (operator final call):
- Y1 verified alpha proven?
- Reverse-snipe moat ready?
- Operator capacity for additional management?
- If YES: Y2 Q1 open subaccount, deploy Unlock SHORT first
- If NO: continue self-trading only, re-review Y3

**Y2 Plan**:
- Strategy additions (intraday stat-arb if sensor data supports)
- Hyperliquid integration (if D1a expands)
- Capital scaling decisions

**Engineering**: 60-90 hr

---

### Sprint Schedule Summary

| Sprint | Weeks | Focus | Hours |
|---|---|---|---|
| 1 | 0-3 | Governance + Sensors + C10 minimal | 80-110 |
| 2 | 4-7 | Workbench + Microstructure | 80-110 |
| 3 | 8-11 | Unlock SHORT + Shadow | 120-150 |
| 4 | 12-15 | Unlock Live + Options Stack 1 | 150-200 |
| 5 | 16-19 | Pairs + Options Stack 2 | 140-190 |
| 6 | 20-23 | Funding short + C13-VRP | 130-170 |
| 7 | 24-27 | C13-VRP Live + Allocator | 100-140 |
| 8 | 28-31 | Decay + Discovery + Moat Design | 110-150 |
| 9 | 32-35 | Auto-Allocator + Copy Infra (build only) | 100-140 |
| 10 | 36-39 | Y1 Review + Y2 Master Trader Decision | 60-90 |
| **Total** | **39 weeks** | | **1,070-1,450 hr** |

---

## §7 Realistic Y1 Outcome (Pure Self-Trading)

```
Y1 Expected (no Copy Trading income):

主帳 5 strategies:
├─ C10 funding harvest: 5% × $2,000 = $100
├─ C13 options VRP: 10% × $1,500 = $150
├─ Unlock SHORT: 18% × $1,500 = $270
├─ Pairs trading: 12% × $1,000 = $120
├─ Funding short-only: 25% × $700 = $175 (when deployed)
├─ Cash buffer (Bybit Earn 4%): $32
├─ Off-exchange savings: $80
└─ Y1 self-trading total: ~$927 expected median

Low scenario (alpha 半 verified): $500-700
Median: $900-1,100
High (all alpha + good regime): $1,400-1,800

Y1 marginal cost: $300-500/year (hosting + API)
Net Y1 expected: $400-1,500 positive
```

**Note**: No double-counting Copy Trading income (per audit point). Pure self-trading honest math.

---

## §8 10-Year Compound Trajectory (Self-Trading Primary + Y2 Copy Optional)

```
Y1 → Y2 (self-trading only, Copy Trading prep):
$10k → $10.9-11.5k (Y1 ~10% APR median + cash)

Y2 (Master Trader enable if Y1 verified):
- Self-trading mature: $1,200-1,500
- Copy Trading Y2 (Cadet/Bronze, AUM $5-20k): $200-800
- Y2 total: $1,400-2,300 (if Copy enabled)
- Y2 self-only: $1,200-1,500

Y3-5 (Copy Trading scaling if successful):
- Self-trading: $1,500-2,500/yr (compounded principal)
- Copy Trading Silver tier: $2,000-8,000/yr (AUM $20-80k)
- Y5 total: $3,500-10,500/yr if Copy successful
- Y5 self-only: $1,800-3,000/yr

Y10:
- Self-trading only: principal $25-40k + cum income $8-15k = $33-55k
- + Copy Trading reach Silver/Gold sustained:
  Principal $40-100k + cum income $50-300k = $90-400k

Median realistic:
- Self-only: $33-55k Y10
- + Copy success: $50-150k Y10
- + Copy stretch: $200k+ Y10

vs S&P passive 8%: $21.6k Y10

True differential:
- Self-only Y10: ~$10-30k above passive (skills + infrastructure)
- + Copy success Y10: $30-130k above passive
```

**Operator's choice**: 主帳 quality first, Copy Trading is bonus when ready.

---

## §9 Portfolio Stress Test (Audit Point Integrated)

**Multi-scenario stress matrix** (audit critique addressed):

```
Scenario 1: BTC -30% gradual decline over 7 days
├─ C10: basis -3% × $2k = -$60
├─ C13: assignment + IV spike, -25% × $1.5k = -$375
├─ Unlock SHORT: alt squeeze coincident -20% × $1.5k = -$300
├─ Pairs: correlation breakdown -10% × $1k = -$100
├─ Funding: funding flip -10% × $0.7k = -$70
├─ Stack with correlation 1.3x: -$1,180
└─ Total: -11.8% portfolio DD ← within D2 30%

Scenario 2: BTC -50% flash crash 24h
├─ C10: extreme basis -8% × $2k = -$160
├─ C13: deep ITM assignment -35% × $1.5k = -$525
├─ Unlock: alt -40% × $1.5k = -$600
├─ Pairs: extreme breakdown -15% × $1k = -$150
├─ Funding: forced exit -15% × $0.7k = -$105
├─ Operational losses (delayed fills): -$200
├─ Stack with correlation 1.6x: -$2,784
└─ Total: -27.8% portfolio DD ← approaching D2 30%, kill switch fires

Scenario 3: Exchange halt (Bybit) for 48h
├─ All 主帳 positions frozen
├─ Off-exchange $2,500 secure
├─ Worst case Bybit insolvency: -$7,500 = 75% portfolio
├─ D2 hard breach, project ends
└─ Mitigation: off-exchange保 $2,500 minimum

Scenario 4: Alt season pump (HYPE/SUI +200% week)
├─ Unlock SHORT squeeze: -50% × $1.5k = -$750
├─ Funding flip: forced exit -20% × $0.7k = -$140
├─ Pairs may benefit (long alt leg)
├─ C10/C13 unaffected
├─ Total: -8.9% ← within D2

Scenario 5: Options market stress (high IV spike)
├─ C13 multiple assignments, holding spot underwater
├─ Loss limited to assignment delta
├─ Funding income from spot positions partial offset
├─ -15-20% × $1.5k = -$225-300
└─ Total: -2.25-3% ← well within D2

Tail risk summary:
- 99% scenarios within D2 30% ceiling
- Exchange halt is existential risk (off-exchange protection only)
- Bot kill switch fires at -$2,500 cumulative loss
```

---

## §10 Kill Criteria (Comprehensive)

| Event | Action |
|---|---|
| Sprint 1: V097/V098 fail | Block all subsequent |
| Sprint 2: Unlock event study t-stat < 1.5 | Drop Unlock from Sprint 3 |
| Sprint 3: Unlock shadow Sharpe < 0.5 30d | Drop Unlock, redirect $1.5k |
| Sprint 4: C13 Stack blockers | Operator decides defer or push |
| Sprint 6: C13-VRP paper Sharpe < 0.5 | Drop C13, redirect $1.5k |
| Sprint 5: Pairs cointegration unstable | Drop Pairs, redirect $1k |
| Per strategy: live cum < kill threshold | Auto-retire per §4.3 rules |
| Cumulative loss > $2,500 | WARN, reduce all live 50% |
| Cumulative loss > $3,000 (D2 ceiling) | HARD STOP all trading |
| Bybit regulatory shutdown | Off-exchange $2,500 safe, deployed loss accept |
| Operator burnout 8 weeks 0 commits | Pause, re-evaluate |
| Sprint 10 Y1 review: 0 strategy verified | Decision point reset or stop |

---

## §11 Y2 Copy Trading Decision Framework

**Sprint 10 Y1 review evaluates**:

1. **Alpha verification**:
   - At least 1 strategy with sustained Sharpe > 1.0 over 90+ days live
   - Pre-registration thresholds met or exceeded
   - Decay detector showing stable performance

2. **Risk discipline**:
   - Y1 cumulative net P&L > 0
   - Y1 max DD < 25%
   - No D2 ceiling breach events

3. **Moat readiness**:
   - Copyability simulator passes (fill rate > 95% on target strategy)
   - Anti-snipe protocols designed
   - Master Trader API integration complete

4. **Operator capacity**:
   - Sustained Y1 sprint commitment
   - Willing to take on additional Copy Trading management hours

**Decision matrix** (placeholder, operator refines later per Q4):

```
If 4/4 conditions met:
  Y2 Q1: Enable Master Trader subaccount with $1,500
  Deploy Unlock SHORT first (most copy-friendly)
  Monitor follower growth + reverse-snipe signals
  Iterate

If 3/4 met:
  Y2 Q2 review: defer 3 months
  Continue self-trading mature

If <3/4 met:
  Y3 review: continue self-trading only
  Copy Trading remains future option
```

**Important per operator**: "具體門檻我們後續研究"——thresholds are placeholders, operator will refine based on Y1 reality.

---

## §12 Governance Compliance

All Stage transitions per AMD-2026-05-15-01 unchanged.

**New ADR**: ADR-0028 (proposed) "Copy Trading Subaccount Deferred Activation"
- Master Trader subaccount activation requires Y1 verification + moat ready
- Copy Trading strategies subset of main account strategies, filtered for copyability
- Anti-snipe protocols enforced before activation
- Operator final approval for Master Trader open

**ADR-0006 amendment**: "Bybit primary; Binance market data approved; Binance trading deferred Y2 review"

---

## §13 Subscription / Operator Time

```
Plan Mode (ADR-0027):
- Sprint 1-5: Build mode (~30 hr/week)
- Sprint 6-8: Mixed (~20 hr/week)
- Sprint 9-10: Observe/review (~10-15 hr/week)

Marginal project cost Y1: $300-500
Subscription: sunk life expense
```

---

## §14 Y2+ Backlog

- **Master Trader Copy Trading activation** (per §11 framework)
- **Intraday stat-arb live deployment** (after Sprint 9 evaluation)
- **Hyperliquid / DEX integration** (D1a expansion)
- **Bybit Earn cash management**
- **Funding rate forecasting ML overlay**
- **Tier 5 LLM-assisted hypothesis generation** (per ADR-0024-lite expansion)
- **Multi-asset class** (forex / equities, if operator interested)

---

## §15 References

- v1 through v5.4: `srv/2026-05-20--*.md` (audit trail)
- AMD-01 through AMD-05: governance amendments
- ADR-0006 (to amend), -0011, -0024-lite, -0025 v3, -0026 v3, -0027 active
- ADR-0028 (proposed): Copy Trading Subaccount Deferred Activation
- Round 1-13 audit conclusions
- Bybit Master Trader Tier System (verified)
- SSRN unlock event evidence (verified)
- Round 11 Monte Carlo aggressive layering

---

**END v5.5 — Self-Trading Primary, Copy Trading Moat Deferred**

**v5.5 dispatch ready upon operator final approval.**
