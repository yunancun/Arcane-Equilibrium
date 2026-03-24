# BybitOpenClaw Repository Layout Policy

## 1. Core rule

The repository keeps an old srv-style project skeleton for compatibility, but canonical business-logic implementation should live in its logical target domain directory.

Examples:

- `program_code/ai_agents/bybit_thought_gate/`
- `program_code/trade_executor/bybit_decision_lease/`
- `program_code/exchange_connectors/bybit_connector/readonly_observer_pipeline/`
- `program_code/market_data_processor/bybit_business_events/`

Legacy flat script paths may remain during transition, but should be treated as wrappers or compatibility entrypoints where documented.

---

## 2. Canonical root

Canonical local repo root:

`/home/ncyu/BybitOpenClaw`

Current working repo-local source root in this clone:

`/home/ncyu/BybitOpenClaw/srv`

Compatibility access path:

`/home/ncyu/srv`

The compatibility path exists for old tooling and operator habits, but is **not** the preferred design target for new code.

---

## 3. Rule for new code

New code must not introduce fresh hardcoded references to:

`/home/ncyu/srv`

unless there is a documented compatibility reason.

Preferred approaches:

1. resolve paths relative to repo-local source files
2. use shared path helper modules
3. keep runtime / settings / secrets paths centralized and documented

---

## 4. Wrapper policy

When a script family is migrated to its canonical target directory:

1. the real implementation lives in the canonical directory
2. the old flat `scripts/` entrypoint may remain as a compatibility wrapper
3. new logic changes should target the canonical implementation first
4. wrappers are removed only after caller cleanup and verification

---

## 5. Runtime / local-only artifact rule

These remain local/operator artifacts and are not canonical source code:

- runtime payloads
- local logs
- local env files
- secrets
- DB payloads
- venvs
- backups / inventory outputs

These may exist inside the repo-local srv-style skeleton for operator convenience, but they should not be treated as GitHub-shareable code assets.

---

## 6. Current canonical migration status

### decision_lease
Canonical implementation directory:

`program_code/trade_executor/bybit_decision_lease/`

Status:
- migration complete
- legacy wrappers still retained during transition

### thought_gate_and_ai_governance
Canonical implementation directory:

`program_code/ai_agents/bybit_thought_gate/`

Completed canonical batches:
- query_budget
- model_router
- compute_governor
- H1 response / governed decision closure fixes
- H5 cost governance no-call compatibility fixes

Legacy flat-script paths remain compatibility entrypoints where still referenced by old tooling.

---

## 7. Current H chapter status

H1-H5 are now closed under the accepted no-call semantics:

- `should_call_ai = false`
- `route_plan = route_skip`
- `no_call_path_accepted = true`

This closure does not grant live execution permission.

Safety state remains:

- read_only
- disabled
- not_granted

---

## 8. Canonical runner baseline

Current minimal H chapter canonical runners:

- `run_h1_thought_gate_canonical_closure_minimal.sh`
- `run_h2_query_budget_canonical_closure_minimal.sh`
- `run_h3_model_router_canonical_closure_minimal.sh`
- `run_h4_compute_governor_canonical_closure_minimal.sh`
- `run_h5_ai_cost_governance_canonical_closure_minimal.sh`

These should be treated as the current authoritative minimal closure runners for H1-H5.

---

## 9. Migration safety rule

Before any future relocation or wide caller rewrite:

1. preview
2. compile check
3. compatibility check
4. git diff / git status review
5. only then commit

---

## 10. Immediate next policy

Before I-stage expansion continues:

1. complete path governance baseline
2. stop new old-root hardcoding
3. introduce shared path helpers
4. clean first batch of actively-used canonical code
5. only then continue I-stage development

