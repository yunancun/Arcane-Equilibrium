"""candidate_evaluation_context_v1 的公共契約測試。"""

from __future__ import annotations

import hashlib
from copy import deepcopy

import pytest

from cost_gate_learning_lane.candidate_evaluation_context import (
    CandidateEvaluationContextError,
    REGIME_BUCKETS,
    build_candidate_evaluation_context,
    candidate_learning_context_projection,
    canonical_sha256,
    validate_candidate_evaluation_context,
)


def _sha(value: object) -> str:
    return canonical_sha256(value)


def test_canonical_sha256_matches_rust_serde_json_float_and_utf8_bytes() -> None:
    value = {"z": 1e-7, "a": [1e16, 1e-6, 1e-5, -0.0, "嘉楠"]}
    rust_bytes = '{"a":[1e+16,1e-6,0.00001,-0.0,"嘉楠"],"z":1e-7}'.encode()

    assert canonical_sha256(value) == hashlib.sha256(rust_bytes).hexdigest()


def _event_context() -> dict[str, object]:
    portfolio_snapshot = {
        "schema_version": "candidate_portfolio_snapshot_v1",
        "captured_at_ms": 1_783_700_000_000,
        "balance": 10_000.0,
        "accepted_demo_equity_usdt": 10_000.0,
        "peak_balance": 10_000.0,
        "drawdown_pct": 0.0,
        "position_count": 0,
        "gross_mark_notional_usdt": 0.0,
        "net_mark_notional_usdt": 0.0,
        "total_realized_pnl": 0.0,
        "total_fees": 0.0,
        "total_funding_pnl": 0.0,
        "trade_count": 0,
    }
    strategy_config_hash = _sha({
        "strategy_params": {"slow": 20, "fast": 5},
        "conf_scale": 1.0,
    })
    body: dict[str, object] = {
        "schema_version": "candidate_event_context_v1",
        "captured_at_ms": 1_783_700_000_000,
        "strategy_name": "ma_crossover",
        "strategy_version": "0123456789abcdef0123456789abcdef01234567",
        "build_git_sha": "0123456789abcdef0123456789abcdef01234567",
        "strategy_params_json": '{"slow":20,"fast":5}',
        "strategy_params_canonical_json": '{"fast":5,"slow":20}',
        "conf_scale": 1.0,
        "strategy_config_hash": strategy_config_hash,
        "symbol": "BTCUSDT",
        "side": "Buy",
        "horizon_policy": {
            "schema_version": "candidate_horizon_policy_v1",
            "source": "default_60_minutes",
            "outcome_horizon_minutes": 60,
            "default_applied": True,
        },
        "evidence_engine_mode": "live_demo",
        "pipeline_kind": "live",
        "endpoint_environment": "live_demo",
        "venue": "bybit",
        "product": "linear_perpetual",
        "context_id": "ctx-live_demo-BTCUSDT-1783700000000",
        "signal_id": "sig-live_demo-ma_crossover-BTCUSDT-1783700000000",
        "scan_id": "scan-20260710-001",
        "scanner_inputs": {
            "authority_mode": "advisory",
            "legacy_would_block": False,
            "legacy_block_reason": None,
            "scan_id": "scan-20260710-001",
            "best_strategy": "ma_crossover",
            "intent_strategy": "ma_crossover",
            "market_regime": "range",
            "trend_phase": "neutral",
            "trend_score": 0.1,
            "range_score": 0.8,
            "shock_score": 0.0,
            "close_alignment": 0.5,
            "range_position": 0.4,
            "crowding_score": 0.2,
            "reversal_risk_score": 0.1,
            "directional_efficiency": 0.3,
            "dir_pct": 0.2,
            "signed_dir_pct": -0.2,
            "range_pct": 0.6,
            "fr_bps": 0.4,
            "f_ma": 61.0,
            "f_grid": 40.0,
            "f_bbrv": 55.0,
            "f_bkout": 12.0,
            "f_funding_arb": 8.0,
            "edge_bps": -2.5,
            "edge_n": 17,
            "edge_status": "observed",
            "route_mode": "advisory",
            "market_status": "compatible",
            "route_reason": "scanner_candidate",
            "opportunity": None,
            "final_score": 58.0,
            "raw_score": 62.0,
        },
        "market_inputs": {
            "observed_at_ms": 1_783_700_000_000,
            "last_price": 2_500.0,
            "best_bid": 2_499.9,
            "best_ask": 2_500.1,
            "tick_size": 0.1,
            "index_price": 2_499.8,
            "funding_rate": 0.0001,
            "open_interest": 1_000_000.0,
            "atr_value": 25.0,
        },
        "risk_context": {
            "risk_state": "NORMAL",
            "governance_profile": "Validation",
            "risk_config_hash": _sha({"limits": {"leverage_max": 2.0}}),
        },
        "portfolio_snapshot": portfolio_snapshot,
        "portfolio_snapshot_ref": (
            "paper_state:live_demo:ctx-live_demo-BTCUSDT-1783700000000:1783700000000"
        ),
        "portfolio_snapshot_hash": _sha(portfolio_snapshot),
        "capture_status": "CAPTURE_COMPLETE",
        "capture_blockers": [],
        "boundary": (
            "immutable learning evidence only; no training, serving, promotion, order, "
            "lease, gate, config, broker, or runtime authority"
        ),
    }
    return {**body, "event_hash": _sha(body)}


