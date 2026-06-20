"""Polymarket → Bybit lead-lag IC research harness.

MODULE_NOTE:
  模塊用途：讀 Polymarket point-in-time snapshot artifacts，構造 implied probability
    delta features，對齊 Bybit perp forward returns，輸出 leak-free IC report。
  硬邊界：
    - research artifact only；不輸出 signal、不碰 strategy/risk/order/auth。
    - PG 只在 CLI 缺 price fixture 時 read-only SELECT market.klines。
    - Polymarket row 零過濾紀律不變；本 harness 只在研究端分桶 price_target vs
      event_reg，原始採集 artifact 不回寫、不覆寫。
"""

from __future__ import annotations

RUNNER_VERSION = "polymarket_leadlag.v0.12"
REPORT_SCHEMA_VERSION = "polymarket.leadlag_report.v0.12"

STATUS_INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"
STATUS_NO_SNAPSHOT_ROWS = "NO_SNAPSHOT_ROWS"
STATUS_NO_PRICE_DATA = "NO_PRICE_DATA"
STATUS_IC_READY_NO_SIGNIFICANT_EDGE = "IC_READY_NO_SIGNIFICANT_EDGE"
STATUS_IC_CANDIDATE_REVIEW_REQUIRED = "IC_CANDIDATE_REVIEW_REQUIRED"

BUCKET_PRICE_TARGET = "price_target"
BUCKET_EVENT_REG = "event_reg"
BUCKET_EVENT_REG_DIRECT = "event_reg_direct"
BUCKET_EVENT_REG_MACRO = "event_reg_macro"
BUCKET_OTHER = "other"

SYMBOL_SOURCE_ASSET_DIRECT = "asset_direct"
SYMBOL_SOURCE_MACRO_EVENT_REG = "macro_event_reg"

__all__ = [
    "BUCKET_EVENT_REG",
    "BUCKET_EVENT_REG_DIRECT",
    "BUCKET_EVENT_REG_MACRO",
    "BUCKET_OTHER",
    "BUCKET_PRICE_TARGET",
    "REPORT_SCHEMA_VERSION",
    "RUNNER_VERSION",
    "SYMBOL_SOURCE_ASSET_DIRECT",
    "SYMBOL_SOURCE_MACRO_EVENT_REG",
    "STATUS_IC_CANDIDATE_REVIEW_REQUIRED",
    "STATUS_IC_READY_NO_SIGNIFICANT_EDGE",
    "STATUS_INSUFFICIENT_SAMPLE",
    "STATUS_NO_PRICE_DATA",
    "STATUS_NO_SNAPSHOT_ROWS",
]
