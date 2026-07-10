# AMD-2026-07-10-02：ALR Freshness and Learning Completion V3

Date: 2026-07-10
Status: Accepted
Related ADRs: ADR-0017, ADR-0035, ADR-0049
Supersedes for completion truth only: AMD-2026-07-09-02 P2-8 / P3 terminal interpretation

## Decision

Operator 以 `ALR_FRESHNESS_AND_LEARNING_COMPLETION_V3` 明確重開 `P2-ALR-OPERATIONAL-SHADOW-V1/P2-8`。既有 `DONE_OPERATIONAL_SHADOW` 因 steady-state fresh ingestion 曾被實測證偽，不再是有效 terminal state。AMD-2026-07-09-02 與 P2 queue v1 保留為歷史授權及當時證據；本修訂只取代其 freshness、learning、retention 與 completion acceptance truth，不擴張任何交易權限。

本修訂授權在原 P2 shadow 邊界內完成 ALR consumer/repository/health/tests、必要的 `learning.alr_*` migration、user-service source/template、Mac 測試、隔離 PostgreSQL 測試、Linux read-only 核驗，以及經 fresh exact-scope `PM -> E3 -> BB -> PM` gate 後的原子部署與 ALR-only service restart。任何 Rust notifier source 變更仍須先通過 Mac Rust tests，再由 PM-owned atomic deploy 路徑處理；delegated role 不得在 Linux 執行 Cargo。

## Fresh-Lane Contract

1. 每個 notification 必須以完整 `(scan_id, ts)` identity 精確消費；notification 只可作為 wake/identity，不是 scanner payload、proof、reward 或交易指令。
2. coalesced 或 missed notification 必須由 durable live watermark 的 bounded catch-up 補齊。正常 steady state 不得依賴臨時 `ALR_RECONCILE_AFTER`、systemd drop-in 或手工 cursor。
3. fresh/live lane 與 historical backfill lane 必須使用獨立、持久化的 cursor/state。fresh lane 每輪優先；history 只能低優先級、有限額執行，且不得阻塞、倒退或冒充 fresh progress。
4. `(scan_id, ts)` ledger identity、canonical source hash 與 append-only lineage 必須提供 idempotency；duplicate、late、out-of-order 與 crash replay 不得靜默改寫 source evidence。

## Truthful Health Contract

ALR health 必須持久化並如實暴露：

- `raw_latest_ts`
- `alr_latest_source_ts`
- `ingest_lag_seconds`
- `fresh_raw_only_count`
- `historical_backfill_remaining`
- `notifications_received`
- `notifications_consumed`
- `notifications_invalid`
- `last_success_at`
- 真實 failure/restart counters

不得把 untrained backlog 當作 raw-to-ALR ingestion backlog，不得硬編碼零 failure/restart，也不得用 service active 或歷史資料 run 冒充 freshness。

## Adversarial And Runtime Acceptance

V3 acceptance 必須同時證明：

- 79k historical backlog 加一個 fresh notification 時，新 identity 在該輪優先入帳；
- duplicate、out-of-order、late、coalesced/missed notification、crash/restart、durable watermark recovery 與 concurrent single-instance 均 fail-closed 或正確恢復；
- 人工 raw-only gap 會令 health 告警，scanner source 仍為 SELECT-only，所有 authority maps/counters 保持 false/zero；
- 不使用 temporary cursor/drop-in，連續至少十個自然 Rust scanner cycles 達成 bounded-latency raw/ALR identity equality、`fresh_raw_only_count=0`、duplicate `0`、`alr_latest_source_ts` 持續前進；
- acceptance window 內只重啟一次 ALR service 並證明 cursor/recovery；不得為此重啟 engine；任何 soak failure 都必須 RCA、修復並重新計完整十-cycle window。

## Qualified Learning Contract

Scanner 只可選擇 research object。label/reward 必須完整 candidate-match，並串接 point-in-time manifest、`proof_packet_v1`、`reward_ledger_v1`、actual fee/slippage/funding、order-to-fill reconstruction 與 after-cost label。訓練/evaluation 必須使用 walk-forward、purge/embargo、OOS、matched controls、negative cells 與完整 lineage。

