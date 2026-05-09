"""
G3-04 — ExecutorAgent shadow → live e2e integration tests.
G3-04 — ExecutorAgent shadow → live 端到端整合測試。

MODULE_NOTE (EN):
  Exercises the FULL Phase A + Phase B chain end-to-end (no real Rust engine):

    Rust IPC `get_risk_config` (mocked)
      → ExecutorConfigCache._fetch_via_ipc_blocking (mocked)
      → cache snapshot atomic swap
      → cache.shadow_mode_provider() lambda
      → ExecutorAgent.__init__(shadow_mode_provider=...)
      → execute_order() → _execute_via_ipc()
        → if provider() returns True: log shadow report, no SubmitOrder
        → if provider() returns False: paper_trading_routes._ipc_command("submit_paper_order", ...) (mocked)

  The "IPC flip" is simulated by varying the mocked
  `_fetch_via_ipc_blocking` return value across `_poll_once()` calls. We do
  NOT spawn the daemon thread; instead we drive `cache._poll_once()`
  synchronously to keep tests deterministic and fast. The shadow_mode_provider
  lambda used by ExecutorAgent reads the latest snapshot live, so a
  mid-test poll change is observed by the very next execute_order().

  Mock boundary chosen per RFC §8 ("verify the call shape"):
    - Cache poll boundary: `cache._fetch_via_ipc_blocking` returns
      ``ExecutorRuntimeConfig`` (post-parse). Equivalent to a successful
      Rust JSON-RPC ``get_risk_config`` reply with the executor sub-slice.
    - SubmitOrder boundary: `paper_trading_routes._ipc_command` returns the
      Rust JSON-RPC ``submit_paper_order`` shape ({"order_id": ..., "price": ..., "qty": ...}).
      This is exactly where Path A (Agent pipeline) hands the intent to the
      Rust intent_processor — see ``executor_agent.py:570-595``.

  We deliberately do NOT cover:
    - The real socket round-trip (covered by ``test_ipc_integration.py``).
    - The Rust gate chain itself (covered by Rust unit + IPC tests in
      ``rust/openclaw_engine/src/ipc_server/tests/config.rs`` + paper_state).
    - Per-engine isolation in the Rust ``PerEngineRiskStores`` layer (already
      covered by the 4 Rust IPC e2e tests landed in G3-02 Phase A).
    - GovernanceHub Decision Lease (G3-04 keeps governance_hub=None to
      isolate the shadow→live path; lease integration is exercised by
      ``test_batch11_executor_exchange.py`` already).

MODULE_NOTE (中):
  G3-02 Phase A + G3-03 Phase B 完整鏈端到端整合（無真實 Rust 引擎）：

    Rust IPC get_risk_config（mocked）
      → ExecutorConfigCache._fetch_via_ipc_blocking（mocked）
      → snapshot 原子交換
      → shadow_mode_provider lambda
      → ExecutorAgent ctor 注入
      → execute_order() → _execute_via_ipc()
        → provider() True：log shadow report，**不**送 SubmitOrder
        → provider() False：呼叫 paper_trading_routes._ipc_command("submit_paper_order", ...)
          （mocked）

  「IPC flip」由變動 mocked `_fetch_via_ipc_blocking` 回傳值模擬；我們**不**啟
  daemon thread，改為同步呼叫 `cache._poll_once()` 維持決定性。
  shadow_mode_provider lambda 即時讀最新 snapshot，下一次 execute_order()
  立刻反映變化。

Coverage (5 test classes, 8 cases):
  TestDefaultStateShadow:
    - test_default_state_shadow_mode_true_no_submit_order
  TestIpcFlipShadowToLive:
    - test_ipc_flip_propagates_to_executor
    - test_submit_order_payload_shape_correct
  TestIpcFlipBackToShadow:
    - test_live_then_back_to_shadow_no_more_submits
  TestIpcUnavailableFailClosed:
    - test_post_init_ipc_failure_retains_live_snapshot   (graceful degrade)
    - test_pre_init_ipc_failure_stays_fail_closed         (safety default)
  TestPerEngineIsolation:
    - test_demo_flip_does_not_leak_to_paper
    - test_paper_engine_default_unaffected_by_demo_cache
"""

