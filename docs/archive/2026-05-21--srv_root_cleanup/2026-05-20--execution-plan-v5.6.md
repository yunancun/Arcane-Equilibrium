> ⚠️ 归档历史文档 — 非当前权威。active 状态见 repo 根 `TODO.md`；本文件仅供历史/审计参考。（2026-07-18 审计批量补入）

# 玄衡 · Arcane Equilibrium — Execution Plan v5.6 (FINAL)

**Self-Trading Lab + Macro Overlay + On-Chain Layer + Bybit Earn — Within Bybit Framework**

**日期**：2026-05-20
**Status**：FINAL — pending operator dispatch approval
**Supersedes**: v5.5 (within-framework only) + reviewer §1-5 corrections + Option C framework expansion
**Foundation**：14 rounds reviewer audit converged truth

---

## §0 v5.6 vs v5.5 變化

| Dimension | v5.5 | v5.6 |
|---|---|---|
| Y1 income estimate | $927 median (滿倉假設) | **$300-600 calendar-weighted ($450 median)** |
| Y2 run-rate | implicit | **$1,200-1,800 explicit mature steady state** |
| Stage gate language | "paper" 多處 | **shadow/counterfactual/Stage 0R/Demo (governance compliant)** |
| C13 default form | naked wheel | **defined-risk put spread default; naked confluence only** |
| Build order | 5 strategies pre-committed | **Evidence-based top-1 first, all 5 if evidence supports** |
| Framework scope | Strategies only | **+ Macro overlay + Bybit Earn + On-chain signals layer** |
| Copy Trading enable | Y2 calendar | **Evidence gate + moat gate (Sprint 9 末或更早可達)** |
| Expected APR | 9-12% sustained | **13-18% sustained median** |
| 10-year compound | $25-35k Y10 | **$33-52k Y10 self-only** |
| Engineering hours | 1,070-1,450 | **1,150-1,570 (+80-120 for framework expansion)** |

---

## §1 Constraints (locked, final)

| ID | Value |
|---|---|
| D1a | Trading: Bybit primary (Binance market data Y1, trading Y2 review) |
| D1b | Market data: multi-exchange OK including OKX/Kraken for cross-reference |
| D1c | Bot never touches bank |
| D1d | API no withdraw permission |
| D2 | $10k initial, max real loss $3,000 (30%) |
| D2-modifier | Y1-2 100% reinvest, Y3-5 50/50, Y6+ 30/70 |
| D3 | No outside consultant |
| D4 | Off-exchange Revolut + Wise $2,500 |
| D5 | NOT US tax |
| D6 | Timeline flexible 36-48 weeks acceptable |
| D7 | NO content monetization |
| D8 | Subscriptions = sunk life expense |
| D9 | Copy Trading evidence-gated (not Y2 calendar; Sprint 9 末 ready min) |
| D10 | Prop firm deferred |
| D11 | Execute v5.6 |
| **D12 NEW** | **Framework expansion: Macro overlay + Bybit Earn + On-chain signals approved; Hyperliquid DEX NOT approved (preserve Bybit primary)** |

---

## §2 Capital Structure — Bybit Primary + Earn Cash Management

```
$10,000 total — 100% within Bybit framework

Bybit 主帳 ($7,500 active):
├─ C10 funding harvest (spot+perp delta-neutral):    $2,000
│  └─ 4.5-7% APR baseline, structural alpha
├─ C13 options VRP defined-risk (put spreads):       $1,500
│  └─ 8-15% APR target with capped tail risk
├─ Unlock SHORT (perp-only event-driven):            $1,500
│  └─ 15-25% APR target, SSRN verified direction
├─ Pairs trading (perp-perp market-neutral):          $1,000
│  └─ 10-20% APR multi-pair (BTC/ETH, ETH/SOL, etc)
├─ Funding short-only (high-threshold):               $700
│  └─ 20-40% APR when deployed (rare)
└─ Bybit Earn cash management (NEW):                  $800
   └─ USDT savings 4-8% APR (replaces idle cash buffer)

Off-exchange ($2,500):
├─ Revolut EUR/USD:                                   $1,500
└─ Wise multi-currency:                               $1,000

Master Trader subaccount: $0 (evidence-gated activation)

Strategy classification (for Y2 Copy Trading export):
├─ Self-only (can't copy):  C10, C13 options spread, Pairs (two-leg risk)
└─ Copy candidates (perp-only, snipe-resistant):  Unlock SHORT, Funding short-only
```

