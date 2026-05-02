# REF-20 - Paper Replay Lab and Learning Surface Design

**Date:** 2026-05-02
**Status:** Draft design contract; implementation must follow REF-19 boundaries.
**Owner:** PM
**Related:** REF-19, REF-03, REF-04, REF-18, DOC-01 §5.3 / §5.7 / §5.8 / §5.10

---

## 1. Purpose

REF-19 defines the governance boundary for Reality-Calibrated Fast Replay. REF-20
defines where that capability belongs in the existing product surfaces and how it
should connect to Learning, MLDE, DreamEngine, and the current 5-Agent monitor.

The immediate developer pain is clear: every strategy or parameter edit currently
requires waiting for new paper/demo data. Paper Replay Lab must reduce that loop
from hours or days to minutes by replaying historical market conditions through
the closest available runtime path, while still reporting execution uncertainty,
fees, data source tier, and calibration freshness.

This design does not replace paper/demo validation. It creates a fast reject and
candidate-selection layer before bounded demo A/B validation.

---

## 2. Current System Findings

### 2.1 Paper Tab

Current Paper Tab files:

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/tab-paper.html`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/app-paper.js`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/paper_trading_routes.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/paper_trading_metrics.py`

Observed role:

- Paper Tab is already a simulated non-live surface.
- The Python paper engine has been retired; the Rust engine is the sole paper
  trading engine behind the session routes.
- Paper API responses are explicitly simulated (`is_simulated=true`,
  `data_category=paper_simulated`).
- The surface already shows session state, balances, PnL, positions, active orders,
  fills, metrics, and shadow decisions.

Conclusion: Paper Tab is the correct surface to evolve into Paper Replay Lab. Live
Tab must not be used for replay.

### 2.2 Learning Tab

Current Learning files:

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/tab-learning.html`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/app-learning.js`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/learning_legacy_routes.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/learning_ops.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/learning_queries.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/learning_records.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/learning_auto_pipeline.py`

Observed role:

- Learning Tab is a knowledge cockpit: observations, lessons, hypotheses,
  experiments, review queue, and net PnL summaries.
- The auto pipeline produces review packets first; durable records require
  operator approval.
- `learning_ops.py` is now a compatibility facade. New code should import the
  narrower child modules directly.

Conclusion: Learning Tab should remain the durable learning and review cockpit.
It should consume replay evidence and monitor ML/Dream producers. It should not
become the replay runner.

### 2.3 5-Agent Monitor

Current 5-Agent files:

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/js/agent-tracker.js`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/agents_routes.py`

Observed role:

- 5-Agent is embedded inside Learning Tab today.
- Its backend routes are read-only and intentionally degrade instead of failing
  the operator console during PostgreSQL outages.
- The panel tracks agent roster, recent activity, cost, demo/shadow summaries,
  governance rejects, leases, and budget.
- This is operational monitoring, not durable learning content.

Conclusion: 5-Agent should be extracted from Learning into a separate Agents
Monitor surface. The functionality should be preserved; only the product boundary
should change.

### 2.4 MLDE and DreamEngine

Relevant files:

- `program_code/local_model_tools/dream_engine.py`
- `program_code/local_model_tools/opportunity_tracker.py`
- `program_code/local_model_tools/cognitive_modulator.py`
- `program_code/ml_training/mlde_shadow_advisor.py`
- `program_code/ml_training/mlde_demo_applier.py`
- `program_code/ml_training/linucb_trainer.py`
- `program_code/ml_training/calibration.py`
- `program_code/ml_training/model_registry.py`

Observed role:

- DreamEngine writes advisory parameter proposals to
  `learning.mlde_shadow_recommendations`.
- MLDE Shadow ranks/vetoes candidates and writes advisory recommendations.
- OpportunityTracker produces regret summaries only when outcome evidence is
  available.
- Demo Applier may apply bounded demo-only changes through the existing audited
  pathway.
- `learning.mlde_edge_training_rows` is a real-outcome training view.

Conclusion: ML/Dream should be called by replay and monitored from Learning, but
they must not be rewritten into replay-only modules.

