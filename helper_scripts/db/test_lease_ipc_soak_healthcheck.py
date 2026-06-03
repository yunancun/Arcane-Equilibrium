#!/usr/bin/env python3
"""Unit tests for P5-SM-OPTION2 B-3 soak healthcheck `[81]` + EQUIV sampler.

P5-SM-OPTION2 B-3 soak healthcheck `[81]` + EQUIV sampler 單元測試。

覆蓋（G-1 fail-closed + sampler 真實樣本驅動）：
  healthcheck `[81]`:
    - V128 snapshot 表缺 → FAIL（投影層未部署不當綠燈）。
    - snapshot row 缺失 → FAIL（flusher 從沒寫）。
    - flag_enabled=false → FAIL（legacy local SM，comparator 不 fire）。
    - snapshot stale（age >= threshold）→ FAIL（flusher 死，R2 緩解；**G-1 核心**：
      stale 絕不當綠燈）。
    - divergences > 0 → FAIL（P-EQUIV gate；O-2 keep-as-gate）。
    - total < N → FAIL（樣本不足）。
    - P-LIVE：lease_transitions 缺 / 0 row / stale → FAIL。
    - 全 gate 滿足 → PASS。
  EQUIV sampler:
    - classify_rust_outcome 正規化（acquire_success/fail/bypass/非 acquire→None）。
    - replay 真實 rows 驅動 comparator（rust 來自 row，python 來自影子）。
    - 無 hub → 影子 UNKNOWN no-opinion（不偽造判定）。
    - read-only：fetch 只 SELECT，無 INSERT/UPDATE。

Mac dev / Linux runtime：
    cd "$OPENCLAW_BASE_DIR" && ./venvs/mac_dev/bin/python -m pytest \\
        helper_scripts/db/test_lease_ipc_soak_healthcheck.py -v
"""
from __future__ import annotations

import os
import sys
import unittest
from typing import Any, Optional
from unittest.mock import MagicMock

# srv root on sys.path（鏡像 test_lg5_healthchecks.py）。
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_HELPER_SCRIPTS_DIR = os.path.dirname(_THIS_DIR)
_SRV_ROOT = os.path.dirname(_HELPER_SCRIPTS_DIR)
sys.path.insert(0, _SRV_ROOT)

from helper_scripts.db.passive_wait_healthcheck.checks_governance_lease_ipc import (  # noqa: E402
    LIVE_TRANSITION_FRESHNESS_MAX_SECONDS,
    SNAPSHOT_FRESHNESS_MAX_SECONDS,
    SOAK_MIN_TOTAL,
    check_81_lease_ipc_soak,
)
from helper_scripts.db.lease_ipc_equiv_sampler import (  # noqa: E402
    classify_rust_outcome,
    fetch_recent_lease_transitions,
    replay_sample_through_comparator,
)


def _cursor(fetches: list[Any]) -> MagicMock:
    """建 mock cursor：fetchone 依序回 fetches。"""
    cur = MagicMock()
    cur.connection = MagicMock()
    cur.connection.rollback = MagicMock()
    cur.fetchone.side_effect = fetches
    return cur


# fetch 序列順序（healthcheck check_81 的 SQL 呼叫順序）：
#   1. to_regclass(snapshot) IS NOT NULL
#   2. snapshot row: (total, matches, divergences, flag_enabled, age_s)
#   3. to_regclass(lease_transitions) IS NOT NULL
#   4. lease_transitions: (count, age_ms)
# 視提前 return 而定，後續 fetch 不被消費。


