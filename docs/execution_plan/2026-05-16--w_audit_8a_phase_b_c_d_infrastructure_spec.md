# W-AUDIT-8a Phase B/C/D Alpha Surface Infrastructure Spec v0.1

Date: 2026-05-16  
Owner: PA(default), Workgroup A-3 / W-AUDIT-8a  
Status: v0.1 planning spec, implementation not authorized by this document  
Scope boundary: documentation/spec only. This task does not edit Rust, SQL schemas, panel schemas, writer code, runtime wiring, TODO, CLAUDE, or shared PA memory.

## 1. Executive Verdict

W-AUDIT-8a Phase A and the first Phase B implementation slice have already landed in source. The remaining infrastructure work is no longer "create AlphaSurface" or "create Tier 2 panel tables"; it is the controlled completion of the source -> writer -> consumer -> healthcheck loop across Tier 2, Tier 3, and Tier 4, under the post-2026-05-15 canary governance model.

Current Phase B is partially complete:

- `AlphaSurface` exists in `rust/openclaw_core/src/alpha_surface.rs`.
- `panel_aggregator` exists in `rust/openclaw_engine/src/panel_aggregator/`.
- Funding and OI panel persistence exist through `panel.funding_rates_panel`, `panel.oi_delta_panel`, and panel continuous aggregates.
- Dispatch already injects funding and OI snapshots into `AlphaSurface` in `tick_pipeline/on_tick/step_4_5_dispatch.rs`.
- `bb_breakout` consumes OI panel data fail-closed through `oi_panel_delta_5m_pct`.
- Funding panel has producer/writer/slot plumbing, but does not yet have a production strategy consumer with promotion authority. W-AUDIT-8b Stage 0R is the intended first read-only consumer path.

Phase C and Phase D must not be treated as single-feature wiring tasks. Each new alpha source needs a complete infrastructure chain:

1. Schema or explicit existing-storage contract.
2. Writer/producer with source-tier semantics and bounded fanout.
3. Consumer contract in `AlphaSurface` with fail-closed missing/stale behavior.
4. Healthcheck and promotion evidence that cannot be bypassed by demo/paper success.

## 2. Source Baseline Inspected

This spec is based on the initial A-3 dispatch source at local `main` aligned with `origin/main` commit `abaa4de7`, plus the recent Phase B implementation commits referenced by TODO. PM C-1 later advanced `origin/main` to `197ca14d` with an E3 doc-only grep guard; that checkpoint does not alter the AlphaSurface implementation baseline.

- `0b76a4db`: funding curve aggregator, V085 writer, first Phase B funding slice.
- `3d0ea347`: OI delta aggregator, V087, BTC lead-lag, database writer/lib gap closure.
- `ddf0cebe`: Bybit WS subscription/main loop integration, V092 continuous aggregates, healthcheck `[66]`.

Primary current-source anchors:

- `rust/openclaw_core/src/alpha_surface.rs`
- `rust/openclaw_engine/src/panel_aggregator/mod.rs`
- `rust/openclaw_engine/src/panel_aggregator/funding_curve.rs`
- `rust/openclaw_engine/src/panel_aggregator/oi_delta.rs`
- `rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs`
- `rust/openclaw_engine/src/strategies/bb_breakout/mod.rs`
- `rust/openclaw_engine/src/ipc_server/slots.rs`
- `helper_scripts/db/passive_wait_healthcheck/checks_derived_ml_hygiene.py`
- `helper_scripts/db/passive_wait_healthcheck/runner.py`
- `sql/migrations/V085__panel_funding_curve.sql`
- `sql/migrations/V087__panel_oi_delta_panel.sql`
- `sql/migrations/V092__panel_continuous_aggregates.sql`

Governance anchors:

- `docs/execution_plan/2026-05-09--w_audit_8a_alpha_surface_foundation_spec.md`
- `docs/execution_plan/2026-05-10--w_audit_8a_phase_b_tier_2_collector_spec.md`
- `docs/execution_plan/2026-05-15--w_audit_8a_c1_liquidation_topic_probe_plan.md`
- `docs/execution_plan/2026-05-15--w_audit_8b_funding_skew_directional_spec.md`
- `docs/adr/0021-alpha-source-architecture-upgrade.md`
- `docs/architecture/2026-05-10--ARCH-04-graduated-canary-5-stage.md`
- `docs/governance_dev/amendments/2026-05-15--AMD-2026-05-15-01-canary-rebase-replay-preflight-demo-micro-canary.md`
- `CLAUDE.md` AlphaSurface section
- `TODO.md` W-AUDIT-8a / W-AUDIT-8b rows

