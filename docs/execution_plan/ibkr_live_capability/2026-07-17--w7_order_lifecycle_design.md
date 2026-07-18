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

### 1.5 encode ceiling guard(IB 现勘增補;transport-gating 不變量的 encode 對稱面)

W5-S3 有 decode ceiling guard(sv>157 定長尾欄 UNVERIFIED → 拒收 frame)。IB 现勘(2026-07-17)指出:**placeOrder/cancelOrder 是定長位置編碼(非 head-prefix)**,encoder 必逐欄輸出到 negotiated band 末欄 —— 故 encode 側需**對稱 ceiling guard**:

> **INV-ORDER-ENCODE**:`send_order_framed` 的上游 encoder 對 negotiated `serverVersion > 157` **一律拒絕產出下單訊息 + audit**,**禁用 157 佈局猜送**(server 位移/reject 風險)。sv∈[145,157] band 骨架確定方可 encode(placeOrder 末欄=`usePriceMgmtAlgo`@151;cancelOrder ≤157 band=`[4, VERSION=1, orderId]`,無 `manualOrderCancelTime`)。

此 guard 是 transport-gating 不變量的一部分(decode ceiling 的 encode 鏡射);歸 **S1**(encoder 所在片),structure/runtime 雙證。

**Deletion test**:刪 `OrderEffectPermit`/`OrderFrame` seam → order frame 可經通用 `send_framed` 在僅 connect/readonly permit 下出站 → INV-ORDER 崩、EA 跑道 readonly soak 期無法阻擋 order verb。⇒ seam 非 ceremonial,承載唯一不變量。
**Second-adapter test**:live-scope order verb(EA7 tiny-live)是同一 seam 的第二消費者 —— 只需 `check_effect_contact` 白名單擴 `Live` scope,`send_order_framed` 出站路徑不變、不複製。seam 抽象有可信第二實作,非過早抽象。

---

## 2. 訂單狀態機(typed 設計 + P0-prone 標記)

### 2.0 wire 事實(IB 现勘 2026-07-17,ibapi 9.81.1 hash-pinned + IBKR 官方)

- **msg ID**:OUT `PLACE_ORDER=3`(**含 whatIf flag**)/ `CANCEL_ORDER=4` / `REQ_IDS=8`;IN `NEXT_VALID_ID=9` / `ORDER_STATUS=3`(12 定長欄,repo 已 pin)/ `OPEN_ORDER=5`。
- **replace = 無獨立 msg**:replace verb 實體 = 同 `PLACE_ORDER=3` **覆蓋同 `orderId`**。故 `OrderFrame` 只需 place/cancel 兩 encoder;replace 是 place-with-existing-orderId 的語義層封裝(狀態機遷 `ReplaceRequested→Replaced`,transport 仍走 place encoder)。
- **placeOrder = 定長位置編碼(非 head-prefix)**:encoder 必逐欄輸出到 band 末欄(sv≥145 省前導 VERSION);STK 現金天然塌縮 comboLegs/deltaNeutral/algo/conditions **變長塊(但仍送 count/flag 欄,非整段消失)**;承載欄 = action / totalQuantity(sv≥101 float)/ orderType / lmtPrice / auxPrice / tif / account / transmit / outsideRth / cashQty(sv≥111 fractional)/ whatIf;sv≤157 末欄 = `usePriceMgmtAlgo`(@151)。
  - **2026-07-17 更正(IB DIVERGENT-1,S1 重導後 CONFIRMED-vs-9.81.1)**:原「承載欄」子集列舉 **不忠實**——placeOrder 尚含約 70 個 mandatory 定長標量欄(extended/shortSale/oca/volatility/scale/hedge/pta/deltaNeutralFlag/algo…)。S1 encoder 已**逐位對照 `client.py placeOrder`@896-1426 重導完整 ≤157 欄序**,並以 pinned ibapi 產出的 **byte-golden**(sv=145/148/151/157)round-trip 驗證。逐位事實:`whatIf`@1347 **在 `cashQty`@1398 之前**;`cashQty` 以 **plain make_field** 送 UNSET_DOUBLE 哨兵(**非 handle_empty**,空欄陷阱);`discretionaryUpToLimitPrice`(sv≥148)/`usePriceMgmtAlgo`(sv≥151)為 band 內 sv-gated 條件欄。故 placeOrder ≤157 佈局 **CONFIRMED**(非「骨架確定」)。
