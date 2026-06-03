"""production listing capture-only collector package。

MODULE_NOTE:
  模塊用途：listing capture-only collector 的 package marker。collector reuse
    helper_scripts/research/ 的 gate_b_rest（phase SM + poller）與 gate_b_ws
    （獨立 WS + capture_lag + markout + poison 哨兵）純邏輯，新增 production
    持久化（pg_sink）、生命週期（capture_state）、常駐 daemon（daemon）、
    健康檢查（healthcheck）。對齊 PA 設計 docs/CCAgentWorkSpace/PA/workspace/
    reports/2026-06-03--production_listing_capture_collector_design.md。
  硬邊界（capture-only 旁路）:
    - 零 order / 零 strategy intent / 零 IPC trading / 零 live / 零 execution_authority
      / 零 改 engine。寫 PG 限 research.listing_capture_events + market.klines additive。
"""

from __future__ import annotations

from .config import COLLECTOR_VERSION

__all__ = ["COLLECTOR_VERSION"]
