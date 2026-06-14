"""Tardis 免費 first-day-of-month CSV.gz 下載（無 key，PIT append-only）。

MODULE_NOTE:
  模塊用途：下載 Tardis 免費數據集（每月 1 號全天 normalized CSV.gz，無需 API
    key）——Bybit linear USDT perp 的 incremental_book_L2 / trades / liquidations
    → 落到 run dir/raw/（PIT append-only，run dir 已存在即 raise，禁回填）。
  依賴：僅 Python 標準庫（urllib / gzip）。零生產模組 import、零 auth、零 PG。
  硬邊界（mirror deribit_vol_axis collector）：
    - host allowlist 只含 datasets.tardis.dev（唯讀公開數據集 base）：結構性排除
      任何 private / 下單 / auth endpoint。
    - 默認 urlopen 禁 redirect（30x 跟跳會把出口引去 allowlist 外 host）：30x
      一律升 HTTPError 且不重試。
    - Tardis 免費 tier 結構性限制：只有「每月 1 號」單日。本模塊強制 day==1，
      否則 raise（防誤抓非免費日 → 402/付費路徑，違原則 14 零外部成本）。
    - artifact root 禁硬編碼：${OPENCLAW_DATA_DIR:-/tmp/openclaw}/ 推導。
"""

from __future__ import annotations

import datetime as dt
import logging
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

from . import TARDIS_DATASETS_HOST, TARDIS_EXCHANGE

logger = logging.getLogger(__name__)

# Tardis 免費數據集 base（唯讀公開；URL 形如
# https://datasets.tardis.dev/v1/<exchange>/<channel>/<YYYY>/<MM>/<DD>/<SYMBOL>.csv.gz）。
TARDIS_DATASETS_BASE = f"https://{TARDIS_DATASETS_HOST}/v1"

DEFAULT_TIMEOUT_S = 60.0
DEFAULT_RETRIES = 3
DEFAULT_BACKOFF_BASE_S = 1.5


class TardisFetchError(Exception):
    """下載在 retry 耗盡後仍失敗（caller 決定 fail-soft / BLOCKED）。"""


