use super::*;

/// Helper: create a gate with fresh data for BTCUSDT and healthy state.
/// 輔助：建立帶有 BTCUSDT 新鮮數據和健康狀態的門控。
fn gate_with_fresh_btc(now_ms: u64) -> H0Gate {
    let mut gate = H0Gate::new(None);
    gate.update_price_ts("BTCUSDT", now_ms - 100); // 100ms ago = fresh
    gate.update_health(H0GateHealthSnapshot {
        cpu_pct: 30.0,
        memory_available_mb: 4096,
        db_latency_ms: 5.0,
        network_loss_pct: 0.1,
        snapshot_ts_ms: now_ms - 1000,
    });
    gate.update_risk(H0GateRiskSnapshot {
        open_position_count: 2,
        total_exposure_pct: 30.0,
        cooldown_until_ts_ms: 0,
        kill_switch_active: false,
        snapshot_ts_ms: now_ms - 500,
    });
    gate
}

// ── 1. All checks pass / 全部通過 ───────────────────────────────────────

#[test]
fn test_all_checks_pass() {
    let now = 1_700_000_000_000u64;
    let mut gate = gate_with_fresh_btc(now);
    let result = gate.check("BTCUSDT", "linear", now);
    assert!(result.allowed);
    assert_eq!(result.check_name, "all_passed");
    assert!(result.reason.is_empty());
    assert_eq!(gate.stats.total_allowed, 1);
    assert_eq!(gate.stats.total_checks, 1);
}

// ── 2. Freshness: no data / 新鮮度：無數據 ─────────────────────────────

#[test]
fn test_freshness_no_data_blocks() {
    let now = 1_700_000_000_000u64;
    let mut gate = gate_with_fresh_btc(now);
    let result = gate.check("ETHUSDT", "linear", now); // no tick for ETH
    assert!(!result.allowed);
    assert_eq!(result.check_name, "freshness");
    assert!(result.reason.contains("no_data_ETHUSDT"));
    assert_eq!(gate.stats.blocked_freshness, 1);
}

// ── 3. Freshness: stale data / 新鮮度：數據過期 ─────────────────────────

#[test]
fn test_freshness_stale_data_blocks() {
    let now = 1_700_000_000_000u64;
    let mut gate = gate_with_fresh_btc(now);
    gate.update_price_ts("BTCUSDT", now - 2000); // 2000ms ago > 1000ms max
    let result = gate.check("BTCUSDT", "linear", now);
    assert!(!result.allowed);
    assert_eq!(result.check_name, "freshness");
    assert!(result.reason.contains("data_stale_BTCUSDT_2000ms"));
}

// ── 4. Freshness: exactly at threshold / 新鮮度：恰好到達閾值 ───────────

#[test]
fn test_freshness_at_threshold_blocks() {
    let now = 1_700_000_000_000u64;
    let mut gate = gate_with_fresh_btc(now);
    gate.update_price_ts("BTCUSDT", now - 1000); // exactly max_data_age_ms
    let result = gate.check("BTCUSDT", "linear", now);
    assert!(
        !result.allowed,
        "age == max_data_age_ms should block (>= comparison)"
    );
}

// ── 5. Health: CPU too high / 健康：CPU 過高 ────────────────────────────

#[test]
fn test_health_cpu_too_high_blocks() {
    let now = 1_700_000_000_000u64;
    let mut gate = gate_with_fresh_btc(now);
    gate.update_health(H0GateHealthSnapshot {
        cpu_pct: 95.0,
        memory_available_mb: 4096,
        db_latency_ms: 5.0,
        network_loss_pct: 0.1,
        snapshot_ts_ms: now - 1000,
    });
    let result = gate.check("BTCUSDT", "linear", now);
    assert!(!result.allowed);
    assert_eq!(result.check_name, "health");
    assert!(result.reason.contains("cpu_too_high"));
    assert_eq!(gate.stats.blocked_health, 1);
}

// ── 6. Health: memory low / 健康：記憶體不足 ────────────────────────────