from __future__ import annotations

import asyncio
import os
import sys
import unittest
from typing import Any, Dict, List
from unittest.mock import patch

_test_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(_test_dir)
if _control_api_dir not in sys.path:
    sys.path.insert(0, _control_api_dir)

from app import executor_config_cache as ecc_mod
from app.executor_agent import ExecutorAgent, ExecutorConfig
from app.executor_config_cache import (
    CanaryStage,
    ExecutorConfigCache,
    ExecutorRuntimeConfig,
)


# ── Helpers / 輔助 ───────────────────────────────────────────────────────────

def _make_runtime_config(
    *,
    shadow: bool,
    max_pos: float = 0.10,
    per_symbol: Dict[str, float] | None = None,
    version: int = 1,
    canary_stage: CanaryStage | None = None,
) -> ExecutorRuntimeConfig:
    """Build a post-parse ExecutorRuntimeConfig (the cache's internal type)。

    W-AUDIT-9 T3：``shadow=False`` 必伴隨 ``canary_stage >= 1``，否則
    shadow_mode_provider 投影為 True（per stage projection 不變式）。helper
    依 ``shadow`` 自動推導合理的 stage（caller 顯式 override 優先）。
    """
    if canary_stage is None:
        canary_stage = CanaryStage.SHADOW if shadow else CanaryStage.PAPER_SINGLE_COHORT
    return ExecutorRuntimeConfig(
        shadow_mode=shadow,
        canary_stage=canary_stage,
        max_position_pct=max_pos,
        per_symbol_position_cap=per_symbol or {},
        config_version=version,
        fetched_at_ms=1,
    )


class _IpcCallRecorder:
    """Synchronous-callable async stub recording each ``_ipc_command`` call.

    Mirrors the ``Awaitable`` contract of ``paper_trading_routes._ipc_command``:
    ``(method: str, params: dict) -> Awaitable[dict]``.

    記錄每次 _ipc_command 呼叫的 async stub。
    """

    def __init__(self, *, success: bool = True, fill_price: float = 60100.0) -> None:
        self.calls: List[Dict[str, Any]] = []
        self._success = success
        self._fill_price = fill_price

    async def __call__(self, method: str, params: dict | None = None) -> dict:
        self.calls.append({"method": method, "params": dict(params or {})})
        if not self._success:
            return {"error": "rust_engine_rejected"}
        # Mirror the Rust submit_order JSON-RPC reply shape.
        # 對應 Rust submit_order JSON-RPC 回應形狀。
        return {
            "order_id": "ord_test_e2e",
            "price": self._fill_price,
            "qty": float((params or {}).get("qty", 0.0)),
            "status": "Filled",
        }


def _build_agent_with_cache(cache: ExecutorConfigCache) -> ExecutorAgent:
    """Construct an ExecutorAgent wired through the given cache.
    用給定 cache 構建 ExecutorAgent；模擬 strategy_wiring.py:487-494 的接線。"""
    agent = ExecutorAgent(
        config=ExecutorConfig(),
        message_bus=None,
        paper_engine=None,                 # forces _execute_via_ipc path
        governance_hub=None,               # isolate from Decision Lease
        audit_callback=None,
        shadow_mode_provider=cache.shadow_mode_provider(),
    )
    agent.start()
    agent.update_market_prices({"BTCUSDT": 60000.0})
    return agent


# ── Test Cases / 測試 ───────────────────────────────────────────────────────


