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


# ═════════════════════════════════════════════════════════════════════════════
# P5-SM soak 第二輪（E1-B）：canary 投影 + V137 事件帳本
# ═════════════════════════════════════════════════════════════════════════════

from program_code.exchange_connectors.bybit_connector.control_api_v1.app import (  # noqa: E402
    governance_ipc_canary as canary_mod,
)


@pytest.fixture(autouse=True)
def _reset_soak_trackers() -> Any:
    """每個 test 前後重置 soak 事件 trackers + canary 計數器（測試隔離）。"""
    flush._reset_soak_event_trackers_for_tests()
    canary_mod.reset_canary_state_for_tests()
    yield
    flush._reset_soak_event_trackers_for_tests()
    canary_mod.reset_canary_state_for_tests()


def _patch_canary_counters(seq: list[dict[str, int]]):
    """patch canary get_canary_counters 依序回 seq（最後一個之後重複回尾值）。"""
    state = {"i": 0}

    def _fake() -> dict[str, int]:
        idx = min(state["i"], len(seq) - 1)
        state["i"] += 1
        return dict(seq[idx])

    return patch.object(canary_mod, "get_canary_counters", _fake)


def _patch_flag(value: Any):
    """patch lease-IPC flag 讀值（value 可為 bool 或 side_effect 例外）。"""
    kwargs: dict[str, Any] = (
        {"side_effect": value} if isinstance(value, Exception) else {"return_value": value}
    )
    return patch(
        "program_code.exchange_connectors.bybit_connector.control_api_v1.app."
        "governance_lease_bridge.is_lease_ipc_enabled",
        **kwargs,
    )


def _executed_sqls(cur: MagicMock) -> list[tuple[str, tuple]]:
    return [(c.args[0], c.args[1] if len(c.args) > 1 else ()) for c in cur.execute.call_args_list]


# ── flush_canary_snapshot_once ───────────────────────────────────────────────


def test_canary_flush_happy_path_upserts_key_canary() -> None:
    """canary flush UPSERT key='canary'，映射 total=attempts / matches=ok / divergences=fail。"""
    cur = MagicMock()
    conn = _make_conn(cur)
    counters = {"attempts": 7, "ok": 6, "fail": 1, "fail_streak_breaches": 0}
    with _patch_pg_conn(conn), _patch_canary_counters([counters]), _patch_flag(True):
        ok = flush.flush_canary_snapshot_once()
    assert ok is True
    sql, params = cur.execute.call_args[0]
    assert "INSERT INTO learning.lease_ipc_divergence_snapshot" in sql
    assert "ON CONFLICT (snapshot_key) DO UPDATE" in sql
    assert params[0] == "canary"
    assert params[1] == 7   # total = attempts
    assert params[2] == 6   # matches = ok
    assert params[3] == 1   # divergences = fail
    assert params[4] is True
    conn.commit.assert_called_once()


def test_canary_flush_pg_unavailable_fail_soft() -> None:
    """PG 不可用 → 回 False 不拋（fail-soft；canary 計數器不受影響）。"""
    with _patch_pg_conn(None), _patch_canary_counters([{"attempts": 1, "ok": 1, "fail": 0}]):
        with _patch_flag(True):
            assert flush.flush_canary_snapshot_once() is False


def test_canary_flush_execute_exception_swallowed() -> None:
    cur = MagicMock()
    cur.execute.side_effect = RuntimeError("pg boom")
    conn = _make_conn(cur)
    with _patch_pg_conn(conn), _patch_canary_counters([{"attempts": 1, "ok": 1, "fail": 0}]):
        with _patch_flag(True):
            assert flush.flush_canary_snapshot_once() is False


def test_canary_flush_never_mutates_canary_counters() -> None:
    """canary flush 純讀計數器（單向 read→write PG；投影不回寫）。"""
    asyncio_run_tick_counters_before = canary_mod.get_canary_counters()
    cur = MagicMock()
    conn = _make_conn(cur)
    with _patch_pg_conn(conn), _patch_flag(True):
        flush.flush_canary_snapshot_once()
    assert canary_mod.get_canary_counters() == asyncio_run_tick_counters_before