- **cancelOrder ≤157 band** = `[4, VERSION=1, orderId]`,**無 `manualOrderCancelTime`**(10.x sv≥161 才加 → DIVERGENT,見 §11 BLOCK-ORDER-BAND-2)。CONFIRMED-vs-9.81.1 `client.py cancelOrder`@1429。
- **nextValidId 管理**:`REQ_IDS=8`(OUT)請求 → `NEXT_VALID_ID=9`(IN)回;order-id 本地遞增;冪等真源仍是 `idempotency_key`(§2.2.4)。
- **error code(2026-07-17 更正)**:原「`10147` 官方查無」**事實錯誤**——`10147`(orderId not found)與 `10148`(order cannot be cancelled, state:…)**皆真** IBKR 碼。S4 reject 族按官方語義**分碼**(10147=查無 orderId;10148=態不可撤),非二選一。此為 S4 註記(S4 落)。

### 2.1 型別基座(已 source-ready,W7 不重造)

`openclaw_types` 已提供:
- `IbkrPaperOrderLifecycleState`(14 態):`LocalIntentCreated → RustAuthorityAccepted → BrokerSubmitRequested → BrokerAcknowledged → PartiallyFilled → Filled` 主鏈;`CancelRequested→Cancelled`、`ReplaceRequested→Replaced`、`Rejected`、`Inactive`、`StateUnknown`、`ManualReviewRequired` 支線。
- `is_transition_allowed` / `is_operation_transition_allowed`(const,窮舉 match):合法遷移矩陣已 pin;`StateUnknown` 唯 `ManualReviewRequired` 或 terminal-with-evidence 可出。
- `BrokerLifecycleEventLogV1`:append-only hash chain(`previous_event_hash`/`event_hash`/`event_sequence`/`genesis_event`)+ `idempotency_key` + `order_local_id`/`broker_order_id`/`execution_id`/`commission_report_id` + `raw_artifact_hash`/`redacted_summary_hash`。
- `classify_ibkr_paper_restart_recovery`:重啟恢復分類(terminal+evidence → 保留;否則 `MarkStateUnknown`)。

### 2.2 W7 engine 待建 runtime driver

**Module**:`ibkr_tws_order_lifecycle.rs`(新;純同步狀態機,注入時鐘,無 socket/async,承 order_exec_data 全慣例)。

1. **Intent journal(先寫意圖後發送)**:任何 order verb 出站**前**,先 append `LocalIntentCreated → RustAuthorityAccepted` 事件進 hash-chain journal(durable)。send 後才 append `BrokerSubmitRequested`。重啟 = replay journal → `classify_ibkr_paper_restart_recovery` 對每筆未終態 order 定姿態(未確認 = `MarkStateUnknown` → 對賬前凍結)。
2. **preview(whatIf)**:`placeOrder` with `whatIf=true` 是**零效果預覽**(broker 回 margin/commission 預估,不成單)。whatIf frame 仍走 `send_order_framed`(它是 order-verb 訊息,受 INV-ORDER;**設計決策:whatIf 仍需 effect envelope**,因它觸 order channel,保守 fail-closed)。
   - **★R18 衝突 seam(IB 现勘)**:whatIf 的 OrderState(status/initMargin*/maintMargin*/equityWithLoan*/commission/minCommission/maxCommission/commissionCurrency/warningText,sv≥142)在 `OPEN_ORDER=5` 訊息內。**preview 功能前置 = 讀此 OrderState 塊**。
   - **2026-07-17 更正(IB DIVERGENT-2,silent-wrong-value)**:原述「OrderState **尾在訊息尾端**、可反向索引」**結構性錯誤**。逐位對照 `decoder.py processOpenOrder`@201-205 + `orderdecoder.py`:`decodeWhatIfInfoAndCommission`(warningText 收尾)**之後仍有約 19 欄**(VolRandomizeFlags 2 / conditions / adjustedOrderParams 8 / softDollarTier 3 / cashQty / dontUseAutoPriceForHedge / isOmsContainers sv≥145 / discretionaryUpToLimitPrice sv≥148 / usePriceMgmtAlgo sv≥151…)。OrderState **深埋 mid-message**,前後皆變長塊 → **無定長正/反索引可達**(=W5-S3 openOrder head-prefix descope 之因)。反向索引 `len-15` 會把訊息尾欄誤讀為 margin → **靜默錯誤估值**。**S1 處置 = fail-closed**:frame 面 preview 一律回 typed `PreviewDecodeBlockedPendingFullSequence`,絕不回結構錯誤 margin;OrderState 塊**內容/序** CONFIRMED(單元 `decode_whatif_order_state_block`),唯**定位**待**全序列解碼**(§11 BLOCK-ORDER-BAND-5,blocked-until)。whatIf **builder**(placeOrder 的 whatIf flag OUT 面)不受影響,已於 S1 encoder 含。
