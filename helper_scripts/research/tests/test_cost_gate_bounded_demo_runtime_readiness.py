from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from cost_gate_learning_lane import bounded_demo_runtime_readiness as mod


NOW = dt.datetime(2026, 6, 29, 18, 0, tzinfo=dt.timezone.utc)
SIDE_CELL = "grid_trading|ETHUSDT|Buy"
EXPECTED_KEY = "demo-key-expected-test-001"
OTHER_KEY = "other-demo-key-test-002"
SECRET = "demo-secret-value"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _plan() -> dict:
    return {
        "schema_version": "cost_gate_demo_learning_lane_plan_v1",
        "generated_at_utc": "2026-06-29T17:54:12+00:00",
        "status": "READY_FOR_DEMO_LEARNING_PROBE",
        "gate_status": "OPERATOR_REVIEW",
        "operator_authorization": {"authorization_id": "standing-demo-test"},
        "order_authority": "ORDER_AUTHORITY_GRANTED",
        "probe_candidates": [
            {
                "side_cell_key": SIDE_CELL,
                "strategy_name": "grid_trading",
                "symbol": "ETHUSDT",
                "side": "Buy",
                "outcome_horizon_minutes": 60,
            }
        ],
    }


def _standing_auth(**overrides) -> dict:
    payload = {
        "schema_version": "standing_demo_operator_authorization_v1",
        "status": "STANDING_DEMO_AUTHORIZATION_ACTIVE",
        "standing_authorization_id": "standing-demo-test",
        "operator_id": "codex-standing-demo-operator",
        "demo_only": True,
        "environment": "demo",
        "scope": "demo_api_only_bounded_probe",
        "expires_at_utc": "2026-06-30T05:49:47+00:00",
        "candidate": {
            "side_cell_key": SIDE_CELL,
            "strategy_name": "grid_trading",
            "symbol": "ETHUSDT",
            "side": "Buy",
            "outcome_horizon_minutes": 60,
        },
    }
    payload.update(overrides)
    return payload


def _engine_env(plan_path: Path) -> bytes:
    values = {
        "OPENCLAW_ALLOW_MAINNET": "0",
        "OPENCLAW_ENABLE_PAPER": "0",
        "OPENCLAW_DEMO_LEARNING_LANE_WRITER": "1",
        "OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED": "1",
        "OPENCLAW_DEMO_LEARNING_LANE_PLAN": str(plan_path),
    }
    return b"\0".join(f"{key}={value}".encode() for key, value in values.items())


def _fixture(
    tmp_path: Path,
    *,
    api_key: str = EXPECTED_KEY,
    connector_mode: str = "demo",
    write_enabled: str = "true",
    standing_auth: dict | None = None,
) -> dict[str, Path]:
    secrets_dir = tmp_path / "secrets" / "secret_files" / "bybit"
    _write(secrets_dir / "demo" / "api_key", api_key)
    _write(secrets_dir / "demo" / "api_secret", SECRET)
    _write(secrets_dir / "demo" / "bybit_endpoint", "demo")
    connector_env = tmp_path / "environment_files" / "trading_services.env"
    _write(
        connector_env,
        "\n".join(
            [
                f"BYBIT_MODE={connector_mode}",
                f"BYBIT_CONNECTOR_WRITE_ENABLED={write_enabled}",
                "BYBIT_CONNECTOR_HEALTH_STATE=healthy",
                "BYBIT_CONNECTOR_CONTRACT_VERSION=v1",
            ]
        ),
    )
    plan = tmp_path / "bounded_demo_probe_soak_plan.json"
    auth = tmp_path / "standing_demo_operator_authorization.json"
    engine_env = tmp_path / "engine_environ"
    _write_json(plan, _plan())
    _write_json(auth, standing_auth or _standing_auth())
    engine_env.write_bytes(_engine_env(plan))
    return {
        "secrets_dir": secrets_dir,
        "connector_env": connector_env,
        "plan": plan,
        "auth": auth,
        "engine_env": engine_env,
    }


def _build(tmp_path: Path, **overrides) -> dict:
    paths = _fixture(tmp_path, **overrides.pop("fixture_overrides", {}))
    return mod.build_bounded_demo_runtime_readiness(
        secrets_dir=paths["secrets_dir"],
        connector_env_file=paths["connector_env"],
        plan_json=paths["plan"],
        standing_auth_json=paths["auth"],
        candidate_side_cell_key=SIDE_CELL,
        expected_demo_api_key_sha256=mod._sha256_text(EXPECTED_KEY),
        engine_environ_file=paths["engine_env"],
        require_engine_env=True,
        now_utc=NOW,
        **overrides,
    )


