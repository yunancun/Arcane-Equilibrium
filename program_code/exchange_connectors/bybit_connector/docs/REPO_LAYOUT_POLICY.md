# BybitOpenClaw Repository Layout Policy

## Core rule

The repository preserves the old `srv`-style project skeleton at the repo level, but keeps the actual connector script files physically flat under:

`program_code/exchange_connectors/bybit_connector/scripts/`

## Why

This project has a large amount of historical shell tooling, absolute-path references, and operator habits built around the flat script layout. A physical relocation inside `scripts/` creates excessive compatibility burden and audit confusion.

## Therefore

- Repo-level skeleton should follow old `srv` style as much as practical.
- Script-level physical layout remains flat unless a future migration is explicitly designed, reviewed, and compatibility-tested.
- Logical grouping is handled by documentation and index files, not by moving files into subfolders.
- Runtime payloads, logs, secrets, and local environment artifacts are local-only and must not be committed to GitHub.

## Current live/local rule

- Canonical project root: `/home/ncyu/BybitOpenClaw`
- Compatibility access path: `/home/ncyu/srv` (symlink to the repo-local `srv`)
- Local runtime payloads may be attached under the repo-local skeleton without entering Git history.

## Migration safety rule

Before any future file relocation:
1. preview
2. compile check
3. compatibility check
4. git status review
5. only then commit

If a relocation changes operator readability but breaks old expectations, operator readability preference wins only when compatibility is preserved or intentionally redesigned.

---

## Compatibility-wrapper migration rule / 兼容包装器迁移规则

When a script family is migrated to its canonical old-srv-style directory:

1. real implementation files move to the canonical directory;
2. old flat entrypoints under `scripts/` stay as compatibility wrappers;
3. docs must state canonical path clearly;
4. migration should preserve operator habit, runtime path compatibility, and rollback simplicity.

<!-- P7C_DECISION_LEASE_BATCH1_CANONICAL_START -->
## Decision-lease batch1 canonical path update (2026-03-24)

Canonical implementation path for the migrated batch1 core schema/preflight files is now:

`program_code/trade_executor/bybit_decision_lease/`

Legacy compatibility entrypoints are intentionally preserved under:

`program_code/exchange_connectors/bybit_connector/scripts/`

Those legacy files are now compatibility wrappers and should not be treated as the primary implementation source for the files listed below.

### Migrated files
- `bybit_decision_lease_chapter_contract_check.py`
- `bybit_decision_lease_chapter_final_audit.py`
- `bybit_decision_lease_chapter_handoff.py`
- `bybit_decision_lease_chapter_summary.py`
- `bybit_decision_lease_final_audit.py`
- `bybit_decision_lease_preflight.py`
- `bybit_decision_lease_preflight_contract_check.py`
- `bybit_decision_lease_schema.py`
- `bybit_decision_lease_schema_contract_check.py`

### Migration rule
- canonical implementation: `program_code/trade_executor/bybit_decision_lease/`
- compatibility wrapper: `program_code/exchange_connectors/bybit_connector/scripts/`
- new edits should target the canonical implementation first
<!-- P7C_DECISION_LEASE_BATCH1_CANONICAL_END -->

<!-- P7E_DECISION_LEASE_BATCH2_2026_03_24 -->
## Decision lease migration progress — batch2 (2026-03-24)
Batch2 (`consume / replay / shadow`) has been migrated to the canonical implementation directory:
`program_code/trade_executor/bybit_decision_lease/`

Rule remains unchanged:
- canonical implementation = target category directory
- legacy flat path under `bybit_connector/scripts/` = compatibility wrapper only
- new business logic changes should be made only in the canonical file

<!-- CANONICAL_PATH_NOTE_DECISION_LEASE_BATCH3 -->
## Decision Lease Migration Progress / Decision Lease 迁移进度

Completed canonical migrations under:

`program_code/trade_executor/bybit_decision_lease/`

Completed batches:
- batch1: core_schema_preflight
- batch2: consume_shadow_replay
- batch3: friction_adaptive_approval

Policy remains:
- canonical implementation lives in target domain directory
- old flat `scripts/` entry remains wrapper-only during transition
- wrappers are removed only after full caller cleanup and verification
<!-- /CANONICAL_PATH_NOTE_DECISION_LEASE_BATCH3 -->