### 2.5 Existing Replay Primitives

Relevant files:

- `program_code/local_model_tools/backtest_engine.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/backtest_routes.py`
- `rust/openclaw_core/src/backtest.rs`
- `rust/openclaw_engine/src/startup/mod.rs`
- `rust/openclaw_engine/src/tick_pipeline/commands.rs`
- `rust/openclaw_types/src/price.rs`
- `rust/openclaw_engine/src/paper_state/fill_engine.rs`
- `helper_scripts/canary/replay_runner.py`

Observed role:

- Python `BacktestEngine` is a stub. It is not the canonical replay path.
- Rust `openclaw_core::backtest` provides a bar-level backtest engine, but it is
  not the same full runtime path as `TickPipeline`.
- Rust engine startup already has replay mode (`--replay-mode`, `--replay-input`,
  `--replay-output`) that feeds historical `PriceEvent` rows into `TickPipeline`.
- The current canary replay runner can synthesize OHLC ticks from Bybit klines.
  This is useful for smoke tests, but execution realism is low unless upgraded
  with calibrated fills and better market data.

Conclusion: Paper Replay Lab should build on Rust same-path replay first, not the
legacy Python backtest route. The paper fill engine may be reused for account and
order lifecycle, but execution realism requires a separate calibrated fill model.

---

## 3. Product Surface Decision

| Surface | Target Role | Decision |
|---|---|---|
| Paper Tab | Paper Replay Lab: current paper session plus fast replay, comparisons, reports, candidate handoff | Upgrade in place |
| Learning Tab | Learning Cockpit: durable records, review queue, replay evidence inbox, ML/Dream producer monitor | Keep separate from replay runner |
| 5-Agent Panel | Agents Monitor: operational health, activity, budget, governance state | Extract out of Learning; do not delete |
| Live Tab | Live/live_demo monitoring and live-grade controls | Leave out of replay |
| GovernanceHub | Review and promotion boundary for live-bound candidates | No automatic approval from replay |

Do not merge Paper Replay Lab and Learning Cockpit into one broad tab. The user
workflows are different:

- Paper Replay Lab answers: "Did this code or parameter patch survive historical
  market conditions under realistic cost/execution assumptions?"
- Learning Cockpit answers: "What has the system learned, what evidence exists,
  and what hypotheses or recommendations require review?"
- Agents Monitor answers: "Are the agents healthy, active, cost-bounded, and
  blocked by governance?"

---

## 4. Target Architecture

```text
Historical Market Data
  S0 real fills/orders/verdicts
  S1 local recorded orderbook/trades
  S2 public klines/trades/funding/OI
  S3 synthetic OHLC ticks
        |
        v
Replay Orchestrator
  manifest + config hashes + git sha
        |
        v
Rust same-path replay through TickPipeline
        |
        v
Execution Reality Model
  fees + maker fill probability + timeout + latency + slippage bands
        |
        v
Replay Report
  q10/q50/q90 net bps + drawdown + source mix + calibration health
        |
        +--> Paper Replay Lab UI
        +--> Learning evidence/review queue
        +--> MLDE/Dream advisory calls, when enabled
        +--> Demo candidate handoff, only through existing bounded applier
```

The replay orchestrator is an experiment coordinator, not a strategy authority.
The strategy/risk behavior must come from the same runtime configuration and Rust
pipeline used by paper/demo/live paths wherever possible.

---

## 5. Paper Replay Lab Requirements

Paper Tab should be reorganized into four work areas:

1. Current Paper Session
   - Preserve existing session control, PnL, positions, orders, fills, and metrics.
   - Keep clear simulated data labeling.

2. Fast Replay
   - Create a replay manifest from selected symbols, date range, data tier, current
     git/config hashes, and candidate parameter patch.
   - Start, cancel, and inspect replay runs.
   - Show data tier and execution calibration freshness before run start.

3. Run Compare
   - Compare candidate vs baseline under the same data window.
   - Show gross bps, net bps after fees, q10/q50/q90, max drawdown, trade count,
     maker fill/timeout rate, taker slippage bands, reject rate, and source mix.
   - Require baseline comparison for any `demo_candidate`.

