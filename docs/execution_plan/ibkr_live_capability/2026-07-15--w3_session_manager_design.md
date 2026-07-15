# W3 — TWS transport/session manager(可恢復)技術設計 + 實作切片計劃

**日期** 2026-07-15 | **性質**:PA 先行設計(loop R3;TODO 行 `P1-IBKR-STOCK-ETF-FULL-LIVE-CAPABILITY-W3`)。
**權威出典**:AMD-2026-07-11-01 §Decision 1-3(transport/session/錯誤處理 development 授權)+ §Activation(envelope 前置、reconnect=新活化、nonce 單次消費)> `IBKR_TODO.md` §5-W3(範圍/DoD 正本)/§2(邊界)/§8 R1-R3 > `docs/agents/ibkr-live-capability-loop.md` §2。
**申報梯度**(IBKR_TODO §3):本包封頂 `source-ready`。本文檔任何一句都不是 broker 授權;W3 全程零真 socket(fake-TWS=tokio duplex,in-process)。
**as-built 種子**:`rust/openclaw_engine/src/ibkr_readonly_tws_client.rs`(B1:純 codec §(a)/泛型 driver §(b)/loopback guard §(c)/G4 gate §(d),26 duplex synthetic-frame 測試)+ `rust/openclaw_types/src/ibkr_phase2_runtime.rs`(`IbkrApiSessionTopologyV1`)+ 港口常量 `ibkr_phase2_gate.rs`(4002/4001/7496)。

---

## 1. Session FSM

### 1.1 狀態集

`Disconnected(halt_reason)` → `Connecting` → `Handshaking` → `Ready{server_version, connection_time_raw, paper_confirmed, next_valid_id}` ⇄ `Degraded` → `Backoff{attempt_n, next_delay}`。

**對任務題面的一處刻意偏差**:Ready 不攜帶 `managedAccounts` 明文——B1「prefix-only inspect then drop」紀律原樣繼承(明文帳號不 bind 具名變量/不 log/不 serialize),Ready 只帶派生 boolean `paper_confirmed`;帳戶 fingerprint hash 是 W5 attestation 產物,W3 不產。

### 1.2 轉移表(未列組合 = 非法轉移,debug_assert + typed `IllegalTransition` 事件)

| 從 | 事件 | 到 | 說明 |
|---|---|---|---|
| Disconnected | `connect_permit granted`(單次 token) | Connecting | **INV-1 掛點,見 §1.5** |
| Disconnected | permit 拒(`EnvelopeRequired` 等) | Disconnected | 記 typed 事件,不重試(production W8 前恆此路) |
| Connecting | transport 建立 | Handshaking | fake 域=duplex 注入;TCP 域見 §5 |
| Connecting | connect timeout/refused | Backoff | transient |
| Handshaking | ACK+version pin 過+15 全 DU+9 收到 | Ready | 缺任一不入 Ready(fail-closed) |
| Handshaking | `NonPaperSessionDetected`/`ServerVersionTooOld`/fatal ERR_MSG(<2100) | Disconnected(SessionFatal) | 不自動重試 |
| Handshaking | IO err/timeout/EOF | Backoff | transient |
| Ready | 心跳連續 miss ≥`degraded_after_misses`(默認 2) | Degraded | socket 未斷,標記劣化 |
| Ready/Degraded | IO err/EOF/timeout ≥`drop_after_misses`(默認 4) | Backoff | 斷傳輸,進退避 |
| Degraded | 心跳恢復 | Ready | |
| Ready/Degraded | `DuplicateClientIdKick`(§2.4) | Disconnected(SessionFatal) | 被踢=session-fatal,不與別 client 互搶 |
| Ready/Degraded | 週日重認證窗判定(§1.4) | Disconnected(SessionExpiredWeeklyReauth) | 人工事務,永不自動重連 |
| Backoff | 延遲到期 ∧ permit 再驗(新 token) | Connecting | **每次重連重新走 INV-1;不緩存 permit** |
| Backoff | 連續失敗 >`max_reconnect_attempts`(默認 8) | Disconnected(ReconnectBudgetExhausted) | 不無限重試(IBKR_TODO §5-W3-1) |
| 任意 | kill-switch epoch 變更/operator stop | Disconnected(Halted) | W8 接真 epoch;W3 先留 typed 停機入口 |

