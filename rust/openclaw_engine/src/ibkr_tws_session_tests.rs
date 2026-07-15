//! W3-S2 session FSM 測試（拆檔;`ibkr_tws_session.rs` 逼近拆檔守衛,測試獨立檔）。
//! 全注入時鐘（`now_ms` / 凍結 UTC）+ 注入 RNG;零 socket / 零 gateway / 零 wall-clock。
//! fixture 禁硬編日期 time-bomb:排程 DST 測試以 chrono-tz 由凍結 UTC/ET 構造,並自檢 weekday。

use super::*;
use chrono::TimeZone;

use openclaw_types::ibkr_tws_session_state::{
    IB_ERR_COULD_NOT_CONNECT_TWS, IB_ERR_DUPLICATE_CLIENT_ID, IB_ERR_MKT_DATA_FARM_LOST,
    IB_ERR_TWS_SERVER_CONNECTIVITY_BROKEN,
};

// ---------------------------------------------------------------------------
// 測試輔助
// ---------------------------------------------------------------------------

/// 確定性 full-jitter RNG:回佇列值 clamp 至 `[0, upper]`,序列走完循環（測試可預測 delay）。
struct SeqRng {
    seq: Vec<u64>,
    idx: usize,
}

impl SeqRng {
    fn new(seq: Vec<u64>) -> Self {
        Self { seq, idx: 0 }
    }
}

impl FullJitterRng for SeqRng {
    fn jitter_upto(&mut self, upper_inclusive: u64) -> u64 {
        let v = self.seq[self.idx % self.seq.len()];
        self.idx += 1;
        v.min(upper_inclusive)
    }
}

/// 放行 provider（**test-only**;production 域不存在此型別 → INV-1 靜態守衛正控:若此型別被接進
/// production connect 路徑,守衛 FAIL）。每次 check() 鑄新 token 並計數（證明 no-cache）。
struct GrantingProvider {
    checks: u32,
}

impl GrantingProvider {
    fn new() -> Self {
        Self { checks: 0 }
    }
}

impl ConnectPermitProvider for GrantingProvider {
    fn check(&mut self) -> Result<PermitToken, ConnectDenied> {
        self.checks += 1;
        Ok(PermitToken::mint())
    }
}

fn cfg() -> TwsSessionConfig {
    TwsSessionConfig::default()
}

fn happy_outcome() -> HandshakeOutcome {
    HandshakeOutcome {
        server_version: 176,
        connection_time_raw: "20260715 09:30:00 EST".to_string(),
        paper_confirmed: true,
        next_valid_id: 42,
    }
}

/// 驅動 FSM 至 Ready（permit→connecting→established→handshaking→ready）。
fn drive_to_ready(fsm: &mut SessionFsm, now_ms: u64) {
    fsm.on_permit_granted(PermitToken::mint(), now_ms);
    fsm.on_transport_established(now_ms);
    fsm.on_handshake_result(happy_outcome(), now_ms);
    assert!(matches!(fsm.state(), SessionState::Ready(_)));
}

// ---------------------------------------------------------------------------
// INV-1 permit（本包最高不變量）
// ---------------------------------------------------------------------------

#[test]
fn stub_permit_always_denies_repeatedly() {
    let mut stub = EnvelopeRequiredStub;
    for _ in 0..5 {
        // 用 matches!（非 unwrap_err）:PermitToken 刻意不 derive Debug,維持單次消費 token 最小面。
        assert!(matches!(stub.check(), Err(ConnectDenied::EnvelopeRequired)));
    }
}

#[test]
fn permit_token_single_use_moved_into_connect() {
    // token 由 mint 構造,move 進 on_permit_granted 消費（非 Clone → 無法復用;編譯期保證）。
    let mut fsm = SessionFsm::new(cfg());
    let token = PermitToken::mint();
    let ev = fsm.on_permit_granted(token, 0);
    // token 已 move,此後不可再用（若取消註解下行則編譯失敗——非 Clone 的結構性單次消費）:
    // let _reuse = token;
    assert_eq!(ev, vec![IbkrTwsSessionEventV1::ConnectPermitGranted]);
    assert!(matches!(fsm.state(), SessionState::Connecting));
}

#[test]
fn production_manager_connect_always_envelope_required() {
    // production manager 持具體 EnvelopeRequiredStub → 恆撞 EnvelopeRequired 停 Disconnected。
    let mut mgr = TwsSessionManager::new(cfg());
    for _ in 0..3 {
        let ev = mgr.attempt_connect(1000);
        assert_eq!(ev, vec![IbkrTwsSessionEventV1::EnvelopeRequired]);
        assert!(matches!(
            mgr.state(),
            SessionState::Disconnected {
                reason: HaltReason::EnvelopeRequired
            }
        ));
    }
    assert_eq!(mgr.ipc_state(), IbkrTwsSessionStateV1::Disconnected);
}