# ── record_epoch_start_events_once ───────────────────────────────────────────


def test_epoch_start_with_prev_rows_writes_rollover_and_start() -> None:
    """V129 有前 epoch row → epoch_rollover（prev_* + detail 時間戳/flag）+ flusher_start。"""
    cur = MagicMock()
    # SELECT 既有兩 row：(key, total, matches, divergences, updated_at_epoch_s, flag)
    cur.fetchall.return_value = [
        ("singleton", 100, 99, 1, 1760000000, True),
        ("canary", 500, 498, 2, 1760000010, True),
    ]
    conn = _make_conn(cur)
    with _patch_pg_conn(conn), _patch_flag(True):
        with _patch_canary_counters([{"attempts": 0, "ok": 0, "fail": 0, "fail_streak_breaches": 0}]):
            ok = flush.record_epoch_start_events_once()
    assert ok is True
    sqls = _executed_sqls(cur)
    # 第 1 個 execute = SELECT 前值；後續 = 事件 INSERT。
    insert_calls = [(s, p) for s, p in sqls if "INSERT INTO learning.lease_ipc_soak_events" in s]
    assert len(insert_calls) == 2
    rollover_params = insert_calls[0][1]
    assert rollover_params[0] == "epoch_rollover"
    assert rollover_params[2] == 100   # prev_total（singleton 終值）
    assert rollover_params[5] == 500   # prev_canary_attempts（canary 終值）
    import json as _json
    detail = _json.loads(rollover_params[8])
    assert detail["prev_singleton_updated_at_epoch_s"] == 1760000000
    assert detail["prev_canary_updated_at_epoch_s"] == 1760000010
    # 跨 restart OFF→ON 識別軸：rollover 必攜前一 epoch 的 flag 狀態。
    assert detail["prev_flag_enabled"] is True
    assert insert_calls[1][1][0] == "flusher_start"


def test_epoch_start_without_prev_rows_writes_start_only() -> None:
    """首次部署（V129 無 row）→ 只寫 flusher_start，無 epoch_rollover。"""
    cur = MagicMock()
    cur.fetchall.return_value = []
    conn = _make_conn(cur)
    with _patch_pg_conn(conn), _patch_flag(False):
        with _patch_canary_counters([{"attempts": 0, "ok": 0, "fail": 0, "fail_streak_breaches": 0}]):
            ok = flush.record_epoch_start_events_once()
    assert ok is True
    insert_calls = [
        (s, p) for s, p in _executed_sqls(cur)
        if "INSERT INTO learning.lease_ipc_soak_events" in s
    ]
    assert len(insert_calls) == 1
    assert insert_calls[0][1][0] == "flusher_start"


def test_epoch_start_records_only_once() -> None:
    """每 epoch 恰一次（第二次呼叫 no-op，不重複寫事件）。"""
    cur = MagicMock()
    cur.fetchall.return_value = []
    conn = _make_conn(cur)
    with _patch_pg_conn(conn), _patch_flag(True):
        with _patch_canary_counters([{"attempts": 0, "ok": 0, "fail": 0, "fail_streak_breaches": 0}]):
            flush.record_epoch_start_events_once()
            n_after_first = cur.execute.call_count
            flush.record_epoch_start_events_once()
    assert cur.execute.call_count == n_after_first  # 第二次 0 新 SQL


def test_epoch_start_v137_missing_fail_soft_no_raise() -> None:
    """V137 未 apply（INSERT 拋）→ fail-soft 回 False 不拋。"""
    cur = MagicMock()
    cur.fetchall.return_value = []

    def _execute(sql: str, *_a: Any) -> None:
        if "lease_ipc_soak_events" in sql:
            raise RuntimeError('relation "learning.lease_ipc_soak_events" does not exist')

    cur.execute.side_effect = _execute
    conn = _make_conn(cur)
    with _patch_pg_conn(conn), _patch_flag(True):
        with _patch_canary_counters([{"attempts": 0, "ok": 0, "fail": 0, "fail_streak_breaches": 0}]):
            assert flush.record_epoch_start_events_once() is False  # 不拋


