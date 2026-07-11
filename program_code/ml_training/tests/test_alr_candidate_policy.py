"""ALR candidate arbiter canonical policy 與 provision preflight 行為測試。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from ml_training.alr_candidate_policy import (
    CandidatePolicyError,
    check_provisioned_candidate_policy,
    load_candidate_policy_template,
    main as policy_main,
    provision_candidate_policy,
    render_candidate_policy_configuration,
    validate_candidate_policy_configuration,
)


ROOT = Path(__file__).resolve().parents[3]
TEMPLATE = ROOT / "helper_scripts/deploy/openclaw-alr-candidate-policy.template.json"
EXPECTED_V2_POLICY_HASH = (
    "27fe66f8fffb58c70395f04897e8b894ddec10ec4889f57ff099b88701d95ef3"
)


def _budgets() -> dict[str, int]:
    return {
        "row_budget": 10_000,
        "byte_budget": 1_000_000,
        "collection_window_days": 7,
        "max_new_entries_per_window": 70,
    }


def _policy_hash(policy: dict[str, object]) -> str:
    body = {key: value for key, value in policy.items() if key != "policy_config_hash"}
    encoded = json.dumps(
        body,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def test_checked_in_template_has_no_production_budget_defaults() -> None:
    template = load_candidate_policy_template(TEMPLATE)

    assert template["schema_version"] == "alr_candidate_arbiter_policy_template_v2"
    assert template["policy_config_hash"] is None
    assert {template[key] for key in _budgets()} == {None}
    with pytest.raises(CandidatePolicyError, match="policy_fields_invalid"):
        validate_candidate_policy_configuration(template)


def test_explicit_budgets_render_canonical_semantically_valid_policy() -> None:
    policy = render_candidate_policy_configuration(
        load_candidate_policy_template(TEMPLATE),
        **_budgets(),
    )

    assert validate_candidate_policy_configuration(policy) == policy
    assert policy == {
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
        "policy_config_hash": EXPECTED_V2_POLICY_HASH,
    }


def test_v1_policy_is_explicitly_rejected_after_atomic_v2_cutover() -> None:
    policy = render_candidate_policy_configuration(
        load_candidate_policy_template(TEMPLATE),
        **_budgets(),
    )
    policy["algorithm_version"] = "candidate_learning_arbiter_v1"
    policy["policy_config_hash"] = _policy_hash(policy)

    with pytest.raises(CandidatePolicyError, match="policy_version_invalid"):
        validate_candidate_policy_configuration(policy)


def test_semantic_validator_rejects_rehashed_frozen_threshold_drift() -> None:
    policy = render_candidate_policy_configuration(
        load_candidate_policy_template(TEMPLATE),
        **_budgets(),
    )
    policy["thresholds"]["e1_n_eff_min"] = 29
    policy["policy_config_hash"] = "0" * 64

    with pytest.raises(CandidatePolicyError, match="policy_thresholds_invalid"):
        validate_candidate_policy_configuration(policy)


@pytest.mark.parametrize("penalty", ("1.0", "1e0", 1))
def test_semantic_validator_rejects_rehashed_noncanonical_penalty(
    penalty: object,
) -> None:
    policy = render_candidate_policy_configuration(
        load_candidate_policy_template(TEMPLATE),
        **_budgets(),
    )
    policy["unknown_portfolio_penalty"] = penalty
    policy["policy_config_hash"] = _policy_hash(policy)

    with pytest.raises(CandidatePolicyError, match="policy_unknown_penalty_invalid"):
        validate_candidate_policy_configuration(policy)


def test_dry_run_reports_missing_destination_fail_closed_without_writing(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "private" / "candidate-policy.json"

    result = provision_candidate_policy(
        TEMPLATE,
        destination,
        apply=False,
        **_budgets(),
    )

    assert result["status"] == "DRY_RUN_PROVISION_REQUIRED"
    assert result["schema_version"] == "alr_candidate_policy_provision_v2"
    assert result["service_preflight_ready"] is False
    assert result["destination_write_performed"] is False
    assert result["policy_file_mutation_performed"] is False
    assert result["runtime_process_mutation_performed"] is False
    assert result["service_unit_mutation_performed"] is False
    assert not destination.exists()
    with pytest.raises(CandidatePolicyError, match="provisioned_policy_missing"):
        check_provisioned_candidate_policy(destination)


def test_explicit_apply_atomically_provisions_private_canonical_policy(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "private" / "candidate-policy.json"

    result = provision_candidate_policy(
        TEMPLATE,
        destination,
        apply=True,
        **_budgets(),
    )

    assert result["status"] == "PROVISIONED"
    assert result["schema_version"] == "alr_candidate_policy_provision_v2"
    assert result["service_preflight_ready"] is True
    assert result["destination_write_performed"] is True
    assert result["policy_file_mutation_performed"] is True
    assert result["runtime_process_mutation_performed"] is False
    assert result["service_unit_mutation_performed"] is False
    assert destination.stat().st_mode & 0o777 == 0o600
    assert destination.parent.stat().st_mode & 0o777 == 0o700
    assert check_provisioned_candidate_policy(destination) == render_candidate_policy_configuration(
        load_candidate_policy_template(TEMPLATE),
        **_budgets(),
    )


def test_cli_dry_run_missing_destination_is_nonzero_and_machine_readable(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    destination = tmp_path / "candidate-policy.json"

    rc = policy_main(
        [
            "--template",
            str(TEMPLATE),
            "--destination",
            str(destination),
            "--row-budget",
            "10000",
            "--byte-budget",
            "1000000",
            "--collection-window-days",
            "7",
            "--max-new-entries-per-window",
            "70",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert rc == 3
    assert payload["status"] == "DRY_RUN_PROVISION_REQUIRED"
    assert payload["schema_version"] == "alr_candidate_policy_provision_v2"
    assert payload["service_preflight_ready"] is False
    assert payload["rendered_policy"]["algorithm_version"] == (
        "candidate_learning_arbiter_v2"
    )
    assert payload["rendered_policy"]["policy_config_hash"] == EXPECTED_V2_POLICY_HASH
    assert not destination.exists()


def test_cli_missing_any_explicit_budget_fails_closed(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = policy_main(
        [
            "--template",
            str(TEMPLATE),
            "--destination",
            str(tmp_path / "candidate-policy.json"),
            "--row-budget",
            "10000",
            "--byte-budget",
            "1000000",
            "--collection-window-days",
            "7",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert payload["status"] == "POLICY_PREFLIGHT_FAILED"
    assert payload["reason"] == "provision_budgets_required"


def test_provisioned_policy_rejects_broad_or_symlink_parent(tmp_path: Path) -> None:
    destination = tmp_path / "private" / "candidate-policy.json"
    provision_candidate_policy(TEMPLATE, destination, apply=True, **_budgets())

    destination.parent.chmod(0o777)
    with pytest.raises(CandidatePolicyError, match="policy_parent_not_private"):
        check_provisioned_candidate_policy(destination)

    destination.parent.chmod(0o700)
    linked_parent = tmp_path / "linked-private"
    linked_parent.symlink_to(destination.parent, target_is_directory=True)
    with pytest.raises(CandidatePolicyError, match="policy_parent_not_private"):
        check_provisioned_candidate_policy(linked_parent / destination.name)
