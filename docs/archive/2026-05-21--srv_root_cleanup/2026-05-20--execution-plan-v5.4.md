# 玄衡 · Arcane Equilibrium — Execution Plan v5.4

**Adaptive Strategy Lab + Master Trader Copy Trading Scaling**

**日期**：2026-05-20
**Status**：DRAFT — pending operator parallel audit
**Supersedes**: v5.3 (lacks Copy Trading scaling mechanism + artificial jitter mitigation错向)
**Foundation**：13 rounds reviewer audit + operator Q1-Q4 final clarifications

---

## §0 v5.4 vs v5.3 關鍵變化

| Issue | v5.3 (前一版) | v5.4 修正 | 原因 |
|---|---|---|---|
| Scaling mechanism | 隱含 capital ladder (operator 加錢) | **Bybit Master Trader Copy Trading subaccount** as primary scaling | operator 明確不具備 capital ladder 法律資質；Copy Trading 是 retail 唯一合法 leverage |
| Capital structure | 全部 $10k 主帳 | **主帳 $8.5k + Master Trader 副帳 $1.5k** | Copy Trading subaccount 獨立運作 |
| Strategy portfolio | C10 + C13 + Unlock | **主帳 (C10+C13) + 副帳 (Unlock + Pairs + Funding short-only)** | Copy Trading 只支援 perps，C10 spot+perp + C13 options 無法 copy |
| Reverse-snipe mitigation | 未深入考慮 | **Market-driven event triggers + multi-condition logic** (per operator Q3) | 人為 timing/size jitter 是假隨機；真實 robust = market-driven |
| Sensor architecture | Polling-based scanner | **Event-driven WebSocket + microstructure features** (Tier A-D latency) | operator Q3 指出 polling 造成 clock-cluster 風險 |
| Master Trader tier ladder | 未規劃 | **Cadet (Day 1) → Bronze (M2-3) → Silver (M6-9) → Gold (Y2+ stretch)** | Bybit official 4-tier structure with verified requirements |

---

## §1 Constraints (locked, final)

| ID | Value |
|---|---|
| D1a | Trading: Bybit + Binance only |
| D1b | Market data: multi-exchange OK |
| D1c | Bot never touches bank |
| D1d | API no withdraw permission |
| D2 | $10k initial, max real loss $3,000 (30%) |
| D2-modifier | Y1-2 100% reinvest, Y3-5 50/50, Y6+ 30/70 |
| D3 | No outside consultant |
| D4 | Off-exchange Revolut + Wise $2,500 |
| D5 | NOT US tax |
| D6 | Timeline flexible 28-40 weeks acceptable |
| D7 | NO content monetization |
| D8 | Subscriptions = sunk life expense |
| D9 | **Bybit Master Trader Copy Trading subaccount — PRIMARY scaling mechanism** |
| D10 | Prop firm optional (deferred) |
| D11 | Execute v5.4 |

---

## §2 Capital Structure — Two-Account Architecture

```
$10,000 total

主帳 Personal Returns ($8,500):
├─ C10 funding harvest (spot+perp delta-neutral):    $2,500
│  └─ Verified 4.5-7% APR baseline (self-trade only)
├─ C13 options wheel (Bybit options):                $1,500
│  └─ Conditional 8-15% APR, full options stack
├─ Off-exchange Revolut + Wise:                      $2,500
│  └─ D2 reserve (本金 floor)
└─ Cash buffer (Bybit available):                    $2,000

Master Trader 副帳 Copy Trading Returns ($1,500):
├─ Unlock SHORT (perp-only, event-driven):           $700
│  └─ Target 15-25% APR (own returns)
│  └─ Highly reverse-snipe resistant (events public)
├─ Pairs trading (perp-perp market-neutral):         $500
│  └─ Target 10-20% APR
│  └─ Market-neutral, snipe-resistant
└─ Funding short-only (high-threshold):              $300
   └─ Target 20-40% APR (with risk)
   └─ Only deploy when funding > 15 bps + microstructure confirms

Worst-case DD check (correlation-aware):
- 主帳 stress: C10 -5% + C13 assignment -25% × correlation 1.3 = -$675
- 副帳 stress: Unlock squeeze -25% + Pairs breakdown -15% + Funding flip -20% × correlation 1.4 = -$455
- Stack worst: -$1,130 = 11.3% of $10k = within D2 30% ceiling ✓
- Off-exchange untouched: 本金保 $7,370 ✓
```

