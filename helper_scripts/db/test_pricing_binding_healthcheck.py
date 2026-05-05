#!/usr/bin/env python3
"""Unit tests for LG-3 pricing-binding healthcheck `[45]`.
LG-3 提供者定價綁定 healthcheck `[45]` 單元測試。

Mocks ``psycopg2``-style cursor with deterministic ``fetchone`` /
``fetchall`` return values per the LG-3 RFC v1
(``2026-05-01--lg3_provider_pricing_binding_rfc.md``) §2.2 ``Refresh
Cadence`` + §2.3 ``Fail-Closed Rules`` + §2.4 ``Healthcheck Shape``
contracts.

模擬 psycopg2 cursor，按 LG-3 RFC v1（``2026-05-01--lg3_*.md``）
§2.2 / §2.3 / §2.4 提供 deterministic fixture，驗證 PASS / WARN /
FAIL 各 path 各自正確。

Coverage scope (REF-20 Sprint C R6-T7, 2026-05-05):
- PASS: all three modes have fresh fee_rate fills (<1h)
- WARN: ≥1 mode aged in [1h, 24h)
- WARN: quiet mode on warm engine (no fills, engine_age >= 30min)
- FAIL: ≥1 mode aged ≥24h
- FAIL: live mode + source=seed_default (RFC §2.3 fail-closed)
- FAIL: trading.fills missing (V003 not applied)
- PASS: cold-engine quiet (engine_age < 30min, 0 fills) tolerated
"""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# srv root on sys.path (mirror test_lg5_healthchecks.py).
# 加 srv root 到 sys.path（鏡像 test_lg5_healthchecks.py）。
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_HELPER_SCRIPTS_DIR = os.path.dirname(_THIS_DIR)
_SRV_ROOT = os.path.dirname(_HELPER_SCRIPTS_DIR)
sys.path.insert(0, _SRV_ROOT)

from helper_scripts.db.passive_wait_healthcheck.checks_pricing_binding import (  # noqa: E402
    DEFAULT_MAKER_FEE,
    DEFAULT_TAKER_FEE,
    REFRESH_AGE_PASS_MAX_SECONDS,
    REFRESH_AGE_WARN_MAX_SECONDS,
    check_45_pricing_binding,
)


# ---------------------------------------------------------------------------
# Mock cursor builder.
# 模擬 cursor 建構器。
# ---------------------------------------------------------------------------

def _build_cur(
    table_exists: bool,
    rows: list[tuple] | None,
) -> MagicMock:
    """Build a MagicMock cursor with ``fetchone`` returning the existence row
    and ``fetchall`` returning per-mode aggregate rows.

    Per-mode row shape (matches the SQL SELECT clause in
    ``check_45_pricing_binding``):
        (engine_mode, fill_count, default_count, non_default_count,
         symbols, age_seconds)

    建立 MagicMock cursor：``fetchone`` 回 existence row，``fetchall``
    回 per-mode 聚合 row。Per-mode row 結構對齊 SQL SELECT。
    """
    cur = MagicMock()
    cur.connection = MagicMock()
    cur.connection.rollback = MagicMock()
    cur.fetchone.return_value = (table_exists,)
    cur.fetchall.return_value = rows if rows is not None else []
    return cur


