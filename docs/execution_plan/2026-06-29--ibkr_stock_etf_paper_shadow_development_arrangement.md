# IBKR Stock/ETF Paper + Shadow Evidence Lane 開發安排

日期：2026-06-29
狀態：設計提案 / 尚未開工 / 不授權任何非 Bybit 實盤交易
目標窗口：實作前置 2-4 週；證據收集 6-8 週，從 collector 穩定運行後起算

## 0. PM 結論

本計劃的目標不是把現有 Bybit 策略直接搬到股票市場，也不是立刻打開
非 Bybit execution。目標是在 AE 既有治理、風控、審計、PnL scorecard 上
建立一條隔離的 `stock_etf_cash` research lane，先用 IBKR paper account 與
shadow fill model 收集 6-8 週 after-cost evidence。

2026-06-29 PM 對抗性審查結論：CC/FA/PA/E3/QC/MIT 一致認為方向有效，
但只批准 Phase 0 ADR/spec。Phase 1+ 實作、IBKR API 呼叫、secret slot 建立、
paper order rehearsal、GUI runtime enablement、6-8 週 evidence clock 均需先補齊
第 11 節 blocker。

2026-06-29 第二輪對抗性審查結論：CC/FA/PA/E3/E5/QC/MIT/QA 八角色一致
不能認證「按排程後完整上線」或「無遺漏」。本計劃仍只批准 Phase 0，
且 Phase 0 必須從單一 ADR/spec 擴展為 ADR + interface / security / data /
GUI / evidence / QA release packet。Phase 1 只能實作已接受的契約；不得讓
E1 在實作中現場發明 broker、IPC、DB、GUI 或 evidence contract。

2026-06-29 第三輪 launch-certification 結論：在第二輪 hard gates 已寫入
本計劃後，CC/FA/PA/E3/E5/QC/MIT/QA 八角色一致返回
`CERTIFIABLE_IF_GATES_PASS`，scope 嚴格限定 `paper_shadow_only`，findings
為 0。這只表示：若 Phase 0 named contract packet 被接受，且 Phase 1-5
每個 gate 以 machine-checkable artifact 全部通過，PM 可簽核
`stock_etf_cash` paper/shadow lane 完整上線。它不表示目前可上線，不授權
IBKR live/tiny-live，也不證明盈利或 durable alpha。

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

長期 GUI 目標是讓 operator 能明確區分 asset lane；但二輪審查後的第一個
GUI slice 不得是 login-success lane selector。首批只允許 default `crypto_perp`
badge / readiness / status page；完整 selector 必須等後端 contract、route/cache
partition、auth/flag matrix 與 disabled-state negative tests 都通過後再做。

| Lane | 初始狀態 | 執行面 | 說明 |
|---|---|---|---|
| `crypto_perp` | 現有主線 | Bybit Demo/LiveDemo/Live gates | 保持現有 Bybit governance，不因本計劃變更 |
| `stock_etf_cash` | 新增，paper/shadow only | IBKR paper + shadow | 本計劃範圍；live 禁止 |
| `cfd_margin` | reserved / first GUI slice 不顯示 | 無 | 只保留 denial tests；不得混入股票/ETF |

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

本節是目標模塊拆分，不是 Phase 1+ 開工授權。對抗性審查後的 PM 判斷：
以下模塊名還不足以實作，必須先補出 lane-scoped Interface、DB evidence
contract、feature-flag invariants 與 IBKR API/session 選型。

### 3.1 Rust types / core

建議新增或擴展：

- `openclaw_types::asset_lane`
  - `AssetLane::{CryptoPerp, StockEtfCash, CfdMargin}`
  - `Broker::{Bybit, Ibkr}`
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

審查後約束：

- 不使用 `BrokerVenue::{IbkrPaper, IbkrLiveReserved}` 這種混合 broker 與
  environment 的型別。