---

## §3 Market-Driven Trigger Architecture (per operator Q3 correction)

**Core principle**: Strategy triggers MUST be market-driven (≥2 conditions), NOT clock-driven.

```
Data ingestion latency tiers:

Tier A (real-time, <1s) — WebSocket subscribed
├─ Bybit perp price + orderbook L1/L5 (already in codebase)
├─ Binance perp price + orderbook L1/L5 (new, Sprint 1)
├─ Bybit options ticker (new, Sprint 4)
└─ Use for: pairs trading, intraday signals, option entry timing

Tier B (medium, 1-60s)
├─ Funding rate updates (every 1min before settlement)
├─ Bybit allLiquidation feed (WebSocket)
└─ Use for: funding harvest, funding short-only triggers

Tier C (low, 5-30min)
├─ Options chain full snapshot (5min poll, Sprint 4)
├─ Cross-exchange funding spread (5min aggregator)
└─ Use for: C13 strike selection, C4 scanner

Tier D (slow, daily)
├─ Token unlock calendar (Tokenomist daily poll)
└─ Use for: Unlock SHORT scheduling

Per-strategy trigger logic (ALL ≥2 market conditions):

C10 funding harvest (clock + market hybrid):
- Condition 1 (clock): funding settlement period reached (T-1min)
- Condition 2 (market): basis check (spot vs perp price spread < 0.5%)
- Condition 3 (market): orderbook depth sufficient (5-level OI > $50k)
- Action: rebalance perp + spot synchronously
- Natural execution time variance via maker patience

Unlock SHORT (pure event-driven):
- Condition 1 (event): unlock event T-3 days reached
- Condition 2 (market): token spread + funding state confirms tradability
- Condition 3 (market): no opposing whale activity detected (orderbook signal)
- Action: open short with PostOnly maker
- Timing: dispersed across T-3 to T-1, depends on market conditions

Pairs trading (pure market-driven):
- Condition 1 (market): spread z-score > 2.0 from 30d rolling mean
- Condition 2 (market): cointegration test ADF < -2.5 in rolling 90d
- Condition 3 (market): orderbook depth balanced both legs
- Action: long underperformer + short outperformer, market-neutral
- Timing: fires when market diverges, naturally distributed

Funding short-only (threshold + microstructure):
- Condition 1 (market): funding > 15 bps/8h on target symbol
- Condition 2 (market): funding trending up (last 3 periods rising)
- Condition 3 (market): liquidation pressure on long side (LP count up)
- Condition 4 (market): no negative news catalyst expected
- Action: short perp before next funding settle
- Timing: rarely deploys, only on confluence

C13 options wheel (cycle + state hybrid):
- Condition 1 (clock): weekly expiry cycle reached (T-7d before expire)
- Condition 2 (market): IV - RV gap > 10 vol points
- Condition 3 (market): BTC 7d return > -10% (no recent crash)
- Condition 4 (market): 14d realized vol < 70%
- Condition 5 (market): skew not extreme on target strike
- Action: sell OTM put with PostOnly limit
- Timing: weekly cycle but strike selection naturally market-driven
```

**Key implementation point**:
- 沒人為 random jitter
- 全部 trigger 由 market state 決定 firing time
- Natural execution variance via maker patience + market microstructure
- Polling 只用 Tier C/D slow-moving data

---

## §4 Bybit Master Trader Copy Trading Integration

### §4.1 Tier Ladder (verified Bybit official requirements)

| Tier | Total Assets | 7d Cum Followers Profit | 7d Max DD | Profit Share | Realistic Timeline |
|---|---|---|---|---|---|
| **Cadet** | 100 USDT | — | — | 10% | Day 1 (immediate) |
| **Bronze** | 200 USDT | 50 USDT | — | 10% | Month 2-3 (first followers) |
| **Silver** | 1,000 USDT | 1,000 USDT | ≤ 30% | 12% | Month 6-9 (target) |
| **Gold** | 10,000 USDT | 10,000 USDT | ≤ 15% | 15% | Y2+ stretch (institutional-tier) |

