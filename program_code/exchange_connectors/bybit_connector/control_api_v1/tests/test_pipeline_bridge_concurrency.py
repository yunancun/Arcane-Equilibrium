"""
MODULE_NOTE:
  EN: Concurrency tests for PipelineBridge._lock — deadlock risk analysis and thread-safety
      verification. Covers: concurrent on_tick, concurrent setter calls, and GovernanceHub
      interaction patterns.
  CN: PipelineBridge._lock 并发测试 — 死锁风险分析与线程安全验证。
      覆盖场景：并发 on_tick、并发 setter 调用、GovernanceHub 交互模式。

P1-18 任务：Wave 2 并发安全审计
测试设计者：E4（测试工程师）
参考报告：docs/audit/March31/PM_review_2026-03-31.md  P1-18
"""

import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# ─── Path setup ───────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.pipeline_bridge import PipelineBridge

# ─── Shared helpers ───────────────────────────────────────────────────────────

TICK_TIMEOUT_S = 5  # Maximum seconds allowed for any concurrent operation


def _make_bridge(*, auto_submit=False, with_stop_mgr=False, with_gov_hub=False) -> PipelineBridge:
    """
    Build a minimal PipelineBridge with all mandatory collaborators mocked.
    Returns a bridge in activated state.
    构建最小化 PipelineBridge，所有必要协作者均 Mock，返回已激活的桥接器。
    """
    mock_orch = MagicMock()
    mock_orch.collect_pending_intents.return_value = []
    mock_orch.dispatch_tick.return_value = None

    mock_km = MagicMock()
    mock_km.on_price_event.return_value = None
    mock_km.bootstrap_from_rest.return_value = {}

    bridge = PipelineBridge(
        kline_manager=mock_km,
        indicator_engine=MagicMock(),
        signal_engine=MagicMock(),
        orchestrator=mock_orch,
        paper_engine=MagicMock(),
        stop_manager=MagicMock() if with_stop_mgr else None,
        auto_submit_intents=auto_submit,
    )

    if with_gov_hub:
        mock_hub = MagicMock()
        mock_hub.is_authorized.return_value = True
        bridge.set_governance_hub(mock_hub)

    bridge._active = True  # Skip bootstrap REST call side effects
    return bridge


def _make_tick_event(symbol="BTCUSDT", price=50000.0) -> dict:
    return {"symbol": symbol, "last_price": price, "ts_ms": int(time.time() * 1000)}


# ══════════════════════════════════════════════════════════════════════════════
# Section 1: LOCK STRUCTURE ANALYSIS (静态分析确认，不执行实际并发)
# ══════════════════════════════════════════════════════════════════════════════

