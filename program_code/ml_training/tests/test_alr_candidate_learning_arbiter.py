"""WP2-A candidate-aware learning arbiter 的公開行為測試。"""

import hashlib
import json
import math
from decimal import Decimal, ROUND_HALF_EVEN, localcontext

import pytest

from program_code.ml_training.alr_candidate_learning_arbiter import (
    build_candidate_learning_decision as _raw_build_candidate_learning_decision,
)


SOURCE_HEAD = "a" * 40
REGIME_BUCKETS = tuple(
    f"{trend}|{volatility}|{liquidity}"
    for trend in ("bear", "neutral", "bull")
    for volatility in ("low_vol", "mid_vol", "high_vol")
    for liquidity in ("liquid", "thin")
)


def _canonical_hash(value: object) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _rehash_candidate(candidate: dict[str, object]) -> dict[str, object]:
    candidate.setdefault("schema_version", "alr_candidate_arbiter_input_v2")
    candidate.pop("arbiter_input_hash", None)
    candidate["arbiter_input_hash"] = _canonical_hash(candidate)
    return candidate


def build_candidate_learning_decision(**kwargs: object) -> dict[str, object]:
    candidates = kwargs.get("candidate_evidence_board")
    if isinstance(candidates, list):
        for candidate in candidates:
            if isinstance(candidate, dict):
                _rehash_candidate(candidate)
    prior_decisions = kwargs.get("prior_decisions")
    if isinstance(prior_decisions, list):
        kwargs["prior_decisions"] = [
            {
                **prior,
                "decision_schema_version": prior.get(
                    "decision_schema_version",
                    "alr_candidate_learning_decision_v2",
                ),
            }
            if isinstance(prior, dict)
            else prior
            for prior in prior_decisions
        ]
    return _raw_build_candidate_learning_decision(**kwargs)


