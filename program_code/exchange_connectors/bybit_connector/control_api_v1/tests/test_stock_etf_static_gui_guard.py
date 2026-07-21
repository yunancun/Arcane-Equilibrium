from __future__ import annotations

import re

from stock_etf_static_guard_helpers import (
    CONTROL_API_DIR,
    FORBIDDEN_IPC_METHOD_STRINGS,
    FORBIDDEN_STATIC_GUI_BACKGROUND_SNIPPETS,
    FORBIDDEN_STATIC_GUI_SNIPPETS,
    STOCK_ETF_STATIC_GUI_AUTH_ACCOUNT_RENDERERS,
    STOCK_ETF_STATIC_GUI_DATA_POLICY_RENDERERS,
    STOCK_ETF_STATIC_GUI_EVIDENCE_PAPER_RENDERERS,
    STOCK_ETF_STATIC_GUI_FALLBACK_BUILDERS,
    STOCK_ETF_STATIC_GUI_ONE_SHOT_GET_FANOUT,
    STOCK_ETF_STATIC_GUI_READINESS_RENDERER,
    STOCK_ETF_STATIC_GUI_SCORECARD_LAUNCH_RENDERERS,
    STOCK_ETF_STATIC_GUI_TIMEOUT_MS,
    candidate_stock_etf_static_gui_files,
    stock_etf_gui_lane_template_endpoints,
)

MAX_FILE_LINES = 2_000


def test_stock_etf_static_gui_endpoint_set_matches_gui_lane_contract_template() -> None:
    files = candidate_stock_etf_static_gui_files()
    assert files, "expected Stock/ETF static GUI surface"

    combined_source = "\n".join(path.read_text(encoding="utf-8") for path in files)
    gui_endpoints = set(
        re.findall(r"/api/v1/stock-etf(?:/[a-z0-9-]+)?", combined_source)
    )

    assert gui_endpoints == stock_etf_gui_lane_template_endpoints()


def test_stock_etf_static_gui_surface_remains_display_only() -> None:
    files = candidate_stock_etf_static_gui_files()
    assert files, "expected Stock/ETF static GUI surface"

    violations: list[str] = []
    forbidden_snippets = FORBIDDEN_STATIC_GUI_SNIPPETS | FORBIDDEN_IPC_METHOD_STRINGS
    sources = {path: path.read_text(encoding="utf-8") for path in files}
    combined_source = "\n".join(sources.values())
    endpoint_requirements = {
        "/api/v1/stock-etf/account-status": "account-status",
        "/api/v1/stock-etf/authorization-status": "authorization-status",
        "/api/v1/stock-etf/data-foundation-status": "data-foundation-status",
        "/api/v1/stock-etf/disable-cleanup-status": "disable-cleanup-status",
        "/api/v1/stock-etf/evidence-status": "evidence-status",
        "/api/v1/stock-etf/lane-status": "lane-status",
        "/api/v1/stock-etf/launch-status": "launch-status",
        "/api/v1/stock-etf/paper-status": "paper-status",
        "/api/v1/stock-etf/phase0-status": "phase0-status",
        "/api/v1/stock-etf/policy-status": "policy-status",
        "/api/v1/stock-etf/readiness": "readiness",
        "/api/v1/stock-etf/reconciliation-status": "reconciliation-status",
        "/api/v1/stock-etf/release-packet-status": "release-packet-status",
        "/api/v1/stock-etf/scorecard-status": "scorecard-status",
        "/api/v1/stock-etf/shadow-status": "shadow-status",
        "/api/v1/stock-etf/universe-status": "universe-status",
    }
    for endpoint, label in endpoint_requirements.items():
        if endpoint not in combined_source:
            violations.append(
                f"Stock/ETF static GUI bundle: missing read-only Stock/ETF {label} endpoint"
            )
    for path in files:
        source = sources[path]
        for snippet in sorted(forbidden_snippets):
            if snippet in source:
                violations.append(f"{path}: contains forbidden display-only snippet {snippet!r}")

    assert violations == []


def test_stock_etf_static_gui_has_no_background_polling_or_push_channels() -> None:
    files = candidate_stock_etf_static_gui_files()
    assert files, "expected Stock/ETF static GUI surface"

    violations: list[str] = []
    for path in files:
        source = path.read_text(encoding="utf-8")
        for snippet in sorted(FORBIDDEN_STATIC_GUI_BACKGROUND_SNIPPETS):
            if snippet in source:
                violations.append(f"{path}: contains forbidden background work snippet {snippet!r}")

    assert violations == []


