// P0-ENGINE-HALTSESSION-STUCK-FIX (2026-05-19) — halt TTL state machine tests.
// P0-ENGINE-HALTSESSION-STUCK-FIX（2026-05-19）：halt TTL 狀態機測試。
//
// 涵蓋 spec §6.1 unit 列表的 15 個 case + Option<u64> halt_ttl_remaining_ms +
// late-clear 邊界（zero-tick 24h + WS recovery 早晚會 catch）。
//
// 測試策略：直接構造 TickPipeline 透過 patch_risk_config 改 daily_loss_halt_ttl_ms
// 後，手動 set halt_kind / halt_set_ts_ms 模擬 step_6 觸發後狀態，呼叫
// `check_and_clear_halt_expired(now_ms)` 驗：
//   - 不該清 → return false + state 不變
//   - 該清 → return true + paper_paused=false + halt_kind=None + halt_set_ts_ms=0

use super::super::*;
use crate::event_consumer::paper_state_restore::env_test_lock as env_lock;
use crate::halt_audit::HaltKind;

/// MUST-FIX-1 Round 2（2026-05-19/20）：健壯 JSONL 解析器。
///
/// 為什麼必要：cargo test 內多 thread 在同 process 對同 halt_audit.log
/// (OPENCLAW_HALT_AUDIT_LOG 路徑) 併行 append；雖然各 write 系統呼叫
/// 個別 atomic（< PIPE_BUF），但 std::fs::OpenOptions 的 writeln! 由
/// `write_all(content)` + `write_all("\n")` 兩個 write 組合（macOS 觀察），
/// 中間若有另一 thread 插入 write 會造成「JSONL 行黏在一起無 \n 分隔」。
///
/// 本 parser 先試 .lines()，找不到 valid JSON 時 fallback 用 `}{` 切並
/// 補 braces，回 Vec<serde_json::Value>（含可解析的所有 JSON 物件）。
///
/// 注意：此 parser 只給 test 使用；prod 路徑（governance_audit_log writer）
/// 由 Python tail-writer（MUST-FIX-3）負責，那邊用 ON CONFLICT DO NOTHING
/// + 嚴格 schema validate + DB 序列化，不會被同 file race 影響。
fn parse_jsonl_robust(content: &str) -> Vec<serde_json::Value> {
    let mut out: Vec<serde_json::Value> = Vec::new();
    // Pass 1：直接 .lines()
    for line in content.lines() {
        if let Ok(v) = serde_json::from_str::<serde_json::Value>(line) {
            out.push(v);
        }
    }
    // Pass 2：整段內容用 `}{` 切，每段補 brace 後試解析（pass 1 漏的黏接行）
    let joined: String = content.replace('\n', "");
    let parts: Vec<String> = joined
        .split("}{")
        .enumerate()
        .map(|(i, p)| {
            let mut s = p.to_string();
            if i > 0 {
                s.insert(0, '{');
            }
            if !s.ends_with('}') {
                s.push('}');
            }
            s
        })
        .collect();
    for p in parts {
        if let Ok(v) = serde_json::from_str::<serde_json::Value>(&p) {
            if !out.contains(&v) {
                out.push(v);
            }
        }
    }
    out
}

/// Helper：建 TickPipeline 並 patch 一個 daily_loss_halt_ttl_ms。
/// 採 IntentProcessor::update_risk_config（既有 public IPC patch 路徑）。
fn make_pipeline_with_daily_loss_ttl(ttl_ms: u64) -> TickPipeline {
    let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
    let mut cfg = pipeline.intent_processor.risk_config().clone();
    cfg.limits.daily_loss_halt_ttl_ms = ttl_ms;
    cfg.limits.drawdown_halt_ttl_ms = 0; // 三環境硬性 sticky
    pipeline.intent_processor.update_risk_config(cfg);
    pipeline
}

#[test]
fn test_check_clear_no_active_halt() {
    let mut p = make_pipeline_with_daily_loss_ttl(24 * 60 * 60 * 1000);
    p.halt_kind = None;
    p.halt_set_ts_ms = 0;
    p.paper_paused = false;
    let cleared = p.check_and_clear_halt_expired(1_000_000);
    assert!(!cleared, "halt_kind=None 不該清");
    assert!(p.halt_kind.is_none());
}

