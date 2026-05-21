# 玄衡 · Arcane Equilibrium — Execution Plan v5.2

**Adaptive Strategy Lab — Survival Baseline + Dynamic Alpha + Meta Allocator**

**日期**：2026-05-20
**Status**：DRAFT — pending operator approval before PA dispatch
**Supersedes**: v5.0 (defensive), v5.1 (reviewer proposal)
**Foundation**：12 rounds reviewer audit + claude self-audit + operator Q3 framing (aggressive learning + long-lasting OR auto-adapting)

---

## §0 v5.2 核心思想（與所有 prior version 不同）

**操作員 2026-05-20 Q3 framing**：
> 「我希望重新關注與最大程度上盈利（aggressive）同時保證這個盈利是長效的或者是bot會自動動態學習動態調整」

11 輪 audit 收斂的關鍵真相：
- Round 11 Monte Carlo verified: **aggressive leverage 失敗**，median CAGR 1.7%，59.7% DD breach 機率
- Round 10 verified: **C4 cross-venue 失敗**，real net 接近 0
- Round 9 verified: **C13 conditional 是最強候選**，但需 regime filter
- Round 7+11: **C10 是 verified 結構性 alpha**，不會 decay 到 0

**v5.2 核心 reframe**：
- 「Aggressive」≠ 高槓桿賭一條 alpha
- 「Aggressive」= **資本動態流向當下最強 verified edge + 持續發現新 hypothesis + 自動退役 decay**
- 「長效」= Survival Layer C10 結構性 alpha + Adaptive Layer 永遠 chase 當下最強

---

## §1 Constraints (locked, final after 12 rounds)

| ID | Value |
|---|---|
| D1a | Trading: Bybit + Binance (max 2 exchanges) |
| D1b | Market data API: multi-exchange OK |
| D1c | Bot never touches bank account |
| D1d | API keys: NO withdrawal permission |
| D2 | $10k initial, max real loss $3,000 (30% ceiling), 本金 ≥ $7,000 |
| D2-modifier | Y1-2 100% reinvest; Y3-5 50% withdraw; Y6+ 70% withdraw |
| D3 | No outside consultant |
| D4 | Off-exchange Revolut $1,500 + Wise $1,000 |
| D5 | NOT US tax (Spain resident) |
| D6 | Timeline flexible 6-24+ months |
| D7 | NO content/subscription monetization |
| D8 | Subscriptions treated as sunk life expense (operator general dev tools) |
| D9 | Bybit Copy Trading subaccount OPTIONAL (not core) |
| D10 | Prop firm OPTIONAL (not core) |
| D11 | Execute v5.2 after operator approval |

---

## §2 Capital Structure — Barbell (Survival + Adaptive Alpha)

```
$10,000 total

Survival Layer ($5,500-6,000) — Long-lasting baseline
├─ C10 Bybit funding harvest static          $3,500
│  ├─ Top 3-5 basket quarterly rebalance
│  ├─ Verified 4.5-7% net APR
│  └─ Structural alpha (不會 decay 到 0)
├─ Bybit cash buffer                          $500
└─ Off-exchange (Revolut + Wise)              $2,500

Adaptive Alpha Layer ($3,500-4,000) — Dynamic capital流向
├─ C13-VRP regime-filtered options            initial $1,500
├─ Unlock SHORT (conditional verify)          initial $1,000-1,500 (Sprint 5)
└─ Discovery slot (future hypothesis)          remaining

NOTE: Alpha Layer weights are DYNAMIC.
      Meta Allocator (Sprint 6+) auto-rebalances based on 30/60d performance.
      Strong performers can take 50%+ of alpha budget.
      Weak performers auto-reduce to 0 weight.
```

**Worst-case DD check (v5.2)**:
- C10 max DD: ~5% × $3,500 = $175
- C13-VRP disciplined max DD: ~18% × $1,500 = $270
- Unlock SHORT max DD (if active): ~25% × $1,000 = $250
- Total stacked worst ~$695 = 7% of $10k = well within D2 30% ceiling ✓
- Off-exchange untouched = principal ≥ $7,500 floor (better than $7,000 D2)

---

## §3 Six-Sprint Engineering Plan (24 Weeks)

