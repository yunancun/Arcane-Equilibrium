# 2026-06-22 — Sealed Horizon Preflight Cron Installer Stack Wiring

本輪不是降低 Cost Gate，也不是授權 probe/order。

核心修正：demo-learning full stack installer 現在包含四條 cron，而不是只裝 demo evidence、Cost Gate learning、healthcheck 三條：

- `demo_learning_evidence_audit_cron.sh`
- `sealed_horizon_probe_preflight_cron.sh`
- `cost_gate_learning_lane_cron.sh`
- `demo_learning_stack_healthcheck_cron.sh`

新增 installer：

```bash
helper_scripts/cron/install_sealed_horizon_probe_preflight_cron.sh
```

它預設只 dry-run；真 install/remove 必須設：

```bash
OPENCLAW_SEALED_HORIZON_PREFLIGHT_CRON_APPLY=1
```

Linux 已驗證：source fast-forward 到 `ad8f5ba4`；bash/py_compile/pytest passed；sealed installer dry-run 和 full stack dry-run 都只輸出 proposed crontab entry，沒有修改 crontab。

下一個 operator-gated runtime 動作仍是 dry-run full stack installer：

```bash
cd ~/BybitOpenClaw/srv
OPENCLAW_DEMO_LEARNING_STACK_EXPECTED_HEAD=<approved_sha> \
OPENCLAW_DEMO_LEARNING_STACK_CRON_APPLY=0 \
bash helper_scripts/cron/install_demo_learning_stack_crons.sh
```

只有 dry-run/preflight clean 後，才可另行把 `OPENCLAW_DEMO_LEARNING_STACK_CRON_APPLY=1` 用於正式安裝。本文檔不授權該 install。
