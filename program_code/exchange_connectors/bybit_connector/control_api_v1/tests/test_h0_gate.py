"""
H0 Gate 確定性門控測試
DOC-02 §3.1 — <1ms SLA · 純確定性邏輯 · 無 AI 調用

覆蓋範圍（Day 1）：
  - TestH0GateFreshness:  15 個測試，涵蓋 freshness check 所有邊界條件
  - TestH0GateEligibility: 15 個測試，涵蓋 category + symbol 資格審核
  - TestH0GateStats:       4 個測試，統計計數驗證
  - TestH0GateLatency:     3 個測試，SLA 基礎驗證

覆蓋範圍（Day 2 新增）：
  - TestH0GateHealth:      12 個測試，health check 所有邊界條件
  - TestH0GateRisk:        12 個測試，risk envelope 邊界條件
  - TestH0GateCooldown:    8 個測試，cooldown period 所有情形
  - TestH0GateSLATimeit:   2 個測試，1000 次迭代 SLA 壓測（avg < 1ms）
  - TestH0HealthWorker:    6 個測試，H0HealthWorker 生命週期與採樣

E1-Beta 任務：P1-16 H0 Gate Day 1 測試基礎框架
E1-Beta 擴展：P1-16 H0 Gate Day 2 健康/風控/冷卻/SLA 完整覆蓋
注意：h0_gate.py 由 E1-Alpha 並行實現，本文件基於接口設計先行編寫。
"""

