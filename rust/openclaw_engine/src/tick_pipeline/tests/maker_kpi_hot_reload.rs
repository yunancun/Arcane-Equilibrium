// G5-09 sibling: EDGE-P2-3 Phase 1B-5 hot-reload e2e for `MakerKpiConfig` +
// FUP-4 follow-through tests T1-T10 (validate / deny_unknown_fields / serde
// backcompat / process_with_features e2e / replace-without-tick semantics /
// router→sweep e2e). Single sibling so future reviewers cite one fence.
// G5-09 sibling：MakerKpiConfig hot-reload + 1B-5 FUP T1-T10。

use super::super::*;

// ─── EDGE-P2-3 Phase 1B-5 hot-reload e2e ────────────────────────────────
// Proves the new `ConfigStore<MakerKpiConfig>` wiring: (1) `set_maker_kpi_store`
// seeds both the pipeline's own snapshot AND IntentProcessor's router-facing
// copy; (2) after `replace()`, a single `on_tick` picks up the new funding-drag
// threshold + KPI-gate thresholds via `sync_maker_kpi_config_if_changed`;
// (3) unwired mode falls back to `MakerKpiConfig::default()` with no per-tick
// allocation.
// 驗證 1B-5 新接線：(1) `set_maker_kpi_store` 同步播種 pipeline 與
// IntentProcessor 兩份快照；(2) `replace()` 後一個 tick 就拾取新門檻；
// (3) 未接 store 時仍等同 `MakerKpiConfig::default()`，無 per-tick 分配。

#[test]
fn test_maker_kpi_hot_reload_seeds_initial_snapshot_on_set() {
    use crate::config::ConfigStore;
    use crate::paper_state::MakerKpiConfig;
    use std::sync::Arc;

    let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
    // Before wiring, both the pipeline's own snapshot and the IntentProcessor's
    // router-facing snapshot must already be at defaults (bit-identical to the
    // pre-hot-reload commit).
    // 未接線前：pipeline 與 IntentProcessor 兩份快照皆為 default。
    assert_eq!(
        pipeline.maker_kpi_config.funding_drag_threshold,
        MakerKpiConfig::default().funding_drag_threshold
    );
    assert_eq!(
        pipeline.intent_processor.maker_kpi_config().funding_drag_threshold,
        MakerKpiConfig::default().funding_drag_threshold
    );

    // Wire a store whose initial snapshot differs from defaults — the setter
    // must push the snapshot into BOTH consumers immediately (before any tick).
    // 建立與 default 不同的 store 初始值 —— setter 必須立即同步至兩個 consumer。
    let mut custom = MakerKpiConfig::default();
    custom.funding_drag_threshold = 0.0009;
    custom.min_avg_net_edge_bps = -10.0;
    let store = Arc::new(ConfigStore::new(custom.clone()));
    pipeline.set_maker_kpi_store(Arc::clone(&store));

    assert!(
        (pipeline.maker_kpi_config.funding_drag_threshold - 0.0009).abs() < 1e-12,
        "pipeline maker_kpi_config.funding_drag_threshold not seeded on set_maker_kpi_store"
    );
    assert!(
        (pipeline.intent_processor.maker_kpi_config().funding_drag_threshold - 0.0009).abs()
            < 1e-12,
        "intent_processor.maker_kpi_config().funding_drag_threshold not seeded on set_maker_kpi_store"
    );
    assert!(
        (pipeline.intent_processor.maker_kpi_config().min_avg_net_edge_bps - (-10.0)).abs()
            < 1e-12
    );
    assert_eq!(pipeline.maker_kpi_version_seen, store.version());
}

