# Standing Demo False-Negative Preflight Runtime Sync Apply

| Field | Value |
|---|---|
| `blocker_id` | `P1-RUNTIME-HEALTH-HYGIENE-STANDING-DEMO-FALSE-NEGATIVE-PREFLIGHT-SYNC-REVIEW` |
| `state_transition` | `DONE_WITH_CONCERNS` |
| `old_runtime_head` | `69f6c4b28a5ec1d1bee89d8cdbfe192c44f37f64` |
| `target_runtime_head` | `e29c96cc754d6599a541ff058aea3a9a20817bf3` |
| `runtime_summary` | `/tmp/openclaw/runtime_hygiene/standing_demo_false_negative_preflight_sync_20260626T224251Z/summary.json` |
| `runtime_summary_sha256` | `73bb60f6b0cff9e2aa09335845c3a99ecb27ecc113c20e6dec29ac11baa610d4` |
| `crontab_pre_sha256` | `4de259e1fe0ed732788544c0b6b77d523089f73c9efba809f7cc6c3b8b43c3f0` |
| `crontab_post_sha256` | `8403678a9084aa6d0152dffca498c212609737934b0447f4f5507d75dc529817` |
| `next_blocker_id` | `P0-STANDING-DEMO-LOSS-CONTROL-ENVELOPE-RUNTIME-MATERIALIZATION-REVIEW` |

## E3 Go/No-Go

E3 returned `DONE_WITH_CONCERNS - GO for bounded apply`.

Allowed apply scope:

- Fast-forward only from `69f6c4b2...` to `e29c96cc...`.
- Replace exactly 11 crontab expected-head literals from old to target.
- No service restart, rebuild, cargo, manual cron run, env mutation, standing-envelope materialization, PG write/query, Bybit/API/order/cancel/modify path, Cost Gate change, writer/adapter enablement, or authority expansion.

E3 confirmed the diff scope was limited to TODO/docs/reports, cron wrappers, research helpers, and tests. No Rust, SQL/migration, service/systemd, settings, credential, secret, execution-engine, Bybit/API/order/cancel/modify, mainnet, adapter, or probe-outcome-recording expansion was present.

## Apply Result

Runtime source:

```text
head=e29c96cc754d6599a541ff058aea3a9a20817bf3
origin=e29c96cc754d6599a541ff058aea3a9a20817bf3
status=## main...origin/main
```

Crontab:

```text
lines=70
old=0
new=11
mainnet=0
adapter=0
record1=0
record0=1
standing_alpha=0
standing_cost=0
auth_alpha=0
auth_cost=0
```

Services stayed active without PID change:

```text
api_active=active
api_pid=2218842
watchdog_active=active
watchdog_pid=1538268
```

Verification:

```text
bash -n helper_scripts/cron/cost_gate_learning_lane_cron.sh helper_scripts/cron/alpha_discovery_throughput_cron.sh
git diff --check 69f6c4b28a5ec1d1bee89d8cdbfe192c44f37f64..e29c96cc754d6599a541ff058aea3a9a20817bf3
```

Both passed.

## Recovery Note

The first apply script exited before mutation because `grep` zero-match counting was not pipefail-safe. The second script fast-forwarded source but failed before crontab installation because `/usr/bin/crontab` truncated the long audit path to `.../crontab_`. PM verified the source-sync-only intermediate state, validated the candidate crontab content, copied it to short path `/tmp/openclaw/crontab_e29c96cc.txt`, and installed the same candidate successfully.

## Post-Sync Runtime Artifacts

Natural artifacts after sync still fail closed:

| Artifact | sha256 | mtime UTC | Status | Decision / authority |
|---|---|---|---|---|
| `profitability_path_scorecard_latest.json` | `8af6d7cc8fad5bb3457d01a47b121247908078b2482236f4ca3135613072cea9` | `2026-06-26T22:45:05.086029+00:00` | `PROFITABILITY_PATHS_PRESENT_BUT_EXECUTION_EVIDENCE_MISSING` | no profit proof |
| `bounded_probe_operator_authorization_latest.json` | `78f0247974d07a6da83f84972793420562862a2829026f9fb91917168f45c591` | `2026-06-26T22:45:04.946568+00:00` | `FALSE_NEGATIVE_PREFLIGHT_OPERATOR_REVIEW_REQUIRED` | `decision=defer`, no auth object, probe/order `false/false` |
| `false_negative_operator_review_latest.json` | `4998adbbae71dfe3c1fd03df75e7c2ff2f234896d439f26594c4887fcb39f3f9` | `2026-06-26T22:29:17.818112+00:00` | `PENDING_COST_GATE_FALSE_NEGATIVE_OPERATOR_REVIEW` | `decision=defer` |
| `false_negative_bounded_probe_preflight_latest.json` | `a4090eebe524abcd9bccdd1aafc2ee5684bd19105da050dcf90a03962179c396` | `2026-06-26T22:29:17.904243+00:00` | `OPERATOR_REVIEW_REQUIRED` | no runtime authority |

## Boundary

No service restart, rebuild, cargo, manual cron run, environment mutation, standing-envelope materialization, PG query/write, Bybit/API/order/cancel/modify, Cost Gate lowering, writer/adapter enablement, active probe/order/live authority, or profit/proof claim occurred.

Next work is not execution. It is to design and review the exact runtime standing Demo loss-control envelope materialization/configuration path so false-negative review/preflight can become ready/fail under machine-checkable bounds.
