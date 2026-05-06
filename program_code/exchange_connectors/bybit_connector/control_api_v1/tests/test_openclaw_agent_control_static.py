from __future__ import annotations

"""
MAG-018 static tests for the Agent Control frontend.

MODULE_NOTE (中文):
  鎖住 tab-agents.html 的 OpenClaw Agent Control foundation：只讀取 MAG-017
  backend view models，不新增按鈕、表單、write request、raw agent table 拼接。
"""

import re
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[1]
_STATIC = _ROOT / "app" / "static"
_TAB_AGENTS = _STATIC / "tab-agents.html"
_OPENCLAW_JS = _STATIC / "js" / "openclaw-agent-control.js"


def _strip_js_comments(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.DOTALL)
    src = re.sub(r"(^|\s)//.*", "", src)
    return src


def _openclaw_section(html: str) -> str:
    marker = '<section id="openclaw-agent-control"'
    start = html.index(marker)
    end = html.index("</section>", start) + len("</section>")
    return html[start:end]


def test_tab_agents_mounts_openclaw_control_surface() -> None:
    html = _TAB_AGENTS.read_text(encoding="utf-8")
    section = _openclaw_section(html)
    assert 'id="openclaw-control-status-chip"' in section
    assert 'id="openclaw-authority-panel"' in section
    assert 'id="openclaw-gateway-panel"' in section
    assert 'id="openclaw-topology-panel"' in section
    assert 'id="openclaw-blockers-panel"' in section
    assert "/static/js/openclaw-agent-control.js?v=20260506.mag018-v1" in html
    assert "startOpenClawAgentControl()" in html
    assert "/static/js/agent-tracker.js" in html


def test_openclaw_control_surface_has_no_manual_controls() -> None:
    section = _openclaw_section(_TAB_AGENTS.read_text(encoding="utf-8")).lower()
    assert "<button" not in section
    assert "<input" not in section
    assert "<select" not in section
    assert "<textarea" not in section
    assert "onclick=" not in section


def test_openclaw_agent_control_js_uses_only_readonly_allowlist() -> None:
    src = _strip_js_comments(_OPENCLAW_JS.read_text(encoding="utf-8"))
    endpoints = set(re.findall(r'_openclawApi\("([^"]+)"\)', src))
    assert endpoints == {
        "/api/v1/openclaw/status",
        "/api/v1/openclaw/self-state",
    }
    assert re.search(r"method:\s*[\"']GET[\"']", src)
    assert re.search(r"method:\s*[\"'](?:POST|PUT|PATCH|DELETE)[\"']", src) is None
    assert "ocPost(" not in src
    assert "fetch('/api" not in src
    assert 'fetch("/api' not in src


def test_openclaw_agent_control_sends_required_request_context_headers() -> None:
    src = _strip_js_comments(_OPENCLAW_JS.read_text(encoding="utf-8"))
    for header in (
        "x-openclaw-source",
        "x-openclaw-channel",
        "x-openclaw-sender",
        "x-openclaw-auth-profile",
        "x-openclaw-request-id",
    ):
        assert header in src


def test_openclaw_agent_control_does_not_join_raw_tables_or_forbidden_routes() -> None:
    src = _strip_js_comments(_OPENCLAW_JS.read_text(encoding="utf-8"))
    forbidden_fragments = (
        "agent.messages",
        "agent.state_changes",
        "agent.ai_invocations",
        "/api/v1/orders",
        "/api/v1/live/session",
        "/api/v1/settings/api-keys",
        "/api/v1/settings/secrets",
        "/api/v1/replay/handoff",
        "/api/v1/settings/development/status",
    )
    for fragment in forbidden_fragments:
        assert fragment not in src
