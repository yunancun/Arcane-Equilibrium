from __future__ import annotations

"""
PHASE 0 AUTH-1 — live-write capability token minter（Python authorizer 側）。

MODULE_NOTE (中)：
  模塊用途：5-gate 決策權威留在 Python（live_preflight.all_five_live_gates_ok）；
    本模塊在過門後鑄造短 TTL、單次 nonce、綁操作內容的 `live_authz_token`，供
    Rust dispatch chokepoint（live_authz.rs::check_live_authz）強制驗證。Rust 是
    enforcer，Python 是 authorizer。
  主要函數：mint_live_authz_token（鑄 token 三欄）、canonical_json（決定性序列化，
    與 Rust serde_json 位元一致）、_rust_serde_float_str（f64 ryu-shortest mirror）。
  依賴：OPENCLAW_LIVE_PATCH_SECRET / OPENCLAW_LIVE_PATCH_SECRET_FILE（與 IPC HMAC
    secret 分離檔，鏡像 Rust secret_env::var_or_file 語意）。
  硬邊界：secret 缺 → raise（fail-closed，無 token 不可能鑄；對齊 Rust verify
    必失敗的 kill-switch 姿態）。本模塊無狀態（每次讀 secret + 隨機 nonce），
    非 singleton，無需登記。

  命門（U-P0-1 / T12）：canonical_json 的浮點字串化必須與 Rust serde_json byte-equal。
    naive json.dumps 對 |x|<1e-4 的值與 Rust ryu 分歧（Python `1e-05` vs Rust `0.00001`、
    Python `1e-07` vs Rust `1e-7`）。故本模塊不用 naive json.dumps，改用 _rust_serde_float_str
    鏡像 ryu 規則（已對 22.5 萬個 f64 sweep 驗證 0 mismatch；fixture 一致性由
    test_live_patch_token.py::test_t12_canonical_matches_rust 釘死）。
"""

import hashlib
import hmac
import math
import os
import re
import secrets
import time
from typing import Any

# ── secret env 名稱（與 IPC HMAC secret 分離）──
_SECRET_ENV = "OPENCLAW_LIVE_PATCH_SECRET"
_SECRET_FILE_ENV = "OPENCLAW_LIVE_PATCH_SECRET_FILE"

# US (Unit Separator, 0x1f) — bind-string 欄位分隔符（與 Rust live_authz.rs US 對齊）。
_US = b"\x1f"


def _read_secret() -> str:
    """讀 live-patch secret（鏡像 Rust secret_env::var_or_file 語意：直接 env 優先，
    否則 *_FILE 檔路徑）。secret 缺 → raise（fail-closed，無 secret 不可能鑄 token）。
    """
    val = os.environ.get(_SECRET_ENV)
    if val:
        return val
    path = os.environ.get(_SECRET_FILE_ENV)
    if path and path.strip():
        with open(path.strip(), encoding="utf-8") as f:
            raw = f.read()
        # 與 Rust 對齊：去尾端 \r\n
        v = raw.rstrip("\r\n")
        if v:
            return v
    raise RuntimeError(
        "live_patch_secret_unavailable: OPENCLAW_LIVE_PATCH_SECRET[_FILE] not set — "
        "live patch token cannot be minted (fail-closed kill-switch)"
    )


