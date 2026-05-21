# 玄衡 · Arcane Equilibrium — Execution Plan v5.0

**Supersedes v4.4. Reflects 11 rounds of audit converged truth.**

**日期**：2026-05-20
**Status**：DRAFT — waiting operator final decision (Final-A / Final-B / Final-C per round 11)
**Foundation**：11 rounds reviewer audit + claude self-audit + real data verification
**Critical reframe**：cost break-even framing dropped (round 11)；no more aggressive layering fantasy

---

## §0 11 輪 audit converged truth（鎖死，不再 debate）

### What's verified

| Candidate | Verified data | Real net APR |
|---|---|---|
| **C10 Bybit funding harvest** | 365d Bybit API, top 3-5 basket, quarterly rebalance | **4.5-7%** (static) |
| **C13 Bybit options wheel disciplined** | Current chain + 730d BTC return distribution | **2.7-5.1%** with strict tail discipline (skip if BTC -10% in 7d) |
| **Token unlock SHORT direction** | SSRN: 46/52 Binance unlock events negative, mean -16.97% / 72h | Direction verified, Bybit tradability unverified |
| **Bybit + Binance funding spread (C4)** | 14,022 aligned observations | **near-zero net** after switch costs (-$100 to +$150/yr on $5k) — **deprecated** |

### What's killed (do not re-evaluate)

- LCS isolated cluster maker: insufficient data, no public precedent
- NLE Pre Market: fees worse + no edge verified
- C3 textbook revival (5 strategies): all negative mean return
- C12 spot-perp basis arb: thesis logic wrong (perp has no settlement)
- C14 triangular arb: spread < cost
- C15 dynamic funding momentum: turnover negative
- ATM options selling: -49% to -93% CAGR in backtest, catastrophic tail
- C10 1.5-2x leverage: borrow cost eats edge, net 2-6% APR worse than unlevered

### What's deferred (one remaining unknown)

- **Token unlock SHORT Bybit-filtered tradability** (Tokenomist data needed)

### Real portfolio expected (verified candidates only)

```
Realistic portfolio at $10k:
  C10 funding harvest (verified):           4-7%
  C13 disciplined options (verified):       3-5% 
  Cash/off-exchange (verified):              0-2%
  Total verified baseline:                   3-6% APR
  
If token unlock SHORT verifies in Round 12:
  + Add unlock layer (15% allocation):     +2-3%
  Total with unlock:                        5-10% APR

Verified 10-year compound (pure reinvest):
  4% APR:  $10k → $14.8k
  6% APR:  $10k → $17.9k
  10% APR: $10k → $25.9k
  15% APR: $10k → $40.5k  (stretch, requires execution discipline)
```

### What aggressive layering doesn't deliver

Round 11 Monte Carlo verified:
- Aggressive layered stack: median 10-year CAGR **1.7%**
- Probability of -30% DD breach: **59.7%** (D2 violation)
- Tail risk amplified, expected return NOT amplified

**Conclusion**: At $10k Bybit+Binance retail under D2 30% ceiling, **真實 ceiling = 8-15% APR with disciplined execution + one upside path verified**. Not 25-40%.

---

## §1 Three execution paths (operator chooses)

### Path Final-A: Round 12 Token Unlock Verification + then dispatch v5.0

**Pre-execution work** (1-2 weeks):
- Tokenomist free trial application
- 1-year backward unlock calendar fetch
- Filter for Bybit perp listings
- Event study T-7/T-2/T+0/T+3/T+7/T+14 returns
- Direction verdict (short vs long-recovery)

**If verified positive** (>10% net APR on $1.5k allocation):
- Continue to execution Phase 0
- Add unlock SHORT as third strategy layer
- Expected portfolio: 8-12% APR

**If verified negative**:
- Drop unlock candidate permanently
- Continue to execution Phase 0 with only C10 + C13
- Expected portfolio: 4-7% APR
- Operator decides Final-B or Final-C

### Path Final-B: Accept ceiling, dispatch v5.0 immediately

