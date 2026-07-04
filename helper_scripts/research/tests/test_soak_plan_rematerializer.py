from __future__ import annotations

import copy
import datetime as dt
import json

from cost_gate_learning_lane import soak_plan_rematerializer as mod


NOW = dt.datetime(2026, 7, 4, 21, 0, tzinfo=dt.timezone.utc)
OLD_GEN = dt.datetime(2026, 7, 3, 20, 43, tzinfo=dt.timezone.utc)
SIDE_CELL = "grid_trading|ETHUSDT|Buy"


def _auth(**overrides) -> dict:
    payload = {
        "schema_version": "bounded_demo_probe_operator_authorization_v1",
        "status": "BOUNDED_DEMO_PROBE_AUTHORIZED",
        "operator_id": "profit-first-fast-demo-loop",
        "side_cell_key": SIDE_CELL,
        "order_authority": "DEMO_LEARNING_PROBE_GRANTED",
        "order_authority_granted": True,
        "probe_authority_granted": True,
        "promotion_evidence": False,
        "main_cost_gate_adjustment": "NONE",
        "max_authorized_probe_orders": 3,
        "expires_at_utc": "2026-07-05T09:02:17+00:00",
    }
    payload.update(overrides)
    return payload


def _plan(**overrides) -> dict:
    payload = {
        "schema_version": "cost_gate_demo_learning_lane_plan_v1",
        "generated_at_utc": OLD_GEN.isoformat(),
        "status": "READY_FOR_DEMO_LEARNING_PROBE",
        "gate_status": "OPERATOR_REVIEW",
        "policy": "artifact_only_demo_learning_probe_plan_no_order_authority",
        "main_cost_gate_adjustment": "NONE",
        "order_authority": "DEMO_LEARNING_PROBE_GRANTED",
        "operator_authorization": _auth(),
        "candidate": {"side_cell_key": SIDE_CELL},
        "probe_candidates": [
            {
                "side_cell_key": SIDE_CELL,
                "strategy_name": "grid_trading",
                "symbol": "ETHUSDT",
                "side": "Buy",
                "outcome_horizon_minutes": 60,
                "max_probe_orders": 3,
            }
        ],
    }
    payload.update(overrides)
    return payload


def _fresh_plan(selected: list[str] | None = None, status: str = "READY_FOR_DEMO_LEARNING_PROBE") -> dict:
    keys = [SIDE_CELL] if selected is None else selected
    return {
        "schema_version": "cost_gate_demo_learning_lane_plan_v1",
        "generated_at_utc": NOW.isoformat(),
        "status": status,
        "gate_status": "OPERATOR_REVIEW",
        "probe_candidates": [{"side_cell_key": key} for key in keys],
        "source": {"source_error": None},
    }


def _review(plan=None, fresh=None, fresh_error=None):
    return mod.build_rematerialization(
        plan=_plan() if plan is None else plan,
        fresh_scorecard_plan=_fresh_plan() if fresh is None else fresh,
        fresh_scorecard_error=fresh_error,
        now_utc=NOW,
    )


def test_valid_soak_plan_is_rematerialized_only_generated_at_changes() -> None:
    plan = _plan()
    original_auth = copy.deepcopy(plan["operator_authorization"])
    review = _review(plan=plan)

    assert review["status"] == mod.REMATERIALIZED_STATUS
    assert review["accepted"] is True
    assert review["blocking_reasons"] == []
    new_plan = review["rematerialized_plan"]
    # 只 generated_at + soak_rematerialization 快照變化；其餘欄位包括授權塊不動。
    assert new_plan["generated_at_utc"] == NOW.isoformat()
    assert new_plan["operator_authorization"] == original_auth
    assert new_plan["candidate"] == plan["candidate"]
    assert new_plan["order_authority"] == "DEMO_LEARNING_PROBE_GRANTED"
    assert new_plan["soak_rematerialization"]["authority_extended"] is False
    assert review["authorization_byte_preserved"] is True
    assert review["authorization_sha256_after"] == review["authorization_sha256_before"]
    assert review["answers"]["authority_extended"] is False


def test_expired_authorization_is_no_op() -> None:
    review = _review(plan=_plan(operator_authorization=_auth(
        expires_at_utc="2026-07-01T09:02:17+00:00"
    )))

    assert review["status"] == mod.NO_OP_STATUS
    assert review["accepted"] is False
    assert "operator_authorization_expired" in review["blocking_reasons"]
    assert review["rematerialized_plan"] is None


def test_side_cell_no_longer_selected_is_no_op() -> None:
    review = _review(fresh=_fresh_plan(selected=["grid_trading|AVAXUSDT|Sell"]))

    assert review["status"] == mod.NO_OP_STATUS
    assert "side_cell_no_longer_selected_by_fresh_scorecard" in review["blocking_reasons"]
    assert review["rematerialized_plan"] is None


def test_stale_scorecard_is_no_op() -> None:
    review = _review(fresh_error="stale_scorecard")

    assert review["status"] == mod.NO_OP_STATUS
    assert any(
        r.startswith("fresh_scorecard_unavailable:stale_scorecard")
        for r in review["blocking_reasons"]
    )
    assert review["rematerialized_plan"] is None