def _policy(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
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
    body.update(overrides)
    stable_config = {
        key: value
        for key, value in body.items()
        if key not in {"decision_ts_s", "as_of_utc_date"}
    }
    body["policy_config_hash"] = _canonical_hash(stable_config)
    return body


def _candidate(**overrides: object) -> dict[str, object]:
    target_regime_context = {
        "label": "bull|high_vol|liquid",
        "utc_date": "2026-06-21",
        "point_in_time": "D-1",
        "source_complete": True,
        "source_hash": "7" * 64,
        "classifier_hash": "8" * 64,
    }
    candidate: dict[str, object] = {
        "identity": {
            "strategy_name": "ma_crossover",
            "strategy_version": "a" * 40,
            "config_hash": "1" * 64,
            "symbol": "BTCUSDT",
            "side": "Buy",
            "horizon_minutes": 60,
            "target_regime": {
                **target_regime_context,
                "hash": _canonical_hash(target_regime_context),
            },
            "engine_mode": "shadow",
            "evidence_engine_mode": "demo",
            "venue": "bybit",
            "product": "linear_perpetual",
        },
        "context_hashes": {
            "data": "3" * 64,
            "evidence": "4" * 64,
            "cost": "5" * 64,
            "portfolio": "6" * 64,
        },
        "cost_evidence": {
            "schema_version": "alr_candidate_cost_evidence_v2",
            "basis": "expected_slippage_mean_abs_v1",
            "source_payload_sha256": "9" * 64,
            "source_asof_utc": "2026-06-21T00:00:00+00:00",
            "normalized_projection_sha256": "b" * 64,
            "max_age_hours": 48,
            "fee_floor_bps": 11.0,
            "mean_abs_source": {
                "scope": "GLOBAL",
                "symbol": None,
                "sample_count": 100,
                "mean_abs_bps": 2.0,
            },
            "tail_source": {
                "scope": "GLOBAL",
                "symbol": None,
                "sample_count": 100,
                "tail_bps": 8.0,
                "tail_metric": "cvar90",
            },
        },
        "quality": {
            "hash_ok": True,
            "integrity_ok": True,
            "freshness_ok": True,
            "censored_share": 0.10,
            "cost_recomputable_share": 1.0,
            "unknown_regime_share": 0.0,
            "replica_inconsistency_count": 0,
            "cluster_variance_clean": True,
            "hidden_oos_consumed": False,
            "legacy_optimistic_cost_present": False,
            "top_day_share": 0.40,
        },
        "evidence": {
            "n_eff": 30,
            "utc_day_count": 5,
            "mean_net_e": 0.05,
            "day_cluster_variance": 0.0004,
            "cluster_se": 0.02,
            "cluster_count": 5,
            "proof_stage": 6,
            "completed_proof_stages": [0, 1, 2, 3, 4, 5, 6],
            "next_gap": {"kind": "NONE", "code": "PROOF_COMPLETE"},
            "raw_attempt_count": 30,
            "regime_entry_counts": {
                **{
                    key: 2 if index < 12 else 1
                    for index, key in enumerate(REGIME_BUCKETS)
                },
                "unknown": 0,
            },
        },
        "resource": {
            "estimated_rows_scanned": 700,
            "predicted_canonical_bytes": 7_000,
            "zero_resource_attested": False,
            "daily_buckets": [
                {
                    "utc_date": f"2026-06-{day:02d}",
                    "scan_complete": True,
                    "distinct_entries": 5,
                }
                for day in range(15, 22)
            ]
        },
        "portfolio": {
            "sector_exposure_share": "0.1",
            "strategy_active_target_share": "0.2",
            "beta_to_portfolio": "0.3",
        },
    }
    _rehash_resource(candidate["resource"])
    candidate.update(overrides)
    return _rehash_candidate(candidate)


def _with_conservative_cost_evidence(
    candidate: dict[str, object],
) -> dict[str, object]:
    candidate["cost_evidence"] = {
        "schema_version": "alr_candidate_cost_evidence_v2",
        "basis": "conservative_v1",
        "source_payload_sha256": None,
        "source_asof_utc": None,
        "normalized_projection_sha256": None,
        "max_age_hours": 48,
        "fee_floor_bps": 11.0,
        "mean_abs_source": {
            "scope": "NONE",
            "symbol": None,
            "sample_count": 0,
            "mean_abs_bps": None,
        },
        "tail_source": {
            "scope": "NONE",
            "symbol": None,
            "sample_count": 0,
            "tail_bps": None,
            "tail_metric": None,
        },
    }
    quality = dict(candidate["quality"])
    quality["cost_recomputable_share"] = 0.0
    candidate["quality"] = quality
    return candidate


def _rehash_resource(resource: dict[str, object]) -> None:
    daily_buckets = [
        {
            "utc_date": bucket["utc_date"],
            "scan_complete": bucket["scan_complete"],
            "distinct_entries": bucket["distinct_entries"],
        }
        for bucket in resource["daily_buckets"]
    ]
    payload = {
        "daily_buckets": daily_buckets,
        "estimated_rows_scanned": resource["estimated_rows_scanned"],
        "predicted_canonical_bytes": resource["predicted_canonical_bytes"],
        "zero_resource_attested": resource["zero_resource_attested"],
    }
    resource["resource_estimator_hash"] = _canonical_hash(payload)


def _set_n_eff(evidence: dict[str, object], n_eff: int) -> None:
    counts = dict(evidence["regime_entry_counts"])
    counts[REGIME_BUCKETS[0]] += n_eff - sum(counts.values())
    evidence["regime_entry_counts"] = counts
    evidence["n_eff"] = n_eff


def test_scanner_seed_alone_never_creates_a_candidate() -> None:
    result = build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[{"symbol": "NOVELUSDT", "novelty": 999}],
        candidate_evidence_board=[],
        prior_decisions=[],
        policy=_policy(),
    )

    assert result["decision"] == "NO_QUALIFIED_CANDIDATE_ROTATE"
    assert result["selected_candidate"] is None
    assert result["selected_collection_target"] is None
    assert result["decision_code"] == result["decision"]
    assert result["evaluated_at"] == "2026-06-22T00:00:00Z"
    assert result["evaluated_candidates"] == result["candidate_assessments"]
    assert result["candidate_count"] == 0
    assert result["eligible_candidate_count"] == 0
    assert set(result["no_authority"].values()) == {False}
    assert set(result["authority_counters"].values()) == {0}
    assert result["candidate_assessments"] == []
    assert result["authority"]["has_order_authority"] is False


def test_complete_candidate_identity_can_become_decision_ready() -> None:
    result = build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[_candidate()],
        prior_decisions=[],
        policy=_policy(),
    )

    assert result["decision"] == "QUALIFIED_CANDIDATE_SELECTED"
    assert result["state"] == "DECISION_READY"
    selected = result["selected_candidate"]
    assert selected["family_key"] == result["candidate_assessments"][0]["family_key"]
    assert selected["evaluation_id"] == result["candidate_assessments"][0]["evaluation_id"]
    assert result["selected_collection_target"] is None
    assert result["candidate_count"] == 1
    assert result["eligible_candidate_count"] == 1
    assert all(
        value is False
        for key, value in result["authority"].items()
        if key.startswith("has_")
    )
    assert all(
        value == 0
        for key, value in result["authority"].items()
        if key.endswith("_count")
    )


@pytest.mark.parametrize(
    ("mutation", "expected"),
    (
        ("missing", "ARBITER_INPUT_FIELDS_INVALID"),
        ("extra", "COST_EVIDENCE_FIELDS_INVALID"),
    ),
)
def test_cost_evidence_is_an_exact_hash_bound_arbiter_input(
    mutation: str,
    expected: str,
) -> None:
    candidate = _candidate()
    if mutation == "missing":
        candidate.pop("cost_evidence")
    else:
        candidate["cost_evidence"]["unexpected"] = True

    result = build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[candidate],
        prior_decisions=[],
        policy=_policy(),
    )

    assert result["evaluated_candidates"][0]["blocker_codes"] == [expected]


