"""AEG execution-realism builder 測試。"""

from __future__ import annotations

import json
from pathlib import Path

from aeg_execution_realism import artifact as artifact_mod
from aeg_execution_realism import builder as builder_mod
from aeg_robustness_matrix import builder as matrix_builder


def _valid_payload() -> dict:
    return {
        "candidate_id": "cand_listing_fade",
        "strategy_family": "listing_fade",
        "parameter_cell_id": "default",
        "status": "PASS",  # 輸入 status 不被信任；此 case 只是確保不被破壞。
        "evidence_source_tier": "live_demo_fills",
        "order_style": "maker",
        "maker_fee_bps": 2.0,
        "taker_fee_bps": 5.5,
        "slippage_bps_p95": 1.5,
        "maker_fill_rate": 0.72,
        "adverse_selection_bps_p95": 2.0,
        "latency_ms_p95": 420,
        "participation_rate_p95": 0.02,
        "sample_count": 64,
        "capacity_notional_usdt": 5000,
        "order_availability_status": "PASS",
    }


def test_empirical_maker_payload_passes_and_computes_cost():
    payload = builder_mod.evaluate(_valid_payload())

    assert payload["status"] == "PASS"
    assert payload["reject_reasons"] == []
    assert payload["execution_realism_mode"] == "calibrated_live_demo_fills_maker"
    assert payload["effective_fee_bps_per_side"] == 2.0
    assert payload["cost_bps_round_trip_p95"] == 9.0


def test_assumption_only_fails_even_if_input_status_claims_pass():
    raw = _valid_payload()
    raw.update({
        "status": "PASS",
        "evidence_source_tier": "assumption_only",
        "sample_count": 0,
    })

    payload = builder_mod.evaluate(raw)

    assert payload["status"] == "FAIL"
    assert "execution_realism_not_empirical" in payload["reject_reasons"]
    assert "sample_count_below_30" in payload["reject_reasons"]
    assert payload["input_status"] == "PASS"


def test_missing_required_fields_fail_closed():
    payload = builder_mod.evaluate({
        "candidate_id": "cand_x",
        "evidence_source_tier": "live_demo_fills",
        "order_style": "maker",
    })

    assert payload["status"] == "FAIL"
    reasons = set(payload["reject_reasons"])
    assert "missing_maker_fee_bps" in reasons
    assert "missing_taker_fee_bps" in reasons
    assert "missing_maker_fill_rate" in reasons
    assert "missing_order_availability_status" in reasons


def test_artifact_write_creates_manifest_index_and_matrix_loader_reads_it(tmp_path):
    payload = builder_mod.evaluate(_valid_payload())
    written = artifact_mod.write_all(
        payload,
        run_id="exec_realism_run",
        repo_root=Path("."),
        runtime_host="test",
        artifact_root=tmp_path / "out",
        created_by_role="PM",
    )

    run_dir = Path(written["run_dir"])
    realism_path = run_dir / "execution_realism.json"
    assert realism_path.exists()
    assert (run_dir / "manifest.json").exists()
    assert (run_dir / "artifact_index.json").exists()
    loaded = matrix_builder.load_execution_realism(realism_path)
    assert loaded["status"] == "PASS"
    assert loaded["execution_realism_mode"] == "calibrated_live_demo_fills_maker"
    index = json.loads((run_dir / "artifact_index.json").read_text(encoding="utf-8"))
    assert any(entry["name"] == "execution_realism.json" for entry in index["artifacts"])


def test_execution_realism_has_no_runtime_or_db_write_route_static():
    pkg = Path(__file__).resolve().parents[1] / "aeg_execution_realism"
    code = "\n".join(path.read_text(encoding="utf-8") for path in pkg.glob("*.py"))
    forbidden = (
        "control_api_v1",
        "psycopg2",
        "asyncpg",
        "INSERT INTO",
        "UPDATE ",
        "DELETE FROM",
        "OPENCLAW_ALLOW_MAINNET",
        "live_execution_allowed",
        "execution_authority",
    )
    for needle in forbidden:
        assert needle not in code
