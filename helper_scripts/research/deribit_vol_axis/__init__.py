"""Deribit 隱含波動率數據軸（artifact-only 離線研究）。

MODULE_NOTE:
  模塊用途：Deribit 公開 API（唯讀、無需 key）的 point-in-time 期權波動率
    採集器——DVOL 隱含波動率指數 + IV term-structure（各到期 ATM IV）+
    put/call skew（IV vs moneyness）。產出 = 研究 artifact（jsonl + manifest），
    唯一消費者 = 離線研究腳本（Track2 另類數據軸的隱含波動率維度）。
  定位鐵則（CLAUDE 一/四 + ADR market-data 例外）：Bybit 是唯一 EXECUTION
    交易所；Deribit 僅作 ADR 允許的 read-only 市場數據來源，與 Tardis 同性質。
    本軸不碰執行路徑、不碰 5-gate、不碰 live 授權，賠率/IV = corroborating
    context only，不可作主信號、不可 override 量化 gate、不可直驅交易。
  主要模塊：collector（urllib HTTP + 解析 + term-structure/skew 構造）、
    artifact（append-only run dir + manifest + sha256，mirror polymarket_axis）、
    cli（daily / manual 模式入口）。
  依賴：僅 Python 標準庫（urllib / json / hashlib …）；duckdb 為可選 parquet
    鏡像（缺套件 skip，照 polymarket_axis / gate_b 慣例）。
  硬邊界（R-0 同款隔離紅線，mirror polymarket_axis）：
    - 絕不 import 任何生產模組；零 auth、零 order、零 PG、零 signal 輸出。
    - 不建 PG 表（artifact-only，避 V### migration），mirror polymarket_axis 模式。
    - 採集端零 relevance 截斷：不 ranking、不丟 instrument（filter 是代碼可改版，
      raw 過去不可再生——同 Polymarket 軸 QC memo §2 鐵則）。
    - PIT append-only：每次採集 = 新 run dir，禁回填、禁覆寫舊 snapshot
      （Polymarket 軸紀律：避 survivorship bias；snapshot 是當時 IV surface 的
      唯一 point-in-time 來源，覆寫 = 不可逆毀證）。
    - host allowlist 只含 www.deribit.com 唯一唯讀公開 API base：結構性排除任何
      private / 下單 / auth endpoint（/api/v2/private/* 全程不碰）。
    - artifact root 禁硬編碼：${OPENCLAW_DATA_DIR:-/tmp/openclaw}/ 推導。

採集面（2026-06-14 真實 public API probe 驗證）：
  - DVOL：GET /api/v2/public/get_volatility_index_data（currency + start/end_ts +
    resolution）→ result.data = [[ts_ms, open, high, low, close], ...]（OHLC of
    annualized vol index, 單位 %）。
  - IV surface：GET /api/v2/public/get_book_summary_by_currency（currency +
    kind=option）→ 單請求回全部 option instrument（944 BTC 級），每筆含 mark_iv +
    underlying_price + open_interest + volume。instrument_name 形如
    BTC-26MAR27-105000-C（CCY-DDMMMYY-STRIKE-{C|P}），解析出到期/strike/型別後
    在採集端構造 ATM term-structure 與 put/call skew（單請求覆蓋全鏈 = PIT 正確，
    無需逐 instrument ticker loop）。
"""

from __future__ import annotations

COLLECTOR_VERSION = "deribit_vol_axis.v0.1"

DVOL_SCHEMA_VERSION = "deribit.vol_axis_dvol.v0.1"
IV_SURFACE_SCHEMA_VERSION = "deribit.vol_axis_iv_surface.v0.1"
TERM_STRUCTURE_SCHEMA_VERSION = "deribit.vol_axis_term_structure.v0.1"
SKEW_SCHEMA_VERSION = "deribit.vol_axis_skew.v0.1"
RAW_INSTRUMENT_SCHEMA_VERSION = "deribit.vol_axis_raw_instrument.v0.1"
MANIFEST_SCHEMA_VERSION = "deribit.vol_axis_manifest.v0.1"

# 採集集 v1（改幣集 / endpoint 集 = 升版 v2，不回溯重算舊 run，mirror polymarket_axis
# QUERY_SET_VERSION 慣例：query/collection set 是代碼可改版，舊 run 凍結不重算）。
COLLECTION_SET_VERSION = "v1"
# 採集幣種（BTC / ETH 隱含波動率指數；Deribit DVOL 僅此二幣有指數）。
COLLECTION_CURRENCIES = ("BTC", "ETH")

__all__ = [
    "COLLECTION_CURRENCIES",
    "COLLECTION_SET_VERSION",
    "COLLECTOR_VERSION",
    "DVOL_SCHEMA_VERSION",
    "IV_SURFACE_SCHEMA_VERSION",
    "MANIFEST_SCHEMA_VERSION",
    "RAW_INSTRUMENT_SCHEMA_VERSION",
    "SKEW_SCHEMA_VERSION",
    "TERM_STRUCTURE_SCHEMA_VERSION",
]
