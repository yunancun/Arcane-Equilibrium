//! W3-S4 session driver 端到端測試（拆檔;`ibkr_tws_driver.rs` 主體 + 測試分檔,同 session/pacing
//! 範式）。以 dev-crate `openclaw_fake_tws`（tokio in-process duplex,零真 socket）+ **test-only
//! granting provider**（production 域不存在 → INV-1）串起 S1(wire)+S2(FSM)+S3(pacing) 全鏈:
//! 冷啟/握手/心跳/各故障注入/重連對賬。全注入時鐘（`TestClock`）,fixture 禁硬編日期。

use super::*;

use std::collections::VecDeque;

use tokio::io::DuplexStream;

use openclaw_fake_tws::scenarios::happy_handshake_frames;
use openclaw_fake_tws::{current_time, err_msg, frame_fields, scenarios, FakeStep, Scenario};

use crate::ibkr_tws_pacing::{OutboundClass, PacingConfig};
use crate::ibkr_tws_session::{
    ConnectDenied, EnvelopeRequiredStub, FatalCause, HaltReason, HeartbeatOutbound, PermitToken,
    TwsSessionManager,
};

// ---------------------------------------------------------------------------
// 測試輔助:granting provider（test-only）/ transport factory 各型 / 注入時鐘
// ---------------------------------------------------------------------------

/// **test-only 放行 permit provider**（production 域不存在此型別 → INV-1:production 唯一
/// `ConnectPermitProvider` 實作 = `EnvelopeRequiredStub` 恆拒;此型別使 fake 域走通 connect）。
/// 定義於 driver 測試檔（非 `ibkr_tws_session.rs`）→ S2 INV-1 permit-stub 靜態守衛不掃此檔。
struct GrantingProvider;

impl ConnectPermitProvider for GrantingProvider {
    fn check(&mut self) -> Result<PermitToken, ConnectDenied> {
        Ok(PermitToken::mint())
    }
}

/// 注入時鐘（固定 now,可 set/advance;serve loop 每迭代取同值,測試以 now 控心跳/退避時序）。
struct TestClock {
    now: u64,
}

impl TestClock {
    fn at(now: u64) -> Self {
        Self { now }
    }
    fn set(&mut self, v: u64) {
        self.now = v;
    }
}

impl DriverClock for TestClock {
    fn now_ms(&mut self) -> u64 {
        self.now
    }
}

/// **可 advance 的注入時鐘**:每次 `now_ms()` 回當前值後自增 `step`（serve loop 每迭代取一次 → 邏輯
/// 時間隨迭代前進）。用於驅動心跳排程/劣化/drop 的時間流逝（配 `start_paused` 令 driver 的 serve
/// poll 逾時即時推進 tokio 時鐘;二時鐘獨立,注入時鐘驅心跳、tokio 驅 poll 喚醒）。
struct AdvancingClock {
    now: u64,
    step: u64,
}

impl AdvancingClock {
    fn new(start: u64, step: u64) -> Self {
        Self { now: start, step }
    }
}

impl DriverClock for AdvancingClock {
    fn now_ms(&mut self) -> u64 {
        let v = self.now;
        self.now = self.now.saturating_add(self.step);
        v
    }
}

/// pacing config:lines=20 → rate=10 msg/s（100ms/token < queue_timeout 500ms;令佇列心跳可在逾時前
/// 補足 token 放行）,capacity=10 token（≥握手 2 control）。
fn queueable_pacing() -> PacingConfig {
    PacingConfig {
        market_data_lines: 20,
        ..PacingConfig::default()
    }
}

/// 一次性 transport:回預 spawn 的 client duplex 一次,其後 Refused。
struct OneShotTransport {
    stream: Option<DuplexStream>,
}

impl TransportFactory for OneShotTransport {
    type Stream = DuplexStream;
    fn connect(
        &mut self,
    ) -> impl std::future::Future<Output = Result<Self::Stream, TransportError>> {
        let s = self.stream.take();
        async move { s.ok_or_else(|| TransportError::Refused("one-shot exhausted".into())) }
    }
}

/// 腳本化 transport:每次 connect spawn 佇列中下個場景（重連測試;連完場景 → Refused）。
struct ScriptedTransport {
    scenarios: VecDeque<Scenario>,
}

