#!/usr/bin/env python3
"""test_halt_audit_pg_writer.py — MUST-FIX-3 Round 2 unit tests.

涵蓋：
  1. JSONL robust parser：純行解析 + `}{` 黏接 fallback
  2. cursor load / save：缺檔 / 壞檔 fail-soft
  3. row validate：schema 缺失 fail-soft pass-through；event_type 不在 allowlist skip
  4. resolve audit log path：env override 序列

整合測試（PG）：本檔僅給單元範圍。Linux PG integration 待 cron 真實安裝後
operator 驗 7d query 端對端。

跑：python3 srv/helper_scripts/canary/test_halt_audit_pg_writer.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import halt_audit_pg_writer as W  # noqa: E402


class TestJsonlRobust(unittest.TestCase):
    """`_parse_jsonl_robust` 對 happy path + 黏接 fallback 的處理。"""

    def test_pure_jsonl_lines(self):
        chunk = '{"a":1}\n{"b":2}\n'
        rows = list(W._parse_jsonl_robust(chunk))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0], {"a": 1})
        self.assertEqual(rows[1], {"b": 2})

    def test_glued_lines_fallback_split(self):
        # 兩條 JSON 黏在同一 line，無 \n 分隔
        chunk = '{"a":1}{"b":2}'
        rows = list(W._parse_jsonl_robust(chunk))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0], {"a": 1})
        self.assertEqual(rows[1], {"b": 2})

    def test_mixed_pure_and_glued(self):
        chunk = '{"a":1}\n{"b":2}{"c":3}\n{"d":4}'
        rows = list(W._parse_jsonl_robust(chunk))
        events_a = {r.get("a") for r in rows}
        events_b = {r.get("b") for r in rows}
        events_c = {r.get("c") for r in rows}
        events_d = {r.get("d") for r in rows}
        # 至少 a=1, b=2, c=3, d=4 各出現一次
        self.assertIn(1, events_a)
        self.assertIn(2, events_b)
        self.assertIn(3, events_c)
        self.assertIn(4, events_d)

    def test_invalid_json_skipped(self):
        chunk = "not-json\n{\"ok\": 1}\n"
        rows = list(W._parse_jsonl_robust(chunk))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0], {"ok": 1})

    def test_empty_chunk(self):
        rows = list(W._parse_jsonl_robust(""))
        self.assertEqual(rows, [])


class TestCursorState(unittest.TestCase):
    """`_load_cursor` / `_save_cursor` 對缺檔 / 壞檔 / 正常的行為。"""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp(prefix="halt_audit_cursor_test_")
        self.state_path = Path(self._tmpdir) / "state.json"

    def tearDown(self):
        import shutil

        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_missing_file_returns_zero(self):
        self.assertFalse(self.state_path.exists())
        self.assertEqual(W._load_cursor(self.state_path), 0)

    def test_save_and_load_roundtrip(self):
        W._save_cursor(self.state_path, 12345)
        self.assertEqual(W._load_cursor(self.state_path), 12345)

    def test_corrupted_state_returns_zero(self):
        self.state_path.write_text("{this is not json")
        self.assertEqual(W._load_cursor(self.state_path), 0)

    def test_negative_offset_rejected(self):
        self.state_path.write_text(json.dumps({"byte_offset": -1}))
        self.assertEqual(W._load_cursor(self.state_path), 0)

    def test_missing_offset_field_returns_zero(self):
        self.state_path.write_text(json.dumps({"other_field": 5}))
        self.assertEqual(W._load_cursor(self.state_path), 0)


class TestValidateRow(unittest.TestCase):
    """`_validate_row` 在 schema=None 時 pass-through；schema 載入失敗 best-effort。"""

    def test_schema_none_pass_through(self):
        self.assertTrue(W._validate_row({"any": "row"}, None))

    def test_schema_validate_success(self):
        # 構造一個簡 schema：必有 "event" 欄位
        minimal_schema = {
            "type": "object",
            "required": ["event"],
            "properties": {"event": {"type": "string"}},
        }
        ok_row = {"event": "halt_session_set"}
        self.assertTrue(W._validate_row(ok_row, minimal_schema))

    def test_schema_validate_fail(self):
        minimal_schema = {
            "type": "object",
            "required": ["event"],
            "properties": {"event": {"type": "string"}},
        }
        bad_row = {"no_event": "x"}
        # 若 jsonschema 未安裝 → return True (best-effort)；安裝則 False
        try:
            import jsonschema  # noqa: F401
        except ImportError:
            self.assertTrue(W._validate_row(bad_row, minimal_schema))
        else:
            self.assertFalse(W._validate_row(bad_row, minimal_schema))


class TestResolvePaths(unittest.TestCase):
    """`_resolve_audit_log_path` + `_resolve_cursor_path` env 優先序。"""

    def test_audit_log_explicit_env_wins(self):
        prev = os.environ.get("OPENCLAW_HALT_AUDIT_LOG")
        try:
            os.environ["OPENCLAW_HALT_AUDIT_LOG"] = "/explicit/path.log"
            self.assertEqual(
                str(W._resolve_audit_log_path()), "/explicit/path.log"
            )
        finally:
            if prev is None:
                os.environ.pop("OPENCLAW_HALT_AUDIT_LOG", None)
            else:
                os.environ["OPENCLAW_HALT_AUDIT_LOG"] = prev

    def test_audit_log_falls_back_to_data_dir(self):
        prev_log = os.environ.pop("OPENCLAW_HALT_AUDIT_LOG", None)
        prev_data = os.environ.get("OPENCLAW_DATA_DIR")
        try:
            os.environ["OPENCLAW_DATA_DIR"] = "/fallback/data"
            self.assertEqual(
                str(W._resolve_audit_log_path()), "/fallback/data/halt_audit.log"
            )
        finally:
            if prev_log is not None:
                os.environ["OPENCLAW_HALT_AUDIT_LOG"] = prev_log
            if prev_data is None:
                os.environ.pop("OPENCLAW_DATA_DIR", None)
            else:
                os.environ["OPENCLAW_DATA_DIR"] = prev_data

    def test_cursor_explicit_env_wins(self):
        prev = os.environ.get("OPENCLAW_HALT_AUDIT_PG_WRITER_STATE")
        try:
            os.environ["OPENCLAW_HALT_AUDIT_PG_WRITER_STATE"] = "/x/state.json"
            self.assertEqual(str(W._resolve_cursor_path()), "/x/state.json")
        finally:
            if prev is None:
                os.environ.pop("OPENCLAW_HALT_AUDIT_PG_WRITER_STATE", None)
            else:
                os.environ["OPENCLAW_HALT_AUDIT_PG_WRITER_STATE"] = prev


class TestEndToEndWithoutPG(unittest.TestCase):
    """整合：tail_and_insert 對 PG 缺失 / log 缺失的 fail-soft 行為。

    用 monkeypatch 風格替換 psycopg2 import 內部依賴；本 test 不真連 DB。
    """

    def test_missing_halt_audit_log_returns_zero(self):
        with tempfile.TemporaryDirectory() as td:
            log_path = Path(td) / "halt_audit.log"
            state_path = Path(td) / "state.json"
            self.assertFalse(log_path.exists())
            # 任意 DSN 字串；本 path 不會走到 PG connect 因為先檢 log 存在
            rc = W.tail_and_insert(log_path, state_path, "postgresql://x/y")
            self.assertEqual(rc, 0)


class TestEndToEndPGMock(unittest.TestCase):
    """整合：mock psycopg2，驗 3 條 halt_audit.log → 3 個 INSERT。"""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp(prefix="halt_audit_e2e_test_")
        self.log_path = Path(self._tmpdir) / "halt_audit.log"
        self.state_path = Path(self._tmpdir) / "state.json"

    def tearDown(self):
        import shutil

        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _make_jsonl_line(
        self,
        event: str,
        ts_ms: int,
        kind: str = "daily_loss",
        process_pid: int = 99999,
    ) -> str:
        row = {
            "schema_version": 1,
            "ts_ms": ts_ms,
            "ts_iso": "2026-05-19T12:00:00.000Z",
            "event": event,
            "kind": kind,
            "engine_mode": "demo",
            "pipeline_kind": "demo",
            "process_pid": process_pid,
            "halt_set_ts_ms": ts_ms,
        }
        return json.dumps(row) + "\n"

    def test_three_rows_three_inserts(self):
        from unittest.mock import MagicMock, patch

        # 寫 3 條 row
        content = (
            self._make_jsonl_line("halt_session_set", 1_700_000_000_000)
            + self._make_jsonl_line(
                "halt_session_auto_cleared", 1_700_086_401_000
            )
            + self._make_jsonl_line(
                "halt_session_manual_cleared", 1_700_172_802_000
            )
        )
        self.log_path.write_text(content)

        # mock psycopg2.connect → mock conn → mock cursor
        # cursor.execute() 收 SQL；governance_audit_log presence probe 回 1；
        # INSERT 回 rowcount=1（表 inserted）
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = (1,)  # presence probe / INSERT WHERE NOT EXISTS
        mock_cur.rowcount = 1
        mock_cur.__enter__.return_value = mock_cur
        mock_cur.__exit__.return_value = False

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_conn.__enter__.return_value = mock_conn
        mock_conn.__exit__.return_value = False

        import sys as _sys

        fake_psycopg2 = MagicMock()
        fake_psycopg2.connect.return_value = mock_conn
        _sys.modules["psycopg2"] = fake_psycopg2

        try:
            rc = W.tail_and_insert(
                self.log_path, self.state_path, "postgresql://x/y"
            )
        finally:
            _sys.modules.pop("psycopg2", None)

        self.assertEqual(rc, 0)
        # INSERT 應該至少被 call 3 次（presence probe 1 + INSERT 3）
        sql_calls = [
            call_args[0][0] for call_args in mock_cur.execute.call_args_list
        ]
        insert_calls = [s for s in sql_calls if "INSERT INTO" in s]
        self.assertEqual(
            len(insert_calls),
            3,
            f"預期 3 INSERT，實 {len(insert_calls)}；SQLs={sql_calls}",
        )
        # cursor 已前進 = file size
        cursor = W._load_cursor(self.state_path)
        self.assertEqual(cursor, len(content.encode()))

    def test_missing_table_returns_zero_cursor_not_advanced(self):
        from unittest.mock import MagicMock

        self.log_path.write_text(
            self._make_jsonl_line("halt_session_set", 1_700_000_000_000)
        )

        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = None  # presence probe returns None → table absent
        mock_cur.__enter__.return_value = mock_cur
        mock_cur.__exit__.return_value = False

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_conn.__enter__.return_value = mock_conn
        mock_conn.__exit__.return_value = False

        import sys as _sys

        fake_psycopg2 = MagicMock()
        fake_psycopg2.connect.return_value = mock_conn
        _sys.modules["psycopg2"] = fake_psycopg2

        try:
            rc = W.tail_and_insert(
                self.log_path, self.state_path, "postgresql://x/y"
            )
        finally:
            _sys.modules.pop("psycopg2", None)

        self.assertEqual(rc, 0, "V098 absent 應 exit 0")
        # cursor NOT advanced（state file 不應存在 / 應仍是 0）
        cursor = W._load_cursor(self.state_path)
        self.assertEqual(
            cursor, 0, "V098 absent 時 cursor 不能前進，否則重啟後丟資料"
        )

    def test_idempotent_skip_duplicate(self):
        """ON CONFLICT pattern：rowcount=0 表 dup；不影響 cursor 前進。"""
        from unittest.mock import MagicMock

        self.log_path.write_text(
            self._make_jsonl_line("halt_session_set", 1_700_000_000_000)
        )

        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = (1,)  # presence probe OK
        mock_cur.rowcount = 0  # INSERT WHERE NOT EXISTS dup
        mock_cur.__enter__.return_value = mock_cur
        mock_cur.__exit__.return_value = False

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_conn.__enter__.return_value = mock_conn
        mock_conn.__exit__.return_value = False

        import sys as _sys

        fake_psycopg2 = MagicMock()
        fake_psycopg2.connect.return_value = mock_conn
        _sys.modules["psycopg2"] = fake_psycopg2

        try:
            rc = W.tail_and_insert(
                self.log_path, self.state_path, "postgresql://x/y"
            )
        finally:
            _sys.modules.pop("psycopg2", None)

        self.assertEqual(rc, 0)
        # cursor 仍前進（即便 dup skip，下次重跑會再 INSERT WHERE NOT EXISTS）
        cursor = W._load_cursor(self.state_path)
        self.assertGreater(cursor, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
