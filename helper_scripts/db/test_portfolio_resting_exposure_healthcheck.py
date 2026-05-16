#!/usr/bin/env python3
"""Unit tests for passive_wait_healthcheck ``[68]`` portfolio_resting_exposure_lineage
（P2-PORTFOLIO-RESTING-58-HEALTHCHECK，2026-05-16 升 P1 per FA Stage 1 demo
啟前 mandatory）。

對應 P1-PORTFOLIO-RESTING-EXPOSURE-1 Rust IMPL（commit `9980448a`）的
healthcheck follow-up。test fixture 涵蓋 PASS / WARN / FAIL 三狀態 + 邊界：
  PASS = 4 條件全綠（notional < 80% cap + divergence < 50% + per-symbol < 80%）
  WARN = 1-2 條件偏移（notional ≥ 80% cap 但 < 100% / divergence 50-100% / per-symbol 80-150%）
  FAIL = notional ≥ cap OR divergence ≥ 100% OR per-symbol > 150% OR resting-only > 50% cap
  Edge case：snapshot 缺 / 表缺 / 無 Working orders / REQUIRED env
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_HELPER_SCRIPTS_DIR = os.path.dirname(_THIS_DIR)
_SRV_ROOT = os.path.dirname(_HELPER_SCRIPTS_DIR)
sys.path.insert(0, _SRV_ROOT)

from helper_scripts.db.passive_wait_healthcheck.checks_portfolio_resting_exposure import (  # noqa: E402
    check_68_portfolio_resting_exposure,
)


def _mock_cursor(fetchone_rows: list, fetchall_rows: list[list] | None = None) -> MagicMock:
    """構造 mock cursor，fetchone 依序回 list[i]，fetchall 依序回 list[i]。

    cursor.connection.rollback 是 no-op；execute 不引發。
    """
    cur = MagicMock()
    cur.connection = MagicMock()
    cur.connection.rollback = MagicMock()
    cur.fetchone.side_effect = fetchone_rows
    if fetchall_rows is not None:
        cur.fetchall.side_effect = fetchall_rows
    return cur


def _write_snapshot(path: Path, balance: float, positions: list[dict]) -> None:
    """將 paper_state snapshot 寫到 path（mimics Rust persistence.rs 格式）。"""
    snap = {
        "schema_version": "2.0.0",
        "paper_state": {
            "balance": balance,
            "initial_balance": balance,
            "peak_balance": balance,
            "total_realized_pnl": 0.0,
            "total_fees": 0.0,
            "trade_count": 0,
            "positions": positions,
        },
    }
    path.write_text(json.dumps(snap), encoding="utf-8")


class TestPortfolioRestingExposureHealthcheck(unittest.TestCase):
    """[68] check_68_portfolio_resting_exposure — PASS/WARN/FAIL + edge cases。"""

    def setUp(self) -> None:
        """保存 env + 構造 tmp data_dir + tmp base_dir 模擬 snapshot + TOML。"""
        self._old_env = dict(os.environ)
        self._tmp_data = tempfile.TemporaryDirectory()
        self._tmp_base = tempfile.TemporaryDirectory()
        os.environ["OPENCLAW_DATA_DIR"] = self._tmp_data.name
        os.environ["OPENCLAW_BASE_DIR"] = self._tmp_base.name

        # 構 risk_config_demo.toml（cap = 65%）讓 test 有 deterministic cap reference
        risk_dir = Path(self._tmp_base.name) / "settings" / "risk_control_rules"
        risk_dir.mkdir(parents=True, exist_ok=True)
        # 兩種 layout 任挑一：頂層 key（與 risk_config.toml 結構對齊）
        toml_content = (
            "total_exposure_max_pct = 150.0\n"
            "correlated_exposure_max_pct = 65.0\n"
            "leverage_max = 50.0\n"
        )
        for name in (
            "risk_config_paper.toml",
            "risk_config_demo.toml",
            "risk_config_live.toml",
        ):
            (risk_dir / name).write_text(toml_content, encoding="utf-8")

    def tearDown(self) -> None:
        """還原 env + 清理 tmp dir。"""
        os.environ.clear()
        os.environ.update(self._old_env)
        self._tmp_data.cleanup()
        self._tmp_base.cleanup()

    # ============================================================
    # Edge case 1：trading.orders 或 order_state_changes 表缺 → 對所有
    # engine：snapshot 也都缺（默認無 file 寫）→ PASS-skipped 訊息
    # ============================================================

    def test_no_snapshots_pass_skip(self) -> None:
        """所有 engine snapshot 都缺 → PASS-skipped pre-deploy 不阻塞。"""
        # trading.orders 表不存在 → 但因 snapshot 都缺，根本走不到 PG query
        cur = _mock_cursor([], [])

        status, msg = check_68_portfolio_resting_exposure(cur)

        self.assertEqual(status, "PASS")
        self.assertIn("skipped", msg.lower())
        self.assertIn("不存在", msg)

    # ============================================================
    # Edge case 2：snapshot 存在 + trading.orders 表缺 → 對該 engine WARN
    # ============================================================

    def test_table_absent_returns_warn(self) -> None:
        """snapshot 在但 trading.orders 表缺 → engine 標 PG_FAIL WARN。

        逐 engine 跑（4 engine），每 engine 一次 to_regclass。snapshot 只配
        paper（demo/live/live_demo 都跳過）。
        """
        # 只寫 paper snapshot
        data_dir = Path(self._tmp_data.name)
        _write_snapshot(
            data_dir / "pipeline_snapshot_paper.json",
            balance=10000.0,
            positions=[
                {"symbol": "BTCUSDT", "is_long": True, "qty": 0.001, "entry_price": 60000.0}
            ],
        )
        # paper 的 to_regclass 回兩個 False（兩表都缺）；其他 engine 沒 snapshot 不查 DB
        cur = _mock_cursor(
            [
                (False, False),  # paper 表缺
            ],
            [],
        )

        status, msg = check_68_portfolio_resting_exposure(cur)

        self.assertEqual(status, "WARN")
        self.assertIn("paper=PG_FAIL", msg)
        self.assertIn("trading.orders 或 order_state_changes 缺", msg)

    # ============================================================
    # Fixture 1：PASS — 4 條件全綠（filled 健康 + resting 小）
    # ============================================================

    def test_fixture_1_all_pass_healthy_demo(self) -> None:
        """Fixture 1 PASS：demo engine + filled BTC long 60USD + resting small。

        Cap = 65% × 10000 = 6500；total long ≈ 60+10=70，遠 < 80% cap = 5200。
        Divergence = 10/60 = 16.7% < 50%。Per-symbol r/f = 10/60 = 16.7% < 80%。
        """
        data_dir = Path(self._tmp_data.name)
        _write_snapshot(
            data_dir / "pipeline_snapshot_demo.json",
            balance=10000.0,
            positions=[
                {"symbol": "BTCUSDT", "is_long": True, "qty": 0.001, "entry_price": 60000.0},
            ],
        )

        # 4 engine 各一次 to_regclass + 一次 aggregate；其他 3 engine snapshot 缺
        # demo: to_regclass→(True,True), aggregate→[BTCUSDT/Buy/10/1]
        cur = _mock_cursor(
            [
                (True, True),  # demo: 兩表都在
            ],
            [
                [("BTCUSDT", "Buy", 10.0, 1)],  # demo: 1 row Working
            ],
        )

        status, msg = check_68_portfolio_resting_exposure(cur)

        self.assertEqual(status, "PASS", msg)
        self.assertIn("healthy", msg)
        self.assertIn("demo=PASS", msg)
        self.assertIn("bal=10000", msg)
        self.assertIn("divergence=16.7%", msg)

    # ============================================================
    # Fixture 2：WARN — divergence ≥ 50% 但 < 100%
    # ============================================================

    def test_fixture_2_warn_divergence_50pct(self) -> None:
        """Fixture 2 WARN：filled 100USD + resting 70USD → divergence 70% ∈ [50%, 100%)。"""
        data_dir = Path(self._tmp_data.name)
        _write_snapshot(
            data_dir / "pipeline_snapshot_demo.json",
            balance=10000.0,
            positions=[
                # filled BTC long: 0.001 × 60000 = 60 + filled ETH long: 0.01 × 4000 = 40 = 100
                {"symbol": "BTCUSDT", "is_long": True, "qty": 0.001, "entry_price": 60000.0},
                {"symbol": "ETHUSDT", "is_long": True, "qty": 0.01, "entry_price": 4000.0},
            ],
        )

        # resting: BTC long 50 + ETH long 20 = 70 → divergence = 70/100 = 70%
        cur = _mock_cursor(
            [(True, True)],
            [
                [
                    ("BTCUSDT", "Buy", 50.0, 1),
                    ("ETHUSDT", "Buy", 20.0, 1),
                ],
            ],
        )

        status, msg = check_68_portfolio_resting_exposure(cur)

        self.assertEqual(status, "WARN", msg)
        self.assertIn("approaching limit", msg)
        self.assertIn("divergence=70.0%", msg)
        self.assertIn("demo=WARN", msg)

    # ============================================================
    # Fixture 3：FAIL — divergence ≥ 100% (resting 完全超過 filled)
    # ============================================================

    def test_fixture_3_fail_divergence_over_100pct(self) -> None:
        """Fixture 3 FAIL：filled 60USD + resting 100USD → divergence 167% ≥ 100%。"""
        data_dir = Path(self._tmp_data.name)
        _write_snapshot(
            data_dir / "pipeline_snapshot_demo.json",
            balance=10000.0,
            positions=[
                {"symbol": "BTCUSDT", "is_long": True, "qty": 0.001, "entry_price": 60000.0},
            ],
        )

        cur = _mock_cursor(
            [(True, True)],
            [
                [
                    ("BTCUSDT", "Buy", 100.0, 5),  # 5 Working orders 各 20 = 100
                ],
            ],
        )

        status, msg = check_68_portfolio_resting_exposure(cur)

        self.assertEqual(status, "FAIL", msg)
        self.assertIn("breach", msg)
        self.assertIn("divergence=166.7%", msg)
        self.assertIn("per_symbol_fail", msg)  # r/f=100/60=1.67 > 1.5 也觸 fail

    # ============================================================
    # Edge case 3：resting-only 無 filled position ≥ 50% cap → FAIL
    # ============================================================

    def test_resting_only_over_50pct_cap_fail(self) -> None:
        """resting-only (filled=0) 且 r_total ≥ 0.5×cap → per_symbol_fail 觸 FAIL。

        cap = 65% × 10000 = 6500；50% cap = 3250。resting BTC long = 3500 ≥ 3250。
        但 long_total = 3500 vs cap_warn = 5200 → 沒到 80% cap → aggregate PASS
        per-symbol fail 直接觸 FAIL（FA verdict 認為這是 Stage 1 demo 必看的訊號）。
        """
        data_dir = Path(self._tmp_data.name)
        _write_snapshot(
            data_dir / "pipeline_snapshot_demo.json",
            balance=10000.0,
            positions=[],  # 無 filled position
        )

        cur = _mock_cursor(
            [(True, True)],
            [
                [
                    ("BTCUSDT", "Buy", 3500.0, 1),  # resting-only 3500 > 3250 (50% cap)
                ],
            ],
        )

        status, msg = check_68_portfolio_resting_exposure(cur)

        self.assertEqual(status, "FAIL", msg)
        self.assertIn("breach", msg)
        self.assertIn("resting-only:3500", msg)

    # ============================================================
    # Edge case 4：REQUIRED env 設定 → WARN 升 FAIL
    # ============================================================

    def test_required_env_escalates_warn_to_fail(self) -> None:
        """OPENCLAW_PORTFOLIO_RESTING_HEALTH_REQUIRED=1 → WARN 升 FAIL。"""
        os.environ["OPENCLAW_PORTFOLIO_RESTING_HEALTH_REQUIRED"] = "1"
        data_dir = Path(self._tmp_data.name)
        _write_snapshot(
            data_dir / "pipeline_snapshot_demo.json",
            balance=10000.0,
            positions=[
                {"symbol": "BTCUSDT", "is_long": True, "qty": 0.001, "entry_price": 60000.0},
                {"symbol": "ETHUSDT", "is_long": True, "qty": 0.01, "entry_price": 4000.0},
            ],
        )

        # 與 fixture 2 同數據（70% divergence WARN）
        cur = _mock_cursor(
            [(True, True)],
            [
                [
                    ("BTCUSDT", "Buy", 50.0, 1),
                    ("ETHUSDT", "Buy", 20.0, 1),
                ],
            ],
        )

        status, msg = check_68_portfolio_resting_exposure(cur)

        self.assertEqual(status, "FAIL", msg)  # WARN 被 REQUIRED 升 FAIL
        self.assertIn("breach", msg)
        self.assertIn("divergence=70.0%", msg)

    # ============================================================
    # Edge case 5：no Working orders (空) → PASS（穩態無分歧）
    # ============================================================

    def test_no_working_orders_pass(self) -> None:
        """有 filled positions 但 0 Working orders → divergence=0%，PASS。"""
        data_dir = Path(self._tmp_data.name)
        _write_snapshot(
            data_dir / "pipeline_snapshot_demo.json",
            balance=10000.0,
            positions=[
                {"symbol": "BTCUSDT", "is_long": True, "qty": 0.001, "entry_price": 60000.0},
            ],
        )

        cur = _mock_cursor(
            [(True, True)],
            [[]],  # 0 row
        )

        status, msg = check_68_portfolio_resting_exposure(cur)

        self.assertEqual(status, "PASS", msg)
        self.assertIn("healthy", msg)
        self.assertIn("resting=0", msg)
        self.assertIn("divergence=0.0%", msg)

    # ============================================================
    # Edge case 6：snapshot 缺欄位防禦（無 paper_state / positions 非 list）
    # ============================================================

    def test_malformed_snapshot_graceful_zero_balance(self) -> None:
        """snapshot 缺 paper_state → balance/positions 視為 0/空，divergence=0 PASS。"""
        data_dir = Path(self._tmp_data.name)
        # 寫一個沒 paper_state 的 snapshot
        (data_dir / "pipeline_snapshot_demo.json").write_text(
            json.dumps({"schema_version": "2.0.0"}), encoding="utf-8"
        )

        cur = _mock_cursor(
            [(True, True)],
            [[]],  # 0 row
        )

        status, msg = check_68_portfolio_resting_exposure(cur)

        # filled=0 / resting=0 → divergence=0 / 0 cap → PASS
        self.assertEqual(status, "PASS", msg)
        self.assertIn("healthy", msg)

    # ============================================================
    # Edge case 7：short side notional + cap 觸 WARN（驗 short 路徑）
    # ============================================================

    def test_short_side_warn_at_80pct_cap(self) -> None:
        """filled BTC short = 5000 + resting BTC short = 300 → short_total
        = 5300 ≥ 80% × cap(6500) = 5200 → WARN。

        驗 short 路徑（非 long）也走相同 cap usage gate；驗 80% cap WARN
        boundary。
        """
        data_dir = Path(self._tmp_data.name)
        _write_snapshot(
            data_dir / "pipeline_snapshot_demo.json",
            balance=10000.0,
            positions=[
                # filled BTC short: 0.1 × 50000 = 5000 (整數對齊，避免浮點誤差)
                {"symbol": "BTCUSDT", "is_long": False, "qty": 0.1, "entry_price": 50000.0},
            ],
        )

        # resting BTC short = 300 → short_total = 5300 ≥ 80% × 6500 = 5200
        cur = _mock_cursor(
            [(True, True)],
            [
                [
                    ("BTCUSDT", "Sell", 300.0, 1),
                ],
            ],
        )

        status, msg = check_68_portfolio_resting_exposure(cur)

        self.assertEqual(status, "WARN", msg)
        self.assertIn("short_total=5300", msg)
        self.assertIn("80%cap", msg)


if __name__ == "__main__":
    unittest.main()
