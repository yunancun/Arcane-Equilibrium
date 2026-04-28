from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[5]


def _load_flatten_module():
    path = REPO_ROOT / "helper_scripts" / "clean_restart_flatten.py"
    spec = importlib.util.spec_from_file_location("clean_restart_flatten_for_test", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_clean_restart_flatten_refuses_mainnet_writes(monkeypatch):
    module = _load_flatten_module()
    monkeypatch.setattr(
        sys,
        "argv",
        ["clean_restart_flatten.py", "--env", "mainnet", "--yes"],
    )

    assert module.main() == 7


def test_restart_wrappers_do_not_invoke_mainnet_flatten():
    clean_restart = (REPO_ROOT / "helper_scripts" / "clean_restart.sh").read_text()
    fresh_start = (REPO_ROOT / "helper_scripts" / "fresh_start.sh").read_text()

    assert "clean_restart_flatten.py \\\n                --env mainnet" not in clean_restart
    assert "clean_restart_flatten.py --env mainnet" not in fresh_start
    assert "direct mainnet REST flatten is disabled" in clean_restart
    assert "direct mainnet REST flatten is disabled" in fresh_start
