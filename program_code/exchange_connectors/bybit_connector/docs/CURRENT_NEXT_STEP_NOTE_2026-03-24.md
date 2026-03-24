# Current Next Step Note (2026-03-24)

## Current structure status

- old srv-style repo skeleton restored at public repo level
- scripts remain physically flat
- logical script category map generated
- local runtime payload reattached
- `/home/ncyu/srv` now resolves to the repo-local `srv`

## Current technical status

I10 clean recheck currently reports:

- summary_state = decision_lease_chapter_not_closed
- audit_state = decision_lease_chapter_audit_failed
- source_errors = ['i1_stage_not_closed']

Further read-only diagnosis shows the earliest real blocker is upstream of I1:
- H1 final audit is not closed
- H5 final audit is not closed
- governed AI invocation chain did not actually produce a valid response object

## Important interpretation

This may not mean the system is "broken" in the traditional sense.
A likely possibility is that current market / runtime conditions did not justify a real AI request or real lease progression, but the pipeline still records that as an unresolved blocked state.

A future repair direction should consider explicit state signaling for:
- no-trade / no-opportunity
- no-AI-needed
- empty-state-is-valid
instead of letting such cases look like stage failures.

## Immediate next engineering direction

1. continue read-only diagnosis of H1/H5 blockers
2. distinguish true bug vs expected empty-state blockage
3. design explicit neutral-state evidence objects if needed
4. only then repair schema / final-audit semantics

---

## 2026-03-24 migration update / 迁移更新

Completed today:
- `business_events` migrated to:
  `program_code/market_data_processor/bybit_business_events/`
- `readonly_observer_pipeline` migrated to:
  `program_code/exchange_connectors/bybit_connector/readonly_observer_pipeline/`

Both migrations currently preserve legacy `scripts/` entrypoints via compatibility wrappers.

Recommended next batch:
- `decision_lease_and_execution_authority`
- then `thought_gate_and_ai_governance`

Do not remove compatibility wrappers until later full-path stabilization and regression closure.

<!-- P7C_DECISION_LEASE_BATCH1_CANONICAL_START -->
## Decision-lease batch1 canonical path update (2026-03-24)

Canonical implementation path for the migrated batch1 core schema/preflight files is now:

`program_code/trade_executor/bybit_decision_lease/`

Legacy compatibility entrypoints are intentionally preserved under:

`program_code/exchange_connectors/bybit_connector/scripts/`

Those legacy files are now compatibility wrappers and should not be treated as the primary implementation source for the files listed below.

### Migrated files
- `bybit_decision_lease_chapter_contract_check.py`
- `bybit_decision_lease_chapter_final_audit.py`
- `bybit_decision_lease_chapter_handoff.py`
- `bybit_decision_lease_chapter_summary.py`
- `bybit_decision_lease_final_audit.py`
- `bybit_decision_lease_preflight.py`
- `bybit_decision_lease_preflight_contract_check.py`
- `bybit_decision_lease_schema.py`
- `bybit_decision_lease_schema_contract_check.py`

### Migration rule
- canonical implementation: `program_code/trade_executor/bybit_decision_lease/`
- compatibility wrapper: `program_code/exchange_connectors/bybit_connector/scripts/`
- new edits should target the canonical implementation first
<!-- P7C_DECISION_LEASE_BATCH1_CANONICAL_END -->

<!-- P7E_DECISION_LEASE_BATCH2_2026_03_24 -->
## Progress update — decision_lease batch2 completed
Completed migration:
- consume family
- replay family
- shadow family

Current canonical home:
- `program_code/trade_executor/bybit_decision_lease/`

Recommended next order:
1. migrate batch3 `friction_adaptive_approval`
2. migrate batch4 `execution_authority_manual_ack`
3. scan/update direct callers that should switch from wrapper path to canonical path
4. rerun targeted compile checks and decision-lease closure checks

<!-- CANONICAL_PATH_NOTE_DECISION_LEASE_BATCH3 -->
## Update: decision_lease batch3 finished / 更新：decision_lease batch3 已完成

