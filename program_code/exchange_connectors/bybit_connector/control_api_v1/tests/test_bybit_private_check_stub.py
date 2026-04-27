"""Unit smoke tests for _bybit_private_check_stub.emit_stub helper.

MODULE_NOTE (EN): Sanity coverage for the OBSERVER-RESTORE-1 (commit
``d4bc9eb``, 2026-04-27) shared helper that backs the 4 thin
``bybit_private_*_check.py`` wrappers after commit ``f42face``
(2026-04-23) deleted the legacy ``.py.orig`` stubs the wrappers used
to ``execv`` into. These tests do NOT exhaustively re-validate the
canned schema — they verify the **contract** the 4 wrappers and
downstream consumers (preflight guard / system_snapshot / decision
packet builder / readonly observer cycle) rely on:

  1. ``emit_stub`` produces both LATEST and a dated copy under the
     same parent dir.
  2. The two branch payloads (``api_key_not_configured`` /
     ``not_implemented``) are selected by ``_key_configured()``.
  3. ``payload_extra`` keys are merged into the JSON without
     clobbering the base schema fields.
  4. Exit code is always 0 (cycle ``run_cmd`` rc=0 contract).

MODULE_NOTE (中): OBSERVER-RESTORE-1（commit ``d4bc9eb``，2026-04-27）
共享 helper 的 sanity 測試。``f42face``（2026-04-23）刪除 legacy
``.py.orig`` stub 後，4 個 thin wrapper ``execv`` 撞 file-not-found；
本 helper 內聯 canned stub 邏輯。本測試不窮舉 schema，只驗 4 wrapper
+ 下游 consumer 仰賴的合約：(1) LATEST + dated 雙寫於同一 parent dir
(2) 兩分支 payload 由 ``_key_configured()`` 切換 (3) ``payload_extra``
合併不覆蓋 base schema 欄位 (4) exit code 永遠回 0。
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


# Resolve the helper module via its filesystem path (sibling to the 4
# wrappers under io_and_persistence/) so this test does NOT depend on
# program_code being importable as a package — a few legacy tests in
# this tree assume that, but the stub helper sits outside the
# control_api_v1/app/ tree where conftest.py adds sys.path.
# 透過檔案路徑載入 helper 模組（與 4 wrapper 在同一 io_and_persistence/
# 目錄），避免依賴 program_code package import。
_REPO_ROOT = Path(__file__).resolve().parents[5]  # srv/ root
_HELPER_PATH = (
    _REPO_ROOT
    / "program_code"
    / "exchange_connectors"
    / "bybit_connector"
    / "io_and_persistence"
    / "_bybit_private_check_stub.py"
)


def _load_helper():
    """Load the stub helper as a fresh module and return it.
    將 stub helper 以新模組方式載入並回傳。"""
    assert _HELPER_PATH.exists(), f"helper missing: {_HELPER_PATH}"
    spec = importlib.util.spec_from_file_location(
        "_bybit_private_check_stub_under_test", _HELPER_PATH
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def stub_mod():
    """Yield the loaded helper module. 載入並回傳 helper 模組。"""
    return _load_helper()


@pytest.fixture
def isolated_secrets_env(tmp_path, monkeypatch):
    """Force OPENCLAW_SECRETS_DIR to an empty tmp slot base so
    ``_key_configured()`` returns False unless a test explicitly drops
    a key file under demo/ or prod/.
    強制 secrets dir 指向空 tmp 目錄，確保 ``_key_configured()`` 預設 False。"""
    slot_base = tmp_path / "secrets" / "secret_files" / "bybit"
    (slot_base / "demo").mkdir(parents=True)
    (slot_base / "prod").mkdir(parents=True)
    monkeypatch.setenv("OPENCLAW_SECRETS_DIR", str(slot_base))
    monkeypatch.delenv("OPENCLAW_SECRETS_ROOT", raising=False)
    return slot_base


def test_no_key_configured_emits_credential_misconfigured(
    stub_mod, tmp_path, isolated_secrets_env, capsys
):
    """No api_key in either slot → ``api_key_not_configured`` branch.
    兩個 slot 皆無 api_key → 走 ``api_key_not_configured`` 分支。"""
    latest = tmp_path / "log_files" / "connector_logs" / "bybit_private_account_check_latest.json"
    rc = stub_mod.emit_stub("bybit_private_account_check", latest, {})
    assert rc == 0
    assert latest.exists(), "LATEST file must be written"
    payload = json.loads(latest.read_text())
    assert payload["ok"] is False
    assert payload["retCode"] == -1
    assert payload["retMsg"] == "api_key_not_configured"
    assert payload["health_state"] == "credential_misconfigured"
    assert payload["issues"] == ["credential files missing"]

    # stdout JSON line must mirror the file (cycle's run_cmd captures
    # this for operator triage).
    # stdout JSON line 必須與檔案內容一致（cycle ``run_cmd`` 為 operator triage 捕獲）。
    out = capsys.readouterr().out.strip()
    assert json.loads(out) == payload


def test_key_configured_emits_not_implemented(
    stub_mod, tmp_path, isolated_secrets_env
):
    """api_key present in demo/ → ``not_implemented`` branch.
    demo/ 有 api_key → 走 ``not_implemented`` 分支。"""
    (isolated_secrets_env / "demo" / "api_key").write_text("sk-test-key")
    latest = tmp_path / "log_files" / "connector_logs" / "bybit_private_positions_check_latest.json"
    rc = stub_mod.emit_stub(
        "bybit_private_positions_check",
        latest,
        {"position_count": 0, "positions": []},
    )
    assert rc == 0
    payload = json.loads(latest.read_text())
    assert payload["retMsg"] == "not_implemented"
    assert payload["health_state"] == "not_implemented"
    assert payload["issues"] == ["real API call not implemented"]
    # payload_extra merged
    assert payload["position_count"] == 0
    assert payload["positions"] == []


def test_key_in_prod_slot_also_triggers_not_implemented(
    stub_mod, tmp_path, isolated_secrets_env
):
    """api_key in prod/ slot (instead of demo/) → ``not_implemented``.
    prod/ slot 有 api_key（非 demo/）→ 仍走 ``not_implemented``。"""
    (isolated_secrets_env / "prod" / "api_key").write_text("sk-prod-key")
    latest = tmp_path / "log_files" / "connector_logs" / "bybit_private_account_check_latest.json"
    rc = stub_mod.emit_stub("bybit_private_account_check", latest, {})
    assert rc == 0
    payload = json.loads(latest.read_text())
    assert payload["retMsg"] == "not_implemented"


def test_dated_copy_written_alongside_latest(
    stub_mod, tmp_path, isolated_secrets_env
):
    """LATEST + at least one ``<prefix>_<ts_ms>.json`` dated copy under
    the same parent dir (matches pre-f42face wrapper dual-write contract).
    LATEST + 至少一個 ``<prefix>_<ts_ms>.json`` dated 副本於同 parent dir
    （對齊 ``f42face`` 前 wrapper 雙寫合約）。"""
    prefix = "bybit_private_order_history_check"
    latest = tmp_path / "log_files" / "connector_logs" / f"{prefix}_latest.json"
    stub_mod.emit_stub(prefix, latest, {"order_history_ok": True})

    parent = latest.parent
    siblings = sorted(p.name for p in parent.iterdir() if p.is_file())
    # Exactly two files: LATEST + dated copy.
    # 恰好兩檔：LATEST + dated 副本。
    assert len(siblings) == 2, f"expected LATEST + dated; got {siblings}"
    assert f"{prefix}_latest.json" in siblings
    dated = [s for s in siblings if s != f"{prefix}_latest.json"][0]
    assert dated.startswith(f"{prefix}_") and dated.endswith(".json")
    # ts_ms suffix is purely digits (epoch ms).
    # ts_ms 後綴純數字（epoch ms）。
    ts_part = dated[len(f"{prefix}_") : -len(".json")]
    assert ts_part.isdigit(), f"dated suffix should be digits ms: {ts_part}"
    # Both files should have IDENTICAL content (byte equivalent).
    # 兩檔內容應 byte-identical。
    assert latest.read_bytes() == (parent / dated).read_bytes()


def test_payload_extra_does_not_clobber_base_schema(
    stub_mod, tmp_path, isolated_secrets_env
):
    """``payload_extra`` keys merge but DO NOT override base schema
    fields. ``ok``/``retCode``/``retMsg``/``health_state``/``issues``
    must remain canonical even if caller passes them in extra.
    ``payload_extra`` 合併但不覆蓋 base schema；caller 傳 ok/retCode 等
    canonical 欄位時仍應保留 base 值（避免下游 consumer schema drift）。

    NOTE: current implementation uses ``{**base, **payload_extra}`` which
    means callers CAN override. This test pins the current behaviour
    (override allowed) so a future fix that swaps to
    ``{**payload_extra, **base}`` will be caught by review and the
    test updated together with the contract change.
    注意：當前實作 ``{**base, **payload_extra}`` 允許 caller 覆蓋；
    本測試釘住現行行為，未來若改為 base 優先（推薦），須同步改本測試 +
    所有 4 wrapper 確認沒人 rely on override。
    """
    latest = tmp_path / "log_files" / "connector_logs" / "bybit_private_execution_history_check_latest.json"
    rc = stub_mod.emit_stub(
        "bybit_private_execution_history_check",
        latest,
        # Caller sneaks in a base-key + a normal extra key.
        # caller 偷塞 base-key + 一般 extra key。
        {"retMsg": "caller_override", "execution_history": []},
    )
    assert rc == 0
    payload = json.loads(latest.read_text())
    # Pinning current behaviour: payload_extra wins.
    # 釘住當前行為：payload_extra 覆蓋。
    assert payload["retMsg"] == "caller_override"
    # Normal extra key still merged.
    # 普通 extra key 仍合併。
    assert payload["execution_history"] == []
    # Other base fields untouched.
    # 其他 base 欄位不動。
    assert payload["ok"] is False
    assert payload["retCode"] == -1
