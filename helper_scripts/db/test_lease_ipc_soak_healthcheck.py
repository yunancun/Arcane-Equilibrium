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
    SOAK_CANARY_SNAPSHOT_STALE_SECONDS,
    check_81_lease_ipc_soak,
    check_82_lease_ipc_soak_window,
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


# ═════════════════════════════════════════════════════════════════════════════
# `[82]` lease_ipc_soak_window（P5-SM soak 第二輪 E1-D）
# ═════════════════════════════════════════════════════════════════════════════
#
# fetch 序列（check_82 的 SQL 呼叫順序）：
#   fetchone: 1. to_regclass(V129)  2. to_regclass(V137)  3. recent-72h count
#             4. now() epoch
#   fetchall: 1. V129 兩 row（key,total,matches,div,flag,age_s）
#             2. 14d 事件掃描（type,flag,canary_attempts,canary_ok,detail,epoch_s）
# 提前 return（PASS-skip / 整合性 FAIL）時後續 fetch 不被消費。
# 每個 FAIL 支路一條「只壞該條件」的合成 bite 測試 + PASS 雙生證明支路不誤殺。

_NOW = 1_760_000_000  # 合成「現在」epoch 秒（所有事件時間以此為基準）


def _cursor82(fetchones: list[Any], fetchalls: list[Any]) -> MagicMock:
    """建 [82] mock cursor：fetchone/fetchall 各依序回。"""
    cur = MagicMock()
    cur.connection = MagicMock()
    cur.connection.rollback = MagicMock()
    cur.fetchone.side_effect = fetchones
    cur.fetchall.side_effect = fetchalls
    return cur


def _snap(key: str, total: int, matches: int, div: int, flag: bool, age_s: int) -> tuple:
    return (key, total, matches, div, flag, age_s)


def _ev(
    ev_type: str,
    flag: bool,
    epoch_s: int,
    attempts: Any = None,
    ok: Any = None,
    detail: Any = None,
) -> tuple:
    return (ev_type, flag, attempts, ok, detail or {}, epoch_s)


def _hb(epoch_s: int, attempts: Any, ok: Any = None) -> tuple:
    """canary_heartbeat 事件（E2 HIGH-2）：flusher 30min 低頻攜 attempts 快照。"""
    return _ev(
        "canary_heartbeat", True, epoch_s, attempts,
        attempts if ok is None else ok, {"heartbeat_interval_s": 1800},
    )


def _healthy_inputs(
    *,
    canary_total: int = 1500,
    canary_ok: int = 1495,
    canary_age: int = 10,
    flag: bool = True,
    events: Any = None,
    now_epoch: int = _NOW,
) -> tuple[list[Any], list[Any]]:
    """一組「全健康」輸入（window 50h / probes 1500 / rate 0.9967）；caller 壞單一條件。

    默認事件含一條合規 heartbeat（E2 HIGH-2 後 10b 支路要求窗內有連續性證據：
    30min 前、attempts 略低於當前快照 → 嚴格增長成立、新鮮度成立）。caller 自帶
    events 時須自行附合規 heartbeat（除非測的支路在 10b 之前提前 return）。
    """
    snaps = [
        _snap("singleton", 100, 100, 0, flag, 10),
        _snap("canary", canary_total, canary_ok, canary_total - canary_ok, flag, canary_age),
    ]
    if events is None:
        events = [
            _ev("flusher_start", True, _NOW - 50 * 3600, 0, 0),
            _hb(_NOW - 1800, max(0, canary_total - 5), max(0, canary_ok - 5)),
        ]
    fetchones = [(True,), (True,), (1,), (now_epoch,)]
    fetchalls = [snaps, events]
    return fetchones, fetchalls


