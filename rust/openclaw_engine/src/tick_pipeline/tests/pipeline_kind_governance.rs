// G5-09 sibling: PipelineKind / GovernanceProfile / pipeline construction tests.
// Covers 3E-1 schema (db_mode / governance_profile / authorization / lease /
// serde / Display) + with_kind kind-propagation regression + basic creation +
// predictor RNG seed plumbing.
// G5-09 sibling：PipelineKind / GovernanceProfile / pipeline 建構測試。

use super::super::*;

// ── 3E-1: PipelineKind + GovernanceProfile tests ──

#[test]
fn test_pipeline_kind_db_mode() {
    assert_eq!(PipelineKind::Paper.db_mode(), "paper");
    assert_eq!(PipelineKind::Demo.db_mode(), "demo");
    assert_eq!(PipelineKind::Live.db_mode(), "live");
}

/// 3E-ARCH regression: with_kind() must persist `pipeline_kind` on the pipeline.
/// Before the fix, all engines kept the with_balance() default Paper and raced
/// on paper_state.json / pipeline_snapshot_paper.json.
/// 3E-ARCH 回歸：with_kind() 必須把 kind 寫入 pipeline 字段。修復前三引擎都
/// 留在 with_balance() 預設的 Paper，搶寫同一份 paper_state.json。
#[test]
fn test_with_kind_sets_pipeline_kind_field() {
    let p_paper = TickPipeline::with_kind(&["BTCUSDT"], 1_000.0, PipelineKind::Paper);
    let p_demo = TickPipeline::with_kind(&["BTCUSDT"], 1_000.0, PipelineKind::Demo);
    let p_live = TickPipeline::with_kind(&["BTCUSDT"], 1_000.0, PipelineKind::Live);
    assert_eq!(p_paper.pipeline_kind.db_mode(), "paper");
    assert_eq!(p_demo.pipeline_kind.db_mode(), "demo");
    assert_eq!(p_live.pipeline_kind.db_mode(), "live");
}

#[test]
fn test_pipeline_kind_is_exchange() {
    assert!(!PipelineKind::Paper.is_exchange());
    assert!(PipelineKind::Demo.is_exchange());
    assert!(PipelineKind::Live.is_exchange());
}

#[test]
fn test_pipeline_kind_governance_profile() {
    assert_eq!(
        PipelineKind::Paper.governance_profile(),
        GovernanceProfile::Exploration
    );
    assert_eq!(
        PipelineKind::Demo.governance_profile(),
        GovernanceProfile::Validation
    );
    assert_eq!(
        PipelineKind::Live.governance_profile(),
        GovernanceProfile::Production
    );
}

#[test]
fn test_governance_profile_authorization_requirements() {
    assert!(!GovernanceProfile::Exploration.requires_authorization());
    assert!(!GovernanceProfile::Validation.requires_authorization());
    assert!(GovernanceProfile::Production.requires_authorization());
}

#[test]
fn test_governance_profile_lease_requirements() {
    assert!(!GovernanceProfile::Exploration.requires_lease());
    assert!(!GovernanceProfile::Validation.requires_lease());
    assert!(GovernanceProfile::Production.requires_lease());
}

#[test]
fn test_pipeline_kind_serde_roundtrip() {
    for kind in [PipelineKind::Paper, PipelineKind::Demo, PipelineKind::Live] {
        let json = serde_json::to_string(&kind).expect("serialize");
        let back: PipelineKind = serde_json::from_str(&json).expect("deserialize");
        assert_eq!(kind, back);
    }
}

#[test]
fn test_pipeline_kind_display() {
    assert_eq!(format!("{}", PipelineKind::Paper), "paper");
    assert_eq!(format!("{}", PipelineKind::Demo), "demo");
    assert_eq!(format!("{}", PipelineKind::Live), "live");
}

#[test]
fn test_pipeline_creation() {
    let pipeline = TickPipeline::new(&["BTCUSDT"]);
    assert_eq!(pipeline.stats.total_ticks, 0);
}

#[test]
fn test_pipeline_on_tick() {
    let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
    pipeline.on_tick(&super::make_event("BTCUSDT", 50000.0, 1000));
    assert_eq!(pipeline.stats.total_ticks, 1);
}

