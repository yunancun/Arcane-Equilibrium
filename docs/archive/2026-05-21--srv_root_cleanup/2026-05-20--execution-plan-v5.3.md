# 玄衡 · Arcane Equilibrium — Execution Plan v5.3

**Adaptive Strategy Lab — Sensor-First, Alpha-First, Full Options Stack**

**日期**：2026-05-20
**Status**：DRAFT — operator-approved framing, pending final review
**Supersedes**: v5.2 (架構正確但工程低估 + paper gate 違 governance)
**Foundation**：12+1 rounds reviewer audit + reviewer 5 hard problems acceptance + operator Q1-Q4 final decisions

---

## §0 與 v5.2 的關鍵差異（reviewer audit 修正）

| 議題 | v5.2 (我前一版) | v5.3 修正 | 原因 |
|---|---|---|---|
| Phase 0 migration | 假設已 catch-up | **Sprint 1 明確 V097/V098 catch-up 才能 proceed** | Linux DB head 仍 V096，未做 |
| C13 options 工程 | Sprint 3 paper, 40-60 hr | **Sprint 5-9, 200-340 hr full stack** | Bybit options API/strategy/executor codebase 0 存在 |
| Paper trading gate | "Sharpe > 0.8 → live" | **Stage 0 shadow + Stage 0R replay + Stage 1 Demo micro-canary** | 違 AMD-2026-05-15-01 paper not promotion evidence |
| DD modeling | Isolated sleeve 線性相加 | **Correlation 上升 stress scenario 真實 model** | BTC crash 下 C10/C13/Unlock 同時惡化 |
| C10 priority | Sprint 2 production deploy | **Minimal viable 即可，不吃工程** | 4.5-7% baseline 不是 compound engine |
| Deploy 順序 | C10 → C13 → Unlock 平行 | **Unlock → C13 → Intraday**（per Claude push-back） | C13 options stack 不存在；Unlock 用既有 perp infra 工程小 |
| Allocator | Sprint 6 Meta Allocator auto | **Sprint 7+ advisory only**（per reviewer） | Allocator 直接動資金 governance 衝突 |

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
| D6 | Timeline flexible 28-40 weeks acceptable (operator dev speed faster than estimate) |
| D7 | NO content monetization |
| D8 | Subscriptions = sunk life expense (not project-attributed) |
| D9 | Bybit Copy Trading OPTIONAL |
| D10 | Prop firm OPTIONAL |
| D11 | Execute v5.3 |

---

## §2 Capital Structure — Survival Minimal + Alpha Aggressive

```
$10,000 total

Survival Layer ($5,000) — minimum viable baseline
├─ C10 Bybit funding harvest (minimal):       $2,500
│  └─ Top 1 symbol funding only, simple rebalance
│     (NOT top 3 basket optimization, NOT fancy execution)
└─ Off-exchange (Revolut + Wise):              $2,500

Adaptive Alpha Layer ($5,000) — primary compound engine
├─ Unlock SHORT (Sprint 3+ live):             initial $1,500
├─ C13-VRP Bybit options wheel (Sprint 6+):   initial $1,500
├─ Intraday Stat-Arb scanner (Year 2 live):   $0 (sensor only)
└─ Bybit cash buffer:                          $2,000 initial

Capital reallocation triggers:
- Strong alpha (DSR > 1.0 30d) → +50% allocation from buffer
- Weak alpha (DSR < 0.5 30d) → -50% allocation to buffer
- Decay alpha (DSR < 0.3 30d) → retire to 0
```

**Worst-case DD with correlation stress (BTC -30% scenario)**:
- C10 stress: spot/perp basis blowout, max -5% × $2,500 = -$125
- Unlock SHORT stress: alt squeeze coincident, max -25% × $1,500 = -$375
- C13 stress: assignment + IV spike, max -25% × $1,500 = -$375
- Correlation multiplier: ~1.4x (not isolated)
- Stressed total: ~-$1,225 = 12.25% of $10k
- Off-exchange untouched = principal保 ≥ $8,775 ✓
- Worst plausible (multi-stress): ~-$1,500-2,000 = 15-20% ✓ within D2 30%

