# W7 — Order Lifecycle 架構設計 + 切片計劃(PA,2026-07-17 loop R23)

**性質**:PA architecture investigator + design writer 產出。**設計文檔,非授權文檔,非實作代碼**。真實 broker 接觸/訂單效果仍由 `ibkr_activation_envelope_v1` + Operator 活化紀錄單獨把關(AMD-2026-07-11-01)。
**基線**:main @ `2613daf14`(只讀分析)。
**權威出典鏈**:AMD-2026-07-11-01(development 授權)> AMD-2026-07-08-01 澄清 #2(option A 6-binding + **HMAC 升級觸發器**)> ADR-0048(lane taxonomy / named-contract gate / Denied Paths / Phase)> `IBKR_TODO.md` §2/§5-W7/§4.4/§8-R6/R8 > `CLAUDE.md` §四 硬邊界。
**先 PA 設計後 E1 實作**(W3 XL 先例);本文檔切片計劃 S0-S4 進 TODO 派工。

---

## 0. 一頁摘要

- **W7 = effect 面核心 + 最大單包(XL)**。它把引擎從「唯讀對賬骨架」(W5-S3 已消化 execDetails/commissionReport/openOrder/orderStatus)補成「完整訂單生命週期、paper/live-capable、default-inactive、fake-TWS only」。
- **最高不變量(貫穿設計)**:**無 effect envelope ⇒ transport 層拒發任何 order 訊息**。這不是一個 if 檢查,而是一個**型別強制的出站閘點**:order-verb frame 是獨立 newtype,唯一送出路徑要求一枚 production 域**不可鑄造**的 `OrderEffectPermit`。production 保持 INV-1 二元:零 effect envelope ⇒ 零 order frame 出站。
- **關鍵發現:型別層已 source-ready,W7 是 runtime driver + authority seam**。`IbkrPaperOrderLifecycleState`(14 態)、`is_transition_allowed`/`is_operation_transition_allowed`、`BrokerLifecycleEventLogV1`(append-only hash chain)、`StockEtfPaperOrderRequestEnvelopeV1`、`broker_capability_registry_v1`、`lane_scoped_ipc_v1`(已含 Preview/Submit/Cancel/Replace 方法矩陣 + PREVIEW/SUBMIT 欄位集)全部在 `openclaw_types`。W7 不重造契約,而是①落地 transport-gating seam、②runtime 狀態機 driver、③cash 約束引擎、④三向對賬引擎、⑤option B HMAC effect-activation。
- **切片**:S0(前置契約 machine-check + transport-gating 骨架,**blocking 前綴,恆拒 stub**)→ S1(狀態機 driver + intent journal,不送出)→ S2(cash 約束引擎)→ S3(三向對賬引擎,**P0 核心**)→ S4(option B HMAC + `check_effect_contact` + IPC 接線 + fake-TWS 全矩陣 + 收口)。**option B 必落於 S4,且為 EA5 paper 窗 blocking 前置**;W8 全包吸收 option B 進完整活化紀錄。
- **建議 R24 起首切片 = W7-S0**(仿 W3 permit-stub 先落、先寫拒絕路徑)。

---

## 1. Transport-gating 貫穿不變量(最高優先)

### 1.1 不變量陳述

> **INV-ORDER**:production build 中,不存在任何路徑可使 order-verb 訊息(placeOrder / cancelOrder / cancelOrder-replace)出 transport 層,除非該次出站被一枚有效 effect-scope `ibkr_activation_envelope_v1`(operation_scope ∈ {paper,...})的 runtime 裁決授權。無 envelope ⇒ 結構性零 order frame 出站。readonly envelope + 任何 order verb ⇒ 拒。

INV-ORDER 是 INV-1(connect permit,W3)的**兄弟不變量**,不可由 INV-1 替代:INV-1 守 connect,INV-ORDER 守 order-verb send。EA 跑道(EA3/EA4)下 session 已 connected(readonly envelope),此時 connect permit 已無守衛作用,**唯 INV-ORDER 阻止 order verb**。

### 1.2 現有 transport 面(as-built 盤點)

`ibkr_tws_driver.rs` / `ibkr_tws_session.rs` 有**兩個 transport 閘點**:

