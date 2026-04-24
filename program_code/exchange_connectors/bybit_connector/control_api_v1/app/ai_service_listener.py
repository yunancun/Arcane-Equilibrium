"""
ai_service_listener — Unix-socket IPC listener (split from ai_service.py per §九 1200-line cap)
==============================================================================================
Governance refs: DOC-04 §G Multi-Agent, Rust Migration R-01

MODULE_NOTE (EN/中):
  Sibling module of ``ai_service``. Hosts ``AIServiceListener`` (the Unix socket
  IPC server that bridges the Rust engine ↔ Python ``AIService``) and the
  ``_probe_unix_listener_alive`` helper used during multi-worker bind races.
  ``ai_service`` 的姊妹模組。承載 ``AIServiceListener``（連接 Rust 引擎 ↔ Python
  ``AIService`` 的 Unix socket IPC 伺服器）以及多 worker bind race 用到的
  ``_probe_unix_listener_alive`` 輔助。

  Wire protocol: newline-delimited JSON-RPC (matches Rust IPC client).
  協議：換行分隔的 JSON-RPC（與 Rust IPC 客戶端一致）。

  This file is purely a structural extraction — no logic changes.
  External callers should keep importing from ``app.ai_service`` (re-export preserved).
  此檔僅做結構性拆分，不改邏輯；外部仍應從 ``app.ai_service`` 匯入（保留 re-export）。
"""

from __future__ import annotations

import asyncio
import errno
import json
import logging
import os
import socket as _socket_stdlib
import time
from typing import Any

from . import ai_service as core
from .ai_service_dispatch import AIService

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# AIServiceListener — Unix socket IPC listener / Unix socket IPC 監聽器
# ═══════════════════════════════════════════════════════════════════════════════

def _probe_unix_listener_alive(path: str, timeout: float = 0.1) -> bool:
    """
    Non-blocking probe: does `path` have a live Unix-socket listener right now?
    非阻塞探測：當下 `path` 是否有活的 Unix socket listener？

    Returns True only on a successful connect (a peer process is accepting).
    僅在成功 connect 時回 True（有 peer process 正在 accept）。

    Any of these conditions → False (safe to bind ourselves):
      - File missing (FileNotFoundError)
      - File exists but nobody listening (ConnectionRefusedError)
      - File not a socket / permission error (OSError)
      - Connect hangs past timeout (socket.timeout)
    任一條件 → False（可安全 bind）：檔案不存在、無 listener、非 socket/權限、超時。
    """
    probe = _socket_stdlib.socket(_socket_stdlib.AF_UNIX, _socket_stdlib.SOCK_STREAM)
    try:
        probe.settimeout(timeout)
        probe.connect(path)
        return True
    except (FileNotFoundError, ConnectionRefusedError, _socket_stdlib.timeout):
        return False
    except OSError:
        return False
    finally:
        probe.close()


