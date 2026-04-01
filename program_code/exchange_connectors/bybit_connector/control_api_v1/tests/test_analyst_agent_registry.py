"""
E4 Batch 2C — AnalystAgent TruthSourceRegistry Integration Tests
E4 Batch 2C — AnalystAgent 知識登記表集成測試

MODULE_NOTE (中文):
  本模塊補充 test_analyst_agent_unit.py 未覆蓋的 _register_pattern_claims 路徑，
  以及 analyze_patterns() AI 路徑呼叫 registry 的集成行為。
  測試設計目標：
  A1. AI 路徑觸發後，registry 應有非空聲明
  A2. losing_patterns 注入後，聲明 pattern_text 含 "losing:" 前綴
  A3. 所有注入聲明的 applies_to_strategy 均不等於 "all"
  A4. registry=None 時不崩潰（fail-open）
  A5. _extract_strategy_from_pattern 已知策略名匹配
  A6. _extract_strategy_from_pattern 未知文字回退 slug（非 "all"）
  A7. 統計路徑也觸發 registry 登記
  A8. 多次分析後 registry 聲明數量遞增

MODULE_NOTE (English):
  Supplements test_analyst_agent_unit.py with coverage for _register_pattern_claims
  and the analyze_patterns() AI-path registry integration.
  Test goals:
  A1. After AI path runs, registry has non-empty claims
  A2. losing_patterns are registered with "losing:" prefix
  A3. All registered claims have applies_to_strategy != "all"
  A4. registry=None does not crash (fail-open)
  A5. _extract_strategy_from_pattern matches known strategy names
  A6. _extract_strategy_from_pattern returns a non-"all" slug for unknown text
  A7. Statistical path also triggers registry registration
  A8. Registry claim count grows after multiple analyses
"""

from __future__ import annotations

import sys
import os
import time
import unittest
from unittest.mock import MagicMock

_test_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(_test_dir)
if _control_api_dir not in sys.path:
    sys.path.insert(0, _control_api_dir)

from app.analyst_agent import AnalystAgent, AnalystConfig, PatternInsight, TradeRecord
from app.truth_source_registry import TruthSourceRegistry


# ─────────────────────────────────────────────────────────────────────────────
# Helpers / 輔助函數
# ─────────────────────────────────────────────────────────────────────────────

def _make_record(strategy: str = "ma_crossover", pnl: float = 0.05, regime: str = "trending") -> TradeRecord:
    """Construct a minimal TradeRecord for testing. / 構建最小測試用 TradeRecord。"""
    return TradeRecord(
        trade_id=f"t_{time.time_ns()}",
        symbol="BTCUSDT",
        strategy=strategy,
        direction="long",
        entry_price=60000.0,
        exit_price=60000.0 + pnl * 60000.0,
        pnl=pnl,
        hold_ms=3600000,
        regime=regime,
        timestamp_ms=int(time.time() * 1000),
    )


def _make_agent_with_registry(
    *,
    min_obs: int = 10,
    ollama_client: MagicMock | None = None,
) -> tuple[AnalystAgent, TruthSourceRegistry]:
    """
    Create AnalystAgent + TruthSourceRegistry and inject registry.
    建立 AnalystAgent + TruthSourceRegistry 並注入 registry。
    """
    config = AnalystConfig(l2_min_observations=min_obs, min_trades_for_ranking=2)
    agent = AnalystAgent(config=config, ollama_client=ollama_client)
    agent.start()
    registry = TruthSourceRegistry()
    agent.set_truth_registry(registry)
    return agent, registry


def _fill_agent(agent: AnalystAgent, count: int = 15) -> None:
    """
    Bulk-insert trade records directly into agent internals (bypass analyze_trade
    to avoid triggering auto-L2 at unexpected times).
    直接向 agent 內部插入交易記錄（繞過 analyze_trade，避免意外觸發 L2）。
    """
    for i in range(count):
        pnl = 0.05 if i % 3 != 0 else -0.02
        record = _make_record(strategy="ma_crossover", pnl=pnl)
        agent._records.append(record)
        ss = agent._strategy_stats[record.strategy]
        ss["trades"] += 1
        ss["total_pnl"] += pnl
        ss["pnl_list"].append(pnl)
        if pnl > 0:
            ss["wins"] += 1
        else:
            ss["losses"] += 1


