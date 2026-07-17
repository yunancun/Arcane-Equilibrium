"""公開 Control Console 的 CodeQL 精準安全回歸契約。

MODULE_NOTE(為何 Node + 最小 DOM / 誠實邊界):
  本檔保護三個已被 CodeQL 定位的瀏覽器資料流：DOM 文字不得重新解讀為 HTML、登入
  跳轉只能從封閉路由常量重建、治理審批 change_id 必須經 DOM attribute round-trip 後
  原樣送往正確 action。Node harness 執行 production function bytes，並只實作本契約
  需要的最小 DOM（innerHTML attribute decode、querySelectorAll、addEventListener）；
  它不連 runtime/API/DB、不載完整瀏覽器，也不證明整頁視覺或網路行為。
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]
STATIC = (
    ROOT
    / "program_code/exchange_connectors/bybit_connector/control_api_v1/app/static"
)


def _read(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def _function(source: str, name: str) -> str:
    """用最小詞法狀態抽出普通 JS 函式。"""

    start = source.index(f"function {name}(")
    opening = source.index("{", start)
    depth = 0
    quote = ""
    escaped = False
    regex = False
    regex_class = False
    line_comment = False
    block_comment = False
    previous = ""
    for index in range(opening, len(source)):
        char = source[index]
        following = source[index + 1] if index + 1 < len(source) else ""
        if line_comment:
            if char == "\n":
                line_comment = False
            continue
        if block_comment:
            if char == "*" and following == "/":
                block_comment = False
            continue
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
            continue
        if regex:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == "[":
                regex_class = True
            elif char == "]":
                regex_class = False
            elif char == "/" and not regex_class:
                regex = False
                previous = "/"
            continue
        if char == "/" and following == "/":
            line_comment = True
            continue
        if char == "/" and following == "*":
            block_comment = True
            continue
        if char == "/" and previous in "([=,:;!&|?{}":
            regex = True
            regex_class = False
            continue
        if char in {"'", '"', "`"}:
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
        if not char.isspace():
            previous = char
    raise AssertionError(f"unterminated JavaScript function: {name}")


def test_alert_cooldown_never_reinterprets_dom_text_as_html() -> None:
    cooldown = _function(_read("tab-settings.html"), "_alertStartTestCooldown")

    assert ".innerHTML" not in cooldown
    assert "btn.textContent || ''" in cooldown
    assert "btn.textContent = original" in cooldown


@pytest.mark.skipif(shutil.which("node") is None, reason="node is required")
def test_alert_cooldown_restores_hostile_label_as_text_only() -> None:
    cooldown = _function(_read("tab-settings.html"), "_alertStartTestCooldown")
    hostile = '<img src=x onerror="globalThis.__xss = true">'
    script = f"""
let _ocAlertTestCooldownIv = null;
let innerHtmlWrites = 0;
const hostile = {json.dumps(hostile)};
const attrs = new Map();
const button = {{
  disabled: false,
  _text: hostile,
  get textContent() {{ return this._text; }},
  set textContent(value) {{ this._text = String(value); }},
  get innerHTML() {{ throw new Error('innerHTML read'); }},
  set innerHTML(_value) {{ innerHtmlWrites += 1; globalThis.__xss = true; }},
  getAttribute(name) {{ return attrs.has(name) ? attrs.get(name) : null; }},
  setAttribute(name, value) {{ attrs.set(name, String(value)); }},
}};
const document = {{ getElementById(id) {{ return id === 'alert-test-btn' ? button : null; }} }};
const clearInterval = () => {{}};
const setInterval = () => 1;
{cooldown}
_alertStartTestCooldown(0);
if (button.textContent !== hostile) throw new Error('hostile label did not round-trip as text');
if (attrs.get('data-orig-label') !== hostile) throw new Error('stored label changed');
if (innerHtmlWrites !== 0 || globalThis.__xss === true) throw new Error('label was interpreted as HTML');
"""
    result = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_login_redirects_are_reconstructed_from_a_closed_route_allowlist() -> None:
    redirect = _function(_read("login.html"), "safeRedirectTarget")

    assert "target.origin !== window.location.origin" in redirect
    assert "return value" not in redirect
    assert "return target.pathname" not in redirect
    assert "return target.href" not in redirect
    assert "return target;" not in redirect
    for route in ("/", "/gui", "/console", "/console/legacy", "/trading"):
        assert f"return '{route}'" in redirect


def test_both_login_redirect_sinks_consume_only_the_validated_target() -> None:
    login = _read("login.html")

    assert login.count("const redirect = loginRedirectTarget();") == 2
    assert login.count("window.location.href = redirect;") == 2


@pytest.mark.skipif(shutil.which("node") is None, reason="node is required")
def test_login_redirect_allowlist_rejects_host_and_parser_confusion() -> None:
    redirect = _function(_read("login.html"), "safeRedirectTarget")
    cases = {
        "https://evil.example/console": "",
        "//evil.example/console": "",
        "/\\evil.example/console": "",
        "/%2f%2fevil.example/console": "/",
        "/%5cevil.example/console": "/",
        "/login": "/",
        "/static/console.html": "/",
        "/not-a-console-route": "/",
        "/": "/",
        "/gui": "/gui",
        "/console": "/console",
        "/console/legacy": "/console/legacy",
        "/trading": "/trading",
        "/trading?embed=1": "/trading?embed=1",
        "/trading?embed=0&next=//evil.example": "/trading",
        "/console?next=//evil.example": "/console",
    }
    script = f"""
