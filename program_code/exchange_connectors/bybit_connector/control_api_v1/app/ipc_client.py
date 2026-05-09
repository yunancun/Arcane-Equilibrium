from __future__ import annotations

"""
Engine IPC Client — JSON-RPC 2.0 over Unix domain socket
引擎 IPC 客戶端 — 通過 Unix 域套接字進行 JSON-RPC 2.0 通信

MODULE_NOTE (中文):
  本模組實現 Python 端與 Rust 引擎之間的 IPC 通信客戶端：
  1. JSON-RPC 2.0 協議，換行分隔消息
  2. 自動重連（指數退避：base=1s, max=30s, factor=2）
  3. 連續 3 次重連失敗 → ai_available=false，退回純 Python 模式
  4. 每方法類型可配超時（strategist=15s, analyst=30s, conductor=10s, default=5s）
  5. asyncio.Lock 序列化並發調用，原子計數器生成請求 ID

MODULE_NOTE (English):
  IPC client for Python ↔ Rust engine communication:
  1. JSON-RPC 2.0 protocol, newline-delimited messages
  2. Auto-reconnect with exponential backoff (base=1s, max=30s, factor=2)
  3. After 3 consecutive reconnect failures → ai_available=false, fallback to pure Python
  4. Per-method timeout (strategist=15s, analyst=30s, conductor=10s, default=5s)
  5. asyncio.Lock serializes concurrent calls, atomic counter for request IDs

Safety guarantees / 安全保證:
  - Read-only: never modifies trading state directly
  - Fail-closed: disconnection → fallback mode, no silent failures
  - No hardcoded paths: socket path via env var or parameter
  - Cross-platform: graceful FileNotFoundError handling
"""

import asyncio
import hashlib
import hmac as _hmac_lib  # std-lib hmac; aliased to avoid shadowing local variables
import logging
import os
import time
from typing import Any

from . import json_fast as json
from .secret_runtime import get_secret_value
from .ipc_client_risk_config import build_update_risk_config_params

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Constants / 常量
# ═══════════════════════════════════════════════════════════════════════════════

DEFAULT_SOCKET_PATH = "/tmp/openclaw/engine.sock"
SOCKET_ENV_VAR = "OPENCLAW_IPC_SOCKET"

# Reconnection parameters / 重連參數
RECONNECT_BASE_DELAY = 1.0        # seconds / 秒
RECONNECT_MAX_DELAY = 30.0        # seconds / 秒
RECONNECT_FACTOR = 2.0
MAX_RECONNECT_ATTEMPTS = 3
FALLBACK_RETRY_INTERVAL = 5.0     # seconds / 秒

# Per-method timeouts / 每方法超時
METHOD_TIMEOUTS: dict[str, float] = {
    "strategist_evaluate": 15.0,
    "analyst_evaluate": 30.0,
    "conductor_evaluate": 10.0,
}
DEFAULT_TIMEOUT = 5.0


# ═══════════════════════════════════════════════════════════════════════════════
# Exceptions / 異常
# ═══════════════════════════════════════════════════════════════════════════════

class EngineDisconnectedError(Exception):
    """Raised when IPC call attempted while disconnected / IPC 調用時引擎未連接"""
    pass


class EngineTimeoutError(Exception):
    """Raised when IPC call times out / IPC 調用超時"""
    pass


# ═══════════════════════════════════════════════════════════════════════════════
# EngineIPCClient / 引擎 IPC 客戶端
# ═══════════════════════════════════════════════════════════════════════════════

