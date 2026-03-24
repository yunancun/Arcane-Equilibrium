# I10 Recheck Interpretation (2026-03-24)

## Purpose

This note clarifies the difference between the two I10-style recheck runners now present in the repo.

---

## 1. Legacy runner

Legacy file:

`helper_scripts/maintenance_scripts/bybit_connector/run_i10_clean_recheck.sh`

Interpretation:

- this runner is still oriented around older `decision_lease_chapter_*` artifacts
- it remains useful as a historical / legacy observer
- it is **not** the authoritative closure checker for the repaired canonical H1-H5 chain

Therefore:

- a legacy I10 warning or blocked output from this file does **not automatically mean**
  the repaired canonical H-chain is broken

---

## 2. Authoritative canonical runner

Authoritative file:

`helper_scripts/maintenance_scripts/bybit_connector/run_i10_canonical_h_chain_recheck.sh`

Interpretation:

- this runner checks the current repaired canonical H-chain directly
- it reads:
  - H1 thought_gate final audit
  - H2 query_budget final audit
  - H3 model_router final audit
  - H4 compute_governor final audit
  - H5 ai_cost_governance final audit
- this is now the correct high-level closure checker for the current H chapter

---

## 3. Current accepted semantics

The repaired canonical H-chain now accepts the following terminal path as valid:

- `should_call_ai = false`
- `route_plan = route_skip`
- `no_call_path_accepted = true`

This means:

- no provider-native AI call may be needed
- no provider JSON response may be produced
- no usage tokens may be observed
- the chain may still close cleanly as a valid governed read-only path

---

## 4. Operational rule

For current project status checks:

- use `run_i10_canonical_h_chain_recheck.sh` as the authoritative H-chain observer
- treat `run_i10_clean_recheck.sh` as a legacy decision-lease-oriented observer only

---

## 5. Important caution

H1-H5 closure still does **not** mean:

- live execution approved
- execution authority granted
- decision lease emitted
- operator live ack enabled

It only means:

- the repaired H-chain now closes coherently
- legal no-call is formally accepted
- runtime remains protected and read-only

