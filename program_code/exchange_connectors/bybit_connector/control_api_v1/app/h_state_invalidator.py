from __future__ import annotations

"""
G3-08 Phase 1 Sub-task B — H-state invalidator (Python → Rust hint channel).
G3-08 Phase 1 Sub-task B — H 狀態失效通知器（Python → Rust 提示通道）。

MODULE_NOTE (EN):
  Phase 1 Python-side counterpart of the Rust ``h_state_cache``. Provides a
  process-global, fire-and-forget invalidator that nudges the Rust cache to
  trigger an ad-hoc poll right after a Python H1-H5 / 5-Agent state change,
  rather than waiting for the next scheduled 10s daemon poll. Pattern mirrors
  G3-03 ``ExecutorConfigCache`` (commit ``51608fe``) — module-level singleton +
  ``threading.Lock`` for thread-safe init/reset — but flips the data flow:

    G3-03 (ExecutorConfigCache): Rust = SSOT  →  Python pulls.
    G3-08 (HStateInvalidator) :  Python = SSOT  →  Python pushes invalidation
                                                   hints, Rust pulls full
                                                   snapshot when prompted.

  Strict DEFAULT-OFF semantics (per PA design §4.5 + §8.1):
    - ``OPENCLAW_H_STATE_GATEWAY != "1"`` → ``init_h_state_invalidator()`` is
      a no-op, ``invalidate_async()`` is a no-op, ``get_invalidator()`` returns
      ``None``. Zero overhead, zero side effects when disabled.
    - ``OPENCLAW_H_STATE_GATEWAY == "1"`` → singleton constructed on first
      ``init_h_state_invalidator()`` call; subsequent calls dedup.
      ``invalidate_async(reason)`` spawns a daemon thread that opens a private
      ``EngineIPCClient``, sends ``invalidate_h_state`` JSON-RPC notification,
      then disconnects. All exceptions silenced (fire-and-forget, non-fatal).

  Why ``threading.Thread`` (not ``asyncio.create_task``):
    - H1-H5 / 5-Agent call sites span sync (``StrategistAgent.evaluate`` is sync)
      and async contexts; a uniform sync API that internally spins a private
      ``asyncio.run`` is simpler than detecting the caller's loop and avoids
      "loop already running" errors during pytest fixtures.
    - Daemon threads die with the process; no graceful shutdown bookkeeping
      required for a fire-and-forget hint channel.

  Failure semantics (per CLAUDE.md §二 principle #6 fail-closed):
    - IPC connect / send / disconnect failures: logged at DEBUG, silenced.
    - The Rust cache's 10s scheduled poll always still happens regardless; a
      missed invalidation hint costs ≤ 10s of staleness, never correctness.
    - No retry, no backoff: either the next state change re-invalidates, or
      the scheduled daemon poll catches up.

  Public API:
    - ``init_h_state_invalidator(ipc_client_factory=None)`` — env-gated
      singleton constructor (idempotent).
    - ``invalidate_async(reason: str)`` — fire-and-forget invalidation hint
      (no-op when env disabled or singleton not initialised).
    - ``get_invalidator()`` — current singleton (or ``None`` when off).
    - ``is_gateway_enabled()`` — strict ``"1"`` env check.
    - ``_reset_for_tests()`` — drop singleton, reset state for unit tests.

  Singleton registry (CLAUDE.md §九, registered in Sub-task C):
    ``_H_STATE_INVALIDATOR`` (this module).

MODULE_NOTE (中):
  G3-08 Phase 1 的 Python 端對應，與 Rust 端 ``h_state_cache`` 配套：在 H1-H5 /
  5-Agent 狀態變化後立即發 fire-and-forget 提示給 Rust 端，提早一次 ad-hoc poll
  而不必等 10s 排程 daemon。設計鏡射 G3-03 ``ExecutorConfigCache``（commit
  ``51608fe``）—— 模組級 singleton + ``threading.Lock`` 線程安全 init/reset；
  但**資料流相反**：

    G3-03（ExecutorConfigCache）：Rust = SSOT，Python pull。
    G3-08（HStateInvalidator）  ：Python = SSOT，Python push 失效提示，
                                  Rust 視 hint 觸發 pull 拉完整 snapshot。

  嚴格 DEFAULT-OFF（PA design §4.5 + §8.1）：
    - ``OPENCLAW_H_STATE_GATEWAY != "1"``：``init_h_state_invalidator()`` 為
      no-op，``invalidate_async()`` 為 no-op，``get_invalidator()`` 回 ``None``。
      零負擔、零副作用。
    - ``OPENCLAW_H_STATE_GATEWAY == "1"``：首次 init 建立 singleton，後續 init
      去重；``invalidate_async(reason)`` 起 daemon thread 開私有
      ``EngineIPCClient``、發 ``invalidate_h_state`` JSON-RPC 通知、斷線。
      所有例外被吞（fire-and-forget，非致命）。

  為何用 ``threading.Thread`` 而非 ``asyncio.create_task``：
    - H1-H5 / 5-Agent 呼叫點橫跨同步（``StrategistAgent.evaluate`` 為 sync）
      與非同步情境；統一同步 API + 內部短命 ``asyncio.run`` 比偵測呼叫端 loop
      簡單，亦避免 pytest fixture 中「loop already running」錯誤。
    - daemon thread 隨進程退出；fire-and-forget 提示通道無須優雅關閉記帳。

  失敗語意（對齊 CLAUDE.md §二 原則 #6 fail-closed）：
    - IPC connect/send/disconnect 例外：DEBUG 記錄後吞掉。
    - Rust 端 10s 排程 poll 永遠仍會發生；漏掉一次提示最多多 ≤ 10s 過時，
      不會破壞正確性。
    - 不重試、不退避：要嘛下次 state change 再 invalidate、要嘛排程 poll 補位。

  公開 API：
    - ``init_h_state_invalidator(ipc_client_factory=None)`` — env-gated
      singleton 建構子（冪等）。
    - ``invalidate_async(reason: str)`` — fire-and-forget 提示
      （env 關閉或未 init 時 no-op）。
    - ``get_invalidator()`` — 當前 singleton（off 時為 ``None``）。
    - ``is_gateway_enabled()`` — 嚴格 ``"1"`` env 檢查。
    - ``_reset_for_tests()`` — 釋放 singleton、重置狀態（測試用）。

  Singleton 登記（CLAUDE.md §九，由 Sub-task C 補登）：``_H_STATE_INVALIDATOR``。
"""

