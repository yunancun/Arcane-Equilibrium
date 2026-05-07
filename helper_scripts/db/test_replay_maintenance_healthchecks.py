#!/usr/bin/env python3
"""REF-20 Sprint D R8 — `[46]`-`[50]` maintenance healthcheck 單元測試。
REF-20 Sprint D R8 — `[46]`-`[50]` maintenance healthcheck unit tests.

MODULE_NOTE (中):
    REF-20 Sprint D R8（2026-05-05）maintenance healthcheck 五個哨兵的
    pure-mock-cursor 測試。測試案例對齊 plan §6.R8 §1.3 的 5 sentinel
    spec，覆蓋 PASS / WARN / FAIL / 表缺即 graceful PASS-skip 各 path。

    測試僅用 unittest.mock，無真實 PG 依賴；live PG opt-in case 留作
    operator post-deploy ad-hoc verify（per Sprint C R7 同 pattern）。

MODULE_NOTE (EN):
    REF-20 Sprint D R8 (2026-05-05) maintenance healthcheck 5-sentinel
    suite pure-mock-cursor unit tests. Cases mirror plan §6.R8 §1.3
    sentinel spec, covering PASS / WARN / FAIL / table-absent graceful
    PASS-skip paths.

    Tests use unittest.mock only — no live PG dependency. Live PG opt-in
    cases deferred to operator post-deploy ad-hoc verify (mirror Sprint
    C R7 pattern).

Spec source / 規格來源:
    - docs/execution_plan/2026-05-04--ref20_gap_closure_reality_backtest_plan_v1.md
      Sprint D R8 §6.R8 task 2 (5 healthcheck probes)
    - helper_scripts/db/passive_wait_healthcheck/checks_replay_maintenance.py
"""

from __future__ import annotations

import os
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# srv root on sys.path (mirror test_pricing_binding_healthcheck.py).
# 加 srv root 到 sys.path（鏡像 test_pricing_binding_healthcheck.py）。
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_HELPER_SCRIPTS_DIR = os.path.dirname(_THIS_DIR)
_SRV_ROOT = os.path.dirname(_HELPER_SCRIPTS_DIR)
sys.path.insert(0, _SRV_ROOT)

from helper_scripts.db.passive_wait_healthcheck.checks_replay_maintenance import (  # noqa: E402
    ARTIFACT_OLDEST_PASS_MAX_DAYS,
    ARTIFACT_OLDEST_WARN_MAX_DAYS,
    ARTIFACT_STORAGE_CAP_MB_DEFAULT,
    REGISTRY_24H_WARN_MIN_ROWS,
    REGISTRY_7D_PASS_MIN_ROWS,
    RETENTION_CANDIDATES_FAIL_THRESHOLD,
    RETENTION_LAST_RUN_PASS_MAX_HOURS,
    RETENTION_LAST_RUN_WARN_MAX_HOURS,
    RUN_STATE_FAILED_RATE_PASS_MAX,
    RUN_STATE_FAILED_RATE_WARN_MAX,
    RUN_STATE_SUPERSEDING_COMPLETED_MIN,
    RUN_STATE_ZOMBIE_PASS_MAX_HOURS,
    RUN_STATE_ZOMBIE_WARN_MAX_HOURS,
    RUNNER_BINARY_CANDIDATE_PATHS,
    check_53_ref21_v058_symbol_universe_recorder,
    check_46_mlde_shadow_retention_status,
    check_47_replay_runner_binary,
    check_48_replay_manifest_registry_growth,
    check_49_replay_artifact_retention,
    check_50_replay_run_state_health,
)


# ---------------------------------------------------------------------------
# Mock cursor builder.
# 模擬 cursor 建構器。
# ---------------------------------------------------------------------------

def _build_cur(
    fetchone_returns: list,
    fetchall_returns: list | None = None,
) -> MagicMock:
    """Build a MagicMock cursor with sequential ``fetchone`` returns.

    Each call to ``cur.fetchone()`` pops the next entry from
    ``fetchone_returns`` in order. ``fetchall`` returns the supplied list
    or ``[]``.

    建立 MagicMock cursor：``fetchone()`` 按序取 ``fetchone_returns`` 元素。
    """
    cur = MagicMock()
    cur.connection = MagicMock()
    cur.connection.rollback = MagicMock()

    # `fetchone` returns sequentially per call.
    # `fetchone` 按 call 順序回值。
    cur.fetchone.side_effect = list(fetchone_returns)
    cur.fetchall.return_value = fetchall_returns or []
    cur.execute = MagicMock()
    return cur


