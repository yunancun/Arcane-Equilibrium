# IBKR_TODO — `stock_etf_cash` 到 live-ready 工程總綱

**版本** v2 | **日期** 2026-07-16 | **正本** repo 根目錄 `IBKR_TODO.md`(main 分支;外層 `~/Projects/TradeBot/IBKR_TODO.md` 為鏡像副本,以 main 為準)
**v2 校準 lineage**:2026-07-16 R8 全盤校準——對 W2/W-CI/W3/W4 完成件做 8 鏡頭對抗審計(workflow `wf_c316991f`):W2/W3/W4 逐項 **CONFIRMED_AS_CLAIMED**(INV-1 二元 HOLDS:production 域唯一 `impl ConnectPermitProvider`=`EnvelopeRequiredStub`、`PermitToken::mint` production 呼叫點=0),全測試鏈本地複現全綠(engine ibkr 211/types 74+287/stock_etf 34/seal 2/fake 9/Python 201);§0/§4 重釘 @ `808144aff`;審計揭 CI 守衛鏈 3 MEDIUM 殘洞(§4.5)歸 W5-S0(R9)收口。
**性質**:工程設計總綱(engineering arrangement)。**本文件不是授權文件**——任何真實 broker 接觸/資料/訂單效果仍由 AMD-2026-07-11-01 定義的 `ibkr_activation_envelope_v1` + Operator 活化紀錄單獨把關。
**與 TODO.md 的關係**:`TODO.md` 是 active dispatch queue 唯一正本(W0-W11 行狀態以它為準);本文件是 W 包的工程設計展開 + 活化跑道設計,派工時兩者並讀。W 狀態變更只改 TODO.md,設計變更才改本文件。
**評審 lineage**:IB(explorer)對抗審 2026-07-15 verdict `APPROVE_WITH_FIXES`,F1(BLOCKER)-F17 全數採納入文;外部政策事實 8 條經官方文件現勘裁定(pacing=lines÷2、週日強制重認證、行情共享互斥等),UNVERIFIED 項(GFV 執行機制、paper 2FA 適用性)已標注為 PA/IB 設計期硬前置。

---

## 0. 一頁摘要