### 1.3 退避與心跳參數(全 config 化,`TwsSessionConfig`;參數禁假功能——每項必真實被讀取、生效、可觀測)

- 指數退避 + **full jitter**:`delay = rand(0, min(cap, base × 2^attempt))`;`base=1s`、`cap=60s`、`max_reconnect_attempts=8`。測試用注入 RNG + tokio paused clock 取確定性。
- 心跳 = `reqCurrentTime` 週期 `heartbeat_interval=30s`,回覆超時 `heartbeat_timeout=10s`;心跳流量過 pacing governor(1/30s 可忽略但不豁免,保單一出口不變量)。

### 1.4 排程感知(IB 2026-07-15 現勘事實,IBKR_TODO §8 R2/R3)

- **nightly restart 窗**:config `restart_window{time_et, duration_min}`(America/New_York,DST 由 tz 庫解,禁手寫偏移)。窗內斷線分類 `ScheduledRestartDisconnect`:進 Backoff 但**不計入 reconnect budget**,首個延遲=窗殘餘+grace。窗未配置 → 無此感知,按一般 transient 處理(fail-closed 不猜默認時刻,見 §8-U4)。
- **週日 ~1:00am ET 強制重認證**(auto-restart 只覆蓋 Mon-Sat):窗內斷線 → `Disconnected(SessionExpiredWeeklyReauth)`,FSM 不重試——重登是人工+活化事務(AMD:reconnect=新活化;EA4 起每日活化紀律,OPEN-GOV-2 未裁前不設計排程性自動重連)。
- 測試紀律:排程判定函數以「注入時鐘」為唯一時間源,fixture 全相對/凍結時鐘(禁硬編日期 time-bomb),DST 換日兩側各設案例。

### 1.5 INV-1(本包最高不變量):envelope 掛點在 connect 之前,W8 前只拒不放

- `ConnectPermitProvider::check(&mut self) -> Result<PermitToken, ConnectDenied>`;`PermitToken` **單次消費**(move 進 connect 呼叫,不可 Clone)——結構上禁止「舊 envelope 靜默復用」(AMD §Activation-authenticity 原文)。
- W3 production 唯一實作 = `EnvelopeRequiredStub`:恆回 `Err(ConnectDenied::EnvelopeRequired)`。**無任何 config/env/cfg 可翻放行**;W8 以真 `ibkr_activation_envelope_v1` 驗證器替換同一 trait 位。
- TCP transport factory(§5)持**具體型別** `EnvelopeRequiredStub`(非 trait object/非泛型)——測試域無法向 TCP 路徑注入放行者;fake 域走 duplex factory,根本不含 permit 放行語義之外的 socket 面。FSM 的「自動重連」全路徑只在 fake-TWS 測試域可走通,production 每次 Backoff→Connecting 都撞 `EnvelopeRequired` 停在 Disconnected。

## 2. Wire 協議層

### 2.1 framing 與解碼

沿用 B1 §(a) 純 codec 原語(`encode_frame`/`try_decode_frame`/`decode_fields`,u32 BE length、`MAX_FRAME_LEN=64KB` 分配前拒、非 ASCII/截斷 typed 拒、零 panic/捏值)。新增 `FrameReader`(streaming):把 B1 one-shot `ReadBudget`(32 frame/256KB,G4 探針語義)換成**滾動窗預算**(`max_frames_per_sec`/`max_bytes_per_sec`,config),長連線防惡意灌流。

### 2.2 版本協商與 pin 策略

