"""
Unit tests for `sync_ipc_call` HMAC ts unit (G2-FUP-IPC-LEGACY-MS-FIX, 2026-04-26).

Background / 背景
==================
`app.ipc_client.sync_ipc_call` previously constructed the HMAC handshake
timestamp as `int(time.time() * 1000)` (milliseconds). The Rust verifier
(`rust/openclaw_engine/src/ipc_server/mod.rs:621-628`) compares the timestamp
using `as_secs() as i64` with a 30-second tolerance window:

    if (now_secs - ts).abs() > 30 { reject "auth token expired" }

A millisecond-valued `ts` differs from `now_secs` by ~1.7e12 (orders of
magnitude beyond 30s), so every legacy `sync_ipc_call` was 100% rejected
by Rust HMAC auth. The two production callers
(`trigger_live_auth_recheck`, `set_system_mode`) are fire-and-forget —
they swallow the resulting `PermissionError`, masking the failure.

These tests pin down the corrected contract:

  (a) Normal path  — `ts` matches the seconds returned by `time.time()`.
  (b) Boundary OK  — Skewing the simulated clock by +25s within the same
                     handshake still passes (well inside the 30s window).
  (c) Boundary bad — A +60s skew between the test's "now" and the value
                     embedded in the handshake exceeds the Rust tolerance,
                     so a real Rust verifier would reject. We don't need a
                     live engine to assert this — we model the verifier
                     locally and confirm `sync_ipc_call`'s ts is close
                     enough to `time.time()` that any 30s+ drift comes
                     from the simulated clock, not from a unit error.

The tests are pure-Python: they isolate the system clock via mocks and
intercept the `socket.socket` constructor with a fake that records all
sent bytes — no real Unix domain socket, no Rust engine required.

`sync_ipc_call` HMAC 時間戳單位修復（G2-FUP-IPC-LEGACY-MS-FIX，2026-04-26）單元測試。

先前 `app.ipc_client.sync_ipc_call` 使用 `int(time.time() * 1000)`（毫秒）構造
HMAC 時間戳，但 Rust verifier
（`rust/openclaw_engine/src/ipc_server/mod.rs:621-628`）以秒為單位比對
30s 容差，導致 100% 認證失敗（fire-and-forget caller 吞錯誤致使 bug 表面靜默）。
本測試固定修復後的契約：

  (a) 正常路徑：構造的 `ts` 與 `time.time()` 秒值一致。
  (b) 容差內 +25s 偏移仍通過。
  (c) 容差外 +60s 偏移失敗（模擬 Rust verifier 拒絕 stale ts）。

測試純 Python：mock 系統時鐘 + 攔截 `socket.socket`，無需真實 IPC 連線或
Rust engine。
"""

from __future__ import annotations

import hashlib
import hmac as _hmac_lib
import json
import time as _real_time
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Reference Rust verifier mirror / Rust verifier 鏡像
#
# Faithful Python port of the verification logic in
# `rust/openclaw_engine/src/ipc_server/mod.rs:621-628`. Used by the boundary
# tests to assert what a real Rust engine would do given a captured handshake.
# 忠實移植 Rust verifier 邏輯，用於邊界測試模擬 Rust 引擎接收 handshake 後的判定。
# ─────────────────────────────────────────────────────────────────────────────

RUST_TS_TOLERANCE_SECS = 30  # rust/openclaw_engine/src/ipc_server/mod.rs:628


