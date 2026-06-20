"""Polymarket 軸 artifact 寫出（append-only run dir + manifest + sha256）。

MODULE_NOTE:
  模塊用途：把單輪採集結果落成 run dir artifact——snapshots.jsonl（market-level
    行）/ raw_events.jsonl / raw_markets.jsonl（raw 保底）或 prices_history.jsonl
    （retrospective lane）+ manifest.json + artifact_index.json（含逐檔 sha256，
    照 aeg_s3_funding_revive.artifact.write_all 形）+ 可選 duckdb parquet 鏡像
    （缺套件 skip 不阻斷，照 gate_b mirror_jsonl_to_parquet 慣例）。
  依賴：標準庫；duckdb 延遲 import（可選）。
  硬邊界：
    - append-only（QC memo §2 鐵則）：每次採集 = 新 run dir；run dir 已存在 →
      raise（禁回填、禁覆寫舊 snapshot——snapshot 是 volume/liquidity/priceChange
      的唯一 point-in-time 來源，覆寫 = 不可逆毀證）。
    - lane 隔離：snapshot lane 與 retrospective lane 檔名集合互斥，由
      write_run 按 lane 分派；manifest 記 lane + retrospective 旗標，研究端
      join 必須按 lane 過濾。
    - artifact root 禁硬編碼：${OPENCLAW_DATA_DIR:-/tmp/openclaw}/
      polymarket_axis_runs/<run_id>/。
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import shutil
import socket
import subprocess
from pathlib import Path
from typing import Any, Optional

from . import (
    COLLECTOR_VERSION,
    LANE_RETROSPECTIVE,
    LANE_SNAPSHOT,
    MANIFEST_SCHEMA_VERSION,
    PRICES_HISTORY_SCHEMA_VERSION,
    QUERY_SET_VERSION,
    RAW_EVENT_SCHEMA_VERSION,
    RAW_MARKET_SCHEMA_VERSION,
    SNAPSHOT_SCHEMA_VERSION,
    UPSTREAM_ATTRIBUTION,
)


def resolve_data_root() -> Path:
    base = os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw").strip() or "/tmp/openclaw"
    return Path(base)


def resolve_artifact_root(data_root: Optional[Path] = None) -> Path:
    root = Path(data_root) if data_root is not None else resolve_data_root()
    return root / "polymarket_axis_runs"


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
    """git sha / dirty / diff 摘要（照 aeg_s3 同形；git 不可用回 unknown 不阻斷）。"""
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
    lane: str,
    mode: str,
    run_id: str,
    repo_root: Path,
    stats: dict[str, Any],
    errors: list[str],
    snapshot_rows: Optional[list[dict[str, Any]]] = None,
    raw_events: Optional[list[dict[str, Any]]] = None,
    raw_markets: Optional[list[dict[str, Any]]] = None,
    prices_history_rows: Optional[list[dict[str, Any]]] = None,
    artifact_root: Optional[Path] = None,
    runtime_host: Optional[str] = None,
    created_by_role: str = "E1",
    parquet_mirror: bool = True,
    query_set_version: str = QUERY_SET_VERSION,
) -> dict[str, Any]:
    """單輪 run 落 artifact；回各檔路徑 + manifest 摘要。

    lane 分派（互斥，違反 = 程式錯誤直接 raise）：
      - snapshot：snapshots.jsonl + raw_events.jsonl + raw_markets.jsonl。
      - retrospective：prices_history.jsonl（不得帶 snapshot 檔——永不冒充
        「當時採集」）。
    """
    if lane == LANE_SNAPSHOT:
        if prices_history_rows is not None:
            raise ValueError("snapshot lane must not carry prices_history rows")
    elif lane == LANE_RETROSPECTIVE:
        if snapshot_rows is not None or raw_events is not None or raw_markets is not None:
            raise ValueError("retrospective lane must not carry snapshot-lane files")
    else:
        raise ValueError(f"unknown lane: {lane!r}")

    root = Path(artifact_root) if artifact_root is not None else resolve_artifact_root()
    run_dir = root / run_id
    # append-only 不變量：run dir 已存在即拒絕（exist_ok=False 是本鐵則的執行點；
    # 同名重跑必須換 run_id，舊 snapshot 不可覆寫）。
    root.mkdir(parents=True, exist_ok=True)
    run_dir.mkdir(parents=False, exist_ok=False)

    artifacts: list[dict[str, Any]] = []
    written: dict[str, str] = {"run_dir": str(run_dir)}

    if lane == LANE_SNAPSHOT:
        snap_path = write_jsonl(run_dir / "snapshots.jsonl", snapshot_rows or [])
        artifacts.append(_index_entry("snapshots.jsonl", snap_path, SNAPSHOT_SCHEMA_VERSION))
        written["snapshots"] = str(snap_path)
        raw_ev_path = write_jsonl(run_dir / "raw_events.jsonl", raw_events or [])
        artifacts.append(_index_entry("raw_events.jsonl", raw_ev_path, RAW_EVENT_SCHEMA_VERSION))
        written["raw_events"] = str(raw_ev_path)
        raw_mk_path = write_jsonl(run_dir / "raw_markets.jsonl", raw_markets or [])
        artifacts.append(_index_entry("raw_markets.jsonl", raw_mk_path, RAW_MARKET_SCHEMA_VERSION))
        written["raw_markets"] = str(raw_mk_path)
    else:
        hist_path = write_jsonl(run_dir / "prices_history.jsonl", prices_history_rows or [])
        artifacts.append(_index_entry("prices_history.jsonl", hist_path, PRICES_HISTORY_SCHEMA_VERSION))
        written["prices_history"] = str(hist_path)

    mirror_result: dict[str, Any] = {"parquet_mirror": "disabled"}
    if parquet_mirror:
        mirror_result = mirror_jsonl_to_parquet(run_dir)

    prov = _git_provenance(repo_root)
    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "run_id": run_id,
        "program": "polymarket-axis-collector",
        "lane": lane,
        "mode": mode,
        # retrospective 旗標冗餘並列 lane：研究端 join 的第一道防呆
        #（QC memo §2：補抓另開 run 標 retrospective=true）。
        "retrospective": lane == LANE_RETROSPECTIVE,
        "point_in_time": lane == LANE_SNAPSHOT,
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "created_by_role": created_by_role,
        "git_sha": prov["git_sha"],
        "git_dirty": prov["git_dirty"],
        "git_diff_sha256": prov["git_diff_sha256"],
        "runtime_host": runtime_host or socket.gethostname(),
        "collector_version": COLLECTOR_VERSION,
        "query_set_version": query_set_version,
        "upstream_attribution": UPSTREAM_ATTRIBUTION,
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
                "schema_version": "polymarket.axis_artifact_index.v0.1",
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

    非阻斷契約（照 gate_b 同款硬邊界）：JSONL 才是 SoT，parquet 只是研究便利
    鏡像；缺套件 / IO 錯 / 壞行任何失敗都收斂成結構化回報，絕不 raise——
    否則 cron 採集收尾會因可選層崩掉整輪 snapshot。逐檔隔離：失敗者記
    files_failed，成功者照常產出。
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
                    # read_json_auto 關聯式 API（COPY TO 不支援 ? bind，gate_b 教訓）。
                    # P-1（E2 2026-06-11）：寫 tmp + os.replace 原子落位——轉換中途失敗
                    # 最終路徑絕不出現 0-byte/半寫殘檔（殘檔會被誤認有效 parquet 輸出；
                    # 2026-06-11 真 smoke 實測 raw_events.jsonl 轉換失敗曾留 0-byte 殘）。
                    rel = con.read_json(str(jsonl_path), format="newline_delimited")
                    rel.write_parquet(str(tmp_path))
                    os.replace(tmp_path, parquet_path)
                    files_ok.append(jsonl_path.name)
                except Exception:  # noqa: BLE001 —— 逐檔隔離（非阻斷契約）。
                    files_failed.append(jsonl_path.name)
                    # 只清 tmp 殘檔；最終路徑在 replace 前從未被觸碰。
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


def mirror_run_dir(run_dir: Path, mirror_root: Path) -> dict[str, Any]:
    """把已完成 run dir append-only 複製到 durable mirror root。

    為什麼不是覆寫：Polymarket lead-lag 需要跨多個 collector run 累積樣本；
    runtime `/tmp` 被清理後若只有最新 run，sample gate 會退回 0。mirror 是
    append-only evidence cache，保留既有 run_id，不修補、不覆蓋。
    """
    src = Path(run_dir)
    root = Path(mirror_root)
    dest = root / src.name
    if not src.is_dir():
        return {
            "mirror_status": "missing_source",
            "source_run_dir": str(src),
            "mirror_run_dir": str(dest),
        }
    if dest.exists():
        return {
            "mirror_status": "exists",
            "source_run_dir": str(src),
            "mirror_run_dir": str(dest),
        }
    root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dest, symlinks=False)
    return {
        "mirror_status": "copied",
        "source_run_dir": str(src),
        "mirror_run_dir": str(dest),
    }
