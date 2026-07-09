# RetentionGuardian P0 Contract

RetentionGuardian P0 is dry-run-only. It runs as an explicit single-shot
source/artifact CLI, emits only `retention_guardian_dry_run_v1` under the
requested output directory, and exits.

It performs no physical delete, no file move/rename/chmod, no symlink update,
no `_latest` overwrite, no PG read/write/delete/DDL, no Timescale policy change,
no network/runtime/Bybit/IPC/cron/daemon action, and does not call or wrap
existing prune/apply scripts.

## Manifest Schema

For every artifact, the dry-run manifest must include:

- `artifact_id`
- `canonical_path`
- `content_sha256`
- `size`
- `mtime`
- `producer`
- `schema_version`
- `candidate_identity`
- `source_hash`
- `input_hashes`
- `order_ids`
- `fill_ids`
- `context_ids`
- `outbound_refs`
- `inbound_refs`
- `report_refs`
- `todo_refs`
- `adr_refs`
- `amd_refs`
- `_latest_refs`
- `classification_reason`
- `retention_state`
- `blockers`
- `rebuild_or_disposable_proof`
- `proposed_action`

## Allowed P0 Retention States

- `PROOF_OR_AUDIT_PROTECTED`
- `DISPUTED_PROTECTED`
- `NEGATIVE_EXAMPLE_PROTECTED`
- `LINEAGE_PROVENANCE_PROTECTED`
- `REFERENCE_UNKNOWN_PROTECTED`
- `REBUILDABLE_SCRATCH_CANDIDATE`
- `QUARANTINE_CANDIDATE_DRY_RUN`
- `TOMBSTONE_STAGE_1_PROPOSED_DRY_RUN_ONLY`

## Never Ordinary Delete

The following must never be ordinary-delete candidates:

- proof packets
- reward ledgers
- orders
- fills
- fees
- slippage
- Decision Lease evidence
- authorization evidence
- Guardian, Risk Governor, or reconciliation evidence
- report-linked artifacts
- hidden OOS, control, or repeat evidence
- cleanup, unattributed, or proof-excluded facts
- failed, blocked, or `ROTATED` gate artifacts
- disputed examples
- negative examples
- falsification examples
- source lineage and provenance artifacts

## Fail-Closed Rules

Any missing schema field, parse failure, unresolved reference, hash mismatch,
path ambiguity, `_latest` ambiguity, rebuild ambiguity, or contact with proof,
dispute, audit, lineage, negative examples, or unknown references returns
`STOP_RETENTION_RISK` and classifies the artifact as protected.

Only ordinary scratch with complete transitive no-reference proof and
rebuildable-or-disposable proof may become
`TOMBSTONE_STAGE_1_PROPOSED_DRY_RUN_ONLY`.

## Tests And Static Guards

Tests/static guards must prove the helper imports no DB/network/runtime/order
modules and contains no executable delete/apply behavior:

- no `unlink`
- no `remove`
- no `rmtree`
- no SQL `DELETE`
- no prune apply call
- no env mutation
- no subprocess runtime call
- no symlink promotion
- no `_latest` writer

Golden tests must show proof/audit/disputed/negative examples are protected,
unknown references fail closed, and only unreferenced rebuildable scratch reaches
dry-run tombstone proposal.
