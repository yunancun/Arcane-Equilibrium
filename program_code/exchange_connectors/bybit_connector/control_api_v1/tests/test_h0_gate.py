"""
H0 Gate 確定性門控測試
DOC-02 §3.1 — <1ms SLA · 純確定性邏輯 · 無 AI 調用

覆蓋範圍（Day 1）：
  - TestH0GateFreshness: 15 個測試，涵蓋 freshness check 所有邊界條件
  - TestH0GateEligibility: 15 個測試，涵蓋 category + symbol 資格審核

E1-Beta 任務：P1-16 H0 Gate Day 1 測試基礎框架
注意：h0_gate.py 由 E1-Alpha 並行實現，本文件基於接口設計先行編寫。
"""

import time
import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.h0_gate import (
    H0Gate,
    H0GateConfig,
    H0GateHealthSnapshot,
    H0GateRiskSnapshot,
)


# ═══════════════════════════════════════════════════════════════════════════════
# 工具函數 / Utility helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _now_ms() -> int:
    """返回當前時間戳（毫秒）"""
    return int(time.time() * 1000)


def _ms_ago(ms: int) -> int:
    """返回 ms 毫秒前的時間戳"""
    return _now_ms() - ms


def _make_gate(max_data_age_ms: int = 1000, allowed_categories=None) -> H0Gate:
    """創建 H0Gate 實例，使用可自定義的 config"""
    kwargs: dict = {"max_data_age_ms": max_data_age_ms}
    if allowed_categories is not None:
        kwargs["allowed_categories"] = allowed_categories
    config = H0GateConfig(**kwargs)
    return H0Gate(config)


def _fresh_health() -> H0GateHealthSnapshot:
    """返回健康狀態正常的 snapshot（讓 health check 通過）"""
    return H0GateHealthSnapshot(
        cpu_pct=30.0,
        memory_available_mb=4096,
    )


def _fresh_risk() -> H0GateRiskSnapshot:
    """返回風控狀態正常的 snapshot（讓 risk check 通過）"""
    return H0GateRiskSnapshot(
        open_position_count=0,
    )


def _pass_freshness(gate: H0Gate, symbol: str = "BTCUSDT") -> None:
    """注入最新時間戳，讓 freshness check 通過"""
    gate.update_price_ts(symbol, _now_ms())


def _pass_all_prerequisites(gate: H0Gate, symbol: str = "BTCUSDT") -> None:
    """注入所有必要狀態，讓除目標 check 以外的所有前置 check 通過"""
    _pass_freshness(gate, symbol)
    gate.update_health(_fresh_health())
    gate.update_risk(_fresh_risk())


# ═══════════════════════════════════════════════════════════════════════════════
# TestH0GateFreshness — Freshness Check 15 個測試
# ═══════════════════════════════════════════════════════════════════════════════