def test_conservative_cost_evidence_accepts_exact_integer_zero_sample_counts() -> None:
    result = build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[
            _with_conservative_cost_evidence(_candidate())
        ],
        prior_decisions=[],
        policy=_policy(),
    )

    assessment = result["evaluated_candidates"][0]
    assert assessment["state"] == "REPAIR_DATA_QUALITY"
    assert assessment["blocker_codes"] == ["COST_NOT_RECOMPUTABLE"]


@pytest.mark.parametrize(
    ("source_asof_utc", "expected_state", "expected_blocker"),
    (
        ("2026-06-20T00:00:00+00:00", "DECISION_READY", None),
        (
            "2026-06-19T23:59:59+00:00",
            "INELIGIBLE",
            "COST_EVIDENCE_STALE",
        ),
        (
            "2026-06-22T00:00:01+00:00",
            "INELIGIBLE",
            "COST_EVIDENCE_FROM_FUTURE",
        ),
    ),
)
def test_cost_evidence_freshness_is_exact_against_decision_time(
    source_asof_utc: str,
    expected_state: str,
    expected_blocker: str | None,
) -> None:
    candidate = _candidate()
    candidate["cost_evidence"]["source_asof_utc"] = source_asof_utc

    result = build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[candidate],
        prior_decisions=[],
        policy=_policy(),
    )
    assessment = result["evaluated_candidates"][0]

    assert assessment["state"] == expected_state
    assert assessment["blocker_codes"] == (
        [] if expected_blocker is None else [expected_blocker]
    )


def test_cost_source_hash_delta_changes_material_not_evaluation_identity() -> None:
    baseline = build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[_candidate()],
        prior_decisions=[],
        policy=_policy(),
    )["evaluated_candidates"][0]
    changed_candidate = _candidate()
    changed_candidate["cost_evidence"]["source_payload_sha256"] = "c" * 64
    changed = build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[changed_candidate],
        prior_decisions=[],
        policy=_policy(),
    )["evaluated_candidates"][0]

    assert changed["evaluation_id"] == baseline["evaluation_id"]
    assert changed["material_fingerprint"] != baseline["material_fingerprint"]


def test_n_eff_gate_collects_at_29_and_opens_at_30() -> None:
    low = _candidate()
    low_evidence = dict(low["evidence"])
    low_evidence["next_gap"] = {
        "kind": "LOCAL_PASSIVE",
        "code": "NEED_DISTINCT_ENTRY",
    }
    _set_n_eff(low_evidence, 29)
    low["evidence"] = low_evidence

    collecting = build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[low],
        prior_decisions=[],
        policy=_policy(),
    )
    ready = build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[_candidate()],
        prior_decisions=[],
        policy=_policy(),
    )

    assert collecting["decision"] == "NO_QUALIFIED_CANDIDATE_COLLECT"
    assert collecting["state"] == "COLLECT_DISTINCT_ENTRIES"
    assert collecting["selected_candidate"] is None
    assert collecting["selected_collection_target"]["state"] == "COLLECT_DISTINCT_ENTRIES"
    assert ready["state"] == "DECISION_READY"


def test_mixed_ineligible_assessment_shapes_sort_deterministically() -> None:
    zero_resource = _candidate()
    evidence = dict(zero_resource["evidence"])
    _set_n_eff(evidence, 29)
    evidence["next_gap"] = {
        "kind": "LOCAL_PASSIVE",
        "code": "ZERO_RESOURCE_NO_COLLECTION",
    }
    zero_resource["evidence"] = evidence
    resource = dict(zero_resource["resource"])
    resource.update(
        {
            "estimated_rows_scanned": 0,
            "predicted_canonical_bytes": 0,
            "zero_resource_attested": True,
            "daily_buckets": [
                {**bucket, "distinct_entries": 0}
                for bucket in resource["daily_buckets"]
            ],
        }
    )
    _rehash_resource(resource)
    zero_resource["resource"] = resource
    kwargs = {
        "source_head": SOURCE_HEAD,
        "scanner_research_seeds": [],
        "prior_decisions": [],
        "policy": _policy(),
    }

    forward = build_candidate_learning_decision(
        **kwargs,
        candidate_evidence_board=[zero_resource, {}],
    )
    reverse = build_candidate_learning_decision(
        **kwargs,
        candidate_evidence_board=[{}, zero_resource],
    )

    assert forward["evaluated_candidates"] == reverse["evaluated_candidates"]
    assert [item["state"] for item in forward["evaluated_candidates"]] == [
        "INELIGIBLE",
        "INELIGIBLE",
    ]
    assert [item["metrics"] is None for item in forward["evaluated_candidates"]] == [
        False,
        True,
    ]


