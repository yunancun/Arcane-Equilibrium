# MIT Review — IBKR Stock/ETF Paper + Shadow Plan

Date: 2026-06-29
Role: MIT(default)
Scope: data, schema, market data, and statistical validation rigor
Reviewed plan: `docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md`

## Verdict

MIT verdict: `DONE_WITH_CONCERNS` for the review task, but `BLOCK` for Phase 1 schema implementation and Phase 3 evidence collection as currently specified.

The plan is acceptable as a Phase 0 governance discussion starter. It is not yet a data design. The proposed DB section is a table-name inventory, not a relational contract; the evidence section names daily scorecard fields, but does not define the point-in-time universe, market-data vendor tier, corporate-action adjustment policy, cost/tax/FX model, benchmark construction, or statistical design tightly enough to produce auditable after-cost evidence.

Finding counts: `BLOCKER=8`, `HIGH=6`, `MEDIUM=3`, `LOW=2`.

I did not edit code or runtime. I also did not update MIT memory or copy this report elsewhere because the operator explicitly limited modifications to this report file.

## Blocking Summary

Before Phase 1:

- A new ADR/AMD must first accept the `stock_etf_cash` paper/shadow lane boundary; the plan itself recognizes this at lines 22-24 and 391-409.
- The schema proposal must be expanded into DDL-level contracts: primary keys, natural keys, foreign keys, CHECK constraints, idempotent migration guards, hypertable decisions, retention/compression decisions, and required indexes.
- Instrument identity, corporate actions, market-data provenance, FX, tax/fees, and benchmark versions must be first-class tables, not comments or nullable blobs.

Before Phase 3:

- The collector cannot start an evidence clock until vendor/tier, calendar coverage, PIT universe, corporate-action adjustment set, frozen cost model, frozen benchmark, and pre-registered validation design are all machine-checkable.
- The current "100+ trades or bootstrap" acceptance language is not sufficient for daily/weekly strategies. Bootstrap cannot rescue biased sampling, non-PIT universes, overlapping labels, or benchmark leakage.

## Findings

### B-01 — DB plan is table names, not schema

Severity: `BLOCKER`
Confidence: high
Blocks: Phase 1

The plan lists `broker.*`, `research.*`, and `audit.asset_lane_events` tables at lines 181-205, but does not specify keys, relationships, constraints, indexes, hypertable/time partition choices, or lineage fields. The plan then allows Phase 1 to pass with "migration design ready" at lines 423-427. That is weaker than this repo's ADR-0010/0011 standard.

Required before Phase 1:

- ERD or DDL draft with all primary/foreign keys.
- Guard A for every `CREATE TABLE IF NOT EXISTS`; Guard B for type-sensitive columns; Guard C for hot-path indexes.
- Linux PG dry-run packet and idempotency double-apply plan before implementation sign-off.
- Explicit choice of plain table vs hypertable for quotes/bars/fills/scorecard rows.

### B-02 — Instrument identity is under-specified

Severity: `BLOCKER`
Confidence: high
Blocks: Phase 1

The plan names `EquityInstrumentId`, listing venue, currency, primary exchange, tradability, PRIIPs/KID, and fractional eligibility at lines 90-97. That is directionally correct but insufficient. IBKR stock contracts can require `primaryExchange` to disambiguate smart-routed contracts, and IBKR also supports FIGI-based definitions. A ticker string is not stable enough for equities.

Required identity contract:

- Internal immutable instrument id.
- IBKR `conid`, `secType`, `localSymbol`, `tradingClass`, `exchange`, `primaryExchange`, `currency`.
- FIGI, ISIN, CUSIP, SEDOL where available, with source and validity windows.
- Listing MIC/exchange, primary listing flag, listed/delisted/suspended/effective timestamps.
- Security type separation: stock, ETF, cash FX, reserved CFD, reserved option.

Without this, fills, bars, corporate actions, benchmark membership, and scorecard rows cannot be reconstructed.

### B-03 — Corporate actions are named but not modeled

Severity: `BLOCKER`
Confidence: high
Blocks: Phase 1 and Phase 3

