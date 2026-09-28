// LG1-T3 sibling（2026-05-11）：TickPipeline ctor `h0_gate.shadow_mode` 預設值
// + 既有 hot-reload 不變式測試。
//
// 動機：PA tech plan §1.5 risk #1 mitigation。Ctor 舊預設 `shadow_mode = true`
// 會在 engine 啟動到首次 TOML 載入完成之間留 1–3s shadow 觀察窗，期間若有
// 觸發 H0 阻斷條件會被誤放行（fail-open）。預設改為 `false`（hard-block）
// 對齊 §四「失敗默認收縮」原則。
//
// 本 sibling 不重複測 `apply_risk_snapshot` 的完整 hot-reload 路徑
// （已由 tests/risk_governance_hot_reload.rs::test_arch_rc1_hot_reload_e2e_*
// 覆蓋）；只補三條 ctor-default 級別斷言：
//   1) 預設 `shadow_mode = false`
//   2) `with_balance` 路徑同樣預設 `shadow_mode = false`
//   3) `with_kind` 路徑（Paper / Demo / Live）也預設 `shadow_mode = false`
//      — TOML 載入路徑（pipeline_config.rs:97-109 RMW）始終覆蓋 ctor default
//      才是真正的 SoT；ctor default 僅作 fail-closed safety net。

use super::super::*;

/// LG1-T3 #1：`TickPipeline::new` 預設 `h0_gate.shadow_mode = false`（hard-block）。
/// 之前 ctor 預設 `true` 引發啟動瞬窗 fail-open 風險，改為 `false`。
#[test]
fn test_lg1_t3_new_default_shadow_mode_is_false() {
    let pipeline = TickPipeline::new(&["BTCUSDT"]);
    assert!(
        !pipeline.h0_gate.config().shadow_mode,
        "LG1-T3 regression: TickPipeline::new ctor default `h0_gate.shadow_mode` \
         must be false (hard-block) to avoid the 1–3s startup window where \
         shadow=true would silently fail-open before the TOML hot-reload \
         lands; see pipeline_ctor.rs comment + PA §1.5 risk #1"
    );
}

/// LG1-T3 #2：`TickPipeline::with_balance` 同樣預設 `shadow_mode = false`。
/// `with_balance` 是 `new` 的內部路徑，但測試明示確保未來重構不漏掉。
#[test]
fn test_lg1_t3_with_balance_default_shadow_mode_is_false() {
    let pipeline = TickPipeline::with_balance(&["BTCUSDT"], 50_000.0);
    assert!(
        !pipeline.h0_gate.config().shadow_mode,
        "LG1-T3 regression: TickPipeline::with_balance ctor default \
         `h0_gate.shadow_mode` must be false (hard-block)"
    );
}

/// LG1-T3 #3：`TickPipeline::with_kind` 對 Paper / Demo / Live 三條 kind
/// 都預設 `shadow_mode = false`。TOML（risk_config_paper.toml 的
/// `h0_shadow_mode = true`）會在 `set_risk_store` + 首個 tick 後透過
/// `apply_risk_snapshot` 覆蓋為 paper-specific 值；ctor default 不需要
/// 為 paper 特化（fail-closed default 對 paper 也是安全的）。
#[test]
fn test_lg1_t3_with_kind_default_shadow_mode_is_false() {
    let p_paper = TickPipeline::with_kind(&["BTCUSDT"], 50_000.0, PipelineKind::Paper);
    let p_demo = TickPipeline::with_kind(&["BTCUSDT"], 50_000.0, PipelineKind::Demo);
    let p_live = TickPipeline::with_kind(&["BTCUSDT"], 50_000.0, PipelineKind::Live);
    assert!(
        !p_paper.h0_gate.config().shadow_mode,
        "LG1-T3 regression: with_kind(Paper) ctor default `h0_gate.shadow_mode` \
         must be false; paper-specific shadow=true is enforced by TOML \
         hot-reload after set_risk_store, not by ctor default"
    );
    assert!(
        !p_demo.h0_gate.config().shadow_mode,
        "LG1-T3 regression: with_kind(Demo) ctor default `h0_gate.shadow_mode` \
         must be false; demo TOML already `h0_shadow_mode = false`"
    );
    assert!(
        !p_live.h0_gate.config().shadow_mode,
        "LG1-T3 regression: with_kind(Live) ctor default `h0_gate.shadow_mode` \
         must be false; live TOML already `h0_shadow_mode = false`"
    );
}

