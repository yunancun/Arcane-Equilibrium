# WP2.1 Training Run PIT Manifest Gate - QA Source Acceptance

Date: 2026-07-07

Role: `QA(worker)`

Status: `DONE`

Verdict: `PASS`

Task: `WP2.1-TRAINING-RUN-PIT-MANIFEST-GATE`

## Scope

This is a source-only phase acceptance. I did not run runtime, DB, exchange, secret,
deploy, restart, Cost Gate, order/probe, live/mainnet, or bounded Demo outcome
ingestion checks.

Required input reports were read:

- PM intake: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-07--ai_ml_downstream_closure_loop_intake.state_packet.json`
- PA design: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-07-07--wp2_1_training_run_pit_manifest_gate_design.md`
- E1 implementation: `docs/CCAgentWorkSpace/E1/workspace/reports/2026-07-07--wp2_1_training_run_pit_manifest_gate_implementation.md`
- E2 review: `docs/CCAgentWorkSpace/E2/workspace/reports/2026-07-07--wp2_1_training_run_pit_manifest_gate_review.md`
- E2 re-review: `docs/CCAgentWorkSpace/E2/workspace/reports/2026-07-07--wp2_1_training_run_pit_manifest_gate_rereview.md`
- E4 regression: `docs/CCAgentWorkSpace/E4/workspace/reports/2026-07-07--wp2_1_training_run_pit_manifest_gate_regression.md`

Dirty worktree note: unrelated memory, GUI/auth, IBKR, and PM files were present. I did
not touch, revert, format, stage, commit, or push them.

## Chain Acceptance

PASS.

The required chain is complete for source closure:

`PM -> PA -> E1 -> E2 -> E1-return-fix -> E2 re-review -> E4 -> QA -> PM`

- PM intake selected WP2.1 as the first incomplete source-safe downstream item and denied runtime/DB/exchange/secret/deploy/order/Cost Gate/live/bounded-Demo-outcome actions.
- PA marked the work `E1_READY_SOURCE_ONLY`.
- E1 implemented the PIT manifest gate, then fixed E2 return items.
- E2 initial verdict was `RETURN_TO_E1` for atomic persistence and missing pooled-symbol permanent coverage.
- E2 re-review closed both findings and returned `PASS_TO_E4`.
- E4 regression returned `PASS`.
- This QA report returns `PASS` to PM for source-only phase acceptance.

## Source Behavior Acceptance

PASS.

Contract-bound quantile training is gated before train/export/registry:

- `run_training_pipeline.py` resolves PIT binding at `_run_quantile_pipeline(...)` before `train_quantile_trio(...)`.
- PIT gate failures return before `quantile_train`.
- Acceptance report persistence and PIT report hash verification happen before ONNX export and registry registration.

Acceptance report binding is canonical:

- `quantile_reports.generate_acceptance_report(...)` writes top-level `pit_dataset_manifest` and `pit_dataset_manifest_binding`.
- The binding schema is `training_pit_manifest_binding_v1`, includes `manifest_hash`, `manifest_path`, validation fields, candidate scope when present, and no-authority false flags.
- Contract-bound dry-run emits a deterministic synthetic manifest labelled `synthetic_training_dry_run`; this is source-gate evidence only, not ProofPacket, bounded Demo outcome, or promotion proof.

Non-contract-bound behavior remains explicit:

- Non-contract-bound callers receive `pit_dataset_manifest=None`.
- Binding has `contract_bound_run=false`, `validation_verdict=not_required`, and `validation_reason=not_contract_bound`.

Fail-closed behavior is covered:

- Pooled symbols `None` and `"ALL"` fail closed for contract-bound runs.
- Legacy scorer path with `contract_bound_run=True` fails closed with `contract_bound_quantile_path_required`.
- Missing manifest, invalid hash, candidate-scope mismatch, unpinned query, and leakage overlap fail before quantile training.

Atomic persistence is protected:

- PIT sidecar writes through a same-directory temp file and `Path.replace()`.
- Acceptance report persistence writes through a same-directory temp JSON and `Path.replace()`.
- Required persistence fails loud; optional persistence remains fail-soft.
- Focused tests prove existing final artifacts are preserved when sidecar/report writes fail.

## Verification Evidence

PASS.

E4 evidence is sufficient for source closure:

| Check | Evidence | Status |
|---|---|---|
| `py_compile` | WP2.1 training/report/manifest/registry files | PASS |
| Focused WP2.1 pytest | `46 passed, 1 skipped` x2 | PASS |
| Registry adjacency pytest | `49 passed` x2 | PASS |
| QA adjacency pytest | `90 passed, 1 skipped` x2 | PASS |
| Diff check | requested WP2.1 paths | PASS |

QA source-only checks additionally performed:

- `git diff --check` limited to WP2.1 source/report paths: PASS.
- Forbidden-surface grep limited to WP2.1 source/test files: only matched explicit false authority flags and comments; no executable runtime/DB/exchange/secret/deploy/order/live path found.
- Line count check: `run_training_pipeline.py` is 1005 lines, above the 800-line review-attention threshold but below the 2000-line hard cap.

I did not rerun the full E4 pytest matrix because E4 already ran each required focused/adjacent suite twice and the task requested source-only acceptance.

## Boundary Acceptance

PASS.

No boundary violation was found in the WP2.1 source delta or reports:

- No runtime mutation.
- No DB read/write/migration.
- No exchange/public quote/private read.
- No credential or secret access.
- No order/probe/cancel/modify.
- No Cost Gate change.
- No deploy/restart/env/crontab mutation.
- No live/mainnet behavior.
- No bounded Demo outcome ingestion.

## Residual Risks

Non-blocking for WP2.1 source acceptance:

- `program_code/ml_training/run_training_pipeline.py` is 1005 lines. This is an INFO-level review-attention item, below the 2000-line hard cap. E2 accepted it as non-blocking because PA explicitly scoped small private helpers into this file for WP2.1.
- The runtime/loss-control branch remains blocked by the latest standing Demo state: `OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED=0` and expired standing auth. No guardrail/materialization occurred, and that runtime state must not be consumed by WP2.1.
- WP2.1 does not ingest bounded Demo outcomes and does not close the runtime learning branch. Next runtime work still requires separate PM -> E3 -> BB review.

## Conclusion

QA source-only acceptance is PASS. WP2.1 can return to PM for source-phase sign-off.

Open blocker for this acceptance: none.

External blocker still active: runtime/loss-control branch remains blocked and must be handled separately before bounded Demo/runtime learning.

QA E2E ACCEPTANCE DONE: PASS · report path: `docs/CCAgentWorkSpace/QA/workspace/reports/2026-07-07--wp2_1_training_run_pit_manifest_gate_acceptance.md`
