# ML/Dream Edge Unblock Plan

Date: 2026-04-29 17:51 CEST
Owner: PM
Status: Approved planning packet; implementation not started in this document.

## Decision

Positive edge is now a promotion gate, not a training gate.

Demo may use ML, LinUCB, DreamEngine, and OpportunityTracker to repair edge before the current strategies are net-positive. Live autonomous trading remains locked behind GovernanceHub / Decision Lease approval plus the existing live gates.

## Hard Boundary

- Demo: ML/Dream may run read-only, shadow, counterfactual, and tightly scoped demo exploration.
- LiveDemo/live: every autonomous execution path must pass GovernanceHub approval before release.
- Mainnet: GovernanceHub approval is necessary but not sufficient; the existing 5 live gates still apply: Operator role, `live_reserved`, `OPENCLAW_ALLOW_MAINNET=1`, valid secrets, and signed non-expired `authorization.json`.
- ML/Dream output is advisory by default. It may produce ranked candidates, veto scores, parameter proposals, and experiment plans. It must not directly mutate live risk/trading parameters or submit live orders.
- Any future live auto-trading promotion must have an auditable decision lease, explicit rollback path, and healthcheck coverage.

## Current Blockers Reframed

1. Phase 5 edge crisis:
   - Old interpretation: block ML/Dream until positive edge exists.
   - New interpretation: block live promotion and autonomous expansion, not learning.
   - Action: use negative demo edge as training signal for veto/ranking/parameter repair.

2. LinUCB 0-row / weak reward loop:
   - True P0 learning blocker.
   - Existing Rust runtime can cold-start and read `learning.linucb_state`, but decision metadata is still too sparse and partially tied to old signal-rule mapping.
   - Action: build arms from strategy intents and scanner metadata, then train from linked outcomes.

3. ExecutorAgent shadow-to-live:
   - Not zero design: ConfigStore, IPC, shadow toggle API, and e2e tests already exist.
   - Remaining blocker is the promotion contract between ML/Dream/agents and live execution.
   - Action: keep Executor shadow for edge repair; design GovernanceHub-approved promotion separately.

4. DreamEngine / OpportunityTracker:
   - Rust core implementations exist, but production wiring is not active.
   - Python strategist currently passes empty `regret_data` / `dream_data`.
   - Action: wire read-only producers first; no direct runtime mutation.

## Work Order

1. Learning Data Contract
   - Build a durable dataset path from `scanner_snapshots -> signals -> intents -> orders/fills -> outcomes`.
   - Use post-fee `net_bps_after_fee` as the primary reward.
   - Split windows explicitly: post-2026-04-22 clean edge window and post-2026-04-29 attribution/maker repair window.

2. LinUCB Unblock
   - Create arms from `strategy + symbol_bucket + regime + scanner.route_mode + edge_status`.
   - Train from linked demo/live_demo outcomes.
   - Keep LinUCB read-only first: log selected arm and counterfactual best arm, do not control sizing or order release.

3. ML Shadow Scorer
   - Train a scorer for expected post-fee net bps, maker fill probability, and hold-time/exit quality.
   - Run in shadow alongside current strategy decisions.
   - Produce veto/ranking/parameter recommendations only.

4. DreamEngine / OpportunityTracker Read-Only
   - Wire OpportunityTracker from skipped/rejected strategy opportunities and scanner candidates.
   - Run DreamEngine on narrow edge-repair questions first: grid spacing, MA whipsaw hold-time, bb_breakout threshold/timeframe, maker timeout.
   - Emit insights with sample count, expected net bps improvement, confidence, and applicable regime.

5. GovernanceHub Promotion Contract
   - Define one contract for turning ML/Dream output into action:
     - advisory log
     - operator-reviewable parameter proposal
     - demo-only patch / A-B experiment
     - live candidate
   - Live candidate requires GovernanceHub approval and a decision lease per execution or approved bounded policy.
   - Add healthchecks before any live release.

## Acceptance Gates

- Dataset gate: no training job may use rows without a valid attribution chain and post-fee reward.
- Shadow gate: ML/Dream recommendations must be logged and compared with actual outcomes before affecting demo execution.
- Demo gate: demo-only experiments must have bounded parameter deltas, rollback, and explicit start/end timestamps.
- Live gate: no autonomous live order or live parameter mutation without GovernanceHub approval, Decision Lease, and the 5 existing live gates.

## Immediate TODO Reorder

1. MLDE-0: formalize GovernanceHub live-autonomy boundary.
2. MLDE-1: learning data contract and dataset healthcheck.
3. MLDE-2: LinUCB intent-arm/reward loop.
4. MLDE-3: ML shadow scorer for edge repair.
5. MLDE-4: DreamEngine / OpportunityTracker read-only producers.
6. MLDE-5: demo A/B experiment path for advisory recommendations.
7. MLDE-6: live promotion contract and healthchecks.

