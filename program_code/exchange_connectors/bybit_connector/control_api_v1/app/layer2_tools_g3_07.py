from __future__ import annotations

"""
Layer 2 Toolbox Extension — G3-07 (2026-04-26)
Layer 2 工具箱擴充 —— G3-07（2026-04-26）

MODULE_NOTE (中文):
  本模組提供 Layer 2 推理迴圈兩個額外工具的純實作：
    - query_onchain        — 單一 on-chain / 衍生品市場指標
    - check_derivatives    — Bybit V5 衍生品多指標快照（單次往返）

  為什麼分檔（不寫進 layer2_tools.py）：
    - layer2_tools.py 加入 schema + handler 後達 1496 行（> §九 1200 硬上限）。
    - 抽出 G3-07 區塊到 sibling 後 layer2_tools.py 回到合規行數。
    - schema entries / handler dict registration 仍留在 layer2_tools.py，
      sibling 只負責「fetch 與解析」純函式 + dataclass↔dict 轉換。

  硬邊界：
    - 兩工具預設關閉（OPENCLAW_LAYER2_TOOL_*_ENABLED 必設 1 / true / yes / on）
    - HTTP 超時預設 5 秒（OPENCLAW_LAYER2_TOOL_HTTP_TIMEOUT_SEC 可覆蓋）
    - 任何 transport / non-200 / parse 失敗 → return result with error 字串，
      *絕不 raise* —— 防止 L2 推理鏈被工具層異常中斷
    - Bybit V5 公開端點（無需簽名），demo / testnet / mainnet 皆安全

MODULE_NOTE (English):
  Pure-function implementation of two extra Layer 2 reasoning tools:
    - query_onchain       — single on-chain / derivatives metric
    - check_derivatives   — Bybit V5 derivatives multi-metric snapshot (1 round-trip)

  Why split out of layer2_tools.py: that file would exceed §九 1200-line hard
  cap once schema + handler were added; extracting the G3-07 block keeps both
  files compliant. Schema entries + handler dict registration remain in
  layer2_tools.py; this sibling only carries fetch / parse pure functions and
  dataclass-to-dict converters.

  Hard boundaries:
    - Both tools DEFAULT-OFF (env-gate must be set to 1 / true / yes / on)
    - HTTP timeout defaults to 5s (OPENCLAW_LAYER2_TOOL_HTTP_TIMEOUT_SEC)
    - Any transport / non-200 / parse failure returns a result carrying an
      error string, *never raises* — prevents tool-layer exceptions from
      breaking the L2 reasoning loop
    - Bybit V5 public endpoints (no auth) — safe under demo / testnet / mainnet
"""

import logging
import os
import time
from pathlib import Path
from typing import Any

