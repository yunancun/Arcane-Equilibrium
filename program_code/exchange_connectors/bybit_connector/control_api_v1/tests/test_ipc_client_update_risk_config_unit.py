"""
Unit tests for `EngineIPCClient.update_risk_config` defensive guards
(Tier 6 Track 1, EDGE-P1b-FUP-NEGATIVE-GUARD, 2026-04-26).

Background / 背景
==================
Per `EDGE-P1b-FUP-STALE-PEAK-IPC` (2026-04-26 commits c2ca032/etc.) the typed
wrapper `EngineIPCClient.update_risk_config` exposes `exit_stale_peak_ms` (the
8th `exit_*` field) so callers (operator CLI / agent self-tune) can patch the
runtime `ExitConfig.stale_peak_ms` without going through the raw
`self.call("update_risk_config", params=raw_dict)` percentile path.

The Rust schema field is `i64` milliseconds and `validate()` rejects negative
values. Without a Python-side guard, a caller passing `-1` would round-trip:
serde_json would error during deserialize ("invalid type: negative integer"),
but the surface to the Python caller is opaque after IPC roundtrip.

`EDGE-P1b-FUP-NEGATIVE-GUARD` (Tier 6 Track 1) adds a Python-side defensive
guard that mirrors the Rust validate() contract — fail-fast with a precise,
actionable error message **before** sending the IPC.

These tests pin down:
  (a) Negative `exit_stale_peak_ms` raises `ValueError` with the expected
      message — and the IPC `call(...)` is NEVER invoked.
  (b) Zero `exit_stale_peak_ms` is accepted (boundary value — Rust schema
      treats 0 as "no stale-peak penalty").
  (c) Positive `exit_stale_peak_ms` is forwarded into the IPC params dict
      under the key `exit_stale_peak_ms` (preserves existing wire contract).
  (d) Omitting `exit_stale_peak_ms` (default `None`) does NOT add the field
      to the params dict (preserves "no change" semantics).

The tests are pure-Python: they bypass the Unix socket entirely by mocking
`EngineIPCClient.call` (which is what every public typed wrapper uses) and
asserting the arguments that would have flowed onto the wire.

`EngineIPCClient.update_risk_config` 對 `exit_stale_peak_ms` 防禦性 guard 的
單元測試（Tier 6 Track 1，EDGE-P1b-FUP-NEGATIVE-GUARD，2026-04-26）。

先前 `EDGE-P1b-FUP-STALE-PEAK-IPC`（2026-04-26）在 typed wrapper 暴露
`exit_stale_peak_ms` 欄位（第 8 個 `exit_*` 欄位）。Rust schema field 為
`i64` 毫秒，`validate()` 拒負值。無 Python 端 guard 時 caller 傳 `-1` 會
round-trip 到 Rust serde_json 解碼失敗，但錯誤面對 Python caller 不透明。
本 ticket 補上 Python 端 fail-fast guard 鏡射 Rust validate() 契約 —
在 IPC 發送前回傳精確且可動的錯誤訊息。

本測試固定：
  (a) 負值 `exit_stale_peak_ms` 拋 `ValueError`，且 IPC `call(...)` 永不被呼。
  (b) 零值通過（邊界 — Rust schema 視 0 為「無 stale-peak 懲罰」）。
  (c) 正值轉 forward 到 IPC params dict 的 `exit_stale_peak_ms` key
      （維持既有 wire contract）。
  (d) 省略（預設 `None`）不加入 params dict（維持「不變」語意）。

純 Python 測試：mock `EngineIPCClient.call` 完全繞過 Unix socket，
斷言 IPC 上線前的 params 內容。
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.ipc_client import EngineIPCClient  # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
# Helpers / 輔助
# ─────────────────────────────────────────────────────────────────────────────


def _run(coro):
    """Run a coroutine in an isolated event loop / 在獨立 event loop 跑 coroutine."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ─────────────────────────────────────────────────────────────────────────────
# Tests / 測試
# ─────────────────────────────────────────────────────────────────────────────


