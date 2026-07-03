from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
STATIC = REPO_ROOT / "program_code/exchange_connectors/bybit_connector/control_api_v1/app/static"


def _source(rel_path: str) -> str:
    return (STATIC / rel_path).read_text(encoding="utf-8")


def test_common_css_defines_action_risk_zones() -> None:
    # ae71575e8 (P2-COMMON-JS-LOC) 拆檔後：風險分區 CSS class 注入仍留在
    # common.js，confirm modal 邏輯（預設表 / confirmClass 應用）移入
    # common-modals.js；斷言字串不變，只改讀取來源。
    source = _source("common.js")

    for marker in (
        ".oc-btn-warning",
        ".oc-btn-critical",
        ".oc-btn-destructive",
        ".oc-action-row",
        ".oc-action-cluster-pause",
        ".oc-action-cluster-stop",
        ".oc-action-cluster-destructive",
        ".oc-toolbar-danger-action",
        ".oc-row-close-action",
    ):
        assert marker in source

    modals_source = _source("common-modals.js")
    assert '"paper-stop-all"' in modals_source
    assert "typeof actionName === 'object'" in modals_source
    assert "confirmBtn.className = 'oc-btn ' + (meta.confirmClass || 'oc-btn-danger');" in modals_source


def test_strategy_stop_pause_delete_are_visually_separated() -> None:
    source = _source("tab-strategy.html")

    assert "oc-action-row-strategy" in source
    assert 'data-danger-zone="strategy-pause"' in source
    assert 'data-danger-zone="strategy-stop"' in source
    assert 'data-danger-zone="strategy-delete"' in source
    assert "oc-btn-warning oc-action-pause" in source
    assert "oc-btn-danger oc-btn-critical oc-action-stop" in source
    assert "oc-btn-destructive oc-action-delete" in source
    assert 'openConfirmModal("delete-strategy")' in source
    assert "confirm(" not in source


def test_paper_stop_and_close_actions_use_zones_and_custom_confirm() -> None:
    source = _source("tab-paper.html")

    assert 'id="paper-session-controls"' in source
    assert 'data-danger-zone="paper-session-pause"' in source
    assert 'data-danger-zone="paper-session-stop"' in source
    assert 'data-danger-zone="paper-dual-stop"' in source
    assert 'id="btn-pause"' in source and "oc-btn-warning" in source
    assert 'id="btn-stop"' in source and "oc-btn-critical" in source
    assert 'id="btn-stop-all"' in source and "oc-btn-destructive" in source
    assert 'openConfirmModal("paper-stop-all")' in source
    assert "oc-toolbar-danger-action" in source
    assert "oc-row-close-action" in source
    assert "confirm(" not in source


def test_live_stop_emergency_and_close_actions_are_visually_separated() -> None:
    # 9bf4fd62d (P2-TAB-LIVE-JS-EXTRACT) 把 tab-live.html 內聯 script 抽到
    # tab-live.js：靜態危險分區標記留在 HTML，動態產生的持倉列平倉按鈕與
    # confirm modal 呼叫移入 JS；斷言字串不變，按內容歸屬拆兩個來源檢查。
    html_source = _source("tab-live.html")
    js_source = _source("tab-live.js")

    assert ".live-shutdown-zone" in html_source
    assert 'data-danger-zone="live-shutdown"' in html_source
    assert "live-stop-action" in html_source
    assert "live-emergency-action" in html_source
    assert "live-close-all-action" in html_source
    assert "oc-toolbar-danger-action live-close-all-action" in html_source

    assert "oc-row-close-action" in js_source
    assert "openConfirmModal({" in js_source
    assert "confirmClass: 'oc-btn-destructive oc-btn-critical'" in js_source
    assert "confirmClass: 'oc-btn-danger oc-btn-critical'" in js_source

    # 原生 confirm() 禁令必須同時覆蓋 HTML 與抽出後的 JS。
    assert "confirm(" not in html_source
    assert "confirm(" not in js_source
