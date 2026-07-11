"""E2 RETURN：WP2-A arbiter 的 P1 mutation-biting 測試。"""

from __future__ import annotations

import copy

import pytest

from program_code.ml_training.tests.test_alr_candidate_learning_arbiter import (
    SOURCE_HEAD,
    _candidate,
    _canonical_hash,
    _policy,
    _rehash_resource,
    _set_n_eff,
    _with_conservative_cost_evidence,
    build_candidate_learning_decision,
)


def _policy_v2(**overrides: object) -> dict[str, object]:
    policy: dict[str, object] = {
        "decision_ts_s": 1_782_086_400,
        "as_of_utc_date": "2026-06-22",
        "algorithm_version": "candidate_learning_arbiter_v2",
        "tie_break_version": "candidate_learning_tie_break_v1",
        "q18_scale": 18,
        "thresholds": {
            "e1_n_eff_min": 30,
            "e2_utc_days_min": 5,
            "e3_top_day_share_max": "0.5",
            "e4_censored_share_max": "0.3",
        },
        "row_budget": 10_000,
        "byte_budget": 1_000_000,
        "collection_window_days": 7,
        "max_new_entries_per_window": 70,
        "cooldown_seconds": 1_800,
        "unknown_portfolio_penalty": "1",
    }
    policy.update(overrides)
    stable_config = {
        key: value
        for key, value in policy.items()
        if key not in {"decision_ts_s", "as_of_utc_date"}
    }
    policy["policy_config_hash"] = _canonical_hash(stable_config)
    return policy


def _rehash_direct_policy(policy: dict[str, object]) -> None:
    stable_config = {
        key: value
        for key, value in policy.items()
        if key not in {"decision_ts_s", "as_of_utc_date", "policy_config_hash"}
    }
    policy["policy_config_hash"] = _canonical_hash(stable_config)