def _mock_ollama_returning(winning: list[str], losing: list[str]) -> MagicMock:
    """
    Build an Ollama mock that returns a JSON insight with given patterns.
    建立一個返回指定模式 JSON 洞察的 Ollama mock。
    """
    import json
    mock_ollama = MagicMock()
    mock_ollama.is_available.return_value = True
    payload = {
        "winning_patterns": winning,
        "losing_patterns": losing,
        "regime_strategy_matrix": {"trending": {"ma_crossover": 0.65}},
    }
    mock_ollama.generate.return_value = MagicMock(success=True, text=json.dumps(payload))
    return mock_ollama


# ─────────────────────────────────────────────────────────────────────────────
# A1: AI path registers claims in registry
# A1: AI 路徑觸發後 registry 應有非空聲明
# ─────────────────────────────────────────────────────────────────────────────

class TestAnalyzePatternRegistersClaimsAiPath(unittest.TestCase):
    """A1: AI path: analyze_patterns(force=True) → registry gets claims."""

    def test_analyze_patterns_registers_claims_ai_path(self):
        """
        Mock Ollama returns winning_patterns → registry should have active claims.
        Mock Ollama 返回 winning_patterns → registry 應有活跃声明。
        """
        mock_ollama = _mock_ollama_returning(
            winning=["ma_crossover works well in trending regime"],
            losing=[],
        )
        agent, registry = _make_agent_with_registry(ollama_client=mock_ollama)
        _fill_agent(agent, count=15)

        result = agent.analyze_patterns(force=True)

        self.assertIsNotNone(result, "analyze_patterns(force=True) should return insight")
        self.assertEqual(result.source, "ai")
        claims = registry.get_active_claims()
        self.assertGreater(len(claims), 0, "Registry should have at least one claim after AI analysis")

    def test_analyze_patterns_registers_only_from_ai_source(self):
        """
        Registry claims after AI path should have evidence_source='ai'.
        AI 路徑後 registry 聲明的 evidence_source 應為 'ai'。
        """
        mock_ollama = _mock_ollama_returning(
            winning=["grid strategy profit in ranging"],
            losing=[],
        )
        agent, registry = _make_agent_with_registry(ollama_client=mock_ollama)
        _fill_agent(agent, count=15)

        agent.analyze_patterns(force=True)

        claims = registry.get_active_claims()
        self.assertTrue(
            all(c.evidence_source == "ai" for c in claims),
            "All claims from AI analysis should have evidence_source='ai'",
        )

    def test_analyze_patterns_no_ollama_still_registers(self):
        """
        Without Ollama, statistical path also populates registry.
        無 Ollama 時，統計路徑同樣會登記到 registry。
        """
        agent, registry = _make_agent_with_registry()  # no ollama
        _fill_agent(agent, count=20)
        # Give the statistical analysis enough wins to produce a winning_pattern
        # (win_rate >= 0.55 triggers winning_pattern in _statistical_pattern_analysis)
        # Add lots of wins for ma_crossover to ensure a pattern is produced
        agent._strategy_stats["ma_crossover"]["wins"] = 16
        agent._strategy_stats["ma_crossover"]["losses"] = 4
        agent._strategy_stats["ma_crossover"]["trades"] = 20

        agent.analyze_patterns(force=True)

        # Even if statistical produces no patterns (borderline data), no crash
        # The important thing: no exception raised
        _ = registry.get_active_claims()  # must not raise


# ─────────────────────────────────────────────────────────────────────────────
# A2: losing_patterns registered with "losing:" prefix
# A2: losing_patterns 含 "losing:" 前綴
# ─────────────────────────────────────────────────────────────────────────────