class TestLockStructureAnalysis(unittest.TestCase):
    """
    Static analysis of locking structure:
    - Verify lock type (non-reentrant threading.Lock)
    - Map all with-self._lock blocks and their nesting
    锁结构静态分析：验证锁类型、映射所有持锁块及其嵌套关系。
    """

    def test_001_lock_is_non_reentrant(self):
        """
        Lock must be threading.Lock (not RLock).
        GovernanceHub uses threading.RLock — the two are different objects, no shared lock.
        锁必须是 threading.Lock（非 RLock）。GovernanceHub 使用独立的 RLock，两者无共享。
        """
        bridge = _make_bridge()
        self.assertIsInstance(bridge._lock, type(threading.Lock()))
        # Confirm it is NOT a reentrant lock
        self.assertNotIsInstance(bridge._lock, type(threading.RLock()))

    def test_002_governance_hub_uses_separate_lock(self):
        """
        GovernanceHub._lock is a separate threading.RLock — it is NOT the same object
        as PipelineBridge._lock, confirming no shared-lock scenario.
        GovernanceHub._lock 是独立的 RLock，与 PipelineBridge._lock 不同对象。
        """
        from app.governance_hub import GovernanceHub
        import tempfile, os
        with tempfile.TemporaryDirectory() as d:
            hub = GovernanceHub(audit_dir=d)
        bridge = _make_bridge()
        self.assertIsNot(bridge._lock, hub._lock)
        self.assertNotEqual(id(bridge._lock), id(hub._lock))

    def test_003_on_tick_releases_lock_before_check_stops(self):
        """
        Key structural invariant: on_tick releases self._lock (at line ~301-303)
        before reaching the _check_stops() call (~line 400).
        The lock is held only briefly to update _stats — NOT across external calls.
        关键结构不变式：on_tick 在调用 _check_stops() 之前已释放 self._lock。
        锁仅短暂持有用于更新 _stats，不跨越外部调用。
        """
        bridge = _make_bridge(with_stop_mgr=True)
        lock_held_during_check_stops = []

        original_check_stops = bridge._check_stops

        def spy_check_stops():
            # Try to acquire the lock — if on_tick still holds it, this would block
            # 尝试获取锁——如果 on_tick 仍持有，会阻塞
            acquired = bridge._lock.acquire(blocking=False)
            lock_held_during_check_stops.append(not acquired)
            if acquired:
                bridge._lock.release()
            original_check_stops()

        bridge._check_stops = spy_check_stops

        event = _make_tick_event()
        bridge.on_tick(event)

        self.assertTrue(
            len(lock_held_during_check_stops) > 0,
            "_check_stops spy was never called"
        )
        self.assertFalse(
            any(lock_held_during_check_stops),
            "on_tick was holding self._lock when _check_stops was called — "
            "this confirms a potential nested lock pattern; check if _check_stops "
            "then acquires GovernanceHub lock"
        )

    def test_004_check_stops_does_not_call_governance_hub(self):
        """
        _check_stops() path: StopManager.check_stops → submit_order on paper engine.
        GovernanceHub.is_authorized() is NOT called in the stop path — only in
        _process_pending_intents(). No cross-object lock chain in stop path.
        _check_stops 路径不调用 GovernanceHub.is_authorized()，无跨对象锁链。
        """
        bridge = _make_bridge(with_stop_mgr=True, with_gov_hub=True)
        gov_hub = bridge._governance_hub

        # Configure stop manager to simulate a triggered stop
        stop_entry = {
            "symbol": "BTCUSDT",
            "side": "Sell",
            "qty": 0.01,
            "reason": "hard_stop",
            "stop_type": "hard",
            "strategy_name": "test_strat",
        }
        bridge._stop_mgr.check_stops.return_value = [stop_entry]
        bridge._latest_prices = {"BTCUSDT": 49000.0}

        # Paper engine: position exists → stop order allowed
        bridge._engine.get_state.return_value = {
            "positions": {"BTCUSDT": {"qty": 0.01}}
        }
        bridge._engine.submit_order.return_value = {"order": {}, "fills": []}

        bridge._check_stops()

        # GovernanceHub.is_authorized must NOT be called in the stop path
        gov_hub.is_authorized.assert_not_called()


# ══════════════════════════════════════════════════════════════════════════════
# Section 2: CONCURRENT on_tick (两线程同时调用 on_tick)
# ══════════════════════════════════════════════════════════════════════════════

