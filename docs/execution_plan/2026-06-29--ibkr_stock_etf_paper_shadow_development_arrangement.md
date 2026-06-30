# IBKR Stock/ETF Paper + Shadow Evidence Lane 開發安排

日期：2026-06-29
狀態：ADR-0048 / AMD / Phase0 named contracts 已 source-materialized；Phase 1-5 source/status/display hardening 進行中；不授權任何非 Bybit 實盤交易
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

2026-06-30 目前狀態：Phase 0 ADR/AMD/named contract packet 已在 source 中落地；
Phase 1-5 多個 source/status/display-only checkpoints 已完成並逐一推送。這仍不
代表 runtime launch：IBKR API contact、secret slot、connector runtime、paper
order、fill import、DB apply、evidence clock、scorecard writer、paper-shadow launch、
tiny-live/live 全部仍須按 gate 另行通過。

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
- Phase 4B：stock read-only overview / data foundation / universe / shadow / evidence / paper /
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
   display-only GET status endpoints（包含 data foundation、account、evidence、
   universe、shadow、paper、reconciliation、scorecard、launch）、route/cache/auth negative tests、crypto
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

## 14. 2026-06-30 PM session source checkpoint：Policy / Capability Status

本 session 依第三輪 PM 簽核語義繼續執行，但仍限定於 source-only /
display-only gate hardening；未啟動 IBKR contact、secret、connector runtime、
paper order、evidence clock、DB apply 或 Linux runtime sync。

新增 checkpoint：

- Rust IPC fixture 新增 `stock_etf.get_policy_status`，輸出
  `phase2_policy_status_source_fixture`，只反映 `stock_etf_risk_policy_v1` 與
  `broker_capability_registry_v1` 的 blocked/default source posture。
- FastAPI 新增 authenticated/no-store
  `GET /api/v1/stock-etf/policy-status`，只呼叫上述 IPC method 且 params 為 `{}`；
  normalizer fail-closes IPC unavailable，並把 risk/capability/contact/secret/order/DB/
  Bybit reuse drift 轉為 `contract_violation_blocked`。
- GUI 新增 `Policy Gate` metric 與 `Policy / Capability Status` panel，只顯示
  risk/capability blocker、required gate posture 與 side-effect denial；未新增表單、
  POST、broker write、order widget 或 browser-storage authority。
- `lane_scoped_ipc_v1` 新增 `GetPolicyStatus` display-only/non-effect-capable method；
  `gui_lane_contract_v1` 新增 exact GET-only
  `/api/v1/stock-etf/policy-status` endpoint。

驗證：

- Python route/normalizer/test `py_compile`：PASS。
- Node inline parser for `tab-stock-etf.html`：PASS（2 inline scripts）。
- Focused FastAPI/static pytest：`18 passed`。
- Full Stock/ETF FastAPI/static pytest：`72 passed`。
- Rust format checks：PASS（含 `lib.rs` with `skip_children=true`）。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_engine stock_etf`：
  `17 passed` focused Stock/ETF tests。
- GUI/lane IPC acceptance：`17 passed`。
- Full `cargo test --manifest-path rust/Cargo.toml -p openclaw_types`：
  `35` unit/golden + `206` integration/acceptance + `0` doc-tests。

PM 邊界不變：此 checkpoint 不批准 IBKR contact、secret access/creation、
connector runtime、contract-details request、account snapshot、paper order rehearsal/submit、
paper fill import、evidence clock、scorecard writer、DB apply、GUI lane authority、
Phase 2/3/5 start、tiny-live、live 或任何 Bybit behavior change。

## 15. 2026-06-30 PM session source checkpoint：Authorization Status

本 session 繼續按第三輪 PM 簽核語義推進，但仍停留在 source-only /
display-only authorization gate hardening。此 checkpoint 不讀取 secret、不建立
secret slot、不呼叫 IBKR、不啟動 connector runtime，也不給 GUI 或 Python 任何
paper-order 權限。

新增 checkpoint：

- Rust IPC fixture 新增 `stock_etf.get_authorization_status`，輸出
  `phase2_authorization_status_source_fixture`，只反映
  `feature_flag_secret_auth_matrix_v1`、`ibkr_secret_slot_contract_v1`、
  `phase2_ibkr_external_surface_gate_v1`、`ibkr_session_attestation_v1` 與
  authorization envelope 的 blocked/default source posture。
- FastAPI 新增 authenticated/no-store
  `GET /api/v1/stock-etf/authorization-status`，只呼叫上述 IPC method 且 params
  為 `{}`；normalizer fail-closes IPC unavailable、拒絕 client-supplied state，
  並把 authorization/contact/secret/session/envelope/order/DB/Bybit reuse drift
  轉為 `contract_violation_blocked`。
- GUI 新增 `Authorization Gate` metric 與 `Authorization Status` panel，只顯示
  auth matrix、secret-slot、Phase 2 gate artifact、session attestation、authorization
  envelope 與 blockers；未新增表單、POST、broker write、order widget 或
  browser-storage authority。
- `lane_scoped_ipc_v1` 新增 `GetAuthorizationStatus`
  display-only/non-effect-capable method；`gui_lane_contract_v1` 新增 exact
  GET-only `/api/v1/stock-etf/authorization-status` endpoint。

驗證：

- Python route/normalizer/test `py_compile`：PASS。
- Node inline parser for `tab-stock-etf.html`：PASS（7 inline scripts）。
- Full Stock/ETF FastAPI/static pytest：`77 passed`。
- Rust format checks：PASS（含 `lib.rs` with `skip_children=true`）。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_engine stock_etf`：
  `18 passed` focused Stock/ETF tests。
- GUI/lane IPC acceptance：`17 passed`。
- Full `cargo test --manifest-path rust/Cargo.toml -p openclaw_types`：
  `35` unit/golden + `206` integration/acceptance + `0` doc-tests。
- `cargo check --manifest-path rust/Cargo.toml --workspace`：PASS。

PM 邊界不變：此 checkpoint 不批准 IBKR contact、secret access/creation、
connector runtime、contract-details request、account snapshot、risk runtime、
paper-order rehearsal/submit、paper fill import、evidence clock、scorecard writer、
DB apply、GUI lane authority、Phase 2/3/5 start、tiny-live、live 或任何 Bybit
behavior change。

## 16. 2026-06-30 PM session hygiene checkpoint：Stock/ETF GUI split

Authorization Status checkpoint 後，`tab-stock-etf.html` 累積到 2225 行，超過
repo 2000 行硬上限。PM 先做純 GUI 拆檔 hygiene，再繼續新增任何 surface。

已完成：

- 將 Stock/ETF tab 的大段 inline JS 原樣抽出為
  `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/tab-stock-etf.js`。
- `tab-stock-etf.html` 只保留 DOM/CSS 與外部 JS 引用；
  `tab-stock-etf.html` 降至 341 行，`tab-stock-etf.js` 為 1883 行，兩者均低於
  2000 行硬上限。
- Static no-write guard 改為同時掃描 HTML+JS bundle：endpoint presence 在 bundle
  層檢查，forbidden write snippets 逐檔檢查。

驗證：

- Python route/static guard tests `py_compile`：PASS。
- `node --check tab-stock-etf.js`：PASS。
- HTML inline parser：PASS（1 inline script）。
- Full Stock/ETF FastAPI/static pytest：`77 passed`。
- `git diff --check`：PASS。

PM 邊界不變：此 checkpoint 不新增 endpoint、不改 IPC/contract、不呼叫 IBKR、
不讀 secret、不啟動 connector/runtime、不送 paper order、不做 DB apply、不做 Linux
runtime sync/restart，也不改變 Bybit behavior。

## 17. 2026-06-30 PM session source checkpoint：Disable Cleanup Status

本 session 繼續按第三輪 PM 簽核語義推進，但仍停留在 source-only /
display-only disable-cleanup runbook visibility。此 checkpoint 不執行 collector stop、
GUI hide、secret absence proof、archive、DB cleanup，不啟動 Phase 5，也不授權
paper/shadow launch。

新增 checkpoint：

- Rust IPC fixture 新增 `stock_etf.get_disable_cleanup_status`，輸出
  `phase5_disable_cleanup_status_source_fixture`。它只展示
  `stock_etf_kill_switch_and_disable_cleanup_runbook_v1` 的 source-ready runbook
  shape 與 runtime-blocked posture；top-level collector/gui/archive/DB cleanup
  request 均為 false。
- Rust dispatch/method registry 將該 method 註冊為 readonly、slot none，並保持不在
  Bybit live-write token surface；`lane_scoped_ipc_v1` 新增
  `GetDisableCleanupStatus` display-only/non-effect-capable method。
- FastAPI 新增 authenticated/no-store
  `GET /api/v1/stock-etf/disable-cleanup-status`，只呼叫上述 IPC method 且 params
  為 `{}`；normalizer fail-closes IPC unavailable、拒絕 client-supplied cleanup/
  launch/live state，並把 contact/secret/order/destructive cleanup/DB/Bybit reuse drift
  轉為 `contract_violation_blocked`。
- GUI 新增 `Disable Cleanup` metric 與 `Disable / Cleanup Status` panel。為維持
  repo 2000 行硬上限，runbook render hook 放入獨立
  `tab-stock-etf-disable-cleanup.js`；主 `tab-stock-etf.js` 只新增 GET 與 render hook。
- `gui_lane_contract_v1` 新增 exact GET-only
  `/api/v1/stock-etf/disable-cleanup-status` endpoint；blocked template 同步加入
  disabled/default 欄位。