class TestDefaultStateShadow(unittest.TestCase):
    """1. Pre-fetch state: cache fail-closed → ExecutorAgent stays shadow.
    1. Pre-fetch 狀態：cache fail-closed → ExecutorAgent 保持 shadow。"""

    def setUp(self) -> None:
        ecc_mod._reset_for_tests()

    def tearDown(self) -> None:
        ecc_mod._reset_for_tests()

    def test_default_state_shadow_mode_true_no_submit_order(self) -> None:
        """Cache fresh + uninitialized → provider() True → shadow path; no IPC.
        Cache 全新未初始化 → provider() True → 走 shadow；不送 IPC。"""
        cache = ExecutorConfigCache()
        # Sanity: brand-new cache must fail-closed to True.
        self.assertTrue(cache.get().shadow_mode)
        self.assertFalse(cache.is_initialized())

        agent = _build_agent_with_cache(cache)
        ipc_recorder = _IpcCallRecorder()
        with patch(
            "app.paper_trading_routes._ipc_command",
            new=ipc_recorder,
        ):
            report = agent.execute_order(
                intent_id="i_default_001",
                symbol="BTCUSDT",
                side="Buy",
                qty=0.01,
            )

        # Shadow path → success=True (intent captured) but IPC NEVER called.
        # Shadow 路徑 → success=True（已捕獲 intent）但 IPC 從未被呼叫。
        self.assertTrue(report.success)
        self.assertEqual(report.error, "shadow_mode")
        self.assertEqual(report.metadata.get("execution_path"), "ipc_shadow")
        self.assertEqual(
            ipc_recorder.calls, [],
            "shadow mode must NOT emit submit_order IPC / shadow 不可送 submit_order",
        )


class TestIpcFlipShadowToLive(unittest.TestCase):
    """2. IPC patch flips shadow=False → next execute emits SubmitOrder.
    2. IPC patch 翻 shadow=False → 下次 execute 發 SubmitOrder。"""

    def setUp(self) -> None:
        ecc_mod._reset_for_tests()

    def tearDown(self) -> None:
        ecc_mod._reset_for_tests()

    def _drive_cache(
        self,
        cache: ExecutorConfigCache,
        snapshot: ExecutorRuntimeConfig,
    ) -> None:
        """Synchronously drive one IPC poll with the given snapshot.
        Mocks the IPC fetch boundary to the post-parse type.
        同步驅動單次 poll；mock IPC 拉取邊界。"""
        with patch.object(cache, "_fetch_via_ipc_blocking", return_value=snapshot):
            cache._poll_once()

    def test_ipc_flip_propagates_to_executor(self) -> None:
        """1) shadow init → 2) IPC flip false → 3) execute emits real IPC.
        1) shadow 初始 → 2) IPC 翻 false → 3) execute 發真實 IPC。"""
        cache = ExecutorConfigCache()
        # Step 1: simulate first successful poll with shadow=True (engine boot).
        # Step 1：第一次成功 poll，shadow=True（engine 啟動預設）。
        self._drive_cache(cache, _make_runtime_config(shadow=True, version=1))
        self.assertTrue(cache.is_initialized())
        self.assertTrue(cache.get().shadow_mode)

        agent = _build_agent_with_cache(cache)
        ipc_recorder = _IpcCallRecorder(success=True, fill_price=60100.0)

        with patch("app.paper_trading_routes._ipc_command", new=ipc_recorder):
            # Confirm shadow first (no IPC).
            r1 = agent.execute_order(
                intent_id="i_flip_pre_001",
                symbol="BTCUSDT", side="Buy", qty=0.01,
            )
            self.assertEqual(r1.error, "shadow_mode")
            self.assertEqual(len(ipc_recorder.calls), 0)

            # Step 2: simulate `patch_risk_config {executor: {shadow_mode: false}}`
            # being processed by Rust → next cache poll picks up shadow=False.
            # Step 2：模擬 patch_risk_config 處理後，下次 poll 拉到 shadow=False。
            self._drive_cache(
                cache,
                _make_runtime_config(shadow=False, max_pos=0.20, version=2),
            )
            self.assertFalse(cache.get().shadow_mode)

            # Step 3: next intent → real SubmitOrder IPC emitted.
            # Step 3：下一個 intent → 發出真實 SubmitOrder IPC。
            r2 = agent.execute_order(
                intent_id="i_flip_post_001",
                symbol="BTCUSDT", side="Buy", qty=0.02,
            )

        self.assertTrue(r2.success)
        self.assertEqual(r2.metadata.get("execution_path"), "ipc_real")
        self.assertEqual(
            len(ipc_recorder.calls), 1,
            "live mode must emit exactly one submit_order IPC / live 須恰好 1 次",
        )

    def test_submit_order_payload_shape_correct(self) -> None:
        """Live IPC call must use method=submit_order with full intent fields.
        Live IPC 呼叫須為 submit_order，且 payload 含完整 intent 欄位。"""
        cache = ExecutorConfigCache()
        self._drive_cache(cache, _make_runtime_config(shadow=False, version=5))
        agent = _build_agent_with_cache(cache)
        ipc_recorder = _IpcCallRecorder(success=True)

        with patch("app.paper_trading_routes._ipc_command", new=ipc_recorder):
            agent.execute_order(
                intent_id="i_payload_check_001",
                symbol="BTCUSDT", side="Sell", qty=0.05,
            )

        self.assertEqual(len(ipc_recorder.calls), 1)
        call = ipc_recorder.calls[0]
        self.assertEqual(call["method"], "submit_paper_order")
        params = call["params"]
        self.assertEqual(params["engine"], "paper")
        self.assertEqual(params["symbol"], "BTCUSDT")
        self.assertEqual(params["side"], "Sell")
        self.assertAlmostEqual(params["qty"], 0.05)
        self.assertEqual(params["order_type"], "market")
        # Strategy tag identifies Path A (Agent pipeline) origin per
        # executor_agent.py:578 — Rust intent_processor uses this for routing.
        # strategy 標識 Path A 來源（executor_agent.py:578）。
        self.assertTrue(
            params["strategy"].startswith("agent_executor:"),
            f"strategy tag must start with agent_executor: / strategy 須以 agent_executor: 開頭, got {params['strategy']!r}",
        )