impl TransportFactory for ScriptedTransport {
    type Stream = DuplexStream;
    fn connect(
        &mut self,
    ) -> impl std::future::Future<Output = Result<Self::Stream, TransportError>> {
        let next = self.scenarios.pop_front();
        async move {
            match next {
                Some(scn) => {
                    let (client, _handle) = scn.spawn();
                    Ok(client)
                }
                None => Err(TransportError::Refused("no more scenarios".into())),
            }
        }
    }
}

/// 恆拒 transport（connect refused → Backoff）。
struct RefusingTransport;

impl TransportFactory for RefusingTransport {
    type Stream = DuplexStream;
    fn connect(
        &mut self,
    ) -> impl std::future::Future<Output = Result<Self::Stream, TransportError>> {
        async { Err(TransportError::Refused("always refuse".into())) }
    }
}

/// **INV-1 正控 transport**:connect 一旦被呼叫即 panic（證 production stub 拒後 factory 從不被觸）。
struct PanicOnConnectTransport;

impl TransportFactory for PanicOnConnectTransport {
    type Stream = DuplexStream;
    fn connect(
        &mut self,
    ) -> impl std::future::Future<Output = Result<Self::Stream, TransportError>> {
        async { panic!("INV-1 違反:production stub 拒後 factory.connect 不應被呼叫") }
    }
}

fn driver_config() -> TwsSessionConfig {
    TwsSessionConfig::default()
}

fn timeouts() -> TimeoutPolicy {
    TimeoutPolicy::default()
}

fn reader_limits() -> FrameReaderLimits {
    FrameReaderLimits {
        window_ms: 1000,
        max_frames_per_window: 10_000,
        max_bytes_per_window: 10_000_000,
    }
}

/// 建 fake driver（granting provider + OneShotTransport(場景),回 driver + FakeHandle 供檢視送出）。
fn fake_driver(
    scn: Scenario,
) -> (
    SessionDriver<GrantingProvider, OneShotTransport>,
    openclaw_fake_tws::FakeHandle,
) {
    let (client, handle) = scn.spawn();
    let driver = SessionDriver::new(
        GrantingProvider,
        OneShotTransport {
            stream: Some(client),
        },
        driver_config(),
        timeouts(),
        reader_limits(),
    );
    (driver, handle)
}

// ===========================================================================
// INV-1:production stub 恆拒 → 停 Disconnected,factory 從不呼叫
// ===========================================================================

#[tokio::test]
async fn inv1_production_stub_denies_and_factory_never_called() {
    // 具體 EnvelopeRequiredStub（production 唯一 provider）+ panic-on-connect transport。
    let mut driver = SessionDriver::new(
        EnvelopeRequiredStub,
        PanicOnConnectTransport,
        driver_config(),
        timeouts(),
        reader_limits(),
    );
    let mut clock = TestClock::at(1000);
    // 反覆嘗試:恆 Denied,停 Disconnected(EnvelopeRequired);factory.connect 從不被呼叫（否則 panic）。
    for _ in 0..3 {
        assert_eq!(
            driver.run_connect_cycle(&mut clock).await,
            CycleOutcome::Denied
        );
        assert!(matches!(
            driver.state(),
            SessionState::Disconnected {
                reason: HaltReason::EnvelopeRequired
            }
        ));
    }
}

// ===========================================================================
// 端到端 happy:握手到 Ready + serve + F4 送出證明
// ===========================================================================

#[tokio::test]
async fn e2e_happy_handshake_reaches_ready() {
    let (mut driver, _h) = fake_driver(scenarios::happy_session());
    // connect_and_handshake 單獨走（不進 serve）→ Ready。
    let step = driver.connect_and_handshake(0).await;
    assert_eq!(step, ConnectStep::Ready);
    assert!(matches!(driver.state(), SessionState::Ready(_)));
}

