from __future__ import annotations

"""
G3-03 Phase B — ExecutorAgent runtime config cache (Rust IPC view).
G3-03 Phase B — ExecutorAgent runtime 配置快取（Rust IPC 視圖）。

MODULE_NOTE (EN):
  Provides a process-global cache of the ExecutorConfig sub-slice of Rust's
  authoritative RiskConfig (Phase A landed `RiskConfig.executor`). Removes the
  hardcoded ``ExecutorAgent._shadow_mode = True`` class attribute (CLAUDE.md §二
  principle #3 violation) by routing the runtime check through this cache.

  Design:
    - Background daemon thread polls IPC ``get_risk_config`` every N seconds
      (default 10s; configurable via env ``OPENCLAW_EXECUTOR_CACHE_POLL_SEC``).
    - Reads only the ``executor.{shadow_mode, max_position_pct,
      per_symbol_position_cap}`` sub-slice; ignores the rest of RiskConfig.
    - Snapshots are immutable dataclasses, swapped atomically under a lock.
    - **Fail-closed default**: if first IPC fetch has not yet succeeded (or
      schema is malformed), ``get().shadow_mode`` returns ``True`` (safe — log
      intents but DO NOT submit orders).  Per CLAUDE.md §二 principle #6.
    - On transient IPC errors after the first success, retain the previous
      good snapshot (graceful degrade).

  Public API:
    - ``get_executor_config_cache()`` — module singleton getter.
    - ``cache.start_polling()`` / ``cache.stop_polling()`` — lifecycle.
    - ``cache.get()`` — current snapshot (always safe; fail-closed default).
    - ``cache.is_initialized()`` — True after first successful IPC fetch.
    - ``shadow_mode_provider()`` — lambda for ``ExecutorAgent`` constructor.

  Singleton registry (CLAUDE.md §九): ``_EXECUTOR_CONFIG_CACHE``.

MODULE_NOTE (中):
  Rust ``RiskConfig.executor`` 子欄位的 process-global 快取（Phase A 已落 schema）。
  取代 ``ExecutorAgent._shadow_mode = True`` 類別屬性硬編碼（違反根原則 #3）。

  設計：
    - daemon thread 每 N 秒（預設 10s，env ``OPENCLAW_EXECUTOR_CACHE_POLL_SEC``）
      呼叫 IPC ``get_risk_config`` 拉取 ``executor`` 子切片。
    - 不可變 dataclass snapshot，於 lock 下原子交換。
    - **失敗關閉預設**：首次 IPC 尚未成功（或 schema 異常）時，
      ``get().shadow_mode`` 回 ``True``（安全：記錄意圖但**不**提交）。
    - 首次成功後若遇瞬時 IPC 錯誤，保留前一個好 snapshot（優雅降級）。

  公開 API：``get_executor_config_cache()`` / ``start_polling`` /
  ``stop_polling`` / ``get`` / ``is_initialized`` / ``shadow_mode_provider``。
"""

import asyncio
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional

logger = logging.getLogger(__name__)


# Conservative defaults matching Rust ExecutorConfig::default() (Phase A).
# 與 Phase A Rust ExecutorConfig::default() 對齊的保守預設。
_DEFAULT_SHADOW_MODE: bool = True       # principle #6 fail-closed
_DEFAULT_MAX_POSITION_PCT: float = 0.05  # 5% — matches Rust default
_DEFAULT_POLL_SEC: float = 10.0
_MIN_POLL_SEC: float = 0.5  # guardrail vs. typo'd env values


@dataclass(frozen=True)
class ExecutorRuntimeConfig:
    """Immutable snapshot of the executor sub-slice of Rust RiskConfig.
    Rust RiskConfig.executor 子切片的不可變快照。

    Independent of Rust's ``ExecutorConfig`` struct (Python local typing
    deliberately separate per RFC §5.2 — typed for IDE autocomplete, with
    fail-closed defaults baked in via factory).
    與 Rust 的 ``ExecutorConfig`` 結構獨立（RFC §5.2：刻意拆開 Python 型別，
    內建 fail-closed 預設）。
    """

    shadow_mode: bool = _DEFAULT_SHADOW_MODE
    max_position_pct: float = _DEFAULT_MAX_POSITION_PCT
    per_symbol_position_cap: Dict[str, float] = field(default_factory=dict)
    config_version: int = 0  # Rust ConfigStore version; 0 = pre-init
    fetched_at_ms: int = 0   # local wall-clock of last successful fetch


