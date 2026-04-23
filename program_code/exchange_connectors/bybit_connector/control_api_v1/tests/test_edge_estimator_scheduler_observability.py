"""
Tests for SCHEDULER-FAILURE-OBSERVABILITY-1
排程器失敗可觀察性測試

Coverage / 覆蓋：
  1. Normal cycle → one DB row with status='ok' per mode
     正常 cycle → 每 mode 一行 status='ok'
  2. Backfill succeeds, JS estimation fails → row with status='fail',
     error_class reflects JS exception type
     Backfill 成功、JS 失敗 → status='fail'，error_class 記 JS 異常類型
  3. DB INSERT itself fails → no raise, logger.warning captured
     DB INSERT 自身失敗 → 不 raise，caplog 捕到 logger.warning

Principles honoured / 遵循原則：
  - CLAUDE.md §二 原則 8 交易可解釋：每個 scheduler cycle 都可 SQL 重建
  - CLAUDE.md §二 原則 10 認知誠實：只在 JS 估計真正 raise 時寫 status='fail'
  - CLAUDE.md §七 雙語注釋
"""
from __future__ import annotations

import logging
from typing import Any, Optional
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures / 幫助工具
# ---------------------------------------------------------------------------

def _make_scheduler(modes=("demo",), **kwargs):
    """
    Build a fresh EdgeEstimatorScheduler with deps mocked externally.
    建立全新 EdgeEstimatorScheduler（外部 mock 依賴）。
    """
    from program_code.exchange_connectors.bybit_connector.control_api_v1.app.edge_estimator_scheduler import (
        EdgeEstimatorScheduler,
    )
    return EdgeEstimatorScheduler(modes=modes, interval_s=3600.0, days_back=7, **kwargs)


class _FakeCursor:
    """
    Minimal psycopg2 cursor stub capturing INSERT statements.
    極簡 psycopg2 cursor stub，記下 INSERT 參數。
    """

    def __init__(self, capture: list[tuple[str, tuple]]):
        self._capture = capture

    def execute(self, sql: str, params: tuple) -> None:
        self._capture.append((sql, params))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeConn:
    """
    Minimal psycopg2 connection stub / psycopg2 connection stub。
    """

    def __init__(self, capture: list[tuple[str, tuple]], insert_raises: Optional[Exception] = None):
        self._capture = capture
        self._insert_raises = insert_raises
        self.committed = False

    def cursor(self):
        if self._insert_raises is not None:
            class _RaisingCursor:
                def __init__(self, exc):
                    self._exc = exc

                def execute(self, *a, **kw):
                    raise self._exc

                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc, tb):
                    return False

            return _RaisingCursor(self._insert_raises)
        return _FakeCursor(self._capture)

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        pass


def _fake_get_pg_conn(conn):
    """
    Build a context-manager factory that yields the given conn.
    建立 context-manager 工廠，yield 指定 conn（或 None）。
    """
    from contextlib import contextmanager

    @contextmanager
    def _cm():
        yield conn

    return _cm


# ---------------------------------------------------------------------------
# Test 1 — normal cycle writes status='ok'
# 測試 1：正常 cycle 寫 status='ok'
# ---------------------------------------------------------------------------

def test_run_cycle_ok_writes_ok_row():
    """Normal cycle → 1 row status='ok', error_class=None.
    正常 cycle → 1 行 status='ok'，error_class=None。"""
    captured: list[tuple[str, tuple]] = []
    conn = _FakeConn(captured)

    sched = _make_scheduler(modes=("demo",))

    import program_code.exchange_connectors.bybit_connector.control_api_v1.app.edge_estimator_scheduler as mod

    with patch.object(sched, "_run_backfill", return_value={"filled": 5, "grid_merged": 0, "excluded": 0, "split_blend": 0}), \
         patch.object(sched, "_run_one_mode", return_value={"n_cells": 3, "grand_mean_bps": 12.5}), \
         patch.object(mod, "get_pg_conn", _fake_get_pg_conn(conn), create=True):
        # get_pg_conn is imported lazily inside _record_cycle_event,
        # so we additionally patch db_pool.get_pg_conn at source.
        # get_pg_conn 在 _record_cycle_event 內懶 import，需在源頭 patch。
        with patch(
            "program_code.exchange_connectors.bybit_connector.control_api_v1.app.db_pool.get_pg_conn",
            _fake_get_pg_conn(conn),
        ):
            results = sched._run_cycle(reason="test_ok")

    assert "demo" in results
    assert results["demo"].get("n_cells") == 3
    assert len(captured) == 1, f"expected 1 INSERT, got {len(captured)}"
    sql, params = captured[0]
    assert "observability.engine_events" in sql
    ts_ms, event_type, source, config_name, payload_json = params
    assert event_type == "scheduler_ok"
    assert source == "edge_estimator_scheduler"
    assert config_name is None
    import json as _json
    payload = _json.loads(payload_json)
    assert payload["status"] == "ok"
    assert payload["error_class"] is None
    assert payload["error_msg"] is None
    assert payload["mode"] == "demo"
    assert payload["engine_mode"] == "demo"
    assert payload["scheduler_name"] == "edge_estimator"
    assert payload["n_cells"] == 3
    assert payload["grand_mean_bps"] == pytest.approx(12.5)
    assert isinstance(payload["duration_ms"], int)
    assert conn.committed is True