#[tokio::test]
async fn e2e_happy_full_cycle_serves_then_eof_backoff() {
    let (mut driver, handle) = fake_driver(scenarios::happy_session());
    let mut clock = TestClock::at(0);
    // 握手到 Ready → serve 讀完握手序列後腳本耗盡 → client EOF → IoDropped。
    let outcome = driver.run_connect_cycle(&mut clock).await;
    assert_eq!(outcome, CycleOutcome::Served(ServeEnd::IoDropped));
    assert!(matches!(driver.state(), SessionState::Backoff { .. }));
    // **F4 送出證明**:driver 送出的訊息 frame 含 START_API(71) + reqCurrentTime(49)——二者皆過
    // governor grant + send_framed（無 grant 無法送 → 編譯期必經 governor）。
    let frames = handle.received_message_frames().await;
    let ids: Vec<String> = frames.iter().map(|f| frame_fields(f)[0].clone()).collect();
    assert!(
        ids.contains(&"71".to_string()),
        "應送 START_API(71): {ids:?}"
    );
    assert!(
        ids.contains(&"49".to_string()),
        "應送 reqCurrentTime(49): {ids:?}"
    );
}

// ===========================================================================
// F4:send_framed by-value 消費 governor 鑄的 grant（單一出口牙齒咬合）
// ===========================================================================

#[tokio::test]
async fn f4_send_framed_consumes_governor_grant() {
    // grant 唯 governor（control_grant）鑄 → send_framed by-value 消費 → frame 送達。
    let mut mgr = TwsSessionManager::new(driver_config());
    let grant = mgr.control_grant(0).expect("滿桶應放行 grant");
    let (mut client, mut server) = tokio::io::duplex(1024);
    let frame = crate::ibkr_tws_wire::encode_req_current_time();
    send_framed(&mut client, grant, &frame, timeouts().io)
        .await
        .unwrap();
    drop(client);
    let mut got = Vec::new();
    server.read_to_end(&mut got).await.unwrap();
    assert_eq!(got, frame);
    // 編譯期牙齒:grant 已 by-value 消費（move),無法復用——`OutboundGrant` 非 Clone/非 Copy。
    // 取消下行註解則編譯失敗（use of moved value），證「無 grant 不能送」:
    // send_framed(&mut client, grant, &frame, timeouts().io).await.unwrap();
}

// ===========================================================================
// 握手段故障注入
// ===========================================================================

#[tokio::test]
async fn fault_version_too_old_is_handshake_fatal() {
    let (mut driver, _h) = fake_driver(scenarios::version_too_old());
    let mut clock = TestClock::at(0);
    assert_eq!(
        driver.run_connect_cycle(&mut clock).await,
        CycleOutcome::HandshakeFatal
    );
    assert!(matches!(
        driver.state(),
        SessionState::Disconnected {
            reason: HaltReason::SessionFatal(FatalCause::ServerVersionTooOld)
        }
    ));
}

#[tokio::test]
async fn fault_duplicate_client_id_is_handshake_fatal() {
    let (mut driver, _h) = fake_driver(scenarios::kick_duplicate_client());
    let mut clock = TestClock::at(0);
    assert_eq!(
        driver.run_connect_cycle(&mut clock).await,
        CycleOutcome::HandshakeFatal
    );
    assert!(matches!(
        driver.state(),
        SessionState::Disconnected {
            reason: HaltReason::SessionFatal(FatalCause::DuplicateClientIdRejected)
        }
    ));
}

#[tokio::test]
async fn fault_non_paper_session_is_handshake_fatal() {
    let (mut driver, _h) = fake_driver(scenarios::non_paper_session());
    let mut clock = TestClock::at(0);
    assert_eq!(
        driver.run_connect_cycle(&mut clock).await,
        CycleOutcome::HandshakeFatal
    );
    assert!(matches!(
        driver.state(),
        SessionState::Disconnected {
            reason: HaltReason::SessionFatal(FatalCause::NonPaperSession)
        }
    ));
}

#[tokio::test]
async fn fault_handshake_gateway_error_is_fatal() {
    let (mut driver, _h) = fake_driver(scenarios::handshake_gateway_error());
    let mut clock = TestClock::at(0);
    assert_eq!(
        driver.run_connect_cycle(&mut clock).await,
        CycleOutcome::HandshakeFatal
    );
    assert!(matches!(
        driver.state(),
        SessionState::Disconnected {
            reason: HaltReason::SessionFatal(FatalCause::GatewayError(502))
        }
    ));
}

