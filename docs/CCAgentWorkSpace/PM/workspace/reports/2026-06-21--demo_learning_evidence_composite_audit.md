# 2026-06-21 -- Demo Learning Evidence Composite Audit

## 結論

新增 `helper_scripts/db/audit/demo_learning_evidence_audit.py`，把 demo 無下單診斷再往「是否真的在學」推一層。

它合併兩個既有 read-only surface：

- `demo_order_stall_audit.py`：PG pipeline / Cost Gate rejects / context payload scope。
- `cost_gate_learning_lane.status`：`probe_ledger.jsonl`、blocked outcome、review、writer config、running process env、source readiness。

輸出 schema：`demo_learning_evidence_audit_v1`。

核心分類會直接回答：

- demo context 是否仍在累積；
- 近期 context 是否只是 observation telemetry；
- Cost Gate rejects 是否已在 PG 內記錄；
- cost-gate learning lane ledger / blocked outcomes / review 是否正在累積；
- 是否應該降主 Cost Gate。

固定策略：`global_cost_gate_lowering_recommended=false`，`main_cost_gate_adjustment=NONE`，`order_authority=NOT_GRANTED`。若 PG 有 Cost Gate rejects 但 ledger 空，狀態為 `PG_REJECTS_RECORDED_LEARNING_LANE_NOT_ACCUMULATING`，下一步是 `enable_bounded_cost_gate_learning_lane_after_operator_review`。

## 變更

- 新增 `helper_scripts/db/audit/demo_learning_evidence_audit.py`
  - read-only PG + read-only artifact/source/process-env inspection。
  - Markdown/JSON output。
  - 支援 `--runtime-env-file`、`--engine-pid`、`--runtime-proc-environ`、`--auto-detect-engine-pid`、`--require-writer-enabled`、`--require-process-writer-enabled`。
- 新增 `helper_scripts/db/audit/test_demo_learning_evidence_audit.py`
  - 鎖住 PG rejects + empty ledger 的 bounded-learning-lane recommendation。
  - 鎖住 observation-only telemetry 不是 actionable silent-drop。
  - 鎖住 blocked outcome review candidate 只進 operator review，不授權下單。

## 驗證

- `python3 -m pytest helper_scripts/db/audit/test_demo_learning_evidence_audit.py helper_scripts/db/audit/test_demo_order_stall_audit.py helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py -q` -> `69 passed`
- `python3 -m py_compile helper_scripts/db/audit/demo_learning_evidence_audit.py helper_scripts/db/audit/test_demo_learning_evidence_audit.py helper_scripts/db/audit/demo_order_stall_audit.py helper_scripts/research/cost_gate_learning_lane/status.py` -> passed
- `python3 helper_scripts/db/audit/demo_learning_evidence_audit.py --help` -> passed
- `git diff --check` -> passed

## 邊界

Source/test/docs only at this checkpoint. No runtime source sync, env edit, deploy, rebuild, restart, cron install, PG table write/schema migration, Bybit private/signed/trading call, order authority, main Cost Gate lowering, credential/auth/risk/order/strategy/runtime mutation, execution proof, or promotion proof.
