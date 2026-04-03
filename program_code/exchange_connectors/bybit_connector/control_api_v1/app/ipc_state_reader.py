# MODULE_NOTE:
# IPC State Reader — file-based read of Rust engine pipeline snapshot (R06-B).
# IPC 狀態讀取器 — 基於文件讀取 Rust 引擎管線快照。
#
# Reads pipeline_snapshot.json written by Rust StateWriter (5s debounce).
# Provides cached, thread-safe access to paper state, latest prices, and tick stats.
# Falls back gracefully when the file is missing or stale (engine not running).
#
# 讀取 Rust StateWriter 寫入的 pipeline_snapshot.json（5 秒去抖）。
# 提供緩存的、線程安全的 paper state、最新價格和 tick 統計訪問。
# 當文件缺失或過期時（引擎未運行）優雅降級。

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Cache TTL — re-read file at most every 2 seconds to reduce I/O
# 緩存 TTL — 最多每 2 秒重讀文件以減少 I/O
_CACHE_TTL_SECONDS = 2.0

# Snapshot staleness threshold — data older than this is considered stale
# 快照過期閾值 — 超過此時間的數據視為過期
_STALENESS_THRESHOLD_SECONDS = 60.0


class RustSnapshotReader:
    """
    Thread-safe cached reader for Rust engine's pipeline_snapshot.json.
    線程安全的緩存讀取器，用於讀取 Rust 引擎的 pipeline_snapshot.json。

    Usage / 用法:
        reader = RustSnapshotReader()
        state = reader.get_paper_state()   # dict or None
        prices = reader.get_latest_prices() # dict or None
        stats = reader.get_tick_stats()     # dict or None
    """

    def __init__(self, data_dir: Optional[str] = None) -> None:
        self._data_dir = data_dir or os.environ.get(
            "OPENCLAW_DATA_DIR", "/tmp/openclaw"
        )
        self._lock = threading.Lock()
        self._cache: Optional[dict[str, Any]] = None
        self._cache_ts: float = 0.0

    @property
    def snapshot_path(self) -> Path:
        """Path to the pipeline snapshot file / 管線快照文件路徑"""
        return Path(self._data_dir) / "pipeline_snapshot.json"

    def _refresh_cache(self) -> Optional[dict[str, Any]]:
        """
        Re-read snapshot file if cache is stale.
        如果緩存過期則重新讀取快照文件。
        """
        now = time.monotonic()
        if self._cache is not None and (now - self._cache_ts) < _CACHE_TTL_SECONDS:
            return self._cache

        path = self.snapshot_path
        try:
            raw = path.read_text(encoding="utf-8")
            data = json.loads(raw)
            self._cache = data
            self._cache_ts = now
            return data
        except FileNotFoundError:
            logger.debug(
                "RustSnapshotReader: snapshot not found at %s — engine may not be running "
                "/ 快照文件未找到 — 引擎可能未運行",
                path,
            )
            return None
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(
                "RustSnapshotReader: failed to read snapshot: %s / 讀取快照失敗：%s",
                exc, exc,
            )
            return None

    def is_available(self) -> bool:
        """
        Check if Rust engine snapshot is available and fresh.
        檢查 Rust 引擎快照是否可用且未過期。
        """
        with self._lock:
            data = self._refresh_cache()
        if data is None:
            return False
        # Check file modification time for staleness / 檢查文件修改時間判斷是否過期
        try:
            mtime = self.snapshot_path.stat().st_mtime
            age = time.time() - mtime
            return age < _STALENESS_THRESHOLD_SECONDS
        except OSError:
            return False

    def get_snapshot(self) -> Optional[dict[str, Any]]:
        """
        Get the full pipeline snapshot (or None if unavailable).
        獲取完整管線快照（不可用時返回 None）。
        """
        with self._lock:
            return self._refresh_cache()

    def get_paper_state(self) -> Optional[dict[str, Any]]:
        """
        Get paper trading state (balance, positions, pnl, fees).
        獲取紙盤交易狀態（餘額、持倉、損益、手續費）。
        """
        snap = self.get_snapshot()
        return snap.get("paper_state") if snap else None

    def get_latest_prices(self) -> Optional[dict[str, float]]:
        """
        Get latest per-symbol prices from Rust engine.
        從 Rust 引擎獲取每交易對最新價格。
        """
        snap = self.get_snapshot()
        return snap.get("latest_prices") if snap else None

    def get_tick_stats(self) -> Optional[dict[str, Any]]:
        """
        Get tick processing statistics.
        獲取 tick 處理統計。
        """
        snap = self.get_snapshot()
        return snap.get("stats") if snap else None

    def get_source(self) -> Optional[str]:
        """
        Get data source tag (should be 'rust_engine').
        獲取數據源標識（應為 'rust_engine'）。
        """
        snap = self.get_snapshot()
        return snap.get("source") if snap else None


# ═══════════════════════════════════════════════════════════════════════════════
# Module-level singleton / 模組級單例
# ═══════════════════════════════════════════════════════════════════════════════

_READER: Optional[RustSnapshotReader] = None
_READER_LOCK = threading.Lock()


def get_rust_reader() -> RustSnapshotReader:
    """
    Get or create the module-level RustSnapshotReader singleton.
    獲取或創建模組級 RustSnapshotReader 單例。
    """
    global _READER
    if _READER is None:
        with _READER_LOCK:
            if _READER is None:
                _READER = RustSnapshotReader()
    return _READER