#[tokio::test]
async fn fault_reordered_handshake_is_transient() {
    // 49 早於 15 → 未實檢 paper 即到 49 → fail-closed transient（可重試,不 fail-open）。
    let (mut driver, _h) = fake_driver(scenarios::reordered_handshake());
    let mut clock = TestClock::at(0);
    assert_eq!(
        driver.run_connect_cycle(&mut clock).await,
        CycleOutcome::HandshakeTransient
    );
    assert!(matches!(driver.state(), SessionState::Backoff { .. }));
}

#[tokio::test]
async fn fault_half_message_disconnect_is_transient() {
    // ACK 後半個 frame + 突然關閉 → codec 不成完整 frame + EOF → transient Backoff。
    let (mut driver, _h) = fake_driver(scenarios::half_message_disconnect());
    let mut clock = TestClock::at(0);
    assert_eq!(
        driver.run_connect_cycle(&mut clock).await,
        CycleOutcome::HandshakeTransient
    );
    assert!(matches!(driver.state(), SessionState::Backoff { .. }));
}

#[tokio::test]
async fn fault_connect_refused_is_connect_failed() {
    let mut driver = SessionDriver::new(
        GrantingProvider,
        RefusingTransport,
        driver_config(),
        timeouts(),
        reader_limits(),
    );
    let mut clock = TestClock::at(0);
    assert_eq!(
        driver.run_connect_cycle(&mut clock).await,
        CycleOutcome::ConnectFailed
    );
    assert!(matches!(driver.state(), SessionState::Backoff { .. }));
}

// ===========================================================================
// serve 段故障注入
// ===========================================================================

#[tokio::test]
async fn serve_mid_stream_disconnect_is_io_dropped() {
    let (mut driver, _h) = fake_driver(scenarios::mid_stream_disconnect());
    let mut clock = TestClock::at(0);
    assert_eq!(
        driver.run_connect_cycle(&mut clock).await,
        CycleOutcome::Served(ServeEnd::IoDropped)
    );
    assert!(matches!(driver.state(), SessionState::Backoff { .. }));
}

#[tokio::test]
async fn serve_fatal_error_frame_drops_session() {
    // serve 期 504（未連線,SessionFatal）→ 斷 session。
    let (mut driver, _h) = fake_driver(scenarios::serve_fatal_error());
    let mut clock = TestClock::at(0);
    assert_eq!(
        driver.run_connect_cycle(&mut clock).await,
        CycleOutcome::Served(ServeEnd::SessionFatal)
    );
    assert!(matches!(
        driver.state(),
        SessionState::Disconnected {
            reason: HaltReason::SessionFatal(FatalCause::GatewayError(504))
        }
    ));
}

#[tokio::test]
async fn serve_pacing_three_strikes_drops_session() {
    // serve 期連續三則 error-100 → governor strike 三振 → SessionFatal(GatewayError(100))。
    let (mut driver, _h) = fake_driver(scenarios::pacing_violation());
    let mut clock = TestClock::at(0);
    assert_eq!(
        driver.run_connect_cycle(&mut clock).await,
        CycleOutcome::Served(ServeEnd::SessionFatal)
    );
    assert_eq!(driver.manager().pacing_observation().ib_pacing_strikes, 3);
}

#[tokio::test]
async fn serve_farm_blip_transient_no_early_reconnect() {
    // N2:serve 期 2103 farm-blip（Transient）**不觸過早 reconnect**——續 serve。判別力:2103 後接一則
    // 心跳回覆（currentTime,證仍 Ready 讀取）再接 504 fatal。若 2103 誤觸 Backoff/早退,driver 會在
    // 2103 即離開 serve → 永不讀到 504 → 結果為 IoDropped;唯有 2103 被容忍、續 serve 才會讀到 504 →
    // Served(SessionFatal(GatewayError(504)))。此結果**唯一**證明 2103 未早退 + reply-after-blip 被處理。
    let mut frames = happy_handshake_frames();
    frames.push(err_msg(2103, "A market data farm connection has been lost"));
    frames.push(current_time(1_700_000_030)); // 心跳回覆:證 2103 後仍 Ready 讀取
    frames.push(err_msg(504, "Not connected")); // fatal:唯續 serve 才讀得到
    let scn = Scenario::new(vec![FakeStep::Send(frames)]);
    let (mut driver, _h) = fake_driver(scn);
    let mut clock = TestClock::at(0);
    assert_eq!(
        driver.run_connect_cycle(&mut clock).await,
        CycleOutcome::Served(ServeEnd::SessionFatal),
        "2103 應被容忍、續 serve 直到讀到 504（誤早退則為 IoDropped）"
    );
    assert!(matches!(
        driver.state(),
        SessionState::Disconnected {
            reason: HaltReason::SessionFatal(FatalCause::GatewayError(504))
        }
    ));
}

