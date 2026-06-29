# IBKR Stock/ETF Paper + Shadow Evidence Lane 開發安排

日期：2026-06-29
狀態：設計提案 / 尚未開工 / 不授權任何非 Bybit 實盤交易
目標窗口：實作前置 2-4 週；證據收集 6-8 週，從 collector 穩定運行後起算

## 0. PM 結論

本計劃的目標不是把現有 Bybit 策略直接搬到股票市場，也不是立刻打開
非 Bybit execution。目標是在 AE 既有治理、風控、審計、PnL scorecard 上
建立一條隔離的 `stock_etf_cash` research lane，先用 IBKR paper account 與
shadow fill model 收集 6-8 週 after-cost evidence。

短期允許的最終狀態只到：

- IBKR read-only account/market-data healthcheck
- IBKR paper account order lifecycle rehearsal
- shadow signal + conservative fill/cost reconstruction
- GUI 可按 asset lane 查看股票/ETF paper/shadow 證據
- 不允許 live IBKR、margin、short、options、CFD、資金劃轉、非 Bybit live

這是一個產品邊界變更候選。正式開工前必須先用新 ADR/AMD 修改
`Bybit-only execution` 的當前治理邊界，且該 ADR 只能批准 `paper/shadow`
研究面，不得順帶批准 IBKR live。

## 1. 背景與硬邊界

已確認事實：

- `ADR-0001` 規定 Rust `openclaw_engine` 是交易、風控、策略配置與執行權威。
- `ADR-0006` 規定 Bybit 是唯一 execution venue。
- `README.md` 與 `CLAUDE.md` 當前口徑仍是 Bybit-only execution。
- `ADR-0040` 只為未來 multi-venue gate 提供過 Binance 方向的 gate 先例，沒有批准股票 broker execution。
- 當前 Bybit Demo loop 尚無候選匹配的盈利證據；現有問題很可能是 after-cost edge 不足，而不只是工程未完成。

本計劃的核心假設：

- IBKR 能降低部分標的上的 cost wall，尤其是 US liquid stocks。
- 股票/ETF alpha 不能假設從 crypto 策略遷移而來，必須獨立建立 evidence。
- 股票/ETF lane 的價值在於更低相關性、更乾淨的交易成本、更成熟的報表與更完整的 paper/shadow 審計。

禁止事項：

- 不把 IBKR paper 成功視為 IBKR live 權限。
- 不讓 Python/FastAPI 持有交易真實狀態或自行下單。
- 不把 GUI lane selector 做成 trading authority。
- 不把 CFD 混入 `stock_etf_cash`。
- 不在沒有新 ADR 的情況下修改 `CLAUDE.md` / `README.md` 的 Bybit-only 口徑。

## 2. 產品分路

GUI 登錄後第一層應明確選擇 asset lane：

| Lane | 初始狀態 | 執行面 | 說明 |
|---|---|---|---|
| `crypto_perp` | 現有主線 | Bybit Demo/LiveDemo/Live gates | 保持現有 Bybit governance，不因本計劃變更 |
| `stock_etf_cash` | 新增，paper/shadow only | IBKR paper + shadow | 本計劃範圍；live 禁止 |
| `cfd_margin` | 顯示但 disabled | 無 | 可未來用 IG/Capital.com demo 評估；不得混入股票/ETF |

每個 lane 共享：

- GovernanceHub / Decision Lease 狀態機語義
- Guardian / risk governor 的 veto、downsize、circuit-breaker 原則
- append-only audit
- PnL scorecard 與 promotion evidence contract
- Operator approval 與 LAL 4 邊界

每個 lane 必須隔離：

- broker/venue adapter
- secret slot
- risk config
- cost model
- instrument identity
- market calendar
- settlement / corporate action / borrow / margin policy
- promotion proof

## 3. 新增 / 分路模塊

### 3.1 Rust types / core

建議新增或擴展：

- `openclaw_types::asset_lane`
  - `AssetLane::{CryptoPerp, StockEtfCash, CfdMargin}`
  - `BrokerVenue::{Bybit, IbkrPaper, IbkrLiveReserved}`
  - `BrokerEnvironment::{ReadOnly, Paper, LiveReserved}`
  - `InstrumentKind::{CryptoPerp, Stock, Etf, Cash, CfdReserved}`
- `openclaw_types::equity_instrument`
  - `EquityInstrumentId`
  - `ListingVenue`
  - `Currency`
  - `PrimaryExchange`
  - `TradabilityStatus`
  - `PriipsKidStatus`
  - `FractionalEligible`
- `openclaw_core::cost_model::ibkr`
  - commission
  - exchange/regulatory fee placeholders
  - FX conversion cost
  - FTT / stamp duty hooks
  - spread/slippage estimator
