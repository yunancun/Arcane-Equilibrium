from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SRV_ROOT = Path(__file__).resolve().parents[3]
if str(SRV_ROOT) not in sys.path:
    sys.path.insert(0, str(SRV_ROOT))

from helper_scripts.research.aeg_report_audit import audit  # noqa: E402


def test_complete_aeg_artifact_is_advisory_ready(tmp_path: Path) -> None:
    artifact = {
        "candidate_id": "oi_delta",
        "strategy_family": "oi_delta",
        "parameter_cell_id": "lb24_h24",
        "n_independent": 64,
        "sample_unit": "non_overlapping_holding_window",
        "oos_start_date": "2026-04-02",
        "psr_0": 0.96,
        "dsr": 0.82,
        "pbo": {"value": 0.2, "method": "time_block_cscv"},
        "regime": "chop",
        "symbol_count": 12,
        "cost_bps": 11.0,
        "fee_bps": 4.0,
        "slippage_bps": 7.0,
        "recent_90d_net_bps": 1.2,
        "advisory_only": True,
        "order_authority_granted": False,
        "promotion_proof": False,
    }
    path = tmp_path / "artifact.json"
    path.write_text(json.dumps(artifact), encoding="utf-8")

    result = audit.audit_path(path, profile="aeg_artifact")

    assert result["status"] == "advisory_pass"
    assert result["finding_count"] == 0
    assert result["authority"]["order_authority_granted"] is False
    assert result["promotion_evidence"] is False


def test_missing_pbo_and_costs_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / "artifact.json"
    path.write_text(json.dumps({
        "candidate_id": "trend",
        "strategy_family": "multiday",
        "n_independent": 40,
        "sample_unit": "days",
        "oos_start_date": "2026-03-01",
        "psr_0": 0.91,
        "dsr": 0.7,
        "advisory_only": True,
        "order_authority_granted": False,
    }), encoding="utf-8")

    result = audit.audit_path(path, profile="aeg_artifact")
    finding_ids = {row["finding_id"] for row in result["findings"]}

    assert result["status"] == "insufficient_evidence"
    assert "missing_aeg_artifact_pbo" in finding_ids
    assert "missing_aeg_artifact_costs" in finding_ids


def test_numeric_markdown_claim_without_source_is_flagged(tmp_path: Path) -> None:
    path = tmp_path / "report.md"
    path.write_text(
        "# Report\n\nThis candidate improved by 12.4 bps across 42 rows.\n\n"
        "Verification: `python -m pytest helper_scripts/research/tests` passed 3 tests.\n",
        encoding="utf-8",
    )

    result = audit.audit_path(path, profile="pm_report")
    numeric = [row for row in result["findings"] if row["finding_id"] == "numeric_claim_without_source_lineage"]

    assert numeric
    assert numeric[0]["line"] == 3
    assert result["authority"]["advisory_only"] is True


def test_m4_missing_bonferroni_and_shift_are_high_findings(tmp_path: Path) -> None:
    path = tmp_path / "m4.md"
    path.write_text(
        "# Hypothesis draft\n\n"
        "hypothesis: funding flip forward return pattern\n"
        "n_observations: 31 rows artifact sha abc123\n"
        "effect_size: cohens_d 0.4\n"
        "status: exploratory not live no order\n",
        encoding="utf-8",
    )

    result = audit.audit_path(path, profile="m4_hypothesis")
    finding_ids = {row["finding_id"] for row in result["findings"]}

    assert result["status"] == "insufficient_evidence"
    assert "missing_m4_hypothesis_bonferroni" in finding_ids
    assert "missing_m4_hypothesis_leak_free_shift" in finding_ids
    assert result["promotion_evidence"] is False


def test_batch_summary_preserves_no_authority(tmp_path: Path) -> None:
    path = tmp_path / "report.md"
    path.write_text(
        "status: ready\nartifact sha abc123\nno order no bybit no pg advisory\nverification pytest passed\nnext operator handoff\n",
        encoding="utf-8",
    )

    batch = audit.audit_many([path], profile="pm_report")

    assert batch["input_count"] == 1
    assert batch["authority"]["runtime_mutation_authority"] is False
    assert batch["promotion_evidence"] is False
    assert batch["status"] == "advisory_pass"


