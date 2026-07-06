# WP2.1 Training Run PIT Manifest Gate - E2 Adversarial Review

Date: 2026-07-07

Role: `E2(explorer)`

Status: `DONE_WITH_CONCERNS`

Verdict: `RETURN_TO_E1`

Finding counts: CRITICAL 0, HIGH 0, MEDIUM 1, LOW 1, INFO 2.

## Scope

Reviewed declared WP2.1 diff only:

- `program_code/ml_training/run_training_pipeline.py`
- `program_code/ml_training/quantile_reports.py`
- `program_code/ml_training/tests/test_run_training_pipeline.py`
- `program_code/ml_training/tests/test_quantile_reports.py`

Read and applied the required operating context: `AGENTS.md`, `CLAUDE.md`, `.codex/MEMORY.md`, `README.md`, `docs/agents/context-loading.md`, `TODO.md`, `.codex/AGENT_DISPATCH_PROTOCOL.md`, `.codex/SUBAGENT_EXECUTION_RULES.md`, E2 profile/memory, PA design, E1 report, and PM intake state packet. Also read `.claude/agents/E2.md` and `pr-adversarial-review` because this is an E2 post-implementation review.

Dirty worktree note: `git status` shows unrelated dirty memory, PM/IBKR, GUI/auth, and bybit control-api files outside WP2.1. I did not revert, format, stage, or modify them. The in-scope code diff remains exactly the four WP2.1 files above.

## Stage 0 Spec Compliance

PASS:

- Contract-bound quantile runs resolve the PIT binding before `train_quantile_trio(...)`: `run_training_pipeline.py:646-668`.
- Missing manifest, bad manifest hash, candidate mismatch, unpinned/leakage source, pooled symbol, and legacy scorer contract-bound path fail before training. Focused tests cover all except pooled; I ran an ad-hoc source-only pooled probe and confirmed `train == 0`.
- ONNX export and registry call remain after acceptance report persistence and PIT report verification: `run_training_pipeline.py:722-801`.
- Dry-run synthetic manifest is deterministic and visibly labelled: `dataset_role="synthetic_training_dry_run"` in `run_training_pipeline.py:322-328`; binding authority flags are false in `PitBinding.to_report_binding`.
- Acceptance report uses canonical `pit_dataset_manifest` and `pit_dataset_manifest_binding` fields, no alias field: `quantile_reports.py:306-328`.
- Registry propagation stays on the existing acceptance-report JSONB path: `model_registry.register_quantile_trio_from_onnx_out(...)` lazily reads `acceptance_report_path` and passes the whole report to registry JSONB.
- Hard boundaries: no new runtime mutation, DB migration, exchange/private read, credential/secret access, order/probe, Cost Gate change, deploy, live/mainnet path, or bounded Demo outcome ingestion observed in the WP2.1 diff.

RETURN:

- PA design line 268 requires "no alias/partial-write drift". The implementation writes the PIT sidecar and acceptance report directly to their final paths, so partial/truncated artifact risk remains.

## Findings

### MEDIUM-1 - Contract artifacts are written directly to final paths, violating no partial-write drift

Location:

- `program_code/ml_training/run_training_pipeline.py:267-277`
- `program_code/ml_training/quantile_reports.py:413-436`
- PA requirement: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-07-07--wp2_1_training_run_pit_manifest_gate_design.md:264-268`

Evidence:

- `_write_pit_manifest_sidecar(...)` calls `path.write_bytes(...)` directly on `{strategy}_{engine_mode}_{symbol_slot}_pit_dataset_manifest.json`.
- `_maybe_persist(...)` opens the acceptance report final path with `"w"` and calls `json.dump(...)` directly.
- Both paths can truncate an existing valid artifact before a write failure or process crash. `persist_required=True` makes write errors fail-loud, and `run_training_pipeline.py:722-733` verifies the report hash after a successful write, but neither mechanism prevents a partial final file from being left behind.

Why this matters:

- WP2.1 makes the persisted acceptance report the source of truth for downstream WP3/WP6 consumption. A direct final-path write can leave a malformed or truncated report/sidecar with a deterministic canonical filename. That is exactly the "partial-write drift" class PA asked E2 to verify.

Required fix:

- Write both the PIT sidecar and acceptance report through a same-directory temporary file, then atomically replace the final path with `Path.replace()` / `os.replace()`.
- Preserve current fail-soft behavior for non-contract-bound report persistence, but for `persist_required=True` fail-loud without leaving or truncating the final artifact.
- Add focused tests that monkeypatch the write path to fail mid-persist or make `json.dump` raise, proving the old final file remains intact.

### LOW-1 - Pooled-symbol fail-closed case is not permanently covered by tests

Location:

- `program_code/ml_training/run_training_pipeline.py:438-440`
- `program_code/ml_training/tests/test_run_training_pipeline.py:296-454`

Evidence:

- Code correctly returns `pit_manifest_pooled_symbol_not_allowed` before training when `contract_bound_run=True` and `symbol` is `None` / `"ALL"`.
- E1 report claims pooled symbol is covered, but the committed focused tests do not include a pooled-symbol case. I verified it with an ad-hoc source-only probe:
  - result: `False pit_manifest_pooled_symbol_not_allowed ['etl', 'labels', 'pit_manifest_gate_failed'] {'train': 0}`

Required fix:

- Add a permanent test alongside the existing missing/hash/scope/leakage cases that asserts pooled symbol fails before `train_quantile_trio`.

## INFO

### INFO-1 - `run_training_pipeline.py` line count is acceptable for this patch, but should remain tracked

`run_training_pipeline.py` is 991 lines after this change. This exceeds the 800-line review-attention threshold but is below the 2000-line hard cap. PA explicitly asked for small private helpers in this file for WP2.1, and the helper group is cohesive around the PIT binding gate. I do not treat extraction as a RETURN blocker for this round. Recommended follow-up: after WP2.1/WP3 stabilizes, extract PIT binding helpers into an internal ML training helper module to reduce hot-file review cost.

### INFO-2 - E1 completion evidence is otherwise consistent

E1 report and memory state the task is source-only, uncommitted, and validated. I reproduced the focused checks below. The report's concern about the 991-line file is accurate.

## Verification Run By E2

Commands run from `/Users/ncyu/Projects/TradeBot/srv`:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 -m py_compile \
  program_code/ml_training/run_training_pipeline.py \
  program_code/ml_training/quantile_reports.py \
  program_code/ml_training/pit_dataset_manifest.py \
  program_code/ml_training/pit_dataset_manifest_builder.py \
  program_code/ml_training/model_registry.py
```

Result: passed.

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 -m pytest -q \
  program_code/ml_training/tests/test_run_training_pipeline.py \
  program_code/ml_training/tests/test_quantile_reports.py \
  program_code/ml_training/tests/test_pit_dataset_manifest.py \
  program_code/ml_training/tests/test_pit_dataset_manifest_builder.py \
  -p no:cacheprovider
```

Result: `41 passed, 1 skipped in 0.27s`.

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 -m pytest -q \
  program_code/ml_training/tests/test_model_registry.py \
  program_code/ml_training/tests/test_registry_serving_contract.py \
  -p no:cacheprovider
```

Result: `49 passed in 0.35s`.

```bash
git diff --check -- \
  program_code/ml_training/run_training_pipeline.py \
  program_code/ml_training/quantile_reports.py \
  program_code/ml_training/tests/test_run_training_pipeline.py \
  program_code/ml_training/tests/test_quantile_reports.py
```

Result: passed.

Additional ad-hoc pooled-symbol gate probe: passed, `train == 0`.

## Race / Worktree Checks

- `git fetch --prune origin` run at start and before report writing.
- HEAD: `8b99833b9e16e3b03efbc6e2198177672687b0ea`.
- `origin/main`: `798843f23b2fda66117cf95bfe7c996f97fdf543`.
- Branch is ahead 5, behind 0. This matches PM intake and TODO source-safe state.
- Recent `origin/main` commits in the 2h window are AI/ML roadmap/source docs commits already in PM intake; no new sibling push overlapped WP2.1 files during review.
- Reflog shows the expected 2026-07-06/07 AI/ML roadmap commit chain. Stash name-only inspection found no WP2.1 four-file overlap; I did not modify or drop any stash.

## Conclusion

The main gate logic is directionally sound and fail-closed before training/export/registry. Dry-run honesty and canonical report fields are present. However, the implementation misses PA's no-partial-write requirement for the two contract artifacts. Return to E1 for atomic persistence plus one pooled-symbol permanent test, then re-run E2 before E4.

E2 REVIEW DONE: `RETURN_TO_E1` · report path: `docs/CCAgentWorkSpace/E2/workspace/reports/2026-07-07--wp2_1_training_run_pit_manifest_gate_review.md`