- `openclaw_core::calendar`
  - market session calendar
  - holiday/early-close handling
  - order TTL across sessions
- `openclaw_core::stock_etf_risk`
  - cash-only notional cap
  - no margin / no short / no options / no CFD invariant
  - per-symbol concentration cap
  - per-sector optional cap
  - overnight exposure cap

注意：現有 `M13 AssetClass / Venue` 設計偏 Bybit/Binance，不能直接把
IBKR live 塞進原 enum。應由新 ADR 決定是 amend M13，還是新增
`AssetLane` 作為更高層分流。

### 3.2 Rust engine

新增 engine 內部邊界：

- `asset_lane_router`
  - 根據 `AssetLane` 選擇 crypto 或 stock/ETF 流程
  - 初期只允許 `stock_etf_cash` 走 `paper` / `shadow`
- `broker_order_lifecycle`
  - normalized order intent
  - normalized order state
  - cancel/replace state machine reservation
  - paper fill import
- `stock_shadow_engine`
  - signal output 不觸發真實 order
  - conservative fill model
  - after-cost scorecard input
- `ibkr_paper_execution_adapter`
  - 只在 `OPENCLAW_IBKR_PAPER_ENABLED=1` 且 ADR gate 通過後可啟用
  - 不實作 live path；live path 使用 reserved enum + fail-closed error

任何 order-capable path 都必須仍由 Rust authority 掌握。Python route 只能
forward operator request 或讀狀態。

### 3.3 Python / FastAPI control plane

新增或分路：

- `app/asset_lane_routes.py`
  - active lane state
  - lane health
  - lane feature flags
- `app/stock_etf_routes.py`
  - paper/shadow run overview
  - instrument universe
  - PnL evidence
  - risk/cost preview
- `app/ibkr_paper_routes.py`
  - read-only healthcheck
  - paper account snapshot
  - paper order/fill import status
  - no direct order submission unless routed through Rust IPC authority
- `app/evidence_routes.py`
  - cross-lane scorecard view
  - after-cost proof artifacts
  - benchmark comparison

不建議把 IBKR 放在現有
`program_code/exchange_connectors/bybit_connector/` 下。建議新增：

```text
program_code/
  broker_connectors/
    ibkr_connector/
      paper_client.py
      readonly_client.py
      models.py
      fixtures/
```

但交易影響邏輯仍不在 Python connector。Python connector 只做 API client、
healthcheck、fixtures、paper fill import helper。

### 3.4 Data / DB

新增 schema 建議：

- `broker.instruments`
- `broker.instrument_listings`
- `broker.market_sessions`
- `broker.corporate_actions`
- `broker.fx_rates`
- `broker.paper_orders`
- `broker.paper_fills`
- `broker.commissions`
- `research.stock_shadow_signals`
- `research.stock_shadow_fills`
- `research.stock_etf_scorecard`
- `audit.asset_lane_events`

核心要求：

- 所有 paper order / fill / fee 必須可重建。
- shadow fill 必須標記 `synthetic_shadow`，不得與 broker paper fill 混同。
- IBKR paper fill 不等於 live fill proof。
- 每筆 scorecard row 必須帶 cost model version、broker、environment、asset lane、instrument identity。

若涉及 migration，必須按現有規則做 Linux PG empirical dry-run 與 idempotency double-apply。

## 4. 設置與 feature flags

新增配置文件建議：

```text
settings/asset_lanes/stock_etf_cash_paper.toml
settings/risk_control_rules/risk_config_stock_etf_paper.toml
settings/broker/ibkr_paper.toml
```

新增 env / feature flag：

| Key | 初始值 | 說明 |
|---|---|---|
| `OPENCLAW_STOCK_ETF_LANE_ENABLED` | `0` | GUI/Control API 顯示 stock lane 的總開關 |
| `OPENCLAW_IBKR_READONLY_ENABLED` | `0` | 允許 IBKR read-only healthcheck |
| `OPENCLAW_IBKR_PAPER_ENABLED` | `0` | 允許 IBKR paper order rehearsal |
| `OPENCLAW_IBKR_LIVE_ENABLED` | `0` | 必須永久 fail-closed，直到另開 live ADR |
| `OPENCLAW_ASSET_LANE_DEFAULT` | `crypto_perp` | 登錄後默認 lane |
| `OPENCLAW_STOCK_ETF_SHADOW_ONLY` | `1` | 初期禁止 paper order，僅 shadow |

Secret slot：

```text
$OPENCLAW_SECRETS_DIR/external/ibkr/readonly/
$OPENCLAW_SECRETS_DIR/external/ibkr/paper/
$OPENCLAW_SECRETS_DIR/external/ibkr/live/        # reserved only; 不創建或保持空
```

Authorization schema 後續需要新增欄位：