---

## §3 9-Sprint Engineering Plan (28-40 weeks, full Bybit options stack)

### Sprint 1 — Phase 0 + ALL Sensors (Week 0-3)

**Critical precondition**: Sprint 1 MUST complete before any further work.

**Phase 0 catch-up**:
- ssh trade-core SELECT version FROM _sqlx_migrations (verify V096)
- Apply V097 (lg5_attribution_healthcheck_indexes) UTC 04-06 low-write window
- Apply V098 (governance_audit_log_halt_event_types) similar window
- Healthcheck pass after each
- V101 minimal: hypotheses + hypothesis_preregistration tables + trading.fills.track column

**Off-exchange setup**:
- $1,500 Revolut + $1,000 Wise EUR/USD
- API key vault for Bybit + Binance (no withdraw, trade + read only)

**C10 minimal**:
- Top 1 symbol selection (likely BTCUSDT)
- Simple long spot + short perp + quarterly rebalance
- No basket optimization, no advanced execution
- Goal: just be alive, prove fills work
- $2,500 deploy

**Tier 0 Sensors (ALL start)**:
- **Sensor A: Options chain recorder**
  - Bybit options API (REST + WS)
  - Poll BTC/ETH option chains every 15 min
  - Capture: bid/ask/IV/OI/volume/delta/DTE/strike
  - Store `market.options_chain_snapshots` (new table)
- **Sensor B: Unlock event feed**
  - Tokenomist free trial API (1y backward)
  - CryptoRank fallback
  - Filter Bybit + Binance tradable perps
  - Store `market.token_unlock_events` (new table)
- **Sensor C: Funding rate aggregator**
  - Bybit + Binance funding history per top 25 symbol
  - 8h snapshot + real-time stream
  - Extend `market.funding_rates`
- **Sensor D: Intraday kline recorder**
  - Bybit + Binance 15m/1h klines per top 20 symbol
  - Store `market.kline_15m` + `market.kline_1h`
  - Purpose: Year 2 stat-arb verification (no live trade now)

**Engineering**: 60-90 hr

**KPI**:
- Linux DB head = V098 confirmed
- $2,500 off-exchange confirmed
- C10 first fills logged
- 4 sensors continuous operation (>95% uptime)
- 30d+ of all sensor data accumulating

---

### Sprint 2 — Alpha Verification Workbench (Week 4-7)

**No live trading deployment this sprint** — pure verification analysis.

**Unlock SHORT event study (priority 1)**:
- Fetch 24mo Tokenomist + CryptoRank unlock data
- Filter for Bybit + Binance perp listings (drop TradFi-only tokens)
- T-7/T-3/T-2/T+0/T+1/T+3/T+7/T+14 event window analysis
- CAR (cumulative abnormal return) per window
- HAC t-statistic with Newey-West variance estimator
- Wilcoxon non-parametric robustness test
- Per-window expected return distribution + sample size

**Pre-registration spec (per ADR-0026 v3)**:
- code_hash (git SHA of Unlock SHORT strategy code, frozen before backtest)
- config_hash (hash of risk_config + params)
- trigger_rule (immutable JSONB)
- side_rule: 'short_only' (per SSRN evidence)
- expected_alpha_bps_min/max from event study
- expected_n_events_min: 30 events/year (Bybit-filtered)
- expected_sharpe_min: 1.0
- expected_max_drawdown_pct: 25%
- variance_estimator: 'newey_west'
- dedup_rule: 'per_event'
- immutable_trigger_hash

**C13 options data analysis (parallel)**:
- 30d options chain data review
- IV/RV gap distribution per moneyness/DTE
- Premium per strike % OTM
- Liquidity (spread, OI) by strike
- Engineering scope estimate (200-340 hr)

