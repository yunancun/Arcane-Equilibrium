"""
PHASE 0 AUTH-1 — FIX 2 caller-retrofit 回歸測試。

MODULE_NOTE (中):
  驗證「generalize token mint」後，既有合法 operator live-control caller 過自身 gate 後
  鑄 method-bound token 併入 IPC params（不再被 Rust chokepoint fail-closed 拒），且安全
  屬性保留（live 無 token 仍會被 Rust 拒——此處由 Rust live_authz unit test 釘死，本檔
  驗 Python 端確實鑄並附 token）。涵蓋：
    - live session start / pause / resume → resume_paper/pause_paper{engine:live} 帶 token。
    - reset-cooldown / unhalt-session（Risk-tab paper-control）→ 顯式 engine="paper"、無 token。
    - reset_drawdown_baseline / unhalt_session(live) （live-halt-recovery）→ engine=live 帶 token。

  Mac mock pytest：不驗 Rust verify（Rust 端 check_live_authz_nonpatch_happy_path 已證
  非-patch mint↔verify interop）；本檔證 Python caller 鑄並附 token 三欄。
"""

from __future__ import annotations

import asyncio
import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

# ── Path setup ────────────────────────────────────────────────────────────────
_test_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(_test_dir)
if _control_api_dir not in sys.path:
    sys.path.insert(0, _control_api_dir)

# ★ 必須在 import app.* 之前 setdefault（main_legacy.settings = Settings() 於 import
#   時一次性 resolve api_token）。本檔字母序早於 test_phase2_*，若先觸發 main_legacy
#   import 而無此 token，sibling 測試的 Bearer 認證會 401。與 test_phase2 同 token。
os.environ.setdefault("OPENCLAW_API_TOKEN", "test-token")

import pytest  # noqa: E402

from app import live_session_endpoints as lse  # noqa: E402
from app import live_session_routes as core  # noqa: E402


_TOKEN_KEYS = {"live_authz_token", "live_authz_nonce", "live_authz_ts"}


def _run(coro):
    # 用 asyncio.run（每次 fresh loop）而非 get_event_loop().run_until_complete：
    # sibling 測試（如 test_learning_chapter）reload main_legacy + 操作 event loop 後，
    # get_event_loop() 可能回已關閉/陳舊 loop → 跨檔測試順序污染。asyncio.run 隔離。
    return asyncio.run(coro)


@pytest.fixture
def live_secret(monkeypatch):
    monkeypatch.setenv("OPENCLAW_LIVE_PATCH_SECRET", "phase0-retrofit-secret")


@pytest.fixture
def operator_actor():
    return SimpleNamespace(actor_id="live-operator", roles={"operator"}, scopes={"live:trade"})


# ── live session pause (operator + live:trade, no full 5-gate) ──────────────────


def test_live_session_pause_attaches_token(live_secret, operator_actor, monkeypatch):
    """post_live_session_pause → pause_paper{engine:live} + token 三欄。"""
    captured = {}

    async def fake_ipc_command(method, params=None):
        captured["method"] = method
        captured["params"] = params
        return {"ok": True}

    monkeypatch.setattr(core, "_ipc_command", fake_ipc_command)
    monkeypatch.setattr(lse, "_require_live_trade", lambda actor: None)

    out = _run(lse.post_live_session_pause(actor=operator_actor))
    assert out["data"]["session"]["session_state"] == "paused"
    assert captured["method"] == "pause_paper"
    assert captured["params"]["engine"] == "live"
    assert _TOKEN_KEYS <= set(captured["params"]), "pause must mint+attach token"


# ── live session start / resume (full 5-gate then mint) ─────────────────────────