@pytest.mark.parametrize("mutation", ["top_level", "threshold"])
def test_rehashed_direct_policy_rejects_noncanonical_field_shapes(
    mutation: str,
) -> None:
    policy = _policy_v2()
    if mutation == "top_level":
        policy["unexpected_policy_field"] = True
    else:
        thresholds = dict(policy["thresholds"])
        thresholds["unexpected_threshold"] = "0.1"
        policy["thresholds"] = thresholds
    _rehash_direct_policy(policy)

    result = build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[_candidate()],
        prior_decisions=[],
        policy=policy,
    )

    assert result["candidate_assessments"][0]["blocker_codes"] == [
        "POLICY_INVALID"
    ]


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("strategy_version", "STRATEGY_VERSION_INVALID"),
        ("symbol_case", "SYMBOL_INVALID"),
        ("venue", "MARKET_IDENTITY_INVALID"),
        ("product", "MARKET_IDENTITY_INVALID"),
        ("horizon", "HORIZON_INVALID"),
        ("target_label", "TARGET_REGIME_INVALID"),
        ("target_hash", "TARGET_REGIME_HASH_INVALID"),
        ("identity_extra", "IDENTITY_FIELDS_INVALID"),
        ("target_extra", "TARGET_REGIME_INVALID"),
        ("context_extra", "CONTEXT_HASHES_FIELDS_INVALID"),
        ("cost_extra", "COST_EVIDENCE_FIELDS_INVALID"),
        ("cost_symbol", "COST_EVIDENCE_SEMANTICS_INVALID"),
        ("cost_sample_count", "COST_EVIDENCE_SEMANTICS_INVALID"),
        ("cost_timestamp", "COST_EVIDENCE_TIMESTAMP_INVALID"),
        ("cost_conservative_mean_bool_zero", "COST_EVIDENCE_SEMANTICS_INVALID"),
        ("cost_conservative_mean_float_zero", "COST_EVIDENCE_SEMANTICS_INVALID"),
        ("cost_conservative_tail_bool_zero", "COST_EVIDENCE_SEMANTICS_INVALID"),
        ("cost_conservative_tail_float_zero", "COST_EVIDENCE_SEMANTICS_INVALID"),
        ("quality_extra", "QUALITY_FIELDS_INVALID"),
        ("quality_coercion", "QUALITY_TYPES_INVALID"),
        ("evidence_extra", "EVIDENCE_FIELDS_INVALID"),
        ("evidence_coercion", "EVIDENCE_TYPES_INVALID"),
        ("next_gap_extra", "NEXT_GAP_INVALID"),
        ("resource_extra", "RESOURCE_FIELDS_INVALID"),
        ("resource_bucket_extra", "RESOURCE_BUCKET_FIELDS_INVALID"),
        ("portfolio_extra", "PORTFOLIO_FIELDS_INVALID"),
        ("portfolio_coercion", "PORTFOLIO_TYPES_INVALID"),
    ],
)
def test_arbiter_rejects_rehashed_noncanonical_producer_shapes(
    mutation: str,
    expected_code: str,
) -> None:
    candidate = _candidate()
    if mutation.startswith("cost_conservative_"):
        _with_conservative_cost_evidence(candidate)
    identity = candidate["identity"]
    if mutation == "strategy_version":
        identity["strategy_version"] = "v2.1.0"
    elif mutation == "symbol_case":
        identity["symbol"] = "btcusdt"
    elif mutation == "venue":
        identity["venue"] = "binance"
    elif mutation == "product":
        identity["product"] = "spot"
    elif mutation == "horizon":
        identity["horizon_minutes"] = 1_441
    elif mutation == "identity_extra":
        identity["unexpected"] = True
    elif mutation in {"target_label", "target_hash", "target_extra"}:
        target = dict(identity["target_regime"])
        if mutation == "target_label":
            target["label"] = "bull_high_vol"
            target["hash"] = _canonical_hash(
                {key: value for key, value in target.items() if key != "hash"}
            )
        elif mutation == "target_hash":
            target["hash"] = "f" * 64
        else:
            target["unexpected"] = True
            target["hash"] = _canonical_hash(
                {key: value for key, value in target.items() if key != "hash"}
            )
        identity["target_regime"] = target
    elif mutation == "context_extra":
        candidate["context_hashes"] = {
            **candidate["context_hashes"],
            "unexpected": "f" * 64,
        }
    elif mutation in {
        "cost_extra",
        "cost_symbol",
        "cost_sample_count",
        "cost_timestamp",
    }:
        cost_evidence = copy.deepcopy(candidate["cost_evidence"])
        if mutation == "cost_extra":
            cost_evidence["unexpected"] = True
        elif mutation == "cost_timestamp":
            cost_evidence["source_asof_utc"] = "2026-06-21T00:00:00Z"
        else:
            cost_evidence["mean_abs_source"] = {
                "scope": "SYMBOL",
                "symbol": "ETHUSDT" if mutation == "cost_symbol" else "BTCUSDT",
                "sample_count": 100 if mutation == "cost_symbol" else 19,
                "mean_abs_bps": 2.0,
            }
        candidate["cost_evidence"] = cost_evidence
    elif mutation.startswith("cost_conservative_"):
        cost_evidence = copy.deepcopy(candidate["cost_evidence"])
        source_field = (
            "mean_abs_source" if "_mean_" in mutation else "tail_source"
        )
        cost_evidence[source_field]["sample_count"] = (
            False if mutation.endswith("bool_zero") else 0.0
        )
        candidate["cost_evidence"] = cost_evidence
    elif mutation in {"quality_extra", "quality_coercion"}:
        quality = dict(candidate["quality"])
        if mutation == "quality_extra":
            quality["unexpected"] = True
        else:
            quality["censored_share"] = "0.1"
        candidate["quality"] = quality
    elif mutation in {"evidence_extra", "evidence_coercion", "next_gap_extra"}:
        evidence = dict(candidate["evidence"])
        if mutation == "evidence_extra":
            evidence["unexpected"] = True
        elif mutation == "evidence_coercion":
            evidence["mean_net_e"] = "0.05"
        else:
            evidence["next_gap"] = {
                **evidence["next_gap"],
                "unexpected": True,
            }
        candidate["evidence"] = evidence
    elif mutation in {"resource_extra", "resource_bucket_extra"}:
        resource = copy.deepcopy(candidate["resource"])
        if mutation == "resource_extra":
            resource["unexpected"] = True
        else:
            resource["daily_buckets"][0]["unexpected"] = 1
        _rehash_resource(resource)
        candidate["resource"] = resource
    else:
        portfolio = dict(candidate["portfolio"])
        if mutation == "portfolio_extra":
            portfolio["unexpected"] = "0"
        else:
            portfolio["sector_exposure_share"] = 0.1
        candidate["portfolio"] = portfolio

    result = build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[candidate],
        prior_decisions=[],
        policy=_policy_v2(),
    )

    assert result["candidate_assessments"][0]["blocker_codes"] == [
        expected_code
    ]