#[tokio::test]
async fn serve_duplicate_current_time_tolerated() {
    // serve 期重複 currentTime → 容忍（spurious 心跳回覆,不斷 session）→ EOF → IoDropped。
    let (mut driver, _h) = fake_driver(scenarios::serve_duplicate_current_time());
    let mut clock = TestClock::at(0);
    assert_eq!(
        driver.run_connect_cycle(&mut clock).await,
        CycleOutcome::Served(ServeEnd::IoDropped)
    );
}

#[tokio::test]
async fn serve_unknown_msg_id_fail_closed() {
    // serve 期未知 msgId(8) → fail-closed 斷線 → Backoff（IoDropped）。
    let (mut driver, _h) = fake_driver(scenarios::serve_unknown_msg_id());
    let mut clock = TestClock::at(0);
    assert_eq!(
        driver.run_connect_cycle(&mut clock).await,
        CycleOutcome::Served(ServeEnd::IoDropped)
    );
    assert!(matches!(driver.state(), SessionState::Backoff { .. }));
}

// ===========================================================================
// 心跳:serve 期到期送 reqCurrentTime（過 governor 單一出口）+ 回覆處理
// ===========================================================================

#[tokio::test]
async fn serve_sends_heartbeat_when_due_and_processes_reply() {
    let (mut driver, handle) = fake_driver(scenarios::happy_with_one_heartbeat_reply());
    // 握手 at now=0 → Ready,心跳 due=30_000。
    assert_eq!(driver.connect_and_handshake(0).await, ConnectStep::Ready);
    // serve at now=30_000 → 心跳到期送 reqCurrentTime,讀預載 currentTime 回覆（miss 歸零）。
    let mut clock = TestClock::at(30_000);
    let end = driver.serve(&mut clock).await;
    assert_eq!(end, ServeEnd::IoDropped); // 回覆後腳本耗盡 → EOF
                                          // 送出的訊息 frame:START_API + 握手 reqCurrentTime + **心跳 reqCurrentTime** = 兩個 49。
    let frames = handle.received_message_frames().await;
    let n_req_time = frames
        .iter()
        .filter(|f| frame_fields(f).first().map(|s| s.as_str()) == Some("49"))
        .count();
    assert_eq!(
        n_req_time, 2,
        "應送 1 握手 + 1 心跳 reqCurrentTime: {n_req_time}"
    );
}

// ===========================================================================
// F-1（E2-F1）:serve 期「時間推進」兩分支的整合覆蓋（advanceable 注入時鐘 + SilentDrop）
// ===========================================================================

/// **分支①:silent server → 心跳 overdue → miss → Degraded → 續 miss → HeartbeatDropped**。
/// 極短 `serve_poll`(1ms 真 poll,免 tokio test-util/start_paused):server 靜默 keep-open → 每次讀
/// poll 逾時回 Idle（非 EOF）令迴圈快速推進;`AdvancingClock` 每迭代推進注入時鐘 10s → 逐步越過
/// heartbeat interval(30s)/timeout(10s),累積 4 miss（degraded_after=2,drop_after=4）。斷言 `Degraded`
/// 真被抵達 + `HeartbeatDropped` 真被產生。
#[tokio::test]
async fn serve_silent_server_degrades_then_heartbeat_dropped() {
    let (mut driver, _h) = fake_driver(scenarios::silent_after_handshake());
    driver.set_serve_poll(std::time::Duration::from_millis(1)); // 靜默 tick 極短 → 迭代快
                                                                // 握手 at now=0 → Ready,心跳 due=30_000。
    assert_eq!(driver.connect_and_handshake(0).await, ConnectStep::Ready);
    // serve:注入時鐘每迭代 +10s;server 靜默 keep-open → 讀恆 Idle poll tick（非 EOF）→ 心跳 liveness
    // 判斷:send→無回覆→overdue→miss ×4 → Degraded(≥2) 續 drop(≥4)。
    let mut clock = AdvancingClock::new(10_000, 10_000);
    let end = driver.serve(&mut clock).await;
    // **HeartbeatDropped 真被產生**（靜默 server 由心跳 miss 判斷 liveness,非讀逾時誤判 io_drop）。
    assert_eq!(end, ServeEnd::HeartbeatDropped);
    // **Degraded 真被抵達**（drop_after=4 > degraded_after=2 → 必先經 Degraded）。
    assert!(
        driver.observed_degraded(),
        "心跳 miss 路徑應真經 Degraded（劣化）再 drop"
    );
    // drop 後 → Backoff（transient，消耗 reconnect budget）。
    assert!(matches!(driver.state(), SessionState::Backoff { .. }));
}