def test_utc_day_gate_collects_at_4_and_opens_at_5() -> None:
    low = _candidate()
    evidence = dict(low["evidence"])
    evidence.update(
        {
            "utc_day_count": 4,
            "cluster_count": 4,
            "next_gap": {"kind": "LOCAL_PASSIVE", "code": "NEED_UTC_DAY"},
        }
    )
    low["evidence"] = evidence

    collecting = build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[low],
        prior_decisions=[],
        policy=_policy(),
    )

    assert collecting["state"] == "COLLECT_DISTINCT_ENTRIES"
    assert collecting["candidate_assessments"][0]["blocker_codes"] == [
        "UTC_DAY_COUNT_BELOW_5"
    ]
    assert build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[_candidate()],
        prior_decisions=[],
        policy=_policy(),
    )["state"] == "DECISION_READY"


def test_top_day_share_accepts_half_and_blocks_above_half() -> None:
    boundary = _candidate()
    boundary_quality = dict(boundary["quality"])
    boundary_quality["top_day_share"] = 0.5
    boundary["quality"] = boundary_quality

    above = _candidate()
    above_quality = dict(above["quality"])
    above_quality["top_day_share"] = math.nextafter(0.5, 1.0)
    above["quality"] = above_quality
    above_evidence = dict(above["evidence"])
    above_evidence["next_gap"] = {
        "kind": "LOCAL_PASSIVE",
        "code": "DIVERSIFY_UTC_DAYS",
    }
    above["evidence"] = above_evidence

    accepted = build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[boundary],
        prior_decisions=[],
        policy=_policy(),
    )
    blocked = build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[above],
        prior_decisions=[],
        policy=_policy(),
    )

    assert accepted["state"] == "DECISION_READY"
    assert blocked["state"] == "COLLECT_DISTINCT_ENTRIES"
    assert "TOP_DAY_SHARE_ABOVE_0_5" in blocked["candidate_assessments"][0][
        "blocker_codes"
    ]


def test_censored_share_accepts_point_three_and_repairs_above_it() -> None:
    boundary = _candidate()
    quality = dict(boundary["quality"])
    quality["censored_share"] = 0.3
    boundary["quality"] = quality

    above = _candidate()
    quality = dict(above["quality"])
    quality["censored_share"] = math.nextafter(0.3, 1.0)
    above["quality"] = quality
    evidence = dict(above["evidence"])
    evidence["next_gap"] = {
        "kind": "LOCAL_ENGINEERING",
        "code": "REPAIR_CENSORING",
    }
    above["evidence"] = evidence

    accepted = build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[boundary],
        prior_decisions=[],
        policy=_policy(),
    )
    repair = build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[above],
        prior_decisions=[],
        policy=_policy(),
    )

    assert accepted["state"] == "DECISION_READY"
    assert repair["decision"] == "NO_QUALIFIED_CANDIDATE_REPAIR"
    assert repair["state"] == "REPAIR_DATA_QUALITY"
    assert repair["selected_collection_target"] is None


@pytest.mark.parametrize(
    ("field", "bad_value", "code"),
    [
        ("hash_ok", False, "HASH_CHECK_FAILED"),
        ("integrity_ok", False, "INTEGRITY_CHECK_FAILED"),
        ("freshness_ok", False, "FRESHNESS_CHECK_FAILED"),
        ("cost_recomputable_share", math.nextafter(1.0, 0.0), "COST_NOT_RECOMPUTABLE"),
        ("replica_inconsistency_count", 1, "REPLICA_INCONSISTENT"),
        ("cluster_variance_clean", False, "CLUSTER_VARIANCE_DEGENERATE"),
        ("hidden_oos_consumed", True, "HIDDEN_OOS_CONSUMED"),
        (
            "legacy_optimistic_cost_present",
            True,
            "LEGACY_OPTIMISTIC_COST_UNBACKFILLED",
        ),
    ],
)
def test_data_quality_hard_gates_require_repair(
    field: str, bad_value: object, code: str
) -> None:
    candidate = _candidate()
    quality = dict(candidate["quality"])
    quality[field] = bad_value
    candidate["quality"] = quality
    evidence = dict(candidate["evidence"])
    if field == "cluster_variance_clean":
        evidence["day_cluster_variance"] = 0.0
        evidence["cluster_se"] = None
    evidence["next_gap"] = {"kind": "LOCAL_ENGINEERING", "code": code}
    candidate["evidence"] = evidence

    result = build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[candidate],
        prior_decisions=[],
        policy=_policy(),
    )

    assert result["state"] == "REPAIR_DATA_QUALITY"
    assert code in result["candidate_assessments"][0]["blocker_codes"]


def test_clean_negative_evidence_remains_a_decision_target() -> None:
    candidate = _candidate()
    evidence = dict(candidate["evidence"])
    evidence["mean_net_e"] = -0.05
    candidate["evidence"] = evidence

    result = build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[candidate],
        prior_decisions=[],
        policy=_policy(),
    )

    assert result["state"] == "DECISION_READY"
    assert result["selected_candidate"] is not None
    assert result["candidate_assessments"][0]["blocker_codes"] == []