| 閘點 | 令牌 | 鑄造點 | production 姿態 |
|---|---|---|---|
| **connect** | `PermitToken`(非 Clone/非 Copy,crate-private `mint`) | `ConnectPermitProvider::check` 回 `Ok` 時 | production 唯一 provider=`EnvelopeRequiredStub` 恆 `Err(EnvelopeRequired)` → 從不鑄造 → 恆停 `Disconnected(EnvelopeRequired)` |
| **outbound send** | `OutboundGrant`(module-private `mint`,by-value 消費) | pacing governor 放行時 | `send_framed(grant, frame)` 單一出口,**但只管 pacing,不管 envelope** |

**缺口**:`send_framed(grant, frame)` 接受**任意** frame。W5-S3 的唯讀對賬 builder(reqExecutions/reqOpenOrders)與未來 W7 的 order builder 都產 frame,兩者在 transport 層無型別區分。若 W7 order builder 直接餵 `send_framed`,則 order verb 只受 pacing 約束,不受 envelope 約束 —— INV-ORDER 落空。

### 1.3 設計:第三令牌 `OrderEffectPermit` + `OrderFrame` newtype(單一 order 出站閘點)

**Module/Interface/Seam**:在 pacing 單一出口之上,為 order verb 增設第二把型別鎖。

```
                       ┌─ 唯讀對賬 frame (Frame) ──→ send_framed(grant, frame)         [pacing only]
order builder 產出 ────┤
                       └─ order-verb frame (OrderFrame) ──→ send_order_framed(          [pacing AND envelope]
                                                              grant: OutboundGrant,
                                                              effect: OrderEffectPermit,
                                                              frame: OrderFrame)
```

- **`OrderFrame`**:order-verb 專屬 newtype(placeOrder/cancelOrder 的 framed bytes 包裹)。**型別上不是 `Frame`** → 編譯期無法餵入通用 `send_framed`。order builder 只回 `OrderFrame`。
- **`OrderEffectPermit`**:非 Clone/非 Copy,crate-private `mint`;唯一鑄造點 = effect-scope 活化裁決 `check_effect_contact(...)` 回 `Accepted` 時(見 §4)。production 唯一 effect provider = `EffectEnvelopeRequiredStub` 恆拒 → 從不鑄造 → production 零 order frame 出站。
- **`send_order_framed`**:唯一 order-verb 出站函數。by-value 消費 `OrderEffectPermit`(單次)+ `OutboundGrant`(pacing 仍在)。每個 order verb 一次 send 需一枚 fresh permit(單次消費語義,承 nonce 一次性)。

### 1.4 機器守衛(structure test,承 W3 四聯 audit / driver-absence audit 家族)

INV-ORDER 的守衛必須是**機器可斷言**,非人審承諾。W7 交付以下 structure test(掛 CI `rust-ibkr-tests`,承 §4.5 CI 守衛鏈紀律):

1. **唯一 order 出站位點**:`OrderFrame` 型別的值只能流入 `send_order_framed`;全 crate grep/type-flow 斷言零其他消費者(仿 `send_framed` 單一出口牙齒)。
2. **effect permit 零 production 鑄造**:`OrderEffectPermit::mint` 全域零 production 呼叫點;唯一鑄造點在 `check_effect_contact` `Ok` 臂,其上游 production provider = `EffectEnvelopeRequiredStub` 恆拒(nm-audit 斷言 production build 唯一 `impl EffectPermitProvider`=stub)。
3. **order builder 缺席於 default build**:承 B′ build posture,order builder + `send_order_framed` 在 default build(無 effect feature/envelope)DCE;g4/driver-absence audit 保綠。
4. **readonly envelope + order verb → 拒**:`check_effect_contact` 對 readonly-scope envelope 回 `OrderVerbStructurallyDenied`(承 `ibkr_activation_envelope_check.rs::readonly_operation_blocker` 現有語義,擴到 effect 面)。

**Deletion test**:刪 `OrderEffectPermit`/`OrderFrame` seam → order frame 可經通用 `send_framed` 在僅 connect/readonly permit 下出站 → INV-ORDER 崩、EA 跑道 readonly soak 期無法阻擋 order verb。⇒ seam 非 ceremonial,承載唯一不變量。
**Second-adapter test**:live-scope order verb(EA7 tiny-live)是同一 seam 的第二消費者 —— 只需 `check_effect_contact` 白名單擴 `Live` scope,`send_order_framed` 出站路徑不變、不複製。seam 抽象有可信第二實作,非過早抽象。

