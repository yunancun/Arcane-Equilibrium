# 2026-06-22 — Alpha Cron Activation Packet And Source Cleanliness

## 結論

v408 已讓 alpha/worklist 能讀 activation packet，但 packet 本身仍依賴一次性 artifact；同時 Linux runtime 的 `vol-event-robust-ruling.md` 會週期性把 tracked docs file 弄髒，導致 source readiness 被誤傷。

v409 修掉這兩個閉環問題：

- 既有 alpha cron 現在會先刷新 canonical activation packet，再跑 alpha killboard。
- vol-event latest report 預設寫到 `OPENCLAW_DATA_DIR`，不再污染 source checkout。

這不是下單改動，也不是降低 Cost Gate。它把「學習棧未啟動」從模糊 blocker 變成 alpha worklist 裡持續刷新的 operator-gated activation task。

## Source 變更

- `helper_scripts/cron/alpha_discovery_throughput_cron.sh`
  - refreshes `demo_learning_stack_activation_packet_latest.json` before `alpha_discovery_throughput.runtime_runner`。
  - writes packet stdout/status artifacts under `/tmp/openclaw/demo_learning_stack_activation_packet/`。
- `helper_scripts/research/order_flow_alpha/vol_event_trigger.py`
  - default robust-ruling latest path moved to `$OPENCLAW_DATA_DIR/order_flow_alpha/vol-event-robust-ruling.md`。
  - `OPENCLAW_VOL_EVENT_RULING_REPORT_PATH` remains available for explicit archival export。
- Added static contract tests for both invariants。

## Runtime Evidence

Linux artifact-only smoke after source sync:

- packet status: `READY_FOR_OPERATOR_DRY_RUN`
- alpha schema: `alpha_discovery_runtime_killboard_v8`
- alpha created: `2026-06-22T15:30:02.131233+00:00`
- source status: `SYNCED_CLEAN`
- worklist schema: `alpha_learning_worklist_v5`
- top task: `cost_gate_learning_activation`
- blocker: `demo_learning_stack_activation_packet_ready_for_operator_dry_run`
- next trigger: `run_dry_run_preview_then_apply_only_if_installer_preflight_passes`
- missing cron count: `4`
- healthcheck status: `NOT_INSTALLED`
- `global_cost_gate_lowering_recommended=false`
- `order_authority_granted=false`
- `probe_authority_granted=false`

The prior generated tracked vol-event report on Linux was preserved at:

`/tmp/openclaw/order_flow_alpha/vol-event-robust-ruling.pre_v409_runtime_copy.md`

## Verification

- Mac `bash -n` passed。
- Mac py_compile passed。
- Mac cron tests: `6 passed`。
- Mac research alpha/worklist/vol-event tests: `64 passed`。
- Source commit: `2d4bad297a6293c1280d26393c63a4851505912f` (`[skip ci]`)。
- Linux source fast-forwarded to `2d4bad29`。
- Linux `bash -n` + py_compile passed。
- Linux cron tests: `6 passed`。
- Linux research alpha/worklist/vol-event tests: `64 passed`。
- Linux artifact-only alpha cron smoke passed and source remained clean。

## PM Read

The near-term profitability path is still not global Cost Gate lowering. The productive path is:

1. install/activate the demo-learning stack only after operator dry-run review;
2. continuously materialize rejected demo signals into ledger/outcome/review artifacts;
3. compare future bounded demo probes against matched blocked-signal controls;
4. only consider side-cell/horizon-specific Cost Gate review after execution-realism evidence shows the probe captures the control edge.

v409 makes that path self-observable in alpha runtime. It does not prove profitability.

## Boundary

No CI run. No PG write/schema migration. No Bybit private/signed/trading call. No deploy/rebuild/restart. No new crontab install. No writer/env/auth/risk/order/strategy mutation. No Cost Gate lowering. No probe/order authority. No promotion proof.