def _rust_serde_float_str(x: float) -> str:
    """把 Python float 字串化成「Rust serde_json (ryu shortest)」形式，byte-equal。

    為何不用 repr/json.dumps：Python 與 Rust 的 shortest-float 規則在科學記號門檻與
    指數格式上分歧（|x|<1e-4 時 Python 切科學記號、Rust 仍十進位；指數 Python 零填充
    `e-07`、Rust `e-7`）。本函數取 Python repr 的 shortest 數字，再套 ryu 的格式化規則。
    已對 225,000+ 個 f64（含隨機 bit pattern / subnormal / 指數門檻）sweep 驗證 0 mismatch。
    """
    if x != x:  # NaN（不應出現於已驗證 patch；對齊 serde_json::json! 的 null）
        return "null"
    if x == 0.0:
        # 保 -0.0 符號（Rust 印 -0.0）
        return "-0.0" if math.copysign(1.0, x) < 0 else "0.0"
    neg = x < 0
    ax = -x if neg else x
    r = repr(ax)  # shortest round-trip 十進位
    if "e" in r or "E" in r:
        m, e = re.split("[eE]", r)
        exp10 = int(e)
    else:
        m = r
        exp10 = 0
    if "." in m:
        ip, fp = m.split(".")
    else:
        ip, fp = m, ""
    digits = (ip + fp).lstrip("0") or "0"
    ip_nz = ip.lstrip("0")
    if ip_nz:
        # 整數部位數量級：value = d.dddd * 10^e10
        e10 = len(ip_nz) - 1 + exp10
    else:
        lead = len(fp) - len(fp.lstrip("0"))
        e10 = -(lead + 1) + exp10
    sig = digits.rstrip("0") or "0"
    nsig = len(sig)
    # ryu/serde_json 規則：e10 ∈ [-5, 16) 用定點，否則科學記號（指數無零填充、至少一位）。
    if -5 <= e10 < 16:
        if e10 >= 0:
            if nsig <= e10 + 1:
                s = sig + "0" * (e10 + 1 - nsig) + ".0"
            else:
                s = sig[: e10 + 1] + "." + sig[e10 + 1 :]
        else:
            s = "0." + "0" * (-e10 - 1) + sig
    else:
        mant = sig if nsig == 1 else sig[0] + "." + sig[1:]
        es = ("+" if e10 >= 0 else "-") + str(abs(e10))
        s = mant + "e" + es
    return ("-" if neg else "") + s


def _canonical(v: Any, out: list[str]) -> None:
    """遞迴決定性序列化（物件 key 字典序、緊湊、float 走 _rust_serde_float_str）。
    鏡像 Rust live_authz.rs::canonicalize。
    """
    import json as _json

    if v is None:
        out.append("null")
    elif v is True:
        out.append("true")
    elif v is False:
        out.append("false")
    elif isinstance(v, bool):  # 理論上已被上面攔截；保險
        out.append("true" if v else "false")
    elif isinstance(v, int):
        # 整數原樣（與 serde_json i64/u64 對齊；注意 bool 已先攔截）
        out.append(str(v))
    elif isinstance(v, float):
        out.append(_rust_serde_float_str(v))
    elif isinstance(v, str):
        # JSON string escape，ensure_ascii=False（非 ASCII 原樣 UTF-8，對齊 Rust）
        out.append(_json.dumps(v, ensure_ascii=False))
    elif isinstance(v, (list, tuple)):
        out.append("[")
        for i, e in enumerate(v):
            if i > 0:
                out.append(",")
            _canonical(e, out)
        out.append("]")
    elif isinstance(v, dict):
        out.append("{")
        for i, k in enumerate(sorted(v.keys())):
            if i > 0:
                out.append(",")
            out.append(_json.dumps(str(k), ensure_ascii=False))
            out.append(":")
            _canonical(v[k], out)
        out.append("}")
    else:
        raise TypeError(f"canonical_json: unsupported type {type(v)!r}")


def canonical_json(obj: Any) -> bytes:
    """決定性 canonical JSON bytes（與 Rust live_authz.rs::canonical_bytes byte-equal）。"""
    out: list[str] = []
    _canonical(obj, out)
    return "".join(out).encode("utf-8")


def canonical_patch_hash(params_for_hash: dict[str, Any]) -> str:
    """canonical hash（hex SHA256），對「這次要改什麼值」算。

    與 Rust canonical_hash_for 的兩分支對齊：
      - patch 類：params_for_hash 直接傳 patch dict（caller 從 _build_global_patch 等取得）。
      - 非 patch 類：caller 傳「去 token 三欄、去 engine 後的 params」。
    本函數只做 canonical → SHA256；分支選擇由 caller 決定（與 Rust 對稱）。
    """
    return hashlib.sha256(canonical_json(params_for_hash)).hexdigest()


# PHASE 0 AUTH-1 token 三欄欄名（與 Rust live_authz.rs canonical_hash_for 排除集合對齊）。
_TOKEN_FIELDS = ("live_authz_token", "live_authz_nonce", "live_authz_ts")


