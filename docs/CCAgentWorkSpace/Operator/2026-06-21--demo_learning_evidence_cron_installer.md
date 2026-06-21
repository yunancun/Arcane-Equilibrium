# Demo Learning Evidence Cron Installer

新增 `helper_scripts/cron/install_demo_learning_evidence_audit_cron.sh`。

用途：為 `demo_learning_evidence_audit_cron.sh` 提供可審查的 Linux crontab installer。預設只 dry-run 顯示 proposed entry；只有設定 `OPENCLAW_DEMO_LEARNING_EVIDENCE_CRON_APPLY=1` 才會 install/remove。

預設 schedule：`7,37 * * * *`。支援 `--remove` rollback，並保留 expected-head、runtime env、engine PID/process writer preflight knobs。

本次仍是 source/test/docs only：沒有在 runtime 安裝 cron、沒有 sync source、沒有改 env、沒有重啟、沒有啟 writer、沒有連 PG/Bybit、沒有下單、沒有降低 Cost Gate。

驗證：bash syntax PASS；cron static 10 passed；combined importlib smoke 79 passed；py_compile PASS。