The plan includes `broker.corporate_actions` at line 188 but does not define action types, effective dating, adjustment factors, or raw-vs-adjusted market-data policy. Corporate actions are not optional for stock/ETF returns: splits, reverse splits, dividends, spinoffs, mergers, symbol changes, delistings, liquidations, and issuer changes can all affect returns and identity joins.

Required before Phase 1:

- Corporate-action fact table with action type, instrument id, ex-date, record date, payable/effective timestamp, ratio/cash amount/currency, source, source version, and ingestion timestamp.
- Adjustment-set table mapping raw bars to adjusted bars with reproducible factors.
- Scorecard policy: compute PnL from broker fills/cash ledger, compute alpha returns from a named adjusted series, and never mix raw and adjusted series silently.

### B-04 — Market-data vendor, tier, and provenance assumptions are missing

Severity: `BLOCKER`
Confidence: high
Blocks: Phase 1 and Phase 3

The plan says "IBKR read-only account/market-data healthcheck" and "market data ingestion" at lines 16 and 455, but never states whether IBKR is the primary historical/real-time vendor, whether quotes are consolidated NBBO or non-consolidated, whether data is live/delayed/frozen, or whether another vendor will be used for corporate actions and benchmarks.

This matters materially. IBKR states that free US stock/ETF streaming data may be non-consolidated and not NBBO, that delayed data is 15-20 minutes delayed, and that historical data has pacing limits and filtering/adjustment behavior. Those facts must be represented in schema as `data_vendor`, `data_tier`, `subscription_id`, `exchange_ts`, `received_ts`, `request_ts`, `raw_response_hash`, and `adjustment_policy`.

Required before Phase 3:

- Vendor matrix for bars, quotes, trades, corporate actions, benchmark returns, FX, and fees/taxes.
- Data tier enum: live consolidated, live non-consolidated, delayed, frozen, snapshot, historical-adjusted, historical-filtered.
- Coverage/latency SLO by instrument and session.
- Pacing/backfill strategy that does not silently skip symbols.

### B-05 — Point-in-time universe and survivorship controls are not defined

Severity: `BLOCKER`
Confidence: high
Blocks: Phase 3

The plan says "universe frozen or versioned" at line 320 and proposes "US liquid stocks" / "UCITS ETFs" at lines 326-329. That is not enough. Universe construction is a leakage surface: using today's liquid survivors to evaluate prior weeks creates survivorship and selection bias.

Required before Phase 3:

- `universe_versions` and `universe_members` tables with as-of date, data cutoff, rule hash, included/excluded reason, and lifecycle validity.
- Selection features computed only from data available before the decision timestamp.
- Active-only vs delisted/closed-aware comparison required by ADR-0047.
- Frozen universe cannot mean "freeze today's survivors"; it must mean "freeze a versioned PIT construction rule and member snapshot with lifecycle windows."

### B-06 — Fee, slippage, FX, FTT, and tax model versioning is not executable

Severity: `BLOCKER`
Confidence: high
Blocks: Phase 3

The plan names commission, regulatory fees, FX conversion, FTT/stamp duty, spread/slippage, and a frozen cost model at lines 98-103, 361-369, and 537. It does not define a versioned cost-model schema, effective-date handling, account jurisdiction, commission plan, routing assumptions, or source provenance.

This is a hard blocker for "after-cost evidence." As of this review, IBKR's US stocks page includes commission tiers plus third-party fees such as SEC transaction fee, FINRA TAF, CAT, clearing, exchange, and pass-through fees. The SEC Section 31 rate is currently time-dependent, and UK stamp duty/SDRT is a jurisdiction-specific buy-side tax. A generic `FTT/tax placeholder` will either overstate or understate edge.

Required before Phase 3:

- `cost_model_versions` table with immutable version id, effective_from/to, source URLs, retrieval timestamp, account type, broker plan, jurisdiction, and code hash.
- Component table: commission, exchange fee/rebate, regulatory fee, clearing fee, CAT, pass-through, tax/FTT/stamp duty, FX spread/commission, slippage, and conservative fill penalty.
- Separate estimated vs broker-reported realized cost fields.
- No scorecard row can have only a placeholder tax field when the instrument jurisdiction implies a known tax/fee path.

### B-07 — FX, cash ledger, settlement, and withholding are missing

Severity: `BLOCKER`
Confidence: medium-high
Blocks: Phase 1 and Phase 3

