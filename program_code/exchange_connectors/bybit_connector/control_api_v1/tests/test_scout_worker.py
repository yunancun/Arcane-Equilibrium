"""
Test suite for ScoutWorker daemon thread.
ScoutWorker daemon 線程的測試套件。

Coverage:
- Daemon thread creation and start
- Thread stop / graceful shutdown
- scan_fn is called after interval
- scan_fn exception does NOT crash the worker
- Double start() is idempotent (no second thread)

覆蓋範圍：
- daemon 線程創建與啟動
- 線程停止 / 優雅停機
- 間隔後 scan_fn 被調用
- scan_fn 拋出異常不崩潰 worker
- 連續兩次 start() 不創建第二個線程（冪等）
"""

import threading
import time
import unittest

# Import the module under test.
# 導入被測模塊。
import sys
import os

# Ensure the app directory is on the path so the import resolves.
# 確保 app 目錄在 sys.path 上，使導入能成功解析。
_APP_DIR = os.path.join(
    os.path.dirname(__file__),
    "..",
    "app",
)
if _APP_DIR not in sys.path:
    sys.path.insert(0, os.path.abspath(_APP_DIR))

from scout_worker import ScoutWorker


class TestScoutWorkerStartsAsDaemon(unittest.TestCase):
    """ScoutWorker 啟動後必須是 daemon 線程。"""

    def test_scout_worker_starts_daemon_thread(self):
        """
        After start(), the worker thread is alive and daemon=True.
        start() 後工作線程必須存活且 daemon=True。
        """
        scan_called = threading.Event()

        def _scan():
            scan_called.set()

        worker = ScoutWorker(scan_fn=_scan, interval_seconds=9999)  # Large interval — won't trigger
        try:
            worker.start()
            self.assertTrue(worker._thread is not None, "Thread should be created")
            self.assertTrue(worker._thread.is_alive(), "Thread must be alive after start()")
            self.assertTrue(worker._thread.daemon, "Thread must be daemon=True")
            self.assertTrue(worker.is_alive, "is_alive property must return True")
        finally:
            worker.stop(timeout=2.0)

    def test_scout_worker_thread_name(self):
        """
        Worker thread should be named 'ScoutWorker' for easy identification in logs.
        工作線程名稱應為 'ScoutWorker'，方便在日誌中識別。
        """
        worker = ScoutWorker(scan_fn=lambda: None, interval_seconds=9999)
        try:
            worker.start()
            self.assertEqual(worker._thread.name, "ScoutWorker")
        finally:
            worker.stop(timeout=2.0)


class TestScoutWorkerStop(unittest.TestCase):
    """ScoutWorker 停止行為測試。"""

    def test_scout_worker_stops(self):
        """
        After stop(), the thread is no longer alive within timeout.
        stop() 後，線程在 timeout 內必須不再存活。
        """
        worker = ScoutWorker(scan_fn=lambda: None, interval_seconds=9999)
        worker.start()
        self.assertTrue(worker.is_alive)

        worker.stop(timeout=3.0)
        # Thread should be dead (or at least stop event is set)
        # 線程應已退出（或停止事件已設置）
        self.assertTrue(
            worker._stop_event.is_set(),
            "Stop event must be set after stop()",
        )
        # Give the thread up to 3 seconds to actually exit
        # 給線程最多 3 秒真正退出
        if worker._thread is not None:
            worker._thread.join(timeout=3.0)
        self.assertFalse(
            worker._thread.is_alive() if worker._thread else False,
            "Thread must be dead after stop()",
        )

    def test_scout_worker_is_alive_false_after_stop(self):
        """
        is_alive returns False after stop().
        stop() 後 is_alive 應返回 False。
        """
        worker = ScoutWorker(scan_fn=lambda: None, interval_seconds=9999)
        worker.start()
        worker.stop(timeout=3.0)
        if worker._thread is not None:
            worker._thread.join(timeout=3.0)
        self.assertFalse(worker.is_alive)


