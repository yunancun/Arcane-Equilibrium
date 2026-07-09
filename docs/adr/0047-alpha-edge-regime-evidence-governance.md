# ADR 0047: Alpha-Edge Regime Evidence Governance

Date: 2026-05-31
Status: **Accepted**
Operator Sign-off Date: 2026-05-31
Scope: Alpha-Edge S1-Sx evidence, regime labeling, Bybit market-data use, external narrative evidence.

## Context

Alpha-Edge research found two active failure modes:

1. A candidate can look strong on a bull-market slice while failing to prove durable alpha.
2. Old or narrow samples can create false confidence when agents report aggregate performance without regime, breadth, or freshness labels.

The operator clarified that bull-market data is not forbidden. The problem is unlabeled use of bull-heavy data as general-market proof. The operator also clarified that future news / X / Reddit / market-summary agents may provide context, but the trading system and promotion gates must remain math-primary.

Bybit V5 market APIs expose raw market-state inputs such as kline, mark/index/premium klines, tickers, orderbook, funding history, open interest, long/short ratio, and historical volatility. These endpoints are not prediction oracles. Any trend or regime judgment must be produced locally from leak-free, point-in-time features.

## Decision

Adopt the following governance rules for all Alpha-Edge S1-Sx work:

1. **Bull data is allowed, but must be labeled.** Reports must explicitly mark evidence as `bull-heavy`, `rally-only`, `2024-dominated`, or `stale-year-dominated` when applicable.
2. **S4 is a global falsification overlay.** S4 is no longer a standalone 2024 bull-data proof track. It is a cross-track regime robustness check for S1-Sx.
3. **Promotion evidence is math-primary.** Strategy promotion cannot rely on news, X, Reddit, market commentary, or any external narrative feed as the main signal or proof.
4. **Bybit market data is raw input.** Bybit market endpoints may be used as state features, but local code must compute trend/regime labels. Agents must not treat exchange-provided data as a forecast.
5. **Every candidate verdict needs an evidence matrix.** At minimum: regime, breadth cohort, time freshness, survivorship correction, and execution realism.
6. **Bull-only or stale-only positives cannot promote.** A positive result concentrated in a bull/rally slice or old-year slice is classified as `regime-bet` or `learning-only` unless cross-regime robustness is separately proven.
7. **Classifier rules are fixed before alpha scoring.** Regime thresholds must be specified before candidate scoring to avoid moving boundaries to fit a strategy.

## Required Verdict Labels

Every S1-Sx candidate verdict must end in one of:

- `durable-alpha candidate`
- `regime-bet / learning-only`
- `stale-data artifact`
- `breadth-limited`
- `insufficient evidence`
- `kill`

## Required Evidence Matrix

Each candidate report must include:

- Regime: bull / range / bear / chop / high-vol, with overlay flags where relevant.
- Breadth: core25 / scanner-active / top-liquidity 40-50 / full survivorship diagnostics.
- Freshness: 2024 / 2025 / 2026 and rolling recent-window result.
- Survivorship: active-only comparison vs delisted/closed-aware universe.
- Execution realism: fees, slippage, maker-fill feasibility, latency, order availability, and capacity/depth where relevant.
- Statistical gates: net edge vs all-in cost, IS/OOS, PSR, DSR, multiple-testing correction, and n_independent.

## Consequences

- Existing 2024 bull funding slices remain useful, but only as labeled regime/falsification evidence.
- S1 backfill and breadth automation must produce reusable regime/freshness labels before promotion verdicts.
- Future narrative agents may annotate events and sentiment, but their output is secondary context and cannot override failed quantitative gates.
- New Bybit market endpoints used for this work must update `docs/references/2026-04-04--bybit_api_reference.md` and receive BB review.
- This ADR grants no trading authority and does not relax Stage 0R, Demo, LiveDemo, true-live, or 5-gate requirements.

## References

- Operator decision report: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-31--alpha_edge_operator_decisions.md`
- Alpha-Edge execution plan: `docs/archive/2026-07-09--execution_plan_v58_closed/2026-05-31--alpha_edge_research_execution_plan.md`
- Alpha Source Architecture Upgrade: `docs/adr/0021-alpha-source-architecture-upgrade.md`
- Bybit V5 Kline: `https://bybit-exchange.github.io/docs/v5/market/kline`
- Bybit V5 Open Interest: `https://bybit-exchange.github.io/docs/v5/market/open-interest`
- Bybit V5 Long/Short Ratio: `https://bybit-exchange.github.io/docs/v5/market/long-short-ratio`
- Bybit V5 Funding History: `https://bybit-exchange.github.io/docs/v5/market/history-fund-rate`

## Sign-off

| Role | Source | Date | Status |
|---|---|---|---|
| Operator | Direct clarification in PM session | 2026-05-31 | ✅ Accepted |
| PM | ADR drafted and governance cascade prepared | 2026-05-31 | ✅ Accepted |
| QC | Regime/falsification governance recommendations | 2026-05-31 | ✅ Incorporated |
| MIT | Data/API/storage feasibility recommendations | 2026-05-31 | ✅ Incorporated into AEG arrangement |
| PA | Engineering arrangement | 2026-05-31 | ✅ Incorporated into AEG arrangement |

---

*Arcane Equilibrium ADR-0047 — Alpha-Edge evidence remains math-primary; bull data must be labeled; S4 is a global S1-Sx falsification overlay; narrative evidence is secondary context only.*
