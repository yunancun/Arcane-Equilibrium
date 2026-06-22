# Demo Learning Stack Healthcheck Cron Wiring

結論：本 checkpoint 把 v368 的 healthcheck latest artifact 從「可手工寫出」推進到「operator 批准安裝 stack 後可由 cron 自動刷新」。這仍是 source/test/docs 階段；沒有 runtime source sync、沒有安裝 runtime crontab、沒有啟 writer、沒有降低 Cost Gate、沒有授權 probe/order。

## 變更

- 新增 `helper_scripts/cron/demo_learning_stack_healthcheck_cron.sh`：執行 `demo_learning_stack_healthcheck.py --json-output`，寫 dated/latest JSON、status JSONL、heartbeat、lock/log，並把 status/reason/next_action 與 key answers 摘要落到 `logs/demo_learning_stack_healthcheck.log`。
- 新增 `helper_scripts/cron/install_demo_learning_stack_healthcheck_cron.sh`：Linux-only、dry-run by default、`OPENCLAW_DEMO_LEARNING_STACK_HEALTHCHECK_CRON_APPLY=1` 才 install/remove，apply 時預設要求 expected-head。
- 更新 `helper_scripts/cron/install_demo_learning_stack_crons.sh`：stack installer 現在同時 preview/install/remove demo evidence heartbeat、Cost Gate learning lane、stack healthcheck refresher 三個 cron。
- 更新 static tests、`TODO.md`、`docs/CLAUDE_CHANGELOG.md`、`helper_scripts/SCRIPT_INDEX.md`、PM memory，並新增 Operator note。

## 驗證

- `bash -n helper_scripts/cron/demo_learning_stack_healthcheck_cron.sh helper_scripts/cron/install_demo_learning_stack_healthcheck_cron.sh helper_scripts/cron/install_demo_learning_stack_crons.sh helper_scripts/cron/demo_learning_evidence_audit_cron.sh helper_scripts/cron/install_demo_learning_evidence_audit_cron.sh helper_scripts/cron/cost_gate_learning_lane_cron.sh helper_scripts/cron/install_cost_gate_learning_lane_cron.sh` passed。
- `python3 -m pytest -q helper_scripts/cron/tests/test_demo_learning_stack_cron_static.py helper_scripts/cron/tests/test_demo_learning_stack_healthcheck.py` passed：`14 passed`。
- Combined related cron static regression passed：`36 passed`。
- `python3 -m py_compile helper_scripts/cron/tests/test_demo_learning_stack_cron_static.py helper_scripts/cron/tests/test_demo_learning_stack_healthcheck.py helper_scripts/cron/demo_learning_stack_healthcheck.py` passed。
- `git diff --check` passed。
- Direct healthcheck artifact smoke wrote latest JSON and returned `SOURCE_NOT_READY` locally because the source tree was dirty, which is expected fail-closed behavior。
- Wrapper smoke wrote latest JSON/status and propagated `SOURCE_NOT_READY` without touching runtime state。

## 邊界

- No runtime source sync or deploy/restart.
- No crontab install was performed on `trade-core`.
- No PG write/schema migration, Bybit private/signed/trading call, credential/auth/risk/order/strategy mutation.
- No writer enablement, Cost Gate lowering, probe/order authority, execution proof, or promotion proof.

## 下一步

Operator-gated runtime step remains: reconcile `trade-core` source to the approved head, dry-run `helper_scripts/cron/install_demo_learning_stack_crons.sh`, then apply the stack only after the preflight is clean. After install, verify `/tmp/openclaw/demo_learning_stack_healthcheck/demo_learning_stack_healthcheck_latest.json`, the three heartbeats, and Cost Gate learning ledger/outcome/review rows before considering any bounded demo-probe review.