### §4.2 Master Trader Strategy Selection

3 copy-tradeable strategies (perp-only, reverse-snipe resistant):

**1. Unlock SHORT** — primary alpha:
- Capital: $700 (47% of subaccount)
- Expected ROI: 15-25% APR on subaccount
- Reverse-snipe risk: 低（events public knowledge）
- Follower attractiveness: 高（clear thesis, periodic events）

**2. Pairs Trading** — market-neutral consistency:
- Capital: $500 (33% of subaccount)
- Expected ROI: 10-20% APR
- Reverse-snipe risk: 極低（spread trade, no direction）
- Follower attractiveness: 中（consistent but lower visible return）

**3. Funding short-only** — opportunistic aggressive:
- Capital: $300 (20% of subaccount)
- Expected ROI: 20-40% APR (when deployed, rare)
- Reverse-snipe risk: 中（directional but funding-driven）
- Follower attractiveness: 高（when active, high returns visible）

**Combined Master Trader subaccount expected**:
- Conservative: 12-15% APR
- Median: 18-22% APR
- High: 25-35% APR (good regime)
- DD target: ≤ 25% (must stay under 30% for Silver tier)

### §4.3 Reverse-Snipe Mitigation (real architecture, not artificial jitter)

Per operator Q3 correction:

**❌ NOT doing** (artificial random):
- Random jitter on entry/exit timing
- Random ±X% on position size
- Random symbol rotation

**✅ DOING** (market-driven):
- All strategies use ≥2 market conditions for triggers
- WebSocket-based real-time signal detection (natural variance)
- PostOnly maker orders with natural fill time variance
- Multi-symbol allocation based on real-time best-edge ranking
- No fixed "rebalance at 12:00 UTC" type logic
- Execution path uses natural microstructure timing

**Additional protections**:
- Position size based on current capital + risk budget (varies naturally)
- Bybit Copy Trading platform handles follower copy with built-in slippage (1-3s typical)
- Position visibility delay (Bybit displays positions with slight lag)
- Multi-strategy diversification means no single策略 entirely predictable

### §4.4 Master Trader Monetization Path

**Y1 (Build Phase, Sprint 1-9)**:
- Sprint 1-3: open Cadet tier Master Trader subaccount (need 100 USDT min)
- Sprint 4-6: deploy Unlock SHORT first (proven thesis)
- Sprint 7-9: deploy Pairs Trading + Funding short-only
- Target end of Y1: Bronze or early Silver tier, 4-10 followers, AUM $5-20k

**Y2 (Scale Phase)**:
- Q1: Silver tier consistent (1k USDT total + 1k/7d follower profit)
- Q2-Q4: AUM growth to $20-50k, monthly profit share $200-800
- Year 2 end target: Gold-tier eligibility (10k+ AUM)

**Y3+ (Steady State)**:
- Silver tier consistent or Gold tier achieved
- Master Trader monthly income $500-2,000+
- Becomes primary monetization channel

### §4.5 Monetization Math (Realistic)

```
$200/month profit share target:

At 10% share (Cadet/Bronze):
- Need follower monthly profit $2,000
- AUM $20k at 10%/mo = $2,000  (not sustainable for followers)
- AUM $40k at 5%/mo = $2,000   (very ambitious)
- AUM $80k at 2.5%/mo = $2,000 (realistic at 30% APR strategy)

At 12% share (Silver):
- Need follower monthly profit $1,667
- AUM $50k at 3.3%/mo = $1,667 (realistic, ~40% APR)
- AUM $80k at 2.1%/mo = $1,667 (steady state)

Realistic Y1 end target: AUM $5-20k, monthly profit share $50-200
Realistic Y2 end target: AUM $20-50k, monthly profit share $200-800
Realistic Y3+ stretch: AUM $50-150k, monthly profit share $800-2,500
```

---

## §5 Engineering Plan — 10 Sprints (32-40 weeks)

