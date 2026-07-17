//! MODULE_NOTE
//! 模塊用途：IBKR **W3-S4 fake-TWS harness**（dev-only 一級交付物;設計 §4）。純 in-process
//!   雙工（tokio duplex）模擬 IB Gateway server 側:腳本化握手（ACK/version/managedAccounts DU*/
//!   nextValidId/currentTime）+ 故障注入（半訊息斷線 / 慢響應 / 亂序 / 重複事件 / 版本不符 /
//!   pacing 違規 error-100 / duplicate client-id 326 拒新連 / 非 paper 帳號 / mid-stream 斷線）。
//!   canned 場景庫供 W3 driver 端到端測試 + W4-W7/W10 復用。
//! 主要區段：
//!   - (a) 自有 wire codec：`encode_frame`（u32 BE len + payload）/`encode_fields`（null-terminated）
//!     + 解碼助手。**與 engine codec 刻意獨立**——fake 是「另一方」server,獨立編碼 IB wire 格式,
//!     不依賴 openclaw_engine（避 dev-dep cycle 的重複編譯單元陷阱;見 Cargo.toml）。
//!   - (b) `FakeFrame` builders：canonical TWS 訊息（handshake_ack / managed_accounts / next_valid_id
//!     / current_time / err_msg / custom_frame）。
//!   - (c) 場景 DSL：`FakeStep`（Send / SendRaw / Delay / CloseAbruptly）+ `Scenario`（`Vec<FakeStep>`）
//!     + `Scenario::spawn()`（→ client 雙工半 + `FakeHandle`）。
//!   - (d) `FakeHandle`：`received_bytes` / `received_message_frames`（檢視 driver 送出）+
//!     `assert_script_exhausted`。
//!   - (e) canned 場景庫 `scenarios::{...}`（後續 W 包組合,不再手搓 frame）。
//! 依賴：`tokio`（in-process 雙工 + 測試 runtime）。**不依賴 openclaw_engine**。
//! 硬邊界：
//!   - **零真 socket 型別**：本 crate 僅用 tokio 的 in-process 記憶體雙工;**絕不引用任何真實網路
//!     連線型別**（TCP 連線 struct / 監聽器 struct / 標準庫 net 家族 / tokio 的 net 家族一律零引用;
//!     測試也不開真連線）→ DoD「零真 socket」全鏈成立。以 in-crate 源守衛 `#[test]` +
//!     `helper_scripts/ci/ibkr_fake_tws_absence_audit.sh` 雙重驗證。
//!   - **dev-only**：僅 engine `[dev-dependencies]` 引用;default `cargo build` 不編譯 → 引擎 artifact
//!     零 fake 符號（IBKR-CI-3 nm 缺席審計 + structure 守衛驗證）。

use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::{Arc, Mutex};
use std::time::Duration;

use tokio::io::{AsyncReadExt, AsyncWriteExt, DuplexStream};
use tokio::task::JoinHandle;

/// 雙工緩衝容量（server 側預載全部 frame 不阻塞;64KB 對握手 + 少量事件綽綽有餘）。
const DUPLEX_CAP: usize = 64 * 1024;

/// 分配前 frame 上界（對齊 engine `MAX_FRAME_LEN`;untrusted 解碼防護,雖 fake 自產可信,仍守此界）。
const MAX_FRAME_LEN: usize = 64 * 1024;

// ===========================================================================
// (a) 自有 wire codec（server 側獨立編碼 IB wire;不依賴 engine）
// ===========================================================================

/// encode 一個 framed 訊息:4-byte big-endian u32 length + payload（IB wire 格式）。
pub fn encode_frame(payload: &[u8]) -> Vec<u8> {
    let len = payload.len() as u32;
    let mut out = Vec::with_capacity(4 + payload.len());
    out.extend_from_slice(&len.to_be_bytes());
    out.extend_from_slice(payload);
    out
}

/// encode null-terminated 欄位序列（每欄尾附 `\0`;TWS wire 為 null-terminated 欄）。
pub fn encode_fields(fields: &[&str]) -> Vec<u8> {
    let mut out = Vec::new();
    for f in fields {
        out.extend_from_slice(f.as_bytes());
        out.push(0);
    }
    out
}

/// 從 buffer 解出所有完整 frame payload（供 `FakeHandle` 檢視 driver 送出的訊息）。截斷尾殘留忽略。
pub fn decode_all_frames(mut buf: &[u8]) -> Vec<Vec<u8>> {
    let mut out = Vec::new();
    while buf.len() >= 4 {
        let len = u32::from_be_bytes([buf[0], buf[1], buf[2], buf[3]]) as usize;
        if len == 0 || len > MAX_FRAME_LEN || buf.len() < 4 + len {
            break;
        }
        out.push(buf[4..4 + len].to_vec());
        buf = &buf[4 + len..];
    }
    out
}

/// 解 null-terminated 欄位（供測試檢視訊息內容;非 ASCII/截斷回已解部分,fake 檢視用途,不 fail-closed）。
pub fn frame_fields(payload: &[u8]) -> Vec<String> {
    let mut fields = Vec::new();
    let mut start = 0usize;
    for (i, &b) in payload.iter().enumerate() {
        if b == 0 {
            fields.push(String::from_utf8_lossy(&payload[start..i]).into_owned());
            start = i + 1;
        }
    }
    fields
}

// ===========================================================================
// (b) FakeFrame builders（canonical TWS 訊息）
// ===========================================================================

/// 一個已編碼的 framed 訊息（server→client）。
#[derive(Debug, Clone)]
pub struct FakeFrame(pub Vec<u8>);

/// 握手 ACK（serverVersion + connectionTime,兩個 null-terminated 欄）。
pub fn handshake_ack(server_version: i32, connection_time: &str) -> FakeFrame {
    FakeFrame(encode_frame(&encode_fields(&[
        &server_version.to_string(),
        connection_time,
    ])))
}

/// managedAccounts（msgId 15;csv 為逗號分隔帳號,如 "DU1234567" 或 "DU1,DU2"）。
pub fn managed_accounts(csv: &str) -> FakeFrame {
    FakeFrame(encode_frame(&encode_fields(&["15", "1", csv])))
}

/// nextValidId（msgId 9）。
pub fn next_valid_id(id: i64) -> FakeFrame {
    FakeFrame(encode_frame(&encode_fields(&["9", "1", &id.to_string()])))
}

