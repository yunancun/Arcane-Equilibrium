# 2026-07-05 AI/ML Trading Maturity Engineering Plan

PM sign-off: `SIGNED-WITH-GATES`

Scope: PM integrated the current repo state, the official exchange MCP review, and independent QC/MIT/AI-E/PA/E3/BB agent reviews into a practical engineering plan. This report is planning-only: no runtime action, no DB action, no secret access, no exchange contact, no MCP install, and no order authorization.

## Executive Verdict

We should push toward AI-assisted trading, but not by letting an LLM, RL policy, or official MCP server trade directly.

The current bottleneck is not model sophistication. The hard blocker is that the program still lacks a fully reconstructable candidate-matched evidence loop: `TODO.md` records the active `grid_trading|ETHUSDT|Buy` posture and a strict scan with 34,574 candidate ledger rows but zero candidate-matched order/fill/fee/slippage proof. The standing Demo loss-control authorization also expired at `2026-07-01T17:16:05Z`.

Therefore the right direction is:

1. Build real evidence.
2. Make evidence trainable.
3. Make models reliable advisors.
4. Let Demo parameters learn under bounded gates.
5. Keep RL and MCP as optional research until the first four layers are true.

## Agent Inputs Used

- `QC(default)`: recommended `REVISE / CONTINUE_EVIDENCE_BUILD`; demanded ProofPacket/LearningEvent, after-cost realism, truthful training manifests, statistical promotion gates, and governed Demo mutation before any maturity claim.
- `MIT(default)`: identified reward/evidence integrity as the main blocker; proposed immutable point-in-time dataset manifests, candidate-matched outcome ledger, parity metadata, mandatory leakage/split evidence, registry-authorized serving, and only-then RL.
- `AI-E(default)`: ranked near-term ROI as supervised quantile/LightGBM edge models first, contextual bandits second, DreamEngine/LLM Teacher as advisory only, RL later, MCP source-only.
- `PA(default)`: mapped the concrete phased implementation across current files/modules and role chains.
- `E3(explorer)`: restated exchange safety gates: expired Demo standing auth, no Cost Gate lowering, no order-capable action without fresh envelope -> fresh E3/BB -> same-window lease/BBO/order shape/Guardian/Rust authority/audit/reconstructability.
- `BB(default)`: rejected official Bybit MCP runtime/private-read/order integration; allowed only offline/static inventory, drift checks, and deny-by-default capability matrix work.
- `CC`: direct subagent spawn was blocked by thread limit. PM applied the root-principle review locally: authority must stay with narrow Rust-owned, auditable contracts; AI can propose, score, and diagnose only after proof integrity exists.

## Current Ground Truth

- Authoritative repo root: `/Users/ncyu/Projects/TradeBot/srv`.
- Current branch/head at review time: `main`, clean against `origin/main`; latest synced commit was `eee280302d6fb02b384f74cefbfde5fff8c71d59`.
- Active TODO posture: `P0-STANDING-DEMO-LOSS-CONTROL-ENVELOPE-REFRESH-CURRENT-HEAD`.
- Active candidate: `grid_trading|ETHUSDT|Buy`.
- Standing Demo auth: expired at `2026-07-01T17:16:05Z`.
- Evidence reality: no candidate-matched order/fill/fee/slippage proof for the active candidate.
- Official MCP review conclusion: source-only/reference-only. Do not replace Bybit runtime, Rust execution authority, or ADR-0048 IBKR baseline.

## 1. Phase One: Evidence Loop And Loss-Control Envelope

Priority: `P0`

Goal: produce one fully reconstructable, candidate-matched Demo outcome, or fail closed with an explicit blocker artifact.

Why this is first: without candidate-matched fills, fees, slippage, markout, control group, and exclusion lineage, any ML/RL reward is untrustworthy. More model complexity would optimize scanner labels or unmatched fills instead of real net outcome.

Primary files/modules:

- `TODO.md`
- `docs/agents/profit-first-autonomy-loop.md`
- `helper_scripts/research/cost_gate_learning_lane/standing_demo_loss_control_envelope_review.py`
- `helper_scripts/research/cost_gate_learning_lane/current_candidate_actual_admission_bbo_lease_window.py`
- `helper_scripts/research/cost_gate_learning_lane/outcome_review.py`
- `rust/openclaw_engine/src/demo_learning_lane.rs`
- `rust/openclaw_engine/src/bounded_probe_active_order.rs`

