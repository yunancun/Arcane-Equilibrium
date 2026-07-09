"""Read-only adapter for Rust-owned ``trading.scanner_snapshots`` rows."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Collection, Mapping
from datetime import datetime, timezone
from typing import Any


SOURCE_TABLE = "trading.scanner_snapshots"
OUTPUT_SCHEMA_VERSION = "alr_scanner_cycle_v1"

_REQUIRED_FIELDS = (
    "ts",
    "scan_id",
    "active_symbols",
    "added",
    "removed",
    "rejected_count",
    "scan_duration_ms",
    "candidates",
    "config",
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class AlrScannerSnapshotError(ValueError):
    """A caller-provided scanner row cannot become an ALR evidence cycle."""


def adapt_scanner_snapshot(
    snapshot: Mapping[str, Any],
    *,
    processed_source_keys: Collection[str] = (),
    watermark: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a hash-bound, evidence-only ALR cycle from one scanner snapshot."""
    if not isinstance(snapshot, Mapping):
        raise AlrScannerSnapshotError("snapshot_not_mapping")
    missing = [field for field in _REQUIRED_FIELDS if field not in snapshot]
    if missing:
        raise AlrScannerSnapshotError(f"snapshot_missing_fields:{','.join(missing)}")
    if not isinstance(snapshot["candidates"], list):
        raise AlrScannerSnapshotError("snapshot_candidates_not_list")
    for index, candidate in enumerate(snapshot["candidates"]):
        if not isinstance(candidate, Mapping):
            raise AlrScannerSnapshotError(f"snapshot_candidate_{index}_not_mapping")
        _required_text(candidate.get("symbol"), f"snapshot_candidate_{index}_symbol")

    ts = _canonical_timestamp(snapshot["ts"])
    scan_id = _required_text(snapshot["scan_id"], "scan_id")
    active_symbols = _validate_symbol_list(
        snapshot["active_symbols"], "snapshot_active_symbols"
    )
    added = _validate_symbol_list(snapshot["added"], "snapshot_added")
    removed = _validate_symbol_list(snapshot["removed"], "snapshot_removed")
    if not set(added).issubset(active_symbols):
        raise AlrScannerSnapshotError("snapshot_added_not_active")
    if set(added).intersection(removed):
        raise AlrScannerSnapshotError("snapshot_added_removed_overlap")
    if set(removed).intersection(active_symbols):
        raise AlrScannerSnapshotError("snapshot_removed_still_active")
    rejected_count = _nonnegative_int(snapshot["rejected_count"], "snapshot_rejected_count")
    scan_duration_ms = _nonnegative_int(
        snapshot["scan_duration_ms"], "snapshot_scan_duration_ms"
    )
    if not isinstance(snapshot["config"], Mapping):
        raise AlrScannerSnapshotError("snapshot_config_not_mapping")
    payload = {field: snapshot[field] for field in _REQUIRED_FIELDS}
    payload["ts"] = ts
    payload["scan_id"] = scan_id
    payload["active_symbols"] = active_symbols
    payload["added"] = added
    payload["removed"] = removed
    payload["rejected_count"] = rejected_count
    payload["scan_duration_ms"] = scan_duration_ms
    payload["config"] = dict(snapshot["config"])
    source_key = f"{scan_id}|{ts}"
    source_hash = _canonical_sha256(payload)
    duplicate = source_key in processed_source_keys
    current_watermark = {
        "ts": ts,
        "scan_id": scan_id,
        "source_hash": source_hash,
    }
    previous_watermark = _normalise_watermark(watermark) if watermark else None
    watermark_advanced = not duplicate and (
        previous_watermark is None
        or (ts, scan_id) > (previous_watermark["ts"], previous_watermark["scan_id"])
    )
    next_watermark = current_watermark if watermark_advanced else previous_watermark or current_watermark
    disposition = "DUPLICATE" if duplicate else "NEW" if watermark_advanced else "NEW_LATE"

    return {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "source": {
            "table": SOURCE_TABLE,
            "scan_id": scan_id,
            "ts": ts,
            "source_key": source_key,
        },
        "source_hash": source_hash,
        "payload": payload,
        "disposition": disposition,
        "watermark_advanced": watermark_advanced,
        "next_watermark": next_watermark,
        "authority": {
            "scanner_evidence_only": True,
            "exchange_authority": False,
            "trading_authority": False,
            "proof_authority": False,
            "serving_authority": False,
            "promotion_authority": False,
        },
    }


def _canonical_timestamp(value: Any) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise AlrScannerSnapshotError("snapshot_ts_naive")
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if not isinstance(value, str) or not value.endswith("Z") or not value.strip():
        raise AlrScannerSnapshotError("snapshot_ts_not_utc_z")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AlrScannerSnapshotError("snapshot_ts_invalid") from exc
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AlrScannerSnapshotError(f"{field}_blank")
    return value


def _validate_symbol_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list):
        raise AlrScannerSnapshotError(f"{field}_not_list")
    symbols = [_required_text(symbol, f"{field}_symbol") for symbol in value]
    if len(symbols) != len(set(symbols)):
        raise AlrScannerSnapshotError(f"{field}_duplicate")
    return symbols


def _nonnegative_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise AlrScannerSnapshotError(f"{field}_not_int")
    if value < 0:
        raise AlrScannerSnapshotError(f"{field}_negative")
    return value


def _normalise_watermark(value: Mapping[str, Any]) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise AlrScannerSnapshotError("watermark_not_mapping")
    source_hash = _required_text(value.get("source_hash"), "watermark_source_hash")
    if not _SHA256_RE.fullmatch(source_hash):
        raise AlrScannerSnapshotError("watermark_source_hash_invalid")
    return {
        "ts": _canonical_timestamp(value.get("ts")),
        "scan_id": _required_text(value.get("scan_id"), "watermark_scan_id"),
        "source_hash": source_hash,
    }


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise AlrScannerSnapshotError(f"snapshot_not_canonical_json:{exc}") from exc
    return hashlib.sha256(encoded).hexdigest()
