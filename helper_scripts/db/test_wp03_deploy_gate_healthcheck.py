#!/usr/bin/env python3
"""Unit tests for passive_wait_healthcheck ``[69]`` wp03_ou_sigma_deploy_gate
(P1-WP03-DEPLOY-GATE-IMPL，2026-05-16 PA spec
``docs/execution_plan/2026-05-16--wp03_ou_sigma_deploy_gate_spec.md``)。

對應 WP-03 OU sigma residual fix (commit ``ef6ea79f`` / v35 rebuild
``2026-05-16T01:00:00Z`` engine PID 69581) 部署後 24h+ monitoring。
test fixture 涵蓋 PASS / WARN / FAIL + 邊界：
  PASS = 三窗在 baseline 容差內，無 trigger
  WARN = 任一窗接近 trigger（80% threshold approach）
  FAIL = T1/T2/T3/ZERO_FILLS 任一 trigger 觸發 → 寫 revert flag
  Edge case：pre-deploy / pre-evaluable / table absent / baseline insufficient /
             query failure / REQUIRED env / ENGINE_MODE 排除 paper+live
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_HELPER_SCRIPTS_DIR = os.path.dirname(_THIS_DIR)
_SRV_ROOT = os.path.dirname(_HELPER_SCRIPTS_DIR)
sys.path.insert(0, _SRV_ROOT)

from helper_scripts.db.passive_wait_healthcheck.checks_wp03_deploy_gate import (  # noqa: E402
    WP03_DEPLOY_TIMESTAMP_UTC,
    check_69_wp03_ou_sigma_deploy_gate,
)


def _mock_cursor(
    fetchone_rows: list,
) -> MagicMock:
    """構造 mock cursor，fetchone 依序回 list[i]。

    cursor.connection.rollback 是 no-op；execute 不引發；fetchall 不會被叫
    （本 check 全 fetchone，無 fetchall）。
    """
    cur = MagicMock()
    cur.connection = MagicMock()
    cur.connection.rollback = MagicMock()
    cur.fetchone.side_effect = fetchone_rows
    return cur


def _write_engine_pid(data_dir: Path, mtime_iso: str | None = None) -> Path:
    """寫 mock engine_pid 檔，可指定 mtime 模擬 deploy 時間。

    mtime_iso=None 默認用 WP-03 deploy + 2h（讓 deploy proxy 過 PRE_EVALUABLE）。
    """
    pid_path = data_dir / "engine_pid"
    pid_path.write_text("12345", encoding="utf-8")
    if mtime_iso is not None:
        import datetime as _dt

        dt = _dt.datetime.fromisoformat(mtime_iso.replace("Z", "+00:00"))
        ts = dt.timestamp()
        os.utime(pid_path, (ts, ts))
    else:
        # 預設 mtime = 現在（modelling current run；engine 啟動很久前）
        # 但要保證 > WP-03 deploy ts，且 age > PRE_EVALUABLE_AGE_HOURS (1h)
        # 用「兩小時前」作 mtime（即 engine 已 run 2h，sample 累積中）
        now_ts = time.time()
        two_h_ago = now_ts - 2 * 3600
        os.utime(pid_path, (two_h_ago, two_h_ago))
    return pid_path


def _baseline_query_result(n: int, avg: float | None, std: float | None = None) -> tuple:
    """構造 baseline _query helper PG return row（n, avg, std）。"""
    return (n, avg, std)


def _table_exists_row() -> tuple:
    """``SELECT to_regclass IS NOT NULL`` return row。"""
    return (True,)


class TestWP03DeployGateHealthcheck(unittest.TestCase):
    """[69] check_69_wp03_ou_sigma_deploy_gate — PASS/WARN/FAIL + edge cases。"""

    def setUp(self) -> None:
        """保存 env + 構造 tmp data_dir 模擬 engine_pid + revert flag persist。"""
        self._old_env = dict(os.environ)
        self._tmp_data = tempfile.TemporaryDirectory()
        os.environ["OPENCLAW_DATA_DIR"] = self._tmp_data.name
        # 清理 env 可能殘留的 opt-in flag
        os.environ.pop("OPENCLAW_WP03_DEPLOY_GATE_REQUIRED", None)
        os.environ.pop("OPENCLAW_WP03_DEPLOY_GATE_LOOKBACK_HOURS", None)

    def tearDown(self) -> None:
        """還原 env + 清理 tmp dir。"""
        os.environ.clear()
        os.environ.update(self._old_env)
        self._tmp_data.cleanup()

    # ============================================================
    # Edge case 1：pre-deploy（engine_pid 不存）→ PASS-skip
    # ============================================================

    def test_pre_deploy_no_engine_pid(self) -> None:
        """engine_pid 不存 → PASS（gate skipped），不查 DB。"""
        cur = _mock_cursor([])  # 無 DB call

        status, msg = check_69_wp03_ou_sigma_deploy_gate(cur)

        self.assertEqual(status, "PASS")
        self.assertIn("engine_pid 不存在", msg)
        self.assertIn("gate skipped", msg)

    # ============================================================
    # Edge case 2：engine_pid mtime < WP-03 deploy ts → PASS（stale deploy）
    # ============================================================

    def test_stale_engine_pid_before_deploy(self) -> None:
        """engine restart 在 WP-03 deploy 前 → PASS（gate not active yet）。"""
        # mtime 設為 2026-05-15（WP-03 deploy 是 2026-05-16T01:00:00Z）
        _write_engine_pid(Path(self._tmp_data.name), mtime_iso="2026-05-15T00:00:00Z")
        cur = _mock_cursor([])

        status, msg = check_69_wp03_ou_sigma_deploy_gate(cur)

        self.assertEqual(status, "PASS")
        self.assertIn("engine restart 在 WP-03 deploy 前", msg)
        self.assertIn("gate not active", msg)

    # ============================================================
    # Edge case 3：deploy_age < 1h → PASS（pre-evaluable）
    # ============================================================

    def test_pre_evaluable_recent_deploy(self) -> None:
        """deploy_age < 1.0h → PASS（sample 累積中，三窗尚不可評估）。"""
        import datetime as _dt

        # 設 mtime = 現在 - 30min；但須 > WP-03 deploy ts
        now = _dt.datetime.now(tz=_dt.timezone.utc)
        thirty_min_ago = now - _dt.timedelta(minutes=30)
        # 確保 > deploy_ts，否則先撞 stale path
        deploy_ts = _dt.datetime.fromisoformat(WP03_DEPLOY_TIMESTAMP_UTC.replace("Z", "+00:00"))
        if thirty_min_ago < deploy_ts:
            self.skipTest(
                "system clock predates WP-03 deploy_ts; pre-evaluable path "
                "needs now > deploy_ts but with age < 1h"
            )
        _write_engine_pid(
            Path(self._tmp_data.name),
            mtime_iso=thirty_min_ago.isoformat().replace("+00:00", "Z"),
        )
        cur = _mock_cursor([])

        status, msg = check_69_wp03_ou_sigma_deploy_gate(cur)

        self.assertEqual(status, "PASS")
        self.assertIn("sample 累積中", msg)

    # ============================================================
    # Edge case 4：table absent（V031 not applied）→ WARN
    # ============================================================

    def test_table_absent_warn(self) -> None:
        """learning.mlde_edge_training_rows 表缺 → WARN。"""
        _write_engine_pid(Path(self._tmp_data.name))
        # fetchone 序列：to_regclass IS NOT NULL → False
        cur = _mock_cursor([(False,)])

        status, msg = check_69_wp03_ou_sigma_deploy_gate(cur)

        self.assertEqual(status, "WARN")
        self.assertIn("learning.mlde_edge_training_rows missing", msg)

    # ============================================================
    # Edge case 5：baseline 樣本不足（pre-V083 historical 期間）→ WARN
    # ============================================================

    def test_baseline_insufficient_sample_warn(self) -> None:
        """baseline window 樣本 n < 30 → WARN cannot evaluate T3 drift。"""
        _write_engine_pid(Path(self._tmp_data.name))
        # fetchone 序列：
        #  1. to_regclass True
        #  2. baseline query: n=10 < 30 → WARN
        cur = _mock_cursor([
            _table_exists_row(),
            _baseline_query_result(10, 5.0),
        ])

        status, msg = check_69_wp03_ou_sigma_deploy_gate(cur)

        self.assertEqual(status, "WARN")
        self.assertIn("baseline compute failed", msg)
        self.assertIn("樣本不足", msg)

    # ============================================================
    # PASS fixture：三窗全在 baseline 容差內
    # ============================================================

    def test_pass_all_windows_within_tolerance(self) -> None:
        """PASS：12h/24h/7d 全在 baseline 容差內，無 trigger。"""
        _write_engine_pid(Path(self._tmp_data.name))
        # fetchone 序列：
        #  1. to_regclass True
        #  2. baseline: n=500, avg=+8.0, std=12
        #  3. T1 12h: n=80, avg=+5.0 (> -10 trigger, 也 > -8 approach)
        #  4. T2 24h: n=200, avg=+6.0 (> -5 trigger, 也 > -4 approach)
        #  5. T3 7d : n=500, avg=+7.0 (> baseline-3=5, 也 > baseline-2.4=5.6)
        cur = _mock_cursor([
            _table_exists_row(),
            _baseline_query_result(500, 8.0, 12.0),
            _baseline_query_result(80, 5.0, 10.0),  # T1
            _baseline_query_result(200, 6.0, 10.0),  # T2
            _baseline_query_result(500, 7.0, 10.0),  # T3
        ])

        status, msg = check_69_wp03_ou_sigma_deploy_gate(cur)

        self.assertEqual(status, "PASS", msg)
        self.assertIn("within tolerance", msg)
        self.assertIn("12h n=80", msg)
        self.assertIn("baseline_14d=8.00bps", msg)

    # ============================================================
    # FAIL T1：12h avg < -10 bps + n >= 30 → CRITICAL revert flag
    # ============================================================

    def test_fail_t1_critical(self) -> None:
        """T1 fast-fail：12h avg=-12 bps + n=50 → FAIL + revert flag。"""
        _write_engine_pid(Path(self._tmp_data.name))
        # fetchone 序列：
        #  1. to_regclass True
        #  2. baseline: n=500, avg=+8.0
        #  3. T1 12h: n=50, avg=-12 (< -10 → trigger)
        #  4. T2 24h: n=200, avg=-3 (> -5)
        #  5. T3 7d : n=500, avg=+7
        cur = _mock_cursor([
            _table_exists_row(),
            _baseline_query_result(500, 8.0, 12.0),
            _baseline_query_result(50, -12.0, 10.0),  # T1 trigger
            _baseline_query_result(200, -3.0, 10.0),
            _baseline_query_result(500, 7.0, 10.0),
        ])

        status, msg = check_69_wp03_ou_sigma_deploy_gate(cur)

        self.assertEqual(status, "FAIL", msg)
        self.assertIn("WP-03 deploy-gate FAIL", msg)
        self.assertIn("revert_recommended=true", msg)
        self.assertIn("T1_CRITICAL", msg)
        # Revert flag 應寫入磁碟
        flag_path = Path(self._tmp_data.name) / "wp03_revert_flag"
        self.assertTrue(flag_path.exists(), "revert flag must be written")
        flag_data = json.loads(flag_path.read_text())
        self.assertEqual(flag_data["severity"], "T1_CRITICAL")
        self.assertEqual(flag_data["wp03_commit"], "ef6ea79f")

    # ============================================================
    # FAIL T2：24h avg < -5 bps + n >= 50 → HIGH revert flag
    # ============================================================

    def test_fail_t2_high(self) -> None:
        """T2 primary：24h avg=-6 bps + n=100 → FAIL T2_HIGH + flag。"""
        _write_engine_pid(Path(self._tmp_data.name))
        cur = _mock_cursor([
            _table_exists_row(),
            _baseline_query_result(500, 8.0, 12.0),
            _baseline_query_result(40, -3.0, 10.0),  # T1 n<floor & avg=-3 > -10
            _baseline_query_result(100, -6.0, 10.0),  # T2 trigger
            _baseline_query_result(500, 6.0, 10.0),  # T3
        ])

        status, msg = check_69_wp03_ou_sigma_deploy_gate(cur)

        self.assertEqual(status, "FAIL", msg)
        self.assertIn("T2_HIGH", msg)
        self.assertIn("24h n=100", msg)
        flag_path = Path(self._tmp_data.name) / "wp03_revert_flag"
        self.assertTrue(flag_path.exists())
        flag_data = json.loads(flag_path.read_text())
        self.assertEqual(flag_data["severity"], "T2_HIGH")

    # ============================================================
    # FAIL T3：7d cumulative drift < baseline - 3 bps → MEDIUM revert flag
    # ============================================================

    def test_fail_t3_cumulative_drift(self) -> None:
        """T3 cumulative：7d avg=+4 bps < baseline (8) - 3 = 5 → FAIL T3_MEDIUM。"""
        _write_engine_pid(Path(self._tmp_data.name))
        cur = _mock_cursor([
            _table_exists_row(),
            _baseline_query_result(500, 8.0, 12.0),
            _baseline_query_result(80, 5.0, 10.0),  # T1 fine
            _baseline_query_result(200, 6.0, 10.0),  # T2 fine
            _baseline_query_result(500, 4.0, 10.0),  # T3 trigger (< 8-3=5)
        ])

        status, msg = check_69_wp03_ou_sigma_deploy_gate(cur)

        self.assertEqual(status, "FAIL", msg)
        self.assertIn("T3_MEDIUM", msg)
        self.assertIn("drift > 3.0bps below baseline", msg)
        flag_path = Path(self._tmp_data.name) / "wp03_revert_flag"
        self.assertTrue(flag_path.exists())
        flag_data = json.loads(flag_path.read_text())
        self.assertEqual(flag_data["severity"], "T3_MEDIUM")

    # ============================================================
    # FAIL ZERO_FILLS：24h n=0 + age >= 24h → strategy dormancy
    # ============================================================

    def test_fail_zero_fills_dormancy(self) -> None:
        """24h grid_trading n=0 且 age>=24h → FAIL ZERO_FILLS dormancy。

        engine_pid mtime 用 patch 設遠古值（age > 24h）模擬部署很久後 0 fills
        場景，避 test runtime 必須 wall-clock 在 WP-03 deploy 後 24h+ 才 run
        的 brittleness（per E2 catch-able edge case）。
        """
        from unittest.mock import patch as _patch
        import datetime as _dt

        # Engine pid mtime 用 deploy ts (engine 自 deploy 跑到現在)
        _write_engine_pid(Path(self._tmp_data.name), mtime_iso=WP03_DEPLOY_TIMESTAMP_UTC)

        # Patch datetime.now 回 deploy_ts + 48h，確保 age > 24h（ZERO_FILLS gate）
        deploy_ts = _dt.datetime.fromisoformat(
            WP03_DEPLOY_TIMESTAMP_UTC.replace("Z", "+00:00")
        )
        fake_now = deploy_ts + _dt.timedelta(hours=48)

        class _FakeDT(_dt.datetime):
            @classmethod
            def now(cls, tz=None):  # type: ignore[override]
                if tz is None:
                    return fake_now.replace(tzinfo=None)
                return fake_now.astimezone(tz)

        cur = _mock_cursor([
            _table_exists_row(),
            _baseline_query_result(500, 8.0, 12.0),
            _baseline_query_result(0, None, None),  # T1 n=0
            _baseline_query_result(0, None, None),  # T2 n=0 → triggers ZERO_FILLS
            _baseline_query_result(0, None, None),  # T3 n=0
        ])

        with _patch(
            "helper_scripts.db.passive_wait_healthcheck.checks_wp03_deploy_gate.datetime",
            _FakeDT,
        ):
            status, msg = check_69_wp03_ou_sigma_deploy_gate(cur)

        self.assertEqual(status, "FAIL", msg)
        self.assertIn("ZERO_FILLS", msg)
        self.assertIn("strategy dormancy", msg)
        flag_path = Path(self._tmp_data.name) / "wp03_revert_flag"
        self.assertTrue(flag_path.exists())

    # ============================================================
    # E2 Round 1 MEDIUM-1 fix：ZERO_FILLS env override age mismatch（false-positive guard）
    # LOOKBACK_HOURS=48 + age=30h + T1 12h has fills + T2 48h n=0
    #   → 修法 (B) 後 PASS（不觸 ZERO_FILLS，因 T1 50 fills > 0 是真實 active）
    # ============================================================

    def test_zero_fills_env_override_age_mismatch(self) -> None:
        """ZERO_FILLS false-positive guard（E2 Round 1 MEDIUM-1）：t2 window > engine age
        且 t2 n=0 但 t1 仍有 fills（策略 active），不應觸 ZERO_FILLS。

        場景：LOOKBACK_HOURS=48 + engine age=30h + T1 12h 50 fills + T2 48h n=0
        → 修法 (B) 後 t1["n"]==0 secondary guard 不滿足 → 不觸 ZERO_FILLS
        → 走 PASS path（T1/T2/T3 全 fine，無 approach warn 也無 hard trigger）。
        """
        from unittest.mock import patch as _patch
        import datetime as _dt

        os.environ["OPENCLAW_WP03_DEPLOY_GATE_LOOKBACK_HOURS"] = "48"
        # Engine pid mtime = deploy_ts（engine 自 deploy 跑到 fake_now）
        _write_engine_pid(Path(self._tmp_data.name), mtime_iso=WP03_DEPLOY_TIMESTAMP_UTC)

        # Patch datetime.now 回 deploy_ts + 30h，age=30h < t2_window=48h
        deploy_ts = _dt.datetime.fromisoformat(
            WP03_DEPLOY_TIMESTAMP_UTC.replace("Z", "+00:00")
        )
        fake_now = deploy_ts + _dt.timedelta(hours=30)

        class _FakeDT(_dt.datetime):
            @classmethod
            def now(cls, tz=None):  # type: ignore[override]
                if tz is None:
                    return fake_now.replace(tzinfo=None)
                return fake_now.astimezone(tz)

        cur = _mock_cursor([
            _table_exists_row(),
            _baseline_query_result(500, 8.0, 12.0),
            # T1 12h: n=50, avg=+5（active；> -10 trigger 也 > -8 approach）
            _baseline_query_result(50, 5.0, 10.0),
            # T2 48h: n=0（query window 超過 engine age 純粹是 mechanic，非真 dormancy）
            _baseline_query_result(0, None, None),
            # T3 7d: n=0（同因）— 但 T3 min sample=200 故不 trigger
            _baseline_query_result(0, None, None),
        ])

        with _patch(
            "helper_scripts.db.passive_wait_healthcheck.checks_wp03_deploy_gate.datetime",
            _FakeDT,
        ):
            status, msg = check_69_wp03_ou_sigma_deploy_gate(cur)

        # 期待 PASS：T1 有 fill 證明 active；T2 0 fills 純粹 env override mechanic
        self.assertEqual(status, "PASS", msg)
        self.assertNotIn("ZERO_FILLS", msg)
        # Revert flag 不應寫入
        flag_path = Path(self._tmp_data.name) / "wp03_revert_flag"
        self.assertFalse(
            flag_path.exists(),
            "ZERO_FILLS false-positive guard must not write revert flag",
        )
        # 確認 T1 + T2 fills 都顯示
        self.assertIn("12h n=50", msg)
        self.assertIn("48h n=0", msg)

    # ============================================================
    # WARN approach：12h avg = -8.5 < -8（T1 80% approach）但 > -10（T1 trigger）
    # ============================================================

    def test_warn_t1_approach(self) -> None:
        """T1 approach：12h avg=-8.5 < -8（80% × -10）但 > -10 → WARN。"""
        _write_engine_pid(Path(self._tmp_data.name))
        cur = _mock_cursor([
            _table_exists_row(),
            _baseline_query_result(500, 8.0, 12.0),
            _baseline_query_result(50, -8.5, 10.0),  # T1 approach
            _baseline_query_result(100, 5.0, 10.0),  # T2 fine
            _baseline_query_result(500, 7.0, 10.0),  # T3 fine
        ])

        status, msg = check_69_wp03_ou_sigma_deploy_gate(cur)

        self.assertEqual(status, "WARN", msg)
        self.assertIn("approaching T1", msg)
        # Revert flag 不應寫入（approach 不是 hard trigger）
        flag_path = Path(self._tmp_data.name) / "wp03_revert_flag"
        self.assertFalse(flag_path.exists(), "approach WARN must not write revert flag")

    # ============================================================
    # WARN approach T2：24h avg = -4.5 < -4（T2 80% approach）但 > -5
    # ============================================================

    def test_warn_t2_approach(self) -> None:
        """T2 approach：24h avg=-4.5 < -4（80% × -5）但 > -5 → WARN。"""
        _write_engine_pid(Path(self._tmp_data.name))
        cur = _mock_cursor([
            _table_exists_row(),
            _baseline_query_result(500, 8.0, 12.0),
            _baseline_query_result(50, -3.0, 10.0),  # T1 fine
            _baseline_query_result(100, -4.5, 10.0),  # T2 approach
            _baseline_query_result(500, 7.0, 10.0),  # T3 fine
        ])

        status, msg = check_69_wp03_ou_sigma_deploy_gate(cur)

        self.assertEqual(status, "WARN", msg)
        self.assertIn("approaching T2", msg)

    # ============================================================
    # WARN approach T3：7d cumulative drift > 2.4 bps below baseline 但 < 3
    # ============================================================

    def test_warn_t3_approach(self) -> None:
        """T3 approach：7d avg = baseline - 2.5（80% × 3=2.4 drift）→ WARN。"""
        _write_engine_pid(Path(self._tmp_data.name))
        cur = _mock_cursor([
            _table_exists_row(),
            _baseline_query_result(500, 8.0, 12.0),
            _baseline_query_result(50, 5.0, 10.0),  # T1 fine
            _baseline_query_result(100, 5.0, 10.0),  # T2 fine
            _baseline_query_result(500, 5.5, 10.0),  # T3: 5.5 < 5.6 (baseline-2.4) approach
        ])

        status, msg = check_69_wp03_ou_sigma_deploy_gate(cur)

        self.assertEqual(status, "WARN", msg)
        self.assertIn("approaching T3", msg)

    # ============================================================
    # REQUIRED env：approach WARN 升 FAIL（strict mode）
    # ============================================================

    def test_required_env_escalates_warn_to_fail(self) -> None:
        """OPENCLAW_WP03_DEPLOY_GATE_REQUIRED=1 + approach → FAIL escalation。

        但 approach 不寫 revert flag（只 hard trigger 才寫）— escalation 純 verdict
        升級不改 advisory behavior。
        """
        os.environ["OPENCLAW_WP03_DEPLOY_GATE_REQUIRED"] = "1"
        _write_engine_pid(Path(self._tmp_data.name))
        cur = _mock_cursor([
            _table_exists_row(),
            _baseline_query_result(500, 8.0, 12.0),
            _baseline_query_result(50, -8.5, 10.0),  # T1 approach
            _baseline_query_result(100, 5.0, 10.0),
            _baseline_query_result(500, 7.0, 10.0),
        ])

        status, msg = check_69_wp03_ou_sigma_deploy_gate(cur)

        self.assertEqual(status, "FAIL", msg)
        self.assertIn("REQUIRED escalation", msg)
        # Approach 升 FAIL 不寫 revert flag（與 hard trigger FAIL 區分）
        flag_path = Path(self._tmp_data.name) / "wp03_revert_flag"
        self.assertFalse(flag_path.exists())

    # ============================================================
    # Sample insufficient：T1/T2/T3 各 n < min_sample → 不 trigger（PASS）
    # ============================================================

    def test_low_sample_skip_trigger(self) -> None:
        """三窗 n < min_sample → 不 trigger，verdict PASS（樣本不足）。"""
        _write_engine_pid(Path(self._tmp_data.name))
        cur = _mock_cursor([
            _table_exists_row(),
            _baseline_query_result(500, 8.0, 12.0),
            _baseline_query_result(20, -15.0, 10.0),  # T1 n=20 < 30 → skip
            _baseline_query_result(40, -10.0, 10.0),  # T2 n=40 < 50 → skip
            _baseline_query_result(100, -5.0, 10.0),  # T3 n=100 < 200 → skip
        ])

        status, msg = check_69_wp03_ou_sigma_deploy_gate(cur)

        # 即便 avg 都很差，n 不夠 → 不 trigger；走 PASS path
        self.assertEqual(status, "PASS", msg)
        self.assertIn("within tolerance", msg)

    # ============================================================
    # ENV override：T2 window 改 48h
    # ============================================================

    def test_t2_window_env_override(self) -> None:
        """OPENCLAW_WP03_DEPLOY_GATE_LOOKBACK_HOURS=48 → T2 用 48h window。"""
        os.environ["OPENCLAW_WP03_DEPLOY_GATE_LOOKBACK_HOURS"] = "48"
        _write_engine_pid(Path(self._tmp_data.name))
        cur = _mock_cursor([
            _table_exists_row(),
            _baseline_query_result(500, 8.0, 12.0),
            _baseline_query_result(80, 5.0, 10.0),
            _baseline_query_result(200, 6.0, 10.0),  # T2: 48h window
            _baseline_query_result(500, 7.0, 10.0),
        ])

        status, msg = check_69_wp03_ou_sigma_deploy_gate(cur)

        self.assertEqual(status, "PASS", msg)
        self.assertIn("48h n=200", msg)  # T2 顯示 48h，不是 24h

    # ============================================================
    # Baseline cache reuse：第二次跑用 cache 不查 PG baseline window
    # ============================================================

    def test_baseline_cache_reuse(self) -> None:
        """第二次 run baseline cache 已存 → 不再 query baseline window，只查 3 窗。"""
        # 預寫 cache
        cache_path = Path(self._tmp_data.name) / "wp03_baseline_cache.json"
        cache_path.write_text(json.dumps({
            "n": 800,
            "avg_net_bps": 10.0,
            "std": 12.0,
            "computed_at": "2026-05-16T03:00:00Z",
            "window_start": "2026-05-11T00:00:00Z",
            "window_end": "2026-05-16T01:44:00Z",
            "window_label": "test cache",
        }), encoding="utf-8")
        _write_engine_pid(Path(self._tmp_data.name))
        # 只需 4 fetchone：to_regclass + T1 + T2 + T3（baseline 由 cache）
        cur = _mock_cursor([
            _table_exists_row(),
            _baseline_query_result(80, 6.0, 10.0),  # T1
            _baseline_query_result(200, 7.0, 10.0),  # T2
            _baseline_query_result(500, 8.0, 10.0),  # T3 (8 > 10-3=7 → PASS)
        ])

        status, msg = check_69_wp03_ou_sigma_deploy_gate(cur)

        self.assertEqual(status, "PASS", msg)
        self.assertIn("baseline_14d=10.00bps", msg)  # cache 值
        self.assertIn("cached", msg)


if __name__ == "__main__":
    unittest.main()
