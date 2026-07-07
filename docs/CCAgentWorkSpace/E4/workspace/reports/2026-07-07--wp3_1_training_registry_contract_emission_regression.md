# WP3.1 Training Registry Contract Emission Regression

Date: 2026-07-07

Role: `E4(worker regression)`

Status: `PASS`

Scope: `WP3.1-TRAINING-REGISTRY-CONTRACT-EMISSION`

This was a source-only regression pass after E2 verdict `PASS_TO_E4`.
Runtime/loss-control remains blocked and was not exercised.

## Inputs Read

- `AGENTS.md`
- `CLAUDE.md`
- `.codex/MEMORY.md`
- `README.md`
- `docs/agents/context-loading.md`
- `TODO.md`
- `.codex/agents/PM.md`
- `.codex/agents/E4.md`
- `.codex/AGENT_DISPATCH_PROTOCOL.md`
- `.codex/SUBAGENT_EXECUTION_RULES.md`
- `.claude/agents/E4.md`
- `.claude/skills/regression-testing-protocol/SKILL.md`
- `docs/CCAgentWorkSpace/PA/workspace/reports/2026-07-07--wp3_1_training_registry_contract_emission_design.md`
- `docs/CCAgentWorkSpace/E1/workspace/reports/2026-07-07--wp3_1_training_registry_contract_emission_implementation.md`
- `docs/CCAgentWorkSpace/E2/workspace/reports/2026-07-07--wp3_1_training_registry_contract_emission_review.md`

## Verification Commands

Run from `/Users/ncyu/Projects/TradeBot/srv`.

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 -m py_compile program_code/ml_training/registry_serving_contract.py program_code/ml_training/model_registry.py program_code/ml_training/run_training_pipeline.py program_code/ml_training/quantile_reports.py
```

Result: `PASS`, exit code 0, no stdout/stderr output.

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 -m pytest -q program_code/ml_training/tests/test_registry_serving_contract.py program_code/ml_training/tests/test_model_registry.py program_code/ml_training/tests/test_run_training_pipeline.py -p no:cacheprovider
```

Result: `74 passed in 0.66s`, exit code 0.

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 -m pytest -q program_code/ml_training/tests/test_run_training_pipeline.py program_code/ml_training/tests/test_quantile_reports.py program_code/ml_training/tests/test_pit_dataset_manifest.py program_code/ml_training/tests/test_pit_dataset_manifest_builder.py program_code/ml_training/tests/test_registry_serving_contract.py program_code/ml_training/tests/test_model_registry.py -p no:cacheprovider
```

Result: `106 passed, 1 skipped in 0.79s`, exit code 0.

Optional focused/adjoining flake sniff:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 -m pytest -q program_code/ml_training/tests/test_registry_serving_contract.py program_code/ml_training/tests/test_model_registry.py program_code/ml_training/tests/test_run_training_pipeline.py -p no:cacheprovider
```

Result: `74 passed in 0.61s`, exit code 0.

```bash
git diff --check -- program_code/ml_training/registry_serving_contract.py program_code/ml_training/run_training_pipeline.py program_code/ml_training/tests/test_registry_serving_contract.py program_code/ml_training/tests/test_model_registry.py program_code/ml_training/tests/test_run_training_pipeline.py docs/CCAgentWorkSpace/E1/workspace/reports/2026-07-07--wp3_1_training_registry_contract_emission_implementation.md docs/CCAgentWorkSpace/E2/workspace/reports/2026-07-07--wp3_1_training_registry_contract_emission_review.md
```

Result: `PASS`, exit code 0, no stdout/stderr output.

## Boundary Statement

This regression was source-only. I did not modify product code, stage, commit,
push, read/write DB, touch runtime services, restart/deploy, access exchange or
secrets, place orders/probes, change Cost Gate, symlink/promote/reload models,
or perform live/mainnet actions.

Existing unrelated dirty files under `memory/*`, IBKR, and Bybit
`control_api_v1` were observed in `git status` and left untouched.

## Residual Risk

- Runtime/loss-control remains blocked, so no DB registry persistence,
  model-serving reload, symlink promotion, runtime integration, or live/demo
  authority path was validated here.
- `program_code/ml_training/run_training_pipeline.py` remains above the
  800-line review-attention threshold; this pass did not refactor it.
- Regression coverage is scoped to the requested source-only WP3.1 and adjacent
  ml_training tests, not a repository-wide Python/Rust full regression.

## Verdict

`E4 REGRESSION DONE: PASS`
