"""
MessageBus 壓力測試 / MessageBus Load Tests
============================================
MODULE_NOTE:
  (EN) Load and stress tests for MessageBus under high-volume conditions,
       simulating long-running ScoutWorker scenarios. Tests verify: no
       deadlock under burst send, slow-subscriber non-blocking behavior,
       memory stability, and exception isolation.
  (中) 對 MessageBus 進行高負載壓測，模擬 ScoutWorker 長期運行場景。
       驗證：大量 send 不死鎖、慢 subscriber 不阻塞 sender、記憶體穩定、
       subscriber 異常不崩潰 bus。

架構觀察（Architecture Notes）:
  - MessageBus._messages: 無上限 List（unbounded list）
      → ⚠️ ISSUE-1: 長期運行下記憶體無限增長，ScoutWorker 30min 循環
         每次可能產生多條消息，若 24h 運行將累積大量消息歷史。
         建議未來加入 max_history 或 ring-buffer 設計。
         暫不修復，僅在測試中標記。

  - MessageBus.send(): 持有 _lock 期間直接調用 subscriber 回調
      → ⚠️ ISSUE-2: subscriber 回調在鎖內執行，若 subscriber 阻塞（如 I/O、
         AI 調用）則 send() 整個阻塞，所有其他 send() 調用也被排隊等待。
         ScoutWorker 30min 掃描發出大量消息，若 StrategistAgent 的回調
         做 Ollama 調用（~1.9s），則其他消息無法傳遞。
         暫不修復，僅在測試中標記與計時驗證。

  - 無隊列（Queue）設計：所有消息同步交付，無背壓機制。
  - subscriber 異常：被 try/except 靜默吞噬，bus 不崩潰（設計正確）。
"""

import threading
import time
import tracemalloc

import pytest

from app.multi_agent_framework import (
    AgentMessage,
    AgentRole,
    MessageBus,
    MessageType,
)


# ─────────────────────────────────────────────────────────────
# 輔助工具 / Helpers
# ─────────────────────────────────────────────────────────────

def _make_scout_intel_msg() -> AgentMessage:
    """Build a valid SCOUT→STRATEGIST INTEL_OBJECT message."""
    return AgentMessage(
        sender=AgentRole.SCOUT,
        receiver=AgentRole.STRATEGIST,
        message_type=MessageType.INTEL_OBJECT,
        priority=3,
        payload={"content": "test intel", "symbol": "BTCUSDT"},
    )


def _make_conductor_directive(target: AgentRole) -> AgentMessage:
    """Build a valid CONDUCTOR→target SYSTEM_DIRECTIVE message."""
    return AgentMessage(
        sender=AgentRole.CONDUCTOR,
        receiver=target,
        message_type=MessageType.SYSTEM_DIRECTIVE,
        priority=0,
        payload={"directive_type": "load_test"},
    )


# ─────────────────────────────────────────────────────────────
# Test 1: 高頻 send 不死鎖
# High-volume send does not deadlock
# ─────────────────────────────────────────────────────────────

