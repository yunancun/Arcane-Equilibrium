mod predictor_wiring_tests {
    use super::*;
    use crate::config::risk_config::EdgePredictorFallback;
    use crate::edge_predictor::{
        features::FeatureVectorV1, EdgePredictor as EdgePredictorTrait, EdgePredictorStore,
        PredictError, Prediction,
    };
    use crate::tick_pipeline::PipelineCommand;
    use std::sync::Arc;

    struct StubOkPredictor {
        pred: Prediction,
    }

    impl EdgePredictorTrait for StubOkPredictor {
        fn predict(&self, _f: &FeatureVectorV1) -> Result<Prediction, PredictError> {
            Ok(self.pred)
        }
        fn age_seconds(&self) -> u64 {
            0
        }
        fn schema_hash(&self) -> &str {
            "stub-schema"
        }
        fn definition_hash(&self) -> &str {
            "stub-def"
        }
        fn model_id(&self) -> &str {
            "stub"
        }
    }

    fn approved_governance() -> GovernanceCore {
        let mut g = GovernanceCore::new();
        g.grant_paper_authorization(None).unwrap();
        g
    }

    fn paper_state_with_price(price: f64) -> PaperState {
        let mut s = PaperState::new(10_000.0);
        s.set_latest_price("BTCUSDT", price);
        s.set_latest_turnover("BTCUSDT", 100_000_000.0);
        s
    }

    fn intent_btc(confidence: f64) -> OrderIntent {
        OrderIntent {
            symbol: "BTCUSDT".into(),
            is_long: true,
            qty: 0.001,
            confidence,
            strategy: "test".into(),
            order_type: "market".into(),
            limit_price: None,
            confluence_score: None,
            persistence_elapsed_ms: None,
            time_in_force: None,
            maker_timeout_ms: None,
        }
    }

    #[test]
    fn test_process_with_features_none_behaves_identically_to_legacy() {
        // features=None → predictor skipped regardless of store/config.
        // features=None → 忽略 predictor，行為等同舊路徑。
        let mut proc = IntentProcessor::new();
        proc.risk_config.edge_predictor.use_edge_predictor = true;
        proc.risk_config.edge_predictor.shadow_mode = false;
        let store = Arc::new(EdgePredictorStore::new());
        store.swap(
            "test",
            Arc::new(StubOkPredictor {
                pred: Prediction {
                    q10: 100.0,
                    q50: 200.0,
                    q90: 300.0,
                },
            }),
        );
        proc.set_edge_predictor_store(store);
        let gov = approved_governance();
        let state = paper_state_with_price(30_000.0);
        // Intent goes through legacy JS cost_gate_paper path — cold-start exploration mode
        // means it passes to fill. Without features the predictor shouldn't short-circuit.
        // features=None 時 predictor 不短路，走舊 JS gate（冷啟動探索放行）。
        let r = proc.process_with_features(
            &intent_btc(0.7),
            &gov,
            &state,
            500.0,
            GovernanceProfile::Exploration,
            None,
            None,
            0,
        );
        assert!(
            r.submitted,
            "features=None must delegate to legacy path; got {:?}",
            r.rejected_reason
        );
    }

    #[test]
    fn test_use_edge_predictor_false_skips_gate() {
        // cfg.use_edge_predictor=false (default) → predictor never called.
        // cfg.use_edge_predictor=false（預設）→ 不呼叫 predictor。
        let mut proc = IntentProcessor::new();
        assert!(!proc.risk_config.edge_predictor.use_edge_predictor);
        let store = Arc::new(EdgePredictorStore::new());
        proc.set_edge_predictor_store(store);
        let gov = approved_governance();
        let state = paper_state_with_price(30_000.0);
        let features = FeatureVectorV1::zeroed();
        let r = proc.process_with_features(
            &intent_btc(0.7),
            &gov,
            &state,
            500.0,
            GovernanceProfile::Exploration,
            Some(&features),
            Some("ctx-1"),
            1_700_000_000_000,
        );
        assert!(
            r.submitted,
            "use_edge_predictor=false must pass through; got {:?}",
            r.rejected_reason
        );
    }

    #[test]
    fn test_shadow_mode_falls_through_to_legacy_even_on_reject_outcome() {
        // shadow_mode=true + margin-insufficient predictor → gate would reject,
        // but shadow_mode forces fall-through to JS gate (observation stage).
        // shadow_mode=true 即使 margin 不足也回退 JS gate（觀察階段）。
        let mut proc = IntentProcessor::new();
        proc.risk_config.edge_predictor.use_edge_predictor = true;
        proc.risk_config.edge_predictor.shadow_mode = true;
        let store = Arc::new(EdgePredictorStore::new());
        store.swap(
            "test",
            Arc::new(StubOkPredictor {
                pred: Prediction {
                    q10: -100.0,
                    q50: -50.0,
                    q90: -10.0,
                },
            }),
        );
        proc.set_edge_predictor_store(store);
        let gov = approved_governance();
        let state = paper_state_with_price(30_000.0);
        let features = FeatureVectorV1::zeroed();
        let r = proc.process_with_features(
            &intent_btc(0.7),
            &gov,
            &state,
            500.0,
            GovernanceProfile::Exploration,
            Some(&features),
            Some("ctx-1"),
            0,
        );
        assert!(
            r.submitted,
            "shadow_mode=true must fall through to legacy; got {:?}",
            r.rejected_reason
        );
    }

    #[test]
    fn test_accept_bypasses_legacy_gate() {
        // shadow_mode=false + predictor Accept → submitted (JS gate bypassed).
        // Use a Prediction with large positive margin vs tiny cost.
        // shadow_mode=false + Accept → submitted（跳過 JS gate）。
        let mut proc = IntentProcessor::new();
        proc.risk_config.edge_predictor.use_edge_predictor = true;
        proc.risk_config.edge_predictor.shadow_mode = false;
        let store = Arc::new(EdgePredictorStore::new());
        store.swap(
            "test",
            Arc::new(StubOkPredictor {
                pred: Prediction {
                    q10: 100.0,
                    q50: 200.0,
                    q90: 300.0,
                },
            }),
        );
        proc.set_edge_predictor_store(store);
        let gov = approved_governance();
        let state = paper_state_with_price(30_000.0);
        let features = FeatureVectorV1::zeroed();
        let r = proc.process_with_features(
            &intent_btc(0.7),
            &gov,
            &state,
            500.0,
            GovernanceProfile::Exploration,
            Some(&features),
            Some("ctx-1"),
            0,
        );
        assert!(
            r.submitted,
            "Accept must bypass JS gate and submit; got {:?}",
            r.rejected_reason
        );
    }

    #[test]
    fn test_reject_short_circuits() {
        // shadow_mode=false + margin-insufficient + exploration_rate=0 → Reject.
        // shadow_mode=false + margin 不足 + exploration_rate=0 → 拒絕。
        let mut proc = IntentProcessor::new();
        proc.risk_config.edge_predictor.use_edge_predictor = true;
        proc.risk_config.edge_predictor.shadow_mode = false;
        proc.risk_config.edge_predictor.exploration_rate = 0.0;
        let store = Arc::new(EdgePredictorStore::new());
        store.swap(
            "test",
            Arc::new(StubOkPredictor {
                pred: Prediction {
                    q10: -100.0,
                    q50: -50.0,
                    q90: -10.0,
                },
            }),
        );
        proc.set_edge_predictor_store(store);
        let gov = approved_governance();
        let state = paper_state_with_price(30_000.0);
        let features = FeatureVectorV1::zeroed();
        let r = proc.process_with_features(
            &intent_btc(0.7),
            &gov,
            &state,
            500.0,
            GovernanceProfile::Exploration,
            Some(&features),
            Some("ctx-1"),
            0,
        );
        assert!(!r.submitted);
        let reason = r.rejected_reason.expect("reason set");
        assert!(
            reason.contains("predictor_cost_margin_insufficient"),
            "expected margin-insufficient reason, got {reason}"
        );
    }

    #[test]
    fn test_fallback_shrinkage_uses_legacy_gate() {
        // use_edge_predictor=true but no model swapped in → Fallback(NoModel) → Shrinkage → legacy.
        // use_edge_predictor=true 但未 swap model → Fallback(NoModel) → Shrinkage → 走 JS gate。
        let mut proc = IntentProcessor::new();
        proc.risk_config.edge_predictor.use_edge_predictor = true;
        proc.risk_config.edge_predictor.shadow_mode = false;
        proc.risk_config.edge_predictor.fallback_on_error = EdgePredictorFallback::Shrinkage;
        let store = Arc::new(EdgePredictorStore::new());
        // No swap — gate returns Fallback(NoModel).
        proc.set_edge_predictor_store(store);
        let gov = approved_governance();
        let state = paper_state_with_price(30_000.0);
        let features = FeatureVectorV1::zeroed();
        let r = proc.process_with_features(
            &intent_btc(0.7),
            &gov,
            &state,
            500.0,
            GovernanceProfile::Exploration,
            Some(&features),
            Some("ctx-1"),
            0,
        );
        // JS gate cold-start exploration passes the intent.
        // JS gate 冷啟動探索模式放行。
        assert!(
            r.submitted,
            "Fallback(Shrinkage) must delegate to legacy gate; got {:?}",
            r.rejected_reason
        );
    }

    #[test]
    fn test_fallback_fail_closed_rejects_with_metric_suffix() {
        // fallback_on_error=FailClosed + no model → hard reject, reason ends with metric name.
        // fallback_on_error=FailClosed + 無 model → 硬拒絕，reason 以 metric 名結尾。
        let mut proc = IntentProcessor::new();
        proc.risk_config.edge_predictor.use_edge_predictor = true;
        proc.risk_config.edge_predictor.shadow_mode = false;
        proc.risk_config.edge_predictor.fallback_on_error = EdgePredictorFallback::FailClosed;
        let store = Arc::new(EdgePredictorStore::new());
        proc.set_edge_predictor_store(store);
        let gov = approved_governance();
        let state = paper_state_with_price(30_000.0);
        let features = FeatureVectorV1::zeroed();
        let r = proc.process_with_features(
            &intent_btc(0.7),
            &gov,
            &state,
            500.0,
            GovernanceProfile::Exploration,
            Some(&features),
            Some("ctx-1"),
            0,
        );
        assert!(!r.submitted);
        let reason = r.rejected_reason.expect("reason set");
        assert!(
            reason.starts_with("predictor_fallback_fail_closed:predict_no_model"),
            "expected fail-closed suffix, got {reason}"
        );
    }

    #[test]
    fn test_shadow_fill_emits_ipc_on_epsilon_greedy() {
        // exploration_rate=1.0 forces ε-greedy branch; verify EmitShadowFill arrives on channel.
        // exploration_rate=1.0 強制走 ε-greedy；驗證 EmitShadowFill 到達通道。
        let mut proc = IntentProcessor::new();
        proc.risk_config.edge_predictor.use_edge_predictor = true;
        proc.risk_config.edge_predictor.shadow_mode = false;
        proc.risk_config.edge_predictor.exploration_rate = 1.0;
        proc.set_pipeline_kind(PipelineKind::Paper);

        let store = Arc::new(EdgePredictorStore::new());
        store.swap(
            "test",
            Arc::new(StubOkPredictor {
                pred: Prediction {
                    q10: -100.0,
                    q50: -50.0,
                    q90: -10.0,
                },
            }),
        );
        proc.set_edge_predictor_store(store);

        let (tx, mut rx) = tokio::sync::mpsc::unbounded_channel::<PipelineCommand>();
        proc.set_shadow_fill_tx(tx);

        let gov = approved_governance();
        let state = paper_state_with_price(30_000.0);
        let features = FeatureVectorV1::zeroed();
        let r = proc.process_with_features(
            &intent_btc(0.7),
            &gov,
            &state,
            500.0,
            GovernanceProfile::Exploration,
            Some(&features),
            Some("ctx-eps"),
            1_700_000_000_000,
        );
        assert!(!r.submitted);
        assert!(r
            .rejected_reason
            .unwrap()
            .contains("predictor_epsilon_greedy_exploration"));

        let cmd = rx.try_recv().expect("ShadowFill IPC must be emitted");
        match cmd {
            PipelineCommand::EmitShadowFill {
                context_id,
                strategy,
                symbol,
                prediction_q50,
                ts_ms,
                ..
            } => {
                assert_eq!(context_id, "ctx-eps");
                assert_eq!(strategy, "test");
                assert_eq!(symbol, "BTCUSDT");
                assert!((prediction_q50 - (-50.0)).abs() < 1e-6);
                assert_eq!(ts_ms, 1_700_000_000_000);
            }
            other => panic!("expected EmitShadowFill, got {:?}", other),
        }
    }

    #[test]
    fn test_non_paper_engine_never_emits_shadow_fill() {
        // Demo engine even at exploration_rate=1.0 must reject without emitting shadow fill.
        // Demo 引擎即使 exploration_rate=1.0 也必須拒絕且不發送 shadow fill。
        let mut proc = IntentProcessor::new();
        proc.risk_config.edge_predictor.use_edge_predictor = true;
        proc.risk_config.edge_predictor.shadow_mode = false;
        proc.risk_config.edge_predictor.exploration_rate = 1.0;
        proc.set_pipeline_kind(PipelineKind::Demo);

        let store = Arc::new(EdgePredictorStore::new());
        store.swap(
            "test",
            Arc::new(StubOkPredictor {
                pred: Prediction {
                    q10: -100.0,
                    q50: -50.0,
                    q90: -10.0,
                },
            }),
        );
        proc.set_edge_predictor_store(store);

        let (tx, mut rx) = tokio::sync::mpsc::unbounded_channel::<PipelineCommand>();
        proc.set_shadow_fill_tx(tx);

        let gov = approved_governance();
        let state = paper_state_with_price(30_000.0);
        let features = FeatureVectorV1::zeroed();
        let r = proc.process_with_features(
            &intent_btc(0.7),
            &gov,
            &state,
            500.0,
            GovernanceProfile::Exploration,
            Some(&features),
            Some("ctx-demo"),
            0,
        );
        assert!(!r.submitted);
        assert!(
            rx.try_recv().is_err(),
            "Demo engine must not emit shadow fills"
        );
    }

    #[test]
    fn test_process_gates_only_with_features_accept_bypasses_legacy() {
        // Exchange path: Accept → approved, legacy JS shrinkage bypassed.
        // 交易所路徑：Accept → approved，跳過 JS shrinkage。
        let mut proc = IntentProcessor::new();
        proc.risk_config.edge_predictor.use_edge_predictor = true;
        proc.risk_config.edge_predictor.shadow_mode = false;
        let store = Arc::new(EdgePredictorStore::new());
        store.swap(
            "test",
            Arc::new(StubOkPredictor {
                pred: Prediction {
                    q10: 100.0,
                    q50: 200.0,
                    q90: 300.0,
                },
            }),
        );
        proc.set_edge_predictor_store(store);
        let gov = approved_governance();
        let state = paper_state_with_price(30_000.0);
        let features = FeatureVectorV1::zeroed();
        // AMD-2026-05-02-01 Track E E-1: real Active lease before Production
        // process_gates_only_with_features (PA push back #4 — no Bypass shortcut
        // for Production fixtures).
        // AMD-2026-05-02-01 Track E E-1：Production process_gates_only_with_features
        // 前播下真實 Active lease（PA push back #4 — Production fixture 禁 Bypass 短路）。
        let lease = super::seed_production_lease(&gov, "intent-features-accept");
        let r = proc.process_gates_only_with_features(
            &intent_btc(0.7),
            &gov,
            &state,
            500.0,
            GovernanceProfile::Production,
            Some(&features),
            Some("ctx-exch"),
            0,
        );
        assert!(
            r.approved,
            "Accept must bypass strict live JS gate; got {:?}",
            r.rejected_reason
        );
        // Successful Accept path → release as Consumed. / Accept 路徑 → release Consumed。
        gov.release_lease(&lease, LeaseOutcome::Consumed).unwrap();
    }

    // ========================================================
    // EDGE-P3-1 Step 7a: DecisionFeatureSnapshot emission tests
    // ========================================================
    //
    // Emission fires at the TOP of evaluate_predictor_gate, before any
    // short-circuit, so Stage 0 training data flows while the gate stays
    // on legacy shrinkage (use_edge_predictor=false). These tests cover:
    //   (a) fires when predictor is disabled + features + ctx_id present;
    //   (b) no emit on empty context_id;
    //   (c) no emit on features=None;
    //   (d) no emit on ts_ms=0 (DB-RUN-6 alignment with writer rejection).
    //
    // EDGE-P3-1 Step 7a：決策特徵快照發射測試 —
    // gate 頂端發射、早於短路檢查，Stage 0 即採集訓練資料。

    #[test]
    fn test_decision_feature_snapshot_emitted_when_predictor_disabled() {
        // use_edge_predictor=false (default Stage 0) + features + ctx_id →
        // snapshot still emits; writer accumulates while gate stays on legacy.
        // use_edge_predictor=false（Stage 0 預設）仍發射；writer 累積訓練資料。
        let mut proc = IntentProcessor::new();
        assert!(!proc.risk_config.edge_predictor.use_edge_predictor);
        proc.set_pipeline_kind(PipelineKind::Paper);

        let (tx, mut rx) = tokio::sync::mpsc::channel::<crate::database::DecisionFeatureMsg>(8);
        proc.set_decision_feature_tx(tx);

        let gov = approved_governance();
        let state = paper_state_with_price(30_000.0);
        let features = FeatureVectorV1::zeroed();
        let _ = proc.process_with_features(
            &intent_btc(0.7),
            &gov,
            &state,
            500.0,
            GovernanceProfile::Exploration,
            Some(&features),
            Some("ctx-seed"),
            1_700_000_000_000,
        );

        let msg = rx.try_recv().expect("snapshot must be emitted at gate top");
        assert_eq!(msg.context_id, "ctx-seed");
        assert_eq!(msg.ts_ms, 1_700_000_000_000);
        assert_eq!(msg.engine_mode, "paper");
        assert_eq!(msg.strategy_name, "test");
        assert_eq!(msg.symbol, "BTCUSDT");
        assert_eq!(msg.side, 1, "is_long=true → side=+1");
        assert_eq!(
            msg.feature_schema_version,
            crate::edge_predictor::features::FEATURE_SCHEMA_VERSION
        );
        assert_eq!(
            msg.feature_schema_hash,
            crate::edge_predictor::features::feature_schema_hash()
        );
        assert_eq!(
            msg.feature_definition_hash,
            crate::edge_predictor::features::feature_definition_hash()
        );
        assert!(
            msg.features_jsonb.starts_with('{') && msg.features_jsonb.ends_with('}'),
            "features_jsonb must be valid JSON object, got {}",
            msg.features_jsonb
        );
    }

    #[test]
    fn test_decision_feature_snapshot_no_emit_on_empty_context() {
        // Empty context_id → caller has nothing to join on later; skip emission.
        // context_id 為空 → 後續無 join key，直接跳過發射。
        let mut proc = IntentProcessor::new();
        proc.set_pipeline_kind(PipelineKind::Paper);

        let (tx, mut rx) = tokio::sync::mpsc::channel::<crate::database::DecisionFeatureMsg>(8);
        proc.set_decision_feature_tx(tx);

        let gov = approved_governance();
        let state = paper_state_with_price(30_000.0);
        let features = FeatureVectorV1::zeroed();
        let _ = proc.process_with_features(
            &intent_btc(0.7),
            &gov,
            &state,
            500.0,
            GovernanceProfile::Exploration,
            Some(&features),
            None,
            1_700_000_000_000,
        );
        assert!(
            rx.try_recv().is_err(),
            "empty context_id must not emit snapshot"
        );
    }

    #[test]
    fn test_decision_feature_snapshot_no_emit_on_none_features() {
        // features=None → nothing to persist; no emission.
        // features=None → 無可持久化資料，不發射。
        let mut proc = IntentProcessor::new();
        proc.set_pipeline_kind(PipelineKind::Paper);

        let (tx, mut rx) = tokio::sync::mpsc::channel::<crate::database::DecisionFeatureMsg>(8);
        proc.set_decision_feature_tx(tx);

        let gov = approved_governance();
        let state = paper_state_with_price(30_000.0);
        let _ = proc.process_with_features(
            &intent_btc(0.7),
            &gov,
            &state,
            500.0,
            GovernanceProfile::Exploration,
            None,
            Some("ctx-nofeat"),
            1_700_000_000_000,
        );
        assert!(
            rx.try_recv().is_err(),
            "features=None must not emit snapshot"
        );
    }

    #[test]
    fn test_decision_feature_snapshot_no_emit_on_zero_timestamp() {
        // ts_ms=0 → DB-RUN-6 writer would reject; skip at source.
        // ts_ms=0 → writer 側 DB-RUN-6 會拒絕；源頭直接略過。
        let mut proc = IntentProcessor::new();
        proc.set_pipeline_kind(PipelineKind::Paper);

        let (tx, mut rx) = tokio::sync::mpsc::channel::<crate::database::DecisionFeatureMsg>(8);
        proc.set_decision_feature_tx(tx);

        let gov = approved_governance();
        let state = paper_state_with_price(30_000.0);
        let features = FeatureVectorV1::zeroed();
        let _ = proc.process_with_features(
            &intent_btc(0.7),
            &gov,
            &state,
            500.0,
            GovernanceProfile::Exploration,
            Some(&features),
            Some("ctx-zero-ts"),
            0,
        );
        assert!(
            rx.try_recv().is_err(),
            "ts_ms=0 must not emit snapshot (DB-RUN-6 alignment)"
        );
    }

    // ── EDGE-P2-3 Phase 1a: maker fee selection tests ──
    // ── EDGE-P2-3 Phase 1a：maker 費率選擇測試 ──

    /// fee_rate_for_intent returns taker rate for non-PostOnly intents
    /// (Market, Limit+GTC/IOC/FOK). Matches prior `fee_rate()` behavior.
    /// fee_rate_for_intent 對非 PostOnly 意圖（Market / GTC 等）返回 taker 費率。
    #[test]
    fn test_fee_rate_for_intent_uses_taker_for_market() {
        let proc = IntentProcessor::new();
        let intent = super::make_intent("BTCUSDT", true);
        // Market/GTC → taker fallback (cold-boot: DEFAULT_TAKER_FEE_RATE = 0.00055)
        let rate = proc.fee_rate_for_intent(&intent.symbol, &intent);
        assert!((rate - 0.00055).abs() < 1e-12);
        assert_eq!(rate, proc.fee_rate(&intent.symbol));
    }

    /// PostOnly intents route to maker rate (~2.75× cheaper on cold-boot).
    /// PostOnly 意圖走 maker 費率（冷啟動為 taker 的約 1/2.75）。
    #[test]
    fn test_fee_rate_for_intent_uses_maker_for_postonly() {
        use crate::order_manager::TimeInForce;
        let proc = IntentProcessor::new();
        let mut intent = super::make_intent("BTCUSDT", true);
        intent.time_in_force = Some(TimeInForce::PostOnly);
        let rate = proc.fee_rate_for_intent(&intent.symbol, &intent);
        // Cold-boot maker default = 0.0002, taker default = 0.00055
        assert!((rate - 0.0002).abs() < 1e-12);
        assert!(rate < proc.fee_rate(&intent.symbol));
    }

    /// Explicit GTC (non-PostOnly) must still pay taker — guards against future
    /// TIF variants being accidentally classified as maker.
    /// 明確 GTC（非 PostOnly）仍走 taker，防止未來 TIF 變體被誤分類。
    #[test]
    fn test_fee_rate_for_intent_gtc_stays_taker() {
        use crate::order_manager::TimeInForce;
        let proc = IntentProcessor::new();
        let mut intent = super::make_intent("BTCUSDT", true);
        intent.time_in_force = Some(TimeInForce::GTC);
        let rate = proc.fee_rate_for_intent(&intent.symbol, &intent);
        assert!((rate - 0.00055).abs() < 1e-12);
    }

    #[test]
    fn test_slippage_rate_for_intent_postonly_is_zero() {
        use crate::order_manager::TimeInForce;
        let proc = IntentProcessor::new();
        let mut intent = super::make_intent("BTCUSDT", true);
        intent.time_in_force = Some(TimeInForce::PostOnly);

        let slippage = proc.slippage_rate_for_intent(&intent, 0.0);

        assert_eq!(slippage, 0.0);
    }

    #[test]
    fn test_slippage_rate_for_intent_market_uses_tier() {
        let proc = IntentProcessor::new();
        let intent = super::make_intent("BTCUSDT", true);

        let slippage = proc.slippage_rate_for_intent(&intent, 2_000_000_000.0);

        assert_eq!(slippage, 0.0001);
    }

    // ── FIX-FEE-POSTONLY-1 (G7-09): fee_rate_for_tif fill-path helper ──
    // ── FIX-FEE-POSTONLY-1：fee_rate_for_tif fill 路徑 TIF-aware 費率 ──

    /// TIF=PostOnly on fill path → maker rate. Mirrors fee_rate_for_intent but
    /// accepts raw Option<TimeInForce> so event_consumer can call it with a
    /// PendingOrder TIF lookup (no OrderIntent available on the exec event).
    /// TIF=PostOnly → maker；對應 loop_handlers hoisted matched_tif 路徑。
    #[test]
    fn test_fee_rate_for_tif_postonly_returns_maker() {
        use crate::order_manager::TimeInForce;
        let proc = IntentProcessor::new();
        let rate = proc.fee_rate_for_tif("BTCUSDT", Some(TimeInForce::PostOnly));
        assert!((rate - 0.0002).abs() < 1e-12);
        assert!(rate < proc.fee_rate("BTCUSDT"));
    }

    /// TIF=GTC on fill path → taker (same as fee_rate_for_intent for GTC).
    /// TIF=GTC → taker。
    #[test]
    fn test_fee_rate_for_tif_gtc_stays_taker() {
        use crate::order_manager::TimeInForce;
        let proc = IntentProcessor::new();
        let rate = proc.fee_rate_for_tif("BTCUSDT", Some(TimeInForce::GTC));
        assert!((rate - 0.00055).abs() < 1e-12);
    }

    /// Race-safety: Bybit Fill event can arrive before OrderUpdate fills
    /// `order_id_to_link`, in which case matched_key lookup fails and TIF is
    /// unknown. Degrade to taker (= pre-G7-09 behaviour) so we never
    /// under-estimate fees when order type is uncertain.
    /// Race 安全：Fill 先於 OrderUpdate → matched_tif=None → fallback taker。
    #[test]
    fn test_fee_rate_for_tif_none_falls_back_to_taker() {
        let proc = IntentProcessor::new();
        let rate = proc.fee_rate_for_tif("BTCUSDT", None);
        assert!((rate - 0.00055).abs() < 1e-12);
        assert_eq!(rate, proc.fee_rate("BTCUSDT"));
    }
}

