"""AEG-S3 candidate rows artifact writer。"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import os
import socket
import subprocess
from pathlib import Path
from typing import Any, Optional, Sequence

from . import (
    DAILY_RETURNS_SCHEMA_VERSION,
    DIRECT_REPORT_SCHEMA_VERSION,
    MANIFEST_SCHEMA_VERSION,
    RUNNER_VERSION,
    SAMPLE_COLUMNS,
    SAMPLE_RETURNS_SCHEMA_VERSION,
)


def resolve_artifact_root() -> Path:
    base = os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw").strip() or "/tmp/openclaw"
    return Path(base) / "alpha_history_runs"


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    return path


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def write_samples_csv(rows: Sequence[dict[str, Any]], path: Path) -> Path:
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(list(SAMPLE_COLUMNS))
        for row in rows:
            writer.writerow([_cell(row.get(col)) for col in SAMPLE_COLUMNS])
    return path


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


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
    direct_report: dict[str, Any],
    summary: dict[str, Any],
    sample_rows: Sequence[dict[str, Any]],
    daily_rows: Sequence[dict[str, Any]],
    run_id: str,
    repo_root: Path,
    runtime_host: Optional[str] = None,
    artifact_root: Optional[Path] = None,
    session_id: Optional[str] = None,
    created_by_role: str = "E1",
) -> dict[str, Any]:
    root = Path(artifact_root) if artifact_root is not None else resolve_artifact_root()
    run_dir = root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    report_path = write_json(run_dir / "candidate_direct_metrics_report.json", direct_report)
    summary_path = write_json(run_dir / "candidate_rows_summary.json", summary)
    samples_path = write_samples_csv(sample_rows, run_dir / "candidate_sample_returns.csv")
    daily_path = write_json(
        run_dir / "candidate_daily_returns.json",
        {"schema_version": DAILY_RETURNS_SCHEMA_VERSION, "run_id": run_id, "rows": list(daily_rows)},
    )
    artifacts = [
        _index_entry("candidate_direct_metrics_report.json", report_path, None, DIRECT_REPORT_SCHEMA_VERSION),
        _index_entry("candidate_rows_summary.json", summary_path, None, summary.get("schema_version", "unknown")),
        _index_entry("candidate_sample_returns.csv", samples_path, len(sample_rows), SAMPLE_RETURNS_SCHEMA_VERSION),
        _index_entry("candidate_daily_returns.json", daily_path, len(daily_rows), DAILY_RETURNS_SCHEMA_VERSION),
    ]
    prov = _git_provenance(repo_root)
    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "run_id": run_id,
        "program": "AEG-S3",
        "session_id": session_id,
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "created_by_role": created_by_role,
        "git_sha": prov["git_sha"],
        "git_dirty": prov["git_dirty"],
        "git_diff_sha256": prov["git_diff_sha256"],
        "runtime_host": runtime_host or socket.gethostname(),
        "timezone": "UTC",
        "runner_version": RUNNER_VERSION,
        "candidate_id": direct_report.get("candidate_id"),
        "strategy_family": direct_report.get("strategy_family"),
        "parameter_cell_id": direct_report.get("parameter_cell_id"),
        "selected_variant": direct_report.get("selected_variant"),
        "policy": direct_report.get("policy"),
        "artifacts": artifacts,
    }
    manifest_path = write_json(run_dir / "manifest.json", manifest)
    artifacts.append(_index_entry("manifest.json", manifest_path, None, MANIFEST_SCHEMA_VERSION))
    index_path = write_json(
        run_dir / "artifact_index.json",
        {"schema_version": "aeg.s3_candidate_rows_artifact_index.v0.1", "run_id": run_id, "artifacts": artifacts},
    )
    return {
        "run_dir": str(run_dir),
        "candidate_direct_metrics_report": str(report_path),
        "candidate_rows_summary": str(summary_path),
        "candidate_sample_returns": str(samples_path),
        "candidate_daily_returns": str(daily_path),
        "manifest": str(manifest_path),
        "artifact_index": str(index_path),
    }