class TestConcurrentOnTick(unittest.TestCase):
    """
    Two threads call on_tick simultaneously.
    Verifies: no deadlock within TICK_TIMEOUT_S, stats remain consistent.
    两线程同时调用 on_tick。验证：无死锁（5 秒超时），统计一致。
    """

    def _run_concurrent(self, bridge, n_threads=2, n_ticks_each=10):
        """Helper: spawn N threads each sending n_ticks_each tick events."""
        errors = []
        threads = []
        barrier = threading.Barrier(n_threads)

        def worker(thread_id):
            try:
                barrier.wait(timeout=TICK_TIMEOUT_S)
                for i in range(n_ticks_each):
                    event = _make_tick_event(
                        symbol="BTCUSDT" if thread_id == 0 else "ETHUSDT",
                        price=50000.0 + i,
                    )
                    bridge.on_tick(event)
            except Exception as exc:
                errors.append(exc)

        for i in range(n_threads):
            t = threading.Thread(target=worker, args=(i,), daemon=True)
            threads.append(t)
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=TICK_TIMEOUT_S)

        live = [t for t in threads if t.is_alive()]
        return live, errors

    def test_010_two_threads_no_deadlock(self):
        """
        Two threads calling on_tick simultaneously must complete without deadlock.
        Timeout = 5 seconds.
        两线程并发 on_tick 必须在 5 秒内完成，无死锁。
        """
        bridge = _make_bridge()
        live, errors = self._run_concurrent(bridge, n_threads=2, n_ticks_each=20)

        self.assertEqual(
            live, [],
            f"Deadlock detected: {len(live)} thread(s) still alive after {TICK_TIMEOUT_S}s"
        )
        self.assertEqual(errors, [], f"Thread errors: {errors}")

    def test_011_stats_monotonically_increase_under_concurrency(self):
        """
        ticks_received must increase monotonically; no lost updates under concurrent writes.
        并发写入下 ticks_received 必须单调递增，不能有更新丢失。
        """
        bridge = _make_bridge()
        n_threads = 4
        n_ticks = 25

        live, errors = self._run_concurrent(bridge, n_threads=n_threads, n_ticks_each=n_ticks)

        self.assertEqual(live, [], "Deadlock detected")
        self.assertEqual(errors, [])

        received = bridge._stats["ticks_received"]
        expected = n_threads * n_ticks
        self.assertEqual(
            received, expected,
            f"ticks_received={received} != expected={expected}; possible lost update under concurrency"
        )

    def test_012_concurrent_ticks_with_stop_manager(self):
        """
        Two threads firing on_tick while stop manager is active.
        Stop manager returns empty list to avoid complex mock setup.
        带止损管理器的并发 on_tick，止损管理器返回空列表。
        """
        bridge = _make_bridge(with_stop_mgr=True)
        bridge._stop_mgr.check_stops.return_value = []
        bridge._latest_prices = {"BTCUSDT": 50000.0}

        live, errors = self._run_concurrent(bridge, n_threads=2, n_ticks_each=15)
        self.assertEqual(live, [], "Deadlock with StopManager active")
        self.assertEqual(errors, [])

    def test_013_concurrent_ticks_with_governance_hub(self):
        """
        Two threads firing on_tick while GovernanceHub is set.
        GovernanceHub.is_authorized() may be called inside lock-free section.
        GovernanceHub 已设置时的并发 on_tick，is_authorized 在无锁区间调用。
        """
        bridge = _make_bridge(with_gov_hub=True, auto_submit=True)

        # Guardian not set → all intents fail-closed, no submit_order called
        # This tests the lock interaction without needing full execution path
        bridge._orch.collect_pending_intents.return_value = []

        live, errors = self._run_concurrent(bridge, n_threads=2, n_ticks_each=15)
        self.assertEqual(live, [], "Deadlock with GovernanceHub active")
        self.assertEqual(errors, [])

    def test_014_high_contention_stress(self):
        """
        Stress test: 8 threads × 50 ticks = 400 total ticks under high lock contention.
        Verifies no deadlock or data corruption under sustained load.
        高竞争压力测试：8 线程 × 50 tick = 400 次总调用，验证无死锁或数据损坏。
        """
        bridge = _make_bridge()
        live, errors = self._run_concurrent(bridge, n_threads=8, n_ticks_each=50)

        self.assertEqual(live, [], f"Stress test deadlock: {len(live)} threads still alive")
        self.assertEqual(errors, [])

        # Stats must equal total ticks sent
        self.assertEqual(bridge._stats["ticks_received"], 8 * 50)


# ══════════════════════════════════════════════════════════════════════════════
# Section 3: on_tick CONCURRENT WITH SETTER CALLS
# ══════════════════════════════════════════════════════════════════════════════

