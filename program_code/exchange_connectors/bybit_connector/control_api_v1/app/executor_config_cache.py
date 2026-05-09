from __future__ import annotations

"""
W-AUDIT-9 T3 — ExecutorAgent stage-aware runtime config cache（Rust IPC 視圖）。

MODULE_NOTE：
  Rust ``RiskConfig.executor`` 子欄位的 process-global 快取。AMD-2026-05-09-03
  把 binary `shadow_mode` 升級為 5-stage graduated canary cohort
  (`CanaryStage`)，本檔提供 Python 端 mirror enum + stage-aware provider，
  並保留 `shadow_mode_provider()` 作 backward-compat lambda（Stage 0 → True；
  Stage ≥ 1 → False）。

  graduated canary 5 階段（per AMD-2026-05-09-03 §2.2）：
    Stage 0  SHADOW              fail-closed shadow，不送 intent 到 Rust
    Stage 1  PAPER_SINGLE_COHORT 1 strategy × 1 symbol × paper（7d 觀察）
    Stage 2  DEMO_SINGLE_COHORT  1 strategy × 1 symbol × demo（14d 觀察）
    Stage 3  DEMO_FULL_UNIVERSE  5 active strategies × demo（21d 觀察）
    Stage 4  LIVE_PENDING        operator 顯式拍板（不自動升級）

  fail-closed 不變式（**critical**, TODO v19 §5 invariant 9）：
    IPC failure / cache miss / schema fail / provider exception → Stage 0
    （**不是** Stage 1）。break 即雞蛋死循環復活。

  backward-compat（AMD §2.3 + §4.4）：
    - legacy `shadow_mode: true` ⇔ canary_stage = Stage 0
    - legacy `shadow_mode: false` 但無 `canary_stage` 欄位 → fail-closed
      reject 至 Stage 0 + log（不再合法 once W-AUDIT-9 land）
    - `shadow_mode_provider()` 仍可用：Stage 0 → True，Stage ≥ 1 → False

  設計：
    - daemon thread 每 N 秒呼叫 IPC ``get_risk_config`` 拉 ``executor`` 子切片
    - 不可變 dataclass snapshot；lock 下原子交換
    - 首次成功前 IPC 失敗 → 維持 fail-closed Stage 0
    - 首次成功後瞬時 IPC 錯誤 → 保留前一個 good snapshot（graceful degrade）

  公開 API：
    ``get_executor_config_cache()`` / ``start_polling`` / ``stop_polling`` /
    ``get`` / ``is_initialized`` / ``shadow_mode_provider`` /
    ``canary_stage_provider``（W-AUDIT-9 新）

  Singleton registry（CLAUDE.md §九）：``_CACHE_INSTANCE``。
"""

import asyncio
import enum
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


class CanaryStage(enum.IntEnum):
    """W-AUDIT-9 T3 — 5-stage graduated canary cohort（mirror Rust）。

    與 Rust 端 ``ExecutorRiskConfig.canary_stage: u8 (0..=4)`` 命名 / 序值對齊
    （PA `2026-05-09--full_dispatch_engineering_plan.md` §2.2 T3；schema 通過
    IPC payload 對齊，本端不需等 Rust commit hash）。

    fail-closed 不變式：任何不可解析 / out-of-range / IPC 失敗 → Stage 0。
    """

    SHADOW = 0                # binary fail-closed；不送 intent；對應 legacy `shadow_mode=True`
    PAPER_SINGLE_COHORT = 1   # 1 strategy × 1 symbol × paper（7d 觀察期）
    DEMO_SINGLE_COHORT = 2    # 1 strategy × 1 symbol × demo（14d 觀察期）
    DEMO_FULL_UNIVERSE = 3    # 5 active strategies × demo（21d 觀察期）
    LIVE_PENDING = 4          # operator 顯式拍板（不自動升級）

    @classmethod
    def from_raw(cls, value: Any) -> "CanaryStage":
        """fail-closed parse：任何異常值返回 SHADOW（Stage 0）。

        允許 int 0..=4 / 對應 IntEnum 實例 / 字串「0」..「4」。
        out-of-range / None / 型別錯誤 → 一律 fall back SHADOW（**不是** Stage 1）。
        """
        if value is None:
            return cls.SHADOW
        if isinstance(value, cls):
            return value
        try:
            int_val = int(value)
        except (TypeError, ValueError):
            return cls.SHADOW
        if 0 <= int_val <= 4:
            return cls(int_val)
        return cls.SHADOW


# Conservative defaults matching Rust ExecutorConfig::default()。
# 與 Rust ExecutorConfig::default() 對齊的保守預設。
_DEFAULT_SHADOW_MODE: bool = True       # 原則 #6 fail-closed（legacy projection）
_DEFAULT_CANARY_STAGE: CanaryStage = CanaryStage.SHADOW  # invariant 9 fail-closed
_DEFAULT_MAX_POSITION_PCT: float = 0.05  # 5% — matches Rust default
_DEFAULT_POLL_SEC: float = 10.0
_MIN_POLL_SEC: float = 0.5  # guardrail vs. typo'd env values


