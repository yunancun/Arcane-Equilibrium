// LG1-T1 sibling：H0 Blocking Production Caller E2E integration test。
//
// MODULE_NOTE：
//   本檔由 Wave 2.2 LG1-T1（2026-05-11）新增。對應 PA tech plan
//   `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--lg_2_3_4_design_plan.md`
//   §1.4 LG1-T1。覆蓋 P0-LG-1 LG-2 RFC §Target State proof：
//
//     1. H0 hard-block 時 lease consumption 必 = 0（PA §1.5 risk #2 mitigation）
//     2. H0 hard-block 時 intent 不進 step_4_5_dispatch（recent_intents 空）
//     3. H0 shadow 模式：intent 仍可派發（only log）
//     4. H0 check latency p99 < 1ms（PA §1.5 risk #5 / CLAUDE.md §五 SLA）
//     5. ctor default(shadow=true) → IPC set_shadow_mode(false) 後 race 不變
//     6. H0 hard-block 路徑仍 emit canary record（observability 不失）
//
//   邊界：本檔僅做 test 範圍；H0 production code（h0_gate.rs / step_0_5）
//   不動；pipeline_ctor.rs 也不動（T3 範疇）。

use super::super::*;
use std::time::Instant;

// ─────────────────────────────────────────────────────────────────────────────
// Helpers / 測試輔助
// ─────────────────────────────────────────────────────────────────────────────

/// 取得 pipeline 內 H0Gate snapshot 計數（總 check / 已通過 / 已 hard-block）。
/// 用 GateStats 的不可變欄位，避免測試端訪問 private state。
fn gate_summary(pipeline: &TickPipeline) -> (u64, u64, u64) {
    let s = pipeline.h0_gate.get_stats();
    (s.total_checks, s.total_allowed, s.total_blocked())
}

/// 構造 paper pipeline；LG1-T3 後 ctor 預設 `shadow_mode = false`（hard-block），
/// 因此本 helper 無需再翻 flag — 對齊 demo/live TOML 載入後的穩態行為。
/// 保留 helper 名稱以表達語意（test 想做的是「hard-block 模式」）。
fn pipeline_in_hard_block_mode(symbol: &str) -> TickPipeline {
    let pipeline = TickPipeline::new(&[symbol]);
    // 不變式：LG1-T3 後 ctor 預設必為 false（hard-block）。若未來重構回 true，
    // 此 assertion 立即把測試打回，防呆。
    debug_assert!(
        !pipeline.h0_gate.config().shadow_mode,
        "LG1-T3 contract: ctor default `h0_gate.shadow_mode` must be false"
    );
    pipeline
}

/// 觸發 H0 hard-block 的便利 helper：把 risk envelope kill switch 翻起來。
/// step_0_5_h0_gate 在 tick 開頭呼 `update_price_ts` → freshness 必 fresh；
/// health 預設健康；eligibility category="linear" pass。最乾淨觸發 H0 hard-block
/// 的場景 = `kill_switch_active=true`（risk envelope sub-check 拒）。
/// 這也對齊 production 真實 H0 block 場景：governance cascade 拉高 kill switch。
fn trigger_kill_switch(pipeline: &mut TickPipeline, now_ms: u64) {
    pipeline.h0_gate.update_risk(openclaw_types::H0GateRiskSnapshot {
        open_position_count: 0,
        total_exposure_pct: 0.0,
        cooldown_until_ts_ms: 0,
        kill_switch_active: true, // ← H0 risk_envelope 必拒
        snapshot_ts_ms: now_ms - 500,
    });
}

// ─────────────────────────────────────────────────────────────────────────────
// 1. H0 hard-block → lease consumption = 0 不變式
// PA §1.5 risk #2 mitigation：H0 是 pre-lease，lease consumption 必 0
// ─────────────────────────────────────────────────────────────────────────────

