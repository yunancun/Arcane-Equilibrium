# 玄衡 · Arcane Equilibrium — Execution Plan v5.7 (Dispatch-Safe Patch)

**Self-Trading Lab + Macro/On-Chain Counterfactual + Earn Cash + Dispatch-Safe Engineering**

**日期**：2026-05-20
**Status**：DISPATCH READY — accepts all reviewer §1-6 corrections from round 15 audit
**Supersedes**: v5.6 (engineering precision drift on 6 verified issues)
**Foundation**：15 rounds reviewer audit converged + reviewer 6/6 technical corrections verified

> **REFERENCE / HISTORICAL DISPATCH PACKET**
>
> 本文件保留 v5.7 设计和审计 lineage，不是当前 active queue。M1-M13 / v5.8
> active-IMPL 已按 v5.9 thesis-shift 冻结（M7 例外），当前 mainline、gate、
> owner 和 runtime evidence 以根目录 `TODO.md`、ADR/AMD 和最新 PM/role reports 为准。

---

## §0 v5.6 → v5.7 changes (engineering precision only, thesis unchanged)

Reviewer round 15 verified 6 hard issues. v5.7 fixes all 6:

| # | v5.6 Issue | v5.7 Fix |
|---|---|---|
| 1 | "V101 minimal" reuses already-reserved V101 (Track schema, 12 tables) | **Migration number reconciled: schema-minimal goes V103/V104; PA dispatch confirms final numbers** |
| 2 | Earn APR hardcoded 4-8% (false: tiered 8-11% first $200 + 3% rest = $1k effective ~4.4%) | **Dynamic API APR tracking; recompute portfolio yield with actual tiered rates** |
| 3 | market.liquidations writer claimed "NEW" (false: already running in `rust/openclaw_engine/src/database/market_writer.rs`) | **Healthcheck/extend existing writer, not new build** |
| 4 | Auto-Allocator Sprint 9 activation but requires 6mo advisory (Sprint 7→9 = 8 weeks) | **Sprint 9 advisory only; Auto activation defer to Y2** |
| 5 | Macro/on-chain counted +2-3% APR uplift (unverified features) | **Counterfactual logging only Y1; not counted as alpha; APR uplift requires Y2 verification** |
| 6 | Earn deposits no governance policy (asset write operation) | **Earn movement requires Guardian-checked policy; manual stake initially** |

**Thesis unchanged**: Self-Trading primary, Copy Trading evidence-gated, Bybit framework, 5 strategies portfolio.

---

## §1 Honest Y1 Income Recompute (per Reviewer §2)

**v5.6 estimates were overoptimistic**. v5.7 honest version:

```
Y1 calendar-weighted, NO macro/on-chain alpha counted (counterfactual only):

C10 funding harvest:
  - Live W3, 36/52 weeks = 0.69x
  - 5% × $2,000 × 0.69 = $69

Unlock SHORT:
  - Live ~W14, 25/52 weeks = 0.48x
  - 18% × $1,500 × 0.48 = $130

Pairs trading:
  - Live ~W22, 17/52 weeks = 0.33x
  - 12% × $1,000 × 0.33 = $40

C13 options VRP (defined-risk):
  - Live ~W28, 11/52 weeks = 0.21x
  - 10% × $1,500 × 0.21 = $32

Funding short-only:
  - Live ~W26, 13/52 weeks = 0.25x
  - 25% × $700 × 0.25 = $44

Bybit Earn cash management (tiered APR realistic):
  - Active from W3, 36/52
  - First $200 @ ~10% = $14 (annualized $20 × 0.69 = $14)
  - Remaining $600 @ ~3% = $12 ($18 × 0.69 = $12)
  - Subtotal: $26 (vs v5.6 wrong $33)

Off-exchange savings (Revolut + Wise interest):
  - Active from Day 1, full year
  - 3-4% × $2,500 ≈ $80-100

Macro overlay: $0 counted (counterfactual logging only)
On-chain signals: $0 counted (counterfactual logging only)

Y1 Total Expected (median): ~$421 ≈ 4.2% Y1 APR
Y1 Range: $300-550 honest

Reviewer's $429-528 estimate is consistent with this. v5.6's $547 was overstated.
```

## §2 Y2 Mature Run-Rate (Honest)