from .layer2_types import (
    DERIV_METRIC_FUNDING,
    DERIV_METRIC_INDEX_PRICE,
    DERIV_METRIC_MARK_PRICE,
    DERIV_METRIC_NEXT_FUNDING_TS,
    DERIV_METRIC_OI_24H_CHANGE_PCT,
    DERIV_METRIC_VALID,
    ONCHAIN_METRIC_FUNDING_RATE,
    ONCHAIN_METRIC_LIQUIDATIONS_24H,
    ONCHAIN_METRIC_OPEN_INTEREST,
    ONCHAIN_METRIC_VALID,
    DerivativesResult,
    OnchainResult,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────
# Env gate / 環境變數開關
# ─────────────────────────────────────────────────────────

ENV_QUERY_ONCHAIN_ENABLED = "OPENCLAW_LAYER2_TOOL_QUERY_ONCHAIN_ENABLED"
ENV_CHECK_DERIVATIVES_ENABLED = "OPENCLAW_LAYER2_TOOL_CHECK_DERIVATIVES_ENABLED"
ENV_HTTP_TIMEOUT_SEC = "OPENCLAW_LAYER2_TOOL_HTTP_TIMEOUT_SEC"
ENV_BYBIT_PUBLIC_BASE_URL = "OPENCLAW_BYBIT_PUBLIC_BASE_URL"
ENV_BYBIT_ENV = "OPENCLAW_BYBIT_ENV"
DEFAULT_HTTP_TIMEOUT_SEC = 5.0
DEFAULT_TOOL_DISABLED_ERROR = "tool disabled by env"
DEFAULT_DATA_UNAVAILABLE_ERROR = "data unavailable"

# Bybit V5 public endpoint roots (no auth required for tickers / open-interest).
# Bybit V5 公開端點根（tickers / open-interest 不需簽名）。
BYBIT_PUBLIC_BASE_URLS: dict[str, str] = {
    "demo": "https://api-demo.bybit.com",
    "testnet": "https://api-testnet.bybit.com",
    "live": "https://api.bybit.com",
    "live_demo": "https://api-demo.bybit.com",
    "mainnet": "https://api.bybit.com",
}


def _live_secret_slot_dir() -> Path:
    """
    Resolve the live Bybit secret slot directory.
    解析 live Bybit secret slot 目錄。

    Mirrors the production file layout used by settings/live auth:
    $OPENCLAW_SECRETS_DIR/live first, then $OPENCLAW_SECRETS_ROOT, then the
    default ~/BybitOpenClaw/secrets/secret_files/bybit/live path.
    """
    base_env = os.environ.get("OPENCLAW_SECRETS_DIR")
    if base_env:
        return Path(base_env) / "live"
    root_env = os.environ.get("OPENCLAW_SECRETS_ROOT")
    if root_env:
        return Path(root_env) / "secret_files" / "bybit" / "live"
    return Path.home() / "BybitOpenClaw" / "secrets" / "secret_files" / "bybit" / "live"


def _file_based_bybit_env() -> str | None:
    """
    Read the production `live/bybit_endpoint` metadata when available.
    可用時讀取 production `live/bybit_endpoint` metadata。

    The file stores endpoint labels written by the settings API. This helper is
    intentionally non-raising and returns None when the file is absent or
    unknown so public Layer 2 tools can keep their safe demo fallback.
    """
    try:
        raw = (_live_secret_slot_dir() / "bybit_endpoint").read_text(
            encoding="utf-8",
        ).strip().lower()
    except (FileNotFoundError, PermissionError, OSError):
        return None
    if raw == "demo":
        return "live_demo"
    if raw in {"mainnet", "live"}:
        return "mainnet"
    if raw == "testnet":
        return "testnet"
    return None


def is_tool_enabled(env_name: str) -> bool:
    """
    Check if a Layer 2 tool env-gate flag is enabled.
    檢查指定 Layer 2 工具的環境變數開關是否啟用。

    True iff env value (after lower/strip) ∈ {"1", "true", "yes", "on"}.
    任何其他值（含未設定 / 空字串）一律當作關閉，符合 fail-closed 預設。
    """
    raw = os.getenv(env_name, "")
    return raw.strip().lower() in ("1", "true", "yes", "on")


def http_timeout() -> float:
    """
    HTTP timeout in seconds for G3-07 tools (env-overridable).
    G3-07 工具的 HTTP 超時秒數（環境變數可覆蓋）。

    Bad numeric values silently fall back to 5.0s (避免 operator typo
    導致 0s timeout 立刻失敗）.
    """
    raw = os.getenv(ENV_HTTP_TIMEOUT_SEC, "")
    if not raw:
        return DEFAULT_HTTP_TIMEOUT_SEC
    try:
        v = float(raw)
        if v <= 0:
            return DEFAULT_HTTP_TIMEOUT_SEC
        return v
    except ValueError:
        logger.warning(
            "Layer2 tool HTTP timeout env %s=%r is not a number; using %.1fs / "
            "環境變數格式錯誤，使用預設值",
            ENV_HTTP_TIMEOUT_SEC,
            raw,
            DEFAULT_HTTP_TIMEOUT_SEC,
        )
        return DEFAULT_HTTP_TIMEOUT_SEC


def bybit_public_base_url() -> str:
    """
    Resolve the Bybit public REST base URL.
    解析 Bybit 公開 REST base URL。

    Priority:
      1. OPENCLAW_BYBIT_PUBLIC_BASE_URL exact URL override
      2. OPENCLAW_BYBIT_ENV legacy/test override
      3. production file-based live/bybit_endpoint metadata
      4. safe demo fallback
    """
    explicit_url = os.getenv(ENV_BYBIT_PUBLIC_BASE_URL, "").strip()
    if explicit_url:
        return explicit_url.rstrip("/")

    explicit_env = os.getenv(ENV_BYBIT_ENV, "").strip().lower()
    if explicit_env:
        return BYBIT_PUBLIC_BASE_URLS.get(explicit_env, BYBIT_PUBLIC_BASE_URLS["demo"])

    file_env = _file_based_bybit_env()
    if file_env:
        return BYBIT_PUBLIC_BASE_URLS.get(file_env, BYBIT_PUBLIC_BASE_URLS["demo"])

    return BYBIT_PUBLIC_BASE_URLS["demo"]


# ─────────────────────────────────────────────────────────
# dataclass <-> dict converters
# ─────────────────────────────────────────────────────────

def onchain_to_dict(r: OnchainResult) -> dict[str, Any]:
    """Serialize OnchainResult to JSON-safe dict / 序列化為 JSON 安全 dict"""
    return {
        "symbol": r.symbol,
        "metric": r.metric,
        "value": r.value,
        "timestamp_ms": r.timestamp_ms,
        "data_source": r.data_source,
        "freshness_secs": r.freshness_secs,
        "error": r.error,
        "is_simulated": r.is_simulated,
    }


def derivatives_to_dict(r: DerivativesResult) -> dict[str, Any]:
    """Serialize DerivativesResult to JSON-safe dict / 序列化為 JSON 安全 dict"""
    return {
        "symbol": r.symbol,
        "metrics": dict(r.metrics),
        "timestamp_ms": r.timestamp_ms,
        "data_source": r.data_source,
        "error": r.error,
        "error_per_metric": dict(r.error_per_metric),
        "is_simulated": r.is_simulated,
    }


# ─────────────────────────────────────────────────────────
# query_onchain — single metric, fail-closed
# ─────────────────────────────────────────────────────────

async def query_onchain(args: dict[str, Any]) -> dict[str, Any]:
    """
    Fetch a single on-chain / derivatives metric for a symbol.
    為單一 symbol 取得單一 on-chain / 衍生品指標。

    Why: gives the L2 reasoning loop one-shot access to common funding /
    OI / liquidation signals without bloating get_market_state. Bybit V5
    public endpoints used (no auth) so this is safe under demo / testnet
    / mainnet without credential leakage risk.
    為什麼：讓 L2 推理迴圈不需擴張 get_market_state 即可一次性取得常用的
    資金費率 / 未平倉 / 強平訊號。使用 Bybit V5 公開端點（無需簽名），
    在 demo / testnet / mainnet 下都不會洩漏憑證風險。

    Fail-closed contract / 失敗收縮契約：
    - env-disabled        → OnchainResult(value=None, error="tool disabled by env")
    - missing args        → OnchainResult(value=None, error="symbol/metric required")
    - unsupported metric  → OnchainResult(value=None, error="metric not supported: ...")
    - HTTP / parse error  → OnchainResult(value=None, error="data unavailable: ...")
    """
    symbol = (args.get("symbol") or "").strip()
    metric = (args.get("metric") or "").strip()

    # Env-gate FIRST — even before arg validation, so disabled tools never
    # leak input echoes or partial diagnostics.
    # 先檢查 env-gate — 即使 args 缺失也統一回 disabled 訊息，
    # 避免關閉時仍洩漏輸入回顯。
    if not is_tool_enabled(ENV_QUERY_ONCHAIN_ENABLED):
        return onchain_to_dict(OnchainResult(
            symbol=symbol, metric=metric,
            error=DEFAULT_TOOL_DISABLED_ERROR,
        ))

    if not symbol or not metric:
        return onchain_to_dict(OnchainResult(
            symbol=symbol, metric=metric,
            error="symbol and metric are required",
        ))

    if metric not in ONCHAIN_METRIC_VALID:
        return onchain_to_dict(OnchainResult(
            symbol=symbol, metric=metric,
            error=(
                f"metric not supported: {metric!r} "
                f"(valid: {sorted(ONCHAIN_METRIC_VALID)})"
            ),
        ))

    result = await _fetch_onchain_metric(symbol, metric)
    return onchain_to_dict(result)


async def _fetch_onchain_metric(
    symbol: str, metric: str,
) -> OnchainResult:
    """
    HTTP fetch + parse single on-chain metric. Pure helper.
    HTTP 取資料並解析單一 on-chain 指標的純輔助函式。

    Why split out: keeps `query_onchain` focused on validation / env-gate;
    this helper is unit-testable in isolation by patching httpx.AsyncClient.
    為什麼拆出：讓 `query_onchain` 專注在 validate / env-gate；
    本 helper 透過 patch httpx.AsyncClient 即可獨立單測。
    """
    try:
        import httpx
    except ImportError:
        return OnchainResult(
            symbol=symbol, metric=metric,
            error="httpx not installed",
        )

    base = bybit_public_base_url()
    timeout = http_timeout()

    # Endpoint dispatch table.
    # 端點派發表。
    if metric == ONCHAIN_METRIC_FUNDING_RATE:
        url = f"{base}/v5/market/tickers"
        params = {"category": "linear", "symbol": symbol}
        extract_key = "fundingRate"
    elif metric == ONCHAIN_METRIC_OPEN_INTEREST:
        url = f"{base}/v5/market/open-interest"
        params = {
            "category": "linear",
            "symbol": symbol,
            "intervalTime": "5min",
            "limit": 1,
        }
        extract_key = "openInterest"
    elif metric == ONCHAIN_METRIC_LIQUIDATIONS_24H:
        # Bybit V5 doesn't expose direct 24h liquidations volume in a
        # public endpoint; surface as data-unavailable so the L2 loop
        # knows to fall back rather than fabricating a value.
        # Bybit V5 公開端點未直接暴露 24h 強平總量；明確回 data-unavailable
        # 讓 L2 迴圈降級，避免捏造數值。
        return OnchainResult(
            symbol=symbol, metric=metric,
            data_source="bybit_v5_public",
            error=(
                f"{DEFAULT_DATA_UNAVAILABLE_ERROR}: "
                "liquidations_24h has no public V5 endpoint"
            ),
        )
    else:
        # Unreachable: caller has already whitelist-checked.
        # 不可達：caller 已白名單檢查。
        return OnchainResult(
            symbol=symbol, metric=metric,
            error=f"metric not supported: {metric!r}",
        )

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, params=params)
            if resp.status_code != 200:
                return OnchainResult(
                    symbol=symbol, metric=metric,
                    data_source="bybit_v5_public",
                    error=(
                        f"{DEFAULT_DATA_UNAVAILABLE_ERROR}: "
                        f"HTTP {resp.status_code}"
                    ),
                )
            data = resp.json()
    except Exception as e:
        return OnchainResult(
            symbol=symbol, metric=metric,
            data_source="bybit_v5_public",
            error=f"{DEFAULT_DATA_UNAVAILABLE_ERROR}: {str(e)[:200]}",
        )

    # Parse Bybit V5 envelope: { retCode, result: { list: [ ... ] } }.
    # 解析 Bybit V5 信封：retCode + result.list 陣列。
    if not isinstance(data, dict) or data.get("retCode") != 0:
        ret_msg = data.get("retMsg", "unknown") if isinstance(data, dict) else "non-dict"
        return OnchainResult(
            symbol=symbol, metric=metric,
            data_source="bybit_v5_public",
            error=f"{DEFAULT_DATA_UNAVAILABLE_ERROR}: retCode!=0 ({ret_msg})",
        )

    rows = (
        data.get("result", {}).get("list", [])
        if isinstance(data.get("result"), dict) else []
    )
    if not rows:
        return OnchainResult(
            symbol=symbol, metric=metric,
            data_source="bybit_v5_public",
            error=f"{DEFAULT_DATA_UNAVAILABLE_ERROR}: empty result list",
        )

    first = rows[0]
    raw = first.get(extract_key, "")
    try:
        value = float(raw) if raw not in (None, "") else None
    except (TypeError, ValueError):
        value = None

    if value is None:
        return OnchainResult(
            symbol=symbol, metric=metric,
            data_source="bybit_v5_public",
            error=f"{DEFAULT_DATA_UNAVAILABLE_ERROR}: missing {extract_key!r} field",
        )

    # Extract source timestamp (best-effort).
    # 提取資料源時戳（盡力而為）。
    ts_ms: int | None = None
    for ts_key in ("timestamp", "ts", "updatedTime", "createdTime"):
        ts_raw = first.get(ts_key) or data.get("time")
        if ts_raw:
            try:
                ts_ms = int(ts_raw)
                break
            except (TypeError, ValueError):
                continue

    freshness_secs: int | None = None
    if ts_ms is not None:
        now_ms = int(time.time() * 1000)
        delta_ms = now_ms - ts_ms
        if delta_ms >= 0:
            freshness_secs = delta_ms // 1000

    return OnchainResult(
        symbol=symbol, metric=metric,
        value=value,
        timestamp_ms=ts_ms,
        data_source="bybit_v5_public",
        freshness_secs=freshness_secs,
    )