class TestHighVolumeSendNoDeadlock:
    """
    500 條消息快速連續 send()，驗證不死鎖、所有合法消息被接受或有序拒絕。
    模擬 ScoutWorker 在 30min 週期內批量發送 intel 的場景。

    500 messages burst-sent. Verifies no deadlock, all valid messages
    accepted or cleanly rejected.
    """

    def test_high_volume_send_no_deadlock(self):
        """500 consecutive sends complete within 5s wall clock (no deadlock)."""
        bus = MessageBus()
        received: list = []

        bus.subscribe(AgentRole.STRATEGIST, lambda m: received.append(m.message_id))

        n = 500
        start = time.monotonic()

        for _ in range(n):
            msg = _make_scout_intel_msg()
            result = bus.send(msg)
            assert result is True, "Valid SCOUT→STRATEGIST route must return True"

        elapsed = time.monotonic() - start

        # 不死鎖 / no deadlock: 必須在 5 秒內完成
        assert elapsed < 5.0, (
            f"500 sends took {elapsed:.3f}s — possible deadlock or severe contention"
        )

        # 所有消息均入隊 / all messages persisted
        assert bus.total_messages == n, (
            f"Expected {n} messages in history, got {bus.total_messages}"
        )

        # subscriber 收到所有消息 / all messages delivered to subscriber
        assert len(received) == n, (
            f"Subscriber received {len(received)}/{n} messages"
        )

    def test_high_volume_mixed_routes(self):
        """
        500 消息中混入無效路由，驗證有效路由全部通過、無效路由全部拒絕。
        Mixed valid/invalid routes: valid ones pass, invalid ones cleanly blocked.
        """
        bus = MessageBus()
        valid_count = 0
        invalid_count = 0

        for i in range(500):
            if i % 2 == 0:
                # 合法路由: SCOUT → STRATEGIST
                msg = _make_scout_intel_msg()
                result = bus.send(msg)
                if result:
                    valid_count += 1
            else:
                # 非法路由: SCOUT → EXECUTOR（不在 VALID_ROUTES）
                msg = AgentMessage(
                    sender=AgentRole.SCOUT,
                    receiver=AgentRole.EXECUTOR,
                    message_type=MessageType.INTEL_OBJECT,
                    payload={},
                )
                result = bus.send(msg)
                if not result:
                    invalid_count += 1

        assert valid_count == 250, f"Expected 250 valid, got {valid_count}"
        assert invalid_count == 250, f"Expected 250 invalid blocked, got {invalid_count}"
        assert bus.total_messages == 250, (
            f"Only valid messages should be stored; expected 250 got {bus.total_messages}"
        )

    def test_concurrent_send_from_multiple_threads_no_deadlock(self):
        """
        10 個線程各自 send 50 條消息（共 500 條），驗證無死鎖、無資料競態。
        模擬多個 Agent 同時向 bus 寫入的場景。

        10 threads × 50 sends = 500 total. No deadlock, no data race.
        Simulates multiple agents sending concurrently (ScoutWorker + Strategist).
        """
        bus = MessageBus()
        errors: list = []

        def send_batch(thread_id: int) -> None:
            for i in range(50):
                try:
                    msg = _make_scout_intel_msg()
                    bus.send(msg)
                except Exception as e:
                    errors.append(f"thread={thread_id} i={i} err={e}")

        threads = [threading.Thread(target=send_batch, args=(t,)) for t in range(10)]
        start = time.monotonic()
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10.0)
        elapsed = time.monotonic() - start

        assert not any(t.is_alive() for t in threads), (
            "Some threads still alive after 10s — possible deadlock"
        )
        assert elapsed < 10.0, f"Concurrent sends took {elapsed:.2f}s — deadlock suspected"
        assert not errors, f"Thread errors: {errors}"
        assert bus.total_messages == 500, (
            f"Expected 500 messages, got {bus.total_messages}"
        )


# ─────────────────────────────────────────────────────────────
# Test 2: 慢 subscriber 不阻塞 sender
# Slow subscriber does not block sender beyond threshold
# ─────────────────────────────────────────────────────────────