```
Y2 expected (full-year deployment, no overlay alpha counted yet):

C10: 5% × $2,000 = $100
Unlock SHORT: 18% × $1,500 = $270
Pairs trading: 12% × $1,000 = $120
C13 defined-risk: 10% × $1,500 = $150
Funding short-only: 25% × $700 = $175
Bybit Earn ($800 effective ~4.4% weighted): $35
Off-exchange savings: $80-100

Y2 Total (no overlay): ~$935 ≈ 9.4% APR

If macro/on-chain overlays verified positive in Y1:
  + Macro overlay verified +1-2% × $5,400 = +$54-108
  + On-chain signals verified +1% × $5,400 = +$54
  Y2 with overlay verified: ~$1,043-1,097 ≈ 10.4-11.0% APR

Honest Y2 estimate: $850-1,150 median ~$950 ≈ 9.5%
Stretch (overlays verified): $1,050-1,250 ~$1,100 ≈ 11%
```

**10-year compound at 10% sustained**: $10k → $25.9k Y10
**Stretch at 12% sustained**: $10k → $31.1k Y10

vs S&P passive 8%: $21.6k Y10
v5.7 honest differential: **+$4-9k over 10 years** + skills + Copy Trading optionality

---

## §3 Schema Migration Number Reconciliation (Reviewer §1 Fix)

**v5.5/v5.6 mistake**: Reused "V101 minimal" for hypotheses + preregistration tables.

**Reality**: V101 already reserved by `docs/execution_plan/2026-05-20--v101_v102_track_attribution_migration_spec.md` for 12-table Track attribution schema (per v4.2 + AMD-2026-05-20-03).

**v5.7 fix**:
```
Migration plan v5.7:

V097, V098: catch-up on Linux DB (Phase 0, unchanged)
V099-V100: reserved for LG-3 + W-AUDIT-8a residuals (do not touch)
V101, V102: Track schema 12-table attribution (existing spec, separate dispatch when relevant)
V103: NEW v5.7 schema: hypotheses + hypothesis_preregistration tables
V104: NEW v5.7 schema: trading.fills.track column add (subset of V101 work; PA may consolidate)

PA dispatch confirms final numbers based on:
- Linux DB head at dispatch time
- Other in-flight migration work
- Race-aware sequencing

v5.7 spec uses V103/V104 placeholder; PA dispatch finalizes.
```

---

## §4 Bybit Earn — Dynamic APR + Governance Policy (Reviewer §2 + §6 Fix)

**v5.6 mistakes**:
- Hardcoded 4-8% APR
- No governance for stake/redeem (asset write operations)

**v5.7 fix**:

```
Earn cash management policy:

1. APR is dynamic:
   - Bybit API query for current tiered APR at each rebalance decision
   - $200 first-tier rate vs subsequent-tier rate
   - Effective APR per dollar = weighted average
   - Recompute portfolio yield estimates using actual API rates

2. Asset movement governance:
   - Each stake operation = asset write, requires authorization
   - Guardian-checked: same risk envelope as trading operations
   - Decision Lease pattern: stake intent → guardian → execute → audit log
   - Auto-redeem trigger: trading margin headroom < 30%
   - Manual rebalance initially (first 3 months); auto after proven
   
3. Internal asset movement audit:
   - learning.earn_movement_log table (new)
   - Records: amount, direction, APR at time, governance approval
   - Daily reconciliation with Bybit account balance

4. Engineering scope:
   - Earn API integration: ~15 hr (Bybit API extension)
   - Governance integration (Guardian + Decision Lease): ~20 hr
   - Audit log schema + writer: ~10 hr
   - Total: ~45 hr (v5.6 estimated 10 hr was too low)
```

---

## §5 Macro / On-Chain — Counterfactual Only Y1 (Reviewer §5 Fix)

**v5.6 mistake**: Counted +1-3% APR macro + 1-2% on-chain in income estimates without verification.

**v5.7 fix**:

```
Macro overlay - Y1 mode:
- Read-only logging: macro events tracked + strategy decisions logged
- Counterfactual A/B: what would have happened with vs without overlay
- NOT applied to actual strategy triggers in Y1 production
- Counted as ZERO income in v5.7 estimates
- Y1 末 evaluate counterfactual evidence
- If overlay真 alpha (counterfactual shows +2%+ on strategies) → Y2 enable
- If overlay null/marginal → retire layer, save engineering

On-chain signals - Y1 mode:
- Read-only logging: signal generation + outcome correlation
- Counterfactual A/B: signal accuracy vs strategy returns
- NOT applied to actual strategy triggers in Y1 production
- Counted as ZERO income in v5.7 estimates
- Y1 末 evaluate counterfactual evidence
- If signals真 alpha → Y2 enable
- If marginal → retire layer

Engineering scope:
- Macro feed + counterfactual logger: 25-35 hr (less than v5.6 30-50 hr)
- On-chain feed + counterfactual logger: 30-40 hr (less than v5.6 40-60 hr)
- A/B evaluation framework: 15-20 hr
- Total: 70-95 hr (vs v5.6 70-110 hr but for production trigger integration)

Y1 conclusion: 2 unverified features investigated; if proven → Y2 income.
v5.7 income honest: NOT counted in Y1 or initial Y2 baseline.
```

---

## §6 Liquidation Writer — Existing, Not NEW (Reviewer §3 Fix)

**v5.6 mistake**: Wrote "Bybit allLiquidation WebSocket (NEW Sprint 1)".

**Reality**: 
- `rust/openclaw_engine/src/database/market_writer.rs` actively writes `market.liquidations`
- `panel_aggregator/liquidation_pulse.rs` consumes `allLiquidation.{symbol}` events
- WS dispatch already routes `allLiquidation.*` topics
- Writer has been running, 30k+ rows in DB

**v5.7 fix**:
```
Sprint 1 Tier 0 Sensors:
- Bybit perp WebSocket: EXTEND existing (add Binance perp WS NEW)
- Bybit allLiquidation WebSocket: HEALTHCHECK existing writer, NOT new
- Funding rate aggregator: HEALTHCHECK existing rate logger; add Binance polling
- Options chain recorder: NEW (Bybit options not previously tracked)
- Token unlock calendar: NEW (Tokenomist trial integration)
- Macro calendar feed: NEW (FOMC/CPI/halving)

Engineering save: ~15-20 hr (don't rebuild liquidation writer)
```

---

## §7 Auto-Allocator Defer to Y2 (Reviewer §4 Fix)

**v5.6 mistake**: Sprint 9 (W32) Auto-Allocator activation, but requires 6mo advisory; Advisory Sprint 7 (W24) → Sprint 9 = 8 weeks, not 6 months.

**v5.7 fix**:
```
Allocator deployment:

Sprint 7 (W24-27): Advisory Allocator activation
  - Generates monthly proposals (multi-component reward)
  - Operator approves via Console
  - All approved → Decision Lease + Guardian + Stage gate

Sprint 8-10 (W28-39): Advisory mode continues, 4-6 months total
  - Track operator approval rate
  - Track allocator proposal quality
  - Refine reward function weights

Y2 Sprint 11+ (W40+): Auto-Allocator activation gate evaluation
  - Requires: 6+ months advisory + >80% operator approval rate
  - + No material allocator-caused incidents
  - + Operator confidence in algorithmic decisions
  - If gate passes → enable auto with hard limits
  - If gate fails → continue advisory longer or refine

Honest timeline: Auto-Allocator earliest Y2 Q1, possibly later
```

---

## §8 Sprint 1 Split (Reviewer's Recommended 1A/1B)

**v5.6 mistake**: Sprint 1 (W0-3) loaded too heavily: governance + V097/V098 + V103/V104 + Earn + Binance WS + liquidation healthcheck + funding aggregator + options recorder + Tokenomist + macro feed + C10 live.

**v5.7 fix — split into Sprint 1A and 1B**:

### Sprint 1A — Governance + Migration + Sensors (Week 0-1.5)

- ADR-0006 amend
- V097/V098 Linux DB catch-up
- V103/V104 schema (hypotheses + preregistration + trading.fills.track)
- Existing market.liquidations writer healthcheck
- Bybit options chain recorder NEW
- Tokenomist unlock calendar NEW
- Macro calendar feed NEW
- Binance market-data-only WebSocket NEW
- Bybit Earn API APR recorder (read-only, no stake yet)
- Engineering: 60-80 hr

### Sprint 1B — C10 + Earn Live + Alpha Tournament Prep (Week 1.5-3)

- C10 minimal viable on 主帳 $2,000
- Earn governance policy + first small manual stake $200-400
- Alpha Tournament dataset readiness check
- Pre-registration table seeded with strategy candidates
- Engineering: 50-70 hr

**Total Sprint 1 (1A + 1B): 110-150 hr over 3 weeks** (vs v5.6 100-130 hr 但 underestimated)