### Sprint 1 — Setup (Week 0-2)

**Operator tasks**:
- Off-exchange transfer: $2,500 to Revolut + Wise
- Bybit 主帳 + 副帳 subaccount setup
- Binance Futures account: confirm KYC + perp enabled
- All API keys: trade + read permissions only, NO withdrawal
- Subscription mode: Build ($30/mo API budget cap)

**Engineering tasks (E1)**:
- Linux DB V097/V098 migration drift catch-up (UTC 04-06 low-write window)
- API key vault setup + permission verification scripts

**KPI**:
- $2,500 off-exchange confirmed
- $7,500 in Bybit subaccounts + Binance ready
- Linux DB head = V098
- API keys validated (no withdraw)

**Engineering hours**: 10-15

---

### Sprint 2 — Survival Layer Live + Tier 0 Sensors (Week 3-6)

**Stream Survival: C10 funding harvest production**:
- Top 3 basket selection logic (highest funding × liquidity score)
- Long spot + short perp delta-neutral pair
- Quarterly rebalance scheduler
- Position monitoring + automatic re-entry on stop-out
- Real production Rust strategy module
- $3,500 deploy on Bybit 主帳

**Tier 0 Sensors build**:
- **Sensor A: BTC/ETH options chain recorder**
  - Bybit options API poll every 15 min
  - Capture: bid/ask/IV/OI/volume/delta/DTE per strike
  - Store in `market.options_chain_snapshots` (new table)
  - Purpose: 30-60d data for C13-VRP regime detection
- **Sensor B: Token unlock calendar feed**
  - Tokenomist free trial API integration (1y backward)
  - CryptoRank cross-reference
  - Filter for Bybit + Binance perp listings
  - Store in `market.token_unlock_events` (new table)
  - Purpose: Sprint 4 event study
- **Sensor C: Cross-exchange funding monitor**
  - Bybit + Binance funding rates per top 25 symbol
  - Real-time stream + 8h snapshot logger
  - Store in `market.funding_rates` (extend existing)
  - Purpose: scanner only, no active trade

**Schema additions (V101 minimal)**:
- `learning.hypotheses` (Tier 1 hypothesis registry)
- `learning.hypothesis_preregistration` (Tier 1 pre-reg per ADR-0026 v3)
- `market.options_chain_snapshots` (Tier 0 sensor)
- `market.token_unlock_events` (Tier 0 sensor)
- `trading.fills.track` column added (NEW: stream attribution)

**KPI**:
- C10 first 7d production: real fills, real funding receipts logged
- Options chain captured continuously (>95% uptime)
- Unlock events table populated with ≥30 historical events
- All schema applied + verified idempotent

**Engineering hours**: 60-80

---

### Sprint 3 — C13-VRP Build (Paper Trading) (Week 7-10)

**Stream Alpha: C13-VRP IV/RV Regime-Filtered Options**:

**Strategy spec**:
- **Entry rule**: Sell weekly BTC OTM puts ONLY when:
  - IV - RV gap > 10 vol points (premium rich)
  - 14d realized vol < 70% (regime stable)
  - BTC 7d return > -10% (no recent crash)
  - Strike: 8-12% OTM (not ATM per Round 11 verified catastrophic)
  - Liquidity check: bid-ask spread < 5%, OI > 100
- **Exit rule**:
  - Expire worthless → keep premium
  - Assignment → roll into spot BTC, sell covered call next week
  - Time stop: if 1 day before expiry and price within 5% strike, close at loss
- **Halt rule**:
  - BTC 7d return < -10% → halt new sales 7 days
  - 14d realized vol > 70% → halt new sales 14 days
  - Already 3 active short put positions → halt new sales

**Pre-registration** (immutable per ADR-0026 v3):
- code_hash, config_hash, trigger_rule, side_rule
- expected_alpha_bps_min/max
- expected_win_rate_min
- expected_max_drawdown_pct
- variance_estimator
- data_window_start_ts, data_window_end_ts
- immutable_trigger_hash

**Paper trading run**:
- 30 days simulated against live options chain data
- Track: hit rate, premium captured, assignment rate, DD
- No real capital deployed yet