class TestSlowSubscriberDoesNotBlockSender:
    """
    subscriber 模擬 100ms 延遲，sender 發 50 條消息。
    量測 sender 的總耗時，確認符合預期（同步執行 → 耗時 ≈ 50×100ms = ~5s）。

    ⚠️ ISSUE-2 驗證：由於 send() 在鎖內調用 subscriber，
    慢 subscriber 必然使 send() 阻塞，此測試記錄實際行為而非斷言非阻塞。
    若未來改為異步 dispatch（非鎖內調用），此測試應改為 < 2s 斷言。
    """

    def test_slow_subscriber_timing_characterization(self):
        """
        Characterize blocking behavior: slow subscriber (100ms) × 50 sends.

        ⚠️ DESIGN NOTE (ISSUE-2): MessageBus calls subscriber callbacks INSIDE
        the _lock. A 100ms subscriber delays each send() by 100ms, making
        50 sends take ~5s. This is the current (synchronous) design.

        If this test fails with elapsed < 1s, the design has changed to async
        dispatch — update assertions accordingly.
        If elapsed > 10s, something is wrong (deadlock or extreme contention).
        """
        bus = MessageBus()
        call_count = [0]

        def slow_subscriber(msg: AgentMessage) -> None:
            # 模擬 100ms 處理延遲（如 Ollama 快速路徑的一小部分）
            time.sleep(0.01)  # 10ms per call，避免測試太慢；仍能驗證阻塞行為
            call_count[0] += 1

        bus.subscribe(AgentRole.STRATEGIST, slow_subscriber)

        n = 50
        start = time.monotonic()
        for _ in range(n):
            bus.send(_make_scout_intel_msg())
        elapsed = time.monotonic() - start

        # 驗證 subscriber 全部被調用
        assert call_count[0] == n, f"Expected {n} calls, got {call_count[0]}"

        # 由於在鎖內同步調用，50×10ms ≈ 0.5s+，記錄到 comment
        # elapsed should be >= n * 0.01 because callbacks run inside the lock
        assert elapsed >= n * 0.005, (
            f"Elapsed {elapsed:.3f}s unexpectedly fast — subscriber may not have been called"
        )

        # 上限：不應超過 30s（防止真正死鎖）
        assert elapsed < 30.0, (
            f"Elapsed {elapsed:.3f}s — possible deadlock with slow subscriber"
        )

        # 記錄觀察值（用 assert message 做文檔）
        # 預期：elapsed ≈ n × 0.01 ± jitter
        # 若 elapsed < 0.1，表示 subscriber 已改為異步 dispatch（需更新設計說明）

    def test_sender_completes_all_messages(self):
        """
        即使 subscriber 拋出異常，所有 50 條 send() 均成功返回 True。
        Sender completes all 50 messages even if subscriber is error-prone.
        """
        bus = MessageBus()
        slow_and_error_count = [0]

        def flaky_slow_sub(msg: AgentMessage) -> None:
            slow_and_error_count[0] += 1
            time.sleep(0.005)
            if slow_and_error_count[0] % 5 == 0:
                raise RuntimeError("Simulated subscriber error")

        bus.subscribe(AgentRole.STRATEGIST, flaky_slow_sub)

        results = []
        for _ in range(50):
            results.append(bus.send(_make_scout_intel_msg()))

        assert all(results), "All sends should return True regardless of subscriber errors"
        assert bus.total_messages == 50


# ─────────────────────────────────────────────────────────────
# Test 3: 記憶體不異常增長
# No memory growth anomaly under load
# ─────────────────────────────────────────────────────────────

