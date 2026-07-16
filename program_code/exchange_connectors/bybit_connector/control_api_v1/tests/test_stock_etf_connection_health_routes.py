"""Stock/ETF W4 connection-health route + normalizer three-layer tests.

包含 AMD-2026-07-08-01 §Runtime Boundary 硬要求的 **all-false fail-closed 回歸**
（tripwire）：`gate=BLOCKED` + 強注每個 operational 真值 → 仍須全列 contract_violations;
任何未來鬆動第 2/3 層即轉紅。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from stock_etf_route_fixtures import (
    _make_client_with_ipc,
    _valid_connection_health,
    client_fail_closed,
    route_module,
    stock_etf_router,
)

# gate=BLOCKED + 全 operational 真值注入下的**精確、有序** contract_violations（tripwire）。
# 第 1 層（hard-safety,無條件）在前;第 2 層（negative-space,lineage 缺席）在後。
EXPECTED_CONNECTION_HEALTH_CONTRACT_VIOLATIONS = [
    # ── 第 1 層 hard-safety（不受 lineage 影響）──
    "ibkr_contact_performed",
    "secret_slot_touched",
    "order_routed",
    "bybit_ipc_reused",
    "ibkr_live_enabled",
    "gateway_socket_open",
    "db_apply_performed",
    # ── 第 2 層 negative-space（lineage_present == False）──
    "session_state_populated",
    "session_active",
    "reconnect_attempt_present",
    "halt_reason_not_envelope_required",
    "pacing_queue_depth_present",
    "pacing_lines_in_use_present",
    "pacing_ib_pacing_strikes_present",
    "pacing_admitted_present",
    "pacing_rejected_order_verb_present",
    "pacing_rejected_queue_full_present",
    "pacing_rejected_timeout_present",
    "pacing_rejected_historical_present",
    "pacing_rejected_lines_present",
    "attestation_status_populated",
    "account_fingerprint_is_live",
    "entitlement_state_populated",
    "report_status_populated",
]


def test_stock_etf_connection_health_returns_200_when_ipc_down(
    client_fail_closed: TestClient,
) -> None:
    resp = client_fail_closed.get("/api/v1/stock-etf/connection-health")
    assert resp.status_code == 200
    assert "no-store" in resp.headers["cache-control"]
    assert "private" in resp.headers["cache-control"]
    assert resp.headers["pragma"] == "no-cache"
    assert resp.headers["expires"] == "0"
    assert resp.headers["vary"] == "Authorization"
    body = resp.json()
    data = body["data"]
    assert body["ok"] is True
    assert body["is_simulated"] is False
    assert body["data_category"] == "stock_etf_connection_health"
    assert data["degraded"] is True
    assert data["reason"] == "ipc_unavailable"
    assert data["connection_health_state"] == "degraded"
    assert data["asset_lane"] == "stock_etf_cash"
    assert data["broker"] == "ibkr"
    assert data["environment"] == "paper_readonly"
    assert data["gui_authority"] == "display_only"
    assert data["lineage_present"] is False
    assert data["contract_violations"] == []
    # 負空間安全束輸出恆 false。
    assert data["session_active"] is False
    assert data["gateway_socket_open"] is False
    assert data["ibkr_contact_performed"] is False
    assert data["ibkr_live_enabled"] is False
    assert data["phase2_gate_status"] == "BLOCKED"


def test_stock_etf_connection_health_uses_only_readonly_fixture_method() -> None:
    async def _fake_call(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        assert method == "stock_etf.get_connection_health"
        assert params == {}
        return _valid_connection_health()

    fake_ipc = AsyncMock()
    fake_ipc.call = AsyncMock(side_effect=_fake_call)
    client = _make_client_with_ipc(fake_ipc)
    try:
        data = client.get("/api/v1/stock-etf/connection-health").json()["data"]
    finally:
        client._stock_etf_patcher.stop()  # type: ignore[attr-defined]

    # inactive 引擎的誠實 health：external_verification_pending,零 violation。
    assert data["degraded"] is False
    assert data["contract_violations"] == []
    assert data["connection_health_state"] == "external_verification_pending"
    assert data["report_status"] == "external_verification_pending"
    assert data["phase"] == "phase2_connection_health_source_fixture"
    assert data["session_state"] == "disconnected"
    assert data["halt_reason"] == "envelope_required"
    assert data["session_active"] is False
    assert data["reconnect_attempt"] == 0
    # main_tokens_available＝滿桶 telemetry,誠實非零,不觸 violation。
    assert data["main_tokens_available"] == 50
    assert data["attestation_status"] == "BLOCKED"
    assert data["entitlement_state"] == "pending"
    assert data["account_fingerprint_is_live"] is False
    assert data["lineage_present"] is False
    assert data["phase2_gate_status"] == "BLOCKED"
    fake_ipc.call.assert_awaited_once()


def test_stock_etf_connection_health_does_not_trust_client_state() -> None:
    async def _fake_call(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        assert method == "stock_etf.get_connection_health"
        assert params == {}
        return _valid_connection_health()

    fake_ipc = AsyncMock()
    fake_ipc.call = AsyncMock(side_effect=_fake_call)
    client = _make_client_with_ipc(fake_ipc)
    try:
        resp = client.get(
            "/api/v1/stock-etf/connection-health",
            params={
                "session_active": "true",
                "gateway_socket_open": "true",
                "phase2_gate_status": "PASS",
            },
            headers={
                "X-Ibkr-Session-Active": "true",
                "X-Ibkr-Gateway-Socket": "true",
            },
        )
        data = resp.json()["data"]
    finally:
        client._stock_etf_patcher.stop()  # type: ignore[attr-defined]

    assert "no-store" in resp.headers["cache-control"]
    assert data["session_active"] is False
    assert data["gateway_socket_open"] is False
    assert data["lineage_present"] is False
    assert data["contract_violations"] == []
    fake_ipc.call.assert_awaited_once()


def test_stock_etf_connection_health_all_false_regression_blocks_injected_truths() -> None:
    """AMD §Runtime Boundary tripwire：gate=BLOCKED + 強注每個 operational 真值 → 全列
    contract_violations。任何未來鬆動第 2/3 層即轉紅。main_tokens_available（telemetry）
    即使極大值仍**不**入列。"""
    payload = _valid_connection_health()
    # phase2 gate 維持 BLOCKED → lineage_present == False（第 3 層結構不可達）。
    # 第 1 層 hard-safety 全注 true。
    payload["ibkr_contact_performed"] = True
    payload["secret_slot_touched"] = True
    payload["order_routed"] = True
    payload["bybit_ipc_reused"] = True
    payload["ibkr_live_enabled"] = True
    payload["gateway_socket_open"] = True
    payload["db_apply_performed"] = True
    # 第 2 層 operational 全注 populated。
    payload["session_state"] = "ready"
    payload["session_active"] = True
    payload["reconnect_attempt"] = 5
    payload["halt_reason"] = "halted"
    payload["queue_depth"] = 3
    payload["lines_in_use"] = 2
    payload["ib_pacing_strikes"] = 1
    payload["admitted"] = 9
    payload["rejected_order_verb"] = 1
    payload["rejected_queue_full"] = 1
    payload["rejected_timeout"] = 1
    payload["rejected_historical"] = 1
    payload["rejected_lines"] = 1
    payload["attestation_status"] = "PAPER_ATTESTED"
    payload["account_fingerprint_is_live"] = True
    payload["entitlement_state"] = "granted"
    payload["report_status"] = "degraded"
    # telemetry 極大值——不得入 violation。
    payload["main_tokens_available"] = 999_999

    fake_ipc = AsyncMock()
    fake_ipc.call = AsyncMock(return_value=payload)
    client = _make_client_with_ipc(fake_ipc)
    try:
        data = client.get("/api/v1/stock-etf/connection-health").json()["data"]
    finally:
        client._stock_etf_patcher.stop()  # type: ignore[attr-defined]

    assert data["connection_health_state"] == "contract_violation_blocked"
    assert data["degraded"] is True
    # gate 恆 BLOCKED → lineage 未放行 → 退化為第 2 層 all-false（與 W3 逐位元同構）。
    assert data["lineage_present"] is False
    violations = data["contract_violations"]
    assert violations == EXPECTED_CONNECTION_HEALTH_CONTRACT_VIOLATIONS
    # telemetry 不入 violation（無任何 main_tokens 相關項）。
    assert not any("main_tokens" in item for item in violations)
    # 輸出安全束仍恆 false（NEVER echo injected truths）。
    assert data["session_active"] is False
    assert data["gateway_socket_open"] is False
    assert data["ibkr_contact_performed"] is False
    assert data["ibkr_live_enabled"] is False


def test_stock_etf_connection_health_forged_gate_pass_still_hard_safety_blocks() -> None:
    """縱深防禦：即使 payload 自宣告 gate=PASS + attestation attested（lineage_present=True,
    進第 3 層）,第 1 層 hard-safety **仍無條件**攔截 socket/contact/order/live——W4 emitter
    永不產此 payload,本測試證第 1 層不受 lineage 鬆動（fail-closed 機制 #1 的補強）。"""
    payload = _valid_connection_health()
    payload["phase2"]["external_surface_gate"]["status"] = "PASS"
    payload["attestation_status"] = "PAPER_ATTESTED"
    payload["gateway_socket_open"] = True
    payload["ibkr_contact_performed"] = True
    payload["order_routed"] = True
    payload["ibkr_live_enabled"] = True
    payload["account_fingerprint_is_live"] = True

    fake_ipc = AsyncMock()
    fake_ipc.call = AsyncMock(return_value=payload)
    client = _make_client_with_ipc(fake_ipc)
    try:
        data = client.get("/api/v1/stock-etf/connection-health").json()["data"]
    finally:
        client._stock_etf_patcher.stop()  # type: ignore[attr-defined]

    # 第 3 層雖被進入,hard-safety 仍恆攔;live 帳戶指紋硬否決。
    assert data["lineage_present"] is True
    assert data["connection_health_state"] == "contract_violation_blocked"
    for field in (
        "ibkr_contact_performed",
        "order_routed",
        "ibkr_live_enabled",
        "gateway_socket_open",
    ):
        assert field in data["contract_violations"]
    assert "account_fingerprint_is_live" in data["contract_violations"]


def test_stock_etf_connection_health_requires_auth() -> None:
    route_module._IPC_CLIENT = None
    app = FastAPI()
    app.include_router(stock_etf_router)
    client = TestClient(app)

    resp = client.get("/api/v1/stock-etf/connection-health")

    assert resp.status_code == 401


def test_stock_etf_connection_health_violation_assertions_stay_exact() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    source_under_test = source.split(
        "def test_stock_etf_connection_health_violation_assertions_stay_exact",
        1,
    )[0]
    forbidden_patterns = [
        'set(data["contract_violations"])',
        'in data["contract_violations"]',
        'issubset(set(data["contract_violations"]))',
    ]
    # 例外：forged-gate 測試以 `in` 斷言 hard-safety 子集(縱深防禦,非精確全列),不在
    # all-false tripwire 的精確排序範疇。此守衛只鎖 all-false 回歸的精確有序陣列。
    source_under_test = source_under_test.split(
        "def test_stock_etf_connection_health_forged_gate_pass_still_hard_safety_blocks",
        1,
    )[0]
    for pattern in forbidden_patterns:
        assert pattern not in source_under_test
