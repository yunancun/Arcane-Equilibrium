# Demo Learning Stack Healthcheck

本輪新增的是安裝後驗收，不是 runtime 啟用。

新增文件：

- `helper_scripts/cron/demo_learning_stack_healthcheck.py`
- `helper_scripts/cron/tests/test_demo_learning_stack_healthcheck.py`

它會只讀檢查：

- runtime source HEAD 是否等於 expected commit
- source 是否 dirty
- crontab 是否有兩條 stack cron
- demo-learning evidence heartbeat 是否 fresh
- Cost Gate learning-lane heartbeat 是否 fresh
- demo-learning evidence status/latest JSON 是否存在
- Cost Gate learning-lane status/latest blocked-outcome review 是否存在
- Cost Gate learning lane 是否有 ledger rows / blocked outcomes / review status

它會輸出明確狀態，例如：

- `SOURCE_NOT_READY`
- `NOT_INSTALLED`
- `INSTALLED_NOT_FIRING`
- `RUNNING_NO_LEDGER_ROWS`
- `LEDGER_ONLY_NEEDS_OUTCOME_REFRESH`
- `EVIDENCE_STACK_ACTIVE`

今天的 read-only runtime 核對仍顯示：

- `trade-core` 還在 `917be4cc`
- source 仍 dirty / behind
- demo-learning evidence cron 沒裝
- Cost Gate learning lane cron 沒裝
- Cost Gate lane 仍只有舊 plan artifact

所以這不是說 runtime 已經好了。這只是把「裝完後如何證明真的在學習」補上。

operator 後續在 source reconcile + stack install 後可跑：

```bash
cd /home/ncyu/BybitOpenClaw/srv
python3 helper_scripts/cron/demo_learning_stack_healthcheck.py \
  --data-dir /tmp/openclaw \
  --repo-root /home/ncyu/BybitOpenClaw/srv \
  --expected-head <pushed_commit_sha> \
  --fail-on-not-active
```

邊界：本輪沒有 sync runtime、沒有安裝 cron、沒有改 env、沒有 deploy/restart、沒有寫 PG、沒有連 Bybit、沒有下單、沒有啟 writer、沒有降低 Cost Gate。
