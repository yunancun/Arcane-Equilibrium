STATUS: DONE_WITH_CONCERNS
VERDICT: CONDITIONAL|FINDINGS=5(C:0/H:2/M:3/L:0)

# E5 二輪審計 — IBKR Stock/ETF Paper + Shadow patched plan

日期：2026-06-29
角色：E5(explorer)
範圍：簡化、性能姿態、技術債預防；report-only。未修改 runtime/code/TODO，未觸碰 Linux `trade-core`、PG、services、secrets、network、IBKR 或 Bybit。

## 總結

patched plan 比第一輪方案明顯收斂：它已把 Phase 0 ADR/spec 作為唯一可立即批准範圍，並把 Phase 1+、IBKR API、secret slot、paper order、GUI runtime activation、evidence clock 全部列為 blocked（`docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:14-17`, `:670-707`；PM 整合報告 `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-29--ibkr_stock_etf_plan_adversarial_pm_integration.md:18-27`）。

E5 判斷：可以批准 Phase 0，但不能批准 Phase 1 conditional implementation。剩餘風險不是方向，而是若過早動手，會累積一批淺模塊、半成品 GUI 分路、無容量上限的 market-data tables、以及未來移除困難的 broker lane 腳手架。

## Findings

### H-01 — 模塊清單仍可能被誤讀成可開工拆分，導致淺 abstraction 和 duplicated broker seams

Evidence:
- plan 自己承認第 3 節只是目標模塊拆分，模塊名「還不足以實作」：`docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:84-88`。
- 但同一節仍同時列出 `asset_lane_router`、`lane_scoped_ipc`、`broker_order_lifecycle`、`stock_shadow_engine`、`ibkr_paper_execution_adapter`、Python `asset_lane_routes` / `stock_etf_routes` / `ibkr_paper_routes` / `evidence_routes`：`docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:140-156`, `:177-194`。
- PA 首輪已指出這些是「names rather than Interfaces」，若作 pass-through 會擴散 lane knowledge：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-29--ibkr_stock_etf_plan_pa_review.md:41-43`。

Required resolution:
- Phase 0 ADR/spec 必須新增「module disposition」表：哪些只是 reserved type、哪些是 fixture-only、哪些 defer 到 IBKR API baseline 後。
- Phase 1 禁止同時建立 router、adapter、routes、scorecard writer、GUI views。先落一個最小 lane-scoped Rust command/evidence contract，然後用 fixture 證明 denial/reconstructability。
- 建議重命名以降低誤解：`ibkr_paper_execution_adapter` -> `ibkr_broker_paper_rehearsal_adapter_reserved`；`evidence_routes` -> defer；`asset_lane_routes` 首 slice 只允許 `asset_lane_readiness_routes`。

### H-02 — quotes/bars/orders/scorecards 的 retention、storage、index、compression、容量上限仍未定義

Evidence:
- plan DB 部分仍是 table list + core requirements，沒有 DDL、PK/FK、index、hypertable、chunk interval、compression、retention、raw artifact policy：`docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:221-247`。
- Phase 3 會引入 market data ingestion 與 daily scorecard writer：`docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:551-567`。
- MIT 首輪明確將「plain table vs hypertable for quotes/bars/fills/scorecard rows」列為 Phase 1 blocker：`docs/CCAgentWorkSpace/MIT/workspace/reports/2026-06-29--ibkr_stock_etf_plan_mit_review.md:33-47`，並要求最小 schema 覆蓋 `market.stock_bars` / `market.stock_quotes` provenance、cost model、orders/fills、scorecard derived-only、audit ledger：`docs/CCAgentWorkSpace/MIT/workspace/reports/2026-06-29--ibkr_stock_etf_plan_mit_review.md:282-299`。

Required resolution:
- Phase 1C 之前補 `stock_etf_storage_capacity_v1`：預估 universe size、bar/quote frequency、daily raw rows、retention days、hot/cold split、compression、index budget、query SLO、raw payload hash retention。
- `research.stock_etf_scorecard` 必須明確是 derived/materialized artifact，不得成為 atomic source of truth；重算成本和輸入 hash 必須可追溯。
- 未完成 storage/capacity contract 前，不允許 market-data collector、daily writer 或 DB migration apply。

### M-01 — GUI plan 仍有「first-screen lane selector」與「badge/readiness first」的內部張力

Evidence:
- plan 前段仍寫「GUI 登錄後第一層應明確選擇 asset lane」：`docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:55-63`，並在 GUI section 描述 login-success selector：`docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:305-319`。
- patched Phase 4 又明確改成「第一個 GUI slice 應是 lane badge/readiness page，而不是立即把 login-success selector 作為主流程」：`docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:574-580`。
- PA 首輪也建議從 status badge/filter 開始，避免 selector 看起來像 trading authority：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-29--ibkr_stock_etf_plan_pa_review.md:118-130`。

Required resolution:
- Phase 0 將 GUI 順序寫死：Phase 4A = badge/readiness/status-only；Phase 4B = stock read-only views；Phase 4C 才能討論 login selector。
- 刪除或標註前段「第一層 selector」為 future/deferred wording，避免 E1/A3 依早段文字做主流程 churn。
- Disabled `cfd_margin` 不應進首屏；只在 denial fixtures/status matrix 中保留。

### M-02 — kill/disable cleanup 只有結果標籤，沒有可逆移除 runbook

