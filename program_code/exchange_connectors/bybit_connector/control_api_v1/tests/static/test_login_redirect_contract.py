"""Static contract tests for GUI login redirects."""

from __future__ import annotations

from pathlib import Path


_STATIC_DIR = Path(__file__).resolve().parents[2] / "app" / "static"


def _read(name: str) -> str:
    path = _STATIC_DIR / name
    assert path.exists(), f"{name} not found at {path}"
    return path.read_text(encoding="utf-8")


def test_login_redirect_defaults_to_root_and_rejects_static_tabs() -> None:
    """Login must not replay iframe tab URLs after cookie expiry."""
    html = _read("login.html")

    assert "path.startsWith('/static/')" in html
    assert "return '/';" in html
    assert "safeRedirectTarget(sessionStorage.getItem(REDIRECT_KEY))" in html
    assert "||\n    '/';" in html


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