# ---------------------------------------------------------------------------
# `[46]` mlde_shadow_retention_status tests.
# `[46]` mlde_shadow_retention_status 測試。
# ---------------------------------------------------------------------------
class TestCheck46MldeShadowRetention(unittest.TestCase):
    """`[46]` retention cron 活性 + candidate cap 雙軸測試。"""

    def _patch_sentinel_mtime_now(self, age_hours: float) -> str:
        """Build a sentinel file path patched mtime equivalent to (now - age_hours).
        建立 sentinel 檔以 mtime = now - age_hours 模擬。

        Returns the path string for OPENCLAW_DATA_DIR.
        """
        import tempfile
        tmp_dir = tempfile.mkdtemp(prefix="r8_sentinel_test_")
        sentinel_path = Path(tmp_dir) / "mlde_shadow_recommendations_retention_last_run"
        sentinel_path.touch()
        target_mtime = time.time() - (age_hours * 3600.0)
        os.utime(sentinel_path, (target_mtime, target_mtime))
        return tmp_dir

    def test_pass_when_v056_absent_and_no_sentinel(self) -> None:
        """V056 不存在 + sentinel 不存在 → PASS（pre-deploy graceful skip）。
        """
        cur = _build_cur(fetchone_returns=[(False,)])  # V056 not present
        with patch.dict(os.environ, {"OPENCLAW_DATA_DIR": "/nonexistent_path_for_test"}, clear=False):
            status, msg = check_46_mlde_shadow_retention_status(cur)
        self.assertEqual(status, "PASS", msg)
        self.assertIn("pre-deploy graceful skip", msg)

    def test_pass_when_v056_present_cron_fresh_low_candidates(self) -> None:
        """V056 在 + cron <26h + candidates <50k → PASS。
        """
        tmp_dir = self._patch_sentinel_mtime_now(age_hours=1.0)
        cur = _build_cur(fetchone_returns=[
            (True,),         # V056 present
            (5, 10),         # 5 replay candidates + 10 real candidates
        ])
        with patch.dict(os.environ, {"OPENCLAW_DATA_DIR": tmp_dir}, clear=False):
            status, msg = check_46_mlde_shadow_retention_status(cur)
        self.assertEqual(status, "PASS", msg)
        self.assertIn("retention healthy", msg)

    def test_warn_when_cron_age_above_pass_threshold(self) -> None:
        """V056 在 + cron age > PASS_MAX (26h) but < WARN_MAX (50h) → WARN。
        """
        tmp_dir = self._patch_sentinel_mtime_now(age_hours=30.0)
        cur = _build_cur(fetchone_returns=[
            (True,),
            (5, 10),
        ])
        with patch.dict(os.environ, {"OPENCLAW_DATA_DIR": tmp_dir}, clear=False):
            status, msg = check_46_mlde_shadow_retention_status(cur)
        self.assertEqual(status, "WARN", msg)
        self.assertIn("daily cadence missed", msg)

    def test_fail_when_cron_age_above_warn_threshold(self) -> None:
        """V056 在 + cron age > WARN_MAX (50h) → FAIL（2-day miss）。
        """
        tmp_dir = self._patch_sentinel_mtime_now(age_hours=72.0)
        cur = _build_cur(fetchone_returns=[
            (True,),
            (5, 10),
        ])
        with patch.dict(os.environ, {"OPENCLAW_DATA_DIR": tmp_dir}, clear=False):
            status, msg = check_46_mlde_shadow_retention_status(cur)
        self.assertEqual(status, "FAIL", msg)
        self.assertIn("2-day cron miss", msg)

    def test_fail_when_candidates_above_fail_threshold(self) -> None:
        """V056 在 + cron fresh + candidates total > 50k → FAIL（dry-run stuck）。
        """
        tmp_dir = self._patch_sentinel_mtime_now(age_hours=1.0)
        cur = _build_cur(fetchone_returns=[
            (True,),
            (60000, 5),  # 60k replay candidates
        ])
        with patch.dict(os.environ, {"OPENCLAW_DATA_DIR": tmp_dir}, clear=False):
            status, msg = check_46_mlde_shadow_retention_status(cur)
        self.assertEqual(status, "FAIL", msg)
        self.assertIn("retention not in apply mode", msg)