Engineering work:

- Refresh the expired standing Demo loss-control envelope only through the existing signed review path.
- Prove GUI/Rust `RiskConfig` cap lineage and confirm there is no hidden `10 USDT` authority path.
- Keep Cost Gate unchanged; do not lower it to force activity.
- Require fresh E3 and BB approval before any exchange-facing or order-capable Demo action.
- On the approved window only, require active Decision Lease, fresh BBO, order shape proof, Guardian/Rust authority, audit trail, and post-run lease release.
- Emit an outcome packet keyed by candidate/context/order identifiers, not by loose time window matching.

Acceptance gates:

- Fresh standing envelope exists and is linked to current head.
- Same-window lease, BBO, order shape, Guardian/Rust authority, audit, and reconstruction artifacts are present.
- Candidate-matched fill/fee/slippage evidence exists, or the run closes as a specific `NO_MATCHED_FILLS` / fail-closed blocker.
- No Cost Gate lowering, no direct AI order authority, no live/mainnet action.

Verification candidates:

- `python -m pytest helper_scripts/research/tests/test_current_candidate_* helper_scripts/research/tests/test_cost_gate_*`
- `cargo test -p openclaw_engine demo_learning_lane bounded_probe -- --test-threads=1`
- Linux read-only checks only until E3/BB authorize any runtime action.

Role chain:

- Exchange-facing refresh: `PM -> E3 -> BB -> PM`
- Code gaps: `PM -> PA -> E1 -> E2 -> E4 -> QA -> PM`
- Outcome review: add `QC -> MIT`

## 2. Phase Two: Point-In-Time Evidence And Training Foundation

Priority: `P0`

Goal: turn Demo/replay/ML inputs into immutable, point-in-time, hash-addressed, proof-exclusion-safe training/evaluation evidence.

Why this is second: supervised models and bandits can only improve if the dataset is reproducible and label truth is tied to real candidate outcomes. A trailing `now()` query or unsealed split is not a promotion-grade dataset.

Primary files/modules:

- `program_code/ml_training/parquet_etl.py`
- `program_code/ml_training/label_generator.py`
- `program_code/ml_training/leakage_check.py`
- `program_code/ml_training/candidate_evidence_manifest.py`
- `rust/openclaw_engine/src/database/decision_feature_writer.rs`
- `rust/openclaw_engine/src/database/exit_feature_writer.rs`
- SQL migrations around feature/outcome/proof tables, including existing V031/V059/V093/V125/V131/V143/V149 surfaces.

Engineering work:

- Add immutable dataset manifests for every promotable train/eval run.
- Include `as_of_ts`, query hash, source table snapshot/hash, row IDs/counts, min/max timestamps, schema hash, label hash, config hash, code commit, Rust build SHA, split IDs, and proof exclusions.
- Build a durable candidate outcome ledger keyed by `candidate_id`, `context_id`, `order_link_id`, `entry_context_id`, side cell, horizon, order shape, and control group.
- Include actual fees, slippage, maker/taker markout, funding, exits, exclusions, and net PnL after costs.
- Make leakage reports and fold-local preprocessing stats mandatory promotion evidence.
- Ensure Linux PG migrations are empirically dry-run and double-apply clean before claiming closure.

Acceptance gates:

- Same manifest rebuilds the same row set/hash.
- No promotable dataset depends on an unpinned `now()` window.
- No governance-reject dominance, cleanup fills, or unattributed fills are counted as proof.
- Disabled embargo, fractional fallback, full-array winsorization stats, or failed CPCV marks the artifact research-only.
- Hidden-OOS seals and reuse counters are persisted.

Verification candidates:

- `python -m pytest program_code/ml_training/tests program_code/learning_engine/tests helper_scripts/db/test_mlde_healthchecks.py`
- Linux PG migration dry-run and double-apply check before any migration sign-off.

Role chain:

- `PM -> MIT -> QC -> PA -> E1 -> E2 -> E4 -> PM`

## 3. Phase Three: Model And LLM Advisory Layer

Priority: `P1`