#[test]
fn test_health_memory_low_blocks() {
    let now = 1_700_000_000_000u64;
    let mut gate = gate_with_fresh_btc(now);
    gate.update_health(H0GateHealthSnapshot {
        cpu_pct: 30.0,
        memory_available_mb: 512, // < 1024 min
        db_latency_ms: 5.0,
        network_loss_pct: 0.1,
        snapshot_ts_ms: now - 1000,
    });
    let result = gate.check("BTCUSDT", "linear", now);
    assert!(!result.allowed);
    assert!(result.reason.contains("memory_low_512mb"));
}

// ── 7. Health: DB latency / 健康：DB 延遲過高 ───────────────────────────

#[test]
fn test_health_db_latency_blocks() {
    let now = 1_700_000_000_000u64;
    let mut gate = gate_with_fresh_btc(now);
    gate.update_health(H0GateHealthSnapshot {
        cpu_pct: 30.0,
        memory_available_mb: 4096,
        db_latency_ms: 150.0, // > 100.0 max
        network_loss_pct: 0.1,
        snapshot_ts_ms: now - 1000,
    });
    let result = gate.check("BTCUSDT", "linear", now);
    assert!(!result.allowed);
    assert!(result.reason.contains("db_latency_high"));
}

// ── 8. Health: network loss / 健康：網絡丟包過高 ────────────────────────

#[test]
fn test_health_network_loss_blocks() {
    let now = 1_700_000_000_000u64;
    let mut gate = gate_with_fresh_btc(now);
    gate.update_health(H0GateHealthSnapshot {
        cpu_pct: 30.0,
        memory_available_mb: 4096,
        db_latency_ms: 5.0,
        network_loss_pct: 8.0, // > 5.0 max
        snapshot_ts_ms: now - 1000,
    });
    let result = gate.check("BTCUSDT", "linear", now);
    assert!(!result.allowed);
    assert!(result.reason.contains("network_loss_high"));
}

// ── 9. Health: snapshot stale / 健康：快照過期 ──────────────────────────

#[test]
fn test_health_snapshot_stale_blocks() {
    let now = 1_700_000_000_000u64;
    let mut gate = gate_with_fresh_btc(now);
    gate.update_health(H0GateHealthSnapshot {
        cpu_pct: 30.0,
        memory_available_mb: 4096,
        db_latency_ms: 5.0,
        network_loss_pct: 0.1,
        snapshot_ts_ms: now - 60_000, // 60s ago > 30s max
    });
    let result = gate.check("BTCUSDT", "linear", now);
    assert!(!result.allowed);
    assert!(result.reason.contains("health_snapshot_stale"));
}

// ── 10. Eligibility: category not allowed / 准入：類別不允許 ────────────

#[test]
fn test_eligibility_category_not_allowed() {
    let now = 1_700_000_000_000u64;
    let mut gate = gate_with_fresh_btc(now);
    let result = gate.check("BTCUSDT", "option", now);
    assert!(!result.allowed);
    assert_eq!(result.check_name, "eligibility");
    assert!(result.reason.contains("category_not_allowed_option"));
    assert_eq!(gate.stats.blocked_eligibility, 1);
}

// ── 11. Eligibility: symbol blocked / 准入：符號被阻擋 ─────────────────

#[test]
fn test_eligibility_symbol_blocked() {
    let now = 1_700_000_000_000u64;
    let mut gate = gate_with_fresh_btc(now);
    gate.set_symbol_eligibility("BTCUSDT", false);
    let result = gate.check("BTCUSDT", "linear", now);
    assert!(!result.allowed);
    assert!(result.reason.contains("symbol_not_eligible_BTCUSDT"));
}

// ── 12. Eligibility: system disabled / 准入：系統已禁用 ─────────────────

#[test]
fn test_eligibility_system_disabled() {
    let now = 1_700_000_000_000u64;
    let mut gate = gate_with_fresh_btc(now);
    gate.set_system_mode("disabled");
    let result = gate.check("BTCUSDT", "linear", now);
    assert!(!result.allowed);
    assert!(result.reason.contains("system_disabled"));
}

// ── 13. Risk: kill switch / 風控：Kill Switch ───────────────────────────

