# 2026-06-22 — Learned Cost Gate Review Candidate Priority

## 結論

這輪不是再包一層 activation。先在 Linux 跑既有 `cost_gate_learning_lane_cron.sh` 的 artifact-only refresh，確認系統已經能從 Cost Gate blocked signals 累積出具體 review candidate。

然後修 alpha/worklist 優先級：當 blocked-outcome review candidate 存在時，它應該排在 demo-learning stack dry-run apply gate 前面。也就是先處理已學到的可疑 edge，而不是繼續停在基礎設施 gate。

## Runtime Evidence

Linux artifact-only Cost Gate learning refresh:

- `ledger_row_count=52419`
- `materializer_input_feature_row_count=10000`
- `materializer_materialized_record_count=10000`
- `materializer_appended_record_count=10000`
- `refresh_outcome_count=2419`
- `refresh_appended_outcome_count=2419`
- `blocked_signal_outcome_count=22419`
- `review_status=DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATES_PRESENT`
- top candidate: `ma_crossover|ETHUSDT|Sell`
- `wrongful_block_score=75.49272112494981`
- `net_cost_cushion_bps=37.746360562474905`

Linux alpha smoke after source sync:

- alpha schema: `alpha_discovery_runtime_killboard_v8`
- source: `SYNCED_CLEAN`
- worklist schema: `alpha_learning_worklist_v5`
- worklist status: `OPERATOR_GATED_LEARNING_READY`
- top task: `operator_probe_review`
- blocker: `cost_gate_blocked_signal_outcomes_need_demo_probe_authority_review`
- objective: `operator_review_top_blocked_signal_side_cell_before_bounded_demo_probe`
- next trigger: `operator_review_blocked_outcome_scorecard_before_demo_probe_authority`
- requires operator authorization: `true`
- runtime mutation required: `false`
- dry-run Cost Gate lowering: `false`
- dry-run order authority: `false`
- dry-run probe authority: `false`

## Source 變更

- `helper_scripts/research/alpha_discovery_throughput/discovery_loop.py`
  - `DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATES_PRESENT` now supersedes the dry-run apply gate.
- `helper_scripts/research/alpha_discovery_throughput/learning_worklist.py`
  - blocked-signal primary blockers keep the blocked-signal side-cell objective even when sealed preflight evidence is also present.
- Tests cover both mixed states.

## Verification

- Mac py_compile passed.
- Mac focused alpha/worklist tests: `65 passed`.
- Source commits:
  - `51e3e5202dfa4dcfb00dafed629875e851326736`
  - `9768b3dd51497fdc7d48f5f5663b4d201e47655b`
- Linux source fast-forwarded to `9768b3dd`.
- Linux py_compile passed.
- Linux focused alpha/worklist tests: `65 passed`.
- Linux artifact-only Cost Gate learning refresh passed.
- Linux artifact-only alpha smoke passed and source remained clean.

## PM Read

This is the first stronger evidence in this local loop: the system has a concrete Cost Gate blocked-signal candidate (`ma_crossover|ETHUSDT|Sell`) from real demo reject history.

It is still not promotion proof. The next valid gate is operator review of the blocked-outcome scorecard and, if approved separately, a bounded demo probe with matched-control and execution-realism review.

## Boundary

No CI run. No PG write/schema migration. No Bybit private/signed/trading call. No deploy/rebuild/restart. No crontab install. No writer/env/auth/risk/order/strategy mutation. No Cost Gate lowering. No probe/order authority. No promotion proof.