#[test]
fn test_maker_kpi_hot_reload_picks_up_replace_on_next_tick() {
    use crate::config::{ConfigStore, PatchSource};
    use crate::paper_state::MakerKpiConfig;
    use std::sync::Arc;

    let mut pipeline = TickPipeline::new(&["BTCUSDT"]);

    let initial = MakerKpiConfig::default();
    let store = Arc::new(ConfigStore::new(initial.clone()));
    pipeline.set_maker_kpi_store(Arc::clone(&store));
    let v0 = store.version();

    // Mutate the config: bump funding_drag_threshold + min_fill_rate.
    // 改 funding_drag_threshold 與 min_fill_rate。
    let mut next = initial.clone();
    next.funding_drag_threshold = 0.0013;
    next.min_fill_rate = 0.25;
    next.min_avg_net_edge_bps = -3.0;

    store
        .replace(next.clone(), PatchSource::Operator)
        .expect("replace must succeed on trivial MakerKpiConfig swap");
    assert_eq!(store.version(), v0 + 1);

    // BEFORE the next tick: the pipeline's owned snapshot is stale (still at
    // `initial`); the new version hasn't been pulled yet.
    // tick 前：pipeline 仍持舊快照。
    assert!(
        (pipeline.maker_kpi_config.funding_drag_threshold - initial.funding_drag_threshold).abs()
            < 1e-12
    );

    // Drive a single tick — `sync_maker_kpi_config_if_changed` runs at the top
    // of on_tick and must mirror the new snapshot into both consumers.
    // 打一個 tick — sync 應將新快照同步至 pipeline + IntentProcessor。
    pipeline.on_tick(&super::make_event("BTCUSDT", 50_000.0, 1_000));

    assert!(
        (pipeline.maker_kpi_config.funding_drag_threshold - 0.0013).abs() < 1e-12,
        "consumer #1: pipeline.maker_kpi_config NOT hot-reloaded after replace"
    );
    assert!(
        (pipeline.maker_kpi_config.min_fill_rate - 0.25).abs() < 1e-12,
        "consumer #1: pipeline.maker_kpi_config.min_fill_rate NOT hot-reloaded"
    );
    assert!(
        (pipeline.intent_processor.maker_kpi_config().funding_drag_threshold - 0.0013).abs()
            < 1e-12,
        "consumer #2: intent_processor.maker_kpi_config() NOT hot-reloaded after replace"
    );
    assert!(
        (pipeline.intent_processor.maker_kpi_config().min_avg_net_edge_bps - (-3.0)).abs() < 1e-12
    );
    assert_eq!(pipeline.maker_kpi_version_seen, store.version());
}

#[test]
fn test_maker_kpi_unwired_falls_back_to_default_every_tick() {
    use crate::paper_state::MakerKpiConfig;

    let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
    // No `set_maker_kpi_store` — sync is a no-op. Drive a tick, then assert
    // the owned snapshot is still `MakerKpiConfig::default()`.
    // 未接 store：sync no-op，tick 之後仍為 default。
    pipeline.on_tick(&super::make_event("BTCUSDT", 50_000.0, 1_000));
    assert_eq!(
        pipeline.maker_kpi_config.funding_drag_threshold,
        MakerKpiConfig::default().funding_drag_threshold
    );
    assert_eq!(
        pipeline.intent_processor.maker_kpi_config().funding_drag_threshold,
        MakerKpiConfig::default().funding_drag_threshold
    );
    assert_eq!(pipeline.maker_kpi_version_seen, 0);
}

#[test]
fn test_maker_kpi_version_bump_only_applies_once_per_version() {
    use crate::config::{ConfigStore, PatchSource};
    use crate::paper_state::MakerKpiConfig;
    use std::sync::Arc;

    // After a patch lands and is consumed by one tick, subsequent ticks must
    // NOT re-apply (version already matches). We prove this by mutating the
    // OWNED `maker_kpi_config` directly between ticks — if the sync ran, the
    // owned value would be overwritten back to the store's snapshot; a no-op
    // leaves the manual tweak alone.
    // patch 被一個 tick 消費後，後續 tick 不應重複套用。於兩個 tick 間手動
    // 覆寫 owned 快照，若 sync 重跑就會被覆蓋回 store；no-op 則保留手改值。
    let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
    let store = Arc::new(ConfigStore::new(MakerKpiConfig::default()));
    pipeline.set_maker_kpi_store(Arc::clone(&store));

    let mut next = MakerKpiConfig::default();
    next.funding_drag_threshold = 0.0011;
    store.replace(next, PatchSource::Operator).unwrap();

    // Tick 1 → pulls patch.
    pipeline.on_tick(&super::make_event("BTCUSDT", 50_000.0, 1_000));
    assert!(
        (pipeline.maker_kpi_config.funding_drag_threshold - 0.0011).abs() < 1e-12
    );

    // Poison the owned snapshot with a sentinel value.
    // 手動寫入一個與 store 不同的 sentinel。
    pipeline.maker_kpi_config.funding_drag_threshold = 0.0042;

    // Tick 2 — no replace since, so version matches → sync must be a no-op.
    // 無 replace，版本號未變 → sync 為 no-op，sentinel 保留。
    pipeline.on_tick(&super::make_event("BTCUSDT", 50_100.0, 2_000));
    assert!(
        (pipeline.maker_kpi_config.funding_drag_threshold - 0.0042).abs() < 1e-12,
        "sync must not re-apply when the store version is unchanged"
    );
}

