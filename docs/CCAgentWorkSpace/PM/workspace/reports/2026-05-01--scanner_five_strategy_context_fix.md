# Scanner 五策略 context 修復工程日誌

日期：2026-05-01
範圍：scanner active-symbol context、趨勢 phase 特徵、五策略 route fitness、intent / IPC metadata
狀態：已部署 Linux `trade-core`，runtime 驗證通過

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
- `cargo build --release -p openclaw_engine`
- `git diff --check`

Linux `trade-core` 已完成：

- fast-forward 到 `06bb5cb`
- release rebuild
- engine-only restart
- 新 engine PID：`2364863`
- watchdog：`engine_alive=true`

## 三端一致性確認

本輪「三端」按 Rust runtime 的 ConfigStore 定義確認為 `paper` / `demo` / `live`。DB 中的 `live_demo` 是 live-grade execution lane，scanner / risk config 來源仍走 live 端 store。

確認結果：

- ScannerRunner 啟動時接入 `ScannerStrategyPolicyStores::new(paper, demo, live)`，每輪 scan 都重新 `load_policy()`，因此 scanner route eligibility 使用三端最新 RiskConfig。
- Scanner active universe 是全局共享的；AddSymbol / RemoveSymbol 廣播到所有 pipeline，不是某一端單獨維護一份 scanner universe。
- `paper` / `demo` / `live` 的 `RiskConfig.per_strategy` policy 一致：
  - `ma_crossover` 三端各有 3 個 blocked symbols。
  - `grid_trading` / `bb_reversion` / `bb_breakout` / `funding_arb` 三端 blocked count 均為 0。
  - 五個 strategy 的 risk-policy route 判斷結果三端一致。
- 策略參數 IPC：
  - `demo` / `live` 均可查到 5 種策略參數。
  - `paper` 目前回 `paper pipeline disabled`，這是既有 runtime 狀態，不代表 scanner 不一致。
  - `funding_arb` 在 demo active、live inactive，是策略啟用策略差異；scanner 仍會為 `funding_arb` 生成 route judgment / fitness / context，是否實際開倉仍由對應 engine 的策略啟用與風控決定。
- Runtime scanner snapshot 驗證：
  - 最新 scan：`scan-1777662406506`
  - active_count=10，`BTCUSDT` / `ETHUSDT` 均為 active 且均存在 candidate context。
  - `BTCUSDT`：`market_regime=trending`，`trend_phase=clean_trend`，`strategy_judgments=5`
  - `ETHUSDT`：`market_regime=mixed`，`trend_phase=mixed`，`strategy_judgments=5`
  - IPC `get_scanner_status` 已能返回 `trend_phase` 與五個 fitness 欄位。

結論：scanner 的資料生成、active universe、per-strategy route judgment、以及三端 risk-policy eligibility 已一致；策略是否 active 屬各 engine 的策略控制面，不應視為 scanner 三端不一致。

## 工程思路與改進

本輪修復的核心不是「再加一道門」，而是把 scanner 從粗粒度候選排序器升級成可審計的市場結構 attribution 層：

1. 不增加新 gate
   既有 `market_gate` / `edge_watch` / `momentum_caution` / `risk_policy_gate` 語義保持不變。新字段只影響 fitness shaping 和審計 metadata，不新增拒單條件。

2. 五策略共享同一份 market feature surface
   `ma_crossover`、`grid_trading`、`bb_reversion`、`bb_breakout`、`funding_arb` 全部讀同一組 `MarketConditions`，避免每個策略各自用不一致的 scanner 解讀。

3. 趨勢預判從 regime 升級為 phase
   原本 `trending / range_bound / one_way_shock / quiet / mixed` 太粗，現在補上：
   - `close_alignment`：收盤位置是否支持當前 24h 方向。
   - `range_position`：最新價位於 24h range 的位置。
   - `crowding_score`：資金費率與單邊行情共同構成的擁擠 proxy。
   - `reversal_risk_score`：趨勢失敗 / 反轉風險 proxy。
   - `trend_phase`：`clean_trend`、`failed_trend`、`crowded_shock` 等更細標籤。

4. 策略按真實需求取用 scanner data
   - `ma_crossover`：需要 clean trend；crowding / failed trend 降分。
   - `grid_trading`：需要可用 range；trend / shock 降分。
   - `bb_reversion`：需要 range + reversal setup；shock 降分。
   - `bb_breakout`：需要 trend expansion + close alignment；不再單純因高 DE 懲罰，而是懲罰 crowded / failed trend。
   - `funding_arb`：需要 funding edge；spot trend / shock / crowding 只降分，不硬阻擋 demo 學習。

5. Pinned / active symbols 和 dynamic candidates 同 surface
   scanner snapshot 的 `candidates` 現在代表 active-universe context，而不是只代表動態入選候選。Pinned BTC/ETH、anti-churn 留存 symbols、以及新選入 symbols 都能被 dispatch 和審計面讀到完整 scanner context。

6. 審計面可直接追蹤五策略差異
   strategy intents 的 `details.scanner` 與 IPC `get_scanner_status` 都帶出五個 fitness 分數、trend phase、crowding、reversal risk。後續分析某筆交易是否應該由某策略開倉，可以直接對照當時 scanner 對五種策略的相對判斷，而不是只看單一 best_strategy。

