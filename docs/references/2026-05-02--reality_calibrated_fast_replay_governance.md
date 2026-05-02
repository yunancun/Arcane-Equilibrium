# REF-19 — Reality-Calibrated Fast Replay Governance

**Date:** 2026-05-02
**Status:** Draft governance contract; implementation must not start until PM/operator accepts this boundary.
**Owner:** PM
**Related:** DOC-01 §5.3 / §5.7 / §5.8 / §5.10, REF-03, REF-04, REF-05, V031, V032, V034

---

## 1. Purpose

Reality-Calibrated Fast Replay is a new research and development plane for OpenClaw.
Its job is to compress historical market experiments into minutes, while staying honest
about the gap between historical replay and real exchange execution.

Reality-Calibrated Fast Replay is not a replacement for demo, LiveDemo, GovernanceHub,
Decision Lease, or the live gates. It is an experiment environment that helps the
operator and agents reject bad parameter sets quickly and select a small number of
candidates for bounded demo validation.

Reality-Calibrated Fast Replay may call MLDE, DreamEngine, OpportunityTracker, and
LinUCB/ML shadow components. It must not redefine those components as replay-only tools.
Their primary mission remains agent self-learning, strategy repair, and bounded strategy /
risk parameter evolution.

---

## 2. Non-Negotiable Boundaries

1. Replay is a research plane. It must never submit live orders.
2. Replay outputs are advisory unless explicitly promoted through existing governance.
3. ML/Dream output is not an execution command.
4. Synthetic or calibrated replay rows must never be mixed into real fill labels without
   explicit source tagging.
5. `learning.mlde_edge_training_rows` remains a real-outcome training view unless a future
   migration adds an explicitly separate replay-labeled view.
6. Demo parameter changes from replay-derived recommendations must remain bounded, audited,
   and reversible through the existing MLDE demo applier contract.
7. Live/live_demo parameter mutation requires GovernanceHub review, Decision Lease, and the
   existing live authorization gates.
8. Replay cannot weaken H0, Guardian, risk config, exchange disaster protection, or account
   survival rules.
9. Replay must report uncertainty. A single point estimate is insufficient.
10. Every replay result must be reproducible from a manifest.

---

## 3. System Role Boundaries

| Component | Responsibility | Must Not Do |
|---|---|---|
| Reality-Calibrated Replay Orchestrator | Build experiment manifest, load historical market data, run Rust same-source replay, call execution calibration and advisory producers, write reports | Mutate live/demo params directly; become a strategy authority |
| Rust `TickPipeline` | Recompute indicators, signals, scanner context, intents, and risk/verdict behavior from historical events | Special-case replay-only strategy behavior unless explicitly versioned |
| Execution Simulator | Estimate maker fills, taker slippage, fees, latency, timeout, reject probability | Claim simulated fills are real fills |
| MLDE / ML Shadow | Rank/veto candidates, estimate expected post-fee edge and uncertainty | Become replay-only; bypass advisory/governance tables |
| DreamEngine | Explore parameter hypotheses over replay windows and produce parameter proposals | Directly apply params; become a general backtest engine |
| OpportunityTracker | Estimate regret/dodged-loss from skipped/rejected opportunities | Treat gate rejection count as regret without outcome evidence |
| Demo Applier | Apply bounded demo-only changes through Rust IPC, with audit rows | Apply live/live_demo changes |
| GovernanceHub | Review live candidates and enforce lease/governance boundaries | Treat replay metrics as sufficient live approval |
| Operator | Accept governance changes and approve live-boundary changes | Use replay report alone as live release evidence |

---

## 4. Data Source Tiers

Replay reliability depends on the market data tier. Every report must state which tier was used.

| Tier | Source | Expected Use | Reliability |
|---|---|---|---|
| S0 | Real demo/live_demo fills, orders, verdicts, snapshots | Calibration and validation labels | Highest for observed behavior |
| S1 | Locally recorded L1/L50 orderbook + trades + ticker/funding/OI | Future high-fidelity maker simulation | High after recorder is stable |
| S2 | Bybit public klines, trades, funding, OI | Low-cost historical replay and signal sweeps | Medium |
| S3 | OHLC-derived synthetic ticks | Strategy signal smoke tests only | Low for execution |
| S4 | Paid historical L2 data, if approved | Deep maker queue/backfill calibration | High, but cost-gated |

Default cost posture: use S0 + S2 first, start collecting S1 immediately, and postpone S4 until the operator approves a specific paid-data scope.

---

## 5. Required Experiment Manifest

Every replay run must have a manifest. The manifest is the reproducibility contract.

Required fields:

