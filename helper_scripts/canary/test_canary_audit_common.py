#!/usr/bin/env python3
"""test_canary_audit_common.py — ENGINE-AUDIT-VISIBILITY direct-write unit tests (2026-06-15)

MODULE_NOTE
模塊用途：canary_audit_common（audit_events 寫入共用層）+ engine_watchdog direct
  fail-soft write 路徑的單元測試。涵蓋：
    1. event→(event_type, severity) 映射正確（每事件類）
    2. dedup_key 確定性 + 跨路徑同形（同 ts → 同 key；direct write 與 bridge 一致）
    3. DSN 解析序（FILE → URL → POSTGRES_* → OPENCLAW_DATA_DIR 推導備援）
    4. INSERT shape（欄位 / NOT EXISTS dedup 子查 / 不含 created_at）
    5. direct write fail-soft：DB 失敗（無 DSN / psycopg2 缺 / connect 拋）絕不拋
    6. watchdog _emit_audit_event_best_effort：crash/outage/recovered 三類映射正確
依賴：canary_audit_common / engine_watchdog；unittest.mock（mock DB 層）；無真 PG。
硬邊界：全 mock，無真連線；驗 direct write 的例外絕不冒泡進 watchdog 邏輯。

跑：python3 -m pytest helper_scripts/canary/test_canary_audit_common.py
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import canary_audit_common as C  # noqa: E402
import engine_watchdog as W  # noqa: E402


class TestEventMapping(unittest.TestCase):
    """每個 canary 事件名 → 正確 (event_type, severity)。"""

    def test_engine_crash_maps_critical(self):
        self.assertEqual(C.map_canary_to_audit("ENGINE_CRASH"), ("engine_crash", "critical"))

    def test_network_outage_maps_warning(self):
        self.assertEqual(C.map_canary_to_audit("NETWORK_OUTAGE"), ("network_outage", "warning"))

    def test_engine_recovered_maps_info(self):
        self.assertEqual(C.map_canary_to_audit("ENGINE_RECOVERED"), ("engine_recovered", "info"))

    def test_circuit_broken_maps_critical(self):
        self.assertEqual(
            C.map_canary_to_audit("RESTART_CIRCUIT_BROKEN"),
            ("restart_circuit_broken", "critical"),
        )

    def test_unmapped_event_returns_none(self):
        self.assertIsNone(C.map_canary_to_audit("RESTART_SUCCESS"))
        self.assertIsNone(C.map_canary_to_audit("TRADING_INERT_PROLONGED"))


class TestDedupKey(unittest.TestCase):
    """dedup_key 確定性 + 同 ts 同 key（跨路徑一致是 backstop 去重命脈）。"""

    def test_deterministic_same_ts_same_key(self):
        k1 = C.build_dedup_key("engine_crash", 1_700_000_000.123)
        k2 = C.build_dedup_key("engine_crash", 1_700_000_000.123)
        self.assertEqual(k1, k2)

    def test_key_shape(self):
        # 固定 UTC 毫秒精度，Z 結尾；前綴 source|event_type|。
        k = C.build_dedup_key("engine_crash", 1_700_000_000.0)
        self.assertEqual(k, "engine_watchdog|engine_crash|2023-11-14T22:13:20.000Z")

    def test_different_event_type_different_key(self):
        ts = 1_700_000_000.0
        self.assertNotEqual(
            C.build_dedup_key("engine_crash", ts),
            C.build_dedup_key("network_outage", ts),
        )

    def test_sub_millisecond_jitter_collapses(self):
        # 微秒抖動低於毫秒 → 同 key（防 direct/bridge 因微秒差異去重失效）。
        k1 = C.build_dedup_key("engine_crash", 1_700_000_000.1234)
        k2 = C.build_dedup_key("engine_crash", 1_700_000_000.1239)
        self.assertEqual(k1, k2)


class TestResolveDsn(unittest.TestCase):
    """DSN 解析序：FILE → URL → POSTGRES_* → OPENCLAW_DATA_DIR 推導備援
    （第 4 分支專測見 TestResolveDsnDataDirFallback）。"""

    def setUp(self):
        # 清掉所有相關 env，逐項測試。OPENCLAW_DATA_DIR 也清：第 4 分支推導
        # 上線後，跑測試的機器若設了它（且契約檔在）會污染 unbuildable 斷言。
        self._saved = {
            k: os.environ.pop(k, None)
            for k in (
                "OPENCLAW_DATABASE_URL_FILE", "OPENCLAW_DATABASE_URL",
                "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB",
                "POSTGRES_HOST", "POSTGRES_PORT", "OPENCLAW_DATA_DIR",
            )
        }

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_file_wins(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "dsn"
            p.write_text("postgresql://from/file\n")
            os.environ["OPENCLAW_DATABASE_URL_FILE"] = str(p)
            os.environ["OPENCLAW_DATABASE_URL"] = "postgresql://from/url"
            self.assertEqual(C.resolve_dsn(), "postgresql://from/file")

    def test_file_missing_falls_through_to_url(self):
        os.environ["OPENCLAW_DATABASE_URL_FILE"] = "/no/such/dsn/file"
        os.environ["OPENCLAW_DATABASE_URL"] = "postgresql://from/url"
        self.assertEqual(C.resolve_dsn(), "postgresql://from/url")

    def test_postgres_env_assembled(self):
        os.environ["POSTGRES_USER"] = "u"
        os.environ["POSTGRES_PASSWORD"] = "p"
        os.environ["POSTGRES_DB"] = "d"
        self.assertEqual(C.resolve_dsn(), "postgresql://u:p@127.0.0.1:5432/d")

    def test_none_when_unbuildable(self):
        self.assertIsNone(C.resolve_dsn())


class TestResolveDsnDataDirFallback(unittest.TestCase):
    """第 4 分支（WATCHDOG-AUDIT-DSN-1）：三顯式源全失敗後由 OPENCLAW_DATA_DIR
    推導 runtime_secrets/openclaw_database_url；顯式 env 永遠優先；DATA_DIR 未設
    絕不猜默認路徑。"""

    def setUp(self):
        # 清掉所有相關 env（含 OPENCLAW_DATA_DIR），逐項測試。
        self._saved = {
            k: os.environ.pop(k, None)
            for k in (
                "OPENCLAW_DATABASE_URL_FILE", "OPENCLAW_DATABASE_URL",
                "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB",
                "POSTGRES_HOST", "POSTGRES_PORT", "OPENCLAW_DATA_DIR",
            )
        }

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _write_contract_file(self, data_dir: Path, content: str) -> Path:
        # 契約路徑 = <data_dir>/runtime_secrets/openclaw_database_url
        # （與 restart_all.sh / engine unit 同一契約）。
        secret_dir = data_dir / "runtime_secrets"
        secret_dir.mkdir(parents=True, exist_ok=True)
        p = secret_dir / "openclaw_database_url"
        p.write_text(content)
        return p

    def test_derived_from_data_dir_when_all_explicit_missing(self):
        # (a) 三顯式源全缺 + DATA_DIR 契約檔有 DSN → 回檔內容（strip 換行）。
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            self._write_contract_file(Path(td), "postgresql://from/derived\n")
            with mock.patch.dict(os.environ, {"OPENCLAW_DATA_DIR": td}):
                self.assertEqual(C.resolve_dsn(), "postgresql://from/derived")

    def test_explicit_file_env_wins_over_derivation(self):
        # (b) OPENCLAW_DATABASE_URL_FILE 顯式設時優先於推導。
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            self._write_contract_file(Path(td), "postgresql://from/derived\n")
            explicit = Path(td) / "explicit_dsn"
            explicit.write_text("postgresql://from/explicit-file\n")
            with mock.patch.dict(os.environ, {
                "OPENCLAW_DATA_DIR": td,
                "OPENCLAW_DATABASE_URL_FILE": str(explicit),
            }):
                self.assertEqual(C.resolve_dsn(), "postgresql://from/explicit-file")

    def test_no_data_dir_returns_none_never_guesses_default(self):
        # (c) OPENCLAW_DATA_DIR 未設 → None，且「零檔案讀取嘗試」。
        # 鐵則咬合（P2-2）：把模組 namespace 的 Path.read_text 換成必炸探針——
        # 若實作猜任何默認路徑（如 /tmp/openclaw），必經 read_text → AssertionError
        # 非 OSError/ValueError、穿透 fail-soft → 測試必紅；不依賴跑測試機器上
        # 是否恰好存在 /tmp/openclaw 契約檔。
        with mock.patch.object(
            C.Path,
            "read_text",
            side_effect=AssertionError("不得嘗試任何檔案讀取（默認路徑猜測）"),
        ) as read_probe:
            self.assertIsNone(C.resolve_dsn())
        self.assertEqual(read_probe.call_count, 0)

    def test_data_dir_set_but_contract_file_missing_returns_none(self):
        # (d) DATA_DIR 設但契約檔不存在 → None（fail-soft）。
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.dict(os.environ, {"OPENCLAW_DATA_DIR": td}):
                self.assertIsNone(C.resolve_dsn())

    def test_blank_contract_file_returns_none(self):
        # (e) 契約檔存在但空白（只有 whitespace）→ None。
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            self._write_contract_file(Path(td), "   \n")
            with mock.patch.dict(os.environ, {"OPENCLAW_DATA_DIR": td}):
                self.assertIsNone(C.resolve_dsn())

    def test_partial_postgres_env_falls_through_to_derivation(self):
        # (P2-5) POSTGRES_* 部分設定（僅 USER，缺 PASSWORD/DB）＝顯式源「部分失敗」
        # → 仍落到第 4 步推導。釘住語意：推導的觸發條件是「三顯式源皆組不出 DSN」，
        # 不是「顯式 env 全空」。
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            self._write_contract_file(Path(td), "postgresql://from/derived\n")
            with mock.patch.dict(os.environ, {
                "OPENCLAW_DATA_DIR": td,
                "POSTGRES_USER": "only-user",
            }):
                self.assertEqual(C.resolve_dsn(), "postgresql://from/derived")


class TestInsertShape(unittest.TestCase):
    """INSERT 欄位 shape + dedup NOT EXISTS 子查 + 不含 created_at。"""

    def _row(self):
        return C.build_audit_row(
            event_type="engine_crash",
            severity="critical",
            summary="boom",
            event_details={"snapshot_age_seconds": 50.0, "total_crashes": 1},
            notes="n",
            dedup_key="engine_watchdog|engine_crash|2023-11-14T22:13:20.000Z",
        )

    def test_build_row_injects_dedup_key_and_source(self):
        row = self._row()
        self.assertEqual(row["event_source"], "engine_watchdog")
        self.assertEqual(
            row["event_details"]["dedup_key"],
            "engine_watchdog|engine_crash|2023-11-14T22:13:20.000Z",
        )

    def test_insert_sql_targets_audit_events_with_not_exists(self):
        mock_cur = mock.MagicMock()
        mock_cur.rowcount = 1
        inserted = C.insert_audit_event_if_absent(mock_cur, self._row())
        self.assertTrue(inserted)
        sql = mock_cur.execute.call_args[0][0]
        self.assertIn("INSERT INTO audit_events", sql)
        self.assertIn("event_details->>'dedup_key'", sql)
        self.assertIn("WHERE NOT EXISTS", sql)
        # 不含 created_at（schema DEFAULT now()）。
        self.assertNotIn("created_at", sql)
        # 欄位順序與 SELECT placeholder 對齊（6 欄位）。
        self.assertIn(
            "event_source, event_type, severity, summary, event_details, notes", sql
        )

    def test_insert_dup_returns_false(self):
        mock_cur = mock.MagicMock()
        mock_cur.rowcount = 0  # NOT EXISTS 命中既有 dedup_key → 0 row inserted
        self.assertFalse(C.insert_audit_event_if_absent(mock_cur, self._row()))

    def test_details_passed_as_sorted_json(self):
        mock_cur = mock.MagicMock()
        mock_cur.rowcount = 1
        C.insert_audit_event_if_absent(mock_cur, self._row())
        params = mock_cur.execute.call_args[0][1]
        # params[4] = details json；params[6] = dedup_key（WHERE 子查）。
        self.assertIn("dedup_key", params[4])
        self.assertEqual(params[6], "engine_watchdog|engine_crash|2023-11-14T22:13:20.000Z")


class TestDirectWriteFailSoft(unittest.TestCase):
    """direct write 路徑：任何 DB 失敗都被吞沒，絕不拋。"""

    def _row(self):
        return C.build_audit_row(
            event_type="engine_crash", severity="critical", summary="s",
            event_details={}, notes="n", dedup_key="k",
        )

    def test_no_dsn_returns_false_no_raise(self):
        with mock.patch.object(C, "resolve_dsn", return_value=None):
            self.assertFalse(C.write_audit_event_best_effort(self._row()))

    def test_psycopg2_missing_returns_false_no_raise(self):
        # 模擬 import psycopg2 失敗。
        with mock.patch.object(C, "resolve_dsn", return_value="postgresql://x/y"):
            real_import = __import__

            def fake_import(name, *a, **k):
                if name == "psycopg2":
                    raise ImportError("no psycopg2")
                return real_import(name, *a, **k)

            with mock.patch("builtins.__import__", side_effect=fake_import):
                self.assertFalse(C.write_audit_event_best_effort(self._row()))

    def test_connect_raises_is_swallowed(self):
        fake_psycopg2 = mock.MagicMock()
        fake_psycopg2.connect.side_effect = RuntimeError("connection refused")
        with mock.patch.object(C, "resolve_dsn", return_value="postgresql://x/y"):
            sys.modules["psycopg2"] = fake_psycopg2
            try:
                # 必不拋；回 False。
                self.assertFalse(C.write_audit_event_best_effort(self._row()))
            finally:
                sys.modules.pop("psycopg2", None)

    def test_successful_insert_returns_true_with_bounded_timeout(self):
        mock_cur = mock.MagicMock()
        mock_cur.rowcount = 1
        mock_cur.__enter__.return_value = mock_cur
        mock_cur.__exit__.return_value = False
        mock_conn = mock.MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_conn.__enter__.return_value = mock_conn
        mock_conn.__exit__.return_value = False
        fake_psycopg2 = mock.MagicMock()
        fake_psycopg2.connect.return_value = mock_conn
        with mock.patch.object(C, "resolve_dsn", return_value="postgresql://x/y"):
            sys.modules["psycopg2"] = fake_psycopg2
            try:
                self.assertTrue(C.write_audit_event_best_effort(self._row()))
            finally:
                sys.modules.pop("psycopg2", None)
        # connect 必帶 5s connect_timeout（DB 卡住不得拖住 watchdog）。
        _, kwargs = fake_psycopg2.connect.call_args
        self.assertEqual(kwargs.get("connect_timeout"), 5)
        self.assertIn("statement_timeout=5000", kwargs.get("options", ""))


class TestWatchdogEmitWiring(unittest.TestCase):
    """engine_watchdog._emit_audit_event_best_effort：三類事件映射正確且 fail-soft。"""

    def test_crash_emits_critical_engine_crash_row(self):
        captured = {}

        def fake_write(row):
            captured["row"] = row
            return True

        with mock.patch.object(W.canary_audit_common, "write_audit_event_best_effort",
                               side_effect=fake_write):
            W._emit_audit_event_best_effort(
                "ENGINE_CRASH", 1_700_000_000.0, "summary",
                {"snapshot_age_seconds": 50.0, "total_crashes": 1, "restart_outcome": "restart_failed"},
                "notes",
            )
        row = captured["row"]
        self.assertEqual(row["event_type"], "engine_crash")
        self.assertEqual(row["severity"], "critical")
        self.assertEqual(row["event_source"], "engine_watchdog")
        self.assertEqual(
            row["event_details"]["dedup_key"],
            "engine_watchdog|engine_crash|2023-11-14T22:13:20.000Z",
        )
        self.assertEqual(row["event_details"]["restart_outcome"], "restart_failed")
        self.assertIn("hostname", row["event_details"])

    def test_outage_emits_warning_row(self):
        captured = {}
        with mock.patch.object(W.canary_audit_common, "write_audit_event_best_effort",
                               side_effect=lambda r: captured.update(row=r) or True):
            W._emit_audit_event_best_effort(
                "NETWORK_OUTAGE", 1_700_000_000.0, "s", {"snapshot_age_seconds": 60.0}, "n",
            )
        self.assertEqual(captured["row"]["event_type"], "network_outage")
        self.assertEqual(captured["row"]["severity"], "warning")

    def test_recovered_emits_info_row(self):
        captured = {}
        with mock.patch.object(W.canary_audit_common, "write_audit_event_best_effort",
                               side_effect=lambda r: captured.update(row=r) or True):
            W._emit_audit_event_best_effort(
                "ENGINE_RECOVERED", 1_700_000_000.0, "s", {"total_crashes": 2}, "n",
            )
        self.assertEqual(captured["row"]["event_type"], "engine_recovered")
        self.assertEqual(captured["row"]["severity"], "info")

    def test_unmapped_event_is_noop(self):
        called = {"n": 0}
        with mock.patch.object(W.canary_audit_common, "write_audit_event_best_effort",
                               side_effect=lambda r: called.__setitem__("n", called["n"] + 1)):
            W._emit_audit_event_best_effort("RESTART_SUCCESS", 1.0, "s", {}, "n")
        self.assertEqual(called["n"], 0)

    def test_write_exception_does_not_propagate(self):
        # 硬約束：即便 write 拋，emit 層 catch-all 也吞沒，絕不冒泡進 watchdog 偵測/重啟。
        with mock.patch.object(W.canary_audit_common, "write_audit_event_best_effort",
                               side_effect=RuntimeError("boom")):
            try:
                W._emit_audit_event_best_effort("ENGINE_CRASH", 1.0, "s", {}, "n")
            except Exception as exc:  # noqa: BLE001
                self.fail(f"emit must not propagate, but raised: {exc!r}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
