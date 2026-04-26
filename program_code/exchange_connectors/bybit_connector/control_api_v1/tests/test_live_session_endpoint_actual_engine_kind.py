"""
Tests for F5/A1 — phantom-view guard + actual_engine_kind / actual_endpoint
markers on Live session account endpoints.

F5/A1 測試 — Live session 帳戶端點的「幽靈視圖守衛」+ actual_engine_kind /
actual_endpoint 元數據欄位。

Background / 背景:
  A3 UX audit (2026-04-26) revealed that when the Live slot is configured for
  LiveDemo (api_key present, bybit_endpoint=demo) but the Rust live engine is
  not running, the previous tab-live HTML always rendered the purple "Live
  实盘 運行中 🟣" banner with real demo wallet/positions data — fooling
  operators into thinking live PnL was being tracked.

  Fix is two-pronged:
    1. ``_live_response()`` now injects ``actual_engine_kind`` + ``actual_endpoint``
       so the GUI can decide between Mainnet (REAL FUNDS) / LiveDemo / unconfigured
       visual modes.
    2. account routes (balance/positions/orders/fills/metrics) call a phantom-view
       guard that returns a structured ``error="live_slot_not_configured"`` payload
       when ``actual_engine_kind != "live"`` AND ``actual_endpoint == "unconfigured"``.

These tests assert both behaviours hold.

A3 UX 審計揭發：Live 槽配置為 LiveDemo 但 Rust live 引擎未跑時，舊 tab-live
永遠渲染紫色「Live 实盘 運行中 🟣」+ demo 帳戶數據 — 誤導 operator。
本檔測試兩件事：
  1. _live_response() 注入 actual_engine_kind + actual_endpoint 欄位
  2. account routes 在 engine 非 live 且 slot 未配置時回 phantom-view error envelope
"""

from __future__ import annotations

import pytest

from app import live_session_account_routes as account_routes
from app import live_session_routes as lsr


# ═══════════════════════════════════════════════════════════════════════════════
# _live_response() — actual_engine_kind / actual_endpoint injection
# ═══════════════════════════════════════════════════════════════════════════════


def test_live_response_injects_actual_engine_kind(monkeypatch):
    """
    Bare ``_live_response({})`` must populate actual_engine_kind via
    setdefault — frontends rely on this for integrity-fail view detection.
    """
    monkeypatch.setattr(lsr, "_get_live_engine_kind", lambda: "demo")
    monkeypatch.setattr(lsr, "_resolve_live_endpoint_label", lambda: "live_demo")
    out = lsr._live_response({"foo": 1})
    assert out["data"]["actual_engine_kind"] == "demo"
    assert out["data"]["actual_endpoint"] == "live_demo"
    assert out["data"]["foo"] == 1
    assert out["data"]["is_simulated"] is False
    assert out["data"]["data_category"] == "live_exchange"


def test_live_response_caller_overrides_actual_fields(monkeypatch):
    """
    Caller-supplied actual_engine_kind / actual_endpoint must NOT be overwritten
    by setdefault. Phantom-view guard relies on this when forcing markers.
    """
    monkeypatch.setattr(lsr, "_get_live_engine_kind", lambda: "live")
    monkeypatch.setattr(lsr, "_resolve_live_endpoint_label", lambda: "mainnet")
    out = lsr._live_response({
        "actual_engine_kind": "paper",   # caller forces paper
        "actual_endpoint": "unconfigured",
    })
    assert out["data"]["actual_engine_kind"] == "paper"
    assert out["data"]["actual_endpoint"] == "unconfigured"


def test_resolve_live_endpoint_label_unconfigured(monkeypatch, tmp_path):
    """When live api_key file is absent → 'unconfigured'."""
    secrets = tmp_path / "secrets" / "secret_files" / "bybit"
    (secrets / "live").mkdir(parents=True)
    monkeypatch.setenv("OPENCLAW_SECRETS_DIR", str(secrets))
    assert lsr._resolve_live_endpoint_label() == "unconfigured"


def test_resolve_live_endpoint_label_mainnet(monkeypatch, tmp_path):
    """live api_key present, no bybit_endpoint file → defaults to mainnet."""
    secrets = tmp_path / "secrets" / "secret_files" / "bybit"
    live = secrets / "live"
    live.mkdir(parents=True)
    (live / "api_key").write_text("MOCK-KEY-1234567890", encoding="utf-8")
    monkeypatch.setenv("OPENCLAW_SECRETS_DIR", str(secrets))
    assert lsr._resolve_live_endpoint_label() == "mainnet"


def test_resolve_live_endpoint_label_live_demo(monkeypatch, tmp_path):
    """live api_key present + bybit_endpoint=demo → 'live_demo' (LiveDemo mode)."""
    secrets = tmp_path / "secrets" / "secret_files" / "bybit"
    live = secrets / "live"
    live.mkdir(parents=True)
    (live / "api_key").write_text("MOCK-DEMO-KEY-12345", encoding="utf-8")
    (live / "bybit_endpoint").write_text("demo", encoding="utf-8")
    monkeypatch.setenv("OPENCLAW_SECRETS_DIR", str(secrets))
    assert lsr._resolve_live_endpoint_label() == "live_demo"