#[test]
fn test_maker_kpi_config_serde_roundtrip_via_toml() {
    use crate::paper_state::MakerKpiConfig;

    // Partial TOML — omitted fields must fall through to `#[serde(default)]`
    // functions which must match `impl Default`.
    // 僅寫一個欄位的 TOML — 其餘欄位應由 `#[serde(default)]` 回填成與
    // `impl Default` 相同的值，證明兩者不會漂移。
    let partial = r#"
funding_drag_threshold = 0.0008
"#;
    let cfg: MakerKpiConfig = toml::from_str(partial).expect("partial TOML must parse");
    let d = MakerKpiConfig::default();
    assert!((cfg.funding_drag_threshold - 0.0008).abs() < 1e-12);
    assert_eq!(cfg.min_samples, d.min_samples);
    assert!((cfg.min_fill_rate - d.min_fill_rate).abs() < 1e-12);
    assert!((cfg.min_avg_net_edge_bps - d.min_avg_net_edge_bps).abs() < 1e-12);
    assert_eq!(cfg.stale_window_ms, d.stale_window_ms);

    // Full-roundtrip: serialize → parse → fields must match bit-for-bit.
    // 完整 round-trip：序列化後再反序列化，各欄位必須完全一致。
    let mut original = MakerKpiConfig::default();
    original.funding_drag_threshold = 0.0007;
    original.min_samples = 50;
    original.min_fill_rate = 0.22;
    original.min_avg_net_edge_bps = -2.5;
    original.stale_window_ms = 900_000;
    let s = toml::to_string(&original).expect("serialize");
    let back: MakerKpiConfig = toml::from_str(&s).expect("deserialize");
    assert!((back.funding_drag_threshold - original.funding_drag_threshold).abs() < 1e-12);
    assert_eq!(back.min_samples, original.min_samples);
    assert!((back.min_fill_rate - original.min_fill_rate).abs() < 1e-12);
    assert!((back.min_avg_net_edge_bps - original.min_avg_net_edge_bps).abs() < 1e-12);
    assert_eq!(back.stale_window_ms, original.stale_window_ms);
}

// ─── EDGE-P2-3 Phase 1B-5 FUP-4: E2 APPROVE_WITH_NITS follow-through ─────────
// Five non-blocking nits + five suggested FUP tests from the 1B-4.3/1B-5 E2
// review, all in one batch so future reviewers can cite a single regression
// fence for the decisions below.
//
// Nits addressed here:
//   N1 `MakerKpiConfig::validate()` method (see tests T1–T2).
//   N2 `#[serde(default)]` on `RestingLimitOrder.funding_rate_at_submit`
//      so pre-1B-4.3 persisted queues round-trip (see test T5).
//   N3 `#[serde(deny_unknown_fields)]` on `MakerKpiConfig` so TOML typos
//      fail loudly instead of silently falling back to defaults (T3).
//   N4 Pre-existing file-size caps — acknowledged but NOT addressed here
//      (separate E5 scope: tick_pipeline/mod.rs, on_tick.rs, tests.rs all
//      exceed §九 1200-line cap from before this PR; splitting is its own
//      refactor wave).
//   N5 §九 registry — already fine, no action needed.
//
// FUP tests added here (T6–T10):
//   FUP1 router→sweep e2e via on_tick pipeline (T10).
//   FUP2 router KPI gate via `process_with_features` path (T7).
//   FUP3 replace-without-tick semantics (T8).
//   FUP4 empty-TOML round-trip (T6).
//   FUP5 `RestingLimitOrder` serde backcompat (T5).
//
// 五項 E2 APPROVE_WITH_NITS 反饋一次處理：
//   N1 加 `MakerKpiConfig::validate()`；N2 `#[serde(default)]` on
//   `RestingLimitOrder.funding_rate_at_submit`；N3 `deny_unknown_fields` on
//   `MakerKpiConfig`；N4 檔案行數超限為既有 E5 scope，不在本次處理；
//   N5 §九 已無需動作。同時補上五個 FUP 測試（T6–T10）。

