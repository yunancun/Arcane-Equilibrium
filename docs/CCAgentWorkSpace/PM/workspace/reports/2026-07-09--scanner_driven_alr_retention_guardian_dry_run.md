# Scanner-Driven ALR Retention Guardian Dry Run

Date: 2026-07-09
Owner: PM
Status: `DONE`
Boundary label: `SOURCE_ONLY_OFFLINE_P0_P1`

## PM Sign-Off

PM SIGN-OFF: APPROVED.

`P0-AIML-ALR-RETENTION-GUARDIAN-DRY-RUN` is complete as a source-only dry-run
retention checkpoint. It adds a deterministic helper that consumes caller
provided artifact manifests and emits a single `retention_guardian_dry_run_v1`
JSON artifact. It does not delete, move, chmod, symlink, apply, prune, schedule,
or contact runtime/PG/IPC/exchange surfaces.

## Selection

The prior outcome bridge state was `ADVANCED`, and the stub queue marked
`P0-AIML-ALR-RETENTION-GUARDIAN-DRY-RUN` as the first `ACTIVE` row. This was the
last P0 row in the scanner-driven ALR source-only queue.

## Role Chain

Required implementation chain completed:

| Role | Status | Verdict |
|---|---|---|
| `PA(default)` | `DONE` | design approved standalone source-only dry-run scope |
| `E1(worker)` | `DONE_WITH_CONCERNS` | implemented two-file helper/tests |
| `E2(explorer)` | `DONE` | PASS after raw-schema, ref-graph, input-hash, and static-guard fixes |
| `E4(default)` | `DONE` | PASS after bounded-output and exclusive-create fixes |
| `QA(default)` | `DONE` | ACCEPT after output-dir and ancestor symlink guard |

E2 initially found missing artifact fields were masked by defaults, not all
reference fields entered the graph, static guard coverage was too narrow, and
`input_hashes` did not resolve by target `content_sha256`. PM patched each issue
and added regressions.

E4 then found output boundedness gaps for non-empty directories, output symlinks,
and non-exclusive writes. QA later found that symlinked output directories or
symlinked parents could redirect writes into forbidden targets. PM patched the
CLI to reject symlinked existing path components, re-check the resolved output
directory, reject non-empty output directories, reject output symlinks, and use
exclusive create.

## Implementation Delta

New source:

- `program_code/ml_training/alr_retention_guardian_dry_run.py`
  - defines `retention_guardian_artifact_manifest_v1` input and
    `retention_guardian_dry_run_v1` output helpers;
  - computes manifest, reference-graph, and output hashes;
  - protects proof/audit, dispute, lineage/provenance, negative-example,
    unknown-reference, and transitive-reference-contact artifacts;
  - allows tombstone proposal only for ordinary rebuildable or disposable
    scratch artifacts with no reference contact and valid metadata;
  - fails closed on raw missing/extra fields, malformed list fields, hash or
    metadata mismatch, duplicate ids/paths, unknown refs, latest refs, and
    output path contamination;
  - maps `input_hashes` to target artifacts by `content_sha256` when the hash is
    unambiguous;
  - exposes a single-shot CLI:
    `--artifact-manifest <input.json> --out-dir <output-dir>`;
  - writes exactly one bounded JSON output via exclusive create.
- `program_code/ml_training/tests/test_alr_retention_guardian_dry_run.py`
  - covers protected classes, transitive refs, unknown refs, all reference
    fields, `input_hashes` by `content_sha256`, raw schema default masking,
    latest rejection, forbidden output paths, non-empty output directories,
    output symlinks, output-dir and parent symlink rejection, and static guard.

## Verification

PM accepted:

```bash
PYTHONPATH=program_code PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile program_code/ml_training/alr_retention_guardian_dry_run.py program_code/ml_training/tests/test_alr_retention_guardian_dry_run.py
```

Result: `PASS`.

```bash
PYTHONPATH=program_code PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q program_code/ml_training/tests/test_alr_retention_guardian_dry_run.py -p no:cacheprovider
```

Result: `27 passed`.

```bash
PYTHONPATH=program_code PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q program_code/ml_training/tests/test_alr_retention_guardian_dry_run.py program_code/ml_training/tests/test_alr_outcome_bridge.py program_code/ml_training/tests/test_learning_target_arbiter.py program_code/ml_training/tests/test_alr_controller_contracts.py -p no:cacheprovider
```

Result: `124 passed`.

```bash
git diff --check -- program_code/ml_training/alr_retention_guardian_dry_run.py program_code/ml_training/tests/test_alr_retention_guardian_dry_run.py
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
`docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-09--scanner_driven_alr_retention_guardian_dry_run.state_packet.json`

Status: `DONE`

P0 source-only rows are complete:

- boundary packet: `DONE_WITH_CONCERNS`
- controller contracts: `DONE`
- learning target arbiter: `DONE`
- outcome bridge: `DONE`
- retention guardian dry-run: `DONE`

The foreground P0 source-development loop stops here with `DONE`. P1 rows remain
`DEFERRED_P0` and require explicit future PM activation before implementation.