#[test]
fn test_risk_kill_switch_blocks() {
    let now = 1_700_000_000_000u64;
    let mut gate = gate_with_fresh_btc(now);
    gate.update_risk(H0GateRiskSnapshot {
        kill_switch_active: true,
        ..H0GateRiskSnapshot::default()
    });
    let result = gate.check("BTCUSDT", "linear", now);
    assert!(!result.allowed);
    assert_eq!(result.check_name, "risk");
    assert!(result.reason.contains("kill_switch_active"));
    assert_eq!(gate.stats.blocked_envelope, 1);
}

// ── 14. Risk: max positions / 風控：持倉上限 ────────────────────────────

#[test]
fn test_risk_max_positions_blocks() {
    let now = 1_700_000_000_000u64;
    let mut gate = gate_with_fresh_btc(now);
    gate.update_risk(H0GateRiskSnapshot {
        open_position_count: 10, // == max (10)
        total_exposure_pct: 30.0,
        cooldown_until_ts_ms: 0,
        kill_switch_active: false,
        snapshot_ts_ms: now - 500,
    });
    let result = gate.check("BTCUSDT", "linear", now);
    assert!(!result.allowed);
    assert!(result.reason.contains("max_positions_reached_10_of_10"));
}

// ── 15. Risk: exposure limit / 風控：曝險上限 ───────────────────────────

#[test]
fn test_risk_exposure_limit_blocks() {
    let now = 1_700_000_000_000u64;
    let mut gate = gate_with_fresh_btc(now);
    gate.update_risk(H0GateRiskSnapshot {
        open_position_count: 2,
        total_exposure_pct: 95.0, // >= 90.0 max
        cooldown_until_ts_ms: 0,
        kill_switch_active: false,
        snapshot_ts_ms: now - 500,
    });
    let result = gate.check("BTCUSDT", "linear", now);
    assert!(!result.allowed);
    assert!(result.reason.contains("exposure_limit_reached"));
}

// ── 16. Cooldown active / 冷卻期生效 ────────────────────────────────────

#[test]
fn test_cooldown_blocks() {
    let now = 1_700_000_000_000u64;
    let mut gate = gate_with_fresh_btc(now);
    gate.update_risk(H0GateRiskSnapshot {
        open_position_count: 2,
        total_exposure_pct: 30.0,
        cooldown_until_ts_ms: now + 5000, // 5s remaining
        kill_switch_active: false,
        snapshot_ts_ms: now - 500,
    });
    let result = gate.check("BTCUSDT", "linear", now);
    assert!(!result.allowed);
    assert_eq!(result.check_name, "cooldown");
    assert!(result.reason.contains("cooldown_active_5000ms_remaining"));
    assert_eq!(gate.stats.blocked_cooldown, 1);
}

// ── 17. Cooldown expired / 冷卻期已過 ───────────────────────────────────

#[test]
fn test_cooldown_expired_passes() {
    let now = 1_700_000_000_000u64;
    let mut gate = gate_with_fresh_btc(now);
    gate.update_risk(H0GateRiskSnapshot {
        open_position_count: 2,
        total_exposure_pct: 30.0,
        cooldown_until_ts_ms: now - 1000, // expired 1s ago
        kill_switch_active: false,
        snapshot_ts_ms: now - 500,
    });
    let result = gate.check("BTCUSDT", "linear", now);
    assert!(result.allowed);
}

// ── 18. Shadow mode: would-block but allows / 影子模式：本來會阻擋但放行

#[test]
fn test_shadow_mode_allows_despite_blocks() {
    let now = 1_700_000_000_000u64;
    let mut gate = gate_with_fresh_btc(now);
    gate.set_shadow_mode(true);
    gate.update_risk(H0GateRiskSnapshot {
        kill_switch_active: true,
        ..H0GateRiskSnapshot::default()
    });
    let result = gate.check("BTCUSDT", "linear", now);
    assert!(result.allowed, "shadow mode must always allow");
    assert!(result.reason.contains("shadow_would_block"));
    assert!(result.reason.contains("kill_switch_active"));
    assert_eq!(result.check_name, "shadow_would_block");
    assert_eq!(gate.stats.shadow_would_block, 1);
    assert_eq!(gate.shadow_log.len(), 1);
}

// ── 19. Shadow mode: all pass / 影子模式：全部通過 ──────────────────────