# ---------------------------------------------------------------------------
# `[47]` replay_runner_binary tests.
# `[47]` replay_runner_binary 測試。
# ---------------------------------------------------------------------------
class TestCheck47ReplayRunnerBinary(unittest.TestCase):
    """`[47]` Linux replay_runner binary presence + executable bit 測試。"""

    def test_pass_when_env_override_executable(self) -> None:
        """OPENCLAW_REPLAY_RUNNER_BIN 指可執行 file → PASS。"""
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False) as f:
            override_path = f.name
        os.chmod(override_path, 0o755)
        try:
            with patch.dict(os.environ, {"OPENCLAW_REPLAY_RUNNER_BIN": override_path}, clear=False):
                status, msg = check_47_replay_runner_binary()
            self.assertEqual(status, "PASS", msg)
            self.assertIn("env override", msg)
        finally:
            os.unlink(override_path)

    def test_fail_when_env_override_not_executable(self) -> None:
        """OPENCLAW_REPLAY_RUNNER_BIN 指不存在 path → FAIL。"""
        with patch.dict(os.environ, {"OPENCLAW_REPLAY_RUNNER_BIN": "/nonexistent_runner"}, clear=False):
            status, msg = check_47_replay_runner_binary()
        self.assertEqual(status, "FAIL", msg)
        self.assertIn("not executable file", msg)

    def test_pass_when_release_path_exists(self) -> None:
        """workspace/release path 存在且可執行 → PASS。"""
        import tempfile
        tmp_base = tempfile.mkdtemp(prefix="r8_runner_test_")
        release_path = Path(tmp_base) / RUNNER_BINARY_CANDIDATE_PATHS[0]
        release_path.parent.mkdir(parents=True, exist_ok=True)
        release_path.touch()
        os.chmod(release_path, 0o755)
        try:
            with patch.dict(os.environ, {"OPENCLAW_BASE_DIR": tmp_base, "OPENCLAW_REPLAY_RUNNER_BIN": ""}, clear=False):
                status, msg = check_47_replay_runner_binary()
            self.assertEqual(status, "PASS", msg)
            self.assertIn("release", msg)
        finally:
            import shutil
            shutil.rmtree(tmp_base, ignore_errors=True)

    def test_warn_when_only_debug_path_exists(self) -> None:
        """只有 workspace/debug path → WARN（未 --rebuild）。"""
        import tempfile
        tmp_base = tempfile.mkdtemp(prefix="r8_runner_test_")
        debug_path = Path(tmp_base) / RUNNER_BINARY_CANDIDATE_PATHS[1]  # workspace debug
        debug_path.parent.mkdir(parents=True, exist_ok=True)
        debug_path.touch()
        os.chmod(debug_path, 0o755)
        try:
            with patch.dict(os.environ, {"OPENCLAW_BASE_DIR": tmp_base, "OPENCLAW_REPLAY_RUNNER_BIN": ""}, clear=False):
                status, msg = check_47_replay_runner_binary()
            self.assertEqual(status, "WARN", msg)
            self.assertIn("debug build", msg)
        finally:
            import shutil
            shutil.rmtree(tmp_base, ignore_errors=True)

    def test_fail_when_no_path_exists(self) -> None:
        """All 4 fallback path 全缺 → FAIL（cargo --release 未跑）。"""
        import tempfile
        tmp_base = tempfile.mkdtemp(prefix="r8_runner_test_")
        try:
            with patch.dict(os.environ, {"OPENCLAW_BASE_DIR": tmp_base, "OPENCLAW_REPLAY_RUNNER_BIN": ""}, clear=False):
                status, msg = check_47_replay_runner_binary()
            self.assertEqual(status, "FAIL", msg)
            self.assertIn("not found at any of", msg)
        finally:
            import shutil
            shutil.rmtree(tmp_base, ignore_errors=True)