@dataclass(frozen=True)
class CanaryCohort:
    """W-AUDIT-9 — Stage 1/2 cohort scope（per AMD-2026-05-09-03 §2.4）。

    Stage 0 / 3 / 4 全 universe：strategy / symbol 為 None（cohort 整體可為 None）。
    Stage 1 / 2 必填 strategy + symbol（由 operator 在 Settings tab 顯式選擇）。
    """

    strategy: Optional[str] = None
    symbol: Optional[str] = None
    environment: Optional[str] = None  # 'paper' | 'demo' | 'live_demo' | 'mainnet'


@dataclass(frozen=True)
class ExecutorRuntimeConfig:
    """Rust RiskConfig.executor 子切片的不可變快照。

    與 Rust 的 ``ExecutorConfig`` 結構獨立（RFC §5.2：刻意拆開 Python 型別，
    內建 fail-closed 預設）。

    W-AUDIT-9 新欄位（per AMD-2026-05-09-03 §2.1, §4.4）：
      - canary_stage: 0..=4，預設 SHADOW（fail-closed）
      - canary_cohort: Stage 1/2 cohort scope
      - stage_entered_at_ms: stage 進入時間戳（毫秒）
      - observation_period_ms: 當前 stage 觀察期長度

    backward-compat：legacy `shadow_mode` 仍保留，等同 `(canary_stage == 0)`
    投影。
    """

    # Legacy projection：`shadow_mode = (canary_stage == SHADOW)`。
    # 保留為 backward-compat；新代碼讀 ``canary_stage`` 為主。
    shadow_mode: bool = _DEFAULT_SHADOW_MODE
    canary_stage: CanaryStage = _DEFAULT_CANARY_STAGE
    canary_cohort: Optional[CanaryCohort] = None
    stage_entered_at_ms: int = 0    # Stage 0 永久；非 0 = stage 進入時間
    observation_period_ms: int = 0  # Stage 0 不觀察（0）；其他 stage = spec 觀察期
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

    def shadow_mode_provider(self) -> Callable[..., bool]:
        """W-AUDIT-9 backward-compat：Stage 0 → True；Stage ≥ 1 → False。

        舊 ExecutorAgent ctor 簽名仍以 ``shadow_mode_provider: Callable[..., bool]``
        為主；本 lambda 包裝 ``canary_stage_provider`` 以維持 zero-impact migration。

        invariant 9：fail-closed Stage 0（**不是** Stage 1）→ True
        （legacy semantic：log intent，不下單）。
        """
        stage_provider = self.canary_stage_provider()

        def _provider(engine: Optional[str] = None) -> bool:
            stage = stage_provider(engine)
            return stage == CanaryStage.SHADOW

        return _provider

    def canary_stage_provider(self) -> Callable[..., "CanaryStage"]:
        """W-AUDIT-9 T3：回傳 stage-aware callable。

        每次呼叫回傳當前 ``CanaryStage``（per AMD-2026-05-09-03 §2.1）。
        ExecutorAgent ctor 升級後可注入此 provider；舊 ctor 仍可用
        ``shadow_mode_provider()`` lambda 包裝。

        fail-closed semantic（**critical**, TODO v19 §5 invariant 9）：
          - cache 未初始化 → SHADOW
          - IPC 失敗 / schema 異常 → SHADOW（**不是** PAPER_SINGLE_COHORT）
          - explicit engine arg 跨 engine fetch 失敗 → SHADOW
          - provider 內任何 exception → SHADOW（caller 不應拋出）
        """
        def _provider(engine: Optional[str] = None) -> "CanaryStage":
            try:
                normalized = _normalize_engine_name(engine)
                if normalized is None or normalized == self._engine:
                    return self.get().canary_stage
                return self._fetch_via_ipc_blocking(engine=normalized).canary_stage
            except Exception as exc:  # noqa: BLE001 — 任何錯誤一律 fail-closed Stage 0
                logger.warning(
                    "canary_stage_provider exception engine=%s exc=%s — "
                    "fail-closed Stage 0（**不是** Stage 1）",
                    engine or "default", exc,
                )
                return CanaryStage.SHADOW

        return _provider

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

    def _fetch_via_ipc_blocking(self, engine: Optional[str] = None) -> ExecutorRuntimeConfig:
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

        selected_engine = _normalize_engine_name(engine) or self._engine

        async def _call() -> dict:
            return await one_shot_ipc_call(
                "get_risk_config",
                params={"engine": selected_engine},
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
        """從 get_risk_config 回應抽出 executor 子切片；缺漏/異常時走 fail-closed 預設。

        W-AUDIT-9 T3 升級：
          - 解析 ``canary_stage`` / ``canary_cohort`` / ``stage_entered_at_ms`` /
            ``observation_period_ms`` 4 欄
          - **backward-compat reject**（per AMD-2026-05-09-03 §4.4）：
            legacy `shadow_mode=false` 但無 `canary_stage` 欄位（或 stage=0）
            → fail-closed reject 至 Stage 0 + log
          - shadow_mode 仍為 `(canary_stage == SHADOW)` projection（避免兩欄
            互相矛盾的隱含風險）
        """
        if not isinstance(resp, dict):
            raise ValueError(f"unexpected IPC response type: {type(resp).__name__}")
        config_obj = resp.get("config") if isinstance(resp.get("config"), dict) else None
        if config_obj is None:
            # 部分 handler 直接平鋪 config 於 result 或頂層。
            if isinstance(resp.get("result"), dict):
                config_obj = resp["result"].get("config", resp["result"])
            else:
                config_obj = resp
        executor_blob = config_obj.get("executor") if isinstance(config_obj, dict) else None
        if not isinstance(executor_blob, dict):
            raise ValueError("IPC response missing `executor` sub-config")

        # ── shadow_mode legacy 解析（保留 raw 以做 §4.4 backward-compat reject）──
        shadow_raw = executor_blob.get("shadow_mode", _DEFAULT_SHADOW_MODE)
        if not isinstance(shadow_raw, bool):
            shadow_raw = _DEFAULT_SHADOW_MODE

        # ── canary_stage 解析（W-AUDIT-9 T3 SoT）──
        # 缺欄 / out-of-range / 型別錯誤 → CanaryStage.from_raw fail-closed Stage 0。
        stage_raw = executor_blob.get("canary_stage")
        canary_stage = CanaryStage.from_raw(stage_raw)

        # ── §4.4 backward-compat reject ──
        # legacy `shadow_mode=false` 但 `canary_stage` 缺欄 / Stage 0 → reject。
        # 這是 AMD-2026-05-09-03 §4.4 明文：legacy `shadow_mode=false` 在 IMPL
        # wave land 後**不再合法**；不可繞過 5-stage canary 直接 live-equivalent。
        if shadow_raw is False and stage_raw is None:
            logger.warning(
                "executor_config_cache: legacy shadow_mode=False without "
                "canary_stage detected — fail-closed reject Stage 0 "
                "（per AMD-2026-05-09-03 §4.4 backward-compat reject）",
            )
            canary_stage = CanaryStage.SHADOW
        elif shadow_raw is False and canary_stage == CanaryStage.SHADOW:
            # legacy `shadow_mode=false` 但 stage=0：兩欄矛盾。同樣 reject。
            logger.warning(
                "executor_config_cache: legacy shadow_mode=False conflicts "
                "with canary_stage=0 — fail-closed reject Stage 0",
            )

        # ── canary_cohort 解析（Stage 1/2 必填，其他 stage 可空）──
        cohort_blob = executor_blob.get("canary_cohort")
        cohort: Optional[CanaryCohort] = None
        if isinstance(cohort_blob, dict):
            strategy_val = cohort_blob.get("strategy")
            symbol_val = cohort_blob.get("symbol")
            env_val = cohort_blob.get("environment")
            cohort = CanaryCohort(
                strategy=strategy_val if isinstance(strategy_val, str) else None,
                symbol=symbol_val if isinstance(symbol_val, str) else None,
                environment=env_val if isinstance(env_val, str) else None,
            )

        # ── stage_entered_at_ms / observation_period_ms ──
        stage_entered_raw = executor_blob.get("stage_entered_at_ms", 0)
        try:
            stage_entered = int(stage_entered_raw) if stage_entered_raw is not None else 0
        except (TypeError, ValueError):
            stage_entered = 0
        obs_period_raw = executor_blob.get("observation_period_ms", 0)
        try:
            obs_period = int(obs_period_raw) if obs_period_raw is not None else 0
        except (TypeError, ValueError):
            obs_period = 0

        # ── max_position_pct / per_symbol_position_cap（既有邏輯）──
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

        # shadow_mode 改為 stage 投影：保「stage 0 ⇔ shadow_mode true」不變式
        # 避免兩欄分歧（legacy 場景 shadow=true 配 stage=0 視同 SHADOW；
        # 升級到 stage>=1 後 shadow=false 投影自動成立）。
        shadow_projected = canary_stage == CanaryStage.SHADOW

        return ExecutorRuntimeConfig(
            shadow_mode=shadow_projected,
            canary_stage=canary_stage,
            canary_cohort=cohort,
            stage_entered_at_ms=stage_entered,
            observation_period_ms=obs_period,
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


def _normalize_engine_name(engine: Optional[str]) -> Optional[str]:
    if engine is None:
        return None
    value = str(engine).strip().lower()
    if value == "live_demo":
        return "live"
    if value in {"paper", "demo", "live"}:
        return value
    return None


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
    "CanaryStage",
    "CanaryCohort",
    "ExecutorRuntimeConfig",
    "ExecutorConfigCache",
    "get_executor_config_cache",
]