/// **分支②:queued-heartbeat → resolve_pacing → HeartbeatReady → send_framed**（driver serve 分派）。
/// 以 `manager_mut` 預先耗盡 bucket + 手動提交心跳令其 Queued（pending 記於 manager）,serve 於 100ms
/// 後（<queue_timeout 500ms）refill 1 token → `resolve_pacing` 放行 → driver send_framed 送出心跳
/// reqCurrentTime。斷言 fake 真收到 resolve 放行的心跳 frame（分派分支被執行）。
#[tokio::test]
async fn serve_queued_heartbeat_resolves_and_sends() {
    // pacing lines=20（rate=10;capacity 10 ≥ 握手 2 control;100ms/token < 500ms queue_timeout）。
    let (client, handle) = scenarios::happy_with_one_heartbeat_reply().spawn();
    let mut driver = SessionDriver::new_with_pacing(
        GrantingProvider,
        OneShotTransport {
            stream: Some(client),
        },
        driver_config(),
        queueable_pacing(),
        timeouts(),
        reader_limits(),
    );
    // 握手 at now=0 → Ready（消 2 control token）。
    assert_eq!(driver.connect_and_handshake(0).await, ConnectStep::Ready);
    // 於 now=30_000（心跳到期）:耗盡 bucket + 手動提交心跳 → Queued（pending 記於 manager）。
    {
        let mgr = driver.manager_mut();
        for _ in 0..10 {
            let _ = mgr.governor_mut().submit(OutboundClass::MarketData, 30_000);
        }
        assert!(
            matches!(mgr.heartbeat_outbound(30_000), HeartbeatOutbound::Queued(_)),
            "耗盡 bucket 後心跳應被 Queued"
        );
    }
    // serve:注入時鐘 30_000 起每迭代 +100ms → iter2 補 1 token → resolve_pacing 放行 → send_framed。
    let mut clock = AdvancingClock::new(30_000, 100);
    let end = driver.serve(&mut clock).await;
    assert_eq!(end, ServeEnd::IoDropped); // 送出後腳本耗盡 → EOF
                                          // 送出的訊息:START_API + 握手 reqCurrentTime + **resolve 放行的心跳 reqCurrentTime** = 2 個 49。
    let frames = handle.received_message_frames().await;
    let n_req_time = frames
        .iter()
        .filter(|f| frame_fields(f).first().map(|s| s.as_str()) == Some("49"))
        .count();
    assert_eq!(
        n_req_time, 2,
        "resolve_pacing→send_framed 應送出佇列後放行的心跳: {n_req_time}"
    );
}

// ===========================================================================
// 重連對賬:io drop → Backoff → 退避未到期(BackingOff) → 到期重連 → 再 Ready
// ===========================================================================

