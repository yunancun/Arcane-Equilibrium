# Scanner-Driven ALR Persistence Design Packet

Date: 2026-07-09
Owner: PM
Status: `DONE_WITH_CONCERNS`
Boundary label: `SOURCE_ONLY_OFFLINE_P0_P1`

## PM Sign-Off

PM SIGN-OFF: APPROVED WITH CONCERNS.

`P1-AIML-ALR-PERSISTENCE-DESIGN` is complete as a design-only packet. It does
not create a migration, reserve a migration number in a mainline ledger, apply
DDL, contact PG, write mainline ADR/AMD files, backfill data, mutate runtime, or
grant any serving/proof/promotion/trading authority.

Boundary: `SOURCE_ONLY_OFFLINE_P0_P1`. This packet is `DESIGN_ONLY` /
`NOT_APPLIED`. It may contain ADR/AMD/spec proposal text only inside PM
workspace reports and Operator summary. It does not write `docs/adr/`,
`docs/governance_dev/amendments/`, root `TODO.md`, `sql/migrations/`, runtime
config, or any executable path.

## Selection

`P1-AIML-ALR-LOCAL-RUNNER` completed at commit
`eeb82579b6a9cdd52458d5eb79bcda6abb8b87a9` and updated the ALR stub queue to
mark `P1-AIML-ALR-PERSISTENCE-DESIGN` as `ACTIVE`. P1-B is a design/report row,
so it stays in PM workspace files only.

## Role Chain

Required design chain completed:

| Role | Status | Verdict |
|---|---|---|
| `CC(default)` | `DONE_WITH_CONCERNS` | keep ADR/AMD proposal text inside PM reports only; V### not created |
| `FA(default)` | `DONE_WITH_CONCERNS` | preserve raw JSON plus canonical hash as persistence authority |
| `PA(default)` | `DONE_WITH_CONCERNS` | synthesized append-only future schema and dry-run plan |

## Current Migration Observation

Local source-only observation:

```text
sql/migrations/V141__research_kline_calibration.sql
sql/migrations/V142__tick_orderbook_recorder.sql
sql/migrations/V143__l1_book_event_recorder.sql
sql/migrations/V144__strategist_promotions.sql
sql/migrations/V145__fills_maker_markout.sql
sql/migrations/V146__fills_maker_markout_comment_fix.sql
sql/migrations/V147__decision_features_label_source.sql
sql/migrations/V148__recorder_promotions_guard_retrofit.sql
sql/migrations/V149__recorder_compression_extension_guard.sql
sql/migrations/V150__governance_audit_log_earn_event_types.sql
```

No local `V151` or `V152` reference existed before this design packet. Therefore
the tentative future migration name is:

`V151__alr_persistence_foundation.sql`

Status: `PROPOSED_RESERVED_NOT_CREATED`.

This is not a migration reservation. A future exact-scope PG/migration session
must re-check local migration filenames, `origin/main`, and Linux
`_sqlx_migrations` before creating any file.

## Future Persistence Contract

Future implementation should use the `learning` schema and plain append-only
tables first. TimescaleDB should be deferred unless volume evidence justifies it.

Raw JSON plus canonical hash remains the authority. Typed columns exist only for
queryability and uniqueness; they must not replace reconstructable raw packets.

Proposed future objects:

| Object | Purpose | Proposed keys |
|---|---|---|
| `learning.alr_artifact_registry` | Immutable artifact row for every ALR source packet. | PK `artifact_hash`; unique `(artifact_id, schema_version, artifact_hash)`. |
| `learning.alr_artifact_edges` | Immutable graph edges between artifacts. | PK `edge_hash`; unique `(from_artifact_hash, to_artifact_hash, edge_role)`. |
| `learning.alr_run_state_ledger` | Append-only loop/run state packets. | PK `state_packet_hash`; unique `(run_id, state_packet_hash)`. |
| `learning.alr_learning_targets` | Projection for `learning_target_runtime_v1`. | PK `runtime_hash`; unique `(target_id, input_manifest_hash, runtime_hash)`. |
| `learning.alr_reward_records` | Projection for `reward_ledger_v1`. | PK `record_id`; unique `record_hash`. |
| `learning.alr_outcome_bridge_events` | Projection for `alr_outcome_bridge_v1`. | PK `bridge_hash`. |
| `learning.alr_effect_reviews` | Projection for review-only decisions. | PK `review_hash`; unique `(review_id, review_hash)`. |
| `learning.alr_retention_manifests` | Projection for retention dry-run manifests. | PK `manifest_hash`; includes `reference_graph_hash`. |

