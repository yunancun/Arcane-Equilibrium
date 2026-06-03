"""AEG-S2 breadth ladder artifact 落地 — breadth_ladder.csv/.parquet + summary + manifest。

MODULE_NOTE:
  模塊用途：把 ladder 產的 rows + summary 落成跨平台 artifact（mirror FND-2 artifact.py）：
    (1) breadth_ladder.csv（純標準庫，SoT）+ breadth_ladder.parquet（duckdb 鏡像，缺套件
        skip）；(2) breadth_ladder_summary.json（含 monotonicity / verdict_hint /
        delisted_proof_total）；(3) manifest.json（AEG-S0 §1.4 子集 + git 來源 +
        fnd2_universe_id/fnd2_run_id provenance 鏈 + child digests）；(4)
        artifact_index.json（每檔 path/sha256/byte_size/row_count/schema_version）。
  主要函數：``resolve_artifact_root`` / ``write_ladder_csv`` / ``mirror_parquet`` /
    ``build_manifest`` / ``write_all``。
  硬邊界（mirror FND-2 紅線，PA §5 + D-3）：
    - **artifact root 禁硬編碼 /tmp/openclaw**（跨平台 feedback_cross_platform）：root =
      ``${OPENCLAW_DATA_DIR:-/tmp/openclaw}/alpha_history_runs/<run_id>/``。
    - 絕不 import 任何 ``control_api_v1/app/`` runtime 模組（artifact 紅線同 FND-2 /
      gate_b_artifact）。0 DB write（只寫本地檔系統）。
    - parquet 鏡像非阻斷（缺 duckdb 時 skip，csv 為 SoT）；用 read_csv().write_parquet()
      非 COPY-TO-?（gate_b_artifact 已證 duckdb COPY TO 不支援 ? bind）。
  依賴：duckdb（延遲 import，可選）+ 標準庫。
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
    BREADTH_LADDER_VERSION,
    LADDER_SCHEMA_VERSION,
    MANIFEST_SCHEMA_VERSION,
)
from .ladder import LADDER_COLUMNS

logger = logging.getLogger(__name__)


def resolve_artifact_root() -> Path:
    """解析 artifact 根目錄（跨平台，禁硬編碼；mirror FND-2 resolve_artifact_root）。

    為什麼 OPENCLAW_DATA_DIR：feedback_cross_platform——不可把 /tmp/openclaw 寫死
    （Mac 與 Linux 資料目錄不同）。與 FND-2 同 ``alpha_history_runs`` 根（S0 §1.2）。
    """
    base = os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw").strip() or "/tmp/openclaw"
    return Path(base) / "alpha_history_runs"


def _csv_cell(value: Any) -> str:
    """row dict 值 → CSV cell（None→空、bool→true/false、list→JSON）。"""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple)):
        return json.dumps(list(value), ensure_ascii=False)
    return str(value)


def write_ladder_csv(rows: list, path: Path) -> Path:
    """寫 breadth_ladder.csv（凍結欄序 LADDER_COLUMNS，純標準庫，SoT）。"""
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(list(LADDER_COLUMNS))
        for r in rows:  # rows 已在 ladder 依 (monotonicity_rank, tier 名) 排序
            writer.writerow([_csv_cell(r.get(col)) for col in LADDER_COLUMNS])
    return path


def mirror_parquet(csv_path: Path, parquet_path: Path) -> dict:
    """用 duckdb 把 breadth_ladder.csv 鏡像成 .parquet（缺套件 skip，非阻斷）。

    為什麼可選 skip：duckdb Mac dev 不一定裝；csv 才是 SoT，parquet 是下游（(c)
    robustness matrix）便利鏡像。任何失敗都吞並回報，絕不 raise（mirror FND-2）。
    為什麼 all_varchar：避免 duckdb 對數值欄做型別推斷而與 csv SoT 不一致。
    """
    try:
        import duckdb  # 延遲 import
    except ImportError:
        return {"parquet_mirror": "skipped", "reason": "duckdb_not_available"}
    try:
        con = duckdb.connect(database=":memory:")
        try:
            con.read_csv(str(csv_path), all_varchar=True).write_parquet(str(parquet_path))
        finally:
            con.close()
        return {"parquet_mirror": "ok"}
    except Exception as exc:  # noqa: BLE001 - 鏡像非阻斷（csv 為 SoT）
        logger.warning("breadth_ladder.parquet 鏡像失敗（不阻斷，csv 為 SoT）: %s", exc)
        return {"parquet_mirror": "failed", "reason": f"mirror_failed:{exc}"}


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path: Path, payload: dict) -> Path:
    # sort_keys=True：determinism（同 payload 同 bytes → 同 sha256；mirror FND-2）。
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    return path


def _git_provenance(repo_root: Path) -> dict:
    """採集 git 來源（manifest 對帳）。失敗回 unknown，不阻斷（mirror FND-2）。"""
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
    ladder_id: str,
    candidate_id: str,
    fnd2_universe_id: str,
    fnd2_run_id: str,
    source_tables: list,
    artifacts: list,
    session_id: Optional[str],
    created_by_role: str,
    repo_root: Path,
    runtime_host: str,
) -> dict:
    """組 manifest.json（AEG-S0 §1.4 子集 + provenance 鏈到 FND-2 universe artifact）。"""
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
        "timezone": "UTC",
        "ladder_id": ladder_id,
        "breadth_ladder_version": BREADTH_LADDER_VERSION,
        "candidate_id": candidate_id,
        # provenance 鏈到 FND-2 universe artifact（S0 §1.4）。
        "fnd2_universe_id": fnd2_universe_id,
        "fnd2_run_id": fnd2_run_id,
        "source_tables": list(source_tables),
        "provenance_mode": "artifact_manifest",
        "breadth_ladder_schema_version": LADDER_SCHEMA_VERSION,
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
    candidate_id: str,
    fnd2_universe_id: str,
    fnd2_run_id: str,
    source_tables: list,
    repo_root: Path,
    runtime_host: str,
    session_id: Optional[str] = None,
    created_by_role: str = "E1",
    artifact_root: Optional[Path] = None,
) -> dict:
    """寫全 artifact（csv/parquet/summary/manifest/index），回 paths + 摘要。

    順序：csv → parquet 鏡像 → summary.json → 收集 child digests → manifest.json →
    artifact_index.json（mirror FND-2 write_all）。
    """
    root = artifact_root if artifact_root is not None else resolve_artifact_root()
    run_dir = Path(root) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    ladder_id = summary["ladder_id"]

    # 1) breadth_ladder.csv（SoT）
    csv_path = run_dir / "breadth_ladder.csv"
    write_ladder_csv(rows, csv_path)

    # 2) breadth_ladder.parquet（可選鏡像）
    parquet_path = run_dir / "breadth_ladder.parquet"
    parquet_result = mirror_parquet(csv_path, parquet_path)

    # 3) breadth_ladder_summary.json
    summary_path = run_dir / "breadth_ladder_summary.json"
    write_json(summary_path, summary)

    # 4) artifact_index（先收 child，最後寫自身）
    index_entries = [
        _index_entry("breadth_ladder.csv", csv_path, len(rows), LADDER_SCHEMA_VERSION),
        _index_entry("breadth_ladder_summary.json", summary_path, None,
                     "aeg.breadth_ladder_summary.v0.1"),
    ]
    if parquet_result.get("parquet_mirror") == "ok" and parquet_path.exists():
        index_entries.append(
            _index_entry("breadth_ladder.parquet", parquet_path, len(rows), LADDER_SCHEMA_VERSION)
        )

    # 5) manifest.json（artifacts 引用 child digests + provenance 鏈）
    manifest = build_manifest(
        run_id=run_id,
        summary=summary,
        ladder_id=ladder_id,
        candidate_id=candidate_id,
        fnd2_universe_id=fnd2_universe_id,
        fnd2_run_id=fnd2_run_id,
        source_tables=source_tables,
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
    write_json(index_path, {"run_id": run_id, "ladder_id": ladder_id, "artifacts": index_entries})

    return {
        "run_dir": str(run_dir),
        "breadth_ladder_csv": str(csv_path),
        "breadth_ladder_parquet": (str(parquet_path)
                                   if parquet_result.get("parquet_mirror") == "ok" else None),
        "breadth_ladder_summary": str(summary_path),
        "manifest": str(manifest_path),
        "artifact_index": str(index_path),
        "parquet_result": parquet_result,
        "ladder_id": ladder_id,
    }


__all__ = [
    "resolve_artifact_root",
    "write_ladder_csv",
    "mirror_parquet",
    "build_manifest",
    "write_all",
    "write_json",
]
