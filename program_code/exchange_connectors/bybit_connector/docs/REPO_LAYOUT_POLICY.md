# BybitOpenClaw Repository Layout Policy

## Core rule

The repository preserves the old `srv`-style project skeleton at the repo level, but keeps the actual connector script files physically flat under:

`program_code/exchange_connectors/bybit_connector/scripts/`

## Why

This project has a large amount of historical shell tooling, absolute-path references, and operator habits built around the flat script layout. A physical relocation inside `scripts/` creates excessive compatibility burden and audit confusion.

## Therefore

- Repo-level skeleton should follow old `srv` style as much as practical.
- Script-level physical layout remains flat unless a future migration is explicitly designed, reviewed, and compatibility-tested.
- Logical grouping is handled by documentation and index files, not by moving files into subfolders.
- Runtime payloads, logs, secrets, and local environment artifacts are local-only and must not be committed to GitHub.

## Current live/local rule

- Canonical project root: `/home/ncyu/BybitOpenClaw`
- Compatibility access path: `/home/ncyu/srv` (symlink to the repo-local `srv`)
- Local runtime payloads may be attached under the repo-local skeleton without entering Git history.

## Migration safety rule

Before any future file relocation:
1. preview
2. compile check
3. compatibility check
4. git status review
5. only then commit

If a relocation changes operator readability but breaks old expectations, operator readability preference wins only when compatibility is preserved or intentionally redesigned.

---

## Compatibility-wrapper migration rule / 兼容包装器迁移规则

When a script family is migrated to its canonical old-srv-style directory:

1. real implementation files move to the canonical directory;
2. old flat entrypoints under `scripts/` stay as compatibility wrappers;
3. docs must state canonical path clearly;
4. migration should preserve operator habit, runtime path compatibility, and rollback simplicity.

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
## Decision lease migration progress — batch2 (2026-03-24)
Batch2 (`consume / replay / shadow`) has been migrated to the canonical implementation directory:
`program_code/trade_executor/bybit_decision_lease/`

Rule remains unchanged:
- canonical implementation = target category directory
- legacy flat path under `bybit_connector/scripts/` = compatibility wrapper only
- new business logic changes should be made only in the canonical file

<!-- CANONICAL_PATH_NOTE_DECISION_LEASE_BATCH3 -->
## Decision Lease Migration Progress / Decision Lease 迁移进度

Completed canonical migrations under:

`program_code/trade_executor/bybit_decision_lease/`

Completed batches:
- batch1: core_schema_preflight
- batch2: consume_shadow_replay
- batch3: friction_adaptive_approval

Policy remains:
- canonical implementation lives in target domain directory
- old flat `scripts/` entry remains wrapper-only during transition
- wrappers are removed only after full caller cleanup and verification
<!-- /CANONICAL_PATH_NOTE_DECISION_LEASE_BATCH3 -->

<!-- CANONICAL_PATH_NOTE_DECISION_LEASE_BATCH4 -->
## Decision Lease Migration Progress / Decision Lease 迁移进度

Completed canonical migrations under:

`program_code/trade_executor/bybit_decision_lease/`

Completed batches:
- batch1: core_schema_preflight
- batch2: consume_shadow_replay
- batch3: friction_adaptive_approval
- batch4: execution_authority_manual_ack

Policy remains:
- canonical implementation lives in target domain directory
- old flat `scripts/` entry remains wrapper-only during transition
- wrappers are removed only after full caller cleanup and verification
<!-- /CANONICAL_PATH_NOTE_DECISION_LEASE_BATCH4 -->

<!-- CANONICAL_PATH_NOTE_DECISION_LEASE_FINAL -->
## Decision Lease Status / Decision Lease 状态

`decision_lease` migration is now complete at canonical target:

`program_code/trade_executor/bybit_decision_lease/`

Status:
- exact members: 44
- canonical real files: 44
- wrappers retained in legacy flat scripts path
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

> Canonical path note: misc batch1 demo_gate has moved to `program_code/exchange_connectors/bybit_connector/misc_tools/`. Legacy flat files under `scripts/` are compatibility wrappers.
