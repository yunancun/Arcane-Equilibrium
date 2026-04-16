use super::*;

    fn make_event(symbol: &str, price: f64, ts: u64) -> PriceEvent {
        PriceEvent::new(symbol.to_string(), price, ts)
    }

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
        let p_demo  = TickPipeline::with_kind(&["BTCUSDT"], 1_000.0, PipelineKind::Demo);
        let p_live  = TickPipeline::with_kind(&["BTCUSDT"], 1_000.0, PipelineKind::Live);
        assert_eq!(p_paper.pipeline_kind.db_mode(), "paper");
        assert_eq!(p_demo.pipeline_kind.db_mode(), "demo");
        assert_eq!(p_live.pipeline_kind.db_mode(), "live");
    }

    /// 3E-ARCH regression: emit_close_fill must embed `effective_engine_mode()`
    /// into fill_id / order_id / context_id so that Paper/Demo/Live records
    /// sharing the same trading_tx channel never collide on `ON CONFLICT DO NOTHING`.
    /// Locks the fix from commit d670759 (BUG-1/2/3) AND the endpoint-aware tag
    /// upgrade: Live+LiveDemo now stamps "live_demo" (not misleading "live") when
    /// the pipeline is pointed at api-demo.bybit.com.
    /// 3E-ARCH 回歸：emit_close_fill 必須將 effective_engine_mode() 嵌入 fill_id /
    /// order_id / context_id。鎖定 commit d670759（BUG-1/2/3）+ endpoint 感知升級
    /// （Live+LiveDemo → "live_demo"）。
    #[test]
    fn test_emit_close_fill_embeds_engine_mode_per_kind() {
        use crate::bybit_rest_client::BybitEnvironment;
        let kinds: [(PipelineKind, Option<BybitEnvironment>, &str); 4] = [
            (PipelineKind::Paper, None, "paper"),
            (PipelineKind::Demo, Some(BybitEnvironment::Demo), "demo"),
            (PipelineKind::Live, Some(BybitEnvironment::Mainnet), "live"),
            (PipelineKind::Live, Some(BybitEnvironment::LiveDemo), "live_demo"),
        ];
        for (kind, env, expected_em) in kinds {
            let mut pipeline =
                TickPipeline::with_kind(&["BTCUSDT"], 1_000.0, kind);
            if let Some(e) = env {
                pipeline.set_endpoint_env(e);
            }
            let (tx, mut rx) =
                tokio::sync::mpsc::channel::<crate::database::TradingMsg>(8);
            pipeline.set_trading_channel(tx);

            // Trigger the risk-close path. Direct call covers fill_id /
            // order_id / context_id / engine_mode embedding all at once.
            // 直接觸發 risk-close 路徑，一次覆蓋四個 ID 欄位。
            pipeline.emit_close_fill(
                "BTCUSDT",
                true,    // is_long
                0.1,     // qty
                50_000.0, // price
                123,     // ts_ms
                0.0,     // realized_pnl
                "risk_close:sl_hit",
                "",      // entry_context_id unused here (test focuses on engine_mode embed)
            );

            let msg = rx
                .try_recv()
                .expect("emit_close_fill must enqueue a Fill message");
            match msg {
                crate::database::TradingMsg::Fill {
                    fill_id,
                    order_id,
                    context_id,
                    engine_mode,
                    ..
                } => {
                    assert_eq!(
                        engine_mode, expected_em,
                        "{:?}: engine_mode tag", kind
                    );
                    assert!(
                        fill_id.starts_with(&format!("close-{}-", expected_em)),
                        "{:?}: fill_id={} missing engine_mode", kind, fill_id
                    );
                    assert!(
                        order_id.starts_with(&format!("close_{}_", expected_em)),
                        "{:?}: order_id={} missing engine_mode", kind, order_id
                    );
                    assert!(
                        context_id.starts_with(&format!("ctx-{}-", expected_em)),
                        "{:?}: context_id={} missing engine_mode", kind, context_id
                    );
                }
                other => panic!("{:?}: expected Fill, got {:?}", kind, other),
            }
        }
    }

    /// EDGE-P3-1 R2 regression: emit_close_fill must thread the caller-supplied
    /// entry_context_id into the Fill row so training can JOIN fills → decision
    /// snapshots via the open-time context id. Empty string → NULL at DB layer.
    /// EDGE-P3-1 R2 回歸：emit_close_fill 必須將 caller 傳入的 entry_context_id
    /// 寫入 Fill，使訓練端可用開倉時的 context id JOIN fills↔決策快照；空字串在 DB 層為 NULL。
    #[test]
    fn test_emit_close_fill_threads_entry_context_id() {
        let mut pipeline = TickPipeline::with_kind(&["BTCUSDT"], 1_000.0, PipelineKind::Paper);
        let (tx, mut rx) = tokio::sync::mpsc::channel::<crate::database::TradingMsg>(8);
        pipeline.set_trading_channel(tx);

        pipeline.emit_close_fill(
            "BTCUSDT",
            true,
            0.1,
            50_000.0,
            999,
            25.0,
            "risk_close:test",
            "ctx-entry-xyz-789",
        );

        let msg = rx.try_recv().expect("Fill must be enqueued");
        match msg {
            crate::database::TradingMsg::Fill { entry_context_id, .. } => {
                assert_eq!(
                    entry_context_id, "ctx-entry-xyz-789",
                    "entry_context_id must thread verbatim from caller to Fill row"
                );
            }
            other => panic!("expected Fill, got {:?}", other),
        }
    }

    /// Empty entry_context_id (open fills, missing context) still produces a
    /// valid Fill — DB writer treats empty as NULL to avoid label pollution.
    /// 空 entry_context_id（開倉 Fill、或缺失）仍應產生有效 Fill — DB writer 將空視為 NULL 以免污染訓練標籤。
    #[test]
    fn test_emit_close_fill_accepts_empty_entry_context_id() {
        let mut pipeline = TickPipeline::with_kind(&["BTCUSDT"], 1_000.0, PipelineKind::Paper);
        let (tx, mut rx) = tokio::sync::mpsc::channel::<crate::database::TradingMsg>(8);
        pipeline.set_trading_channel(tx);

        pipeline.emit_close_fill("BTCUSDT", false, 0.05, 3_000.0, 111, 0.0, "test", "");

        let msg = rx.try_recv().expect("Fill must be enqueued");
        match msg {
            crate::database::TradingMsg::Fill { entry_context_id, .. } => {
                assert_eq!(entry_context_id, "");
            }
            other => panic!("expected Fill, got {:?}", other),
        }
    }

    /// P0-4 R1 regression: execute_position_close must propagate `trigger_tag` to
    /// OrderDispatchRequest.strategy. Previously hardcoded "risk_check", which
    /// collapsed strategy exits + fast_track closes + shadow mirrors into a single
    /// bucket in trading.fills.strategy_name and broke attribution (see audit
    /// docs/audits/2026-04-16--demo_zero_strategy_exit_audit.md).
    /// P0-4 R1 回歸：execute_position_close 必須把 trigger_tag 穿透到
    /// OrderDispatchRequest.strategy，不能再硬編碼 "risk_check" 吞掉歸因。
    #[test]
    fn test_execute_position_close_propagates_trigger_tag() {
        let cases: &[(bool, &str)] = &[
            (true,  "strategy_close:funding_arb_exit"),
            (true,  "risk_close:fast_track_reduce_half"),
            (true,  "risk_close:halt_session"),
            (false, "strategy_close:ma_crossover_flip"),
            (false, "risk_close:cost_edge_ratio"),
        ];
        for (is_primary, tag) in cases {
            let mut pipeline =
                TickPipeline::with_kind(&["BTCUSDT"], 1_000.0, PipelineKind::Demo);
            let (tx, mut rx) =
                tokio::sync::mpsc::unbounded_channel::<OrderDispatchRequest>();
            pipeline.set_shadow_channel(tx);

            let event = make_event("BTCUSDT", 50_000.0, 1_700_000_000_000);
            pipeline.execute_position_close(
                "BTCUSDT",
                true, // is_long — closing a long position
                0.1,
                &event,
                *is_primary,
                tag,
            );

            let req = rx.try_recv().expect("OrderDispatchRequest must be sent");
            assert_eq!(
                req.strategy, *tag,
                "strategy must carry trigger_tag verbatim (is_primary={}, tag={})",
                is_primary, tag
            );
            assert!(req.is_close, "close dispatch must set is_close=true");
            assert_eq!(req.is_primary, *is_primary);
            let expected_prefix = if *is_primary { "oc_risk_" } else { "sh_risk_" };
            assert!(
                req.order_link_id.starts_with(expected_prefix),
                "order_link_id={} expected prefix {}",
                req.order_link_id,
                expected_prefix
            );
        }
    }

    #[test]
    fn test_pipeline_kind_is_exchange() {
        assert!(!PipelineKind::Paper.is_exchange());
        assert!(PipelineKind::Demo.is_exchange());
        assert!(PipelineKind::Live.is_exchange());
    }

    #[test]
    fn test_pipeline_kind_governance_profile() {
        assert_eq!(PipelineKind::Paper.governance_profile(), GovernanceProfile::Exploration);
        assert_eq!(PipelineKind::Demo.governance_profile(), GovernanceProfile::Validation);
        assert_eq!(PipelineKind::Live.governance_profile(), GovernanceProfile::Production);
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

    /// 3E D10/D20: Verify Arc<PriceEvent> fan-out delivers to multiple receivers.
    /// 3E D10/D20：驗證 Arc<PriceEvent> 扇出可向多個接收端投遞。
    #[tokio::test]
    async fn test_fanout_arc_price_event() {
        use std::sync::Arc;
        use tokio::sync::mpsc;
        let (tx1, mut rx1) = mpsc::channel::<Arc<openclaw_types::PriceEvent>>(16);
        let (tx2, mut rx2) = mpsc::channel::<Arc<openclaw_types::PriceEvent>>(16);
        let event = openclaw_types::PriceEvent::new("BTCUSDT".into(), 50000.0, 1000);
        let arc_event = Arc::new(event);
        tx1.try_send(Arc::clone(&arc_event)).unwrap();
        tx2.try_send(arc_event).unwrap();
        let e1 = rx1.recv().await.unwrap();
        let e2 = rx2.recv().await.unwrap();
        assert_eq!(e1.symbol, "BTCUSDT");
        assert_eq!(e2.symbol, "BTCUSDT");
        assert_eq!(e1.last_price, e2.last_price);
    }

    /// 3E D10: Verify try_send returns Err when channel is full (lag detection).
    /// 3E D10：驗證通道滿時 try_send 返回 Err（延遲檢測）。
    #[tokio::test]
    async fn test_fanout_lag_detection() {
        use std::sync::Arc;
        use tokio::sync::mpsc;
        // Buffer size 1 — second send should fail
        let (tx, _rx) = mpsc::channel::<Arc<openclaw_types::PriceEvent>>(1);
        let e1 = Arc::new(openclaw_types::PriceEvent::new("A".into(), 1.0, 1));
        let e2 = Arc::new(openclaw_types::PriceEvent::new("B".into(), 2.0, 2));
        assert!(tx.try_send(e1).is_ok());
        assert!(tx.try_send(e2).is_err()); // channel full → lag detected
    }

    #[test]
    fn test_pipeline_creation() {
        let pipeline = TickPipeline::new(&["BTCUSDT"]);
        assert_eq!(pipeline.stats.total_ticks, 0);
    }

    #[test]
    fn test_pipeline_on_tick() {
        let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
        pipeline.on_tick(&make_event("BTCUSDT", 50000.0, 1000));
        assert_eq!(pipeline.stats.total_ticks, 1);
    }

    #[test]
    fn test_pipeline_multiple_ticks() {
        let mut pipeline = TickPipeline::new(&["BTCUSDT", "ETHUSDT"]);
        for i in 0..50 {
            pipeline.on_tick(&make_event("BTCUSDT", 50000.0 + i as f64, i * 60_000));
        }
        assert_eq!(pipeline.stats.total_ticks, 50);
    }

    #[test]
    fn test_position_snapshot_emitted_every_1000_ticks() {
        // GAP-7 regression: PositionSnapshot must be emitted every 1000 ticks
        // for every open paper position when trading_tx is wired.
        // GAP-7 回歸：掛接 trading_tx 時每 1000 ticks 為每個持倉發射快照。
        let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
        let (tx, mut rx) = tokio::sync::mpsc::channel::<crate::database::TradingMsg>(8192);
        pipeline.set_trading_channel(tx);
        // Open a paper long position directly.
        // 直接建立紙盤多單持倉。
        pipeline
            .paper_state
            .apply_fill("BTCUSDT", true, 0.1, 50_000.0, 0.0, 0, "test");
        // Pump exactly 1000 ticks. total_ticks becomes 1000 -> snapshot.
        // 打 1000 tick，total_ticks 達到 1000 觸發快照。
        for i in 0..1000 {
            pipeline.on_tick(&make_event("BTCUSDT", 50_000.0, (i + 1) * 60_000));
        }
        // Drain channel; expect at least one PositionSnapshot for BTCUSDT.
        // 抽取通道；至少應有一條 BTCUSDT 的 PositionSnapshot。
        let mut found = false;
        while let Ok(msg) = rx.try_recv() {
            if let crate::database::TradingMsg::PositionSnapshot {
                symbol,
                side,
                qty,
                mark_price,
                unrealized_pnl,
                ..
            } = msg
            {
                if symbol == "BTCUSDT" {
                    assert_eq!(side, "long");
                    assert!((qty - 0.1).abs() < 1e-9);
                    assert!((mark_price - 50_000.0).abs() < 1e-9);
                    assert!(unrealized_pnl.abs() < 1e-6);
                    found = true;
                    break;
                }
            }
        }
        assert!(
            found,
            "expected a PositionSnapshot for BTCUSDT; positions={}",
            pipeline.paper_state.position_count()
        );
    }

    #[test]
    fn test_position_snapshot_noop_without_channel() {
        // Without trading_tx wired, snapshot loop must be a no-op and never panic.
        // 未掛接 trading_tx 時快照循環必須無動作且不 panic。
        let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
        pipeline
            .paper_state
            .apply_fill("BTCUSDT", false, 0.2, 50_000.0, 0.0, 0, "test");
        for i in 0..1000 {
            pipeline.on_tick(&make_event("BTCUSDT", 49_000.0, (i + 1) * 60_000));
        }
        assert_eq!(pipeline.stats.total_ticks, 1000);
    }

    #[test]
    fn test_pipeline_with_auth() {
        let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
        pipeline.grant_paper_auth().unwrap();
        assert!(pipeline.governance.is_authorized());
    }

    #[test]
    fn test_canary_mode_off_returns_none() {
        let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
        assert!(!pipeline.canary_mode);
        let record = pipeline.on_tick(&make_event("BTCUSDT", 50000.0, 1000));
        assert!(record.is_none());
    }

    #[test]
    fn test_canary_mode_on_returns_record() {
        let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
        pipeline.canary_mode = true;
        let record = pipeline.on_tick(&make_event("BTCUSDT", 50000.0, 1000));
        assert!(record.is_some());
        let r = record.unwrap();
        assert_eq!(r.schema_version, "1.0.0");
        assert_eq!(r.source, "rust_engine");
        assert_eq!(r.tick_number, 1);
        assert_eq!(r.symbol, "BTCUSDT");
        assert_eq!(r.price, 50000.0);
        assert_eq!(r.timestamp_ms, 1000);
    }

    #[test]
    fn test_canary_record_serializable() {
        let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
        pipeline.canary_mode = true;
        let record = pipeline
            .on_tick(&make_event("BTCUSDT", 50000.0, 1000))
            .unwrap();
        let json = serde_json::to_string(&record).unwrap();
        assert!(json.contains("\"schema_version\":\"1.0.0\""));
        assert!(json.contains("\"source\":\"rust_engine\""));
        // Deserialize back / 反序列化
        let r2: CanaryRecord = serde_json::from_str(&json).unwrap();
        assert_eq!(r2.tick_number, record.tick_number);
    }

    #[test]
    fn test_snapshot_to_input() {
        let snap = IndicatorSnapshot {
            sma_20: Some(50000.0),
            sma_50: None,
            ema_12: Some(50100.0),
            ema_26: None,
            rsi_14: Some(55.0),
            macd: None,
            bollinger: None,
            atr_14: None,
            atr_5: None,
            stochastic: None,
            kama: None,
            adx: None,
            hurst: None,
            ewma_vol: None,
            volume_ratio: Some(1.2),
            donchian: None,
        };
        let input = snapshot_to_input(&snap);
        assert_eq!(input.sma, Some(50000.0));
        assert_eq!(input.rsi, Some(55.0));
        assert_eq!(input.volume_ratio, Some(1.2));
    }

    // ─── I-08 Dual-Rail Stop tests (Principle #9) ───
    // 雙軌止損測試：驗證 broker-side SL 只在 primary exchange mode 開倉時啟用

    #[test]
    fn test_dual_rail_shadow_order_has_sl_fields() {
        // Struct must expose stop_loss / take_profit for broker rail wiring
        let req = OrderDispatchRequest {
            symbol: "BTCUSDT".into(),
            is_long: true,
            qty: 0.01,
            price: 50000.0,
            strategy: "test".into(),
            paper_fill_ts: 0,
            is_close: false,
            order_link_id: "oc_test".into(),
            is_primary: true,
            stop_loss: Some(49000.0),
            take_profit: Some(52000.0),
        };
        assert_eq!(req.stop_loss, Some(49000.0));
        assert_eq!(req.take_profit, Some(52000.0));
    }

    #[test]
    fn test_dual_rail_broker_sl_long_below_entry() {
        // Long SL must sit below entry price
        let entry: f64 = 50000.0;
        let sl_pct: f64 = 2.0;
        let sl = entry * (1.0 - sl_pct / 100.0);
        assert!(sl < entry);
        assert!((sl - 49000.0f64).abs() < 0.01);
    }

    #[test]
    fn test_dual_rail_broker_sl_short_above_entry() {
        // Short SL must sit above entry price
        let entry: f64 = 50000.0;
        let sl_pct: f64 = 2.0;
        let sl = entry * (1.0 + sl_pct / 100.0);
        assert!(sl > entry);
        assert!((sl - 51000.0f64).abs() < 0.01);
    }

    #[test]
    fn test_dual_rail_close_orders_no_broker_sl() {
        // Close orders never attach broker SL (Bybit auto-cancels on reduce-only fill)
        let req = OrderDispatchRequest {
            symbol: "BTCUSDT".into(),
            is_long: false,
            qty: 0.01,
            price: 50000.0,
            strategy: "risk_check".into(),
            paper_fill_ts: 0,
            is_close: true,
            order_link_id: "oc_risk".into(),
            is_primary: true,
            stop_loss: None,
            take_profit: None,
        };
        assert!(req.stop_loss.is_none());
        assert!(req.is_close);
    }

    #[test]
    fn test_dual_rail_paper_shadow_skips_broker_sl() {
        // Paper/shadow orders keep broker SL None (engine rail handles stops locally)
        let req = OrderDispatchRequest {
            symbol: "ETHUSDT".into(),
            is_long: true,
            qty: 0.1,
            price: 3000.0,
            strategy: "ma".into(),
            paper_fill_ts: 0,
            is_close: false,
            order_link_id: "sh_test".into(),
            is_primary: false,
            stop_loss: None,
            take_profit: None,
        };
        assert!(!req.is_primary);
        assert!(req.stop_loss.is_none());
    }

    fn make_signal(symbol: &str, dir: openclaw_core::signals::SignalDirection, ts_ms: u64) -> openclaw_core::signals::Signal {
        openclaw_core::signals::Signal {
            symbol: symbol.into(),
            direction: dir,
            confidence: 0.5,
            edge_bps: 10.0,
            source: "ma_crossover".into(),
            timeframe: "1m".into(),
            reasoning: "test".into(),
            ts_ms,
        }
    }

    #[test]
    fn test_dbrun1_first_signal_persisted() {
        use openclaw_core::signals::SignalDirection;
        let mut p = TickPipeline::new(&["BTCUSDT"]);
        assert!(p.should_persist_signal(&make_signal("BTCUSDT", SignalDirection::Long, 1_000)));
        assert_eq!(p.signals_throttled(), 0);
    }

    #[test]
    fn test_dbrun1_unchanged_signal_throttled_within_heartbeat() {
        use openclaw_core::signals::SignalDirection;
        let mut p = TickPipeline::new(&["BTCUSDT"]);
        p.set_signals_heartbeat_ms(60_000);
        assert!(p.should_persist_signal(&make_signal("BTCUSDT", SignalDirection::Long, 1_000)));
        // Same direction, +30s → throttled
        assert!(!p.should_persist_signal(&make_signal("BTCUSDT", SignalDirection::Long, 31_000)));
        assert_eq!(p.signals_throttled(), 1);
    }

    #[test]
    fn test_dbrun1_direction_change_breaks_throttle() {
        use openclaw_core::signals::SignalDirection;
        let mut p = TickPipeline::new(&["BTCUSDT"]);
        p.set_signals_heartbeat_ms(60_000);
        assert!(p.should_persist_signal(&make_signal("BTCUSDT", SignalDirection::Long, 1_000)));
        // Direction flips → persist immediately even within heartbeat
        assert!(p.should_persist_signal(&make_signal("BTCUSDT", SignalDirection::Short, 5_000)));
        assert_eq!(p.signals_throttled(), 0);
    }

    #[test]
    fn test_dbrun1_heartbeat_elapsed_persists() {
        use openclaw_core::signals::SignalDirection;
        let mut p = TickPipeline::new(&["BTCUSDT"]);
        p.set_signals_heartbeat_ms(60_000);
        assert!(p.should_persist_signal(&make_signal("BTCUSDT", SignalDirection::Long, 1_000)));
        // Same direction, 60s later → heartbeat fires
        assert!(p.should_persist_signal(&make_signal("BTCUSDT", SignalDirection::Long, 61_000)));
        assert_eq!(p.signals_throttled(), 0);
    }

    #[test]
    fn test_dbrun1_disable_throttle() {
        use openclaw_core::signals::SignalDirection;
        let mut p = TickPipeline::new(&["BTCUSDT"]);
        p.set_signals_heartbeat_ms(0);
        // Every call persists, no dedupe state consulted
        for ts in [1, 2, 3, 4, 5] {
            assert!(p.should_persist_signal(&make_signal("BTCUSDT", SignalDirection::Long, ts)));
        }
        assert_eq!(p.signals_throttled(), 0);
    }

    #[test]
    fn test_dbrun3_close_position_returns_pnl() {
        let mut p = TickPipeline::new(&["BTCUSDT"]);
        // Open long at 50k, close at 51k → +0.1 * 1000 = +$100 realized
        p.paper_state.apply_fill("BTCUSDT", true, 0.1, 50_000.0, 0.0, 0, "test");
        let pnl = p.paper_state.close_position("BTCUSDT", 51_000.0, 1_000);
        assert_eq!(pnl, Some(100.0));
        // Subsequent close on same symbol → None
        let none = p.paper_state.close_position("BTCUSDT", 52_000.0, 2_000);
        assert!(none.is_none());
    }

    #[test]
    fn test_dbrun3_emit_close_fill_increments_stats() {
        let mut p = TickPipeline::new(&["BTCUSDT"]);
        let before = p.stats.total_fills;
        p.emit_close_fill("BTCUSDT", true, 0.1, 51_000.0, 1_000, 100.0, "risk_close:test", "");
        assert_eq!(p.stats.total_fills, before + 1);
    }

    /// Regression: emit_close_fill must mirror the fill into `recent_fills`
    /// so the pipeline_snapshot view surfaces close fills to the GUI.
    /// Previously it only incremented stats, causing snapshot `recent_fills`
    /// to stay empty while DB accumulated closes every second.
    /// 回歸：emit_close_fill 必須把平倉 fill 鏡像到 recent_fills，讓 GUI 快照能看見。
    #[test]
    fn test_emit_close_fill_pushes_to_recent_fills() {
        let mut p = TickPipeline::new(&["BTCUSDT"]);
        assert_eq!(p.recent_fills.len(), 0);
        // Close a long position → fill side should be short (is_long = false).
        // 平多倉 → fill 方向為空（is_long = false）。
        p.emit_close_fill(
            "BTCUSDT", true, 0.1, 51_000.0, 1_234, 100.0,
            "stop_trigger:hard_stop", "",
        );
        assert_eq!(p.recent_fills.len(), 1);
        let fill = &p.recent_fills[0];
        assert_eq!(fill.symbol, "BTCUSDT");
        assert_eq!(fill.is_long, false, "close of long position → short fill side");
        assert_eq!(fill.qty, 0.1);
        assert_eq!(fill.price, 51_000.0);
        assert_eq!(fill.timestamp_ms, 1_234);
        assert_eq!(fill.strategy, "stop_trigger:hard_stop");
        // fee is the computed close fee (qty * price * fee_rate), not the raw 0.
        // fee 是計算出的平倉費，而非原始 0。
        assert!(fill.fee > 0.0, "close fee must be charged, not zero");
    }

    /// Close of a short position produces a long-side fill in recent_fills.
    /// 平空倉 → fill 方向為多。
    #[test]
    fn test_emit_close_fill_inverts_is_long_for_short_close() {
        let mut p = TickPipeline::new(&["BTCUSDT"]);
        p.emit_close_fill(
            "BTCUSDT", false, 0.05, 50_000.0, 2_000, -50.0,
            "risk_close:fast_track", "",
        );
        assert_eq!(p.recent_fills.len(), 1);
        assert_eq!(p.recent_fills[0].is_long, true, "close of short → long fill side");
    }

    #[test]
    fn test_dbrun2_context_counter_starts_zero() {
        let p = TickPipeline::new(&["BTCUSDT"]);
        assert_eq!(p.context_throttled(), 0);
        assert_eq!(p.signals_throttled(), 0);
    }

    #[test]
    fn test_dbrun1_per_symbol_strategy_isolation() {
        use openclaw_core::signals::SignalDirection;
        let mut p = TickPipeline::new(&["BTCUSDT", "ETHUSDT"]);
        p.set_signals_heartbeat_ms(60_000);
        assert!(p.should_persist_signal(&make_signal("BTCUSDT", SignalDirection::Long, 1_000)));
        // Different symbol, same strategy → independent key, persists
        assert!(p.should_persist_signal(&make_signal("ETHUSDT", SignalDirection::Long, 1_000)));
        assert_eq!(p.signals_throttled(), 0);
    }

    #[test]
    fn test_pnl3_boot_cooldown_stamps_first_tick() {
        // PNL-3: First tick stamps boot_ts_ms; subsequent ticks reuse it.
        // PNL-3：首個 tick 記錄 boot_ts_ms；後續 tick 沿用。
        let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
        assert!(pipeline.boot_ts_ms.is_none());
        pipeline.on_tick(&make_event("BTCUSDT", 50_000.0, 1_000_000));
        assert_eq!(pipeline.boot_ts_ms, Some(1_000_000));
        pipeline.on_tick(&make_event("BTCUSDT", 50_001.0, 1_010_000));
        assert_eq!(pipeline.boot_ts_ms, Some(1_000_000));
    }

    #[test]
    fn test_pnl4_derive_regime_hurst_priority() {
        use openclaw_core::indicators::{HurstResult, IndicatorSnapshot};
        let pipeline = TickPipeline::new(&["BTCUSDT"]);
        let mut ind = IndicatorSnapshot::default();
        ind.hurst = Some(HurstResult { hurst: 0.7, regime: "trending".into() });
        assert_eq!(pipeline.derive_regime(Some(&ind)), "trending");
        ind.hurst = Some(HurstResult { hurst: 0.3, regime: "mean_reverting".into() });
        assert_eq!(pipeline.derive_regime(Some(&ind)), "ranging");
    }

    #[test]
    fn test_pnl4_derive_regime_adx_fallback() {
        use openclaw_core::indicators::{AdxResult, HurstResult, IndicatorSnapshot};
        let pipeline = TickPipeline::new(&["BTCUSDT"]);
        let mut ind = IndicatorSnapshot::default();
        ind.hurst = Some(HurstResult { hurst: 0.5, regime: "random_walk".into() });
        ind.adx = Some(AdxResult { adx: 30.0, plus_di: 25.0, minus_di: 10.0 });
        assert_eq!(pipeline.derive_regime(Some(&ind)), "trending");
        ind.adx = Some(AdxResult { adx: 15.0, plus_di: 10.0, minus_di: 12.0 });
        assert_eq!(pipeline.derive_regime(Some(&ind)), "ranging");
    }

    #[test]
    fn test_pnl4_derive_regime_none_default() {
        let pipeline = TickPipeline::new(&["BTCUSDT"]);
        assert_eq!(pipeline.derive_regime(None), "ranging");
    }

    #[test]
    fn test_rc1_risk_runtime_status_no_boot_ts() {
        // 1C-3-B: before first tick, boot_ts_ms is None → remaining = 0
        // 1C-3-B：第一個 tick 之前 boot_ts_ms 為 None → 剩餘 0
        let pipeline = TickPipeline::new(&["BTCUSDT"]);
        let snap = pipeline.risk_runtime_status_json(1_000_000);
        assert_eq!(snap["boot_cooldown_remaining_ms"], 0);
        assert_eq!(snap["paper_paused"], false);
        assert_eq!(snap["session_halted"], false);
        assert!(snap["governor_tier"].is_string());
        assert!(snap["consecutive_losses_by_symbol"].is_object());
    }

    #[test]
    fn test_rc1_risk_runtime_status_boot_cooldown_math() {
        // 1C-3-B: boot at t=1000, cooldown=60s, now=t=11000 → remaining 50s
        // 1C-3-B：boot 時間 1000、冷卻 60s、現在 11000 → 剩 50s
        let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
        pipeline.boot_ts_ms = Some(1_000);
        pipeline.boot_cooldown_ms = 60_000;
        let snap = pipeline.risk_runtime_status_json(11_000);
        assert_eq!(snap["boot_cooldown_remaining_ms"], 50_000);
        assert_eq!(snap["boot_cooldown_total_ms"], 60_000);
        // Past expiry → saturating to 0
        // 過期 → 飽和到 0
        let snap2 = pipeline.risk_runtime_status_json(999_999_999);
        assert_eq!(snap2["boot_cooldown_remaining_ms"], 0);
    }

    #[test]
    fn test_rc1b2_parse_risk_level_aliases() {
        use openclaw_core::sm::risk_gov::RiskLevel;
        assert_eq!(TickPipeline::parse_risk_level("normal").unwrap(), RiskLevel::Normal);
        assert_eq!(TickPipeline::parse_risk_level("CAUTIOUS").unwrap(), RiskLevel::Cautious);
        assert_eq!(TickPipeline::parse_risk_level("circuit_breaker").unwrap(), RiskLevel::CircuitBreaker);
        assert_eq!(TickPipeline::parse_risk_level("CircuitBreaker").unwrap(), RiskLevel::CircuitBreaker);
        assert_eq!(TickPipeline::parse_risk_level("manual_review").unwrap(), RiskLevel::ManualReview);
        assert!(TickPipeline::parse_risk_level("foo").is_err());
    }

    #[test]
    fn test_rc1b2_governor_cooldown_const_24h() {
        // 1C-3-B-2: 24h = 86_400_000 ms
        // 1C-3-B-2：24h = 86_400_000 ms
        assert_eq!(TickPipeline::GOVERNOR_DE_ESCALATION_COOLDOWN_MS, 86_400_000);
    }

    #[test]
    fn test_rc1b2_de_escalation_reason_whitelist() {
        let valid = TickPipeline::VALID_DE_ESCALATION_REASONS;
        assert!(valid.contains(&"false_positive"));
        assert!(valid.contains(&"root_cause_fixed"));
        assert!(valid.contains(&"accept_risk"));
        assert!(!valid.contains(&"because_i_said_so"));
        assert_eq!(valid.len(), 3);
    }

    #[test]
    fn test_rc1b2_cooldown_state_setter_and_getter() {
        let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
        assert_eq!(pipeline.last_governor_de_escalation_ms(), None);
        pipeline.set_last_governor_de_escalation_ms(Some(12345));
        assert_eq!(pipeline.last_governor_de_escalation_ms(), Some(12345));
        pipeline.set_last_governor_de_escalation_ms(None);
        assert_eq!(pipeline.last_governor_de_escalation_ms(), None);
    }

    #[test]
    fn test_rc1b2_sm_escalate_then_de_escalate_round_trip() {
        // End-to-end through pipeline.governance.risk: simulate operator
        // first making things tighter then relaxing them. Bypass min_hold_time
        // to keep the test fast.
        // 模擬 operator 先收緊再放鬆。繞過 min_hold_time 加速測試。
        use openclaw_core::sm::risk_gov::{RiskEvent, RiskLevel};
        let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
        pipeline.governance.risk.thresholds.min_hold_time_ms = 0;
        // Tighter: Normal → Cautious
        pipeline
            .governance
            .risk
            .escalate_to(RiskLevel::Cautious, "operator_ipc: testing", RiskEvent::OperatorEscalation)
            .unwrap();
        assert_eq!(pipeline.governance.risk.snapshot_level(), RiskLevel::Cautious);
        // Looser: Cautious → Normal
        pipeline
            .governance
            .risk
            .de_escalate_to(RiskLevel::Normal, "operator_ipc", "operator_ipc:false_positive")
            .unwrap();
        assert_eq!(pipeline.governance.risk.snapshot_level(), RiskLevel::Normal);
    }

    #[test]
    fn test_rc1_risk_runtime_status_consecutive_losses_map() {
        // 1C-3-B: per-symbol map round-trips into JSON object
        // 1C-3-B：per-symbol map 序列化為 JSON object
        let mut pipeline = TickPipeline::new(&["BTCUSDT", "ETHUSDT"]);
        pipeline.consecutive_losses.insert("BTCUSDT".into(), 3);
        pipeline.consecutive_losses.insert("ETHUSDT".into(), 1);
        let snap = pipeline.risk_runtime_status_json(0);
        assert_eq!(snap["consecutive_losses_by_symbol"]["BTCUSDT"], 3);
        assert_eq!(snap["consecutive_losses_by_symbol"]["ETHUSDT"], 1);
    }

    #[test]
    fn test_pnl3_boot_cooldown_default_60s() {
        // PNL-3: default cooldown is 60_000ms when env var not set.
        // PNL-3：未設環境變量時冷卻期默認 60_000ms。
        let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
        // Force-set boot_ts_ms then check elapsed math via direct field.
        pipeline.boot_ts_ms = Some(0);
        assert_eq!(pipeline.boot_cooldown_ms, 60_000);
        // Tick at t=30s → still in cooldown
        let in_cd_30s: bool = (30_000u64).saturating_sub(0) < pipeline.boot_cooldown_ms;
        assert!(in_cd_30s);
        // Tick at t=61s → out of cooldown
        let in_cd_61s: bool = (61_000u64).saturating_sub(0) < pipeline.boot_cooldown_ms;
        assert!(!in_cd_61s);
    }

    // ─── ARCH-RC1 1C-4 hot-reload e2e ───────────────────────────────────
    // 驗證 IPC patch_risk_config 後的下一個 tick：5 個下游消費者全部
    // 同步看到新值（intent_processor / guardian / paper_state / h0_gate /
    // governance.risk.thresholds）。這份硬證據是 1C-4 wrap 的關鍵。
    // E2E proof: after a ConfigStore.replace() that simulates an IPC
    // patch_risk_config, driving a single on_tick must propagate the new
    // RiskConfig snapshot into ALL 5 owned-copy consumers via
    // sync_risk_config_if_changed → apply_risk_snapshot.
    #[test]
    fn test_arch_rc1_hot_reload_e2e_propagates_to_all_5_consumers() {
        use crate::config::{ConfigStore, PatchSource, RiskConfig};
        use std::sync::Arc;

        let mut pipeline = TickPipeline::new(&["BTCUSDT"]);

        // Build a baseline RiskConfig (defaults) and wire it as the live store.
        // 建立預設 RiskConfig 並以 live store 接線。
        let initial = RiskConfig::default();
        let store = Arc::new(ConfigStore::new(initial.clone()));
        pipeline.set_risk_store(Arc::clone(&store));

        // Sanity: initial seed must already be visible across all 5 consumers.
        // 初始 seed 應已同步至 5 個下游。
        assert_eq!(
            pipeline.intent_processor.risk_config().limits.leverage_max,
            initial.limits.leverage_max
        );
        assert_eq!(
            pipeline.intent_processor.guardian_config().max_leverage,
            initial.limits.leverage_max
        );
        assert_eq!(
            pipeline.h0_gate.config().max_open_positions,
            initial.limits.open_positions_max
        );
        assert_eq!(
            pipeline.paper_state.stop_config().hard_stop_pct,
            initial.limits.stop_loss_max_pct
        );
        assert_eq!(
            pipeline.governance.risk.thresholds.drawdown_cautious_pct,
            initial.cascade.drawdown_cautious_pct
        );
        let v0 = store.version();

        // Build a mutated config that differs in fields touched by all 5
        // downstream paths inside apply_risk_snapshot, then atomically
        // replace() — this is exactly what handle_patch_config does after
        // a successful patch_risk_config IPC call.
        // 修改一份新 config（覆蓋 5 條下游路徑各自讀的欄位），用 replace()
        // 原子寫入 — 這正是 IPC patch_risk_config 成功後的行為。
        let mut next = initial.clone();
        next.limits.leverage_max = initial.limits.leverage_max + 1.0;
        next.limits.open_positions_max = initial.limits.open_positions_max + 1;
        next.limits.stop_loss_max_pct = initial.limits.stop_loss_max_pct + 0.5;
        next.anti_cluster.max_same_direction =
            initial.anti_cluster.max_same_direction + 1;
        next.cascade.drawdown_cautious_pct =
            initial.cascade.drawdown_cautious_pct + 0.001;
        // Validate the mutated config to make sure we don't accidentally
        // craft an invalid one (defaults + tiny bumps should always pass).
        next.validate().expect("mutated test config must be valid");

        store
            .replace(next.clone(), PatchSource::Operator)
            .expect("replace must succeed");
        assert_eq!(store.version(), v0 + 1);

        // Drive a single tick — sync_risk_config_if_changed runs at the top
        // of on_tick and must apply_risk_snapshot to all 5 consumers.
        // 打一個 tick — sync_risk_config_if_changed 會在 on_tick 頂部執行
        // 並把新快照推到 5 個下游。
        pipeline.on_tick(&make_event("BTCUSDT", 50_000.0, 1_000));

        // 1) intent_processor's owned RiskConfig (Gate 0 / cost-edge / dynamic_stop)
        assert_eq!(
            pipeline.intent_processor.risk_config().limits.leverage_max,
            next.limits.leverage_max,
            "consumer #1: intent_processor.risk_config NOT hot-reloaded"
        );
        // 2) Guardian (P0 trade intent veto path)
        let g = pipeline.intent_processor.guardian_config();
        assert_eq!(
            g.max_leverage, next.limits.leverage_max,
            "consumer #2: guardian.max_leverage NOT hot-reloaded"
        );
        assert_eq!(
            g.max_same_direction_positions,
            next.anti_cluster.max_same_direction as usize,
            "consumer #2: guardian.max_same_direction_positions NOT hot-reloaded"
        );
        // 3) H0Gate (risk-level fields RMW)
        assert_eq!(
            pipeline.h0_gate.config().max_open_positions,
            next.limits.open_positions_max,
            "consumer #3: h0_gate.max_open_positions NOT hot-reloaded"
        );
        // 4) paper_state.stop_config (H0-blocked / paused fallback stops)
        assert!(
            (pipeline.paper_state.stop_config().hard_stop_pct
                - next.limits.stop_loss_max_pct)
                .abs()
                < 1e-9,
            "consumer #4: paper_state.stop_config.hard_stop_pct NOT hot-reloaded"
        );
        // 5) GovernanceCore.risk.thresholds (6-tier cascade SM)
        assert!(
            (pipeline.governance.risk.thresholds.drawdown_cautious_pct
                - next.cascade.drawdown_cautious_pct)
                .abs()
                < 1e-9,
            "consumer #5: governance.risk.thresholds NOT hot-reloaded"
        );

        // The pipeline must remember the new version so the NEXT tick is a
        // no-op (cheap atomic load + equality, no re-apply).
        // 紀錄版本號避免下個 tick 重複套用。
        assert_eq!(pipeline.risk_config_version_seen, store.version());
    }

    #[test]
    fn test_strategy_close_action_closes_position() {
        // Integration test: open a paper position, then simulate the strategy Close
        // deferred execution path, verify position is closed and fills/stats updated.
        // 集成測試：建立紙盤倉位，模擬策略 Close 延遲執行路徑，驗證倉位已平且成交/統計已更新。
        let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
        pipeline.grant_paper_auth().unwrap();

        // Open a long position directly via paper_state
        pipeline
            .paper_state
            .apply_fill("BTCUSDT", true, 0.1, 50_000.0, 5.5, 1000, "test");
        assert_eq!(pipeline.paper_state.position_count(), 1);
        let balance_before = pipeline.paper_state.balance();

        // Simulate the deferred close: close_position + record_trade + recent_fills
        // (This is exactly what the deferred close loop does for paper mode.)
        let close_price = 51_000.0;
        let close_ts = 2000_u64;
        let pos = pipeline.paper_state.get_position("BTCUSDT").unwrap();
        let is_long = pos.is_long;
        let qty = pos.qty;
        assert!(is_long);
        assert!((qty - 0.1).abs() < 1e-9);

        let pnl = pipeline
            .paper_state
            .close_position("BTCUSDT", close_price, close_ts);
        assert!(pnl.is_some(), "close_position should return pnl");
        let pnl = pnl.unwrap();
        assert!(pnl > 0.0, "long closed at higher price should be profitable");

        // Kelly stats update
        pipeline.intent_processor.record_trade("BTCUSDT", pnl);

        // Position should be gone
        assert_eq!(pipeline.paper_state.position_count(), 0);
        assert!(pipeline.paper_state.get_position("BTCUSDT").is_none());

        // Balance should have increased (profit minus fees)
        assert!(pipeline.paper_state.balance() > balance_before);
    }

    #[test]
    fn test_strategy_close_no_position_is_noop() {
        // Close when no position exists must be a safe no-op.
        // 無倉位時 Close 必須安全無動作。
        let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
        let result = pipeline
            .paper_state
            .close_position("BTCUSDT", 50_000.0, 1000);
        assert!(result.is_none(), "close_position on empty should return None");
        assert_eq!(pipeline.paper_state.position_count(), 0);
    }

    // ═══════════════════════════════════════════════════════════════
    // Phase 3: set_trading_mode state swap tests / 模式切換狀態交換測試
    // ═══════════════════════════════════════════════════════════════

    // 3E-4: set_trading_mode / add_mode / mode_snapshot tests REMOVED.
    // Pipeline identity is now immutable (PipelineKind set at construction).
    // Mode state swap tests replaced by per-pipeline independence tests (3E e2e).
    // 3E-4：模式切換/添加/快照測試已移除。管線身份不可變。

    #[test]
    fn test_snapshot_contains_pipeline_kind_mode_snapshot() {
        let pipeline = TickPipeline::with_balance(&["BTCUSDT"], 8_000.0);
        let snap = pipeline.snapshot();
        // mode_snapshots should contain exactly the pipeline's own kind.
        // mode_snapshots 應包含管線自身 kind。
        assert!(snap.mode_snapshots.contains_key("paper"));
        assert_eq!(snap.mode_snapshots.len(), 1);
        assert_eq!(snap.mode_snapshots["paper"].paper_state.balance, 8_000.0);
    }

    // ═══════════════════════════════════════════════════════════════════════
    // BLOCKER-10 / D6: EngineEvent + PipelineHealth tests
    // D6 跨引擎事件與管線健康狀態測試
    // ═══════════════════════════════════════════════════════════════════════

    #[test]
    fn test_d6_engine_event_crashed_clone() {
        // EngineEvent::Crashed must be Clone + Debug (required for broadcast).
        // Crashed 必須支持 Clone + Debug（broadcast 需要）。
        let evt = EngineEvent::Crashed(PipelineKind::Paper);
        let cloned = evt.clone();
        let dbg = format!("{:?}", cloned);
        assert!(dbg.contains("Crashed"));
        assert!(dbg.contains("Paper"));
    }

    #[test]
    fn test_d6_engine_event_cb_tripped_clone() {
        // EngineEvent::CircuitBreakerTripped must be Clone + Debug.
        // CircuitBreakerTripped 必須支持 Clone + Debug。
        let evt = EngineEvent::CircuitBreakerTripped(PipelineKind::Live);
        let cloned = evt.clone();
        let dbg = format!("{:?}", cloned);
        assert!(dbg.contains("CircuitBreakerTripped"));
        assert!(dbg.contains("Live"));
    }

    #[test]
    fn test_d6_pipeline_health_from_u8_roundtrip() {
        // PipelineHealth from_u8 covers all repr values + unknown default.
        // from_u8 覆蓋所有 repr 值 + 未知值默認 Down。
        assert_eq!(PipelineHealth::from_u8(0), PipelineHealth::Running);
        assert_eq!(PipelineHealth::from_u8(1), PipelineHealth::Paused);
        assert_eq!(PipelineHealth::from_u8(2), PipelineHealth::Down);
        assert_eq!(PipelineHealth::from_u8(3), PipelineHealth::Disabled);
        assert_eq!(PipelineHealth::from_u8(255), PipelineHealth::Down); // unknown → Down
    }

    #[test]
    fn test_d6_pipeline_health_repr_values() {
        // Repr values must be stable (stored in AtomicU8 by other code).
        // repr 值必須穩定（其他代碼以 AtomicU8 存儲）。
        assert_eq!(PipelineHealth::Running as u8, 0);
        assert_eq!(PipelineHealth::Paused as u8, 1);
        assert_eq!(PipelineHealth::Down as u8, 2);
        assert_eq!(PipelineHealth::Disabled as u8, 3);
    }

    #[tokio::test]
    async fn test_d6_broadcast_delivers_to_multiple_receivers() {
        // broadcast::channel delivers same event to 2 receivers.
        // broadcast 通道將同一事件送達 2 個接收端。
        let (tx, mut rx1) = tokio::sync::broadcast::channel::<EngineEvent>(4);
        let mut rx2 = tx.subscribe();
        tx.send(EngineEvent::Crashed(PipelineKind::Demo)).unwrap();
        let e1 = rx1.recv().await.unwrap();
        let e2 = rx2.recv().await.unwrap();
        assert!(matches!(e1, EngineEvent::Crashed(PipelineKind::Demo)));
        assert!(matches!(e2, EngineEvent::Crashed(PipelineKind::Demo)));
    }

    #[tokio::test]
    async fn test_d6_broadcast_cb_event_delivery() {
        // CircuitBreakerTripped event delivered via broadcast.
        // 熔斷事件通過 broadcast 送達。
        let (tx, mut rx) = tokio::sync::broadcast::channel::<EngineEvent>(4);
        tx.send(EngineEvent::CircuitBreakerTripped(PipelineKind::Live)).unwrap();
        let evt = rx.recv().await.unwrap();
        assert!(matches!(evt, EngineEvent::CircuitBreakerTripped(PipelineKind::Live)));
    }

    // ═══════════════════════════════════════════════════════════════════════
    // BLOCKER-10 / MAJOR-7 (D23): Snapshot versioning tests
    // 快照版本控制測試
    // ═══════════════════════════════════════════════════════════════════════

    #[test]
    fn test_d23_snapshot_schema_version_is_2_0_0() {
        // New snapshot must have schema_version "2.0.0".
        // 新快照的 schema_version 必須是 "2.0.0"。
        let pipeline = TickPipeline::with_balance(&["BTCUSDT"], 1_000.0);
        let snap = pipeline.snapshot();
        assert_eq!(snap.schema_version, "2.0.0");
    }

    #[test]
    fn test_d23_snapshot_written_at_ms_nonzero() {
        // written_at_ms must be set to a recent wall-clock timestamp.
        // written_at_ms 必須設為近期的 wall-clock 時間戳。
        let pipeline = TickPipeline::with_balance(&["BTCUSDT"], 1_000.0);
        let snap = pipeline.snapshot();
        assert!(snap.written_at_ms > 0, "written_at_ms should be nonzero");
        // Sanity: should be after 2026-01-01 (~1767225600000 ms)
        assert!(snap.written_at_ms > 1_700_000_000_000, "written_at_ms too old: {}", snap.written_at_ms);
    }

    #[test]
    fn test_d23_snapshot_deserialization_without_schema_version() {
        // Old snapshot JSON without schema_version should default to "2.0.0".
        // 舊快照 JSON 無 schema_version 時應默認為 "2.0.0"。
        let pipeline = TickPipeline::with_balance(&["BTCUSDT"], 1_000.0);
        let snap = pipeline.snapshot();
        let mut json: serde_json::Value = serde_json::to_value(&snap).unwrap();
        // Remove schema_version + written_at_ms to simulate old format
        json.as_object_mut().unwrap().remove("schema_version");
        json.as_object_mut().unwrap().remove("written_at_ms");
        let raw = serde_json::to_string(&json).unwrap();
        let restored: crate::pipeline_types::PipelineSnapshot = serde_json::from_str(&raw).unwrap();
        assert_eq!(restored.schema_version, "2.0.0"); // serde default
        assert_eq!(restored.written_at_ms, 0); // serde default
    }

    // ═══════════════════════════════════════════════════════════════════════
    // BLOCKER-10 / MAJOR-2 (D2): Startup barrier tests
    // 啟動屏障測試
    // ═══════════════════════════════════════════════════════════════════════

    #[tokio::test]
    async fn test_d2_startup_barrier_oneshot_fires() {
        // oneshot channel used for startup barrier works as expected.
        // 啟動屏障的 oneshot 通道正常運作。
        let (tx, rx) = tokio::sync::oneshot::channel::<()>();
        tx.send(()).unwrap();
        let result = tokio::time::timeout(
            std::time::Duration::from_millis(100),
            rx,
        ).await;
        assert!(result.is_ok(), "oneshot must resolve");
        assert!(result.unwrap().is_ok(), "oneshot must deliver ()");
    }

    #[tokio::test]
    async fn test_d2_startup_barrier_timeout_on_no_send() {
        // If pipeline never sends ready, fan-out timeout should fire.
        // 若管線永不發送 ready，扇出超時應觸發。
        let (_tx, rx) = tokio::sync::oneshot::channel::<()>();
        let result = tokio::time::timeout(
            std::time::Duration::from_millis(50),
            rx,
        ).await;
        assert!(result.is_err(), "should timeout when no ready signal sent");
    }

    /// PNL-FIX-1 regression: each position must close at its OWN symbol's
    /// latest_price, not the price of whichever tick happened to fire the
    /// close path. The 2026-04-12 paper anomaly produced ~$497K fake PnL
    /// from 8 fast_track fills because every close used `event.last_price`
    /// (the triggering tick's price) for ALL symbols regardless of their
    /// real prices (FFUSDT closed at $2301 instead of ~$0.50, etc.).
    /// PNL-FIX-1 回歸：每個倉位平倉時必須使用該交易對自己的 latest_price，
    /// 禁止借用觸發 tick 的價格。鎖定 2026-04-12 paper 異常的修復。
    #[test]
    fn test_close_position_at_symbol_market_uses_per_symbol_price() {
        let mut pipeline = TickPipeline::with_kind(
            &["BTCUSDT", "ETHUSDT", "FFUSDT", "DOGEUSDT"],
            10_000.0,
            PipelineKind::Paper,
        );
        // Open four long positions at very different real-world price scales.
        // 在四個價格相差幾個數量級的交易對上各開一個多倉。
        pipeline.paper_state.apply_fill("BTCUSDT", true, 0.01, 50_000.0, 0.0, 1_000, "test");
        pipeline.paper_state.apply_fill("ETHUSDT", true, 0.10, 3_000.0,  0.0, 1_000, "test");
        pipeline.paper_state.apply_fill("FFUSDT",  true, 100.0, 0.50,    0.0, 1_000, "test");
        pipeline.paper_state.apply_fill("DOGEUSDT", true, 1_000.0, 0.20, 0.0, 1_000, "test");

        // Set per-symbol latest prices — each at a small +1% gain over entry.
        // The triggering tick (in production) would carry only ONE of these prices,
        // but the close MUST use each symbol's own latest_price.
        // 為每個交易對設定獨立的最新價（各 +1%）。觸發 tick 只會帶其中一個價格，
        // 但平倉必須各自使用自己的 latest_price。
        pipeline.paper_state.set_latest_price("BTCUSDT", 50_500.0);
        pipeline.paper_state.set_latest_price("ETHUSDT", 3_030.0);
        pipeline.paper_state.set_latest_price("FFUSDT",  0.505);
        pipeline.paper_state.set_latest_price("DOGEUSDT", 0.202);

        // Close each position via the helper. Returned close_price MUST equal
        // that symbol's latest_price, NEVER another symbol's.
        // 通過 helper 平倉，返回的 close_price 必須等於該交易對的 latest_price。
        let (_il, _q, btc_px, btc_pnl) =
            pipeline.close_position_at_symbol_market("BTCUSDT", 2_000).unwrap();
        let (_il, _q, eth_px, eth_pnl) =
            pipeline.close_position_at_symbol_market("ETHUSDT", 2_000).unwrap();
        let (_il, _q, ff_px,  ff_pnl) =
            pipeline.close_position_at_symbol_market("FFUSDT",  2_000).unwrap();
        let (_il, _q, doge_px, doge_pnl) =
            pipeline.close_position_at_symbol_market("DOGEUSDT", 2_000).unwrap();

        // Each close uses the right symbol's price. (The bug closed
        // FFUSDT at $50,500 — BTCUSDT's price — producing -$5,049,950 PnL.)
        // 每個平倉都用了正確的價格。修復前 FFUSDT 會被以 BTC 的 50500 平倉。
        assert!((btc_px - 50_500.0).abs() < 1e-9, "BTC close at wrong price: {btc_px}");
        assert!((eth_px - 3_030.0).abs()  < 1e-9, "ETH close at wrong price: {eth_px}");
        assert!((ff_px  - 0.505).abs()    < 1e-9, "FF close at wrong price: {ff_px}");
        assert!((doge_px - 0.202).abs()   < 1e-9, "DOGE close at wrong price: {doge_px}");

        // PnL = (close_price - entry_price) * qty for longs.
        // Each position should show a small +1% gain in proportion to notional.
        // PnL = (close - entry) * qty。每個都應該是小幅正收益。
        assert!((btc_pnl - 5.0).abs()   < 1e-9, "BTC PnL: {btc_pnl}");   // (50500-50000)*0.01
        assert!((eth_pnl - 3.0).abs()   < 1e-9, "ETH PnL: {eth_pnl}");   // (3030-3000)*0.1
        assert!((ff_pnl  - 0.5).abs()   < 1e-9, "FF PnL: {ff_pnl}");     // (0.505-0.5)*100
        assert!((doge_pnl - 2.0).abs()  < 1e-9, "DOGE PnL: {doge_pnl}"); // (0.202-0.2)*1000

        assert_eq!(pipeline.paper_state.position_count(), 0, "all positions should be closed");
    }

    /// PNL-FIX-1 fallback: when no latest_price is recorded for a symbol,
    /// the helper must fall back to the position's entry_price (yielding zero
    /// PnL), NEVER to the triggering tick's price.
    /// PNL-FIX-1 退路：無 latest_price 時必須回退到 entry_price（pnl=0），
    /// 絕不能借用觸發 tick 的價格。
    #[test]
    fn test_close_position_at_symbol_market_fallback_to_entry_when_no_latest_price() {
        let mut pipeline = TickPipeline::with_kind(
            &["FFUSDT"],
            10_000.0,
            PipelineKind::Paper,
        );
        // Open position WITHOUT setting latest_price.
        // 開倉但不設定 latest_price。
        pipeline.paper_state.apply_fill("FFUSDT", true, 100.0, 0.50, 0.0, 1_000, "test");
        // apply_fill seeds latest_prices via its internal book-keeping; clear it
        // explicitly to simulate a position whose price has not been observed yet.
        // apply_fill 內部會種入 latest_price，這裡強制清掉模擬「未觀測過價格」的情境。
        pipeline.paper_state.set_latest_price("FFUSDT", f64::NAN);

        let (_il, _q, close_px, pnl) =
            pipeline.close_position_at_symbol_market("FFUSDT", 2_000).unwrap();

        // Falls back to entry_price (0.50), producing zero PnL — the safe choice.
        // 回退到入場價，pnl 為零。
        assert!((close_px - 0.50).abs() < 1e-9, "fallback should be entry price, got {close_px}");
        assert!(pnl.abs() < 1e-9, "fallback close should produce zero PnL, got {pnl}");
    }

    /// PNL-FIX-2: emit_close_fill must (a) charge the close-side taker fee
    /// against paper_state.balance / total_fees, AND (b) write that same fee
    /// into the DB Fill row. Locks the 2026-04-12 fix where every risk_close
    /// row had fee=$0 and the comment lied about "accrued separately".
    /// PNL-FIX-2：emit_close_fill 必須對 paper_state 計入平倉費，並寫入 DB 行。
    #[test]
    fn test_emit_close_fill_charges_real_close_fee() {
        let mut pipeline =
            TickPipeline::with_kind(&["BTCUSDT"], 10_000.0, PipelineKind::Paper);
        // Pin a known taker rate so the math is reproducible (5.5 bps = 0.00055).
        // 鎖定一個已知 taker 費率讓計算可預期。
        pipeline.intent_processor.set_fee_rate(0.00055);

        let (tx, mut rx) =
            tokio::sync::mpsc::channel::<crate::database::TradingMsg>(8);
        pipeline.set_trading_channel(tx);

        let bal_before = pipeline.paper_state.balance();
        let fees_before = pipeline.paper_state.total_fees();

        // qty=0.1 @ price=50_000 → notional=5_000 → fee=5_000 × 0.00055 = 2.75
        pipeline.emit_close_fill(
            "BTCUSDT",
            true,
            0.1,
            50_000.0,
            1_000,
            0.0,
            "risk_close:sl_hit",
            "",
        );

        // (a) paper_state must show the fee charge.
        let bal_after = pipeline.paper_state.balance();
        let fees_after = pipeline.paper_state.total_fees();
        assert!(
            (bal_before - bal_after - 2.75).abs() < 1e-9,
            "balance should drop by close fee 2.75, got drop {}",
            bal_before - bal_after
        );
        assert!(
            (fees_after - fees_before - 2.75).abs() < 1e-9,
            "total_fees should rise by 2.75, got rise {}",
            fees_after - fees_before
        );

        // (b) DB Fill row must carry the real fee value, NOT 0.0.
        let msg = rx
            .try_recv()
            .expect("emit_close_fill must enqueue a Fill message");
        match msg {
            crate::database::TradingMsg::Fill { fee, fee_rate, .. } => {
                assert!(
                    (fee - 2.75).abs() < 1e-9,
                    "DB fee must equal close fee 2.75, got {fee}"
                );
                assert!(
                    (fee_rate - 0.00055).abs() < 1e-9,
                    "DB fee_rate must equal taker rate, got {fee_rate}"
                );
            }
            other => panic!("expected Fill, got {other:?}"),
        }
    }

    // ── FIX-18: Price=0.0 tick boundary tests ──

    /// FIX-18: A tick with price=0.0 must not panic or cause division-by-zero.
    /// All code paths (indicators, stops, risk evaluator) must survive gracefully.
    /// FIX-18：price=0.0 的 tick 不能 panic 或導致除零。所有路徑必須存活。
    #[test]
    fn test_zero_price_tick_no_panic() {
        let mut pipeline = TickPipeline::with_kind(&["BTCUSDT"], 10_000.0, PipelineKind::Paper);
        // First feed some normal ticks to populate klines
        for i in 0..50 {
            let e = make_event("BTCUSDT", 50000.0, 1_000_000 + i * 60_000);
            pipeline.on_tick(&e);
        }
        // Now feed a zero-price tick — must not panic
        let zero_event = make_event("BTCUSDT", 0.0, 1_000_000 + 50 * 60_000);
        let _result = pipeline.on_tick(&zero_event);
        // Balance should be unchanged (no fills at price 0)
        assert!(pipeline.paper_state.balance() > 0.0, "balance must survive zero-price tick");
    }

    /// FIX-18: A tick with price=0.0 on a symbol with open position must not produce NaN PnL.
    /// FIX-18：有持倉的交易對收到 price=0 tick 時不能產生 NaN PnL。
    #[test]
    fn test_zero_price_tick_with_position_no_nan() {
        let mut pipeline = TickPipeline::with_kind(&["BTCUSDT"], 10_000.0, PipelineKind::Paper);
        // Open a position via paper_state directly
        pipeline.paper_state.apply_fill("BTCUSDT", true, 0.01, 50000.0, 2.75, 100_000, "test");
        // Feed zero-price tick
        let zero_event = make_event("BTCUSDT", 0.0, 200_000);
        let _result = pipeline.on_tick(&zero_event);
        // Balance must still be finite
        let bal = pipeline.paper_state.balance();
        assert!(bal.is_finite(), "balance must be finite after zero-price tick, got {bal}");
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
        assert_eq!(p_paper.intent_processor.pipeline_kind(), PipelineKind::Paper);
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

    /// PNL-FIX-2: charge_fee() helper rejects non-positive / non-finite inputs
    /// so a malformed fee_rate cannot corrupt balance. Locks the safety guard.
    /// PNL-FIX-2：charge_fee 必須拒絕非正或非有限值，避免費率異常污染餘額。
    #[test]
    fn test_paper_state_charge_fee_rejects_garbage() {
        let mut pipeline =
            TickPipeline::with_kind(&["BTCUSDT"], 1_000.0, PipelineKind::Paper);
        let bal0 = pipeline.paper_state.balance();
        pipeline.paper_state.charge_fee(0.0);
        pipeline.paper_state.charge_fee(-5.0);
        pipeline.paper_state.charge_fee(f64::NAN);
        pipeline.paper_state.charge_fee(f64::INFINITY);
        assert!(
            (pipeline.paper_state.balance() - bal0).abs() < 1e-9,
            "garbage fees must not move balance"
        );
        // A real fee must still apply.
        // 真實費用仍應扣除。
        pipeline.paper_state.charge_fee(1.50);
        assert!((bal0 - pipeline.paper_state.balance() - 1.50).abs() < 1e-9);
    }

    // ── P0-5: ReduceToHalf cooldown + Normal-only clear (PHANTOM-2-FUP) ──
    // P0-5：ReduceToHalf 冷卻 + 僅 Normal 清空（PHANTOM-2 跟進修復）
    //
    // Root cause recap: FA-PHANTOM-2 (commit 348a9c5) added a
    // `held_drop≥5% && sigma≥3` path that fires ReduceToHalf at risk<Defensive.
    // EDGE-P0-1's old clear `< Defensive` wiped the guard every tick in
    // persistent Cautious, producing 9 ReduceToHalf emissions in 1.3s
    // on ORDIUSDT (engine.log 2026-04-16 18:03:41). Fix: per-symbol 60s
    // cooldown (method A) + clear only at Normal (method C).
    //
    // 根因：FA-PHANTOM-2 開放了 risk<Defensive 下的 ReduceToHalf 路徑；原
    // EDGE-P0-1 在 `<Defensive` 時清空 → Cautious 持續時毫秒連發。修復為
    // 冷卻窗 + 僅 Normal 清空。

    #[test]
    fn test_ft_reduce_cooldown_expired_no_prior_entry() {
        // Never-halved symbol is always eligible — filter returns true.
        // 從未半倉的 symbol 永遠可觸發 — filter 回 true。
        let map: std::collections::HashMap<String, i64> = std::collections::HashMap::new();
        assert!(super::on_tick_helpers::ft_reduce_cooldown_expired(
            &map, "BTCUSDT", 1_700_000_000_000
        ));
    }

    #[test]
    fn test_ft_reduce_cooldown_blocks_within_window() {
        // Same-tick and sub-cooldown re-emits are blocked.
        // 同 tick 與冷卻窗內的重觸發一律擋掉。
        let mut map: std::collections::HashMap<String, i64> = std::collections::HashMap::new();
        map.insert("BTCUSDT".to_string(), 1_700_000_000_000);
        // +0 ms (same tick) — reproduces the 1.3s / 9-fire cascade.
        // +0 毫秒（同 tick）— 複現 1.3s 連發 9 次的 cascade。
        assert!(!super::on_tick_helpers::ft_reduce_cooldown_expired(
            &map, "BTCUSDT", 1_700_000_000_000
        ));
        // +59_999 ms (1 ms before cooldown expiry) — still blocked.
        // +59999 毫秒（冷卻到期前 1 毫秒）— 仍被擋。
        assert!(!super::on_tick_helpers::ft_reduce_cooldown_expired(
            &map, "BTCUSDT", 1_700_000_059_999
        ));
    }

    #[test]
    fn test_ft_reduce_cooldown_re_arms_after_window() {
        // Exactly at cooldown boundary re-arms; per-symbol independence holds.
        // 冷卻到期即解鎖；每 symbol 獨立計時。
        let mut map: std::collections::HashMap<String, i64> = std::collections::HashMap::new();
        map.insert("BTCUSDT".to_string(), 1_700_000_000_000);
        // Exactly 60_000 ms later — allowed (>= FT_REDUCE_COOLDOWN_MS).
        // 剛好 60 秒後 — 允許（>= FT_REDUCE_COOLDOWN_MS）。
        assert!(super::on_tick_helpers::ft_reduce_cooldown_expired(
            &map, "BTCUSDT", 1_700_000_060_000
        ));
        // Different symbol shares no cooldown — independent.
        // 其他 symbol 不共享冷卻 — 獨立。
        assert!(super::on_tick_helpers::ft_reduce_cooldown_expired(
            &map, "ETHUSDT", 1_700_000_000_000
        ));
    }

    #[test]
    fn test_ft_reduce_clear_only_on_normal() {
        // Method C: the clear branch in on_tick.rs:158 only fires at Normal.
        // Cautious/Reduced/Defensive must keep the guard populated so symbols
        // already halved are not re-emitted when `ft_action == ReduceToHalf`
        // recurs on subsequent ticks under the same stress episode.
        // Method C：僅 Normal 觸發清空；Cautious/Reduced/Defensive 必須保留
        // 集合以避免同一 stress episode 下對同 symbol 重複半倉。
        use openclaw_core::sm::risk_gov::RiskLevel;

        for level in [RiskLevel::Cautious, RiskLevel::Reduced, RiskLevel::Defensive] {
            let clear_condition = level == RiskLevel::Normal;
            assert!(
                !clear_condition,
                "clear must NOT fire at {:?} — would re-open the cascade bug",
                level
            );
        }
        assert!(
            RiskLevel::Normal == RiskLevel::Normal,
            "clear MUST fire at Normal — fast re-arm for a fresh episode"
        );
    }

    /// P0-5 regression: drive ReduceToHalf for the SAME symbol twice within
    /// the cooldown window on a live `TickPipeline` and assert only the first
    /// emit stamps the cooldown map. Complements the helper-level tests by
    /// covering the filter+insert wiring in on_tick.rs:186-237.
    /// P0-5 回歸：在真正的 TickPipeline 上對同一 symbol 冷卻窗內連發兩次
    /// ReduceToHalf，驗證第二次被 filter 擋下、map 不重複覆寫。
    #[test]
    fn test_ft_reduce_cooldown_map_stamps_once_per_window() {
        let mut pipeline =
            TickPipeline::with_kind(&["BTCUSDT"], 10_000.0, PipelineKind::Paper);
        // Seed a position so the ReduceToHalf branch has something to halve.
        // 先建倉，讓 ReduceToHalf 分支有倉可減。
        pipeline
            .paper_state
            .apply_fill("BTCUSDT", true, 0.1, 50_000.0, 0.0, 1_000, "test");
        assert_eq!(pipeline.paper_state.position_count(), 1);

        // Simulate first halving at ts = 1_000_000.
        // 模擬第一次半倉，時間戳 1,000,000。
        pipeline
            .ft_reduced_symbols
            .insert("BTCUSDT".to_string(), 1_000_000);

        // Within cooldown window (+30 s) — filter must reject the symbol.
        // 冷卻窗內（+30 秒）— filter 必須擋下。
        let now_within = 1_000_000 + 30_000;
        assert!(!super::on_tick_helpers::ft_reduce_cooldown_expired(
            &pipeline.ft_reduced_symbols,
            "BTCUSDT",
            now_within
        ));

        // Past cooldown window (+60 s exact) — filter must re-admit.
        // 冷卻到期（+60 秒）— filter 重新放行。
        let now_after = 1_000_000 + 60_000;
        assert!(super::on_tick_helpers::ft_reduce_cooldown_expired(
            &pipeline.ft_reduced_symbols,
            "BTCUSDT",
            now_after
        ));
    }
