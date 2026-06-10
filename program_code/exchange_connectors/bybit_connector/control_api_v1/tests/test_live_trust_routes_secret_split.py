"""OPS-2 SECRET-SPLIT — live_trust_routes signing key 拆分驗證（Phase 2 cutover）。

MODULE_NOTE：
  - 模塊用途：驗證 `_read_live_auth_signing_key()` Phase 2 cutover（2026-06-10）
    行為——純讀 `OPENCLAW_LIVE_AUTH_SIGNING_KEY`，legacy `OPENCLAW_IPC_SECRET`
    fallback 已移除（missing 必 fail loud：sign 路徑 raise / verify 路徑回
    reason "live_auth_signing_key_missing"）——與 cross-lang HMAC byte-identical
    fixture。
  - 對齊 spec：`docs/execution_plan/specs/2026-05-26--p1-ops-2-secret-split-design.md`
    §3.2（Phase 2 移除 fallback）+ runbook `docs/runbooks/credential_rotation.md`
    §13.3（PR dispatch 範圍）。
  - 為什麼保留本檔：cutover 後 fallback 行為測試刪除，改為「legacy env 單獨
    存在必 fail-closed」負向測試；cross-lang HMAC fixture 為永久 invariant
    （runbook §10.5 / §13.6）。
  - 硬邊界：簽名 key 與 IPC transport key 分離是 5-gate #5 的完整性前提，
    測試不可引入任何「IPC env 可代替簽名 key」的斷言。
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import sys
import time
from pathlib import Path

import pytest

_test_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(_test_dir)
if _control_api_dir not in sys.path:
    sys.path.insert(0, _control_api_dir)

from app import live_trust_routes  # noqa: E402


# ---------------------------------------------------------------------------
# Helper：每個 test 開頭清乾淨 4 env
# 為什麼仍清 IPC env：Phase 2 後簽名路徑不讀它，但測試須從已知環境出發，
# 才能精確驗「IPC 單獨存在不提供簽名 key」。
# ---------------------------------------------------------------------------
def _reset_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENCLAW_LIVE_AUTH_SIGNING_KEY", raising=False)
    monkeypatch.delenv("OPENCLAW_LIVE_AUTH_SIGNING_KEY_FILE", raising=False)
    monkeypatch.delenv("OPENCLAW_IPC_SECRET", raising=False)
    monkeypatch.delenv("OPENCLAW_IPC_SECRET_FILE", raising=False)


# ---------------------------------------------------------------------------
# Phase 2 primary path：LIVE_AUTH 設置 → 讀 primary；IPC 值不得污染
# ---------------------------------------------------------------------------
def test_primary_live_auth_key_read_ignores_ipc_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_env(monkeypatch)
    monkeypatch.setenv("OPENCLAW_LIVE_AUTH_SIGNING_KEY", "primary-live-auth-key")
    monkeypatch.setenv("OPENCLAW_IPC_SECRET", "ipc-transport-only-key")

    got = live_trust_routes._read_live_auth_signing_key()

    assert got == "primary-live-auth-key", (
        "OPENCLAW_LIVE_AUTH_SIGNING_KEY 必為唯一簽名 key 來源"
    )


# ---------------------------------------------------------------------------
# Phase 2 cutover 負向：只設 legacy IPC env → 必回空字串（fallback 已移除）
# ---------------------------------------------------------------------------
def test_ipc_secret_alone_no_longer_provides_signing_key(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _reset_env(monkeypatch)
    monkeypatch.setenv("OPENCLAW_IPC_SECRET", "legacy-ipc-key-must-not-rescue")

    with caplog.at_level(logging.WARNING, logger="app.live_trust_routes"):
        got = live_trust_routes._read_live_auth_signing_key()

    assert got == "", (
        "Phase 2 cutover 後 OPENCLAW_IPC_SECRET 單獨存在不可提供簽名 key"
        "（fail-closed）"
    )
    # cutover 後 fallback WARN 發射點已刪——任何此字串出現 = 殘留代碼 P0
    # （runbook §13.6）。
    fallback_warns = [
        r for r in caplog.records
        if "ops2_secret_split_phase1_fallback" in r.getMessage()
    ]
    assert not fallback_warns, "Phase 1 fallback WARN 發射點必須已移除"


# ---------------------------------------------------------------------------
# 兩 env 都未設 → 回空字串（caller 須 fail-closed）
# ---------------------------------------------------------------------------
def test_returns_empty_when_both_envs_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_env(monkeypatch)
    got = live_trust_routes._read_live_auth_signing_key()
    assert got == "", "key 未設必回空字串，caller fail-closed"


# ---------------------------------------------------------------------------
# Sign authorization 用 LIVE_AUTH key（IPC 值不同時 sig 必不同）
# 為什麼：簽授權 sig 必須 = HMAC(LIVE_AUTH_key, payload)，否則 Rust verify 失敗。
# ---------------------------------------------------------------------------
def test_sign_authorization_uses_live_auth_signing_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_env(monkeypatch)
    monkeypatch.setenv("OPENCLAW_LIVE_AUTH_SIGNING_KEY", "key-a-live-auth")
    monkeypatch.setenv("OPENCLAW_IPC_SECRET", "key-b-ipc-transport")

    got_key = live_trust_routes._read_live_auth_signing_key()
    assert got_key == "key-a-live-auth"

    # 用 key-a 簽 vs key-b 簽必不同 → 確保 sign 用 LIVE_AUTH key。
    payload = "2|T0_ENTRY|1700000000000|1700086400000|ncyu|live_reserved|live_demo"
    sig_with_a = live_trust_routes._sign_authorization_payload(payload, got_key)
    sig_with_b = live_trust_routes._sign_authorization_payload(payload, "key-b-ipc-transport")
    assert sig_with_a != sig_with_b, "LIVE_AUTH vs IPC key 簽出的 sig 必不同"


# ---------------------------------------------------------------------------
# Cross-language HMAC byte-identical fixture：Python 必與 Rust 算出同 sig
# 為什麼：runbook §10.5 / §13.6 永久 invariant — 防 Earn first stake silent
# fail；canonical payload format / endianness drift 立刻在此 fail。
# ---------------------------------------------------------------------------
def test_cross_lang_hmac_fixture_matches_rust_compute_signature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_env(monkeypatch)
    test_key = "test-live-auth-signing-key-do-not-use-in-prod"

    # 與 Rust live_authorization::cross_lang_hmac_fixture_is_byte_identical
    # 同一 canonical payload。
    payload = "2|T0_ENTRY|1700000000000|1700086400000|ncyu|live_reserved|live_demo"
    sig = live_trust_routes._sign_authorization_payload(payload, test_key)
    # HMAC-SHA256 hex = 64 chars
    assert len(sig) == 64, f"HMAC-SHA256 hex 必 64 chars；got {len(sig)}"

    # 獨立 Python 標準庫重算驗 _sign_authorization_payload 無偏移。
    expected = hmac.new(
        test_key.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    assert sig == expected, (
        "Python live_trust_routes._sign_authorization_payload 必與 stdlib hmac 對齊"
    )

    # 為什麼固化 pinned_hex：與 Rust `live_authorization::cross_lang_hmac_fixture_is_byte_identical`
    # 同一 fixture（同 key + 同 payload）必產出同 hex。任何一端改 canonical 格式
    # / HMAC 算法 / hex encoding 立刻 fail。pinned 由 Python stdlib hmac 算出，
    # Rust 端 unit test 同樣 assert 此值。
    # Pre-computed via: python -c "import hmac,hashlib; \
    #   print(hmac.new(b'test-live-auth-signing-key-do-not-use-in-prod', \
    #     b'2|T0_ENTRY|1700000000000|1700086400000|ncyu|live_reserved|live_demo', \
    #     hashlib.sha256).hexdigest())"
    pinned_hex = (
        "1b2b18d7e212d0d1e8f943c25f6f070b2ba75013b8fd5c3a021800d11b8b78fc"
    )
    assert sig == pinned_hex, (
        f"Rust-Python cross-lang HMAC fixture drift detected！\n"
        f"expected={pinned_hex}\n"
        f"got     ={sig}"
    )


# ---------------------------------------------------------------------------
# Fail loud #1：兩 env 都未設 → sign 路徑必 raise RuntimeError（提及新 env 名）
# ---------------------------------------------------------------------------
def test_write_signed_live_authorization_raises_when_both_envs_unset(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _reset_env(monkeypatch)
    monkeypatch.setenv("OPENCLAW_SECRETS_DIR", str(tmp_path))

    with pytest.raises(RuntimeError) as exc_info:
        live_trust_routes._write_signed_live_authorization(
            operator_id="ncyu",
            tier=0,
            expires_at_ms=int(time.time() * 1000) + 3600_000,
        )
    msg = str(exc_info.value)
    assert "OPENCLAW_LIVE_AUTH_SIGNING_KEY" in msg, (
        "錯誤訊息必提及新 env name（operator 可直接定位 root cause）"
    )


# ---------------------------------------------------------------------------
# Fail loud #2（cutover 定義性測試）：legacy IPC env 設置也救不了 sign 路徑
# 為什麼：Phase 1 此情境會 fallback 成功 + WARN；Phase 2 必 raise——
# 證明 fallback 在 sign 端到端層級已移除，且不寫任何授權檔。
# ---------------------------------------------------------------------------
def test_write_signed_live_authorization_raises_even_when_ipc_secret_set(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _reset_env(monkeypatch)
    monkeypatch.setenv("OPENCLAW_SECRETS_DIR", str(tmp_path))
    monkeypatch.setenv("OPENCLAW_IPC_SECRET", "legacy-ipc-key-must-not-rescue")

    with pytest.raises(RuntimeError) as exc_info:
        live_trust_routes._write_signed_live_authorization(
            operator_id="ncyu",
            tier=0,
            expires_at_ms=int(time.time() * 1000) + 3600_000,
        )
    msg = str(exc_info.value)
    assert "OPENCLAW_LIVE_AUTH_SIGNING_KEY" in msg
    # fail-closed 完整性：raise 前不可寫出任何 authorization.json。
    assert not (tmp_path / "live" / "authorization.json").exists(), (
        "missing key 時不可留下部分寫入的授權檔"
    )


# ---------------------------------------------------------------------------
# Fail loud #3：verify 路徑 reason 改 "live_auth_signing_key_missing"
# 為什麼：runbook §13.3 live_trust_routes reason rename——對齊 Rust
# auth_error_kind；舊 "ipc_secret_missing" 字串不得再出現（runbook §13.6
# trust-status invariant grep = 0）。
# ---------------------------------------------------------------------------
def test_verify_status_reason_is_live_auth_signing_key_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _reset_env(monkeypatch)
    monkeypatch.setenv("OPENCLAW_SECRETS_DIR", str(tmp_path))

    # 先用有效 key 簽出 authorization.json（通過 version / mode 前置檢查）。
    monkeypatch.setenv("OPENCLAW_LIVE_AUTH_SIGNING_KEY", "key-present-at-sign-time")
    live_trust_routes._write_signed_live_authorization(
        operator_id="ncyu",
        tier=0,
        expires_at_ms=int(time.time() * 1000) + 3600_000,
    )

    # 再移除簽名 key、僅留 legacy IPC env → verify 必 unverifiable + 新 reason。
    monkeypatch.delenv("OPENCLAW_LIVE_AUTH_SIGNING_KEY", raising=False)
    monkeypatch.setenv("OPENCLAW_IPC_SECRET", "legacy-ipc-key-must-not-rescue")

    status = live_trust_routes._read_signed_live_authorization_status()

    assert status["status"] == "unverifiable"
    assert status["reason"] == "live_auth_signing_key_missing", (
        "Phase 2 cutover 後 reason 必為 live_auth_signing_key_missing"
        f"（對齊 Rust auth_error_kind）；got {status['reason']!r}"
    )
    assert status["valid_for_engine"] is False, "key missing 必 fail-closed"


# ---------------------------------------------------------------------------
# 殘留代碼防護：fallback rate-limit 機制必須整個移除
# 為什麼：runbook §13.6「任何 grep > 0 = 有殘留代碼 P0」的模塊級對應——
# rate-limit state 與 WARN 發射點是 Phase 1 機制的兩個錨點，缺一不可殘留。
# ---------------------------------------------------------------------------
def test_phase1_fallback_machinery_is_removed() -> None:
    assert not hasattr(live_trust_routes, "_fallback_warn_state"), (
        "_fallback_warn_state（Phase 1 rate-limit state）必須已刪除"
    )
    assert not hasattr(live_trust_routes, "_FALLBACK_WARN_INTERVAL_SECS"), (
        "_FALLBACK_WARN_INTERVAL_SECS（Phase 1 rate-limit 窗口）必須已刪除"
    )
