"""W-AUDIT-9 T5 GUI 靜態回歸測試。

範圍 — AMD-2026-05-09-03 §4.3 Graduated Canary Cohort GUI surface land：
  1. tab-governance.html 加 Graduated Canary section + canary-tab.js script tag
  2. canary-tab.js 渲染 5-stage ladder + active cohort grid + manual promote 按鈕
  3. 後端 governance_canary_routes.py routes 註冊在 main.py（GUI 接口齊全）

設計原則：
  - 純靜態結構檢查，不啟瀏覽器
  - node --check 條件跳過（CI 容錯）
  - 沿用 test_w_audit_7c_typed_confirm_modal.py lenient HTMLParser pattern

測試案例：
  CASE-01  tab-governance.html 結構合法（lenient HTMLParser 收斂）
  CASE-02  canary-tab.js syntax balance（{}/()/[]）
  CASE-03  canary-tab.js node --check（真 V8 parser；未裝 node 跳過）
  CASE-04  Graduated Canary section 必備 DOM ID 全在位
  CASE-05  canary-tab.js 必備函式 + window.loadCanaryCohorts 暴露
  CASE-06  CSS class 必備（5 stage chip + cohort card + progress bar）
  CASE-07  XSS 防護：canary-tab.js 用 ocEsc / ocSanitizeClass 包動態值
  CASE-08  manual_promote endpoint 必經 LeaseScope::CanaryStagePromotion
           常數對齊 Rust audit_str
  CASE-09  governance_canary_routes.py 註冊在 main.py
  CASE-10  WCAG 2.1 AA：mobile 44px touch target retrofit + role/aria-label
  CASE-11  typed-confirm phrase = 'PROMOTE'（case-sensitive，per CLAUDE.md
           §五 audit-aware 三原則）
"""

from __future__ import annotations

import re
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path

import pytest

_THIS_DIR = Path(__file__).resolve().parent
_STATIC_DIR = _THIS_DIR.parent.parent / "app" / "static"
_APP_DIR = _THIS_DIR.parent.parent / "app"

_TAB_GOVERNANCE_HTML = _STATIC_DIR / "tab-governance.html"
_CANARY_TAB_JS = _STATIC_DIR / "canary-tab.js"
_MAIN_PY = _APP_DIR / "main.py"
_CANARY_ROUTES_PY = _APP_DIR / "governance_canary_routes.py"


def _read(path: Path) -> str:
    assert path.exists(), f"static asset 缺失：{path}"
    return path.read_text(encoding="utf-8")


# ─── lenient HTMLParser ────────────────────────────────────────────────────
class _LenientHTMLValidator(HTMLParser):
    _VOID = {
        "br", "hr", "img", "input", "meta", "link", "source", "track",
        "wbr", "area", "base", "col", "embed", "param",
    }

    def __init__(self) -> None:
        super().__init__()
        self.stack: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag not in self._VOID:
            self.stack.append(tag)

    def handle_startendtag(self, tag: str, attrs) -> None:
        return

    def handle_endtag(self, tag: str) -> None:
        if tag in self._VOID:
            return
        # 一般 tag：找 stack 內最近 match 處 pop
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i] == tag:
                self.stack = self.stack[:i]
                return
        # 找不到 match：忽略（lenient）


def _strip_js_comments_strings(src: str) -> str:
    """剝離 JS 注釋 + 字串字面值，保留結構 brace/paren/bracket 給 balance check。"""
    out = []
    i = 0
    n = len(src)
    while i < n:
        c = src[i]
        if c == "/" and i + 1 < n and src[i + 1] == "/":
            while i < n and src[i] != "\n":
                i += 1
            continue
        if c == "/" and i + 1 < n and src[i + 1] == "*":
            i += 2
            while i + 1 < n and not (src[i] == "*" and src[i + 1] == "/"):
                i += 1
            i += 2
            continue
        if c in ('"', "'", "`"):
            q = c
            i += 1
            while i < n and src[i] != q:
                if src[i] == "\\" and i + 1 < n:
                    i += 2
                    continue
                i += 1
            i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


# ════════════════════════════════════════════════════════════════════════════
# Test Cases
# ════════════════════════════════════════════════════════════════════════════