def _read_poll_interval_seconds() -> float:
    """Resolve poll interval from env, with floor.
    從 env 解析 poll 間隔，含下限保護。"""
    raw = os.environ.get("OPENCLAW_EXECUTOR_CACHE_POLL_SEC")
    if not raw:
        return _DEFAULT_POLL_SEC
    try:
        val = float(raw)
    except ValueError:
        logger.warning(
            "OPENCLAW_EXECUTOR_CACHE_POLL_SEC=%r not a float, using default %.1fs",
            raw, _DEFAULT_POLL_SEC,
        )
        return _DEFAULT_POLL_SEC
    if val < _MIN_POLL_SEC:
        logger.warning(
            "OPENCLAW_EXECUTOR_CACHE_POLL_SEC=%.3fs below floor %.3fs, clamping",
            val, _MIN_POLL_SEC,
        )
        return _MIN_POLL_SEC
    return val


def _resolve_engine_mode() -> str:
    """Resolve which engine slot's RiskConfig to read.

    Mirrors the convention used elsewhere (paper / demo / live). Default
    "paper" to match Rust ``risk_stores.select`` fallback.

    解析要讀哪一個引擎槽位的 RiskConfig。預設 "paper" 對齊 Rust 後端。
    """
    return (
        os.environ.get("OPENCLAW_ENGINE_MODE")
        or os.environ.get("OPENCLAW_EXECUTOR_CACHE_ENGINE")
        or "paper"
    )