def _rust_verifier_accepts(secret: str, ts: int, token: str, now_secs: int) -> bool:
    """
    Mirror Rust HMAC verifier behavior.
    模擬 Rust HMAC 驗證器行為。

    Returns True iff:
      - |now_secs - ts| <= 30   (timestamp skew check)
      - HMAC-SHA256(secret, str(ts)) == token   (constant-time compare)
    """
    if abs(now_secs - ts) > RUST_TS_TOLERANCE_SECS:
        return False
    expected = _hmac_lib.new(
        secret.encode("utf-8"), str(ts).encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return _hmac_lib.compare_digest(expected, token)


# ─────────────────────────────────────────────────────────────────────────────
# Fake socket — captures sent bytes, replies with canned JSON-RPC frames.
# 假 socket — 捕獲發送字節，回覆預設的 JSON-RPC 響應。
# ─────────────────────────────────────────────────────────────────────────────


class _FakeSocket:
    """
    Stand-in for `socket.socket(AF_UNIX, SOCK_STREAM)` — used as a context
    manager. Records `sendall()` writes and feeds canned bytes back through
    `recv(1)` byte-by-byte (matching `sync_ipc_call._recv_line` semantics).

    `socket.socket(AF_UNIX, SOCK_STREAM)` 的替身 — 作為 context manager 使用。
    記錄 `sendall()` 寫入內容，並透過 `recv(1)` 逐位元組回覆預設字節
    （配合 `sync_ipc_call._recv_line` 的逐位元組讀取）。
    """

    def __init__(self, reply_lines: list[bytes]) -> None:
        # Each entry is a complete line WITHOUT trailing newline.
        # Flatten into a byte-by-byte stream for `recv(1)` consumption.
        # 每筆是一條不含末尾換行的完整訊息；攤平為逐位元組串流供 recv(1) 使用。
        self._reply_bytes: list[bytes] = []
        for line in reply_lines:
            self._reply_bytes.extend([bytes([b]) for b in line])
            self._reply_bytes.append(b"\n")
        self._cursor = 0
        self.sent_payloads: list[bytes] = []
        self.connected_to: str | None = None
        self.timeout: float | None = None

    # Context manager hooks / Context manager 鉤子
    def __enter__(self) -> "_FakeSocket":
        return self

    def __exit__(self, *exc: Any) -> None:
        return None

    # API used by sync_ipc_call / sync_ipc_call 用到的介面
    def settimeout(self, t: float) -> None:
        self.timeout = t

    def connect(self, path: str) -> None:
        self.connected_to = path

    def sendall(self, data: bytes) -> None:
        self.sent_payloads.append(data)

    def recv(self, n: int) -> bytes:
        # `sync_ipc_call._recv_line` always passes n=1.
        # `sync_ipc_call._recv_line` 永遠傳 n=1。
        if self._cursor >= len(self._reply_bytes):
            return b""  # connection closed
        ch = self._reply_bytes[self._cursor]
        self._cursor += 1
        return ch


def _extract_auth_payload(fake_sock: _FakeSocket) -> dict:
    """
    Extract the `__auth` request from the FakeSocket's first sendall payload.
    從 FakeSocket 的第一筆 sendall 中提取 `__auth` 請求。
    """
    assert fake_sock.sent_payloads, "no payload sent"
    raw = fake_sock.sent_payloads[0].decode("utf-8").rstrip("\n")
    msg = json.loads(raw)
    assert msg["method"] == "__auth", f"first message is not __auth: {msg}"
    return msg


# ─────────────────────────────────────────────────────────────────────────────
# Tests / 測試
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def _ipc_secret(monkeypatch: pytest.MonkeyPatch) -> str:
    """Provide a deterministic IPC secret for every test in this module."""
    secret = "test-secret-g2-fup-ipc-legacy-ms-fix"
    monkeypatch.setenv("OPENCLAW_IPC_SECRET", secret)
    return secret


def _build_canned_replies() -> list[bytes]:
    """
    Build canned replies for a successful auth + dummy method call.
    建構成功 auth + 假方法呼叫的預設回覆。

    `sync_ipc_call` reads two lines: auth response, then method response.
    `sync_ipc_call` 讀兩條：認證響應 + 方法響應。
    """
    auth_ok = json.dumps(
        {"jsonrpc": "2.0", "result": {"authenticated": True}, "id": 0}
    ).encode("utf-8")
    method_ok = json.dumps(
        {"jsonrpc": "2.0", "result": {"ok": True}, "id": 1}
    ).encode("utf-8")
    return [auth_ok, method_ok]


def test_sync_ipc_call_uses_seconds_for_hmac_ts(
    _ipc_secret: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    (a) Normal path / 正常路徑

    `sync_ipc_call` MUST construct `ts` as `int(time.time())` — i.e. seconds,
    not milliseconds. Verify by:
      1. Pinning `time.time()` inside `app.ipc_client` to a known value.
      2. Capturing the `__auth` payload via fake socket.
      3. Asserting `ts == frozen_now_secs` (NOT `frozen_now_secs * 1000`).
      4. Asserting the HMAC token is computed against the seconds payload.
      5. Asserting a Rust verifier mirror (using the same frozen now)
         accepts the handshake.

    `sync_ipc_call` 必須以 `int(time.time())`（秒）構造 `ts`。本測試:
    凍結 `time.time()` → 攔截 socket → 驗 `ts` 等於 frozen 秒值
    （而非 *1000 毫秒值）→ 驗 HMAC token 對應秒值 payload →
    Rust verifier 鏡像確認 handshake 通過。
    """
    from app import ipc_client as ic

    frozen_now_secs = 1_700_000_000  # arbitrary fixed epoch / 任意固定 epoch
    monkeypatch.setattr(ic.time, "time", lambda: float(frozen_now_secs))

    fake_sock = _FakeSocket(_build_canned_replies())
    monkeypatch.setattr(
        "socket.socket", lambda *a, **kw: fake_sock
    )

    result = ic.sync_ipc_call("dummy_method", {"k": "v"}, timeout=1.0)
    assert result == {"ok": True}

    auth_msg = _extract_auth_payload(fake_sock)
    sent_ts = auth_msg["params"]["ts"]
    sent_token = auth_msg["params"]["token"]

    # (1) Unit assertion: ts equals seconds, NOT milliseconds.
    # 單位斷言：ts 為秒，非毫秒。
    assert sent_ts == frozen_now_secs, (
        f"sync_ipc_call sent ts={sent_ts} (expected {frozen_now_secs} seconds, "
        f"NOT {frozen_now_secs * 1000} milliseconds)"
    )

    # (2) HMAC self-consistency: token must match HMAC(secret, str(ts_secs)).
    # HMAC 自洽：token 必為對秒值 ts 的 HMAC。
    expected_token = _hmac_lib.new(
        _ipc_secret.encode("utf-8"),
        str(frozen_now_secs).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    assert sent_token == expected_token

    # (3) Rust verifier mirror accepts (now == ts → skew 0).
    # Rust verifier 鏡像通過（now == ts → skew 0）。
    assert _rust_verifier_accepts(
        _ipc_secret, sent_ts, sent_token, now_secs=frozen_now_secs
    )

    # Negative cross-check: a millisecond-valued ts would NOT verify
    # against the same Rust now, proving the unit matters.
    # 反證：毫秒 ts 在同一 Rust now 下不會通過，證明單位至關重要。
    assert not _rust_verifier_accepts(
        _ipc_secret,
        frozen_now_secs * 1000,
        sent_token,  # token irrelevant — skew alone rejects
        now_secs=frozen_now_secs,
    )


def test_sync_ipc_call_within_25s_skew_passes(
    _ipc_secret: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    (b) Boundary OK / 容差內 +25s

    Even if the engine's clock is 25s ahead of the client's clock when the
    handshake arrives, the Rust verifier (30s tolerance) MUST still accept.
    Done by:
      1. Pinning client `time.time()` to T0.
      2. Capturing the `__auth` handshake.
      3. Modeling Rust verifier with `now_secs = T0 + 25` (engine clock skewed
         +25s) and asserting it accepts.

    引擎時鐘比 client 快 25s 時，30s 容差內仍須通過。
    """
    from app import ipc_client as ic

    t0 = 1_700_000_000
    monkeypatch.setattr(ic.time, "time", lambda: float(t0))

    fake_sock = _FakeSocket(_build_canned_replies())
    monkeypatch.setattr("socket.socket", lambda *a, **kw: fake_sock)

    ic.sync_ipc_call("dummy_method", {}, timeout=1.0)

    auth_msg = _extract_auth_payload(fake_sock)
    sent_ts = auth_msg["params"]["ts"]
    sent_token = auth_msg["params"]["token"]

    # Engine clock 25s ahead → still within Rust 30s tolerance.
    # 引擎時鐘快 25s → 仍在 30s 容差內。
    assert _rust_verifier_accepts(
        _ipc_secret, sent_ts, sent_token, now_secs=t0 + 25
    ), "Rust verifier should accept handshake with +25s engine clock skew"

    # Symmetry: 25s lag also passes.
    # 對稱：慢 25s 也應通過。
    assert _rust_verifier_accepts(
        _ipc_secret, sent_ts, sent_token, now_secs=t0 - 25
    ), "Rust verifier should accept handshake with -25s engine clock skew"


def test_sync_ipc_call_beyond_60s_skew_rejects(
    _ipc_secret: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    (c) Boundary bad / 容差外 +60s

    Confirms the Rust verifier mirror rejects a 60s-skewed handshake.
    This test is the converse of (b) — it does NOT prove `sync_ipc_call`
    misbehaves; it proves the test harness correctly distinguishes
    "in tolerance" from "out of tolerance", so any future regression
    re-introducing milliseconds (skew ≈ 1.7e12) would be unambiguously
    detected by test (a) without false positives here.

    確認 Rust verifier 鏡像會拒絕 60s 偏移 handshake。本測試是 (b) 的對偶
    — 不是證明 `sync_ipc_call` 行為錯誤，而是證明測試 harness 能正確區分
    「容差內」與「容差外」，使未來若有人重新引入毫秒（偏移 ≈ 1.7e12），
    測試 (a) 能毫不含糊地發現，而本測試也不會誤判。
    """
    from app import ipc_client as ic

    t0 = 1_700_000_000
    monkeypatch.setattr(ic.time, "time", lambda: float(t0))

    fake_sock = _FakeSocket(_build_canned_replies())
    monkeypatch.setattr("socket.socket", lambda *a, **kw: fake_sock)

    ic.sync_ipc_call("dummy_method", {}, timeout=1.0)

    auth_msg = _extract_auth_payload(fake_sock)
    sent_ts = auth_msg["params"]["ts"]
    sent_token = auth_msg["params"]["token"]

    # +60s engine clock → outside 30s tolerance → rejection expected.
    # 引擎時鐘快 60s → 超出 30s 容差 → 預期拒絕。
    assert not _rust_verifier_accepts(
        _ipc_secret, sent_ts, sent_token, now_secs=t0 + 60
    ), "Rust verifier should reject handshake with +60s skew (>30s)"

    # -60s lag also rejects.
    # 慢 60s 也應拒絕。
    assert not _rust_verifier_accepts(
        _ipc_secret, sent_ts, sent_token, now_secs=t0 - 60
    ), "Rust verifier should reject handshake with -60s skew (>30s)"

    # Sanity: the regression case (ts in milliseconds) under any plausible
    # engine `now` yields skew ≫ 30s — guaranteed rejection.
    # 健全性：毫秒 ts 在任何合理的引擎 now 下偏移都遠大於 30s — 必然拒絕。
    ms_ts = t0 * 1000  # what the bug used to send
    fake_token_for_ms = _hmac_lib.new(
        _ipc_secret.encode("utf-8"),
        str(ms_ts).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    assert not _rust_verifier_accepts(
        _ipc_secret, ms_ts, fake_token_for_ms, now_secs=t0
    ), "Pre-fix millisecond ts should be unconditionally rejected"
