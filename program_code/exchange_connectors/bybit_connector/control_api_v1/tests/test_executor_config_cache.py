"""
G3-03 Phase B + W-AUDIT-9 T3 — ExecutorConfigCache unit tests.
Coverage:
  1. Initial fail-closed default (shadow_mode=True before any IPC fetch).
  2. Successful IPC fetch updates snapshot + marks initialized.
  3. Polling refresh (interval-driven re-fetch).
  4. IPC error after init: retains previous good snapshot.
  5. IPC error before init: stays on fail-closed default.
  6. Lifecycle stop_polling joins thread cleanly.
  7. shadow_mode_provider() returns current shadow_mode (live read).
  8. Concurrent reads stay safe under interleaved polls.
  9. Malformed IPC response (missing executor) treated as error → fail-closed.
 10. Module singleton dedup via get_executor_config_cache().

W-AUDIT-9 T3 新增（per AMD-2026-05-09-03 §2.1, §4.4 + TODO v19 §5 invariant 9）：
 11. CanaryStage.from_raw 解析（int / str / IntEnum / out-of-range / None）
 12. _parse_response stage 欄位 + cohort + 觀察期解析
 13. backward-compat reject：legacy shadow_mode=false 無 canary_stage → Stage 0
 14. canary_stage_provider() exception → Stage 0（不是 Stage 1）
 15. shadow_mode_provider() lambda：Stage 0 → True / Stage ≥ 1 → False
 16. legacy shadow=true 配 canary_stage=0 backward-compat 行為
"""

from __future__ import annotations

import os
import sys
import threading
import time
import unittest
from unittest.mock import patch

_test_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(_test_dir)
if _control_api_dir not in sys.path:
    sys.path.insert(0, _control_api_dir)

from app import executor_config_cache as ecc_mod
from app.executor_config_cache import (
    CanaryCohort,
    CanaryStage,
    ExecutorConfigCache,
    ExecutorRuntimeConfig,
    get_executor_config_cache,
)


def _make_response(
    *,
    shadow: bool = False,
    max_pos: float = 0.10,
    per_symbol: dict | None = None,
    version: int = 7,
    canary_stage: int | None = None,
) -> dict:
    """Helper: build a get_risk_config-shaped IPC response.

    W-AUDIT-9 T3：``shadow=False`` 場景必伴隨 ``canary_stage >= 1`` 才能通過
    AMD §4.4 backward-compat reject；shadow=True 預設配 canary_stage=0
    （backward-compat legacy）。
    """
    executor_blob: dict = {
        "shadow_mode": shadow,
        "max_position_pct": max_pos,
        "per_symbol_position_cap": per_symbol or {},
    }
    # 規則：shadow=False 必須帶 canary_stage（避 §4.4 reject）；shadow=True 配
    # canary_stage=0 是 legacy 默認；caller 顯式 override canary_stage 優先。
    if canary_stage is not None:
        executor_blob["canary_stage"] = canary_stage
    elif shadow is False:
        # 默認 Stage 1（PAPER_SINGLE_COHORT）以與舊測試 shadow=False 語義對齊
        executor_blob["canary_stage"] = 1
    return {
        "config": {"executor": executor_blob},
        "version": version,
    }


class TestInitialFailClosedDefault(unittest.TestCase):
    """1. Pre-fetch state must be safe (shadow_mode=True)."""

    def test_default_snapshot_is_shadow_mode_true(self):
        cache = ExecutorConfigCache()
        snap = cache.get()
        self.assertTrue(snap.shadow_mode)
        self.assertFalse(cache.is_initialized())
        self.assertEqual(snap.config_version, 0)

    def test_provider_callable_returns_true_initially(self):
        cache = ExecutorConfigCache()
        provider = cache.shadow_mode_provider()
        self.assertTrue(provider())


