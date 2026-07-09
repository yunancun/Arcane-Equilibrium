# Scanner 行情預判增強工程日誌

日期：2026-05-01  
範圍：Rust scanner/scorer、demo/live_demo 新開倉 dispatch、passive healthcheck  
狀態：本地實作完成，已通過 release rebuild；等待 Linux 部署載入

## 背景

最近 12 小時 demo/live_demo 連續虧損不是單一 pipeline dead bug，而是策略 cell edge、行情 regime、maker 成交品質共同惡化。部署前 runtime 只讀檢查顯示：

- `live_demo` 12h MLDE：24 rows，平均 `-5.75bps`，中位 `-8.25bps`，勝率 `25.0%`
- `demo` 12h MLDE：37 rows，平均 `0.17bps`，中位 `-11.92bps`，勝率 `27.0%`
- 主要弱 cell：`grid_trading/ZEREBROUSDT -50.99bps`、`ma_crossover/ETHUSDT -48.44bps`、`grid_trading/ZECUSDT -33.99bps`
- runtime healthcheck 仍 WARN：`[33] maker_fill_rate` fee_drop `20.9%` / maker_like `25.7%`，`[38] grid lifecycle` live_demo 比 demo 更短，`[40] realized_edge_acceptance` 24h 平均 `-5.12bps`

因此本輪不是加一層全局風控，而是把 scanner 從「只選 symbol」提升為「產出可審計的分策略行情判斷」，讓每個策略新開倉前按自身需求判斷當前行情是否相容。

## 可行性與方案判斷

方案可行，且比以下替代方案更穩：

- 不採用 LLM 判斷行情：scanner 是高頻基礎設施，應保持 Rust 本地、確定性、可重建。
- 不採用全局 scanner best_strategy 硬 gate：同一 symbol 可能不適合 grid，但仍可能適合 MA 或 breakout；全局 gate 會誤傷策略自主性。
- 不改 close/reduce：行情判斷只影響 demo/live_demo 新開倉，既有倉位的止損、減倉、平倉不能被阻擋。

最終設計是「scanner 產生分策略 route judgement，dispatch 以 `intent.strategy` 查自己的 judgement」。

## 落地內容

### 1. scanner_config.toml 新增 `[market_judgment]`

文件：`settings/risk_control_rules/scanner_config.toml`

新增可調參數：

- `enabled`
- `gate_score_cap`
- grid regime gate：`grid_max_trend_score`、`grid_max_directional_efficiency`、`grid_max_dir_pct`、`grid_min_range_pct`
- trend / reversion / breakout / funding 專用 threshold
- 低樣本負 edge quarantine：`immature_negative_min_trades`、`immature_negative_bps_threshold`、`immature_negative_score_cap`

Rust 配置在 `scanner/config.rs` 中新增 `MarketJudgmentConfig`，包含 default、serde partial-load、validate。

### 2. scanner/scorer 增加 market regime features

文件：

- `rust/openclaw_engine/src/scanner/scorer.rs`
- `rust/openclaw_engine/src/scanner/market_judgment.rs`
- `rust/openclaw_engine/src/scanner/types.rs`

新增行情特徵：

- `signed_dir_pct`
- `signed_fr_bps`
- `trend_score`
- `range_score`
- `shock_score`
- `market_regime`

新增 `StrategyRouteJudgment`，每個 scanner candidate 都攜帶：

- `strategy`
- `fitness_score`
- `final_score`
- `edge_bps`
- `edge_bonus`
- `edge_n`
- `edge_status`
- `route_mode`
- `market_status`
- `route_reason`

scanner candidate 現在有完整 `strategy_judgments: BTreeMap<String, StrategyRouteJudgment>`。候選排序使用「經 edge + market judgement 後的最佳可交易 route」，避免某個原始高分但已被 gate 的策略把 symbol 從 universe 中錯誤擠掉。

### 3. EdgeFeedback 補充 market 狀態與路由原因

文件：`rust/openclaw_engine/src/scanner/scorer.rs`

`EdgeFeedback` 新增：

- `market_status`
- `route_reason`

`route_mode` / `edge_status` 改為 string metadata，便於 scanner snapshot、intent details、healthcheck 全鏈路序列化與 DB 後驗。

### 4. demo/live_demo 新開倉按策略自身 judgement gate

文件：

- `rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs`
- `rust/openclaw_engine/src/tick_pipeline/on_tick_helpers.rs`