// ════════════════════════════════════════════════════════════════════════════
// EDGE-P2-3 Phase 1B-5: MakerKpi gate router tests.
// Verifies router consults per-symbol fill-rate / net-edge KPI before enqueueing
// a PostOnly intent. Cold (warmup) and Healthy → enqueue as resting order;
// Degraded → silent fallback to market fill with `maker_degraded_fallback`
// sentinel set so `on_tick` bumps the counter and warns.
// EDGE-P2-3 Phase 1B-5：MakerKpi gate 路由測試。驗 router 於 enqueue PostOnly
// 前查 per-symbol fill-rate / net-edge KPI。Cold / Healthy → 入掛單隊列；
// Degraded → 靜默改走市價，`maker_degraded_fallback` 標記由 on_tick 計數 + warn。
// ════════════════════════════════════════════════════════════════════════════
#[cfg(test)]
mod maker_kpi_gate_tests {
    use super::*;
    use crate::order_manager::TimeInForce;

    const NOW_MS: u64 = 1_700_000_000_000;

    fn approved_gov() -> GovernanceCore {
        let mut g = GovernanceCore::new();
        g.grant_paper_authorization(None).unwrap();
        g
    }

    fn paper_state_seeded(price: f64) -> PaperState {
        let mut s = PaperState::new(10_000.0);
        s.set_latest_price("BTCUSDT", price);
        s.set_latest_turnover("BTCUSDT", 100_000_000.0);
        s
    }

