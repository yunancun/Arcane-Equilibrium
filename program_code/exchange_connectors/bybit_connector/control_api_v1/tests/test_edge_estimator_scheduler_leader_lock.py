"""
EDGE-SCHEDULER-LEADER-1 — tests for per-host leader election via fcntl.flock.
EDGE-SCHEDULER-LEADER-1 — fcntl.flock 單機 leader 選舉測試。

Covers:
  1. First call in a process wins the lock → becomes leader
  2. OPENCLAW_SCHEDULER_LEADER=0 force-opts out → non-leader
  3. start_scheduler() returns None when non-leader (no instance, no thread)
  4. start_scheduler() returns instance when leader
  5. Idempotency — second call within same process is a no-op (stays leader)
  6. Sentinel file contains the leader PID (operator-debuggable)
  7. Multi-process election — a subprocess holding the lock forces this
     process to non-leader (the canonical uvicorn-workers scenario)
"""

from __future__ import annotations

import fcntl
import multiprocessing
import os
import sys
import time
from pathlib import Path
from typing import Optional

import pytest


# ───── PATH SETUP / 路徑設置 ─────────────────────────────────────────────────
_THIS_DIR = Path(__file__).resolve().parent
_CONTROL_API = _THIS_DIR.parent
_BYBIT_CONNECTOR = _CONTROL_API.parent
_EXCHANGE_CONNECTORS = _BYBIT_CONNECTOR.parent
_PROGRAM_CODE = _EXCHANGE_CONNECTORS.parent
_SRV_ROOT = _PROGRAM_CODE.parent
for _p in (str(_CONTROL_API), str(_SRV_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)


# ───── FIXTURES / 夾具 ───────────────────────────────────────────────────────

@pytest.fixture
def isolated_data_dir(tmp_path, monkeypatch):
    """
    Isolate OPENCLAW_DATA_DIR per test so flock files don't bleed.
    每測試獨立 OPENCLAW_DATA_DIR，避免 flock 檔案跨測試污染。
    """
    data_dir = tmp_path / "openclaw_rt"
    data_dir.mkdir()
    monkeypatch.setenv("OPENCLAW_DATA_DIR", str(data_dir))
    # Clear any leader-lock opt-out leaked from parent env.
    # 清除父環境可能帶入的 leader-lock opt-out。
    monkeypatch.delenv("OPENCLAW_SCHEDULER_LEADER", raising=False)
    yield data_dir


@pytest.fixture
def scheduler_module(isolated_data_dir):
    """
    Fresh scheduler module state per test — release any held flock fd
    and null out the singleton + path cache.
    每測試重置 scheduler 模組狀態 — 釋放 flock fd，清除單例 + path cache。
    """
    from program_code.exchange_connectors.bybit_connector.control_api_v1.app import (
        edge_estimator_scheduler as mod,
    )
    mod._reset_for_tests()
    yield mod
    mod._reset_for_tests()


# ───── TESTS / 測試 ──────────────────────────────────────────────────────────

def test_acquire_leader_lock_first_call_wins(scheduler_module, isolated_data_dir):
    """
    First call in a fresh process acquires the lock → leader.
    新進程內首次呼叫取得鎖 → 成為 leader。
    """
    assert scheduler_module._acquire_leader_lock() is True
    assert scheduler_module._LEADER_LOCK_FD is not None

    lock_file = isolated_data_dir / "edge_scheduler.leader.lock"
    assert lock_file.exists(), "sentinel file should be created on leader election"

    # Sentinel content should be current PID for operator debuggability.
    # sentinel 檔應寫 current PID 便於 operator debug。
    content = lock_file.read_text().strip()
    assert content == str(os.getpid()), (
        f"lock file should contain leader PID {os.getpid()}, got '{content}'"
    )


def test_acquire_leader_lock_idempotent_same_process(scheduler_module):
    """
    Second call in the same process stays leader without re-flocking.
    同進程內再次呼叫維持 leader 狀態，不重新 flock。
    """
    assert scheduler_module._acquire_leader_lock() is True
    first_fd = scheduler_module._LEADER_LOCK_FD
    assert first_fd is not None

    # Second call — should return True without touching the fd.
    # 第二次呼叫回 True 且 fd 不變。
    assert scheduler_module._acquire_leader_lock() is True
    assert scheduler_module._LEADER_LOCK_FD is first_fd, (
        "idempotent re-call must not allocate a new fd"
    )


def test_env_force_non_leader(scheduler_module, monkeypatch):
    """
    OPENCLAW_SCHEDULER_LEADER=0 → forced non-leader; no flock attempted.
    OPENCLAW_SCHEDULER_LEADER=0 → 強制非 leader，不嘗試 flock。
    """
    monkeypatch.setenv("OPENCLAW_SCHEDULER_LEADER", "0")
    assert scheduler_module._acquire_leader_lock() is False
    assert scheduler_module._LEADER_LOCK_FD is None


def test_start_scheduler_leader_returns_instance(scheduler_module):
    """
    Leader worker: start_scheduler() returns the scheduler instance.
    Leader worker：start_scheduler() 回傳 scheduler 實例。
    """
    sched = scheduler_module.start_scheduler(
        modes=("demo",),
        interval_s=3600.0,
        days_back=7,
    )
    assert sched is not None
    assert isinstance(sched, scheduler_module.EdgeEstimatorScheduler)
    # get_scheduler() mirrors start return for leader path
    # get_scheduler() 對 leader path 應回同實例。
    assert scheduler_module.get_scheduler() is sched


def test_start_scheduler_non_leader_returns_none(scheduler_module, monkeypatch):
    """
    Non-leader worker: start_scheduler() returns None; no NEW thread spawned.
    非 leader worker：start_scheduler() 回 None，不新增 thread。

    We count scheduler-named threads before + after the call rather than
    asserting zero, because a sibling test in the same pytest session may
    have spawned a leader daemon thread that outlives its fixture (daemon
    threads only exit on process shutdown — we can't cleanly stop the
    `while True:` loop without adding a shutdown primitive, out of scope
    for this TODO).
    用前後計數而非絕對 0 斷言，因為同 pytest session 內其他測試可能已啟
    leader daemon thread（daemon 只在進程退出才結束；無阻塞式 shutdown
    primitive，超出本 TODO 範圍）。
    """
    import threading
    monkeypatch.setenv("OPENCLAW_SCHEDULER_LEADER", "0")
    before = sum(1 for t in threading.enumerate() if t.name == "edge-estimator-scheduler")

    sched = scheduler_module.start_scheduler(
        modes=("demo",),
        interval_s=3600.0,
        days_back=7,
    )
    assert sched is None
    assert scheduler_module.get_scheduler() is None

    # Give any rogue thread creation a brief window to show up.
    # 稍等避免 race 判讀。
    time.sleep(0.05)
    after = sum(1 for t in threading.enumerate() if t.name == "edge-estimator-scheduler")
    assert after == before, (
        f"non-leader must not spawn a new scheduler daemon thread "
        f"(before={before}, after={after})"
    )


# ───── MULTI-PROCESS ELECTION ────────────────────────────────────────────────

def _child_hold_lock(lock_path: str, ready_evt, release_evt) -> None:
    """
    Child process: acquire flock on `lock_path`, signal ready, hold until told.
    子進程：flock 鎖住 lock_path，發 ready 信號後等待釋放指令。
    """
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o644)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    os.ftruncate(fd, 0)
    os.write(fd, f"{os.getpid()}\n".encode("utf-8"))
    ready_evt.set()
    release_evt.wait(timeout=30.0)
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        pass
    os.close(fd)


