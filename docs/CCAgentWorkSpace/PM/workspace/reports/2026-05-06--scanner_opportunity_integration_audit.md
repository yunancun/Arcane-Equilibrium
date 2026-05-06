# Scanner Opportunity 整合審計

日期：2026-05-06
角色：PM
Repo root：`/Users/ncyu/Projects/TradeBot/srv`
Read-time HEAD：`df5b1638`
Implementation / deploy HEAD：`74b986a0`
Continuation / deploy HEAD：`113f345f`
Regret healthcheck HEAD：`d1754aa6`
Admission canary / deploy HEAD：`98ce3d00`
狀態：Scanner Opportunity 已完成本 session 收口：v1 typed evaluation、`[51]` healthcheck、shared cost definition、runtime AccountManager cost prior、demo/live_demo new-open canary、pre-risk rejected intent/verdict row proof 均已落地並 Linux rebuild deploy。

更新：v1 shadow implementation 已落地，詳
`docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-06--scanner_opportunity_v1_shadow_implementation.md`。

續做更新：

- `[51] scanner_opportunity_shadow_acceptance` 已落地，詳
  `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-06--scanner_opportunity_healthcheck_51.md`。
- `113f345f` 將 scanner opportunity 的 fee+slippage round-trip cost 定義改為復用
  `edge_predictor::gate::estimate_round_trip_cost_bps`，scanner 只額外加當前 spread。
- Linux `trade-core` 已 `restart_all.sh --rebuild --keep-auth` 部署 `113f345f`；watchdog
  `engine_alive=true`，demo/live snapshots fresh。
- 最新 scanner snapshot（2026-05-06 19:53:12+02:00）75/75 route judgments 帶
  `opportunity`，且 75/75 `opportunity.reason` 含
  `cost_model=edge_predictor_round_trip+spread`。
- `5434543c` 將 `[51]` 擴展到 rejected scanner intents：用
  `risk_verdicts` + `intents.details.scanner.opportunity` + `decision_outcomes`
  形成 missed / regret counterfactual proof；positive LCB 被 reject 但後續為正時
  WARN-only，不新增 gate。
- `d1754aa6` 修正 `[51]` intent coverage denominator：只統計
  `jsonb_typeof(details->'scanner') = 'object'` 的真 scanner context，避免
  `{"scanner": null}` 非 scanner intent 造成 false FAIL。
- Linux focused `[51]` after `d1754aa6`：WARN；3h snapshot routes 370/370，
  scanner intents 6/6，24h labels=7<10，rejected_labels=0。
- `98ce3d00` 接入 shared `AccountManager` 作 scanner opportunity cost prior：
  per-symbol taker fee 優先，fee cache 冷啟動時使用 AccountManager conservative
  default taker fee，並持久化 `components.cost_source`。
- `98ce3d00` 開啟 `canary_block_new_entries = true`。此 canary 只阻擋
  demo/live_demo new-open；close / reduce / protective exit 不受 scanner
  opportunity 影響。
- `98ce3d00` 將 scanner pre-risk rejects（per-strategy risk policy、
  scanner market gate、opportunity canary）持久化為 `trading.intents` +
  synthetic rejected `trading.risk_verdicts`，且 intent details 保留
  `scanner.opportunity`，讓 `[51]` 能後續累積 rejected counterfactual proof。
- Linux `trade-core` 已 `restart_all.sh --rebuild --keep-auth` 部署
  `98ce3d00`。部署後最新 scanner snapshot（2026-05-06 20:46:59+02:00）
  85/85 route judgments 帶 `opportunity`、85/85 帶
  `cost_source=account_manager_taker_fee`、85/85 帶 canary 欄位。
  最近 30 分鐘 demo/live_demo rejected scanner intents 78/78 帶 scanner
  opportunity，其中 2 筆為 `scanner_opportunity_canary`。
  focused `[51]`：WARN，3h snapshot routes 485/485，scanner intents 50/50，
  24h labels=9<10，rejected_labels=0（需等 decision_outcomes backfill）。

## 結論

不要再加一個孤立 gate。已落地的是 typed Scanner Opportunity Evaluation
內部產出的 canary admission flag，並由既有 demo/live_demo new-open
pre-risk path 消費；它不是獨立於 scanner evaluation 的臨時補丁。

耐久方向是把目前散在 scanner、edge、cost、learning 裡的判斷收斂成一個 typed **Scanner Opportunity Evaluation** 層。它應該是 Rust 純計算，輸出可審計的 opportunity 欄位，然後由既有 open-admission path 或未來 Agent Decision Spine 消費；它不應成為新的隱性交易權威。

