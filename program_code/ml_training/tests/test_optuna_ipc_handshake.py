"""
Optuna IPC __auth handshake regression test
（對應 commit 3d8d543e: ml_training cron IPC __auth fix）

MODULE_NOTE
模組目的：保護 `optuna_optimizer._resolve_ipc_secret` /
`_read_response_line` / `_send_ipc_command` 三個 IPC helper 函數的
不變式不被未來 commit 破壞。涵蓋四組 case：

  (a) `_resolve_ipc_secret` env-first / file-fallback 5 case，
      與 `secret_runtime.get_secret_value` 行為等價。
  (b) `_send_ipc_command` mock socket 4 case，覆蓋 fail-closed
      不 silent skip 路徑（無 secret raise / 業務正常 / auth false /
      timeout）。
  (c) Wire format byte-equal 1 case：對齊
      `app.ipc_client.ipc_client._authenticate` line 595-614 的
      `__auth` payload 構造（id=0 / method=__auth / token = HMAC-
      SHA256(secret, str(ts).encode("utf-8")).hexdigest() /
      ensure_ascii=False / `+ "\\n"` terminated）。
  (d) Critical fail-closed 不變式 1 case：secret 設置且 server 回
      `{authenticated: false}` 必須 raise RuntimeError，禁 silent
      return None / silent skip → 走「樣本不足」分支吃掉 error。
      這條是 E2 反問 #4 的 regression：以前 silent skip 把 IPC fail
      偽裝成業務 fills<80 不足，必避。

WHY：E2 review 對 commit `3d8d543e` 的判定為 RETURN-TO-E1，唯一
退回原因是 process gap — E1 自報 9/9 unit test 但 0 test file
進 repo。本 regression test 就是把 E1 round 1 自跑的 ad-hoc
inline test 編碼成 CI-runnable form，確保：

  1. byte-equal 不變式（11/11 細項）對未來 wire format drift 有守。
  2. fail-closed 不變式對未來「為了 cron 不 fail 順手把 RuntimeError
     吞掉」反模式有守。
  3. ml_parameter_suggestions=0 真因 = fills<80 業務樣本不足，IPC
     auth 真通；future commit 把 silent skip 引回來會立即被 (d)
     case 抓到。

注：本 test 檔故意不 import optuna — IPC helper 不依賴 optuna，
optuna_optimizer.py 的 `try: import optuna` 已捕 ImportError，本檔
import 只觸發 graceful warning（Mac 無 optuna 也可跑）。
"""

from __future__ import annotations

import hashlib
import hmac as _hmac_lib
import json
import socket
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from program_code.ml_training.optuna_optimizer import (
    _read_response_line,
    _resolve_ipc_secret,
    _send_ipc_command,
)


# ─────────────────────────────────────────────────────────────────────────────
# (a) `_resolve_ipc_secret` 5 case
#
# 對齊基準：`app.ipc_client.secret_runtime.get_secret_value`
# 不變式：env-first / file-fallback；OSError 不 raise（fail-soft 回 None）；
#       trailing whitespace 必 strip；env 與 file 同存在時 env 勝。
# ─────────────────────────────────────────────────────────────────────────────