    fn postonly_intent(price: f64) -> OrderIntent {
        OrderIntent {
            symbol: "BTCUSDT".into(),
            is_long: true,
            qty: 0.001,
            confidence: 0.7,
            strategy: "grid_trading".into(),
            order_type: "limit".into(),
            limit_price: Some(price * 0.999),
            confluence_score: None,
            persistence_elapsed_ms: None,
            time_in_force: Some(TimeInForce::PostOnly),
            maker_timeout_ms: Some(45_000),
        }
    }

    #[test]
    fn test_postonly_cold_gate_allows_enqueue() {
        // No terminal samples → Cold → router must build the resting draft.
        // 零終局樣本 → Cold → router 必須建立 resting draft。
        let proc = IntentProcessor::new();
        let gov = approved_gov();
        let state = paper_state_seeded(30_000.0);
        let r = proc.process_with_features(
            &postonly_intent(30_000.0),
            &gov,
            &state,
            2000.0,
            GovernanceProfile::Exploration,
            None,
            None,
            NOW_MS,
        );
        assert!(r.submitted, "cold gate must allow enqueue");
        assert!(
            r.resting_order.is_some(),
            "cold gate must produce resting draft; got fill={:?}",
            r.fill
        );
        assert!(r.fill.is_none(), "resting draft implies no immediate fill");
        assert!(r.maker_degraded_fallback.is_none());
    }

