"""W-AUDIT-7c GUI 靜態回歸測試。

涵蓋 commit 9e265ba9 三項修復：
  1. governance-tab.js 兩個 native confirm() → openTypedConfirmModal
  2. tab-ai.html clearProviderKey native confirm() → openTypedConfirmModal
  3. tab-settings.html 拆 4 個 sub-tab（engines / system / connection / debug）

設計原則（E4 邊界）：
  - 純靜態結構/語法檢查，不 mock 業務邏輯
  - 不啟瀏覽器、不 jsdom；遵循 codebase 既有「最低線交付」pattern
  - node syntax check 透過 shutil.which 條件跳過（CI 容錯）
  - 與 test_replay_subtab_static_assets.py / test_login_redirect_contract.py 同 layer

測試案例（來自 E1a report 建議 + E4 對抗性補強）：
  CASE-01  HTML structural validity（HTMLParser 跑 3 個 tab html，stack_residue 空）
  CASE-02  JS syntax balance via brace/paren/bracket diff = 0
  CASE-03  governance-tab.js 兩個 native confirm() 殘留 grep = 0
  CASE-04  tab-ai.html native confirm() 殘留 grep = 0
  CASE-05  common.js openTypedConfirmModal helper 函數體 brace_balanced
  CASE-06  4 sub-tab open/close 平衡（engines/system/connection/debug）
  CASE-07  openTypedConfirmModal 必備 hook keys 全在位
  CASE-08  ★ E4 對抗性 catch：governance-tab.js 用 node -c 真實 ES6 SyntaxError 偵測
  CASE-09  ★ E4 對抗性 catch：common.js 用 node -c 真實 ES6 SyntaxError 偵測
  CASE-10  ocSettingsSubtabShow / Restore JS function 都存在且 balanced
"""

from __future__ import annotations

import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path

import pytest

# 路徑解析：從本檔位置往上到 control_api_v1/app/static
# tests/static/ → tests/ → control_api_v1/ → app/ → static/
_THIS_DIR = Path(__file__).resolve().parent
_STATIC_DIR = _THIS_DIR.parent.parent / "app" / "static"

_TAB_AI_HTML = _STATIC_DIR / "tab-ai.html"
_TAB_SETTINGS_HTML = _STATIC_DIR / "tab-settings.html"
_TAB_GOVERNANCE_HTML = _STATIC_DIR / "tab-governance.html"
_GOVERNANCE_TAB_JS = _STATIC_DIR / "governance-tab.js"
_COMMON_JS = _STATIC_DIR / "common.js"


def _read(path: Path) -> str:
    assert path.exists(), f"static asset 缺失：{path}"
    return path.read_text(encoding="utf-8")


# ─── HTMLParser 寬容版（接受 self-closing void elements 寫成 </tag>）──
class _LenientHTMLValidator(HTMLParser):
    """寬容版 HTML 驗證器：

    瀏覽器與 HTML5 spec 對 self-closing void element 結束標記寬容
    （`</meta>` / `</input>` 等）。本驗證器只關注 stack 收斂（最終 stack 為空）
    與「未配對的反向結束標籤」是否落在已 open 的 tag 上。
    """

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
        # <foo /> 自閉合，不入棧
        return

    def handle_endtag(self, tag: str) -> None:
        if tag in self._VOID:
            return
        if not self.stack:
            return
        if self.stack[-1] == tag:
            self.stack.pop()
        elif tag in self.stack:
            # 容忍嵌套錯位：彈到匹配為止
            while self.stack and self.stack[-1] != tag:
                self.stack.pop()
            if self.stack and self.stack[-1] == tag:
                self.stack.pop()


def _stack_residue(html: str) -> list[str]:
    v = _LenientHTMLValidator()
    v.feed(html)
    return list(v.stack)


# ─── JS 語法平衡（純文字計數，不解析 string / comment）──
def _bal(src: str, open_ch: str, close_ch: str) -> int:
    """純字元計數，不剝 string / comment；O(n) 簡易檢測。

    對 brace/paren/bracket：若 diff != 0，幾乎肯定有真實結構問題；
    若 diff == 0，在 codebase 多年實踐中與真實平衡高度相關
    （字符串內括號平均對齊，正反互抵）。
    """
    return src.count(open_ch) - src.count(close_ch)