**Bybit Earn cash management** (NEW per Option C):
- Replaces v5.5's $1,000 idle buffer
- USDT savings 4-8% APR (Bybit Earn product, no lock-up)
- Instant convertibility back to trading margin
- ~$32-64/yr passive yield uplift
- Engineering: ~10 hr (existing Bybit API extension)

---

## §3 Framework Expansion Layers (Option C 加入)

### Layer 1: Macro Calendar Overlay (NEW)

**目的**: 提升所有 strategy 的 timing/sizing quality，不是新 alpha source.

**Macro events tracked**:
- FOMC meetings (8x/yr) — IV spike windows
- CPI/PPI releases (12x/yr) — short-term volatility events
- ETF flow data (daily Glassnode + 13F filings) — directional bias
- Bitcoin halving cycles (Y4 reference)
- Major exchange listings/delistings — alt season catalysts
- Token unlock cluster events (Unlock SHORT already uses)

**Overlay rules per strategy**:

```
C13 options VRP:
- 24h before FOMC → halt new put sales (IV spike risk)
- 24h after FOMC → resume normal entry
- Post-CPI: assess realized vol shift before next cycle

C10 funding harvest:
- Post-FOMC 24h: funding often normalizes → opportunity to re-enter
- Halving event: long-term funding regime may shift, monitor carefully

Unlock SHORT:
- Macro risk-on (post-FOMC dovish): alts pump risk → reduce position size
- Macro risk-off (CPI hot, FOMC hawk): increase position size confidence

Pairs trading:
- High-vol regime: spread divergence faster, tighter stops
- Low-vol regime: longer holding times acceptable

Funding short-only:
- Post-macro event: funding regime can flip → re-evaluate before entry
```

**Engineering**: ~30-50 hr (calendar feed + overlay rule engine)

**Expected uplift**: 1-3% portfolio APR via better risk-adjusted timing

### Layer 2: On-Chain Signals (NEW)

**目的**: 額外 alpha layer 利用 retail systematically ignored 的 on-chain data.

**Free data sources**:
- Glassnode free tier (exchange flows, supply metrics, NUPL)
- Etherscan / blockscan public APIs (whale wallet monitoring)
- DeFiLlama (stablecoin TVL, protocol flows)
- CryptoQuant free tier (some metrics)

**Signal types**:

```
Exchange inflow surge:
- BTC inflow to exchanges +30% in 24h above baseline
- → bearish signal, increase Unlock SHORT confidence
- → reduce C13 put-selling exposure

Stablecoin mint surge:
- USDT/USDC supply +1% in 7d
- → bullish liquidity inflow
- → favor long-side positions, reduce shorts

Whale wallet alerts:
- Known whale addresses transferring >100 BTC or >1000 ETH
- → directional bias signal
- → adjust strategy sizing accordingly

Stablecoin TVL flow:
- Major DeFi protocol seeing TVL outflow
- → risk-off signal
- → tighten all directional positions
```

**Engineering**: ~40-60 hr (free API integrations + signal aggregation)

**Expected uplift**: 1-2% portfolio APR

**Limitation**: Free tier APIs have rate limits. Paid tier ($30-100/mo Glassnode pro) might be needed if signals prove valuable. Operator approves before paid upgrade.

### Layer 3: Bybit Earn Cash Management (NEW)

**目的**: Idle cash 不再死資本.

**Implementation**:
- USDT idle cash → Bybit Earn flexible savings 4-8% APR
- Instant withdrawal when strategies need margin
- Auto-rebalance: when margin headroom < 30%, auto-pull from Earn
- ~$800-1,500 typically idle

**Engineering**: ~10 hr (existing Bybit API)

**Expected uplift**: 0.5-1.5% portfolio APR

---

