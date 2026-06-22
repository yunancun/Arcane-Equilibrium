# 2026-06-22 — Demo-Learning Activation Packet Alpha Ingestion

## 結論

v407 讓系統能生成 `demo_learning_stack_activation_packet_v1`，但主 alpha loop 仍只看 healthcheck，所以 runtime blocker 仍容易退化成泛化的 `NOT_INSTALLED`。v408 補上 ingestion：activation packet 現在是 alpha runtime / profitability blocker / learning worklist 的正式 evidence。

這使 Cost Gate 翻越路徑更具體：不是降低主 gate，而是先把 rejected demo signals 轉成可持續積累、可回看、可匹配控制組的 learning loop。只有當 matched blocked outcomes、bounded demo probe result review、execution-realism review 都支持時，才進一步給 operator 做 probe/COST-Gate review。

## Source 變更

- `helper_scripts/research/alpha_discovery_throughput/runtime_runner.py`
  - schema bump: `alpha_discovery_runtime_killboard_v8`。
  - 新增 canonical reader：
    `/tmp/openclaw/demo_learning_stack_activation_packet/demo_learning_stack_activation_packet_latest.json`。
  - 將 activation packet 狀態、缺失 cron、operator dry-run/apply/rollback/verification commands、Cost Gate escape thesis、edge-amplification levers、no-authority answers 帶入 `cost_gate_demo_learning_lane` detail。
- `helper_scripts/research/alpha_discovery_throughput/discovery_loop.py`
  - fresh packet `READY_FOR_OPERATOR_DRY_RUN` -> `demo_learning_stack_activation_packet_ready_for_operator_dry_run`。
  - stale/unreadable packet -> refresh blocker。
  - `SOURCE_NOT_READY` -> source-health blocker。
  - repair/review-refresh states -> data-coverage blocker。
- `helper_scripts/research/alpha_discovery_throughput/learning_worklist.py`
  - schema bump: `alpha_learning_worklist_v5`。
  - evidence now carries packet status, missing crons, dry-run shell, no-authority answers, and edge-amplification levers。
  - dry-run-ready stack activation has a specific objective before any cron install。

## Verification

- Mac py_compile passed。
- Mac focused pytest:
  `PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_alpha_discovery_throughput.py helper_scripts/research/tests/test_alpha_discovery_learning_worklist.py`
  = `62 passed`。
- Source commit: `277b00bef6e3404b310145f6cf441495d6c0037e` (`[skip ci]`)。
- Linux `trade-core:/home/ncyu/BybitOpenClaw/srv` fast-forwarded to `277b00be`。
- Linux py_compile passed。
- Linux same focused pytest = `62 passed`。
- Mac/Linux `git diff --check` passed。

## Boundary

No CI run. No PG write/schema migration. No Bybit private/signed/trading call. No deploy/rebuild/restart. No crontab install. No writer/env/auth/risk/order/strategy/runtime mutation. No Cost Gate lowering. No probe/order authority. No promotion proof.

## Next Gate

Operator can review the packet dry-run path, but v408 itself does not authorize apply. The next evidence gate remains:

1. dry-run preview reviewed;
2. operator decides whether to install the four-cron learning stack separately;
3. stack health reaches `EVIDENCE_STACK_ACTIVE`;
4. learning lane accumulates ledger/outcome/review rows;
5. matched-control bounded probe reviews and execution-realism reviews decide whether any side-cell/horizon deserves further operator probe review.