產品語義要分清：

- Scanner 仍然負責掃描市場。
- Scanner 也要判斷「某個 strategy-symbol-side 現在是否是數學上值得開倉的機會」。
- 這個機會判斷要 current-state-first，不能被低樣本歷史數據過度牽引。
- realized historical edge 只應校準 confidence / uncertainty，不應主導 market opportunity score。

當前止血目標是 **new-entry admission**。Close / reduce / protective exit 不屬於 scanner opportunity 範圍。

## 已確認事實

權威 scanner 在 Rust：

- `rust/openclaw_engine/src/scanner/types.rs`
- `rust/openclaw_engine/src/scanner/scorer.rs`
- `rust/openclaw_engine/src/scanner/market_judgment.rs`
- `rust/openclaw_engine/src/scanner/runner.rs`

Python `MarketScanner` 只是 retained stub：

- `program_code/local_model_tools/market_scanner.py`

Python 控制面已經 Rust scanner 優先：

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/rust_scanner_reader.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategy_wiring_scanner.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategy_read_routes.py`

目前 scanner 對 new-open 的實際阻擋點在：

- `rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs`

它會因以下條件阻擋新開倉：

- symbol 不在 scanner active universe
- per-strategy risk policy reject
- scanner `route_mode in {market_gate, exploration_only, risk_policy_gate}`
- funding-arb exploration 特例

Cost / edge admission 另在 IntentProcessor 中實作：

- `rust/openclaw_engine/src/intent_processor/gates.rs`
- `rust/openclaw_engine/src/intent_processor/router.rs`

我們想要的 quantile / LCB 類 EV 數學已經有雛形：

- `rust/openclaw_engine/src/edge_predictor/gate.rs`
- `rust/openclaw_engine/src/edge_predictor/features.rs`
- `rust/openclaw_engine/src/edge_predictor/feature_builder.rs`

學習與 advisory 面已經會攜帶 scanner context：

- `program_code/ml_training/mlde_shadow_advisor.py`
- `program_code/local_model_tools/dream_engine.py`
- `program_code/local_model_tools/opportunity_tracker.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/edge_estimator_scheduler.py`
- `program_code/ml_training/realized_edge_stats.py`
- `program_code/learning_engine/fee_execution_calibrator.py`

## 整合地圖

| 現有模組 | 當前角色 | Scanner Opportunity 角色 | 邊界 |
|---|---|---|---|
| `scanner/scorer.rs` | market fitness、hard filters、correlation selection | 主要 neutral market-structure component | 保持 pure、current-state-first |
| `scanner/market_judgment.rs` | per-strategy route compatibility / route mode | 收編為 `market_compatibility` 與 `invalidation_reason` | 不再讓每個 route mode 都像獨立 gate |
| `scanner/types.rs` | `ScoredSymbol`、`StrategyRouteJudgment` audit fields | 在這裡加 typed opportunity fields | serialization backward compatible |
| `scanner/strategy_policy.rs` | RiskConfig per-strategy eligibility bridge | policy mask / eligibility | disabled / blocked strategy 是 policy，不是 market opportunity |
| `intent_processor/gates.rs` | JS cost gate / demo-live strictness | opportunity result 的 consumer 或 shadow fallback | 長期避免 duplicate JS edge logic |
| `edge_predictor/gate.rs` | intent-time quantile EV gate | 復用 LCB versus execution cost 的數學定義 | predictor optional；no-model fallback 必須顯式 |
| `edge_predictor/feature_builder.rs` | intent-time feature vector | admission-time opportunity 的 canonical feature schema | scanner-time subset 不能依賴 position-only fields |
| `edge_estimates.rs` | runtime JS cell estimates | historical calibration / uncertainty | 低樣本歷史不能 overfit 當前機會 |
| `edge_estimator_scheduler.py` / `realized_edge_stats.py` | 產生 realized edge snapshots | calibration producer | freshness / sample quality 是 acceptance input |
| `fee_execution_calibrator.py` | maker/taker/fee quality estimate | execution-cost calibration | feed cost priors，不 feed market opportunity |
| `RiskConfig.market_gate` / slippage config | microstructure thresholds / cost settings | shared cost / tradability source | 消除 scanner hard filters threshold drift |
| `mlde_shadow_advisor.py` | offline advisory | validation / ranking feedback | 不進 hot-path authority |
| `dream_engine.py` | read-only parameter proposal | post-trade pattern feedback | 不進 hot-path authority |
| `opportunity_tracker.py` | rejected-opportunity regret summary | false block / missed opportunity validation | 不能直接觸發開倉 |
| `strategy_wiring_scanner.py` / ScoutWorker | scanner-to-agent intel | opportunity candidate consumer | 讀 opportunity fields，不重算 |
| `bybit_ai_route_selector_builder.py` | AI spend routing proxy | consumer only | 其 `opportunity_score` 是 AI 路由價值，不是 trading edge |
| H0 / Guardian / Decision Lease / Risk Governor | hard safety / governance | 保留在外層 | 不能被 scanner 弱化或吞掉 |
| Exit P1b / phys lock / step 6 risk checks | close / reduce / protective behavior | feedback source only | scanner opportunity 只管 new-open |

## 建議 Contract

在既有 scanner serialization surface 上新增 scanner-side opportunity object。

建議 Rust shape：

```rust
pub struct OpportunityComponents {
    pub market_structure_score: f64,
    pub strategy_fitness_score: f64,
    pub gross_opportunity_bps: Option<f64>,
    pub execution_cost_bps: Option<f64>,
    pub cost_uncertainty_bps: Option<f64>,
    pub historical_edge_bps: Option<f64>,
    pub historical_edge_n: u32,
    pub historical_edge_lcb_bps: Option<f64>,
    pub data_quality_score: f64,
    pub calibration_weight: f64,
}

