"""
Static asset structure test for OpenClawReplaySubtab namespace.
OpenClawReplaySubtab 命名空間的靜態資源結構測試。

REF-20 Sprint B1 R4-T4 (2026-05-05): pytest sibling fixture for the browser
HTML test (`test_replay_subtab_readiness.html`). This Python test runs in CI
without browser/jsdom — only asserts:

  1. tab-paper.html removed hardcoded `aria-disabled="true"` / `data-disabled="true"`
     on the Replay button (R4-T1 acceptance).
  2. app-paper.js defines `OpenClawReplaySubtab` namespace with required public API
     (onTabActivate / onTabDeactivate / pollBackendReadiness).
  3. app-paper.js renders the 4 report-backed cells (execution_confidence /
     data_tier / fee_model / calibration_status) and exposes the operator
     workflow: register → run → finalize → load report.
  4. app-paper.js polls `/api/v1/replay/health` and reads `wiring_status` field.
  5. ocPaperSubtabShow wires the activate/deactivate hooks for replay.
  6. tab-paper.html no longer renders static disabled card on page load for replay.
  7. Reuse `disabled_state.p2_backend_pending` i18n key (no new key added).
  8. The browser HTML test fixture is co-located.

REF-20 Sprint B1 R4-T4（2026-05-05）：browser HTML test 的 pytest sibling，
CI 可跑，僅做 grep / structural 斷言，不依賴 browser / jsdom。

Caveats / 限制:
  - This is structural sanity, NOT runtime behavior. Real DOM render / state
    machine 行為驗證在 `test_replay_subtab_readiness.html` 浏览器测试。
  - 这是结构性检查，不是 runtime 行为；DOM 渲染/状态机验证在 HTML 测试。
"""

from pathlib import Path

import pytest

# ─── Path resolution / 路徑解析 ────────────────────────────────────────────
# Cross-platform: resolve from this test file's location, not user-home.
# 跨平台：從本測試檔位置解析，不依賴 user-home。
_THIS_DIR = Path(__file__).resolve().parent
# tests/static/ → tests/ → control_api_v1/ → app/ → static/
_STATIC_DIR = _THIS_DIR.parent.parent / "app" / "static"
_TAB_PAPER_HTML = _STATIC_DIR / "tab-paper.html"
_TAB_REPLAY_HTML = _STATIC_DIR / "tab-replay.html"
_TAB_DEVELOPMENT_HTML = _STATIC_DIR / "tab-development.html"
_TAB_EDGE_GATES_HTML = _STATIC_DIR / "tab-edge-gates.html"
_TAB_DEMO_HTML = _STATIC_DIR / "tab-demo.html"
_TAB_LIVE_HTML = _STATIC_DIR / "tab-live.html"
_TAB_STRATEGY_HTML = _STATIC_DIR / "tab-strategy.html"
_TAB_RISK_HTML = _STATIC_DIR / "tab-risk.html"
_TAB_SETTINGS_HTML = _STATIC_DIR / "tab-settings.html"
_CONSOLE_HTML = _STATIC_DIR / "console.html"
_LOGIN_HTML = _STATIC_DIR / "login.html"
_INDEX_HTML = _STATIC_DIR / "index.html"
_TRADING_HTML = _STATIC_DIR / "trading.html"
_COMMON_JS = _STATIC_DIR / "common.js"
_APP_PAPER_JS = _STATIC_DIR / "app-paper.js"
_RISK_TAB_JS = _STATIC_DIR / "risk-tab.js"
_BROWSER_TEST_HTML = _THIS_DIR / "test_replay_subtab_readiness.html"


