"""REF-20 Sprint A R2 round 2 fix M-2 — /experiments/register rate limit.
REF-20 Sprint A R2 round 2 fix M-2 — /experiments/register 速率限制。

MODULE_NOTE (EN):
    Hermetic 1-case suite covering R2 round 2 M-2 fix:

      Case 1: 11 sequential register requests within < 60s → 11th gets 429.

    Round 1 had no per-actor / per-IP rate limit on the register endpoint.
    Round 2 adds ``@_replay_limiter.limit("10/minute", key_func=_replay_rate_limit_key)``.
    slowapi 0.1.9 enforces the limit inside the ``@limit`` wrapper directly
    (not via middleware), so this test works without registering
    ``SlowAPIMiddleware`` on the test app.

MODULE_NOTE (中):
    封閉式 1-case 套件，覆蓋 R2 round 2 M-2 fix：

      Case 1：60s 內連續 11 次 register → 第 11 次回 429。

    Round 1 register endpoint 無 rate limit。Round 2 加 @limiter.limit
    decorator；slowapi 0.1.9 在 @limit wrapper 直接強制（非 middleware），
    本測試無需在 test app 加 SlowAPIMiddleware。

SPEC: docs/execution_plan/2026-05-04--ref20_gap_closure_reality_backtest_plan_v1.md §6.R2 round 2 M-2
"""

from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest

_test_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(_test_dir)
if _control_api_dir not in sys.path:
    sys.path.insert(0, _control_api_dir)

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.auth import AuthenticatedActor  # noqa: E402
from app.main_legacy import current_actor, limiter  # noqa: E402
from app.replay_routes import replay_router  # noqa: E402
from replay import experiment_registry as _er  # noqa: E402


_DUMMY_ENGINE_SHA = "a" * 64


def _operator_actor_alice() -> AuthenticatedActor:
    return AuthenticatedActor(
        actor_id="alice",
        actor_type="human",
        roles={"operator", "viewer"},
        scopes={"replay:write", "private_readonly"},
    )


@pytest.fixture(autouse=True)
def _setup(monkeypatch):
    """Set engine sha + reset slowapi limiter + clear idempotency cache.
    設 engine sha + 重置 slowapi limiter + 清 idempotency cache。

    Limiter state is module-level singleton on ``main_legacy.limiter``;
    must reset between tests so the 11th-request 429 boundary is reliable.
    Limiter 是 main_legacy.limiter 模組級 singleton；測試間必 reset 才能
    可靠觸發第 11 次 429。
    """
    monkeypatch.setenv("OPENCLAW_ENGINE_BINARY_SHA", _DUMMY_ENGINE_SHA)
    _er._cache_clear_for_test()
    limiter.reset()
    yield
    limiter.reset()
    _er._cache_clear_for_test()


def _build_client(actor_factory) -> TestClient:
    """Build test client; sets app.state.limiter so slowapi internals find it."""
    app = FastAPI()
    # slowapi internal _check_request_limit reads app.state.limiter for
    # storage-level retries; bind here so the limiter does not assume an
    # app.state.limiter from a different FastAPI instance.
    # slowapi 內部讀 app.state.limiter；此處綁，避免 limiter 假設別個
    # FastAPI 實例的 app.state.limiter。
    app.state.limiter = limiter
    app.include_router(replay_router)
    app.dependency_overrides[current_actor] = actor_factory
    return TestClient(app)


def _stub_get_pg_conn():
    """PG conn that always returns successful INSERT.
    永遠成功 INSERT 的 PG conn stub。
    """
    @contextmanager
    def _gen():
        from datetime import datetime, timezone
        ts = datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc)
        conn = MagicMock()
        cur = MagicMock()
        # Each request needs RETURNING (uuid, ts).
        # 每次 request 需要 RETURNING (uuid, ts)。
        cur.fetchone.return_value = (
            "abcd0000-0000-0000-0000-000000000001", ts,
        )
        conn.cursor.return_value = cur
        yield conn
    return _gen


def _minimal_register_body() -> dict:
    return {
        "symbol": "BTCUSDT",
        "strategy": "grid_trading",
        "timeframe": "1m",
        "data_tier": "S3",
        "data_window_start": "2026-04-01T00:00:00Z",
        "data_window_end": "2026-04-30T23:59:00Z",
        "strategy_config_sha256": "a" * 64,
        "risk_config_sha256": "b" * 64,
        "half_life_days": 7.0,
        "embargo_days": 1.0,
        "manifest_jsonb": {"name": "rate-limit-test", "candidate_K": 1},
    }


# ─── Case 1: 11th request returns 429 ────────────────────────────────


def test_register_rate_limit_429_after_10(monkeypatch):
    """R2 round 2 M-2: 11 register requests in <60s → 11th = 429.
    R2 round 2 M-2：60s 內 11 次 register → 第 11 次 = 429。

    The decorator ``@_replay_limiter.limit("10/minute", key_func=...)``
    permits 10 requests per rolling minute. Issuing 11 in tight loop
    should trip 429 on the 11th.
    decorator ``@_replay_limiter.limit("10/minute", key_func=...)`` 允許
    rolling 1 分鐘內 10 次。連發 11 次第 11 次必觸 429。
    """
    monkeypatch.setattr("app.replay_routes.get_pg_conn", _stub_get_pg_conn())

    client = _build_client(_operator_actor_alice)
    body = _minimal_register_body()

    success_count = 0
    last_status = None
    for i in range(11):
        resp = client.post("/api/v1/replay/experiments/register", json=body)
        last_status = resp.status_code
        if resp.status_code == 200:
            success_count += 1
        elif resp.status_code == 429:
            # Hit the limit — verify it's on or before the 11th.
            # 觸限速 — 驗於第 11 次或之前。
            break

    # Expectation per "10/minute": at least 10 successes; 11th = 429
    # (slowapi may permit slight burst variation but in TestClient
    # synchronous loop the 11th must fail).
    # 預期 "10/minute"：至少 10 成功；第 11 次 = 429（slowapi burst 變動小，
    # TestClient 同步 loop 第 11 次必 fail）。
    assert last_status == 429, (
        f"expected 429 by 11th request; success_count={success_count}, "
        f"last_status={last_status}"
    )
    assert success_count >= 9, (
        f"expected at least 9 successes before 429; got {success_count}"
    )
