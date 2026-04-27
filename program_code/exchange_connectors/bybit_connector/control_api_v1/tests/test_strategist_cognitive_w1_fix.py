"""
G8-01 W1 sanity tests — CognitiveModulator dead-path production fix
====================================================================

MODULE_NOTE (中文):
  本檔僅驗證 G8-01 W1 production fix 直接修復的兩個 BLOCKER bug，**不**承擔
  ≥85% line cov 的完整覆蓋（屬 W2 工作組責任）：

  - **BUG-A**：``strategist_cognitive._apply_cognitive_modulation`` 與
    ``strategist_edge_eval._build_prompt_context`` 原本呼叫不存在的
    ``modulator.get_current_params()``，AttributeError 被 try/except 靜默吞 →
    cognitive 門檻永遠回退 default。Fix 後改呼真實 API ``get_all_params()``，
    試 invoke 不再 raise，回傳 dict 含 5 鍵。
  - **BUG-B**：``CognitiveModulator.update(...)`` production caller = 0，
    modulator 永卡在 ctor base value（``update_count=0``）。Fix 後
    ``StrategistAgent._handle_intel`` 每 N=10 個 intel 觸發
    ``tick_cognitive_modulator(self)``，``update_count`` 隨 tick 推進。

  W2 ≥85% cov + W3 integration ≥5 case 留給後續 wave。

MODULE_NOTE (English):
  Sanity tests verifying ONLY the two BLOCKER bugs G8-01 W1 fixes; the full
  ≥85% line coverage suite belongs to W2:

  - **BUG-A**: ``_apply_cognitive_modulation`` + ``_build_prompt_context`` used
    to call a nonexistent ``modulator.get_current_params()``; AttributeError was
    silently swallowed → cognitive thresholds permanently returned defaults.
    Post-fix the real API ``get_all_params()`` is called and the returned dict
    contains the 5 expected keys.
  - **BUG-B**: ``CognitiveModulator.update(...)`` had zero production callers,
    so the modulator was forever at ctor base values (``update_count=0``).
    Post-fix ``StrategistAgent._handle_intel`` invokes
    ``tick_cognitive_modulator(self)`` every N=10 intel events, so
    ``update_count`` advances.

  W2 ≥85% line cov + W3 integration ≥5 case are deferred to subsequent waves.

Refs:
  - PA RFC ``docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-27--g8_01_cognitive_e2e_design.md`` §3.1
  - feedback_no_dead_params memory entry
"""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock

# Ensure ``app`` is importable when run from srv root or tests/ /
# 從 srv root 或 tests/ 跑時保證可 import ``app``。
_test_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(_test_dir)
if _control_api_dir not in sys.path:
    sys.path.insert(0, _control_api_dir)

from app.strategist_agent import (
    StrategistAgent,
    StrategistConfig,
    _COGNITIVE_TICK_INTERVAL,
)
from app.strategist_cognitive import (
    _apply_cognitive_modulation,
    tick_cognitive_modulator,
)
from app.multi_agent_framework import (
    AgentMessage,
    AgentRole,
    DataQualityLevel,
    IntelObject,
    MessageType,
    SentimentScore,
)

# Direct import of the production class — no stub / mock for the modulator
# itself; W1 fix must work with the real instance.
# 直接 import production class — 不替 modulator 本身做 stub / mock；W1 fix
# 必須對真實 instance 生效。
from program_code.local_model_tools.cognitive_modulator import CognitiveModulator


def _make_strategist(cost_tracker=None) -> StrategistAgent:
    """Build a minimal running StrategistAgent (shadow mode, lenient relevance).
    建立最小化運行中的 StrategistAgent（shadow 模式、寬鬆 relevance）。"""
    agent = StrategistAgent(
        config=StrategistConfig(
            shadow=True,
            min_relevance=0.0,            # accept any relevance / 接受任何相關度
            heuristic_min_relevance=0.0,
            heuristic_min_freshness=9999,
            max_intel_age_seconds=10**9,  # effectively disable age gate / 形同關閉年齡門
        ),
        cost_tracker=cost_tracker,
    )
    agent.start()
    return agent


def _make_intel_message() -> AgentMessage:
    """Build a minimal valid INTEL_OBJECT AgentMessage.
    建立最小化有效 INTEL_OBJECT AgentMessage。"""
    intel = IntelObject(
        source="g8_01_w1_test",
        content="sanity",
        symbols=["BTCUSDT"],
        data_quality=DataQualityLevel.FACT,
        sentiment=SentimentScore.POSITIVE,
        relevance_score=0.5,
        freshness_seconds=1,
        metadata={},
    )
    return AgentMessage(
        sender=AgentRole.SCOUT,
        receiver=AgentRole.STRATEGIST,
        message_type=MessageType.INTEL_OBJECT,
        priority=3,
        payload=intel.to_dict(),
    )