**Intraday stat-arb scanner analysis**:
- Rolling cointegration on 15m/1h Bybit-Binance perp pairs
- Spread distribution per pair (BTC-ETH, ETH-SOL, etc.)
- Edge estimate after fees (assume maker round-trip 8 bps)
- Year 2 deploy decision pending more data

**Engineering**: 70-100 hr (mostly Python/SQL analysis, no production strategy code)

**KPI**:
- Unlock event study complete + pre-registration locked
- t-stat ≥ 2.0 + n_events ≥ 30 → proceed Sprint 3
- C13 engineering scope locked (operator Option A = full stack)
- Intraday year-2-eligibility verdict

---

### Sprint 3 — Unlock SHORT Build + Stage 0 Shadow (Week 8-11)

**Unlock SHORT strategy module**:
- Event-driven scheduler (poll unlock calendar daily)
- Position planner: T-3 entry, T+3 or T+7 exit (per event study optimal)
- Sizing: $50-150 per event, diversified across 5-10 events/month
- Risk rules:
  - Max 5 concurrent positions
  - Auto-halt 5 consecutive losers → pause 14d
  - Squeeze detection (price +15% from entry) → exit immediately
- Pre-registration enforcement (per ADR-0026)
- ~300 LOC Rust + ~150 LOC Python orchestration

**Stage 0 shadow run (30 days)**:
- Strategy generates "would-have" signals
- Compare to actual price action
- No real fills, no capital deployed
- Track: hit rate, expected vs realized return per event
- Goal: validate strategy behavior matches pre-registration

**Engineering**: 100-130 hr

**KPI**:
- Unlock SHORT strategy code complete + pre-registered
- 30d shadow data showing signals + would-be outcomes
- Gate: shadow Sharpe > 1.0 + replay match ≥ 80% → Stage 0R
- Gate: pre-registration thresholds met → Sprint 4 micro-live

---

### Sprint 4 — Unlock SHORT Micro Live + C13 Stack Phase 1 (Week 12-15)

**Unlock SHORT promotion to live**:
- Stage 0R replay preflight (per AMD-2026-05-15-01)
- Stage 1 Demo micro-canary 7d
- Stage 2 Demo extended 14d
- If acceptance → live $500 initial allocation
- Scale ladder: 30d positive → $1,000; 60d positive → $1,500

**C13 Bybit Options Stack — Phase 1 (HTTP + WS + Data Structures)**:
- Bybit options REST API client (Rust)
  - GET /v5/market/instruments-info?category=option
  - GET /v5/market/tickers?category=option
  - GET /v5/market/orderbook?category=option
  - POST /v5/order/create with category=option
- WS subscription for option tickers + orderbook
- Options data structures:
  - Greeks (delta, gamma, theta, vega, IV)
  - Open interest, volume
  - Time to expiration
  - Strike, moneyness calc
  - Bid/ask spread metrics
- ~600 LOC Rust + 200 LOC Python orchestration

**Engineering**: 130-170 hr

**KPI**:
- Unlock SHORT first live fills + cum P&L tracked
- Bybit options API integrated, data flowing in real-time
- Options data structures complete + unit tests

---

### Sprint 5 — C13 Stack Phase 2 (Margin + Risk + Execution) (Week 16-19)

**C13 Bybit Options Stack — Phase 2**:
- Margin calculator for options positions (Bybit UTA portfolio margin)
- Risk engine:
  - Per-position max loss
  - Greek aggregation (net delta, gamma, vega)
  - Stress test (BTC ±30%) per portfolio
- Execution path:
  - Order placement with all option-specific params
  - Fill confirmation handling
  - Assignment lifecycle (auto-convert to spot if assigned)
  - Covered call rollover
- ~500 LOC Rust + 150 LOC Python

