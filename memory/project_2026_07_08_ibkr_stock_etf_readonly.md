---
name: project_2026_07_08_ibkr_stock_etf_readonly
description: "首個非-Bybit 資產類:美股/ETF via IBKR,stock_etf_cash lane(ADR-0048);AMD-2026-07-08-01 授權 Phase2 read-only 外接(Rust-owned TWS client loopback:4002 paper);live/order 永久 DENIED,Bybit path 不變,lane dormant"
metadata:
  node_type: memory
  heat: 0
  type: project
  originSessionId: b8f94432-3891-440a-ba13-f17896dd26d5
---

TradeBot 的**首個非-Bybit 資產類**——美股/ETF via Interactive Brokers,走 `stock_etf_cash` 研究 lane。這是 memory 先前完全缺失的 scope(索引一直隱含 Bybit-crypto-only)。CLAUDE.md §一 已收錄:Bybit 仍是唯一 active live 執行所;例外=Binance market-data-only(ADR-0033/0040)與 IBKR `stock_etf_cash` read-only/paper/shadow(ADR-0048 + AMD-2026-06-29-01),Phase 2 read-only 外接經 AMD-2026-07-08-01 授權。承 [[project_openclaw_positioning]](補其非-Bybit 資產軸)。

**治理**:`docs/governance_dev/amendments/2026-07-08--AMD-2026-07-08-01-ibkr-phase2-external-contact-readonly.md`,Status=**Active - Phase 2 read-only external-contact authorization**。授權單一 Rust-owned 模組(在 `openclaw_engine`)講 read-only 子集的原生 TWS wire protocol(reqCurrentTime/reqAccountSummary/reqPositions/reqContractDetails/reqMktData snapshot),只連 **IB Gateway paper mode loopback `127.0.0.1:4002`**。Python 只 expose read-only status + thin Rust IPC caller。

**代碼面**:~35 個 `rust/openclaw_types/src/{ibkr_*,stock_etf_*}.rs` 型別/契約檔(6/30-7/1 建)+ source-only Python skeleton `program_code/broker_connectors/ibkr_connector/`(README 明言「**not a runtime IBKR connector**」,ADR-0048 source-only boundary,display-only + fixtures;SDK import/socket/secret/write 全 DENIED)。`stock_etf_account_normalizers.py` 是 negative-space attestation gate:現在把**任何** populated value 都標 `contract_violation`,Phase 2 啟用時須與 Rust emitter 在**同一 PR** lockstep 演進。

**現狀=G0.5 + P0 landed(僅 Mac-verified);P1 next;live/order 永久 DENIED;lane dormant**:
- AMD 2026-07-08 accepted(`fae556847`);precondition=`CERTIFIABLE_IF_GATES_PASS`。
- G0.5 `stock-etf-static-guards` CI job 綠(25 guard tests)+ GUI fake-$0 誠實 fix(`0ce7534a3`)。
- P0 risk-TOML→Rust wiring landed `c66338e8b`(碰 `ipc_server/handlers/stock_etf.rs`+engine crate),使 displayed cap=enforced source-of-record;**E2 APPROVE-on-correctness 但 UNVERIFIED(無 Mac cargo);Linux `cargo test -p openclaw_engine stock_etf` 待跑**。
- lane dormant:`settings/risk_control_rules/risk_config_stock_etf_paper.toml` → `enabled = false`,`shadow_only = true`(已驗)。

**永不鬆動的 invariant**:IBKR live/tiny-live 一律 DENIED(不建 live gate);零真錢;任何 order-write(含 paper order)禁;live secret slot 必須缺席;**Bybit `crypto_perp` live path 不變**;Python 保持 display-only。

**How to apply**:別把 IBKR 當交易軸——它是 read-only/shadow 研究 lane,ADR-0048 明禁 auto-promote 到 tiny-live/live/durable-alpha proof。下一步 P1=fingerprint-only secret-slot loader(tech design 已草 `2026-07-09--ibkr_p1_secret_slot_loader_tech_design.md`);**首次真實外接需 operator 一次性明確批准 @ gate G4 + BB + E3**。SHA `fae556847`。

## 演變軌跡(append-only;被推翻結論留原文)

- **2026-07-09**:P1 loader `3217e94b4`/P2 gate producer `b89c7b2d8`/B1 readonly client `aedca2291` 全 landed + 引擎 rebuild 部署(`26401fbb`)——上文「P1 next/Linux cargo 待跑」失效。
- **2026-07-11(AMD-2026-07-11-01 Accepted)**:「live/tiny-live 永久 DENIED、不建 live gate、任何 order-write(含 paper)禁」**僅在活化維度存續**;capability development 全授權(readonly/paper/shadow/tiny-live/live 全模式 no-contact 開發)。任何真實接觸(含 readonly)需 Rust 驗證 `ibkr_activation_envelope_v1`+authenticated Operator 活化紀錄;margin/short/options/cfd/transfer 永久 denied 不變。AMD-2026-07-09-01(GUI 憑證寫路徑)acceptance 前廢止。
- **2026-07-15~16(W2-W4+W-CI 收口)**:normalizer「任何真值=violation」已演進為三層 lockstep(W4);G4 一次性批准語義被 EA3(envelope+活化紀錄)吸收;工程正本=repo 根 `IBKR_TODO.md`(v2)+loop `docs/agents/ibkr-live-capability-loop.md`(v2)+帳本 PROGRESS.md,本檔僅史料。