class TestOnTickConcurrentWithSetters(unittest.TestCase):
    """
    on_tick runs in thread A while setter methods run in thread B.
    Setters write to plain instance attributes (no lock), which is the race condition
    documented in the audit report.
    线程 A 执行 on_tick，线程 B 同时调用 setter 方法。
    Setter 写入无锁的实例属性 — 审计报告记录的竞态条件。
    """

    def _run_tick_and_setter(self, bridge, setter_fn, n_ticks=30):
        """Run on_tick loop in thread A, setter in thread B simultaneously."""
        errors = []
        barrier = threading.Barrier(2)
        done = threading.Event()

        def tick_worker():
            try:
                barrier.wait(timeout=TICK_TIMEOUT_S)
                for i in range(n_ticks):
                    bridge.on_tick(_make_tick_event(price=50000.0 + i))
            except Exception as exc:
                errors.append(("tick_worker", exc))
            finally:
                done.set()

        def setter_worker():
            try:
                barrier.wait(timeout=TICK_TIMEOUT_S)
                for _ in range(10):
                    setter_fn()
                    time.sleep(0.001)
            except Exception as exc:
                errors.append(("setter_worker", exc))

        t1 = threading.Thread(target=tick_worker, daemon=True)
        t2 = threading.Thread(target=setter_worker, daemon=True)
        t1.start()
        t2.start()
        t1.join(timeout=TICK_TIMEOUT_S)
        t2.join(timeout=TICK_TIMEOUT_S)

        live = [t for t in [t1, t2] if t.is_alive()]
        return live, errors

    def test_020_on_tick_and_set_guardian_agent_concurrent(self):
        """
        set_guardian_agent() writes to self._guardian_agent (no lock).
        on_tick reads self._guardian_agent in _process_pending_intents.
        OBSERVATION: CPython GIL prevents torn reads for object attribute assignment,
        but this is an implementation detail — not a language guarantee.
        No deadlock expected (different attributes, no cross-lock).
        set_guardian_agent 写 self._guardian_agent（无锁），on_tick 读取该属性。
        CPython GIL 防止撕裂读，但这是实现细节。预期无死锁。
        """
        bridge = _make_bridge(auto_submit=True)
        mock_guardian = MagicMock()
        mock_guardian.review_intent.return_value = MagicMock(result="REJECTED", reason="test")
        bridge._orch.collect_pending_intents.return_value = []

        live, errors = self._run_tick_and_setter(
            bridge,
            setter_fn=lambda: bridge.set_guardian_agent(mock_guardian),
            n_ticks=30,
        )
        self.assertEqual(live, [], "Deadlock: on_tick + set_guardian_agent")
        # Errors from setter or tick worker indicate thread-safety issue
        self.assertEqual(errors, [], f"Errors during concurrent access: {errors}")

    def test_021_on_tick_and_set_governance_hub_concurrent(self):
        """
        set_governance_hub() writes to self._governance_hub (no lock).
        on_tick reads it in _process_pending_intents at governance check.
        Verify no deadlock or unhandled exception.
        set_governance_hub 写 self._governance_hub（无锁），并发验证无死锁。
        """
        bridge = _make_bridge(auto_submit=True)
        mock_hub = MagicMock()
        mock_hub.is_authorized.return_value = True
        bridge._orch.collect_pending_intents.return_value = []

        live, errors = self._run_tick_and_setter(
            bridge,
            setter_fn=lambda: bridge.set_governance_hub(mock_hub),
            n_ticks=30,
        )
        self.assertEqual(live, [], "Deadlock: on_tick + set_governance_hub")
        self.assertEqual(errors, [])

    def test_022_on_tick_and_activate_deactivate_concurrent(self):
        """
        activate()/is_active() read/write self._active (no lock).
        on_tick checks self._active at entry. Race is benign in CPython
        (bool assignment is atomic under GIL), but tests document the pattern.
        activate/deactivate 并发访问 self._active（无锁），CPython GIL 下安全。
        """
        bridge = _make_bridge()
        bridge._active = True

        live, errors = self._run_tick_and_setter(
            bridge,
            setter_fn=lambda: setattr(bridge, "_active", True),  # keep active during test
            n_ticks=30,
        )
        self.assertEqual(live, [], "Deadlock: on_tick + _active toggle")
        self.assertEqual(errors, [])


# ══════════════════════════════════════════════════════════════════════════════
# Section 4: GOVERNANCE HUB CALLBACK PATH (双向锁链分析)
# ══════════════════════════════════════════════════════════════════════════════