class TestSuccessfulFetch(unittest.TestCase):
    """2. Successful single-poll updates snapshot."""

    def test_poll_once_success_updates_snapshot(self):
        cache = ExecutorConfigCache()
        with patch.object(
            cache, "_fetch_via_ipc_blocking",
            return_value=ExecutorRuntimeConfig(
                shadow_mode=False,
                max_position_pct=0.20,
                per_symbol_position_cap={"BTCUSDT": 0.50},
                config_version=42,
                fetched_at_ms=int(time.time() * 1000),
            ),
        ):
            cache._poll_once()
        snap = cache.get()
        self.assertFalse(snap.shadow_mode)
        self.assertAlmostEqual(snap.max_position_pct, 0.20)
        self.assertEqual(snap.per_symbol_position_cap.get("BTCUSDT"), 0.50)
        self.assertEqual(snap.config_version, 42)
        self.assertTrue(cache.is_initialized())

    def test_response_parser_extracts_executor_subslice(self):
        resp = _make_response(shadow=False, max_pos=0.07, version=11)
        snap = ExecutorConfigCache._parse_response(resp)
        self.assertFalse(snap.shadow_mode)
        self.assertAlmostEqual(snap.max_position_pct, 0.07)
        self.assertEqual(snap.config_version, 11)


class TestPollingRefresh(unittest.TestCase):
    """3. Polling daemon re-fetches at interval."""

    def test_poll_loop_refreshes_at_interval(self):
        cache = ExecutorConfigCache(poll_interval_s=0.05)
        responses = [
            ExecutorRuntimeConfig(shadow_mode=True, config_version=1, fetched_at_ms=1),
            ExecutorRuntimeConfig(shadow_mode=False, config_version=2, fetched_at_ms=2),
            ExecutorRuntimeConfig(shadow_mode=False, config_version=3, fetched_at_ms=3),
        ]
        idx = {"i": 0}

        def fake_fetch():
            i = idx["i"]
            idx["i"] = min(i + 1, len(responses) - 1)
            return responses[i]

        with patch.object(cache, "_fetch_via_ipc_blocking", side_effect=lambda: fake_fetch()):
            cache.start_polling()
            try:
                # Wait until we observe at least 2 successful polls.
                deadline = time.time() + 2.0
                while time.time() < deadline:
                    if cache._stats_snapshot_for_tests()["successes"] >= 2:
                        break
                    time.sleep(0.01)
            finally:
                cache.stop_polling()
        stats = cache._stats_snapshot_for_tests()
        self.assertGreaterEqual(stats["successes"], 2)
        # Final snapshot should be one of the later entries (shadow=False).
        self.assertFalse(cache.get().shadow_mode)


class TestIpcErrorRetainsPrevious(unittest.TestCase):
    """4. After successful init, transient errors retain previous snapshot."""

    def test_post_init_error_retains_prev_snapshot(self):
        cache = ExecutorConfigCache()
        good = ExecutorRuntimeConfig(
            shadow_mode=False, max_position_pct=0.30, config_version=99, fetched_at_ms=1,
        )
        with patch.object(cache, "_fetch_via_ipc_blocking", return_value=good):
            cache._poll_once()
        self.assertTrue(cache.is_initialized())
        # Now simulate a transient failure.
        with patch.object(
            cache, "_fetch_via_ipc_blocking",
            side_effect=ConnectionError("socket closed"),
        ):
            cache._poll_once()
        snap = cache.get()
        # Previous good snapshot retained.
        self.assertFalse(snap.shadow_mode)
        self.assertAlmostEqual(snap.max_position_pct, 0.30)
        self.assertEqual(snap.config_version, 99)


class TestIpcErrorBeforeInit(unittest.TestCase):
    """5. Errors before first success leave fail-closed default in place."""

    def test_pre_init_error_stays_fail_closed(self):
        cache = ExecutorConfigCache()
        with patch.object(
            cache, "_fetch_via_ipc_blocking",
            side_effect=ConnectionError("socket missing"),
        ):
            cache._poll_once()
        self.assertFalse(cache.is_initialized())
        # Default fail-closed: shadow_mode True.
        self.assertTrue(cache.get().shadow_mode)