# ── detect_and_record_soak_events_once ───────────────────────────────────────


def _detect_with(
    cur: MagicMock,
    flag_seq_value: Any,
    canary_seq: list[dict[str, int]],
) -> Any:
    conn = _make_conn(cur)
    with _patch_pg_conn(conn), _patch_flag(flag_seq_value), _patch_canary_counters(canary_seq):
        return flush.detect_and_record_soak_events_once()


def test_detect_first_observation_is_baseline_no_event() -> None:
    """首次觀測只記 baseline（無 flag_change 事件——沒有「前值」可比）。"""
    cur = MagicMock()
    _detect_with(cur, True, [{"attempts": 0, "ok": 0, "fail": 0, "fail_streak_breaches": 0}])
    inserts = [s for s, _ in _executed_sqls(cur) if "lease_ipc_soak_events" in s]
    assert inserts == []  # 無事件


def test_detect_flag_change_emits_event() -> None:
    """flag ON→OFF → flag_change 事件（S4 flag-OFF 觀測軸）。"""
    cur = MagicMock()
    counters = [{"attempts": 0, "ok": 0, "fail": 0, "fail_streak_breaches": 0}]
    conn = _make_conn(cur)
    with _patch_pg_conn(conn), _patch_canary_counters(counters * 2):
        with _patch_flag(True):
            flush.detect_and_record_soak_events_once()   # baseline = ON
        with _patch_flag(False):
            flush.detect_and_record_soak_events_once()   # ON→OFF
    insert_params = [
        p for s, p in _executed_sqls(cur) if "lease_ipc_soak_events" in s
    ]
    assert len(insert_params) == 1
    assert insert_params[0][0] == "flag_change"
    assert insert_params[0][1] is False  # 事件記錄 OFF 狀態
    import json as _json
    assert _json.loads(insert_params[0][8]) == {"from": True, "to": False}


def test_detect_canary_leader_start_once() -> None:
    """attempts 0→>0 → canary_leader_start 恰一次（後續增長不再發）。"""
    cur = MagicMock()
    seq = [
        {"attempts": 0, "ok": 0, "fail": 0, "fail_streak_breaches": 0},
        {"attempts": 3, "ok": 3, "fail": 0, "fail_streak_breaches": 0},
        {"attempts": 6, "ok": 6, "fail": 0, "fail_streak_breaches": 0},
    ]
    conn = _make_conn(cur)
    with _patch_pg_conn(conn), _patch_flag(True), _patch_canary_counters(seq):
        flush.detect_and_record_soak_events_once()
        flush.detect_and_record_soak_events_once()
        flush.detect_and_record_soak_events_once()
    starts = [
        p for s, p in _executed_sqls(cur)
        if "lease_ipc_soak_events" in s and p[0] == "canary_leader_start"
    ]
    assert len(starts) == 1


def test_detect_fail_streak_breach_increment_emits_event() -> None:
    """fail_streak_breaches 增量 → canary_fail_streak 事件（S3 連段證據）。"""
    cur = MagicMock()
    seq = [
        {"attempts": 10, "ok": 5, "fail": 5, "fail_streak_breaches": 0},
        {"attempts": 20, "ok": 5, "fail": 15, "fail_streak_breaches": 1},
    ]
    conn = _make_conn(cur)
    with _patch_pg_conn(conn), _patch_flag(True), _patch_canary_counters(seq):
        flush.detect_and_record_soak_events_once()  # baseline breaches=0
        flush.detect_and_record_soak_events_once()  # 0→1
    streaks = [
        p for s, p in _executed_sqls(cur)
        if "lease_ipc_soak_events" in s and p[0] == "canary_fail_streak"
    ]
    assert len(streaks) == 1
    import json as _json
    assert _json.loads(streaks[0][8])["breaches"] == 1