#[test]
fn manager_transient_backoff_delay_within_bounds() {
    // manager 的 full-jitter delay（EntropyJitterRng;attempt=1,ceiling=min(cap,base*2)=2000ms）
    // 恆落 [0, ceiling]，證明 backoff plumbing 生效且被 cap 夾（非確定性 RNG,只驗上界）。
    let mut mgr = TwsSessionManager::new(cfg());
    for _ in 0..64 {
        let d = mgr.next_transient_backoff_delay();
        assert!(d <= Duration::from_millis(2000), "delay {d:?} 超 ceiling");
        assert!(d <= cfg().backoff_cap);
    }
}

#[test]
fn manager_attempt_connect_is_noop_in_terminal_state() {
    // 硬化 terminal 前置（E2-F1）:終態 attempt_connect 直接 no-op,不觸 FSM 非法轉移 debug_assert。
    let mut mgr = TwsSessionManager::new(cfg());
    mgr.halt(); // → Disconnected(Halted) 終態
    assert_eq!(mgr.ipc_state(), IbkrTwsSessionStateV1::Disconnected);
    let ev = mgr.attempt_connect(1000);
    assert!(ev.is_empty(), "終態 attempt_connect 應 no-op");
    assert!(matches!(
        mgr.state(),
        SessionState::Disconnected {
            reason: HaltReason::Halted
        }
    ));
}

#[test]
fn granting_provider_new_token_each_reconnect_cycle_no_cache() {
    // 用 test-only 放行 provider 走完一輪重連,證明每次 Backoff→Connecting 都重新 check()（禁緩存）。
    let mut fsm = SessionFsm::new(cfg());
    let mut provider = GrantingProvider::new();

    // 第 1 輪:Disconnected → check() #1 → Connecting → Ready。
    let t1 = provider.check().unwrap();
    fsm.on_permit_granted(t1, 0);
    fsm.on_transport_established(0);
    fsm.on_handshake_result(happy_outcome(), 0);
    assert_eq!(provider.checks, 1);

    // 斷線 → Backoff → 到期。
    fsm.on_io_drop(100, Duration::from_millis(50));
    assert!(matches!(fsm.state(), SessionState::Backoff { .. }));
    assert!(fsm.backoff_elapsed(200));

    // 第 2 輪:必須重新 check()（#2）取新 token — 舊 token 早被 move 消費,結構上無從緩存。
    let t2 = provider.check().unwrap();
    fsm.on_permit_granted(t2, 200);
    assert_eq!(provider.checks, 2);
    assert!(matches!(fsm.state(), SessionState::Connecting));
}

// ---------------------------------------------------------------------------
// FSM 轉移表（設計 §1.2）
// ---------------------------------------------------------------------------

#[test]
fn disconnected_permit_granted_to_connecting() {
    let mut fsm = SessionFsm::new(cfg());
    let ev = fsm.on_permit_granted(PermitToken::mint(), 0);
    assert_eq!(ev, vec![IbkrTwsSessionEventV1::ConnectPermitGranted]);
    assert!(matches!(fsm.state(), SessionState::Connecting));
}

#[test]
fn disconnected_permit_denied_stays_disconnected() {
    let mut fsm = SessionFsm::new(cfg());
    let ev = fsm.on_permit_denied();
    assert_eq!(ev, vec![IbkrTwsSessionEventV1::EnvelopeRequired]);
    assert!(matches!(
        fsm.state(),
        SessionState::Disconnected {
            reason: HaltReason::EnvelopeRequired
        }
    ));
}

#[test]
fn connecting_transport_established_to_handshaking() {
    let mut fsm = SessionFsm::new(cfg());
    fsm.on_permit_granted(PermitToken::mint(), 0);
    let ev = fsm.on_transport_established(0);
    assert!(ev.is_empty());
    assert!(matches!(fsm.state(), SessionState::Handshaking));
}

#[test]
fn connecting_failed_to_backoff() {
    let mut fsm = SessionFsm::new(cfg());
    fsm.on_permit_granted(PermitToken::mint(), 0);
    fsm.on_connect_failed(0, Duration::from_secs(1));
    match fsm.state() {
        SessionState::Backoff {
            attempt_n,
            scheduled,
            ..
        } => {
            assert_eq!(*attempt_n, 1);
            assert!(!scheduled);
        }
        s => panic!("expected Backoff, got {s:?}"),
    }
}