class EngineIPCClient:
    """
    JSON-RPC 2.0 client communicating with the Rust engine over Unix domain socket.
    通過 Unix 域套接字與 Rust 引擎通信的 JSON-RPC 2.0 客戶端。

    Features / 功能:
      - Auto-reconnect with exponential backoff / 指數退避自動重連
      - Fallback mode after 3 consecutive failures / 連續 3 次失敗後進入降級模式
      - Per-method configurable timeouts / 按方法可配超時
      - Serialized concurrent access via asyncio.Lock / Lock 序列化並發訪問
    """

    def __init__(self, socket_path: str | None = None) -> None:
        """
        Initialize IPC client. / 初始化 IPC 客戶端。

        Args:
            socket_path: Unix socket path. Falls back to OPENCLAW_IPC_SOCKET env
                         var, then to default /tmp/openclaw/engine.sock.
                         Unix 套接字路徑。優先使用參數，其次環境變量，最後默認路徑。
        """
        self._socket_path: str = (
            socket_path
            or os.environ.get(SOCKET_ENV_VAR)
            or DEFAULT_SOCKET_PATH
        )
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._connected: bool = False
        self._reconnect_attempts: int = 0
        self._ai_available: bool = True
        self._request_id: int = 0
        self._lock: asyncio.Lock = asyncio.Lock()
        self._reconnect_task: asyncio.Task | None = None

        logger.info(
            "EngineIPCClient initialized, socket_path=%s / "
            "IPC 客戶端已初始化，套接字路徑=%s",
            self._socket_path, self._socket_path,
        )

    # ─── Properties / 屬性 ───────────────────────────────────────────────────

    @property
    def is_connected(self) -> bool:
        """Whether the socket connection is active. / 套接字連接是否活躍。"""
        return self._connected

    @property
    def is_engine_available(self) -> bool:
        """
        True if connected OR if fallback mode hasn't been triggered.
        連接中或尚未觸發降級模式時為 True。
        """
        return self._connected or self._ai_available

    # ─── Connection management / 連接管理 ────────────────────────────────────

    async def connect(self) -> bool:
        """
        Connect to the Rust engine Unix socket.
        連接到 Rust 引擎的 Unix 域套接字。

        Returns:
            True on success, False on failure. / 成功返回 True，失敗返回 False。
        """
        return await self._try_connect()

    async def disconnect(self) -> None:
        """
        Cleanly close the socket connection.
        乾淨地關閉套接字連接。
        """
        # Cancel any running reconnect task / 取消運行中的重連任務
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass
            self._reconnect_task = None

        await self._close_connection()
        logger.info(
            "EngineIPCClient disconnected / IPC 客戶端已斷開連接"
        )

    # ─── RPC calls / RPC 調用 ────────────────────────────────────────────────

    async def call(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """
        Send a JSON-RPC 2.0 request and await the response.
        發送 JSON-RPC 2.0 請求並等待響應。

        Args:
            method:  RPC method name / RPC 方法名
            params:  Optional parameters dict / 可選參數字典
            timeout: Override timeout in seconds; if None, uses per-method default.
                     覆蓋超時（秒）；None 時使用方法默認超時。

        Returns:
            The 'result' field from the JSON-RPC response.
            JSON-RPC 響應中的 'result' 字段。

        Raises:
            EngineDisconnectedError: If not connected / 未連接時拋出
            EngineTimeoutError: If response not received within timeout / 超時時拋出
        """
        if not self._connected:
            raise EngineDisconnectedError(
                f"Not connected to engine at {self._socket_path} / "
                f"未連接到引擎 {self._socket_path}"
            )

        effective_timeout = timeout or METHOD_TIMEOUTS.get(method, DEFAULT_TIMEOUT)

        # Build JSON-RPC 2.0 request / 構建 JSON-RPC 2.0 請求
        self._request_id += 1
        request_id = self._request_id
        request = {
            "jsonrpc": "2.0",
            "method": method,
            "id": request_id,
        }
        if params is not None:
            request["params"] = params

        # E2 round 1 LOW-2 retrofit (2026-05-03): ensure_ascii=False keeps
        # raw UTF-8 bytes on the wire so any cross-language byte-equal
        # contract (mirror of REF-20 W6 V042 manifest_signer canonical body
        # pattern + Sprint 1 Track A F1 lock) holds when params include
        # unicode (e.g. intent_id="测试_intent_001" / non-ASCII strategy
        # name). All current 33+ IPC methods use ASCII payloads so the kwarg
        # is a no-op today; future unicode-bearing payloads (Decision Lease
        # Track H E-3 lease IPC bridge, MLDE strategy_name fields, audit
        # writers, etc.) get correct raw-UTF-8 framing automatically.
        # Rust serde_json::to_vec emits raw UTF-8 by default; ensure_ascii=False
        # is what makes Python serde mirror it byte-for-byte.
        # E2 round 1 LOW-2 retrofit（2026-05-03）：ensure_ascii=False 讓 wire
        # 上保留 raw UTF-8 bytes，使任何跨語言 byte-equal contract（鏡像
        # REF-20 W6 V042 manifest_signer canonical body 模式 + Sprint 1
        # Track A F1 鎖）在 params 含 unicode（如中文 intent_id / 非 ASCII
        # 策略名）時仍成立。當前 33+ IPC method 全 ASCII payload，本 kwarg
        # 今日為 no-op；未來含 unicode 的 payload（Track H E-3 lease IPC、
        # MLDE strategy_name 欄位、audit writer 等）將自動獲得正確的
        # raw-UTF-8 framing。Rust serde_json::to_vec 預設 raw UTF-8；
        # ensure_ascii=False 讓 Python serde 鏡像相同 byte 流。
        payload = json.dumps(
            request, separators=(",", ":"), ensure_ascii=False
        ) + "\n"

        async with self._lock:
            try:
                return await asyncio.wait_for(
                    self._send_and_receive(payload, request_id),
                    timeout=effective_timeout,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "IPC call timed out: method=%s timeout=%.1fs id=%d / "
                    "IPC 調用超時：method=%s timeout=%.1fs id=%d",
                    method, effective_timeout, request_id,
                    method, effective_timeout, request_id,
                )
                # Connection may be stale; trigger reconnect
                # 連接可能已過時，觸發重連
                await self._handle_disconnect()
                raise EngineTimeoutError(
                    f"IPC call '{method}' timed out after {effective_timeout}s / "
                    f"IPC 調用 '{method}' 在 {effective_timeout}s 後超時"
                )
            except (ConnectionError, OSError, BrokenPipeError) as exc:
                logger.error(
                    "IPC send/recv error: %s / IPC 發送接收錯誤: %s", exc, exc,
                )
                await self._handle_disconnect()
                raise EngineDisconnectedError(
                    f"Connection lost during call '{method}' / "
                    f"調用 '{method}' 時連接丟失"
                ) from exc

    async def ping(self) -> bool:
        """
        Quick health check against the engine.
        對引擎進行快速健康檢查。

        Returns:
            True if engine responds, False otherwise.
            引擎回應返回 True，否則 False。
        """
        try:
            result = await self.call("ping", timeout=2.0)
            # Rust IPC server returns "pong" as result value
            # Rust IPC 服務端返回 "pong" 作為 result 值
            return result == "pong" or (isinstance(result, dict) and result.get("status") == "ok")
        except (EngineDisconnectedError, EngineTimeoutError):
            return False

    async def get_state(self) -> dict[str, Any]:
        """
        Get engine state summary. / 獲取引擎狀態摘要。
        """
        return await self.call("get_state")

    async def reload_config(self) -> dict[str, Any]:
        """
        Trigger engine config reload. / 觸發引擎配置重載。
        """
        return await self.call("reload_config")

    # ─── R06-A: Pipeline state queries / 管線狀態查詢 ────────────────────────

    async def get_paper_state(self, engine: str = "paper") -> dict[str, Any]:
        """
        Get pipeline state snapshot (balance, positions, PnL, fees) for a specific engine.
        獲取指定引擎的管線狀態快照（餘額、持倉、損益、手續費）。
        :param engine: "paper" | "demo" | "live"
        """
        return await self.call("get_paper_state", params={"engine": engine})

    async def get_mode_snapshot(self, engine: str = "paper") -> dict[str, Any]:
        """
        Get full ModeStateSnapshot for a specific engine (paper/demo/live).
        獲取指定引擎的完整 ModeStateSnapshot。
        :param engine: "paper" | "demo" | "live"
        """
        return await self.call("get_mode_snapshot", params={"engine": engine})

    async def get_active_modes(self) -> list[str]:
        """
        List all active engine modes (Phase 4).
        列出所有活躍引擎模式（Phase 4）。
        """
        return await self.call("get_active_modes")

    async def get_latest_prices(self) -> dict[str, float]:
        """
        Get latest per-symbol prices from the tick pipeline.
        從 tick 管線獲取每交易對最新價格。
        """
        return await self.call("get_latest_prices")

    async def get_tick_stats(self) -> dict[str, Any]:
        """
        Get tick processing statistics (total_ticks, fills, intents, stops).
        獲取 tick 處理統計（總 ticks、成交、意圖、止損）。
        """
        return await self.call("get_tick_stats")

    # ─── Phase 4 (4-00): Dashboard skeleton status / 儀表板骨架狀態 ───────────

    async def get_phase4_status(self) -> dict[str, Any]:
        """
        Get Phase 4 dashboard traffic-light aggregation.
        獲取 Phase 4 儀表板紅黃綠燈聚合狀態。

        Returns a dict with keys: teacher / linucb / news / dl3 / last_update_ms.
        Each module status is one of: grey (not started) / green / yellow / red.
        At skeleton stage (4-00) all modules return "grey".

        返回字典欄位：teacher / linucb / news / dl3 / last_update_ms。
        各模組狀態為：grey（未啟動）/ green / yellow / red。
        骨架階段（4-00）所有模組均返回 "grey"。
        """
        return await self.call("get_phase4_status")

    # ─── Phase 4 (4-15): AI budget tracker / AI 預算追蹤器 ──────────────────────

    async def get_ai_budget_status(self) -> dict[str, Any]:
        """
        Get current AI budget status snapshot from the Rust BudgetTracker.
        從 Rust BudgetTracker 取得當前 AI 預算狀態快照。

        Returns the full status_json (limits, mtd usage, degrade level, refresh ts).
        If the tracker is uninitialized (DB pool unavailable at boot), fail-soft
        returns ``{"status": "uninitialized", "reason": ...}`` instead of raising.

        返回完整 status_json（額度、本月用量、降級等級、刷新時戳）。
        若 tracker 未初始化（啟動時 DB 池不可用），fail-soft 回傳
        ``{"status": "uninitialized", "reason": ...}`` 而不拋出例外。
        """
        return await self.call("get_ai_budget_status")

    async def update_ai_budget_config(
        self,
        scope: str,
        monthly_usd: float,
        updated_by: str = "operator",
    ) -> dict[str, Any]:
        """
        Upsert one AI budget scope and trigger an in-memory refresh.
        Upsert 單一 AI 預算 scope 並觸發記憶體刷新。

        :param scope: budget scope name (e.g. ``teacher`` / ``analyst`` / ``reserve``
            / ``local_total``). 預算 scope 名稱。
        :param monthly_usd: monthly USD ceiling (>= 0). 月度美元上限（>= 0）。
        :param updated_by: audit origin tag, defaults to ``"operator"``.
            審計來源標籤，預設為 ``"operator"``。

        Fail-closed: invalid params raise via the JSON-RPC error path; tracker
        uninitialized or DB write failure raises an internal error. Successful
        upsert refreshes the tracker so the new ceiling is enforced on the very
        next LLM call.
        fail-closed：參數無效會經由 JSON-RPC 錯誤路徑拋出；tracker 未初始化或
        DB 寫入失敗也會拋出 internal error。寫入成功後 tracker 會刷新，新上限
        在下一次 LLM 調用即生效。
        """
        return await self.call(
            "update_ai_budget_config",
            {"scope": scope, "monthly_usd": monthly_usd, "updated_by": updated_by},
        )

    # ─── Paper session control commands / 紙盤 session 控制命令 ────────────────

    async def pause_paper(self) -> dict[str, Any]:
        """
        Pause paper trading — stops strategy dispatch + shadow orders.
        Prices, indicators, and stop checks continue.
        暫停紙盤交易 — 停止策略分派+影子訂單。價格、指標、止損繼續。
        """
        return await self.call("pause_paper")

    async def resume_paper(self) -> dict[str, Any]:
        """
        Resume paper trading — restores strategy dispatch + shadow orders.
        恢復紙盤交易 — 恢復策略分派+影子訂單。
        """
        return await self.call("resume_paper")

    async def close_all_positions(self) -> dict[str, Any]:
        """
        Close all open paper positions at current market prices.
        以當前市場價格平掉所有紙盤持倉。
        """
        return await self.call("close_all_positions")

    async def reset_paper_state(self, new_balance: float = 10_000.0) -> dict[str, Any]:
        """
        Reset paper state — clear positions, reset balance to new_balance.
        重置紙盤狀態 — 清倉、重置餘額。
        """
        return await self.call("reset_paper_state", params={"new_balance": new_balance})

    # ─── ARCH-RC1 1C-3-F: External paper-side order submission ──────────────
    async def submit_paper_order(
        self,
        *,
        symbol: str,
        side: str,
        qty: float,
        order_type: str = "market",
        limit_price: float | None = None,
        confidence: float = 1.0,
        strategy: str = "external",
    ) -> dict[str, Any]:
        """
        Submit an external paper-side order through the same IntentProcessor
        pipeline strategies use (Guardian / Kelly / P1 cap / risk gate / cost
        gate). Returns the success envelope from the Rust engine:
        ``{order_id, fill_qty, fill_price, fee, realized_pnl}``.
        Rejection (paused / halted / no price / gate failure) raises via the
        JSON-RPC error path.
        ARCH-RC1 1C-3-F：通過策略所走的同一條 IntentProcessor 管線提交外部紙盤訂單。
        """
        params: dict[str, Any] = {
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "order_type": order_type,
            "confidence": confidence,
            "strategy": strategy,
        }
        if limit_price is not None:
            params["limit_price"] = limit_price
        return await self.call("submit_paper_order", params=params)

    _UNSET = object()  # sentinel for "not passed" vs "passed as None (=disable)"

    async def update_risk_config(
        self,
        hard_stop_pct: float | None = None,
        p1_risk_pct: float | None = None,
        trailing_stop_pct: float | None = _UNSET,
        time_stop_hours: float | None = _UNSET,
        atr_multiplier: float | None = _UNSET,
        take_profit_pct: float | None = _UNSET,
        max_leverage: float | None = None,
        max_drawdown_pct: float | None = None,
        max_same_direction_positions: int | None = None,
        h0_shadow_mode: bool | None = None,
        # EDGE-P1b-FUP-STALE-PEAK-IPC (2026-04-26): dim 5 of EDGE-P1b T1
        #   calibrator (`time_since_peak_ms`) → `ExitConfig.stale_peak_ms`
        #   (i64 ms in schema; wire is u64 ms for parity with sibling
        #   `*_ms` IPC fields). Closes the asymmetry where this dim was
        #   TOML-only and forced calibrator into a two-step bind path
        #   (TOML edit + reload_risk_config IPC).
        # EDGE-P1b-FUP-STALE-PEAK-IPC（2026-04-26）：EDGE-P1b T1 calibrator
        #   第 5 維度（`time_since_peak_ms`）→ `ExitConfig.stale_peak_ms`
        #   （schema i64 ms；wire u64 ms 對齊同伴 `*_ms` IPC 欄位）。
        #   封閉先前 calibrator 必須走 TOML edit + reload_risk_config 兩步
        #   bind 的不對稱。
        exit_stale_peak_ms: int | None = None,
    ) -> dict[str, Any]:
        """
        Update risk config on Rust engine at runtime (GUI/Agent → IPC → Rust).
        運行時更新 Rust 引擎風控配置。所有參數可選，僅傳遞需要改變的。
        For Option<Option<f64>> fields (trailing/time/atr/tp): None=disable, float=set, _UNSET=no change.

        Note (2026-04-26): the 7 `exit_*` percentile fields wired in Rust
        IPC since EDGE-DIAG-1-FUP-IPC are NOT exposed on this typed wrapper —
        callers wanting the percentile bind path (e.g.
        `helper_scripts/research/exit_threshold_calibrator.py`) call
        `self.call("update_risk_config", params=raw_dict)` directly with the
        full set. Adding `exit_stale_peak_ms` here lays the groundwork for
        `restore_exit_config_defaults` and future operator CLI bindings.
        注（2026-04-26）：自 EDGE-DIAG-1-FUP-IPC 後 Rust IPC 已 wire 的 7 個
        `exit_*` 百分位欄位**未**在本 typed wrapper 暴露 — 需走百分位 bind
        路徑的 caller（如 `helper_scripts/research/exit_threshold_calibrator.py`）
        直接 `self.call("update_risk_config", params=raw_dict)` 並提供完整
        欄位集。本欄位先補上 `exit_stale_peak_ms` 為
        `restore_exit_config_defaults` 與未來 operator CLI binding 鋪路。
        """
        params = build_update_risk_config_params(
            unset_marker=EngineIPCClient._UNSET,
            hard_stop_pct=hard_stop_pct,
            p1_risk_pct=p1_risk_pct,
            trailing_stop_pct=trailing_stop_pct,
            time_stop_hours=time_stop_hours,
            atr_multiplier=atr_multiplier,
            take_profit_pct=take_profit_pct,
            max_leverage=max_leverage,
            max_drawdown_pct=max_drawdown_pct,
            max_same_direction_positions=max_same_direction_positions,
            h0_shadow_mode=h0_shadow_mode,
            exit_stale_peak_ms=exit_stale_peak_ms,
        )
        return await self.call("update_risk_config", params=params)

    # ─── Internal: connection helpers / 內部：連接輔助 ───────────────────────

    async def _try_connect(self) -> bool:
        """
        Attempt a single connection to the Unix socket.
        嘗試單次連接到 Unix 套接字。

        Returns:
            True on success, False on failure. / 成功 True，失敗 False。
        """
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_unix_connection(self._socket_path),
                timeout=3.0,  # 3s hard timeout — prevents GUI freeze during engine restart
            )
            self._connected = True
            self._reconnect_attempts = 0
            self._ai_available = True
            logger.info(
                "Connected to engine at %s / 已連接到引擎 %s",
                self._socket_path, self._socket_path,
            )
            # G-3 / SEC-08: HMAC-SHA256 auth handshake (fail-closed if secret set)
            # G-3 / SEC-08：HMAC-SHA256 認證握手（設置密鑰時 fail-closed）
            try:
                await self._authenticate()
            except Exception as exc:
                logger.error(
                    "IPC auth handshake failed — closing connection: %s / "
                    "IPC 認證握手失敗 — 關閉連線: %s",
                    exc, exc,
                )
                await self._close_connection()
                return False
            return True
        except FileNotFoundError:
            logger.warning(
                "Socket not found: %s (engine may not be running) / "
                "套接字未找到: %s（引擎可能未運行）",
                self._socket_path, self._socket_path,
            )
            return False
        except (ConnectionRefusedError, OSError) as exc:
            logger.warning(
                "Connection failed to %s: %s / 連接失敗 %s: %s",
                self._socket_path, exc, self._socket_path, exc,
            )
            return False

    async def _authenticate(self) -> None:
        """
        G-3 / SEC-08: Perform HMAC-SHA256 handshake if OPENCLAW_IPC_SECRET is set.
        G-3 / SEC-08：若設置 OPENCLAW_IPC_SECRET，執行 HMAC-SHA256 握手。

        Sends: {"jsonrpc":"2.0","method":"__auth","params":{"token":"<hex>","ts":<int>},"id":0}
        Expects: {"jsonrpc":"2.0","result":{"authenticated":true},"id":0}

        token = HMAC-SHA256(secret, str(unix_timestamp))
        Fail-closed: raises RuntimeError if secret is set but auth fails.
        Fail-closed：設置密鑰但認證失敗時拋出 RuntimeError。
        No-op: if OPENCLAW_IPC_SECRET is not set (dev/test mode).
        無操作：未設置 OPENCLAW_IPC_SECRET 時跳過（開發/測試模式）。
        """
        secret = get_secret_value("OPENCLAW_IPC_SECRET")
        if not secret:
            return  # No secret — skip auth / 無密鑰 — 跳過認證
        ts = int(time.time())
        token = _hmac_lib.new(
            secret.encode(), str(ts).encode(), hashlib.sha256
        ).hexdigest()
        request = {
            "jsonrpc": "2.0",
            "method": "__auth",
            "params": {"token": token, "ts": ts},
            "id": 0,
        }
        # E2 round 1 LOW-2 retrofit (2026-05-03): mirror the call() path —
        # ensure_ascii=False so HMAC token bytes (always hex, ASCII-clean)
        # plus future unicode-bearing auth fields stay byte-equal to Rust
        # serde_json. See call() above for full rationale.
        # E2 round 1 LOW-2 retrofit（2026-05-03）：與 call() 路徑同步加
        # ensure_ascii=False，讓 HMAC token（hex 純 ASCII）與未來 unicode
        # auth 欄位皆與 Rust serde_json byte-equal。詳見上方 call()。
        payload = json.dumps(
            request, separators=(",", ":"), ensure_ascii=False
        ) + "\n"
        if self._writer is None:
            raise RuntimeError("IPC auth: writer is None (not connected)")
        self._writer.write(payload.encode("utf-8"))
        await self._writer.drain()
        if self._reader is None:
            raise RuntimeError("IPC auth: reader is None (not connected)")
        raw = await asyncio.wait_for(self._reader.readline(), timeout=5.0)
        if not raw:
            raise RuntimeError("IPC auth: empty response from server")
        resp = json.loads(raw.decode("utf-8").strip())
        if resp.get("error"):
            raise RuntimeError(
                f"IPC auth rejected: {resp['error'].get('message', resp['error'])}"
            )
        logger.info("IPC HMAC-SHA256 auth handshake succeeded / IPC 認證握手成功")

    # ── OC-3: Reconciler / risk runtime status ──────────────────────────────

    async def get_risk_runtime_status(self) -> dict[str, Any]:
        """
        OC-3: Return current risk governor tier and reconciler runtime state.
        OC-3：返回當前風控 governor tier 及對帳器運行狀態。

        Returns dict with keys:
          governor_tier: str  ("NORMAL" | "CAUTIOUS" | "REDUCED" | "DEFENSIVE" |
                               "CIRCUIT_BREAKER" | "MANUAL_REVIEW")
          consecutive_losses_by_symbol: dict
          boot_cooldown_remaining_ms: int
          paper_paused: bool
          session_halted: bool
        """
        return await self.call("get_risk_runtime_status")

    async def _close_connection(self) -> None:
        """
        Close the underlying socket streams.
        關閉底層套接字流。
        """
        self._connected = False
        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass  # Best-effort close / 盡力關閉
        self._reader = None
        self._writer = None

    async def _send_and_receive(
        self, payload: str, request_id: int
    ) -> dict[str, Any]:
        """
        Write a JSON-RPC request and read the response line.
        寫入 JSON-RPC 請求並讀取響應行。

        Args:
            payload: Newline-terminated JSON string / 換行結尾的 JSON 字符串
            request_id: Expected response ID / 預期的響應 ID

        Returns:
            Parsed result from the JSON-RPC response / 解析後的 result 字段
        """
        if self._writer is None or self._reader is None:
            raise EngineDisconnectedError(
                "No active connection (writer/reader is None) / "
                "無活躍連接（writer/reader 為 None）"
            )

        self._writer.write(payload.encode("utf-8"))
        await self._writer.drain()

        raw_line = await self._reader.readline()
        if not raw_line:
            raise ConnectionError(
                "Empty response (connection closed) / 空響應（連接已關閉）"
            )

        response = json.loads(raw_line.decode("utf-8"))

        # Validate JSON-RPC response / 驗證 JSON-RPC 響應
        if response.get("id") != request_id:
            logger.warning(
                "Response ID mismatch: expected=%d got=%s / "
                "響應 ID 不匹配：預期=%d 實際=%s",
                request_id, response.get("id"),
                request_id, response.get("id"),
            )

        if "error" in response:
            error = response["error"]
            raise RuntimeError(
                f"Engine RPC error [{error.get('code')}]: {error.get('message')} / "
                f"引擎 RPC 錯誤 [{error.get('code')}]: {error.get('message')}"
            )

        return response.get("result", {})

    # ─── Internal: reconnection / 內部：重連 ─────────────────────────────────

    async def _handle_disconnect(self) -> None:
        """
        Handle an unexpected disconnection: close and start reconnect loop.
        處理意外斷連：關閉連接並啟動重連循環。
        """
        await self._close_connection()

        # Only start one reconnect loop at a time / 同時只啟動一個重連循環
        if self._reconnect_task is None or self._reconnect_task.done():
            self._reconnect_task = asyncio.create_task(self._reconnect_loop())

    async def _reconnect_loop(self) -> None:
        """
        Attempt reconnection with exponential backoff.
        以指數退避策略嘗試重連。

        After MAX_RECONNECT_ATTEMPTS consecutive failures, enters fallback mode
        (ai_available=False) and retries every FALLBACK_RETRY_INTERVAL seconds.
        連續 MAX_RECONNECT_ATTEMPTS 次失敗後進入降級模式（ai_available=False），
        之後每 FALLBACK_RETRY_INTERVAL 秒重試一次。
        """
        self._reconnect_attempts = 0

        # Phase 1: exponential backoff, up to MAX_RECONNECT_ATTEMPTS
        # 階段 1：指數退避，最多 MAX_RECONNECT_ATTEMPTS 次
        while self._reconnect_attempts < MAX_RECONNECT_ATTEMPTS:
            delay = min(
                RECONNECT_BASE_DELAY * (RECONNECT_FACTOR ** self._reconnect_attempts),
                RECONNECT_MAX_DELAY,
            )
            logger.info(
                "Reconnect attempt %d/%d in %.1fs / "
                "重連嘗試 %d/%d，%.1fs 後重試",
                self._reconnect_attempts + 1, MAX_RECONNECT_ATTEMPTS, delay,
                self._reconnect_attempts + 1, MAX_RECONNECT_ATTEMPTS, delay,
            )
            await asyncio.sleep(delay)

            if await self._try_connect():
                logger.info(
                    "Reconnected successfully / 重連成功"
                )
                return

            self._reconnect_attempts += 1

        # Phase 2: fallback mode — ai_available=False, retry every 5s
        # 階段 2：降級模式 — ai_available=False，每 5 秒重試
        self._ai_available = False
        logger.warning(
            "Engine IPC failed %d times, entering fallback mode "
            "(ai_available=false, retry every %.0fs) / "
            "引擎 IPC 失敗 %d 次，進入降級模式"
            "（ai_available=false，每 %.0fs 重試）",
            MAX_RECONNECT_ATTEMPTS, FALLBACK_RETRY_INTERVAL,
            MAX_RECONNECT_ATTEMPTS, FALLBACK_RETRY_INTERVAL,
        )

        while True:
            await asyncio.sleep(FALLBACK_RETRY_INTERVAL)
            if await self._try_connect():
                logger.info(
                    "Reconnected from fallback mode / 從降級模式恢復連接"
                )
                return

from .ipc_client_sync import sync_ipc_call  # noqa: E402,F401
