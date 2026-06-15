#!/usr/bin/env python3
"""test_canary_audit_pg_writer.py — ENGINE-AUDIT-VISIBILITY tail-bridge tests (2026-06-15)

MODULE_NOTE
模塊用途：canary_audit_pg_writer（tail-bridge backstop）單元測試，建模緊貼
  sibling test_halt_audit_pg_writer.py。涵蓋：
    1. JSONL robust parser（純行 + `}{` 黏接 fallback）
    2. cursor load/save（缺檔/壞檔 fail-soft）
    3. path 解析 env 優先序
    4. canary 事件 → audit_events 行映射（含自帶 dedup_key / 舊行就地推導）
    5. tail_and_insert：correct INSERT shape / dedup NOT EXISTS 防重 / 壞行 fail-soft /
       PG-down fail-soft / cursor 只在成功時前進 / 表缺 cursor 不前進
依賴：canary_audit_pg_writer / canary_audit_common；unittest.mock（mock DB 層）；無真 PG。
硬邊界：全 mock，無真連線；驗 backstop 冪等 + fail-soft + cursor 推進語義。

跑：python3 -m pytest helper_scripts/canary/test_canary_audit_pg_writer.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import canary_audit_pg_writer as B  # noqa: E402
import canary_audit_common as C  # noqa: E402


class TestJsonlRobust(unittest.TestCase):
    def test_pure_jsonl_lines(self):
        rows = list(B._parse_jsonl_robust('{"a":1}\n{"b":2}\n'))
        self.assertEqual(rows, [{"a": 1}, {"b": 2}])

    def test_glued_lines_fallback_split(self):
        rows = list(B._parse_jsonl_robust('{"a":1}{"b":2}'))
        self.assertEqual(len(rows), 2)

    def test_invalid_json_skipped(self):
        rows = list(B._parse_jsonl_robust('not-json\n{"ok":1}\n'))
        self.assertEqual(rows, [{"ok": 1}])

    def test_empty_chunk(self):
        self.assertEqual(list(B._parse_jsonl_robust("")), [])


class TestCursorState(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.mkdtemp(prefix="canary_audit_cursor_")
        self.state_path = Path(self._td) / "state.json"

    def tearDown(self):
        import shutil
        shutil.rmtree(self._td, ignore_errors=True)

    def test_missing_file_returns_zero(self):
        self.assertEqual(B._load_cursor(self.state_path), 0)

    def test_save_and_load_roundtrip(self):
        B._save_cursor(self.state_path, 4242)
        self.assertEqual(B._load_cursor(self.state_path), 4242)

    def test_corrupted_state_returns_zero(self):
        self.state_path.write_text("{not json")
        self.assertEqual(B._load_cursor(self.state_path), 0)

    def test_negative_offset_rejected(self):
        self.state_path.write_text(json.dumps({"byte_offset": -1}))
        self.assertEqual(B._load_cursor(self.state_path), 0)


class TestResolvePaths(unittest.TestCase):
    def test_canary_log_explicit_env_wins(self):
        prev = os.environ.get("OPENCLAW_CANARY_EVENTS_LOG")
        try:
            os.environ["OPENCLAW_CANARY_EVENTS_LOG"] = "/explicit/canary.jsonl"
            self.assertEqual(str(B._resolve_canary_events_path()), "/explicit/canary.jsonl")
        finally:
            if prev is None:
                os.environ.pop("OPENCLAW_CANARY_EVENTS_LOG", None)
            else:
                os.environ["OPENCLAW_CANARY_EVENTS_LOG"] = prev

    def test_canary_log_falls_back_to_data_dir(self):
        prev_log = os.environ.pop("OPENCLAW_CANARY_EVENTS_LOG", None)
        prev_data = os.environ.get("OPENCLAW_DATA_DIR")
        try:
            os.environ["OPENCLAW_DATA_DIR"] = "/fallback/data"
            self.assertEqual(
                str(B._resolve_canary_events_path()), "/fallback/data/canary_events.jsonl"
            )
        finally:
            if prev_log is not None:
                os.environ["OPENCLAW_CANARY_EVENTS_LOG"] = prev_log
            if prev_data is None:
                os.environ.pop("OPENCLAW_DATA_DIR", None)
            else:
                os.environ["OPENCLAW_DATA_DIR"] = prev_data

    def test_cursor_does_not_collide_with_watchdog_state(self):
        # 獨立命名空間，絕不碰 watchdog_state.json。
        prev = os.environ.pop("OPENCLAW_CANARY_AUDIT_PG_WRITER_STATE", None)
        prev_data = os.environ.get("OPENCLAW_DATA_DIR")
        try:
            os.environ["OPENCLAW_DATA_DIR"] = "/d"
            p = str(B._resolve_cursor_path())
            self.assertTrue(p.endswith("canary_audit_pg_writer_state.json"))
            self.assertNotIn("watchdog_state.json", p)
        finally:
            if prev is not None:
                os.environ["OPENCLAW_CANARY_AUDIT_PG_WRITER_STATE"] = prev
            if prev_data is None:
                os.environ.pop("OPENCLAW_DATA_DIR", None)
            else:
                os.environ["OPENCLAW_DATA_DIR"] = prev_data


class TestCanaryToAuditRow(unittest.TestCase):
    """canary 事件 → audit_events 行映射。"""

    def test_uses_embedded_dedup_key_when_present(self):
        event = {
            "ts": 1_700_000_000.0, "event": "ENGINE_CRASH",
            "snapshot_age_seconds": 50.0, "total_crashes": 1,
            "restart_outcome": "restart_failed",
            "dedup_key": "engine_watchdog|engine_crash|EMBEDDED",
        }
        row = B._canary_to_audit_row(event)
        self.assertEqual(row["event_type"], "engine_crash")
        self.assertEqual(row["severity"], "critical")
        self.assertEqual(row["event_details"]["dedup_key"], "engine_watchdog|engine_crash|EMBEDDED")
        self.assertEqual(row["event_details"]["restart_outcome"], "restart_failed")
        self.assertEqual(row["event_details"]["backfilled_by"], "canary_audit_pg_writer")

    def test_derives_dedup_key_for_legacy_row_without_key(self):
        # 舊行無 dedup_key → 用 ts + event_type 就地推導（與 direct write 同形）。
        event = {"ts": 1_700_000_000.0, "event": "NETWORK_OUTAGE", "snapshot_age_seconds": 60.0}
        row = B._canary_to_audit_row(event)
        self.assertEqual(
            row["event_details"]["dedup_key"],
            C.build_dedup_key("network_outage", 1_700_000_000.0),
        )

    def test_unmapped_event_returns_none(self):
        self.assertIsNone(B._canary_to_audit_row({"ts": 1.0, "event": "RESTART_SUCCESS"}))

    def test_no_dedup_key_and_no_ts_returns_none(self):
        # 無法構造穩定去重 key → skip（避免插入無法去重的行）。
        self.assertIsNone(B._canary_to_audit_row({"event": "ENGINE_CRASH"}))

    def test_non_string_event_returns_none(self):
        self.assertIsNone(B._canary_to_audit_row({"event": 123, "ts": 1.0}))


def _mock_psycopg2(rowcount=1, table_present=True):
    """建構 mock psycopg2，presence probe + INSERT rowcount 可控。"""
    mock_cur = mock.MagicMock()
    # fetchone：presence probe 回 (1,) 表存在 / None 表缺。
    mock_cur.fetchone.return_value = (1,) if table_present else None
    mock_cur.rowcount = rowcount
    mock_cur.__enter__.return_value = mock_cur
    mock_cur.__exit__.return_value = False
    mock_conn = mock.MagicMock()
    mock_conn.cursor.return_value = mock_cur
    mock_conn.__enter__.return_value = mock_conn
    mock_conn.__exit__.return_value = False
    fake = mock.MagicMock()
    fake.connect.return_value = mock_conn
    return fake, mock_cur


class TestTailAndInsert(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.mkdtemp(prefix="canary_audit_e2e_")
        self.log_path = Path(self._td) / "canary_events.jsonl"
        self.state_path = Path(self._td) / "state.json"

    def tearDown(self):
        import shutil
        shutil.rmtree(self._td, ignore_errors=True)

    def _write(self, *events):
        with self.log_path.open("w", encoding="utf-8") as f:
            for e in events:
                f.write(json.dumps(e) + "\n")

    def _crash(self, ts):
        return {"ts": ts, "event": "ENGINE_CRASH", "snapshot_age_seconds": 50.0,
                "total_crashes": 1, "restart_outcome": "restart_failed",
                "dedup_key": C.build_dedup_key("engine_crash", ts)}

    def test_missing_log_returns_zero(self):
        self.assertFalse(self.log_path.exists())
        rc = B.tail_and_insert(self.log_path, self.state_path, "postgresql://x/y")
        self.assertEqual(rc, 0)

    def test_mappable_events_insert_correct_shape(self):
        self._write(
            self._crash(1_700_000_000.0),
            {"ts": 1_700_000_100.0, "event": "NETWORK_OUTAGE", "snapshot_age_seconds": 60.0,
             "dedup_key": C.build_dedup_key("network_outage", 1_700_000_100.0)},
            {"ts": 1_700_000_200.0, "event": "RESTART_SUCCESS"},  # 不 mappable → skip
        )
        fake, mock_cur = _mock_psycopg2(rowcount=1)
        sys.modules["psycopg2"] = fake
        try:
            rc = B.tail_and_insert(self.log_path, self.state_path, "postgresql://x/y")
        finally:
            sys.modules.pop("psycopg2", None)
        self.assertEqual(rc, 0)
        sqls = [c[0][0] for c in mock_cur.execute.call_args_list]
        inserts = [s for s in sqls if "INSERT INTO audit_events" in s]
        # 2 個 mappable（crash + outage），RESTART_SUCCESS skip。
        self.assertEqual(len(inserts), 2)
        # cursor 前進到 file size。
        self.assertEqual(B._load_cursor(self.state_path), self.log_path.stat().st_size)

    def test_dedup_not_exists_prevents_duplicate(self):
        # rowcount=0 模擬 dedup_key 已存在（direct write 已寫）→ INSERT 0 row。
        self._write(self._crash(1_700_000_000.0))
        fake, mock_cur = _mock_psycopg2(rowcount=0)
        sys.modules["psycopg2"] = fake
        try:
            rc = B.tail_and_insert(self.log_path, self.state_path, "postgresql://x/y")
        finally:
            sys.modules.pop("psycopg2", None)
        self.assertEqual(rc, 0)
        # INSERT 仍被嘗試（WHERE NOT EXISTS 在 SQL 層擋），但 rowcount=0 = 未重複插入。
        sqls = [c[0][0] for c in mock_cur.execute.call_args_list]
        self.assertEqual(len([s for s in sqls if "WHERE NOT EXISTS" in s]), 1)
        # cursor 照常前進（冪等：dup skip 不阻塞推進）。
        self.assertGreater(B._load_cursor(self.state_path), 0)

    def test_malformed_rows_fail_soft(self):
        # 壞 JSON 行夾在好行間 → 不卡死，好行照常 INSERT。
        with self.log_path.open("w", encoding="utf-8") as f:
            f.write("this is not json\n")
            f.write(json.dumps(self._crash(1_700_000_000.0)) + "\n")
        fake, mock_cur = _mock_psycopg2(rowcount=1)
        sys.modules["psycopg2"] = fake
        try:
            rc = B.tail_and_insert(self.log_path, self.state_path, "postgresql://x/y")
        finally:
            sys.modules.pop("psycopg2", None)
        self.assertEqual(rc, 0)
        inserts = [c[0][0] for c in mock_cur.execute.call_args_list if "INSERT INTO audit_events" in c[0][0]]
        self.assertEqual(len(inserts), 1)

    def test_pg_connect_down_fail_soft_cursor_not_advanced(self):
        self._write(self._crash(1_700_000_000.0))
        fake = mock.MagicMock()
        fake.connect.side_effect = RuntimeError("connection refused")
        sys.modules["psycopg2"] = fake
        try:
            rc = B.tail_and_insert(self.log_path, self.state_path, "postgresql://x/y")
        finally:
            sys.modules.pop("psycopg2", None)
        self.assertEqual(rc, 1)  # PG 錯誤回 1
        # cursor 不前進（下輪冪等重試整個 chunk）。
        self.assertEqual(B._load_cursor(self.state_path), 0)

    def test_table_absent_cursor_not_advanced(self):
        self._write(self._crash(1_700_000_000.0))
        fake, mock_cur = _mock_psycopg2(table_present=False)
        sys.modules["psycopg2"] = fake
        try:
            rc = B.tail_and_insert(self.log_path, self.state_path, "postgresql://x/y")
        finally:
            sys.modules.pop("psycopg2", None)
        self.assertEqual(rc, 0)  # 表缺 fail-soft exit 0
        # cursor 不前進，等表 land 後補全。
        self.assertEqual(B._load_cursor(self.state_path), 0)

    def test_insert_error_per_row_does_not_abort_others(self):
        # 第一行 INSERT 拋，第二行仍應被嘗試（per-row fail-soft）。
        self._write(self._crash(1_700_000_000.0), self._crash(1_700_000_100.0))
        fake, mock_cur = _mock_psycopg2(rowcount=1)
        call_count = {"n": 0}

        def exec_side_effect(sql, params=None):
            if "INSERT INTO audit_events" in sql:
                call_count["n"] += 1
                if call_count["n"] == 1:
                    raise RuntimeError("transient INSERT error")
            return None

        mock_cur.execute.side_effect = exec_side_effect
        sys.modules["psycopg2"] = fake
        try:
            rc = B.tail_and_insert(self.log_path, self.state_path, "postgresql://x/y")
        finally:
            sys.modules.pop("psycopg2", None)
        self.assertEqual(rc, 0)
        # 兩個 INSERT 都被嘗試（第一個拋、第二個照跑）→ 不因單行錯誤中止。
        self.assertEqual(call_count["n"], 2)

    def test_no_new_rows_since_cursor(self):
        self._write(self._crash(1_700_000_000.0))
        # cursor 已在 file 末尾。
        B._save_cursor(self.state_path, self.log_path.stat().st_size)
        fake, mock_cur = _mock_psycopg2(rowcount=1)
        sys.modules["psycopg2"] = fake
        try:
            rc = B.tail_and_insert(self.log_path, self.state_path, "postgresql://x/y")
        finally:
            sys.modules.pop("psycopg2", None)
        self.assertEqual(rc, 0)
        # 沒新行 → 不 connect、不 INSERT。
        fake.connect.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