def test_stock_etf_static_gui_one_shot_get_fanout_stays_bounded() -> None:
    static_dir = CONTROL_API_DIR / "app" / "static"
    main_source = (static_dir / "tab-stock-etf.js").read_text(encoding="utf-8")

    assert main_source.count("Promise.all(") == 1
    assert main_source.count("waitForServerUp(loadReadiness)") == 1
    assert main_source.count("ocApi(") == STOCK_ETF_STATIC_GUI_ONE_SHOT_GET_FANOUT
    assert main_source.count("method: 'GET'") == STOCK_ETF_STATIC_GUI_ONE_SHOT_GET_FANOUT
    assert main_source.count("toastOnError: false") == STOCK_ETF_STATIC_GUI_ONE_SHOT_GET_FANOUT
    assert (
        main_source.count(f"timeoutMs: {STOCK_ETF_STATIC_GUI_TIMEOUT_MS}")
        == STOCK_ETF_STATIC_GUI_ONE_SHOT_GET_FANOUT
    )


def test_stock_etf_static_gui_files_stay_below_line_cap() -> None:
    files = candidate_stock_etf_static_gui_files()
    assert files, "expected Stock/ETF static GUI surface"

    oversized = []
    for path in files:
        line_count = len(path.read_text(encoding="utf-8").splitlines())
        if line_count > 2000:
            oversized.append(f"{path}:{line_count}")

    assert oversized == []


def test_stock_etf_static_gui_payload_builders_remain_split() -> None:
    static_dir = CONTROL_API_DIR / "app" / "static"
    main_path = static_dir / "tab-stock-etf.js"
    fallback_path = static_dir / "tab-stock-etf-fallbacks.js"
    main_source = main_path.read_text(encoding="utf-8")
    fallback_source = fallback_path.read_text(encoding="utf-8")

    missing_fallbacks = [
        name
        for name in sorted(STOCK_ETF_STATIC_GUI_FALLBACK_BUILDERS)
        if f"function {name}(reason)" not in fallback_source
    ]
    main_definitions = [
        name
        for name in sorted(STOCK_ETF_STATIC_GUI_FALLBACK_BUILDERS)
        if f"function {name}(reason)" in main_source
    ]

    assert missing_fallbacks == []
    assert main_definitions == []
    assert "scorecard_input_bundle" in fallback_source
    assert "readonly_probe_result_import_request_contract_id" in fallback_source
    assert "readonly_probe_result_import_request_hash_present" in fallback_source
    assert "stock_etf_ibkr_readonly_probe_result_import_request_v1" in fallback_source
    assert len(main_source.splitlines()) <= MAX_FILE_LINES
    assert len(fallback_source.splitlines()) <= MAX_FILE_LINES


def test_stock_etf_static_gui_data_policy_renderers_remain_split() -> None:
    static_dir = CONTROL_API_DIR / "app" / "static"
    main_path = static_dir / "tab-stock-etf.js"
    data_policy_path = static_dir / "tab-stock-etf-data-policy.js"
    main_source = main_path.read_text(encoding="utf-8")
    data_policy_source = data_policy_path.read_text(encoding="utf-8")

    missing_renderers = [
        name
        for name in sorted(STOCK_ETF_STATIC_GUI_DATA_POLICY_RENDERERS)
        if f"function {name}(data)" not in data_policy_source
    ]
    main_definitions = [
        name
        for name in sorted(STOCK_ETF_STATIC_GUI_DATA_POLICY_RENDERERS)
        if f"function {name}(data)" in main_source
    ]

    assert missing_renderers == []
    assert main_definitions == []
    assert len(main_source.splitlines()) <= MAX_FILE_LINES
    assert len(data_policy_source.splitlines()) <= MAX_FILE_LINES


