from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from ml_training.alr_scanner_snapshot_adapter import (
    AlrScannerSnapshotError,
    OUTPUT_SCHEMA_VERSION,
    adapt_scanner_snapshot,
)


def _scanner_snapshot(**overrides: object) -> dict[str, object]:
    snapshot: dict[str, object] = {
        "ts": "2026-07-09T12:00:00Z",
        "scan_id": "scan-1783598400000",
        "active_symbols": ["BTCUSDT", "ETHUSDT"],
        "added": ["ETHUSDT"],
        "removed": [],
        "rejected_count": 3,
        "scan_duration_ms": 47,
        "candidates": [
            {
                "symbol": "BTCUSDT",
                "best_strategy": "grid_trading",
                "final_score": 42.5,
            }
        ],
        "config": {"edge_routing": {"enabled": True}},
    }
    snapshot.update(overrides)
    return snapshot


def test_adapts_rust_scanner_snapshot_as_hash_bound_evidence_only_cycle() -> None:
    cycle = adapt_scanner_snapshot(_scanner_snapshot())

    assert cycle["schema_version"] == OUTPUT_SCHEMA_VERSION
    assert cycle["source"] == {
        "table": "trading.scanner_snapshots",
        "scan_id": "scan-1783598400000",
        "ts": "2026-07-09T12:00:00Z",
        "source_key": "scan-1783598400000|2026-07-09T12:00:00Z",
    }
    assert len(cycle["source_hash"]) == 64
    assert cycle["disposition"] == "NEW"
    assert cycle["watermark_advanced"] is True
    assert cycle["authority"] == {
        "scanner_evidence_only": True,
        "exchange_authority": False,
        "trading_authority": False,
        "proof_authority": False,
        "serving_authority": False,
        "promotion_authority": False,
    }


def test_rejects_non_list_candidates_before_hashing() -> None:
    with pytest.raises(AlrScannerSnapshotError, match="snapshot_candidates_not_list"):
        adapt_scanner_snapshot(_scanner_snapshot(candidates={"symbol": "BTCUSDT"}))


def test_processed_source_key_is_duplicate_and_does_not_advance_watermark() -> None:
    cycle = adapt_scanner_snapshot(
        _scanner_snapshot(),
        processed_source_keys={"scan-1783598400000|2026-07-09T12:00:00Z"},
    )

    assert cycle["disposition"] == "DUPLICATE"
    assert cycle["watermark_advanced"] is False


def test_late_unseen_cycle_is_retained_without_rewinding_watermark() -> None:
    watermark = {
        "ts": "2026-07-09T13:00:00Z",
        "scan_id": "scan-1783602000000",
        "source_hash": "a" * 64,
    }

    cycle = adapt_scanner_snapshot(_scanner_snapshot(), watermark=watermark)

    assert cycle["disposition"] == "NEW_LATE"
    assert cycle["watermark_advanced"] is False
    assert cycle["next_watermark"] == watermark


def test_normalizes_postgres_utc_datetime_to_same_source_key() -> None:
    cycle = adapt_scanner_snapshot(
        _scanner_snapshot(ts=datetime(2026, 7, 9, 12, 0, tzinfo=timezone.utc))
    )

    assert cycle["source"]["ts"] == "2026-07-09T12:00:00Z"
    assert cycle["source"]["source_key"] == "scan-1783598400000|2026-07-09T12:00:00Z"


def test_rejects_candidate_without_scanner_symbol_identity() -> None:
    with pytest.raises(AlrScannerSnapshotError, match="snapshot_candidate_0_symbol_blank"):
        adapt_scanner_snapshot(_scanner_snapshot(candidates=[{}]))


def test_rejects_non_list_or_duplicate_active_symbols() -> None:
    with pytest.raises(AlrScannerSnapshotError, match="snapshot_active_symbols_not_list"):
        adapt_scanner_snapshot(_scanner_snapshot(active_symbols="BTCUSDT"))

    with pytest.raises(AlrScannerSnapshotError, match="snapshot_active_symbols_duplicate"):
        adapt_scanner_snapshot(_scanner_snapshot(active_symbols=["BTCUSDT", "BTCUSDT"]))


def test_rejects_added_symbol_that_is_not_in_active_universe() -> None:
    with pytest.raises(AlrScannerSnapshotError, match="snapshot_added_not_active"):
        adapt_scanner_snapshot(_scanner_snapshot(added=["SOLUSDT"]))


def test_rejects_removed_symbol_still_active_or_added() -> None:
    with pytest.raises(AlrScannerSnapshotError, match="snapshot_removed_still_active"):
        adapt_scanner_snapshot(_scanner_snapshot(removed=["BTCUSDT"]))

    with pytest.raises(AlrScannerSnapshotError, match="snapshot_added_removed_overlap"):
        adapt_scanner_snapshot(
            _scanner_snapshot(added=["ETHUSDT"], removed=["ETHUSDT"])
        )


def test_rejects_invalid_scanner_counters() -> None:
    with pytest.raises(AlrScannerSnapshotError, match="snapshot_rejected_count_negative"):
        adapt_scanner_snapshot(_scanner_snapshot(rejected_count=-1))

    with pytest.raises(AlrScannerSnapshotError, match="snapshot_scan_duration_ms_not_int"):
        adapt_scanner_snapshot(_scanner_snapshot(scan_duration_ms=True))


def test_rejects_non_mapping_scanner_config() -> None:
    with pytest.raises(AlrScannerSnapshotError, match="snapshot_config_not_mapping"):
        adapt_scanner_snapshot(_scanner_snapshot(config=[]))


def test_rejects_watermark_without_sha256_lineage_hash() -> None:
    with pytest.raises(AlrScannerSnapshotError, match="watermark_source_hash_invalid"):
        adapt_scanner_snapshot(
            _scanner_snapshot(),
            watermark={
                "ts": "2026-07-09T13:00:00Z",
                "scan_id": "scan-1783602000000",
                "source_hash": "not-a-sha256",
            },
        )


def test_canonical_hash_is_stable_across_mapping_order() -> None:
    left = _scanner_snapshot(
        config={"edge_routing": {"enabled": True, "tier": "shadow"}, "version": 1}
    )
    right = _scanner_snapshot(
        config={"version": 1, "edge_routing": {"tier": "shadow", "enabled": True}}
    )

    assert adapt_scanner_snapshot(left)["source_hash"] == adapt_scanner_snapshot(right)["source_hash"]


def test_adapter_has_no_direct_db_network_or_runtime_imports() -> None:
    source = (Path(__file__).parents[1] / "alr_scanner_snapshot_adapter.py").read_text(
        encoding="utf-8"
    )

    assert "trading.scanner_snapshots" in source
    for forbidden in ("psycopg", "sqlalchemy", "requests", "socket", "subprocess"):
        assert forbidden not in source