#[test]
fn handshaking_ok_to_ready() {
    let mut fsm = SessionFsm::new(cfg());
    fsm.on_permit_granted(PermitToken::mint(), 0);
    fsm.on_transport_established(0);
    let ev = fsm.on_handshake_result(happy_outcome(), 1000);
    assert!(ev.is_empty());
    match fsm.state() {
        SessionState::Ready(rs) => {
            assert_eq!(rs.server_version, 176);
            assert!(rs.paper_confirmed);
            assert_eq!(rs.next_valid_id, 42);
            assert_eq!(rs.consecutive_misses, 0);
        }
        s => panic!("expected Ready, got {s:?}"),
    }
}

#[test]
fn handshaking_version_too_old_is_session_fatal() {
    let mut fsm = SessionFsm::new(cfg());
    fsm.on_permit_granted(PermitToken::mint(), 0);
    fsm.on_transport_established(0);
    let mut outcome = happy_outcome();
    outcome.server_version = PINNED_MIN_SERVER_VERSION - 1;
    let ev = fsm.on_handshake_result(outcome, 0);
    assert_eq!(ev, vec![IbkrTwsSessionEventV1::ServerVersionTooOld]);
    assert!(matches!(
        fsm.state(),
        SessionState::Disconnected {
            reason: HaltReason::SessionFatal(FatalCause::ServerVersionTooOld)
        }
    ));
}

#[test]
fn handshaking_non_paper_is_session_fatal() {
    let mut fsm = SessionFsm::new(cfg());
    fsm.on_permit_granted(PermitToken::mint(), 0);
    fsm.on_transport_established(0);
    let mut outcome = happy_outcome();
    outcome.paper_confirmed = false;
    let ev = fsm.on_handshake_result(outcome, 0);
    assert_eq!(ev, vec![IbkrTwsSessionEventV1::NonPaperSessionDetected]);
    assert!(matches!(
        fsm.state(),
        SessionState::Disconnected {
            reason: HaltReason::SessionFatal(FatalCause::NonPaperSession)
        }
    ));
}

#[test]
fn handshaking_transient_error_to_backoff() {
    let mut fsm = SessionFsm::new(cfg());
    fsm.on_permit_granted(PermitToken::mint(), 0);
    fsm.on_transport_established(0);
    fsm.on_handshake_transient(0, Duration::from_secs(1));
    assert!(matches!(
        fsm.state(),
        SessionState::Backoff { attempt_n: 1, .. }
    ));
}

#[test]
fn handshaking_fatal_gateway_error() {
    let mut fsm = SessionFsm::new(cfg());
    fsm.on_permit_granted(PermitToken::mint(), 0);
    fsm.on_transport_established(0);
    let ev = fsm.on_handshake_fatal(FatalCause::GatewayError(IB_ERR_COULD_NOT_CONNECT_TWS), 0);
    // GatewayError 無專屬 IPC 事件（以 halt_reason 承載）。
    assert!(ev.is_empty());
    assert!(matches!(
        fsm.state(),
        SessionState::Disconnected {
            reason: HaltReason::SessionFatal(FatalCause::GatewayError(502))
        }
    ));
}

#[test]
fn ready_heartbeat_misses_reach_degraded() {
    let mut fsm = SessionFsm::new(cfg()); // degraded_after=2, drop_after=4
    drive_to_ready(&mut fsm, 0);
    // miss #1 → 仍 Ready。
    fsm.on_heartbeat_miss(1000, Duration::ZERO);
    assert!(matches!(fsm.state(), SessionState::Ready(_)));
    // miss #2 → Degraded。
    fsm.on_heartbeat_miss(2000, Duration::ZERO);
    assert!(matches!(fsm.state(), SessionState::Degraded(_)));
}

#[test]
fn degraded_heartbeat_reply_recovers_ready() {
    let mut fsm = SessionFsm::new(cfg());
    drive_to_ready(&mut fsm, 0);
    fsm.on_heartbeat_miss(1000, Duration::ZERO);
    fsm.on_heartbeat_miss(2000, Duration::ZERO);
    assert!(matches!(fsm.state(), SessionState::Degraded(_)));
    // 回覆到達 → Ready,miss 歸零。
    fsm.on_heartbeat_reply(3000);
    match fsm.state() {
        SessionState::Ready(rs) => assert_eq!(rs.consecutive_misses, 0),
        s => panic!("expected Ready, got {s:?}"),
    }
}

#[test]
fn misses_reach_drop_threshold_to_backoff() {
    let mut fsm = SessionFsm::new(cfg()); // drop_after=4
    drive_to_ready(&mut fsm, 0);
    fsm.on_heartbeat_miss(1000, Duration::ZERO); // 1 Ready
    fsm.on_heartbeat_miss(2000, Duration::ZERO); // 2 Degraded
    fsm.on_heartbeat_miss(3000, Duration::ZERO); // 3 Degraded
    assert!(matches!(fsm.state(), SessionState::Degraded(_)));
    assert!(fsm.heartbeat_miss_would_drop()); // 下一 miss(=4) 會 drop
    fsm.on_heartbeat_miss(4000, Duration::from_secs(2)); // 4 → Backoff
    assert!(matches!(
        fsm.state(),
        SessionState::Backoff { attempt_n: 1, .. }
    ));
}