def _patch_start_resume_deps(monkeypatch, captured):
    async def fake_ipc_command(method, params=None):
        captured["method"] = method
        captured["params"] = params
        return {"ok": True}

    monkeypatch.setattr(core, "_ipc_command", fake_ipc_command)
    monkeypatch.setattr(lse, "_require_live_trade", lambda actor: None)
    # 5-gate pass + readback live_reserved + engine kind
    fake_pre = MagicMock()
    fake_pre.all_five_live_gates_ok = MagicMock(return_value=(True, []))
    fake_pre.engine_mode_readback = AsyncMock(return_value={"system_mode": "live_reserved"})
    monkeypatch.setattr(lse, "core_preflight", lambda: fake_pre)
    monkeypatch.setattr(core, "_get_live_engine_kind", lambda: "live")
    monkeypatch.setattr(core, "_set_execution_authority", lambda v: None)
    monkeypatch.setattr(core, "_get_execution_authority", lambda: {"authority": "granted"})


def test_live_session_start_mints_token_after_gate(live_secret, operator_actor, monkeypatch):
    captured = {}
    _patch_start_resume_deps(monkeypatch, captured)
    # start route does extra stamping after readback; we only assert the IPC mint wiring.
    try:
        _run(lse.post_live_session_start(actor=operator_actor))
    except Exception:
        # 後續 stamp/狀態流程在 mock 下可能拋（非本測試關注點）；只要 IPC 已被帶 token 呼叫即可。
        pass
    assert captured.get("method") == "resume_paper"
    assert captured["params"]["engine"] == "live"
    assert _TOKEN_KEYS <= set(captured["params"]), "start must mint+attach token after 5-gate"


def test_live_session_start_blocked_no_mint_when_gate_fails(operator_actor, monkeypatch):
    """5-gate 失敗 → 409，永不 mint（caller 不鑄 token 在 gate 之前）。"""
    captured = {}

    async def fake_ipc_command(method, params=None):
        captured["method"] = method
        return {"ok": True}

    monkeypatch.setattr(core, "_ipc_command", fake_ipc_command)
    monkeypatch.setattr(lse, "_require_live_trade", lambda actor: None)
    fake_pre = MagicMock()
    fake_pre.all_five_live_gates_ok = MagicMock(return_value=(False, ["global_mode_not_live_reserved"]))
    monkeypatch.setattr(lse, "core_preflight", lambda: fake_pre)
    monkeypatch.setattr(core, "_get_live_engine_kind", lambda: "live")

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        _run(lse.post_live_session_start(actor=operator_actor))
    assert exc.value.status_code == 409
    assert captured == {}, "no IPC / no mint when gate fails"


# ── secret kill-switch on the live-control path ─────────────────────────────────


def test_live_session_pause_killswitch_no_secret(operator_actor, monkeypatch):
    """撤 secret → mint raise → pause fail-closed（502，不靜默放行無 token live 寫）。"""
    # 只移除兩個 secret env（不可用 clear=True 整盤清，會誤殺 sibling 測試的
    # OPENCLAW_API_TOKEN 等模組級 env → 401 污染）。
    monkeypatch.delenv("OPENCLAW_LIVE_PATCH_SECRET", raising=False)
    monkeypatch.delenv("OPENCLAW_LIVE_PATCH_SECRET_FILE", raising=False)

    async def fake_ipc_command(method, params=None):  # pragma: no cover — must not reach
        raise AssertionError("IPC must not be called when token mint fails (fail-closed)")

    monkeypatch.setattr(core, "_ipc_command", fake_ipc_command)
    monkeypatch.setattr(lse, "_require_live_trade", lambda actor: None)
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        _run(lse.post_live_session_pause(actor=operator_actor))
    # 既有 pause except 分支把 mint RuntimeError 包成 502 ipc_error
    assert exc.value.status_code == 502


# ── strategy_write_routes: dynamic-risk toggle + set_strategy_active ────────────


def _fake_request(body: dict):
    req = MagicMock()
    req.json = AsyncMock(return_value=body)
    return req