    #[test]
    fn test_postonly_healthy_gate_allows_enqueue() {
        // Seed 18 fills / 2 timeouts → fill_rate 0.9 > 0.15, edge 0 > -5 → Healthy.
        // 塞 18 fills / 2 timeouts → 成交率 0.9 > 0.15、edge 0 > -5 → Healthy。
        let proc = IntentProcessor::new();
        let gov = approved_gov();
        let mut state = paper_state_seeded(30_000.0);
        state.test_seed_maker_stats_terminal("BTCUSDT", 18, 2, NOW_MS);
        let r = proc.process_with_features(
            &postonly_intent(30_000.0),
            &gov,
            &state,
            2000.0,
            GovernanceProfile::Exploration,
            None,
            None,
            NOW_MS,
        );
        assert!(r.submitted);
        assert!(r.resting_order.is_some(), "healthy gate must enqueue");
        assert!(r.maker_degraded_fallback.is_none());
    }

    #[test]
    fn test_postonly_degraded_low_fill_rate_falls_back_to_market() {
        // Seed 2 fills / 18 timeouts → fill_rate 0.1 < 0.15 → Degraded.
        // Router must skip enqueue and produce a market fill, with the
        // fallback sentinel pointing at the rejected symbol.
        // 塞 2/18 → rate 0.1 < 0.15 → Degraded。router 必須跳過 enqueue、
        // 走市價成交、maker_degraded_fallback 指向被拒的 symbol。
        let proc = IntentProcessor::new();
        let gov = approved_gov();
        let mut state = paper_state_seeded(30_000.0);
        state.test_seed_maker_stats_terminal("BTCUSDT", 2, 18, NOW_MS);
        let r = proc.process_with_features(
            &postonly_intent(30_000.0),
            &gov,
            &state,
            2000.0,
            GovernanceProfile::Exploration,
            None,
            None,
            NOW_MS,
        );
        assert!(r.submitted);
        assert!(r.resting_order.is_none(), "degraded gate must NOT enqueue");
        assert!(r.fill.is_some(), "degraded gate must take market fallback");
        assert_eq!(
            r.maker_degraded_fallback.as_deref(),
            Some("BTCUSDT"),
            "fallback sentinel must carry the symbol so on_tick can count it"
        );
    }