# ---------------------------------------------------------------------------
# `[45]` pricing_binding test cases.
# `[45]` pricing_binding 測試用例。
# ---------------------------------------------------------------------------
class TestCheck45PricingBinding(unittest.TestCase):
    """Eight verdict paths exercised per LG-3 RFC contract.
    對應 LG-3 RFC 契約的 8 條 verdict path 測試。
    """

    def test_pass_when_all_modes_fresh(self) -> None:
        """All three modes have fills aged <1h with non-default fee_rate.
        三 mode 都有 <1h 內非 default 的 fill → PASS。
        """
        rows = [
            # (mode, fill_count, default_count, non_default_count, symbols, age_seconds)
            ("demo", 100, 5, 95, 12, 600),
            ("live", 80, 0, 80, 10, 1200),
            ("live_demo", 50, 0, 50, 8, 900),
        ]
        cur = _build_cur(True, rows)
        with patch(
            "helper_scripts.db.passive_wait_healthcheck.shared._engine_process_age_minutes",
            return_value=(120.0, "ok"),
        ):
            status, msg = check_45_pricing_binding(cur)
        self.assertEqual(status, "PASS", msg)
        self.assertIn("category=linear", msg)
        self.assertIn("source=bybit_v5", msg)
        self.assertIn("pricing binding healthy", msg)

    def test_warn_when_mode_aged_between_1h_and_24h(self) -> None:
        """One mode aged 7200s (2h) → WARN band per RFC §2.2.
        其中一 mode 老化 7200s → WARN band。
        """
        rows = [
            ("demo", 100, 5, 95, 12, 600),
            ("live_demo", 30, 0, 30, 6, 7200),  # 2h aged
            ("live", 80, 0, 80, 10, 800),
        ]
        cur = _build_cur(True, rows)
        with patch(
            "helper_scripts.db.passive_wait_healthcheck.shared._engine_process_age_minutes",
            return_value=(120.0, "ok"),
        ):
            status, msg = check_45_pricing_binding(cur)
        self.assertEqual(status, "WARN", msg)
        self.assertIn("exceeds 1h refresh cadence", msg)
        self.assertIn("live_demo", msg)

    def test_fail_when_mode_aged_24h_or_more(self) -> None:
        """One mode aged ≥86400s → FAIL per RFC §2.2 24h limit.
        其中一 mode 老化 ≥86400s → FAIL（RFC §2.2 24h 上限）。
        """
        rows = [
            ("demo", 100, 5, 95, 12, 600),
            ("live", 50, 0, 50, 8, 900),
            ("live_demo", 10, 0, 10, 4, 90000),  # >24h aged
        ]
        cur = _build_cur(True, rows)
        with patch(
            "helper_scripts.db.passive_wait_healthcheck.shared._engine_process_age_minutes",
            return_value=(120.0, "ok"),
        ):
            status, msg = check_45_pricing_binding(cur)
        self.assertEqual(status, "FAIL", msg)
        self.assertIn("exceeds 24h FAIL threshold", msg)

    def test_fail_when_live_uses_seed_default(self) -> None:
        """Live mode + 100% default fee_rate → FAIL per RFC §2.3.
        Live + 100% default fee_rate → FAIL（RFC §2.3 mainnet fail-closed）。
        """
        rows = [
            ("demo", 100, 5, 95, 12, 600),
            ("live", 50, 50, 0, 5, 900),  # 100% default → seed_default source
            ("live_demo", 30, 0, 30, 6, 1200),
        ]
        cur = _build_cur(True, rows)
        with patch(
            "helper_scripts.db.passive_wait_healthcheck.shared._engine_process_age_minutes",
            return_value=(120.0, "ok"),
        ):
            status, msg = check_45_pricing_binding(cur)
        self.assertEqual(status, "FAIL", msg)
        self.assertIn("live+source=seed_default", msg)
        self.assertIn("RFC §2.3", msg)
        self.assertIn("mainnet must not use", msg)

    def test_fail_when_table_missing(self) -> None:
        """trading.fills missing (V003 not applied) → FAIL fail-closed.
        trading.fills 缺（V003 未 apply）→ FAIL fail-closed。
        """
        cur = _build_cur(False, None)
        status, msg = check_45_pricing_binding(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("V003 not applied", msg)

    def test_pass_cold_engine_zero_fills_tolerated(self) -> None:
        """Engine warmup grace: 0 fills + engine_age <30min → PASS.
        熱機豁免：0 fills + engine_age <30min → PASS。
        """
        rows = []  # all modes quiet
        cur = _build_cur(True, rows)
        with patch(
            "helper_scripts.db.passive_wait_healthcheck.shared._engine_process_age_minutes",
            return_value=(15.0, "ok"),  # 15 min uptime
        ):
            status, msg = check_45_pricing_binding(cur)
        self.assertEqual(status, "PASS", msg)
        self.assertIn("category=linear", msg)

    def test_warn_warm_engine_quiet_modes(self) -> None:
        """Warm engine (60min) + 0 fills in any mode → WARN (real signal gap).
        熱機 60min 後仍三 mode 0 fills → WARN（真信號缺口）。
        """
        rows = []  # all quiet
        cur = _build_cur(True, rows)
        with patch(
            "helper_scripts.db.passive_wait_healthcheck.shared._engine_process_age_minutes",
            return_value=(60.0, "ok"),
        ):
            status, msg = check_45_pricing_binding(cur)
        self.assertEqual(status, "WARN", msg)
        self.assertIn("0 fills with fee_rate in 24h", msg)

    def test_pass_demo_seed_default_acceptable(self) -> None:
        """Demo + 100% default fee_rate → PASS per RFC §2.3 demo fallback.
        Demo + 100% default → PASS（RFC §2.3 demo 容許 conservative default）。
        """
        rows = [
            ("demo", 100, 100, 0, 12, 600),  # demo seed_default — accepted
            ("live_demo", 50, 0, 50, 8, 900),
            ("live", 30, 0, 30, 5, 1200),
        ]
        cur = _build_cur(True, rows)
        with patch(
            "helper_scripts.db.passive_wait_healthcheck.shared._engine_process_age_minutes",
            return_value=(120.0, "ok"),
        ):
            status, msg = check_45_pricing_binding(cur)
        self.assertEqual(status, "PASS", msg)
        self.assertIn("demo: source=seed_default", msg)


# ---------------------------------------------------------------------------
# Source-inference unit tests for the pure helpers.
# Source 推斷純函數測試。
# ---------------------------------------------------------------------------
class TestSourceInferenceHelpers(unittest.TestCase):
    def test_default_constants_match_rust_sibling(self) -> None:
        """Python sibling defaults must mirror Rust ``account_manager.rs:136-138``.
        Python sibling default 必鏡 Rust ``account_manager.rs:136-138``。
        """
        self.assertEqual(DEFAULT_MAKER_FEE, 0.0002)
        self.assertEqual(DEFAULT_TAKER_FEE, 0.00055)

    def test_threshold_constants_match_rfc(self) -> None:
        """Threshold constants must match RFC §2.2 cadence wording.
        閾值常量必對齊 RFC §2.2 措辭。
        """
        self.assertEqual(REFRESH_AGE_PASS_MAX_SECONDS, 3600)
        self.assertEqual(REFRESH_AGE_WARN_MAX_SECONDS, 86400)


if __name__ == "__main__":
    unittest.main()