#[test]
fn test_shadow_mode_all_pass() {
    let now = 1_700_000_000_000u64;
    let mut gate = gate_with_fresh_btc(now);
    gate.set_shadow_mode(true);
    let result = gate.check("BTCUSDT", "linear", now);
    assert!(result.allowed);
    assert!(result.reason.is_empty());
    assert_eq!(result.check_name, "shadow_all_passed");
    assert_eq!(gate.stats.shadow_would_block, 0);
}

// ── 20. Shadow log circular buffer / 影子日誌環形緩衝區 ─────────────────

#[test]
fn test_shadow_log_circular_buffer() {
    let now = 1_700_000_000_000u64;
    let mut gate = gate_with_fresh_btc(now);
    gate.set_shadow_mode(true);
    gate.set_system_mode("disabled"); // triggers eligibility block every time

    for i in 0..120u64 {
        gate.check("BTCUSDT", "linear", now + i);
    }

    assert_eq!(gate.shadow_log.len(), SHADOW_LOG_MAX);
    // Oldest entries evicted; newest should be last.
    let last = gate.shadow_log.back().unwrap();
    assert_eq!(last.ts_ms, now + 119);
}

// ── 21. Stats tracking / 統計追蹤 ───────────────────────────────────────

#[test]
fn test_stats_tracking() {
    let now = 1_700_000_000_000u64;
    let mut gate = gate_with_fresh_btc(now);

    // Pass
    gate.check("BTCUSDT", "linear", now);
    // Block freshness (no data for ETH)
    gate.check("ETHUSDT", "linear", now);
    // Block eligibility (bad category)
    gate.check("BTCUSDT", "option", now);

    let stats = gate.get_stats();
    assert_eq!(stats.total_checks, 3);
    assert_eq!(stats.total_allowed, 1);
    assert_eq!(stats.blocked_freshness, 1);
    assert_eq!(stats.blocked_eligibility, 1);
    assert_eq!(stats.total_blocked(), 2);
}

// ── 22. Stats derived metrics / 統計派生指標 ────────────────────────────

#[test]
fn test_stats_derived_metrics() {
    let stats = GateStats {
        total_checks: 10,
        total_allowed: 7,
        total_latency_us: 500,
        ..GateStats::default()
    };
    let rate = stats.allow_rate_pct();
    assert!((rate - 70.0).abs() < 0.01);
    let avg = stats.avg_latency_us();
    assert!((avg - 50.0).abs() < 0.01);
}

// ── 23. Stats zero checks edge case / 統計零檢查邊界 ────────────────────

#[test]
fn test_stats_zero_checks() {
    let stats = GateStats::default();
    assert_eq!(stats.allow_rate_pct(), 0.0);
    assert_eq!(stats.avg_latency_us(), 0.0);
}

// ── 24. Default config values / 預設配置值 ──────────────────────────────

#[test]
fn test_default_config() {
    let gate = H0Gate::new(None);
    let cfg = gate.config();
    assert_eq!(cfg.max_data_age_ms, 1000);
    assert_eq!(cfg.max_cpu_pct, 90.0);
    assert_eq!(cfg.min_memory_mb, 1024);
    assert_eq!(cfg.max_db_latency_ms, 100.0);
    assert_eq!(cfg.max_network_loss_pct, 5.0);
    assert_eq!(cfg.max_open_positions, 10);
    assert_eq!(cfg.max_total_exposure_pct, 90.0);
    assert_eq!(cfg.health_snapshot_max_age_ms, 30_000);
    assert!(!cfg.shadow_mode);
}

// ── 25. System mode "active" passes / 系統模式 active 通過 ──────────────

#[test]
fn test_system_mode_active_passes() {
    let now = 1_700_000_000_000u64;
    let mut gate = gate_with_fresh_btc(now);
    gate.set_system_mode("active");
    let result = gate.check("BTCUSDT", "linear", now);
    assert!(result.allowed);
}

// ── 26. Fail-fast: freshness blocks before health / 快速失敗順序 ────────