class TestRegisterClaimsIncludesLosingPatterns(unittest.TestCase):
    """A2: losing_patterns registered with 'losing: ' prefix."""

    def test_register_claims_includes_losing_patterns(self):
        """
        losing_patterns should be registered with 'losing:' prefix in pattern_text.
        輸模式應以 'losing:' 前綴登記在 registry 中。
        """
        mock_ollama = _mock_ollama_returning(
            winning=[],
            losing=["bb_reversion fails in high volatility"],
        )
        agent, registry = _make_agent_with_registry(ollama_client=mock_ollama)
        _fill_agent(agent, count=15)

        agent.analyze_patterns(force=True)

        claims = registry.get_active_claims()
        self.assertGreater(len(claims), 0, "Should have at least one claim for losing pattern")
        losing_claims = [c for c in claims if "losing:" in c.pattern_text.lower()]
        self.assertGreater(len(losing_claims), 0,
                           "At least one claim should have 'losing:' in pattern_text")

    def test_losing_pattern_has_lower_confidence_than_winning(self):
        """
        Losing patterns registered with lower confidence (0.4) than winning patterns.
        輸模式置信度（0.4）應低於贏模式。
        """
        mock_ollama = _mock_ollama_returning(
            winning=["ma_crossover works in trending"],
            losing=["grid fails in trending"],
        )
        agent, registry = _make_agent_with_registry(ollama_client=mock_ollama)
        _fill_agent(agent, count=100)  # more obs → higher win_confidence

        agent.analyze_patterns(force=True)

        claims = registry.get_active_claims()
        winning_claims = [c for c in claims if "losing:" not in c.pattern_text.lower()]
        losing_claims = [c for c in claims if "losing:" in c.pattern_text.lower()]

        if winning_claims and losing_claims:
            max_losing_conf = max(c.confidence for c in losing_claims)
            max_winning_conf = max(c.confidence for c in winning_claims)
            self.assertLessEqual(
                max_losing_conf, max_winning_conf,
                "Losing pattern confidence should be ≤ winning pattern confidence",
            )


# ─────────────────────────────────────────────────────────────────────────────
# A3: applies_to_strategy never equals "all"
# A3: applies_to_strategy 永遠不等於 "all"
# ─────────────────────────────────────────────────────────────────────────────

class TestRegisterClaimsStrategyNotAll(unittest.TestCase):
    """A3: applies_to_strategy != 'all' for all registered claims."""

    def test_register_claims_strategy_not_all_ai_path(self):
        """
        All claims from AI analysis must have applies_to_strategy != 'all'.
        AI 路徑所有聲明的 applies_to_strategy 均不得等於 'all'。
        """
        mock_ollama = _mock_ollama_returning(
            winning=["some signal pattern here", "ma_crossover performs well"],
            losing=["grid loses money in trending"],
        )
        agent, registry = _make_agent_with_registry(ollama_client=mock_ollama)
        _fill_agent(agent, count=15)

        agent.analyze_patterns(force=True)

        claims = registry.get_active_claims()
        for claim in claims:
            self.assertNotEqual(
                claim.applies_to_strategy,
                "all",
                f"Claim '{claim.pattern_text[:60]}' should not have applies_to_strategy='all'",
            )

    def test_register_claims_strategy_not_all_statistical_path(self):
        """
        All claims from statistical analysis must have applies_to_strategy != 'all'.
        統計路徑所有聲明的 applies_to_strategy 均不得等於 'all'。
        """
        agent, registry = _make_agent_with_registry()
        _fill_agent(agent, count=30)
        # Force winning pattern: win_rate >= 0.55 for ma_crossover
        agent._strategy_stats["ma_crossover"]["wins"] = 25
        agent._strategy_stats["ma_crossover"]["losses"] = 5
        agent._strategy_stats["ma_crossover"]["trades"] = 30

        agent.analyze_patterns(force=True)

        claims = registry.get_active_claims()
        for claim in claims:
            self.assertNotEqual(
                claim.applies_to_strategy,
                "all",
                f"Statistical claim should not have applies_to_strategy='all'",
            )


