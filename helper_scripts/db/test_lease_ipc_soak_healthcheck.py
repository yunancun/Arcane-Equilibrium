#!/usr/bin/env python3
"""Unit tests for P5-SM-OPTION2 B-3 soak healthcheck `[81]`（rework (b)+(b-i)）。

P5-SM-OPTION2 B-3 soak healthcheck `[81]` 單元測試（rework (b)+(b-i)）。

**rework 背景（operator 拍板 (b)+(b-i)，2026-06-03）**：comparator 從硬 gate 降為觀測性
信號（Option 2 下歷史 replay vs contemporaneous comparator 語意不可達，見
`2026-06-03--p5_sm_soak_equiv_sampler_reconciliation.md`）。故：
  - healthcheck `[81]` gate（FAIL 條件）**只剩 P-LIVE**：lease_transitions 表存在 + 窗內
    有 row + fresh。任一不滿足 → FAIL（G-1 紀律對 P-LIVE 仍適用）。
  - comparator counter（total / divergences / snapshot freshness / flag_enabled）→ **觀測欄**
    （在 msg 報數值，**不再 FAIL**）。讀不到（V129 缺 / row 缺 / stale）→ 觀測欄缺值，
    照常 PASS（gate 由 P-LIVE 定）。

覆蓋：
  healthcheck `[81]` P-LIVE gate（G-1 fail-closed）：
    - P-LIVE：lease_transitions 表缺 → FAIL（Rust 權威路徑不可確認）。
    - P-LIVE：0 row → FAIL（Rust 權威路徑未 emit）。
    - P-LIVE：stale（age >= threshold）→ FAIL（Rust 權威路徑 silent-dead）。
    - 查詢例外 → fail-closed FAIL。
    - P-LIVE 健康 → PASS（msg 附 comparator 觀測欄）。
  healthcheck `[81]` comparator 觀測欄（**非 gate**，rework 核心斷言）：
    - divergences > 0：只要 P-LIVE 健康 → **PASS**（divergence 在觀測欄報數值，不 FAIL）。
    - V129 snapshot 表缺：P-LIVE 健康 → **PASS**（觀測欄報 unavailable，不 FAIL）。
    - snapshot row 缺：P-LIVE 健康 → **PASS**（觀測欄報 unavailable，不 FAIL）。
    - flag_enabled=false：P-LIVE 健康 → **PASS**（觀測欄報 flag=OFF，不 FAIL）。
    - snapshot stale：P-LIVE 健康 → **PASS**（觀測欄照報，不 FAIL）。
  EQUIV sampler：DEPRECATED（(b)+(b-i) 後已不接 gate，語意不可達）→ 測試 skip。

Mac dev / Linux runtime：
    cd "$OPENCLAW_BASE_DIR" && ./venvs/mac_dev/bin/python -m pytest \\
        helper_scripts/db/test_lease_ipc_soak_healthcheck.py -v
"""
from __future__ import annotations

import os
import sys
import unittest
from typing import Any
from unittest.mock import MagicMock

# srv root on sys.path（鏡像 test_lg5_healthchecks.py）。
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_HELPER_SCRIPTS_DIR = os.path.dirname(_THIS_DIR)
_SRV_ROOT = os.path.dirname(_HELPER_SCRIPTS_DIR)
sys.path.insert(0, _SRV_ROOT)

from helper_scripts.db.passive_wait_healthcheck.checks_governance_lease_ipc import (  # noqa: E402
    LIVE_TRANSITION_FRESHNESS_MAX_SECONDS,
    check_81_lease_ipc_soak,
)


def _cursor(fetches: list[Any]) -> MagicMock:
    """建 mock cursor：fetchone 依序回 fetches。"""
    cur = MagicMock()
    cur.connection = MagicMock()
    cur.connection.rollback = MagicMock()
    cur.fetchone.side_effect = fetches
    return cur


