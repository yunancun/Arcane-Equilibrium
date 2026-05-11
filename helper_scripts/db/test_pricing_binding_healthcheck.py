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
    DUAL_SOURCE_ENV_VAR,
    REFRESH_AGE_PASS_MAX_SECONDS,
    REFRESH_AGE_WARN_MAX_SECONDS,
    RUST_FEE_SOURCE_BYBIT_API,
    RUST_FEE_SOURCE_COLD_DEFAULT,
    RUST_FEE_SOURCE_DEMO_CONSERVATIVE_DEFAULT,
    _is_rust_pg_source_compatible,
    check_45_pricing_binding,
)


# ---------------------------------------------------------------------------
# Mock cursor builder.
# 模擬 cursor 建構器。
# ---------------------------------------------------------------------------

def _build_cur(
    table_exists: bool,
    rows: list[tuple] | None,
    fee_proxy_rows: list[tuple] | None = None,
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
    cur.fetchall.side_effect = [
        rows if rows is not None else [],
        fee_proxy_rows if fee_proxy_rows is not None else [],
    ]
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

    def test_pass_when_demo_livedemo_stale_fill_age_has_recent_fee_proxy(self) -> None:
        """Demo/LiveDemo stale fill proof is explained by rejected-only flow.

        `account_manager_taker_fee` in recent intent details proves the Rust
        AccountManager fee table is in use, while approved_30m=0 explains why
        no fresh fill materialized fee proof is expected.
        """
        rows = [
            ("demo", 100, 5, 95, 12, 7200),
            ("live_demo", 50, 0, 50, 8, 7200),
        ]
        fee_proxy_rows = [
            ("demo", 20, 20, 0, 12, 0, 12),
            ("live_demo", 18, 18, 0, 10, 0, 10),
            ("live", 0, 0, 0, 0, 0, 0),
        ]
        cur = _build_cur(True, rows, fee_proxy_rows)
        with patch.dict(os.environ, {"OPENCLAW_ALLOW_MAINNET": ""}, clear=False), patch(
            "helper_scripts.db.passive_wait_healthcheck.shared._engine_process_age_minutes",
            return_value=(120.0, "ok"),
        ):
            status, msg = check_45_pricing_binding(cur)
        self.assertEqual(status, "PASS", msg)
        self.assertIn("fee_proxy_context", msg)
        self.assertIn("fill fee proof stale", msg)
        self.assertIn("approved_30m=0", msg)

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

    def test_pass_when_mainnet_live_slot_inactive_but_demo_modes_fresh(self) -> None:
        """No Mainnet fills are expected when OPENCLAW_ALLOW_MAINNET is disabled."""
        rows = [
            ("demo", 100, 5, 95, 12, 600),
            ("live_demo", 50, 0, 50, 8, 900),
            # live missing means 0 fills; with mainnet disabled this is designed.
        ]
        cur = _build_cur(True, rows)
        with patch.dict(os.environ, {"OPENCLAW_ALLOW_MAINNET": ""}, clear=False), patch(
            "helper_scripts.db.passive_wait_healthcheck.shared._engine_process_age_minutes",
            return_value=(120.0, "ok"),
        ):
            status, msg = check_45_pricing_binding(cur)
        self.assertEqual(status, "PASS", msg)
        self.assertIn("live: source=inactive_mainnet", msg)
        self.assertIn("pricing binding healthy", msg)

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


# ---------------------------------------------------------------------------
# LG-2 T3 (2026-05-11) IPC dual-source compare test cases。
# 對賬 Rust enum 真值與 PG proxy 推斷字串；disagree 升 WARN（首階段 2 週觀察期）。
# ---------------------------------------------------------------------------
class TestLg2T3DualSourceCompat(unittest.TestCase):
    """Rust FeeSource ↔ PG proxy 字串相容性表測試。"""

    def test_bybit_api_compatible_with_bybit_v5(self) -> None:
        self.assertTrue(
            _is_rust_pg_source_compatible(RUST_FEE_SOURCE_BYBIT_API, "bybit_v5")
        )

    def test_demo_conservative_default_compatible_with_seed_default(self) -> None:
        self.assertTrue(
            _is_rust_pg_source_compatible(
                RUST_FEE_SOURCE_DEMO_CONSERVATIVE_DEFAULT, "seed_default"
            )
        )

    def test_cold_default_compatible_with_cold_default(self) -> None:
        self.assertTrue(
            _is_rust_pg_source_compatible(RUST_FEE_SOURCE_COLD_DEFAULT, "cold_default")
        )

    def test_inactive_mainnet_compatible_with_all_enum(self) -> None:
        """inactive_mainnet 是 PG 對 live slot 在 OPENCLAW_ALLOW_MAINNET 未啟用
        時的標記；不視為 disagree。
        """
        self.assertTrue(
            _is_rust_pg_source_compatible(RUST_FEE_SOURCE_BYBIT_API, "inactive_mainnet")
        )
        self.assertTrue(
            _is_rust_pg_source_compatible(
                RUST_FEE_SOURCE_DEMO_CONSERVATIVE_DEFAULT, "inactive_mainnet"
            )
        )
        self.assertTrue(
            _is_rust_pg_source_compatible(
                RUST_FEE_SOURCE_COLD_DEFAULT, "inactive_mainnet"
            )
        )

    def test_disagree_cases(self) -> None:
        """跨類別不相容 → disagree。"""
        self.assertFalse(
            _is_rust_pg_source_compatible(RUST_FEE_SOURCE_BYBIT_API, "seed_default")
        )
        self.assertFalse(
            _is_rust_pg_source_compatible(
                RUST_FEE_SOURCE_DEMO_CONSERVATIVE_DEFAULT, "bybit_v5"
            )
        )
        self.assertFalse(
            _is_rust_pg_source_compatible(RUST_FEE_SOURCE_COLD_DEFAULT, "bybit_v5")
        )
        # 未知 rust_enum 視為 disagree（fail-closed compatibility check）
        self.assertFalse(
            _is_rust_pg_source_compatible("unknown_enum", "bybit_v5")
        )


class TestLg2T3DualSourceWarn(unittest.TestCase):
    """check_45 主流程在 dual-source disagree 時升 WARN 的端對端測試。"""

    def test_dual_source_disagree_promotes_pass_to_warn(self) -> None:
        """Rust 端 IPC 報 bybit_api，但 PG 端推斷 seed_default → 升 WARN。
        IPC 啟用旗標：OPENCLAW_LG2_T3_DUAL_SOURCE=1。

        Setup：demo+live_demo 全 100% default fees（PG 推斷 seed_default 但
        RFC §2.3 demo+live_demo 是 accepted source）；live 走 inactive_mainnet
        （OPENCLAW_ALLOW_MAINNET 未啟用），因此 PG verdict 為 PASS。Rust 端
        IPC mock 回 bybit_api → dual-source disagree → 升 WARN。
        """
        rows = [
            # demo / live_demo 全 100% default → PG 推斷 seed_default
            ("demo", 100, 100, 0, 12, 600),
            ("live_demo", 50, 50, 0, 8, 900),
            # live 無 fills；OPENCLAW_ALLOW_MAINNET 未啟用 → 走 inactive_mainnet PG path
        ]
        cur = _build_cur(True, rows)

        # 模擬 Rust 端 IPC 回真實 bybit_api（與 PG 推斷 seed_default 不相容）
        mock_ipc = MagicMock(
            return_value={
                "status": "ok",
                "symbol": "BTCUSDT",
                "fee_source": RUST_FEE_SOURCE_BYBIT_API,
                "last_refresh_ms": 1_700_000_000_000,
                "fee_rate_count": 25,
            }
        )
        with patch.dict(
            os.environ,
            {DUAL_SOURCE_ENV_VAR: "1", "OPENCLAW_ALLOW_MAINNET": ""},
            clear=False,
        ), patch(
            "helper_scripts.db.passive_wait_healthcheck.shared._engine_process_age_minutes",
            return_value=(120.0, "ok"),
        ), patch(
            # 注入到模組命名空間的 sync_ipc_call lazy import 路徑
            "program_code.exchange_connectors.bybit_connector.control_api_v1.app.ipc_client_sync.sync_ipc_call",
            mock_ipc,
        ):
            status, msg = check_45_pricing_binding(cur)
        # PG demo+live_demo seed_default 可接受 + live inactive_mainnet skip →
        # PG verdict=PASS；dual-source disagree (Rust bybit_api vs PG seed_default)
        # → 升 WARN（首階段 2 週觀察期不直接 FAIL）
        self.assertEqual(status, "WARN", msg)
        self.assertIn("dual_source", msg)
        self.assertIn("rust_enum=bybit_api", msg)
        self.assertIn("pg_proxy_canonical=seed_default", msg)
        self.assertIn("compatible=False", msg)
        self.assertIn("LG-2 T3 dual_source disagree", msg)

    def test_dual_source_compat_no_verdict_change(self) -> None:
        """Rust 端與 PG 推斷相容 → verdict 不變，但 summary 含 dual_source。"""
        rows = [
            ("demo", 100, 5, 95, 12, 600),
            ("live_demo", 50, 0, 50, 8, 900),
            ("live", 30, 0, 30, 5, 1200),
        ]
        cur = _build_cur(True, rows)
        mock_ipc = MagicMock(
            return_value={
                "status": "ok",
                "symbol": "BTCUSDT",
                "fee_source": RUST_FEE_SOURCE_BYBIT_API,
                "last_refresh_ms": 1_700_000_000_000,
                "fee_rate_count": 25,
            }
        )
        with patch.dict(
            os.environ, {DUAL_SOURCE_ENV_VAR: "1"}, clear=False
        ), patch(
            "helper_scripts.db.passive_wait_healthcheck.shared._engine_process_age_minutes",
            return_value=(120.0, "ok"),
        ), patch(
            "program_code.exchange_connectors.bybit_connector.control_api_v1.app.ipc_client_sync.sync_ipc_call",
            mock_ipc,
        ):
            status, msg = check_45_pricing_binding(cur)
        self.assertEqual(status, "PASS", msg)
        self.assertIn("dual_source", msg)
        self.assertIn("compatible=True", msg)

    def test_dual_source_ipc_unavailable_fail_soft(self) -> None:
        """IPC socket 不存在 → fail-soft（dual_source=ipc_unavailable，不改 verdict）。"""
        rows = [
            ("demo", 100, 5, 95, 12, 600),
            ("live_demo", 50, 0, 50, 8, 900),
            ("live", 30, 0, 30, 5, 1200),
        ]
        cur = _build_cur(True, rows)

        # 模擬 sync_ipc_call raise FileNotFoundError（engine socket 不存在）
        mock_ipc = MagicMock(side_effect=FileNotFoundError("no engine"))
        with patch.dict(
            os.environ, {DUAL_SOURCE_ENV_VAR: "1"}, clear=False
        ), patch(
            "helper_scripts.db.passive_wait_healthcheck.shared._engine_process_age_minutes",
            return_value=(120.0, "ok"),
        ), patch(
            "program_code.exchange_connectors.bybit_connector.control_api_v1.app.ipc_client_sync.sync_ipc_call",
            mock_ipc,
        ):
            status, msg = check_45_pricing_binding(cur)
        # PG 三 mode 都 PASS，IPC 不可用 fail-soft 不阻 healthcheck
        self.assertEqual(status, "PASS", msg)
        self.assertIn("dual_source=ipc_unavailable", msg)

    def test_dual_source_disabled_by_default(self) -> None:
        """OPENCLAW_LG2_T3_DUAL_SOURCE 未設 → dual_source compare 不執行；
        msg 應不含 dual_source 字串（保持向後相容）。"""
        rows = [
            ("demo", 100, 5, 95, 12, 600),
            ("live_demo", 50, 0, 50, 8, 900),
            ("live", 30, 0, 30, 5, 1200),
        ]
        cur = _build_cur(True, rows)
        with patch.dict(
            os.environ, {DUAL_SOURCE_ENV_VAR: ""}, clear=False
        ), patch(
            "helper_scripts.db.passive_wait_healthcheck.shared._engine_process_age_minutes",
            return_value=(120.0, "ok"),
        ):
            status, msg = check_45_pricing_binding(cur)
        self.assertEqual(status, "PASS", msg)
        self.assertNotIn("dual_source", msg)


if __name__ == "__main__":
    unittest.main()
