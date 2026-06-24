from __future__ import annotations

import datetime as dt
import json

from helper_scripts.cron.api_service_env_parity import (
    build_api_service_env_parity_packet,
    main,
    render_markdown,
)


def _runtime_like_snapshot() -> dict:
    return {
        "api_processes": [
            {
                "pid": 1859622,
                "ppid": "1",
                "cwd": (
                    "/home/ncyu/BybitOpenClaw/srv/program_code/"
                    "exchange_connectors/bybit_connector/control_api_v1"
                ),
                "exe": "/usr/bin/python3.12",
                "cmdline": (
                    ".venv/bin/python3 .venv/bin/uvicorn app.main:app "
                    "--host 100.91.109.86 --port 8000 --workers 4"
                ),
                "selected_env": {
                    "OPENCLAW_BASE_DIR": "/home/ncyu/BybitOpenClaw/srv",
                    "OPENCLAW_DATA_DIR": "/tmp/openclaw",
                    "OPENCLAW_DATABASE_URL_FILE": (
                        "/tmp/openclaw/runtime_secrets/openclaw_database_url"
                    ),
                    "OPENCLAW_IPC_SECRET_FILE": (
                        "/home/ncyu/BybitOpenClaw/secrets/environment_files/"
                        "ipc_secret.txt"
                    ),
                    "OPENCLAW_IPC_SOCKET": "/tmp/openclaw/engine.sock",
                    "OPENCLAW_LEASE_PYTHON_IPC_ENABLED": "1",
                    "OPENCLAW_LIVE_AUTH_SIGNING_KEY_FILE": (
                        "/home/ncyu/BybitOpenClaw/secrets/environment_files/"
                        "live_auth_signing_key.txt"
                    ),
                    "OPENCLAW_STRATEGY_TOGGLE_LIVE_MODE": "1",
                },
            }
        ],
        "systemd_cat": {
            "stdout": "\n".join(
                [
                    "# /home/ncyu/.config/systemd/user/openclaw-trading-api.service",
                    "[Service]",
                    (
                        "WorkingDirectory=/home/ncyu/BybitOpenClaw/srv/program_code/"
                        "exchange_connectors/bybit_connector/control_api_v1"
                    ),
                    (
                        "ExecStart=/home/ncyu/BybitOpenClaw/srv/program_code/"
                        "exchange_connectors/bybit_connector/control_api_v1/.venv/"
                        "bin/uvicorn app.main:app --host 0.0.0.0 --port 8000"
                    ),
                    "Environment=HOME=/home/ncyu",
                    "Environment=TMPDIR=/tmp",
                    "Environment=PATH=/usr/local/bin:/usr/bin:/bin",
                ]
            )
        },
        "systemd_show": {
            "stdout": "\n".join(
                [
                    "MainPID=0",
                    "ActiveState=inactive",
                    "SubState=dead",
                    "UnitFileState=disabled",
                ]
            )
        },
    }


def test_api_service_env_parity_detects_current_runtime_drift_shape() -> None:
    packet = build_api_service_env_parity_packet(
        combined_snapshot=_runtime_like_snapshot(),
        now_utc=dt.datetime(2026, 6, 24, 10, tzinfo=dt.timezone.utc),
    )
    finding_ids = {finding["id"] for finding in packet["findings"]}
    markdown = render_markdown(packet)

    assert packet["status"] == "API_SERVICE_ENV_PARITY_DRIFT"
    assert packet["answers"]["service_restart_performed"] is False
    assert packet["answers"]["runtime_mutation_performed"] is False
    assert packet["answers"]["probe_authority_granted"] is False
    assert packet["answers"]["order_authority_granted"] is False
    assert packet["answers"]["live_authority_granted"] is False
    assert "service_inactive_while_manual_process_present" in finding_ids
    assert "unsafe_unit_bind_host" in finding_ids
    assert "bind_host_mismatch" in finding_ids
    assert "worker_count_mismatch" in finding_ids
    assert "unit_missing_runtime_env_keys" in finding_ids
    assert packet["no_restart_patch_proposal"]["restart_allowed_by_this_packet"] is False
    assert packet["next_actions"] == [
        "draft_no_restart_systemd_unit_env_parity_patch",
        "e3_review_api_service_owner_parity_plan_before_restart",
        "keep_current_manual_uvicorn_owner_until_parity_acceptance",
    ]
    assert "API_SERVICE_ENV_PARITY_DRIFT" in markdown