```yaml
schema_version: replay_manifest_v1
experiment_id: <stable id>
created_at: <UTC timestamp>
operator_or_agent: <actor>
git_sha: <repo sha>
engine_binary_sha: <if available>
strategy_config_sha256: <hash>
risk_config_sha256: <hash>
market_data:
  tier: S0|S1|S2|S3|S4
  source: bybit_public|local_recorded|paid_l2|synthetic
  symbols: [...]
  start_ts: <UTC>
  end_ts: <UTC>
  timeframe_or_tick: <details>
execution_model:
  version: <model version>
  calibrated_from_start_ts: <UTC>
  calibrated_from_end_ts: <UTC>
  source_modes: [demo, live_demo]
candidate_params:
  strategy_params: <hash or inline patch>
  risk_params: <hash or inline patch>
output_policy:
  write_shadow_recommendations: true|false
  allow_demo_candidate: true|false
  allow_live_candidate: false
```

No manifest means no replay result may be used for MLDE recommendation, demo patching, or governance review.

---

## 6. Source Tagging Contract

All rows and reports produced by replay must carry source tags.

Required source tags:

| Tag | Meaning |
|---|---|
| `real_fill` | A real demo/live_demo/live fill from exchange or runtime DB |
| `calibrated_replay` | A simulated fill produced by an execution model calibrated from real fills |
| `synthetic_replay` | A simulated fill or tick produced from OHLC or other synthetic reconstruction |
| `counterfactual_replay` | A recalculated outcome using a real observed trade as the anchor |
| `dream_parameter_proposal` | A DreamEngine advisory parameter hypothesis |
| `ml_shadow_rank` | MLDE rank recommendation |
| `ml_shadow_veto` | MLDE veto recommendation |

Reports must include a source mix table. Any aggregate that mixes sources must expose the mix explicitly.

---

## 7. Execution Calibration Contract

The execution model is separate from the strategy replay. It must estimate exchange realism rather than assume immediate paper fills.

Minimum model outputs:

1. `maker_fill_probability`
2. `maker_timeout_probability`
3. `maker_expected_latency_ms`
4. `maker_adverse_selection_bps`
5. `taker_slippage_q10_bps`
6. `taker_slippage_q50_bps`
7. `taker_slippage_q90_bps`
8. `reject_probability`
9. `fee_rate_maker`
10. `fee_rate_taker`

Calibration features should include, when available:

- symbol
- strategy
- side
- order type
- liquidity role
- maker offset bps
- maker timeout ms
- spread bps
- turnover / volume
- volatility / ATR
- funding rate
- open interest
- scanner regime / route mode
- time of day
- recent reject/timeout state

Calibration acceptance:

- The model must publish sample count and calibration window.
- Low-sample cells must be shrunk or marked insufficient.
- Reports must show calibrated / pessimistic / optimistic outcomes.
- If calibration is stale, replay may run but cannot emit actionable recommendations.

---

## 8. MLDE and DreamEngine Usage Boundary

Reality-Calibrated Fast Replay may call MLDE and DreamEngine in three ways.

### 8.1 ML Execution Calibration

ML may train or update execution-reality estimators from S0 real fills and orders.
These estimators feed replay simulation and report uncertainty.

This does not change MLDE's primary role. The same calibration outputs may also help live agent self-awareness, cost-edge analysis, and future strategy/risk tuning.

### 8.2 Dream Parameter Exploration

DreamEngine may run parameter exploration on replay windows. It should produce parameter proposals, not approvals.

DreamEngine outputs must remain compatible with the general advisory contract:

- `source = dream_engine`
- `recommendation_type = parameter_proposal`
- `expected_net_bps`
- `confidence`
- `sample_count`
- `payload.policy = read_only_parameter_proposal`
- `payload.replay_experiment_id` when derived from replay

DreamEngine must remain a general self-learning component for agents. Replay is one experiment environment, not its only purpose.

### 8.3 MLDE Rank/Veto

MLDE may rank or veto replay-generated candidates. It must include:

- expected post-fee edge
- q10 or pessimistic downside
- confidence
- sample count
- data source tier
- attribution quality
- calibration freshness

MLDE recommendations remain advisory unless consumed by the existing demo applier or GovernanceHub review flow.

---

## 9. Report Acceptance Metrics

A replay report must include at least:

| Metric | Required |
|---|---|
| gross PnL / bps | Yes |
| net bps after fee | Yes |
| q10 / q50 / q90 net bps | Yes |
| max drawdown | Yes |
| maker fill rate | Yes for maker strategies |
| maker timeout rate | Yes for maker strategies |
| taker slippage distribution | Yes for market close paths |
| reject rate | Yes |
| trade count / sample count | Yes |
| source mix | Yes |
| calibration model version | Yes |
| calibration freshness | Yes |
| attribution-chain quality | Yes |
| regime breakdown | Yes |
| symbol breakdown | Yes |
| pass / defer / reject verdict | Yes |

Promotion-oriented reports must include the reason for every verdict.

---

## 10. Candidate Verdict Rules

Replay may produce only these verdicts:

| Verdict | Meaning |
|---|---|
| `reject` | Candidate is worse than baseline or fails safety / data gates |
| `defer_data` | Insufficient sample, stale calibration, or weak attribution |
| `defer_reality` | Signal looks good, but execution model uncertainty is too high |
| `demo_candidate` | Candidate may enter bounded demo A/B |
| `live_candidate_research_only` | Candidate may be logged for GovernanceHub review, but not auto-applied |

Replay must never produce `live_approved`.

Minimum `demo_candidate` gates:

1. calibrated q50 net bps after fee > 0
2. pessimistic q10 does not breach the configured downside threshold
3. maker timeout/reject rates do not degrade beyond threshold
4. source tier is S0/S1/S2, not S3-only
5. calibration is fresh enough
6. attribution-chain quality is above the configured minimum
7. parameter delta is within demo applier bounds

---

## 11. Storage and Table Separation

Initial implementation should avoid schema churn when possible, but any persistent replay result must be separable from real outcomes.

Allowed sinks:

- local JSON/Markdown report under `docs/CCAgentWorkSpace/PM/workspace/reports/`
- `learning.mlde_shadow_recommendations` with explicit replay tags
- future `replay.*` schema for experiment manifests, replay fills, and reports

Disallowed sinks:

- writing replay fills into `trading.fills` as if real
- writing replay rows into `learning.mlde_edge_training_rows` without a new explicit replay source column/view
- mutating live/live_demo configs from replay output

Recommended future schema:

- `replay.experiments`
- `replay.market_data_manifests`
- `replay.execution_model_versions`
- `replay.simulated_fills`
- `replay.candidate_results`
- `replay.report_artifacts`

---

## 12. Healthcheck Requirements

Before replay output can feed demo candidates, add healthchecks for:

1. `replay_manifest_contract` — every run has a valid manifest.
2. `replay_source_mix` — reports expose real/calibrated/synthetic proportions.
3. `execution_calibration_freshness` — calibration window and samples are fresh enough.
4. `execution_calibration_power` — low-sample cells are not treated as high confidence.
5. `replay_no_live_mutation` — replay path cannot write live/live_demo params.
6. `replay_shadow_sink_boundary` — replay-derived MLDE rows are advisory and tagged.
7. `replay_report_reproducibility` — report references git SHA, config hashes, and model version.

Any healthcheck FAIL blocks promotion to demo candidate.

---

## 13. Implementation Sequence

### Phase R0 — Governance First

- Land this document.
- Register it as REF-19.
- No runtime behavior change.

### Phase R1 — Read-Only Replay MVP

- Add a standalone replay runner.
- Load historical Bybit data and generate `PriceEvent` stream.
- Run Rust `TickPipeline` in replay mode with selected strategy/risk configs.
- Emit manifest and report.
- Do not write recommendations.

### Phase R2 — Execution Calibration

- Train/calibrate maker fill, slippage, reject, and timeout models from real demo/live_demo data.
- Add calibrated / pessimistic / optimistic result bands.
- Add healthchecks.

### Phase R3 — MLDE/Dream Advisory Integration

- Allow replay to call DreamEngine for parameter proposals.
- Allow MLDE to rank/veto replay candidates.
- Write advisory rows only with explicit replay source tags.

### Phase R4 — Bounded Demo A/B Candidate Flow

- Permit `demo_candidate` output to be consumed by MLDE demo applier.
- Enforce existing bounded delta, dedupe, rollback, and audit rules.

### Phase R5 — GovernanceHub Live Candidate Review

- Permit high-confidence demo-validated candidates to become live research candidates.
- GovernanceHub review remains mandatory.
- Decision Lease and live gates remain mandatory.

---

## 14. Cost Policy

Default path:

1. Use existing runtime DB and real demo/live_demo fills.
2. Use Bybit public historical data.
3. Start collecting local orderbook data for future replay.
4. Avoid paid data until the free path shows the execution model is limited by missing L2 history.

Paid historical L2 data requires an operator decision specifying:

- vendor
- symbol list
- time range
- expected cost
- acceptance question
- expiry date for using the dataset

---

## 15. Review Chain

Implementation work following this document is a feature / quant / data hybrid and must use:

- PM triage
- PA design check
- QC strategy/math review
- MIT data/schema review
- E1 implementation
- E2 adversarial code review
- E4 regression and targeted replay tests
- QA acceptance if GUI/operator workflow is added
- PM sign-off

Roles may be skipped only with explicit PM rationale, but E2 and E4 are mandatory.

---

## 16. Operator-Facing Summary

Reality-Calibrated Fast Replay is a high-speed experiment environment. It calls MLDE
and DreamEngine, but does not redefine them. MLDE and DreamEngine remain general
agent-learning components for strategy repair, risk tuning, and self-improvement.

Replay can say:

- this parameter set is not worth demo time
- this parameter set deserves a bounded demo A/B
- this candidate should be logged for future governance review

Replay cannot say:

- this is live-approved
- synthetic PnL is real PnL
- ML/Dream output is an order
- paper fill assumptions are exchange truth

