# 2026-07-06 AI/ML Trading Engineering Roadmap After Maker-First Challenge

PM sign-off: `SIGNED-WITH-GATES`

Scope: respond to the operator request to seriously challenge the 2026-07-06 maker-first
microstructure verdict and produce a practical engineering direction, roadmap, and concrete
implementation plan. This is a planning/report artifact only. No runtime mutation, DB write, secret
access, MCP install/config, exchange contact, private read, order/probe, Cost Gate change, or
live/mainnet action was performed.

## Executive Verdict

The challenge does not overturn the narrow maker-first `NO-GO`. It corrects the interpretation.

Accepted:

- At current Bybit fee tier, mature-perp maker-first passive spread capture is not a good P0/P1
  profit lever.
- `fill_sim` is strong enough to kill the normal mature-universe market-making pivot:
  `0/172` positive cells across the two tested windows, best fill-only cell still around `-3.2 bps`
  per fill after fees.
- M12/adaptive routing is worth preserving as execution cost reduction, not as alpha.

Rejected as overreach:

- The report does not prove that "AI is useless", that the bot cannot become profitable, or that
  every passive/niche/event surface is dead.
- It does not decide brand-new listings, event windows, cross-venue/funding/basis, portfolio
  allocation, or supervised edge/risk scoring.
- It does not replace the current need for candidate-matched Demo outcomes. The current hard blocker
  is still evidence integrity, not model sophistication.

The correct development direction is not "train one mature AI trader". It is to build a governed
intelligence stack:

1. proof/evidence loop,
2. point-in-time trainable data foundation,
3. supervised advisory/scoring,
4. bounded Demo learning/bandits,
5. optional RL/MCP/niche research after gates.

## Inputs Integrated

Local sources:

- `TODO.md`: active blocker remains `P0-STANDING-DEMO-LOSS-CONTROL-ENVELOPE-REFRESH-CURRENT-HEAD`;
  standing Demo authorization expired at `2026-07-01T17:16:05Z`; current candidate
  `grid_trading|ETHUSDT|Buy` still has zero candidate-matched order/fill/fee/slippage proof.
- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-05--ai_ml_trading_maturity_engineering_plan.md`
- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-05--official_mcp_exchange_tool_review.md`
- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-06--maker_first_microstructure_feasibility_verdict.md`
- `program_code/research/microstructure/fill_sim.py`
- ML/evidence/Rust surfaces under `program_code/ml_training/`, `program_code/learning_engine/`,
  `rust/openclaw_engine/src/edge_predictor/`, `rust/openclaw_engine/src/linucb/`,
  `rust/openclaw_engine/src/demo_learning_lane*`, and `rust/openclaw_engine/src/order_router.rs`.

Agent inputs available in-thread:

- `QC(default)`: continue evidence build; no promotion without ProofPacket / LearningEvent,
  candidate-matched fills, real costs, controls, and OOS/repeat proof.
- `MIT(default)`: reward/evidence integrity is the blocker; add immutable PIT dataset manifests,
  candidate outcome ledger, leakage/split evidence, and registry-authorized serving.
- `AI-E(default)`: supervised quantile/LightGBM first, bandits second, DreamEngine/LLM advisory only,
  RL later, MCP source-only.
- `PA(default)`: phase plan: evidence loop -> data foundation -> advisory model -> controlled Demo
  learning -> optional RL/MCP.
- `E3(explorer)`: standing auth is expired; any order-capable step needs fresh envelope -> fresh
  E3/BB -> same-window Decision Lease/BBO/order shape/Guardian/Rust authority/audit/reconstructability.
- `BB(default)`: official Bybit MCP is source/reference only; no runtime order/private-read path;
  build a deny-by-default capability matrix if used at all.

Dispatch note: PM attempted to spawn fresh role agents, but the desktop thread limit was reached.
PM then inspected the six completed in-thread role outputs above and integrated them. No sub-agent
was asked to edit files or touch runtime.

External public-source sanity check on 2026-07-06:

- Bybit official MCP repo currently describes a broad Bybit MCP server with 206 tools, environment
  credential loading, 22 no-key market-data tools, and `npx ...@latest` quick start.
- IBKR AI integrations page describes an MCP connector for portfolio-aware analysis and draft trade
  instructions; IBKR remains the platform where the order is submitted.

These public facts reinforce the local conclusion: official MCP can inform taxonomy and UX, but it
must not become execution authority.

## Challenge Conclusions

### 1. Maker-first is killed only for the correct scope

Scope killed:

- mature USDT perp universe,
- current Bybit fee tier,
- maker-first as primary profit lever,
- passive spread capture / market-making style edge,
- existing retail/non-colocated queue posture.

Scope still open:

- first-hours new-listing/event windows,
- cross-venue/funding/basis and portfolio overlays,
- supervised edge/risk scoring,
- execution-cost reduction,
- bounded strategy/parameter allocation,
- IBKR stock/ETF research lane under ADR-0048 boundaries.

### 2. The highest ROI work is not a larger model

The current system has many ML/DreamEngine/agent surfaces, but the active blocker is still missing
truth labels. Training a large agent now would likely optimize:

- unmatched scanner rows,
- governance rejects,
- stale windows,
- synthetic or cleanup fills,
- or labels not tied to actual fee/slippage outcomes.

That would make the bot more complex, not more intelligent.

### 3. AI should become a governed research and scoring layer

The first useful "AI" should be:

- conservative supervised q10/q50/q90 edge/risk models,
- calibrated shadow advisory,
- model registry + train/serve parity,
- contextual bandits for bounded allocation after real outcomes exist,
- LLM/DreamEngine for hypothesis generation, code/evidence diagnosis, and experiment design.

It should not:

- place orders,
- mutate live parameters,
- lower Cost Gate,
- call MCP tools with credentials,
- use Bybit/IBKR MCP as fill/PnL truth,
- or bypass Rust authority.

## Ranked Engineering Bets

| Rank | Bet | Priority | Why | Minimum experiment | Kill gate |
|---:|---|---|---|---|---|
| 1 | Candidate-matched ProofPacket / outcome loop | P0 | Without real after-cost outcomes, all learning is untrusted | fresh envelope -> same-window bounded Demo outcome or explicit no-fill blocker | no fill/fee/slippage lineage after approved bounded attempts means rotate candidate or fix execution gate, not train |
| 2 | PIT dataset manifest + outcome ledger | P0 | Makes data trainable and reproducible | immutable manifest rebuilds exact row/hash; ledger joins candidate/context/order/fill ids | any unpinned `now()` train set, unmatched fill, or cleanup/proof-excluded fill blocks promotion |
| 3 | Supervised quantile/edge scorer | P1 | Highest near-term AI ROI after labels exist | q10/q50/q90 model trio with registry hashes, leakage report, hidden-OOS, calibration | no positive after-cost hidden-OOS / DSR / controls means shadow-only |
| 4 | Controlled Demo bandit allocation | P1 | Lets system learn small bounded choices before RL | LinUCB/Thompson chooses among pre-approved arms, DemoMutationEnvelope only | no matched after-cost uplift vs controls after sample threshold freezes bandit |
| 5 | New-listing/event microstructure screen | P1/P2 | Only plausible maker-style challenge not covered by mature-perp `fill_sim` | offline scan first-hours spreads, fill feasibility, adverse selection, fee threshold | 0 net-positive sealed event windows, or fee threshold above actual tier, kills niche |
| 6 | M12 adaptive router | P2 | Reduces taker/slippage/regret; not alpha | design-only then shadow replay comparing route choices and realized costs | no statistically meaningful cost reduction keeps dormant |
| 7 | Official MCP inventory | P2 | Useful as taxonomy/drift reference only | pinned source hash -> deny-by-default capability matrix | any credential/runtime/private read/order requirement blocks |
| 8 | RL policy | P2/later | Reward-sensitive and dangerous before evidence maturity | offline sealed episodes only, constrained action space, counterfactual evaluation | no sealed candidate-matched episodes means no RL |

## 90-Day Roadmap

### Days 0-14: unblock truth

Objective: produce one reconstructable candidate-matched Demo outcome, or a precise fail-closed
blocker.

Work packages:

- Refresh standing Demo loss-control envelope at current head.
- Re-run exact E3/BB review before any exchange-facing/runtime action.
- Execute same-window gate only if authorized: active Decision Lease, fresh BBO, exact order shape,
  Guardian/Rust authority, audit/reconstructability, post-run lease release.
- Emit a ProofPacket / LearningEvent draft keyed by candidate/context/order ids.
- If no fills, emit `NO_MATCHED_FILLS` with placement/touchability facts, not a fake learning label.

Primary chain:

- Runtime/exchange-facing: `PM -> E3 -> BB -> PM`
- Any source gap: `PM -> PA -> E1 -> E2 -> E4 -> QA -> PM`
- Outcome review: `PM -> QC -> MIT -> PM`

### Days 15-30: make evidence trainable

Objective: turn outcomes and replay inputs into sealed, point-in-time manifests.

Work packages:

- Add/extend immutable dataset manifest contract:
  `as_of_ts`, query hash, source snapshot/hash, row ids/counts, min/max timestamps, schema hash,
  label hash, config hash, code commit, Rust build SHA, split ids, proof exclusions.
- Harden outcome ledger around `candidate_id`, `context_id`, `order_link_id`, `entry_context_id`,
  side cell, horizon, order shape, controls, fees, slippage, funding, markout, and proof exclusion.
- Require leakage/split reports for any promotion-grade artifact.
- Mark trailing-window, unsealed, or failed-CPCV artifacts as research-only.

Primary chain:

- `PM -> MIT -> QC -> PA -> E1 -> E2 -> E4 -> PM`

### Days 31-60: supervised advisory

Objective: make AI useful without giving it authority.

Work packages:

- Registry-authorized q10/q50/q90 model trio.
- Python/Rust feature parity golden fixtures.
- ONNX real-inference or explicit disabled fallback.
- Calibrated shadow advisory output with `not_authority=true`.
- L2/LLM calls only under scarce logged review windows; no direct mutation.

Primary chain:

- `PM -> QC -> MIT -> AI-E -> PA -> E1 -> E2 -> E4 -> PM`
- Add `E3` if cloud/secrets/model-call runtime path changes.

### Days 61-90: controlled learning and niche challenges

Objective: let Demo learn bounded decisions and separately challenge untested edge surfaces.

Work packages:

- DemoMutationEnvelope for bounded parameter/arm changes.
- LinUCB/Thompson/regime bandit only after outcome ledger has real rewards.
- Shadow compare against controls before any bounded Demo application.
- New-listing/event microstructure screen in offline mode only.
- M12 adaptive router design as cost-reduction, not alpha.
- MCP source-only inventory and capability matrix if it helps governance.

Primary chains:

- Bandits/Demo learning: `PM -> QC -> MIT -> PA -> E1 -> E2 -> E4 -> QA -> E3/BB -> PM`
- MCP/source matrix: `PM -> CC -> FA -> PA -> E3 -> BB -> PM`
- New-listing screen: `PM -> QC -> MIT -> BB -> PA -> PM`

## Concrete Engineering Plan

### WP0: current-head standing envelope refresh

Priority: P0.

Goal: remove the expired-auth blocker without granting order authority.

Files:

- `TODO.md`
- `helper_scripts/research/cost_gate_learning_lane/standing_demo_loss_control_envelope_review.py`
- `helper_scripts/research/cost_gate_learning_lane/standing_envelope_post_approval_drift_gate.py`

Acceptance:

- Fresh current-head request packet.
- Fresh E3/BB approval for exact scope.
- Final source/drift gate pass.
- Runtime action remains no-order/no-private unless separately approved.

Verification:

- Existing focused cost-gate/standing-envelope tests.
- Linux read-only hash/status checks only until approval.

### WP1: ProofPacket / LearningEvent contract

Priority: P0.

Goal: define one canonical proof object for candidate-matched outcomes.

Files:

- `program_code/ml_training/candidate_evidence_manifest.py`
- `program_code/ml_training/candidate_evidence_manifest_builder.py`
- `program_code/learning_engine/promotion_gate.py`
- `rust/openclaw_engine/src/demo_learning_lane.rs`
- `rust/openclaw_engine/src/demo_learning_lane_ledger.rs`

Required fields:

- candidate identity: strategy, symbol, side, candidate id, context id.
- execution identity: order link id, fill id(s), entry/exit context ids, liquidity role.
- cost identity: maker/taker fees, slippage, spread, funding, markout, realized net PnL.
- controls: matched control rows, regime labels, OOS split, proof exclusions.
- provenance: source hashes, code commit, build SHA, input artifact hashes.

Acceptance:

- No `promotion_ready` without candidate-matched fills and costs.
- Cleanup/unattributed/proof-excluded fills cannot enter proof.
- A no-fill run is a valid blocker artifact, not a positive/negative label.

### WP2: point-in-time dataset manifest

Priority: P0.

Goal: make train/eval datasets reproducible.

Files:

- `program_code/ml_training/parquet_etl.py`
- `program_code/ml_training/label_generator.py`
- `program_code/ml_training/leakage_check.py`
- `program_code/ml_training/tests/test_candidate_evidence_manifest*.py`
- SQL migration only after PA/MIT design and Linux PG dry-run.

Acceptance:

- No promotable dataset depends on unpinned `now()` windows.
- Same manifest rebuilds same row set and hash.
- Fold-local preprocessing stats and leakage evidence are attached.
- Failed CPCV/embargo/hidden-OOS gates mark artifact research-only.

### WP3: model registry and Rust serving parity

Priority: P1.

Goal: make supervised models safe to serve as advisory.

Files:

- `program_code/ml_training/model_registry.py`
- `program_code/ml_training/run_training_pipeline.py`
- `program_code/ml_training/promotion_evidence.py`
- `rust/openclaw_engine/src/edge_predictor/features.rs`
- `rust/openclaw_engine/src/edge_predictor/feature_builder.rs`
- `rust/openclaw_engine/src/edge_predictor/ort_backend.rs`
- `rust/openclaw_engine/src/ml/registry.rs`

Acceptance:

- q10/q50/q90 exact trio required.
- Registry row includes dataset manifest hash, label schema hash, feature definition hash,
  split hash, leakage report hash, serving config hash, missingness policy, units, side handling.
- `_current` symlink is convenience only, not serving authority.
- Rust fails closed or marks fallback non-promotable on mismatch.

### WP4: advisory and DreamEngine role hardening

Priority: P1.

Goal: use LLM/DreamEngine as research copilot, not trader.

Files:

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/l2_advisory_orchestrator.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/l2_ml_advisory_executor.py`
- `program_code/ml_training/mlde_shadow_advisor.py`
- `program_code/ai_agents/`