#[test]
fn test_check_clear_daily_loss_within_ttl() {
    let ttl = 24 * 60 * 60 * 1000;
    let mut p = make_pipeline_with_daily_loss_ttl(ttl);
    p.halt_kind = Some(HaltKind::DailyLoss);
    p.halt_set_ts_ms = 1_000_000;
    p.paper_paused = true;
    p.session_halted = true;
    // 1h elapse，遠未過 24h ttl
    let cleared = p.check_and_clear_halt_expired(1_000_000 + 60 * 60 * 1000);
    assert!(!cleared, "1h elapse 不該清");
    assert_eq!(p.halt_kind, Some(HaltKind::DailyLoss));
    assert!(p.paper_paused);
}

#[test]
fn test_check_clear_daily_loss_after_ttl() {
    let ttl = 24 * 60 * 60 * 1000;
    let mut p = make_pipeline_with_daily_loss_ttl(ttl);
    p.halt_kind = Some(HaltKind::DailyLoss);
    p.halt_set_ts_ms = 1_000_000;
    p.paper_paused = true;
    p.session_halted = true;
    // 24h + 1s elapse
    let cleared = p.check_and_clear_halt_expired(1_000_000 + ttl + 1000);
    assert!(cleared, "過 ttl 應清");
    assert_eq!(p.halt_kind, None);
    assert_eq!(p.halt_set_ts_ms, 0);
    assert!(!p.paper_paused);
    assert!(!p.session_halted);
}

#[test]
fn test_check_clear_drawdown_never_clears() {
    let ttl = 24 * 60 * 60 * 1000;
    let mut p = make_pipeline_with_daily_loss_ttl(ttl);
    p.halt_kind = Some(HaltKind::SessionDrawdown);
    p.halt_set_ts_ms = 1_000_000;
    p.paper_paused = true;
    // 7d elapse — 仍 sticky
    let cleared = p.check_and_clear_halt_expired(1_000_000 + 7 * ttl);
    assert!(!cleared, "drawdown 三環境永遠 sticky");
    assert_eq!(p.halt_kind, Some(HaltKind::SessionDrawdown));
    assert!(p.paper_paused);
}

#[test]
fn test_check_clear_other_never_clears() {
    let ttl = 24 * 60 * 60 * 1000;
    let mut p = make_pipeline_with_daily_loss_ttl(ttl);
    p.halt_kind = Some(HaltKind::Other);
    p.halt_set_ts_ms = 1_000_000;
    p.paper_paused = true;
    // 7d elapse — fail-safe sticky
    let cleared = p.check_and_clear_halt_expired(1_000_000 + 7 * ttl);
    assert!(!cleared, "未知 reason 走 Other → fail-safe sticky");
    assert_eq!(p.halt_kind, Some(HaltKind::Other));
}

#[test]
fn test_check_clear_disabled_when_ttl_zero() {
    // Live D1：daily_loss_halt_ttl_ms = 0 = sticky
    let mut p = make_pipeline_with_daily_loss_ttl(0);
    p.halt_kind = Some(HaltKind::DailyLoss);
    p.halt_set_ts_ms = 1_000_000;
    p.paper_paused = true;
    // 7d elapse — TTL=0 = disabled sticky
    let cleared = p.check_and_clear_halt_expired(1_000_000 + 7 * 86_400_000);
    assert!(!cleared, "ttl=0 = sticky（Live D1 policy）");
    assert_eq!(p.halt_kind, Some(HaltKind::DailyLoss));
    assert!(p.paper_paused);
}

#[test]
fn test_clock_skew_no_panic() {
    // halt_set_ts_ms > now_ms（時鐘倒流）→ saturating_sub → elapsed=0，不該清不該 panic
    let ttl = 24 * 60 * 60 * 1000;
    let mut p = make_pipeline_with_daily_loss_ttl(ttl);
    p.halt_kind = Some(HaltKind::DailyLoss);
    p.halt_set_ts_ms = 2_000_000_000; // 未來 ts
    p.paper_paused = true;
    let cleared = p.check_and_clear_halt_expired(1_000_000_000); // 過去 ts
    assert!(!cleared, "時鐘倒流 saturating_sub=0 不清");
    assert_eq!(p.halt_kind, Some(HaltKind::DailyLoss));
}

