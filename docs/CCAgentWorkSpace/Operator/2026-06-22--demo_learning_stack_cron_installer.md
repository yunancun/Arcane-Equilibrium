# Demo Learning Stack Cron Installer

本輪只改 source/test/docs，沒有在 runtime 安裝 cron。

新增的是：

- `helper_scripts/cron/install_demo_learning_stack_crons.sh`
- `helper_scripts/cron/tests/test_demo_learning_stack_cron_static.py`

它的作用是把兩個本來分開的 runtime 安裝步驟合成一個受控 stack：

- demo-learning evidence heartbeat cron
- Cost Gate learning-lane cron

重點不是放寬 Cost Gate，而是避免只裝了一半，導致 evidence heartbeat 有了但 Cost Gate learning lane 沒真正跑，或者反過來。

安全邊界：

- 預設 dry-run
- 真 install/remove 必須 `OPENCLAW_DEMO_LEARNING_STACK_CRON_APPLY=1`
- apply 必須帶 expected source HEAD
- apply 前會檢查 runtime source HEAD 匹配且工作樹乾淨
- apply 前會跑 Cost Gate preinstall refresh
- apply 前會跑 read-only activation preflight
- stack script 不直接寫 crontab，只委派既有子 installer
- `--remove` 會先移除 Cost Gate learning cron，再移除 demo-learning evidence cron

這沒有做：

- 沒有 sync runtime source
- 沒有安裝 runtime cron
- 沒有改 env
- 沒有 deploy/restart
- 沒有寫 PG
- 沒有連 Bybit
- 沒有下單
- 沒有啟 writer
- 沒有降低 Cost Gate

下一步仍然是 operator 批准 runtime source reconcile。等 `trade-core` source 到最新 pushed commit 且乾淨後，再用該 commit SHA 做 stack installer dry-run/apply。
