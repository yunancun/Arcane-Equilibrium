"""
MODULE_NOTE:
ScoutWorker — Background daemon thread for periodic market scanning.
ScoutWorker — 後台定時掃描 Daemon 線程，每 30 分鐘自動觸發全品種情報掃描。

Layer: Execution Layer (E1) — wraps MarketScanner.scan() with a timed loop.
所屬層次：執行層（E1）— 以定時循環包裝 MarketScanner.scan()，讓掃描定期自動觸發。

Principle 15: Multi-Agent Collaboration — Scout produces intel via ScoutAgent → MessageBus
  → Strategist chain. ScoutWorker is the trigger layer; it is NOT responsible for intel
  routing (that belongs to ScoutAgent.produce_intel).
原則 15：多 Agent 協作 — Scout 通過 ScoutAgent → MessageBus → Strategist 鏈路注入情報。
  ScoutWorker 只是觸發層，不負責情報路由（路由屬於 ScoutAgent.produce_intel 的職責）。

Design constraints / 設計約束:
- Uses daemon thread: terminates automatically when main process exits, no blocking.
  使用 daemon 線程：主進程退出時自動終止，不阻塞進程結束。
- Interruptible sleep (1-second chunks): stop() returns within ~1 second.
  可中斷睡眠（1 秒分段）：stop() 在約 1 秒內響應，不長時間阻塞。
- Scan failure must not crash the worker thread (logged, then continue).
  掃描失敗不可導致 worker 線程崩潰：記錄異常後繼續下一輪循環。
- Double-start is idempotent: second start() is ignored if thread is alive.
  雙重啟動冪等：若線程已在運行，第二次 start() 靜默忽略。
"""

import logging
import threading
import time
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# Default scan interval: 30 minutes
# 默認掃描間隔：30 分鐘
SCAN_INTERVAL_SECONDS: int = 30 * 60