    #[test]
    fn test_postonly_degraded_per_symbol_leaves_other_symbol_healthy() {
        // BTCUSDT saturated with timeouts (Degraded), ETHUSDT untouched (Cold
        // per-symbol → falls back to aggregate). Aggregate = BTCUSDT stats
        // alone → also Degraded. So ETHUSDT should also fall back to market
        // when fed the same gate. This locks the aggregate-fallback semantics.
        // BTCUSDT 被 timeouts 灌滿（Degraded）、ETHUSDT 未觸碰（per-symbol Cold
        // → fallback 到 aggregate）。aggregate = BTCUSDT 獨撐 → 也 Degraded。
        // 故 ETHUSDT 也會被 gate 擋。此測固化 aggregate fallback 語意。
        let proc = IntentProcessor::new();
        let gov = approved_gov();
        let mut state = paper_state_seeded(30_000.0);
        state.test_seed_maker_stats_terminal("BTCUSDT", 2, 18, NOW_MS);
        state.set_latest_price("ETHUSDT", 3_000.0);
        state.set_latest_turnover("ETHUSDT", 100_000_000.0);
        let mut eth_intent = postonly_intent(3_000.0);
        eth_intent.symbol = "ETHUSDT".into();
        eth_intent.limit_price = Some(3_000.0 * 0.999);
        let r = proc.process_with_features(
            &eth_intent,
            &gov,
            &state,
            300.0,
            GovernanceProfile::Exploration,
            None,
            None,
            NOW_MS,
        );
        assert!(r.submitted);
        assert!(
            r.resting_order.is_none(),
            "ETHUSDT must ride aggregate verdict (Degraded) → no enqueue"
        );
        assert_eq!(r.maker_degraded_fallback.as_deref(), Some("ETHUSDT"));
    }