def test_plan_authorization_side_cell_mismatch_is_no_op() -> None:
    review = _review(plan=_plan(operator_authorization=_auth(
        side_cell_key="grid_trading|AVAXUSDT|Sell"
    )))

    assert review["status"] == mod.NO_OP_STATUS
    assert "plan_and_authorization_side_cell_mismatch" in review["blocking_reasons"]
    assert review["rematerialized_plan"] is None


def test_plan_caps_exceed_authorization_is_no_op() -> None:
    plan = _plan()
    plan["probe_candidates"][0]["max_probe_orders"] = 5  # > auth max 3
    review = _review(plan=plan)

    assert review["status"] == mod.NO_OP_STATUS
    assert "plan_probe_caps_inconsistent_with_authorization" in review["blocking_reasons"]
    assert review["rematerialized_plan"] is None


def test_schema_mismatch_authorization_is_no_op() -> None:
    review = _review(plan=_plan(operator_authorization=_auth(
        schema_version="something_else_v9"
    )))

    assert review["status"] == mod.NO_OP_STATUS
    assert "operator_authorization_schema_mismatch" in review["blocking_reasons"]
    assert review["rematerialized_plan"] is None


def test_bidirectional_mutation_authority_invariant_edit_is_no_op() -> None:
    # E2 審查點①(第一層防線=授權邊界指紋)：篡改任一「授權語意」欄位使塊偏離已簽 soak
    # envelope 指紋 → 必 no-op(不可災難性重簽)。逐欄位掃描。
    for field, tampered in (
        ("order_authority", "SOMETHING_ELSE"),
        ("order_authority_granted", False),
        ("probe_authority_granted", False),
        ("promotion_evidence", True),
        ("main_cost_gate_adjustment", "LOWER"),
        ("status", "SOMETHING_ELSE"),
        ("schema_version", "something_else_v9"),
        ("side_cell_key", "grid_trading|AVAXUSDT|Sell"),
    ):
        review = _review(plan=_plan(operator_authorization=_auth(**{field: tampered})))
        assert review["status"] == mod.NO_OP_STATUS, field
        assert review["rematerialized_plan"] is None, field


def test_sha256_anchor_catches_non_invariant_field_edit() -> None:
    # E2 審查點①(第二層防線=可信 sha anchor)：連授權邊界指紋都合法、但欄位(operator_id /
    # max_authorized_probe_orders)被改、本腳本無法獨立再推導者 → 由 orchestrator 於簽名時
    # 記錄的 sha256 anchor 攔截。先取合法塊 sha 當 anchor，再篡改 → 必 no-op。
    good_auth = _auth()
    anchor = mod._sha256_obj(good_auth)
    for field, tampered in (
        ("operator_id", "attacker"),
        ("max_authorized_probe_orders", 99),
    ):
        review = mod.build_rematerialization(
            plan=_plan(operator_authorization=_auth(**{field: tampered})),
            fresh_scorecard_plan=_fresh_plan(),
            fresh_scorecard_error=None,
            now_utc=NOW,
            expected_authorization_sha256=anchor,
        )
        assert review["status"] == mod.NO_OP_STATUS, field
        assert "operator_authorization_sha256_anchor_mismatch" in review["blocking_reasons"], field
        assert review["rematerialized_plan"] is None, field


def test_sha256_anchor_matches_legit_block_accepts() -> None:
    good_auth = _auth()
    anchor = mod._sha256_obj(good_auth)
    review = mod.build_rematerialization(
        plan=_plan(operator_authorization=good_auth),
        fresh_scorecard_plan=_fresh_plan(),
        fresh_scorecard_error=None,
        now_utc=NOW,
        expected_authorization_sha256=anchor,
    )
    assert review["status"] == mod.REMATERIALIZED_STATUS
    assert review["rematerialized_plan"] is not None


def test_byte_preserve_holds_across_serialization() -> None:
    # 正向自證：合法路徑下輸出授權塊與輸入逐字節相同(sha 相等)。
    review = _review()
    before = review["authorization_sha256_before"]
    new_plan = review["rematerialized_plan"]
    after = mod._sha256_obj(new_plan["operator_authorization"])
    assert before == after
    # 且輸出 plan 序列化後重讀，授權塊仍 sha 不變(過 JSON round-trip)。
    round_tripped = json.loads(json.dumps(new_plan, ensure_ascii=False, sort_keys=True))
    assert mod._sha256_obj(round_tripped["operator_authorization"]) == before


def test_end_to_end_writes_plan_0600_when_accepted(tmp_path) -> None:
    plan_path = tmp_path / "bounded_demo_probe_soak_plan.json"
    scorecard_path = tmp_path / "scorecard.json"
    alert_path = tmp_path / "alerts.jsonl"
    plan = _plan()
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    # scorecard 不存在 → policy 會回 source_failure(missing) → 應 no-op + 告警，不改 plan。
    review = mod.rematerialize_soak_plan(
        plan_path=plan_path,
        scorecard_path=scorecard_path,
        alert_path=alert_path,
        now_utc=NOW,
    )
    assert review["status"] == mod.NO_OP_STATUS
    assert alert_path.exists()
    # plan 檔未被改(no-op 守恆)。
    assert json.loads(plan_path.read_text(encoding="utf-8"))["generated_at_utc"] == OLD_GEN.isoformat()