class TestIpcFlipBackToShadow(unittest.TestCase):
    """3. live → shadow flip-back: next intent reverts to shadow.
    3. live → shadow 翻回：下一 intent 退回 shadow。"""

    def setUp(self) -> None:
        ecc_mod._reset_for_tests()

    def tearDown(self) -> None:
        ecc_mod._reset_for_tests()

    def test_live_then_back_to_shadow_no_more_submits(self) -> None:
        """Operator panic-flips back to shadow → no further IPC submits.
        Operator 緊急翻回 shadow → 不再送 IPC。"""
        cache = ExecutorConfigCache()
        # Start live.  / 起始 live。
        with patch.object(
            cache, "_fetch_via_ipc_blocking",
            return_value=_make_runtime_config(shadow=False, version=1),
        ):
            cache._poll_once()
        self.assertFalse(cache.get().shadow_mode)

        agent = _build_agent_with_cache(cache)
        ipc_recorder = _IpcCallRecorder(success=True)

        with patch("app.paper_trading_routes._ipc_command", new=ipc_recorder):
            # Live intent → emits IPC.
            agent.execute_order(
                intent_id="i_back_pre_001",
                symbol="BTCUSDT", side="Buy", qty=0.01,
            )
            self.assertEqual(len(ipc_recorder.calls), 1)

            # Flip back to shadow.  / 翻回 shadow。
            with patch.object(
                cache, "_fetch_via_ipc_blocking",
                return_value=_make_runtime_config(shadow=True, version=2),
            ):
                cache._poll_once()
            self.assertTrue(cache.get().shadow_mode)

            # Subsequent intents must NOT emit further IPC.
            # 後續 intent 不再送 IPC。
            for i in range(3):
                r = agent.execute_order(
                    intent_id=f"i_back_post_{i:03d}",
                    symbol="BTCUSDT", side="Buy", qty=0.01,
                )
                self.assertEqual(r.error, "shadow_mode")

        self.assertEqual(
            len(ipc_recorder.calls), 1,
            "after flip-back to shadow, no additional IPC should fire / 翻回 shadow 後不再有 IPC",
        )