- `asset_lane`
- `broker`
- `environment`
- `secret_slot_fingerprint`
- `permission_scope`
- `expires_at`

但第一階段可以只做 read-only / paper-scoped envelope，不得復用 Bybit live
authorization。

## 5. GUI 更改

### 5.1 登錄後 lane selector

登錄成功後第一屏進入 asset lane selector：

- `Crypto Perps / Bybit`
- `Stock & ETF Cash / IBKR Paper`
- `CFD Margin / Disabled`

選擇後進入同一 Control Console，但左側/頂部必須有不可忽略的 lane badge。
所有 tabs 的資料查詢都必須帶 `asset_lane`。

### 5.2 Stock/ETF 專用視圖

新增或分路 tabs：

- `stock overview`
  - account paper equity
  - buying power paper value
  - open paper positions
  - lane health
- `stock universe`
  - symbol
  - listing venue
  - currency
  - tradability
  - fractional eligibility
  - PRIIPs / UCITS constraint
- `stock paper`
  - paper orders
  - paper fills
  - order lifecycle status
  - reconstructability checks
- `stock shadow`
  - signals
  - synthetic fills
  - conservative cost model
  - benchmark comparison
- `stock risk`
  - cash-only caps
  - no-margin/no-short/no-CFD invariants
  - concentration / overnight exposure
- `stock evidence`
  - after-cost expectancy
  - win/loss distribution
  - turnover
  - fees / spread / FX / tax drag
  - benchmark excess return

### 5.3 Existing tabs 分路

現有 tabs 不應重寫，應在 data source 層分路：

| Existing tab | 改動 |
|---|---|
| `system` | 顯示 active asset lane 與 lane health |
| `demo` | Crypto demo 與 stock paper 分開，不共用語義 |
| `live` | Stock/ETF lane 下顯示 live disabled / no authorization path |
| `strategy` | strategy universe 按 lane 分組 |
| `risk` | 讀取 lane-specific risk config |
| `governance` | Decision Lease / authorization 顯示 asset_lane 欄位 |
| `learning` | scorecard 按 lane filter |
| `edge-gates` | stock/ETF 的 evidence gate 單獨列出 |

## 6. 6-8 週 evidence collection 設計

證據窗口從以下條件全部成立後起算：

- IBKR paper/read-only connector 綠燈連續 5 個交易日
- shadow collector 連續 5 個交易日無缺口
- cost model version frozen
- universe frozen 或版本化
- scorecard 每日產出成功
- GUI 能展示 reconstructable evidence

### 6.1 初始 universe

建議只開兩組：

- US liquid stocks：大市值、高成交量、窄 spread；避免 penny / low liquidity
- UCITS ETFs：只做低頻/再平衡研究；不做高 turnover

暫不開：

- European single-stock intraday
- options
- margin
- short
- leveraged/inverse ETF
- CFD
- crypto stocks proxy basket

### 6.2 策略類型

第一批只做中低 turnover：

- daily/weekly momentum
- sector rotation
- mean reversion after overextension
- earnings drift research-only
- ETF trend + risk-off rotation
- opening/closing auction behavior shadow-only

不做：

- HFT / scalping
- high-turnover market making
- news 秒級交易
- hard-to-borrow / short alpha

### 6.3 Scorecard 指標

必須每日寫入：

- gross PnL
- commission
- spread estimate
- slippage estimate
- FX drag
- FTT/tax placeholder
- net PnL
- net expectancy per trade
- turnover
- max drawdown
- exposure time
- benchmark excess return
- conservative fill penalty sensitivity
- paper-vs-shadow divergence

Promotion-like 判斷需要：

- after-cost expectancy > 0
- benchmark excess return > 0
- conservative fill model 下仍 > 0
- 不由單一 event / 單一 symbol 驅動
- 標記 bull-heavy / regime-heavy / stale-window
- 至少 100+ 筆可重建樣本；低頻策略不足 100 筆時，需 walk-forward + bootstrap 補足統計可信度

## 7. 開發階段與派工

### Phase 0: Governance unlock / ADR

目標：允許 `stock_etf_cash` paper/shadow research lane，但不允許 live。

工作：

- 新 ADR：IBKR stock/ETF paper/shadow lane scope
- 明確 amend `ADR-0006` 的只讀/紙面例外，不改 live execution
- 定義 non-Bybit API call policy
- 定義 per-lane authorization schema
- review chain：`PM -> CC -> FA -> PA -> E3 -> QC -> MIT -> PM`
  - CC：16 根原則 / Bybit-only hard-boundary amend 審查
  - FA/PA：功能邊界與技術拆分
  - E3：IBKR secrets/API/redaction/security posture
  - QC/MIT：6-8 週 paper/shadow evidence 設計與統計可信度

驗收：