/// 不變式 1：H0 hard-block 路徑下 `governance.lease.lock().len()` 必 = 0。
/// 不變式 reason：H0 在 step_0_5 早退（ControlFlow::Break），完全不進 step_4_5；
/// step_4_5_dispatch 才呼 `acquire_lease`，因此 lease store 不會被推任何條目。
///
/// 觸發路徑：kill_switch_active=true → risk_envelope sub-check 拒。
/// 這對應 production 真實場景（GovernanceCore cascade 拉高 kill switch
/// → H0 risk snapshot 同步 → 後續所有 tick 被 H0 hard-block）。
#[test]
fn test_h0_hard_block_zero_lease_consumption() {
    let now_ms = 1_700_000_000_000u64;
    let mut pipeline = pipeline_in_hard_block_mode("BTCUSDT");
    trigger_kill_switch(&mut pipeline, now_ms);

    // 初始 lease store 必空。
    assert_eq!(
        pipeline.governance.lease.lock().len(),
        0,
        "初始 lease store 必為空 / initial lease store must be empty"
    );

    let event = super::make_event("BTCUSDT", 50_000.0, now_ms);
    let _ = pipeline.on_tick(&event);

    // 不變式：H0 hard-block 後 lease store 仍 = 0。
    assert_eq!(
        pipeline.governance.lease.lock().len(),
        0,
        "H0 hard-block 後 lease store 必仍 = 0（intent 從未進 dispatch）/ \
         H0 hard-block must leave lease store at 0"
    );

    // 證明 H0 確實 hard-block 了：stats counter 必 +1（blocked_envelope）。
    let (total, allowed, blocked) = gate_summary(&pipeline);
    assert_eq!(total, 1, "H0 必 check 過 1 次 / H0 must have run once");
    assert_eq!(allowed, 0, "hard-block 模式下不能 allow / hard-block must not allow");
    assert_eq!(blocked, 1, "必 +1 blocked / must increment blocked");
    assert_eq!(
        pipeline.h0_gate.get_stats().blocked_envelope,
        1,
        "kill_switch 屬 risk_envelope category / kill_switch counts as risk_envelope"
    );
}

// ─────────────────────────────────────────────────────────────────────────────
// 2. H0 hard-block → intent 不進 dispatch（recent_intents 空）
// ─────────────────────────────────────────────────────────────────────────────

/// 不變式 2：H0 hard-block 早退後，本 tick 不可能有 intent 進 step_4_5_dispatch。
/// 驗 `recent_intents` 仍空 + `recent_fills` 仍空。
#[test]
fn test_h0_hard_block_intent_not_dispatched() {
    let now_ms = 1_700_000_000_000u64;
    let mut pipeline = pipeline_in_hard_block_mode("BTCUSDT");
    trigger_kill_switch(&mut pipeline, now_ms);

    let event = super::make_event("BTCUSDT", 50_000.0, now_ms);
    let _ = pipeline.on_tick(&event);

    assert_eq!(
        pipeline.recent_intents.len(),
        0,
        "hard-block 後 recent_intents 必為空 / recent_intents must be empty after hard-block"
    );
    assert_eq!(
        pipeline.recent_fills.len(),
        0,
        "hard-block 後 recent_fills 必為空 / recent_fills must be empty after hard-block"
    );

    // paper_state 餘額未變（沒下單 / 沒費用）。
    assert!(
        (pipeline.paper_state.balance() - 10_000.0).abs() < 1e-9,
        "balance 必未變 / balance must remain unchanged"
    );
    assert_eq!(
        pipeline.paper_state.position_count(),
        0,
        "position_count 必為 0 / position_count must stay 0"
    );

    // 強驗證：H0 確實命中 risk_envelope，不是漏 trigger。
    assert_eq!(
        pipeline.h0_gate.get_stats().blocked_envelope, 1,
        "必 +1 blocked_envelope / blocked_envelope must increment"
    );
}

// ─────────────────────────────────────────────────────────────────────────────
// 3. H0 shadow 模式：blocks 不 hard-block，僅記錄 would-block
// ─────────────────────────────────────────────────────────────────────────────

/// 不變式 3：shadow 模式下，即使 5 sub-check 任一失敗，H0 也不 hard-block。
/// allowed=true 仍回，dispatch path 仍進得去。
/// 此測對應 paper TOML 預設（`h0_shadow_mode=true`）的 production 場景。
/// LG1-T3 之後 ctor 預設改為 false（hard-block），shadow 需 explicit flip。
#[test]
fn test_h0_shadow_mode_does_not_hard_block() {
    let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
    // LG1-T3 後 ctor default = false；explicit 翻為 shadow=true 模擬 paper TOML
    // 載入後 apply_risk_snapshot RMW 覆蓋（pipeline_config.rs:97-109）的結果。
    pipeline.h0_gate.set_shadow_mode(true);
    assert!(
        pipeline.h0_gate.config().shadow_mode,
        "explicit flip 後 shadow_mode 必為 true / shadow_mode must be true after flip"
    );

    // 觸發 H0 在 shadow 模式下「本應 block」：kill_switch_active=true。
    let now_ms = 1_700_000_000_000u64;
    trigger_kill_switch(&mut pipeline, now_ms);

    let event = super::make_event("BTCUSDT", 50_000.0, now_ms);
    let _ = pipeline.on_tick(&event);

    let stats = pipeline.h0_gate.get_stats();
    // shadow 模式下：total_allowed +1（即使 would-block 仍 allow），
    // total_blocked = 0（hard-block 計數不動），shadow_would_block +1。
    assert_eq!(stats.total_checks, 1);
    assert_eq!(
        stats.total_allowed, 1,
        "shadow 模式下必 +1 allowed / shadow mode must always increment allowed"
    );
    assert_eq!(
        stats.total_blocked(),
        0,
        "shadow 模式下必 0 hard-block / shadow mode must have 0 hard-block"
    );
    assert!(
        stats.shadow_would_block >= 1,
        "shadow_would_block 必 +1（kill_switch_active → risk_envelope would-block）/ \
         shadow_would_block must increment (kill_switch triggers would-block)"
    );
}