def test_detect_counter_regression_emits_event() -> None:
    """程內計數器倒退（單調不變式破壞）→ counter_regression 事件留痕。"""
    cur = MagicMock()
    seq = [
        {"attempts": 50, "ok": 50, "fail": 0, "fail_streak_breaches": 0},
        {"attempts": 3, "ok": 3, "fail": 0, "fail_streak_breaches": 0},  # 倒退
    ]
    conn = _make_conn(cur)
    with _patch_pg_conn(conn), _patch_flag(True), _patch_canary_counters(seq):
        flush.detect_and_record_soak_events_once()
        flush.detect_and_record_soak_events_once()
    regressions = [
        p for s, p in _executed_sqls(cur)
        if "lease_ipc_soak_events" in s and p[0] == "counter_regression"
    ]
    assert len(regressions) == 1
    import json as _json
    detail = _json.loads(regressions[0][8])
    assert detail["axis"] == "canary"
    assert detail["before"] == 50 and detail["after"] == 3


def test_detect_negative_monotonic_growth_no_regression_event() -> None:
    """負向（bite）：單調增長**不**發 counter_regression（偵測支路不誤殺正常路徑）。"""
    cur = MagicMock()
    seq = [
        {"attempts": 10, "ok": 10, "fail": 0, "fail_streak_breaches": 0},
        {"attempts": 20, "ok": 20, "fail": 0, "fail_streak_breaches": 0},
    ]
    conn = _make_conn(cur)
    with _patch_pg_conn(conn), _patch_flag(True), _patch_canary_counters(seq):
        flush.detect_and_record_soak_events_once()
        flush.detect_and_record_soak_events_once()
    regressions = [
        p for s, p in _executed_sqls(cur)
        if "lease_ipc_soak_events" in s and p[0] == "counter_regression"
    ]
    assert regressions == []


def test_detect_exception_fail_soft() -> None:
    """偵測層任何例外 → fail-soft 回 False 不拋（絕不影響權威路徑）。"""
    cur = MagicMock()
    cur.execute.side_effect = RuntimeError("pg boom")
    conn = _make_conn(cur)
    seq = [{"attempts": 5, "ok": 5, "fail": 0, "fail_streak_breaches": 0}]
    with _patch_pg_conn(conn), _patch_flag(True), _patch_canary_counters(seq):
        # attempts>0 會嘗試寫 canary_leader_start → INSERT 拋 → 吞噬回 False。
        assert flush.detect_and_record_soak_events_once() is False


# ── flush_observability_cycle_once ───────────────────────────────────────────


def test_cycle_runs_all_three_steps_independently() -> None:
    """單輪週期 = comparator 投影 + canary 投影 + 事件偵測；事件步失敗不阻斷投影。"""
    cur = MagicMock()

    def _execute(sql: str, *_a: Any) -> None:
        # 模擬 V137 未 apply：事件 INSERT 拋；V129 UPSERT 正常。
        if "lease_ipc_soak_events" in sql:
            raise RuntimeError("V137 not applied")

    cur.execute.side_effect = _execute
    conn = _make_conn(cur)
    seq = [{"attempts": 5, "ok": 5, "fail": 0, "fail_streak_breaches": 0}] * 4
    with _patch_pg_conn(conn), _patch_flag(True), _patch_canary_counters(seq):
        ok = flush.flush_observability_cycle_once()
    assert ok is False  # 事件步失敗 → 整體 False（測試斷言用）
    upserts = [
        p for s, p in _executed_sqls(cur)
        if "lease_ipc_divergence_snapshot" in s
    ]
    # 兩個 V129 投影（singleton + canary）都照常執行（步驟獨立）。
    keys = {p[0] for p in upserts}
    assert keys == {"singleton", "canary"}