# fetch 序列順序（rework 後 check_81 的 SQL 呼叫順序）：
#   P-LIVE gate（先判）：
#     1. to_regclass(lease_transitions) IS NOT NULL
#     2. lease_transitions: (count, age_ms)
#   comparator 觀測欄（後讀，best-effort，不 gate；只在 P-LIVE 通過後才跑）：
#     3. to_regclass(snapshot) IS NOT NULL
#     4. snapshot row: (total, matches, divergences, flag_enabled, age_s)
# 視提前 return（P-LIVE FAIL）而定，觀測欄 fetch 不被消費。

# 便利常量：一組「P-LIVE 健康」的前兩筆 fetch（表在、count>0、age 5s fresh）。
_PLIVE_OK = [(True,), (12345, 5000)]
# 便利常量：一組「comparator 觀測欄完整」的後兩筆 fetch（snapshot 表在 + 一筆 row）。
def _observed(total: int, matches: int, divergences: int, flag: bool, age_s: int) -> list[Any]:
    return [(True,), (total, matches, divergences, flag, age_s)]


class TestCheck81PliveGate(unittest.TestCase):
    """[81] P-LIVE gate（G-1 fail-closed；rework 後唯一 FAIL 軸）。"""

    def test_plive_lease_transitions_missing_fail(self) -> None:
        cur = _cursor([(False,)])  # to_regclass(lease_transitions) → NULL
        status, msg = check_81_lease_ipc_soak(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("P-LIVE FAIL", msg)
        self.assertIn("lease_transitions missing", msg)

    def test_plive_zero_rows_fail(self) -> None:
        cur = _cursor([(True,), (0, 0)])  # 表在但 count=0
        status, msg = check_81_lease_ipc_soak(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("0 lease_transitions rows", msg)

    def test_plive_stale_fail(self) -> None:
        stale_ms = (LIVE_TRANSITION_FRESHNESS_MAX_SECONDS + 10) * 1000
        cur = _cursor([(True,), (12345, stale_ms)])  # count>0 but stale
        status, msg = check_81_lease_ipc_soak(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("silent-dead", msg)

    def test_plive_existence_query_exception_fail_closed(self) -> None:
        cur = MagicMock()
        cur.connection = MagicMock()
        cur.connection.rollback = MagicMock()
        cur.execute.side_effect = RuntimeError("pg boom")
        status, msg = check_81_lease_ipc_soak(cur)
        self.assertEqual(status, "FAIL")

    def test_plive_healthy_passes_with_observed(self) -> None:
        # P-LIVE 健康 + comparator 觀測欄完整（0 div）→ PASS，msg 含觀測欄。
        cur = _cursor(_PLIVE_OK + _observed(500, 500, 0, True, 10))
        status, msg = check_81_lease_ipc_soak(cur)
        self.assertEqual(status, "PASS")
        self.assertIn("soak healthy (P-LIVE gate)", msg)
        self.assertIn("lease_transitions count=12345", msg)
        # comparator 觀測欄（非 gate）出現在 msg。
        self.assertIn("observed[comparator non-gate]", msg)
        self.assertIn("divergences=0", msg)
        self.assertIn("flag=ON", msg)


class TestCheck81ComparatorNonGate(unittest.TestCase):
    """[81] comparator 觀測欄非 gate（rework (b)+(b-i) 核心斷言）。

    只要 P-LIVE 健康，comparator 的任何狀態（divergence>0 / 缺表 / 缺 row / flag-OFF /
    stale）都**不 FAIL**——它已降為觀測性信號，僅在 msg 報數值。
    """

    def test_divergences_positive_does_not_fail(self) -> None:
        # P-LIVE 健康 + comparator divergences=3 → 仍 PASS（divergence 在觀測欄報，不 gate）。
        cur = _cursor(_PLIVE_OK + _observed(500, 497, 3, True, 10))
        status, msg = check_81_lease_ipc_soak(cur)
        self.assertEqual(status, "PASS")
        self.assertIn("divergences=3", msg)  # 報數值供 triage

    def test_snapshot_table_missing_does_not_fail(self) -> None:
        # P-LIVE 健康 + V129 snapshot 表缺 → PASS（觀測欄報 unavailable，不 gate）。
        cur = _cursor(_PLIVE_OK + [(False,)])  # 觀測：snapshot 表缺
        status, msg = check_81_lease_ipc_soak(cur)
        self.assertEqual(status, "PASS")
        self.assertIn("unavailable", msg)
        self.assertIn("V129 snapshot table absent", msg)

    def test_snapshot_row_missing_does_not_fail(self) -> None:
        # P-LIVE 健康 + snapshot 表在但無 'singleton' row → PASS（觀測欄報 unavailable）。
        cur = _cursor(_PLIVE_OK + [(True,), None])
        status, msg = check_81_lease_ipc_soak(cur)
        self.assertEqual(status, "PASS")
        self.assertIn("no snapshot row", msg)

    def test_flag_off_does_not_fail(self) -> None:
        # P-LIVE 健康 + comparator flag_enabled=False → PASS（觀測欄報 flag=OFF，不 gate）。
        cur = _cursor(_PLIVE_OK + _observed(500, 500, 0, False, 10))
        status, msg = check_81_lease_ipc_soak(cur)
        self.assertEqual(status, "PASS")
        self.assertIn("flag=OFF", msg)

    def test_snapshot_stale_does_not_fail(self) -> None:
        # P-LIVE 健康 + comparator snapshot 很舊 → PASS（觀測欄照報 age，不 gate）。
        cur = _cursor(_PLIVE_OK + _observed(500, 500, 0, True, 99999))
        status, msg = check_81_lease_ipc_soak(cur)
        self.assertEqual(status, "PASS")
        self.assertIn("snapshot_age=99999s", msg)

    def test_observed_query_exception_does_not_fail(self) -> None:
        # P-LIVE 健康；comparator 觀測查詢拋例外 → PASS（觀測欄報 error，不 gate）。
        cur = MagicMock()
        cur.connection = MagicMock()
        cur.connection.rollback = MagicMock()
        # 前 2 次 fetch（P-LIVE）正常；第 3 次（觀測 existence）execute 拋例外。
        cur.fetchone.side_effect = [(True,), (12345, 5000)]

        call_state = {"n": 0}

        def _execute(*_a: Any, **_k: Any) -> None:
            call_state["n"] += 1
            # 第 3 個 execute = 觀測欄的 to_regclass(snapshot)，拋例外。
            if call_state["n"] >= 3:
                raise RuntimeError("observed boom")

        cur.execute.side_effect = _execute
        status, msg = check_81_lease_ipc_soak(cur)
        self.assertEqual(status, "PASS")
        self.assertIn("unavailable", msg)


@unittest.skip(
    "EQUIV sampler DEPRECATED — operator (b)+(b-i) 2026-06-03：Option 2 下歷史 replay vs "
    "contemporaneous comparator 語意不可達（E2 HIGH-2 + PA reconciliation），sampler 已從 "
    "soak gate 路徑移除、不接 production。保留檔案防重寫；不再對其行為斷言。"
)
class TestEquivSamplerDeprecated(unittest.TestCase):
    """EQUIV sampler 行為測試 —— 已 DEPRECATED（(b)+(b-i)），整類 skip。

    sampler（lease_ipc_equiv_sampler.py）在 Option 2 下語意不可達，已不接 gate（comparator
    降觀測性信號）。原本驗 classify_rust_outcome / replay_sample_through_comparator /
    fetch read-only 的測試對「已棄用、不接 production」的程式碼斷言無價值，整類 skip。
    sampler 檔案保留作歷史參照（含 HIGH-1/MEDIUM-1 已知缺陷，刻意不修）。
    """

    def test_deprecated_placeholder(self) -> None:
        # skip 由 class decorator 觸發；此 placeholder 僅讓 skip 有掛載點。
        self.fail("should be skipped (sampler deprecated)")


if __name__ == "__main__":
    unittest.main()