- 有合格資料時必須實際執行 training/evaluation，並如實記錄 `model_training_performed=true`。
- 無合格資料時必須記錄缺口及 `model_training_performed=false`；單一 target 的 `DEFER_EVIDENCE` 必須自動輪換，不能停止全局 loop。
- 任何輸出只可成為 challenger；不得自動 serving、promotion 或覆寫 `_latest`。

## Retention Contract

Retention 只可對 ALR-owned、rebuildable、unreferenced derived cache 執行 `reference graph -> quarantine -> grace/recheck -> sweep`。production 無 eligible cache 時，唯一 truthful state 是 `NOT_EXERCISED_NO_ELIGIBLE_CACHE`；不得虛構 delete/sweep。若未來實際 training 產生 eligible cache，才可在 fresh gate 下執行受控 retention，並重新驗證 protected evidence 與 lineage 未受損。

## Terminal State And Exact Packet Binding

正常完成狀態只有 `DONE_FRESH_OPERATIONAL_LEARNING_SHADOW`，且須同時滿足 fresh/backfill separation、truthful health、adversarial tests、十-cycle natural soak、ALR-only restart recovery、qualified training/evaluation、feedback、retention、lineage、authority audit 與三端 source/runtime alignment。

若已證明所有安全資料來源均無法形成 qualified candidate-matched label，允許的替代 terminal state 只有 `WAIT_OPERATOR_DEMO_AUTH_EXACT`。目前替代 gate 綁定以下 immutable packet：

- Path: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-10--alr_f5_exact_demo_authorization_packet.json`
- SHA-256: `1ab349a6f753e4d3846b0699d7404f18e231d8ca95b8f250bb19b9f89b7eabde`
- Packet status: `EXACT_DEMO_AUTHORIZATION_PACKET_READY_UNAUTHORIZED`
- Candidate: `grid_trading|SUIUSDT|Sell`
- Operator authorization: `false`
- Execution performed: `false`
- E3/BB hash-bound reviews: approved for Operator decision only

該 packet 是可執行規格但仍未授權；它不等於 order、probe、cancel、close、Decision Lease、exchange contact 或 Demo execution authority。任何內容、candidate、source/runtime head、instrument、RiskConfig lineage 或 packet bytes 改變都必須 ROTATE、重算 SHA 並重新取得 E3/BB 與 Operator 對同一 SHA 的明確批准。歷史 NEAR candidate 與 generic/standing request 不得替代此 exact packet。

## Hard Boundaries Retained

- ALR 不得主動呼叫 Bybit REST/WS 或 official MCP；不得執行 order/probe/cancel/modify/close。
- 不得進入 live/mainnet，不得修改 Guardian、RiskConfig、order dispatch、Decision Lease policy 或 global Cost Gate。
- Decision Lease requirement 是未來 exact Demo admission 的必要條件，不是本修訂或 packet 所授予的 authority。
- Scanner score/registry/snapshot 不得成為 proof、reward 或交易權限。
- 不得自動 serving/promotion、覆寫 `_latest`，或從 no-fill、scanner、artifact count 推導 profit/edge。
- 不得刪除 fills/orders/fees/slippage、proof/dispute、negative/control/OOS、audit、authorization、risk、reconciliation 或 lineage evidence。
- 所有 exchange、trading、order/probe、Decision Lease、Cost Gate、proof、serving、promotion 與 `_latest` authority maps/counters 必須保持 false/zero。

## Sign-off

| Role | Status | Basis |
|---|---|---|
| Operator | Accepted governance scope; exact Demo execution not authorized | `ALR_FRESHNESS_AND_LEARNING_COMPLETION_V3`; packet authorization remains false |
| PM | Active / terminal truth owner | V3 queue and immutable packet binding |
| CC / FA / PA | Required in V3 compliance chain | Root-principle, functional-gap, and design acceptance |
| E3 / BB | Runtime gate complete; exact packet approved for Operator decision only | Reviews are bound to packet SHA `1ab349a6...abde`; neither review is Operator authority |