- `IbkrLiveReserved` 若作 serialization reservation，任何 order path 使用時必須
  typed-deny；不得成為 dormant live toggle。
- 新 enum 不得有 `Other(String)` / catch-all venue/broker/lane variant。

### 3.2 Rust engine

新增 engine 內部邊界：

- `asset_lane_router`
  - 根據 `AssetLane` 選擇 crypto 或 stock/ETF 流程
  - 初期只允許 `stock_etf_cash` 走 `paper` / `shadow`
- `lane_scoped_ipc`
  - 新增 lane-scoped Rust IPC / command contract
  - 禁止復用既有 Bybit/Paper `submit_paper_order` 作 stock/ETF broker-paper path
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

Paper order lifecycle 必須先規格化為 `ibkr_paper_order_lifecycle_v1`：

- internal states / allowed transitions / terminal states
- submit / acknowledge / partial fill / fill / cancel / replace / reject / inactive
- local id / broker order id / execution id / commission report id / idempotency key
- restart recovery and stale state policy
- `STATE_UNKNOWN -> MANUAL_REVIEW_REQUIRED`
- typed denial reasons：lane disabled、broker disabled、live reserved、market closed、
  instrument blocked、cost model missing、universe mismatch、credential unavailable、
  connector unavailable、authorization invalid

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

Python connector 負面約束：

- 不得暴露直接 broker `place_order` / `cancel_order` / `replace_order` 方法。
- 若未來需要 order rehearsal，Python 只能作 Rust-owned IPC 的 thin caller，
  不能持有 broker order truth 或自行重試 broker write。
- 需要 grep/static tests 防止 Python route 直接調用 broker write API。

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
- Daily scorecard 只能是 derived artifact；atomic facts 才是證據 source of truth。
- Schema 必須包含 instrument identity、universe version、corporate actions、
  market-data provenance、FX/cash ledger、cost model version、benchmark version、
  paper-vs-shadow reconciliation。

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
| `OPENCLAW_ASSET_LANE_DEFAULT` | `crypto_perp` | 登錄後默認 lane |
| `OPENCLAW_STOCK_ETF_SHADOW_ONLY` | `1` | 初期禁止 paper order，僅 shadow |

不設 functional `OPENCLAW_IBKR_LIVE_ENABLED`。若為 GUI 顯示需要保留 live status，
應命名為 reserved/denied 狀態，且任何 order path 讀到 live intent 都必須 typed-deny。

Secret slot：