import asyncio
import logging
import os
import threading
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# ── Constants / 常數 ────────────────────────────────────────────────────────

# Strict env-gate value per PA design §4.5 (mirrors ExecutorConfigCache /
# Rust h_state_poller spawn condition). Anything other than "1" → disabled.
# 嚴格 env 閘值（對齊 PA §4.5 與 Rust h_state_poller spawn 條件），
# 非 "1" 一律視為關閉。
_GATEWAY_ENV_VAR: str = "OPENCLAW_H_STATE_GATEWAY"
_GATEWAY_ENABLED_VALUE: str = "1"

# IPC method name (must match Rust dispatch arm — see PA §4.4 / §5.1).
# IPC method 名稱（須與 Rust dispatch arm 對齊 — 見 PA §4.4 / §5.1）。
_INVALIDATE_METHOD: str = "invalidate_h_state"

# Per-call IPC timeout. Short because we're notify-style (fire-and-forget);
# we only care about getting bytes onto the socket, not the response.
# 單次 IPC 逾時（短，因為是 notify 風格 fire-and-forget；
# 我們只關心字節打進 socket，不在乎回應）。
_INVALIDATE_TIMEOUT_S: float = 2.0


def is_gateway_enabled() -> bool:
    """Strict env-gate: True iff env var equals exactly ``"1"``.
    嚴格 env 閘檢查：env 變數恰為 ``"1"`` 才回 True。"""
    return os.environ.get(_GATEWAY_ENV_VAR) == _GATEWAY_ENABLED_VALUE


# ── HStateInvalidator class / HStateInvalidator 類 ───────────────────────────