**Unlock SHORT scaling**:
- If 30 events live tracked + Sharpe > 1.0 → scale to $1,000
- Decay detector starts (event-count based, not calendar):
  - ≥ 30 events: compute DSR
  - DSR < 0.5 → reduce weight ×0.5
  - DSR < 0.3 → auto-retire

**Engineering**: 120-160 hr

**KPI**:
- Options margin/risk/execution stack complete
- Unit + integration tests pass
- Unlock SHORT scale operational

---

### Sprint 6 — C13-VRP Strategy + Paper Trading (Week 20-23)

**C13-VRP Regime-Filtered Strategy**:
- Entry rule:
  - IV - RV gap > 10 vol points (premium rich)
  - 14d realized vol < 70% (regime stable)
  - BTC 7d return > -10% (no recent crash)
  - Strike: 8-12% OTM weekly puts
  - Liquidity: spread < 5%, OI > 100
  - Skew filter: skew not extreme
- Exit rule:
  - Expire worthless → keep premium
  - Assignment → spot BTC, sell covered call
  - Time stop: 1d before expiry, close if at-money
- Halt rule:
  - BTC 7d < -10% → halt 7d
  - 14d RV > 70% → halt 14d
  - 3+ active short puts → halt new

**Pre-registration locked**:
- All thresholds frozen before paper
- code_hash from final Rust commit
- Variance estimator: 'realized_variance' (Andersen et al 2003)

**Stage 0 shadow + paper trading 30d**:
- Strategy generates signals on real chain data
- Track which signals fire and what would happen
- Realistic fee/slippage model applied
- Goal: 12 weekly cycles minimum (~3 months data)

**Engineering**: 90-130 hr

**KPI**:
- C13-VRP strategy code complete + pre-registered
- 30d shadow Sharpe + DSR computed
- Gate: shadow Sharpe > 0.8 + DSR > 0.7 + n_cycles ≥ 12 → Sprint 7 micro-live

---

### Sprint 7 — C13-VRP Live + Advisory Allocator (Week 24-27)

**C13-VRP promotion**:
- Stage 0R replay preflight (event-study CAR + replay match)
- Stage 1 Demo micro-canary 7d
- Stage 2 Demo extended 14d
- If acceptance → live $500 initial allocation
- Scale ladder: 12 cycles positive → $1,000; 24 cycles → $1,500

**Advisory Meta Allocator (Sprint 7+)**:
- NOT auto-allocation (per reviewer correct)
- Generates proposals only:
  - "Increase Unlock SHORT to $X (reason: DSR improvement)"
  - "Reduce C13-VRP to $Y (reason: regime shift)"
  - "Pause Intraday scanner (reason: cointegration breakdown)"
- Operator approves via Console UI
- All approved actions go through Decision Lease + Guardian + Stage gate
- Multi-component reward (per operator Q3 framing):
  ```
  reward(strategy_i) = realized_return_i
                    - λ_dd × max_drawdown_30d_i
                    - λ_tail × p5_return_30d_i
                    - λ_turnover × turnover_cost_i
                    - λ_slippage × slippage_30d_i
                    - λ_decay × dsr_decay_signal_i
  ```
- λ weights operator-tunable

**Engineering**: 80-120 hr

**KPI**:
- C13-VRP first live fills
- Allocator generating monthly proposals
- 2 strategies live (Unlock + C13) + C10 baseline

---

### Sprint 8 — Decay Auto-Retire + Discovery Pipeline (Week 28-31)

**Strategy Decay Auto-Retire**:
- Per strategy: rolling event-count based DSR (not calendar)
  - C13-VRP: track per-cycle (weekly options)
  - Unlock SHORT: track per-event
  - C10: track per-quarter
- Decay flags:
  - DSR < 0.5 for 14d → operator notification + suggest reduce weight
  - DSR < 0.3 for 30d → auto-reduce weight ×0.25 (Guardian check)
  - DSR < 0.1 for 60d → auto-retire (set weight = 0)