# ─────────────────────────────────────────────────────────
# check_derivatives — multi-metric snapshot, fail-closed per metric
# ─────────────────────────────────────────────────────────

async def check_derivatives(args: dict[str, Any]) -> dict[str, Any]:
    """
    Fetch multiple Bybit V5 derivatives market metrics in one round-trip.
    透過單次往返取得多項 Bybit V5 衍生品市場指標。

    Why: avoids N×latency for L2 sessions wanting a comprehensive
    snapshot. Single GET /v5/market/tickers returns mark_price /
    index_price / fundingRate / nextFundingTime / openInterest / etc.
    為什麼：避免 L2 推理為取得完整快照付出 N 倍延遲。單次 GET
    /v5/market/tickers 即包含標記價 / 指數價 / 資金費率 / 下次費率時間
    / 未平倉量等所有欄位。

    Fail-closed contract / 失敗收縮契約：
    - env-disabled         → DerivativesResult(error="tool disabled by env")
    - missing symbol       → DerivativesResult(error="symbol required")
    - HTTP / parse error   → DerivativesResult(error="data unavailable: ...")
    - per-metric extract   → metrics[name]=None + error_per_metric[name]=reason
    """
    symbol = (args.get("symbol") or "").strip()

    if not is_tool_enabled(ENV_CHECK_DERIVATIVES_ENABLED):
        return derivatives_to_dict(DerivativesResult(
            symbol=symbol, error=DEFAULT_TOOL_DISABLED_ERROR,
        ))

    if not symbol:
        return derivatives_to_dict(DerivativesResult(
            symbol=symbol, error="symbol is required",
        ))

    # Default to all supported metrics if caller omits.
    # caller 未指定時預設取全部支援的指標。
    raw_metrics = args.get("metrics") or list(sorted(DERIV_METRIC_VALID))
    if not isinstance(raw_metrics, list):
        return derivatives_to_dict(DerivativesResult(
            symbol=symbol, error="metrics must be a list",
        ))

    requested: list[str] = []
    invalid_per_metric: dict[str, str] = {}
    for m in raw_metrics:
        if not isinstance(m, str):
            continue
        if m in DERIV_METRIC_VALID:
            requested.append(m)
        else:
            invalid_per_metric[m] = (
                f"metric not supported: {m!r} "
                f"(valid: {sorted(DERIV_METRIC_VALID)})"
            )

    if not requested:
        res = DerivativesResult(
            symbol=symbol,
            error="no valid metrics requested",
            error_per_metric=invalid_per_metric,
        )
        return derivatives_to_dict(res)

    result = await _fetch_derivatives_snapshot(symbol, requested)
    # Merge invalid-metric errors back so caller sees both kinds.
    # 把 invalid metric 錯誤合併回去，讓 caller 兩類錯誤都看得到。
    for k, v in invalid_per_metric.items():
        result.error_per_metric.setdefault(k, v)
    return derivatives_to_dict(result)