#[test]
fn test_check_clear_zero_halt_set_ts_defensive() {
    // halt_kind=Some 但 halt_set_ts_ms=0（不一致狀態）→ defensive return false
    let ttl = 24 * 60 * 60 * 1000;
    let mut p = make_pipeline_with_daily_loss_ttl(ttl);
    p.halt_kind = Some(HaltKind::DailyLoss);
    p.halt_set_ts_ms = 0;
    let cleared = p.check_and_clear_halt_expired(1_000_000_000);
    assert!(!cleared, "halt_set_ts_ms=0 防禦性回 false");
}

#[test]
fn test_compute_halt_ttl_remaining_none_when_no_halt() {
    let p = make_pipeline_with_daily_loss_ttl(24 * 60 * 60 * 1000);
    // halt_kind 預設 None
    assert!(p.compute_halt_ttl_remaining_ms(1_000_000).is_none());
}

#[test]
fn test_compute_halt_ttl_remaining_some_for_daily_loss() {
    let ttl = 24 * 60 * 60 * 1000;
    let mut p = make_pipeline_with_daily_loss_ttl(ttl);
    p.halt_kind = Some(HaltKind::DailyLoss);
    p.halt_set_ts_ms = 1_000_000;
    // 1h elapse → 剩 23h
    let now = 1_000_000 + 60 * 60 * 1000;
    let remaining = p.compute_halt_ttl_remaining_ms(now);
    assert_eq!(remaining, Some(23 * 60 * 60 * 1000));
}

#[test]
fn test_compute_halt_ttl_remaining_none_for_drawdown_sticky() {
    let mut p = make_pipeline_with_daily_loss_ttl(24 * 60 * 60 * 1000);
    p.halt_kind = Some(HaltKind::SessionDrawdown);
    p.halt_set_ts_ms = 1_000_000;
    // MIT SHOULD-2：sticky → None（不是 sentinel u64::MAX）
    assert!(p.compute_halt_ttl_remaining_ms(2_000_000).is_none());
}

#[test]
fn test_compute_halt_ttl_remaining_none_for_ttl_zero_live_sticky() {
    // Live D1：daily_loss + ttl=0
    let mut p = make_pipeline_with_daily_loss_ttl(0);
    p.halt_kind = Some(HaltKind::DailyLoss);
    p.halt_set_ts_ms = 1_000_000;
    // ttl=0 → None（sticky）
    assert!(p.compute_halt_ttl_remaining_ms(2_000_000).is_none());
}

#[test]
fn test_zero_tick_24h_no_clear_until_first_tick() {
    // WS-feed dependency acknowledgment：tick 為 0 期間 TTL 不 fire。
    // 模擬：set halt 後不呼 check（無 tick），檢查 state 仍 sticky；
    // 之後第一個 tick 帶過期 ts，state 立即清。
    let ttl = 24 * 60 * 60 * 1000;
    let mut p = make_pipeline_with_daily_loss_ttl(ttl);
    p.halt_kind = Some(HaltKind::DailyLoss);
    p.halt_set_ts_ms = 0;
    p.halt_set_ts_ms = 1_000_000;
    p.paper_paused = true;
    // 模擬 zero-tick 24h：完全不呼 check → state 仍 sticky
    assert_eq!(p.halt_kind, Some(HaltKind::DailyLoss));
    assert!(p.paper_paused);
    // WS recovery → 第一筆 tick ts_ms = halt_set + ttl + 30s
    let recovery_ts = 1_000_000 + ttl + 30_000;
    let cleared = p.check_and_clear_halt_expired(recovery_ts);
    assert!(cleared, "WS recovery 第一 tick 該清");
    assert_eq!(p.halt_kind, None);
}

#[test]
fn test_snapshot_roundtrip_persist_halt_state() {
    // 設 daily_loss halt → snapshot → 驗 mode_snapshots 帶 halt_kind / halt_set_ts_ms
    let ttl = 24 * 60 * 60 * 1000;
    let mut p = make_pipeline_with_daily_loss_ttl(ttl);
    p.halt_kind = Some(HaltKind::DailyLoss);
    p.halt_set_ts_ms = 1_700_000_000_000;
    let snap = p.snapshot();
    // Mode snapshot 帶 halt_kind / halt_set_ts_ms
    let kind_key = p.pipeline_kind.db_mode();
    let mode_snap = snap.mode_snapshots.get(kind_key).expect("mode snapshot 必存");
    assert_eq!(mode_snap.halt_kind, Some(HaltKind::DailyLoss));
    assert_eq!(mode_snap.halt_set_ts_ms, 1_700_000_000_000);
    // PipelineSnapshot 對外欄位也帶
    assert_eq!(snap.halt_kind, Some("daily_loss".to_string()));
    assert_eq!(snap.halt_set_ts_ms, 1_700_000_000_000);
}