3. **place → ack/reject → partial fills → filled/cancelled/replaced**:orderStatus/openOrder/execDetails 推送驅動遷移;**唯一 mutator** `apply_lifecycle_event(event) -> Result<State, Reject>`(Bybit 幻影倉教訓移植:單一狀態 mutator,無第二寫入路徑)。
4. **`nextValidId` 管理 + order-id drift recovery**:`nextValidId` 取自 session `Ready(serverVersion, managedAccounts, nextValidId)`;本地遞增分配 order-id;**冪等真源 = `idempotency_key`(client order key)非 order-id** —— 重連後 broker 回的 order-id 可能漂移,以 idempotency_key join intent journal。
5. **in-flight 斷線 → resync**:重連後以 broker 為真值(`reqOpenOrders`+`reqExecutions`,W5-S3 已 build 唯讀 builder)對 intent journal **三向對賬**(§3)。
6. **★ApiPending 態分流(IB 现勘;W5-S3「ApiPending W7 前解」carry-forward 的解)**:IB 的 `ApiPending` = 訂單尚未送達 IB server 的**合法暫態前置狀態**(非錯誤、非終態);W5-S3 現把它當 `UnknownDenied` 毒化 open-orders 面 → benign security-def 延遲時**誤毒**。設計:`ApiPending` 歸**獨立 transient-pending 態 + 有界 timeout**,逾時才升級 `denied`/poison,與真 unknown(`StateUnknown`,§2.3 P0-B)分流。**歸片 S1**(狀態機 態分流);此片同時解 W5-S3 carry-forward。

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

| 約束 | 結構設計 | 規則來源(IB 现勘 2026-07-17 CONFIRMED,設計留接口) |
|---|---|---|
| **settled-funds 台帳(T+1)** | ledger 分 settled/unsettled tranche,各帶 settlement-date;買入只用 settled cash | **T+1 settlement(SEC 2024-05-28 生效)**:cash 賣出所得待清算結算;offset 進 `CashAccountRules` + W6 calendar |
| **GFV 防護(free-riding)** | 每 symbol 追 unsettled-buy → 若結算前賣出即 violation → **下單前查 settled-cash 拒** | **GFV/free-riding 官方**:未結算資金買入後結算前賣出=violation |
| **no-short** | sell qty ≤ 既有 long position(W5 positions) | **cash account 禁融券**(硬邊界;short 永久 denied) |
| **RTH-only** | order time ∈ regular trading hours | W6 calendar(America/New_York + DST) |
| **LULD / halt 拒** | 暫停/熔斷 **pre-trade filter** → order `Inactive`/reject | **LULD/halt 官方**;W6 market data 狀態 |
| **order-type 白名單 v1** | 只允 `LMT`/`MKT` × `DAY`(型別 `Market`/`Limit` × `Day`/`Gtc`,v1 限 Day) | v1 裁定;**MOC/LOC 官方支援但列 W7 後續 opt-in** |
| **fractional 拒 v1** | 非整數 qty → 拒(v1) | v1 裁定;**fractional 官方支援(cashQty sv≥111)但列 W7 後續 opt-in** |

**settled-cash 前置門歸片 S2**(cash 約束引擎;`evaluate` 跑在 Rust authority accept 之後、order frame build 之前)。

**Second-adapter test**:live-scope(EA7)復用同一約束引擎,只換 `CashAccountRules`(tiny-live caps)—— 引擎不 branch venue。
**Locality test**:約束政策與其執行 authority(Rust engine)同置;規則參數與其驅動的判定同置(注入 config),不散落。

### 3.3 S2 IB 现勘裁定 + review rework(2026-07-17 loop R26,W7-S2 landed=PR#83)