const window = {{ location: {{ origin: 'https://console.example' }} }};
{redirect}
const cases = {json.dumps(cases)};
for (const [input, expected] of Object.entries(cases)) {{
  const actual = safeRedirectTarget(input);
  if (actual !== expected) {{
    throw new Error(JSON.stringify({{ input, expected, actual }}));
  }}
}}
"""
    result = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_audit_actions_use_dom_bound_ids_instead_of_inline_javascript() -> None:
    render = _function(_read("governance-tab.js"), "renderPendingAudit")

    assert "cidJs" not in render
    assert "onclick=" not in render
    assert 'data-audit-action="approve"' in render
    assert 'data-audit-action="reject"' in render
    assert 'data-change-id="' in render
    assert "querySelectorAll('[data-audit-action][data-change-id]')" in render
    assert "button.addEventListener('click'" in render
    assert "auditApprove(changeId)" in render
    assert "auditReject(changeId)" in render


@pytest.mark.skipif(shutil.which("node") is None, reason="node is required")
def test_audit_dom_round_trip_dispatches_exact_id_and_unknown_is_noop() -> None:
    render = _function(_read("governance-tab.js"), "renderPendingAudit")
    escape_html = _function(_read("common-formatters.js"), "ocEsc")
    hostile = "change\\'\"<img src=x onerror=globalThis.__xss=true>&\nnext"
    script = f"""
{escape_html}

function decodeHtml(value) {{
  return value
    .replace(/&#39;/g, "'")
    .replace(/&quot;/g, '"')
    .replace(/&gt;/g, '>')
    .replace(/&lt;/g, '<')
    .replace(/&amp;/g, '&');
}}

class FakeButton {{
  constructor(action, changeId) {{
    this.attrs = new Map([
      ['data-audit-action', decodeHtml(action)],
      ['data-change-id', decodeHtml(changeId)],
    ]);
    this.listeners = new Map();
  }}
  getAttribute(name) {{ return this.attrs.has(name) ? this.attrs.get(name) : null; }}
  setAttribute(name, value) {{ this.attrs.set(name, String(value)); }}
  addEventListener(type, listener) {{ this.listeners.set(type, listener); }}
  click() {{ const listener = this.listeners.get('click'); if (listener) listener(); }}
}}

class FakeContainer {{
  constructor() {{ this.buttons = []; this._html = ''; }}
  set innerHTML(value) {{
    this._html = String(value);
    this.buttons = [];
    const pattern = /<button\\b[^>]*data-audit-action="([^"]*)"[^>]*data-change-id="([^"]*)"[^>]*>/g;
    let match;
    while ((match = pattern.exec(this._html)) !== null) {{
      this.buttons.push(new FakeButton(match[1], match[2]));
    }}
  }}
  get innerHTML() {{ return this._html; }}
  querySelectorAll(selector) {{
    if (selector !== '[data-audit-action][data-change-id]') throw new Error('unexpected selector');
    return this.buttons;
  }}
}}

const content = new FakeContainer();
const bulk = {{ classList: {{ add() {{}}, remove() {{}} }} }};
const document = {{
  getElementById(id) {{
    if (id === 'pending-audit-content') return content;
    if (id === 'btn-bulk-actions') return bulk;
    return null;
  }},
}};
const _APPROVAL_STATUS_CN = {{}};
const ocChip = () => '';
const _translateWhat = value => String(value || '');
const _getApprovalGuidance = () => null;
const _formatValue = value => String(value);
const _translateComp = value => String(value);
const _changeTypeBadge = () => '';
const ocTime = () => '';
const _translateWho = value => String(value || '');
const approved = [];
const rejected = [];
function auditApprove(changeId) {{ approved.push(changeId); }}
function auditReject(changeId) {{ rejected.push(changeId); }}

{render}
const hostile = {json.dumps(hostile)};
renderPendingAudit([{{
  change_id: hostile,
  approval_status: 'PENDING',
  change_type: 'test',
  what: 'test',
  who: 'tester',
}}]);
if (content.buttons.length !== 2) throw new Error('expected approve/reject buttons');
const approve = content.buttons.find(button => button.getAttribute('data-audit-action') === 'approve');
const reject = content.buttons.find(button => button.getAttribute('data-audit-action') === 'reject');
if (!approve || !reject) throw new Error('missing action button');
if (approve.getAttribute('data-change-id') !== hostile || reject.getAttribute('data-change-id') !== hostile) {{
  throw new Error('change_id did not survive the DOM attribute round-trip');
}}
approve.click();
reject.click();
if (approved.length !== 1 || approved[0] !== hostile) throw new Error('approve did not receive original id');
if (rejected.length !== 1 || rejected[0] !== hostile) throw new Error('reject did not receive original id');
approve.setAttribute('data-audit-action', 'future-action');
approve.click();
if (approved.length !== 1 || rejected.length !== 1) throw new Error('unknown action was not a no-op');
if (globalThis.__xss === true) throw new Error('malicious id executed');
"""
    result = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
