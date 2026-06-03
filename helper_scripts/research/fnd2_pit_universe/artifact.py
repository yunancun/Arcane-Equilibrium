"""FND-2 artifact 落地 — universe.csv/.parquet + summary.json + manifest.json + index。

MODULE_NOTE:
  模塊用途：把 builder 產的 universe rows + summary 落成跨平台 artifact：
    (1) universe.csv（純標準庫，SoT）+ universe.parquet（duckdb 鏡像，缺套件 skip）；
    (2) universe_summary.json（含 delisted_proof_count / survivor_rejection_status /
        seed_regression）；(3) manifest.json（AEG-S0 §1.4 子集 + universe_sources PIT
        gate + git 來源 + child digests）；(4) artifact_index.json（每檔 path/sha256/
        byte_size/row_count/schema_version）。
  主要函數：``resolve_artifact_root`` / ``write_universe_csv`` / ``mirror_parquet`` /
    ``build_manifest`` / ``write_all``。
  硬邊界：
    - **artifact root 禁硬編碼 /tmp/openclaw**（跨平台 feedback_cross_platform）：
      root = ``${OPENCLAW_DATA_DIR:-/tmp/openclaw}/alpha_history_runs/<run_id>/``。
    - 絕不 import 任何 ``control_api_v1/app/`` runtime 模組（artifact 紅線同
      gate_b_artifact）。0 DB write（只寫本地檔系統）。
    - parquet 鏡像非阻斷（缺 duckdb/pyarrow 時 skip，csv 為 SoT）。
  依賴：duckdb/pyarrow（延遲 import，可選）+ 標準庫。
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
from typing import Any, Optional

from . import (
    BUILDER_VERSION,
    MANIFEST_SCHEMA_VERSION,
    QUERY_SCHEMA_VERSION,
    UNIVERSE_SCHEMA_VERSION,
)
from .builder import UNIVERSE_COLUMNS

logger = logging.getLogger(__name__)


def resolve_artifact_root() -> Path:
    """解析 artifact 根目錄（跨平台，禁硬編碼）。

    為什麼 OPENCLAW_DATA_DIR：feedback_cross_platform——不可把 /tmp/openclaw 寫死
    （Mac 與 Linux 資料目錄不同，operator 可改）。預設 fallback 僅在 env 未設時生效。
    """
    base = os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw").strip() or "/tmp/openclaw"
    return Path(base) / "alpha_history_runs"


def _csv_cell(value: Any) -> str:
    """row dict 值 → CSV cell。list（cohort_ids/statuses_seen）→ JSON array 字串。"""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple)):
        return json.dumps(list(value), ensure_ascii=False)
    return str(value)


def write_universe_csv(rows: list, path: Path) -> Path:
    """寫 universe.csv（凍結欄序 UNIVERSE_COLUMNS，純標準庫，SoT）。"""
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(list(UNIVERSE_COLUMNS))
        for r in rows:  # rows 已在 builder 依 symbol 排序
            writer.writerow([_csv_cell(r.get(col)) for col in UNIVERSE_COLUMNS])
    return path


def mirror_parquet(csv_path: Path, parquet_path: Path) -> dict:
    """用 duckdb 把 universe.csv 鏡像成 universe.parquet（缺套件 skip，非阻斷）。

    為什麼可選 skip：duckdb/pyarrow Mac dev 不一定裝；csv 才是 SoT，parquet 是下游
    （breadth/robustness runner）便利鏡像。任何失敗都吞並回報，絕不 raise（mirror
    gate_b_artifact 非阻斷紅線）。
    為什麼用關聯式 read_csv().write_parquet() 而非 COPY-TO-?：duckdb COPY TO 不支援 ?
    bind（gate_b_artifact 已證 Linux 1.5.1 / Mac 1.5.3 皆此限制）。
    """
    try:
        import duckdb  # 延遲 import
    except ImportError:
        return {"parquet_mirror": "skipped", "reason": "duckdb_not_available"}
    try:
        con = duckdb.connect(database=":memory:")
        try:
            # all_varchar：避免 duckdb 對 cohort_ids/statuses_seen JSON 字串或數值欄
            # 做型別推斷而與 csv SoT 不一致；parquet 純鏡像，型別以 csv 文本為準。
            con.read_csv(str(csv_path), all_varchar=True).write_parquet(str(parquet_path))
        finally:
            con.close()
        return {"parquet_mirror": "ok"}
    except Exception as exc:  # noqa: BLE001 - 鏡像非阻斷（csv 為 SoT）
        logger.warning("fnd2 universe.parquet 鏡像失敗（不阻斷，csv 為 SoT）: %s", exc)
        return {"parquet_mirror": "failed", "reason": f"mirror_failed:{exc}"}


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path: Path, payload: dict) -> Path:
    # sort_keys=True：determinism（同 payload 同 bytes → 同 sha256，T4 / T10）。
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    return path


def _git_provenance(repo_root: Path) -> dict:
    """採集 git 來源（manifest 對帳）。失敗回 unknown，不阻斷。"""
    def _run(args):
        try:
            return subprocess.run(
                args, cwd=str(repo_root), capture_output=True, text=True, timeout=10,
            ).stdout.strip()
        except Exception:
            return ""

    git_sha = _run(["git", "rev-parse", "HEAD"]) or "unknown"
    status = _run(["git", "status", "--porcelain"])
    git_dirty = bool(status)
    diff = _run(["git", "diff", "HEAD"])
    git_diff_sha256 = hashlib.sha256(diff.encode("utf-8")).hexdigest() if diff else None
    return {"git_sha": git_sha, "git_dirty": git_dirty, "git_diff_sha256": git_diff_sha256}


def build_manifest(
    *,
    run_id: str,
    summary: dict,
    universe_id: str,
    window: Any,
    symbol_count: int,
    universe_sources: list,
    artifacts: list,
    session_id: Optional[str],
    created_by_role: str,
    repo_root: Path,
    runtime_host: str,
) -> dict:
    """組 manifest.json（AEG-S0 §1.4 子集 + universe_sources PIT gate）。"""
    prov = _git_provenance(repo_root)
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "run_id": run_id,
        "program": "AEG",
        "session_id": session_id,
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "created_by_role": created_by_role,
        "git_sha": prov["git_sha"],
        "git_dirty": prov["git_dirty"],
        "git_diff_sha256": prov["git_diff_sha256"],
        "runtime_host": runtime_host,
        "window_start_utc": summary["window_start_utc"],
        "window_end_utc": summary["window_end_utc"],
        "asof_utc": summary["asof_utc"],
        "closed_bar_cutoff_utc": summary["closed_bar_cutoff_utc"],
        "timezone": "UTC",
        "universe_id": universe_id,
        # PIT-source gate（contract §5）：必含 symbol_universe_snapshots。
        "universe_sources": list(universe_sources),
        "symbol_count": symbol_count,
        "source_tables": list(universe_sources),
        "provenance_mode": "artifact_manifest",
        "builder_version": BUILDER_VERSION,
        "query_schema_version": QUERY_SCHEMA_VERSION,
        "artifacts": list(artifacts),
    }


def _index_entry(name: str, path: Path, row_count: Optional[int], schema_version: str) -> dict:
    return {
        "name": name,
        "path": str(path),
        "sha256": _sha256_file(path),
        "byte_size": path.stat().st_size,
        "row_count": row_count,
        "schema_version": schema_version,
    }


def write_all(
    rows: list,
    summary: dict,
    *,
    run_id: str,
    window: Any,
    universe_sources: list,
    repo_root: Path,
    runtime_host: str,
    session_id: Optional[str] = None,
    created_by_role: str = "E1",
    artifact_root: Optional[Path] = None,
) -> dict:
    """寫全 artifact（csv/parquet/summary/manifest/index），回 paths + 摘要。

    順序：csv → parquet 鏡像 → summary.json → 收集 child digests → manifest.json →
    artifact_index.json（含上述全檔 + 自身回填）。
    """
    root = artifact_root if artifact_root is not None else resolve_artifact_root()
    run_dir = Path(root) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    universe_id = summary["universe_id"]

    # 1) universe.csv（SoT）
    csv_path = run_dir / "universe.csv"
    write_universe_csv(rows, csv_path)

    # 2) universe.parquet（可選鏡像）
    parquet_path = run_dir / "universe.parquet"
    parquet_result = mirror_parquet(csv_path, parquet_path)

    # 3) universe_summary.json
    summary_path = run_dir / "universe_summary.json"
    write_json(summary_path, summary)

    # 4) artifact_index（先收 child，最後寫自身）
    index_entries = [
        _index_entry("universe.csv", csv_path, len(rows), UNIVERSE_SCHEMA_VERSION),
        _index_entry("universe_summary.json", summary_path, None, "fnd2.summary.v0.1"),
    ]
    if parquet_result.get("parquet_mirror") == "ok" and parquet_path.exists():
        index_entries.append(
            _index_entry("universe.parquet", parquet_path, len(rows), UNIVERSE_SCHEMA_VERSION)
        )

    # 5) manifest.json（artifacts 引用 child digests）
    manifest = build_manifest(
        run_id=run_id,
        summary=summary,
        universe_id=universe_id,
        window=window,
        symbol_count=summary["included_count"],
        universe_sources=universe_sources,
        artifacts=index_entries,
        session_id=session_id,
        created_by_role=created_by_role,
        repo_root=repo_root,
        runtime_host=runtime_host,
    )
    manifest_path = run_dir / "manifest.json"
    write_json(manifest_path, manifest)
    index_entries.append(
        _index_entry("manifest.json", manifest_path, None, MANIFEST_SCHEMA_VERSION)
    )

    # 6) artifact_index.json（最後寫，含上述全部）
    index_path = run_dir / "artifact_index.json"
    write_json(index_path, {"run_id": run_id, "universe_id": universe_id, "artifacts": index_entries})

    return {
        "run_dir": str(run_dir),
        "universe_csv": str(csv_path),
        "universe_parquet": (str(parquet_path) if parquet_result.get("parquet_mirror") == "ok" else None),
        "universe_summary": str(summary_path),
        "manifest": str(manifest_path),
        "artifact_index": str(index_path),
        "parquet_result": parquet_result,
        "universe_id": universe_id,
    }


__all__ = [
    "resolve_artifact_root",
    "write_universe_csv",
    "mirror_parquet",
    "build_manifest",
    "write_all",
    "write_json",
]