## 3. Hard Non-Goals

This document does not authorize:

- Relanding or editing V085/V087/V092.
- Creating new SQL migrations in this task.
- Adding Tier 3/Tier 4 runtime subscriptions in this task.
- Reintroducing production liquidation topics before C1 proof passes.
- Using paper-mode evidence for promotion.
- Letting a strategy trade on a missing, stale, or non-finite alpha panel.
- Reverting A4-C. A4-C remains tombstoned/diagnostic-only and is not an authority path for AlphaSurface promotion.

## 4. Tier Infrastructure Matrix

Every tier must be tracked as schema + writer + consumer + healthcheck. "Existing schema" means no DDL is required for the next slice unless MIT/OPS requests a migration during a later implementation dispatch.

| Tier | Schema / Storage Contract | Writer / Producer | Consumer Contract | Healthcheck / Promotion Evidence |
| --- | --- | --- | --- | --- |
| Tier 1: TA / OHLCV | Existing market OHLCV and indicator storage. No W-AUDIT-8a schema work. | Existing market data and indicator writers. | Existing strategies consume TA directly; `AlphaSurface::tier1_only` preserves backward-compatible operation. | Existing indicator/data freshness gates remain authoritative. No new Tier 1 healthcheck required by this spec. |
| Tier 2: Funding curve | Existing `panel.funding_rates_panel` from V085 plus V092 continuous aggregates. | `FundingCurveAggregator` consumes Bybit V5 WS ticker funding fields, snapshots slot state, and flushes PG on bounded cadence. | `AlphaSurface.funding_curve` is injected at dispatch. First non-trading/read-only consumer is W-AUDIT-8b Stage 0R; any future trading consumer must fail closed on missing/stale/non-finite data. | `[66] panel.* freshness sentinel` covers table freshness. Roadmap must add consumer evidence: funding panel availability ratio, symbol coverage, source tier, and explicit "no promotion if absent" report fields. |
| Tier 2: OI delta | Existing `panel.oi_delta_panel` from V087 plus V092 continuous aggregates. | `OIDeltaAggregator` consumes WS OI updates with REST cold-start seeding and rolling 5m/15m/1h deltas. | `AlphaSurface.oi_delta_panel` is injected at dispatch. `bb_breakout` already consumes via `oi_panel_delta_5m_pct` and emits unavailable evaluation paths. | `[66]` table freshness plus strategy-path evidence: missing/stale/non-finite reasons must be visible in candidate reports before any OI-dependent promotion. |
| Tier 2: BTC lead-lag | Current source includes BTC lead-lag panel infrastructure from the 3d0ea347 slice. | Existing panel infrastructure where wired; not central to Phase B remaining work. | Consumer use must remain advisory until a strategy declares it and reports source availability. | Same pattern as funding/OI: source availability, freshness, and explicit skip/fail-closed evidence. |
| Tier 3: Orderflow imbalance | Future target: `panel.orderflow_microstructure_panel` or an equivalent MIT-approved schema. Minimum fields: `snapshot_ts_ms`, `symbol`, `queue_imbalance`, `trade_imbalance_60s`, `microprice_bps`, `large_trade_count_60s`, `large_trade_notional_60s`, `source_tier`. No schema change in this task. | Future Rust panel producer from existing `orderbook.50` and public trade events. Must reuse existing WS fanout; no high-rate REST polling. | `AlphaSurface.orderflow` already has an optional field. Strategies may read it only as optional signal input; missing/stale data must skip the alpha branch, not synthesize neutral truth. | New healthcheck required before promotion: freshness by symbol, finite-value scan, orderbook/trade event coverage, and bounded latency from WS event to panel slot. |
| Tier 3: Bid-ask spread dynamics | Prefer to store in the same future microstructure panel unless MIT requests a separate `panel.spread_dynamics_panel`. Minimum fields: `best_bid`, `best_ask`, `spread_bps`, `spread_zscore_5m`, `spread_p95_1h`, `source_tier`. | Future writer derives from ticker/orderbook best bid/ask and rolling spread windows. | Consumer role is execution/risk advisory first: widen slippage, suppress entry during abnormal spread, or mark alpha unavailable. It must not create a standalone buy/sell trigger without Stage 0R evidence. | New healthcheck: non-negative spread, finite z-score, stale-symbol count, p95 spread sanity, and reportable abnormal-spread suppression count. |
| Tier 3: Liquidation pulse | Existing raw storage contract: `market.liquidations` exists, but production rows/topics are dormant. Future pulse can be derived into slot-only state first, with PG persistence only after C1 proof + MIT/BB approval. | No production writer revival until C1 isolated proof passes. Future writer may subscribe to verified Bybit liquidation topic only after `PASS_C1_PROOF_CANDIDATE`; it must parse topic, symbol, side, size, price, and source tier. | `AlphaSurface.liquidation_pulse` is optional and must remain `None` in production until C1 gates pass. No mock/stub pulse is allowed to feed strategy decisions. | Before revival: C1 24h proof report only. After revival: table freshness, non-zero but bounded volume, parser error rate, topic-name audit, and strategy skip count when pulse is absent. |
| Tier 4: Event alerts | Existing raw schema candidate: `market.news_signals` and Scout/news event artifacts. Future `EventAlert` contract maps raw events into normalized active alerts with expiry. | Future provider maps news/scout/event rows into bounded active `EventAlert` list. Writer must preserve source, severity, affected symbols, TTL, and dedupe key. | `AlphaSurface.event_alerts` is a slice. Strategies may suppress or annotate trades from active alerts, but must not bypass normal signal gates on event presence alone. | New healthcheck: source freshness, active-alert expiry correctness, dedupe rate, severity distribution, and stale-alert count. |
| Tier 4: Regime tag | Existing schema candidates: `market.regime_snapshots` and `market.regime_transitions`; existing detector code can inform implementation. | Future `RegimeTagProvider` writes or reads regime snapshots from volatility/trend/chop features. Unknown must be the safe default. | `AlphaSurface.regime` already exists and defaults to `Unknown`. Strategy consumers must define what each regime permits/suppresses and report skip reasons. | New healthcheck: snapshot freshness, `Unknown` ratio, transition churn limit, and consistency with volatility/trend inputs. |
| Tier 4: Sentiment panel | Existing raw schema candidate: `market.news_signals.sentiment`. If persistence is needed, future target is `panel.sentiment_panel` with `snapshot_ts_ms`, `symbol`, `score`, `sample_count`, `positive_count`, `negative_count`, `source_tier`. No schema change in this task. | Future provider aggregates bounded-window sentiment by symbol from approved news/scout inputs. External API cost must be capped by OPS policy. | `AlphaSurface.sentiment` is optional. Consumers must treat absent or low-sample sentiment as unavailable, not zero-confidence confirmation. | New healthcheck: sample count floor, freshness, per-source contribution, stale symbol coverage, cost-budget compliance, and score finite-range validation. |