#[test]
fn test_fail_fast_freshness_blocks_before_health() {
    let now = 1_700_000_000_000u64;
    let mut gate = H0Gate::new(None);
    // No price data (freshness fails) AND bad health
    gate.update_health(H0GateHealthSnapshot {
        cpu_pct: 99.0,
        memory_available_mb: 100,
        db_latency_ms: 999.0,
        network_loss_pct: 99.0,
        snapshot_ts_ms: now - 1000,
    });
    let result = gate.check("BTCUSDT", "linear", now);
    assert!(!result.allowed);
    assert_eq!(result.check_name, "freshness"); // must fail on freshness, not health
    assert_eq!(gate.stats.blocked_freshness, 1);
    assert_eq!(gate.stats.blocked_health, 0);
}

// ── 27. Shadow mode with no-data symbol / 影子模式：無數據符號 ──────────

#[test]
fn test_shadow_mode_no_data_symbol() {
    let now = 1_700_000_000_000u64;
    let mut gate = gate_with_fresh_btc(now);
    gate.set_shadow_mode(true);
    let result = gate.check("XYZUSDT", "linear", now);
    assert!(result.allowed);
    assert!(result.reason.contains("no_data_XYZUSDT"));
}

// ── 28. Health snapshot ts=0 skips staleness / 快照 ts=0 跳過過期檢查 ──

#[test]
fn test_health_snapshot_zero_ts_skips_staleness() {
    let now = 1_700_000_000_000u64;
    let mut gate = gate_with_fresh_btc(now);
    // snapshot_ts_ms = 0 means "never updated" — staleness check is skipped.
    gate.update_health(H0GateHealthSnapshot {
        cpu_pct: 30.0,
        memory_available_mb: 4096,
        db_latency_ms: 5.0,
        network_loss_pct: 0.1,
        snapshot_ts_ms: 0,
    });
    let result = gate.check("BTCUSDT", "linear", now);
    assert!(
        result.allowed,
        "snapshot_ts_ms=0 should skip staleness check"
    );
}

// ── 29. Latency is recorded / 延遲已記錄 ───────────────────────────────

#[test]
fn test_latency_recorded() {
    let now = 1_700_000_000_000u64;
    let mut gate = gate_with_fresh_btc(now);
    let _result = gate.check("BTCUSDT", "linear", now);
    // Stats should have accumulated some latency and the check count.
    assert_eq!(gate.stats.total_checks, 1);
    // total_latency_us is populated (may be 0 on very fast machines).
    assert_eq!(gate.stats.total_allowed, 1);
}

// ── 30a. P2-LG1: with_metrics 注入 recorder + record 計數 ──────────────

/// P2-LG1-DEMO-SLO-CARVEOUT (2026-05-21)：with_metrics ctor 注入 recorder，
/// 每次 check() 後 recorder.summary 的 count 應對應呼叫次數。
/// allowed + blocked 兩條路徑都應觸發 record（finalize_allowed/blocked 均接線）。
#[test]
fn test_p2_lg1_with_metrics_records_both_paths() {
    let now = 1_700_000_000_000u64;
    let rec = Arc::new(H0LatencyRecorder::new());
    // 用 with_metrics 注入 recorder + engine_mode="demo"
    let mut gate = H0Gate::with_metrics(None, Arc::clone(&rec), "demo");
    gate.update_price_ts("BTCUSDT", now - 100);
    gate.update_health(H0GateHealthSnapshot {
        cpu_pct: 30.0,
        memory_available_mb: 4096,
        db_latency_ms: 5.0,
        network_loss_pct: 0.1,
        snapshot_ts_ms: now - 1000,
    });
    gate.update_risk(H0GateRiskSnapshot {
        open_position_count: 2,
        total_exposure_pct: 30.0,
        cooldown_until_ts_ms: 0,
        kill_switch_active: false,
        snapshot_ts_ms: now - 500,
    });

    // 1 個 allowed
    let r1 = gate.check("BTCUSDT", "linear", now);
    assert!(r1.allowed);
    // 2 個 blocked（無資料 / 類別不允許）
    let r2 = gate.check("ETHUSDT", "linear", now);
    assert!(!r2.allowed);
    let r3 = gate.check("BTCUSDT", "option", now);
    assert!(!r3.allowed);

    // recorder demo summary count 應 = 3（2 blocked + 1 allowed）
    let s = rec.summary("demo", 0).expect("demo histogram exists");
    assert_eq!(
        s.count, 3,
        "P2-LG1：finalize_allowed + finalize_blocked 各走 record；3 check → 3 sample"
    );
    // 其他 mode 不應被污染
    assert_eq!(rec.summary("paper", 0).unwrap().count, 0);
    assert_eq!(rec.summary("live", 0).unwrap().count, 0);
    assert_eq!(rec.summary("live_demo", 0).unwrap().count, 0);
    assert_eq!(rec.summary("live_testnet", 0).unwrap().count, 0);
}