// T1: `validate()` accepts the default config.
// T1：`validate()` 對 default 必須 OK。
#[test]
fn test_maker_kpi_config_validate_default_ok() {
    use crate::paper_state::MakerKpiConfig;
    let d = MakerKpiConfig::default();
    assert!(
        d.validate().is_ok(),
        "MakerKpiConfig::default() must satisfy validate() — got {:?}",
        d.validate()
    );
}

// T2: `validate()` rejects every documented invariant violation.
// T2：每一條 validate() 不變量都必須被對應的違反案例拒絕。
#[test]
fn test_maker_kpi_config_validate_rejects_bad_fields() {
    use crate::paper_state::MakerKpiConfig;

    // min_fill_rate out of [0, 1]
    let mut cfg = MakerKpiConfig::default();
    cfg.min_fill_rate = 1.5;
    assert!(cfg.validate().is_err(), "min_fill_rate 1.5 must be rejected");
    cfg.min_fill_rate = -0.1;
    assert!(cfg.validate().is_err(), "min_fill_rate -0.1 must be rejected");
    cfg.min_fill_rate = f64::NAN;
    assert!(cfg.validate().is_err(), "NaN min_fill_rate must be rejected");

    // min_avg_net_edge_bps > 0 → deadlock
    let mut cfg = MakerKpiConfig::default();
    cfg.min_avg_net_edge_bps = 1.0;
    assert!(
        cfg.validate().is_err(),
        "positive min_avg_net_edge_bps must be rejected (deadlock the gate)"
    );

    // Non-finite min_avg_net_edge_bps
    let mut cfg = MakerKpiConfig::default();
    cfg.min_avg_net_edge_bps = f64::INFINITY;
    assert!(cfg.validate().is_err(), "Inf min_avg_net_edge_bps must be rejected");

    // Negative funding_drag_threshold
    let mut cfg = MakerKpiConfig::default();
    cfg.funding_drag_threshold = -0.001;
    assert!(cfg.validate().is_err(), "negative funding_drag_threshold must be rejected");

    // Non-finite funding_drag_threshold
    let mut cfg = MakerKpiConfig::default();
    cfg.funding_drag_threshold = f64::NAN;
    assert!(cfg.validate().is_err(), "NaN funding_drag_threshold must be rejected");

    // Edge case: 0.0 funding_drag_threshold is VALID (guard disabled semantic).
    // 邊界：`funding_drag_threshold = 0.0` 合法（代表關閉 guard）。
    let mut cfg = MakerKpiConfig::default();
    cfg.funding_drag_threshold = 0.0;
    assert!(cfg.validate().is_ok(), "0.0 funding_drag_threshold must be accepted (disables guard)");
}

// T3: `deny_unknown_fields` — a typo in a TOML patch yields an error instead
// of silently being absorbed by `#[serde(default)]` on siblings.
// T3：TOML 中有拼錯的欄位必須失敗，不能被 sibling 的 `#[serde(default)]` 吞掉。
#[test]
fn test_maker_kpi_config_deny_unknown_fields_rejects_typo() {
    use crate::paper_state::MakerKpiConfig;
    let typo = r#"
funding_drag_trheshold = 0.0008
"#;
    let res: Result<MakerKpiConfig, _> = toml::from_str(typo);
    assert!(
        res.is_err(),
        "TOML with typo field `funding_drag_trheshold` must be rejected by deny_unknown_fields"
    );
}