def test_forbidden_trade_vocabulary_is_audit_gap(tmp_path: Path) -> None:
    path = tmp_path / "report.md"
    path.write_text(
        "status ready\nartifact sha abc123\nverification pytest passed\nnext operator handoff\n"
        "This is a recommendation BUY signal.\n",
        encoding="utf-8",
    )

    result = audit.audit_path(path, profile="pm_report")
    finding_ids = {row["finding_id"] for row in result["findings"]}

    assert result["status"] == "audit_gap"
    assert "forbidden_authority_vocabulary" in finding_ids


def test_json_nan_and_fraction_unit_confusion_are_audit_gaps(tmp_path: Path) -> None:
    path = tmp_path / "artifact.json"
    path.write_text(json.dumps({
        "candidate_id": "x",
        "strategy_family": "s",
        "parameter_cell_id": "p",
        "n_independent": 40,
        "sample_unit": "non_overlapping",
        "oos_start_date": "2026-03-01",
        "psr_0": float("nan"),
        "dsr": 0.8,
        "pbo": 0.2,
        "regime": "chop",
        "symbol_count": 10,
        "cost_bps": 1.0,
        "recent_90d_net_bps": 1.0,
        "per_trade_risk_pct_fraction": 10.0,
        "advisory_only": True,
        "order_authority_granted": False,
        "promotion_proof": False,
    }), encoding="utf-8")

    result = audit.audit_path(path, profile="aeg_artifact")
    finding_ids = {row["finding_id"] for row in result["findings"]}

    assert result["status"] == "audit_gap"
    assert "numeric_value_not_finite" in finding_ids
    assert "percentage_fraction_unit_confusion" in finding_ids