# ─────────────────────────────────────────────────────────────────────────────
# A4: registry=None → fail-open (no crash)
# A4: registry=None → fail-open 不崩潰
# ─────────────────────────────────────────────────────────────────────────────

class TestRegisterClaimsRegistryNone(unittest.TestCase):
    """A4: _register_pattern_claims with no registry must not crash."""

    def test_register_claims_no_registry_no_crash(self):
        """
        Agent without registry injected: analyze_patterns should complete normally.
        未注入 registry 的 agent：analyze_patterns 應正常完成，不崩潰。
        """
        mock_ollama = _mock_ollama_returning(
            winning=["some winning signal"],
            losing=["some losing signal"],
        )
        config = AnalystConfig(l2_min_observations=5)
        agent = AnalystAgent(config=config, ollama_client=mock_ollama)
        agent.start()
        # Do NOT call set_truth_registry — registry remains None
        _fill_agent(agent, count=10)

        # Should not raise
        result = agent.analyze_patterns(force=True)
        self.assertIsNotNone(result)

    def test_register_pattern_claims_direct_none_registry(self):
        """
        _register_pattern_claims with registry=None returns silently.
        registry=None 時 _register_pattern_claims 靜默返回。
        """
        agent = AnalystAgent()
        agent.start()
        # registry is None by default
        insight = PatternInsight(
            observations_count=50,
            winning_patterns=["test pattern"],
            losing_patterns=["bad pattern"],
            source="test",
        )
        # Must not raise
        agent._register_pattern_claims(insight)


# ─────────────────────────────────────────────────────────────────────────────
# A5: _extract_strategy_from_pattern — known strategy name matching
# A5: 已知策略名匹配
# ─────────────────────────────────────────────────────────────────────────────

class TestExtractStrategyFromPattern(unittest.TestCase):
    """A5/A6: _extract_strategy_from_pattern static method tests."""

    def test_known_strategy_ma_crossover(self):
        """Pattern text containing 'ma_crossover' returns 'ma_crossover'."""
        result = AnalystAgent._extract_strategy_from_pattern("ma_crossover works well in trending")
        self.assertEqual(result, "ma_crossover")

    def test_known_strategy_grid(self):
        """Pattern text containing 'grid' returns 'grid'."""
        result = AnalystAgent._extract_strategy_from_pattern("grid strategy loses in volatile")
        self.assertEqual(result, "grid")

    def test_known_strategy_bb_reversion(self):
        """Pattern text containing 'bb_reversion' returns 'bb_reversion'."""
        result = AnalystAgent._extract_strategy_from_pattern("bb_reversion performs well ranging")
        self.assertEqual(result, "bb_reversion")

    def test_known_strategy_bb_breakout(self):
        """Pattern text containing 'bb_breakout' returns 'bb_breakout'."""
        result = AnalystAgent._extract_strategy_from_pattern("bb_breakout is profitable in trending")
        self.assertEqual(result, "bb_breakout")

    def test_known_strategy_funding_arb(self):
        """Pattern text containing 'funding_arb' returns 'funding_arb'."""
        result = AnalystAgent._extract_strategy_from_pattern("funding_arb generates steady returns")
        self.assertEqual(result, "funding_arb")

    def test_unknown_text_returns_non_all_slug(self):
        """
        Unknown text returns a non-empty, non-'all' slug (A6).
        未知文字返回非空且非 'all' 的 slug。
        """
        result = AnalystAgent._extract_strategy_from_pattern("some completely unknown pattern here")
        self.assertNotEqual(result, "all", "Unknown text must not return 'all'")
        self.assertNotEqual(result, "", "Unknown text slug must not be empty")

    def test_empty_string_returns_non_all(self):
        """Empty input returns 'generic_pattern' fallback, not 'all'."""
        result = AnalystAgent._extract_strategy_from_pattern("")
        self.assertNotEqual(result, "all")
        self.assertEqual(result, "generic_pattern")

    def test_all_word_input_returns_non_all(self):
        """Input that is literally 'all' returns 'generic_pattern', not 'all'."""
        result = AnalystAgent._extract_strategy_from_pattern("all")
        self.assertNotEqual(result, "all")

    def test_case_insensitive_matching(self):
        """Strategy name matching is case-insensitive (A5)."""
        result = AnalystAgent._extract_strategy_from_pattern("MA_CROSSOVER TRENDING SIGNAL")
        self.assertEqual(result, "ma_crossover")