def test_multiprocess_election_second_worker_is_non_leader(
    scheduler_module, isolated_data_dir,
):
    """
    Canonical uvicorn --workers scenario: a separate process holds the lock,
    THIS process attempts election, gets EWOULDBLOCK → non-leader.
    標準 uvicorn --workers 場景：另一進程持鎖，本進程嘗試選舉收到
    EWOULDBLOCK → 非 leader。
    """
    lock_path = str(isolated_data_dir / "edge_scheduler.leader.lock")
    ctx = multiprocessing.get_context("fork" if sys.platform != "win32" else "spawn")
    ready_evt = ctx.Event()
    release_evt = ctx.Event()
    proc = ctx.Process(
        target=_child_hold_lock,
        args=(lock_path, ready_evt, release_evt),
        name="edge-sched-lock-holder",
    )
    proc.start()
    try:
        assert ready_evt.wait(timeout=10.0), "child failed to acquire lock in time"
        # Child holds the lock — this process must lose election.
        # 子進程已持鎖，本進程選舉必敗。
        assert scheduler_module._acquire_leader_lock() is False
        assert scheduler_module._LEADER_LOCK_FD is None

        # And start_scheduler() must return None accordingly.
        # 因此 start_scheduler() 也要回 None。
        scheduler_module._reset_for_tests()  # clear any side-effect
        sched = scheduler_module.start_scheduler(
            modes=("demo",),
            interval_s=3600.0,
            days_back=7,
        )
        assert sched is None
    finally:
        release_evt.set()
        proc.join(timeout=5.0)
        if proc.is_alive():
            proc.terminate()
            proc.join(timeout=2.0)