/// currentTime（msgId 49;epoch 秒）——握手完成訊號,亦 serve 期心跳回覆。
pub fn current_time(epoch: i64) -> FakeFrame {
    FakeFrame(encode_frame(&encode_fields(&[
        "49",
        "1",
        &epoch.to_string(),
    ])))
}

/// ERR_MSG（msgId 4;IB v100+ 欄序 [msgId, version, reqId, errorCode, errorMsg]）。
pub fn err_msg(code: i64, text: &str) -> FakeFrame {
    FakeFrame(encode_frame(&encode_fields(&[
        "4",
        "2",
        "-1",
        &code.to_string(),
        text,
    ])))
}

/// 任意欄位 frame（版本不符 / 未知 msgId / 亂序 等自訂場景）。
pub fn custom_frame(fields: &[&str]) -> FakeFrame {
    FakeFrame(encode_frame(&encode_fields(fields)))
}

// ---- W5-S2 account/positions builders（IN 空間 61-64;IB pinned 欄位序）----

/// accountSummary 行（IN 63;欄序 `[63, version, reqId, account, tag, value, currency]`）。
pub fn account_summary(
    req_id: i64,
    account: &str,
    tag: &str,
    value: &str,
    currency: &str,
) -> FakeFrame {
    FakeFrame(encode_frame(&encode_fields(&[
        "63",
        "1",
        &req_id.to_string(),
        account,
        tag,
        value,
        currency,
    ])))
}

/// accountSummaryEnd（IN 64;`[64, version, reqId]`）——首回全量完成標記。
pub fn account_summary_end(req_id: i64) -> FakeFrame {
    FakeFrame(encode_frame(&encode_fields(&[
        "64",
        "1",
        &req_id.to_string(),
    ])))
}

/// position 行（IN 61;version 3 固定 16 欄:`[61, 3, account, conId, symbol, secType,
/// lastTradeDateOrContractMonth, strike, right, multiplier, exchange, currency, localSymbol,
/// tradingClass, position, avgCost]`——STK 行的 expiry/strike/right/multiplier 佔位欄仍在
/// wire,以空/零值承載）。
#[allow(clippy::too_many_arguments)]
pub fn position_row(
    account: &str,
    con_id: i64,
    symbol: &str,
    sec_type: &str,
    exchange: &str,
    currency: &str,
    position: &str,
    avg_cost: &str,
) -> FakeFrame {
    FakeFrame(encode_frame(&encode_fields(&[
        "61",
        "3",
        account,
        &con_id.to_string(),
        symbol,
        sec_type,
        "",
        "0",
        "",
        "",
        exchange,
        currency,
        symbol,
        symbol,
        position,
        avg_cost,
    ])))
}

/// version<3 的 position 行（15 欄,無 avgCost;G1 負場景:消化端必須 typed 拒,禁捏值）。
pub fn position_row_v2_no_avg_cost(account: &str, con_id: i64, symbol: &str) -> FakeFrame {
    FakeFrame(encode_frame(&encode_fields(&[
        "61",
        "2",
        account,
        &con_id.to_string(),
        symbol,
        "STK",
        "",
        "0",
        "",
        "",
        "ARCA",
        "USD",
        symbol,
        symbol,
        "100",
    ])))
}

/// positionEnd（IN 62;`[62, version]`）——首回全量完成標記。
pub fn position_end() -> FakeFrame {
    FakeFrame(encode_frame(&encode_fields(&["62", "1"])))
}

// ---- W5-S3 open orders/executions/commissions builders（IN 3/5/11/53/55/59;IB pinned
// 欄位序,serverVersion≥136/131/145 無前導 version 欄——commissionReport 除外恆帶 version）----

/// execDetails 行（IN 11;31 定長平面欄:`[11, reqId, orderId, Contract(conId..tradingClass
/// ×11), Execution(execId, time, acctNumber, exchange, side, shares, price, permId, clientId,
/// liquidation, cumQty, avgPrice, orderRef, evRule, evMultiplier, modelCode, lastLiquidity)]`）。
/// `contract_exchange` 與 `exec_exchange` 刻意分參:消化端必綁 Execution.exchange（成交所）。
#[allow(clippy::too_many_arguments)]
pub fn execution_row(
    req_id: i64,
    order_id: i64,
    con_id: i64,
    symbol: &str,
    contract_exchange: &str,
    exec_exchange: &str,
    exec_id: &str,
    exec_time: &str,
    account: &str,
    side: &str,
    shares: &str,
    price: &str,
) -> FakeFrame {
    FakeFrame(encode_frame(&encode_fields(&[
        "11",
        &req_id.to_string(),
        &order_id.to_string(),
        &con_id.to_string(),
        symbol,
        "STK",
        "",
        "0",
        "",
        "",
        contract_exchange,
        "USD",
        symbol,
        symbol,
        exec_id,
        exec_time,
        account,
        exec_exchange,
        side,
        shares,
        price,
        "1000001",
        "0",
        "0",
        shares,
        price,
        "",
        "",
        "",
        "",
        "1",
    ])))
}

/// execDetailsEnd（IN 55;`[55, version, reqId]`）——快照收批標記。
pub fn execution_end(req_id: i64) -> FakeFrame {
    FakeFrame(encode_frame(&encode_fields(&[
        "55",
        "1",
        &req_id.to_string(),
    ])))
}

/// commissionReport（IN 59;8 定長平面欄 `[59, version, execId, commission, currency,
/// realizedPNL, yield_, yieldRedemptionDate]`;前導 version 恆在）。`realized_pnl` 可餵
/// 空欄/精確哨兵/量級哨兵三形態驗消化端哨兵雙判別。
pub fn commission_report(
    exec_id: &str,
    commission: &str,
    currency: &str,
    realized_pnl: &str,
) -> FakeFrame {
    FakeFrame(encode_frame(&encode_fields(&[
        "59",
        "1",
        exec_id,
        commission,
        currency,
        realized_pnl,
        "",
        "",
    ])))
}

/// orderStatus（IN 3;12 定長平面欄 `[3, orderId, status, filled, remaining, avgFillPrice,
/// permId, parentId, lastFillPrice, clientId, whyHeld, mktCapPrice]`）。
pub fn order_status(order_id: i64, status: &str, filled: &str, remaining: &str) -> FakeFrame {
    FakeFrame(encode_frame(&encode_fields(&[
        "3",
        &order_id.to_string(),
        status,
        filled,
        remaining,
        "412.35",
        "1000001",
        "0",
        "412.35",
        "0",
        "",
        "412.35",
    ])))
}