class HStateInvalidator:
    """Process-global fire-and-forget invalidator for H-state cache hints.
    H 狀態快取提示的進程全域 fire-and-forget 通知器。

    Construction is private (``__init__``); callers must use
    ``init_h_state_invalidator()`` + ``get_invalidator()`` / ``invalidate_async()``.
    建構為私有（``__init__``）；呼叫端僅使用 ``init_h_state_invalidator()``
    與 ``get_invalidator()`` / ``invalidate_async()``。
    """

    def __init__(
        self,
        *,
        ipc_client_factory: Optional[Callable[[], Any]] = None,
    ) -> None:
        # Optional factory injection lets tests substitute a mock client.
        # Production callers leave this None → factory uses lazy import of
        # ``EngineIPCClient`` from ``ipc_client``.
        # Optional factory 讓測試可注入 mock client；生產端傳 None 時走 lazy
        # import ``EngineIPCClient``。
        self._ipc_client_factory: Optional[Callable[[], Any]] = ipc_client_factory
        # Stats (mostly for tests / debug; cheap atomic-ish counters).
        # 統計（測試/除錯用，廉價 atomic-ish 計數器）。
        self._stats_lock: threading.Lock = threading.Lock()
        self._invalidations_attempted: int = 0
        self._invalidations_dispatched: int = 0
        self._invalidations_failed: int = 0

    # ── Public API / 公開 API ──

    def invalidate(self, reason: str) -> None:
        """Spawn a daemon thread to send one invalidation hint to Rust.
        Returns immediately (does not block caller).
        起一條 daemon thread 發送一次提示給 Rust；立即返回，不阻塞呼叫者。

        Errors are silenced (DEBUG log only). The Rust cache's scheduled poll
        will catch up within ~10s if a hint is lost.
        錯誤被吞（僅 DEBUG 記錄）。即使提示遺失，Rust 排程 poll 約 10s 內補位。
        """
        with self._stats_lock:
            self._invalidations_attempted += 1
        thread = threading.Thread(
            target=self._dispatch_one,
            args=(reason,),
            name="h-state-invalidate",
            daemon=True,
        )
        thread.start()

    # ── Internal: dispatch worker / 內部：派發 worker ──

    def _dispatch_one(self, reason: str) -> None:
        """Run one IPC invalidate call synchronously inside a private event loop.
        Always silences exceptions — this is fire-and-forget per PA design §4.3.
        在私有 event loop 中同步跑一次 IPC 呼叫；永遠吞例外（PA §4.3 fire-and-forget）。
        """
        loop: Optional[asyncio.AbstractEventLoop] = None
        try:
            loop = asyncio.new_event_loop()
            loop.run_until_complete(self._call_invalidate_ipc(reason))
            with self._stats_lock:
                self._invalidations_dispatched += 1
        except Exception as exc:  # noqa: BLE001 — fire-and-forget, silence all
            with self._stats_lock:
                self._invalidations_failed += 1
            # DEBUG-level only; do NOT raise — see MODULE_NOTE failure semantics.
            # 僅 DEBUG 記錄；絕不 raise — 見 MODULE_NOTE 失敗語意。
            logger.debug(
                "h_state_invalidator: IPC dispatch failed (reason=%s): %s "
                "/ IPC 派發失敗，已吞例外",
                reason, exc,
            )
        finally:
            if loop is not None:
                try:
                    loop.close()
                except Exception:  # noqa: BLE001 — best effort cleanup
                    pass

    async def _call_invalidate_ipc(self, reason: str) -> None:
        """Single connect → call → disconnect cycle. Caller catches all errors.
        單次「連線→呼叫→斷線」循環；例外由呼叫端統一捕獲。
        """
        client = self._build_ipc_client()
        try:
            await client.connect()
            # We piggyback on ``call`` (request-response) for transport
            # compatibility with the existing ``EngineIPCClient`` API. Rust side
            # treats this as a notification (response is just an ack); we send
            # but do not require anything specific in the response.
            # 沿用 ``call``（request-response）以相容既有 ``EngineIPCClient``；
            # Rust 側視為 notification（回應僅為 ack），我們不檢查回應內容。
            await client.call(
                _INVALIDATE_METHOD,
                params={"reason": reason},
                timeout=_INVALIDATE_TIMEOUT_S,
            )
        finally:
            try:
                await client.disconnect()
            except Exception:  # noqa: BLE001 — best-effort close
                pass

    def _build_ipc_client(self) -> Any:
        """Construct a per-call ``EngineIPCClient`` (or use the injected factory).
        Lazy-imports ``EngineIPCClient`` so this module stays importable in
        environments without a socket (e.g. test fixtures).
        建構 per-call ``EngineIPCClient``（或使用注入的 factory）；
        延遲 import 讓無 socket 的環境（如測試 fixture）也能 import 本模組。
        """
        if self._ipc_client_factory is not None:
            return self._ipc_client_factory()
        # Lazy import. / 延遲匯入。
        from .ipc_client import EngineIPCClient  # noqa: PLC0415
        return EngineIPCClient()

    # ── Stats accessors (test / debug) / 統計存取（測試/除錯）──

    def stats_snapshot(self) -> dict[str, int]:
        """Return a thread-safe shallow copy of internal counters.
        回傳內部計數器的線程安全淺拷貝。"""
        with self._stats_lock:
            return {
                "attempted": self._invalidations_attempted,
                "dispatched": self._invalidations_dispatched,
                "failed": self._invalidations_failed,
            }


# ── Module-level singleton (CLAUDE.md §九 registry, Sub-task C) ──────────────

_H_STATE_INVALIDATOR: Optional[HStateInvalidator] = None
_LOCK: threading.Lock = threading.Lock()


