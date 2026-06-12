"""Polymarket 數據採集軸（artifact-only 離線研究）。

MODULE_NOTE:
  模塊用途：Polymarket Gamma API 公開預測市場賠率的 point-in-time 採集器
    （snapshot lane）+ CLOB prices-history 歷史回補（retrospective lane，
    永不混入 snapshot lane）。產出 = 研究 artifact（jsonl + manifest），
    唯一消費者 = 離線研究腳本。
  紀律正本：docs/CCAgentWorkSpace/QC/workspace/reports/
    2026-06-11--polymarket_axis_discipline.md。
  定位鐵則（QC memo §0）：prediction-market 賠率 = corroborating context only，
    不可作主信號、不可 override 量化 gate、不可直驅交易；不在 Polymarket 交易
    （Bybit 唯一執行所），CLOB 下單 / auth 類 endpoint 全程不碰。
  主要模塊：collector（HTTP + 解析 + 攤平）、state（track-to-resolution 登記）、
    artifact（append-only run dir + manifest + sha256）、cli（三模式入口）。
  依賴：僅 Python 標準庫（urllib / json / hashlib …）；duckdb 為可選 parquet
    鏡像（缺套件 skip，照 gate_b 慣例）。
  硬邊界（R-0 同款隔離紅線）：
    - 絕不 import 任何生產模組；零 auth、零 order、零 PG、零 signal 輸出。
    - 採集端零 relevance 截斷：不 ranking、不丟 row（filter 是代碼可改版，
      raw 過去不可再生——QC memo §2 鐵則）。
    - append-only：每次採集 = 新 run dir，禁回填、禁覆寫舊 snapshot。
    - artifact root 禁硬編碼：${OPENCLAW_DATA_DIR:-/tmp/openclaw}/ 推導。

上游出處（MIT attribution）：
  解析邏輯（outcomes/outcomePrices 雙層 JSON-encoded 解析、安全浮點轉換、
  closed/active 判別）移植自 last30days-skill（MIT License）：
    repo:   https://github.com/mvanhorn/last30days-skill
    file:   skills/last30days/scripts/lib/polymarket.py
    commit: 122158415ae421da83e739f2668032f6bc78d39c (v3.3.2, 2026-06-06)
    (MIT License, Copyright (c) 2026 Matt Van Horn)
  已丟棄其 relevance 評分 / 截斷 / 搜索-UX 邏輯（QC memo §1：採集端
  ranking 截斷 = 不可逆選擇偏差，研究數據要 raw 全量）。
"""

from __future__ import annotations

COLLECTOR_VERSION = "polymarket_axis.v0.1"

SNAPSHOT_SCHEMA_VERSION = "polymarket.axis_snapshot.v0.1"
RAW_EVENT_SCHEMA_VERSION = "polymarket.axis_raw_event.v0.1"
RAW_MARKET_SCHEMA_VERSION = "polymarket.axis_raw_market.v0.1"
PRICES_HISTORY_SCHEMA_VERSION = "polymarket.axis_prices_history.v0.1"
MANIFEST_SCHEMA_VERSION = "polymarket.axis_manifest.v0.1"
STATE_SCHEMA_VERSION = "polymarket.axis_state.v0.1"

# lane 枚舉：snapshot = 「當時知道什麼」的 point-in-time 觀測（daily / hourly-topn /
# 已追蹤 market 的 resolution follow-up 都屬此 lane——follow-up 是「現在抓到的現值」）；
# retrospective = CLOB prices-history 事後回補序列，永不冒充「當時採集」（QC memo §2）。
LANE_SNAPSHOT = "snapshot"
LANE_RETROSPECTIVE = "retrospective"

# 查詢集 v1（QC memo §2 原文逐字；改集合 = 升版 v2，不回溯重算舊 run）。
QUERY_SET_VERSION = "v1"
QUERY_SET_V1_TAG = "crypto"
QUERY_SET_V1_KEYWORDS = (
    "bitcoin", "btc", "ethereum", "eth", "solana", "xrp",
    "bitcoin price", "all time high", "etf", "blackrock", "grayscale",
    "sec", "cftc", "stablecoin", "regulation", "bitcoin reserve",
    "fed", "fomc", "rate cut", "inflation", "cpi", "recession",
    "tether", "binance", "coinbase",
)

# 上游 MIT attribution（manifest 載入，供溯源）。
UPSTREAM_ATTRIBUTION = {
    "source_repo": "https://github.com/mvanhorn/last30days-skill",
    "source_file": "skills/last30days/scripts/lib/polymarket.py",
    "source_commit": "122158415ae421da83e739f2668032f6bc78d39c",
    "source_version": "v3.3.2",
    "license": "MIT",
}

__all__ = [
    "COLLECTOR_VERSION",
    "LANE_RETROSPECTIVE",
    "LANE_SNAPSHOT",
    "MANIFEST_SCHEMA_VERSION",
    "PRICES_HISTORY_SCHEMA_VERSION",
    "QUERY_SET_V1_KEYWORDS",
    "QUERY_SET_V1_TAG",
    "QUERY_SET_VERSION",
    "RAW_EVENT_SCHEMA_VERSION",
    "RAW_MARKET_SCHEMA_VERSION",
    "SNAPSHOT_SCHEMA_VERSION",
    "STATE_SCHEMA_VERSION",
    "UPSTREAM_ATTRIBUTION",
]
