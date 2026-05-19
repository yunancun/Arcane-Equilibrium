//! P0-ENGINE-HALTSESSION-STUCK-FIX (2026-05-19) — halt TTL validate sibling tests。
//! MUST-FIX-4 Round 2：從 `risk_config_tests.rs` 拆出 165 LOC halt TTL 區塊，
//! 否則父檔 2076 LOC 超 CLAUDE.md §九 2000 LOC 硬上限。
//!
//! MODULE_NOTE
//! 模塊用途：守住 `GlobalLimits::validate()` 對 `daily_loss_halt_ttl_ms`
//!   / `drawdown_halt_ttl_ms` 的範圍門檻（0、24h 下限、7d 上限、drawdown
//!   恆 0 sticky），以及 Live/demo/paper 三 TOML production 值驗證。
//! 主要 case：
//!   - test_validate_drawdown_ttl_must_be_zero
//!   - test_validate_daily_loss_ttl_zero_accepted_for_live_sticky
//!   - test_validate_daily_loss_ttl_floor_24h
//!   - test_validate_daily_loss_ttl_24h_accepted
//!   - test_validate_daily_loss_ttl_7d_accepted
//!   - test_validate_daily_loss_ttl_above_7d_rejected
//!   - test_default_global_limits_halt_ttl_defaults
//!   - test_live_daily_loss_sticky_enforcement（MUST-6 / A-9）
//!   - test_demo_paper_daily_loss_ttl_24h
//! 依賴：父 `risk_config` module 的 `RiskConfig` / `GlobalLimits`。
//! 硬邊界：Live `daily_loss_halt_ttl_ms = 0` 為 D1 sticky 強制；
//!   `drawdown_halt_ttl_ms > 0` 必 reject。

use super::*;

#[test]
fn test_validate_drawdown_ttl_must_be_zero() {
    // drawdown_halt_ttl_ms 任何 > 0 即 reject（三環境硬性 sticky）
    let mut cfg = RiskConfig::default();
    cfg.limits.drawdown_halt_ttl_ms = 1000;
    let err = cfg.validate().expect_err("drawdown_halt_ttl_ms > 0 應 reject");
    assert!(
        err.contains("drawdown_halt_ttl_ms"),
        "錯誤訊息應提及 drawdown_halt_ttl_ms；got: {err}"
    );
}

#[test]
fn test_validate_daily_loss_ttl_zero_accepted_for_live_sticky() {
    // Live D1 policy：daily_loss_halt_ttl_ms = 0 = sticky
    let mut cfg = RiskConfig::default();
    cfg.limits.daily_loss_halt_ttl_ms = 0;
    cfg.validate().expect("ttl=0 (Live sticky) 應 OK");
}

#[test]
fn test_validate_daily_loss_ttl_floor_24h() {
    // 0 < ttl < 24h 應 reject（防 immediate re-halt 同 UTC day）
    let mut cfg = RiskConfig::default();
    cfg.limits.daily_loss_halt_ttl_ms = 3_600_000; // 1h
    let err = cfg
        .validate()
        .expect_err("daily_loss_halt_ttl_ms < 24h 應 reject");
    assert!(
        err.contains("daily_loss_halt_ttl_ms"),
        "錯誤訊息應提及 daily_loss_halt_ttl_ms；got: {err}"
    );
}

#[test]
fn test_validate_daily_loss_ttl_24h_accepted() {
    let mut cfg = RiskConfig::default();
    cfg.limits.daily_loss_halt_ttl_ms = 86_400_000; // 24h
    cfg.validate().expect("ttl=24h 應 OK");
}

#[test]
fn test_validate_daily_loss_ttl_7d_accepted() {
    let mut cfg = RiskConfig::default();
    cfg.limits.daily_loss_halt_ttl_ms = 7 * 86_400_000; // 7d
    cfg.validate().expect("ttl=7d 應 OK（上限）");
}

#[test]
fn test_validate_daily_loss_ttl_above_7d_rejected() {
    // 防 misconfig：wall-clock 語意不應跨週
    let mut cfg = RiskConfig::default();
    cfg.limits.daily_loss_halt_ttl_ms = 8 * 86_400_000;
    let err = cfg
        .validate()
        .expect_err("daily_loss_halt_ttl_ms > 7d 應 reject");
    assert!(
        err.contains("daily_loss_halt_ttl_ms"),
        "錯誤訊息應提及 daily_loss_halt_ttl_ms；got: {err}"
    );
}

