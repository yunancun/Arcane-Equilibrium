"""AEG execution-realism artifact writer。"""

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
    EXECUTION_REALISM_SCHEMA_VERSION,
    MANIFEST_SCHEMA_VERSION,
    RUNNER_VERSION,
)


def resolve_artifact_root() -> Path:
    """解析 artifact 根目錄（與 AEG 其他 artifact 共用 alpha_history_runs）。"""
    base = os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw").strip() or "/tmp/openclaw"
    return Path(base) / "alpha_history_runs"


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
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
    payload: dict[str, Any],
    *,
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

    realism_path = write_json(run_dir / "execution_realism.json", {**payload, "run_id": run_id})
    artifacts = [
        _index_entry("execution_realism.json", realism_path, None, EXECUTION_REALISM_SCHEMA_VERSION)
    ]
    prov = _git_provenance(repo_root)
    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "run_id": run_id,
        "program": "AEG",
        "session_id": session_id,
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "created_by_role": created_by_role,
        "git_sha": prov["git_sha"],
        "git_dirty": prov["git_dirty"],
        "git_diff_sha256": prov["git_diff_sha256"],
        "runtime_host": runtime_host or socket.gethostname(),
        "timezone": "UTC",
        "execution_realism_runner_version": RUNNER_VERSION,
        "candidate_id": payload.get("candidate_id"),
        "strategy_family": payload.get("strategy_family"),
        "parameter_cell_id": payload.get("parameter_cell_id"),
        "status": payload.get("status"),
        "execution_realism_mode": payload.get("execution_realism_mode"),
        "evidence_source_tier": payload.get("evidence_source_tier"),
        "order_style": payload.get("order_style"),
        "policy": "empirical_execution_evidence_required",
        "artifacts": artifacts,
    }
    manifest_path = write_json(run_dir / "manifest.json", manifest)
    artifacts.append(_index_entry("manifest.json", manifest_path, None, MANIFEST_SCHEMA_VERSION))

    index = {
        "schema_version": "aeg.artifact_index.v0.1",
        "run_id": run_id,
        "artifacts": artifacts,
    }
    index_path = write_json(run_dir / "artifact_index.json", index)
    return {
        "run_dir": str(run_dir),
        "execution_realism_json": str(realism_path),
        "manifest": str(manifest_path),
        "artifact_index": str(index_path),
    }