class TestScoutWorkerCallsScanFn(unittest.TestCase):
    """ScoutWorker 應在間隔後調用 scan_fn。"""

    def test_scout_worker_calls_scan_fn(self):
        """
        scan_fn is called at least once within 2x the interval.
        scan_fn 必須在 2 倍間隔時間內至少被調用一次。
        """
        scan_called = threading.Event()

        def _scan():
            scan_called.set()

        # Use a very short interval (0.1 seconds) for testing speed.
        # 使用非常短的間隔（0.1 秒）加快測試速度。
        worker = ScoutWorker(scan_fn=_scan, interval_seconds=1)
        try:
            worker.start()
            # Wait up to 5 seconds for scan to be called
            # 等待最多 5 秒確認 scan 被調用
            called = scan_called.wait(timeout=5.0)
            self.assertTrue(called, "scan_fn must be called within the interval")
        finally:
            worker.stop(timeout=2.0)

    def test_scout_worker_calls_scan_fn_multiple_times(self):
        """
        scan_fn is called more than once if the worker runs long enough.
        若 worker 運行足夠長時間，scan_fn 應被調用多次。
        """
        call_count = [0]
        lock = threading.Lock()

        def _scan():
            with lock:
                call_count[0] += 1

        worker = ScoutWorker(scan_fn=_scan, interval_seconds=1)
        try:
            worker.start()
            # Wait long enough for at least 2 scan cycles (2 × 1s + buffer)
            # 等待足夠長確認至少 2 次掃描週期
            time.sleep(3.5)
            with lock:
                count = call_count[0]
            self.assertGreaterEqual(count, 2, f"scan_fn should be called ≥2 times, got {count}")
        finally:
            worker.stop(timeout=2.0)


class TestScoutWorkerScanErrorNoCrash(unittest.TestCase):
    """scan_fn 拋出異常時，worker 線程不可崩潰。"""

    def test_scout_worker_scan_error_no_crash(self):
        """
        If scan_fn raises an Exception, the worker thread keeps running.
        若 scan_fn 拋出異常，worker 線程必須繼續運行（不可崩潰）。
        """
        call_count = [0]
        lock = threading.Lock()

        def _failing_scan():
            with lock:
                call_count[0] += 1
            raise RuntimeError("Simulated scan failure / 模擬掃描失敗")

        worker = ScoutWorker(scan_fn=_failing_scan, interval_seconds=1)
        try:
            worker.start()
            # Let it run through 2+ scan cycles even with failures
            # 即使失敗也讓它完成 2+ 掃描週期
            time.sleep(3.5)
            self.assertTrue(
                worker.is_alive,
                "Worker thread must still be alive after scan failures",
            )
            with lock:
                count = call_count[0]
            self.assertGreaterEqual(
                count, 2,
                f"scan_fn should be called ≥2 times despite failures, got {count}",
            )
        finally:
            worker.stop(timeout=2.0)

    def test_scout_worker_scan_value_error_no_crash(self):
        """
        ValueError in scan_fn does not crash the worker.
        ValueError 也不應崩潰 worker。
        """
        def _value_error_scan():
            raise ValueError("bad value / 錯誤值")

        worker = ScoutWorker(scan_fn=_value_error_scan, interval_seconds=1)
        try:
            worker.start()
            time.sleep(2.5)
            self.assertTrue(worker.is_alive, "Worker must survive ValueError in scan_fn")
        finally:
            worker.stop(timeout=2.0)


class TestScoutWorkerDoubleStart(unittest.TestCase):
    """連續兩次 start() 應冪等，不創建第二個線程。"""

    def test_scout_worker_double_start_ignored(self):
        """
        Calling start() twice does not create a second thread.
        連續兩次 start() 不創建第二個線程（冪等）。
        """
        worker = ScoutWorker(scan_fn=lambda: None, interval_seconds=9999)
        try:
            worker.start()
            first_thread = worker._thread

            # Second start() — must not replace or add a thread
            # 第二次 start() — 不可替換或新增線程
            worker.start()
            second_thread = worker._thread

            self.assertIs(
                first_thread,
                second_thread,
                "Double start() must not create a new thread",
            )
            # Both references point to the same alive thread
            # 兩個引用必須指向同一個存活線程
            self.assertTrue(first_thread.is_alive())
        finally:
            worker.stop(timeout=2.0)

    def test_scout_worker_start_after_stop_creates_new_thread(self):
        """
        After stop(), calling start() again creates a new thread (restart support).
        stop() 後再次調用 start() 應創建新線程（支持重啟）。
        """
        worker = ScoutWorker(scan_fn=lambda: None, interval_seconds=9999)
        worker.start()
        first_thread = worker._thread
        worker.stop(timeout=3.0)
        if first_thread is not None:
            first_thread.join(timeout=3.0)

        # Restart
        # 重啟
        worker.start()
        second_thread = worker._thread
        try:
            self.assertIsNotNone(second_thread, "New thread must be created after restart")
            self.assertTrue(second_thread.is_alive(), "Restarted thread must be alive")
        finally:
            worker.stop(timeout=2.0)


if __name__ == "__main__":
    unittest.main()
