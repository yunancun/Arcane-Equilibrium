# 玄衡 · Arcane Equilibrium — Execution Plan v4.4

**This is the final execution plan. No more audit rounds. PA dispatch immediately.**

**日期**：2026-05-20
**Status**：ACTIVE — supersedes v4.3 + retracts Stream 3 IP sale + supersedes "dual-track architecture" framing
**Foundation**：Round 7 真實 data verification + operator final constraint relaxations
**Estimated break-even probability**：18 月 42-55% / 24 月 50-65% / 30 月 58-72%

---

## §0 Constraints (final, locked)

| ID | Value |
|---|---|
| D1 | Bybit-only |
| D2 | $10k cap, max real loss $3,000 (30% ceiling)，本金 ≥ $7,000 |
| D3 | No outside consultant |
| D4 | Off-exchange Revolut $1,500 + Wise $1,000 |
| D5 | NOT US tax jurisdiction (ES resident) |
| D6 | Timeline flexible 18-24+ months |
| D7 | NO content/subscription monetization |
| D8 | C (50% subscription attribution) + active degradation |
| D9 | Bybit Copy Trading subaccount $1,500 ON |
| D10 | Crypto prop firm verification ON |
| D11 | Execute |

---

## §1 Capital Configuration (locked)

```
$10,000 total:
├─ Bybit 主帳 $6,000 (alpha verification)
│   ├─ C10 funding harvest        $3,500
│   ├─ C9 unlock event             $0 (await Tokenomist data)
│   ├─ C3 regime revival           $0 (sunset, offline analysis only)
│   ├─ C1 LCS micro                $500 (telemetry only, no trade)
│   └─ Bybit cash buffer           $2,000 (was $500; absorbed C9+C3)
├─ Bybit 副帳 $1,500 (Copy Trading aggressive)
│   └─ Trend breakout + pullback strategy
└─ Off-exchange $2,500
    ├─ Revolut EUR/USD             $1,500
    └─ Wise multi-currency         $1,000
```

**Worst-case DD check**:
- 主帳 portfolio max DD ~$800 (13% of $6,000)
- 副帳 Copy Trading worst -$1,500 (100%)
- Total worst ~$2,300 = 23% of $10k = within 30% ceiling ✓
- Off-exchange $2,500 untouched = 本金 ≥ $7,500 ✓ (better than $7,000 D2 floor)

---

## §2 Phase Structure

### Phase 0 — Setup (Week 0, ~3-5 days)

**Tasks**:
- Off-exchange cash 配置完成（Revolut + Wise to $2,500）
- Bybit 主帳 + 副帳 subaccount creation
- Linux DB migration drift reconcile (V097/V098 catch-up, UTC 04-06 low-write window)
- Subscription degradation policy formalized (Build/Observe/Idle modes per ADR-0027)

**KPI**:
- $2,500 confirmed off-exchange
- $7,500 confirmed in Bybit subaccounts
- Linux DB head = V098 confirmed
- Phase 0 sign-off

### Phase A — Alpha Verification + Copy Trading Bootstrap (Month 1-3)

**Mode**: Build ($400/mo subscription budget)

**Stream 1 — 主帳 C10 funding harvest** ($3,500):
- Top 3-5 basket: BSB/HYPE/SUI/XAUT/ARB (per Round 7 API data)
- Long spot + Short perp delta-neutral
- Monthly rebalance maker orders
- Target: stable $100-250/yr proven over 90d
- Implementation: ~500 LOC Rust strategy module + Python orchestrator

**Stream 2 — 副帳 Copy Trading aggressive** ($1,500):
- Profile: USDT perp trend breakout + pullback
- Symbols: BTC/ETH/SOL/HYPE/SUI (top liquidity for follower experience)
- Risk: 0.8-1.5% per trade, portfolio heat ≤6%, forced stop at -18% monthly
- Frequency: 3-10 trades/week, no scalping
- Target: 90d positive ROI + max DD <25%
- Implementation: ~400 LOC strategy + manual trade execution OR Bybit Copy Master Trader compatible automation