class TestCheck81FailClosed(unittest.TestCase):
    """[81] G-1 fail-closed 各路徑。"""

    def test_snapshot_table_missing_fail(self) -> None:
        cur = _cursor([(False,)])  # to_regclass(snapshot) → NULL
        status, msg = check_81_lease_ipc_soak(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("V128 not applied", msg)

    def test_snapshot_row_missing_fail(self) -> None:
        cur = _cursor([(True,), None])  # 表在，但無 'singleton' row
        status, msg = check_81_lease_ipc_soak(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("no snapshot row", msg)

    def test_flag_off_fail(self) -> None:
        # 表在；row: total 充足、0 div、但 flag_enabled=False。
        cur = _cursor([(True,), (500, 500, 0, False, 10)])
        status, msg = check_81_lease_ipc_soak(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("flag_enabled=false", msg)

    def test_snapshot_stale_fail(self) -> None:
        # flag-ON、0 div、total 充足，但 snapshot age 超過 threshold（flusher 死）。
        stale_age = SNAPSHOT_FRESHNESS_MAX_SECONDS + 1
        cur = _cursor([(True,), (500, 500, 0, True, stale_age)])
        status, msg = check_81_lease_ipc_soak(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("stale", msg)

    def test_divergences_positive_fail(self) -> None:
        # flag-ON、fresh、total 充足，但 divergences=3 > 0。
        cur = _cursor([(True,), (500, 497, 3, True, 10)])
        status, msg = check_81_lease_ipc_soak(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("divergences=3", msg)

    def test_insufficient_total_fail(self) -> None:
        # flag-ON、fresh、0 div，但 total < N。
        low = SOAK_MIN_TOTAL - 1
        cur = _cursor([(True,), (low, low, 0, True, 10)])
        status, msg = check_81_lease_ipc_soak(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("insufficient sample", msg)

    def test_plive_lease_transitions_missing_fail(self) -> None:
        # P-EQUIV 全過，但 lease_transitions 表缺。
        cur = _cursor([
            (True,), (500, 500, 0, True, 10),  # P-EQUIV pass
            (False,),                           # lease_transitions 缺
        ])
        status, msg = check_81_lease_ipc_soak(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("P-LIVE FAIL", msg)
        self.assertIn("lease_transitions missing", msg)

    def test_plive_zero_rows_fail(self) -> None:
        cur = _cursor([
            (True,), (500, 500, 0, True, 10),  # P-EQUIV pass
            (True,),                            # lease_transitions 在
            (0, 0),                             # count=0
        ])
        status, msg = check_81_lease_ipc_soak(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("0 lease_transitions rows", msg)

    def test_plive_stale_fail(self) -> None:
        stale_ms = (LIVE_TRANSITION_FRESHNESS_MAX_SECONDS + 10) * 1000
        cur = _cursor([
            (True,), (500, 500, 0, True, 10),  # P-EQUIV pass
            (True,),                            # lease_transitions 在
            (12345, stale_ms),                  # count>0 but stale
        ])
        status, msg = check_81_lease_ipc_soak(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("silent-dead", msg)

    def test_all_gates_pass(self) -> None:
        cur = _cursor([
            (True,), (500, 500, 0, True, 10),   # P-EQUIV pass
            (True,),                             # lease_transitions 在
            (12345, 5000),                       # count>0, age 5s fresh
        ])
        status, msg = check_81_lease_ipc_soak(cur)
        self.assertEqual(status, "PASS")
        self.assertIn("soak healthy", msg)
        self.assertIn("divergences=0", msg)

    def test_query_exception_fail_closed(self) -> None:
        cur = MagicMock()
        cur.connection = MagicMock()
        cur.connection.rollback = MagicMock()
        cur.execute.side_effect = RuntimeError("pg boom")
        status, msg = check_81_lease_ipc_soak(cur)
        self.assertEqual(status, "FAIL")


class TestClassifyRustOutcome(unittest.TestCase):
    """EQUIV sampler：Rust event/to_state → OUTCOME 標籤正規化。"""

    def test_acquire_success_granted(self) -> None:
        self.assertEqual(classify_rust_outcome("lease_acquire_success", "ACTIVE"), "granted")

    def test_acquire_fail_denied(self) -> None:
        self.assertEqual(classify_rust_outcome("lease_acquire_fail", "REJECTED"), "denied")

    def test_bypass(self) -> None:
        self.assertEqual(classify_rust_outcome("lease_acquire_bypass", "BRIDGED"), "bypass")

    def test_non_acquire_event_none(self) -> None:
        # release / sm_transition / 中間態 → None（caller 跳過）。
        self.assertIsNone(classify_rust_outcome("lease_release_consumed", "CONSUMED"))
        self.assertIsNone(classify_rust_outcome("lease_sm_transition", "FROZEN"))


class TestReplaySampler(unittest.TestCase):
    """EQUIV sampler：真實 rows 驅動 comparator（dry-run 統計不污染 counter）。"""

    def test_dry_run_classifies_without_recording(self) -> None:
        rows = [
            {"lease_id": "l1", "event": "lease_acquire_success", "to_state": "ACTIVE",
             "profile": "Production", "engine_mode": "demo", "ts_ms": 1},
            {"lease_id": "l2", "event": "lease_release_consumed", "to_state": "CONSUMED",
             "profile": "Production", "engine_mode": "demo", "ts_ms": 2},
        ]
        # hub=None → python 影子 UNKNOWN → no-opinion（不偽造判定）。
        stats = replay_sample_through_comparator(rows, hub=None, dry_run=True)
        self.assertEqual(stats["sampled"], 2)
        self.assertEqual(stats["replayed"], 1)           # 只 acquire-outcome 那筆
        self.assertEqual(stats["skipped_non_acquire"], 1)  # release 那筆跳過
        self.assertEqual(stats["no_opinion"], 1)          # hub=None → UNKNOWN no-opinion

    def test_replay_drives_comparator_with_real_rows(self) -> None:
        """非 dry-run：真實 row 驅動 comparator record_divergence（rust 來自 row）。"""
        from program_code.exchange_connectors.bybit_connector.control_api_v1.app import (
            governance_divergence as divergence,
        )
        divergence.reset_divergence_state()

        # 一個 hub stub：影子永遠回 granted（模擬現役 Python SM 判定）。
        hub = MagicMock()
        hub._shadow_local_acquire_outcome.return_value = "granted"

        rows = [
            # rust granted vs python granted → match
            {"lease_id": "l1", "event": "lease_acquire_success", "to_state": "ACTIVE",
             "profile": "Production", "engine_mode": "demo", "ts_ms": 1},
            # rust denied vs python granted → divergence
            {"lease_id": "l2", "event": "lease_acquire_fail", "to_state": "REJECTED",
             "profile": "Production", "engine_mode": "demo", "ts_ms": 2},
        ]
        stats = replay_sample_through_comparator(rows, hub=hub, dry_run=False)
        self.assertEqual(stats["replayed"], 2)
        # comparator 真實計入（flusher 再投影到 PG）。
        counters = divergence.get_divergence_counters()
        self.assertEqual(counters["total"], 2)
        self.assertEqual(counters["divergences"], 1)  # l2 rust=denied vs python=granted
        self.assertEqual(counters["matches"], 1)      # l1 rust=granted vs python=granted
        divergence.reset_divergence_state()


class TestFetchReadOnly(unittest.TestCase):
    """EQUIV sampler：fetch 只 SELECT（read-only，無 INSERT/UPDATE/DELETE）。"""

    def test_fetch_emits_select_only(self) -> None:
        cur = MagicMock()
        cur.connection = MagicMock()
        cur.connection.rollback = MagicMock()
        cur.fetchall.return_value = [
            ("l1", "lease_acquire_success", "ACTIVE", "Production", "demo", 1),
        ]
        rows = fetch_recent_lease_transitions(cur, limit=10)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["lease_id"], "l1")
        # 驗 SQL 是 SELECT、含 shadow 過濾、無寫操作關鍵字。
        sql = cur.execute.call_args[0][0]
        self.assertIn("SELECT", sql)
        self.assertIn("FROM learning.lease_transitions", sql)
        self.assertIn("engine_mode <> 'shadow'", sql)
        upper = sql.upper()
        for forbidden in ("INSERT", "UPDATE ", "DELETE", "DROP", "ALTER"):
            self.assertNotIn(forbidden, upper)

    def test_fetch_query_failure_returns_empty(self) -> None:
        cur = MagicMock()
        cur.connection = MagicMock()
        cur.connection.rollback = MagicMock()
        cur.execute.side_effect = RuntimeError("pg boom")
        rows = fetch_recent_lease_transitions(cur, limit=10)
        self.assertEqual(rows, [])  # fail-soft


if __name__ == "__main__":
    unittest.main()
