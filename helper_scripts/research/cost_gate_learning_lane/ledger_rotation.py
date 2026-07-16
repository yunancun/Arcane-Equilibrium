#!/usr/bin/env python3
"""
MODULE_NOTE
模塊用途:probe_ledger.jsonl 的 rotation / retention 共用層(P1-10,operator D9 裁定:
  主檔達 50MB 輪轉為 `probe_ledger.<UTCts>.jsonl` 段檔,段檔保留 14 天)。
主要函數:maybe_rotate_ledger(append 前的輪轉+清理入口)、retained_ledger_files
  (retention 窗內讀取視圖)、rotated_segment_paths(段檔枚舉)。
依賴:僅標準庫;fcntl.flock 為 Unix-only,與部署目標(Linux runtime + 未來 Apple
  Silicon)一致。
硬邊界(並發安全論證):
  - 輪轉 = flock 互斥下的 rename。rename 在同一檔案系統內原子且不改 inode:
    已持舊 fd 的 append 寫者(Rust O_APPEND BufWriter / Python open("a"))續寫
    舊段不丟行;之後按路徑新開的寫者落在新主檔。故 append 寫者「不需」持鎖。
  - flock 只互斥「輪轉者之間」(Rust 引擎與 Python lane 都可能觸發輪轉),
    防止 double-rotation 把剛建立的新主檔再轉走。進程崩潰時 flock 隨 fd 關閉
    自動釋放,不會留下永久卡死輪轉的殘鎖。
  - retention 只刪除嚴格匹配 `<stem>.<UTCts>Z(_seq)?.jsonl` 的段檔,永不觸碰
    lane 目錄下的其他 artifact;讀取視圖按檔名時間戳排除過期段,語義與磁盤
    清理時點解耦(段檔未被及時 unlink 也不會回到視圖)。
"""

from __future__ import annotations

import datetime as dt
import fcntl
import os
import re
from pathlib import Path
from typing import Any, Iterator

# P1-10 / D9 裁定值:50MB 輪轉閾值 + 14d retention。
# 測試經 monkeypatch 模組常量注入小閾值;生產側不提供 env 旋鈕(避免假參數)。
ROTATE_THRESHOLD_BYTES = 50 * 1024 * 1024
RETENTION_DAYS = 14
MAX_IN_MEMORY_RETAINED_LEDGER_BYTES = 128 * 1024 * 1024

_TS_FORMAT = "%Y%m%dT%H%M%SZ"
_JSONL_SUFFIX = ".jsonl"


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _ledger_stem(ledger_path: Path) -> str:
    name = ledger_path.name
    if name.endswith(_JSONL_SUFFIX):
        return name[: -len(_JSONL_SUFFIX)]
    return name


def _segment_pattern(ledger_path: Path) -> re.Pattern[str]:
    # 段名嚴格契約:<stem>.<YYYYMMDDTHHMMSSZ>(_seq)?.jsonl。與 Rust 側
    # demo_learning_lane_writer.rs 的段名解析保持逐字一致,兩側互認段檔。
    stem = re.escape(_ledger_stem(ledger_path))
    return re.compile(rf"^{stem}\.(\d{{8}}T\d{{6}}Z)(?:_(\d+))?\{_JSONL_SUFFIX}$")


def _iter_segments(ledger_path: Path) -> Iterator[tuple[str, int, Path]]:
    directory = ledger_path.parent
    if not directory.is_dir():
        return
    pattern = _segment_pattern(ledger_path)
    for name in os.listdir(directory):
        matched = pattern.match(name)
        if matched is None:
            continue
        yield matched.group(1), int(matched.group(2) or 0), directory / name


def _parse_segment_ts(ts_text: str) -> dt.datetime | None:
    try:
        parsed = dt.datetime.strptime(ts_text, _TS_FORMAT)
    except ValueError:
        return None
    return parsed.replace(tzinfo=dt.timezone.utc)


def rotated_segment_paths(ledger_path: Path) -> list[Path]:
    """按(時間戳, 序號)升冪回傳全部段檔(含已過期者;過期過濾在讀取視圖層)。"""
    entries = sorted(_iter_segments(ledger_path), key=lambda item: (item[0], item[1]))
    return [path for _, _, path in entries]


