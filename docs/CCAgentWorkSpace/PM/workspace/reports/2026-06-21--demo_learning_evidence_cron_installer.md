# Demo Learning Evidence Cron Installer

## 結論

新增 `helper_scripts/cron/install_demo_learning_evidence_audit_cron.sh`，為 demo-learning evidence heartbeat 提供可審查、可 rollback、默認 dry-run 的 Linux crontab installer。

這補上 v332 wrapper 的落地缺口：operator 之後不需要手寫 cron line，也不會因普通執行腳本就改 runtime。真正 install/remove 必須顯式設定 `OPENCLAW_DEMO_LEARNING_EVIDENCE_CRON_APPLY=1`。

## 變更

- 新 installer：
  - default base dir：`$HOME/BybitOpenClaw/srv`
  - default data dir：`/tmp/openclaw`
  - default schedule：`7,37 * * * *`
  - wrapper：`helper_scripts/cron/demo_learning_evidence_audit_cron.sh`
  - cron log：`$OPENCLAW_DATA_DIR/logs/demo_learning_evidence_audit_cron.cron.log`
- 安全行為：
  - Linux-only。
  - existing entry idempotent skip。
  - `--remove` rollback path。
  - install/remove 都由 `OPENCLAW_DEMO_LEARNING_EVIDENCE_CRON_APPLY=1` gate。
  - validation covers cron minute list, bool flags, and cron env-safe values。
- Operator knobs preserved：
  - engine modes / lookback / top-limit。
  - writer/process-writer required preflight flags。
  - expected source head。
  - runtime env file / engine PID / `/proc/<pid>/environ` pass-through。

## 為何重要

我們現在需要 demo 持續累積「被擋信號是否真的不賺錢」的證據，而不是只靠一次性本地測算。v332 已經有 heartbeat wrapper；v333 已把 heartbeat artifact 接進 alpha killboard。這次補上 installer，讓 heartbeat 有清楚的 operator activation path。

但這一步仍然不是 runtime activation。當前 runtime checkout 仍需 operator-gated source sync/reconcile/env/restart/cron/writer 決策，否則 demo-learning lane 不會因本 commit 自動開始累積。

## 邊界

- Source/test/docs only。
- 不在 runtime 安裝 cron。
- 不同步 runtime source。
- 不改 env。
- 不 deploy / rebuild / restart。
- 不啟用 learning writer。
- 不 append ledger。
- 不連 PG。
- 不連 Bybit private/signed/trading API。
- 不下單。
- 不改 auth / risk / strategy / runtime config。
- 不降低 main Cost Gate。
- 不授權 demo order。

## 驗證

- `bash -n helper_scripts/cron/demo_learning_evidence_audit_cron.sh helper_scripts/cron/install_demo_learning_evidence_audit_cron.sh`：PASS
- `python3 -m pytest helper_scripts/cron/tests/test_demo_learning_evidence_audit_cron_static.py -q`：10 passed
- `python3 -m pytest --import-mode=importlib helper_scripts/cron/tests/test_demo_learning_evidence_audit_cron_static.py helper_scripts/db/audit/test_demo_learning_evidence_audit.py helper_scripts/db/audit/test_demo_order_stall_audit.py helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py -q`：79 passed
- `python3 -m py_compile helper_scripts/cron/tests/test_demo_learning_evidence_audit_cron_static.py`：PASS

普通 pytest 混跑 `helper_scripts/cron/tests` 和 `helper_scripts/research/tests` 仍需 `--import-mode=importlib`，原因是既有 top-level `tests` package collision；本次沒有改動該 harness 結構。