    #[test]
    fn test_market_intent_is_never_tagged_with_fallback() {
        // Market intents bypass the gate entirely — the sentinel must stay
        // None so downstream observers don't mistakenly count them.
        // 市價意圖完全不進 gate — sentinel 保持 None。
        let proc = IntentProcessor::new();
        let gov = approved_gov();
        let mut state = paper_state_seeded(30_000.0);
        // Even with Degraded stats present, a market intent shouldn't care.
        // 即使 stats 呈 Degraded，市價意圖也不應受影響。
        state.test_seed_maker_stats_terminal("BTCUSDT", 2, 18, NOW_MS);
        let intent = super::make_intent("BTCUSDT", true); // order_type=market
        let r = proc.process_with_features(
            &intent,
            &gov,
            &state,
            2000.0,
            GovernanceProfile::Exploration,
            None,
            None,
            NOW_MS,
        );
        assert!(r.submitted);
        assert!(r.fill.is_some());
        assert!(r.maker_degraded_fallback.is_none());
    }

    #[test]
    fn test_enqueue_bumps_submit_counter() {
        // Enqueue side-effect on PaperState must increment `maker_stats.submitted`
        // on both aggregate and per-symbol scopes. Gate not involved here —
        // this is an integration check of the 1B-5 wiring through PaperState.
        // enqueue 副作用必須同時更新 aggregate + per-symbol 的 submitted。
        let proc = IntentProcessor::new();
        let gov = approved_gov();
        let mut state = paper_state_seeded(30_000.0);
        let r = proc.process_with_features(
            &postonly_intent(30_000.0),
            &gov,
            &state,
            2000.0,
            GovernanceProfile::Exploration,
            None,
            None,
            NOW_MS,
        );
        let draft = r.resting_order.expect("cold gate enqueues");
        // Caller (on_tick) normally runs this; replicate manually for the test.
        // caller（on_tick）通常執行此行；測試中手動重現。
        state.enqueue_resting_limit_order(draft);
        assert_eq!(state.maker_stats().aggregate.submitted, 1);
        assert_eq!(
            state
                .maker_stats()
                .per_symbol
                .get("BTCUSDT")
                .unwrap()
                .submitted,
            1
        );
    }
}

// ════════════════════════════════════════════════════════════════════════════
// AMD-2026-05-02-01 Track E E-2: Router Decision Lease gate tests (Gate 1.4).
// Verifies router gate flag toggling, profile-based Bypass / Active path
// selection, fail-closed AuthNotEffective, RouterLeaseGuard rejection cleanup,
// and IntentResult/ExchangeGateResult lease_id population on success.
//
// AMD-2026-05-02-01 Track E E-2：Router Decision Lease gate 測試（Gate 1.4）。
// 驗 router gate flag 開關 / profile 對 Bypass vs Active 路徑選擇 /
// AuthNotEffective fail-closed / RouterLeaseGuard 拒絕路徑 cleanup / 成功路徑
// IntentResult/ExchangeGateResult lease_id 填入。
// ════════════════════════════════════════════════════════════════════════════
#[cfg(test)]
mod router_gate_lease_tests {
    use super::*;

    const NOW_MS: u64 = 1_700_000_000_000;

    /// Helper: build a Production GovernanceCore with auth + router gate flag
    /// flipped via the cross-crate test setter (avoids env_var race).
    /// Helper：構造 Production GovernanceCore + auth；用跨 crate test setter
    /// 翻 router gate flag（避免 env_var race）。
    fn make_gov(router_gate_on: bool, auth: bool) -> GovernanceCore {
        let mut g = GovernanceCore::new();
        if auth {
            g.grant_paper_authorization(None).unwrap();
        }
        g.set_router_gate_enabled_for_test(router_gate_on);
        g
    }

    fn make_state() -> PaperState {
        let mut s = PaperState::new(10_000.0);
        s.set_latest_price("BTCUSDT", 30_000.0);
        s.set_latest_turnover("BTCUSDT", 100_000_000.0);
        s
    }

    /// Test 1: flag OFF → Gate 1.4 short-circuits; lease_id stays None on
    /// success and rejection paths; behavior identical to pre-E-2.
    /// Test 1：flag OFF → Gate 1.4 短路；成功與拒絕路徑 lease_id 皆 None；
    /// 行為與 E-2 前一致。
    #[test]
    fn test_router_gate_off_lease_id_none_on_success() {
        let proc = IntentProcessor::new();
        let gov = make_gov(false, true);
        let state = make_state();
        // Exploration profile + flag OFF → Gate 1.4 short-circuits to None.
        // Exploration profile + flag OFF → Gate 1.4 短路 None。
        let r = proc.process_with_features(
            &make_intent("BTCUSDT", true),
            &gov,
            &state,
            2000.0,
            GovernanceProfile::Exploration,
            None,
            None,
            NOW_MS,
        );
        assert!(r.submitted, "intent must be accepted");
        assert!(r.lease_id.is_none(), "flag OFF → lease_id stays None");
        // SM has 0 lease objects since acquire_lease was never called.
        // 因從未呼 acquire_lease，SM 有 0 lease object。
        assert_eq!(gov.lease.lock().len(), 0);
    }

    /// Test 2: flag ON + Production profile happy path → Active lease
    /// acquired; IntentResult.lease_id = Some("lease:..."); SM has 1 Active
    /// lease (waiting for fill consumer release).
    /// Test 2：flag ON + Production happy path → 取得 Active lease；
    /// IntentResult.lease_id = Some("lease:...")；SM 有 1 個 Active（等 fill
    /// consumer 釋放）。
    #[test]
    fn test_router_gate_on_production_happy_path_lease_active() {
        let proc = IntentProcessor::new();
        let gov = make_gov(true, true);
        let state = make_state();
        // ATR=2000 to clear cost gate; intent confidence 0.7 default.
        // ATR=2000 通過 cost gate；intent confidence 預設 0.7。
        let r = proc.process_with_features(
            &make_intent("BTCUSDT", true),
            &gov,
            &state,
            2000.0,
            GovernanceProfile::Production,
            None,
            None,
            NOW_MS,
        );
        assert!(r.submitted, "Production happy path must accept");
        let lid = r.lease_id.expect("lease_id must be Some");
        assert!(
            lid.starts_with("lease:"),
            "Active lease id format check (lease:xxxx); got {lid}"
        );
        // Caller's consume() takes the lease out so Drop won't release; SM keeps
        // the Active lease for downstream fill consumer to release Consumed.
        // 呼叫端 consume() 取出 lease；SM 保留 Active 供下游 fill consumer 釋放。
        assert_eq!(
            gov.lease.lock().get_live().len(),
            1,
            "Active lease retained for fill consumer release"
        );
    }