#[test]
fn test_snapshot_pipeline_halt_kind_for_drawdown_sticky_remaining_none() {
    let mut p = make_pipeline_with_daily_loss_ttl(24 * 60 * 60 * 1000);
    p.halt_kind = Some(HaltKind::SessionDrawdown);
    p.halt_set_ts_ms = 1_700_000_000_000;
    let snap = p.snapshot();
    assert_eq!(snap.halt_kind, Some("session_drawdown".to_string()));
    // MIT SHOULD-2：sticky → halt_ttl_remaining_ms = None
    assert!(snap.halt_ttl_remaining_ms.is_none());
}

// ---------------------------------------------------------------------------
// MUST-FIX-2 Round 2（2026-05-19/20）：snapshot → restart → restore roundtrip
// 確認 restore_halt_state_from_snapshot 把 mode_snapshots 內 halt_kind /
// halt_set_ts_ms 真實寫回新 pipeline，TTL 起點不被重啟重置（AC A-4）。
// ---------------------------------------------------------------------------

/// 工具：把 PipelineSnapshot 序列化成 JSON 並寫進 tempdir，做為 restart
/// 之前的「上一輪 snapshot」素材；同時設好 OPENCLAW_DATA_DIR 讓 restore
/// helper 讀對位置。
fn write_snapshot_to_tempdir(snap: &crate::pipeline_types::PipelineSnapshot) -> std::path::PathBuf {
    let dir = std::env::temp_dir().join(format!(
        "halt_restore_test_{}_{}",
        std::process::id(),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_nanos())
            .unwrap_or(0)
    ));
    std::fs::create_dir_all(&dir).expect("temp data dir");
    // 用 pipeline.pipeline_kind.db_mode() 作為 snapshot filename 一部分 —
    // PipelineSnapshot 自帶 pipeline_kind 欄位。
    let kind_tag = snap.pipeline_kind.db_mode();
    let path = dir.join(format!("pipeline_snapshot_{}.json", kind_tag));
    let json = serde_json::to_string_pretty(snap).expect("serialize snapshot");
    std::fs::write(&path, json).expect("write snapshot");
    dir
}

#[tokio::test]
async fn test_halt_state_restored_after_restart() {
    let _guard = env_lock();
    // 場景：engine 1 在 T0 設 daily_loss halt → snapshot → engine 1 停。
    // engine 2 啟動 → 讀 snapshot → halt_kind=Some(DailyLoss) + halt_set_ts_ms=T0。
    // 推進到 T0+24h+1s → on_tick → paper_paused 被清，elapsed 從 ORIGINAL T0 算。
    let ttl = 24 * 60 * 60 * 1000_u64;
    let t0: u64 = 1_700_000_000_000;

    // engine 1：set halt 後抓 snapshot
    let mut engine1 = make_pipeline_with_daily_loss_ttl(ttl);
    engine1.halt_kind = Some(HaltKind::DailyLoss);
    engine1.halt_set_ts_ms = t0;
    engine1.paper_paused = true;
    engine1.session_halted = true;
    let snap = engine1.snapshot();

    let temp_dir = write_snapshot_to_tempdir(&snap);

    // SAFETY: 串行 test 改 env；末尾清除。
    unsafe {
        std::env::set_var("OPENCLAW_DATA_DIR", &temp_dir);
    }

    // engine 2：fresh pipeline；ctor 預設 halt_kind=None / 0；TTL 仍 24h。
    let mut engine2 = make_pipeline_with_daily_loss_ttl(ttl);
    assert!(engine2.halt_kind.is_none(), "ctor 預設應為 None");
    assert_eq!(engine2.halt_set_ts_ms, 0, "ctor 預設應為 0");

    // 跑 restore
    crate::event_consumer::paper_state_restore::restore_halt_state_from_snapshot(&mut engine2).await;

    // 驗：halt_kind + halt_set_ts_ms 從 snapshot 還原
    assert_eq!(
        engine2.halt_kind,
        Some(HaltKind::DailyLoss),
        "halt_kind 應從 snapshot 還原為 DailyLoss"
    );
    assert_eq!(
        engine2.halt_set_ts_ms, t0,
        "halt_set_ts_ms 應從 snapshot 還原為原 T0，不被 restart 重置"
    );
    assert!(engine2.paper_paused, "paper_paused 應從 snapshot 還原");
    assert!(engine2.session_halted, "session_halted 應從 snapshot 還原");

    // 推進到 T0+24h+1s（模擬已過 TTL）— on_tick TTL probe 應清
    let cleared = engine2.check_and_clear_halt_expired(t0 + ttl + 1000);
    assert!(
        cleared,
        "TTL 從 ORIGINAL T0 算（不重新從 boot 算），過 24h+1s 應被清"
    );
    assert_eq!(engine2.halt_kind, None);
    assert!(!engine2.paper_paused);

    // cleanup
    let _ = std::fs::remove_dir_all(&temp_dir);
    unsafe {
        std::env::remove_var("OPENCLAW_DATA_DIR");
    }
}

