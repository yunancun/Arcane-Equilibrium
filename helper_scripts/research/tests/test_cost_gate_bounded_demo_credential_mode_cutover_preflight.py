from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path

from cost_gate_learning_lane import (
    bounded_demo_credential_mode_cutover_preflight as mod,
)


NOW = dt.datetime(2026, 6, 29, 22, 0, tzinfo=dt.timezone.utc)


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _write_json(path: Path, payload: dict) -> Path:
    return _write(path, json.dumps(payload))


def _readiness(**overrides) -> dict:
    payload = {
        "schema_version": "bounded_demo_runtime_readiness_v1",
        "status": "BOUNDED_DEMO_RUNTIME_BLOCKED_BY_CREDENTIALS",
        "candidate": {"side_cell_key": "grid_trading|ETHUSDT|Buy"},
        "blocking_reasons": [
            "demo_api_slot:demo_api_key_expected_value_mismatch",
            "connector_mode:bybit_mode_not_demo",
            "connector_mode:bybit_connector_write_not_enabled",
        ],
        "answers": {
            "order_capable_action_allowed_by_this_packet": False,
            "decision_lease_acquire_performed": False,
            "runtime_mutation_performed": False,
            "service_restart_performed": False,
            "env_mutation_performed": False,
            "writer_enabled_by_this_packet": False,
            "adapter_enabled_by_this_packet": False,
            "bybit_private_call_performed": False,
            "bybit_credential_validation_call_performed": False,
            "pg_write_performed": False,
            "order_submission_performed": False,
            "global_cost_gate_lowering_recommended": False,
            "live_or_mainnet": False,
            "live_authority_granted": False,
            "promotion_evidence": False,
            "promotion_proof": False,
        },
    }
    payload.update(overrides)
    return payload


def _settings_source() -> str:
    return """
ALLOWED_SLOTS = frozenset({"demo", "live_demo", "live"})

class ApiKeySaveRequest(BaseModel):
    pass

def _require_operator_auth():
    pass

def _validate_bybit_credentials():
    pass

def _credential_blockers_from_cutover_preflight(payload):
    pass

@settings_router.post("/api-key/{slot}")
async def save_api_key(slot, body, actor = Depends(_require_operator_auth)):
    _validate_bybit_credentials()
    _write_key_file(slot, "api_key", "k")
    _write_key_file(slot, "api_secret", "s")
    _write_key_file(slot, "bybit_endpoint", "demo")
"""


def _env_file(path: Path, *, mode: str = "read_only", write_enabled: str = "false") -> Path:
    return _write(
        path,
        "\n".join(
            [
                f"BYBIT_MODE={mode}",
                f"BYBIT_CONNECTOR_WRITE_ENABLED={write_enabled}",
                "BYBIT_CONNECTOR_HEALTH_STATE=healthy",
                "BYBIT_CONNECTOR_CONTRACT_VERSION=v1",
            ]
        ),
    )


def _build(tmp_path: Path, *, readiness: dict | None = None, settings_source: str | None = None) -> dict:
    readiness_path = _write_json(tmp_path / "readiness.json", readiness or _readiness())
    settings_path = _write(tmp_path / "settings_routes.py", settings_source or _settings_source())
    env_path = _env_file(tmp_path / "trading_services.env")
    return mod.build_bounded_demo_credential_mode_cutover_preflight(
        readiness_json=readiness_path,
        settings_routes_py=settings_path,
        connector_env_file=env_path,
        public_ipv4="79.117.10.224",
        now_utc=NOW,
    )


def test_builds_ready_no_mutation_cutover_preflight_for_expected_blockers(tmp_path: Path) -> None:
    packet = _build(tmp_path)

    assert packet["status"] == mod.READY_STATUS
    assert packet["profit_first_state_transition"] == "DONE_WITH_CONCERNS"
    assert packet["public_ipv4_for_bybit_api_allowlist"] == "79.117.10.224"
    assert packet["settings_api_source"]["requires_operator_role"] is True
    assert packet["settings_api_source"]["validates_with_bybit_before_secret_write"] is True
    assert packet["connector_env_cutover"]["diff_preview"]["BYBIT_MODE"] == {
        "current": "read_only",
        "proposed": "demo",
    }
    assert packet["answers"]["secret_write_performed"] is False
    assert packet["answers"]["env_mutation_performed"] is False
    assert packet["answers"]["order_capable_action_allowed_by_this_packet"] is False


def test_blocks_when_settings_route_source_is_missing_validation_or_write_path(tmp_path: Path) -> None:
    packet = _build(
        tmp_path,
        settings_source='@settings_router.post("/api-key/{slot}")\nclass ApiKeySaveRequest: pass\n',
    )

    assert packet["status"] == mod.SOURCE_BLOCKED_STATUS
    assert "bybit_validation_before_write" in packet["settings_api_source"]["missing_checks"]
    assert "api_secret_file_write" in packet["settings_api_source"]["missing_checks"]


def test_blocks_when_runtime_has_unexpected_engine_or_auth_blocker(tmp_path: Path) -> None:
    packet = _build(
        tmp_path,
        readiness=_readiness(
            blocking_reasons=[
                "engine_env:engine_env_OPENCLAW_ALLOW_MAINNET_not_0",
                "connector_mode:bybit_mode_not_demo",
            ]
        ),
    )

    assert packet["status"] == mod.RUNTIME_BLOCKED_STATUS
    assert packet["profit_first_state_transition"] == "BLOCKED_BY_RUNTIME"
    assert packet["readiness"]["unexpected_blocking_reasons"] == [
        "engine_env:engine_env_OPENCLAW_ALLOW_MAINNET_not_0"
    ]


def test_ready_runtime_reports_cutover_not_required(tmp_path: Path) -> None:
    packet = _build(
        tmp_path,
        readiness=_readiness(
            status="BOUNDED_DEMO_RUNTIME_READY_FOR_FINAL_WINDOW_GATES",
            blocking_reasons=[],
        ),
    )

    assert packet["status"] == mod.NOT_REQUIRED_STATUS
    assert packet["next_actions"] == [
        "rerun final-window BBO/Decision Lease/Guardian/Rust authority/GUI cap gates"
    ]


def test_packet_does_not_contain_secret_material(tmp_path: Path) -> None:
    packet = _build(tmp_path)
    rendered = json.dumps(packet, sort_keys=True)
    secret_value = "super-secret-test-value"

    assert secret_value not in rendered
    assert hashlib.sha256(secret_value.encode()).hexdigest() not in rendered
    assert "secret_write_performed" in rendered
    assert packet["answers"]["api_key_plaintext_accepted_by_this_packet"] is False
    assert packet["answers"]["api_secret_plaintext_accepted_by_this_packet"] is False