class TestIpcUnavailableFailClosed(unittest.TestCase):
    """4. IPC unavailability paths preserve safety per RFC §5.2.
    4. IPC 不可用路徑：依 RFC §5.2 保持安全。"""

    def setUp(self) -> None:
        ecc_mod._reset_for_tests()

    def tearDown(self) -> None:
        ecc_mod._reset_for_tests()

    def test_post_init_ipc_failure_retains_live_snapshot(self) -> None:
        """Post-init transient IPC failure → previous good snapshot retained
        (graceful degrade). Live remains live until operator intervenes.
        初始化後瞬時失敗 → 保留前一好 snapshot；live 維持 live。"""
        cache = ExecutorConfigCache()
        # Initialize with shadow=False.
        with patch.object(
            cache, "_fetch_via_ipc_blocking",
            return_value=_make_runtime_config(shadow=False, version=10),
        ):
            cache._poll_once()
        self.assertFalse(cache.get().shadow_mode)

        agent = _build_agent_with_cache(cache)

        # Now IPC fails on next poll.  / 下次 poll IPC 失敗。
        with patch.object(
            cache, "_fetch_via_ipc_blocking",
            side_effect=ConnectionError("socket closed"),
        ):
            cache._poll_once()
        # Snapshot retained: shadow still False.
        # snapshot 保留：shadow 仍為 False。
        self.assertFalse(cache.get().shadow_mode)

        ipc_recorder = _IpcCallRecorder(success=True)
        with patch("app.paper_trading_routes._ipc_command", new=ipc_recorder):
            r = agent.execute_order(
                intent_id="i_postinit_fail_001",
                symbol="BTCUSDT", side="Buy", qty=0.01,
            )
        # Live path emitted IPC.
        # Live 路徑送出 IPC。
        self.assertTrue(r.success)
        self.assertEqual(r.metadata.get("execution_path"), "ipc_real")
        self.assertEqual(len(ipc_recorder.calls), 1)

    def test_pre_init_ipc_failure_stays_fail_closed(self) -> None:
        """Pre-init IPC failure → cache stays on fail-closed shadow=True →
        ExecutorAgent must NOT emit any SubmitOrder (principle #6).
        未初始化前 IPC 失敗 → 維持 fail-closed shadow=True → 不送 SubmitOrder。"""
        cache = ExecutorConfigCache()
        with patch.object(
            cache, "_fetch_via_ipc_blocking",
            side_effect=ConnectionError("socket missing"),
        ):
            cache._poll_once()
        self.assertFalse(cache.is_initialized())
        self.assertTrue(cache.get().shadow_mode)  # safe default

        agent = _build_agent_with_cache(cache)
        ipc_recorder = _IpcCallRecorder()

        with patch("app.paper_trading_routes._ipc_command", new=ipc_recorder):
            r = agent.execute_order(
                intent_id="i_preinit_fail_001",
                symbol="BTCUSDT", side="Buy", qty=0.01,
            )

        self.assertEqual(r.error, "shadow_mode")
        self.assertEqual(
            ipc_recorder.calls, [],
            "pre-init IPC failure must keep agent in shadow / 未初始化失敗須保持 shadow",
        )


