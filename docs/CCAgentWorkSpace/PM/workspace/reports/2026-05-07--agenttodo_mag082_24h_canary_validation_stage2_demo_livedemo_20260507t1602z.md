# AgentTodo MAG-082 24h Canary Validation: Stage 2 Window Start

Date: 2026-05-07
Status: RUNNING, operator-authorized Stage 2 window
Window: stage2_demo_livedemo_20260507t1602z

## Window Header

| Field | Value |
|---|---|
| Canary name | stage2_demo_livedemo_20260507t1602z |
| Runtime build commit | `e8a588529a65c2b5a62a2a5a6c79f0a58be9faac` |
| Mac source commit at authorization | `e8a588529a65c2b5a62a2a5a6c79f0a58be9faac` |
| Origin source commit at authorization | `e8a588529a65c2b5a62a2a5a6c79f0a58be9faac` |
| Linux source commit at authorization | `e8a588529a65c2b5a62a2a5a6c79f0a58be9faac` |
| Engine scope | Stage 2 only: `demo` / `live_demo` evidence. No Stage 3/4. No true-live primary autonomy. |
| Strategy scope | Current runtime active strategies: `grid_trading`, `ma_crossover`, `bb_reversion`; inactive: `bb_breakout`, `funding_arb`. |
| Symbol scope | Current runtime/snapshot symbols: `ADAUSDT`, `B3USDT`, `BILLUSDT`, `BTCUSDT`, `DOGEUSDT`, `ENAUSDT`, `ETHUSDT`, `ICPUSDT`, `JTOUSDT`, `LABUSDT`, `TAOUSDT`, `VIRTUALUSDT`, `XRPUSDT`, `ZECUSDT`. |
| Start time UTC | `2026-05-07T16:02:23Z` |
| Planned stop time UTC | `2026-05-08T16:02:23Z` |
| Actual stop time UTC | `running` |
| Rollback owner | Operator/user in Codex thread; PM-local execution |
| Live auth state | No live authorization mutation performed by this checkpoint. `OPENCLAW_ALLOW_MAINNET` absent from captured engine env. |
| OpenClaw route posture | Linux route contract test passed: `tests/test_openclaw_routes.py` 8/8. Active OpenClaw M8 posture remains read-only foundation. |

## Operator Authorization

The operator explicitly requested:

```text
rebuild, sync three sides, then allow Stage 2
```

This report records that Stage 2 is allowed to start for demo/live_demo
evidence collection only. It is not a MAG-082 PASS verdict and does not unblock
MAG-083/MAG-084 until the 24h evidence window completes and passes the MAG-082
checklist.

## Rebuild And Sync

- First rebuild attempt exited before service stop because remote non-login
  shell did not have `cargo` on PATH.
- Successful rebuild used the same script after sourcing `$HOME/.cargo/env`:
  `bash helper_scripts/restart_all.sh --rebuild --keep-auth`.
- Build finished in release mode with existing warnings only.
- Engine restarted cleanly with `--keep-auth`.
- API restarted with 4 workers.
- Post-rebuild process evidence:
  - engine PID: `3006073`;
  - API parent PID: `3006151`;
  - API `OPENCLAW_ENGINE_BINARY_SHA`:
    `cf402fe89c1e4ec39dd5c3a2aafc67df40e82d9b7cdd92219e5c26590034a52a`.
- Three-side source sync was clean at authorization:
  - Mac HEAD = origin/main = Linux HEAD =
    `e8a588529a65c2b5a62a2a5a6c79f0a58be9faac`.

## Captured Runtime Flags

Engine env captured from `/proc/3006073/environ` after rebuild:

```text
OPENCLAW_AUTO_MIGRATE=1
OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv
OPENCLAW_CANARY_MODE=1
OPENCLAW_DATABASE_URL_FILE=/tmp/openclaw/runtime_secrets/openclaw_database_url
OPENCLAW_DATA_DIR=/tmp/openclaw
OPENCLAW_ENABLE_PAPER=0
OPENCLAW_IPC_SECRET_FILE=/home/ncyu/BybitOpenClaw/secrets/environment_files/ipc_secret.txt
```

API env captured from `/proc/3006151/environ` after rebuild:

```text
OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv
OPENCLAW_DATABASE_URL_FILE=/tmp/openclaw/runtime_secrets/openclaw_database_url
OPENCLAW_DATA_DIR=/tmp/openclaw
OPENCLAW_ENGINE_BINARY_SHA=cf402fe89c1e4ec39dd5c3a2aafc67df40e82d9b7cdd92219e5c26590034a52a
OPENCLAW_IPC_SECRET_FILE=/home/ncyu/BybitOpenClaw/secrets/environment_files/ipc_secret.txt
OPENCLAW_REPLAY_FIXTURE_DEFAULT=/home/ncyu/BybitOpenClaw/srv/rust/openclaw_engine/tests/fixtures/replay_runner_e2e/synthetic_btcusdt.json
OPENCLAW_REPLAY_SIGNING_KEY_FILE=/home/ncyu/BybitOpenClaw/srv/rust/openclaw_engine/tests/fixtures/replay_runner_e2e/key.hex
```

Not changed by this checkpoint:

- `OPENCLAW_LEASE_ROUTER_GATE_ENABLED` was not enabled.
- `OPENCLAW_AGENT_EVENT_STORE_ENABLED` was not enabled.
- `OPENCLAW_AGENT_SPINE_CLIENT_ENABLED` was not enabled.
- `settings/risk_control_rules/scanner_config.toml` was not changed; missing
  `[authority]` still defaults to `legacy_gate`.
- `executor.shadow_mode` was not toggled false in committed demo/live config.

This keeps Stage 2 in an authorization/evidence-start posture. It does not
pre-approve Stage 3/4 promotion. Lease-router and full decision-spine evidence
must still exist before MAG-083 can pass.

## Start Watchdog Evidence

Command:

```bash
python3 helper_scripts/canary/engine_watchdog.py --data-dir /tmp/openclaw --stale-threshold 45 --grace-period 120 --status
```

Result after rebuild:

```json
{
  "engine_alive": true,
  "snapshot_age_seconds": 6.6,
  "snapshot_path": "/tmp/openclaw/pipeline_snapshot.json",
  "stale_threshold_seconds": 45.0,
  "engines": {
    "paper": {"alive": false, "age_seconds": 69.4},
    "demo": {"alive": true, "age_seconds": 6.6},
    "live": {"alive": true, "age_seconds": 6.6}
  }
}
```

Interpretation: demo and live-demo runtime paths are fresh. Paper is disabled
by `OPENCLAW_ENABLE_PAPER=0` and is out of this Stage 2 scope.

## Start Passive Healthcheck Evidence

Command:

```bash
bash helper_scripts/db/passive_wait_healthcheck.sh
```

Summary at `2026-05-07T16:00:58Z`: `FAIL`.

Relevant start-state failures and warnings:

- FAIL `[Xb] pipeline_triangulation`.
- FAIL `[42] live_candidate_eval_contract`.
- FAIL `[42b] live_candidate_attribution_drift`.
- FAIL `[42c] live_candidate_attribution_drift_3d`.
- FAIL `[50] replay_run_state_health`.
- FAIL `[51] scanner_opportunity_shadow_acceptance`.
- PASS `[52] agent_event_store_rows`: event-store disabled by env; row proof
  skipped.
- WARN `[33] maker_fill_rate`.
- WARN `[40] realized_edge_acceptance`.

Interpretation: Stage 2 is allowed to collect evidence, but this start state is
not promotion-clean. These pre-existing failures must be separated from any
new Stage 2 regression, and a final MAG-082 PASS cannot be claimed while
required lineage/lease evidence is missing.

## OpenClaw Route Evidence

Linux route contract:

```bash
python3 -m pytest tests/test_openclaw_routes.py -q
```

Result: `8 passed in 0.34s`.

## Current Verdict

```text
MAG-082 24h canary validation verdict: RUNNING
Window: stage2_demo_livedemo_20260507t1602z
Engine scope: demo/live_demo only
Decision count: pending 24h collection
Executable chain count: pending 24h collection
Non-shadow submit report count: pending 24h collection
Rollback used: no
Operator: user/operator in Codex thread
Timestamp UTC: 2026-05-07T16:02:23Z
```

Only a later PASS/WARN/FAIL update after the 24h window can feed MAG-083.
MAG-083 and MAG-084 remain blocked until this report is completed and MAG-083
passes.