驗證：

- Python route/normalizer/test `py_compile`：PASS。
- Full Stock/ETF FastAPI/static pytest：`81 passed`。
- `node --check tab-stock-etf.js` 與 `tab-stock-etf-disable-cleanup.js`：PASS。
- HTML inline parser：PASS（1 inline script）。
- GUI line caps：`tab-stock-etf.html` 359 行、`tab-stock-etf.js` 1895 行、
  `tab-stock-etf-disable-cleanup.js` 132 行。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_engine stock_etf`：
  `19 passed` focused Stock/ETF tests。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types stock_etf`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不讀/建 secret、不啟動 connector runtime、
不執行 collector stop、GUI hide、archive、DB cleanup、DB apply、paper order、
paper fill import、evidence clock、scorecard writer、Linux runtime sync/restart、
paper-shadow launch、Phase 2/3/5 start、tiny-live、live 或任何 Bybit behavior change。

## 18. 2026-06-30 PM session source checkpoint：Release Packet Status

本 session 繼續按第三輪 PM 簽核語義推進，但仍停留在 source-only /
display-only release packet visibility。此 checkpoint 不物化 release packet、不啟動
Phase 5、不啟動 paper/shadow launch，也不授權任何 runtime writer。

新增 checkpoint：

- Rust IPC fixture 新增 `stock_etf.get_release_packet_status`，輸出
  `phase5_release_packet_status_source_fixture`。它只展示
  `stock_etf_release_packet_v1` accepted source fixture 與
  `stock_etf_kill_switch_and_disable_cleanup_runbook_v1` proof 摘要；top-level
  Phase 3/5、paper-shadow launch、connector、scorecard writer、DB、evidence clock、
  order、secret、IBKR contact、Bybit reuse 欄位均為 false。
- Rust dispatch/method registry 將該 method 註冊為 readonly、slot none，並保持不在
  Bybit live-write token surface；`lane_scoped_ipc_v1` 新增
  `GetReleasePacketStatus` display-only/non-effect-capable method。
- FastAPI 新增 authenticated/no-store
  `GET /api/v1/stock-etf/release-packet-status`，只呼叫上述 IPC method 且 params
  為 `{}`；normalizer fail-closes IPC unavailable、拒絕 client-supplied launch/live
  state，並把 release packet、contact、secret、order、DB、writer、evidence clock、
  Bybit reuse drift 轉為 `contract_violation_blocked`。
- GUI 新增 `Release Packet` metric 與 `Release Packet Status` panel。為維持
  repo 2000 行硬上限，release packet render hook 放入獨立
  `tab-stock-etf-release-packet.js`；主 `tab-stock-etf.js` 只新增 GET 與 render hook。
- `gui_lane_contract_v1` 新增 exact GET-only
  `/api/v1/stock-etf/release-packet-status` endpoint；blocked template 同步加入
  disabled/default 欄位。

驗證：

- Python route/normalizer/test `py_compile`：PASS。
- Full Stock/ETF FastAPI/static pytest：`85 passed`。
- `node --check tab-stock-etf.js`、`tab-stock-etf-release-packet.js` 與
  `tab-stock-etf-disable-cleanup.js`：PASS。
- HTML inline parser：PASS（1 inline script）。
- Rust format checks：PASS（含 `lib.rs` with `skip_children=true`）。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_engine stock_etf`：
  `20 passed` focused Stock/ETF tests。
- Full `cargo test --manifest-path rust/Cargo.toml -p openclaw_types`：PASS。
- `cargo check --manifest-path rust/Cargo.toml --workspace`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不讀/建 secret、不啟動 connector runtime、
不物化 release packet、不啟動 scorecard writer、不啟動 evidence clock、不做 DB apply、
不送 paper order、不匯入 fill、不做 Linux runtime sync/restart、不啟動 paper-shadow
launch、不啟動 Phase 2/3/5、不授權 tiny-live/live 或任何 Bybit behavior change。

## 19. 2026-06-30 PM session source checkpoint：Phase 0 Packet Status

本 session 繼續按第三輪 PM 簽核語義推進，但新增的是 Phase 0 named contract
packet 的 source-only / display-only visibility。此 checkpoint 只展示
`stock_etf_phase0_contract_packet_manifest_v1` accepted source manifest；不代表
Phase 1+ runtime 已啟動，也不授權 IBKR contact、secret slot、paper/shadow launch
或任何 writer。

新增 checkpoint：

- Rust IPC fixture 新增 `stock_etf.get_phase0_status`，輸出
  `phase0_contract_packet_status_source_fixture`。它只展示
  `StockEtfPhase0ContractPacketManifestV1::accepted_fixture()` 的 schema/status/
  scope/contract count、API baseline、global denials 與 phase unlock 語義；top-level
  Phase 1/2/3/4/5 runtime、paper-shadow launch、connector、scorecard writer、DB、
  evidence clock、order、secret、IBKR contact、Bybit reuse 欄位均為 false。
- Rust dispatch/method registry 將該 method 註冊為 readonly、slot none，並保持不在
  Bybit live-write token surface；`lane_scoped_ipc_v1` 新增
  `GetPhase0Status` display-only/non-effect-capable method。
- FastAPI 新增 authenticated/no-store
  `GET /api/v1/stock-etf/phase0-status`，只呼叫上述 IPC method 且 params 為 `{}`；
  normalizer fail-closes IPC unavailable、拒絕 client-supplied Phase 0/launch/live
  state，並把 manifest drift、runtime side-effect drift、IBKR contact、secret、order、
  DB、writer、evidence clock、Bybit reuse drift 轉為 `contract_violation_blocked`。
- GUI 新增 `Phase 0 Packet` metric 與 `Phase 0 Packet Status` panel。為維持
  repo 2000 行硬上限，Phase 0 render hook 放入獨立
  `tab-stock-etf-phase0.js`；主 `tab-stock-etf.js` 只新增 GET 與 render hook。
- `gui_lane_contract_v1` 新增 exact GET-only
  `/api/v1/stock-etf/phase0-status` endpoint；blocked template 同步加入
  disabled/default 欄位；Phase 0 named contract packet 的 GUI endpoint 清單同步更新。

驗證：

- Python route/normalizer/test `py_compile`：PASS。
- Full Stock/ETF FastAPI/static pytest：`89 passed`。
- `node --check tab-stock-etf.js`、`tab-stock-etf-phase0.js`、
  `tab-stock-etf-release-packet.js` 與 `tab-stock-etf-disable-cleanup.js`：PASS。
- HTML inline parser：PASS（1 inline script）。
- Rust format checks：PASS（含 `lib.rs` with `skip_children=true`）。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_engine stock_etf`：
  `21 passed` focused Stock/ETF tests。
- Full `cargo test --manifest-path rust/Cargo.toml -p openclaw_types`：
  `35` unit/golden + `206` integration/acceptance + `0` doc-tests。
- `cargo check --manifest-path rust/Cargo.toml --workspace`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不讀/建 secret、不啟動 connector runtime、
不啟動 Phase 1/2/3/4/5 runtime、不物化 release packet、不啟動 scorecard writer、
不啟動 evidence clock、不做 DB apply、不送 paper order、不匯入 fill、不做 Linux
runtime sync/restart、不啟動 paper-shadow launch、不授權 tiny-live/live 或任何 Bybit
behavior change。

## 20. 2026-06-30 PM session source checkpoint：DB Evidence DDL Source Audit

本 session 進入 Phase 1C 的 source DDL audit hardening，但仍只停留在
`stock_etf_db_evidence_ddl_v1.source_only.sql` 的 source-only validation。此
checkpoint 不把 draft 複製到 `sql/migrations/`，不執行 Postgres dry-run，不做 double
apply，也不表示任何 DB schema 已部署。

新增 checkpoint：

- Rust `openclaw_types` 新增 exported auditor
  `audit_stock_etf_db_evidence_source_sql`，直接檢查 source-only DDL draft。
- Auditor machine-checks：source-only banner、migration/apply denial、禁止
  destructive/migration-promotion SQL、required schemas/tables、Guard A、key table
  column declarations、natural keys、stock/IBKR/paper checks、live denial、
  synthetic shadow fill separation、raw artifact hash、append-only audit event table
  與 hot-path indexes。
- Acceptance tests 不再只做弱 substring 檢查；現在會讀取實際 source SQL 並驗證
  `accepted=true`、13 張 required table、至少 6 個 index，同時故意刪除 required
  column、刪除 synthetic shadow check、追加 `DROP TABLE` 來證明 contract drift 與
  migration promotion 都會被拒絕。
- 欄位檢查使用 column declaration pattern，避免欄名出現在同表 `UNIQUE(...)`
  constraint 時被誤判為欄位仍存在。

驗證：