### Sprint 1 — Phase 0 + Sensors + Subaccount (Week 0-3)

**Phase 0 catch-up**:
- ssh trade-core verify V096
- Apply V097/V098 (UTC 04-06 low-write window)
- V101 minimal schema (hypotheses + preregistration + trading.fills.track)

**Subaccount setup**:
- Open Bybit Master Trader subaccount
- Transfer 100 USDT → Cadet tier qualified immediately
- API keys: trade + read, NO withdraw

**Off-exchange**:
- $1,500 Revolut + $1,000 Wise

**C10 minimal viable**:
- Top 1 symbol funding harvest (BTCUSDT)
- Simple long spot + short perp + quarterly rebalance
- $2,500 deploy on 主帳

**Tier 0 Sensors (event-driven priority)**:
- Sensor A: Bybit + Binance perp orderbook + price WebSocket subscribed (already exists for Bybit, add Binance)
- Sensor B: Funding rate aggregator (1min poll Bybit + Binance per top 25 symbol)
- Sensor C: Bybit options chain recorder (5min poll, BTC + ETH)
- Sensor D: Tokenomist unlock calendar feed (daily poll)

**Engineering**: 70-100 hr

**KPI**:
- Linux DB head = V098 confirmed
- Master Trader subaccount Cadet tier qualified
- 4 sensors operational

---

### Sprint 2 — Alpha Verification Workbench + Microstructure Features (Week 4-7)

**Workbench analysis (no live deployment)**:
- Unlock SHORT event study (24mo backward, T-7/T-3/T+0/T+3/T+7/T+14)
- C13 options data: IV/RV gap distribution, skew analysis
- Pairs trading: rolling cointegration on 15m/1h pairs
- Funding short-only: high-funding event analysis

**Microstructure feature extractors (NEW per Q3 correction)**:
- Orderbook depth ratio (bid vs ask top 5 levels)
- Recent trade flow imbalance (last 100 trades buy/sell ratio)
- Spread metrics (bid-ask spread, mid-price stability)
- Funding rate momentum (3-period delta)
- Cross-exchange spread state (Bybit vs Binance per symbol)

**Pre-registration drafts**:
- Unlock SHORT pre-reg spec locked
- Pairs trading pre-reg spec locked
- Funding short-only pre-reg spec drafted (refinement in Sprint 5)

**Engineering**: 80-110 hr (mostly Python/SQL analysis + microstructure feature code)

**KPI**:
- Workbench reports for 4 alpha candidates
- Microstructure feature library operational
- Pre-registration tables populated

---

### Sprint 3 — Unlock SHORT Build + Stage 0 Shadow (Week 8-11)

**Unlock SHORT engine** (deploy to 副帳 Master Trader account):
- Event scheduler reading Tokenomist daily
- Position planner with multi-condition triggers (T-3d + market state)
- Risk rules:
  - Max 5 concurrent positions
  - Auto-halt 5 consecutive losers
  - Squeeze detection (price +15% from entry → exit)
- Sizing: $50-150 per event, diversified
- Multi-condition trigger logic per §3
- ~350 LOC Rust + ~150 LOC Python

**Stage 0 shadow run (30d)**:
- Strategy generates "would-have" signals
- No real fills, no capital deployed
- Compare to actual price action
- Validate Pre-registration thresholds

**Engineering**: 110-140 hr

**KPI**:
- Unlock SHORT code complete + pre-registered
- 30d shadow Sharpe + DSR computed
- Gate: shadow Sharpe > 1.0 + n_events ≥ 15 → Sprint 4 micro-live

---

### Sprint 4 — Unlock SHORT Micro Live + C13 Options Stack Phase 1 (Week 12-15)

**Unlock SHORT promotion** (to Master Trader 副帳):
- Stage 0R replay preflight
- Stage 1 Demo micro-canary 7d
- Stage 2 Demo extended 14d
- If acceptance → live $500 initial on Master Trader subaccount
- This makes Master Trader subaccount HAS active live strategy (Cadet → applying for Bronze ladder)

