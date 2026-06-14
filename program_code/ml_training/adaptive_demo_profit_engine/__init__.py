"""
MODULE_NOTE (中):
  Adaptive Demo Profit Engine（ADPE）閉環 runner package。
  用途：把已建且已測綠的核心 allocator（program_code.ml_training.
  regime_bandit_allocator.RegimeBanditAllocator）接成一個 **demo-only** 閉環：
  定期讀近窗 realized demo PnL（per strategy×regime）→ ingest 進 allocator →
  allocate → 對 demo 引擎呼 set_strategy_active（活化贏家 / 停損家），並附
  kill switch（一鍵停 runner + 還原策略 active 態 snapshot）。

  主要子模組：
    - reward_source：讀 learning.mlde_edge_training_rows（demo scope、post-fee
      net_bps_after_fee、attribution_chain_ok），複用 linucb_trainer SQL pattern，
      不合成任何 PnL。
    - ipc_lever：薄殼，複用既有 sync_ipc_call('set_strategy_active') IPC，0 新 IPC。
    - demo_maker_arm：demo-maker 候選 arm 定義 / 註冊 cell（post-only maker 捕價差）。
    - runner：編排五步 + kill switch + CLI/cron entry（默認 dry-run）。

  硬邊界 / 誠實鐵則（為什麼這樣設計）：
    1. **demo 沙盒專用**。閉環只控 demo 路徑；真錢 / mainnet 5-gate / live 路徑
       完全不碰（runner 啟動硬鎖 engine_mode='demo'，非 demo 直接拒絕整個 cycle）。
    2. **不合成 PnL / fills**。reward 只餵 realized demo PnL（post-fee、attribution-gated），
       不走 NULL 的 trading.decision_outcomes（已知 bug）。
    3. **demo-maker 增益標 artifact 不可轉移**。demo-maker arm 的成交走 allocator
       all_fills 軌標 saw_artifact，transferable_only 軌（promotion 鐵則）誠實不吸收。
    4. **0 改既有檔**。本 package 全新檔；整合靠複用既有 IPC / SQL pattern，
       不動既有碼。
"""

from __future__ import annotations
