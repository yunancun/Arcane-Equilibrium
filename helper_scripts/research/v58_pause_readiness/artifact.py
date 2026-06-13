"""Artifact writer for V5.8 pause readiness summaries."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import socket
import subprocess
from pathlib import Path
from typing import Any

from . import MANIFEST_SCHEMA_VERSION, RUNNER_VERSION, SUMMARY_SCHEMA_VERSION


def default_artifact_root() -> Path:
    base = os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw").strip() or "/tmp/openclaw"
    return Path(base) / "v58_pause_readiness"


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
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

    diff = _run(["git", "diff", "HEAD"])
    return {
        "git_sha": _run(["git", "rev-parse", "HEAD"]) or "unknown",
        "git_dirty": bool(_run(["git", "status", "--porcelain"])),
        "git_diff_sha256": hashlib.sha256(diff.encode("utf-8")).hexdigest() if diff else None,
    }


def _index_entry(name: str, path: Path, schema_version: str) -> dict[str, Any]:
    return {
        "name": name,
        "path": str(path),
        "sha256": _sha256(path),
        "byte_size": path.stat().st_size,
        "row_count": None,
        "schema_version": schema_version,
    }


def write_all(
    *,
    summary: dict[str, Any],
    run_id: str,
    repo_root: Path,
    artifact_root: Path | None = None,
    runtime_host: str | None = None,
    session_id: str | None = None,
    created_by_role: str = "PM",
) -> dict[str, str]:
    root = artifact_root or default_artifact_root()
    run_dir = root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    summary_path = write_json(run_dir / "v58_pause_readiness_summary.json", summary)
    artifacts = [_index_entry("v58_pause_readiness_summary.json", summary_path, SUMMARY_SCHEMA_VERSION)]
    prov = _git_provenance(repo_root)
    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "run_id": run_id,
        "program": "V5.8-pause-readiness",
        "session_id": session_id,
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "created_by_role": created_by_role,
        "git_sha": prov["git_sha"],
        "git_dirty": prov["git_dirty"],
        "git_diff_sha256": prov["git_diff_sha256"],
        "runtime_host": runtime_host or socket.gethostname(),
        "runner_version": RUNNER_VERSION,
        "pause_readiness_status": summary.get("pause_readiness_status"),
        "policy": "inspect_repo_and_optional_gate_watch_only_no_db_no_runtime_mutation",
        "artifacts": artifacts,
    }
    manifest_path = write_json(run_dir / "manifest.json", manifest)
    artifacts.append(_index_entry("manifest.json", manifest_path, MANIFEST_SCHEMA_VERSION))
    index_path = write_json(
        run_dir / "artifact_index.json",
        {
            "schema_version": "v58.pause_readiness_artifact_index.v0.1",
            "run_id": run_id,
            "artifacts": artifacts,
        },
    )
    return {
        "run_dir": str(run_dir),
        "summary": str(summary_path),
        "manifest": str(manifest_path),
        "artifact_index": str(index_path),
    }


__all__ = ["default_artifact_root", "write_all", "write_json"]