class TestLifecycleStopPolling(unittest.TestCase):
    """6. stop_polling() joins the daemon thread cleanly."""

    def test_stop_polling_joins_cleanly(self):
        cache = ExecutorConfigCache(poll_interval_s=0.05)
        with patch.object(
            cache, "_fetch_via_ipc_blocking",
            return_value=ExecutorRuntimeConfig(shadow_mode=True),
        ):
            cache.start_polling()
            time.sleep(0.05)
            self.assertTrue(cache.stop_polling(join_timeout=2.0))
        # Idempotent second call.
        self.assertTrue(cache.stop_polling(join_timeout=2.0))


class TestProviderLambda(unittest.TestCase):
    """7. shadow_mode_provider() always reads current snapshot."""

    def test_provider_reads_live(self):
        cache = ExecutorConfigCache()
        provider = cache.shadow_mode_provider()
        self.assertTrue(provider())  # initial fail-closed
        # W-AUDIT-9 T3：shadow_mode=False 必伴隨 canary_stage >= 1，否則
        # shadow_mode_provider 投影為 True（per stage projection 不變式）
        cache._inject_snapshot_for_tests(
            ExecutorRuntimeConfig(
                shadow_mode=False,
                canary_stage=CanaryStage.PAPER_SINGLE_COHORT,
                config_version=1,
                fetched_at_ms=1,
            )
        )
        self.assertFalse(provider())  # reads new snapshot
        cache._inject_snapshot_for_tests(
            ExecutorRuntimeConfig(
                shadow_mode=True,
                canary_stage=CanaryStage.SHADOW,
                config_version=2,
                fetched_at_ms=2,
            )
        )
        self.assertTrue(provider())  # reads back to True

    def test_provider_fetches_explicit_engine(self):
        cache = ExecutorConfigCache(engine="paper")
        provider = cache.shadow_mode_provider()
        with patch.object(
            cache,
            "_fetch_via_ipc_blocking",
            return_value=ExecutorRuntimeConfig(
                shadow_mode=False,
                canary_stage=CanaryStage.PAPER_SINGLE_COHORT,
                config_version=9,
                fetched_at_ms=1,
            ),
        ) as mocked_fetch:
            self.assertFalse(provider("demo"))
        mocked_fetch.assert_called_once_with(engine="demo")

    def test_provider_maps_live_demo_to_live(self):
        cache = ExecutorConfigCache(engine="paper")
        provider = cache.shadow_mode_provider()
        with patch.object(
            cache,
            "_fetch_via_ipc_blocking",
            return_value=ExecutorRuntimeConfig(
                shadow_mode=False,
                canary_stage=CanaryStage.PAPER_SINGLE_COHORT,
                config_version=10,
                fetched_at_ms=1,
            ),
        ) as mocked_fetch:
            self.assertFalse(provider("live_demo"))
        mocked_fetch.assert_called_once_with(engine="live")


class TestConcurrentReads(unittest.TestCase):
    """8. Concurrent reads under interleaving polls remain safe."""

    def test_concurrent_reads_atomic(self):
        cache = ExecutorConfigCache()
        good_a = ExecutorRuntimeConfig(shadow_mode=False, config_version=1, fetched_at_ms=1)
        good_b = ExecutorRuntimeConfig(shadow_mode=True, config_version=2, fetched_at_ms=2)
        cache._inject_snapshot_for_tests(good_a)
        results: list[bool] = []
        stop = threading.Event()

        def reader():
            while not stop.is_set():
                results.append(cache.get().shadow_mode)

        t = threading.Thread(target=reader, daemon=True)
        t.start()
        # Flip snapshot a few times.
        for _ in range(50):
            cache._inject_snapshot_for_tests(good_a)
            cache._inject_snapshot_for_tests(good_b)
        stop.set()
        t.join(timeout=1.0)
        # Either bool is fine; the goal is no crash + only valid bool values.
        self.assertTrue(all(isinstance(v, bool) for v in results))


