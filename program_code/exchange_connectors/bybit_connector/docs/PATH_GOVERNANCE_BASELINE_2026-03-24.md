# Path Governance Baseline (2026-03-24)

## Purpose

This document defines the **current path governance baseline** for the BybitOpenClaw repository after H1-H5 canonical closure was completed.

The immediate goal is **not** to relocate everything at once.  
The goal is to stop further path drift, document the real canonical structure, and provide a safe baseline for future cleanup.

---

## Current confirmed status

As of 2026-03-24:

- H1 thought_gate closed
- H2 query_budget closed
- H3 model_router closed
- H4 compute_governor closed
- H5 ai_cost_governance closed

The H chapter is now formally closed under the following accepted semantics:

- `should_call_ai = false`
- `route_plan = route_skip`
- `no_call_path_accepted = true`

Safety boundaries remain intact:

- `system_mode = read_only`
- `execution_state = disabled`
- `execution_authority = not_granted`

---

## Canonical root vs compatibility root

### Canonical project root

The canonical repository root is:

`/home/ncyu/BybitOpenClaw`

Within local operator workflow, the actual editable repo root in this clone is:

`/home/ncyu/BybitOpenClaw/srv`

### Compatibility access path

The old path:

`/home/ncyu/srv`

currently exists only as a **compatibility symlink / compatibility access path**.

It should not be treated as the design target for new code.

---

## Governance rule for new code

### Hard rule

New or newly-refactored code must **not introduce additional hardcoded** references to:

`/home/ncyu/srv`

unless there is a documented compatibility exception.

### Preferred rule

New code should use one of these approaches:

1. repo-relative resolution from the current file location
2. a shared path helper module
3. a documented canonical root abstraction

---

## Local-only runtime rule

The following categories remain local/operator data and must not be treated as GitHub-shareable source artifacts:

- runtime payloads
- connector logs
- local env files
- local secret files
- database payloads
- venvs
- local backups / inventory outputs

These may exist under the repo-local srv-style skeleton, but they are not business-logic source code.

---

## Current migration principle

Canonical implementation files should live in their logical domain directory.

Examples already in effect:

- `program_code/ai_agents/bybit_thought_gate/`
- `program_code/trade_executor/bybit_decision_lease/`
- `program_code/exchange_connectors/bybit_connector/readonly_observer_pipeline/`
- `program_code/market_data_processor/bybit_business_events/`

Legacy flat-script entrypoints under `program_code/exchange_connectors/bybit_connector/scripts/` may remain as compatibility wrappers during transition.

---

## Canonical runner baseline

The following canonical minimal closure runners now exist for the H chapter:

- `run_h1_thought_gate_canonical_closure_minimal.sh`
- `run_h2_query_budget_canonical_closure_minimal.sh`
- `run_h3_model_router_canonical_closure_minimal.sh`
- `run_h4_compute_governor_canonical_closure_minimal.sh`
- `run_h5_ai_cost_governance_canonical_closure_minimal.sh`

These runners represent the current authoritative minimal chapter closure path for H1-H5.

---

## Immediate cleanup priority

The current repo still contains a large amount of `/home/ncyu/srv` hardcoding.

Priority should be:

1. stop new hardcoding
2. document the baseline
3. introduce shared path helpers
4. clean the actively-used canonical H-chain first
5. then expand cleanup to other folders by batch

---

## Recommended next engineering order

### P1
Document + freeze baseline:
- path governance baseline
- repo layout policy refresh
- current next step note refresh
- thought_gate README refresh

### P2
Create / adopt shared path helper in actively-maintained canonical code.

### P3
Run first hardcode cleanup batch for:
- `program_code/ai_agents/bybit_thought_gate`
- directly-related helper scripts
- directly-related wrapper / helper files

### P4
Re-design I10 / mainline recheck so that it reflects the current canonical H-chain rather than old decision_lease-only assumptions.

### P5
Only after the above, continue I1 development.

---

## Operator reminder

Do **not** treat current H-chain closure as execution permission.

H1-H5 closure means:
- audit semantics are now coherent
- legal no-call is now formally accepted
- read-only governance remains intact

It does **not** mean:
- live execution is approved
- execution authority is granted
- decision lease should be emitted

