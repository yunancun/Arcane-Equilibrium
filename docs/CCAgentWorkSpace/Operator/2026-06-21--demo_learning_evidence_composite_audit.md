# 2026-06-21 -- Demo Learning Evidence Composite Audit

新增 `helper_scripts/db/audit/demo_learning_evidence_audit.py`。

用途：把 demo 無下單診斷和 cost-gate learning-lane readiness 放在同一份 read-only 報告裡，直接回答「demo 是否正在產生可學習證據」。

輸出會合併：

- PG order-stall scorecard：context / candidate / risk / intent / order / fill / payload scope。
- Cost Gate learning preflight：source readiness、writer config、running process env、`probe_ledger.jsonl`、blocked outcomes、review artifact、learning-loop heartbeat/status。

重要分類：

- `OBSERVATION_TELEMETRY_ACTIVE_NO_ACTIONABLE_LEDGER`
- `PG_REJECTS_RECORDED_LEARNING_LANE_NOT_ACCUMULATING`
- `ADMISSION_ROWS_NEED_OUTCOME_REFRESH`
- `BLOCKED_OUTCOMES_ACCUMULATING`
- `LEARNING_REVIEW_CANDIDATES_PRESENT`

固定安全結論：

- 不降低主 Cost Gate。
- 不授權下單。
- 若 PG 有 Cost Gate rejects 但 ledger 空，下一步是 operator review 後啟用 bounded demo-learning lane，而不是 global gate lowering。

驗證：

- focused regression -> `69 passed`
- `py_compile`, CLI `--help`, and `git diff --check` passed

邊界：source/test/docs only；沒有 deploy/restart、沒有 PG write、沒有 Bybit private/signed/trading call、沒有下單、沒有降低 Cost Gate。