---

## 2. 訂單狀態機(typed 設計 + P0-prone 標記)

### 2.1 型別基座(已 source-ready,W7 不重造)

`openclaw_types` 已提供:
- `IbkrPaperOrderLifecycleState`(14 態):`LocalIntentCreated → RustAuthorityAccepted → BrokerSubmitRequested → BrokerAcknowledged → PartiallyFilled → Filled` 主鏈;`CancelRequested→Cancelled`、`ReplaceRequested→Replaced`、`Rejected`、`Inactive`、`StateUnknown`、`ManualReviewRequired` 支線。
- `is_transition_allowed` / `is_operation_transition_allowed`(const,窮舉 match):合法遷移矩陣已 pin;`StateUnknown` 唯 `ManualReviewRequired` 或 terminal-with-evidence 可出。
- `BrokerLifecycleEventLogV1`:append-only hash chain(`previous_event_hash`/`event_hash`/`event_sequence`/`genesis_event`)+ `idempotency_key` + `order_local_id`/`broker_order_id`/`execution_id`/`commission_report_id` + `raw_artifact_hash`/`redacted_summary_hash`。
- `classify_ibkr_paper_restart_recovery`:重啟恢復分類(terminal+evidence → 保留;否則 `MarkStateUnknown`)。

### 2.2 W7 engine 待建 runtime driver

**Module**:`ibkr_tws_order_lifecycle.rs`(新;純同步狀態機,注入時鐘,無 socket/async,承 order_exec_data 全慣例)。

1. **Intent journal(先寫意圖後發送)**:任何 order verb 出站**前**,先 append `LocalIntentCreated → RustAuthorityAccepted` 事件進 hash-chain journal(durable)。send 後才 append `BrokerSubmitRequested`。重啟 = replay journal → `classify_ibkr_paper_restart_recovery` 對每筆未終態 order 定姿態(未確認 = `MarkStateUnknown` → 對賬前凍結)。
2. **preview(whatIf)**:`placeOrder` with `whatIf=true` 是**零效果預覽**(broker 回 margin/commission 預估,不成單)。設計上 whatIf frame 仍走 `send_order_framed`(它是 order-verb 訊息,受 INV-ORDER;但活化裁決可對 whatIf 給較寬 scope —— **設計決策:whatIf 仍需 effect envelope**,因它觸 order channel,保守 fail-closed;IB 现勘確認 whatIf 是否真零效果)。
3. **place → ack/reject → partial fills → filled/cancelled/replaced**:orderStatus/openOrder/execDetails 推送驅動遷移;**唯一 mutator** `apply_lifecycle_event(event) -> Result<State, Reject>`(Bybit 幻影倉教訓移植:單一狀態 mutator,無第二寫入路徑)。
4. **`nextValidId` 管理 + order-id drift recovery**:`nextValidId` 取自 session `Ready(serverVersion, managedAccounts, nextValidId)`;本地遞增分配 order-id;**冪等真源 = `idempotency_key`(client order key)非 order-id** —— 重連後 broker 回的 order-id 可能漂移,以 idempotency_key join intent journal。
5. **in-flight 斷線 → resync**:重連後以 broker 為真值(`reqOpenOrders`+`reqExecutions`,W5-S3 已 build 唯讀 builder)對 intent journal **三向對賬**(§3)。

### 2.3 P0-prone 面標記(狀態機內)

- **(P0-A) reduce-only fail-closed**:cancel/replace 與 fill 的競態(Bybit 幻影倉根因:PositionUpdate/Fill 無序雙寫)。設計:狀態機的 fill 應用與 cancel 應用共用單一 mutator,reduce-only 語義 fail-closed(無法證明減倉安全即拒)。
- **(P0-B) unknown terminal = fail-closed 凍結 symbol**:任何 order 落 `StateUnknown` 且無法對賬到 terminal-with-evidence → 遷 `ManualReviewRequired` + 告警 + **凍結該 symbol 的後續下單**,人工/reconciler 裁決前不再對該 symbol 發 order verb(型別已強制 `StateUnknown` 出口窄)。
- **(P0-C) idempotency 錯配**:重複事件(execDetails 推送慣稱 reqId -1、無序 commissionReport,W5-S3 已註)以 execId/idempotency_key 去重;**禁按 pending 匹配失敗丟棄**(W5-S3 unsolicited 通道慣例移植)。