dispatch 變更點：

- 根據 `intent.strategy` 查 `candidate.strategy_judgments[intent.strategy]`
- 若 engine mode 是 `demo` 或 `live_demo`，且該 strategy route 為 `market_gate` 或 `exploration_only`，直接 reject 該新開倉 intent
- `paper` 與真 `live` 不因本輪新增 market gate 改變
- close/reduce 路徑未改

intent details 的 scanner metadata 新增：

- `intent_strategy`
- `market_status`
- `route_reason`

### 5. healthcheck 新增 [41] scanner market-gate confirmation

文件：

- `helper_scripts/db/passive_wait_healthcheck/checks_scanner_market.py`
- `helper_scripts/db/passive_wait_healthcheck/runner.py`
- `helper_scripts/db/passive_wait_healthcheck/__init__.py`

新增 `[41] scanner_market_gate_confirmation`：

- 讀 `trading.scanner_snapshots.candidates[*].strategy_judgments`
- 找出被 `market_gate`、`edge_quarantine`、或 robust/posterior negative `exploration_only` 擋下的 strategy-symbol cell
- 往後 12 小時 join `learning.mlde_edge_training_rows`
- 若後續可評分樣本平均仍負，PASS
- 若被擋下後續卻非負，FAIL
- 若 gate 已觸發但尚無 label，WARN

這個 check 用於回答「被 scanner gate 擋下的 symbol/strategy 是否後續確實是負 edge」。

## 策略自主性邊界

本輪刻意避免「scanner 一刀切」：

- scanner 可以選 universe，也可以提供每個 strategy-symbol 的行情判斷。
- 每個策略新開倉時使用自身 `intent.strategy` 對應的 judgement。
- scanner `best_strategy` 只作排序 / 審計 / fallback，不代表其他策略必須盲從。
- close/reduce 不受 scanner market judgement 影響。

## 驗證

本地 Mac 已完成：

- `cargo fmt --all --check`
- `python3 -m py_compile helper_scripts/db/passive_wait_healthcheck/checks_execution.py helper_scripts/db/passive_wait_healthcheck/checks_scanner_market.py helper_scripts/db/passive_wait_healthcheck/runner.py helper_scripts/db/passive_wait_healthcheck/__init__.py`
- `cargo check -p openclaw_engine`
- `cargo test -p openclaw_engine scanner --lib`：65 passed
- `cargo test -p openclaw_engine --lib`：2385 passed
- `cargo build --release -p openclaw_engine`
- `git diff --check`

本輪新增後仍符合 repo 1200 行硬上限：

- `rust/openclaw_engine/src/scanner/scorer.rs`：1159 行
- `rust/openclaw_engine/src/scanner/market_judgment.rs`：280 行
- `helper_scripts/db/passive_wait_healthcheck/checks_execution.py`：1178 行
- `helper_scripts/db/passive_wait_healthcheck/checks_scanner_market.py`：212 行

## 部署注意事項

本輪需要 Linux rebuild 載入 Rust scanner / tick dispatch 變更。部署應使用：

```bash
bash helper_scripts/restart_all.sh --rebuild --keep-auth
```

原因：

- live_demo/live pipeline 使用 live-grade authorization；planned deploy 不應丟失 `authorization.json`
- 本輪不修改真 live 自動交易授權邊界
- 本輪不繞過 GovernanceHub / Decision Lease / live gates

## 預期效果與觀察點

部署後預期：

- demo/live_demo 新開倉中，grid 在單邊趨勢/高 directional efficiency 下會被擋住。
- MA / breakout / reversion / funding arb 各自依自己的行情需求判斷，不受 scanner 全局 best_strategy 盲控。
- `trading.intents.details.scanner` 將可看到 `intent_strategy`、`market_status`、`route_reason`。
- `[41] scanner_market_gate_confirmation` 會開始驗證 gate 是否真能避開後續負 edge。

部署後重點觀察：

- `[33] maker_fill_rate`
- `[38] grid_trading_lifecycle_drift`
- `[40] realized_edge_acceptance`
- `[41] scanner_market_gate_confirmation`

## 結論

本輪完成的是 scanner 行情預判基礎設施增強，不是新增 alpha 策略。它把最近連虧暴露出的「策略與行情 regime 不匹配」變成可配置、可審計、可後驗的本地 Rust gate，並保持策略自主判斷與 close/reduce 安全邊界。
