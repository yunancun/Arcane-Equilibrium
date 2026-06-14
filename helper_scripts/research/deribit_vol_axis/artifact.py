"""Deribit vol 軸 artifact 寫出（append-only run dir + manifest + sha256）。

MODULE_NOTE:
  模塊用途：把單輪採集結果落成 run dir artifact——dvol.jsonl（DVOL OHLC bar 行）/
    iv_surface.jsonl（option-level mark_iv 行）/ term_structure.jsonl（各到期 ATM
    IV）/ skew.jsonl（各到期 put/call skew）/ raw_instruments.jsonl（raw 保底）+
    manifest.json + artifact_index.json（含逐檔 sha256，mirror polymarket_axis
    write_run）+ 可選 duckdb parquet 鏡像（缺套件 skip 不阻斷）。
  依賴：標準庫；duckdb 延遲 import（可選）。
  硬邊界（mirror polymarket_axis）：
    - append-only（Polymarket 軸紀律 = 避 survivorship）：每次採集 = 新 run dir；
      run dir 已存在 → raise（禁回填、禁覆寫舊 snapshot——snapshot 是當時 IV
      surface 的唯一 point-in-time 來源，覆寫 = 不可逆毀證）。
    - 不建 PG 表：artifact-only（避 V### migration），唯一輸出 = filesystem。
    - artifact root 禁硬編碼：${OPENCLAW_DATA_DIR:-/tmp/openclaw}/
      deribit_vol_axis_runs/<run_id>/。
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
    COLLECTION_SET_VERSION,
    COLLECTOR_VERSION,
    DVOL_SCHEMA_VERSION,
    IV_SURFACE_SCHEMA_VERSION,
    MANIFEST_SCHEMA_VERSION,
    RAW_INSTRUMENT_SCHEMA_VERSION,
    SKEW_SCHEMA_VERSION,
    TERM_STRUCTURE_SCHEMA_VERSION,
)


def resolve_data_root() -> Path:
    base = os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw").strip() or "/tmp/openclaw"
    return Path(base)


def resolve_artifact_root(data_root: Optional[Path] = None) -> Path:
    root = Path(data_root) if data_root is not None else resolve_data_root()
    return root / "deribit_vol_axis_runs"


def default_run_id(mode: str, now: Optional[dt.datetime] = None) -> str:
    ts = (now or dt.datetime.now(dt.timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    return f"{mode}-{ts}"


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> Path:
    with open(path, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True, default=str))
            fh.write("\n")
    return path


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _git_provenance(repo_root: Path) -> dict[str, Any]:
    """git sha / dirty / diff 摘要（mirror polymarket_axis；git 不可用回 unknown 不阻斷）。"""
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


def write_run(
    *,
    mode: str,
    run_id: str,
    repo_root: Path,
    stats: dict[str, Any],
    errors: list[str],
    dvol_rows: Optional[list[dict[str, Any]]] = None,
    surface_rows: Optional[list[dict[str, Any]]] = None,
    term_structure_rows: Optional[list[dict[str, Any]]] = None,
    skew_rows: Optional[list[dict[str, Any]]] = None,
    raw_instruments: Optional[list[dict[str, Any]]] = None,
    artifact_root: Optional[Path] = None,
    runtime_host: Optional[str] = None,
    created_by_role: str = "E1",
    parquet_mirror: bool = True,
) -> dict[str, Any]:
    """單輪 run 落 artifact；回各檔路徑 + manifest 摘要。

    snapshot-only（本軸無 retrospective lane）：DVOL 窗口有界、surface 是當時
    快照，append-only 不回填更早歷史。
    """
    root = Path(artifact_root) if artifact_root is not None else resolve_artifact_root()
    run_dir = root / run_id
    # append-only 不變量：run dir 已存在即拒絕（exist_ok=False 是本鐵則的執行點；
    # 同名重跑必須換 run_id，舊 snapshot 不可覆寫）。
    root.mkdir(parents=True, exist_ok=True)
    run_dir.mkdir(parents=False, exist_ok=False)

    artifacts: list[dict[str, Any]] = []
    written: dict[str, str] = {"run_dir": str(run_dir)}

    dvol_path = write_jsonl(run_dir / "dvol.jsonl", dvol_rows or [])
    artifacts.append(_index_entry("dvol.jsonl", dvol_path, DVOL_SCHEMA_VERSION))
    written["dvol"] = str(dvol_path)

    surf_path = write_jsonl(run_dir / "iv_surface.jsonl", surface_rows or [])
    artifacts.append(_index_entry("iv_surface.jsonl", surf_path, IV_SURFACE_SCHEMA_VERSION))
    written["iv_surface"] = str(surf_path)

    term_path = write_jsonl(run_dir / "term_structure.jsonl", term_structure_rows or [])
    artifacts.append(_index_entry("term_structure.jsonl", term_path, TERM_STRUCTURE_SCHEMA_VERSION))
    written["term_structure"] = str(term_path)

    skew_path = write_jsonl(run_dir / "skew.jsonl", skew_rows or [])
    artifacts.append(_index_entry("skew.jsonl", skew_path, SKEW_SCHEMA_VERSION))
    written["skew"] = str(skew_path)

    raw_path = write_jsonl(run_dir / "raw_instruments.jsonl", raw_instruments or [])
    artifacts.append(_index_entry("raw_instruments.jsonl", raw_path, RAW_INSTRUMENT_SCHEMA_VERSION))
    written["raw_instruments"] = str(raw_path)

    mirror_result: dict[str, Any] = {"parquet_mirror": "disabled"}
    if parquet_mirror:
        mirror_result = mirror_jsonl_to_parquet(run_dir)

    prov = _git_provenance(repo_root)
    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "run_id": run_id,
        "program": "deribit-vol-axis-collector",
        "mode": mode,
        # point_in_time 旗標：本軸全是 PIT snapshot（無 retrospective lane），
        # 研究端 join 第一道防呆（Polymarket 軸紀律的 PIT 標記慣例）。
        "point_in_time": True,
        "retrospective": False,
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "created_by_role": created_by_role,
        "git_sha": prov["git_sha"],
        "git_dirty": prov["git_dirty"],
        "git_diff_sha256": prov["git_diff_sha256"],
        "runtime_host": runtime_host or socket.gethostname(),
        "collector_version": COLLECTOR_VERSION,
        "collection_set_version": COLLECTION_SET_VERSION,
        "stats": stats,
        "errors": errors,
        "parquet_mirror": mirror_result,
        "artifacts": artifacts,
    }
    manifest_path = run_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    artifacts_with_manifest = artifacts + [_index_entry("manifest.json", manifest_path, MANIFEST_SCHEMA_VERSION)]
    index_path = run_dir / "artifact_index.json"
    index_path.write_text(
        json.dumps(
            {
                "schema_version": "deribit.vol_axis_artifact_index.v0.1",
                "run_id": run_id,
                "artifacts": artifacts_with_manifest,
            },
            ensure_ascii=False, indent=2, sort_keys=True, default=str,
        ),
        encoding="utf-8",
    )
    written["manifest"] = str(manifest_path)
    written["artifact_index"] = str(index_path)
    return {"written": written, "manifest": manifest}


def mirror_jsonl_to_parquet(run_dir: Path) -> dict[str, Any]:
    """duckdb 把 run dir 內各 JSONL 鏡像成 parquet（可選便利層）。

    非阻斷契約（mirror polymarket_axis）：JSONL 才是 SoT，parquet 只是研究便利
    鏡像；缺套件 / IO 錯 / 壞行任何失敗都收斂成結構化回報，絕不 raise——否則
    cron 採集收尾會因可選層崩掉整輪 snapshot。逐檔隔離 + 原子寫（.tmp+os.replace）。
    """
    try:
        import duckdb  # 延遲 import：Mac dev 常無，Linux runtime 已驗可用。
    except ImportError:
        return {"parquet_mirror": "skipped", "reason": "duckdb_not_available"}

    files_ok: list[str] = []
    files_failed: list[str] = []
    try:
        con = duckdb.connect()
        try:
            for jsonl_path in sorted(Path(run_dir).glob("*.jsonl")):
                parquet_path = jsonl_path.with_suffix(".parquet")
                tmp_path = jsonl_path.with_suffix(".parquet.tmp")
                try:
                    # 寫 tmp + os.replace 原子落位：轉換中途失敗最終路徑絕不出現
                    # 0-byte/半寫殘檔（mirror polymarket_axis P-1 教訓）。
                    rel = con.read_json(str(jsonl_path), format="newline_delimited")
                    rel.write_parquet(str(tmp_path))
                    os.replace(tmp_path, parquet_path)
                    files_ok.append(jsonl_path.name)
                except Exception:  # noqa: BLE001 —— 逐檔隔離（非阻斷契約）。
                    files_failed.append(jsonl_path.name)
                    try:
                        tmp_path.unlink(missing_ok=True)
                    except OSError:
                        pass
        finally:
            con.close()
    except Exception as exc:  # noqa: BLE001 —— 鏡像層級失敗也不傳播。
        return {"parquet_mirror": "failed", "reason": f"{type(exc).__name__}: {exc}"}

    if files_failed and files_ok:
        status = "partial"
    elif files_failed:
        status = "failed"
    else:
        status = "ok"
    return {"parquet_mirror": status, "files_ok": files_ok, "files_failed": files_failed}