# ---------------------------------------------------------------------------
# `[53]` ref21_v058_symbol_universe_recorder tests.
# `[53]` REF21 V058 symbol universe recorder 測試。
# ---------------------------------------------------------------------------
class TestCheck53Ref21V058Recorder(unittest.TestCase):
    """`[53]` V058 recurring universe snapshot healthcheck tests."""

    def test_pass_skip_when_v058_table_absent(self) -> None:
        cur = _build_cur(fetchone_returns=[(False,)])

        status, msg = check_53_ref21_v058_symbol_universe_recorder(cur)

        self.assertEqual(status, "PASS", msg)
        self.assertIn("pre-deploy graceful skip", msg)

    def test_fail_when_v058_table_exists_but_empty(self) -> None:
        cur = _build_cur(fetchone_returns=[(True,), (0, 0, None)])

        status, msg = check_53_ref21_v058_symbol_universe_recorder(cur)

        self.assertEqual(status, "FAIL", msg)
        self.assertIn("no Bybit rows", msg)

    def test_pass_when_recent_rows_exist(self) -> None:
        cur = _build_cur(fetchone_returns=[(True,), (905, 905, 120)])

        status, msg = check_53_ref21_v058_symbol_universe_recorder(cur)

        self.assertEqual(status, "PASS", msg)
        self.assertIn("recorder healthy", msg)

    def test_warn_when_latest_row_misses_hourly_cadence(self) -> None:
        cur = _build_cur(fetchone_returns=[(True,), (905, 905, 3 * 3600)])

        status, msg = check_53_ref21_v058_symbol_universe_recorder(cur)

        self.assertEqual(status, "WARN", msg)
        self.assertIn("missed hourly cadence", msg)

    def test_fail_when_latest_row_is_stale(self) -> None:
        cur = _build_cur(fetchone_returns=[(True,), (905, 0, 27 * 3600)])

        status, msg = check_53_ref21_v058_symbol_universe_recorder(cur)

        self.assertEqual(status, "FAIL", msg)
        self.assertIn("recorder stale", msg)


# ---------------------------------------------------------------------------
# `[48]` replay_manifest_registry_growth tests.
# `[48]` replay_manifest_registry_growth 測試。
# ---------------------------------------------------------------------------
class TestCheck48ReplayManifestRegistryGrowth(unittest.TestCase):
    """`[48]` replay.experiments row growth rate stall 偵測測試。"""

    def test_pass_when_table_absent(self) -> None:
        """V049 未 land → PASS-skip。"""
        cur = _build_cur(fetchone_returns=[(False,)])  # to_regclass IS NULL
        status, msg = check_48_replay_manifest_registry_growth(cur)
        self.assertEqual(status, "PASS", msg)
        self.assertIn("V049 not applied", msg)

    def test_pass_when_table_empty(self) -> None:
        """V049 在但 0 row → PASS（freshly bootstrapped）。"""
        cur = _build_cur(fetchone_returns=[
            (True,),
            (0, 0, 0, None),
        ])
        status, msg = check_48_replay_manifest_registry_growth(cur)
        self.assertEqual(status, "PASS", msg)
        self.assertIn("empty", msg)

    def test_pass_when_growth_healthy(self) -> None:
        """7d 5 row + 24h 1 row → PASS（registry growth healthy）。"""
        cur = _build_cur(fetchone_returns=[
            (True,),
            (10, 5, 1, 3600),
        ])
        status, msg = check_48_replay_manifest_registry_growth(cur)
        self.assertEqual(status, "PASS", msg)
        self.assertIn("healthy", msg)

    def test_warn_when_24h_quiet_but_7d_active(self) -> None:
        """7d 5 row + 24h 0 row → WARN（quiet day）。"""
        cur = _build_cur(fetchone_returns=[
            (True,),
            (10, 5, 0, 100000),
        ])
        status, msg = check_48_replay_manifest_registry_growth(cur)
        self.assertEqual(status, "WARN", msg)
        self.assertIn("quiet 24h", msg)

    def test_fail_when_7d_zero_but_total_geq_2(self) -> None:
        """7d 0 row + total >= 2 → FAIL（runner stalled）。"""
        cur = _build_cur(fetchone_returns=[
            (True,),
            (5, 0, 0, 1000000),
        ])
        status, msg = check_48_replay_manifest_registry_growth(cur)
        self.assertEqual(status, "FAIL", msg)
        self.assertIn("runner stalled", msg)