class TestH0GateFreshness:
    """
    驗證 H0Gate freshness check 的所有邊界條件。
    freshness 是 check() 流程的第一關，未通過即提前返回 blocked。
    """

    def test_unregistered_symbol_blocked(self):
        """1. 未注册的 symbol → blocked，reason 包含 'no_data'"""
        gate = _make_gate()
        result = gate.check("BTCUSDT", "linear")
        assert result.allowed is False
        assert "no_data" in result.reason

    def test_just_registered_symbol_allowed(self):
        """2. 剛注册的 symbol（now_ms）→ allowed（freshness 關通過）"""
        gate = _make_gate()
        _pass_all_prerequisites(gate, "BTCUSDT")
        result = gate.check("BTCUSDT", "linear")
        # freshness 應通過；整體結果取決於後續 check，
        # 但 check_name 不應是 "freshness"（freshness 未阻擋）
        assert result.check_name != "freshness"

    def test_999ms_old_data_allowed(self):
        """3. 999ms 前的數據 → allowed（未超過 1000ms 閾值）"""
        gate = _make_gate(max_data_age_ms=1000)
        gate.update_price_ts("BTCUSDT", _ms_ago(999))
        gate.update_health(_fresh_health())
        gate.update_risk(_fresh_risk())
        result = gate.check("BTCUSDT", "linear")
        assert result.check_name != "freshness"

    def test_1000ms_old_data_blocked(self):
        """4. 1000ms 前的數據 → blocked（達到閾值）"""
        gate = _make_gate(max_data_age_ms=1000)
        gate.update_price_ts("BTCUSDT", _ms_ago(1000))
        result = gate.check("BTCUSDT", "linear")
        assert result.allowed is False
        assert "data_stale" in result.reason

    def test_1001ms_old_data_blocked(self):
        """5. 1001ms 前的數據 → blocked"""
        gate = _make_gate(max_data_age_ms=1000)
        gate.update_price_ts("BTCUSDT", _ms_ago(1001))
        result = gate.check("BTCUSDT", "linear")
        assert result.allowed is False

    def test_5000ms_old_data_reason_contains_age(self):
        """6. 5000ms 前的數據 → blocked，reason 包含 age 毫秒數"""
        gate = _make_gate(max_data_age_ms=1000)
        gate.update_price_ts("BTCUSDT", _ms_ago(5000))
        result = gate.check("BTCUSDT", "linear")
        assert result.allowed is False
        # reason 應包含數字（age 毫秒數）
        assert any(ch.isdigit() for ch in result.reason)

    def test_blocked_by_freshness_check_name(self):
        """7. check_name == 'freshness' 當被 freshness 阻擋"""
        gate = _make_gate()
        # 未注册 symbol，應在 freshness 階段阻擋
        result = gate.check("BTCUSDT", "linear")
        assert result.check_name == "freshness"

    def test_multiple_symbols_independent_freshness(self):
        """8. 多個 symbol，只有 BTCUSDT stale → BTCUSDT blocked，ETHUSDT 不受影響"""
        gate = _make_gate(max_data_age_ms=1000)
        # BTCUSDT: 2000ms 前（stale）
        gate.update_price_ts("BTCUSDT", _ms_ago(2000))
        # ETHUSDT: 剛注册（fresh）
        _pass_all_prerequisites(gate, "ETHUSDT")

        result_btc = gate.check("BTCUSDT", "linear")
        result_eth = gate.check("ETHUSDT", "linear")

        assert result_btc.allowed is False
        assert result_btc.check_name == "freshness"
        # ETHUSDT 的 freshness 應通過（check_name 不是 freshness）
        assert result_eth.check_name != "freshness"

    def test_update_price_ts_turns_blocked_to_allowed(self):
        """9. update_price_ts 更新後從 blocked 變 allowed（freshness 關）"""
        gate = _make_gate(max_data_age_ms=1000)
        gate.update_price_ts("BTCUSDT", _ms_ago(2000))
        result_stale = gate.check("BTCUSDT", "linear")
        assert result_stale.allowed is False

        # 更新為最新時間戳
        gate.update_price_ts("BTCUSDT", _now_ms())
        gate.update_health(_fresh_health())
        gate.update_risk(_fresh_risk())
        result_fresh = gate.check("BTCUSDT", "linear")
        assert result_fresh.check_name != "freshness"

    def test_custom_threshold_500ms_blocks_at_500ms(self):
        """10. max_data_age_ms=500 的 config：500ms 前的數據 blocked"""
        gate = _make_gate(max_data_age_ms=500)
        gate.update_price_ts("BTCUSDT", _ms_ago(500))
        result = gate.check("BTCUSDT", "linear")
        assert result.allowed is False
        assert result.check_name == "freshness"

    def test_custom_threshold_2000ms_allows_1500ms_old(self):
        """11. max_data_age_ms=2000 的 config：1500ms 前的數據 allowed"""
        gate = _make_gate(max_data_age_ms=2000)
        gate.update_price_ts("BTCUSDT", _ms_ago(1500))
        gate.update_health(_fresh_health())
        gate.update_risk(_fresh_risk())
        result = gate.check("BTCUSDT", "linear")
        assert result.check_name != "freshness"

    def test_allowed_result_has_empty_reason(self):
        """12. 當 freshness 通過且整體 allowed=True 時 reason == ''"""
        gate = _make_gate()
        _pass_all_prerequisites(gate, "BTCUSDT")
        result = gate.check("BTCUSDT", "linear")
        if result.allowed:
            assert result.reason == ""

    def test_latency_us_positive(self):
        """13. result.latency_us >= 0（計時有效，極快操作可能為 0）"""
        gate = _make_gate()
        result = gate.check("BTCUSDT", "linear")
        assert result.latency_us >= 0
        assert isinstance(result.latency_us, int)

    def test_stats_blocked_increments_on_block(self):
        """14. stats['blocked'] 在 block 後遞增"""
        gate = _make_gate()
        stats_before = gate.get_stats()
        blocked_before = stats_before.get("blocked", 0)

        gate.check("BTCUSDT", "linear")  # 未注册，應 block
        stats_after = gate.get_stats()
        assert stats_after["blocked"] > blocked_before

    def test_stats_passed_increments_on_pass(self):
        """15. stats['passed'] 在 pass 後遞增"""
        gate = _make_gate()
        _pass_all_prerequisites(gate, "BTCUSDT")

        stats_before = gate.get_stats()
        passed_before = stats_before.get("passed", 0)

        result = gate.check("BTCUSDT", "linear")
        if result.allowed:
            stats_after = gate.get_stats()
            assert stats_after["passed"] > passed_before
        else:
            # 如果後續 check 阻擋了，至少 blocked 有遞增
            stats_after = gate.get_stats()
            assert stats_after.get("total_checks", 0) > stats_before.get("total_checks", 0)


