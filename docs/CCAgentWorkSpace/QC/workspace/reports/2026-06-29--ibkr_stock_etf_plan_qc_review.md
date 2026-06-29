# QC Review — IBKR Stock/ETF Paper + Shadow Evidence Lane

Date: 2026-06-29
Role: QC(default)
Scope: quant / alpha feasibility review of `docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md`
Verdict: **REVISE before starting the 6-8 week evidence clock**
Status: **DONE_WITH_CONCERNS**

## Executive Summary

The plan is a sound engineering and governance skeleton for an isolated `stock_etf_cash` paper/shadow lane. It is not yet a sufficient profitability-feasibility protocol.

As written, the 6-8 week collection window can answer: "can AE collect reconstructable IBKR paper/shadow evidence without violating boundaries?" It cannot reliably answer: "does this stock/ETF lane have durable after-cost alpha?" The main failure mode is false optimism from broad universe definitions, unspecified benchmarks, underpowered low-frequency samples, and weak promotion-like criteria based on positive point estimates.

My recommendation is **Phase 0 ADR/spec may proceed**, but Phase 5 must be rewritten before the evidence clock starts. Treat the first 6-8 weeks as an **engineering shakedown plus preliminary feasibility screen**, not as promotion-grade profitability evidence, unless the revisions below are accepted and the realized sample satisfies the pre-registered power thresholds.

Finding counts: **CRITICAL 0 / HIGH 6 / MEDIUM 5 / LOW 1**.

## Sources Reviewed

- `AGENTS.md`, `CLAUDE.md`, `.codex/MEMORY.md`, `README.md`
- `docs/agents/context-loading.md`
- `docs/adr/0047-alpha-edge-regime-evidence-governance.md`
- `docs/agents/profit-first-autonomy-loop.md`
- `TODO.md` profitability-relevant facts
- `.codex/AGENT_DISPATCH_PROTOCOL.md`, `.codex/SUBAGENT_EXECUTION_RULES.md`
- `.codex/agents/QC.md`, `.claude/agents/QC.md`, QC profile/memory
- QC skills: `quant-strategy-design`, `math-model-audit`, `walk-forward-validation-protocol`, `portfolio-construction-protocol`
- `docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md`

Note: QC role memory normally asks for a memory append and Operator mirror, but the operator explicitly constrained writes to this report only. I did not modify any other file.

## Verdict

**REVISE.** The plan should not claim that 6-8 weeks can decide profitability feasibility until it adds:

1. A frozen, exact universe with survivorship/corporate-action handling.
2. Strategy-specific benchmarks and matched-control portfolios.
3. Pre-registered turnover, cost, and adverse-selection stress thresholds.
4. Sample-size and statistical-power gates based on independent observations, not raw trade count.
5. Paper-vs-shadow divergence thresholds with quarantine actions.
6. Promotion/go-no-go rules using confidence intervals, PSR/DSR or equivalent deflation, drawdown limits, and multiple-testing correction.

Without those, the likely output is either false optimism in a bull/risk-on equity slice or an inconclusive report dressed up as evidence.

## Findings

### HIGH-1 — 6-8 weeks is underpowered for the proposed strategy classes

The plan lists daily/weekly momentum, sector rotation, ETF trend/risk-off rotation, mean reversion after overextension, and earnings drift research-only. Most of these are low-frequency or medium-frequency strategies. A 6-8 week US equity window is roughly 30-40 trading days. Weekly rotation may produce only 6-8 portfolio decisions; daily momentum may still have highly autocorrelated day-clustered observations; sector and ETF signals are dominated by common market beta.

The plan mentions "100+ reconstructable samples" and bootstrap for lower-frequency strategies, but bootstrap cannot create new independent information. It can only quantify uncertainty in the observations already present. Correlated trades across many symbols on the same day do not equal 100 independent samples.

Required revision: define `n_independent`, clustered by date and symbol/sector, before collection starts. If the realized sample is below the pre-registered power threshold, the only valid verdict is **insufficient evidence**, not go/no-go.

### HIGH-2 — Universe definition is too broad and can create selection bias

The proposed universe is "US liquid stocks" plus "UCITS ETFs." That is not a tradable research universe. It leaves room for cherry-picking by market cap, spread, availability, region, currency, ETF domicile, sector, and after-the-fact symbol inclusion.

This also mixes different market structures: US cash equities, ETFs, possible non-US UCITS listings, different currencies, holiday calendars, fees, tax/transaction-cost placeholders, and settlement behavior. A broad label like "liquid" is not enough to prevent survivorship or beta concentration.

Required revision: freeze exact cohorts before scoring. Example: `US_LARGE_100_v1`, `US_SECTOR_ETF_11_v1`, `US_LIQUID_ETF_50_v1`, with inclusion date, primary listing, currency, corporate action policy, delisting policy, spread/ADV thresholds, and IBKR tradability status. Do not merge UCITS and US-listed ETFs into one performance verdict.

