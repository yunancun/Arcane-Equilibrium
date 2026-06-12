#!/usr/bin/env python3
"""Unit tests for the standalone pg_dump freshness healthcheck.

MODULE_NOTE:
  P2-OPS-4-GAP-B-D-UNIT-TEST-GAP — pg_dump/passive health 生產代碼補測試。
  本檔只測純函數 / mock 邊界：
    - tmp_path backup/log paths，不碰真 /tmp/openclaw 或真 backup 目錄。
    - check[6] mock pg_restore subprocess，不呼叫真 CLI。
    - check[7] mock connect_pg / cursor，不連真 PostgreSQL。
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import types
from datetime import datetime, timezone
from pathlib import Path

import pytest

_THIS_DIR = Path(__file__).resolve().parent
_HEALTHCHECKS_DIR = _THIS_DIR / "healthchecks"
sys.path.insert(0, str(_HEALTHCHECKS_DIR))

import check_pg_dump_freshness as pgdump  # noqa: E402


NOW = 1_700_000_000.0


def _paths(tmp_path: Path) -> dict[str, Path]:
    backup_root = tmp_path / "pg_backups"
    data_dir = tmp_path / "openclaw"
    log_dir = data_dir / "logs"
    backup_root.mkdir()
    log_dir.mkdir(parents=True)
    return {
        "backup_root": backup_root,
        "data_dir": data_dir,
        "log_dir": log_dir,
        "jsonl": log_dir / "trading_ai_pg_dump_cron.jsonl",
        "sentinel": backup_root / ".last_pg_dump",
        "heartbeat": data_dir / "cron_heartbeat" / "trading_ai_pg_dump.last_fire",
    }


def _write_dump(path: Path, data: bytes = b"dump-bytes") -> Path:
    path.write_bytes(data)
    os.utime(path, (NOW, NOW))
    return path


def test_check_4_md5_match_reads_matching_jsonl_entry(tmp_path: Path) -> None:
    """check[4] 以 dump_file 絕對路徑匹配 JSONL ok entry 並驗 md5。"""
    paths = _paths(tmp_path)
    dump = _write_dump(paths["backup_root"] / "trading_ai_20260612.dump")
    md5 = hashlib.md5(dump.read_bytes()).hexdigest()  # noqa: S324
    paths["jsonl"].write_text(
        json.dumps({"dump_file": str(dump), "status": "ok", "md5": md5}) + "\n",
        encoding="utf-8",
    )

    verdict, msg = pgdump.check_4_md5_match(paths)

    assert verdict == "PASS"
    assert f"md5 match {md5}" in msg


def test_check_4_md5_drift_fails(tmp_path: Path) -> None:
    """JSONL md5 與 dump 實際內容不一致時必須 FAIL。"""
    paths = _paths(tmp_path)
    dump = _write_dump(paths["backup_root"] / "trading_ai_20260612.dump")
    paths["jsonl"].write_text(
        json.dumps(
            {
                "dump_file": str(dump),
                "status": "ok",
                "md5": "0" * 32,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    verdict, msg = pgdump.check_4_md5_match(paths)

    assert verdict == "FAIL"
    assert "md5 drift recorded=" in msg


def test_check_6_l0_schema_coverage_uses_pg_restore_list(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """check[6] mock pg_restore --list，驗 shell=False 固定 argv 與 TOC grep。"""
    paths = _paths(tmp_path)
    dump = _write_dump(paths["backup_root"] / "trading_ai_20260612.dump")
    calls: list[dict] = []

    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/pg_restore")

    def fake_run(cmd, *, capture_output, text, timeout, check):
        calls.append(
            {
                "cmd": cmd,
                "capture_output": capture_output,
                "text": text,
                "timeout": timeout,
                "check": check,
            }
        )
        return types.SimpleNamespace(
            returncode=0,
            stdout="1234; 0 0 TABLE learning earn_movement_log trading_admin\n",
            stderr="",
        )

    monkeypatch.setattr(pgdump.subprocess, "run", fake_run)

    verdict, msg = pgdump.check_6_l0_schema_coverage(paths)

    assert verdict == "PASS"
    assert "L0 schema coverage OK" in msg
    assert calls == [
        {
            "cmd": ["pg_restore", "--list", str(dump)],
            "capture_output": True,
            "text": True,
            "timeout": 60,
            "check": False,
        }
    ]


class FakeCursor:
    def __init__(self, rows: list[tuple]) -> None:
        self._rows = list(rows)
        self.executed: list[str] = []

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *exc) -> bool:
        return False

    def execute(self, sql: str) -> None:
        self.executed.append(sql)

    def fetchone(self) -> tuple | None:
        if not self._rows:
            return None
        return self._rows.pop(0)


class FakeConn:
    def __init__(self, rows: list[tuple]) -> None:
        self.cursor_obj = FakeCursor(rows)
        self.closed = False

    def cursor(self) -> FakeCursor:
        return self.cursor_obj

    def close(self) -> None:
        self.closed = True


def test_check_7_audit_trail_warns_when_heartbeat_fresh_but_no_audit_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """V113 存在且 cron heartbeat 新鮮但 0 audit row → WARN 解 silent-fail mask。"""
    paths = _paths(tmp_path)
    paths["heartbeat"].parent.mkdir(parents=True)
    paths["heartbeat"].touch()
    os.utime(paths["heartbeat"], (NOW - 60.0, NOW - 60.0))
    conn = FakeConn(
        [
            ("CHECK (event_type IN ('pg_dump_completed'))",),
            (None, 0),
        ]
    )
    monkeypatch.setattr(pgdump, "connect_pg", lambda: conn)

    verdict, msg = pgdump.check_7_audit_trail(
        max_age_hours=26,
        paths=paths,
        now_epoch=NOW,
    )

    assert verdict == "WARN"
    assert "cron heartbeat fresh" in msg
    assert "0 pg_dump_completed row in 7d" in msg
    assert "audit INSERT likely silent fail" in msg
    assert conn.closed is True


def test_check_7_audit_trail_passes_with_recent_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """V113 存在且 latest pg_dump_completed 在 freshness window 內 → PASS。"""
    recent_ts = datetime.now(timezone.utc)
    conn = FakeConn(
        [
            ("CHECK (event_type IN ('pg_dump_completed'))",),
            (recent_ts, 3),
        ]
    )
    monkeypatch.setattr(pgdump, "connect_pg", lambda: conn)

    verdict, msg = pgdump.check_7_audit_trail(max_age_hours=26)

    assert verdict == "PASS"
    assert "last pg_dump_completed" in msg
    assert "7d window n=3" in msg
    assert conn.closed is True
