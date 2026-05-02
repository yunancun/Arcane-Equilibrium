# REF-20 — Paper Replay Lab 與 Learning Surface 設計（中文版）

**日期：** 2026-05-02
**狀態：** Draft 設計契約；後續實作必須遵守 REF-19 邊界。
**Owner：** PM
**英文版：** `docs/references/2026-05-02--paper_replay_learning_surface_design.md`
**關聯：** REF-19、REF-03、REF-04、REF-18、DOC-01 §5.3 / §5.7 / §5.8 / §5.10

---

## 1. 目的

REF-19 定義 Reality-Calibrated Fast Replay 的治理邊界。REF-20 定義這個能力應該放在哪些現有產品頁面裡，以及它如何連接 Learning、MLDE、DreamEngine 和目前的 5-Agent monitor。

目前最直接的開發痛點是：每次改策略或參數後，都要等待新的 paper / demo 數據累積。Paper Replay Lab 的目標，是把這個 loop 從數小時或數天壓縮到分鐘級：用歷史市場行情跑過最接近現有 runtime 的路徑，同時清楚報告 execution uncertainty、手續費、資料來源 tier 和 calibration freshness。

這個設計不取代 paper / demo 驗證。它增加的是一層快速淘汰與候選篩選機制，讓少量候選再進入 bounded demo A/B 驗證。

---

## 2. 現有系統結論

### 2.1 Paper Tab

目前相關檔案：

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/tab-paper.html`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/app-paper.js`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/paper_trading_routes.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/paper_trading_metrics.py`

觀察到的角色：

- Paper Tab 已經是 simulated non-live surface。
- Python paper engine 已退休；Rust engine 是目前 session routes 後面的唯一 paper trading engine。
- Paper API response 明確標記 simulated：`is_simulated=true`、`data_category=paper_simulated`。
- 現有頁面已經顯示 session state、balance、PnL、positions、active orders、fills、metrics 和 shadow decisions。

結論：Paper Tab 是改造成 Paper Replay Lab 的正確位置。Live Tab 不應該承擔 replay。

### 2.2 Learning Tab

目前相關檔案：

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/tab-learning.html`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/app-learning.js`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/learning_legacy_routes.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/learning_ops.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/learning_queries.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/learning_records.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/learning_auto_pipeline.py`

觀察到的角色：

- Learning Tab 是知識 cockpit：observations、lessons、hypotheses、experiments、review queue、net PnL summaries。
- auto pipeline 先產生 review packets；durable records 需要 operator approval。
- `learning_ops.py` 現在是 compatibility facade。新程式碼應該直接 import 更窄的 child modules。

結論：Learning Tab 應保持為 durable learning 和 review cockpit。它可以消費 replay evidence、監控 ML / Dream producers，但不應成為 replay runner。

### 2.3 5-Agent Monitor

目前相關檔案：

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/js/agent-tracker.js`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/agents_routes.py`

觀察到的角色：

- 5-Agent 目前嵌在 Learning Tab 裡。
- 後端 routes 是 read-only，且刻意在 PostgreSQL outage 時 degraded，而不是拖垮 operator console。
- 面板追蹤 agent roster、recent activity、cost、demo / shadow summaries、governance rejects、leases 和 budget。
- 這是 operational monitoring，不是 durable learning content。

結論：5-Agent 應該從 Learning 抽出，變成獨立 Agents Monitor surface。功能保留，只改產品邊界。

### 2.4 MLDE 和 DreamEngine

相關檔案：

- `program_code/local_model_tools/dream_engine.py`
- `program_code/local_model_tools/opportunity_tracker.py`
- `program_code/local_model_tools/cognitive_modulator.py`
- `program_code/ml_training/mlde_shadow_advisor.py`
- `program_code/ml_training/mlde_demo_applier.py`
- `program_code/ml_training/linucb_trainer.py`
- `program_code/ml_training/calibration.py`
- `program_code/ml_training/model_registry.py`

觀察到的角色：

- DreamEngine 會把 advisory parameter proposals 寫入 `learning.mlde_shadow_recommendations`。
- MLDE Shadow 會對 candidates 做 rank / veto，並寫 advisory recommendations。
- OpportunityTracker 只有在存在 outcome evidence 時才產生 regret summaries。
- Demo Applier 可透過既有 audited pathway 套用 bounded demo-only changes。
- `learning.mlde_edge_training_rows` 是 real-outcome training view。