/// openOrder（IN 5;head 前綴 26 欄 `[5, orderId, Contract(conId..tradingClass ×11), action,
/// totalQuantity, orderType, lmtPrice, auxPrice, tif, ocaGroup, account, openClose, origin,
/// orderRef, clientId, permId]` + `tail` 可注入任意尾欄——模擬 66 步全欄尾,消化端
/// head-prefix 讀到 permId 止、tail 整體丟棄+audit）。
#[allow(clippy::too_many_arguments)]
pub fn open_order_head(
    order_id: i64,
    con_id: i64,
    symbol: &str,
    action: &str,
    total_quantity: &str,
    lmt_price: &str,
    account: &str,
    tail: &[&str],
) -> FakeFrame {
    let oid = order_id.to_string();
    let cid = con_id.to_string();
    let mut fields: Vec<&str> = vec![
        "5",
        &oid,
        &cid,
        symbol,
        "STK",
        "",
        "0",
        "",
        "",
        "ARCA",
        "USD",
        symbol,
        symbol,
        action,
        total_quantity,
        "LMT",
        lmt_price,
        "",
        "DAY",
        "",
        account,
        "O",
        "0",
        "",
        "0",
        "1000001",
    ];
    fields.extend_from_slice(tail);
    FakeFrame(encode_frame(&encode_fields(&fields)))
}

/// openOrderEnd（IN 53;`[53, version]`）——快照收批標記。
pub fn open_order_end() -> FakeFrame {
    FakeFrame(encode_frame(&encode_fields(&["53", "1"])))
}

// ===========================================================================
// (c) 場景 DSL + runner
// ===========================================================================

/// fake server 腳本步驟（設計 §4）。
pub enum FakeStep {
    /// 送一個或多個完整 framed 訊息（server→client）。
    Send(Vec<FakeFrame>),
    /// 送原始 bytes（半訊息 / 損壞 / 亂序位元組;不經 framing）。
    SendRaw(Vec<u8>),
    /// 邏輯延遲（tokio sleep;測試以 `tokio::time::pause`+`advance` orchestrate 慢響應/逾時）。
    Delay(Duration),
    /// server 側突然關閉（drop write 半 → client 讀到 EOF;mid-stream 斷線）。
    CloseAbruptly,
    /// **keep-open 靜默**:不回任何 frame、不關閉,write 半永久保持開啟（client 讀持續 pending,
    /// **非 EOF**）。模擬「連線活著但 server 不回應」→ driver 應以心跳 miss 判 liveness（Degraded →
    /// HeartbeatDropped）,而非誤判斷線。**注**:writer 於此 park（持有 sw）,測試須令 driver 的靜默
    /// poll 快速推進（短 `serve_poll` 或 `tokio::time::pause`）。
    SilentDrop,
}

/// fake server 場景（腳本步驟序列）。
pub struct Scenario {
    steps: Vec<FakeStep>,
}

impl Scenario {
    pub fn new(steps: Vec<FakeStep>) -> Self {
        Self { steps }
    }

    /// spawn fake server,回 (client 雙工半, `FakeHandle`)。**兩個獨立任務**:
    ///   - writer:依腳本寫 server→client;完成即返回 → 捕獲的 write 半 `sw` **立即 drop** → client
    ///     讀到 EOF。**必須獨立於 reader**——否則 `tokio::join!` 會扣住已完成 writer 的 `sw` 直到
    ///     reader 也完成,而 reader 等 client drop（需 client 先讀到 EOF）→ 死鎖。
    ///   - reader:讀 client→server 全量入共享 buffer（client drop → EOF → 完成;供 `received_*` 檢視）。
    /// **需 tokio runtime context**（測試 `#[tokio::test]` 提供）。
    pub fn spawn(self) -> (DuplexStream, FakeHandle) {
        let (client, server) = tokio::io::duplex(DUPLEX_CAP);
        let (mut sr, mut sw) = tokio::io::split(server);
        let received = Arc::new(Mutex::new(Vec::new()));
        let recv2 = received.clone();
        let steps_done = Arc::new(AtomicUsize::new(0));
        let done2 = steps_done.clone();
        let total_steps = self.steps.len();
        let steps = self.steps;

        // writer 任務（detached）:播腳本;完成即 **shutdown sw**（write 半）→ client 讀 EOF。
        // **關鍵**:`split` 下僅 drop `sw`（WriteHalf）不會關通道——`sr`（ReadHalf）仍持有底層
        // DuplexStream → client 永不見 EOF。必須顯式 `shutdown().await` 關 write 方向送 EOF。
        tokio::spawn(async move {
            for step in steps {
                match step {
                    FakeStep::Send(frames) => {
                        for f in frames {
                            if sw.write_all(&f.0).await.is_err() {
                                return;
                            }
                        }
                    }
                    FakeStep::SendRaw(bytes) => {
                        if sw.write_all(&bytes).await.is_err() {
                            return;
                        }
                    }
                    FakeStep::Delay(d) => tokio::time::sleep(d).await,
                    FakeStep::CloseAbruptly => {
                        // 計入本步 → shutdown sw → client 讀 EOF（mid-stream 斷線）。
                        done2.fetch_add(1, Ordering::SeqCst);
                        let _ = sw.shutdown().await;
                        return;
                    }
                    FakeStep::SilentDrop => {
                        // keep-open:park 於此持有 sw（不 shutdown、不回 frame）→ client 讀持續 pending
                        // （非 EOF）。driver 以心跳 miss 判 liveness。task 於測試結束時被 runtime 清理。
                        done2.fetch_add(1, Ordering::SeqCst);
                        std::future::pending::<()>().await;
                    }
                }
                done2.fetch_add(1, Ordering::SeqCst);
            }
            // 腳本走完 → shutdown sw（送 EOF 給 client）。
            let _ = sw.shutdown().await;
        });

        // reader 任務:讀 client→server 全量直到 client drop（driver 結束連線）。
        let reader_join = tokio::spawn(async move {
            let mut buf = Vec::new();
            let _ = sr.read_to_end(&mut buf).await;
            *recv2.lock().unwrap() = buf;
        });

        (
            client,
            FakeHandle {
                received,
                steps_done,
                total_steps,
                join: Some(reader_join),
            },
        )
    }
}