---

## 3. Cash-account 約束引擎(結構設計;官方規則歸 IB 现勘)

### 3.1 定位

**Module**:`ibkr_cash_account_constraints.rs`(新;**deterministic policy engine** —— 承 root principle「deterministic routing/retries/data transforms belong in code」,非 model judgment)。純函數 gate,跑在 **Rust authority accept 之後、order frame build 之前**。

`fn evaluate(intent: &OrderIntent, account: &CashAccountState, instrument: &InstrumentState, rules: &CashAccountRules, calendar: &TradingCalendar) -> Result<(), CashConstraintDenial>`

- `CashAccountState`:承 W5 帳戶面(settled/unsettled cash、positions)。
- `CashAccountRules`:**注入式 config**,承載 T+1 offset / GFV 定義 / LULD 帶寬 / RTH 窗 —— **官方數值全歸 IB 现勘**,設計只留接口,不硬編未證規則(避免 R6/R8/R11 官方政策憑記憶寫錯)。
- `TradingCalendar`:承 W6 日曆(交易日/RTH/半日)。

### 3.2 約束項(v1;結構在,規則參數 IB 现勘)

| 約束 | 結構設計 | 規則來源 |
|---|---|---|
| **settled-funds 台帳(T+1)** | ledger 分 settled/unsettled tranche,各帶 settlement-date;買入只用 settled cash | T+1 regular-way settlement offset → IB 现勘 + W6 calendar |
| **GFV 防護** | 每 symbol 追 unsettled-buy → 若在結算前賣出即 GFV → 拒 | GFV 精確定義/計次 → IB 现勘(§4.4 標 UNVERIFIED) |
| **no-short** | sell qty ≤ 既有 long position(W5 positions) | 硬邊界(short 永久 denied) |
| **RTH-only** | order time ∈ regular trading hours | W6 calendar(America/New_York + DST) |
| **order-type 白名單** | v1 只允 `LMT`/`MKT` × `DAY`(型別已 `Market`/`Limit` × `Day`/`Gtc`,v1 限 Day) | 本包裁定 |
| **fractional 拒** | 非整數 qty → 拒(v1) | 本包裁定 |
| **LULD / halt 拒** | instrument halt/LULD 狀態下 order → 拒 | W6 market data 狀態 + IB 现勘帶寬 |

**Second-adapter test**:live-scope(EA7)復用同一約束引擎,只換 `CashAccountRules`(tiny-live caps)—— 引擎不 branch venue。
**Locality test**:約束政策與其執行 authority(Rust engine)同置;規則參數與其驅動的判定同置(注入 config),不散落。

---

## 4. Option B HMAC 批准升級(W7 blocking 前置;憲法面)

### 4.1 觸發與定位

AMD-2026-07-08-01 澄清 #2:**paper order-write / 資本暴露面 = 強制升級 option B(HMAC-signed,與 `authorization.json` 同紀律)**,option A(W2 seal 6-binding owner-only 檔)僅限 read-only / zero-money gate-seal。W7 落地 paper order-write 即命中觸發器 → **option B 為 W7 blocking 前置**,必落於 **S4**,且與 W8 活化紀錄設計合流(W8 吸收)。

**禁擴鐵律(承 W2 設計 §5)**:W2 caller 的批准檔格式 / 6-binding 驗證器 / ledger 語義**不得被複用或順手擴充**到 order-write 面 —— 那是不同 authorization 軸(live-money 執行軸)。option B 是新軸。

### 4.2 Interface:HMAC 簽名層 疊在 effect-scope envelope 上

**先例(second adapter 已存在)**:`openclaw_engine/src/live_authorization.rs` —— Bybit live `authorization.json`:`HmacSha256` + `canonical_payload`(pipe-separated 正規化)+ `compute_signature` + **constant-time 比對** + `expires_at_ms` + typed `AuthError`。IBKR option B **平行**此紀律,不共用其軸。