Evidence:
- plan 結果標籤包含 `kill`：`docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:462-469`。
- 6-8 週後若無 edge，只寫「關閉或降級 stock/ETF lane」：`docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:653-658`。
- 沒有定義如何證明回到 no-stock state、如何處理 flags、routes、GUI badge、secret slots、DB tables、audit artifacts、cron/collector、docs/index。

Required resolution:
- Phase 0 加 `stock_etf_disable_cleanup_runbook_v1` 作 blocker：關閉 flags、證明 live/paper secret absent/empty、停止 collectors、隱藏 GUI surfaces、保留/封存 evidence、禁止 dead routes 被默默留用。
- DB 需定義 forward-only retention vs removable fixture tables；若 migration 不可 rollback，也要有 `lane_disabled` read path 和 no-writer proof。
- 每個新增模塊必須有 owning phase 和 disable behavior；沒有 cleanup owner 的模塊不得落地。

### M-03 — `cfd_margin`、UCITS、廣義 calendar/cost/risk taxonomy 仍有前置過度建模風險

Evidence:
- plan 在首批 lane 表展示 `cfd_margin` disabled：`docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:57-63`，並在 types 中預留 `CfdMargin` / `CfdReserved`：`docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:94-98`。
- 初始 universe 同時提 UCITS 作第二批，但仍列出 PRIIPs/KID、UCITS、TER/domicile 類需求：`docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:389-397`。
- `openclaw_core::calendar`、`cost_model::ibkr`、`stock_etf_risk` 均被列為 core modules：`docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:107-123`；PA 首輪已提醒 broad calendar / taxonomy / risk placement 容易變成 shallow module：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-29--ibkr_stock_etf_plan_pa_review.md:185-195`。

Required resolution:
- Phase 1A 僅保留最小 denied enum / negative tests；不要顯示或 route `cfd_margin`。
- 第一批只建 US stock/ETF 所需 identity/cost/calendar fields；UCITS/PRIIPs/withholding/TER 等放 Phase 3+ data-contract appendix，不進第一批 core type。
- `stock_etf_risk` 先做 pure predicates + typed denial reasons；runtime admission/gate 狀態留在 `openclaw_engine`，避免 core module 提前吞掉運行語義。

## Planned Module Disposition

| 模塊 / surface | E5 建議 |
|---|---|
| `asset_lane_router` | defer；Phase 1 只做 typed denial/readiness，不做通用 runtime router。 |
| `lane_scoped_ipc` | narrow；只定義一個 Rust-owned command/evidence contract + negative tests，無 IBKR connector。 |
| `broker_order_lifecycle` | rename/narrow 為 `ibkr_broker_paper_lifecycle_v1` spec；先 state-machine + fixtures。 |
| `stock_shadow_engine` | defer 到 market-data/cost/benchmark contracts 完成後；先做 deterministic fixture fill model。 |
| `ibkr_paper_execution_adapter` | defer 到 Phase 2B+；名稱加入 `broker_paper_rehearsal`，避免和 legacy Paper/live 混淆。 |
| Python `paper_client.py` | rename or split：`readonly_client.py` + `fill_import_client.py`；不得含 broker write methods。 |
| `evidence_routes.py` | defer；先產出 offline artifact / status endpoint，避免泛化 cross-lane evidence route。 |
| GUI login lane selector | defer；先 lane badge/readiness page。 |
| `openclaw_core::calendar` | narrow to stock market-session contract used by evidence clock/risk only。 |
| `cfd_margin` surface | remove from first GUI slice；只保留 fail-closed tests。 |

## Minimal Phase Sequence

1. Phase 0: ADR/AMD/spec only；接受 `stock_etf_cash` read-only/paper/shadow research boundary，禁止 live/margin/short/options/CFD/transfer。
2. Phase 0 addenda: `stock_etf_disable_cleanup_runbook_v1`、`stock_etf_storage_capacity_v1`、API/session baseline、feature/secret invariant matrix。
3. Phase 1A: Rust minimal type reservation + denied-state tests only。
4. Phase 1B: flag/readiness parser + status contract，全部 default OFF；不轉發任何 order-capable action。
5. Phase 1C: DDL/evidence contract + Linux dry-run packet；無 migration apply，無 collector。
6. Phase 1D: lane-scoped Rust IPC/order-lifecycle Interface + fixtures；無 IBKR connector。
7. Phase 2A: Python fixtures/read-only status only；no-write static tests。
8. Phase 2B: E3-approved IBKR read-only health/account/session observation；仍無 paper order。
9. Phase 3: shadow collector + scorecard only after vendor/tier/PIT universe/corporate-action/cost/benchmark/storage contracts are machine-checkable。
10. Phase 4A: GUI badge/readiness/status-only；full selector/views later。
11. Phase 5: evidence clock only after manifest, retention/capacity, scorecard reproducibility, and cleanup runbook are green。

## Gate Answer

- planned modules: defer or narrow most modules; only ADR/spec, minimal types, denial tests, flag/readiness, DDL contract, and lane IPC spec should precede any IBKR connectivity。
- GUI: first-screen lane selector is still too much churn; patched badge/readiness-first wording should become the sole accepted order。
- storage/performance: not addressed enough; must define hypertable/retention/compression/index/capacity before collector/writer。
- kill/cleanup: not defined; must be a Phase 0 blocker before any module lands。
- minimal method: approve Phase 0 only, then fixture/spec slices; no runtime connector until contracts are testable。

PM-facing gate decision: APPROVE_PHASE0_ONLY