新增 / 更新測試覆蓋：

- `funding_arb` estimate key
- `funding_arb` 可成為 scanner 第五個 best route
- breakout 不再因高 DE 本身被懲罰，改為懲罰 failed trend
- 五策略全 policy-blocked 時 symbol 才從 scanner selection 丟棄

## 2026-05-01 follow-up：Python / Agent / MLDE surface 對齊（不 rebuild）

本輪按「不新增 gate、不做 Rust rebuild」原則，補齊 scanner 資料在 Python 控制面、Agent 情報面、MLDE / Dream 學習面的取用路徑。Rust scanner hot path 未改動。

### 1. Python 控制面改讀權威 Rust scanner

新增 `rust_scanner_reader.py`，作為 Python 控制面統一 reader：

- 透過 IPC `get_scanner_status` 讀 Rust scanner 最新狀態。
- `/scanner/opportunities` 保留原 GUI 舊欄位：`symbol` / `strategy_type` / `score` / `reason`。
- 同時新增：
  - `scanner_context`：market_regime / trend_phase / trend_score / range_score / shock_score / crowding / reversal risk 等。
  - `fitness`：`f_ma` / `f_grid` / `f_bbrv` / `f_bkout` / `f_funding_arb`。
  - `breakout_proxy`：暴露 bb_breakout 當前 proxy inputs，標記為 audit only。
  - `strategy_judgments`：若 DB 最新 scanner snapshot 可用，從 `trading.scanner_snapshots.candidates` 補齊每策略 route judgment。

這裡的 DB 補齊是 fail-soft：IPC 仍是主來源；DB 不可用時 API 不 500，只少掉 per-strategy 詳細 judgment。

### 2. ScoutWorker 從 stub 改為 Rust scanner 優先

原 ScoutWorker 每 30 分鐘呼叫 `MarketScanner.scan()`，但 Python `local_model_tools.market_scanner.MarketScanner` 已是 legacy stub，`scan()` 返回空列表，導致 Scout→Strategist 情報面拿不到 scanner 趨勢判斷。

本輪改為：

1. 先讀 Rust scanner normalized opportunities。
2. 若 Rust scanner / IPC 不可用，再 fallback 到 legacy `MarketScanner.scan()`。
3. Scout intel metadata 帶出：
   - `scanner_source`
   - `scanner_candidates`
   - `market_regimes`
   - `trend_phases`

結果：Agent 情報面現在能讀到 pinned BTC/ETH 和其他 active symbols 的 scanner 趨勢 phase / market regime，而不依賴 Python stub。

### 3. MLDE / Dream 訓練與建議面補 scanner context

新增 SQL migration `V034__mlde_scanner_context_columns.sql`，重建 `learning.mlde_edge_training_rows`，並在 view 尾部追加 scanner context 欄位：

- regime / phase：`scanner_market_regime`、`scanner_trend_phase`
- trend/range/shock：`scanner_trend_score`、`scanner_range_score`、`scanner_shock_score`
- 位置與風險：`scanner_close_alignment`、`scanner_range_position`、`scanner_crowding_score`、`scanner_reversal_risk_score`
- 原始 market inputs：`scanner_directional_efficiency`、`scanner_dir_pct`、`scanner_signed_dir_pct`、`scanner_range_pct`、`scanner_fr_bps`
- 五策略 fitness：`scanner_f_ma`、`scanner_f_grid`、`scanner_f_bbrv`、`scanner_f_bkout`、`scanner_f_funding_arb`

`mlde_shadow_advisor.py` 與 `dream_engine.py` 現在會把可用 scanner context 放入 recommendation / insight payload。為避免 DB migration 尚未 apply 時整個 advisor 失效，兩者會先查 view columns；缺失欄位以 NULL select，保持 backward compatible。

### 4. BB breakout proxy 的處理

本輪沒有新增 bb_breakout gate，也沒有把 kline Bollinger bandwidth 硬塞進 scanner hot path。原因是：

- 現有 Rust scanner 的 `f_bkout` 是 market-structure proxy：trend / range expansion / close alignment / crowding / failed-trend 風險。
- 真正的 BB bandwidth / squeeze / band expansion 屬於策略 indicator domain，若要在 Rust scanner 中直接納入，需要 scanner 讀 kline/indicator context，屬 Rust hot path 改造並需要 rebuild。

因此本輪做的是「暴露 proxy inputs + 讓學習面可歸因」，不是加門。後續若 `bb_breakout` 持續虧損，應用這些欄位做 counterfactual 分析，再決定是否值得做 kline-bandwidth Rust scanner 改造。

### 5. 本輪不改變的邊界

- 不新增 scanner gate。
- 不改 Rust scanner scorer / runner / dispatch hot path。
- 不修改 live / live_demo execution authority。
- 不 rebuild，不 restart engine。
- SQL migration 只擴展 learning view；ML/Dream 仍是 advisory / shadow surface。

## 結論

這次修復沒有新增 hard gate；scanner 的作用從「四策略粗 regime 分流」提升為「五策略共享的市場結構 attribution」。Pinned BTC/ETH、anti-churn active symbols、以及 dynamic candidates 都會保有同樣的 scanner context surface；五種策略可按自身真實需求讀取同一份 scanner data。