#[test]
fn ready_io_drop_to_backoff() {
    let mut fsm = SessionFsm::new(cfg());
    drive_to_ready(&mut fsm, 0);
    fsm.on_io_drop(500, Duration::from_secs(1));
    assert!(matches!(
        fsm.state(),
        SessionState::Backoff { attempt_n: 1, .. }
    ));
}

#[test]
fn ready_duplicate_client_id_kick_is_session_fatal() {
    // 顯式踢線入口。
    let mut fsm = SessionFsm::new(cfg());
    drive_to_ready(&mut fsm, 0);
    let ev = fsm.on_duplicate_client_id(0);
    assert_eq!(ev, vec![IbkrTwsSessionEventV1::DuplicateClientIdRejected]);
    assert!(matches!(
        fsm.state(),
        SessionState::Disconnected {
            reason: HaltReason::SessionFatal(FatalCause::DuplicateClientIdRejected)
        }
    ));
}

#[test]
fn error_frame_326_duplicate_client_id_from_ready() {
    // 主路徑:ERR_MSG 326 → conservative=SessionFatal → DuplicateClientIdRejected。
    let mut fsm = SessionFsm::new(cfg());
    drive_to_ready(&mut fsm, 0);
    let class = IbkrTwsErrorClassV1::conservative(IB_ERR_DUPLICATE_CLIENT_ID);
    let ev = fsm.on_error_frame(IB_ERR_DUPLICATE_CLIENT_ID, class, 0);
    assert_eq!(ev, vec![IbkrTwsSessionEventV1::DuplicateClientIdRejected]);
    assert!(matches!(
        fsm.state(),
        SessionState::Disconnected {
            reason: HaltReason::SessionFatal(FatalCause::DuplicateClientIdRejected)
        }
    ));
}

#[test]
fn weekly_reauth_from_ready_disconnects_and_is_terminal() {
    let mut fsm = SessionFsm::new(cfg());
    drive_to_ready(&mut fsm, 0);
    let ev = fsm.on_weekly_reauth();
    assert_eq!(ev, vec![IbkrTwsSessionEventV1::SessionExpiredWeeklyReauth]);
    assert!(matches!(
        fsm.state(),
        SessionState::Disconnected {
            reason: HaltReason::WeeklyReauth
        }
    ));
    // 結構性終態:永不自動重連（manager 以 is_terminal 為 attempt_connect 前置閘;終態 attempt 即
    // 非法轉移,debug_assert 攔——見 illegal_transition 測試）。唯一離開=reset_for_reactivation。
    assert!(fsm.is_terminal());
    fsm.reset_for_reactivation();
    assert!(!fsm.is_terminal());
    assert!(matches!(
        fsm.state(),
        SessionState::Disconnected {
            reason: HaltReason::Initial
        }
    ));
}

#[test]
fn backoff_elapsed_then_permit_recheck_to_connecting() {
    let mut fsm = SessionFsm::new(cfg());
    drive_to_ready(&mut fsm, 0);
    fsm.on_io_drop(0, Duration::from_millis(500));
    assert!(!fsm.backoff_elapsed(400)); // 未到期
    assert!(fsm.backoff_elapsed(500)); // 到期
    let ev = fsm.on_permit_granted(PermitToken::mint(), 500);
    assert_eq!(ev, vec![IbkrTwsSessionEventV1::ConnectPermitGranted]);
    assert!(matches!(fsm.state(), SessionState::Connecting));
}

#[test]
fn reconnect_budget_exhausted() {
    let mut c = cfg();
    c.max_reconnect_attempts = 3;
    let mut fsm = SessionFsm::new(c);
    drive_to_ready(&mut fsm, 0);
    // 連續 connect 失敗:attempt 1,2,3 → Backoff;第 4 次 → Exhausted。
    fsm.on_io_drop(0, Duration::from_millis(10)); // attempt 1
    fsm.on_permit_granted(PermitToken::mint(), 100);
    fsm.on_connect_failed(100, Duration::from_millis(10)); // attempt 2
    fsm.on_permit_granted(PermitToken::mint(), 200);
    fsm.on_connect_failed(200, Duration::from_millis(10)); // attempt 3
    fsm.on_permit_granted(PermitToken::mint(), 300);
    let ev = fsm.on_connect_failed(300, Duration::from_millis(10)); // attempt 4 > 3 → Exhausted
    assert_eq!(ev, vec![IbkrTwsSessionEventV1::ReconnectBudgetExhausted]);
    assert!(matches!(
        fsm.state(),
        SessionState::Disconnected {
            reason: HaltReason::ReconnectBudgetExhausted
        }
    ));
}

