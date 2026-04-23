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