# ─────────────────────────────────────────────────────────────
# CASE-01  HTML structural validity（3 tab html stack_residue=[]）
# ─────────────────────────────────────────────────────────────
def test_w_audit_7c_case01_html_stack_residue_empty() -> None:
    """tab-settings.html / tab-ai.html / tab-governance.html 收斂無未閉合 open 標籤。"""
    for path in (_TAB_SETTINGS_HTML, _TAB_AI_HTML, _TAB_GOVERNANCE_HTML):
        residue = _stack_residue(_read(path))
        assert residue == [], f"{path.name} 有未閉合 open tag 殘留：{residue}"


# ─────────────────────────────────────────────────────────────
# CASE-02  JS syntax balance（brace/paren/bracket diff = 0）
# ─────────────────────────────────────────────────────────────
def test_w_audit_7c_case02_js_brace_paren_bracket_diff_zero() -> None:
    """common.js / governance-tab.js {} / () / [] 全 diff = 0。"""
    for path in (_COMMON_JS, _GOVERNANCE_TAB_JS):
        src = _read(path)
        b = _bal(src, "{", "}")
        p = _bal(src, "(", ")")
        s = _bal(src, "[", "]")
        assert b == 0, f"{path.name} brace diff != 0 (got {b})"
        assert p == 0, f"{path.name} paren diff != 0 (got {p})"
        assert s == 0, f"{path.name} bracket diff != 0 (got {s})"


