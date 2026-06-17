"""
POLICY-2 — flag-gated 5-gate live strategy toggle 測試（TP2-1..8）。

MODULE_NOTE (中):
  驗 strategy_write_routes activate/pause/stop 的 POLICY-2 行為：
    - 旗標 OPENCLAW_STRATEGY_TOGGLE_LIVE_MODE default-OFF。
    - flag-OFF + engine=demo / 無 engine → 既有 demo 行為，bit-identical（呼 ORCHESTRATOR +
      _sync_strategy_active{engine:demo}，無 token）。
    - flag-OFF + engine=live → 409 live_strategy_toggle_disabled（fail-loud，不靜默降級 demo）。
    - flag-ON + engine=live：補完整 5-gate（all_five_live_gates_ok require_authz=True）；
      失敗 → 409 live_gate_failed；通過 → call_params_with_token("set_strategy_active",
      {engine:live}) + IPC，**不**碰 ORCHESTRATOR（Python demo orchestrator 狀態）。

  Mac mock pytest：不驗 Rust chokepoint（TP2-7 由 Phase-0 Rust live_authz unit test 釘死，
  set_strategy_active 已在 LIVE_WRITE_METHODS）；本檔證 Python 端鑄並附 token + fail-loud +
  orchestrator 隔離。
"""

from __future__ import annotations

import asyncio
import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

# ── Path setup ────────────────────────────────────────────────────────────────
_test_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(_test_dir)
if _control_api_dir not in sys.path:
    sys.path.insert(0, _control_api_dir)

# 與 sibling 測試一致：import app.* 前 setdefault api token，避免 Bearer 401 污染。
os.environ.setdefault("OPENCLAW_API_TOKEN", "test-token")

import pytest  # noqa: E402

from app import strategy_write_routes as sw  # noqa: E402


_TOKEN_KEYS = {"live_authz_token", "live_authz_nonce", "live_authz_ts"}


def _run(coro):
    # asyncio.run（fresh loop）隔離跨檔 event-loop 污染（鏡像 phase0 retrofit 測試）。
    return asyncio.run(coro)


def _fake_request(body: dict | None):
    req = MagicMock()
    if body is None:
        req.json = AsyncMock(side_effect=ValueError("no body"))
    else:
        req.json = AsyncMock(return_value=body)
    return req


def _operator_actor():
    return SimpleNamespace(actor_id="op", roles={"operator"}, scopes={"strategy:write"})


@pytest.fixture(autouse=True)
def _flag_off_by_default(monkeypatch):
    # 每測試前確保旗標 OFF（除非該測試顯式 setenv ON），避免環境洩漏。
    monkeypatch.delenv("OPENCLAW_STRATEGY_TOGGLE_LIVE_MODE", raising=False)


@pytest.fixture
def live_secret(monkeypatch):
    monkeypatch.setenv("OPENCLAW_LIVE_PATCH_SECRET", "policy2-test-secret")


def _patch_demo_path(monkeypatch, captured):
    """demo 路徑共用 mock：strategy:write gate no-op + 捕捉 ORCHESTRATOR + IPC。"""
    monkeypatch.setattr(sw, "_require_strategy_write", lambda actor: None)
    monkeypatch.setattr(sw, "_validate_strategy_name", lambda n: n)

    orch = MagicMock()
    orch.activate_strategy.return_value = True
    orch.pause_strategy.return_value = True
    orch.stop_strategy.return_value = True
    monkeypatch.setattr(sw, "ORCHESTRATOR", orch)
    captured["orch"] = orch

    class _FakeIpc:
        async def call(self, method, params=None):
            captured["method"] = method
            captured["params"] = params
            return {"ok": True}

    monkeypatch.setattr(sw, "_get_strategy_ipc", AsyncMock(return_value=_FakeIpc()))


# ── TP2-1: flag-OFF + demo → 既有行為 bit-identical（ORCHESTRATOR + engine=demo，無 token）──


def test_tp2_1_flag_off_demo_bit_identical(monkeypatch):
    captured = {}
    _patch_demo_path(monkeypatch, captured)

    out = _run(sw.activate_strategy("ma_crossover", _fake_request({"engine": "demo"}), actor=_operator_actor()))
    assert out["data"]["action"] == "activated"
    captured["orch"].activate_strategy.assert_called_once_with("ma_crossover")
    assert captured["method"] == "set_strategy_active"
    assert captured["params"] == {"strategy_name": "ma_crossover", "active": True, "engine": "demo"}
    assert "live_authz_token" not in captured["params"]


def test_tp2_1b_flag_off_no_engine_defaults_demo(monkeypatch):
    """無 engine 欄（None request 與空 body）→ demo（保 direct-call 與 HTTP 兩路徑）。"""
    captured = {}
    _patch_demo_path(monkeypatch, captured)

    # direct-call 無 request（None）
    out = _run(sw.pause_strategy("ma_crossover", actor=_operator_actor()))
    assert out["data"]["action"] == "paused"
    assert captured["params"]["engine"] == "demo"
    assert "live_authz_token" not in captured["params"]

    # HTTP 路徑空 body
    captured.clear()
    _patch_demo_path(monkeypatch, captured)
    out = _run(sw.stop_strategy("ma_crossover", _fake_request(None), actor=_operator_actor()))
    assert out["data"]["action"] == "stopped"
    assert captured["params"]["engine"] == "demo"