E1 landed `ibkr_cash_account_constraints.rs`(engine-local policy engine,無 types 契約改);E2 APPROVE_WITH_NOTES + IB PASS_WITH_NOTES(官方出典齊全)。核心邏輯/fail-closed/i128 定點/T+1/no-short/RTH/白名單/fractional **CONFIRMED**。三處 rework 已落:

| 決策點 | IB 现勘裁定(官方出典) | S2 處置 |
|---|---|---|
| **T+1 settlement** | SEC 15c6-1(a)(T+1 標準,2024-05-28 生效) | offset 歸 `CashAccountRules.settlement_offset_business_days`(illustrative=1,待 EA 校準);結算日由 W6 calendar `Open`-day 序算,引擎不硬編 SEC 數值。**CONFIRMED** |
| **no-short(硬邊界)** | IBKR cash account 禁融券(short 永久 denied) | sell qty > 既有 long → `ShortSaleDenied`(此 gate + S4 `check_effect_contact` 白名單雙證)。**CONFIRMED** |
| **RTH-only** | IBKR RTH 語義(America/New_York + DST) | now_ms ∈ W6 `Open` session,DST-aware。**CONFIRMED** |
| **order-type 白名單** | LMT/MKT × DAY;IOC/MOC/LOC 官方支援 | v1 只 LMT/MKT×DAY;GTC opt-in(`allow_gtc`);MOC/LOC/IOC **forward-reserved**(`StockEtfPaperOrderType` 契約當前僅 Market/Limit,擴變體前 inert)。**CONFIRMED** |
| **fractional** | 官方 cashQty(sv≥111)支援 | v1 拒非整數(`allow_fractional` opt-in)。**CONFIRMED** |
| **★MKT 資金 buffer(修 MED-1 唯一 fail-open)** | 官方 Available-for-Trading 對即時可用資金檢查,MKT 以估價保留(cash 不可負) | 新 `marketable_buffer_bps`(注入,illustrative=100bps);MKT 成本 `ref×(1+bps/10000)` **向上取整保守高估** → fail-closed;**純 LMT 不套 buffer**(限價即成本上界)。 |
| **★GFV 語義收緊(修 E2 LOW-1 過度拒)** | 官方 GFV = 以**未結算資金**買入後、**該資金結算前**賣出;買入當下已足額 settled-funded **不構成 GFV**(Fidelity/IBKR/Schwab 一致) | `unsettled_buys` → **`unsettled_funded_buys`** rename;`UnsettledFundedBuyLot.funding_settlement_date` 綁**資金來源** tranche 結算日。因 S2 買入閘只放行 settled-funded 買入,此 map 於 S2 世界恆空 → 成為 S3 ledger 的 **defense-in-depth**,不再誤殺 settled-funded 賣。下單前硬拒方向保留(比 IBKR 更保守)。 |
| **★LULD venue-flag 權威 + 本地 band 不誤殺 limit(修 E2 NOTE-1)** | 官方 LULD=tiered(Tier1/2 × 價位分層 × 時段加倍 × 5-min-avg 參考)——單 f64 無法承載;交易所自算帶寬 | `luld_limit_state`/`halted`=**venue 權威 gate**(命中即拒,不受 filter 旗影響);本地 `luld_band_percent` 標 **approximate-only sanity**,**僅套 marketable 語境**(MKT / buy limit≥ref / sell limit≤ref);**resting limit(遠離現價,如 dip-buy)不以定價偏離誤判 LULD**。 |

**EA 校準清單(7 項 illustrative config,待 EA 现勘,非 W7 收口 blocker)**:①T+1 offset=1 ②LULD tier 帶寬(venue flag 為權威,本地 band 僅 sanity)③結算日曆 vs 交易日曆等價性 ④MKT `marketable_buffer_bps` ⑤unsettled-funded 語義(S3 ledger populate 時 pin)⑥halt/LULD 資料源(W6 mktData lane)⑦GFV 違規次數門檻(僅未來事後對賬)。

**carry(非 S2 fix)**:E2 LOW-2(已成熟 tranche 若上游同時滾入 settled_cash 又留 unsettled_tranches → 重複計數)= **S3 整合不變量**,S3 populate ledger 時 pin(S2 邏輯於其 disjoint 契約下正確)。

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

