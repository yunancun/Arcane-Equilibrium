from __future__ import annotations

import datetime as dt
import json
import os
import stat
import urllib.parse
from pathlib import Path

from cost_gate_learning_lane import demo_fast_balance_equity_artifact as mod
from cost_gate_learning_lane.current_cap_staircase_risk_worksheet import (
    READY_STATUS as WORKSHEET_READY_STATUS,
    build_current_cap_staircase_risk_worksheet,
)


NOW = dt.datetime(2026, 6, 27, 1, 5, tzinfo=dt.timezone.utc)


class FakeHTTPResponse:
    def __init__(self, payload=None, *, status=200):
        self._raw = json.dumps(payload).encode("utf-8")
        self._status = status

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def getcode(self):
        return self._status

    def read(self):
        return self._raw


class FakeOpener:
    def __init__(self, payload):
        self.payload = payload
        self.requests = []

    def __call__(self, req, timeout=None):
        self.requests.append(req)
        return FakeHTTPResponse(self.payload)


def _now() -> dt.datetime:
    return NOW


def _balance_payload(*, equity: float = 100.0, data_overrides=None, **overrides) -> dict:
    data = {
        "source": "rust_engine",
        "read_model": "rust_snapshot_fast",
        "pipeline_status": "connected",
        "totalEquity": equity,
        "total_equity": equity,
        "equity": equity,
        "balance": equity,
    }
    if data_overrides:
        data.update(data_overrides)
    payload = {
        "action_result": "success",
        "data": data,
        "is_simulated": True,
        "data_category": "paper_simulated",
    }
    payload.update(overrides)
    return payload


def _control_contract() -> dict:
    return {
        "schema_version": "cost_gate_source_only_control_identity_contract_v1",
        "status": "SOURCE_ONLY_CONTROL_IDENTITY_CONTRACT_READY_NO_AUTHORITY",
        "candidate": {
            "side_cell_key": "grid_trading|AVAXUSDT|Sell",
            "strategy_name": "grid_trading",
            "symbol": "AVAXUSDT",
            "side": "Sell",
            "outcome_horizon_minutes": 60,
        },
        "answers": {
            "bounded_demo_probe_authorized": False,
            "operator_authorization_object_emitted": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "cap_envelope_mutation_allowed": False,
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "promotion_evidence": False,
            "promotion_proof": False,
        },
    }


def _construction_preview() -> dict:
    return {
        "schema_version": "bounded_demo_probe_candidate_construction_preview_v1",
        "status": "CANDIDATE_CONSTRUCTION_BBO_STALE",
        "candidate": {
            "side_cell_key": "grid_trading|AVAXUSDT|Sell",
            "strategy_name": "grid_trading",
            "symbol": "AVAXUSDT",
            "side": "Sell",
            "outcome_horizon_minutes": 60,
        },
        "blocking_gates": ["bbo_freshness"],
        "construction": {
            "cap_usdt": 10.0,
            "constructible": True,
            "limit_price": 6.064,
            "min_notional": 5.0,
            "qty_step": 0.1,
            "reference_price": 6.063,
            "tick_size": 0.001,
        },
        "market_inputs": {
            "effective_bbo_age_ms": 4935.735,
            "instrument_status": "Trading",
            "max_fresh_bbo_age_ms": 1000.0,
        },
        "readiness": {"bbo_fresh": False},
        "answers": {
            "bybit_call_performed": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "order_authority_granted": False,
            "order_submission_performed": False,
            "pg_query_performed": False,
            "pg_write_performed": False,
            "probe_authority_granted": False,
            "promotion_evidence": False,
            "runtime_mutation_performed": False,
        },
    }


def _gui_risk_config() -> dict:
    return {
        "limits": {
            "per_trade_risk_pct": 0.1,
            "position_size_max_pct": 25.0,
            "total_exposure_max_pct": 150.0,
            "correlated_exposure_max_pct": 65.0,
            "max_order_notional_usdt": 0.0,
        }
    }


def _worksheet(artifact: dict) -> dict:
    return build_current_cap_staircase_risk_worksheet(
        control_identity_contract=_control_contract(),
        construction_preview=_construction_preview(),
        gui_risk_config=_gui_risk_config(),
        account_equity_artifact=artifact,
        now_utc=NOW,
    )


def test_valid_supplied_fast_balance_payload_builds_ready_artifact() -> None:
    artifact = mod.build_demo_account_equity_artifact(
        balance_payload=_balance_payload(equity=100.0),
        now_fn=_now,
    )

    assert artifact["schema_version"] == mod.SCHEMA_VERSION
    assert artifact["status"] == mod.READY_STATUS
    assert artifact["source_endpoint"] == mod.DEMO_FAST_BALANCE_ENDPOINT
    assert artifact["payload_checks"]["read_model"] == "rust_snapshot_fast"
    assert artifact["payload_checks"]["pipeline_status"] == "connected"
    assert artifact["equity"]["equity_usdt"] == 100.0
    assert artifact["payload_sha256"]
    assert artifact["artifact_self_hash_sha256"]
    assert artifact["answers"]["control_api_call_performed"] is False
    assert artifact["answers"]["bybit_call_performed"] is False
    assert artifact["answers"]["pg_query_performed"] is False
    assert artifact["answers"]["order_submission_performed"] is False


