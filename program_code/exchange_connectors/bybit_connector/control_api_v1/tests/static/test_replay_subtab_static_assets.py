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
_APP_PAPER_JS = _STATIC_DIR / "app-paper.js"
_BROWSER_TEST_HTML = _THIS_DIR / "test_replay_subtab_readiness.html"


@pytest.fixture(scope="module")
def tab_paper_html() -> str:
    """Read tab-paper.html once per test module / 每模組讀一次。"""
    assert _TAB_PAPER_HTML.exists(), (
        f"tab-paper.html not found at {_TAB_PAPER_HTML}"
    )
    return _TAB_PAPER_HTML.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def app_paper_js() -> str:
    """Read app-paper.js once per test module / 每模組讀一次。"""
    assert _APP_PAPER_JS.exists(), (
        f"app-paper.js not found at {_APP_PAPER_JS}"
    )
    return _APP_PAPER_JS.read_text(encoding="utf-8")


# ═══════════════════════════════════════════════════════════════════════════════
# R4-T1 acceptance: tab-paper.html replay button no longer hardcoded disabled
# R4-T1 驗收：tab-paper.html replay 按鈕不再硬編 disabled
# ═══════════════════════════════════════════════════════════════════════════════


def test_r4_t1_replay_button_not_hardcoded_disabled(tab_paper_html: str) -> None:
    """Replay button must NOT carry static aria-disabled/data-disabled.

    回放按鈕不可靜態帶 aria-disabled/data-disabled。
    """
    # The replay button block must contain id="subtab-btn-replay" and
    # data-subtab="replay" but NOT aria-disabled="true"/data-disabled="true"
    # within its tag bounds. Find the button line and assert.
    lines = tab_paper_html.split("\n")
    in_replay_btn = False
    btn_lines: list[str] = []
    for line in lines:
        if 'id="subtab-btn-replay"' in line:
            in_replay_btn = True
        if in_replay_btn:
            btn_lines.append(line)
            if line.rstrip().endswith("</button>"):
                break

    assert btn_lines, "subtab-btn-replay <button> block not found"
    btn_text = "\n".join(btn_lines)
    assert 'aria-disabled="true"' not in btn_text, (
        f"R4-T1 violation: replay button still has aria-disabled='true':\n{btn_text}"
    )
    assert 'data-disabled="true"' not in btn_text, (
        f"R4-T1 violation: replay button still has data-disabled='true':\n{btn_text}"
    )


def test_r4_t1_replay_button_keeps_subtab_id(tab_paper_html: str) -> None:
    """data-subtab + id attributes preserved per PA brief §3 R4-T1.

    PA brief §3 R4-T1：保留 data-subtab + id 屬性。
    """
    assert 'id="subtab-btn-replay"' in tab_paper_html
    assert 'data-subtab="replay"' in tab_paper_html


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
    """ocPaperSubtabShow must call onTabActivate when name === 'replay'.

    ocPaperSubtabShow 對 name === 'replay' 必呼 onTabActivate。
    """
    # Find the show fn block and confirm 'replay' branch wires hooks
    assert "onTabActivate" in app_paper_js
    assert "onTabDeactivate" in app_paper_js
    # Ensure replay branch in show fn
    show_idx = app_paper_js.find("function ocPaperSubtabShow(")
    assert show_idx >= 0, "ocPaperSubtabShow not found"
    # Look for 'replay' string within ~3500 chars after show start
    show_block = app_paper_js[show_idx:show_idx + 3500]
    assert '"replay"' in show_block or "'replay'" in show_block, (
        "ocPaperSubtabShow does not branch on 'replay' name"
    )


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
    ["tab_paper_html", "app_paper_js"],
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
