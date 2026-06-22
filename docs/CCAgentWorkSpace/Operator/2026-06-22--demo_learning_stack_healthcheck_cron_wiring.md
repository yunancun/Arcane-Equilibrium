# Demo Learning Stack Healthcheck Cron Wiring

本次只做 source/test/docs。新增 healthcheck cron wrapper + dry-run installer，並把 demo-learning stack installer 擴展為三件套：demo evidence heartbeat、Cost Gate learning lane、stack healthcheck refresher。

Runtime 未被修改：沒有 source sync、沒有 crontab install、沒有 restart/deploy、沒有 PG/Bybit 寫入、沒有降低 Cost Gate、沒有 order/probe authority。

下一個 operator-gated 動作仍是先 reconcile `trade-core` source 到 approved head，再 dry-run/apply：

```bash
cd ~/BybitOpenClaw/srv
OPENCLAW_DEMO_LEARNING_STACK_EXPECTED_HEAD=<approved_sha> \
OPENCLAW_DEMO_LEARNING_STACK_CRON_APPLY=0 \
bash helper_scripts/cron/install_demo_learning_stack_crons.sh
```

只有 dry-run/preflight clean 後，才把 `OPENCLAW_DEMO_LEARNING_STACK_CRON_APPLY=1` 用於正式安裝。