def init_h_state_invalidator(
    *,
    ipc_client_factory: Optional[Callable[[], Any]] = None,
    force: bool = False,
) -> Optional[HStateInvalidator]:
    """Idempotent env-gated singleton constructor.
    冪等的 env-gated singleton 建構子。

    Behaviour:
      - When env disabled (``OPENCLAW_H_STATE_GATEWAY != "1"``) and
        ``force`` is False: returns ``None`` without constructing anything.
        Subsequent ``invalidate_async`` calls become no-ops.
      - When env enabled OR ``force=True`` (test override): constructs the
        singleton on first call; subsequent calls dedup and return the
        existing instance (``ipc_client_factory`` argument is ignored after
        first init — by design, to keep the singleton's behaviour stable).
      - Returns the active singleton (or ``None`` when disabled).

    行為：
      - env 關閉且 ``force=False``：回 ``None``，不建構任何物件；
        之後 ``invalidate_async`` 全為 no-op。
      - env 開啟或 ``force=True``（測試覆寫）：首次呼叫建構 singleton，
        之後去重並回相同實例（首次後 ``ipc_client_factory`` 參數會忽略，
        刻意設計以保持 singleton 行為穩定）。
      - 回傳當前 singleton（關閉時 ``None``）。
    """
    global _H_STATE_INVALIDATOR
    if not force and not is_gateway_enabled():
        # DEFAULT-OFF: stay no-op, do NOT construct.
        # DEFAULT-OFF：保持 no-op，不建構。
        return None
    # Double-checked-lock idiom: cheap fast-path, lock only on construction.
    # 雙重檢查鎖：快速路徑免鎖，僅建構時上鎖。
    if _H_STATE_INVALIDATOR is None:
        with _LOCK:
            if _H_STATE_INVALIDATOR is None:
                _H_STATE_INVALIDATOR = HStateInvalidator(
                    ipc_client_factory=ipc_client_factory,
                )
                logger.info(
                    "HStateInvalidator initialised (env=%s) "
                    "/ HStateInvalidator 已初始化（env=%s）",
                    os.environ.get(_GATEWAY_ENV_VAR, ""),
                    os.environ.get(_GATEWAY_ENV_VAR, ""),
                )
    return _H_STATE_INVALIDATOR


def get_invalidator() -> Optional[HStateInvalidator]:
    """Return the current singleton (or ``None`` when disabled / pre-init).
    回傳當前 singleton（關閉或尚未 init 時為 ``None``）。
    """
    return _H_STATE_INVALIDATOR


def invalidate_async(reason: str) -> None:
    """Fire-and-forget invalidation hint to the Rust h_state_cache.
    對 Rust h_state_cache 發送 fire-and-forget 失效提示。

    No-op when:
      - Env-gate is off (``OPENCLAW_H_STATE_GATEWAY != "1"``).
      - Singleton has not been ``init_h_state_invalidator()``-ed yet.

    Always returns immediately; never blocks the caller.
    Caller need NOT wrap in try/except — exceptions are silenced internally.

    no-op 條件：
      - env 閘關閉（``OPENCLAW_H_STATE_GATEWAY != "1"``）。
      - singleton 尚未 ``init_h_state_invalidator()``。

    永遠立即返回；不阻塞呼叫者；呼叫端**毋須** try/except — 例外於內部吞掉。
    """
    inv = _H_STATE_INVALIDATOR
    if inv is None:
        return
    try:
        inv.invalidate(reason)
    except Exception as exc:  # noqa: BLE001 — outer guard; never raise
        # Belt-and-braces: even thread spawn could conceivably fail under
        # extreme resource pressure. Keep the contract: never raise from this
        # function. Per CLAUDE.md §二 principle #6 fail-closed.
        # 雙保險：thread spawn 在資源極端緊張下亦可能失敗；契約不變
        # —— 本函數永不 raise（CLAUDE.md §二 原則 #6 fail-closed）。
        logger.debug(
            "invalidate_async: outer guard caught (reason=%s): %s "
            "/ 外層守衛捕獲，已吞例外",
            reason, exc,
        )


def _reset_for_tests() -> None:
    """Test-only: drop the module singleton.
    測試專用：丟棄模組 singleton。

    Does not interrupt in-flight daemon threads (they will complete or fail
    silently). Tests using mock clients should arrange ``side_effect`` /
    completion expectations themselves.
    不中斷在飛 daemon thread（自行完成或靜默失敗）；用 mock client 的測試
    應自備 ``side_effect`` / 完成條件。
    """
    global _H_STATE_INVALIDATOR
    with _LOCK:
        _H_STATE_INVALIDATOR = None


__all__ = [
    "HStateInvalidator",
    "init_h_state_invalidator",
    "get_invalidator",
    "invalidate_async",
    "is_gateway_enabled",
]
