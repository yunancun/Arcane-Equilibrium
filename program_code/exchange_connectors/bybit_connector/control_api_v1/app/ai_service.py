"""
R01-7 — AIService: Python-side AI evaluation service for Rust engine IPC
=========================================================================
Governance refs: DOC-04 §G Multi-Agent, Rust Migration R-01

MODULE_NOTE (中文):
  AIService 是 Rust 遷移架構中 Python 側的 AI 評估服務。
  當 Rust 引擎需要 AI 推理（L1/L2 模型）時，通過 IPC 發送 JSON-RPC 請求到此服務。
  本服務接收請求、路由到對應的 Agent（Strategist/Analyst/Conductor/Scout/Guardian），
  收集回應後返回結構化結果。

  職責：
  1. 接收 Rust 引擎的 JSON-RPC 請求（5 種方法）
  2. 分派到對應 Agent 處理器
  3. 每個處理器有獨立 TTL（strategist=15s, analyst=30s, conductor=10s, scout=10s, guardian=5s）
  4. 統計調用次數、錯誤數、超時數
  5. AIServiceListener 在 Unix socket 上監聽連線

  安全不變量：
  - system_mode = demo_only 不變
  - fail-closed：未知方法或異常時返回錯誤結構，不崩潰
  - 錯誤訊息截斷至 200 字符（防止洩漏堆疊追蹤）
  - 所有路徑使用環境變量，不硬編碼

  遷移階段：
  - 當前為 stub 實現（返回有效但保守的回應結構）
  - R-02/R-06 階段將接入真實 Agent 邏輯

MODULE_NOTE (English):
  AIService is the Python-side AI evaluation service for the Rust migration architecture.
  When the Rust engine needs AI inference (L1/L2 models), it sends JSON-RPC requests
  via IPC to this service. This service receives requests, routes them to the appropriate
  Agent (Strategist/Analyst/Conductor/Scout/Guardian), and returns structured responses.

  Responsibilities:
  1. Receive JSON-RPC requests from the Rust engine (5 methods)
  2. Dispatch to the corresponding Agent handler
  3. Each handler has an independent TTL (strategist=15s, analyst=30s, conductor=10s, scout=10s, guardian=5s)
  4. Track call counts, error counts, timeout counts
  5. AIServiceListener listens on a Unix socket for connections

  Safety invariants:
  - system_mode = demo_only (unchanged)
  - fail-closed: unknown methods or exceptions return error structure, never crash
  - Error messages truncated to 200 chars (prevent stack trace leakage)
  - All paths use env vars, no hardcoded paths

  Migration phase:
  - Currently stub implementations (return valid but conservative responses)
  - Will be wired to real Agent logic in R-02/R-06
"""

from __future__ import annotations

import asyncio
import json
import logging
import os

import time
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Constants / 常數
# ═══════════════════════════════════════════════════════════════════════════════

# Handler TTLs (seconds) / 處理器超時時間（秒）
HANDLER_TTLS: dict[str, float] = {
    "strategist_evaluate": 15.0,   # Strategy evaluation / 策略評估
    "analyst_evaluate": 30.0,      # Deep analysis / 深度分析
    "conductor_evaluate": 10.0,    # Orchestration / 編排決策
    "scout_scan": 10.0,            # Market scanning / 市場掃描
    "guardian_check": 5.0,         # Risk check (fastest) / 風控檢查（最快）
}

# Socket path defaults / Socket 路徑默認值
_DEFAULT_SOCKET_DIR = "/tmp/openclaw"
_DEFAULT_SOCKET_NAME = "ai_service.sock"

JSONRPC_VERSION = "2.0"                   # JSON-RPC protocol version
MAX_LINE_BYTES = 16 * 1024 * 1024         # Max line size 16 MB / 最大行長度 16 MB
ERROR_MSG_MAX_LEN = 200                   # Truncate errors (security) / 截斷錯誤訊息（安全）


# ═══════════════════════════════════════════════════════════════════════════════
# Helper: default socket path / 輔助函數：默認 socket 路徑
# ═══════════════════════════════════════════════════════════════════════════════

def _resolve_socket_path(explicit: str | None = None) -> str:
    """Resolve socket path: explicit > env > default. / 解析 socket 路徑：顯式 > 環境變量 > 默認值。"""
    if explicit:
        return explicit
    env_path = os.environ.get("OPENCLAW_AI_SERVICE_SOCKET")
    if env_path:
        return env_path
    return os.path.join(_DEFAULT_SOCKET_DIR, _DEFAULT_SOCKET_NAME)