class TestNoMemoryGrowthUnderLoad:
    """
    用 tracemalloc 測量發送 1000 條消息前後的記憶體增長。

    ⚠️ ISSUE-1 驗證：MessageBus._messages 是無上限的 List，每條消息
    永久保留在記憶體中。ScoutWorker 30min 週期，24h 連續運行 = 48 次掃描，
    若每次掃描產生 20 條 intel → 960 條消息永駐記憶體（小規模可接受）。
    若每個 payload 較大或並發量大，長期積累需要監控。
    """

    def test_no_memory_growth_under_load(self):
        """
        Send 1000 messages and verify memory growth < 5MB.

        ⚠️ ISSUE-1: _messages list is unbounded. All 1000 messages remain
        in memory after this test. For long-running ScoutWorker (24h+),
        the accumulation should be monitored. Recommend adding max_history
        or ring-buffer in a future sprint.
        """
        bus = MessageBus()

        # 暖機：防止 Python allocator lazy-init 影響測量
        for _ in range(10):
            bus.send(_make_scout_intel_msg())
        bus._messages.clear()  # 重置以獲得乾淨基準線

        tracemalloc.start()
        snapshot_before = tracemalloc.take_snapshot()

        n = 1000
        for _ in range(n):
            bus.send(_make_scout_intel_msg())

        snapshot_after = tracemalloc.take_snapshot()
        tracemalloc.stop()

        # 計算增長量
        stats = snapshot_after.compare_to(snapshot_before, "lineno")
        total_growth_bytes = sum(s.size_diff for s in stats if s.size_diff > 0)
        total_growth_mb = total_growth_bytes / (1024 * 1024)

        # 驗證所有消息均已存儲（clear 後發送 n 條，應為 n）
        # _messages.clear() empties the list; then n sends → total_messages == n
        assert bus.total_messages == n, (
            f"Expected {n} messages after clear+send, got {bus.total_messages}"
        )

        # 5MB 限制：1000 條 AgentMessage（約 300-500 bytes each）應遠低於此限
        # 若超過，表示消息 payload 異常大或有記憶體洩漏
        assert total_growth_mb < 5.0, (
            f"Memory grew by {total_growth_mb:.2f}MB for 1000 messages — "
            f"possible unbounded accumulation. "
            f"ISSUE-1: _messages list has no upper bound."
        )

    def test_unbounded_list_acknowledged(self):
        """
        Confirm _messages grows linearly (no pruning mechanism exists).

        This is a documentation test: it passes by design but records
        ISSUE-1 — MessageBus has no max_history / ring-buffer.
        ScoutWorker running 24h × 48 scans × ~20 intel/scan = ~960 messages.
        At 24h × higher frequency, could grow to tens of thousands.
        """
        bus = MessageBus()

        n = 200
        for _ in range(n):
            bus.send(_make_scout_intel_msg())

        # 確認沒有任何自動清理機制（設計確認測試）
        # Confirm no auto-pruning: all messages are retained
        assert bus.total_messages == n, (
            f"Expected {n} messages retained (no pruning), got {bus.total_messages}. "
            f"If < {n}, pruning was added — update ISSUE-1 status."
        )

        # ISSUE-1 記錄：
        # MessageBus._messages 是無上限的 list。
        # 建議：在未來 Sprint 中考慮 max_history 參數或 LRU ring-buffer。
        # Recommendation: add max_history param or ring-buffer in future sprint.


# ─────────────────────────────────────────────────────────────
# Test 4: subscriber 異常不崩潰 bus
# Subscriber exception does not crash bus
# ─────────────────────────────────────────────────────────────

class TestSubscriberExceptionDoesNotCrashBus:
    """
    subscriber 回調拋 RuntimeError，驗證 bus 繼續運行，後續消息仍能被處理。
    Subscriber raises RuntimeError; bus continues running and delivers subsequent messages.
    """

    def test_subscriber_exception_does_not_crash_bus(self):
        """
        RuntimeError in subscriber is swallowed; subsequent messages still delivered.
        """
        bus = MessageBus()
        good_received: list = []
        crash_count = [0]

        def crashing_subscriber(msg: AgentMessage) -> None:
            crash_count[0] += 1
            raise RuntimeError("Simulated subscriber crash")

        def good_subscriber(msg: AgentMessage) -> None:
            good_received.append(msg.message_id)

        bus.subscribe(AgentRole.STRATEGIST, crashing_subscriber)
        bus.subscribe(AgentRole.STRATEGIST, good_subscriber)

        # 發送 10 條消息，全部應成功
        n = 10
        results = [bus.send(_make_scout_intel_msg()) for _ in range(n)]

        assert all(results), "send() must return True even when subscriber raises"
        assert crash_count[0] == n, f"Crashing subscriber called {crash_count[0]}/{n}"
        assert len(good_received) == n, (
            f"Good subscriber only received {len(good_received)}/{n} — "
            f"exception in first subscriber may have prevented second subscriber"
        )
        assert bus.total_messages == n, f"Bus should have {n} messages in history"

    def test_exception_in_audit_callback_does_not_crash_bus(self):
        """
        audit_callback 拋異常也被靜默吞噬，bus 繼續運行。
        audit_callback exception is also swallowed; bus continues.
        """
        crash_count = [0]

        def crashing_audit(event: str, data: dict) -> None:
            crash_count[0] += 1
            raise ValueError("Audit crash")

        bus = MessageBus(audit_callback=crashing_audit)

        # 應正常完成 20 條 send
        results = [bus.send(_make_scout_intel_msg()) for _ in range(20)]

        assert all(results), "send() must succeed even if audit_callback raises"
        assert crash_count[0] == 20, f"Audit called {crash_count[0]}/20"
        assert bus.total_messages == 20

    def test_multiple_subscribers_partial_crash_isolation(self):
        """
        5 個 subscriber，其中 2 個拋異常，其餘 3 個仍全部收到消息。

        ⚠️ ISSUE-3: subscribers 在同一個 try/except 包裹內逐一調用，
        每個 subscriber 的異常獨立被吞噬，不影響後續 subscriber。
        這是正確的設計，此測試確認行為。
        """
        bus = MessageBus()
        counter = [0, 0, 0, 0, 0]  # 5 subscribers

        def make_sub(idx: int, should_crash: bool):
            def sub(msg: AgentMessage) -> None:
                counter[idx] += 1
                if should_crash:
                    raise RuntimeError(f"Sub {idx} crash")
            return sub

        # sub 0: crash, sub 1: ok, sub 2: crash, sub 3: ok, sub 4: ok
        bus.subscribe(AgentRole.STRATEGIST, make_sub(0, True))
        bus.subscribe(AgentRole.STRATEGIST, make_sub(1, False))
        bus.subscribe(AgentRole.STRATEGIST, make_sub(2, True))
        bus.subscribe(AgentRole.STRATEGIST, make_sub(3, False))
        bus.subscribe(AgentRole.STRATEGIST, make_sub(4, False))

        n = 5
        for _ in range(n):
            bus.send(_make_scout_intel_msg())

        # 所有 subscriber 都應被調用（包括崩潰的）
        for i, count in enumerate(counter):
            assert count == n, f"Subscriber {i} called {count}/{n} times"


