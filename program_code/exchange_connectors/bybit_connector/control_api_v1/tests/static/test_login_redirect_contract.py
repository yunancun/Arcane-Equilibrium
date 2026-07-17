"""Static contract tests for GUI login redirects."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

import pytest


_STATIC_DIR = Path(__file__).resolve().parents[2] / "app" / "static"


def _read(name: str) -> str:
    path = _STATIC_DIR / name
    assert path.exists(), f"{name} not found at {path}"
    return path.read_text(encoding="utf-8")


def _function(source: str, name: str) -> str:
    """Extract a plain JavaScript function so its production bytes can be executed."""
    start = source.index(f"function {name}(")
    opening = source.index("{", start)
    depth = 0
    quote = ""
    escaped = False
    for index in range(opening, len(source)):
        char = source[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
            continue
        if char in {"'", '"', "`"}:
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise AssertionError(f"unterminated JavaScript function: {name}")


@pytest.mark.skipif(shutil.which("node") is None, reason="node is required")
def test_login_redirect_defaults_to_root_and_rejects_static_tabs() -> None:
    """Login redirects are reconstructed from a fixed, closed route allowlist."""
    safe_redirect = _function(_read("login.html"), "safeRedirectTarget")
    cases = {
        "/": "/",
        "/gui": "/gui",
        "/console": "/console",
        "/console/legacy": "/console/legacy",
        "/trading": "/trading",
        "/trading?embed=1": "/trading?embed=1",
        "/trading?embed=0&next=//evil.example": "/trading",
        "/console?next=//evil.example": "/console",
        "/static/console.html": "/",
        "/static/settings.html?next=//evil.example": "/",
        "/%2f%2fevil.example/console": "/",
        "/%5cevil.example/console": "/",
        "/login": "/",
        "/not-an-allowed-route": "/",
        "https://evil.example/console": "",
        "//evil.example/console": "",
        "/\\evil.example/console": "",
    }
    script = f"""
const window = {{ location: {{ origin: 'https://console.example' }} }};
{safe_redirect}
const cases = {json.dumps(cases)};
for (const [input, expected] of Object.entries(cases)) {{
  const actual = safeRedirectTarget(input);
  if (actual !== expected) {{
    throw new Error(JSON.stringify({{ input, expected, actual }}));
  }}
}}
"""
    result = subprocess.run(
        ["node", "-e", script],
        cwd=_STATIC_DIR,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_common_auth_redirect_normalizes_static_iframe_path_to_root() -> None:
    """Iframe auth expiry should send the next login to the console entry root."""
    js = _read("common.js")

    assert "currentPath.startsWith('/static/') ? '/' : rawCurrent" in js
    assert "sessionStorage.setItem('oc_login_redirect', current)" in js


def test_console_build_version_is_not_appended_twice() -> None:
    """Tab iframe URLs may already carry v=BUILD_TS and must not get a second v."""
    html = _read("console.html")

    assert "function withBuildVersion(src)" in html
    assert "if (src.includes('v=')) return src;" in html
    assert "frame.dataset.src = frameSrc;" in html
    assert "t.src + sep + 'v=' + BUILD_TS" not in html