The plan has "FX conversion cost" and "FX drag" at lines 101 and 367, but not the data model. A stock/ETF lane with US stocks and UCITS ETFs is necessarily multi-currency unless explicitly restricted. PnL cannot be reconstructed from fills alone.

Required before Phase 1:

- Cash ledger by currency, account, broker environment, event type, trade date, settlement date, value date, and source.
- FX rate table with pair, bid/ask/mid, source, quote timestamp, conversion timestamp, and conversion fee.
- Dividend/cash-distribution and withholding-tax events linked to instruments and corporate actions.
- Benchmark return currency and FX conversion policy.

### B-08 — Statistical validation design is not pre-registered

Severity: `BLOCKER`
Confidence: high
Blocks: Phase 3 and Phase 5

The plan requires after-cost expectancy, benchmark excess return, conservative fill sensitivity, non-single-symbol/event concentration, regime labels, and 100+ reconstructable samples or walk-forward/bootstrap at lines 378-385. That is not a validation design. It does not define primary endpoints, effect sizes, folds, purge/embargo, bootstrap block unit, multiple-testing correction, or independent sample counting.

Required before Phase 3:

- Pre-registered strategy family, universe, benchmark, horizons, labels, and primary metric.
- Walk-forward split schedule with purge/embargo based on holding period and event windows.
- Block/bootstrap unit defined by date and symbol cluster, not iid trade rows.
- HAC/cluster-robust inference for overlapping forward returns.
- PSR/DSR or equivalent multiple-testing adjustment.
- Concentration caps for event, symbol, sector, and calendar week.

### H-01 — Market calendar/session model is too shallow

Severity: `HIGH`
Confidence: high
Blocks: Phase 3 if unfixed

The plan includes `market session calendar`, holidays, early closes, and TTL across sessions at lines 104-107, and `broker.market_sessions` at line 187. It does not include exchange-specific sessions, pre/early/core/late trading, auction windows, early-close overrides, halts/LULD, timezone/DST, or session eligibility per strategy.

NYSE publishes distinct sessions and auction windows; the collector/fill model must know which session a signal belongs to. Opening/closing auction shadow strategies at line 350 cannot be evaluated from a generic "market open/close" calendar.

### H-02 — Benchmark provenance is undefined

Severity: `HIGH`
Confidence: high
Blocks: Phase 3 scorecard credibility

The plan requires benchmark excess return and a frozen benchmark version at lines 374 and 539, but it never defines benchmark identity or source. A sector-rotation strategy, SPY-equity strategy, and UCITS ETF strategy need different benchmarks and possibly different return bases.

Required:

- `benchmark_versions` table with benchmark id, source vendor, total-return vs price-return flag, dividend treatment, currency, timezone, rebalancing calendar, constituent source, and effective date.
- Strategy-to-benchmark mapping locked before scoring.
- Excess return computed from the same PIT calendar/currency convention as the strategy.

### H-03 — Paper-vs-shadow reconciliation is not fully specified

Severity: `HIGH`
Confidence: high

The plan separates `broker.paper_orders`, `broker.paper_fills`, `research.stock_shadow_signals`, and `research.stock_shadow_fills` at lines 190-194, and says shadow fills must not be mixed with broker paper fills at lines 200-202. Good. Missing is the linking contract.

Required:

- Stable `signal_id`, `order_intent_id`, `broker_order_id`, `execution_id`, `commission_report_id`, and `scorecard_row_id`.
- Full order state transition log with placed/ack/partial/cancel/reject/fill timestamps.
- Reconciliation table classifying paper-vs-shadow divergence: price, quantity, timing, venue, commission, FX, tax, and corporate-action/cash events.
- Paper fill remains rehearsal evidence, not live execution proof.

### H-04 — Daily scorecard rows are too lossy as primary evidence

Severity: `HIGH`
Confidence: high

The scorecard fields at lines 361-376 are daily aggregates. Aggregates are useful for the GUI, but cannot be the source of truth for reconstructability. Max drawdown, exposure time, and expectancy must be derived from atomic events: signals, quotes/bars, order states, fills, commissions, FX, cash events, corporate actions, and benchmark marks.

Required:

- Daily scorecard must be a derived view/materialized artifact with input hashes.
- Atomic facts must be immutable or append-only.
- Each scorecard row must carry code commit, data snapshot ids, universe version, benchmark version, cost model version, fill model version, and artifact hash.

### H-05 — ADR-0047 evidence matrix is only partially carried over

Severity: `HIGH`
Confidence: high

The plan only says to label bull-heavy/regime-heavy/stale-window at line 384. ADR-0047 requires regime, breadth, freshness, survivorship correction, execution realism, and statistical gates. It also requires classifier rules to be fixed before alpha scoring.

Required:

- Equity-specific regime classifier fixed before scoring: broad market trend, volatility, rates/credit proxy if used, sector dispersion, and liquidity regime.
- Breadth labels for liquid US stock universe, ETF subset, and any sector cohort.
- Freshness labels by calendar period and recent rolling window.
- Execution realism labels: consolidated vs non-consolidated data, paper-vs-shadow divergence, spread/depth availability, auction eligibility, latency, and capacity.

### H-06 — 6-8 weeks plus 100 trades is not enough for the named strategy mix

Severity: `HIGH`
Confidence: high

The plan includes daily/weekly momentum, sector rotation, ETF trend/risk-off rotation, and earnings drift research at lines 343-350, then asks for 100+ reconstructable samples or walk-forward/bootstrap at line 385. Low-frequency strategies may not generate enough independent samples in 6-8 weeks. Counting multiple symbols on the same day as independent iid trades will overstate significance.

Required:

- Separate evidence clocks by strategy turnover.
- Independent sample definition by date/event/symbol cluster.
- For low-frequency strategies, extend the clock or use pre-Phase-3 historical PIT backtest with the same vendor/corporate-action/benchmark contracts before starting live paper evidence.

### M-01 — UCITS/PRIIPs/ETF metadata needs a source contract

Severity: `MEDIUM`
Confidence: medium-high

The plan mentions `PriipsKidStatus`, fractional eligibility, and UCITS ETFs at lines 96-97, 270-276, and 329. It does not define ETF domicile, KID/PRIIPs source, TER/expense ratio, distributing vs accumulating class, withholding/dividend treatment, leveraged/inverse flag, synthetic/physical replication, or exchange listing currency.

This does not block Phase 0, but it should be added before Phase 1 if UCITS remains in the first universe.

### M-02 — IBKR connector source of truth is not selected

Severity: `MEDIUM`
Confidence: medium

Phase 2 names IBKR account snapshot, orders/fills import, and paper healthcheck at lines 435-446. It does not decide whether orders/fills/commissions/corporate actions come from TWS API callbacks, Client Portal, Flex reports, statements, or a combination. Those sources can differ in latency and field completeness.

Required:

- Source priority order by fact type.
- Reconciliation rules when API callbacks and reports disagree.
- Commission report capture path before any cost evidence is accepted.

### M-03 — Append-only audit is not yet an evidence schema

Severity: `MEDIUM`
Confidence: high

The plan says lanes share append-only audit at line 64 and daily reports must trace to append-only evidence at line 540. That is correct but underspecified. `audit.asset_lane_events` must have event types, actor, source, payload hash, previous hash/sequence, environment, asset lane, broker, and immutable artifact references. Otherwise it becomes a log sink rather than an evidence ledger.

### L-01 — "FTT/tax placeholder" wording is unsafe

Severity: `LOW`
Confidence: high

The plan uses "FTT/tax placeholder" at line 368. That wording should be replaced with "jurisdiction-specific tax/FTT component, versioned and fail-closed when unknown." A placeholder in a daily scorecard can accidentally become an implicit zero.

### L-02 — Source as-of dates are absent from the plan

Severity: `LOW`
Confidence: high

Fees, tax rules, calendars, and data subscription behavior change. The plan should require every external assumption to carry `source_url`, `retrieved_at`, `effective_from`, and `effective_to` fields. This is especially important for SEC/FINRA fees, exchange calendars, IBKR commission schedules, and market-data subscriptions.

## Minimal Phase 1 Schema Contract

The first schema ADR/migration packet should include at least:

- `broker.instruments`: internal id, IBKR conid, secType, symbol, localSymbol, tradingClass, currency, FIGI/ISIN/CUSIP/SEDOL, issuer, security type, source, valid_from/to.
- `broker.instrument_listings`: instrument id, listing MIC/exchange, primary exchange, route exchange, status, listed_at, delisted_at, tick size, lot size, fractional flag, tradability flag, source version.
- `broker.universe_versions` and `broker.universe_members`: rule hash, data cutoff, membership validity, inclusion/exclusion reason, PIT lifecycle proof.
- `broker.market_sessions`: calendar id, exchange, date, timezone, session type, open/close, auction windows, early close, holiday/closed reason, source version.
- `broker.corporate_actions`: action id, instrument id, action type, ex/record/pay/effective dates, ratio/cash/currency, resulting instrument id when applicable, source version.
- `market.stock_bars`, `market.stock_quotes`, or equivalent: vendor, data tier, subscription id, exchange timestamp, receive timestamp, adjusted/raw flag, corporate-action adjustment set id, raw payload hash.
- `broker.fx_rates` and `broker.cash_ledger`: quote/conversion source, bid/ask/mid, currency pair, value date, settlement date, account id, event id.
- `broker.cost_model_versions` and `broker.cost_model_components`: immutable version and effective dating for commissions, regulatory fees, exchange/clearing/pass-through, CAT, FTT/stamp duty, FX, slippage, and fill penalty.
- `broker.paper_orders`, `broker.paper_order_state_changes`, `broker.paper_fills`, `broker.commissions`: broker ids, execution ids, commission report ids, route, TIF, side, quantity, price, timestamps, environment, asset lane.
- `research.stock_shadow_signals`, `research.stock_shadow_fills`: signal id, model/strategy version, input data hash, fill model version, quote/bar snapshot link, synthetic flag.
- `research.stock_etf_scorecard`: derived aggregate only; must link back to all source ids and versions.
- `research.benchmark_versions`: benchmark id, source, TR/price flag, currency, calendar, constituent and rebalance source.
- `audit.asset_lane_events`: append-only event ledger with hash chain or immutable artifact references.

## Minimal Phase 3 Evidence Gate

Do not start the 6-8 week evidence clock until all are true:

- Five trading days of collector health means calendar-aware coverage, not just process uptime.
- Data tier is explicit for every quote/bar: consolidated, non-consolidated, delayed, frozen, or historical-filtered.
- Universe version and PIT selection proof are frozen.
- Corporate-action adjustment set is frozen and replayable.
- Cost model and benchmark versions are frozen with source as-of dates.
- Paper and shadow fills reconcile through stable ids.
- Walk-forward/bootstrap/multiple-testing rules are pre-registered.
- Daily scorecard is regenerated from atomic facts and hashes match.

## External Source Notes

Checked current external assumptions on 2026-06-29:

- IBKR US stocks/ETFs commissions and third-party fee components: [Interactive Brokers commissions page](https://www.interactivebrokers.com/en/pricing/commissions-stocks.php).
- SEC Section 31 transaction fee fiscal 2026 advisory: [SEC fee rate advisory 2026-2](https://www.sec.gov/rules-regulations/fee-rate-advisories/2026-2).
- IBKR market data subscription/tier behavior: [IBKR market data pricing](https://www.interactivebrokers.com/en/pricing/market-data-pricing.php) and [IBKR Campus TWS API market data types](https://ibkrcampus.com/campus/ibkr-api-page/twsapi-doc/).
- IBKR historical data pacing/filtering limitations: [TWS API historical limitations](https://interactivebrokers.github.io/tws-api/historical_limitations.html).
- IBKR contract identity and primary exchange examples: [TWS API basic contracts](https://interactivebrokers.github.io/tws-api/basic_contracts.html).
- IBKR corporate-action source caveat: [IBKR corporate actions](https://www.interactivebrokers.com/en/general/corporate-actions.php).
- NYSE session/calendar reference: [NYSE hours and calendars](https://www.nyse.com/trade/hours-calendars).
- UK SDRT/stamp duty example for tax model sensitivity: [GOV.UK tax when buying shares](https://www.gov.uk/tax-buy-shares).

MIT AUDIT DONE: docs/CCAgentWorkSpace/MIT/workspace/reports/2026-06-29--ibkr_stock_etf_plan_mit_review.md