class TestPerEngineIsolation(unittest.TestCase):
    """5. Per-engine isolation: demo executor flip does not affect paper.
    5. 引擎間隔離：demo executor 翻轉不影響 paper。

    The Rust ``PerEngineRiskStores`` already guarantees this at the
    JSON-RPC layer (covered by 4 Rust IPC e2e tests in G3-02 Phase A).
    Here we verify the Python cache + agent layer mirrors that isolation
    when two cache instances are bound to different engines.
    Rust 端隔離已由 G3-02 Phase A 的 4 個 IPC 測試證實；本層驗 Python cache
    + agent 配合不同 engine 時的行為一致。
    """

    def setUp(self) -> None:
        ecc_mod._reset_for_tests()

    def tearDown(self) -> None:
        ecc_mod._reset_for_tests()

    def test_demo_flip_does_not_leak_to_paper(self) -> None:
        """Two caches (paper, demo). Flip demo → paper unaffected.
        兩 cache（paper、demo）。翻 demo → paper 不變。"""
        cache_paper = ExecutorConfigCache(engine="paper")
        cache_demo = ExecutorConfigCache(engine="demo")

        # Both start initialized with shadow=True (matching Phase A defaults).
        # 兩者初始 shadow=True（對齊 Phase A 預設）。
        with patch.object(
            cache_paper, "_fetch_via_ipc_blocking",
            return_value=_make_runtime_config(shadow=True, version=1),
        ):
            cache_paper._poll_once()
        with patch.object(
            cache_demo, "_fetch_via_ipc_blocking",
            return_value=_make_runtime_config(shadow=True, version=1),
        ):
            cache_demo._poll_once()
        self.assertTrue(cache_paper.get().shadow_mode)
        self.assertTrue(cache_demo.get().shadow_mode)

        # Flip ONLY demo to live.  / 僅翻 demo 為 live。
        with patch.object(
            cache_demo, "_fetch_via_ipc_blocking",
            return_value=_make_runtime_config(shadow=False, version=2),
        ):
            cache_demo._poll_once()

        self.assertTrue(
            cache_paper.get().shadow_mode,
            "paper cache must remain shadow=True / paper cache 須保持 shadow=True",
        )
        self.assertFalse(cache_demo.get().shadow_mode)

        # Now build two agents, one per cache, and verify behavior diverges.
        # 為兩 cache 建兩個 agent，驗證行為分歧。
        agent_paper = _build_agent_with_cache(cache_paper)
        agent_demo = _build_agent_with_cache(cache_demo)
        ipc_recorder_paper = _IpcCallRecorder(success=True)
        ipc_recorder_demo = _IpcCallRecorder(success=True)

        with patch(
            "app.paper_trading_routes._ipc_command",
            new=ipc_recorder_paper,
        ):
            r_paper = agent_paper.execute_order(
                intent_id="i_iso_paper_001",
                symbol="BTCUSDT", side="Buy", qty=0.01,
            )
        with patch(
            "app.paper_trading_routes._ipc_command",
            new=ipc_recorder_demo,
        ):
            r_demo = agent_demo.execute_order(
                intent_id="i_iso_demo_001",
                symbol="BTCUSDT", side="Buy", qty=0.01,
                metadata={"engine": "demo"},
            )

        # Paper: shadow report, no IPC.
        self.assertEqual(r_paper.error, "shadow_mode")
        self.assertEqual(ipc_recorder_paper.calls, [])

        # Demo: live IPC.
        self.assertEqual(r_demo.metadata.get("execution_path"), "ipc_real")
        self.assertEqual(len(ipc_recorder_demo.calls), 1)
        self.assertEqual(ipc_recorder_demo.calls[0]["method"], "submit_paper_order")
        self.assertEqual(ipc_recorder_demo.calls[0]["params"]["engine"], "demo")

    def test_paper_engine_default_unaffected_by_demo_cache(self) -> None:
        """Even if demo cache hasn't initialized, paper agent stays consistent
        with its own cache snapshot. (No cross-engine global leak.)
        即使 demo cache 未初始化，paper agent 仍以自身 cache snapshot 為準。"""
        cache_paper = ExecutorConfigCache(engine="paper")
        cache_demo = ExecutorConfigCache(engine="demo")

        # Paper: initialize live.  / Paper 初始為 live。
        with patch.object(
            cache_paper, "_fetch_via_ipc_blocking",
            return_value=_make_runtime_config(shadow=False, version=1),
        ):
            cache_paper._poll_once()
        # Demo: never polled (uninitialized, fail-closed default shadow=True).
        # Demo：從未 poll（未初始化，fail-closed shadow=True）。
        self.assertFalse(cache_paper.get().shadow_mode)
        self.assertTrue(cache_demo.get().shadow_mode)
        self.assertFalse(cache_demo.is_initialized())

        agent_paper = _build_agent_with_cache(cache_paper)
        ipc_recorder = _IpcCallRecorder(success=True)
        with patch("app.paper_trading_routes._ipc_command", new=ipc_recorder):
            r = agent_paper.execute_order(
                intent_id="i_iso_paper_only_001",
                symbol="BTCUSDT", side="Buy", qty=0.01,
            )

        # Paper agent reads ONLY paper cache → live → IPC fires.
        # Paper agent 只讀 paper cache → live → IPC 觸發。
        self.assertEqual(r.metadata.get("execution_path"), "ipc_real")
        self.assertEqual(len(ipc_recorder.calls), 1)


if __name__ == "__main__":
    unittest.main()