option B = effect-scope 活化的**簽名 leg**,疊在 W8a envelope shape 之上。W7-S4 擴 `IbkrActivationOperationScopeV1` 增 `Paper` scope(承 W8a→W8 吸收模式),並落 `check_effect_contact`:

```
check_effect_contact(envelope, operation, posture, ledger, sig_verifier) -> EffectVerdict
  1. envelope.validate(now_ms)            [shape/綁定/時窗;承 W8a]
  2. build_sha / revocation / kill-switch epoch 比對  [承 W8a posture]
  3. seal≠活化(seal 在位無 envelope → 拒)  [承 W8a]
  4. operation verb 白名單(paper submit/cancel/replace 放行;live/margin/short/options/cfd/transfer 仍拒)
  5. ★option B:HMAC 簽名 over canonical payload == Operator 驗證金鑰   [新 leg]
  6. nonce 原子消費(承 W8a ledger)
  → Ok(OrderEffectPermit::mint())         [唯一鑄造點;§1.3]
```

### 4.3 憲法面(CC 審點,標記)

- **CC-B1 金鑰 custody**:硬邊界要求「Rust-owned, authenticated Operator activation record」+「no env-var credential fallback」。**option B 的 HMAC 金鑰不得複用 Bybit `OPENCLAW_LIVE_AUTH_SIGNING_KEY` env-var 模式作為唯一來源** —— 需 Rust secret-slot custody。CC 審點:金鑰來源、輪替、缺席 fail-closed。
- **CC-B2 fail-closed 先寫拒絕**:簽名驗證在任何 accept 之前;bad-signature / missing-key / expired 各 typed。承 W8「一律先寫拒絕路徑再寫放行路徑;test-only 放行必 `#[cfg(test)]` + E3 專項掃描」。
- **CC-B3 cross-runtime parity(Python 不成 authority)**:Python/FastAPI/GUI 只能 request/display 活化流程,**不得創建/更改/轉發原始授權材料或代 attest**。option B 簽名/驗證全 Rust-owned;IPC 只轉 opaque 簽名 blob,不解析。cross-runtime parity test:Python schema 不得出現簽名構造能力。
- **CC-B4 P2 seal≠option B**:option A seal(W2)與 option B effect-activation 是兩軸;W7 需機器證明「sealed Phase-2 PASS artifact 在位 + 無 effect envelope → order 拒」(承 W8a `SealIsNotActivationAuthority` 擴到 effect 面)。
- **CC-B5 global Cost Gate 不得因本 lane 降低**;Guardian / Decision Lease lineage 綁定進 effect envelope(型別已有三 lineage 欄)。

---

## 5. 前置契約(machine-check + IPC 方法矩陣)

### 5.1 `broker_capability_registry_v1` machine-check(ADR 硬序)

`stock_etf_broker_capability_registry.rs` 型別已在(REQUIRED_OPERATIONS 含全 verb + allowed/denial_reason 矩陣)。W7-S0 落 **engine machine-check**:effect-capable paper-route 的 order builder / `send_order_framed` **編譯期或啟動期**斷言 —— capability registry 必須 admit `PaperOrderSubmit/Cancel/Replace`(且 `LiveOrderSubmit/Margin/Short/Options/Cfd/Transfer` 恆 denied)方可存在該路徑。ADR 硬序:registry machine-check 先於任何 effect 路徑實作。

### 5.2 `lane_scoped_ipc_v1` preview/submit/cancel/replace 方法矩陣

`stock_etf_lane_scoped_ipc.rs` 已含 `PreviewPaperOrder/SubmitPaperOrder/CancelPaperOrder/ReplacePaperOrder` 於 REQUIRED_METHODS + PREVIEW_FIELDS/SUBMIT_PAPER_ORDER_FIELDS。W7 落 **engine IPC handler**(`ipc_server/handlers/stock_etf.rs`;**現 17 method 全 GET-only,這是首批 mutate-verb**):

| 面 | 設計紀律 |
|---|---|
| **Rust-owned** | 訂單/風控/授權真值全在 Rust;IPC handler = parse→call engine→format |
| **Python thin relay** | Python/FastAPI 只轉發 request、display 結果;不成 order/risk/activation authority;不解析簽名材料(CC-B3) |
| **typed denial** | default-inactive:無 effect envelope → 回 typed `EXTERNAL_VERIFICATION_PENDING`/envelope-absent denial(非 fake-success,承 AMD-07-08 $0.00 誠實缺陷修復精神) |
| **與 Bybit paper IPC 顯式分離** | 不復用 Bybit paper IPC 路徑(跨 lane 鐵律);lane-scoped method 命名空間獨立;bybit-live-unchanged 回歸 |