def retained_ledger_files(
    ledger_path: Path,
    *,
    retention_days: int | None = None,
    now_utc: dt.datetime | None = None,
) -> list[Path]:
    """讀取視圖:retention 窗內段檔(升冪)+ 主檔(若存在)。

    為什麼按檔名時間戳而非 mtime:段檔時間戳=輪轉時刻,是兩側寫者共同的
    確定性契約;mtime 會被 touch / 備份工具漂移。
    """
    days = RETENTION_DAYS if retention_days is None else retention_days
    now = now_utc or _utc_now()
    cutoff = now - dt.timedelta(days=days)
    out: list[Path] = []
    for ts_text, seq, path in sorted(
        _iter_segments(ledger_path), key=lambda item: (item[0], item[1])
    ):
        parsed = _parse_segment_ts(ts_text)
        if parsed is None or parsed < cutoff:
            continue
        out.append(path)
    if ledger_path.exists():
        out.append(ledger_path)
    return out


def retained_ledger_total_bytes(ledger_path: Path) -> int:
    """Return bytes in the current retention view without reading payloads."""

    return sum(path.stat().st_size for path in retained_ledger_files(ledger_path))


def _rotation_lock_path(ledger_path: Path) -> Path:
    return ledger_path.with_name(ledger_path.name + ".rotate.lock")


class _RotationLock:
    """flock 互斥(blocking)。持鎖時間僅覆蓋 re-stat + rename + retention 清理。"""

    def __init__(self, lock_path: Path) -> None:
        self._lock_path = lock_path
        self._fh = None

    def __enter__(self) -> "_RotationLock":
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self._lock_path.open("a")
        fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(self, *_exc: Any) -> None:
        if self._fh is not None:
            fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
            self._fh.close()
            self._fh = None


def _next_segment_path(ledger_path: Path, now_utc: dt.datetime) -> Path:
    ts_text = now_utc.strftime(_TS_FORMAT)
    stem = _ledger_stem(ledger_path)
    candidate = ledger_path.with_name(f"{stem}.{ts_text}{_JSONL_SUFFIX}")
    seq = 0
    while candidate.exists():
        seq += 1
        candidate = ledger_path.with_name(f"{stem}.{ts_text}_{seq}{_JSONL_SUFFIX}")
    return candidate


def _sweep_expired_segments(
    ledger_path: Path, *, retention_days: int, now_utc: dt.datetime
) -> int:
    cutoff = now_utc - dt.timedelta(days=retention_days)
    deleted = 0
    for ts_text, _seq, path in _iter_segments(ledger_path):
        parsed = _parse_segment_ts(ts_text)
        if parsed is None or parsed >= cutoff:
            continue
        try:
            path.unlink()
        except FileNotFoundError:
            # 另一側輪轉者剛清掉同一過期段,冪等跳過。
            continue
        deleted += 1
    return deleted


def maybe_rotate_ledger(
    ledger_path: Path,
    *,
    threshold_bytes: int | None = None,
    retention_days: int | None = None,
    now_utc: dt.datetime | None = None,
) -> dict[str, Any]:
    """append 前調用:主檔達閾值即輪轉,並在同一把鎖下做 retention 清理。

    fast path 只做一次 stat(不掃目錄),per-append 開銷可忽略;retention 掃描
    只在真正輪轉時發生,過期段的「語義排除」由 retained_ledger_files 兜底。
    """
    threshold = ROTATE_THRESHOLD_BYTES if threshold_bytes is None else threshold_bytes
    days = RETENTION_DAYS if retention_days is None else retention_days
    summary: dict[str, Any] = {"rotated": False, "segment_path": None, "expired_deleted": 0}
    try:
        size = ledger_path.stat().st_size
    except FileNotFoundError:
        return summary
    if size < threshold:
        return summary
    now = now_utc or _utc_now()
    with _RotationLock(_rotation_lock_path(ledger_path)):
        # 鎖下複核:並發輪轉者可能剛把主檔轉走(路徑上是新的小主檔或不存在)。
        try:
            size = ledger_path.stat().st_size
        except FileNotFoundError:
            return summary
        if size < threshold:
            return summary
        target = _next_segment_path(ledger_path, now)
        ledger_path.rename(target)
        summary["rotated"] = True
        summary["segment_path"] = str(target)
        summary["expired_deleted"] = _sweep_expired_segments(
            ledger_path, retention_days=days, now_utc=now
        )
    return summary