- handshake 送 `v{min}..{max}`(現值 100..176);ACK `server_version < PINNED_MIN_SERVER_VERSION` → `ServerVersionTooOld` session-fatal(客戶端自檢 fail-closed,不依賴 server 拒絕行為,§8-U5)。
- **pin 來源出典**:`PINNED_MIN_SERVER_VERSION` 常量入 types crate,旁註官方 TWS API 文檔出處+IB 現勘日期;初值 = B1 的 100(v100+ 協議下界)。凡我方實作的訊息 shape 需要更高 server version,pin 隨之上調並附出典——**由 IB 現勘腿核定後才進代碼**(loop §2:UNVERIFIED 不得寫成代碼常數)。
- v1 無 feature-degradation 分支:version 不足=拒,不做「舊 server 降級路徑」(deletion test 不過,無第二消費者)。

### 2.3 未知訊息 fail-closed

已知 msgId 白名單(W3 期:ACK/49/15/9/4)之外 → `UnknownMsgId` → Degraded→Backoff 斷線(不猜欄位、不跳過)。已知 msgId 尾部多餘欄位:容忍+計數(telemetry),前綴欄位嚴格解析(B1 現行語義)。W4-W7 各包擴白名單時逐 msgId 附解碼器+測試,禁「默認略過」。

### 2.4 錯誤三元組 → typed 分類

`decode_error_code` 沿用(index 3);新增 `IbErrorClass` 表驅動分類器(單一 const 表,單處維護):
`Transient`(farm/connectivity 斷復類)/`SessionFatal`(未連線 502/504、duplicate client-id)/`Entitlement`(行情未訂閱類,W6 消費)/`Pacing`(**error 100**,超限;三次違規斷 session——IB 2026-07-15 已現勘)/`OrderReject`(族保留,分類表 W7 填)/`Info`(≥2100 floor,B1 E2 已實證)/`Unknown`。
**分類紀律**:表中只允許「IB 帶來源現勘過」的 code(現勘已定:100、≥2100 floor、502/504);其餘候選(duplicate client-id 疑 326、connectivity 1100/1101/1102、未訂閱疑 354)在 §8 掛 UNVERIFIED,現勘落地前一律走 `Unknown`。`Unknown` 保守裁決:code<2100 → 按 SessionFatal 處理(fail-closed),≥2100 → Info。duplicate client-id 的偵測 v1 以「現勘後的 code + 握手後即被斷線的形態」雙判,產 typed `DuplicateClientIdKick`。

### 2.5 timeout 正規化

單一 `TimeoutPolicy{connect=5s, io=10s, handshake_total=15s, heartbeat_reply=10s, graceful_close=2s}`(config);每個 await 必包 timeout → typed `Timeout{op}`(禁裸 await 掛死;B1 PROBE_IO_TIMEOUT 範式推廣)。

### 2.6 與 B1 的關係:擴展 + 最小抽檔,不重構 G4 路徑

- **抽**:B1 §(a) 純 codec + `decode_error_code`/`managed_accounts_all_paper` → 新檔 `ibkr_tws_wire.rs`(pub(crate));B1 檔改 `use` 引入,對外行為/測試語義零變(26 測試隨遷或原檔 re-export 保綠)。動機:B1 檔已 1416 行,疊 FSM 必破 2000 行守衛;codec 自此有兩個消費者(B1 G4 探針 + W3 session manager)——deletion test 過。
- **不動**:B1 §(b) driver、§(c) guard、G4 approval reader、§(d) G4 entry 原樣凍結(G4 一次性探針語義+批准鏈是 EA3 入口,不與新 FSM 同 PR 攪動)。session manager 自寫長連線 handshake driver(復用 wire 原語),不改造 `drive_handshake_and_current_time`。

## 3. Pacing governor

