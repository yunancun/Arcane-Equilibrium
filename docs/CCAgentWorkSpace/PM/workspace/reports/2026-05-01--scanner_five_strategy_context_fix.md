# Scanner 五策略 context 修復工程日誌

日期：2026-05-01
範圍：scanner active-symbol context、趨勢 phase 特徵、五策略 route fitness、intent / IPC metadata
狀態：本地驗證通過，待 Linux 部署驗證

## 背景

前一輪已修復 pinned / active symbols 只在 dynamic candidates 中找 scanner context 的問題，BTC/ETH 等 pinned symbols 已能持續生成 scanner candidate context。本輪繼續修正 scanner 對五種策略的資料供給一致性，以及趨勢預判過粗的問題。

核心判斷：不新增新的 gate。這次只增強 scanner 的可解釋特徵與 route fitness，讓下游策略能基於自身需求取用同一份 scanner 判斷。

## 主要改動

- `funding_arb` 升級為 scanner 第五個正式 `StrategyCategory`：
  - `as_estimate_key()` 對應 `funding_arb`
  - `compute_fitness()` 同時計算 `f_funding_arb`
  - best-route 競爭包含 `funding_arb`
  - strategy-policy 測試同步五策略全阻擋場景
- `MarketConditions` / `ScoredSymbol` 新增趨勢細節：
  - `trend_phase`
  - `close_alignment`
  - `range_position`
  - `crowding_score`
  - `reversal_risk_score`
- 趨勢預判從粗略 `trend/range/shock` 擴展為 phase：
  - `crowded_shock`
  - `one_way_shock`
  - `failed_trend`
  - `clean_trend`
  - `range_bound`
  - `quiet`
  - `mixed`
- 五策略 fitness 調整為使用同一組 scanner features：
  - `ma_crossover`：重視 clean trend，懲罰 crowding / failed-trend
  - `grid_trading`：重視 range score，懲罰 trend / shock
  - `bb_reversion`：重視 range + reversal setup，懲罰 shock
  - `bb_breakout`：重視 trend + range expansion + close alignment，懲罰 crowding / failed-trend
  - `funding_arb`：重視 funding，懲罰 spot trend / shock / crowding
- Intent scanner details 和 `get_scanner_status` IPC top candidates 補齊：
  - 五個 fitness 分數
  - trend phase / crowding / reversal-risk
  - 原有 per-strategy route judgment 保留

## 驗證

本地已通過：

- `cargo fmt --all -- --check`
- `cargo test -p openclaw_engine scanner --lib`
- `cargo test -p openclaw_engine ipc_server::tests::scanner --lib`
- `cargo test -p openclaw_engine tick_pipeline --lib`
- `cargo test -p openclaw_engine --lib`（2394 passed / 0 failed）
- `git diff --check`

新增 / 更新測試覆蓋：

- `funding_arb` estimate key
- `funding_arb` 可成為 scanner 第五個 best route
- breakout 不再因高 DE 本身被懲罰，改為懲罰 failed trend
- 五策略全 policy-blocked 時 symbol 才從 scanner selection 丟棄

## 結論

這次修復沒有新增 hard gate；scanner 的作用從「四策略粗 regime 分流」提升為「五策略共享的市場結構 attribution」。Pinned BTC/ETH、anti-churn active symbols、以及 dynamic candidates 都會保有同樣的 scanner context surface；五種策略可按自身真實需求讀取同一份 scanner data。