#[tokio::test]
async fn reconnect_after_io_drop_backoff_then_reconnects() {
    // 場景1=握手到 Ready 後 mid-stream 斷;場景2=happy（重連目標）。
    let mut scns = VecDeque::new();
    scns.push_back(scenarios::mid_stream_disconnect());
    scns.push_back(scenarios::happy_session());
    let mut driver = SessionDriver::new(
        GrantingProvider,
        ScriptedTransport { scenarios: scns },
        driver_config(),
        timeouts(),
        reader_limits(),
    );
    let mut clock = TestClock::at(0);
    // cycle1:Ready → mid-stream 斷 → IoDropped → Backoff(attempt 1)。
    assert_eq!(
        driver.run_connect_cycle(&mut clock).await,
        CycleOutcome::Served(ServeEnd::IoDropped)
    );
    let (entered, delay_ms) = match driver.state() {
        SessionState::Backoff {
            entered_at_ms,
            next_delay,
            ..
        } => (*entered_at_ms, next_delay.as_millis() as u64),
        s => panic!("expected Backoff, got {s:?}"),
    };
    // 退避未到期 → BackingOff（僅 delay>0 時可確定性驗;full-jitter 偶回 0 則跳過此子斷言）。
    if delay_ms > 0 {
        clock.set(entered + delay_ms / 2);
        assert_eq!(
            driver.run_connect_cycle(&mut clock).await,
            CycleOutcome::BackingOff
        );
    }
    // 推進過 delay → 到期 → cycle 重連場景2 → 再 Ready → serve 至 EOF → IoDropped。
    clock.set(entered + delay_ms + 1);
    assert_eq!(
        driver.run_connect_cycle(&mut clock).await,
        CycleOutcome::Served(ServeEnd::IoDropped),
        "退避到期後應重連並再度 serve"
    );
}

// ===========================================================================
// W5-S2:account/positions 消化端到端（訂閱 pump 經 governor 單一出口 + 入站消化 + 斷線失效）
// ===========================================================================

#[tokio::test]
async fn w5_account_data_end_to_end_digests_and_marks_disconnect() {
    use crate::ibkr_tws_account_data::SnapshotStaleness;
    use openclaw_types::IbkrAccountSummaryTagV1;

    let (mut driver, handle) = fake_driver(scenarios::account_data_session(ACCOUNT_SUMMARY_REQ_ID));
    driver.enable_account_data_subscriptions();
    let mut clock = TestClock::at(1_000);
    // 全 cycle:Ready → 首 serve tick 送訂閱(經 governor AccountData 類)→ 消化全量+End+增量
    // → 腳本盡 EOF → IoDropped。
    assert_eq!(
        driver.run_connect_cycle(&mut clock).await,
        CycleOutcome::Served(ServeEnd::IoDropped)
    );
    // 出站證明:reqAccountSummary(OUT 62,group=All+9 tag)與 reqPositions(OUT 61)真被送出
    //（皆過 send_framed=grant 消費,單一出口編譯期強制)。
    let frames = handle.received_message_frames().await;
    let ids: Vec<String> = frames.iter().map(|f| frame_fields(f)[0].clone()).collect();
    assert!(
        ids.contains(&"62".to_string()),
        "應送 reqAccountSummary(62): {ids:?}"
    );
    assert!(
        ids.contains(&"61".to_string()),
        "應送 reqPositions(61): {ids:?}"
    );
    let req_summary = frames
        .iter()
        .map(|f| frame_fields(f))
        .find(|f| f[0] == "62")
        .unwrap();
    assert_eq!(req_summary[3], "All", "group 必為 All");
    assert_eq!(
        req_summary[4].split(',').count(),
        9,
        "tags=白名單 9 值單欄逗號"
    );
    // 消化證明:summary 2 tag(增量覆蓋 BuyingPower=48000)+ 1 倉位。
    let digest = driver.account_data();
    assert_eq!(digest.summary_rows().count(), 2);
    let bp = digest
        .summary_rows()
        .find(|r| r.tag == IbkrAccountSummaryTagV1::BuyingPower)
        .unwrap();
    assert_eq!(bp.value_decimal, "48000", "節拍增量應覆蓋首回全量值");
    let pos = digest.positions_rows().next().unwrap();
    assert_eq!((pos.con_id, pos.position_decimal.as_str()), (756733, "100"));
    // 斷線失效:serve 結束(EOF)→ 快照標 DisconnectedStale(重連需重訂閱)。
    assert_eq!(
        digest.summary_staleness(0),
        SnapshotStaleness::DisconnectedStale
    );
    assert_eq!(
        digest.positions_staleness(0),
        SnapshotStaleness::DisconnectedStale
    );
}

