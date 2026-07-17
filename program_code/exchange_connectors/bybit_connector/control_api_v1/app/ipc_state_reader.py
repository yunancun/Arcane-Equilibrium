# MODULE_NOTE:
# IPC State Reader — file-based read of Rust engine pipeline snapshots (R06-B / 3E-5).
# IPC 狀態讀取器 — 基於文件讀取 Rust 引擎管線快照。
#
# 3E-5: Per-engine snapshot files (pipeline_snapshot_{paper|demo|live}.json).
# Primary pipeline also writes pipeline_snapshot.json for backward compat.
# Provides cached, thread-safe access to paper state, latest prices, and tick stats.
# Falls back gracefully when the file is missing or stale (engine not running).
#
# 3E-5：每引擎快照文件（pipeline_snapshot_{paper|demo|live}.json）。
# 主管線同時寫入 pipeline_snapshot.json 保持向後兼容。
# 提供緩存的、線程安全的 paper state、最新價格和 tick 統計訪問。
# 當文件缺失或過期時（引擎未運行）優雅降級。

from __future__ import annotations

import json
import logging
import os
import stat
import threading
import time
from pathlib import Path
from typing import Any, Optional

from .error_sanitize import log_safe_exception

logger = logging.getLogger(__name__)

# Cache TTL — re-read file at most every 2 seconds to reduce I/O
# 緩存 TTL — 最多每 2 秒重讀文件以減少 I/O
_CACHE_TTL_SECONDS = 2.0

# Snapshot staleness threshold — data older than this is considered stale
# 快照過期閾值 — 超過此時間的數據視為過期
_STALENESS_THRESHOLD_SECONDS = 60.0

# A snapshot is operational state, not an unbounded artifact transport.
_MAX_SNAPSHOT_BYTES = 4 * 1024 * 1024

# Valid engine names / 有效引擎名稱
_VALID_ENGINES = frozenset({"paper", "demo", "live"})
_VALID_SNAPSHOT_FILENAMES = frozenset(
    {"pipeline_snapshot.json"}
    | {f"pipeline_snapshot_{engine}.json" for engine in _VALID_ENGINES}
)


