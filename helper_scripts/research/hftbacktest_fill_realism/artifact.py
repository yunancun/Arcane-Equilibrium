"""hftbacktest fill-realism artifact 寫出（append-only run dir + manifest + sha256）。

MODULE_NOTE:
  模塊用途：落 run dir artifact——raw/（Tardis 原始 CSV.gz）、hbt/（converter 8-field
    npz）、fill_realism.json / d2_revalidation.json（模擬裁決）+ manifest.json +
    artifact_index.json（逐檔 sha256，mirror deribit_vol_axis write_run）。
  依賴：標準庫。
  硬邊界（mirror deribit_vol_axis）：
    - append-only：run dir 已存在 → raise（禁回填、禁覆寫舊 snapshot）。
    - 不建 PG 表：artifact-only（避 V### migration），唯一輸出 = filesystem。
    - artifact root 禁硬編碼：${OPENCLAW_DATA_DIR:-/tmp/openclaw}/
      hftbacktest_fill_realism_runs/<run_id>/。
"""

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
    ARTIFACT_INDEX_SCHEMA_VERSION,
    D2_REVALIDATION_SCHEMA_VERSION,
    FILL_REALISM_SCHEMA_VERSION,
    MANIFEST_SCHEMA_VERSION,
    RUNNER_VERSION,
)


def resolve_data_root() -> Path:
    base = os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw").strip() or "/tmp/openclaw"
    return Path(base)


def resolve_artifact_root(data_root: Optional[Path] = None) -> Path:
    root = Path(data_root) if data_root is not None else resolve_data_root()
    return root / "hftbacktest_fill_realism_runs"


def default_run_id(mode: str, now: Optional[dt.datetime] = None) -> str:
    ts = (now or dt.datetime.now(dt.timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    return f"{mode}-{ts}"


def create_run_dir(run_id: str, artifact_root: Optional[Path] = None) -> Path:
    """建立 append-only run dir（已存在即 raise，PIT 鐵則執行點）。

    為什麼 exist_ok=False：snapshot 是當時 L2 tape 的唯一 point-in-time 來源，
    同名重跑覆寫 = 不可逆毀證；必須換 run_id。
    """
    root = artifact_root if artifact_root is not None else resolve_artifact_root()
    root.mkdir(parents=True, exist_ok=True)
    run_dir = root / run_id
    run_dir.mkdir(parents=False, exist_ok=False)
    return run_dir


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    return path


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def git_provenance(repo_root: Path) -> dict[str, Any]:
    """git sha / dirty / diff 摘要（mirror deribit_vol_axis；git 不可用回 unknown 不阻斷）。"""

    def _run(args: list[str]) -> str:
        try:
            return subprocess.run(
                args, cwd=str(repo_root), capture_output=True, text=True, timeout=10,
            ).stdout.strip()
        except Exception:  # noqa: BLE001 —— git 不可用不阻斷 artifact 落地。
            return ""

    sha = _run(["git", "rev-parse", "HEAD"]) or "unknown"
    status = _run(["git", "status", "--porcelain"])
    diff = _run(["git", "diff", "HEAD"])
    return {
        "git_sha": sha,
        "git_dirty": bool(status),
        "git_diff_sha256": hashlib.sha256(diff.encode("utf-8")).hexdigest() if diff else None,
    }


def index_entry(name: str, path: Path, schema_version: str) -> dict[str, Any]:
    return {
        "name": name,
        "path": str(path),
        "sha256": sha256_file(path),
        "byte_size": path.stat().st_size,
        "schema_version": schema_version,
    }


def write_manifest_and_index(
    run_dir: Path,
    *,
    mode: str,
    run_id: str,
    repo_root: Path,
    stats: dict[str, Any],
    errors: list[str],
    fill_realism_payload: Optional[dict[str, Any]] = None,
    d2_revalidation_payload: Optional[dict[str, Any]] = None,
    extra_artifacts: Optional[list[dict[str, Any]]] = None,
    runtime_host: Optional[str] = None,
    created_by_role: str = "E1",
) -> dict[str, Any]:
    """落 fill_realism.json / d2_revalidation.json（若有）+ manifest + index。

    extra_artifacts 用於把已落地的 raw/ 與 hbt/ 檔（在 caller 階段寫好）也納入
    sha256 index。
    """
    artifacts: list[dict[str, Any]] = list(extra_artifacts or [])
    written: dict[str, str] = {"run_dir": str(run_dir)}

    if fill_realism_payload is not None:
        fr_path = write_json(run_dir / "fill_realism.json", {**fill_realism_payload, "run_id": run_id})
        artifacts.append(index_entry("fill_realism.json", fr_path, FILL_REALISM_SCHEMA_VERSION))
        written["fill_realism"] = str(fr_path)

    if d2_revalidation_payload is not None:
        d2_path = write_json(run_dir / "d2_revalidation.json", {**d2_revalidation_payload, "run_id": run_id})
        artifacts.append(index_entry("d2_revalidation.json", d2_path, D2_REVALIDATION_SCHEMA_VERSION))
        written["d2_revalidation"] = str(d2_path)

    prov = git_provenance(repo_root)
    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "run_id": run_id,
        "program": "hftbacktest-fill-realism-harness",
        "mode": mode,
        # PIT 旗標：本 harness 全是 PIT snapshot 模擬（Tardis 免費單日），研究端
        # join 第一道防呆（mirror deribit_vol_axis）。
        "point_in_time": True,
        "retrospective": False,
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "created_by_role": created_by_role,
        "git_sha": prov["git_sha"],
        "git_dirty": prov["git_dirty"],
        "git_diff_sha256": prov["git_diff_sha256"],
        "runtime_host": runtime_host or socket.gethostname(),
        "timezone": "UTC",
        "runner_version": RUNNER_VERSION,
        # net 計算鐵則公示（reviewer 一眼可驗 rebate=0）。
        "maker_rebate_bps": 0.0,
        "policy": "offline_fill_realism_no_rebate_pit_append_only",
        "stats": stats,
        "errors": errors,
        "artifacts": artifacts,
    }
    manifest_path = write_json(run_dir / "manifest.json", manifest)
    artifacts_with_manifest = artifacts + [
        index_entry("manifest.json", manifest_path, MANIFEST_SCHEMA_VERSION)
    ]
    index_path = write_json(
        run_dir / "artifact_index.json",
        {
            "schema_version": ARTIFACT_INDEX_SCHEMA_VERSION,
            "run_id": run_id,
            "artifacts": artifacts_with_manifest,
        },
    )
    written["manifest"] = str(manifest_path)
    written["artifact_index"] = str(index_path)
    return {"written": written, "manifest": manifest}
