from __future__ import annotations

from ml_training.candidate_signal_spec import (
    SIGNAL_SPEC_FIELD,
    SIGNAL_SPEC_SCHEMA_VERSION,
    compute_signal_spec_hash,
    extract_signal_spec,
    validate_signal_spec,
)


def _valid_signal_spec(**overrides) -> dict:
    spec = {
        "schema_version": SIGNAL_SPEC_SCHEMA_VERSION,
        "candidate_id": "candidate-alpha-1",
        "family_id": "family-alpha",
        "hypothesis": "funding and orderbook imbalance residual alpha",
        "horizon": {"bars": 12, "unit": "1m"},
        "inputs": ["funding_rate", "orderbook_imbalance_top5", "BTCUSDT_return"],
        "pit_contract": {
            "point_in_time": True,
            "future_data_allowed": False,
        },
        "universe_ref": {"source": "research.alpha_symbol_universe", "hash": "u"},
        "regime_ref": {"source": "research.aeg_regime_labels", "hash": "r"},
        "feature_schema": {"version": "edge17"},
        "cost_model_ref": {"source": "demo_cost_baseline", "version": "v1"},
        "residualization": {
            "method": "ols",
            "factors": ["BTCUSDT_return", "pit_universe_equal_weight_return"],
        },
        "failure_taxonomy": ["beta_edge", "cost_defeat", "data_leak"],
        "hidden_oos_policy": {"state_required": "sealed", "open_once": True},
    }
    spec.update(overrides)
    return spec


def test_valid_signal_spec_hashes_and_passes():
    spec = _valid_signal_spec()
    spec_hash = compute_signal_spec_hash(spec)

    validation = validate_signal_spec(
        spec,
        expected_spec_hash=spec_hash,
        candidate_id="candidate-alpha-1",
        family_id="family-alpha",
    )

    assert validation.ok is True
    assert validation.reason == "ok"
    assert validation.spec_hash == spec_hash


def test_extract_reads_only_canonical_field():
    spec = _valid_signal_spec()

    assert extract_signal_spec({SIGNAL_SPEC_FIELD: spec}) == spec
    assert extract_signal_spec({"factor_spec": spec}) is None


def test_hash_ignores_embedded_spec_hash():
    spec = _valid_signal_spec()
    spec_hash = compute_signal_spec_hash(spec)
    spec["spec_hash"] = spec_hash

    assert compute_signal_spec_hash(spec) == spec_hash
    assert validate_signal_spec(spec, expected_spec_hash=spec_hash).ok is True


def test_expected_hash_mismatch_is_invalid():
    validation = validate_signal_spec(
        _valid_signal_spec(),
        expected_spec_hash="0" * 64,
    )

    assert validation.ok is False
    assert validation.verdict == "invalid"
    assert validation.reason == "expected_spec_hash_mismatch"


def test_pit_contract_future_data_is_invalid():
    validation = validate_signal_spec(
        _valid_signal_spec(
            pit_contract={
                "point_in_time": True,
                "future_data_allowed": True,
            }
        )
    )

    assert validation.ok is False
    assert validation.verdict == "invalid"
    assert validation.reason == "pit_contract_future_data_allowed"


def test_missing_residualization_is_pending_schema():
    spec = _valid_signal_spec()
    spec.pop("residualization")

    validation = validate_signal_spec(spec)

    assert validation.ok is False
    assert validation.verdict == "pending_schema"
    assert validation.reason == "residualization_missing"