## 5. Phase B Remaining Work: Funding/OI Consumer Wiring Completeness

Phase B remaining work should be dispatched as a completion sprint, not as a schema sprint.

### B-REM-1 Dispatch Snapshot Contract

Verify that all active `on_tick` dispatch paths construct `AlphaSurface` from slot snapshots without holding locks across strategy execution. Current `step_4_5_dispatch.rs` already clones funding/OI snapshots before dispatch; the remaining work is test and report coverage:

- `funding_curve` slot present and age-reported.
- `oi_delta_panel` slot present and age-reported.
- `try_read` failure is observable and fail-soft.
- Missing panel does not panic and does not create synthetic neutral alpha data.

### B-REM-2 Funding Consumer Completeness

Funding has producer/writer/slot completeness, but not strategy-consumer completeness.

Required next evidence:

- W-AUDIT-8b Stage 0R reports must include funding panel availability ratio, cohort coverage, freshness, and source tier.
- If a future strategy declares `FundingCurve` or funding skew as a required alpha source, it must emit explicit missing/stale/non-finite skip reasons.
- No funding-derived trading promotion is allowed until Stage 0R replay preflight and Demo micro-canary requirements pass under AMD-2026-05-15-01.

### B-REM-3 OI Consumer Completeness

OI has a real consumer path through `bb_breakout`.

Required next evidence:

- Candidate reports must count `oi_panel_unavailable` by reason: absent panel, stale panel, missing symbol, non-finite absolute OI, non-finite delta.
- `enable_oi_signal` must remain fail-closed. If OI is unavailable, the OI-confirmed branch cannot silently degrade into old behavior while still claiming OI evidence.
- OI panel freshness in `[66]` is necessary but insufficient; strategy-path availability must also be reported.

### B-REM-4 Healthcheck Operational Closure

`[66] panel.* freshness sentinel` is registered in the passive health runner. The shell cron helper exists separately. The roadmap must decide whether cron installation is required operationally or whether passive runner registration is the only authoritative health path.

No runtime change is authorized here. The next implementation owner should produce either:

- a no-op ops note that passive runner `[66]` is sufficient, or
- an OPS-approved cron/systemd install task with explicit rollback.

