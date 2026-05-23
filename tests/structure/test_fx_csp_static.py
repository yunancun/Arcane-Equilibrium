from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CONTROL_API = REPO_ROOT / "program_code/exchange_connectors/bybit_connector/control_api_v1"


def test_common_js_uses_same_origin_fx_proxy() -> None:
    """GUI 匯率刷新不能在瀏覽器直連第三方，避免 CSP connect-src 漂移。"""
    source = (CONTROL_API / "app/static/common.js").read_text(encoding="utf-8")
    assert "api.coingecko.com" not in source
    assert "ocApi('/api/v1/system/fx-rates')" in source


def test_csp_connect_src_stays_self_only() -> None:
    """匯率代理不得靠放寬 CSP 解決。"""
    source = (CONTROL_API / "app/main_legacy.py").read_text(encoding="utf-8")
    assert '"connect-src \'self\'; "' in source
    assert "api.coingecko.com" not in source