def test_expected_key_mismatch_is_advisory_unless_strict_and_read_only_mode_blocks(
    tmp_path: Path,
) -> None:
    packet = _build(
        tmp_path,
        fixture_overrides={
            "api_key": OTHER_KEY,
            "connector_mode": "read_only",
            "write_enabled": "false",
        },
    )

    assert packet["status"] == mod.BLOCKED_BY_CONNECTOR_MODE_STATUS
    assert packet["profit_first_state_transition"] == "BLOCKED_BY_RUNTIME"
    assert (
        packet["checks"]["demo_api_slot"]["api_key"]["expected_key_matches_observed"]
        is False
    )
    assert packet["checks"]["demo_api_slot"]["ready"] is True
    assert "demo_api_key_expected_value_mismatch" in packet["checks"][
        "demo_api_slot"
    ]["advisory_reasons"]
    assert "demo_api_slot:demo_api_key_expected_value_mismatch" not in packet[
        "blocking_reasons"
    ]
    assert "connector_mode:bybit_mode_not_demo" in packet["blocking_reasons"]
    assert "connector_mode:bybit_connector_write_not_enabled" in packet[
        "blocking_reasons"
    ]
    assert packet["answers"]["expected_demo_api_key_match_required"] is False


def test_strict_expected_key_mismatch_blocks_credentials(tmp_path: Path) -> None:
    packet = _build(
        tmp_path,
        fixture_overrides={"api_key": OTHER_KEY},
        require_expected_demo_api_key_match=True,
    )

    assert packet["status"] == mod.BLOCKED_BY_CREDENTIALS_STATUS
    assert (
        packet["checks"]["demo_api_slot"]["api_key"]["expected_key_matches_observed"]
        is False
    )
    assert packet["checks"]["demo_api_slot"]["api_key"][
        "expected_key_match_required"
    ] is True
    assert "demo_api_slot:demo_api_key_expected_value_mismatch" in packet[
        "blocking_reasons"
    ]
    assert packet["answers"]["expected_demo_api_key_match_required"] is True


def test_blocks_on_connector_mode_after_credentials_match(tmp_path: Path) -> None:
    packet = _build(
        tmp_path,
        fixture_overrides={"connector_mode": "read_only", "write_enabled": "false"},
    )

    assert packet["status"] == mod.BLOCKED_BY_CONNECTOR_MODE_STATUS
    assert (
        packet["checks"]["demo_api_slot"]["api_key"]["expected_sha256_match"] is True
    )
    assert packet["checks"]["connector_mode"]["write_enabled"] is False
    assert packet["answers"]["order_capable_action_allowed_by_this_packet"] is False


def test_ready_still_grants_no_order_or_runtime_authority(tmp_path: Path) -> None:
    packet = _build(tmp_path)

    assert packet["status"] == mod.READY_STATUS
    assert packet["profit_first_state_transition"] == "DONE_WITH_CONCERNS"
    assert packet["answers"]["bounded_demo_final_window_prerequisites_ready"] is True
    assert packet["answers"]["order_capable_action_allowed_by_this_packet"] is False
    assert packet["answers"]["decision_lease_acquire_performed"] is False
    assert packet["answers"]["order_submission_performed"] is False
    assert packet["answers"]["global_cost_gate_lowering_recommended"] is False


def test_expired_standing_auth_blocks_even_with_ready_slot_and_mode(tmp_path: Path) -> None:
    packet = _build(
        tmp_path,
        fixture_overrides={
            "standing_auth": _standing_auth(
                expires_at_utc="2026-06-29T17:00:00+00:00"
            )
        },
    )

    assert packet["status"] == mod.BLOCKED_BY_AUTH_OR_PLAN_STATUS
    assert "standing_authorization:standing_auth_expired" in packet[
        "blocking_reasons"
    ]


def test_output_omits_secret_value_and_secret_hash(tmp_path: Path) -> None:
    packet = _build(tmp_path)
    text = json.dumps(packet, sort_keys=True)

    assert SECRET not in text
    assert mod._sha256_text(SECRET)[:12] not in text
    assert packet["checks"]["demo_api_slot"]["api_secret"]["value_omitted"] is True
    assert "api_secret" in packet["checks"]["demo_api_slot"]