@pytest.mark.parametrize(
    "mutation",
    ("cluster_algebra", "cluster_count", "raw_attempt_count"),
)
def test_arbiter_rejects_rehashed_producer_count_and_cluster_drift(
    mutation: str,
) -> None:
    candidate = _candidate()
    evidence = dict(candidate["evidence"])
    if mutation == "cluster_algebra":
        evidence["cluster_se"] = 0.03
    elif mutation == "cluster_count":
        evidence["cluster_count"] = 4
    else:
        evidence["raw_attempt_count"] = 29
    candidate["evidence"] = evidence

    result = build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[candidate],
        prior_decisions=[],
        policy=_policy_v2(),
    )

    assert result["candidate_assessments"][0]["blocker_codes"] == [
        "EVIDENCE_ALGEBRA_INVALID"
    ]


def _with_candidate_resource(
    candidate: dict[str, object],
    *,
    rows: int = 700,
    byte_count: int = 7_000,
    zero_attested: bool = False,
) -> dict[str, object]:
    old_resource = candidate["resource"]
    daily_buckets = [
        {
            "utc_date": bucket["utc_date"],
            "scan_complete": bucket["scan_complete"],
            "distinct_entries": bucket["distinct_entries"],
        }
        for bucket in old_resource["daily_buckets"]
    ]
    estimator_payload = {
        "daily_buckets": daily_buckets,
        "estimated_rows_scanned": rows,
        "predicted_canonical_bytes": byte_count,
        "zero_resource_attested": zero_attested,
    }
    candidate["resource"] = {
        **estimator_payload,
        "resource_estimator_hash": _canonical_hash(estimator_payload),
    }
    return candidate


_REGIME_BUCKETS = tuple(
    f"{trend}|{volatility}|{liquidity}"
    for trend in ("bear", "neutral", "bull")
    for volatility in ("low_vol", "mid_vol", "high_vol")
    for liquidity in ("liquid", "thin")
)


def _with_regimes(
    candidate: dict[str, object], *, bull_heavy: bool = False, single: bool = False
) -> dict[str, object]:
    counts = {key: 0 for key in _REGIME_BUCKETS}
    if single:
        counts[_REGIME_BUCKETS[0]] = 30
    elif bull_heavy:
        for index, key in enumerate(key for key in _REGIME_BUCKETS if key.startswith("bull|")):
            counts[key] = 4 if index == 0 else 3
        non_bull = [key for key in _REGIME_BUCKETS if not key.startswith("bull|")]
        for key in non_bull[:11]:
            counts[key] = 1
    else:
        for index, key in enumerate(_REGIME_BUCKETS):
            counts[key] = 2 if index < 12 else 1
    counts["unknown"] = 0
    evidence = dict(candidate["evidence"])
    evidence["regime_entry_counts"] = counts
    candidate["evidence"] = evidence
    return candidate


def test_policy_config_hash_is_stable_across_clock_and_date() -> None:
    first_policy = _policy_v2()
    second_policy = _policy_v2(
        decision_ts_s=1_782_172_800,
        as_of_utc_date="2026-06-23",
    )

    first = build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[],
        prior_decisions=[],
        policy=first_policy,
    )
    second = build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[],
        prior_decisions=[],
        policy=second_policy,
    )

    assert first["policy_config_hash"] == first_policy["policy_config_hash"]
    assert second["policy_config_hash"] == first["policy_config_hash"]
    assert first["evaluated_at"] == "2026-06-22T00:00:00Z"
    assert second["evaluated_at"] == "2026-06-23T00:00:00Z"