**注意 FastAPI Depends × reload 凍結陷阱**(在案教訓):新 mutate route 的 method 分區守衛白名單需同 PR 顯式修訂 + route module 與 main 同步 reload / 就地刷新 env 派生態。

---

## 6. 切片計劃 S0-S4

原則:每片可獨立 E1 實作 + E2/E3/IB/CC/QA 審;**一輪一 PR**;並行片 file-surface manifest 不相交(loop v2 manifest 程序把關);DoD 對照 fake-TWS 情景矩陣。

| 片 | 主題 | 檔案面(engine/types 主) | 依賴 | 並行 | risk | reviewer 集 |
|---|---|---|---|---|---|---|
| **S0** | **前置契約 machine-check + transport-gating 骨架(blocking 前綴)** | `stock_etf_broker_capability_registry`(engine check)、`OrderFrame`/`OrderEffectPermit`/`EffectEnvelopeRequiredStub`/`send_order_framed`(session/driver)、`check_effect_contact` **恆拒 stub**、4 structure test 入 CI | W3/W5/W6(源碼) | — | **HIGH(authority)** | E2, E3, IB, **CC** |
| **S1** | **訂單狀態機 driver + intent journal(不送出)** | `ibkr_tws_order_lifecycle.rs`(新):14 態 runtime driver + append-only journal + 單一 `apply_lifecycle_event` mutator + nextValidId + idempotency + whatIf builder(產 `OrderFrame`,無 production send)+ restart recovery | S0 | — | **HIGH** | E2, E4, IB, QA |
| **S2** | **cash 約束引擎(deterministic pre-submit gate)** | `ibkr_cash_account_constraints.rs`(新):settled-funds ledger + GFV + no-short + RTH + order-type 白名單 + fractional + LULD/halt;注入 `CashAccountRules`(IB 现勘規則參數) | S1(共 OrderIntent 型別) | (與 S3 部分可交錯;同 engine 面建議序列) | **HIGH(cash 正確性)** | E2, **IB(现勘)**, QA |
| **S3** | **三向對賬引擎(P0 核心)** | reconciliation engine:broker 真值(reqOpenOrders+reqExecutions,W5-S3)× intent journal × 本地態;無序 join tolerant;差異 fail-closed;unknown-terminal 凍結 symbol + 告警;reduce-only fail-closed | S1 | — | **P0/HIGH** | E2, E4, IB, QA, **CC(fail-closed)** |
| **S4** | **option B HMAC + `check_effect_contact` + IPC 接線 + fake-TWS 全矩陣 + 收口** | envelope 擴 `Paper` scope、HMAC 簽名 leg、`check_effect_contact` 放行臂(鑄 `OrderEffectPermit`)、金鑰 custody(secret-slot)、IPC preview/submit/cancel/replace handler、Python thin relay、full fake-TWS 情景矩陣 | S0-S3 | — | **P0/HIGH(effect+authority)** | E2, E3, IB, **CC**, QA |

### 6.1 依賴序 + blocking 前置

```
S0 (blocking 前綴:恆拒 stub 先落) → S1 → S2 → S3 → S4 (option B 放行臂;EA5 blocking)
```

- **option B 何時必落**:S4。S0 先落 `check_effect_contact` **恆拒 stub**(承 W3 permit-stub 模式:先寫拒絕路徑);S4 才落 HMAC 放行臂。**INV-ORDER 全程成立**(S0→S3 期間 effect permit 零鑄造)。option B 必須在 **EA5 paper 窗開啟前**落地(§6 EA5 硬前置 = W7+W8 全綠 + option B);W8 全包吸收 option B 進完整活化紀錄(readonly+paper+tiny-live+live 共用同一驗證代碼路徑,禁語義漂移)。
- **W8 交接**:S4 的 `EffectEnvelopeRequiredStub` / `check_effect_contact` 是 W8 完整 envelope 驗證器的 effect-scope 前身;W8 落 production TCP factory 時做**四聯 permit audit 第二階段擴張**(承 E3-F1),涵蓋 order-verb send-path 檔。
- **reactivation**:承 W3 移交 —— W8 接 reactivation 時須重置 pacing governor;W7 增:reconnect 後 intent journal 未終態 order 一律 `MarkStateUnknown` → 對賬前凍結(不續用舊授權;nonce 一次性)。