**C13 Bybit Options Stack Phase 1 (主帳)**:
- Bybit options REST + WS client (Rust)
  - Endpoints: instruments-info, tickers, orderbook, order/create
- Options data structures: Greeks, IV, OI, DTE, strikes
- Real-time IV/RV tracking
- ~600 LOC Rust + 200 LOC Python

**Engineering**: 130-170 hr

**KPI**:
- Unlock SHORT first live fills on Master Trader 副帳
- First followers might join (depends on visibility)
- Bybit options data infrastructure complete

---

### Sprint 5 — Pairs Trading Build + C13 Stack Phase 2 (Week 16-19)

**Pairs Trading strategy** (deploy to Master Trader 副帳):
- Cointegration detector (rolling 90d ADF)
- Z-score entry/exit (>2σ entry, 0σ exit)
- Pair selection: BTC/ETH, ETH/SOL, BTC/BCH, ETH/AVAX
- Market-neutral perp long + perp short
- Hedge ratio via Kalman filter (rolling adjustment)
- Multi-condition trigger (z-score + cointegration + orderbook)
- ~400 LOC Rust + 200 LOC Python

**C13 Options Stack Phase 2 (主帳)**:
- Margin calculator (Bybit UTA portfolio margin)
- Risk engine (Greek aggregation, stress test)
- Execution path (order placement, assignment lifecycle, rollover)
- ~500 LOC Rust + 150 LOC Python

**Unlock SHORT scaling**:
- If 15 events live tracked + Sharpe > 1.0 → scale to $700

**Engineering**: 130-180 hr

**KPI**:
- Pairs Trading paper running
- C13 options margin + risk stack complete
- 2 strategies on 副帳 (Unlock live + Pairs paper)

---

### Sprint 6 — Funding Short-Only + C13-VRP Strategy (Week 20-23)

**Funding short-only build** (副帳):
- High-threshold trigger (funding > 15 bps/8h)
- Multi-condition: rising funding + long liquidation pressure + no negative catalyst
- Position sizing: variable based on funding magnitude
- Stop loss: tight (1.5% per position)
- ~250 LOC Rust + 100 LOC Python

**C13-VRP Regime-Filtered strategy** (主帳):
- Entry rules: IV-RV gap > 10 vol pts + BTC stable + low realized vol
- Exit: expire worthless, assignment, or time stop
- Halt: BTC -10% in 7d, RV > 70%
- Pre-registration locked
- ~350 LOC Rust + 150 LOC Python

**Pairs Trading promotion** (副帳):
- Stage 0R + Demo canary
- If pass → live $300 initial on Master Trader 副帳

**Engineering**: 130-170 hr

**KPI**:
- 3 strategies on 副帳 (Unlock live + Pairs live + Funding paper)
- C13-VRP strategy code complete + pre-registered

---

### Sprint 7 — C13-VRP Live + Advisory Allocator (Week 24-27)

**C13-VRP promotion** (主帳):
- Stage 0R replay + Demo canary
- If pass → live $500 initial on 主帳
- Scale ladder: 12 cycles positive → $1,000; 24 cycles → $1,500

**Funding short-only promotion** (副帳):
- Stage 0R + Demo
- If pass → live $300 on 副帳

**Advisory Allocator** (per reviewer):
- NOT auto-allocation
- Generates monthly proposals based on multi-component reward
- Operator approves via Console
- All approved actions through Decision Lease + Guardian + Stage gates

**Engineering**: 90-130 hr

**KPI**:
- All 5 strategies live: 主帳 (C10 + C13) + 副帳 (Unlock + Pairs + Funding)
- Allocator generating proposals

---

### Sprint 8 — Decay Auto-Retire + Discovery Pipeline (Week 28-31)

**Strategy Decay Detector**:
- Event-count based (not calendar):
  - C13-VRP: per-cycle DSR (weekly)
  - Unlock SHORT: per-event DSR
  - Pairs Trading: per-trade DSR
  - Funding short-only: per-deployment DSR
  - C10: per-quarter DSR
- Auto-reduce weight rules:
  - DSR < 0.5 (event count threshold met) → ×0.5 weight
  - DSR < 0.3 → ×0.25 weight
  - DSR < 0.1 → auto-retire