class TestG801W1BugAFix(unittest.TestCase):
    """BUG-A：``get_current_params`` rename → ``get_all_params``.
    Method-name mismatch 修復後，``_apply_cognitive_modulation`` 真實取到
    modulator 參數，不再回退 default。"""

    def test_apply_cognitive_modulation_uses_real_modulator_value(self):
        """Real CognitiveModulator → ``_apply_cognitive_modulation`` 回真實 floor /
        not the bypass default.
        真實 CognitiveModulator 注入後，``_apply_cognitive_modulation`` 必須
        回 modulator 的 confidence_floor，而非 bypass default。
        """
        agent = _make_strategist()
        modulator = CognitiveModulator()

        # Drive the modulator off ctor base so floor != min_confidence default
        # (max single-factor 0.05 from "overtrading" → EMA(0.3) on base 0.60
        # gives 0.6 + 0.3 * 0.05 = 0.615, rounded to 0.615 / 0.6150).
        # 把 modulator 推離 ctor base，使 floor 與 default 可分辨。
        modulator.update(regret_data={"net_regret_direction": "overtrading"})
        agent._cognitive_modulator = modulator

        floor, qty_ceil = _apply_cognitive_modulation(agent, confidence=0.5)

        # Should reflect modulator's get_all_params() — not default
        # min_confidence (StrategistConfig default ~ 0.5) AND not 1.0 default.
        # 應反映 modulator.get_all_params() — 不再是 config default。
        params = modulator.get_all_params()
        self.assertEqual(floor, params["confidence_floor"])
        self.assertEqual(qty_ceil, params["qty_ceiling"])

    def test_get_all_params_does_not_raise(self):
        """Confirm modulator.get_all_params() does NOT raise AttributeError —
        regression guard in case method was ever renamed back.
        確認 ``get_all_params()`` 不 raise — 萬一日後又被 rename，本測立刻紅。"""
        modulator = CognitiveModulator()
        try:
            params = modulator.get_all_params()
        except AttributeError as exc:  # pragma: no cover — defensive guard
            self.fail(f"modulator.get_all_params() raised AttributeError: {exc}")
        self.assertIsInstance(params, dict)
        # Sanity: 5 documented keys present (per CognitiveModulator.get_all_params).
        # 衛生檢查：documented 的 5 個鍵齊備。
        for key in ("confidence_floor", "qty_ceiling", "stoploss_multiplier",
                    "scan_interval_s", "update_count"):
            self.assertIn(key, params)


class TestG801W1BugBFix(unittest.TestCase):
    """BUG-B：``modulator.update(...)`` production caller 從 0 → ≥1。
    驗 ``tick_cognitive_modulator`` 直呼 + ``_handle_intel`` 每 N tick 自動驅動。"""

    def test_tick_cognitive_modulator_increments_update_count(self):
        """Direct tick → ``update_count`` 0 → 1.
        直呼 tick → ``update_count`` 從 0 推進到 1。"""
        agent = _make_strategist()
        modulator = CognitiveModulator()
        agent._cognitive_modulator = modulator

        self.assertEqual(modulator.get_all_params()["update_count"], 0)

        tick_cognitive_modulator(agent)

        self.assertEqual(modulator.get_all_params()["update_count"], 1)

    def test_tick_cognitive_modulator_no_modulator_is_safe_noop(self):
        """No modulator wired → tick is a fast no-op, no exception.
        未注入 modulator → tick 安全 no-op，不 raise。"""
        agent = _make_strategist()
        agent._cognitive_modulator = None
        try:
            tick_cognitive_modulator(agent)
        except Exception as exc:  # pragma: no cover — defensive guard
            self.fail(f"tick_cognitive_modulator raised on None modulator: {exc}")

    def test_handle_intel_drives_modulator_at_tick_interval(self):
        """``_handle_intel`` 每 ``_COGNITIVE_TICK_INTERVAL`` 個 intel 推進
        modulator.update_count 一次。
        Ensures the production hot path actually invokes the tick helper.
        確保 production hot path 真有呼到 tick helper（修 BUG-B 的核心斷言）。
        """
        agent = _make_strategist()
        modulator = CognitiveModulator()
        agent._cognitive_modulator = modulator

        # Feed exactly _COGNITIVE_TICK_INTERVAL intel messages — expect 1 tick.
        # 投遞剛好 _COGNITIVE_TICK_INTERVAL 個 intel — 預期 1 次 tick。
        for _ in range(_COGNITIVE_TICK_INTERVAL):
            agent._handle_intel(_make_intel_message())

        self.assertGreaterEqual(
            modulator.get_all_params()["update_count"],
            1,
            "update_count must advance after _COGNITIVE_TICK_INTERVAL intel "
            "events; if 0 → tick helper not actually invoked from _handle_intel "
            "/ update_count 應在 N 個 intel 後推進；若仍為 0 表示 _handle_intel "
            "未真正呼叫 tick helper。",
        )

    def test_handle_intel_tick_failure_is_fail_soft(self):
        """Modulator raise inside tick → hot path 不崩、stats 仍累積。
        Modulator 在 tick 內 raise → hot path 不崩，stats 仍累積。"""
        agent = _make_strategist()
        bad_modulator = MagicMock()
        bad_modulator.update.side_effect = RuntimeError("simulated modulator failure")
        # Stub get_all_params so the *other* call site (``_apply_cognitive_modulation``)
        # does not also blow up — we are isolating the tick failure path here.
        # Stub get_all_params 避免 _apply_cognitive_modulation 也炸 — 本 test 隔離
        # tick failure path。
        bad_modulator.get_all_params.return_value = {
            "confidence_floor": 0.0,
            "qty_ceiling": 1.0,
            "stoploss_multiplier": 1.0,
            "scan_interval_s": 1800,
            "update_count": 0,
        }
        agent._cognitive_modulator = bad_modulator

        for _ in range(_COGNITIVE_TICK_INTERVAL):
            try:
                agent._handle_intel(_make_intel_message())
            except Exception as exc:  # pragma: no cover — fail-soft guard
                self.fail(f"_handle_intel surfaced modulator exception: {exc}")

        # Confirm tick was attempted at least once (proves hot-path wired up).
        # 確認 tick 至少嘗試 1 次（證 hot path 接線生效）。
        self.assertGreaterEqual(bad_modulator.update.call_count, 1)
        # And intel_received accounting unaffected by modulator failure.
        # 且 intel_received 統計不受 modulator 失敗影響。
        self.assertEqual(
            agent._stats["intel_received"], _COGNITIVE_TICK_INTERVAL,
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
