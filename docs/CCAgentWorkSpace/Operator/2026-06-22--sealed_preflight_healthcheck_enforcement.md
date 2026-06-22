# 2026-06-22 — Sealed Preflight Healthcheck Enforcement

本輪不是降低 Cost Gate，也不是授權 probe/order。

核心修正：v405 full stack installer 已是四件套，但 healthcheck 還按舊 two-cron 驗收。現在 healthcheck 會要求：

- `demo_learning_evidence_audit_cron.sh` entry present；
- `sealed_horizon_probe_preflight_cron.sh` entry present；
- `cost_gate_learning_lane_cron.sh` entry present；
- `demo_learning_stack_healthcheck_cron.sh` entry present；
- demo evidence / sealed preflight / Cost Gate learning 三條資料生產 cron 的 heartbeat + status fresh。

如果 sealed preflight cron 缺 entry，stack 會是 `NOT_INSTALLED`。如果 sealed preflight heartbeat stale，stack 會是 `INSTALLED_NOT_FIRING`。如果 cron 有跑但 latest sealed preflight artifact 缺失，stack 會是 `BOUNDED_PROBE_PREFLIGHT_MISSING`。

已在 Mac 驗證：py_compile passed；healthcheck tests `9 passed`；alpha/worklist focused `60 passed`。本 note 不授權 runtime cron install。
