"""Tests for governance_divergence_flush (P5-SM-OPTION2 B-3 flusher).

P5-SM-OPTION2 B-3 flusher 單元測試。

MODULE_NOTE:
    覆蓋 flusher 的關鍵不變量（G-2）：
      1. flush happy path：讀 comparator counter → UPSERT 投影表（SQL + 參數正確）。
      2. **fail-soft 不傳播**：PG 不可用 / cursor.execute 拋例外 / commit 拋例外 →
         flush 回 False，**絕不向 caller 拋**（不影響權威路徑 / comparator）。
      3. flag 狀態正確記錄（flag-ON / flag-OFF / flag 讀取失敗 → 保守 False）。
      4. counter 讀取拋例外 → fail-soft 回 False。
      5. **不持有 comparator lock 過久**：flush 只呼叫 get_divergence_counters（取 dict
         copy），PG I/O 不在 comparator lock 內（以 record_divergence 在 flush 期間仍可
         並發運作驗證契約）。

Mac dev / Linux runtime（從 OPENCLAW_BASE_DIR 切換）：
    cd "$OPENCLAW_BASE_DIR" && ./venvs/mac_dev/bin/python -m pytest \\
        program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_governance_divergence_flush.py -v
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from program_code.exchange_connectors.bybit_connector.control_api_v1.app import (
    governance_divergence as divergence,
    governance_divergence_flush as flush,
)


@pytest.fixture(autouse=True)
def _reset_comparator() -> Any:
    """每個 test 前後清空 comparator counter（測試隔離）。"""
    divergence.reset_divergence_state()
    yield
    divergence.reset_divergence_state()


def _make_conn(cur: MagicMock) -> MagicMock:
    """建一個 mock PG conn：cursor() context manager 回給定 cur，commit 可驗。"""
    conn = MagicMock()
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    return conn


@contextmanager
def _patch_pg_conn(conn: Any):
    """patch db_pool.get_pg_conn 回給定 conn（None=PG 不可用）。"""
    @contextmanager
    def _fake_get_pg_conn():
        yield conn

    with patch(
        "program_code.exchange_connectors.bybit_connector.control_api_v1.app.db_pool.get_pg_conn",
        _fake_get_pg_conn,
    ):
        yield


# ─────────────────────────────────────────────────────────────────────────────
# 1. happy path
# ─────────────────────────────────────────────────────────────────────────────


def test_flush_happy_path_upserts_counters() -> None:
    """flush 讀 comparator counter → UPSERT 投影表（SQL INSERT...ON CONFLICT + 參數）。"""
    # 先讓 comparator 累積 3 筆（2 match + 1 divergence）。
    divergence.record_divergence(op="acquire", rust_outcome="granted", python_outcome="granted")
    divergence.record_divergence(op="acquire", rust_outcome="granted", python_outcome="granted")
    divergence.record_divergence(op="acquire", rust_outcome="granted", python_outcome="denied")

    cur = MagicMock()
    conn = _make_conn(cur)
    with _patch_pg_conn(conn), patch.object(flush, "is_lease_ipc_enabled", return_value=True, create=True):
        # is_lease_ipc_enabled 是在 flush 內 lazy import；改 patch bridge 模塊。
        with patch(
            "program_code.exchange_connectors.bybit_connector.control_api_v1.app.governance_lease_bridge.is_lease_ipc_enabled",
            return_value=True,
        ):
            ok = flush.flush_divergence_snapshot_once()

    assert ok is True
    # 驗 execute 被呼叫且 SQL 是 INSERT ... ON CONFLICT (snapshot_key) DO UPDATE。
    assert cur.execute.call_count == 1
    sql, params = cur.execute.call_args[0]
    assert "INSERT INTO learning.lease_ipc_divergence_snapshot" in sql
    assert "ON CONFLICT (snapshot_key) DO UPDATE" in sql
    assert "now()" in sql  # updated_at 用 DB-side now()
    # 參數順序：(snapshot_key, total, matches, divergences, flag_enabled, flusher_ts_ms)
    assert params[0] == "singleton"
    assert params[1] == 3  # total
    assert params[2] == 2  # matches
    assert params[3] == 1  # divergences
    assert params[4] is True  # flag_enabled
    assert isinstance(params[5], int)  # flusher_ts_ms
    conn.commit.assert_called_once()


def test_flush_records_flag_off() -> None:
    """flag-OFF 時 flag_enabled 參數記 False（soak gate 會據此判非 PASS）。"""
    cur = MagicMock()
    conn = _make_conn(cur)
    with _patch_pg_conn(conn):
        with patch(
            "program_code.exchange_connectors.bybit_connector.control_api_v1.app.governance_lease_bridge.is_lease_ipc_enabled",
            return_value=False,
        ):
            ok = flush.flush_divergence_snapshot_once()
    assert ok is True
    _, params = cur.execute.call_args[0]
    assert params[4] is False


def test_flush_flag_read_failure_defaults_false() -> None:
    """flag 讀取拋例外 → 保守記 False，flush 仍成功（不因 flag 讀取失敗中斷）。"""
    cur = MagicMock()
    conn = _make_conn(cur)
    with _patch_pg_conn(conn):
        with patch(
            "program_code.exchange_connectors.bybit_connector.control_api_v1.app.governance_lease_bridge.is_lease_ipc_enabled",
            side_effect=RuntimeError("flag boom"),
        ):
            ok = flush.flush_divergence_snapshot_once()
    assert ok is True
    _, params = cur.execute.call_args[0]
    assert params[4] is False


# ─────────────────────────────────────────────────────────────────────────────
# 2. fail-soft 不傳播（G-2 核心）
# ─────────────────────────────────────────────────────────────────────────────


def test_flush_pg_unavailable_returns_false_no_raise() -> None:
    """PG 不可用（get_pg_conn 回 None）→ flush 回 False，不拋（G-2）。"""
    with _patch_pg_conn(None):
        with patch(
            "program_code.exchange_connectors.bybit_connector.control_api_v1.app.governance_lease_bridge.is_lease_ipc_enabled",
            return_value=True,
        ):
            ok = flush.flush_divergence_snapshot_once()
    assert ok is False  # fail-soft，不拋例外


def test_flush_execute_exception_swallowed() -> None:
    """cursor.execute 拋例外 → flush 回 False，**絕不向 caller 傳播**（G-2）。"""
    cur = MagicMock()
    cur.execute.side_effect = RuntimeError("pg write boom")
    conn = _make_conn(cur)
    with _patch_pg_conn(conn):
        with patch(
            "program_code.exchange_connectors.bybit_connector.control_api_v1.app.governance_lease_bridge.is_lease_ipc_enabled",
            return_value=True,
        ):
            # 不應拋；fail-soft 回 False。
            ok = flush.flush_divergence_snapshot_once()
    assert ok is False


def test_flush_commit_exception_swallowed() -> None:
    """conn.commit 拋例外 → flush 回 False，不傳播（G-2）。"""
    cur = MagicMock()
    conn = _make_conn(cur)
    conn.commit.side_effect = RuntimeError("commit boom")
    with _patch_pg_conn(conn):
        with patch(
            "program_code.exchange_connectors.bybit_connector.control_api_v1.app.governance_lease_bridge.is_lease_ipc_enabled",
            return_value=True,
        ):
            ok = flush.flush_divergence_snapshot_once()
    assert ok is False


def test_flush_counter_read_exception_swallowed() -> None:
    """get_divergence_counters 拋例外 → flush 回 False，不傳播（G-2）。"""
    with patch(
        "program_code.exchange_connectors.bybit_connector.control_api_v1.app.governance_divergence.get_divergence_counters",
        side_effect=RuntimeError("counter boom"),
    ):
        ok = flush.flush_divergence_snapshot_once()
    assert ok is False


def test_flush_never_mutates_comparator_counter() -> None:
    """flush 純讀 counter，**絕不改 comparator 計數器**（投影是單向 read→write PG）。"""
    divergence.record_divergence(op="acquire", rust_outcome="granted", python_outcome="granted")
    before = divergence.get_divergence_counters()

    cur = MagicMock()
    conn = _make_conn(cur)
    with _patch_pg_conn(conn):
        with patch(
            "program_code.exchange_connectors.bybit_connector.control_api_v1.app.governance_lease_bridge.is_lease_ipc_enabled",
            return_value=True,
        ):
            flush.flush_divergence_snapshot_once()

    after = divergence.get_divergence_counters()
    assert before == after  # flush 不動 comparator counter


def test_record_divergence_still_works_during_flush_window() -> None:
    """flush 期間 comparator record_divergence 仍可並發運作（不持 comparator lock 過久）。

    驗證 flush 不在 comparator lock 內持有：在 flush 的 PG execute 期間呼叫
    record_divergence，若 flush 持鎖過久此呼叫會死鎖；正常運作證明 PG I/O 在鎖外。
    """
    cur = MagicMock()
    conn = _make_conn(cur)

    def _execute_side_effect(*_a: Any, **_k: Any) -> None:
        # 模擬 PG I/O 期間（flush 已釋放 comparator lock）comparator 仍可記錄。
        divergence.record_divergence(op="acquire", rust_outcome="granted", python_outcome="granted")

    cur.execute.side_effect = _execute_side_effect
    with _patch_pg_conn(conn):
        with patch(
            "program_code.exchange_connectors.bybit_connector.control_api_v1.app.governance_lease_bridge.is_lease_ipc_enabled",
            return_value=True,
        ):
            ok = flush.flush_divergence_snapshot_once()
    assert ok is True
    # 並發記錄的那筆已計入（證明 flush 期間 comparator 未被鎖死）。
    assert divergence.get_divergence_counters()["total"] == 1
