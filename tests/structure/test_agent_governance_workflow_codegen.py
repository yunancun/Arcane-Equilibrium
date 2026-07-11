"""Drift and loader checks for generated standalone workflow Context blocks."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

from agent_governance_workflow_codegen import (  # noqa: E402
    BEGIN,
    SHADOW_RE,
    WORKFLOWS,
    render_context_admission_block,
    workflow_context_codegen_errors,
)


def _async_function_syntax(source: str) -> subprocess.CompletedProcess[str]:
    wrapper = (
        "const AsyncFunction=Object.getPrototypeOf(async function(){}).constructor;"
        "new AsyncFunction('args','phase','log','parallel','pipeline','agent',"
        + json.dumps(source.replace("export const meta =", "const meta ="))
        + ");"
    )
    return subprocess.run(
        ["node", "-e", wrapper], cwd=ROOT, text=True, capture_output=True,
        check=False,
    )


def test_context_codegen_block_is_exact_used_and_standalone_parseable() -> None:
    assert workflow_context_codegen_errors() == []
    expected = render_context_admission_block()
    for path in WORKFLOWS:
        source = path.read_text(encoding="utf-8")
        assert expected in source
        assert "+// BEGIN GENERATED" not in source
        assert source.count("contextPrefixV1(") >= 1
        assert _async_function_syntax(source).returncode == 0


def test_codegen_guards_have_negative_controls() -> None:
    assert SHADOW_RE.search("const budgetFields = []")
    source = WORKFLOWS[0].read_text(encoding="utf-8")
    leaked_patch_marker = source.replace(BEGIN, "+" + BEGIN, 1)
    assert _async_function_syntax(leaked_patch_marker).returncode != 0