class AIServiceListener:
    """
    Listens on a Unix socket for incoming AI requests from the Rust engine.
    在 Unix socket 上監聽來自 Rust 引擎的 AI 請求。

    Python-side counterpart to the Rust IPC client. Protocol: length-prefixed
    JSON-RPC (4-byte big-endian u32 header + UTF-8 JSON payload).
    Rust IPC 客戶端的 Python 側對應物。協議：長度前綴 JSON-RPC。

    Request (Rust→Python): {"jsonrpc":"2.0","id":N,"method":"...","params":{...}}
    Response (Python→Rust): {"jsonrpc":"2.0","id":N,"result":{...}} or "error":{...}

    Usage: ``await listener.start()`` ... ``await listener.stop()``
    """

    def __init__(
        self,
        service: AIService,
        socket_path: str | None = None,
    ) -> None:
        self._service = service
        self._socket_path = core._resolve_socket_path(socket_path)
        self._server: asyncio.AbstractServer | None = None
        self._active_connections: int = 0
        self._running: bool = False

        # Stats for the listener itself / 監聽器自身的統計
        self._listener_stats: dict[str, int] = {
            "connections_accepted": 0,
            "connections_closed": 0,
            "requests_received": 0,
            "responses_sent": 0,
            "protocol_errors": 0,
            "payload_too_large": 0,
        }

        logger.info(
            "AIServiceListener configured: socket_path=%s", self._socket_path,
        )

    # ─── Lifecycle / 生命週期 ───

    async def start(self) -> None:
        """
        Start listening on the Unix socket. Creates dir, removes stale socket.
        開始在 Unix socket 上監聽。創建目錄，移除殘留 socket。

        Multi-worker safe: under uvicorn --workers N, only one worker successfully
        binds; peers probe-detect the live listener and passively no-op.
        多 worker 安全：uvicorn --workers N 下僅一個 worker 綁定成功，其餘探測到
        活 listener 後被動跳過（不 unlink、不 bind、不告警）。
        """
        if self._running:
            logger.warning("AIServiceListener already running, ignoring start()")
            return

        # Ensure socket directory exists / 確保 socket 目錄存在
        socket_dir = os.path.dirname(self._socket_path)
        if socket_dir:
            os.makedirs(socket_dir, exist_ok=True)

        # Multi-worker guard: peer worker already serving → passive no-op.
        # 多 worker 守衛：peer worker 已在服務 → 被動跳過（不 unlink、不 bind）。
        if _probe_unix_listener_alive(self._socket_path):
            logger.info(
                "AIServiceListener: peer worker already listening at %s, "
                "running as passive worker / 另一 worker 已監聽，被動模式",
                self._socket_path,
            )
            return

        # Remove stale socket file if present / 移除殘留 socket 文件
        try:
            os.unlink(self._socket_path)
        except FileNotFoundError:
            pass

        try:
            self._server = await asyncio.start_unix_server(
                self._handle_connection,
                path=self._socket_path,
            )
        except OSError as bind_exc:
            if bind_exc.errno == errno.EADDRINUSE:
                # Lost the narrow probe→bind race with a peer worker.
                # 與 peer worker 的窄 probe→bind 競速敗北，降級被動模式。
                logger.info(
                    "AIServiceListener: lost bind race at %s, "
                    "running as passive worker / 綁定競速敗北，被動模式",
                    self._socket_path,
                )
                return
            raise
        self._running = True
        logger.info("AIServiceListener started: %s", self._socket_path)

    async def stop(self) -> None:
        """Gracefully stop: close server, drain active connections (5s max). / 優雅停止：關閉服務器，排空連線（最多 5 秒）。"""
        if not self._running:
            logger.debug("AIServiceListener not running, ignoring stop()")
            return

        self._running = False

        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

        # Wait briefly for active connections to finish / 短暫等待活躍連線完成
        drain_deadline = time.monotonic() + 5.0
        while self._active_connections > 0 and time.monotonic() < drain_deadline:
            await asyncio.sleep(0.1)

        if self._active_connections > 0:
            logger.warning(
                "AIServiceListener stopped with %d active connections",
                self._active_connections,
            )

        # Clean up socket file / 清理 socket 文件
        try:
            os.unlink(self._socket_path)
        except FileNotFoundError:
            pass

        logger.info("AIServiceListener stopped")

    # ─── Connection handler / 連線處理 ───

    async def _handle_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """
        Handle a single client connection (read→dispatch→write loop).
        處理單個客戶端連線（讀取→分派→寫入循環）。
        """
        self._active_connections += 1
        self._listener_stats["connections_accepted"] += 1
        peer = "unknown"

        try:
            while self._running:
                # Read newline-delimited JSON-RPC request (matches Rust IPC protocol)
                # 讀取換行分隔的 JSON-RPC 請求（與 Rust IPC 協議一致）
                raw_line = await reader.readline()
                if not raw_line:
                    # EOF — client disconnected / 客戶端斷連
                    break

                # Validate line size / 驗證行大小
                if len(raw_line) > core.MAX_LINE_BYTES:
                    self._listener_stats["payload_too_large"] += 1
                    logger.error(
                        "Line too large: %d bytes > %d max",
                        len(raw_line), core.MAX_LINE_BYTES,
                    )
                    await self._write_error(writer, None, -32600, "payload_too_large")
                    break

                line = raw_line.strip()
                if not line:
                    continue

                self._listener_stats["requests_received"] += 1

                # Parse JSON-RPC request / 解析 JSON-RPC 請求
                try:
                    request = json.loads(line.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError) as parse_err:
                    self._listener_stats["protocol_errors"] += 1
                    logger.error("JSON parse error: %s", str(parse_err)[:100])
                    await self._write_error(writer, None, -32700, "parse_error")
                    continue

                # Extract JSON-RPC fields / 提取 JSON-RPC 字段
                request_id = request.get("id")
                method = request.get("method")
                params = request.get("params", {})

                if not method:
                    self._listener_stats["protocol_errors"] += 1
                    await self._write_error(
                        writer, request_id, -32600, "missing_method",
                    )
                    continue

                # Dispatch to AIService / 分派到 AIService
                result = await self._service.dispatch(method, params)

                # Build JSON-RPC response / 構建 JSON-RPC 回應
                if "error" in result:
                    response = {
                        "jsonrpc": core.JSONRPC_VERSION,
                        "id": request_id,
                        "error": {
                            "code": -32000,
                            "message": result["error"],
                            "data": {
                                k: v for k, v in result.items() if k != "error"
                            },
                        },
                    }
                else:
                    response = {
                        "jsonrpc": core.JSONRPC_VERSION,
                        "id": request_id,
                        "result": result,
                    }

                await self._write_response(writer, response)
                self._listener_stats["responses_sent"] += 1

        except asyncio.IncompleteReadError:
            # Client disconnected — normal in IPC lifecycle
            # 客戶端斷連 — IPC 生命週期中的正常情況
            logger.debug("Client disconnected (incomplete read): peer=%s", peer)

        except ConnectionResetError:
            # Client reset — normal during shutdown
            # 客戶端重置 — 關機期間的正常情況
            logger.debug("Client connection reset: peer=%s", peer)

        except Exception as exc:
            # Unexpected error — log but don't crash
            # 意外錯誤 — 記錄但不崩潰
            logger.error(
                "Connection handler error: %s", str(exc)[:core.ERROR_MSG_MAX_LEN],
            )

        finally:
            self._active_connections -= 1
            self._listener_stats["connections_closed"] += 1
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    # ─── Wire protocol helpers / 線路協議輔助 ───

    async def _write_response(
        self,
        writer: asyncio.StreamWriter,
        response: dict[str, Any],
    ) -> None:
        """
        Write a newline-delimited JSON response (matches Rust IPC protocol).
        寫入換行分隔的 JSON 回應（與 Rust IPC 協議一致）。
        """
        payload = json.dumps(response, separators=(",", ":")) + "\n"
        writer.write(payload.encode("utf-8"))
        await writer.drain()

    async def _write_error(
        self,
        writer: asyncio.StreamWriter,
        request_id: int | None,
        code: int,
        message: str,
    ) -> None:
        """
        Write a JSON-RPC error response.
        寫入 JSON-RPC 錯誤回應。
        """
        response = {
            "jsonrpc": core.JSONRPC_VERSION,
            "id": request_id,
            "error": {"code": code, "message": message},
        }
        await self._write_response(writer, response)

    # ─── Listener stats / 監聽器統計 ───

    def get_listener_stats(self) -> dict[str, Any]:
        """
        Return listener-level statistics.
        返回監聽器級別的統計。
        """
        return {
            **self._listener_stats,
            "socket_path": self._socket_path,
            "running": self._running,
            "active_connections": self._active_connections,
        }

    @property
    def socket_path(self) -> str:
        """
        Return the resolved socket path.
        返回解析後的 socket 路徑。
        """
        return self._socket_path

    @property
    def is_running(self) -> bool:
        """
        Whether the listener is currently running.
        監聽器是否正在運行。
        """
        return self._running
