"""
G8-01-FUP-LOSSES-WIRING sanity tests — Analyst → Strategist consecutive_losses
==============================================================================

MODULE_NOTE (中文):
  本檔僅驗證 G8-01-FUP-LOSSES-WIRING P2 直接修復的兩個結構性 gap，**不**承擔
  W2 ≥85% line cov 或 W3 integration ≥5 case：

  - **GAP-A**：``StrategistAgent._stats["consecutive_losses"]`` 過往無人 set →
    ``tick_cognitive_modulator`` 永遠以 0 餵 modulator → modulator state 卡 base
    （RFC §3.1 acknowledged limitation）。本 fix 讓 ``record_trade_outcome``
    正確以 net_pnl 號分類更新計數器（>0 reset / <=0 +1）。
  - **GAP-B**：``AnalystAgent.analyze_trade`` 無下游 hook → Strategist 永不知
    交易結果。本 fix 加 ``set_strategist_loss_callback`` + 在 analyze_trade
    內 fail-open 觸發 callback，使 IPC trade outcome 真正傳播到 Strategist。

  + 一條端到端測試：連續 N 次 net_pnl<=0 後 ``tick_cognitive_modulator`` 真正
  推進 modulator state（``confidence_floor`` ≠ ctor base）—— 證 RFC §3.1
  acknowledged limitation 確實閉合。

MODULE_NOTE (English):
  Sanity tests verifying ONLY the two structural gaps G8-01-FUP-LOSSES-WIRING
  fixes; the full W2/W3 coverage suite belongs to subsequent waves:

  - **GAP-A**: ``StrategistAgent._stats["consecutive_losses"]`` had no setter
    in production → ``tick_cognitive_modulator`` always fed 0 to the modulator
    → modulator state stuck at base (RFC §3.1 acknowledged limitation). Fix
    adds ``record_trade_outcome`` updating the counter by net_pnl sign
    (>0 reset / <=0 increment).
  - **GAP-B**: ``AnalystAgent.analyze_trade`` had no downstream hook →
    Strategist never observed trade outcomes. Fix adds
    ``set_strategist_loss_callback`` + fail-open invocation inside
    analyze_trade, propagating IPC-driven trade outcomes to Strategist.

  + One end-to-end test: after N consecutive net_pnl<=0 outcomes
    ``tick_cognitive_modulator`` actually advances modulator state
    (``confidence_floor`` ≠ ctor base) — proving RFC §3.1 limitation closed.

Refs:
  - PA RFC ``docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-27--g8_01_cognitive_e2e_design.md`` §3.1
  - W1 sanity tests ``test_strategist_cognitive_w1_fix.py`` (still green)
  - feedback_no_dead_params memory entry
"""

from __future__ import annotations

import os
import sys
import unittest

# Ensure ``app`` is importable when run from srv root or tests/ /
# 從 srv root 或 tests/ 跑時保證可 import ``app``。
_test_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(_test_dir)
if _control_api_dir not in sys.path:
    sys.path.insert(0, _control_api_dir)

from app.analyst_agent import AnalystAgent, AnalystConfig, TradeRecord
from app.strategist_agent import StrategistAgent, StrategistConfig
from app.strategist_cognitive import tick_cognitive_modulator

# Direct import of the production class — no stub / mock for the modulator
# itself; the W1 fix and this FUP both must work with the real instance.
# 直接 import production class —— W1 fix 與本 FUP 都必須對真實 instance 生效。
from program_code.local_model_tools.cognitive_modulator import CognitiveModulator


def _make_strategist() -> StrategistAgent:
    """Build a minimal running StrategistAgent (shadow mode).
    建立最小化運行中的 StrategistAgent（shadow 模式）。"""
    agent = StrategistAgent(
        config=StrategistConfig(
            shadow=True,
            min_relevance=0.0,
            heuristic_min_relevance=0.0,
            heuristic_min_freshness=9999,
            max_intel_age_seconds=10**9,
        ),
        cost_tracker=None,
    )
    agent.start()
    return agent