- All decay events to `governance.strategy_decay_events`

**Discovery Pipeline (Tier 1 hypothesis management)**:
- Operator + Cowork session monthly:
  - Review sensor data (options chain trends, unlock patterns, intraday scans)
  - Draft new hypothesis specs (DRAFT state in V101)
  - Manual or Cowork-assisted (per ADR-0024-lite)
- Pre-registration → Stage 0 shadow → ... ladder per existing canary
- Max 3 concurrent paper-stage hypotheses (anti-bloat)

**Console GUI additions**:
- Strategy weights dashboard
- Decay alerts panel
- Hypothesis pipeline funnel

**Engineering**: 100-140 hr

**KPI**:
- 3 live strategies + decay detector running
- First new hypothesis from discovery pipeline (operator + Cowork)
- Console showing live + paper + draft strategies

---

### Sprint 9 — Tier 4 Auto-Allocator + Intraday Year 2 Decision (Week 32-35)

**Auto-Allocator Activation**:
- After 6 months of advisory mode + operator approving 80%+ proposals
- Switch to auto-execute with hard limits:
  - Max single-strategy weight 50% of Alpha Layer
  - Max weight change per rebalance ±20%
  - Operator emergency override switch
- Monthly rebalance cadence

**Intraday Stat-Arb Year 2 Decision**:
- After 8 months of sensor data (Sprint 1 start + 8 months)
- Evaluate: real cointegration stability + edge per fee
- If verified positive: build strategy module Year 2 Q1
- If still marginal: keep sensor running, defer further

**Engineering**: 60-100 hr

**KPI**:
- Auto-allocator running in auto mode
- Intraday decision documented (Y2 or defer)
- v5.3 Phase 1 (Sprint 1-9) complete

---

## §4 Sprint Schedule Summary

| Sprint | Weeks | Focus | Engineering hr |
|---|---|---|---|
| 1 | 0-3 | Phase 0 + 4 sensors + C10 minimal | 60-90 |
| 2 | 4-7 | Alpha verification workbench (no live) | 70-100 |
| 3 | 8-11 | Unlock SHORT build + Stage 0 shadow | 100-130 |
| 4 | 12-15 | Unlock live + C13 options stack Phase 1 | 130-170 |
| 5 | 16-19 | C13 stack Phase 2 + Unlock scaling | 120-160 |
| 6 | 20-23 | C13-VRP strategy + paper trading | 90-130 |
| 7 | 24-27 | C13-VRP live + Advisory Allocator | 80-120 |
| 8 | 28-31 | Decay Auto-Retire + Discovery Pipeline | 100-140 |
| 9 | 32-35 | Tier 4 Auto-Allocator + Intraday Y2 | 60-100 |
| **Total** | **35 weeks** | | **810-1,140 hr** |

**Per operator Q4 framing**: operator dev speed faster than estimate (except hard multi-day data verification). Realistic timeline 28-35 weeks if operator solo + part-time; could compress to 20-28 weeks if focused.

---

## §5 Realistic APR Distribution (v5.3)

```
After 9 sprints (~35 weeks), 3 strategies live:

Scenario A (all alpha verified + good regime, 25-30% probability):
  Survival C10 5% × 25% = 1.25%
  Unlock SHORT 25% × 30% = 7.5%
  C13-VRP 15% × 30% = 4.5%
  Cash 0% × 15% = 0%
  Total: ~13.25% APR = $1,325/yr on $10k
  
Scenario B (one alpha fails, allocator rebalances, 35-40% probability):
  Survival 5% × 35% = 1.75%
  Strong alpha 15% × 40% = 6%
  Weak alpha 2% × 10% = 0.2%
  Cash 0% × 15% = 0%
  Total: ~8% APR = $800/yr
  
Scenario C (alpha decay handled, mid regime, 25-30% probability):
  Survival + 1 weak alpha: ~5-6% APR = $500-600/yr

Scenario D (catastrophic regime, 5-10% probability):
  All alpha auto-retire → C10 baseline only
  ~2-4% APR = $200-400/yr
  D2 protection prevents major loss

Honest median: 8-12% APR sustained
```