def test_state_is_derived_from_evidence_not_laundered_by_next_gap() -> None:
    low_sample = _candidate()
    evidence = dict(low_sample["evidence"])
    evidence["next_gap"] = {"kind": "NONE", "code": "MISLABELED_READY"}
    _set_n_eff(evidence, 29)
    low_sample["evidence"] = evidence

    bad_replica = _candidate()
    quality = dict(bad_replica["quality"])
    quality["replica_inconsistency_count"] = 1
    bad_replica["quality"] = quality
    evidence = dict(bad_replica["evidence"])
    evidence["next_gap"] = {"kind": "LOCAL_PASSIVE", "code": "MISLABELED_PASSIVE"}
    bad_replica["evidence"] = evidence

    sample_result = build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[low_sample],
        prior_decisions=[],
        policy=_policy_v2(),
    )
    replica_result = build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[bad_replica],
        prior_decisions=[],
        policy=_policy_v2(),
    )

    assert sample_result["state"] == "COLLECT_DISTINCT_ENTRIES"
    assert sample_result["selected_collection_target"] is not None
    assert replica_result["state"] == "REPAIR_DATA_QUALITY"
    assert replica_result["selected_collection_target"] is None


def test_evi_uses_candidate_level_resource_estimator() -> None:
    candidate = _with_candidate_resource(_candidate())

    result = build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[candidate],
        prior_decisions=[],
        policy=_policy_v2(),
    )

    assert result["state"] == "DECISION_READY"
    metrics = result["evaluated_candidates"][0]["metrics"]
    assert metrics["compute"] == "0.070000000000000000"
    assert metrics["storage"] == "0.007000000000000000"


def test_zero_resource_requires_attestation_and_never_becomes_collection_target() -> None:
    contradictory = _with_candidate_resource(_candidate(), rows=0)
    contradiction_result = build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[contradictory],
        prior_decisions=[],
        policy=_policy_v2(),
    )

    zero = _candidate()
    resource = dict(zero["resource"])
    resource["daily_buckets"] = [
        {**bucket, "distinct_entries": 0} for bucket in resource["daily_buckets"]
    ]
    zero["resource"] = resource
    zero = _with_candidate_resource(zero, rows=0, byte_count=0, zero_attested=True)
    evidence = dict(zero["evidence"])
    evidence["next_gap"] = {"kind": "NONE", "code": "NO_RESOURCE_AVAILABLE"}
    _set_n_eff(evidence, 29)
    zero["evidence"] = evidence
    zero_result = build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[zero],
        prior_decisions=[],
        policy=_policy_v2(),
    )

    assert contradiction_result["state"] == "INELIGIBLE"
    assert contradiction_result["evaluated_candidates"][0]["blocker_codes"] == [
        "RESOURCE_SEMANTICS_INVALID"
    ]
    assert zero_result["selected_collection_target"] is None
    assert zero_result["state"] == "INELIGIBLE"


@pytest.mark.parametrize(
    ("rows", "byte_count"),
    ((0, 7_000), (700, 0)),
)
def test_asymmetric_zero_resource_never_becomes_free_collection(
    rows: int,
    byte_count: int,
) -> None:
    candidate = _candidate()
    resource = dict(candidate["resource"])
    resource["daily_buckets"] = [
        {**bucket, "distinct_entries": 0}
        for bucket in resource["daily_buckets"]
    ]
    candidate["resource"] = resource
    candidate = _with_candidate_resource(
        candidate,
        rows=rows,
        byte_count=byte_count,
        zero_attested=False,
    )
    evidence = dict(candidate["evidence"])
    _set_n_eff(evidence, 29)
    candidate["evidence"] = evidence

    result = build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[candidate],
        prior_decisions=[],
        policy=_policy_v2(),
    )

    assessment = result["evaluated_candidates"][0]
    assert assessment["state"] == "INELIGIBLE"
    assert assessment["blocker_codes"] == ["RESOURCE_SEMANTICS_INVALID"]
    assert result["selected_collection_target"] is None