- Rust format checks：PASS（`lib.rs` 使用 `skip_children=true` 避免 unrelated module
  traversal）。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types source_sql -- --nocapture`：
  focused source SQL audit `2 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test stock_etf_db_evidence_ddl_acceptance -- --nocapture`：
  DB evidence DDL acceptance `9 passed`。
- Full `cargo test --manifest-path rust/Cargo.toml -p openclaw_types`：
  `35` unit/golden + `207` integration/acceptance + `0` doc-tests。
- `cargo check --manifest-path rust/Cargo.toml --workspace`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不讀/建 secret、不啟動 connector runtime、
不做 DB migration/apply、不中繼 PG dry-run、不啟動 Phase 1/2/3/4/5 runtime、不啟動
scorecard writer、不啟動 evidence clock、不送 paper order、不匯入 fill、不做 Linux
runtime sync/restart、不啟動 paper-shadow launch、不授權 tiny-live/live 或任何 Bybit
behavior change。

## 21. 2026-06-30 PM session source checkpoint：DB Evidence DDL Source Contract Hardening

本 session 繼續 Phase 1C，但仍停留在 source-only DDL contract。上一個 checkpoint
讓 source SQL 有 auditor；本 checkpoint 補足計劃中要求但尚未 machine-check 的
FK、Guard B/C、scorecard lineage 與 hypertable/retention promotion plan。

新增 checkpoint：

- `stock_etf_db_evidence_ddl_v1.source_only.sql` 新增 Guard B type-sensitive
  checks，覆蓋 paper order/fill、shadow fill、scorecard JSON、audit event time/boolean
  欄位，避免既有 table shape drift 被 `CREATE TABLE IF NOT EXISTS` 靜默跳過。
- Source draft 新增 Guard C hot-path index drift check，使用 `pg_get_indexdef`
  驗 paper order、paper fill、shadow signals、scorecard、asset lane events indexes。
- Source draft 補 FK lineage：instrument listing/order/fill 指回
  `broker.instruments`，fill 指回 paper order，commission 指回 fill，shadow fill
  指回 signal；同時補 `research.stock_shadow_fills.broker/strategy_id`。
- `research.stock_etf_scorecard` 補 broker/environment、`cost_model_version`、
  `market_data_provenance_hash`、`corporate_actions_hash`、
  `fx_cash_ledger_hash`、`paper_shadow_reconciliation_hash`，讓 scorecard 仍是
  derived artifact，但可追溯到 atomic evidence source。
- Source draft 新增 TimescaleDB hypertable/retention promotion plan，但沒有執行
  `create_hypertable` 或 `add_retention_policy`；它明確要求未來 V### promotion 前
  必須先把所有被 promotion 的 table 改成 partition-safe primary/unique constraints。
- Rust auditor 新增 blockers：`GuardBBlockMissing`、`GuardCBlockMissing`、
  `MigrationDryRunPlanMissing`、`RequiredForeignKeyMissing`、
  `HypertableRetentionPlanMissing`，並追蹤 `foreign_key_count`。

驗證：

- Rust format checks：PASS（`lib.rs` 使用 `skip_children=true`）。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test stock_etf_db_evidence_ddl_acceptance -- --nocapture`：
  DB evidence DDL acceptance `10 passed`。
- Full `cargo test --manifest-path rust/Cargo.toml -p openclaw_types`：
  `35` unit/golden + `208` integration/acceptance + `0` doc-tests。
- `cargo check --manifest-path rust/Cargo.toml --workspace`：PASS。

PM 邊界不變：此 checkpoint 不把 source draft 複製到 `sql/migrations/`，不做 DB
migration/apply，不做 Postgres dry-run 或 double apply，不註冊 sqlx migration，不呼叫
IBKR、不讀/建 secret、不啟動 connector runtime、不啟動 Phase 1/2/3/4/5 runtime、不啟動
scorecard writer、不啟動 evidence clock、不送 paper order、不匯入 fill、不做 Linux
runtime sync/restart、不啟動 paper-shadow launch、不授權 tiny-live/live 或任何 Bybit
behavior change。

## 22. 2026-06-30 PM session source checkpoint：Paper IPC Request Shape Hardening

本 session 進入 Phase 1D 的 lane-scoped IPC/order-lifecycle fixture hardening，但仍是
source-only contract。此 checkpoint 不啟動 IPC server、不接 IBKR、不送 paper order、
不做 cancel/replace、不啟動 connector runtime，也不重用既有 Bybit
`submit_paper_order` path。

新增 checkpoint：

- `lane_scoped_ipc_v1` 將 `PreviewPaperOrder`、`SubmitPaperOrder`、
  `CancelPaperOrder`、`ReplacePaperOrder` 的 request fields 明確拆分；submit、
  cancel、replace 不再共用一個 generic `PAPER_EFFECT_FIELDS`。
- Preview/submit 現在 pin 住 account fingerprint hash、instrument identity、symbol、
  instrument kind、side、order type、quantity、`limit_price_policy`、time in force；
  submit 另 pin `order_local_id`、idempotency、session/scoped authorization/guardian/
  lifecycle/audit hashes。
- Cancel 現在只 pin 撤單 envelope：`order_local_id`、`broker_order_id`、
  `cancel_reason`、idempotency、lifecycle/capability/audit fields；它不要求 submit
  的 quantity/order_type/limit-price fields。
- Replace 現在 pin 改單 envelope：`order_local_id`、`broker_order_id`、instrument
  identity、symbol、side、`replacement_idempotency_key`、`replacement_quantity`、
  `replacement_limit_price_policy`、`replacement_time_in_force`、`replace_reason`、
  lifecycle/capability/audit fields。
- Acceptance tests 新增 cross-wire regression：把 cancel 誤接 submit fields、replace
  誤接 cancel fields、submit 誤接 cancel fields 都會得到
  `CommandRequestFieldMissing`，避免未來 runtime 實作混用 request schema。

驗證：

- Rust format checks：PASS。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test stock_etf_lane_scoped_ipc_acceptance -- --nocapture`：
  lane IPC acceptance `9 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test stock_etf_lane_scoped_ipc_acceptance --test stock_etf_phase0_manifest_acceptance -- --nocapture`：
  lane IPC + Phase0 manifest `15 passed`。
- Full `cargo test --manifest-path rust/Cargo.toml -p openclaw_types`：
  `35` unit/golden + `209` integration/acceptance + `0` doc-tests。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_engine stock_etf -- --nocapture`：
  Stock/ETF engine filter `21 passed`；legacy `submit_paper_order` 仍走既有 channel
  path，未被 stock/ETF IPC alias。
- `cargo check --manifest-path rust/Cargo.toml --workspace`：PASS。
- `git diff --check`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不讀/建 secret、不啟動 connector runtime、
不啟動 Phase 1/2/3/4/5 runtime、不送 paper order、不做 cancel/replace、不匯入 fill、
不做 DB migration/apply、不做 Postgres dry-run、不啟動 evidence clock、不啟動
scorecard writer、不做 Linux runtime sync/restart、不啟動 paper-shadow launch、不授權
tiny-live/live 或任何 Bybit behavior change。

## 24. 2026-06-30 PM session source checkpoint：Paper-Shadow Reconciliation Contract

本 session 繼續補 Phase 3 前置的 source-only contract：新增
`stock_etf_paper_shadow_reconciliation_v1`。這是 paper fill fact、synthetic shadow
fill fact 與 divergence threshold 的 typed reconciliation contract，不是
reconciliation writer、fill importer、shadow fill generator 或 scorecard writer。

新增 checkpoint：

- Rust `openclaw_types` 新增
  `StockEtfPaperShadowReconciliationV1`，固定 `stock_etf_cash`、IBKR、
  `paper_shadow` scope、read-only authority 與 effect-capable false posture。
- Validator 要求 reconciliation run、paper local order、broker order、execution、
  commission report、shadow signal id，以及 lifecycle/event-log/paper-fill import/
  shadow-signal/shadow-fill/cost-model/market-data/divergence-threshold/
  paper-shadow-link/raw/redacted/source hashes。
- Accepted fixture 必須有 append-only event readiness、paper fill imported marker、
  synthetic shadow fill marker、正數 threshold、divergence <= threshold、unmatched
  paper/shadow fills 都為 0。
- Validator 拒絕 IBKR contact、connector runtime、secret serialization、fill import
  side effect、shadow fill generation、reconciliation writer、scorecard writer、DB apply、
  order routing、Bybit path reuse、tiny-live/live、margin/short/options/CFD 與 Python
  direct broker write。
- Phase0 manifest source + repository JSON 增加
  `stock_etf_paper_shadow_reconciliation_v1`，contract count 從 31 更新為 32；FastAPI
  Phase0 normalizer、fixtures/tests、reconciliation normalizer/tests 與 Phase0 packet
  spec 同步。
- Rust `stock_etf.get_reconciliation_status` status fixture 現在顯示 reconciliation
  contract id、accepted/blockers、paper-shadow link hash、paper fill imported、
  synthetic shadow fill 與 writer/side-effect flags，全部保持 default blocked false。

驗證：

- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test stock_etf_paper_shadow_reconciliation_acceptance -- --nocapture`：
  reconciliation acceptance `5 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test stock_etf_phase0_manifest_acceptance -- --nocapture`：
  Phase0 manifest acceptance `6 passed`。
- `python3 -m pytest -q ...test_stock_etf_phase0_status_routes.py ...test_stock_etf_reconciliation_status_routes.py`：
  FastAPI Phase0/reconciliation focused `9 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_engine stock_etf_reconciliation_status -- --nocapture`：
  focused reconciliation status `1 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_engine stock_etf -- --nocapture`：
  Stock/ETF engine filter `27 passed`（既有 warnings only）。
- `cargo check --manifest-path rust/Cargo.toml --workspace`：PASS。
- `rustfmt --edition 2021 --check ...`：PASS。
- `git diff --check`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不讀/建 secret、不啟動 connector runtime、
不啟動 Phase 1/2/3/4/5 runtime、不啟動 reconciliation writer、不匯入 fill、不生成
shadow fill、不啟動 scorecard writer、不做 DB migration/apply、不做 Postgres dry-run、
不啟動 evidence clock、不送 paper order、不做 cancel/replace、不做 Linux runtime
sync/restart、不啟動 paper-shadow launch、不授權 tiny-live/live 或任何 Bybit behavior
change。

## 25. 2026-06-30 PM session source checkpoint：Reconciliation GUI Contract Display

本 session 完成純 GUI display-only hardening，把
`stock_etf_paper_shadow_reconciliation_v1` 的 contract summary 顯示到 Stock/ETF
Reconciliation panel。這不是 runtime reconciliation，也不是任何 writer / importer。

新增 checkpoint：

- 新增 `/static/tab-stock-etf-reconciliation.js`，從主
  `tab-stock-etf.js` 抽出 reconciliation fallback/render，讓主 JS 從 1951 行降到
  1847 行，保持低於 2000 行上限。
- Reconciliation panel 現在顯示 expected/actual reconciliation contract id、
  reconciliation accepted/blockers、contract reconciliation run id、paper-shadow link
  hash、paper fill imported、shadow fill synthetic、reconciliation writer、IBKR contact、
  connector runtime、secret serialization、fill import、shadow fill generation 等欄位。
- HTML 載入新檔，static route contract test 與 no-write static guard 都把新 JS
  納入掃描。

驗證：

- `node --check tab-stock-etf-reconciliation.js` + `tab-stock-etf.js`：PASS。
- GUI line counts：HTML 396、main JS 1847、reconciliation JS 177、phase0 JS 149、
  release-packet JS 138、disable-cleanup JS 132。
- Focused route/static/no-write pytest `13 passed`。
- Full Stock/ETF Python route/static suite `90 passed`。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不讀/建 secret、不啟動 connector runtime、
不啟動 reconciliation writer、不匯入 fill、不生成 shadow fill、不啟動 scorecard writer、
不做 DB apply、不送 paper order、不做 cancel/replace、不做 Linux runtime sync/restart、
不授權 tiny-live/live 或任何 Bybit behavior change。

## 29. 2026-06-30 PM session source checkpoint：Shadow Signal Request Contract + IPC Binding

本 session 繼續 Phase 1D/3 邊界，但仍是 source-only contract + IPC gate。此
checkpoint 讓未來 `stock_etf.evaluate_shadow_signal` 不再只有 generic params，而必須
先滿足 typed shadow request contract。

新增 checkpoint：

- Rust `openclaw_types` 新增 `stock_etf_shadow_signal_request_v1`，位於
  `stock_etf_shadow_signal_request.rs`。
- Contract 固定 `asset_lane=stock_etf_cash`、`broker=ibkr`、
  `environment=shadow`、`request_method=evaluate_shadow_signal`、
  `operation=shadow_signal_emit`、`authority_scope=shadow_only`、
  `effect_capable=false`。
- Validator 要求 request id、evaluation run id、shadow signal id、evidence clock hash、
  PIT universe hash、strategy hypothesis hash、instrument identity hash、market-data
  provenance hash、cost model version hash、asset-lane event hash、source artifact hash。
- Validator 拒絕 IBKR contact、connector runtime、secret serialization、shadow signal
  emission、shadow fill generation、scorecard writer、DB apply、order routing、Bybit path
  reuse、live/tiny-live authority、margin/short/options/CFD、Python direct broker write。
- 新增 blocked secret-free template
  `settings/broker/stock_etf_shadow_signal_request.template.toml`。
- Phase0 manifest source、repository manifest JSON、FastAPI Phase0 count、route fixtures/tests
  與 Phase0 packet spec 同步；contract count 從 30 更新為 31。
- Rust IPC handler 現在對 `stock_etf.evaluate_shadow_signal` 回傳
  `shadow_signal_request` verdict，並把 top-level `allowed` 綁到
  `shadow_signal_request_accepted_for_ipc`。

驗證：

- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test stock_etf_shadow_signal_request_acceptance -- --nocapture`：
  shadow signal request acceptance `5 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test stock_etf_phase0_manifest_acceptance -- --nocapture`：
  Phase0 manifest acceptance `6 passed`。
- `python3 -m pytest -q ...test_stock_etf_phase0_status_routes.py`：
  Phase0 route `4 passed`。
- `python3 -m pytest -q ...test_stock_etf_routes.py ...test_stock_etf_phase0_status_routes.py`：
  FastAPI StockETF focused `14 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_engine stock_etf_evaluate_shadow_signal -- --nocapture`：
  shadow-signal IPC focused `2 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_engine stock_etf -- --nocapture`：
  Stock/ETF engine filter `27 passed`（既有 warnings only）。
- `cargo check --manifest-path rust/Cargo.toml --workspace`：PASS。
- `rustfmt --edition 2021 --check --config skip_children=true ...`：PASS。
- `git diff --check`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不讀/建 secret、不啟動 connector runtime、
不啟動 shadow collector、不 emit shadow signal、不 generate shadow fill、不啟動
Phase 1/2/3/4/5 runtime、不送 paper order、不做 cancel/replace、不匯入 fill、不做 DB
migration/apply、不做 Postgres dry-run、不啟動 evidence clock、不啟動 scorecard writer、
不做 Linux runtime sync/restart、不啟動 paper-shadow launch、不授權 tiny-live/live 或任何
Bybit behavior change。

## 28. 2026-06-30 PM session source checkpoint：Paper Fill Import IPC Binding

本 session 繼續 Phase 1D source-only IPC hardening。上一個 checkpoint 已新增
`stock_etf_paper_fill_import_request_v1`；本 checkpoint 把
`stock_etf.import_paper_fills` Rust IPC skeleton 綁到該 typed validator，確保未來
fill import runtime 不能繞過 request contract。

新增 checkpoint：

- `stock_etf.import_paper_fills` 會嘗試把 params 解析成
  `StockEtfPaperFillImportRequestV1`。
- Response 新增 `fill_import_request` verdict，包含 expected contract id、parse
  status、expected/request method、IPC method match、validator blockers、
  read-only authority posture、lineage field presence 與 side-effect boundary flags。
- Minimal/stale params 會得到 `fill_import_request_parse_failed`，且 top-level
  `fill_import_request_accepted_for_ipc=false`。
- Valid fill-import request 只代表 typed request shape 通過；top-level fixture 仍保留
  `runtime_authority_denied=true`，且 `ibkr_call_performed=false`、
  `secret_slot_touched=false`、`order_routed=false`、`bybit_ipc_reused=false`。
- Handler 的 `allowed` 現在同時要求 broker capability decision、paper request
  envelope verdict 與 fill-import request verdict 全部 accepted-for-IPC。

驗證：

- `rustfmt --edition 2021 --check rust/openclaw_engine/src/ipc_server/handlers/stock_etf.rs rust/openclaw_engine/src/ipc_server/tests/stock_etf.rs`：PASS。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_engine stock_etf_import_paper_fills -- --nocapture`：
  fill-import IPC focused `2 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test stock_etf_paper_fill_import_request_acceptance -- --nocapture`：
  fill import request acceptance `6 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_engine stock_etf -- --nocapture`：
  Stock/ETF engine filter `25 passed`（既有 warnings only）。
- `cargo check --manifest-path rust/Cargo.toml --workspace`：PASS。
- `git diff --check`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不讀/建 secret、不啟動 connector runtime、
不啟動 lifecycle writer、不啟動 Phase 1/2/3/4/5 runtime、不匯入 fill、不做 DB
migration/apply、不做 Postgres dry-run、不啟動 evidence clock、不啟動 scorecard writer、
不做 Linux runtime sync/restart、不送 paper order、不做 cancel/replace、不授權
tiny-live/live 或任何 Bybit behavior change。

## 24. 2026-06-30 PM session source checkpoint：Paper Lifecycle State-Machine Contract Hardening

本 session 繼續 Phase 1D，但仍停留在 source-only lifecycle contract。上一個
checkpoint 補上 lane IPC 與 paper lifecycle 之間的 typed request envelope；本
checkpoint 補強 `ibkr_paper_order_lifecycle_v1` / `broker_lifecycle_event_log_v1`
本身，避免後續 runtime 只檢查單筆 transition 而缺少 append-only lineage、
operation-state 對映或 request-envelope linkage。

新增 checkpoint：

- `BrokerLifecycleEventLogV1` 新增 event sequence、genesis marker、previous event
  hash、event hash、`stock_etf_paper_order_request_v1` request contract id、
  request envelope hash 與 stale-state policy。
- Lifecycle validator 要求非 genesis event 必須有 valid previous event hash；
  genesis event 必須 sequence `1` 且不能帶 previous hash；所有 event 都必須有
  valid event hash 與 request envelope hash。
- Validator 現在要求 lifecycle event environment 必須 exact `paper`，不再只拒絕
  `live_reserved_denied`。
- Validator 新增 operation-bound transition matrix：submit/cancel/replace/fill-import
  只能覆蓋各自允許的 state transitions；submit 不可冒充 fill，cancel 不可冒充
  replace，replace 不可冒充 fill/cancel。
- Denied event 不得推進 active broker state；`STATE_UNKNOWN` recovery 必須帶對應
  stale-state policy，manual-review 與 reconciled terminal state 分開檢查。
- Blocked template `settings/broker/ibkr_paper_order_lifecycle.toml` 同步新增
  default-blocked 欄位；Phase 0 contract packet spec 同步記錄新欄位與 operation
  transition policy。

驗證：

- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test ibkr_paper_lifecycle_acceptance -- --nocapture`：
  lifecycle acceptance `12 passed`。