**Background tasks**:
- C9 Tokenomist free trial application (Week 2)
- C9 event study (Month 2-3)
- C1 60d sample accumulation (passive, no action)
- C3 offline stratification analysis (background, no live trade)

**Phase A KPI** (end of Month 3):
- C10 90d real ROI > 0 bps net
- 副帳 90d ROI > 0%, DD < 25%
- C9 event study Tokenomist trial complete or rejected
- C1 sample ≥ 60d
- C3 verdict: positive slice OR sunset

### Phase B — Monetization Activation (Month 4-9)

**Mode**: Mixed Build/Observe (~$200/mo average)

**Stream 3 — Bybit Master Trader application** (Month 4):
- 副帳 90d eligibility check：
  - 7d trades ≥ 2
  - 30d trading days ≥ 5
  - 90d trading days ≥ 14
  - 30d max DD ≤ 40%
  - Wallet ≥ 500 USDT (副帳 OK)
- Apply Master Trader status
- Wait 2-3 business days for activation
- Optimize for Bybit leaderboard exposure

**Stream 4 — Prop firm 1 evaluation** (Month 2-3, if Phase A 30d positive):
- Choice: Breakout (Kraken-backed, Trustpilot 4.8) or HyroTrader (Bybit-native, Trustpilot 4.2)
- Evaluation budget: $100-300 first attempt, $600 cap (max 2 attempts)
- Strategy for evaluation: tighter version of 副帳 strategy
- Pass criteria: 10% profit target with ≤6-10% max DD
- If pass: $25k-$200k funded account opens

**Stream 5 — Bybit competition opportunistic** (sporadic):
- Monitor monthly Bybit competition announcements
- Enter eligible ones (US/UK/EEA restrictions check first)
- 0 capital commitment, opportunistic prize upside

**Phase B KPI** (end of Month 9):
- Master Trader status: APPROVED
- Followers: ≥4 first followers, AUM ≥ $4k
- Prop firm: 1 evaluation outcome (pass or fail)
- C10 cumulative: $50-150 net
- Combined cumulative: $300-1,000

### Phase C — Scale or Reset (Month 10-18+)

**Mode**: Mixed (~$100-150/mo subscription)

**Decision tree at Month 12**:

```
Outcome A (probability 35-50%): On track to break-even
  - Copy Trading AUM growing organically
  - C10 stable
  - Prop firm passed OR not pursued (acceptable)
  → CONTINUE; expand Copy Trading capital if profitable

Outcome B (probability 30-40%): Slow but positive
  - Some monetization but below break-even
  - C10 yielding small
  - Need 6-12 more months to break-even
  → CONTINUE in Observe mode (lower burn)

Outcome C (probability 15-25%): Failed
  - Copy Trading 0 followers
  - Prop firm failed both attempts
  - C10 marginal
  → HARD STOP at Month 18; codebase to portfolio asset
```

**Phase C decision criteria** at Month 18:
- If Cumulative net P&L > -$1,500 (within D2): continue to Month 24
- If Cumulative net P&L < -$1,500: STOP, reset operator capital

---

## §3 Engineering Workload

| Phase | Tasks | LOC estimate | Hours estimate |
|---|---|---|---|
| Phase 0 | Off-exchange + subaccount + migration | ~100 SQL | 10-15 |
| Phase A Stream 1 (C10) | spot+perp orchestrator + rebalance | ~500 Rust + 200 Py | 40-60 |
| Phase A Stream 2 (Copy aggressive) | trend strategy module | ~400 Rust | 30-50 |
| Phase A Background | C9 event study script + C3 stratify | ~400 Py | 20-30 |
| Phase B Master Trader | Bybit API integration + leaderboard monitoring | ~200 Py | 15-25 |
| Phase B Prop eval | tighter strategy variant + risk discipline | ~150 Rust | 10-15 |
| Phase C ongoing | maintenance + monitoring | minimal | 5 hr/wk |

