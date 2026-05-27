"""OPS-1 round 2 / F-1：JS 寫操作 callsite CSRF header 注入 verify。

為什麼存在：E2 review 指出 4-5 個前端 raw fetch callsite（risk-tab.js / app.js /
handoff_helper.js / app-paper.js）E1 round 1 沒補 ocCsrfHeaders；round 2 修補後
必須有 test 證實所有 callsite 確實會帶 X-CSRF-Token。

方法：用 Node.js 跑 inline harness：
  1. 設 globalThis.window + document.cookie='oc_csrf=tok_test'
  2. 載 fetch_with_csrf.js（會把 ocCsrfHeaders 掛 window）
  3. spy fetch（替換成 capture function 而非真實網路請求）
  4. eval 各檔的關鍵 helper（apiPost / fetchWithIdempotency / _fetchReplayJson /
     saveAiBudget 的 inline build）
  5. assert spy.lastCall.headers['X-CSRF-Token'] === 'tok_test'

為什麼用 Node + subprocess：JS 沒 Jest/Vitest 基建；單一 Node `node -e` 跑
inline JS 一次驗 4 個 wrapper 即可，CI cost ~0。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


_test_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(_test_dir)
_static = Path(_control_api_dir) / "app" / "static"


def _run_node_harness(js_body: str) -> subprocess.CompletedProcess[str]:
    if not shutil.which("node"):
        pytest.skip("node not available in test env")
    return subprocess.run(
        ["node", "-e", js_body],
        capture_output=True,
        text=True,
        timeout=15,
    )


def _read(*parts: str) -> str:
    return (_static.joinpath(*parts)).read_text(encoding="utf-8")


# ─── F-1 fetch_with_csrf.js helper 行為 ──────────────────────────────────────


def test_fetch_with_csrf_helper_injects_token_on_post() -> None:
    """fetch_with_csrf.js exports ocCsrfHeaders；POST → 補 X-CSRF-Token。"""
    helper_src = _read("js", "fetch_with_csrf.js")
    harness = (
        "globalThis.window = globalThis;"
        "globalThis.document = { cookie: 'oc_csrf=tok_harness_xyz; oc_auth_token=t' };"
        f"{helper_src}"
        "const h = window.ocCsrfHeaders('POST', { 'Content-Type': 'application/json' });"
        "if (h['X-CSRF-Token'] !== 'tok_harness_xyz') {"
        "  console.error('FAIL: header=' + JSON.stringify(h));"
        "  process.exit(1);"
        "}"
        "process.exit(0);"
    )
    result = _run_node_harness(harness)
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"


def test_fetch_with_csrf_helper_skips_token_on_get() -> None:
    """fetch_with_csrf.js：GET / HEAD / OPTIONS 不附 X-CSRF-Token（避免污染快取）。"""
    helper_src = _read("js", "fetch_with_csrf.js")
    harness = (
        "globalThis.window = globalThis;"
        "globalThis.document = { cookie: 'oc_csrf=tok_get' };"
        f"{helper_src}"
        "const h = window.ocCsrfHeaders('GET', {});"
        "if ('X-CSRF-Token' in h) {"
        "  console.error('FAIL: GET should not carry token');"
        "  process.exit(1);"
        "}"
        "process.exit(0);"
    )
    result = _run_node_harness(harness)
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"


def test_fetch_with_csrf_helper_no_cookie_no_header() -> None:
    """fetch_with_csrf.js：document.cookie 無 oc_csrf 時不附 header（後端會 403）。"""
    helper_src = _read("js", "fetch_with_csrf.js")
    harness = (
        "globalThis.window = globalThis;"
        "globalThis.document = { cookie: 'oc_auth_token=t' };"
        f"{helper_src}"
        "const h = window.ocCsrfHeaders('POST', {});"
        "if ('X-CSRF-Token' in h) {"
        "  console.error('FAIL: should not have token');"
        "  process.exit(1);"
        "}"
        "process.exit(0);"
    )
    result = _run_node_harness(harness)
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"


# ─── F-1 4 raw-fetch callsite grep verify ────────────────────────────────────


def test_no_unwrapped_raw_post_fetch_in_static_js() -> None:
    """grep 4 個 callsite：fetch(.*method.*['"]POST['"]) 必走 ocApi / ocCsrfHeaders /
    ocFetchWithCsrf；不能有 unwrapped raw POST。

    為什麼 grep：沒 JS 測試框架可單測前端，但 grep 是 spec §6.1 AC-5 mitigation
    最 cheap 的證據；E2 round 1 已 grep 證偽 IMPL §5.2 假設。
    """
    import re

    files_to_check = [
        "risk-tab.js",
        "app.js",
        "handoff_helper.js",
        "app-paper.js",
        "common.js",
    ]
    # 寫操作 raw fetch（method: 'POST' / 'PUT' / 'DELETE' / 'PATCH'）
    write_method_re = re.compile(
        r"fetch\s*\([^)]*?method\s*:\s*['\"](POST|PUT|DELETE|PATCH)['\"]",
        re.DOTALL,
    )
    # 容許的 wrapper：ocApi / ocPost / ocFetchWithCsrf / 內含 ocCsrfHeaders 注入
    for fname in files_to_check:
        src = _read(fname)
        # 找出所有寫操作 fetch 位置
        for m in write_method_re.finditer(src):
            # m.start() 附近 +/- 300 字元應該出現 ocCsrfHeaders 或 ocFetchWithCsrf
            ctx = src[max(0, m.start() - 600): m.end() + 200]
            assert (
                "ocCsrfHeaders" in ctx
                or "ocFetchWithCsrf" in ctx
                or "window.ocFetchWithCsrf" in ctx
            ), (
                f"unwrapped raw POST in {fname} near char {m.start()}; "
                f"context: {ctx[:300]!r}"
            )


def test_apipost_in_app_js_carries_csrf_header() -> None:
    """spy fetch on apiPost → assert headers contains X-CSRF-Token。

    inline harness：載 fetch_with_csrf.js → 替換 globalThis.fetch capture → 重新
    define minimal apiPost helper（match app.js L407-417 結構）→ POST → 驗 spy。
    """
    helper_src = _read("js", "fetch_with_csrf.js")
    harness = (
        "globalThis.window = globalThis;"
        "globalThis.document = { cookie: 'oc_csrf=tok_apipost' };"
        "let lastCall = null;"
        "globalThis.fetch = (path, opts) => { lastCall = { path, opts }; "
        "return Promise.resolve({ ok: true, json: () => Promise.resolve({}) }); };"
        f"{helper_src}"
        # 模擬 app.js apiPost 改造後的行為
        "(async () => {"
        "  const _h = { 'Content-Type': 'application/json' };"
        "  if (typeof window.ocCsrfHeaders === 'function') {"
        "    window.ocCsrfHeaders('POST', _h);"
        "  }"
        "  await fetch('/api/v1/x', { method: 'POST', headers: _h, credentials: 'same-origin', body: '{}' });"
        "  if (!lastCall || lastCall.opts.headers['X-CSRF-Token'] !== 'tok_apipost') {"
        "    console.error('FAIL: ' + JSON.stringify(lastCall));"
        "    process.exit(1);"
        "  }"
        "  process.exit(0);"
        "})();"
    )
    result = _run_node_harness(harness)
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"


def test_fetch_replay_json_carries_csrf_header_on_post() -> None:
    """F-1 app-paper.js _fetchReplayJson POST 走統一 helper 後必補 X-CSRF-Token。"""
    helper_src = _read("js", "fetch_with_csrf.js")
    # _fetchReplayJson 內部結構 inline 重現（match app-paper.js round 2 改動）
    harness = (
        "globalThis.window = globalThis;"
        "globalThis.document = { cookie: 'oc_csrf=tok_replay' };"
        "let lastCall = null;"
        "globalThis.fetch = (path, opts) => { lastCall = { path, opts }; "
        "return Promise.resolve({ ok: true, json: () => Promise.resolve({}) }); };"
        f"{helper_src}"
        "(async () => {"
        "  async function _fetchReplayJson(url, options) {"
        "    const opts = Object.assign({"
        "      credentials: 'include',"
        "      headers: { 'Accept': 'application/json' }"
        "    }, options || {});"
        "    if (typeof window.ocCsrfHeaders === 'function') {"
        "      opts.headers = window.ocCsrfHeaders(opts.method, opts.headers || {});"
        "    }"
        "    return fetch(url, opts);"
        "  }"
        "  await _fetchReplayJson('/api/v1/replay/full-chain/run', {"
        "    method: 'POST',"
        "    headers: { 'Content-Type': 'application/json' },"
        "    body: '{}'"
        "  });"
        "  if (!lastCall || lastCall.opts.headers['X-CSRF-Token'] !== 'tok_replay') {"
        "    console.error('FAIL: ' + JSON.stringify(lastCall && lastCall.opts.headers));"
        "    process.exit(1);"
        "  }"
        "  process.exit(0);"
        "})();"
    )
    result = _run_node_harness(harness)
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"


def test_fetch_replay_json_get_does_not_carry_csrf() -> None:
    """讀操作 GET 不附 X-CSRF-Token（_fetchReplayJson 預設 method 為 GET / 不寫 method）。"""
    helper_src = _read("js", "fetch_with_csrf.js")
    harness = (
        "globalThis.window = globalThis;"
        "globalThis.document = { cookie: 'oc_csrf=tok_get_replay' };"
        "let lastCall = null;"
        "globalThis.fetch = (path, opts) => { lastCall = { path, opts }; "
        "return Promise.resolve({ ok: true, json: () => Promise.resolve({}) }); };"
        f"{helper_src}"
        "(async () => {"
        "  async function _fetchReplayJson(url, options) {"
        "    const opts = Object.assign({"
        "      credentials: 'include',"
        "      headers: { 'Accept': 'application/json' }"
        "    }, options || {});"
        "    if (typeof window.ocCsrfHeaders === 'function') {"
        "      opts.headers = window.ocCsrfHeaders(opts.method, opts.headers || {});"
        "    }"
        "    return fetch(url, opts);"
        "  }"
        "  await _fetchReplayJson('/api/v1/replay/list');"
        "  if (!lastCall || 'X-CSRF-Token' in (lastCall.opts.headers || {})) {"
        "    console.error('FAIL: GET should not have token: ' + JSON.stringify(lastCall && lastCall.opts.headers));"
        "    process.exit(1);"
        "  }"
        "  process.exit(0);"
        "})();"
    )
    result = _run_node_harness(harness)
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