def test_evi_resource_and_portfolio_cost_outrank_scanner_novelty() -> None:
    lean = _candidate()
    expensive = _candidate()
    identity = dict(expensive["identity"])
    identity.update({"symbol": "NOVELUSDT", "config_hash": "7" * 64})
    expensive["identity"] = identity
    resource = dict(expensive["resource"])
    resource["estimated_rows_scanned"] = 70_000
    resource["predicted_canonical_bytes"] = 7_000_000
    _rehash_resource(resource)
    expensive["resource"] = resource
    expensive["portfolio"] = {
        "sector_exposure_share": "0.9",
        "strategy_active_target_share": "0.9",
        "beta_to_portfolio": "0.9",
    }

    result = build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[{"symbol": "NOVELUSDT", "novelty": 999}],
        candidate_evidence_board=[expensive, lean],
        prior_decisions=[],
        policy=_policy(),
    )

    selected_family = result["selected_candidate"]["family_key"]
    by_symbol = {
        item["identity"]["symbol"]: item for item in result["evaluated_candidates"]
    }
    assert Decimal(by_symbol["BTCUSDT"]["metrics"]["evi"]) > Decimal(
        by_symbol["NOVELUSDT"]["metrics"]["evi"]
    )
    assert selected_family == by_symbol["BTCUSDT"]["family_key"]


def test_evi_uses_frozen_decimal_formula_and_q18_output() -> None:
    result = build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[_candidate()],
        prior_decisions=[],
        policy=_policy(),
    )

    with localcontext() as context:
        context.prec = 50
        context.rounding = ROUND_HALF_EVEN
        information_gain = Decimal("0.5") * (Decimal(66) / Decimal(31)).ln()
        ambiguity = (Decimal("-0.5") * (Decimal("0.05") / Decimal("0.02")) ** 2).exp()
        quality = Decimal("0.9")
        resource = (Decimal("0.07") + Decimal("0.007")) / Decimal(2)
        portfolio = Decimal("0.3")
        expected = (
            information_gain
            * Decimal(1)
            * ambiguity
            * quality
            / ((Decimal(1) + resource) * (Decimal(1) + portfolio))
        ).quantize(Decimal("0.000000000000000001"))

    metrics = result["evaluated_candidates"][0]["metrics"]
    assert metrics["expected_new_entries"] == "35.000000000000000000"
    assert metrics["resource"] == "0.038500000000000000"
    assert metrics["portfolio_redundancy"] == "0.300000000000000000"
    assert metrics["evi"] == format(expected, "f")


def test_missing_policy_or_resource_never_becomes_a_target() -> None:
    missing_resource = _candidate()
    missing_resource.pop("resource")
    missing_row_bytes = _candidate()
    resource = dict(missing_row_bytes["resource"])
    resource.pop("predicted_canonical_bytes")
    missing_row_bytes["resource"] = resource

    for candidate, policy in (
        (_candidate(), {}),
        (missing_resource, _policy()),
        (missing_row_bytes, _policy()),
    ):
        result = build_candidate_learning_decision(
            source_head=SOURCE_HEAD,
            scanner_research_seeds=[],
            candidate_evidence_board=[candidate],
            prior_decisions=[],
            policy=policy,
        )
        assert result["selected_candidate"] is None
        assert result["selected_collection_target"] is None
        assert result["evaluated_candidates"][0]["metrics"] is None
        assert result["state"] == "INELIGIBLE"


def test_missing_portfolio_is_rejected_by_atomic_v2_input_even_for_passive_gap() -> None:
    blocked = _candidate()
    blocked.pop("portfolio")

    passive = _candidate()
    passive.pop("portfolio")
    evidence = dict(passive["evidence"])
    evidence["next_gap"] = {
        "kind": "LOCAL_PASSIVE",
        "code": "NEED_DISTINCT_ENTRY",
    }
    _set_n_eff(evidence, 29)
    passive["evidence"] = evidence

    blocked_result = build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[blocked],
        prior_decisions=[],
        policy=_policy(),
    )
    passive_result = build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[passive],
        prior_decisions=[],
        policy=_policy(unknown_portfolio_penalty="0.75"),
    )

    assert blocked_result["state"] == "INELIGIBLE"
    assert blocked_result["selected_candidate"] is None
    assert passive_result["state"] == "INELIGIBLE"
    assessment = passive_result["evaluated_candidates"][0]
    assert assessment["portfolio_assumption"] is None
    assert assessment["metrics"] is None
    assert assessment["blocker_codes"] == ["ARBITER_INPUT_FIELDS_INVALID"]