---

## §6 10-Year Compound Trajectory (per D2-modifier)

```
Assumptions:
- Y1-2: 100% reinvest (build principal)
- Y3-5: 50% reinvest / 50% withdraw
- Y6+: 30% reinvest / 70% withdraw
- 19% Spain savings tax on realized gains

At 10% APR sustained (median):
  Y1: $11.0k
  Y3: $13.3k (+ $200 cum cash)
  Y5: $15.8k (+ $1.5k cum cash)
  Y10: $23.1k principal + $5.8k cum cash = $28.9k total

At 12% APR sustained:
  Y10: $27.5k principal + $8.0k cum cash = $35.5k total

At 8% APR (conservative):
  Y10: $19.4k principal + $3.6k cum cash = $23.0k total

Comparison passive S&P500 8%:
  Y10: $21.6k (operator does nothing)

v5.3 median outcome ~$28-35k differential ~$5-15k over 10y
+ skills + infrastructure + scaling optionality
```

---

## §7 Stress Test (Correlation-Aware, Reviewer Critique Addressed)

**BTC -30% crash scenario** (correlation rises across alpha sources):

```
Pre-stress portfolio: $10k
- C10 $2,500 spot+perp delta-neutral (low individual DD)
- Unlock SHORT $1,500 (high alt-pump squeeze risk)
- C13-VRP $1,500 (short put assignment risk)
- Cash buffer $2,000
- Off-exchange $2,500

During -30% BTC crash, correlations rise:
- C10 stress: basis -3% × $2,500 = -$75
- Unlock SHORT: alt squeeze coincident -25% × $1,500 = -$375
- C13-VRP: BTC put assignment underwater -25% × $1,500 = -$375
- Correlation amplifier: 1.4x (sleeves not independent)

Stressed total loss (active sleeves): ~-$1,225
Plus operational losses (delayed fills, missed exits): ~-$300
Total stressed: ~-$1,525 = 15.25% of $10k

Post-stress:
- D2 ceiling (30%) not breached ✓
- Off-exchange保 $2,500 ✓
- Surviving capital $8,475 + off-exchange = $10,975 base for recovery
- Decay detector auto-retires losers
- C10 + remaining alpha continue Y2 with reduced positions
```

**Recovery time from -15% DD**:
- At verified C10 5% APR: ~3 years
- At v5.3 median 10% APR: ~1.5 years
- Acceptable given D2 protection

---

## §8 Pipeline Architecture (Tier 0-4 per reviewer 5-tier, staged)

```
Tier 0: Sensors (Sprint 1, ALWAYS RUNNING)
  - Options chain recorder
  - Unlock event feed
  - Funding rate aggregator
  - Intraday kline recorder
  
Tier 1: Hypothesis Registry (Sprint 1 schema, Sprint 8 full pipeline)
  - learning.hypotheses (state machine)
  - learning.hypothesis_preregistration (immutable per ADR-0026 v3)
  
Tier 2: Validation (Sprint 2+, manual + scripts)
  - Operator + Python event-study scripts
  - HAC variance + Wilcoxon
  - Manual pre-registration approval
  - NO automated CPCV engine (defer)
  
Tier 3: Deployment (Sprint 3+, existing Decision Lease + Stage canary)
  - Stage 0 shadow → 0R replay → 1 Demo → 2 ext → live
  - 0.5-2% initial micro live size
  - Scale ladder from realized profit
  
Tier 4: Allocator (Sprint 7 advisory, Sprint 9 auto)
  - Multi-component reward
  - Monthly rebalance proposals
  - Operator approval gate first 6 months
  - Auto execute after proven cycle
```

---

## §9 Kill Criteria