# ---------------------------------------------------------------------------
# `[49]` replay_artifact_retention tests.
# `[49]` replay_artifact_retention 測試。
# ---------------------------------------------------------------------------
class TestCheck49ReplayArtifactRetention(unittest.TestCase):
    """`[49]` V046 oldest age + storage cap dual check 測試。"""

    def test_pass_when_table_absent(self) -> None:
        """V046 未 land → PASS-skip。"""
        cur = _build_cur(fetchone_returns=[(False,)])
        status, msg = check_49_replay_artifact_retention(cur)
        self.assertEqual(status, "PASS", msg)
        self.assertIn("V046 not applied", msg)

    def test_pass_when_table_empty(self) -> None:
        """V046 在但 0 row → PASS（freshly pruned or pre-Sprint-A R3）。"""
        cur = _build_cur(fetchone_returns=[
            (True,),
            (0, None, 0),
        ])
        status, msg = check_49_replay_artifact_retention(cur)
        self.assertEqual(status, "PASS", msg)
        self.assertIn("empty", msg)

    def test_pass_when_oldest_below_30d_and_total_below_cap(self) -> None:
        """oldest <30d + total <cap → PASS。"""
        cur = _build_cur(fetchone_returns=[
            (True,),
            (5, 86400 * 10, 100 * 1024 * 1024),  # 10 days old, 100 MB
        ])
        status, msg = check_49_replay_artifact_retention(cur)
        self.assertEqual(status, "PASS", msg)
        self.assertIn("retention healthy", msg)

    def test_warn_when_oldest_above_30d_but_below_60d(self) -> None:
        """oldest 35d → WARN（TTL prune cron sluggish）。"""
        cur = _build_cur(fetchone_returns=[
            (True,),
            (5, 86400 * 35, 100 * 1024 * 1024),
        ])
        status, msg = check_49_replay_artifact_retention(cur)
        self.assertEqual(status, "WARN", msg)
        self.assertIn("PASS threshold", msg)

    def test_fail_when_oldest_above_60d(self) -> None:
        """oldest >60d → FAIL（TTL prune cron silent dead）。"""
        cur = _build_cur(fetchone_returns=[
            (True,),
            (5, 86400 * 70, 100 * 1024 * 1024),
        ])
        status, msg = check_49_replay_artifact_retention(cur)
        self.assertEqual(status, "FAIL", msg)
        self.assertIn("TTL prune cron silent dead", msg)

    def test_fail_when_total_bytes_above_cap(self) -> None:
        """total > cap → FAIL（cap prune cron silent dead）。"""
        cur = _build_cur(fetchone_returns=[
            (True,),
            (5, 86400 * 5, (ARTIFACT_STORAGE_CAP_MB_DEFAULT + 100) * 1024 * 1024),
        ])
        status, msg = check_49_replay_artifact_retention(cur)
        self.assertEqual(status, "FAIL", msg)
        self.assertIn("storage cap", msg)


# ---------------------------------------------------------------------------
# `[50]` replay_run_state_health tests.
# `[50]` replay_run_state_health 測試。
# ---------------------------------------------------------------------------
class TestCheck50ReplayRunStateHealth(unittest.TestCase):
    """`[50]` V045 failed_rate + zombie 'running' detection 測試。"""

    def test_pass_when_table_absent(self) -> None:
        """V045 未 land → PASS-skip。"""
        cur = _build_cur(fetchone_returns=[(False,)])
        status, msg = check_50_replay_run_state_health(cur)
        self.assertEqual(status, "PASS", msg)
        self.assertIn("V045 not applied", msg)

    def test_pass_when_no_runs_in_7d(self) -> None:
        """V045 在但 7d 全空 → PASS（quiet week）。"""
        cur = _build_cur(fetchone_returns=[
            (True,),
            (0, 0, 0, 0, None, None, None, 0),
        ])
        status, msg = check_50_replay_run_state_health(cur)
        self.assertEqual(status, "PASS", msg)
        self.assertIn("empty in 7d", msg)

    def test_pass_when_failed_rate_low(self) -> None:
        """failed_rate 5% + 0 zombie → PASS。"""
        cur = _build_cur(fetchone_returns=[
            (True,),
            (95, 5, 0, 0, None, 1, 2, 1),  # 95 completed + 5 failed = 5% failed rate
        ])
        status, msg = check_50_replay_run_state_health(cur)
        self.assertEqual(status, "PASS", msg)
        self.assertIn("PASS", msg)

    def test_warn_when_failed_rate_above_pass(self) -> None:
        """failed_rate 15% (>10% PASS but <20% WARN) → WARN。"""
        cur = _build_cur(fetchone_returns=[
            (True,),
            (85, 15, 0, 0, None, 1, 2, 1),
        ])
        status, msg = check_50_replay_run_state_health(cur)
        self.assertEqual(status, "WARN", msg)
        self.assertIn("PASS threshold", msg)

    def test_fail_when_failed_rate_above_warn(self) -> None:
        """failed_rate 30% → FAIL（系統性問題）。"""
        cur = _build_cur(fetchone_returns=[
            (True,),
            (70, 30, 0, 0, None, 2, 1, 0),
        ])
        status, msg = check_50_replay_run_state_health(cur)
        self.assertEqual(status, "FAIL", msg)
        self.assertIn("FAIL threshold", msg)

    def test_warn_when_failed_rate_superseded_by_newer_successes(self) -> None:
        """High historical failed_rate + newer completed streak → WARN."""
        cur = _build_cur(fetchone_returns=[
            (True,),
            (6, 6, 0, 0, None, 1, 2, RUN_STATE_SUPERSEDING_COMPLETED_MIN),
        ])
        status, msg = check_50_replay_run_state_health(cur)
        self.assertEqual(status, "WARN", msg)
        self.assertIn("supersede newest failure", msg)

    def test_warn_when_zombie_running_above_1h(self) -> None:
        """zombie 'running' age 2h → WARN。"""
        cur = _build_cur(fetchone_returns=[
            (True,),
            (90, 5, 0, 1, 7200, 1, 2, 1),  # 1 'running' aged 2h
        ])
        status, msg = check_50_replay_run_state_health(cur)
        self.assertEqual(status, "WARN", msg)
        self.assertIn("zombie_running_age", msg)

    def test_fail_when_zombie_running_above_4h(self) -> None:
        """zombie 'running' age 5h → FAIL（subprocess 死亡未收回）。"""
        cur = _build_cur(fetchone_returns=[
            (True,),
            (90, 5, 0, 1, 18000, 1, 2, 1),  # 1 'running' aged 5h
        ])
        status, msg = check_50_replay_run_state_health(cur)
        self.assertEqual(status, "FAIL", msg)
        self.assertIn("subprocess died", msg)


