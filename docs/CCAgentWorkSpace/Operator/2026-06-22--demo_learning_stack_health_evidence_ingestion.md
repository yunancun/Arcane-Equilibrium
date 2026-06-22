# Demo Learning Stack Health Evidence Ingestion

日期：2026-06-22

## 做了什麼

- `demo_learning_stack_healthcheck.py` 新增 `--json-output`，operator 可把 healthcheck 結果明確寫成 latest JSON artifact。
- alpha runtime killboard 升到 `alpha_discovery_runtime_killboard_v7`，會讀這個 healthcheck artifact。
- alpha learning worklist 升到 `alpha_learning_worklist_v4`，會把 stack 是否安裝、是否 firing、是否有 ledger/outcome 作為 Cost Gate learning activation 的完成證據。

## 重要邊界

本輪沒有同步 runtime source、沒有安裝 cron、沒有改 env、沒有 deploy/restart、沒有寫 PG、沒有連 Bybit private API、沒有下單、沒有啟 writer、沒有降低 Cost Gate。

## 下一步仍是 operator-gated

runtime 仍需先做 source reconcile，再安裝 demo learning cron stack，之後用：

```bash
python3 helper_scripts/cron/demo_learning_stack_healthcheck.py \
  --data-dir /tmp/openclaw \
  --repo-root /home/ncyu/BybitOpenClaw/srv \
  --expected-head <sha> \
  --json-output /tmp/openclaw/demo_learning_stack_healthcheck/demo_learning_stack_healthcheck_latest.json \
  --fail-on-not-active
```

只有 healthcheck 變成 `EVIDENCE_STACK_ACTIVE`，才算 learning stack 真正在持續累積可用證據。
