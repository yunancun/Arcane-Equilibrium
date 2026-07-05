// MODULE_NOTE
// 模塊用途：F-D6-1 dynamic_sizing band snapshot 測試。鎖死三環境 risk_config*.toml
//   的 [dynamic_sizing] band [min_pct, max_pct] 與 base per_trade_risk_pct 的關係,
//   並守衛 band 兩端落在 SSOT bounds [MIN_PER_TRADE_RISK_PCT, MAX_PER_TRADE_RISK_PCT] 內。
// 主要測試：demo band 含 base(F-D6-1 operator 2026-07-05 裁定擴 band 後的守衛)、
//   三環境 band 皆在 SSOT bounds 內、band 排序合法(min<max)。
// 依賴：settings/risk_control_rules/risk_config_{demo,paper,live}.toml、
//   config::risk_config::{RiskConfig, MIN_PER_TRADE_RISK_PCT, MAX_PER_TRADE_RISK_PCT}。
// 硬邊界：本測試只讀 TOML,不改值;dynamic_sizing 是 agent HardBoundary(applier 否決),
//   band 值僅 operator 手動改 TOML 可動。
//
// 背景（F-D6-1，冷審計 R2）：demo band 原為 [0.01, 0.05],不含 base
// per_trade_risk_pct=0.1 → agent 首次動態調整就被 clamp 到 0.05(等效砍半)。
// operator 2026-07-05 裁定擴 demo band 上限至 0.10,使 band [0.01, 0.10] 含 base,
// 仍在 SSOT bounds [0.001, 0.20] 內。此測試把「band 含 base」釘為 demo 的守衛;
// 之前 E5 D6 報告 §4.4 計劃的「記錄現狀(band 不含 base)」snapshot 從未落地,
// 本測試直接落地裁定後的正確斷言,不依賴 D6 refactor 其餘部分(UNIT_TABLE 等)。

// 本 sibling 經 risk_config.rs 的 `#[path] mod` 掛在 crate::config::risk_config 模塊下,
// 故 super = 該模塊,RiskConfig 與 SSOT bound 常量皆同模塊直接可見。
use super::{RiskConfig, MAX_PER_TRADE_RISK_PCT, MIN_PER_TRADE_RISK_PCT};
use std::path::PathBuf;

fn load_toml(fname: &str) -> RiskConfig {
    // CARGO_MANIFEST_DIR=srv/rust/openclaw_engine,往上兩層=srv/。
    let crate_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let repo_root = crate_root
        .parent()
        .and_then(|p| p.parent())
        .expect("srv root")
        .to_path_buf();
    let path = repo_root
        .join("settings")
        .join("risk_control_rules")
        .join(fname);
    let content =
        std::fs::read_to_string(&path).unwrap_or_else(|e| panic!("read {}: {}", path.display(), e));
    toml::from_str(&content).unwrap_or_else(|e| panic!("parse {}: {}", fname, e))
}

#[test]
fn test_f_d6_1_demo_dynamic_sizing_band_contains_base() {
    // F-D6-1(operator 2026-07-05 裁定擴 band):demo band 必須含 base,否則 agent
    // 首次調整就被 clamp 砍半。斷言 min_pct <= per_trade_risk_pct <= max_pct。
    let cfg = load_toml("risk_config_demo.toml");
    let base = cfg.limits.per_trade_risk_pct;
    let band = &cfg.dynamic_sizing;
    assert!(
        band.min_pct <= base && base <= band.max_pct,
        "demo dynamic_sizing band [{}, {}] must contain base per_trade_risk_pct={} \
         (F-D6-1 operator 2026-07-05 裁定擴 band 至含 base)",
        band.min_pct,
        band.max_pct,
        base
    );
    // 釘死裁定後的具體 band 值,防未來人靜默改回不含 base 的 [0.01, 0.05]。
    assert_eq!(band.min_pct, 0.01, "demo dynamic_sizing.min_pct 應為 0.01");
    assert_eq!(band.max_pct, 0.10, "demo dynamic_sizing.max_pct 應為 0.10(F-D6-1 擴後)");
}

#[test]
fn test_oos6_live_dynamic_sizing_band_contains_base() {
    // OOS-6(operator 2026-07-05 裁定 A,意圖 live 5%):live band 擴上限至 0.05 後
    // 必須含 base per_trade_risk_pct=0.05,否則 sizer 首次調整就被 clamp。
    let cfg = load_toml("risk_config_live.toml");
    let base = cfg.limits.per_trade_risk_pct;
    let band = &cfg.dynamic_sizing;
    assert!(
        band.min_pct <= base && base <= band.max_pct,
        "live dynamic_sizing band [{}, {}] must contain base per_trade_risk_pct={} \
         (OOS-6 operator 2026-07-05 裁定 A 擴 band 上限至 0.05)",
        band.min_pct,
        band.max_pct,
        base
    );
    // 釘死裁定後的具體上限,防未來人靜默改回不含 base 的 0.03。
    assert_eq!(band.min_pct, 0.005, "live dynamic_sizing.min_pct 應為 0.005");
    assert_eq!(band.max_pct, 0.05, "live dynamic_sizing.max_pct 應為 0.05(OOS-6 擴後)");
}