def _make_analyst() -> AnalystAgent:
    """Build a minimal running AnalystAgent (no Ollama, no learning gate).
    建立最小化運行中的 AnalystAgent（無 Ollama、無 learning gate）。"""
    agent = AnalystAgent(
        config=AnalystConfig(),
        message_bus=None,
        ollama_client=None,
        learning_tier_gate=None,
        audit_callback=None,
    )
    agent.start()
    return agent


def _make_record(*, pnl: float, fees: float = 0.0, strategy: str = "test_strat") -> TradeRecord:
    """Build a TradeRecord with a specific net_pnl signature.
    建立指定 net_pnl 的 TradeRecord。"""
    return TradeRecord(
        trade_id="t",
        symbol="BTCUSDT",
        strategy=strategy,
        direction="long",
        entry_price=100.0,
        exit_price=100.0 + pnl,
        pnl=pnl,
        hold_ms=60_000,
        regime="ranging",
        timestamp_ms=0,
        fees_paid=fees,
        param_snapshot={},
    )


class TestRecordTradeOutcomeCounterSemantics(unittest.TestCase):
    """GAP-A：``record_trade_outcome`` 對 net_pnl 號的計數語意正確。
    Loss / breakeven → +1；win → reset to 0。"""

    def test_loss_increments_consecutive_losses(self):
        """net_pnl<0 → ``consecutive_losses`` +1.
        net_pnl<0 → ``consecutive_losses`` +1。"""
        agent = _make_strategist()
        self.assertEqual(agent._stats["consecutive_losses"], 0)

        agent.record_trade_outcome(net_pnl=-3.0)
        self.assertEqual(agent._stats["consecutive_losses"], 1)

        agent.record_trade_outcome(net_pnl=-7.5)
        self.assertEqual(agent._stats["consecutive_losses"], 2)

        agent.record_trade_outcome(net_pnl=-0.01)
        self.assertEqual(agent._stats["consecutive_losses"], 3)

        # Diagnostic counter advances on every outcome.
        # 診斷計數器每筆都推進。
        self.assertEqual(agent._stats["trade_outcomes_observed"], 3)

    def test_win_resets_consecutive_losses_to_zero(self):
        """net_pnl>0 → ``consecutive_losses`` 重置為 0。
        net_pnl>0 → ``consecutive_losses`` reset to 0."""
        agent = _make_strategist()

        # Build up a streak first / 先累積一段虧損連勝
        for _ in range(5):
            agent.record_trade_outcome(net_pnl=-1.0)
        self.assertEqual(agent._stats["consecutive_losses"], 5)

        # Single win → reset / 一次勝利 → 歸零
        agent.record_trade_outcome(net_pnl=+0.5)
        self.assertEqual(agent._stats["consecutive_losses"], 0)

        # And subsequent loss begins a new streak from 1.
        # 接下來再輸從 1 開始計。
        agent.record_trade_outcome(net_pnl=-0.5)
        self.assertEqual(agent._stats["consecutive_losses"], 1)

    def test_breakeven_treated_as_loss(self):
        """net_pnl == 0（fee 吃光）→ 視為輸 → +1（per fix docstring §5/§13）。
        net_pnl == 0 (fee-eaten) → counted as loss → +1."""
        agent = _make_strategist()
        agent.record_trade_outcome(net_pnl=0.0)
        self.assertEqual(agent._stats["consecutive_losses"], 1)