- **主預算(msg-rate)**:token bucket;`rate = market_data_lines ÷ 2` msg/s(IB 現勘語義;默認 `market_data_lines=100` → 50 msg/s),burst 容量=1 秒額度。config 鍵 `pacing.market_data_lines`(帳戶實際 lines 只能 EA4 實測校準,§8-U6)。**所有出站 framed 訊息單一出口過 governor**(含心跳),無旁路。
- **獨立預算**:`historical` bucket(歷史資料請求另有官方限速,具體額度 UNVERIFIED §8-U2——W3 落框架+保守低默認,IB 現勘後校準);`subscription lines` 是併發配額非速率(`acquire_line/release_line` 計數器,W6 訂閱表消費)。
- **超限裁決:有界排隊,溢出即拒**。bounded FIFO(cap=1 秒額度×2)平滑突發;排隊逾時 `queue_timeout=500ms` → typed `PacingBudgetExceeded` 拒絕呼叫端。**禁無界排隊**(OOM 教訓)、禁 silent drop;order-verb 訊息(W7)超限直接拒不排隊(訂單延遲=語義謊言,重試權還呼叫端)。理由:IB 三次違規斷 session——本地 governor 必須讓違規結構性不可能,而非事後處理 error 100。
- 觀測:tokens/queue depth/reject 計數 export 給 W4 health IPC。

## 4. fake-TWS harness(一級交付物)

- **落位:workspace dev-only crate `rust/openclaw_fake_tws/`**(engine 的 `[dev-dependencies]`)。比 `#[cfg(test)]` module 強:①可被 engine 單元測試、`tests/` 整合測試、W10 E2E 跨檔復用;②production build 是**不同編譯單元根本不編譯它**(結構性缺席,非屬性標註)。純 in-process duplex,**crate 內零 `TcpStream`/`TcpListener` 符號**(測試也不開真 socket,DoD「零真 socket」全鏈成立)。
- **場景 DSL**(腳本=`Vec<FakeStep>`,以 B1 duplex synthetic frames 為種子):`AnswerHandshake{server_version}`(版本不符場景)/`Send(frames)`/`SendRaw(bytes)`(半訊息/損壞)/`Expect(client-msg 匹配)`/`Delay(ms)`(paused clock)/`CloseAbruptly`/`Duplicate(frame)`/`Reorder(...)`/`InjectErr{code}`(pacing 100、fatal 504、現勘後的踢線 code)/`SilentDrop`(不回心跳→Degraded 場景)。Runner 驅動 duplex server 側,對 client 斷言 FSM 事件序列。
- **API 形態(供 W4-W7/W10)**:`FakeTws::builder().script(s).build() -> (impl TransportFactory, FakeHandle)`;`FakeHandle::{received_frames, assert_script_exhausted}`;附 canned 場景庫 `scenarios::{happy_session, kick_duplicate_client, version_too_old, pacing_violation, mid_stream_disconnect, weekly_reauth_window,…}`——後續 W 包組合場景,不再手搓 frame。
- **production 缺席機器斷言(掛 W-CI,IBKR-CI-3 新行)**:①`helper_scripts/ci/ibkr_fake_tws_absence_audit.sh`——nm 掃 default **debug** engine artifact 零 `fake_tws` 符號(全仿 `ibkr_g4_symbol_audit.sh` 範式:審 debug 非 stripped release、inconclusive=exit 5 fail-closed、正控自證 pattern 有牙);②`tests/structure/` 靜態守衛——解析 engine `Cargo.toml`,`openclaw_fake_tws` 只允許出現在 `[dev-dependencies]`。

## 5. Build posture 重裁提案(只提案不裁決;裁決人=CC)

**現狀**:`ibkr_g4_contact` feature lazy-build,default build 零 socket 符號(L1 feature+DCE 主保證,L3 nm audit 回歸)。**張力**:AMD-07-11 已授權 production wiring;W4 要在 default build 消費 session 狀態;維持全 feature-gate 則 live-ready 終態結構性不可達。

