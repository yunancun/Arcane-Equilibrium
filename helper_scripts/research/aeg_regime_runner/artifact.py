"""AEG regime runner artifact writer.

MODULE_NOTE:
  模塊用途：把 regime labels / transitions / feature_lineage 寫成本地 deterministic
    artifact。CSV 是 SoT；parquet mirror 可選，缺 duckdb 不阻斷。manifest/index
    帶 git provenance、schema version 與 child sha256。
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Any, Optional, Sequence

from . import (
    LABEL_SCHEMA_VERSION,
    LINEAGE_SCHEMA_VERSION,
    MANIFEST_SCHEMA_VERSION,
    RUNNER_VERSION,
    TRANSITION_SCHEMA_VERSION,
)

logger = logging.getLogger(__name__)

LABEL_COLUMNS = (
    "classifier_version",
    "run_id",
    "signal_ts",
    "symbol",
    "timeframe",
    "main_regime",
    "market_anchor_regime",
    "high_vol_overlay",
    "overlay_flags",
    "ret_30d",
    "ret_90d",
    "rv_30d",
    "rv_90d",
    "trend_z_30",
    "ma_50",
    "ma_200",
    "efficiency_30",
    "direction_flip_30",
    "rv_30d_percentile_365",
    "context_bars",
    "insufficient_context",
    "feature_rules_digest",
)

TRANSITION_COLUMNS = (
    "classifier_version",
    "run_id",
    "symbol",
    "timeframe",
    "transition_ts",
    "from_regime",
    "to_regime",
    "trigger_feature",
)

LINEAGE_COLUMNS = (
    "run_id",
    "classifier_version",
    "signal_ts_utc",
    "symbol",
    "feature_name",
    "source_table",
    "source_endpoint",
    "source_ts_utc",
    "bar_close_ts_utc",
    "feature_bar_ms",
    "lookback_bars",
    "join_rule_version",
    "lag_ms",
    "leak_violation_count",
)


def resolve_artifact_root() -> Path:
    """解析 artifact 根目錄（跨平台，與 FND-2/breadth 共用 alpha_history_runs）。"""
    base = os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw").strip() or "/tmp/openclaw"
    return Path(base) / "alpha_history_runs"


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, dt.datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=dt.timezone.utc)
        return value.astimezone(dt.timezone.utc).isoformat()
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return str(value)


def write_csv(rows: Sequence[dict[str, Any]], path: Path, columns: Sequence[str]) -> Path:
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(list(columns))
        for row in rows:
            writer.writerow([_cell(row.get(col)) for col in columns])
    return path


def mirror_parquet(csv_path: Path, parquet_path: Path) -> dict[str, str]:
    """duckdb parquet mirror；失敗不阻斷。"""
    try:
        import duckdb  # type: ignore
    except ImportError:
        return {"parquet_mirror": "skipped", "reason": "duckdb_not_available"}
    try:
        con = duckdb.connect(database=":memory:")
        try:
            con.read_csv(str(csv_path), all_varchar=True).write_parquet(str(parquet_path))
        finally:
            con.close()
        return {"parquet_mirror": "ok"}
    except Exception as exc:  # noqa: BLE001
        logger.warning("AEG regime parquet mirror failed: %s", exc)
        return {"parquet_mirror": "failed", "reason": f"mirror_failed:{exc}"}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    return path


def _git_provenance(repo_root: Path) -> dict[str, Any]:
    def _run(args: list[str]) -> str:
        try:
            return subprocess.run(
                args,
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                timeout=10,
            ).stdout.strip()
        except Exception:
            return ""

    sha = _run(["git", "rev-parse", "HEAD"]) or "unknown"
    status = _run(["git", "status", "--porcelain"])
    diff = _run(["git", "diff", "HEAD"])
    return {
        "git_sha": sha,
        "git_dirty": bool(status),
        "git_diff_sha256": hashlib.sha256(diff.encode("utf-8")).hexdigest() if diff else None,
    }


def _index_entry(name: str, path: Path, row_count: Optional[int], schema_version: str) -> dict[str, Any]:
    return {
        "name": name,
        "path": str(path),
        "sha256": _sha256(path),
        "byte_size": path.stat().st_size,
        "row_count": row_count,
        "schema_version": schema_version,
    }


def write_all(
    *,
    labels: Sequence[dict[str, Any]],
    transitions: Sequence[dict[str, Any]],
    lineage: Sequence[dict[str, Any]],
    summary: dict[str, Any],
    run_id: str,
    repo_root: Path,
    runtime_host: str,
    artifact_root: Optional[Path] = None,
    session_id: Optional[str] = None,
    created_by_role: str = "E1",
) -> dict[str, Any]:
    root = Path(artifact_root) if artifact_root is not None else resolve_artifact_root()
    run_dir = root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    labels_csv = write_csv(labels, run_dir / "regime_labels.csv", LABEL_COLUMNS)
    transitions_csv = write_csv(transitions, run_dir / "regime_transitions.csv", TRANSITION_COLUMNS)
    lineage_csv = write_csv(lineage, run_dir / "feature_lineage.csv", LINEAGE_COLUMNS)

    mirror_results = {
        "regime_labels": mirror_parquet(labels_csv, run_dir / "regime_labels.parquet"),
        "regime_transitions": mirror_parquet(transitions_csv, run_dir / "regime_transitions.parquet"),
        "feature_lineage": mirror_parquet(lineage_csv, run_dir / "feature_lineage.parquet"),
    }

    summary_path = write_json(
        run_dir / "regime_summary.json",
        {**summary, "parquet_mirror": mirror_results},
    )

    artifacts = [
        _index_entry("regime_labels_csv", labels_csv, len(labels), LABEL_SCHEMA_VERSION),
        _index_entry("regime_transitions_csv", transitions_csv, len(transitions), TRANSITION_SCHEMA_VERSION),
        _index_entry("feature_lineage_csv", lineage_csv, len(lineage), LINEAGE_SCHEMA_VERSION),
        _index_entry("regime_summary_json", summary_path, None, "aeg.regime_summary.v0.1"),
    ]
    prov = _git_provenance(repo_root)
    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "run_id": run_id,
        "program": "AEG",
        "component": "regime_runner",
        "runner_version": RUNNER_VERSION,
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "created_by_role": created_by_role,
        "session_id": session_id,
        "runtime_host": runtime_host,
        "source_tables": ["market.klines"],
        "provenance_mode": "artifact_manifest",
        "artifacts": artifacts,
        **prov,
    }
    manifest_path = write_json(run_dir / "manifest.json", manifest)
    artifacts.append(_index_entry("manifest_json", manifest_path, None, MANIFEST_SCHEMA_VERSION))
    index_path = write_json(
        run_dir / "artifact_index.json",
        {
            "schema_version": "aeg.regime_artifact_index.v0.1",
            "run_id": run_id,
            "artifacts": artifacts,
        },
    )
    artifacts.append(_index_entry("artifact_index_json", index_path, None, "aeg.regime_artifact_index.v0.1"))
    write_json(
        index_path,
        {
            "schema_version": "aeg.regime_artifact_index.v0.1",
            "run_id": run_id,
            "artifacts": artifacts,
        },
    )

    return {
        "run_dir": str(run_dir),
        "regime_labels": str(labels_csv),
        "regime_transitions": str(transitions_csv),
        "feature_lineage": str(lineage_csv),
        "regime_summary": str(summary_path),
        "manifest": str(manifest_path),
        "artifact_index": str(index_path),
        "row_count": len(labels),
    }