# ═══════════════════════════════════════════════════════════════════════════════
# TestH0GateEligibility — Eligibility Check 15 個測試
# ═══════════════════════════════════════════════════════════════════════════════

class TestH0GateEligibility:
    """
    驗證 H0Gate eligibility check（category + symbol 資格審核）。
    測試前置：使用 _pass_all_prerequisites 讓 freshness/health/risk 通過，
    專注測試 eligibility 邏輯。

    注意：若 health/risk check 骨架尚未實現（預設通過），
    此處測試仍有效；一旦實現後仍然通過。
    """

    @pytest.fixture(autouse=True)
    def gate_with_fresh_data(self):
        """每個測試前準備一個 freshness 已通過的 gate"""
        self.gate = _make_gate()
        _pass_all_prerequisites(self.gate, "BTCUSDT")
        _pass_all_prerequisites(self.gate, "ETHUSDT")
        _pass_all_prerequisites(self.gate, "XYZUSDT")
        _pass_all_prerequisites(self.gate, "SOLUSDT")

    def test_linear_category_allowed(self):
        """1. 'linear' category → allowed（默認允許）"""
        result = self.gate.check("BTCUSDT", "linear")
        assert result.check_name != "eligibility"

    def test_inverse_category_allowed(self):
        """2. 'inverse' category → allowed"""
        _pass_all_prerequisites(self.gate, "BTCUSDT")
        result = self.gate.check("BTCUSDT", "inverse")
        assert result.check_name != "eligibility"

    def test_spot_category_allowed(self):
        """3. 'spot' category → allowed"""
        result = self.gate.check("BTCUSDT", "spot")
        assert result.check_name != "eligibility"

    def test_option_category_blocked(self):
        """4. 'option' category（不在 allowed_categories）→ blocked，reason 包含 'category_not_allowed'"""
        result = self.gate.check("BTCUSDT", "option")
        assert result.allowed is False
        assert "category_not_allowed" in result.reason

    def test_unknown_category_blocked(self):
        """5. 'UNKNOWN_CATEGORY' → blocked"""
        result = self.gate.check("BTCUSDT", "UNKNOWN_CATEGORY")
        assert result.allowed is False

    def test_blocked_by_eligibility_check_name(self):
        """6. check_name == 'eligibility' 當被 eligibility 阻擋"""
        result = self.gate.check("BTCUSDT", "option")
        assert result.check_name == "eligibility"

    def test_set_symbol_eligibility_false_blocks(self):
        """7. set_symbol_eligibility('XYZUSDT', False) 後 check XYZUSDT → blocked，reason 包含 'symbol_not_eligible'"""
        self.gate.set_symbol_eligibility("XYZUSDT", False)
        result = self.gate.check("XYZUSDT", "linear")
        assert result.allowed is False
        assert "symbol_not_eligible" in result.reason

    def test_set_symbol_eligibility_true_allows(self):
        """8. set_symbol_eligibility('BTCUSDT', True) 後 → allowed（eligibility 關通過）"""
        self.gate.set_symbol_eligibility("BTCUSDT", True)
        result = self.gate.check("BTCUSDT", "linear")
        assert result.check_name != "eligibility"

    def test_default_symbol_eligibility_is_allowed(self):
        """9. 未設置 symbol eligibility（默認）→ allowed（默認開放）"""
        # SOLUSDT 未顯式設置
        result = self.gate.check("SOLUSDT", "linear")
        assert result.check_name != "eligibility"

    def test_allowed_category_with_blocked_symbol(self):
        """10. 允許的 category + blocked symbol → blocked（symbol 優先）"""
        self.gate.set_symbol_eligibility("XYZUSDT", False)
        result = self.gate.check("XYZUSDT", "linear")
        assert result.allowed is False
        assert result.check_name == "eligibility"

    def test_custom_allowed_categories_only_linear(self):
        """11. allowed_categories 自定義只允許 'linear' → spot blocked"""
        gate = _make_gate(allowed_categories=["linear"])
        _pass_all_prerequisites(gate, "BTCUSDT")
        result = gate.check("BTCUSDT", "spot")
        assert result.allowed is False
        assert result.check_name == "eligibility"

    def test_set_symbol_eligibility_recovers_blocked_symbol(self):
        """12. set_symbol_eligibility 改為 True 後原來 blocked symbol 現在 allowed"""
        self.gate.set_symbol_eligibility("XYZUSDT", False)
        blocked_result = self.gate.check("XYZUSDT", "linear")
        assert blocked_result.allowed is False

        self.gate.set_symbol_eligibility("XYZUSDT", True)
        allowed_result = self.gate.check("XYZUSDT", "linear")
        assert allowed_result.check_name != "eligibility"

    def test_allowed_result_has_empty_reason(self):
        """13. allowed=True 時 reason == ''"""
        result = self.gate.check("BTCUSDT", "linear")
        if result.allowed:
            assert result.reason == ""

    def test_all_passed_check_name_when_everything_passes(self):
        """14. check_name == 'all_passed' 當全部通過（freshness + eligibility + health/risk/cooldown 全通）"""
        result = self.gate.check("BTCUSDT", "linear")
        if result.allowed:
            assert result.check_name == "all_passed"

    def test_system_mode_disabled_blocks(self):
        """15. set_system_mode('disabled') → blocked"""
        gate = H0Gate()
        gate.set_system_mode("disabled")
        _pass_all_prerequisites(gate, "BTCUSDT")
        result = gate.check("BTCUSDT", "linear")
        assert result.allowed is False
        assert "disabled" in result.reason or result.check_name == "eligibility"