class TestGovernanceHubCallbackPath(unittest.TestCase):
    """
    Analyzes the two-way lock chain scenario:
      PipelineBridge._lock → (released) → GovernanceHub._lock → callback? → PipelineBridge._lock

    For a true deadlock to occur:
      1. Thread A must hold PipelineBridge._lock AND wait for GovernanceHub._lock
      2. Thread B must hold GovernanceHub._lock AND wait for PipelineBridge._lock

    This section verifies the actual call sequence prevents this pattern.
    分析双向锁链场景：验证实际调用序列是否能触发真实死鎖。
    """

    def test_030_governance_is_authorized_called_outside_pipeline_lock(self):
        """
        CRITICAL FINDING VERIFICATION: governance_hub.is_authorized() is called
        at line ~492 in _process_pending_intents(), which is called from on_tick()
        at line ~396 — both AFTER the self._lock block at lines 301-303 is released.

        This confirms: PipelineBridge does NOT hold self._lock when calling
        GovernanceHub.is_authorized(). No Lock-A→Lock-B hold pattern exists.
        关键发现验证：调用 GovernanceHub.is_authorized() 时 PipelineBridge._lock 已释放。
        """
        bridge = _make_bridge(with_gov_hub=True, auto_submit=True)
        mock_hub = bridge._governance_hub

        lock_state_during_auth_check = []

        original_is_authorized = mock_hub.is_authorized

        def spy_is_authorized():
            # Try non-blocking acquire; success means PipelineBridge does NOT hold the lock
            acquired = bridge._lock.acquire(blocking=False)
            lock_state_during_auth_check.append(acquired)
            if acquired:
                bridge._lock.release()
            return True

        mock_hub.is_authorized.side_effect = spy_is_authorized

        # Set up an intent so governance check is actually reached
        mock_intent = MagicMock()
        mock_intent.symbol = "BTCUSDT"
        mock_intent.side = "Buy"
        mock_intent.qty = 0.01
        mock_intent.metadata = {}
        mock_intent.perception_data_id = None
        mock_intent.order_type = "market"
        mock_intent.price = None
        bridge._orch.collect_pending_intents.return_value = [mock_intent]

        # Guardian not set → fail-closed REJECT after governance check
        bridge._guardian_agent = None

        bridge._process_pending_intents()

        self.assertTrue(
            len(lock_state_during_auth_check) > 0,
            "is_authorized() was never called — check mock setup or intent path"
        )
        self.assertTrue(
            all(lock_state_during_auth_check),
            "PipelineBridge._lock was HELD when is_authorized() was called — "
            "this creates a lock ordering risk if GovernanceHub tries to acquire "
            "PipelineBridge._lock in a callback"
        )

    def test_031_governance_hub_has_no_pipeline_bridge_reference(self):
        """
        Verify GovernanceHub does not store any reference to PipelineBridge,
        ruling out callback-induced reverse lock acquisition.
        验证 GovernanceHub 不持有 PipelineBridge 引用，排除回调触发反向锁获取。
        """
        import tempfile
        from app.governance_hub import GovernanceHub

        with tempfile.TemporaryDirectory() as d:
            hub = GovernanceHub(audit_dir=d)

        # GovernanceHub should have no attribute pointing to a PipelineBridge
        hub_dict = vars(hub)
        pipeline_refs = [
            k for k, v in hub_dict.items()
            if isinstance(v, PipelineBridge)
        ]
        self.assertEqual(
            pipeline_refs, [],
            f"GovernanceHub holds PipelineBridge references: {pipeline_refs}"
        )

    def test_032_simulated_governance_with_slow_lock(self):
        """
        Simulate GovernanceHub.is_authorized() acquiring its own internal lock slowly.
        Even with this delay, PipelineBridge should not deadlock because PipelineBridge
        does NOT hold self._lock during the call.
        模拟 GovernanceHub.is_authorized() 缓慢获取自身锁。
        即使有延迟，PipelineBridge 也不应死锁，因为调用时 PipelineBridge._lock 已释放。
        """
        bridge = _make_bridge(with_gov_hub=True, auto_submit=True)
        slow_internal_lock = threading.Lock()
        call_count = [0]

        def slow_is_authorized():
            # Simulate GovernanceHub acquiring its own lock (slow)
            with slow_internal_lock:
                time.sleep(0.01)
                call_count[0] += 1
            return True

        bridge._governance_hub.is_authorized.side_effect = slow_is_authorized

        mock_intent = MagicMock()
        mock_intent.symbol = "BTCUSDT"
        mock_intent.side = "Buy"
        mock_intent.qty = 0.01
        mock_intent.metadata = {}
        mock_intent.perception_data_id = None
        mock_intent.order_type = "market"
        mock_intent.price = None
        bridge._orch.collect_pending_intents.return_value = [mock_intent]
        bridge._guardian_agent = None  # fail-closed after governance passes

        start = time.time()
        bridge._process_pending_intents()
        elapsed = time.time() - start

        self.assertGreater(call_count[0], 0, "is_authorized never called")
        self.assertLess(elapsed, TICK_TIMEOUT_S, "Operation timed out — possible deadlock")