## §4 Realistic Y1 + Y2 Outcome (Calendar-Weighted, Honest)

### Y1 Expected (Sprint 1-10, ~40 weeks)

Calendar-weighted by strategy live start date:

```
Y1 expected income breakdown:

C10 funding harvest:
  - Live from W3, 36 weeks of 52 = 0.69x annualization
  - 5% × $2,000 × 0.69 = $69

Unlock SHORT:
  - Live from ~W14 (after Stage 0R), 25 weeks of 52 = 0.48x
  - 18% × $1,500 × 0.48 = $130

Pairs trading:
  - Live from ~W22, 17 weeks of 52 = 0.33x
  - 12% × $1,000 × 0.33 = $40

C13 options VRP (defined-risk):
  - Live from ~W28, 11 weeks of 52 = 0.21x
  - 10% × $1,500 × 0.21 = $32

Funding short-only:
  - Live from ~W26, 13 weeks of 52 = 0.25x
  - 25% × $700 × 0.25 = $44

Bybit Earn cash management:
  - Active from W3, 36 weeks = 0.69x
  - 6% × $800 × 0.69 = $33

Off-exchange savings:
  - Active from Day 1, full year
  - 4% × $2,500 = $100

Macro overlay quality uplift (~+1-3% on strategy returns):
  - Applied W12+ ~30 weeks = 0.58x
  - +2% × $5,400 active capital × 0.58 = $63

On-chain signals layer:
  - Active from ~W16, 23 weeks = 0.44x
  - +1.5% × $5,400 active capital × 0.44 = $36

Y1 Total Expected (median): ~$547 ≈ 5.5% Y1 APR
Y1 Range: $350-800 (low to high scenario)
```

### Y2 Mature Run-Rate

```
Y2 expected (full-year deployment):

C10: 5% × $2,000 = $100
Unlock SHORT: 18% × $1,500 = $270
Pairs trading: 12% × $1,000 = $120
C13 defined-risk: 10% × $1,500 = $150
Funding short-only: 25% × $700 = $175
Bybit Earn: 6% × $800 = $48
Off-exchange: 4% × $2,500 = $100
Macro overlay: +2% × $5,400 = $108
On-chain signals: +1.5% × $5,400 = $81

Y2 Total Expected (median): ~$1,152 ≈ 11.5% Y2 APR
Y2 Range: $850-1,700

Aggregate APR including all layers: 11.5% mature
v5.5 without Option C expansion: 9.5% mature
Differential from framework expansion: +2% APR ($200/yr on $10k)
```

### 10-Year Compound Trajectory

```
Y1: $10k → $10.5k (5.5% Y1 calendar-weighted)
Y2: $10.5k × 1.115 = $11.7k (mature steady state)
Y3: $11.7k × 1.115 + Y3 yield = $13.0k
Y5: ~$15.5k (assuming sustained 11.5%)
Y7: ~$19.3k
Y10: $10k × 1.115^10 ÷ adjusted = **~$30-35k principal + cumulative withdrawals**

Conservative path (8% sustained): $10k → $21.6k Y10
Median path (12% sustained): $10k → $31.1k Y10
Stretch path (16% sustained): $10k → $44.1k Y10 (requires Copy Trading scaling)

vs S&P passive 8%: $10k → $21.6k Y10
v5.6 expected differential: +$10-23k over 10 years
+ skills + infrastructure + Copy Trading optionality
```

---

## §5 Defined-Risk C13 Strategy (per reviewer §3 fix)

**v5.5 issue**: naked wheel as default has IV spike + margin expansion + forced liquidation tail risks not adequately modeled.

**v5.6 fix**: defined-risk put spread as default form:

```
C13 default mode: Defined-Risk Put Spread
- Sell put at 8-12% OTM (collect premium)
- Buy put at 15-20% OTM (cap downside)
- Max loss = (short strike - long strike) - net premium
- Margin requirement: width × contract size (not full naked margin)
- Capital efficient + tail risk bounded

C13 advanced modes (only on confluence):
1. Cash-secured naked put:
   - IV-RV gap > 15 vol points (premium 充足)
   - BTC 30d return > +5% (近期不弱)
   - Cash buffer ≥ 2x potential assignment value
   - Account portfolio margin headroom > 50%
   - All 4 satisfied → may use naked put
   
2. Covered call (post-assignment):
   - Spot BTC held (from put assignment)
   - Sell call at 10-15% OTM
   - Wait for either expiration or roll
   - Standard wheel post-assignment

3. Iron condor (advanced):
   - Both put spread + call spread
   - Profit from sideways markets
   - Used in low-vol stable regime only

Engineering scope: ~50-80 hr additional vs naked-only design
Expected APR slightly lower (10-15% vs naked theoretical 15-20%)
But max DD on this sleeve dramatically reduced (8-15% vs 25-40% naked)
```

---

## §6 Evidence-Based Build Order (per reviewer §4 with nuance)

**v5.5 issue**: pre-committed to all 5 strategies build, regardless of Sprint 2 evidence.

**v5.6 fix**: Sprint 2 evidence ranks all 5 candidates; build order follows evidence; all 5 eventually built if evidence supports.

```
Sprint 2 Alpha Tournament — produces ranked candidate list:

For each candidate (Unlock, Pairs, C13, Funding short, C10 enhancements):
- Real data analysis with verified statistics
- Pre-registration draft locked
- Expected APR + DD profile + capacity estimate
- Implementation complexity score

Sprint 3-7 build order (driven by ranking):

Sprint 3: Build top-1 candidate first
  Highest evidence + lowest implementation risk → priority deploy
  
Sprint 4: Continue top-1 to live + start top-2 build
  Top-2 in shadow/development as top-1 enters Stage 0R
  
Sprint 5-6: Build top-3 + start top-4 in workbench
  
Sprint 7: Build top-5 if all previous performing
  Last candidate to deploy
  
Sprint 8+: Decay detector kills underperformers, frees capital for re-allocation

Important: If Sprint 2 evidence shows candidate has t-stat < 1.5 or
infeasible deployment, REMOVE from build queue. Don't waste sprints on
disconfirmed alpha.

Worst case: only 2-3 candidates verify → build only those, keep capital in
Bybit Earn for non-deployed sleeves.

Best case: all 5 verify → build all 5 over Sprint 3-7.

Operator approves each promotion to live deployment.
```

---

## §7 10-Sprint Plan (Updated for Option C Framework Expansion)

### Sprint 1 — Governance + Sensors + C10 + Earn (Week 0-3)

**Governance**:
- ADR-0006 amend: "Bybit primary trading; Binance market data Y1; Binance trading Y2 review; DEX/Hyperliquid NOT approved (D12)"
- V097/V098 Linux DB migration catch-up
- V101 minimal: hypotheses + preregistration + trading.fills.track
- TODO.md update

**Off-exchange**:
- $1,500 Revolut + $1,000 Wise

**Bybit Earn cash management (NEW, simple)**:
- USDT savings integration
- Auto-rebalance idle cash
- $800-1,000 deployed to Earn

**Tier 0 Sensors (event-driven)**:
- Bybit perp WebSocket (extend existing)
- Binance perp WebSocket (NEW)
- Bybit allLiquidation WebSocket (NEW)
- Funding rate aggregator (1min poll)
- Options chain recorder (5min poll Bybit BTC + ETH)
- Token unlock calendar (Tokenomist daily)
- **Macro calendar feed (NEW per Option C)**: FOMC/CPI/halving/major listings, daily poll

**C10 minimal viable**:
- Top 1 symbol (BTCUSDT) funding harvest
- Simple long spot + short perp + quarterly rebalance
- $2,000 deploy on 主帳

**Engineering**: 100-130 hr (10 hr added for macro calendar + Earn)

---

### Sprint 2 — Alpha Tournament + Microstructure + On-Chain Setup (Week 4-7)

**Alpha Tournament analysis (rank all candidates)**:
- Unlock SHORT 24mo event study (Tokenomist trial data)
- Pairs trading rolling cointegration analysis (15m/1h)
- C13 options data analysis (IV/RV, skew, capacity)
- Funding short-only high-threshold analysis
- All produce: ranked candidate list with pre-registration drafts