**Discovery Pipeline**:
- Operator + Cowork monthly review
- Sensor data → idea generation
- New hypothesis → paper → micro live → scale
- Max 3 concurrent paper-stage hypotheses

**Console GUI**:
- Strategy weights dashboard (per account)
- Master Trader tier progress widget
- Followers + AUM display
- Decay alerts panel

**Engineering**: 100-140 hr

**KPI**:
- Decay detector running
- First new hypothesis from discovery
- Master Trader subaccount approaching Bronze/Silver tier

---

### Sprint 9 — Auto-Allocator + Master Trader Optimization (Week 32-35)

**Auto-Allocator activation**:
- After 6+ months of advisory mode + 80%+ operator approval rate
- Switch to auto with hard limits:
  - Max single-strategy weight 50%
  - Max weight change per rebalance ±20%
  - Operator emergency override
- Monthly cadence

**Master Trader Optimization**:
- Tier upgrade tracking
- Follower AUM growth analytics
- Master Trader performance attribution per strategy
- Profit share weekly settlement tracking

**Master Trader Strategy Bias Tuning**:
- Adjust strategy mix to optimize for follower attractiveness
- Steady consistent returns > volatile high returns
- Lower max DD priority for tier maintenance

**Engineering**: 70-110 hr

**KPI**:
- Auto-allocator running
- Master Trader Silver tier achieved or close
- Followers AUM > $10k (target end of Sprint 9)

---

### Sprint 10 — Y1 Review + Y2 Planning (Week 36-39)

**Comprehensive Y1 review**:
- 主帳 strategies real performance vs pre-registration
- 副帳 Master Trader monetization performance
- Strategy retire decisions (data-driven)
- Y2 plan: scaling existing + new candidates pipeline

**Y2 candidates to evaluate**:
- Intraday stat-arb live (sensor data 8+ months)
- Hyperliquid integration (if D1a expands)
- Bybit Earn cash management for idle capital
- Additional copy trading strategies

**Engineering**: 50-80 hr

**KPI**:
- Y1 audit report complete
- Y2 spec drafted
- Decision: continue / pivot / scale-back

---

### Sprint Schedule Summary

| Sprint | Weeks | Focus | Engineering hr |
|---|---|---|---|
| 1 | 0-3 | Phase 0 + Sensors + Subaccount | 70-100 |
| 2 | 4-7 | Workbench + Microstructure | 80-110 |
| 3 | 8-11 | Unlock SHORT + Shadow | 110-140 |
| 4 | 12-15 | Unlock Live + Options Stack 1 | 130-170 |
| 5 | 16-19 | Pairs Build + Options Stack 2 | 130-180 |
| 6 | 20-23 | Funding short + C13-VRP | 130-170 |
| 7 | 24-27 | C13-VRP Live + Advisory Allocator | 90-130 |
| 8 | 28-31 | Decay + Discovery | 100-140 |
| 9 | 32-35 | Auto-Allocator + Master Optimization | 70-110 |
| 10 | 36-39 | Y1 Review + Y2 Plan | 50-80 |
| **Total** | **39 weeks** | | **960-1,330 hr** |

Per operator Q4: dev speed faster than estimate; realistic compression to 30-35 weeks possible.

---

## §6 Realistic APR + Income Distribution (v5.4 with Copy Trading)