def test_generated_artifact_is_accepted_by_gui_risk_cap_resolver() -> None:
    artifact = mod.build_demo_account_equity_artifact(
        balance_payload=_balance_payload(equity=200.0),
        now_fn=_now,
    )

    packet = _worksheet(artifact)

    assert packet["status"] == WORKSHEET_READY_STATUS
    assert packet["cap_resolution"]["account_equity_artifact_accepted"] is True
    assert packet["cap_resolution"]["per_trade_risk_pct_display"] == 10.0
    assert packet["cap_resolution"]["account_equity_usdt"] == 200.0
    assert packet["cap_resolution"]["per_trade_budget_usdt"] == 20.0
    assert packet["risk_worksheet"]["per_order_cap_usdt"] == 20.0
    assert packet["cap_resolution"]["source_construction_cap_usdt"] == 10.0
    assert packet["cap_resolution"]["construction_cap_is_authority"] is False
    assert packet["cap_resolution"]["gui_risk_config_is_authority"] is True


def test_slow_or_disconnected_balance_payload_is_not_ready() -> None:
    artifact = mod.build_demo_account_equity_artifact(
        balance_payload=_balance_payload(
            data_overrides={
                "read_model": "bybit_rest",
                "pipeline_status": "disconnected",
            }
        ),
        now_fn=_now,
    )

    packet = _worksheet(artifact)

    assert artifact["status"] == mod.NOT_READY_STATUS
    assert "balance_data_read_model_not_rust_snapshot_fast" in artifact[
        "payload_checks"
    ]["blocking_reasons"]
    assert "balance_data_pipeline_status_not_connected" in artifact[
        "payload_checks"
    ]["blocking_reasons"]
    assert packet["account_equity_resolution"]["accepted"] is False
    assert "account_equity_artifact_status_not_ready" in packet["cap_resolution"][
        "blocking_reasons"
    ]


def test_runtime_diagnostics_accept_active_demo_snapshot_without_secret_values(tmp_path) -> None:
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    (runtime_dir / "pipeline_snapshot_demo.json").write_text(
        json.dumps(
            {
                "schema_version": "openclaw_pipeline_snapshot_v1",
                "source": "rust_engine",
                "trading_mode": "demo",
                "paper_state": {
                    "balance": 100.0,
                    "initial_balance": 100.0,
                    "peak_balance": 101.0,
                    "positions": {},
                },
            }
        ),
        encoding="utf-8",
    )
    secret_root = tmp_path / "secrets" / "bybit"
    demo_slot = secret_root / "demo"
    demo_slot.mkdir(parents=True)
    (demo_slot / "api_key").write_text("never-print-api-key", encoding="utf-8")
    (demo_slot / "api_secret").write_text("never-print-api-secret", encoding="utf-8")

    diagnostics = mod.build_runtime_diagnostics(
        runtime_data_dir=runtime_dir,
        bybit_secret_root=secret_root,
        now_fn=_now,
    )
    artifact = mod.build_demo_account_equity_artifact(
        balance_payload=_balance_payload(equity=100.0),
        now_fn=_now,
        runtime_diagnostics=diagnostics,
    )
    rendered = json.dumps(artifact, ensure_ascii=False, sort_keys=True)

    assert artifact["status"] == mod.READY_STATUS
    assert artifact["payload_checks"]["runtime_diagnostic_blocking_reasons"] == []
    assert artifact["runtime_diagnostics"]["snapshots"][
        "pipeline_snapshot_demo.json"
    ]["summary"]["paper_state_balance_present"] is True
    assert "never-print-api-key" not in rendered
    assert "never-print-api-secret" not in rendered
    assert artifact["runtime_diagnostics"]["answers"]["secret_values_read"] is False


def test_runtime_diagnostics_block_missing_snapshot_and_active_demo_slot(tmp_path) -> None:
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    secret_root = tmp_path / "secrets" / "bybit"
    disabled_slot = secret_root / "demo.dev_disabled_20260421"
    disabled_slot.mkdir(parents=True)
    (disabled_slot / "api_key").write_text("disabled-secret-value", encoding="utf-8")

    diagnostics = mod.build_runtime_diagnostics(
        runtime_data_dir=runtime_dir,
        bybit_secret_root=secret_root,
        now_fn=_now,
    )
    artifact = mod.build_demo_account_equity_artifact(
        balance_payload=_balance_payload(equity=100.0),
        now_fn=_now,
        runtime_diagnostics=diagnostics,
    )
    blockers = artifact["payload_checks"]["runtime_diagnostic_blocking_reasons"]
    rendered = json.dumps(artifact, ensure_ascii=False, sort_keys=True)

    assert artifact["status"] == mod.NOT_READY_STATUS
    assert artifact["reason"] == "demo_fast_balance_runtime_diagnostics_not_accepted"
    assert "demo_snapshot_missing" in blockers
    assert "active_demo_secret_slot_missing" in blockers
    assert "demo.dev_disabled_20260421" in artifact["runtime_diagnostics"][
        "bybit_secret_slots"
    ]["disabled_demo_slot_names"]
    assert "disabled-secret-value" not in rendered