def _rehash_event(event: dict[str, object]) -> dict[str, object]:
    body = {key: value for key, value in event.items() if key != "event_hash"}
    return {**body, "event_hash": _sha(body)}


def _resource() -> dict[str, object]:
    body: dict[str, object] = {
        "daily_buckets": [
            {
                "utc_date": f"2026-07-{day:02d}",
                "scan_complete": True,
                "distinct_entries": 5,
            }
            for day in range(3, 10)
        ],
        "estimated_rows_scanned": 700,
        "predicted_canonical_bytes": 7_000,
        "zero_resource_attested": False,
    }
    return {**body, "resource_estimator_hash": _sha(body)}


def _rehash_resource(resource: dict[str, object]) -> dict[str, object]:
    body = {
        key: value
        for key, value in resource.items()
        if key != "resource_estimator_hash"
    }
    return {**body, "resource_estimator_hash": _sha(body)}


def _hidden_oos_state(*, state: str = "sealed") -> dict[str, object]:
    consumed = state == "consumed"
    opened = state in {"opened", "consumed"}
    body = {
        "schema_version": "hidden_oos_state_v1",
        "state": state,
        "open_count": 1 if opened else 0,
        "opened_for_iteration": opened,
        "consumed": consumed,
        "invalidated": state == "invalidated",
        "family_id": "ma_crossover-v1",
        "split_hash": "8" * 64,
    }
    return {**body, "state_hash": _sha(body)}


def _valid_build_kwargs() -> dict[str, object]:
    return {
        "candidate_event_context": _event_context(),
        "as_of_utc_date": "2026-07-10",
        "evidence_regime_label": "neutral|low_vol|liquid",
        "regime_entry_counts": {
            **{
                f"{trend}|{volatility}|{liquidity}": 0
                for trend in ("bear", "neutral", "bull")
                for volatility in ("low_vol", "mid_vol", "high_vol")
                for liquidity in ("liquid", "thin")
            },
            "neutral|low_vol|liquid": 30,
            "unknown": 0,
        },
        "target_regime_context": {
            "label": "neutral|low_vol|liquid",
            "utc_date": "2026-07-09",
            "point_in_time": "D-1",
            "source_complete": True,
            "source_hash": "2" * 64,
            "classifier_hash": "3" * 64,
        },
        "context_hashes": {
            "data": "4" * 64,
            "evidence": "5" * 64,
            "cost": "6" * 64,
            "portfolio": "7" * 64,
        },
        "resource": _resource(),
        "portfolio": {
            "sector_exposure_share": "0.10",
            "strategy_active_target_share": "0.20",
            "beta_to_portfolio": "-1.50",
        },
        "proof": {
            "proof_stage": 1,
            "completed_proof_stages": [0, 1],
            "next_gap": {"kind": "LOCAL_PASSIVE", "code": "COLLECT_MORE"},
        },
        "hidden_oos_state": _hidden_oos_state(),
    }