#[test]
fn halt_from_any_state() {
    // 從 Ready。
    let mut fsm = SessionFsm::new(cfg());
    drive_to_ready(&mut fsm, 0);
    let ev = fsm.on_halt();
    assert_eq!(ev, vec![IbkrTwsSessionEventV1::Halted]);
    assert!(matches!(
        fsm.state(),
        SessionState::Disconnected {
            reason: HaltReason::Halted
        }
    ));
    // 從 Connecting。
    let mut fsm2 = SessionFsm::new(cfg());
    fsm2.on_permit_granted(PermitToken::mint(), 0);
    fsm2.on_halt();
    assert!(matches!(
        fsm2.state(),
        SessionState::Disconnected {
            reason: HaltReason::Halted
        }
    ));
}

#[test]
fn illegal_transition_typed_and_state_unchanged() {
    // Disconnected(Initial) 收 transport_established → 非法（狀態不變）。
    // 註:debug build 下 illegal 會 debug_assert panic;測試以 release-mode 語義驗 typed 事件,
    // 故用 catch:在 debug_assertions 開啟時,改驗「非法組合經由 on_error_frame 於錯態」的 no-panic 面。
    // 這裡選 on_error_frame 在 Disconnected（無 debug_assert 生效路徑差異;它同樣 illegal）——
    // 為避免 debug_assert 中止,改測 release 契約:見下方 cfg(not(debug_assertions)) 版本。
    #[cfg(not(debug_assertions))]
    {
        let mut fsm = SessionFsm::new(cfg());
        let ev = fsm.on_transport_established(0);
        assert_eq!(ev, vec![IbkrTwsSessionEventV1::IllegalTransition]);
        assert!(matches!(
            fsm.state(),
            SessionState::Disconnected {
                reason: HaltReason::Initial
            }
        ));
    }
    // debug build:非法轉移 debug_assert!,以 catch_unwind 驗證確實觸發（fail-fast 契約）。
    #[cfg(debug_assertions)]
    {
        let res = std::panic::catch_unwind(|| {
            let mut fsm = SessionFsm::new(cfg());
            let _ = fsm.on_transport_established(0);
        });
        assert!(res.is_err(), "debug build 非法轉移應 debug_assert panic");
    }
}

#[test]
fn scheduled_restart_disconnect_does_not_consume_budget() {
    let mut fsm = SessionFsm::new(cfg());
    drive_to_ready(&mut fsm, 0);
    let ev = fsm.on_scheduled_restart_disconnect(0, Duration::from_secs(120));
    assert_eq!(ev, vec![IbkrTwsSessionEventV1::ScheduledRestartDisconnect]);
    match fsm.state() {
        SessionState::Backoff {
            attempt_n,
            scheduled,
            next_delay,
            ..
        } => {
            assert_eq!(*attempt_n, 0, "排程斷線不吃 budget（attempt 不 +1）");
            assert!(scheduled);
            assert_eq!(*next_delay, Duration::from_secs(120));
        }
        s => panic!("expected scheduled Backoff, got {s:?}"),
    }
    assert_eq!(fsm.reconnect_attempt(), 0);
}

// ---------------------------------------------------------------------------
// backoff（full jitter,注入 RNG）
// ---------------------------------------------------------------------------

#[test]
fn full_jitter_delay_bounded_and_capped() {
    let c = cfg(); // base=1s, cap=60s
                   // attempt=1:ceiling=min(cap, 1000*2)=2000ms;RNG 回超大值 → clamp 至 ceiling。
    let mut rng = SeqRng::new(vec![u64::MAX]);
    let d = full_jitter_delay(&c, 1, &mut rng);
    assert_eq!(d, Duration::from_millis(2000));
    // attempt=10:1000*2^10=1_024_000ms > cap 60_000ms → ceiling=cap;RNG=0 → 0。
    let mut rng0 = SeqRng::new(vec![0]);
    let d0 = full_jitter_delay(&c, 10, &mut rng0);
    assert_eq!(d0, Duration::ZERO);
    // 大 attempt 溢位飽和不 panic,仍被 cap 夾。
    let mut rngm = SeqRng::new(vec![u64::MAX]);
    let dm = full_jitter_delay(&c, 64, &mut rngm);
    assert_eq!(dm, Duration::from_millis(60_000));
}

