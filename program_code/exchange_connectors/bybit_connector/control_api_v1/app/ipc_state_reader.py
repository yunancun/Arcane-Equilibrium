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
        self._cache_file_age: float = 999999.0  # seconds since last snapshot write

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
            mtime = path.stat().st_mtime
            self._cache_file_age = time.time() - mtime
            raw = path.read_text(encoding="utf-8")
            data = json.loads(raw)
            self._cache = data
            self._cache_ts = now
            return data
        except FileNotFoundError:
            self._cache_file_age = 999999.0
            logger.debug(
                "RustSnapshotReader: snapshot not found at %s — engine may not be running "
                "/ 快照文件未找到 — 引擎可能未運行",
                path,
            )
            return None
        except (json.JSONDecodeError, OSError) as exc:
            self._cache_file_age = 999999.0
            logger.warning(
                "RustSnapshotReader: failed to read snapshot: %s / 讀取快照失敗：%s",
                exc, exc,
            )
            return None

    def is_available(self) -> bool:
        """
        Check if Rust engine snapshot is available and fresh.
        檢查 Rust 引擎快照是否可用且未過期。
        Uses file mtime cached alongside data to avoid extra stat() calls.
        使用與數據一起緩存的 mtime，避免額外 stat() 調用。
        """
        with self._lock:
            data = self._refresh_cache()
        if data is None:
            return False
        # Use mtime captured during _refresh_cache, not an extra stat() call
        # 使用 _refresh_cache 時捕獲的 mtime，不做額外 stat()
        return self._cache_file_age < _STALENESS_THRESHOLD_SECONDS

    def get_snapshot(self) -> Optional[dict[str, Any]]:
        """
        Get the full pipeline snapshot (or None if unavailable).
        獲取完整管線快照（不可用時返回 None）。
        """
        with self._lock:
            return self._refresh_cache()

    def get_paper_state(self, mode: str = "paper") -> Optional[dict[str, Any]]:
        """
        Get paper trading state (balance, positions, pnl, fees).
        Phase 4: accepts `mode` param to query a specific engine mode.
        Default "paper" for backward compatibility.
        獲取紙盤交易狀態（餘額、持倉、損益、手續費）。
        Phase 4：接受 `mode` 參數查詢特定引擎模式，默認 "paper" 向後兼容。
        """
        snap = self.get_snapshot()
        if snap is None:
            return None
        # Phase 4: check mode_snapshots first for the requested mode.
        # Phase 4：優先從 mode_snapshots 查找請求的模式。
        mode_snapshots = snap.get("mode_snapshots", {})
        if mode in mode_snapshots:
            return mode_snapshots[mode].get("paper_state")
        # Fallback: top-level paper_state (primary mode / backward compat).
        # TradingMode serde: "paper_only" / "demo" / "live"; db_mode: "paper" / "demo" / "live".
        # Accept both forms for backward compatibility.
        # 回退：頂層 paper_state（主模式 / 向後兼容）。
        # 接受兩種形式（serde 和 db_mode）。
        trading_mode = snap.get("trading_mode", "paper_only")
        _MODE_ALIASES = {"paper": "paper_only", "paper_only": "paper"}
        if mode == trading_mode or _MODE_ALIASES.get(mode) == trading_mode:
            return snap.get("paper_state")
        return None

    def get_mode_snapshot(self, mode: str = "paper") -> Optional[dict[str, Any]]:
        """
        Get full ModeStateSnapshot for a specific engine mode.
        Phase 4: returns paper_state + recent_intents + recent_fills +
        consecutive_losses + session_halted + paper_paused for that mode.
        獲取特定引擎模式的完整 ModeStateSnapshot。
        """
        snap = self.get_snapshot()
        if snap is None:
            return None
        mode_snapshots = snap.get("mode_snapshots", {})
        return mode_snapshots.get(mode)

    def get_active_modes(self) -> list[str]:
        """
        List all active engine modes (e.g. ["paper", "demo", "live"]).
        列出所有活躍引擎模式。
        """
        snap = self.get_snapshot()
        if snap is None:
            return []
        mode_snapshots = snap.get("mode_snapshots", {})
        return list(mode_snapshots.keys())

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

    # ── IPC-02: Expanded snapshot fields / 擴展快照欄位 ──────────────────────

    def get_indicators(self, symbol: Optional[str] = None) -> dict:
        """
        Get indicator values from Rust engine.
        If symbol specified, return that symbol's indicators only.
        從 Rust 引擎獲取指標值。若指定 symbol，只返回該交易對的指標。
        """
        snap = self.get_snapshot()
        if snap is None:
            return {}
        indicators = snap.get("indicators", {})
        if symbol:
            return indicators.get(symbol, {})
        return indicators

    def get_signals(self) -> list:
        """
        Get recent signals from Rust engine (up to 100).
        從 Rust 引擎獲取最近信號（最多 100 條）。
        """
        snap = self.get_snapshot()
        return (snap or {}).get("signals", [])

    def get_strategies(self) -> list:
        """
        Get strategy status list from Rust engine.
        從 Rust 引擎獲取策略狀態列表。
        """
        snap = self.get_snapshot()
        return (snap or {}).get("strategies", [])

    def get_recent_intents(self, mode: Optional[str] = None) -> list:
        """
        Get recent order intents from Rust engine (up to 50).
        Phase 4: optional `mode` param for per-mode intents.
        從 Rust 引擎獲取最近交易意圖（最多 50 條）。
        Phase 4：可選 `mode` 參數獲取特定模式的意圖。
        """
        if mode:
            ms = self.get_mode_snapshot(mode)
            return (ms or {}).get("recent_intents", [])
        snap = self.get_snapshot()
        return (snap or {}).get("recent_intents", [])

    def get_recent_fills(self, mode: Optional[str] = None) -> list:
        """
        Get recent fills from Rust engine (up to 50).
        Phase 4: optional `mode` param for per-mode fills.
        從 Rust 引擎獲取最近成交記錄（最多 50 條）。
        Phase 4：可選 `mode` 參數獲取特定模式的成交。
        """
        if mode:
            ms = self.get_mode_snapshot(mode)
            return (ms or {}).get("recent_fills", [])
        snap = self.get_snapshot()
        return (snap or {}).get("recent_fills", [])

    def get_klines(self, symbol: str, n: int = 50) -> list:
        """
        Get latest completed klines for a symbol from Rust engine (1m, up to 100).
        從 Rust 引擎獲取指定交易對最新已完成 K 線（1m，最多 100 根）。
        """
        snap = self.get_snapshot()
        if snap is None:
            return []
        klines = snap.get("klines", {})
        bars = klines.get(symbol, [])
        return bars[-n:] if len(bars) > n else bars


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