結論：Replay 可以調用 ML / Dream，Learning 可以監控它們，但不得把它們改寫成 replay-only modules。

### 2.5 現有 Replay 基礎

相關檔案：

- `program_code/local_model_tools/backtest_engine.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/backtest_routes.py`
- `rust/openclaw_core/src/backtest.rs`
- `rust/openclaw_engine/src/startup/mod.rs`
- `rust/openclaw_engine/src/tick_pipeline/commands.rs`
- `rust/openclaw_types/src/price.rs`
- `rust/openclaw_engine/src/paper_state/fill_engine.rs`
- `helper_scripts/canary/replay_runner.py`

觀察到的角色：

- Python `BacktestEngine` 是 stub，不是 canonical replay path。
- Rust `openclaw_core::backtest` 有 bar-level backtest engine，但不是完整 `TickPipeline` 同路徑。
- Rust engine startup 已經有 replay mode：`--replay-mode`、`--replay-input`、`--replay-output`，可以把歷史 `PriceEvent` 餵進 `TickPipeline`。
- 目前 canary replay runner 可以從 Bybit klines 合成 OHLC ticks。這對 smoke test 有用，但如果沒有 calibrated fills 和更好市場資料，execution realism 低。

結論：Paper Replay Lab 第一版應建立在 Rust same-path replay 上，不應擴張 legacy Python backtest route。Paper fill engine 可重用 account / order lifecycle，但 execution realism 需要獨立 calibrated fill model。

---

## 3. 產品頁面決策

| Surface | 目標角色 | 決策 |
|---|---|---|
| Paper Tab | Paper Replay Lab：current paper session + fast replay + comparisons + reports + candidate handoff | 原地升級 |
| Learning Tab | Learning Cockpit：durable records、review queue、replay evidence inbox、ML / Dream producer monitor | 與 replay runner 分離 |
| 5-Agent Panel | Agents Monitor：operational health、activity、budget、governance state | 從 Learning 抽出，不刪功能 |
| Live Tab | live / live_demo monitoring 和 live-grade controls | 不承擔 replay |
| GovernanceHub | live-bound candidates 的 review / promotion boundary | replay 不自動批准 |

不要把 Paper Replay Lab 和 Learning Cockpit 合併成一個大 tab。兩者回答的問題不同：

- Paper Replay Lab 回答：「這次 code 或參數 patch，在歷史行情 + 務實 execution / fee 假設下，是否活得下來？」
- Learning Cockpit 回答：「系統學到了什麼？證據在哪裡？哪些 hypothesis / recommendation 需要 review？」
- Agents Monitor 回答：「agents 是否健康、活躍、成本受控、是否被 governance 卡住？」

---

## 4. 目標架構

```text
Historical Market Data
  S0 real fills/orders/verdicts
  S1 local recorded orderbook/trades
  S2 public klines/trades/funding/OI
  S3 synthetic OHLC ticks
        |
        v
Replay Orchestrator
  manifest + config hashes + git sha
        |
        v
Rust same-path replay through TickPipeline
        |
        v
Execution Reality Model
  fees + maker fill probability + timeout + latency + slippage bands
        |
        v
Replay Report
  q10/q50/q90 net bps + drawdown + source mix + calibration health
        |
        +--> Paper Replay Lab UI
        +--> Learning evidence/review queue
        +--> MLDE/Dream advisory calls, when enabled
        +--> Demo candidate handoff, only through existing bounded applier
```

Replay Orchestrator 是 experiment coordinator，不是 strategy authority。策略 / 風控行為應盡量來自 paper / demo / live 已使用的同一份 runtime config 和 Rust pipeline。

---

## 5. Paper Replay Lab 要求

Paper Tab 應重組為四個工作區：

1. Current Paper Session
   - 保留現有 session control、PnL、positions、orders、fills、metrics。
   - 保持明確 simulated data 標籤。

2. Fast Replay
   - 根據 symbol、date range、data tier、current git / config hashes、candidate parameter patch 建立 replay manifest。
   - 支援 start、cancel、inspect replay runs。
   - run 前顯示 data tier 和 execution calibration freshness。

3. Run Compare
   - 在同一資料窗口下比較 candidate vs baseline。
   - 顯示 gross bps、net bps after fees、q10 / q50 / q90、max drawdown、trade count、maker fill / timeout rate、taker slippage bands、reject rate、source mix。
   - 任何 `demo_candidate` 都必須有 baseline comparison。

