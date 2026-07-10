# PM R4 Request - GLOBAL_QUALIFIED_AUTONOMOUS_LEARNING_SHADOW_V1 WP1 Runtime

Date: 2026-07-10
Authority chain: `PM -> E3 -> BB -> PM`
Exact target: `7d1c247947f0fb6c139f8a0583c5e6ed6ae62c70`
State requested: `WP1_R4_INTERPRETER_GUARD_REPAIR`

R3 stopped before temp creation. Root cause: the fixed venv interpreter path
is a normal symlink, but the guard required its resolved Homebrew binary path
to equal the symlink string. Independent checks confirm no PG, port, worktree,
or temp residue.

R4 changes one preflight assertion only:

- Keep the fixed symlink path exactly
  `/Users/ncyu/Projects/TradeBot/srv/venvs/mac_dev/bin/python`.
- Resolve it, require the resolved target executable, and require SHA-256
  `fe46716a94d8efa4514feb3c39ba3e270deee2187556986f6ddcff54aba7bb9a`,
  Python `3.12.13`, psycopg2 `2.9.11`, and target-root ALR module provenance.
- Do not require the resolved path string to equal the symlink path.

All R2/R3 target, protected drift, outer cleanup, fixture assertions, Linux
merge, ALR-only restart, 420-second soak, rollback, and exclusions remain
unchanged. One attempt only; no retry under R4.