// T6 (FUP4): empty TOML must yield a fully defaulted config via every field's
// `#[serde(default = "...")]`.
// T6（FUP4）：空 TOML 反序列化必須全部回退到 default。
#[test]
fn test_maker_kpi_config_empty_toml_yields_defaults() {
    use crate::paper_state::MakerKpiConfig;
    let empty = "";
    let cfg: MakerKpiConfig = toml::from_str(empty).expect("empty TOML must parse");
    let d = MakerKpiConfig::default();
    assert_eq!(cfg.min_samples, d.min_samples);
    assert!((cfg.min_fill_rate - d.min_fill_rate).abs() < 1e-12);
    assert!((cfg.min_avg_net_edge_bps - d.min_avg_net_edge_bps).abs() < 1e-12);
    assert_eq!(cfg.stale_window_ms, d.stale_window_ms);
    assert!((cfg.funding_drag_threshold - d.funding_drag_threshold).abs() < 1e-12);
}

// T5 (FUP5): `RestingLimitOrder` serde backcompat — a persisted queue written
// before 1B-4.3 landed will not have `funding_rate_at_submit` in the blob.
// `#[serde(default)]` must let it parse back as `0.0` (= unknown rate → guard
// stays off, preserving pre-1B-4.3 behaviour).
// T5（FUP5）：1B-4.3 之前持久化的 `RestingLimitOrder` 無此欄位，反序列化時必須
// 回退 `0.0`（= rate 未知、guard 關閉），行為與升級前一致。
#[test]
fn test_resting_limit_order_deserialize_without_funding_rate_defaults_to_zero() {
    use crate::order_manager::TimeInForce;
    use crate::paper_state::RestingLimitOrder;

    // Pre-1B-4.3 TOML shape — no `funding_rate_at_submit` key.
    // 1B-4.3 前的 TOML 形狀 —— 無 `funding_rate_at_submit`。
    let legacy_toml = r#"
symbol = "BTCUSDT"
is_long = true
qty = 0.01
limit_price = 49995.0
time_in_force = "PostOnly"
submit_ts_ms = 1700000000000
deadline_ms = 1700000045000
mid_price_at_submit = 50000.0
order_link_id = "pop_paper_BTCUSDT_1700000000000"
context_id = "ctx-legacy"
strategy = "grid_trading"
"#;
    let order: RestingLimitOrder = toml::from_str(legacy_toml).expect("legacy TOML must parse");
    assert_eq!(order.symbol, "BTCUSDT");
    assert_eq!(order.time_in_force, TimeInForce::PostOnly);
    assert!(
        order.funding_rate_at_submit.abs() < 1e-12,
        "missing funding_rate_at_submit must deserialize to 0.0 (found {})",
        order.funding_rate_at_submit
    );
}