class TestCanaryGuiAssets:
    def test_tab_governance_html_structure_valid(self):
        """CASE-01: tab-governance.html lenient HTMLParser 收斂 stack=0"""
        validator = _LenientHTMLValidator()
        validator.feed(_read(_TAB_GOVERNANCE_HTML))
        assert validator.stack == [], (
            f"tab-governance.html stack residue: {validator.stack}"
        )

    def test_canary_tab_js_balance(self):
        """CASE-02: canary-tab.js {}/()/[] diff = 0"""
        src = _strip_js_comments_strings(_read(_CANARY_TAB_JS))
        for op, cl, name in [
            ("{", "}", "braces"),
            ("(", ")", "parens"),
            ("[", "]", "squares"),
        ]:
            assert src.count(op) == src.count(cl), (
                f"canary-tab.js {name} diff: {src.count(op)} vs {src.count(cl)}"
            )

    def test_canary_tab_js_node_check(self):
        """CASE-03: canary-tab.js node --check 跑 V8 parser 確認真 syntax 合法。

        若 node 未裝（CI 環境），跳過。
        """
        node_bin = shutil.which("node")
        if not node_bin:
            pytest.skip("node not installed; falling back to brace balance only")
        result = subprocess.run(
            [node_bin, "--check", str(_CANARY_TAB_JS)],
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert result.returncode == 0, (
            f"node --check fail: rc={result.returncode} stderr={result.stderr}"
        )

    def test_canary_section_dom_ids_present(self):
        """CASE-04: Graduated Canary section 必備 DOM ID 全在位"""
        html = _read(_TAB_GOVERNANCE_HTML)
        required_ids = [
            'id="canary-status-card"',
            'id="canary-stage-ladder"',
            'id="canary-cohort-list"',
            'id="canary-metric-registry-section"',
            'id="canary-metric-registry"',
        ]
        for needle in required_ids:
            assert needle in html, f"tab-governance.html 缺 DOM ID: {needle}"

    def test_canary_tab_js_function_exposure(self):
        """CASE-05: canary-tab.js 必備函式 + window.loadCanaryCohorts 暴露"""
        js = _read(_CANARY_TAB_JS)
        # 暴露 API
        assert "window.loadCanaryCohorts" in js, (
            "canary-tab.js 必暴露 window.loadCanaryCohorts 供 governance-tab 呼叫"
        )
        assert "window.OpenClawCanary" in js
        # 內部關鍵 helper
        assert "_renderStageLadder" in js
        assert "_renderCohortList" in js
        assert "_renderMetricRegistry" in js
        assert "_formatObservationProgress" in js
        assert "_onPromoteClick" in js

    def test_canary_css_classes_present(self):
        """CASE-06: tab-governance.html style 區塊含 canary 5-stage / cohort CSS"""
        html = _read(_TAB_GOVERNANCE_HTML)
        required_css = [
            ".canary-stage-ladder",
            ".canary-stage-chip",
            ".canary-cohort-grid",
            ".canary-cohort-card",
            ".canary-stage-badge",
            ".canary-progress-bar-wrap",
            ".canary-progress-bar-fill",
            ".canary-promote-btn",
        ]
        for selector in required_css:
            assert selector in html, f"tab-governance.html 缺 CSS class: {selector}"

    def test_canary_js_xss_protection(self):
        """CASE-07: canary-tab.js 動態 HTML 必過 ocEsc / ocSanitizeClass

        檢查 (1) 至少 N 處 ocEsc 呼叫 (2) ocSanitizeClass 必呼叫 (3) 每個
        innerHTML 賦值點往前 1500 char window（同 function body）能找到
        ocEsc 或屬靜態 placeholder（loading / fallback）字面值。
        """
        js = _read(_CANARY_TAB_JS)
        # 至少幾處 ocEsc + 必有 ocSanitizeClass
        assert js.count("ocEsc(") >= 8, (
            f"canary-tab.js 動態 HTML 必過 ocEsc 防 XSS（>=8 處，實際 {js.count('ocEsc(')}）"
        )
        assert "ocSanitizeClass(" in js, (
            "canary-tab.js 動態 class 必過 ocSanitizeClass 防 XSS"
        )
        # 每個 innerHTML 賦值點，向前 1500 char 視窗（同 function body）必含
        # ocEsc 呼叫或為靜態 placeholder（loading / fallback empty state）
        static_placeholders = (
            "Loading", "尚無 active cohort", "metric registry 為空",
        )
        for m in re.finditer(r"innerHTML\s*=", js):
            # 向後看 800 char 取賦值的 RHS 上下文
            tail = js[m.end(): m.end() + 800]
            # 向前看 1500 char 取所在 function body（catch html var 構造處）
            head = js[max(0, m.start() - 1500): m.start()]
            ok = (
                "ocEsc(" in tail
                or "ocEsc(" in head
                or any(p in tail for p in static_placeholders)
            )
            assert ok, (
                f"canary-tab.js innerHTML 賦值缺 ocEsc 防護於 offset {m.end()}; "
                f"tail head: {tail[:120]!r}"
            )

    def test_lease_scope_constants(self):
        """CASE-08: manual_promote 走 LeaseScope::CanaryStagePromotion + TTL 60s"""
        py = _read(_CANARY_ROUTES_PY)
        # AMD §4.5 strict 60s
        assert "60.0" in py, "TTL 必為 60.0 秒（AMD §4.5 strict）"
        assert '"CanaryStagePromotion"' in py, (
            "scope 必為字面值 'CanaryStagePromotion' 對齊 Rust LeaseScope audit_str"
        )
        # transition_kind 對齊 V080 CHECK constraint
        assert '"manual_promote"' in py
        # SHADOW_BYPASS sentinel 拒絕邏輯
        assert "SHADOW_BYPASS:" in py
        assert "_is_shadow_bypass_lease" in py

    def test_main_py_registers_canary_routes(self):
        """CASE-09: main.py import governance_canary_routes（觸發 decorator 註冊）"""
        main_py = _read(_MAIN_PY)
        assert "governance_canary_routes" in main_py, (
            "main.py 必 import governance_canary_routes 觸發 decorator 註冊"
        )

    def test_a11y_baseline(self):
        """CASE-10: WCAG 2.1 AA mobile 44px touch + role/aria-label baseline"""
        html = _read(_TAB_GOVERNANCE_HTML)
        # canary section 必有 role + aria-label / aria-disabled / progressbar
        assert 'aria-label="Graduated canary 5 stage ladder"' in html
        assert 'aria-label="Active canary cohorts"' in html
        # mobile 44px touch retrofit
        assert "min-height: 44px" in html, (
            "canary promote button 必有 mobile 44px touch target retrofit"
        )

        js = _read(_CANARY_TAB_JS)
        # progressbar role + aria-valuemin/max/now
        assert 'role="progressbar"' in js
        assert 'aria-valuemin="0"' in js
        assert 'aria-valuemax="100"' in js
        # cohort card region role
        assert 'role="region"' in js

    def test_typed_confirm_phrase_promote(self):
        """CASE-11: typed-confirm phrase = 'PROMOTE'（case-sensitive）"""
        js = _read(_CANARY_TAB_JS)
        assert "CANARY_PROMOTE_PHRASE = 'PROMOTE'" in js, (
            "manual promote typed-confirm phrase 必為 'PROMOTE' (case-sensitive)，"
            "對齊 governance ux-checklist §5 audit-aware 三原則"
        )
        # phrase 喂入 openTypedConfirmModal options 而非 hardcoded 比對
        assert "phrase: CANARY_PROMOTE_PHRASE" in js

    def test_no_native_confirm_in_canary(self):
        """CASE-12: canary-tab.js 不可用 native confirm()（W-AUDIT-7c lesson）

        Critical 寫操作不可走 native confirm；必走 openTypedConfirmModal。
        允許 window.prompt() 用於 reason 輸入（reason 不是 critical phrase 故
        用 simple prompt 的 settings tab restart pattern 一致）。
        """
        js = _read(_CANARY_TAB_JS)
        # 不可有 native confirm() — grep 'confirm(' 但允許 'openTypedConfirmModal' /
        # 'confirmLabel' / 'confirmClass' / 'confirmation' 等子字串
        for m in re.finditer(r"\bconfirm\s*\(", js):
            # 看前 30 char 是否有 openTyped / 註釋
            head = js[max(0, m.start() - 30): m.start()]
            assert (
                "openTyped" in head
                or "openType" in head
            ), f"canary-tab.js native confirm() 禁用，offset={m.start()}"
