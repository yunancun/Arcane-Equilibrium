# WP3.1 Training Registry Contract Emission QA Acceptance

Date: 2026-07-07

Role: `QA(worker)`

Status: `DONE`

QA E2E ACCEPTANCE DONE: `PASS`

Scope: `WP3.1-TRAINING-REGISTRY-CONTRACT-EMISSION`

This is source-only acceptance. Runtime/loss-control remains blocked and this
QA pass did not exercise runtime, DB, exchange, order/probe, deploy, live, or
model-serving paths.

## Inputs Read

- `AGENTS.md`
- `CLAUDE.md`
- `.codex/MEMORY.md`
- `README.md`
- `docs/agents/context-loading.md`
- `TODO.md`
- `.codex/agents/PM.md`
- `.codex/agents/QA.md`
- `.codex/AGENT_DISPATCH_PROTOCOL.md`
- `.codex/SUBAGENT_EXECUTION_RULES.md`
- `.claude/agents/QA.md`
- `docs/CCAgentWorkSpace/QA/profile.md`
- `docs/CCAgentWorkSpace/QA/memory.md`
- `docs/CCAgentWorkSpace/PA/workspace/reports/2026-07-07--wp3_1_training_registry_contract_emission_design.md`
- `docs/CCAgentWorkSpace/E1/workspace/reports/2026-07-07--wp3_1_training_registry_contract_emission_implementation.md`
- `docs/CCAgentWorkSpace/E2/workspace/reports/2026-07-07--wp3_1_training_registry_contract_emission_review.md`
- `docs/CCAgentWorkSpace/E4/workspace/reports/2026-07-07--wp3_1_training_registry_contract_emission_regression.md`

## Acceptance Checklist

| Criterion | QA result | Evidence |
|---|---|---|
| Contract-bound quantile training emits valid `registry_serving_contract_v1` from acceptance report, PIT manifest/binding, feature/schema hashes, and q10/q50/q90 artifact bytes | PASS | `build_registry_serving_contract_from_training_acceptance(...)` requires PIT report/binding, cross-checks feature hashes, reads exact q10/q50/q90 artifact bytes, computes `artifact_hashes`, `serving_config_hash`, `contract_hash`, then calls `validate_registry_serving_contract(...)`. |
| Persisted acceptance report contains canonical contract | PASS | `_persist_acceptance_report_with_registry_contract(...)` attaches canonical `registry_serving_contract` via `attach_registry_serving_contract(...)` and same-directory atomic write before registry call. Test `test_contract_bound_quantile_path_persists_and_passes_registry_contract` reads the persisted report. |
| Same contract is passed to `register_quantile_trio_from_onnx_out(...)` | PASS | Pipeline stores one `registry_serving_contract` object, persists it, then passes the same object in `registry_kwargs`. Test asserts persisted contract equals passed contract. |
| Mismatched/missing PIT/feature/schema/artifact data fails before DB/connect | PASS | Builder raises `RegistryServingContractError` before `check_db_connectivity(...)`. Test `test_contract_build_failure_happens_before_registry_db_connect` patches DB precheck to hard-fail and observes missing trio failure with zero registry calls. |
| Authority flags remain no-authority | PASS | Contract generation sets `serving_mode="advisory_only"`, `not_authority=True`, `symlink_authority=False`, `promotion_serving_ready=False`; validator rejects authority aliases including `order_allowed`. |
| Non-contract-bound training emits no fake contract | PASS | Pipeline only builds/passes the contract when `pit_binding.contract_bound_run` is true. Test asserts non-contract-bound report and registry kwargs omit `registry_serving_contract`. |
| Focused evidence is sufficient for source acceptance | PASS | E1/E2/E4 all reported green focused tests; QA independently reran the requested focused pytest and diff-check successfully. |

## Commands And Results

Run from `/Users/ncyu/Projects/TradeBot/srv`.

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 -m pytest -q program_code/ml_training/tests/test_registry_serving_contract.py program_code/ml_training/tests/test_model_registry.py program_code/ml_training/tests/test_run_training_pipeline.py -p no:cacheprovider
```

Result: `74 passed in 0.62s`.

```bash
git diff --check -- program_code/ml_training/registry_serving_contract.py program_code/ml_training/run_training_pipeline.py program_code/ml_training/tests/test_registry_serving_contract.py program_code/ml_training/tests/test_model_registry.py program_code/ml_training/tests/test_run_training_pipeline.py docs/CCAgentWorkSpace/PA/workspace/reports/2026-07-07--wp3_1_training_registry_contract_emission_design.md docs/CCAgentWorkSpace/E1/workspace/reports/2026-07-07--wp3_1_training_registry_contract_emission_implementation.md docs/CCAgentWorkSpace/E2/workspace/reports/2026-07-07--wp3_1_training_registry_contract_emission_review.md docs/CCAgentWorkSpace/E4/workspace/reports/2026-07-07--wp3_1_training_registry_contract_emission_regression.md
```

Result: `PASS`, exit code 0, no output.

Additional source checks:

- Reviewed `program_code/ml_training/registry_serving_contract.py`, `run_training_pipeline.py`, and `model_registry.py` wiring around contract build, persistence, artifact hash verification, and registry call.
- Ran focused `rg` boundary scan over the WP3.1 source/test/report set. Hits were denied-boundary vocabulary, existing test fixtures/comments, or existing model-registry mock/adjacent tests; no new runtime/exchange/secret/order/deploy path was introduced by the WP3.1 builder or pipeline wiring.

## Boundary Statement

No denied boundary action was performed or introduced in this QA pass: no
runtime mutation, DB empirical read/write, DB migration, exchange/private read,
secret access, order/probe, Cost Gate action, deploy, live/mainnet action,
symlink promotion, or model reload.

The WP3.1 source patch itself is limited to `program_code/ml_training` contract
builder/pipeline/test surfaces and reports. It does not edit Rust authority,
Decision Lease, Guardian, Bybit connector, GUI, cron, migrations, runtime
services, or deployment scripts.

## Dirty Worktree

`git status --short --branch` shows `main...origin/main [ahead 1]`.

Observed unrelated dirty files include:

- `docs/CCAgentWorkSpace/{PA,E1,E2,E4}/memory.md`
- `memory/*`
- `program_code/broker_connectors/ibkr_connector/api_absent_engineering.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/...`

These are outside WP3.1 acceptance scope and were ignored. I did not touch,
stage, commit, or revert them.

## Residual Risk

- Runtime/loss-control remains blocked, so this is not DB registry persistence
  acceptance and not serving/model-reload/symlink/live/demo authority evidence.
- `program_code/ml_training/run_training_pipeline.py` remains above the
  800-line review-attention threshold. The WP3.1 change is localized and this
  QA pass did not refactor it.
- Source acceptance covers the focused WP3.1 and adjacent ml_training tests, not
  a repository-wide regression.

## Verdict

`WP3.1-TRAINING-REGISTRY-CONTRACT-EMISSION` is accepted for source-only scope.