# ─────────────────────────────────────────────────────────────
# CASE-03  governance-tab.js native confirm() 殘留 = 0
# ─────────────────────────────────────────────────────────────
def test_w_audit_7c_case03_governance_tab_no_native_confirm() -> None:
    """W-AUDIT-7c 修復後不應再有 `if (confirm(...))` / `if (!confirm(...))` 模式。

    說明：本檢查只覆蓋頂層條件式對 `confirm(...)` 的同步使用；
    若未來工程在註釋裡提到 confirm 不會誤判（substring 含底線會被排除）。
    """
    src = _read(_GOVERNANCE_TAB_JS)
    # 排除註釋行，逐行檢查
    offenders: list[tuple[int, str]] = []
    for idx, line in enumerate(src.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("*"):
            continue
        # 只 catch 同步 native confirm() 用法
        if "if (confirm(" in line or "if (!confirm(" in line:
            offenders.append((idx, stripped))
    assert offenders == [], (
        f"governance-tab.js 仍有 native confirm() 殘留 {len(offenders)} 處：{offenders[:3]}"
    )


# ─────────────────────────────────────────────────────────────
# CASE-04  tab-ai.html native confirm() 殘留 = 0
# ─────────────────────────────────────────────────────────────
def test_w_audit_7c_case04_tab_ai_no_native_confirm() -> None:
    """tab-ai.html clearProviderKey 不應再用 native confirm()。"""
    src = _read(_TAB_AI_HTML)
    offenders: list[tuple[int, str]] = []
    for idx, line in enumerate(src.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("*"):
            continue
        if "if (confirm(" in line or "if (!confirm(" in line:
            offenders.append((idx, stripped))
    assert offenders == [], (
        f"tab-ai.html 仍有 native confirm() 殘留 {len(offenders)} 處：{offenders[:3]}"
    )


def test_tab_ai_pricing_table_reads_backend_mtok_fields() -> None:
    """Pricing table must render Layer2 PricingTable.to_dict field names."""
    src = _read(_TAB_AI_HTML)
    assert "side + '_per_mtok'" in src
    assert "mtokPrice(costs, 'input')" in src
    assert "mtokPrice(costs, 'output')" in src


# ─────────────────────────────────────────────────────────────
# CASE-05  common.js openTypedConfirmModal 函數體 brace_balanced
# ─────────────────────────────────────────────────────────────
def test_w_audit_7c_case05_open_typed_confirm_modal_helper_balanced() -> None:
    """common.js 內 openTypedConfirmModal 函數體 brace 平衡。"""
    src = _read(_COMMON_JS)
    marker = "function openTypedConfirmModal("
    start = src.find(marker)
    assert start != -1, "common.js 找不到 openTypedConfirmModal 定義"
    # 找到第一個 { 後做 brace 平衡掃描
    body_start = src.find("{", start)
    assert body_start != -1, "openTypedConfirmModal 缺少函數體 {"
    depth = 0
    end = -1
    for i in range(body_start, len(src)):
        ch = src[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    assert end != -1, "openTypedConfirmModal 函數體 brace 不平衡（無對應 }）"
    body = src[body_start : end + 1]
    # 函數體不能空
    assert len(body) > 100, f"openTypedConfirmModal 函數體過短 ({len(body)} chars)"


# ─────────────────────────────────────────────────────────────
# CASE-06  tab-settings.html 4 sub-tab open/close 平衡
# ─────────────────────────────────────────────────────────────
def test_w_audit_7c_case06_tab_settings_subtab_open_close_balanced() -> None:
    """tab-settings.html 4 sub-tab（engines/system/connection/debug）開閉計數一致。"""
    src = _read(_TAB_SETTINGS_HTML)
    for name in ("engines", "system", "connection", "debug"):
        open_marker = f'id="subtab-{name}"'
        close_marker = f"<!-- /subtab-{name} -->"
        opens = src.count(open_marker)
        closes = src.count(close_marker)
        assert opens == 1, (
            f"sub-tab '{name}' 應有 1 個 open marker（id=\"subtab-{name}\"），實得 {opens}"
        )
        assert closes == 1, (
            f"sub-tab '{name}' 應有 1 個 close marker（<!-- /subtab-{name} -->），實得 {closes}"
        )


# ─────────────────────────────────────────────────────────────
# CASE-07  openTypedConfirmModal 必備 hook keys 全在位
# ─────────────────────────────────────────────────────────────
def test_w_audit_7c_case07_open_typed_confirm_modal_hooks_present() -> None:
    """common.js openTypedConfirmModal 必備 hook 全部存在。"""
    src = _read(_COMMON_JS)
    required = [
        "function openTypedConfirmModal(",
        "oc-typed-confirm-overlay",
        "oc-tc-input",
        "oc-tc-confirm",
        "oc-tc-cancel",
        "phrase",
        "'CONFIRM'",
        "key === 'Escape'",
        "key === 'Enter'",
        "autocomplete=\"off\"",
        "autocapitalize=\"off\"",
        "spellcheck=\"false\"",
    ]
    missing = [k for k in required if k not in src]
    assert not missing, f"openTypedConfirmModal 缺少必備 hook：{missing}"


# ─────────────────────────────────────────────────────────────
# CASE-08  ★ E4 對抗性：governance-tab.js node -c 真實 ES6 syntax check
# ─────────────────────────────────────────────────────────────
def test_w_audit_7c_case08_governance_tab_js_real_syntax_check() -> None:
    """node -c 跑 governance-tab.js 真實 ES6 語法檢查。

    對抗目的：純字元 brace 計數可能 false-pass — 同 block 內
    `const ok = ...` 後 `let ok = 0` 重複宣告會在 brace diff = 0 下漏掉，
    但會在瀏覽器 / node 真實 parse 時 throw SyntaxError。
    """
    node = shutil.which("node")
    if node is None:
        pytest.skip("node 不在 PATH（CI 環境可能無 node）；跳過真實 syntax check")
    result = subprocess.run(
        [node, "--check", str(_GOVERNANCE_TAB_JS)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, (
        f"governance-tab.js node -c 失敗：\n"
        f"stderr={result.stderr.strip()[:1500]}\n"
        f"stdout={result.stdout.strip()[:500]}"
    )


# ─────────────────────────────────────────────────────────────
# CASE-09  ★ E4 對抗性：common.js node -c 真實 ES6 syntax check
# ─────────────────────────────────────────────────────────────
def test_w_audit_7c_case09_common_js_real_syntax_check() -> None:
    """node -c 跑 common.js 真實 ES6 語法檢查（含新增 openTypedConfirmModal 140 行）。"""
    node = shutil.which("node")
    if node is None:
        pytest.skip("node 不在 PATH（CI 環境可能無 node）；跳過真實 syntax check")
    result = subprocess.run(
        [node, "--check", str(_COMMON_JS)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, (
        f"common.js node -c 失敗：\n"
        f"stderr={result.stderr.strip()[:1500]}\n"
        f"stdout={result.stdout.strip()[:500]}"
    )


# ─────────────────────────────────────────────────────────────
# CASE-10  tab-settings.html 必備 sub-tab JS function + button id 在位
# ─────────────────────────────────────────────────────────────
def test_w_audit_7c_case10_settings_subtab_js_functions_present() -> None:
    """tab-settings.html 含 ocSettingsSubtabShow / Restore + 4 sub-tab nav button。"""
    src = _read(_TAB_SETTINGS_HTML)
    required = [
        "function ocSettingsSubtabShow",
        "function ocSettingsSubtabRestore",
        "settings_active_subtab",
        'id="subtab-btn-engines"',
        'id="subtab-btn-system"',
        'id="subtab-btn-connection"',
        'id="subtab-btn-debug"',
    ]
    missing = [k for k in required if k not in src]
    assert not missing, f"tab-settings.html 缺少必備 sub-tab hook：{missing}"
