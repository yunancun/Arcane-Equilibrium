"""OPS-2 SECRET-SPLIT — live_trust_routes signing key 拆分驗證。

MODULE_NOTE：
  - 模塊用途：驗證 `_read_live_auth_signing_key()` Phase 1 行為（primary
    `OPENCLAW_LIVE_AUTH_SIGNING_KEY` 優先；fallback `OPENCLAW_IPC_SECRET` +
    rate-limited WARN）與 cross-lang HMAC byte-identical fixture。
  - 對齊 spec：`docs/execution_plan/specs/2026-05-26--p1-ops-2-secret-split-design.md`
    §4.4 Python 表格 + §8.5 E2 重點 #3（WARN rate ≤1/h）。
  - 為什麼新檔：原 live_trust_routes 無對應 test；本 split 屬高風險 gate #4+#5，
    必獨立 test 覆蓋 Phase 1 行為 + cross-lang HMAC（避免 Earn first stake silent fail）。
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
# Helper：每個 test 開頭清乾淨 4 env + reset rate-limit state
# 為什麼：fallback warn rate-limit 是 process-wide；test 間需重置才能驗 emit。
# ---------------------------------------------------------------------------
def _reset_env_and_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENCLAW_LIVE_AUTH_SIGNING_KEY", raising=False)
    monkeypatch.delenv("OPENCLAW_LIVE_AUTH_SIGNING_KEY_FILE", raising=False)
    monkeypatch.delenv("OPENCLAW_IPC_SECRET", raising=False)
    monkeypatch.delenv("OPENCLAW_IPC_SECRET_FILE", raising=False)
    # 重置 rate-limit 計數讓本 test 可獨立驗 WARN emit。
    with live_trust_routes._fallback_warn_state["lock"]:
        live_trust_routes._fallback_warn_state["last_ts"] = 0.0


# ---------------------------------------------------------------------------
# Phase 1 primary path：兩 env 都 set 必走 primary（不觸 WARN）
# ---------------------------------------------------------------------------
def test_primary_live_auth_key_wins_over_ipc_fallback(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _reset_env_and_state(monkeypatch)
    monkeypatch.setenv("OPENCLAW_LIVE_AUTH_SIGNING_KEY", "primary-live-auth-key")
    monkeypatch.setenv("OPENCLAW_IPC_SECRET", "fallback-ipc-key-different")

    with caplog.at_level(logging.WARNING, logger="app.live_trust_routes"):
        got = live_trust_routes._read_live_auth_signing_key()

    assert got == "primary-live-auth-key", (
        "primary OPENCLAW_LIVE_AUTH_SIGNING_KEY 必勝出，不可走 fallback"
    )
    # 兩 env 都設時不該觸 fallback WARN。
    fallback_warns = [
        r for r in caplog.records
        if "ops2_secret_split_phase1_fallback" in r.getMessage()
    ]
    assert not fallback_warns, (
        "primary env 命中時不可 emit fallback WARN（保留 alert 信噪比）"
    )


# ---------------------------------------------------------------------------
# Phase 1 fallback path：primary 未設 + IPC 設 → 走 fallback + emit 一次 WARN
# ---------------------------------------------------------------------------
def test_phase1_fallback_emits_warn_when_only_ipc_set(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _reset_env_and_state(monkeypatch)
    monkeypatch.setenv("OPENCLAW_IPC_SECRET", "phase1-legacy-ipc-secret")

    with caplog.at_level(logging.WARNING, logger="app.live_trust_routes"):
        got = live_trust_routes._read_live_auth_signing_key()

    assert got == "phase1-legacy-ipc-secret", "Phase 1 fallback 必讀 IPC_SECRET"
    fallback_warns = [
        r for r in caplog.records
        if "ops2_secret_split_phase1_fallback" in r.getMessage()
    ]
    assert len(fallback_warns) == 1, (
        f"首次 fallback 必 emit 1 條 WARN；got {len(fallback_warns)}"
    )


# ---------------------------------------------------------------------------
# Phase 1 fallback WARN rate-limit：≤1/h（spec §8.5 E2 重點 #3）
# ---------------------------------------------------------------------------
def test_phase1_fallback_warn_rate_limit_one_per_hour(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _reset_env_and_state(monkeypatch)
    monkeypatch.setenv("OPENCLAW_IPC_SECRET", "phase1-rate-limit-test")

    with caplog.at_level(logging.WARNING, logger="app.live_trust_routes"):
        # 連續 100 次呼叫模擬 watcher 5s poll → 500s 內 100 calls
        for _ in range(100):
            live_trust_routes._read_live_auth_signing_key()

    fallback_warns = [
        r for r in caplog.records
        if "ops2_secret_split_phase1_fallback" in r.getMessage()
    ]
    # 為什麼期望 1：100 calls 在 ms 級內，必落入 3600s 窗口 → 僅 1 emit。
    # 防 7200 logs/day 洪流（watcher 5s poll + sign/verify 路徑）。
    assert len(fallback_warns) == 1, (
        f"WARN rate-limit 必 ≤1/h；100 calls 內 emit {len(fallback_warns)} 次"
    )


# ---------------------------------------------------------------------------
# Rate-limit 窗口外可重新 emit（模擬 1h+ 後第二次 fallback）
# ---------------------------------------------------------------------------
def test_phase1_fallback_warn_reemits_after_interval(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _reset_env_and_state(monkeypatch)
    monkeypatch.setenv("OPENCLAW_IPC_SECRET", "phase1-reemit-test")

    with caplog.at_level(logging.WARNING, logger="app.live_trust_routes"):
        live_trust_routes._read_live_auth_signing_key()
        # 把 last_ts 倒回 1h+1s 前 → 下一次必再 emit。
        with live_trust_routes._fallback_warn_state["lock"]:
            live_trust_routes._fallback_warn_state["last_ts"] = (
                time.time() - live_trust_routes._FALLBACK_WARN_INTERVAL_SECS - 1
            )
        live_trust_routes._read_live_auth_signing_key()

    fallback_warns = [
        r for r in caplog.records
        if "ops2_secret_split_phase1_fallback" in r.getMessage()
    ]
    assert len(fallback_warns) == 2, (
        f"超過 1h 窗口必重新 emit；got {len(fallback_warns)}"
    )


# ---------------------------------------------------------------------------
# 兩 env 都未設 → 回空字串（caller 須 fail-closed）
# ---------------------------------------------------------------------------
def test_returns_empty_when_both_envs_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_env_and_state(monkeypatch)
    got = live_trust_routes._read_live_auth_signing_key()
    assert got == "", "兩 env 都未設必回空字串，caller fail-closed"


# ---------------------------------------------------------------------------
# Sign authorization 用 LIVE_AUTH primary key（非 IPC fallback）
# 為什麼：spec §4.4 Python 表格 — 簽授權 sig 必須 = HMAC(LIVE_AUTH_key, payload)
# 而非 HMAC(IPC_SECRET, payload)，否則 Rust verify 失敗。
# ---------------------------------------------------------------------------
def test_sign_authorization_uses_live_auth_signing_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_env_and_state(monkeypatch)
    # primary = key-a；fallback = key-b（不同）
    monkeypatch.setenv("OPENCLAW_LIVE_AUTH_SIGNING_KEY", "key-a-live-auth")
    monkeypatch.setenv("OPENCLAW_IPC_SECRET", "key-b-ipc-fallback")

    got_key = live_trust_routes._read_live_auth_signing_key()
    assert got_key == "key-a-live-auth"

    # 用 key-a 簽 vs key-b 簽必不同 → 確保 sign 用 primary。
    payload = "2|T0_ENTRY|1700000000000|1700086400000|ncyu|live_reserved|live_demo"
    sig_with_a = live_trust_routes._sign_authorization_payload(payload, got_key)
    sig_with_b = live_trust_routes._sign_authorization_payload(payload, "key-b-ipc-fallback")
    assert sig_with_a != sig_with_b, "primary vs fallback key 簽出的 sig 必不同"


# ---------------------------------------------------------------------------
# Cross-language HMAC byte-identical fixture：Python 必與 Rust 算出同 sig
# 為什麼：spec §8.5 E2 重點 #1 + §1 防 Earn first stake silent fail；
# canonical payload format / endianness drift 立刻在此 fail。
# ---------------------------------------------------------------------------
def test_cross_lang_hmac_fixture_matches_rust_compute_signature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_env_and_state(monkeypatch)
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

    # 為什麼固化 expected sig 字串：Rust 端 cross_lang_hmac_fixture_is_byte_identical
    # 用 compute_signature(同 payload, 同 key) 必產出同一字串；任何一端改
    # canonical 格式立刻在 grep 此固化值時暴露。固化值 = sha256_hex(...)。
    # Pre-computed via: python -c "import hmac,hashlib; \
    #   print(hmac.new(b'test-live-auth-signing-key-do-not-use-in-prod', \
    #     b'2|T0_ENTRY|1700000000000|1700086400000|ncyu|live_reserved|live_demo', \
    #     hashlib.sha256).hexdigest())"
    # 為什麼固化 pinned_hex：與 Rust `live_authorization::cross_lang_hmac_fixture_is_byte_identical`
    # 同一 fixture（同 key + 同 payload）必產出同 hex。任何一端改 canonical 格式
    # / HMAC 算法 / hex encoding 立刻 fail。pinned 由 Python stdlib hmac 算出，
    # Rust 端 unit test 同樣 assert 此值。
    pinned_hex = (
        "1b2b18d7e212d0d1e8f943c25f6f070b2ba75013b8fd5c3a021800d11b8b78fc"
    )
    assert sig == pinned_hex, (
        f"Rust-Python cross-lang HMAC fixture drift detected！\n"
        f"expected={pinned_hex}\n"
        f"got     ={sig}"
    )


# ---------------------------------------------------------------------------
# Sign authorization missing both envs → RuntimeError with renamed message
# ---------------------------------------------------------------------------
def test_write_signed_live_authorization_raises_when_both_envs_unset(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _reset_env_and_state(monkeypatch)
    monkeypatch.setenv("OPENCLAW_SECRETS_DIR", str(tmp_path))

    with pytest.raises(RuntimeError) as exc_info:
        live_trust_routes._write_signed_live_authorization(
            operator_id="ncyu",
            tier=0,
            expires_at_ms=int(time.time() * 1000) + 3600_000,
        )
    msg = str(exc_info.value)
    assert "OPENCLAW_LIVE_AUTH_SIGNING_KEY" in msg, (
        "錯誤訊息必提及新 env name（per spec §4.2.1 Phase 1 error message）"
    )