def _build_valid(**overrides: object) -> dict[str, object]:
    kwargs = _valid_build_kwargs()
    kwargs.update(overrides)
    return build_candidate_evaluation_context(**kwargs)  # type: ignore[arg-type]


def test_builds_valid_hash_bound_context_and_compatible_projection() -> None:
    context = _build_valid()

    assert validate_candidate_evaluation_context(context) == context
    assert context["schema_version"] == "candidate_evaluation_context_v1"
    assert context["evidence_regime_label"] == "neutral|low_vol|liquid"
    assert context["portfolio"] == {
        "sector_exposure_share": "0.1",
        "strategy_active_target_share": "0.2",
        "beta_to_portfolio": "-1.5",
    }
    assert len(context["candidate_evaluation_context_hash"]) == 64

    projection = candidate_learning_context_projection(context)
    assert projection["strategy_version"] == "0123456789abcdef0123456789abcdef01234567"
    assert projection["strategy_config_hash"] == _event_context()["strategy_config_hash"]
    assert projection["target_regime_context"] == {
        "label": "neutral|low_vol|liquid",
        "utc_date": "2026-07-09",
        "point_in_time": "D-1",
    }
    assert projection["hidden_oos_consumed"] is False
    assert "event_hash" not in projection
    assert "candidate_evaluation_context_hash" not in projection


@pytest.mark.parametrize(
    "mutate",
    [
        lambda event: event.__setitem__("symbol", "btcusdt"),
        lambda event: event["scanner_inputs"].__setitem__(  # type: ignore[union-attr]
            "intent_strategy", "grid_trading"
        ),
        lambda event: event["market_inputs"].__setitem__(  # type: ignore[union-attr]
            "observed_at_ms", 1_783_700_000_001
        ),
        lambda event: event["market_inputs"].__setitem__(  # type: ignore[union-attr]
            "best_bid", 2_500.2
        ),
        lambda event: event["risk_context"].__setitem__(  # type: ignore[union-attr]
            "risk_state", "UNKNOWN"
        ),
        lambda event: event["risk_context"].__setitem__(  # type: ignore[union-attr]
            "governance_profile", "Production"
        ),
        lambda event: event["portfolio_snapshot"].__setitem__(  # type: ignore[union-attr]
            "peak_balance", 9_999.0
        ),
        lambda event: event.__setitem__("portfolio_snapshot_ref", "paper_state:current"),
        lambda event: event.__setitem__("boundary", "learning authority"),
    ],
)
def test_revalidates_complete_event_semantics_independent_of_valid_hash(mutate) -> None:
    event = _event_context()
    mutate(event)
    event = _rehash_event(event)

    with pytest.raises(CandidateEvaluationContextError):
        _build_valid(candidate_event_context=event)


@pytest.mark.parametrize("kind", ["missing", "hash_mutated", "blocked", "legacy"])
def test_requires_complete_immutable_event_without_backfill(kind: str) -> None:
    event = _event_context()
    if kind == "missing":
        event.pop("market_inputs")
        event = _rehash_event(event)
    elif kind == "hash_mutated":
        event["symbol"] = "ETHUSDT"
    elif kind == "blocked":
        event["capture_status"] = "CAPTURE_BLOCKED"
        event["capture_blockers"] = ["BBO_MISSING_OR_INVALID"]
        event = _rehash_event(event)
    else:
        event = {"schema_version": "candidate_event_context_v0"}

    with pytest.raises(CandidateEvaluationContextError):
        _build_valid(candidate_event_context=event)


def test_live_demo_evidence_accepts_demo_endpoint_with_live_pipeline() -> None:
    event = _event_context()
    event["endpoint_environment"] = "demo"

    context = _build_valid(candidate_event_context=_rehash_event(event))

    assert context["identity"]["evidence_engine_mode"] == "live_demo"  # type: ignore[index]


