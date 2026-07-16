# W4 — connection-health IPC/route + normalizer lockstep 技術設計

**日期** 2026-07-16 | **loop** R7 | **TODO 行** `P1-IBKR-STOCK-ETF-FULL-LIVE-CAPABILITY-W4` | **狀態** PA design(未 commit;PM 收)
**權威** AMD-2026-07-11-01(development-only)+ AMD-2026-07-08-01 §Runtime Boundary + ADR-0048;`IBKR_TODO.md` §5-W4 為 DoD 正本
**紀律** read-only 除本檔;零真接觸/零 socket/零 secret;不確定 IB 外部事實標 `UNVERIFIED-IB`

---

## 0. 摘要與封頂

W4 把 W3 已建的 session FSM label(`IbkrTwsSessionManager::ipc_state()`)+ pacing 觀測(`pacing_observation()`)沿
**Rust IPC → FastAPI GET → (可選)GUI** 唯讀鏈路接通,並演進 Python health normalizer 的負空間 attestation。
**核心洞見:W4 接的是「health 狀態查詢管線」,非「driver 真啟動」**——inactive 引擎下 health method 回
`EXTERNAL_VERIFICATION_PENDING` 形態(session=`Disconnected(EnvelopeRequired)`),是對 **inactive session 的真實
FSM 計算**,非 fake-success,非真連。**封頂 = `source-ready`**(源+測綠;inactive 引擎下 IPC/route 於 E4/QA 本地
真調通回 PENDING 態);`runtime-active(inactive deploy)` 屬 W10,不在本包。

---

## 1. IPC method `stock_etf.get_connection_health`(Q1)

**回應 shape**——新增 types 契約 `IbkrConnectionHealthReportV1`(`openclaw_types`,Rust 為 authority),欄位分四束 +
負空間安全束:
- `session_state: IbkrTwsSessionStateV1`(投影 `manager.ipc_state()`;inactive=`disconnected`)、`halt_reason`
  (`envelope_required`)、`session_active: bool`(=false)、`reconnect_attempt`。
- `pacing`(投影 `PacingObservation`):`main_tokens_available`/`queue_depth`/`lines_in_use`/`ib_pacing_strikes`/
  `admitted`/`rejected_*`(inactive=初始桶量 + 全零)。
- `attestation_status: IbkrSessionAttestationStatus`(=`blocked`)、`account_fingerprint_is_live: bool`(=false,
  white-list paper 語義,W5 才真派生)。
- `entitlement_state`(=`pending`;entitlement 邏輯 W6,W4 只佔位)、`pending_reason`。
- **負空間安全束**(恆 false):`ibkr_contact_performed`/`secret_slot_touched`/`gateway_socket_open`/
  `order_routed`/`bybit_ipc_reused`/`ibkr_live_enabled`。
- `report_status`(枚舉,W4 唯一可產值=`external_verification_pending`)、`contract_id`/`source_version`。

**方法矩陣 + allowlist 最小改動**:
1. `rust/openclaw_types/src/stock_etf_lane_scoped_ipc.rs`:`StockEtfLaneScopedIpcMethod` 加 `GetConnectionHealth`;
   進 `REQUIRED_METHODS`;`expected_method` 回 `{Op::HealthRead, Scope::DisplayOnly, effect_capable:false,
   rust_owned:false, gates:&[], fields:STATUS_FIELDS}`(與其餘 13 個 status method 同形)。
2. `rust/openclaw_engine/src/ipc_server/method_registry.rs`:加 `STOCK_ETF_GET_CONNECTION_HEALTH`
   (`readonly:true, slot:None`)進 `IPC_METHOD_REGISTRY` + `stock_etf_methods_are_registered_as_lane_scoped_fixtures`
   測試表(不進 `LIVE_WRITE_METHODS`——readonly 豁免 token surface)。
3. `_API_ALLOWLIST_READ_ACTIONS` 已含 `connection_health_read`(`stock_etf_status_common.py` 現存,無需改)。