class TestMalformedResponse(unittest.TestCase):
    """9. Malformed/missing executor section → ValueError → fail-closed retain."""

    def test_missing_executor_raises(self):
        with self.assertRaises(ValueError):
            ExecutorConfigCache._parse_response({"config": {}, "version": 1})

    def test_non_dict_raises(self):
        with self.assertRaises(ValueError):
            ExecutorConfigCache._parse_response("not a dict")

    def test_malformed_falls_back_after_init(self):
        cache = ExecutorConfigCache()
        good = ExecutorRuntimeConfig(shadow_mode=False, config_version=5, fetched_at_ms=1)
        with patch.object(cache, "_fetch_via_ipc_blocking", return_value=good):
            cache._poll_once()
        self.assertFalse(cache.get().shadow_mode)
        with patch.object(
            cache, "_fetch_via_ipc_blocking",
            side_effect=ValueError("missing executor"),
        ):
            cache._poll_once()
        # Retained previous good shadow=False (post-init graceful degrade).
        self.assertFalse(cache.get().shadow_mode)


class TestModuleSingleton(unittest.TestCase):
    """10. get_executor_config_cache() returns the same instance."""

    def setUp(self):
        ecc_mod._reset_for_tests()

    def tearDown(self):
        ecc_mod._reset_for_tests()

    def test_singleton_dedup(self):
        a = get_executor_config_cache()
        b = get_executor_config_cache()
        self.assertIs(a, b)

    def test_reset_for_tests_drops_singleton(self):
        a = get_executor_config_cache()
        ecc_mod._reset_for_tests()
        b = get_executor_config_cache()
        self.assertIsNot(a, b)


# ═══════════════════════════════════════════════════════════════════════════════
# W-AUDIT-9 T3 — graduated canary stage-aware tests
# AMD-2026-05-09-03 §2.1 / §2.2 / §4.4 + TODO v19 §5 invariant 9
# ═══════════════════════════════════════════════════════════════════════════════


class TestCanaryStageEnum(unittest.TestCase):
    """11. ``CanaryStage.from_raw`` 解析所有合法 / 異常輸入。

    invariant 9：任何不可解析輸入 → SHADOW（**不是** PAPER_SINGLE_COHORT）。
    """

    def test_canary_stage_int_in_range(self):
        """合法整數 0..=4 → 對應 enum 成員。"""
        self.assertEqual(CanaryStage.from_raw(0), CanaryStage.SHADOW)
        self.assertEqual(CanaryStage.from_raw(1), CanaryStage.PAPER_SINGLE_COHORT)
        self.assertEqual(CanaryStage.from_raw(2), CanaryStage.DEMO_SINGLE_COHORT)
        self.assertEqual(CanaryStage.from_raw(3), CanaryStage.DEMO_FULL_UNIVERSE)
        self.assertEqual(CanaryStage.from_raw(4), CanaryStage.LIVE_PENDING)

    def test_canary_stage_string_int(self):
        """字串「0」..「4」可解析（IPC payload 容錯）。"""
        self.assertEqual(CanaryStage.from_raw("0"), CanaryStage.SHADOW)
        self.assertEqual(CanaryStage.from_raw("3"), CanaryStage.DEMO_FULL_UNIVERSE)

    def test_canary_stage_enum_passthrough(self):
        """傳入 CanaryStage 實例 → 原值 passthrough。"""
        self.assertEqual(
            CanaryStage.from_raw(CanaryStage.DEMO_SINGLE_COHORT),
            CanaryStage.DEMO_SINGLE_COHORT,
        )

    def test_canary_stage_none_fails_closed(self):
        """invariant 9：None → Stage 0（**不是** Stage 1）。"""
        self.assertEqual(CanaryStage.from_raw(None), CanaryStage.SHADOW)

    def test_canary_stage_out_of_range_fails_closed(self):
        """invariant 9：5 / -1 / 100 等 out-of-range → Stage 0。"""
        self.assertEqual(CanaryStage.from_raw(5), CanaryStage.SHADOW)
        self.assertEqual(CanaryStage.from_raw(-1), CanaryStage.SHADOW)
        self.assertEqual(CanaryStage.from_raw(100), CanaryStage.SHADOW)

    def test_canary_stage_invalid_type_fails_closed(self):
        """invariant 9：dict / list / 隨機字串 → Stage 0。"""
        self.assertEqual(CanaryStage.from_raw("abc"), CanaryStage.SHADOW)
        self.assertEqual(CanaryStage.from_raw({}), CanaryStage.SHADOW)
        self.assertEqual(CanaryStage.from_raw([]), CanaryStage.SHADOW)

    def test_canary_stage_intenum_ordering(self):
        """IntEnum 排序：SHADOW < PAPER < DEMO_SINGLE < DEMO_FULL < LIVE_PENDING。"""
        self.assertLess(CanaryStage.SHADOW, CanaryStage.PAPER_SINGLE_COHORT)
        self.assertLess(
            CanaryStage.PAPER_SINGLE_COHORT, CanaryStage.DEMO_SINGLE_COHORT,
        )
        self.assertLess(
            CanaryStage.DEMO_SINGLE_COHORT, CanaryStage.DEMO_FULL_UNIVERSE,
        )
        self.assertLess(
            CanaryStage.DEMO_FULL_UNIVERSE, CanaryStage.LIVE_PENDING,
        )