// ===========================================================================
// (d) FakeHandle（檢視 driver 送出 + 腳本耗盡斷言）
// ===========================================================================

/// fake server 控制柄:檢視 client（driver）送出的位元組 / 訊息 frame + 斷言腳本耗盡。
pub struct FakeHandle {
    received: Arc<Mutex<Vec<u8>>>,
    steps_done: Arc<AtomicUsize>,
    total_steps: usize,
    join: Option<JoinHandle<()>>,
}

impl FakeHandle {
    /// join server 任務（等 client drop → reader 讀完）後回 client 送出的原始位元組。
    pub async fn received_bytes(mut self) -> Vec<u8> {
        if let Some(j) = self.join.take() {
            let _ = j.await;
        }
        self.received.lock().unwrap().clone()
    }

    /// join 後回 client 送出的**訊息 frame payload**（跳過 `API\0` 連線前綴 + 其後 framed 版本字串;
    /// 其餘 = START_API / reqCurrentTime / 心跳 等 framed 訊息）。
    pub async fn received_message_frames(self) -> Vec<Vec<u8>> {
        let bytes = self.received_bytes().await;
        let mut rest = bytes.as_slice();
        // 跳過 `API\0`（4 bytes）連線前綴。
        if rest.len() >= 4 && &rest[..4] == b"API\0" {
            rest = &rest[4..];
            // 跳過版本 frame（4-byte len + payload;非訊息）。
            if rest.len() >= 4 {
                let len = u32::from_be_bytes([rest[0], rest[1], rest[2], rest[3]]) as usize;
                if rest.len() >= 4 + len {
                    rest = &rest[4 + len..];
                }
            }
        }
        decode_all_frames(rest)
    }

    /// 已完成的腳本步驟數（CloseAbruptly 亦計）。
    pub fn steps_done(&self) -> usize {
        self.steps_done.load(Ordering::SeqCst)
    }

    /// 斷言腳本全步驟已播畢（happy 場景驗 driver 消費完整握手序列;CloseAbruptly 場景不適用）。
    pub fn assert_script_exhausted(&self) {
        let done = self.steps_done();
        assert_eq!(
            done, self.total_steps,
            "fake 腳本未播畢:{done}/{} 步（driver 未消費完整場景?）",
            self.total_steps
        );
    }
}

// ===========================================================================
// (e) canned 場景庫（W3 driver 端到端 + W4-W7/W10 復用;設計 §4）
// ===========================================================================

pub mod scenarios {
    use super::*;

    /// 預設 paper 握手序列（ACK v176 + managedAccounts DU + nextValidId + 兩則 farm-OK info +
    /// currentTime）——driver 應到 Ready。
    pub fn happy_handshake_frames() -> Vec<FakeFrame> {
        vec![
            handshake_ack(176, "20260716 09:30:00 EST"),
            managed_accounts("DU1234567"),
            next_valid_id(42),
            err_msg(2104, "Market data farm connection is OK:usfarm"),
            err_msg(2106, "HMDS data farm connection is OK:ushmds"),
            current_time(1_700_000_000),
        ]
    }

    /// happy session:握手到 Ready,腳本走完 → client EOF（serve 讀 EOF → IoDropped）。
    pub fn happy_session() -> Scenario {
        Scenario::new(vec![FakeStep::Send(happy_handshake_frames())])
    }

    /// happy session + 一則心跳回覆（serve 期 driver 送心跳,fake 預載一則 currentTime 回覆）。
    pub fn happy_with_one_heartbeat_reply() -> Scenario {
        let mut frames = happy_handshake_frames();
        frames.push(current_time(1_700_000_030)); // serve 期心跳回覆
        Scenario::new(vec![FakeStep::Send(frames)])
    }

    /// 版本不符:ACK server_version=50（< pin 100）→ driver 自檢 fail-closed（ServerVersionTooOld）。
    pub fn version_too_old() -> Scenario {
        Scenario::new(vec![FakeStep::Send(vec![handshake_ack(
            50,
            "20260716 09:30:00 EST",
        )])])
    }

    /// duplicate client-id:握手期 ERR_MSG 326（拒新連線）→ driver fatal（DuplicateClientIdRejected）。
    pub fn kick_duplicate_client() -> Scenario {
        Scenario::new(vec![FakeStep::Send(vec![
            handshake_ack(176, "20260716 09:30:00 EST"),
            err_msg(326, "client id already in use"),
        ])])
    }

    /// 非 paper session:managedAccounts 含 live 帳號（U…）→ driver fatal（NonPaperSession）。
    pub fn non_paper_session() -> Scenario {
        Scenario::new(vec![FakeStep::Send(vec![
            handshake_ack(176, "20260716 09:30:00 EST"),
            managed_accounts("U1234567"),
        ])])
    }

    /// **W5-S4 混合帳戶**:managedAccounts 全 DU 中混入一個 U*（live）→ 白名單實檢
    /// all_paper=false → driver fatal（NonPaperSession）+ attestation Blocked
    /// （`account_fingerprint_is_live=true` 語義）。
    pub fn mixed_paper_live_session() -> Scenario {
        Scenario::new(vec![FakeStep::Send(vec![
            handshake_ack(176, "20260716 09:30:00 EST"),
            managed_accounts("DU1234567,U7654321"),
        ])])
    }

    /// **W5-S4 IN 15 缺席**:握手直到 currentTime(49) 全程無 managedAccounts → paper 實檢
    /// 未立 → driver transient false-fail（重試;絕不以未見當已驗證,attestation 只可產
    /// Blocked）。與 `reordered_handshake`（15 晚於 49）同族,此為全缺席形。
    pub fn missing_managed_accounts() -> Scenario {
        Scenario::new(vec![FakeStep::Send(vec![
            handshake_ack(176, "20260716 09:30:00 EST"),
            next_valid_id(42),
            current_time(1_700_000_000),
        ])])
    }

    /// 握手期致命 gateway error（502 未連線,<2100）→ driver fatal（GatewayError(502)）。
    pub fn handshake_gateway_error() -> Scenario {
        Scenario::new(vec![FakeStep::Send(vec![
            handshake_ack(176, "20260716 09:30:00 EST"),
            err_msg(502, "Couldn't connect to TWS"),
        ])])
    }