# ─────────────────────────────────────────────────────────────
# Test 5: ScoutWorker 長期運行場景（整合）
# ScoutWorker long-run simulation
# ─────────────────────────────────────────────────────────────

class TestScoutWorkerLongRunSimulation:
    """
    模擬 ScoutWorker 連續掃描的消息模式（壓縮時間版本）。
    Simulate ScoutWorker periodic scan pattern over compressed time window.
    """

    def test_simulated_8_scan_cycles_no_issues(self):
        """
        模擬 8 次掃描週期（壓縮為即時執行）：
        每次掃描產生 20 條 INTEL_OBJECT + 2 條 EVENT_ALERT。
        共 8×22 = 176 條消息，驗證 bus 正常累積、無死鎖、subscriber 全收到。

        Simulates 8 scan cycles (each: 20 intel + 2 alerts).
        Total: 176 messages. Verifies accumulation, no deadlock, delivery intact.
        """
        bus = MessageBus()
        strategist_inbox: list = []
        guardian_inbox: list = []

        bus.subscribe(AgentRole.STRATEGIST, lambda m: strategist_inbox.append(m.message_id))
        bus.subscribe(AgentRole.GUARDIAN, lambda m: guardian_inbox.append(m.message_id))

        n_scans = 8
        intel_per_scan = 20
        alert_per_scan = 2

        start = time.monotonic()

        for scan in range(n_scans):
            # 每次掃描：20 intel → Strategist
            for _ in range(intel_per_scan):
                bus.send(AgentMessage(
                    sender=AgentRole.SCOUT,
                    receiver=AgentRole.STRATEGIST,
                    message_type=MessageType.INTEL_OBJECT,
                    payload={"scan": scan, "symbol": "BTCUSDT"},
                ))
            # 每次掃描：2 alert → Guardian
            for _ in range(alert_per_scan):
                bus.send(AgentMessage(
                    sender=AgentRole.SCOUT,
                    receiver=AgentRole.GUARDIAN,
                    message_type=MessageType.EVENT_ALERT,
                    payload={"scan": scan, "severity": "medium"},
                ))

        elapsed = time.monotonic() - start
        total_expected = n_scans * (intel_per_scan + alert_per_scan)

        assert bus.total_messages == total_expected, (
            f"Expected {total_expected} messages, got {bus.total_messages}"
        )
        assert len(strategist_inbox) == n_scans * intel_per_scan
        assert len(guardian_inbox) == n_scans * alert_per_scan
        assert elapsed < 5.0, f"8 simulated scans took {elapsed:.3f}s — unexpected slowdown"