@pytest.fixture(scope="module")
def tab_paper_html() -> str:
    """Read tab-paper.html once per test module / 每模組讀一次。"""
    assert _TAB_PAPER_HTML.exists(), (
        f"tab-paper.html not found at {_TAB_PAPER_HTML}"
    )
    return _TAB_PAPER_HTML.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def tab_replay_html() -> str:
    """Read tab-replay.html once per test module / 每模組讀一次。"""
    assert _TAB_REPLAY_HTML.exists(), (
        f"tab-replay.html not found at {_TAB_REPLAY_HTML}"
    )
    return _TAB_REPLAY_HTML.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def tab_development_html() -> str:
    """Read tab-development.html once per test module / 每模組讀一次。"""
    assert _TAB_DEVELOPMENT_HTML.exists(), (
        f"tab-development.html not found at {_TAB_DEVELOPMENT_HTML}"
    )
    return _TAB_DEVELOPMENT_HTML.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def tab_edge_gates_html() -> str:
    """Read tab-edge-gates.html once per test module / 每模組讀一次。"""
    assert _TAB_EDGE_GATES_HTML.exists(), (
        f"tab-edge-gates.html not found at {_TAB_EDGE_GATES_HTML}"
    )
    return _TAB_EDGE_GATES_HTML.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def tab_demo_html() -> str:
    """Read tab-demo.html once per test module / 每模組讀一次。"""
    assert _TAB_DEMO_HTML.exists(), f"tab-demo.html not found at {_TAB_DEMO_HTML}"
    return _TAB_DEMO_HTML.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def console_html() -> str:
    """Read console.html once per test module / 每模組讀一次。"""
    assert _CONSOLE_HTML.exists(), f"console.html not found at {_CONSOLE_HTML}"
    return _CONSOLE_HTML.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def tab_settings_html() -> str:
    """Read tab-settings.html once per test module / 每模組讀一次。"""
    assert _TAB_SETTINGS_HTML.exists(), (
        f"tab-settings.html not found at {_TAB_SETTINGS_HTML}"
    )
    return _TAB_SETTINGS_HTML.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def tab_live_html() -> str:
    """Read tab-live.html once per test module / 每模組讀一次。"""
    assert _TAB_LIVE_HTML.exists(), f"tab-live.html not found at {_TAB_LIVE_HTML}"
    return _TAB_LIVE_HTML.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def tab_strategy_html() -> str:
    """Read tab-strategy.html once per test module / 每模組讀一次。"""
    assert _TAB_STRATEGY_HTML.exists(), (
        f"tab-strategy.html not found at {_TAB_STRATEGY_HTML}"
    )
    return _TAB_STRATEGY_HTML.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def tab_risk_html() -> str:
    """Read tab-risk.html once per test module / 每模組讀一次。"""
    assert _TAB_RISK_HTML.exists(), f"tab-risk.html not found at {_TAB_RISK_HTML}"
    return _TAB_RISK_HTML.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def common_js() -> str:
    """Read common.js once per test module / 每模組讀一次。"""
    assert _COMMON_JS.exists(), f"common.js not found at {_COMMON_JS}"
    return _COMMON_JS.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def app_paper_js() -> str:
    """Read app-paper.js once per test module / 每模組讀一次。"""
    assert _APP_PAPER_JS.exists(), (
        f"app-paper.js not found at {_APP_PAPER_JS}"
    )
    return _APP_PAPER_JS.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def risk_tab_js() -> str:
    """Read risk-tab.js once per test module / 每模組讀一次。"""
    assert _RISK_TAB_JS.exists(), f"risk-tab.js not found at {_RISK_TAB_JS}"
    return _RISK_TAB_JS.read_text(encoding="utf-8")


# ═══════════════════════════════════════════════════════════════════════════════
# R4-T1 acceptance: tab-paper.html replay button no longer hardcoded disabled
# R4-T1 驗收：tab-paper.html replay 按鈕不再硬編 disabled
# ═══════════════════════════════════════════════════════════════════════════════


def test_replay_is_no_longer_owned_by_paper_tab(tab_paper_html: str) -> None:
    """Legacy Paper tab must not expose the Replay subtab anymore."""
    assert 'id="subtab-btn-replay"' not in tab_paper_html
    assert 'id="subtab-replay"' not in tab_paper_html


def test_top_level_replay_tab_mount_present(tab_replay_html: str) -> None:
    """Standalone Replay tab owns the readiness mount and boot hook."""
    assert 'id="subtab-replay-disabled-card"' in tab_replay_html
    assert "OpenClawReplaySubtab.onTabActivate" in tab_replay_html


def test_console_has_replay_and_optional_paper_tabs(console_html: str) -> None:
    """Console exposes Replay as first-class tab; Paper is settings-gated."""
    assert "id: 'replay'" in console_html
    assert "tab-replay.html" in console_html
    assert "TAB_GROUP_LABELS" in console_html
    assert "tab-group-label" in console_html
    assert "toggleTabGroup" in console_html
    assert "TAB_GROUP_SHORTCUTS" in console_html
    assert "'1': 'core'" in console_html
    assert "'6': 'ops'" in console_html
    assert "handleTabGroupShortcut" in console_html
    assert "tab-group-caret" in console_html
    assert "tab-group-key" in console_html
    assert "tab-label" in console_html
    assert "requiresPaperEngine: true" in console_html
    assert "/api/v1/settings/paper-engine" in console_html