class TestAnalystToStrategistCallbackWiring(unittest.TestCase):
    """GAP-B：``AnalystAgent.analyze_trade`` → ``record_trade_outcome`` 接線
    + fail-open 行為驗證。"""

    def test_analyze_trade_invokes_strategist_callback_with_net_pnl(self):
        """``analyze_trade(record)`` 觸發 callback、傳入 ``record.net_pnl``。
        ``analyze_trade(record)`` fires callback with ``record.net_pnl``."""
        analyst = _make_analyst()
        strategist = _make_strategist()

        # Mirror strategy_wiring.py wiring shape exactly.
        # 完全鏡像 strategy_wiring.py 的接線形狀。
        analyst.set_strategist_loss_callback(
            lambda net_pnl: strategist.record_trade_outcome(net_pnl)
        )

        # Loss with fees: pnl=-2, fees=1 → net_pnl=-3 (loss → +1).
        # 帶 fees 的虧損：pnl=-2, fees=1 → net_pnl=-3（輸 → +1）。
        analyst.analyze_trade(_make_record(pnl=-2.0, fees=1.0))
        self.assertEqual(strategist._stats["consecutive_losses"], 1)

        # Win after fees: pnl=+5, fees=1 → net_pnl=+4 → reset.
        # 扣 fees 後仍贏：pnl=+5, fees=1 → net_pnl=+4 → reset。
        analyst.analyze_trade(_make_record(pnl=+5.0, fees=1.0))
        self.assertEqual(strategist._stats["consecutive_losses"], 0)

        # Apparent win but fee-eaten to breakeven: pnl=+1, fees=1 → net_pnl=0 → loss.
        # 表面贏但 fee 吃成平手：pnl=+1, fees=1 → net_pnl=0 → 算輸。
        analyst.analyze_trade(_make_record(pnl=+1.0, fees=1.0))
        self.assertEqual(strategist._stats["consecutive_losses"], 1)

        # Diagnostic counter on Strategist side proves callback fired 3 times.
        # Strategist 端診斷計數器證 callback 真的呼了 3 次。
        self.assertEqual(strategist._stats["trade_outcomes_observed"], 3)
        # Analyst's own stats also advance — proves no early-return regression.
        # Analyst 自身 stats 也推進 —— 證沒因接線改動造成提早 return regression。
        self.assertEqual(analyst._stats["trades_analyzed"], 3)

    def test_callback_failure_is_fail_open_and_does_not_break_analyst(self):
        """Callback raise → analyst hot path 不崩、stats 仍累積。
        Callback raise → analyst hot path不崩，stats 仍累積。"""
        analyst = _make_analyst()

        def _bad_callback(_net_pnl: float) -> None:
            raise RuntimeError("simulated downstream consumer failure")

        analyst.set_strategist_loss_callback(_bad_callback)

        # Should not raise out of analyze_trade.
        # 應不從 analyze_trade 拋出。
        try:
            analyst.analyze_trade(_make_record(pnl=-1.0))
            analyst.analyze_trade(_make_record(pnl=+1.0))
        except Exception as exc:  # pragma: no cover — fail-open guard
            self.fail(
                f"analyze_trade surfaced callback exception (fail-open broken): {exc}"
            )

        # Analyst's own stats still advance — proves callback failure is isolated.
        # Analyst 自身 stats 仍推進 —— 證 callback 失敗被隔離。
        self.assertEqual(analyst._stats["trades_analyzed"], 2)
        self.assertEqual(analyst._stats["errors"], 0)

    def test_no_callback_wired_is_safe_noop(self):
        """未注入 callback → analyze_trade 正常運行（向後兼容驗證）。
        No callback → analyze_trade runs normally (backward compatibility check)."""
        analyst = _make_analyst()
        # No setter call — _strategist_loss_callback stays None.
        # 不呼 setter — _strategist_loss_callback 維持 None。

        try:
            analyst.analyze_trade(_make_record(pnl=-1.0))
        except Exception as exc:  # pragma: no cover — defensive guard
            self.fail(f"analyze_trade raised when callback is None: {exc}")

        self.assertEqual(analyst._stats["trades_analyzed"], 1)