**S4a 實作序修訂(validation-first;R23 review 必修-2)**:實作將 step 4 的結構性 operation×scope 閘
**短路前置**(readonly+order→`OrderVerbStructurallyDenied` / margin·short·options·cfd·transfer·live→
`PermanentlyDeniedVerb` / paper+非order→`OperationOutsideEffectScope` / unknown→`EffectScopeDenied`),
paper+paper-order 方進 step 1(`validate_paper_effect` shape)→ step 2 posture → step 5 HMAC → step 6
nonce → mint。**簽名/nonce/鑄造前必先 shape 驗證**(canonical payload 非歧義性前提);deny path 不燒
nonce、不鑄 permit。

**canonical payload 規格(v2;R23 review 必修-1 簽名覆蓋擴欄)**:pipe-separated,**24 欄**,含版本前綴
(drift guard,v1→v2 舊簽名前向拒)+ §2 活化鐵律綁定面**全欄**——不僅 identity/window/operation 核心,
亦含 **session_attestation_fingerprint / risk_config_hash / 三額度(max_order·max_position·
max_orders_per_day) / 三治理 lineage(cost_gate·guardian·decision_lease,CC-B5) / operator_identity**。
欄序:

```
version | contract_id | source_version | asset_lane | broker | environment | operation_scope |
operation | build_git_sha | account_fingerprint | session_attestation_fingerprint | risk_config_hash |
max_order_notional | max_position_notional | max_orders_per_day | cost_gate_lineage | guardian_lineage |
decision_lease_lineage | operator_identity | activation_nonce | issued_at_ms | expires_at_ms |
revocation_epoch | kill_switch_epoch
```

**為何全欄簽**:build_sha/兩 epoch 既簽名又 posture 比對;上列擴欄在 W8 前**尚無 posture 現值比對**,
若不簽則除 shape(格式)外零綁定 → 持有效 (envelope,sig) 者可把某綁定欄換成另一**有效格式**值(如換
一枚合法 sha256 lineage / 調高額度)仍驗過,違「authenticated Operator activation record」+ CC-B5
lineage bound 硬邊界。**範疇界定**:本片只做**簽名覆蓋(tamper-proofing)**;上列欄的**值綁定 / posture
現值比對**(對 runtime-authoritative 值)仍**歸 W8**(與簽名軸不同軸),本片不做值強制。**pipe 非歧義性**:
除 `operator_identity`(shape 僅檢非空)外簽名欄經 shape 檢查為 pipe-free;實作以
`canonical_effect_payload` 內 `debug_assert!(operator_identity pipe-free)` + `verify()` doc-contract
(前提=envelope 已 shape-validate)明示不變量,防未來 caller 於未驗/自由格式欄重開跨欄 pipe-injection。

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
| **S1** | **訂單狀態機 driver + intent journal(不送出)** | `ibkr_tws_order_lifecycle.rs`(新):14 態 runtime driver + append-only journal + 單一 `apply_lifecycle_event` mutator + nextValidId(REQ_IDS=8/NEXT_VALID_ID=9)+ idempotency + place/cancel encoder(產 `OrderFrame`,**encode ceiling guard §1.5**,無 production send)+ whatIf builder + **openOrder tail decode 擴充(R18 衝突 seam)** + **ApiPending 態分流** + restart recovery | S0 | — | **HIGH** | E2, E4, IB, QA |
| **S2** | **cash 約束引擎(deterministic pre-submit gate)** | `ibkr_cash_account_constraints.rs`(新):**settled-cash 前置門(T+1/SEC 2024-05-28)** + GFV/free-riding + no-short + RTH + LULD/halt pre-trade filter + order-type 白名單(LMT/MKT×DAY)+ fractional 拒;注入 `CashAccountRules`(IB 现勘規則參數,MOC/LOC/fractional 列後續 opt-in) | S1(共 OrderIntent 型別) | (與 S3 部分可交錯;同 engine 面建議序列) | **HIGH(cash 正確性)** | E2, **IB(现勘)**, QA |
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

fake-TWS(`openclaw_fake_tws` dev-crate,15 場景種子)必覆蓋:正常鏈、部分成交、拒單各族(reject code 含 10148)、重連中 in-flight、重啟對賬、重複事件(無序 execDetails/commissionReport)、GFV/short/RTH/halt/fractional 拒絕、unknown-terminal 凍結;**whatIf preview(openOrder tail OrderState 解析)**、**ApiPending → transient-pending → 逾時升級 denied**、**replace=覆蓋同 orderId**、**encode ceiling(sv>157 拒產出 order 訊息)**;**貫穿不變量測試:無 effect envelope ⇒ transport 層拒發任何 order 訊息**(S0 structure test + S4 runtime 測試雙證);readonly envelope + 任何 order verb → 拒;seal 在位無 effect envelope → 拒。全片零真 socket;Mac+Linux cargo 綠。

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