**dispatch 落點**:`handlers/stock_etf.rs::handle_stock_etf_ipc` 加分支 `"stock_etf.get_connection_health" =>
connection_health_summary()`。emitter `connection_health_summary()`(建議新檔 `handlers/stock_etf/health_summary.rs`)
**構造一個 ephemeral `TwsSessionManager::new(default)`,呼 `attempt_connect(0)` 一次**(permit stub 恆拒 →
`Disconnected(EnvelopeRequired)`,**零 socket**),讀 `ipc_state()` + `pacing_observation()`,投影進契約。此為 session/
pacing 模塊的**首個 production caller**(滿足其 `TODO(W4)` 標記,把 `ibkr_tws_session`/`ibkr_tws_pacing` 移出 DCE);
**g4 symbol audit 保綠**(forbidden 只含 `g4_operator_triggered_first_contact`/`ibkr_g4_first_contact`/
`ibkr_readonly_tws_client`,不含 session/pacing);**fake-absence audit 保綠**(不引 `openclaw_fake_tws`)。

---

## 2. FastAPI GET route(Q2)

`stock_etf_routes.py` 加 `@stock_etf_router.get("/connection-health")`(命名慣例對齊 `connection_health_read`),薄 relay:
`_apply_no_store_headers` → `_get_ipc` → `_query_stock_etf_status(ipc, "stock_etf.get_connection_health")` →
`_normalize_connection_health(raw, reason)`,回 `{ok, data, is_simulated:False, data_category:"stock_etf_connection_health"}`。
**方法分區維持**:仍 GET-only、`current_actor` 認證、`del actor`、no-store。Python thin relay **不解讀不加 authority**
(所有裁決在 Rust emitter + normalizer 負空間)。**FastAPI Depends×reload 凍結陷阱**:route module 與 main 同步 reload
或就地刷新 env 派生態(教訓在案 `dbc6a936c`)。

---

## 3. normalizer lockstep + fail-closed 保持機制(Q3,最微妙,AMD 硬要求)

**現況**:負空間 normalizer 把**任何真值/populated 標 `contract_violation`**(見 `_account_status_contract_violations`)。
**W4 演進**:`真值而無 (PASS gate + session-attestation lineage) = violation`。判定邏輯分**三層,依序,前層永不可被後層鬆動**:

- **第 1 層(hard-safety,無條件):** `_SAFETY_FALSE_FIELDS` + `ibkr_live_enabled` + `gateway_socket_open` +
  `db_apply_performed` 若為 true → **恆 violation**,不受任何 lineage 影響(contact/secret/order/socket 屬 EA-gated,
  非 W4/W5 可解禁)。**最先執行,在任何 lineage 分支之前**。
- **第 2 層(negative-space default,lineage 缺席):** `lineage_present == false` 時,**每一個 populated operational
  值**(`session_state != disconnected`、`session_active`、`main_tokens_available>0`、`attestation_status != blocked`、
  `entitlement_state != pending`、各 `*_present`/`*_hash`)→ violation。**與 W3 時代 all-false 檢查逐位元同構**。
- **第 3 層(lineage-bounded,W5+,W4 結構性不可達):** `lineage_present == true` 時 operational 值**可** populated,
  但仍逐值受 lineage-bound 不變量約束(如 `session_active=true` 要求 `attestation_status ∈ {paper_attested,
  readonly_attested}` ∧ `account_fingerprint_is_live=false` white-list;`session_state` 與 `session_active` 一致)。

**`lineage_present` 謂詞(唯一放行閘)**:`= (phase2_gate.status == "PASS") ∧ (attestation.accepted == true) ∧
(attestation.status != "BLOCKED")` ——三者**全部 Rust-emitter 所有**,production 未 seal 下結構性為 false。Python **只做
一致性檢查,不計算 lineage、不接受 client state**。

**fail-closed 不可鬆動的機制(四道)**:
1. **謂詞源於 Rust emitter payload**:gate=BLOCKED(production 從未 seal)⇒ `lineage_present=false` ⇒ 新邏輯
   **退化為第 2 層 all-false**——W4 行為與 W3 逐位元相同。
