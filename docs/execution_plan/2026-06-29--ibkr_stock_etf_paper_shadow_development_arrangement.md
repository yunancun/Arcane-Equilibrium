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

## 30. 2026-06-30 PM session source checkpoint：Paper-Shadow Reconciliation Contract

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

## 31. 2026-06-30 PM session source checkpoint：Reconciliation GUI Contract Display

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

## 32. 2026-06-30 PM session source checkpoint：Scorecard Reconciliation Lineage Gate

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

## 33. 2026-06-30 PM session source checkpoint：Scorecard Derivation Contract

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

## 34. 2026-06-30 PM session source checkpoint：Tiny-Live Eligibility Lineage Gate

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

## 35. 2026-06-30 PM session source checkpoint：IBKR Read-Only Connector Skeleton Boundary

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

## 36. 2026-06-30 PM session governance checkpoint：ADR/Register Lineage Catch-up

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

## 37. 2026-06-30 PM session display checkpoint：Connector Skeleton Readiness Gate

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

## 38. 2026-06-30 PM session source checkpoint：Read-Only Probe IPC Binding

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

## 39. 2026-06-30 PM session source checkpoint：Broker Read Capability Probe Gate

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

## 40. 2026-06-30 PM session source/status/display checkpoint：Policy Status Read-Row Gate Display

本 checkpoint 把 checkpoint 39 的 broker read-row gate hardening 顯示到
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

## 41. 2026-06-30 PM session source checkpoint：Read-Only Probe Request Operation Binding

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
## 42. 2026-06-30 PM session governance checkpoint：Plan Timeline Checkpoint Guard

本 checkpoint 修正主計畫內 PM session checkpoint 編號/順序漂移，並新增 structure
test 防止同類漂移再次進入 repo。這是文檔治理 guard，不是 runtime 開發、不是 IBKR
contact，也不改 Stock/ETF 或 Bybit 行為。

新增 checkpoint：

- 主計畫 PM session checkpoint 現在從 14 到 81 連續遞增，無重複編號。
- 已按 PM memory / Operator 實際 source timeline 重排 23-41 區塊：paper request /
  lifecycle / fill-import / shadow / reconciliation / scorecard / tiny-live /
  connector skeleton / readonly-probe / broker read gate / policy display / operation
  binding。
- Section-body 對比確認每個 checkpoint 正文未遺失；除了 policy display 內部引用從
  `checkpoint 37` 改為新的 `checkpoint 39` 外，正文內容保持一致。
- 新增 `tests/structure/test_docs_readme_index_static.py` 的 IBKR 主計畫 timeline guard，
  要求 PM session checkpoint 編號連續且唯一。

驗證：

- `python3 -m pytest -q tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_pm_checkpoint_numbers_are_linear`：
  `1 passed`。
- Section-body compare against `HEAD`：PASS。
- `git diff --check`：PASS。
- 註：`python3 -m pytest -q tests/structure/test_docs_readme_index_static.py` 仍有既有
  docs README index drift 失敗；與本 checkpoint 新增的 IBKR timeline guard 無關。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不啟動 Phase 1/2/3/4/5
runtime、不送 paper order、不做 cancel/replace、不匯入 fill、不做 DB apply、不啟動
evidence writer、不啟動 evidence clock、不啟動 scorecard writer、不做 Linux runtime
sync/restart、不授權 tiny-live/live 或任何 Bybit behavior change。

## 43. 2026-06-30 PM session governance checkpoint：PM Memory Traceability Backfill

本 checkpoint 補齊 PM memory 已記錄、但主計畫與 Operator 摘要沒有明確 title trace 的
中間 source/status checkpoint。這不是新增 runtime 能力，也不是重做既有 source
工作；它只把審計線補成可機器檢查。

回補 title：

- `Source Posture Header Catch-up`
- `Rust Connector Skeleton Readiness Source`
- `Read-Only Probe Request Contract`
- `Read-Only Probe Readiness Gate`

治理 guard：

- 新增 structure test 要求上述 PM memory trace titles 同時出現在主計畫與 Operator
  摘要中。
- 這四項已由 PM memory / `.codex/MEMORY.md` 記錄為 source/status/display-only
  checkpoint；本 checkpoint 不聲稱它們授權 IBKR contact 或 runtime launch。

驗證：

- `python3 -m pytest -q tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_pm_checkpoint_numbers_are_linear tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_plan_and_operator_cover_pm_memory_trace_titles`：
  `2 passed`。
- `git diff --check`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不啟動 Phase 1/2/3/4/5
runtime、不送 paper order、不做 cancel/replace、不匯入 fill、不做 DB apply、不啟動
evidence writer、不啟動 evidence clock、不啟動 scorecard writer、不做 Linux runtime
sync/restart、不授權 tiny-live/live 或任何 Bybit behavior change。

## 44. 2026-06-30 PM session source checkpoint：Python Connector Network Static Guard

本 checkpoint 強化 Stock/ETF / IBKR Python source-only boundary。前面已經有
`test_stock_etf_python_no_write_static_guard.py` 禁止 Python broker write method、
direct IBKR SDK import、非 GET route、GUI write snippets 與 Stock/ETF paper IPC
write string；這次補上 network-client import / dynamic import guard，避免未來在
`program_code/broker_connectors/ibkr_connector/` 或 Stock/ETF FastAPI surface 中
繞過 inert skeleton，直接導入 socket/HTTP/WebSocket client。

已完成：

- 新增 forbidden network module prefix guard：
  `socket`、`http.client`、`requests`、`httpx`、`urllib`、`urllib3`、
  `aiohttp`、`websocket`、`websockets`。
- 同一 guard 檢查 `__import__()` / `import_module()` 對 IBKR SDK 或 network
  module 的動態導入。
- 掃描範圍仍只限 Stock/ETF / IBKR Python surface 與 IBKR connector skeleton，
  不掃既有 Bybit connector，避免改變 Bybit behavior。
- `Python Connector Network Static Guard` 已加入主計畫與 Operator 摘要 trace，
  防止 hardening checkpoint 只留在測試而沒有 PM/Operator 可審計紀錄。

驗證：

- `python3 -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py`：
  `4 passed`。
- `python3 -m pytest -q tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_pm_checkpoint_numbers_are_linear tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_plan_and_operator_cover_pm_memory_trace_titles`：
  `2 passed`。
- `git diff --check`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不啟動 Phase 1/2/3/4/5
runtime、不送 paper order、不做 cancel/replace、不匯入 fill、不做 DB apply、不啟動
evidence writer、不啟動 evidence clock、不啟動 scorecard writer、不做 Linux runtime
sync/restart、不授權 tiny-live/live 或任何 Bybit behavior change。

## 45. 2026-06-30 PM session source checkpoint：GUI Endpoint Template Consistency Guard

本 checkpoint 強化 Stock/ETF GUI / FastAPI / source template 的 endpoint 一致性。
前面已經有 OpenAPI GET-only guard、GUI static endpoint presence guard，以及
`gui_lane_contract_v1` Rust source validator；這次把 FastAPI OpenAPI 實際暴露的
Stock/ETF GET endpoint set 與
`settings/broker/stock_etf_gui_lane_contract.template.toml` 內的 endpoint set
做機器對照，避免 future endpoint 增刪只更新其中一邊。

已完成：

- 新增 `test_stock_etf_openapi_paths_match_gui_lane_contract_template`。
- 測試排除 root redirect `/api/v1/stock-etf`，其餘 Stock/ETF OpenAPI GET paths
  必須等於 GUI lane contract template 的 `*_endpoint` set。
- parser 覆蓋含數字的 key，例如 `phase0_status_endpoint`。
- 本 guard 不新增 endpoint、不改 route handler、不改 GUI runtime，只防 drift。

驗證：

- `python3 -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_routes.py`：
  `11 passed`。
- `python3 -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf*.py`：
  `96 passed`。
- `python3 -m pytest -q tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_pm_checkpoint_numbers_are_linear tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_plan_and_operator_cover_pm_memory_trace_titles`：
  `2 passed`。
- `git diff --check`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不啟動 Phase 1/2/3/4/5
runtime、不送 paper order、不做 cancel/replace、不匯入 fill、不做 DB apply、不啟動
evidence writer、不啟動 evidence clock、不啟動 scorecard writer、不做 Linux runtime
sync/restart、不授權 tiny-live/live 或任何 Bybit behavior change。

## 46. 2026-06-30 PM session source checkpoint：GUI Static Endpoint Template Consistency Guard

本 checkpoint 補上 checkpoint 45 的 static GUI 端一致性 guard。前一個 checkpoint
已要求 FastAPI OpenAPI Stock/ETF GET endpoint set 等於 GUI lane contract template；
這次要求 `tab-stock-etf*` static GUI bundle 中出現的 Stock/ETF API endpoint set
也必須等於同一 template，避免未來 GUI source 自行增刪 endpoint 而沒有同步 source
contract。

已完成：

- 新增 `test_stock_etf_static_gui_endpoint_set_matches_gui_lane_contract_template`。
- 測試掃描 static GUI bundle 的 `/api/v1/stock-etf...` endpoint 字串。
- 掃描結果必須精確等於
  `settings/broker/stock_etf_gui_lane_contract.template.toml` 的 `*_endpoint` set。
- 本 guard 不新增 endpoint、不改 route handler、不改 GUI runtime，只防 static
  GUI/template drift 與 accidental extra Stock/ETF API surface。

驗證：

- `python3 -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py`：
  `5 passed`。
- `python3 -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf*.py`：
  `97 passed`。
- `python3 -m pytest -q tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_pm_checkpoint_numbers_are_linear tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_plan_and_operator_cover_pm_memory_trace_titles`：
  `2 passed`。
- `git diff --check`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不啟動 Phase 1/2/3/4/5
runtime、不送 paper order、不做 cancel/replace、不匯入 fill、不做 DB apply、不啟動
evidence writer、不啟動 evidence clock、不啟動 scorecard writer、不做 Linux runtime
sync/restart、不授權 tiny-live/live 或任何 Bybit behavior change。

## 47. 2026-06-30 PM session source checkpoint：FastAPI Route Auth Coverage Guard

本 checkpoint 強化 Stock/ETF FastAPI route auth coverage。前面已有個別 route 的
requires-auth 測試，但缺少一個會隨 OpenAPI endpoint set 自動擴展的全域 guard；
這次把所有 Stock/ETF GET route 與 root redirect 都納入未登入 401 檢查。

已完成：

- 新增 `test_stock_etf_all_registered_get_routes_require_auth`。
- 測試從 OpenAPI 取得所有 `/api/v1/stock-etf...` GET paths。
- 另加入 include-in-schema=false 的 root redirect `/api/v1/stock-etf`。
- 未提供 `current_actor` dependency override 時，每個 route 都必須回 `401`。
- 本 guard 不新增 endpoint、不改 auth 實作、不啟動 runtime，只防未來 route 漏 auth。

驗證：

- `python3 -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_routes.py`：
  `12 passed`。
- `python3 -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf*.py`：
  `98 passed`。
- `python3 -m pytest -q tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_pm_checkpoint_numbers_are_linear tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_plan_and_operator_cover_pm_memory_trace_titles`：
  `2 passed`。
- `git diff --check`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不啟動 Phase 1/2/3/4/5
runtime、不送 paper order、不做 cancel/replace、不匯入 fill、不做 DB apply、不啟動
evidence writer、不啟動 evidence clock、不啟動 scorecard writer、不做 Linux runtime
sync/restart、不授權 tiny-live/live 或任何 Bybit behavior change。

## 48. 2026-06-30 PM session source checkpoint：FastAPI Route Cache Header Coverage Guard

本 checkpoint 強化 Stock/ETF FastAPI route cache/auth partition。前面已經要求
readiness 與部分 status route 帶 no-store/private header；這次加上全域 guard，
讓未來新增 endpoint 也必須保持 private/no-store 並按 Authorization 分區。

已完成：

- 新增 `test_stock_etf_all_registered_get_routes_are_private_no_store`。
- 測試從 OpenAPI 取得所有 `/api/v1/stock-etf...` GET paths。
- 另加入 include-in-schema=false 的 root redirect `/api/v1/stock-etf`。
- 每個 route 都必須帶 `Cache-Control` 中的 `no-store` / `private`、
  `Pragma: no-cache`、`Expires: 0`、`Vary: Authorization`。
- 本 guard 不新增 endpoint、不改 header 實作、不啟動 runtime，只防未來 route
  漏 cache/auth partition。

驗證：

- `python3 -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_routes.py`：
  `13 passed`。
- `python3 -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf*.py`：
  `99 passed`。
- `python3 -m pytest -q tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_pm_checkpoint_numbers_are_linear tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_plan_and_operator_cover_pm_memory_trace_titles`：
  `2 passed`。
- `git diff --check`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不啟動 Phase 1/2/3/4/5
runtime、不送 paper order、不做 cancel/replace、不匯入 fill、不做 DB apply、不啟動
evidence writer、不啟動 evidence clock、不啟動 scorecard writer、不做 Linux runtime
sync/restart、不授權 tiny-live/live 或任何 Bybit behavior change。

## 49. 2026-06-30 PM session source checkpoint：FastAPI IPC Empty Params Guard

本 checkpoint 強化 Stock/ETF FastAPI 到 Rust IPC 的 client-state-untrusted 邊界。
前面 route tests 已逐條證明部分 endpoint 不信任 query/header state；這次用 AST guard
直接鎖住 `stock_etf_routes.py` 的 IPC 呼叫形狀：所有 Stock/ETF status read 都必須
使用 literal `params={}`。

已完成：

- 新增 `test_stock_etf_routes_call_ipc_with_empty_params_only`。
- 掃描 `stock_etf_routes.py` 的 `ipc.call(...)`。
- 每個 call 必須有且只有一個 `params` keyword，且 value 必須是 literal empty dict。
- call count 必須覆蓋當前全部 Stock/ETF status IPC reads。
- 本 guard 不改 route handler、不改 IPC method、不啟動 runtime，只防未來把 query /
  header / client lane claims 傳入 Rust IPC。

驗證：

- `python3 -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py`：
  `6 passed`。
- `python3 -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf*.py`：
  `100 passed`。
- `python3 -m pytest -q tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_pm_checkpoint_numbers_are_linear tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_plan_and_operator_cover_pm_memory_trace_titles`：
  `2 passed`。
- `git diff --check`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不啟動 Phase 1/2/3/4/5
runtime、不送 paper order、不做 cancel/replace、不匯入 fill、不做 DB apply、不啟動
evidence writer、不啟動 evidence clock、不啟動 scorecard writer、不做 Linux runtime
sync/restart、不授權 tiny-live/live 或任何 Bybit behavior change。

## 50. 2026-06-30 PM session source checkpoint：FastAPI Handler Client-State Guard

本 checkpoint 強化 Stock/ETF FastAPI route handler 的 client-state-untrusted 邊界。
前一個 guard 已鎖住 IPC calls 必須使用 `params={}`；這次往上一層鎖住
`stock_etf_routes.py` 的 route handler signature，避免未來把 Request/Header/Query/
Body/Cookie/Form 類 client state 帶進 status handler，再間接影響 Rust IPC/status
normalization。

已完成：

- 新增 `test_stock_etf_get_route_handlers_accept_only_response_and_authenticated_actor`。
- 掃描每個 `@stock_etf_router.get` handler。
- handler 只允許接收 `response` 與/或 authenticated `actor`。
- `actor` 必須以 `Depends(base.current_actor)` 注入。
- 禁止 variadic / keyword-only route args，防止繞過 signature guard。
- 本 guard 不改 route behavior、不新增 endpoint、不改 IPC method、不啟動 runtime，只防
  client-state-bearing handler inputs 進入 Stock/ETF status surface。

驗證：

- `python3 -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py`：
  `7 passed`。
- `python3 -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf*.py`：
  `101 passed`。
- `python3 -m pytest -q tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_pm_checkpoint_numbers_are_linear tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_plan_and_operator_cover_pm_memory_trace_titles`：
  `2 passed`。
- `git diff --check`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不啟動 Phase 1/2/3/4/5
runtime、不送 paper order、不做 cancel/replace、不匯入 fill、不做 DB apply、不啟動
evidence writer、不啟動 evidence clock、不啟動 scorecard writer、不做 Linux runtime
sync/restart、不授權 tiny-live/live 或任何 Bybit behavior change。

## 51. 2026-06-30 PM session source checkpoint：FastAPI IPC Method Allowlist Guard

本 checkpoint 強化 Stock/ETF FastAPI 到 Rust IPC 的 readonly method 邊界。前面
已經鎖住 route handler inputs 與 `params={}`；這次再鎖住 `ipc.call(...)` 的 method
identity，避免未來把 paper preview/submit/cancel/replace、fill import、shadow
evaluation、readonly-probe preview 或其他非 status/readiness IPC method 接到 GET/status
surface。

已完成：

- 新增 `test_stock_etf_routes_call_only_readonly_status_ipc_methods`。
- 測試解析 `stock_etf_routes.py` 的 `_..._METHOD` constants。
- 每個 `ipc.call(...)` 必須使用 named method constant。
- resolved method set 必須精確等於 readonly Stock/ETF status/readiness IPC allowlist。
- 本 guard 不改 route behavior、不新增 endpoint、不改 IPC method、不啟動 runtime，只防
  non-status IPC method 被接到 FastAPI display/status surface。

驗證：

- `python3 -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py`：
  `8 passed`。
- `python3 -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf*.py`：
  `102 passed`。
- `python3 -m pytest -q tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_pm_checkpoint_numbers_are_linear tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_plan_and_operator_cover_pm_memory_trace_titles`：
  `2 passed`。
- `git diff --check`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不啟動 Phase 1/2/3/4/5
runtime、不送 paper order、不做 cancel/replace、不匯入 fill、不做 DB apply、不啟動
evidence writer、不啟動 evidence clock、不啟動 scorecard writer、不做 Linux runtime
sync/restart、不授權 tiny-live/live 或任何 Bybit behavior change。

## 52. 2026-06-30 PM session source checkpoint：Python Persistence Static Guard

本 checkpoint 強化 Stock/ETF / IBKR Python source surface 的 no persistence/no writer
邊界。前面已經禁止 broker/network imports 與 FastAPI method drift；這次明確防止
Stock/ETF / IBKR Python surface 直接接入 DB、object store、本地 persistence/evidence
writer 或文件寫入 API。

已完成：

- 新增 `test_stock_etf_ibkr_python_surface_has_no_persistence_or_file_writers`。
- 掃描 scoped Stock/ETF / IBKR Python files。
- 禁止 DB/persistence/object-store imports：psycopg/psycopg2/sqlalchemy/sqlite3/
  asyncpg/duckdb/redis/boto3 等。
- 禁止 local persistence/evidence-writer imports：`db_pool`、`audit_persistence`、
  `state_store`、`agent_event_store` 等。
- 禁止 dynamic persistence imports。
- 禁止明確 file writer calls：`write_text`、`write_bytes`、write-mode `open(...)`、
  `os.replace(...)` 等。
- 本 guard 不改 route behavior、不新增 endpoint、不改 IPC method、不啟動 runtime，只防
  Python surface 出現 DB/evidence writer 或本地文件寫入路徑。

驗證：

- `python3 -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py`：
  `9 passed`。
- `python3 -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf*.py`：
  `103 passed`。
- `python3 -m pytest -q tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_pm_checkpoint_numbers_are_linear tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_plan_and_operator_cover_pm_memory_trace_titles`：
  `2 passed`。
- `git diff --check`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不啟動 Phase 1/2/3/4/5
runtime、不送 paper order、不做 cancel/replace、不匯入 fill、不做 DB apply、不啟動
evidence writer、不啟動 evidence clock、不啟動 scorecard writer、不做 Linux runtime
sync/restart、不授權 tiny-live/live 或任何 Bybit behavior change。

## 53. 2026-06-30 PM session source checkpoint：OpenAPI Client Input Surface Guard

本 checkpoint 強化 Stock/ETF public OpenAPI contract 的 client-input 邊界。前面已經
鎖住 handler signature、IPC params 與 IPC method；這次把外部 schema 也鎖住，確保
GET/status surface 不宣告 request body、query/path/cookie/client header inputs。

已完成：

- 新增 `test_stock_etf_openapi_exposes_no_client_state_inputs`。
- 掃描所有 `/api/v1/stock-etf...` OpenAPI GET operations。
- 不允許 `requestBody`。
- parameters 只允許既有 auth 的 optional `Authorization` header。
- 本 guard 不改 route behavior、不新增 endpoint、不改 auth 實作、不啟動 runtime，只防
  public OpenAPI contract 出現 client-state-bearing inputs。

驗證：

- `python3 -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_routes.py`：
  `14 passed`。
- `python3 -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf*.py`：
  `104 passed`。
- `python3 -m pytest -q tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_pm_checkpoint_numbers_are_linear tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_plan_and_operator_cover_pm_memory_trace_titles`：
  `2 passed`。
- `git diff --check`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不啟動 Phase 1/2/3/4/5
runtime、不送 paper order、不做 cancel/replace、不匯入 fill、不做 DB apply、不啟動
evidence writer、不啟動 evidence clock、不啟動 scorecard writer、不做 Linux runtime
sync/restart、不授權 tiny-live/live 或任何 Bybit behavior change。

## 54. 2026-06-30 PM session source checkpoint：Rust Status IPC Untrusted Params Guard

本 checkpoint 把 client-state-untrusted 邊界往 Rust IPC status/readiness fixture 層
下沉。前面 FastAPI 已經鎖住 handler signature、OpenAPI input surface 與 `params={}`；
這次證明即使 direct IPC caller 帶入惡意非空 params，Stock/ETF status/readiness methods
也不會改變 output。

已完成：

- 新增 `stock_etf_status_methods_ignore_untrusted_params`。
- 覆蓋 16 個 Stock/ETF status/readiness methods。
- 每個 method 分別用 `{}` params 與惡意非空 params 呼叫。
- 惡意 params 宣稱 `asset_lane=crypto_perp`、`broker=bybit`、`environment=live`、
  `method=stock_etf.submit_paper_order`、IBKR contact、secret touch、order routing、
  Bybit IPC reuse。
- 兩次 result 必須完全一致，防止 direct IPC params 影響 status/readiness fixture。
- 本 guard 不改 handler runtime behavior、不新增 IPC method、不啟動 runtime，只防
  Rust status fixture 受 client params 污染。

驗證：

- `rustfmt --edition 2021 rust/openclaw_engine/src/ipc_server/tests/stock_etf.rs`：PASS。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_engine stock_etf_status_methods_ignore_untrusted_params -- --nocapture`：
  `1 passed`。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_engine stock_etf -- --nocapture`：
  `31 passed`。
- `python3 -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf*.py`：
  `104 passed`。
- `python3 -m pytest -q tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_pm_checkpoint_numbers_are_linear tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_plan_and_operator_cover_pm_memory_trace_titles`：
  `2 passed`。
- `git diff --check`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不啟動 Phase 1/2/3/4/5
runtime、不送 paper order、不做 cancel/replace、不匯入 fill、不做 DB apply、不啟動
evidence writer、不啟動 evidence clock、不啟動 scorecard writer、不做 Linux runtime
sync/restart、不授權 tiny-live/live 或任何 Bybit behavior change。

## 55. 2026-06-30 PM session source checkpoint：Rust Dispatch Registry Routing Guard

本 checkpoint 消除 Rust IPC Stock/ETF routing 的 duplicated method list。前面
`method_registry.rs` 已經記錄 Stock/ETF fixture metadata；但 `dispatch.rs` 仍有另一份
手寫 match list，未來新增/改名 method 時可能造成 registry、dispatch 與 live-token
exclusion drift。這次把 dispatch 路由改為 registry-driven。

已完成：

- 新增 `is_stock_etf_fixture_method(name)` registry helper。
- Helper 要求 method 必須是 registered `stock_etf.` method，且 `slot=None`。
- `dispatch.rs` 的 Stock/ETF arm 從 duplicated literal list 改為
  `method if is_stock_etf_fixture_method(method)`。
- 既有 debug assertion 仍檢查 slot 為 `None`。
- Registry tests 同步要求每個 Stock/ETF method 都被 helper 接受，且 legacy
  `submit_paper_order` / unknown method 不會被 helper 接受。
- 本 checkpoint 不新增 IPC method、不改 Stock/ETF handler、不改 legacy Bybit
  `submit_paper_order` path、不啟動 runtime，只降低 method routing drift。

驗證：

- `rustfmt --edition 2021 rust/openclaw_engine/src/ipc_server/dispatch.rs rust/openclaw_engine/src/ipc_server/method_registry.rs`：PASS。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_engine stock_etf -- --nocapture`：
  `31 passed`。
- `python3 -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf*.py`：
  `104 passed`。
- `python3 -m pytest -q tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_pm_checkpoint_numbers_are_linear tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_plan_and_operator_cover_pm_memory_trace_titles`：
  `2 passed`。
- `git diff --check`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不啟動 Phase 1/2/3/4/5
runtime、不送 paper order、不做 cancel/replace、不匯入 fill、不做 DB apply、不啟動
evidence writer、不啟動 evidence clock、不啟動 scorecard writer、不做 Linux runtime
sync/restart、不授權 tiny-live/live 或任何 Bybit behavior change。

## 56. 2026-06-30 PM session source checkpoint：GUI Data/Policy Fallback Split Guard

本 checkpoint 降低 Stock/ETF GUI 主 bundle 的結構風險。`tab-stock-etf.js` 已接近
repo 2000 行 hard cap（1976 行），後續新增狀態面板很容易再次違反治理線；這次只拆
Data Foundation / Policy 的大型 fallback payload，不改 endpoint、不改 renderer、不改
load flow。

已完成：

- 新增 `tab-stock-etf-data-policy.js`，承載 `dataFoundationFallback(...)` 與
  `policyFallback(...)`。
- `tab-stock-etf.html` 在主 `tab-stock-etf.js` 前載入 data/policy split。
- `tab-stock-etf.js` 從 `1976` 行降到 `1805` 行；新增檔為 `170` 行。
- 更新 Stock/ETF static no-write guard，掃描新 JS 檔。
- 新增 `test_stock_etf_static_gui_files_stay_below_line_cap`，要求 Stock/ETF GUI
  bundle 每個檔案都不超過 2000 行。
- 本 checkpoint 不新增 API endpoint、不新增 IPC method、不改 Rust/FastAPI status
  contract，只做 display-only GUI bundle hygiene。

驗證：

- `node --check` on Stock/ETF JS bundle：PASS。
- `python3 -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py`：
  `10 passed`。
- `python3 -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf*.py`：
  `105 passed`。
- `python3 -m pytest -q tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_pm_checkpoint_numbers_are_linear tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_plan_and_operator_cover_pm_memory_trace_titles`：
  `2 passed`。
- `git diff --check`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不啟動 Phase 1/2/3/4/5
runtime、不送 paper order、不做 cancel/replace、不匯入 fill、不做 DB apply、不啟動
evidence writer、不啟動 evidence clock、不啟動 scorecard writer、不做 Linux runtime
sync/restart、不授權 tiny-live/live 或任何 Bybit behavior change。

## 57. 2026-06-30 PM session source checkpoint：Rust IPC Test Split Guard

本 checkpoint 降低 Stock/ETF Rust IPC 測試檔的結構風險。`stock_etf.rs` 已超過
2000 行 governance cap；這次只拆測試模組，把尾端 status fixture regressions 放到
子模組，不改 handler、不改 dispatch、不新增 IPC method、不啟動 runtime。

已完成：

- 新增 `rust/openclaw_engine/src/ipc_server/tests/stock_etf/status_fixtures.rs`。
- 搬移 Account/Reconciliation/Scorecard/Launch/Release/Disable status fixture tests。
- 父檔 `stock_etf.rs` 從 `2532` 行降到 `1852` 行；子檔為 `685` 行。
- 父檔只新增 `mod status_fixtures;`，保留既有 helper 與 source-only fixture
  assertions。
- 新增 `tests/structure/test_stock_etf_ipc_tests_split_static.py`，要求父檔與子檔都不超過
  2000 行，並確認 moved fixture 不引入 IBKR SDK 或 socket/HTTP client token。
- 本 checkpoint 不改 runtime behavior、不改 Bybit path、不改 IBKR boundary，只做
  Rust test structure hygiene。

驗證：

- `rustfmt --edition 2021 rust/openclaw_engine/src/ipc_server/tests/stock_etf.rs rust/openclaw_engine/src/ipc_server/tests/stock_etf/status_fixtures.rs`：PASS。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_engine stock_etf -- --nocapture`：
  `31 passed`。
- `python3 -m pytest -q tests/structure/test_stock_etf_ipc_tests_split_static.py`：
  `2 passed`。
- `python3 -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf*.py`：
  `105 passed`。
- `python3 -m pytest -q tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_pm_checkpoint_numbers_are_linear tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_plan_and_operator_cover_pm_memory_trace_titles`：
  `2 passed`。
- `git diff --check`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不啟動 Phase 1/2/3/4/5
runtime、不送 paper order、不做 cancel/replace、不匯入 fill、不做 DB apply、不啟動
evidence writer、不啟動 evidence clock、不啟動 scorecard writer、不做 Linux runtime
sync/restart、不授權 tiny-live/live 或任何 Bybit behavior change。

## 58. 2026-06-30 PM session source checkpoint：Rust IPC Handler Split Guard

本 checkpoint 降低 Stock/ETF Rust IPC handler 的結構風險。`handlers/stock_etf.rs`
已超過 2000 行 hard cap；這次只拆 tail status summary builder，不改 handler
入口、不改 dispatch、不新增 IPC method、不改 request envelope parsing、不啟動 runtime。

已完成：

- 新增 `rust/openclaw_engine/src/ipc_server/handlers/stock_etf/status_summaries.rs`。
- 搬移 Account/Reconciliation/Scorecard/Launch/Release/Disable/Paper/Shadow/Universe/Evidence
  status summary builders。
- 父檔 `stock_etf.rs` 從 `2217` 行降到 `1292` 行；子檔為 `934` 行。
- 父檔只新增 `mod status_summaries;` 與明確 imports，保留 IPC 入口、readiness、
  Phase2 precontact、operation selection、request envelope parsing。
- 新增 `tests/structure/test_stock_etf_ipc_handler_split_static.py`，要求 handler 父檔
  與子檔都不超過 2000 行，並確認 moved builders 不引入 IBKR SDK 或 socket/HTTP
  client token。
- 本 checkpoint 不改 runtime behavior、不改 Bybit path、不改 IBKR boundary，只做
  Rust handler structure hygiene。

驗證：

- `rustfmt --edition 2021 rust/openclaw_engine/src/ipc_server/handlers/stock_etf.rs rust/openclaw_engine/src/ipc_server/handlers/stock_etf/status_summaries.rs`：PASS。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_engine stock_etf -- --nocapture`：
  `31 passed`。
- `python3 -m pytest -q tests/structure/test_stock_etf_ipc_handler_split_static.py tests/structure/test_stock_etf_ipc_tests_split_static.py`：
  `4 passed`。
- `python3 -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf*.py`：
  `105 passed`。
- `python3 -m pytest -q tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_pm_checkpoint_numbers_are_linear tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_plan_and_operator_cover_pm_memory_trace_titles`：
  `2 passed`。
- `git diff --check`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不啟動 Phase 1/2/3/4/5
runtime、不送 paper order、不做 cancel/replace、不匯入 fill、不做 DB apply、不啟動
evidence writer、不啟動 evidence clock、不啟動 scorecard writer、不做 Linux runtime
sync/restart、不授權 tiny-live/live 或任何 Bybit behavior change。

## 59. 2026-06-30 PM session source checkpoint：Route Fixture Split Guard

本 checkpoint 降低 Stock/ETF FastAPI route fixture 的結構風險。前一輪 route
tests 拆分後，共用 fixture helper 已重新成長到 1525 行；這次只拆 test
fixture payload，不改 production route、不改 endpoint、不改 IPC method、不啟動
runtime。

已完成：

- 移除 legacy flat helper
  `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/stock_etf_route_fixtures.py`。
- 新增同名 package
  `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/stock_etf_route_fixtures/`。
- 依責任切分為 `app.py`、`phase2_payloads.py`、`phase3_payloads.py`、
  `phase5_payloads.py`，由 `__init__.py` 維持原有 re-export surface。
- 既有 tests 的 `from stock_etf_route_fixtures import ...` import surface 不變。
- 拆分後模組行數為 `57`、`63`、`482`、`629`、`364`，全部低於 800 行
  review-attention threshold。
- 新增 `tests/structure/test_stock_etf_route_fixtures_split_static.py`，要求 legacy
  flat helper 保持移除、package module/export surface 穩定，並阻止 payload fixture
  模組引入 network / IBKR SDK / file-write token。
- 本 checkpoint 不改 runtime behavior、不改 Bybit path、不改 IBKR boundary，只做
  FastAPI route test fixture structure hygiene。

驗證：

- `python3 -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/tests/stock_etf_route_fixtures/*.py`：
  PASS。
- `python3 -m pytest -q tests/structure/test_stock_etf_route_fixtures_split_static.py`：
  `3 passed`。
- `python3 -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf*.py`：
  `105 passed`。
- `python3 -m pytest -q tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_pm_checkpoint_numbers_are_linear tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_plan_and_operator_cover_pm_memory_trace_titles`：
  `2 passed`。
- `git diff --check`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不啟動 Phase 1/2/3/4/5
runtime、不送 paper order、不做 cancel/replace、不匯入 fill、不做 DB apply、不啟動
evidence writer、不啟動 evidence clock、不啟動 scorecard writer、不做 Linux runtime
sync/restart、不授權 tiny-live/live 或任何 Bybit behavior change。

## 60. 2026-06-30 PM session source checkpoint：Rust IPC Request Contract Test Split Guard

本 checkpoint 進一步降低 Stock/ETF Rust IPC 測試父檔的結構風險。第 57 輪已拆出
tail status fixture tests；這次只拆 paper/fill/shadow/readonly-probe request
contract tests，不改 handler、不改 dispatch、不新增 IPC method、不啟動 runtime。

已完成：

- 新增 `rust/openclaw_engine/src/ipc_server/tests/stock_etf/request_contracts.rs`。
- 搬移 paper order request envelope、paper fill import request、shadow signal request、
  readonly probe request、legacy paper route channel boundary、live typed denial tests。
- 父檔 `stock_etf.rs` 從 `1852` 行降到 `1110` 行。
- 新子檔 `request_contracts.rs` 為 `745` 行；既有 `status_fixtures.rs` 保持
  `685` 行。
- 父檔只新增 `mod request_contracts;`，保留 readiness / lane / phase0 / phase2 /
  phase3 status regressions 與共用 helper。
- 更新 `tests/structure/test_stock_etf_ipc_tests_split_static.py`，要求 Stock/ETF Rust
  IPC test module set 固定為 `request_contracts.rs` 與 `status_fixtures.rs`，並把
  父/子檔 line cap 收緊到 `1200`。
- Guard 同時確認 request-contract 子模組保留 paper/fill/shadow/readonly-probe method
  覆蓋，並阻止 moved fixture 檔引入 IBKR SDK 或 socket/HTTP client token。
- 本 checkpoint 不改 runtime behavior、不改 Bybit path、不改 IBKR boundary，只做
  Rust IPC test structure hygiene。

驗證：

- `rustfmt --edition 2021 rust/openclaw_engine/src/ipc_server/tests/stock_etf.rs rust/openclaw_engine/src/ipc_server/tests/stock_etf/request_contracts.rs rust/openclaw_engine/src/ipc_server/tests/stock_etf/status_fixtures.rs`：
  PASS。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_engine stock_etf -- --nocapture`：
  `31 passed`。
- `python3 -m pytest -q tests/structure/test_stock_etf_ipc_tests_split_static.py`：
  `3 passed`。
- `python3 -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf*.py`：
  `105 passed`。
- `python3 -m pytest -q tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_pm_checkpoint_numbers_are_linear tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_plan_and_operator_cover_pm_memory_trace_titles`：
  `2 passed`。
- `git diff --check`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不啟動 Phase 1/2/3/4/5
runtime、不送 paper order、不做 cancel/replace、不匯入 fill、不做 DB apply、不啟動
evidence writer、不啟動 evidence clock、不啟動 scorecard writer、不做 Linux runtime
sync/restart、不授權 tiny-live/live 或任何 Bybit behavior change。

## 61. 2026-06-30 PM session source checkpoint：Rust IPC Handler Request Summary Split Guard

本 checkpoint 進一步降低 Stock/ETF Rust IPC production handler 的結構風險。第 58 輪
已拆出 tail status summary builders；這次只拆 request parsing 與 source-only request
summary helpers，不改 handler 入口、不改 dispatch、不新增 IPC method、不改 status
payload、不啟動 runtime。

已完成：

- 新增 `rust/openclaw_engine/src/ipc_server/handlers/stock_etf/request_summaries.rs`。
- 搬移 `operation_for_method_and_params`、`request_from_params`、
  `paper_request_envelope_summary`、`fill_import_request_summary`、
  `shadow_signal_request_summary`、`readonly_probe_request_ipc_summary` 與其私有 helper。
- 父檔 `stock_etf.rs` 從 `1292` 行降到 `823` 行。
- 新子檔 `request_summaries.rs` 為 `477` 行；既有 `status_summaries.rs` 保持
  `934` 行。
- 父檔只新增 `mod request_summaries;` 與明確 imports，保留 IPC 入口、readiness、
  Phase0/Phase2/authorization/data/policy status summaries。
- 更新 `tests/structure/test_stock_etf_ipc_handler_split_static.py`，要求 Stock/ETF
  handler module set 固定為 `request_summaries.rs` 與 `status_summaries.rs`，並把
  父/子檔 line cap 收緊到 `1200`。
- Guard 同時確認 request summary helpers 在子模組，並阻止子模組引入 IBKR SDK 或
  socket/HTTP client token。
- 本 checkpoint 不改 runtime behavior、不改 Bybit path、不改 IBKR boundary，只做
  Rust IPC handler structure hygiene。

驗證：

- `rustfmt --check --edition 2021 rust/openclaw_engine/src/ipc_server/handlers/stock_etf.rs rust/openclaw_engine/src/ipc_server/handlers/stock_etf/request_summaries.rs rust/openclaw_engine/src/ipc_server/handlers/stock_etf/status_summaries.rs`：
  PASS。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_engine stock_etf -- --nocapture`：
  `31 passed`。
- `python3 -B -m pytest -q tests/structure/test_stock_etf_ipc_handler_split_static.py tests/structure/test_stock_etf_ipc_tests_split_static.py`：
  `6 passed`。
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf*.py`：
  `105 passed`。
- `python3 -B -m pytest -q tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_pm_checkpoint_numbers_are_linear tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_plan_and_operator_cover_pm_memory_trace_titles`：
  `2 passed`。
- `git diff --check`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不啟動 Phase 1/2/3/4/5
runtime、不送 paper order、不做 cancel/replace、不匯入 fill、不做 DB apply、不啟動
evidence writer、不啟動 evidence clock、不啟動 scorecard writer、不做 Linux runtime
sync/restart、不授權 tiny-live/live 或任何 Bybit behavior change。

## 62. 2026-06-30 PM session source checkpoint：FastAPI Route IPC Query Helper Guard

本 checkpoint 降低 Stock/ETF FastAPI route IPC query 重複邏輯風險。這是行為不變的
source hygiene：不新增 endpoint、不新增 IPC method、不改 normalizer、不引入
client-state input、不啟動 runtime。

已完成：

- 將 `stock_etf_routes.py` 內 16 個重複的 `_query_stock_etf_*` IPC status helper
  收斂為單一 `_query_stock_etf_status(ipc, method)`。
- 既有 endpoint、auth dependency、no-store headers、method constants、normalizer、
  response envelope 與 OpenAPI GET-only surface 不變。
- `stock_etf_routes.py` 從 `587` 行降到 `393` 行。
- 更新 `test_stock_etf_python_no_write_static_guard.py`：
  - 確認只有一個 `ipc.call(method, params={})` 呼叫點。
  - 確認 16 個 route handler 只能以 allowlisted readonly Stock/ETF method
    constant 呼叫 central helper。
  - 繼續禁止 write IPC method、IBKR SDK import、network client、persistence、
    file writer、client-state route args。
- 本 checkpoint 不改 runtime behavior、不改 Bybit path、不改 IBKR boundary，只做
  FastAPI route query structure hygiene。

驗證：

- `python3 -B -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/app/stock_etf_routes.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py`：
  PASS。
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_routes.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py`：
  `24 passed`。
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf*.py`：
  `105 passed`。
- `python3 -B -m pytest -q tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_pm_checkpoint_numbers_are_linear tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_plan_and_operator_cover_pm_memory_trace_titles`：
  `2 passed`。
- `git diff --check`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不啟動 Phase 1/2/3/4/5
runtime、不送 paper order、不做 cancel/replace、不匯入 fill、不做 DB apply、不啟動
evidence writer、不啟動 evidence clock、不啟動 scorecard writer、不做 Linux runtime
sync/restart、不授權 tiny-live/live 或任何 Bybit behavior change。

## 63. 2026-07-01 PM session source checkpoint：GUI Fallback Payload Split Guard

本 checkpoint 降低 Stock/ETF 靜態 GUI 主 bundle 的結構風險。這是顯示層 source
hygiene：不新增 endpoint、不新增 IPC method、不改 renderer、不引入 client-state
input、不啟動 runtime。

已完成：

- 新增 `tab-stock-etf-fallbacks.js`。
- 將 authorization、account、evidence、universe、shadow、paper、scorecard、launch
  fallback payload builders 從 `tab-stock-etf.js` 搬到新 fallback 模組。
- `tab-stock-etf.js` 從 `1805` 行降到 `1244` 行。
- 新 fallback 模組為 `563` 行，且 HTML 在主 loader 前載入它。
- 既有 endpoint constants、renderer、`ocApi(... GET ...)` 載入流程、auth/no-store
  route 行為、display-only fallback payload 字段不變。
- 更新 `test_stock_etf_python_no_write_static_guard.py`：
  - 新 fallback 模組納入 Stock/ETF static GUI no-write 掃描。
  - 確認大型 fallback builders 只存在於新模組，不回流主 bundle。
  - 將 `tab-stock-etf.js` cap 收緊為 `<= 1400`，新 fallback 模組 cap 為 `<= 800`。
- 更新 `test_stock_etf_routes.py`，讓 readonly display test 拼接 data-policy 與
  fallback 子模組，避免分檔後漏掃 scorecard / launch evidence tokens。
- 本 checkpoint 不改 runtime behavior、不改 Bybit path、不改 IBKR boundary，只做
  Stock/ETF GUI fallback payload structure hygiene。

驗證：

- `node --check` on Stock/ETF GUI JS modules：PASS。
- `python3 -B -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_routes.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py`：
  PASS。
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_routes.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py`：
  `25 passed`。
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf*.py`：
  `106 passed`。
- `python3 -B -m pytest -q tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_pm_checkpoint_numbers_are_linear tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_plan_and_operator_cover_pm_memory_trace_titles`：
  `2 passed`。
- `git diff --check`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不啟動 Phase 1/2/3/4/5
runtime、不送 paper order、不做 cancel/replace、不匯入 fill、不做 DB apply、不啟動
evidence writer、不啟動 evidence clock、不啟動 scorecard writer、不做 Linux runtime
sync/restart、不授權 tiny-live/live 或任何 Bybit behavior change。

## 64. 2026-07-01 PM session source checkpoint：GUI Data/Policy Renderer Split Guard

本 checkpoint 進一步降低 Stock/ETF 靜態 GUI 主 bundle 的結構風險。這是顯示層
source hygiene：不新增 endpoint、不新增 IPC method、不改 data/policy payload、不引入
client-state input、不啟動 runtime。

已完成：

- 將 `renderDataFoundationStatus` 與 `renderPolicyStatus` 從 `tab-stock-etf.js`
  搬到既有 `tab-stock-etf-data-policy.js`。
- `tab-stock-etf-data-policy.js` 現在同時保存 Data Foundation / Policy fallback
  payload builders 與其 renderers。
- `tab-stock-etf.js` 從 `1244` 行降到 `985` 行。
- `tab-stock-etf-data-policy.js` 從 `170` 行增至 `469` 行，並補齊與其他 split
  modules 一致的本地 display helper。
- 更新 HTML cache-bust，確保瀏覽器載入包含 renderers 的 data-policy 子模組。
- 更新 `test_stock_etf_python_no_write_static_guard.py`：
  - 確認 `renderDataFoundationStatus` 與 `renderPolicyStatus` 只存在於
    `tab-stock-etf-data-policy.js`。
  - 將 `tab-stock-etf.js` cap 收緊為 `<= 1100`。
  - 將 `tab-stock-etf-data-policy.js` cap 設為 `<= 700`。
- 本 checkpoint 不改 runtime behavior、不改 Bybit path、不改 IBKR boundary，只做
  Stock/ETF GUI data/policy renderer structure hygiene。

驗證：

- `node --check` on Stock/ETF GUI JS modules：PASS。
- `python3 -B -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_routes.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py`：
  PASS。
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_routes.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py`：
  `26 passed`。
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf*.py`：
  `107 passed`。
- `python3 -B -m pytest -q tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_pm_checkpoint_numbers_are_linear tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_plan_and_operator_cover_pm_memory_trace_titles`：
  `2 passed`。
- `git diff --check`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不啟動 Phase 1/2/3/4/5
runtime、不送 paper order、不做 cancel/replace、不匯入 fill、不做 DB apply、不啟動
evidence writer、不啟動 evidence clock、不啟動 scorecard writer、不做 Linux runtime
sync/restart、不授權 tiny-live/live 或任何 Bybit behavior change。

## 65. 2026-07-01 PM session source checkpoint：GUI Authorization/Account Renderer Split Guard

本 checkpoint 進一步降低 Stock/ETF 靜態 GUI 主 bundle 的結構風險。這是顯示層
source hygiene：不新增 endpoint、不新增 IPC method、不改 authorization/account
payload、不引入 client-state input、不啟動 runtime。

已完成：

- 新增 `tab-stock-etf-auth-account.js`。
- 將 `renderAuthorizationStatus` 與 `renderAccountStatus` 從 `tab-stock-etf.js`
  搬到新 auth/account 模組。
- 新模組以 `window.renderAuthorizationStatus` 與 `window.renderAccountStatus`
  暴露 renderer 給主 loader。
- `tab-stock-etf.js` 從 `985` 行降到 `798` 行。
- 新 auth/account 模組為 `235` 行，並在 HTML 中於 fallback module 後、主 loader
  前載入。
- 更新 `test_stock_etf_python_no_write_static_guard.py`：
  - 新 auth/account 模組納入 Stock/ETF static GUI no-write 掃描。
  - 確認 `renderAuthorizationStatus` 與 `renderAccountStatus` 只存在於
    `tab-stock-etf-auth-account.js`。
  - 將 `tab-stock-etf.js` cap 收緊為 `<= 900`。
  - 將 `tab-stock-etf-auth-account.js` cap 設為 `<= 400`。
- 更新 `test_stock_etf_routes.py`，讓 readonly display test 拼接 auth/account
  子模組，避免分檔後漏掃 authorization/account evidence tokens。
- 本 checkpoint 不改 runtime behavior、不改 Bybit path、不改 IBKR boundary，只做
  Stock/ETF GUI authorization/account renderer structure hygiene。

驗證：

- `node --check` on Stock/ETF GUI JS modules：PASS。
- `python3 -B -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_routes.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py`：
  PASS。
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_routes.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py`：
  `27 passed`。
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf*.py`：
  `108 passed`。
- `python3 -B -m pytest -q tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_pm_checkpoint_numbers_are_linear tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_plan_and_operator_cover_pm_memory_trace_titles`：
  `2 passed`。
- `git diff --check`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不啟動 Phase 1/2/3/4/5
runtime、不送 paper order、不做 cancel/replace、不匯入 fill、不做 DB apply、不啟動
evidence writer、不啟動 evidence clock、不啟動 scorecard writer、不做 Linux runtime
sync/restart、不授權 tiny-live/live 或任何 Bybit behavior change。

## 66. 2026-07-01 PM session source checkpoint：GUI Evidence/Paper Renderer Split Guard

本 checkpoint 進一步降低 Stock/ETF 靜態 GUI 主 bundle 的結構風險。這是顯示層
source hygiene：不新增 endpoint、不新增 IPC method、不改 evidence/universe/shadow/paper
payload、不引入 client-state input、不啟動 runtime。

已完成：

- 新增 `tab-stock-etf-evidence-paper.js`。
- 將 `renderEvidenceStatus`、`renderUniverseStatus`、`renderShadowStatus` 與
  `renderPaperStatus` 從 `tab-stock-etf.js` 搬到新 evidence/paper 模組。
- 新模組以 `window.renderEvidenceStatus`、`window.renderUniverseStatus`、
  `window.renderShadowStatus` 與 `window.renderPaperStatus` 暴露 renderer 給主 loader。
- `tab-stock-etf.js` 從 `798` 行降到 `583` 行。
- 新 evidence/paper 模組為 `265` 行，並在 HTML 中於 auth/account module 後、主
  loader 前載入。
- 更新 `test_stock_etf_python_no_write_static_guard.py`：
  - 新 evidence/paper 模組納入 Stock/ETF static GUI no-write 掃描。
  - 確認 Evidence / Universe / Shadow / Paper renderers 只存在於
    `tab-stock-etf-evidence-paper.js`。
  - 將 `tab-stock-etf.js` cap 收緊為 `<= 650`。
  - 將 `tab-stock-etf-evidence-paper.js` cap 設為 `<= 500`。
- 更新 `test_stock_etf_routes.py`，讓 readonly display test 拼接 evidence/paper
  子模組，避免分檔後漏掃 evidence / universe / shadow / paper display tokens。
- 本 checkpoint 不改 runtime behavior、不改 Bybit path、不改 IBKR boundary，只做
  Stock/ETF GUI evidence/paper renderer structure hygiene。

驗證：

- `node --check` on Stock/ETF GUI JS modules：PASS。
- `python3 -B -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_routes.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py`：
  PASS。
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_routes.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py`：
  `28 passed`。
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf*.py`：
  `109 passed`。
- `python3 -B -m pytest -q tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_pm_checkpoint_numbers_are_linear tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_plan_and_operator_cover_pm_memory_trace_titles`：
  `2 passed`。
- `git diff --check`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不啟動 Phase 1/2/3/4/5
runtime、不送 paper order、不做 cancel/replace、不匯入 fill、不做 DB apply、不啟動
evidence writer、不啟動 evidence clock、不啟動 scorecard writer、不做 Linux runtime
sync/restart、不授權 tiny-live/live 或任何 Bybit behavior change。

## 67. 2026-07-01 PM session source checkpoint：GUI Scorecard/Launch Renderer Split Guard

本 checkpoint 進一步降低 Stock/ETF 靜態 GUI 主 bundle 的結構風險。這是顯示層
source hygiene：不新增 endpoint、不新增 IPC method、不改 scorecard/launch payload、
不引入 client-state input、不啟動 runtime。

已完成：

- 新增 `tab-stock-etf-scorecard-launch.js`。
- 將 `renderScorecardStatus` 與 `renderLaunchStatus` 從 `tab-stock-etf.js`
  搬到新 scorecard/launch 模組。
- 新模組以 `window.renderScorecardStatus` 與 `window.renderLaunchStatus`
  暴露 renderer 給主 loader。
- `tab-stock-etf.js` 從 `583` 行降到 `350` 行。
- 新 scorecard/launch 模組為 `281` 行，並在 HTML 中於 evidence/paper module 後、
  主 loader 前載入。
- 更新 `test_stock_etf_python_no_write_static_guard.py`：
  - 新 scorecard/launch 模組納入 Stock/ETF static GUI no-write 掃描。
  - 確認 Scorecard / Launch renderers 只存在於
    `tab-stock-etf-scorecard-launch.js`。
  - 將 `tab-stock-etf.js` cap 收緊為 `<= 400`。
  - 將 `tab-stock-etf-scorecard-launch.js` cap 設為 `<= 500`。
- 更新 `test_stock_etf_routes.py`，讓 readonly display test 拼接 scorecard/launch
  子模組，避免分檔後漏掃 scorecard / launch / release denial tokens。
- 本 checkpoint 不改 runtime behavior、不改 Bybit path、不改 IBKR boundary，只做
  Stock/ETF GUI scorecard/launch renderer structure hygiene。

驗證：

- `node --check` on Stock/ETF GUI JS modules：PASS。
- `python3 -B -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_routes.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py`：
  PASS。
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_routes.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py`：
  `29 passed`。
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf*.py`：
  `110 passed`。
- `python3 -B -m pytest -q tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_pm_checkpoint_numbers_are_linear tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_plan_and_operator_cover_pm_memory_trace_titles`：
  `2 passed`。
- `git diff --check`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不啟動 Phase 1/2/3/4/5
runtime、不送 paper order、不做 cancel/replace、不匯入 fill、不做 DB apply、不啟動
evidence writer、不啟動 evidence clock、不啟動 scorecard writer、不做 Linux runtime
sync/restart、不授權 tiny-live/live 或任何 Bybit behavior change。

## 68. 2026-07-01 PM session source checkpoint：GUI Readiness Renderer Split Guard

本 checkpoint 將 Stock/ETF 靜態 GUI 主 bundle 收斂為 endpoint/fallback/load
orchestrator。這是顯示層 source hygiene：不新增 endpoint、不新增 IPC method、不改
readiness payload、不引入 client-state input、不啟動 runtime。

已完成：

- 新增 `tab-stock-etf-readiness.js`。
- 將 `renderReadiness` 與其本地 UI helpers 從 `tab-stock-etf.js` 搬到新 readiness
  模組。
- 新模組以 `window.renderReadiness` 暴露 renderer 給主 loader 與 fallback path。
- `tab-stock-etf.js` 從 `350` 行降到 `197` 行。
- 新 readiness 模組為 `159` 行，並在 HTML 中於 data/policy module 前、主 loader
  前載入。
- 更新 `test_stock_etf_python_no_write_static_guard.py`：
  - 新 readiness 模組納入 Stock/ETF static GUI no-write 掃描。
  - 確認 `renderReadiness(data, laneStatus)` 只存在於 `tab-stock-etf-readiness.js`。
  - 確認 `toneFor` / `kvRow` 等 UI helper 不回流主 bundle。
  - 將 `tab-stock-etf.js` cap 收緊為 `<= 250`。
  - 將 `tab-stock-etf-readiness.js` cap 設為 `<= 250`。
- 更新 `test_stock_etf_routes.py`，讓 readonly display test 拼接 readiness 子模組，
  避免分檔後漏掃 lane / API allowlist / runtime guard display tokens。
- 本 checkpoint 不改 runtime behavior、不改 Bybit path、不改 IBKR boundary，只做
  Stock/ETF GUI readiness renderer structure hygiene。

驗證：

- `node --check` on Stock/ETF GUI JS modules：PASS。
- `python3 -B -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_routes.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py`：
  PASS。
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_routes.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py`：
  `30 passed`。
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf*.py`：
  `111 passed`。
- `python3 -B -m pytest -q tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_pm_checkpoint_numbers_are_linear tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_plan_and_operator_cover_pm_memory_trace_titles`：
  `2 passed`。
- `git diff --check`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不啟動 Phase 1/2/3/4/5
runtime、不送 paper order、不做 cancel/replace、不匯入 fill、不做 DB apply、不啟動
evidence writer、不啟動 evidence clock、不啟動 scorecard writer、不做 Linux runtime
sync/restart、不授權 tiny-live/live 或任何 Bybit behavior change。

## 69. 2026-07-01 PM session source checkpoint：Python Secret/Env Access Static Guard

本 checkpoint 將 Stock/ETF / IBKR Python source-only boundary 補上 secret/env
material access 的 AST 守衛。這不是 connector runtime，也不是 IBKR read probe；
目標是防止未來有人在 Python display/readiness surface 加入 env fallback、secret file
read 或 path material locator。

已完成：

- 更新 `test_stock_etf_python_no_write_static_guard.py`，新增
  `test_stock_etf_ibkr_python_surface_has_no_secret_or_env_material_access`。
- Guard 掃描 scoped Stock/ETF / IBKR Python files，包括 FastAPI Stock/ETF routes、
  Stock/ETF normalizers，以及 `program_code/broker_connectors/ibkr_connector/`。
- Guard 禁止 import `os`、`dotenv`、`getpass`、`keyring` 等 env/secret helper
  surface。
- Guard 禁止 `os.environ`、`getenv` / `os.getenv`、`getpass`、
  `load_dotenv`、`Path.home`、`expanduser`、`read_text`、`read_bytes` 與任意
  `open()` call。
- Guard 保留現有 display-only `secret_slot_contract` schema normalization；它可顯示
  blocked/serialized=false 欄位，但不可讀取 secret material。
- 本 checkpoint 不改 runtime behavior、不改 endpoint、不改 IPC method、不改 Bybit
  path、不啟動任何 IBKR 或 secret runtime。

驗證：

- `python3 -B -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py`：
  PASS。
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py`：
  `17 passed`。
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_routes.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py`：
  `31 passed`。
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf*.py`：
  `112 passed`。
- `python3 -B -m pytest -q tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_pm_checkpoint_numbers_are_linear tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_plan_and_operator_cover_pm_memory_trace_titles`：
  `2 passed`。
- `git diff --check`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不啟動 Phase 1/2/3/4/5
runtime、不送 paper order、不做 cancel/replace、不匯入 fill、不做 DB apply、不啟動
evidence writer、不啟動 evidence clock、不啟動 scorecard writer、不做 Linux runtime
sync/restart、不授權 tiny-live/live 或任何 Bybit behavior change。

## 70. 2026-07-01 PM session source checkpoint：Rust IPC Secret/Env Material Static Guard

本 checkpoint 將 Python secret/env material guard 的同級治理補到 Rust
Stock/ETF IPC source split files。這不是 Rust runtime behavior change，不改
handler output，不新增 IPC method；目標是防止未來在 Stock/ETF IPC handler/test
files 中加入 direct env bypass、secret file read、network/socket client 或 IBKR SDK。

已完成：

- 更新 `tests/structure/test_stock_etf_ipc_handler_split_static.py`：
  - 新增 `test_stock_etf_ipc_handler_files_have_no_runtime_material_readers`。
  - 掃描 `stock_etf.rs`、`request_summaries.rs`、`status_summaries.rs`。
  - 明確保留 parent handler 中唯一合法的
    `StockEtfFeatureFlags::from_env()` typed feature-flag path。
  - 禁止 `std::env` / `env::var`、`std::fs`、`File::open`、
    `read_to_string`、`include_str!` / `include_bytes!`、`std::net`、
    `TcpStream` / `UdpSocket`、`tokio::net`、`reqwest`、`hyper::`、`ureq`、
    `ibapi` / `ib_insync` / `IBApi`。
- 更新 `tests/structure/test_stock_etf_ipc_tests_split_static.py`：
  - 新增同級 runtime material reader guard，掃描 Rust parent IPC test 與
    `request_contracts.rs`、`status_fixtures.rs`。
- 本 checkpoint 不改 Rust production code、不改 endpoint、不改 IPC method、不改
  Bybit path、不啟動任何 IBKR 或 secret runtime。

驗證：

- `python3 -B -m py_compile tests/structure/test_stock_etf_ipc_handler_split_static.py tests/structure/test_stock_etf_ipc_tests_split_static.py`：
  PASS。
- `python3 -B -m pytest -q tests/structure/test_stock_etf_ipc_handler_split_static.py tests/structure/test_stock_etf_ipc_tests_split_static.py`：
  `8 passed`。
- `python3 -B -m pytest -q tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_pm_checkpoint_numbers_are_linear tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_plan_and_operator_cover_pm_memory_trace_titles`：
  `2 passed`。
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf*.py`：
  `112 passed`。
- `git diff --check`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不啟動 Phase 1/2/3/4/5
runtime、不送 paper order、不做 cancel/replace、不匯入 fill、不做 DB apply、不啟動
evidence writer、不啟動 evidence clock、不啟動 scorecard writer、不做 Linux runtime
sync/restart、不授權 tiny-live/live 或任何 Bybit behavior change。

## 71. 2026-07-01 PM session source checkpoint：Rust Feature Flag Env Allowlist Guard

本 checkpoint 鎖定 `StockEtfFeatureFlags::from_lookup` 的 env lookup contract。這不是
啟動 runtime，也不是新增 env 讀取；它只證明 typed feature flag reader 只查詢
允許的五個非 secret feature flag key，且全部 absent 時保持 default-off。

已完成：

- 更新 `rust/openclaw_types/tests/stock_etf_lane_acceptance.rs`：
  - 新增 `feature_flag_lookup_uses_exact_non_secret_env_allowlist`。
  - 用 `RefCell` 記錄 `from_lookup` 實際查詢的 key order。
  - 要求 exact allowlist：
    `OPENCLAW_STOCK_ETF_LANE_ENABLED`、
    `OPENCLAW_IBKR_READONLY_ENABLED`、
    `OPENCLAW_IBKR_PAPER_ENABLED`、
    `OPENCLAW_ASSET_LANE_DEFAULT`、
    `OPENCLAW_STOCK_ETF_SHADOW_ONLY`。
  - 驗證全部 key absent 時回到 `StockEtfFeatureFlags::default()`。
  - 驗證 allowlist key 不含 `secret`、`token`、`password`、`account`、`key`。
- 本 checkpoint 不改 production Rust code、不改 endpoint、不改 IPC method、不改
  Bybit path、不啟動任何 IBKR 或 secret runtime。

驗證：

- `rustfmt --edition 2021 rust/openclaw_types/tests/stock_etf_lane_acceptance.rs --check`：
  PASS。
- `cargo test --manifest-path rust/Cargo.toml -p openclaw_types --test stock_etf_lane_acceptance -- --nocapture`：
  `9 passed`。
- `python3 -B -m pytest -q tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_pm_checkpoint_numbers_are_linear tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_plan_and_operator_cover_pm_memory_trace_titles`：
  `2 passed`。
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf*.py`：
  `112 passed`。
- `git diff --check`：PASS。

註：`cargo fmt --manifest-path rust/Cargo.toml --all -- --check` 仍會因既有、非本
checkpoint 的 Rust workspace formatting drift 失敗；本 checkpoint 已用 file-scoped
`rustfmt --check` 驗證修改檔案。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不啟動 Phase 1/2/3/4/5
runtime、不送 paper order、不做 cancel/replace、不匯入 fill、不做 DB apply、不啟動
evidence writer、不啟動 evidence clock、不啟動 scorecard writer、不做 Linux runtime
sync/restart、不授權 tiny-live/live 或任何 Bybit behavior change。

## 72. 2026-07-01 PM session source checkpoint：IBKR Connector Preview Payload Guard

本 checkpoint 收緊 inert IBKR connector skeleton 的 display-only preview payload
contract。這不是 connector runtime，不導入 IBKR SDK，不開 network，不讀 secret，
也不新增 FastAPI endpoint 或 IPC method；目標是讓所有 skeleton preview 都明確
fail-closed，避免後續實作前被誤判為可連線或可操作。

已完成：

- 更新 `IbkrReadOnlyClient.connection_plan()`：
  - 補上 `surface_id=ibkr_stock_etf_readonly_connector_skeleton_v1`。
  - 補上 `accepted=false` 與 `status=blocked_source_only`。
  - 補上 `phase2_gate_not_accepted` 與 `connection_plan_blocked` blockers。
  - 保留 non-secret loopback descriptor 與所有 no-contact/no-secret/no-paper/no-live/
    no-Bybit-reuse flags。
- 更新 `test_stock_etf_ibkr_connector_skeleton.py`：
  - 新增 exact payload-shape regression。
  - 覆蓋 connection plan、readiness、account snapshot、market data、contract details、
    paper lifecycle、fill import 與 static fixture previews。
  - 固定所有 preview payload 為 secret-free、no network、no paper channel、no live、
    no broker write、no DB apply、no Bybit path reuse。
  - 驗證 blockers 去重，且所有 payload 保留 `phase2_gate_not_accepted`。
- 本 checkpoint 不改 Bybit path、不改 FastAPI Stock/ETF route、不改 Rust IPC、不啟動
  任何 IBKR/read-probe/paper/fill/evidence runtime。

驗證：

- `python3 -B -m py_compile program_code/broker_connectors/ibkr_connector/readonly_client.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_ibkr_connector_skeleton.py`：
  PASS。
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_ibkr_connector_skeleton.py`：
  `5 passed`。
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py`：
  `17 passed`。
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf*.py`：
  `113 passed`。
- `python3 -B -m pytest -q tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_pm_checkpoint_numbers_are_linear tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_plan_and_operator_cover_pm_memory_trace_titles`：
  `2 passed`。
- `git diff --check`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不啟動 Phase 1/2/3/4/5
runtime、不送 paper order、不做 cancel/replace、不匯入 fill、不做 DB apply、不啟動
evidence writer、不啟動 evidence clock、不啟動 scorecard writer、不做 Linux runtime
sync/restart、不授權 tiny-live/live 或任何 Bybit behavior change。

## 73. 2026-07-01 PM session source checkpoint：IBKR Connector Bybit Import Separation Guard

本 checkpoint 將 IBKR connector skeleton 與 Bybit/control-api runtime 的隔離變成
source guard。這不是 connector runtime，不改任何 Bybit module，不改 FastAPI route，
也不新增 endpoint/IPC method；目標是防止未來在
`program_code/broker_connectors/ibkr_connector/` 直接 import Bybit connector 或
control-api `app` 模組。

已完成：

- 更新 `test_stock_etf_ibkr_connector_skeleton.py`：
  - 新增 `test_ibkr_connector_skeleton_does_not_import_bybit_or_control_api_modules`。
  - 掃描 `program_code/broker_connectors/ibkr_connector/**/*.py`。
  - 禁止 direct import `app`、`bybit_connector`、
    `exchange_connectors.bybit_connector`、
    `program_code.exchange_connectors.bybit_connector`。
  - 禁止 literal dynamic import 透過 `__import__` 或
    `importlib.import_module` 載入上述 Bybit/control-api module prefix。
- Guard 保留 payload 欄位 `bybit_path_reused=false`，但禁止以 import 形式重用
  Bybit runtime/control-api code path。
- 本 checkpoint 不改 production behavior、不改 endpoint、不改 IPC method、不改 Bybit
  path、不啟動任何 IBKR 或 Bybit runtime。

驗證：

- `python3 -B -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_ibkr_connector_skeleton.py`：
  PASS。
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_ibkr_connector_skeleton.py`：
  `6 passed`。
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py`：
  `17 passed`。
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf*.py`：
  `114 passed`。
- `python3 -B -m pytest -q tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_pm_checkpoint_numbers_are_linear tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_plan_and_operator_cover_pm_memory_trace_titles`：
  `2 passed`。
- `git diff --check`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不啟動 Phase 1/2/3/4/5
runtime、不送 paper order、不做 cancel/replace、不匯入 fill、不做 DB apply、不啟動
evidence writer、不啟動 evidence clock、不啟動 scorecard writer、不做 Linux runtime
sync/restart、不授權 tiny-live/live 或任何 Bybit behavior change。

## 74. 2026-07-01 PM session source checkpoint：FastAPI IBKR Connector Runtime Wiring Guard

本 checkpoint 把未批准前「FastAPI/control-api 不得 wire/import IBKR connector
skeleton」固定為 source guard。這不是 connector runtime，不改 FastAPI route，不改
normalizer payload，不改 Bybit runtime；目標是防止 source-only connector skeleton
被提前接入 control-api startup path，避免不必要 coupling 與 runtime overhead。

已完成：

- 更新 `test_stock_etf_python_no_write_static_guard.py`：
  - 新增 `test_stock_etf_control_api_surface_does_not_import_ibkr_connector_runtime_skeleton`。
  - 新增 `_candidate_stock_etf_control_api_python_files()`，只掃描
    `control_api_v1/app` 下 Stock/ETF / IBKR production surface。
  - 禁止 production surface import
    `program_code.broker_connectors.ibkr_connector`、
    `broker_connectors.ibkr_connector` 或 bare `ibkr_connector`。
  - 禁止 literal dynamic import 透過 `__import__`、`import_module` 或
    `importlib.import_module` 載入 connector skeleton。
  - 保留 dedicated skeleton tests 對 package 的 import 權限。
- Shared dynamic import helper 現在同時支援 `importlib.import_module`，讓既有
  network/persistence guards 也覆蓋此形式。
- 本 checkpoint 不改 production behavior、不改 endpoint、不改 IPC method、不改 Bybit
  path、不啟動任何 IBKR 或 connector runtime。

驗證：

- `python3 -B -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py`：
  PASS。
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py`：
  `18 passed`。
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_ibkr_connector_skeleton.py`：
  `6 passed`。
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf*.py`：
  `115 passed`。
- `python3 -B -m pytest -q tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_pm_checkpoint_numbers_are_linear tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_plan_and_operator_cover_pm_memory_trace_titles`：
  `2 passed`。
- `git diff --check`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不啟動 Phase 1/2/3/4/5
runtime、不送 paper order、不做 cancel/replace、不匯入 fill、不做 DB apply、不啟動
evidence writer、不啟動 evidence clock、不啟動 scorecard writer、不做 Linux runtime
sync/restart、不授權 tiny-live/live 或任何 Bybit behavior change。

## 75. 2026-07-01 PM session source checkpoint：Rust IPC Bybit Runtime Separation Guard

本 checkpoint 把 Stock/ETF Rust IPC handler/test source 不得 import/call Bybit
runtime/order path 固定為 structure guard。這不是 Rust runtime 改動，不新增 IPC
method，不改 legacy Bybit `submit_paper_order` 行為；目標是防止 IBKR/Stock-ETF
source-only IPC 合約被未來改動接到 Bybit REST/WS/order manager/order router/paper
state runtime。

已完成：

- 更新 `tests/structure/test_stock_etf_ipc_handler_split_static.py`：
  - 新增 `FORBIDDEN_BYBIT_RUNTIME_TOKENS`。
  - 新增 handler source guard，掃描 `stock_etf.rs`、
    `stock_etf/request_summaries.rs`、`stock_etf/status_summaries.rs`。
  - 禁止 Bybit REST/WS/Earn module/client、order manager、order router、
    paper state、bounded-probe active-order module、`handle_submit_paper_order`
    與 direct order method call token。
- 更新 `tests/structure/test_stock_etf_ipc_tests_split_static.py`：
  - 同步禁止 Rust IPC fixture tests import/call Bybit runtime/order path。
  - 掃描 parent `stock_etf.rs`、`request_contracts.rs`、`status_fixtures.rs`。
- Guard 保留 contract/posture 層的顯式否定欄位，例如
  `bybit_ipc_reused=false`、`bybit_path_reused=false`、Bybit live execution
  unchanged，以及 legacy Bybit `submit_paper_order` channel regression；禁止的是
  source coupling/import/call，不是禁止 boundary text。
- 本 checkpoint 不改 production behavior、不改 endpoint、不改 IPC method、不改 Bybit
  path、不啟動任何 IBKR 或 connector runtime。

驗證：

- `python3 -B -m py_compile tests/structure/test_stock_etf_ipc_handler_split_static.py tests/structure/test_stock_etf_ipc_tests_split_static.py`：
  PASS。
- `python3 -B -m pytest -q tests/structure/test_stock_etf_ipc_handler_split_static.py tests/structure/test_stock_etf_ipc_tests_split_static.py`：
  `10 passed`。
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf*.py`：
  `115 passed`。
- `python3 -B -m pytest -q tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_pm_checkpoint_numbers_are_linear tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_plan_and_operator_cover_pm_memory_trace_titles`：
  `2 passed`。
- `git diff --check`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不啟動 Phase 1/2/3/4/5
runtime、不送 paper order、不做 cancel/replace、不匯入 fill、不做 DB apply、不啟動
evidence writer、不啟動 evidence clock、不啟動 scorecard writer、不做 Linux runtime
sync/restart、不授權 tiny-live/live 或任何 Bybit behavior change。

## 76. 2026-07-01 PM session source checkpoint：IBKR Connector Public API Freeze Guard

本 checkpoint 將 Python IBKR connector skeleton 的 package/class public surface 固定為
source-only API。這不是 connector runtime，不新增 IBKR call，不改 FastAPI route；目標是
避免未批准前在 skeleton package 上新增 runtime start、order write、secret/network 或
Bybit reuse 入口。

已完成：

- 更新 `test_stock_etf_ibkr_connector_skeleton.py`：
  - Import package module 本身，檢查 `ibkr_connector.__all__` exact order/content。
  - 新增 `EXPECTED_CONNECTOR_EXPORTS`，只允許 surface id、read-only client、
    paper boundary client、endpoint config、surface status。
  - 新增 `EXPECTED_READONLY_CLIENT_PUBLIC_SURFACE`，只允許 `config`、
    `readiness()`、`connection_plan()`、`account_snapshot_preview()`、
    `market_data_preview()`、`contract_details_preview()`。
  - 新增 `EXPECTED_PAPER_CLIENT_PUBLIC_SURFACE`，只允許
    `lifecycle_readiness()` 與 `fill_import_readiness()`。
  - 保留既有 forbidden write method guard；新增 exact public surface freeze，防止
    future write-like method 以不同名字進入 public class surface。
- 本 checkpoint 不改 production behavior、不改 endpoint、不改 IPC method、不改 Bybit
  path、不啟動任何 IBKR 或 connector runtime。

驗證：

- `python3 -B -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_ibkr_connector_skeleton.py`：
  PASS。
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_ibkr_connector_skeleton.py`：
  `8 passed`。
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py`：
  `18 passed`。
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf*.py`：
  `117 passed`。
- `python3 -B -m pytest -q tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_pm_checkpoint_numbers_are_linear tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_plan_and_operator_cover_pm_memory_trace_titles`：
  `2 passed`。
- `git diff --check`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不啟動 Phase 1/2/3/4/5
runtime、不送 paper order、不做 cancel/replace、不匯入 fill、不做 DB apply、不啟動
evidence writer、不啟動 evidence clock、不啟動 scorecard writer、不做 Linux runtime
sync/restart、不授權 tiny-live/live 或任何 Bybit behavior change。

## 77. 2026-07-01 PM session source checkpoint：Python Runtime Side-Effect Static Guard

本 checkpoint 將 Stock/ETF / IBKR Python scoped surface 的 clock、thread/concurrency、
subprocess side-effect boundary 固定為 AST guard。這不是 runtime behavior 改動，也不是
IBKR connector wiring；目標是讓 FastAPI normalizers、routes 與 inert connector skeleton
維持 deterministic display/source-only，避免未批准前引入 timer、sleep、thread、
async task、subprocess 或 background work。

已完成：

- 更新 `test_stock_etf_python_no_write_static_guard.py`：
  - 新增 `FORBIDDEN_RUNTIME_SIDE_EFFECT_MODULE_PREFIXES`，禁止 scoped surface import
    `time`、`datetime`、`asyncio`、`threading`、`multiprocessing`、`subprocess`、
    `concurrent`。
  - 新增 `FORBIDDEN_RUNTIME_SIDE_EFFECT_CALL_NAMES`，禁止 `time()`、`sleep()`、
    `monotonic()`、`perf_counter()`、`now()`、`utcnow()`、`fromtimestamp()`、
    `Thread()`、`Process()`、`Popen()`、`asyncio.run()`、`create_task()`、
    `to_thread()` 等 side-effect/timing calls。
  - 新增 `test_stock_etf_ibkr_python_surface_has_no_clock_or_concurrency_side_effects`，
    使用既有 scoped file list，只掃 Stock/ETF/IBKR Python surface 和 IBKR connector
    skeleton，不掃既有 Bybit runtime modules。
- 本 checkpoint 不改 production behavior、不改 endpoint、不改 IPC method、不改 Bybit
  path、不啟動任何 IBKR 或 connector runtime。

驗證：

- `python3 -B -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py`：
  PASS。
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py`：
  `19 passed`。
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_ibkr_connector_skeleton.py`：
  `8 passed`。
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf*.py`：
  `118 passed`。
- `python3 -B -m pytest -q tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_pm_checkpoint_numbers_are_linear tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_plan_and_operator_cover_pm_memory_trace_titles`：
  `2 passed`。
- `git diff --check`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不啟動 Phase 1/2/3/4/5
runtime、不送 paper order、不做 cancel/replace、不匯入 fill、不做 DB apply、不啟動
evidence writer、不啟動 evidence clock、不啟動 scorecard writer、不做 Linux runtime
sync/restart、不授權 tiny-live/live 或任何 Bybit behavior change。

## 78. 2026-07-01 PM session source checkpoint：Rust IPC Runtime Side-Effect Static Guard

本 checkpoint 將 Stock/ETF Rust IPC handler/test split files 的 clock、thread/task、
process side-effect boundary 固定為 structure guard。這不是 Rust runtime behavior
改動，也不是 IBKR connector wiring；目標是讓 Stock/ETF IPC source-only fixtures
維持 deterministic/no-background-work posture，避免未批准前引入 timer、sleep、
thread/task spawn 或 subprocess。

已完成：

- 更新 `tests/structure/test_stock_etf_ipc_handler_split_static.py`：
  - 新增 `FORBIDDEN_RUNTIME_SIDE_EFFECT_TOKENS`。
  - 新增 handler guard，掃描 `stock_etf.rs`、`request_summaries.rs`、
    `status_summaries.rs`。
  - 禁止 `std::time`、`SystemTime`、`Instant`、`chrono`、`Utc::now`、
    `Local::now`、`std::thread`、`thread::spawn`、`tokio::spawn`、
    `tokio::task`、`tokio::time`、`sleep(`、`std::process`、`Command::new`、
    `.spawn(` 等 side-effect tokens。
- 更新 `tests/structure/test_stock_etf_ipc_tests_split_static.py`：
  - 同步禁止 Rust IPC fixture tests 引入 clock/thread/task/process side effects。
  - 掃描 parent `stock_etf.rs`、`request_contracts.rs`、`status_fixtures.rs`。
- 本 checkpoint 不改 production behavior、不改 endpoint、不改 IPC method、不改 Bybit
  path、不啟動任何 IBKR 或 connector runtime。

驗證：

- `python3 -B -m py_compile tests/structure/test_stock_etf_ipc_handler_split_static.py tests/structure/test_stock_etf_ipc_tests_split_static.py`：
  PASS。
- `python3 -B -m pytest -q tests/structure/test_stock_etf_ipc_handler_split_static.py tests/structure/test_stock_etf_ipc_tests_split_static.py`：
  `12 passed`。
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf*.py`：
  `118 passed`。
- `python3 -B -m pytest -q tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_pm_checkpoint_numbers_are_linear tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_plan_and_operator_cover_pm_memory_trace_titles`：
  `2 passed`。
- `git diff --check`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不啟動 Phase 1/2/3/4/5
runtime、不送 paper order、不做 cancel/replace、不匯入 fill、不做 DB apply、不啟動
evidence writer、不啟動 evidence clock、不啟動 scorecard writer、不做 Linux runtime
sync/restart、不授權 tiny-live/live 或任何 Bybit behavior change。

## 79. 2026-07-01 PM session source checkpoint：GUI Background Work Static Guard

本 checkpoint 將 Stock/ETF static GUI 的 no-background-work posture 固定為 static
guard。這不是 GUI runtime activation，不新增 endpoint，不改 API call shape；目標是
避免 display-only Stock/ETF tab 在未批准前引入 polling、push channel、worker、
sendBeacon、XHR 或 high-frequency timing，保護 control-api/browser runtime 效率。

已完成：

- 更新 `test_stock_etf_python_no_write_static_guard.py`：
  - 新增 `FORBIDDEN_STATIC_GUI_BACKGROUND_SNIPPETS`。
  - 新增 `test_stock_etf_static_gui_has_no_background_polling_or_push_channels`。
  - 掃描 `tab-stock-etf*.js` 與 `tab-stock-etf.html`。
  - 禁止 `setInterval(`、`setTimeout(`、`requestAnimationFrame(`、
    `requestIdleCallback(`、`WebSocket(`、`EventSource(`、`new Worker(`、
    `new SharedWorker(`、`BroadcastChannel(`、`XMLHttpRequest`、
    `navigator.sendBeacon`、`performance.now(`、`Date.now(`。
  - 保留現有一次性 authenticated GET load path；現有 `new Date().toLocaleTimeString()`
    只作顯示時間，不啟動 background work。
- 本 checkpoint 不改 production behavior、不改 endpoint、不改 IPC method、不改 Bybit
  path、不啟動任何 IBKR 或 connector runtime。

驗證：

- `python3 -B -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py`：
  PASS。
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py`：
  `20 passed`。
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf*.py`：
  `119 passed`。
- `python3 -B -m pytest -q tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_pm_checkpoint_numbers_are_linear tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_plan_and_operator_cover_pm_memory_trace_titles`：
  `2 passed`。
- `git diff --check`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不啟動 Phase 1/2/3/4/5
runtime、不送 paper order、不做 cancel/replace、不匯入 fill、不做 DB apply、不啟動
evidence writer、不啟動 evidence clock、不啟動 scorecard writer、不做 Linux runtime
sync/restart、不授權 tiny-live/live 或任何 Bybit behavior change。

## 80. 2026-07-01 PM session source checkpoint：GUI One-Shot Fanout Budget Guard

本 checkpoint 將 Stock/ETF static GUI 的一次性 GET fanout budget 固定為 static
guard。這不是 GUI runtime activation，不新增 endpoint，不改 API call shape；目標是
避免 display-only Stock/ETF tab 在未批准前增加額外 API fanout、提高 timeout budget
或重複 loader，防止拖慢 control-api/browser runtime。

已完成：

- 更新 `test_stock_etf_python_no_write_static_guard.py`：
  - 新增 `STOCK_ETF_STATIC_GUI_ONE_SHOT_GET_FANOUT = 16`。
  - 新增 `STOCK_ETF_STATIC_GUI_TIMEOUT_MS = 5000`。
  - 新增 `test_stock_etf_static_gui_one_shot_get_fanout_stays_bounded`。
  - Guard 要求 `tab-stock-etf.js` 只有一個 `Promise.all(`、一個
    `waitForServerUp(loadReadiness)`，且正好 16 個 `ocApi(`。
  - 每個 `ocApi` 必須是 `method: 'GET'`、`timeoutMs: 5000`、
    `toastOnError: false`。
- 本 checkpoint 不改 production behavior、不改 endpoint、不改 IPC method、不改 Bybit
  path、不啟動任何 IBKR 或 connector runtime。

驗證：

- `python3 -B -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py`：
  PASS。
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py`：
  `21 passed`。
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf*.py`：
  `120 passed`。
- `python3 -B -m pytest -q tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_pm_checkpoint_numbers_are_linear tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_plan_and_operator_cover_pm_memory_trace_titles`：
  `2 passed`。
- `git diff --check`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不啟動 Phase 1/2/3/4/5
runtime、不送 paper order、不做 cancel/replace、不匯入 fill、不做 DB apply、不啟動
evidence writer、不啟動 evidence clock、不啟動 scorecard writer、不做 Linux runtime
sync/restart、不授權 tiny-live/live 或任何 Bybit behavior change。

## 81. 2026-07-01 PM session source checkpoint：Collector Run Contract

本 checkpoint 將 `stock_etf_collector_run_v1` 具體化為 Phase 3 source-only
collector run manifest contract。它不是 collector runtime，不啟動 market-data ingestion，
不新增 endpoint，不新增 IPC method，也不增加 GUI fanout；只讓既有 Phase0 manifest、
Phase3 evidence status、FastAPI normalizer 與 GUI evidence panel 能看見 fail-closed
collector-run lineage 狀態。

已完成：

- `openclaw_types` 新增 `StockEtfCollectorRunV1` 與
  `STOCK_ETF_COLLECTOR_RUN_CONTRACT_ID` / `STOCK_ETF_COLLECTOR_MIN_GREEN_TRADING_DAYS`。
- Validator 要求 exact contract id/source version、`stock_etf_cash` + IBKR + paper/shadow
  identity、collector run id/trading day、至少 5 個 green trading sessions，以及 PIT
  universe、market-data provenance、reference-data sources、storage-capacity、gap report、
  DQ manifest、replay manifest、source artifact 的 lineage hashes。
- Validator 明確拒絕 IBKR contact、connector runtime、market-data ingestion、
  evidence writer、scorecard writer、DB apply、secret serialization、tiny-live/live authority。
- Phase0 manifest / repository manifest / Phase0 FastAPI fixtures contract count 從 33
  更新為 34，Phase0 named contract packet spec 新增 `stock_etf_collector_run_v1`。
- `settings/broker/stock_etf_phase3_evidence_contracts.toml` 新增 `[collector_run]`
  default-blocked template；settings README 同步。
- 既有 `stock_etf.get_evidence_status` source fixture 暴露 default-blocked
  `collector_run` block；FastAPI evidence normalizer fail-closes missing/mismatched
  collector-run payload，並將 collector side-effect truthy claims 轉為
  `contract_violation_blocked`。
- GUI `tab-stock-etf-evidence-paper.js` 只 display collector-run accepted/id/session
  counts/lineage flags/side-effect flags；既有 `tab-stock-etf-fallbacks.js` 提供
  secret-free fail-closed fallback。

驗證：

- Python changed files `py_compile`：PASS。
- `node --check` for `tab-stock-etf-evidence-paper.js` and
  `tab-stock-etf-fallbacks.js`：PASS。
- Scoped Rust `rustfmt --edition 2021 --check`：PASS。
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf*.py`：
  `120 passed`。
- `cargo test -p openclaw_types`：`287` tests passed
  (`35` unit/golden + `252` integration/acceptance + `0` doc-tests)。
- `cargo test -p openclaw_engine stock_etf -- --nocapture`：target Stock/ETF tests
  `31 passed`；僅既有 unrelated warnings（`ScriptedSpawn` visibility 與
  `m3_emitter_replay_forbidden` unused import）。
- `python3 -B -m pytest -q tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_pm_checkpoint_numbers_are_linear tests/structure/test_docs_readme_index_static.py::test_ibkr_stock_etf_plan_and_operator_cover_pm_memory_trace_titles`：
  `2 passed`。
- `git diff --check`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不啟動 collector、不啟動
market-data ingestion、不啟動 Phase 1/2/3/4/5 runtime、不送 paper order、不做
cancel/replace、不匯入 fill、不做 DB apply、不啟動 evidence writer、不啟動 evidence
clock、不啟動 scorecard writer、不做 Linux runtime sync/restart、不授權 tiny-live/live
或任何 Bybit behavior change。

## 82. 2026-07-01 PM session source checkpoint：DQ Manifest Contract

本 checkpoint 將 `stock_etf_dq_manifest_v1` 具體化為 Phase 3 source-only
daily data-quality manifest contract。它不是 DQ writer，不啟動 market-data ingestion，
不啟動 evidence clock，不新增 endpoint，不新增 IPC method，也不增加 GUI fanout；
只讓既有 Phase0 manifest、Phase3 evidence status、FastAPI normalizer 與 GUI
evidence panel 能看見 fail-closed DQ manifest lineage 狀態。

已完成：

- `openclaw_types` 新增 `STOCK_ETF_DQ_MANIFEST_CONTRACT_ID`，並擴展
  `StockEtfDailyDqManifestV1`：
  - exact contract id / source version。
  - `stock_etf_cash` + IBKR + paper/read-only/shadow identity。
  - collector run id、market-data provenance contract id/hash、source artifact hash。
  - Bybit-live unchanged proof。
  - IBKR contact、connector runtime、market-data ingestion、DQ writer、
    evidence-clock start、scorecard writer、DB apply、secret serialization、
    tiny-live/live authority全部 fail-closed。
- Phase0 manifest / repository manifest / Phase0 FastAPI fixtures contract count 從 34
  更新為 35，Phase0 named contract packet spec 新增 `stock_etf_dq_manifest_v1`。
- `settings/broker/stock_etf_phase3_evidence_contracts.toml` 的 `[dq_manifest]`
  default-blocked template 補齊 named contract、lineage 與 side-effect denial fields；
  settings README 同步。
- Existing `stock_etf.get_evidence_status` source fixture 暴露 default-blocked
  `dq_manifest` contract block；FastAPI evidence normalizer fail-closes missing/mismatched
  DQ payload，並將 DQ side-effect truthy claims 轉為 `contract_violation_blocked`。
- GUI `tab-stock-etf-evidence-paper.js` 只 display DQ contract id、lineage hash
  presence 與 side-effect flags；既有 `tab-stock-etf-fallbacks.js` 提供 secret-free
  fail-closed fallback。

驗證：

- Python changed files `py_compile`：PASS。
- `node --check` for `tab-stock-etf-evidence-paper.js` and
  `tab-stock-etf-fallbacks.js`：PASS。
- Scoped Rust `rustfmt --edition 2021 --check`：PASS；`lib.rs` 使用
  `skip_children=true` 檢查以避開既有 unrelated `risk.rs` formatting drift。
- `cargo test -p openclaw_types --test stock_etf_phase3_evidence_acceptance -- --nocapture`：
  `19 passed`。
- `cargo test -p openclaw_types --test stock_etf_phase0_manifest_acceptance -- --nocapture`：
  `6 passed`。
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_phase0_status_routes.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_evidence_status_routes.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_routes.py`：
  `22 passed`。
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf*.py`：
  `120 passed`。
- `cargo test -p openclaw_types`：PASS。
- `cargo test -p openclaw_engine stock_etf -- --nocapture`：target Stock/ETF tests
  `31 passed`；僅既有 unrelated warnings（`ScriptedSpawn` visibility 與
  `m3_emitter_replay_forbidden` unused import）。
- IBKR timeline + trace-title structure guard：`2 passed`。
- `git diff --check`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不啟動 collector、不啟動
market-data ingestion、不啟動 DQ writer、不啟動 Phase 1/2/3/4/5 runtime、不送 paper
order、不做 cancel/replace、不匯入 fill、不做 DB apply、不啟動 evidence writer、不啟動
evidence clock、不啟動 scorecard writer、不做 Linux runtime sync/restart、不授權
tiny-live/live 或任何 Bybit behavior change。

## 83. 2026-07-01 PM session source checkpoint：Evidence Clock Lineage Guard

本 checkpoint 將 `stock_etf_evidence_clock_v1` 的 source-only checker 補硬為
必須明確綁定 collector run 與 DQ manifest lineage。它不是 evidence-clock runtime、
不是 evidence writer，不新增 endpoint，不新增 IPC method，也不增加 GUI fanout；只讓
existing Phase3 evidence status、FastAPI normalizer 與 GUI evidence panel 能看見
fail-closed evidence-clock lineage 狀態。

已完成：

- `StockEtfEvidenceClockDayV1` 新增 collector-run contract id/hash 與 DQ manifest
  contract id/hash 欄位。
- Validator 要求 exact `stock_etf_collector_run_v1` /
  `stock_etf_dq_manifest_v1` lineage，並拒絕 missing/invalid hashes。
- `settings/broker/stock_etf_phase3_evidence_contracts.toml` 的
  `[evidence_clock_day]` default-blocked template 同步新增 lineage 欄位。
- Existing `stock_etf.get_evidence_status` source fixture、FastAPI normalizer /
  fail-closed fallback 與 display-only GUI evidence panel 顯示
  evidence-clock collector/DQ/source/provenance/scorecard input hash presence。
- FastAPI contract violation guard 會把錯誤 collector/DQ lineage contract id 擋成
  `contract_violation_blocked`。

驗證：

- Python changed files `py_compile`：PASS。
- Stock/ETF evidence/fallback JS `node --check`：PASS。
- Scoped Rust `rustfmt --edition 2021 --check`：PASS。
- `cargo test -p openclaw_types --test stock_etf_phase3_evidence_acceptance -- --nocapture`：
  `19 passed`。
- `cargo test -p openclaw_types --test stock_etf_phase0_manifest_acceptance -- --nocapture`：
  `6 passed`。
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_evidence_status_routes.py`：
  `4 passed`。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不啟動 collector、不啟動
market-data ingestion、不啟動 DQ writer、不啟動 Phase 1/2/3/4/5 runtime、不送 paper
order、不做 cancel/replace、不匯入 fill、不做 DB apply、不啟動 evidence writer、不啟動
evidence clock、不啟動 scorecard writer、不做 Linux runtime sync/restart、不授權
tiny-live/live 或任何 Bybit behavior change。

## 84. 2026-07-01 PM session source checkpoint：Phase3 Evidence Module Split Guard

本 checkpoint 將 Phase3 evidence contract 的 market-data provenance 與 frozen-input
contract 從單一大檔拆到子模組。這是純 Rust source organization / maintainability
guard，不新增 contract、不改 public re-export、不改 validator 語義、不新增 endpoint
或 IPC method，也不改 FastAPI/GUI payload。

已完成：

- 新增 `rust/openclaw_types/src/stock_etf_phase3_evidence/market_data.rs`。
- `StockEtfAdjustmentMarker`、`StockMarketDataProvenanceV1`、
  `StockEtfFrozenEvidenceInputsV1` 移入子模組，原
  `stock_etf_phase3_evidence` module 保留 public re-export。
- `stock_etf_phase3_evidence.rs` 從 982 行降到 742 行，低於 800 行
  review-attention threshold；新增子模組為 254 行。
- Phase3 acceptance tests 未改語義，繼續覆蓋 market-data provenance、frozen inputs、
  collector run、DQ manifest 與 evidence clock。

驗證：

- Scoped Rust `rustfmt --edition 2021 --check`：PASS。
- `cargo test -p openclaw_types --test stock_etf_phase3_evidence_acceptance -- --nocapture`：
  `19 passed`。
- `cargo test -p openclaw_types --test stock_etf_phase0_manifest_acceptance -- --nocapture`：
  `6 passed`。
- Full Stock/ETF FastAPI/static pytest：`120 passed`。
- Full `cargo test -p openclaw_types`：PASS。
- `cargo test -p openclaw_engine stock_etf -- --nocapture`：PASS。
- Focused docs trace：`2 passed`。
- `git diff --check`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不啟動 collector、不啟動
market-data ingestion、不啟動 DQ writer、不啟動 Phase 1/2/3/4/5 runtime、不送 paper
order、不做 cancel/replace、不匯入 fill、不做 DB apply、不啟動 evidence writer、不啟動
evidence clock、不啟動 scorecard writer、不做 Linux runtime sync/restart、不授權
tiny-live/live 或任何 Bybit behavior change。

## 85. 2026-07-01 PM session source checkpoint：Connector Attestation Preview Guard

本 checkpoint 補上 inert IBKR connector skeleton 的 session attestation 與 paper
attestation preview surface。這不是 IBKR session attestation runtime，也不是 paper
account/channel attestation；只提供 future Phase 2 gate 可接的 typed、secret-free、
blocked preview payload，避免後續臨時拼 dict 或把 attestation shape 混入 Bybit path。

已完成：

- `models.py` 新增 `IbkrSessionAttestationPreview`、
  `IbkrPaperAttestationPreview` 與對應 blocked helper；payload 固定
  `phase2_gate_not_accepted`、source-only blocked blockers，並明確標示 no network /
  no secret / no Bybit path。
- `IbkrReadOnlyClient` 新增 `session_attestation_preview()`；`IbkrPaperClientBoundary`
  新增 `paper_attestation_preview()`。
- Static fixture package 新增 blocked session/paper attestation fixtures。
- Connector skeleton public surface freeze tests 更新，鎖住新增 exports、method set、
  payload keys、contract ids、side-effect false flags 與 blocker 去重。
- README 同步說明 display-only session/paper attestation previews。

驗證：

- Python changed files `py_compile`：PASS。
- `python3 -B -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_ibkr_connector_skeleton.py`：
  `8 passed`。
- Full Stock/ETF FastAPI/static pytest：`120 passed`。
- Focused docs trace：`2 passed`。
- `git diff --check`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不啟動 collector、不啟動
market-data ingestion、不啟動 DQ writer、不啟動 Phase 1/2/3/4/5 runtime、不送 paper
order、不做 cancel/replace、不匯入 fill、不做 DB apply、不啟動 evidence writer、不啟動
evidence clock、不啟動 scorecard writer、不做 Linux runtime sync/restart、不授權
tiny-live/live 或任何 Bybit behavior change。

## 86. 2026-07-01 PM session source checkpoint：Session Attestation Data-Tier Lineage Guard

本 checkpoint 將 `ibkr_session_attestation_v1` 補硬為可追溯 data tier /
entitlements / gateway startup lineage 的 source-only contract。這不是 IBKR
session runtime、不是 read probe、不是 paper order approval，也不啟動 market-data
ingestion；只讓 Phase2 session attestation 在進入任何 broker contact 前具備足夠的
機器可驗證欄位。

已完成：

- `IbkrSessionDataTier` 新增 `account_only`、`delayed`、
  `realtime_entitled`、`unknown` 枚舉。
- `IbkrSessionAttestationV1` 新增 `data_tier`、
  `entitlements_fingerprint`、`market_data_entitlement_purchase_denied` 與
  `gateway_started_at_ms`。
- Session validator 從「非空」補硬到 SHA-256 形狀檢查：account fingerprint、
  secret-slot fingerprint、entitlements fingerprint 與 raw artifact hash 都必須是
  64 hex。
- Validator 新增 missing/invalid data-tier lineage、market-data entitlement
  purchase not denied、gateway startup after attestation blockers。
- Inert Python connector session preview、FastAPI account/authorization
  normalizers 與 route fixtures 同步加入新欄位，全部維持 fail-closed：
  `unknown` / `False` / `0`。
- Account/authorization contract violation guard 會拒絕 client/IPC 提前宣稱
  data tier、entitlements fingerprint、market-data entitlement purchase denial 或
  gateway startup timestamp。
- Phase0 named-contract packet 的 `ibkr_session_attestation_v1` required fields /
  blockers 同步補齊。

驗證：

- Python changed files `py_compile`：PASS。
- Connector/account/authorization focused pytest：`18 passed`。
- Scoped Rust `rustfmt --edition 2021 --check`：PASS。
- `cargo test -p openclaw_types --test ibkr_phase2_gate_acceptance -- --nocapture`：
  `11 passed`。
- `cargo test -p openclaw_types --test ibkr_feature_flag_secret_auth_acceptance -- --nocapture`：
  `8 passed`。
- Full Stock/ETF FastAPI/static pytest：`120 passed`。
- Full `cargo test -p openclaw_types`：`291 passed`。
- Focused docs trace：`2 passed`。
- `git diff --check`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不啟動 collector、不啟動
market-data ingestion、不啟動 DQ writer、不啟動 Phase 1/2/3/4/5 runtime、不送 paper
order、不做 cancel/replace、不匯入 fill、不做 DB apply、不啟動 evidence writer、不啟動
evidence clock、不啟動 scorecard writer、不做 Linux runtime sync/restart、不授權
tiny-live/live 或任何 Bybit behavior change。

## 87. 2026-07-01 PM session source checkpoint：Read-Only Probe Result Import Request Contract

本 checkpoint 補上 `stock_etf_ibkr_readonly_probe_result_import_request_v1`
source-only contract，銜接既有 pre-contact
`stock_etf_ibkr_readonly_probe_request_v1` 與下游 account cash ledger /
market-data provenance / instrument identity / lifecycle read evidence lineage。這不是
read probe runtime、不是 result import runtime、不是 evidence writer，也不批准 IBKR
contact；只固定未來 sanitized read-only result 進入 evidence 前必須具備的 typed
envelope。

已完成：

- 新增 Rust module
  `stock_etf_ibkr_readonly_probe_result_import_request`，定義 exact contract id、
  source version、Stock/ETF IBKR readonly/paper identity、read action/operation
  mapping、request/session/allowlist/redaction/audit lineage、result payload/raw/
  redacted/source hashes、as-of/import-request timestamp、idempotency key。
- Validator 依 probe kind 要求 exactly one downstream evidence lineage：
  health snapshot、`broker_account_portfolio_cash_ledger_v1`、
  `stock_market_data_provenance_v1`、`instrument_identity_contract_v1` 或
  `broker_lifecycle_event_log_v1`。
- Validator fail-closed 拒絕 duplicate import、stale result without manual review、
  IBKR contact、connector runtime、secret serialization、result import、evidence
  writer、scorecard writer、DB apply、order/paper-order、Bybit path reuse、
  entitlement purchase、Client Portal Web API、Python direct broker write 與
  tiny-live/live。
- Phase0 manifest / manifest JSON 從 35 named contracts 更新為 36，新增
  `stock_etf_ibkr_readonly_probe_result_import_request_v1` named contract。
- Broker capability registry 的 `scorecard_derive` gate 新增 readonly probe result
  import request lineage，避免 future scorecard 只看 cash ledger/provenance hash 而缺
  read-only result import envelope trace。
- 新增 default-blocked secret-free template
  `settings/broker/stock_etf_ibkr_readonly_probe_result_import_request.template.toml`，
  並同步 settings README、broker capability template 與 Phase0 named-contract spec。

驗證：

- Scoped Rust `rustfmt --edition 2021 --check`：PASS。
- `cargo test -p openclaw_types --test stock_etf_ibkr_readonly_probe_result_import_request_acceptance -- --nocapture`：
  `6 passed`。
- `cargo test -p openclaw_types --test stock_etf_phase0_manifest_acceptance -- --nocapture`：
  `6 passed`。
- `cargo test -p openclaw_types --test stock_etf_broker_capability_registry_acceptance -- --nocapture`：
  `10 passed`。
- Full `cargo test -p openclaw_types`：PASS。
- Full Stock/ETF FastAPI/static pytest：`120 passed`。
- Focused docs trace：`2 passed`。
- `git diff --check`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不匯入 result、不啟動
collector、不啟動 market-data ingestion、不啟動 DQ writer、不啟動 Phase 1/2/3/4/5
runtime、不送 paper order、不做 cancel/replace、不匯入 fill、不做 DB apply、不啟動
evidence writer、不啟動 evidence clock、不啟動 scorecard writer、不做 Linux runtime
sync/restart、不授權 tiny-live/live 或任何 Bybit behavior change。

## 88. 2026-07-01 PM session source/display checkpoint：Phase0 Result-Import Display Lineage Guard

本 checkpoint 將上一個
`stock_etf_ibkr_readonly_probe_result_import_request_v1` source-only contract 從
Rust type/manifest layer 同步到 control-plane 與 display surface。這不是 read probe
runtime、不是 result import runtime、不是 scorecard writer，也不批准 IBKR contact；
只防止 FastAPI/GUI/IPC 顯示層仍停在 35 contracts 或漏顯 scorecard lineage gate。

已完成：

- FastAPI Phase0 normalizer / route fixture / tests 從 35 contracts 同步為 36，
  並 fail-closed 檢查 readonly probe request 與 readonly probe result-import
  request 兩個 required contract presence。
- Rust IPC Phase0 status test 同步 `contract_count=36`，並覆蓋
  `stock_etf_ibkr_readonly_probe_result_import_request_v1` 出現在 manifest list。
- Rust IPC policy status summary 新增
  `readonly_probe_result_import_request_contract_id` 與
  `scorecard_requires_readonly_probe_result_import_request`，對應 broker capability
  registry 的 `scorecard_derive` gate。
- FastAPI policy normalizer / fixture / tests fail-closed 地傳遞並檢查上述兩個欄位；
  accepted registry 若缺 result-import contract id 或 scorecard gate 會進入
  `contract_violation_blocked`。
- Stock/ETF GUI Phase0 panel 顯示 readonly probe request / result-import request
  presence；Policy panel 顯示 result-import contract id 與 scorecard gate boolean。

驗證：

- Python changed files `py_compile`：PASS。
- Stock/ETF JS `node --check`：PASS。
- Scoped Rust `rustfmt --edition 2021 --check`：PASS。
- Focused FastAPI Phase0/Policy/Route pytest：`23 passed`。
- Full Stock/ETF FastAPI/static pytest：`120 passed`。
- Focused engine Phase0 IPC test：PASS。
- Focused engine Policy IPC test：PASS。
- Engine Stock/ETF IPC regression：`31 passed`。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不匯入 result、不啟動
collector、不啟動 market-data ingestion、不啟動 DQ writer、不啟動 Phase 1/2/3/4/5
runtime、不送 paper order、不做 cancel/replace、不匯入 fill、不做 DB apply、不啟動
evidence writer、不啟動 evidence clock、不啟動 scorecard writer、不做 Linux runtime
sync/restart、不授權 tiny-live/live 或任何 Bybit behavior change。

## 89. 2026-07-01 PM session source/display checkpoint：Readiness Result-Import Request Guard

本 checkpoint 將
`stock_etf_ibkr_readonly_probe_result_import_request_v1` 接入
`stock_etf.get_readiness` / FastAPI readiness / GUI readiness display 的
fail-closed 路徑。這不是 read probe runtime、不是 result import runtime、不是
connector runtime，也不批准 IBKR contact；只讓 readiness 面板在 Phase2 尚未通過時
明確顯示 result-import request artifact 缺失與所有 side-effect flags 為 false。

已完成：

- Rust IPC `phase2_precontact_summary()` 新增
  `readonly_probe_result_import_request`，預設
  `blocked_no_result_import_request_artifact`，並固定
  `accepted_for_import=false`、`result_import_performed=false`、
  `evidence_writer_started=false`、`scorecard_writer_started=false`、
  `db_apply_performed=false`。
- FastAPI readiness normalizer 新增 result-import request fail-closed fallback，
  並在 contract id、source version、status 或任何副作用旗標被上游聲稱 ready/true
  時進入 `contract_violation_blocked`。
- Stock/ETF GUI readiness renderer 與 browser fallback 同步顯示 result-import
  request contract/status/blockers/side-effect flags，不新增 endpoint、IPC method、
  GUI fanout 或 client input。
- Route/static tests 鎖住 result-import readiness 欄位與 GUI 字串；Rust IPC test
  鎖住 Phase2 pre-contact source fixture 的 result-import default-blocked payload。

驗證：

- Python changed files `py_compile`：PASS。
- Stock/ETF JS `node --check`：PASS。
- Scoped Rust `rustfmt --edition 2021 --check`：PASS。
- Focused FastAPI readiness/static route pytest：`20 passed`。
- Focused engine readiness IPC test：PASS。
- Full Stock/ETF FastAPI/static pytest：`120 passed`。
- Engine Stock/ETF IPC regression：`31 passed`。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不匯入 result、不啟動
collector、不啟動 market-data ingestion、不啟動 DQ writer、不啟動 Phase 1/2/3/4/5
runtime、不送 paper order、不做 cancel/replace、不匯入 fill、不做 DB apply、不啟動
evidence writer、不啟動 evidence clock、不啟動 scorecard writer、不做 Linux runtime
sync/restart、不授權 tiny-live/live 或任何 Bybit behavior change。

## 90. 2026-07-01 PM session source checkpoint：Connector Result-Import Preview Guard

本 checkpoint 將 readonly probe result-import request 的 blocked preview 補進
inert Python IBKR connector skeleton。這不是 result import runtime、不是 connector
runtime、不是 FastAPI production wiring，也不批准 IBKR contact；只讓 connector
skeleton 的 future-facing source-only preview surface 與 readiness/result-import
contract 對齊。

已完成：

- 新增 `IBKR_READONLY_PROBE_RESULT_IMPORT_REQUEST_CONTRACT_ID` 與
  `IbkrReadOnlyProbeResultImportPreview`，固定 contract id/source version、blocked
  no-artifact status、`accepted_for_import=false`、`result_import_performed=false`、
  writer/DB/order/live/Bybit reuse flags false。
- `IbkrReadOnlyClient.readonly_probe_result_import_request_preview()` 回傳 secret-free
  blocked dict；新增 matching static fixture。
- Connector skeleton `__all__`、public client surface freeze、payload shape guard、
  no-Bybit-import guard 與 display-only side-effect guard 已同步。
- Connector README 明確列入 display-only readonly probe result-import request
  preview；沒有新增 FastAPI endpoint、IPC method、GUI fanout 或 production
  control-api import。

驗證：

- Python changed files `py_compile`：PASS。
- Connector skeleton focused pytest：`8 passed`。
- Python no-write static guard：`21 passed`。
- Full Stock/ETF FastAPI/static pytest：`120 passed`。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不匯入 result、不啟動
collector、不啟動 market-data ingestion、不啟動 DQ writer、不送 paper order、不做
cancel/replace、不匯入 fill、不做 DB apply、不啟動 evidence writer、不啟動 evidence
clock、不啟動 scorecard writer、不做 Linux runtime sync/restart、不授權 tiny-live/live
或任何 Bybit behavior change。

## 91. 2026-07-01 PM session source/display checkpoint：Scorecard Input Result-Import Lineage Guard

本 checkpoint 將 `stock_etf_ibkr_readonly_probe_result_import_request_v1`
lineage 接入 scorecard input bundle contract 與 scorecard status display surface。這
不是 result import runtime、不是 scorecard writer、不是 evidence clock，也不批准
IBKR contact；只讓未來 scorecard 派生輸入必須顯式攜帶 readonly probe
result-import request contract id/hash lineage。

已完成：

- Rust `StockEtfScorecardInputBundleV1` 新增
  `readonly_probe_result_import_request_contract_id` 與
  `readonly_probe_result_import_request_hash`，validator 要求 exact result-import
  request contract id 與 64-hex hash。
- Blocked TOML template 保持 source-only blocked posture；accepted fixture 才帶完整
  result-import request lineage。
- Rust IPC `stock_etf.get_scorecard_status` 新增 default-blocked
  `scorecard_input_bundle` 摘要，僅暴露 hash-present boolean，不暴露 hash 內容。
- FastAPI scorecard normalizer 新增 input-bundle fail-closed fallback 與 contract
  violation guard；GUI scorecard panel 顯示 input-bundle lineage/side-effect flags。
- Route/static/Rust IPC tests 鎖住 result-import lineage guard，不新增 endpoint、IPC
  method、GUI fanout、client input、connector runtime 或 production result import。

驗證：

- Python changed files `py_compile`：PASS。
- Stock/ETF JS `node --check`：PASS。
- Scoped Rust `rustfmt --edition 2021 --check`：PASS。
- Focused Rust scorecard input acceptance：PASS。
- Focused engine scorecard IPC fixture：PASS。
- Focused FastAPI scorecard/static pytest：PASS。
- Full Stock/ETF FastAPI/static pytest：PASS。
- Docs trace guard：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不匯入 result、不啟動
collector、不啟動 market-data ingestion、不啟動 DQ writer、不送 paper order、不做
cancel/replace、不匯入 fill、不做 DB apply、不啟動 evidence writer、不啟動 evidence
clock、不啟動 scorecard writer、不做 Linux runtime sync/restart、不授權 tiny-live/live
或任何 Bybit behavior change。

## 92. 2026-07-01 PM session source/display checkpoint：Scorecard Fallback Input Lineage Guard

本 checkpoint 將 `scorecard_input_bundle` 的 result-import lineage fallback 補進
browser-side `scorecardFallback()`。這不是 API fanout change、不是 endpoint change、
不是 IPC method change，也不批准任何 IBKR contact；只確保 API unavailable/degraded
時 GUI 仍保留與 FastAPI fail-closed payload 一致的 input-bundle lineage/blocker
顯示。

已完成：

- `tab-stock-etf-fallbacks.js` 的 `scorecardFallback()` 新增 default-degraded
  `scorecard_input_bundle` block。
- Fallback 固定
  `readonly_probe_result_import_request_contract_id=stock_etf_ibkr_readonly_probe_result_import_request_v1`，
  result-import request hash-present、market/reference/risk/atomic/source lineage
  flags 與所有 side-effect flags 皆為 false。
- Python static no-write/split guard 鎖住 fallback payload 必須保留
  `scorecard_input_bundle` 與 readonly probe result-import request lineage 欄位。

驗證：

- Python changed files `py_compile`：PASS。
- Stock/ETF JS `node --check`：PASS。
- Focused fallback/static/docs trace pytest：PASS。
- Full Stock/ETF FastAPI/static pytest：PASS。
- `git diff --check`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不匯入 result、不啟動
collector、不啟動 market-data ingestion、不啟動 DQ writer、不送 paper order、不做
cancel/replace、不匯入 fill、不做 DB apply、不啟動 evidence writer、不啟動 evidence
clock、不啟動 scorecard writer、不新增 GUI fanout、不授權 tiny-live/live 或任何
Bybit behavior change。

## 93. 2026-07-01 PM session source checkpoint：Scorecard Status Module Split Guard

本 checkpoint 將 Rust Stock/ETF `scorecard_status_summary` 從
`status_summaries.rs` 拆到 `status_summaries/scorecard.rs`。這不是 behavior change、
不是 endpoint change、不是 IPC method change，也不改 scorecard payload；只降低單檔
體積與維護風險，讓 source-only status fixtures 更清楚分層。

已完成：

- 新增 `rust/openclaw_engine/src/ipc_server/handlers/stock_etf/status_summaries/scorecard.rs`，
  承載原 scorecard status source fixture。
- `status_summaries.rs` 保留 thin wrapper，對外 `scorecard_status_summary` import
  surface 不變。
- 父檔由 1006 行降至 785 行，低於 800 行 review threshold；新子模組 228 行。
- 沒有新增 endpoint、IPC method、request handler、GUI fanout 或 runtime path。

驗證：

- Scoped Rust `rustfmt --edition 2021 --check`：PASS。
- Focused engine scorecard IPC fixture：PASS。
- Engine Stock/ETF IPC regression：`29 passed`。
- Docs trace guard：PASS。
- `git diff --check`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不匯入 result、不啟動
collector、不啟動 market-data ingestion、不啟動 DQ writer、不送 paper order、不做
cancel/replace、不匯入 fill、不做 DB apply、不啟動 evidence writer、不啟動 evidence
clock、不啟動 scorecard writer、不新增 GUI fanout、不授權 tiny-live/live 或任何
Bybit behavior change。

## 94. 2026-07-01 PM session source checkpoint：Python No-Write Static Guard Split Guard

本 checkpoint 將 Stock/ETF Python no-write static guard 從單一 1022 行測試檔拆成
共享 helper 與三個窄測試模組。這不是 behavior change、不是 endpoint change、
不是 IPC method change，也不放寬任何 IBKR/Bybit 邊界；只降低 guard 本身的審查
成本，避免保護 IBKR source-only posture 的測試檔繼續膨脹。

已完成：

- 新增 `stock_etf_static_guard_helpers.py`，集中常數、候選檔掃描與 AST 檢查 helper。
- `test_stock_etf_python_no_write_static_guard.py` 只保留 Python/connector surface
  no-write、network、persistence、secret/env、clock/concurrency 與 connector-import
  邊界測試。
- 新增 `test_stock_etf_route_static_guard.py`，承接 GET-only、empty params、
  readonly status IPC allowlist 與 authenticated actor route signature guard。
- 新增 `test_stock_etf_static_gui_guard.py`，承接 GUI endpoint template、display-only、
  no-background-work、one-shot fanout budget 與 renderer/fallback split guard。
- 原 1022 行 guard 降至 152 行；共享 helper 522 行；新增 route/GUI guard 分別
  147/263 行，Stock/ETF guard files 皆低於 800 行 review threshold。

驗證：

- Python changed files `py_compile`：PASS。
- Focused split guard pytest：`21 passed`。
- Full Stock/ETF FastAPI/static pytest：`120 passed`。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不匯入 result、不啟動
collector、不啟動 market-data ingestion、不啟動 DQ writer、不送 paper order、不做
cancel/replace、不匯入 fill、不做 DB apply、不啟動 evidence writer、不啟動 evidence
clock、不啟動 scorecard writer、不新增 GUI fanout、不授權 tiny-live/live 或任何
Bybit behavior change。

## 95. 2026-07-01 PM session source checkpoint：Scorecard Input Module Split Guard

本 checkpoint 將 Rust `stock_etf_scorecard_inputs.rs` 從 800 行邊界檔拆成父
re-export + `components.rs` + `bundle.rs`。這不是 contract behavior change、不是
payload change、不是 endpoint/IPC change；只降低 scorecard input source-only
contract 的單檔審查風險，保留
`openclaw_types::stock_etf_scorecard_inputs::*` public import surface。

已完成：

- 父檔保留 contract constants、public re-export、`StockEtfScorecardInputVerdict`
  與 `StockEtfScorecardInputBlocker`。
- `components.rs` 承載 cash ledger、cost model、benchmark、shadow fill model、
  storage capacity component validators。
- `bundle.rs` 承載 `StockEtfScorecardInputBundleV1` default/accepted fixture 與
  bundle-level lineage/side-effect validator。
- 原父檔由 800 行降至 128 行；新 components/bundle 模組分別為 520/181 行。

驗證：

- Scoped Rust `rustfmt --edition 2021 --check`：PASS。
- Focused scorecard input acceptance：`12 passed`。
- Focused scorecard derivation/verdict acceptance：`13 passed`。
- Full `cargo test -p openclaw_types`：PASS。
- Engine Stock/ETF IPC regression：`29 passed`。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不匯入 result、不啟動
collector、不啟動 market-data ingestion、不啟動 DQ writer、不送 paper order、不做
cancel/replace、不匯入 fill、不做 DB apply、不啟動 evidence writer、不啟動 evidence
clock、不啟動 scorecard writer、不新增 GUI fanout、不授權 tiny-live/live 或任何
Bybit behavior change。

## 96. 2026-07-01 PM session source checkpoint：Rust IPC Parent Module Split Guard

本 checkpoint 將 Stock/ETF Rust IPC handler parent 與 IPC fixture test parent
拆出 precontact / foundation child modules。這不是 behavior change、不是 endpoint
change、不是 IPC method change，也不改 payload shape；只降低 Stock/ETF source-only
IPC layer 的單檔審查風險，並把 split structure guard 的 line cap 收緊到 800。

已完成：

- `handlers/stock_etf/precontact.rs` 承載 Phase2 pre-contact、readonly probe
  request、result-import request 與 connector skeleton summaries。
- `tests/stock_etf/precontact_fixtures.rs` 承載 readiness pre-contact fixture test。
- `tests/stock_etf/foundation_status_fixtures.rs` 承載 data-foundation、policy、
  authorization status fixture tests。
- Handler parent 由 860 行降至 750 行；IPC fixture test parent 由 1209 行降至
  706 行；新增 precontact/foundation 子模組分別為 118/158/353 行。
- Rust IPC handler/test split static guards 的 file cap 從 1200 收緊到 800，並鎖住
  新子模組 allowlist 與 moved helper/test ownership。

驗證：

- Scoped Rust `rustfmt --edition 2021 --check`：PASS。
- Focused Rust IPC split structure guards：`14 passed`。
- Engine Stock/ETF IPC regression：`29 passed`。
- Docs trace guard：PASS。
- `git diff --check`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不匯入 result、不啟動
collector、不啟動 market-data ingestion、不啟動 DQ writer、不送 paper order、不做
cancel/replace、不匯入 fill、不做 DB apply、不啟動 evidence writer、不啟動 evidence
clock、不啟動 scorecard writer、不新增 GUI fanout、不授權 tiny-live/live 或任何
Bybit behavior change。

## 97. 2026-07-01 PM session source checkpoint：Paper Order Request Module Split Guard

本 checkpoint 將 Rust `stock_etf_paper_order_request.rs` 從 798 行邊界檔拆成父
type/default 檔 + `fixtures.rs` + `validation.rs`。這不是 contract behavior
change、不是 endpoint/IPC change、不是 payload shape change；只降低 future
paper-order source-only contract 的單檔審查風險，保留
`openclaw_types::StockEtfPaperOrderRequestEnvelopeV1` public method surface。

已完成：

- 父檔保留 public enums、envelope、default、verdict/blocker 與 contract id。
- `fixtures.rs` 承載 accepted preview/submit/cancel/replace fixtures。
- `validation.rs` 承載 `validate()` 與 order intent、effect hash、limit price、
  boundary flag helper。
- 原父檔由 798 行降至 216 行；fixtures/validation 子模組分別為 114/498 行。
- 新增 paper-order request split static guard，鎖住子模組 allowlist、moved ownership
  與 no-runtime-token posture。

驗證：

- Scoped Rust `rustfmt --edition 2021 --check`：PASS。
- Focused paper-order request split static guard：`3 passed`。
- Focused paper-order request acceptance：`8 passed`。
- Full `cargo test -p openclaw_types`：PASS。
- Engine Stock/ETF IPC regression：`29 passed`。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不匯入 result、不啟動
collector、不啟動 market-data ingestion、不啟動 DQ writer、不送 paper order、不做
cancel/replace、不匯入 fill、不做 DB apply、不啟動 evidence writer、不啟動 evidence
clock、不啟動 scorecard writer、不新增 GUI fanout、不授權 tiny-live/live 或任何
Bybit behavior change。

## 98. 2026-07-01 PM session source checkpoint：Connector Risky Config Blocker Guard

本 checkpoint 為 inert IBKR connector skeleton 補上 risky endpoint config regression。
這不是 connector wiring、不是 FastAPI route wiring、不是 Rust IPC behavior change；
只鎖住一個 source-only 安全不變量：即使未來有人用 non-loopback host、live TWS
port、secret/account fingerprint、paper/live channel flags 或 Bybit reuse flag 建立
client，所有 preview payload 也只能擴充 blockers，不能暗示任何 network/secret/
paper/live/import/order/DB side effect。

已完成：

- `test_stock_etf_ibkr_connector_skeleton.py` 新增 `RISKY_CONFIG_BLOCKERS`。
- 新增 `test_ibkr_connector_risky_config_only_expands_blockers`，覆蓋
  `connection_plan`、readiness、account/market-data/contract-detail preview、
  session attestation、readonly probe result-import、paper lifecycle、fill import、
  paper attestation。
- Regression 要求 risky config blockers 全部出現在 payload blockers 中，
  blockers 去重，且既有 side-effect false keys 全部仍為 `false`。
- 沒有改 production code、route、Rust IPC、GUI、connector README 或 Bybit module。

驗證：

- Connector skeleton py_compile：PASS。
- Connector skeleton focused pytest：`9 passed`。
- Python no-write/static/GUI guard focused pytest：`30 passed`。
- Stock/ETF Python route/static suite：`121 passed`。
- 廣義 `-k stock_etf` collection 嘗試因無關 L2 測試在 Python 3.10 缺少
  `tomllib` 中止；已改用 `test_stock_etf_*.py` 檔案集合完成本 checkpoint 相關
  E4 覆蓋。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不匯入 result、不啟動
collector、不啟動 market-data ingestion、不啟動 DQ writer、不送 paper order、不做
cancel/replace、不匯入 fill、不做 DB apply、不啟動 evidence writer、不啟動 evidence
clock、不啟動 scorecard writer、不新增 GUI fanout、不授權 tiny-live/live 或任何
Bybit behavior change。

## 99. 2026-07-01 PM session source checkpoint：Phase2 Policy Source Static Guard

本 checkpoint 為 `ibkr_phase2_policies.rs` 補上 source-only structure guard。這不是
Phase 2 runtime start、不是 external-surface gate PASS、不是 IBKR contact；只把
redaction、rate-limit、audit-event、paper-attestation、Python no-write guard 這組
Phase 2 prerequisite policy contract 的 source hygiene 機器化。

已完成：

- 新增 `tests/structure/test_ibkr_phase2_policies_source_static.py`。
- Guard 鎖住 `ibkr_phase2_policies.rs` 低於 800 行 governance cap。
- Guard 要求 5 個 named contract id 與 5 個 policy `impl` 保持在 source 中，並
  承認 bundle 自身也有 `source_template()`。
- Guard 禁止 runtime material/network/clock/thread/process/order/Bybit runtime tokens，
  防止 Phase 2 policy contract 檔長出 secret IO、socket、clock、spawn、order 或
  Bybit runtime dependency。

驗證：

- New structure guard py_compile：PASS。
- Focused structure guard pytest：`3 passed`。
- Focused Phase2 policy acceptance：`9 passed`。
- Full `cargo test -p openclaw_types`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不匯入 result、不啟動
collector、不啟動 market-data ingestion、不啟動 DQ writer、不送 paper order、不做
cancel/replace、不匯入 fill、不做 DB apply、不啟動 evidence writer、不啟動 evidence
clock、不啟動 scorecard writer、不新增 GUI fanout、不授權 tiny-live/live 或任何
Bybit behavior change。

## 100. 2026-07-01 PM session source checkpoint：Lane-Scoped IPC Source Static Guard

本 checkpoint 為 `stock_etf_lane_scoped_ipc.rs` 補上 source-only structure guard。
這不是 IPC runtime 啟動、不是 IBKR contact、不是 connector wiring，也不是 Bybit
runtime reuse；只把 Stock/ETF lane-scoped IPC contract 的 method matrix、contract
tokens 與 no-runtime posture 機器化，避免未來改動在 source 層面引入 paper/order/
network/secret/Bybit runtime drift。

已完成：

- 新增 `tests/structure/test_stock_etf_lane_scoped_ipc_source_static.py`。
- Guard 鎖住 `stock_etf_lane_scoped_ipc.rs` 低於 800 行 governance cap。
- Guard 要求 20 個 lane-scoped IPC method variants 保持對齊 engine Method mapping，
  並保留 `BybitSubmitPaperOrderDenied` / `UnknownDenied` denied sentinels。
- Guard 要求 lane IPC、scoped authorization、external surface gate、session
  attestation、non-Bybit allowlist、secret slot/topology、broker registry、asset-lane
  events 等 contract tokens 保持在 source 中。
- Guard 禁止 env/fs/network/IBKR SDK/clock/thread/process/order/Bybit runtime tokens。

驗證：

- New structure guard py_compile：PASS。
- Focused structure guard pytest：`3 passed`。
- Focused lane-scoped IPC acceptance：`9 passed`。
- Full `cargo test -p openclaw_types`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不匯入 result、不啟動
collector、不啟動 market-data ingestion、不啟動 DQ writer、不送 paper order、不做
cancel/replace、不匯入 fill、不做 DB apply、不啟動 evidence writer、不啟動 evidence
clock、不啟動 scorecard writer、不新增 GUI fanout、不授權 tiny-live/live 或任何
Bybit behavior change。

## 101. 2026-07-01 PM session source checkpoint：Stock/ETF Lane Source Static Guard

本 checkpoint 為 `stock_etf_lane.rs` 補上 source-only structure guard。這不是
feature flag enablement、不是 Phase 2 runtime start、不是 IBKR contact、不是
paper-order authority；只把 Stock/ETF lane taxonomy、feature flag allowlist、
readiness/gate matrix、broker operation denial surface 與 no-runtime posture
機器化。

已完成：

- 新增 `tests/structure/test_stock_etf_lane_source_static.py`。
- Guard 鎖住 `stock_etf_lane.rs` 低於 800 行 governance cap。
- Guard 要求 lane/broker/environment/instrument/authority/operation/denial/gate/
  lifecycle type surface 保持在 source 中。
- Guard 要求 15 個 broker operation variants、20 個 denial variants、13 個 gate
  fields 保持完整，並保留 live/margin/options/CFD/account-write typed denials。
- Guard 將 feature flag env keys 限定為 5 個非 secret allowlist keys，且只允許
  `StockEtfFeatureFlags::from_env()` 的單一 `std::env::var(key).ok()` path。
- Guard 禁止 fs/network/IBKR SDK/clock/thread/process/order/Bybit runtime tokens 與
  secret/account material tokens。

驗證：

- New structure guard py_compile：PASS。
- Focused structure guard pytest：`4 passed`。
- Focused Stock/ETF lane acceptance：`9 passed`。
- Full `cargo test -p openclaw_types`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不匯入 result、不啟動
collector、不啟動 market-data ingestion、不啟動 DQ writer、不送 paper order、不做
cancel/replace、不匯入 fill、不做 DB apply、不啟動 evidence writer、不啟動 evidence
clock、不啟動 scorecard writer、不新增 GUI fanout、不授權 tiny-live/live 或任何
Bybit behavior change。

## 102. 2026-07-01 PM session source checkpoint：IBKR Phase2 Gate Source Static Guard

本 checkpoint 為 `ibkr_phase2_gate.rs` 補上 source-only structure guard。這不是
external-surface gate PASS、不是 session attestation runtime、不是第一次 IBKR
contact；只把 Phase 2 pre-contact gate 與 session attestation contract 的 source
hygiene 機器化，避免未來改動引入 env/secret material reads、socket、clock、
process、order 或 Bybit runtime coupling。

已完成：

- 新增 `tests/structure/test_ibkr_phase2_gate_source_static.py`。
- Guard 鎖住 `ibkr_phase2_gate.rs` 低於 800 行 governance cap。
- Guard 要求 ADR/AMD、external-surface gate、session attestation、paper/live port
  constants 保持精確。
- Guard 要求 external-surface gate type surface、13 個 gate fields、18 個 gate
  blockers、`ibkr_contact_allowed: blockers.is_empty()` 與 retroactive
  `ibkr_call_performed` blocker 保持在 source 中。
- Guard 要求 session attestation type surface、20 個 attestation fields、28 個
  attestation blockers、loopback/paper-port/live-port/env-fallback/staleness checks
  保持在 source 中。
- Guard 禁止 env/fs/network/IBKR SDK/clock/thread/process/order/Bybit runtime tokens
  與 secret material access tokens。

驗證：

- New structure guard py_compile：PASS。
- Focused structure guard pytest：`4 passed`。
- Focused Phase2 gate acceptance：`11 passed`。
- Full `cargo test -p openclaw_types`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不匯入 result、不啟動
collector、不啟動 market-data ingestion、不啟動 DQ writer、不送 paper order、不做
cancel/replace、不匯入 fill、不做 DB apply、不啟動 evidence writer、不啟動 evidence
clock、不啟動 scorecard writer、不新增 GUI fanout、不授權 tiny-live/live 或任何
Bybit behavior change。

## 103. 2026-07-01 PM session source checkpoint：IBKR Phase2 Runtime Source Static Guard

本 checkpoint 為 `ibkr_phase2_runtime.rs` 補上 source-only structure guard。這不是
secret-slot reader、不是 gateway/TWS process start、不是 API topology probe、不是
IBKR contact；只把 Phase 2 secret-slot contract 與 API session topology contract 的
source hygiene 機器化。

已完成：

- 新增 `tests/structure/test_ibkr_phase2_runtime_source_static.py`。
- Guard 鎖住 `ibkr_phase2_runtime.rs` 低於 800 行 governance cap。
- Guard 要求 secret-slot / API-session-topology contract IDs、paper/live port
  imports、secret-slot posture enum、gateway process mode、verdict/blocker types 保持
  在 source 中。
- Guard 要求 secret-slot source template 維持 hashed paper slot、absent live slot、
  owner-only permission、env fallback denied、secret/account serialization false。
- Guard 要求 API session topology 維持 `ib_gateway_tws_api`、`trade-core`、
  loopback `127.0.0.1`、paper gateway port、PaperGateway mode、Paper environment、
  live-port denial 與 loopback check。
- Guard 禁止 env/fs/network/IBKR SDK/clock/thread/process/order/Bybit runtime tokens
  與 secret material access tokens。

驗證：

- New structure guard py_compile：PASS。
- Focused structure guard pytest：`4 passed`。
- Focused Phase2 runtime acceptance：`7 passed`。
- Full `cargo test -p openclaw_types`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不匯入 result、不啟動
collector、不啟動 market-data ingestion、不啟動 DQ writer、不送 paper order、不做
cancel/replace、不匯入 fill、不做 DB apply、不啟動 evidence writer、不啟動 evidence
clock、不啟動 scorecard writer、不新增 GUI fanout、不授權 tiny-live/live 或任何
Bybit behavior change。

## 104. 2026-07-01 PM session source checkpoint：IBKR Phase2 Artifact Source Static Guard

本 checkpoint 為 `ibkr_phase2_artifact.rs` 補上 source-only structure guard。這不是
external-surface gate PASS、不是 immutable artifact materialization、不是第一次
IBKR contact；只把 Phase 2 PASS 前必須聚合的 gate、policy、secret-slot、API
topology 與 PM/Operator seal/hash metadata source invariant 機器化。

已完成：

- 新增 `tests/structure/test_ibkr_phase2_artifact_source_static.py`。
- Guard 鎖住 `ibkr_phase2_artifact.rs` 低於 800 行 governance cap。
- Guard 要求 artifact fields、verdict/blocker enum、`is_sha256_hex`、PM/Operator
  reviewer check、policy-flag cross-check、runtime contract cross-check 保持在 source
  中。
- Guard 要求 artifact default 仍 fail-closed：empty contract/source/artifact fields、
  default blocked external gate、default secret-slot contract、default API topology。
- Guard 要求 validate 仍以 `blockers.is_empty()` 作為 `ibkr_contact_allowed` 的唯一
  source verdict，並拒絕 retroactive `ibkr_call_performed`。
- Guard 禁止 env/fs/network/IBKR SDK/clock/thread/process/order/Bybit runtime tokens
  與 secret material access tokens。

驗證：

- New structure guard py_compile：PASS。
- Focused structure guard pytest：`4 passed`。
- Focused Phase2 artifact acceptance：`8 passed`。
- Full `cargo test -p openclaw_types`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不匯入 result、不啟動
collector、不啟動 market-data ingestion、不啟動 DQ writer、不送 paper order、不做
cancel/replace、不匯入 fill、不做 DB apply、不啟動 evidence writer、不啟動 evidence
clock、不啟動 scorecard writer、不新增 GUI fanout、不授權 tiny-live/live 或任何
Bybit behavior change。

## 105. 2026-07-01 PM session source checkpoint：IBKR Feature Flag Secret Auth Source Static Guard

本 checkpoint 為 `ibkr_feature_flag_secret_auth.rs` 補上 source-only structure
guard。這不是 feature flag enablement、不是 secret-slot reader、不是 Phase 2
artifact PASS、不是 session runtime、不是 paper order authorization；只把未來 IBKR
paper auth 前必須同時滿足的 feature flag、secret-slot contract、Phase2 artifact、
session attestation 與 authorization envelope source invariant 機器化。

已完成：

- 新增 `tests/structure/test_ibkr_feature_flag_secret_auth_source_static.py`。
- Guard 鎖住 `ibkr_feature_flag_secret_auth.rs` 低於 800 行 governance cap。
- Guard 要求 matrix contract id、authorization envelope、matrix/verdict/blocker
  surface、evaluation helper 保持在 source 中。
- Guard 要求 default 仍 fail-closed：empty contract/source version、read-only/denied
  envelope、default feature flags、default secret/artifact/session/envelope contracts、
  GUI override denied false、server Rust authoritative false。
- Guard 要求 decision chain 仍同時檢查 lane/broker/live environment/instrument/live
  or account-write operation、read-only/paper/shadow-only flags、secret contract、
  live-secret absence、Phase2 artifact、session attestation 與 authorization envelope。
- Guard 要求 authorization envelope 維持 scope、hash validity、expiry、
  secret-slot fingerprint 與 account fingerprint 跨 secret/artifact/session 的一致性
  檢查。
- Guard 禁止 env/fs/network/IBKR SDK/clock/thread/process/order/Bybit runtime tokens
  與 secret material access tokens。

驗證：

- New structure guard py_compile：PASS。
- Focused structure guard pytest：`5 passed`。
- Focused feature-flag/secret auth acceptance：`8 passed`。
- Full `cargo test -p openclaw_types`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不匯入 result、不啟動
collector、不啟動 market-data ingestion、不啟動 DQ writer、不送 paper order、不做
cancel/replace、不匯入 fill、不做 DB apply、不啟動 evidence writer、不啟動 evidence
clock、不啟動 scorecard writer、不新增 GUI fanout、不授權 tiny-live/live 或任何
Bybit behavior change。

## 106. 2026-07-01 PM session source checkpoint：IBKR Non-Bybit API Allowlist Source Static Guard

本 checkpoint 為 `ibkr_non_bybit_api_allowlist.rs` 補上 source-only structure guard。
這不是 external-surface gate PASS、不是 IBKR client construction、不是 read probe、
不是 paper order submission；只把非 Bybit IBKR API action allowlist/deny matrix 的
source invariant 機器化。

已完成：

- 新增 `tests/structure/test_ibkr_non_bybit_api_allowlist_source_static.py`。
- Guard 鎖住 `ibkr_non_bybit_api_allowlist.rs` 低於 800 行 governance cap。
- Guard 要求 allowlist contract id、action enum、denial reason enum、decision、
  allowlist/verdict/blocker surface、classifier、required-action list 與 bucket
  validator 保持在 source 中。
- Guard 要求 10 個 read actions、3 個 paper-write actions、10 個 denied actions 與
  10 個 typed denial reasons 不得消失。
- Guard 要求 paper-write action 仍需要 external surface gate、session attestation 與
  paper-order gates，且不能在 external gate 後直接 allowed。
- Guard 要求 live order、live account fingerprint、transfer、margin/short/options/CFD、
  market-data entitlement purchase、account management write、Client Portal Web API 仍
  typed-denied。
- Guard 要求 drift detection 保留 missing/duplicated/wrong-bucket checks，並要求
  retroactive IBKR contact、secret serialization、Bybit live execution unprotected 都會
  block。
- Guard 禁止 env/fs/network/IBKR SDK/clock/thread/process/order/Bybit runtime tokens
  與 secret material access tokens。

驗證：

- New structure guard py_compile：PASS。
- Focused structure guard pytest：`5 passed`。
- Focused Phase2 gate/allowlist acceptance：`11 passed`。
- Full `cargo test -p openclaw_types`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不匯入 result、不啟動
collector、不啟動 market-data ingestion、不啟動 DQ writer、不送 paper order、不做
cancel/replace、不匯入 fill、不做 DB apply、不啟動 evidence writer、不啟動 evidence
clock、不啟動 scorecard writer、不新增 GUI fanout、不授權 tiny-live/live 或任何
Bybit behavior change。

## 107. 2026-07-01 PM session source checkpoint：Stock/ETF Broker Capability Registry Source Static Guard

本 checkpoint 為 `stock_etf_broker_capability_registry.rs` 補上 source-only
structure guard。這不是 broker registry activation、不是 IBKR contact、不是 read
probe、不是 paper order authorization；只把 Stock/ETF IBKR operation capability
matrix 的 source invariant 機器化。

已完成：

- 新增 `tests/structure/test_stock_etf_broker_capability_registry_source_static.py`。
- Guard 鎖住 `stock_etf_broker_capability_registry.rs` 低於 800 行 governance cap。
- Guard 要求 registry contract id、audit fields、15 個 required operations、registry
  entry/verdict/blocker surface、expected capability mapper、entry validator 保持在
  source 中。
- Guard 要求 default 仍 fail-closed：CryptoPerp/Bybit、empty operations、Bybit live
  protection false、Python broker write denied false、IBKR live denied false。
- Guard 要求 accepted fixture 仍為 StockEtfCash/IBKR，並保留 Bybit live unchanged、
  Python broker write denied、IBKR live denied、CFD/margin reserved denied、no first
  IBKR contact、no secret serialization。
- Guard 要求 read-only rows 保留 external surface、lane-scoped IPC、readonly probe
  request、session/provenance/instrument gates；paper-write rows 保留 PaperRehearsal、
  paper attestation、scoped authorization、risk policy、decision lease、guardian 與
  lifecycle gates，且 Rust-owned。
- Guard 要求 shadow/scorecard rows 保留 evidence clock、PIT universe、strategy、
  reference/cost/provenance/cash-ledger/result-import gates。
- Guard 要求 live/margin/options/CFD/account-write rows 維持 Denied scope 與 typed
  denials。
- Guard 禁止 env/fs/network/IBKR SDK/clock/thread/process/order/Bybit runtime tokens
  與 secret material access tokens。

驗證：

- New structure guard py_compile：PASS。
- Focused structure guard pytest：`5 passed`。
- Focused broker capability registry acceptance：`10 passed`。
- Full `cargo test -p openclaw_types`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不匯入 result、不啟動
collector、不啟動 market-data ingestion、不啟動 DQ writer、不送 paper order、不做
cancel/replace、不匯入 fill、不做 DB apply、不啟動 evidence writer、不啟動 evidence
clock、不啟動 scorecard writer、不新增 GUI fanout、不授權 tiny-live/live 或任何
Bybit behavior change。

## 108. 2026-07-01 PM session source checkpoint：Stock/ETF Risk Policy Source Static Guard

本 checkpoint 為 `stock_etf_risk_policy.rs` 補上 source-only structure guard。這不是
risk policy runtime enablement、不是 IBKR contact、不是 connector start、不是 paper
order authorization；只把 dormant Stock/ETF cash risk-policy contract 的 source
invariant 機器化。

已完成：

- 新增 `tests/structure/test_stock_etf_risk_policy_source_static.py`。
- Guard 鎖住 `stock_etf_risk_policy.rs` 低於 800 行 governance cap。
- Guard 要求 risk-policy contract id、source config structs、caps/cash-only/universe/
  cost-model/paper-order validators、hash helper 與 verdict/blocker surface 保持在
  source 中。
- Guard 要求 default 仍 fail-closed：CryptoPerp/Bybit、LiveReservedDenied、
  `enabled=true` 會被 blocker 擋住、`shadow_only=false`、margin/short/options/CFD/
  transfer/live all true、Bybit live protected false。
- Guard 要求 accepted fixture 仍為 StockEtfCash/IBKR Paper、`enabled=false`、
  `shadow_only=true`、cash-only、stock/ETF/cash allowed、CFD/crypto denied、Bybit live
  unchanged、no IBKR contact、no connector runtime、no secret serialization。
- Guard 要求 caps 維持 positive finite 與 order <= position <= daily ordering，
  max open orders/positions 上限檢查仍存在。
- Guard 要求 frozen universe、instrument identity、market session、commission、
  spread/slippage/FX/conservative penalty、Rust authority、session attestation、
  decision lease、guardian、idempotency key、broker reconciliation gates 不得消失。
- Guard 禁止 env/fs/network/IBKR SDK/clock/thread/process/order/Bybit runtime tokens
  與 secret material access tokens。

驗證：

- New structure guard py_compile：PASS。
- Focused structure guard pytest：`5 passed`。
- Focused risk policy acceptance：`8 passed`。
- Full `cargo test -p openclaw_types`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不匯入 result、不啟動
collector、不啟動 market-data ingestion、不啟動 DQ writer、不送 paper order、不做
cancel/replace、不匯入 fill、不做 DB apply、不啟動 evidence writer、不啟動 evidence
clock、不啟動 scorecard writer、不新增 GUI fanout、不授權 tiny-live/live 或任何
Bybit behavior change。

## 109. 2026-07-01 PM session source checkpoint：Stock/ETF Paper Order Request Source Static Guard

本 checkpoint 為 `stock_etf_paper_order_request.rs` 與
`stock_etf_paper_order_request/validation.rs` 補上 source-only semantic guard。這不是
IPC runtime、不是 IBKR contact、不是 connector start、不是 paper order route；只把
paper order request envelope 在 lane-scoped IPC 與 IBKR paper lifecycle 之間的 source
invariant 機器化。

已完成：

- 新增 `tests/structure/test_stock_etf_paper_order_request_source_static.py`。
- Guard 鎖住 parent module 與 validation module 低於 800 行 governance cap。
- Guard 要求 request envelope fields、paper order type/time-in-force/limit-price policy、
  verdict/blocker surface 與 validation helper surface 保持在 source 中。
- Guard 要求 default 仍 fail-closed：CryptoPerp/Bybit、LiveReservedDenied、
  UnknownDenied IPC method、TransferOrAccountWrite operation、Denied authority、
  `effect_capable=false`，且 no contact/runtime/secret/order/Bybit/live flags。
- Guard 要求 preview 仍是 `PaperOrderSubmit` + ReadOnly + effect=false；submit/cancel/
  replace 仍是 PaperRehearsal + effect=true，並保持 operation/scope/effect mismatch
  blockers。
- Guard 要求 request id、account/session/scoped-auth/guardian/lifecycle/broker-capability
  hashes、decision lease、audit event、risk/instrument/cost/universe/source artifact hashes
  checks 不得消失。
- Guard 要求 submit/preview order intent 仍限制 normalized symbol、Buy/Sell side、
  Stock/ETF instrument、positive quantity、limit/market price policy 與 TIF compatibility。
- Guard 要求 preview 禁止 effect/lifecycle fields，submit 禁止 broker order id 與
  cancel/replace fields，cancel 禁止 order-shape pollution，replace 禁止 original mutable
  fields。
- Guard 禁止 env/fs/network/IBKR SDK/clock/thread/process/order/Bybit runtime tokens
  與 secret material access tokens。

驗證：

- New structure guard py_compile：PASS。
- Focused structure guard pytest：`5 passed`。
- Existing split + new semantic paper-order structure guards：`8 passed`。
- Focused paper order request acceptance：`8 passed`。
- Full `cargo test -p openclaw_types`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不匯入 result、不啟動
collector、不啟動 market-data ingestion、不啟動 DQ writer、不送 paper order、不做
cancel/replace、不匯入 fill、不做 DB apply、不啟動 evidence writer、不啟動 evidence
clock、不啟動 scorecard writer、不新增 GUI fanout、不授權 tiny-live/live 或任何
Bybit behavior change。

## 110. 2026-07-01 PM session source checkpoint：IBKR Paper Lifecycle Source Static Guard

本 checkpoint 為 `ibkr_paper_lifecycle.rs` 補上 source-only structure guard。這不是
IBKR contact、不是 connector construction、不是 paper order route、不是 lifecycle
writer；只把 IBKR paper order lifecycle 與 append-only event-log contract 的 source
invariant 機器化。

已完成：

- 新增 `tests/structure/test_ibkr_paper_lifecycle_source_static.py`。
- Guard 鎖住 `ibkr_paper_lifecycle.rs` 低於 800 行 governance cap。
- Guard 要求 lifecycle/event-log contract ids、event fields、event verdict/blocker
  surface、stale-state policy、restart recovery input/action、transition helpers 保持在
  source 中。
- Guard 要求 default event 仍 blocked/incomplete，accepted ack fixture 仍保留 request
  contract lineage、event sequence、append-only hashes、paper environment、submit ack
  transition、idempotency/reconciliation ids 與 raw/redacted hashes。
- Guard 要求 append-only validation 保留 genesis sequence/hash rules、event/request
  hash checks、StockEtfCash/IBKR/Paper checks、live environment denial、paper lifecycle
  operation gating、operation-transition gating、state-transition gating、raw/redacted hash
  checks。
- Guard 要求 StateUnknown recovery 只能 manual-review 或 terminal-with-evidence，denied
  events 必須有 denial reason 且不能 advance active state，stale-state policy matching
  不得消失。
- Guard 要求 restart recovery 分類保持 fail-closed：terminal evidence preserve、
  broker known + broker order id + idempotency key 才 reconcile，否則 MarkStateUnknown。
- Guard 禁止 env/fs/network/IBKR SDK/clock/thread/process/order/Bybit runtime tokens
  與 secret material access tokens。

驗證：

- New structure guard py_compile：PASS。
- Focused structure guard pytest：`6 passed`。
- Focused paper lifecycle acceptance：`12 passed`。
- Full `cargo test -p openclaw_types`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不匯入 result、不啟動
collector、不啟動 market-data ingestion、不啟動 DQ writer、不送 paper order、不做
cancel/replace、不匯入 fill、不做 DB apply、不啟動 evidence writer、不啟動 evidence
clock、不啟動 scorecard writer、不新增 GUI fanout、不授權 tiny-live/live 或任何
Bybit behavior change。

## 111. 2026-07-01 PM session source checkpoint：Stock/ETF Paper Fill Import Request Source Static Guard

本 checkpoint 為 `stock_etf_paper_fill_import_request.rs` 補上 source-only structure
guard。這不是 IBKR contact、不是 connector construction、不是 fill import execution、
不是 DB apply、不是 paper order route；只把 paper fill import request envelope 的
source invariant 機器化。

已完成：

- 新增 `tests/structure/test_stock_etf_paper_fill_import_request_source_static.py`。
- Guard 鎖住 `stock_etf_paper_fill_import_request.rs` 低於 800 行 governance cap。
- Guard 要求 fill-import contract id、request/verdict/blocker surface、required-field
  validator、boundary-flag validator 與 lifecycle/event-log/redaction imports 保持在
  source 中。
- Guard 要求 default 仍 fail-closed：CryptoPerp/Bybit、LiveReservedDenied、
  UnknownDenied IPC method、TransferOrAccountWrite operation、Denied authority、
  `effect_capable=false`、observed state/stale policy empty。
- Guard 要求 accepted fixture 仍是 StockEtfCash/IBKR/Paper、ImportPaperFills、
  PaperOrderFillImport、ReadOnly、effect=false，並綁定 lifecycle/event-log/redaction
  contract ids、Filled observed state、PreserveTerminalWithEvidence stale policy。
- Guard 要求 request id、session attestation、lifecycle/event-log/redaction/source
  artifact hashes、reconciliation run id、broker order id、execution id、commission report id、
  import idempotency key、raw/redacted hashes checks 不得消失。
- Guard 要求 duplicate import denial、StateUnknown stale-policy handling、IBKR contact、
  connector runtime、secret serialization、fill import、DB apply、order route、Bybit reuse、
  live/tiny-live、margin/short/options/CFD、Python direct broker write boundary flags 不得消失。
- Guard 禁止 env/fs/network/IBKR SDK/clock/thread/process/order/Bybit runtime tokens
  與 secret material access tokens。

驗證：

- New structure guard py_compile：PASS。
- Focused structure guard pytest：`6 passed`。
- Focused paper fill import request acceptance：`6 passed`。
- Full `cargo test -p openclaw_types`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不匯入 result、不啟動
collector、不啟動 market-data ingestion、不啟動 DQ writer、不送 paper order、不做
cancel/replace、不匯入 fill、不做 DB apply、不啟動 evidence writer、不啟動 evidence
clock、不啟動 scorecard writer、不新增 GUI fanout、不授權 tiny-live/live 或任何
Bybit behavior change。

## 112. 2026-07-01 PM session source checkpoint：Stock/ETF Paper Shadow Reconciliation Source Static Guard

本 checkpoint 為 `stock_etf_paper_shadow_reconciliation.rs` 補上 source-only structure
guard。這不是 IBKR contact、不是 connector construction、不是 fill import execution、
不是 shadow fill generation、不是 reconciliation writer、不是 scorecard writer、不是
DB apply、不是 paper order route；只把 paper fill 與 synthetic shadow fill reconciliation
envelope 的 source invariant 機器化。

已完成：

- 新增 `tests/structure/test_stock_etf_paper_shadow_reconciliation_source_static.py`。
- Guard 鎖住 `stock_etf_paper_shadow_reconciliation.rs` 低於 800 行 governance cap。
- Guard 要求 reconciliation contract id/scope、request/verdict/blocker surface、
  required-field validator、reconciliation-evidence validator、boundary-flag validator 保持在
  source 中。
- Guard 要求 default 仍 fail-closed：CryptoPerp/Bybit、Denied authority、effect=false、
  append-only event 未 ready、paper fill 未 imported、shadow fill 未 synthetic、divergence
  threshold 為 0。
- Guard 要求 accepted fixture 仍是 StockEtfCash/IBKR、`paper_shadow`、ReadOnly、
  effect=false，並保留 append-only event ready、paper fill imported、synthetic shadow fill、
  divergence <= threshold、unmatched paper/shadow fill count 為 0。
- Guard 要求 reconciliation/broker/execution/commission/shadow-signal ids 與 lifecycle、
  event-log、paper-fill-import、shadow-signal、shadow-fill-model、cost-model、
  market-data-provenance、divergence-threshold、paper-shadow-link、raw/redacted/source
  artifact hashes checks 不得消失。
- Guard 要求 append-only event、paper fill imported、shadow fill synthetic、divergence
  threshold、divergence exceed、unmatched paper/shadow fill gates 不得消失。
- Guard 要求 IBKR contact、connector runtime、secret serialization、fill import、shadow
  fill generation、reconciliation writer、scorecard writer、DB apply、order route、Bybit reuse、
  live/tiny-live、margin/short/options/CFD、Python direct broker write boundary flags 不得消失。
- Guard 禁止 env/fs/network/IBKR SDK/clock/thread/process/order/Bybit runtime tokens
  與 secret material access tokens。

驗證：

- New structure guard py_compile：PASS。
- Focused structure guard pytest：`7 passed`。
- Focused paper shadow reconciliation acceptance：`5 passed`。
- Full `cargo test -p openclaw_types`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不匯入 result、不啟動
collector、不啟動 market-data ingestion、不啟動 DQ writer、不送 paper order、不做
cancel/replace、不匯入 fill、不生成 shadow fill、不做 reconciliation/scorecard writer、不做
DB apply、不啟動 evidence writer、不啟動 evidence clock、不新增 GUI fanout、不授權
tiny-live/live 或任何 Bybit behavior change。

## 113. 2026-07-01 PM session source checkpoint：Stock/ETF Shadow Signal Request Source Static Guard

本 checkpoint 為 `stock_etf_shadow_signal_request.rs` 補上 source-only structure guard。
這不是 IBKR contact、不是 connector construction、不是 shadow signal emission、不是
shadow fill generation、不是 scorecard writer、不是 DB apply、不是 paper order route；
只把 paper-shadow signal evaluation request envelope 的 source invariant 機器化。

已完成：

- 新增 `tests/structure/test_stock_etf_shadow_signal_request_source_static.py`。
- Guard 鎖住 `stock_etf_shadow_signal_request.rs` 低於 800 行 governance cap。
- Guard 要求 shadow-signal request contract id、request/verdict/blocker surface、
  required-field validator、boundary-flag validator 保持在 source 中。
- Guard 要求 default 仍 fail-closed：CryptoPerp/Bybit、LiveReservedDenied、
  UnknownDenied IPC method、TransferOrAccountWrite operation、Denied authority、
  `effect_capable=false`。
- Guard 要求 accepted fixture 仍是 StockEtfCash/IBKR/Shadow、EvaluateShadowSignal、
  ShadowSignalEmit、ShadowOnly、effect=false。
- Guard 要求 request/evaluation/shadow-signal ids 與 evidence clock、PIT universe、
  strategy hypothesis、instrument identity、market data provenance、cost model、
  asset-lane events、source artifact hash checks 不得消失。
- Guard 要求 IBKR contact、connector runtime、secret serialization、shadow signal
  emission、shadow fill generation、scorecard writer、DB apply、order route、Bybit reuse、
  live/tiny-live、margin/short/options/CFD、Python direct broker write boundary flags 不得消失。
- Guard 禁止 env/fs/network/IBKR SDK/clock/thread/process/order/Bybit runtime tokens
  與 secret material access tokens。

驗證：

- New structure guard py_compile：PASS。
- Focused structure guard pytest：`6 passed`。
- Focused shadow signal request acceptance：`5 passed`。
- Full `cargo test -p openclaw_types`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不匯入 result、不啟動
collector、不啟動 market-data ingestion、不啟動 DQ writer、不送 paper order、不做
cancel/replace、不匯入 fill、不發射 shadow signal、不生成 shadow fill、不做 scorecard
writer、不做 DB apply、不啟動 evidence writer、不啟動 evidence clock、不新增 GUI fanout、
不授權 tiny-live/live 或任何 Bybit behavior change。

## 114. 2026-07-01 PM session source checkpoint：Stock/ETF Scorecard Inputs Source Static Guard

本 checkpoint 為 split `stock_etf_scorecard_inputs` parent/components/bundle modules 補上
source-only structure guard。這不是 IBKR contact、不是 broker fill import、不是 scorecard
derivation、不是 scorecard writer、不是 DB apply、不是 evidence clock；只把 paper-shadow
scorecard inputs 的 source invariant 與容量/效率邊界機器化。

已完成：

- 新增 `tests/structure/test_stock_etf_scorecard_inputs_source_static.py`。
- Guard 鎖住 parent、components、bundle 三檔各自低於 800 行 governance cap。
- Guard 要求 cash ledger、cost model、benchmark、shadow fill model、storage capacity
  contract ids 與 storage caps/retention/query-SLO/archive path prefix 保持在 parent source。
- Guard 要求 cash ledger 仍限制 StockEtfCash/IBKR 且只接受 Paper/ReadOnly，並保留 account、
  snapshot、positions、currency、as-of、source-report checks。
- Guard 要求 cost/benchmark validators、shadow fill synthetic marker、broker paper fill/live
  fill separation、storage universe/rows/index/query-SLO caps、raw/compressed retention order、
  safe lane-scoped archive path、capacity-plan hash、capacity breach blocks evidence clock policy
  不得消失。
- Guard 要求 bundle accepted fixture 仍由 cash ledger/cost/benchmark/shadow fill/storage
  accepted fixtures 組成，並保持 readonly probe result import contract id、scorecard
  derived-only、paper/shadow fills separate、live fill false、Bybit live execution unchanged。
- Guard 要求 bundle validation 保留 sub-validator rejection、cross-contract hashes、source
  commit、derived-only、paper-shadow separation、live fill denial、Bybit live protection、IBKR
  contact、connector runtime、broker fill import、scorecard writer、DB apply、evidence clock、
  secret serialization、live/tiny-live boundary flags。
- Guard 禁止 env/fs/network/IBKR SDK/clock/thread/process/order/Bybit runtime tokens
  與 secret material access tokens。

驗證：

- New structure guard py_compile：PASS。
- Focused structure guard pytest：`7 passed`。
- Focused scorecard inputs acceptance：`12 passed`。
- Full `cargo test -p openclaw_types`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不匯入 result、不啟動
collector、不啟動 market-data ingestion、不啟動 DQ writer、不送 paper order、不做
cancel/replace、不匯入 broker fill、不衍生或寫入 scorecard、不做 DB apply、不啟動
evidence writer/clock、不新增 GUI fanout、不授權 tiny-live/live 或任何 Bybit behavior change。

## 115. 2026-07-01 PM session source checkpoint：Stock/ETF Scorecard Derivation Source Static Guard

本 checkpoint 為 `stock_etf_scorecard_derivation.rs` 補上 source-only structure guard。
這不是 IBKR contact、不是 broker fill import、不是 shadow fill generation、不是
reconciliation writer、不是 scorecard writer、不是 DB apply、不是 evidence clock；只把 sealed
derived scorecard artifact lineage 的 source invariant 機器化。

已完成：

- 新增 `tests/structure/test_stock_etf_scorecard_derivation_source_static.py`。
- Guard 鎖住 `stock_etf_scorecard_derivation.rs` 低於 800 行 governance cap。
- Guard 要求 derivation contract id、request/verdict/blocker surface、id validator、hash
  validator、authority validator 保持在 source 中。
- Guard 要求 default 仍 fail-closed：CryptoPerp/Bybit、LiveReservedDenied、atomic-facts-only
  false、idempotent replay false、paper/shadow separation false、Bybit live protection false、
  sealed false。
- Guard 要求 accepted fixture 仍是 StockEtfCash/IBKR/Paper，並保留 atomic-facts-only、
  idempotent replay、paper/shadow separation、Bybit live execution unchanged、no side-effect
  flags 與 sealed=true。
- Guard 要求 derivation/strategy/universe/benchmark/as-of ids 與 scorecard input、
  evidence clock manifest、DQ manifest、paper-shadow reconciliation、formula appendix、
  statistical preregistration、scorecard manifest/verdict、source commit、derivation code、
  output artifact、QC/MIT/QA review hash checks 不得消失。
- Guard 要求 derived-only、idempotent replay、paper-shadow separation、Bybit live protection、
  IBKR contact、connector runtime、broker fill import、shadow fill generation、reconciliation
  writer、scorecard writer、DB apply、evidence clock、secret serialization、live/tiny-live、
  sealed boundary flags 不得消失。
- Guard 禁止 env/fs/network/IBKR SDK/clock/thread/process/order/Bybit runtime tokens
  與 secret material access tokens。

驗證：

- New structure guard py_compile：PASS。
- Focused structure guard pytest：`6 passed`。
- Focused scorecard derivation acceptance：`5 passed`。
- Full `cargo test -p openclaw_types`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不匯入 result、不啟動
collector、不啟動 market-data ingestion、不啟動 DQ writer、不送 paper order、不做
cancel/replace、不匯入 broker fill、不生成 shadow fill、不做 reconciliation/scorecard writer、
不做 DB apply、不啟動 evidence writer/clock、不新增 GUI fanout、不授權 tiny-live/live 或任何
Bybit behavior change。

## 116. 2026-07-01 PM session source checkpoint：Stock/ETF Scorecard Verdict Source Static Guard

本 checkpoint 為 `stock_etf_scorecard_verdict.rs` 補上 source-only structure guard。這不是
IBKR contact、不是 scorecard writer、不是 DB apply、不是 evidence clock、不是 tiny-live/live
authorization、不是 Bybit gate lowering；只把 statistical verdict 與 tiny-live 討論前置 gate
的 source invariant 機器化。

已完成：

- 新增 `tests/structure/test_stock_etf_scorecard_verdict_source_static.py`。
- Guard 鎖住 `stock_etf_scorecard_verdict.rs` 低於 800 行 governance cap。
- Guard 要求 verdict contract id、label enum、request/verdict/blocker surface、contract/hash/
  threshold/window/divergence/profitability/probability/quality/review authority validators 保持在
  source 中。
- Guard 要求 default 仍 fail-closed：CryptoPerp/Bybit、LiveReservedDenied、
  InsufficientEvidence、derived-only false、paper/shadow separation false、Bybit live protection
  false、sealed false。
- Guard 要求 profitability-feasible fixture 保留 StockEtfCash/IBKR/Paper、window/observation
  門檻、net PnL、positive LCBs、divergence threshold、PSR/DSR thresholds、quality labels、
  derived-only、paper/shadow separation、no live fill、Bybit live unchanged、no tiny-live/live、
  sealed=true。
- Guard 要求 label dispatch 保留 ProfitabilityFeasible/ResearchPromising/EngineeringReady/
  ExecutionModelInvalid/InsufficientEvidence/Kill 差異，且 ExecutionModelInvalid 必須有 execution
  failure evidence。
- Guard 要求 formula appendix、statistical preregistration、scorecard input、evidence clock、
  DQ、benchmark/cost/strategy/reference/reconciliation/manifest/rationale hashes，window、
  independent observation、divergence、PSR/DSR、LCB、quality label checks 不得消失。
- Guard 要求 QC/MIT/QA review hashes/pass flags、derived-only、paper-shadow separation、live
  fill denial、Bybit live protection、IBKR contact、connector runtime、broker fill import、
  scorecard writer、DB apply、evidence clock、secret serialization、live/tiny-live、sealed boundary
  flags 不得消失。
- Guard 禁止 env/fs/network/IBKR SDK/clock/thread/process/order/Bybit runtime tokens
  與 secret material access tokens。

驗證：

- New structure guard py_compile：PASS。
- Focused structure guard pytest：`7 passed`。
- Focused scorecard verdict acceptance：`8 passed`。
- Full `cargo test -p openclaw_types`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不匯入 result、不啟動
collector、不啟動 market-data ingestion、不啟動 DQ writer、不送 paper order、不做
cancel/replace、不匯入 broker fill、不做 scorecard writer、不做 DB apply、不啟動 evidence
writer/clock、不降低任何 Bybit gate、不新增 GUI fanout、不授權 tiny-live/live 或任何 Bybit
behavior change。

## 117. 2026-07-01 PM session source checkpoint：Stock/ETF Tiny-Live Eligibility Source Static Guard

本 checkpoint 為 `stock_etf_tiny_live_eligibility.rs` 補上 source-only structure guard。這不是
tiny-live/live authorization、不是 IBKR contact、不是 connector construction、不是 secret
access、不是 evidence clock、不是 Bybit gate lowering；只把未來 ADR discussion-only gate 的
source invariant 機器化。

已完成：

- 新增 `tests/structure/test_stock_etf_tiny_live_eligibility_source_static.py`。
- Guard 鎖住 `stock_etf_tiny_live_eligibility.rs` 低於 800 行 governance cap。
- Guard 要求 ADR/AMD/spec release paths、tiny-live ADR eligibility contract id、decision enum、
  request/verdict/blocker surface 保持在 source 中。
- Guard 要求 default 仍 fail-closed：NotEligible、paper-shadow window incomplete、LCBs/observation/
  divergence threshold 為 0、secret serialization false、sealed false。
- Guard 要求 accepted fixture 仍只允許 AdrDiscussionOnly，並保留 phase5 release packet、
  scorecard derivation/verdict/manifest、paper-shadow reconciliation、DQ manifest、statistical
  preregistration、QC/MIT/QA review hashes，paper-shadow window complete、positive LCBs、
  independent observation gate、divergence gate、labels/reviews passed、sealed=true。
- Guard 要求 contract/path/hash/stat/review gates 不得消失。
- Guard 要求 decision matrix 保持：AdrDiscussionOnly 可通過，TinyLiveAuthorized 必須回
  TinyLiveAuthorizationRequested，LiveAuthorized 必須回 LiveAuthorizationRequested，NotEligible
  必須回 DecisionNotAdrDiscussionOnly。
- Guard 要求 secret serialization denial 與 sealed requirement 不得消失。
- Guard 禁止 env/fs/network/IBKR SDK/clock/thread/process/order/Bybit runtime tokens
  與 secret material access tokens。

驗證：

- New structure guard py_compile：PASS。
- Focused structure guard pytest：`6 passed`。
- Focused tiny-live eligibility acceptance：`7 passed`。
- Full `cargo test -p openclaw_types`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不匯入 result、不啟動
collector、不啟動 market-data ingestion、不啟動 DQ writer、不送 paper order、不做
cancel/replace、不匯入 broker fill、不做 scorecard writer、不做 DB apply、不啟動 evidence
writer/clock、不降低任何 Bybit gate、不新增 GUI fanout、不授權 tiny-live/live 或任何 Bybit
behavior change。

## 118. 2026-07-01 PM session source checkpoint：Stock/ETF Release Packet Source Static Guard

本 checkpoint 為 `stock_etf_release_packet.rs` 補上 source-only structure guard。這不是
PASS artifact creation、不是 secret slot、不是 broker session、不是 paper order、不是
evidence clock、不是 tiny-live/live authorization；只把 paper/shadow release packet 的
source invariant 機器化。

已完成：

- 新增 `tests/structure/test_stock_etf_release_packet_source_static.py`。
- Guard 鎖住 `stock_etf_release_packet.rs` 低於 800 行 governance cap。
- Guard 要求 ADR/AMD/spec release paths、release packet contract id、manifest hash、
  PG migration evidence、kill-disable cleanup proof、release packet/verdict/blocker surface 保持在
  source 中。
- Guard 要求 default 仍 fail-closed：empty packet id、source_version 0、paper-shadow window
  incomplete、engineering shakedown incomplete、secret false、IBKR live/tiny-live false、sealed false。
- Guard 要求 accepted fixture 保留 exact release paths、all required roles、manifest hashes、
  no-migration fixture、kill-disable cleanup proof、evidence archive pointer/hash、paper-shadow
  window complete、engineering shakedown complete、secret false、IBKR live/tiny-live false、
  sealed=true。
- Guard 要求 PM/Operator/E2/E3/E4/QA/QC/MIT signoff mapping、role reports、E2/E3/E4/QA logs、
  manifest hashes、PG migration dry-run/double-apply evidence、redaction fixture、GUI screenshots、
  DQ manifests、scorecard regeneration hashes、kill-disable cleanup proof、evidence archive、
  paper-shadow window、engineering shakedown gates 不得消失。
- Guard 要求 secret serialization denial、IBKR live/tiny-live authority denial、release packet
  sealed requirement 不得消失。
- Guard 禁止 env/fs/network/IBKR SDK/clock/thread/process/order/Bybit runtime tokens
  與 secret material access tokens。

驗證：

- New structure guard py_compile：PASS。
- Focused structure guard pytest：`7 passed`。
- Focused release packet acceptance：`8 passed`。
- Full `cargo test -p openclaw_types`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不匯入 result、不啟動
collector、不啟動 market-data ingestion、不啟動 DQ writer、不送 paper order、不做
cancel/replace、不匯入 broker fill、不做 scorecard writer、不做 DB apply、不啟動 evidence
writer/clock、不建立 PASS artifact、不建立 secret slot、不授權 tiny-live/live 或任何 Bybit
behavior change。

## 119. 2026-07-01 PM session source checkpoint：Stock/ETF Phase0 Manifest Source Static Guard

本 checkpoint 為 `stock_etf_phase0_manifest.rs` 補上 source-only structure guard。這不是
runtime authority、不是 IBKR contact、不是 connector construction、不是 migration、不是
evidence clock、不是 order route；只把 Phase0 named contract packet manifest 的 source
invariant 機器化。

已完成：

- 新增 `tests/structure/test_stock_etf_phase0_manifest_source_static.py`。
- Guard 鎖住 `stock_etf_phase0_manifest.rs` 低於 800 行 governance cap。
- Guard 要求 Phase0 manifest schema/status/scope/generated_at/ADR/AMD/packet paths、required
  contract set、manifest/authority/API baseline/global denials/unlock table/verdict/blocker surface
  保持在 source 中。
- Guard 要求 accepted manifest 仍是 StockEtfCash/IBKR/paper_shadow_only，並保留 authority、
  API baseline、global denials、contracts、phase unlock accepted fixtures。
- Guard 要求 API baseline 保持 `ib_gateway_tws_api`、`loopback_only`、paper port 4002、
  live ports denied、`ibkr_call_performed=false`。
- Guard 要求 global denials 保留 IBKR live、tiny-live、margin、short、options、CFD、transfer、
  account-management writes、Python broker write authority、GUI lane authority、automatic
  promotion 全部 denied。
- Guard 要求 phase unlock 保持 Phase1 只在 E2/E4/QA 後允許，Phase2 contact、Phase3 evidence
  clock、Phase4 GUI runtime、Phase5 online、tiny-live/live 全部 fail-closed。
- Guard 要求 required contract missing/duplicated/unexpected detection 不得消失。
- Guard 禁止 env/fs/network/IBKR SDK/clock/thread/process/order/Bybit runtime tokens
  與 secret material access tokens。

驗證：

- New structure guard py_compile：PASS。
- Focused structure guard pytest：`6 passed`。
- Focused Phase0 manifest acceptance：`6 passed`。
- Full `cargo test -p openclaw_types`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不執行 read probe、不匯入 result、不啟動
collector、不啟動 market-data ingestion、不啟動 DQ writer、不送 paper order、不做
cancel/replace、不做 migration、不啟動 evidence writer/clock、不新增 GUI fanout、不授權
tiny-live/live 或任何 Bybit behavior change。

## 120. 2026-07-01 PM session source checkpoint：Stock/ETF Asset-Lane Audit Events Source Static Guard

本 checkpoint 為 `stock_etf_audit_events.rs` 補上 source-only structure guard。這不是
audit writer、不是 DB apply、不是 IBKR contact、不是 connector runtime、不是 evidence
clock、不是 order route；只把 asset-lane immutable event reference contract 的 source
invariant 機器化。

已完成：

- 新增 `tests/structure/test_stock_etf_audit_events_source_static.py`。
- Guard 鎖住 `stock_etf_audit_events.rs` 低於 800 行 governance cap。
- Guard 要求 exact `audit.asset_lane_events_v1` contract id、event kind 列表、event field
  surface、verdict/blocker surface 保持在 source 中。
- Guard 要求 default event fail-closed：`source_version=0`、`Unknown` event kind、sequence
  missing、StockEtfCash/IBKR/ReadOnly、`allowed=false`、no secret serialization、no raw payload
  inline。
- Guard 要求 accepted genesis/chained fixtures 保留 hash linkage、IBKR external-surface source、
  scorecard input reference、readonly/derived permission scopes。
- Guard 要求 validation matrix 保留 schema/source-version、event id/kind/sequence、genesis
  previous-hash、non-genesis hash、actor/source、lane/broker/live denial、account/session/source
  hashes、allowed/denied denial-reason rules、input hashes、secret/raw-payload denials。
- Guard 禁止 env/fs/network/IBKR SDK/clock/thread/process/order/Bybit runtime tokens
  與 secret material access tokens。

驗證：

- New structure guard py_compile：PASS。
- Focused structure guard pytest：`6 passed`。
- Focused asset-lane audit events acceptance：`9 passed`。
- Full `cargo test -p openclaw_types`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動
connector runtime、不開 socket/HTTP、不送 paper order、不做 cancel/replace、不匯入 fill、
不做 audit writer、不做 DB apply、不啟動 evidence writer/clock、不授權 tiny-live/live 或任何
Bybit behavior change。

## 121. 2026-07-01 PM session source checkpoint：Stock/ETF DB Evidence DDL Source Static Guard

本 checkpoint 為 `stock_etf_db_evidence_ddl.rs` 補上 source-only structure guard。這不是
migration apply、不是 PG write、不是 sqlx registration、不是 DB runtime、不是 IBKR contact、
不是 paper order、不是 evidence clock；只把 DB evidence DDL contract 與 source SQL auditor 的
source invariant 機器化。

已完成：

- 新增 `tests/structure/test_stock_etf_db_evidence_ddl_source_static.py`。
- Guard 鎖住 `stock_etf_db_evidence_ddl.rs` 低於 800 行 governance cap。
- Guard 要求 exact `stock_etf_db_evidence_ddl_v1` contract id、source-only SQL path、
  required schemas/tables/natural keys、contract/verdict/blocker/source-audit surface 保持在
  source 中。
- Guard 要求 accepted fixture 保持 source-only：不複製到 `sql/migrations/`、不做 DB apply、
  不做 PG write、不註冊 sqlx migration、不宣稱 PM/Operator apply authorization。
- Guard 要求 E2/E4 review、Linux PG dry-run、double-apply、Guard A/B/C、stock asset-lane
  check、IBKR broker check、live denial、paper-shadow table separation、synthetic shadow check、
  audit event table、forward-only retention、destructive rollback denial 保持 required。
- Guard 要求 source SQL auditor 保留 source-only banner、migration/apply denial、destructive
  SQL denial、schema/table/column/natural-key/FK checks、stock/IBKR/paper/live checks、raw hash、
  append-only audit event、hypertable/retention plan、hot-path index checks。
- Guard 禁止 env/fs/network/IBKR SDK/clock/thread/process/order/Bybit runtime tokens
  與 secret material access tokens。

驗證：

- New structure guard py_compile：PASS。
- Focused structure guard pytest：`6 passed`。
- Focused DB evidence DDL acceptance：`10 passed`。
- Full `cargo test -p openclaw_types`：PASS。

PM 邊界不變：此 checkpoint 不把 source draft 複製到 `sql/migrations/`，不做 DB
migration/apply，不做 PG write/dry-run，不註冊 sqlx migration，不呼叫 IBKR、不導入 IBKR SDK、
不讀/建 secret、不啟動 connector runtime、不送 paper order、不做 evidence writer/clock、
不授權 tiny-live/live 或任何 Bybit behavior change。

## 122. 2026-07-01 PM session source checkpoint：Stock/ETF Disable Cleanup Runbook Source Static Guard

本 checkpoint 為 `stock_etf_disable_cleanup_runbook.rs` 補上 source-only structure guard。這不是
service stop、不是 env mutation、不是 secret inspection、不是 DB cleanup、不是 IBKR contact、
不是 paper order、不是 launch authorization；只把 kill-switch / disable-cleanup runbook 的
source invariant 機器化。

已完成：

- 新增 `tests/structure/test_stock_etf_disable_cleanup_runbook_source_static.py`。
- Guard 鎖住 `stock_etf_disable_cleanup_runbook.rs` 低於 800 行 governance cap。
- Guard 要求 exact `stock_etf_kill_switch_and_disable_cleanup_runbook_v1` runbook id、
  required env flag values、required proof kinds、contract/verdict/blocker surface 保持在 source
  中。
- Guard 允許固定 `OPENCLAW_*` disable flag 字面量，但禁止任何 env/fs/network/IBKR SDK/clock/
  thread/process/order/Bybit runtime token。
- Guard 要求 default runbook fail-closed：CryptoPerp/Bybit placeholder、Bybit live unchanged
  proof missing、no launch authority、empty env/proof vectors。
- Guard 要求 accepted fixture 保留 StockEtfCash/IBKR、Bybit live unchanged true、IBKR contact/
  connector runtime/paper order/secret/destructive DB cleanup/tiny-live/live 全部 false。
- Guard 要求 env/proof validation 保留 missing/duplicated/unexpected checks、expected/observed
  value checks、evidence hash checks、proof verified/runtime-authority/destructive-cleanup checks。

驗證：

- New structure guard py_compile：PASS。
- Focused structure guard pytest：`7 passed`。
- Focused disable-cleanup runbook acceptance：`7 passed`。
- Full `cargo test -p openclaw_types`：PASS。

PM 邊界不變：此 checkpoint 不讀 env、不改 env、不停服務、不檢查 secret、不建立 secret slot、
不做 destructive cleanup、不做 DB delete/truncate、不呼叫 IBKR、不導入 IBKR SDK、不啟動
connector runtime、不送 paper order、不授權 paper-shadow launch/tiny-live/live 或任何 Bybit
behavior change。

## 123. 2026-07-01 PM session source checkpoint：Stock/ETF GUI Lane Contract Source Static Guard

本 checkpoint 為 `stock_etf_gui_lane_contract.rs` 補上 source-only structure guard。這不是 GUI
write surface、不是 lane selection authority、不是 IBKR contact、不是 secret/order widget、不是
runtime route；只把 display-only GUI lane contract 的 source invariant 機器化。

已完成：

- 新增 `tests/structure/test_stock_etf_gui_lane_contract_source_static.py`。
- Guard 鎖住 `stock_etf_gui_lane_contract.rs` 低於 800 行 governance cap。
- Guard 要求 exact `gui_lane_contract_v1` contract id、16 個 Stock/ETF GET-only endpoint
  constants/path、contract/verdict/blocker surface 保持在 source 中。
- Guard 要求 default contract fail-closed：CryptoPerp default、Stock/ETF tab missing、endpoints
  empty/not GET-only、display-only/client-state-untrusted/authority-denial flags 全部 false。
- Guard 要求 accepted fixture 保留 display-only、client lane state untrusted、localStorage/query/
  hidden-field authority denied、no login-success selector、no POST route、no order/secret widget、
  no render-time IBKR contact、paper order entry hidden、stock live disabled display、CFD hidden。
- Guard 要求 route/auth/cache partition、crypto tab regression、Decision Lease risk regression、
  static/route/crypto hashes、live-order/secret-slot/pre-gate-contact denials 保持 required。
- Guard 禁止 env/fs/network/IBKR SDK/clock/thread/process/order/Bybit runtime tokens
  與 secret material access tokens。

驗證：

- New structure guard py_compile：PASS。
- Focused structure guard pytest：`6 passed`。
- Focused GUI lane contract acceptance：`9 passed`。
- Full `cargo test -p openclaw_types`：PASS。

PM 邊界不變：此 checkpoint 不新增 GUI write surface，不新增 POST route，不信任 client lane
state，不授權 localStorage/query/hidden-field，不建立 order/secret widget，不呼叫 IBKR，不導入
IBKR SDK，不讀/建 secret，不啟動 connector runtime，不送 paper order，不授權 tiny-live/live 或
任何 Bybit behavior change。

## 124. 2026-07-01 PM session source checkpoint：Stock/ETF Read-Only Probe Request Source Static Guard

本 checkpoint 為 `stock_etf_ibkr_readonly_probe_request.rs` 補上 source-only structure guard。
這不是 IBKR contact、不是 read probe execution、不是 connector runtime、不是 secret access、
不是 order route、不是 evidence writer；只把 future first-contact 前的 readonly probe request
envelope source invariant 機器化。

已完成：

- 新增 `tests/structure/test_stock_etf_ibkr_readonly_probe_request_source_static.py`。
- Guard 鎖住 `stock_etf_ibkr_readonly_probe_request.rs` 低於 800 行 governance cap。
- Guard 要求 exact `stock_etf_ibkr_readonly_probe_request_v1` contract id、read probe kind 列表、
  request fields、verdict/blocker surface、helper surface 保持在 source 中。
- Guard 要求 default request fail-closed：CryptoPerp/Bybit/LiveReservedDenied、Client Portal API、
  transfer/account-write operation、Denied authority、empty lineage hashes、all side-effect flags false。
- Guard 要求 accepted fixture 保留 StockEtfCash/IBKR/ReadOnly、ConnectionHealthRead、HealthRead、
  ReadOnly authority、effect=false、request/probe ids、Phase2 gate、non-Bybit allowlist、secret-slot、
  API topology、session attestation、redaction/rate-limit/audit policy hashes。
- Guard 要求 probe kind 到 NonBybitApiAction/BrokerOperation mapping 保持完整，並要求 API action
  必須 classify 為 read-allowed/external-gate-required/no paper-order gates。
- Guard 要求 boundary flags 保留 no IBKR contact、no connector runtime、no secret serialization、
  no order/paper order、no DB apply、no evidence clock、no Bybit path reuse、no live/tiny-live、no
  margin/short/options/CFD/account-write/entitlement/client-portal/Python broker write。
- Guard 禁止 env/fs/network/IBKR SDK/clock/thread/process/order/Bybit runtime tokens
  與 secret material access tokens。

驗證：

- New structure guard py_compile：PASS。
- Focused structure guard pytest：`8 passed`。
- Focused read-only probe request acceptance：`6 passed`。
- Full `cargo test -p openclaw_types`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動 connector
runtime、不執行 read probe、不送 order、不提交 paper order、不做 DB apply、不啟動 evidence
writer/clock、不授權 tiny-live/live 或任何 Bybit behavior change。

## 125. 2026-07-01 PM session source checkpoint：Stock/ETF Read-Only Probe Result Import Request Source Static Guard

本 checkpoint 為 `stock_etf_ibkr_readonly_probe_result_import_request.rs` 補上 source-only
structure guard。這不是 IBKR contact、不是 read probe execution、不是 result import
execution、不是 connector runtime、不是 secret access、不是 evidence/scorecard writer、不是
DB apply、不是 order route；只把 future sanitized readonly probe result import request envelope
的 source invariant 機器化。

已完成：

- 新增 `tests/structure/test_stock_etf_ibkr_readonly_probe_result_import_request_source_static.py`。
- Guard 鎖住 `stock_etf_ibkr_readonly_probe_result_import_request.rs` 低於 800 行 governance cap。
- Guard 要求 exact `stock_etf_ibkr_readonly_probe_result_import_request_v1` contract id、request
  fields、verdict/blocker surface、helper surface、read probe kind 列表保持在 source 中。
- Guard 要求 default request fail-closed：CryptoPerp/Bybit/LiveReservedDenied、Client Portal API、
  transfer/account-write operation、Denied authority、empty lineage hashes、duplicate/stale flags
  false、all side-effect flags false。
- Guard 要求 accepted fixture 保留 StockEtfCash/IBKR/ReadOnly、ConnectionHealthRead、HealthRead、
  ReadOnly authority、effect=false、result-import/request/probe ids、readonly probe request、
  session attestation、non-Bybit allowlist、redaction/audit policy、payload/raw/redacted/source
  artifact hashes、as-of/import-request timestamps、idempotency key。
- Guard 要求 probe kind 到 NonBybitApiAction/BrokerOperation mapping 保持完整，並要求 API action
  必須 classify 為 read-allowed/external-gate-required/no paper-order gates。
- Guard 要求 common lineage 保留 request/session/allowlist/redaction/audit/result payload/raw/
  redacted/source artifact hashes、as-of <= import-request、idempotency、duplicate/stale denial。
- Guard 要求 kind-specific downstream lineage 保留 health snapshot、account cash ledger、
  market-data provenance、instrument identity、paper lifecycle event log 的 contract/hash checks。
- Guard 要求 boundary flags 保留 no IBKR contact、no connector runtime、no secret serialization、
  no result import、no evidence/scorecard writer、no DB apply、no order/paper order、no Bybit path
  reuse、no live/tiny-live、no margin/short/options/CFD/account-write/entitlement/client-portal/
  Python broker write。
- Guard 禁止 env/fs/network/IBKR SDK/clock/thread/process/order/Bybit runtime tokens
  與 secret material access tokens。

驗證：

- New structure guard py_compile：PASS。
- Focused structure guard pytest：`10 passed`。
- Focused read-only probe result import request acceptance：`6 passed`。
- Full `cargo test -p openclaw_types`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動 connector
runtime、不執行 read probe、不做 result import execution、不啟動 collector、不啟動 market-data
ingestion、不啟動 DQ writer、不送 order、不提交 paper order、不做 DB apply、不啟動 evidence/
scorecard writer、不啟動 evidence clock、不授權 tiny-live/live 或任何 Bybit behavior change。

## 126. 2026-07-01 PM session source checkpoint：Stock/ETF Instrument Identity Source Static Guard

本 checkpoint 為 `stock_etf_instrument_identity.rs` 補上 source-only structure guard。這不是
IBKR contract-details call、不是 market-data subscription、不是 connector runtime、不是 secret
access、不是 paper order、不是 evidence/scorecard writer、不是 DB apply；只把 point-in-time
Stock/ETF cash instrument identity source invariant 機器化。

已完成：

- 新增 `tests/structure/test_stock_etf_instrument_identity_source_static.py`。
- Guard 鎖住 `stock_etf_instrument_identity.rs` 低於 800 行 governance cap。
- Guard 要求 exact `instrument_identity_contract_v1` contract id、identity fields、listing
  venue/currency/tradability/PRIIPs enums、verdict/blocker surface、cash venue helper、symbol helper
  保持在 source 中。
- Guard 要求 default identity fail-closed：CryptoPerp/Bybit、CryptoPerp instrument kind、empty
  symbol、UnknownDenied venue/currency/tradability/PRIIPs、missing PIT/as-of/hash lineage、Bybit live
  unchanged false、IBKR live/margin/options-CFD denial flags false。
- Guard 要求 accepted fixture 保留 StockEtfCash/IBKR、Stock、`AMD`、XNAS listing/primary exchange、
  USD、Tradable、PRIIPs NotRequired、fractional policy recorded、PIT as-of、market calendar、
  broker contract-details、identity、corporate-action-adjustment、source artifact hashes。
- Guard 要求 validation matrix 保留 contract/version/lane/broker checks、Stock/ETF/Cash-only kind
  allowlist、symbol validator、venue/primary exchange denial、cash/non-cash venue separation、USD-only、
  tradable-only、PRIIPs missing/unknown denial、fractional/PIT/market calendar/hash lineage checks。
- Guard 要求 boundary flags 保留 Bybit live protected、IBKR live denied、margin/short denied、
  options/CFD denied、no IBKR contact、no secret serialization。
- Guard 禁止 env/fs/network/IBKR SDK/clock/thread/process/order/Bybit runtime tokens
  與 secret material access tokens。

驗證：

- New structure guard py_compile：PASS。
- Focused structure guard pytest：`7 passed`。
- Focused instrument identity acceptance：`8 passed`。
- Full `cargo test -p openclaw_types`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動 connector
runtime、不做 contract-details call、不訂閱 market data、不送 order、不提交 paper order、不做
DB apply、不啟動 evidence/scorecard writer、不啟動 evidence clock、不授權 tiny-live/live 或任何
Bybit behavior change。

## 127. 2026-07-01 PM session source checkpoint：Stock/ETF PIT Universe Source Static Guard

本 checkpoint 為 `stock_etf_pit_universe.rs` 補上 source-only structure guard。這不是 IBKR
contact、不是 connector runtime、不是 market-data collection、不是 evidence clock、不是
scorecard writer、不是 DB apply、不是 paper order；只把 point-in-time universe membership
source invariant 機器化。

已完成：

- 新增 `tests/structure/test_stock_etf_pit_universe_source_static.py`。
- Guard 鎖住 `stock_etf_pit_universe.rs` 低於 800 行 governance cap。
- Guard 要求 exact `stock_etf_pit_universe_contract_v1` contract id、universe fields、
  constituent fields、verdict/blocker surface、constituent validator、required-hash validator、
  identifier/symbol helpers 保持在 source 中。
- Guard 要求 default universe fail-closed：CryptoPerp/Bybit、empty universe id/version/hash、
  missing PIT/effective window、zero counts、empty constituents、empty rule/screen/policy hashes、
  not frozen for evidence clock、survivorship controls missing、Bybit live unchanged false、IBKR live
  denied false。
- Guard 要求 accepted fixture 保留 StockEtfCash/IBKR、`US_LARGE_100_V1`、version
  `US_LARGE_100_V1_20260301`、PIT/effective window、3 constituents AMD/MSFT/SPY、max 100、
  inclusion/exclusion/liquidity/tradability/PRIIPs/delisted/corporate-action/market-calendar/source
  hashes、frozen/survivorship controls、Bybit live protection、IBKR live denial。
- Guard 要求 validation matrix 保留 contract/version/lane/broker checks、identifier/hash checks、
  PIT/effective-window/count/max-count/broad-universe checks、constituent validation、required hashes、
  frozen/survivorship/boundary checks。
- Guard 要求 constituent checks 保留 symbol/kind allowlist、instrument identity hash、unknown/cash
  venue denial、USD/tradable/PRIIPs checks、included-only and no exclusion reason for included names。
- Guard 禁止 env/fs/network/IBKR SDK/clock/thread/process/order/Bybit runtime tokens
  與 secret material access tokens。

驗證：

- New structure guard py_compile：PASS。
- Focused structure guard pytest：`8 passed`。
- Focused PIT universe acceptance：`7 passed`。
- Full `cargo test -p openclaw_types`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動 connector
runtime、不收集 market data、不啟動 evidence clock、不啟動 scorecard writer、不做 DB apply、
不執行 read probe、不做 result import execution、不送 order、不提交 paper order、不授權
tiny-live/live 或任何 Bybit behavior change。

## 128. 2026-07-01 PM session source checkpoint：Stock/ETF Reference Data Sources Source Static Guard

本 checkpoint 為 `stock_etf_reference_data_sources.rs` 補上 source-only structure guard。這不是
IBKR contact、不是 connector runtime、不是 reference/market-data ingest、不是 evidence clock、
不是 scorecard writer、不是 DB migration/apply、不是 live/tiny-live authorization；只把
corporate-action、FX、fee、tax/FTT source-as-of records 的 source invariant 機器化。

已完成：

- 新增 `tests/structure/test_stock_etf_reference_data_sources_source_static.py`。
- Guard 鎖住 `stock_etf_reference_data_sources.rs` 低於 800 行 governance cap。
- Guard 要求 exact `stock_etf_reference_data_sources_v1` contract id、reference source fields、
  corporate-action/FX/fee-tax validators、verdict/blocker surface 保持在 source 中。
- Guard 要求 default reference sources fail-closed：CryptoPerp/Bybit/LiveReservedDenied、not frozen
  for evidence clock、empty corporate-action/FX/fee source names、zero as-of values、UnknownDenied
  currencies、empty hashes、Bybit live unchanged false、no contact/runtime/secret flags、live/tiny-live
  authorized true as blocker。
- Guard 要求 accepted fixture 保留 StockEtfCash/IBKR/Paper、frozen for evidence clock、
  corporate-action source/as-of/raw/adjustment/policy/dividend hashes、USD/USD FX source/as-of/
  snapshot/drag-model hashes、IBKR paper fee source/as-of/commission/regulatory/tax/withholding/source
  hashes、Bybit live protection、no contact/runtime/secret/live-tiny authority。
- Guard 要求 validation matrix 保留 contract/version/lane/broker checks、ReadOnly/Paper/Shadow-only
  environment allowlist、freeze requirement、corporate-action/FX/fee-tax validator calls、source
  artifact hash、Bybit/contact/runtime/secret/live-tiny blockers。
- Guard 禁止 env/fs/network/IBKR SDK/clock/thread/process/order/Bybit runtime tokens
  與 secret material access tokens。

驗證：

- New structure guard py_compile：PASS。
- Focused structure guard pytest：`7 passed`。
- Focused reference data sources acceptance：`6 passed`。
- Full `cargo test -p openclaw_types`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動 connector
runtime、不做 reference/market-data ingest、不啟動 evidence clock、不啟動 scorecard writer、
不做 DB migration/apply、不執行 read probe、不做 result import execution、不送 order、不提交
paper order、不授權 tiny-live/live 或任何 Bybit behavior change。

## 129. 2026-07-01 PM session source checkpoint：Stock/ETF Strategy Hypothesis Source Static Guard

本 checkpoint 為 `stock_etf_strategy_hypothesis.rs` 補上 source-only structure guard。這不是
IBKR contact、不是 connector runtime、不是 market-data collection、不是 scorecard writer、
不是 profitability claim、不是 live/tiny-live authorization、不是 paper order；只把
pre-registered paper-shadow strategy hypothesis source invariant 機器化。

已完成：

- 新增 `tests/structure/test_stock_etf_strategy_hypothesis_source_static.py`。
- Guard 鎖住 `stock_etf_strategy_hypothesis.rs` 低於 800 行 governance cap。
- Guard 要求 exact `stock_etf_strategy_hypothesis_contract_v1` contract id、hypothesis fields、
  family/timeframe/scope enums、verdict/blocker surface、hash validator、limit/control validator、
  identifier helper 保持在 source 中。
- Guard 要求 default hypothesis fail-closed：CryptoPerp/Bybit、empty id/version、UnknownDenied
  family/timeframe/scope、empty universe/cost/rule/design/preregistration hashes、zero holding/
  turnover/constituent/sample controls、all bias/metric/paper-shadow controls false、no profitability/
  live authority claim、Bybit live unchanged false、IBKR live denied false。
- Guard 要求 accepted fixture 保留 StockEtfCash/IBKR、daily momentum large-100 hypothesis id/version、
  DailyMomentum/Daily/StockAndEtf、universe/PIT universe/benchmark/cost/entry/exit/risk/feature/
  data-source/statistical-design/preregistration hashes、holding >= 3 days、turnover 5000 bps、
  max constituents 100、independent observations 50、bias/multiple-testing/benchmark/cost-after/
  no-options-CFD-margin-short controls、paper-shadow-only、no profitability/live authority。
- Guard 要求 validation matrix 保留 contract/version/lane/broker/id/version checks、allowed
  family/timeframe/scope、all hash checks、holding/turnover/constituent/sample limits、bias/metric/
  forbidden-instrument/paper-shadow controls、no premature profitability/live authority/contact/secret。
- Guard 禁止 env/fs/network/IBKR SDK/clock/thread/process/order/Bybit runtime tokens
  與 secret material access tokens。

驗證：

- New structure guard py_compile：PASS。
- Focused structure guard pytest：`9 passed`。
- Focused strategy hypothesis acceptance：`7 passed`。
- Full `cargo test -p openclaw_types`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動 connector
runtime、不收集 market data、不啟動 evidence clock、不啟動 scorecard writer、不宣稱 profitability、
不做 DB apply、不執行 read probe、不做 result import execution、不送 order、不提交 paper order、
不授權 tiny-live/live 或任何 Bybit behavior change。

## 130. 2026-07-01 PM session source checkpoint：Stock/ETF Phase3 Evidence Source Static Guard

本 checkpoint 為 `stock_etf_phase3_evidence.rs` 與
`stock_etf_phase3_evidence/market_data.rs` 補上 source-only structure guard。這不是
market-data ingest、不是 evidence clock runtime、不是 DQ/evidence/scorecard writer、不是
DB apply、不是 IBKR contact、不是 connector runtime；只把 Phase3 collector/DQ/evidence-clock/
provenance/frozen-input source invariant 機器化。

已完成：

- 新增 `tests/structure/test_stock_etf_phase3_evidence_source_static.py`。
- Guard 鎖住 parent 低於 800 行、market-data child 低於 500 行 governance cap。
- Guard 要求 parent 保留 collector run、DQ manifest、evidence clock、verdict/blocker surface、
  market-data child module/re-export、Phase3 contract ids、5-day green minimum。
- Guard 要求 child 保留 market-data provenance、adjustment marker、frozen evidence inputs、
  source fixtures、validation helpers、hash checks。
- Guard 要求 collector run 保留 PIT universe、market-data provenance、reference data sources、
  storage-capacity lineage hashes、gap/DQ/replay/source hashes、5 green sessions、no ingestion/
  writer/DB/secret/live flags。
- Guard 要求 DQ manifest 保留 named market-data provenance lineage、shape-vs-quality split、
  10000 bps coverage/completeness、latency/provenance/scorecard-regeneration gates、no DQ writer/
  evidence clock/scorecard/DB/runtime flags。
- Guard 要求 evidence clock day 保留 collector/DQ/source/market-data/scorecard-input lineage、
  frozen inputs、DQ manifest、connector/shadow 5-day gates、PassDay/QuarantinedDay/WindowComplete
  status rules、no checker runtime/write/DB/live authority。
- Guard 要求 market-data provenance 保留 source vendor、entitlement tier、raw payload hash、
  timestamps、adjustment marker、corporate action hash、symbol、instrument identity、calendar session、
  source artifact、Bybit protection、no contact/runtime/secret/live authority。
- Guard 要求 frozen inputs 保留 universe/benchmark/cost/strategy/reference/divergence hashes、
  corporate-action/FX/fee as-of、GUI evidence view、scorecard regeneration readiness。
- Guard 禁止 env/fs/network/IBKR SDK/clock/thread/process/order/Bybit runtime tokens
  與 secret material access tokens。

驗證：

- New structure guard py_compile：PASS。
- Focused structure guard pytest：`10 passed`。
- Focused Phase3 evidence acceptance：`19 passed`。
- Full `cargo test -p openclaw_types`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動 connector
runtime、不做 market-data ingest、不啟動 collector runtime、不啟動 DQ writer、不啟動 evidence
clock runtime、不啟動 evidence/scorecard writer、不做 DB apply、不執行 read probe、不做 result
import execution、不送 order、不提交 paper order、不授權 tiny-live/live 或任何 Bybit behavior change。

## 131. 2026-07-01 PM session source checkpoint：Stock/ETF Paper Order Fixture Source Static Guard

本 checkpoint 為 `stock_etf_paper_order_request/fixtures.rs` 補上 source-only structure guard。
這不是 paper order route、不是 paper submit/cancel/replace execution、不是 IBKR contact、不是
connector runtime、不是 secret access；只把 accepted preview/submit/cancel/replace fixture source
invariant 機器化。

已完成：

- 新增 `tests/structure/test_stock_etf_paper_order_request_fixtures_source_static.py`。
- Guard 鎖住 `stock_etf_paper_order_request/fixtures.rs` 低於 400 行 governance cap。
- Guard 要求 fixture module 保留 accepted preview/submit/cancel/replace fixture functions、paper
  order request contract id、lane-scoped IPC methods、broker operations、authority scopes、
  instrument/order/price/TIF enums。
- Guard 要求 preview fixture 保留 StockEtfCash/IBKR/Paper、PreviewPaperOrder、PaperOrderSubmit、
  ReadOnly authority、SPY ETF buy limit DAY shape、risk/instrument/cost/PIT/source hashes、effect
  fields absent via default。
- Guard 要求 submit fixture 保留 SubmitPaperOrder、PaperRehearsal、effect_capable=true、
  session/scoped/decision/guardian/lifecycle/broker-registry/audit lineage、local order id、
  idempotency key、preview-only source hashes cleared。
- Guard 要求 cancel fixture 保留 CancelPaperOrder、PaperOrderCancel、PaperRehearsal、broker order id
  and cancel reason。
- Guard 要求 replace fixture 保留 ReplacePaperOrder、PaperOrderReplace、replacement idempotency/
  quantity/limit-price/TIF/reason fields while clearing original submit/cancel fields。
- Guard 禁止 env/fs/network/IBKR SDK/clock/thread/process/order/Bybit runtime tokens
  與 secret material access tokens。

驗證：

- New structure guard py_compile：PASS。
- Focused structure guard pytest：`6 passed`。
- Focused paper order request acceptance：`8 passed`。
- Full `cargo test -p openclaw_types`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動 connector
runtime、不做 paper order route、不執行 paper submit/cancel/replace、不做 market-data ingest、
不啟動 evidence clock、不啟動 scorecard writer、不做 DB apply、不授權 tiny-live/live 或任何
Bybit behavior change。

## 132. 2026-07-01 PM session source checkpoint：Stock/ETF IPC Scorecard Summary Source Static Guard

本 checkpoint 為
`rust/openclaw_engine/src/ipc_server/handlers/stock_etf/status_summaries/scorecard.rs`
補上 source-only structure guard。這不是 IPC runtime change、不是 scorecard writer、
不是 DB apply、不是 evidence-clock runtime、不是 IBKR contact、不是 connector runtime、
不是 paper order execution；只把 display-only scorecard status child module 的 source invariant
機器化。

已完成：

- 新增 `tests/structure/test_stock_etf_ipc_scorecard_summary_source_static.py`。
- Guard 鎖住 scorecard summary child module 低於 500 行 governance cap。
- Guard 要求 `scorecard_status_summary(phase2)` 保留 display-only entry point。
- Guard 要求 default construction/validation 保留 `StockEtfScorecardInputBundleV1`、
  `StockEtfScorecardDerivationV1`、`StockEtfScorecardVerdictV1`。
- Guard 要求 blocked Phase3 scorecard status posture 保留：no scorecard writer、no DB apply、
  no evidence clock、no paper-shadow window complete、no IBKR call、no secret touch、no order route、
  no Bybit IPC reuse、no live/tiny-live authority。
- Guard 要求 input bundle lineage 保留 read-only probe result import、market-data provenance、
  reference data、risk policy、atomic fact input、source commit、paper/shadow separation 與 side-effect
  denial flags。
- Guard 要求 derivation/verdict lineage 保留 scorecard input、evidence clock、DQ、formula、
  preregistration、benchmark/cost/strategy/reference/reconciliation hashes、PnL/cost/statistical
  fields、quality labels、QC/MIT/QA review hashes、sealed/default-blocked posture。
- Guard 禁止 env/fs/network/IBKR SDK/clock/thread/process/order/Bybit runtime tokens
  與 secret material access tokens。

驗證：

- New structure guard py_compile：PASS。
- Focused structure guard pytest：`5 passed`。
- Focused Rust IPC scorecard status acceptance：PASS。
- Existing Rust IPC handler split guard：PASS。
- Full `cargo test -p openclaw_engine`：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動 connector
runtime、不做 IPC runtime side effect、不啟動 scorecard writer、不啟動 evidence clock、不做 DB
apply、不做 paper order route、不執行 paper submit/cancel/replace、不授權 tiny-live/live 或任何
Bybit behavior change。

## 133. 2026-07-01 PM session source checkpoint：Stock/ETF Read-Only Probe Request Template Source Static Guard

本 checkpoint 為 `settings/broker/stock_etf_ibkr_readonly_probe_request.template.toml`
補上 source-only structure guard。這不是 read-only probe execution、不是 IBKR contact、
不是 connector runtime、不是 SDK import、不是 secret access、不是 DB apply、不是 evidence
clock runtime、不是 paper order route；只把 read-only probe request default-blocked template
的 source invariant 機器化。

已完成：

- 新增 `tests/structure/test_stock_etf_readonly_probe_request_template_source_static.py`。
- Guard 鎖住 template 低於 80 行 governance cap。
- Guard 要求 default denied posture 保留 empty contract id、`source_version = 0`、
  `crypto_perp`/`bybit`、`live_reserved_denied`、client-portal denied action、
  transfer/account-write denied operation、denied authority、`effect_capable = false`。
- Guard 要求 request/probe id 與 Phase2 gate、allowlist、secret-slot、topology、session、
  redaction、rate-limit、audit、source/raw/redacted artifact lineage 全部保持 empty。
- Guard 要求所有 side-effect/authority flags 保持 false：IBKR contact、connector runtime、
  secret serialization、order route、paper submit、DB apply、evidence clock、Bybit path reuse、
  live/tiny-live、margin/short/options/CFD、account write、entitlement purchase、client portal use、
  Python direct broker write。
- Guard 禁止 runtime/network/IBKR SDK/order/Bybit client tokens 與 secret material keys。

驗證：

- New structure guard py_compile：PASS。
- Focused structure guard pytest：`5 passed`。
- Focused read-only probe request acceptance：`6 passed`。
- Full `cargo test -p openclaw_types`：PASS。
- Docs PM trace tests：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動 connector
runtime、不執行 read-only probe、不做 result import、不啟動 evidence/scorecard writer、不啟動
evidence clock、不做 DB apply、不做 paper order route、不授權 tiny-live/live 或任何 Bybit
behavior change。

## 134. 2026-07-01 PM session source checkpoint：Stock/ETF Settings Template Coverage Static Guard

本 checkpoint 新增 IBKR/Stock-ETF settings/template coverage meta guard。這不是 settings
mutation、不是 runtime enablement、不是 IBKR contact、不是 secret access、不是 connector
runtime、不是 paper order route；只把 #133 發現的 read-only probe request template coverage gap
變成可持續的 source-static invariant。

已完成：

- 新增 `tests/structure/test_stock_etf_settings_template_coverage_static.py`。
- Guard 動態掃描 `settings/asset_lanes`、`settings/broker`、
  `settings/risk_control_rules` 底下檔名包含 `ibkr`、`stock_etf` 或 legacy
  `stock_market_data` alias 的 TOML。
- Guard 要求 scan scope 包含 `stock_market_data_provenance.template.toml` 這個非
  `stock_etf_*` 命名例外。
- Guard 要求 scan scope 不包含 unrelated Bybit runtime configs：
  `risk_config_demo.toml`、`risk_config_live.toml`、`risk_config_paper.toml`。
- Guard 要求每個 matching settings/template 檔都被 Rust acceptance tests、structure tests 或
  Stock/ETF control-api tests 直接引用；未引用即 fail。

驗證：

- New structure guard py_compile：PASS。
- Focused structure guard pytest：`3 passed`。
- Docs PM trace tests：PASS。

PM 邊界不變：此 checkpoint 不改 settings values、不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、
不啟動 connector runtime、不執行 read-only probe、不做 result import、不啟動 evidence/
scorecard writer、不啟動 evidence clock、不做 DB apply、不做 paper order route、不授權
tiny-live/live 或任何 Bybit behavior change。

## 135. 2026-07-01 PM session source checkpoint：Stock/ETF Python/GUI Surface Coverage Static Guard

本 checkpoint 新增 Stock/ETF/IBKR Python 與 static GUI candidate-scope guard。這不是
FastAPI behavior change、不是 GUI behavior change、不是 connector runtime wiring、不是 IBKR
contact、不是 secret access、不是 paper order route；只把現有 no-write/no-runtime/no-background
guards 的檔案選取面機器化。

已完成：

- 新增
  `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_surface_coverage_static_guard.py`。
- Guard 要求 `candidate_stock_etf_control_api_python_files()` 包含所有目前
  `app/*stock_etf*.py` 與 `app/*ibkr*.py` control-api modules。
- Guard 要求 `candidate_stock_etf_ibkr_python_files()` 包含所有目前
  `program_code/broker_connectors/ibkr_connector/**/*.py` connector skeleton files。
- Guard 要求 `candidate_stock_etf_static_gui_files()` 包含所有目前
  `app/static/tab-stock-etf*` GUI files。
- Guard 要求 candidate scope 不包含 Bybit runtime fragments：REST client、private WS、
  order manager/router、bounded-probe active-order 等。

驗證：

- New control-api guard py_compile：PASS。
- Focused new guard pytest：`4 passed`。
- Full Stock/ETF control-api pytest：PASS。
- Docs PM trace tests：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動 connector
runtime、不執行 read-only probe、不做 result import、不啟動 evidence/scorecard writer、不做 DB
apply、不做 paper order route、不授權 tiny-live/live 或任何 Bybit behavior change。

## 136. 2026-07-01 PM session source checkpoint：Stock/ETF Rust Source Coverage Static Guard

本 checkpoint 新增 IBKR/Stock-ETF Rust source coverage meta guard。這不是 Rust behavior
change、不是 IPC runtime change、不是 IBKR contact、不是 secret access、不是 connector
runtime、不是 paper order route；只把 Rust contract 與 Stock/ETF IPC handler source 覆蓋面
機器化。

已完成：

- 新增 `tests/structure/test_stock_etf_rust_source_coverage_static.py`。
- Guard 動態掃描 `rust/openclaw_types/src` 底下檔名/路徑包含 `ibkr` 或
  `stock_etf` 的 Rust source。
- Guard 動態掃描 `rust/openclaw_engine/src/ipc_server/handlers/stock_etf.rs` 與
  `handlers/stock_etf/` 底下所有 child modules。
- Guard 要求 nested child modules 仍在 scope：paper-order fixtures/validation、Phase3
  market-data、scorecard input components/bundle、precontact、request/status summaries、
  scorecard summary。
- Guard 要求 Bybit runtime modules 不在 scope：REST client、order manager、
  bounded-probe active-order。
- Guard 要求每個 matching Rust source 檔都被 structure tests、Rust acceptance tests、
  Rust engine IPC tests 或 Stock/ETF control-api tests 直接引用；未引用即 fail。

驗證：

- New structure guard py_compile：PASS。
- Focused new guard pytest：`3 passed`。
- Focused Stock/ETF/IBKR source-static structure subset：PASS。
- Docs PM trace tests：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動 connector
runtime、不執行 read-only probe、不做 result import、不啟動 evidence/scorecard writer、不做 DB
apply、不做 paper order route、不授權 tiny-live/live 或任何 Bybit behavior change。

## 137. 2026-07-01 PM session source checkpoint：IBKR Connector README Source Boundary Guard

本 checkpoint 為 inert IBKR connector skeleton README 補上 source-only posture guard。這不是
connector behavior change、不是 endpoint change、不是 IBKR contact、不是 secret access、
不是 connector runtime、不是 paper order route；只把 connector package 文檔邊界納入測試，
避免 source-only skeleton 被描述成 runtime-ready 或 order-capable。

已完成：

- 在 `test_stock_etf_ibkr_connector_skeleton.py` 新增
  `test_ibkr_connector_readme_preserves_source_only_boundary()`。
- Guard 要求 `program_code/broker_connectors/ibkr_connector/README.md` 明確保留
  `It is not a runtime IBKR connector.`。
- Guard 要求 README 的 allowed scope 維持 typed blocked readiness payloads、non-secret loopback
  endpoint descriptors、display-only previews、static fixtures。
- Guard 要求 README 的 denied scope 保留 IBKR SDK imports、socket/HTTP contact、secret/env
  credential fallback、broker write methods、paper order routing、fill-import side effects、
  DB writes、tiny-live、live。
- Guard 禁止 README 出現 runtime-ready、live-ready、paper-order-ready 或 direct broker write
  method support claims。

驗證：

- Connector skeleton test py_compile：PASS。
- Focused connector skeleton pytest：`10 passed`。
- Docs PM trace tests：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動 connector
runtime、不執行 read-only probe、不做 result import、不做 DB apply、不做 paper order route、
不授權 tiny-live/live 或任何 Bybit behavior change。

## 138. 2026-07-01 PM session source checkpoint：Stock/ETF Phase0 Spec Artifact Coverage Static Guard

本 checkpoint 新增 Phase0 spec artifact coverage meta guard。這不是 runtime behavior change、
不是 IBKR contact、不是 connector runtime、不是 secret access、不是 DB migration apply、
不是 paper order route；只把 `docs/execution_plan/specs` 下 IBKR/Stock-ETF source artifacts
的入口完整性、測試直接引用與 launch trace 同步機器化。

已完成：

- 新增 `tests/structure/test_stock_etf_phase0_spec_artifact_coverage_static.py`。
- Guard 動態掃描 `docs/execution_plan/specs` 中檔名包含 `stock_etf` 或 `ibkr` 的 source
  artifacts，並要求目前 scope 精確等於：
  `2026-06-29--stock_etf_cash_phase0_named_contract_packet.manifest.json`、
  `2026-06-29--stock_etf_cash_phase0_named_contract_packet.md`、
  `2026-06-29--stock_etf_db_evidence_ddl_v1.source_only.sql`。
- Guard 要求上述每個 artifact 都被 structure tests、Rust acceptance tests 或 Stock/ETF
  control-api tests 直接引用；未引用即 fail。
- Guard 要求本主開發安排與 Operator 摘要都列出上述每個 artifact；launch trace
  未同步即 fail。
- Guard 鎖住 manifest JSON 的 `stock_etf_cash` / `ibkr` / `paper_shadow_only`、
  loopback-only IB Gateway baseline、paper port 4002、no prior IBKR call、global denials
  與 phase unlock fail-closed strings。
- Guard 鎖住 named contract packet 的 no-runtime-authority denial list。
- Guard 鎖住 DB evidence SQL 的 SOURCE-ONLY posture，並要求不得被複製到 `sql/migrations`。

驗證：

- New structure guard py_compile：PASS。
- Focused new guard pytest：`6 passed`。
- Focused Phase0/source-static pytest subset：`31 passed`。
- Rust Phase0 manifest acceptance：`6 passed`。
- Rust release packet acceptance：`8 passed`。
- Rust DB evidence DDL acceptance：`10 passed`。
- Docs PM trace tests：PASS。
- Diff check：PASS。

PM 邊界不變：此 checkpoint 不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動 connector
runtime、不執行 read-only probe、不做 result import、不啟動 evidence/scorecard writer、不做 DB
apply、不做 paper order route、不授權 tiny-live/live 或任何 Bybit behavior change。

## 139. 2026-07-01 PM session source checkpoint：Stock/ETF ADR/AMD Authority Coverage Static Guard

本 checkpoint 新增 ADR/AMD authority artifact coverage meta guard。這不是 ADR/AMD content
change、不是 runtime behavior change、不是 IBKR contact、不是 connector runtime、不是 secret
access、不是 DB migration apply、不是 paper order route；只把最高層授權文件的 source
邊界、測試直接引用與 launch trace 同步機器化。

已完成：

- 新增 `tests/structure/test_stock_etf_authority_artifact_coverage_static.py`。
- Guard 動態掃描 Stock/ETF authority artifacts，並要求目前 scope 精確等於：
  `docs/adr/0048-ibkr-stock-etf-paper-shadow-lane.md`、
  `docs/governance_dev/amendments/2026-06-29--AMD-2026-06-29-01-ibkr-stock-etf-paper-shadow-lane.md`。
- Guard 要求上述兩個 authority artifacts 都被 structure tests、Rust acceptance tests 或
  Stock/ETF control-api tests 直接引用；未引用即 fail。
- Guard 要求本主開發安排與 Operator 摘要都列出上述完整 authority artifact paths；launch
  trace 未同步即 fail。
- Guard 鎖住 ADR-0048 的 Bybit-only active live execution venue、IBKR read-only/paper/shadow
  research scope、closed lane/broker/environment taxonomy，以及 IBKR live/tiny-live/margin/
  short/options/CFD/transfer/GUI/Python/Bybit-paper-reuse denied paths。
- Guard 鎖住 AMD-2026-06-29-01 的 paper/shadow amendment boundary、readonly/paper secret slots、
  denied live slot、Rust authority、inert connector skeleton posture，以及 tiny-live eligibility
  discussion-only boundary。

驗證：

- New structure guard py_compile：PASS。
- Focused new guard pytest：`7 passed`。
- Focused ADR/AMD + Phase0/release source-static subset：`29 passed`。
- Docs PM trace tests：PASS。
- Diff check：PASS。

PM 邊界不變：此 checkpoint 不改 ADR/AMD 正文、不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、
不啟動 connector runtime、不執行 read-only probe、不做 result import、不做 DB apply、不做 paper
order route、不授權 tiny-live/live 或任何 Bybit behavior change。

## 140. 2026-07-01 PM session source checkpoint：Stock/ETF Stable Boundary Docs Static Guard

本 checkpoint 新增 stable boundary docs guard。這不是 stable-doc wording change、不是 runtime
behavior change、不是 IBKR contact、不是 connector runtime、不是 secret access、不是 DB
migration apply、不是 paper order route；只把 AMD-2026-06-29-01 要求同步的長期入口文件
邊界機器化，避免 agent 從入口文件誤讀 IBKR paper/shadow 例外為 active live 或 runtime-ready。

已完成：

- 新增 `tests/structure/test_stock_etf_stable_boundary_docs_static.py`。
- Guard 要求 `CLAUDE.md`、`.codex/MEMORY.md`、`README.md`、
  `docs/_indexes/document_index.md`、`docs/_indexes/initiative_index.md`、
  `docs/governance_dev/SPECIFICATION_REGISTER.md` 都存在。
- Guard 鎖住 CLAUDE / Codex memory 的 Bybit-only active live execution boundary，以及
  ADR-0048 + AMD-2026-06-29-01 下 IBKR read-only / paper / shadow research exception。
- Guard 鎖住 README 的 operator-facing 文案：IBKR `stock_etf_cash` 是隔離 research lane，
  不是 live/tiny-live 或 durable-alpha promotion lane。
- Guard 鎖住 document / initiative index 對 ADR-0048、AMD-2026-06-29-01、Phase0 packet、
  Phase2 real secret/topology evidence + immutable PASS artifact blocker 的 routing。
- Guard 鎖住 governance specification register 的 active amendment/ADR rows、Bybit-only live
  execution wording、IBKR read-only/paper/shadow limits，以及 live/tiny-live/margin/short/options/
  CFD/transfer/account-write denials。
- Guard 禁止 stable docs 宣稱 IBKR live approval、connector runtime approval、paper-order route
  approval 或 first-contact allowance。

驗證：

- New structure guard py_compile：PASS。
- Focused new guard pytest：`3 passed`。
- Focused stable-boundary + ADR/AMD + Phase0 spec artifact subset：`16 passed`。
- Docs PM trace tests：PASS。
- Diff check：PASS。

PM 邊界不變：此 checkpoint 不改 stable docs 正文、不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、
不啟動 connector runtime、不執行 read-only probe、不做 result import、不做 DB apply、不做 paper
order route、不授權 tiny-live/live 或任何 Bybit behavior change。

## 141. 2026-07-01 PM session source checkpoint：Stock/ETF Index Reference Integrity Static Guard

本 checkpoint 新增 document / initiative index reference integrity guard。這不是 index wording
change、不是 runtime behavior change、不是 IBKR contact、不是 connector runtime、不是 secret
access、不是 DB migration apply、不是 paper order route；只把 IBKR/Stock-ETF launch trace 的
索引鏈接完整性機器化，避免 index 指向不存在的 PM/Operator report、ADR/AMD、spec 或 settings
artifact。

已完成：

- 新增 `tests/structure/test_stock_etf_index_reference_integrity_static.py`。
- Guard 掃描 `docs/_indexes/document_index.md` 與 `docs/_indexes/initiative_index.md` 中
  IBKR/Stock-ETF 相關 code spans。
- Guard 只把 path-like code spans 視為檔案，並有意排除 `/api/v1/stock-etf/readiness`、
  `first_ibkr_contact_allowed=false`、`stock_etf.*` 這類 endpoint / flag / method pattern。
- Guard 要求 `docs/`、`settings/`、ADR、governance amendment、execution plan、CCAgent workspace
  prefix 下的 path-like references 都 resolve 到現有 repo file。
- Guard 要求 index 仍保留 ADR-0048、AMD-2026-06-29-01、Phase0 packet/manifest、DB DDL
  source draft、主開發安排、PM round3 report、Operator round3 summary 等 launch trace references。

驗證：

- New structure guard py_compile：PASS。
- Focused new guard pytest：`3 passed`。
- Focused index + stable-boundary + ADR/AMD + Phase0 spec artifact subset：`19 passed`。
- Docs PM trace tests：PASS。
- Diff check：PASS。

PM 邊界不變：此 checkpoint 不改 index 正文、不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、
不啟動 connector runtime、不執行 read-only probe、不做 result import、不做 DB apply、不做 paper
order route、不授權 tiny-live/live 或任何 Bybit behavior change。

## 142. 2026-07-01 PM session source checkpoint：Stock/ETF Dynamic Checkpoint Trace Guard

本 checkpoint 將 Stock/ETF checkpoint trace title guard 從手寫長清單改成由主開發安排自動抽取。
這不是 runtime behavior change、不是 IBKR contact、不是 connector runtime、不是 secret access、
不是 DB migration apply、不是 paper order route；只確保主開發安排新增 PM session checkpoint 時，
Operator round3 summary 也必須保留可搜尋 trace，避免後續交接時 PM plan 與 Operator summary 脫節。

已完成：

- 更新 `tests/structure/test_docs_readme_index_static.py`。
- Guard 解析本文件所有 `PM session ... checkpoint` 標題，並要求 dynamic title list 維持目前
  Stock/ETF checkpoint history 覆蓋規模。
- Guard 要求每個解析出的 checkpoint title 都出現在 Operator round3 summary。
- 移除舊的手寫 `required_titles` tuple，後續新增 checkpoint 不再需要額外手動更新測試清單。
- Operator round3 summary 補上三個歷史 exact trace alias：
  `Stock/ETF GUI split`、`Paper Lifecycle State-Machine Contract Hardening`、
  `Paper Status Lifecycle Surface Hardening`。

驗證：

- Dynamic docs trace guard py_compile：PASS。
- Dynamic docs trace pytest：`2 passed, 5 deselected`。
- Full docs README/index structure pytest：known pre-existing docs README index drift remains
  (4 failures outside the Stock/ETF trace guard)。
- Diff check：PASS。

PM 邊界不變：此 checkpoint 不改 production code、不新增 endpoint/IPC method、不呼叫 IBKR、
不導入 IBKR SDK、不讀/建 secret、不啟動 connector runtime、不執行 read-only probe、不做
result import、不做 DB/evidence writer、不做 paper order route、不做 Linux runtime sync/restart、
不授權 tiny-live/live 或任何 Bybit behavior change。

## 143. 2026-07-01 PM session source checkpoint：Stock/ETF Paper Order Validation Source Static Guard

本 checkpoint 為 `stock_etf_paper_order_request/validation.rs` 補上專用 source-only structure
guard。這不是 Rust production behavior change、不是 IBKR contact、不是 connector runtime、
不是 secret access、不是 DB/evidence writer、不是 paper order route；只把 paper order request
validation 子模組的 fail-closed contract 機器化，避免 preview/submit/cancel/replace 的 authority、
effect、hash、field-separation 邏輯被後續改弱。

已完成：

- 新增 `tests/structure/test_stock_etf_paper_order_request_validation_source_static.py`。
- Guard 要求 validation 子模組維持 520 行 governance cap 與現有 helper/function surface。
- Guard 鎖住 top-level contract/source/lane/broker/paper-only/live-denial/boundary flag/request
  method dispatch checks。
- Guard 鎖住 method-specific surface mapping：preview 必須保持 ReadOnly + non-effect-capable；
  submit/cancel/replace 必須保持 PaperRehearsal + effect-capable。
- Guard 鎖住 preview/submit/cancel/replace 的 field separation、order shape、symbol/side、
  quantity、limit/market price、time-in-force、preview hash 與 effect hash gates。
- Guard 禁止 validation 子模組出現 runtime、secret material、order client 或 Bybit client tokens。

驗證：

- New validation guard py_compile：PASS。
- Focused new guard pytest：`6 passed`。
- Focused paper-order request validation/parent/fixtures/split subset：`20 passed`。
- Dynamic docs trace pytest：`2 passed, 5 deselected`；parsed checkpoint titles `130`，
  missing `[]`。
- Diff check：PASS。

PM 邊界不變：此 checkpoint 不改 Rust production code、不新增 endpoint/IPC method、不呼叫 IBKR、
不導入 IBKR SDK、不讀/建 secret、不啟動 connector runtime、不執行 read-only probe、不做
result import、不做 DB/evidence writer、不做 paper order/cancel/replace route、不做 Linux runtime
sync/restart、不授權 tiny-live/live 或任何 Bybit behavior change。

## 144. 2026-07-01 PM session source checkpoint：Stock/ETF Paper Order Acceptance Authority Gate Hardening

本 checkpoint 補強 `stock_etf_paper_order_request_acceptance.rs` 的 Rust acceptance coverage。這是
test-only，不是 Rust production behavior change、不是 IPC/endpoint change、不是 IBKR contact、
不是 connector runtime、不是 secret access、不是 DB/evidence writer、不是 paper order route；
只把 paper order request 的 authority/effect/hash gates 變成行為型 regression tests。

已完成：

- 新增 request-method surface mismatch acceptance：preview/submit/cancel/replace 若 operation、
  authority_scope 或 effect_capable 與 method contract 不一致，必須產生對應 blocker。
- 新增 effect-capable submit request acceptance：缺 session attestation、scoped authorization、
  decision lease、Guardian state、lifecycle contract、broker capability registry 或 audit event 時
  必須 fail closed。
- 新增 preview pollution acceptance：read-only preview envelope 若帶 effect/lifecycle、
  broker-order、cancel 或 replace 欄位，必須以 `PreviewEffectFieldPresent` block。

驗證：

- Targeted Rust acceptance：`cargo test -p openclaw_types --test stock_etf_paper_order_request_acceptance`
  passed `11 passed`。
- Targeted rustfmt：`rustfmt rust/openclaw_types/tests/stock_etf_paper_order_request_acceptance.rs`
  PASS。
- Full `cargo fmt -p openclaw_types -- --check`：known pre-existing formatting drift remains in
  `rust/openclaw_types/src/risk.rs` outside this checkpoint。
- Dynamic docs trace pytest：`2 passed, 5 deselected`；parsed checkpoint titles `131`，
  missing `[]`。
- Diff check：PASS。

PM 邊界不變：此 checkpoint 不改 Rust production code、不新增 endpoint/IPC method、不呼叫 IBKR、
不導入 IBKR SDK、不讀/建 secret、不啟動 connector runtime、不執行 read-only probe、不做
result import、不做 DB/evidence writer、不做 paper order/cancel/replace route、不做 Linux runtime
sync/restart、不授權 tiny-live/live 或任何 Bybit behavior change。

## 145. 2026-07-01 PM session source checkpoint：Stock/ETF Openclaw Types Format Gate Hygiene

本 checkpoint 清掉先前阻擋 `openclaw_types` package-level format gate 的既有 drift。這不是
IBKR behavior change、不是 Bybit behavior change、不是 runtime/deploy action；只把
`rust/openclaw_types/src/risk.rs` 做機械 rustfmt，讓後續 Stock/ETF Rust checkpoint 可以重新使用
`cargo fmt -p openclaw_types -- --check` 作為 package-level gate，而不必只依賴 file-scoped
rustfmt。

已完成：

- 執行 `rustfmt rust/openclaw_types/src/risk.rs`。
- diff 只包含一個 `return Err(...)` expression formatting 與兩個 test vector literal formatting。
- 解除 #144 當時記錄的 `rust/openclaw_types/src/risk.rs` pre-existing formatting drift。

驗證：

- `cargo fmt -p openclaw_types -- --check`：PASS。
- `cargo test -p openclaw_types risk --lib`：`13 passed`。
- Full `cargo test -p openclaw_types`：PASS。
- Dynamic docs trace pytest：`2 passed, 5 deselected`；parsed checkpoint titles `132`，
  missing `[]`。
- Diff check：PASS。

PM 邊界不變：此 checkpoint 不改 trading logic、不改 risk semantics、不新增 endpoint/IPC method、
不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動 connector runtime、不執行 read-only
probe、不做 result import、不做 DB/evidence writer、不做 paper order route、不做 Linux runtime
sync/restart、不授權 tiny-live/live 或任何 Bybit behavior change。

## 146. 2026-07-01 PM session source checkpoint：Stock/ETF Docs README Index Gate Restoration

本 checkpoint 修復 full docs README/index structure gate 的既有 drift。這不是 runtime behavior
change、不是 IBKR contact、不是 connector runtime、不是 secret access、不是 DB/evidence writer、
不是 paper order route；只把 `docs/README.md` 的穩定入口索引補回測試要求的可審計狀態，讓
Stock/ETF checkpoint trace guard 可以和完整 docs index gate 一起綠。

已完成：

- 更新 `docs/README.md`，新增 `Static Guard Index`。
- 補回 `docs/agents/` 穩定入口，包含 `agents/domain.md`、`agents/issue-tracker.md`、
  `agents/triage-labels.md`。
- 補回 helper script 索引入口 `../helper_scripts/SCRIPT_INDEX.md`。
- 補回 `CCAgentWorkSpace/` 19 個 Agent / role directories 的穩定描述，並明確列出
  `CCAgentWorkSpace/MIT/`、`CCAgentWorkSpace/BB/`、`CCAgentWorkSpace/Operator/`。
- 補回 `docs/archive/` top-level Markdown 檔名索引，避免 archive path drift 讓 docs README
  structure guard 失真。

驗證：

- Full docs README/index structure pytest：`7 passed`。
- Dynamic docs trace pytest：PASS；主計畫與 Operator summary 保持 checkpoint title coverage。
- Diff check：PASS。

PM 邊界不變：此 checkpoint 不改 production code、不改 trading logic、不新增 endpoint/IPC method、
不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動 connector runtime、不執行 read-only
probe、不做 result import、不做 DB/evidence writer、不做 paper order route、不做 Linux runtime
sync/restart、不授權 tiny-live/live 或任何 Bybit behavior change。

## 147. 2026-07-01 PM session source checkpoint：Stock/ETF Broker Capability Paper Fill Import Gate Hardening

本 checkpoint 補強 broker capability registry 對 `PaperOrderFillImport` 的 test-only/source-static
coverage。這不是 Rust production behavior change、不是 IBKR contact、不是 connector runtime、
不是 secret access、不是 DB/evidence writer、不是 fill import、不是 paper order route；只確保
paper fill import 仍是 ReadOnly source artifact import request，不能被錯升級成 paper-write /
Decision Lease / Guardian / order-like authority。

已完成：

- 在 `stock_etf_broker_capability_registry_acceptance.rs` 新增
  `paper_fill_import_row_is_readonly_and_requires_session_lifecycle_gate`。
- Acceptance 鎖住 `PaperOrderFillImport` row 的 `AuthorityScope::ReadOnly`、`typed_denial_reason=None`、
  `rust_owned=false`、`audit_event_required=true`、`source_artifact_hash_required=true`。
- Acceptance 鎖住 required gates 必須包含 `IBKR_SESSION_ATTESTATION_CONTRACT_ID` 與
  `IBKR_PAPER_ORDER_LIFECYCLE_CONTRACT_ID`，並對 wrong scope / missing gates / rust ownership /
  audit/source-hash regressions 產生 blockers。
- 在 `test_stock_etf_broker_capability_registry_source_static.py` 新增 source block parser，直接鎖
  `Op::PaperOrderFillImport => ExpectedCapability` block，禁止混入 `PaperRehearsal`、
  scoped authorization、Decision Lease 或 Guardian gate。

驗證：

- Targeted rustfmt check：PASS。
- Broker capability source static pytest：`6 passed`。
- Broker capability Rust acceptance：`11 passed`。
- Dynamic docs trace pytest：PASS；主計畫與 Operator summary 保持 checkpoint title coverage。
- Diff check：PASS。

PM 邊界不變：此 checkpoint 不改 Rust production code、不改 endpoint/IPC method、不呼叫 IBKR、
不導入 IBKR SDK、不讀/建 secret、不啟動 connector runtime、不執行 read-only probe、不做
fill import/result import、不做 DB/evidence writer、不做 paper order route、不做 Linux runtime
sync/restart、不授權 tiny-live/live 或任何 Bybit behavior change。

## 148. 2026-07-01 PM session source checkpoint：Stock/ETF Broker Operation Authority Taxonomy Guard

本 checkpoint 補強 `stock_etf_lane` 的 operation authority taxonomy coverage。這不是 Rust production
behavior change、不是 broker capability semantics change、不是 IBKR contact、不是 connector
runtime、不是 secret access、不是 DB/evidence writer、不是 paper order route；只把
`BrokerOperation::{is_read,is_paper_write,is_shadow,authority_scope}` 的分類契約用 acceptance 與
source-static guard 鎖住。

已完成：

- 在 `stock_etf_lane_acceptance.rs` 新增
  `broker_operation_authority_taxonomy_keeps_fill_import_readonly_and_orders_separate`。
- Acceptance 鎖住 `HealthRead`、`AccountSnapshotRead`、`MarketDataRead`、`ContractDetailsRead`、
  `PaperOrderFillImport`、`ScorecardDerive` 必須維持 `is_read=true` 與 `AuthorityScope::ReadOnly`。
- Acceptance 鎖住 `PaperOrderSubmit/Cancel/Replace` 必須維持 `is_paper_write=true` 與
  `AuthorityScope::PaperRehearsal`，且不能混入 read/shadow。
- Acceptance 鎖住 `ShadowSignalEmit/ShadowFillReconstruct` 必須維持 `AuthorityScope::ShadowOnly`；
  live/margin/options/transfer 類 operation 必須維持 `AuthorityScope::Denied`。
- 在 `test_stock_etf_lane_source_static.py` 新增 method body parser，直接檢查
  `is_read`、`is_paper_write`、`is_shadow` 與 `authority_scope` fallback order。

驗證：

- Targeted rustfmt check：PASS。
- Stock/ETF lane source static pytest：`5 passed`。
- Stock/ETF lane Rust acceptance：`10 passed`。
- Dynamic docs trace pytest：PASS；主計畫與 Operator summary 保持 checkpoint title coverage。
- Diff check：PASS。

PM 邊界不變：此 checkpoint 不改 Rust production code、不改 endpoint/IPC method、不呼叫 IBKR、
不導入 IBKR SDK、不讀/建 secret、不啟動 connector runtime、不執行 read-only probe、不做
fill import/result import、不做 DB/evidence writer、不做 paper order route、不做 Linux runtime
sync/restart、不授權 tiny-live/live 或任何 Bybit behavior change。

## 149. 2026-07-01 PM session source checkpoint：Stock/ETF Readonly Probe Result Import Cross-Wire Guard

本 checkpoint 補強 `stock_etf_ibkr_readonly_probe_result_import_request` 的 probe kind / API action /
BrokerOperation cross-wire coverage。這不是 Rust production behavior change、不是 IBKR contact、
不是 connector runtime、不是 secret access、不是 read-only probe execution、不是 result import、
不是 DB/evidence writer、不是 paper order route；只把 read-only result-import envelope 的 action /
operation mapping gate 變成行為型 regression test 與 source-static body guard。

已完成：

- 在 `stock_etf_ibkr_readonly_probe_result_import_request_acceptance.rs` 新增
  `result_import_request_rejects_probe_action_operation_cross_wire`。
- Acceptance 證明 `MarketDataSnapshot` 搭配 `AccountSummarySnapshotRead` 時必須產生
  `ProbeActionMismatch`。
- Acceptance 證明 `MarketDataSnapshot` 搭配 `AccountSnapshotRead` operation 時必須產生
  `OperationMismatch`。
- Acceptance 證明 result-import envelope 若混入 `PaperOrderSubmit` action，必須同時產生
  `ProbeActionMismatch` 與 `ApiActionNotReadAllowed`，且不可被 paper-order gate 誤接受。
- 在 `test_stock_etf_ibkr_readonly_probe_result_import_request_source_static.py` 新增 mapping function
  body parser，直接鎖住 `expected_api_action` / `expected_operation` 不包含 paper order 或 live order
  operation，並要求 open-paper-orders / paper-executions-commissions 只映射到 account snapshot read。

驗證：

- Targeted rustfmt check：PASS。
- Readonly probe result import source static pytest：`10 passed`。
- Readonly probe result import Rust acceptance：`7 passed`。
- Dynamic docs trace pytest：PASS；主計畫與 Operator summary 保持 checkpoint title coverage。
- Diff check：PASS。

PM 邊界不變：此 checkpoint 不改 Rust production code、不改 endpoint/IPC method、不呼叫 IBKR、
不導入 IBKR SDK、不讀/建 secret、不啟動 connector runtime、不執行 read-only probe、不做
result import、不做 DB/evidence writer、不做 paper order route、不做 Linux runtime sync/restart、
不授權 tiny-live/live 或任何 Bybit behavior change。

## 150. 2026-07-01 PM session source checkpoint：Stock/ETF Readonly Probe Request Cross-Wire Guard

本 checkpoint 補強 `stock_etf_ibkr_readonly_probe_request` 的 probe kind / API action /
BrokerOperation cross-wire coverage。這不是 Rust production behavior change、不是 IBKR contact、
不是 connector runtime、不是 secret access、不是 read-only probe execution、不是 DB/evidence
writer、不是 paper order route；只把 pre-contact read-only probe request envelope 的 action /
operation mapping gate 變成行為型 regression test 與 source-static body guard。

已完成：

- 在 `stock_etf_ibkr_readonly_probe_request_acceptance.rs` 新增
  `readonly_probe_request_rejects_probe_action_operation_cross_wire`。
- Acceptance 證明 `MarketDataSnapshot` 搭配錯誤 `AccountSummarySnapshotRead` action 時，必須產生
  `ProbeActionMismatch`，且不應誤報 `OperationMismatch` 或 read-allowlist failure。
- Acceptance 證明 `MarketDataSnapshot` 搭配錯誤 `AccountSnapshotRead` operation 時，必須產生
  `OperationMismatch`，且不應誤報 `ProbeActionMismatch` 或 read-allowlist failure。
- Acceptance 證明 request envelope 若混入 `PaperOrderSubmit` action，必須同時產生
  `ProbeActionMismatch` 與 `ApiActionNotReadAllowed`，且不可被 paper-order submitted flag
  誤當作已提交訂單處理。
- 在 `test_stock_etf_ibkr_readonly_probe_request_source_static.py` 新增 mapping function body parser，
  直接鎖住 `expected_api_action` / `expected_operation` 不包含 paper order 或 live order operation，
  並要求 open-paper-orders / paper-executions-commissions 只映射到 account snapshot read。

驗證：

- Targeted rustfmt check：PASS。
- Readonly probe request source static pytest：`8 passed`。
- Readonly probe request Rust acceptance：`7 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace pytest：PASS；主計畫與 Operator summary 保持 checkpoint title coverage。
- Diff check：PASS。

PM 邊界不變：此 checkpoint 不改 Rust production code、不改 endpoint/IPC method、不呼叫 IBKR、
不導入 IBKR SDK、不讀/建 secret、不啟動 connector runtime、不執行 read-only probe、不做
result import、不做 DB/evidence writer、不做 paper order route、不做 Linux runtime sync/restart、
不授權 tiny-live/live 或任何 Bybit behavior change。

## 151. 2026-07-01 PM session source checkpoint：Stock/ETF Shadow Signal Request Cross-Wire Guard

本 checkpoint 補強 `stock_etf_shadow_signal_request` 的 IPC method / BrokerOperation /
AuthorityScope cross-wire coverage。這不是 Rust production behavior change、不是 IBKR contact、
不是 connector runtime、不是 secret access、不是 shadow signal execution、不是 shadow fill
generation、不是 DB/evidence writer、不是 paper order route；只把 shadow-only request envelope 的
method / operation / scope gate 變成行為型 regression test 與 source-static guard。

已完成：

- 在 `stock_etf_shadow_signal_request_acceptance.rs` 新增
  `shadow_signal_request_rejects_method_operation_and_paper_write_cross_wire`。
- Acceptance 證明 shadow signal request 若混入 `ImportPaperFills` IPC method，必須產生
  `RequestMethodMismatch`，且不誤報 operation / scope / effect blocker。
- Acceptance 證明 `EvaluateShadowSignal` 若搭配 `PaperOrderSubmit` operation，必須產生
  `OperationMismatch`，且不誤報 method / scope / effect blocker。
- Acceptance 證明 request envelope 若混入 paper-submit method、paper-submit operation、
  `PaperRehearsal` scope 與 `effect_capable=true`，必須同時產生 method / operation / scope /
  effect blockers。
- 在 `test_stock_etf_shadow_signal_request_source_static.py` 新增 source-static cross-wire guard，
  禁止 paper order、fill import、readonly probe、Bybit-denied method 以及 paper/live operation
  混入 shadow signal source。

驗證：

- Targeted rustfmt check：PASS。
- Shadow signal request source static pytest：`7 passed`。
- Shadow signal request Rust acceptance：`6 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace pytest：PASS；主計畫與 Operator summary 保持 checkpoint title coverage。
- Diff check：PASS。

PM 邊界不變：此 checkpoint 不改 Rust production code、不改 endpoint/IPC method、不呼叫 IBKR、
不導入 IBKR SDK、不讀/建 secret、不啟動 connector runtime、不執行 shadow signal、不生成
shadow fill、不做 result import、不做 DB/evidence writer、不做 paper order route、不做 Linux
runtime sync/restart、不授權 tiny-live/live 或任何 Bybit behavior change。

## 152. 2026-07-01 PM session source checkpoint：Stock/ETF Paper Fill Import Request Cross-Wire Guard

本 checkpoint 補強 `stock_etf_paper_fill_import_request` 的 IPC method / BrokerOperation /
AuthorityScope cross-wire coverage。這不是 Rust production behavior change、不是 IBKR contact、
不是 connector runtime、不是 secret access、不是 fill import execution、不是 DB/evidence writer、
不是 paper order route；只把 paper fill import request envelope 的 method / operation / scope gate
變成行為型 regression test 與 source-static guard。

已完成：

- 在 `stock_etf_paper_fill_import_request_acceptance.rs` 新增
  `fill_import_request_rejects_method_operation_and_scope_cross_wire`。
- Acceptance 證明 fill-import request 若混入 `EvaluateShadowSignal` IPC method 但 operation 仍為
  `PaperOrderFillImport`，必須只產生 `RequestMethodMismatch`。
- Acceptance 證明 `ImportPaperFills` 若搭配 `PaperOrderSubmit` operation，必須只產生
  `OperationMismatch`。
- Acceptance 證明 request envelope 若混入 paper-submit method、paper-submit operation、
  `PaperRehearsal` scope 與 `effect_capable=true`，必須同時產生 method / operation / scope /
  effect blockers。
- Acceptance 證明 shadow-signal method / operation / scope 污染必須產生 method / operation /
  scope blockers，但不可誤報 effect blocker。
- 在 `test_stock_etf_paper_fill_import_request_source_static.py` 新增 source-static cross-wire guard，
  禁止 paper order、shadow signal、readonly probe、Bybit-denied method 以及 paper/live/shadow
  operation 混入 fill-import source。

驗證：

- Targeted rustfmt check：PASS。
- Paper fill import request source static pytest：`7 passed`。
- Paper fill import request Rust acceptance：`7 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace pytest：PASS；主計畫與 Operator summary 保持 checkpoint title coverage。
- Diff check：PASS。

PM 邊界不變：此 checkpoint 不改 Rust production code、不改 endpoint/IPC method、不呼叫 IBKR、
不導入 IBKR SDK、不讀/建 secret、不啟動 connector runtime、不執行 fill import、不做
result import、不做 DB/evidence writer、不做 paper order route、不做 Linux runtime sync/restart、
不授權 tiny-live/live 或任何 Bybit behavior change。

## 153. 2026-07-01 PM session source checkpoint：Stock/ETF Paper Shadow Reconciliation Cross-Wire Guard

本 checkpoint 補強 `stock_etf_paper_shadow_reconciliation` 的 scope / AuthorityScope /
effect-capable cross-wire coverage。這不是 Rust production behavior change、不是 IBKR contact、
不是 connector runtime、不是 secret access、不是 fill import execution、不是 shadow fill
generation、不是 reconciliation writer、不是 DB/evidence writer、不是 paper order route；只把
paper-shadow reconciliation evidence 的 `paper_shadow` / `ReadOnly` / non-effect posture 變成
行為型 regression test 與 source-static guard。

已完成：

- 在 `stock_etf_paper_shadow_reconciliation_acceptance.rs` 新增
  `reconciliation_rejects_scope_authority_and_effect_cross_wire`。
- Acceptance 證明 reconciliation scope 若混入 `shadow_signal`，必須只產生 `ScopeMismatch`。
- Acceptance 證明 authority 若混入 `ShadowOnly`，必須只產生 `AuthorityScopeMismatch`。
- Acceptance 證明 paper-write scope / `PaperRehearsal` / `effect_capable=true` 污染必須同時產生
  scope / authority / effect blockers。
- Acceptance 證明 shadow-only scope / authority 污染必須產生 scope / authority blockers，且不可誤報
  effect blocker。
- 在 `test_stock_etf_paper_shadow_reconciliation_source_static.py` 新增 source-static cross-wire guard，
  禁止 `PaperRehearsal`、`ShadowOnly`、`effect_capable=true`、paper-order scope、shadow-signal
  scope 混入 reconciliation source。

驗證：

- Targeted rustfmt check：PASS。
- Paper-shadow reconciliation source static pytest：`8 passed`。
- Paper-shadow reconciliation Rust acceptance：`6 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace pytest：PASS；主計畫與 Operator summary 保持 checkpoint title coverage。
- Diff check：PASS。

PM 邊界不變：此 checkpoint 不改 Rust production code、不改 endpoint/IPC method、不呼叫 IBKR、
不導入 IBKR SDK、不讀/建 secret、不啟動 connector runtime、不執行 fill import、不生成
shadow fill、不啟動 reconciliation writer、不做 result import、不做 DB/evidence writer、不做 paper
order route、不做 Linux runtime sync/restart、不授權 tiny-live/live 或任何 Bybit behavior change。

## 154. 2026-07-01 PM session source checkpoint：Stock/ETF Scorecard Input Bundle Cross-Wire Guard

本 checkpoint 補強 `stock_etf_scorecard_inputs` bundle 的 derived-only / paper-shadow separation /
live-fill / writer-runtime authority cross-wire coverage。這不是 Rust production behavior change、
不是 IBKR contact、不是 connector runtime、不是 secret access、不是 fill import execution、不是
scorecard derivation、不是 scorecard writer、不是 DB/evidence writer、不是 tiny-live/live gate；
只把 scorecard input bundle 的 source-only evidence posture 變成行為型 regression test 與
source-static guard。

已完成：

- 在 `stock_etf_scorecard_inputs_acceptance.rs` 新增
  `scorecard_bundle_rejects_derived_separation_live_and_writer_cross_wire_independently`。
- Acceptance 證明 `scorecard_is_derived_only=false` 只產生 `ScorecardNotDerivedOnly`，不誤報
  paper-shadow separation、live fill 或 writer blocker。
- Acceptance 證明 `paper_and_shadow_fills_separate=false` 只產生
  `PaperShadowFillSeparationMissing`，不誤報 derived-only、live fill 或 writer blocker。
- Acceptance 證明 `live_fill_claimed=true` 只產生 `LiveFillClaimed`，不誤報 derived-only、
  paper-shadow separation 或 writer blocker。
- Acceptance 證明 writer/runtime/tiny-live 污染必須產生 `ScorecardWriterStarted`、
  `DbApplyPerformed`、`EvidenceClockStarted`、`LiveOrTinyLiveAuthorized`，且不誤報 input
  evidence posture blockers。
- 在 `test_stock_etf_scorecard_inputs_source_static.py` 新增 bundle cross-wire guard，禁止
  live fill、IBKR contact、connector runtime、broker fill import、scorecard writer、DB apply、
  evidence clock、secret serialization、tiny-live/live authority 被 hardcoded 成 true。

驗證：

- Targeted rustfmt check：PASS。
- Scorecard inputs source static pytest：`8 passed`。
- Scorecard inputs Rust acceptance：`13 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace pytest：PASS；主計畫與 Operator summary 保持 checkpoint title coverage。
- Diff check：PASS。

PM 邊界不變：此 checkpoint 不改 Rust production code、不改 endpoint/IPC method、不呼叫 IBKR、
不導入 IBKR SDK、不讀/建 secret、不啟動 connector runtime、不執行 fill import、不做 scorecard
derivation、不啟動 scorecard writer、不做 DB/evidence writer、不做 paper order route、不做 Linux
runtime sync/restart、不授權 tiny-live/live 或任何 Bybit behavior change。

## 155. 2026-07-01 PM session source checkpoint：Stock/ETF Scorecard Derivation Cross-Wire Guard

本 checkpoint 補強 `stock_etf_scorecard_derivation` 的 atomic-facts-only / idempotent replay /
paper-shadow separation / Bybit unchanged / writer-runtime authority cross-wire coverage。這不是 Rust
production behavior change、不是 IBKR contact、不是 connector runtime、不是 secret access、不是
scorecard derivation execution、不是 reconciliation writer、不是 scorecard writer、不是
DB/evidence writer、不是 tiny-live/live gate；只把 scorecard derivation artifact 的 source-only、
idempotent、sealed posture 變成行為型 regression test 與 source-static guard。

已完成：

- 在 `stock_etf_scorecard_derivation_acceptance.rs` 新增
  `derivation_rejects_atomic_replay_separation_and_writer_cross_wire_independently`。
- Acceptance 證明 `derived_from_atomic_facts_only=false` 只產生
  `NotDerivedFromAtomicFactsOnly`，不誤報 replay、paper-shadow separation、Bybit unchanged 或 writer
  blocker。
- Acceptance 證明 `idempotent_replay_proven=false` 只產生
  `IdempotentReplayNotProven`，不誤報 atomic-facts、paper-shadow separation、Bybit unchanged 或 writer
  blocker。
- Acceptance 證明 `paper_and_shadow_fills_separate=false` 只產生
  `PaperShadowFillSeparationMissing`，不誤報 atomic-facts、replay、Bybit unchanged 或 writer blocker。
- Acceptance 證明 `bybit_live_execution_unchanged=false` 只產生
  `BybitLiveExecutionNotProtected`，不誤報 atomic-facts、replay、paper-shadow separation 或 writer
  blocker。
- Acceptance 證明 IBKR contact / connector runtime / broker fill import / shadow fill /
  reconciliation writer / scorecard writer / DB apply / evidence clock / secret serialization /
  tiny-live/live authority 污染必須產生各自 blocker，且不誤報 derivation evidence posture blockers。
- 在 `test_stock_etf_scorecard_derivation_source_static.py` 新增 fixture cross-wire guard，禁止
  IBKR contact、connector runtime、broker fill import、shadow fill、reconciliation writer、
  scorecard writer、DB apply、evidence clock、secret serialization、tiny-live/live authority 被
  hardcoded 成 true，並鎖住 default fail-closed posture。

驗證：

- Targeted rustfmt check：PASS。
- Scorecard derivation source static pytest：`7 passed`。
- Scorecard derivation Rust acceptance：`6 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace pytest：PASS；主計畫與 Operator summary 保持 checkpoint title coverage。
- Diff check：PASS。

PM 邊界不變：此 checkpoint 不改 Rust production code、不改 endpoint/IPC method、不呼叫 IBKR、
不導入 IBKR SDK、不讀/建 secret、不啟動 connector runtime、不執行 scorecard derivation、不啟動
reconciliation writer、不啟動 scorecard writer、不做 DB/evidence writer、不做 paper order route、
不做 Linux runtime sync/restart、不授權 tiny-live/live 或任何 Bybit behavior change。

## 156. 2026-07-01 PM session source checkpoint：Stock/ETF Scorecard Verdict Cross-Wire Guard

本 checkpoint 補強 `stock_etf_scorecard_verdict` 的 derived-only / paper-shadow separation /
live-fill / Bybit unchanged / writer-runtime authority cross-wire coverage。這不是 Rust production
behavior change、不是 IBKR contact、不是 connector runtime、不是 secret access、不是 scorecard
writer、不是 DB/evidence writer、不是 tiny-live/live gate；只把 scorecard verdict artifact 的
source-only、paper/shadow separated、no-live-claim posture 變成行為型 regression test 與
source-static guard。

已完成：

- 在 `stock_etf_scorecard_verdict_acceptance.rs` 新增
  `scorecard_verdict_rejects_evidence_live_bybit_and_writer_cross_wire_independently`。
- Acceptance 證明 `scorecard_is_derived_only=false` 只產生 `ScorecardNotDerivedOnly`，不誤報
  paper-shadow separation、live fill、Bybit unchanged 或 writer blocker。
- Acceptance 證明 `paper_and_shadow_fills_separate=false` 只產生
  `PaperShadowFillSeparationMissing`，不誤報 derived-only、live fill、Bybit unchanged 或 writer
  blocker。
- Acceptance 證明 `live_fill_claimed=true` 只產生 `LiveFillClaimed`，不誤報 derived-only、
  paper-shadow separation、Bybit unchanged 或 writer blocker。
- Acceptance 證明 `bybit_live_execution_unchanged=false` 只產生
  `BybitLiveExecutionNotProtected`，不誤報 derived-only、paper-shadow separation、live fill 或 writer
  blocker。
- Acceptance 證明 IBKR contact / connector runtime / broker fill import / scorecard writer /
  DB apply / evidence clock / secret serialization / tiny-live/live authority 污染必須產生各自 blocker，
  且不誤報 verdict evidence posture blockers。
- 在 `test_stock_etf_scorecard_verdict_source_static.py` 新增 fixture cross-wire guard，禁止
  live fill、IBKR contact、connector runtime、broker fill import、scorecard writer、DB apply、
  evidence clock、secret serialization、tiny-live/live authority 被 hardcoded 成 true，並鎖住 default
  fail-closed posture。

驗證：

- Targeted rustfmt check：PASS。
- Scorecard verdict source static pytest：`8 passed`。
- Scorecard verdict Rust acceptance：`9 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace pytest：PASS；主計畫與 Operator summary 保持 checkpoint title coverage。
- Diff check：PASS。

PM 邊界不變：此 checkpoint 不改 Rust production code、不改 endpoint/IPC method、不呼叫 IBKR、
不導入 IBKR SDK、不讀/建 secret、不啟動 connector runtime、不執行 scorecard writer、不做
DB/evidence writer、不做 paper order route、不做 Linux runtime sync/restart、不授權 tiny-live/live 或任何
Bybit behavior change。

## 157. 2026-07-01 PM session source checkpoint：Stock/ETF Tiny-Live Eligibility Decision Cross-Wire Guard

本 checkpoint 補強 `stock_etf_tiny_live_eligibility` 的 ADR-discussion-only decision matrix 與
secret/sealed posture cross-wire coverage。這不是 Rust production behavior change、不是 IBKR contact、
不是 connector runtime、不是 secret access、不是 tiny-live/live authorization、不是 DB/evidence
writer、不是 paper order route；只把未來 ADR 討論資格 artifact 的 no-live-authority posture 變成
行為型 regression test 與 source-static guard。

已完成：

- 在 `stock_etf_tiny_live_eligibility_acceptance.rs` 新增
  `tiny_live_eligibility_rejects_decision_and_secret_cross_wire_independently`。
- Acceptance 證明 `NotEligible` decision 只產生 `DecisionNotAdrDiscussionOnly`，不誤報 tiny-live、
  live、secret 或 sealed blockers。
- Acceptance 證明 `TinyLiveAuthorized` decision 只產生 `TinyLiveAuthorizationRequested`，不誤報
  NotEligible、live、secret 或 sealed blockers。
- Acceptance 證明 `LiveAuthorized` decision 只產生 `LiveAuthorizationRequested`，不誤報 NotEligible、
  tiny-live、secret 或 sealed blockers。
- Acceptance 證明 `secret_content_serialized=true` 只產生 `SecretContentSerialized`，不誤報 decision
  或 sealed blockers。
- Acceptance 證明 `sealed=false` 只產生 `NotSealed`，不誤報 decision 或 secret blockers。
- 在 `test_stock_etf_tiny_live_eligibility_source_static.py` 新增 fixture cross-wire guard，禁止
  `TinyLiveAuthorized`、`LiveAuthorized`、secret serialization、unsealed posture 被 hardcoded 到
  `adr_discussion_fixture()`，並鎖住 default fail-closed posture。

驗證：

- Targeted rustfmt check：PASS。
- Tiny-live eligibility source static pytest：`7 passed`。
- Tiny-live eligibility Rust acceptance：`8 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace pytest：PASS；主計畫與 Operator summary 保持 checkpoint title coverage。
- Diff check：PASS。

PM 邊界不變：此 checkpoint 不改 Rust production code、不改 endpoint/IPC method、不呼叫 IBKR、
不導入 IBKR SDK、不讀/建 secret、不啟動 connector runtime、不授權 tiny-live/live、不做
DB/evidence writer、不做 paper order route、不做 Linux runtime sync/restart、不改任何 Bybit behavior。

## 158. 2026-07-01 PM session source checkpoint：Stock/ETF Release Packet Authority Cross-Wire Guard

本 checkpoint 補強 `stock_etf_release_packet` 的 secret serialization / tiny-live/live authority /
release seal / paper-shadow window / engineering shakedown cross-wire coverage。這不是 Rust production
behavior change、不是 release execution、不是 IBKR contact、不是 connector runtime、不是 secret
access、不是 DB/evidence writer、不是 paper order route、不是 tiny-live/live authorization；只把
release packet artifact 的 no-secret、no-live-authority、sealed posture 變成行為型 regression test 與
source-static guard。

已完成：

- 在 `stock_etf_release_packet_acceptance.rs` 新增
  `release_packet_rejects_secret_authority_window_and_seal_cross_wire_independently`。
- Acceptance 證明 `secret_content_serialized=true` 只產生 `SecretContentSerialized`，不誤報
  live/tiny-live authority 或 seal blocker。
- Acceptance 證明 `ibkr_live_or_tiny_live_authorized=true` 只產生
  `LiveOrTinyLiveAuthorityPresent`，不誤報 secret 或 seal blocker。
- Acceptance 證明 `sealed=false` 只產生 `ReleasePacketNotSealed`，不誤報 secret 或 live/tiny-live
  authority blocker。
- Acceptance 證明 `paper_shadow_window_complete=false` 只產生 `PaperShadowWindowIncomplete`，不誤報
  secret、live/tiny-live authority 或 seal blocker。
- Acceptance 證明 `engineering_shakedown_complete=false` 只產生
  `EngineeringShakedownIncomplete`，不誤報 secret、live/tiny-live authority 或 seal blocker。
- 在 `test_stock_etf_release_packet_source_static.py` 新增 fixture cross-wire guard，禁止 incomplete
  paper-shadow window、incomplete engineering shakedown、secret serialization、live/tiny-live authority、
  unsealed posture 被 hardcoded 到 accepted fixture，並鎖住 default fail-closed posture。

驗證：

- Targeted rustfmt check：PASS。
- Release packet source static pytest：`8 passed`。
- Release packet Rust acceptance：`9 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace pytest：PASS；主計畫與 Operator summary 保持 checkpoint title coverage。
- Diff check：PASS。

PM 邊界不變：此 checkpoint 不改 Rust production code、不改 endpoint/IPC method、不呼叫 IBKR、
不導入 IBKR SDK、不讀/建 secret、不啟動 connector runtime、不執行 release、不做 DB/evidence
writer、不做 paper order route、不做 Linux runtime sync/restart、不授權 tiny-live/live 或任何 Bybit
behavior change。

## 159. 2026-07-01 PM session source checkpoint：Stock/ETF Strategy Hypothesis Authority Cross-Wire Guard

本 checkpoint 補強 `stock_etf_strategy_hypothesis` 的 pre-registration / paper-shadow only /
profitability claim / tiny-live/live authority / Bybit unchanged / IBKR live denial / secret
serialization cross-wire coverage。這不是 Rust production behavior change、不是 IBKR contact、不是
connector runtime、不是 secret access、不是 strategy execution、不是 scorecard writer、不是
DB/evidence writer、不是 paper order route、不是 tiny-live/live gate；只把 strategy hypothesis artifact
的 source-only、paper-shadow preregistration、no-profitability-claim、no-live-authority posture 變成
行為型 regression test 與 source-static guard。

已完成：

- 在 `stock_etf_strategy_hypothesis_acceptance.rs` 新增
  `strategy_hypothesis_rejects_authority_profitability_and_secret_cross_wire_independently`。
- Acceptance 證明 `paper_shadow_only=false` 只產生 `PaperShadowOnlyMissing`，不誤報 profitability、
  live/tiny-live authority、Bybit、IBKR live、IBKR contact 或 secret blockers。
- Acceptance 證明 `profitability_claimed=true` 只產生 `PrematureProfitabilityClaim`，不誤報
  paper-shadow、live/tiny-live authority、Bybit、IBKR live、IBKR contact 或 secret blockers。
- Acceptance 證明 `live_or_tiny_live_authority_claimed=true` 只產生
  `LiveOrTinyLiveAuthorityClaimed`，不誤報 paper-shadow、profitability、Bybit、IBKR live、IBKR
  contact 或 secret blockers。
- Acceptance 證明 `bybit_live_execution_unchanged=false` 只產生
  `BybitLiveExecutionNotProtected`，不誤報 paper-shadow、profitability、live/tiny-live authority、IBKR
  live、IBKR contact 或 secret blockers。
- Acceptance 證明 `ibkr_live_denied=false` 只產生 `IbkrLiveNotDenied`，不誤報 paper-shadow、
  profitability、live/tiny-live authority、Bybit、IBKR contact 或 secret blockers。
- Acceptance 證明 `ibkr_contact_performed=true` 只產生 `IbkrContactPerformed`，不誤報 paper-shadow、
  profitability、live/tiny-live authority、Bybit、IBKR live 或 secret blockers。
- Acceptance 證明 `secret_content_serialized=true` 只產生 `SecretContentSerialized`，不誤報
  paper-shadow、profitability、live/tiny-live authority、Bybit、IBKR live 或 IBKR contact blockers。
- 在 `test_stock_etf_strategy_hypothesis_source_static.py` 新增 accepted fixture body parser，禁止
  non-paper-shadow、profitability claim、live/tiny-live authority、Bybit changed、IBKR live not denied、
  IBKR contact、secret serialization 被 hardcoded 到 accepted fixture，並鎖住 default fail-closed
  posture。

驗證：

- Targeted rustfmt check：PASS。
- Strategy hypothesis source static pytest：`10 passed`。
- Strategy hypothesis Rust acceptance：`8 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace pytest：PASS；主計畫與 Operator summary 保持 checkpoint title coverage。
- Diff check：PASS。

PM 邊界不變：此 checkpoint 不改 Rust production code、不改 endpoint/IPC method、不呼叫 IBKR、
不導入 IBKR SDK、不讀/建 secret、不啟動 connector runtime、不執行 strategy、不做 scorecard writer、
不做 DB/evidence writer、不做 paper order route、不做 Linux runtime sync/restart、不授權 tiny-live/live
或任何 Bybit behavior change。

## 160. 2026-07-01 PM session source checkpoint：Stock/ETF Risk Policy Runtime Authority Cross-Wire Guard

本 checkpoint 補強 `stock_etf_risk_policy` 的 dormant paper/shadow risk posture、cash-only controls、
live-denial controls、Bybit unchanged、IBKR contact、connector runtime、secret serialization cross-wire
coverage。這不是 Rust production behavior change、不是 IBKR contact、不是 connector runtime、不是
secret access、不是 order execution、不是 risk runtime enablement、不是 DB/evidence writer、不是
paper order route、不是 tiny-live/live gate；只把 risk policy artifact 的 source-only、disabled、
shadow-only、cash-only、no-runtime-authority posture 變成行為型 regression test 與 source-static guard。

已完成：

- 在 `stock_etf_risk_policy_acceptance.rs` 新增
  `risk_policy_rejects_runtime_cash_and_authority_cross_wire_independently`。
- Acceptance 證明 `enabled=true` 只產生 `RuntimeEnablementClaimed`。
- Acceptance 證明 `shadow_only=false` 只產生 `ShadowOnlyPostureMissing`。
- Acceptance 證明 `environment=LiveReservedDenied` 只產生 `WrongEnvironment`。
- Acceptance 證明 `allow_margin=true`、`allow_short=true`、`allow_options=true`、`allow_cfd=true`、
  `allow_transfer=true`、`allow_live=true` 會各自只產生對應 cash-only / live-denial blocker。
- Acceptance 證明 `bybit_live_execution_unchanged=false` 只產生
  `BybitLiveExecutionNotProtected`。
- Acceptance 證明 `ibkr_contact_performed=true`、`connector_runtime_started=true`、
  `secret_content_serialized=true` 會各自只產生對應 IBKR contact、connector runtime、secret blocker。
- 在 `test_stock_etf_risk_policy_source_static.py` 新增 accepted fixture / source-config mapper body
  parser，禁止 runtime enabled、non-shadow、live environment、margin/short/options/CFD/transfer/live
  allowance、Bybit changed、IBKR contact、connector runtime、secret serialization 被 hardcoded 到
  accepted fixture 或 source-config mapper，並鎖住 default fail-closed posture。

驗證：

- Targeted rustfmt check：PASS。
- Risk policy source static pytest：`6 passed`。
- Risk policy Rust acceptance：`9 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace pytest：PASS；主計畫與 Operator summary 保持 checkpoint title coverage。
- Diff check：PASS。

PM 邊界不變：此 checkpoint 不改 Rust production code、不改 endpoint/IPC method、不呼叫 IBKR、
不導入 IBKR SDK、不讀/建 secret、不啟動 connector runtime、不啟用 risk runtime、不做 order execution、
不做 DB/evidence writer、不做 paper order route、不做 Linux runtime sync/restart、不授權 tiny-live/live
或任何 Bybit behavior change。

## 161. 2026-07-01 PM session source checkpoint：Stock/ETF Phase3 Collector Runtime Cross-Wire Guard

本 checkpoint 補強 `stock_etf_phase3_evidence` 中 `StockEtfCollectorRunV1` 的 green-session、
Bybit unchanged、IBKR contact、connector runtime、market-data ingestion、evidence writer、scorecard
writer、DB apply、secret serialization、tiny-live/live authority cross-wire coverage。這不是 Rust
production behavior change、不是 IBKR contact、不是 connector runtime、不是 market-data ingestion、
不是 evidence clock runtime、不是 writer execution、不是 DB apply、不是 paper order route、不是
tiny-live/live gate；只把 collector run artifact 的 source-only、no-runtime、no-writer、no-live-authority
posture 變成行為型 regression test 與 source-static guard。

已完成：

- 在 `stock_etf_phase3_evidence_acceptance.rs` 新增
  `collector_run_rejects_runtime_writer_secret_and_authority_cross_wire_independently`。
- Acceptance 證明 `completed_trading_sessions` 低於 required green sessions 只產生
  `CollectorCompletedSessionsMissing`。
- Acceptance 證明 `bybit_live_execution_unchanged=false` 只產生
  `BybitLiveExecutionNotProtected`。
- Acceptance 證明 `ibkr_contact_performed=true`、`connector_runtime_started=true`、
  `market_data_ingestion_started=true`、`evidence_writer_started=true`、`scorecard_writer_started=true`、
  `db_apply_performed=true`、`secret_content_serialized=true`、`live_or_tiny_live_authorized=true` 都會
  各自只產生單一對應 blocker。
- 在 `test_stock_etf_phase3_evidence_source_static.py` 新增 collector `source_fixture()` body parser，
  禁止 live environment、zero session counts、Bybit changed、IBKR contact、connector runtime、
  market-data ingestion、evidence writer、scorecard writer、DB apply、secret serialization、
  tiny-live/live authority 被 hardcoded 到 collector fixture，並鎖住 default fail-closed posture。

驗證：

- Targeted rustfmt check：PASS。
- Phase3 evidence source static pytest：`11 passed`。
- Phase3 evidence Rust acceptance：`20 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace pytest：PASS；主計畫與 Operator summary 保持 checkpoint title coverage。
- Diff check：PASS。

PM 邊界不變：此 checkpoint 不改 Rust production code、不改 endpoint/IPC method、不呼叫 IBKR、
不導入 IBKR SDK、不讀/建 secret、不啟動 connector runtime、不啟動 market-data ingestion、不啟動
evidence clock runtime、不做 writer execution、不做 DB/evidence writer、不做 paper order route、不做
Linux runtime sync/restart、不授權 tiny-live/live 或任何 Bybit behavior change。

## 162. 2026-07-01 PM session source checkpoint：Stock/ETF Phase3 DQ Manifest Runtime Cross-Wire Guard

本 checkpoint 補強 `stock_etf_phase3_evidence` 中 `StockEtfDailyDqManifestV1` 的 Bybit unchanged、
IBKR contact、connector runtime、market-data ingestion、DQ writer、evidence clock、scorecard writer、
DB apply、secret serialization、tiny-live/live authority cross-wire coverage。這不是 Rust production
behavior change、不是 IBKR contact、不是 connector runtime、不是 market-data ingestion、不是 DQ writer、
不是 evidence clock runtime、不是 scorecard writer、不是 DB apply、不是 paper order route、不是
tiny-live/live gate；只把 DQ manifest artifact 的 source-only、shape-vs-quality split、no-runtime、
no-writer、no-live-authority posture 變成行為型 regression test 與 source-static guard。

已完成：

- 在 `stock_etf_phase3_evidence_acceptance.rs` 新增
  `dq_manifest_rejects_runtime_writer_secret_and_authority_cross_wire_independently`。
- Acceptance 證明 `bybit_live_execution_unchanged=false` 只產生
  `BybitLiveExecutionNotProtected`。
- Acceptance 證明 `ibkr_contact_performed=true`、`connector_runtime_started=true`、
  `market_data_ingestion_started=true`、`dq_writer_started=true`、`evidence_clock_started=true`、
  `scorecard_writer_started=true`、`db_apply_performed=true`、`secret_content_serialized=true`、
  `live_or_tiny_live_authorized=true` 都會各自只產生單一對應 blocker。
- 在 `test_stock_etf_phase3_evidence_source_static.py` 新增 DQ manifest `pass_fixture()` body parser，
  禁止 live environment、Bybit changed、IBKR contact、connector runtime、market-data ingestion、
  DQ writer、evidence clock、scorecard writer、DB apply、secret serialization、tiny-live/live authority
  與 zero coverage 被 hardcoded 到 pass fixture，並鎖住 default fail-closed posture。

驗證：

- Targeted rustfmt check：PASS。
- Phase3 evidence source static pytest：`12 passed`。
- Phase3 evidence Rust acceptance：`21 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace pytest：PASS；主計畫與 Operator summary 保持 checkpoint title coverage。
- Diff check：PASS。

PM 邊界不變：此 checkpoint 不改 Rust production code、不改 endpoint/IPC method、不呼叫 IBKR、
不導入 IBKR SDK、不讀/建 secret、不啟動 connector runtime、不啟動 market-data ingestion、不啟動
DQ writer、不啟動 evidence clock runtime、不做 scorecard writer、不做 DB/evidence writer、不做 paper
order route、不做 Linux runtime sync/restart、不授權 tiny-live/live 或任何 Bybit behavior change。

## 163. 2026-07-01 PM session source checkpoint：Stock/ETF Phase3 Evidence Clock Runtime Cross-Wire Guard

本 checkpoint 補強 `stock_etf_phase3_evidence` 中 `StockEtfEvidenceClockDayV1` 的 Bybit unchanged、
IBKR contact、connector runtime、evidence clock runtime、scorecard writer、DB apply、secret
serialization、tiny-live/live authority、IBKR connector green dependency、shadow collector green
dependency cross-wire coverage。這不是 Rust production behavior change、不是 IBKR contact、不是
connector runtime、不是 evidence clock runtime、不是 scorecard writer、不是 DB apply、不是 paper order
route、不是 tiny-live/live gate；只把 evidence-clock day artifact 的 source-only、dependency-green、
no-runtime、no-writer、no-live-authority posture 變成行為型 regression test 與 source-static guard。

已完成：

- 在 `stock_etf_phase3_evidence_acceptance.rs` 新增
  `evidence_clock_day_rejects_runtime_writer_secret_and_authority_cross_wire_independently`。
- Acceptance 證明 `bybit_live_execution_unchanged=false` 只產生
  `BybitLiveExecutionNotProtected`。
- Acceptance 證明 `checker_contacted_ibkr=true`、`checker_started_connector_runtime=true`、
  `checker_started_evidence_clock=true`、`checker_wrote_scorecard=true`、`checker_applied_db=true`、
  `secret_content_serialized=true`、`live_or_tiny_live_authorized=true` 都會各自只產生單一對應 blocker。
- Acceptance 證明 `ibkr_readonly_paper_connector_green_5d=false` 只產生
  `IbkrConnectorNotGreenFiveDays`，`shadow_collector_green_5d=false` 只產生
  `ShadowCollectorNotGreenFiveDays`。
- 在 `test_stock_etf_phase3_evidence_source_static.py` 新增 evidence-clock `pass_day_fixture()` body
  parser，禁止 live environment、Bybit changed、IBKR contact、connector runtime、evidence clock runtime、
  scorecard writer、DB apply、secret serialization、tiny-live/live authority、missing green dependencies、
  `WindowComplete` status 被 hardcoded 到 pass-day fixture，並鎖住 default fail-closed posture。

驗證：

- Targeted rustfmt check：PASS。
- Phase3 evidence source static pytest：`13 passed`。
- Phase3 evidence Rust acceptance：`22 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace pytest：PASS；主計畫與 Operator summary 保持 checkpoint title coverage。
- Diff check：PASS。

PM 邊界不變：此 checkpoint 不改 Rust production code、不改 endpoint/IPC method、不呼叫 IBKR、
不導入 IBKR SDK、不讀/建 secret、不啟動 connector runtime、不啟動 evidence clock runtime、不做
scorecard writer、不做 DB/evidence writer、不做 paper order route、不做 Linux runtime sync/restart、
不授權 tiny-live/live 或任何 Bybit behavior change。

## 164. 2026-07-01 PM session source checkpoint：Stock/ETF Phase3 Market Data Provenance Runtime Cross-Wire Guard

本 checkpoint 補強 `stock_etf_phase3_evidence::market_data` 中 `StockMarketDataProvenanceV1` 的 live
environment denial、Bybit unchanged、IBKR contact、connector runtime、secret serialization、
tiny-live/live authority cross-wire coverage。這不是 Rust production behavior change、不是 IBKR contact、
不是 connector runtime、不是 market-data ingestion、不是 evidence writer、不是 DB apply、不是 paper
order route、不是 tiny-live/live gate；只把 market-data provenance artifact 的 source-only、paper/shadow
provenance、no-runtime、no-secret、no-live-authority posture 變成行為型 regression test 與 source-static
guard。

已完成：

- 在 `stock_etf_phase3_evidence_acceptance.rs` 新增
  `market_data_provenance_rejects_runtime_secret_and_authority_cross_wire_independently`。
- Acceptance 證明 `environment=LiveReservedDenied` 只產生
  `MarketDataProvenanceEnvironmentDenied`。
- Acceptance 證明 `bybit_live_execution_unchanged=false` 只產生
  `BybitLiveExecutionNotProtected`。
- Acceptance 證明 `ibkr_contact_performed=true`、`connector_runtime_started=true`、
  `secret_content_serialized=true`、`live_or_tiny_live_authorized=true` 都會各自只產生單一對應 blocker。
- 在 `test_stock_etf_phase3_evidence_source_static.py` 新增 market-data provenance `source_fixture()`
  body parser，禁止 live environment、Bybit changed、IBKR contact、connector runtime、secret
  serialization、tiny-live/live authority、unknown adjustment marker、zero timestamps 被 hardcoded 到
  source fixture，並鎖住 default fail-closed posture。

驗證：

- Targeted rustfmt check：PASS。
- Phase3 evidence source static pytest：`14 passed`。
- Phase3 evidence Rust acceptance：`23 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace pytest：PASS；主計畫與 Operator summary 保持 checkpoint title coverage。
- Diff check：PASS。

PM 邊界不變：此 checkpoint 不改 Rust production code、不改 endpoint/IPC method、不呼叫 IBKR、
不導入 IBKR SDK、不讀/建 secret、不啟動 connector runtime、不啟動 market-data ingestion、不做
evidence writer、不做 DB/evidence writer、不做 paper order route、不做 Linux runtime sync/restart、
不授權 tiny-live/live 或任何 Bybit behavior change。

## 165. 2026-07-01 PM session source checkpoint：Stock/ETF Phase3 Frozen Inputs Readiness Cross-Wire Guard

本 checkpoint 補強 `stock_etf_phase3_evidence::market_data` 中
`StockEtfFrozenEvidenceInputsV1` 的 frozen source hash、corporate-action/FX/fee as-of、
paper-shadow divergence threshold、GUI evidence view readiness、daily scorecard regeneration readiness
cross-wire coverage。這不是 Rust production behavior change、不是 IBKR contact、不是 connector
runtime、不是 market-data ingestion、不是 evidence writer、不是 scorecard writer、不是 DB apply、
不是 paper order route、不是 tiny-live/live gate；只把 frozen-input artifact 的 source-only、
readiness-only、no-runtime posture 變成行為型 regression test 與 source-static guard。

已完成：

- 在 `stock_etf_phase3_evidence_acceptance.rs` 新增
  `frozen_inputs_reject_source_readiness_cross_wire_independently`。
- Acceptance 證明 `universe_hash`、`benchmark_hash`、`cost_model_hash`、
  `strategy_hypothesis_hash`、`reference_data_sources_contract_hash`、
  `paper_shadow_divergence_threshold_hash` 缺失時，都會各自只產生單一對應 hash blocker。
- Acceptance 證明 `corporate_action_fx_fee_asof_ms=0` 只產生
  `CorporateActionFxFeeAsOfMissing`。
- Acceptance 證明 `gui_evidence_view_available=false` 只產生 `GuiEvidenceViewMissing`。
- Acceptance 證明 `daily_scorecard_regeneration_passed=false` 只產生
  `ScorecardRegenerationMissing`。
- 在 `test_stock_etf_phase3_evidence_source_static.py` 新增 frozen-input `source_fixture()` body
  parser，禁止 missing hash、zero as-of、missing GUI evidence view、missing scorecard regeneration
  被 hardcoded 到 source fixture，並鎖住 default fail-closed posture。

驗證：

- Targeted rustfmt check：PASS。
- Phase3 evidence source static pytest：`15 passed`。
- Phase3 evidence Rust acceptance：`24 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace pytest：PASS；主計畫與 Operator summary 保持 checkpoint title coverage。
- Diff check：PASS。

PM 邊界不變：此 checkpoint 不改 Rust production code、不改 endpoint/IPC method、不呼叫 IBKR、
不導入 IBKR SDK、不讀/建 secret、不啟動 connector runtime、不啟動 market-data ingestion、不做
evidence writer、不做 scorecard writer、不做 DB/evidence writer、不做 paper order route、不做
Linux runtime sync/restart、不授權 tiny-live/live 或任何 Bybit behavior change。

## 166. 2026-07-01 PM session source checkpoint：Stock/ETF Reference Data Sources Runtime Authority Cross-Wire Guard

本 checkpoint 補強 `stock_etf_reference_data_sources` 中 `StockEtfReferenceDataSourcesV1` 的
evidence-clock freeze、USD-only FX posture、Bybit unchanged、IBKR contact、connector runtime、secret
serialization、tiny-live/live authority cross-wire coverage。這不是 Rust production behavior change、
不是 IBKR contact、不是 connector runtime、不是 reference-data ingestion、不是 scorecard writer、
不是 DB apply、不是 paper order route、不是 tiny-live/live gate；只把 reference-data sources artifact
的 source-only、frozen-for-evidence、no-runtime、no-secret、no-live-authority posture 變成行為型
regression test 與 source-static guard。

已完成：

- 在 `stock_etf_reference_data_sources_acceptance.rs` 新增
  `reference_sources_reject_runtime_freeze_and_authority_cross_wire_independently`。
- Acceptance 證明 `environment=LiveReservedDenied` 只產生 `EnvironmentDenied`。
- Acceptance 證明 `frozen_for_evidence_clock=false` 只產生 `EvidenceClockFreezeMissing`。
- Acceptance 證明 `base_currency=UnknownDenied` 只產生 `CurrencyDenied`。
- Acceptance 證明 `bybit_live_execution_unchanged=false` 只產生
  `BybitLiveExecutionNotProtected`。
- Acceptance 證明 `ibkr_contact_performed=true`、`connector_runtime_started=true`、
  `secret_content_serialized=true`、`live_or_tiny_live_authorized=true` 都會各自只產生單一對應 blocker。
- 在 `test_stock_etf_reference_data_sources_source_static.py` 新增 accepted fixture body parser，
  禁止 live environment、missing evidence freeze、missing source names/as-of、unknown currencies、
  Bybit changed、IBKR contact、connector runtime、secret serialization、tiny-live/live authority 被
  hardcoded 到 accepted fixture，並鎖住 default fail-closed posture。

驗證：

- Targeted rustfmt check：PASS。
- Reference-data source static pytest：`8 passed`。
- Reference-data Rust acceptance：`7 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace pytest：PASS；主計畫與 Operator summary 保持 checkpoint title coverage。
- Diff check：PASS。

PM 邊界不變：此 checkpoint 不改 Rust production code、不改 endpoint/IPC method、不呼叫 IBKR、
不導入 IBKR SDK、不讀/建 secret、不啟動 connector runtime、不啟動 reference-data ingestion、不做
scorecard writer、不做 DB/evidence writer、不做 paper order route、不做 Linux runtime sync/restart、
不授權 tiny-live/live 或任何 Bybit behavior change。

## 167. 2026-07-01 PM session source checkpoint：Stock/ETF PIT Universe Source Authority Cross-Wire Guard

本 checkpoint 補強 `stock_etf_pit_universe` 中 `StockEtfPitUniverseV1` 的 evidence-clock freeze、
survivorship-bias controls、Bybit unchanged、IBKR live denial、IBKR contact、secret serialization
cross-wire coverage。這不是 Rust production behavior change、不是 IBKR contact、不是 connector
runtime、不是 market-data collection、不是 order route、不是 scorecard writer、不是 DB apply、
不是 tiny-live/live gate；只把 PIT universe artifact 的 source-only、frozen-for-evidence、
survivorship-safe、no-contact、no-secret posture 變成行為型 regression test 與 source-static guard。

已完成：

- 在 `stock_etf_pit_universe_acceptance.rs` 新增
  `pit_universe_rejects_freeze_survivorship_and_authority_cross_wire_independently`。
- Acceptance 證明 `frozen_for_evidence_clock=false` 只產生
  `UniverseNotFrozenForEvidenceClock`。
- Acceptance 證明 `survivorship_bias_controls_present=false` 只產生
  `SurvivorshipControlsMissing`。
- Acceptance 證明 `bybit_live_execution_unchanged=false` 只產生
  `BybitLiveExecutionNotProtected`。
- Acceptance 證明 `ibkr_live_denied=false` 只產生 `IbkrLiveNotDenied`。
- Acceptance 證明 `ibkr_contact_performed=true` 只產生 `IbkrContactPerformed`。
- Acceptance 證明 `secret_content_serialized=true` 只產生 `SecretContentSerialized`。
- 在 `test_stock_etf_pit_universe_source_static.py` 新增 accepted fixture body parser，禁止
  crypto/Bybit lane、missing universe identity/hash/as-of/count、missing freeze/survivorship controls、
  Bybit changed、IBKR live not denied、IBKR contact、secret serialization 被 hardcoded 到 accepted
  fixture，並鎖住 default fail-closed posture。

驗證：

- Targeted rustfmt check：PASS。
- PIT universe source static pytest：`9 passed`。
- PIT universe Rust acceptance：`8 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace pytest：PASS；主計畫與 Operator summary 保持 checkpoint title coverage。
- Diff check：PASS。

PM 邊界不變：此 checkpoint 不改 Rust production code、不改 endpoint/IPC method、不呼叫 IBKR、
不導入 IBKR SDK、不讀/建 secret、不啟動 connector runtime、不啟動 market-data collection、不做
scorecard writer、不做 DB/evidence writer、不做 paper order route、不做 Linux runtime sync/restart、
不授權 tiny-live/live 或任何 Bybit behavior change。

## 168. 2026-07-01 PM session source checkpoint：Stock/ETF Instrument Identity Authority Cross-Wire Guard

本 checkpoint 補強 `stock_etf_instrument_identity` 中 `StockEtfInstrumentIdentityV1` 的 Bybit
unchanged、IBKR live denial、margin/short denial、options/CFD denial、IBKR contact、secret
serialization cross-wire coverage。這不是 Rust production behavior change、不是 IBKR contact、
不是 connector runtime、不是 market-data subscription、不是 order route、不是 scorecard writer、
不是 DB apply、不是 tiny-live/live gate；只把 instrument identity artifact 的 source-only、
point-in-time、cash-only、no-contact、no-secret posture 變成行為型 regression test 與 source-static
guard。

已完成：

- 在 `stock_etf_instrument_identity_acceptance.rs` 新增
  `instrument_identity_rejects_live_margin_secret_and_authority_cross_wire_independently`。
- Acceptance 證明 `bybit_live_execution_unchanged=false` 只產生
  `BybitLiveExecutionNotProtected`。
- Acceptance 證明 `ibkr_live_denied=false` 只產生 `IbkrLiveNotDenied`。
- Acceptance 證明 `margin_short_denied=false` 只產生 `MarginShortNotDenied`。
- Acceptance 證明 `options_cfd_denied=false` 只產生 `OptionsCfdNotDenied`。
- Acceptance 證明 `ibkr_contact_performed=true` 只產生 `IbkrContactPerformed`。
- Acceptance 證明 `secret_content_serialized=true` 只產生 `SecretContentSerialized`。
- 在 `test_stock_etf_instrument_identity_source_static.py` 新增 accepted fixture body parser，禁止
  crypto/Bybit lane、missing instrument identity/as-of/calendar、Bybit changed、IBKR live not denied、
  margin/short/options/CFD not denied、IBKR contact、secret serialization 被 hardcoded 到 accepted
  fixture，並鎖住 default fail-closed posture。

驗證：

- Targeted rustfmt check：PASS。
- Instrument identity source static pytest：`8 passed`。
- Instrument identity Rust acceptance：`9 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace pytest：PASS；主計畫與 Operator summary 保持 checkpoint title coverage。
- Diff check：PASS。

PM 邊界不變：此 checkpoint 不改 Rust production code、不改 endpoint/IPC method、不呼叫 IBKR、
不導入 IBKR SDK、不讀/建 secret、不啟動 connector runtime、不啟動 market-data subscription、不做
scorecard writer、不做 DB/evidence writer、不做 paper order route、不做 Linux runtime sync/restart、
不授權 tiny-live/live 或任何 Bybit behavior change。

## 169. 2026-07-01 PM session source checkpoint：Stock/ETF Non-Bybit API Allowlist Acceptance Cross-Wire Guard

本 checkpoint 補強 `ibkr_non_bybit_api_allowlist` 中 `NonBybitApiAllowlistV1` 的 read / paper-write /
denied action bucket、Client Portal Web API denial、live/account-transfer/margin-short-options-CFD /
market-data-entitlement/account-management write denial、IBKR contact、secret serialization、Bybit
live protection cross-wire coverage。這不是 Rust production behavior change、不是 IBKR contact、
不是 connector runtime、不是 Client Portal Web API enablement、不是 paper order route、不是
secret access、不是 tiny-live/live gate；只把 non-Bybit API allowlist artifact 的 source-only、
no-runtime、no-contact、no-secret、no-Bybit-cross-wire posture 變成行為型 regression test 與
source-static guard。

已完成：

- 新增 `ibkr_non_bybit_api_allowlist_acceptance.rs`，覆蓋 default fail-closed posture。
- Acceptance 證明 accepted fixture pin 住 required action matrix、contract id、source version、no
  contact、no secret、Bybit live execution protected。
- Acceptance 證明 `ServerTimeRead`、`AccountSummarySnapshotRead`、`PaperOrderSubmit`、
  `LiveOrderSubmit`、`ClientPortalWebApiUse` 的 classification / denial semantics。
- Acceptance 證明 missing action、duplicated action、wrong bucket action 都會被拒絕。
- Acceptance 證明 Client Portal Web API、live order、account transfer、margin/short/options/CFD、
  market-data entitlement purchase、account-management write denial 缺失都會各自只產生單一對應
  blocker。
- Acceptance 證明 `ibkr_contact_performed=true`、`secret_content_serialized=true`、
  `bybit_live_execution_protected=false` 都會各自只產生單一對應 blocker。
- 在 `test_ibkr_non_bybit_api_allowlist_source_static.py` 新增 accepted fixture body parser，禁止 empty
  action buckets、denial booleans false、IBKR contact、secret serialization、Bybit protection loss 被
  hardcoded 到 accepted fixture，並鎖住 default fail-closed posture。

驗證：

- Targeted rustfmt check：PASS。
- Non-Bybit allowlist source static pytest：`6 passed`。
- Non-Bybit allowlist Rust acceptance：`4 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace pytest：PASS；主計畫與 Operator summary 保持 checkpoint title coverage。
- Diff check：PASS。

PM 邊界不變：此 checkpoint 不改 Rust production code、不改 endpoint/IPC method、不呼叫 IBKR、
不導入 IBKR SDK、不讀/建 secret、不啟動 connector runtime、不啟用 Client Portal Web API、不做
broker routing、不做 paper order route、不做 Linux runtime sync/restart、不授權 tiny-live/live 或任何
Bybit behavior change。

## 170. 2026-07-01 PM session source checkpoint：IBKR Phase2 Policy Template Authority Cross-Wire Guard

本 checkpoint 補強 `ibkr_phase2_policies` 中 Phase 2 redaction、rate-limit、audit-event、
paper-attestation、Python write-guard policy templates 的單點 authority regression coverage。這不是
Rust production behavior change、不是 IBKR contact、不是 connector runtime、不是 redaction writer、
不是 rate limiter runtime、不是 audit writer、不是 secret lookup、不是 paper order route、不是
tiny-live/live gate；只把 Phase 2 policy source templates 的 no-secret-leak、per-action pacing、
append-only audit、Rust-scoped paper attestation、Python no-write / no-Bybit-mutation posture 變成
exact-blocker acceptance test 與 source-static guard。

已完成：

- 在 `ibkr_phase2_policy_acceptance.rs` 新增 redaction exact-blocker cases，逐一證明 missing payload
  hashes、account/secret/path/cookie/token/raw-payload/stack-trace log leaks 只產生單一對應 blocker。
- 新增 rate-limit exact-blocker cases，逐一證明 non-per-action scope、missing spacing/concurrency、
  missing per-action buckets、missing pacing circuit breaker、missing read/market-data/paper-write
  budgets 只產生單一對應 blocker。
- 新增 audit-event exact-blocker cases，逐一證明 append-only、lane/broker/environment/operation、
  allow/deny reason、source/raw/redacted hashes、account-fingerprint-only 與 raw-payload-storage
  posture 不可漏開。
- 新增 paper-attestation / Python write-guard exact-blocker cases，逐一證明 Phase 2 gate、session、
  Rust IPC、scoped authorization、Decision Lease、Guardian、risk/instrument/idempotency/lifecycle/
  reconciliation、paper-only、live/margin denial、max notional、Python no-write/no-secret/GUI no-override/
  Bybit unchanged posture 不可漏開。
- 在 `test_ibkr_phase2_policies_source_static.py` 新增 source-template/default block parser，鎖住
  source templates 的安全 posture 與 default fail-closed posture。

驗證：

- Targeted rustfmt check：PASS。
- Phase2 policy source static pytest：`4 passed`。
- Phase2 policy Rust acceptance：`13 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace pytest：PASS；主計畫與 Operator summary 保持 checkpoint title coverage。
- Diff check：PASS。

PM 邊界不變：此 checkpoint 不改 Rust production code、不改 endpoint/IPC method、不呼叫 IBKR、
不導入 IBKR SDK、不讀/建 secret、不啟動 connector runtime、不啟動 redaction/rate-limit/audit runtime、
不做 broker routing、不做 paper order route、不做 Linux runtime sync/restart、不授權 tiny-live/live
或任何 Bybit behavior change。

## 171. 2026-07-01 PM session source checkpoint：IBKR Phase2 Gate Artifact Metadata Cross-Wire Guard

本 checkpoint 補強 `ibkr_phase2_artifact` 中 immutable Phase 2 gate artifact 的 metadata、reviewer、
seal、hash 與 default runtime posture coverage。這不是 Rust production behavior change、不是 IBKR
contact、不是 connector runtime、不是 artifact materialization、不是 secret lookup、不是 broker session、
不是 paper order route、不是 tiny-live/live gate；只把 gate artifact 的 sealed-review metadata、
source/ADR/AMD identity、immutable storage、hash lineage、default fail-closed posture 變成 exact-blocker
acceptance test 與 source-static guard。

已完成：

- 在 `ibkr_phase2_artifact_acceptance.rs` 新增
  `artifact_rejects_each_metadata_seal_and_hash_gap_independently`。
- Acceptance 證明 artifact id、ADR、AMD、source commit、created-at、immutable storage path、PM reviewer、
  Operator reviewer、sealed flag、raw artifact hash、redacted summary hash 缺失或錯誤都會各自只產生
  單一對應 blocker。
- 保留既有 runtime/gate mismatch aggregate coverage；不把會同時拒絕 external gate 的 runtime drift
  誤標成 single-blocker。
- 在 `test_ibkr_phase2_artifact_source_static.py` 新增 default block parser，鎖住 contract/source default
  empty、reviewer empty、sealed false、gate/default policy flags false、secret/topology default、hash empty、
  supersedes none 的 fail-closed posture。

驗證：

- Targeted rustfmt check：PASS。
- Phase2 artifact source static pytest：`5 passed`。
- Phase2 artifact Rust acceptance：`9 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace pytest：PASS；主計畫與 Operator summary 保持 checkpoint title coverage。
- Diff check：PASS。

PM 邊界不變：此 checkpoint 不改 Rust production code、不改 endpoint/IPC method、不呼叫 IBKR、
不導入 IBKR SDK、不讀/建 secret、不啟動 connector runtime、不物化 PASS artifact、不做 broker routing、
不做 paper order route、不做 Linux runtime sync/restart、不授權 tiny-live/live 或任何 Bybit behavior
change。

## 172. 2026-07-01 PM session source checkpoint：IBKR External Surface Gate Precontact Cross-Wire Guard

本 checkpoint 補強 `ibkr_phase2_gate` 中 `IbkrExternalSurfaceGateV1` 的 pre-contact gate posture。
這不是 Rust production behavior change、不是 IBKR contact、不是 connector runtime、不是 session
attestation runtime、不是 secret lookup、不是 broker session、不是 paper order route、不是 tiny-live/live
gate；只把 external surface gate 的 contract/source identity、ADR/AMD、API baseline、loopback host、
paper gateway port、live-port denial、secret contract/live-secret absence、API allowlist、redaction、
rate-limit、audit-event、paper-attestation、Python no-write 與 no-retroactive-call posture 變成
exact-blocker acceptance test 與 source-static guard。

已完成：

- 在 `ibkr_phase2_gate_acceptance.rs` 新增
  `external_surface_gate_rejects_each_precontact_gap_independently`。
- Acceptance 證明 contract id、source version、status、ADR、AMD、API baseline、host policy、port
  policy、live-port denial、secret contract、live-secret absence、API allowlist、redaction suite、
  rate-limit policy、audit-event policy、paper-attestation contract、Python no-write guard、retroactive
  IBKR call 都會各自只產生單一對應 blocker。
- 在 `test_ibkr_phase2_gate_source_static.py` 新增 default / passing fixture block parser，鎖住 default
  blocked posture 與 passing fixture no-side-effect posture。

驗證：

- Targeted rustfmt check：PASS。
- Phase2 gate source static pytest：`5 passed`。
- Phase2 gate Rust acceptance：`12 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace pytest：PASS；主計畫與 Operator summary 保持 checkpoint title coverage。
- Diff check：PASS。

PM 邊界不變：此 checkpoint 不改 Rust production code、不改 endpoint/IPC method、不呼叫 IBKR、
不導入 IBKR SDK、不讀/建 secret、不啟動 connector runtime、不啟動 session attestation runtime、
不做 broker routing、不做 paper order route、不做 Linux runtime sync/restart、不授權 tiny-live/live
或任何 Bybit behavior change。

## 173. 2026-07-01 PM session source checkpoint：IBKR Session Attestation Source Posture Cross-Wire Guard

本 checkpoint 補強 `ibkr_phase2_gate` 中 `IbkrSessionAttestationV1` 的 session identity、
loopback/paper gateway、account/secret fingerprint、gateway mode、credential fallback、data-tier、
entitlement、startup-time、raw artifact hash 與 freshness window posture。這不是 Rust production
behavior change、不是 IBKR contact、不是 connector runtime、不是 session runtime、不是 secret lookup、
不是 broker session、不是 paper order route、不是 tiny-live/live gate；只把 session attestation 的
paper-only、loopback-only、secret-lineage、no-live-secret、delayed/entitled-data、freshness-window posture
變成 exact-blocker acceptance test 與 source-static guard。

已完成：

- 在 `ibkr_phase2_gate_acceptance.rs` 新增
  `session_attestation_rejects_each_secret_lineage_and_window_gap_independently`。
- Acceptance 證明 contract id、source version、status、environment、host、paper gateway port、
  account fingerprint、live-account marker、process identity、gateway mode、secret fingerprint、
  secret slot mode、world-readable secret、live secret、env-var credential fallback、API server version、
  data tier、entitlements fingerprint、market-data entitlement purchase denial、gateway startup time、
  raw artifact hash、attestation window 都會各自只產生單一對應 blocker。
- Acceptance 明確保留 live TWS/gateway port 的 aggregate 行為：live port 必須同時命中
  `LivePortDenied` 與 `PortNotPaperGatewayDefault`，不得被誤寫成單一 blocker。
- Acceptance 證明 stale attestation 只產生 `StaleAttestation`。
- 在 `test_ibkr_phase2_gate_source_static.py` 新增 session default / paper fixture block parser，鎖住
  default fail-closed posture 與 paper fixture 的 loopback/paper-gateway/no-live-secret/hash-lineage posture。

驗證：

- Targeted rustfmt check：PASS。
- Phase2 gate source static pytest：`6 passed`。
- Phase2 gate Rust acceptance：`13 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace pytest：PASS；主計畫與 Operator summary 保持 checkpoint title coverage。
- Diff check：PASS。

PM 邊界不變：此 checkpoint 不改 Rust production code、不改 endpoint/IPC method、不呼叫 IBKR、
不導入 IBKR SDK、不讀/建 secret、不啟動 connector runtime、不啟動 session attestation runtime、
不做 broker session、不做 broker routing、不做 paper order route、不做 Linux runtime sync/restart、
不授權 tiny-live/live 或任何 Bybit behavior change。

## 174. 2026-07-01 PM session source checkpoint：IBKR Feature Flag Secret Auth Authority Cross-Wire Guard

本 checkpoint 補強 `ibkr_feature_flag_secret_auth` 中 feature flag、secret-slot、Phase 2 artifact、
session attestation 與 scoped authorization envelope 的 authority cross-wire coverage。這不是 Rust
production behavior change、不是 IBKR contact、不是 connector runtime、不是 secret lookup、不是
authorization runtime、不是 broker session、不是 paper order route、不是 tiny-live/live gate；只把
server-Rust matrix authority、GUI override denial、lane/broker/environment/instrument/operation、read/paper
flags、shadow-only、secret contract、artifact/session prerequisite、authorization envelope lineage 與 expiry
posture 變成 exact-blocker acceptance test 與 source-static guard。

已完成：

- 在 `ibkr_feature_flag_secret_auth_acceptance.rs` 新增
  `feature_flag_secret_auth_rejects_each_authority_gap_independently`。
- Acceptance 證明 contract id、source version、server-Rust authority、GUI override denial、wrong lane、
  wrong broker、live environment、denied instrument kind、live/account-write operation、lane flag、read-only
  flag、paper flag、shadow-only blocks paper、secret contract rejection、Phase 2 artifact rejection、session
  attestation rejection、authorization envelope mismatch、permission scope mismatch、risk config hash、envelope
  expiry、secret-slot fingerprint mismatch、account fingerprint mismatch 都會各自只產生單一對應 blocker。
- Acceptance 明確保留 aggregate lineage failures：live-secret absence 未證明會同時拒絕 secret contract；
  invalid secret/account hashes 會同時命中 invalid-hash 與 fingerprint mismatch，不被誤標成 single-blocker。
- 在 `test_ibkr_feature_flag_secret_auth_source_static.py` 新增 authorization envelope default / paper fixture
  與 matrix default block parser，鎖住 default denied posture、paper rehearsal fixture hashes 與 matrix default
  fail-closed posture。

驗證：

- Targeted rustfmt check：PASS。
- Feature flag secret auth source static pytest：`6 passed`。
- Feature flag secret auth Rust acceptance：`10 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace pytest：PASS；主計畫與 Operator summary 保持 checkpoint title coverage。
- Diff check：PASS。

PM 邊界不變：此 checkpoint 不改 Rust production code、不改 endpoint/IPC method、不呼叫 IBKR、
不導入 IBKR SDK、不讀/建 secret、不啟動 connector runtime、不啟動 authorization runtime、不做
broker session、不做 broker routing、不做 paper order route、不做 Linux runtime sync/restart、不授權
tiny-live/live 或任何 Bybit behavior change。

## 175. 2026-07-01 PM session source checkpoint：IBKR Phase2 Runtime Secret Topology Cross-Wire Guard

本 checkpoint 補強 `ibkr_phase2_runtime` 中 `IbkrSecretSlotContractV1` 與
`IbkrApiSessionTopologyV1` 的 pre-contact runtime evidence contract posture。這不是 Rust production
behavior change、不是 IBKR contact、不是 connector runtime、不是 secret lookup、不是 gateway startup、
不是 broker session、不是 paper order route、不是 tiny-live/live gate；只把 secret-slot hashed posture、
live-secret absence、owner-only permissions、env-var fallback denial、no secret/account serialization、
loopback paper gateway topology、deterministic client/process identity、account fingerprint 與 topology
lineage 變成 exact-blocker acceptance test 與 source-static guard。

已完成：

- 在 `ibkr_phase2_runtime_acceptance.rs` 新增
  `secret_slot_contract_rejects_each_slot_and_secret_gap_independently`。
- Acceptance 證明 secret contract id、source version、contract present、readonly/paper/live slot posture、
  secret/account fingerprint hash、owner-only permissions、env-var fallback denial、secret serialization、
  account id serialization、live-secret absence proof 都會各自只產生單一對應 blocker。
- 在同檔新增 `topology_rejects_each_paper_gateway_gap_independently`。
- Acceptance 證明 topology contract id、source version、topology present、API baseline、runtime owner、
  loopback host、paper port、gateway mode、paper environment、deterministic client id、process identity、
  account fingerprint、API server version、data entitlements、startup time、attestation expiry 都會各自只產生
  單一對應 blocker。
- Acceptance 明確保留 live TWS/gateway port aggregate 行為：live port 必須同時命中
  `LivePortDenied` 與 `PaperPortNotUsed`。
- 在 `test_ibkr_phase2_runtime_source_static.py` 新增 secret-slot/default template 與 topology/default
  template block parser，鎖住 default fail-closed posture 與 source template 的 paper-only/no-secret posture。

驗證：

- Targeted rustfmt check：PASS。
- Phase2 runtime source static pytest：`5 passed`。
- Phase2 runtime Rust acceptance：`9 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace pytest：PASS；主計畫與 Operator summary 保持 checkpoint title coverage。
- Diff check：PASS。

PM 邊界不變：此 checkpoint 不改 Rust production code、不改 endpoint/IPC method、不呼叫 IBKR、
不導入 IBKR SDK、不讀/建 secret、不啟動 connector runtime、不啟動 IB Gateway/TWS、不做 broker session、
不做 broker routing、不做 paper order route、不做 Linux runtime sync/restart、不授權 tiny-live/live 或任何
Bybit behavior change。

## 176. 2026-07-01 PM session source checkpoint：Stock/ETF Readonly Probe Request Authority Lineage Cross-Wire Guard

本 checkpoint 補強 `stock_etf_ibkr_readonly_probe_request` 的 authority、pre-contact lineage 與
no-side-effect boundary coverage。這不是 Rust production behavior change、不是 IBKR contact、不是
connector runtime、不是 read-only probe execution、不是 secret lookup、不是 broker session、不是
paper order route、不是 tiny-live/live gate；只把 future first-contact 前 readonly probe request envelope
的 lane/broker/environment/action/operation/authority/effect、Phase2 lineage 與 no-runtime/no-order/no-Bybit
cross-wire posture 變成 exact-blocker acceptance test 與 source-static guard。

已完成：

- 在 `stock_etf_ibkr_readonly_probe_request_acceptance.rs` 新增
  `readonly_probe_request_rejects_each_authority_gap_independently`。
- Acceptance 證明 contract id、source version、asset lane、broker、environment、read action、operation、
  authority scope、effect-capable gaps 都會各自只產生單一對應 blocker。
- 在同檔新增 `readonly_probe_request_rejects_each_lineage_gap_independently`。
- Acceptance 證明 request/probe ids、external surface gate、Phase2 artifact、non-Bybit allowlist、
  secret-slot、API session topology、session attestation、redaction/rate-limit/audit policies 與
  source/raw/redacted artifact hash lineage gaps 都會各自只產生單一對應 blocker。
- Acceptance 明確保留 paper-order action aggregate 行為：paper write action 必須同時命中
  `ProbeActionMismatch` 與 `ApiActionNotReadAllowed`。
- 在同檔新增 `readonly_probe_request_rejects_each_boundary_flag_independently`。
- Acceptance 證明 IBKR contact、connector runtime、secret serialization、order route、paper submit、
  DB apply、evidence clock、Bybit path reuse、live/tiny-live、margin/short/options/CFD、account write、
  market-data entitlement purchase、Client Portal Web API、Python direct broker write flags 都會各自只產生
  單一對應 blocker。
- 在 `test_stock_etf_ibkr_readonly_probe_request_source_static.py` 新增 default / accepted fixture block
  parser，鎖住 default fail-closed posture 與 accepted fixture 不可硬編 runtime、secret、order、Bybit
  cross-wire 或 empty-lineage posture。

驗證：

- Targeted rustfmt check：PASS。
- Readonly probe request source static pytest：`9 passed`。
- Readonly probe request Rust acceptance：`10 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace pytest：PASS；主計畫與 Operator summary 保持 checkpoint title coverage。
- Diff check：PASS。

PM 邊界不變：此 checkpoint 不改 Rust production code、不改 endpoint/IPC method、不呼叫 IBKR、
不導入 IBKR SDK、不讀/建 secret、不啟動 connector runtime、不啟動 read-only probe runtime、不做
broker session、不做 broker routing、不做 paper order route、不做 Linux runtime sync/restart、不授權
tiny-live/live 或任何 Bybit behavior change。

## 177. 2026-07-01 PM session source checkpoint：Stock/ETF Readonly Probe Result Import Authority Lineage Cross-Wire Guard

本 checkpoint 補強 `stock_etf_ibkr_readonly_probe_result_import_request` 的 authority、common lineage、
kind-specific downstream lineage、timestamp/replay 與 no-side-effect boundary coverage。這不是 Rust
production behavior change、不是 IBKR contact、不是 connector runtime、不是 read-only probe execution、
不是 result import execution、不是 secret lookup、不是 broker session、不是 evidence/scorecard writer、
不是 paper order route、不是 tiny-live/live gate；只把 future sanitized read-only result import request
envelope 的 lane/broker/environment/action/operation/authority/effect、request/result/source lineage、
downstream lineage、idempotency/replay 與 no-runtime/no-writer/no-order/no-Bybit cross-wire posture 變成
exact-blocker acceptance test 與 source-static guard。

已完成：

- 在 `stock_etf_ibkr_readonly_probe_result_import_request_acceptance.rs` 新增
  `result_import_request_rejects_each_authority_gap_independently`。
- Acceptance 證明 contract id、source version、asset lane、broker、environment、read action、operation、
  authority scope、effect-capable gaps 都會各自只產生單一對應 blocker。
- 在同檔新增 `result_import_request_rejects_each_common_lineage_gap_independently`。
- Acceptance 證明 result-import/request/probe ids、readonly probe request、session attestation、non-Bybit
  allowlist、redaction/audit policies、payload/raw/redacted/source artifact hashes、result as-of、
  idempotency、duplicate import、stale manual-review gates 都會各自只產生單一對應 blocker。
- Acceptance 明確保留 missing import timestamp aggregate 行為：`import_requested_at_ms=0` 必須同時命中
  `ImportRequestedAtMissing` 與 `ResultAsOfAfterImportRequested`。
- 在同檔新增 `result_import_request_rejects_each_kind_lineage_gap_independently`。
- Acceptance 證明 account cash ledger、market-data provenance、instrument identity、broker lifecycle event
  log 的 contract/hash gaps 都會各自只產生單一對應 blocker。
- 在同檔新增 `result_import_request_rejects_each_boundary_flag_independently`。
- Acceptance 證明 IBKR contact、connector runtime、secret serialization、result import、evidence writer、
  scorecard writer、DB apply、order route、paper submit、Bybit path reuse、live/tiny-live、margin/short/options/
  CFD、account write、market-data entitlement purchase、Client Portal Web API、Python direct broker write flags
  都會各自只產生單一對應 blocker。
- 在 `test_stock_etf_ibkr_readonly_probe_result_import_request_source_static.py` 新增 default / accepted fixture
  block parser，鎖住 default fail-closed posture 與 accepted fixture 不可硬編 runtime、secret、order、writer、
  Bybit cross-wire 或 empty-common-lineage posture。

驗證：

- Targeted rustfmt check：PASS。
- Readonly probe result-import source static pytest：`11 passed`。
- Readonly probe result-import Rust acceptance：`11 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace pytest：PASS；主計畫與 Operator summary 保持 checkpoint title coverage。
- Diff check：PASS。

PM 邊界不變：此 checkpoint 不改 Rust production code、不改 endpoint/IPC method、不呼叫 IBKR、
不導入 IBKR SDK、不讀/建 secret、不啟動 connector runtime、不啟動 read-only probe runtime、不執行
result import、不做 broker session、不做 broker routing、不做 evidence/scorecard writer、不做 paper order
route、不做 Linux runtime sync/restart、不授權 tiny-live/live 或任何 Bybit behavior change。

## 178. 2026-07-01 PM session source checkpoint：IBKR Paper Lifecycle Event Authority Lineage Cross-Wire Guard

本 checkpoint 補強 `ibkr_paper_lifecycle` 的 append-only event identity、request lineage、paper-only
authority、transition/stale-policy、denial semantics 與 fill identity coverage。這不是 Rust production
behavior change、不是 IBKR contact、不是 connector runtime、不是 lifecycle writer、不是 secret lookup、
不是 broker session、不是 evidence/scorecard writer、不是 paper order route、不是 tiny-live/live gate；只把
paper lifecycle event 的 source/event/request identity、StockEtfCash/IBKR/Paper authority、state transition、
stale recovery、denied-event 與 fill id posture 變成 exact-blocker acceptance test 與 source-static guard。

已完成：

- 在 `ibkr_paper_lifecycle_acceptance.rs` 新增
  `lifecycle_event_rejects_each_identity_and_lineage_gap_independently`。
- Acceptance 證明 lifecycle/event-log contract ids、source version、event id、event sequence、previous-event
  hash、event time/hash、paper-order request contract/hash、asset lane、broker、local order id、idempotency
  key、reconciliation run id gaps 都會各自只產生單一對應 blocker。
- 在同檔新增 `lifecycle_event_rejects_each_paper_authority_and_artifact_gap_independently`。
- Acceptance 證明 ReadOnly environment、paper transition mismatch、broker order id、allowed-event denial
  reason、stale policy missing/mismatch、raw/redacted artifact hash gaps 都會各自只產生單一對應 blocker。
- Acceptance 明確保留 non-paper operation aggregate 行為：非 paper lifecycle operation 必須同時命中
  `OperationNotPaperLifecycle` 與 `OperationTransitionMismatch`。
- 在同檔新增 `lifecycle_event_rejects_denial_and_fill_identity_gaps_independently`。
- Acceptance 證明 denied event missing reason、denied active-state event、fill execution id、commission report
  id gaps 都會各自只產生單一對應 blocker。
- 在 `test_ibkr_paper_lifecycle_source_static.py` 新增 default / accepted ack fixture block parser，鎖住
  default fail-closed posture 與 accepted ack fixture 不可硬編 live/Bybit/wrong-operation/denied/empty-lineage/
  stale-policy-missing posture。

驗證：

- Targeted rustfmt check：PASS。
- Paper lifecycle source static pytest：`7 passed`。
- Paper lifecycle Rust acceptance：`15 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace pytest：PASS；主計畫與 Operator summary 保持 checkpoint title coverage。
- Diff check：PASS。

PM 邊界不變：此 checkpoint 不改 Rust production code、不改 endpoint/IPC method、不呼叫 IBKR、
不導入 IBKR SDK、不讀/建 secret、不啟動 connector runtime、不啟動 lifecycle writer、不做 broker
session、不做 broker routing、不做 evidence/scorecard writer、不做 paper order route、不做 Linux runtime
sync/restart、不授權 tiny-live/live 或任何 Bybit behavior change。

## 179. 2026-07-01 PM session source checkpoint：Stock/ETF Paper Fill Import Request Authority Lineage Cross-Wire Guard

本 checkpoint 補強 `stock_etf_paper_fill_import_request` 的 lane/broker/environment/method/operation/
authority、lifecycle/event-log/redaction/session lineage、idempotency/replay、stale-state policy 與
no-side-effect boundary coverage。這不是 Rust production behavior change、不是 IBKR contact、不是
connector runtime、不是 fill import execution、不是 DB/evidence writer、不是 secret lookup、不是 broker
session、不是 paper order route、不是 tiny-live/live gate；只把 future paper fill import request envelope 的
StockEtfCash/IBKR/Paper authority、lifecycle/event-log lineage、fill identity、stale policy 與 no-runtime/
no-writer/no-order/no-Bybit cross-wire posture 變成 exact-blocker acceptance test 與 source-static guard。

已完成：

- 在 `stock_etf_paper_fill_import_request_acceptance.rs` 新增
  `fill_import_request_rejects_each_authority_gap_independently`。
- Acceptance 證明 contract id、source version、asset lane、broker、environment、IPC method、operation、
  authority scope、effect-capable gaps 都會各自只產生單一對應 blocker。
- 在同檔新增 `fill_import_request_rejects_each_lineage_gap_independently`。
- Acceptance 證明 request id、session attestation、lifecycle/event-log contract/hash、redaction policy、
  source artifact、reconciliation run、broker order、execution、commission、idempotency、observed state、
  stale policy、raw/redacted artifact、duplicate import 與 explicit stale-unknown flags 都會各自只產生單一
  對應 blocker。
- Acceptance 明確保留 `StateUnknown` without stale policy aggregate 行為：必須同時命中
  `StaleStatePolicyMissing` 與 `StaleUnknownStateWithoutPolicy`。
- 在同檔新增 `fill_import_request_rejects_each_boundary_flag_independently`。
- Acceptance 證明 IBKR contact、connector runtime、secret serialization、fill import execution、DB apply、
  order route、Bybit path reuse、live/tiny-live、margin/short/options/CFD、Python direct broker write flags
  都會各自只產生單一對應 blocker。
- 在 `test_stock_etf_paper_fill_import_request_source_static.py` 新增 default / accepted fixture block parser，
  鎖住 default fail-closed posture 與 accepted fixture 不可硬編 crypto/Bybit/live/wrong-method/
  wrong-operation/effectful/empty-lineage/replay/runtime/secret/order posture。

驗證：

- Targeted rustfmt check：PASS。
- Paper fill import source static pytest：`8 passed`。
- Paper fill import Rust acceptance：`10 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace pytest：PASS；主計畫與 Operator summary 保持 checkpoint title coverage。
- Diff check：PASS。

PM 邊界不變：此 checkpoint 不改 Rust production code、不改 endpoint/IPC method、不呼叫 IBKR、
不導入 IBKR SDK、不讀/建 secret、不啟動 connector runtime、不執行 fill import、不做 broker session、
不做 broker routing、不做 DB/evidence writer、不做 paper order route、不做 Linux runtime sync/restart、
不授權 tiny-live/live 或任何 Bybit behavior change。

## 180. 2026-07-01 PM session source checkpoint：Stock/ETF Shadow Signal Request Authority Lineage Cross-Wire Guard

本 checkpoint 補強 `stock_etf_shadow_signal_request` 的 lane/broker/environment/method/operation/
authority、evidence-clock/PIT-universe/strategy/instrument/market-data/cost/event/source lineage 與
no-side-effect boundary coverage。這不是 Rust production behavior change、不是 IBKR contact、不是
connector runtime、不是 shadow signal emission、不是 shadow fill generation、不是 DB/evidence writer、
不是 secret lookup、不是 broker session、不是 paper order route、不是 tiny-live/live gate；只把 future
shadow signal evaluation request envelope 的 StockEtfCash/IBKR/Shadow authority、lineage 與 no-runtime/
no-writer/no-order/no-Bybit cross-wire posture 變成 exact-blocker acceptance test 與 source-static guard。

已完成：

- 在 `stock_etf_shadow_signal_request_acceptance.rs` 新增
  `shadow_signal_request_rejects_each_authority_gap_independently`。
- Acceptance 證明 contract id、source version、asset lane、broker、environment、IPC method、operation、
  authority scope、effect-capable gaps 都會各自只產生單一對應 blocker。
- 在同檔新增 `shadow_signal_request_rejects_each_lineage_gap_independently`。
- Acceptance 證明 request/evaluation/signal ids、evidence clock、PIT universe、strategy hypothesis、
  instrument identity、market-data provenance、cost model、asset-lane event 與 source artifact lineage gaps
  都會各自只產生單一對應 blocker。
- 在同檔新增 `shadow_signal_request_rejects_each_boundary_flag_independently`。
- Acceptance 證明 IBKR contact、connector runtime、secret serialization、shadow signal emission、shadow fill
  generation、scorecard writer、DB apply、order route、Bybit path reuse、live/tiny-live、margin/short/options/
  CFD、Python direct broker write flags 都會各自只產生單一對應 blocker。
- 在 `test_stock_etf_shadow_signal_request_source_static.py` 新增 default / accepted fixture block parser，
  鎖住 default fail-closed posture 與 accepted fixture 不可硬編 crypto/Bybit/paper/read-only/live/
  wrong-method/wrong-operation/effectful/empty-lineage/runtime/secret/order posture。

驗證：

- Targeted rustfmt check：PASS。
- Shadow signal request source static pytest：`8 passed`。
- Shadow signal request Rust acceptance：`9 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace pytest：PASS；主計畫與 Operator summary 保持 checkpoint title coverage。
- Diff check：PASS。

PM 邊界不變：此 checkpoint 不改 Rust production code、不改 endpoint/IPC method、不呼叫 IBKR、
不導入 IBKR SDK、不讀/建 secret、不啟動 connector runtime、不執行 shadow signal emission、不生成
shadow fill、不啟動 shadow collector、不做 broker session、不做 broker routing、不做 DB/evidence writer、
不做 scorecard writer、不做 paper order route、不做 Linux runtime sync/restart、不授權 tiny-live/live 或任何
Bybit behavior change。

## 181. 2026-07-01 PM session source checkpoint：Stock/ETF Paper Shadow Reconciliation Authority Lineage Cross-Wire Guard

本 checkpoint 補強 `stock_etf_paper_shadow_reconciliation` 的 contract/scope/authority、paper-fill/
shadow-signal/shadow-fill-model lineage、reconciliation evidence gates 與 no-side-effect boundary coverage。
這不是 Rust production behavior change、不是 IBKR contact、不是 connector runtime、不是 fill import
execution、不是 shadow fill generation、不是 reconciliation writer、不是 DB/evidence writer、不是 secret
lookup、不是 broker session、不是 paper order route、不是 tiny-live/live gate；只把 paper fill fact 與
synthetic shadow fill fact 的 reconciliation envelope 變成 exact-blocker acceptance test 與 source-static
guard。

已完成：

- 在 `stock_etf_paper_shadow_reconciliation_acceptance.rs` 新增
  `reconciliation_rejects_each_authority_gap_independently`。
- Acceptance 證明 contract id、source version、asset lane、broker、scope、authority scope、effect-capable
  gaps 都會各自只產生單一對應 blocker。
- 在同檔新增 `reconciliation_rejects_each_lineage_gap_independently`。
- Acceptance 證明 reconciliation run、paper local order、broker order、execution、commission、shadow signal
  ids，以及 lifecycle/event-log/paper-fill-import/shadow-signal/shadow-fill-model/cost/market/divergence/link/
  raw/redacted/source artifact hashes 都會各自只產生單一對應 blocker。
- 在同檔新增 `reconciliation_rejects_each_evidence_gate_independently`。
- Acceptance 證明 append-only event、paper fill imported、synthetic shadow fill、divergence threshold、
  divergence excess、unmatched paper/shadow fill evidence gates 都會各自只產生單一對應 blocker。
- 在同檔新增 `reconciliation_rejects_each_boundary_flag_independently`。
- Acceptance 證明 IBKR contact、connector runtime、secret serialization、fill import execution、shadow fill
  generation、reconciliation writer、scorecard writer、DB apply、order route、Bybit path reuse、live/tiny-live、
  margin/short/options/CFD、Python direct broker write flags 都會各自只產生單一對應 blocker。
- 在 `test_stock_etf_paper_shadow_reconciliation_source_static.py` 新增 default / accepted fixture block
  parser，鎖住 default fail-closed posture 與 accepted fixture 不可硬編 crypto/Bybit/wrong-scope/
  wrong-authority/effectful/empty-lineage/unready-evidence/runtime/secret/writer/order posture。

驗證：

- Targeted rustfmt check：PASS。
- Paper-shadow reconciliation source static pytest：`9 passed`。
- Paper-shadow reconciliation Rust acceptance：`10 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace pytest：PASS；主計畫與 Operator summary 保持 checkpoint title coverage。
- Diff check：PASS。

PM 邊界不變：此 checkpoint 不改 Rust production code、不改 endpoint/IPC method、不呼叫 IBKR、
不導入 IBKR SDK、不讀/建 secret、不啟動 connector runtime、不執行 fill import、不生成 shadow fill、
不啟動 reconciliation writer、不做 broker session、不做 broker routing、不做 DB/evidence writer、不做
scorecard writer、不做 paper order route、不做 Linux runtime sync/restart、不授權 tiny-live/live 或任何
Bybit behavior change。

## 182. 2026-07-01 PM session source checkpoint：Stock/ETF Scorecard Derivation Authority Lineage Cross-Wire Guard

本 checkpoint 補強 `stock_etf_scorecard_derivation` 的 artifact identity、ids、hash lineage、
atomic/replay/paper-shadow separation、seal 與 no-side-effect boundary coverage。這不是 Rust production
behavior change、不是 IBKR contact、不是 connector runtime、不是 broker fill import execution、不是
shadow fill generation、不是 reconciliation writer、不是 scorecard writer、不是 DB/evidence writer、不是
secret lookup、不是 paper order route、不是 tiny-live/live gate；只把 scorecard derivation artifact 的
sealed source-only lineage 與 no-runtime/no-writer/no-Bybit posture 變成 exact-blocker acceptance test
與 source-static guard。

已完成：

- 在 `stock_etf_scorecard_derivation_acceptance.rs` 新增
  `derivation_rejects_each_identity_gap_independently`。
- Acceptance 證明 contract id missing/mismatch、source version、asset lane、broker、environment gaps
  都會各自只產生單一對應 blocker。
- 在同檔新增 `derivation_rejects_each_id_gap_independently`。
- Acceptance 證明 derivation run、strategy、universe、benchmark、as-of ids 都會各自只產生單一對應 blocker。
- 在同檔新增 `derivation_rejects_each_hash_lineage_gap_independently`。
- Acceptance 證明 scorecard input、evidence clock、DQ、paper-shadow reconciliation、formula、preregistration、
  manifest、verdict、source commit、derivation code、output artifact、QC/MIT/QA review hashes 都會各自只
  產生單一對應 blocker。
- 在同檔新增 `derivation_rejects_each_evidence_and_seal_gap_independently`。
- Acceptance 證明 atomic-facts-only、idempotent replay、paper-shadow fill separation、Bybit-live protection
  與 sealed posture 都會各自只產生單一對應 blocker。
- 在同檔新增 `derivation_rejects_each_boundary_flag_independently`。
- Acceptance 證明 IBKR contact、connector runtime、broker fill import、shadow fill generation、
  reconciliation writer、scorecard writer、DB apply、evidence clock、secret serialization、live/tiny-live flags
  都會各自只產生單一對應 blocker。
- 在 `test_stock_etf_scorecard_derivation_source_static.py` 新增 default / accepted fixture block parser，
  鎖住 default fail-closed posture 與 accepted fixture 不可硬編 crypto/Bybit/live/shadow/empty-lineage/
  unsealed/runtime/secret/writer posture。

驗證：

- Targeted rustfmt check：PASS。
- Scorecard derivation source static pytest：`7 passed`。
- Scorecard derivation Rust acceptance：`11 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace pytest：PASS；主計畫與 Operator summary 保持 checkpoint title coverage。
- Diff check：PASS。

PM 邊界不變：此 checkpoint 不改 Rust production code、不改 endpoint/IPC method、不呼叫 IBKR、
不導入 IBKR SDK、不讀/建 secret、不啟動 connector runtime、不執行 broker fill import、不生成 shadow
fill、不啟動 reconciliation writer、不啟動 scorecard writer、不做 broker session、不做 broker routing、
不做 DB/evidence writer、不啟動 evidence clock、不做 paper order route、不做 Linux runtime sync/restart、
不授權 tiny-live/live 或任何 Bybit behavior change。

## 183. 2026-07-01 PM session source checkpoint：Stock/ETF Scorecard Verdict Authority Lineage Cross-Wire Guard

本 checkpoint 補強 `stock_etf_scorecard_verdict` 的 artifact identity、hash lineage、threshold/statistical
quality、review gates、derived-only / paper-shadow separation / live denial 與 no-side-effect boundary
coverage。這不是 Rust production behavior change、不是 IBKR contact、不是 connector runtime、不是 broker
fill import execution、不是 scorecard writer、不是 DB/evidence writer、不是 evidence clock runtime、不是
secret lookup、不是 paper order route、不是 tiny-live/live gate；只把 scorecard verdict artifact 的 statistical
gate、review gate 與 no-runtime/no-writer/no-live posture 變成 exact-blocker acceptance test 與 source-static
guard。

已完成：

- 在 `stock_etf_scorecard_verdict_acceptance.rs` 新增
  `scorecard_verdict_rejects_each_identity_gap_independently`。
- Acceptance 證明 contract id missing/mismatch、source version、asset lane、broker、environment gaps
  都會各自只產生單一對應 blocker。
- 在同檔新增 `scorecard_verdict_rejects_each_hash_lineage_gap_independently`。
- Acceptance 證明 scorecard input、evidence clock、DQ、formula、preregistration、benchmark、cost、strategy、
  reference-data、paper-shadow reconciliation、manifest 與 rationale hashes 都會各自只產生單一對應 blocker。
- 在同檔新增 `scorecard_verdict_rejects_each_threshold_shape_gap_independently`。
- Acceptance 證明 window/observation/divergence/probability threshold shape gaps 都會各自只產生單一對應
  blocker。
- 在同檔新增 `scorecard_verdict_rejects_each_profitability_and_quality_gap_independently`。
- Acceptance 證明 window/observation threshold not met、paper-shadow divergence exceeded、after-cost LCB、
  cost-stress LCB、PSR/DSR threshold、concentration/regime/breadth/freshness/survivorship/execution-realism
  labels 都會各自只產生單一對應 blocker。
- 在同檔新增 `scorecard_verdict_rejects_each_review_authority_and_boundary_gap_independently`。
- Acceptance 證明 QC/MIT/QA review hashes/pass flags、derived-only、paper-shadow separation、live-fill denial、
  Bybit-live protection、IBKR contact、connector runtime、broker fill import、scorecard writer、DB apply、
  evidence clock、secret serialization、live/tiny-live、sealed posture 與 execution-model-invalid special case
  都會各自只產生單一對應 blocker。
- 在 `test_stock_etf_scorecard_verdict_source_static.py` 新增 default / profitability fixture block parser，
  鎖住 default fail-closed posture 與 profitability fixture 不可硬編 crypto/Bybit/live/empty-lineage/
  missing-threshold/runtime/secret/writer/live/tiny-live posture。

驗證：

- Targeted rustfmt check：PASS。
- Scorecard verdict source static pytest：`8 passed`。
- Scorecard verdict Rust acceptance：`14 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace pytest：PASS；主計畫與 Operator summary 保持 checkpoint title coverage。
- Diff check：PASS。

PM 邊界不變：此 checkpoint 不改 Rust production code、不改 endpoint/IPC method、不呼叫 IBKR、
不導入 IBKR SDK、不讀/建 secret、不啟動 connector runtime、不執行 broker fill import、不啟動 scorecard
writer、不做 broker session、不做 broker routing、不做 DB/evidence writer、不啟動 evidence clock、不做
paper order route、不做 Linux runtime sync/restart、不授權 tiny-live/live 或任何 Bybit behavior change。

## 184. 2026-07-01 PM session source checkpoint：Stock/ETF Release Packet Authority Lineage Cross-Wire Guard

本 checkpoint 補強 `stock_etf_release_packet` 的 release identity、ADR/AMD/spec path、source timestamp、
reviewer signoff、evidence hash、migration evidence、kill-disable-cleanup proof 與 final no-live posture
coverage。這不是 Rust production behavior change、不是 IBKR contact、不是 connector runtime、不是
secret lookup、不是 release execution、不是 DB/evidence writer、不是 scorecard writer、不是 paper order
route、不是 tiny-live/live gate；只把 release packet artifact 的 final launch evidence lineage 與 no-live
posture 變成 exact-blocker acceptance test 與 source-static guard。

已完成：

- 在 `stock_etf_release_packet_acceptance.rs` 新增
  `release_packet_rejects_each_identity_and_path_gap_independently`。
- Acceptance 證明 packet id missing/mismatch、source version、ADR/AMD/spec path、source commit 與
  created timestamp gaps 都會各自只產生單一對應 blocker。
- 在同檔新增 `release_packet_rejects_each_required_role_gap_independently`。
- Acceptance 證明 PM/Operator/E2/E3/E4/QA/QC/MIT signoff 與 role report paths gaps 都會各自只產生
  單一對應 blocker。
- 在同檔新增 `release_packet_rejects_each_evidence_hash_gap_independently`。
- Acceptance 證明 E2/E3/E4/QA logs、manifest、redaction fixture、GUI screenshot、DQ manifest、scorecard
  regeneration、evidence archive pointer/hash gaps 都會各自只產生單一對應 blocker。
- 在同檔新增 `release_packet_rejects_each_migration_evidence_gap_independently`。
- Acceptance 證明 migration manifest、dry-run log 與 double-apply log gaps 都會各自只產生單一對應
  blocker。
- 在同檔新增 `release_packet_rejects_each_kill_disable_cleanup_gap_independently`。
- Acceptance 證明 lane/readonly/paper disable、shadow-only preservation、collector stop、GUI disable、
  live-secret absence、forward-only archive、destructive DB cleanup denial 與 kill proof hash gaps 都會各自只
  產生單一對應 blocker。
- 在同檔新增 `release_packet_rejects_each_final_posture_gap_independently`。
- Acceptance 證明 paper-shadow window、engineering shakedown、secret serialization、live/tiny-live authority
  與 sealed posture gaps 都會各自只產生單一對應 blocker。
- 在 `test_stock_etf_release_packet_source_static.py` 新增 impl-block parser，精準鎖住
  `StockEtfReleasePacketV1::accepted_fixture` / `Default` 與
  `StockEtfKillDisableCleanupProofV1::accepted_fixture`，避免錯抓第一個 `accepted_fixture()` 區塊。

驗證：

- Targeted rustfmt check：PASS。
- Release packet source static pytest：`9 passed`。
- Release packet Rust acceptance：`15 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace pytest：PASS；主計畫與 Operator summary 保持 checkpoint title coverage。
- Diff check：PASS。

PM 邊界不變：此 checkpoint 不改 Rust production code、不改 endpoint/IPC method、不呼叫 IBKR、
不導入 IBKR SDK、不讀/建 secret、不啟動 connector runtime、不執行 release、不做 DB/evidence
writer、不啟動 scorecard writer、不做 broker session、不做 broker routing、不做 paper order route、
不做 Linux runtime sync/restart、不授權 tiny-live/live 或任何 Bybit behavior change。

## 185. 2026-07-01 PM session source checkpoint：Stock/ETF Tiny-Live Eligibility Authority Lineage Cross-Wire Guard

本 checkpoint 補強 `stock_etf_tiny_live_eligibility` 的 contract identity、ADR/AMD/spec path、Phase 5 release
packet lineage、scorecard lineage、paper-shadow reconciliation lineage、DQ/preregistration/review hashes、
statistical gates、review gates、ADR-discussion-only decision、secret denial 與 sealed posture coverage。這不是
Rust production behavior change、不是 IBKR contact、不是 connector runtime、不是 secret lookup、不是
release execution、不是 DB/evidence writer、不是 scorecard writer、不是 paper order route、不是
tiny-live/live gate；只把 future ADR discussion eligibility artifact 的 lineage 與 no-live/no-secret posture
變成 exact-blocker acceptance test 與 source-static guard。

已完成：

- 在 `stock_etf_tiny_live_eligibility_acceptance.rs` 新增
  `tiny_live_eligibility_rejects_each_identity_and_path_gap_independently`。
- Acceptance 證明 contract id missing/mismatch、source version、ADR/AMD/spec path gaps 都會各自只產生
  單一對應 blocker。
- 在同檔新增 `tiny_live_eligibility_rejects_each_hash_lineage_gap_independently`。
- Acceptance 證明 Phase 5 release packet、scorecard derivation/verdict/manifest、paper-shadow reconciliation、
  DQ manifest、statistical preregistration、QC/MIT/QA review hashes 都會各自只產生單一對應 blocker。
- 在同檔新增 `tiny_live_eligibility_rejects_each_statistical_gate_gap_independently`。
- Acceptance 證明 paper-shadow window、benchmark after-cost LCB、min/actual independent observations、
  cost-stress LCB、divergence threshold/exceeded gates 都會各自只產生單一對應 blocker。
- 在同檔新增 `tiny_live_eligibility_rejects_each_label_and_review_gap_independently`。
- Acceptance 證明 concentration/regime/freshness labels 與 QC/MIT/QA review pass flags 都會各自只產生單一
  對應 blocker。
- 在同檔新增 `tiny_live_eligibility_rejects_each_decision_secret_and_seal_gap_independently`。
- Acceptance 證明 `NotEligible`、`TinyLiveAuthorized`、`LiveAuthorized`、secret serialization 與 unsealed
  posture 都會各自只產生單一對應 blocker；`AdrDiscussionOnly` 仍是唯一可通過 decision。
- 在 `test_stock_etf_tiny_live_eligibility_source_static.py` 新增 impl-block parser，精準鎖住
  `TinyLiveAdrEligibilityV1::adr_discussion_fixture` 與 `Default`，避免 fixture 硬編 tiny-live/live approval、
  secret serialization、unsealed posture 或空 lineage。

驗證：

- Targeted rustfmt check：PASS。
- Tiny-live eligibility source static pytest：`7 passed`。
- Tiny-live eligibility Rust acceptance：`13 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace pytest：PASS；主計畫與 Operator summary 保持 checkpoint title coverage。
- Diff check：PASS。

PM 邊界不變：此 checkpoint 不改 Rust production code、不改 endpoint/IPC method、不呼叫 IBKR、
不導入 IBKR SDK、不讀/建 secret、不啟動 connector runtime、不執行 release、不做 DB/evidence
writer、不啟動 scorecard writer、不做 broker session、不做 broker routing、不做 paper order route、
不做 Linux runtime sync/restart、不授權 tiny-live/live 或任何 Bybit behavior change。

## 186. 2026-07-01 PM session source checkpoint：Stock/ETF Paper Order Request Authority Lineage Cross-Wire Guard

本 checkpoint 補強 `stock_etf_paper_order_request` 的 common surface、method/operation/authority/effect
matrix、preview hash/order-intent gates、effect lifecycle lineage、submit/cancel/replace shape gates 與
no-side-effect boundary flags。這不是 Rust production behavior change、不是 IBKR contact、不是 connector
runtime、不是 secret lookup、不是 paper order routing、不是 cancel/replace routing、不是 DB/evidence writer、
不是 paper order route enablement、不是 tiny-live/live gate；只把 future paper order request envelope 的
StockEtfCash/IBKR/Paper 分離、lineage 與 no-runtime/no-order-route posture 變成 exact-blocker acceptance test
與 source-static guard。

已完成：

- 在 `stock_etf_paper_order_request_acceptance.rs` 新增
  `paper_order_request_rejects_each_common_surface_gap_independently`。
- Acceptance 證明 contract/source/lane/broker/environment/request method/request id/account hash gaps 可獨立
  阻斷；`LiveReservedDenied` environment 維持 `LiveEnvironmentDenied + EnvironmentNotPaper` 雙重阻斷。
- 在同檔新增 `paper_order_request_rejects_each_method_authority_and_effect_gap_independently`。
- Acceptance 證明 preview/submit/cancel/replace method surface 的 operation、authority scope、effect flag drift
  可各自只產生單一對應 blocker。
- 在同檔新增 `paper_order_request_rejects_each_preview_hash_and_order_intent_gap_independently`。
- Acceptance 證明 preview risk/instrument/cost/PIT/source hashes、symbol、instrument kind、side、order type、
  quantity、limit-price policy、time-in-force gates 可獨立阻斷；invalid limit price 維持 policy+price
  雙重阻斷。
- 在同檔新增 `paper_order_request_rejects_each_effect_lifecycle_and_submit_gap_independently`。
- Acceptance 證明 session/scoped authorization/decision lease/guardian/lifecycle/capability/audit lineage、
  local order id、idempotency key、submit broker-order pollution、submit cancel/replace pollution 可獨立阻斷。
- 在同檔新增 `paper_order_request_rejects_each_cancel_and_replace_gap_independently`。
- Acceptance 證明 cancel broker-order/cancel reason/shape pollution、replace instrument/replacement id/
  replacement quantity/replacement policy/replacement TIF/replace reason/original mutable pollution 可獨立阻斷；
  invalid replacement price 維持 policy+price 雙重阻斷。
- 在同檔新增 `paper_order_request_rejects_each_boundary_flag_independently`。
- Acceptance 證明 IBKR contact、connector runtime、secret serialization、order routed、Bybit path reuse、
  live/tiny-live authority、margin/short/options/CFD、Python direct broker write flags 都會各自只產生單一
  對應 blocker。
- 在 `test_stock_etf_paper_order_request_source_static.py` 新增 `fixtures.rs` coverage 與 fixture/default block
  parsers，鎖住 accepted preview/submit/cancel/replace fixtures 的 StockEtfCash/IBKR/Paper 分離、
  no-runtime、no-secret、no-Bybit posture。

驗證：

- Targeted rustfmt check：PASS。
- Paper order request source static pytest：`7 passed`。
- Paper order request Rust acceptance：`17 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace pytest：PASS；主計畫與 Operator summary 保持 checkpoint title coverage。
- Diff check：PASS。

PM 邊界不變：此 checkpoint 不改 Rust production code、不改 endpoint/IPC method、不呼叫 IBKR、
不導入 IBKR SDK、不讀/建 secret、不啟動 connector runtime、不執行 paper order routing、不執行 cancel/
replace routing、不做 DB/evidence writer、不啟動 scorecard writer、不做 broker session、不做 broker routing、
不做 Linux runtime sync/restart、不授權 tiny-live/live 或任何 Bybit behavior change。

## 187. 2026-07-01 PM session source checkpoint：Stock/ETF Lane-Scoped IPC Authority Lineage Cross-Wire Guard

本 checkpoint 補強 `stock_etf_lane_scoped_ipc` 的 top-level lane/broker/authority flags、Python forward-only /
direct-write denial、Bybit IPC/paper path denial、live denial、no-contact/no-runtime/no-secret flags、required
method coverage、denied method handling、command operation/authority/effect/rust ownership、required gate/
request-field/denial-reason coverage。這不是 Rust production behavior change、不是 IPC server start、不是
IBKR contact、不是 connector runtime、不是 secret lookup、不是 paper order routing、不是 DB/evidence writer、
不是 paper order route enablement、不是 tiny-live/live gate；只把 lane-scoped IPC source contract 的
StockEtfCash/IBKR 分離、required method matrix 與 no-runtime/no-Bybit-reuse posture 變成 exact-blocker
acceptance test 與 source-static guard。

已完成：

- 在 `stock_etf_lane_scoped_ipc_acceptance.rs` 新增
  `lane_scoped_ipc_rejects_each_top_level_authority_gap_independently`。
- Acceptance 證明 contract/source/lane/broker/Rust authority/Python forward-only/Python direct-write denial、
  Bybit IPC reuse denial、existing Bybit paper path denial、live denial、Bybit live protection、contact/runtime/
  secret gaps 都會各自只產生單一對應 blocker。
- 在同檔新增 `lane_scoped_ipc_rejects_each_command_coverage_gap_independently`。
- Acceptance 證明 missing command、duplicated command、extra denied method command 都會各自只產生單一對應
  blocker。
- 在同檔新增 `lane_scoped_ipc_rejects_each_command_shape_gap_independently`。
- Acceptance 證明 submit-paper command 的 operation、authority scope、effect flag、rust ownership、required
  gate、required request field、typed denial reason gaps 都會各自只產生單一對應 blocker。
- 在 `test_stock_etf_lane_scoped_ipc_source_static.py` 新增 required-method/default/accepted-fixture block
  parsers，鎖住 denied methods 不得進 `REQUIRED_METHODS`，並鎖住 accepted fixture 只能用
  StockEtfCash/IBKR/no-runtime/no-secret posture。

驗證：

- Targeted rustfmt check：PASS。
- Lane-scoped IPC source static pytest：`6 passed`。
- Lane-scoped IPC Rust acceptance：`12 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace pytest：PASS；主計畫與 Operator summary 保持 checkpoint title coverage。
- Diff check：PASS。

PM 邊界不變：此 checkpoint 不改 Rust production code、不改 endpoint/IPC method、不啟動 IPC server、
不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動 connector runtime、不執行 paper order routing、
不做 DB/evidence writer、不啟動 scorecard writer、不做 broker session、不做 broker routing、不做 Linux
runtime sync/restart、不授權 tiny-live/live 或任何 Bybit behavior change。

## 188. 2026-07-01 PM session source checkpoint：Stock/ETF Lane Taxonomy Authority Decision Cross-Wire Guard

本 checkpoint 補強 `stock_etf_lane` 的 broker capability decision coverage，固定 StockEtfCash/IBKR/Paper/
Shadow/ReadOnly taxonomy、feature flag fail-closed posture、gate input fail-closed posture、live/margin/options/
account-write denial、flag denial、read/shadow/paper gate denial 與 allowed authority scope。這不是 Rust
production behavior change、不是 IPC server start、不是 IBKR contact、不是 connector runtime、不是 secret
lookup、不是 paper order routing、不是 DB/evidence writer、不是 paper order route enablement、不是
tiny-live/live gate；只把 lane taxonomy 的 authority/denial ordering 與 no-live/no-Bybit-crosswire posture
變成 exact-denial acceptance test 與 source-static guard。

已完成：

- 在 `stock_etf_lane_acceptance.rs` 新增
  `broker_capability_rejects_each_lane_broker_and_operation_gap_independently`。
- Acceptance 證明 wrong asset lane、wrong broker、live-reserved environment、live order、margin/short、
  options/CFD、transfer/account-write、wrong instrument kind 都會各自只產生單一對應 denial reason。
- 在同檔新增 `broker_capability_rejects_each_flag_gap_independently`。
- Acceptance 證明 lane disabled、readonly disabled、paper disabled、shadow-only flags 都會各自只產生單一對應
  denial reason。
- 在同檔新增 `broker_capability_rejects_each_gate_gap_independently`。
- Acceptance 證明 read authorization、shadow cost/universe、paper market/credential/connector/auth/decision
  lease/guardian gates 都會各自只產生單一對應 denial reason。
- 在同檔新增 `broker_capability_allows_only_read_shadow_or_paper_when_all_gates_pass`。
- Acceptance 證明 all-green read、shadow、paper requests 只得到對應 ReadOnly/ShadowOnly/PaperRehearsal
  authority scope；live/tiny-live、margin/options/CFD 與 account-write 仍不可通過。
- 在 `test_stock_etf_lane_source_static.py` 新增 default block parser，鎖住 `StockEtfFeatureFlags` 與
  `StockEtfGateInputs` default fail-closed posture，並鎖住 `evaluate_broker_operation` denial ordering。

驗證：

- Targeted rustfmt check：PASS。
- Stock/ETF lane source static pytest：`8 passed`。
- Stock/ETF lane Rust acceptance：`14 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace pytest：PASS；主計畫與 Operator summary 保持 checkpoint title coverage。
- Diff check：PASS。

PM 邊界不變：此 checkpoint 不改 Rust production code、不改 endpoint/IPC method、不啟動 IPC server、
不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動 connector runtime、不執行 paper order routing、
不做 DB/evidence writer、不啟動 scorecard writer、不做 broker session、不做 broker routing、不做 Linux
runtime sync/restart、不授權 tiny-live/live 或任何 Bybit behavior change。

## 189. 2026-07-01 PM session source checkpoint：Stock/ETF Broker Capability Registry Authority Lineage Cross-Wire Guard

本 checkpoint 補強 `stock_etf_broker_capability_registry` 的 registry identity、StockEtfCash/IBKR lane
separation、Bybit/live/python-write/contact/secret denials、required audit fields、required operation coverage
與 operation row authority/gate/typed-denial/rust/audit/source-artifact shape。這不是 Rust production behavior
change、不是 IPC server start、不是 IBKR contact、不是 connector runtime、不是 secret lookup、不是 paper order
routing、不是 DB/evidence writer、不是 paper order route enablement、不是 tiny-live/live gate；只把 broker
capability registry 的 operation matrix 與 no-live/no-Bybit-crosswire posture 變成 exact-blocker acceptance
test 與 source-static guard。

已完成：

- 在 `stock_etf_broker_capability_registry_acceptance.rs` 新增
  `registry_rejects_each_top_level_gap_independently`。
- Acceptance 證明 registry id/source/lane/broker、Bybit live protection、Python broker write denial、IBKR live
  denial、CFD/margin denial、first-contact denial、secret denial、required audit fields 都會各自只產生單一對應
  blocker。
- 在同檔新增 `registry_rejects_each_operation_coverage_gap_independently`。
- Acceptance 證明 missing operation、duplicated operation 都會各自只產生單一對應 blocker。
- 在同檔新增 `registry_rejects_each_operation_shape_gap_independently`。
- Acceptance 證明 paper submit/live/paper-fill-import rows 的 authority scope、required gates、typed denial、
  rust ownership、audit event、source artifact hash requirements 都會各自只產生單一對應 blocker。
- 在 `test_stock_etf_broker_capability_registry_source_static.py` 新增 required-operations/default/
  accepted-fixture block parsers，鎖住 default fail-closed posture、accepted StockEtfCash/IBKR/no-contact/
  no-secret posture、以及 REQUIRED_OPERATIONS 全矩陣。

驗證：

- Targeted rustfmt check：PASS。
- Broker capability registry source static pytest：`8 passed`。
- Broker capability registry Rust acceptance：`14 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace pytest：PASS；主計畫與 Operator summary 保持 checkpoint title coverage。
- Diff check：PASS。

PM 邊界不變：此 checkpoint 不改 Rust production code、不改 endpoint/IPC method、不啟動 IPC server、
不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動 connector runtime、不執行 paper order routing、
不做 DB/evidence writer、不啟動 scorecard writer、不做 broker session、不做 broker routing、不做 Linux
runtime sync/restart、不授權 tiny-live/live 或任何 Bybit behavior change。

## 190. 2026-07-01 PM session source checkpoint：IBKR Phase 2 Runtime Secret/Topology Exact Default Guard

本 checkpoint 補強 `ibkr_phase2_runtime` 的 secret-slot contract 與 API session topology default
fail-closed posture，固定 default secret-slot blocker 向量、default topology blocker 向量，以及 live
TWS/Gateway port 必須同時被 `LivePortDenied` 與 `PaperPortNotUsed` 拒絕。這不是 Rust production behavior
change、不是 IPC server start、不是 IBKR contact、不是 connector runtime、不是 secret lookup、不是 paper order
routing、不是 DB/evidence writer、不是 paper order route enablement、不是 tiny-live/live gate；只把 Phase 2
runtime evidence 的 secret/topology fail-closed posture 變成 exact-blocker acceptance test 與 source-static
guard。

已完成：

- 在 `ibkr_phase2_runtime_acceptance.rs` 將 default `IbkrSecretSlotContractV1` 檢查提升為完整順序 blocker
  向量。
- 在同檔將 default `IbkrApiSessionTopologyV1` 檢查提升為完整順序 blocker 向量。
- 在同檔將 live TWS/Gateway port topology case 固定為 `LivePortDenied` + `PaperPortNotUsed` 雙 blocker。
- 在 `test_ibkr_phase2_runtime_source_static.py` 新增 fail-closed verdict 與 live-port dual-denial source guard，
  鎖住 secret slot live-secret denial 與 topology live-port/paper-port 雙重拒絕邏輯。

驗證：

- Targeted rustfmt check：PASS。
- IBKR Phase 2 runtime source static pytest：`6 passed`。
- IBKR Phase 2 runtime Rust acceptance：`9 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace pytest：PASS；主計畫與 Operator summary 保持 checkpoint title coverage。
- Diff check：PASS。

PM 邊界不變：此 checkpoint 不改 Rust production code、不改 endpoint/IPC method、不啟動 IPC server、
不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動 connector runtime、不執行 paper order routing、
不做 DB/evidence writer、不啟動 scorecard writer、不做 broker session、不做 broker routing、不做 Linux
runtime sync/restart、不授權 tiny-live/live 或任何 Bybit behavior change。

## 191. 2026-07-01 PM session source checkpoint：IBKR Phase 2 Gate Artifact Exact Lineage Guard

本 checkpoint 補強 `ibkr_phase2_artifact` 的 immutable gate artifact lineage，固定 default artifact
blocker 向量、contract id/source version drift、blocked/retroactive external gate、policy flag mismatch、
runtime evidence mismatch 與 validator blocker ordering。這不是 Rust production behavior change、不是 IPC
server start、不是 IBKR contact、不是 connector runtime、不是 secret lookup、不是 paper order routing、不是
DB/evidence writer、不是 paper order route enablement、不是 tiny-live/live gate；只把 Phase 2 immutable
gate artifact 的 metadata/gate/policy/runtime lineage 變成 exact-blocker acceptance test 與 source-static
guard。

已完成：

- 在 `ibkr_phase2_artifact_acceptance.rs` 將 default `IbkrPhase2GateArtifactV1` 檢查提升為完整順序
  blocker 向量。
- 在同檔將 contract id/source version drift 固定為 exact 雙 blocker。
- 在同檔將 blocked/retroactive external gate、policy flag mismatch、runtime evidence mismatch 固定為
  exact blocker 向量。
- 在 `test_ibkr_phase2_artifact_source_static.py` 新增 validator blocker ordering parser，鎖住 artifact
  validator 的 blocker emit order。

驗證：

- Targeted rustfmt check：PASS。
- IBKR Phase 2 artifact source static pytest：`6 passed`。
- IBKR Phase 2 artifact Rust acceptance：`9 passed`。
- `cargo fmt -p openclaw_types -- --check`：PASS。
- Dynamic docs trace pytest：PASS；主計畫與 Operator summary 保持 checkpoint title coverage。
- Diff check：PASS。

PM 邊界不變：此 checkpoint 不改 Rust production code、不改 endpoint/IPC method、不啟動 IPC server、
不呼叫 IBKR、不導入 IBKR SDK、不讀/建 secret、不啟動 connector runtime、不執行 paper order routing、
不做 DB/evidence writer、不啟動 scorecard writer、不做 broker session、不做 broker routing、不做 Linux
runtime sync/restart、不授權 tiny-live/live 或任何 Bybit behavior change。
