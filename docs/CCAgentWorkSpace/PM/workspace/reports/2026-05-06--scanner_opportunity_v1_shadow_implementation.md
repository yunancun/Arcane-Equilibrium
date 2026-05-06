# Scanner Opportunity v1 Shadow Implementation

日期：2026-05-06
角色：PM
Repo root：`/Users/ncyu/Projects/TradeBot/srv`
狀態：本地實作完成；等待 commit / 三端同步 / Linux rebuild deploy

## 範圍

本輪實作 `Scanner Opportunity Evaluation v1 shadow`。

明確邊界：

- 只新增 scanner opportunity 計算、持久化欄位、intent details、Python API 正規化與測試。
- 不新增 gate number。
- 不使用 `opportunity_lcb_bps` 或 `admission_hint` 來拒單。
- 不改 close / reduce / protective exit。
- 不改 H0、Guardian、Decision Lease、Risk Governor、IntentProcessor cost gate 的 authority。

## 已落地

### Rust scanner

新增：

- `rust/openclaw_engine/src/scanner/opportunity.rs`
  - 純函數 `evaluate_opportunity(...)`
  - current-state-first LCB 計算
  - execution cost / cost uncertainty / market uncertainty / historical calibration components
  - shadow `admission_hint`

更新：

- `rust/openclaw_engine/src/scanner/types.rs`
  - `OpportunityComponents`
  - `OpportunityDecision`
  - `StrategyRouteJudgment.opportunity: Option<OpportunityDecision>`
- `rust/openclaw_engine/src/scanner/config.rs`
  - `OpportunityConfig`
  - default serde / validation / TOML round-trip
- `rust/openclaw_engine/src/scanner/scorer.rs`
  - 每個 per-strategy judgment 都會附上 opportunity shadow object
  - route selection 邏輯不讀 opportunity，不改分數篩選
- `rust/openclaw_engine/src/scanner/runner.rs`
  - runtime 使用 `scanner_config.toml [opportunity]`
- `settings/risk_control_rules/scanner_config.toml`
  - 新增 `[opportunity]`，全部為 shadow/audit knobs

### Intent details

更新：

- `rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs`
  - 從 matched strategy judgment 取 `opportunity`
- `rust/openclaw_engine/src/tick_pipeline/on_tick_helpers.rs`
  - `trading.intents.details.scanner.opportunity` 持久化同一份 object

這確保後續 realized outcome / MLDE / replay 可以從 intent details 對上當時 scanner opportunity。

### Python control plane

更新：

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/rust_scanner_reader.py`
  - `/scanner/opportunities` normalized row 新增 `opportunity`
  - 保留完整 `strategy_judgments[*].opportunity`
  - 處理 Rust enum serialization key (`MaCrossover`) 與 estimate key (`ma_crossover`) mismatch

## Shadow 數學

核心欄位：

```text
opportunity_lcb_bps =
  q10(gross_current_opportunity_bps)
  - q90(expected_execution_cost_bps)
  - uncertainty_buffer_bps
```

v1 實作方式：

- `gross_current_opportunity_bps`：`strategy_fitness_score * fitness_gross_bps_per_score`
- `expected_execution_cost_bps`：`2 * (one_way_fee_bps + slippage_buffer_bps) + spread_bps`
- `cost_uncertainty_bps`：config base + spread buffer
- `uncertainty_buffer_bps`：base + shock / crowding / reversal / data-quality penalty
- `historical_edge_lcb_bps`：JS cell shrunk bps 的 lower confidence bound
- historical negative 只增加 uncertainty penalty；positive history 只小幅降低 uncertainty，不直接覆寫 current-state opportunity

這符合「中性、量化、current-state-first」要求。

## 對抗性審查

檢查項：

- `opportunity_lcb_bps` / `admission_hint` 沒有出現在 IntentProcessor rejection path。
- `step_4_5_dispatch.rs` 仍只用原有 `route_mode` / policy / cost gate 分支，沒有新增 opportunity-based `continue`。
- `StrategyRouteJudgment.opportunity` 使用 `#[serde(default, skip_serializing_if = "Option::is_none")]`，舊 snapshot / DB enrichment backward compatible。
- Python reader 不重算 opportunity，只讀 Rust snapshot / IPC / DB enrichment。
- `score_ticker_with_policy(...)` 舊 API 保持 default config，runner 走 configured API。
- close / reduce path 沒有新增 scanner opportunity 依賴。

審查結論：

- v1 shadow 功能完整。
- 本輪沒有發現會改變交易行為的 gap。
- 剩餘 future gap 是刻意非目標：shadow acceptance healthcheck、admission consolidation、demo/live_demo canary enforcement。

## 驗證

本地通過：

- `rustfmt --edition 2021 --check` on touched Rust files
- `git diff --check`
- `cargo test -p openclaw_engine scanner --lib --manifest-path rust/Cargo.toml`
  - 79 passed
- `cargo test -p openclaw_engine --lib --manifest-path rust/Cargo.toml`
  - 2519 passed
- `cargo build --release -p openclaw_engine --manifest-path rust/Cargo.toml`
  - passed
- `python3 -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/app/rust_scanner_reader.py`
  - passed
- `PYTHONPATH=. python3 -m pytest tests/test_scanner_opportunities_ipc.py tests/test_strategy_wiring_scanner.py -q`
  - 13 passed

Warnings：

- Rust warnings 為既有 unused/dead_code warnings。
- Python warnings 為既有 Pydantic v2 deprecation warnings。

## 下游使用

新欄位位置：

- scanner snapshot:
  - `trading.scanner_snapshots.candidates[*].strategy_judgments.<strategy>.opportunity`
- intent details:
  - `trading.intents.details.scanner.opportunity`
- API:
  - `/api/v1/strategy/scanner/opportunities` normalized row `opportunity`
  - `strategy_judgments[*].opportunity`

## 後續

下一步可以派：

1. E4 / QA：Linux runtime query 驗證新 scanner snapshot 與 intent details 出現 opportunity object。
2. QC / MIT：設計 shadow acceptance healthcheck，對比 `opportunity_lcb_bps` 與後續 realized outcome。
3. PA：定義 admission consolidation 條件，但 enforcement 必須等 shadow metrics 和 canary criteria。