def test_accepts_reduced_risk_state_emitted_by_rust_risk_governor() -> None:
    event = _event_context()
    event["risk_context"]["risk_state"] = "REDUCED"  # type: ignore[index]

    context = _build_valid(candidate_event_context=_rehash_event(event))

    assert context["identity"]["symbol"] == "BTCUSDT"  # type: ignore[index]


def test_accepts_each_fixed_regime_bucket_and_explicit_unknown_bucket() -> None:
    assert len(REGIME_BUCKETS) == 18
    for label in (*REGIME_BUCKETS, "unknown"):
        counts = {bucket: 0 for bucket in (*REGIME_BUCKETS, "unknown")}
        counts[label] = 1
        context = _build_valid(
            evidence_regime_label=label,
            regime_entry_counts=counts,
        )
        assert context["evidence_regime_label"] == label
        assert context["regime_entry_counts"][label] == 1  # type: ignore[index]


@pytest.mark.parametrize("kind", ["d0", "incomplete", "17_buckets", "empty", "unknown_key"])
def test_rejects_non_d_minus_one_or_incomplete_regime_inputs(kind: str) -> None:
    kwargs = _valid_build_kwargs()
    target = deepcopy(kwargs["target_regime_context"])
    counts = deepcopy(kwargs["regime_entry_counts"])
    if kind == "d0":
        target["utc_date"] = "2026-07-10"
        target["point_in_time"] = "D0"
    elif kind == "incomplete":
        target["source_complete"] = False
    elif kind == "17_buckets":
        counts.pop(REGIME_BUCKETS[0])
    elif kind == "empty":
        counts["neutral|low_vol|liquid"] = 0
    else:
        counts["raw-unclassified"] = 1
    kwargs["target_regime_context"] = target
    kwargs["regime_entry_counts"] = counts

    with pytest.raises(CandidateEvaluationContextError):
        build_candidate_evaluation_context(**kwargs)  # type: ignore[arg-type]


def test_accepts_attested_zero_resource_only_for_seven_complete_empty_days() -> None:
    resource = _resource()
    resource["estimated_rows_scanned"] = 0
    resource["predicted_canonical_bytes"] = 0
    resource["zero_resource_attested"] = True
    for bucket in resource["daily_buckets"]:  # type: ignore[union-attr]
        bucket["distinct_entries"] = 0
    context = _build_valid(resource=_rehash_resource(resource))

    assert context["resource"]["zero_resource_attested"] is True  # type: ignore[index]


@pytest.mark.parametrize(
    "kind",
    ["six_days", "incomplete", "negative", "unattested_zero", "false_zero", "asymmetric", "hash"],
)
def test_rejects_incomplete_or_contradictory_resource_evidence(kind: str) -> None:
    resource = _resource()
    if kind == "six_days":
        resource["daily_buckets"].pop()  # type: ignore[union-attr]
    elif kind == "incomplete":
        resource["daily_buckets"][0]["scan_complete"] = False  # type: ignore[index]
    elif kind == "negative":
        resource["estimated_rows_scanned"] = -1
    elif kind == "unattested_zero":
        resource["estimated_rows_scanned"] = 0
        resource["predicted_canonical_bytes"] = 0
        for bucket in resource["daily_buckets"]:  # type: ignore[union-attr]
            bucket["distinct_entries"] = 0
    elif kind == "false_zero":
        resource["estimated_rows_scanned"] = 0
        resource["predicted_canonical_bytes"] = 0
        resource["zero_resource_attested"] = True
    elif kind == "asymmetric":
        resource["estimated_rows_scanned"] = 0
    else:
        resource["resource_estimator_hash"] = "f" * 64
    if kind != "hash":
        resource = _rehash_resource(resource)

    with pytest.raises(CandidateEvaluationContextError):
        _build_valid(resource=resource)