    /// 亂序握手:currentTime(49) 早於 managedAccounts(15) → 未實檢 paper 即到 49 → transient。
    pub fn reordered_handshake() -> Scenario {
        Scenario::new(vec![FakeStep::Send(vec![
            handshake_ack(176, "20260716 09:30:00 EST"),
            current_time(1_700_000_000), // 49 早於 15
            managed_accounts("DU1234567"),
        ])])
    }

    /// 半訊息斷線:ACK 後送半個 frame（4-byte len 宣稱 8 bytes,只給 3）再突然關閉 → codec 不成完整
    /// frame + EOF → transient。
    pub fn half_message_disconnect() -> Scenario {
        let ack = handshake_ack(176, "20260716 09:30:00 EST");
        // 半個 frame:宣稱 payload 8 bytes,只送 3 bytes。
        let mut partial = 8u32.to_be_bytes().to_vec();
        partial.extend_from_slice(&[1, 2, 3]);
        Scenario::new(vec![
            FakeStep::Send(vec![ack]),
            FakeStep::SendRaw(partial),
            FakeStep::CloseAbruptly,
        ])
    }

    /// mid-stream 斷線:到 Ready 後 server 突然關閉（serve 讀 EOF → IoDropped → Backoff）。
    pub fn mid_stream_disconnect() -> Scenario {
        Scenario::new(vec![
            FakeStep::Send(happy_handshake_frames()),
            FakeStep::CloseAbruptly,
        ])
    }

    /// pacing 違規:到 Ready 後 server 連送三則 error-100（driver governor strike 三振 → 斷 session）。
    pub fn pacing_violation() -> Scenario {
        let mut frames = happy_handshake_frames();
        frames.push(err_msg(
            100,
            "Max rate of messages per second has been reached",
        ));
        frames.push(err_msg(
            100,
            "Max rate of messages per second has been reached",
        ));
        frames.push(err_msg(
            100,
            "Max rate of messages per second has been reached",
        ));
        Scenario::new(vec![FakeStep::Send(frames)])
    }

    /// serve 期 session-fatal error frame（504 未連線）→ driver 斷 session（SessionFatal）。
    pub fn serve_fatal_error() -> Scenario {
        let mut frames = happy_handshake_frames();
        frames.push(err_msg(504, "Not connected"));
        Scenario::new(vec![FakeStep::Send(frames)])
    }

    /// serve 期 farm-blip transient（2103 mkt-data farm lost）→ N2:不觸過早 reconnect,續 serve。
    pub fn serve_farm_blip_then_close() -> Scenario {
        let mut frames = happy_handshake_frames();
        frames.push(err_msg(2103, "A market data farm connection has been lost"));
        Scenario::new(vec![FakeStep::Send(frames)])
    }

    /// serve 期重複 currentTime（duplicate 事件）→ driver 容忍（spurious 心跳回覆,不斷線）。
    pub fn serve_duplicate_current_time() -> Scenario {
        let mut frames = happy_handshake_frames();
        frames.push(current_time(1_700_000_030));
        frames.push(current_time(1_700_000_031)); // 重複
        Scenario::new(vec![FakeStep::Send(frames)])
    }

    /// serve 期未知 msgId（8,不在 {4,9,15,49} 白名單）→ driver fail-closed 斷線（→ Backoff）。
    pub fn serve_unknown_msg_id() -> Scenario {
        let mut frames = happy_handshake_frames();
        frames.push(custom_frame(&["8", "1", "0"]));
        Scenario::new(vec![FakeStep::Send(frames)])
    }

    /// **靜默 server**:握手到 Ready 後 keep-open 不回任何 frame（不 EOF）→ driver 應以心跳 miss 判
    /// liveness:Degraded → 續 miss → HeartbeatDropped（設計 §1.2;測試以短 `serve_poll` 令 poll 推進）。
    pub fn silent_after_handshake() -> Scenario {
        Scenario::new(vec![
            FakeStep::Send(happy_handshake_frames()),
            FakeStep::SilentDrop,
        ])
    }

    // ---- W5-S2 account/positions 場景 ----

    /// **W5-S2 happy account-data session**:握手到 Ready 後推 summary 全量（2 tag）→ End →
    /// positions 全量（1 倉）→ positionEnd → summary 節拍增量（變動 tag 覆蓋）→ 腳本盡 EOF。
    /// `req_id` 由消化端對齊（engine 側固定 reqId）。fake 為腳本化 push——不等 driver 的
    /// req 訊息即推（driver 首 serve tick 先送訂閱再讀,時序天然成立）。
    pub fn account_data_session(req_id: i64) -> Scenario {
        let mut frames = happy_handshake_frames();
        frames.push(account_summary(
            req_id,
            "DU1234567",
            "NetLiquidation",
            "100000.25",
            "USD",
        ));
        frames.push(account_summary(
            req_id,
            "DU1234567",
            "BuyingPower",
            "50000",
            "USD",
        ));
        frames.push(account_summary_end(req_id));
        frames.push(position_row(
            "DU1234567",
            756733,
            "SPY",
            "STK",
            "ARCA",
            "USD",
            "100",
            "412.35",
        ));
        frames.push(position_end());
        // 節拍增量:變動 tag 覆蓋(IB 每 3 分鐘僅推變動 tag)。
        frames.push(account_summary(
            req_id,
            "DU1234567",
            "BuyingPower",
            "48000",
            "USD",
        ));
        Scenario::new(vec![FakeStep::Send(frames)])
    }

    /// **W5-S2 負場景:表外 tag**:End 前推白名單外 tag（"Cushion"）→ 消化端走契約
    /// `UnknownDenied` blocker 路徑（快照 Invalidated,session 不斷、不 panic）。
    pub fn account_summary_off_whitelist_tag(req_id: i64) -> Scenario {
        let mut frames = happy_handshake_frames();
        frames.push(account_summary(
            req_id,
            "DU1234567",
            "Cushion",
            "0.5",
            "USD",
        ));
        Scenario::new(vec![FakeStep::Send(frames)])
    }