/// Direct setter remains available for explicit in-process transitions.
#[test]
fn test_lg1_t3_set_shadow_mode_overrides_ctor_default_to_true() {
    let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
    assert!(!pipeline.h0_gate.config().shadow_mode);
    pipeline.h0_gate.set_shadow_mode(true);
    assert!(pipeline.h0_gate.config().shadow_mode);
}

/// Former ignored regression: an accepted store version must update H0.
#[test]
fn bya_gap_h0_hot_reload_applies_both_directions_and_gate_verdict() {
    use crate::config::{ConfigStore, PatchSource, RiskConfig};
    use std::sync::Arc;
    for kind in [PipelineKind::Paper, PipelineKind::Demo, PipelineKind::Live] {
        let mut pipeline = TickPipeline::with_kind(&["BTCUSDT"], 10_000.0, kind);
        let mut initial = RiskConfig::default();
        initial.runtime.h0_shadow_mode = false;
        let store = Arc::new(ConfigStore::new(initial));
        pipeline.set_risk_store(Arc::clone(&store));
        // An ineligible symbol gives the same real blocking condition in both modes.
        pipeline.h0_gate.set_symbol_eligibility("BTCUSDT", false);
        for (step, enabled) in [true, false].into_iter().enumerate() {
            store
                .apply_patch(
                    PatchSource::Operator,
                    |cfg| cfg.runtime.h0_shadow_mode = enabled,
                    RiskConfig::validate,
                )
                .unwrap();
            let now = 1_000 + step as u64;
            pipeline.on_replay_tick(&super::make_event("BTCUSDT", 50_000.0, now));
            assert_eq!(pipeline.h0_gate.config().shadow_mode, enabled, "{kind:?}");
            assert_eq!(
                pipeline.h0_gate.check("BTCUSDT", "linear", now).allowed,
                enabled
            );
        }
    }
}

#[test]
fn bya_gap_h0_startup_store_applies_before_first_tick_and_is_engine_local() {
    use crate::config::{ConfigStore, PatchSource, RiskConfig};
    use std::sync::Arc;
    let mut pipelines = Vec::new();
    let mut stores = Vec::new();
    for (kind, enabled) in [
        (PipelineKind::Paper, true),
        (PipelineKind::Demo, false),
        (PipelineKind::Live, false),
    ] {
        let mut cfg = RiskConfig::default();
        cfg.runtime.h0_shadow_mode = enabled;
        let store = Arc::new(ConfigStore::new(cfg));
        let mut pipeline = TickPipeline::with_kind(&["BTCUSDT"], 10_000.0, kind);
        pipeline.set_risk_store(Arc::clone(&store));
        assert_eq!(pipeline.h0_gate.config().shadow_mode, enabled);
        stores.push(store);
        pipelines.push(pipeline);
    }
    stores[1]
        .apply_patch(
            PatchSource::Operator,
            |cfg| cfg.runtime.h0_shadow_mode = true,
            RiskConfig::validate,
        )
        .unwrap();
    for pipeline in &mut pipelines {
        pipeline.on_replay_tick(&super::make_event("BTCUSDT", 50_000.0, 1_000));
    }
    assert_eq!(
        pipelines
            .iter()
            .map(|p| p.h0_gate.config().shadow_mode)
            .collect::<Vec<_>>(),
        vec![true, true, false]
    );
    assert!(!stores[2].load().runtime.h0_shadow_mode);
}

#[test]
fn bya_gap_h0_missing_config_defaults_to_hard_block_but_explicit_shadow_survives() {
    use crate::config::RiskConfig;
    let default = RiskConfig::default();
    assert!(!default.runtime.h0_shadow_mode);
    let mut document = serde_json::to_value(&default).unwrap();
    document["runtime"]
        .as_object_mut()
        .unwrap()
        .remove("h0_shadow_mode");
    let missing: RiskConfig = serde_json::from_value(document.clone()).unwrap();
    assert!(!missing.runtime.h0_shadow_mode);
    document.as_object_mut().unwrap().remove("runtime");
    let absent_section: RiskConfig = serde_json::from_value(document.clone()).unwrap();
    assert!(!absent_section.runtime.h0_shadow_mode);
    document["runtime"] = serde_json::json!({"h0_shadow_mode": true});
    let explicit: RiskConfig = serde_json::from_value(document).unwrap();
    assert!(explicit.runtime.h0_shadow_mode);
}