def test_multiprocess_election_reclaim_after_leader_exits(
    scheduler_module, isolated_data_dir,
):
    """
    Leader crash/exit → OS releases flock → next process can re-elect.
    Leader crash/exit → OS 釋放 flock → 下一進程可重新選舉。

    This exercises the crash-recovery path: simulated by a short-lived
    child that grabs then releases the lock, after which THIS process
    should win election.
    模擬 crash-recovery：短暫子進程抓鎖後釋放，本進程接著選舉應勝。
    """
    lock_path = str(isolated_data_dir / "edge_scheduler.leader.lock")
    ctx = multiprocessing.get_context("fork" if sys.platform != "win32" else "spawn")
    ready_evt = ctx.Event()
    release_evt = ctx.Event()
    proc = ctx.Process(
        target=_child_hold_lock,
        args=(lock_path, ready_evt, release_evt),
    )
    proc.start()
    assert ready_evt.wait(timeout=10.0)

    # Tell child to release + exit; wait for process to fully terminate so
    # the OS has released the flock before we retry.
    # 通知子進程釋放 + 退出，等進程完全結束以確保 OS 已釋放 flock。
    release_evt.set()
    proc.join(timeout=10.0)
    assert not proc.is_alive(), "child must have exited before re-election"

    # Fresh election in this process should now succeed.
    # 本進程現應成功當選。
    scheduler_module._reset_for_tests()
    assert scheduler_module._acquire_leader_lock() is True
    assert scheduler_module._LEADER_LOCK_FD is not None


# ───── E4-3 EDGE CASES / 邊界測試（audit finding 補測） ─────────────────────────
#
# Rationale / 理由：
#   E4-3 audit 指出 _acquire_leader_lock() 有 3 條 fallback path 與 1 條
#   _reset_for_tests 冪等性無測試覆蓋：
#     (a) mkdir parent 失敗（permission / read-only fs）
#     (b) os.open 失敗（fd 耗盡 / path 非法）
#     (c) OPENCLAW_SCHEDULER_LEADER 非 "0" 非法值（任何非 "0" 都應走 flock）
#     (d) _reset_for_tests 連續呼叫（冪等）
#   補此四 test 覆蓋 E4-3 列舉的 primitive-level 邊界；
#   shutdown primitive（daemon thread 可中止）明確**不在**本 commit 範圍
#   （scope creep，operator 延後）。