2. **保留的 all-false 回歸測試(AMD §Runtime Boundary 原文)**:fixture `phase2_gate.status="BLOCKED"` + 每個
   operational 值強注 true → 斷言 `connection_health_state == "contract_violation_blocked"` 且所有注入欄位列入
   `contract_violations`。**此測試是 tripwire:任何未來鬆動第 2/3 層即轉紅**。
3. **同 PR lockstep**:normalizer 演進(引入第 3 層 dead branch)**必與** Rust emitter 引入 lineage 欄位
   (`phase2_gate_status`/`attestation_status`/`account_fingerprint_is_live`,W4 恆 BLOCKED/false)**同片交付**;否則
   自宣告 `{status:PASS, session_active:true}` payload 可繞過。emitter 契約欄位集 ⊗ normalizer 欄位集由
   **cross-surface parity 測試**(仿 `test_stock_etf_session_attestation_cross_surface_parity.py`)鎖死,漂移即紅。
4. **第 3 層在 W4 不可達的機器證明**:inactive fixture 下斷言 `lineage_present=false`(gate 恆 BLOCKED),第 3 層
   分支永不進入 → 覆蓋率/斷言雙鎖。

---

## 4. GUI readiness 面(Q4)

現有 stock readiness 唯讀 view 已原生化(§4.2,10 子視圖)。**判斷:W4 DoD 核心 = 後端鏈(IPC+route+normalizer),
不含 GUI;health 顯示欄擴充建議併入 W9「真值接通」**,理由:(a)W4 health 值全 inactive/PENDING,GUI 擴欄低價值;
(b)避免與進行中 gui_redesign 玄衡 shell 排程二次觸碰;(c)W9-3 本就是所有 readiness 真值接通的自然家。若 loop 有
空閒 GUI 帶寬,可作**可選 E1a 小切片**(display-only、`present && accepted` 才渲染、client state untrusted、GET-only、
`node --check`),但**非 W4 DoD 阻擋項**。**建議 W4 不需 E1a**;GUI 留 W9(此為 PM 決策點)。

---

## 5. W3 移交接線邊界(Q5)

**明確邊界:W4 = health 狀態查詢管線(前者),非 driver 真啟動。**
- W4 的 production caller 只到 **`TwsSessionManager`**(讀 `ipc_state()`+`pacing_observation()`);manager 用其自持
  `EnvelopeRequiredStub` permit,`attempt_connect` 恆停 `Disconnected(EnvelopeRequired)`,**FSM 停 Disconnected
  (EnvelopeRequired),零 socket**。driver `SessionDriver<P,F>` 需注入 `TransportFactory`——production factory =
  **W8 TCP factory(`ibkr_transport_tcp` feature)**,W4 不具備,故 **driver + serve loop + `send_framed` 全維持
  production-DCE**(manager 不引用 driver,故構造 manager 不把 driver 拉出 DCE)。
- **send_framed 的 F4 單一出口牙齒咬合,production bite 不在 W4 達成——等 W8 TCP factory + run-loop**。W3 收口紀錄
  「queued-heartbeat + send_framed 真消費者→W4」**過度樂觀,需更正為 →W8**:兩者皆 driver serve-loop 概念,無真
  transport 即無 production caller,而真 transport = 真 socket = W4 禁止。W4 期 `send_framed`/`resolve_pacing`/
  queued-heartbeat 仍僅 `#[cfg(test)]` driver 測試域行使。**(移交修正,PM 應同步 IBKR_TODO §5-W3 殘項行。)**
- **防禦性建議**:W4 加機器斷言「`ibkr_tws_driver` production 符號(`SessionDriver`/`TransportFactory`/`send_framed`)
  於 default artifact 缺席」(仿 g4/fake nm 審計,負向鎖「manager-only 非 driver」邊界),對齊 E3-F1 audit-scope
  但方向為「W4 driver 仍應缺席」。

---

## 6. 切片計劃(Q6;normalizer lockstep 必與 Rust emitter 同片)