@pytest.mark.parametrize(
    ("beta", "expected"),
    [("10", "10"), ("100", "100"), ("-0.0", "0"), ("-1.50", "-1.5")],
)
def test_decimal_strings_preserve_integer_magnitude_and_normalize_safely(
    beta: str,
    expected: str,
) -> None:
    context = _build_valid(portfolio={
        "sector_exposure_share": "0.10",
        "strategy_active_target_share": "1.00",
        "beta_to_portfolio": beta,
    })

    assert context["portfolio"] == {
        "sector_exposure_share": "0.1",
        "strategy_active_target_share": "1",
        "beta_to_portfolio": expected,
    }


@pytest.mark.parametrize(
    "portfolio",
    [
        {"sector_exposure_share": "1.01", "strategy_active_target_share": "0.2", "beta_to_portfolio": "1"},
        {"sector_exposure_share": "-0.01", "strategy_active_target_share": "0.2", "beta_to_portfolio": "1"},
        {"sector_exposure_share": 0.1, "strategy_active_target_share": "0.2", "beta_to_portfolio": "1"},
        {"sector_exposure_share": "0.1", "strategy_active_target_share": "0.2", "beta_to_portfolio": "NaN"},
        {"sector_exposure_share": "0.1", "strategy_active_target_share": "0.2", "beta_to_portfolio": "Infinity"},
    ],
)
def test_rejects_invalid_portfolio_decimal_contract(portfolio: dict[str, object]) -> None:
    with pytest.raises(CandidateEvaluationContextError):
        _build_valid(portfolio=portfolio)


@pytest.mark.parametrize("kind", ["skipped", "unknown_gap"])
def test_rejects_skipped_proof_prefix_or_unknown_gap(kind: str) -> None:
    proof = {
        "proof_stage": 2,
        "completed_proof_stages": [0, 2],
        "next_gap": {"kind": "LOCAL_PASSIVE", "code": "COLLECT_MORE"},
    }
    if kind == "unknown_gap":
        proof["proof_stage"] = 1
        proof["completed_proof_stages"] = [0, 1]
        proof["next_gap"]["kind"] = "BYPASS"
    with pytest.raises(CandidateEvaluationContextError):
        _build_valid(proof=proof)


@pytest.mark.parametrize("state", ["opened", "consumed", "invalidated"])
def test_any_valid_opened_hidden_oos_state_projects_consumed(state: str) -> None:
    context = _build_valid(hidden_oos_state=_hidden_oos_state(state=state))

    assert context["hidden_oos_consumed"] is True
    assert candidate_learning_context_projection(context)["hidden_oos_consumed"] is True


@pytest.mark.parametrize(
    "kind", ["missing", "dirty_sealed", "ambiguous_opened", "ambiguous_invalidated", "hash"]
)
def test_rejects_missing_or_ambiguous_hidden_oos_state(kind: str) -> None:
    state = _hidden_oos_state()
    if kind == "missing":
        state.pop("family_id")
    elif kind == "dirty_sealed":
        state["open_count"] = 1
    elif kind == "ambiguous_opened":
        state["state"] = "opened"
    elif kind == "ambiguous_invalidated":
        state["state"] = "invalidated"
        state["invalidated"] = True
        state["open_count"] = 1
    else:
        state["state_hash"] = "f" * 64
    if kind != "hash":
        state = {
            **{key: value for key, value in state.items() if key != "state_hash"},
            "state_hash": _sha({
                key: value for key, value in state.items() if key != "state_hash"
            }),
        }

    with pytest.raises(CandidateEvaluationContextError):
        _build_valid(hidden_oos_state=state)


def _rehash_evaluation(context: dict[str, object]) -> dict[str, object]:
    body = {
        key: value
        for key, value in context.items()
        if key != "candidate_evaluation_context_hash"
    }
    return {**body, "candidate_evaluation_context_hash": _sha(body)}