def test_authority_contaminated_payload_fails_closed() -> None:
    artifact = mod.build_demo_account_equity_artifact(
        balance_payload=_balance_payload(
            data_overrides={"bybit_private_call_performed": True}
        ),
        now_fn=_now,
    )

    assert artifact["status"] == mod.AUTHORITY_BOUNDARY_VIOLATION_STATUS
    assert "bybit_private_call_performed_true" in artifact["payload_checks"][
        "blocking_reasons"
    ]
    assert artifact["answers"]["order_authority_granted"] is False


def test_capture_uses_only_approved_fast_balance_get_with_token_file(tmp_path) -> None:
    token_file = tmp_path / "api_token"
    token_file.write_text("secret-token\n", encoding="utf-8")
    token_file.chmod(stat.S_IRUSR | stat.S_IWUSR)
    opener = FakeOpener(_balance_payload(equity=125.0))

    artifact = mod.capture_demo_fast_balance_equity_artifact(
        api_base="http://127.0.0.1:8000",
        token_file=token_file,
        opener=opener,
        now_fn=_now,
    )

    assert artifact["status"] == mod.READY_STATUS
    assert artifact["source_transport"]["transport_status"] == "success"
    assert artifact["source_transport"]["authorization_header_used"] is True
    assert artifact["answers"]["control_api_call_performed"] is True
    assert artifact["answers"]["bybit_call_performed"] is False
    assert len(opener.requests) == 1
    req = opener.requests[0]
    parsed = urllib.parse.urlsplit(req.full_url)
    assert req.get_method() == "GET"
    assert parsed.scheme == "http"
    assert parsed.netloc == "127.0.0.1:8000"
    assert parsed.path == "/api/v1/strategy/demo/balance"
    assert parsed.query == "fast=1"
    assert req.headers["Authorization"] == "Bearer secret-token"


def test_capture_rejects_unapproved_api_base() -> None:
    artifact = mod.capture_demo_fast_balance_equity_artifact(
        api_base="https://api.bybit.com",
        opener=FakeOpener(_balance_payload()),
        now_fn=_now,
    )

    assert artifact["status"] == mod.SOURCE_FAILURE_STATUS
    assert artifact["source_transport"]["error_class"] == "ValueError"
    assert artifact["answers"]["control_api_call_performed"] is False
    assert artifact["answers"]["order_submission_performed"] is False


def test_token_file_must_not_be_group_or_world_readable(tmp_path) -> None:
    token_file = tmp_path / "api_token"
    token_file.write_text("secret-token\n", encoding="utf-8")
    token_file.chmod(0o644)

    artifact = mod.capture_demo_fast_balance_equity_artifact(
        api_base="http://127.0.0.1:8000",
        token_file=token_file,
        opener=FakeOpener(_balance_payload()),
        now_fn=_now,
    )

    assert artifact["status"] == mod.SOURCE_FAILURE_STATUS
    assert artifact["source_transport"]["error_class"] == "ValueError"


def test_cli_supplied_json_writes_ready_artifact(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(mod, "_utc_now", _now)
    source = tmp_path / "balance.json"
    out = tmp_path / "artifact.json"
    source.write_text(json.dumps(_balance_payload(equity=88.0)), encoding="utf-8")
    monkeypatch.setattr(
        "sys.argv",
        [
            "demo_fast_balance_equity_artifact.py",
            "--balance-response-json",
            str(source),
            "--json-output",
            str(out),
        ],
    )

    rc = mod.main()
    artifact = json.loads(out.read_text(encoding="utf-8"))

    assert rc == 0
    assert artifact["status"] == mod.READY_STATUS
    assert artifact["equity"]["equity_usdt"] == 88.0


def test_static_no_order_db_bybit_imports() -> None:
    source = Path(
        "helper_scripts/research/cost_gate_learning_lane/"
        "demo_fast_balance_equity_artifact.py"
    ).read_text(encoding="utf-8")

    forbidden = [
        "psycopg",
        "requests",
        "ccxt",
        "pybit",
        "subprocess",
        "create_order",
        "cancel_order",
        "place_order",
        "refresh_balance",
    ]
    for needle in forbidden:
        assert needle not in source