# ---------------------------------------------------------------------------
# Test 2 — JS estimation fails → status='fail', error_class set
# 測試 2：JS 估計失敗 → status='fail'，error_class 有值
# ---------------------------------------------------------------------------

def test_run_cycle_js_fail_writes_fail_row():
    """JS estimation raises → row with status='fail', error_class='RuntimeError'.
    JS 估計 raise → status='fail'，error_class='RuntimeError'。"""
    captured: list[tuple[str, tuple]] = []
    conn = _FakeConn(captured)

    sched = _make_scheduler(modes=("demo",))

    with patch.object(sched, "_run_backfill", return_value={"filled": 1, "grid_merged": 0, "excluded": 0, "split_blend": 0}), \
         patch.object(sched, "_run_one_mode", side_effect=RuntimeError("simulated JS failure")), \
         patch(
             "program_code.exchange_connectors.bybit_connector.control_api_v1.app.db_pool.get_pg_conn",
             _fake_get_pg_conn(conn),
         ):
        results = sched._run_cycle(reason="test_fail")

    assert "demo" in results
    assert "error" in results["demo"]
    assert sched._failures == 1
    assert len(captured) == 1
    sql, params = captured[0]
    ts_ms, event_type, source, config_name, payload_json = params
    assert event_type == "scheduler_fail"
    import json as _json
    payload = _json.loads(payload_json)
    assert payload["status"] == "fail"
    assert payload["error_class"] == "RuntimeError"
    assert "simulated JS failure" in payload["error_msg"]
    # When JS failed, results_for_mode == {"error": str(exc)} — a dict without
    # n_cells / grand_mean_bps keys; writer falls back to 0 / 0.0 defaults.
    # JS 失敗時 results_for_mode == {"error": ...}，無 n_cells/grand_mean_bps
    # 鍵，writer 回退 0 / 0.0 預設值。
    assert payload["n_cells"] == 0
    assert payload["grand_mean_bps"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Test 3 — DB INSERT itself fails → no raise, warning logged
# 測試 3：DB INSERT 自身失敗 → 不 raise，warning 有記錄
# ---------------------------------------------------------------------------

def test_record_cycle_event_db_insert_failure_is_fail_soft(caplog):
    """INSERT raises OperationalError → scheduler swallows, logs warning.
    INSERT raise OperationalError → scheduler 吞掉，log warning。"""
    # Simulate a DB-side failure (e.g. connection dropped mid-INSERT)
    # 模擬 DB 端失敗（如 INSERT 中途連線中斷）
    conn = _FakeConn([], insert_raises=RuntimeError("pg conn lost"))
    sched = _make_scheduler(modes=("demo",))

    caplog.set_level(logging.WARNING,
                     logger="program_code.exchange_connectors.bybit_connector.control_api_v1.app.edge_estimator_scheduler")

    # Successful backfill + JS, but INSERT will raise.
    # Backfill + JS 成功，但 INSERT 會 raise。
    with patch.object(sched, "_run_backfill", return_value={"filled": 0, "grid_merged": 0, "excluded": 0, "split_blend": 0}), \
         patch.object(sched, "_run_one_mode", return_value={"n_cells": 1, "grand_mean_bps": 0.0}), \
         patch(
             "program_code.exchange_connectors.bybit_connector.control_api_v1.app.db_pool.get_pg_conn",
             _fake_get_pg_conn(conn),
         ):
        # Must not raise / 不可 raise
        results = sched._run_cycle(reason="test_insert_fail")

    assert "demo" in results
    # Scheduler cycle itself succeeded (JS OK); only observability writer failed.
    # Scheduler cycle 本身 OK（JS 成功），只是 observability writer 失敗。
    assert "error" not in results["demo"]
    # Warning must have been emitted / 必須 emit warning
    relevant = [r for r in caplog.records
                if "observability INSERT failed" in r.getMessage()
                or "DB pool unavailable" in r.getMessage()]
    assert relevant, (
        "expected fail-soft warning when INSERT raises, got: "
        + "; ".join(r.getMessage() for r in caplog.records)
    )


# ---------------------------------------------------------------------------
# Test 4 (extra) — pool unavailable (get_conn returns None) → warning, no crash
# 測試 4（額外）：pool 不可達（get_conn 返 None）→ warning，不 crash
# ---------------------------------------------------------------------------

def test_record_cycle_event_pool_unavailable_is_fail_soft(caplog):
    """get_pg_conn yields None → fail-soft warning, cycle continues.
    get_pg_conn yield None → fail-soft warning，cycle 繼續。"""
    sched = _make_scheduler(modes=("demo",))

    caplog.set_level(logging.WARNING,
                     logger="program_code.exchange_connectors.bybit_connector.control_api_v1.app.edge_estimator_scheduler")

    with patch.object(sched, "_run_backfill", return_value={"filled": 0, "grid_merged": 0, "excluded": 0, "split_blend": 0}), \
         patch.object(sched, "_run_one_mode", return_value={"n_cells": 0, "grand_mean_bps": 0.0}), \
         patch(
             "program_code.exchange_connectors.bybit_connector.control_api_v1.app.db_pool.get_pg_conn",
             _fake_get_pg_conn(None),
         ):
        results = sched._run_cycle(reason="test_pool_none")

    assert "demo" in results
    assert any("DB pool unavailable" in r.getMessage() for r in caplog.records)


# ---------------------------------------------------------------------------
# Test 5 (E4 audit follow-up) — backfill fails + JS succeeds → status='ok'
# AND payload.backfill_error_class captures the backfill error class name.
# The pre-fix test suite had no scenario exercising this asymmetric branch;
# E4 audit flagged it because `_record_cycle_event` line 306-308 set
# `backfill_error_class` only on this specific path.
# 測試 5（E4 audit 補）：backfill 失敗 + JS 成功 → status='ok' 且
# payload.backfill_error_class 捕獲 backfill 錯誤類名。原測試套件缺這
# 不對稱分支；E4 審核指出 `backfill_error_class` 只在此路徑設值，無測試覆蓋。
# ---------------------------------------------------------------------------

def test_backfill_fail_js_ok_records_backfill_error_class():
    """backfill raises, JS succeeds → status='ok' + backfill_error_class set.
    backfill 拋錯、JS 成功 → status='ok' 且 backfill_error_class 有值。"""
    captured: list[tuple[str, tuple]] = []
    conn = _FakeConn(captured)

    sched = _make_scheduler(modes=("demo",))

    class _BackfillBlewUp(RuntimeError):
        """Custom error class for precise class-name assertion.
        自訂 error class 以精確斷言 class 名稱。"""
        pass

    with patch.object(sched, "_run_backfill", side_effect=_BackfillBlewUp("simulated backfill fail")), \
         patch.object(sched, "_run_one_mode", return_value={"n_cells": 7, "grand_mean_bps": -8.3}), \
         patch(
             "program_code.exchange_connectors.bybit_connector.control_api_v1.app.db_pool.get_pg_conn",
             _fake_get_pg_conn(conn),
         ):
        results = sched._run_cycle(reason="test_backfill_fail_js_ok")

    # JS still ran and produced summary / JS 仍執行並產出摘要
    assert "demo" in results
    assert results["demo"].get("n_cells") == 7
    assert sched._failures == 0, "backfill failure must not bump _failures counter"

    # Exactly one obs event written / 恰寫一行 obs event
    assert len(captured) == 1
    sql, params = captured[0]
    _, event_type, _, _, payload_json = params

    # Status is still 'ok' because JS succeeded — backfill fail is non-fatal
    # status 仍 'ok' 因 JS 成功 — backfill 失敗不致命
    assert event_type == "scheduler_ok"

    import json as _json
    payload = _json.loads(payload_json)
    assert payload["status"] == "ok"
    assert payload["error_class"] is None
    assert payload["error_msg"] is None

    # The distinguishing assertion: backfill error class captured
    # 關鍵斷言：backfill 錯誤類名被捕
    assert payload["backfill_error_class"] == "_BackfillBlewUp", (
        f"expected 'backfill_error_class'='_BackfillBlewUp', got "
        f"{payload.get('backfill_error_class')!r}"
    )
    # JS succeeded so summary fields populated / JS 成功，摘要欄位填入
    assert payload["n_cells"] == 7
    assert payload["grand_mean_bps"] == pytest.approx(-8.3)