4. Candidate Handoff
   - Allow only advisory handoff:
     - write source-tagged replay report
     - create Learning review evidence
     - optionally write MLDE/Dream advisory recommendation
     - optionally submit `demo_candidate` to existing bounded demo applier
   - Never allow direct live/live_demo mutation.

Paper Replay Lab must not expose a manual order submission path as part of replay.

---

## 6. Learning Cockpit Requirements

Learning should remain the cockpit for durable knowledge. It should add two
replay-related areas without becoming the replay runner.

### 6.1 Replay Evidence Inbox

Replay outputs may enter Learning only as tagged evidence:

- `experiment_id`
- `manifest_hash`
- `git_sha`
- `strategy_config_sha256`
- `risk_config_sha256`
- `source_tier`
- `source_mix`
- `calibration_model_version`
- `calibration_freshness`
- `verdict`
- `baseline_delta`
- `report_uri`

Evidence must land in a review queue or future `learning.replay_evidence` table.
It must not be inserted into `learning.mlde_edge_training_rows` as if it were a
real outcome.

### 6.2 ML/Dream Producer Monitor

Learning should show producer health for:

- MLDE Shadow Advisor
- DreamEngine
- OpportunityTracker
- LinUCB trainer
- Model Registry
- Calibration jobs
- MLDE Demo Applier

Minimum monitor fields:

- last run timestamp
- last successful run timestamp
- sample count
- input source view/table
- output table
- stale/degraded reason
- latest recommendation count
- latest applied demo-only count
- latest blocked-by-governance count

This monitor is read-only. It helps the operator understand whether ML/Dream is
learning and proposing, not whether replay should auto-apply.

---

## 7. 5-Agent Extraction Requirements

The current 5-Agent monitor should be moved out of Learning into an Agents Monitor
tab or equivalent top-level monitor.

Rules:

1. Preserve the existing read-only route posture in `agents_routes.py`.
2. Preserve degraded responses on data outages.
3. Preserve the current `agent-tracker.js` behavior where possible, but mount it
   outside Learning.
4. Remove 5-Agent visual weight from Learning after the new surface exists.
5. Do not delete 5-Agent functionality unless a later governance decision retires
   the agent model itself.

Rationale: 5-Agent health, cost, activity, rejects, and leases are operational
runtime signals. They are not observations, lessons, hypotheses, or experiments.

---

## 8. API and Storage Design

New replay routes should be introduced instead of expanding legacy
`backtest_routes.py`.

Suggested route family:

| Route | Method | Purpose |
|---|---|---|
| `/api/v1/replay/health` | GET | Replay subsystem readiness, calibration freshness, data source availability |
| `/api/v1/replay/manifests` | POST | Create manifest only; no execution side effects |
| `/api/v1/replay/runs` | POST | Start run from manifest id/hash |
| `/api/v1/replay/runs/{id}` | GET | Run status, progress, data tier, degraded reason |
| `/api/v1/replay/runs/{id}/cancel` | POST | Cancel run |
| `/api/v1/replay/reports/{id}` | GET | Report summary and links |
| `/api/v1/replay/compare` | POST | Compare baseline vs candidate reports |
| `/api/v1/replay/candidates` | POST | Advisory candidate handoff; never live approval |

Storage posture:

- Phase 1 may store manifests/reports locally under a repo-ignored runtime
  directory.
- Durable DB storage may later use a separate `replay.*` schema.
- Replay rows must never be written to `trading.fills`.
- Replay labels must never be mixed into `learning.mlde_edge_training_rows`.
- Any MLDE advisory row derived from replay must carry `payload.replay_experiment_id`,
  `payload.source_tier`, and `payload.manifest_hash`.

---

## 9. Execution Realism Requirements

Paper Replay Lab must be more realistic than the current paper fill assumption.
The execution model is separate from strategy replay.

Minimum modeled costs:

- maker fee rate
- taker fee rate
- maker fill probability
- maker timeout probability
- maker latency
- maker adverse selection
- taker slippage q10/q50/q90
- reject probability