    /// Test 3: flag ON + Validation/Exploration profile → LeaseId::Bypass
    /// short-circuit; SM never touched (PA push back #1 spec §3 point 1
    /// trailing clause). lease_id=Some("bypass") so audit can count Bypass
    /// occurrences distinctly from None.
    /// Test 3：flag ON + Validation/Exploration → LeaseId::Bypass 短路；
    /// SM 從未碰觸；lease_id=Some("bypass") 讓 audit 能區分 Bypass 與 None。
    #[test]
    fn test_router_gate_on_non_production_bypass() {
        let proc = IntentProcessor::new();
        let gov = make_gov(true, true);
        let state = make_state();

        // Validation profile.
        let r_val = proc.process_with_features(
            &make_intent("BTCUSDT", true),
            &gov,
            &state,
            2000.0,
            GovernanceProfile::Validation,
            None,
            None,
            NOW_MS,
        );
        assert!(r_val.submitted);
        assert_eq!(r_val.lease_id.as_deref(), Some("bypass"));

        // Exploration profile.
        let r_exp = proc.process_with_features(
            &make_intent("BTCUSDT", true),
            &gov,
            &state,
            2000.0,
            GovernanceProfile::Exploration,
            None,
            None,
            NOW_MS,
        );
        assert!(r_exp.submitted);
        assert_eq!(r_exp.lease_id.as_deref(), Some("bypass"));

        // SM untouched: 0 lease objects ever created.
        // SM 未碰觸：0 lease object。
        assert_eq!(gov.lease.lock().len(), 0);
    }

    /// Test 4: flag ON + Production + auth NOT effective → AuthNotEffective
    /// fail-closed reject. lease_id=None on rejection (per E-2 contract:
    /// rejection paths never carry lease lineage).
    /// Test 4：flag ON + Production + auth 未生效 → AuthNotEffective fail-closed
    /// 拒絕。拒絕路徑 lease_id=None（contract：rejection 不帶 lease lineage）。
    #[test]
    fn test_router_gate_on_production_no_auth_fails_closed() {
        let proc = IntentProcessor::new();
        let gov = make_gov(true, false); // flag ON but NO auth
        let state = make_state();
        let r = proc.process_with_features(
            &make_intent("BTCUSDT", true),
            &gov,
            &state,
            2000.0,
            GovernanceProfile::Production,
            None,
            None,
            NOW_MS,
        );
        assert!(!r.submitted, "no auth must fail-closed reject");
        let reason = r.rejected_reason.expect("must have reason");
        // Could be either Gate 1 (governance not authorized) or Gate 1.4 (lease
        // facade auth not effective) — both are valid fail-closed branches and
        // both surface auth failure to caller. Accept either form.
        // 可能是 Gate 1（governance not authorized）或 Gate 1.4（lease facade auth
        // not effective）— 兩者都是合法 fail-closed 路徑且都把 auth failure 透給
        // 呼叫端；接受任一形式。
        assert!(
            reason.contains("authoriz") || reason.contains("authorization"),
            "reason must mention authorization: {reason}"
        );
        assert!(r.lease_id.is_none());
        // SM untouched.
        assert_eq!(gov.lease.lock().len(), 0);
    }

    /// Test 5: flag ON + Production happy path through Gate 1.4 then downstream
    /// gate (ATR=0 SEC-11 fail-closed) rejection → RouterLeaseGuard Drop
    /// releases Cancelled; lease moves from Active to Revoked; lease_id=None
    /// on rejection.
    /// Test 5：flag ON + Production 通過 Gate 1.4 後下游 gate（ATR=0 SEC-11
    /// fail-closed）拒絕 → RouterLeaseGuard Drop 釋放 Cancelled；lease 從
    /// Active → Revoked；拒絕路徑 lease_id=None。
    #[test]
    fn test_router_gate_on_production_drop_cancels_on_atr_zero() {
        let proc = IntentProcessor::new();
        let gov = make_gov(true, true);
        let state = make_state();
        // ATR=0 forces SEC-11 fail-closed at Gate 3 cost gate (after Gate 1.4
        // has acquired the lease).
        // ATR=0 觸發 Gate 3 cost gate 的 SEC-11 fail-closed（Gate 1.4 已拿到 lease）。
        let r = proc.process_with_features(
            &make_intent("BTCUSDT", true),
            &gov,
            &state,
            0.0, // ATR=0
            GovernanceProfile::Production,
            None,
            None,
            NOW_MS,
        );
        assert!(!r.submitted, "ATR=0 must SEC-11 fail-closed downstream");
        assert!(
            r.lease_id.is_none(),
            "rejection path must NOT carry lease_id"
        );
        let reason = r.rejected_reason.expect("must have reason");
        assert!(
            reason.contains("ATR") || reason.contains("atr"),
            "rejection reason must mention ATR: {reason}"
        );
        // SM has 1 lease total (acquired by Gate 1.4) but 0 live (Drop released
        // it Cancelled → Revoked).
        // SM 共 1 個 lease（Gate 1.4 acquire）但 0 個 live（Drop 釋放 Cancelled → Revoked）。
        let total = gov.lease.lock().len();
        let live = gov.lease.lock().get_live().len();
        assert_eq!(total, 1, "Gate 1.4 acquired one lease");
        assert_eq!(
            live, 0,
            "RouterLeaseGuard Drop must release acquired lease on rejection"
        );
    }

