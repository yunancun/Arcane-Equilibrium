# P1 Autonomous Parameter Proposal Contract

- Timestamp UTC: `2026-06-24T02:38:11Z`
- Active blocker: `P1-AUTONOMOUS-PARAMETER-PROPOSAL`
- Status: `DONE_WITH_CONCERNS`
- Scope: source/test/docs only

## Session Loop State

- `session_goal`: Profit-first Demo-learning Autonomy Improvement Loop under Aggressive Alpha Expansion Mode.
- `active_blocker_id`: `P1-AUTONOMOUS-PARAMETER-PROPOSAL`
- `blocker_goal`: establish a learned-candidate-to-bounded-proposal contract where learning output can only become a reviewable proposal, never a direct order/risk/live mutation.
- `profit_relevance`: autonomous learning can only improve risk-adjusted net PnL if learned edges become auditable proposal objects with explicit proof, cost, lineage, and authority gates.
- `completed_blockers`: `P1-LEARNING-LOOP-CLOSURE` source checkpoint completed at `bdc9f15b82ef938f8fd41fb390b1c27839637dfa`.
- `blocked_blockers`: `P0-PROFIT-EVIDENCE-QUALITY` and `P0-PROFIT-CANDIDATE-SELECTION` remain blocked by operator cleanup/quarantine of exchange overhang and fill-lineage drift.
- `previous_report_paths`: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-24--profit_evidence_quality_operator_checkpoint.md`, `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-24--profit_evidence_quality_proof_exclusion_guard.md`, `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-24--learning_ssot_decision_packet.md`.
- `source_head`: `bdc9f15b82ef938f8fd41fb390b1c27839637dfa` at loop start; local and origin were aligned.
- `runtime_timestamp`: not refreshed; no runtime action was authorized or needed for this source-only checkpoint.
- `pg_snapshot_timestamp`: not refreshed; no PG query/write was performed.
- `artifact_mtimes`: not refreshed; no canonical runtime artifact was regenerated.
- `operator_action_required`: still required for Bybit cancel/modify/close, PG reconciliation/write, crontab/restart/writer enablement, probe/order/live authority.
- `new_evidence_delta_required`: no runtime delta required for source-only proposal contract; P0 re-audit still requires operator/runtime evidence delta.
- `new_evidence_delta_found`: source gap found: no explicit no-authority conversion contract from learned candidate packet to reviewable parameter proposal existed.
- `acceptance_criteria`: builder emits `cost_gate_autonomous_parameter_proposal_v1`; default current P0 status blocks proposal emission; explicit cleared/quarantined P0 status can emit only inactive review packet; all proposed parameter rows carry `mutation_allowed_by_this_packet=false`; authority-bearing inputs including malformed truthy values fail closed; tests pass.
- `next_blocker_id`: `P1-RUNTIME-HEALTH-HYGIENE`; P0 candidate selection remains operator-gated.

## Anti-Repeat Decision

`P0-PROFIT-EVIDENCE-QUALITY` has no new operator authorization, runtime snapshot, PG snapshot, exchange action result, or canonical artifact delta after the operator checkpoint. Repeating the same order/fill audit would violate the anti-repeat rule, so this round moved to `P1-AUTONOMOUS-PARAMETER-PROPOSAL`, a source-only blocker with a concrete missing contract.

## Change

Added `helper_scripts/research/cost_gate_learning_lane/autonomous_parameter_proposal.py`.

The packet:

- emits schema `cost_gate_autonomous_parameter_proposal_v1`;
- consumes `cost_gate_learning_ssot_decision_v1` plus `cost_gate_false_negative_candidate_packet_v1`;
- requires the current learning SSOT to be artifact `probe_ledger.jsonl`, with no PG-backed cutover;
- requires P0 profit-evidence-quality status to be `DONE`, `DONE_WITH_CONCERNS`, or `EXPLICITLY_QUARANTINED_BY_OPERATOR` before any proposal is emitted;
- emits only `INACTIVE_REVIEW_PACKET_ONLY` proposal objects;
- keeps `main_cost_gate_adjustment=NONE`, `probe_authority_granted=false`, `order_authority_granted=false`, `promotion_evidence=false`, and no runtime/PG/Bybit/order action flags;
- marks every proposed parameter row `mutation_allowed_by_this_packet=false`;
- fail-closes `AUTHORITY_BOUNDARY_VIOLATION` on boolean and malformed truthy authority-bearing input values.

Updated `helper_scripts/research/tests/test_cost_gate_autonomous_parameter_proposal.py` and `helper_scripts/SCRIPT_INDEX.md`.

## Chain

- PM/PA: selected P1 source-only contract work after anti-repeat skipped P0 re-audit.
- E1: implemented the no-authority proposal builder and focused tests.
- E2: read-only review found a blocking truthy-authority parsing gap. PM/E1 fixed it.
- E4/QA: reran focused and related regression tests; verified no runtime/exchange/PG mutation.

## Verification

- `python3 -m py_compile helper_scripts/research/cost_gate_learning_lane/autonomous_parameter_proposal.py`
- `PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_cost_gate_autonomous_parameter_proposal.py` -> `5 passed`
- `PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py` -> `86 passed`
- `git diff --check`

## Boundaries

No PG query/write, Bybit call, order/cancel/modify, runtime mutation, service restart, crontab edit, Rust writer enablement, Cost Gate lowering, probe authority, order authority, live promotion, or promotion proof was performed.

## Concerns

This establishes the source contract but does not clear P0. In the current real state, `profit_evidence_quality_status` remains blocked unless the operator resolves or explicitly quarantines the open-order overhang and fill-lineage drift. The new builder is not yet wired into a runtime cron/worklist surface; that should only happen after deciding the exact canonical artifact refresh point.
