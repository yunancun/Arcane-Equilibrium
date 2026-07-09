# E3 Review - ALR P2-2 Persistence Scope

E3_VERDICT: APPROVE_FOR_PM_BB_P2_2_SCOPE_REVIEW
CONFIDENCE: high

Reviewed request:
`docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-09--scanner_driven_alr_p2_persistence_e3_request.json`

## Evidence

- Mac `HEAD` and `origin/main` both resolve to `715334273` after the P2-1 push.
- Linux read-only preflight reached `trade-core`; its checkout and `origin/main`
  are both clean but stale at `0bafe2f9e`.
- The Linux host has `psql`, Docker, systemd user support, and the V030 scanner
  migration file; this demonstrates only isolated-test capability, not apply
  authority.
- The current checksum guard passes and allows a new V151+ migration while
  preventing edits to already locked migration bytes.
- Existing V134/V135 migrations establish the local append-only pattern:
  revoke `UPDATE, DELETE` from `PUBLIC` and `trading_ai`, grant only
  `INSERT, SELECT`, and make later state a new ledger row.
- P2-1 contains no credential-value pattern and no direct network, broker, or
  trading call/import.

## Security Findings

| Severity | Location | Attack path | Required control |
|---|---|---|---|
| HIGH if violated | Proposed V151/repository | Mutable state or UPSERT could rewrite provenance, hide a duplicate, or corrupt recovery. | All `learning.alr_*` ledgers append-only; source-key collision with different hash raises; recovery/watermark uses new events only. |
| HIGH if violated | Proposed repository | Scanner-derived identifiers interpolated into SQL could create injection or cross-table access. | Fixed SQL identifiers; bind every scanner/value parameter; no dynamic schema/table/column path. |
| HIGH if violated | Linux apply | Stale Linux checkout could apply a schema that lacks the reviewed source contract. | Do not apply until Mac/GitHub/Linux heads are identical and Linux remains clean. Use only `V151` dry-run then single-migration apply. |
| MEDIUM | Proposed service boundary | A persistence worker could accidentally become an authority or read secrets/broker paths. | P2-2 adds no service, API route, broker client, credential read, order/lease/Cost Gate/serving/promotion integration. |

## Conditions

1. New migration must be V151 or later, only create `learning.alr_*` objects,
   contain Guard A/B schema checks, and never alter/drop existing tables.
2. Isolated Docker PostgreSQL must apply the migration twice and exercise
   parameterized repository insert, duplicate, hash-conflict, restart-recovery,
   and provenance-edge cases before existing-PG consideration.
3. The final preapply recheck must prove equal Mac/GitHub/Linux heads, clean
   Linux worktree, checksum guard pass, and exact V151-only dry-run/apply scope.
4. No scanner read, existing-PG write, service start, retention sweep, exchange
   call, order, Decision Lease, Cost Gate action, serving, promotion, or `_latest`
   action is approved by this review.

The E3 memory file has pre-existing unrelated dirty edits and was not modified.

E3 AUDIT DONE: 0 CRITICAL / 0 HIGH / 0 MEDIUM in the approved constrained scope.
