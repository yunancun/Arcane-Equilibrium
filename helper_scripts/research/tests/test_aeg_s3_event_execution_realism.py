"""Tests for AEG-S3 event execution-realism empirical adapter."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from aeg_robustness_matrix import builder as matrix_builder
from aeg_s3_event_execution_realism import builder as builder_mod
from aeg_s3_event_execution_realism import harness as harness_mod


def _funding_evidence(sample_count: int = 40) -> dict:
    samples = []
    for idx in range(sample_count):
        samples.append({
            "sample_id": f"sample_{idx}",
            "sample_ts_utc": f"2025-06-{(idx % 28) + 1:02d}T00:00:00+00:00",
            "symbol": "BTCUSDT" if idx % 2 == 0 else "ETHUSDT",
            "gross_bps": 20.0,
            "cost_bps": 5.0,
            "net_bps": 15.0,
            "independence_bucket": f"2025-06-{(idx % 28) + 1:02d}:funding_revive",
        })
    return {
        "candidate_id": "funding_revive",
        "strategy_family": "funding_revive",
        "parameter_cell_id": "cell_a",
        "sample_unit": "funding_revive_event_window",
        "samples": samples,
    }


def _observations_for(evidence: dict, *, count: int = 40) -> list[dict]:
    out = []
    for idx, sample in enumerate(evidence["samples"][:count]):
        out.append({
            "sample_id": sample["sample_id"],
            "candidate_id": "funding_revive",
            "parameter_cell_id": "cell_a",
            "evidence_source_tier": "demo_fills",
            "order_style": "maker",
            "maker_fee_bps": 2.0,
            "taker_fee_bps": 5.5,
            "slippage_bps": 1.0 + (idx % 3) * 0.1,
            "maker_fill": idx % 5 != 0,
            "adverse_selection_bps": 1.0 + (idx % 4) * 0.2,
            "latency_ms": 250 + idx,
            "participation_rate": 0.01 + (idx % 5) * 0.001,
            "capacity_notional_usdt": 10_000,
            "order_availability_status": "PASS",
        })
    return out


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_empirical_event_observations_write_pass_artifact(tmp_path):
    evidence = _funding_evidence()
    evidence_path = tmp_path / "evidence.json"
    obs_path = tmp_path / "obs.jsonl"
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
    _write_jsonl(obs_path, _observations_for(evidence))

    result = harness_mod.build_and_write(argparse.Namespace(
        run_id="event_exec",
        candidate_evidence_json=str(evidence_path),
        execution_observations_jsonl=str(obs_path),
        evidence_source_tier=None,
        order_style=None,
        capacity_notional_usdt=None,
        order_availability_status=None,
        artifact_root=str(tmp_path / "out"),
        session_id=None,
        created_by_role="PM",
    ))

    payload = result["payload"]
    assert payload["status"] == "PASS"
    assert payload["execution_realism_mode"] == "calibrated_demo_fills_maker"
    assert payload["sample_count"] == 40
    assert payload["maker_fill_rate"] == 0.8
    assert payload["event_execution_summary"]["matched_observation_count"] == 40
    loaded = matrix_builder.load_execution_realism(Path(result["written"]["execution_realism_json"]))
    assert loaded["status"] == "PASS"


def test_insufficient_or_unmatched_observations_fail_closed():
    evidence = _funding_evidence()
    rows = _observations_for(evidence, count=10)
    rows.append({
        "sample_id": "not_a_candidate_sample",
        "candidate_id": "funding_revive",
        "parameter_cell_id": "cell_a",
        "evidence_source_tier": "demo_fills",
        "order_style": "maker",
    })

    raw, summary = builder_mod.build_execution_input(
        candidate_evidence=evidence,
        observation_rows=rows,
    )
    from aeg_execution_realism import builder as exec_builder
    payload = exec_builder.evaluate(raw)

    assert summary["matched_observation_count"] == 10
    assert summary["rejected_observation_reasons"] == {"unmatched_candidate_event_sample": 1}
    assert payload["status"] == "FAIL"
    assert "sample_count_below_30" in payload["reject_reasons"]


def test_oi_delta_basket_evidence_is_unsupported():
    with pytest.raises(builder_mod.UnsupportedCandidateEvidence):
        builder_mod.build_execution_input(
            candidate_evidence={
                "candidate_id": "oi_delta",
                "samples": [{
                    "sample_ts_utc": "2025-06-01T00:00:00+00:00",
                    "gross_bps": 1.0,
                    "cost_bps": 1.0,
                    "net_bps": 0.0,
                    "top_symbols": ["BTCUSDT"],
                    "bottom_symbols": ["ETHUSDT"],
                }],
            },
            observation_rows=[],
        )


def test_static_no_runtime_or_db_route():
    pkg = Path(__file__).resolve().parents[1] / "aeg_s3_event_execution_realism"
    code = "\n".join(path.read_text(encoding="utf-8") for path in pkg.glob("*.py"))
    forbidden = (
        "control_api_v1",
        "psycopg2",
        "asyncpg",
        "INSERT INTO",
        "UPDATE ",
        "DELETE FROM",
        "OPENCLAW_ALLOW_MAINNET",
        "execution_authority",
        "wss://stream.bybit.com",
        "urlopen",
    )
    for needle in forbidden:
        assert needle not in code