#[test]
fn test_default_global_limits_halt_ttl_defaults() {
    let l = GlobalLimits::default();
    assert_eq!(l.daily_loss_halt_ttl_ms, 86_400_000, "default daily_loss TTL = 24h");
    assert_eq!(l.drawdown_halt_ttl_ms, 0, "default drawdown TTL = 0 (sticky)");
}

#[test]
fn test_live_daily_loss_sticky_enforcement() {
    // MUST-6：載入 risk_config_live.toml 後驗 ttl=0（sticky D1 policy）
    let candidates = [
        "../../settings/risk_control_rules/risk_config_live.toml",
        "../../../settings/risk_control_rules/risk_config_live.toml",
        "../../../../settings/risk_control_rules/risk_config_live.toml",
    ];
    let mut found = None;
    for c in &candidates {
        let p = std::path::Path::new(c);
        if p.exists() {
            found = Some(p.to_path_buf());
            break;
        }
        // try CARGO_MANIFEST_DIR-relative
        if let Some(manifest) = option_env!("CARGO_MANIFEST_DIR") {
            let p = std::path::Path::new(manifest)
                .join("../../settings/risk_control_rules/risk_config_live.toml");
            if p.exists() {
                found = Some(p);
                break;
            }
        }
    }
    let path = found.expect("找不到 risk_config_live.toml（測試應在 srv/rust/openclaw_engine 下跑）");
    let content = std::fs::read_to_string(&path)
        .unwrap_or_else(|e| panic!("讀 risk_config_live.toml 失敗：{e}"));
    let cfg: RiskConfig =
        toml::from_str(&content).unwrap_or_else(|e| panic!("解析 risk_config_live.toml 失敗：{e}"));
    cfg.validate()
        .expect("risk_config_live.toml 必須通過 validate");
    assert_eq!(
        cfg.limits.daily_loss_halt_ttl_ms, 0,
        "Live D1 policy: daily_loss_halt_ttl_ms 必須 = 0（sticky；operator 人工 RCA）"
    );
    assert_eq!(
        cfg.limits.drawdown_halt_ttl_ms, 0,
        "Live drawdown_halt_ttl_ms 必須 = 0（三環境 sticky）"
    );
}

#[test]
fn test_demo_paper_daily_loss_ttl_24h() {
    // demo / paper：daily_loss_halt_ttl_ms = 86400000（24h wall-clock）
    let candidates = [
        ("risk_config_demo.toml", 86_400_000_u64),
        ("risk_config_paper.toml", 86_400_000_u64),
    ];
    for (fname, expected_ttl) in &candidates {
        let mut found = None;
        for prefix in [
            "../../settings/risk_control_rules/",
            "../../../settings/risk_control_rules/",
            "../../../../settings/risk_control_rules/",
        ] {
            let p = std::path::Path::new(prefix).join(fname);
            if p.exists() {
                found = Some(p);
                break;
            }
        }
        if found.is_none() {
            if let Some(manifest) = option_env!("CARGO_MANIFEST_DIR") {
                let p = std::path::Path::new(manifest)
                    .join("../../settings/risk_control_rules/")
                    .join(fname);
                if p.exists() {
                    found = Some(p);
                }
            }
        }
        let path = found.unwrap_or_else(|| panic!("找不到 {fname}"));
        let content = std::fs::read_to_string(&path)
            .unwrap_or_else(|e| panic!("讀 {fname} 失敗：{e}"));
        let cfg: RiskConfig =
            toml::from_str(&content).unwrap_or_else(|e| panic!("解析 {fname} 失敗：{e}"));
        cfg.validate()
            .unwrap_or_else(|e| panic!("{fname} validate 失敗：{e}"));
        assert_eq!(
            cfg.limits.daily_loss_halt_ttl_ms, *expected_ttl,
            "{fname}: daily_loss_halt_ttl_ms 應為 {expected_ttl}（24h wall-clock）"
        );
        assert_eq!(
            cfg.limits.drawdown_halt_ttl_ms, 0,
            "{fname}: drawdown_halt_ttl_ms 必須 = 0"
        );
    }
}