def test_console_has_top_level_edge_gates_tab(console_html: str) -> None:
    """Console exposes Pre-Live Edge Gates as a standalone grouped tab."""
    assert "id: 'edge-gates'" in console_html
    assert "tab-edge-gates.html" in console_html
    assert "Pre-Live Gates" in console_html
    assert "group: 'core'" in console_html


def test_console_strategy_group_order_and_labels_are_operator_clear(
    console_html: str,
) -> None:
    """Strategy/Edge order is Replay → Strategy → Charts; AI labels are distinct."""
    replay_idx = console_html.index("id: 'replay'")
    strategy_idx = console_html.index("id: 'strategy'")
    charts_idx = console_html.index("id: 'charts'")
    assert replay_idx < strategy_idx < charts_idx
    assert "label: 'AI 状态'" in console_html
    assert "label: 'Agent 团队'" in console_html
    assert "AI 智能" not in console_html


def test_console_has_settings_gated_development_support_tab(console_html: str) -> None:
    """Development support tab is present but hidden until the setting is enabled."""
    assert "id: 'development'" in console_html
    assert "tab-development.html" in console_html
    assert "requiresDevelopmentSupport: true" in console_html
    assert "/api/v1/settings/development-mode" not in console_html
    assert "openclaw-development-support-setting" in console_html


def test_development_tab_covers_v001_to_v063(tab_development_html: str) -> None:
    """Development support tab is backed by dynamic repo diagnostics."""
    assert "/api/v1/settings/development-status" in tab_development_html
    assert "Migration Intelligence" in tab_development_html
    assert "Development Focus" in tab_development_html
    assert "Recent PM Reports" in tab_development_html
    assert "Documentation Intelligence" in tab_development_html
    assert "Hot GUI Candidates" in tab_development_html
    assert "dev-migration-grid" in tab_development_html
    assert "toggleMigrationCard" in tab_development_html
    assert "auto refresh 60s" in tab_development_html
    assert "server-side scan per refresh" in tab_development_html
    assert "renderDocumentation" in tab_development_html
    assert "新增 V064+ migration 后会自动出现在本页" in tab_development_html
    assert "for (let i = 1; i <= 63; i += 1)" not in tab_development_html


def test_development_support_toggle_is_browser_local(
    tab_settings_html: str,
    common_js: str,
) -> None:
    """Settings support toggle must not depend on a newly loaded backend route."""
    assert "Development Support" in tab_settings_html
    assert "development-support-enabled" in tab_settings_html
    assert "/api/v1/settings/development-mode" not in tab_settings_html
    assert "OC_DEVELOPMENT_SUPPORT_MODE_KEY" in common_js
    assert "async function ocFetchDevelopmentSupportMode" in common_js
    assert "/api/v1/settings/development-mode" not in common_js


def test_settings_decision_lease_status_is_dynamic(tab_settings_html: str) -> None:
    """W-AUDIT-3 F-17: Settings tab must not hardcode Decision Lease=false."""
    assert 'id="sys-decision-lease"' in tab_settings_html
    assert "/api/v1/governance/lease-router/status" in tab_settings_html
    assert "renderDecisionLeaseStatus" in tab_settings_html
    hardcoded_metric = (
        '<div class="oc-metric-label">Decision Lease</div>'
        '<div class="oc-metric-val" style="font-size:14px">false</div>'
    )
    assert hardcoded_metric not in tab_settings_html


def test_edge_gates_tab_renders_strategy_and_healthcheck_surfaces(
    tab_edge_gates_html: str,
) -> None:
    """Edge Gates tab must show readiness, strategies, crisis, and healthcheck."""
    assert "/api/v1/strategy/prelive/edge-gates" in tab_edge_gates_html
    assert "/api/v1/system/health" in tab_edge_gates_html
    assert "Strategy Gate Matrix" in tab_edge_gates_html
    assert "Strategy Crisis" in tab_edge_gates_html
    assert "Global Healthcheck" in tab_edge_gates_html
    assert "fallbackStrategyStatus" in tab_edge_gates_html


def test_global_mode_control_surfaces_are_development_gated(
    tab_live_html: str,
) -> None:
    """Live's global-mode explanatory surface is gated by Development Support."""
    assert 'id="live-global-mode-control-note"' in tab_live_html
    assert 'data-dev-mode-only="global-mode-control"' in tab_live_html
    assert "ocFetchDevelopmentSupportMode" in tab_live_html