class ExecutorConfigCache:
    """Process-global cache of Rust ``RiskConfig.executor`` sub-slice.
    Rust ``RiskConfig.executor`` 子切片的 process-global 快取。

    Thread-safe reads, fail-closed default before first IPC success.
    Read 線程安全；首次 IPC 成功前走 fail-closed 預設。
    """

    def __init__(
        self,
        *,
        engine: Optional[str] = None,
        poll_interval_s: Optional[float] = None,
    ) -> None:
        self._engine: str = engine or _resolve_engine_mode()
        self._poll_interval_s: float = (
            poll_interval_s if poll_interval_s is not None else _read_poll_interval_seconds()
        )
        # Conservative starting snapshot — fail-closed shadow_mode=True.
        # 起始 snapshot：fail-closed shadow_mode=True。
        self._snapshot: ExecutorRuntimeConfig = ExecutorRuntimeConfig()
        self._snapshot_lock: threading.Lock = threading.Lock()
        self._initialized: bool = False
        self._stop_event: threading.Event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lifecycle_lock: threading.Lock = threading.Lock()
        # Stats (mostly for tests / debug). / 統計（測試/除錯用）。
        self._poll_attempts: int = 0
        self._poll_successes: int = 0
        self._poll_failures: int = 0

    # ── Public read API / 公開讀取 API ──

    def get(self) -> ExecutorRuntimeConfig:
        """Return the current snapshot (always safe; fail-closed default).
        回傳當前 snapshot（一律安全，未初始化走 fail-closed 預設）。"""
        with self._snapshot_lock:
            return self._snapshot

    def is_initialized(self) -> bool:
        """True after the first successful IPC fetch.
        首次 IPC 成功後為 True。"""
        with self._snapshot_lock:
            return self._initialized

    def shadow_mode_provider(self) -> Callable[[], bool]:
        """Return a zero-arg callable that reads current shadow_mode.
        Used by ``ExecutorAgent`` constructor's ``shadow_mode_provider`` arg.
        回傳零參 callable，供 ExecutorAgent ctor 的 shadow_mode_provider 注入。"""
        return lambda: self.get().shadow_mode

    # ── Lifecycle / 生命週期 ──

    def start_polling(self) -> None:
        """Idempotent start of background polling daemon.
        冪等啟動背景輪詢 daemon。"""
        with self._lifecycle_lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._poll_loop,
                daemon=True,
                name="executor-config-cache-poller",
            )
            self._thread.start()
        logger.info(
            "ExecutorConfigCache: polling started (engine=%s interval=%.1fs) "
            "/ ExecutorConfigCache 開始輪詢（engine=%s 間隔=%.1fs）",
            self._engine, self._poll_interval_s,
            self._engine, self._poll_interval_s,
        )

    def stop_polling(self, join_timeout: float = 5.0) -> bool:
        """Graceful shutdown of background poller. Idempotent.
        優雅關閉背景輪詢；冪等。"""
        with self._lifecycle_lock:
            self._stop_event.set()
            thread = self._thread
        if thread is None or not thread.is_alive():
            return True
        thread.join(timeout=join_timeout)
        return not thread.is_alive()

    # ── Internal: polling loop / 內部：輪詢循環 ──

    def _poll_loop(self) -> None:
        # Eager first poll so callers don't wait poll_interval_s before first
        # successful read. Subsequent polls space at poll_interval_s.
        # 立即第一次拉取，避免 caller 等 poll_interval_s 才見到首次成功讀。
        self._poll_once()
        while not self._stop_event.is_set():
            if self._stop_event.wait(timeout=self._poll_interval_s):
                return
            self._poll_once()

    def _poll_once(self) -> None:
        """One IPC fetch + atomic snapshot swap. Never raises.
        單次 IPC 拉取 + 原子 snapshot 交換；永不拋出。"""
        with self._snapshot_lock:
            self._poll_attempts += 1
        try:
            new_snapshot = self._fetch_via_ipc_blocking()
        except Exception as exc:  # noqa: BLE001 — fail-soft poller
            with self._snapshot_lock:
                self._poll_failures += 1
                already_init = self._initialized
            if already_init:
                # Retain previous good snapshot (graceful degrade per RFC §5.2).
                # 保留前一個好 snapshot（RFC §5.2 優雅降級）。
                logger.warning(
                    "ExecutorConfigCache: IPC fetch failed, retaining previous "
                    "snapshot (shadow=%s): %s / IPC 拉取失敗，保留前次 snapshot",
                    self.get().shadow_mode, exc,
                )
            else:
                # Pre-init: stay on fail-closed default shadow_mode=True.
                # 未初始化：維持 fail-closed 預設 shadow_mode=True。
                logger.warning(
                    "ExecutorConfigCache: IPC fetch failed before first init, "
                    "fail-closed shadow_mode=True: %s "
                    "/ IPC 首次拉取失敗，沿用 fail-closed 預設",
                    exc,
                )
            return
        # Success → atomic swap. / 成功 → 原子交換。
        with self._snapshot_lock:
            self._snapshot = new_snapshot
            self._initialized = True
            self._poll_successes += 1
        logger.debug(
            "ExecutorConfigCache: refreshed shadow=%s max_pos=%.4f version=%d",
            new_snapshot.shadow_mode,
            new_snapshot.max_position_pct,
            new_snapshot.config_version,
        )

    def _fetch_via_ipc_blocking(self) -> ExecutorRuntimeConfig:
        """Synchronously execute the async IPC call from this thread.

        ``one_shot_ipc_call`` is async; we own this daemon thread, so we
        spin a private event loop per call (cheap; <1ms loop creation,
        small offset relative to poll interval).
        非同步 IPC 包成同步：daemon thread 內每次 poll 起一個短命 event loop。
        """
        # Lazy import to keep cache importable in test environments without
        # the IPC client + socket installed (defensive).
        # 延遲匯入：避免測試環境缺 IPC client 時連 import 都失敗。
        from .ipc_dispatch import one_shot_ipc_call  # noqa: PLC0415

        async def _call() -> dict:
            return await one_shot_ipc_call(
                "get_risk_config",
                params={"engine": self._engine},
                timeout=2.0,
                wrap_errors_as_http=False,
                error_context="executor_config_cache",
            )

        try:
            asyncio.get_running_loop()
            # Already in an event loop (e.g. test fixture).  Use a private
            # loop in a worker thread to stay synchronous from caller's POV.
            # 已在事件迴圈中：起一個 worker thread + 私有 loop 保持同步介面。
            return self._fetch_via_private_loop(_call)
        except RuntimeError:
            # No running loop — create one for this synchronous call.
            # 無 running loop：直接建立。
            loop = asyncio.new_event_loop()
            try:
                response = loop.run_until_complete(_call())
            finally:
                loop.close()
            return self._parse_response(response)

    def _fetch_via_private_loop(self, async_fn) -> ExecutorRuntimeConfig:
        """Run an async callable on a private event loop in a worker thread.
        在 worker thread 的私有 loop 執行 async callable。"""
        result_holder: Dict[str, object] = {}

        def _runner() -> None:
            loop = asyncio.new_event_loop()
            try:
                result_holder["response"] = loop.run_until_complete(async_fn())
            except Exception as exc:  # noqa: BLE001
                result_holder["error"] = exc
            finally:
                loop.close()

        worker = threading.Thread(target=_runner, daemon=True, name="exec-cache-fetch")
        worker.start()
        worker.join(timeout=10.0)
        if worker.is_alive():
            raise TimeoutError("executor_config_cache fetch worker did not finish within 10s")
        if "error" in result_holder:
            raise result_holder["error"]  # type: ignore[misc]
        return self._parse_response(result_holder.get("response", {}))  # type: ignore[arg-type]

    @staticmethod
    def _parse_response(resp: object) -> ExecutorRuntimeConfig:
        """Extract the executor sub-slice from ``get_risk_config`` response.
        Falls back to safe defaults on missing/malformed fields (fail-closed).
        從 get_risk_config 回應抽出 executor 子切片；缺漏/異常時走安全預設。"""
        if not isinstance(resp, dict):
            raise ValueError(f"unexpected IPC response type: {type(resp).__name__}")
        config_obj = resp.get("config") if isinstance(resp.get("config"), dict) else None
        if config_obj is None:
            # Some handlers return the config directly under "result" or top-level.
            # 部分 handler 直接平鋪 config 於 result 或頂層。
            if isinstance(resp.get("result"), dict):
                config_obj = resp["result"].get("config", resp["result"])
            else:
                config_obj = resp
        executor_blob = config_obj.get("executor") if isinstance(config_obj, dict) else None
        if not isinstance(executor_blob, dict):
            raise ValueError("IPC response missing `executor` sub-config")
        # Defensive parse — keep schema mismatches behind fail-closed defaults.
        # 防禦式解析：schema 不符仍走 fail-closed 預設。
        shadow_raw = executor_blob.get("shadow_mode", _DEFAULT_SHADOW_MODE)
        if not isinstance(shadow_raw, bool):
            shadow_raw = _DEFAULT_SHADOW_MODE
        max_pos_raw = executor_blob.get("max_position_pct", _DEFAULT_MAX_POSITION_PCT)
        try:
            max_pos = float(max_pos_raw)
        except (TypeError, ValueError):
            max_pos = _DEFAULT_MAX_POSITION_PCT
        per_symbol_raw = executor_blob.get("per_symbol_position_cap", {})
        per_symbol: Dict[str, float] = {}
        if isinstance(per_symbol_raw, dict):
            for sym, val in per_symbol_raw.items():
                if not isinstance(sym, str):
                    continue
                try:
                    per_symbol[sym] = float(val)
                except (TypeError, ValueError):
                    continue
        version_raw = resp.get("version") if isinstance(resp, dict) else 0
        try:
            version = int(version_raw) if version_raw is not None else 0
        except (TypeError, ValueError):
            version = 0
        return ExecutorRuntimeConfig(
            shadow_mode=shadow_raw,
            max_position_pct=max_pos,
            per_symbol_position_cap=per_symbol,
            config_version=version,
            fetched_at_ms=int(time.time() * 1000),
        )

    # ── Test hooks / 測試掛鉤 ──

    def _inject_snapshot_for_tests(self, snapshot: ExecutorRuntimeConfig) -> None:
        """Test-only: replace snapshot atomically (does NOT mark initialized).
        測試專用：原子替換 snapshot（不改 initialized 旗標）。"""
        with self._snapshot_lock:
            self._snapshot = snapshot

    def _mark_initialized_for_tests(self) -> None:
        """Test-only: simulate post-first-fetch state.
        測試專用：模擬首次成功後狀態。"""
        with self._snapshot_lock:
            self._initialized = True

    def _stats_snapshot_for_tests(self) -> Dict[str, int]:
        with self._snapshot_lock:
            return {
                "attempts": self._poll_attempts,
                "successes": self._poll_successes,
                "failures": self._poll_failures,
            }