| 切片 | 範圍/檔面 | 測試 | Role | 規模 | E1a/IB | 依賴 |
|---|---|---|---|---|---|---|
| **W4-0**(可選 pre-slice) | `IbkrConnectionHealthReportV1` types 契約 + inactive/accepted fixture + `validate()`(僅 `openclaw_types`,零行為) | types acceptance(欄位 taxonomy + 負空間 fixture) | E1→E2→E4 + IB | S | IB | W3 |
| **W4-1**(核心,**lockstep**) | Rust emitter(`health_summary.rs` 構 inactive manager 讀 ipc_state+pacing_observation)+ dispatch 分支 + method_registry + lane-scoped `GetConnectionHealth` + FastAPI GET route + **Python `_normalize_connection_health` 三層負空間演進** + **保留 all-false 回歸** + 靜態守衛(route count 17→18、`ALLOWED_STOCK_ETF_STATUS_IPC_METHODS` +1、surface coverage、driver-absence nm 斷言) | engine IPC fixture + normalizer 三層測試 + all-false tripwire + cross-surface parity + route/GET-only 守衛 | E1→E2→E4 + **IB**(health/pacing 語義)+ **E3**(GET-only/no-write/lineage 不鬆動)+ **QA**(唯讀鏈路) | M | IB+QA+E3 | W4-0(或內含) |
| **W4-2**(可選) | GUI readiness health 顯示欄(display-only) | GUI 負測試 + `node --check` | E1a→E2→E4 + QA | S | E1a | W4-1;**建議 defer W9** |

**lockstep 說明**:AMD 硬要求 normalizer 演進與 Rust emitter 同 PR → **W4-1 為單一不可分 PR**(emitter⊗normalizer⊗
regression⊗parity)。W4-0(純 types,無行為耦合)可先落以 de-risk taxonomy,或折入 W4-1。W4-2 非 lockstep-bound,
可獨立或 defer。**建議波次**:W4-0 → W4-1(核心);W4-2 視 GUI 帶寬 / defer W9。

---

## 7. 狀態梯度封頂(Q7)

W4 封頂 = **`source-ready`**(§3 詞彙):源碼 + Mac(aarch64)/Linux cargo + pytest 綠;inactive 引擎下 IPC/route 於
**E4/QA 本地真調通回 `EXTERNAL_VERIFICATION_PENDING` 形態**(非 fake-success)。**不達 `runtime-active`**——Linux
inactive deploy 屬 W10(operator-gated 部署窗);引擎 binary 落後 main 為觀測值非缺陷。申報禁把 source-landed 混稱
runtime-verified。

---

## 8. UNVERIFIED-IB 與風險

**UNVERIFIED-IB**:
1. IBKR 是否有單一「connection health」API 訊息——**無 load-bearing 外部事實**:W4 health 為**內部 FSM 合成**
   (session state + isConnected + error-frame 分類 1100/1101/1102/2103-2110,皆 W3 已落現勘常數),非新 IBKR call,
   故不需新外部事實入碼。
2. `market_data_lines` default=100(→`main_tokens_available` 派生)為 IB 現勘、EA4 實測校準前的佔位——W4 沿用 W3
   default 屬已記錄非 fake;若 W4 順帶 plumb engine TOML→`PacingConfig`(W3 標「plumbing 待 W4」),須確保 lines
   真讀取生效(參數禁假功能),否則維持 default 並文檔標注。

**風險**:
- normalizer 第 3 層 dead-branch 誤啟(鬆動 fail-closed)→ 由第 2 層 all-false tripwire + parity + 第 4 道不可達斷言
  三鎖;E3 專審。
- ephemeral manager per-call:config 全 `default`,FSM 恆 inactive,backoff/heartbeat 參數 W4 不行使(W3 已測),
  無新 dead param;`main_tokens_available` 為唯一真派生值。
- Depends×reload 凍結(§2);IPC unavailable → `_query_stock_etf_status` 回 `reason` → normalizer fail-closed
  `degraded`。

**移交修正(PM)**:IBKR_TODO §5-W3 殘項「send_framed 真消費者→W4」應更正為 →W8;§5-W4 GUI 擴欄讀法建議標「defer W9
或可選 E1a」。
