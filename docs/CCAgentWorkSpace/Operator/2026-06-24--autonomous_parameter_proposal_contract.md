# Operator Note: Autonomous Parameter Proposal Contract

- Timestamp UTC: `2026-06-24T02:38:11Z`
- Status: `DONE_WITH_CONCERNS`
- Scope: source/test/docs only

新增 `helper_scripts/research/cost_gate_learning_lane/autonomous_parameter_proposal.py`，用來把 learning SSOT + false-negative learned candidate packet 轉成 no-authority `cost_gate_autonomous_parameter_proposal_v1`。

安全語意：

- P0 profit-evidence-quality 未清除時預設 `PROFIT_EVIDENCE_QUALITY_NOT_CLEARED`，不輸出 proposal；
- 只有 `DONE` / `DONE_WITH_CONCERNS` / `EXPLICITLY_QUARANTINED_BY_OPERATOR` 才能輸出 inactive review packet；
- READY proposal 仍不是 bounded probe authorization，不是 order authority，不是 Cost Gate lowering，也不是 promotion proof；
- 所有 proposed parameter rows 固定 `mutation_allowed_by_this_packet=false`；
- boolean 或 malformed truthy authority-bearing input（例如 `"true"` 或 `1`）都會 fail-close 為 `AUTHORITY_BOUNDARY_VIOLATION`。

Verification:

- `python3 -m py_compile helper_scripts/research/cost_gate_learning_lane/autonomous_parameter_proposal.py`
- `PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_cost_gate_autonomous_parameter_proposal.py` -> `5 passed`
- `PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py` -> `86 passed`
- `git diff --check`

仍需 operator action：P0 exchange working-order overhang 與 SOL/ETH fill-lineage drift 仍未解除或 quarantine；本變更沒有 cancel/modify orders、寫 PG、啟 writer、改 crontab、restart service、grant probe/order/live authority。
