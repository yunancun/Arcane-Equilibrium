# bybit_thought_gate

## Purpose

This directory contains the canonical implementation for the current Bybit AI thought-gate and AI governance chain.

It is the canonical home for the repaired H-chapter logic.

---

## Current chapter status (2026-03-24)

The H chapter is now formally closed:

- H1 thought_gate closed
- H2 query_budget closed
- H3 model_router closed
- H4 compute_governor closed
- H5 ai_cost_governance closed

Accepted canonical semantics:

- `should_call_ai = false`
- `route_plan = route_skip`
- `no_call_path_accepted = true`

Safety boundaries remain intact:

- `system_mode = read_only`
- `execution_state = disabled`
- `execution_authority = not_granted`

This means the chain now correctly accepts a legal no-call terminal path without pretending there was a real provider-native response.

---

## What this directory contains

### H1
- AI response check
- governed decision
- acceptance suite
- regression summary
- handoff
- final audit

### H2
- query budget policy / gate / runtime / final audit

### H3
- model router policy / decision / runtime / final audit

### H4
- compute governor policy / gate / runtime / final audit

### H5
- AI cost log
- AI governance audit
- AI cost governance final audit

It also contains contract-check files for each major report family.

---

## Canonical runner baseline

Minimal canonical closure runners created during the 2026-03-24 repair work:

- `helper_scripts/maintenance_scripts/bybit_connector/run_h1_thought_gate_canonical_closure_minimal.sh`
- `helper_scripts/maintenance_scripts/bybit_connector/run_h2_query_budget_canonical_closure_minimal.sh`
- `helper_scripts/maintenance_scripts/bybit_connector/run_h3_model_router_canonical_closure_minimal.sh`
- `helper_scripts/maintenance_scripts/bybit_connector/run_h4_compute_governor_canonical_closure_minimal.sh`
- `helper_scripts/maintenance_scripts/bybit_connector/run_h5_ai_cost_governance_canonical_closure_minimal.sh`

These are currently the authoritative minimal chapter-closure runners for the repaired H-chain.

---

## Path rule

New business-logic changes for the canonical H-chain should be made here first.

Do not introduce new hardcoded `/home/ncyu/srv` paths in newly-refactored code unless there is an explicit compatibility reason.

Prefer:
- repo-relative resolution
- shared path helper
- centralized runtime path definitions

---

## Wrapper rule

Older flat `scripts/` entrypoints may still exist as compatibility wrappers.

Those wrapper paths should not be treated as the canonical location for new edits unless a file has not yet been migrated.

---

## Important operational note

H-chapter closure does **not** mean live trading approval.

It only means:
- the audit semantics are now coherent
- legal no-call is formally accepted
- read-only governance remains intact

It does **not** mean:
- execution authority granted
- decision lease emitted
- live operator ack enabled
- live execution allowed