#[test]
fn test_dynamic_sizing_band_contains_base_all_enabled_envs() {
    // OOS-6 ③:把「band 含 base」斷言從 demo-only 擴到三環境。守 enabled gate:
    // 僅 enabled=true 的環境要求 band 含 base(paper enabled=false 且 base=0.20
    // 天然不含 dormant 預設 band,故豁免——與 RiskConfig::validate() 的豁免同語意)。
    for fname in [
        "risk_config_demo.toml",
        "risk_config_paper.toml",
        "risk_config_live.toml",
    ] {
        let cfg = load_toml(fname);
        let base = cfg.limits.per_trade_risk_pct;
        let band = &cfg.dynamic_sizing;
        if !band.enabled {
            continue; // dynamic_sizing 停用 → 未接 runtime,豁免 band 含 base
        }
        assert!(
            band.min_pct <= base && base <= band.max_pct,
            "{}: enabled dynamic_sizing band [{}, {}] must contain base \
             per_trade_risk_pct={}",
            fname,
            band.min_pct,
            band.max_pct,
            base
        );
    }
}

#[test]
fn test_all_env_toml_pass_validate() {
    // OOS-6 ②/③:三環境 real toml 過 RiskConfig::validate()(含新加的 band-contains-base
    // fail-closed 斷言)必須綠。若哪個環境 band 不含 base 且 enabled,此處會紅。
    for fname in [
        "risk_config_demo.toml",
        "risk_config_paper.toml",
        "risk_config_live.toml",
    ] {
        let cfg = load_toml(fname);
        assert!(
            cfg.validate().is_ok(),
            "{}: validate() must pass, got {:?}",
            fname,
            cfg.validate()
        );
    }
}

#[test]
fn test_validate_rejects_enabled_band_not_containing_base() {
    // OOS-6 ② 紅→綠:構造 band 不含 base + enabled=true 的 config,validate() 必須
    // Err(現碼在此改動前是靜默過,由 sizer runtime clamp)。此為 fail-closed 護欄的
    // 直接證明:max_pct < base(band 上限低於 base)→ 拒絕。
    let mut cfg = RiskConfig::default();
    cfg.dynamic_sizing.enabled = true;
    cfg.limits.per_trade_risk_pct = 0.05;
    // 把 max_pct 壓到 base 之下,使 band [0.01, 0.03] 不含 base 0.05。
    cfg.dynamic_sizing.max_pct = 0.03;
    let err = cfg
        .validate()
        .expect_err("enabled band [0.01,0.03] not containing base 0.05 must be rejected");
    assert!(
        err.contains("dynamic_sizing band") && err.contains("must contain base"),
        "error 應指出 band 不含 base,實得: {}",
        err
    );

    // 對稱情況:min_pct 抬到 base 之上(band 下限高於 base)也須拒絕。
    let mut cfg2 = RiskConfig::default();
    cfg2.dynamic_sizing.enabled = true;
    cfg2.limits.per_trade_risk_pct = 0.005;
    cfg2.dynamic_sizing.min_pct = 0.01; // band [0.01, 0.05] 不含 base 0.005
    assert!(
        cfg2.validate().is_err(),
        "enabled band [0.01,0.05] not containing base 0.005 must be rejected"
    );
}

#[test]
fn test_validate_exempts_disabled_band_not_containing_base() {
    // OOS-6 ②:paper 語意——enabled=false 時即使 band 不含 base 也豁免(dynamic_sizing
    // 未接 runtime,不影響下單)。此為 fail-closed 護欄不誤殺 dormant 配置的證明。
    let mut cfg = RiskConfig::default();
    cfg.dynamic_sizing.enabled = false;
    cfg.limits.per_trade_risk_pct = 0.20; // 與 paper 同:base 在 dormant band 之外
    cfg.dynamic_sizing.min_pct = 0.01;
    cfg.dynamic_sizing.max_pct = 0.05; // band [0.01,0.05] 不含 base 0.20
    assert!(
        cfg.validate().is_ok(),
        "disabled dynamic_sizing must be exempt from band-contains-base, got {:?}",
        cfg.validate()
    );
}

#[test]
fn test_dynamic_sizing_band_within_ssot_bounds_all_envs() {
    // 三環境 band 兩端皆須落在 SSOT bounds [MIN_PER_TRADE_RISK_PCT, MAX_PER_TRADE_RISK_PCT]
    // 內,且 min<max(排序合法)。此為 band 值任何未來改動的護欄。
    for fname in [
        "risk_config_demo.toml",
        "risk_config_paper.toml",
        "risk_config_live.toml",
    ] {
        let cfg = load_toml(fname);
        let band = &cfg.dynamic_sizing;
        assert!(
            band.min_pct < band.max_pct,
            "{}: dynamic_sizing.min_pct {} 必 < max_pct {}",
            fname,
            band.min_pct,
            band.max_pct
        );
        assert!(
            (MIN_PER_TRADE_RISK_PCT..=MAX_PER_TRADE_RISK_PCT).contains(&band.min_pct),
            "{}: dynamic_sizing.min_pct {} 超出 SSOT bounds [{}, {}]",
            fname,
            band.min_pct,
            MIN_PER_TRADE_RISK_PCT,
            MAX_PER_TRADE_RISK_PCT
        );
        assert!(
            (MIN_PER_TRADE_RISK_PCT..=MAX_PER_TRADE_RISK_PCT).contains(&band.max_pct),
            "{}: dynamic_sizing.max_pct {} 超出 SSOT bounds [{}, {}]",
            fname,
            band.max_pct,
            MIN_PER_TRADE_RISK_PCT,
            MAX_PER_TRADE_RISK_PCT
        );
    }
}