Finished migration:
- adaptive_ttl
- approval_bridge
- friction

Canonical target:
`program_code/trade_executor/bybit_decision_lease/`

Next recommended step:
- migrate batch4 `execution_authority_manual_ack`
- then refresh docs / caller notes / commit / push
- then run targeted verification for decision_lease chapter closure dependencies
<!-- /CANONICAL_PATH_NOTE_DECISION_LEASE_BATCH3 -->

<!-- CANONICAL_PATH_NOTE_DECISION_LEASE_BATCH4 -->
## Update: decision_lease batch4 finished / 更新：decision_lease batch4 已完成

Finished migration:
- execution_authority_aggregator
- manual_approval_packet
- operator_ack_shadow

Canonical target:
`program_code/trade_executor/bybit_decision_lease/`

Decision lease migration status:
- batch1 complete
- batch2 complete
- batch3 complete
- batch4 complete

Next recommended step:
- run a focused caller/reference cleanup pass for decision_lease docs and helper scripts
- then start next canonical migration batch from remaining logical categories
<!-- /CANONICAL_PATH_NOTE_DECISION_LEASE_BATCH4 -->

<!-- CANONICAL_PATH_NOTE_DECISION_LEASE_FINAL -->
## Update: decision_lease fully complete / 更新：decision_lease 已全部完成

Canonical migration completed for all decision_lease formal members.

Counts:
- exact list: 44
- canonical real files: 44

Recommended next step:
- start `thought_gate_and_ai_governance` extraction, batching, and migration
<!-- /CANONICAL_PATH_NOTE_DECISION_LEASE_FINAL -->

## Canonical Path Update / 规范路径更新（Thought Gate Batch 1）

The first `thought_gate_and_ai_governance` batch has been migrated to:

`program_code/ai_agents/bybit_thought_gate/`

Batch:
- model_router

Canonical real files moved in this batch:
- bybit_model_router_contract_check.py
- bybit_model_router_decision.py
- bybit_model_router_decision_contract_check.py
- bybit_model_router_final_audit.py
- bybit_model_router_policy.py
- bybit_model_router_policy_contract_check.py
- bybit_model_router_runtime.py
- bybit_model_router_runtime_contract_check.py

Legacy flat-script paths remain compatibility wrappers during transition.

## Canonical Path Update / 规范路径更新（Thought Gate Batch 2）

The second `thought_gate_and_ai_governance` batch has been migrated to:

`program_code/ai_agents/bybit_thought_gate/`

Batch:
- compute_governor

Canonical real files moved in this batch:
- bybit_compute_governor_contract_check.py
- bybit_compute_governor_final_audit.py
- bybit_compute_governor_gate.py
- bybit_compute_governor_gate_contract_check.py
- bybit_compute_governor_policy.py
- bybit_compute_governor_policy_contract_check.py
- bybit_compute_governor_runtime.py
- bybit_compute_governor_runtime_contract_check.py

Legacy flat-script paths remain compatibility wrappers during transition.

## Canonical Path Update / 规范路径更新（Thought Gate Batch 3）

The third `thought_gate_and_ai_governance` batch has been migrated to:

`program_code/ai_agents/bybit_thought_gate/`

Batch:
- query_budget

Canonical real files moved in this batch:
- bybit_query_budget_final_audit.py
- bybit_query_budget_final_audit_contract_check.py
- bybit_query_budget_gate.py
- bybit_query_budget_gate_contract_check.py
- bybit_query_budget_policy.py
- bybit_query_budget_policy_contract_check.py
- bybit_query_budget_runtime.py
- bybit_query_budget_runtime_contract_check.py

Legacy flat-script paths remain compatibility wrappers during transition.

## Canonical Path Update / 规范路径更新（Thought Gate Batch 4）

The fourth `thought_gate_and_ai_governance` batch has been migrated to:

`program_code/ai_agents/bybit_thought_gate/`

Batch:
- ai_request_response_core

