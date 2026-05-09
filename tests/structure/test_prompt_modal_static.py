from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
STATIC = REPO_ROOT / "program_code/exchange_connectors/bybit_connector/control_api_v1/app/static"


PROMPT_REPLACEMENT_TARGETS = (
    "app-learning.js",
    "governance-tab.js",
    "tab-governance.html",
)


def test_common_js_exposes_custom_prompt_modal() -> None:
    source = (STATIC / "common.js").read_text(encoding="utf-8")
    assert "function openPromptModal(options)" in source
    assert "oc-generic-prompt-overlay" in source
    assert "oc-prompt-select" in source
    assert "oc-prompt-textarea" in source


def test_learning_and_governance_do_not_use_native_prompt() -> None:
    for rel_path in PROMPT_REPLACEMENT_TARGETS:
        source = (STATIC / rel_path).read_text(encoding="utf-8")
        assert "prompt(" not in source, rel_path
        assert "openPromptModal(" in source, rel_path