def test_proof_prefix_cannot_skip_and_external_gap_never_auto_collects() -> None:
    external = _candidate()
    evidence = dict(external["evidence"])
    evidence.update(
        {
            "proof_stage": 2,
            "completed_proof_stages": [0, 1, 2],
            "next_gap": {"kind": "EXTERNAL_OPERATOR", "code": "OOS_SEAL_REQUIRED"},
        }
    )
    external["evidence"] = evidence

    skipped = _candidate()
    evidence = dict(skipped["evidence"])
    evidence.update(
        {
            "proof_stage": 2,
            "completed_proof_stages": [0, 2],
            "next_gap": {"kind": "LOCAL_PASSIVE", "code": "INVALID_SKIP"},
        }
    )
    skipped["evidence"] = evidence

    external_result = build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[external],
        prior_decisions=[],
        policy=_policy(),
    )
    skipped_result = build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[skipped],
        prior_decisions=[],
        policy=_policy(),
    )

    assert external_result["decision"] == "NO_QUALIFIED_CANDIDATE_EXTERNAL"
    assert external_result["state"] == "EXTERNAL_GAP"
    assert external_result["selected_candidate"] is None
    assert external_result["selected_collection_target"] is None
    assert skipped_result["state"] == "INELIGIBLE"
    assert skipped_result["evaluated_candidates"][0]["blocker_codes"] == [
        "PROOF_PREFIX_INVALID"
    ]


def test_cooldown_waits_at_1799_and_consecutive_guard_holds_at_1800() -> None:
    policy = _policy()
    baseline = build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[_candidate()],
        prior_decisions=[],
        policy=policy,
    )["selected_candidate"]

    def prior(age_s: int) -> list[dict[str, object]]:
        return [
            {
                "family_key": baseline["family_key"],
                "decision_ts_s": policy["decision_ts_s"] - age_s,
                "material_fingerprint": baseline["material_fingerprint"],
            }
        ]

    waiting = build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[_candidate()],
        prior_decisions=prior(1_799),
        policy=policy,
    )
    opened = build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[_candidate()],
        prior_decisions=prior(1_800),
        policy=policy,
    )

    assert waiting["decision"] == "NO_QUALIFIED_CANDIDATE_WAIT"
    assert waiting["state"] == "WAIT_COOLDOWN"
    assert waiting["selected_candidate"] is None
    assert opened["state"] == "WAIT_COOLDOWN"


def test_raw_count_and_threshold_deltas_are_material_for_cooldown() -> None:
    policy = _policy()
    baseline = build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[_candidate()],
        prior_decisions=[],
        policy=policy,
    )["selected_candidate"]
    raw_delta = _candidate()
    evidence = dict(raw_delta["evidence"])
    evidence["raw_attempt_count"] = 9_999
    raw_delta["evidence"] = evidence
    same_prior = [
        {
            "family_key": baseline["family_key"],
            "decision_ts_s": policy["decision_ts_s"] - 1,
            "material_fingerprint": baseline["material_fingerprint"],
        }
    ]

    raw_delta_opened = build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[raw_delta],
        prior_decisions=same_prior,
        policy=policy,
    )

    below = _candidate()
    evidence = dict(below["evidence"])
    evidence["next_gap"] = {
        "kind": "LOCAL_PASSIVE",
        "code": "NEED_DISTINCT_ENTRY",
    }
    _set_n_eff(evidence, 29)
    below["evidence"] = evidence
    below_target = build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[below],
        prior_decisions=[],
        policy=policy,
    )["selected_collection_target"]
    threshold_prior = [
        {
            "family_key": below_target["family_key"],
            "decision_ts_s": policy["decision_ts_s"] - 1,
            "material_fingerprint": below_target["material_fingerprint"],
        }
    ]
    opened = build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[_candidate()],
        prior_decisions=threshold_prior,
        policy=policy,
    )

    assert raw_delta_opened["state"] == "DECISION_READY"
    assert opened["state"] == "DECISION_READY"


@pytest.mark.parametrize(
    "mutation",
    (
        "mean_net_e",
        "cluster_scale",
        "quality_share",
        "regime_counts",
        "resource_bucket",
        "portfolio_beta",
        "data_context",
        "scanner_context",
    ),
)
def test_normalized_decision_input_deltas_are_material_for_cooldown(
    mutation: str,
) -> None:
    policy = _policy()
    baseline = build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[_candidate()],
        prior_decisions=[],
        policy=policy,
    )["selected_candidate"]
    candidate = _candidate()
    scanner_seeds: list[dict[str, object]] = []
    if mutation == "mean_net_e":
        candidate["evidence"]["mean_net_e"] = 0.10
    elif mutation == "cluster_scale":
        candidate["evidence"]["day_cluster_variance"] = 0.0009
        candidate["evidence"]["cluster_se"] = 0.03
    elif mutation == "quality_share":
        candidate["quality"]["top_day_share"] = 0.45
    elif mutation == "regime_counts":
        counts = candidate["evidence"]["regime_entry_counts"]
        counts[REGIME_BUCKETS[0]] -= 1
        counts[REGIME_BUCKETS[-1]] += 1
    elif mutation == "resource_bucket":
        candidate["resource"]["daily_buckets"][0]["distinct_entries"] = 6
        _rehash_resource(candidate["resource"])
    elif mutation == "portfolio_beta":
        candidate["portfolio"]["beta_to_portfolio"] = "0.4"
    elif mutation == "data_context":
        candidate["context_hashes"]["data"] = "9" * 64
    else:
        scanner_seeds = [
            {"symbol": "BTCUSDT", "novelty": "1", "recurrence": "2"}
        ]

    result = build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=scanner_seeds,
        candidate_evidence_board=[candidate],
        prior_decisions=[
            {
                "family_key": baseline["family_key"],
                "decision_ts_s": policy["decision_ts_s"] - 1,
                "material_fingerprint": baseline["material_fingerprint"],
            }
        ],
        policy=policy,
    )
    assessment = result["evaluated_candidates"][0]

    assert assessment["material_fingerprint"] != baseline["material_fingerprint"]
    assert assessment["state"] == "DECISION_READY"
    assert result["state"] == "DECISION_READY"