def test_beta_above_one_is_finite_measured_redundancy_not_invalid() -> None:
    candidate = _with_regimes(_with_candidate_resource(_candidate()))
    candidate["portfolio"] = {
        **candidate["portfolio"],
        "beta_to_portfolio": "1.5",
    }

    result = build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[candidate],
        prior_decisions=[],
        policy=_policy_v2(),
    )

    assessment = result["evaluated_candidates"][0]
    assert assessment["state"] == "DECISION_READY"
    assert assessment["metrics"]["portfolio_redundancy"] == "1.500000000000000000"
    assert assessment["metrics"]["evi"] > "0.000000000000000000"


def test_regime_entropy_is_q18_and_bull_heavy_is_learning_only_ranked_after_diverse() -> None:
    diverse = _with_regimes(_with_candidate_resource(_candidate()))
    concentrated = _with_regimes(
        _with_candidate_resource(_candidate()), single=True
    )
    bull_heavy = _with_regimes(
        _with_candidate_resource(_candidate()), bull_heavy=True
    )
    identity = dict(bull_heavy["identity"])
    identity.update({"symbol": "BULLUSDT", "config_hash": "d" * 64})
    bull_heavy["identity"] = identity

    concentrated_result = build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[concentrated],
        prior_decisions=[],
        policy=_policy_v2(),
    )
    ranked = build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[bull_heavy, diverse],
        prior_decisions=[],
        policy=_policy_v2(),
    )

    assert concentrated_result["evaluated_candidates"][0]["metrics"][
        "regime_coverage"
    ] == "0.000000000000000000"
    by_symbol = {
        item["identity"]["symbol"]: item for item in ranked["evaluated_candidates"]
    }
    assert by_symbol["BULLUSDT"]["learning_only"] is True
    assert ranked["selected_candidate"]["identity"]["symbol"] == "BTCUSDT"


def test_global_consecutive_family_waits_after_1800_and_future_prior_repairs() -> None:
    policy = _policy_v2()
    first_candidate = _with_regimes(_with_candidate_resource(_candidate()))
    first = build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[first_candidate],
        prior_decisions=[],
        policy=policy,
    )["selected_candidate"]
    other_candidate = _with_regimes(_with_candidate_resource(_candidate()))
    identity = dict(other_candidate["identity"])
    identity.update({"symbol": "ETHUSDT", "config_hash": "e" * 64})
    other_candidate["identity"] = identity
    old_prior = [
        {
            "family_key": first["family_key"],
            "decision_ts_s": policy["decision_ts_s"] - 1_800,
            "material_fingerprint": first["material_fingerprint"],
        }
    ]

    rotated = build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[first_candidate, other_candidate],
        prior_decisions=old_prior,
        policy=policy,
    )
    by_symbol = {
        item["identity"]["symbol"]: item
        for item in rotated["evaluated_candidates"]
    }
    future_prior = [
        {
            "family_key": first["family_key"],
            "decision_ts_s": policy["decision_ts_s"] + 1,
            "material_fingerprint": first["material_fingerprint"],
        }
    ]
    future = build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[first_candidate],
        prior_decisions=future_prior,
        policy=policy,
    )

    assert by_symbol["BTCUSDT"]["state"] == "WAIT_COOLDOWN"
    assert rotated["selected_candidate"]["identity"]["symbol"] == "ETHUSDT"
    assert future["state"] == "REPAIR_DATA_QUALITY"
    assert "PRIOR_DECISION_FROM_FUTURE" in future["evaluated_candidates"][0][
        "blocker_codes"
    ]


def test_source_head_requires_exactly_40_lower_hex_characters() -> None:
    candidate = _with_regimes(_with_candidate_resource(_candidate()))
    result = build_candidate_learning_decision(
        source_head="a" * 64,
        scanner_research_seeds=[],
        candidate_evidence_board=[candidate],
        prior_decisions=[],
        policy=_policy_v2(),
    )

    assert result["state"] == "INELIGIBLE"
    assert result["evaluated_candidates"][0]["blocker_codes"] == [
        "SOURCE_HEAD_INVALID"
    ]


