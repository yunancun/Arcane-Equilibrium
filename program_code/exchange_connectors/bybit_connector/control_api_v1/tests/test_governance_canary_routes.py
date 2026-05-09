"""
governance_canary_routes pytest 套件 — W-AUDIT-9 T5 GUI 後端契約。

範圍：
  1. validate payload — 跳階 / Stage 4 / 相鄰晉升合法
  2. acquire lease 失敗 → 423 LOCKED；不寫 audit log row
  3. SHADOW_BYPASS sentinel 拒 → 409；不寫 audit log row
  4. happy path — operator + lease ok + DB write ok → 200 + envelope
  5. operator role 守門
  6. cohort listing 端點 — read-only，PG 不可用回空 list（fail-soft）

策略：
  - 不啟 FastAPI app 整個 import chain（避免 db_pool / 其他 singleton 在 Mac
    pytest 撞 import-time side effect）
  - 直接 unit-test handler function via inject mock GovernanceHub +
    monkeypatch _write_canary_stage_log_manual_promote / _query_*
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ────────────────────────────────────────────────────────────────────────────
# Stub actor with operator role
# ────────────────────────────────────────────────────────────────────────────
@dataclass(slots=True)
class _StubActor:
    actor_id: str
    actor_type: str
    roles: set
    scopes: set


def _make_operator_actor() -> _StubActor:
    return _StubActor(
        actor_id="op-test-1",
        actor_type="human",
        roles={"operator", "viewer"},
        scopes={"private_readonly"},
    )


def _make_viewer_actor() -> _StubActor:
    return _StubActor(
        actor_id="viewer-1",
        actor_type="human",
        roles={"viewer"},
        scopes={"private_readonly"},
    )


# ────────────────────────────────────────────────────────────────────────────
# Lazy import — 避免 collection-time side effects
# ────────────────────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def canary_module():
    from app import governance_canary_routes
    return governance_canary_routes


# ────────────────────────────────────────────────────────────────────────────
# 1. Payload validation
# ────────────────────────────────────────────────────────────────────────────
class TestValidatePayload:
    def test_adjacent_promotion_ok(self, canary_module):
        from fastapi import HTTPException
        body = canary_module.CanaryManualPromoteRequest(
            cohort_id="grid:BTCUSDT:demo",
            from_stage=1,
            to_stage=2,
            reason="entry_fills 12 滿足升 stage 條件",
        )
        # 不應拋
        canary_module._validate_manual_promote_payload(body)

    def test_skip_stage_rejected(self, canary_module):
        from fastapi import HTTPException
        body = canary_module.CanaryManualPromoteRequest(
            cohort_id="grid:BTCUSDT:demo",
            from_stage=0,
            to_stage=2,
            reason="skip stage attempt",
        )
        with pytest.raises(HTTPException) as exc:
            canary_module._validate_manual_promote_payload(body)
        assert exc.value.status_code == 400
        assert "相鄰 stage" in str(exc.value.detail)

    def test_to_stage_4_rejected(self, canary_module):
        from fastapi import HTTPException
        body = canary_module.CanaryManualPromoteRequest(
            cohort_id="global",
            from_stage=3,
            to_stage=4,
            reason="attempt direct LIVE_PENDING",
        )
        with pytest.raises(HTTPException) as exc:
            canary_module._validate_manual_promote_payload(body)
        assert exc.value.status_code == 400
        assert "5-gate" in str(exc.value.detail)

    def test_rollback_via_endpoint_rejected(self, canary_module):
        from fastapi import HTTPException
        # to_stage < from_stage 必然 != from_stage + 1，落在第一個 if
        body = canary_module.CanaryManualPromoteRequest(
            cohort_id="grid:BTCUSDT:demo",
            from_stage=2,
            to_stage=0,
            reason="attempt rollback via promote endpoint",
        )
        with pytest.raises(HTTPException) as exc:
            canary_module._validate_manual_promote_payload(body)
        assert exc.value.status_code == 400


# ────────────────────────────────────────────────────────────────────────────
# 2. SHADOW_BYPASS sentinel 偵測
# ────────────────────────────────────────────────────────────────────────────
class TestShadowBypassDetection:
    def test_sentinel_recognized(self, canary_module):
        assert canary_module._is_shadow_bypass_lease("SHADOW_BYPASS:intent-foo") is True

    def test_normal_uuid_not_sentinel(self, canary_module):
        assert canary_module._is_shadow_bypass_lease(
            "550e8400-e29b-41d4-a716-446655440000"
        ) is False

    def test_none_not_sentinel(self, canary_module):
        assert canary_module._is_shadow_bypass_lease(None) is False

    def test_empty_string_not_sentinel(self, canary_module):
        assert canary_module._is_shadow_bypass_lease("") is False


# ────────────────────────────────────────────────────────────────────────────
# 3. _write_canary_stage_log_manual_promote — UUID 校驗 + DB unavailable 回 None
# ────────────────────────────────────────────────────────────────────────────
class TestWriteCanaryStageLog:
    def test_invalid_uuid_returns_none(self, canary_module):
        # 非合法 UUID 字串 → fail-closed 回 None
        result = canary_module._write_canary_stage_log_manual_promote(
            cohort_id="grid:BTCUSDT:demo",
            from_stage=1,
            to_stage=2,
            decision_lease_id="not-a-valid-uuid",
            reason="test invalid uuid",
        )
        assert result is None

    def test_db_unavailable_returns_none(self, canary_module):
        # mock db_pool.get_pg_conn 回 None → fail-closed
        with patch.object(
            canary_module,
            "_write_canary_stage_log_manual_promote",
            wraps=canary_module._write_canary_stage_log_manual_promote,
        ):
            with patch("app.db_pool.get_pg_conn") as mock_get_conn:
                mock_ctx = MagicMock()
                mock_ctx.__enter__.return_value = None
                mock_ctx.__exit__.return_value = False
                mock_get_conn.return_value = mock_ctx

                result = canary_module._write_canary_stage_log_manual_promote(
                    cohort_id="grid:BTCUSDT:demo",
                    from_stage=1,
                    to_stage=2,
                    decision_lease_id="550e8400-e29b-41d4-a716-446655440000",
                    reason="test db unavailable",
                )
                assert result is None


# ────────────────────────────────────────────────────────────────────────────
# 4. _query_active_cohorts / _query_metric_registry — fail-soft
# ────────────────────────────────────────────────────────────────────────────
class TestQueryActiveCohorts:
    def test_pg_unavailable_returns_empty_list(self, canary_module):
        with patch("app.db_pool.get_pg_conn") as mock_get_conn:
            mock_ctx = MagicMock()
            mock_ctx.__enter__.return_value = None
            mock_ctx.__exit__.return_value = False
            mock_get_conn.return_value = mock_ctx

            result = canary_module._query_active_cohorts()
            assert result == []

    def test_table_missing_returns_empty_list(self, canary_module):
        with patch("app.db_pool.get_pg_conn") as mock_get_conn:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            # to_regclass returns None → table missing
            mock_cursor.fetchone.return_value = (None,)
            mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
            mock_ctx = MagicMock()
            mock_ctx.__enter__.return_value = mock_conn
            mock_ctx.__exit__.return_value = False
            mock_get_conn.return_value = mock_ctx

            result = canary_module._query_active_cohorts()
            assert result == []


class TestQueryMetricRegistry:
    def test_pg_unavailable_returns_empty(self, canary_module):
        with patch("app.db_pool.get_pg_conn") as mock_get_conn:
            mock_ctx = MagicMock()
            mock_ctx.__enter__.return_value = None
            mock_ctx.__exit__.return_value = False
            mock_get_conn.return_value = mock_ctx
            result = canary_module._query_metric_registry()
            assert result == []


# ────────────────────────────────────────────────────────────────────────────
# 5. POST /manual_promote — handler full flow
# ────────────────────────────────────────────────────────────────────────────
class TestPostManualPromote:
    def test_acquire_returns_none_raises_423(self, canary_module):
        from fastapi import HTTPException
        body = canary_module.CanaryManualPromoteRequest(
            cohort_id="grid:BTCUSDT:demo",
            from_stage=1,
            to_stage=2,
            reason="acquire fails test",
        )
        actor = _make_operator_actor()

        # mock GOV_HUB
        mock_hub = MagicMock()
        mock_hub.acquire_lease.return_value = None  # acquire denied
        with patch(
            "app.paper_trading_routes.GOV_HUB",
            mock_hub,
            create=True,
        ):
            with pytest.raises(HTTPException) as exc:
                canary_module.post_canary_manual_promote(body, actor=actor)
            assert exc.value.status_code == 423

    def test_shadow_bypass_lease_raises_409(self, canary_module):
        from fastapi import HTTPException
        body = canary_module.CanaryManualPromoteRequest(
            cohort_id="grid:BTCUSDT:demo",
            from_stage=0,
            to_stage=1,
            reason="shadow bypass test",
        )
        actor = _make_operator_actor()

        mock_hub = MagicMock()
        mock_hub.acquire_lease.return_value = "SHADOW_BYPASS:canary-promote-x"
        with patch(
            "app.paper_trading_routes.GOV_HUB",
            mock_hub,
            create=True,
        ):
            with pytest.raises(HTTPException) as exc:
                canary_module.post_canary_manual_promote(body, actor=actor)
            assert exc.value.status_code == 409

    def test_non_operator_raises_403(self, canary_module):
        from fastapi import HTTPException
        body = canary_module.CanaryManualPromoteRequest(
            cohort_id="grid:BTCUSDT:demo",
            from_stage=1,
            to_stage=2,
            reason="viewer attempt",
        )
        viewer = _make_viewer_actor()
        with pytest.raises(HTTPException) as exc:
            canary_module.post_canary_manual_promote(body, actor=viewer)
        # _require_operator_role 在 Step 1 即拋；不會走到 acquire
        assert exc.value.status_code == 403

    def test_skip_stage_raises_400_before_lease(self, canary_module):
        from fastapi import HTTPException
        body = canary_module.CanaryManualPromoteRequest(
            cohort_id="grid:BTCUSDT:demo",
            from_stage=0,
            to_stage=2,
            reason="skip attempt",
        )
        actor = _make_operator_actor()

        mock_hub = MagicMock()
        # acquire 不應被呼叫
        with patch(
            "app.paper_trading_routes.GOV_HUB",
            mock_hub,
            create=True,
        ):
            with pytest.raises(HTTPException) as exc:
                canary_module.post_canary_manual_promote(body, actor=actor)
            assert exc.value.status_code == 400
            mock_hub.acquire_lease.assert_not_called()

    def test_happy_path_returns_envelope(self, canary_module):
        body = canary_module.CanaryManualPromoteRequest(
            cohort_id="grid:BTCUSDT:demo",
            from_stage=1,
            to_stage=2,
            reason="happy path test entry_fills>=10",
        )
        actor = _make_operator_actor()
        valid_uuid = "550e8400-e29b-41d4-a716-446655440000"

        mock_hub = MagicMock()
        mock_hub.acquire_lease.return_value = valid_uuid
        mock_hub.release_lease.return_value = True
        with patch(
            "app.paper_trading_routes.GOV_HUB",
            mock_hub,
            create=True,
        ):
            with patch.object(
                canary_module,
                "_write_canary_stage_log_manual_promote",
                return_value=42,  # stage_log_id
            ) as mock_write:
                result = canary_module.post_canary_manual_promote(body, actor=actor)
                assert result["ok"] is True
                assert result["data"]["stage_log_id"] == 42
                assert result["data"]["from_stage"] == 1
                assert result["data"]["to_stage"] == 2
                assert result["data"]["decision_lease_id"] == valid_uuid
                assert result["data"]["transition_kind"] == "manual_promote"

                # acquire 用 60s TTL
                mock_hub.acquire_lease.assert_called_once()
                call_kwargs = mock_hub.acquire_lease.call_args.kwargs
                assert call_kwargs["ttl_seconds"] == 60.0
                assert call_kwargs["scope"] == "CanaryStagePromotion"

                # release 必呼叫
                mock_hub.release_lease.assert_called_once()

                # write 收到正確的 lease_id
                mock_write.assert_called_once()
                write_kwargs = mock_write.call_args.kwargs
                assert write_kwargs["decision_lease_id"] == valid_uuid

    def test_db_write_failure_releases_lease_and_500(self, canary_module):
        from fastapi import HTTPException
        body = canary_module.CanaryManualPromoteRequest(
            cohort_id="grid:BTCUSDT:demo",
            from_stage=1,
            to_stage=2,
            reason="db write fail test",
        )
        actor = _make_operator_actor()
        valid_uuid = "550e8400-e29b-41d4-a716-446655440000"

        mock_hub = MagicMock()
        mock_hub.acquire_lease.return_value = valid_uuid
        mock_hub.release_lease.return_value = True
        with patch(
            "app.paper_trading_routes.GOV_HUB",
            mock_hub,
            create=True,
        ):
            with patch.object(
                canary_module,
                "_write_canary_stage_log_manual_promote",
                return_value=None,  # DB write 失敗
            ):
                with pytest.raises(HTTPException) as exc:
                    canary_module.post_canary_manual_promote(body, actor=actor)
                assert exc.value.status_code == 500
                # release 即使 DB write 失敗也必呼叫
                mock_hub.release_lease.assert_called_once()

    def test_governance_hub_unavailable_raises_503(self, canary_module):
        from fastapi import HTTPException
        body = canary_module.CanaryManualPromoteRequest(
            cohort_id="grid:BTCUSDT:demo",
            from_stage=1,
            to_stage=2,
            reason="hub unavailable",
        )
        actor = _make_operator_actor()

        # Force GOV_HUB import to raise → handler should catch and return 503
        import sys as _sys

        # Save original module if present
        ptr_module = _sys.modules.get("app.paper_trading_routes")
        try:
            # Patch the module-level GOV_HUB attribute to None to simulate unavailable
            with patch(
                "app.paper_trading_routes.GOV_HUB",
                None,
                create=True,
            ):
                with pytest.raises(HTTPException) as exc:
                    canary_module.post_canary_manual_promote(body, actor=actor)
                assert exc.value.status_code == 503
        finally:
            if ptr_module is not None:
                _sys.modules["app.paper_trading_routes"] = ptr_module


# ────────────────────────────────────────────────────────────────────────────
# 6. GET /cohorts handler — fail-soft + envelope
# ────────────────────────────────────────────────────────────────────────────
class TestGetCanaryCohorts:
    def test_pg_unavailable_returns_empty_envelope(self, canary_module):
        with patch.object(canary_module, "_query_active_cohorts", return_value=[]):
            with patch.object(canary_module, "_query_metric_registry", return_value=[]):
                result = canary_module.get_canary_cohorts()
                assert result["ok"] is True
                assert result["data"]["cohorts"] == []
                assert result["data"]["metric_registry"] == []
                assert len(result["data"]["stages"]) == 5
                # 每 stage label 有 'Stage' prefix
                for s in result["data"]["stages"]:
                    assert "Stage" in s["label"]
                assert "now_ms" in result["data"]

    def test_with_active_cohorts(self, canary_module):
        sample_cohorts = [
            {
                "cohort_id": "grid:BTCUSDT:demo",
                "current_stage": 1,
                "stage_entered_at_ms": 1700000000000,
                "last_transition_kind": "manual_promote",
                "last_decision_lease_id": "550e8400-e29b-41d4-a716-446655440000",
            }
        ]
        sample_metrics = [
            {
                "stage": 1,
                "metric_name": "entry_fills",
                "direction": "promote_upper",
                "threshold_value": 10.0,
                "observation_window_ms": 7 * 24 * 60 * 60 * 1000,
                "description": "Stage 1 promote condition",
            }
        ]
        with patch.object(canary_module, "_query_active_cohorts", return_value=sample_cohorts):
            with patch.object(canary_module, "_query_metric_registry", return_value=sample_metrics):
                result = canary_module.get_canary_cohorts()
                assert result["ok"] is True
                assert len(result["data"]["cohorts"]) == 1
                assert result["data"]["cohorts"][0]["cohort_id"] == "grid:BTCUSDT:demo"
                assert len(result["data"]["metric_registry"]) == 1
                assert result["data"]["metric_registry"][0]["metric_name"] == "entry_fills"


# ────────────────────────────────────────────────────────────────────────────
# 7. Constants invariants — TTL 60s strict + scope literal
# ────────────────────────────────────────────────────────────────────────────
class TestConstants:
    def test_lease_ttl_is_60_seconds(self, canary_module):
        # AMD-2026-05-09-03 §4.5 strict 60s
        assert canary_module._CANARY_PROMOTION_LEASE_TTL_SECONDS == 60.0

    def test_lease_scope_literal(self, canary_module):
        # 對齊 Rust LeaseScope::CanaryStagePromotion::as_audit_str()
        assert canary_module._LEASE_SCOPE_CANARY_PROMOTION == "CanaryStagePromotion"

    def test_transition_kind_literal(self, canary_module):
        # 對齊 V080 CHECK constraint canary_stage_log_transition_kind_chk
        assert canary_module._TRANSITION_MANUAL_PROMOTE == "manual_promote"
