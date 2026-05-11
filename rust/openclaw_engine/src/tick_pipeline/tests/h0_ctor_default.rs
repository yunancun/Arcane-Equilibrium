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

/// LG1-T3 #4：IPC `patch_risk_config{runtime.h0_shadow_mode=true}` 路徑驗證 —
/// `H0Gate::set_shadow_mode(true)` 必須能把 ctor `false` default 推翻成 true。
///
/// 這條測試是 ctor-default-as-safety-net 契約的核心：runtime IPC（operator
/// flip / drawdown_revoke / paper TOML reload via patch handler）始終是
/// shadow_mode SoT，ctor default 只在 IPC 來臨前提供 fail-closed 預設。
///
/// 注意：本 sibling 不測 `apply_risk_snapshot` 是否把 `RiskConfig.runtime.
/// h0_shadow_mode` 推進 `H0GateConfig.shadow_mode`。**E1 在 LG1-T3 IMPL 過程
/// 發現**：pipeline_config.rs:105-109 H0Gate RMW 路徑刻意 *保留*
/// shadow_mode（舊注釋稱「shadow_mode fields don't live in RiskConfig」已
/// 過時，因為 `runtime.h0_shadow_mode` 於 risk_config_advanced.rs:366 確實
/// 存在）— 實際 TOML→H0Gate 的 wire-in 只走 IPC `patch_risk_config` 的
/// risk.rs handler（line 313 `pipeline.h0_gate.set_shadow_mode(v)`）。
/// **E2 reviewer note**：見 sibling test #5 / report §reviewer-note。
#[test]
fn test_lg1_t3_set_shadow_mode_overrides_ctor_default_to_true() {
    let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
    assert!(
        !pipeline.h0_gate.config().shadow_mode,
        "precondition: ctor default must be false"
    );

    pipeline.h0_gate.set_shadow_mode(true);

    assert!(
        pipeline.h0_gate.config().shadow_mode,
        "LG1-T3 invariant: H0Gate::set_shadow_mode(true) must override ctor \
         `false` default; this is the path the IPC patch_risk_config handler \
         (event_consumer/handlers/risk.rs:313) uses for paper TOML / operator \
         flip / drawdown_revoke"
    );
}

/// LG1-T3 #5（ignored / E1 IMPL 期間發現）：`RiskConfig.runtime.h0_shadow_mode`
/// 透過 `set_risk_store` + `replace` 後，**目前不會** 自動推進
/// `H0GateConfig.shadow_mode`。本 test 標 `#[ignore]` 記錄此發現，作為
/// E2 reviewer note 的可執行證據。
///
/// **發現脈絡**（PA tech plan §1.5 risk #1 假設 vs runtime 真實狀態）：
/// - PA 假設「TOML 載入路徑 always 覆蓋 ctor default」
/// - 實際 wire-in 路徑：
///   * Startup time：TOML → `RiskConfig` → `ConfigStore` → `set_risk_store`
///     → `apply_risk_snapshot`（pipeline_config.rs:67–174）
///     **但** H0Gate RMW（line 105–109）**沒** copy
///     `snap.runtime.h0_shadow_mode` 進 `h0.shadow_mode`
///   * Runtime patch：IPC `patch_risk_config{h0_shadow_mode=...}`
///     → `event_consumer/handlers/risk.rs:313`
///     → `pipeline.h0_gate.set_shadow_mode(v)`（直接設）
/// - 結果：startup 階段 ctor default 是真正的 SoT，TOML 值要等到第一次
///   IPC patch 才會生效。
///
/// 後續工作（**不在本 T3 scope**）：
///   - 修 apply_risk_snapshot 把 `snap.runtime.h0_shadow_mode` 推進
///     `h0.shadow_mode`（≤ 5 LOC，新 LG-1 子任務 / 後續 wave）
///   - 同次刪除 line 98 的過時注釋
#[test]
#[ignore = "LG1-T3 reviewer note：apply_risk_snapshot 目前不會把 RiskConfig.runtime.h0_shadow_mode 推進 H0GateConfig.shadow_mode；修法 ≤5 LOC，留新子任務"]
fn test_lg1_t3_known_gap_apply_risk_snapshot_does_not_wire_h0_shadow_mode() {
    use crate::config::{ConfigStore, PatchSource, RiskConfig};
    use std::sync::Arc;

    let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
    let initial = RiskConfig::default();
    let store = Arc::new(ConfigStore::new(initial.clone()));
    pipeline.set_risk_store(Arc::clone(&store));

    let mut next = initial.clone();
    next.runtime.h0_shadow_mode = true;
    next.validate().expect("mutated config must be valid");
    store
        .replace(next, PatchSource::Operator)
        .expect("replace must succeed");

    pipeline.on_tick(&super::make_event("BTCUSDT", 50_000.0, 1_000));

    // 修好 apply_risk_snapshot 後本 assert 會 PASS；目前 fail（保留為已知
    // gap，標 #[ignore]）。
    assert!(
        pipeline.h0_gate.config().shadow_mode,
        "expected (post-fix): apply_risk_snapshot wires runtime.h0_shadow_mode \
         into H0GateConfig.shadow_mode"
    );
}
