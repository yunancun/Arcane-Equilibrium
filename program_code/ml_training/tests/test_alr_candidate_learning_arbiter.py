"""WP2-A candidate-aware learning arbiter 的公開行為測試。"""

import hashlib
import json
from decimal import Decimal, ROUND_HALF_EVEN, localcontext

import pytest

from program_code.ml_training.alr_candidate_learning_arbiter import (
    build_candidate_learning_decision,
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


def _policy(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "decision_ts_s": 1_782_086_400,
        "as_of_utc_date": "2026-06-22",
        "algorithm_version": "candidate_learning_arbiter_v1",
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
    candidate: dict[str, object] = {
        "identity": {
            "strategy_name": "ma_crossover",
            "strategy_version": "v2.1.0",
            "config_hash": "1" * 64,
            "symbol": "BTCUSDT",
            "side": "Buy",
            "horizon_minutes": 60,
            "target_regime": {
                "label": "bull_high_vol",
                "utc_date": "2026-06-21",
                "hash": "2" * 64,
                "point_in_time": "D-1",
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
        "quality": {
            "hash_ok": True,
            "integrity_ok": True,
            "freshness_ok": True,
            "censored_share": "0.10",
            "cost_recomputable_share": "1",
            "unknown_regime_share": "0",
            "replica_inconsistency_count": 0,
            "cluster_variance_clean": True,
            "hidden_oos_consumed": False,
            "top_day_share": "0.40",
        },
        "evidence": {
            "n_eff": 30,
            "utc_day_count": 5,
            "mean_net_e": "0.05",
            "cluster_se": "0.02",
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
                    "estimated_rows_scanned": 100,
                    "predicted_canonical_bytes": 1_000,
                }
                for day in range(15, 22)
            ]
        },
        "portfolio": {
            "sector_exposure_share": "0.10",
            "strategy_active_target_share": "0.20",
            "beta_to_portfolio": "0.30",
        },
    }
    _rehash_resource(candidate["resource"])
    candidate.update(overrides)
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


def test_utc_day_gate_collects_at_4_and_opens_at_5() -> None:
    low = _candidate()
    evidence = dict(low["evidence"])
    evidence.update(
        {
            "utc_day_count": 4,
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
    boundary_quality["top_day_share"] = "0.500000000000000000"
    boundary["quality"] = boundary_quality

    above = _candidate()
    above_quality = dict(above["quality"])
    above_quality["top_day_share"] = "0.500000000000000001"
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
    quality["censored_share"] = "0.300000000000000000"
    boundary["quality"] = quality

    above = _candidate()
    quality = dict(above["quality"])
    quality["censored_share"] = "0.300000000000000001"
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
        ("cost_recomputable_share", "0.999999999999999999", "COST_NOT_RECOMPUTABLE"),
        ("replica_inconsistency_count", 1, "REPLICA_INCONSISTENT"),
        ("cluster_variance_clean", False, "CLUSTER_VARIANCE_DEGENERATE"),
        ("hidden_oos_consumed", True, "HIDDEN_OOS_CONSUMED"),
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
    evidence["mean_net_e"] = "-0.05"
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
        "sector_exposure_share": "0.90",
        "strategy_active_target_share": "0.90",
        "beta_to_portfolio": "0.90",
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


def test_missing_portfolio_blocks_decision_but_allows_labeled_passive_collection() -> None:
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
    assert passive_result["state"] == "COLLECT_DISTINCT_ENTRIES"
    assessment = passive_result["evaluated_candidates"][0]
    assert assessment["portfolio_assumption"] == "UNKNOWN"
    assert assessment["metrics"]["portfolio_redundancy"] == "0.750000000000000000"


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


def test_raw_count_delta_does_not_bypass_cooldown_but_threshold_delta_does() -> None:
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

    waiting = build_candidate_learning_decision(
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

    assert waiting["state"] == "WAIT_COOLDOWN"
    assert opened["state"] == "DECISION_READY"


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
    evidence = dict(candidate["evidence"])
    evidence.update(
        {
            "cluster_se": "0",
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


def test_hard_gate_flip_is_a_material_cooldown_delta() -> None:
    policy = _policy()
    concentrated = _candidate()
    quality = dict(concentrated["quality"])
    quality["top_day_share"] = "0.500000000000000001"
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