---

## §9 v5.7 Engineering Total (Updated)

| Sprint | Weeks | Focus | Hours |
|---|---|---|---|
| 1A | 0-1.5 | Governance + Migration + Sensors | 60-80 |
| 1B | 1.5-3 | C10 + Earn live + Tournament prep | 50-70 |
| 2 | 4-7 | Alpha Tournament + Microstructure + On-chain counterfactual setup | 110-150 |
| 3 | 8-11 | Top-1 build + Stage 0 shadow | 130-160 |
| 4 | 12-15 | Top-1 live + Top-2 + Options Stack 1 | 160-210 |
| 5 | 16-19 | Top-2 live + Top-3 + Options Stack 2 | 150-200 |
| 6 | 20-23 | Top-4 + C13-VRP + Funding short | 140-180 |
| 7 | 24-27 | Top-5 + Advisory Allocator + Live promos | 110-150 |
| 8 | 28-31 | Decay + Discovery + Moat Design | 110-150 |
| 9 | 32-35 | Continue Advisory + Copy Infra build | 100-140 |
| 10 | 36-39 | Y1 Review + Copy Trading Evidence Gate + Overlay verdict | 70-100 |
| **Total** | **39 weeks** | | **1,190-1,590 hr** |

vs v5.6 (1,180-1,570 hr): roughly same total but reallocated:
- Less wasted on duplicate liquidation writer
- More on Earn governance
- Less on macro/on-chain production integration (counterfactual only)
- Sprint 1 split adds clarity

---

## §10 Honest Aggregate Outcomes

```
Y1 expected (no overlay alpha counted): $300-550 ≈ 4.2% APR
Y2 mature (no overlay alpha): $850-1,050 ≈ 9.4% APR  
Y2 with overlay verified: $1,050-1,250 ≈ 11% APR
Y3+ steady state: 10-12% APR sustained median

10-year compound at 10% sustained: $10k → $25.9k Y10
At 12% sustained: $10k → $31.1k Y10
At 15% (stretch with Copy Trading): $10k → $40.5k Y10

vs S&P passive 8%: $21.6k Y10

Honest differential: $4-19k over 10 years self-only
With Y2+ Copy Trading scaling: potential $50-150k Y10 stretch

These are honest numbers, not optimistic.
```

---

## §11 5 Reviewer Conditions Met (Dispatch-Safe)

Reviewer specified 5 conditions for dispatch-safe v5.6 patch:

✅ **Condition 1**: V101/V102 migration name conflict fixed → v5.7 uses V103/V104 placeholder, PA dispatch finalizes

✅ **Condition 2**: Earn APR dynamic API tracking, not hardcoded → v5.7 §4

✅ **Condition 3**: Macro/on-chain not counted as income, counterfactual only → v5.7 §5

✅ **Condition 4**: Auto-Allocator deferred to Y2 → v5.7 §7

✅ **Condition 5**: Sprint 1 split into 1A/1B (sensor + evidence first, then build) → v5.7 §8

**v5.7 is dispatch-safe**. Sprint 1A can begin immediately upon operator final approval.

---

## §12 Governance Compliance Recap

All Stage transitions per AMD-2026-05-15-01 unchanged.

ADRs/AMDs:
- ADR-0006 amendment: Bybit primary + Binance market data + DEX not approved
- ADR-0024-lite, -0025 v3, -0026 v3, -0027 active
- ADR-0028 (proposed): Copy Trading evidence-gated
- ADR-0029 (proposed): Framework expansion (Earn governance + macro counterfactual + on-chain counterfactual)
- ADR-0030 (proposed): Bybit Earn asset movement Guardian policy

All 14 hard problems from reviewer rounds 12-15 addressed.

---

## §13 References

- v5.6 (superseded): `srv/2026-05-20--execution-plan-v5.6.md`
- v1 through v5.5: audit trail
- AMD-01 through AMD-05: governance amendments
- V101/V102 Track schema spec: `docs/execution_plan/2026-05-20--v101_v102_track_attribution_migration_spec.md`
- Round 15 reviewer audit (verified 6/6 corrections)
- Bybit Earn tiered APR (verified web search Round 15)
- market.liquidations writer (grep verified existing)

---

**END v5.7 — Dispatch-Safe Patch**

**Sprint 1A ready for PA dispatch upon operator final approval.**
