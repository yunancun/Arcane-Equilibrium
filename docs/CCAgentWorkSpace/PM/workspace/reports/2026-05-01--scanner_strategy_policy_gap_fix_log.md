# Scanner 策略政策 gap 修復工程日誌

日期：2026-05-01  
範圍：scanner strategy-symbol route eligibility、demo/live_demo 新開倉前置 gate  
狀態：本地驗證完成，等待 Linux 部署回填

## 背景

前一輪 scanner 行情判斷增強後，發現一個真實策略 gap：scanner 會把 `NAORISUSDT + ma_crossover` 選成候選 route，但 `RiskConfig.per_strategy.ma_crossover.blocked_symbols` 已明確阻擋 `NAORISUSDT`。結果是 scanner 持續把注意力分配到下游必定拒絕的 strategy-symbol cell，demo/live_demo 出現大量 `risk_gate` rejected spam。

這不是行情模型本身錯，而是 scanner route eligibility 沒同步 per-strategy symbol policy。

## 設計決策

採雙層修復：

1. scanner scoring 層同步 `RiskConfig.per_strategy`：
   - 每輪 scan 從 paper/demo/live 三個 `RiskConfigStore` 讀當前快照。
   - 如果某 strategy-symbol 新開倉在三個目標環境都會被 per-strategy policy 拒絕，該 route 標記為 `risk_policy_gate`，`market_status=policy_blocked`，並從 scanner best-route 競爭中移除。
   - 如果至少一個目標環境允許，scanner 不全局移除，避免 demo/live 配置未來分歧時過度保守。

2. dispatch 層按當前 engine 再做 pre-gate：
   - 僅作用於 `demo` / `live_demo` 的 `StrategyAction::Open`。
   - 在寫 `trading.signals` / `trading.intents` / `risk_verdicts` 前，用當前 engine 的 `RiskConfig` 檢查 per-strategy policy。
   - close/reduce 路徑不受影響。

## 主要改動

- 新增 `scanner/strategy_policy.rs`
  - `ScannerStrategyPolicyStores`
  - `ScannerStrategyPolicy`
  - `apply_strategy_policy`
- `scanner/scorer.rs`
  - 新增 `score_ticker_with_policy`
  - policy-blocked route 不再可成為 scanner best route
  - 所有可選 route 都被 policy-blocked 時，該 symbol 本輪不進 candidate
- `scanner/runner.rs` / `main.rs`
  - ScannerRunner 接入 paper/demo/live risk stores，每輪 scan 生成 policy snapshot
- `config/risk_config_per_strategy.rs`
  - 抽出共用 `per_strategy_new_entry_rejection`
  - `intent_processor` 與 scanner 共用同一套 per-strategy symbol policy 判斷
- `tick_pipeline/on_tick/step_4_5_dispatch.rs`
  - demo/live_demo 新開倉在 risk verdict 前 pre-gate
  - 新增支援 `risk_policy_gate`

## 驗證

本地已通過：

- `cargo fmt --all --check`
- `cargo test -p openclaw_engine scanner::strategy_policy --lib`
- `cargo test -p openclaw_engine scanner --lib`
- `cargo test -p openclaw_engine --lib`
- `cargo check -p openclaw_engine`
- `cargo build --release -p openclaw_engine`

新增測試覆蓋：

- 三端全部拒絕時 scanner policy 才拒絕 route
- 任一目標環境允許時 scanner 不全局移除 route
- 原 best route 被 policy-blocked 時 scanner 改選其他策略 route
- 所有可選 route 都被 policy-blocked 時 symbol 不進 candidate

## 預期效果

- `NAORISUSDT + ma_crossover` 這類已被 per-strategy policy 明確阻擋的 cell 不再成為 scanner best route。
- demo/live_demo 不再把這類新開倉寫成 risk verdict rejected spam。
- 策略仍按自身 route judgment 行動，不會盲目服從 scanner 的單一 best strategy。
- 平倉、減倉、fast-track reduce、風控 close 路徑不變。

