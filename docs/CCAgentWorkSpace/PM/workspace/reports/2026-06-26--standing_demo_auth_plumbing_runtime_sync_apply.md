# Standing Demo Auth Plumbing Runtime Sync Apply

Date: 2026-06-26 23:52 CEST

本輪推進 `P1-RUNTIME-HEALTH-HYGIENE-STANDING-DEMO-AUTH-PLUMBING-SYNC-REVIEW` 到 `DONE_WITH_CONCERNS`。執行的是 runtime source fast-forward + expected-head crontab literal replacement；沒有 service restart/rebuild、沒有 PG query/write、沒有 Bybit/API/order/cancel/modify、沒有 env authority expansion、沒有 Cost Gate lowering、沒有 writer/adapter enablement、沒有 active probe/order/live authority，也沒有 proof/profit claim。

## Required Round Output

| Field | Value |
|---|---|
| `active_blocker_id` | `P1-RUNTIME-HEALTH-HYGIENE-STANDING-DEMO-AUTH-PLUMBING-SYNC-REVIEW` |
| `blocker_goal` | Sync standing Demo auth source plumbing to Linux runtime and align expected-head pins without changing runtime authority. |
| `profit_relevance` | Runtime must load the standing-envelope plumbing before TradeBot can progress from defer-only auth churn toward bounded Demo evidence and after-cost PnL review. |
| `new_evidence_delta_found` | Source/origin `69f6c4b2` vs runtime `b224c759`; runtime artifacts refreshed but remained defer/no-authority; crontab still pinned old expected head. |
| `action_taken` | Fast-forwarded runtime source to `69f6c4b2`; replaced 11 crontab expected-head occurrences from `b224c759...` to `69f6c4b2...`; ran focused Linux Python/static checks and post-checks. |
| `status` | `DONE_WITH_CONCERNS` |
| `next_blocker_id` | `P0-STANDING-DEMO-FALSE-NEGATIVE-PREFLIGHT-PLUMBING` |

## E3-Style Go/No-Go

Diff range: `b224c759200d8dfc6fc4a53cbee39b8fb3683118..69f6c4b28a5ec1d1bee89d8cdbfe192c44f37f64`.

Findings:

- No `rust/`, `program_code/`, `sql/`, service, settings, credential, or secret path changes.
- Runtime-impacting paths are helper cron/research scripts and tests; added helpers are source-only no-order evidence/review tooling.
- Dangerous-token scan found no `OPENCLAW_ALLOW_MAINNET=1`, adapter enablement, probe outcome recording enablement, or true runtime/order authority changes.
- BB skipped: no exchange-facing API/read/order path was invoked or modified in this apply.

## Runtime Apply

Runtime source:

```text
before=b224c759200d8dfc6fc4a53cbee39b8fb3683118
after=69f6c4b28a5ec1d1bee89d8cdbfe192c44f37f64
status_lines_after=0
```

Crontab expected-head replacement:

```text
line_count_before=70
line_count_after=70
old_count_before=11
old_count_after=0
target_count_before=0
target_count_after=11
OPENCLAW_ALLOW_MAINNET=1 count=0
OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED count=0
OPENCLAW_COST_GATE_LEARNING_RECORD_PROBE_OUTCOMES=1 count=0
OPENCLAW_COST_GATE_LEARNING_RECORD_PROBE_OUTCOMES=0 count=1
standing Demo auth env count=0
```

Crontab backup/summary:

- `/tmp/openclaw/runtime_hygiene/crontab_pre_standing_demo_auth_plumbing_sync_20260626T2131Z.txt`
- `/tmp/openclaw/runtime_hygiene/crontab_post_standing_demo_auth_plumbing_sync_20260626T2131Z.txt`
- `/tmp/openclaw/runtime_hygiene/crontab_standing_demo_auth_plumbing_sync_summary_20260626T2131Z.json`
- `/tmp/openclaw/runtime_hygiene/crontab_live_after_standing_demo_auth_plumbing_sync_20260626T2131Z.txt`

Service sanity:

```text
openclaw-trading-api.service: MainPID=2218842, NRestarts=0, active/running
openclaw-watchdog.service: MainPID=1538268, NRestarts=1, active/running
```

## Runtime Verification

```text
PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_cost_gate_bounded_probe_operator_authorization.py
21 passed

python3 -m pytest -q --import-mode=importlib helper_scripts/cron/tests/test_alpha_discovery_throughput_cron_static.py helper_scripts/cron/tests/test_cost_gate_learning_lane_cron_static.py
24 passed

PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_cost_gate_false_negative_candidate_friction_scorecard.py helper_scripts/research/tests/test_profitability_path_scorecard.py helper_scripts/research/tests/test_alpha_discovery_throughput.py helper_scripts/research/tests/test_alpha_discovery_learning_worklist.py helper_scripts/research/tests/test_cost_gate_bounded_probe_result_review.py helper_scripts/research/tests/test_cost_gate_bounded_probe_execution_realism_review.py
140 passed

git diff --check
PASS

bash -n helper_scripts/cron/alpha_discovery_throughput_cron.sh
PASS

bash -n helper_scripts/cron/cost_gate_learning_lane_cron.sh
PASS

python3 -m py_compile helper_scripts/research/cost_gate_learning_lane/bounded_probe_operator_authorization.py helper_scripts/research/cost_gate_learning_lane/bounded_probe_operator_authorization_cli.py
PASS
```

## Runtime Artifacts After Sync

Natural refresh after sync remains fail-closed:

- Profitability scorecard sha `f437a41d93248360f47b48a2f0309345326bf784e17f3407dfa48b895623f245`, mtime `2026-06-26T21:45:04.741688Z`, status `PROFITABILITY_PATHS_PRESENT_BUT_EXECUTION_EVIDENCE_MISSING`.
- Bounded auth sha `a2ee54e8bf91720a0f8c0bd1dfd19813d2eac266b2721ace346afec43e81c0f2`, mtime `2026-06-26T21:45:04.612928Z`, status `FALSE_NEGATIVE_PREFLIGHT_OPERATOR_REVIEW_REQUIRED`, `decision=defer`, no `authorization_id`, object emitted `false`, active runtime probe/order `false/false`.
- False-negative review sha `df03c21f61bc820e59378881dc8e423f30c41e9ec349104534f063ad6b06eefb`, mtime `2026-06-26T21:29:17.571879Z`, status `PENDING_COST_GATE_FALSE_NEGATIVE_OPERATOR_REVIEW`, `decision=defer`.
- False-negative preflight sha `98a4a0cf3b3bc6c08f4d09f7a9fb34c74dbddf06e112325e9e580076444ceb8b`, mtime `2026-06-26T21:29:17.674307Z`, status `OPERATOR_REVIEW_REQUIRED`.

## Concern

The standing Demo authorization builder is now synced, but scheduled runtime artifacts still cannot admit a bounded probe because the false-negative operator review/preflight layer remains generic `defer` / `OPERATOR_REVIEW_REQUIRED`. The next source-progress blocker is to let that upstream false-negative/preflight layer consume the same structured standing Demo loss-control envelope and emit machine-checkable ready/fail states without granting order/live/risk authority.