```
Y1 End-of-Year Expected (Sprint 1-10):

主帳 Self-Returns ($8.5k):
├─ C10: 5% × $2,500 = $125
├─ C13-VRP: 10% × $1,500 = $150
├─ Cash buffer: 2% × $2,000 = $40
├─ Off-exchange: 4% × $2,500 = $100 (Bybit Earn or savings)
└─ Subtotal: ~$415

副帳 Master Trader Self-Returns ($1.5k):
├─ Unlock SHORT: 20% × $700 = $140
├─ Pairs Trading: 15% × $500 = $75
├─ Funding short-only: 30% × $300 = $90
└─ Subtotal: ~$305

副帳 Copy Trading Profit Share (Y1 end):
├─ Cadet/Bronze tier likely (Sprint 4 onwards)
├─ AUM 期望: $5-20k by Sprint 10
├─ Monthly profit share Q3-Q4: $50-200
└─ Y1 cumulative: $200-800

────────────────────────────────
Y1 Total Expected: $920 - $1,520 + Copy Trading income

Y2 Steady State Expected:

主帳 mature:
├─ C10 + C13 + perhaps new hypothesis: 10-13% APR × $9.0k (compounded) = $900-1,170

副帳 Master Trader + Copy Trading:
├─ Self-returns: 20% × $1,650 = $330
├─ Copy Trading profit share Y2: $2,400-9,600 (Silver tier consistent, AUM $20-50k)
└─ Subtotal: $2,730-9,930

Y2 Total Expected: $3,630 - $11,100

Y3+ Stretch:
├─ Master Trader Silver/Gold reach
├─ Copy Trading $5,000-25,000/year
├─ Total $7,000-30,000/year possible

10-year compound model (with Master Trader scaling):

Y1: $10k → $11.0k principal + $400-1,000 cum income
Y3: $14-16k principal + $5-15k cum income (Master Trader scaling)
Y5: $20-30k principal + $15-50k cum income  
Y10: $50-150k principal + $100-500k cum income (if Master Trader achieves Silver/Gold)
```

**Master Trader 是 retail $10k operator 真實 leverage 機制**：自己 $1,500 capital → 透過 follower AUM 放大到 effective $20-100k+ management。

---

## §7 Stress Test (Reverse-Snipe + Correlation-Aware)

**BTC -30% crash scenario with reverse-snipe attempt**:

```
Pre-stress portfolio: $10k
- 主帳 C10 $2,500, C13 $1,500, cash $2,000
- 副帳 Unlock $700, Pairs $500, Funding $300
- Off-exchange $2,500

During -30% BTC crash + sophisticated reverse-snipe attempt:

主帳 stress:
- C10 spot+perp: basis -3% × $2,500 = -$75 (delta-neutral protection holds)
- C13 short puts: BTC -30% causes -25% × $1,500 = -$375 (assignment + IV spike)
- Subtotal: -$450

副帳 stress (reverse-snipe applied):
- Unlock SHORT: alt squeeze coincident -25% × $700 = -$175
- Pairs Trading: correlation breakdown -15% × $500 = -$75
- Funding short-only: funding flip during crash -15% × $300 = -$45
- Reverse-snipe amplification: +20% additional loss = -$59
- Subtotal: -$354

Combined stress total: -$804 = 8.04% of $10k
Plus operational losses (delayed fills, missed exits): -$200
Total stressed: -$1,004 = 10% of $10k ← well within D2 30%

Master Trader 副帳 specific:
- Followers see -8% week → some defection (lose 30% AUM)
- DD breach < 30% maintains Silver tier (if reached)
- Recovery period: 2-3 months to restore tier
```

---

## §8 Reverse-Snipe Mitigation (Architecture, Not Jitter)

Per operator Q3 correction:

**Architectural defenses** (built into strategy design):

1. **Multi-condition triggers**: every strategy needs ≥2 market conditions to fire. Scrapers can't reliably predict trigger because conditions vary independently.

2. **Event-driven over clock-driven**: Unlock events, funding settlements, options expiries are public schedule; but trigger CONDITIONS within those windows are market-state-dependent.

3. **Market-neutral preference**: Pairs and C10 are inherently non-directional. Reverse-snipe needs directional exposure to attack.

4. **Multi-leg structures**: C13 wheel + Pairs are multi-leg, harder to copy and harder to fade.

5. **Real-time microstructure check**: Triggers include orderbook state, recent trade flow. Snipers must wait for clean state to attack, which itself is detectable.

6. **PostOnly maker execution**: We wait for liquidity to come to us, not chase. Snipers can't preempt maker orders sitting in book.

7. **Multi-symbol rotation**: Funding short-only rotates among top 5 funding pairs. Snipers can't predict which symbol next.

**Operational defenses**:

1. **Bybit Copy Trading inherent slippage**: Master positions display has 1-3s lag; followers fill at slightly different price. Natural buffer against sub-second snipers.