### B-REM-5 Source-Tier and Cohort Semantics

Tier 2 reports must distinguish:

- WS-first live source.
- REST cold-start seed.
- missing symbol due to cohort exclusion.
- unavailable due to stale panel.

This prevents consumer code from treating a seeded or partial panel as equivalent to fully live evidence.

## 6. Phase C Microstructure Infrastructure

Phase C should be split into two independent surfaces:

1. C1 liquidation revival, governed by the existing C1 proof plan.
2. C2 orderflow/spread microstructure, governed by a new producer + consumer + healthcheck plan.

### C1 Liquidation Pulse

Current governance state:

- Production liquidation subscriptions remain disabled.
- `AlphaSurface.liquidation_pulse` must remain `None` unless C1 proof passes.
- `market.liquidations` existing table does not by itself authorize a writer or strategy consumer.

Required implementation sequence after C1 proof:

1. Verify 24h isolated topic proof report and PM/MIT/BB sign-off.
2. Add parser/writer for the exact verified Bybit topic name.
3. Produce rolling in-memory `LiquidationPulse` with source tier and age.
4. Wire optional `AlphaSurface.liquidation_pulse`.
5. Add healthcheck for topic freshness, row volume, parse errors, and symbol coverage.
6. Only then allow Stage 0R replay and Demo micro-canary planning.

### C2 Orderflow Imbalance

Target source inputs:

- Bybit `orderbook.50` top levels already present in event schemas.
- Public trade events with side/quantity when available.
- Existing fanout path, not new REST polling.

Target panel fields:

- queue imbalance from top-N bid/ask quantity.
- trade imbalance over 60s and 300s windows.
- large-trade count/notional over 60s.
- microprice deviation in bps.
- source tier, symbol, snapshot timestamp.

Consumer rules:

- `AlphaSurface.orderflow` remains optional.
- Strategies must declare orderflow source need before using it.
- Missing/stale orderflow skips only the dependent alpha branch.
- No orderflow-only strategy promotion before Stage 0R replay preflight.

Healthcheck rules:

- per-symbol freshness.
- finite feature scan.
- event coverage by symbol.
- latency from WS event to panel slot.
- memory/window bound check.

### C3 Bid-Ask Spread Dynamics

Spread dynamics may share the same microstructure panel as orderflow. The first implementation should avoid creating a second panel unless MIT requires isolated retention or access patterns.

Target fields:

- best bid and best ask.
- instantaneous spread bps.
- rolling spread z-score.
- p95/p99 spread by symbol over 1h.
- abnormal-spread boolean for consumer suppression.

Consumer rules:

- First use is advisory/risk suppressor, not directional alpha.
- Strategies may widen slippage or suppress entry during abnormal spread.
- Reports must show how often spread logic changed a decision.

Healthcheck rules:

- spread must be non-negative.
- best bid/ask must be finite.
- z-score must be finite or explicitly unavailable during warmup.
- abnormal-spread rate must be bounded and explainable.

## 7. Phase D Information Flow Infrastructure

Phase D should not begin by giving strategies unconstrained access to raw news or scout artifacts. It should build normalized, bounded, auditable `AlphaSurface` providers.

### D1 Event Alerts

Target inputs:

- `market.news_signals`.
- Scout/event artifacts if PM approves the bridge.

Provider contract:

- Normalize to `EventAlert` with source, affected symbols, severity, TTL, and dedupe key.
- Expire alerts deterministically.
- Cap active alerts per symbol and globally.

Consumer rules:

- Event alerts can suppress, annotate, or require extra confirmation.
- Event alerts cannot bypass normal signal gates or risk controls.
- Strategy reports must attribute suppressions to alert id/source/severity.

Healthcheck:

- stale active alerts.
- dedupe rate.
- source freshness.
- symbol mapping coverage.
- severity distribution drift.

### D2 Regime Tag

Target inputs:

- Existing regime snapshot/transition tables.
- Existing volatility/trend/chop detectors.
- Indicator-derived fallback only if explicitly approved.

Provider contract:

- Default to `RegimeTag::Unknown`.
- Emit source age and confidence internally even if `RegimeTag` remains compact.
- Bound transition churn to avoid per-tick regime flapping.

Consumer rules:

- Strategy-specific regime policy must be explicit.
- Unknown is not bullish, bearish, or neutral confirmation; it is unavailable.
- Reports must count regime-based suppressions and unknown-ratio.

Healthcheck:

- snapshot age.
- unknown-ratio threshold.
- transition churn threshold.
- consistency with volatility/trend features.

### D3 Sentiment Panel

