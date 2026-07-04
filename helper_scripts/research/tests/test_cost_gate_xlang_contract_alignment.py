"""跨語言契約判準對齊回歸測試（冷審計 R2 Phase B2-3：B2 / B3）。

MODULE_NOTE:
  模塊用途：釘住 Python 側與 Rust 側兩個契約判準的統一結果，任一側再漂移即紅——
    B2 = envelope expiry 解析統一到 Rust 嚴格側：naive datetime（無 tz offset）
      一律拒收（對齊 rust/openclaw_engine/src/demo_learning_lane.rs
      validate_operator_authorization_envelope 的 DateTime::parse_from_rfc3339）。
    B3 = envelope 數值型別統一拒字串（對齊 Rust serde Option<u64> 對 JSON 字串
      reject；Python `_int("5")` 不得再回 5）。
  主要對象：cost_gate_learning_lane.runtime_adapter（_parse_dt / _int /
    evaluate_probe_admission）。
  依賴：pytest + 標準庫；純 source 測試。
  硬邊界：不觸 PG / Bybit / runtime / 授權檔；E4 後續 golden vector 以同判準釘死。
  範圍註記：C3（engine_mode 正規化 trim+lower，proof_exclusion.py）不在本檔——
    該處由 fix/p3-smalls-0704 的 F10（commit db07df83b）覆蓋並自帶測試，本任務
    不重複改 proof_exclusion.py 以免合併撞車；C3 xlang parity 隨 F10 一併釘。
"""

from __future__ import annotations

import datetime as dt

from cost_gate_learning_lane.contract import (
    AUTHORITY_PATH_PATCH_READY_STATUS,
    BOUNDED_PROBE_AUTHORIZED_STATUS,
    BOUNDED_PROBE_OPERATOR_AUTHORIZATION_SCHEMA_VERSION,
    ELIGIBLE_REJECT_REASON_CODE,
    ORDER_AUTHORITY_GRANTED,
)
from cost_gate_learning_lane.policy import DEMO_LEARNING_LANE_SCHEMA_VERSION
from cost_gate_learning_lane.runtime_adapter import (
    ADMIT_DECISION,
    _int,
    _parse_dt,
    evaluate_probe_admission,
)


NOW_UTC = dt.datetime(2026, 6, 21, 11, 0, tzinfo=dt.timezone.utc)
SIDE_CELL = "ma_crossover|ETHUSDT|Sell"


def _candidate() -> dict:
    return {
        "side_cell_key": SIDE_CELL,
        "probe_proposal": {
            "mode": "demo_only_learning_probe",
            "max_probe_orders": 2,
            "cooldown_minutes": 30,
            "requires_runtime_policy_adapter": True,
            "requires_probe_attempt_logging": True,
            "requires_probe_outcome_logging": True,
        },
        "guardrails": {
            "main_cost_gate_adjustment": "NONE",
            "may_bypass_main_live_gate": False,
            "demo_only": True,
            "notional_or_qty_not_granted_by_artifact": True,
        },
    }


def _plan(
    *,
    expires_at: str = "2026-06-21T12:00:00+00:00",
    max_authorized_probe_orders: object = 2,
) -> dict:
    return {
        "schema_version": DEMO_LEARNING_LANE_SCHEMA_VERSION,
        "status": "READY_FOR_DEMO_LEARNING_PROBE",
        "generated_at_utc": "2026-06-21T10:00:00+00:00",
        "main_cost_gate_adjustment": "NONE",
        "order_authority": ORDER_AUTHORITY_GRANTED,
        "probe_candidates": [_candidate()],
        "operator_authorization": {
            "schema_version": BOUNDED_PROBE_OPERATOR_AUTHORIZATION_SCHEMA_VERSION,
            "status": BOUNDED_PROBE_AUTHORIZED_STATUS,
            "authorization_id": "auth-xlang-001",
            "operator_id": "operator-test",
            "side_cell_key": SIDE_CELL,
            "expires_at_utc": expires_at,
            "authority_path_readiness_status": AUTHORITY_PATH_PATCH_READY_STATUS,
            "main_cost_gate_adjustment": "NONE",
            "order_authority": ORDER_AUTHORITY_GRANTED,
            "max_authorized_probe_orders": max_authorized_probe_orders,
            "probe_authority_granted": True,
            "order_authority_granted": True,
            "promotion_evidence": False,
        },
    }