class TestCanaryStageParseResponse(unittest.TestCase):
    """12. ``_parse_response`` stage / cohort / 觀察期欄位解析。"""

    @staticmethod
    def _make_resp(executor: dict, version: int = 1) -> dict:
        return {"config": {"executor": executor}, "version": version}

    def test_canary_stage_parsed_from_response(self):
        """合法 canary_stage=2 + cohort + 觀察期 → snapshot 正確攜帶。"""
        resp = self._make_resp({
            "shadow_mode": False,
            "canary_stage": 2,
            "canary_cohort": {
                "strategy": "bb_breakout",
                "symbol": "BTCUSDT",
                "environment": "demo",
            },
            "stage_entered_at_ms": 1735000000000,
            "observation_period_ms": 14 * 24 * 3600 * 1000,
            "max_position_pct": 0.07,
        })
        snap = ExecutorConfigCache._parse_response(resp)
        self.assertEqual(snap.canary_stage, CanaryStage.DEMO_SINGLE_COHORT)
        self.assertFalse(snap.shadow_mode)  # stage > 0 投影為 False
        self.assertIsNotNone(snap.canary_cohort)
        self.assertEqual(snap.canary_cohort.strategy, "bb_breakout")
        self.assertEqual(snap.canary_cohort.symbol, "BTCUSDT")
        self.assertEqual(snap.canary_cohort.environment, "demo")
        self.assertEqual(snap.stage_entered_at_ms, 1735000000000)

    def test_canary_stage_missing_falls_back_to_shadow(self):
        """canary_stage 欄位缺失 + shadow_mode=true → Stage 0 backward-compat。

        legacy config 場景：shadow_mode=true 不變，canary_stage 自動 fall back
        SHADOW（與 legacy 行為等同）。
        """
        resp = self._make_resp({"shadow_mode": True})
        snap = ExecutorConfigCache._parse_response(resp)
        self.assertEqual(snap.canary_stage, CanaryStage.SHADOW)
        self.assertTrue(snap.shadow_mode)

    def test_canary_stage_out_of_range_fails_closed(self):
        """canary_stage=99 → Stage 0（不是 Stage 1）。"""
        resp = self._make_resp({"shadow_mode": False, "canary_stage": 99})
        snap = ExecutorConfigCache._parse_response(resp)
        self.assertEqual(snap.canary_stage, CanaryStage.SHADOW)
        # stage=0 投影 → shadow_mode=True（不論 raw shadow_mode 為何）
        self.assertTrue(snap.shadow_mode)

    def test_shadow_projection_overrides_legacy_field(self):
        """legacy shadow_mode=true 配 canary_stage=2 → stage 為 SoT，shadow=False。

        AMD §4.4：shadow_mode 以 stage projection 為主，避免兩欄矛盾。
        """
        resp = self._make_resp({"shadow_mode": True, "canary_stage": 2})
        snap = ExecutorConfigCache._parse_response(resp)
        self.assertEqual(snap.canary_stage, CanaryStage.DEMO_SINGLE_COHORT)
        self.assertFalse(snap.shadow_mode)