def test_resolve_ipc_secret_env_var_direct(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """case 1: OPENCLAW_IPC_SECRET env var 直設 → 回傳 env value。

    對齊 ipc_client `secret_runtime.get_secret_value` 的「if value: return value」
    分支：truthy env value 直接回傳，不 strip / 不檢查 file。
    """
    monkeypatch.setenv("OPENCLAW_IPC_SECRET", "direct-env-secret-value")
    monkeypatch.delenv("OPENCLAW_IPC_SECRET_FILE", raising=False)

    assert _resolve_ipc_secret() == "direct-env-secret-value"


def test_resolve_ipc_secret_file_fallback(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """case 2: OPENCLAW_IPC_SECRET_FILE 指向有效 file → 讀檔內容。

    cron 場景下 systemd cron 不繼承 daemon shell env，必走 file path；
    這條覆蓋了 commit 3d8d543e cron.sh 注入 OPENCLAW_IPC_SECRET_FILE
    的最常見 happy path。
    """
    secret_file = tmp_path / "ipc_secret.txt"
    secret_file.write_text("file-resolved-secret", encoding="utf-8")

    monkeypatch.delenv("OPENCLAW_IPC_SECRET", raising=False)
    monkeypatch.setenv("OPENCLAW_IPC_SECRET_FILE", str(secret_file))

    assert _resolve_ipc_secret() == "file-resolved-secret"


def test_resolve_ipc_secret_missing_file_returns_none(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """case 3: file path 但 file 不存在 → OSError → 回傳 None（fail-soft）。

    不可 raise — `_resolve_ipc_secret` 對 OSError 必須 fail-soft 回 None，
    讓 caller `_send_ipc_command` 走「無 secret 跳 auth」分支（後續若 engine
    需要 auth 自會在 first message 拒收，由 (d) case 守 fail-closed 不變式）。
    """
    missing_path = tmp_path / "does-not-exist.txt"
    assert not missing_path.exists()

    monkeypatch.delenv("OPENCLAW_IPC_SECRET", raising=False)
    monkeypatch.setenv("OPENCLAW_IPC_SECRET_FILE", str(missing_path))

    # 不可 raise；必須 None
    assert _resolve_ipc_secret() is None


def test_resolve_ipc_secret_strips_trailing_whitespace(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """case 4: file 內容含 trailing `\\n` → 必須 strip。

    `secrets/environment_files/ipc_secret.txt` 由 shell echo 寫入時尾隨換行
    幾乎必然存在；HMAC token 對 secret 任何尾隨字節敏感（hex 不一致即驗證
    失敗），strip 不變式必守。
    """
    secret_file = tmp_path / "ipc_secret.txt"
    secret_file.write_text("trimmed-secret\n\t \n", encoding="utf-8")

    monkeypatch.delenv("OPENCLAW_IPC_SECRET", raising=False)
    monkeypatch.setenv("OPENCLAW_IPC_SECRET_FILE", str(secret_file))

    assert _resolve_ipc_secret() == "trimmed-secret"


def test_resolve_ipc_secret_env_takes_precedence_over_file(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """case 5: env var 與 file 同設 → env var 優先。

    與 ipc_client `secret_runtime.get_secret_value` 行為等價：if direct env
    truthy: return direct（不檢查 file）。若這條反過來 file > env，會違反
    cross-module 不變式且 multi-source 解析時上層 service env 注入會被檔案值
    意外覆蓋。
    """
    secret_file = tmp_path / "ipc_secret.txt"
    secret_file.write_text("from-file", encoding="utf-8")

    monkeypatch.setenv("OPENCLAW_IPC_SECRET", "from-env")
    monkeypatch.setenv("OPENCLAW_IPC_SECRET_FILE", str(secret_file))

    assert _resolve_ipc_secret() == "from-env"


# ─────────────────────────────────────────────────────────────────────────────
# Fake socket helpers（mock 不掩蓋邏輯：捕獲 sendall / recv 真實 byte）
# 對齊 program_code/exchange_connectors/.../tests/test_ipc_client_hmac_ts_unit.py
# 的 _FakeSocket pattern；recv 改成 buffer 模式（_send_ipc_command 用
# `recv(IPC_RECV_BUFFER)` 而非逐字節 recv(1)）。
# ─────────────────────────────────────────────────────────────────────────────


class _FakeSocket:
    """`socket.socket(AF_UNIX, SOCK_STREAM)` 的替身。

    捕獲 `sendall()` 寫入內容；`recv(n)` 每次返回 reply queue 的下一條完整
    newline-delimited line（含 trailing `\\n`）。

    為什麼按 line 切片返回：`optuna_optimizer._read_response_line` 的實作對
    「sock.recv 一次返回多條 line」並未做 unread-buffer 處理 — 第一次 recv
    若拿到 `line1\\nline2\\n`，line1 被消費後 line2 會被丟。實際 engine 端
    Unix domain socket 下，server 是 sequential reply（auth 處理完才釋放
    business call），所以 reader 不需 unread buffer。本 FakeSocket 模擬這個
    server-side sequential 特性：每呼一次 recv → 釋放下一條 reply 的全部
    bytes（至多 n 字節，超量留下一次 recv），這對 IPC_RECV_BUFFER=65536
    場景而言 reply <512 bytes 不會被截斷。

    `_send_ipc_command` 用 `socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)`
    建構（非 context manager），所以本 fake 不需 `__enter__/__exit__`，但保留
    `close()` 供 try/finally 使用。
    """

    def __init__(self, reply_lines: list[bytes]) -> None:
        # 每筆 reply_line = 一條完整 newline-delimited JSON-RPC 回覆（不含 \n）
        # 內部存 list of bytes-with-trailing-\n，recv 一次釋一條（模擬 server
        # sequential reply 行為）。
        self._reply_queue: list[bytes] = [line + b"\n" for line in reply_lines]
        self._current: bytes = b""  # 當前正釋出的 line 殘餘（recv n < len 時）
        self.sent_payloads: list[bytes] = []
        self.connected_to: str | None = None
        self.timeout_secs: float | None = None
        self.closed: bool = False

    def settimeout(self, t: float) -> None:
        self.timeout_secs = t

    def connect(self, path: str) -> None:
        self.connected_to = path

    def sendall(self, data: bytes) -> None:
        self.sent_payloads.append(data)

    def recv(self, n: int) -> bytes:
        # 若 _current 還有殘餘字節，繼續釋出同一條 line
        if not self._current:
            if not self._reply_queue:
                return b""  # connection closed / 連線被對端關閉
            self._current = self._reply_queue.pop(0)
        chunk = self._current[:n]
        self._current = self._current[n:]
        return chunk

    def close(self) -> None:
        self.closed = True


def _build_auth_ok_response(authenticated: bool = True) -> bytes:
    """構造 engine 端 `__auth` 成功 / 失敗回覆。"""
    return json.dumps(
        {
            "jsonrpc": "2.0",
            "result": {"authenticated": authenticated},
            "id": 0,
        }
    ).encode("utf-8")


def _build_business_ok_response(result: dict[str, Any]) -> bytes:
    """構造業務 method 成功回覆（id=1）。"""
    return json.dumps(
        {"jsonrpc": "2.0", "result": result, "id": 1}
    ).encode("utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# (b) `_send_ipc_command` mock socket 4 case
#
# 不變式：
#   1. secret 缺失 → engine 端 first-message-must-be-__auth 必拒，故
#      `_send_ipc_command` 不應跳過 auth 後送業務 call（該 call 100%
#       會被 engine 拒絕）。但 helper 的當前語義是：secret None → skip
#       auth，直接送業務 method（讓 engine 拒絕並回 RuntimeError）。
#       本 case group 驗證 wire 1 = business（無 auth wire），驗證
#       即使 engine 後續拒收，error path 也是 RuntimeError 而非
#       silent return。
#   2. server 回 authenticated=true → auth 通過 → 後續 business call
#      正常 dispatch + result extracted。
#   3. server 回 authenticated=false → RuntimeError（不可 silent skip）。
#   4. server timeout → RuntimeError "ipc timeout"（不可 silent skip）。
# ─────────────────────────────────────────────────────────────────────────────


def test_send_ipc_command_no_secret_skips_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """case 1: 無 secret → 不送 __auth，只送業務 call（wire1 = business）。

    當前語義：secret None → skip auth，直接 send business method。
    若 engine 端要求 auth，business call 會被 engine 拒（first message
    must be __auth）→ caller 收 RuntimeError。本 case 模擬 engine 端
    寬鬆模式（不要求 auth），驗證 wire1 = business 而非 __auth。

    為什麼要驗：未來若有人「順手」加上「無 secret 也送 fake __auth」
    可能讓 engine 端拒收 + caller bypass，這條守住現有契約。
    """
    monkeypatch.delenv("OPENCLAW_IPC_SECRET", raising=False)
    monkeypatch.delenv("OPENCLAW_IPC_SECRET_FILE", raising=False)

    fake = _FakeSocket([_build_business_ok_response({"hello": "world"})])
    monkeypatch.setattr(socket, "socket", lambda *a, **kw: fake)

    result = _send_ipc_command("/dev/null", "ping", {"k": 1})

    assert result == {"hello": "world"}
    assert fake.connected_to == "/dev/null"

    # wire 1 = business call（id=1，method=ping）— 沒 __auth 前綴
    assert len(fake.sent_payloads) == 1
    msg = json.loads(fake.sent_payloads[0].decode("utf-8").rstrip("\n"))
    assert msg == {
        "jsonrpc": "2.0",
        "method": "ping",
        "id": 1,
        "params": {"k": 1},
    }


def test_send_ipc_command_with_secret_auth_then_business(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """case 2: 有 secret + auth 通 → wire1=__auth(id=0)、wire2=business(id=1)。

    Happy path：cron 場景下 OPENCLAW_IPC_SECRET_FILE → file 解析成功 →
    `_send_ipc_command` 先送 __auth handshake → engine 回 authenticated=true
    → 接著送 business method → engine 回 result。
    """
    secret = "test-cron-secret"
    monkeypatch.setenv("OPENCLAW_IPC_SECRET", secret)
    monkeypatch.delenv("OPENCLAW_IPC_SECRET_FILE", raising=False)

    fake = _FakeSocket(
        [
            _build_auth_ok_response(authenticated=True),
            _build_business_ok_response({"ranges": {"foo": [1, 2]}}),
        ]
    )
    monkeypatch.setattr(socket, "socket", lambda *a, **kw: fake)

    result = _send_ipc_command(
        "/dev/null", "get_param_ranges", {"strategy": "ma_crossover"}
    )

    assert result == {"ranges": {"foo": [1, 2]}}
    assert len(fake.sent_payloads) == 2

    # wire 1 = __auth
    auth_msg = json.loads(fake.sent_payloads[0].decode("utf-8").rstrip("\n"))
    assert auth_msg["method"] == "__auth"
    assert auth_msg["id"] == 0
    assert "token" in auth_msg["params"]
    assert "ts" in auth_msg["params"]

    # wire 2 = business call
    biz_msg = json.loads(fake.sent_payloads[1].decode("utf-8").rstrip("\n"))
    assert biz_msg == {
        "jsonrpc": "2.0",
        "method": "get_param_ranges",
        "id": 1,
        "params": {"strategy": "ma_crossover"},
    }


def test_send_ipc_command_auth_error_response_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """case 3a: secret 設置 + server 回 {error: ...} → RuntimeError。

    覆蓋 optuna_optimizer.py:391-395 的 `if "error" in auth_resp` 分支。
    對齊 engine 端 connection.rs 拒收 stale ts / 錯誤 token 時的 JSON-RPC
    error frame。caller 必收 RuntimeError，不可 silent skip。
    """
    monkeypatch.setenv("OPENCLAW_IPC_SECRET", "wrong-secret")
    monkeypatch.delenv("OPENCLAW_IPC_SECRET_FILE", raising=False)

    auth_err = json.dumps(
        {
            "jsonrpc": "2.0",
            "error": {"code": -32600, "message": "auth token expired"},
            "id": 0,
        }
    ).encode("utf-8")

    fake = _FakeSocket([auth_err])
    monkeypatch.setattr(socket, "socket", lambda *a, **kw: fake)

    with pytest.raises(RuntimeError, match=r"IPC __auth rejected.*-32600.*"):
        _send_ipc_command("/dev/null", "get_param_ranges", {})


def test_send_ipc_command_socket_timeout_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """case 4: server timeout 透過 socket.timeout → RuntimeError 路徑。

    `_read_response_line` 在 sock.recv 上被 settimeout 包；timeout 觸發
    socket.timeout（Python 3.x 為 TimeoutError 別名）。本 case 驗 helper
    不可 silent skip，必 propagate 出 caller 可見的 exception（caller
    `_resolve_optuna_param_ranges` catch 後 status='unavailable:RuntimeError'
    分支會被走，這是 fail-closed 觀察軌跡）。

    我們不直接驗 RuntimeError 的訊息（socket.timeout 是 IOError 子類），
    驗 propagation 即可：函數不可吞錯誤回 None / 回 {}。
    """
    monkeypatch.setenv("OPENCLAW_IPC_SECRET", "any-secret")
    monkeypatch.delenv("OPENCLAW_IPC_SECRET_FILE", raising=False)

    class _TimeoutSocket(_FakeSocket):
        def recv(self, n: int) -> bytes:  # noqa: ARG002
            raise socket.timeout("recv timeout")

    fake = _TimeoutSocket([])
    monkeypatch.setattr(socket, "socket", lambda *a, **kw: fake)

    # propagate — 不可 return None 或 {} 把 timeout 吃掉
    with pytest.raises((socket.timeout, TimeoutError, OSError)):
        _send_ipc_command("/dev/null", "get_param_ranges", {})


# ─────────────────────────────────────────────────────────────────────────────
# (c) Wire format byte-equal vs `ipc_client._authenticate` 1 case
#
# 對齊基準：program_code/exchange_connectors/.../app/ipc_client.py:595-614
#   ts = int(time.time())
#   token = _hmac_lib.new(
#       secret.encode(), str(ts).encode(), hashlib.sha256
#   ).hexdigest()
#   request = {"jsonrpc":"2.0","method":"__auth",
#              "params":{"token":token,"ts":ts},"id":0}
#   payload = json.dumps(request, separators=(",",":"), ensure_ascii=False)
#            + "\n"
#   self._writer.write(payload.encode("utf-8"))
#
# `_send_ipc_command` 必須產生 byte-equal 的 wire 1。
# ─────────────────────────────────────────────────────────────────────────────


def test_send_ipc_command_auth_wire_byte_equal_to_ipc_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """case (c): __auth wire format 與 ipc_client._authenticate byte-equal。

    本 case 是 E2 round 1 verdict 「11/11 byte-equal」的 regression guard：
    凍結 `time.time()` → 攔截 socket → 提取 _send_ipc_command 的 wire 1
    → 與 ipc_client._authenticate 同樣 ts/secret 構造的 reference payload
    逐字節對比。

    任何 future commit 動到下列任何一處都會立即被本 test 抓到：
      - id=0 改 id=任意
      - method 名稱 "__auth" 改寫
      - separators=(",", ":") 移除 → JSON 多空格
      - ensure_ascii=False 改 True → 非 ASCII 字段被 escape（雖 token 純
        hex 不會觸發，但 future 加 unicode 字段會 byte-mismatch）
      - "\\n" terminator 漏寫
      - encode("utf-8") 改 ascii
    """
    secret = "byte-equal-test-secret"
    frozen_now = 1_700_000_000

    monkeypatch.setenv("OPENCLAW_IPC_SECRET", secret)
    monkeypatch.delenv("OPENCLAW_IPC_SECRET_FILE", raising=False)

    # 凍結 _send_ipc_command 用到的 time.time
    import program_code.ml_training.optuna_optimizer as oo

    monkeypatch.setattr(oo.time, "time", lambda: float(frozen_now))

    fake = _FakeSocket(
        [
            _build_auth_ok_response(authenticated=True),
            _build_business_ok_response({}),
        ]
    )
    monkeypatch.setattr(socket, "socket", lambda *a, **kw: fake)

    _send_ipc_command("/dev/null", "noop", None)

    # 構造對齊 ipc_client._authenticate 的 reference wire
    expected_token = _hmac_lib.new(
        secret.encode("utf-8"),
        str(frozen_now).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    reference_request = {
        "jsonrpc": "2.0",
        "method": "__auth",
        "params": {"token": expected_token, "ts": frozen_now},
        "id": 0,
    }
    reference_payload = (
        json.dumps(reference_request, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")

    # 逐字節對比
    actual_wire1 = fake.sent_payloads[0]
    assert actual_wire1 == reference_payload, (
        f"wire format drift!\n"
        f"actual:    {actual_wire1!r}\n"
        f"reference: {reference_payload!r}"
    )

    # 補充：HMAC token 64 hex chars（SHA256 → 32 bytes → 64 hex）
    auth_msg = json.loads(actual_wire1.decode("utf-8").rstrip("\n"))
    assert len(auth_msg["params"]["token"]) == 64
    assert auth_msg["params"]["ts"] == frozen_now


# ─────────────────────────────────────────────────────────────────────────────
# (d) Critical fail-closed 不變式 1 case
#
# 場景：OPENCLAW_IPC_SECRET 設置 + Rust engine 回 {authenticated: false}
# 不變式：`_send_ipc_command` 必須 raise RuntimeError；不可 silent return
#       None / silent skip 走「樣本不足」分支吃掉 error。
#
# Why critical：E2 反問 #4 揭示 ml_parameter_suggestions=0 真因 = fills<80
# 業務樣本不足；但 fix 前的 IPC silent fall through 把 `unavailable:RuntimeError`
# 路由偽裝成「樣本不足」，做 RCA 時 operator 會誤判「IPC 通了，是業務樣本不夠」
# 從而錯失真正的 IPC handshake bug。本 case 是這條反模式的 regression guard：
# 任何 future commit 把 RuntimeError 改成 silent return 都會破本 case。
# ─────────────────────────────────────────────────────────────────────────────


def test_send_ipc_command_authenticated_false_raises_no_silent_skip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """case (d): server 回 authenticated=false → RuntimeError，禁 silent skip。

    Critical fail-closed regression：optuna_optimizer.py:396-399 的
    `if not auth_resp.get("result", {}).get("authenticated"): raise RuntimeError`
    分支必觸發。

    若這條被未來人改成 `return None` 或 `pass` 等 silent skip，本 test
    會立即標 RED。
    """
    monkeypatch.setenv("OPENCLAW_IPC_SECRET", "any-secret")
    monkeypatch.delenv("OPENCLAW_IPC_SECRET_FILE", raising=False)

    # engine 回 authenticated=false（result 存在但 authenticated 為 false）
    auth_false = json.dumps(
        {
            "jsonrpc": "2.0",
            "result": {"authenticated": False},
            "id": 0,
        }
    ).encode("utf-8")

    fake = _FakeSocket([auth_false])
    monkeypatch.setattr(socket, "socket", lambda *a, **kw: fake)

    with pytest.raises(RuntimeError) as exc_info:
        _send_ipc_command("/dev/null", "get_param_ranges", {})

    # 確認錯誤訊息明指 authenticated=true 缺失（caller log 可定位）
    assert "authenticated" in str(exc_info.value).lower()

    # 補充驗證：不可送出 wire 2（business call）— auth 失敗即必停
    # 否則 engine 會收到非法 wire（auth 後業務直送）造成 connection 污染
    assert len(fake.sent_payloads) == 1, (
        f"auth failure must NOT proceed to business call; "
        f"sent_payloads={len(fake.sent_payloads)}"
    )


# 補充：缺 result 欄位也要 fail-closed（authenticated key 全缺）
def test_send_ipc_command_missing_authenticated_key_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """case (d-補): server 回 {result: {}} 缺 authenticated 鍵 → RuntimeError。

    `auth_resp.get("result", {}).get("authenticated")` 對 missing key 回 None
    （falsy），按代碼語義應 raise。本 case 補強 (d) 的邊界。
    """
    monkeypatch.setenv("OPENCLAW_IPC_SECRET", "any-secret")
    monkeypatch.delenv("OPENCLAW_IPC_SECRET_FILE", raising=False)

    auth_no_key = json.dumps(
        {"jsonrpc": "2.0", "result": {}, "id": 0}
    ).encode("utf-8")

    fake = _FakeSocket([auth_no_key])
    monkeypatch.setattr(socket, "socket", lambda *a, **kw: fake)

    with pytest.raises(RuntimeError):
        _send_ipc_command("/dev/null", "noop", None)
