# Scanner-Driven ALR Statistical Selector Baseline

Date: 2026-07-09
Owner: PM
Status: `DONE`
Boundary label: `SOURCE_ONLY_OFFLINE_P0_P1`

## PM Sign-Off

PM SIGN-OFF: APPROVED.

`P1-AIML-ALR-STAT-SELECTOR-BASELINE` is complete as a source-only offline
selector helper. It ranks ALR learning targets from a caller-provided,
hash-bound snapshot and exits. It does not train a model, serve a model, mutate
runtime state, contact PG, contact IPC, contact Bybit or official MCP tooling,
acquire Decision Lease authority, place or probe orders, alter Cost Gate,
overwrite `_latest`, promote proof, delete/apply data, create a scheduler, or
grant live/mainnet authority.

## Selection

`P1-AIML-ALR-PERSISTENCE-DESIGN` completed as a proposal-only packet and left
`P1-AIML-ALR-STAT-SELECTOR-BASELINE` as the active queue row. The selected work
was a new source-only helper plus focused tests.

## Role Chain

The quant/design chain and implementation chain completed:

| Role | Status | Verdict |
|---|---|---|
| `QC(default)` | `DONE_WITH_CONCERNS` | required controlled VOI scoring, frozen universe, controls, OOS, uncertainty, retained non-selected candidates, and proof-gated `STOP_NO_EDGE` |
| `MIT(default)` | `DONE_WITH_CONCERNS` | required manifest fields and fail-closed split/control/OOS/negative/non-selected evidence |
| `AI-E(default)` | `DONE_WITH_CONCERNS` | kept model class offline deterministic statistical only; no LLM/RL/serving/runtime authority |
| `PA(default)` | `DONE` | selected new helper and tests |
| `E1(worker)` | `DONE` | implemented selector and E2 rework |
| `E2(explorer)` | `DONE` | PASS after raw-schema, formula, and evidence-gate fixes |
| `E4(explorer)` | `DONE` | PASS with no findings |
| `QA(explorer)` | `DONE` | ACCEPT |

E2 initially rejected the first implementation because it did not fully enforce
the top-level frozen-universe/split/policy schema, candidate raw evidence
schema, raw controlled formula, and evidence gates. E1 reworked the module, and
E2 passed the re-review.

E4 and QA both accepted the final state. Their residual concerns are
non-blocking: `proof_exclusion` is broad mapping-level validation, and nested
`_latest` rejection currently targets source/path/ref/alias carriers.

## Implementation Delta

New source:

- `program_code/ml_training/alr_stat_selector_baseline.py`
  - defines `alr_stat_selector_snapshot_v1` input and
    `alr_stat_selector_baseline_v1` output helpers;
  - accepts only explicit `--snapshot` and `--out` CLI paths;
  - rejects `_latest` paths and source/path/ref/alias refs;
  - validates frozen universe, pre-registered split, selector policy, raw
    candidate/control OOS statistics, matched controls, negative cells, regime
    labels, and required source-only flags;
  - computes score from raw candidate/control means, standard deviations, OOS
    counts, shrinkage toward `prior_delta_bps`, standard error, conservative
    lower confidence bound, VOI, offline cost, governance risk, staleness, and
    evidence-gap penalties;
  - sorts deterministically by score descending and candidate id ascending;
  - retains non-selected candidates in output;
  - returns `DEFER_EVIDENCE`, `HYPOTHESIS_ONLY`, `ROTATED`,
    `BLOCKED_BOUNDARY`, or proof-gated `STOP_NO_EDGE` as appropriate;
  - emits zero authority counters and hard false proof/promotion/runtime/
    trading/order/serving flags.
- `program_code/ml_training/tests/test_alr_stat_selector_baseline.py`
  - covers formula math, deterministic tie-breaks, retained non-selected
    candidates, missing required evidence, frozen-universe and split rejection,
    min-OOS evidence deferral, walk-forward deferral, `_latest` rejection, hash
    mismatch rotation, authority contamination blocking, proof-gated
    `STOP_NO_EDGE`, validation, extraction, and static import/call guards.

## Verification

PM accepted:

```bash
PYTHONPATH=program_code PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile program_code/ml_training/alr_stat_selector_baseline.py program_code/ml_training/tests/test_alr_stat_selector_baseline.py
```

Result: `PASS`.

```bash
PYTHONPATH=program_code PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q program_code/ml_training/tests/test_alr_stat_selector_baseline.py -p no:cacheprovider
```

Result: `20 passed`.

```bash
PYTHONPATH=program_code PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q program_code/ml_training/tests/test_alr_stat_selector_baseline.py program_code/ml_training/tests/test_learning_target_arbiter.py program_code/ml_training/tests/test_alr_controller_contracts.py -p no:cacheprovider
```

Result: `95 passed`.

```bash
PYTHONPATH=program_code PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q program_code/ml_training/tests/test_alr_controller_contracts.py program_code/ml_training/tests/test_learning_target_arbiter.py program_code/ml_training/tests/test_alr_outcome_bridge.py program_code/ml_training/tests/test_alr_retention_guardian_dry_run.py program_code/ml_training/tests/test_alr_local_runner.py program_code/ml_training/tests/test_alr_stat_selector_baseline.py -p no:cacheprovider
```

Result: `159 passed`.

```bash
git diff --check -- program_code/ml_training/alr_stat_selector_baseline.py program_code/ml_training/tests/test_alr_stat_selector_baseline.py
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
`docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-09--scanner_driven_alr_stat_selector_baseline.state_packet.json`

Status: `DONE`

The P1 source-only queue is complete. The next step is a source-only P2
readiness audit packet that summarizes the completed P0/P1 artifacts and names
the future exact-scope gates required before any runtime, exchange, proof,
promotion, or order-capable work.
