"""signal_spec producer 測試：核心是 producer 輸出**通過** validator。"""

from __future__ import annotations

from program_code.ml_training.candidate_signal_spec import (
    PROMOTION_READY,
    compute_signal_spec_hash,
    validate_signal_spec,
)
from program_code.ml_training.candidate_signal_spec_producer import build_signal_spec


def _spec(**over):
    params = dict(
        candidate_id="grid_trading::BTCUSDT::resid_v1",
        family_id="grid_trading",
        strategy_name="grid_trading",
        symbol="BTCUSDT",
        bucket_sec=14400.0,
        residual_report={"factor_panel_hash": "a" * 64},
    )
    params.update(over)
    return build_signal_spec(**params)


def test_build_signal_spec_validates_promotion_ready():
    spec = _spec()
    v = validate_signal_spec(
        spec, candidate_id="grid_trading::BTCUSDT::resid_v1", family_id="grid_trading"
    )
    assert v.ok is True
    assert v.verdict == PROMOTION_READY
    assert v.reason == "ok"


def test_spec_hash_self_consistent():
    spec = _spec()
    # 嵌入的 spec_hash 必須等於對其餘欄位重算（validator 也這樣查）
    assert spec["spec_hash"] == compute_signal_spec_hash(spec)


def test_pit_and_hidden_oos_hardwired():
    spec = _spec()
    assert spec["pit_contract"] == {"point_in_time": True, "future_data_allowed": False}
    assert spec["hidden_oos_policy"] == {"state_required": "sealed", "open_once": True}
    assert spec["residualization"]["factors"] == ["btc"]
    assert spec["residualization"]["factor_panel_hash"] == "a" * 64


def test_candidate_id_mismatch_fails_validation():
    spec = _spec()
    v = validate_signal_spec(spec, candidate_id="WRONG", family_id="grid_trading")
    assert v.ok is False
    assert any("candidate_id" in r for r in v.reasons)


def test_validates_without_factor_panel_hash():
    # residual_report 缺 factor_panel_hash → factors=["btc"] 仍滿足 validator
    spec = _spec(residual_report=None)
    assert spec["residualization"]["factor_panel_hash"] == ""
    v = validate_signal_spec(
        spec, candidate_id="grid_trading::BTCUSDT::resid_v1", family_id="grid_trading"
    )
    assert v.ok is True