**KPI**:
- C13-VRP code: pre-registered, locked, paper running
- 30d paper results logged
- Sharpe ratio, DSR computed honestly
- Gate: paper Sharpe > 0.8 → Sprint 4 micro live

**Engineering hours**: 40-60

---

### Sprint 4 — C13-VRP Micro Live + Unlock Event Study (Week 11-14)

**Promote C13-VRP if paper gate passed**:
- Initial allocation: $500-1,000 of Alpha Layer
- Position size: 1 contract (0.01 BTC) per week max
- Real fills tracked vs paper expectations
- Auto-halt if real drawdown > paper p95

**Unlock SHORT verification**:
- Fetch 24mo Tokenomist + CryptoRank unlock data
- Filter for Bybit/Binance tradable perps
- Event study T-7/T-2/T+0/T+3/T+7/T+14 returns
- Compute CAR (cumulative abnormal return) per event window
- HAC t-stat + Wilcoxon non-parametric robustness
- Verdict: direction (short confirmed) + tradable n_events_per_year

**Decision gate**:
- If unlock event study t-stat > 2 AND tradable n_events ≥ 30/year:
  → Pre-registration spec drafted, paper trading starts Sprint 5
- If fail: drop unlock candidate, $1,000-1,500 returned to cash buffer

**KPI**:
- C13-VRP first live fills + ROI vs paper benchmark
- Unlock event study report with cite-able statistics
- Pre-registration table populated

**Engineering hours**: 40-60

---

### Sprint 5 — Unlock SHORT Live + Strategy Decay Detector (Week 15-20)

**Unlock SHORT deployment (if Sprint 4 verified)**:
- Initial allocation: $500-1,000 of Alpha Layer
- Diversified across 5-10 events per month
- Position size: $50-150 per event (small)
- Entry: T-3 to T-1 before unlock
- Exit: T+3 OR T+7 (per event study optimal)
- Auto-halt: if 5 consecutive losers, pause 14d

**Strategy Decay Detector build (new module)**:
- Per strategy: rolling 30d/60d/90d Sharpe + DSR
- Decay flag triggers:
  - 30d DSR < 0.5 for 14 consecutive days → reduce weight ×0.5
  - 60d DSR < 0.5 for 30 days → reduce weight ×0.25
  - 90d DSR < 0.3 → auto-retire (weight = 0)
- Manual override: operator can preserve via Console
- All decay events logged to `governance.strategy_decay_events`

**KPI**:
- Unlock SHORT live with real fills
- Decay detector running on all 3 strategies (C10, C13-VRP, Unlock SHORT)
- 0 false-positive decay flags after 30d soak

**Engineering hours**: 30-50

---

### Sprint 6 — Meta Allocator + Discovery Pipeline (Week 21-24)

**Meta Allocator skeleton (Tier 4)**:
- Trigger: ≥2 strategies live with 30d+ track record
- Allocation algorithm: Thompson Sampling on multi-component reward
- **Reward function** (per operator Q3 framing):
  ```
  reward(strategy_i) = realized_return_i
                    - λ_dd × max_drawdown_30d_i
                    - λ_tail × p5_return_30d_i
                    - λ_turnover × turnover_cost_i
                    - λ_slippage × slippage_30d_i
                    - λ_decay × dsr_decay_signal_i
  ```
- Weights (λ) start operator-set, can tune later
- Monthly auto-rebalance (operator approval gate for first 6 months)
- Post-Month-6: full auto if no issues

**Discovery Pipeline build**:
- New hypothesis intake routes:
  - **Manual route**: operator drafts hypothesis spec → V101 hypotheses table DRAFT state
  - **Cowork-assisted route** (per ADR-0024-lite): operator triggers Cowork session, Claude reads recent market data + drafts candidate specs → DRAFT state
- All new hypothesis → backtest → pre-registration → paper → micro live → scale ladder
- Anti-bloat rule: max 3 concurrent paper-stage hypotheses (operator focus)

**Console GUI tab additions**:
- Strategy weights dashboard (current allocator state)
- Decay detector alerts panel
- Hypothesis pipeline funnel view

