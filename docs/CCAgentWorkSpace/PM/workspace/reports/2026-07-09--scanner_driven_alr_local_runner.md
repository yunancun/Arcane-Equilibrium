# Scanner-Driven ALR Local Runner

Date: 2026-07-09
Owner: PM
Status: `DONE`
Boundary label: `SOURCE_ONLY_OFFLINE_P0_P1`

## PM Sign-Off

PM SIGN-OFF: APPROVED.

`P1-AIML-ALR-LOCAL-RUNNER` is complete as a source-only foreground helper. It
adds an explicit local runner that can compose one bounded P0 ALR component per
operator invocation, emit a validated state packet and report, and then exit. It
does not create a scheduler, daemon, service, sidecar, IPC listener, PG writer,
runtime hook, exchange path, proof/promotion path, Cost Gate change, `_latest`
promotion, or order/probe path.

## Selection

The P0 state packet ended at `P0_COMPLETE_P1_DEFERRED`. The operator prompt for
this session explicitly activated the P1 source-only rows and required the
foreground Codex loop to continue past P0. `P1-AIML-ALR-LOCAL-RUNNER` was the
first P1 implementation row.

## Role Chain

Required implementation chain completed:

| Role | Status | Verdict |
|---|---|---|
| `PA(default)` | `DONE` | design approved explicit source-only foreground runner scope |
| `E1(worker)` | `DONE` | implemented runner and tests |
| `E2(explorer)` | `DONE` | PASS after state/report selected-ref fixes |
| `E4(explorer)` | `DONE` | PASS after existing-empty output-dir fix |
| `QA(explorer)` | `DONE` | ACCEPT |

E2 initially found state/report mismatches around selected work-item semantics:
top-level previous state recovery was fixed, state packets now include the
controller contract fields, all-DONE queues keep an empty selection, and the
report uses the validated state packet's selected ref.

E4 found the existing-empty output-dir path was ambiguous because validation
allowed it but `mkdir(exist_ok=False)` produced a raw `FileExistsError`. PM
patched the runner to accept existing empty directories explicitly, revalidate
after directory creation, and keep non-empty and symlinked paths fail-closed.

## Implementation Delta

New source:

- `program_code/ml_training/alr_local_runner.py`
  - defines `alr_local_runner_manifest_v1` input and
    `alr_local_runner_report_v1` output helpers;
  - accepts only explicit `--manifest` and `--out-dir` CLI paths;
  - rejects `_latest` refs and symlinked output path components;
  - accepts new or existing-empty output directories, rejects non-empty output
    directories, and writes bounded JSON artifacts with exclusive create;
  - composes one bounded step: learning target, outcome bridge, retention
    dry-run, effect review, or state-only;
  - recovers completed artifact schemas from a caller-provided previous state
    packet for `auto` selection;
  - checks expected previous artifact hashes and emits `ROTATED` state on hash
    drift without running a component;
  - emits `alr_loop_state_packet_v1` and validates it with the controller
    contract before writing the report.
- `program_code/ml_training/tests/test_alr_local_runner.py`
  - covers each component step, evidence deferral, retention risk, hash
    rotation, previous-state auto selection, `_latest` rejection, authority flag
    rejection, non-empty and symlinked output rejection, existing-empty output
    acceptance, all-DONE queue selection, state/report ref consistency, and
    static guardrails for forbidden runtime surfaces.

## Verification

PM accepted:

```bash
PYTHONPATH=program_code PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile program_code/ml_training/alr_local_runner.py program_code/ml_training/tests/test_alr_local_runner.py
```

Result: `PASS`.

```bash
PYTHONPATH=program_code PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q program_code/ml_training/tests/test_alr_local_runner.py -p no:cacheprovider
```

Result: `15 passed`.

```bash
PYTHONPATH=program_code PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q program_code/ml_training/tests/test_alr_local_runner.py program_code/ml_training/tests/test_alr_controller_contracts.py program_code/ml_training/tests/test_learning_target_arbiter.py program_code/ml_training/tests/test_alr_outcome_bridge.py program_code/ml_training/tests/test_alr_retention_guardian_dry_run.py program_code/ml_training/tests/test_learning_effect_review.py -p no:cacheprovider
```

Result: `170 passed`.

```bash
git diff --check -- program_code/ml_training/alr_local_runner.py program_code/ml_training/tests/test_alr_local_runner.py
```

Result: `PASS`.

## Boundary

No denied action was performed or introduced:

- no runtime mutation;
- no PG read/write or migration;
- no IPC;
- no Bybit or official MCP contact;
- no Decision Lease;
- no order/probe;
- no Cost Gate change;
- no `_latest` overwrite;
- no serving/proof/promotion authority;
- no delete/apply/prune wrapper;
- no cron/daemon/scheduler/service/env mutation;
- no live/mainnet.

The helper contains denial vocabulary only as fail-closed validation terms and
test fixtures.

## State

State packet:
`docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-09--scanner_driven_alr_local_runner.state_packet.json`

Status: `DONE`

The foreground P1 source-development loop continues with
`P1-AIML-ALR-PERSISTENCE-DESIGN`, which is design/report only. It has no
migration creation, migration apply, PG contact, runtime, or service authority.