### HIGH-3 — Benchmark design is unspecified, so beta can masquerade as alpha

The plan requires `benchmark excess return > 0`, but does not define the benchmark. For stocks and ETFs, this is the central alpha question. A strategy that is simply long high-beta US equities during a rising 6-week window can beat cash and still have no alpha.

Required revision: benchmarks must be strategy-specific and pre-registered:

- US stock momentum: SPY plus sector-neutral or beta-matched equal-weight universe.
- Sector rotation: equal-weight sector ETF basket and SPY, with same rebalance calendar and cost model.
- ETF trend/risk-off: static benchmark matching target exposure, e.g. SPY/AGG/T-bill blend, not just zero.
- Mean reversion: same-universe equal-weight or randomized-entry matched-control with identical holding-period and turnover constraints.
- Earnings drift: event-calendar control portfolio matched by sector, size, and event date.

Report both absolute net PnL and benchmark-relative alpha/beta. A positive market-regime result with no benchmark-adjusted alpha must be labeled `regime-bet / learning-only`.

### HIGH-4 — Turnover/cost wall is not pre-registered tightly enough

The plan correctly names commissions, spread, slippage, FX drag, FTT/tax placeholder, and conservative fill sensitivity. It does not define the cost wall: maximum allowed turnover, minimum gross edge over all-in cost, cost-edge ratio, adverse-selection penalty, or capacity/depth thresholds.

This is dangerous because stock/ETF edges are often small. A 5-20 bps gross signal can vanish under spread, slippage, partial fills, auction mechanics, FX conversion, exchange/regulatory fees, and tax placeholders. If cost assumptions are calibrated after seeing outcomes, the plan can manufacture false after-cost positivity.

Required revision: freeze cost model version plus stress cases before scoring:

- base cost, conservative cost, and punitive cost per instrument class;
- spread capture/fill penalty rules;
- turnover cap per strategy and per portfolio;
- all-in cost as percent of gross edge;
- sensitivity rule: if conservative or punitive cost flips net expectancy negative, verdict cannot be positive.

Use `cost_edge_ratio < 0.5` as a strong preferred gate; if a strategy needs more than half its gross edge to pay execution costs, it is not robust enough for promotion-like interpretation.

### HIGH-5 — Promotion-like criteria are too weak and point-estimate driven

The plan's promotion-like rules are: after-cost expectancy > 0, benchmark excess > 0, conservative fill > 0, not single-event/symbol driven, labels, and 100+ samples or walk-forward/bootstrap. This is necessary but not sufficient.

Positive point estimates over 6-8 weeks are not evidence of durable alpha. The criteria omit lower confidence bounds, PSR/DSR, multiple-testing correction, drawdown duration, path dependency, parameter plateau, paper/shadow validity, and a clear `insufficient evidence` branch.

Required revision: split the outcome into three separate verdicts:

- **Engineering ready:** data collection, reconstruction, and UI evidence are stable.
- **Research promising:** net excess is positive but statistical power is insufficient.
- **Profitability feasible:** pre-registered statistical and execution-realism gates pass.

Minimum profitability gates should include cluster/block-bootstrap 95% CI for net excess, PSR(0) target, DSR or equivalent deflation across tested strategies/parameters, max drawdown and drawdown-duration limits, and concentration caps.

### HIGH-6 — Paper-vs-shadow divergence has no fail/disable thresholds

The plan tracks paper-vs-shadow divergence, but does not define what divergence invalidates the evidence. This matters because IBKR paper fills and synthetic shadow fills can both be optimistic in different ways. Paper is a broker simulator, not live queue position. Shadow is model output, not execution proof.

Required revision: predefine divergence bands and actions:

- fill-rate ratio outside a fixed band triggers quarantine;
- median and tail fill-price slippage vs quote/bar model must stay within thresholds;
- partial fill, unfilled, delayed fill, and cancel/replace behavior must be separately tracked;
- paper and shadow rows must never be pooled for profitability proof;
- if paper and shadow disagree materially, the verdict is **execution model invalid**, not "take the better result."

The prior QC paper/demo lesson is directly relevant: paper fill-rate ratios outside roughly 0.7-1.3 should prevent use as edge evidence until explained.

### MEDIUM-1 — Strategy list is too broad for a first evidence clock

The first batch includes at least six strategy families. That creates a multiple-hypothesis problem before the lane has even proven data quality. If each family has several parameter variants, the effective K can become large enough that one positive result is expected by chance.

Required revision: pre-register a small number of strategy hypotheses, ideally 2-3, each with alpha source, half-life, turnover target, benchmark, parameter grid, and rejection rule. Everything else should be labeled exploratory and excluded from promotion-like scoring.

### MEDIUM-2 — After-cost scorecard lacks risk-adjusted and statistical fields