# ═══════════════════════════════════════════════════════════════════════════════
# Phantom-view guard — refuses to expose data when engine != live AND
#                      slot is unconfigured
# ═══════════════════════════════════════════════════════════════════════════════


def test_phantom_guard_blocks_when_engine_not_live_and_slot_unconfigured(monkeypatch):
    """
    Engine reports non-live (demo) AND slot is unconfigured → guard returns
    a structured error payload instead of None.
    """
    monkeypatch.setattr(lsr, "_get_live_engine_kind", lambda: "demo")
    monkeypatch.setattr(lsr, "_resolve_live_endpoint_label", lambda: "unconfigured")
    out = account_routes._phantom_view_guard()
    assert out is not None
    payload = out["data"]
    assert payload["error"] == "live_slot_not_configured"
    assert payload["available"] is False
    assert payload["actual_engine_kind"] == "demo"
    assert payload["actual_endpoint"] == "unconfigured"
    assert payload["count"] == 0
    assert payload["list"] == []
    assert payload["positions"] == []
    # Bilingual error fields present / 雙語錯誤訊息存在
    assert "Live 槽未配置" in payload["error_zh"]
    assert "Live slot not configured" in payload["error_en"]


def test_phantom_guard_allows_live_demo_mode(monkeypatch):
    """
    LiveDemo (slot configured for demo endpoint + Rust live engine running) is
    a legitimate Live mode per CLAUDE.md memory
    `feedback_live_no_degradation_by_endpoint` — the Live pipeline genuinely
    runs on api-demo and authorization is enforced at full Live strictness.
    Guard MUST NOT block this case.
    """
    # LiveDemo with engine running as live: kind=live, endpoint=live_demo
    # LiveDemo 引擎跑 live：kind=live, endpoint=live_demo
    monkeypatch.setattr(lsr, "_get_live_engine_kind", lambda: "live")
    monkeypatch.setattr(lsr, "_resolve_live_endpoint_label", lambda: "live_demo")
    out = account_routes._phantom_view_guard()
    assert out is None  # proceed to normal handler logic


def test_phantom_guard_allows_live_engine_running(monkeypatch):
    """
    Engine reports live → guard always returns None regardless of endpoint
    (Mainnet or LiveDemo). The frontend uses actual_endpoint for theming
    only, not for blocking.
    """
    monkeypatch.setattr(lsr, "_get_live_engine_kind", lambda: "live")
    monkeypatch.setattr(lsr, "_resolve_live_endpoint_label", lambda: "mainnet")
    assert account_routes._phantom_view_guard() is None
    monkeypatch.setattr(lsr, "_resolve_live_endpoint_label", lambda: "live_demo")
    assert account_routes._phantom_view_guard() is None
    monkeypatch.setattr(lsr, "_resolve_live_endpoint_label", lambda: "unconfigured")
    # Even with unconfigured slot, if engine truly is live we proceed —
    # the badge/banner reflects "未配置" but data flow is genuine.
    # 即使槽未配置，引擎真的是 live 也放行 — banner/徽章反映「未配置」，資料是真的。
    assert account_routes._phantom_view_guard() is None


def test_phantom_guard_blocks_when_engine_paper_and_slot_unconfigured(monkeypatch):
    """Paper engine + unconfigured slot → block (same as demo + unconfigured)."""
    monkeypatch.setattr(lsr, "_get_live_engine_kind", lambda: "paper")
    monkeypatch.setattr(lsr, "_resolve_live_endpoint_label", lambda: "unconfigured")
    out = account_routes._phantom_view_guard()
    assert out is not None
    assert out["data"]["error"] == "live_slot_not_configured"


def test_phantom_guard_blocks_when_engine_unknown_and_slot_unconfigured(monkeypatch):
    """Unknown engine_kind (engine offline) + unconfigured slot → block."""
    monkeypatch.setattr(lsr, "_get_live_engine_kind", lambda: "unknown")
    monkeypatch.setattr(lsr, "_resolve_live_endpoint_label", lambda: "unconfigured")
    out = account_routes._phantom_view_guard()
    assert out is not None
    assert out["data"]["actual_engine_kind"] == "unknown"


def test_phantom_guard_allows_demo_engine_with_configured_mainnet_slot(monkeypatch):
    """
    Mainnet slot configured but Rust live engine not running (running demo).
    The slot exchange data is technically real, but it is NOT what the Live
    engine is doing. We DO surface the data but mark actual_engine_kind=demo
    so the frontend swaps to integrity-fail view (per A1 fix #1 in tab-live).

    Note: the guard itself only blocks the unconfigured case. The demo engine
    + Mainnet slot case is handled in the frontend — the GUI sees
    actual_engine_kind != "live" and swaps view, even though backend would
    have happily returned real Mainnet wallet here.
    """
    monkeypatch.setattr(lsr, "_get_live_engine_kind", lambda: "demo")
    monkeypatch.setattr(lsr, "_resolve_live_endpoint_label", lambda: "mainnet")
    # Backend guard does NOT block (slot configured) — frontend handles
    # integrity-fail swap based on actual_engine_kind marker on ``status`` payload.
    # 後端守衛不擋（槽已配置）— 前端讀 status payload actual_engine_kind 自行 swap。
    assert account_routes._phantom_view_guard() is None