- Linked Rust acceptance：
  `ibkr_paper_lifecycle_acceptance` `12 passed` +
  `stock_etf_paper_order_request_acceptance` `8 passed` +
  `stock_etf_lane_scoped_ipc_acceptance` `9 passed` +
  `stock_etf_phase0_manifest_acceptance` `6 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_engine stock_etf -- --nocapture`：
  Stock/ETF engine filter `21 passed`（既有 warnings only）。
- Full `cargo test --manifest-path rust/Cargo.toml -p openclaw_types`：
  `35` unit/golden + `221` integration/acceptance + `0` doc-tests。
- `cargo check --manifest-path rust/Cargo.toml --workspace`：PASS。
- `rustfmt --edition 2021 --check` for changed lifecycle Rust files：PASS。
- `git diff --check`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不讀/建 secret、不啟動 connector runtime、
不啟動 lifecycle writer、不啟動 Phase 1/2/3/4/5 runtime、不送 paper order、不做
cancel/replace、不匯入 fill、不做 DB migration/apply、不做 Postgres dry-run、不啟動
evidence clock、不啟動 scorecard writer、不做 Linux runtime sync/restart、不啟動
paper-shadow launch、不授權 tiny-live/live 或任何 Bybit behavior change。因本 turn
tool policy 僅允許在 operator 明確要求 subagent 時 spawn，PM 未派 E1/E2/E4
subagent；已用 focused/full Mac regression 取代本地驗證。

## 25. 2026-06-30 PM session source checkpoint：Paper Status Lifecycle Surface Hardening

本 session 繼續 Phase 1D/4 source-only hardening。上一個 checkpoint 補強
`ibkr_paper_order_lifecycle_v1` / `broker_lifecycle_event_log_v1` 本體；本
checkpoint 把新的 lifecycle state-machine 欄位收斂到 read-only
`stock_etf.get_paper_status` / FastAPI / GUI surface，避免 status 層接受舊 shape
或把 pre-gate lifecycle readiness 誤顯示為可操作狀態。

新增 checkpoint：

- Rust `stock_etf.get_paper_status` 現在輸出 expected/request contract id、
  event sequence、genesis marker、previous/event hash presence、
  request-envelope hash presence 與 stale-state policy presence。
- Paper reconstructability summary 顯示 append-only、event hash chain、
  request-envelope linkage 與 stale-state-policy posture，但 default source fixture
  仍全部 blocked false。
- FastAPI normalizer 要求 lifecycle state-machine 欄位存在；缺欄位的 stale
  payload 會進入 `paper_lifecycle_state_machine_fields_missing` /
  `paper_request_expected_contract_id_mismatch`，並以
  `contract_violation_blocked` fail-closed。
- FastAPI guard 會拒絕 pre-gate `event_sequence_present`、`genesis_event`、
  previous/event hash、request-envelope hash、stale-state policy 或 actual request
  contract id claim。
- GUI paper panel 顯示 request contract id、sequence/hash/stale policy 與
  reconstructability 欄位；fallback 仍是 display-only blocked shape。

驗證：

- `python3 -m py_compile ...stock_etf_status_common.py ...stock_etf_paper_normalizers.py ...stock_etf_route_fixtures.py ...test_stock_etf_paper_status_routes.py`：PASS。
- `python3 -m pytest -q ...test_stock_etf_paper_status_routes.py`：
  paper-status focused `6 passed`。
- `python3 -m pytest -q ...test_stock_etf_paper_status_routes.py ...test_stock_etf_routes.py ...test_stock_etf_python_no_write_static_guard.py`：
  wider Stock/ETF FastAPI/static `19 passed`。
- `node --check program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/tab-stock-etf.js`：PASS。
- `rustfmt --edition 2021 --check rust/openclaw_engine/src/ipc_server/handlers/stock_etf.rs rust/openclaw_engine/src/ipc_server/tests/stock_etf.rs`：PASS。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_engine stock_etf_paper_status -- --nocapture`：
  focused paper-status engine test PASS。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_engine stock_etf -- --nocapture`：
  Stock/ETF engine filter `21 passed`（既有 warnings only）。
- `cargo check --manifest-path rust/Cargo.toml --workspace`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不讀/建 secret、不啟動 connector runtime、
不啟動 lifecycle writer、不啟動 Phase 1/2/3/4/5 runtime、不送 paper order、不做
cancel/replace、不匯入 fill、不做 DB migration/apply、不做 Postgres dry-run、不啟動
evidence clock、不啟動 scorecard writer、不做 Linux runtime sync/restart、不啟動
paper-shadow launch、不授權 tiny-live/live 或任何 Bybit behavior change。

## 26. 2026-06-30 PM session source checkpoint：Paper IPC Request Envelope Binding

本 session 繼續 Phase 1D source-only IPC hardening。前面已建立
`stock_etf_paper_order_request_v1` typed envelope 與 paper lifecycle contract；
本 checkpoint 把 Rust IPC effect-capable skeleton 綁到該 envelope validator，避免
未來 runtime 在 `preview/submit/cancel/replace` 入口處繞過 typed request shape。

新增 checkpoint：

- `stock_etf.preview_paper_order`、`stock_etf.submit_paper_order`、
  `stock_etf.cancel_paper_order`、`stock_etf.replace_paper_order` 會嘗試把 params
  解析成 `StockEtfPaperOrderRequestEnvelopeV1`。
- Response 新增 `request_envelope` 子物件，回報 expected contract id、parse status、
  expected/request method、IPC method match、validator blockers、authority scope、
  effect-capable flag、lineage field presence 與 side-effect boundary flags。
- Minimal/stale params 會被標記為 `request_envelope_parse_failed`，但仍不需要或觸碰
  legacy Bybit paper channel。
- Valid envelope 只代表 typed request shape 通過；top-level fixture 仍保留
  `runtime_authority_denied=true`，且 `ibkr_call_performed=false`、
  `secret_slot_touched=false`、`order_routed=false`、`bybit_ipc_reused=false`。
- Handler 會檢查 envelope request method 與實際 IPC method 一致；valid submit
  envelope 送到 cancel IPC 會得到 `ipc_method_mismatch`，不能成為 accepted-for-IPC。

驗證：

- `rustfmt --edition 2021 --check rust/openclaw_engine/src/ipc_server/handlers/stock_etf.rs rust/openclaw_engine/src/ipc_server/tests/stock_etf.rs`：PASS。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_engine stock_etf -- --nocapture`：
  Stock/ETF engine filter `23 passed`（既有 warnings only）。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test stock_etf_paper_order_request_acceptance -- --nocapture`：
  paper request acceptance `8 passed`。
- `cargo check --manifest-path rust/Cargo.toml --workspace`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不讀/建 secret、不啟動 connector runtime、
不啟動 lifecycle writer、不啟動 Phase 1/2/3/4/5 runtime、不送 paper order、不做
cancel/replace、不匯入 fill、不做 DB migration/apply、不做 Postgres dry-run、不啟動
evidence clock、不啟動 scorecard writer、不做 Linux runtime sync/restart、不啟動
paper-shadow launch、不授權 tiny-live/live 或任何 Bybit behavior change。

## 27. 2026-06-30 PM session source checkpoint：Paper Fill Import Request Contract

本 session 繼續 Phase 1D source-only contract hardening。前面已補上 paper order
request envelope 與 lifecycle contract；本 checkpoint 新增未來
`stock_etf.import_paper_fills` 必須滿足的 typed request contract，先封住 fill
idempotency、duplicate import、stale unknown-state 與 redaction/evidence lineage。

新增 checkpoint：

- Rust `openclaw_types` 新增 `stock_etf_paper_fill_import_request_v1`，位於
  `stock_etf_paper_fill_import_request.rs`。
- Contract 固定 `asset_lane=stock_etf_cash`、`broker=ibkr`、`environment=paper`、
  `request_method=import_paper_fills`、`operation=paper_order_fill_import`、
  `authority_scope=readonly`、`effect_capable=false`。
- Validator 要求 session attestation hash、lifecycle contract id/hash、event-log
  contract id/hash、redaction policy id/hash、source artifact hash、reconciliation run id、
  broker order id、execution id、commission report id、import idempotency key、observed
  order state、stale-state policy、raw artifact hash 與 redacted summary hash。
- Validator 拒絕 duplicate import、沒有 policy 的 stale unknown state、IBKR contact、
  connector runtime、serialized secret、fill import side effect、DB apply、order routed、
  Bybit path reuse、live/tiny-live authority、margin/short/options/CFD request、Python
  direct broker write。
- 新增 blocked secret-free template
  `settings/broker/stock_etf_paper_fill_import_request.template.toml`。
- Phase0 manifest source、repository manifest JSON、FastAPI Phase0 count、route fixtures/tests
  與 Phase0 packet spec 同步；contract count 從 29 更新為 30。

驗證：

- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test stock_etf_paper_fill_import_request_acceptance -- --nocapture`：
  fill import request acceptance `6 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test stock_etf_phase0_manifest_acceptance -- --nocapture`：
  Phase0 manifest acceptance `6 passed`。
- `python3 -m pytest -q ...test_stock_etf_phase0_status_routes.py ...test_stock_etf_routes.py`：
  FastAPI Phase0/StockETF focused `14 passed`。
- Full `cargo test --manifest-path rust/Cargo.toml -p openclaw_types`：
  `35` unit/golden + `227` integration/acceptance + `0` doc-tests。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_engine stock_etf -- --nocapture`：
  Stock/ETF engine filter `23 passed`（既有 warnings only）。