def test_acquire_leader_lock_mkdir_fail_returns_non_leader(
    scheduler_module, isolated_data_dir, monkeypatch,
):
    """
    mkdir parent 目錄失敗（OSError）→ _acquire_leader_lock() 回 False，fd 未設。
    Parent dir mkdir raises OSError → return False; no fd stashed.

    E4-3 (a)：read-only FS / permission denied / ENOSPC 等情境下，scheduler
    應 fail-open 降級為非 leader（warning log），而非拋出未捕獲異常使整個
    uvicorn worker 啟動失敗。
    E4-3 (a)：唯讀檔案系統 / 權限不足 / 空間滿等情境下，scheduler 應 fail-open
    降級為非 leader（warning），不應拋出未捕獲異常中斷 uvicorn worker 啟動。
    """
    # Patch Path.mkdir to always raise OSError (regardless of exist_ok).
    # 所有 Path.mkdir 呼叫一律拋 OSError 模擬 permission denied。
    def _boom_mkdir(self, *args, **kwargs):
        raise OSError("permission denied (simulated)")

    monkeypatch.setattr(Path, "mkdir", _boom_mkdir)

    assert scheduler_module._acquire_leader_lock() is False, (
        "mkdir OSError must fail-open as non-leader, not raise"
    )
    assert scheduler_module._LEADER_LOCK_FD is None, (
        "fd must not be stashed when mkdir failed"
    )


def test_acquire_leader_lock_open_fail_returns_non_leader(
    scheduler_module, isolated_data_dir, monkeypatch,
):
    """
    os.open 失敗（OSError）→ _acquire_leader_lock() 回 False，fd 未設。
    os.open raises OSError → return False; no fd stashed.

    E4-3 (b)：fd table 耗盡 (EMFILE) / path 非法 / SELinux 拒絕等情境下，
    scheduler 降級為非 leader，不影響其他進程競選。注意：parent mkdir 必須
    成功（不 patch），才能測到 os.open 這條 path。
    E4-3 (b)：fd 表滿 / path 非法 / SELinux 拒絕等情境下，scheduler 降級為
    非 leader，不阻斷其他進程競選。注意：不 patch mkdir 確保先通過 parent
    建立階段，才測到 os.open 這條 path。
    """
    real_open = os.open

    def _boom_open(path, flags, mode=0o777, *args, **kwargs):
        # Only poison the leader lock path; let other os.open calls
        # (e.g. pytest internals) pass through to the real os.open.
        # 只污染 leader lock 檔案路徑；pytest 內部其他 os.open 仍走原實作。
        if "edge_scheduler.leader.lock" in str(path):
            raise OSError("no fd available (simulated EMFILE)")
        return real_open(path, flags, mode, *args, **kwargs)

    monkeypatch.setattr(os, "open", _boom_open)

    assert scheduler_module._acquire_leader_lock() is False, (
        "os.open OSError must fail-open as non-leader, not raise"
    )
    assert scheduler_module._LEADER_LOCK_FD is None, (
        "fd must not be stashed when os.open failed"
    )


@pytest.mark.parametrize(
    "env_value",
    ["", "1", "true", "yes"],
    ids=["empty_string", "one", "true_literal", "yes_literal"],
)
def test_env_non_zero_values_still_attempt_flock(
    scheduler_module, isolated_data_dir, monkeypatch, env_value,
):
    """
    OPENCLAW_SCHEDULER_LEADER 非 "0" 值（空串/"1"/"true"/"yes"）→ 仍走 flock path
    →（單測進程無競爭）應當選 leader。
    OPENCLAW_SCHEDULER_LEADER set to any non-"0" value still runs flock path
    and (in a contention-free test) acquires the lock.

    E4-3 (c)：opt-out 機制設計意圖是「唯 '0' 關閉」，其他任何值都不該誤判為
    強制非 leader。這防止 operator 誤設 `OPENCLAW_SCHEDULER_LEADER=1`（期待
    「強制當 leader」）卻意外觸發 opt-out 的反直覺陷阱 — 實際語意：只認 "0"
    為 opt-out signal，其他值一律忽略 env 照常競選。
    E4-3 (c)：opt-out 設計語意為「僅 '0' 生效」，其他值（含 '1'/'true'/'yes'/空串）
    皆應被忽略照常參與選舉。避免 operator 誤設 `=1` 期待「強制 leader」卻反被
    opt-out 的反直覺行為。實際語意：唯 "0" 字面值為 opt-out signal。
    """
    monkeypatch.setenv("OPENCLAW_SCHEDULER_LEADER", env_value)

    # In this isolated test process there's no competing flock holder, so the
    # non-"0" path should end up electing THIS process leader.
    # 測試進程隔離無競爭 flock holder，非 "0" 值應順利 flock 成功當選 leader。
    assert scheduler_module._acquire_leader_lock() is True, (
        f"env value {env_value!r} must NOT be treated as opt-out; "
        f"only the literal '0' disables leader election"
    )
    assert scheduler_module._LEADER_LOCK_FD is not None, (
        f"fd must be stashed when env={env_value!r} (non-opt-out path)"
    )