#[tokio::test]
async fn test_restore_halt_state_missing_snapshot_is_cold_start() {
    let _guard = env_lock();
    // 缺檔 → fail-soft 冷啟動：pipeline halt 狀態維持 ctor 預設。
    let temp_dir = std::env::temp_dir().join(format!(
        "halt_restore_missing_{}_{}",
        std::process::id(),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_nanos())
            .unwrap_or(0)
    ));
    std::fs::create_dir_all(&temp_dir).expect("temp dir");
    // 不寫 snapshot — restore 應 fail-soft

    unsafe {
        std::env::set_var("OPENCLAW_DATA_DIR", &temp_dir);
    }

    let ttl = 24 * 60 * 60 * 1000_u64;
    let mut engine = make_pipeline_with_daily_loss_ttl(ttl);
    crate::event_consumer::paper_state_restore::restore_halt_state_from_snapshot(&mut engine).await;
    assert!(engine.halt_kind.is_none(), "缺檔 → halt_kind 應仍為 None");
    assert_eq!(engine.halt_set_ts_ms, 0, "缺檔 → halt_set_ts_ms 應仍為 0");

    let _ = std::fs::remove_dir_all(&temp_dir);
    unsafe {
        std::env::remove_var("OPENCLAW_DATA_DIR");
    }
}

#[tokio::test]
async fn test_restore_halt_state_corrupted_json_is_cold_start() {
    let _guard = env_lock();
    // 壞 JSON → fail-soft 冷啟動。
    let temp_dir = std::env::temp_dir().join(format!(
        "halt_restore_corrupt_{}_{}",
        std::process::id(),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_nanos())
            .unwrap_or(0)
    ));
    std::fs::create_dir_all(&temp_dir).expect("temp dir");
    // 寫一個壞 JSON
    std::fs::write(
        temp_dir.join("pipeline_snapshot_paper.json"),
        "{ this_is_not_valid_json :: ",
    )
    .expect("write corrupted snapshot");

    unsafe {
        std::env::set_var("OPENCLAW_DATA_DIR", &temp_dir);
    }

    let ttl = 24 * 60 * 60 * 1000_u64;
    let mut engine = make_pipeline_with_daily_loss_ttl(ttl);
    crate::event_consumer::paper_state_restore::restore_halt_state_from_snapshot(&mut engine).await;
    assert!(engine.halt_kind.is_none(), "壞 JSON → halt_kind 應仍為 None");
    assert_eq!(engine.halt_set_ts_ms, 0);

    let _ = std::fs::remove_dir_all(&temp_dir);
    unsafe {
        std::env::remove_var("OPENCLAW_DATA_DIR");
    }
}

#[tokio::test]
async fn test_restore_halt_state_kind_set_but_ts_zero_treated_as_cold() {
    let _guard = env_lock();
    // halt_kind=Some 但 halt_set_ts_ms=0 → 不一致；保守冷啟動。
    let ttl = 24 * 60 * 60 * 1000_u64;

    // 構造異常 snapshot：halt_kind=DailyLoss 但 halt_set_ts_ms=0
    let mut engine1 = make_pipeline_with_daily_loss_ttl(ttl);
    engine1.halt_kind = Some(HaltKind::DailyLoss);
    engine1.halt_set_ts_ms = 0; // 異常
    let snap = engine1.snapshot();
    let temp_dir = write_snapshot_to_tempdir(&snap);

    unsafe {
        std::env::set_var("OPENCLAW_DATA_DIR", &temp_dir);
    }

    let mut engine2 = make_pipeline_with_daily_loss_ttl(ttl);
    crate::event_consumer::paper_state_restore::restore_halt_state_from_snapshot(&mut engine2).await;
    assert!(engine2.halt_kind.is_none(), "halt_set_ts=0 應 fail-soft 冷啟動");
    assert_eq!(engine2.halt_set_ts_ms, 0);

    let _ = std::fs::remove_dir_all(&temp_dir);
    unsafe {
        std::env::remove_var("OPENCLAW_DATA_DIR");
    }
}

