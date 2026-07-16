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