def test_json_string_unit_confusion_is_audit_gap(tmp_path: Path) -> None:
    path = tmp_path / "artifact.json"
    payload = {
        "candidate_id": "x",
        "strategy_family": "s",
        "parameter_cell_id": "p",
        "n_independent": 40,
        "sample_unit": "non_overlapping",
        "oos_start_date": "2026-03-01",
        "psr_0": 0.9,
        "dsr": 0.8,
        "pbo": 0.2,
        "regime": "chop",
        "symbol_count": 10,
        "cost_bps": 1.0,
        "recent_90d_net_bps": 1.0,
        "risk_cap_usdt": "10%",
        "position_size_pct": "25 USDT",
        "advisory_only": True,
        "order_authority_granted": False,
        "promotion_proof": False,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")

    result = audit.audit_path(path, profile="aeg_artifact")
    finding_ids = {row["finding_id"] for row in result["findings"]}

    assert result["status"] == "audit_gap"
    assert "usdt_percent_unit_confusion" in finding_ids
    assert "percent_usdt_unit_confusion" in finding_ids


def test_malformed_json_artifact_is_audit_gap(tmp_path: Path) -> None:
    path = tmp_path / "artifact.json"
    path.write_text(
        '{"candidate_id":"x","strategy_family":"s","parameter_cell_id":"p","n_independent":40,'
        '"sample_unit":"non_overlapping","oos_start_date":"2026-03-01","psr_0":0.9,'
        '"dsr":0.8,"pbo":0.2,"regime":"chop","symbol_count":10,"cost_bps":1.0,'
        '"recent_90d_net_bps":1.0,"advisory_only":true,"order_authority_granted":false,',
        encoding="utf-8",
    )

    result = audit.audit_path(path, profile="aeg_artifact")
    finding_ids = {row["finding_id"] for row in result["findings"]}

    assert result["status"] == "audit_gap"
    assert result["json_parse_ok"] is False
    assert "malformed_json_artifact" in finding_ids


@pytest.mark.parametrize(
    "flag",
    [
        "order_authority_granted",
        "order_capable_action_allowed",
        "promotion_authority",
        "promotion_proof",
        "proof_authority",
        "risk_config_authority",
        "runtime_mutation_authority",
        "bybit_access",
        "db_access",
    ],
)
def test_true_authority_flags_are_audit_gaps(tmp_path: Path, flag: str) -> None:
    path = tmp_path / "artifact.json"
    payload = {
        "candidate_id": "x",
        "strategy_family": "s",
        "parameter_cell_id": "p",
        "n_independent": 40,
        "sample_unit": "non_overlapping",
        "oos_start_date": "2026-03-01",
        "psr_0": 0.9,
        "dsr": 0.8,
        "pbo": 0.2,
        "regime": "chop",
        "symbol_count": 10,
        "cost_bps": 1.0,
        "recent_90d_net_bps": 1.0,
        "advisory_only": True,
        "order_authority_granted": False,
        "promotion_proof": False,
    }
    payload[flag] = True
    path.write_text(json.dumps(payload), encoding="utf-8")

    result = audit.audit_path(path, profile="aeg_artifact")
    finding_ids = {row["finding_id"] for row in result["findings"]}

    assert result["status"] == "audit_gap"
    assert "authority_contamination" in finding_ids


def test_artifact_sha_mismatch_is_audit_gap(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("real source\n", encoding="utf-8")
    path = tmp_path / "artifact.json"
    path.write_text(json.dumps({
        "candidate_id": "x",
        "strategy_family": "s",
        "parameter_cell_id": "p",
        "n_independent": 40,
        "sample_unit": "non_overlapping",
        "oos_start_date": "2026-03-01",
        "psr_0": 0.9,
        "dsr": 0.8,
        "pbo": 0.2,
        "regime": "chop",
        "symbol_count": 10,
        "cost_bps": 1.0,
        "recent_90d_net_bps": 1.0,
        "source_path": "source.txt",
        "source_sha256": "0" * 64,
        "advisory_only": True,
        "order_authority_granted": False,
        "promotion_proof": False,
    }), encoding="utf-8")

    result = audit.audit_path(path, profile="aeg_artifact")
    finding_ids = {row["finding_id"] for row in result["findings"]}

    assert result["status"] == "audit_gap"
    assert "artifact_sha_mismatch" in finding_ids


def test_missing_referenced_artifact_is_audit_gap(tmp_path: Path) -> None:
    path = tmp_path / "artifact.json"
    path.write_text(json.dumps({
        "candidate_id": "x",
        "strategy_family": "s",
        "parameter_cell_id": "p",
        "n_independent": 40,
        "sample_unit": "non_overlapping",
        "oos_start_date": "2026-03-01",
        "psr_0": 0.9,
        "dsr": 0.8,
        "pbo": 0.2,
        "regime": "chop",
        "symbol_count": 10,
        "cost_bps": 1.0,
        "recent_90d_net_bps": 1.0,
        "source_path": "missing-source.txt",
        "source_sha256": "0" * 64,
        "advisory_only": True,
        "order_authority_granted": False,
        "promotion_proof": False,
    }), encoding="utf-8")

    result = audit.audit_path(path, profile="aeg_artifact")
    finding_ids = {row["finding_id"] for row in result["findings"]}

    assert result["status"] == "audit_gap"
    assert "referenced_artifact_missing" in finding_ids


@pytest.mark.parametrize(
    "line",
    [
        "promotion_ready",
        "stage0_ready",
        "approve_trade",
        "approve trading",
        "pass to trading",
        "order_capable_action_allowed=true",
        "recommendation SELL",
        "sizing recommendation",
    ],
)
def test_forbidden_vocabulary_patterns_are_audit_gaps(tmp_path: Path, line: str) -> None:
    path = tmp_path / "report.md"
    path.write_text(
        "status ready\nartifact sha abc123\nno order no bybit no pg advisory\n"
        "verification pytest passed\nnext operator handoff\n"
        f"{line}\n",
        encoding="utf-8",
    )

    result = audit.audit_path(path, profile="pm_report")
    finding_ids = {row["finding_id"] for row in result["findings"]}

    assert result["status"] == "audit_gap"
    assert "forbidden_authority_vocabulary" in finding_ids