# ---------------------------------------------------------------------------
# Constants sanity tests.
# 常量合理性測試。
# ---------------------------------------------------------------------------
class TestConstantsSanity(unittest.TestCase):
    """所有 sentinel 常量必符合 plan §6.R8 spec 計算範圍。"""

    def test_retention_thresholds_ordered(self) -> None:
        """PASS_MAX < WARN_MAX。"""
        self.assertLess(RETENTION_LAST_RUN_PASS_MAX_HOURS, RETENTION_LAST_RUN_WARN_MAX_HOURS)
        self.assertGreater(RETENTION_CANDIDATES_FAIL_THRESHOLD, 0)

    def test_artifact_thresholds_ordered(self) -> None:
        """oldest PASS_MAX_DAYS <= WARN_MAX_DAYS。"""
        self.assertLessEqual(ARTIFACT_OLDEST_PASS_MAX_DAYS, ARTIFACT_OLDEST_WARN_MAX_DAYS)
        self.assertGreater(ARTIFACT_STORAGE_CAP_MB_DEFAULT, 0)

    def test_run_state_thresholds_ordered(self) -> None:
        """failed_rate / zombie 兩軸 PASS < WARN。"""
        self.assertLess(RUN_STATE_FAILED_RATE_PASS_MAX, RUN_STATE_FAILED_RATE_WARN_MAX)
        self.assertLess(RUN_STATE_ZOMBIE_PASS_MAX_HOURS, RUN_STATE_ZOMBIE_WARN_MAX_HOURS)

    def test_registry_thresholds_sane(self) -> None:
        """7d / 24h 增長下限 sane。"""
        self.assertGreaterEqual(REGISTRY_7D_PASS_MIN_ROWS, 1)
        self.assertGreaterEqual(REGISTRY_24H_WARN_MIN_ROWS, 0)

    def test_runner_binary_candidate_paths_priority(self) -> None:
        """4 path workspace release 優先於 debug 與 legacy nested。"""
        self.assertEqual(len(RUNNER_BINARY_CANDIDATE_PATHS), 4)
        self.assertIn("release/replay_runner", RUNNER_BINARY_CANDIDATE_PATHS[0])
        self.assertIn("debug/replay_runner", RUNNER_BINARY_CANDIDATE_PATHS[1])
        # legacy nested last.
        self.assertIn("openclaw_engine/target", RUNNER_BINARY_CANDIDATE_PATHS[2])
        self.assertIn("openclaw_engine/target", RUNNER_BINARY_CANDIDATE_PATHS[3])


if __name__ == "__main__":
    unittest.main()
