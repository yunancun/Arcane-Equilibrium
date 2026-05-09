from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]

STATE_SNAPSHOT_MODULES = (
    "program_code/exchange_connectors/bybit_connector/control_api_v1/app/state_machine_base.py",
    "program_code/exchange_connectors/bybit_connector/control_api_v1/app/authorization_state_machine.py",
    "program_code/exchange_connectors/bybit_connector/control_api_v1/app/decision_lease_state_machine.py",
    "program_code/exchange_connectors/bybit_connector/control_api_v1/app/risk_governor_state_machine.py",
    "program_code/exchange_connectors/bybit_connector/control_api_v1/app/learning_tier_gate.py",
)


def test_state_machine_snapshots_do_not_use_generic_deepcopy() -> None:
    for rel_path in STATE_SNAPSHOT_MODULES:
        source = (REPO_ROOT / rel_path).read_text(encoding="utf-8")
        assert "\nimport copy\n" not in source, rel_path
        assert "copy.deepcopy" not in source, rel_path
        assert "from copy import deepcopy" not in source, rel_path