| 方案 | 內容 | 代價 |
|---|---|---|
| A(現狀延伸) | W3 全部新代碼仍鎖 feature 後 | 與 AMD-07-11 wiring 授權矛盾;W4 IPC 接不上;終態不可達 |
| **B′(PA 主建議,兩段式)** | **W3**:FSM/wire/governor/契約/fake-harness 進 default build(不含任何 socket 符號——TransportFactory 是 trait,duplex 實作在 dev-crate);**TCP factory(唯一新 `TcpStream::connect`)留 `ibkr_transport_tcp` feature 後**,現行「零 socket 符號」audit **原樣有效**。**W8**:envelope 驗證器落地同 PR 把 TCP factory 進 default build + audit 斷言改版 | 兩段各一次 CC 審;W4-W7 全程騎 fake factory,無損 |
| B(一步到位) | W3 即讓 TCP factory 進 default build,envelope runtime-gate(W8 前=EnvelopeRequiredStub 恆拒),同 PR 改版 audit | audit 改版提前到 W3;stub 期「符號在、runtime 拒」的保證弱於「符號不在」 |

- **audit 改版計劃(採 B′ 時歸 W8 同 PR;採 B 時歸 W3-S2 同 PR;IBKR_TODO §5 W-CI 效期注記:不得留紅、不得靜默刪)**:「零 socket 符號」負斷言 → 三聯斷言:①源級守衛:engine crate ibkr 面的 `TcpStream::connect` 只允許出現在 `ibkr_tws_transport.rs` 單一函數(AST/grep 靜態測試);②結構斷言:該函數 connect 之前必經 `ConnectPermitProvider::check` 且 `PermitToken` move 消費(源級模式斷言+負測試);③fake_tws 符號缺席審計(§4)照常。
- **CC 需裁精確問題清單**:
  1. 採 B′ 還是 B?(PA 建議 B′:最小信任面推進,audit 改版與真 envelope 驗證器同窗落地,不出現「stub 期靠 runtime 拒」的中間態。)
  2. 若採 B:三聯斷言是否足以替代「零 socket 符號」?是否強制同 PR land?
  3. 既有 `ibkr_g4_contact` feature + G4 bin:保留原樣至 EA3(PA 建議),還是 W8 時併入新 transport+envelope 路徑後廢止?
  4. `EnvelopeRequiredStub` 以「具體型別持有、無放行構造路徑」為 fail-closed 證明,是否需再加 E3 專項掃描斷言(test-only 放行者不可達 TCP factory)入 W-CI?
  5. dev-only crate `openclaw_fake_tws` 是否認可為「fixtures 不藏 caller」邊界的合規形態(AMD 不變量 6)?

## 6. 實作切片計劃(每片獨立 E1→E2→E4;role chain 按 TODO 行,IBKR 面全片 +IB)

| 片 | 名稱/規模 | 範圍 | 檔案面 | 測試矩陣 | 依賴 |
|---|---|---|---|---|---|
| W3-S1 | wire 抽檔+錯誤分類+timeout 正規化(M) | §2.1/2.4/2.5/2.6 抽檔;`IbErrorClass` 表(僅現勘 code);`TimeoutPolicy`;**IB 現勘腿**:code 表(§8-U1/U3)+ version pin 出典核定 | 新 `ibkr_tws_wire.rs`;`ibkr_readonly_tws_client.rs` 縮身(only-use 改動);types 加 `IbkrTwsErrorClassV1`+pin 常量 | B1 26 測試保綠;分類矩陣;fuzz 保留擴檔;unknown-code 保守裁決 | 無 |
| W3-S2 | session FSM+心跳+排程感知+permit stub(L) | §1 全部;INV-1;typed 事件契約 | 新 `ibkr_tws_session.rs`;types 加 `ibkr_tws_session_state.rs`(state/event/config 契約) | 轉移矩陣全覆蓋(paused clock+注入 RNG);心跳劣化/恢復;窗分類 DST 兩側;**permit 恆拒負測試**(production 構造路徑無放行);非法轉移 | S1 |
| W3-S3 | pacing governor(M) | §3 全部;config plumbing | 新 `ibkr_tws_pacing.rs`;engine config(stock_etf/ibkr 節) | paused-clock bucket 確定性;burst/排隊逾時拒;預算隔離;**參數有效性測試**(改參數→行為可觀測變化) | S1(S2 並行可,合流在 S4) |
| W3-S4 | fake-TWS harness+故障注入全矩陣+缺席審計(L) | §4 全部;整合 S2+S3 全 FSM 路徑 | 新 crate `rust/openclaw_fake_tws/`;`ibkr_fake_tws_absence_audit.sh`;structure 守衛;`ci.yml` IBKR-CI-3 | 斷線恢復/過期/踢線/pacing/版本不符/亂序/重複/慢/半訊息;audit 正控;dev-dep-only 守衛 | S1+S2+S3 |