# ── TP2-2: flag-OFF + engine=live → 409 live_strategy_toggle_disabled（fail-loud）──


def test_tp2_2_flag_off_live_fails_loud(monkeypatch):
    from fastapi import HTTPException

    captured = {}
    _patch_demo_path(monkeypatch, captured)
    # 不設旗標 → OFF
    with pytest.raises(HTTPException) as exc:
        _run(sw.activate_strategy("ma_crossover", _fake_request({"engine": "live"}), actor=_operator_actor()))
    assert exc.value.status_code == 409
    assert exc.value.detail["error"] == "live_strategy_toggle_disabled"
    # 0 mutation：既不碰 ORCHESTRATOR 也不發 IPC
    captured["orch"].activate_strategy.assert_not_called()
    assert "method" not in captured, "no IPC when flag-OFF live is refused"


def test_tp2_2b_flag_off_live_never_demoted_to_demo(monkeypatch):
    """強化：flag-OFF live 必須 fail-loud，**絕不**靜默改成 demo（pause/stop 同此）。"""
    from fastapi import HTTPException

    captured = {}
    _patch_demo_path(monkeypatch, captured)
    for fn in (sw.activate_strategy, sw.pause_strategy, sw.stop_strategy):
        with pytest.raises(HTTPException) as exc:
            _run(fn("ma_crossover", _fake_request({"engine": "live"}), actor=_operator_actor()))
        assert exc.value.status_code == 409
        assert exc.value.detail["error"] == "live_strategy_toggle_disabled"
    assert "method" not in captured


# ── TP2-3: flag-ON + demo → 仍走 demo（旗標只開 live 分支，不改 demo）──


def test_tp2_3_flag_on_demo_still_demo(monkeypatch):
    captured = {}
    _patch_demo_path(monkeypatch, captured)
    monkeypatch.setenv("OPENCLAW_STRATEGY_TOGGLE_LIVE_MODE", "1")
    gate = MagicMock()
    import app.live_preflight as lp
    monkeypatch.setattr(lp, "all_five_live_gates_ok", gate)

    out = _run(sw.activate_strategy("ma_crossover", _fake_request({"engine": "demo"}), actor=_operator_actor()))
    assert out["data"]["action"] == "activated"
    gate.assert_not_called()  # demo 不走 5-gate
    assert captured["params"]["engine"] == "demo"
    assert "live_authz_token" not in captured["params"]


# ── TP2-4: flag-ON + engine=live + 5-gate 通過 → 鑄 token + IPC engine=live ──


def test_tp2_4_flag_on_live_5gate_pass_mints_token(live_secret, monkeypatch):
    captured = {}
    _patch_demo_path(monkeypatch, captured)
    monkeypatch.setenv("OPENCLAW_STRATEGY_TOGGLE_LIVE_MODE", "1")
    import app.live_preflight as lp
    monkeypatch.setattr(lp, "all_five_live_gates_ok", lambda actor, require_authz=True: (True, []))

    out = _run(sw.activate_strategy("ma_crossover", _fake_request({"engine": "live"}), actor=_operator_actor()))
    assert out["data"]["action"] == "activated"
    assert out["data"]["engine"] == "live"
    assert captured["method"] == "set_strategy_active"
    assert captured["params"]["engine"] == "live"
    assert captured["params"]["strategy_name"] == "ma_crossover"
    assert captured["params"]["active"] is True
    assert _TOKEN_KEYS <= set(captured["params"]), "live toggle must mint+attach token after 5-gate"


# ── TP2-5: flag-ON + engine=live + 5-gate 失敗 → 409 live_gate_failed，永不 mint/IPC ──


def test_tp2_5_flag_on_live_missing_5gate_blocked(monkeypatch):
    from fastapi import HTTPException

    captured = {}
    _patch_demo_path(monkeypatch, captured)
    monkeypatch.setenv("OPENCLAW_STRATEGY_TOGGLE_LIVE_MODE", "1")
    import app.live_preflight as lp
    monkeypatch.setattr(lp, "all_five_live_gates_ok",
                        lambda actor, require_authz=True: (False, ["global_mode_not_live_reserved"]))

    with pytest.raises(HTTPException) as exc:
        _run(sw.activate_strategy("ma_crossover", _fake_request({"engine": "live"}), actor=_operator_actor()))
    assert exc.value.status_code == 409
    assert exc.value.detail["error"] == "live_gate_failed"
    assert "global_mode_not_live_reserved" in exc.value.detail["gate_failed"]
    assert "method" not in captured, "no IPC / no mint when 5-gate fails"


# ── TP2-6: scope —— strategy:write 單獨不足以授權 live（須額外 5-gate）──