The listed daily scorecard metrics are useful but incomplete. It should also include:

- capital-weighted and exposure-adjusted net return;
- net benchmark alpha, beta, tracking error, and information ratio;
- hit rate, payoff ratio, skew, kurtosis, tail loss;
- Sharpe, Sortino, Calmar/MAR, max drawdown duration;
- net expectancy confidence interval;
- cluster by date/symbol/sector;
- number of independent observations;
- parameter set and hypothesis family ID;
- proof-exclusion flags.

Daily rows alone are not a QC verdict surface.

### MEDIUM-3 — Regime/freshness labels are acknowledged but not operationalized

ADR-0047 requires regime, breadth, freshness, survivorship, execution realism, and statistical gates. The plan says to mark bull-heavy/regime-heavy/stale-window but does not define regime classifier thresholds before scoring.

Required revision: define leak-free local regime labels before the evidence window: market trend, realized volatility, breadth, sector dispersion, rate/risk-off proxy, and equity index drawdown state. A positive result in one rising 6-week equity regime should not become `durable-alpha candidate`.

### MEDIUM-4 — Earnings drift and auction behavior need separate data contracts

Earnings drift needs point-in-time earnings calendars, event timestamps, surprise data definition, revisions, and post-event windows. Opening/closing auction behavior needs auction order types, auction price/volume data, and fill assumptions. Treating these as ordinary bar-based shadow strategies will bias results.

Required revision: keep these as research-only until their data contracts are specified. Exclude them from the first go/no-go profitability verdict unless data provenance and fill realism are separately reviewed.

### MEDIUM-5 — Portfolio and capacity evidence is missing

The plan asks for benchmark excess and turnover, but not portfolio-level concentration, factor exposure, or effective number of bets. In equities, many "different" names collapse into the same market/sector/factor exposure.

Required revision: include gross/net exposure, beta to SPY/QQQ/IWM or chosen local factors, sector weights, single-name contribution, top-event contribution, and capacity/depth estimate. A result driven by one sector, one event week, or high market beta must be capped at `regime-bet / learning-only`.

### LOW-1 — Evidence clock start criteria need machine-checkable hashes

The plan says the evidence clock starts after 5 stable trading days, frozen cost model, frozen universe, daily scorecard, and GUI evidence. Good direction, but it should require immutable artifact hashes and version IDs.

Required revision: evidence clock start manifest should include frozen universe hash, benchmark hash, cost model hash, strategy hypothesis hash, collector version, schema version, and the 5-day data-quality report hash.

## Required Go / No-Go Framework

Before Phase 5 starts, write a pre-registration appendix with these fields:

| Area | Required definition |
|---|---|
| Universe | exact symbols, inclusion/exclusion rules, version hash, survivorship/corporate-action policy |
| Strategy hypotheses | alpha source, half-life, turnover target, parameters, K count, benchmark |
| Data quality | missing bar/quote tolerance, corporate action handling, calendar/holiday rules |
| Costs | base/conservative/punitive costs, spread/slippage, FX/tax placeholders, turnover cap |
| Benchmark | strategy-specific matched control and passive baseline |
| Sample size | minimum raw trades, minimum independent date-clustered observations, power assumption |
| Statistics | PSR/DSR or equivalent, block bootstrap CI, multiple-testing correction, drawdown limits |
| Divergence | paper-vs-shadow thresholds and quarantine actions |
| Concentration | max symbol/event/sector contribution and beta exposure limits |
| Verdict labels | `profitability feasible`, `research promising`, `insufficient evidence`, `execution model invalid`, `kill` |

Suggested minimum post-window decisions:

- **GO to extended research / possible tiny-live ADR discussion:** all pre-registered gates pass, lower confidence bound for after-cost benchmark excess is positive under conservative costs, paper/shadow divergence is inside threshold, and no concentration/regime veto fires.
- **NEEDS MORE DATA:** point estimates are positive but independent sample/power is below threshold, or only one regime was observed.
- **NO-GO / KILL:** net expectancy <= 0, benchmark excess <= 0, conservative cost flips negative, divergence invalidates fills, concentration veto fires, or result is only beta/rally exposure.

Do not allow direct promotion from paper/shadow to live. Even a GO result only justifies a separate ADR/spec for a tiny live probe.

## Direct Answer To PM Question

Can the current 6-8 week evidence plan answer profitability feasibility?

**Not as written.** It can answer operational feasibility and produce preliminary after-cost diagnostics. It cannot safely answer profitability feasibility because its universe, benchmarks, independent sample size, cost wall, paper/shadow validity, and go/no-go thresholds are not pre-registered tightly enough.

The plan should be revised before any evidence clock starts. If revised, the 6-8 week window can become a valid **screening gate**. It still should not be treated as durable-alpha proof for low-frequency stock/ETF strategies unless independent sample and cross-regime evidence thresholds are actually met.