#[test]
fn full_jitter_delay_ceiling_is_min_cap_base_pow2() {
    let c = cfg();
    // 遍歷 attempt,ceiling 應 = min(cap, base*2^attempt),RNG 回 ceiling（clamp 證上界）。
    for attempt in 0..12u32 {
        let mut rng = SeqRng::new(vec![u64::MAX]);
        let d = full_jitter_delay(&c, attempt, &mut rng).as_millis() as u64;
        let factor = 2u64.checked_pow(attempt).unwrap_or(u64::MAX);
        let expect = (1000u64.saturating_mul(factor)).min(60_000);
        assert_eq!(d, expect, "attempt {attempt}");
    }
}

#[test]
fn backoff_attempt_increments_and_resets_on_ready() {
    let mut fsm = SessionFsm::new(cfg());
    drive_to_ready(&mut fsm, 0);
    fsm.on_io_drop(0, Duration::from_millis(10)); // attempt 1
    assert_eq!(fsm.reconnect_attempt(), 1);
    fsm.on_permit_granted(PermitToken::mint(), 20);
    fsm.on_connect_failed(20, Duration::from_millis(10)); // attempt 2
    assert_eq!(fsm.reconnect_attempt(), 2);
    // 成功回 Ready → budget 歸零。
    fsm.on_permit_granted(PermitToken::mint(), 40);
    fsm.on_transport_established(40);
    fsm.on_handshake_result(happy_outcome(), 40);
    assert_eq!(fsm.reconnect_attempt(), 0);
}

// ---------------------------------------------------------------------------
// 心跳簿記
// ---------------------------------------------------------------------------

#[test]
fn heartbeat_send_due_and_marked_sent() {
    let mut fsm = SessionFsm::new(cfg()); // interval=30s
    drive_to_ready(&mut fsm, 0); // next_due=30_000
    assert!(!fsm.heartbeat_send_due(29_000));
    assert!(fsm.heartbeat_send_due(30_000));
    fsm.mark_heartbeat_sent(30_000);
    // 已送 → 在途,不再 due 直到回覆/miss + 下個 interval。
    assert!(!fsm.heartbeat_send_due(31_000));
}

#[test]
fn heartbeat_reply_overdue_detection() {
    let mut fsm = SessionFsm::new(cfg()); // timeout=10s
    drive_to_ready(&mut fsm, 0);
    fsm.mark_heartbeat_sent(30_000);
    assert!(!fsm.heartbeat_reply_overdue(39_000)); // <10s
    assert!(fsm.heartbeat_reply_overdue(40_000)); // =10s → overdue
}

#[test]
fn heartbeat_miss_would_drop_query() {
    let mut fsm = SessionFsm::new(cfg()); // drop_after=4
    drive_to_ready(&mut fsm, 0);
    assert!(!fsm.heartbeat_miss_would_drop()); // 0+1<4
    fsm.on_heartbeat_miss(1000, Duration::ZERO); // 1
    fsm.on_heartbeat_miss(2000, Duration::ZERO); // 2
    assert!(!fsm.heartbeat_miss_would_drop()); // 2+1<4
    fsm.on_heartbeat_miss(3000, Duration::ZERO); // 3
    assert!(fsm.heartbeat_miss_would_drop()); // 3+1>=4
}

// ---------------------------------------------------------------------------
// N2:farm-blip Transient 在活 session 不觸過早 reconnect
// ---------------------------------------------------------------------------

#[test]
fn n2_farm_blip_transient_no_state_change_in_ready() {
    let mut fsm = SessionFsm::new(cfg());
    drive_to_ready(&mut fsm, 0);
    for code in [
        IB_ERR_MKT_DATA_FARM_LOST,
        IB_ERR_TWS_SERVER_CONNECTIVITY_BROKEN,
        2105,
    ] {
        let class = IbkrTwsErrorClassV1::conservative(code);
        assert_eq!(
            class,
            IbkrTwsErrorClassV1::Transient,
            "code {code} 應 Transient"
        );
        let ev = fsm.on_error_frame(code, class, 1000);
        assert!(ev.is_empty(), "farm-blip {code} 不應發事件");
        assert!(
            matches!(fsm.state(), SessionState::Ready(_)),
            "farm-blip {code} 不得觸過早 reconnect/Backoff"
        );
    }
}

#[test]
fn n2_farm_blip_transient_no_state_change_in_degraded() {
    let mut fsm = SessionFsm::new(cfg());
    drive_to_ready(&mut fsm, 0);
    fsm.on_heartbeat_miss(1000, Duration::ZERO);
    fsm.on_heartbeat_miss(2000, Duration::ZERO);
    assert!(matches!(fsm.state(), SessionState::Degraded(_)));
    let class = IbkrTwsErrorClassV1::conservative(IB_ERR_MKT_DATA_FARM_LOST);
    let ev = fsm.on_error_frame(IB_ERR_MKT_DATA_FARM_LOST, class, 3000);
    assert!(ev.is_empty());
    // 仍 Degraded（farm-blip 不改劣化態;只有心跳回覆才恢復 Ready）。
    assert!(matches!(fsm.state(), SessionState::Degraded(_)));
}