2. **PostOnly limit orders**: Maker patience 2-30s natural execution variance.

3. **Position size variation**: Sized by current capital × risk budget, varies naturally each trade.

4. **Strategy diversification**: 5 strategies running concurrently make Master Trader pattern不 monolithic.

**No artificial jitter** (per Q3): clock-driven random timing/size is假 randomness; market-driven natural variance is真 randomness.

---

## §9 Kill Criteria + Decay Auto-Retire

### §9.1 Per-strategy kill criteria

| Strategy | Kill Trigger | Action |
|---|---|---|
| C10 | 30d cum < -2% | Reduce to $1,500, expand cash buffer |
| C13-VRP | 12-cycle Sharpe < 0.3 | Auto-retire, return $ to buffer |
| Unlock SHORT | 30 events Sharpe < 0.3 | Auto-retire |
| Pairs Trading | 20 trades Sharpe < 0.3 | Auto-retire |
| Funding short-only | 5 consecutive losers | Pause 14d, then retry |

### §9.2 Portfolio-level kill criteria

| Event | Action |
|---|---|
| Cumulative loss > $2,500 | WARN, reduce all live size 50% |
| Cumulative loss > $3,000 (D2 30%) | HARD STOP all trading |
| Bybit/Binance regulatory shutdown | Off-exchange $2,500 secure, deployed loss accept |
| Master Trader subaccount DD > 30% | Auto-pause all 副帳 strategies, prevent Silver tier loss |
| Operator burnout 8 weeks 0 commits | Pause sprint, re-evaluate |

### §9.3 Master Trader specific

| Trigger | Action |
|---|---|
| Tier downgrade Silver → Bronze | Investigate strategy, optimize for steady DD |
| Followers AUM drops 50% in 30d | Brand damage assessment, strategy review |
| Bybit Copy Trading policy change | Adapt or migrate to alternative venue |
| Reverse-snipe detected (price action) | Add additional trigger conditions, randomize symbol selection |

---

## §10 Governance Compliance (unchanged)

All Stage transitions per AMD-2026-05-15-01:
- DRAFT → REGISTERED (pre-registration locked)
- → SHADOW → STAGE_0R_REPLAY → STAGE_1_DEMO_MICRO_CANARY (1×1×7d)
- → STAGE_2_DEMO_EXTENDED → STAGE_3_DEMO_FULL → STAGE_4_LIVE_PENDING

ADRs/AMDs unchanged from v5.3 + ADR-0026 v3 event-study + pre-registration.

---

## §11 Subscription / Operator Time

```
Plan Mode per ADR-0027:
- Sprint 1-5: Build mode (~30 hr/week)
- Sprint 6-8: Mixed (~20 hr/week)
- Sprint 9-10: Observe (~10-15 hr/week)
- Y2+: Low Activity (~5-10 hr/week)

Marginal project cost: ~$300-500/year (hosting + API)
Subscription: sunk life expense (D8 simplified)
```

---

## §12 Open Items (Y2+ backlog)

- Intraday stat-arb live deployment (after 8+ months sensor data)
- Hyperliquid / DEX integration (if D1a expands)
- Bybit Earn cash management for idle capital
- Forex / multi-asset (if operator interested)
- Funding rate forecasting ML overlay on C10
- Tier 4 full auto-allocator (operator currently approves)
- Master Trader Gold tier optimization (if Y2 reaches Silver consistent)

---

## §13 References

- v1 through v5.3: `srv/2026-05-20--*.md` (audit trail)
- AMD-01 through AMD-05: governance amendments
- ADR-0011, -0024-lite, -0025 v3, -0026 v3, -0027: active governance
- Round 1-13 audit conclusions
- Bybit Master Trader Tier System (verified Round 13 web search)
- Bybit Copy Trading Documentation (Cadet/Bronze/Silver/Gold)
- SSRN unlock event evidence (Round 6 + Round 11 verified)
- Round 11 Monte Carlo on aggressive layering

---

**END v5.4 — Adaptive Strategy Lab + Master Trader Copy Trading Scaling**

**Sprint 1 dispatch pending operator parallel audit completion.**
