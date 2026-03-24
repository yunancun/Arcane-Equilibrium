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