def test_policy_clock_mismatch_or_missing_algorithm_metadata_fails_closed() -> None:
    clock_mismatch = _policy_v2(decision_ts_s=1_782_172_800)
    missing_algorithm = _policy_v2()
    missing_algorithm.pop("algorithm_version")
    stable_config = {
        key: value
        for key, value in missing_algorithm.items()
        if key not in {"decision_ts_s", "as_of_utc_date", "policy_config_hash"}
    }
    missing_algorithm["policy_config_hash"] = _canonical_hash(stable_config)

    for policy in (clock_mismatch, missing_algorithm):
        result = build_candidate_learning_decision(
            source_head=SOURCE_HEAD,
            scanner_research_seeds=[],
            candidate_evidence_board=[],
            prior_decisions=[],
            policy=policy,
        )
        assert result["policy_config_hash"] is None
        assert result["evaluated_at"] is None


@pytest.mark.parametrize("penalty", ("1.0", "1e0", 1))
def test_rehashed_noncanonical_unknown_penalty_fails_closed(penalty: object) -> None:
    policy = _policy_v2(unknown_portfolio_penalty=penalty)

    result = build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[_candidate()],
        prior_decisions=[],
        policy=policy,
    )

    assert result["policy_config_hash"] is None
    assert result["selected_candidate"] is None
    assert result["evaluated_candidates"][0]["blocker_codes"] == ["POLICY_INVALID"]


def test_regime_counts_bind_n_eff_and_unknown_share() -> None:
    mismatched = _with_regimes(_with_candidate_resource(_candidate()))
    evidence = dict(mismatched["evidence"])
    counts = dict(evidence["regime_entry_counts"])
    counts[_REGIME_BUCKETS[0]] -= 1
    evidence["regime_entry_counts"] = counts
    mismatched["evidence"] = evidence

    result = build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[mismatched],
        prior_decisions=[],
        policy=_policy_v2(),
    )

    assert result["state"] == "INELIGIBLE"
    assert result["evaluated_candidates"][0]["blocker_codes"] == [
        "REGIME_COUNTS_N_EFF_MISMATCH"
    ]


def test_selected_view_is_self_describing_and_has_no_authority() -> None:
    candidate = _with_regimes(_with_candidate_resource(_candidate()))
    result = build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[candidate],
        prior_decisions=[],
        policy=_policy_v2(),
    )

    selected = result["selected_candidate"]
    assert selected["identity"]["horizon_minutes"] == 60
    assert selected["identity"]["engine_mode"] == "shadow"
    assert selected["identity"]["evidence_engine_mode"] == "demo"
    assert set(selected["context_hashes"]) == {"data", "evidence", "cost", "portfolio"}
    assert selected["proof_stage"] == 6
    assert selected["next_gap"]["kind"] == "NONE"
    assert selected["blocker_codes"] == []
    assert selected["metrics"]["evi"] == selected["evi"]
    assert selected["portfolio_assumption"] == "MEASURED"
    assert set(result["no_authority"].values()) == {False}
    assert set(result["authority_counters"].values()) == {0}


@pytest.mark.parametrize("value", (None, "shadow", "live"))
def test_evidence_engine_mode_is_required_and_demo_bounded(value: object) -> None:
    candidate = _candidate()
    identity = dict(candidate["identity"])
    if value is None:
        identity.pop("evidence_engine_mode")
    else:
        identity["evidence_engine_mode"] = value
    candidate["identity"] = identity

    result = build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[candidate],
        prior_decisions=[],
        policy=_policy(),
    )

    assert result["selected_candidate"] is None
    assert result["evaluated_candidates"][0]["blocker_codes"] == [
        "IDENTITY_FIELDS_INVALID" if value is None else "EVIDENCE_ENGINE_MODE_INVALID"
    ]