- `cargo check --manifest-path rust/Cargo.toml --workspace`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不讀/建 secret、不啟動 connector runtime、
不啟動 lifecycle writer、不啟動 Phase 1/2/3/4/5 runtime、不匯入 fill、不做 DB
migration/apply、不做 Postgres dry-run、不啟動 evidence clock、不啟動 scorecard writer、
不做 Linux runtime sync/restart、不送 paper order、不做 cancel/replace、不授權
tiny-live/live 或任何 Bybit behavior change。

## 23. 2026-06-30 PM session source checkpoint：Paper Request Envelope Contract

本 session 繼續 Phase 1D，但仍停留在 source-only contract。上一個 checkpoint 固定
lane-scoped IPC 欄位矩陣；本 checkpoint 補上 typed request envelope，讓後續 runtime
不能自行解讀 submit/cancel/replace schema。

新增 checkpoint：

- Rust `openclaw_types` 新增 `stock_etf_paper_order_request_v1`，位於
  `stock_etf_paper_order_request.rs`，作為 `lane_scoped_ipc_v1` 到
  `ibkr_paper_order_lifecycle_v1` 之間的 typed request envelope。
- Envelope 驗證 preview/submit/cancel/replace 的 exact method / operation /
  authority scope / effect-capable 對映，且固定 `asset_lane=stock_etf_cash`、
  `broker=ibkr`、`environment=paper`。
- Preview/submit 驗證 normalized symbol、stock/ETF instrument kind、buy/sell side、
  market/limit order type、positive decimal quantity、explicit limit-price policy、
  day/GTC time-in-force。Market order 必須沒有 limit price；limit order 必須有正數
  limit price。
- Submit 驗證 session attestation、scoped authorization、Decision Lease、Guardian、
  risk config、instrument identity、local order id、idempotency、lifecycle、
  broker capability registry、audit event lineage，且 submit 前不能帶 broker order id。
- Cancel 驗證 local order id、broker order id、cancel reason、idempotency、
  lifecycle/capability/audit lineage，並拒絕 submit order-shape pollution。
- Replace 驗證 local/broker order id、instrument identity、symbol/side、
  replacement idempotency、replacement quantity、replacement limit-price policy、
  replacement time in force、replace reason，並拒絕 original mutable fields pollution。
- Phase0 manifest source + repository JSON 增加
  `stock_etf_paper_order_request_v1`，contract count 從 28 更新為 29；FastAPI
  Phase0 normalizer 與 tests 同步，避免 display surface 接受 stale count。
- 新增 blocked template：
  `settings/broker/stock_etf_paper_order_request.template.toml`。

驗證：

- `python3 -m py_compile ...stock_etf_phase0_normalizers.py ...test_stock_etf_phase0_status_routes.py ...stock_etf_route_fixtures.py`：PASS。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test stock_etf_paper_order_request_acceptance --test stock_etf_phase0_manifest_acceptance -- --nocapture`：
  paper request `8 passed` + Phase0 manifest `6 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test stock_etf_lane_scoped_ipc_acceptance -- --nocapture`：
  lane IPC `9 passed`。
- `python3 -m pytest -q ...test_stock_etf_phase0_status_routes.py ...test_stock_etf_routes.py`：
  FastAPI focused `14 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_engine stock_etf -- --nocapture`：
  Stock/ETF engine filter `21 passed`（既有 warnings only）。
- Full `cargo test --manifest-path rust/Cargo.toml -p openclaw_types`：
  `35` unit/golden + `217` integration/acceptance + `0` doc-tests。
- `cargo check --manifest-path rust/Cargo.toml --workspace`：PASS。
- `rustfmt --edition 2021 --check ...`：PASS。
- `git diff --check`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不讀/建 secret、不啟動 connector runtime、
不啟動 Phase 1/2/3/4/5 runtime、不送 paper order、不做 cancel/replace、不匯入 fill、
不做 DB migration/apply、不做 Postgres dry-run、不啟動 evidence clock、不啟動
scorecard writer、不做 Linux runtime sync/restart、不啟動 paper-shadow launch、不授權
tiny-live/live 或任何 Bybit behavior change。

## 30. 2026-06-30 PM session source checkpoint：Scorecard Reconciliation Lineage Gate

本 session 繼續 Phase 3 scorecard source-only hardening。前面已建立
`stock_etf_paper_shadow_reconciliation_v1` 以及 display-only reconciliation panel；
本 checkpoint 把該 reconciliation lineage 明確接入
`stock_etf_scorecard_verdict_v1`，避免未來 scorecard verdict 在沒有 paper-vs-shadow
reconciliation hash 的情況下被誤讀為完整。

新增 checkpoint：

- `StockEtfScorecardVerdictV1` 新增
  `paper_shadow_reconciliation_hash`，並要求為 SHA-256 hex。
- Validator 新增 `PaperShadowReconciliationHashInvalid` blocker；default verdict
  會 fail closed，positive fixture 必須帶 reconciliation hash 才能通過。
- Blocked template
  `settings/broker/stock_etf_scorecard_verdict.template.toml` 同步新增欄位。
- Rust IPC `stock_etf.get_scorecard_status` 現在回報
  `paper_shadow_reconciliation_hash_present=false`，保持 blocked source fixture。
- FastAPI scorecard normalizer、route tests、fixtures 與 GUI scorecard panel 同步顯示
  reconciliation hash gate；pre-gate payload 若宣稱該 hash present 會被
  `contract_violation_blocked` 擋下。
- Phase0 packet spec 與 broker README 已更新，說明 scorecard verdict 必須攜帶
  paper-shadow reconciliation hash。

驗證：

- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test stock_etf_scorecard_verdict_acceptance -- --nocapture`：
  scorecard verdict acceptance `8 passed`。
- `python3 -m pytest -q ...test_stock_etf_scorecard_status_routes.py ...test_stock_etf_routes.py`：
  focused FastAPI/static `15 passed`。
- `python3 -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf*.py`：
  full Stock/ETF FastAPI/static `90 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_engine stock_etf -- --nocapture`：
  Stock/ETF engine filter `27 passed`（既有 warnings only）。
- Full `cargo test --manifest-path rust/Cargo.toml -p openclaw_types`：
  `35` unit/golden + `236` integration/acceptance + `0` doc-tests。
- `cargo check --manifest-path rust/Cargo.toml --workspace`：PASS。
- `rustfmt --edition 2021 --check ...`：PASS。
- `node --check .../tab-stock-etf.js`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不讀/建 secret、不啟動 connector runtime、
不啟動 Phase 1/2/3/4/5 runtime、不送 paper order、不做 cancel/replace、不匯入 fill、
不產生 shadow fill、不啟動 reconciliation writer、不啟動 scorecard writer、不做 DB
migration/apply、不做 Postgres dry-run、不啟動 evidence clock、不做 Linux runtime
sync/restart、不啟動 paper-shadow launch、不授權 tiny-live/live 或任何 Bybit behavior
change。

## 33. 2026-06-30 PM session source checkpoint：IBKR Read-Only Connector Skeleton Boundary

本 checkpoint 建立計劃第 3.3 節指定的隔離 Python package：
`program_code/broker_connectors/ibkr_connector/`。這不是 runtime connector，
不導入 `ibapi` / `ib_insync`，不開 network，不讀 secret，不提供任何 broker write
method；用途是把未來 IBKR read-only / paper surface 的 Python 邊界先固定在
Bybit 目錄外，且讓 no-write guard 對實際目錄生效。

新增 checkpoint：

- 新增 `program_code/broker_connectors/ibkr_connector` package 與 README。
- `models.py` 定義 non-secret loopback endpoint descriptor 與 blocked
  read-only surface status。
- `readonly_client.py` 只提供 blocked readiness / account snapshot / market data /
  contract details preview，所有 payload 都保持 `network_contact_performed=false`、
  `secret_content_loaded=false`、`order_write_method_present=false`。
- `paper_client.py` 只提供 paper lifecycle / fill-import readiness previews，
  明確 `python_broker_write_authority=false`。
- `fixtures/readonly.py` 提供 secret-free blocked fixture。
- 新增 `test_stock_etf_ibkr_connector_skeleton.py`，並由既有
  `test_stock_etf_python_no_write_static_guard.py` 自動掃描新 connector package。
- Phase0 packet spec 已更新，說明 no-write guard 現在掃描實際 IBKR skeleton。

驗證：

- `python3 -m py_compile program_code/broker_connectors/... test_stock_etf_ibkr_connector_skeleton.py`：PASS。
- `python3 -m pytest -q ...test_stock_etf_ibkr_connector_skeleton.py ...test_stock_etf_python_no_write_static_guard.py`：
  connector skeleton + no-write guard `7 passed`。
- `python3 -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf*.py`：
  full Stock/ETF FastAPI/static `94 passed`。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不啟動 Phase 1/2/3/4/5 runtime、不送 paper
order、不做 cancel/replace、不匯入 fill、不做 DB apply、不啟動 evidence clock、
不啟動 scorecard writer、不做 Linux runtime sync/restart、不授權 tiny-live/live 或任何
Bybit behavior change。

## 35. 2026-06-30 PM session display checkpoint：Connector Skeleton Readiness Gate

本 checkpoint 把 inert IBKR connector skeleton boundary 顯示到現有
`/api/v1/stock-etf/readiness`，但不 import connector package、不啟動 runtime、
不新增 endpoint，也不新增任何 effect-capable action。

新增 checkpoint：

- FastAPI readiness normalizer 新增 `connector_skeleton` block，預設為
  `ibkr_stock_etf_readonly_connector_skeleton_v1` / `blocked_source_only`。