def test_demo_and_live_tabs_have_risk_shortcuts(
    console_html: str,
    tab_demo_html: str,
    tab_live_html: str,
    tab_risk_html: str,
    risk_tab_js: str,
) -> None:
    """Demo/Live can jump to the selected Risk surface inside the console."""
    assert "openclaw-console-switch-tab" in console_html
    assert "openclaw-risk-select" in console_html
    assert "openDemoRisk" in tab_demo_html
    assert "riskEngine: 'demo'" in tab_demo_html
    assert "riskTab: 'config'" in tab_demo_html
    assert "openLiveRisk" in tab_live_html
    assert "riskEngine: 'live'" in tab_live_html
    assert "riskTab: 'config'" in tab_live_html
    assert "风险总览 / Risk Overview" in tab_risk_html
    assert "参数设置 / Risk Settings" in tab_risk_html
    assert "applyPaperRiskAvailability" in risk_tab_js
    assert "/api/v1/settings/paper-engine" in risk_tab_js
    assert "openclaw-risk-select" in risk_tab_js


def test_demo_and_live_fill_history_show_strategy(
    console_html: str,
    tab_demo_html: str,
    tab_live_html: str,
) -> None:
    """Demo/Live fill history tables show per-fill strategy attribution."""
    assert "20260507.fill-tabs-v1" in console_html
    assert "<th>策略</th>" in tab_demo_html
    assert "f.strategy || f.strategy_name || f.owner_strategy" in tab_demo_html
    assert "ocStrategyChip(s)" in tab_demo_html
    assert "暂无成交" in tab_demo_html
    assert "<th>策略 / Strategy</th>" in tab_live_html
    assert "f.strategy || f.strategy_name || f.owner_strategy || _liveStratMap" in tab_live_html
    assert "ocStrategyChip(s)" in tab_live_html
    assert 'td colspan="10"' in tab_live_html


def test_strategy_identity_colors_are_shared_across_console_surfaces(
    console_html: str,
    common_js: str,
    tab_strategy_html: str,
    tab_demo_html: str,
    tab_live_html: str,
    tab_edge_gates_html: str,
) -> None:
    """Five strategy identities should keep one color system across pages."""
    assert "20260507.fill-tabs-v1" in console_html
    assert "OC_STRATEGY_COLOR_META" in common_js
    for key in [
        "grid_trading",
        "ma_crossover",
        "bb_reversion",
        "bb_breakout",
        "funding_arb",
    ]:
        assert key in common_js
        assert f"oc-strategy-{key}" in common_js
        assert f"oc-strategy-card-{key}" in common_js

    assert "ocStrategyKey(stratName)" in tab_strategy_html
    assert "ocStrategyChip(stratName" in tab_strategy_html
    assert "oc-strategy-card-" in tab_strategy_html
    assert "ocStrategyChip(s)" in tab_demo_html
    assert "ocStrategyChip(s)" in tab_live_html
    assert "ocStrategyChip(row.strategy_name" in tab_edge_gates_html


def test_demo_and_live_fill_history_has_paged_subtabs(
    console_html: str,
    tab_demo_html: str,
    tab_live_html: str,
) -> None:
    """Demo/Live fill history should page server-side and split key views."""
    assert "20260507.fill-tabs-v1" in console_html
    for html in [tab_demo_html, tab_live_html]:
        assert "data-fill-tab=\"aggregate\"" in html
        assert "data-fill-tab=\"buy\"" in html
        assert "data-fill-tab=\"sell\"" in html
        assert "data-fill-tab=\"profit\"" in html
        assert "limit=' + _" in html
        assert "offset=' + _" in html
        assert "side=' + encodeURIComponent(side)" in html
        assert "has_more" in html
        assert "Page ' + page" in html
        assert "BuildProfitRows" in html


def test_demo_live_tabs_use_matching_backend_surfaces(
    console_html: str,
    tab_demo_html: str,
    tab_live_html: str,
) -> None:
    """Demo and Live tabs should not cross-read each other's account APIs."""
    for endpoint in [
        "/api/v1/strategy/demo/balance",
        "/api/v1/strategy/demo/positions",
        "/api/v1/strategy/demo/orders",
        "/api/v1/strategy/demo/fills",
        "/api/v1/strategy/demo/metrics",
    ]:
        assert endpoint in tab_demo_html

    for endpoint in [
        "/api/v1/live/balance",
        "/api/v1/live/positions",
        "/api/v1/live/orders",
        "/api/v1/live/fills",
        "/api/v1/live/metrics",
    ]:
        assert endpoint in tab_live_html

    assert "/api/v1/live/balance" not in tab_demo_html
    assert "/api/v1/live/positions" not in tab_demo_html
    assert "/api/v1/strategy/demo/balance" not in tab_live_html
    assert "/api/v1/strategy/demo/positions" not in tab_live_html

    assert "api('/api/v1/live/metrics')" in console_html
    assert "api('/api/v1/strategy/demo/metrics')" in console_html


