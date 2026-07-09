# Scanner-Driven ALR Learning Target Arbiter

Date: 2026-07-09
Owner: PM
Status: `ADVANCED`
Boundary label: `SOURCE_ONLY_OFFLINE_P0_P1`

## PM Sign-Off

PM SIGN-OFF: APPROVED.

`P0-AIML-ALR-LEARNING-TARGET-ARBITER` is complete as a source-only arbiter
checkpoint. It adds a deterministic CLI for ranking offline learning targets by
expected value of information and writes only an explicit output artifact.

## Selection

The prior controller state was `ADVANCED`, and the stub queue marked
`P0-AIML-ALR-LEARNING-TARGET-ARBITER` as the first `ACTIVE` row.

## Role Chain

Required implementation chain completed:

| Role | Status | Verdict |
|---|---|---|
| `PA(default)` | `DONE` | design approved two-file source-only scope |
| `E1(worker)` | `DONE` | implemented, then reworked reviewer findings |
| `E2(explorer)` | `DONE` | final PASS after QA reject fixes |
| `E4(worker)` | `DONE` | PASS; `75 passed` adjacent regression |
| `QA(worker)` | `DONE` | ACCEPT |

E2 first found missing fail-closed coverage around `no_authority`,
`proof_exclusion`, and nested `_latest` source refs. E1 reworked those. E2 then
found a blocked source-tier case bypass; PM patched the tier normalization. QA
then rejected three fail-open cases: non-exact latest flags, case-sensitive
`_latest` detection, and separator variants such as `NO ORDER`. PM patched those
and added regression tests. E2 rereview passed, E4 passed, and QA accepted.

## Implementation Delta

New source:

- `program_code/ml_training/learning_target_arbiter.py`
  - defines `learning_target_snapshot_manifest_v1` and
    `learning_target_runtime_v1` contracts;
  - requires explicit `--snapshot` and `--out`;
  - rejects `_latest` in input path, output path, and nested source refs using
    case-insensitive matching;
  - requires `latest_alias_used` and any `source_path_latest` value to be exact
    `False`;
  - validates the input manifest hash and embeds the bound input reference in
    output;
  - ranks targets by
    `expected_information_gain + uncertainty_reduction - cost_estimate -
    risk_penalty - staleness_penalty`;
  - normalizes blocked source tiers across case, hyphen, underscore, and space
    variants before rejecting proof/reward/edge/promotion fields;
  - forces authority counters and flags to zero or false.
- `program_code/ml_training/tests/test_learning_target_arbiter.py`
  - covers explicit output, hash binding, `_latest` paths/refs including case
    variants, exact latest flags, manifest hash mismatch, objective mismatch,
    truthy `no_authority`, truthy `proof_exclusion`, blocked source-tier
    authority attempts, deterministic ranking, and zero/false authority output.

## Verification

PM accepted:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 -m py_compile program_code/ml_training/learning_target_arbiter.py program_code/ml_training/alr_controller_contracts.py
```

Result: `PASS`.

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 -m pytest -q program_code/ml_training/tests/test_learning_target_arbiter.py -p no:cacheprovider
```

Result: `33 passed`.

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 -m pytest -q program_code/ml_training/tests/test_learning_target_arbiter.py program_code/ml_training/tests/test_alr_controller_contracts.py -p no:cacheprovider
```

Result: `75 passed`.

Denied-surface scan on the arbiter source/test files: `PASS`. Matches are denial
vocabulary, fail-closed rejection logic, and CLI test harness only.

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
- no delete/apply;
- no cron/daemon/scheduler/service/env mutation;
- no live/mainnet.

The schema name includes `runtime` as an output artifact name only. It does not
grant live runtime authority.

## State

State packet:
`docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-09--scanner_driven_alr_learning_target_arbiter.state_packet.json`

Status: `ADVANCED`

Next row:

`P0-AIML-ALR-OUTCOME-BRIDGE`

Required next chain:

`PM -> PA -> E1/E1a -> E2 -> E4 -> QA -> PM`

The next row remains source-only and must not touch runtime, PG, IPC, Bybit/MCP,
scheduler, service/env, `_latest`, proof/promotion, delete/apply, Cost Gate,
order/probe, or live/mainnet.