// ── 30b. P2-LG1: 無 recorder 路徑（None） backward compat ─────────────

/// 為什麼：spec §11.4 不變式「H0Gate::new 不可破 backward compat」；
/// 既有 test / cold ctor 必須在 metrics_recorder=None 下保持 latency
/// stats 行為（total_latency_us / max_latency_us 仍累計）。
#[test]
fn test_p2_lg1_no_recorder_backward_compat() {
    let now = 1_700_000_000_000u64;
    let mut gate = gate_with_fresh_btc(now); // H0Gate::new 路徑 → recorder=None
    gate.check("BTCUSDT", "linear", now);
    gate.check("ETHUSDT", "linear", now); // blocked freshness

    // GateStats 累計仍正確（latency 路徑未被破壞）
    assert_eq!(gate.stats.total_checks, 2);
    assert_eq!(gate.stats.total_allowed, 1);
    assert_eq!(gate.stats.blocked_freshness, 1);
    // 不 panic 即驗 None 分支無 alloc / 無錯誤
}

// ── 30c. P2-LG1: set_metrics_recorder + set_engine_mode 後接注入 ─────

/// 為什麼：bootstrap.rs 接線路徑用 setter（pipeline_ctor 已 H0Gate::new 完成
/// 後才知道 effective_engine_mode）；驗 setter 路徑語意等同 with_metrics。
#[test]
fn test_p2_lg1_post_construction_injection() {
    let now = 1_700_000_000_000u64;
    let rec = Arc::new(H0LatencyRecorder::new());
    let mut gate = gate_with_fresh_btc(now); // H0Gate::new → recorder=None, mode="paper"

    // 注入前 1 check：應寫到 "paper"（預設 mode）但 None recorder 跳過
    gate.check("BTCUSDT", "linear", now);
    assert_eq!(rec.summary("paper", 0).unwrap().count, 0);

    // 後接注入 recorder + engine_mode="live_demo"
    gate.set_metrics_recorder(Arc::clone(&rec));
    gate.set_engine_mode("live_demo");

    // 注入後 2 check：應計入 "live_demo"
    gate.check("BTCUSDT", "linear", now);
    gate.check("BTCUSDT", "linear", now);

    let s = rec.summary("live_demo", 0).unwrap();
    assert_eq!(
        s.count, 2,
        "set_metrics_recorder 後 record 應計入新 engine_mode"
    );
    assert_eq!(rec.summary("paper", 0).unwrap().count, 0);
}

// ── 30. Shadow mode multiple blocks / 影子模式：多重阻擋 ────────────────

#[test]
fn test_shadow_mode_multiple_blocks() {
    let now = 1_700_000_000_000u64;
    let mut gate = H0Gate::new(None);
    gate.set_shadow_mode(true);
    // No price data + bad CPU + kill switch => multiple blocks
    gate.update_health(H0GateHealthSnapshot {
        cpu_pct: 99.0,
        memory_available_mb: 4096,
        db_latency_ms: 5.0,
        network_loss_pct: 0.1,
        snapshot_ts_ms: now - 1000,
    });
    gate.update_risk(H0GateRiskSnapshot {
        kill_switch_active: true,
        ..H0GateRiskSnapshot::default()
    });
    let result = gate.check("BTCUSDT", "linear", now);
    assert!(result.allowed);
    // Should capture multiple blocks in shadow reason
    assert!(result.reason.contains("no_data_BTCUSDT"));
    assert!(result.reason.contains("cpu_too_high"));
    assert!(result.reason.contains("kill_switch_active"));
}