### 6.2 DoD 對照 fake-TWS 情景矩陣(承 §5-W7 DoD)

fake-TWS(`openclaw_fake_tws` dev-crate,15 場景種子)必覆蓋:正常鏈、部分成交、拒單各族(reject 100/200/201/...)、重連中 in-flight、重啟對賬、重複事件(無序 execDetails/commissionReport)、GFV/short/RTH/halt/fractional 拒絕、unknown-terminal 凍結;**貫穿不變量測試:無 effect envelope ⇒ transport 層拒發任何 order 訊息**(S0 structure test + S4 runtime 測試雙證);readonly envelope + 任何 order verb → 拒;seal 在位無 effect envelope → 拒。全片零真 socket;Mac+Linux cargo 綠。

---

## 7. 硬邊界自查(§2 全套 + 幻影倉教訓)

- **永久 denied**:`margin/short/options/cfd/transfer/account-write` —— `check_effect_contact` operation 白名單**結構性拒**(承 `readonly_operation_blocker` 窮舉 match,新增 verb 編譯期強制重審);capability registry machine-check 斷言恆 denied。
- **W7 order builder 合法但 gated**:AMD-07-11 development 授權內;必 transport envelope-gated(INV-ORDER)+ default-inactive(B′ DCE)+ fake-TWS only + 零真接觸。
- **唯一 mutator + reduce-only fail-closed**:Bybit 幻影倉教訓(PositionUpdate/Fill 無序雙寫競態)直接移植 —— `apply_lifecycle_event` 單一狀態 mutator,reduce-only 無法證明即拒。
- **對賬三原則寫死**:broker 真值 / intent journal 對照 / 差異 fail-closed(S3)。
- **Bybit crypto_perp live 不受影響**:跨 lane 鐵律,每 gate 帶 bybit-live-unchanged 證明;不復用 Bybit paper IPC;IB reviewer 用 IB agent。
- **Python 不成 order/risk authority**:Rust-owned,Python thin relay;簽名材料不入 Python(CC-B3)。
- **憑證 custody Rust-only**:無 Python/FastAPI/GUI 明文 ingress;option B 金鑰 secret-slot 非 env fallback(CC-B1)。

---

## 8. 深度測試結論(architecture-depth-review)

- **Deletion test**:`OrderEffectPermit`/`OrderFrame` seam 刪除 → INV-ORDER 崩(§1.3);cash 約束引擎刪除 → GFV/short/over-buy 違規放行;三向對賬引擎刪除 → 幻影倉 P0 復現。三 Module 各承載唯一不變量,非 ceremonial。
- **Second-Adapter test**:live-scope(EA7)是 transport seam / cash 引擎 / option B 的可信第二消費者,只擴 scope 白名單 + 換 rules config,不複製 policy、不 branch venue。抽象成立非過早。
- **Authority/trust test**:effect 授權真源 = Rust `check_effect_contact` + option B HMAC(out-of-band Operator 簽名);Python 標籤 / packet-local digest / GUI 狀態皆 integrity-only,不授權。envelope 存在 ≠ 活化(nonce 原子消費 + epoch 比對)。
- **Cross-runtime parity test**:Python schema 不得出現簽名構造 / order authority;IPC 只轉 opaque blob。
- **Failure/recovery test**:in-flight 斷線 → broker 真值 resync;重啟 → journal replay + `MarkStateUnknown`;unknown-terminal → 凍結 + 人工裁決;nonce 一次性 → reconnect 換新 envelope;鎖中毒 → fail-closed。recovery owner = reconciler + Operator(ManualReviewRequired)。
- **Consumption test**:XL 拆 5 片一輪一 PR,file-surface manifest 並行程序把關;S2/S3 同 engine 面建議序列避免撞工;reviewer 帶寬為主變異源(§5.5)。

### 對抗性第二思考