def test_api_service_env_parity_clean_snapshot_is_source_only() -> None:
    snapshot = _runtime_like_snapshot()
    snapshot["systemd_cat"]["stdout"] = "\n".join(
        [
            "[Service]",
            (
                "WorkingDirectory=/home/ncyu/BybitOpenClaw/srv/program_code/"
                "exchange_connectors/bybit_connector/control_api_v1"
            ),
            (
                "ExecStart=/home/ncyu/BybitOpenClaw/srv/program_code/"
                "exchange_connectors/bybit_connector/control_api_v1/.venv/bin/"
                "uvicorn app.main:app --host 100.91.109.86 --port 8000 "
                "--workers 4"
            ),
            "Environment=OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv",
            "Environment=OPENCLAW_DATA_DIR=/tmp/openclaw",
            "Environment=OPENCLAW_DATABASE_URL_FILE=/tmp/dburl",
            "Environment=OPENCLAW_IPC_SECRET_FILE=/tmp/ipc_secret",
            "Environment=OPENCLAW_IPC_SOCKET=/tmp/openclaw/engine.sock",
            "Environment=OPENCLAW_LEASE_PYTHON_IPC_ENABLED=1",
            "Environment=OPENCLAW_LIVE_AUTH_SIGNING_KEY_FILE=/tmp/live_key",
            "Environment=OPENCLAW_STRATEGY_TOGGLE_LIVE_MODE=1",
        ]
    )
    snapshot["systemd_show"]["stdout"] = "\n".join(
        ["MainPID=1859622", "ActiveState=active", "SubState=running"]
    )

    packet = build_api_service_env_parity_packet(
        combined_snapshot=snapshot,
        now_utc=dt.datetime(2026, 6, 24, 10, tzinfo=dt.timezone.utc),
    )

    assert packet["status"] == "API_SERVICE_ENV_PARITY_CLEAN_SOURCE_ONLY"
    assert packet["answers"]["operator_action_required"] is False
    assert packet["findings"] == []
    assert packet["next_actions"] == ["no_service_restart_needed_from_this_packet"]


def test_api_service_env_parity_fails_closed_on_missing_evidence() -> None:
    packet = build_api_service_env_parity_packet(
        combined_snapshot={},
        now_utc=dt.datetime(2026, 6, 24, 10, tzinfo=dt.timezone.utc),
    )

    assert packet["status"] == "API_SERVICE_ENV_PARITY_EVIDENCE_INCOMPLETE"
    assert packet["answers"]["operator_action_required"] is True
    assert packet["evidence_gaps"] == [
        "process_snapshot_missing",
        "systemd_snapshot_missing",
    ]
    assert packet["answers"]["service_restart_performed"] is False


def test_api_service_env_parity_fails_closed_on_missing_process_env_evidence() -> None:
    snapshot = _runtime_like_snapshot()
    snapshot["systemd_cat"]["stdout"] = "\n".join(
        [
            "[Service]",
            (
                "WorkingDirectory=/home/ncyu/BybitOpenClaw/srv/program_code/"
                "exchange_connectors/bybit_connector/control_api_v1"
            ),
            (
                "ExecStart=/home/ncyu/BybitOpenClaw/srv/program_code/"
                "exchange_connectors/bybit_connector/control_api_v1/.venv/bin/"
                "uvicorn app.main:app --host 100.91.109.86 --port 8000 "
                "--workers 4"
            ),
            "Environment=OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv",
            "Environment=OPENCLAW_DATA_DIR=/tmp/openclaw",
            "Environment=OPENCLAW_DATABASE_URL_FILE=/tmp/dburl",
            "Environment=OPENCLAW_IPC_SECRET_FILE=/tmp/ipc_secret",
            "Environment=OPENCLAW_IPC_SOCKET=/tmp/openclaw/engine.sock",
            "Environment=OPENCLAW_LEASE_PYTHON_IPC_ENABLED=1",
            "Environment=OPENCLAW_LIVE_AUTH_SIGNING_KEY_FILE=/tmp/live_key",
            "Environment=OPENCLAW_STRATEGY_TOGGLE_LIVE_MODE=1",
        ]
    )
    snapshot["systemd_show"]["stdout"] = "\n".join(
        ["MainPID=1859622", "ActiveState=active", "SubState=running"]
    )
    del snapshot["api_processes"][0]["selected_env"]

    packet = build_api_service_env_parity_packet(
        combined_snapshot=snapshot,
        now_utc=dt.datetime(2026, 6, 24, 10, tzinfo=dt.timezone.utc),
    )

    assert packet["status"] == "API_SERVICE_ENV_PARITY_EVIDENCE_INCOMPLETE"
    assert packet["evidence_gaps"] == ["process_selected_env_snapshot_missing"]