- ADR accepted 或 operator 明確批准
- `CLAUDE.md` / `.codex/MEMORY.md` 是否需要同步由 PM 判斷；未接受前不改
- `TODO.md` active implementation row 只能在 Phase 0 通過後新增

### Phase 1: Type / config / schema foundation

目標：讓系統能表達 asset lane、broker、instrument、environment、cost model。

工作：

- Rust type reservation
- config files
- DB migration design
- migration Linux dry-run packet
- fixture-based tests

驗收：

- Mac Rust/Python focused tests pass
- migration design ready；若 apply，必須 Linux PG dry-run + double apply
- no runtime mutation

### Phase 2: IBKR read-only + paper connector

目標：建立可測試、可重建、fail-closed 的 IBKR paper 接口。

工作：

- IBKR read-only account snapshot
- IBKR paper orders/fills import
- paper healthcheck
- redaction / secret handling
- paper-only order lifecycle rehearsal

驗收：

- paper account snapshot 可重建
- paper orders/fills 帶 broker ids
- secrets 不出現在 argv/log
- live path compile/runtime fail-closed

### Phase 3: Stock shadow collector + scorecard

目標：每日產出 after-cost evidence。

工作：

- universe builder
- market data ingestion
- conservative fill model
- cost model
- benchmark comparator
- daily scorecard writer

驗收：

- 5 個交易日穩定跑通
- scorecard row 可追溯到 signal、quote/bar、cost model、instrument identity
- paper fill 與 shadow fill 分表/分標記

### Phase 4: GUI lane selector + stock views

目標：operator 能在 GUI 上清楚區分 crypto 與 stock/ETF。

工作：

- login-success lane selector
- lane badge
- stock overview/paper/shadow/risk/evidence views
- lane-specific routing
- disabled CFD surface

驗收：

- GUI JS `node --check` 或更強驗證
- desktop/mobile smoke screenshot
- crypto tabs 行為不回歸
- stock live 清楚 fail-closed

### Phase 5: 6-8 週 paper/shadow evidence collection

目標：判斷 IBKR stock/ETF lane 是否存在 after-cost edge。

工作：

- daily collector
- weekly PM/QC/MIT review
- after-cost scorecard
- paper-vs-shadow divergence
- benchmark comparison
- operator weekly brief

驗收：

- 6-8 週完整報告
- QC/MIT/AI-E review
- PM go/no-go
- live 仍禁止；如要 tiny live probe，另開 ADR/authorization/spec

## 8. 預估工期

不含 6-8 週 evidence clock 的工程前置：

| 範圍 | 樂觀 | 中位 | 悲觀 |
|---|---:|---:|---:|
| ADR / spec / governance | 3 天 | 1 週 | 2 週 |
| types/config/schema | 1 週 | 1.5 週 | 2.5 週 |
| IBKR paper/read-only connector | 1 週 | 2 週 | 3 週 |
| shadow + scorecard | 1 週 | 2 週 | 3 週 |
| GUI lane selector/views | 1 週 | 1.5 週 | 2.5 週 |
| integration hardening | 3 天 | 1 週 | 2 週 |

可並行後的整體前置估算：

- 樂觀：2-3 週
- 中位：4-5 週
- 悲觀：6-8 週

證據收集另算 6-8 週，且只有在 Phase 3/4 穩定後開始計時。

## 9. 首批 acceptance criteria

進入 6-8 週 evidence collection 前：

- `stock_etf_cash` lane 只能 paper/shadow。
- IBKR live flag 永遠 fail-closed。
- 所有 IBKR secrets 使用 external secret slot。
- GUI lane selector 不授權任何交易。
- Paper order path 經 Rust authority，不經 Python 直接下單。
- 每筆 paper/shadow fill 可重建成本。
- Cost model version frozen。
- Universe version frozen。
- Benchmark version frozen。
- 日報可追溯至 append-only evidence。

6-8 週完成後：

- 產出 after-cost evidence report。
- 明確判斷是否有繼續 tiny-live 探索價值。
- 若沒有 after-cost edge，關閉或降級 stock/ETF lane。
- 若有 edge，只允許開新 ADR 討論 tiny-live，不得從 paper 自動升級。

## 10. 開工前需要 operator 決定

1. 是否接受 `stock_etf_cash` paper/shadow lane 方向。
2. 是否以 IBKR 作第一 broker baseline。
3. 是否允許 E3/CC/FA/PA 啟動 ADR 變更評審。
4. 是否把 eToro/Saxo 作為 Phase 5 之後的 challenger，而不是第一批同時接。
5. 是否接受工程前置中位 4-5 週 + evidence 6-8 週的總周期。

PM 建議：先批准 Phase 0。Phase 0 只產出 ADR/spec，不寫 runtime，不觸碰 IBKR API，不改 live 邊界。