class TestEndToEndModulatorAdvancesUnderLossStreak(unittest.TestCase):
    """RFC §3.1 acknowledged limitation 真正閉合驗證：
    Analyst → Strategist callback wired + 連續 loss + ``tick_cognitive_modulator``
    → CognitiveModulator state 真實推進（confidence_floor 上移、不再卡 base）。"""

    def test_modulator_state_actually_advances_after_loss_streak(self):
        """連續 N>=5 loss + tick → modulator confidence_floor > ctor base。
        ≥5 consecutive losses + tick → modulator floor advances above base."""
        analyst = _make_analyst()
        strategist = _make_strategist()
        modulator = CognitiveModulator()
        strategist.set_cognitive_modulator(modulator)

        # Wire as production does / 按 production 接線
        analyst.set_strategist_loss_callback(
            lambda net_pnl: strategist.record_trade_outcome(net_pnl)
        )

        # Capture base values BEFORE any update.
        # 在任何 update 前抓取 base 值。
        base = modulator.get_all_params()
        base_floor = base["confidence_floor"]
        self.assertEqual(base["update_count"], 0)

        # Feed 5 consecutive losses through Analyst → Strategist path.
        # 經 Analyst → Strategist 路徑投入 5 次連續虧損。
        for _ in range(5):
            analyst.analyze_trade(_make_record(pnl=-1.0))
        self.assertEqual(strategist._stats["consecutive_losses"], 5)

        # Now manually drive a tick (in production, _handle_intel does this every
        # _COGNITIVE_TICK_INTERVAL=10 intel events; here we test the unit cycle).
        # 手動觸發一次 tick（production 中由 _handle_intel 每 N=10 個 intel 觸發；
        # 此處驗證單元 cycle）。
        tick_cognitive_modulator(strategist)

        post = modulator.get_all_params()
        # update_count must have advanced — modulator no longer dead.
        # update_count 必須推進 —— modulator 不再 dead。
        self.assertGreaterEqual(post["update_count"], 1)
        # confidence_floor must be STRICTLY ABOVE base — 5 consecutive losses
        # is a clear stress signal, modulator should tighten the threshold.
        # confidence_floor 必須嚴格高於 base —— 5 連虧是明確壓力信號，
        # modulator 應收緊門檻。
        self.assertGreater(
            post["confidence_floor"], base_floor,
            f"modulator confidence_floor did not advance above base "
            f"({post['confidence_floor']} <= {base_floor}) — "
            f"FUP wiring failed to deliver non-zero consecutive_losses input "
            f"/ modulator confidence_floor 未超過 base，FUP 接線未成功傳遞非零 "
            f"consecutive_losses 輸入",
        )

    def test_win_streak_does_not_advance_floor_above_base(self):
        """連勝 → consecutive_losses=0 → modulator 不收緊門檻（對照組）。
        Win streak → consecutive_losses=0 → modulator floor not tightened (control)."""
        analyst = _make_analyst()
        strategist = _make_strategist()
        modulator = CognitiveModulator()
        strategist.set_cognitive_modulator(modulator)

        analyst.set_strategist_loss_callback(
            lambda net_pnl: strategist.record_trade_outcome(net_pnl)
        )

        base = modulator.get_all_params()
        base_floor = base["confidence_floor"]

        # 5 wins → consecutive_losses stays at 0
        # 5 連勝 → consecutive_losses 維持 0
        for _ in range(5):
            analyst.analyze_trade(_make_record(pnl=+1.0))
        self.assertEqual(strategist._stats["consecutive_losses"], 0)

        tick_cognitive_modulator(strategist)
        post = modulator.get_all_params()

        # update_count still advances (tick fired) — proves the chain ran.
        # update_count 仍推進（tick 有觸發）—— 證 chain 跑了。
        self.assertGreaterEqual(post["update_count"], 1)
        # But confidence_floor should NOT exceed base (no loss-stress signal).
        # 但 confidence_floor 不應超過 base（無虧損壓力信號）。
        self.assertLessEqual(
            post["confidence_floor"], base_floor + 1e-9,
            f"modulator floor moved above base under win streak "
            f"({post['confidence_floor']} > {base_floor}) — "
            f"unexpected stress reaction / 連勝下 modulator floor 升高，異常",
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
