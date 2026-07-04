"""Shared constants for the cost-gate demo learning-lane runtime contract."""

# schema 升 v2:outcome row 新增保守成本欄位(cost_model_version/source、
# cost_bps_optimistic、realized_net_bps 語義升級、censored 標記)。缺此欄的舊 row
# 一律視為 v1(legacy_optimistic_v0),下游按樂觀成本標記、不得用於候選立案。
ADAPTER_SCHEMA_VERSION = "cost_gate_demo_learning_lane_adapter_v2"
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
