"""Shared constants for the cost-gate demo learning-lane runtime contract."""

# C4(冷審計 R2 整合):ADAPTER_SCHEMA_VERSION 拆成兩個獨立 record 面,不再共用一個
# 版本號。原因:Rust 只寫 admission 面 record(probe_admission_decision /
# probe_capture_error),其 record 形狀在 P1-2 未變;P1-2 新增保守成本欄
# (cost_model_version/source、cost_bps_optimistic、realized_net_bps 語義升級、censored)
# 只落在 Python outcome 面 record(probe_outcome / blocked_signal_outcome)。兩者本是
# 不同 record 類型,先前恰好共用一個常量名 → 把 admission 面誤標成 v2 且與 Rust 漂移。
# 拆分後:
#   ADAPTER_SCHEMA_VERSION = admission 面(Rust↔Python 逐值 parity,形狀未變 → 保 v1)。
#   OUTCOME_ADAPTER_SCHEMA_VERSION = outcome 面(Python 唯一寫入方,P1-2 升 v2)。
# 下游不以此字串做 gate(候選立案由 per-row cost_model_version=legacy_optimistic_v0
# 攔截,見 outcome_review.py),故舊 v1 row + 新 v2 row 混寫向後相容。
ADAPTER_SCHEMA_VERSION = "cost_gate_demo_learning_lane_adapter_v1"
# outcome 面:缺保守成本欄的舊 row 一律視為 legacy_optimistic_v0(樂觀成本、不得立案)。
OUTCOME_ADAPTER_SCHEMA_VERSION = "cost_gate_demo_learning_lane_adapter_v2"
ORDER_AUTHORITY_GRANTED = "DEMO_LEARNING_PROBE_GRANTED"
BOUNDED_PROBE_OPERATOR_AUTHORIZATION_SCHEMA_VERSION = (
    "bounded_demo_probe_operator_authorization_v1"
)
STANDING_DEMO_AUTHORIZATION_SCHEMA_VERSION = "standing_demo_operator_authorization_v1"
STANDING_DEMO_AUTHORIZATION_ACTIVE_STATUS = "STANDING_DEMO_AUTHORIZATION_ACTIVE"
BOUNDED_PROBE_AUTHORIZED_STATUS = "BOUNDED_DEMO_PROBE_AUTHORIZED"
AUTHORITY_PATH_PATCH_READY_STATUS = "AUTHORITY_PATH_PATCH_READY_FOR_OPERATOR_REVIEW"
ELIGIBLE_REJECT_REASON_CODE = "cost_gate_js_demo_negative_edge"
ADMIT_DECISION = "ADMIT_DEMO_LEARNING_PROBE"
PROBE_ADMISSION_DECISION_RECORD_TYPE = "probe_admission_decision"
PROBE_OUTCOME_RECORD_TYPE = "probe_outcome"
BLOCKED_SIGNAL_OUTCOME_RECORD_TYPE = "blocked_signal_outcome"