def test_tp2_6_strategy_write_scope_alone_insufficient_for_live(monkeypatch):
    """actor 持 strategy:write 但 5-gate 失敗（如缺 operator 角色被 gate 攔）→ 仍被拒。

    證 live 分支不只看 _require_strategy_write，必額外過 all_five_live_gates_ok（與
    toggle_dynamic_risk 同級）。
    """
    from fastapi import HTTPException

    captured = {}
    _patch_demo_path(monkeypatch, captured)
    monkeypatch.setenv("OPENCLAW_STRATEGY_TOGGLE_LIVE_MODE", "1")
    import app.live_preflight as lp
    monkeypatch.setattr(lp, "all_five_live_gates_ok",
                        lambda actor, require_authz=True: (False, ["operator_role"]))

    actor = SimpleNamespace(actor_id="viewer", roles={"viewer"}, scopes={"strategy:write"})
    with pytest.raises(HTTPException) as exc:
        _run(sw.pause_strategy("ma_crossover", _fake_request({"engine": "live"}), actor=actor))
    assert exc.value.status_code == 409
    assert exc.value.detail["error"] == "live_gate_failed"
    assert "method" not in captured


# ── TP2-7: no-token direct-to-Rust → Rust chokepoint live_authz_token_required ──
#   （Phase-0 已保證：set_strategy_active ∈ LIVE_WRITE_METHODS；本 Python 路徑無論如何
#    都鑄 token。此處以結構斷言證 live 分支恆鑄 token，即「不存在不帶 token 的 live IPC」。）


def test_tp2_7_live_branch_always_mints_token(live_secret, monkeypatch):
    captured = {}
    _patch_demo_path(monkeypatch, captured)
    monkeypatch.setenv("OPENCLAW_STRATEGY_TOGGLE_LIVE_MODE", "1")
    import app.live_preflight as lp
    monkeypatch.setattr(lp, "all_five_live_gates_ok", lambda actor, require_authz=True: (True, []))

    # 三路由皆走 _sync_strategy_active_live → call_params_with_token → 帶 token。
    for fn, active in ((sw.activate_strategy, True), (sw.pause_strategy, False), (sw.stop_strategy, False)):
        captured.clear()
        _patch_demo_path(monkeypatch, captured)
        _run(fn("ma_crossover", _fake_request({"engine": "live"}), actor=_operator_actor()))
        assert captured["params"]["engine"] == "live"
        assert captured["params"]["active"] is active
        assert _TOKEN_KEYS <= set(captured["params"]), f"{fn.__name__} live IPC must carry token"


def test_tp2_7b_killswitch_no_secret_fails_closed(monkeypatch):
    """撤 secret → mint raise → live toggle fail-closed（500），永不發無 token live IPC。"""
    from fastapi import HTTPException

    captured = {}
    _patch_demo_path(monkeypatch, captured)
    monkeypatch.setenv("OPENCLAW_STRATEGY_TOGGLE_LIVE_MODE", "1")
    monkeypatch.delenv("OPENCLAW_LIVE_PATCH_SECRET", raising=False)
    monkeypatch.delenv("OPENCLAW_LIVE_PATCH_SECRET_FILE", raising=False)
    import app.live_preflight as lp
    monkeypatch.setattr(lp, "all_five_live_gates_ok", lambda actor, require_authz=True: (True, []))

    with pytest.raises(HTTPException) as exc:
        _run(sw.activate_strategy("ma_crossover", _fake_request({"engine": "live"}), actor=_operator_actor()))
    # 路由 except → 500 internal error（mint RuntimeError 被包）
    assert exc.value.status_code == 500
    assert "method" not in captured, "no IPC when token mint fails (fail-closed)"


# ── TP2-8: live toggle 不可變動 Python ORCHESTRATOR 狀態（純 Rust IPC）──


def test_tp2_8_live_toggle_does_not_mutate_orchestrator(live_secret, monkeypatch):
    captured = {}
    _patch_demo_path(monkeypatch, captured)
    monkeypatch.setenv("OPENCLAW_STRATEGY_TOGGLE_LIVE_MODE", "1")
    import app.live_preflight as lp
    monkeypatch.setattr(lp, "all_five_live_gates_ok", lambda actor, require_authz=True: (True, []))

    for fn in (sw.activate_strategy, sw.pause_strategy, sw.stop_strategy):
        captured.clear()
        _patch_demo_path(monkeypatch, captured)
        import app.live_preflight as lp2
        monkeypatch.setattr(lp2, "all_five_live_gates_ok", lambda actor, require_authz=True: (True, []))
        _run(fn("ma_crossover", _fake_request({"engine": "live"}), actor=_operator_actor()))
        orch = captured["orch"]
        orch.activate_strategy.assert_not_called()
        orch.pause_strategy.assert_not_called()
        orch.stop_strategy.assert_not_called()
        # 確認確實有走 live IPC（否則 assert_not_called 為空轉真陽性）
        assert captured["params"]["engine"] == "live"
        assert _TOKEN_KEYS <= set(captured["params"])


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