class TestCanaryStageBackwardCompatReject(unittest.TestCase):
    """13. backward-compat reject：legacy shadow=false 無 canary_stage → Stage 0。"""

    def test_legacy_shadow_false_without_canary_rejects_to_shadow(self):
        """AMD §4.4：legacy `shadow_mode=false` 但無 `canary_stage` 欄位 → Stage 0。"""
        resp = {
            "config": {"executor": {"shadow_mode": False}},
            "version": 1,
        }
        with self.assertLogs(ecc_mod.logger, level="WARNING") as captured:
            snap = ExecutorConfigCache._parse_response(resp)
        self.assertEqual(snap.canary_stage, CanaryStage.SHADOW)
        self.assertTrue(snap.shadow_mode)
        # log 必有 backward-compat reject hint
        self.assertTrue(
            any("backward-compat reject" in msg for msg in captured.output),
            f"log 中未見 backward-compat reject hint: {captured.output}",
        )

    def test_legacy_shadow_false_with_explicit_stage_zero_logs_conflict(self):
        """legacy `shadow_mode=false` + `canary_stage=0` → 兩欄矛盾，log + Stage 0。"""
        resp = {
            "config": {"executor": {"shadow_mode": False, "canary_stage": 0}},
            "version": 1,
        }
        with self.assertLogs(ecc_mod.logger, level="WARNING") as captured:
            snap = ExecutorConfigCache._parse_response(resp)
        self.assertEqual(snap.canary_stage, CanaryStage.SHADOW)
        self.assertTrue(snap.shadow_mode)
        self.assertTrue(
            any("conflicts with canary_stage=0" in msg for msg in captured.output),
            f"log 中未見矛盾 hint: {captured.output}",
        )


class TestCanaryStageProvider(unittest.TestCase):
    """14. ``canary_stage_provider()`` exception → Stage 0；read live snapshot。"""

    def test_provider_reads_current_stage(self):
        """provider 讀取當前 snapshot 的 canary_stage。"""
        cache = ExecutorConfigCache()
        provider = cache.canary_stage_provider()
        # 初始 fail-closed Stage 0
        self.assertEqual(provider(), CanaryStage.SHADOW)
        # 注入 stage 1 snapshot
        cache._inject_snapshot_for_tests(
            ExecutorRuntimeConfig(
                shadow_mode=False,
                canary_stage=CanaryStage.PAPER_SINGLE_COHORT,
                config_version=1,
                fetched_at_ms=1,
            )
        )
        self.assertEqual(provider(), CanaryStage.PAPER_SINGLE_COHORT)
        # 注入 stage 3
        cache._inject_snapshot_for_tests(
            ExecutorRuntimeConfig(
                shadow_mode=False,
                canary_stage=CanaryStage.DEMO_FULL_UNIVERSE,
                config_version=2,
                fetched_at_ms=2,
            )
        )
        self.assertEqual(provider(), CanaryStage.DEMO_FULL_UNIVERSE)

    def test_provider_engine_mismatch_fails_closed(self):
        """跨 engine fetch 失敗 → fail-closed Stage 0（**不是** Stage 1）。"""
        cache = ExecutorConfigCache(engine="paper")
        provider = cache.canary_stage_provider()
        with patch.object(
            cache,
            "_fetch_via_ipc_blocking",
            side_effect=ConnectionError("ipc down"),
        ):
            self.assertEqual(provider("demo"), CanaryStage.SHADOW)

    def test_provider_engine_match_returns_snapshot_stage(self):
        """engine 匹配 self._engine → 直接讀本地 snapshot stage。"""
        cache = ExecutorConfigCache(engine="paper")
        cache._inject_snapshot_for_tests(
            ExecutorRuntimeConfig(
                shadow_mode=False,
                canary_stage=CanaryStage.DEMO_SINGLE_COHORT,
                config_version=1,
                fetched_at_ms=1,
            )
        )
        provider = cache.canary_stage_provider()
        self.assertEqual(provider("paper"), CanaryStage.DEMO_SINGLE_COHORT)
        self.assertEqual(provider(None), CanaryStage.DEMO_SINGLE_COHORT)