class TestUpdateRiskConfigStalePeakMsGuard:
    """Negative-value guard for `exit_stale_peak_ms` parameter.

    `exit_stale_peak_ms` 參數的 negative-value guard。
    """

    def test_negative_one_raises_and_skips_ipc(self) -> None:
        """
        Passing -1 raises ValueError with explicit message; IPC call is NOT made.
        傳 -1 拋 ValueError 帶明確訊息；IPC call 不被觸發。
        """
        client = EngineIPCClient(socket_path="/tmp/test-fake.sock")
        with patch.object(client, "call", new_callable=AsyncMock) as mock_call:
            with pytest.raises(ValueError, match=r"exit_stale_peak_ms must be >= 0"):
                _run(client.update_risk_config(exit_stale_peak_ms=-1))
            # Crucially: IPC call must NOT have been invoked — guard fails fast
            # BEFORE wire payload construction.
            # 關鍵：IPC call 永不被呼 — guard 在 wire payload 構造前 fail-fast。
            mock_call.assert_not_called()

    def test_negative_large_value_raises(self) -> None:
        """
        Passing a large negative value (e.g. -1_000_000) raises with the same
        message — the guard is value-direction-based, not magnitude-based.
        傳大負值（如 -1_000_000）也拋 ValueError —— guard 為「方向」而非「量級」判定。
        """
        client = EngineIPCClient(socket_path="/tmp/test-fake.sock")
        with patch.object(client, "call", new_callable=AsyncMock) as mock_call:
            with pytest.raises(ValueError, match=r"exit_stale_peak_ms must be >= 0"):
                _run(client.update_risk_config(exit_stale_peak_ms=-1_000_000))
            mock_call.assert_not_called()

    def test_zero_accepted_boundary(self) -> None:
        """
        Zero is a valid Rust schema value (treated as "no stale-peak penalty");
        guard MUST accept it. The wrapper should forward `exit_stale_peak_ms=0`
        into the IPC params dict.
        零為 Rust schema 合法值（視為「無 stale-peak 懲罰」）；guard 必接受並 forward。
        """
        client = EngineIPCClient(socket_path="/tmp/test-fake.sock")
        with patch.object(
            client, "call", new_callable=AsyncMock, return_value={"ok": True}
        ) as mock_call:
            result = _run(client.update_risk_config(exit_stale_peak_ms=0))
            assert result == {"ok": True}
            mock_call.assert_called_once()
            args, kwargs = mock_call.call_args
            assert args[0] == "update_risk_config"
            assert kwargs["params"]["exit_stale_peak_ms"] == 0

    def test_positive_forwarded_into_params(self) -> None:
        """
        Positive value is forwarded into IPC params under key `exit_stale_peak_ms`
        (preserves existing EDGE-P1b-FUP-STALE-PEAK-IPC wire contract).
        正值轉 forward 到 IPC params 的 `exit_stale_peak_ms` key（維持既有 wire 契約）。
        """
        client = EngineIPCClient(socket_path="/tmp/test-fake.sock")
        with patch.object(
            client, "call", new_callable=AsyncMock, return_value={"ok": True}
        ) as mock_call:
            _run(client.update_risk_config(exit_stale_peak_ms=5_000))
            mock_call.assert_called_once()
            args, kwargs = mock_call.call_args
            assert args[0] == "update_risk_config"
            assert kwargs["params"] == {"exit_stale_peak_ms": 5_000}

    def test_omitted_does_not_add_field(self) -> None:
        """
        Omitting `exit_stale_peak_ms` (default None) does NOT inject the key
        into IPC params (preserves "no change" semantics for partial patches).
        省略 `exit_stale_peak_ms`（預設 None）不注入 key 到 IPC params
        （維持 partial patch 的「不變」語意）。
        """
        client = EngineIPCClient(socket_path="/tmp/test-fake.sock")
        with patch.object(
            client, "call", new_callable=AsyncMock, return_value={"ok": True}
        ) as mock_call:
            _run(client.update_risk_config(hard_stop_pct=0.05))
            mock_call.assert_called_once()
            args, kwargs = mock_call.call_args
            assert args[0] == "update_risk_config"
            assert "exit_stale_peak_ms" not in kwargs["params"]
            assert kwargs["params"] == {"hard_stop_pct": 0.05}

    def test_error_message_mentions_rust_contract(self) -> None:
        """
        Error message must reference the Rust schema field to give the operator
        a precise, actionable surface (per EDGE-P1b-FUP-NEGATIVE-GUARD intent —
        opaque IPC roundtrip errors are unhelpful).
        錯誤訊息必須引用 Rust schema 欄位給 operator 精確且可動的錯誤面。
        """
        client = EngineIPCClient(socket_path="/tmp/test-fake.sock")
        with patch.object(client, "call", new_callable=AsyncMock):
            try:
                _run(client.update_risk_config(exit_stale_peak_ms=-42))
            except ValueError as e:
                msg = str(e)
                assert "exit_stale_peak_ms" in msg
                assert "must be >= 0" in msg
                assert "got -42" in msg
                assert "Rust" in msg or "rust" in msg.lower()
            else:
                pytest.fail("ValueError not raised for negative exit_stale_peak_ms")