def test_reset_for_tests_is_idempotent(scheduler_module):
    """
    _reset_for_tests() 連續呼叫多次不應 raise（冪等性）。
    _reset_for_tests() must be idempotent — repeated calls don't raise.

    E4-3 (d)：pytest fixture teardown + setup 順序下 _reset_for_tests 可能在
    同一進程被重複呼叫（fixture yield 後 teardown、下一 test setup 再呼）。
    第 2+ 次呼叫時 _LEADER_LOCK_FD 已為 None，flock/close 的 guard 必須保
    「None 狀態下 no-op」的契約，不應拋 TypeError/AttributeError。
    E4-3 (d)：pytest fixture teardown/setup 順序可能讓 _reset_for_tests 於同一
    進程重複呼叫。第 2+ 次呼叫時 _LEADER_LOCK_FD 已為 None，flock/close guard
    須維持 no-op 契約，不得拋 TypeError/AttributeError。
    """
    # First call — may or may not have state to release depending on what
    # earlier fixtures did; should always succeed.
    # 第一次：可能有可能沒 leader state，皆應成功。
    scheduler_module._reset_for_tests()
    assert scheduler_module._LEADER_LOCK_FD is None
    assert scheduler_module._scheduler is None

    # Second call immediately — fd is already None, must no-op cleanly.
    # 第二次立即呼叫：fd 已為 None，必須乾淨 no-op。
    scheduler_module._reset_for_tests()
    assert scheduler_module._LEADER_LOCK_FD is None
    assert scheduler_module._scheduler is None

    # Third call — still idempotent.
    # 第三次：仍冪等。
    scheduler_module._reset_for_tests()
    assert scheduler_module._LEADER_LOCK_FD is None
    assert scheduler_module._scheduler is None

    # After acquiring then reset-reset, still clean.
    # 取得 leader 後連續 reset 兩次，狀態仍乾淨。
    assert scheduler_module._acquire_leader_lock() is True
    assert scheduler_module._LEADER_LOCK_FD is not None
    scheduler_module._reset_for_tests()
    assert scheduler_module._LEADER_LOCK_FD is None
    scheduler_module._reset_for_tests()  # second reset — must no-op
    assert scheduler_module._LEADER_LOCK_FD is None


# ───── SCHEDULER-SHUTDOWN-PRIMITIVE-1 / shutdown 原語測試 ────────────────────
#
# Rationale / 理由：
#   Prior to SHUTDOWN-PRIMITIVE-1 (2026-04-23), EdgeEstimatorScheduler._loop
#   was `while True:` with no stop_event. `_reset_for_tests()` cleared the
#   singleton but could not join the daemon thread — pytest sessions leaked
#   5+ scheduler daemons. The leader_returns_none test above used a
#   before/after thread-count workaround instead of absolute zero.
#
#   This commit adds an Event-based shutdown + `shutdown(join_timeout)` method
#   + `_reset_for_tests()` now calls `shutdown()` before clearing. Three new
#   tests exercise the happy path, idempotency, and the _reset_for_tests()
#   integration.
#
#   2026-04-23 以前 `_loop` 為 `while True:` 無 stop_event，`_reset_for_tests()`
#   不 join daemon thread → pytest session 累積 5+ 條 daemon。本 commit 新增
#   Event-based shutdown + `shutdown(join_timeout)` + `_reset_for_tests` 改
#   呼 shutdown；以下 3 test 驗 happy path、冪等性、與 reset 整合。


