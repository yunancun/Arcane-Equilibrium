#!/usr/bin/env python3
"""Unit tests for passive_wait_healthcheck `[57]` W2 A4-C BTC→Alt Lead-Lag
panel 4 條件健康監測（W2-IMPL-3 2026-05-11，PA dispatch plan §3.3）。

3 fixture 對應 PASS / WARN / FAIL 三狀態 + 額外 boundary case：
  PASS = 4 條件全綠（age < 120s, cohort=7, extreme<5%, book非0非NULL）
  WARN = 1-2 條件偏移（age 120-300s OR extreme 5-20%）
  FAIL = age≥300s OR cohort<7 OR extreme≥20%
  Edge case：default-off / pre-deploy / 0 row / book placeholder
"""

from __future__ import annotations

import os
import sys
import unittest
from decimal import Decimal
from unittest.mock import MagicMock

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_HELPER_SCRIPTS_DIR = os.path.dirname(_THIS_DIR)
_SRV_ROOT = os.path.dirname(_HELPER_SCRIPTS_DIR)
sys.path.insert(0, _SRV_ROOT)

from helper_scripts.db.passive_wait_healthcheck.checks_btc_lead_lag import (  # noqa: E402
    check_57_btc_lead_lag_panel_health,
)


def _mock_cursor(fetchone_rows: list) -> MagicMock:
    """構造 mock cursor，fetchone 依序回 list[i]，cursor.connection.rollback 是 no-op。"""
    cur = MagicMock()
    cur.connection = MagicMock()
    cur.connection.rollback = MagicMock()
    cur.fetchone.side_effect = fetchone_rows
    return cur


