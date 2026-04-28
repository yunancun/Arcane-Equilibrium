"""Python httpx-based Bybit V5 REST client — drop-in replacement for PyO3 BybitClient.
Python httpx 版 Bybit V5 REST 客戶端 — 取代 PyO3 BybitClient 的 drop-in 實作。

MODULE_NOTE (EN): Same public surface as the Rust PyO3 openclaw_core.BybitClient so
  Python call sites (strategy_ai_routes / live_session_routes / clean_restart_flatten)
  can switch over without code changes. All requests use a blocking httpx.Client
  because Python callers are synchronous FastAPI handlers / CLI scripts.

  Response shape contract mirrors the pythonize-serialized Rust structs:
    - refresh_balance() -> dict (WalletState w/ snake_case)
    - get_positions(...) -> list[dict] (raw Bybit V5 camelCase from /v5/position/list)
    - get_active_orders(...) -> list[dict] (Bybit V5 camelCase)
    - get_executions(...) -> list[dict] (Bybit V5 camelCase + closedPnl)
    - get_instrument(sym) -> dict | None (SymbolSpec-style snake_case)
    - place_order(...) -> dict with BOTH snake_case order_id / order_link_id AND
      the original camelCase orderId / orderLinkId (upstream callers use either
      form — see clean_restart_flatten.py:134).

  Credential loading mirrors the Rust BybitRestClient (LIVE-GUARD-1):
    Mainnet:  explicit param → slot file (env var fallback DISABLED)
    Other:    explicit param → env var BYBIT_API_KEY/SECRET → slot file

  HMAC-SHA256 signing follows Bybit V5 spec:
    sign_str = timestamp + api_key + recv_window + (query_string | json_body)
    X-BAPI-SIGN = hex(hmac_sha256(api_secret, sign_str))
    Reference: https://bybit-exchange.github.io/docs/v5/intro#authentication

MODULE_NOTE (中): 與 Rust PyO3 openclaw_core.BybitClient 相同的公開介面，讓 Python
  呼叫端（strategy_ai_routes / live_session_routes / clean_restart_flatten）可以
  零改動切換。所有請求使用阻塞 httpx.Client，因 Python 端呼叫者為同步 FastAPI
  handler / CLI 腳本。

  回應形狀契約對齊 Rust 端 pythonize 序列化的 struct（見上）。

  憑證載入對齊 Rust BybitRestClient LIVE-GUARD-1 契約。

  HMAC-SHA256 簽章依 Bybit V5 規範：sign_str = ts + api_key + recv_window + params。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import math
import os
import time
from pathlib import Path
from threading import RLock
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Error types / 錯誤類型
# ---------------------------------------------------------------------------

class BybitError(Exception):
    """Base class for all BybitClient errors / BybitClient 錯誤基類。"""


class BybitTransportError(BybitError):
    """HTTP / network / timeout error (no body, or body unparseable).
    HTTP / 網路 / 逾時錯誤（無 body 或無法解析）。"""


class BybitBusinessError(BybitError):
    """Bybit V5 returned HTTP 200 but retCode != 0.
    Bybit V5 回 HTTP 200 但 retCode != 0 的業務錯誤。"""

    def __init__(self, ret_code: int, ret_msg: str, response: Any = None):
        super().__init__(f"Bybit API error: retCode={ret_code}, retMsg={ret_msg}")
        self.ret_code = ret_code
        self.ret_msg = ret_msg
        self.response = response


class BybitCredentialsMissing(BybitError):
    """API key or secret not configured for a private endpoint call.
    私有端點呼叫時缺少 API key / secret。"""


# ---------------------------------------------------------------------------
# Environment mapping / 環境映射
# ---------------------------------------------------------------------------

# Base URL table mirrors Rust BybitEnvironment::rest_base_url():
#   bybit_rest_client.rs:85-91. LiveDemo shares the demo server with the live
#   slot key (engine LiveDemo mode).
# Base URL 表對齊 Rust BybitEnvironment：LiveDemo 用 live slot key 連 demo 伺服器。
_BASE_URLS: dict[str, str] = {
    "demo":      "https://api-demo.bybit.com",
    "testnet":   "https://api-testnet.bybit.com",
    "mainnet":   "https://api.bybit.com",
    "live":      "https://api.bybit.com",   # alias — same as mainnet
    "live_demo": "https://api-demo.bybit.com",
}

# Secret slot mapping (Rust: BybitEnvironment::secret_slot())
# Demo & Testnet share "demo"; Mainnet & LiveDemo share "live".
# Demo/Testnet 共用 "demo" 槽；Mainnet/LiveDemo 共用 "live" 槽。
_SECRET_SLOTS: dict[str, str] = {
    "demo":      "demo",
    "testnet":   "demo",
    "mainnet":   "live",
    "live":      "live",
    "live_demo": "live",
}


def _normalize_env(environment: str) -> str:
    """Normalize environment string (case-insensitive + 'live' alias).
    標準化環境字串（不區分大小寫 + 'live' 別名）。"""
    e = (environment or "").strip().lower()
    if e == "live":
        return "mainnet"   # historical alias used by Rust parse_environment
    if e in _BASE_URLS:
        return e
    # Safe default — never accidentally hit mainnet. Matches Rust default.
    # 安全默認 — 絕不意外連主網。對齊 Rust default。
    return "demo"


# ---------------------------------------------------------------------------
# Credential loading / 憑證載入
# ---------------------------------------------------------------------------

def _secrets_base_dir() -> Path:
    """Resolve the secrets base directory. Mirrors Rust read_secret_file().
    解析 secrets 基礎目錄，對齊 Rust read_secret_file()。

    Priority: $OPENCLAW_SECRETS_DIR → $HOME/BybitOpenClaw/secrets/secret_files/bybit.
    Cross-platform: uses HOME / USERPROFILE, no hardcoded paths (§七 準則).
    """
    env_dir = os.environ.get("OPENCLAW_SECRETS_DIR")
    if env_dir:
        return Path(env_dir)
    home = os.environ.get("HOME") or os.environ.get("USERPROFILE")
    if not home:
        # Extreme fallback — cwd + relative path. Tests set HOME explicitly.
        # 極端回退 — 當前目錄 + 相對。測試會顯式設 HOME。
        return Path.cwd() / "BybitOpenClaw" / "secrets" / "secret_files" / "bybit"
    return Path(home) / "BybitOpenClaw" / "secrets" / "secret_files" / "bybit"


def _read_secret_file(slot: str, name: str) -> Optional[str]:
    """Read a secret value from the standard slot file location.
    從標準 slot 文件位置讀取 secret 值。"""
    try:
        path = _secrets_base_dir() / slot / name
        if not path.exists():
            return None
        value = path.read_text(encoding="utf-8").strip()
        return value or None
    except OSError:
        return None


def _resolve_credentials(
    env: str,
    api_key: Optional[str],
    api_secret: Optional[str],
) -> tuple[str, str]:
    """Resolve (api_key, api_secret) honouring LIVE-GUARD-1 Rust-side contract.
    解析憑證，遵守 LIVE-GUARD-1 Rust 端契約。

    Mainnet:
        1. Explicit param (if non-empty)
        2. Secret file at {base}/live/{api_key|api_secret}
        (env var fallback DISABLED — LIVE-GUARD-1 Gate #2)

    Demo / Testnet / LiveDemo:
        1. Explicit param (if non-empty)
        2. Env var BYBIT_API_KEY / BYBIT_API_SECRET
        3. Secret file at {base}/{slot}/{api_key|api_secret}
    """
    is_mainnet = (env == "mainnet")
    slot = _SECRET_SLOTS.get(env, "demo")

    # Resolve api_key / 解析 api_key
    key = (api_key or "").strip() or None
    if key is None and not is_mainnet:
        key = (os.environ.get("BYBIT_API_KEY") or "").strip() or None
    if key is None:
        key = _read_secret_file(slot, "api_key")
    key = key or ""

    # Resolve api_secret / 解析 api_secret
    secret = (api_secret or "").strip() or None
    if secret is None and not is_mainnet:
        secret = (os.environ.get("BYBIT_API_SECRET") or "").strip() or None
    if secret is None:
        secret = _read_secret_file(slot, "api_secret")
    secret = secret or ""

    return key, secret


# ---------------------------------------------------------------------------
# HTTP request helper / HTTP 請求輔助
# ---------------------------------------------------------------------------

# Default HTTP timeout (seconds) — matches Rust Client::builder().timeout(10s).
# 預設 HTTP 逾時（秒）— 對齊 Rust 10s。
_DEFAULT_TIMEOUT_S = 10.0
# Default recv_window (ms) — matches Rust "5000".
# 預設 recv_window（毫秒）— 對齊 Rust。
_DEFAULT_RECV_WINDOW_MS = "5000"


# ---------------------------------------------------------------------------
# BybitClient — drop-in replacement for openclaw_core.BybitClient
# BybitClient — openclaw_core.BybitClient 的 drop-in 取代
# ---------------------------------------------------------------------------

class BybitClient:
    """Bybit V5 REST client — Python httpx implementation.
    Bybit V5 REST 客戶端 — Python httpx 實作。

    Same public API as the PyO3 openclaw_core.BybitClient so call sites can
    switch over without changes. All methods are blocking (sync) because
    FastAPI handlers / CLI tools are the consumers.
    與 PyO3 openclaw_core.BybitClient 相同 API，呼叫端可直接切換；
    所有方法為阻塞（sync），因消費端是 FastAPI handler / CLI。
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        environment: str = "demo",
    ):
        """Create a new BybitClient.
        創建新的 BybitClient。

        Args:
            api_key: Optional explicit API key (empty → fall through to env/slot).
            api_secret: Optional explicit API secret.
            environment: "demo" | "testnet" | "mainnet" | "live_demo".
                         Unknown values default to "demo" (safe default).
        """
        env = _normalize_env(environment)
        is_mainnet = (env == "mainnet")

        # LIVE-GUARD-1 Gate #1: operator opt-in on mainnet.
        # LIVE-GUARD-1 門 #1：Mainnet 需 operator 顯式 opt-in。
        if is_mainnet and os.environ.get("OPENCLAW_ALLOW_MAINNET", "") != "1":
            raise BybitBusinessError(
                ret_code=-1,
                ret_msg=(
                    "Mainnet blocked: set OPENCLAW_ALLOW_MAINNET=1 to enable / "
                    "主網被阻止：需設置 OPENCLAW_ALLOW_MAINNET=1"
                ),
                response={"blocked": True, "guard": "OPENCLAW_ALLOW_MAINNET"},
            )

        key, secret = _resolve_credentials(env, api_key, api_secret)

        # LIVE-GUARD-1 Gate #3: fail-closed on empty credentials for Mainnet.
        # LIVE-GUARD-1 門 #3：Mainnet 憑證空 → 構造時 Err。
        if is_mainnet and (not key or not secret):
            raise BybitBusinessError(
                ret_code=-1,
                ret_msg=(
                    "Mainnet blocked: credentials missing from secret slot / "
                    "主網被阻止：secret 槽位缺憑證"
                ),
                response={"blocked": True, "guard": "mainnet_credentials"},
            )

        if is_mainnet:
            logger.warning(
                "MAINNET mode enabled — real money at risk / 主網模式已啟用 — 真金白銀"
            )
        elif not key or not secret:
            logger.warning(
                "Bybit API credentials not found — client will reject private requests / "
                "Bybit API 憑證未找到 — 私有請求將被拒"
            )

        self._env = env
        self._api_key = key
        self._api_secret = secret
        self._base_url = _BASE_URLS[env]
        self._recv_window = _DEFAULT_RECV_WINDOW_MS

        # Single shared HTTP client for connection pooling.
        # 單一共享 HTTP client 以共用連線池。
        self._client = httpx.Client(
            base_url=self._base_url,
            timeout=_DEFAULT_TIMEOUT_S,
            headers={"Content-Type": "application/json"},
        )

        # Instrument info cache: symbol -> dict spec (snake_case SymbolSpec shape).
        # 合約資訊快取：symbol -> dict（SymbolSpec 風格的 snake_case dict）。
        self._instruments: dict[str, dict[str, Any]] = {}
        self._lock = RLock()

    # ------------------------------------------------------------------
    # Lifecycle / 生命週期
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the underlying HTTP client. Safe to call multiple times.
        關閉底層 HTTP client，可重複呼叫安全。"""
        try:
            self._client.close()
        except Exception:
            pass

    def __del__(self):
        # Best-effort cleanup — don't raise in __del__.
        # Best-effort 清理 — __del__ 不 raise。
        try:
            self.close()
        except Exception:
            pass

    def __repr__(self) -> str:
        return (
            f"BybitClient(url={self._base_url}, "
            f"credentials={'yes' if self.has_credentials() else 'no'})"
        )

    # ------------------------------------------------------------------
    # Introspection / 內省
    # ------------------------------------------------------------------

    def has_credentials(self) -> bool:
        """Whether api_key AND api_secret are both non-empty.
        api_key 和 api_secret 皆非空時回 True。"""
        return bool(self._api_key) and bool(self._api_secret)

    def base_url(self) -> str:
        """Configured REST base URL. 已配置的 REST 基礎 URL。"""
        return self._base_url

    def instrument_count(self) -> int:
        """Number of cached instruments (post refresh_instruments()).
        已快取的合約數量（呼叫 refresh_instruments() 後）。"""
        with self._lock:
            return len(self._instruments)

    # ------------------------------------------------------------------
    # HMAC-SHA256 signing (Bybit V5 spec)
    # HMAC-SHA256 簽章（Bybit V5 規範）
    # ------------------------------------------------------------------

    def _timestamp_ms(self) -> str:
        """Current UTC timestamp in milliseconds as string.
        目前 UTC 毫秒時間戳（字串）。"""
        return str(int(time.time() * 1000))

    def _sign(self, timestamp: str, params: str) -> str:
        """HMAC-SHA256(api_secret, timestamp + api_key + recv_window + params).
        Bybit V5 docs: https://bybit-exchange.github.io/docs/v5/intro#signature

        Returns lowercase 64-char hex — byte-identical to Rust
        common::bybit_signer::sign_rest_v5() for the same inputs.
        返回 64 字元小寫 hex，與 Rust common::bybit_signer::sign_rest_v5() 字節一致。
        """
        sign_payload = f"{timestamp}{self._api_key}{self._recv_window}{params}"
        return hmac.new(
            self._api_secret.encode("utf-8"),
            sign_payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def _auth_headers(self, timestamp: str, signature: str) -> dict[str, str]:
        """Build Bybit V5 required auth headers.
        組 Bybit V5 必要認證 headers。"""
        return {
            "X-BAPI-API-KEY": self._api_key,
            "X-BAPI-SIGN": signature,
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-RECV-WINDOW": self._recv_window,
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------
    # Low-level HTTP methods (private endpoints require credentials)
    # 低階 HTTP 方法（私有端點需要憑證）
    # ------------------------------------------------------------------

    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        """Signed GET. Returns parsed JSON response dict.
        簽名 GET。返回解析後的 JSON response dict。"""
        if not self.has_credentials():
            raise BybitCredentialsMissing(
                "API credentials not configured / 未配置 API 憑證"
            )

        # Bybit V5 spec: signature is computed over the SORTED query string.
        # Bybit V5 規範：簽名對排序後的 query string 計算。
        sorted_items = sorted(
            [(k, _param_to_str(v)) for k, v in params.items() if v is not None],
            key=lambda kv: kv[0],
        )
        query_string = "&".join(f"{k}={v}" for k, v in sorted_items)
        timestamp = self._timestamp_ms()
        signature = self._sign(timestamp, query_string)

        try:
            r = self._client.get(
                path,
                params=sorted_items if sorted_items else None,
                headers=self._auth_headers(timestamp, signature),
            )
        except httpx.HTTPError as exc:
            raise BybitTransportError(f"HTTP error during GET {path}: {exc}") from exc

        return self._parse_json_body(path, r)

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        """Signed POST. Returns parsed JSON response dict.
        簽名 POST。返回解析後的 JSON response dict。"""
        if not self.has_credentials():
            raise BybitCredentialsMissing(
                "API credentials not configured / 未配置 API 憑證"
            )

        # Bybit V5 spec: signature is computed over the exact JSON body string
        # (no spaces — json.dumps with default separators is fine; both ends must agree).
        # Bybit V5 規範：簽名針對精確 JSON body 字串計算；兩端需字串一致。
        body_str = json.dumps(body, separators=(",", ":"), ensure_ascii=False)
        timestamp = self._timestamp_ms()
        signature = self._sign(timestamp, body_str)

        try:
            r = self._client.post(
                path,
                content=body_str,
                headers=self._auth_headers(timestamp, signature),
            )
        except httpx.HTTPError as exc:
            raise BybitTransportError(f"HTTP error during POST {path}: {exc}") from exc

        return self._parse_json_body(path, r)

    @staticmethod
    def _parse_json_body(path: str, r: httpx.Response) -> dict[str, Any]:
        """Parse Bybit V5 envelope, raising BybitBusinessError on retCode != 0.
        解析 Bybit V5 envelope，retCode != 0 時 raise BybitBusinessError。"""
        try:
            payload = r.json()
        except (json.JSONDecodeError, ValueError) as exc:
            raise BybitTransportError(
                f"Bad JSON body from {path} (HTTP {r.status_code}): {exc}"
            ) from exc

        if not isinstance(payload, dict):
            raise BybitTransportError(f"Bybit response from {path} is not a JSON object")

        ret_code = payload.get("retCode")
        # Bybit V5 ALWAYS returns retCode on success (==0). Missing → treat as error.
        # Bybit V5 任何 2xx 回應都會有 retCode；缺失時視為錯誤。
        if ret_code is None:
            raise BybitTransportError(
                f"Bybit response missing retCode ({path}): {payload!r}"
            )

        if ret_code != 0:
            raise BybitBusinessError(
                ret_code=int(ret_code),
                ret_msg=str(payload.get("retMsg") or ""),
                response=payload,
            )
        return payload

    # ------------------------------------------------------------------
    # Account / wallet — GET /v5/account/wallet-balance
    # 帳戶 / 錢包
    # ------------------------------------------------------------------

    def refresh_balance(self) -> dict[str, Any]:
        """Fetch UNIFIED wallet balance and return a WalletState-shaped dict.
        抓取 UNIFIED 錢包餘額，返回 WalletState 形狀 dict。

        Contract mirrors the pythonize-serialized Rust AccountManager::wallet_snapshot():
          {
            "account_type": "UNIFIED",
            "total_equity": f64,
            "total_wallet_balance": f64,
            "total_available_balance": f64,
            "total_unrealised_pnl": f64,
            "coins": { "USDT": {"coin": "USDT", "wallet_balance": ..., ...}, ... },
            "updated_at_ms": u64,
          }
        """
        payload = self._get("/v5/account/wallet-balance", {"accountType": "UNIFIED"})
        result = payload.get("result") or {}
        accounts = (result.get("list") or []) if isinstance(result, dict) else []
        if not accounts:
            # Empty account list — return a default-shaped WalletState.
            # 帳戶清單為空 — 返回預設形狀。
            return {
                "account_type": "UNIFIED",
                "total_equity": 0.0,
                "total_wallet_balance": 0.0,
                "total_available_balance": 0.0,
                "total_unrealised_pnl": 0.0,
                "coins": {},
                "updated_at_ms": int(time.time() * 1000),
            }

        account = accounts[0] or {}
        coins_array = account.get("coin") or []
        coins: dict[str, dict[str, Any]] = {}
        for item in coins_array:
            if not isinstance(item, dict):
                continue
            name = item.get("coin") or ""
            if not name:
                continue
            coins[name] = {
                "coin": name,
                "wallet_balance": _parse_f64(item, "walletBalance"),
                "available_to_withdraw": _parse_f64(item, "availableToWithdraw"),
                "equity": _parse_f64(item, "equity"),
                "unrealised_pnl": _parse_f64(item, "unrealisedPnl"),
                "cum_realised_pnl": _parse_f64(item, "cumRealisedPnl"),
            }

        return {
            "account_type": account.get("accountType") or "UNIFIED",
            "total_equity": _parse_f64(account, "totalEquity"),
            "total_wallet_balance": _parse_f64(account, "totalWalletBalance"),
            "total_available_balance": _parse_f64(account, "totalAvailableBalance"),
            "total_unrealised_pnl": sum(c["unrealised_pnl"] for c in coins.values()),
            "coins": coins,
            "updated_at_ms": int(time.time() * 1000),
        }

    # ------------------------------------------------------------------
    # Instruments — GET /v5/market/instruments-info (paginated)
    # 合約資訊 — 支援分頁
    # ------------------------------------------------------------------

    def refresh_instruments(self, category: str = "linear") -> int:
        """Load and cache all instrument specs for a category.
        載入並快取某品類的所有合約規格。

        Paginates through `cursor` until exhausted (Bybit V5 returns up to
        ~1000 per page; linear universe fits easily).
        透過 cursor 分頁拉完全部（Bybit V5 單頁上限約 1000 筆）。

        Returns: number of instruments loaded into cache for this call.
        返回：此次載入到快取的合約數量。
        """
        loaded = 0
        cursor: Optional[str] = None
        # Hard bound on pagination loops to prevent pathological responses.
        # 分頁硬上限，防止病理回應無限迴圈。
        for _ in range(50):
            params: dict[str, Any] = {"category": category, "limit": 1000}
            if cursor:
                params["cursor"] = cursor
            payload = self._get("/v5/market/instruments-info", params)
            result = payload.get("result") or {}
            items = (result.get("list") or []) if isinstance(result, dict) else []
            with self._lock:
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    spec = _parse_instrument_item(item)
                    if spec:
                        self._instruments[spec["symbol"]] = spec
                        loaded += 1
            cursor = result.get("nextPageCursor") if isinstance(result, dict) else None
            if not cursor:
                break
        return loaded

    def get_instrument(self, symbol: str) -> Optional[dict[str, Any]]:
        """Return cached SymbolSpec-style dict for symbol (or None).
        返回快取的 SymbolSpec 風格 dict，未快取返回 None。"""
        with self._lock:
            spec = self._instruments.get(symbol)
            return dict(spec) if spec else None

    def round_qty(self, symbol: str, qty: float) -> Optional[float]:
        """Round qty down to exchange qty_step precision. None if symbol not cached.
        按交易所 qty_step 精度地板取整，未快取返回 None。"""
        with self._lock:
            spec = self._instruments.get(symbol)
        if not spec:
            return None
        step = float(spec.get("qty_step") or 0.0)
        q = float(qty or 0.0)
        if step <= 0.0 or q <= 0.0:
            return 0.0
        floored = math.floor(q / step) * step
        decimals = int(spec.get("qty_decimals") or 0)
        # Rounding to the declared decimals avoids binary float drift.
        # 取整到宣告的小數位可避免浮點漂移。
        return round(floored, decimals) if decimals > 0 else float(floored)

    # ------------------------------------------------------------------
    # Positions — GET /v5/position/list
    # 持倉查詢
    # ------------------------------------------------------------------

    def get_positions(self, category: str = "linear") -> list[dict[str, Any]]:
        """Return raw Bybit V5 position rows (camelCase).
        返回原始 Bybit V5 持倉列表（camelCase 欄位）。

        Uses settleCoin=USDT for linear — Bybit requires symbol OR settleCoin.
        linear 使用 settleCoin=USDT，Bybit 要求 symbol 或 settleCoin 二擇一。
        """
        params: dict[str, Any] = {"category": category}
        if category == "linear":
            params["settleCoin"] = "USDT"
        payload = self._get("/v5/position/list", params)
        result = payload.get("result") or {}
        items = result.get("list") or [] if isinstance(result, dict) else []
        # Return raw Bybit dicts — Python call sites read markPrice/avgPrice/etc.
        # 返回原始 Bybit dict — call site 直接讀 markPrice/avgPrice 等 camelCase。
        return [it for it in items if isinstance(it, dict)]

    # ------------------------------------------------------------------
    # Active orders — GET /v5/order/realtime
    # 活躍訂單
    # ------------------------------------------------------------------

    def get_active_orders(
        self,
        category: str = "linear",
        symbol: Optional[str] = None,
        settle_coin: Optional[str] = "USDT",
    ) -> list[dict[str, Any]]:
        """Return active orders (Bybit V5 camelCase).
        返回活躍訂單列表（Bybit V5 camelCase）。

        If `symbol` given → filter by symbol; else use settleCoin.
        有 symbol 時按 symbol 過濾；否則以 settleCoin 查。
        """
        params: dict[str, Any] = {"category": category}
        if symbol:
            params["symbol"] = symbol
        elif settle_coin:
            params["settleCoin"] = settle_coin
        payload = self._get("/v5/order/realtime", params)
        result = payload.get("result") or {}
        items = result.get("list") or [] if isinstance(result, dict) else []
        return [it for it in items if isinstance(it, dict)]

    # ------------------------------------------------------------------
    # Cancel order — POST /v5/order/cancel
    # 取消訂單（helper for clean_restart_flatten.py）
    # ------------------------------------------------------------------

    def cancel_order(
        self,
        symbol: str,
        order_id: str,
        category: str = "linear",
    ) -> dict[str, Any]:
        """Cancel a single order by orderId. Returns dict with order_id / order_link_id.
        依 orderId 取消單一訂單，返回含 order_id / order_link_id 的 dict。

        (Note: not in the Phase 2 headline contract but used by
        clean_restart_flatten.py:108 — kept for drop-in parity.)
        """
        body = {
            "category": category,
            "symbol": symbol,
            "orderId": order_id,
        }
        payload = self._post("/v5/order/cancel", body)
        result = payload.get("result") or {}
        return _order_response_dual_shape(result if isinstance(result, dict) else {})

    # ------------------------------------------------------------------
    # Cancel all orders — POST /v5/order/cancel-all
    # 一次性取消所有掛單
    # ------------------------------------------------------------------

    def cancel_all_orders(
        self,
        category: str = "linear",
        symbol: Optional[str] = None,
        settle_coin: Optional[str] = "USDT",
        base_coin: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Cancel all active orders in scope (one HTTP call, not per-symbol).
        一次取消範圍內所有活躍掛單（單次 HTTP，**不**依 symbol 迭代）。

        Bybit V5 requires one of: symbol / baseCoin / settleCoin.
        Linear default: settleCoin=USDT — clears every USDT linear order in
        the account in a single request, regardless of symbol count. This is
        deliberately not bounded to the active strategy symbol set so a Stop
        action genuinely flattens the book.

        Bybit V5 規則：symbol / baseCoin / settleCoin 三選一。Linear 預設 settleCoin=USDT，
        單次清掉帳戶內所有 USDT linear 掛單，不受策略 symbol 數量限制 — Stop 真正清掃
        全帳戶，不只 25 個策略 symbol。

        Returns the list of cancelled orders (each has orderId + orderLinkId).
        """
        body: dict[str, Any] = {"category": category}
        if symbol:
            body["symbol"] = symbol
        elif base_coin:
            body["baseCoin"] = base_coin
        elif settle_coin:
            body["settleCoin"] = settle_coin
        else:
            raise BybitError(
                "cancel_all_orders requires one of symbol / baseCoin / settleCoin"
            )
        payload = self._post("/v5/order/cancel-all", body)
        result = payload.get("result") or {}
        items = result.get("list") or [] if isinstance(result, dict) else []
        return [
            _order_response_dual_shape(it) for it in items if isinstance(it, dict)
        ]

    # ------------------------------------------------------------------
    # Executions — GET /v5/execution/list
    # 成交記錄
    # ------------------------------------------------------------------

    def get_executions(
        self,
        category: str = "linear",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Return execution / fill records (Bybit V5 camelCase + closedPnl).
        返回成交記錄列表（Bybit V5 camelCase + closedPnl）。"""
        params: dict[str, Any] = {
            "category": category,
            "limit": int(limit),
        }
        if category == "linear":
            params["settleCoin"] = "USDT"
        payload = self._get("/v5/execution/list", params)
        result = payload.get("result") or {}
        items = result.get("list") or [] if isinstance(result, dict) else []
        return [it for it in items if isinstance(it, dict)]

    # ------------------------------------------------------------------
    # Place order — POST /v5/order/create
    # 下單
    # ------------------------------------------------------------------

    # LIVE-GATE-FALLBACK-1: place_order is used as reduce_only emergency close path
    # (clean_restart_flatten.py:124,165 + operator-initiated live close buttons).
    # LIVE-GATE-FALLBACK-1：place_order 是 reduce_only 緊急平倉路徑
    # （clean_restart_flatten.py 與 operator 觸發的 live 平倉按鈕）。
    def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        qty: float,
        category: str = "linear",
        reduce_only: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Place a new order on Bybit V5.
        在 Bybit V5 下新訂單。

        Args:
            symbol: Trading pair, e.g. "BTCUSDT".
            side: "Buy" | "Sell".
            order_type: "Market" | "Limit".
            qty: Order quantity (caller should pre-round via round_qty).
            category: "linear" | "spot" | "inverse".
            reduce_only: If True, Bybit will reject increasing a position.
            **kwargs: extension fields passed through to Bybit:
                price: float — required for Limit orders
                time_in_force: "GTC" | "IOC" | "FOK" | "PostOnly"
                order_link_id: str — client order ID for idempotency
                trigger_price / trigger_direction / take_profit / stop_loss

        Returns:
            dict with BOTH snake_case and camelCase order id keys for
            drop-in compatibility with call sites that read either form
            (Rust serialized as snake_case; Bybit raw response is camelCase):
              {"order_id": "...", "order_link_id": "...",
               "orderId": "...", "orderLinkId": "..."}
        """
        body: dict[str, Any] = {
            "category": category,
            "symbol": symbol,
            "side": side,
            "orderType": order_type,
            "qty": _format_qty(qty),
        }

        # price (Limit) / 限價
        price = kwargs.get("price")
        if price is not None:
            body["price"] = _format_price(float(price))

        # time in force — default GTC for Limit / 有效期（限價默認 GTC）
        tif = kwargs.get("time_in_force") or kwargs.get("timeInForce")
        if tif:
            body["timeInForce"] = str(tif)
        elif order_type.lower() == "limit":
            body["timeInForce"] = "GTC"

        if reduce_only:
            body["reduceOnly"] = True
        if kwargs.get("close_on_trigger") is not None:
            body["closeOnTrigger"] = bool(kwargs["close_on_trigger"])

        order_link_id = kwargs.get("order_link_id") or kwargs.get("orderLinkId")
        if order_link_id:
            body["orderLinkId"] = str(order_link_id)

        trigger_price = kwargs.get("trigger_price") or kwargs.get("triggerPrice")
        if trigger_price is not None:
            body["triggerPrice"] = _format_price(float(trigger_price))

        trigger_direction = kwargs.get("trigger_direction") or kwargs.get("triggerDirection")
        if trigger_direction is not None:
            body["triggerDirection"] = int(trigger_direction)

        take_profit = kwargs.get("take_profit") or kwargs.get("takeProfit")
        if take_profit is not None:
            body["takeProfit"] = _format_price(float(take_profit))

        stop_loss = kwargs.get("stop_loss") or kwargs.get("stopLoss")
        if stop_loss is not None:
            body["stopLoss"] = _format_price(float(stop_loss))

        payload = self._post("/v5/order/create", body)
        result = payload.get("result") or {}
        return _order_response_dual_shape(result if isinstance(result, dict) else {})


# ---------------------------------------------------------------------------
# Parsing + formatting helpers / 解析 + 格式化輔助
# ---------------------------------------------------------------------------

def _parse_f64(obj: dict[str, Any], field: str) -> float:
    """Extract a Bybit numeric-string field as float. Defaults to 0.0.
    Bybit 數值欄位常為字串；無法解析時返回 0.0。"""
    raw = obj.get(field)
    if raw is None or raw == "":
        return 0.0
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def _parse_instrument_item(item: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Parse a single instrument row into SymbolSpec-style dict.
    解析單一合約 row 為 SymbolSpec 風格 dict。

    Mirrors Rust parse_instrument_item (instrument_info.rs:276) with identical
    defaults so get_instrument() returns the same shape Python callers expect.
    """
    symbol = item.get("symbol")
    if not isinstance(symbol, str) or not symbol:
        return None

    lot_filter = item.get("lotSizeFilter")
    price_filter = item.get("priceFilter")
    if not isinstance(lot_filter, dict) or not isinstance(price_filter, dict):
        return None

    qty_step = _parse_f64(lot_filter, "qtyStep") or 0.001
    min_qty = _parse_f64(lot_filter, "minOrderQty") or 0.001
    max_qty = _parse_f64(lot_filter, "maxOrderQty") or 100.0
    tick_size = _parse_f64(price_filter, "tickSize") or 0.01
    min_price = _parse_f64(price_filter, "minPrice") or 0.01
    max_price = _parse_f64(price_filter, "maxPrice")

    min_notional = 0.0
    for container in (lot_filter, item):
        candidate = _parse_f64(container, "minNotionalValue")
        if candidate > 0.0:
            min_notional = candidate
            break

    return {
        "symbol": symbol,
        "base_currency": item.get("baseCoin") or "",
        "quote_currency": item.get("quoteCoin") or "",
        "contract_type": item.get("contractType") or "",
        "qty_step": qty_step,
        "min_qty": min_qty,
        "max_qty": max_qty,
        "tick_size": tick_size,
        "min_price": min_price,
        "max_price": max_price,
        "min_notional": min_notional,
        "qty_decimals": _decimals_from_step(qty_step),
        "price_decimals": _decimals_from_step(tick_size),
    }


def _decimals_from_step(step: float) -> int:
    """Derive decimal places from a step value (e.g. 0.001 → 3).
    從 step 值推導小數位數（如 0.001 → 3）。"""
    if step <= 0.0 or step >= 1.0:
        return 0
    # Use string representation to avoid float-binary drift.
    # 用字串表達避免浮點漂移。
    s = f"{step:.12f}".rstrip("0")
    if "." not in s:
        return 0
    return len(s.split(".", 1)[1])


def _format_qty(qty: float) -> str:
    """Format qty for Bybit V5 API (no trailing zeros, no '.').
    格式化 qty 為 Bybit V5 API 字串（無尾零、無點號）。"""
    return _format_number(qty)


def _format_price(price: float) -> str:
    """Format price for Bybit V5 API (no trailing zeros).
    格式化 price 為 Bybit V5 API 字串。"""
    return _format_number(price)


def _format_number(value: float) -> str:
    """Format a float for Bybit V5 API — 8-decimal precision, trimmed zeros.
    格式化 float 為 Bybit V5 字串 — 8 位精度、去尾零。"""
    s = f"{float(value):.8f}"
    trimmed = s.rstrip("0").rstrip(".")
    return trimmed or "0"


def _param_to_str(value: Any) -> str:
    """Normalise a query-param value to string for signing + URL encoding.
    將 query-param 值標準化為字串（供簽名 + URL encode）。"""
    if isinstance(value, bool):
        # Bybit sends lowercase "true"/"false" for bool params.
        # Bybit 對 bool 參數要求小寫 "true"/"false"。
        return "true" if value else "false"
    if isinstance(value, float):
        # Avoid scientific notation in query strings.
        # 查詢字串不使用科學記號。
        return _format_number(value)
    return str(value)


def _order_response_dual_shape(result: dict[str, Any]) -> dict[str, Any]:
    """Expose order id in BOTH snake_case (Rust PyO3 shape) and camelCase
    (Bybit native) so call sites reading either form keep working.
    以 snake_case + camelCase 雙形狀暴露訂單 id，兼容兩種呼叫端。"""
    order_id = str(result.get("orderId") or "")
    order_link_id = str(result.get("orderLinkId") or "")
    out = dict(result)
    out.setdefault("orderId", order_id)
    out.setdefault("orderLinkId", order_link_id)
    out["order_id"] = order_id
    out["order_link_id"] = order_link_id
    return out
