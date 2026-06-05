"""
MODULE_NOTE
模塊用途：WATCHDOG-ALERT-WIRE（2026-06-05）GUI 告警配置端點單元測試。
  覆蓋 GET /api/v1/settings/alerts（遮罩，不外洩明文）、POST（partial-safe 合併、
  __CLEAR__ sentinel、enabled 前置條件 + SSRF 驗證 400）。
主要類/函數：以 dependency_overrides 繞過 auth（auth 本體沿用既有已測程式碼），
  只掛 settings_router 於乾淨 FastAPI app，OPENCLAW_DATA_DIR 指向 tmpdir。
依賴：fastapi.testclient、settings_routes、alert_config、pytest tmp_path。
硬邊界：不發真 HTTP；不寫 prod data dir；不碰交易 / 風控 / 授權硬邊界。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import settings_routes  # noqa: E402
from app import alert_config  # noqa: E402


class _FakeActor:
    """測試用 actor，帶 operator 角色。"""
    actor_id = "test-operator"
    roles = ["operator"]


@pytest.fixture
def alert_dir(tmp_path, monkeypatch) -> str:
    """把 OPENCLAW_DATA_DIR 指向 tmpdir，並清掉告警 env 變量（避免 fallback 污染）。"""
    d = tmp_path / "data"
    d.mkdir()
    monkeypatch.setenv("OPENCLAW_DATA_DIR", str(d))
    for k in (
        "OPENCLAW_TELEGRAM_BOT_TOKEN", "OPENCLAW_TELEGRAM_CHAT_ID",
        "OPENCLAW_WEBHOOK_URLS", "OPENCLAW_WEBHOOK_SECRET",
    ):
        monkeypatch.delenv(k, raising=False)
    return str(d)


@pytest.fixture
def client(alert_dir) -> TestClient:
    """只掛 settings_router，並用 dependency_overrides 繞過 auth。"""
    app = FastAPI()
    app.include_router(settings_routes.settings_router)
    app.dependency_overrides[settings_routes._get_auth_actor] = lambda: _FakeActor()
    app.dependency_overrides[settings_routes._require_operator_auth] = lambda: _FakeActor()
    return TestClient(app)


def _write_stored(data_dir: str, telegram=None, webhook=None) -> None:
    cfg = {
        "version": 1,
        "telegram": telegram or {"enabled": False, "bot_token": "", "chat_id": ""},
        "webhook": webhook or {"enabled": False, "urls": [], "secret": ""},
        "updated_at": 111,
    }
    with open(Path(data_dir) / "alert_config.json", "w", encoding="utf-8") as f:
        json.dump(cfg, f)


# ── GET：遮罩 / 不外洩明文 ──


def test_get_empty_config(client: TestClient):
    resp = client.get("/api/v1/settings/alerts")
    assert resp.status_code == 200
    body = resp.json()
    assert body["telegram"]["enabled"] is False
    assert body["telegram"]["bot_token_configured"] is False
    assert body["webhook"]["urls"] == []
    assert body["any_channel_active"] is False
    assert body["config_present"] is False
    assert body["last_modified"] is None


def test_get_masks_secrets(client: TestClient, alert_dir):
    _write_stored(
        alert_dir,
        telegram={"enabled": True, "bot_token": "SECRET_TOKEN_1234", "chat_id": "999"},
        webhook={"enabled": True, "urls": ["https://h.example.com"], "secret": "WHSECRET9876"},
    )
    resp = client.get("/api/v1/settings/alerts")
    body = resp.json()
    # 永不回明文 token / secret。
    assert "bot_token" not in body["telegram"]
    assert "secret" not in body["webhook"]
    assert body["telegram"]["bot_token_configured"] is True
    assert body["telegram"]["bot_token_hint"] == "••••1234"
    assert body["webhook"]["secret_hint"] == "••••9876"
    # chat_id / urls 屬識別碼明文回。
    assert body["telegram"]["chat_id"] == "999"
    assert body["webhook"]["urls"] == ["https://h.example.com"]
    assert body["any_channel_active"] is True
    assert body["last_modified"] == 111
    # 確認整個回應 body 不含任何明文機密。
    assert "SECRET_TOKEN_1234" not in resp.text
    assert "WHSECRET9876" not in resp.text


# ── POST：partial-safe / __CLEAR__ / 驗證 400 ──


def test_post_partial_safe_empty_keeps_stored(client: TestClient, alert_dir):
    """空字串 token = 保留原值（與 stored 合併）。"""
    _write_stored(alert_dir, telegram={"enabled": False, "bot_token": "KEEP_ME_4321", "chat_id": "5"})
    resp = client.post("/api/v1/settings/alerts", json={
        "telegram": {"enabled": False, "bot_token": "", "chat_id": "5"},
    })
    assert resp.status_code == 200, resp.text
    assert resp.json()["saved"] is True
    # 落盤後 token 仍是原值。
    stored = alert_config.load_alert_config(alert_dir)
    assert stored["telegram"]["bot_token"] == "KEEP_ME_4321"


def test_post_clear_sentinel_clears_token(client: TestClient, alert_dir):
    """__CLEAR__ sentinel = 清除（且 enabled 必須一併關閉，否則前置條件 400）。"""
    _write_stored(alert_dir, telegram={"enabled": True, "bot_token": "OLD", "chat_id": "5"})
    resp = client.post("/api/v1/settings/alerts", json={
        "telegram": {"enabled": False, "bot_token": "__CLEAR__", "chat_id": "5"},
    })
    assert resp.status_code == 200, resp.text
    stored = alert_config.load_alert_config(alert_dir)
    assert stored["telegram"]["bot_token"] == ""


def test_post_new_token_replaces(client: TestClient, alert_dir):
    resp = client.post("/api/v1/settings/alerts", json={
        "telegram": {"enabled": True, "bot_token": "NEW_TOKEN_0001", "chat_id": "42"},
    })
    assert resp.status_code == 200, resp.text
    stored = alert_config.load_alert_config(alert_dir)
    assert stored["telegram"]["bot_token"] == "NEW_TOKEN_0001"
    assert stored["telegram"]["enabled"] is True
    # 回應遮罩，不外洩。
    assert "NEW_TOKEN_0001" not in resp.text


def test_post_telegram_enabled_requires_creds(client: TestClient, alert_dir):
    """telegram.enabled 但 chat_id 空 → 400。"""
    resp = client.post("/api/v1/settings/alerts", json={
        "telegram": {"enabled": True, "bot_token": "T", "chat_id": ""},
    })
    assert resp.status_code == 400
    assert "chat_id" in resp.json()["detail"]


def test_post_webhook_enabled_requires_url(client: TestClient, alert_dir):
    resp = client.post("/api/v1/settings/alerts", json={
        "webhook": {"enabled": True, "urls": []},
    })
    assert resp.status_code == 400


def test_post_webhook_ssrf_blocked(client: TestClient, alert_dir):
    """webhook.enabled + 內網 URL → SSRF 守衛 400，且不外洩 URL 回顯。"""
    resp = client.post("/api/v1/settings/alerts", json={
        "webhook": {"enabled": True, "urls": ["https://169.254.169.254/x"]},
    })
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "Invalid webhook URL" in detail
    assert "blocked_internal_address" in detail


def test_post_webhook_non_https_blocked(client: TestClient, alert_dir):
    resp = client.post("/api/v1/settings/alerts", json={
        "webhook": {"enabled": True, "urls": ["http://8.8.8.8/x"]},
    })
    assert resp.status_code == 400
    assert "scheme_not_https" in resp.json()["detail"]


def test_post_webhook_public_https_ok(client: TestClient, alert_dir):
    """公網 https（IP 字面量，免 DNS）應通過並落盤。"""
    resp = client.post("/api/v1/settings/alerts", json={
        "webhook": {"enabled": True, "urls": ["https://8.8.8.8/hook"], "secret": "abc"},
    })
    assert resp.status_code == 200, resp.text
    stored = alert_config.load_alert_config(alert_dir)
    assert stored["webhook"]["urls"] == ["https://8.8.8.8/hook"]
    assert stored["webhook"]["enabled"] is True


def test_post_rejects_too_many_urls(client: TestClient, alert_dir):
    urls = [f"https://8.8.8.8/{i}" for i in range(11)]
    resp = client.post("/api/v1/settings/alerts", json={
        "webhook": {"enabled": True, "urls": urls},
    })
    assert resp.status_code == 400
    assert "10" in resp.json()["detail"]


def test_post_rejects_control_chars(client: TestClient, alert_dir):
    resp = client.post("/api/v1/settings/alerts", json={
        "telegram": {"enabled": False, "bot_token": "bad\ntoken", "chat_id": "1"},
    })
    assert resp.status_code == 400


# ── POST /test：節流 ──


def test_post_test_unconfigured_returns_not_attempted(client: TestClient, alert_dir):
    """無配置 → test 端點回 attempted=False，不拋。"""
    # 重置 per-process 節流時間戳，避免被其他測試殘留卡住。
    settings_routes._alert_test_last_ts = 0.0
    resp = client.post("/api/v1/settings/alerts/test")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["telegram"]["attempted"] is False
    assert body["webhook"]["attempted"] is False


def test_post_test_rate_limited(client: TestClient, alert_dir):
    """連續兩次 test → 第二次 429（per-process ≥10s 節流）。"""
    settings_routes._alert_test_last_ts = 0.0
    r1 = client.post("/api/v1/settings/alerts/test")
    assert r1.status_code == 200
    r2 = client.post("/api/v1/settings/alerts/test")
    assert r2.status_code == 429