def test_live_today_pnl_uses_backend_metric_not_position_cumulative(
    console_html: str,
    tab_live_html: str,
) -> None:
    """Live Today PnL must come from backend net_pnl_today, not cumRealisedPnl."""
    assert "net_pnl_today" in tab_live_html
    assert "net_pnl_today" in console_html
    assert "account_metrics_today" in tab_live_html
    assert "account_metrics_today" in console_html
    assert "cumRealisedPnl" not in tab_live_html
    assert "cum_realised_pnl" not in tab_live_html


def test_soft_rename_removes_claw_logo_from_entry_surfaces(
    console_html: str,
) -> None:
    """Entry surfaces should show 玄衡 branding, not the old claw mark."""
    entry_text = "\n".join(
        [
            console_html,
            _LOGIN_HTML.read_text(encoding="utf-8"),
            _INDEX_HTML.read_text(encoding="utf-8"),
            _TRADING_HTML.read_text(encoding="utf-8"),
        ]
    )
    assert "玄衡" in entry_text
    assert "Arcane Equilibrium" in entry_text
    assert "&#x1F99E;" not in entry_text
    assert "OpenClaw Trading Console" not in entry_text
    assert "OpenClaw Trading System" not in entry_text
    assert "OpenClaw / Bybit Control Center" not in entry_text


def test_r4_t1_other_subtabs_still_disabled(tab_paper_html: str) -> None:
    """compare/handoff still disabled (only replay flipped to dynamic gate).

    compare/handoff 仍 disabled（只 replay 切到動態 gate）。
    """
    assert 'data-subtab="compare"' in tab_paper_html
    # find compare button block and assert still disabled
    idx = tab_paper_html.find('id="subtab-btn-compare"')
    assert idx >= 0
    # Find enclosing <button ...> and </button>
    btn_start = tab_paper_html.rfind("<button", 0, idx)
    btn_end = tab_paper_html.find("</button>", idx)
    assert btn_start >= 0 and btn_end > 0
    compare_btn = tab_paper_html[btn_start:btn_end]
    assert 'aria-disabled="true"' in compare_btn, (
        "compare subtab should still be disabled (P3 gated)"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# R4-T2 acceptance: OpenClawReplaySubtab namespace + 5-state machine + 30s poll
# R4-T2 驗收：OpenClawReplaySubtab 命名空間 + 5 態狀態機 + 30s 輪詢
# ═══════════════════════════════════════════════════════════════════════════════


def test_r4_t2_namespace_exported(app_paper_js: str) -> None:
    """OpenClawReplaySubtab must be exported on window.

    OpenClawReplaySubtab 必須掛在 window 上。
    """
    assert "window.OpenClawReplaySubtab" in app_paper_js, (
        "OpenClawReplaySubtab namespace not exported on window"
    )


@pytest.mark.parametrize(
    "fn_name",
    ["onTabActivate", "onTabDeactivate", "pollBackendReadiness"],
)
def test_r4_t2_namespace_public_api(app_paper_js: str, fn_name: str) -> None:
    """Public API: onTabActivate / onTabDeactivate / pollBackendReadiness.

    公開 API：onTabActivate / onTabDeactivate / pollBackendReadiness。
    """
    # Look for either `function onTabActivate` definition OR
    # `onTabActivate: onTabActivate` namespace export
    has_def = f"function {fn_name}(" in app_paper_js
    has_export = f"{fn_name}: {fn_name}" in app_paper_js
    assert has_def or has_export, (
        f"{fn_name} not defined or not exported on namespace"
    )


def test_r4_t2_polls_replay_health_endpoint(app_paper_js: str) -> None:
    """Must call /api/v1/replay/health (no other replay probe URLs).

    必呼 /api/v1/replay/health（無其他 probe URL）。
    """
    assert '"/api/v1/replay/health"' in app_paper_js or \
           "'/api/v1/replay/health'" in app_paper_js, (
        "OpenClawReplaySubtab does not call /api/v1/replay/health"
    )


def test_r4_t2_reads_wiring_status_field(app_paper_js: str) -> None:
    """Must parse wiring_status from /health response data field.

    必從 /health response 的 data 欄位解析 wiring_status。
    """
    assert "wiring_status" in app_paper_js
    # All three documented states must be handled
    assert '"ready"' in app_paper_js or "'ready'" in app_paper_js
    assert '"degraded"' in app_paper_js or "'degraded'" in app_paper_js
    assert '"binary_missing"' in app_paper_js or "'binary_missing'" in app_paper_js


def test_r4_t2_30s_polling_interval(app_paper_js: str) -> None:
    """30s polling interval per PA brief §3 R4-T2.

    PA brief §3 R4-T2：30 秒輪詢間隔。
    """
    # 30000 ms = 30s
    assert "30000" in app_paper_js, "Expected 30s (30000ms) poll interval"
    assert "setInterval" in app_paper_js, "setInterval not used for polling"
    assert "clearInterval" in app_paper_js, (
        "clearInterval not used for teardown"
    )


def test_r4_t2_subtab_show_hooks_replay_activate(app_paper_js: str) -> None:
    """Replay namespace still exports activation hooks for the standalone tab."""
    assert "onTabActivate: onTabActivate" in app_paper_js
    assert "onTabDeactivate: onTabDeactivate" in app_paper_js
    show_idx = app_paper_js.find("function ocPaperSubtabShow(")
    assert show_idx >= 0, "ocPaperSubtabShow not found"
    next_fn = app_paper_js.find("function ocPaperSubtabRestoreFromStorage", show_idx)
    assert next_fn > show_idx
    show_block = app_paper_js[show_idx:next_fn]
    assert '"replay"' not in show_block and "'replay'" not in show_block


# ═══════════════════════════════════════════════════════════════════════════════
# R4-T3 acceptance: 4 baseline cells + Sprint A invariants
# R4-T3 驗收：4 baseline cell + Sprint A 不變式
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "marker_zh,marker_en,desc",
    [
        ("執行可信度", "Execution Confidence", "cell1_execution_confidence"),
        ("資料層級", "Data Tier", "cell2_data_tier"),
        ("費率模型", "Fee Model", "cell3_fee_model"),
        ("校準狀態", "Calibration", "cell4_calibration"),
    ],
)
def test_r4_t3_four_cells_bilingual_labels(
    app_paper_js: str, marker_zh: str, marker_en: str, desc: str
) -> None:
    """4 cell labels must be bilingual (中英對照).

    4 個 cell 標籤必中英對照（per CLAUDE.md §七 強制）。
    """
    assert marker_zh in app_paper_js, (
        f"{desc}: zh label '{marker_zh}' not found"
    )
    assert marker_en in app_paper_js, (
        f"{desc}: en label '{marker_en}' not found"
    )


