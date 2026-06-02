"""ocApi background polling error policy tests.

這組測試鎖住 GUI only 行為：背景輪詢的 client-side abort/timeout 不應反覆
彈右下角全局 toast；交易/授權後端邏輯不在本檔 scope。
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest


_test_dir = Path(os.path.abspath(__file__)).parent
_static_dir = _test_dir.parent.parent / "app" / "static"


def _run_node_harness(js_body: str) -> subprocess.CompletedProcess[str]:
    if not shutil.which("node"):
        pytest.skip("node not available in test env")
    return subprocess.run(
        ["node", "-e", js_body],
        capture_output=True,
        text=True,
        timeout=15,
    )


def _read_static(*parts: str) -> str:
    return _static_dir.joinpath(*parts).read_text(encoding="utf-8")


def _common_harness_prefix() -> str:
    common_src = _read_static("common.js")
    return (
        "globalThis.window = globalThis;"
        "globalThis.localStorage = { getItem: () => null, setItem: () => {}, removeItem: () => {} };"
        "globalThis.sessionStorage = { setItem: () => {} };"
        "globalThis.document = { cookie: '', body: {}, head: { appendChild: () => {} },"
        "  createElement: () => ({"
        "    classList: { add: () => {}, remove: () => {} },"
        "    style: {}, remove: () => {}"
        "  }), querySelectorAll: () => [], getElementById: () => null };"
        "globalThis.addEventListener = () => {};"
        "globalThis.dispatchEvent = () => {};"
        "globalThis.CustomEvent = function(name, opts) { return { name, opts }; };"
        "globalThis.location = { pathname: '/console', search: '', href: '', reload: () => {} };"
        "globalThis.AbortSignal = { timeout: (ms) => ({ timeoutMs: ms }) };"
        f"{common_src}"
        "let toasts = [];"
        "ocToast = (msg, type) => { toasts.push({ msg, type }); };"
    )


def test_ocapi_does_not_toast_client_abort_errors() -> None:
    """AbortError 是 client-side 中止，不代表 API 斷線，不應彈全局 toast。"""
    harness = (
        _common_harness_prefix()
        + "globalThis.fetch = () => {"
        "  const err = new Error('The user aborted a request.');"
        "  err.name = 'AbortError';"
        "  return Promise.reject(err);"
        "};"
        "(async () => {"
        "  const result = await ocApi('/api/v1/strategy/scanner/opportunities');"
        "  if (result !== null) { console.error('FAIL result=' + JSON.stringify(result)); process.exit(1); }"
        "  if (toasts.length !== 0) { console.error('FAIL toasts=' + JSON.stringify(toasts)); process.exit(1); }"
        "  process.exit(0);"
        "})();"
    )
    result = _run_node_harness(harness)
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"


def test_ocapi_can_suppress_background_get_timeout_toasts() -> None:
    """背景只讀輪詢可選擇局部降級，不把 timeout 包裝成全局 API 斷線 toast。"""
    harness = (
        _common_harness_prefix()
        + "globalThis.fetch = (_path, _opts) => {"
        "  const err = new Error('signal timed out');"
        "  err.name = 'TimeoutError';"
        "  return Promise.reject(err);"
        "};"
        "(async () => {"
        "  const result = await ocApi('/api/v1/live/pnl-series?range=24h', { toastOnError: false });"
        "  if (result !== null) { console.error('FAIL result=' + JSON.stringify(result)); process.exit(1); }"
        "  if (toasts.length !== 0) { console.error('FAIL toasts=' + JSON.stringify(toasts)); process.exit(1); }"
        "  process.exit(0);"
        "})();"
    )
    result = _run_node_harness(harness)
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"


def test_ocapi_timeout_ms_option_is_passed_to_abort_signal() -> None:
    """慢只讀端點可以延長前端 timeout，不改後端實質執行。"""
    harness = (
        _common_harness_prefix()
        + "let seenTimeout = null;"
        "globalThis.AbortSignal = { timeout: (ms) => { seenTimeout = ms; return { timeoutMs: ms }; } };"
        "globalThis.fetch = (_path, opts) => Promise.resolve({"
        "  ok: true,"
        "  clone() { return this; },"
        "  json: () => Promise.resolve({ ok: true, signalTimeout: opts.signal.timeoutMs })"
        "});"
        "(async () => {"
        "  const result = await ocApi('/api/v1/strategy/prelive/edge-gates?window_days=7', {"
        "    toastOnError: false,"
        "    timeoutMs: 15000"
        "  });"
        "  if (!result || result.signalTimeout !== 15000 || seenTimeout !== 15000) {"
        "    console.error('FAIL result=' + JSON.stringify(result) + ' seen=' + seenTimeout);"
        "    process.exit(1);"
        "  }"
        "  process.exit(0);"
        "})();"
    )
    result = _run_node_harness(harness)
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"


def test_live_background_pollers_opt_out_of_global_error_toasts() -> None:
    """Live 背景面板的慢查詢必須 opt out，避免 operator 看到重複全局錯誤。"""
    live_src = _read_static("tab-live.js")
    assert (
        "ocApi('/api/v1/live/pnl-series?range=' + encodeURIComponent(_livePnlRange), "
        "{ toastOnError: false, timeoutMs: 15000 })"
    ) in live_src
    assert (
        "ocApi('/api/v1/strategy/prelive/edge-gates?window_days=7', "
        "{ toastOnError: false, timeoutMs: 15000 })"
    ) in live_src