def test_stock_etf_static_gui_auth_account_renderers_remain_split() -> None:
    static_dir = CONTROL_API_DIR / "app" / "static"
    main_path = static_dir / "tab-stock-etf.js"
    auth_account_path = static_dir / "tab-stock-etf-auth-account.js"
    main_source = main_path.read_text(encoding="utf-8")
    auth_account_source = auth_account_path.read_text(encoding="utf-8")

    missing_renderers = [
        name
        for name in sorted(STOCK_ETF_STATIC_GUI_AUTH_ACCOUNT_RENDERERS)
        if f"function {name}(data)" not in auth_account_source
    ]
    main_definitions = [
        name
        for name in sorted(STOCK_ETF_STATIC_GUI_AUTH_ACCOUNT_RENDERERS)
        if f"function {name}(data)" in main_source
    ]

    assert missing_renderers == []
    assert main_definitions == []
    assert "window.renderAuthorizationStatus" in main_source
    assert "window.renderAccountStatus" in main_source
    assert len(main_source.splitlines()) <= MAX_FILE_LINES
    assert len(auth_account_source.splitlines()) <= MAX_FILE_LINES


def test_stock_etf_static_gui_evidence_paper_renderers_remain_split() -> None:
    static_dir = CONTROL_API_DIR / "app" / "static"
    main_path = static_dir / "tab-stock-etf.js"
    evidence_paper_path = static_dir / "tab-stock-etf-evidence-paper.js"
    main_source = main_path.read_text(encoding="utf-8")
    evidence_paper_source = evidence_paper_path.read_text(encoding="utf-8")

    missing_renderers = [
        name
        for name in sorted(STOCK_ETF_STATIC_GUI_EVIDENCE_PAPER_RENDERERS)
        if f"function {name}(data)" not in evidence_paper_source
    ]
    main_definitions = [
        name
        for name in sorted(STOCK_ETF_STATIC_GUI_EVIDENCE_PAPER_RENDERERS)
        if f"function {name}(data)" in main_source
    ]

    assert missing_renderers == []
    assert main_definitions == []
    assert "window.renderEvidenceStatus" in main_source
    assert "window.renderUniverseStatus" in main_source
    assert "window.renderShadowStatus" in main_source
    assert "window.renderPaperStatus" in main_source
    assert len(main_source.splitlines()) <= MAX_FILE_LINES
    assert len(evidence_paper_source.splitlines()) <= MAX_FILE_LINES


def test_stock_etf_static_gui_scorecard_launch_renderers_remain_split() -> None:
    static_dir = CONTROL_API_DIR / "app" / "static"
    main_path = static_dir / "tab-stock-etf.js"
    scorecard_launch_path = static_dir / "tab-stock-etf-scorecard-launch.js"
    main_source = main_path.read_text(encoding="utf-8")
    scorecard_launch_source = scorecard_launch_path.read_text(encoding="utf-8")

    missing_renderers = [
        name
        for name in sorted(STOCK_ETF_STATIC_GUI_SCORECARD_LAUNCH_RENDERERS)
        if f"function {name}(data)" not in scorecard_launch_source
    ]
    main_definitions = [
        name
        for name in sorted(STOCK_ETF_STATIC_GUI_SCORECARD_LAUNCH_RENDERERS)
        if f"function {name}(data)" in main_source
    ]

    assert missing_renderers == []
    assert main_definitions == []
    assert "window.renderScorecardStatus" in main_source
    assert "window.renderLaunchStatus" in main_source
    assert len(main_source.splitlines()) <= MAX_FILE_LINES
    assert len(scorecard_launch_source.splitlines()) <= MAX_FILE_LINES


def test_stock_etf_static_gui_readiness_renderer_remains_split() -> None:
    static_dir = CONTROL_API_DIR / "app" / "static"
    main_path = static_dir / "tab-stock-etf.js"
    readiness_path = static_dir / "tab-stock-etf-readiness.js"
    main_source = main_path.read_text(encoding="utf-8")
    readiness_source = readiness_path.read_text(encoding="utf-8")

    readiness_definition = f"function {STOCK_ETF_STATIC_GUI_READINESS_RENDERER}(data, laneStatus)"
    assert readiness_definition in readiness_source
    assert readiness_definition not in main_source
    assert "window.renderReadiness" in main_source
    assert "function toneFor(value)" not in main_source
    assert "function kvRow(label, html)" not in main_source
    assert len(main_source.splitlines()) <= MAX_FILE_LINES
    assert len(readiness_source.splitlines()) <= MAX_FILE_LINES