Target inputs:

- Existing `market.news_signals.sentiment`.
- Approved bounded-cost external sentiment sources only after OPS budget review.

Provider contract:

- Aggregate by symbol and time window.
- Preserve source contribution and sample count.
- Treat low-sample windows as unavailable.

Consumer rules:

- Sentiment is optional and cannot override risk gates.
- Missing or low-sample sentiment must be a skip/unavailable reason.
- Any sentiment-confirmed strategy must report sample count and source mix.

Healthcheck:

- score finite range.
- sample count floor.
- per-source contribution.
- freshness by symbol.
- external API cost and rate budget.

## 8. Sprint Allocation: N+3 / N+4 / N+5

| Sprint | Phase Mapping | Authorized Work Shape | Exit Evidence |
| --- | --- | --- | --- |
| N+3 | Phase B completion + Phase C1 proof review + Phase C2/C3 design lock | Close funding/OI consumer evidence gaps; review C1 proof candidate; produce MIT-ready microstructure schema/writer/consumer/healthcheck design. If C1 proof passes, dispatch liquidation parser/writer as W-AUDIT-8c implementation. | `[66]` panel health evidence; funding/OI consumer availability report; C1 PASS/FAIL decision; no production liquidation topic unless PASS; microstructure design accepted. |
| N+4 | Phase C implementation + Phase D schema contract | Implement orderflow/spread panel only after MIT approval; wire optional `AlphaSurface.orderflow`; add microstructure healthcheck; continue W-AUDIT-8b only if Stage 0R evidence is green. Define EventAlert/Regime/Sentiment provider contracts. | Microstructure panel freshness/finite checks; strategy skip reasons; no promotion without Stage 0R; Phase D contract review signed. |
| N+5 | Phase D implementation + staged canary preparation | Implement EventAlert, RegimeTag, and Sentiment providers with healthchecks; connect strategy consumers as optional/fail-closed; prepare first supervised Demo micro-canary only after Stage 0R replay preflight passes. | Event/regime/sentiment healthchecks; consumer suppression/skip reports; Stage 0R replay packet; Demo micro-canary packet if green. |

## 9. Promotion and Canary Rules

ARCH-04 established that new alpha sources must pass graduated evidence before live use. AMD-2026-05-15-01 rebases that model:

- Stage 0R replay preflight is the current pre-demo promotion gate.
- Stage 1 is Demo micro-canary, not paper-mode evidence.
- Paper-mode success is not promotion evidence.
- Each alpha source must expose missing/stale/non-finite reasons.
- A source can be present in `AlphaSurface` and still be unauthorized for trading promotion.

For W-AUDIT-8a Phase B/C/D, this means:

- Producer freshness does not equal consumer readiness.
- Consumer readiness does not equal strategy promotion.
- Strategy demo performance does not equal live/supervised approval.
- Any source with no healthcheck is infrastructure-incomplete.

## 10. Acceptance Criteria

The Phase B/C/D infrastructure track is complete only when all of the following are true:

1. Tier 2 funding and OI have explicit consumer-path evidence, not only table freshness.
2. Funding-derived strategies remain read-only or Stage 0R-only until governance gates pass.
3. OI-dependent `bb_breakout` reports unavailable reasons and never silently treats missing OI as confirmation.
4. Liquidation pulse remains disabled until C1 isolated proof passes.
5. Orderflow/spread microstructure has an accepted schema/storage contract before implementation.
6. Tier 3 orderflow/spread has producer, consumer, and healthcheck before any Stage 0R claim.
7. Tier 4 event/regime/sentiment providers normalize raw inputs before strategy consumption.
8. Every Tier 4 consumer path reports suppressions/skips and treats `Unknown` or low-sample state as unavailable.
9. No alpha source can be promoted without Stage 0R replay preflight and Demo micro-canary evidence under AMD-2026-05-15-01.
10. All reports explicitly list schema, writer, consumer, and healthcheck status per alpha source.

## 11. Open Assumptions for PM/MIT

1. V085/V087/V092 are considered applied/landed for current planning; this spec does not revalidate database state directly.
2. `[66]` passive-runner registration is the authoritative current health path unless OPS explicitly requests cron/systemd installation.
3. Tier 3 orderflow and spread should share one microstructure panel unless MIT requests separate retention or query patterns.
4. Tier 4 sentiment can start from existing `market.news_signals.sentiment`; a new `panel.sentiment_panel` should be deferred until persistence/query requirements are proven.
5. No production liquidation topic may be restored from historical assumptions; only the C1 proof plan can authorize the exact topic and parser path.
