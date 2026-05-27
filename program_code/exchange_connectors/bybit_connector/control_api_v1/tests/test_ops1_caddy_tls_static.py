"""OPS-1 Track A 整合測試：Caddy + Tailscale cert 跨平台靜態檢查。

為什麼是 static check 而非 runtime：Caddy 真正啟動需要 root + sudo + 已 up 的
Tailscale + 真實 cert，Mac sandbox 無法滿足；spec §7.3 列為 Linux-only
integration test。本檔做：
  - AC-9 Mac portability：所有新增 helper / template / unit 沒有硬編碼
    `/home/ncyu` / `/Users/ncyu` 路徑
  - Caddyfile.template 必含必要 reverse-proxy directive
  - systemd unit 必引用 lib/tls_cert.sh 而非寫死路徑
  - install_caddy.sh dry-run 預設不寫檔
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


_test_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(_test_dir)
_repo_root = Path(_control_api_dir).parents[3]
_helper_scripts = _repo_root / "helper_scripts"


def test_ac9_no_hardcoded_user_paths_in_new_files() -> None:
    """AC-9 跨平台：新增 4 個 OPS-1 Track A 檔不得硬編碼個人主目錄。

    為什麼：CLAUDE.md §六 ★ — 新代碼必須隨時可部署 Apple Silicon Mac，
    `/home/ncyu` / `/Users/ncyu` 硬編碼會破跨平台 portability。
    """
    new_files = [
        _helper_scripts / "lib" / "tls_cert.sh",
        _helper_scripts / "Caddyfile.template",
        _helper_scripts / "install_caddy.sh",
        _helper_scripts / "systemd" / "openclaw-caddy.service",
        _helper_scripts / "systemd" / "openclaw-tls-renew.service",
        _helper_scripts / "systemd" / "openclaw-tls-renew.timer",
        _helper_scripts / "systemd" / "openclaw-tls-renew-notify.service",
    ]
    pattern = re.compile(r"/home/ncyu|/Users/ncyu")
    for fp in new_files:
        assert fp.exists(), f"missing: {fp}"
        text = fp.read_text(encoding="utf-8")
        assert not pattern.search(text), f"hardcoded user path in {fp}"


def test_caddyfile_template_directives() -> None:
    """Caddyfile.template 必含 reverse_proxy + Tailscale cert path placeholder。"""
    template = (_helper_scripts / "Caddyfile.template").read_text(encoding="utf-8")
    # spec §1.2：必走 Tailscale cert
    assert "OPENCLAW_TLS_CERT_DIR" in template
    assert "OPENCLAW_TLS_CERT_HOST" in template
    # spec §3.2：bind 127.0.0.1，Caddy 反代 8000
    assert "127.0.0.1" in template
    assert "reverse_proxy" in template
    # 不應 fallback 到 Caddy 內建 dev CA（spec §1.2 reject）
    assert "tls internal" not in template
    # admin endpoint 必關（不暴露 :2019）
    assert "admin off" in template
    # X-Forwarded-Proto 必傳給 FastAPI（_has_https_proxy_hint 依此）
    assert "X-Forwarded-Proto" in template


def test_tls_cert_helper_cross_platform() -> None:
    """lib/tls_cert.sh 必有 Linux + Darwin 雙分支，且不寫死 /home/ncyu。"""
    helper = (_helper_scripts / "lib" / "tls_cert.sh").read_text(encoding="utf-8")
    assert "Linux)" in helper
    assert "Darwin)" in helper
    # macOS 用 $HOME 而非硬編碼路徑
    assert '$HOME/Library/Application Support/Tailscale/certs' in helper
    # 必提供 resolve / renew 兩個必要函數
    assert "resolve_openclaw_tls_cert_dir()" in helper
    assert "tls_cert_should_renew()" in helper


def test_install_caddy_dry_run_default() -> None:
    """install_caddy.sh --dry-run 不應寫檔；APPLY 旗標必須顯式才生效。

    跑 --help 即可驗證 argparse 邏輯，避免在 CI 真正改 /etc/。
    """
    script = _helper_scripts / "install_caddy.sh"
    text = script.read_text(encoding="utf-8")
    # APPLY 預設 0
    assert "APPLY=0" in text
    # --apply 必須顯式
    assert '--apply) APPLY=1 ;;' in text
    # 必引用 lib/tls_cert.sh 而非寫死路徑
    assert 'source "$REPO_ROOT/helper_scripts/lib/tls_cert.sh"' in text


def test_systemd_units_reference_helper_lib() -> None:
    """systemd renew service 必引用 lib/tls_cert.sh 而非寫死 tailscale cert 邏輯。

    為什麼：renewal 邏輯（14d threshold / chown / reload Caddy）只應該寫一次，
    跨平台時 launchd plist 同樣引用 lib 即可。
    """
    renew = (_helper_scripts / "systemd" / "openclaw-tls-renew.service").read_text(
        encoding="utf-8"
    )
    assert "helper_scripts/lib/tls_cert.sh" in renew
    assert "tls_cert_should_renew" in renew
    assert "tailscale cert" in renew
    assert "systemctl reload openclaw-caddy.service" in renew


def test_tls_cert_helper_syntax_valid() -> None:
    """bash -n 驗 lib/tls_cert.sh 語法（不執行）。"""
    if not shutil.which("bash"):
        pytest.skip("bash not available")
    result = subprocess.run(
        ["bash", "-n", str(_helper_scripts / "lib" / "tls_cert.sh")],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"bash -n failed: {result.stderr}"


def test_install_caddy_syntax_valid() -> None:
    """bash -n 驗 install_caddy.sh 語法（不執行 envsubst / apt）。"""
    if not shutil.which("bash"):
        pytest.skip("bash not available")
    result = subprocess.run(
        ["bash", "-n", str(_helper_scripts / "install_caddy.sh")],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"bash -n failed: {result.stderr}"