# ═══════════════════════════════════════════════════════════════════════════════
# AIService — Core dispatch logic / 核心分派邏輯
# ═══════════════════════════════════════════════════════════════════════════════

class AIService:
    """
    AI Service — bridges Rust engine IPC requests to Python AI Agents.
    AI 服務 — 橋接 Rust 引擎 IPC 請求到 Python AI Agent。

    Receives JSON-RPC requests from the Rust engine, dispatches to the
    appropriate agent, and returns structured responses.
    接收 Rust 引擎的 JSON-RPC 請求，分派到對應的 Agent，返回結構化結果。

    Thread safety: single-threaded asyncio — no locks needed for stats dict.
    線程安全：單線程 asyncio — 統計 dict 不需要鎖。

    Usage::

        service = AIService()
        result = await service.dispatch("strategist_evaluate", {"intel": {...}})

    Migration note:
        All handlers currently return stub responses. They will be wired to
        real StrategistAgent/AnalystAgent/etc. in R-02 and R-06 phases.
    遷移備註：
        所有處理器目前返回 stub 回應。將在 R-02 和 R-06 階段接入真實 Agent。
    """

    def __init__(self) -> None:
        # Handler registry: method name -> async handler callable
        # 處理器註冊表：方法名 -> 異步處理器
        self._handlers: dict[str, Callable[..., Any]] = {}

        # Call statistics — single-threaded asyncio, no lock needed
        # 調用統計 — 單線程 asyncio，不需要鎖
        self._stats: dict[str, int] = {
            "strategist_calls": 0,
            "analyst_calls": 0,
            "conductor_calls": 0,
            "scout_calls": 0,
            "guardian_calls": 0,
            "errors": 0,
            "timeouts": 0,
            "total_dispatches": 0,
        }

        # Timestamps for observability / 可觀測性的時間戳
        self._created_at: float = time.time()
        self._last_dispatch_at: float = 0.0

        self._register_handlers()
        logger.info("AIService initialized with %d handlers", len(self._handlers))

    # ─── Handler registration / 處理器註冊 ───

    def _register_handlers(self) -> None:
        """
        Register all JSON-RPC method handlers.
        註冊所有 JSON-RPC 方法處理器。
        """
        self._handlers = {
            "strategist_evaluate": self._handle_strategist,
            "analyst_evaluate": self._handle_analyst,
            "conductor_evaluate": self._handle_conductor,
            "scout_scan": self._handle_scout,
            "guardian_check": self._handle_guardian,
        }

    # ─── Main dispatch / 主分派入口 ───

    async def dispatch(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """
        Dispatch an IPC method call to the appropriate handler with per-method TTL.
        將 IPC 方法調用分派到對應的處理器，帶每方法 TTL。

        Returns JSON-serializable dict with "status" or "error" key.
        返回可序列化 dict，包含 "status" 或 "error" 鍵。
        """
        self._stats["total_dispatches"] += 1
        self._last_dispatch_at = time.time()

        handler = self._handlers.get(method)
        if handler is None:
            self._stats["errors"] += 1
            logger.warning("Unknown IPC method: %s", method)
            return {
                "error": f"unknown_method: {method}",
                "available_methods": list(self._handlers.keys()),
            }

        ttl = HANDLER_TTLS.get(method, 15.0)
        t0 = time.monotonic()

        try:
            result = await asyncio.wait_for(handler(params), timeout=ttl)
            elapsed_ms = (time.monotonic() - t0) * 1000
            result["_elapsed_ms"] = round(elapsed_ms, 2)
            return result

        except asyncio.TimeoutError:
            self._stats["timeouts"] += 1
            elapsed_ms = (time.monotonic() - t0) * 1000
            logger.error(
                "Handler timeout: method=%s ttl=%.1fs elapsed=%.0fms",
                method, ttl, elapsed_ms,
            )
            return {
                "error": "timeout",
                "method": method,
                "ttl_seconds": ttl,
                "_elapsed_ms": round(elapsed_ms, 2),
            }

        except Exception as exc:
            self._stats["errors"] += 1
            elapsed_ms = (time.monotonic() - t0) * 1000
            # Truncate error message to prevent stack trace leakage
            # 截斷錯誤訊息防止堆疊追蹤洩漏
            error_msg = str(exc)[:ERROR_MSG_MAX_LEN]
            logger.error(
                "Handler error: method=%s error=%s elapsed=%.0fms",
                method, error_msg, elapsed_ms,
            )
            return {
                "error": error_msg,
                "method": method,
                "_elapsed_ms": round(elapsed_ms, 2),
            }

    # ─── Agent handlers (stubs) / Agent 處理器（stub 實現）───
    # These will be wired to real agents in R-02/R-06.
    # 這些將在 R-02/R-06 階段接入真實 Agent。

    async def _handle_strategist(self, params: dict[str, Any]) -> dict[str, Any]:
        """
        Forward to Strategist agent for strategy evaluation.
        轉發到策略師 Agent 進行策略評估。
        Params: intel (IntelObject), model_tier, context. Stub: hold + confidence=0.
        """
        self._stats["strategist_calls"] += 1

        intel = params.get("intel", {})
        symbol = intel.get("symbol", "unknown")
        model_tier = params.get("model_tier", "l1_9b")

        # TODO(R-02): Wire to real StrategistAgent.evaluate()
        # TODO(R-02): 接入真實 StrategistAgent.evaluate()
        logger.debug("Strategist stub: symbol=%s tier=%s", symbol, model_tier)

        return {
            "status": "evaluated",
            "agent": "strategist",
            "symbol": symbol,
            "action": "hold",
            "confidence": 0.0,
            "reasoning": "stub_response: no evaluation performed during migration phase",
            "model_tier": model_tier,
            "source": "ai_service_stub",
            "signals_considered": 0,
        }

    async def _handle_analyst(self, params: dict[str, Any]) -> dict[str, Any]:
        """
        Forward to Analyst agent for deep trade analysis.
        轉發到分析師 Agent 進行深度交易分析。
        Params: trade_data, analysis_type, lookback_trades. Stub: empty analysis.
        """
        self._stats["analyst_calls"] += 1

        trade_data = params.get("trade_data", {})
        analysis_type = params.get("analysis_type", "round_trip")
        symbol = trade_data.get("symbol", "unknown")

        # TODO(R-06): Wire to real AnalystAgent.analyze()
        # TODO(R-06): 接入真實 AnalystAgent.analyze()
        logger.debug(
            "Analyst stub: symbol=%s type=%s", symbol, analysis_type,
        )

        return {
            "status": "analyzed",
            "agent": "analyst",
            "symbol": symbol,
            "analysis_type": analysis_type,
            "observations": 0,
            "winning_patterns": [],
            "losing_patterns": [],
            "regime_strategy_matrix": {},
            "recommendations": [],
            "source": "ai_service_stub",
        }

    async def _handle_conductor(self, params: dict[str, Any]) -> dict[str, Any]:
        """
        Forward to Conductor for orchestration decisions.
        轉發到指揮者進行編排決策。
        Params: decision_type, agents_state, pending_tasks. Stub: maintain_current.
        """
        self._stats["conductor_calls"] += 1

        decision_type = params.get("decision_type", "priority")

        # TODO(R-06): Wire to real Conductor orchestration logic
        # TODO(R-06): 接入真實 Conductor 編排邏輯
        logger.debug("Conductor stub: decision_type=%s", decision_type)

        return {
            "status": "decided",
            "agent": "conductor",
            "decision_type": decision_type,
            "action": "maintain_current",
            "priority_changes": [],
            "resource_reallocation": {},
            "conflict_resolutions": [],
            "source": "ai_service_stub",
        }

    async def _handle_scout(self, params: dict[str, Any]) -> dict[str, Any]:
        """
        Forward to Scout agent for market scanning.
        轉發到偵查員 Agent 進行市場掃描。
        Params: symbols, scan_type, filters. Stub: empty scan results.
        """
        self._stats["scout_calls"] += 1

        symbols = params.get("symbols", [])
        scan_type = params.get("scan_type", "full")

        # TODO(R-02): Wire to real ScoutAgent.scan()
        # TODO(R-02): 接入真實 ScoutAgent.scan()
        logger.debug(
            "Scout stub: symbols=%d scan_type=%s", len(symbols), scan_type,
        )

        return {
            "status": "scanned",
            "agent": "scout",
            "scan_type": scan_type,
            "symbols_scanned": 0,
            "intel_objects": [],
            "event_alerts": [],
            "source": "ai_service_stub",
        }

    async def _handle_guardian(self, params: dict[str, Any]) -> dict[str, Any]:
        """
        Forward to Guardian agent for risk check.
        轉發到守衛 Agent 進行風控檢查。
        Params: intent, portfolio_state, check_type.
        Stub: REJECTED (fail-closed per Principle #4/#6). / Stub: REJECTED（遵循原則 #4/#6）。
        """
        self._stats["guardian_calls"] += 1

        intent = params.get("intent", {})
        check_type = params.get("check_type", "pre_trade")
        symbol = intent.get("symbol", "unknown")

        # TODO(R-02): Wire to real GuardianAgent.review()
        # TODO(R-02): 接入真實 GuardianAgent.review()
        logger.debug("Guardian stub: symbol=%s check=%s", symbol, check_type)

        return {
            "status": "checked",
            "agent": "guardian",
            "symbol": symbol,
            "check_type": check_type,
            "verdict": "REJECTED",
            "reason": "stub_guardian: fail-closed default during migration",
            "risk_flags": [],
            "modifications": {},
            "source": "ai_service_stub",
        }

    # ─── Stats & introspection / 統計與自省 ───

    def get_stats(self) -> dict[str, Any]:
        """
        Return call statistics and service metadata.
        返回調用統計和服務元數據。
        """
        uptime = time.time() - self._created_at
        return {
            **self._stats,
            "uptime_seconds": round(uptime, 1),
            "last_dispatch_at": self._last_dispatch_at or None,
            "handler_count": len(self._handlers),
        }

    def get_handler_methods(self) -> list[str]:
        """
        List registered handler method names.
        列出已註冊的處理方法名稱。
        """
        return list(self._handlers.keys())

    def get_handler_ttls(self) -> dict[str, float]:
        """
        Return TTL configuration for each handler.
        返回每個處理器的 TTL 配置。
        """
        return dict(HANDLER_TTLS)

    def reset_stats(self) -> None:
        """
        Reset all call statistics to zero.
        重置所有調用統計為零。

        Useful for testing or after a known configuration change.
        用於測試或已知配置變更後。
        """
        for key in self._stats:
            self._stats[key] = 0
        self._last_dispatch_at = 0.0
        logger.info("AIService stats reset")


# ═══════════════════════════════════════════════════════════════════════════════
# AIServiceListener — Unix socket IPC listener / Unix socket IPC 監聽器
# ═══════════════════════════════════════════════════════════════════════════════

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
        self._socket_path = _resolve_socket_path(socket_path)
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
        """
        if self._running:
            logger.warning("AIServiceListener already running, ignoring start()")
            return

        # Ensure socket directory exists / 確保 socket 目錄存在
        socket_dir = os.path.dirname(self._socket_path)
        if socket_dir:
            os.makedirs(socket_dir, exist_ok=True)

        # Remove stale socket file if present / 移除殘留 socket 文件
        try:
            os.unlink(self._socket_path)
        except FileNotFoundError:
            pass

        self._server = await asyncio.start_unix_server(
            self._handle_connection,
            path=self._socket_path,
        )
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
                if len(raw_line) > MAX_LINE_BYTES:
                    self._listener_stats["payload_too_large"] += 1
                    logger.error(
                        "Line too large: %d bytes > %d max",
                        len(raw_line), MAX_LINE_BYTES,
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
                        "jsonrpc": JSONRPC_VERSION,
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
                        "jsonrpc": JSONRPC_VERSION,
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
                "Connection handler error: %s", str(exc)[:ERROR_MSG_MAX_LEN],
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
            "jsonrpc": JSONRPC_VERSION,
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


# ═══════════════════════════════════════════════════════════════════════════════
# Factory / convenience / 工廠 / 便利函數
# ═══════════════════════════════════════════════════════════════════════════════

def create_ai_service_listener(
    socket_path: str | None = None,
) -> tuple[AIService, AIServiceListener]:
    """
    Create an AIService + AIServiceListener pair ready to start.
    創建一對準備啟動的 AIService + AIServiceListener。

    Usage::

        service, listener = create_ai_service_listener()
        await listener.start()
        # ... later ...
        await listener.stop()

    Args:
        socket_path: Optional explicit socket path. Falls back to env var
                     or default (/tmp/openclaw/ai_service.sock).
                     可選的顯式 socket 路徑。回退到環境變量或默認值。

    Returns:
        Tuple of (AIService, AIServiceListener).
        (AIService, AIServiceListener) 元組。
    """
    service = AIService()
    listener = AIServiceListener(service, socket_path=socket_path)
    return service, listener
