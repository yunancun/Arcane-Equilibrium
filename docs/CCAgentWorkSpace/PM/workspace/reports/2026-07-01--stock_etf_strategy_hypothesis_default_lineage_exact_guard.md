# Stock/ETF Strategy Hypothesis Default Lineage Exact Guard

日期：2026-07-01
角色：PM
範圍：IBKR Stock/ETF paper/shadow source hygiene；strategy hypothesis fail-closed lineage hardening

## 結論

已補強 `stock_etf_strategy_hypothesis` 的 pre-registration hypothesis default fail-closed coverage。這次只改
acceptance 與 source-static guard，不改 Rust production validator、IPC/API routes、IBKR connector、secret、
paper order route、market data collection、scorecard writer 或 Bybit 路徑。

## 變更

- Rust acceptance 將 default `StockEtfStrategyHypothesisV1` blocker 檢查提升為完整順序向量，覆蓋 identity、
  StockEtfCash/IBKR lane drift、strategy/timeframe/scope denial、所有 hash lineage、controls、paper-shadow、
  Bybit/IBKR live-denial blockers。
- Rust acceptance 將 contract/source drift、identity/family/timeframe/scope regressions、missing hashes、
  bad limits/controls/authority claims、single-flag authority/profitability/secret cases 固定為 exact vectors。
- Python source-static guard 新增 root validator、hash validator、limits/boundary validator blocker ordering
  parser，並鎖住 root validator child-call order。

## 驗證

- `rustfmt --edition 2021 --check rust/openclaw_types/tests/stock_etf_strategy_hypothesis_acceptance.rs`：PASS。
- `python3 -B -m pytest -q tests/structure/test_stock_etf_strategy_hypothesis_source_static.py --tb=short`：`11 passed`。
- `cargo test -p openclaw_types --test stock_etf_strategy_hypothesis_acceptance`：`8 passed`。
- Full `cargo test -p openclaw_types`：PASS。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace coverage：PASS。
- `git diff --check`：PASS。

## 邊界

- 無 Rust production code change。
- 無 IPC/API route、endpoint behavior、GUI runtime change。
- 無 IBKR contact、IBKR SDK import、connector runtime、secret access。
- 無 market data collection、scorecard writer、paper order routing、broker session。
- 無 paper-shadow launch、tiny-live/live authorization。
- 無 Linux runtime sync/restart，也無 Bybit live/demo execution behavior change。