最小反例:**S4 落 option B 放行臂後,production 是否可能鑄 `OrderEffectPermit`?** —— 只要 production 無有效 effect envelope(無簽名金鑰、無 Operator 紀錄、default-inactive),`check_effect_contact` 恆走拒絕臂,零鑄造(INV-ORDER 二元成立,同 INV-1 模型:capability 進 default build,activation 由 envelope runtime-gate)。但**殘留風險**:S4 若把「envelope 存在」誤當「activation 完成」而提前鑄 permit(先寬後緊)→ 授權事故。緩解:S4 必須 nonce 消費 + HMAC 驗證**在鑄造之前**,且 E3 專項掃描 test-only 放行臂 `#[cfg(test)]` 邊界(承 W8 風險條)。此反例在 S4 review 必逐項對抗,不可自評放行。

---

## 9. 實作 owner + 獨立驗證路徑

- **實作 owner**:E1(Rust engine writer),按 S0-S4 逐片;PA 不寫實作代碼。
- **獨立驗證**:每片 E2(獨立源審)→ E4(對抗核驗)硬邊;authority/security 面加 **E3 + CC**;IBKR 語義加 **IB**(官方政策現勘,BB 不能替);end-to-end 宣稱加 **QA**;S2 cash 規則參數 blocking 於 IB 现勘(T+1/GFV/LULD/RTH 官方數值)。
- **申報紀律**:§3 梯度詞彙;W7 DoD 封頂 `source-ready`;fake-TWS 為唯一「接觸」;真活化全屬 EA5+(Operator-gated)。

---

## 10. 建議 R24 起首切片

**W7-S0**(前置契約 machine-check + transport-gating 骨架,blocking 前綴)。理由:
1. 承 W3 先例 —— permit-stub / 拒絕路徑先於一切放行落地(先寫拒絕再寫放行,授權面最忌先寬後緊)。
2. INV-ORDER 是 W7 全包的 fail-closed 地基;S1-S4 全騎其上。S0 先鎖住 order-verb 出站閘點(恆拒 stub),後續片即使中途未收口,production 仍零 order frame 出站。
3. 檔案面(capability check + transport seam + structure test)與 W6 / 其他並行面不相交,可即刻派工。
4. CC/E3 在 S0 先建立 authority seam 的審計基線,S4 option B 放行臂時 review 有錨。

---

## 附:as-built 依賴指針(實作參照,非重造)

| W7 待建 | 騎乘的既有面(main @ `2613daf14`) |
|---|---|
| transport seam | `ibkr_tws_session.rs`(`PermitToken`/`ConnectPermitProvider`/`EnvelopeRequiredStub`)、`ibkr_tws_driver.rs`(`send_framed`/`OutboundGrant`/`TransportFactory`) |
| 狀態機型別 | `openclaw_types::ibkr_paper_lifecycle`(`BrokerLifecycleEventLogV1`/`is_transition_allowed`/`classify_ibkr_paper_restart_recovery`)、`stock_etf_lane::IbkrPaperOrderLifecycleState` |
| order request | `openclaw_types::stock_etf_paper_order_request`(`StockEtfPaperOrderRequestEnvelopeV1`) |
| 唯讀對賬 builder | `ibkr_tws_order_exec_data.rs`(reqExecutions/reqOpenOrders/reqAllOpenOrders,W5-S3) |
| 帳戶/持倉 | `ibkr_tws_account_data.rs`(W5-S2,`SnapshotStaleness` 六態) |
| effect activation | `ibkr_activation_envelope_check.rs`(`check_readonly_contact`/`ActivationNonceLedger`/`readonly_operation_blocker`,W8a)→ 擴 `check_effect_contact` |
| envelope 型別 | `openclaw_types::ibkr_activation_envelope`(`IbkrActivationEnvelopeV1`/`IbkrActivationOperationScopeV1`)→ 擴 `Paper` scope |
| option B 先例 | `openclaw_engine::live_authorization`(`HmacSha256`/`canonical_payload`/`compute_signature`/constant-time compare) |
| 前置契約 | `stock_etf_broker_capability_registry`、`stock_etf_lane_scoped_ipc`(Preview/Submit/Cancel/Replace 方法矩陣已在) |
| IPC handler | `ipc_server/handlers/stock_etf.rs`(現 17 GET-only method;W7 首批 mutate-verb) |