async def _fetch_derivatives_snapshot(
    symbol: str, requested: list[str],
) -> DerivativesResult:
    """
    HTTP fetch + parse multi-metric derivatives snapshot.
    HTTP 取資料並解析多項衍生品指標快照。

    Single round-trip via GET /v5/market/tickers. oi_24h_change_pct is
    surfaced as data-unavailable per-metric (no public V5 endpoint for
    24h OI delta — keep honest rather than fabricate).
    透過單次 GET /v5/market/tickers 取主要欄位；oi_24h_change_pct
    Bybit 公開 V5 無直接欄位，誠實標記不可得。
    """
    try:
        import httpx
    except ImportError:
        return DerivativesResult(
            symbol=symbol, error="httpx not installed",
            error_per_metric={m: "httpx not installed" for m in requested},
        )

    base = bybit_public_base_url()
    timeout = http_timeout()
    url = f"{base}/v5/market/tickers"
    params = {"category": "linear", "symbol": symbol}

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, params=params)
            if resp.status_code != 200:
                err = (
                    f"{DEFAULT_DATA_UNAVAILABLE_ERROR}: "
                    f"HTTP {resp.status_code}"
                )
                return DerivativesResult(
                    symbol=symbol, error=err,
                    data_source="bybit_v5_public",
                    error_per_metric={m: err for m in requested},
                )
            data = resp.json()
    except Exception as e:
        err = f"{DEFAULT_DATA_UNAVAILABLE_ERROR}: {str(e)[:200]}"
        return DerivativesResult(
            symbol=symbol, error=err,
            data_source="bybit_v5_public",
            error_per_metric={m: err for m in requested},
        )

    if not isinstance(data, dict) or data.get("retCode") != 0:
        ret_msg = data.get("retMsg", "unknown") if isinstance(data, dict) else "non-dict"
        err = f"{DEFAULT_DATA_UNAVAILABLE_ERROR}: retCode!=0 ({ret_msg})"
        return DerivativesResult(
            symbol=symbol, error=err,
            data_source="bybit_v5_public",
            error_per_metric={m: err for m in requested},
        )

    rows = (
        data.get("result", {}).get("list", [])
        if isinstance(data.get("result"), dict) else []
    )
    if not rows:
        err = f"{DEFAULT_DATA_UNAVAILABLE_ERROR}: empty result list"
        return DerivativesResult(
            symbol=symbol, error=err,
            data_source="bybit_v5_public",
            error_per_metric={m: err for m in requested},
        )

    first = rows[0]
    metrics: dict[str, float | None] = {}
    error_per_metric: dict[str, str] = {}

    # Bybit V5 ticker JSON field map.
    # Bybit V5 ticker JSON 欄位映射。
    bybit_field_map = {
        DERIV_METRIC_MARK_PRICE: "markPrice",
        DERIV_METRIC_INDEX_PRICE: "indexPrice",
        DERIV_METRIC_FUNDING: "fundingRate",
        DERIV_METRIC_NEXT_FUNDING_TS: "nextFundingTime",
        # oi_24h_change_pct synthesized below from openInterest
        # vs price24hPcnt; not a 1:1 field.
    }

    for m in requested:
        if m == DERIV_METRIC_OI_24H_CHANGE_PCT:
            # Bybit V5 ticker exposes 'openInterestValue' but NOT a 24h
            # OI delta percentage; mark None with explicit reason.
            # Bybit V5 ticker 暴露 openInterestValue 但無 24h OI 變化率；
            # 標記 None 並寫明原因。
            metrics[m] = None
            error_per_metric[m] = (
                f"{DEFAULT_DATA_UNAVAILABLE_ERROR}: "
                "oi_24h_change_pct requires open-interest history "
                "endpoint not yet wired"
            )
            continue

        field_name = bybit_field_map.get(m)
        if field_name is None:
            metrics[m] = None
            error_per_metric[m] = f"no field map for metric: {m!r}"
            continue

        raw = first.get(field_name, "")
        try:
            metrics[m] = float(raw) if raw not in (None, "") else None
        except (TypeError, ValueError):
            metrics[m] = None
            error_per_metric[m] = f"non-numeric value: {raw!r}"

        if metrics[m] is None and m not in error_per_metric:
            error_per_metric[m] = (
                f"{DEFAULT_DATA_UNAVAILABLE_ERROR}: "
                f"missing {field_name!r} field"
            )

    # Server-side timestamp for whole snapshot.
    # 整個快照的 server-side 時戳。
    ts_ms: int | None = None
    try:
        ts_ms = int(data.get("time") or 0) or None
    except (TypeError, ValueError):
        ts_ms = None

    return DerivativesResult(
        symbol=symbol,
        metrics=metrics,
        timestamp_ms=ts_ms,
        data_source="bybit_v5_public",
        error_per_metric=error_per_metric,
    )


__all__ = [
    "ENV_QUERY_ONCHAIN_ENABLED",
    "ENV_CHECK_DERIVATIVES_ENABLED",
    "ENV_HTTP_TIMEOUT_SEC",
    "ENV_BYBIT_PUBLIC_BASE_URL",
    "ENV_BYBIT_ENV",
    "DEFAULT_HTTP_TIMEOUT_SEC",
    "DEFAULT_TOOL_DISABLED_ERROR",
    "DEFAULT_DATA_UNAVAILABLE_ERROR",
    "BYBIT_PUBLIC_BASE_URLS",
    "is_tool_enabled",
    "http_timeout",
    "bybit_public_base_url",
    "onchain_to_dict",
    "derivatives_to_dict",
    "query_onchain",
    "check_derivatives",
]