def _event() -> dict:
    return {
        "strategy_name": "ma_crossover",
        "symbol": "ETHUSDT",
        "side": "Sell",
        "reject_reason_code": ELIGIBLE_REJECT_REASON_CODE,
        "engine_mode": "demo",
        "ts_ms": 1_782_037_200_000,
        "context_id": "ctx-xlang-1",
        "signal_id": "sig-xlang-1",
    }


def _admit(plan: dict) -> dict:
    return evaluate_probe_admission(
        plan,
        _event(),
        now_utc=NOW_UTC,
        adapter_enabled=True,
    )


# ---------------------------------------------------------------------------
# B2 — expiry 解析拒 naive datetime（統一 Rust 嚴格側）
# ---------------------------------------------------------------------------

def test_parse_dt_rejects_naive_datetime():
    # 無 tz offset = reject；帶 offset / Z 正常解析。
    assert _parse_dt("2026-07-05T12:00:00") is None
    assert _parse_dt("2026-07-05") is None
    aware = _parse_dt("2026-07-05T12:00:00+00:00")
    assert aware == dt.datetime(2026, 7, 5, 12, 0, tzinfo=dt.timezone.utc)
    assert _parse_dt("2026-07-05T12:00:00Z") == aware
    assert _parse_dt("2026-07-05T20:00:00+08:00") == aware


def test_probe_admission_rejects_naive_expiry_envelope():
    # 綠色基線：tz-aware 未過期 envelope 必 ADMIT（證 fixture 本身有效，拒絕非空洞）。
    admitted = _admit(_plan())
    assert admitted["decision"] == ADMIT_DECISION

    # naive expiry（未來時刻但無 offset）：舊判準默認視為 UTC 而放行，
    # 統一 Rust 嚴格側後必須 reject。
    rejected = _admit(_plan(expires_at="2026-06-21T12:00:00"))
    assert rejected["decision"] == "OPERATOR_AUTHORIZATION_INVALID"
    assert rejected["reason"] == "operator_authorization_expiry_missing_or_malformed"
    assert rejected["allowed_to_submit_order"] is False


def test_probe_admission_rejects_naive_plan_generated_at():
    # plan generated_at_utc 為 naive → 解析 None → 按 stale/missing fail-closed。
    plan = _plan()
    plan["generated_at_utc"] = "2026-06-21T10:00:00"
    decision = _admit(plan)
    assert decision["decision"] == "PLAN_STALE_OR_MISSING_GENERATED_AT"
    assert decision["allowed_to_submit_order"] is False


# ---------------------------------------------------------------------------
# B3 — envelope 數值型別拒字串（統一 Rust serde 側）
# ---------------------------------------------------------------------------

def test_int_rejects_string_numerics():
    # 字串一律回 default（Rust serde Option<u64> 對 JSON 字串 reject）。
    assert _int("5") == 0
    assert _int("5", default=7) == 7
    assert _int(" 5 ") == 0
    # 非字串數值行為保留。
    assert _int(5) == 5
    assert _int(5.0) == 5
    assert _int(None) == 0


def test_probe_admission_rejects_string_probe_budget():
    # 綠色基線：int 預算必 ADMIT。
    assert _admit(_plan())["decision"] == ADMIT_DECISION

    # 字串 "2"：舊判準 _int("2")=2 放行；統一後視為缺失 → 預算 fail-closed reject。
    rejected = _admit(_plan(max_authorized_probe_orders="2"))
    assert rejected["decision"] == "OPERATOR_AUTHORIZATION_INVALID"
    assert rejected["reason"] == "operator_authorization_probe_budget_missing"
    assert rejected["allowed_to_submit_order"] is False