Canonical real files moved in this batch:
- bybit_ai_governed_decision.py
- bybit_ai_governed_decision_contract_check.py
- bybit_ai_invocation_attempt_builder.py
- bybit_ai_invocation_attempt_contract_check.py
- bybit_ai_prompt_prep_builder.py
- bybit_ai_prompt_prep_contract_check.py
- bybit_ai_prompt_prep_tighten.py
- bybit_ai_request_envelope_builder.py
- bybit_ai_request_envelope_contract_check.py
- bybit_ai_response_check.py
- bybit_ai_response_check_builder.py
- bybit_ai_response_check_contract_check.py
- bybit_ai_route_selector_builder.py
- bybit_ai_route_selector_contract_check.py

Legacy flat-script paths remain compatibility wrappers during transition.

## Canonical Path Update / 规范路径更新（Thought Gate Batch 5）

The fifth `thought_gate_and_ai_governance` batch has been migrated to:

`program_code/ai_agents/bybit_thought_gate/`

Batch:
- ai_governance_cost

Canonical real files moved in this batch:
- bybit_ai_cost_governance_contract_check.py
- bybit_ai_cost_governance_final_audit.py
- bybit_ai_cost_log.py
- bybit_ai_cost_log_contract_check.py
- bybit_ai_governance_audit.py
- bybit_ai_governance_audit_contract_check.py

Legacy flat-script paths remain compatibility wrappers during transition.

## Canonical Path Update / 规范路径更新（Thought Gate Batch 6）

The sixth `thought_gate_and_ai_governance` batch has been migrated to:

`program_code/ai_agents/bybit_thought_gate/`

Batch:
- thought_gate_outputs

Canonical real files moved in this batch:
- bybit_thought_gate_acceptance_suite.py
- bybit_thought_gate_contract_check.py
- bybit_thought_gate_decision_builder.py
- bybit_thought_gate_decision_contract_check.py
- bybit_thought_gate_final_audit.py
- bybit_thought_gate_handoff.py
- bybit_thought_gate_input_builder.py
- bybit_thought_gate_input_contract_check.py
- bybit_thought_gate_policy_builder.py
- bybit_thought_gate_policy_contract_check.py
- bybit_thought_gate_regression_summary.py

Legacy flat-script paths remain compatibility wrappers during transition.

> Canonical path note: exchange_io batch4 misc_io_support has moved to `program_code/exchange_connectors/bybit_connector/io_and_persistence/`. Legacy flat files under `scripts/` are compatibility wrappers.

> Canonical path note: exchange_io batch2 snapshot_and_postgres has moved to `program_code/exchange_connectors/bybit_connector/io_and_persistence/`. Legacy flat files under `scripts/` are compatibility wrappers.

> Canonical path note: exchange_io batch3 private_api_checks has moved to `program_code/exchange_connectors/bybit_connector/io_and_persistence/`. Legacy flat files under `scripts/` are compatibility wrappers.

> Canonical path note: exchange_io batch1 connectivity_and_ws has moved to `program_code/exchange_connectors/bybit_connector/io_and_persistence/`. Legacy flat files under `scripts/` are compatibility wrappers.

> Canonical path note: local_models batch3 local_judgment has moved to `program_code/risk_control/bybit_local_models_and_risk/`. Legacy flat files under `scripts/` are compatibility wrappers.

> Canonical path note: local_models batch2 risk_envelope_and_friction has moved to `program_code/risk_control/bybit_local_models_and_risk/`. Legacy flat files under `scripts/` are compatibility wrappers.

> Canonical path note: local_models remaining trigger/trade-eligibility and support builders have moved to `program_code/risk_control/bybit_local_models_and_risk/`. Legacy flat files under `scripts/` are compatibility wrappers.

> Canonical path note: misc batch2 demo_paper_or_adapter has moved to `program_code/exchange_connectors/bybit_connector/misc_tools/`. Legacy flat files under `scripts/` are compatibility wrappers.

> Canonical path note: misc batch4 other_misc has moved to `program_code/exchange_connectors/bybit_connector/misc_tools/`. Legacy flat files under `scripts/` are compatibility wrappers.