| Event | Action |
|---|---|
| Sprint 1: V097/V098 catch-up fails | Block all subsequent work |
| Sprint 1: C10 first fills error | Pause, fix execution path |
| Sprint 2: Unlock event study t-stat < 1.5 | Drop Unlock from Sprint 3 |
| Sprint 3: Unlock shadow Sharpe < 0.5 30d | Drop Unlock, redirect $1,500 to cash |
| Sprint 4: C13 stack Phase 1 blockers | Operator decides defer C13 or push timeline |
| Sprint 6: C13-VRP paper Sharpe < 0.5 | Drop C13, redirect to Unlock scaling |
| Sprint 5: Unlock live cum -10% in 30 events | Auto-retire Unlock |
| Sprint 7+: C13 live cum -15% in 12 cycles | Auto-retire C13 |
| Cumulative loss > $2,500 | WARN, reduce all live size 50% |
| Cumulative loss > $3,000 (D2 ceiling) | HARD STOP all trading |
| Bybit/Binance regulatory shutdown | Off-exchange $2,500 secure, deployed capital loss |
| Operator burnout (8 weeks 0 commits) | Pause sprint, re-evaluate |
| Month 9 review: 0 alpha verified | Decision: reset OR continue baseline only |

---

## §10 Governance Compliance

All Stage transitions per AMD-2026-05-15-01 (Stage 1 = Demo-only, no paper promotion):

```
DRAFT → REGISTERED (pre-registration locked)
       → SHADOW (Tier 2 verification)
       → STAGE_0R_REPLAY_PREFLIGHT (existing infrastructure)
       → STAGE_1_DEMO_MICRO_CANARY (1 strategy × 1 symbol × 7d)
       → STAGE_2_DEMO_EXTENDED (14d)
       → STAGE_3_DEMO_FULL (21d)
       → STAGE_4_LIVE_PENDING (operator + 5-gate)
```

v5.3 doesn't bypass any existing Stage gates. Adds pre-registration + event-study + replay-match as ADDITIONAL gates before Stage 0R (per ADR-0026 v3).

---

## §11 Subscription / Operator Time Budget

```
Plan Mode per ADR-0027:
- Sprint 1-4: Build mode (~30 hr/week, $30/mo API cap)
- Sprint 5-7: Build/Observe mix (~20 hr/week)
- Sprint 8-9: Observe stabilizing (~10-15 hr/week)
- Year 2+: Low Activity (~5 hr/week steady state)

Subscription: treat as sunk life expense (per D8 framing post-Round 11)
Bot project marginal cost: ~$300-500/year (hosting + API + minor)
```

---

## §12 Open Items (Year 2+ backlog)

- **Intraday Stat-Arb live deployment** (after Sprint 9 evaluation)
- **Multi-asset class** (forex, equities) — operator interest TBD
- **Bybit Copy Trading Master subaccount** (D9 optional)
- **Prop firm evaluation** (D10 optional)
- **Tier 2 full auto CPCV/DSR engine** (currently manual)
- **Hyperliquid / DEX integration** (D1a expansion if needed)
- **Bybit Earn cash management** (passive yield on idle capital)
- **Funding rate forecasting ML** (overlay on C10)

---

## §13 References

- v1 through v5.2: `srv/2026-05-20--*.md` (audit trail)
- AMD-01 through AMD-05: governance amendments
- ADR-0011, -0024-lite, -0025 v3, -0026 v3, -0027: active governance
- Round 7 verified: Bybit funding API 365d
- Round 10 verified: 14,022 cross-venue funding observations (C4 fail)
- Round 11 verified: aggressive layering Monte Carlo (-33% median DD)
- Round 12 verified: Bybit options stack 0 existing, migration drift V096

---

**END v5.3 — Adaptive Strategy Lab with Full Bybit Options Stack**

**Sprint 1 dispatch pending operator final approval (after out-of-box review).**
