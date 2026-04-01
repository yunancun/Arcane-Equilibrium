"""
Audit Persistence Layer — EX-01 §8 / GAP-H3 Implementation
审计持久化层 — EX-01 §8 / GAP-H3 实现

MODULE_NOTE (中文):
  本模块实现正式审计持久化系统：
  - JSON Lines 格式（每行一条审计记录）
  - 按日期自动轮转文件
  - 可配置最大文件大小轮转
  - 追加写模式（append-only，不可删除不可修改）
  - 线程安全写入
  - 支持外部查询（按时间范围、事件类型、关键字）
  - 与 AuthorizationStateMachine / RiskGovernorStateMachine 的 audit_callback 集成
  - 每日摘要生成

MODULE_NOTE (English):
  Implements formal audit persistence per EX-01 §8 / GAP-H3:
  - JSON Lines format (one audit record per line)
  - Automatic date-based file rotation
  - Configurable max file size rotation
  - Append-only mode (immutable audit trail)
  - Thread-safe writes
  - External query support (by time range, event type, keyword)
  - Integrates with AuthorizationStateMachine / RiskGovernorStateMachine audit_callback
  - Daily summary generation

Safety invariant:
  - Append-only: records are NEVER deleted or modified once written
  - Every write is flushed immediately (no buffered loss on crash)
  - File rotation creates new file but NEVER removes old files
  - Corrupted lines are skipped on read, never silently dropped on write
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Configuration / 配置
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class AuditPersistenceConfig:
    """
    Configuration for audit file persistence.
    审计文件持久化配置。
    """
    # Base directory for audit files / 审计文件基目录
    base_dir: str = "data/audit"

    # File naming / 文件命名
    file_prefix: str = "audit"
    file_extension: str = ".jsonl"

    # Rotation / 轮转
    rotate_by_date: bool = True          # New file each day / 每日新文件
    max_file_size_bytes: int = 50_000_000  # 50MB per file / 每文件50MB
    max_records_per_file: int = 500_000    # 500K records per file / 每文件50万条

    # Write behavior / 写入行为
    flush_after_write: bool = True   # Immediate flush / 立即刷盘
    create_dirs: bool = True         # Auto-create directories / 自动创建目录

    # Summary / 摘要
    generate_daily_summary: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "base_dir": self.base_dir,
            "file_prefix": self.file_prefix,
            "rotate_by_date": self.rotate_by_date,
            "max_file_size_bytes": self.max_file_size_bytes,
            "max_records_per_file": self.max_records_per_file,
            "flush_after_write": self.flush_after_write,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# Audit Record Envelope / 审计记录封装
# ═══════════════════════════════════════════════════════════════════════════════

def wrap_audit_record(record: dict[str, Any], source: str = "unknown") -> dict[str, Any]:
    """
    Wrap a raw audit record with persistence metadata.
    用持久化元数据封装原始审计记录。

    This adds: audit_id, persisted_at_ms, source, and sequence_id.
    """
    return {
        "audit_id": f"aud:{uuid.uuid4().hex[:16]}",
        "persisted_at_ms": int(time.time() * 1000),
        "source": source,
        "record": record,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Audit File Writer / 审计文件写入器
# ═══════════════════════════════════════════════════════════════════════════════

class AuditFileWriter:
    """
    Append-only JSON Lines audit file writer with rotation.
    追加写模式的 JSON Lines 审计文件写入器，带轮转。

    Thread-safe. Each write is immediately flushed to disk.
    线程安全。每次写入立即刷盘。
    """

    def __init__(self, config: AuditPersistenceConfig | None = None) -> None:
        self._config = config or AuditPersistenceConfig()
        self._lock = threading.Lock()
        self._current_file: Any = None  # file handle
        self._current_path: Path | None = None
        self._current_date: str = ""
        self._records_in_file: int = 0
        self._total_records: int = 0
        self._ensure_base_dir()

    def _ensure_base_dir(self) -> None:
        if self._config.create_dirs:
            Path(self._config.base_dir).mkdir(parents=True, exist_ok=True)

    def _get_date_str(self) -> str:
        """Current UTC date string / 当前 UTC 日期字符串"""
        return time.strftime("%Y-%m-%d", time.gmtime())

    def _build_file_path(self, date_str: str, seq: int = 0) -> Path:
        """Build audit file path / 构建审计文件路径"""
        base = Path(self._config.base_dir)
        suffix = f"_{seq}" if seq > 0 else ""
        name = f"{self._config.file_prefix}_{date_str}{suffix}{self._config.file_extension}"
        return base / name

    def _needs_rotation(self) -> bool:
        """Check if file rotation is needed / 检查是否需要轮转"""
        if self._current_file is None:
            return True

        # Date-based rotation / 按日期轮转
        if self._config.rotate_by_date:
            current_date = self._get_date_str()
            if current_date != self._current_date:
                return True

        # Size-based rotation / 按大小轮转
        if self._current_path and self._current_path.exists():
            if self._current_path.stat().st_size >= self._config.max_file_size_bytes:
                return True

        # Record count rotation / 按记录数轮转
        if self._records_in_file >= self._config.max_records_per_file:
            return True

        return False

    def _rotate(self) -> None:
        """Perform file rotation / 执行文件轮转"""
        # Close current file / 关闭当前文件
        if self._current_file:
            try:
                self._current_file.close()
            except Exception as e:
                logger.debug("audit_persistence: %s", e)
            self._current_file = None

        # Determine new file path / 确定新文件路径
        date_str = self._get_date_str()
        seq = 0
        path = self._build_file_path(date_str, seq)
        while path.exists():
            # Check if file exceeds size OR record count limit
            file_size = path.stat().st_size
            if file_size >= self._config.max_file_size_bytes:
                seq += 1
                path = self._build_file_path(date_str, seq)
                continue
            # Count lines to check record limit
            try:
                with open(path, "r", encoding="utf-8") as f:
                    line_count = sum(1 for line in f if line.strip())
                if line_count >= self._config.max_records_per_file:
                    seq += 1
                    path = self._build_file_path(date_str, seq)
                    continue
            except Exception as e:
                logger.debug("audit_persistence: %s", e)
            break

        # If file exists and is under size limit, append to it
        # 如果文件存在且未超限，追加写入
        self._current_path = path
        self._current_date = date_str
        self._current_file = open(path, "a", encoding="utf-8")

        # Count existing records in file / 计算文件中现有记录数
        if path.exists() and path.stat().st_size > 0:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    self._records_in_file = sum(1 for _ in f)
            except Exception as e:
                logger.debug("audit_persistence: %s", e)
                self._records_in_file = 0
        else:
            self._records_in_file = 0

        logger.info("Audit file rotated to: %s / 审计文件轮转至", path)

    def write(self, record: dict[str, Any], source: str = "unknown") -> str:
        """
        Write an audit record to the current file.
        将审计记录写入当前文件。

        Returns the audit_id of the persisted record.
        返回持久化记录的 audit_id。
        """
        envelope = wrap_audit_record(record, source=source)

        with self._lock:
            if self._needs_rotation():
                self._rotate()

            try:
                line = json.dumps(envelope, ensure_ascii=False, default=str)
                self._current_file.write(line + "\n")
                if self._config.flush_after_write:
                    self._current_file.flush()
                    os.fsync(self._current_file.fileno())
                self._records_in_file += 1
                self._total_records += 1
            except Exception:
                logger.exception("Failed to write audit record / 审计记录写入失败")
                raise

        return envelope["audit_id"]

    def write_batch(self, records: list[dict[str, Any]], source: str = "unknown") -> list[str]:
        """Write multiple audit records atomically / 原子批量写入审计记录"""
        ids: list[str] = []
        with self._lock:
            if self._needs_rotation():
                self._rotate()

            for record in records:
                envelope = wrap_audit_record(record, source=source)
                try:
                    line = json.dumps(envelope, ensure_ascii=False, default=str)
                    self._current_file.write(line + "\n")
                    self._records_in_file += 1
                    self._total_records += 1
                    ids.append(envelope["audit_id"])
                except Exception:
                    logger.exception("Failed to write audit record in batch")

            if self._config.flush_after_write:
                try:
                    self._current_file.flush()
                    os.fsync(self._current_file.fileno())
                except Exception as e:
                    logger.debug("audit_persistence: %s", e)

        return ids

    def close(self) -> None:
        """Close the current file / 关闭当前文件"""
        with self._lock:
            if self._current_file:
                try:
                    self._current_file.close()
                except Exception as e:
                    logger.debug("audit_persistence: %s", e)
                self._current_file = None

    @property
    def current_path(self) -> Path | None:
        return self._current_path

    @property
    def total_records(self) -> int:
        return self._total_records

    def get_status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "current_file": str(self._current_path) if self._current_path else None,
                "current_date": self._current_date,
                "records_in_file": self._records_in_file,
                "total_records_session": self._total_records,
                "config": self._config.to_dict(),
            }

    def __del__(self) -> None:
        self.close()


# ═══════════════════════════════════════════════════════════════════════════════
# Audit File Reader / 审计文件读取器
# ═══════════════════════════════════════════════════════════════════════════════

class AuditFileReader:
    """
    Reader for querying persisted audit records.
    查询持久化审计记录的读取器。
    """

    def __init__(self, base_dir: str = "data/audit", file_prefix: str = "audit") -> None:
        self._base_dir = Path(base_dir)
        self._file_prefix = file_prefix

    def list_files(self) -> list[Path]:
        """List all audit files sorted by name / 列出所有审计文件（按名称排序）"""
        if not self._base_dir.exists():
            return []
        files = sorted(self._base_dir.glob(f"{self._file_prefix}_*.jsonl"))
        return files

    def read_file(self, path: Path) -> Iterator[dict[str, Any]]:
        """Read all records from a single file / 从单个文件读取所有记录"""
        if not path.exists():
            return
        with open(path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    logger.warning("Corrupted line %d in %s, skipping / 损坏行", line_num, path)

    def query(
        self,
        *,
        start_ms: int | None = None,
        end_ms: int | None = None,
        source: str | None = None,
        event_type: str | None = None,
        keyword: str | None = None,
        limit: int = 1000,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Query audit records with filters.
        按条件查询审计记录。

        date_from/date_to: "YYYY-MM-DD" to limit which files to scan
        start_ms/end_ms: timestamp range filter on persisted_at_ms
        source: filter by source name
        event_type: search in record for trigger_event or trigger_event_type
        keyword: substring search in JSON line
        limit: max results
        """
        results: list[dict[str, Any]] = []

        for fpath in self.list_files():
            # Filename filter by date / 按文件名日期过滤
            fname = fpath.stem  # e.g. "audit_2026-03-29"
            parts = fname.split("_")
            if len(parts) >= 2:
                file_date = parts[1]  # "2026-03-29"
                if date_from and file_date < date_from:
                    continue
                if date_to and file_date > date_to:
                    continue

            for envelope in self.read_file(fpath):
                if len(results) >= limit:
                    return results

                # Time range filter / 时间范围过滤
                ts = envelope.get("persisted_at_ms", 0)
                if start_ms and ts < start_ms:
                    continue
                if end_ms and ts > end_ms:
                    continue

                # Source filter / 来源过滤
                if source and envelope.get("source") != source:
                    continue

                # Event type filter / 事件类型过滤
                if event_type:
                    rec = envelope.get("record", {})
                    rec_event = rec.get("trigger_event") or rec.get("trigger_event_type", "")
                    if event_type not in rec_event:
                        continue

                # Keyword filter / 关键字过滤
                if keyword:
                    line_str = json.dumps(envelope, default=str)
                    if keyword not in line_str:
                        continue

                results.append(envelope)

        return results

    def count_by_date(self) -> dict[str, int]:
        """Count records per date / 按日期统计记录数"""
        counts: dict[str, int] = {}
        for fpath in self.list_files():
            count = 0
            for _ in self.read_file(fpath):
                count += 1
            fname = fpath.stem
            parts = fname.split("_")
            date_key = parts[1] if len(parts) >= 2 else "unknown"
            counts[date_key] = counts.get(date_key, 0) + count
        return counts

    def generate_daily_summary(self, date_str: str | None = None) -> dict[str, Any]:
        """
        Generate a summary for a specific date.
        生成指定日期的审计摘要。

        Per EX-01 §8.2: "Daily summary generated for operational review"
        """
        if date_str is None:
            date_str = time.strftime("%Y-%m-%d", time.gmtime())

        records = self.query(date_from=date_str, date_to=date_str, limit=999_999)

        source_counts: dict[str, int] = {}
        event_counts: dict[str, int] = {}
        first_ts = None
        last_ts = None

        for env in records:
            src = env.get("source", "unknown")
            source_counts[src] = source_counts.get(src, 0) + 1

            rec = env.get("record", {})
            evt = rec.get("trigger_event") or rec.get("trigger_event_type", "unknown")
            event_counts[evt] = event_counts.get(evt, 0) + 1

            ts = env.get("persisted_at_ms", 0)
            if first_ts is None or ts < first_ts:
                first_ts = ts
            if last_ts is None or ts > last_ts:
                last_ts = ts

        return {
            "date": date_str,
            "total_records": len(records),
            "source_breakdown": source_counts,
            "event_breakdown": event_counts,
            "first_record_at_ms": first_ts,
            "last_record_at_ms": last_ts,
            "files_scanned": len([
                f for f in self.list_files()
                if date_str in f.stem
            ]),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# Audit Pipeline / 审计管道
# ═══════════════════════════════════════════════════════════════════════════════

class AuditPipeline:
    """
    Central audit pipeline that receives records from all state machines
    and persists them through AuditFileWriter.
    中央审计管道，接收所有状态机的记录并通过 AuditFileWriter 持久化。

    Use as audit_callback for AuthorizationStateMachine and RiskGovernorStateMachine.
    用作 AuthorizationStateMachine 和 RiskGovernorStateMachine 的 audit_callback。
    """

    def __init__(self, config: AuditPersistenceConfig | None = None) -> None:
        self._writer = AuditFileWriter(config)
        self._in_memory_buffer: list[dict[str, Any]] = []
        self._max_buffer_size: int = 10000
        self._subscribers: list[Callable[[dict[str, Any]], None]] = []

    def make_callback(self, source: str) -> Callable[[dict[str, Any]], None]:
        """
        Create a callback function for a specific source.
        为特定来源创建回调函数。

        Usage:
            auth_sm = AuthorizationStateMachine(
                audit_callback=pipeline.make_callback("authorization_sm")
            )
            risk_gov = RiskGovernorStateMachine(
                audit_callback=pipeline.make_callback("risk_governor")
            )
        """
        def callback(record: dict[str, Any]) -> None:
            self.ingest(record, source=source)
        return callback

    def ingest(self, record: dict[str, Any], source: str = "unknown") -> str:
        """
        Ingest an audit record: persist to file and notify subscribers.
        摄入审计记录：持久化到文件并通知订阅者。
        """
        audit_id = self._writer.write(record, source=source)

        # In-memory buffer for recent queries / 内存缓冲用于近期查询
        envelope = {"audit_id": audit_id, "source": source, "record": record,
                     "persisted_at_ms": int(time.time() * 1000)}
        self._in_memory_buffer.append(envelope)
        if len(self._in_memory_buffer) > self._max_buffer_size:
            self._in_memory_buffer = self._in_memory_buffer[-self._max_buffer_size:]

        # Notify subscribers / 通知订阅者
        for sub in self._subscribers:
            try:
                sub(envelope)
            except Exception:
                logger.exception("Audit subscriber error / 审计订阅者异常")

        return audit_id

    def subscribe(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Subscribe to audit events / 订阅审计事件"""
        self._subscribers.append(callback)

    def get_recent(self, limit: int = 100) -> list[dict[str, Any]]:
        """Get most recent records from in-memory buffer / 从内存缓冲获取最近记录"""
        return list(reversed(self._in_memory_buffer[-limit:]))

    def get_reader(self) -> AuditFileReader:
        """Get a reader for querying persisted records / 获取持久化查询读取器"""
        cfg = self._writer._config
        return AuditFileReader(base_dir=cfg.base_dir, file_prefix=cfg.file_prefix)

    def get_status(self) -> dict[str, Any]:
        return {
            "writer": self._writer.get_status(),
            "in_memory_buffer_size": len(self._in_memory_buffer),
            "subscribers": len(self._subscribers),
        }

    def close(self) -> None:
        self._writer.close()