- 若 upstream payload 宣稱 connector skeleton `accepted=true`、status 非 blocked、
  network contact、secret loaded、paper/live channel exposed、write method present、
  或 Bybit path reused，readiness 會轉為 `contract_violation_blocked`。
- GUI readiness panel 現在顯示 connector skeleton surface/status，以及所有
  side-effect flags。
- Route tests 覆蓋 fallback false、正常 blocked display、與 truthy claims 被拒。

驗證：

- `python3 -m py_compile ...stock_etf_readiness_normalizers.py ...test_stock_etf_readiness_routes.py`：PASS。
- `python3 -m pytest -q ...test_stock_etf_readiness_routes.py ...test_stock_etf_python_no_write_static_guard.py`：
  focused readiness/no-write `9 passed`。
- `python3 -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf*.py`：
  full Stock/ETF FastAPI/static `94 passed`。
- `node --check .../tab-stock-etf.js`：PASS。
- `git diff --check`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不啟動 Phase 1/2/3/4/5 runtime、不送 paper
order、不做 cancel/replace、不匯入 fill、不做 DB apply、不啟動 evidence clock、
不啟動 scorecard writer、不做 Linux runtime sync/restart、不授權 tiny-live/live 或任何
Bybit behavior change。

## 34. 2026-06-30 PM session governance checkpoint：ADR/Register Lineage Catch-up

本 checkpoint 只補治理索引與 ADR/AMD 文字，不改程式碼：

- `docs/governance_dev/SPECIFICATION_REGISTER.md` 的 Last Updated 已改為
  ADR-0048 lineage + connector-skeleton hardening。
- 新增 ADR-0048 Addendum E，登記 scorecard derivation / verdict /
  paper-shadow reconciliation / tiny-live eligibility lineage。
- 新增 ADR-0048 Addendum F，登記
  `program_code/broker_connectors/ibkr_connector/` 是 inert source-only skeleton。
- ADR-0048 與 AMD-2026-06-29-01 已補明：
  tiny-live discussion gate 需要 derivation/verdict/manifest/reconciliation/DQ/
  preregistration/QC/MIT/QA lineage，但仍只可開新 ADR discussion。
- ADR-0048 與 AMD 已補明：Python IBKR skeleton 不得導入 SDK、開 network、
  讀 secret、暴露 broker write、匯入 fills 或寫 DB。

驗證：

- `rg` 檢查 register/ADR/AMD 中 `ibkr_connector`、`scorecard_derivation`、
  `paper_shadow_reconciliation`、`tiny_live_adr` 均有最新登記。
- `git diff --check`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不啟動 Phase 1/2/3/4/5 runtime、不送 paper
order、不做 cancel/replace、不匯入 fill、不做 DB apply、不啟動 evidence clock、
不啟動 scorecard writer、不做 Linux runtime sync/restart、不授權 tiny-live/live 或任何
Bybit behavior change。

## 32. 2026-06-30 PM session source checkpoint：Tiny-Live Eligibility Lineage Gate

本 checkpoint harden Phase 5 之後「是否可以拿去開 ADR 討論 tiny-live」的
source-only gate。它不是 tiny-live approval，也不是 live/tiny-live runtime；它只把
前面已建立的 scorecard derivation、scorecard verdict、paper-shadow reconciliation
與 QA lineage 接入 `tiny_live_adr_eligibility_v1`。

新增 checkpoint：

- `TinyLiveAdrEligibilityV1` 新增 `scorecard_derivation_hash`、
  `scorecard_verdict_hash`、`paper_shadow_reconciliation_hash`、`qa_review_hash`
  與 `qa_review_passed`。
- Validator 新增對應 SHA-256 hash blockers：
  `ScorecardDerivationHashInvalid`、`ScorecardVerdictHashInvalid`、
  `PaperShadowReconciliationHashInvalid`、`QaReviewHashInvalid`，以及
  `QaReviewMissing`。
- Blocked template
  `settings/broker/stock_etf_tiny_live_adr_eligibility.template.toml` 同步新增欄位，
  預設仍全部 fail closed。
- Rust `stock_etf.get_launch_status`、FastAPI launch normalizer/fixtures/tests 與 GUI
  launch panel 新增 display-only lineage hash-present rows；pre-gate truthy lineage
  或 QA pass claims 會被 `contract_violation_blocked` 擋下。
- Phase0 packet spec 與 broker README 已更新，明確 tiny-live ADR discussion gate
  需要 derivation/verdict/reconciliation/QA lineage。

驗證：

- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test stock_etf_tiny_live_eligibility_acceptance -- --nocapture`：
  tiny-live eligibility acceptance `7 passed`。
- `python3 -m py_compile ...stock_etf_launch_normalizers.py ...test_stock_etf_launch_status_routes.py ...stock_etf_route_fixtures.py`：PASS。
- `python3 -m pytest -q ...test_stock_etf_launch_status_routes.py ...test_stock_etf_routes.py`：
  focused FastAPI/static `15 passed`。
- `python3 -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf*.py`：
  full Stock/ETF FastAPI/static `90 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_engine stock_etf_launch_status -- --nocapture`：
  engine launch-status focused `1 passed`（既有 warnings only）。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_engine stock_etf -- --nocapture`：
  Stock/ETF engine filter `27 passed`（既有 warnings only）。
- Full `cargo test --manifest-path rust/Cargo.toml -p openclaw_types`：
  `35` unit/golden + `241` integration/acceptance + `0` doc-tests。
- `cargo check --manifest-path rust/Cargo.toml --workspace`：PASS。
- `rustfmt --edition 2021 --check ...`：PASS。
- `node --check .../tab-stock-etf.js`：PASS。
- `git diff --check`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不讀/建 secret、不啟動 connector runtime、
不啟動 Phase 1/2/3/4/5 runtime、不送 paper order、不做 cancel/replace、不匯入 fill、
不產生 shadow fill、不啟動 reconciliation writer、不啟動 scorecard writer、不做 DB
migration/apply、不做 Postgres dry-run、不啟動 evidence clock、不做 Linux runtime
sync/restart、不啟動 paper-shadow launch、不授權 tiny-live/live 或任何 Bybit behavior
change。

## 31. 2026-06-30 PM session source checkpoint：Scorecard Derivation Contract

本 checkpoint 補上 Phase 3 `scorecard_derive` 的 source-only artifact gate。
前面已有 scorecard inputs、paper-shadow reconciliation 與 verdict；這次新增的是
「derivation artifact 自身」的 lineage contract，避免未來 scorecard writer 或 daily
regeneration 在未證明 input/reconciliation/verdict/output hashes 時被誤視為完整。

新增 checkpoint：

- Rust `openclaw_types` 新增 `stock_etf_scorecard_derivation_v1`，位於
  `stock_etf_scorecard_derivation.rs`。
- Contract 要求 exact Stock/ETF + IBKR + paper identity、derivation run id、strategy /
  universe / benchmark / as-of identity、scorecard input bundle hash、evidence-clock /
  DQ manifest hashes、paper-shadow reconciliation hash、formula/preregistration hashes、
  scorecard manifest hash、scorecard verdict hash、source commit/code/output artifact
  hashes、QC/MIT/QA review hashes。
- Validator 要求 `derived_from_atomic_facts_only=true`、
  `idempotent_replay_proven=true`、paper/shadow fills separated、Bybit live execution
  unchanged、sealed；拒絕 IBKR contact、connector runtime、broker fill import、
  shadow fill generation、reconciliation writer、scorecard writer、DB apply、
  evidence-clock start、secret serialization、tiny-live/live authority。
- 新增 blocked secret-free template
  `settings/broker/stock_etf_scorecard_derivation.template.toml`。
- Rust `stock_etf.get_scorecard_status`、FastAPI normalizer/fixtures/tests 與 GUI
  scorecard panel 新增 display-only `scorecard_derivation` block；pre-gate derivation
  truthy claims 會被 `contract_violation_blocked` 擋下。
- Phase0 packet spec 與 broker README 已更新，說明 derivation contract 是 writer 前置
  gate；本 checkpoint 不改 Phase0 required-contract count。

驗證：

- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test stock_etf_scorecard_derivation_acceptance -- --nocapture`：
  derivation acceptance `5 passed`。
- `python3 -m py_compile ...stock_etf_scorecard_normalizers.py ...stock_etf_status_common.py ...test_stock_etf_scorecard_status_routes.py ...stock_etf_route_fixtures.py`：PASS。
- `python3 -m pytest -q ...test_stock_etf_scorecard_status_routes.py ...test_stock_etf_routes.py`：
  focused FastAPI/static `15 passed`。
- `python3 -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf*.py`：
  full Stock/ETF FastAPI/static `90 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_engine stock_etf_scorecard_status -- --nocapture`：
  engine scorecard focused `1 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_engine stock_etf -- --nocapture`：
  Stock/ETF engine filter `27 passed`（既有 warnings only）。
- Full `cargo test --manifest-path rust/Cargo.toml -p openclaw_types`：
  `35` unit/golden + `241` integration/acceptance + `0` doc-tests。
- `cargo check --manifest-path rust/Cargo.toml --workspace`：PASS。
- `rustfmt --edition 2021 --check ...`：PASS。
- `node --check .../tab-stock-etf.js`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不讀/建 secret、不啟動 connector runtime、
不啟動 Phase 1/2/3/4/5 runtime、不送 paper order、不做 cancel/replace、不匯入 fill、
不產生 shadow fill、不啟動 reconciliation writer、不啟動 scorecard writer、不做 DB
migration/apply、不做 Postgres dry-run、不啟動 evidence clock、不做 Linux runtime
sync/restart、不啟動 paper-shadow launch、不授權 tiny-live/live 或任何 Bybit behavior
change。

## 36. 2026-06-30 PM session source checkpoint：Read-Only Probe IPC Binding

本 checkpoint 把前面新增的 `stock_etf_ibkr_readonly_probe_request_v1` 接到 Rust
IPC validation-only method：`stock_etf.preview_readonly_probe`。這不是 IBKR
healthcheck、不是 connector runtime，也不是首次 contact；它只讓 future first-contact
read probe request 在 Rust fixture 層先有 typed parse/validation verdict。

新增 checkpoint：

- `lane_scoped_ipc_v1` 新增 `PreviewReadonlyProbe` required method。
- Method gate/field matrix 要求 Phase 2 external-surface gate、non-Bybit API
  allowlist、secret-slot、API topology、session attestation、redaction、rate-limit、
  audit-policy lineage，以及 request/probe/source/raw/redacted artifact hashes。
- Rust method registry 新增 `stock_etf.preview_readonly_probe`，標記
  readonly、slot none，且不進 Bybit live-write token surface。
- Rust dispatch 將 method 送入 Stock/ETF fixture handler；handler 將 params 解析成
  `StockEtfIbkrReadonlyProbeRequestV1`，回傳 `readonly_probe_request` verdict 與
  `readonly_probe_request_accepted_for_ipc`。
- Valid envelope 可以 typed/read-only validate，但 top-level `allowed` 仍會因 default
  flags/gates 維持 false；minimal params fail closed 為
  `readonly_probe_request_parse_failed`。
- Phase0 packet spec 與 broker template README 已同步此 method binding。

驗證：

- `rustfmt`：PASS。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test stock_etf_lane_scoped_ipc_acceptance -- --nocapture`：
  lane-scoped IPC acceptance `9 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_engine stock_etf_preview_readonly_probe -- --nocapture`：
  readonly-probe IPC focused `2 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_engine stock_etf_registry -- --nocapture`：
  registry boundary focused `1 passed`。
- Full `cargo test --manifest-path rust/Cargo.toml -p openclaw_types`：
  `35` unit/golden + `247` integration/acceptance + `0` doc-tests。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_engine stock_etf -- --nocapture`：
  Stock/ETF engine filter `29 passed`（既有 warnings only）。
- `cargo check --manifest-path rust/Cargo.toml --workspace`：PASS。
- `git diff --check`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不啟動 Phase 1/2/3/4/5
runtime、不送 paper order、不做 cancel/replace、不匯入 fill、不做 DB apply、不啟動
evidence clock、不啟動 scorecard writer、不做 Linux runtime sync/restart、不授權
tiny-live/live 或任何 Bybit behavior change。

## 37. 2026-06-30 PM session source checkpoint：Broker Read Capability Probe Gate

本 checkpoint 強化 `broker_capability_registry_v1` 的 read rows。前面已經完成
`stock_etf_ibkr_readonly_probe_request_v1` 和 `stock_etf.preview_readonly_probe`
validation-only IPC；這次把 broker capability registry 的「read capability 可用」
條件綁回這兩個 typed gate，避免未來只憑 capability row 表示可讀而繞過 request /
IPC 邊界。

新增 checkpoint：

- `health_read` 現在要求 external surface gate + `lane_scoped_ipc_v1` +
  `stock_etf_ibkr_readonly_probe_request_v1`。
- `account_snapshot_read` 現在要求 external surface gate + lane-scoped IPC +
  readonly-probe request + session attestation。
- `market_data_read` 現在要求 external surface gate + lane-scoped IPC +
  readonly-probe request + market-data provenance。
- `contract_details_read` 現在要求 external surface gate + lane-scoped IPC +
  readonly-probe request + instrument identity。
- Validator acceptance 新增缺失 gate 的 negative test；缺少 typed IPC /
  readonly-probe request 會產生 `OperationRequiredGateMissing`。
- Paper-write rows 改用共享 `STOCK_ETF_LANE_SCOPED_IPC_CONTRACT_ID`，避免同一
  contract id 在 registry 內硬編碼漂移。
- Phase0 packet spec、broker settings README、blocked broker capability template
  已同步上述 read-row prerequisite。

驗證：

- `rustfmt --edition 2021 rust/openclaw_types/src/stock_etf_broker_capability_registry.rs rust/openclaw_types/tests/stock_etf_broker_capability_registry_acceptance.rs`：PASS。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test stock_etf_broker_capability_registry_acceptance -- --nocapture`：
  broker capability acceptance `10 passed`。
- Full `cargo test --manifest-path rust/Cargo.toml -p openclaw_types`：
  `35` unit/golden + `248` integration/acceptance + `0` doc-tests。
- `cargo check --manifest-path rust/Cargo.toml --workspace`：PASS。
- `git diff --check`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不啟動 Phase 1/2/3/4/5
runtime、不送 paper order、不做 cancel/replace、不匯入 fill、不做 DB apply、不啟動
evidence writer、不啟動 evidence clock、不啟動 scorecard writer、不做 Linux runtime
sync/restart、不授權 tiny-live/live 或任何 Bybit behavior change。

## 39. 2026-06-30 PM session source checkpoint：Read-Only Probe Request Operation Binding

本 checkpoint 修正 `stock_etf.preview_readonly_probe` 的 source-only IPC semantics。
前面已經把 readonly-probe request 接到 IPC 並顯示在 readiness/policy；這次確保
top-level broker decision 的 operation 跟 valid request envelope 一致，而不是所有
readonly probe 都固定顯示為 method fallback `health_read`。

新增 checkpoint：

- `stock_etf.preview_readonly_probe` 會先嘗試解析
  `StockEtfIbkrReadonlyProbeRequestV1`。
- 只有 `validate().accepted=true` 的 readonly-probe request 才能派生 top-level
  `BrokerOperation`。
- Invalid 或 parse-failed payload 不被信任；仍 fallback 到 method-level
  `HealthRead` fixture boundary。
- 新增 market-data readonly-probe IPC test：valid `market_data_snapshot` request 會讓
  top-level `decision.operation=market_data_read`，同時 `allowed=false` 並且沒有任何
  contact/routing side effect。

驗證：

- `rustfmt --edition 2021 rust/openclaw_engine/src/ipc_server/handlers/stock_etf.rs rust/openclaw_engine/src/ipc_server/tests/stock_etf.rs`：PASS。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_engine stock_etf_preview_readonly_probe -- --nocapture`：
  readonly-probe IPC focused `3 passed`（既有 warnings only）。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_engine stock_etf -- --nocapture`：
  Stock/ETF engine filter `30 passed`（既有 warnings only）。
- `cargo check --manifest-path rust/Cargo.toml --workspace`：PASS。
- `git diff --check`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不啟動 Phase 1/2/3/4/5
runtime、不送 paper order、不做 cancel/replace、不匯入 fill、不做 DB apply、不啟動
evidence writer、不啟動 evidence clock、不啟動 scorecard writer、不做 Linux runtime
sync/restart、不授權 tiny-live/live 或任何 Bybit behavior change。

## 38. 2026-06-30 PM session source/status/display checkpoint：Policy Status Read-Row Gate Display

本 checkpoint 把 checkpoint 37 的 broker read-row gate hardening 顯示到
`stock_etf.get_policy_status`、FastAPI `/api/v1/stock-etf/policy-status` 和 Stock/ETF
GUI policy panel。這不是 read probe execution，也不是 Phase 2 start；它只是讓
Operator 能在 policy/capability status 看到 broker registry read rows 是否已綁到
typed IPC / readonly-probe request gate。

新增 checkpoint：

- Rust policy-status payload 在 `broker_capability_registry` 下新增
  `lane_scoped_ipc_contract_id`、`readonly_probe_request_contract_id`、
  `read_rows_require_lane_scoped_ipc`、
  `read_rows_require_readonly_probe_request`。
- FastAPI normalizer/fallback 保留同樣欄位；若 registry 宣稱 accepted 但缺少或
  mismatch 這些 read-row gate claims，會回傳 `contract_violation_blocked`。
- GUI policy panel 顯示兩個 contract id 和兩個 read-row gate booleans。
- Tests 覆蓋 route normalization、contract violation、static GUI contract 和 Rust IPC
  policy-status fixture。

驗證：

- `python3 -m py_compile ...stock_etf_policy_normalizers.py ...stock_etf_route_fixtures.py ...test_stock_etf_policy_status_routes.py ...test_stock_etf_routes.py`：PASS。
- `node --check program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/tab-stock-etf.js`：PASS。
- `python3 -m pytest -q ...test_stock_etf_policy_status_routes.py ...test_stock_etf_routes.py`：
  focused policy/static `15 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_engine stock_etf_policy_status -- --nocapture`：
  engine policy-status focused `1 passed`（既有 warnings only）。
- `python3 -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf*.py`：
  full Stock/ETF FastAPI/static `94 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_engine stock_etf -- --nocapture`：
  Stock/ETF engine filter `29 passed`（既有 warnings only）。
- `cargo check --manifest-path rust/Cargo.toml --workspace`：PASS。
- `git diff --check`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不啟動 Phase 1/2/3/4/5
runtime、不送 paper order、不做 cancel/replace、不匯入 fill、不做 DB apply、不啟動
evidence writer、不啟動 evidence clock、不啟動 scorecard writer、不做 Linux runtime
sync/restart、不授權 tiny-live/live 或任何 Bybit behavior change。