## 11. IB 现勘納入(2026-07-17)歸片總表 + EA 前 band blocking

### 11.1 決策點 → 切片歸屬

| IB 现勘決策點 | 設計處置 | 歸片 |
|---|---|---|
| **①openOrder whatIf preview(R18 head-prefix 衝突)** | **2026-07-17 更正(DIVERGENT-2)**:OrderState 深埋 mid-message(非尾端)→ 無定長索引可達 → **S1 fail-closed(blocked)**,內容/序 CONFIRMED 但定位待全序列解碼 | **S1**(§2.2.2)/blocked→S3+EA |
| **②ApiPending 態** | 獨立 transient-pending 態 + 有界 timeout,與真 unknown 分流;解 W5-S3 carry-forward | **S1**(§2.2.6) |
| **③encode ceiling guard** | placeOrder/cancelOrder encoder 對 sv>157 拒產出 + audit,禁 157 佈局猜送;transport-gating 不變量 encode 對稱面(INV-ORDER-ENCODE) | **S1**(§1.5) |
| **settled-cash 前置門** | T+1(SEC 2024-05-28)/ GFV / no-short / LULD-halt / order-type / fractional | **S2**(§3.2) |
| **replace = 覆蓋同 orderId(無獨立 msg)** | `OrderFrame` 只 place/cancel 兩 encoder;replace=place-with-existing-orderId 語義封裝 | **S0/S1**(§2.0) |
| **option B HMAC** | effect activation 簽名 leg;**S4 blocking(EA5 paper 窗硬前置)** | **S4**(§4) |

### 11.2 EA3 前 blocking(order-band 10.x re-pin;D5 同源)

W7 在 **sv∈[145,157] band 開發 encoder(placeOrder/cancelOrder ≤157 佈局 **CONFIRMED-vs-9.81.1**,byte-golden 驗)**;**真接觸待 10.x re-pin + envelope**。以下標為 **EA 前置 blocking**(承 §4.4 gap matrix UNVERIFIED 紀律,IB 定期政策巡檢):

- **BLOCK-ORDER-BAND-1**:placeOrder 158-176 尾欄 UNVERIFIED(官方位元組未 pin;10.x band 佈局待現勘)。
- **BLOCK-ORDER-BAND-2**:cancelOrder 10.x `manualOrderCancelTime`(sv≥161)DIVERGENT(≤157 band 無此欄)。
- **BLOCK-ORDER-BAND-3(2026-07-17 修訂)**:whatIf openOrder decode——**≤157 定位本身即不可達**(OrderState 非訊息尾,深埋 mid-message,DIVERGENT-2)**且** 10.x 尾續增長。故非單純「10.x 增長」,而是**定位缺陷 + band 增長雙重**。
- **BLOCK-ORDER-BAND-4(新增)**:placeOrder 158-176 尾欄 / sv-gated 欄(`autoCancelDate`/`peggedRefPrice` 等 10.x)10.x re-pin(encode 側 ceiling guard 已 sv>157 拒產出覆蓋)。
- **BLOCK-ORDER-BAND-5(新增,blocked-until)**:whatIf preview **全序列解碼**(逐塊解 openOrder 至 OrderState 定位)+ EA 尾欄校準——S1 fail-closed(blocked),真接觸待此解碼落地(S3+)且 operator EA 校準;在此之前 preview 恆 `PreviewDecodeBlockedPendingFullSequence`。

encode 側均 **transport ceiling guard 覆蓋**(sv>157 拒 encode + audit,§1.5;INV-ORDER-ENCODE);decode 側 whatIf preview fail-closed。故 W7 source-ready 不被 band 未證阻塞;10.x re-pin + 全序列解碼是 **EA 活化前置**(operator follow-up + IB 现勘),非 W7 收口前置。**error code(更正)**:`10147`(orderId not found)與 `10148`(cannot be cancelled, state:…)**皆真** IBKR 碼,S4 按官方語義分碼。

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