def test_replay_metrics_start_unloaded_not_hardcoded_none(
    app_paper_js: str,
) -> None:
    """Metrics must wait for report data instead of hardcoding Sprint A NONE."""
    assert "未載入 / NOT LOADED" in app_paper_js
    assert "無 / NONE" not in app_paper_js
    assert "oc-cell-warn" in app_paper_js, (
        "oc-cell-warn class for pre-report warning state not found"
    )


def test_full_chain_summary_surfaces_execution_calibration(
    app_paper_js: str,
) -> None:
    """One-click full-chain summary must show execution calibration fidelity."""
    assert "Exec Cal / 執行校準" in app_paper_js
    assert "Maker Fill / Maker成交" in app_paper_js
    assert "BBO Anchor / BBO約束" in app_paper_js
    assert "Preflight / 預檢" in app_paper_js
    assert "bbo_anchor_coverage_ratio" in app_paper_js
    assert "/api/v1/replay/full-chain/coverage" in app_paper_js
    assert "recommended_taker_slippage_bps" in app_paper_js
    assert "recommended_maker_fill_probability_cap" in app_paper_js
    assert "Replay-only taker slippage floor from demo/live_demo fills" in app_paper_js
    assert "PostOnly order outcome calibration from demo/live_demo orders" in app_paper_js
    assert "Taker fills are bounded by local best bid/ask only for covered events" in app_paper_js
    assert "Read-only recorder coverage estimate before launching replay" in app_paper_js
    assert "Net Bps / 淨bps" in app_paper_js
    assert "Verdict / 判定" in app_paper_js
    assert "Miss/Reject / 未成交拒絕" in app_paper_js
    assert "C3 development-sandbox verdict; not a live/demo promotion" in app_paper_js