**Microstructure feature library**:
- Orderbook depth ratio, trade flow imbalance, spread metrics
- Cross-exchange spread state
- Macro event proximity flags

**On-Chain signals layer setup (NEW per Option C)**:
- Glassnode free tier integration (exchange flows, supply metrics)
- Etherscan whale wallet monitoring
- DeFiLlama stablecoin TVL flow
- Signal aggregation engine

**Pre-registration locking**:
- Top-ranked candidates locked for Sprint 3 build
- Others remain in queue or removed if evidence weak

**Engineering**: 120-160 hr (40-60 hr added for on-chain layer)

---

### Sprint 3 — Build Top-1 Candidate (Week 8-11)

Based on Sprint 2 ranking (likely Unlock SHORT given SSRN evidence):

**Top-1 build (Unlock SHORT expected)**:
- Strategy module on 主帳
- Multi-condition triggers (T-3d + microstructure + funding state + macro state)
- Risk rules + auto-halt
- ~400 LOC Rust + 200 LOC Python

**Stage 0 shadow run 30d**:
- Strategy generates would-have signals
- Compare to real outcomes
- Validate pre-registration

**Macro overlay activation for active strategies**:
- C10 + Unlock SHORT receive macro context
- Position sizing adjustment based on FOMC/CPI proximity

**Engineering**: 130-160 hr (10-20 hr added for macro overlay integration)

**Gate**: Stage 0 shadow Sharpe > 1.0 → Sprint 4 promotion to Stage 0R

---

### Sprint 4 — Top-1 Live + Build Top-2 + C13 Stack Phase 1 (Week 12-15)

**Top-1 promotion (Unlock SHORT)**:
- Stage 0R replay preflight
- Stage 1 Demo micro-canary 7d
- Stage 2 Demo extended 14d
- If pass → live $500 initial on 主帳

**Build Top-2 candidate** (likely Pairs trading or Funding short-only):
- Similar build pattern
- Shadow run start

**C13 Bybit Options Stack Phase 1**:
- Options REST + WS client (Rust)
- Options data structures (Greeks, IV, OI, DTE)
- Defined-risk put spread logic preparation
- ~600 LOC Rust + 250 LOC Python

**Engineering**: 160-210 hr (peak engineering week)

---

### Sprint 5 — Top-2 Live + Top-3 Build + C13 Stack Phase 2 (Week 16-19)

**Top-2 promotion** to live $300-500

**Build Top-3 candidate**

**C13 Stack Phase 2**:
- Margin calculator (portfolio margin)
- Risk engine (Greek aggregation + stress test)
- Defined-risk put spread execution path
- Naked put logic (advanced mode, confluence-gated)
- ~600 LOC Rust + 200 LOC Python

**Unlock SHORT scaling**:
- If 15 events Sharpe > 1.0 → scale to $1,000

**Engineering**: 150-200 hr

---

### Sprint 6 — Top-4 Build + C13-VRP Strategy + Funding Short-Only (Week 20-23)

**Top-4 build**

**C13-VRP defined-risk strategy**:
- Regime-filtered put spread (default)
- Naked put confluence rules (advanced)
- Pre-registration locked
- ~400 LOC Rust + 150 LOC Python

**Funding short-only build (if not already Top-1-3)**

**Top-3 promotion to live $300-500 if Stage 0R passes**

**Engineering**: 140-180 hr

---

### Sprint 7 — Top-5 Build + Advisory Allocator + Live Promotions (Week 24-27)

**Build Top-5 (last candidate)**

**C13-VRP promotion** to live $500 (defined-risk default)

**Advisory Allocator**:
- Multi-component reward function (per Q3 framing)
- Monthly proposals
- Operator approves via Console
- All approved → Decision Lease + Guardian

**Engineering**: 110-150 hr

---

### Sprint 8 — Decay Detector + Discovery Pipeline + Moat Design (Week 28-31)

**Strategy Decay Detector** (event-count based):
- Per strategy rolling DSR by event/cycle/trade count
- Auto-reduce / retire rules
- Manual override