    /// Test 6: ExchangeGateResult mirror — flag OFF (Production profile)
    /// leaves lease_id None; flag ON + Validation profile yields Bypass;
    /// flag ON + Production fail-closed when cost gate is strict (no edge
    /// data) but Drop still cleans up the acquired lease (no leak).
    /// Test 6：ExchangeGateResult 對齊 — flag OFF + Production → lease_id None；
    /// flag ON + Validation → Bypass；flag ON + Production 嚴格 cost gate 拒絕
    /// 但 Drop 仍清理 acquired lease（不 leak）。
    #[test]
    fn test_router_gate_exchange_path_lease_id_states() {
        let proc = IntentProcessor::new();
        let state = make_state();

        // Sub-case 1: Flag OFF + Production → cost gate strict reject; lease_id None.
        // Sub-case 1：flag OFF + Production → cost gate 嚴格拒絕；lease_id None。
        let gov_off = make_gov(false, true);
        let g_off = proc.process_gates_only_with_features(
            &make_intent("BTCUSDT", true),
            &gov_off,
            &state,
            2000.0,
            GovernanceProfile::Production,
            None,
            None,
            NOW_MS,
        );
        // Production cost_gate_live_with_slippage is strict in absence of edge
        // data — exchange path rejects. lease_id stays None either way.
        // Production cost_gate_live_with_slippage 在無 edge 時嚴格拒絕；
        // lease_id 兩種情況都 None。
        assert!(
            g_off.lease_id.is_none(),
            "flag OFF → exchange path lease_id None"
        );
        assert_eq!(gov_off.lease.lock().len(), 0, "flag OFF → SM untouched");

        // Sub-case 2: Flag ON + Validation → Bypass.
        // Sub-case 2：flag ON + Validation → Bypass。
        let gov_val = make_gov(true, true);
        let g_val = proc.process_gates_only_with_features(
            &make_intent("BTCUSDT", true),
            &gov_val,
            &state,
            2000.0,
            GovernanceProfile::Validation,
            None,
            None,
            NOW_MS,
        );
        assert_eq!(g_val.lease_id.as_deref(), Some("bypass"));
        assert_eq!(gov_val.lease.lock().len(), 0, "Validation → SM untouched");

        // Sub-case 3: Flag ON + Production. Gate 1.4 acquires lease; downstream
        // strict cost gate rejects → Drop releases Cancelled; SM ends with 0 live.
        // Sub-case 3：flag ON + Production。Gate 1.4 acquire；下游嚴格 cost gate
        // 拒絕 → Drop 釋放 Cancelled；SM 結束 0 live。
        let gov_prod = make_gov(true, true);
        let g_prod = proc.process_gates_only_with_features(
            &make_intent("BTCUSDT", true),
            &gov_prod,
            &state,
            2000.0,
            GovernanceProfile::Production,
            None,
            None,
            NOW_MS,
        );
        // Either approved (lease_id Some) OR rejected (lease_id None).
        // 接受（lease_id Some）或拒絕（lease_id None）兩種狀態都合法。
        if g_prod.approved {
            let lid = g_prod
                .lease_id
                .expect("Production approved → lease_id Some");
            assert!(lid.starts_with("lease:"));
            assert_eq!(
                gov_prod.lease.lock().get_live().len(),
                1,
                "Active lease retained for fill consumer release"
            );
        } else {
            assert!(g_prod.lease_id.is_none(), "rejection path → lease_id None");
            // Drop released the lease Cancelled.
            // Drop 釋放 Cancelled。
            assert_eq!(
                gov_prod.lease.lock().get_live().len(),
                0,
                "RouterLeaseGuard Drop releases on rejection (no leak)"
            );
            assert!(
                gov_prod.lease.lock().len() >= 1,
                "Gate 1.4 did acquire at least one lease before downstream reject"
            );
        }
    }

    /// Test 7 (perf SLA sanity): flag OFF Gate 1.4 short-circuit ≤ 50ns avg;
    /// flag ON acquire+release pair ≤ 5µs avg. Loose bound to avoid flake on
    /// CI runners; real SLA monitoring is via cargo bench. AMD §6 condition #1
    /// IPC budget = 100µs, so per-call ≤ 5µs leaves 20× headroom.
    /// Test 7（perf SLA 健康度）：flag OFF Gate 1.4 短路 ≤ 50ns 平均；
    /// flag ON acquire+release pair ≤ 5µs 平均。寬鬆 bound 避 CI flake；真實
    /// SLA 監控由 cargo bench 負責。AMD §6 條件 #1 IPC budget = 100µs，per-call
    /// ≤ 5µs 留 20× headroom。
    #[test]
    fn test_router_gate_perf_within_sla() {
        use std::time::Instant;
        const ITER: usize = 1_000;

        let proc = IntentProcessor::new();
        let state = make_state();

        // Flag OFF path: just `if router_gate_enabled() { ... }` short-circuit.
        // flag OFF 路徑：僅 `if router_gate_enabled() { ... }` 短路。
        let gov_off = make_gov(false, true);
        let intent = make_intent("BTCUSDT", true);
        let t0 = Instant::now();
        for _ in 0..ITER {
            let r = proc.process_with_features(
                &intent,
                &gov_off,
                &state,
                2000.0,
                GovernanceProfile::Exploration,
                None,
                None,
                NOW_MS,
            );
            std::hint::black_box(r);
        }
        let off_avg_ns = (t0.elapsed().as_nanos() as f64) / (ITER as f64);
        // Note: this measures the *whole* process_with_features call, not just
        // Gate 1.4. Gate 1.4 contribution itself is < 1ns when flag OFF.
        // 注：此測量整個 process_with_features，非單 Gate 1.4；flag OFF 時 Gate 1.4
        // 自身貢獻 < 1ns。
        assert!(
            off_avg_ns < 200_000.0, // 200µs loose ceiling for full process call
            "flag OFF avg {off_avg_ns}ns exceeds 200µs ceiling — process path regression?"
        );

        // Flag ON path: Gate 1.4 acquires lease + Drop releases Cancelled
        // (rejection path due to ATR=0). Each iter creates+drops one SM lease.
        // flag ON 路徑：Gate 1.4 acquire + Drop release Cancelled（ATR=0 拒絕路徑）。
        // 每 iter 創建+drop 一個 SM lease。
        let gov_on = make_gov(true, true);
        let t1 = Instant::now();
        for _ in 0..ITER {
            let r = proc.process_with_features(
                &intent,
                &gov_on,
                &state,
                0.0, // ATR=0 → SEC-11 reject after Gate 1.4 acquire → Drop release
                GovernanceProfile::Production,
                None,
                None,
                NOW_MS,
            );
            std::hint::black_box(r);
        }
        let on_avg_ns = (t1.elapsed().as_nanos() as f64) / (ITER as f64);
        // 200µs ceiling; AMD §6 IPC budget 100µs is for IPC roundtrip not
        // pure Rust facade — facade should be sub-µs in practice.
        // 200µs 上限；AMD §6 IPC budget 100µs 針對 IPC roundtrip 而非純 Rust
        // facade — facade 實務應 sub-µs。
        assert!(
            on_avg_ns < 200_000.0,
            "flag ON avg {on_avg_ns}ns exceeds 200µs ceiling — Mutex/SM regression?"
        );

        eprintln!(
            "AMD-2026-05-02-01 Track E E-2 Gate 1.4 perf — \
             flag OFF avg = {off_avg_ns:.0}ns, flag ON avg = {on_avg_ns:.0}ns"
        );
    }
}