# ── Module-level singleton (CLAUDE.md §九 registry) ──

_CACHE_INSTANCE: Optional[ExecutorConfigCache] = None
_CACHE_LOCK: threading.Lock = threading.Lock()


def get_executor_config_cache() -> ExecutorConfigCache:
    """Return the process-global ``ExecutorConfigCache`` singleton, creating
    it on first call. Polling is NOT auto-started — caller must invoke
    ``start_polling()`` (typically in lifecycle init).
    取得 process-global ExecutorConfigCache 單例；首次呼叫時建立。
    輪詢**不自動啟動**，由生命週期初始化呼叫 ``start_polling()``。"""
    global _CACHE_INSTANCE
    if _CACHE_INSTANCE is None:
        with _CACHE_LOCK:
            if _CACHE_INSTANCE is None:
                _CACHE_INSTANCE = ExecutorConfigCache()
    return _CACHE_INSTANCE


def _reset_for_tests() -> None:
    """Test-only: drop the singleton + stop any running poller.
    測試專用：丟棄單例並關閉 poller。"""
    global _CACHE_INSTANCE
    with _CACHE_LOCK:
        if _CACHE_INSTANCE is not None:
            try:
                _CACHE_INSTANCE.stop_polling(join_timeout=2.0)
            except Exception:  # noqa: BLE001 — best effort
                pass
        _CACHE_INSTANCE = None


__all__ = [
    "ExecutorRuntimeConfig",
    "ExecutorConfigCache",
    "get_executor_config_cache",
]