**Discovery Pipeline**:
- Operator + Cowork monthly review
- New hypothesis intake
- Max 3 concurrent paper-stage (now shadow-stage per governance)

**Reverse-Snipe Moat Design**:
- Copyable strategy criteria documented
- Copyability simulator specification
- Anti-snipe protocols specification
- Master Trader subaccount setup plan (build but not enable)

**On-chain signals integration into strategy triggers**

**Engineering**: 110-150 hr

---

### Sprint 9 — Auto-Allocator + Copy Trading Infrastructure (Y2 prep) (Week 32-35)

**Auto-Allocator activation**:
- After 6+ months advisory + >80% approval rate
- Hard limits enforced
- Operator emergency override

**Copy Trading Infrastructure (build, not enable)**:
- Copyability simulator (test fill rates)
- Master Trader ranking dashboard (offline)
- Bybit Copy Trading API integration code
- Anti-snipe monitoring system

**Engineering**: 100-140 hr

---

### Sprint 10 — Y1 Review + Copy Trading Decision (Week 36-39)

**Comprehensive Y1 review**:
- All strategies real performance vs pre-registration
- Calendar-weighted Y1 actual vs $300-600 estimate
- Strategy retire decisions

**Copy Trading Evidence Gate evaluation** (replaces Y2 calendar per audit fix):
```
Gate criteria (ALL must pass):
1. Alpha gate: ≥1 copyable strategy with 90+ days live, Sharpe > 1.0, max DD < 20%
2. Moat gate: copyability simulator fill rate > 95%, anti-snipe protocols deployed
3. Operator gate: capacity for additional management
4. Bybit-side gate: subaccount + Master Trader API integration tested

If 4/4 PASS:
  → Y1 末 OR Sprint 11 enable Master Trader subaccount
  → Deploy Unlock SHORT first (most copy-friendly)

If 3/4:
  → Defer 3 months, re-evaluate
  
If <3/4:
  → Continue self-trading only, re-evaluate Sprint 14
```

**Y2 Plan documentation**

**Engineering**: 60-90 hr

---

### Sprint Schedule Summary

| Sprint | Weeks | Focus | Hours |
|---|---|---|---|
| 1 | 0-3 | Governance + Sensors + C10 + Earn + Macro feed | 100-130 |
| 2 | 4-7 | Tournament + Microstructure + On-chain setup | 120-160 |
| 3 | 8-11 | Top-1 build + Macro overlay | 130-160 |
| 4 | 12-15 | Top-1 live + Top-2 build + Options Stack 1 | 160-210 |
| 5 | 16-19 | Top-2 live + Top-3 + Options Stack 2 | 150-200 |
| 6 | 20-23 | Top-4 + C13-VRP + Funding short | 140-180 |
| 7 | 24-27 | Top-5 + Advisory Allocator + Live promotions | 110-150 |
| 8 | 28-31 | Decay + Discovery + Moat Design + On-chain integration | 110-150 |
| 9 | 32-35 | Auto-Allocator + Copy Infra | 100-140 |
| 10 | 36-39 | Y1 Review + Copy Trading Evidence Gate | 60-90 |
| **Total** | **39 weeks** | | **1,180-1,570 hr** |

Per operator Q4: dev speed faster than estimate; realistic compression to 32-36 weeks.

---

## §8 Portfolio Stress Test (Correlation-Aware, Multi-Scenario)

**5 stress scenarios**:

```
Scenario 1: BTC -30% gradual over 7d
- C10: basis -3% × $2,000 = -$60
- C13 defined-risk: -8% × $1,500 = -$120 (capped vs -25% naked)
- Unlock SHORT: alt squeeze -25% × $1,500 = -$375
- Pairs: correlation breakdown -10% × $1,000 = -$100
- Funding short-only: forced exit -15% × $700 = -$105
- On-chain layer: provides advance warning, partial protection
- Macro overlay: position size reduced 24h pre, partial protection
- Bybit Earn: unaffected
- Stack with correlation 1.3x: -$988 = 9.9% portfolio DD ← within D2

Scenario 2: BTC -50% flash crash 24h
- C10 extreme basis -8% × $2,000 = -$160
- C13 defined-risk MAX loss capped: -30% × $1,500 = -$450 (vs unlimited naked)
- Unlock SHORT: alt -45% × $1,500 = -$675
- Pairs: extreme -15% × $1,000 = -$150
- Funding short-only: forced exit -20% × $700 = -$140
- Operational losses: -$200
- Stack with correlation 1.5x: -$2,663 = 26.6% portfolio DD ← within D2

Scenario 3: Exchange halt (Bybit) 48h
- All Bybit positions frozen
- Off-exchange $2,500 secure
- Bybit Earn frozen with rest
- Worst case Bybit insolvency: -$7,500 = 75% portfolio
- D2 hard breach, project ends
- Mitigation: off-exchange保 $2,500 floor

Scenario 4: Alt season pump (HYPE/SUI +200% week)
- Unlock SHORT squeeze: -45% × $1,500 = -$675
- Funding short-only flip: -20% × $700 = -$140
- C10/C13 stable
- Pairs may benefit (long alt leg)
- Macro overlay: would size down before entry
- On-chain layer: stablecoin mint surge signal pre-warned
- Stack: -$700 = 7% portfolio DD ← within D2

Scenario 5: Options market stress (IV spike +50%)
- C13 defined-risk capped: -10% × $1,500 = -$150 (vs unlimited naked margin call)
- Other strategies relatively unaffected
- Total: -1.5% ← well within D2

Defined-risk C13 specifically prevents Scenario 2 from breaching D2.
```

---

## §9 Kill Criteria (Updated)

| Event | Action |
|---|---|
| Sprint 1: V097/V098 catch-up fail | Block subsequent |
| Sprint 2: 0 candidates pass evidence threshold | Reset alpha selection |
| Sprint 3: Top-1 shadow Sharpe < 0.5 | Move to Top-2, top-1 retire |
| Sprint 4+: any strategy Stage 0R fail | Drop, redirect capital |
| Per strategy live: cum < kill threshold | Auto-retire per §6 rules |
| Portfolio cumulative loss > $2,500 | WARN, reduce live 50% |
| Portfolio cumulative loss > $3,000 (D2) | HARD STOP all trading |
| Bybit regulatory shutdown | Off-exchange $2,500 safe, deployed loss accept |
| Bybit Earn product withdrawal | Auto-redeem to active capital |
| Macro overlay false positives > 3/month | Recalibrate or disable layer |
| On-chain signals 0 actionable alpha after Sprint 6 | Retire layer, save engineering |
| Operator burnout 8 weeks 0 commits | Pause, re-evaluate |
| Sprint 10 review: 0 alpha sustained | Decision: reset or stop |

---

## §10 Copy Trading Evidence Gate (Final Form)

**Replaces v5.5 Y2 calendar with evidence-based activation**:

```
Pre-conditions to enable Master Trader subaccount:

Alpha gate (ALL):
✓ ≥1 strategy with 90+ consecutive days live trading
✓ That strategy's Sharpe ratio > 1.0
✓ That strategy's max drawdown < 20%
✓ Strategy is copyable (perp-only, snipe-resistant)

Moat gate (ALL):
✓ Copyability simulator developed and tested
✓ Anti-snipe protocols deployed and tested
✓ Master Trader API integration complete
✓ Ranking dashboard operational

Operator gate:
✓ Operator capacity for additional 5-10 hr/week management
✓ Y1 verified positive net P&L
✓ Operator psychologically ready for follower-facing pressure

Bybit-side gate:
✓ Subaccount setup (100 USDT minimum transferred)
✓ Master Trader application submitted
✓ Cadet tier qualified

When all gates pass → enable Master Trader
Earliest possible: Sprint 9 末 (Y1 W35)
Median expectation: Y2 Q1-Q2
Possible later: if any gate not satisfied
```

**Copy Trading 啟用後**:
- Deploy Unlock SHORT first (most snipe-resistant copyable strategy)
- Monitor for 30 days reverse-snipe signals
- Add Funding short-only as second copy strategy if base proves
- Pairs trading stays self-only (two-leg copy risk)
- C10 + C13 stays self-only (not copyable products)