4. Candidate Handoff
   - 只允許 advisory handoff：
     - 寫入 source-tagged replay report
     - 建立 Learning review evidence
     - 可選寫入 MLDE / Dream advisory recommendation
     - 可選把 `demo_candidate` 交給既有 bounded demo applier
   - 永遠不得直接修改 live / live_demo。

Paper Replay Lab 的 replay workflow 不得暴露 manual order submission path。

---

## 6. Learning Cockpit 要求

Learning 應維持為 durable knowledge cockpit。它可以新增兩個 replay 相關區塊，但不變成 replay runner。

### 6.1 Replay Evidence Inbox

Replay outputs 只能作為 tagged evidence 進入 Learning：

- `experiment_id`
- `manifest_hash`
- `git_sha`
- `strategy_config_sha256`
- `risk_config_sha256`
- `source_tier`
- `source_mix`
- `calibration_model_version`
- `calibration_freshness`
- `verdict`
- `baseline_delta`
- `report_uri`

Evidence 應進入 review queue 或未來 `learning.replay_evidence` table。它不得被當成 real outcome 寫入 `learning.mlde_edge_training_rows`。

### 6.2 ML / Dream Producer Monitor

Learning 應顯示以下 producer health：

- MLDE Shadow Advisor
- DreamEngine
- OpportunityTracker
- LinUCB trainer
- Model Registry
- Calibration jobs
- MLDE Demo Applier

最小 monitor 欄位：

- last run timestamp
- last successful run timestamp
- sample count
- input source view / table
- output table
- stale / degraded reason
- latest recommendation count
- latest applied demo-only count
- latest blocked-by-governance count

這個 monitor 是 read-only。它幫 operator 理解 ML / Dream 是否在學習與提出建議，而不是讓 replay 自動套用。

---

## 7. 5-Agent 抽出要求

目前 5-Agent monitor 應從 Learning 移出，成為 Agents Monitor tab 或等價 top-level monitor。

規則：

1. 保留 `agents_routes.py` 既有 read-only route posture。
2. 保留資料 outage 時 degraded response 的行為。
3. 儘量保留目前 `agent-tracker.js` 行為，但掛載位置移出 Learning。
4. 新 surface 存在後，移除 Learning 內 5-Agent 的視覺重量。
5. 除非未來有治理決策退休 agent model 本身，否則不得刪除 5-Agent 功能。

原因：5-Agent health、cost、activity、rejects 和 leases 都是 operational runtime signals，不是 observations、lessons、hypotheses 或 experiments。

---

## 8. API 與 Storage 設計

應新增 replay routes，而不是擴張 legacy `backtest_routes.py`。

建議 route family：

| Route | Method | 用途 |
|---|---|---|
| `/api/v1/replay/health` | GET | Replay subsystem readiness、calibration freshness、data source availability |
| `/api/v1/replay/manifests` | POST | 只建立 manifest；無 execution side effects |
| `/api/v1/replay/runs` | POST | 從 manifest id / hash 啟動 run |
| `/api/v1/replay/runs/{id}` | GET | run status、progress、data tier、degraded reason |
| `/api/v1/replay/runs/{id}/cancel` | POST | 取消 run |
| `/api/v1/replay/reports/{id}` | GET | report summary 和 links |
| `/api/v1/replay/compare` | POST | 比較 baseline vs candidate reports |
| `/api/v1/replay/candidates` | POST | advisory candidate handoff；永不 live approval |

Storage posture：

- Phase 1 可先把 manifests / reports 存在 repo-ignored runtime directory。
- Durable DB storage 後續可使用獨立 `replay.*` schema。
- Replay rows 永遠不得寫入 `trading.fills`。
- Replay labels 永遠不得混入 `learning.mlde_edge_training_rows`。
- 任何 replay-derived MLDE advisory row 都必須帶 `payload.replay_experiment_id`、`payload.source_tier`、`payload.manifest_hash`。

---

## 9. Execution Realism 要求

Paper Replay Lab 必須比目前 paper fill 假設更務實。Execution model 與 strategy replay 分離。

最小成本 / 執行模型：

- maker fee rate
- taker fee rate
- maker fill probability
- maker timeout probability
- maker latency
- maker adverse selection
- taker slippage q10 / q50 / q90
- reject probability

最小報告：

- calibrated case
- pessimistic case
- optimistic case
- insufficient-calibration warning
- data source tier warning
- source mix table