// ─────────────────────────────────────────────────────────────────────────────
// 4. H0 check p99 latency < 1ms（PA §1.5 risk #5 SLA）
// ─────────────────────────────────────────────────────────────────────────────

/// 不變式 4：H0 check 在 release build 下 10k iter p99 < 1ms。
/// 直接量 `h0_gate.check()` 不包含 step_0_5 stop processing，純門控延遲。
/// 警告：debug build 下可能高，此 test 強制 release build profile 才執行 perf
/// assertion（`#[cfg(not(debug_assertions))]`）。在 debug build 跑時跳過 perf
/// 但仍驗 stats 累積正確。
#[test]
fn test_h0_check_p99_latency_under_1ms() {
    let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
    // 預先填 health + risk snapshot，避免每 iter trigger no_data fail（保證走
    // 5 sub-check 完整路徑而非短路 freshness）。
    let now_ms = 1_700_000_000_000u64;
    pipeline.h0_gate.set_shadow_mode(false);
    pipeline.h0_gate.update_health(openclaw_types::H0GateHealthSnapshot {
        cpu_pct: 30.0,
        memory_available_mb: 4096,
        db_latency_ms: 5.0,
        network_loss_pct: 0.1,
        snapshot_ts_ms: now_ms - 1_000,
    });
    pipeline.h0_gate.update_risk(openclaw_types::H0GateRiskSnapshot {
        open_position_count: 0,
        total_exposure_pct: 0.0,
        cooldown_until_ts_ms: 0,
        kill_switch_active: false,
        snapshot_ts_ms: now_ms - 500,
    });
    pipeline.h0_gate.update_price_ts("BTCUSDT", now_ms - 100);

    const N: usize = 10_000;
    let mut latencies_us: Vec<u128> = Vec::with_capacity(N);
    for i in 0..N {
        let ts = now_ms + (i as u64);
        // 同步 price_ts 防止 freshness drift。
        pipeline.h0_gate.update_price_ts("BTCUSDT", ts - 50);
        let start = Instant::now();
        let result = pipeline.h0_gate.check("BTCUSDT", "linear", ts);
        let elapsed = start.elapsed().as_micros();
        latencies_us.push(elapsed);
        assert!(result.allowed, "10k iter 必全 allow / 10k iter must all allow");
    }

    // 算 p99：sort asc → idx 9900。
    latencies_us.sort_unstable();
    let p99_us = latencies_us[(N as f64 * 0.99) as usize];
    let max_us = *latencies_us.last().unwrap();
    let mean_us = (latencies_us.iter().sum::<u128>() as f64) / (N as f64);

    eprintln!(
        "[H0 latency 10k iter] mean={:.2}us p99={}us max={}us",
        mean_us, p99_us, max_us
    );

    // GateStats 累積必正確：total_checks +N + total_allowed +N。
    // 注意：max_latency_us 在 release build 可能因每 iter <1us 飽和為 0；不能
    // assert >0（H0Gate finalize 用 micros 解析度，0 是合法值），但 total_checks
    // 累積一定正確。
    let stats_total = pipeline.h0_gate.get_stats().total_checks;
    assert!(
        stats_total >= N as u64,
        "GateStats.total_checks 必累積 ≥ {N} / total_checks must accumulate"
    );

    // p99 perf assertion 僅在 release build 跑（debug build 開銷大，會 false-fail）。
    #[cfg(not(debug_assertions))]
    {
        assert!(
            p99_us < 1_000,
            "H0 check p99 must be <1ms; got {p99_us}us (release build, PA §1.5 risk #5 SLA)"
        );
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// 5. H0 shadow → hard-block flip 同 symbol race 不變
// PA §1.5 risk #1 mitigation：ctor default shadow=true vs 載入後 demo TOML
// shadow=false 啟動瞬窗（1-3s）H0 行為的 race。本 test 模擬 IPC flip 順序。
// ─────────────────────────────────────────────────────────────────────────────

/// 不變式 5：flip set_shadow_mode 後，下一個 tick 必依新 shadow 值 dispatch。
/// 前一個 tick（flip 前）按舊值 dispatch；flip 是原子的，無中間狀態洩漏。
#[test]
fn test_h0_shadow_to_hardblock_race_safe() {
    let now_ms = 1_700_000_000_000u64;
    let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
    // 第一階段：LG1-T3 後 ctor default = false（hard-block）。手動翻為 shadow=true
    // 模擬 paper TOML 載入後 apply_risk_snapshot RMW 覆蓋的中間狀態。
    pipeline.h0_gate.set_shadow_mode(true);
    assert!(pipeline.h0_gate.config().shadow_mode);

    // 同時觸發 risk_envelope（kill_switch=true）：shadow 階段必 record
    // shadow_would_block，hard 階段必 record blocked。
    trigger_kill_switch(&mut pipeline, now_ms);

    let _ = pipeline.on_tick(&super::make_event("BTCUSDT", 50_000.0, now_ms));

    let stats_pre = pipeline.h0_gate.get_stats().clone();
    assert_eq!(stats_pre.total_allowed, 1, "shadow phase: must allow");
    assert_eq!(stats_pre.total_blocked(), 0, "shadow phase: 0 hard-block");
    assert_eq!(stats_pre.shadow_would_block, 1, "shadow phase: would_block +1");

    // 第二階段：IPC patch flip → shadow=false（demo TOML 載入語意）。
    pipeline.h0_gate.set_shadow_mode(false);
    assert!(!pipeline.h0_gate.config().shadow_mode);

    // 再送一個同 symbol tick → 必 hard-block。
    let _ = pipeline.on_tick(&super::make_event("BTCUSDT", 50_001.0, now_ms + 1));

    let stats_post = pipeline.h0_gate.get_stats();
    assert_eq!(stats_post.total_checks, 2, "post flip: total_checks=2");
    assert_eq!(
        stats_post.total_allowed, 1,
        "post flip: allowed 不再 +1（hard-block 後）/ allowed must not increment after hard-block"
    );
    assert_eq!(
        stats_post.total_blocked(),
        1,
        "post flip: hard-block +1 / hard-block must increment"
    );
    assert_eq!(
        stats_post.shadow_would_block, 1,
        "post flip: shadow_would_block 不增（已 hard-block）/ shadow_would_block must not increment after flip"
    );

    // lease store 兩階段都必 = 0。
    assert_eq!(
        pipeline.governance.lease.lock().len(),
        0,
        "整個 race 流程：lease store 永遠 = 0 / lease store must stay 0 across flip"
    );
}

// ─────────────────────────────────────────────────────────────────────────────
// 6. H0 hard-block + canary record observability 不變式
// ─────────────────────────────────────────────────────────────────────────────

/// 不變式 6：H0 hard-block 路徑下，canary_mode=true 時仍 emit CanaryRecord
/// （observability 不失）；record.order_intents 必空。
/// 這是 LG-2 RFC 「audit log entry written」的 minimal proof。
#[test]
fn test_h0_hard_block_emits_canary_record_with_no_intents() {
    let now_ms = 1_700_000_000_000u64;
    let mut pipeline = pipeline_in_hard_block_mode("BTCUSDT");
    pipeline.canary_mode = true;
    trigger_kill_switch(&mut pipeline, now_ms);

    let event = super::make_event("BTCUSDT", 50_000.0, now_ms);
    let record = pipeline.on_tick(&event);

    // canary record 必存在。
    assert!(
        record.is_some(),
        "canary_mode=true 時 hard-block tick 必 emit record / canary record must be emitted"
    );
    let r = record.unwrap();
    assert_eq!(r.schema_version, "1.0.0");
    assert_eq!(r.symbol, "BTCUSDT");
    // hard-block 路徑：order_intents 必空（沒進 dispatch）。
    assert!(
        r.order_intents.is_empty(),
        "hard-block 路徑 order_intents 必空 / hard-block must produce empty order_intents"
    );
    // signals 也必空（hard-block 路徑只走 stops，不跑 signal evaluation）。
    assert!(
        r.signals.is_empty(),
        "hard-block 路徑 signals 必空 / hard-block must produce empty signals"
    );

    // 整體不變式：lease store + recent_intents + recent_fills 全 = 0。
    assert_eq!(pipeline.governance.lease.lock().len(), 0);
    assert_eq!(pipeline.recent_intents.len(), 0);
    assert_eq!(pipeline.recent_fills.len(), 0);
}