**KPI**:
- Allocator running, monthly rebalance approval cycle proven
- Discovery pipeline produces first new hypothesis (manual or Cowork)
- 3 active strategies with dynamic weights

**Engineering hours**: 60-80

---

### Sprint Schedule Summary

| Sprint | Weeks | Focus | Hours | Cumulative |
|---|---|---|---|---|
| 1 | 0-2 | Setup | 10-15 | 10-15 |
| 2 | 3-6 | Survival + Sensors | 60-80 | 70-95 |
| 3 | 7-10 | C13-VRP Paper | 40-60 | 110-155 |
| 4 | 11-14 | C13 Live + Unlock Study | 40-60 | 150-215 |
| 5 | 15-20 | Unlock Live + Decay Detector | 30-50 | 180-265 |
| 6 | 21-24 | Allocator + Discovery | 60-80 | 240-345 |

**Total v5.2 Phase 1**: 240-345 engineering hours over 24 weeks (~10-14 hr/week sustained)

---

## §4 Long-lasting + Auto-adapting Architecture（Operator Q3 explicit answer）

**Long-lasting baseline (Survival Layer)**:

C10 funding harvest is structural alpha：
- Bybit funding rate exists because long/short positioning imbalance
- This imbalance is permanent feature of perp markets (won't decay to 0)
- Verified 4.5-7% net APR sustainable
- **C10 is portfolio insurance, not main yield engine**
- Always 35-50% of capital, even when alpha sleeves underperform

**Auto-adapting alpha (Adaptive Layer + Meta Allocator)**:

Capital flows dynamically based on real performance:
- Sprint 2-3: C13-VRP only active (single alpha)
- Sprint 4: Unlock SHORT added (two alpha)
- Sprint 6+: Meta Allocator dynamic weight
- Year 2+: New hypothesis continuously ingested

Decay handling:
- Strategy decay detector watches every strategy daily
- DSR-based auto-reduce weight if performance declines
- Auto-retire at 90d sustained underperformance
- **No strategy is "married" to capital — it earns its weight**

**Discovery pipeline (永遠 chase 新 alpha)**:

- Operator + Cowork session weekly draft new candidates
- Sensor data (options chain, unlocks, funding) feeds idea generation
- All candidates → paper → micro live → scale ladder
- **System never stops learning**

---

## §5 Realistic APR Expectations

```
v5.2 portfolio APR distribution (after 6 sprint build):

All verified + adaptive working (60-70% probability):
  Survival 5% × 0.5 + Alpha 15% × 0.4 + cash 0% × 0.1 = ~8.5% APR
  → $850/yr on $10k

One alpha fails but allocator redirects (20-25% probability):
  Survival 5% × 0.5 + Alpha 10% × 0.4 + cash 0% × 0.1 = ~6.5% APR
  → $650/yr on $10k

All adaptive alpha fails (10-15% probability):
  Survival 5% × 0.5 + Alpha 0% × 0.4 + cash 0% × 0.1 = ~2.5% APR
  → $250/yr on $10k

Stretch (both alpha verified + good regime, 15-20% probability):
  Survival 5% × 0.5 + Alpha 25% × 0.4 + cash 0% × 0.1 = ~12.5% APR
  → $1,250/yr on $10k

Tail downside (5-10% probability):
  D2 ceiling protects: max -$3,000 loss
  Auto-retire stops bleeding
  Recovery from C10 baseline
```

**Median honest estimate**: 8-10% APR sustained, with 12-15% in good regime years.

---

## §6 10-Year Compound Trajectory

```
Assumptions:
- Year 1-2: 100% reinvest (build principal)
- Year 3-5: 50% reinvest / 50% withdraw
- Year 6+: 30% reinvest / 70% withdraw
- No additional capital injection (D2)
- Tax: 19% Spain savings tax on realized gains

| APR    | Y1     | Y5      | Y10 principal | Y10 cum cash | Y10 total |
|--------|--------|---------|---------------|--------------|-----------|
| 6%     | $10.6k | $13.4k  | $14.3k        | $1.9k        | $16.2k    |
| 8%     | $10.8k | $14.7k  | $16.5k        | $3.2k        | $19.7k    |
| 10%    | $11.0k | $16.1k  | $19.0k        | $4.7k        | $23.7k    |
| 12%    | $11.2k | $17.6k  | $21.7k        | $6.5k        | $28.2k    |
| 15%    | $11.5k | $20.1k  | $26.5k        | $9.5k        | $36.0k    |

Comparison to passive S&P500 8% historical:
  $10k → $21.6k by Y10 (operator does nothing)

v5.2 median (10% APR):
  $10k → $23.7k by Y10 (operator gains skills + optionality)

Differential: ~$2k over 10 years for ~250 hours of operator time
Hourly rate: ~$8/hr if only profit motivated
True value: skills + infrastructure + future scale option
```

**Operator must accept this is reality. Not DeepSeek scale.**

---

## §7 Strategy Pipeline (Tier 0 → Tier 4, my staging not reviewer's)

```
Tier 0: Data Sensors (Sprint 2 build, always running)
  - Options chain recorder
  - Unlock event feed
  - Funding rate aggregator
  - C10/C13/Unlock performance metrics
  
Tier 1: Hypothesis Registry (Sprint 2 schema, Sprint 6 GUI)
  - learning.hypotheses (state machine: DRAFT → REGISTERED → EXPERIMENTING → EVIDENCE_GATE → PROMOTED → REJECTED → EXPIRED)
  - learning.hypothesis_preregistration (immutable per ADR-0026 v3)
  
Tier 2: Validation (Sprint 3-5, manual + scripts)
  - Operator + Python scripts run backtest
  - Event study templates
  - DSR + HAC t-stat computation
  - No automated CPCV engine (defer to Year 2 if needed)
  
Tier 3: Micro Live Deployment (Sprint 4+, uses existing Decision Lease)
  - First deploy 0.5-2% of capital
  - Scale only from realized profit
  - Existing Decision Lease + Guardian + Stage 0/0R/1/2 canary
  
Tier 4: Meta Allocator (Sprint 6 build, automated Year 2)
  - Thompson Sampling on multi-component reward
  - Monthly rebalance (operator approval first 6 months)
  - Strategy decay auto-retire
```

---

## §8 Kill Criteria

| Event | Action |
|---|---|
| Phase 0 fails | Block all subsequent work |
| Sprint 2: C10 30d cum < -2% | Reduce to $1,500, expand cash buffer |
| Sprint 3: C13-VRP paper Sharpe < 0.5 after 30d | Cancel live promotion, retire candidate |
| Sprint 4: Unlock event study t-stat < 1.5 | Drop unlock candidate, $ to cash |
| Sprint 5: Unlock live cum < -5% in 30d | Auto-retire |
| Sprint 6: Allocator instability (frequent re-balance flip) | Manual override, weight tuning |
| Cumulative loss > $2,500 (D2 ceiling 80%) | WARN, reduce all live size 50% |
| Cumulative loss > $3,000 (D2 ceiling) | HARD STOP all trading |
| Bybit/Binance regulatory action | Off-exchange保 $2,500, deployed capital loss accept |
| Operator burnout (8 weeks 0 commits) | Pause sprint, re-evaluate |
| Month 6 review: cumulative net P&L < 0 | Decision point: reset OR continue Year 2 plan |

---

## §9 Subscription Cost Discipline (per ADR-0027 Plan Mode)

```
Sprint phases vs Plan Mode:
- Sprint 1-2: Build mode ($30/mo API budget)
- Sprint 3: Build mode (C13-VRP development)
- Sprint 4: Build mode (Unlock event study)
- Sprint 5: Mixed (Build for module, Observe for stable strategies)
- Sprint 6: Mixed
- Post-Sprint 6 (steady state): Observe mode ($10/mo API)
- Year 2+: Mostly Low Activity mode

Total expected API spend Year 1: ~$200-300
Subscription (Claude Max + GPT Plus) treated as sunk life expense
```

---

## §10 Open Items for Future Sprints (Year 2+)

Not in v5.2 scope but tracked:

- **Intraday statistical arbitrage** (Reviewer R11 proposed, deferred — needs Round 9 daily verified before intraday)
- **DEX integration** (Hyperliquid / Drift) — requires rescinding D1a partially
- **Bybit Copy Trading subaccount** — D9 optional, activate if Phase 1 successful + 90d positive
- **Prop firm evaluation** — D10 optional, attempt if 副帳 30d positive
- **Automated CPCV/DSR engine** (Tier 2 full auto) — currently manual
- **Cross-exchange arbitrage active deployment** — Round 10 verified fail, only as scanner

---

## §11 governance unchanged

All prior ADRs/AMDs preserved as audit trail:
- ADR-0001 Rust trading authority
- ADR-0006 originally Bybit-only — now updated: trading limited to Bybit + Binance per D1a, market data multi-exchange OK per D1b
- ADR-0011 V### migration mandatory Linux PG dry-run
- ADR-0018 funding_arb v2 retire (different from C4 cross-venue, both now closed)
- ADR-0020 Layer 2 manual+supervisor-only
- ADR-0024-lite Cowork subscription operator-assistant
- ADR-0025 v3 Track-based attribution (V101 minimal)
- ADR-0026 v3 Direct Exploit bypass CPCV (event-study + pre-registration)
- ADR-0027 AI Plan Mode time-based budgeting

AMDs 01-05 preserved as historical audit trail.

---

## §12 Audit Trail Summary (12 rounds)

```
Round 1-4: Architecture iterations (Track A/B/C variants) — abandoned
Round 5: First candidate evaluation pool (LCS, NLE, regime, funding, MM, etc.)
Round 6: Risk-constrained portfolio
Round 7: Data verification of top candidates → C10 verified
Round 8: Constraint clarification + Round 7 baseline
Round 9: Missed candidates evaluation (C11-C15) → most failed
Round 10: Multi-exchange + options + monetization verification → C4 verified fail
Round 11: Aggressive layering Monte Carlo → -33% DD median, 1.7% CAGR median
Round 12 (this round): v5.1 reviewer + Claude push-back synthesis → v5.2

Converged truths:
- $10k Bybit+Binance retail真實 APR ceiling 8-15% sustained
- C10 funding harvest is verified structural alpha
- C13-VRP regime-filtered is best alpha candidate
- Token unlock SHORT has public precedent, Bybit tradability TBD
- Aggressive leverage = catastrophic DD
- Adaptive learning + decay handling = real differentiator
```

---

## §13 Approval Required

Before PA dispatch Sprint 1:

**Operator confirms**:
- ✅ v5.2 barbell structure (Survival + Adaptive Alpha)
- ✅ 6-sprint 24-week timeline
- ✅ 240-345 engineering hours commitment
- ✅ 8-12% expected APR realistic ceiling
- ✅ Strategy Decay Detector + Meta Allocator (Sprint 5-6)
- ✅ Tier 0-4 staging (my version, not reviewer's full 5-tier)

**Sub-decisions still open**:
- Tokenomist free trial vs paid (Sprint 4)
- C13-VRP first allocation size ($500 vs $1000)
- Allocator manual approval gate duration (3 vs 6 months)

---

## §14 Concrete Week 0 Actions

**Operator personal actions** (Day 1-7):
1. Day 1-3: Revolut $1,500 + Wise $1,000 USD/EUR transfer
2. Day 4: Bybit 主帳 + 副帳 subaccount creation
3. Day 5: Binance Futures account confirm + API key (trade + read, NO withdraw)
4. Day 6: Tokenomist free trial application
5. Day 7: Verify all access + permissions

**Engineering actions** (Sprint 1, Week 1-2):
1. V097/V098 migration catch-up on Linux DB (UTC 04-06)
2. API key vault + permission verification scripts
3. Sprint 2 plan finalize (sensor schema design)
4. C10 production module spec finalize

---

## §15 References

- v1-v5.1 history: `srv/2026-05-20--*.md` (audit trail)
- AMD-01 through AMD-05: governance amendments
- 12 round audit reports (in conversation history)
- ADR-0001 through ADR-0027: governance decisions
- Round 7 verified data: Bybit funding API 365d
- Round 10 verified data: 14,022 cross-venue funding observations
- Round 11 verified Monte Carlo: aggressive layering DD distribution

---

**END v5.2 — Adaptive Strategy Lab**

**Awaits operator approval for Sprint 1 dispatch.**