// T7 (FUP2): router KPI gate effective through `process_with_features` path.
// Verifies (a) the PostOnly draft stamps `funding_rate_at_submit` from
// `paper_state.latest_funding_rate`; (b) `update_maker_kpi_config` hot-reload
// actually changes the gate verdict on the next `process_with_features` call
// (not just via the lower-level `process`).
// T7（FUP2）：從 process_with_features 高階入口驗證 KPI gate 接線 ——
// (a) PostOnly draft 必須打標 funding_rate_at_submit；(b) update_maker_kpi_config
// 熱重載後，下一次 process_with_features 調用 gate 判決必須改變。
#[test]
fn test_maker_kpi_gate_via_process_with_features_hot_reload_effective() {
    use crate::intent_processor::{IntentProcessor, OrderIntent};
    use crate::order_manager::TimeInForce;
    use crate::paper_state::{MakerKpiConfig, PaperState};
    use openclaw_core::governance_core::{GovernanceCore, GovernanceProfile};

    let mut proc = IntentProcessor::new();
    let mut gov = GovernanceCore::new();
    gov.grant_paper_authorization(None).unwrap();

    let mut ps = PaperState::new(10_000.0);
    ps.set_latest_price("BTCUSDT", 50_000.0);
    ps.set_latest_turnover("BTCUSDT", 100_000_000.0);
    // Stamp a non-zero funding rate so the draft picks it up.
    // 設定非零 funding rate，供 draft 打標。
    ps.set_latest_funding_rate("BTCUSDT", 0.0012);

    let intent = OrderIntent {
        symbol: "BTCUSDT".into(),
        is_long: true,
        qty: 0.002,
        confidence: 0.8,
        strategy: "grid_trading".into(),
        order_type: "Limit".into(),
        limit_price: Some(49_990.0),
        confluence_score: None,
        persistence_elapsed_ms: None,
        time_in_force: Some(TimeInForce::PostOnly),
        maker_timeout_ms: Some(45_000),
    };

    // (a) Under default config the gate is Cold (no samples) so enqueue succeeds.
    //     The resting_order draft must carry the non-zero funding rate.
    // (a) default 下 gate 為 Cold（無樣本），enqueue 應成功；draft 必須帶非零 rate。
    let r1 = proc.process_with_features(
        &intent,
        &gov,
        &ps,
        500.0,
        GovernanceProfile::Exploration,
        None,
        Some("ctx-a"),
        1_700_000_000_000,
    );
    let draft = r1
        .resting_order
        .as_ref()
        .expect("PostOnly + Cold gate must yield a resting_order draft");
    assert!(
        (draft.funding_rate_at_submit - 0.0012).abs() < 1e-12,
        "process_with_features must stamp funding_rate_at_submit from paper_state \
         (got {})",
        draft.funding_rate_at_submit
    );

    // Seed per-symbol stats so an aggressive min_fill_rate turns the gate Degraded.
    // Uses the existing `#[cfg(test)] pub fn test_seed_maker_stats_terminal` helper
    // on PaperState (see paper_state/resting_orders.rs:417) — 5 fills + 20 timeouts
    // → fill_rate = 0.2. Stamps `last_seen_ms=1_700_000_000_000` so the seed will
    // not be silently decayed by `stale_window_ms` before the next
    // `process_with_features` call at `1_700_000_000_500`.
    // 以既有測試 helper 種入 per-symbol 統計：5 成交 / 20 超時 → fill_rate = 0.2。
    // last_seen_ms 設於下次呼叫前 500ms，避免被 stale_window_ms 衰減。
    ps.test_seed_maker_stats_terminal("BTCUSDT", 5, 20, 1_700_000_000_000);

    // (b) Hot-reload: min_samples=0 makes the gate always evaluate; min_fill_rate=0.5
    //     with the seeded 0.2 rate forces Degraded → router falls back to market.
    // (b) 熱重載：min_samples=0 讓 gate 立即評估；min_fill_rate=0.5 使 0.2 ×
    //     seed → Degraded → router 改走市價。
    let mut patched = MakerKpiConfig::default();
    patched.min_samples = 0;
    patched.min_fill_rate = 0.5;
    patched.stale_window_ms = 0; // disable staleness decay for deterministic test
    proc.update_maker_kpi_config(patched);

    let r2 = proc.process_with_features(
        &intent,
        &gov,
        &ps,
        500.0,
        GovernanceProfile::Exploration,
        None,
        Some("ctx-b"),
        1_700_000_000_500,
    );
    assert!(
        r2.resting_order.is_none(),
        "after hot-reload to min_fill_rate=0.5, degraded gate must drop resting_order"
    );
    assert!(
        r2.maker_degraded_fallback.is_some(),
        "degraded gate must emit maker_degraded_fallback marker"
    );
}