class ScoutWorker:
    """
    Periodic background worker that triggers market scanning every 30 minutes.
    定時後台工作線程，每 30 分鐘觸發一次全品種市場掃描。

    The worker wraps any callable ``scan_fn`` and calls it on the configured
    interval. It is designed to be a thin trigger layer — all intel production
    and routing logic lives in ScoutAgent / MessageBus.
    Worker 包裝任意可調用 ``scan_fn``，按設定間隔調用。
    這是一個薄薄的觸發層 — 所有情報生成與路由邏輯屬於 ScoutAgent / MessageBus。

    Thread safety: start() and stop() are safe to call from any thread.
    線程安全：start() 和 stop() 可從任意線程調用。
    """

    def __init__(
        self,
        scan_fn: Callable[[], None],
        interval_seconds: int = SCAN_INTERVAL_SECONDS,
        scan_interval_seconds: Optional[int] = None,
    ) -> None:
        """
        Initialize ScoutWorker with a scan function and interval.
        初始化 ScoutWorker，傳入掃描函數和觸發間隔。

        :param scan_fn: Callable executed once per scan cycle. Must be
            thread-safe (called from daemon thread, not the event loop).
            每輪掃描執行一次的可調用對象，必須是線程安全的（在 daemon 線程中調用）。
        :param interval_seconds: Seconds between scan cycles (default 1800 = 30 min).
            掃描間隔秒數（默認 1800 = 30 分鐘）。
        :param scan_interval_seconds: Optional override for scan interval (takes precedence
            over interval_seconds when not None). Allows runtime configuration.
            可選的掃描間隔覆蓋（非 None 時優先於 interval_seconds），支持運行時配置。
        """
        self._scan_fn: Callable[[], None] = scan_fn
        # scan_interval_seconds takes precedence when provided (runtime configurability)
        # scan_interval_seconds 非 None 時優先使用（支持運行時可配置）
        self._scan_interval: int = scan_interval_seconds if scan_interval_seconds is not None else interval_seconds
        self._interval: int = self._scan_interval
        # Event for interruptible sleep and stop signalling.
        # 用於可中斷睡眠和停止信號的事件對象。
        self._stop_event: threading.Event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ── Public API ──────────────────────────────────────────────────────────────

    def start(self) -> None:
        """
        Start the background daemon thread.
        啟動後台 daemon 線程，開始定時掃描循環。

        Idempotent: if the thread is already alive, this call is silently ignored.
        冪等：若線程已在運行，此調用靜默忽略，不創建第二個線程。
        """
        if self._thread is not None and self._thread.is_alive():
            # Already running — do not create a second thread.
            # 已在運行 — 不創建第二個線程，防止重複掃描。
            logger.warning(
                "ScoutWorker already running, ignoring duplicate start() call. "
                "/ ScoutWorker 已在運行，忽略重複的 start() 調用。"
            )
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            daemon=True,  # daemon=True: thread dies with the main process
            name="ScoutWorker",
        )
        self._thread.start()
        logger.info(
            "ScoutWorker started (interval=%ds / 間隔=%d 秒)",
            self._interval,
            self._interval,
        )

    def stop(self, timeout: float = 5.0) -> None:
        """
        Signal the worker to stop and wait for the thread to exit.
        向工作線程發出停止信號，等待線程退出。

        Used for graceful shutdown and in tests. The thread will exit within
        at most one sleep-chunk (1 second) after the signal is set.
        用於優雅停機和測試。發出信號後，線程最多在 1 秒內退出。

        :param timeout: Max seconds to wait for thread join (default 5.0).
            等待線程退出的最長秒數（默認 5.0）。
        """
        # Signal the loop to exit at the next sleep-chunk boundary.
        # 通知循環在下一個睡眠分段邊界退出。
        self._stop_event.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        logger.info("ScoutWorker stopped / ScoutWorker 已停止")

    @property
    def is_alive(self) -> bool:
        """
        Return True if the worker thread is currently running.
        若工作線程當前正在運行，返回 True。
        """
        return self._thread is not None and self._thread.is_alive()

    # ── Internal loop ───────────────────────────────────────────────────────────

    def _run_loop(self) -> None:
        """
        Main worker loop: sleep for interval then trigger scan, repeat until stopped.
        主工作循環：等待間隔後觸發掃描，循環直到收到停止信號。

        Uses 1-second interruptible sleep chunks so that stop() can respond
        promptly rather than waiting for the full interval to elapse.
        使用 1 秒分段睡眠實現可中斷等待，確保 stop() 可快速響應，不需等待完整間隔。

        Scan exceptions are caught and logged but do NOT crash the thread.
        掃描異常被捕獲並記錄，但不會使 worker 線程崩潰（記錄後繼續下一輪）。
        """
        logger.info(
            "ScoutWorker loop started (interval=%ds) / ScoutWorker 循環開始（間隔=%d 秒）",
            self._interval,
            self._interval,
        )
        while not self._stop_event.is_set():
            # --- Interruptible sleep ---
            # Sleep in 1-second chunks so stop() can break the loop quickly.
            # 分 1 秒小段睡眠，確保 stop() 能快速打斷循環。
            for _ in range(self._interval):
                if self._stop_event.is_set():
                    logger.debug("ScoutWorker stop event detected during sleep / 睡眠期間收到停止信號")
                    return
                time.sleep(1)

            # --- Trigger scan ---
            # Scan failure must not crash the worker; log and continue next cycle.
            # 掃描失敗不可崩潰 worker；記錄異常後繼續下一輪循環（生存優先原則）。
            try:
                logger.info(
                    "ScoutWorker triggering scan cycle / ScoutWorker 觸發掃描週期"
                )
                self._scan_fn()
                logger.info(
                    "ScoutWorker scan cycle completed / ScoutWorker 掃描週期完成"
                )
            except Exception as exc:
                # Swallowing the exception here is intentional: the worker must
                # survive individual scan failures to continue future cycles.
                # 此處吞掉異常是刻意設計：worker 必須在單次掃描失敗後存活並繼續。
                logger.error(
                    "ScoutWorker scan failed (%s): %s — continuing next cycle. "
                    "/ ScoutWorker 掃描失敗（%s）：%s — 繼續下一輪循環。",
                    type(exc).__name__,
                    exc,
                    type(exc).__name__,
                    exc,
                )

        logger.info("ScoutWorker loop exited cleanly / ScoutWorker 循環正常退出")