    /// **W5-S2 負場景:G1 version<3 position 行**（無 avgCost 欄）→ 消化端 typed 拒
    /// （禁 ibapi 式默認 avgCost=0 捏值）,session 不斷。
    pub fn position_version_too_old() -> Scenario {
        let mut frames = happy_handshake_frames();
        frames.push(position_row_v2_no_avg_cost("DU1234567", 756733, "SPY"));
        frames.push(position_end());
        Scenario::new(vec![FakeStep::Send(frames)])
    }

    /// **W5-S2 負場景:壞欄位 summary 行**（reqId 非數字）→ wire 損壞,消化端
    /// `WireMalformed` → driver fail-closed 斷線。
    pub fn account_summary_malformed(_req_id: i64) -> Scenario {
        let mut frames = happy_handshake_frames();
        frames.push(custom_frame(&[
            "63",
            "1",
            "abc",
            "DU1234567",
            "NetLiquidation",
            "1",
            "USD",
        ]));
        Scenario::new(vec![FakeStep::Send(frames)])
    }

    /// **W5-S2 cancel 對稱場景**:summary 全量 → End 後腳本盡 EOF(消化端 cancel 出站由
    /// driver 測試側驅動;fake 只驗收到 cancel frame)。
    pub fn account_summary_then_idle(req_id: i64) -> Scenario {
        let mut frames = happy_handshake_frames();
        frames.push(account_summary(
            req_id,
            "DU1234567",
            "NetLiquidation",
            "100000.25",
            "USD",
        ));
        frames.push(account_summary_end(req_id));
        Scenario::new(vec![FakeStep::Send(frames)])
    }

    // ---- W5-S3 open orders/executions/commissions 場景 ----

    /// grammar 合法的 exec_time 樣式（UTC 形 `^\d{8}-\d{2}:\d{2}:\d{2}$`;shape-only 驗形,
    /// 無牆鐘依賴——非當前日期,無日期腐化 time-bomb 面）。
    pub const EXEC_TIME_FIXTURE: &str = "20200102-13:30:05";

    /// **W5-S3 happy order/exec session**:握手到 Ready 後——exec 快照行 e1 → **亂序**
    /// commission e2 先到(其 exec 尚未到,孤兒緩存) → execDetailsEnd → unsolicited 推送
    /// exec e2(reqId=-1) → commission e1 後到(補齊 join) → orderStatus 重複×2(冪等去重)
    /// → openOrder head(帶 2 尾欄,tail-discard) → openOrderEnd → 腳本盡 EOF。
    /// e1/e2 兩 exchange 欄異值(SMART vs ARCA/NYSE)驗 Execution.exchange 綁定。
    pub fn order_exec_session(req_id: i64) -> Scenario {
        let mut frames = happy_handshake_frames();
        frames.push(execution_row(
            req_id,
            7,
            756733,
            "SPY",
            "SMART",
            "ARCA",
            "e1",
            EXEC_TIME_FIXTURE,
            "DU1234567",
            "BOT",
            "100",
            "412.35",
        ));
        // 亂序:e2 的 commission 先到(execDetails 與 commissionReport 無到達順序保證)。
        frames.push(commission_report("e2", "1.10", "USD", "0"));
        frames.push(execution_end(req_id));
        // unsolicited 推送(reqId=-1 慣稱):e2 的 exec 後到,補齊 join。
        frames.push(execution_row(
            -1,
            8,
            756733,
            "SPY",
            "SMART",
            "NYSE",
            "e2",
            EXEC_TIME_FIXTURE,
            "DU1234567",
            "SLD",
            "50",
            "413.00",
        ));
        frames.push(commission_report("e1", "1.25", "USD", "-3.50"));
        // orderStatus 重複推送(官方明言常有重複 → 消化端冪等去重)。
        frames.push(order_status(7, "Filled", "100", "0"));
        frames.push(order_status(7, "Filled", "100", "0"));
        // openOrder head + 2 尾欄(66 步全欄尾模擬 → head-prefix 消化,tail 丟棄+audit)。
        frames.push(open_order_head(
            9,
            756733,
            "SPY",
            "BUY",
            "10",
            "410.00",
            "DU1234567",
            &["tail_a", "tail_b"],
        ));
        frames.push(open_order_end());
        Scenario::new(vec![FakeStep::Send(frames)])
    }

    /// **W5-S3 哨兵三形態場景**:commission realizedPNL=空欄/精確哨兵字串(小寫 e)/量級
    /// 哨兵(負側)→ 消化端全映 None+audit;`0` 對照恆 Some("0")。
    pub fn commission_sentinel_session(req_id: i64) -> Scenario {
        let mut frames = happy_handshake_frames();
        frames.push(execution_end(req_id));
        frames.push(commission_report("s1", "1.00", "USD", ""));
        frames.push(commission_report(
            "s2",
            "1.00",
            "USD",
            "1.7976931348623157e308",
        ));
        frames.push(commission_report(
            "s3",
            "1.00",
            "USD",
            "-1.7976931348623157E308",
        ));
        frames.push(commission_report("s4", "1.00", "USD", "0"));
        Scenario::new(vec![FakeStep::Send(frames)])
    }

    /// **W5-S3 負場景:表外 orderStatus**(`ApiPending` 屬表外)→ 消化端 UnknownDenied:
    /// audit 計數+open-orders 面毒化,session 不斷、不 panic。
    pub fn order_status_unknown_denied_session() -> Scenario {
        let mut frames = happy_handshake_frames();
        frames.push(order_status(7, "ApiPending", "0", "100"));
        Scenario::new(vec![FakeStep::Send(frames)])
    }

    /// **W5-S3 負場景:壞欄位 exec 行**(reqId 非數字)→ wire 損壞,消化端 `WireMalformed`
    /// → driver fail-closed 斷線。
    pub fn execution_malformed_session() -> Scenario {
        let mut frames = happy_handshake_frames();
        let good = execution_row(
            1,
            7,
            756733,
            "SPY",
            "SMART",
            "ARCA",
            "e1",
            EXEC_TIME_FIXTURE,
            "DU1234567",
            "BOT",
            "100",
            "412.35",
        );
        // 以合規 frame 重組:reqId 欄替換為非數字(其餘 30 欄形狀不變)。
        let mut fields = frame_fields(&decode_all_frames(&good.0)[0]);
        fields[1] = "abc".to_string();
        let refs: Vec<&str> = fields.iter().map(String::as_str).collect();
        frames.push(custom_frame(&refs));
        Scenario::new(vec![FakeStep::Send(frames)])
    }

