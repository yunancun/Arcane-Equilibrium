"""
MODULE_NOTE
模塊用途：P0-1c boot/repo SHA 可觀測面（control API 側）。startup 時 append 一行
  boot 紀錄到 OPENCLAW_DATA_DIR/boot_history.jsonl（與 Rust 引擎共檔，以
  component 欄位區分寫入者），並向 /api/v1/healthz 提供 boot_sha（進程啟動時
  凍結）與 repo_head（請求時讀取，TTL 緩存）兩欄位 —— 兩值不等即代表運行進程
  的代碼世代落後 checkout（07-03 冷審計 P0-1 的「重啟未 rebuild / 未重啟」盲區）。
主要函數：build_boot_record / append_boot_record / boot_identity / resolve_repo_head。
依賴：僅標準庫（subprocess / json / os / threading / datetime）。
硬邊界：純可觀測性面 —— git 缺席或任何失敗一律 fallback "unknown"，絕不拋出
  阻斷 startup；寫檔失敗由呼叫端 fail-open 記 warning。不觸碰交易 / 授權路徑。
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# boot 紀錄檔名（append-only JSONL；與 Rust 引擎 boot_observability.rs 同名常量）。
BOOT_HISTORY_FILENAME = "boot_history.jsonl"

# git 子進程超時秒數：可觀測性查詢不得拖慢 healthz / startup。
_GIT_TIMEOUT_SECONDS = 3.0

# repo_head 請求側 TTL 緩存秒數：healthz 是監控輪詢面，不能每次 fork git。
_REPO_HEAD_TTL_SECONDS = 60.0

_lock = threading.Lock()

# 進程級狀態：boot_sha 首次解析後凍結（= 進程啟動時的 repo HEAD）；
# repo_head 帶 TTL 緩存（= 當下磁盤 checkout 的 HEAD）。
_state: dict[str, Any] = {
    "boot_sha": None,          # 凍結值；None = 尚未解析
    "repo_head": "unknown",    # TTL 緩存值
    "repo_head_expires_at": 0.0,
}


def _git_head_uncached() -> str:
    """以 git rev-parse HEAD 讀當前 checkout 的 SHA；任何失敗回 "unknown"。

    為什麼用本檔所在目錄當 cwd：git 會自行向上尋找 repo root，避免硬編碼
    /home/ncyu、/Users/ncyu 等機器路徑（跨平台合規）。
    為什麼吞掉所有異常：git 不在 PATH（FileNotFoundError）、非 repo、超時等
    都不得讓可觀測性面拋錯阻斷 startup / healthz。
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(Path(__file__).resolve().parent),
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_SECONDS,
        )
        if result.returncode != 0:
            return "unknown"
        sha = result.stdout.strip()
        return sha if sha else "unknown"
    except Exception:
        return "unknown"


def resolve_repo_head() -> str:
    """回傳當前 checkout 的 HEAD SHA（TTL 緩存；失敗 "unknown"）。"""
    now = time.monotonic()
    with _lock:
        if now < _state["repo_head_expires_at"]:
            return _state["repo_head"]
    sha = _git_head_uncached()
    with _lock:
        _state["repo_head"] = sha
        _state["repo_head_expires_at"] = now + _REPO_HEAD_TTL_SECONDS
        return sha


def boot_identity() -> dict[str, str]:
    """回傳 {"boot_sha": 進程啟動時凍結的 SHA, "repo_head": 當前 checkout SHA}。

    不變量：boot_sha 首次解析後在進程壽命內不再改變 —— 它代表「本進程載入的
    代碼世代」；與 repo_head 不等即為 drift 信號（進程未跟上 checkout）。
    """
    with _lock:
        frozen = _state["boot_sha"]
    if frozen is None:
        resolved = _git_head_uncached()
        with _lock:
            # 併發首呼叫防重：僅第一個寫入者凍結。
            if _state["boot_sha"] is None:
                _state["boot_sha"] = resolved
            frozen = _state["boot_sha"]
    return {"boot_sha": frozen, "repo_head": resolve_repo_head()}


def _resolve_workers() -> int | None:
    """best-effort 解析 uvicorn worker 數（OPENCLAW_API_WORKERS / WEB_CONCURRENCY）。

    restart_all.sh 目前不把 worker 數轉發進 worker 進程 env，故此欄位可能為
    None —— 誠實記 null 而非猜測。
    """
    for env_name in ("OPENCLAW_API_WORKERS", "WEB_CONCURRENCY"):
        raw = os.environ.get(env_name)
        if raw:
            try:
                return int(raw)
            except ValueError:
                continue
    return None


def resolve_data_dir() -> Path:
    """OPENCLAW_DATA_DIR 解析（默認值沿用現行代碼慣例 /tmp/openclaw）。"""
    return Path(os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw"))


def build_boot_record() -> dict[str, Any]:
    """組出本 worker 進程的單行 boot 紀錄（純函數，schema 唯一定義點）。

    欄位：component / boot_ts / repo_head / pid / workers。
    repo_head 用凍結的 boot_sha（= 進程啟動世代），非請求時值。
    """
    return {
        "component": "control_api",
        "boot_ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "repo_head": boot_identity()["boot_sha"],
        "pid": os.getpid(),
        "workers": _resolve_workers(),
    }


def append_boot_record(data_dir: Path | str | None = None) -> Path:
    """把本進程 boot 紀錄 append 到 data_dir/boot_history.jsonl，回傳寫入路徑。

    為什麼 append-only：boot 歷史是審計證據，覆寫會毀掉「重啟未 rebuild /
    未重啟」類事故的重建能力。uvicorn 多 worker 下每個 worker 各寫一行
    （pid 可區分）；單行 O_APPEND 寫入對併發 append 安全。
    IO 錯誤上拋，由呼叫端（startup event）fail-open 記 warning。
    """
    base = Path(data_dir) if data_dir is not None else resolve_data_dir()
    base.mkdir(parents=True, exist_ok=True)
    path = base / BOOT_HISTORY_FILENAME
    line = json.dumps(build_boot_record(), ensure_ascii=False)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    return path