Goal: make ML useful as an advisory/scoring layer with train/serve parity, calibration, and zero execution authority.

Why this is third: once evidence is sound, the highest ROI is not RL. It is conservative supervised edge models, quantile models, calibration, and advisory diagnostics. DreamEngine/LLM Teacher should help explain, triage, hypothesize, and design experiments, not place orders.

Primary files/modules:

- `program_code/ml_training/run_training_pipeline.py`
- `program_code/ml_training/model_registry.py`
- `program_code/ml_training/promotion_evidence.py`
- `program_code/ml_training/mlde_shadow_advisor.py`
- `rust/openclaw_engine/src/ml/model_manager.rs`
- `rust/openclaw_engine/src/ml/scorer.rs`
- `rust/openclaw_engine/src/edge_predictor/features.rs`
- `rust/openclaw_engine/src/edge_predictor/feature_builder.rs`
- `rust/openclaw_engine/src/edge_predictor/ort_backend.rs`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/l2_advisory_orchestrator.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/l2_ml_advisory_executor.py`

Engineering work:

- Extend model registry metadata with feature definition hash, label schema/version/horizon, dataset manifest hash, CV split hash, leakage report hash, serving config hash, missingness policy, zero-fill semantics, units, side handling, and builder version.
- Make Rust serving load only registry-approved exact q10/q50/q90 artifact trios with matching hashes.
- Treat `_current` symlinks as convenience only, never as serving authority.
- Add golden Python/Rust feature fixture hashes and fail closed on mismatch.
- Keep L2/LLM calls scarce, logged, cost-gated, and explicitly `not_authority=true`.
- If ONNX inference is not real, the fallback must be visible, disabled from promotion, and unable to masquerade as model success.

Acceptance gates:

- Real registry rows exist with q10/q50/q90 artifact hashes.
- Feature schema and feature definition hashes match train/serve.
- Calibration, DSR/PBO, residual alpha, hidden-OOS, and leakage reports are present.
- L2 E2E call, if approved, writes `agent.l2_calls` and then returns to disabled/scarce mode.
- Advisory output cannot mutate runtime config or submit orders.

Verification candidates:

- `python -m pytest program_code/ml_training/tests/test_model_registry.py program_code/ml_training/tests/test_promotion_evidence.py program_code/ml_training/tests/test_mlde_shadow_advisor.py`
- `cargo test -p openclaw_engine ml linucb -- --test-threads=1`

Role chain:

- `PM -> QC -> MIT -> AI-E -> PA -> E1 -> E2 -> E4 -> PM`
- Add `E3` if any secret/cloud model/runtime path changes.

## 4. Phase Four: Controlled Demo Learning And Bandit Allocation

Priority: `P1`

Goal: allow bounded Demo parameter learning only after real after-cost outcomes exist.

Why this is fourth: the right first "AI control" mechanism is bounded parameter selection and contextual bandits, not a broad autonomous trader. The action space must be small, reversible, Demo-only, and backed by candidate-matched outcomes.

Primary files/modules:

- `program_code/ml_training/mlde_demo_applier.py`
- `program_code/ml_training/residual_stage0r_preflight.py`
- `program_code/ml_training/regime_bandit_allocator.py`
- `program_code/ml_training/linucb_trainer.py`
- `program_code/ml_training/thompson_sampling.py`
- `rust/openclaw_engine/src/linucb/runtime.rs`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/promotion_pipeline.py`

Engineering work:

- Limit initial learning to Demo-only bounded parameter applications through Rust-owned IPC.
- Use contextual bandits/LinUCB or Thompson sampling for bounded arm selection after the outcome ledger exists.
- Require before/after snapshots, bounded deltas, dedupe, governance review, matched controls, after-cost review, and rollback.
- Keep live candidates as review packets only.
- Do not let LLM/DreamEngine directly mutate runtime parameters.

Acceptance gates:

- Every Demo mutation has a `DemoMutationEnvelope`, source proof, previous value, proposed value, bounded delta, governance verdict, and rollback path.
- Empty/dedupe/dry-run applications do not count as learning success.
- Controls show after-cost improvement, not just blocked-signal markout.
- Live/mainnet remains closed; Cost Gate remains unchanged.

Verification candidates:

- `python -m pytest program_code/ml_training/tests/test_mlde_demo_applier*.py program_code/ml_training/tests/test_adaptive_demo_*.py`
- `cargo test -p openclaw_engine linucb demo_learning_lane config::risk_config -- --test-threads=1`

Role chain:

- `PM -> QC -> MIT -> PA -> E1 -> E2 -> E4 -> QA -> E3/BB -> PM`

## 5. Phase Five: RL And Official MCP Research Only

Priority: `P2`, optional after Phases 1-4

Goal: keep RL and official MCP work in a research/source-only lane until the repo has proven evidence, trainability, advisory parity, and governed Demo learning.

Why this is fifth: RL is reward-sensitive and can exploit bad labels. MCP servers broaden the attack and authority surface. Neither fixes the current blocker.

RL rules:

- Prefer contextual bandits before broad RL.
- Any RL must start offline on sealed, immutable, candidate-matched episodes.
- Reward must be `net_pnl_after_costs` with controls/exclusions, not scanner labels or unmatched fills.
- The action space must be constrained and reversible.
- Initial mode is shadow/research only; bounded Demo comes only after Phase Four gates.
- No RL policy can place orders directly or bypass Decision Lease, Guardian, Rust authority, ProofPacket, or promotion gates.

Official MCP rules:

- Bybit and IBKR official MCP/connectors stay source-only/reference-only.
- Allowed: static tool inventory, pinned version/hash review, deny-by-default capability matrix, API/documentation drift comparison, and ADR notes.
- Not allowed now: MCP install/config, `npx @latest`, credentials, private reads, order tools, exchange calls, WS trade loops, runtime replacement, promotion evidence, Cost Gate evidence, or PnL truth.
- IBKR connector UX can inform human-in-the-loop instruction drafting, but it is not an ADR-0048 runtime baseline.
- Bybit MCP capability taxonomy can inform a deny-by-default matrix, but Rust remains the runtime owner.

Primary references:

- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-05--official_mcp_exchange_tool_review.md`
- `docs/CCAgentWorkSpace/Operator/2026-07-05--official_mcp_exchange_tool_review.md`

Acceptance gates:

- MCP output cannot be used as alpha proof, fill truth, Cost Gate evidence, or execution authority.
- Any future exchange-facing MCP experiment requires a fresh ADR/AMD plus E3/BB review before even no-key public diagnostics.
- RL artifacts remain research-only unless they reference sealed candidate-matched outcome manifests and pass Phase Two/Three/Four gates.

Role chain:

- Architecture: `PM -> CC -> FA -> PA`
- Model economics: `PM -> QC -> MIT -> AI-E`
- Exchange boundary: `PM -> E3 -> BB`

## Non-Negotiable Boundaries

- No direct AI order authority.
- No direct LLM or MCP runtime mutation.
- No live/mainnet work in this plan.
- No Cost Gate lowering to manufacture activity.
- No `BYBIT_API_KEY` / `BYBIT_API_SECRET` env fallback for live/mainnet-like authority.
- No official MCP private-read/order integration.
- No hidden `_latest` / `_current` promotion shortcut.
- No proof from cleanup/unattributed/unmatched fills.
- No promotion without candidate-matched after-cost outcomes and sealed point-in-time evidence.

## PM Implementation Queue Recommendation

Immediate next dispatch should stay on the existing P0:

`P0-STANDING-DEMO-LOSS-CONTROL-ENVELOPE-REFRESH-CURRENT-HEAD`

After Phase One produces either candidate-matched proof or a fail-closed blocker artifact, dispatch Phase Two as the first AI/ML maturity engineering slice:

`P0-PIT-DATASET-MANIFEST-AND-CANDIDATE-OUTCOME-LEDGER`

Do not dispatch RL, MCP runtime integration, or DreamEngine trading authority work before those are complete.

## PM Sign-Off

PM signs this plan as implementable with gates:

- Proceed with Phase One and Phase Two engineering.
- Proceed with Phase Three advisory hardening only after Phase Two has promotion-grade manifests.
- Proceed with Phase Four Demo learning only after real candidate-matched outcomes exist.
- Keep Phase Five research-only until Phases One through Four are materially closed.

This is not an authorization to trade, start MCP servers, touch secrets, contact exchanges, lower gates, or change runtime authority.