def test_api_service_env_parity_rejects_authority_signal() -> None:
    snapshot = _runtime_like_snapshot()
    snapshot["operator_authorization_object_emitted"] = True

    packet = build_api_service_env_parity_packet(
        combined_snapshot=snapshot,
        now_utc=dt.datetime(2026, 6, 24, 10, tzinfo=dt.timezone.utc),
    )

    assert packet["status"] == "API_SERVICE_ENV_PARITY_BOUNDARY_VIOLATION"
    assert packet["answers"]["authority_boundary_violation_present"] is True
    assert packet["answers"]["service_restart_performed"] is False
    assert packet["authority_signal_path"] == (
        "process_snapshot.operator_authorization_object_emitted"
    )
    assert packet["next_actions"] == [
        "remove_authority_or_mutation_signals_from_supplied_snapshot"
    ]


def test_api_service_env_parity_rejects_env_and_service_mutation_signals() -> None:
    snapshot = _runtime_like_snapshot()
    snapshot["env_mutation_performed"] = True

    packet = build_api_service_env_parity_packet(
        combined_snapshot=snapshot,
        now_utc=dt.datetime(2026, 6, 24, 10, tzinfo=dt.timezone.utc),
    )

    assert packet["status"] == "API_SERVICE_ENV_PARITY_BOUNDARY_VIOLATION"
    assert packet["authority_signal_path"] == (
        "process_snapshot.env_mutation_performed"
    )

    snapshot = _runtime_like_snapshot()
    snapshot["nested"] = {"service_mutation_performed": True}
    packet = build_api_service_env_parity_packet(
        combined_snapshot=snapshot,
        now_utc=dt.datetime(2026, 6, 24, 10, tzinfo=dt.timezone.utc),
    )

    assert packet["status"] == "API_SERVICE_ENV_PARITY_BOUNDARY_VIOLATION"
    assert packet["authority_signal_path"] == (
        "process_snapshot.nested.service_mutation_performed"
    )


def test_api_service_env_parity_redacts_sensitive_cmdline_values() -> None:
    snapshot = _runtime_like_snapshot()
    snapshot["api_processes"][0]["cmdline"] = (
        "/usr/bin/env OPENCLAW_IPC_SECRET=supersecret .venv/bin/uvicorn "
        "app.main:app --host 100.91.109.86 --port 8000 --workers 4 "
        "--api-key alsosecret --ipc-secret unlistedsecret "
        "--client-key genericsecret --access-key=genericsecret2"
    )

    packet = build_api_service_env_parity_packet(
        combined_snapshot=snapshot,
        now_utc=dt.datetime(2026, 6, 24, 10, tzinfo=dt.timezone.utc),
    )
    encoded = json.dumps(packet, sort_keys=True)

    assert packet["manual_process"]["command"]["redaction_applied"] is True
    assert "supersecret" not in encoded
    assert "alsosecret" not in encoded
    assert "unlistedsecret" not in encoded
    assert "genericsecret" not in encoded
    assert "genericsecret2" not in encoded
    assert "OPENCLAW_IPC_SECRET=REDACTED" in encoded
    assert "--api-key" in encoded
    assert "--ipc-secret" in encoded
    assert "--client-key" in encoded
    assert "--access-key=REDACTED" in encoded


def test_api_service_env_parity_cli_writes_outputs(tmp_path, monkeypatch) -> None:
    snapshot_path = tmp_path / "snapshot.json"
    json_output = tmp_path / "packet.json"
    md_output = tmp_path / "packet.md"
    snapshot_path.write_text(json.dumps(_runtime_like_snapshot()) + "\n")
    monkeypatch.setattr(
        "sys.argv",
        [
            "api_service_env_parity.py",
            "--combined-snapshot-json",
            str(snapshot_path),
            "--json-output",
            str(json_output),
            "--output",
            str(md_output),
        ],
    )

    assert main() == 0
    packet = json.loads(json_output.read_text())
    markdown = md_output.read_text()

    assert packet["schema_version"] == "api_service_env_parity_packet_v1"
    assert packet["status"] == "API_SERVICE_ENV_PARITY_DRIFT"
    assert "API Service Env-Parity Packet" in markdown