class TestBtcLeadLagPanelHealthcheck(unittest.TestCase):
    """[57] check_57_btc_lead_lag_panel_health 3 fixture + 5 edge case 測試。"""

    def setUp(self) -> None:
        """每個 test case 保存 env，tearDown 還原；避免 cross-test 污染。"""
        self._old_env = dict(os.environ)

    def tearDown(self) -> None:
        """還原 env 到 setUp 前的狀態。"""
        os.environ.clear()
        os.environ.update(self._old_env)

    # ============================================================
    # Edge case 1：default-off → PASS-skip，不 query DB
    # ============================================================

    def test_default_off_pass_skip_without_query(self) -> None:
        """未設 OPENCLAW_W2_HEALTHCHECK_ENABLED → PASS-skip 不查 DB（pre-deploy 不阻塞）。"""
        os.environ.pop("OPENCLAW_W2_HEALTHCHECK_ENABLED", None)
        cur = _mock_cursor([])

        status, msg = check_57_btc_lead_lag_panel_health(cur)

        self.assertEqual(status, "PASS")
        self.assertIn("disabled by env", msg)
        cur.execute.assert_not_called()

    # ============================================================
    # Edge case 2：V088 panel.btc_lead_lag_panel 未 deploy → PASS-skip
    # ============================================================

    def test_v088_table_absent_pass_skip(self) -> None:
        """OPENCLAW_W2_HEALTHCHECK_ENABLED=1 但 V088 未 deploy → PASS-skip pre-deploy。"""
        os.environ["OPENCLAW_W2_HEALTHCHECK_ENABLED"] = "1"
        # to_regclass(...) 回 NULL（表不存在）
        cur = _mock_cursor([(None,)])

        status, msg = check_57_btc_lead_lag_panel_health(cur)

        self.assertEqual(status, "PASS")
        self.assertIn("ABSENT", msg)
        self.assertIn("V088 not yet deployed", msg)

    # ============================================================
    # Edge case 3：V088 deployed 但 0 row → PASS-skip post-deploy <60s window
    # ============================================================

    def test_v088_zero_rows_pass_skip_post_deploy(self) -> None:
        """V088 deployed 但 1h 內 0 row → PASS-skip（首次 deploy <60s 預期）。"""
        os.environ["OPENCLAW_W2_HEALTHCHECK_ENABLED"] = "1"
        # 第 1 row：to_regclass 回 True；第 2 row：aggregate 全 NULL（無 row）
        cur = _mock_cursor([
            (True,),
            (None, None, 0, 0, None, 0),
        ])

        status, msg = check_57_btc_lead_lag_panel_health(cur)

        self.assertEqual(status, "PASS")
        self.assertIn("0 rows in last", msg)

    # ============================================================
    # Fixture 1：PASS = 4 條件全綠
    # ============================================================
    # 對應 W2 IMPL-1+2 land + V088 deployed 7d 健康跑：
    #   age = 45s (< 120s PASS)
    #   cohort_size = 7 (= 7 PASS)
    #   total = 60 / extreme = 2 → ratio 3.3% (< 5% PASS)
    #   book_imb_abs_avg = 0.0237 (非 0 PASS)
    # 預設 OPENCLAW_W2_HEALTHCHECK_BOOK_REQUIRED=0 也 PASS（book 真實值）

    def test_fixture_1_all_four_conditions_pass(self) -> None:
        """Fixture 1 PASS：4 條件全綠 — producer 健康 + W2-IMPL-1 orderbook 接線生效。"""
        os.environ["OPENCLAW_W2_HEALTHCHECK_ENABLED"] = "1"
        # to_regclass=True / age=45s / cohort=7 / total=60 / extreme=2 / book_avg=0.0237 / book_n=60
        cur = _mock_cursor([
            (True,),
            (Decimal("45.2"), 7, 60, 2, Decimal("0.0237"), 60),
        ])

        status, msg = check_57_btc_lead_lag_panel_health(cur)

        self.assertEqual(status, "PASS", msg)
        self.assertIn("healthy", msg)
        self.assertIn("age=45.2s/PASS", msg)
        self.assertIn("cohort=7/7/PASS", msg)
        self.assertIn("extreme=2(3.3%)/PASS", msg)
        self.assertIn("book=real(", msg)
        self.assertIn("/PASS", msg)

    # ============================================================
    # Fixture 2：WARN = 1-2 條件偏移（age 120-300s OR extreme 5-20%）
    # ============================================================
    # 對應 producer 偶有 lag + BTC 中度波動期：
    #   age = 180s (120-300s WARN)
    #   cohort_size = 7 (= 7 PASS)
    #   total = 60 / extreme = 7 → ratio 11.7% (5-20% WARN)
    #   book_imb_avg = 0.018 (非 0 PASS)
    # 2 條件 WARN，整體 WARN

    def test_fixture_2_two_warn_conditions(self) -> None:
        """Fixture 2 WARN：age 120-300s + extreme 5-20%（producer lag + BTC 中度波動）。"""
        os.environ["OPENCLAW_W2_HEALTHCHECK_ENABLED"] = "1"
        # age=180s WARN / cohort=7 PASS / extreme_ratio=11.7% WARN / book real PASS
        cur = _mock_cursor([
            (True,),
            (Decimal("180.5"), 7, 60, 7, Decimal("0.018"), 60),
        ])

        status, msg = check_57_btc_lead_lag_panel_health(cur)

        self.assertEqual(status, "WARN", msg)
        self.assertIn("degraded", msg)
        self.assertIn("age=180.5s/WARN", msg)
        self.assertIn("cohort=7/7/PASS", msg)
        self.assertIn("extreme=7(11.7%)/WARN", msg)
        self.assertIn("/PASS", msg)  # book real-value PASS portion

    # ============================================================
    # Fixture 3：FAIL = age ≥ 300s OR cohort < 7 OR extreme ≥ 20%
    # ============================================================
    # 對應 producer dead + cohort 配置錯 + BTC 異常波動：
    #   age = 420s (≥ 300s FAIL)
    #   cohort_size = 5 (< 7 FAIL)
    #   total = 60 / extreme = 15 → ratio 25% (≥ 20% FAIL)
    #   book_imb_avg = NULL (orderbook subscription 斷 WARN/FAIL)
    # 3-4 條件 FAIL，整體 FAIL（silent-dead 觸發）

    def test_fixture_3_silent_dead_three_failures(self) -> None:
        """Fixture 3 FAIL：3+ 條件破 — producer dead + cohort 配錯 + BTC 異常 + book 斷。"""
        os.environ["OPENCLAW_W2_HEALTHCHECK_ENABLED"] = "1"
        # age=420s FAIL / cohort=5 FAIL / extreme_ratio=25% FAIL / book all_null WARN
        cur = _mock_cursor([
            (True,),
            (Decimal("420.0"), 5, 60, 15, None, 0),
        ])

        status, msg = check_57_btc_lead_lag_panel_health(cur)

        self.assertEqual(status, "FAIL", msg)
        self.assertIn("silent-dead", msg)
        self.assertIn("age=420.0s/FAIL", msg)
        self.assertIn("cohort=5/7/FAIL", msg)
        self.assertIn("extreme=15(25.0%)/FAIL", msg)
        self.assertIn("all_null", msg)

    # ============================================================
    # Edge case 4：book placeholder（W2-IMPL-1 未 land）— book_avg = 0
    # ============================================================
    # 對應 W2-IMPL-1 未 land + book_required=0：book WARN，其他全 PASS → WARN
    # OPENCLAW_W2_HEALTHCHECK_BOOK_REQUIRED=1 後升 FAIL

    def test_book_placeholder_warn_without_required_env(self) -> None:
        """book_avg=0 placeholder（IMPL-1 未 land）+ book_required=0 → WARN（默認）。"""
        os.environ["OPENCLAW_W2_HEALTHCHECK_ENABLED"] = "1"
        os.environ.pop("OPENCLAW_W2_HEALTHCHECK_BOOK_REQUIRED", None)
        # 全 PASS 除 book_avg=0.0 (placeholder)
        cur = _mock_cursor([
            (True,),
            (Decimal("45.0"), 7, 60, 1, Decimal("0.0"), 60),
        ])

        status, msg = check_57_btc_lead_lag_panel_health(cur)

        self.assertEqual(status, "WARN", msg)
        self.assertIn("placeholder_zero", msg)
        self.assertIn("/WARN", msg)

    def test_book_placeholder_fail_with_book_required(self) -> None:
        """book_avg=0 + OPENCLAW_W2_HEALTHCHECK_BOOK_REQUIRED=1 → FAIL（W2-IMPL-1 land 後嚴格）。"""
        os.environ["OPENCLAW_W2_HEALTHCHECK_ENABLED"] = "1"
        os.environ["OPENCLAW_W2_HEALTHCHECK_BOOK_REQUIRED"] = "1"
        cur = _mock_cursor([
            (True,),
            (Decimal("45.0"), 7, 60, 1, Decimal("0.0"), 60),
        ])

        status, msg = check_57_btc_lead_lag_panel_health(cur)

        self.assertEqual(status, "FAIL", msg)
        self.assertIn("silent-dead or evidence corrupt", msg)
        self.assertIn("placeholder_zero/FAIL", msg)

    # ============================================================
    # Edge case 5：REQUIRED env 把 WARN 升 FAIL
    # ============================================================

    def test_required_env_escalates_warn_to_fail(self) -> None:
        """OPENCLAW_W2_HEALTHCHECK_REQUIRED=1 把 WARN 升 FAIL（嚴格 silent-dead 模式）。"""
        os.environ["OPENCLAW_W2_HEALTHCHECK_ENABLED"] = "1"
        os.environ["OPENCLAW_W2_HEALTHCHECK_REQUIRED"] = "1"
        # age=180s WARN / cohort=7 PASS / extreme<5% PASS / book real PASS → 整體 WARN
        # 但 REQUIRED=1 升 FAIL
        cur = _mock_cursor([
            (True,),
            (Decimal("180.0"), 7, 60, 2, Decimal("0.018"), 60),
        ])

        status, msg = check_57_btc_lead_lag_panel_health(cur)

        self.assertEqual(status, "FAIL", msg)

    # ============================================================
    # Edge case 6：cursor execute SQL 純 SELECT（無 INSERT / UPDATE / DELETE）
    # ============================================================

    def test_sql_contract_is_read_only(self) -> None:
        """SQL 必為純 SELECT（passive sentinel 不可寫資料；CLAUDE.md §三）。"""
        os.environ["OPENCLAW_W2_HEALTHCHECK_ENABLED"] = "1"
        cur = _mock_cursor([
            (True,),
            (Decimal("45.0"), 7, 60, 1, Decimal("0.02"), 60),
        ])

        check_57_btc_lead_lag_panel_health(cur)

        sql_text = "\n".join(str(call.args[0]) for call in cur.execute.call_args_list)
        # 必含 panel.btc_lead_lag_panel + to_regclass 入口
        self.assertIn("to_regclass", sql_text)
        self.assertIn("panel.btc_lead_lag_panel", sql_text)
        # 必含 4 條件 evidence column
        self.assertIn("snapshot_ts_ms", sql_text)
        self.assertIn("alt_symbols", sql_text)
        self.assertIn("regime_tag", sql_text)
        self.assertIn("btc_book_imbalance", sql_text)
        # 禁含寫操作
        self.assertNotIn("INSERT ", sql_text.upper())
        self.assertNotIn("UPDATE ", sql_text.upper())
        self.assertNotIn("DELETE ", sql_text.upper())
        self.assertNotIn("TRUNCATE", sql_text.upper())
        self.assertNotIn("DROP ", sql_text.upper())


if __name__ == "__main__":
    unittest.main()