**W2 殘餘 LOW/NOTE 六項歸屬**(PROGRESS R2:Revoke 豁免壞 inputs/compile_error target 守衛/expiry 上界/F-4/5/6 測試加硬/CLI dry-run 診斷 UX):**檔面全屬 W2**(`ibkr_phase2_gate_producer.rs`/seal CLI),與 W3 檔面零交集,不併入本包切片(避免 review 面污染)。唯一例外候選:若 CC 把「compile_error target 守衛」裁為範式,B1 檔 `#[cfg(not(unix))]` G4 approval reader 是同構位點,可在 S1 順手比照——默認不做,標給 PM 裁。

## 7. 模組落位(engine crate 內;2000 行拆檔守衛)

| 檔 | 職責邊界 | 預估量級 |
|---|---|---|
| `openclaw_engine/src/ibkr_tws_wire.rs` | 純 codec+錯誤分類+TimeoutPolicy;無 I/O、無狀態 | ~700 行含測試 |
| `openclaw_engine/src/ibkr_tws_session.rs` | FSM/退避/心跳/排程感知/permit trait+stub/TransportFactory trait;泛型於 stream,不自持 socket | ~1100;逼近 2000 即拆 `_tests.rs`(repo 既有範式) |
| `openclaw_engine/src/ibkr_tws_pacing.rs` | governor(雙 bucket+line 配額+觀測計數) | ~500 |
| `openclaw_fake_tws/`(dev-only crate) | 場景 DSL+runner+canned 場景庫;零 socket 符號 | ~800 |
| `openclaw_types/src/ibkr_tws_session_state.rs` | **契約最小集**:`IbkrTwsSessionStateV1`/`IbkrTwsSessionEventV1`(DuplicateClientIdKick/SessionExpiredWeeklyReauth/ReconnectBudgetExhausted/PacingBudgetExceeded/EnvelopeRequired…)/`IbkrTwsErrorClassV1`/pin 常量——W4 IPC 的直接消費面,W3 不加其他契約 | ~350+acceptance 測試檔 |
| `ibkr_readonly_tws_client.rs`(既有) | 縮至 driver/guards/G4(凍結);只改 use | 1416→~900 |

deletion test 記錄:wire(消費者=B1+session)、session(W4 IPC+W5-W7)、pacing(session+W6)、fake crate(W3-W7/W10 測試)——各有 ≥2 消費者或既定復發需求;未建 `ibkr_tws_router.rs`(request-id 路由表先內嵌 session 檔,W5 多請求型別出現=第二消費者時才抽)。

## 8. UNVERIFIED-IB-現勘清單(**2026-07-15 IB 現勘已解 U1-U3/U6;U4/U5 裁定不可證維持 config/自檢**)

> **現勘落地(2026-07-15,IB fragment)**:U1(326=拒新連非踢舊,typed 改名 `DuplicateClientIdRejected`)、U2(歷史 60req/600s+BID_ASK×2+15s dedup+2s<6,default 入碼閾值 config)、U3(1100/1101/1102/1300/2103-2110/2158/354/503 全表分類確認)、U6(lines=100 默認+÷2 公式;無查詢 API,EA4 校準)——**已進 S1 代碼常數**(每條旁註官方 URL+現勘日)。**U4**(Gateway 默認重啟時刻,官方通篇無載)與 **U5**(server 拒過低 client 的專屬 code,不存在)裁定**不可證,禁入常數**:U4 全留 config、U5 走客戶端 `PINNED_MIN_SERVER_VERSION` 自檢 fail-closed。下列原始清單保留供追溯。

