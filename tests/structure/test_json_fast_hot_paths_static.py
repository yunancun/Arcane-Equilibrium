from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_python_ipc_hot_paths_use_json_fast() -> None:
    for rel_path in (
        "program_code/exchange_connectors/bybit_connector/control_api_v1/app/ai_service_listener.py",
        "program_code/exchange_connectors/bybit_connector/control_api_v1/app/ipc_client_sync.py",
    ):
        source = (REPO_ROOT / rel_path).read_text(encoding="utf-8")
        assert "from . import json_fast as json" in source, rel_path
        assert "\nimport json\n" not in source, rel_path
