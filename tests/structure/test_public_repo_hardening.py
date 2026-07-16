from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CONTROL_API = (
    ROOT
    / "program_code"
    / "exchange_connectors"
    / "bybit_connector"
    / "control_api_v1"
)
APP = CONTROL_API / "app"
MONITORING = ROOT / "docker_projects" / "monitoring_services"
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"

EXPECTED_ACTION_PINS = {
    "actions/checkout": (
        "34e114876b0b11c390a56381ad16ebd13914f8d5",
        "v4",
    ),
    "actions/setup-python": (
        "a26af69be951a213d495a4c3e4e4022e16d87065",
        "v5",
    ),
    "Swatinem/rust-cache": (
        "e18b497796c12c097a38f9edb9d0641fb99eee32",
        "v2",
    ),
}
COMPROMISED_SECRET_DIGESTS = {
    "4d086b0fa6456a0716bf7e65c4339452ca3a3e7548a2c490ea2f0d697731cf75",
    "5ce8f424042afd24345aa12ab2ca2f3ee409164f72d5c425d801a1779e4e6a84",
    "a07e30fc5f44656f5c042bed97d28339becdc9b9e8afe8895c323a6b620819a0",
}
COMPROMISED_SECRET_LENGTHS = (12, 22, 43)
PRINTABLE_TOKEN = re.compile(r"[A-Za-z0-9!#$%&()*+./:=?@^_~-]{12,128}")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_external_gateway_and_grafana_backend_surfaces_are_retired() -> None:
    main = _read(APP / "main.py")
    legacy = _read(APP / "main_legacy.py")
    system_routes = _read(APP / "system_legacy_routes.py")
    wiring = _read(APP / "strategy_wiring.py")
    restart = _read(ROOT / "helper_scripts" / "restart_all.sh")
    preflight = _read(ROOT / "helper_scripts" / "deploy" / "launchd_preflight.sh")

    assert "/openclaw/{path:path}" not in main
    assert "OPENCLAW_GATEWAY_HOST" not in main
    assert "openclaw_proxy" not in main
    assert "http://trade-core:3000" not in legacy
    assert "/system/grafana-health" not in system_routes
    assert "GrafanaDataWriter" not in wiring
    assert "GRAFANA_WRITER" not in wiring
    assert "trading_grafana" not in restart
    assert "ensure_docker_network" not in restart
    assert "com.openclaw.gateway.plist" not in preflight
    assert not (APP / "grafana_data_writer.py").exists()
    assert not (
        ROOT / "helper_scripts" / "deploy" / "com.openclaw.gateway.plist"
    ).exists()


def test_external_gateway_and_grafana_frontend_surfaces_are_retired() -> None:
    static = APP / "static"
    monitoring = _read(static / "tab-monitoring.html") + _read(
        static / "view-monitor.js"
    )
    agents = (
        _read(static / "tab-agents.html")
        + _read(static / "js" / "openclaw-agent-control.js")
        + _read(static / "view-agents-openclaw.js")
    )
    served_shells = _read(static / "login.html") + _read(static / "console.html")

    for retired_fragment in (
        "grafana-health",
        "trade-core:3000",
        "/openclaw/health",
    ):
        assert retired_fragment not in monitoring
    for retired_fragment in (
        "openclaw-gateway-panel",
        "renderGateway",
        "Gateway / Channel Posture",
    ):
        assert retired_fragment not in agents
    for retired_fragment in (
        "OpenClaw Gateway",
        "gw-link",
        "window.location.origin + '/openclaw'",
        "OC + '/health'",
        'id="s-oc"',
    ):
        assert retired_fragment not in served_shells


def test_canonical_docs_do_not_advertise_retired_external_services() -> None:
    canonical_docs = "\n".join(
        _read(path)
        for path in (
            ROOT / "README.md",
            ROOT / "CONTEXT.md",
            ROOT / "CLAUDE.md",
            ROOT / "memory" / "reference_remote_access.md",
        )
    )

    for retired_fragment in (
        "http://trade-core:3000",
        "trade-core.tail358794.ts.net",
        "openclaw-gateway.service",
        "--port 18789",
        "systemctl --user status openclaw-gateway",
        "grafana_data_writer.py",
        "OpenClaw Gateway → `/api/v1/openclaw/*`",
    ):
        assert retired_fragment not in canonical_docs


def test_local_openclaw_control_plane_and_bootstrap_schema_are_preserved() -> None:
    main = _read(APP / "main.py")
    routes = _read(APP / "openclaw_routes.py")
    contracts = _read(APP / "openclaw_authority_contracts.py")
    schema = MONITORING / "init_trading_schema.sql"

    assert "from .openclaw_routes import openclaw_router" in main
    assert "app.include_router(openclaw_router)" in main
    assert 'prefix="/api/v1/openclaw"' in routes
    assert "OPENCLAW_READ_ONLY_ROUTES" in contracts
    assert schema.is_file()
    assert schema.stat().st_size > 0
    assert {path.name for path in MONITORING.rglob("*") if path.is_file()} == {
        "init_trading_schema.sql"
    }


def test_all_github_actions_are_pinned_to_expected_full_shas() -> None:
    uses_lines = [
        line.strip()
        for line in _read(WORKFLOW).splitlines()
        if re.match(r"-?\s*uses:", line.strip())
    ]
    assert uses_lines

    seen: set[str] = set()
    for line in uses_lines:
        match = re.fullmatch(
            r"-?\s*uses:\s+([^@\s]+)@([0-9a-f]{40})\s+#\s+(v[0-9]+)",
            line,
        )
        assert match is not None, f"Action is not full-SHA pinned: {line}"
        action, sha, version = match.groups()
        assert action in EXPECTED_ACTION_PINS, f"Unreviewed action dependency: {action}"
        assert (sha, version) == EXPECTED_ACTION_PINS[action]
        seen.add(action)

    assert seen == set(EXPECTED_ACTION_PINS)


def _tracked_text_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-co", "--exclude-standard", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    paths: list[Path] = []
    for raw_path in result.stdout.split(b"\0"):
        if not raw_path:
            continue
        path = ROOT / raw_path.decode("utf-8")
        if path.is_file() and path.stat().st_size <= 2_000_000:
            paths.append(path)
    return paths


def test_confirmed_compromised_secret_values_are_absent_without_embedding_them() -> None:
    for path in _tracked_text_files():
        payload = path.read_bytes()
        if b"\0" in payload:
            continue
        text = payload.decode("utf-8", errors="ignore")
        for match in PRINTABLE_TOKEN.finditer(text):
            token = match.group(0)
            for length in COMPROMISED_SECRET_LENGTHS:
                if len(token) < length:
                    continue
                for start in range(len(token) - length + 1):
                    candidate = token[start : start + length]
                    digest = hashlib.sha256(candidate.encode("utf-8")).hexdigest()
                    assert digest not in COMPROMISED_SECRET_DIGESTS, (
                        "Confirmed compromised credential remains in "
                        f"{path.relative_to(ROOT)} (digest={digest[:12]}...)"
                    )
