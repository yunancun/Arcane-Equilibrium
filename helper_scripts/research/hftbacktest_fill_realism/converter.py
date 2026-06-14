"""Tardis CSV.gz → hftbacktest 8-field event npz 轉換。

MODULE_NOTE:
  模塊用途：把 raw/ 下的 Tardis incremental_book_L2 + trades CSV.gz 轉成
    hftbacktest 原生 8-field event array（ev/exch_ts/local_ts/px/qty/order_id/
    ival/fval），落 hbt/<symbol>_<day>.npz。**首選官方
    hftbacktest.data.utils.tardis.convert**（vendor-supported，正確處理 exch_ts/
    local_ts 雙時戳 + queue position 雙扣防護），降級 hftbacktest 不可用時 raise
    導向 NON-HARVESTABLE/BLOCKED（不自製近似 converter 偽造 fill）。
  依賴：numpy + hftbacktest（2.x）。
  leak hot-spot（承 sub-bar event timing 教訓）：
    - converter 不做任何時序重排「向前看」：官方 convert 用 Tardis 自帶 exch_ts
      （exchange 發送時戳）與 local_ts（採集端收到時戳），feed latency = local_ts
      − exch_ts 必為正，hftbacktest 重放即以此雙時戳保證「本地先看到才能下單」。
    - trades 檔必須在 incremental_book 檔之前傳入 convert（官方契約）：若 depth
      message 先處理，queue position 會被扣兩次（depth 已扣成交量、隨後 trade
      又扣）→ 高估 fill 率。本模塊 build_input_files 強制此順序。
"""

from __future__ import annotations

import contextlib
import logging
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class ConverterUnavailableError(RuntimeError):
    """hftbacktest 官方 tardis converter 不可用（caller 應導向 BLOCKED）。"""


def build_input_files(raw_files: dict[str, str]) -> list[str]:
    """依官方契約把 raw channel 檔排序成 convert 的 input_files。

    不變量：trades 必須在 incremental_book_L2 之前（防 queue position 雙扣）。
    缺任一必需 channel → raise（無法 replay 的硬信號）。
    """
    book = raw_files.get("incremental_book_L2")
    trades = raw_files.get("trades")
    if not book:
        raise ConverterUnavailableError("缺 incremental_book_L2 raw 檔，無法構造 hftbacktest 輸入")
    if not trades:
        raise ConverterUnavailableError("缺 trades raw 檔，無法構造 hftbacktest 輸入")
    # trades 在前、depth 在後（官方 docstring 明示的 queue 雙扣防護順序）。
    return [trades, book]


def convert_symbol(
    raw_files: dict[str, str],
    *,
    out_npz: Path,
    base_latency: float = 0.0,
    buffer_size: int = 100_000_000,
    ss_buffer_size: int = 1_000_000,
) -> dict[str, object]:
    """用官方 hftbacktest tardis converter 把 raw CSV.gz → 8-field npz。

    回 {"npz": <path>, "n_events": int}。hftbacktest 不可用 → ConverterUnavailableError。
    """
    try:
        from hftbacktest.data.utils import tardis  # 延遲 import：Mac dev 需先 pip install。
    except Exception as exc:  # noqa: BLE001 —— 套件缺席導向 BLOCKED，不自製近似。
        raise ConverterUnavailableError(
            f"hftbacktest 官方 tardis converter 不可用：{exc!r}（pip install hftbacktest）"
        ) from exc

    input_files = build_input_files(raw_files)
    out_npz.parent.mkdir(parents=True, exist_ok=True)
    # output_filename 提供時 convert 直接落 npz（內部 np.savez_compressed data=array）。
    # 官方 convert 把進度（Reading/Correcting/Saving）print 到 stdout，會污染 CLI 的
    # JSON 摘要輸出 → 重導到 stderr，保持 stdout 純 JSON（cron/下游可直接 parse）。
    with contextlib.redirect_stdout(sys.stderr):
        data = tardis.convert(
            input_files,
            output_filename=str(out_npz),
            buffer_size=buffer_size,
            ss_buffer_size=ss_buffer_size,
            base_latency=base_latency,
        )
    n_events = int(data.shape[0]) if hasattr(data, "shape") else 0
    logger.info("converter 完成 n_events=%d -> %s", n_events, out_npz)
    return {"npz": str(out_npz), "n_events": n_events}


def load_event_array(npz_path: Path):
    """讀回 converter 落地的 npz event array（hftbacktest convert 存於 key 'data'）。"""
    import numpy as np

    with np.load(str(npz_path)) as z:
        # 官方 convert 以 np.savez_compressed(out, data=array) 落地。
        key = "data" if "data" in z.files else z.files[0]
        return z[key]
