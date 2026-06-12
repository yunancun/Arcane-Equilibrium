"""Artifact writer for AEG-S3 execution observations."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import socket
import subprocess
from pathlib import Path
from typing import Any, Optional

from . import (
    MANIFEST_SCHEMA_VERSION,
    OBSERVATION_SCHEMA_VERSION,
    RUNNER_VERSION,
    SUMMARY_SCHEMA_VERSION,
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


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> Path:
    with open(path, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True, default=str) + "\n")
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
    observations: list[dict[str, Any]],
    summary: dict[str, Any],
    run_id: str,
    repo_root: Path,
    artifact_root: Optional[Path] = None,
    runtime_host: Optional[str] = None,
    session_id: Optional[str] = None,
    created_by_role: str = "PM",
) -> dict[str, str]:
    root = Path(artifact_root) if artifact_root is not None else resolve_artifact_root()
    run_dir = root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    observations_path = write_jsonl(run_dir / "execution_observations.jsonl", observations)
    summary_path = write_json(run_dir / "execution_observations_summary.json", summary)
    artifacts = [
        _index_entry("execution_observations.jsonl", observations_path, len(observations), OBSERVATION_SCHEMA_VERSION),
        _index_entry("execution_observations_summary.json", summary_path, None, SUMMARY_SCHEMA_VERSION),
    ]
    prov = _git_provenance(repo_root)
    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "run_id": run_id,
        "program": "AEG-S3-execution-observations",
        "session_id": session_id,
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "created_by_role": created_by_role,
        "git_sha": prov["git_sha"],
        "git_dirty": prov["git_dirty"],
        "git_diff_sha256": prov["git_diff_sha256"],
        "runtime_host": runtime_host or socket.gethostname(),
        "runner_version": RUNNER_VERSION,
        "candidate_id": summary.get("candidate_id"),
        "strategy_family": summary.get("strategy_family"),
        "parameter_cell_id": summary.get("parameter_cell_id"),
        "evidence_source_tier": summary.get("evidence_source_tier"),
        "order_style": summary.get("order_style"),
        "policy": "matched_event_execution_observations_only",
        "artifacts": artifacts,
    }
    manifest_path = write_json(run_dir / "manifest.json", manifest)
    artifacts.append(_index_entry("manifest.json", manifest_path, None, MANIFEST_SCHEMA_VERSION))
    index_path = write_json(
        run_dir / "artifact_index.json",
        {"schema_version": "aeg.s3_execution_observations_artifact_index.v0.1", "run_id": run_id, "artifacts": artifacts},
    )
    return {
        "run_dir": str(run_dir),
        "execution_observations_jsonl": str(observations_path),
        "summary": str(summary_path),
        "manifest": str(manifest_path),
        "artifact_index": str(index_path),
    }


__all__ = [
    "resolve_artifact_root",
    "write_all",
    "write_json",
    "write_jsonl",
]

