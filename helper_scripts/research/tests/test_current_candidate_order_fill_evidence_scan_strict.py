from __future__ import annotations

import json

from cost_gate_learning_lane import current_candidate_order_fill_evidence_scan_strict as mod


CANDIDATE = "ma_crossover|NEARUSDT|Buy"


def _write_jsonl(path, rows) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_blocked_signal_rows_are_not_actual_fill_evidence(tmp_path) -> None:
    ledger = tmp_path / "probe_ledger.jsonl"
    _write_jsonl(
        ledger,
        [
            {
                "ts_utc": "2026-07-08T18:00:00+00:00",
                "record_type": "blocked_signal_outcome",
                "candidate_summary": {"side_cell_key": CANDIDATE},
                "allowed_to_submit_order": True,
            }
        ],
    )

    scan = mod.build_scan(
        candidate=CANDIDATE,
        ledger_paths=[ledger],
        snapshot_paths=[],
        log_paths=[],
    )

    assert scan["status"] == mod.NO_EVIDENCE_STATUS
    assert scan["candidate_matched_actual_order_fill_evidence_present"] is False
    assert scan["ledger_counts"]["candidate_rows"] == 1
    assert scan["ledger_allowed_true_samples"]
    assert scan["ledger_strict_evidence_samples"] == []


def test_candidate_matched_fill_identifiers_are_actual_evidence(tmp_path) -> None:
    ledger = tmp_path / "probe_ledger.jsonl"
    _write_jsonl(
        ledger,
        [
            {
                "ts_utc": "2026-07-08T18:00:00+00:00",
                "record_type": "bounded_probe_fill",
                "side_cell_key": CANDIDATE,
                "exchange_order_id": "demo-order-1",
                "fill_id": "fill-1",
                "fee_bps": 5.5,
                "slippage_bps": 1.2,
            }
        ],
    )

    scan = mod.build_scan(
        candidate=CANDIDATE,
        ledger_paths=[ledger],
        snapshot_paths=[],
        log_paths=[],
    )

    assert scan["status"] == mod.EVIDENCE_PRESENT_STATUS
    assert scan["candidate_matched_actual_order_fill_evidence_present"] is True
    assert scan["ledger_strict_evidence_samples"][0]["record_type"] == "bounded_probe_fill"


def test_pipeline_snapshot_strict_hit_counts_as_evidence(tmp_path) -> None:
    snapshot = tmp_path / "pipeline_snapshot_demo.json"
    snapshot.write_text(
        json.dumps(
            {
                "demo": {
                    "latest_fill": {
                        "candidate": CANDIDATE,
                        "exchange_order_id": "demo-order-2",
                        "reconstruction_status": "matched",
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    scan = mod.build_scan(
        candidate=CANDIDATE,
        ledger_paths=[],
        snapshot_paths=[snapshot],
        log_paths=[],
    )

    assert scan["status"] == mod.EVIDENCE_PRESENT_STATUS
    assert (
        scan["pipeline_snapshot_strict_hits"][str(snapshot)]["strict_candidate_objects"]
        >= 1
    )