@pytest.mark.parametrize(
    ("threshold", "value"),
    (
        ("e1_n_eff_min", 1),
        ("e2_utc_days_min", 1),
        ("e3_top_day_share_max", "1"),
        ("e4_censored_share_max", "1"),
    ),
)
def test_frozen_hard_gates_cannot_be_lowered_by_a_rehashed_policy(
    threshold: str,
    value: object,
) -> None:
    policy = _policy_v2()
    thresholds = dict(policy["thresholds"])
    thresholds[threshold] = value
    policy["thresholds"] = thresholds
    stable_config = {
        key: item
        for key, item in policy.items()
        if key not in {"decision_ts_s", "as_of_utc_date", "policy_config_hash"}
    }
    policy["policy_config_hash"] = _canonical_hash(stable_config)

    result = build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[_candidate()],
        prior_decisions=[],
        policy=policy,
    )

    assert result["policy_config_hash"] is None
    assert result["selected_candidate"] is None
    assert result["evaluated_candidates"][0]["blocker_codes"] == ["POLICY_INVALID"]


@pytest.mark.parametrize(
    ("gap_kind", "expected_state", "expected_decision"),
    (
        ("EXTERNAL_OPERATOR", "EXTERNAL_GAP", "NO_QUALIFIED_CANDIDATE_EXTERNAL"),
        ("LOCAL_ENGINEERING", "REPAIR_DATA_QUALITY", "NO_QUALIFIED_CANDIDATE_REPAIR"),
    ),
)
def test_sample_deficit_never_launders_non_passive_gap_into_collection(
    gap_kind: str,
    expected_state: str,
    expected_decision: str,
) -> None:
    candidate = _with_regimes(_with_candidate_resource(_candidate()))
    evidence = dict(candidate["evidence"])
    _set_n_eff(evidence, 29)
    evidence["next_gap"] = {"kind": gap_kind, "code": "NOT_PASSIVE"}
    candidate["evidence"] = evidence

    result = build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[candidate],
        prior_decisions=[],
        policy=_policy_v2(),
    )

    assert result["state"] == expected_state
    assert result["decision"] == expected_decision
    assert result["selected_collection_target"] is None


def test_ready_ranking_prefers_higher_evi_before_family_hash() -> None:
    high = _with_regimes(_with_candidate_resource(_candidate()))
    high_identity = dict(high["identity"])
    high_identity.update({"symbol": "AAAUSDT", "config_hash": "a" * 64})
    high["identity"] = high_identity
    low = copy.deepcopy(high)
    low_identity = dict(low["identity"])
    low_identity.update({"symbol": "ZZZUSDT", "config_hash": "f" * 64})
    low["identity"] = low_identity
    low_resource = dict(low["resource"])
    low_resource["daily_buckets"] = [
        {**bucket, "distinct_entries": 0}
        for bucket in low_resource["daily_buckets"]
    ]
    _rehash_resource(low_resource)
    low["resource"] = low_resource

    result = build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[high, low],
        prior_decisions=[],
        policy=_policy_v2(),
    )
    by_symbol = {
        item["identity"]["symbol"]: item for item in result["evaluated_candidates"]
    }

    assert by_symbol["AAAUSDT"]["metrics"]["evi"] > by_symbol["ZZZUSDT"][
        "metrics"
    ]["evi"]
    assert result["selected_candidate"]["identity"]["symbol"] == "AAAUSDT"


def test_exact_metric_tie_across_target_regimes_is_permutation_stable() -> None:
    first = _with_regimes(_with_candidate_resource(_candidate()))
    second = copy.deepcopy(first)
    second_identity = dict(second["identity"])
    second_target = {
        **second_identity["target_regime"],
        "label": "bear|low_vol|liquid",
    }
    second_target["hash"] = _canonical_hash(
        {key: value for key, value in second_target.items() if key != "hash"}
    )
    second_identity["target_regime"] = second_target
    second["identity"] = second_identity

    forward = build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[first, second],
        prior_decisions=[],
        policy=_policy_v2(),
    )
    reversed_result = build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[second, first],
        prior_decisions=[],
        policy=_policy_v2(),
    )

    assert forward["selected_candidate"]["evaluation_id"] == reversed_result[
        "selected_candidate"
    ]["evaluation_id"]
    assert forward["candidate_assessments"] == reversed_result[
        "candidate_assessments"
    ]
    assert forward["decision_hash"] == reversed_result["decision_hash"]