- **U1** duplicate client-id 被踢:精確 error code(疑 326)與 server 行為(拒新連 vs 踢舊連)。
- **U2** 歷史資料 pacing 具體限額與窗口(W3 只落獨立 bucket 框架+保守低默認)。
- **U3** connectivity/farm code 完整表(1100/1101/1102、2103/2105/2107 等)與行情未訂閱 code(疑 354)。
- **U4** IB Gateway nightly restart 的默認重啟時刻與可配置範圍(W3 不硬編默認,未配置=不啟用排程感知)。
- **U5** server 對過低 client version 的具體拒絕形態(斷線 vs ERR_MSG;客戶端自 pin 檢查已 fail-closed,不依賴)。
- **U6** 帳戶實際 market data lines 數(默認 100 為 config 初值;EA4 實測校準)。
- 已現勘(可入代碼,出典=IB 2026-07-15,IBKR_TODO §6/§8):pacing=lines÷2、error 100、三次違規斷 session、週日 ~1:00am ET 強制重認證、auto-restart 僅 Mon-Sat、單 username 單 session 互踢(R3)。

## 9. DoD 對照(IBKR_TODO §5-W3)

`source-ready`;fake-TWS 下全 FSM 路徑覆蓋(S4 矩陣);**零真 socket 測試**(duplex-only,fake crate 無 TCP 符號);Mac+Linux cargo 綠(E4 兩腿);fake 路徑 production 缺席機器斷言掛 W-CI;INV-1 負測試(production 無放行構造路徑);B1 26 測試與 G4 路徑零語義變更;bybit-live-unchanged 回歸隨每片 PR。

## 10. R3 評審裁決落地(2026-07-15/16)

- **Build posture(CC 裁,置信 0.92)**:採 **B′ 兩段式**——W3 讓 FSM/wire/governor/契約進 default build(本身零 socket 符號);唯一 `TcpStream::connect` 的 TCP factory 留 `ibkr_transport_tcp` marker feature 後,**現行 g4 零符號 audit 於 W3-W7 原樣保綠**;W8 envelope 驗證器落地同 PR 解鎖 TCP 進 default + audit 改版為四聯斷言(唯一 connect 位點/connect 前必經 permit 且 `PermitToken` move 消費/fake 缺席/**provider 型別唯一性**)。`ibkr_g4_contact`+G4 bin 凍結保留至 EA3(退役走獨立 decommission PR,禁 W8 併吸)。permit-stub 靜態守衛(具體型別 `EnvelopeRequiredStub`/`PermitToken` 非 Clone·構造子 crate-private/stub 零 env·cfg 讀取/正控/inconclusive 非零 exit)於 S2 同 PR 掛 W-CI。`openclaw_fake_tws` dev-crate 認可為 AMD 不變量 6 合規形態(structure 守衛掃全 workspace `[dev-dependencies]` + nm 缺席審計)。
- **IB 官方現勘(見 §8 頭)**:U1-U3/U6 已解入碼;U4/U5 不可證。
- **S1 收口(2026-07-16)**:E2 APPROVE_WITH_NOTES(抽檔 byte-level 乾淨;module `allow(dead_code)` 裁可接受=均勻 DCE 誠實標註,真守衛=g4 nm 審計)+ E4 雙腿(Mac engine 113/types 11/stock_etf 33/seal bin 2 全綠、g4 audit PASS;Linux main 基線對照)。殘 NOTE:N2(S2 接 FSM 時 farm-blip 2103/2105/2110 不得觸過早 reconnect)、N3(S2 接線後 wire S2 面應獲真消費者 tripwire,隨 IBKR-CI-3 落地)。
- **下一切片**:S2(FSM+心跳+排程感知+permit stub,依賴 S1)、S3(pacing governor,依賴 S1 可與 S2 並行)、S4(fake-TWS crate,依賴 S1-S3)。