Minimum common fields:

- `schema_version`
- `boundary_label`
- `source_head` / `code_commit`
- `artifact_kind`
- `artifact_id`
- `artifact_hash`
- `canonical_payload_jsonb`
- `candidate_identity_jsonb`
- `input_refs_jsonb`
- `source_hashes_jsonb`
- `lineage_hashes_jsonb`
- `no_authority_jsonb`
- `authority_counters_jsonb`
- `created_at`
- `run_id`

Allowed edge roles:

- `input_snapshot`
- `proof_packet`
- `reward_record`
- `retention_ref`
- `loop_state`
- `previous_state`
- `outcome_bridge`
- `effect_review`

## Append-Only Rule

Future tables must be append-only:

- revoke or deny `UPDATE` and `DELETE` for application roles;
- allow only `SELECT` and `INSERT` to the future writer role;
- corrections are new events, never row mutation;
- supersede/replace uses `supersedes_artifact_hash` or `supersedes_event_hash`;
- rollback disables future readers/writers or adds a superseding event; it does
  not delete ALR provenance;
- physical `DROP` is allowed only in a separate exact scope after proving zero
  production rows.

## Future Guard Plan

Future migration scope must include:

- re-check local `sql/migrations/V*.sql`;
- re-check `origin/main`;
- re-check Linux `_sqlx_migrations`;
- Guard A for prerequisite schema/table existence;
- Guard B for type/nullability drift when objects already exist;
- Guard C for indexes, uniqueness, privileges, and constraints;
- canonical hash shape checks for raw JSON packets;
- double-apply idempotency;
- Linux PG rollback-only dry-run;
- app-role privilege reflection;
- explicit PM/MIT/E4 sign-off before any real `sqlx migrate run`.

No such PG dry-run or migration execution was performed in this row.

## Rollback Plan

If future implementation lands and must be backed out:

1. Disable future ALR persistence readers/writers by config or code in a separate
   exact-scope change.
2. Insert a superseding append-only event marking the previous schema/event as
   inactive.
3. Preserve raw payload rows and hashes for audit.
4. Do not backfill, rewrite, prune, delete, or mutate retained provenance inside
   this design scope.
5. Consider physical table removal only in a separate exact-scope migration after
   proving zero production rows and receiving explicit operator approval.

## Verification

Accepted source-only checks:

```bash
git ls-files 'sql/migrations/V*.sql' | sort -V | tail -n 10
```

Result: highest local migration file observed was
`V150__governance_audit_log_earn_event_types.sql`.

```bash
rg -n '^V151__|V151|V152' sql/migrations docs/CCAgentWorkSpace/PM/workspace docs/governance_dev docs/adr
```

Result before this packet: no local `V151`/`V152` references.

Final pre-commit checks are recorded in the effect review and state packet.

## Boundary

No denied action was performed or introduced:

- no root TODO import;
- no mainline ADR/AMD write;
- no migration creation;
- no migration apply;
- no backfill;
- no PG read/write or DDL;
- no Linux PG dry-run;
- no runtime mutation;
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

Stop as `BLOCKED_BOUNDARY` before tool use if work would require any of the
above.

## State

State packet:
`docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-09--scanner_driven_alr_persistence_design_packet.state_packet.json`

Status: `DONE_WITH_CONCERNS`

The foreground P1 source-development loop continues with
`P1-AIML-ALR-STAT-SELECTOR-BASELINE`.