Fee handling 必須務實。針對 Bybit demo / live_demo parity，默認 fee model 應使用配置中的 maker / taker rates，並在報告中列出實際使用費率。

---

## 10. 分階段交付

### P0 - Design and Governance

- 新增 REF-20 和中文版 companion。
- 在 specification register 和 docs index 登記 REF-20。
- 不改 runtime。

### P1 - Paper Tab Information Architecture

- 把 Paper Tab 重命名 / 重組為 Paper Replay Lab。
- 保持 current paper session 行為不變。
- 若 backend 未 ready，可先加入 disabled 或 read-only 的 Fast Replay、Run Compare、Candidate Handoff placeholder。

### P2 - Read-Only Replay MVP

- 新增 `/api/v1/replay/*` routes。
- 第一版 canonical engine path 使用 Rust replay mode。
- 產生 manifest 和 report artifacts。
- 支援 baseline vs candidate comparison。
- S2 / S3 data 只用於 strategy signal 和 smoke-test confidence；execution confidence 必須標為 limited。

### P3 - Execution Calibration

- 從 S0 real demo / live_demo fills / orders 訓練或載入 execution reality model。
- 加入 fee、fill probability、timeout、latency、slippage、reject estimates。
- calibration stale 或 underpowered 時，阻止 actionable recommendations。

### P4 - MLDE / Dream Advisory Integration

- 允許 DreamEngine 提出 replay candidate parameter patches。
- 允許 MLDE 對 replay candidates 做 rank / veto。
- 只寫 source-tagged advisory rows。
- 加入 Learning producer monitor 和 replay evidence inbox。

### P5 - Agents Monitor Extraction

- 把 5-Agent dashboard 從 Learning 移出。
- 保持 read-only、degraded-safe route behavior。
- Learning Tab 收斂回 learning records、review、replay evidence、ML / Dream producer health。

### P6 - Bounded Demo A/B Handoff

- `demo_candidate` 只能透過既有 MLDE demo applier handoff。
- 要求 baseline comparison、calibration health、source mix、replay manifest。
- live / live_demo mutation 仍由 GovernanceHub、Decision Lease 和 live gates 保護。

---

## 11. 驗收檢查

任一實作 phase 完成前，至少需要以下檢查：

| Check | 要求 |
|---|---|
| `replay_manifest_contract` | 每個 run 都有 manifest、config hashes、git sha、data tier、output policy |
| `replay_source_mix` | 每份 report 都揭示 real / calibrated / synthetic / counterfactual mix |
| `execution_calibration_freshness` | stale calibration 會阻止 actionable handoff |
| `execution_calibration_power` | low sample cells 會 shrink 或標為 insufficient |
| `replay_no_live_mutation` | replay routes 不能修改 live / live_demo config 或提交 live orders |
| `replay_shadow_sink_boundary` | replay-derived MLDE rows 必須 advisory 且 source-tagged |
| `replay_report_reproducibility` | report 可由 manifest 和 input artifacts 重建 |
| `paper_replay_lab_no_trading_submit` | replay UI 不暴露 live / manual order submission |
| `learning_producer_monitor_read_only` | Learning producer monitor 沒有 mutation controls |
| `agents_monitor_read_only` | 抽出的 5-Agent monitor 保持 read-only 和 degraded-safe |

---

## 12. 成本策略

默認方案：

1. 使用現有 S0 demo / live_demo records 作 calibration labels。
2. 使用免費或低成本 S2 Bybit public data 做第一版 historical replay。
3. 盡快開始本地錄製 S1 market data。
4. 在具體 gap 被證明，且 operator 批准精確 cost / scope 前，不購買 S4 paid L2 data。

這是成本最低、又能提升開發速度並保留 execution uncertainty 的路線。

---

## 13. 最終決策

Paper Tab 應改造成 Paper Replay Lab。Learning 應保持 Learning Cockpit，新增 replay evidence 和 ML / Dream producer monitoring。當前 5-Agent panel 應從 Learning 抽出為獨立 Agents Monitor，保留其 read-only operational value。

這個設計直接針對「改完策略後等待數據太久」的開發瓶頸，同時不假裝 paper fills 就是真實交易所 fills。它用 fast replay 快速淘汰壞方案、選出候選，再靠 calibrated uncertainty、source tagging 和 bounded demo validation 進入 live-bound governance review。