Acceptance:

- All L2/LLM outputs include `not_authority=true`.
- Calls are budgeted, logged, and tied to input hashes.
- Any proposal becomes inactive review packet unless a separate Demo envelope authorizes mutation.
- No strategy/config/order mutation from LLM path.

### WP5: controlled Demo bandit allocation

Priority: P1 after WP1/WP2.

Goal: learn bounded choices using real after-cost rewards.

Files:

- `program_code/ml_training/regime_bandit_allocator.py`
- `program_code/ml_training/linucb_trainer.py`
- `program_code/ml_training/thompson_sampling.py`
- `program_code/ml_training/mlde_demo_applier.py`
- `rust/openclaw_engine/src/linucb/runtime.rs`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/promotion_pipeline.py`

Acceptance:

- Action space is small, reversible, pre-approved.
- Every Demo change has previous value, proposed value, bounded delta, governance verdict,
  rollback handle, and post-change review.
- Empty/dedupe/dry-run application does not count as learning.
- Live/mainnet stays closed.

### WP6: new-listing/event microstructure challenge

Priority: P1/P2.

Goal: test the remaining maker-style niche without touching exchange/runtime.

Files:

- `program_code/research/microstructure/fill_sim.py`
- future source-only scanner under `program_code/research/microstructure/`
- recorder outputs from `market.l1_events` / `market.trades`

Acceptance:

- Event/listing window is pre-registered.
- Fee tier is explicit and no rebate is assumed.
- Uses holdout and adverse-selection markout, not gross spread.
- Positive cells require enough events and survive out-of-sample; otherwise niche is closed.

### WP7: M12 adaptive router design

Priority: P2.

Goal: reduce execution cost, not create alpha.

Files:

- `rust/openclaw_engine/src/order_router.rs`
- strategy order-intent helpers under `rust/openclaw_engine/src/strategies/`
- event dispatch/order manager paths.

Acceptance:

- Shadow-only design first.
- Compares route choice vs realized fee/slippage/markout with controls.
- Does not bypass Decision Lease, Guardian, Rust authority, or audit.
- No claim of alpha without outcome ledger proof.

### WP8: official MCP source-only capability matrix

Priority: P2.

Goal: harvest official taxonomy without importing authority.

Files:

- future source-only docs/spec under `docs/execution_plan/specs/`
- Bybit reference docs under `docs/references/`
- ADR/AMD note if IBKR hosted connector posture changes.

Acceptance:

- Pinned package/repo version and source hash.
- Every tool classified as public read, private read, trade write, account write, asset movement,
  or denied.
- No MCP install, credentials, server start, exchange call, runtime truth, proof, or Cost Gate use.

## Non-Goals

- No direct AI trader.
- No RL before sealed candidate-matched episodes.
- No official MCP runtime/private-read/order integration.
- No live/mainnet change.
- No Cost Gate lowering to force activity.
- No promotion based on scanner rows, gross markout, cleanup fills, or unmatched fills.
- No model serving from unsealed `_current` artifacts.

## PM Sign-Off

PM signs the roadmap as `SIGNED-WITH-GATES`.

Decision:

- Keep the maker-first mature-perp NO-GO in force.
- Do not kill AI/ML. Redirect it into evidence, PIT data, supervised advisory, and bounded Demo
  learning.
- Treat new-listing/event maker screens and M12 router as scoped challenge items, not as current
  mainline.
- Treat official MCP as source/reference only unless a future ADR/AMD plus E3/BB review approves a
  much narrower diagnostic scope.

Immediate next executable work remains the existing P0:

`P0-STANDING-DEMO-LOSS-CONTROL-ENVELOPE-REFRESH-CURRENT-HEAD`

Only after that can the roadmap's evidence and learning phases produce real outcomes.