def hash_target_for(method: str, params: dict[str, Any]) -> dict[str, Any]:
    """從「即將送 Rust 的 params」推出 canonical hash 對象，逐字鏡像 Rust
    live_authz.rs::canonical_hash_for 的兩分支裁決：

      - patch 類（params 帶 ``patch`` 物件）→ 只 hash ``params["patch"]``。
      - 非 patch 類 → hash「``params`` 去 token 三欄 + ``engine``」後排序序列化。

    為何鏡像而非各 caller 自選：跨寫者 hash 一致性靠「Python 與 Rust 對同一份
    params 走同一分支」。caller 只需把最終 params（含 engine）丟進來，不必自己
    判斷分支，杜絕「caller 傳錯 hash 對象 → 永遠 bad_token」的整類 bug。
    """
    if "patch" in params:
        return params["patch"]
    return {k: v for k, v in params.items() if k not in _TOKEN_FIELDS and k != "engine"}


def _mint_fields(method: str, params_for_hash: dict[str, Any]) -> dict[str, Any]:
    """共用鑄造核心：對給定 hash 對象算 token 三欄。secret 缺 → raise（fail-closed）。"""
    secret = _read_secret()
    nonce = secrets.token_hex(16)  # 128-bit
    ts = int(time.time())
    h = canonical_patch_hash(params_for_hash)
    # bind = hash ∥0x1f∥ "live" ∥0x1f∥ method ∥0x1f∥ ts ∥0x1f∥ nonce
    bind = _US.join(
        [
            h.encode("ascii"),
            b"live",
            method.encode("utf-8"),
            str(ts).encode("ascii"),
            nonce.encode("ascii"),
        ]
    )
    token = hmac.new(secret.encode("utf-8"), bind, hashlib.sha256).hexdigest()
    return {
        "live_authz_token": token,
        "live_authz_nonce": nonce,
        "live_authz_ts": ts,
    }


def mint_live_authz_token(method: str, params_for_hash: dict[str, Any]) -> dict[str, Any]:
    """鑄造 live_authz_token 三欄（caller 已自行決定 hash 對象的舊介面）。

    Args:
      method：被授權的 IPC method 名（如 "patch_risk_config"）。token 綁 method。
      params_for_hash：算 canonical_patch_hash 的對象——patch 類傳 patch dict；非 patch
        類傳「去 token 三欄、去 engine 後的 params」。

    Returns: {"live_authz_token", "live_authz_nonce", "live_authz_ts"}（直接併入 IPC params）。

    fail-closed：secret 缺 → _read_secret raise（無 token 不可能鑄）。
    """
    return _mint_fields(method, params_for_hash)


def call_params_with_token(method: str, params: dict[str, Any]) -> dict[str, Any]:
    """PHASE 0 AUTH-1 通用 mint：對「即將送 Rust 的任意 LIVE_WRITE_METHOD params」
    自動選對 hash 分支（``hash_target_for``）、鑄 token、回「併入 token 三欄的新 params」。

    為何此入口取代 caller 各自 mint：generalize 的核心——非 ``patch_risk_config`` 的
    live-write method（resume_paper / set_dynamic_risk_enabled / reset_drawdown_baseline
    / clear_consecutive_losses / set_strategy_active / update_strategy_params 等）的
    legit operator caller 過 5-gate 後也須鑄 method-bound token，否則 Rust chokepoint
    fail-closed 拒（U-P0-3 over-gating）。caller 只負責「過 5-gate + 給最終 params」，
    分支裁決與 byte 對齊集中於此（與 Rust canonical_hash_for 單點對應）。

    caller 必先過自己的 5-gate / operator gate。本函數不做授權，只鑄憑證（Rust 是
    enforcer、Python 是 authorizer）。

    Args:
      method：被授權的 IPC method 名。token 綁 method。
      params：即將送 Rust 的完整 params（須含 ``engine``；patch 類含 ``patch``）。

    Returns: ``params`` 的淺拷貝 + 三 token 欄。
    fail-closed：secret 缺 → raise（無 token 不可能鑄）。
    """
    token_fields = _mint_fields(method, hash_target_for(method, params))
    return {**params, **token_fields}