def test_candidate_and_scanner_permutations_are_byte_deterministic() -> None:
    btc = _candidate()
    eth = _candidate()
    identity = dict(eth["identity"])
    identity.update({"symbol": "ETHUSDT", "config_hash": "8" * 64})
    eth["identity"] = identity
    seeds = [
        {"symbol": "BTCUSDT", "novelty": "1", "recurrence": "2"},
        {"symbol": "BTCUSDT", "novelty": "1", "recurrence": "3"},
        {"symbol": "ETHUSDT", "novelty": "1", "recurrence": "1"},
    ]

    forward = build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=seeds,
        candidate_evidence_board=[btc, eth],
        prior_decisions=[],
        policy=_policy(),
    )
    reversed_inputs = build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=list(reversed(seeds)),
        candidate_evidence_board=[eth, btc],
        prior_decisions=[],
        policy=_policy(),
    )

    assert forward == reversed_inputs
    assert forward["decision_hash"] == reversed_inputs["decision_hash"]


def test_zero_cluster_se_is_a_degenerate_variance_hard_gate() -> None:
    candidate = _candidate()
    quality = dict(candidate["quality"])
    quality["cluster_variance_clean"] = False
    candidate["quality"] = quality
    evidence = dict(candidate["evidence"])
    evidence.update(
        {
            "day_cluster_variance": 0.0,
            "cluster_se": None,
            "next_gap": {"kind": "LOCAL_ENGINEERING", "code": "REPAIR_VARIANCE"},
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

    assert result["state"] == "REPAIR_DATA_QUALITY"
    assert "CLUSTER_VARIANCE_DEGENERATE" in result["evaluated_candidates"][0][
        "blocker_codes"
    ]


@pytest.mark.parametrize(
    "mutation",
    ("day_cluster_variance", "cluster_count", "raw_attempt_count"),
)
def test_valid_statistical_material_change_alters_fingerprint_and_decision(
    mutation: str,
) -> None:
    baseline = build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[_candidate()],
        prior_decisions=[],
        policy=_policy(),
    )
    candidate = _candidate()
    evidence = dict(candidate["evidence"])
    if mutation == "day_cluster_variance":
        evidence["day_cluster_variance"] = 0.0009
        evidence["cluster_se"] = 0.03
    elif mutation == "cluster_count":
        evidence["cluster_count"] = 6
        evidence["utc_day_count"] = 6
    else:
        evidence["raw_attempt_count"] = 31
    candidate["evidence"] = evidence

    changed = build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[candidate],
        prior_decisions=[],
        policy=_policy(),
    )

    assert changed["evaluated_candidates"][0]["material_fingerprint"] != (
        baseline["evaluated_candidates"][0]["material_fingerprint"]
    )
    assert changed["decision_hash"] != baseline["decision_hash"]


def test_legacy_optimistic_cost_is_a_material_quality_gate() -> None:
    baseline = build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[_candidate()],
        prior_decisions=[],
        policy=_policy(),
    )
    candidate = _candidate()
    quality = dict(candidate["quality"])
    quality["legacy_optimistic_cost_present"] = True
    candidate["quality"] = quality
    changed = build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[candidate],
        prior_decisions=[],
        policy=_policy(),
    )

    assessment = changed["evaluated_candidates"][0]
    assert "LEGACY_OPTIMISTIC_COST_UNBACKFILLED" in assessment["blocker_codes"]
    assert assessment["material_fingerprint"] != baseline["evaluated_candidates"][0][
        "material_fingerprint"
    ]
    assert changed["decision_hash"] != baseline["decision_hash"]