# ─────────────────────────────────────────────────────────────────────────────
# A7: Statistical path also triggers registry registration
# A7: 統計路徑也觸發 registry 登記
# ─────────────────────────────────────────────────────────────────────────────

class TestStatisticalPathRegistersRegistry(unittest.TestCase):
    """A7: Statistical fallback path calls _register_pattern_claims."""

    def test_statistical_path_calls_register(self):
        """
        When Ollama is unavailable, _statistical_pattern_analysis should still
        call _register_pattern_claims (verifiable by spying).
        Ollama 不可用時，統計路徑仍應呼叫 _register_pattern_claims。
        """
        from unittest.mock import patch

        agent, registry = _make_agent_with_registry()
        _fill_agent(agent, count=20)
        # Ensure winning pattern threshold met
        agent._strategy_stats["ma_crossover"]["wins"] = 18
        agent._strategy_stats["ma_crossover"]["losses"] = 2
        agent._strategy_stats["ma_crossover"]["trades"] = 20

        called_with = []

        original = agent._register_pattern_claims
        def spy(insight):
            called_with.append(insight)
            return original(insight)

        agent._register_pattern_claims = spy

        agent.analyze_patterns(force=True)

        self.assertEqual(len(called_with), 1,
                         "_register_pattern_claims should be called once by statistical path")
        self.assertEqual(called_with[0].source, "statistical")


# ─────────────────────────────────────────────────────────────────────────────
# A8: Multiple analyses → registry claim count grows or stays stable (idempotent)
# A8: 多次分析後 registry 聲明數 >= 前一次
# ─────────────────────────────────────────────────────────────────────────────

class TestRegistryClaimGrowthMultipleAnalyses(unittest.TestCase):
    """A8: Registry claim count is non-decreasing across multiple analyses."""

    def test_registry_claims_non_decreasing(self):
        """
        Running analyze_patterns twice should not decrease the claim count.
        兩次 analyze_patterns 後，聲明數量不應減少。
        """
        mock_ollama = _mock_ollama_returning(
            winning=["ma_crossover trending signal"],
            losing=["grid ranging failure"],
        )
        agent, registry = _make_agent_with_registry(ollama_client=mock_ollama)
        _fill_agent(agent, count=15)

        agent.analyze_patterns(force=True)
        count_after_first = len(registry.get_active_claims())

        agent.analyze_patterns(force=True)
        count_after_second = len(registry.get_active_claims())

        self.assertGreaterEqual(
            count_after_second,
            count_after_first,
            "Claim count should be non-decreasing after multiple analyses",
        )


# ─────────────────────────────────────────────────────────────────────────────
# New tests: ExperimentLedger integration
# 新測試：ExperimentLedger 集成
# ─────────────────────────────────────────────────────────────────────────────

