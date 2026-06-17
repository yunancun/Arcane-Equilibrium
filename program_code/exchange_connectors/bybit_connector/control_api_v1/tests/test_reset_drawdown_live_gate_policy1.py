"""
POLICY-1 — POST /reset-drawdown-baseline {engine:live} 必須 5-gate + 顯式 override 路徑。

MODULE_NOTE (中):
  驗證 risk_routes.reset_drawdown_baseline 對 engine=="live" 的授權收緊（POLICY-1）：
    - override=False（預設）→ 完整 5-gate（live_preflight.all_five_live_gates_ok
      require_authz=True）；未過 → 409 live_gate_failed，IPC 永不被呼叫。
    - override=True → 結構不可達 signed-auth 場景（halt-recovery 等）的顯式 override：
      前 4 門（live_reserved + operator + ALLOW_MAINNET + secret-slot）一律必過，
      **只**豁免第 5 門 (signed-auth)；前 4 門缺一 → 409。
    - override 永不繞 operator-role（route 自身 operator gate 先於 live 分支，403 先發）。
    - demo/paper 不受 5-gate 影響（維持現行，無 token）。
    - 審計可區分查詢（Root #8）：override row 帶 override:true/bypassed_gate:signed_auth/
      caller，普通 row 不帶 override 欄。
    - halt-recovery（approve_live_halt_recovery）走直接 risk_view_client 繞過本 route，
      不被新 5-gate 卡死。
    - four_gates_minus_authz_ok = all_five_live_gates_ok(require_authz=False) 重組，
      零新增/零放寬 gate 邏輯。

  Mock 邊界（infra-independent，不連真 PG/engine/socket）：
    - 直接呼叫 async route handler（鏡 test_reset_drawdown_route）。
    - live_preflight.all_five_live_gates_ok / four_gates_minus_authz_ok → patch 回
      (ok, reasons)；分離測試另證 four_gates_minus_authz_ok 真委派 require_authz=False。
    - _get_risk_view_client → 假 client。
    - _get_governance_hub → 真 ChangeAuditLog 驗審計 row 可分離。
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app import risk_routes
from app.change_audit_log import ChangeAuditLog, ChangeType
from app.risk_routes import (
    ResetDrawdownBaselineRequest,
    reset_drawdown_baseline,
)


# ─── helpers ────────────────────────────────────────────────────────────────


def _run(coro):
    # Py 3.12：每 call 自管 new loop + close，不污染 global state（鏡既有測試）。
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class _FakeRiskViewClient:
    """最小 RiskViewClient 替身 — route 只用 reset_drawdown_baseline + get_status。"""

    def __init__(self, result: dict[str, Any] | Exception) -> None:
        self._result = result
        self.calls: list[str] = []

    async def reset_drawdown_baseline(self, engine: str) -> dict[str, Any]:
        self.calls.append(engine)
        if isinstance(self._result, Exception):
            raise self._result
        return self._result

    async def unhalt_session(self, engine: str) -> dict[str, Any]:
        self.calls.append(f"unhalt:{engine}")
        return {"ok": True}

    def get_status(self) -> dict[str, Any]:
        return {"governor_tier": "Normal"}


def _operator_actor(actor_id: str = "operator-1") -> SimpleNamespace:
    return SimpleNamespace(actor_id=actor_id, roles={"operator"}, scopes={"risk:write"})


def _non_operator_actor() -> SimpleNamespace:
    return SimpleNamespace(actor_id="viewer-1", roles={"viewer"})


def _nv(change) -> dict[str, Any]:
    """ChangeRecord.new_value 以 json.dumps 存為字串（PG text/jsonb 欄），解回 dict
    供斷言。可分離查詢正是靠這個 JSON（operator 對 change_audit_log 查 override 欄）。"""
    return json.loads(change.new_value) if change.new_value else {}


@pytest.fixture
def patch_risk_view_client(monkeypatch):
    def _install(client: _FakeRiskViewClient):
        async def _factory():
            return client

        monkeypatch.setattr(risk_routes, "_get_risk_view_client", _factory)
        return client

    return _install


@pytest.fixture
def audit_hub(monkeypatch):
    log = ChangeAuditLog()
    hub = SimpleNamespace(_change_audit_log=log)
    from app import governance_routes  # noqa: PLC0415
    monkeypatch.setattr(governance_routes, "_get_governance_hub", lambda: hub)
    return log


# ═══════════════════════════════════════════════════════════════════════════
# TP1-1: engine=live, override=False, 5-gate 未過 → 409, 0 reset
# ═══════════════════════════════════════════════════════════════════════════


def test_tp1_1_live_default_gate_fail_returns_409_no_reset(patch_risk_view_client):
    client = patch_risk_view_client(_FakeRiskViewClient({"ok": True}))
    body = ResetDrawdownBaselineRequest(engine="live", reason="probe", operator_override=False)
    with patch(
        "app.live_preflight.all_five_live_gates_ok",
        return_value=(False, ["global_mode_not_live_reserved"]),
    ) as gate:
        with pytest.raises(HTTPException) as exc:
            _run(reset_drawdown_baseline(body=body, actor=_operator_actor()))
    assert exc.value.status_code == 409
    assert exc.value.detail["error"] == "live_gate_failed"
    assert exc.value.detail["gate_failed"] == ["global_mode_not_live_reserved"]
    # require_authz=True 必為預設路徑用法。
    _args, kwargs = gate.call_args
    assert kwargs.get("require_authz") is True
    # fail-closed：門未過絕不 reset。
    assert client.calls == []


# ═══════════════════════════════════════════════════════════════════════════
# TP1-2: engine=live, override=False, 5-gate 全過 → reset + 普通審計 (override:false)
# ═══════════════════════════════════════════════════════════════════════════


def test_tp1_2_live_default_gate_pass_resets_normal_audit(patch_risk_view_client, audit_hub):
    ipc_result = {"engine": "live", "result": "drawdown_baseline_reset"}
    client = patch_risk_view_client(_FakeRiskViewClient(ipc_result))
    body = ResetDrawdownBaselineRequest(
        engine="live",
        reason="operator manual reset after review",
        operator_override=False,
    )
    with patch("app.live_preflight.all_five_live_gates_ok", return_value=(True, [])):
        resp = _run(reset_drawdown_baseline(body=body, actor=_operator_actor("op-5g")))
    assert resp["ok"] is True
    assert resp["data"]["engine"] == "live"
    assert client.calls == ["live"]
    # 普通路徑審計 row：override 欄不存在（byte-identical 既有形態）。
    changes = audit_hub.get_all_changes()
    assert len(changes) == 1
    c = changes[0]
    assert c.change_type == ChangeType.STATE_CHANGE
    assert c.who == "op-5g"
    assert "OPERATOR_OVERRIDE" not in c.what
    assert "override" not in _nv(c)


# ═══════════════════════════════════════════════════════════════════════════
# TP1-3: engine=live, override=True, operator-role + 前4門過、無 signed-auth → reset + DISTINCT 審計
# ═══════════════════════════════════════════════════════════════════════════


def test_tp1_3_live_override_4gate_pass_resets_distinct_audit(patch_risk_view_client, audit_hub):
    ipc_result = {"engine": "live", "result": "drawdown_baseline_reset"}
    client = patch_risk_view_client(_FakeRiskViewClient(ipc_result))
    body = ResetDrawdownBaselineRequest(
        engine="live",
        reason="halt recovery operator override: signed-auth auto-revoked",
        operator_override=True,
    )
    # override 路徑只諮詢 four_gates_minus_authz_ok（不諮詢 all_five，因 signed-auth 豁免）。
    with patch(
        "app.live_preflight.four_gates_minus_authz_ok", return_value=(True, [])
    ) as four_gate, patch(
        "app.live_preflight.all_five_live_gates_ok",
        return_value=(False, ["authorization"]),  # 若被誤呼會洩漏；驗證它不被呼叫。
    ) as five_gate:
        resp = _run(reset_drawdown_baseline(body=body, actor=_operator_actor("op-ovr")))
    assert resp["ok"] is True
    assert client.calls == ["live"]
    four_gate.assert_called_once()
    five_gate.assert_not_called()  # override 路徑不跑 require_authz=True
    # DISTINCT 審計 row：可分離查詢（Root #8）。
    changes = audit_hub.get_all_changes()
    assert len(changes) == 1
    c = changes[0]
    assert "OPERATOR_OVERRIDE" in c.what
    assert "authz-gate-bypassed" in c.what
    nv = _nv(c)
    assert nv["override"] is True
    assert nv["bypassed_gate"] == "signed_auth"
    assert nv["caller"] == "manual_override"


# ═══════════════════════════════════════════════════════════════════════════
# TP1-4: engine=live, override=True, 非 operator-role → 403 (override 不繞 operator-role)
# ═══════════════════════════════════════════════════════════════════════════


def test_tp1_4_live_override_non_operator_returns_403(patch_risk_view_client):
    client = patch_risk_view_client(_FakeRiskViewClient({"ok": True}))
    body = ResetDrawdownBaselineRequest(engine="live", reason="probe", operator_override=True)
    # 即使 4-gate primitive 會放行也無關緊要：operator gate 先擋。
    with patch(
        "app.live_preflight.four_gates_minus_authz_ok", return_value=(True, [])
    ) as four_gate:
        with pytest.raises(HTTPException) as exc:
            _run(reset_drawdown_baseline(body=body, actor=_non_operator_actor()))
    assert exc.value.status_code == 403
    # operator gate 先於 live 分支：4-gate 不該被諮詢，0 reset。
    four_gate.assert_not_called()
    assert client.calls == []


# ═══════════════════════════════════════════════════════════════════════════
# TP1-5: engine=live, override=True, 前4門缺一 → 409 (override 只豁免 signed-auth)
# ═══════════════════════════════════════════════════════════════════════════


def test_tp1_5_live_override_missing_one_of_four_gates_returns_409(patch_risk_view_client):
    client = patch_risk_view_client(_FakeRiskViewClient({"ok": True}))
    body = ResetDrawdownBaselineRequest(engine="live", reason="probe", operator_override=True)
    # 前 4 門缺一（如 mainnet_env）→ override 仍必 409。
    with patch(
        "app.live_preflight.four_gates_minus_authz_ok",
        return_value=(False, ["mainnet_env"]),
    ):
        with pytest.raises(HTTPException) as exc:
            _run(reset_drawdown_baseline(body=body, actor=_operator_actor()))
    assert exc.value.status_code == 409
    assert exc.value.detail["error"] == "live_gate_failed"
    assert exc.value.detail["gate_failed"] == ["mainnet_env"]
    assert client.calls == []


# ═══════════════════════════════════════════════════════════════════════════
# TP1-6: engine=demo/paper → 維持現行（無 5-gate, 無 token）
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("engine", ["demo", "paper"])
def test_tp1_6_demo_paper_unaffected_no_gate(patch_risk_view_client, audit_hub, engine):
    client = patch_risk_view_client(_FakeRiskViewClient({"engine": engine, "ok": True}))
    body = ResetDrawdownBaselineRequest(engine=engine, reason="routine reset")
    # 即使 gate primitive 會 fail 也不該被諮詢（demo/paper 不觸 live 分支）。
    five_gate = MagicMock(return_value=(False, ["should_not_be_consulted"]))
    four_gate = MagicMock(return_value=(False, ["should_not_be_consulted"]))
    with patch("app.live_preflight.all_five_live_gates_ok", five_gate), patch(
        "app.live_preflight.four_gates_minus_authz_ok", four_gate
    ):
        resp = _run(reset_drawdown_baseline(body=body, actor=_operator_actor()))
    assert resp["ok"] is True
    assert client.calls == [engine]
    five_gate.assert_not_called()
    four_gate.assert_not_called()
    # demo/paper 審計：無 override 欄（byte-identical 既有形態）。
    changes = audit_hub.get_all_changes()
    assert len(changes) == 1
    assert "override" not in _nv(changes[0])


# ═══════════════════════════════════════════════════════════════════════════
# TP1-6b: override=True 但 engine=demo → override 旗標對 non-live 無效（demo 維持現行）
# ═══════════════════════════════════════════════════════════════════════════


def test_tp1_6b_override_true_on_demo_is_inert(patch_risk_view_client, audit_hub):
    client = patch_risk_view_client(_FakeRiskViewClient({"engine": "demo", "ok": True}))
    body = ResetDrawdownBaselineRequest(engine="demo", reason="routine", operator_override=True)
    four_gate = MagicMock(return_value=(False, ["should_not_be_consulted"]))
    with patch("app.live_preflight.four_gates_minus_authz_ok", four_gate):
        resp = _run(reset_drawdown_baseline(body=body, actor=_operator_actor()))
    assert resp["ok"] is True
    four_gate.assert_not_called()
    # demo 即使帶 override=True 也不寫 distinct 審計（override 概念僅 live）。
    changes = audit_hub.get_all_changes()
    assert len(changes) == 1
    assert "override" not in _nv(changes[0])


# ═══════════════════════════════════════════════════════════════════════════
# TP1-7: halt-recovery end-to-end 不被新 5-gate 卡死（直接走 client，繞過 route）
# ═══════════════════════════════════════════════════════════════════════════


def test_tp1_7_halt_recovery_not_deadlocked_by_new_gate(monkeypatch, tmp_path):
    """approve_live_halt_recovery 走直接 risk_view_client（繞過 FastAPI route），
    故新 route-level 5-gate 不卡死它。同時驗證：override 路徑的設計使其結構上
    不可能被 require_authz=True 卡死（halt 時 signed-auth 已撤銷）。"""
    from app import live_halt_recovery as lhr

    # OPENCLAW_DATA_DIR → tmp，注入 halted snapshot。
    monkeypatch.setenv("OPENCLAW_DATA_DIR", str(tmp_path))
    snapshot = {
        "session_halted": True,
        "session_drawdown_pct": 12.0,
        "max_drawdown_pct": 10.0,
        "system_mode": "live_reserved",
    }
    (tmp_path / lhr.LIVE_HALT_SNAPSHOT_FILENAME).write_text(
        __import__("json").dumps(snapshot), encoding="utf-8"
    )

    fake_client = _FakeRiskViewClient({"ok": True, "result": "reset"})

    async def _factory():
        return fake_client

    # halt-recovery 走 risk_routes._get_risk_view_client（lazy import 進 lhr）。
    monkeypatch.setattr(risk_routes, "_get_risk_view_client", _factory)

    # 關鍵不變量：即使 all_five_live_gates_ok(require_authz=True) 必然失敗（halt 時
    # signed-auth 撤銷），halt-recovery 仍能成功——因為它不經 route。若它誤經 route 預設
    # 路徑，這個 patch 會使它 409 卡死。
    def _always_fail(actor, *, require_authz):
        return (False, ["authorization"])

    monkeypatch.setattr("app.live_preflight.all_five_live_gates_ok", _always_fail)

    result = _run(lhr.approve_live_halt_recovery("op-halt"))
    assert result["status"] == "approved"
    assert result["reset"]["ok"] is True
    # 直接走 client：reset("live") + unhalt("live") 都被呼叫。
    assert "live" in fake_client.calls
    assert "unhalt:live" in fake_client.calls


# ═══════════════════════════════════════════════════════════════════════════
# TP1-8: 審計可區分查詢 — override row vs 普通 row（同一 ChangeAuditLog）
# ═══════════════════════════════════════════════════════════════════════════


def test_tp1_8_audit_separable_override_vs_normal(patch_risk_view_client, audit_hub):
    client = patch_risk_view_client(_FakeRiskViewClient({"ok": True}))

    # 普通 5-gated live reset。
    with patch("app.live_preflight.all_five_live_gates_ok", return_value=(True, [])):
        _run(reset_drawdown_baseline(
            body=ResetDrawdownBaselineRequest(
                engine="live", reason="normal 5-gated reset", operator_override=False
            ),
            actor=_operator_actor("op-normal"),
        ))

    # override live reset。
    with patch("app.live_preflight.four_gates_minus_authz_ok", return_value=(True, [])):
        _run(reset_drawdown_baseline(
            body=ResetDrawdownBaselineRequest(
                engine="live",
                reason="override reset for halt recovery",
                operator_override=True,
            ),
            actor=_operator_actor("op-override"),
        ))

    changes = audit_hub.get_all_changes()
    assert len(changes) == 2

    # 可按 new_value["override"] 分離查詢（Root #8）。
    override_rows = [c for c in changes if _nv(c).get("override") is True]
    normal_rows = [c for c in changes if "override" not in _nv(c)]
    assert len(override_rows) == 1
    assert len(normal_rows) == 1
    assert override_rows[0].who == "op-override"
    assert _nv(override_rows[0])["bypassed_gate"] == "signed_auth"
    assert normal_rows[0].who == "op-normal"


# ═══════════════════════════════════════════════════════════════════════════
# four_gates_minus_authz_ok 重組正確性：= all_five_live_gates_ok(require_authz=False)
# （只重組、不新增/不放寬 gate；signed-auth 是唯一被豁免的門）
# ═══════════════════════════════════════════════════════════════════════════


def test_four_gates_helper_delegates_to_require_authz_false():
    import app.live_preflight as lp

    actor = _operator_actor()
    captured = {}

    def _fake_all_five(a, *, require_authz):
        captured["actor"] = a
        captured["require_authz"] = require_authz
        return (True, ["sentinel"])

    with patch.object(lp, "all_five_live_gates_ok", _fake_all_five):
        ok, reasons = lp.four_gates_minus_authz_ok(actor)

    # 嚴格委派：require_authz=False（豁免第 5 門 signed-auth），其餘原樣轉回。
    assert captured["require_authz"] is False
    assert captured["actor"] is actor
    assert ok is True
    assert reasons == ["sentinel"]


def test_four_gates_helper_propagates_first_four_gate_failure():
    """前 4 門任一失敗（如 operator_role）必如實回傳 — 不放寬。"""
    import app.live_preflight as lp

    def _fake_all_five(a, *, require_authz):
        assert require_authz is False
        return (False, ["operator_role"])

    with patch.object(lp, "all_five_live_gates_ok", _fake_all_five):
        ok, reasons = lp.four_gates_minus_authz_ok(_operator_actor())
    assert ok is False
    assert reasons == ["operator_role"]


# ═══════════════════════════════════════════════════════════════════════════
# IPC failure 仍 fail-loud（live override 路徑過 gate 後 IPC 掛 → 500，0 審計）
# ═══════════════════════════════════════════════════════════════════════════


def test_live_override_ipc_failure_surfaces_500_no_audit(patch_risk_view_client, audit_hub):
    patch_risk_view_client(_FakeRiskViewClient(RuntimeError("ipc timeout")))
    body = ResetDrawdownBaselineRequest(engine="live", reason="ovr", operator_override=True)
    with patch("app.live_preflight.four_gates_minus_authz_ok", return_value=(True, [])):
        with pytest.raises(HTTPException) as exc:
            _run(reset_drawdown_baseline(body=body, actor=_operator_actor()))
    assert exc.value.status_code == 500
    # 未發生的 reset 絕不留審計。
    assert audit_hub.get_all_changes() == []