    /// **W5-S3 負場景:ceiling 佈局窗**——happy 握手 sv=176(>157 pinned),exec 行帶 1 個
    /// 尾部多欄 → 消化端 `PinnedLayoutOverflow` frame 拒收+audit(禁猜讀),session 存活。
    pub fn execution_ceiling_overflow_session(req_id: i64) -> Scenario {
        let mut frames = happy_handshake_frames();
        let good = execution_row(
            req_id,
            7,
            756733,
            "SPY",
            "SMART",
            "ARCA",
            "e1",
            EXEC_TIME_FIXTURE,
            "DU1234567",
            "BOT",
            "100",
            "412.35",
        );
        let mut fields = frame_fields(&decode_all_frames(&good.0)[0]);
        fields.push("surplus".to_string());
        let refs: Vec<&str> = fields.iter().map(String::as_str).collect();
        frames.push(custom_frame(&refs));
        Scenario::new(vec![FakeStep::Send(frames)])
    }
}

// ===========================================================================
// 自測（含零 socket 源守衛）
// ===========================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn frame_codec_roundtrip() {
        let framed = encode_frame(b"hello");
        assert_eq!(&framed[..4], &[0, 0, 0, 5]);
        let frames = decode_all_frames(&framed);
        assert_eq!(frames, vec![b"hello".to_vec()]);
    }

    #[test]
    fn fields_roundtrip() {
        let f = encode_fields(&["49", "1", "123"]);
        assert_eq!(f, b"49\x001\x00123\x00");
        assert_eq!(frame_fields(&f), vec!["49", "1", "123"]);
    }

    #[test]
    fn builders_produce_expected_bytes() {
        assert_eq!(current_time(1).0, encode_frame(b"49\x001\x001\x00"));
        assert_eq!(
            managed_accounts("DU1").0,
            encode_frame(b"15\x001\x00DU1\x00")
        );
        assert_eq!(next_valid_id(42).0, encode_frame(b"9\x001\x0042\x00"));
        assert_eq!(
            err_msg(100, "x").0,
            encode_frame(b"4\x002\x00-1\x00100\x00x\x00")
        );
    }

    #[tokio::test]
    async fn spawn_plays_frames_and_closes_to_eof() {
        let scn = Scenario::new(vec![FakeStep::Send(vec![current_time(7)])]);
        let (mut client, handle) = scn.spawn();
        // client 讀到 server 送的 frame,然後 EOF。
        let mut buf = Vec::new();
        client.read_to_end(&mut buf).await.unwrap();
        assert_eq!(
            decode_all_frames(&buf),
            vec![encode_fields(&["49", "1", "7"])]
        );
        // client drop → reader 完成。received 空（本測試未寫任何 client→server）。
        drop(client);
        assert!(handle.received_bytes().await.is_empty());
    }

    #[tokio::test]
    async fn handle_records_client_sent_bytes() {
        let scn = Scenario::new(vec![FakeStep::Send(vec![current_time(1)])]);
        let (mut client, handle) = scn.spawn();
        // client 送一個 frame 給 server,再讀 server 的 + EOF。
        client
            .write_all(&encode_frame(b"71\x002\x000\x00"))
            .await
            .unwrap();
        let mut buf = Vec::new();
        client.read_to_end(&mut buf).await.unwrap();
        drop(client);
        let frames = handle.received_message_frames().await;
        // received_message_frames 無 API\0 前綴（本測試未送前綴）→ 直接解 START_API frame。
        assert_eq!(frames, vec![encode_fields(&["71", "2", "0"])]);
    }

    #[tokio::test]
    async fn silent_drop_keeps_connection_open_not_eof() {
        // 握手 frames 後 SilentDrop keep-open:讀到 frames,其後讀應 **pending**（短 timeout 逾時,非 EOF）。
        let (mut client, _handle) = scenarios::silent_after_handshake().spawn();
        let mut buf = vec![0u8; 8192];
        let n = client.read(&mut buf).await.unwrap();
        assert!(n > 0, "應先收到握手 frames");
        // 其後 keep-open → 讀 pending;以短真 timeout 證「逾時（非 return 0 EOF）」。
        let r = tokio::time::timeout(Duration::from_millis(50), client.read(&mut buf)).await;
        assert!(r.is_err(), "SilentDrop 應 keep-open（讀 timeout,非 EOF）");
    }

    #[tokio::test]
    async fn close_abruptly_gives_early_eof() {
        let scn = Scenario::new(vec![
            FakeStep::Send(vec![current_time(1)]),
            FakeStep::CloseAbruptly,
        ]);
        let (mut client, _handle) = scn.spawn();
        let mut buf = Vec::new();
        client.read_to_end(&mut buf).await.unwrap();
        // 只收到 CloseAbruptly 前的 frame。
        assert_eq!(decode_all_frames(&buf).len(), 1);
    }

    #[test]
    fn canned_scenarios_construct() {
        // 冒煙:場景庫建構不 panic + 步驟非空。
        let _ = scenarios::happy_session();
        let _ = scenarios::version_too_old();
        let _ = scenarios::kick_duplicate_client();
        let _ = scenarios::pacing_violation();
        let _ = scenarios::mid_stream_disconnect();
        let _ = scenarios::half_message_disconnect();
        let _ = scenarios::reordered_handshake();
        let _ = scenarios::serve_duplicate_current_time();
        let _ = scenarios::non_paper_session();
        let _ = scenarios::serve_unknown_msg_id();
        let _ = scenarios::silent_after_handshake();
        // W5-S2 account/positions 場景。
        let _ = scenarios::account_data_session(9001);
        let _ = scenarios::account_summary_off_whitelist_tag(9001);
        let _ = scenarios::position_version_too_old();
        let _ = scenarios::account_summary_malformed(9001);
        let _ = scenarios::account_summary_then_idle(9001);
        // W5-S3 open orders/executions/commissions 場景。
        let _ = scenarios::order_exec_session(9002);
        let _ = scenarios::commission_sentinel_session(9002);
        let _ = scenarios::order_status_unknown_denied_session();
        let _ = scenarios::execution_malformed_session();
        let _ = scenarios::execution_ceiling_overflow_session(9002);
        // W5-S4 session attestation 場景。
        let _ = scenarios::mixed_paper_live_session();
        let _ = scenarios::missing_managed_accounts();
    }

    #[test]
    fn w5_s4_attestation_scenarios_compose_expected_frames() {
        // 混合帳戶場景:managedAccounts csv 原文透傳（DU+U 混合,消化端白名單實檢據此拒）。
        assert_eq!(
            managed_accounts("DU1234567,U7654321").0,
            encode_frame(b"15\x001\x00DU1234567,U7654321\x00")
        );
        // IN 15 缺席場景:ack + 9 + 49,全程無 msgId 15 frame。
        let scn = scenarios::missing_managed_accounts();
        let frames: Vec<Vec<u8>> = match &scn.steps[0] {
            FakeStep::Send(fs) => fs.iter().map(|f| f.0.clone()).collect(),
            _ => panic!("首步應為 Send"),
        };
        assert_eq!(frames.len(), 3);
        for f in &frames[1..] {
            let fields = frame_fields(&decode_all_frames(f)[0]);
            assert_ne!(fields[0], "15", "IN 15 缺席場景不得含 managedAccounts");
        }
    }

    #[test]
    fn w5_s3_order_exec_builders_produce_pinned_field_order() {
        // IN 11 execDetails = 31 定長平面欄;Contract.exchange(idx 10)與
        // Execution.exchange(idx 17)異值分參。
        let f = frame_fields(
            &decode_all_frames(
                &execution_row(
                    9002,
                    7,
                    756733,
                    "SPY",
                    "SMART",
                    "ARCA",
                    "e1",
                    scenarios::EXEC_TIME_FIXTURE,
                    "DU1",
                    "BOT",
                    "100",
                    "412.35",
                )
                .0,
            )[0],
        );
        assert_eq!(f.len(), 31);
        assert_eq!(&f[..3], &["11", "9002", "7"]);
        assert_eq!(f[10], "SMART", "Contract.exchange 於 idx 10");
        assert_eq!(f[14], "e1", "Execution.execId 於 idx 14");
        assert_eq!(f[17], "ARCA", "Execution.exchange(成交所)於 idx 17");
        assert_eq!(f[18], "BOT");
        assert_eq!((f[19].as_str(), f[20].as_str()), ("100", "412.35"));
        assert_eq!(f[21], "1000001", "permId 於 idx 21");
        // IN 55 execDetailsEnd = [55, 1, reqId]。
        assert_eq!(
            frame_fields(&decode_all_frames(&execution_end(9002).0)[0]),
            vec!["55", "1", "9002"]
        );
        // IN 59 commissionReport = 8 欄(前導 version 恆在)。
        let f = frame_fields(&decode_all_frames(&commission_report("e1", "1.25", "USD", "0").0)[0]);
        assert_eq!(f, vec!["59", "1", "e1", "1.25", "USD", "0", "", ""]);
        // IN 3 orderStatus = 12 欄。
        let f = frame_fields(&decode_all_frames(&order_status(7, "Filled", "100", "0").0)[0]);
        assert_eq!(f.len(), 12);
        assert_eq!(&f[..5], &["3", "7", "Filled", "100", "0"]);
        // IN 5 openOrder = 26 head 欄 + tail 注入。
        let f = frame_fields(
            &decode_all_frames(
                &open_order_head(
                    9,
                    756733,
                    "SPY",
                    "BUY",
                    "10",
                    "410.00",
                    "DU1",
                    &["t1", "t2"],
                )
                .0,
            )[0],
        );
        assert_eq!(f.len(), 28, "26 head + 2 tail");
        assert_eq!(&f[..2], &["5", "9"]);
        assert_eq!(f[13], "BUY", "action 於 idx 13");
        assert_eq!(f[16], "410.00", "lmtPrice 於 idx 16");
        assert_eq!(f[25], "1000001", "permId 於 idx 25(head 止點)");
        // IN 53 openOrderEnd = [53, 1]。
        assert_eq!(
            frame_fields(&decode_all_frames(&open_order_end().0)[0]),
            vec!["53", "1"]
        );
    }

    #[test]
    fn w5_account_data_builders_produce_pinned_field_order() {
        // IN 63 accountSummary = [63, 1, reqId, account, tag, value, currency]。
        assert_eq!(
            frame_fields(
                &decode_all_frames(&account_summary(7, "DU1", "NetLiquidation", "1.5", "USD").0)[0]
            ),
            vec!["63", "1", "7", "DU1", "NetLiquidation", "1.5", "USD"]
        );
        // IN 64 accountSummaryEnd = [64, 1, reqId]。
        assert_eq!(
            frame_fields(&decode_all_frames(&account_summary_end(7).0)[0]),
            vec!["64", "1", "7"]
        );
        // IN 61 position v3 = 16 欄(佔位欄按位在 wire)。
        let f = frame_fields(
            &decode_all_frames(
                &position_row("DU1", 756733, "SPY", "STK", "ARCA", "USD", "100", "412.35").0,
            )[0],
        );
        assert_eq!(f.len(), 16);
        assert_eq!(&f[..2], &["61", "3"]);
        assert_eq!(f[14], "100");
        assert_eq!(f[15], "412.35");
        // v2 負場景 = 15 欄(無 avgCost)。
        let f =
            frame_fields(&decode_all_frames(&position_row_v2_no_avg_cost("DU1", 1, "SPY").0)[0]);
        assert_eq!(f.len(), 15);
        assert_eq!(&f[..2], &["61", "2"]);
        // IN 62 positionEnd = [62, 1]。
        assert_eq!(
            frame_fields(&decode_all_frames(&position_end().0)[0]),
            vec!["62", "1"]
        );
    }

    // ---- 零 socket 源守衛（本 crate 源碼絕不含真實網路連線型別;in-crate 第一道防線）----
    // needle 以 concat! 於編譯期組裝,令 verbatim token 不出現在本檔源碼,避免 include_str! 自我命中。
    #[test]
    fn source_has_no_real_socket_symbols() {
        let src = include_str!("lib.rs");
        let forbidden = [
            concat!("Tcp", "Stream"),
            concat!("Tcp", "Listener"),
            concat!("Unix", "Stream"),
            concat!("Unix", "Listener"),
            concat!("std", "::net"),
            concat!("tokio", "::net"),
        ];
        for needle in forbidden {
            assert!(
                !src.contains(needle),
                "fake crate 源含真實 socket 型別 token: {needle}"
            );
        }
    }
}