#[test]
fn session_fatal_error_frame_disconnects() {
    let mut fsm = SessionFsm::new(cfg());
    drive_to_ready(&mut fsm, 0);
    let class = IbkrTwsErrorClassV1::conservative(IB_ERR_COULD_NOT_CONNECT_TWS); // 502
    let ev = fsm.on_error_frame(IB_ERR_COULD_NOT_CONNECT_TWS, class, 0);
    assert!(ev.is_empty()); // GatewayError 無專屬 IPC 事件
    assert!(matches!(
        fsm.state(),
        SessionState::Disconnected {
            reason: HaltReason::SessionFatal(FatalCause::GatewayError(502))
        }
    ));
}

// ---------------------------------------------------------------------------
// 排程感知 + DST（America/New_York;chrono-tz 解;凍結時鐘,禁硬編日期 time-bomb）
// ---------------------------------------------------------------------------

/// 由 ET civil time 構造 UTC 注入時鐘（非模糊時段;自檢 weekday）。
fn utc_from_et(y: i32, mo: u32, d: u32, h: u32, mi: u32, expect_wd: Weekday) -> DateTime<Utc> {
    let et = chrono_tz::America::New_York
        .with_ymd_and_hms(y, mo, d, h, mi, 0)
        .single()
        .expect("non-ambiguous ET civil time");
    assert_eq!(et.weekday(), expect_wd, "fixture weekday 自檢");
    et.with_timezone(&Utc)
}

#[test]
fn restart_window_resolves_dst_both_sides() {
    // restart 窗 23:30 ET,30 分;工作日(Mon-Sat)。冬(EST,UTC-5)與夏(EDT,UTC-4)同 ET 本地時應同判。
    let mut c = cfg();
    c.restart_window = Some(RestartWindow {
        start_hour: 23,
        start_minute: 30,
        duration_min: 30,
    });
    c.scheduled_grace = Duration::from_secs(60);

    // 冬:2026-01-13(週二)23:40 EST。
    let winter = utc_from_et(2026, 1, 13, 23, 40, Weekday::Tue);
    // 夏:2026-07-14(週二)23:40 EDT。
    let summer = utc_from_et(2026, 7, 14, 23, 40, Weekday::Tue);
    for now in [winter, summer] {
        match classify_disconnect_context(now, &c) {
            DisconnectContext::ScheduledRestart { first_delay } => {
                // 窗尾=24:00(=23:30+30m),now=23:40 → 殘餘 20m + grace 60s = 1260s。
                assert_eq!(first_delay, Duration::from_secs(20 * 60 + 60));
            }
            other => panic!("expected ScheduledRestart, got {other:?}"),
        }
    }
    // 證明 DST offset 確實不同（同 ET 本地 → 不同 UTC 小時）。
    assert_ne!(winter.hour(), summer.hour());
}

#[test]
fn weekly_reauth_resolves_dst_both_sides() {
    let c = cfg(); // 週日 1:00-2:00 ET
                   // 冬週日:2026-01-11 01:30 EST。
    let winter = utc_from_et(2026, 1, 11, 1, 30, Weekday::Sun);
    // 夏週日:2026-07-05 01:30 EDT。
    let summer = utc_from_et(2026, 7, 5, 1, 30, Weekday::Sun);
    for now in [winter, summer] {
        assert_eq!(
            classify_disconnect_context(now, &c),
            DisconnectContext::WeeklyReauth
        );
    }
    assert_ne!(winter.hour(), summer.hour());
}

#[test]
fn weekly_reauth_across_fall_back_ambiguous_hour() {
    // 2026-11-01(週日)回撥:02:00 EDT → 01:00 EST（01:00-01:59 出現兩次）。
    // 兩次 01:30(EDT 前、EST 後)皆在週日 1:00-2:00 ET 重認證窗內。以 UTC 直接注入避開模糊構造。
    let c = cfg();
    // 05:30 UTC = 01:30 EDT(回撥前)。
    let before = Utc.with_ymd_and_hms(2026, 11, 1, 5, 30, 0).unwrap();
    // 06:30 UTC = 01:30 EST(回撥後,第二次 01:30)。
    let after = Utc.with_ymd_and_hms(2026, 11, 1, 6, 30, 0).unwrap();
    for now in [before, after] {
        let et = now.with_timezone(&chrono_tz::America::New_York);
        assert_eq!(et.weekday(), Weekday::Sun);
        assert_eq!(et.hour(), 1);
        assert_eq!(et.minute(), 30);
        assert_eq!(
            classify_disconnect_context(now, &c),
            DisconnectContext::WeeklyReauth,
            "回撥兩側 01:30 ET 皆應 WeeklyReauth"
        );
    }
}

