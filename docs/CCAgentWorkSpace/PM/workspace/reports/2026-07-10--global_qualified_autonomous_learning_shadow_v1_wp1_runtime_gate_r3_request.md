# PM R3 Request - GLOBAL_QUALIFIED_AUTONOMOUS_LEARNING_SHADOW_V1 WP1 Runtime

Date: 2026-07-10
Authority chain: `PM -> E3 -> BB -> PM`
Exact immutable target: `7d1c247947f0fb6c139f8a0583c5e6ed6ae62c70`
State requested: `WP1_R3_COMMAND_REPAIR_EXACT_SHADOW_ONLY`

R3 disposition: `FAILED_PREFLIGHT_NO_ACTION`. The fixed venv path is a normal
symlink to the Homebrew Python binary, but the wrapper incorrectly required its
`realpath` to equal the symlink path. It exited `11` before creating either
temp path. Independent checks found no PG, worktree, port, or directory
residue. R3 cannot be retried.

R2 failed before fixture ingestion. Root cause: target worktrees correctly omit
the gitignored Mac venv, but the script resolved Python relative to the
worktree. Contributing defect: the inner zsh EXIT trap did not stop/remove the
temporary PG on command-not-found. The independent mandatory residue audit
caught PID `13949` and the temp directory; authorized rollback stopped/removed
both and reverified port/process/directory/worktree clear. No Linux,
production, service, engine, exchange, or trading state changed.

R3 changes commands only; target, tests, fixtures, assertions, production
sequence, thresholds, and exclusions are identical to approved R2.

Binding repair:

- Source/migrations/PYTHONPATH stay rooted at the detached exact-target
  worktree.
- Python executable is an explicit separately verified absolute runtime:
  `/Users/ncyu/Projects/TradeBot/srv/venvs/mac_dev/bin/python`, never resolved
  inside the target worktree.
- The outer authorized wrapper owns both `mktemp` paths, records them before
  launch, captures the child exit code with `set +e`, and unconditionally runs
  `pg_ctl -m immediate`, removes PG/worktree paths, prunes the worktree
  registration, and performs independent residue checks before propagating
  success/failure. Inner cleanup remains defense in depth only.
- A missing interpreter, cleanup failure, or any residue stops R3 before Linux.

All R2 protected-path drift checks, Unix-socket-only PostgreSQL controls,
canonical and explicit probes, derived-cache zero, exact Linux merge,
ALR-only restart, 420-second thresholds, inactive rollback, and hard-boundary
exclusions remain mandatory. One attempt only; no retry under R3.