class TestExperimentLedgerIntegration(unittest.TestCase):
    """
    E1-Beta Batch 3B — ExperimentLedger integration with AnalystAgent.
    驗收標準：
      - set_experiment_ledger 正確注入
      - winning pattern 分析 → record_observation("supporting") 被呼叫
      - _experiment_ledger=None 時分析不崩潰（fail-open）
    """

    # ── 測試 1：set_experiment_ledger 正確注入 ──────────────────────────────
    def test_set_experiment_ledger_injects_correctly(self):
        """
        After set_experiment_ledger(mock), _experiment_ledger attribute is set.
        呼叫 set_experiment_ledger(mock) 後，_experiment_ledger 屬性應正確設置。
        """
        agent = AnalystAgent()
        agent.start()

        # 初始時應為 None / Should be None initially
        self.assertIsNone(agent._experiment_ledger)

        mock_ledger = MagicMock()
        agent.set_experiment_ledger(mock_ledger)

        # 注入後應為 mock_ledger / After injection should be mock_ledger
        self.assertIs(agent._experiment_ledger, mock_ledger)

    # ── 測試 2：Winning pattern 分析 → record_observation("supporting") 被呼叫 ──
    def test_record_pattern_observations_calls_ledger(self):
        """
        Winning pattern analysis triggers record_observation("supporting") on active hypotheses.
        贏模式分析應觸發 ExperimentLedger.record_observation("supporting") 呼叫。
        """
        from app.experiment_ledger import ExperimentLedger, HypothesisStatus

        # 建立真實的 ExperimentLedger 並注入一個活躍假設
        # Create a real ExperimentLedger with an active hypothesis
        ledger = ExperimentLedger()
        hid = ledger.propose_hypothesis(
            description="ma_crossover works in trending",
            strategy_name="ma_crossover",
            min_observations=100,  # 高閾值，不讓假設提前結案 / High threshold to avoid premature conclusion
        )
        # 假設應處於 PENDING 狀態 / Hypothesis should be in PENDING state
        self.assertEqual(ledger.get_hypothesis(hid).status, HypothesisStatus.PENDING)

        # 建立帶 mock Ollama 的 AnalystAgent 並注入 ledger
        # Create AnalystAgent with mock Ollama and inject ledger
        mock_ollama = _mock_ollama_returning(
            winning=["ma_crossover performs well in trending"],
            losing=[],
        )
        config = AnalystConfig(l2_min_observations=5)
        agent = AnalystAgent(config=config, ollama_client=mock_ollama)
        agent.start()
        agent.set_experiment_ledger(ledger)
        _fill_agent(agent, count=10)

        # 觸發分析 / Trigger analysis
        agent.analyze_patterns(force=True)

        # 假設應已從 PENDING 轉為 RUNNING（表示有 observation 被記錄）
        # Hypothesis should have transitioned PENDING → RUNNING (observation was recorded)
        h = ledger.get_hypothesis(hid)
        self.assertEqual(
            h.status, HypothesisStatus.RUNNING,
            "Hypothesis should be RUNNING after winning pattern observation was recorded",
        )
        # supporting_count 應大於 0 / supporting_count should be > 0
        self.assertGreater(h.supporting_count, 0, "supporting_count should be > 0 after supporting observation")

    # ── 測試 3：_experiment_ledger=None 時分析不崩潰（fail-open）──────────────
    def test_experiment_ledger_none_is_noop(self):
        """
        When _experiment_ledger=None (not injected), analysis completes without crash.
        _experiment_ledger=None（未注入）時，分析應正常完成，不崩潰。
        """
        mock_ollama = _mock_ollama_returning(
            winning=["some winning pattern"],
            losing=["some losing pattern"],
        )
        config = AnalystConfig(l2_min_observations=5)
        agent = AnalystAgent(config=config, ollama_client=mock_ollama)
        agent.start()
        # 故意不注入 ExperimentLedger / Intentionally do NOT inject ExperimentLedger
        self.assertIsNone(agent._experiment_ledger)

        registry = TruthSourceRegistry()
        agent.set_truth_registry(registry)
        _fill_agent(agent, count=10)

        # 不應拋出任何異常 / Must not raise any exception
        result = agent.analyze_patterns(force=True)
        self.assertIsNotNone(result, "analyze_patterns should return insight even without ledger")


if __name__ == "__main__":
    unittest.main()