def test_evaluation_hash_detects_mutation_and_only_itself_is_excluded() -> None:
    context = _build_valid()
    context["portfolio"]["beta_to_portfolio"] = "2"  # type: ignore[index]
    with pytest.raises(CandidateEvaluationContextError):
        validate_candidate_evaluation_context(context)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("symbol", "btcusdt"),
        ("venue", "binance"),
        ("product", "spot"),
    ],
)
def test_standalone_validation_rejects_rehashed_market_identity_mutation(
    field: str,
    value: str,
) -> None:
    context = _build_valid()
    context["identity"][field] = value  # type: ignore[index]
    context = _rehash_evaluation(context)

    with pytest.raises(CandidateEvaluationContextError):
        validate_candidate_evaluation_context(context)

    context = _build_valid()
    context["unbound_extra"] = "not canonical contract"
    context = _rehash_evaluation(context)
    with pytest.raises(CandidateEvaluationContextError):
        validate_candidate_evaluation_context(context)


def test_permuted_inputs_build_identical_context_and_hash_without_floats() -> None:
    expected = _build_valid()
    kwargs = _valid_build_kwargs()
    for key in (
        "candidate_event_context", "regime_entry_counts", "target_regime_context",
        "context_hashes", "portfolio", "proof", "hidden_oos_state",
    ):
        kwargs[key] = dict(reversed(list(kwargs[key].items())))  # type: ignore[union-attr]
    event = kwargs["candidate_event_context"]
    for key in ("scanner_inputs", "market_inputs", "portfolio_snapshot"):
        event[key] = dict(reversed(list(event[key].items())))
    resource = deepcopy(kwargs["resource"])
    resource["daily_buckets"] = list(reversed(resource["daily_buckets"]))
    resource["daily_buckets"] = [
        dict(reversed(list(bucket.items()))) for bucket in resource["daily_buckets"]
    ]
    kwargs["resource"] = resource

    actual = build_candidate_evaluation_context(**kwargs)  # type: ignore[arg-type]
    assert actual == expected

    def assert_no_float(value: object) -> None:
        assert not isinstance(value, float)
        if isinstance(value, dict):
            for item in value.values():
                assert_no_float(item)
        elif isinstance(value, list):
            for item in value:
                assert_no_float(item)

    assert_no_float(actual)


def test_projection_drops_per_event_hashes_so_same_cohort_does_not_false_conflict() -> None:
    first = _build_valid()
    event = _event_context()
    event["context_id"] = "ctx-live_demo-BTCUSDT-1783700000000-second"
    event["portfolio_snapshot_ref"] = (
        "paper_state:live_demo:ctx-live_demo-BTCUSDT-1783700000000-second:1783700000000"
    )
    second = _build_valid(candidate_event_context=_rehash_event(event))

    assert first["event_hash"] != second["event_hash"]
    assert first["candidate_evaluation_context_hash"] != second["candidate_evaluation_context_hash"]
    assert candidate_learning_context_projection(first) == candidate_learning_context_projection(second)


@pytest.mark.parametrize(
    "kind",
    ["data", "evidence", "cost", "portfolio", "target_source", "target_classifier", "resource", "proof", "oos"],
)
def test_each_bound_lineage_mutation_changes_evaluation_hash(kind: str) -> None:
    baseline = _build_valid()
    kwargs = _valid_build_kwargs()
    if kind in {"data", "evidence", "cost", "portfolio"}:
        kwargs["context_hashes"][kind] = "e" * 64
    elif kind.startswith("target_"):
        field = "source_hash" if kind == "target_source" else "classifier_hash"
        kwargs["target_regime_context"][field] = "e" * 64
    elif kind == "resource":
        resource = kwargs["resource"]
        resource["estimated_rows_scanned"] = 701
        kwargs["resource"] = _rehash_resource(resource)
    elif kind == "proof":
        kwargs["proof"]["next_gap"]["code"] = "WAIT_NEXT_DAY"
    else:
        kwargs["hidden_oos_state"] = _hidden_oos_state(state="consumed")

    changed = build_candidate_evaluation_context(**kwargs)  # type: ignore[arg-type]
    assert changed["candidate_evaluation_context_hash"] != baseline["candidate_evaluation_context_hash"]