class RustSnapshotReader:
    """
    Thread-safe cached reader for Rust engine pipeline snapshots.
    3E-5: Supports per-engine snapshot files (pipeline_snapshot_{engine}.json)
    and backward-compat primary file (pipeline_snapshot.json).
    線程安全的緩存讀取器，支持每引擎快照文件和向後兼容主文件。

    Usage / 用法:
        reader = RustSnapshotReader()
        state = reader.get_paper_state()            # primary snapshot
        state = reader.get_paper_state(engine="demo") # per-engine snapshot
        prices = reader.get_latest_prices()
        engines = reader.get_active_engines()       # ["paper", "demo"]
    """

    def __init__(self, data_dir: Optional[str] = None) -> None:
        self._data_dir = data_dir or os.environ.get(
            "OPENCLAW_DATA_DIR", "/tmp/openclaw"
        )
        self._data_root = Path(
            os.path.abspath(Path(self._data_dir).expanduser())
        )
        self._lock = threading.Lock()
        # Primary (compat) cache / 主（兼容）緩存
        self._cache: Optional[dict[str, Any]] = None
        self._cache_ts: float = 0.0
        self._cache_file_age: float = 999999.0
        # Per-engine caches / 每引擎緩存
        self._engine_caches: dict[str, dict[str, Any]] = {}
        self._engine_cache_ts: dict[str, float] = {}
        self._engine_file_ages: dict[str, float] = {}
        self._engine_snapshot_missing: dict[str, bool] = {}

    @property
    def snapshot_path(self) -> Path:
        """Path to the primary (compat) pipeline snapshot file / 主（兼容）管線快照文件路徑"""
        return self._snapshot_path("pipeline_snapshot.json")

    def _snapshot_path(self, filename: str) -> Path:
        if filename not in _VALID_SNAPSHOT_FILENAMES:
            raise ValueError("unsupported snapshot filename")
        candidate = Path(os.path.abspath(self._data_root / filename))
        if not candidate.is_relative_to(self._data_root):
            raise ValueError("snapshot path escapes data directory")
        return candidate

    def _engine_snapshot_path(self, engine: str) -> Path:
        """Path to per-engine snapshot file / 每引擎快照文件路徑"""
        if engine not in _VALID_ENGINES:
            raise ValueError("unsupported snapshot engine")
        return self._snapshot_path(f"pipeline_snapshot_{engine}.json")

    def _open_data_root_fd(self) -> int:
        """Open every data-root component without following replacement symlinks."""
        no_follow = getattr(os, "O_NOFOLLOW", None)
        directory = getattr(os, "O_DIRECTORY", None)
        if no_follow is None or directory is None:
            raise OSError("safe snapshot directory flags unavailable")
        flags = os.O_RDONLY | directory | no_follow
        root = self._data_root
        if not root.is_absolute() or not root.anchor:
            raise ValueError("snapshot data root must be absolute")

        current_fd = -1
        try:
            current_fd = os.open(root.anchor, flags)
            for component in root.parts[1:]:
                if component in {"", ".", ".."}:
                    raise ValueError("invalid snapshot root component")
                next_fd = os.open(component, flags, dir_fd=current_fd)
                os.close(current_fd)
                current_fd = next_fd
            result_fd = current_fd
            current_fd = -1
            return result_fd
        finally:
            if current_fd >= 0:
                os.close(current_fd)

    def _read_snapshot_file(self, path: Path) -> tuple[dict[str, Any], float]:
        """Read one bounded regular snapshot and its mtime through one fd."""
        no_follow = getattr(os, "O_NOFOLLOW", None)
        nonblock = getattr(os, "O_NONBLOCK", None)
        directory = getattr(os, "O_DIRECTORY", None)
        if no_follow is None or nonblock is None or directory is None:
            raise OSError("safe snapshot open flags unavailable")
        if path.parent != self._data_root or path.name not in _VALID_SNAPSHOT_FILENAMES:
            raise ValueError("snapshot path is outside the allowlist")

        root_fd = -1
        fd = -1
        try:
            root_fd = self._open_data_root_fd()
            fd = os.open(
                path.name,
                os.O_RDONLY | no_follow | nonblock,
                dir_fd=root_fd,
            )
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode):
                raise OSError("snapshot is not a regular file")
            if before.st_size < 0 or before.st_size > _MAX_SNAPSHOT_BYTES:
                raise OSError("snapshot exceeds size bound")

            chunks: list[bytes] = []
            total = 0
            while total <= _MAX_SNAPSHOT_BYTES:
                chunk = os.read(
                    fd,
                    min(64 * 1024, _MAX_SNAPSHOT_BYTES + 1 - total),
                )
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
            if total > _MAX_SNAPSHOT_BYTES:
                raise OSError("snapshot exceeds size bound")

            after = os.fstat(fd)
            if (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
            ) != (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
            ):
                raise OSError("snapshot changed during read")
            data = json.loads(b"".join(chunks))
            if not isinstance(data, dict):
                raise ValueError("snapshot JSON must be an object")
            return data, after.st_mtime
        finally:
            if fd >= 0:
                os.close(fd)
            if root_fd >= 0:
                os.close(root_fd)

    def _refresh_cache(self) -> Optional[dict[str, Any]]:
        """
        Re-read primary snapshot file if cache is stale.
        如果緩存過期則重新讀取主快照文件。
        """
        now = time.monotonic()
        if self._cache is not None and (now - self._cache_ts) < _CACHE_TTL_SECONDS:
            return self._cache

        try:
            path = self.snapshot_path
            data, mtime = self._read_snapshot_file(path)
            self._cache_file_age = time.time() - mtime
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
        except (json.JSONDecodeError, OSError, UnicodeError, ValueError) as exc:
            self._cache_file_age = 999999.0
            log_safe_exception(
                logger,
                "rust_primary_snapshot_read",
                exc,
                level=logging.WARNING,
            )
            return None

    def _refresh_engine_cache(self, engine: str) -> Optional[dict[str, Any]]:
        """
        Re-read per-engine snapshot file if cache is stale (3E-5).
        如果緩存過期則重新讀取每引擎快照文件。
        """
        now = time.monotonic()
        cached_ts = self._engine_cache_ts.get(engine, 0.0)
        if engine in self._engine_caches and (now - cached_ts) < _CACHE_TTL_SECONDS:
            return self._engine_caches[engine]

        try:
            path = self._engine_snapshot_path(engine)
            data, mtime = self._read_snapshot_file(path)
            self._engine_file_ages[engine] = time.time() - mtime
            self._engine_caches[engine] = data
            self._engine_cache_ts[engine] = now
            self._engine_snapshot_missing[engine] = False
            return data
        except FileNotFoundError:
            self._engine_file_ages[engine] = 999999.0
            self._engine_snapshot_missing[engine] = True
            return None
        except (json.JSONDecodeError, OSError, UnicodeError, ValueError) as exc:
            self._engine_file_ages[engine] = 999999.0
            self._engine_snapshot_missing[engine] = False
            log_safe_exception(
                logger,
                "rust_engine_snapshot_read",
                exc,
                level=logging.WARNING,
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
        return self._cache_file_age < _STALENESS_THRESHOLD_SECONDS

    def is_engine_available(self, engine: str) -> bool:
        """
        Check if a specific engine's snapshot is available and fresh (3E-5).
        檢查特定引擎的快照是否可用且未過期。
        """
        if engine not in _VALID_ENGINES:
            return False
        with self._lock:
            data = self._refresh_engine_cache(engine)
        if data is None:
            return False
        return self._engine_file_ages.get(engine, 999999.0) < _STALENESS_THRESHOLD_SECONDS

    def get_snapshot(self, engine: Optional[str] = None) -> Optional[dict[str, Any]]:
        """
        Get the full pipeline snapshot.

        Default (engine=None): reads the legacy compat pipeline_snapshot.json
        (preserved for backward compat with pre-3E-ARCH unit tests / single-engine
        deployments).

        Pass engine="paper"/"demo"/"live" to read the per-engine snapshot file
        directly — REQUIRED in 3E-ARCH for paper-tab routes, otherwise the compat
        file is whichever engine has is_primary=true (Live > Demo > Paper) and
        paper-tab callers will accidentally read Live data.

        獲取完整管線快照。預設讀 compat 檔（向後兼容單元測試 / 單引擎部署）。
        3E-ARCH 下 paper-tab 路由必須顯式傳 engine="paper"，否則 compat 檔由
        is_primary 引擎寫入（Live > Demo > Paper 優先序），會誤讀 Live 數據。
        """
        if engine and engine in _VALID_ENGINES:
            return self.get_engine_snapshot(engine)
        with self._lock:
            return self._refresh_cache()

    def get_engine_snapshot(self, engine: str) -> Optional[dict[str, Any]]:
        """
        Get per-engine pipeline snapshot (3E-5). Falls back to primary if per-engine
        file not found and engine matches primary pipeline kind.
        獲取每引擎管線快照。若每引擎文件未找到且引擎匹配主管線 kind，回退到主快照。
        """
        if engine not in _VALID_ENGINES:
            return None
        with self._lock:
            snap = self._refresh_engine_cache(engine)
            if snap is not None:
                return snap
            if not self._engine_snapshot_missing.get(engine, False):
                return None
            # Fallback: primary snapshot if its trading_mode matches requested engine
            # 回退：若主快照的 trading_mode 匹配請求的引擎
            primary = self._refresh_cache()
            if primary is None:
                return None
            primary_kind = primary.get("trading_mode", "paper")
            _ALIASES = {"paper_only": "paper"}
            if _ALIASES.get(primary_kind, primary_kind) == engine:
                return primary
            return None

    def get_paper_state(self, mode: str = "paper", engine: Optional[str] = None) -> Optional[dict[str, Any]]:
        """
        Get paper trading state (balance, positions, pnl, fees).
        3E-ARCH: routes through per-engine snapshot file by default (mode="paper").
        Pass engine="demo"/"live" or mode="demo"/"live" to read other engines.

        ★ Bugfix 2026-04-11: previously defaulted to the compat pipeline_snapshot.json,
        which under 3E-ARCH is written by whichever engine has is_primary=true (Live > Demo > Paper).
        That made the Paper GUI tab show Live engine balance + zero positions when all
        three engines ran. Now defaults to pipeline_snapshot_paper.json.
        ★ 修復 2026-04-11：之前預設讀取 compat pipeline_snapshot.json，
        該檔在 3E-ARCH 下由 is_primary=true 的引擎寫入（Live > Demo > Paper 優先序），
        導致 Paper GUI 顯示 Live 餘額 + 零持倉。現在預設讀 pipeline_snapshot_paper.json。
        """
        target = engine or mode or "paper"
        if target not in _VALID_ENGINES:
            target = "paper"
        snap = self.get_engine_snapshot(target)
        if snap is None:
            return None
        return snap.get("paper_state")

    def get_mode_snapshot(self, mode: str = "paper") -> Optional[dict[str, Any]]:
        """
        Get full ModeStateSnapshot for a specific engine mode.
        3E-5: reads from per-engine snapshot file.
        獲取特定引擎模式的完整快照。3E-5：從每引擎快照文件讀取。
        """
        snap = self.get_engine_snapshot(mode)
        return snap

    def get_active_engines(self) -> list[str]:
        """
        List all engines with fresh snapshots (3E-5).
        Checks pipeline_snapshot_{paper|demo|live}.json freshness.
        列出所有擁有新鮮快照的引擎。
        """
        active = []
        for eng in sorted(_VALID_ENGINES):
            if self.is_engine_available(eng):
                active.append(eng)
        return active

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
        3E-5: mode param reads from per-engine snapshot.
        從 Rust 引擎獲取最近交易意圖（最多 50 條）。
        """
        if mode:
            snap = self.get_engine_snapshot(mode)
            return (snap or {}).get("recent_intents", [])
        snap = self.get_snapshot()
        return (snap or {}).get("recent_intents", [])

    def get_recent_fills(self, mode: Optional[str] = None) -> list:
        """
        Get recent fills from Rust engine (up to 50).
        3E-5: mode param reads from per-engine snapshot.
        從 Rust 引擎獲取最近成交記錄（最多 50 條）。
        """
        if mode:
            snap = self.get_engine_snapshot(mode)
            return (snap or {}).get("recent_fills", [])
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