- **目標終態(工程側)**:`IBKR_FULL_LIVE_CAPABILITY_COMPLETE_EXTERNAL_ACTIVATION_PENDING`——所有 no-contact 源碼、production wiring、測試、GUI、inactive 部署、恢復、文檔、三端同步、gap matrix 全 PASS,只剩人工憑證/session/活化與真實回執未決。這就是本文件說的 **live-ready**。
- **最終驗證終態(活化側)**:`IBKR_FULL_LIVE_READY_VERIFIED`——Operator 單獨授權的 live session + 活化後,由 IB/E3/OPS/QA 出具 health/account/market/lifecycle/money-boundary 實證。
- **現況一句話(2026-07-16 R8 校準)**:治理全解鎖(AMD-2026-07-11-01 Accepted);**W0/W1/W2(DONE_SOURCE_SECURED_HARDENED,PR#28)/W-CI(DONE_LANDED_FIRST_GREEN,PR#21)/W3(DONE_SOURCE_SECURED,S1-S4,PR#32/#33/#35/#38)/W4(DONE_SOURCE_SECURED,W4-1,PR#40)全收口且經 R8 對抗審計 CONFIRMED**;型別契約陣 34 modules/37 acceptance 檔;**W5 為下一包(S0 blocking 前綴必修)**,W6-W11 QUEUED。runtime 側教科書式 dormant(07-16 復核):lane 旗標全 false、IB Gateway 未安裝、零 ibkr secret slot、production 從未 seal——**從未發生任何真實接觸**。
- **路徑一句話**:剩 W5→W11 七包(+W8a/W9a carve)把引擎從「session/health 骨架」補成「全生命週期 live-capable 但 default-inactive」;之後 EA1→EA8 活化跑道(全 Operator-gated)按 readonly→paper→evidence clock→tiny-live→live 逐級點火。W8a/W9a 為純 no-contact 開發(AMD-07-11 授權內),先行落地使 EA1-EA3 在 Operator 就緒時零等待點火;EA 時序決策(D2)不因此預決。
- **最大 wall-clock 項**:paper/shadow evidence clock(ADR-0048 預期 6-8 週)——工程全部完工也繞不開這段證據窗;故 ①W5 收口後即帶 W8a/W9a,使唯讀跑道(EA1-EA4,7-14 天 soak,**若 Operator 採 D2**)可與 W6/W7 開發平行,②**W7+W8 收口後**盡早申請 EA5 開 paper 窗(硬前置 = W7+W8 全綠 + option B 落地),與 W9-W11 的非授權面平行推進(見 §5.5/§6)。

## 1. 終態定義:什麼叫 live-ready

AMD-2026-07-11-01 只允許三種終態(引自 §Required implementation and evidence posture):

| 終態 | 條件 | 本文件對應 |
|---|---|---|
| `IBKR_FULL_LIVE_CAPABILITY_COMPLETE_EXTERNAL_ACTIVATION_PENDING` | 每一項 no-contact source/production-wiring/test/GUI/inactive-deployment/recovery/documentation/synchronization/gap-matrix 項目 PASS;僅剩人工憑證/session/活化與真實回執 pending | **W2→W11 全部收口 = live-ready** |
| `IBKR_FULL_LIVE_READY_VERIFIED` | 單獨授權的 live session + 活化產生 IB/E3/OPS/QA attested 的 health/account/market/lifecycle/money-boundary 證據 | **EA 跑道走完** |
| `HARD_BLOCKED_OPERATOR_DECISION_REQUIRED` | 僅限新產品/資金/法務衝突;**缺憑證/session/Gateway/市場開盤永遠不算 HARD_BLOCKED**,記 `EXTERNAL_VERIFICATION_PENDING` 繼續其餘工作 | 異常出口 |

判定紀律:缺外部件(憑證/session/entitlement/開市/live 批准)只 block 對應的真實接觸驗證,**永不 block 其餘源碼/fake-TWS/GUI/部署/恢復/文檔工作**。

## 2. 權威鏈與不可動邊界

**權威鏈(normative,新者優先於衝突舊文)**:
1. `AMD-2026-07-11-01`(Accepted 2026-07-11)——full live-capability **development** 授權 + 活化分離。壓倒 ADR-0048/AMD-06-29-01/AMD-07-08-01 中衝突的 capability-development 禁令;其餘(lane 隔離、Rust authority、fail-closed、audit、非 IBKR 邊界)原樣有效。AMD-2026-07-09-01(GUI 憑證寫路徑)**acceptance 前被廢止,無任何獨立效力**。
2. `AMD-2026-07-08-01`(部分被壓倒,歷史 Phase 2 授權保留)——static-guard 邊界唯一修訂(engine 內單一 Rust read-only TWS client)、secret slot 語義(`OPENCLAW_SECRETS_ROOT` locator)、P2 seal 批准模型(option A 6-binding)與 **HMAC 升級觸發器**。
3. `ADR-0048`(accepted_amended_in_part)——lane taxonomy(closed enums)、named-contract gate 陣、Denied Paths、Phase 0-5 語義。
4. `CLAUDE.md` §邊界行、`TODO.md`(active state 正本)。

**永久 denied(本 lane,任何 W 包不得觸碰)**:`margin` / `short` / `options` / `cfd` / `transfer` / account-management writes;Python/FastAPI/GUI 成為 order/risk/activation authority;GUI/client 狀態當授權;credential/activation-secret 明文進入 Python/IPC/DB/log;env-var credential fallback;繞過或削弱 Guardian/Decision Lease/global Cost Gate/idempotency/fingerprint/audit/limits/kill switch;降低 global Cost Gate;fake-success(fabricated 帳戶/行情/訂單資料、`allow(dead_code)` 藏 caller)。

**活化鐵律(每個真實接觸模式都適用,含 readonly 與 paper)**:真實接觸前必須有 Rust 驗證的 `ibkr_activation_envelope_v1`,綁定 lane/broker/environment/operation scope、`BUILD_GIT_SHA`、account fingerprint、Gateway/session attestation fingerprint、risk-config hash + limits、global Cost Gate/Guardian/Decision Lease lineage、Operator identity、activation nonce(原子消費、防 replay)、issued-at/expiry、revocation epoch、kill-switch epoch。reconnect 或 scope 變更 = 重新活化。**每個真實接觸模式(含 readonly/paper)都需 Rust 驗證的 authenticated Operator 活化紀錄支撐 envelope**;tiny-live/live 額外要求顯式、限時、commit/account/session-bound、精確到操作範圍。憑證/slot/session 存在**永不**自動活化任何模式。

**跨 lane 鐵律**:Bybit `crypto_perp` 是唯一現行 active live venue;每個 gate 都要 bybit-live-unchanged 證明;不得復用 Bybit paper IPC 路徑;BB 證據不能替 IB gate(reviewer 用 IB agent)。

## 3. 狀態梯度詞彙(申報紀律)

所有 W 包驗收與 status 報告必須用以下梯度精確申報,禁止「done」混稱(教訓:2026-07-09 QA 誠實校正——P1 loader/B1 曾被誤稱 GUI-wired):

`source-ready`(源碼+測試綠,未接線)→ `external-gate-ready`(sealed gate artifact 可產,未接觸)→ `session-ready`(Gateway session 建立,fingerprint 驗過)→ `entitlement-ready`(行情權限狀態確認)→ `runtime-active`(engine 在跑該能力,inactive≠active)→ `effect-authorized`(envelope 驗過、允許產生效果)→ `evidence-producing`(真實證據落地)。

W2-W11 的全部 DoD 都封頂在 `source-ready` + `runtime-active(inactive posture)`;`session-ready` 起全部屬於 EA 跑道。

## 4. As-built 現狀盤點(2026-07-16 R8 校準,main @ `808144aff`)

### 4.1 治理/gate 現狀

| 項 | 狀態 | 證據 |
|---|---|---|
| AMD-2026-07-11-01 full live-capability development | **Accepted** | `ebb94d730`;W0 行 DONE_POLICY_ACCEPTED |
| AMD-2026-07-08-01 Phase 2 readonly 外接 + static-guard 唯一修訂 | Accepted(部分被 07-11 壓倒) | 文件 §Sign-off |
| AMD-2026-07-09-01 GUI 憑證寫路徑 | **廢止(acceptance 前 superseded)** | AMD-07-11 §Supersession |
| G0.5 `stock-etf-static-guards` CI job | 綠 | AMD-07-08 前置,已 wired |
| P2 seal 批准模型 | option A(owner-only 檔案 + 6 bindings)僅限 read-only zero-money seal;**任何 paper order-write / `tiny_live_adr_eligibility_v1` 討論 / 資本暴露面必須升級 option B(HMAC,與 authorization.json 同紀律)**(觸發器三項照抄原文);**澄清 #3(2026-07-15,CC 裁)**:控制批准綁定=`ibkr_phase2_seal_control_v1 ∧ authorization_amd==AMD-2026-07-11-01`,ADR/AMD 出典由 artifact 層硬 pin;EA3 每次 apply 前歸檔該次批准檔精確位元組 | AMD-07-08 澄清 #2/#3 |
| P2 waiver-gated 硬阻塞票 T1(seal-lineage-fields)/T2(triangulation-crosscheck) | **CLOSED** | `58d0e9749` + `0bafe2f9e` |
| Phase2 seal 生命週期(Seal genesis→Supersede→Revoke terminal per build SHA;pre-write guard 防 reseal-after-revoke brick) | source-landed + 回歸測試 | `324fb87a8` `7902efe71`,ADR-0048 §Phase 2 |
| W1 sealed-artifact production consume 硬化(euid 0400、inode-bound traversal、anti-relocation、FIFO-safe open) | DONE_SOURCE_SECURED | TODO W1 行;`c082bc569` |
| managedAccounts prefix-only paper attestation(seam#2,fail-closed) | source-landed | `c4b52c2e2`;W5 有 2026-07-12 驗收附註:`account_fingerprint_is_live` 必須 managedAccounts 實檢派生,禁聲明自填 |

### 4.2 代碼現狀(引擎/Python/GUI/DB;2026-07-16 盤點 @ main `808144aff`)

**Rust 契約層 `rust/openclaw_types/`**:34 個 ibkr/stock_etf module(W3/W4 新增 `ibkr_tws_session_state.rs`/`ibkr_tws_connection_health.rs`)+ 37 個 acceptance 測試檔(~16.8k 行)——phase2 gate/artifact/policies/runtime、feature-flag secret-auth matrix、非-Bybit API allowlist(9 read action)、readonly probe request(9 probe KIND)、probe result import envelope、paper lifecycle 狀態機契約、lane/capability registry、lane-scoped IPC、risk policy、scorecard 三件套、instrument identity/PIT universe/reference data/strategy hypothesis/phase3 evidence/DDL 鏡射/audit events/disable-cleanup runbook/tiny-live eligibility/gui lane contract/release packet/phase0 manifest。**named-contract 陣的型別層基本齊裝**;`IbkrSessionAttestationV1` 型別已定義但 runtime 產生器未落地(歸 W5)。

**Rust 引擎層 `rust/openclaw_engine/src/`**:

| 模組 | 量級 | 狀態 |
|---|---|---|
| `ibkr_phase2_gate_producer.rs` | ~5.1k 行 | P2 producer + **W2 seal/supersede/revoke ledger 全鏈**(append-only hash chain、flock+dirfd、ledger replay 驗證、reseal-after-revoke pre-write guard)+ **R2 加固**(expiry 只約束 active leaf、/run 族 denylist、相對路徑拒絕、readdir errno fail-closed、anti-placeholder)+ 55 in-file 測試(47+8,R8 實數) |
| `ibkr_tws_wire.rs` + `ibkr_tws_session.rs` + `ibkr_tws_pacing.rs` | ~2.4k 行 | **W3**:framing/版本協商/`IbErrorClass`+六態 FSM(退避 jitter/心跳/chrono-tz 排程感知)+INV-1 permit stub(恆拒)+pacing governor(lines÷2 bucket/historical 四規則/有界排隊/`OutboundGrant` module-private 單一出口) |
| `ibkr_tws_driver.rs` | ~0.7k 行 | W3-S4 端到端泛型 driver(`SessionDriver<P: ConnectPermitProvider, F>`);production 整面 DCE,`ibkr_driver_absence_audit.sh` nm 斷言在 CI 把關 |
| `rust/openclaw_fake_tws/` | dev-crate | W3-S4 fake-TWS(15 場景+故障注入);dev-dependency only,production 零 fake 符號(nm audit 入 CI) |
| `ibkr_readonly_tws_client.rs` | ~1.4k 行 | B1:純 codec + 泛型 driver(handshake+`reqCurrentTime`)+ `assert_loopback_paper_endpoint`(硬編 `127.0.0.1:4002`,4001/7496 硬拒)+ `g4_operator_triggered_first_contact`(唯一 `TcpStream::connect`,`ibkr_g4_contact` feature-gate;**default build 零 socket 符號**);26 測試(tokio duplex synthetic frames) |
| `ibkr_secret_slot_loader.rs` | ~0.8k 行 | P1 fingerprint-only loader;**scaffold(檔級 `allow(dead_code)`,無 production 讀者;TODO(P5) 接 attestation/healthcheck)**;18 測試 |
| `ipc_server/handlers/stock_etf.rs`(779 行,PR#42 拆檔後<800)+ `stock_etf/` 子目錄(health_summary/precontact/summaries) | ~3k 行 | **17** 個 `stock_etf.get_*` 唯讀 IPC method(W4 +`get_connection_health`;零 mutate verb)+ fixtures |
| `bin/ibkr_phase2_seal.rs` | 111 行 | W2 seal CLI:default dry-run;`--apply` + `OPENCLAW_IBKR_PHASE2_SEAL_APPLY=1` 雙閘 |
| `bin/ibkr_g4_first_contact.rs` | 53 行 | G4 CLI 薄殼(`required-features=ibkr_g4_contact` + `OPENCLAW_IBKR_G4_CONTACT_APPLY=1`,default dry-run) |

**Python/FastAPI**:17 條 `/api/v1/stock-etf/*` **全 GET 唯讀** route(W4 +`/connection-health`;lane/phase0/readiness/data-foundation/policy/authorization/account/evidence/universe/shadow/paper/reconciliation/scorecard/launch/release-packet/disable-cleanup)+ 17 個 normalizer 檔(負空間 attestation 態;W4 起 connection-health 面演進為三層 lockstep);`broker_connectors/ibkr_connector/` 維持 inert no-network placeholder;52 個 `tests/structure/` 靜態守衛(no-write AST、route guard、live-port reject、cross-surface parity、permit-stub INV-1、fake dev-dep-only、拆檔守衛、authority artifact 覆蓋)。

**GUI**:`tab-stock-etf.*` 容器 + 10 個子視圖(readiness/auth-account/data-policy/evidence-paper/reconciliation/scorecard-launch/release-packet/disable-cleanup/phase0/fallbacks),已隨 GUI 大改遷入原生 view(13/19 之一)——**唯讀顯示面已相當完整,等真值接通(Phase 4 gate)**。

**DB**:DDL source-only(387 行 SQL,13 表:`broker.instruments/instrument_listings/market_sessions/corporate_actions/fx_rates/account_cash_ledger/paper_orders/paper_fills/commissions`、`research.stock_shadow_signals/stock_shadow_fills/stock_etf_scorecard`、`audit.asset_lane_events`)+ 型別鏡射;`sql/migrations/` 零 stock_etf migration。

**確認缺席(對應 §4.4)**:`ibkr_activation_envelope_v1` struct/impl(代碼中僅字串 placeholder;歸 W8a/W8)、S3/S5 typed row payload(僅 probe KIND + digest envelope;歸 W5)、entitlement 邏輯(W6)、runtime attestation/audit 產生器(W5/W8)、憑證寫路徑(隨 AMD-07-09-01 廢止,零代碼,**維持缺席**)。~~persistent session manager/fake-TWS server~~ 已由 W3 交付。

**CI 現狀(W-CI 已收口 2026-07-15,PR#21 `48872c4fa`)**:`rust-ibkr-tests` job(五 scope=types 74+287/engine ibkr/stock_etf/seal bin/g4 audit,warm ~7-8m)+ W3/W4 追加 permit-stub、fake dev-dep-only、fake 缺席 nm、driver-absence 四守衛入 CI;結構守衛+classifier 擴 6 prefix 接 hosted CI(PR#42 `275c76c59`)。**R8 審計揭 3 MEDIUM 殘洞(歸 W5-S0/R9,詳 §4.5)**:①三個 `helper_scripts/ci/ibkr_*.sh` 審計腳本自身路徑不在 changes classifier(只改腳本的 PR 靜默 skip 本 job);②`rust-ibkr-tests` job 未被無條件 workflow static test 釘住(整 job 可被刪而靜默過);③W4 lockstep/parity pytest 套件不在 hosted CI(單改 Rust emitter 的 PR 可破 lockstep 而 CI 全綠)。

### 4.3 Runtime 現狀(trade-core,2026-07-16 ~18:50 CEST 只讀復核;前次 07-15 16:12)

| 項 | 實測 |
|---|---|
| Linux repo | `808144aff` 與 main 完全同步(clean tree) |
| 引擎 | PID 1084557(07-16 07:40 CEST 起,uptime ~11h);binary 2026-07-15 01:10 build(reflog 推定 `0a4d38ee0`,啟動 banner 已被小時級 log 輪替沖掉=間接推定)——**落後 main 為觀測值非缺陷,W10 inactive deploy 窗收斂** |
| IB Gateway/TWS | **未安裝、未運行**;4001/4002/7496/7497 零 listener;`~/Jts` 不存在 |
| IBKR secrets | secrets 樹零 ibkr slot → P1 loader dormant 如設計 |
| lane 旗標(runtime TOML) | `risk_config_stock_etf_paper.toml` `enabled=false` 實測;connector/external_contact/paper_order/live_order 全 false;port 候選 4002 loopback-only、live ports denied |
| external-surface gate | `<DATA_DIR>/governance/ibkr_phase2/` 不存在 = **production 從未 seal**(fail-closed 成立) |
| systemd user units | `openclaw-trading-api`+`openclaw-watchdog` enabled+active、linger=yes;`openclaw-gateway` disabled;引擎自身 durable unit 仍欠(歸 W9-4) |
| rollback 錨 | `binary_backups/openclaw-engine.pre-ibkr-deploy` 等三錨在位(07-15 觀測) |
| 周邊發現(非 IBKR 範疇) | 07-15 快照:watchdog DSN/logrotate/cron OOM 疊加機均已 source-landed(PR#22/#24/#27/#30/#31),runtime apply 見 TODO 對應行;07-16 增:uvicorn journal 見 judge_edge Timeout 8s 反覆、PG collation 警告(均另行處置) |

結論:runtime 側 IBKR 是**教科書式 dormant**(07-16 全項復核通過)——代碼在、旗標全關、無 slot、無 Gateway、無 seal、零接觸痕跡;W10 inactive deploy 之前不需要任何 runtime 動作。

### 4.4 差距總覽(對照 W2-W11 主題;R8 校準)

| 能力 | 現狀 | 歸屬 W |
|---|---|---|
| production seal caller(Seal/Supersede/Revoke) | **DONE(2026-07-15,R1+R2)**:收口四腿+加固 PR#28 `19985f312`(55 測試);production seal arming 屬 EA3 | W2 ✅ |
| IBKR Rust 測試/G4 symbol audit 進 CI | **DONE(2026-07-15,PR#21 `48872c4fa`)**:`rust-ibkr-tests` 首綠;W3/W4 +4 守衛、結構守衛接 CI(PR#42);殘 3 MEDIUM 洞→W5-S0(§4.5) | W-CI ✅ |
| TWS transport/session manager(可恢復) | **DONE(2026-07-16,S1-S4)**:wire 抽檔 + 六態 FSM(退避/心跳/排程感知 DST)+ INV-1 permit stub + pacing governor(單一出口/有界排隊)+ fake-TWS dev-crate + 端到端 driver;211 engine 測試 | W3 ✅ |
| connection-health IPC/route + normalizer lockstep | **DONE(2026-07-16,W4-1)**:`get_connection_health` IPC+FastAPI route+`IbkrConnectionHealthReportV1`+normalizer 三層 lockstep+fail-closed 四道+driver-absence audit 入 CI | W4 ✅ |
| account/positions/open orders/executions/commissions + session attestation | attestation 僅型別;typed row 契約與 fetch 全缺(只有 probe KIND + digest envelope) | W5 |
| contract details/market data/calendar/entitlement | 契約型別在(identity/provenance);fetch/訂閱/entitlement 邏輯全缺 | W6 |
| order lifecycle(preview/place/cancel/replace/fills/reconcile) | paper lifecycle 契約 source-only,零執行路徑 | W7 |
| activation envelope/風控 authority/kill switch/audit 接線 | envelope 僅字串 placeholder,**無 struct/impl**;kill-switch/audit 契約在、runtime 產生器缺 | W8 |
| DB migration/FastAPI 全面/GUI Phase 4/服務配置/觀測/回滾 | DDL source-only 零 migration;FastAPI 17 唯讀 route 在;GUI 10 子視圖唯讀在(等真值);Gateway unit/observability/rollback runbook 演練缺 | W9 |
| readonly-scope envelope 最小切片(D2 carve) | 缺(envelope 僅字串 placeholder) | W8a |
| Gateway 安裝/unit 預備(D2 carve) | 缺(Gateway 未安裝,unit 不存在) | W9a |
| fake-TWS E2E + inactive Linux deploy + QA | 缺;runtime binary 落後 main(07-16 觀測 87 commits rev-list 全計/35 first-parent,持續擴大;觀測值非缺陷,W10 部署一併收) | W10 |
| 對抗性全域 gap rescan | 缺 | W11 |

### 4.5 R8 校準審計紀錄(2026-07-16)

8 鏡頭對抗審計(W2/W3/W4 源碼逐項核實、全測試鏈本地複跑、CI 姿態、文檔漂移 26 條、移交帳本 33 項、loop 協議批判、runtime 復核):
- **完成件裁決**:W2/W3/W4 全部 `CONFIRMED_AS_CLAIMED`,零紅測試,計數逐項吻合;INV-1 二元 HOLDS(production 無任何 permit 放行路徑);fake crate dev-dep-only 成立;W2 R2 殘餘六項確認仍 open(維持 R-順手)。
- **CI 守衛鏈 3 MEDIUM(→ W5-S0/R9 必修)**:①classifier 缺 `helper_scripts/ci/ibkr_*.sh`(三審計腳本自身的 PR 不觸發 `rust-ibkr-tests`,掏空審計可靜默 merge);②`rust-ibkr-tests` job 無機器釘鎖(workflow static test 未斷言 job 存在+五審計步,同 PR#42 修過的 guard-drift 病根);③W4 lockstep/parity/tripwire pytest 不在 hosted CI(單側改 emitter 可破 lockstep 而 CI 綠)。
- **LOW/NOTE(→ R9+ 順手)**:seal-control 守衛掃描面(order_manager.rs 等)⊄ classifier 觸發面;push-main cancel-in-progress × 精確 diff 的低頻覆蓋窗(記帳為 known posture 或 per-sha concurrency);`rust-ibkr-tests` 加一行 `cargo test -p openclaw_fake_tws`(9 unit tests 現不在 CI);W3 wire/session/pacing MODULE_NOTE「全面 DCE」表述已被 W4 production caller 過時;fake 場景實數 15 非 14(歷史敘事不改,以此行為準)。
- **memory 抄錄漂移**:rust-cache 實為**四** job 非「三」(84b5a3d90 commit body 明文)。

## 5. 工程階段設計 W2→W11

通用紀律(適用每個 W,不再逐條重複):
- **Role chain** 按 TODO.md 各行;authority/security 面加 CC/E3,IBKR 面加 IB,runtime 面加 OPS,end-to-end 宣稱加 QA。E1 自評不算 sign-off(IMPL DONE 必走對抗核驗)。
- **新代碼 Rust 優先**;Python 只做 control plane + thin IPC;注釋只寫中文;跨平台(Mac aarch64 CI 必綠)。
- **測試**:fixture 禁硬編日期(相對/凍結時鐘);fake-TWS 為唯一「接觸」手段;每 W 收口報 E4 計數(新增/總量/PASS);參數禁假功能(每個可調參數必須真實被讀取、生效、持久化)。
- **申報**:用 §3 梯度詞彙;source-landed ≠ GUI-wired ≠ runtime-verified,混稱視為申報缺陷。
- **Commit**:meta-doc 用 `git commit --only`;派工前 fetch + 查遠端 branch;三端同步按既有 SSH bridge 流程。

---

### W2 — P2 production seal/supersession caller ✅ **DONE_SOURCE_SECURED_HARDENED 2026-07-15**(production seal arming 屬 EA3)

**目標**:讓 Phase-2 external-surface gate 的 sealed PASS artifact 有受控的 production 寫路徑(genesis Seal / Supersede / Revoke),移除「production 永不 seal」的永久阻塞,但**不創造任何接觸**。

**R1+R2 收口紀錄**:四腿(PA 補簽/E2/E3/E4)+ 加固切片 PR#28 `19985f312`(staggered-expiry brick 修復=expiry 只約束 active leaf、/run 族 denylist、相對路徑拒絕、readdir errno fail-closed、anti-placeholder、8 新測試,102/0 雙審過);E2-F2 AMD 綁定漂移由 CC 裁 NOT-BLOCKER→AMD-07-08-01 澄清 #3 入典;殘餘 LOW/NOTE(Revoke 豁免壞 inputs、compile_error target 守衛、expiry 上界、測試加硬三項)入 R3+ 順手清單。

**現狀(R8 校準)**:seal/supersede/revoke 三 action ledger(append-only hash chain、flock+dirfd、replay 驗證、pre-write guard)、`bin/ibkr_phase2_seal.rs`(default dry-run + `--apply`×`OPENCLAW_IBKR_PHASE2_SEAL_APPLY=1` 雙閘)、55 in-file 測試 + 靜態守衛在 main;設計檔 `docs/execution_plan/ibkr_live_capability/2026-07-15--w2_seal_caller_authority_design.md`(R1 補簽)。**殘項(blocking):無(2026-07-15 全收口;R8 審計 CONFIRMED)**——殘餘 LOW/NOTE 六項入 R-順手清單(Revoke 豁免壞 inputs/compile_error 守衛/expiry 遠期上界/F-4/5/6 測試加硬/dry-run 診斷 UX;R8 確認全部仍 open、apply 側診斷分流已在 PR#28 落地)。

**範圍 in**:caller authority 模型(誰、何時、以什麼介面觸發 seal:建議 engine 專用子命令或 operator-run helper,禁 GUI/FastAPI 觸發);option A 批准檔 6-binding 驗證(owner-only 0600 + 0700 祖先鏈 + symlink-reject;`source_commit==BUILD_GIT_SHA`;`adr==ADR-0048 ∧ amd==AMD-2026-07-08-01`(此為原始設計範圍;**已被澄清 #3 取代**,現行控制批准綁定見 §4.1);expiry/freshness;lineage 進 artifact hash;永不自注入 Operator);write-once/supersession/revocation lineage 語義落到 caller;default-inactive fail-closed;fake-only 測試。
**範圍 out**:任何 socket/接觸;live 憑證;GUI 面。

**設計要點**:
1. Producer 既有防線全部保留:拒 `/tmp` 或未設 `OPENCLAW_DATA_DIR`;拒 non-empty chain 上的 genesis Seal;Revoke terminal per build SHA。
2. Caller 與 consume 側共用 lineage 驗證代碼路徑,避免兩套語義漂移。
3. 審計:每次 seal/supersede/revoke 寫 append-only 事件(未來掛 `audit.asset_lane_events_v1` 引用)。

**交付物**:caller 模組 + 6-binding 驗證 + lineage 操作 + 拒絕矩陣測試(缺任一 binding、過期、replay、revoked chain、/tmp、非 owner-only)。
**DoD**:`source-ready` + `external-gate-ready`(capability);production 中無批准檔時零效果;E2/E3 PASS;E4 計數;Linux cargo 綠。
**依賴**:無(W1 完)。**規模**:M。
**風險**:批准檔語義與未來 W8 活化紀錄混淆——文檔必須寫死「P2 seal ≠ 活化 authority」(AMD-07-11 明文)。

---

### W-CI — CI 接線雜項 ✅ **DONE_LANDED_FIRST_GREEN 2026-07-15(PR#21 `48872c4fa`)**

**收口紀錄**:IBKR-CI-1(`rust-ibkr-tests` job,五 scope=types 74+287/engine ibkr/stock_etf/seal bin,首綠 7m35s)+ IBKR-CI-2(g4 symbol audit 入 CI)落地;質量鏈 E1→E2 REJECT(F1 IPC 缺)→修復→E2 APPROVE(31+2 溯源閉合)。W3/W4 追加 permit-stub/fake dev-dep-only/fake 缺席 nm/driver-absence 四守衛;結構守衛+classifier 擴 prefix 接 hosted CI(PR#42 `275c76c59`)。build-posture 已裁 B′(2026-07-16 R3):g4 零符號斷言 W3-W7 保綠,W8 落 production TCP factory 時同 PR 改四聯斷言,不得留紅、不得靜默刪除。
**殘項(R8 審計定界,→ W5-S0/R9)**:classifier 補 `helper_scripts/ci/ibkr_*.sh` 三腳本;workflow static test 釘 `rust-ibkr-tests` job 存在+五審計步;W4 lockstep/parity pytest 入 `stock-etf-static-guards`;順手=`cargo test -p openclaw_fake_tws` 一行、seal-control 守衛掃描面 classifier 對齊、三 audit 正控腿 CI-inline。

---

### W3 — TWS transport/session manager(可恢復)✅ **DONE 2026-07-16(loop R3-R6,S1-S4)**

**收口紀錄**:S1 wire 抽檔+`IbErrorClass`(PR#32)· S2 六態 FSM+INV-1 permit stub(PR#33)· S3 pacing governor 單一出口+有界排隊(PR#35)· S4 fake-TWS dev-crate+端到端 driver(PR 見 PROGRESS R6)。211 engine 測試;CC 裁 build-posture=B′(TCP 留 `ibkr_transport_tcp` feature,g4 零符號 audit W3-W7 保綠);IB U1-U6 官方現勘入碼(U4/U5 不可證留 config);三機器守衛(permit-stub INV-1/fake dev-dep-only/fake 缺席 nm 審計)入 CI。**殘項移交**:F1 historical 預算 ordering→W6;queued-heartbeat+單一出口牙齒 send_framed 真消費者→W4;W8 reactivation 須重置 governor strike/bucket;**E3-F1 permit 守衛範圍須隨 driver connect-path 擴(見 W8 audit-scope 條)**。

**目標(原始)**:把 B1(handshake + `reqCurrentTime`)擴成生產級、可恢復的 TWS 傳輸/會話層——之後 W4-W7 的一切都騎在它上面。

**範圍 in**:
1. **Session FSM**:`Disconnected → Connecting → Handshaking → Ready(serverVersion, managedAccounts, nextValidId) → Degraded → Backoff`;斷線指數退避 + jitter;心跳(`reqCurrentTime` 週期);nightly restart 窗與 weekly logoff 的會話過期偵測(fail-closed 進 Backoff,不無限重試)。
2. **Wire 協議層**:length-prefixed framing;API 版本協商(pin 最低 server version);未知訊息 fail-closed;錯誤三元組(id/code/string)→ typed 錯誤分類(transient/session-fatal/entitlement/pacing/order-reject 族);timeout 正規化。
3. **Pacing governor**:client-side token bucket,上限**從帳戶 market data lines 派生**(IBKR 現行語義 = lines ÷ 2 req/s,預設 100 lines → 50 msg/s;超限 error 100、三次違規斷 session——IB 2026-07-15 現勘),config 化、歷史資料/行情訂閱各自預算;**PA 設計時仍須按官方文件複核**。
4. **請求路由**:request-id 分配、pending-request 表、重複/亂序事件容忍、client-id 衝突偵測(duplicate client id 被踢時 typed 事件)。
5. **fake-TWS harness(一級交付物)**:in-process 腳本化 fake server(協議子集 + 故障注入:半訊息斷線、慢響應、亂序、重複事件、版本不符、pacing 違規回應),供 W3-W7 單元/整合與 W10 E2E 復用;以 B1 現有 tokio duplex synthetic-frame 測試為種子擴建,勿另起爐灶;只存在於測試,production build 不含 fake 路徑(AMD 不變量 6:禁 fixtures 藏 caller)。
6. **接觸前置檢查**:`connect()` 之前強制 envelope 驗證掛點(W8 前先放 typed `EnvelopeRequired` fail-closed stub——**stub 只能拒絕,不能放行**);loopback-only;port 由 config(paper 4002 / live 4001 config 分離,live port 在 envelope 缺席時結構性不可達)。

**範圍 out**:任何真連線(G4 之前連 paper 4002 都不許);帳戶/行情/訂單語義(W5-W7)。

**設計要點**:B1 的「lazy build / default build 0 socket 符號」是 AMD-07-08 時代防線;AMD-07-11 已授權 production wiring——**PA 設計槓 CC 重裁 build posture**(建議:能力進 default build,活化由 envelope runtime-gate;保留 `cfg` 開關做防禦縱深)。
**交付物**:session manager 模組 + fake-TWS harness + 故障注入測試矩陣(斷線恢復/過期/踢線/pacing/版本)+ **fake 路徑 production 缺席機器斷言**(仿 G4 symbol audit 的符號/`#[cfg(test)]` 掃描,掛入 W-CI)。
**DoD**:`source-ready`;fake-TWS 下全 FSM 路徑覆蓋;零真 socket 測試;Mac+Linux cargo 綠。
**依賴**:W2 不阻塞 W3(可並行,W3 在 TODO 排 W2 後主要是 reviewer 帶寬)。**規模**:L。
**風險**:協議細節憑記憶寫錯(版本協商/欄位序)——設計期用官方 API 文件 + 抓包對照(paper 環境正式接觸後在 EA2 校準,W3 期間以官方文檔為準);pacing 超限會被 IBKR 斷線,governor 必須先於任何真接觸存在。

---

### W4 — P4 connection-health IPC/route + normalizer lockstep ✅ **DONE 2026-07-16(loop R7,W4-1)**

**收口紀錄**:W4-1 lockstep 單 PR——`IbkrConnectionHealthReportV1` + Rust emitter(ephemeral manager 撞 permit → `external_verification_pending`,零 socket)+ `get_connection_health` IPC + FastAPI GET route + normalizer 三層 lockstep + fail-closed 四道 + driver-absence audit 入 CI。五腿:E2 APPROVE/E3 PASS(授權面無繞過)/IB PASS/E4 全綠/QA ACCEPT。GUI 面 defer W9(採 PA 建議,避免二次觸碰玄衡 shell)。**W5 blocking 移交(見 W5 節)**:Layer 3 lineage-present 分支窮舉性遠弱於 Layer 2 + parity 缺 operational-欄⊆guard superset 斷言,seal lineage 前必修。**pre-existing 治理債**:handler cap(HEAD 826>800)+ runtime-material-reader 3 紅守衛不在 CI(drift),W4 +5→831 加劇非引入(E2/E3/QA 三方驗屍)——**已解(PR#42 `275c76c59`,2026-07-16:`stock_etf.rs` 826→779<800、結構守衛接 CI、classifier 擴 6 prefix;task_2dbb7f53 closed)**。

**目標**:把 session 健康狀態沿 Rust IPC → FastAPI → GUI 唯讀鏈路端到端接通,同步演進 Python normalizer 的負空間 attestation。

**範圍 in**:`stock_etf.get_connection_health` IPC method(進 `lane_scoped_ipc_v1` 方法矩陣與 allowlist);FastAPI GET route(方法分區守衛不動);`stock_etf_account_normalizers.py` lockstep:從「任何真值=violation」演進為「真值而無 PASS+session-attestation lineage=violation」,**gate=BLOCKED 時 all-false fail-closed 回歸測試必須保留**(AMD-07-08 §Runtime Boundary 原文要求,同 PR 內完成);GUI readiness 面消費 health(現有 stock 唯讀 view 擴欄)。
**範圍 out**:帳戶/持倉數據(W5);GUI 新寫面(永禁)。

**DoD**:`source-ready` + inactive 引擎下 IPC/route 真調通(回 `EXTERNAL_VERIFICATION_PENDING` 形態,非 fake-success);Python 靜態守衛(GET-only/no-SDK/no-write)綠;E4 + QA(唯讀鏈路宣稱)。
**依賴**:W3。**規模**:S-M。
**風險**:FastAPI Depends × reload 凍結陷阱(教訓在案)——route module 與 main 同步 reload,或就地刷新 env 派生態。

---

### W5 — account/positions/open orders/executions/commissions + session attestation

**目標**:唯讀帳戶面全量 + 會話 attestation 生產者,把「這是哪個帳戶、是不是 paper、資料新不新鮮」變成 typed、可審計的事實。

**W4 移交(seal lineage 前 blocking,否則 fail-closed 退化——E3-F1/F2 + E2-F3,2026-07-16)**:
- **normalizer Layer 3 窮舉補齊**:W4 的 lineage-present 分支只查 session_active/fingerprint/state 一致性,**遺漏** pacing 活動計數、`entitlement_state`、`report_status`、`reconnect_attempt`、`halt_reason`、attestation-populated。W5 一旦 seal attestation+gate 使 Layer 3 可達,這些遺漏欄即成 fail-open 面——必須對每欄補 per-field lineage-bound 不變量並納入同款精確有序 tripwire(維持 lockstep)。
- **parity superset 斷言**:現 cross-surface parity 只鎖 guard⊆contract、fixture⊇contract,**未鎖 operational-欄⊆guard**——未來 emitter 加 operational 欄而 normalizer 忘 guard,三測仍綠。W5 前加「非 telemetry 的 struct bool/state 欄必屬某 guard 集」斷言(telemetry allowlist=`main_tokens_available`),漂移即紅。
- entitlement enum 二元→三元見 W6;farm-connectivity 欄 + WeeklyReauth 出典見 W8。

**切片計劃(2026-07-16 R8 定稿;S0 為 blocking 前綴,S0∥S1 為指名合格並行對)**:
- **W5-S0 fail-closed 硬化 + CI 守衛鏈收口(R9;E3 加審)**:①normalizer Layer 3 窮舉補齊(pacing 活動計數/`entitlement_state`/`report_status`/`reconnect_attempt`/`halt_reason`/attestation-populated 逐欄 per-field lineage-bound 不變量+同款精確有序 tripwire);②parity 加 operational-欄⊆guard superset 斷言(telemetry allowlist=`main_tokens_available`);③CI 守衛鏈三洞(§4.5:classifier 補 ibkr_*.sh/static test 釘 job/lockstep+parity pytest 入 hosted CI);④順手:fake crate 測試行、W3 MODULE_NOTE 過時注釋(comment-only);⑤`ci.yml` `rust-check-macos` 掛 `github.event.pull_request.draft == false` 條件(loop v2 S4 draft 閘的落地載體)。檔案面=Python/tests/ci + engine .rs 注釋檔(comment-only),零 Rust 語義變更。
- **W5-S1 typed row contracts(可與 S0 並行——檔案面不相交:S1=`openclaw_types` 新檔+acceptance)**:positions-row/executions-row/commissions-row/account-summary-row 契約。
- **W5-S2 account/positions 消化**(engine,騎 session manager 請求路由;快照 staleness 標記)。
- **W5-S3 open orders/executions/commissionReport 消化**(斷線 resync 語義)。
- **W5-S4 attestation producer + 指紋三角測量 + 收口**(managedAccounts 實檢派生、DU* 白名單、未知前綴 fail-closed 當 live 拒;三腿指紋全鏈真值)。

**範圍 in**:
1. `reqAccountSummary`(net liq、cash、settled cash、buying power 等白名單 tag)、`reqPositions`、`reqOpenOrders`/`reqAllOpenOrders`、`reqExecutions` + commissionReport 流的 typed 消化(全部掛 session manager 的請求路由)。
2. **S3/S5 row contracts**:positions-row、executions-row 等 typed 行契約(AMD-07-08 FA gap 明列 positions-row;quote/bar-row 歸 W6)——先契約後消化,禁裸 map。
3. `IbkrSessionAttestationV1` 生產者:`account_fingerprint_is_live` **必須由 managedAccounts 實檢派生(prefix-only paper 判定,fail-closed),禁聲明自填**(TODO W5 行 2026-07-12 附註;seam#2 修復 `c4b52c2e2` 為既有基準)。
4. **指紋三角測量落地**:`FeatureFlagSecretAuthMatrixV1`(secret-slot ∧ session attestation ∧ sealed gate artifact 三腿同一非 live fingerprint)從 T2 的 producer 側交叉檢查升級為全鏈真值(這是 readonly 之外一切的真授權機制)。
5. 快照 vs 流式一致性:序列號/時間戳、staleness 標記、斷線後 resync 語義。

**範圍 out**:行情(W6)、訂單寫(W7)、DB 持久化 migration(W9;本包可寫 evidence 檔案/記憶體形態)。

**DoD**:`source-ready`;fake-TWS 覆蓋:live-prefix 帳戶 → 全鏈 fail-closed;**未知帳號前綴 → 按 live 拒全鏈**(白名單 DU*,非黑名單);三腿指紋不一致 → fail-closed;斷線中途 resync 正確。CC 加審 audit lineage(出典:AMD-07-08 gated sequence P5 行)。
**依賴**:W3(+W4 的 IPC 模式)。**規模**:L。
**風險**:attestation 語義被未來 live 場景反噬——`is_live` 判定必須是白名單(DU* = paper)而非黑名單;未知前綴 = fail-closed 當 live 拒。

---

### W6 — contract details/market data/calendar/entitlement

**目標**:工具識別 + 行情 + 交易日曆 + 權限狀態,全部 point-in-time、可雜湊、可審計。

**範圍 in**:
1. `instrument_identity_contract_v1` 實體化:conid 為主鍵的 PIT 身份(symbol/primary exchange/currency=USD v1/tradability/PRIIPs 標記/fractional policy/calendar/corporate-action 來源雜湊);`reqContractDetails` 消化;拒未知 venue/非 USD/crypto/CFD。
2. `reqMktData` snapshot + subscription 生命週期:訂閱表、行情線路預算(市場數據 lines 上限 config 化)、退訂紀律、斷線重訂;**delayed vs realtime 語義**(`reqMarketDataType` 分級 + per-instrument entitlement 狀態機 `ENTITLED/DELAYED/NONE`)——v1 姿態 = delayed-only、**不購買任何 entitlement**(購買是 EA 跑道 Operator 決策)。
3. quote/bar row contracts(承 W5 契約風格);`stock_market_data_provenance_v1` 雜湊(vendor/entitlement/timestamps/adjustment marker/instrument+calendar hash)。
4. 交易時段/日曆:contract details 的 tradingHours/liquidHours 解析 + 假日/半日;RTH-only v1;時區紀律(America/New_York,DST 換日測試)。

**範圍 out**:歷史 K 線回補管線(進 W9 evidence/DB 或後續研究軌);entitlement 購買;Client Portal Web API(永禁)。

**DoD**:`source-ready`;fake-TWS 覆蓋 delayed/realtime/無權限三態 + 訂閱線路耗盡 + DST 邊界;provenance 雜湊可重建。
**依賴**:源碼依賴=W3(provenance 綁定 attestation 部分待 W5);排程閘=TODO 行 Dispatch after W5。**規模**:L。
**風險**:paper 帳戶行情權限鏡像 live 訂閱(Client Portal **opt-in 共享**,且共享後 **live 與 paper 兩側不能同時取用**該行情——IB 2026-07-15 現勘)、免費檔常為 delayed——v1 delayed-only 姿態天然繞開互斥;**scorecard/成本重建必須顯式標 delayed,禁把 delayed 當 realtime 證據**(QC 審查點);D4 購買 realtime 時必須同時裁決共享拓撲(engine 專用取數 vs operator 觀察面讓位)。

---

### W7 — order lifecycle(preview/place/cancel/replace + fills + reconciliation;fake-TWS)

**目標**:完整訂單狀態機與對賬,paper/live capable、default-inactive,全部用 fake-TWS 驗證。**本包是效果面核心,also 是 HMAC 升級觸發點。**

**範圍 in**:
1. **前置契約**:`broker_capability_registry_v1` machine-check(effect-capable paper-route 實作前,ADR 硬序);`lane_scoped_ipc_v1` 的 `stock_etf.preview/submit/cancel/replace` 方法矩陣(Rust-owned,Python thin relay,typed denial reasons,與 Bybit paper IPC 顯式分離)。
2. **訂單狀態機**:intent journal(先寫意圖後發送,重啟可對賬)→ preview(`whatIf`)→ place → ack/reject → partial fills → filled/cancelled/replaced;`nextValidId` 管理 + order-id drift recovery;重複事件冪等(client order key);in-flight 斷線:重連後以 broker 為真值 resync(`reqOpenOrders`+`reqExecutions` 對 intent journal 三向對賬);**unknown terminal state = fail-closed 凍結該 symbol 並告警,人工/reconciler 裁決前不再下單**。
3. **cash-account 約束引擎**:settled-funds 台帳(T+1 結算追蹤,買入用 settled cash)、good-faith-violation 防護(未結算資金買入後賣出偵測即拒)、no-short(賣出僅限既有多倉)、RTH-only 預設、訂單型別白名單 v1(LMT/MKT DAY;MOC/LOC 後補)、fractional 拒絕 v1、LULD/halt 狀態下的下單拒絕。**T+1/GFV 具體規則由 PA 設計時按官方現行文件核實。**
4. **批准紀律升級**:paper order-write 面落地即觸發 AMD-07-08 澄清 #2 的強制升級——效果面批准從 option A 升 **option B(HMAC 簽名,authorization.json 同紀律)**;此為 W7 的 blocking 前置,與 W8 活化紀錄設計合流。
5. 費用/稅費消化:commission report 綁定 fill;SEC/TAF 費項欄位進 executions-row(數值來源歸 reference-data 契約)。

**範圍 out**:真實 paper 下單(EA5 才發生);策略信號(研究軌);智慧路由/演算法單(v2+)。

**DoD**:`source-ready`;fake-TWS 情景矩陣全綠:正常鏈、部分成交、拒單各族、重連中 in-flight、重啟對賬、重複事件、GFV/short/RTH/halt 拒絕、unknown-terminal 凍結;E3+IB+QA 加審;貫穿性不變量測試:「無 envelope ⇒ transport 層拒發任何 order 訊息」。
**依賴**:W3+W5+W6。**規模**:XL(最大單包)。
**風險**:對賬語義最易藏 P0——**以 broker 為真值、本地 intent journal 為對照、差異 fail-closed** 三原則寫死;Bybit 幻影倉教訓(fill 記帳競態)直接移植:唯一 mutator + reduce-only fail-closed。

---

### W8 — Rust risk/authority:activation envelope、kill switch、audit

**目標**:把 AMD-2026-07-11-01 的活化邊界一字不差變成代碼——這是 live-ready 的授權心臟。

**範圍 in**:
1. **`ibkr_activation_envelope_v1` 驗證器**:全綁定驗證(§2 活化鐵律清單);nonce 原子消費(首次允許接觸前消費,replay/重複消費/stale issue/expiry/revoked epoch/kill-switch epoch 不符全拒);reconnect/scope 變更強制新活化;envelope 有效 ≠ 免除憑證/entitlement/market-hours/safety checks。
   - **W3 移交:reactivation 一致性**——W8 接 reactivation 時,無論 fresh-manager 或 in-place `reset_for_reactivation`,**必須**重置/重建 pacing governor(strike+bucket+queue+lines)並加「reactivation 後無 strike 殘留」測試(否則兩耦合態只重置其一→誤斷,E1/E2 R5 標)。
   - **W3 移交:permit audit-scope 擴張(E3-F1,W4/W8 blocking 前置)**——S2 permit-stub 靜態守衛現 file-scoped 於 `ibkr_tws_session.rs`;W3-S4 引入 `ibkr_tws_driver.rs` 的泛型 permit connect 路徑(`SessionDriver<P: ConnectPermitProvider, F>`)。W8 落 production TCP factory + W4 落 production driver caller 後,四聯 audit(唯一 connect 位點/connect 前必經 permit 且 `PermitToken` move 消費/fake 缺席/**provider 型別唯一性**)**必須涵蓋 `ibkr_tws_driver.rs` 及任何新 connect-path 檔**,斷言全 production 域唯一 `impl ConnectPermitProvider`=`EnvelopeRequiredStub`、`PermitToken::mint()` 全域零 production 呼叫點。W4 wiring 複核已於 R7 完成(driver-absence audit 入 CI);**四聯 audit 首階段擴張隨 W8a 落地(承 E3-F1),W8 落 production TCP factory 時做第二階段擴張並吸收**。
2. **Operator 活化紀錄(authenticated)**:Rust-owned 驗證——issuer identity + verification key 或 immutable approval hash、envelope payload digest、nonce、account/session/build scope 綁定;實作與 W7 的 option B(HMAC/簽名)合一設計,達到 authorization.json 紀律 parity;Python/FastAPI/GUI 只能 request/display 活化流程,**不得創建/更改/轉發原始授權材料或代 attest**。
3. **風控接線**:`stock_etf_risk_policy_v1` machine-check;`risk_config_stock_etf_paper.toml` + live 變體 config 分離(readonly/paper/shadow/tiny-live/live 五態 config 可重現,live-capable build ≠ active build);notional/order/position 上限、Guardian、Decision Lease、global Cost Gate lineage 進 envelope 綁定;**global Cost Gate 不得因本 lane 降低**。
4. **kill switch**:kill-switch epoch 全域檢查點(transport 層 + order 層雙掛);`stock_etf_kill_switch_and_disable_cleanup_runbook_v1` machine-check(disable flags、collector stop、GUI disabled 姿態、live-secret 缺席、forward-only 保留、append-only audit)。
5. **audit lineage**:`audit.asset_lane_events_v1` 事件引用(lane/broker/env/operation、hash-chain 連續性、producer/source metadata、redaction 邊界);活化/接觸/效果/kill 全部事件化。

**範圍 out**:真活化(EA);GUI 活化流程 UI(W9 顯示層)。

**DoD**:`source-ready`;拒絕矩陣測試逐綁定(每個 binding 單獨缺失/過期/不符 → 拒);nonce 併發消費競態測試;**seal≠活化機器證明**(sealed Phase-2 PASS artifact 在位 + 無 envelope → 接觸拒絕);**envelope 與傳輸層交叉一致性**(paper/readonly envelope + live port 4001 → 拒;readonly envelope + 任何 order verb → 拒);CC+E3+IB 三審(16 root principles checklist 必讀面)。
**依賴**:W7(合流 option B)。**規模**:L。
**風險**:授權面最忌「先寬後緊」——一律先寫拒絕路徑再寫放行路徑;任何測試後門(test-only 放行)必須 `#[cfg(test)]` 且 E3 專項掃描。

---

### W8a — readonly-scope activation envelope 最小切片(D2 carve;2026-07-16 R8 入 §5 排程)

**目標**:`ibkr_activation_envelope_v1` struct + 驗證器的 **readonly-scope 最小實體**:全綁定驗證(§2 活化鐵律清單)、nonce 原子消費、issued-at/expiry、revocation epoch、kill-switch epoch;**order verb 一律結構性拒**(readonly scope 外全拒);拒絕矩陣標準與 W8 完全同級,CC/E3/IB 審不減。
**定位紀律**:純 no-contact 開發,在 AMD-07-11 development 授權內,**不預決 D2**(是否提前點火 EA1-EA4 仍是 Operator 活化時序決策);W8 全包落地時**吸收**本切片(共用同一驗證代碼路徑,禁兩套語義漂移——同 W2「caller 與 consume 共路徑」原則)。落地本切片的唯一目的=讓 EA1-EA3 在 Operator 就緒時零工程等待。
**範圍 out**:paper/tiny-live/live scope、option B HMAC(歸 W7/W8)、GUI 顯示(W9)。
**DoD**:`source-ready`;拒絕矩陣逐綁定 + nonce 併發競態 + 「readonly envelope + 任何 order verb → 拒」+「seal 在位無 envelope → 拒」;permit audit-scope 四聯斷言隨本切片首次擴到 driver 面(承 W3 移交 E3-F1)。
**依賴**:源碼依賴=W3;排程閘=TODO 行 Dispatch after W5(理由=先收 W5-S0 CI 守衛鏈+避免與 W5 engine 面撞工,非源碼依賴)。**規模**:M。**與 W9a 可並行**(檔案面/reviewer 集不相交)。

### W9a — IB Gateway 安裝/systemd unit 預備(D2 carve)

**目標**:Gateway 安裝腳本 + systemd unit 檔(default **disabled/masked**)+ headless 預備(nightly restart 窗、watchdog 掛點、log rotation 配置)。**接觸語義定界**:「接觸」=AMD-07-11 語義的 broker API/session/資料/訂單效果;installer 從 IBKR 官方來源下載屬**供應鏈動作**,僅限 operator 批准窗內、官方 URL+checksum 釘定(pin-by-reference,承 DOC-06 RM-4)。**執行者**:operator 親手,或 OPS agent 於批准窗內代跑(批准紀錄+before/after 快照按 RM-1 落檔)。**安裝不產生任何接觸**(從不啟動、從不登入,enable 屬 EA2)。
**範圍 out**:enable/登入/任何 socket;live Gateway(4001)配置(EA7)。
**DoD**:腳本+unit source-ready;若 operator 開窗執行安裝:OPS preflight/postcheck 證據(unit masked、零 listener、零 ~/Jts 進程);**dormant 簽名遷移**:安裝後「~/Jts 不存在」失效,新簽名=~/Jts 存在但零進程+unit masked+4001/4002/7496/7497 零 listener(§4.3 快照同步加日期注記)。
**依賴**:源碼依賴=無;排程閘=TODO 行 Dispatch after W5;安裝執行需 operator 開窗。**規模**:S-M。Role:PM→E1→E2→E3/OPS/IB→PM(E3=供應鏈/unit 權限面)。

---

### W9 — DB/evidence、FastAPI、GUI、service config、observability、rollback

**目標**:把能力包進完整的運維外殼:資料落地、全面唯讀 API、GUI Phase 4、服務配置、觀測、回滾。

**範圍 in**:
1. **DB**:`stock_etf_db_evidence_ddl_v1` 從 source-only 走到 V### migration——**單獨 migration 授權是 Operator/PM 決策點(§9)**;Linux PG dry-run + double-apply 強制;Guard A/B/C 控制;paper/shadow 分離、audit-event 存儲、自然鍵。
2. **FastAPI**:唯讀面補全(health/account/positions/orders/executions/market/entitlement/activation-status);方法分區 + allowlist gate 維持;非 GET 僅開放**單一具名**受限 method(activation-request/display 專用,**不接收、不轉發任何授權材料**),同 PR 顯式修訂 GET-only 靜態守衛白名單並引 AMD-07-11 request/display 條款為據(修訂模式參照已廢止 AMD-07-09-01 invariant 9 的單方法例外寫法);其餘面 GET-only 守衛與回歸測試原樣保留,E3 專審。
3. **GUI Phase 4**:10 個唯讀子視圖已在(§4.2),W9 重點不是蓋新面板而是**真值接通**:`gui_lane_contract_v1` artifact(GET-only、client state untrusted、route/cache/auth 負測試、stale-cache 跨 lane 拒絕、crypto Decision Lease/risk 回歸)+ 新增 entitlement 狀態與活化流程展示(display-only);**騎現行玄衡 shell(tokens.css 雙主題),遵 gui-style-guide,sign-off 必跑 node --check**;GUI 數字禁 fake(`present && accepted` 才渲染,承 AMD-07-08 的 $0.00 誠實缺陷修復精神)。
4. **Service config**:(2026-07-16 R8 注:Gateway 安裝/unit 預備已 carve 至 **W9a**,本項承接其交付並收殘面)engine env 持久化(`OPENCLAW_DATA_DIR` home 路徑;durable systemd unit 既有欠賬一併收);bind host 安全預設(Tailscale IPv4 否則 loopback,禁 0.0.0.0);W9a 已交付面此處僅整合驗收。
5. **Observability**:session FSM 狀態、pacing 預算、attestation/entitlement 狀態、訂單生命週期計數、對賬差異、kill-switch epoch——落 DB 告警 sink + healthcheck 整合(**live-slot 出現且無有效 tiny-live/live 活化 lineage → healthcheck fail-closed(typed blocker)**;唯一放行條件 = W8 定義的 Rust 驗證現行 tiny-live/live 活化紀錄 epoch,EA7 引用此語義)。
6. **Rollback**:binary 備份 + config 回滾 + disable/cleanup runbook 演練腳本(machine-check 承 W8)。

**DoD**:`source-ready` + `runtime-active(inactive)` 於 staging 級驗證;migration 在 Linux PG dry-run+double-apply 證據;GUI 負測試矩陣綠;OPS+IB 審。
**依賴**:W5-W8。**規模**:XL。
**風險**:migration 是全局命名空間(V### 撞號教訓)——先 fetch 全 repo + Linux `_sqlx_migrations` 對表再選號;GUI 大改程仍在跑,與 gui_redesign 排程協調(stock view 已原生遷移,增量開發不回退殼)。

---

### W10 — Mac 測試 + fake-TWS E2E + Linux inactive deploy + QA + 三端同步

**目標**:全鏈整合驗證與 inactive 部署——「部署了、活著、但一根 socket 都不伸出去」。

**範圍 in**:Mac aarch64 全量 cargo/pytest;fake-TWS E2E 劇本套件(冷啟→session→reads→orders→故障→重啟對賬→kill→disable cleanup 全流程);Linux inactive deploy(engine rebuild+restart,lane `enabled=false`,boot 後驗證:零 socket 嘗試、`EXTERNAL_VERIFICATION_PENDING` 姿態、healthcheck 綠-inactive、Bybit 路徑零擾動);QA 真 GUI journey(唯讀 inactive);三端同步(Mac/GitHub/Linux 同 SHA)。
**教訓內建**:post-deploy 真連線 smoke > mock(這裡「真連線」= IPC/FastAPI/GUI 對 inactive 引擎,非 broker);deploy 走 restart_all 既有腳本語義(`--rebuild` 只重建 engine);07-05 binary 備份慣例保留 rollback 錨。
**DoD**:QA/OPS/IB 簽;deploy 前後 preflight/postcheck 證據包;Bybit 回歸零差異。
**依賴**:W1-W9。**規模**:M。

---

### W11 — 對抗性全域 gap rescan + 收口

**目標**:多角色冷酷複掃,宣告 `IBKR_FULL_LIVE_CAPABILITY_COMPLETE_EXTERNAL_ACTIVATION_PENDING`。

**範圍 in**:CC/E3/IB/OPS/QA 並行對抗審(範式:ultracode 全審);對照物 = AMD-2026-07-11-01 終態清單 + ADR-0048 named contracts 全陣 + 本文件 §5 全 DoD;產出 gap matrix,**只允許 external session/credential/activation 類殘項**;governance 開放題裁決(§9 OPEN-GOV);TODO.md/CLAUDE.md/memory 三端申報同步。
**DoD**:gap matrix 零非外部殘項;終態宣告進 TODO banner;EA 跑道文件化交接。
**依賴**:W10。**規模**:M。

---

### 5.5 剩餘工程日誌安排(R8 定稿;live-ready 為止)

```
[✅W2 ✅W-CI ✅W3 ✅W4]
W5(S0∥S1→S2→S3→S4)─┬─ W8a ∥ W9a(carve;與 W6 平行)
                     ├─ W6(S1→S2→S3)
                     └────→ W7(PA 切片→S1..S4)── W8 ── W9 ── W10 ── W11
```

| 輪 | 切片 | 並行注記 |
|---|---|---|
| R8 | 本次校準(docs)+ loop v2 | docs-only |
| R9 | **W5-S0** fail-closed 硬化 + CI 守衛鏈收口 | 可 ∥ R10(檔案面不相交,loop v2 manifest 程序把關) |
| R10 | **W5-S1** typed row contracts | 同上 |
| R11-R13 | **W5-S2/S3/S4** → W5 收口 | 序列(同 engine 面) |
| R14/R15 | **W8a ∥ W9a**(carve) | 檔案面+reviewer 集全不相交,首選並行對;與 R16+ W6 亦可交錯 |
| R16-R18 | **W6-S1/S2/S3**(contract details+PIT/行情+entitlement 三態/日曆 DST)→ W6 收口 | S1 含 W3 移交 F1 historical ordering |
| R19-R22 | **W7**(PA 切片計劃→前置契約/狀態機/cash 約束/對賬)→ W7 收口 | XL 獨佔窗;T+1/GFV 需 IB 現勘前置;option B 觸發 |
| R23-R25 | **W8**(envelope 全量 承 W8a/option B 活化紀錄/風控/kill switch/audit)→ W8 收口 | 含 W3 移交 reactivation 重置+四聯 permit audit **第二階段擴張**(TCP factory 面;首階段已隨 W8a) |
| R26-R28 | **W9**(DB migration D1 裁決/FastAPI/GUI Phase 4/service/observability/rollback)→ W9 收口 | XL;GUI 面承 W4 defer |
| R29 | **W10** Mac 全量+fake-TWS E2E+Linux inactive deploy+QA+三端 | operator 開 deploy 窗 |
| R30 | **W11** 對抗性全域 rescan → 終態宣告 | gap matrix 只許外部殘項 |

- **工期估計(R8 修訂)**:剩餘 ~22 輪;實證 cadence R3-R7=5 輪/2 天(峰值),持續性折算 1.5-2 輪/天 ⇒ **工程側 live-ready ≈ 2.5-4 個有效工程週**(原 v1 估 6-10 週,W2-W4 已消化+cadence 實證上修)。主要變異源:reviewer/E4 帶寬、agent 配額死亡、operator 決策窗(D1/D2)、CI spending;**XL 包(W7/W9)每輪切片吞吐未經同規模實證,輪數或膨脹**。
- **EA 疊加時間軸(若採 D2;各週標記按樂觀端 ~2 輪/天,悲觀端順延 ×1.6)**:W5+W8a+W9a 齊(≈第 1-1.5 週末)→ EA1-EA3 可點火(全 Operator 動作);EA4 readonly soak 7-14 天與 W6/W7 開發平行;W7+W8+option B 齊(≈第 3 週)→ 申請 EA5 開 paper 窗 → evidence clock 6-8 週起跑;工程終態宣告(W11)與 clock 平行,tiny-live(EA7)最早 ≈ clock 開窗後 6-8 週(受 OPEN-GOV-1/D7 保守讀法約束)。
- **TODO 對位注記**:現行並行面=W5-S0∥W5-S1、W8a∥W9a、carve∥W6;凡鬆於 TODO.md 行前置者派工前先更新 TODO 對應行;W8a/W9a 已補 TODO 行(v816)。TODO.md 是 dispatch 唯一正本。

## 6. 外部活化跑道 EA1→EA8(全 Operator-gated;本節是設計不是授權)

每一步都要:當步 envelope(scope 精確到操作)+ 憑證/session 實態 + 前步證據;缺件記 `EXTERNAL_VERIFICATION_PENDING`。

| 階段 | 內容 | Operator 動作 | 產出證據 |
|---|---|---|---|
| **EA1 憑證 custody** | Operator 手動放置 readonly/paper 憑證入 `<secrets-root>/external/ibkr/{readonly,paper}/`(loader 只驗 fingerprint;live slot 此時**必須仍缺席**) | 放置 + 確認 slot 指紋 | slot fingerprint 記錄 |
| **EA2 Gateway paper 起立** | enable W9 交付的 systemd unit(paper 4002、loopback、read-only API 設定);watchdog/nightly restart 演練(Gateway 現況未安裝——安裝與 unit 預備歸 W9,EA2 只做 enable+登入) | 批准 enable + IBKR 帳號側 paper 登入(2FA 適用性按 IBKR 現行政策,EA1 時由 IB 現勘) | OPS runbook 執行證據 |
| **EA3 G4 首次接觸(readonly)** | 前置:**AMD-07-08-01 澄清 #3 Operator acknowledgement(尚待,PROGRESS R2)**;production seal(W2 路徑,option A 批准檔;**每次 apply 前歸檔該次批准檔精確位元組——AMD-07-08-01 澄清 #3 第 4 點,審計重算閉合必要條件**)→ readonly envelope + 活化紀錄 → 首次 **health/serverTime** 真讀(嚴格對齊 AMD-07-08 G4 讀集;accountSummary 等歸 EA4 逐項納入) | **一次性顯式批准**(AMD-07-08 G4 語義)+ 活化紀錄 | QA runtime 證據;`session-ready` 達成 |
| **EA4 readonly soak + entitlement 確認** | 7-14 天唯讀穩定窗:session FSM/重連/nightly restart 實測;accountSummary/positions 等唯讀集按 envelope scope 逐項納入;delayed 行情實態;三角指紋長期一致。**重連活化紀律**:每次 reconnect(含 nightly restart 後)需新 envelope + 活化紀錄——soak 期預設 Operator 每日活化;如欲設計 scoped 排程性重連授權(單活化綁定預告重啟窗),屬 AMD-07-11 字面外,先開 OPEN-GOV-2 由 CC 裁決,未裁前按每日活化執行 | 讀 soak 報告 + 每日(或裁決後按窗)活化 | `entitlement-ready`;W3 協議假設校準 |
| **EA5 paper effect 活化** | 開窗前置:**W7+W8 全綠 + option B 落地** + PIT universe / strategy hypothesis / market-data provenance / reference-data **四契約 accepted + 全 hash 凍結(D5 已裁)**;然後 paper envelope(option B HMAC 紀律)→ 首批 paper 訂單生命週期真跑 + 對賬 → 開 `stock_etf_evidence_clock_v1`(6-8 週 paper/shadow 窗) | paper 活化紀錄 + evidence clock 開窗批准 | `effect-authorized`+`evidence-producing`(paper) |
| **EA6 證據與研究收斂** | scorecard/benchmark/cost 重建與證據收斂(QC/MIT 鏈);`tiny_live_adr_eligibility_v1` 討論閘評估(預註冊已在 EA5 前完成,此處不再改假設) | 讀 QC/MIT verdict | scorecard verdict artifact |
| **EA7 tiny-live** | live 憑證 slot 創建(此時才允許,單獨批准;出典:AMD-07-11 活化紀錄路徑——ADR-0048 Denied Paths 的 live-slot 行僅於有效 tiny-live/live 活化 lineage 下被壓倒,healthcheck 放行語義見 W9-5)+ live Gateway(4001)+ tiny-live envelope(顯式限時、exact scope、極小 notional caps)+ 首單~soak | **live 資金 + tiny-live 活化紀錄**(逐窗;是否另需新 ADR/AMD 見 OPEN-GOV-1 第二問,未裁前按需要執行) | money-boundary 證據 |
| **EA8 live ramp → VERIFIED** | 額度階梯逐級放大(每級新活化);IB/E3/OPS/QA 聯合 attested 證據包 → `IBKR_FULL_LIVE_READY_VERIFIED` | 每級活化 + 終態確認 | 終態證據包 |

**平行化建議(R8 修訂,以本段為準)**:W8a/W9a 兩個 carve 件已入 §5 排程(R14/R15)——**開發面不需等 D2**(純 no-contact,AMD-07-11 授權內);D2 只裁「EA1-EA4 是否提前點火」,時點=W5+W8a+W9a 齊備時。**EA1-EA3 前置 = W3-W5 + W8a + W9a**;W8a/W9a 未齊則 EA1-EA3 前置回落完整 W8/W9。EA 各步 W 前置總表:EA5 = W7+W8 全綠 + option B(建議含 W9);EA7+ = W7-W11 全綠。

## 7. 橫切工程紀律

- **fake-TWS 為王**:W2-W11 期間唯一「broker」是 fake harness;任何真接觸提案都是 EA 事項,直接打回。
- **Reviewer 陣**:IB 是 IBKR 面唯一 broker reviewer(BB 不能替);官方政策事實(pacing/結算/費率/entitlement)一律「來源+時間」現勘,不信記憶。
- **安全**:E3 每包掃 secret 邊界(明文零容忍、log redaction、symlink/權限矩陣);OWASP checklist 於 FastAPI/GUI 面;secret-leak 掃描是每次 commit gate。
- **CI**:`stock-etf-static-guards` job 常綠;新增 Rust 面掛進現有 workflow;macOS job 遵 2000min/月成本政策(PR+週一 cron)。
- **文檔**:每 W 收口更新 SPECIFICATION_REGISTER + document_index(R4 巡檢);本文件 §4/§5 狀態行同步。
- **三端同步**:Mac SSOT → origin/main → Linux `pull --ff-only`;部署只由 operator-gated 窗執行。

## 8. 風險登記簿(IBKR 特有)

| # | 風險 | 影響 | 緩解(歸屬) |
|---|---|---|---|
| R1 | TWS API pacing/斷線(現行語義:上限 = market data lines ÷ 2 req/s,超限 error 100、三次違規斷 session) | session 不穩、資料缺口 | governor 上限從帳戶 lines 派生(W3);soak 實測(EA4) |
| R2 | nightly restart + **週日 ~1:00am ET 強制人工重新認證**(auto-restart 只覆蓋 Mon-Sat) | 每日固定失聯窗 + 每週人工事務;疊加 AMD 重連鐵律 = **每次重連需新活化**(每日活化負擔,EA4 起) | FSM 過期態 + 排程感知(W3);runbook(W9);OPEN-GOV-2 裁排程性重連授權 |
| R3 | 單 username 單 session(重登互踢) | operator 手動登 TWS 會踢引擎 | 專用 paper/live username 紀律(EA1 決策);踢線 typed 事件(W3) |
| R4 | paper fills 失真(模擬撮合偏樂觀) | 證據高估 edge | scorecard 標記 paper 保守重建(EA6 QC);shadow fill 對照(ADR 既有) |
| R5 | delayed vs realtime 行情混標 | 證據污染 | provenance 強制標記(W6);QC 審 |
| R6 | T+1 settled funds / GFV | cash 帳戶違規、券商限制 | settled-funds 台帳 + GFV 防護(W7) |
| R7 | corporate actions(拆併股/配息) | 持倉/成本基準漂移、對賬假差異 | PIT identity + reference-data 雜湊(W6);對賬容差規則(W7) |
| R8 | LULD/halt/auction | 下單被拒/掛死 | 狀態感知拒單(W7);錯誤族分類(W3) |
| R9 | 行情訂閱費/entitlement 結構 | 成本與資料品質權衡 | v1 delayed-only;購買為 EA 決策(§9) |
| R10 | IBKR API 版本漂移 | 協議破壞 | server version pin + 協商 fail-closed(W3);IB 定期政策巡檢 |
| R11 | 時區/DST/半日 | 排程與 RTH 判定錯 | America/New_York 統一 + DST 測試(W6) |
| R12 | 治理錯配(把 capability 說成 activation) | 合規事故 | §3 申報詞彙強制;W11 CC 終審 |

## 9. Operator 決策清單(遇到即問,不預設)

| # | 決策 | 時點 | 預設建議 |
|---|---|---|---|
| D1 | DB migration 授權(evidence DDL → V###) | W9 前 | 批;Linux dry-run+double-apply 證據隨附 |
| D2 | 唯讀跑道提前並行(EA1-EA4 提前點火) | W5+W8a+W9a 齊備時(≈R15 後,在即) | **建議採用**——W8a/W9a 開發已入 §5 排程(R14/R15,不需 D2);D2 只裁 EA 點火時序。採用=校準真實 session 假設+壓縮總 wall-clock;EA1-EA4 每步仍逐一 Operator 活化 |
| D3 | paper/live 專用 IBKR username 拆分 | EA1 前 | 建議拆(避免互踢) |
| D4 | 行情 entitlement 購買(realtime US equities) | EA4 後 | 先 delayed 跑證據窗,按 QC 需求再買;**購買時必須同時裁決 live↔paper 行情共享拓撲**(共享後兩側互斥取用,見 W6 風險) |
| D5 | 策略假設家族與 universe(低/中換手、日/週頻,USD 股/ETF) | EA5 前(QC 研究軌可先行) | QC 預註冊提案後裁 |
| D6 | tiny-live 額度階梯與每級 soak 長度 | EA7 前 | QC/風控提案後裁 |
| D7 | evidence clock 是否為 tiny-live 硬前置(OPEN-GOV-1,見下) | W11 | 建議維持 6-8 週窗為硬前置 |

**OPEN-GOV-1**(W11 CC 出典裁決,未裁前一律保守讀法):①AMD-2026-07-11-01 把 tiny-live/live 活化條件定義為 envelope + 顯式限時 Operator 活化,未字面重申 ADR-0048 的 `tiny_live_adr_eligibility_v1` 討論閘/證據窗前置;ADR 的 auto-promotion 禁令仍在——「Operator 可直接活化」vs「證據窗仍是硬前置」需裁決(本文件預設後者,D7)。②tiny-live 是否需**新 ADR/AMD**(ADR-0048 Authority Matrix「positive paper/shadow may only open a new ADR discussion」讀法)——未裁前 EA7 按保守讀法需新 ADR/AMD。

**OPEN-GOV-2**(EA4 前如需再裁):AMD-2026-07-11-01 重連鐵律 = 每次 reconnect 新活化;nightly restart 使之成為每日事務。若欲設計「scoped 排程性重連授權」(單一活化紀錄綁定預告重啟窗,windowed 自動重連),屬 AMD 字面外,需 CC 裁決或 AMD 補充;未裁前 EA4 起按每日活化執行。

## 10. 維護規則

- 本文件由 PM 維護;**每 W 收口時的固定回寫清單(loop v2 S6 checklist,與代碼同 PR)**:§5 該 W 節狀態行(一行,含 SHA)+ §4.4 對應行 + **§0 現況一句話** + 被本輪推翻的任何舊行(§4.2/§4.3 快照段不回寫,只加日期注記);EA 階段推進時更新 §6 表。教訓:v1 只刷「本輪行」導致 §0/§4.4 凍結在 07-15 而 §5 局部已 DONE 的段內自相矛盾(R8 校準修復)。
- **自主推進 loop(v2,2026-07-16 起)**:協議正本 `docs/agents/ibkr-live-capability-loop.md`(R-N 迭代:同步門→選工(file-surface manifest 並行程序)→派工→質量門→一輪一 PR→三端收斂→固定記帳 checklist→自排;反空轉硬規則+接棒死亡分類),帳本 `docs/execution_plan/ibkr_live_capability/PROGRESS.md`。loop 只推 W5-W11+W8a/W9a 的 no-contact 工程;EA 跑道仍全 Operator-gated。
- 措辭紀律:任何更新不得把 source 就緒寫成 broker 授權(AMD-07-11 §Required source-of-truth updates 對所有摘要文件的要求)。
- 撞版防護:multi-session 環境,更新走 `git commit --only IBKR_TODO.md`,推前 fetch;main 禁直推,走 feature branch → exact-head PR → merge。