- Skip Round 12 (don't verify unlock)
- Accept 4-7% APR expectation
- Phase 0 starts now
- 10-year outcome target: $10k → $15-25k

### Path Final-C: Stop project

- Accept retail $10k Bybit+Binance constraint doesn't deliver
- $10k → S&P500 index passively: 8% historical → $21.6k over 10 years (0 operator hours)
- Codebase preserved as learning portfolio
- Subscription reduces to personal use only

---

## §2 v5.0 Capital Configuration (if executing Path A or B)

```
$10,000 total:

Bybit deploy: $5,500
├─ C10 funding harvest:                $3,000
├─ C13 options wheel disciplined:      $1,500
├─ Token unlock SHORT (if Final-A):    $1,000 (or roll into cash if Final-B)
└─ Bybit cash buffer:                  $0-1,000

Binance deploy: $1,000
└─ Cross-exchange C4 SCANNER ONLY      $0-1,000 (no active capital, just signal)

Off-exchange: $3,500
├─ Revolut EUR/USD:                    $2,000
└─ Wise multi-currency:                $1,500
```

**Worst-case DD check** (verified):
- C10 max DD: ~5% × $3k = $150
- C13 disciplined max DD: ~18% × $1.5k = $270
- Unlock SHORT max DD (if active): ~25% × $1k = $250
- Total worst ~$670 = 6.7% of $10k = well within D2 30% ceiling ✓
- Off-exchange untouched = principal $7,000 floor ✓

---

## §3 Phase Structure (Path A/B execution)

### Phase 0 — Setup (Week 0-1)

- Phase 0 V097/V098 migration drift reconcile on Linux DB
- Off-exchange cash transfer to Revolut + Wise
- Bybit + Binance subaccount setup, API keys NO withdrawal
- Subscription mode set to Build ($30/month API budget)

**KPI**: V098 confirmed, off-exchange $3.5k secured, accounts ready

### Phase A — Verification & First Trades (Month 1-3)

**Stream 1: C10 funding harvest** ($3,000):
- Static quarterly rebalance, top 3 basket
- Real production-grade implementation
- ~500 LOC Rust + Python orchestrator
- Target: real 4-7% net APR demonstrated

**Stream 2: C13 options wheel** ($1,500):
- Weekly 8-12% OTM puts on BTC
- Disciplined tail rules: skip if BTC -10% in 7d, skip if 14d RV >70%
- Paper trading first 30 days, then live
- Target: real 3-5% net APR with controlled DD

**Stream 3 (Final-A only): Token Unlock SHORT** ($1,000):
- After Round 12 verification
- Tokenomist event calendar feed
- Diversified small shorts across 5-10 events per month
- Target: real 15-25% APR on this sleeve (if alpha real)

**Background**: C4 cross-venue scanner (passive monitoring, no capital)

### Phase B — Refinement (Month 4-9)

- Real performance review monthly
- Strategy parameter tuning based on real fills
- Decision per Stream:
  - Stream 1 < 3% APR after 3 months → reduce or kill
  - Stream 2 net negative after 3 months → kill options
  - Stream 3 ROI < 5% APR → kill unlock SHORT
- Subscription mode shifts to Observe after Phase A stabilizes

### Phase C — Optional Monetization Add-ons (Month 6+)

**Only if Phase A/B demonstrating real positive APR**:
- Bybit Copy Trading subaccount (separate $1,000, aggressive strategy)
- Prop firm evaluation attempt (Breakout or HyroTrader, $100-300 fee)
- Both as upside optionality, not core path

### Yield discipline (per D2-modifier)

- Monthly profit sweep
- Year 1-2: 100% reinvest (build principal)
- Year 3-5: 50% reinvest / 50% withdraw to operator cash
- Year 6+: 30% reinvest / 70% withdraw

---

## §4 Honest expectations matrix

| Scenario | Year 1 P&L | Year 5 total value | Year 10 total value |
|---|---|---|---|
| **Verified only (C10+C13)** | $400-700 | $13-18k | $18-26k |
| **With Unlock SHORT verified** | $700-1,200 | $15-22k | $25-40k |
| **Aggressive layering attempted** | -$200-$1,500 | $5-25k (high variance) | $8-50k (high tail risk) |
| **Stop & index fund S&P500** | $800 | $14.7k | $21.6k |

**Most honest expectation**: Path A median outcome ≈ Path C index fund outcome. The bot project differential is:
- Learning value (operator gains quant skills)
- Optionality for future scale-up
- Time investment cost (operator hours)

---

## §5 Strategy Development Redesign — Operator's Open Question

Operator (2026-05-20) flagged: "我可能需要重新設計下策略開發思路"

11 rounds of audit identified systemic candidate pool framing issues:

1. **Directional/event/carry bias** in candidate selection
2. **Underweighted statistical arb / structural income** strategies
3. **LLM reviewer pool echo chamber** on certain frames
4. **Bybit-only inertia** from ADR-0006 (now rescinded)
5. **Cost break-even obsession** anchoring defensive posture

Potential redesign directions operator may consider:

- **Concentration on 1-2 alpha sources** rather than portfolio diversification
- **Continuous strategy refresh pipeline** (alpha decay tracking + sunset rules)
- **Manual + algo hybrid** (operator discretionary overlay on bot baseline)
- **Different venue stack** (DEX/Hyperliquid for retail-only edges, off-table currently)
- **Capital scaling roadmap** (if alpha verified, plan $25k → $50k → $100k path)
- **Open question for v5.1**: should we treat bot as "yield generator" or "alpha incubator"?

**v5.0 leaves these open**. Operator's strategy redesign thinking takes priority.

---

## §6 Engineering Workload (Path A/B)

| Phase | Tasks | LOC | Hours |
|---|---|---|---|
| Phase 0 | Migration + setup | ~100 SQL | 10-15 |
| Phase A C10 production | Rust strategy + orchestrator | ~500 Rust + 200 Py | 40-60 |
| Phase A C13 options | Options API + wheel state machine | ~400 Rust + 150 Py | 30-50 |
| Phase A Unlock SHORT (if Final-A) | Event calendar feed + execution | ~300 Py | 20-30 |
| Phase B ongoing | Monitoring + tuning | minimal | 5 hr/week |

**Phase A total**: ~1,250-1,550 LOC + 100-150 engineering hours
**Maintenance**: 5 hours/week steady state

---

## §7 Governance unchanged (rounds 1-10 outputs preserved)

- ADR-0001 / -0006 (rescinded for trading, retained for note) / -0011 / -0018 / -0020 / -0024-lite / -0025 v3 / -0026 v3 / -0027 active
- AMD-01 through -05 audit trail preserved
- TODO §-0 banner reflects v5.0
- 11 round audit reports archived

**v5.0 simplification**: removed Track A/B/C dual-track framework (was v4.x). Now 3 streams: C10 / C13 / Unlock (if verified). Simpler.

---

## §8 Kill Criteria (per Stream)

| Event | Action |
|---|---|
| Phase 0 fails | Block all subsequent work |
| Month 3: C10 < 3% APR | Reduce allocation or kill |
| Month 3: C13 net negative | Kill options stream |
| Month 3: Unlock SHORT < 5% APR | Kill stream 3 |
| Cumulative loss > $2,500 (D2 ceiling) | HARD STOP all trading |
| Bybit/Binance regulatory shutdown | Off-exchange保 $3.5k, deploy 接受 loss |
| Operator burnout (consecutive 4 weeks 0 activity) | Pause, re-evaluate |

---

## §9 No more LLM audits

11 rounds of audit have:
- Verified 4 candidates (C10, C13, C4 deprecated, token unlock direction)
- Killed 7+ candidates (LCS, NLE, C3, C12, C14, C15, aggressive layering)
- Run Monte Carlo with real data
- Reached convergent ceiling estimate

**Round 12 is conditional final** (only if Final-A path).

After Round 12 or immediate Final-B: PA → E1 dispatch begins.

Future audit only triggered by:
- Strategy ACTUAL live performance miss vs expectations
- Material new alpha source discovered (operator initiative)
- Bybit/Binance regulatory environment change

---

## §10 Open question for operator

Three immediate decisions before next step:

**Q1**: Path Final-A / B / C?

**Q2**: If Final-A, who does Tokenomist event-study work?
- Operator manually (1-2 days work)
- Engineering sprint (1 week, Python event-study script)

**Q3**: Strategy development redesign — what's on your mind?
- Conceptual reset (rethink alpha sources from scratch)
- Process change (how do we audit/test/deploy)
- Architecture change (move beyond Strategy trait pattern)
- Different venue ecosystem (DEX, options-heavy, etc.)

**v5.0 waits for operator clarification on Q1/Q2/Q3 before PA dispatch.**

---

## §11 References

- v4.4: `srv/2026-05-20--execution-plan-v4.4.md` (superseded)
- v4.3: `srv/2026-05-20--commercial-evidence-sprint-v4.3.md` (audit trail)
- v4-v4.2: `srv/2026-05-20--dual-track-architecture-*.md` (audit trail)
- Round 1-11 audit reports (in conversation history, to be archived)
- 27 ADR/spec/AMD docs (governance trail)

---

**END v5.0 — Awaits operator Q1/Q2/Q3 decisions**
