# PM Report — Alpha-Edge NOW 3 Parallel Dispatch

Date: 2026-05-31
Role: PM(default)
Scope: S1-W1-S1, S2-W0-S1, S4-W0-S1 parallel dispatch integration.
Mode: doc/report integration only; no runtime deploy, no DB write, no live/auth/order/execution change.

## Verdict

PM SIGN-OFF: **CONDITIONAL / OPERATOR-GATED**.

The requested three-way parallel dispatch completed:

| Session | Role | Verdict | Report |
|---|---|---|---|
| S1-W1-S1 | MIT(default) | **PASS advisory; S1-W1-S2 still locked** | `docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-31--s1_w1_s1_retention_symbol_universe.md` |
| S2-W0-S1 | QC(default) | **PROCEED** | `docs/CCAgentWorkSpace/QC/workspace/reports/2026-05-31--s2_w0_s1_listing_gate_a_feasibility.md` |
| S4-W0-S1 | MIT(default) | **BLOCKED_ON_RETENTION + SCRIPT** | `docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-31--s4_w0_s1_bull_regime_backfill_preflight.md` |

## Key Results

S1-W1-S1 established the Track 1 data gate. MIT recommends `market.klines` retention `365d -> 1095d`, an 18-month window, core25 as the first analysis breadth, and the full survivorship-corrected 18mo USDT LinearPerpetual universe for collection. The artifact has 797 symbols, including 225 delisted/Closed overlap symbols, so the survivor-only failure mode is closed.

S2-W0-S1 cleared the Track 2 Gate-A kill line. Maker-fill feasibility was 59/67 = 88.1% under the +500bps pump trigger / 1bp PostOnly / 60s BBO-touch proxy, with Wilson 95% interval 78.2-93.8%. This is execution reachability only, not alpha proof. Before collector IMPL, BB still needs a longer isolated PreLaunch phase-transition probe and the design must preserve capture-only isolation.

S4-W0-S1 proved the 2024 bull funding data is available from Bybit public API, but not locally persisted. Local PG has 0 rows for 2024-11 funding/kline coverage. Existing `market.funding_rates` retention is 180d and `market.klines` retention is 365d, so a DB-writing backfill would be reaped unless storage policy changes first. There is also no production-ready idempotent DB writer script for Bybit funding history + daily/4h klines.

## Operator Decision Packet

Recommended decision:

1. Approve `market.klines` retention extension to `1095 days`.
2. Decide how 2024 funding history should persist: extend `market.funding_rates` retention, or create a separate research funding-history table through the normal migration path.
3. Approve Track 1 window = 18mo.
4. Approve Track 1 primary analysis breadth = core25, while collecting the full survivorship-corrected universe.

After that decision, next executable engineering is:

1. E1(worker): implement a public Bybit historical backfill writer for `1d`/`4h` klines plus funding history, with `ON CONFLICT DO NOTHING`, fail-closed API handling, rate limit discipline, and coverage report output.
2. MIT(default): verify coverage, retention persistence after the next retention job, no live-1m contamination, and 2024 funding rows present.
3. QC(default)+MIT(default): run Track 1 leak-free TSMOM/X-sec replay and Track 4 funding percentile directional replay.

## Boundaries

No sub-agent changed runtime, auth, order, execution, strategy config, TOML, or collector code. The only repository changes from this dispatch are reports, the survivorship CSV artifact, PM memory, TODO active-state update, and a status-line correction in the alpha-edge plan.