#[test]
fn test_pipeline_multiple_ticks() {
    let mut pipeline = TickPipeline::new(&["BTCUSDT", "ETHUSDT"]);
    for i in 0..50 {
        pipeline.on_tick(&super::make_event("BTCUSDT", 50000.0 + i as f64, i * 60_000));
    }
    assert_eq!(pipeline.stats.total_ticks, 50);
}

#[test]
fn test_pipeline_with_auth() {
    let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
    pipeline.grant_paper_auth().unwrap();
    assert!(pipeline.governance.is_authorized());
}

/// EDGE-P3-1 Phase B #4 regression: `with_kind` forwards the kind into the
/// IntentProcessor so the predictor gate's `inputs.engine_kind` actually
/// reflects paper/demo/live. Before the fix, `IntentProcessor::pipeline_kind`
/// stayed at the constructor default (Paper) for every engine, causing the
/// ε-greedy branch in `gate.rs` to fire on demo/live too (only the writer-
/// level R5 guard + DB CHECK stopped the leak). This test locks the
/// propagation so future refactors don't silently regress it.
/// EDGE-P3-1 Phase B #4 回歸：`with_kind` 必須把 kind 透傳給 IntentProcessor，
/// 否則 demo/live 的 gate 仍視為 Paper，ε-greedy 會在 demo/live 誤發。
#[test]
fn test_with_kind_forwards_kind_to_intent_processor() {
    use crate::tick_pipeline::PipelineKind;
    let p_paper = TickPipeline::with_kind(&["BTCUSDT"], 1_000.0, PipelineKind::Paper);
    let p_demo = TickPipeline::with_kind(&["BTCUSDT"], 1_000.0, PipelineKind::Demo);
    let p_live = TickPipeline::with_kind(&["BTCUSDT"], 1_000.0, PipelineKind::Live);
    assert_eq!(
        p_paper.intent_processor.pipeline_kind(),
        PipelineKind::Paper
    );
    assert_eq!(p_demo.intent_processor.pipeline_kind(), PipelineKind::Demo);
    assert_eq!(p_live.intent_processor.pipeline_kind(), PipelineKind::Live);
}

/// EDGE-P3-1 Phase B #4: `set_predictor_rng_seed` reseeds the IntentProcessor
/// RNG. Locks the wiring by constructing two pipelines with different seeds
/// and asserting they disagree on at least one ε-greedy draw — the spec §7.3
/// contract is that the kind-discriminant XOR produces independent streams.
/// We use the fact that two different seeds of `SmallRng` produce different
/// `gen_bool(0.5)` sequences within a short prefix. No model needed because
/// this only probes the RNG plumbing, not the gate.
/// EDGE-P3-1 Phase B #4：`set_predictor_rng_seed` 必須真正重置 RNG。
#[test]
fn test_set_predictor_rng_seed_changes_draw_stream() {
    use crate::edge_predictor::gate::seed_for_engine;
    use crate::tick_pipeline::PipelineKind;
    let seed_paper = seed_for_engine(12_345, PipelineKind::Paper);
    let seed_demo = seed_for_engine(12_345, PipelineKind::Demo);
    assert_ne!(
        seed_paper, seed_demo,
        "sanity: per-kind XOR must yield different seeds for the same startup"
    );
    let mut p1 = TickPipeline::with_kind(&["BTCUSDT"], 1_000.0, PipelineKind::Paper);
    let mut p2 = TickPipeline::with_kind(&["BTCUSDT"], 1_000.0, PipelineKind::Paper);
    p1.set_predictor_rng_seed(seed_paper);
    p2.set_predictor_rng_seed(seed_demo);
    // Drain 64 bool draws from each RNG; at least one index must disagree.
    // 各抽 64 個 bool，至少一個位置需不同，證明兩條 RNG 流獨立。
    use rand::Rng;
    let draw_64 = |ip: &crate::intent_processor::IntentProcessor| -> Vec<bool> {
        let mut rng = ip.predictor_rng_lock_for_tests();
        (0..64).map(|_| rng.gen_bool(0.5)).collect()
    };
    let s1 = draw_64(&p1.intent_processor);
    let s2 = draw_64(&p2.intent_processor);
    assert_ne!(
        s1, s2,
        "different seeds must produce different draw streams within 64 bits"
    );
}