---

## §11 Governance Compliance (NEW ADRs)

**ADR-0028 (proposed)**: Copy Trading Subaccount Evidence-Gated Activation
- Replaces calendar-based activation with evidence gates
- Specifies copyable strategy criteria
- Specifies moat construction requirements
- Operator final approval for Master Trader open

**ADR-0006 amendment**: 
- Bybit primary trading
- Binance market data approved
- Binance trading deferred Y2 review
- DEX/Hyperliquid NOT approved (preserve focused execution)

**ADR-0029 (proposed)**: Macro Overlay + On-Chain Signals Framework Expansion
- Macro calendar feed (FOMC/CPI/halving/listings) integrated into strategy triggers
- On-chain signals (free tier) layer for additional alpha
- Bybit Earn cash management for idle capital
- All within Bybit primary venue (D12 compliance)

All existing ADRs (-0011, -0024-lite, -0025 v3, -0026 v3, -0027) active unchanged.

---

## §12 Stage Gate Language (Reviewer §2 Fix)

**Replaces all "paper" language with governance-compliant terminology**:

```
Strategy lifecycle:

DRAFT
  ↓ (pre-registration locked)
PREREGISTERED
  ↓ (operator + Cowork hypothesis review)
SHADOW (counterfactual replay against historical data, NOT promotion evidence)
  ↓ (evidence quality check, NOT Sharpe gate)
STAGE_0R_REPLAY_PREFLIGHT (per AMD-2026-05-15-01)
  ↓ (per existing canary)
STAGE_1_DEMO_MICRO_CANARY (1 strategy × 1 symbol × 7d, REAL fills, Demo env)
  ↓
STAGE_2_DEMO_EXTENDED (14d)
  ↓
STAGE_3_DEMO_FULL (21d)
  ↓
STAGE_4_LIVE_PENDING (operator approval + 5-gate boundary)
  ↓
LIVE
```

**NO paper Sharpe gates**. Shadow is diagnostic only.
**Stage 0R replay** is technical replay against historical data, NOT live promotion.
**Stage 1 Demo** is the FIRST promotion gate per AMD-2026-05-15-01.

---

## §13 Subscription / Operator Time

```
Plan Mode (ADR-0027):
- Sprint 1-5: Build mode (~30 hr/week, $30/mo API cap)
- Sprint 6-8: Mixed (~20 hr/week)
- Sprint 9-10: Observe (~10-15 hr/week)
- Y2+: Low Activity (~5-10 hr/week)

Marginal project cost Y1: $350-550 (hosting + API + minor)
Subscription: sunk life expense
```

---

## §14 Y2+ Backlog

- **Master Trader Copy Trading activation** (per §10 evidence gates)
- **Intraday stat-arb live deployment** (after Sprint 9 evaluation)
- **Hyperliquid integration RE-REVIEW** (deferred per D12, may revisit Y3)
- **Multi-asset class** (forex/equities if operator interested)
- **Funding rate forecasting ML overlay** on C10
- **Tier 5 LLM-assisted hypothesis generation** (per ADR-0024-lite expansion)
- **Bybit Pro Trader tier** (if volume sufficient Y2+)
- **Paid on-chain data subscription** (if free tier insufficient evidence)

---

## §15 References

- v1 through v5.5: `srv/2026-05-20--*.md` (audit trail)
- AMD-01 through AMD-05: governance amendments
- ADR-0011, -0024-lite, -0025 v3, -0026 v3, -0027 active
- ADR-0028 (proposed): Copy Trading evidence-gated
- ADR-0029 (proposed): Framework expansion (Macro + On-chain + Earn)
- Round 1-14 audit conclusions (Round 14 §6 challenge outside-box exercise)
- Bybit Master Trader Tier System verified
- SSRN unlock event evidence verified
- Glassnode free tier, Bybit Earn product docs

---

**END v5.6 — Self-Trading Lab + Macro + On-Chain + Earn (Bybit Framework Final)**

**Sprint 1 dispatch ready upon operator final approval.**
