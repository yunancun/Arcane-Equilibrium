# Runtime Demo Accumulation Read-Only Audit

日期：2026-06-21
角色：PM 主會話
狀態：READ-ONLY EVIDENCE

## 結論

demo 不是完全沒有數據。`trade-core` PG 仍在持續記錄 demo/live_demo Cost Gate rejects 和 `learning.decision_features`。

但這些數據沒有進入真正的 demo 下單/成交驗證，也沒有進入 cost-gate learning lane 的 ledger/outcome loop：

- 近 1h：2496 條 decision features / cost-gate features / risk rejects，0 intents，0 orders，0 fills。
- 近 4h：24536 條 decision features / cost-gate features / risk rejects，0 intents，0 orders，0 fills。
- 近 24h：53693 decision features、53690 cost-gate features/risk rejects，只有 3 intents/orders，0 fills。

所以當前狀態是：信號與 reject 在 PG 層有記錄，不是 silent lost；但 learning lane runtime 沒有啟用，因此還沒有形成「被擋信號 -> outcome -> policy learning」的閉環。

## Source / Runtime 狀態

Linux runtime checkout：

- path：`/home/ncyu/BybitOpenClaw/srv`
- branch：`main...origin/main [behind 5]`
- `HEAD=917be4cc9a3d3549328155f1863d42400c70267f`
- local `origin/main=1401848b5f61136051d2b623c71dbad006a99459`
- Mac pushed source `origin/main=42f77f365ffba3c1195f0661bc64bcdffaad986d`
- checkout has many dirty and untracked source/docs/test paths.

Interpretation：runtime source is not activation-ready. Current runtime artifacts cannot be interpreted as reflecting v356/v357 source behavior.

## Artifact 狀態

Cost-gate learning lane directory only contains:

- `demo_learning_lane_plan_latest.json`
- `demo_learning_lane_policy_stdout.txt`

Missing:

- `logs/cost_gate_learning_lane.log`
- `cron_heartbeat/cost_gate_learning_lane.last_fire`
- `probe_ledger.jsonl`
- `reject_materializer_latest.json`
- `outcome_refresh_latest.json`
- `blocked_outcome_review_latest.json`

Running engine PID `35187` has no:

- `OPENCLAW_DEMO_LEARNING_LANE_WRITER`
- `OPENCLAW_DEMO_LEARNING_LANE_PLAN`
- `OPENCLAW_DEMO_LEARNING_LANE_LEDGER`

Interpretation：cost-gate learning lane is plan-only on runtime; no writer/cron/ledger/outcome accumulation is active.

## Demo Data Flow

Read-only PG evidence at DB time `2026-06-21T23:58:03+02`:

| window | decision_features | cost_gate_features | risk_cost_gate | intents | orders | fills |
|---|---:|---:|---:|---:|---:|---:|
| 1h | 2496 | 2496 | 2496 | 0 | 0 | 0 |
| 4h | 24536 | 24536 | 24536 | 0 | 0 | 0 |
| 24h | 53693 | 53690 | 53690 | 3 | 3 | 0 |

Latest timestamps:

- latest feature / cost-gate feature / risk reject：`2026-06-21T23:15:59.991+02`
- latest intent：`2026-06-21T02:00:00.003+02`
- latest order：`2026-06-21T02:00:00.658+02`
- latest fill：`2026-06-20T00:54:59.791+02`

Top 4h rejected side-cells:

- `ma_crossover|BTCUSDT|Buy`：12409 rejects
- `ma_crossover|BTCUSDT|Sell`：12127 rejects

## Alpha Runtime Artifact

Actual latest alpha path:

- `/tmp/openclaw/alpha_discovery_throughput/alpha_discovery_latest.json`

Runtime latest still has:

- schema：`alpha_discovery_runtime_killboard_v1`
- created：`2026-06-21T21:45:01.614317+00:00`
- killboard：`actionable_alpha_found=true` and `actionable_probe_found=true`
- cost-gate row：`blocker_class=probe_ready`, `primary_blocker=cost_gate_learning_probe_candidates_ready`

Interpretation：this is stale-runtime-code evidence. It predates the newer source-side source-readiness and preflight blockers, so it must not be used as authorization to probe or lower gates.

## Boundary

Actions performed were read-only:

- `ssh trade-core`
- `git status/rev-parse/log`
- `ls/find/crontab -l`
- PG `SELECT` with read-only transaction option
- `/proc` env inspection
- JSON artifact read

No runtime source sync, artifact refresh, crontab edit/install, env edit, deploy/rebuild/restart, PG write/schema migration, Bybit private/signed/trading call, credential/auth/risk/order/strategy mutation, order authority, Cost Gate lowering, execution proof, or promotion proof.

## Next Minimum Closure

The next real engineering closure is operator-gated:

1. reconcile dirty runtime checkout and fast-forward/source-sync to `42f77f36` or later;
2. run the existing read-only activation preflight;
3. run preinstall refresh-only to regenerate current scorecard/plan on runtime;
4. install/enable cost-gate learning cron;
5. enable/restart writer only under explicit operator approval;
6. observe ledger/materializer/outcome artifacts before discussing bounded demo probe authority.

Without that runtime activation, source-side learning improvements will remain unused and demo will keep accumulating reject records without learning from them.
