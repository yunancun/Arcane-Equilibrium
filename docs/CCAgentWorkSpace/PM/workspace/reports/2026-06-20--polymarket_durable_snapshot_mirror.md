# Polymarket durable snapshot mirror

Date: 2026-06-20

## Decision

Preserve Polymarket axis snapshot evidence outside volatile `/tmp` and make lead-lag IC consume that mirror without double-counting run IDs.

This fixes a profitability feedback-loop defect: after `/tmp/openclaw` was reset, Polymarket lead-lag lost accumulated snapshot history and fell back to `NO_SNAPSHOT_ROWS` / zero IC sample. That made the alpha discovery killboard wait on a moving target instead of accumulating evidence toward a real candidate verdict.

## Implementation

- `polymarket_axis` now supports `--mirror-artifact-root`.
- `polymarket_axis_cron.sh` defaults `OPENCLAW_POLYMARKET_AXIS_MIRROR_ROOT` to `$BASE/../archive/polymarket_axis_runs`.
- Completed run dirs are copied append-only; existing run IDs are not overwritten.
- `polymarket_leadlag` report schema/runner moved to v0.15.
- `polymarket_leadlag` now supports `--polymarket-mirror-root` and merges primary `/tmp` rows with mirror roots.
- Primary root wins on duplicate run IDs; mirror rows only fill missing run IDs.

## Runtime evidence

- Collector smoke mirrored run: `hourly-topn-20260620T215444Z`.
- Mirror status: `copied`.
- Mirror root: `/home/ncyu/BybitOpenClaw/archive/polymarket_axis_runs`.
- Mirror size after smoke: `12M`.
- Lead-lag latest sha256: `e86ca7daf701da329b76ee51deddc552005a829480a3b0926c30b4b6f8dfb4f7`.
- Lead-lag created: `2026-06-20T21:54:51.193211+00:00`.
- Snapshot rows: `2685`.
- Snapshot distinct timestamps: `3`.
- Distinct run dirs: `3`.
- Duplicate mirror run dirs skipped: `1`.
- Max overlap-adjusted IC points: `0`.
- Joined rows: `0`.
- Verdict: `INSUFFICIENT_SAMPLE`.
- Alpha latest sha256: `1619ca99dbfe10c22ee79d83cf44312aae434687c03fd4bfaa5ccfe94a4ff825`.
- Alpha created: `2026-06-20T21:54:56.634203+00:00`.
- Alpha status: `NO_ACTIONABLE_ALPHA_RESEARCH_BLOCKED`.

## Read

The mirror path works: lead-lag sees multiple snapshot timestamps after the collector smoke and reports the duplicate mirror run skip explicitly. This makes Polymarket evidence accumulation durable across `/tmp` cleanup.

It does not create a tradable signal. Current labels had not matured, so lead-lag still had zero joined IC rows and zero overlap-adjusted IC points. The next trigger remains ordinary capture and recomputation after enough label horizon maturity, followed by replay/history/execution-realism review if a candidate reappears.

## Verification

- TDD red first caught missing mirror functions before implementation.
- Mac research suites: `110 passed, 1 skipped`.
- Mac cron static suites: `22 passed`.
- Linux research suites: `110 passed, 1 skipped`.
- Linux cron static suites: `22 passed`.
- `py_compile`: passed.
- `bash -n`: passed.
- `git diff --check`: passed before documentation.
- Linux artifact-only collector, lead-lag, and alpha runtime smokes passed.

## Boundary

Source/test/docs plus selective Linux source sync, `/tmp/openclaw` artifact writes, and sibling archive artifact mirror writes only. No PG table write/schema migration, no Bybit private/signed/trading call, no engine/API rebuild/restart, and no credential/auth/risk/order/strategy mutation. Not signal, execution proof, or promotion proof.