class _RedirectRefusedHandler(urllib.request.HTTPRedirectHandler):
    """任何 30x redirect 升為 HTTPError（allowlist 防不了跟跳，mirror deribit_vol_axis）。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D102
        # newurl 截斷 200：Location 是外部可控文本，原樣嵌 error 會灌爆 cron log。
        raise urllib.error.HTTPError(
            req.full_url, code, f"redirect refused (-> {str(newurl)[:200]!r})", headers, fp,
        )


_NO_REDIRECT_OPENER = urllib.request.build_opener(_RedirectRefusedHandler())


def _assert_host_allowed(url: str) -> None:
    """url host 必須恰為 datasets.tardis.dev，否則 raise（host allowlist 執行點）。"""
    from urllib.parse import urlparse

    host = (urlparse(url).hostname or "").lower()
    if host != TARDIS_DATASETS_HOST:
        raise TardisFetchError(f"host 不在 allowlist：{host!r}（只允許 {TARDIS_DATASETS_HOST}）")


def build_url(channel: str, day: dt.date, symbol: str, exchange: str = TARDIS_EXCHANGE) -> str:
    """構造 Tardis 免費數據集 URL。

    不變量：Tardis 免費 tier 只開放每月 1 號 → day.day 必須 == 1，否則 raise
    （防誤抓非免費日落入 402/付費，違原則 14）。
    """
    if day.day != 1:
        raise TardisFetchError(
            f"Tardis 免費 tier 僅每月 1 號可下載，收到 day={day.isoformat()}（day != 1）"
        )
    return (
        f"{TARDIS_DATASETS_BASE}/{exchange}/{channel}/"
        f"{day.year:04d}/{day.month:02d}/{day.day:02d}/{symbol}.csv.gz"
    )


def _http_get_bytes(
    url: str,
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    retries: int = DEFAULT_RETRIES,
    backoff_base_s: float = DEFAULT_BACKOFF_BASE_S,
) -> bytes:
    """禁 redirect + 指數 backoff retry 的 GET-bytes。404 不重試（免費日不存在）。"""
    _assert_host_allowed(url)
    last_exc: Optional[Exception] = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "openclaw-research/0.1"})
            with _NO_REDIRECT_OPENER.open(req, timeout=timeout_s) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            # 404 = 該 symbol/日無數據（免費日該 channel 缺檔）：不重試，直接升。
            if exc.code == 404:
                raise TardisFetchError(f"404 not found: {url}") from exc
            last_exc = exc
        except Exception as exc:  # noqa: BLE001 —— 網路類錯一律退避重試。
            last_exc = exc
        if attempt < retries - 1:
            sleep_s = backoff_base_s * (2 ** attempt)
            logger.warning("Tardis GET 失敗 attempt=%d url=%s 重試前等待 %.1fs", attempt, url, sleep_s)
            time.sleep(sleep_s)
    raise TardisFetchError(f"GET 失敗（retry 耗盡）：{url}：{last_exc!r}")


def fetch_to_raw(
    raw_dir: Path,
    *,
    channel: str,
    day: dt.date,
    symbol: str,
    exchange: str = TARDIS_EXCHANGE,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    retries: int = DEFAULT_RETRIES,
    overwrite: bool = False,
) -> Path:
    """下載單一 channel/day/symbol 的 CSV.gz 到 raw_dir，回落地路徑。

    PIT append-only 不變量：目標檔已存在且 overwrite=False → raise（不覆寫舊
    snapshot）。raw_dir 由 caller 在 append-only run dir 下建立。
    """
    raw_dir.mkdir(parents=True, exist_ok=True)
    out_path = raw_dir / f"{exchange}_{channel}_{day.isoformat()}_{symbol}.csv.gz"
    if out_path.exists() and not overwrite:
        raise TardisFetchError(
            f"目標已存在（PIT append-only 禁覆寫）：{out_path}（換 run_id 或設 overwrite）"
        )
    url = build_url(channel, day, symbol, exchange=exchange)
    body = _http_get_bytes(url, timeout_s=timeout_s, retries=retries)
    # 原子寫：.tmp + replace，下載中斷不留半檔（mirror deribit_vol_axis parquet 教訓）。
    tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
    tmp_path.write_bytes(body)
    tmp_path.replace(out_path)
    logger.info("Tardis 下載完成 channel=%s symbol=%s bytes=%d -> %s", channel, symbol, len(body), out_path)
    return out_path


def fetch_symbol_month(
    raw_dir: Path,
    *,
    symbol: str,
    day: dt.date,
    channels: tuple[str, ...],
    exchange: str = TARDIS_EXCHANGE,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    retries: int = DEFAULT_RETRIES,
    overwrite: bool = False,
) -> dict[str, object]:
    """下載某 symbol 在某免費日的多 channel；回逐 channel 結果（fail-soft per channel）。

    liquidations channel 在 Bybit 自 2020-12-18 起才有 → 缺檔（404）不阻斷整批，
    標 error 繼續（其它 channel 仍可用）。incremental_book_L2 / trades 缺檔則是
    硬失敗信號（無法 replay）。
    """
    result: dict[str, object] = {"symbol": symbol, "day": day.isoformat(), "files": {}, "errors": []}
    files: dict[str, str] = {}
    errors: list[str] = []
    for ch in channels:
        try:
            p = fetch_to_raw(
                raw_dir, channel=ch, day=day, symbol=symbol,
                exchange=exchange, timeout_s=timeout_s, retries=retries, overwrite=overwrite,
            )
            files[ch] = str(p)
        except TardisFetchError as exc:
            errors.append(f"{ch}:{exc}")
            logger.warning("channel 下載失敗 channel=%s symbol=%s：%s", ch, symbol, exc)
    result["files"] = files
    result["errors"] = errors
    return result
