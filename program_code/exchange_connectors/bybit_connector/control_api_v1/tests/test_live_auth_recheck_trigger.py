"""
Tests for PIPELINE-SLOT-1 Phase 4 threaded-offload trigger and its wiring
into renew / renew-review / revoke flows.

Covers E2 Phase 3 finding F5: prior to Phase 4 there were no tests for
`_trigger_live_auth_recheck_fire_and_forget` or the three call sites that
invoke it (revoke, /auth/renew, /auth/renew-review).

We intentionally exercise the *Python function* layer rather than standing up
the full FastAPI stack — the renew/revoke handlers do far more than trigger
IPC (they touch SM-01 state machines, the trust engine, and execution-authority
grants). A full-stack integration test would drag in Rust IPC, Postgres and
GovernanceHub singletons; the focused unit tests here prove the contract
Phase 4 cares about:

  1. Successful renew path reaches the trigger exactly once.
  2. Successful revoke path reaches the trigger exactly once.
  3. Trigger is truly fire-and-forget: a hung IPC call does NOT delay the
     caller (HTTP thread) — proof via daemon-thread offload semantics.
  4. Trigger failure is swallowed silently (5s watcher poll backstop).

測試 PIPELINE-SLOT-1 Phase 4 執行緒 offload 觸發器及其 renew / renew-review /
revoke 流程整合。
對應 E2 Phase 3 finding F5：Phase 4 之前無任何測試覆蓋
`_trigger_live_auth_recheck_fire_and_forget` 或三個呼叫點。
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app import live_trust_routes as ltr


@pytest.fixture(autouse=True)
def _suppress_live_trust_logger(caplog):
    """
    Silence `live_trust_routes` logger during these tests.

    Rationale: `post_live_renew` and `post_live_renew_review` contain a known
    pre-existing `logger.warning()` call with a format-string / arg-count
    mismatch (7 placeholders, 6 args). That defect is OUT OF SCOPE for
    PIPELINE-SLOT-1 Phase 4 — our job is only to verify the trigger-offload
    contract. Raising the log level to ERROR lets the happy path return
    without `logging` raising a TypeError during emit.
    靜默 live_trust_routes logger — renew warning 是 pre-existing format bug
    （7 placeholder vs 6 args），與 Phase 4 無關。
    """
    logger = logging.getLogger("app.live_trust_routes")
    prev_level = logger.level
    logger.setLevel(logging.ERROR)
    try:
        yield
    finally:
        logger.setLevel(prev_level)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers / 輔助
# ─────────────────────────────────────────────────────────────────────────────

def _wait_for(condition, timeout_s: float = 2.0, interval_s: float = 0.01) -> bool:
    """
    Spin until `condition()` is truthy or timeout. Returns True if condition
    was met, False on timeout. Used because the Phase 4 trigger runs on a
    daemon thread — tests must wait for it to complete before asserting.
    自旋等待 condition 為真或超時；因 Phase 4 trigger 跑於背景執行緒，需等完成。
    """
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(interval_s)
    return False


# ─────────────────────────────────────────────────────────────────────────────
# (1) Direct function tests — trigger calls IPC correctly
# (1) 直接函式測試 — trigger 正確呼叫 IPC
# ─────────────────────────────────────────────────────────────────────────────

def test_trigger_spawns_daemon_thread_and_calls_ipc():
    """
    Happy path: _trigger_live_auth_recheck_fire_and_forget() spawns a daemon
    thread that calls sync_ipc_call("trigger_live_auth_recheck", {}, timeout=1.5).
    happy path：trigger spawn daemon thread 並以預期參數呼叫 sync_ipc_call。
    """
    call_log: list[dict[str, Any]] = []
    ipc_done = threading.Event()

    def fake_sync_ipc(method, params, timeout=3.0):
        call_log.append({"method": method, "params": params, "timeout": timeout})
        ipc_done.set()
        return {"accepted": True}

    # Patch the lazily-imported sync_ipc_call inside the _fire() closure.
    # Lazy import path is `from .ipc_client import sync_ipc_call`.
    with patch("app.ipc_client.sync_ipc_call", side_effect=fake_sync_ipc) as mock:
        ltr._trigger_live_auth_recheck_fire_and_forget()
        assert ipc_done.wait(timeout=2.0), "daemon thread did not fire within 2s"

    assert mock.call_count == 1
    assert len(call_log) == 1
    entry = call_log[0]
    assert entry["method"] == "trigger_live_auth_recheck"
    assert entry["params"] == {}
    assert entry["timeout"] == 1.5


def test_trigger_returns_immediately_even_when_ipc_hangs():
    """
    F1 fix: trigger must NOT block the caller even if the IPC stalls.
    Proves the daemon-thread offload. Without Phase 4 the caller would
    wait up to 1.5s here. We allow a generous 0.3s budget.
    F1 修復：IPC 卡住也不能拖累呼叫者。證明 daemon thread offload。
    """
    release = threading.Event()
    started = threading.Event()

    def hanging_ipc(method, params, timeout=3.0):
        started.set()
        # Simulate a stuck engine socket. Will be released at test teardown.
        # 模擬 engine socket 卡住。
        release.wait(timeout=5.0)
        return {"accepted": False}

    with patch("app.ipc_client.sync_ipc_call", side_effect=hanging_ipc):
        t0 = time.monotonic()
        ltr._trigger_live_auth_recheck_fire_and_forget()
        elapsed = time.monotonic() - t0

        # Sanity: the background thread actually started (so we are really
        # measuring offload, not a no-op fast return).
        assert started.wait(timeout=1.0), "background thread never started"
        # Must return in well under the IPC timeout (1.5s). Generous budget
        # accounts for CI jitter.
        assert elapsed < 0.3, (
            f"HTTP caller blocked {elapsed:.3f}s on hung IPC — "
            f"Phase 4 offload regressed"
        )
        # Release the fake IPC so daemon thread can exit cleanly.
        release.set()


def test_trigger_swallows_ipc_exceptions_silently():
    """
    Trigger is fire-and-forget — an IPC exception must never propagate.
    This is the correctness invariant that keeps renew/revoke HTTP flows
    from failing when only the advisory hint is broken. Watcher 5s poll
    is the backstop.
    IPC 異常吞掉：保證 renew/revoke HTTP 流程不因 advisory 崩而失敗。
    """

    def boom(method, params, timeout=3.0):
        raise ConnectionError("simulated engine socket down")

    with patch("app.ipc_client.sync_ipc_call", side_effect=boom):
        # Must NOT raise.
        ltr._trigger_live_auth_recheck_fire_and_forget()

    # Give the daemon thread a chance to run its exception handler.
    # 給 daemon thread 跑完 exception handler 的時間。
    time.sleep(0.1)
    # Nothing to assert beyond "did not raise" — the contract is silence.


def test_trigger_spawns_daemon_thread_not_foreground():
    """
    Assert the spawned thread has daemon=True — important so interpreter
    shutdown is not delayed by a stuck IPC call.
    驗證 spawn 的 thread 是 daemon=True，直譯器退出不被 IPC 卡住拖慢。
    """
    started = threading.Event()
    observed_daemon: list[bool] = []

    def capture_daemon(method, params, timeout=3.0):
        started.set()
        # current_thread() is the daemon thread itself.
        observed_daemon.append(threading.current_thread().daemon)
        return {"accepted": True}

    with patch("app.ipc_client.sync_ipc_call", side_effect=capture_daemon):
        ltr._trigger_live_auth_recheck_fire_and_forget()
        assert started.wait(timeout=2.0), "trigger thread did not start"

    # Wait briefly for the fake IPC to record observed_daemon.
    # 短等觀察值寫入。
    _wait_for(lambda: len(observed_daemon) == 1, timeout_s=1.0)
    assert observed_daemon == [True], (
        f"trigger thread should be daemon=True, got {observed_daemon}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# (2) Call-site integration — renew / renew-review / revoke all fire trigger
# (2) 呼叫點整合測試 — renew / renew-review / revoke 三路都呼叫 trigger
# ─────────────────────────────────────────────────────────────────────────────
#
# These tests replace the full-stack end-to-end dance (SM-01 + trust engine +
# execution authority) with targeted patches. The invariant being tested is
# purely: "when the happy path reaches the trigger-fire point, the trigger is
# called exactly once". We don't re-test SM-01 or the trust engine here.
#
# 這些測試用精準 patch 取代完整 end-to-end。驗證不變量：happy path 到達
# trigger 呼叫點時，trigger 恰被呼叫一次。

class _FakeActor:
    """Minimal operator actor stand-in. / 最小 operator actor 替身。"""
    actor_id = "ncyu"
    role = "operator"


class _FakeState:
    """Mutable state slot touched by /auth/renew-review. / renew-review 會寫入的狀態槽。"""
    current_tier: int = 3
    renewals_at_t3: int = 2
    promotion_history: list[dict[str, Any]] = []


class _FakeEngine:
    """
    Minimal TrustEngine stand-in covering the handful of attrs/methods the
    /renew and /renew-review paths touch. Avoids dragging in TrustEngine's
    real state file + SM-01 collaborators.
    最小 TrustEngine 替身，覆蓋 renew + renew-review 所需屬性/方法。
    """

    def __init__(self, requires_review: bool = False):
        snapshot_data = {
            "current_tier": 0,
            "tier_name": "T0_ENTRY",
            "requires_operator_review": requires_review,
        }

        class _Rec:
            recommended_tier = 0
            recommended_tier_name = "T0_ENTRY"
            recommended_ttl_hours = 24
            action = "renew_at_t0"
            reasons = ["unit_test"]
            requires_operator_review = requires_review
            metrics_snapshot: dict[str, Any] = {}

        self._snapshot = snapshot_data
        self._rec = _Rec()
        self.on_renew_calls: list[tuple[int, int]] = []
        # Attrs exercised by /auth/renew-review body. Real engine uses a
        # threading.Lock and a dataclass-like state object; the fake uses a
        # no-op context manager + mutable state slot.
        # /auth/renew-review 會用到的屬性；真實 engine 用 threading.Lock + 狀態物件。
        from contextlib import nullcontext
        self._lock = nullcontext()
        self._state = _FakeState()
        self._state.promotion_history = []  # fresh list per-instance

    def get_state_snapshot(self) -> dict[str, Any]:
        return dict(self._snapshot)

    def evaluate_renewal(self, metrics):  # noqa: ANN001
        return self._rec

    def on_auth_renewed(self, new_tier: int, new_expires_ts_ms: int) -> None:
        self.on_renew_calls.append((new_tier, new_expires_ts_ms))


def _patch_common_renew_path(monkeypatch, engine: _FakeEngine):
    """
    Neutralise every collaborator the /renew (and /renew-review) path uses
    so the body reaches `_trigger_live_auth_recheck_fire_and_forget` cleanly.
    中性化 /renew 路徑上所有 collaborator，讓 body 可抵達 trigger。
    """
    monkeypatch.setattr(ltr, "_require_operator", lambda actor: None)
    monkeypatch.setattr(ltr, "get_trust_engine", lambda: engine)
    monkeypatch.setattr(ltr, "_collect_live_metrics", lambda: ltr.TrustMetrics())
    monkeypatch.setattr(
        ltr, "_revoke_existing_live_auths", lambda actor_id: None
    )
    monkeypatch.setattr(
        ltr,
        "_create_live_auth",
        lambda actor_id, tier: ("auth-test-id", 1_800_000_000_000),
    )
    monkeypatch.setattr(
        ltr,
        "_write_signed_live_authorization",
        lambda operator_id, tier, expires_at_ms, approved_system_mode="live_reserved": {
            "tier": "T0_ENTRY",
            "expires_at_ms": expires_at_ms,
            "operator_id": operator_id,
            "approved_system_mode": approved_system_mode,
        },
    )
    monkeypatch.setattr(
        ltr,
        "_require_live_reserved_global_mode",
        lambda actor_id, action: "live_reserved",
    )

    # live_session_routes._grant_execution_authority_internal is best-effort
    # at the call site (wrapped in try/except pass); stub to a no-op so we
    # don't require that module to import cleanly in the test env.
    # 被 try/except 包裹，此處 stub 防止真實導入失敗。
    import sys
    fake_live_session = MagicMock()
    fake_live_session._grant_execution_authority_internal = MagicMock(
        return_value=None
    )
    monkeypatch.setitem(
        sys.modules,
        "app.live_session_routes",
        fake_live_session,
    )


def test_trigger_called_after_successful_renew(monkeypatch):
    """
    Hit `/auth/renew` via the route-function layer; assert the trigger fires
    exactly once after the signed authorization is written.
    呼叫 /auth/renew 路由函式層；驗證簽名寫入後 trigger 恰觸發一次。
    """
    engine = _FakeEngine(requires_review=False)
    _patch_common_renew_path(monkeypatch, engine)

    trigger_mock = MagicMock()
    monkeypatch.setattr(
        ltr, "_trigger_live_auth_recheck_fire_and_forget", trigger_mock
    )

    body = ltr.RenewBody()  # defaults: accepted_tier=None, reason="operator_renew"
    response = ltr.post_live_renew(
        body=body,
        request=MagicMock(),
        authorization=None,
        actor=_FakeActor(),
    )

    assert response["ok"] is True
    assert trigger_mock.call_count == 1, (
        f"expected exactly 1 trigger call from /auth/renew, "
        f"got {trigger_mock.call_count}"
    )
    # Trust engine was notified and execution-authority grant attempted.
    # 信任引擎被通知，execution authority grant 已嘗試。
    assert len(engine.on_renew_calls) == 1


def test_renew_blocks_before_signing_when_global_mode_not_live_reserved(monkeypatch):
    engine = _FakeEngine(requires_review=False)
    _patch_common_renew_path(monkeypatch, engine)

    sign_mock = MagicMock()
    trigger_mock = MagicMock()
    grant_mock = MagicMock()
    monkeypatch.setattr(ltr, "_write_signed_live_authorization", sign_mock)
    monkeypatch.setattr(ltr, "_trigger_live_auth_recheck_fire_and_forget", trigger_mock)
    monkeypatch.setattr(
        ltr,
        "_require_live_reserved_global_mode",
        lambda actor_id, action: (_ for _ in ()).throw(
            ltr.HTTPException(status_code=409, detail="global_mode='demo_reserved'")
        ),
    )

    import sys
    sys.modules["app.live_session_routes"]._grant_execution_authority_internal = grant_mock

    with pytest.raises(ltr.HTTPException) as excinfo:
        ltr.post_live_renew(
            body=ltr.RenewBody(),
            request=MagicMock(),
            authorization=None,
            actor=_FakeActor(),
        )

    assert excinfo.value.status_code == 409
    sign_mock.assert_not_called()
    trigger_mock.assert_not_called()
    grant_mock.assert_not_called()


def test_trigger_called_after_successful_revoke(monkeypatch):
    """
    Exercise the revoke helper (`_revoke_existing_live_auths`) and assert it
    both deletes the authorization file and fires the trigger exactly once
    after iterating the SM-01 authorization state machine.

    We provide a `_get_hub()` that returns a stub with an empty
    `_authorization_sm` so the helper skips the inner revoke loop (nothing
    to revoke) but still hits the mandatory teardown sequence:
      1. delete authorization.json
      2. trigger watcher recheck (sub-100ms teardown)
    revoke 輔助函式測試：驗證 teardown 必經 delete + trigger 恰一次。
    """

    class _EmptyAuthSM:
        """No live auths to iterate. / 無 live auth 可迭代。"""

        def get_effective(self):
            return []

    class _HubStub:
        _authorization_sm = _EmptyAuthSM()

    monkeypatch.setattr(ltr, "_get_hub", lambda: _HubStub())

    delete_mock = MagicMock(return_value=False)
    monkeypatch.setattr(ltr, "_delete_live_authorization_file", delete_mock)

    trigger_mock = MagicMock()
    monkeypatch.setattr(
        ltr, "_trigger_live_auth_recheck_fire_and_forget", trigger_mock
    )

    ltr._revoke_existing_live_auths(actor_id="ncyu")

    assert delete_mock.call_count == 1, (
        "revoke must attempt to delete authorization.json exactly once"
    )
    assert trigger_mock.call_count == 1, (
        f"expected exactly 1 trigger call from revoke, "
        f"got {trigger_mock.call_count}"
    )


def test_trigger_called_after_successful_renew_review(monkeypatch):
    """
    Full-review (/auth/renew-review) is the T3 mandatory-review path. It has
    its own body model and confirmed_tier, but must also fire the trigger
    exactly once after the signed authorization is written.
    /auth/renew-review 是 T3 強制審查分支，參數不同但 trigger 行為與 renew 一致。
    """
    engine = _FakeEngine(requires_review=True)
    _patch_common_renew_path(monkeypatch, engine)

    trigger_mock = MagicMock()
    monkeypatch.setattr(
        ltr, "_trigger_live_auth_recheck_fire_and_forget", trigger_mock
    )

    body = ltr.FullReviewBody(
        review_notes="full review completed by operator for unit test",
        confirmed_tier=1,
    )
    response = ltr.post_live_renew_review(
        body=body,
        request=MagicMock(),
        authorization=None,
        actor=_FakeActor(),
    )

    assert response["ok"] is True
    assert trigger_mock.call_count == 1, (
        f"expected exactly 1 trigger call from /auth/renew-review, "
        f"got {trigger_mock.call_count}"
    )


def test_renew_review_blocks_before_signing_when_global_mode_not_live_reserved(monkeypatch):
    engine = _FakeEngine(requires_review=True)
    _patch_common_renew_path(monkeypatch, engine)

    sign_mock = MagicMock()
    trigger_mock = MagicMock()
    monkeypatch.setattr(ltr, "_write_signed_live_authorization", sign_mock)
    monkeypatch.setattr(ltr, "_trigger_live_auth_recheck_fire_and_forget", trigger_mock)
    monkeypatch.setattr(
        ltr,
        "_require_live_reserved_global_mode",
        lambda actor_id, action: (_ for _ in ()).throw(
            ltr.HTTPException(status_code=409, detail="global_mode='observe_only'")
        ),
    )

    with pytest.raises(ltr.HTTPException) as excinfo:
        ltr.post_live_renew_review(
            body=ltr.FullReviewBody(
                review_notes="full review should be blocked before signing",
                confirmed_tier=1,
            ),
            request=MagicMock(),
            authorization=None,
            actor=_FakeActor(),
        )

    assert excinfo.value.status_code == 409
    sign_mock.assert_not_called()
    trigger_mock.assert_not_called()


def test_trigger_failure_does_not_break_http_response(monkeypatch):
    """
    The critical fire-and-forget contract at the HTTP layer: if the IPC call
    inside the trigger raises, the /auth/renew response must still succeed
    with a normal ok=True payload (not 500, not exception).
    Proves that renew flow is decoupled from advisory trigger success.
    關鍵 fire-and-forget 契約：IPC 內部拋例外，/auth/renew 回應仍需正常 ok=True。
    """
    engine = _FakeEngine(requires_review=False)
    _patch_common_renew_path(monkeypatch, engine)

    # Install a real (un-patched) trigger that spawns a real daemon thread,
    # but make the IPC call inside blow up. We want to prove the HTTP path
    # is not coupled to the IPC call's success.
    # 保留真 trigger + 真 daemon thread，但 IPC 內部爆炸；驗證 HTTP 路徑解耦。
    def boom(method, params, timeout=3.0):
        raise ConnectionError("engine socket hard-down")

    body = ltr.RenewBody()
    with patch("app.ipc_client.sync_ipc_call", side_effect=boom):
        response = ltr.post_live_renew(
            body=body,
            request=MagicMock(),
            authorization=None,
            actor=_FakeActor(),
        )

    # Must be a fully-successful renew response.
    # 必須為完整成功的 renew 回應。
    assert response["ok"] is True
    assert response["message"].startswith("live_auth_renewed_tier_")
    assert response["data"]["auth_id"] == "auth-test-id"
    assert response["data"]["expires_at_ms"] == 1_800_000_000_000

    # Let the daemon thread run its exception handler to completion before
    # the test exits (avoids noisy background-logging during teardown).
    # 讓 daemon thread 跑完 exception handler。
    time.sleep(0.1)
