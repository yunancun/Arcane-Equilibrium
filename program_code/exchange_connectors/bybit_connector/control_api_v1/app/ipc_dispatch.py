"""IPC dispatch helpers — shared JSON-RPC call-site utilities (E5-P1-5 orphan §九).
IPC 派發輔助 — 共享的 JSON-RPC 調用點工具（E5-P1-5，§九 孤兒抽取）。

MODULE_NOTE (EN):
    Across the route layer we accumulated several near-duplicate helpers that
    together form a single dispatch pattern:

      1. **one-shot call**: open a fresh ``EngineIPCClient``, ``connect()``,
         ``call(method, params, timeout)``, ``disconnect()`` in a ``finally``.
         Lives in ``paper_trading_routes._ipc_command`` and
         ``live_session_routes._ipc_command`` (byte-for-byte duplicate).

      2. **lazy singleton**: module-global ``_IPC_CLIENT`` / ``_STRATEGY_IPC``
         with ``connect()`` on first access, log-and-return-None on failure.
         Lives in ``engine_capabilities_routes._get_ipc``,
         ``risk_routes._get_direct_ipc``, ``strategy_write_routes._get_strategy_ipc``.

    This module extracts both into reusable building blocks while preserving
    existing call-site behaviour exactly:

      - :func:`one_shot_ipc_call`  – matches ``_ipc_command`` semantics (raises
        ``HTTPException(503)`` on failure for the ``live_session_routes`` variant;
        the lighter ``paper_trading_routes`` variant bubbles the raw exception and
        is opted into via ``wrap_errors_as_http=False``).
      - :func:`get_or_connect_shared_client` – matches the lazy-singleton pattern
        with either per-module slot or the shared ``_SHARED_IPC_SLOTS`` registry.

    Zero behaviour change — legacy call sites continue to work unchanged; these
    helpers are offered so new call sites stop copying the pattern.

MODULE_NOTE (中):
    路由層累積了多個近乎相同的輔助函數，實際上是同一個派發樣式：

      1. **單次呼叫**：開新 ``EngineIPCClient`` → ``connect`` → ``call`` →
         ``finally disconnect``。在 ``paper_trading_routes._ipc_command`` 與
         ``live_session_routes._ipc_command`` 為 byte-for-byte 重複。

      2. **懶加載單例**：模組級 ``_IPC_CLIENT`` / ``_STRATEGY_IPC``，首次使用時
         ``connect()``，失敗則 log 並回 ``None``。分布於
         ``engine_capabilities_routes._get_ipc``、``risk_routes._get_direct_ipc``、
         ``strategy_write_routes._get_strategy_ipc``。

    本模組把兩種樣式抽成可重用元件，行為完全不變：

      - :func:`one_shot_ipc_call`  – 對應 ``_ipc_command``（``live_session_routes``
        版本失敗拋 ``HTTPException(503)``；較輕量的 ``paper_trading_routes``
        版本原樣傳遞例外，用 ``wrap_errors_as_http=False`` 選入）。
      - :func:`get_or_connect_shared_client` – 對應懶加載單例，可使用模組自定
        槽位或 ``_SHARED_IPC_SLOTS`` 全局註冊表。

    零行為變動 — 舊調用點保持原樣；新的調用點不再重寫這段樣板。

Safety guarantees / 安全保證:
  - Fail-closed: all dispatch paths propagate or raise; no silent swallow.
  - Disconnect always runs in ``finally`` for one-shot variant.
  - Shared singleton connect failure returns ``None`` (caller decides policy).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import HTTPException

from .ipc_error_handler import raise_http_for_ipc_error

logger = logging.getLogger(__name__)


# ─── Shared singleton registry / 共享單例註冊表 ─────────────────────────────
#
# Callers may supply their own module-level slot, or opt into this in-module
# registry keyed by string (useful for ad-hoc dispatchers that don't want to
# declare their own global).
# 呼叫方可自備模組級槽位，或用字串鍵加入此模組內的註冊表（適合不想宣告
# 自己全局變數的臨時派發點）。
_SHARED_IPC_SLOTS: dict[str, Any] = {}
_SHARED_SLOT_LOCK = asyncio.Lock()


# ─── One-shot dispatch / 單次派發 ───────────────────────────────────────────

async def one_shot_ipc_call(
    method: str,
    params: dict[str, Any] | None = None,
    *,
    timeout: float = 5.0,
    wrap_errors_as_http: bool = True,
    error_context: str = "ipc_command",
    client_factory: Any = None,
) -> dict[str, Any]:
    """One-shot connect → call → disconnect against the Rust engine.
    對 Rust 引擎執行一次性的「連線→呼叫→斷線」流程。

    Preserves the existing ``_ipc_command`` contract:

      - ``wrap_errors_as_http=True`` (default, matches ``live_session_routes``):
        any failure is reclassified through :func:`raise_http_for_ipc_error`
        (``HTTPException(503 / 504)`` depending on exception kind).
      - ``wrap_errors_as_http=False`` (matches ``paper_trading_routes``):
        raw exception propagates to the caller.

    Returns the JSON-RPC ``result`` field. When Rust returns a non-dict value
    (e.g. ``"pong"``), we wrap it in ``{"result": <value>}`` so the contract
    ``dict[str, Any]`` still holds — mirrors ``live_session_routes``.

    與既有 ``_ipc_command`` 契約一致：``wrap_errors_as_http=True`` 時失敗轉
    ``HTTPException``；``False`` 時原樣拋出。回傳 JSON-RPC ``result`` 欄位；
    Rust 回非 dict 值時包成 ``{"result": <value>}``，與 ``live_session_routes``
    相同。

    :param method:               JSON-RPC method name / JSON-RPC 方法名。
    :param params:               optional params dict / 可選參數字典。
    :param timeout:              per-call timeout seconds / 每次呼叫的超時秒數。
    :param wrap_errors_as_http:  see above / 見上。
    :param error_context:        tag used when wrapping errors as HTTP.
                                 包裝為 HTTP 錯誤時使用的上下文標籤。
    :param client_factory:       override for ``EngineIPCClient()`` — lets tests
                                 inject a mock without patching the module.
                                 覆寫 ``EngineIPCClient()`` 供測試注入 mock。
    """
    if client_factory is None:
        # Lazy import so this module stays importable in tests without a socket.
        # 延遲匯入，讓測試環境即便沒有 socket 也能匯入本模組。
        from .ipc_client import EngineIPCClient  # noqa: PLC0415
        client = EngineIPCClient()
    else:
        client = client_factory()

    try:
        await client.connect()
        result = await client.call(method, params=params or {}, timeout=timeout)
        if isinstance(result, dict):
            return result
        # Non-dict result — wrap so the public signature holds / 非 dict 結果包裝
        return {"result": result}
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 — reclassify below
        if wrap_errors_as_http:
            raise_http_for_ipc_error(exc, context=error_context, log=logger)
        raise
    finally:
        try:
            await client.disconnect()
        except Exception:  # noqa: BLE001 — best-effort close
            pass


# ─── Lazy singleton dispatch / 懶加載單例派發 ───────────────────────────────

async def get_or_connect_shared_client(
    slot_key: str,
    *,
    log: logging.Logger | None = None,
    client_factory: Any = None,
    reconnect_if_disconnected: bool = True,
) -> Any | None:
    """Return a lazily-connected ``EngineIPCClient`` from the shared registry.
    從共享註冊表取得一個懶連線的 ``EngineIPCClient``。

    On first access, constructs an ``EngineIPCClient``, calls ``connect()``,
    and stores it under ``slot_key``. Subsequent calls return the same
    instance. Connection failure logs a warning and returns ``None`` — mirrors
    ``engine_capabilities_routes._get_ipc`` fail-soft semantics.

    首次存取時建構 ``EngineIPCClient``、呼叫 ``connect()``、以 ``slot_key`` 快取；
    之後呼叫沿用同一個實例。連線失敗記 warning 回 ``None``，對應
    ``engine_capabilities_routes._get_ipc`` 的 fail-soft。

    :param slot_key:                    registry key (e.g. ``"capabilities"``).
                                        註冊表鍵值。
    :param log:                         optional caller logger.
                                        可選呼叫方 logger。
    :param client_factory:              override for ``EngineIPCClient()``.
                                        覆寫 ``EngineIPCClient()``。
    :param reconnect_if_disconnected:   if ``True`` (default), verifies the
                                        cached client is still connected and
                                        reconnects on demand. ``False`` returns
                                        the cached instance without checking.
                                        預設會在回傳前確認連線仍有效並視需要重連；
                                        ``False`` 則直接回傳快取實例。
    """
    _log = log or logger

    async with _SHARED_SLOT_LOCK:
        cached = _SHARED_IPC_SLOTS.get(slot_key)
        if cached is not None:
            if reconnect_if_disconnected and not getattr(cached, "is_connected", True):
                try:
                    await cached.connect()
                except Exception as exc:  # noqa: BLE001
                    _log.warning(
                        "ipc_dispatch[%s]: reconnect failed: %s / 重新連線失敗",
                        slot_key, exc,
                    )
                    return None
            return cached

        if client_factory is None:
            from .ipc_client import EngineIPCClient  # noqa: PLC0415
            client = EngineIPCClient()
        else:
            client = client_factory()

        try:
            await client.connect()
        except Exception as exc:  # noqa: BLE001
            _log.warning(
                "ipc_dispatch[%s]: initial connect failed: %s / 初次連線失敗",
                slot_key, exc,
            )
            return None

        _SHARED_IPC_SLOTS[slot_key] = client
        return client


async def reset_shared_client(slot_key: str) -> None:
    """Drop (and best-effort disconnect) a cached shared client.
    丟棄（並盡力斷線）快取中的共享 client。

    Useful for tests that need a clean slate, or for reconnect-after-auth-fail
    flows. No-op if the slot is empty.
    測試需要乾淨環境、或認證失敗後需重新連線時使用；槽位空時為 no-op。
    """
    async with _SHARED_SLOT_LOCK:
        client = _SHARED_IPC_SLOTS.pop(slot_key, None)
    if client is None:
        return
    try:
        await client.disconnect()
    except Exception:  # noqa: BLE001 — best-effort
        pass


__all__ = [
    "one_shot_ipc_call",
    "get_or_connect_shared_client",
    "reset_shared_client",
]