// ---------------------------------------------------------------------------
// SHOULD-FIX Round 2 (spec §6.3)：2026-05-19 incident replay。
// 透過直接構造 paper_state + 觸發 step_6 / 推進時鐘等流程，覆蓋 14 步 assertion。
// ---------------------------------------------------------------------------

#[test]
fn test_2026_05_19_incident_replay() {
    let _guard = env_lock();
    use crate::halt_audit::HaltKind;

    // Step 1: 構造 TickPipeline + RiskConfig 同 demo TOML 預設
    //   - session_drawdown_max_pct = 25.0
    //   - daily_loss_max_pct = 15.0
    //   - daily_loss_halt_ttl_ms = 24h
    //   - drawdown_halt_ttl_ms = 0 (sticky)
    let ttl_24h = 24 * 60 * 60 * 1000_u64;
    let mut pipeline = make_pipeline_with_daily_loss_ttl(ttl_24h);
    let mut cfg = pipeline.intent_processor.risk_config().clone();
    cfg.limits.session_drawdown_max_pct = 25.0;
    cfg.limits.daily_loss_max_pct = 15.0;
    pipeline.intent_processor.update_risk_config(cfg);

    // forensic log 隔離至 tempfile（避免污染 /tmp/openclaw 真實 log）
    let halt_log = std::env::temp_dir().join(format!(
        "halt_audit_incident_replay_{}_{}.log",
        std::process::id(),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_nanos())
            .unwrap_or(0)
    ));
    let _ = std::fs::remove_file(&halt_log);
    unsafe {
        std::env::set_var("OPENCLAW_HALT_AUDIT_LOG", &halt_log);
    }

    // Step 2: 直接模擬 step_6 priority 9 DailyLoss arm 已觸發
    //   （單測無法簡易觸發 IntentProcessor priority 9，本步以 set state +
    //   呼叫 record_halt_set 取代，覆蓋 spec §6.3 第 4-5 步斷言）
    // Reason 加 unique tag 以便精確篩本 test 的 JSONL 行（避免併發 test
    //   寫入 default path 污染最後一行解析）。
    let t0_set = 1_700_000_000_000_u64;
    let reason = "DAILY LOSS: 15.23% >= 15.0% / round2-incident-replay";
    let kind = HaltKind::classify(reason);
    assert_eq!(kind, HaltKind::DailyLoss, "spec §6.3 step 2 classify");
    pipeline.halt_kind = Some(kind);
    pipeline.halt_set_ts_ms = t0_set;
    pipeline.paper_paused = true;
    pipeline.session_halted = true;

    // 寫 forensic set 行（模擬 step_6 arm 內部呼叫）
    {
        let pipeline_kind = pipeline.pipeline_kind;
        let engine_mode = pipeline.effective_engine_mode().to_string();
        let risk_config = pipeline.intent_processor.risk_config().clone();
        crate::halt_audit::record_halt_set(
            kind,
            reason,
            pipeline_kind,
            &engine_mode,
            &risk_config,
            0,
            &pipeline.paper_state,
            t0_set,
        );
    }

    // Step 3-4: 跑 on_tick 不會清（剛 set，1ms elapsed）
    let _ = pipeline.check_and_clear_halt_expired(t0_set + 1);
    assert!(pipeline.paper_paused, "step 3-4 仍 paused");
    assert_eq!(pipeline.halt_kind, Some(HaltKind::DailyLoss));
    assert_eq!(pipeline.halt_set_ts_ms, t0_set);

    // Step 5: halt_audit.log set 行存在（用 unique reason 精確篩） + 含
    // kind=daily_loss + reason；併發 test 污染下可能存在「兩條 JSONL 黏在同行」
    // 缺 \n 的情況（同 process 多 test thread 對同檔 append），改用「`}{` split
    // + repair braces」健壯解析後再 filter。
    let content = std::fs::read_to_string(&halt_log).expect("halt_audit log should exist");
    let set_parsed = parse_jsonl_robust(&content)
        .into_iter()
        .find(|v| v.get("reason").and_then(|r| r.as_str()) == Some(reason))
        .unwrap_or_else(|| panic!("set 行未找到 by reason={}, content={}", reason, content));
    assert_eq!(set_parsed["event"].as_str().unwrap_or(""), "halt_session_set");
    assert_eq!(set_parsed["kind"].as_str().unwrap_or(""), "daily_loss");
    assert_eq!(set_parsed["reason"].as_str().unwrap_or(""), reason);
    assert_eq!(set_parsed["halt_set_ts_ms"].as_u64().unwrap_or(0), t0_set);
    // 量化 context 6 個欄位 schema 存在（部分 null 是 Round 1 設計，§6.1 已記）
    assert!(set_parsed.get("per_symbol_drawdown_max_pct").is_some());
    assert!(set_parsed.get("paper_state_recompute_ok").is_some());
    assert!(set_parsed.get("paper_state_balance_history").is_some());

    // Step 6: 推進 1h → on_tick → 仍 paused
    let cleared = pipeline.check_and_clear_halt_expired(t0_set + 60 * 60 * 1000);
    assert!(!cleared, "1h elapse 不該清");
    assert!(pipeline.paper_paused);

    // Step 7-8: 推進 23h+1s（合計 24h+1s） → on_tick → 應 auto-clear
    let cleared = pipeline.check_and_clear_halt_expired(t0_set + ttl_24h + 1000);
    assert!(cleared, "過 24h+1s 應 auto-clear");
    assert_eq!(pipeline.halt_kind, None);
    assert!(!pipeline.paper_paused);
    assert!(!pipeline.session_halted);

    // forensic log auto_cleared 行：用 (halt_set_ts_ms == t0_set + clear_path=auto_ttl)
    // 精確篩出本 test 寫入的 cleared 行，避開併發 test 污染（同 robust parser）。
    let content = std::fs::read_to_string(&halt_log).expect("halt log");
    let clr_parsed = parse_jsonl_robust(&content)
        .into_iter()
        .find(|v| {
            v.get("halt_set_ts_ms").and_then(|s| s.as_u64()) == Some(t0_set)
                && v.get("clear_path").and_then(|c| c.as_str()) == Some("auto_ttl")
        })
        .unwrap_or_else(|| panic!("auto_ttl cleared 行未找到, content={}", content));
    assert_eq!(
        clr_parsed["event"].as_str().unwrap_or(""),
        "halt_session_auto_cleared",
        "MUST-FIX-1：clear_path=auto_ttl 應映射 auto_cleared"
    );
    assert_eq!(clr_parsed["clear_path"].as_str().unwrap_or(""), "auto_ttl");
    let elapsed_ms = clr_parsed["elapsed_ms"].as_u64().unwrap_or(0);
    assert!(
        (86_399_000..=86_401_000).contains(&elapsed_ms),
        "elapsed_ms 應 ∈ [86399000, 86401000] (24h ±1s)；got {}",
        elapsed_ms
    );

    // Step 9-10: 構造 SESSION DRAWDOWN priority 7 halt
    let t1_set = t0_set + ttl_24h + 2000;
    let dd_reason = "SESSION DRAWDOWN: 25.1% >= 25.0%";
    let dd_kind = HaltKind::classify(dd_reason);
    assert_eq!(dd_kind, HaltKind::SessionDrawdown);
    pipeline.halt_kind = Some(dd_kind);
    pipeline.halt_set_ts_ms = t1_set;
    pipeline.paper_paused = true;
    pipeline.session_halted = true;

    // Step 11: 推進 7d
    let cleared = pipeline.check_and_clear_halt_expired(t1_set + 7 * ttl_24h);

    // Step 12: drawdown 三環境永遠 sticky，不管 TTL config
    assert!(!cleared, "drawdown halt 7d 仍 sticky");
    assert!(pipeline.paper_paused);
    assert_eq!(pipeline.halt_kind, Some(HaltKind::SessionDrawdown));

    // Step 13-14: schema_version + 量化欄位 — schema_version=1
    assert_eq!(set_parsed["schema_version"].as_u64().unwrap_or(0), 1);
    assert_eq!(set_parsed["pipeline_kind"].as_str().unwrap_or(""), "paper");

    // cleanup
    let _ = std::fs::remove_file(&halt_log);
    unsafe {
        std::env::remove_var("OPENCLAW_HALT_AUDIT_LOG");
    }
}
