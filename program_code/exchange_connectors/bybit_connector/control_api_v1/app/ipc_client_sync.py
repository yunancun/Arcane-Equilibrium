"""Synchronous IPC helper split from ``ipc_client``.
自 ``ipc_client`` 抽出的同步 IPC helper。
"""

from __future__ import annotations

import hashlib
import hmac as _hmac_lib
import logging
import os
import time

from . import json_fast as json
from .secret_runtime import get_secret_value

logger = logging.getLogger(__name__)

DEFAULT_SOCKET_PATH = "/tmp/openclaw/engine.sock"
SOCKET_ENV_VAR = "OPENCLAW_IPC_SOCKET"


def sync_ipc_call(
    method: str,
    params: dict,
    timeout: float = 3.0,
    socket_path: str | None = None,
) -> dict:
    """
    Synchronous fire-and-best-effort IPC call to the Rust engine.
    Uses a fresh socket connection per call — suitable only for low-frequency
    control-plane operations (e.g. mode sync on config change), NOT for
    hot-path per-tick calls.

    Returns the JSON-RPC result dict on success, or raises on error.
    Failures are logged but never propagate to callers — this is a best-effort
    sync from Python config to Rust engine state. If the engine is not running,
    the mode will sync on next engine startup via snapshot read.

    同步的盡力而為 IPC 調用 Rust 引擎。
    每次調用使用新的 socket 連接 — 僅適用於低頻控制面操作（如模式同步），
    不適用於高頻 per-tick 調用。

    成功時返回 JSON-RPC result dict，失敗時拋出異常。
    失敗只記錄日誌，不傳播 — 這是盡力同步。引擎未運行時，模式將在下次啟動時
    通過快照讀取同步。
    """
    import socket as _socket

    _path = socket_path or os.environ.get(SOCKET_ENV_VAR, DEFAULT_SOCKET_PATH)
    ipc_secret = get_secret_value("OPENCLAW_IPC_SECRET") or ""

    try:
        with _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            sock.connect(_path)

            def _recv_line() -> str:
                buf = b""
                while True:
                    ch = sock.recv(1)
                    if not ch:
                        raise ConnectionResetError("engine closed connection")
                    if ch == b"\n":
                        return buf.decode("utf-8")
                    buf += ch

            def _send(msg: dict) -> None:
                sock.sendall(json.dumps_line_bytes(msg))

            # Authenticate if secret configured / 如果配置了密鑰則進行認證
            #
            # G2-FUP-IPC-LEGACY-MS-FIX (2026-04-26):
            # `ts` MUST be Unix epoch SECONDS (not milliseconds), to match the
            # Rust verifier in `rust/openclaw_engine/src/ipc_server/mod.rs:621-628`
            # which compares `|now_secs - ts|.abs() <= 30`. Earlier this path
            # used `int(time.time() * 1000)` (milliseconds), causing every legacy
            # `sync_ipc_call` to fail HMAC auth (skew ≈ 1.7e12 seconds → rejected
            # as "auth token expired"). Production callers (`trigger_live_auth_recheck`,
            # `set_system_mode`) fire-and-forget swallowed the error, so the bug
            # was silent; the fast-path was 100% non-functional. This change
            # aligns with the async `_authenticate()` path (line 553) and the
            # canonical helper in `helper_scripts/canary/edge_p2_flip_dry_run.py`.
            #
            # G2-FUP-IPC-LEGACY-MS-FIX（2026-04-26）：
            # `ts` 必須使用 Unix epoch 秒（非毫秒），以匹配 Rust verifier
            # （`rust/openclaw_engine/src/ipc_server/mod.rs:621-628`）的
            # `|now_secs - ts|.abs() <= 30` 比對邏輯。先前此處誤用
            # `int(time.time() * 1000)`（毫秒），導致每次 legacy `sync_ipc_call`
            # HMAC 驗證失敗（時間差 ≈ 1.7e12 秒 → 被判為「auth token expired」）。
            # 兩個 production caller（`trigger_live_auth_recheck`、`set_system_mode`）
            # 採 fire-and-forget 吞錯誤，故 bug 表面靜默；實際 fast-path 100% 失效。
            # 本修復對齊 async `_authenticate()` 路徑（第 553 行）與
            # `helper_scripts/canary/edge_p2_flip_dry_run.py` 內嵌 helper。
            if ipc_secret:
                ts = int(time.time())
                token = _hmac_lib.new(
                    ipc_secret.encode("utf-8"),
                    str(ts).encode("utf-8"),
                    hashlib.sha256,
                ).hexdigest()
                _send({"jsonrpc": "2.0", "method": "__auth",
                       "params": {"token": token, "ts": ts}, "id": 0})
                auth_resp = json.loads(_recv_line())
                if auth_resp.get("error"):
                    raise PermissionError(f"IPC auth failed: {auth_resp['error']}")

            # Send the actual request / 發送實際請求
            _send({"jsonrpc": "2.0", "method": method, "params": params, "id": 1})
            resp = json.loads(_recv_line())

            if resp.get("error"):
                raise RuntimeError(f"IPC error from engine: {resp['error']}")
            return resp.get("result", {})

    except FileNotFoundError:
        logger.debug(
            "sync_ipc_call: engine socket not found (engine not running?) — skipping / "
            "同步 IPC：引擎 socket 不存在（引擎未運行？）— 跳過"
        )
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "sync_ipc_call(%s) failed: %s — engine may sync on next restart / "
            "sync_ipc_call(%s) 失敗：%s — 引擎可能在下次重啟時同步",
            method, exc, method, exc,
        )
        raise