// T8 (FUP3): `store.replace()` *without* an intervening `on_tick` keeps the
// pipeline's owned snapshot stale — the router reads the stale config until
// the next tick fires `sync_maker_kpi_config_if_changed`. This codifies the
// design so a future "eager sync on replace" refactor is a conscious decision
// rather than an accidental regression.
// T8（FUP3）：store.replace() 後若不打 tick，pipeline 持有的快照仍為舊值，
// router 會讀到舊 config 直到下一個 tick 觸發 sync。此行為被此測試明文鎖定，
// 未來如需改成 replace 即時同步須作為有意識決策而非意外回歸。
#[test]
fn test_maker_kpi_replace_without_tick_leaves_snapshot_stale_until_next_tick() {
    use crate::config::{ConfigStore, PatchSource};
    use crate::paper_state::MakerKpiConfig;
    use std::sync::Arc;

    let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
    let initial = MakerKpiConfig::default();
    let store = Arc::new(ConfigStore::new(initial.clone()));
    pipeline.set_maker_kpi_store(Arc::clone(&store));

    // replace() bumps version but does NOT touch pipeline state.
    // replace() 僅升版，不動 pipeline。
    let mut next = initial.clone();
    next.funding_drag_threshold = 0.0033;
    store
        .replace(next, PatchSource::Operator)
        .expect("replace must succeed");

    // Router reads `self.maker_kpi_config.funding_drag_threshold` in-process —
    // here we read the pipeline's owned snapshot directly, which is the same
    // byte that the IntentProcessor holds (seeded at `set_maker_kpi_store`).
    // Should still be at the initial (default) value.
    // 此時 pipeline 仍持 initial 快照（未 sync）。
    assert!(
        (pipeline.maker_kpi_config.funding_drag_threshold - initial.funding_drag_threshold).abs()
            < 1e-12,
        "replace without tick must NOT alter pipeline.maker_kpi_config"
    );
    assert!(
        (pipeline.intent_processor.maker_kpi_config().funding_drag_threshold
            - initial.funding_drag_threshold)
            .abs()
            < 1e-12,
        "replace without tick must NOT alter IntentProcessor.maker_kpi_config"
    );

    // Next on_tick runs `sync_maker_kpi_config_if_changed` at top-of-tick and
    // picks up the new version.
    // 下一個 on_tick 執行 sync，拾取新版本。
    pipeline.on_tick(&super::make_event("BTCUSDT", 50_000.0, 1_000));
    assert!(
        (pipeline.maker_kpi_config.funding_drag_threshold - 0.0033).abs() < 1e-12,
        "on_tick after replace must mirror the new value"
    );
    assert!(
        (pipeline.intent_processor.maker_kpi_config().funding_drag_threshold - 0.0033).abs()
            < 1e-12,
        "on_tick after replace must also mirror into IntentProcessor"
    );
}

