"""AEG-S3 OI delta evidence artifact writer。"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import socket
import subprocess
from pathlib import Path
from typing import Any, Optional

from . import EVIDENCE_SCHEMA_VERSION, MANIFEST_SCHEMA_VERSION, RUNNER_VERSION


def resolve_artifact_root() -> Path:
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


def _index_entry(name: str, path: Path, schema_version: str) -> dict[str, Any]:
    return {
        "name": name,
        "path": str(path),
        "sha256": _sha256(path),
        "byte_size": path.stat().st_size,
        "schema_version": schema_version,
    }


def write_all(
    *,
    evidence: dict[str, Any],
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

    evidence_path = write_json(run_dir / "oi_delta_candidate_evidence.json", evidence)
    summary_path = write_json(run_dir / "oi_delta_evidence_summary.json", summary)
    artifacts = [
        _index_entry("oi_delta_candidate_evidence.json", evidence_path, EVIDENCE_SCHEMA_VERSION),
        _index_entry("oi_delta_evidence_summary.json", summary_path, summary.get("schema_version", "unknown")),
    ]
    prov = _git_provenance(repo_root)
    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "run_id": run_id,
        "program": "AEG-S3-oi-delta-evidence",
        "session_id": session_id,
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "created_by_role": created_by_role,
        "git_sha": prov["git_sha"],
        "git_dirty": prov["git_dirty"],
        "git_diff_sha256": prov["git_diff_sha256"],
        "runtime_host": runtime_host or socket.gethostname(),
        "runner_version": RUNNER_VERSION,
        "candidate_id": evidence.get("candidate_id"),
        "strategy_family": evidence.get("strategy_family"),
        "parameter_cell_id": evidence.get("parameter_cell_id"),
        "policy": evidence.get("policy"),
        "artifacts": artifacts,
    }
    manifest_path = write_json(run_dir / "manifest.json", manifest)
    artifacts.append(_index_entry("manifest.json", manifest_path, MANIFEST_SCHEMA_VERSION))
    index_path = write_json(
        run_dir / "artifact_index.json",
        {"schema_version": "aeg.s3_oi_delta_artifact_index.v0.1", "run_id": run_id, "artifacts": artifacts},
    )
    return {
        "run_dir": str(run_dir),
        "candidate_evidence": str(evidence_path),
        "summary": str(summary_path),
        "manifest": str(manifest_path),
        "artifact_index": str(index_path),
    }