# ══════════════════════════════════════════════════════════════════════════════
# Section 5: LOCK RE-ENTRANCY RISK (非可重入锁 + 同一线程嵌套)
# ══════════════════════════════════════════════════════════════════════════════

class TestLockReentrancyRisk(unittest.TestCase):
    """
    PipelineBridge uses threading.Lock (non-reentrant).
    If any code path calls with self._lock: from within an already-locked section
    in the SAME thread, it will deadlock immediately.
    验证同一线程内是否存在嵌套 with self._lock: 调用（会立即死锁）。
    """

    def test_040_check_stops_does_not_reenter_lock(self):
        """
        _check_stops() acquires self._lock at line ~759 (stops_triggered update).
        Verify that calling _check_stops() directly (when lock is NOT held by caller)
        completes without deadlock — confirming no accidental re-entrancy.
        _check_stops 在 ~759 行获取锁，直接调用时（调用方未持锁）应正常完成。
        """
        bridge = _make_bridge(with_stop_mgr=True)
        stop_entry = {
            "symbol": "BTCUSDT",
            "side": "Sell",
            "qty": 0.01,
            "reason": "hard_stop",
            "stop_type": "hard",
            "strategy_name": "test",
        }
        bridge._stop_mgr.check_stops.return_value = [stop_entry]
        bridge._latest_prices = {"BTCUSDT": 49000.0}
        bridge._engine.get_state.return_value = {
            "positions": {"BTCUSDT": {"qty": 0.01}}
        }
        bridge._engine.submit_order.return_value = {"order": {}, "fills": []}

        completed = threading.Event()

        def run():
            bridge._check_stops()
            completed.set()

        t = threading.Thread(target=run, daemon=True)
        t.start()
        t.join(timeout=TICK_TIMEOUT_S)

        self.assertTrue(
            completed.is_set(),
            f"_check_stops() did not complete within {TICK_TIMEOUT_S}s — "
            "possible deadlock or re-entrancy with non-reentrant lock"
        )

    def test_041_check_edge_filter_does_not_reenter_lock(self):
        """
        _check_edge_filter() acquires self._lock at lines ~886, ~892, ~947, ~973, ~978, ~984.
        All are brief atomic stat updates; none are nested. Verify completion.
        _check_edge_filter 多处获取锁，均为原子统计更新，无嵌套。验证正常完成。
        """
        bridge = _make_bridge()

        mock_ollama = MagicMock()
        mock_ollama.is_available.return_value = True
        mock_response = MagicMock()
        mock_response.success = True
        mock_response.text = '{"has_edge": true, "confidence": 0.8, "reason": "test"}'
        mock_response.latency_ms = 100
        mock_ollama.judge_edge.return_value = mock_response
        bridge._ollama_client = mock_ollama

        mock_intent = MagicMock()
        mock_intent.symbol = "BTCUSDT"
        mock_intent.side = "Buy"
        mock_intent.metadata = {"strategy_name": "test"}

        completed = threading.Event()

        def run():
            bridge._check_edge_filter(mock_intent, {"BTCUSDT": 50000.0})
            completed.set()

        t = threading.Thread(target=run, daemon=True)
        t.start()
        t.join(timeout=TICK_TIMEOUT_S)

        self.assertTrue(
            completed.is_set(),
            "_check_edge_filter() did not complete — possible lock re-entrancy"
        )


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    unittest.main(verbosity=2)
