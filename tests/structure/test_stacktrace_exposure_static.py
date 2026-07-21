from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
APP = (
    ROOT
    / "program_code"
    / "exchange_connectors"
    / "bybit_connector"
    / "control_api_v1"
    / "app"
)
ALERT_SURFACE = (
    "db_pool.py",
    "earn_routes.py",
    "error_sanitize.py",
    "governance_autonomy_service.py",
    "governance_extended_routes.py",
    "layer2_routes.py",
    "paper_trading_routes.py",
    "phase4_routes.py",
    "pnl_series.py",
    "prelive_edge_gate_trends.py",
    "replay_quick_routes.py",
    "replay_routes.py",
    "settings_routes.py",
    "strategy_ai_routes.py",
    "strategy_read_routes.py",
    "system_legacy_routes.py",
)

RAW_LOG_PATTERNS = (
    re.compile(r"logger\.(?:exception|error|warning|debug)\([^\n]*(?:exc|\be\b)"),
    re.compile(r"logger\.(?:exception|error|warning|debug)\(f[\"'][^\n]*\{(?:exc|e)[!:.}]"),
    re.compile(r"exc_info\s*=\s*True"),
    re.compile(r"logger\.exception\("),
)
CLIENT_LEAK_PATTERNS = (
    re.compile(r"traceback\.(?:format_exc|format_exception)"),
    re.compile(r"errors?\.append\(f[\"'][^\n]*\{(?:exc|e)[!:.}]"),
    re.compile(
        r"[\"'](?:detail|error|message|reason)[\"']\s*:\s*"
        r"(?:str\((?:exc|e)\)|f[\"'][^\n]*\{(?:exc|e)[!:.}])"
    ),
    re.compile(
        r"[\"'](?:detail|error|message|reason)[\"']\s*:\s*"
        r"f[\"'][^\n]*type\((?:exc|e)\)"
    ),
)


def _findings(patterns: tuple[re.Pattern[str], ...]) -> list[str]:
    findings: list[str] = []
    for filename in ALERT_SURFACE:
        source = (APP / filename).read_text(encoding="utf-8")
        for pattern in patterns:
            for match in pattern.finditer(source):
                line = source.count("\n", 0, match.start()) + 1
                findings.append(f"{filename}:{line}:{pattern.pattern}")
    return findings


def test_stacktrace_alert_surface_has_no_raw_exception_client_fields() -> None:
    assert _findings(CLIENT_LEAK_PATTERNS) == []


def test_stacktrace_alert_surface_has_no_raw_exception_or_trace_logs() -> None:
    assert _findings(RAW_LOG_PATTERNS) == []


def test_error_sanitizer_has_no_debug_bypass() -> None:
    source = (APP / "error_sanitize.py").read_text(encoding="utf-8")
    assert "OPENCLAW_DEBUG" not in source
    assert "_DEBUG" not in source


def test_replay_signature_failure_values_are_fixed_allowlist_only() -> None:
    source = (APP / "replay_routes.py").read_text(encoding="utf-8")
    assert "_SAFE_SIGNATURE_FAIL_MODES" in source
    assert "_SAFE_SIGNATURE_FAIL_MODES.get(untrusted_mode" in source
    assert 'return "verification_failed"' in source