class TestCheck82SkipPaths(unittest.TestCase):
    """[82] PASS-skip：soak 非 active 不污染平時 cron。"""

    def test_v129_absent_skips(self) -> None:
        cur = _cursor82([(False,)], [])
        status, msg = check_82_lease_ipc_soak_window(cur)
        self.assertEqual(status, "PASS")
        self.assertIn("not active", msg)

    def test_flag_off_and_no_recent_events_skips(self) -> None:
        snaps = [_snap("singleton", 5, 5, 0, False, 10), _snap("canary", 5, 5, 0, False, 10)]
        cur = _cursor82([(True,), (True,), (0,)], [snaps])
        status, msg = check_82_lease_ipc_soak_window(cur)
        self.assertEqual(status, "PASS")
        self.assertIn("not active", msg)

    def test_no_rows_no_events_skips(self) -> None:
        cur = _cursor82([(True,), (True,), (0,)], [[]])
        status, msg = check_82_lease_ipc_soak_window(cur)
        self.assertEqual(status, "PASS")
        self.assertIn("not active", msg)


class TestCheck82IntegrityFailClosed(unittest.TestCase):
    """[82] active 下基建完整性 fail-closed（PA E2 重點 2 的四種「無假綠」情形）。"""

    def test_active_but_v137_missing_fails(self) -> None:
        snaps = [_snap("singleton", 5, 5, 0, True, 10)]
        cur = _cursor82([(True,), (False,)], [snaps])
        status, msg = check_82_lease_ipc_soak_window(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("V137 not applied", msg)

    def test_flag_currently_off_with_recent_events_fails(self) -> None:
        """flag-OFF 但近 72h 有事件 = soak 被中斷（S4 invalid，最 load-bearing 支路）。"""
        snaps = [_snap("singleton", 5, 5, 0, False, 10), _snap("canary", 9, 9, 0, False, 10)]
        cur = _cursor82([(True,), (True,), (5,)], [snaps])
        status, msg = check_82_lease_ipc_soak_window(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("flag currently OFF", msg)

    def test_no_canary_row_fails(self) -> None:
        snaps = [_snap("singleton", 5, 5, 0, True, 10)]
        cur = _cursor82([(True,), (True,), (1,)], [snaps])
        status, msg = check_82_lease_ipc_soak_window(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("no 'canary' snapshot row", msg)

    def test_flusher_dead_stale_canary_snapshot_fails(self) -> None:
        fo, fa = _healthy_inputs(canary_age=SOAK_CANARY_SNAPSHOT_STALE_SECONDS + 5)
        cur = _cursor82(fo, fa)
        status, msg = check_82_lease_ipc_soak_window(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("flusher dead", msg)

    def test_empty_event_ledger_fails(self) -> None:
        fo, fa = _healthy_inputs(events=[])
        cur = _cursor82(fo, fa)
        status, msg = check_82_lease_ipc_soak_window(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("0 soak events", msg)

    def test_canary_stalled_low_cumulative_attempts_fails(self) -> None:
        """canary 死（probe 數不增長）：窗 50h 僅 100 拍 < 保守下限 300。"""
        fo, fa = _healthy_inputs(canary_total=100, canary_ok=100)
        cur = _cursor82(fo, fa)
        status, msg = check_82_lease_ipc_soak_window(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("canary stalled", msg)


class TestCheck82S3Gates(unittest.TestCase):
    """[82] S3 數字 gate（窗 / probe / 成功率 / 連段）。"""

    def test_happy_path_passes_with_numbers(self) -> None:
        fo, fa = _healthy_inputs()
        cur = _cursor82(fo, fa)
        status, msg = check_82_lease_ipc_soak_window(cur)
        self.assertEqual(status, "PASS")
        self.assertIn("window=50.0h", msg)
        self.assertIn("probes=1500", msg)
        self.assertIn("success_rate=0.99", msg)

    def test_window_too_short_fails_accumulating(self) -> None:
        events = [
            _ev("flusher_start", True, _NOW - 10 * 3600, 0, 0),
            _hb(_NOW - 1800, 1490),  # 合規 heartbeat（10b 不搶答，讓窗軸自己咬）
        ]
        fo, fa = _healthy_inputs(events=events)
        cur = _cursor82(fo, fa)
        status, msg = check_82_lease_ipc_soak_window(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("window=10.0h", msg)
        self.assertIn("accumulating", msg)

    def test_probe_floor_not_met_fails(self) -> None:
        """probes=300 < 500（300 恰好不觸發停擺下限 → 精準咬 probe-floor 支路）。"""
        fo, fa = _healthy_inputs(canary_total=300, canary_ok=300)
        cur = _cursor82(fo, fa)
        status, msg = check_82_lease_ipc_soak_window(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("probes=300 < 500", msg)

    def test_success_rate_below_99_fails(self) -> None:
        fo, fa = _healthy_inputs(canary_total=2000, canary_ok=1900)
        cur = _cursor82(fo, fa)
        status, msg = check_82_lease_ipc_soak_window(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("success rate=0.9500", msg)

    def test_fail_streak_event_in_window_fails(self) -> None:
        events = [
            _ev("flusher_start", True, _NOW - 50 * 3600, 0, 0),
            _ev("canary_fail_streak", True, _NOW - 10 * 3600, 800, 700,
                {"breaches": 1}),
        ]
        fo, fa = _healthy_inputs(events=events)
        cur = _cursor82(fo, fa)
        status, msg = check_82_lease_ipc_soak_window(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("canary_fail_streak", msg)


class TestCheck82S4WindowValidity(unittest.TestCase):
    """[82] S4 窗有效性（flag-OFF / epoch 間隙 / counter regression）。"""

    def test_flag_off_observation_resets_anchor(self) -> None:
        """窗內 flag-OFF 觀測（**非** flag_change 事件）→ 錨點重置 → 窗縮短 → FAIL。

        bite 精準度（E1 第三棒 mutation 驗證補強）：OFF 觀測來自 canary_leader_start
        事件的 flag_enabled=False（模擬 flag_change INSERT 失敗被漏記、但其他事件
        帶到 OFF 狀態的真實情形），且**無** OFF→ON flag_change 補償事件——只有
        「任何事件的 flag-OFF 觀測」支路能擋住這個窗；移除該支路（mutation C）時
        本測試必紅（先前版本被 OFF→ON transition 支路遮蔽，mutation C 存活）。
        """
        events = [
            _ev("flusher_start", True, _NOW - 50 * 3600, 0, 0),
            # OFF 觀測：flag_change 寫入失敗（tracker 前移寧漏勿重），OFF 狀態僅由
            # 本事件的 flag_enabled=False 留痕；之後 flag 回 ON（V129 當前 flag=True）
            # 但無 transition 事件——belt-and-suspenders 支路必須單獨擋住。
            _ev("canary_leader_start", False, _NOW - 30 * 3600, 100, 100),
            _hb(_NOW - 1800, 1490),  # 合規 heartbeat（10b 不搶答）
        ]
        fo, fa = _healthy_inputs(events=events)
        cur = _cursor82(fo, fa)
        status, msg = check_82_lease_ipc_soak_window(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("flag-OFF observation", msg)  # 錨點重置原因 = OFF 觀測支路

    def test_flag_off_then_on_transition_resets_anchor(self) -> None:
        """同 epoch OFF→ON flag_change → 錨點重置在 transition（窗 30h <48h → FAIL）。"""
        events = [
            _ev("flusher_start", True, _NOW - 50 * 3600, 0, 0),
            _ev("flag_change", False, _NOW - 30 * 3600, 100, 100,
                {"from": True, "to": False}),
            _ev("flag_change", True, _NOW - 30 * 3600 + 60, 100, 100,
                {"from": False, "to": True}),
            _hb(_NOW - 1800, 1490),  # 合規 heartbeat（10b 不搶答）
        ]
        fo, fa = _healthy_inputs(events=events)
        cur = _cursor82(fo, fa)
        status, msg = check_82_lease_ipc_soak_window(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("flag OFF->ON transition", msg)  # 錨點重置原因可追溯

    def test_off_to_on_transition_at_49h_passes(self) -> None:
        """雙生 PASS：OFF→ON 在 49h 前 → 窗 49h ≥48h 照常 PASS（錨點不誤殺）。"""
        events = [
            _ev("flag_change", True, _NOW - 49 * 3600, 10, 10,
                {"from": False, "to": True}),
            _hb(_NOW - 1800, 1490),  # 合規 heartbeat（10b 支路滿足）
        ]
        fo, fa = _healthy_inputs(events=events)
        cur = _cursor82(fo, fa)
        status, msg = check_82_lease_ipc_soak_window(cur)
        self.assertEqual(status, "PASS")
        self.assertIn("window=49.0h", msg)

    def test_epoch_gap_over_30min_resets_anchor(self) -> None:
        """epoch 間隙 7200s > 1800s → 錨點重置在 rollover → 窗 20h → FAIL。"""
        rollover_ts = _NOW - 20 * 3600
        events = [
            _ev("flusher_start", True, _NOW - 50 * 3600, 0, 0),
            _ev("epoch_rollover", True, rollover_ts, 700, 698, {
                "prev_singleton_updated_at_epoch_s": rollover_ts - 7200,
                "prev_canary_updated_at_epoch_s": rollover_ts - 7200,
                "prev_flag_enabled": True,
            }),
            _hb(_NOW - 1800, 1490),  # 合規 heartbeat（10b 不搶答，讓間隙軸自己咬）
        ]
        fo, fa = _healthy_inputs(events=events)
        cur = _cursor82(fo, fa)
        status, msg = check_82_lease_ipc_soak_window(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("epoch gap", msg)

    def test_epoch_gap_within_30min_preserves_window_and_sums_across_epochs(self) -> None:
        """雙生 PASS + 跨 epoch 求和：間隙 60s → 窗保留；累計 = 當前 700 + 前值 800。"""
        rollover_ts = _NOW - 20 * 3600
        events = [
            _ev("flusher_start", True, _NOW - 50 * 3600, 0, 0),
            _ev("epoch_rollover", True, rollover_ts, 800, 795, {
                "prev_singleton_updated_at_epoch_s": rollover_ts - 60,
                "prev_canary_updated_at_epoch_s": rollover_ts - 60,
                "prev_flag_enabled": True,
            }),
            _hb(_NOW - 1800, 690),  # 本 epoch 合規 heartbeat（< 當前 total=700）
        ]
        fo, fa = _healthy_inputs(canary_total=700, canary_ok=698, events=events)
        cur = _cursor82(fo, fa)
        status, msg = check_82_lease_ipc_soak_window(cur)
        self.assertEqual(status, "PASS")
        self.assertIn("probes=1500", msg)  # 700 + 800 跨 epoch 求和

    def test_rollover_with_unknown_gap_resets_anchor_fail_closed(self) -> None:
        """rollover 無前 epoch 時間戳 → 間隙不可知 → fail-closed 重置錨點。"""
        events = [
            _ev("flusher_start", True, _NOW - 50 * 3600, 0, 0),
            _ev("epoch_rollover", True, _NOW - 20 * 3600, 700, 698,
                {"prev_flag_enabled": True}),
            _hb(_NOW - 1800, 1490),  # 合規 heartbeat（10b 不搶答）
        ]
        fo, fa = _healthy_inputs(events=events)
        cur = _cursor82(fo, fa)
        status, msg = check_82_lease_ipc_soak_window(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("unknown gap", msg)

    def test_cross_restart_off_to_on_resets_anchor(self) -> None:
        """跨 restart OFF→ON（rollover prev_flag_enabled=false）→ 錨點重置（防虛胖窗）。"""
        rollover_ts = _NOW - 20 * 3600
        events = [
            _ev("flusher_start", False, _NOW - 50 * 3600, 0, 0),
            _ev("epoch_rollover", True, rollover_ts, 0, 0, {
                "prev_singleton_updated_at_epoch_s": rollover_ts - 60,
                "prev_canary_updated_at_epoch_s": rollover_ts - 60,
                "prev_flag_enabled": False,
            }),
            _hb(_NOW - 1800, 1490),  # 合規 heartbeat（10b 不搶答）
        ]
        fo, fa = _healthy_inputs(events=events)
        cur = _cursor82(fo, fa)
        status, msg = check_82_lease_ipc_soak_window(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("cross-restart flag OFF->ON", msg)

    def test_counter_regression_event_in_window_fails(self) -> None:
        events = [
            _ev("flusher_start", True, _NOW - 50 * 3600, 0, 0),
            _ev("counter_regression", True, _NOW - 5 * 3600, 100, 100,
                {"axis": "canary", "before": 500, "after": 100}),
        ]
        fo, fa = _healthy_inputs(events=events)
        cur = _cursor82(fo, fa)
        status, msg = check_82_lease_ipc_soak_window(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("counter_regression", msg)

    def test_stateless_regression_without_rollover_fails(self) -> None:
        """無狀態交叉偵測：窗內事件快照 attempts=5000 > 當前 total=1500 且無 rollover。"""
        events = [
            _ev("flusher_start", True, _NOW - 50 * 3600, 0, 0),
            _ev("canary_leader_start", True, _NOW - 3600, 5000, 4990),
        ]
        fo, fa = _healthy_inputs(events=events)  # canary_total=1500
        cur = _cursor82(fo, fa)
        status, msg = check_82_lease_ipc_soak_window(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("regression without epoch_rollover", msg)

    def test_query_exception_fail_closed(self) -> None:
        """任何查詢例外 → fail-closed FAIL（讀不到絕不當綠燈）。"""
        cur = MagicMock()
        cur.connection = MagicMock()
        cur.connection.rollback = MagicMock()
        cur.execute.side_effect = RuntimeError("pg boom")
        status, msg = check_82_lease_ipc_soak_window(cur)
        self.assertEqual(status, "FAIL")


class TestCheck82DupRolloverDedup(unittest.TestCase):
    """[82] E2 HIGH-1 regression：crash-loop 重複 epoch_rollover 去重（Probe A）。

    epoch 存活 <30s（死於首次 flush 前）時，下一 epoch 的 rollover 重讀**未刷新**
    的 V129 → 攜帶與前一 rollover 完全相同的 prev 終值。修復前跨 epoch 求和全數
    疊加 → 成功率稀釋假綠；修復後同一底層快照（同 prev_canary_updated_at_epoch_s
    + 同 prev 計數）只計一次。
    """

    def test_probe_a_dup_rollover_dilution_fails(self) -> None:
        """E2 Probe A 縮減版：30 個 crash-loop rollover 攜同一 V129 終值（800/795）
        + 劣化當前 epoch（60 attempts / 20 ok，散發失敗無連段）。

        修復前：30 份疊加 → 24060/23870 = 0.9921 ≥ 0.99 → 假 PASS（本測試紅）；
        修復後：dedup 帳 = 860/815 = 0.9477 < 0.99 → S3 成功率 FAIL。
        """
        v129_updated = _NOW - 49 * 3600  # epoch1 終值 updated_at（全部 dup 共享）
        events = [_ev("flusher_start", True, _NOW - 50 * 3600, 0, 0)]
        for i in range(30):
            # 10 分鐘內 30 次 crash-loop restart（各 epoch <30s，間隙 20s ≤30min
            # 不觸發錨點重置——窗保留，正是稀釋假綠成立的前提）。
            events.append(_ev("epoch_rollover", True, _NOW - 49 * 3600 + i * 20, 800, 795, {
                "prev_singleton_updated_at_epoch_s": v129_updated,
                "prev_canary_updated_at_epoch_s": v129_updated,
                "prev_flag_enabled": True,
            }))
        events.append(_hb(_NOW - 1800, 50))  # 合規 heartbeat（10b 不搶答）
        fo, fa = _healthy_inputs(canary_total=60, canary_ok=20, events=events)
        cur = _cursor82(fo, fa)
        status, msg = check_82_lease_ipc_soak_window(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("success rate=0.9477", msg)
        self.assertIn("cum_attempts=860", msg)  # dedup 後帳（非 24060）

    def test_identical_prev_counted_once_distinct_prev_still_counted(self) -> None:
        """精確算術雙生：identical-prev pair 計一次、distinct-prev 照計。

        rollover A(prev 300/299) + B(=A 完全重複) + C(prev 500/496，不同快照)
        + 當前 epoch 700/698 → probes = 700+300+500 = 1500（非 1800 過度疊加、
        非 1200 過度去重）→ PASS。
        """
        base_ts = _NOW - 20 * 3600
        shared_detail = {
            "prev_singleton_updated_at_epoch_s": base_ts - 60,
            "prev_canary_updated_at_epoch_s": base_ts - 60,
            "prev_flag_enabled": True,
        }
        events = [
            _ev("flusher_start", True, _NOW - 50 * 3600, 0, 0),
            _ev("epoch_rollover", True, base_ts, 300, 299, dict(shared_detail)),
            _ev("epoch_rollover", True, base_ts + 20, 300, 299, dict(shared_detail)),
            _ev("epoch_rollover", True, base_ts + 40, 500, 496, {
                "prev_singleton_updated_at_epoch_s": base_ts + 30,
                "prev_canary_updated_at_epoch_s": base_ts + 30,
                "prev_flag_enabled": True,
            }),
            _hb(_NOW - 1800, 690),  # 本 epoch 合規 heartbeat（< 當前 total=700）
        ]
        fo, fa = _healthy_inputs(canary_total=700, canary_ok=698, events=events)
        cur = _cursor82(fo, fa)
        status, msg = check_82_lease_ipc_soak_window(cur)
        self.assertEqual(status, "PASS")
        self.assertIn("probes=1500", msg)


class TestCheck82HeartbeatContinuity(unittest.TestCase):
    """[82] E2 HIGH-2 regression：canary 中段死亡偵測（heartbeat 連續性支路 10b）。

    flusher 每 30min 寫 canary_heartbeat（攜 attempts 快照）；本支路斷言
    (i) 窗 ≥1h 必須有 heartbeat、(ii) 最新 heartbeat ≤1h、(iii) 同 epoch 相鄰
    heartbeat 嚴格增長、(iv) 最後 heartbeat（>600s 寬限）→ 當前快照嚴格增長。
    """

    def test_probe_d_midwindow_death_flat_heartbeats_fails(self) -> None:
        """E2 Probe D：17h 攢 510 拍（@120s）後 canary 死 31h；flusher 持續 flush
        （V129 fresh、0 失敗、無連段、窗 48h、510 ≥ 500 floor）。

        修復前：全軸不咬 → 假 PASS rate=1.0000（本測試紅）；
        修復後：死亡後相鄰 heartbeat attempts 持平（510 -> 510）→ 連續性 FAIL。
        """
        start = _NOW - 48 * 3600 - 60
        events = [_ev("flusher_start", True, start, 0, 0)]
        # 存活期 17h：每 30min 一條 heartbeat，attempts 嚴格增長至 510（~15 拍/30min）。
        for k in range(1, 35):
            events.append(_hb(start + k * 1800, min(510, k * 15)))
        # 死亡期 31h：flusher 活著照發 heartbeat，但 attempts 凍結在 510。
        for k in range(35, 97):
            events.append(_hb(start + k * 1800, 510))
        fo, fa = _healthy_inputs(canary_total=510, canary_ok=510, events=events)
        cur = _cursor82(fo, fa)
        status, msg = check_82_lease_ipc_soak_window(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("did not grow between adjacent heartbeats", msg)

    def test_heartbeat_chain_stopped_midwindow_fails(self) -> None:
        """heartbeat 證據鏈中途停擺（最新一條 5h 前）→ 新鮮度 FAIL。

        否則「heartbeat 在 17h 停發、canary 30h 才死」會讓 HIGH-2 換個位置復發
        （快照增長軸 vs 最後一條舊 heartbeat 仍會假綠）。
        """
        start = _NOW - 50 * 3600
        events = [_ev("flusher_start", True, start, 0, 0)]
        for k in range(1, 10):
            events.append(_hb(start + k * 1800, k * 15)) # 早期正常增長
        events.append(_hb(_NOW - 5 * 3600, 600))  # 最後一條在 5h 前，之後全黑
        fo, fa = _healthy_inputs(canary_total=1500, canary_ok=1500, events=events)
        cur = _cursor82(fo, fa)
        status, msg = check_82_lease_ipc_soak_window(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("newest canary_heartbeat age=", msg)

    def test_no_heartbeats_in_long_window_fails(self) -> None:
        """窗 ≥1h 但 0 條 heartbeat → 連續性不可證 → fail-closed FAIL
        （事件路徑死或部署不含 heartbeat 機制，canary 中段死亡將不可見）。"""
        events = [_ev("flusher_start", True, _NOW - 50 * 3600, 0, 0)]
        fo, fa = _healthy_inputs(events=events)
        cur = _cursor82(fo, fa)
        status, msg = check_82_lease_ipc_soak_window(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("0 canary_heartbeat events", msg)

    def test_no_growth_since_last_heartbeat_fails(self) -> None:
        """尾段死亡：相鄰 heartbeat 全增長，但最後一條（1800s 前 > 600s 寬限）後
        當前快照無增長 → (iv) FAIL。"""
        events = [
            _ev("flusher_start", True, _NOW - 50 * 3600, 0, 0),
            _hb(_NOW - 7200, 1460),
            _hb(_NOW - 5400, 1475),
            _hb(_NOW - 3600, 1490),
            _hb(_NOW - 1800, 1500),  # 最後一條後 canary 死：當前快照仍 1500
        ]
        fo, fa = _healthy_inputs(canary_total=1500, canary_ok=1500, events=events)
        cur = _cursor82(fo, fa)
        status, msg = check_82_lease_ipc_soak_window(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("window tail", msg)

    def test_recent_heartbeat_within_grace_no_false_tail_fail(self) -> None:
        """雙生 PASS：最後 heartbeat 300s 前（<600s 寬限）、當前快照同值 →
        不誤殺（120s cadence 下 300s 內零增長完全合法）。"""
        events = [
            _ev("flusher_start", True, _NOW - 50 * 3600, 0, 0),
            _hb(_NOW - 2100, 1490),
            _hb(_NOW - 300, 1500),
        ]
        fo, fa = _healthy_inputs(canary_total=1500, canary_ok=1500, events=events)
        cur = _cursor82(fo, fa)
        status, msg = check_82_lease_ipc_soak_window(cur)
        self.assertEqual(status, "PASS")

    def test_cross_epoch_heartbeat_drop_not_false_positive(self) -> None:
        """雙生 PASS：epoch_rollover 後計數器歸零，heartbeat 800→30 是合法回落
        （比較基線在 rollover 重置，不誤判死亡）；跨 epoch 求和照常。"""
        rollover_ts = _NOW - 20 * 3600
        events = [
            _ev("flusher_start", True, _NOW - 50 * 3600, 0, 0),
            _hb(rollover_ts - 3600, 790),
            _hb(rollover_ts - 1800, 800),
            _ev("epoch_rollover", True, rollover_ts, 800, 795, {
                "prev_singleton_updated_at_epoch_s": rollover_ts - 60,
                "prev_canary_updated_at_epoch_s": rollover_ts - 60,
                "prev_flag_enabled": True,
            }),
            _hb(rollover_ts + 1800, 30),   # 新 epoch 從低值重新累積
            _hb(_NOW - 1800, 690),
        ]
        fo, fa = _healthy_inputs(canary_total=700, canary_ok=698, events=events)
        cur = _cursor82(fo, fa)
        status, msg = check_82_lease_ipc_soak_window(cur)
        self.assertEqual(status, "PASS")
        self.assertIn("probes=1500", msg)  # 700 + 800（跨 epoch 求和不受影響）

    def test_heartbeat_without_attempts_snapshot_fails_closed(self) -> None:
        """heartbeat 攜 None attempts（計數讀取失敗）→ 增長不可證 → fail-closed。"""
        events = [
            _ev("flusher_start", True, _NOW - 50 * 3600, 0, 0),
            _hb(_NOW - 1800, None),
        ]
        fo, fa = _healthy_inputs(events=events)
        cur = _cursor82(fo, fa)
        status, msg = check_82_lease_ipc_soak_window(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("carries no attempts snapshot", msg)


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