```text
$OPENCLAW_SECRETS_DIR/external/ibkr/readonly/
$OPENCLAW_SECRETS_DIR/external/ibkr/paper/
$OPENCLAW_SECRETS_DIR/external/ibkr/live/        # 不創建；若有 credential material，healthcheck FAIL
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

Phase 0 必須補充：

- exact IBKR API baseline：TWS API / IB Gateway / Client Portal Web API 只能先選一個。
- broker-reported paper attestation：下單前必須證明 session/account 是 paper，
  且 account fingerprint、host/port、environment 全部匹配。
- secret contract：exact filenames、chmod 700/600、fingerprint、rotation、TTL、
  no-env-fallback、redaction rules。
- non-Bybit API allowlist：method/action/transport/rate-limit/raw artifact policy。
- feature flag matrix：所有組合對 allowed action、UI state、route response、
  Rust authority result 的預期。

## 5. GUI 更改

### 5.1 登錄後 lane selector

登錄成功後第一屏進入 asset lane selector：

- `Crypto Perps / Bybit`
- `Stock & ETF Cash / IBKR Paper`
- `CFD Margin / Disabled`

選擇後進入同一 Control Console，但左側/頂部必須有不可忽略的 lane badge。
所有 tabs 的資料查詢都必須帶 `asset_lane`。

GUI lane selector 只可作 query/filter state。任何 effect-capable operation 都必須
由 server/Rust 使用簽名 envelope 重新驗證 `asset_lane`、broker、environment、
risk config、authorization、Decision Lease、Guardian。localStorage、query param、
hidden form field 均不得授權交易。

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
- `stock_etf_evidence_clock_v1` manifest 完成並帶 hash
- benchmark version frozen
- strategy hypothesis hash frozen
- corporate-action / FX / fee source as-of frozen
- paper-vs-shadow divergence thresholds frozen

### 6.1 初始 universe

建議只開兩組：

- `US_LARGE_100_v1`：大市值、高成交量、窄 spread；避免 penny / low liquidity
- `US_SECTOR_ETF_11_v1` 或 `US_LIQUID_ETF_50_v1`：低頻/再平衡研究
- UCITS ETFs 作第二批；除非 PRIIPs/KID、TER、domicile、listing currency、
  withholding/dividend treatment 已有 source contract

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

- 最多 2-3 個 pre-registered hypotheses
- 每個 hypothesis 必須有 alpha source、half-life、turnover target、benchmark、
  parameter grid、K count、rejection rule
- daily/weekly momentum、sector rotation、ETF trend/risk-off rotation 可作第一批候選
- earnings drift、opening/closing auction behavior 先 research-only，不進第一輪
  profitability verdict，除非另補事件/auction data contract

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
- independent observation count by date/symbol/sector cluster
- benchmark alpha / beta / tracking error / information ratio
- cost-edge ratio
- PSR/DSR 或等價 deflated metric
- concentration by symbol/sector/event/week

Promotion-like 判斷需要：

- lower confidence bound for after-cost benchmark excess > 0 under conservative cost
- benchmark excess return > 0 against pre-registered matched benchmark
- conservative/punitive fill model 下仍 > 0
- cost-edge ratio 不得過高；若執行成本吃掉 gross edge 的主要部分，不能判定 positive
- 不由單一 event / 單一 symbol 驅動
- 標記 bull-heavy / regime-heavy / stale-window
- 至少滿足 pre-registered independent sample threshold；原始 100+ trade rows
  不等於 100+ independent observations
- walk-forward / bootstrap 只能量化不確定性，不能補出不存在的獨立樣本

結果標籤：

- `engineering_ready`
- `research_promising`
- `profitability_feasible`
- `insufficient_evidence`
- `execution_model_invalid`
- `kill`

6-8 週窗口默認只可作 engineering shakedown + preliminary feasibility screen。
低頻策略若樣本不足，只能輸出 `research_promising` 或 `insufficient_evidence`，
不能輸出 durable-alpha proof。

## 7. 開發階段與派工

### Phase 0: Governance unlock / ADR

目標：允許 `stock_etf_cash` paper/shadow research lane，但不允許 live。

工作：

- 新 ADR：IBKR stock/ETF paper/shadow lane scope
- 明確 amend `ADR-0006` 的只讀/紙面例外，不改 live execution
- 擴充 operator decision matrix：decision、default conservative answer、owner、
  artifact、gated phase、revisit condition
- 定義 non-Bybit API call policy
- 定義 per-lane authorization schema
- 定義 IBKR API/session baseline
- 定義 `asset_lane_taxonomy_v1`
- 定義 `broker_capability_registry_v1` / operation authority matrix
- 定義 `non_bybit_api_allowlist_v1`
- 定義 `ibkr_api_session_topology_v1`
- 定義 `ibkr_session_attestation_v1`
- 定義 `feature_flag_secret_auth_matrix_v1`
- 定義 `lane_scoped_ipc_v1`
- 定義 `stock_etf_evidence_clock_v1`
- 定義 `ibkr_paper_order_lifecycle_v1`
- 定義 `broker_lifecycle_event_log_v1`
- 定義 `stock_etf_db_evidence_ddl_v1`
- 定義 `stock_market_data_provenance_v1`
- 定義 `broker_account_portfolio_cash_ledger_v1`
- 定義 `cost_model_version_v1`
- 定義 `benchmark_versions_v1`
- 定義 `stock_shadow_fill_model_v1`
- 定義 `gui_lane_contract_v1`
- 定義 `stock_etf_storage_capacity_v1`
- 定義 `stock_etf_kill_switch_and_disable_cleanup_runbook_v1`
- 定義 `stock_etf_release_packet_v1`
- 定義 `tiny_live_adr_eligibility_v1`，僅作未來是否可討論 tiny-live ADR 的門檻；
  不授權 live/tiny-live
- review chain：`PM -> CC -> FA -> PA -> E3 -> E5 -> QC -> MIT -> QA -> PM`
  - CC：16 根原則 / Bybit-only hard-boundary amend 審查
  - FA/PA：功能邊界與技術拆分
  - E3：IBKR secrets/API/redaction/security posture
  - E5：簡化 / storage-capacity / 技術債風險
  - QC/MIT：6-8 週 paper/shadow evidence 設計與統計可信度
  - QA：release packet / E2-E4-QA gate matrix / rollback-disable 驗收

驗收：

- ADR/AMD accepted，且 operator approval 落入治理文檔；chat-only approval 不生效
- 上述 Phase 0 spec packet 全部落文檔，並通過 CC/FA/PA/E3/E5/QC/MIT/QA closeout
- `CLAUDE.md` / `.codex/MEMORY.md` 是否需要同步由 PM 判斷；未接受前不改
- `TODO.md` active implementation row 只能在 Phase 0 通過後新增
- 不允許 chat-only approval 代替 ADR/AMD；operator approval 必須落入治理文檔

### Phase 1: Type / config / schema foundation

目標：只實作已接受 Phase 0 spec packet 中的 type/config/schema/IPC
foundation。Phase 1 不得包含未決設計，不得新增 IBKR connector，不得建立
secret slot，不得外部呼叫 IBKR。

對抗性審查後拆成：

- Phase 1A：Rust type reservation + denial tests only
- Phase 1B：flag/readiness parser + status contract，全部 default OFF
- Phase 1C：DDL/migration source implementation only from accepted
  `stock_etf_db_evidence_ddl_v1`；apply 前必須 Linux PG dry-run + double apply
- Phase 1D：lane-scoped Rust IPC/order-lifecycle fixture implementation；不接 IBKR

工作：

- Rust type reservation
- config files
- DB migration design
- migration Linux dry-run packet
- fixture-based tests

驗收：

- Mac Rust/Python focused tests pass
- E2 review confirms no catch-all broker/lane enum、no live/CFD/margin/short/options route
- E4 focused regression confirms existing Bybit/crypto IPC/routes/risk/Decision Lease unchanged
- migration design ready；若 apply，必須 Linux PG dry-run + double apply
- all flags default OFF；`crypto_perp` remains default
- no runtime mutation

### Phase 2: IBKR read-only + paper connector

目標：建立可測試、可重建、fail-closed 的 IBKR paper 接口。

Phase 2 不得啟動，除非 `phase2_ibkr_external_surface_gate_v1` PASS。首次
IBKR read-only healthcheck 也算非 Bybit external contact；在 accepted ADR/AMD、
API baseline、runtime topology、secret slot contract、API allowlist、redaction
suite、rate limits、audit event 與 live-slot absent/empty proof 全部通過前不得呼叫。

工作：

- IBKR read-only account snapshot
- IBKR paper orders/fills import
- paper healthcheck
- redaction / secret handling
- paper-only order lifecycle rehearsal

驗收：

- `phase2_ibkr_external_surface_gate_v1` immutable manifest PASS
- `ibkr_session_attestation_v1` proves paper/read-only environment, account fingerprint,
  host/port/process identity, secret fingerprint, data tier, expiry
- paper account snapshot 可重建
- paper orders/fills 帶 broker ids
- secrets 不出現在 argv/log
- Python no-write AST/grep/route tests pass；generic authenticated write helper 也不得繞過
- fill import idempotency / duplicate / stale unknown-state tests pass
- live path compile/runtime fail-closed

### Phase 3: Stock shadow collector + scorecard

目標：每日產出 after-cost evidence。

Phase 3 不得啟動，除非 market-data vendor/tier、PIT universe、corporate-action
adjustment set、FX/cost model、benchmark、storage/capacity、retention、paper-vs-shadow
reconciliation、statistical validation design 均已 machine-checkable。

工作：

- universe builder
- market data ingestion
- conservative fill model
- cost model
- benchmark comparator
- daily scorecard writer

驗收：

- `stock_etf_evidence_clock_v1` day-count checker outputs PASS/FAIL/QUARANTINED
- 5 個交易日穩定跑通，且每一天都有 calendar-aware coverage、symbol completeness、
  latency/DQ、quarantine manifest
- scorecard row 可追溯到 signal、quote/bar、cost model、instrument identity
- paper fill 與 shadow fill 分表/分標記
- scorecard can be regenerated from atomic facts and input hashes

### Phase 4: GUI lane selector + stock views

目標：operator 能在 GUI 上清楚區分 crypto 與 stock/ETF。

第一個 GUI slice 應是 lane badge/readiness page，而不是立即把 login-success
selector 作為主流程。只有後端 Interface 與 fail-closed gates 穩定後才做完整
lane selector。

工作順序：

- Phase 4A：default `crypto_perp` lane badge / readiness / status page
- Phase 4B：stock read-only overview / universe / shadow / evidence / paper /
  reconciliation / account / scorecard / launch-release status views
- Phase 4C：完整 login-success lane selector；只能在 route/cache/auth negative tests PASS 後討論
- disabled CFD surface first slice 不顯示，只保留 fail-closed status / denial tests

驗收：

- GUI JS `node --check` 或更強驗證
- desktop/mobile smoke screenshot
- route/cache/auth partition tests prove client-side lane state is untrusted
- localStorage、query param、hidden field 均不得授權交易
- crypto tabs / routes / Decision Lease / risk / scorecard 行為不回歸
- stock live 清楚 fail-closed

### Phase 5: 6-8 週 paper/shadow evidence collection

目標：完成 engineering shakedown + preliminary feasibility screen。Phase 5
不得被描述為 durable-alpha proof 或 production readiness；positive point estimate
不得自動觸發 tiny-live。

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
- verdict labels machine-checkable：`engineering_ready`、`research_promising`、
  `profitability_feasible`、`insufficient_evidence`、`execution_model_invalid`、`kill`
- live 仍禁止；如要 tiny live probe，另開 ADR/authorization/spec，且必須先通過
  `tiny_live_adr_eligibility_v1`

## 8. 預估工期

不含 6-8 週 evidence clock 的工程前置：

| 範圍 | 樂觀 | 中位 | 悲觀 |
|---|---:|---:|---:|
| ADR / interface / release spec / governance | 1 週 | 2 週 | 3 週 |
| types/config/schema | 1 週 | 1.5 週 | 2.5 週 |
| IBKR paper/read-only connector | 1 週 | 2 週 | 3 週 |
| shadow + scorecard | 1 週 | 2 週 | 3 週 |
| GUI badge/readiness + stock views | 1 週 | 1.5 週 | 2.5 週 |
| integration hardening | 3 天 | 1 週 | 2 週 |

可並行後的整體前置估算：

- 樂觀：3-4 週
- 中位：5-7 週
- 悲觀：8-10 週

二輪審查後，這些估算只能表示 paper/shadow engineering readiness 的可能窗口。
它們不是 fully-online、tiny-live 或盈利可行性承諾。證據收集另算 6-8 週，
且只有在 Phase 3/4 與 `stock_etf_evidence_clock_v1` checker 穩定後開始計時。

## 9. 首批 acceptance criteria

進入 6-8 週 evidence collection 前：

- `stock_etf_cash` lane 只能 paper/shadow。
- IBKR live flag 永遠 fail-closed。
- 所有 IBKR secrets 使用 external secret slot。
- GUI lane state 不授權任何交易；首批只做 badge/readiness/status。
- Paper order path 經 Rust authority，不經 Python 直接下單。
- 每筆 paper/shadow fill 可重建成本。
- Cost model version frozen。
- Universe version frozen。
- Benchmark version frozen。
- 日報可追溯至 append-only evidence。
- `stock_etf_release_packet_v1` assembled：ADR/spec、role reports、E2/E4/QA
  logs、manifest hashes、PG dry-run logs、redaction fixtures、GUI screenshots、
  DQ manifests、scorecard regeneration outputs。

6-8 週完成後：

- 產出 after-cost evidence report。
- 明確判斷是否只有 `engineering_ready` / `research_promising` /
  `insufficient_evidence`，還是達到可討論 `tiny_live_adr_eligibility_v1`。
- 若沒有 after-cost edge，關閉或降級 stock/ETF lane。
- 若有 edge，只允許開新 ADR 討論 tiny-live，不得從 paper 自動升級。

## 10. 開工前需要 operator 決定

1. 是否接受 `stock_etf_cash` paper/shadow lane 方向。
2. 是否以 IBKR 作第一 broker baseline。
3. 首個 IBKR API baseline 是 TWS API、IB Gateway、Client Portal Web API，
   還是先開 no-order spike。
4. IBKR paper account jurisdiction / account fingerprint / market-data entitlement
   policy 由誰確認。
5. 第一批 universe owner、benchmark owner、base currency、data-cost ceiling。
6. 第一批 risk / loss caps、shadow-only lift criteria、是否允許 Phase 2 paper
   order rehearsal。
7. 每週 PM/QC/MIT review format 與 operator brief format。
8. 是否允許 E3/CC/FA/PA/QC/MIT/QA 啟動 ADR 變更評審。
9. 是否把 eToro/Saxo 作為 Phase 5 之後的 challenger，而不是第一批同時接。
10. 是否接受工程前置中位 5-7 週 + evidence 6-8 週的總周期，且該周期
    不保證 profitability/tiny-live readiness。

PM 建議：先批准 Phase 0。Phase 0 只產出 ADR/AMD + named contract packet，
不寫 runtime，不觸碰 IBKR API，不改 live 邊界。

## 11. 對抗性審查後硬 blocker

2026-06-29 PM 派發 `CC/FA/PA/E3/QC/MIT` 六角色對抗性審查。共識如下：

- 方向有效：`stock_etf_cash` 作為 IBKR paper/shadow research lane 是值得探索的。
- 工程方案尚未 implementation-ready。
- 唯一可立即前進的是 Phase 0 ADR/spec。
- 所有 Phase 1+、IBKR API、secret slot、paper order、GUI runtime activation、
  evidence clock 均 BLOCKED。

Phase 1 前必須完成：

1. 接受的新 ADR/AMD，明確只批准 `stock_etf_cash` read-only/paper/shadow
   research；不批准 IBKR live、margin、short、options、CFD、transfer。
2. IBKR API baseline：TWS API / IB Gateway / Client Portal Web API 三者選一，
   並定義 runtime process owner、host/port、session lifecycle、market data tier。
3. Rust lane-scoped IPC/order Interface；不得重用現有 Bybit/Paper
   `submit_paper_order`。
4. `ibkr_paper_order_lifecycle_v1` 狀態機與 reconciliation contract。
5. DB evidence contract：instrument identity、PIT universe、corporate actions、
   market data provenance、FX/cash ledger、cost model、benchmark、paper/shadow links。
6. Feature flag matrix 和 secret invariant matrix，包含 live slot absent/empty
   enforcement。
7. Python connector no-write structural guard。
8. GUI lane selector display/filter-only contract。

Phase 3 / evidence clock 前必須完成：

1. `stock_etf_evidence_clock_v1` manifest。
2. Frozen universe hash、benchmark hash、cost model hash、strategy hypothesis hash。
3. Corporate-action / FX / fee / tax source as-of records。
4. Pre-registered sample-size / independent observation rules。
5. Paper-vs-shadow divergence thresholds and quarantine action。
6. Strategy-specific benchmark and matched-control definitions。
7. Regime / breadth / freshness / survivorship / execution-realism labels per ADR-0047。
8. Scorecard formula appendix with CI / PSR / DSR or equivalent deflation，並以
   `stock_etf_scorecard_verdict_v1` 封存正面或負面 scorecard verdict；此契約不得
   授權 IBKR contact、scorecard writer、tiny-live/live 或 Bybit gate 變更。

PM 判定：第一輪後方案「有效但未可開工」。有效性只限於 Phase 0。

## 12. 第二輪對抗性審查後追加 gate

2026-06-29 PM 再派 `CC/FA/PA/E3/E5/QC/MIT/QA` 八角色二輪審查。共識如下：

- 未發現可讓我們跳過 Phase 0 的捷徑。
- 不能確認「無遺漏」或「按排程後完整上線」。
- 不能批准 Phase 1 conditional implementation。
- Phase 0 必須前移所有 interface / data / security / GUI / QA release contract。
- 任何 positive paper/shadow 結果也只可能開啟新的 tiny-live ADR 討論，不是 live readiness。

二輪角色結果：

| Role | Gate | Finding summary |
|---|---|---|
| CC | APPROVE_PHASE0_ONLY | Phase 1+、IBKR 外部接觸、GUI runtime、evidence clock、future tiny-live 仍需硬 gate。 |
| FA | APPROVE_PHASE0_ONLY | 不能確認無遺漏；operator workflows、disabled/error/recovery/export、crypto regression 不足。 |
| PA | APPROVE_PHASE0_ONLY | Phase 0/1 邊界仍會讓 E1 發明 Interface，需把 specs 前移。 |
| E3 | APPROVE_PHASE0_ONLY | 首次 IBKR healthcheck 前也需 external-surface gate；paper/live/session/account attestation 未 executable。 |
| E5 | APPROVE_PHASE0_ONLY | 淺模塊、GUI selector churn、storage/retention/capacity、disable cleanup 是主要技術債風險。 |
| QC | APPROVE_PHASE0_ONLY | 6-8 週只能 screening；`profitability_feasible` 與 tiny-live wording 需分離 gate。 |
| MIT | APPROVE_PHASE0_ONLY | Phase 1 schema 與 Phase 3 collector 仍 blocked；DDL/event sourcing/provenance/cash-FX-cost-benchmark contract 未 machine-checkable。 |
| QA | APPROVE_PHASE0_ONLY | 缺 per-phase E2/E4/QA gate matrix、release packet、rollback/disable、artifact manifest。 |

Phase 0 追加 mandatory outputs：

1. `broker_capability_registry_v1`：operation taxonomy、allowed lanes、required auth、
   Decision Lease / Guardian / attestation、rate limit、audit event、typed denial reason。
2. `phase2_ibkr_external_surface_gate_v1`：首次 read-only healthcheck 前必須 PASS。
3. `stock_etf_db_evidence_ddl_v1`：DDL/ERD、PK/FK/natural keys、CHECK、index、
   hypertable、retention、Guard A/B/C、Linux PG dry-run/double-apply plan。
4. `audit.asset_lane_events_v1` / immutable event references：scorecard 永遠是 derived artifact。
5. `stock_etf_storage_capacity_v1`：universe size、row volume、retention、compression、
   index budget、query SLO、raw payload hash retention。
6. `gui_lane_contract_v1`：badge/readiness-first、client lane untrusted、exact
   display-only GET status endpoints、route/cache/auth negative tests、crypto
   regression、disabled CFD/live no-write tests。
7. `stock_etf_release_packet_v1`：role reports、commands、hashes、screenshots、DQ manifests、
   redaction fixtures、PG logs、scorecard regeneration outputs。
8. `stock_etf_kill_switch_and_disable_cleanup_runbook_v1`：lane disable、collector stop、
   secret absence proof、GUI hide, evidence archive, DB forward-only retention。
9. `tiny_live_adr_eligibility_v1`：separate from scorecard；paper/shadow positive cannot
   auto-promote to live/tiny-live。

新的 PM 判定：工程方向仍有效，但「一勞永逸」的正確做法不是提前寫 connector，
而是先把上述 contract 寫成可審核、可測試、可關閉的 Phase 0 packet。未完成前，
任何 Phase 1+、IBKR API/healthcheck、secret slot、paper order、GUI runtime activation、
evidence clock、tiny-live/live 討論均 BLOCKED。

## 13. 第三輪 launch-certification 結論

2026-06-29 PM 以第二輪 hard-gated 版本為基準，再派
`CC/FA/PA/E3/E5/QC/MIT/QA` 八角色做第三輪 launch-certification。審查問題被
嚴格限定為：在所有 Phase 0 named contract packet 已接受、Phase 1-5 所有 gate
均按本計劃通過且有 immutable artifacts 的假設下，是否仍存在阻止
`stock_etf_cash` paper/shadow lane 完整上線的 missing launch gate。

第三輪角色結果：

| Role | Certification | Findings | Scope |
|---|---|---:|---|
| CC | CERTIFIABLE_IF_GATES_PASS | 0 | paper_shadow_only |
| FA | CERTIFIABLE_IF_GATES_PASS | 0 | paper_shadow_only |
| PA | CERTIFIABLE_IF_GATES_PASS | 0 | paper_shadow_only |
| E3 | CERTIFIABLE_IF_GATES_PASS | 0 | paper_shadow_only |
| E5 | CERTIFIABLE_IF_GATES_PASS | 0 | paper_shadow_only |
| QC | CERTIFIABLE_IF_GATES_PASS | 0 | paper_shadow_only |
| MIT | CERTIFIABLE_IF_GATES_PASS | 0 | paper_shadow_only |
| QA | CERTIFIABLE_IF_GATES_PASS | 0 | paper_shadow_only |

PM 判定：

- 可以使用的簽核語句：
  `PAPER_SHADOW_LAUNCH_CERTIFIABLE_IF_ALL_GATES_PASS`。
- `paper_shadow_online_complete` 定義為：Phase 0 ADR/AMD + named contract
  packet accepted；Phase 1 type/config/schema/IPC foundation 通過；Phase 2
  external-surface + read-only/paper lifecycle gates 通過；Phase 3 collector /
  DQ / scorecard / evidence clock 通過；Phase 4 GUI badge/readiness/views/negative
  tests 通過；Phase 5 release packet、kill/disable cleanup、operator runbook 與
  engineering shakedown evidence 全部通過。
- 在上述條件全部成立後，第三輪未發現額外 minimum launch gate；可以簽核
  `stock_etf_cash` paper/shadow lane 按計劃完整上線。
- 當前狀態仍不是 launch-ready：Phase 0 packet 尚未生成與接受，Phase 1-5
  artifact 尚不存在，IBKR API/secret/paper order/GUI runtime/evidence clock 仍 blocked。
- 本結論不等於絕對「無遺漏」保證；它只是在已定義 scope 與 all-gates-pass
  假設下的八角色 launch-certification。
- 本結論明確排除 IBKR live、tiny-live、margin、short、options、CFD、資金劃轉、
  transfer/account-management writes、盈利保證、durable alpha proof，以及任何自動
  promotion beyond paper/shadow。
