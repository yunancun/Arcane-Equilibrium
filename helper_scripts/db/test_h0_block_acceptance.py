#!/usr/bin/env python3
"""Unit tests for LG-1 H0 block acceptance healthcheck `[59]`.
LG-1 H0 hard-block 驗收 healthcheck `[59]` 單元測試。

Per PA tech plan `2026-05-11--lg_2_3_4_design_plan.md` §1.4 T2 acceptance:
- PASS: hard-block events > 0 AND fills_during_block = 0
- WARN: stats insufficient (n < threshold)
- WARN: shadow_mode=true
- WARN: snapshot stale/missing
- FAIL: H0 block dominant 但 entry fills > 0(block invariant 失效)

Mocks:
  - psycopg2-style cursor（``cur.connection.rollback`` / ``cur.execute`` /
    ``cur.fetchone``).
  - filesystem ``pipeline_snapshot_{engine}.json`` via tmp_path + monkeypatch
    of ``OPENCLAW_DATA_DIR`` env var.

Use ``importlib.util.spec_from_file_location`` 直接 load 模組,繞過
package ``__init__.py`` 的 runner.py import chain（與
test_agent_spine_healthcheck.py 一致 pattern,避免 W1 panel_aggregator
pre-existing breakage 干擾）。
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_HELPER_SCRIPTS_DIR = os.path.dirname(_THIS_DIR)
_SRV_ROOT = os.path.dirname(_HELPER_SCRIPTS_DIR)
sys.path.insert(0, _SRV_ROOT)


def _load_isolated_check() -> tuple[callable, object]:
    """直接 load checks_h0_block_acceptance,繞過 package __init__.py。

    與 test_agent_spine_healthcheck.py 相同 pattern (避免 W1 panel_aggregator
    pre-existing breakage:runner.py 預先 import check_panel_freshness
    但對應 check 函數可能尚未 land 即 ImportError)。
    """
    spec_path = os.path.join(
        _HELPER_SCRIPTS_DIR,
        "db",
        "passive_wait_healthcheck",
        "checks_h0_block_acceptance.py",
    )
    spec = importlib.util.spec_from_file_location(
        "checks_h0_block_acceptance_isolated",
        spec_path,
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.check_59_h0_block_acceptance, mod


check_59_h0_block_acceptance, _module = _load_isolated_check()


# ---------------------------------------------------------------------------
# Test fixture helpers / 測試夾具輔助
# ---------------------------------------------------------------------------

def _make_snapshot(
    *,
    shadow_mode: bool = False,
    total_checks: int = 1000,
    total_allowed: int = 800,
    blocked_freshness: int = 100,
    blocked_health: int = 50,
    blocked_eligibility: int = 30,
    blocked_envelope: int = 15,
    blocked_cooldown: int = 5,
    shadow_would_block: int = 0,
    include_h0_stats: bool = True,
    include_risk_config: bool = True,
) -> dict:
    """Build a pipeline_snapshot dict with controllable H0 fields.
    建構 pipeline_snapshot dict（可控 H0 各欄位）。
    """
    snap: dict = {"schema_version": "2.0.0", "source": "rust_engine"}
    if include_h0_stats:
        snap["h0_gate_stats"] = {
            "total_checks": total_checks,
            "total_allowed": total_allowed,
            "blocked_freshness": blocked_freshness,
            "blocked_health": blocked_health,
            "blocked_eligibility": blocked_eligibility,
            "blocked_envelope": blocked_envelope,
            "blocked_cooldown": blocked_cooldown,
            "shadow_would_block": shadow_would_block,
            "max_latency_us": 200,
            "total_latency_us": 50000,
        }
    if include_risk_config:
        snap["risk_manager_config"] = {
            "runtime": {
                "boot_cooldown_ms": 60000,
                "signals_heartbeat_ms": 60000,
                "h0_shadow_mode": shadow_mode,
            }
        }
    return snap


def _write_snapshots(
    data_dir: Path,
    snapshots: dict[str, dict | None],
) -> None:
    """寫多個 ``pipeline_snapshot_{engine}.json``。None 即不建檔(模擬缺檔)。"""
    for engine, snap in snapshots.items():
        if snap is None:
            continue
        path = data_dir / f"pipeline_snapshot_{engine}.json"
        path.write_text(json.dumps(snap), encoding="utf-8")


def _make_cur(
    *,
    fills_table_exists: bool = True,
    entry_fills_per_engine: dict[str, int] | None = None,
    fill_query_raises: bool = False,
) -> MagicMock:
    """Build a MagicMock cursor with deterministic responses.

    sequence:
        1. ``SELECT to_regclass('trading.fills') IS NOT NULL`` → fills_table_exists
        2. ``SELECT COUNT(*) FROM trading.fills WHERE engine_mode=%s ...``
            x N(monitored_engines) → entry_fills_per_engine[engine]

    Args:
        fills_table_exists: 第一個 fetchone 回傳值。
        entry_fills_per_engine: per-engine entry_fills 計數;預設 {"demo":0,
            "live_demo":0}。
        fill_query_raises: 若 True,fill query 直接 raise(走 except path)。
    """
    if entry_fills_per_engine is None:
        entry_fills_per_engine = {"demo": 0, "live_demo": 0}

    cur = MagicMock()
    cur.connection = MagicMock()
    cur.connection.rollback = MagicMock()

    # 第一個 cur.fetchone 回 (fills_table_exists,)
    # 後續 cur.fetchone (entry fills query) 回對應 engine 數
    fetchone_seq: list = [(fills_table_exists,)]
    engines_default = ("demo", "live_demo")
    for engine in engines_default:
        count = entry_fills_per_engine.get(engine, 0)
        fetchone_seq.append((count,))
    cur.fetchone.side_effect = fetchone_seq

    if fill_query_raises:
        # 第一個 execute(table-exists check) 走正常,後續 entry-fills execute raise。
        execute_calls = {"count": 0}

        def _exec_side_effect(*_args, **_kwargs):
            execute_calls["count"] += 1
            # 第 1 call 是 table-exists check,後面才是 fills query
            if execute_calls["count"] > 1:
                raise RuntimeError("simulated PG fill query failure")
            return None

        cur.execute.side_effect = _exec_side_effect

    return cur


# ---------------------------------------------------------------------------
# Test cases / 測試用例
# ---------------------------------------------------------------------------

class TestCheck59H0BlockAcceptance(unittest.TestCase):
    """LG-1 T2 acceptance contract 5+ test paths."""

    def setUp(self) -> None:
        self._old_env = dict(os.environ)
        # 給每個 test 一個獨立 tmp data dir 以隔離 snapshot 寫入。
        # Each test gets its own tmp data dir.
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self._data_dir = Path(self._tmp.name)
        os.environ["OPENCLAW_DATA_DIR"] = str(self._data_dir)
        # 預設清空可能干擾的 env
        # Clear potentially interfering env vars.
        for var in (
            "OPENCLAW_H0_BLOCK_HEALTH_REQUIRED",
            "OPENCLAW_H0_BLOCK_HEALTH_MIN_CHECKS",
            "OPENCLAW_H0_BLOCK_HEALTH_ENGINES",
        ):
            os.environ.pop(var, None)

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._old_env)
        self._tmp.cleanup()

    def test_pass_when_hard_block_active_and_no_fill_leakage(self) -> None:
        """PASS path: 兩 engine snapshot fresh + shadow=false + 充足樣本 +
        無 entry fill leakage。"""
        snap_demo = _make_snapshot(
            shadow_mode=False,
            total_checks=1000,
            blocked_freshness=100,
            blocked_health=50,
            blocked_eligibility=30,
            blocked_envelope=15,
            blocked_cooldown=5,
        )
        snap_livedemo = _make_snapshot(
            shadow_mode=False,
            total_checks=500,
            blocked_freshness=50,
            blocked_health=20,
            blocked_eligibility=10,
            blocked_envelope=5,
            blocked_cooldown=0,
        )
        _write_snapshots(
            self._data_dir,
            {"demo": snap_demo, "live_demo": snap_livedemo},
        )
        # block_ratio: demo = (100+50+30+15+5)/1000 = 0.20 (not dominant)
        # block_ratio: live_demo = (50+20+10+5+0)/500 = 0.17 (not dominant)
        # block_ratio 都 < 0.5 + entry fills = 0 → no leakage 條件
        cur = _make_cur(entry_fills_per_engine={"demo": 0, "live_demo": 0})

        status, msg = check_59_h0_block_acceptance(cur)
        self.assertEqual(status, "PASS", msg)
        self.assertIn("H0 hard-block acceptance healthy", msg)
        self.assertIn("demo", msg)
        self.assertIn("live_demo", msg)
        self.assertIn("verdict=PASS", msg)

    def test_warn_when_total_checks_insufficient(self) -> None:
        """WARN_LOW_SAMPLE: total_checks < min_checks (預設 100)。"""
        snap_demo = _make_snapshot(
            shadow_mode=False,
            total_checks=10,  # < 100 default min
            blocked_freshness=2,
            blocked_health=0,
            blocked_eligibility=0,
            blocked_envelope=0,
            blocked_cooldown=0,
        )
        snap_livedemo = _make_snapshot(
            shadow_mode=False,
            total_checks=500,
            blocked_freshness=50,
            blocked_health=20,
            blocked_eligibility=10,
            blocked_envelope=5,
            blocked_cooldown=0,
        )
        _write_snapshots(
            self._data_dir,
            {"demo": snap_demo, "live_demo": snap_livedemo},
        )
        cur = _make_cur(entry_fills_per_engine={"demo": 0, "live_demo": 0})

        status, msg = check_59_h0_block_acceptance(cur)
        self.assertEqual(status, "WARN", msg)
        self.assertIn("WARN_LOW_SAMPLE", msg)
        self.assertIn("demo", msg)

    def test_warn_when_shadow_mode_true(self) -> None:
        """WARN_SHADOW_MODE: shadow_mode=true(demo/live_demo by-design hard-block)。"""
        snap_demo = _make_snapshot(
            shadow_mode=True,  # ← shadow=true 不應出現 in demo/live_demo
            total_checks=1000,
            blocked_freshness=100,
            blocked_health=50,
            blocked_eligibility=30,
            blocked_envelope=15,
            blocked_cooldown=5,
        )
        snap_livedemo = _make_snapshot(
            shadow_mode=False,
            total_checks=500,
            blocked_freshness=50,
            blocked_health=20,
            blocked_eligibility=10,
            blocked_envelope=5,
            blocked_cooldown=0,
        )
        _write_snapshots(
            self._data_dir,
            {"demo": snap_demo, "live_demo": snap_livedemo},
        )
        cur = _make_cur(entry_fills_per_engine={"demo": 0, "live_demo": 0})

        status, msg = check_59_h0_block_acceptance(cur)
        self.assertEqual(status, "WARN", msg)
        self.assertIn("WARN_SHADOW_MODE", msg)
        self.assertIn("demo: shadow_mode=true", msg)

    def test_fail_when_block_dominant_but_entry_fills_present(self) -> None:
        """FAIL_BLOCK_LEAKAGE: block dominant(>50%)但 entry fills > 0。"""
        # demo: 800/1000 blocked = 80% dominant
        snap_demo = _make_snapshot(
            shadow_mode=False,
            total_checks=1000,
            total_allowed=200,
            blocked_freshness=400,
            blocked_health=200,
            blocked_eligibility=100,
            blocked_envelope=80,
            blocked_cooldown=20,
        )
        snap_livedemo = _make_snapshot(
            shadow_mode=False,
            total_checks=500,
            total_allowed=400,
            blocked_freshness=50,
            blocked_health=20,
            blocked_eligibility=10,
            blocked_envelope=5,
            blocked_cooldown=0,
        )
        _write_snapshots(
            self._data_dir,
            {"demo": snap_demo, "live_demo": snap_livedemo},
        )
        # demo block_ratio=0.8 + entry_fills=5 → block invariant 失效
        cur = _make_cur(entry_fills_per_engine={"demo": 5, "live_demo": 0})

        status, msg = check_59_h0_block_acceptance(cur)
        self.assertEqual(status, "FAIL", msg)
        self.assertIn("FAIL_BLOCK_LEAKAGE", msg)
        self.assertIn("block invariant violated", msg)

    def test_warn_when_snapshot_missing(self) -> None:
        """WARN_NO_SNAPSHOT: snapshot 檔不存在(Mac dev / engine cold start)。"""
        # 不寫任何 snapshot 檔 → 兩 engine 都 missing
        cur = _make_cur(entry_fills_per_engine={"demo": 0, "live_demo": 0})

        status, msg = check_59_h0_block_acceptance(cur)
        self.assertEqual(status, "WARN", msg)
        self.assertIn("WARN_NO_SNAPSHOT", msg)
        # 因 snapshot 缺,fill query 路徑 short-circuit (continue),不會碰
        # cur.execute(fills_count_query),所以 fetchone 不耗第 2/3 個 stub。
        # 但 table-exists check 仍跑,所以 first fetchone (True,) 被消耗。

    def test_fail_when_required_env_set_and_warn_present(self) -> None:
        """REQUIRED env=1: WARN 升 FAIL(low-sample case)。"""
        os.environ["OPENCLAW_H0_BLOCK_HEALTH_REQUIRED"] = "1"
        snap_demo = _make_snapshot(
            shadow_mode=False,
            total_checks=10,  # < 100 → WARN_LOW_SAMPLE
            blocked_freshness=2,
        )
        snap_livedemo = _make_snapshot(
            shadow_mode=False,
            total_checks=500,
            blocked_freshness=50,
            blocked_health=20,
            blocked_eligibility=10,
            blocked_envelope=5,
            blocked_cooldown=0,
        )
        _write_snapshots(
            self._data_dir,
            {"demo": snap_demo, "live_demo": snap_livedemo},
        )
        cur = _make_cur(entry_fills_per_engine={"demo": 0, "live_demo": 0})

        status, msg = check_59_h0_block_acceptance(cur)
        self.assertEqual(status, "FAIL", msg)
        self.assertIn("WARN_LOW_SAMPLE", msg)

    def test_fail_when_trading_fills_table_missing(self) -> None:
        """FAIL fail-closed: trading.fills 不存在(V003 未 apply)。"""
        cur = _make_cur(fills_table_exists=False)

        status, msg = check_59_h0_block_acceptance(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("V003 not applied", msg)

    def test_pass_with_custom_engine_list(self) -> None:
        """OPENCLAW_H0_BLOCK_HEALTH_ENGINES 自訂只測 demo。"""
        os.environ["OPENCLAW_H0_BLOCK_HEALTH_ENGINES"] = "demo"
        snap_demo = _make_snapshot(
            shadow_mode=False,
            total_checks=1000,
            blocked_freshness=100,
            blocked_health=50,
            blocked_eligibility=30,
            blocked_envelope=15,
            blocked_cooldown=5,
        )
        _write_snapshots(self._data_dir, {"demo": snap_demo})
        # 因 engines=demo 只跑一個,只需 fill query 一次
        # cur fetchone seq: (True,) [table exists], (0,) [demo fills]
        cur = MagicMock()
        cur.connection = MagicMock()
        cur.connection.rollback = MagicMock()
        cur.fetchone.side_effect = [(True,), (0,)]

        status, msg = check_59_h0_block_acceptance(cur)
        self.assertEqual(status, "PASS", msg)
        self.assertIn("engines=demo", msg)
        # live_demo 不應出現在 msg
        self.assertNotIn("live_demo:", msg)

    def test_warn_when_fill_query_raises(self) -> None:
        """WARN_QUERY_ERROR: PG fill query raise → fail-soft 不 FAIL。"""
        snap_demo = _make_snapshot(
            shadow_mode=False,
            total_checks=1000,
            blocked_freshness=100,
            blocked_health=50,
            blocked_eligibility=30,
            blocked_envelope=15,
            blocked_cooldown=5,
        )
        snap_livedemo = _make_snapshot(
            shadow_mode=False,
            total_checks=500,
            blocked_freshness=50,
            blocked_health=20,
            blocked_eligibility=10,
            blocked_envelope=5,
            blocked_cooldown=0,
        )
        _write_snapshots(
            self._data_dir,
            {"demo": snap_demo, "live_demo": snap_livedemo},
        )
        cur = _make_cur(
            entry_fills_per_engine={"demo": 0, "live_demo": 0},
            fill_query_raises=True,
        )

        status, msg = check_59_h0_block_acceptance(cur)
        self.assertEqual(status, "WARN", msg)
        self.assertIn("WARN_QUERY_ERROR", msg)

    def test_warn_when_pipeline_quiet(self) -> None:
        """WARN_PIPELINE_QUIET: snapshot fresh + 充足 checks + 0 blocks +
        0 entry_fills → pipeline 完全靜默(snapshot 寫但 stats 沒動)。"""
        snap_demo = _make_snapshot(
            shadow_mode=False,
            total_checks=500,
            total_allowed=500,
            blocked_freshness=0,
            blocked_health=0,
            blocked_eligibility=0,
            blocked_envelope=0,
            blocked_cooldown=0,
        )
        snap_livedemo = _make_snapshot(
            shadow_mode=False,
            total_checks=500,
            total_allowed=500,
            blocked_freshness=0,
            blocked_health=0,
            blocked_eligibility=0,
            blocked_envelope=0,
            blocked_cooldown=0,
        )
        _write_snapshots(
            self._data_dir,
            {"demo": snap_demo, "live_demo": snap_livedemo},
        )
        cur = _make_cur(entry_fills_per_engine={"demo": 0, "live_demo": 0})

        status, msg = check_59_h0_block_acceptance(cur)
        self.assertEqual(status, "WARN", msg)
        self.assertIn("WARN_PIPELINE_QUIET", msg)


class TestModuleHelpers(unittest.TestCase):
    """純函數 helper 的單元測試。"""

    def test_total_blocked_sums_correctly(self) -> None:
        """_total_blocked 須合計 5 個 blocked_* 欄位(對齊 Rust GateStats)。"""
        stats = {
            "blocked_freshness": 10,
            "blocked_health": 5,
            "blocked_eligibility": 3,
            "blocked_envelope": 2,
            "blocked_cooldown": 1,
        }
        self.assertEqual(_module._total_blocked(stats), 21)

    def test_total_blocked_missing_keys_defaults_zero(self) -> None:
        """缺欄位以 0 fill。"""
        stats = {"blocked_freshness": 7}
        self.assertEqual(_module._total_blocked(stats), 7)

    def test_extract_h0_stats_returns_zeros_when_absent(self) -> None:
        """h0_gate_stats 缺即回全 0 dict。"""
        stats, diag = _module._extract_h0_stats({})
        self.assertEqual(stats["total_checks"], 0)
        self.assertEqual(stats["blocked_freshness"], 0)
        self.assertIn("absent", diag)

    def test_extract_shadow_mode_handles_missing_paths(self) -> None:
        """各種 missing path 都 fail-soft 回 None。"""
        # 完全缺
        val, diag = _module._extract_shadow_mode({})
        self.assertIsNone(val)
        self.assertIn("risk_manager_config absent", diag)

        # runtime 缺
        val, diag = _module._extract_shadow_mode({"risk_manager_config": {}})
        self.assertIsNone(val)
        self.assertIn("runtime absent", diag)

        # h0_shadow_mode 非 bool
        val, diag = _module._extract_shadow_mode(
            {"risk_manager_config": {"runtime": {"h0_shadow_mode": "yes"}}}
        )
        self.assertIsNone(val)
        self.assertIn("non-bool", diag)

        # 正常 bool
        val, diag = _module._extract_shadow_mode(
            {"risk_manager_config": {"runtime": {"h0_shadow_mode": False}}}
        )
        self.assertEqual(val, False)
        self.assertEqual(diag, "ok")


if __name__ == "__main__":
    unittest.main()