#[test]
fn weekly_reauth_across_spring_forward_gap() {
    // 2026-03-08(週日)前撥:02:00 EST → 03:00 EDT（02:00-02:59 不存在）。
    // 01:30 EST(gap 前)在重認證窗內;03:30 EDT(gap 後)在窗外 → Normal（週日不套 restart 窗）。
    let c = cfg();
    // 06:30 UTC = 01:30 EST(前撥前)。
    let before = Utc.with_ymd_and_hms(2026, 3, 8, 6, 30, 0).unwrap();
    let et_b = before.with_timezone(&chrono_tz::America::New_York);
    assert_eq!(
        (et_b.weekday(), et_b.hour(), et_b.minute()),
        (Weekday::Sun, 1, 30)
    );
    assert_eq!(
        classify_disconnect_context(before, &c),
        DisconnectContext::WeeklyReauth
    );
    // 07:30 UTC = 03:30 EDT(前撥後,窗外)。
    let after = Utc.with_ymd_and_hms(2026, 3, 8, 7, 30, 0).unwrap();
    let et_a = after.with_timezone(&chrono_tz::America::New_York);
    assert_eq!(
        (et_a.weekday(), et_a.hour(), et_a.minute()),
        (Weekday::Sun, 3, 30)
    );
    assert_eq!(
        classify_disconnect_context(after, &c),
        DisconnectContext::Normal
    );
}

#[test]
fn restart_window_unconfigured_is_normal() {
    // 窗未配置 → 無感知（不猜默認時刻,§8-U4）:即便處於「像是」重啟時段亦 Normal。
    let c = cfg(); // restart_window=None
    let now = utc_from_et(2026, 1, 13, 23, 45, Weekday::Tue);
    assert_eq!(
        classify_disconnect_context(now, &c),
        DisconnectContext::Normal
    );
}

#[test]
fn restart_window_not_applied_on_sunday() {
    // auto-restart 只覆蓋 Mon-Sat:週日落在 restart 窗時刻但非重認證窗 → Normal（不套 restart）。
    let mut c = cfg();
    c.restart_window = Some(RestartWindow {
        start_hour: 23,
        start_minute: 30,
        duration_min: 30,
    });
    // 週日 23:40 ET（restart 窗時刻,但週日不套 restart;亦不在 1-2am 重認證窗）→ Normal。
    let sun = utc_from_et(2026, 1, 11, 23, 40, Weekday::Sun);
    assert_eq!(
        classify_disconnect_context(sun, &c),
        DisconnectContext::Normal
    );
}

#[test]
fn restart_window_remaining_plus_grace_precise() {
    // 秒粒度殘餘:窗 01:00-01:10 ET,now=01:05:00 → 殘餘 5m + grace 30s = 330s。
    let w = RestartWindow {
        start_hour: 1,
        start_minute: 0,
        duration_min: 10,
    };
    assert_eq!(
        w.remaining_within(1, 5, 0, Duration::from_secs(30)),
        Some(Duration::from_secs(5 * 60 + 30))
    );
    // 窗外(01:15) → None。
    assert_eq!(w.remaining_within(1, 15, 0, Duration::from_secs(30)), None);
    // 窗起始邊界(01:00:00) → 含（殘餘 10m）。
    assert_eq!(
        w.remaining_within(1, 0, 0, Duration::from_secs(0)),
        Some(Duration::from_secs(10 * 60))
    );
    // 窗尾邊界(01:10:00) → 排除。
    assert_eq!(w.remaining_within(1, 10, 0, Duration::from_secs(0)), None);
}

// ---------------------------------------------------------------------------
// IPC label 投影
// ---------------------------------------------------------------------------

#[test]
fn ipc_label_projection_matches_state() {
    let mut fsm = SessionFsm::new(cfg());
    assert_eq!(fsm.ipc_state(), IbkrTwsSessionStateV1::Disconnected);
    fsm.on_permit_granted(PermitToken::mint(), 0);
    assert_eq!(fsm.ipc_state(), IbkrTwsSessionStateV1::Connecting);
    fsm.on_transport_established(0);
    assert_eq!(fsm.ipc_state(), IbkrTwsSessionStateV1::Handshaking);
    fsm.on_handshake_result(happy_outcome(), 0);
    assert_eq!(fsm.ipc_state(), IbkrTwsSessionStateV1::Ready);
    fsm.on_heartbeat_miss(1000, Duration::ZERO);
    fsm.on_heartbeat_miss(2000, Duration::ZERO);
    assert_eq!(fsm.ipc_state(), IbkrTwsSessionStateV1::Degraded);
    fsm.on_io_drop(3000, Duration::from_secs(1));
    assert_eq!(fsm.ipc_state(), IbkrTwsSessionStateV1::Backoff);
}