def test_replay_data_tier_is_report_backed_not_s3_static(
    app_paper_js: str,
) -> None:
    """Data tier cell starts waiting; the selector still allows S2/S3."""
    assert "等待 manifest / WAITING" in app_paper_js
    assert "S2 calibrated_replay" in app_paper_js
    assert "S3 synthetic_replay" in app_paper_js


def test_replay_fee_model_waits_for_runner_fill_fields(
    app_paper_js: str,
) -> None:
    """Fee model must be loaded from fill fee_rate/liquidity_role fields."""
    assert "fee_rate=" in app_paper_js
    assert "NOT CALIBRATED" not in app_paper_js


def test_replay_calibration_waits_for_finalize(
    app_paper_js: str,
) -> None:
    """Calibration is finalize-backed, not a stale PENDING R6 label."""
    assert "等待 finalize / WAITING" in app_paper_js
    assert "PENDING R6" not in app_paper_js


def test_r4_t3_fetches_replay_report_endpoint(app_paper_js: str) -> None:
    """Must fetch /api/v1/replay/report/{experiment_id} on load button click.

    載入按鈕必 fetch /api/v1/replay/report/{experiment_id}。
    """
    assert "/api/v1/replay/report/" in app_paper_js, (
        "Does not fetch /api/v1/replay/report/{id}"
    )


def test_replay_operator_workflow_endpoints_wired(app_paper_js: str) -> None:
    """Paper tab must expose register/run/finalize workflow calls."""
    assert "/api/v1/replay/experiments/register" in app_paper_js
    assert '"/api/v1/replay/run"' in app_paper_js
    assert "/finalize" in app_paper_js
    assert "Run Backtest / 一鍵回測" in app_paper_js
    assert "oc-replay-fixture-uri" in app_paper_js


def test_replay_quick_mode_is_default_and_advanced_is_preserved(
    app_paper_js: str,
) -> None:
    """Replay tab defaults to simple one-click flow and keeps Advanced."""
    assert "oc-replay-quick-panel" in app_paper_js
    assert "oc-replay-advanced-panel" in app_paper_js
    assert "One-Click Replay / 一鍵 Replay" in app_paper_js
    assert "Advanced / 進階" in app_paper_js
    assert "/api/v1/replay/full-chain/run" in app_paper_js
    assert "historical scanner timeline" in app_paper_js
    assert "oc-replay-quick-universe" in app_paper_js
    assert "oc-replay-quick-symbols" in app_paper_js
    assert "oc-replay-quick-strategy-check" in app_paper_js
    assert "oc-replay-quick-window-start" in app_paper_js
    assert "oc-replay-quick-engine" in app_paper_js
    assert "use_current_config: true" in app_paper_js
    assert "SIMULATION ONLY" in app_paper_js
    assert '<option value="1h" selected>1h</option>' in app_paper_js
    assert (
        'id="oc-replay-quick-max-symbols" type="number" min="1" max="25" '
        'step="1" value="2"'
    ) in app_paper_js
    assert "oc-replay-preflight-events" in app_paper_js
    assert "replay_full_chain_window_too_large" in app_paper_js
    assert "reduce Max Symbols, choose 1h/4h, or shorten the window" in app_paper_js


def test_replay_tab_copy_mentions_quick_and_advanced(tab_replay_html: str) -> None:
    """Top-level Replay page frames Quick as default and Advanced as full flow."""
    assert "One-Click Replay" in tab_replay_html
    assert "multi-symbol, multi-strategy" in tab_replay_html
    assert "historical scanner timeline" in tab_replay_html
    assert "Advanced" in tab_replay_html