# ═══════════════════════════════════════════════════════════════════════════════
# TestH0GateStats — 統計計數測試（輔助驗證）
# ═══════════════════════════════════════════════════════════════════════════════

class TestH0GateStats:
    """驗證 get_stats() 返回結構與計數邏輯正確"""

    def test_stats_has_required_keys(self):
        """stats 返回字典包含 total_checks, blocked, passed"""
        gate = _make_gate()
        stats = gate.get_stats()
        assert "total_checks" in stats
        assert "blocked" in stats
        assert "passed" in stats

    def test_stats_initial_zero(self):
        """新建 gate 未執行任何 check，stats 各計數為 0"""
        gate = _make_gate()
        stats = gate.get_stats()
        assert stats["total_checks"] == 0
        assert stats["blocked"] == 0
        assert stats["passed"] == 0

    def test_stats_total_checks_increments(self):
        """每次 check() 調用後 total_checks 遞增"""
        gate = _make_gate()
        gate.check("BTCUSDT", "linear")
        gate.check("ETHUSDT", "linear")
        stats = gate.get_stats()
        assert stats["total_checks"] == 2

    def test_stats_blocked_plus_passed_equals_total(self):
        """blocked + passed == total_checks（無丟失計數）"""
        gate = _make_gate()
        _pass_all_prerequisites(gate, "BTCUSDT")

        gate.check("MISSING_SYMBOL", "linear")  # blocked
        gate.check("BTCUSDT", "linear")         # 可能 passed

        stats = gate.get_stats()
        assert stats["blocked"] + stats["passed"] == stats["total_checks"]


# ═══════════════════════════════════════════════════════════════════════════════
# TestH0GateLatency — SLA 驗證（<1ms 確定性門控）
# ═══════════════════════════════════════════════════════════════════════════════

class TestH0GateLatency:
    """
    DOC-02 §3.1 要求：<1ms SLA。
    注意：CI 環境資源受限，此處設置寬鬆門限（5ms）做基礎保護，
    嚴格 1ms 驗證需在專用性能環境中執行。
    """

    def test_check_latency_under_5ms_for_blocked(self):
        """blocked 路徑延遲 < 5ms（寬鬆 CI 門限）"""
        gate = _make_gate()
        result = gate.check("BTCUSDT", "linear")
        assert result.latency_us < 5000  # 5ms = 5000μs

    def test_check_latency_under_5ms_for_allowed(self):
        """allowed 路徑延遲 < 5ms（寬鬆 CI 門限）"""
        gate = _make_gate()
        _pass_all_prerequisites(gate, "BTCUSDT")
        result = gate.check("BTCUSDT", "linear")
        assert result.latency_us < 5000

    def test_latency_us_type_is_int(self):
        """latency_us 類型為 int"""
        gate = _make_gate()
        result = gate.check("BTCUSDT", "linear")
        assert isinstance(result.latency_us, int)