**Total Phase A engineering**: ~1,650 LOC + ~120-180 hours over 12 weeks
**Phase B engineering**: ~350 LOC + ~25-40 hours
**Maintenance**: 5 hr/wk steady state from Month 4+

---

## §4 ADR / governance unchanged

- ADR-0001 (Rust trading authority) — unchanged
- ADR-0006 (Bybit-only) — unchanged
- ADR-0011 (V### migration Linux PG dry-run) — applies to V097/V098 catch-up
- ADR-0018 (funding_arb retire) — applies to C3 sunset
- ADR-0020 (Layer 2 manual+supervisor-only) — unchanged
- ADR-0024-lite (Cowork subscription operator-assistant) — operative
- ADR-0025 v3, ADR-0026 v3 — Track schema land but Phase A scope MINIMAL (only trading.fills + hypothesis_preregistration)
- ADR-0027 (Plan Mode time-based) — operative

**Simplification**: V101 12-table scope DEFERRED until Phase B starts. Phase A only needs:
- trading.fills.track column added (so we can separate C10 vs Copy Trading P&L)
- learning.hypothesis_preregistration table (Track A pre-reg per ADR-0026)

This is ~3 ALTER TABLE + 1 CREATE TABLE = ~50 LOC SQL. NOT 12+1 tables.

---

## §5 Kill Criteria (binary)

| Event | Action |
|---|---|
| Phase 0 fails (off-exchange or migration) | Wait, fix, retry; don't proceed without |
| Phase A Month 3: C10 net APR < 1.5% | Reduce C10 to $1,500, expand cash buffer |
| Phase A Month 3: 副帳 ROI < -10% or DD > 30% | KILL Copy Trading subaccount, return $1,500 to main |
| Phase B Month 6: 0 Master Trader followers | Continue but adjust strategy profile |
| Phase B Prop firm 2 evaluations fail | Stop prop firm path entirely |
| Cumulative loss > $3,000 (D2 ceiling) | HARD STOP all trading immediately |
| Bybit regulatory shutdown / freeze | Off-exchange保 $2,500，主帳 loss accept |
| Operator burnout (consecutive 4 weeks 0 commits) | Pause, re-evaluate at Month 6/12/18 |

---

## §6 No more audits

**This is the final plan**. After 8 rounds of audit and 5 amendments, the planning phase ends here.

Future amendments only triggered by:
1. Material new information (e.g., Bybit regulatory change)
2. Phase A KPI miss requiring strategy reset
3. Operator constraint change

Otherwise:
- PA → E1 dispatch begins immediately
- Phase 0 Week 0
- Phase A Month 1-3 build
- No further LLM audit unless critical issue

---

## §7 Concrete Week 1 Actions (operator side)

Operator personal actions (no engineering):
1. Set up Revolut $1,500 + Wise $1,000 transfer (Day 1-3)
2. Open Bybit 副帳 subaccount + transfer 100 USDT min (Day 4)
3. Apply Tokenomist free trial account (Day 5)
4. Verify Bybit Copy Trading region eligibility (Day 6)
5. Identify prop firm region eligibility (Breakout / HyroTrader account creation only, no evaluation yet) (Day 7)

Engineering actions (E1):
1. V097 + V098 migration catch-up Linux DB (UTC 04-06)
2. Minimal V101 (3 ALTER + 1 CREATE) draft
3. C10 funding harvest spec finalize
4. Phase A Stream 1/2 sprint kickoff

---

## §8 References

- v1-v4.3: `srv/2026-05-20--*.md` (all audit trail, no longer active)
- AMD-01 through AMD-05: governance amendments (Round 1-4 audit history)
- Round 7 audit baseline: data + monetization verification (locked)
- Round 8 prompt sent but no new findings (Round 7 confirmed as final)
- ADR-0011 / -0024-lite / -0025 v3 / -0026 v3 / -0027 (active governance)

---

**END v4.4 — Execute.**