def test_r4_t3_xss_safe_via_ocesc(app_paper_js: str) -> None:
    """All dynamic strings from backend must go through ocEsc().

    所有來自 backend 的 dynamic string 必走 ocEsc()（per E1a profile XSS 規範）。
    """
    # Multiple ocEsc usages in the OpenClawReplaySubtab section
    namespace_idx = app_paper_js.find("OpenClawReplaySubtab — readiness probe")
    assert namespace_idx >= 0
    # Section after this header until end of file
    section = app_paper_js[namespace_idx:]
    ocesc_count = section.count("ocEsc(")
    assert ocesc_count >= 5, (
        f"Expected at least 5 ocEsc() calls in OpenClawReplaySubtab block, "
        f"got {ocesc_count}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# R4 invariant: tab-paper.html no longer renders static disabled card on init
# R4 不變式：tab-paper.html 不再 page-load 渲染靜態 disabled card
# ═══════════════════════════════════════════════════════════════════════════════


def test_r4_t2_no_static_disabled_render_on_page_load(
    tab_paper_html: str,
) -> None:
    """The DOMContentLoaded init no longer calls render('subtab-replay-...').

    DOMContentLoaded init 不再呼叫 render('subtab-replay-disabled-card', ...)。
    """
    # Find the _ocInitPaperDisabledCards function block
    init_idx = tab_paper_html.find("_ocInitPaperDisabledCards")
    assert init_idx >= 0, "_ocInitPaperDisabledCards init block not found"
    # 4000 chars after init function should cover the body
    init_block = tab_paper_html[init_idx:init_idx + 4000]
    # The render call for replay-disabled-card must NOT appear in this init block
    assert "render('subtab-replay-disabled-card'" not in init_block, (
        "R4-T2 violation: page-load still renders static replay disabled card"
    )
    assert 'render("subtab-replay-disabled-card"' not in init_block


# ═══════════════════════════════════════════════════════════════════════════════
# R4 invariant: i18n key reuse (no new disabled_state.* key added)
# R4 不變式：i18n key 重用（不新增 disabled_state.* key）
# ═══════════════════════════════════════════════════════════════════════════════


def test_r4_reuses_existing_i18n_key(app_paper_js: str) -> None:
    """Must reuse `disabled_state.p2_backend_pending` per PA brief §3 invariant.

    PA brief §3 不變式：必重用 disabled_state.p2_backend_pending key。
    """
    assert "disabled_state.p2_backend_pending" in app_paper_js, (
        "Should reuse existing i18n key, not add a new disabled_state.* key"
    )


def test_r4_no_new_disabled_state_keys_added(app_paper_js: str) -> None:
    """No newly-coined disabled_state.* keys appear in OpenClawReplaySubtab.

    OpenClawReplaySubtab 內不應新增 disabled_state.* key（避免 i18n 表膨脹）。
    """
    # Allowed: only the existing key we reuse.
    allowed = {
        "disabled_state.p2_backend_pending",
        "disabled_state.execution_calibration_unavailable",  # used elsewhere
        "disabled_state.handoff_disabled_until_p6",          # used elsewhere
    }
    # Find all disabled_state.* references in app-paper.js (across whole file).
    import re

    refs = set(re.findall(r"disabled_state\.[a-zA-Z0-9_]+", app_paper_js))
    new_keys = refs - allowed
    assert not new_keys, (
        f"R4 violation: new disabled_state.* keys introduced: {new_keys}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# R4-T4 acceptance: browser HTML test fixture co-located
# R4-T4 驗收：browser HTML test fixture 同目錄
# ═══════════════════════════════════════════════════════════════════════════════


def test_r4_t4_browser_test_fixture_present() -> None:
    """test_replay_subtab_readiness.html must be co-located in tests/static/.

    test_replay_subtab_readiness.html 必同目錄（tests/static/）。
    """
    assert _BROWSER_TEST_HTML.exists(), (
        f"Browser test fixture not found at {_BROWSER_TEST_HTML}"
    )


def test_r4_t4_browser_test_covers_three_states() -> None:
    """Browser fixture must cover 3 wiring_status states + fetch_failed.

    browser fixture 必覆蓋 3 個 wiring_status 狀態 + fetch_failed。
    """
    content = _BROWSER_TEST_HTML.read_text(encoding="utf-8")
    assert "case_ready" in content
    assert "case_degraded" in content
    assert "case_binary_missing" in content
    assert "case_fetch_failed" in content
    assert "case_deactivate" in content


# ═══════════════════════════════════════════════════════════════════════════════
# Cross-platform sanity: no hardcoded user-home paths in new code
# 跨平台：新代碼不可硬編 user-home 路徑
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "src",
    ["tab_paper_html", "tab_replay_html", "console_html", "app_paper_js"],
)
def test_no_hardcoded_user_home_paths(
    request: pytest.FixtureRequest, src: str,
) -> None:
    """Per CLAUDE.md §七 ★★ 跨平台：禁止 /home/ncyu/ or /Users/ncyu/ literals.

    per CLAUDE.md §七 跨平台：禁 /home/ncyu/ 或 /Users/ncyu/ 字面值。
    """
    content = request.getfixturevalue(src)
    assert "/home/ncyu/" not in content, (
        f"{src}: hardcoded /home/ncyu/ path violates §七"
    )
    assert "/Users/ncyu/" not in content, (
        f"{src}: hardcoded /Users/ncyu/ path violates §七"
    )