pub struct OpportunityDecision {
    pub opportunity_score: f64,
    pub opportunity_lcb_bps: Option<f64>,
    pub admission_hint: String,
    pub reason: String,
}
```

這個 object 應掛在每個 `StrategyRouteJudgment` 上，而不是只掛 best strategy。真正要問的是 strategy-specific 問題：`grid_trading:BTCUSDT` 可以是弱機會，同一時間 `ma_crossover:BTCUSDT` 可以是可接受機會。

建議中性數學：

```text
opportunity_lcb_bps =
  q10(gross_current_opportunity_bps)
  - q90(expected_execution_cost_bps)
  - uncertainty_buffer_bps
```

其中：

- `gross_current_opportunity_bps` 先由當前 market structure / strategy fit 推出。
- `expected_execution_cost_bps` 使用 fee、spread、slippage、maker/taker calibration。
- `uncertainty_buffer_bps` 對 stale data、低樣本、no model、volatile microstructure 加大。
- realized `edge_estimates` 只調整 calibration weight 與 posterior uncertainty；除非 mature negative evidence 足夠 robust，否則不能抹掉 fresh neutral signal。

沒有 predictor 時不要偽裝精準：

```text
opportunity_lcb_bps = None
admission_hint = shadow_only | exploration_budget | weak_opportunity
```

這樣 operator 和 healthcheck 仍然能審計，但不會把 fallback heuristic 偽裝成 trained edge。

## Admission 語義

新層應使用一套統一 vocabulary：

- `tradability_block`：hard market facts、impossible order constraints、missing instrument、disabled strategy、不可接受 spread/liquidity。
- `opportunity_positive`：current-state LCB 扣除 cost / uncertainty 後仍為正。
- `opportunity_weak`：current-state LCB 為零或負。
- `exploration_candidate`：current-state signal 合格但 confidence 低，只能在明確 exploration budget 內通過。
- `calibration_block`：mature realized negative evidence 足夠強，與當前 signal 矛盾並阻擋。

這套語義可以逐步替換目前混雜的 `market_gate`、`exploration_only`、`robust_negative`、cost-gate negative reasons。第一步必須 shadow emit，不改行為。

## 為什麼這不是創可貼

現在慢性虧損不是靠禁掉某個 strategy 或某個 symbol 能耐久修好。真正問題是「candidate ranking」、「market fit」、「realized historical edge」、「execution cost」、「risk policy」分散在不同地方，而且語義有重疊。

耐久修復應讓 new-open admission 回答一個通用問題：

```text
這個 exact strategy-symbol-side 在扣除 execution cost、uncertainty、
hard eligibility 後，是否仍有正 expected net opportunity？
```

這個問題可跨 MA / Grid / BB / Funding、demo / live_demo、replay validation、未來 Agent Decision Spine 重用。單點 gate 或臨時封鎖做不到。

## 實作順序

1. Shadow fields only，零行為改變
   - 在 scanner types 增加 opportunity structs。
   - 對每個 per-strategy judgment 計算 opportunity components。
   - 寫入 `trading.scanner_snapshots`。
   - 經 `rust_scanner_reader.py` 與 `/scanner/opportunities` 暴露。
   - 寫入 `IntentScannerContext` 與 `trading.intents.details.scanner`。

2. Shared cost model
   - 復用 `edge_predictor::gate::estimate_round_trip_cost_bps`。
   - 對齊 scanner hard filters 與 `RiskConfig.market_gate` / slippage config。
   - 消費 fee / maker calibration snapshots 作為 cost priors。

   **2026-05-06 續做狀態**：第一條已完成於 `113f345f`。Scanner opportunity 不再手寫
   fee+slippage round-trip cost，而是使用 `estimate_round_trip_cost_bps`，再疊加
   scanner-time spread 作為當前市場成本。這仍是 shadow-only，沒有任何
   `opportunity_lcb_bps` / `admission_hint` enforcement。尚未完成的是動態 cost-source：
   runtime fee/maker calibration snapshots 仍未成為 scanner cost prior；這是下一個
   durable 切口，而不是新增 gate。

3. Shadow acceptance healthcheck
   - 比較 `opportunity_lcb_bps <= 0` 與後續 realized negative round trips。
   - 比較 `opportunity_lcb_bps > 0` 與 missed / regret opportunities。
   - 按 strategy 追 false block / false pass rate。

   **2026-05-06 續做狀態**：`[51]` 已覆蓋 snapshot / intent / MLDE row proof、
   positive-LCB realized outcome warmup，以及 rejected scanner-intent
   counterfactual regret proof。新 rejected path 直接對齊 scanner
   `opportunity_lcb_bps` 與 `components.expected_execution_cost_bps`，來源是
   `risk_verdicts` / `intents` / `decision_outcomes`，語義與
   `opportunity_tracker.py` 的 rejected-outcome regret summary 一致但保持 healthcheck
   read-only。Runtime 結果是 row proof 100%，但 labels=7<10 且
   rejected_labels=0，所以正確回 `WARN`。

4. Admission consolidation
   - 不新增 gate number。
   - 在既有 open-admission seam 內替換重複 route/cost interpretation。
   - live strictness、Governance、Decision Lease 不變。

5. Canary enforcement
   - 先只作用於 demo / live_demo new opens。
   - close / reduce 不受影響。
   - 只有 shadow metrics 證明能減少負 open 且不讓 learning 樣本餓死時才 enforcement。

## AgentTodo 對齊

這個工作和 AgentTodo M2 完全對齊，但如果只做 shadow scanner metadata，不需要等 M1 row proof。

相關 backlog：

- `MAG-020`：scanner authority modes。
- `MAG-021`：`OpportunityCandidate` / `OpportunityDecay` contracts。
- `MAG-024`：scanner hot-path gate to advisory shadow comparison。
- `MAG-025`：scanner churn / wave PnL replay set。
- `MAG-026`：scanner decay 不能 auto-close。

PM 建議切分：

- **Scanner Opportunity v1 shadow** 可以先開，因為只是 metadata，不改 authority。
- **任何 enforcement** 必須等 M1 row proof、E2/E4 acceptance、明確 canary criteria。

## 明確非目標

- 不把 Strategist LLM 或 cognitive modulation 搬進 scanner。
- 不讓 OpportunityTracker 或 DreamEngine 開倉。
- 不弱化 H0、Guardian、Decision Lease、Risk Governor、protective close。
- 不用 scanner decay 自動平倉。
- 不把 historical realized edge 當主要 opportunity score。
- 不保留 Python `MarketScanner` 作第二套 opportunity engine。

## Dispatch 建議

下一輪 handoff：

PM -> PA -> E1/E1a -> E2 -> E4 -> QA -> PM

PA deliverable：

- Rust struct additions 精確定義。
- feature flag semantics：`shadow_only`、`demo_enforced`、`live_demo_enforced`。
- cost-source ownership。
- migration / API compatibility notes。
- replay / healthcheck acceptance metrics。

E1/E1a 第一波：

- Rust scanner opportunity fields。
- Python reader / API propagation。
- intent details propagation。
- serialization tests 與 no-behavior-change tests。

E2/E4 gate：

- 證明 shadow mode 不新增 rejection 行為。
- 證明 Linux runtime 會持久化 scanner opportunity fields。
- 證明 healthcheck 能把 opportunity result 和後續 realized outcome 對上。