def test_hard_gate_flip_is_a_material_cooldown_delta() -> None:
    policy = _policy()
    concentrated = _candidate()
    quality = dict(concentrated["quality"])
    quality["top_day_share"] = math.nextafter(0.5, 1.0)
    concentrated["quality"] = quality
    evidence = dict(concentrated["evidence"])
    evidence["next_gap"] = {"kind": "LOCAL_PASSIVE", "code": "DIVERSIFY_DAYS"}
    concentrated["evidence"] = evidence
    old_target = build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[concentrated],
        prior_decisions=[],
        policy=policy,
    )["selected_collection_target"]
    prior = [
        {
            "family_key": old_target["family_key"],
            "decision_ts_s": policy["decision_ts_s"] - 1,
            "material_fingerprint": old_target["material_fingerprint"],
        }
    ]

    result = build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[_candidate()],
        prior_decisions=prior,
        policy=policy,
    )

    assert result["state"] == "DECISION_READY"


def test_atomic_v2_candidate_contract_rejects_v1_and_hash_tampering() -> None:
    legacy = _candidate()
    legacy["schema_version"] = "alr_candidate_arbiter_input_v1"
    legacy.pop("arbiter_input_hash")
    legacy["arbiter_input_hash"] = _canonical_hash(legacy)
    legacy_result = _raw_build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[legacy],
        prior_decisions=[],
        policy=_policy(),
    )

    tampered = _candidate()
    tampered["evidence"]["n_eff"] = 31
    tampered_result = _raw_build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[tampered],
        prior_decisions=[],
        policy=_policy(),
    )

    assert legacy_result["evaluated_candidates"][0]["blocker_codes"] == [
        "ARBITER_INPUT_SCHEMA_INVALID"
    ]
    assert tampered_result["evaluated_candidates"][0]["blocker_codes"] == [
        "ARBITER_INPUT_HASH_MISMATCH"
    ]


def test_v1_prior_is_ignored_but_v2_prior_enforces_cooldown() -> None:
    policy = _policy()
    candidate = _candidate()
    baseline = _raw_build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[candidate],
        prior_decisions=[],
        policy=policy,
    )["selected_candidate"]
    prior_body = {
        "family_key": baseline["family_key"],
        "decision_ts_s": policy["decision_ts_s"] - 1,
        "material_fingerprint": baseline["material_fingerprint"],
    }

    ignored = _raw_build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[candidate],
        prior_decisions=[
            {
                **prior_body,
                "decision_schema_version": "alr_candidate_learning_decision_v1",
            }
        ],
        policy=policy,
    )
    enforced = _raw_build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[candidate],
        prior_decisions=[
            {
                **prior_body,
                "decision_schema_version": "alr_candidate_learning_decision_v2",
            }
        ],
        policy=policy,
    )

    assert ignored["state"] == "DECISION_READY"
    assert enforced["state"] == "WAIT_COOLDOWN"


def test_v2_output_and_family_hash_use_frozen_raw_nine_field_identity() -> None:
    candidate = _candidate()
    result = build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[candidate],
        prior_decisions=[],
        policy=_policy(),
    )
    identity = candidate["identity"]
    expected_family = _canonical_hash(
        {
            "schema_version": "candidate_learning_family_v2",
            "identity": {
                "strategy_name": identity["strategy_name"],
                "strategy_version": identity["strategy_version"],
                "strategy_config_hash": identity["config_hash"],
                "symbol": identity["symbol"],
                "side": identity["side"],
                "horizon_minutes": identity["horizon_minutes"],
                "venue": identity["venue"],
                "product": identity["product"],
                "evidence_engine_mode": identity["evidence_engine_mode"],
            },
        }
    )

    assert result["schema_version"] == "alr_candidate_learning_arbiter_v2"
    assert result["algorithm_version"] == "candidate_learning_arbiter_v2"
    assert result["tie_break_version"] == "candidate_learning_tie_break_v1"
    assert result["evaluated_candidates"][0]["family_key"] == expected_family


@pytest.mark.parametrize(
    ("mutation", "expected"),
    (
        ("top_extra", "ARBITER_INPUT_FIELDS_INVALID"),
        ("identity_extra", "IDENTITY_FIELDS_INVALID"),
        ("identity_whitespace", "IDENTITY_INCOMPLETE"),
        ("mode_case", "EVIDENCE_ENGINE_MODE_INVALID"),
    ),
)
def test_v2_input_rejects_hash_bound_extras_and_identity_coercion(
    mutation: str,
    expected: str,
) -> None:
    candidate = _candidate()
    if mutation == "top_extra":
        candidate["ignored_extension"] = "must-not-be-silent"
    else:
        identity = dict(candidate["identity"])
        if mutation == "identity_extra":
            identity["ignored_extension"] = "must-not-be-silent"
        elif mutation == "identity_whitespace":
            identity["strategy_name"] = " ma_crossover"
        else:
            identity["evidence_engine_mode"] = "DEMO"
        candidate["identity"] = identity

    result = build_candidate_learning_decision(
        source_head=SOURCE_HEAD,
        scanner_research_seeds=[],
        candidate_evidence_board=[candidate],
        prior_decisions=[],
        policy=_policy(),
    )

    assert result["evaluated_candidates"][0]["blocker_codes"] == [expected]