def test_shutdown_exits_cleanly_when_thread_idle(scheduler_module):
    """
    Scheduler started → short delay → shutdown() → returns True + thread dead.
    啟動 scheduler → 短暫延遲 → shutdown() → 回 True 且 thread 已退出。

    Happy path：warm-up 期間被 stop_event 打斷，thread 乾淨退出。
    """
    import threading as _threading
    sched = scheduler_module.start_scheduler(
        modes=("demo",),
        interval_s=3600.0,
        days_back=7,
    )
    assert sched is not None

    # Let the thread actually enter the warm-up wait before we signal stop.
    # 稍等確保 thread 已進入 warm-up wait，再發 stop 訊號。
    time.sleep(0.1)
    thread = sched._thread
    assert thread is not None and thread.is_alive(), "daemon should be running pre-shutdown"

    clean = sched.shutdown(join_timeout=5.0)
    assert clean is True, "shutdown must return True on clean exit"
    assert not thread.is_alive(), "daemon thread must be dead after shutdown"

    # Ensure the name is no longer in threading.enumerate() (absolute check).
    # 絕對檢查：threading.enumerate() 不再包含 scheduler thread。
    remaining = [t for t in _threading.enumerate()
                 if t.name == "edge-estimator-scheduler" and t.is_alive()]
    assert remaining == [], (
        f"no live edge-estimator-scheduler thread should remain, got {remaining}"
    )


def test_shutdown_idempotent(scheduler_module):
    """
    Consecutive shutdown() calls both return True; the second returns
    immediately without blocking on join.
    連呼兩次 shutdown() 都回 True，第二次立即回（不 join 已退出的 thread）。
    """
    sched = scheduler_module.start_scheduler(
        modes=("demo",),
        interval_s=3600.0,
        days_back=7,
    )
    assert sched is not None
    time.sleep(0.1)

    first = sched.shutdown(join_timeout=5.0)
    assert first is True, "first shutdown must succeed"

    # Second call: thread already dead, must return True immediately.
    # 第二次：thread 已死，應立即回 True。
    t0 = time.time()
    second = sched.shutdown(join_timeout=5.0)
    elapsed = time.time() - t0
    assert second is True, "second shutdown must also return True (idempotent)"
    assert elapsed < 0.5, (
        f"second shutdown should be near-instant (thread already dead), "
        f"got elapsed={elapsed:.3f}s"
    )


def test_reset_for_tests_cleanly_joins_thread(scheduler_module):
    """
    _reset_for_tests() now calls shutdown() before clearing the singleton
    → no scheduler daemon thread leaks into subsequent tests.
    _reset_for_tests() 清單例前呼 shutdown()，daemon thread 不再洩漏到後續 test。

    This is the core SHUTDOWN-PRIMITIVE-1 contract the test-count workaround
    in `test_start_scheduler_non_leader_returns_none` was working around.
    此為 SHUTDOWN-PRIMITIVE-1 核心契約，解除 `test_start_scheduler_non_leader_returns_none`
    內 before/after thread 計數 workaround 的需要。
    """
    import threading as _threading
    sched = scheduler_module.start_scheduler(
        modes=("demo",),
        interval_s=3600.0,
        days_back=7,
    )
    assert sched is not None
    time.sleep(0.1)
    assert sched._thread is not None and sched._thread.is_alive()

    # _reset_for_tests() should shutdown + join before nulling the singleton.
    # _reset_for_tests() 應先 shutdown + join 再清單例。
    scheduler_module._reset_for_tests()

    # Absolute-zero assertion: no live edge-estimator-scheduler thread remains.
    # 絕對 0 斷言：無存活 edge-estimator-scheduler thread。
    live_sched_threads = [
        t for t in _threading.enumerate()
        if t.name == "edge-estimator-scheduler" and t.is_alive()
    ]
    assert live_sched_threads == [], (
        f"_reset_for_tests must join the daemon thread, but "
        f"{len(live_sched_threads)} still alive: {live_sched_threads}"
    )
    assert scheduler_module._scheduler is None, "singleton must be cleared"
