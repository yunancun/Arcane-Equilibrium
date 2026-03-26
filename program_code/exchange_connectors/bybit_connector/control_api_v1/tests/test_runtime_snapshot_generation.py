from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from generate_runtime_snapshot import build_runtime_snapshot  # noqa: E402
from runtime_snapshot_contract import RuntimeSnapshotValidationError, validate_runtime_snapshot_payload  # noqa: E402


def test_generate_runtime_snapshot_from_fragments() -> None:
    runtime_status_payload = {
        "runtime_snapshot_id": "runtime:file:test-001",
        "runtime_snapshot_ts_ms": 1774486000000,
        "readonly_connector_name": "bybit_prod_readonly_main",
        "execution_connector_name": None,
        "rest_private_connection_state": "ready",
        "ws_private_connection_state": "ready",
        "runtime_connection_state": "healthy",
        "account_fact_completeness_state": "complete",
        "source_snapshot_completeness_state": "complete",
        "global_runtime_facts": {
            "system_mode_fact": "shadow_only",
            "execution_state_fact": "execution_disabled",
            "runtime_last_refresh_ts_ms": 1774486000000,
            "runtime_data_freshness_state": "fresh",
        },
    }
    product_family_facts_payload = {
        "spot": {
            "exchange_permission_fact": "readonly_visible",
            "account_permission_fact": "readonly_visible",
        },
        "perp_linear": {
            "exchange_permission_fact": "unavailable",
            "account_permission_fact": "unavailable",
        },
    }
    health_payload = {
        "gates": {
            "health_gates_overall_state": "passed",
        }
    }

    snapshot = build_runtime_snapshot(
        runtime_status_payload=runtime_status_payload,
        product_family_facts_payload=product_family_facts_payload,
        health_payload=health_payload,
        readonly_connector_name=None,
        execution_connector_name=None,
    )

    validate_runtime_snapshot_payload(snapshot)
    assert snapshot["runtime_snapshot_id"] == "runtime:file:test-001"
    assert snapshot["product_family_facts"]["perp_linear"]["exchange_permission_fact"] == "unavailable"
    assert snapshot["health_telemetry"]["gates"]["health_gates_overall_state"] == "passed"


def test_validate_runtime_snapshot_rejects_invalid_runtime_connection_state() -> None:
    payload = {
        "runtime_snapshot_id": "runtime:file:test-002",
        "runtime_snapshot_ts_ms": 1774486000000,
        "rest_private_connection_state": "ready",
        "ws_private_connection_state": "ready",
        "runtime_connection_state": "ready",
        "account_fact_completeness_state": "complete",
        "source_snapshot_completeness_state": "complete",
        "global_runtime_facts": {
            "system_mode_fact": "shadow_only",
            "execution_state_fact": "execution_disabled",
            "runtime_last_refresh_ts_ms": 1774486000000,
            "runtime_data_freshness_state": "fresh",
        },
        "product_family_facts": {
            "spot": {
                "exchange_permission_fact": "readonly_visible",
                "account_permission_fact": "readonly_visible",
            }
        },
    }

    try:
        validate_runtime_snapshot_payload(payload)
    except RuntimeSnapshotValidationError as exc:
        assert "runtime_connection_state invalid" in str(exc)
    else:
        raise AssertionError("expected RuntimeSnapshotValidationError")


def test_generated_snapshot_can_be_rendered_to_file() -> None:
    runtime_status_payload = {
        "runtime_snapshot_id": "runtime:file:test-003",
        "runtime_snapshot_ts_ms": 1774486000000,
        "rest_private_connection_state": "ready",
        "ws_private_connection_state": "ready",
        "runtime_connection_state": "healthy",
        "account_fact_completeness_state": "complete",
        "source_snapshot_completeness_state": "complete",
        "global_runtime_facts": {
            "system_mode_fact": "shadow_only",
            "execution_state_fact": "execution_disabled",
            "runtime_last_refresh_ts_ms": 1774486000000,
            "runtime_data_freshness_state": "fresh",
        },
    }
    product_family_facts_payload = {
        "spot": {
            "exchange_permission_fact": "readonly_visible",
            "account_permission_fact": "readonly_visible",
        }
    }

    snapshot = build_runtime_snapshot(
        runtime_status_payload=runtime_status_payload,
        product_family_facts_payload=product_family_facts_payload,
        health_payload=None,
        readonly_connector_name="bybit_prod_readonly_main",
        execution_connector_name=None,
    )
    validate_runtime_snapshot_payload(snapshot)

    tmp_dir = Path(tempfile.mkdtemp(prefix="runtime_snapshot_generation_"))
    target = tmp_dir / "runtime_snapshot.generated.json"
    target.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    reloaded = json.loads(target.read_text(encoding="utf-8"))
    assert reloaded["runtime_snapshot_id"] == "runtime:file:test-003"
