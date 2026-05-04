"""REF-20 Sprint A R2 round 2 fix H-3 — /report cross-route consistency smoke.
REF-20 Sprint A R2 round 2 fix H-3 — /report 跨 route 一致性 smoke。

MODULE_NOTE (EN):
    Hermetic 3-case suite covering R2 round 2 H-3 fix:

      Case 1: register → report (registered) — /report uses real V049
              experiment_id (no UUID5 derivation).
      Case 2: report on unregistered experiment_id → 404 + reason.
      Case 3: report shape validation — invalid chars → 400.

    Round 1 ``/report`` derived ``manifest_uuid`` via UUID5 from the
    experiment_id text and SELECT-d V046.report_artifacts WHERE
    manifest_id = derived. After R2-T2 ``run_state.manifest_id`` is the
    REAL V049 experiment_id, so derived UUID never matched any V045
    row — ``/report`` was permanently 0-row for any experiment registered
    post-R2-T2. Round 2 H-3 makes ``/report`` use the SAME helper as
    ``/run`` (route_helpers.lookup_registered_experiment_id) for V049
    text → real UUID resolution.

MODULE_NOTE (中):
    封閉式 3-case 套件，覆蓋 R2 round 2 H-3 fix：

      Case 1：register → report（已註冊）— /report 用真 V049 experiment_id（無 UUID5 衍生）。
      Case 2：對未註冊 experiment_id /report → 404。
      Case 3：shape 驗證：非法字 → 400。

    Round 1 ``/report`` 由 experiment_id text UUID5 衍生 manifest_uuid
    然後 SELECT V046；R2-T2 後 ``run_state.manifest_id`` 已是真 V049
    experiment_id，derived ≠ real → ``/report`` 對 R2-T2 後註冊的
    experiment 永遠 0 row。Round 2 H-3 讓 ``/report`` 與 ``/run`` 共用
    同 helper（route_helpers.lookup_registered_experiment_id）。

SPEC: docs/execution_plan/2026-05-04--ref20_gap_closure_reality_backtest_plan_v1.md §6.R2 round 2 H-3
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
from app.main_legacy import current_actor  # noqa: E402
from app.replay_routes import replay_router  # noqa: E402


# ─── Test actor / 測試 actor ───────────────────────────────────────────


def _operator_actor_alice() -> AuthenticatedActor:
    return AuthenticatedActor(
        actor_id="alice",
        actor_type="human",
        roles={"operator", "viewer"},
        scopes={"replay:write", "private_readonly"},
    )


def _build_client(actor_factory) -> TestClient:
    app = FastAPI()
    app.include_router(replay_router)
    app.dependency_overrides[current_actor] = actor_factory
    return TestClient(app)


# ─── PG conn stub builders / PG conn stub builder ──────────────────────


def _make_lookup_then_select_stub(
    captured_calls: list,
    *,
    manifest_uuid_for_lookup: str | None,
    report_rows: list,
    created_by_for_actor_check: str | None = "alice",
):
    """Stub: lookup_registered_experiment_id → returns manifest_uuid OR None;
    then build_report_idor_sql SELECT → returns report_rows.

    Uses two separate context-manager invocations (the /report flow
    opens xact #1 for lookup then xact #2 for the IDOR SELECT).

    Round 3 M-IDOR-ENUM: ``_lookup_manifest_uuid_sync`` runs a *second*
    fetchone after the FOR SHARE SELECT to read ``created_by``. Default
    ``created_by_for_actor_check='alice'`` matches ``_operator_actor_alice``
    (own row branch). Pass a different actor_id (e.g. 'bob') or ``None`` to
    simulate cross-actor enumeration.

    Stub：lookup_registered_experiment_id → 回 manifest_uuid 或 None；
    build_report_idor_sql SELECT → 回 report_rows。/report 流程兩次 xact。

    Round 3 M-IDOR-ENUM：``_lookup_manifest_uuid_sync`` 在 FOR SHARE SELECT 後
    再 fetchone 一次讀 ``created_by``。default ``created_by_for_actor_check
    ='alice'`` 對齊 ``_operator_actor_alice``（own row 分支）。傳不同
    actor_id（如 'bob'）或 ``None`` 模擬跨 actor 枚舉。
    """
    invocation_count = {"n": 0}

    @contextmanager
    def _gen():
        conn = MagicMock()
        cur = MagicMock()
        invocation_count["n"] += 1

        if invocation_count["n"] == 1:
            # First xact: lookup_registered_experiment_id (FOR SHARE) +
            # round 3 created_by check.
            # 第一次 xact：lookup_registered_experiment_id（FOR SHARE）+
            # round 3 created_by check。
            fetchone_returns: list = [
                # SET LOCAL statement_timeout (no fetchone return needed
                # because execute is captured but fetchone not called for SET).
                # Then SELECT ... FOR SHARE: returns (uuid,) or None.
                (manifest_uuid_for_lookup,) if manifest_uuid_for_lookup else None,
            ]
            # Round 3: only when V049 row found AND caller passed an
            # ``expected_actor_id`` (production /report path always does)
            # do we run the second fetchone.
            # Round 3：只有 V049 row 找到 + caller 傳 ``expected_actor_id``
            # （production /report 路徑必傳）才執行第二次 fetchone。
            if manifest_uuid_for_lookup:
                fetchone_returns.append(
                    (created_by_for_actor_check,)
                    if created_by_for_actor_check is not None
                    else None
                )
            cur.fetchone.side_effect = fetchone_returns
        else:
            # Second xact: build_report_idor_sql SELECT
            # 第二次 xact：build_report_idor_sql SELECT。
            # safe_pg_select uses cur.fetchall() so we set side_effect on that.
            cur.fetchall.return_value = report_rows
            cur.description = [
                ("artifact_id",), ("artifact_type",), ("artifact_path",),
                ("byte_size",), ("is_mock",), ("created_at_ms",),
                ("run_id",), ("status",), ("exit_code",),
                ("started_at_ms",), ("completed_at_ms",),
            ]

        def _execute(sql, params=()):
            captured_calls.append(
                (str(sql), tuple(params) if not isinstance(params, tuple) else params)
            )

        cur.execute.side_effect = _execute
        conn.cursor.return_value = cur
        yield conn
    return _gen


# ─── Case 1: report after register works (real experiment_id flow) ────


def test_report_post_r2_smoke_registered_experiment_returns_200(monkeypatch):
    """Case 1: /report on a registered experiment → 200 + matching manifest_id.
    Case 1：對已註冊 experiment 執行 /report → 200 + 對齊 manifest_id。

    Validates the H-3 fix: /report calls
    ``route_helpers.lookup_registered_experiment_id`` (same helper /run
    uses) and uses the REAL V049 UUID for the V046 SELECT, instead of
    the broken UUID5 derivation.
    驗 H-3 fix：/report 用 lookup_registered_experiment_id（與 /run 同 helper）
    取真 V049 UUID，取代壞掉的 UUID5 衍生。
    """
    captured_calls: list = []
    real_uuid = "11111111-1111-1111-1111-bbbbbbbbbbbb"
    monkeypatch.setattr(
        "app.replay_routes.get_pg_conn",
        _make_lookup_then_select_stub(
            captured_calls,
            manifest_uuid_for_lookup=real_uuid,
            report_rows=[],  # 0 artifacts — still 200 with empty list
        ),
    )

    client = _build_client(_operator_actor_alice)
    resp = client.get(f"/api/v1/replay/report/{real_uuid}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    data = body["data"]
    # H-3 invariant: manifest_id in response is the REAL UUID (not UUID5
    # derivation). With round 1 it would be uuid5(NS, real_uuid) which
    # differs.
    # H-3 不變式：response 的 manifest_id 是真 UUID（非 UUID5 衍生）。
    assert data["manifest_id"] == real_uuid, (
        f"H-3 regression: /report manifest_id != registered UUID "
        f"(got {data['manifest_id']!r}, want {real_uuid!r})"
    )
    assert data["experiment_id"] == real_uuid
    assert data["wiring_status"] == "pg_path_active"

    # Verify the lookup SQL (FOR SHARE) was issued — proves H-3 cross-route
    # helper reuse, not UUID5.
    # 驗 lookup SQL（FOR SHARE）已發 — 證 H-3 跨 route helper 重用，非 UUID5。
    lookup_sqls = [s for s, _ in captured_calls
                   if "FOR SHARE" in s and "replay.experiments" in s]
    assert len(lookup_sqls) >= 1, (
        f"expected lookup SQL with FOR SHARE on replay.experiments; "
        f"captured: {[s[:80] for s, _ in captured_calls]}"
    )


# ─── Case 2: report on unregistered experiment → 404 ─────────────────


def test_report_post_r2_smoke_unregistered_returns_404(monkeypatch):
    """Case 2: /report on unregistered experiment_id → 404 + reason.
    Case 2：對未註冊 experiment_id /report → 404 + 原因。

    Round 1 silently returned 200 + 0 artifacts because UUID5 derivation
    of an unregistered ID still produces a deterministic UUID that just
    didn't match any row. Round 2 H-3 short-circuits with 404 when V049
    has no row — operator immediately sees the registration is missing.
    Round 1 對未註冊 silently 回 200 + 0 artifacts（UUID5 仍產 deterministic
    UUID 只是 0 match）。Round 2 H-3 在 V049 0 row 短路 404 — operator 立即
    看到未註冊。
    """
    captured_calls: list = []
    monkeypatch.setattr(
        "app.replay_routes.get_pg_conn",
        _make_lookup_then_select_stub(
            captured_calls,
            manifest_uuid_for_lookup=None,  # not registered
            report_rows=[],
        ),
    )

    client = _build_client(_operator_actor_alice)
    resp = client.get(
        "/api/v1/replay/report/aaaa1111-2222-3333-4444-cccccccccccc"
    )
    assert resp.status_code == 404, resp.text
    detail = resp.json().get("detail", {})
    assert "replay_experiment_not_found" in detail.get("reason_codes", []), detail


# ─── Case 3: invalid experiment_id shape → 400 ───────────────────────


def test_report_post_r2_smoke_invalid_shape_returns_400():
    """Case 3: experiment_id with disallowed chars → 400.
    Case 3：experiment_id 含非法字 → 400。

    Pre-existing shape guard (preserved by R2 round 2 H-3 extraction
    into ``replay/report_route.py::validate_experiment_id_shape``).
    既有 shape 守門（R2 round 2 H-3 抽至
    ``replay/report_route.py::validate_experiment_id_shape``）。
    """
    client = _build_client(_operator_actor_alice)
    # FastAPI may URL-encode '/' so use a non-slash invalid char (semicolon)
    # to keep the request reaching the handler with the path param intact.
    # FastAPI 會 URL-encode '/'，用分號保持 path param 抵達 handler。
    resp = client.get("/api/v1/replay/report/has;semicolon")
    assert resp.status_code == 400, resp.text
    detail = resp.json().get("detail", {})
    assert "replay_invalid_experiment_id" in detail.get("reason_codes", []), detail