class TestCanaryStageProviderShadowProjection(unittest.TestCase):
    """15. backward-compat shadow_mode_provider lambda：Stage 0 → True / ≥ 1 → False。"""

    def test_shadow_provider_stage_zero_returns_true(self):
        """Stage 0 → shadow_mode_provider → True。"""
        cache = ExecutorConfigCache()
        # 默認初始 Stage 0
        provider = cache.shadow_mode_provider()
        self.assertTrue(provider())

    def test_shadow_provider_stage_one_returns_false(self):
        """Stage 1 → shadow_mode_provider → False。"""
        cache = ExecutorConfigCache()
        cache._inject_snapshot_for_tests(
            ExecutorRuntimeConfig(
                shadow_mode=False,
                canary_stage=CanaryStage.PAPER_SINGLE_COHORT,
                config_version=1,
                fetched_at_ms=1,
            )
        )
        provider = cache.shadow_mode_provider()
        self.assertFalse(provider())

    def test_shadow_provider_stage_two_returns_false(self):
        """Stage 2 → shadow_mode_provider → False。"""
        cache = ExecutorConfigCache()
        cache._inject_snapshot_for_tests(
            ExecutorRuntimeConfig(
                shadow_mode=False,
                canary_stage=CanaryStage.DEMO_SINGLE_COHORT,
                config_version=1,
                fetched_at_ms=1,
            )
        )
        provider = cache.shadow_mode_provider()
        self.assertFalse(provider())

    def test_shadow_provider_higher_stages_return_false(self):
        """Stage 3/4 → shadow_mode_provider → False。"""
        cache = ExecutorConfigCache()
        for stage in (CanaryStage.DEMO_FULL_UNIVERSE, CanaryStage.LIVE_PENDING):
            cache._inject_snapshot_for_tests(
                ExecutorRuntimeConfig(
                    shadow_mode=False,
                    canary_stage=stage,
                    config_version=1,
                    fetched_at_ms=1,
                )
            )
            provider = cache.shadow_mode_provider()
            self.assertFalse(provider(), f"stage={stage}")


class TestCanaryStageBackwardCompatLegacyConfig(unittest.TestCase):
    """16. backward-compat：legacy `shadow_mode=true` config（無 canary_stage）→ Stage 0。"""

    def test_legacy_shadow_true_implies_stage_zero(self):
        """legacy config（pre W-AUDIT-9）只有 shadow_mode=true → Stage 0 + shadow=True。"""
        resp = {
            "config": {
                "executor": {
                    "shadow_mode": True,
                    "max_position_pct": 0.05,
                },
            },
            "version": 1,
        }
        snap = ExecutorConfigCache._parse_response(resp)
        self.assertEqual(snap.canary_stage, CanaryStage.SHADOW)
        self.assertTrue(snap.shadow_mode)
        # shadow_mode_provider lambda 對 legacy config 仍回 True
        cache = ExecutorConfigCache()
        cache._inject_snapshot_for_tests(snap)
        self.assertTrue(cache.shadow_mode_provider()())

    def test_legacy_config_via_full_polling_path(self):
        """模擬完整 polling path：legacy IPC payload → Stage 0 snapshot。"""
        cache = ExecutorConfigCache()
        legacy_resp = {
            "config": {"executor": {"shadow_mode": True}},
            "version": 5,
        }
        with patch.object(
            cache, "_fetch_via_ipc_blocking",
            return_value=ExecutorConfigCache._parse_response(legacy_resp),
        ):
            cache._poll_once()
        snap = cache.get()
        self.assertTrue(cache.is_initialized())
        self.assertEqual(snap.canary_stage, CanaryStage.SHADOW)
        self.assertTrue(snap.shadow_mode)


if __name__ == "__main__":
    unittest.main()