// T10 (FUP1): end-to-end wire-through from a hot-reloaded `MakerKpiConfig`
// snapshot into the paper sweep's bias-guard #3 classification. Seeds a
// resting order whose submit-time funding is adverse, drives one tick at
// touch-equal price, and asserts the guard trips (incrementing
// `funding_drag_skips`). Then hot-reloads a higher threshold, ticks again,
// and asserts the counter does NOT advance — proving the sweep reads the
// live snapshot rather than a boot-time constant.
// T10（FUP1）：從 ConfigStore 熱重載 → on_tick sync → sweep bias #3 分類的
// 端到端接線。先種入逆向 funding 掛單於 touch-equal 價位，第一個 tick 應
// 觸發 guard（funding_drag_skips +1）；熱重載更高 threshold 後再 tick，
// guard 應失效（計數器不增）—— 證明 sweep 讀取 live snapshot。
#[test]
fn test_maker_kpi_hot_reload_router_to_sweep_e2e() {
    use crate::config::{ConfigStore, PatchSource};
    use crate::order_manager::TimeInForce;
    use crate::paper_state::{MakerKpiConfig, RestingLimitOrder};
    use std::collections::{HashMap, VecDeque};
    use std::sync::Arc;

    let mut pipeline = TickPipeline::with_balance(&["BTCUSDT"], 10_000.0);

    // Threshold 0.0001 is low enough that funding=0.002 trips the guard.
    // 將 threshold 調至 0.0001，使 0.002 的 funding 必觸發 guard。
    let mut initial = MakerKpiConfig::default();
    initial.funding_drag_threshold = 0.0001;
    initial.stale_window_ms = 0;
    let store = Arc::new(ConfigStore::new(initial));
    pipeline.set_maker_kpi_store(Arc::clone(&store));

    // Seed a resting order at exactly touch-equal (price == limit) so the
    // classifier yields FillPartial — the ONLY branch the funding-drag guard
    // can downgrade. `submit_ts_ms < now_ms` so bias #1 "same-tick Keep" does
    // not mask the test. Use "AA" as order_link_id (byte sum 130 → heads) so
    // if the guard were disabled, the order would proceed to partial-fill
    // heads branch (Fill). Under the guard it must be retained as Keep.
    // 種入 touch-equal 掛單（price == limit）觸發 FillPartial 分類，只有此
    // 分支會被 funding-drag guard 降級。submit_ts_ms < now_ms 避 bias #1。
    // order_link_id "AA" 的 byte sum = 130 → heads=true，guard 關閉時原本
    // 會 Fill；guard 作用下必 Keep。
    let limit_price = 49_990.0;
    let adverse_long_rate = 0.002; // > 0.0001 threshold, adverse to long
    let mut queues: HashMap<String, VecDeque<RestingLimitOrder>> = HashMap::new();
    queues.insert(
        "BTCUSDT".to_string(),
        VecDeque::from(vec![RestingLimitOrder {
            symbol: "BTCUSDT".into(),
            is_long: true,
            qty: 0.01,
            limit_price,
            time_in_force: TimeInForce::PostOnly,
            submit_ts_ms: 500,
            deadline_ms: 10_000_000,
            mid_price_at_submit: 50_000.0,
            order_link_id: "AA".into(),
            context_id: "ctx-e2e".into(),
            strategy: "grid_trading".into(),
            funding_rate_at_submit: adverse_long_rate,
        }]),
    );
    pipeline.paper_state.seed_resting_limit_orders(queues);
    let skips_before = pipeline
        .paper_state
        .maker_stats()
        .aggregate
        .funding_drag_skips;

    // Tick #1: price == limit, guard armed → expect FundingDragSkip.
    // tick #1：price == limit + guard 啟用 → 期望 FundingDragSkip。
    pipeline.on_tick(&super::make_event("BTCUSDT", limit_price, 1_000));
    let skips_after_tick1 = pipeline
        .paper_state
        .maker_stats()
        .aggregate
        .funding_drag_skips;
    assert_eq!(
        skips_after_tick1,
        skips_before + 1,
        "tick #1 with armed guard must increment funding_drag_skips by exactly 1"
    );
    // Order retained — FundingDragSkip keeps the order in-queue.
    // FundingDragSkip 保留掛單於隊列。
    assert_eq!(
        pipeline.paper_state.resting_limit_order_count(),
        1,
        "FundingDragSkip must NOT drain the order from the queue"
    );

    // Hot-reload to a higher threshold so the same funding rate is no longer
    // considered adverse. Next tick: guard disabled → order fills (heads).
    // 熱重載至更高 threshold → guard 失效；同 rate 不再視為逆向。
    let mut relaxed = MakerKpiConfig::default();
    relaxed.funding_drag_threshold = 0.0050; // > 0.002
    relaxed.stale_window_ms = 0;
    store
        .replace(relaxed, PatchSource::Operator)
        .expect("replace must succeed");

    // Tick #2: price still == limit, guard disarmed. The classifier returns
    // FillPartial and the partial-fill heads branch actually fills (since
    // "AA" byte sum is even → heads=true). The funding_drag_skips counter
    // must stay at skips_after_tick1 — guard did NOT fire.
    // tick #2：price 仍等於 limit，guard 關閉。分類 FillPartial + heads → Fill。
    // funding_drag_skips 不應再增，證明 sweep 讀的是 hot-reloaded snapshot。
    pipeline.on_tick(&super::make_event("BTCUSDT", limit_price, 2_000));
    let skips_after_tick2 = pipeline
        .paper_state
        .maker_stats()
        .aggregate
        .funding_drag_skips;
    assert_eq!(
        skips_after_tick2, skips_after_tick1,
        "tick #2 with disarmed guard must NOT advance funding_drag_skips \
         (hot-reload must reach the sweep)"
    );
}
