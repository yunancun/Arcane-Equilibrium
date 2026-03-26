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
from runtime_snapshot_providers import DirectoryFragmentProvider  # noqa: E402


def test_directory_fragment_provider_loads_required_and_optional_files() -> None:
    tmp_dir = Path(tempfile.mkdtemp(prefix="runtime_fragments_dir_"))
    (tmp_dir / "runtime_status.json").write_text(
        json.dumps(
            {
                "runtime_snapshot_id": "runtime:dir-test:001",
                "runtime_snapshot_ts_ms": 1774487000000,
                "rest_private_connection_state": "ready",
                "ws_private_connection_state": "ready",
                "runtime_connection_state": "healthy",
                "account_fact_completeness_state": "complete",
                "source_snapshot_completeness_state": "complete",
                "global_runtime_facts": {
                    "system_mode_fact": "shadow_only",
                    "execution_state_fact": "execution_disabled",
                    "runtime_last_refresh_ts_ms": 1774487000000,
                    "runtime_data_freshness_state": "fresh",
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (tmp_dir / "product_family_facts.json").write_text(
        json.dumps(
            {
                "spot": {
                    "exchange_permission_fact": "readonly_visible",
                    "account_permission_fact": "readonly_visible",
                },
                "perp_linear": {
                    "exchange_permission_fact": "unavailable",
                    "account_permission_fact": "unavailable",
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (tmp_dir / "health_telemetry.json").write_text(
        json.dumps({"gates": {"health_gates_overall_state": "passed"}}, ensure_ascii=False),
        encoding="utf-8",
    )

    fragments = DirectoryFragmentProvider(tmp_dir).load_fragments()
    assert fragments.runtime_status_payload["runtime_snapshot_id"] == "runtime:dir-test:001"
    assert fragments.product_family_facts_payload["perp_linear"]["exchange_permission_fact"] == "unavailable"
    assert fragments.health_payload["gates"]["health_gates_overall_state"] == "passed"


def test_directory_fragment_provider_requires_runtime_status_and_product_family_files() -> None:
    tmp_dir = Path(tempfile.mkdtemp(prefix="runtime_fragments_missing_"))
    try:
        DirectoryFragmentProvider(tmp_dir).load_fragments()
    except RuntimeSnapshotValidationError as exc:
        assert "required fragment file missing" in str(exc)
    else:
        raise AssertionError("expected RuntimeSnapshotValidationError")


def test_build_runtime_snapshot_from_directory_provider_fragments() -> None:
    tmp_dir = Path(tempfile.mkdtemp(prefix="runtime_fragments_build_"))
    (tmp_dir / "runtime_status.json").write_text(
        json.dumps(
            {
                "runtime_snapshot_id": "runtime:dir-build:001",
                "runtime_snapshot_ts_ms": 1774487000000,
                "readonly_connector_name": "bybit_prod_readonly_main",
                "rest_private_connection_state": "ready",
                "ws_private_connection_state": "ready",
                "runtime_connection_state": "healthy",
                "account_fact_completeness_state": "complete",
                "source_snapshot_completeness_state": "complete",
                "global_runtime_facts": {
                    "system_mode_fact": "shadow_only",
                    "execution_state_fact": "execution_disabled",
                    "runtime_last_refresh_ts_ms": 1774487000000,
                    "runtime_data_freshness_state": "fresh",
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (tmp_dir / "product_family_facts.json").write_text(
        json.dumps(
            {
                "spot": {
                    "exchange_permission_fact": "readonly_visible",
                    "account_permission_fact": "readonly_visible",
                },
                "margin": {
                    "exchange_permission_fact": "readonly_visible",
                    "account_permission_fact": "readonly_visible",
                },
                "perp_linear": {
                    "exchange_permission_fact": "unavailable",
                    "account_permission_fact": "unavailable",
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    fragments = DirectoryFragmentProvider(tmp_dir).load_fragments()
    snapshot = build_runtime_snapshot(
        runtime_status_payload=fragments.runtime_status_payload,
        product_family_facts_payload=fragments.product_family_facts_payload,
        health_payload=fragments.health_payload,
        readonly_connector_name=None,
        execution_connector_name=None,
    )
    validate_runtime_snapshot_payload(snapshot)
    assert snapshot["runtime_snapshot_id"] == "runtime:dir-build:001"
    assert snapshot["product_family_facts"]["perp_linear"]["account_permission_fact"] == "unavailable"