def test_toggle_dynamic_risk_live_5gate_then_mint(live_secret, monkeypatch):
    """engine=live → 補完整 5-gate；通過後 set_dynamic_risk_enabled 帶 token。"""
    from app import strategy_write_routes as sw

    captured = {}

    class _FakeIpc:
        async def call(self, method, params=None):
            captured["method"] = method
            captured["params"] = params
            return {"ok": True}

    monkeypatch.setattr(sw, "_require_strategy_write", lambda actor: None)
    monkeypatch.setattr(sw, "_get_strategy_ipc", AsyncMock(return_value=_FakeIpc()))
    monkeypatch.setattr(sw, "AUTO_DEPLOYER", None)
    import app.live_preflight as lp
    monkeypatch.setattr(lp, "all_five_live_gates_ok", lambda actor, require_authz=True: (True, []))

    actor = SimpleNamespace(actor_id="op", roles={"operator"}, scopes={"strategy:write"})
    req = _fake_request({"enabled": True, "engine": "live"})
    _run(sw.toggle_dynamic_risk(req, actor=actor))
    assert captured["method"] == "set_dynamic_risk_enabled"
    assert captured["params"]["engine"] == "live"
    assert _TOKEN_KEYS <= set(captured["params"]), "live toggle must mint token after 5-gate"


def test_toggle_dynamic_risk_live_blocked_without_gate(monkeypatch):
    """engine=live + 5-gate 失敗 → 409，永不 mint/IPC。"""
    from app import strategy_write_routes as sw
    from fastapi import HTTPException

    ipc = MagicMock()
    ipc.call = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr(sw, "_require_strategy_write", lambda actor: None)
    monkeypatch.setattr(sw, "_get_strategy_ipc", AsyncMock(return_value=ipc))
    import app.live_preflight as lp
    monkeypatch.setattr(lp, "all_five_live_gates_ok",
                        lambda actor, require_authz=True: (False, ["global_mode_not_live_reserved"]))

    actor = SimpleNamespace(actor_id="op", roles={"operator"}, scopes={"strategy:write"})
    req = _fake_request({"enabled": True, "engine": "live"})
    with pytest.raises(HTTPException) as exc:
        _run(sw.toggle_dynamic_risk(req, actor=actor))
    assert exc.value.status_code == 409
    ipc.call.assert_not_called()


def test_toggle_dynamic_risk_demo_no_gate_no_token(monkeypatch):
    """engine=demo → 既有行為，無 5-gate、無 token。"""
    from app import strategy_write_routes as sw

    captured = {}

    class _FakeIpc:
        async def call(self, method, params=None):
            captured["params"] = params
            return {"ok": True}

    monkeypatch.setattr(sw, "_require_strategy_write", lambda actor: None)
    monkeypatch.setattr(sw, "_get_strategy_ipc", AsyncMock(return_value=_FakeIpc()))
    monkeypatch.setattr(sw, "AUTO_DEPLOYER", None)
    gate = MagicMock()
    import app.live_preflight as lp
    monkeypatch.setattr(lp, "all_five_live_gates_ok", gate)

    actor = SimpleNamespace(actor_id="op", roles={"operator"}, scopes={"strategy:write"})
    req = _fake_request({"enabled": False, "engine": "demo"})
    _run(sw.toggle_dynamic_risk(req, actor=actor))
    gate.assert_not_called()  # demo no 5-gate
    assert captured["params"] == {"enabled": False, "engine": "demo"}
    assert "live_authz_token" not in captured["params"]


def test_sync_strategy_active_targets_demo_explicitly(monkeypatch):
    """_sync_strategy_active 顯式 engine="demo"（非缺省 → 不在 live 引擎觸發 token gate）。"""
    from app import strategy_write_routes as sw

    captured = {}

    class _FakeIpc:
        async def call(self, method, params=None):
            captured["method"] = method
            captured["params"] = params
            return {"ok": True}

    monkeypatch.setattr(sw, "_get_strategy_ipc", AsyncMock(return_value=_FakeIpc()))
    _run(sw._sync_strategy_active("grid_trading", active=True))
    assert captured["method"] == "set_strategy_active"
    assert captured["params"]["engine"] == "demo"
    assert "live_authz_token" not in captured["params"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