def test_clean_stage_one_with_no_next_gap_is_decision_ready() -> None:
    candidate = _candidate()
    evidence = dict(candidate["evidence"])
    evidence.update(
        {
            "proof_stage": 1,
            "completed_proof_stages": [0, 1],
            "next_gap": {"kind": "NONE", "code": "DATA_GATES_READY"},
        }
    )
    candidate["evidence"] = evidence
    result = build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[candidate],
        prior_decisions=[],
        policy=_policy(),
    )
    assert result["state"] == "DECISION_READY"


def test_only_proven_complete_zero_day_is_counted_as_zero() -> None:
    proven_zero = _candidate()
    resource = dict(proven_zero["resource"])
    buckets = [dict(item) for item in resource["daily_buckets"]]
    buckets[0]["distinct_entries"] = 0
    resource["daily_buckets"] = buckets
    _rehash_resource(resource)
    proven_zero["resource"] = resource
    missing_day = _candidate()
    resource = dict(missing_day["resource"])
    resource["daily_buckets"] = list(resource["daily_buckets"])[1:]
    missing_day["resource"] = resource
    accepted = build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[proven_zero],
        prior_decisions=[],
        policy=_policy(),
    )
    rejected = build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[missing_day],
        prior_decisions=[],
        policy=_policy(),
    )
    assert accepted["state"] == "DECISION_READY"
    assert rejected["state"] == "INELIGIBLE"


@pytest.mark.parametrize(
    ("case", "expected_code"),
    [
        ("side", "SIDE_INVALID"),
        ("horizon", "HORIZON_INVALID"),
        ("regime", "TARGET_REGIME_INVALID"),
        ("mode", "ENGINE_MODE_NOT_SHADOW"),
        ("config", "CONFIG_HASH_INVALID"),
        ("context", "CONTEXT_HASHES_FIELDS_INVALID"),
    ],
)
def test_partial_or_non_shadow_identity_is_ineligible(
    case: str, expected_code: str
) -> None:
    candidate = _candidate()
    if case == "context":
        candidate["context_hashes"] = {"data": "3" * 64}
    else:
        identity = dict(candidate["identity"])
        if case == "side":
            identity["side"] = "NONE"
        elif case == "horizon":
            identity["horizon_minutes"] = 0
        elif case == "regime":
            regime = dict(identity["target_regime"])
            regime["utc_date"] = "2026-06-22"
            identity["target_regime"] = regime
        elif case == "mode":
            identity["engine_mode"] = "live"
        elif case == "config":
            identity["config_hash"] = "not-a-hash"
        candidate["identity"] = identity
    result = build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[candidate],
        prior_decisions=[],
        policy=_policy(),
    )
    assert result["state"] == "INELIGIBLE"
    assert result["evaluated_candidates"][0]["blocker_codes"] == [expected_code]


def test_family_key_excludes_regime_and_context_but_evaluation_id_binds_them() -> None:
    first = _candidate()
    second = _candidate()
    identity = dict(second["identity"])
    regime = dict(identity["target_regime"])
    regime["label"] = "bear|low_vol|liquid"
    regime["hash"] = _canonical_hash(
        {key: value for key, value in regime.items() if key != "hash"}
    )
    identity["target_regime"] = regime
    second["identity"] = identity
    context_hashes = dict(second["context_hashes"])
    context_hashes.update({"data": "a" * 64, "evidence": "b" * 64})
    second["context_hashes"] = context_hashes
    first_assessment = build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[first],
        prior_decisions=[],
        policy=_policy(),
    )["evaluated_candidates"][0]
    second_assessment = build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[second],
        prior_decisions=[],
        policy=_policy(),
    )["evaluated_candidates"][0]
    assert first_assessment["family_key"] == second_assessment["family_key"]
    assert first_assessment["evaluation_id"] != second_assessment["evaluation_id"]