Minimum reporting:

- calibrated case
- pessimistic case
- optimistic case
- insufficient-calibration warning
- data source tier warning
- source mix table

Fee handling must be practical. For Bybit demo/live_demo parity work, the default
fee model should use configured maker/taker rates and report the exact rates used.

---

## 10. Phased Delivery

### P0 - Design and Governance

- Add REF-20 and Chinese companion.
- Register REF-20 in the specification register and docs index.
- No runtime changes.

### P1 - Paper Tab Information Architecture

- Rename/reorganize Paper Tab into Paper Replay Lab.
- Keep current paper session behavior intact.
- Add disabled or read-only placeholders for Fast Replay, Run Compare, and Candidate
  Handoff if backend is not ready.

### P2 - Read-Only Replay MVP

- Introduce `/api/v1/replay/*` routes.
- Use Rust replay mode as the first canonical engine path.
- Produce manifest and report artifacts.
- Support baseline vs candidate comparison.
- Use S2/S3 data only for strategy signal and smoke-test confidence; mark execution
  confidence limited.

### P3 - Execution Calibration

- Train or load execution reality model from S0 real demo/live_demo fills/orders.
- Add fee, fill probability, timeout, latency, slippage, and reject estimates.
- Block actionable recommendations when calibration is stale or underpowered.

### P4 - MLDE/Dream Advisory Integration

- Allow DreamEngine to propose replay candidate parameter patches.
- Allow MLDE to rank/veto replay candidates.
- Write only source-tagged advisory rows.
- Add Learning producer monitor and replay evidence inbox.

### P5 - Agents Monitor Extraction

- Move 5-Agent dashboard out of Learning.
- Keep read-only, degraded-safe route behavior.
- Trim Learning Tab back to learning records, review, replay evidence, and ML/Dream
  producer health.

### P6 - Bounded Demo A/B Handoff

- Allow `demo_candidate` handoff only through the existing MLDE demo applier.
- Require baseline comparison, calibration health, source mix, and replay manifest.
- Keep live/live_demo mutation behind GovernanceHub, Decision Lease, and live gates.

---

## 11. Acceptance Checks

Required checks before any implementation phase is considered complete:

| Check | Requirement |
|---|---|
| `replay_manifest_contract` | Every run has manifest, config hashes, git sha, data tier, and output policy |
| `replay_source_mix` | Every report exposes real/calibrated/synthetic/counterfactual mix |
| `execution_calibration_freshness` | Stale calibration blocks actionable handoff |
| `execution_calibration_power` | Low sample cells are shrunk or marked insufficient |
| `replay_no_live_mutation` | Replay routes cannot mutate live/live_demo configuration or submit live orders |
| `replay_shadow_sink_boundary` | Replay-derived MLDE rows are advisory and source-tagged |
| `replay_report_reproducibility` | Report can be reproduced from manifest and input artifacts |
| `paper_replay_lab_no_trading_submit` | Replay UI exposes no live/manual order submission |
| `learning_producer_monitor_read_only` | Learning producer monitor has no mutation controls |
| `agents_monitor_read_only` | Extracted 5-Agent monitor stays read-only and degraded-safe |

---

## 12. Cost Posture

Default plan:

1. Use existing S0 demo/live_demo records for calibration labels.
2. Use free or low-cost S2 public Bybit data for initial historical replay.
3. Start recording S1 local market data as soon as practical.
4. Avoid S4 paid L2 data until a concrete gap is proven and operator approves the
   exact cost/scope.

This is the lowest-cost path that still improves development speed without hiding
execution uncertainty.

---

## 13. Final Decision

Paper Tab should become Paper Replay Lab. Learning should remain a Learning
Cockpit with replay evidence and ML/Dream producer monitoring. The current 5-Agent
panel should be extracted from Learning into a separate Agents Monitor, preserving
its read-only operational value.

This design directly addresses the development bottleneck without pretending that
paper fills are real exchange fills. It uses fast replay for rapid rejection and
candidate selection, then relies on calibrated uncertainty, source tagging, and
bounded demo validation before any live-bound governance review.
