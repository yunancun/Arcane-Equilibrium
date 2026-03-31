"""
H0Gate Cooldown Integration Smoke Tests / H0 門控冷卻期聯動端對端煙霧測試

MODULE_NOTE (中文):
  驗證 H0Gate cooldown 聯動鏈路：
    RiskManager 觸發 cooldown → H0Gate.update_risk() 被調用 → H0Gate.check() 阻擋

  這是 Phase 1 Batch 1B 的第一項測試，僅測試行為，不修改生產代碼。
  純煙霧測試（smoke test），覆蓋五個核心場景。

MODULE_NOTE (English):
  Validates the H0Gate cooldown integration chain:
    RiskManager triggers cooldown → H0Gate.update_risk() is called → H0Gate.check() blocks

  This is the first test suite for Phase 1 Batch 1B. Read-only test: no production
  code is modified. Covers five core scenarios as end-to-end smoke tests.

Governance reference:
  DOC-02 §3: H0 Gate deterministic gating, <1ms SLA
  §5.5 Principle 5: survival before profit — cooldown is a survival mechanism
  §5.6 Principle 6: fail to safe — system must block during cooldown
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

# ── Imports under test ────────────────────────────────────────────────────────
from app.h0_gate import H0Gate, H0GateConfig, H0GateRiskSnapshot
from app.risk_manager import GlobalRiskConfig, RiskManager


# ── Helper factory / 輔助工廠 ─────────────────────────────────────────────────

def _make_passing_gate(symbol: str = "BTCUSDT") -> H0Gate:
    """
    Create an H0Gate pre-configured to pass all checks except cooldown.
    建立一個對所有檢查（除冷卻期外）均通過的 H0Gate 實例。

    - Sets a fresh price tick for the symbol (freshness passes)
    - Leaves health snapshot at default (all zero = healthy)
    - Sets system_mode = "active" (eligibility passes)
    """
    gate = H0Gate()
    now_ms = int(time.time() * 1000)
    gate.update_price_ts(symbol, now_ms)          # freshness: fresh tick
    gate.set_system_mode("active")                 # eligibility: active mode
    # Health snapshot default is healthy (cpu=0%, mem=9999MB, db_lat=0ms)
    # Risk snapshot default: no positions, no cooldown
    return gate


# ═══════════════════════════════════════════════════════════════════════════════
# Test Class / 測試類
# ═══════════════════════════════════════════════════════════════════════════════

class TestH0GateCooldownIntegration:
    """
    End-to-end smoke tests for the RiskManager → H0Gate cooldown linkage.
    RiskManager → H0Gate 冷卻期聯動端對端煙霧測試。

    Covers five scenarios:
    涵蓋五個場景：
      1. RiskManager pushes cooldown to H0Gate (mock H0Gate)
      2. H0Gate blocks when cooldown_until is in the future
      3. H0Gate allows when cooldown_until is in the past (expired)
      4. cooldown_seconds=0 / cooldown_until=0 does not block
      5. Blocked result reason contains the word "cooldown"
    """

    # ── Scenario 1 ───────────────────────────────────────────────────────────

    def test_risk_manager_pushes_cooldown_to_h0gate(self):
        """
        Scenario 1: RiskManager triggers consecutive losses → H0Gate.update_risk() called.
        場景 1：RiskManager 觸發連續虧損冷卻期 → H0Gate.update_risk() 應被調用。

        Arrange:
          - RiskManager with consecutive_loss_cooldown_count=3, 30-minute cooldown
          - A mock H0Gate injected via set_h0_gate()
        Act:
          - Record 3 consecutive losses (pnl < 0) via record_fill_result()
        Assert:
          - mock_gate.update_risk() was called at least once with an H0GateRiskSnapshot
            whose cooldown_until_ts_ms is in the future
        """
        # Arrange
        config = GlobalRiskConfig()
        config.consecutive_loss_cooldown_count = 3
        config.consecutive_loss_cooldown_minutes = 30.0
        rm = RiskManager(config=config)

        mock_gate = MagicMock(spec=H0Gate)
        # update_risk is called with H0GateRiskSnapshot; gate._risk_snapshot must exist
        mock_gate._risk_snapshot = H0GateRiskSnapshot()
        rm.set_h0_gate(mock_gate)

        # Act: record 3 consecutive losses
        now_ms = int(time.time() * 1000)
        rm.record_fill_result(-100.0)
        rm.record_fill_result(-100.0)
        rm.record_fill_result(-100.0)   # 3rd loss → triggers cooldown

        # Assert
        mock_gate.update_risk.assert_called()
        call_args = mock_gate.update_risk.call_args[0]
        assert len(call_args) == 1, "update_risk should receive exactly one positional argument"
        snapshot = call_args[0]
        assert isinstance(snapshot, H0GateRiskSnapshot), (
            "update_risk should be called with an H0GateRiskSnapshot instance"
        )
        assert snapshot.cooldown_until_ts_ms > now_ms, (
            f"cooldown_until_ts_ms={snapshot.cooldown_until_ts_ms} "
            f"should be in the future (now={now_ms})"
        )

    # ── Scenario 2 ───────────────────────────────────────────────────────────

    def test_h0gate_blocks_during_cooldown(self):
        """
        Scenario 2: H0Gate.update_risk(cooldown_until=future) → check() returns allowed=False.
        場景 2：update_risk 注入未來冷卻截止時間 → check() 應返回 allowed=False。

        Arrange:
          - H0Gate pre-configured to pass all non-cooldown checks
          - Inject risk snapshot with cooldown_until_ts_ms = now + 30 minutes
        Act:
          - Call gate.check("BTCUSDT", "linear")
        Assert:
          - result.allowed is False
          - result.check_name == "cooldown"
        """
        # Arrange
        gate = _make_passing_gate("BTCUSDT")
        future_ts_ms = int(time.time() * 1000) + 30 * 60 * 1000  # +30 minutes
        snap = H0GateRiskSnapshot(
            open_position_count=0,
            total_exposure_pct=0.0,
            cooldown_until_ts_ms=future_ts_ms,
            kill_switch_active=False,
            snapshot_ts_ms=int(time.time() * 1000),
        )
        gate.update_risk(snap)

        # Act
        result = gate.check("BTCUSDT", "linear")

        # Assert
        assert result.allowed is False, (
            "H0Gate must block when cooldown_until_ts_ms is in the future"
        )
        assert result.check_name == "cooldown", (
            f"check_name should be 'cooldown', got '{result.check_name}'"
        )

    # ── Scenario 3 ───────────────────────────────────────────────────────────

    def test_h0gate_allows_after_cooldown_expires(self):
        """
        Scenario 3: update_risk with past cooldown_until → check() returns allowed=True.
        場景 3：冷卻截止時間已過 → check() 應返回 allowed=True（冷卻已解除）。

        Arrange:
          - H0Gate pre-configured to pass all non-cooldown checks
          - Inject risk snapshot with cooldown_until_ts_ms = now - 1 second (past)
        Act:
          - Call gate.check("BTCUSDT", "linear")
        Assert:
          - result.allowed is True (cooldown expired, gate should pass)
        """
        # Arrange
        gate = _make_passing_gate("BTCUSDT")
        past_ts_ms = int(time.time() * 1000) - 1000  # 1 second in the past
        snap = H0GateRiskSnapshot(
            open_position_count=0,
            total_exposure_pct=0.0,
            cooldown_until_ts_ms=past_ts_ms,
            kill_switch_active=False,
            snapshot_ts_ms=int(time.time() * 1000),
        )
        gate.update_risk(snap)

        # Act
        result = gate.check("BTCUSDT", "linear")

        # Assert
        assert result.allowed is True, (
            f"H0Gate should allow when cooldown has expired; got: "
            f"allowed={result.allowed}, reason='{result.reason}'"
        )

    # ── Scenario 4 ───────────────────────────────────────────────────────────

    def test_h0gate_cooldown_zero_does_not_block(self):
        """
        Scenario 4: cooldown_until_ts_ms=0 (default) → check() returns allowed=True.
        場景 4：冷卻截止時間為 0（默認，表示無冷卻）→ check() 應返回 allowed=True。

        Arrange:
          - H0Gate pre-configured to pass all non-cooldown checks
          - Risk snapshot uses default cooldown_until_ts_ms=0
        Act:
          - Call gate.check("BTCUSDT", "linear")
        Assert:
          - result.allowed is True (no cooldown active)
        """
        # Arrange
        gate = _make_passing_gate("BTCUSDT")
        snap = H0GateRiskSnapshot(
            open_position_count=0,
            total_exposure_pct=0.0,
            cooldown_until_ts_ms=0,    # 0 = no cooldown
            kill_switch_active=False,
            snapshot_ts_ms=int(time.time() * 1000),
        )
        gate.update_risk(snap)

        # Act
        result = gate.check("BTCUSDT", "linear")

        # Assert
        assert result.allowed is True, (
            "H0Gate must allow when cooldown_until_ts_ms=0 (no cooldown)"
        )

    # ── Scenario 5 ───────────────────────────────────────────────────────────

    def test_h0gate_cooldown_check_includes_reason(self):
        """
        Scenario 5: Blocked due to cooldown → result.reason contains 'cooldown'.
        場景 5：因冷卻期被阻擋時 → result.reason 應包含 'cooldown' 字樣。

        Arrange:
          - H0Gate pre-configured to pass all non-cooldown checks
          - Inject future cooldown_until_ts_ms
        Act:
          - Call gate.check("BTCUSDT", "linear")
        Assert:
          - result.allowed is False
          - "cooldown" appears in result.reason (case-insensitive)
          - result.check_name == "cooldown"
        """
        # Arrange
        gate = _make_passing_gate("BTCUSDT")
        future_ts_ms = int(time.time() * 1000) + 60 * 1000  # +60 seconds
        snap = H0GateRiskSnapshot(
            open_position_count=0,
            total_exposure_pct=0.0,
            cooldown_until_ts_ms=future_ts_ms,
            kill_switch_active=False,
            snapshot_ts_ms=int(time.time() * 1000),
        )
        gate.update_risk(snap)

        # Act
        result = gate.check("BTCUSDT", "linear")

        # Assert
        assert result.allowed is False
        assert "cooldown" in result.reason.lower(), (
            f"reason should contain 'cooldown', got: '{result.reason}'"
        )
        assert result.check_name == "cooldown", (
            f"check_name should be 'cooldown', got: '{result.check_name}'"
        )
