# 2026-06-20 -- FlashDip L1 Short-Exit Replay Cron

## Scope

Turn the v246 manual L1 short-exit replay into a durable, read-only revalidation loop. The goal is to avoid losing the K6/N2/C3/nf0.5% 240m short-exit hypothesis just because the first candidate day had no L1 coverage.

Hard boundary: read-only PG, local artifact/log/heartbeat writes only, no engine/API restart, no rebuild, no strategy parameter change, no order/auth/risk/runtime mutation, no Bybit private/signed/trading call.

## Delivered

- Added `helper_scripts/cron/flash_dip_l1_short_exit_replay_cron.sh`.
- The wrapper:
  - uses `PGOPTIONS=-c default_transaction_read_only=on` plus the replay helper's readonly PG session;
  - writes dated replay artifacts under `/tmp/openclaw/research/tail_dislocation_meanrev/`;
  - maintains `shallow_retune_l1_short_exit_replay_latest.json`;
  - appends compact status lines to `/tmp/openclaw/logs/flash_dip_l1_short_exit_replay.log`;
  - emits heartbeat `cron_heartbeat/flash_dip_l1_short_exit_replay.last_fire`;
  - uses mkdir lock `locks/flash_dip_l1_short_exit_replay_cron.lock.d`.
- Added static cron tests.
- Added alpha discovery runtime detail passthrough: FlashDip arm now includes `detail.l1_short_exit_replay`, but this does not change readiness/action semantics.

## Verification

- Mac:
  - `bash -n helper_scripts/cron/flash_dip_l1_short_exit_replay_cron.sh` PASS.
  - `python3 -m pytest -q helper_scripts/cron/tests/test_flash_dip_l1_short_exit_replay_cron_static.py` = 6 passed.
  - `PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_alpha_discovery_throughput.py` = 13 passed.
  - `PYTHONPATH=helper_scripts/research/tail_dislocation_meanrev python3 -m pytest -q helper_scripts/research/tests/test_tail_dislocation_shallow_retune.py` = 11 passed.
  - py_compile for `runtime_runner.py` and `shallow_retune_l1_short_exit_replay.py` PASS.
- Linux `trade-core` selective sync:
  - same bash syntax PASS.
  - cron static tests = 6 passed.
  - alpha discovery tests = 13 passed.
  - py_compile PASS.
- Linux manual read-only smoke:
  - status log latest: `/tmp/openclaw/logs/flash_dip_l1_short_exit_replay.log`
  - artifact: `/tmp/openclaw/research/tail_dislocation_meanrev/shallow_retune_l1_short_exit_replay_20260620T024620Z.json`
  - latest copy: `/tmp/openclaw/research/tail_dislocation_meanrev/shallow_retune_l1_short_exit_replay_latest.json`
  - latest sha256: `67670804402a58eee6f02e2dd1e3da590d7bfc806ebca5dbc71744688e3f48ee`
- Alpha discovery manual run confirmed `flash_dip_buy_demo.detail.l1_short_exit_replay.source_ok=true` and preserves verdict/fail reasons.

## Runtime Install

Installed Linux user cron:

```text
31 6 * * * OPENCLAW_BASE_DIR=$HOME/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/tmp/openclaw $HOME/BybitOpenClaw/srv/helper_scripts/cron/flash_dip_l1_short_exit_replay_cron.sh >> /tmp/openclaw/logs/flash_dip_l1_short_exit_replay_cron.cronout.log 2>&1
```

The entry was installed idempotently by removing prior matching lines before appending. No engine/API restart was performed.

## Result

Current smoke repeats v246's data gate:

- Verdict: `L1_SHORT_EXIT_INSUFFICIENT_SAMPLE`.
- Fail reasons: `no_l1_rows_for_candidate_window`, `gate_horizon_sample_below_min_filled`, `gate_horizon_sample_below_min_days`.
- Candidate events: 3 on one day, symbols `APTUSDT`, `ATOMUSDT`, `AVAXUSDT`.
- L1 rows: 0.
- Trade rows: 608,227.

PM read: the 240m short-exit path is now a durable monitored research lane. It is not promotion evidence; it becomes actionable only if future cron runs produce L1-covered samples and a conditional-pass replay, followed by QC/MIT/AI-E review and an E1 default-off design.