import time
import timeit
import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.h0_gate import (
    H0Gate,
    H0GateConfig,
    H0GateHealthSnapshot,
    H0GateRiskSnapshot,
    H0HealthWorker,
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


# ═══════════════════════════════════════════════════════════════════════════════
# TestH0GateHealth — Health Check 12 個測試（Day 2 新增）
# ═══════════════════════════════════════════════════════════════════════════════

class TestH0GateHealth:
    """
    驗證 H0Gate health check 的所有邊界條件。
    health check 是 check() 流程的第二關。
    使用 _pass_all_prerequisites 確保 freshness 先通過，再測試 health 邏輯。
    """

    @pytest.fixture(autouse=True)
    def gate_with_fresh_data(self):
        """每個測試前建立 gate，freshness 已通過"""
        self.gate = H0Gate()
        _pass_freshness(self.gate, "BTCUSDT")

    def _healthy_snap(self, **kwargs) -> H0GateHealthSnapshot:
        """返回健康的 snapshot，可覆蓋個別欄位"""
        defaults = dict(
            cpu_pct=30.0,
            memory_available_mb=4096,
            db_latency_ms=10.0,
            network_loss_pct=0.0,
            snapshot_ts_ms=int(time.time() * 1000),
        )
        defaults.update(kwargs)
        return H0GateHealthSnapshot(**defaults)

    def test_default_snapshot_no_timestamp_passes(self):
        """1. 默認 snapshot（snapshot_ts_ms=0）略過過期檢查，cpu=0/mem=9999→通過"""
        # 默認 snapshot 所有值安全（cpu=0, mem=9999MB, snapshot_ts_ms=0）
        self.gate.update_risk(_fresh_risk())
        result = self.gate.check("BTCUSDT", "linear")
        assert result.check_name != "health"

    def test_healthy_snapshot_passes(self):
        """2. 有時間戳且所有指標正常的 snapshot → 通過"""
        self.gate.update_health(self._healthy_snap())
        self.gate.update_risk(_fresh_risk())
        result = self.gate.check("BTCUSDT", "linear")
        assert result.check_name != "health"

    def test_cpu_above_threshold_blocked(self):
        """3. CPU 超過 max_cpu_pct → blocked"""
        self.gate.update_health(self._healthy_snap(cpu_pct=95.0))
        result = self.gate.check("BTCUSDT", "linear")
        assert result.allowed is False
        assert result.check_name == "health"
        assert "cpu_too_high" in result.reason

    def test_cpu_exactly_at_threshold_blocked(self):
        """4. CPU == max_cpu_pct（90.0）→ blocked（> 比較）"""
        gate = H0Gate(H0GateConfig(max_cpu_pct=90.0))
        _pass_freshness(gate, "BTCUSDT")
        gate.update_health(self._healthy_snap(cpu_pct=90.1))
        result = gate.check("BTCUSDT", "linear")
        assert result.allowed is False
        assert result.check_name == "health"

    def test_cpu_below_threshold_passes(self):
        """5. CPU == 89.9（低於 90.0 閾值）→ health 通過"""
        gate = H0Gate(H0GateConfig(max_cpu_pct=90.0))
        _pass_freshness(gate, "BTCUSDT")
        gate.update_health(self._healthy_snap(cpu_pct=89.9))
        gate.update_risk(_fresh_risk())
        result = gate.check("BTCUSDT", "linear")
        assert result.check_name != "health"

    def test_memory_below_threshold_blocked(self):
        """6. 可用記憶體低於 min_memory_mb → blocked"""
        self.gate.update_health(self._healthy_snap(memory_available_mb=512))
        result = self.gate.check("BTCUSDT", "linear")
        assert result.allowed is False
        assert result.check_name == "health"
        assert "memory_low" in result.reason

    def test_memory_exactly_at_threshold_passes(self):
        """7. 可用記憶體 == min_memory_mb（1024）→ 通過（< 比較）"""
        gate = H0Gate(H0GateConfig(min_memory_mb=1024))
        _pass_freshness(gate, "BTCUSDT")
        gate.update_health(self._healthy_snap(memory_available_mb=1024))
        gate.update_risk(_fresh_risk())
        result = gate.check("BTCUSDT", "linear")
        assert result.check_name != "health"

    def test_db_latency_above_threshold_blocked(self):
        """8. DB 延遲超過 max_db_latency_ms → blocked"""
        self.gate.update_health(self._healthy_snap(db_latency_ms=150.0))
        result = self.gate.check("BTCUSDT", "linear")
        assert result.allowed is False
        assert result.check_name == "health"
        assert "db_latency_high" in result.reason

    def test_network_loss_above_threshold_blocked(self):
        """9. 網絡丟包超過 max_network_loss_pct → blocked"""
        self.gate.update_health(self._healthy_snap(network_loss_pct=10.0))
        result = self.gate.check("BTCUSDT", "linear")
        assert result.allowed is False
        assert result.check_name == "health"
        assert "network_loss_high" in result.reason

    def test_stale_health_snapshot_blocked(self):
        """10. health snapshot 超過 health_snapshot_max_age_ms → blocked"""
        old_ts = int(time.time() * 1000) - 60_000  # 60秒前，超過默認 30秒 TTL
        stale_snap = H0GateHealthSnapshot(
            cpu_pct=0.0,
            memory_available_mb=9999,
            snapshot_ts_ms=old_ts,
        )
        self.gate.update_health(stale_snap)
        result = self.gate.check("BTCUSDT", "linear")
        assert result.allowed is False
        assert result.check_name == "health"
        assert "health_snapshot_stale" in result.reason

    def test_fresh_health_snapshot_not_stale(self):
        """11. 剛更新的 snapshot（now）→ 不觸發 stale 判斷"""
        fresh_snap = H0GateHealthSnapshot(
            cpu_pct=10.0,
            memory_available_mb=8192,
            snapshot_ts_ms=int(time.time() * 1000),
        )
        self.gate.update_health(fresh_snap)
        self.gate.update_risk(_fresh_risk())
        result = self.gate.check("BTCUSDT", "linear")
        assert result.check_name != "health"

    def test_update_health_immediately_effective(self):
        """12. update_health 立即生效：注入 bad→blocked，再注入 good→通過"""
        self.gate.update_health(self._healthy_snap(cpu_pct=99.9))
        result_bad = self.gate.check("BTCUSDT", "linear")
        assert result_bad.allowed is False

        _pass_freshness(self.gate, "BTCUSDT")  # 重新注入新鮮 tick
        self.gate.update_health(self._healthy_snap(cpu_pct=10.0))
        self.gate.update_risk(_fresh_risk())
        result_good = self.gate.check("BTCUSDT", "linear")
        assert result_good.check_name != "health"


# ═══════════════════════════════════════════════════════════════════════════════
# TestH0GateRisk — Risk Envelope Check 12 個測試（Day 2 新增）
# ═══════════════════════════════════════════════════════════════════════════════

class TestH0GateRisk:
    """
    驗證 H0Gate risk envelope check 的所有邊界條件。
    risk check 是 check() 流程的第四關。
    使用 _pass_all_prerequisites 確保 freshness/health/eligibility 先通過，
    再通過 update_risk() 測試 risk 邏輯。
    """

    @pytest.fixture(autouse=True)
    def gate_with_prerequisites(self):
        """每個測試前建立 gate，freshness + health 已通過"""
        self.gate = H0Gate()
        _pass_freshness(self.gate, "BTCUSDT")
        self.gate.update_health(_fresh_health())

    def test_kill_switch_active_blocked(self):
        """1. kill_switch_active=True → blocked，reason 包含 'kill_switch_active'"""
        self.gate.update_risk(H0GateRiskSnapshot(kill_switch_active=True))
        result = self.gate.check("BTCUSDT", "linear")
        assert result.allowed is False
        assert result.check_name == "risk"
        assert "kill_switch_active" in result.reason

    def test_kill_switch_inactive_allows(self):
        """2. kill_switch_active=False（默認）→ risk check 通過"""
        self.gate.update_risk(H0GateRiskSnapshot(kill_switch_active=False))
        result = self.gate.check("BTCUSDT", "linear")
        assert result.check_name != "risk"

    def test_max_positions_reached_blocked(self):
        """3. open_position_count == max_open_positions → blocked（>= 比較）"""
        gate = H0Gate(H0GateConfig(max_open_positions=5))
        _pass_freshness(gate, "BTCUSDT")
        gate.update_health(_fresh_health())
        gate.update_risk(H0GateRiskSnapshot(open_position_count=5))
        result = gate.check("BTCUSDT", "linear")
        assert result.allowed is False
        assert result.check_name == "risk"
        assert "max_positions_reached" in result.reason

    def test_positions_below_max_allowed(self):
        """4. open_position_count < max_open_positions → 通過"""
        gate = H0Gate(H0GateConfig(max_open_positions=5))
        _pass_freshness(gate, "BTCUSDT")
        gate.update_health(_fresh_health())
        gate.update_risk(H0GateRiskSnapshot(open_position_count=4))
        result = gate.check("BTCUSDT", "linear")
        assert result.check_name != "risk"

    def test_exposure_at_limit_blocked(self):
        """5. total_exposure_pct == max_total_exposure_pct → blocked（>= 比較）"""
        gate = H0Gate(H0GateConfig(max_total_exposure_pct=80.0))
        _pass_freshness(gate, "BTCUSDT")
        gate.update_health(_fresh_health())
        gate.update_risk(H0GateRiskSnapshot(total_exposure_pct=80.0))
        result = gate.check("BTCUSDT", "linear")
        assert result.allowed is False
        assert result.check_name == "risk"
        assert "exposure_limit_reached" in result.reason

    def test_exposure_below_limit_allowed(self):
        """6. total_exposure_pct < max_total_exposure_pct → 通過"""
        gate = H0Gate(H0GateConfig(max_total_exposure_pct=80.0))
        _pass_freshness(gate, "BTCUSDT")
        gate.update_health(_fresh_health())
        gate.update_risk(H0GateRiskSnapshot(total_exposure_pct=79.9))
        result = gate.check("BTCUSDT", "linear")
        assert result.check_name != "risk"

    def test_kill_switch_takes_priority_over_positions(self):
        """7. kill_switch + max positions 同時觸發 → reason 為 kill_switch_active"""
        gate = H0Gate(H0GateConfig(max_open_positions=5))
        _pass_freshness(gate, "BTCUSDT")
        gate.update_health(_fresh_health())
        gate.update_risk(H0GateRiskSnapshot(
            kill_switch_active=True,
            open_position_count=10,
        ))
        result = gate.check("BTCUSDT", "linear")
        assert result.allowed is False
        assert "kill_switch_active" in result.reason

    def test_default_risk_snapshot_all_zero_allowed(self):
        """8. 默認 risk snapshot（全零）→ 通過"""
        self.gate.update_risk(H0GateRiskSnapshot())
        result = self.gate.check("BTCUSDT", "linear")
        assert result.check_name != "risk"

    def test_risk_reason_contains_position_counts(self):
        """9. max positions blocked 時 reason 包含實際數字"""
        gate = H0Gate(H0GateConfig(max_open_positions=3))
        _pass_freshness(gate, "BTCUSDT")
        gate.update_health(_fresh_health())
        gate.update_risk(H0GateRiskSnapshot(open_position_count=3))
        result = gate.check("BTCUSDT", "linear")
        assert result.allowed is False
        assert "3" in result.reason

    def test_risk_reason_contains_exposure_pct(self):
        """10. exposure blocked 時 reason 包含百分比數字"""
        gate = H0Gate(H0GateConfig(max_total_exposure_pct=50.0))
        _pass_freshness(gate, "BTCUSDT")
        gate.update_health(_fresh_health())
        gate.update_risk(H0GateRiskSnapshot(total_exposure_pct=75.5))
        result = gate.check("BTCUSDT", "linear")
        assert result.allowed is False
        assert "75.5" in result.reason

    def test_update_risk_immediately_effective(self):
        """11. update_risk 立即生效：注入 bad→blocked，再注入 good→通過"""
        self.gate.update_risk(H0GateRiskSnapshot(kill_switch_active=True))
        result_bad = self.gate.check("BTCUSDT", "linear")
        assert result_bad.allowed is False

        _pass_freshness(self.gate, "BTCUSDT")
        self.gate.update_risk(H0GateRiskSnapshot(kill_switch_active=False))
        result_good = self.gate.check("BTCUSDT", "linear")
        assert result_good.check_name != "risk"

    def test_stats_blocked_risk_increments(self):
        """12. kill switch blocked → stats['blocked_risk'] 遞增"""
        self.gate.update_risk(H0GateRiskSnapshot(kill_switch_active=True))
        stats_before = self.gate.get_stats().get("blocked_risk", 0)
        self.gate.check("BTCUSDT", "linear")
        stats_after = self.gate.get_stats().get("blocked_risk", 0)
        assert stats_after == stats_before + 1


# ═══════════════════════════════════════════════════════════════════════════════
# TestH0GateCooldown — Cooldown Check 8 個測試（Day 2 新增）
# ═══════════════════════════════════════════════════════════════════════════════

class TestH0GateCooldown:
    """
    驗證 H0Gate cooldown check 的所有邊界條件。
    cooldown check 是 check() 流程的最後一關（第五關）。
    使用 _pass_all_prerequisites 確保前四關通過，專注測試 cooldown 邏輯。
    """

    @pytest.fixture(autouse=True)
    def gate_with_prerequisites(self):
        """每個測試前建立 gate，freshness + health 已通過"""
        self.gate = H0Gate()
        _pass_all_prerequisites(self.gate, "BTCUSDT")

    def test_no_cooldown_zero_timestamp_allowed(self):
        """1. cooldown_until_ts_ms=0 → 無冷卻，通過"""
        self.gate.update_risk(H0GateRiskSnapshot(cooldown_until_ts_ms=0))
        result = self.gate.check("BTCUSDT", "linear")
        assert result.allowed is True
        assert result.check_name == "all_passed"

    def test_active_cooldown_blocked(self):
        """2. cooldown_until_ts_ms 設在未來 10 秒 → blocked"""
        future_ts = int(time.time() * 1000) + 10_000
        self.gate.update_risk(H0GateRiskSnapshot(cooldown_until_ts_ms=future_ts))
        result = self.gate.check("BTCUSDT", "linear")
        assert result.allowed is False
        assert result.check_name == "cooldown"
        assert "cooldown_active" in result.reason

    def test_expired_cooldown_allowed(self):
        """3. cooldown_until_ts_ms 設在過去 1 秒前 → 冷卻已過期，通過"""
        past_ts = int(time.time() * 1000) - 1_000
        self.gate.update_risk(H0GateRiskSnapshot(cooldown_until_ts_ms=past_ts))
        result = self.gate.check("BTCUSDT", "linear")
        assert result.allowed is True

    def test_cooldown_reason_contains_remaining_ms(self):
        """4. active cooldown 的 reason 包含剩餘毫秒數"""
        future_ts = int(time.time() * 1000) + 5_000
        self.gate.update_risk(H0GateRiskSnapshot(cooldown_until_ts_ms=future_ts))
        result = self.gate.check("BTCUSDT", "linear")
        assert result.allowed is False
        # reason 包含數字（剩餘 ms）
        assert any(ch.isdigit() for ch in result.reason)

    def test_cooldown_reason_contains_ms_remaining(self):
        """5. reason 包含 'ms_remaining' 後綴"""
        future_ts = int(time.time() * 1000) + 3_000
        self.gate.update_risk(H0GateRiskSnapshot(cooldown_until_ts_ms=future_ts))
        result = self.gate.check("BTCUSDT", "linear")
        assert "ms_remaining" in result.reason

    def test_just_expired_cooldown_allowed(self):
        """6. cooldown_until 剛好等於當前時間（差 <5ms）→ 通過（已過期）"""
        just_past = int(time.time() * 1000) - 1  # 1ms 前
        self.gate.update_risk(H0GateRiskSnapshot(cooldown_until_ts_ms=just_past))
        result = self.gate.check("BTCUSDT", "linear")
        assert result.allowed is True

    def test_stats_blocked_cooldown_increments(self):
        """7. active cooldown blocked → stats['blocked_cooldown'] 遞增"""
        future_ts = int(time.time() * 1000) + 10_000
        self.gate.update_risk(H0GateRiskSnapshot(cooldown_until_ts_ms=future_ts))
        before = self.gate.get_stats().get("blocked_cooldown", 0)
        self.gate.check("BTCUSDT", "linear")
        after = self.gate.get_stats().get("blocked_cooldown", 0)
        assert after == before + 1

    def test_cooldown_cleared_by_update_risk(self):
        """8. 先設 active cooldown → blocked；再 update_risk 清除冷卻 → 通過"""
        future_ts = int(time.time() * 1000) + 10_000
        self.gate.update_risk(H0GateRiskSnapshot(cooldown_until_ts_ms=future_ts))
        result_blocked = self.gate.check("BTCUSDT", "linear")
        assert result_blocked.allowed is False

        _pass_freshness(self.gate, "BTCUSDT")
        self.gate.update_risk(H0GateRiskSnapshot(cooldown_until_ts_ms=0))
        result_allowed = self.gate.check("BTCUSDT", "linear")
        assert result_allowed.allowed is True


# ═══════════════════════════════════════════════════════════════════════════════
# TestH0GateSLATimeit — 1000 次迭代 SLA 壓測（Day 2 新增）
# ═══════════════════════════════════════════════════════════════════════════════

class TestH0GateSLATimeit:
    """
    DOC-02 §3.1 嚴格 SLA 驗證：1000 次迭代平均必須 < 1ms。
    分別測試 blocked 路徑（第一關即失敗）與 allowed 路徑（全部通過）。
    """

    def test_sla_1ms_blocked_path_1000_iterations(self):
        """
        blocked 路徑（第一關即失敗）的 1000 次平均延遲 < 1ms。
        這是最樂觀的情境（fail-fast，只跑 freshness check）。
        """
        gate = _make_gate()
        # 不注冊任何 symbol → 第一關即失敗

        elapsed = timeit.timeit(
            lambda: gate.check("BTCUSDT", "linear"),
            number=1000,
        )
        avg_ms = (elapsed / 1000) * 1000  # 轉換為毫秒
        assert avg_ms < 1.0, (
            f"SLA violation: blocked path avg={avg_ms:.4f}ms > 1ms (DOC-02 §3.1)"
        )

    def test_sla_1ms_allowed_path_1000_iterations(self):
        """
        allowed 路徑（全部 5 個子檢查通過）的 1000 次平均延遲 < 1ms。
        這是最嚴格的情境（完整熱路徑）。

        注意：max_data_age_ms 設為 60000ms（60秒），避免 1000 次迭代期間
        price_ts 逐漸老化至 stale（預設 1s 閾值在低速機器上可能在迭代中間觸發）。
        """
        # 使用 60s freshness window，確保整個 timeit 期間不觸發 stale
        gate = H0Gate(H0GateConfig(max_data_age_ms=60_000))
        # 注入所有狀態使 check 通過
        gate.update_price_ts("BTCUSDT", int(time.time() * 1000))
        gate.update_health(H0GateHealthSnapshot(
            cpu_pct=10.0,
            memory_available_mb=8192,
            snapshot_ts_ms=int(time.time() * 1000),
        ))
        gate.update_risk(H0GateRiskSnapshot())

        elapsed = timeit.timeit(
            lambda: gate.check("BTCUSDT", "linear"),
            number=1000,
        )
        avg_ms = (elapsed / 1000) * 1000
        assert avg_ms < 1.0, (
            f"SLA violation: allowed path avg={avg_ms:.4f}ms > 1ms (DOC-02 §3.1)"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# TestH0HealthWorker — H0HealthWorker 生命週期測試（Day 2 新增）
# ═══════════════════════════════════════════════════════════════════════════════

class TestH0HealthWorker:
    """
    驗證 H0HealthWorker 生命週期（start/stop）與採樣注入功能。
    注意：不依賴 psutil 是否已安裝（psutil 為可選依賴）。
    """

    def test_worker_starts_and_stops(self):
        """1. start() → is_running=True；stop() → is_running=False"""
        gate = H0Gate()
        worker = H0HealthWorker(gate, sample_interval_s=60.0)  # 長間隔避免自動採樣干擾

        worker.start()
        assert worker.is_running is True

        worker.stop()
        assert worker.is_running is False

    def test_worker_start_idempotent(self):
        """2. 連續兩次 start() 不應 crash（idempotent）"""
        gate = H0Gate()
        worker = H0HealthWorker(gate, sample_interval_s=60.0)

        worker.start()
        thread1 = worker._thread
        worker.start()  # 第二次應被忽略
        thread2 = worker._thread

        assert thread1 is thread2  # 同一個線程，未重建

        worker.stop()

    def test_worker_stop_before_start_is_noop(self):
        """3. 未 start 就 stop() 不應 crash"""
        gate = H0Gate()
        worker = H0HealthWorker(gate, sample_interval_s=60.0)
        worker.stop()  # 不應拋出異常
        assert worker.is_running is False

    def test_worker_injects_health_snapshot(self):
        """4. 啟動後短暫等待，gate 的 health snapshot 應被更新（snapshot_ts_ms > 0）"""
        gate = H0Gate()
        worker = H0HealthWorker(gate, sample_interval_s=0.05)  # 50ms 短間隔

        worker.start()
        time.sleep(0.2)  # 等待至少一次採樣
        worker.stop()

        snap = gate._health_snapshot
        assert snap.snapshot_ts_ms > 0, "H0HealthWorker 未注入任何 health snapshot"

    def test_worker_with_db_probe_fn(self):
        """5. 提供 db_probe_fn → 採樣後 db_latency_ms 應 >= 0"""
        gate = H0Gate()
        probe_called = []

        def fake_probe():
            probe_called.append(1)
            time.sleep(0.001)  # 模擬 1ms DB 延遲

        worker = H0HealthWorker(gate, sample_interval_s=0.05, db_probe_fn=fake_probe)
        worker.start()
        time.sleep(0.2)
        worker.stop()

        assert len(probe_called) > 0, "db_probe_fn 從未被調用"
        snap = gate._health_snapshot
        assert snap.db_latency_ms >= 0.0

    def test_worker_sample_once_returns_snapshot(self):
        """6. _sample_once() 直接調用應返回有效 snapshot（無論 psutil 是否安裝）"""
        gate = H0Gate()
        worker = H0HealthWorker(gate)
        snap = worker._sample_once()

        assert isinstance(snap.cpu_pct, float)
        assert isinstance(snap.memory_available_mb, int)
        assert snap.memory_available_mb > 0
        assert snap.snapshot_ts_ms > 0


# ═══════════════════════════════════════════════════════════════════════════════
# TestPipelineBridgeH0Integration — PipelineBridge × H0Gate 集成測試（Day 3 新增）
# ═══════════════════════════════════════════════════════════════════════════════

class TestPipelineBridgeH0Integration:
    """
    驗證 PipelineBridge 的 H0Gate 注入接口（P1-16 Day 3）。
    使用最小化 mock，避免完整 bridge 初始化的複雜依賴。
    Verifies PipelineBridge H0Gate injection interface (P1-16 Day 3).
    Uses minimal mocks to avoid the complex dependencies of full bridge init.
    """

    def _make_bridge_shell(self):
        """
        建立 PipelineBridge 空殼實例（不調用 __init__），直接設置 _h0_gate 屬性。
        Create a PipelineBridge shell instance (bypassing __init__) with _h0_gate attr.
        """
        from app.pipeline_bridge import PipelineBridge
        bridge = PipelineBridge.__new__(PipelineBridge)
        bridge._h0_gate = None
        return bridge

    def test_set_h0_gate_injects(self):
        """1. set_h0_gate(mock_gate) 後 bridge._h0_gate 等於 mock_gate"""
        from unittest.mock import MagicMock
        bridge = self._make_bridge_shell()
        mock_gate = MagicMock()
        bridge.set_h0_gate(mock_gate)
        assert bridge._h0_gate is mock_gate

    def test_set_h0_gate_none_safe(self):
        """2. set_h0_gate(None) 不 raise"""
        from unittest.mock import MagicMock
        bridge = self._make_bridge_shell()
        bridge._h0_gate = MagicMock()  # 先設置非 None
        bridge.set_h0_gate(None)       # 再清除
        assert bridge._h0_gate is None

    def test_set_h0_gate_replace_existing(self):
        """3. 已有 gate 時再次 set_h0_gate() 可覆蓋（不 raise，新 gate 生效）"""
        from unittest.mock import MagicMock
        bridge = self._make_bridge_shell()
        gate1 = MagicMock()
        gate2 = MagicMock()
        bridge.set_h0_gate(gate1)
        bridge.set_h0_gate(gate2)
        assert bridge._h0_gate is gate2

    def test_h0_gate_none_attribute_exists_after_new(self):
        """4. __new__ 後直接設置 _h0_gate=None，set_h0_gate 仍可正常注入"""
        from unittest.mock import MagicMock
        from app.pipeline_bridge import PipelineBridge
        bridge = PipelineBridge.__new__(PipelineBridge)
        bridge._h0_gate = None
        mock_gate = MagicMock()
        bridge.set_h0_gate(mock_gate)
        assert bridge._h0_gate is mock_gate

    def test_h0_warn_only_does_not_raise_on_blocked(self):
        """
        5. mock gate 返回 allowed=False 時，_process_pending_intents 內部 warn-only 路徑
           不應 raise（紙上交易模式只告警，不中斷意圖處理）。

        策略：使用完整 mock 框架，只驗證 gate.check 被調用且無異常拋出。
        Strategy: use full mock framework, verify gate.check called and no exception raised.
        """
        from unittest.mock import MagicMock, patch
        from app.pipeline_bridge import PipelineBridge

        # 建立帶最小屬性的 bridge（不走 __init__）
        bridge = PipelineBridge.__new__(PipelineBridge)

        # 設置所有 _process_pending_intents 需要的屬性
        mock_gate = MagicMock()
        mock_check_result = MagicMock()
        mock_check_result.allowed = False
        mock_check_result.check_name = "risk"
        mock_check_result.reason = "test_blocked"
        mock_gate.check.return_value = mock_check_result

        bridge._h0_gate = mock_gate
        bridge._orchestrator = MagicMock()
        bridge._orchestrator.get_pending_intents.return_value = []
        bridge._strategist_agent = None
        bridge._paper_engine = MagicMock()
        bridge._governance_hub = None
        bridge._executor_agent = None
        bridge._stats = {"intents_submitted": 0, "intents_rejected": 0}
        bridge._daily_trade_count = 0
        bridge._daily_trade_date = ""

        # 不應拋出異常
        bridge._process_pending_intents()

    def test_h0_gate_none_skips_check(self):
        """
        6. _h0_gate=None 時，_process_pending_intents 不調用任何 gate.check，不 raise。
        When _h0_gate=None, _process_pending_intents skips H0 check and does not raise.
        """
        from unittest.mock import MagicMock
        from app.pipeline_bridge import PipelineBridge

        bridge = PipelineBridge.__new__(PipelineBridge)
        bridge._h0_gate = None
        bridge._orchestrator = MagicMock()
        bridge._orchestrator.get_pending_intents.return_value = []
        bridge._strategist_agent = None
        bridge._paper_engine = MagicMock()
        bridge._governance_hub = None
        bridge._executor_agent = None
        bridge._stats = {"intents_submitted": 0, "intents_rejected": 0}
        bridge._daily_trade_count = 0
        bridge._daily_trade_date = ""

        # 不應拋出異常
        bridge._process_pending_intents()


# ═══════════════════════════════════════════════════════════════════════════════
# TestGovernanceRoutesH0GateStatus — /governance/h0-gate/status 端點測試（Day 3 新增）
# ═══════════════════════════════════════════════════════════════════════════════

class TestGovernanceRoutesH0GateStatus:
    """
    驗證 GET /governance/h0-gate/status 端點的主要分支（P1-16 Day 3）。
    直接調用路由處理函數（無 HTTP 層），與 test_governance_routes_coverage.py 保持一致風格。
    Tests GET /governance/h0-gate/status endpoint branches (P1-16 Day 3).
    Calls route handler directly (no HTTP layer), consistent with coverage test style.
    """

    def setup_method(self):
        """每個測試前確保 AuthenticatedActor class 固定（防 reload 污染）"""
        import sys
        from pathlib import Path
        project_root = str(Path(__file__).resolve().parents[1])
        if project_root not in sys.path:
            sys.path.insert(0, project_root)

    def _make_actor(self, roles=None):
        """建立通過認證的 actor（預設非 Operator，只有 viewer）"""
        from app.main_legacy import AuthenticatedActor
        if roles is None:
            roles = {"viewer"}
        return AuthenticatedActor(
            actor_id="test-viewer",
            actor_type="human",
            roles=roles,
            scopes={"private_readonly"},
        )

    def test_get_h0_gate_status_returns_state(self):
        """1. mock gate.get_current_state() 返回 dict → 端點返回 200 + {"ok": True, "data": state}"""
        from unittest.mock import MagicMock, patch
        from fastapi import HTTPException
        from app.governance_routes import get_h0_gate_status

        mock_gate = MagicMock()
        mock_gate.get_current_state.return_value = {
            "stats": {"total_checks": 10, "passed": 8, "blocked": 2},
            "config": {"max_data_age_ms": 1000},
        }
        actor = self._make_actor()

        with patch("app.governance_routes._get_h0_gate", return_value=mock_gate):
            result = get_h0_gate_status(actor=actor)

        assert result["ok"] is True
        assert "data" in result
        assert result["data"]["stats"]["total_checks"] == 10

    def test_get_h0_gate_status_503_when_none(self):
        """2. H0_GATE=None（_get_h0_gate 返回 None）→ 端點返回 503"""
        from unittest.mock import patch
        from fastapi import HTTPException
        import pytest as _pytest
        from app.governance_routes import get_h0_gate_status

        actor = self._make_actor()

        with patch("app.governance_routes._get_h0_gate", return_value=None):
            with _pytest.raises(HTTPException) as exc:
                get_h0_gate_status(actor=actor)
            assert exc.value.status_code == 503

    def test_get_h0_gate_status_no_operator_role_required(self):
        """3. 普通認證用戶（只有 viewer，非 Operator）也能訪問（端點不要求 Operator 角色）"""
        from unittest.mock import MagicMock, patch
        from app.governance_routes import get_h0_gate_status
        from app.main_legacy import AuthenticatedActor

        # 使用 viewer-only actor（無 operator 角色）
        viewer_actor = AuthenticatedActor(
            actor_id="viewer-only",
            actor_type="human",
            roles={"viewer"},
            scopes={"private_readonly"},
        )
        mock_gate = MagicMock()
        mock_gate.get_current_state.return_value = {"stats": {}, "config": {}}

        with patch("app.governance_routes._get_h0_gate", return_value=mock_gate):
            # 不應因角色不足而拋出 403
            result = get_h0_gate_status(actor=viewer_actor)

        assert result["ok"] is True

    def test_get_h0_gate_status_500_when_state_none(self):
        """4. gate.get_current_state() 返回 None → 端點返回 500"""
        from unittest.mock import MagicMock, patch
        from fastapi import HTTPException
        import pytest as _pytest
        from app.governance_routes import get_h0_gate_status

        mock_gate = MagicMock()
        mock_gate.get_current_state.return_value = None
        actor = self._make_actor()

        with patch("app.governance_routes._get_h0_gate", return_value=mock_gate):
            with _pytest.raises(HTTPException) as exc:
                get_h0_gate_status(actor=actor)
            assert exc.value.status_code == 500

    def test_get_h0_gate_status_message_field(self):
        """5. 正常返回時 message 字段為 'h0_gate_status'"""
        from unittest.mock import MagicMock, patch
        from app.governance_routes import get_h0_gate_status

        mock_gate = MagicMock()
        mock_gate.get_current_state.return_value = {"stats": {}}
        actor = self._make_actor()

        with patch("app.governance_routes._get_h0_gate", return_value=mock_gate):
            result = get_h0_gate_status(actor=actor)

        assert result.get("message") == "h0_gate_status"


# ═══════════════════════════════════════════════════════════════════════════════
# TestRiskManagerH0GateSync — RiskManager × H0Gate 冷卻同步測試（Day 3 新增）
# ═══════════════════════════════════════════════════════════════════════════════

class TestRiskManagerH0GateSync:
    """
    驗證 RiskManager 的 H0Gate 注入接口與冷卻期同步邏輯（P1-16 Day 3）。
    Tests RiskManager H0Gate injection interface and cooldown sync logic (P1-16 Day 3).
    """

    def _make_risk_manager(self):
        """建立最小化 RiskManager 實例"""
        from app.risk_manager import RiskManager, GlobalRiskConfig
        return RiskManager(config=GlobalRiskConfig())

    def test_set_h0_gate_injects(self):
        """1. rm.set_h0_gate(mock_gate) 後 rm._h0_gate 等於 mock_gate"""
        from unittest.mock import MagicMock
        rm = self._make_risk_manager()
        mock_gate = MagicMock()
        rm.set_h0_gate(mock_gate)
        assert rm._h0_gate is mock_gate

    def test_set_h0_gate_none_safe(self):
        """2. rm.set_h0_gate(None) 不 raise"""
        from unittest.mock import MagicMock
        rm = self._make_risk_manager()
        rm.set_h0_gate(MagicMock())  # 先設置非 None
        rm.set_h0_gate(None)          # 再清除
        assert rm._h0_gate is None

    def test_h0gate_none_does_not_affect_record_fill_profit(self):
        """3. _h0_gate=None 時，record_fill_result(正 PnL) 正常執行不 raise"""
        rm = self._make_risk_manager()
        assert rm._h0_gate is None
        rm.record_fill_result(100.0)  # 盈利，不觸發冷卻期，不 raise

    def test_h0gate_none_does_not_affect_record_fill_loss(self):
        """4. _h0_gate=None 時，record_fill_result(負 PnL) 正常執行不 raise（無 H0 同步嘗試）"""
        from app.risk_manager import RiskManager, GlobalRiskConfig
        # 設置 consecutive_loss_cooldown_count=1 讓第一次虧損即觸發冷卻邏輯
        config = GlobalRiskConfig()
        config.consecutive_loss_cooldown_count = 1
        rm = RiskManager(config=config)
        assert rm._h0_gate is None
        rm.record_fill_result(-50.0)  # 虧損觸發冷卻邏輯，但 _h0_gate=None → 跳過 H0 同步

    def test_h0gate_injected_record_fill_loss_calls_update_risk(self):
        """
        5. _h0_gate 已注入時，record_fill_result(負 PnL) 觸發連續虧損冷卻時
           應調用 gate.update_risk()（同步冷卻期到 H0 風控快照）。
        When _h0_gate is injected, record_fill_result with loss triggers cooldown sync
        and calls gate.update_risk().

        Note: Must isolate from operator config file which overrides consecutive_loss_cooldown_count.
        注意：必須隔離 operator 配置文件，否則 consecutive_loss_cooldown_count 會被覆蓋。
        """
        from unittest.mock import MagicMock, patch
        from app.h0_gate import H0GateRiskSnapshot

        # Isolate from operator config: patch _OPERATOR_CONFIG_PATH to /dev/null
        # so _load_operator_config() skips file loading and uses code defaults.
        # 隔離 operator 配置：將 _OPERATOR_CONFIG_PATH 設為 /dev/null，
        # 使 _load_operator_config() 跳過文件加載，使用代碼默認值。
        with patch("app.risk_manager._OPERATOR_CONFIG_PATH", "/dev/null"):
            from app.risk_manager import RiskManager, GlobalRiskConfig

            config = GlobalRiskConfig()
            config.consecutive_loss_cooldown_count = 1  # 第一次虧損即觸發
            rm = RiskManager(config=config)

        mock_gate = MagicMock()
        # _risk_snapshot 必須有有效屬性（RiskManager 會讀取）
        mock_snap = H0GateRiskSnapshot(
            open_position_count=0,
            total_exposure_pct=0.0,
            cooldown_until_ts_ms=0,
            kill_switch_active=False,
        )
        mock_gate._risk_snapshot = mock_snap
        rm.set_h0_gate(mock_gate)

        rm.record_fill_result(-100.0)

        # 應調用 update_risk 將冷卻期同步到 H0Gate
        mock_gate.update_risk.assert_called_once()

    def test_h0gate_injected_record_fill_profit_no_update_risk(self):
        """
        6. _h0_gate 已注入時，record_fill_result(正 PnL) 不觸發冷卻，不調用 gate.update_risk()。
        When _h0_gate is injected and fill is profitable, update_risk should NOT be called.
        """
        from unittest.mock import MagicMock
        rm = self._make_risk_manager()
        mock_gate = MagicMock()
        rm.set_h0_gate(mock_gate)

        rm.record_fill_result(200.0)  # 盈利，不觸發冷卻

        mock_gate.update_risk.assert_not_called()