#[tokio::test]
async fn w5_off_whitelist_tag_invalidates_snapshot_but_session_survives() {
    use crate::ibkr_tws_account_data::SnapshotStaleness;

    // 表外 tag → 契約 UnknownDenied blocker:快照 Invalidated,session 不因此斷(EOF 才斷)。
    let (mut driver, _h) = fake_driver(scenarios::account_summary_off_whitelist_tag(
        ACCOUNT_SUMMARY_REQ_ID,
    ));
    driver.enable_account_data_subscriptions();
    let mut clock = TestClock::at(1_000);
    assert_eq!(
        driver.run_connect_cycle(&mut clock).await,
        CycleOutcome::Served(ServeEnd::IoDropped),
        "表外 tag 是資料層 reject,非 wire 損壞——session 應活到腳本 EOF"
    );
    // 斷線標記只覆蓋活躍相位;Invalidated 保留(毒化事實不被斷線沖淡)。
    assert_eq!(
        driver.account_data().summary_staleness(0),
        SnapshotStaleness::Invalidated
    );
    assert_eq!(driver.account_data().summary_rows().count(), 0);
}

#[tokio::test]
async fn w5_position_version_too_old_rejected_session_survives() {
    // G1:v2 position 行(無 avgCost)→ typed 拒不捏值;positionEnd 仍消化(訂閱 Live 空快照)。
    let (mut driver, _h) = fake_driver(scenarios::position_version_too_old());
    driver.enable_account_data_subscriptions();
    let mut clock = TestClock::at(1_000);
    assert_eq!(
        driver.run_connect_cycle(&mut clock).await,
        CycleOutcome::Served(ServeEnd::IoDropped)
    );
    assert_eq!(
        driver.account_data().positions_rows().count(),
        0,
        "v<3 行不得以 avgCost=0 捏值併入"
    );
}

#[tokio::test]
async fn w5_malformed_summary_frame_fail_closed_disconnects() {
    // reqId 非數字 → WireMalformed → driver 既有紀律 fail-closed 斷線(Backoff)。
    let (mut driver, _h) =
        fake_driver(scenarios::account_summary_malformed(ACCOUNT_SUMMARY_REQ_ID));
    driver.enable_account_data_subscriptions();
    let mut clock = TestClock::at(1_000);
    assert_eq!(
        driver.run_connect_cycle(&mut clock).await,
        CycleOutcome::Served(ServeEnd::IoDropped)
    );
    assert!(matches!(driver.state(), SessionState::Backoff { .. }));
}

#[tokio::test]
async fn w5_pump_disabled_by_default_no_subscription_sent() {
    // 默認 off:不開 pump → 不送 61/62;入站 account 資料因未訂而收=typed 拒,不併入。
    let (mut driver, handle) = fake_driver(scenarios::account_data_session(ACCOUNT_SUMMARY_REQ_ID));
    let mut clock = TestClock::at(1_000);
    assert_eq!(
        driver.run_connect_cycle(&mut clock).await,
        CycleOutcome::Served(ServeEnd::IoDropped)
    );
    let frames = handle.received_message_frames().await;
    let ids: Vec<String> = frames.iter().map(|f| frame_fields(f)[0].clone()).collect();
    assert!(
        !ids.contains(&"62".to_string()),
        "pump off 不得送 reqAccountSummary"
    );
    assert!(
        !ids.contains(&"61".to_string()),
        "pump off 不得送 reqPositions"
    );
    assert_eq!(driver.account_data().summary_rows().count(), 0);
    assert_eq!(driver.account_data().positions_rows().count(), 0);
}

// ===========================================================================
// 終態:結構性終態後 cycle no-op（Terminal;factory 不被觸）
// ===========================================================================

#[tokio::test]
async fn terminal_state_cycle_is_noop() {
    // version_too_old → SessionFatal（終態）;其後 cycle → Terminal（OneShot 已耗盡也不會被呼叫）。
    let (mut driver, _h) = fake_driver(scenarios::version_too_old());
    let mut clock = TestClock::at(0);
    assert_eq!(
        driver.run_connect_cycle(&mut clock).await,
        CycleOutcome::HandshakeFatal
    );
    assert!(driver.manager().is_terminal());
    assert_eq!(
        driver.run_connect_cycle(&mut clock).await,
        CycleOutcome::Terminal
    );
}
