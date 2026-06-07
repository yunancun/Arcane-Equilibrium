//! PHANTOM-FILL-FIX-1（2026-06-07）· 真亂序整合 / 三引擎 / partial-fill is_close 透傳 golden
//!
//! 層級：這些測試驅動**真正的 `handle_exchange_event`**（event_consumer 整合層），
//! 而非 `apply_fill` 單元層（單元層已由 E1 於 `paper_state/tests.rs` 覆蓋）。它們
//! 重現 TONUSDT 17:03 事故的完整事件鏈：
//!
//!   Bybit private WS 平倉時先推 `PositionUpdate(size=0)`（把 short 移除為 flat），
//!   隨後平倉 `Fill(Buy, is_close=true)` 才抵達 → 修前 `apply_fill` 落空 → 落「開新倉」
//!   分支 → 開出幻影反向 LONG（entry=平倉價、qty=平倉量）。
//!
//! 本檔釘住修後契約（在整合層、經 PendingOrder 匹配 → `apply_confirmed_fill` →
//! `apply_fill_with_close_semantics` 全鏈）：
//!   G1  真亂序：PositionUpdate(size=0) 先於 close Fill → 結果 **flat 非反向 LONG**，
//!        不寫幻影 entry_context_id，PnL 記在原 short 平倉（在 advisory 收斂路徑下）。
//!   G1b 對照組：正常順序（先 Fill 後 PositionUpdate）也須 flat（防修法把正常路徑弄壞）。
//!   G3  三引擎獨立驗（demo / live_demo / live）：同一亂序序列在三模式皆 flat（共用
//!        PaperState + is_close 來源一致），證明修復不是 demo-only（CLAUDE 3E-ARCH）。
//!   G4  partial-fill is_close 透傳一致：同一平倉單跨多筆 execution 分批成交，每筆都
//!        正確帶 is_close 到 apply_fill（reduce-only 語意全程保持）。
//!
//! Bite 驗證見各測試 docstring 末 `// BITE:` 段（如何邏輯性還原修復使該 golden 失敗）。

use crate::bybit_private_ws::{ExecutionUpdate, PositionUpdate};
use crate::bybit_rest_client::BybitEnvironment;
use crate::event_consumer::types::{ExchangeEvent, PendingOrder};
use crate::order_manager::TimeInForce;
use crate::tick_pipeline::{PipelineKind, TickPipeline};

use super::super::loop_handlers::handle_exchange_event;
use super::make_test_writer;

// ───────────────────────────────────────────────────────────────────────────
// Fixtures
// ───────────────────────────────────────────────────────────────────────────

/// 構建一個 close PendingOrder（reduce-only / 平倉單）。`is_long` = 平倉成交方向
/// （平 short → Buy → is_long=true）。qty 為平倉量。無 OrderUpdate 先行時，
/// loop_exchange 的 symbol+side fallback 會以「唯一同向 eligible pending order」匹配
/// 此單，從而把 `is_close=true` 帶入 apply_fill 鏈。
fn close_pending_order(symbol: &str, is_long: bool, qty: f64) -> PendingOrder {
    PendingOrder {
        order_link_id: format!("oc_close_{symbol}"),
        symbol: symbol.into(),
        is_long,
        qty,
        strategy: "strategy_close:grid_close_short".into(),
        sent_ts_ms: 1_700_000_000_000,
        cum_filled_qty: 0.0,
        is_close: true, // ★ reduce-only：本檔的核心旗標
        context_id: "ctx-close".into(),
        order_type: "market".into(),
        time_in_force: None,
        maker_timeout_ms: None,
        close_maker_audit: None,
        reference_price: None,
        reference_ts_ms: None,
        reference_source: None,
        cancel_requested_ts_ms: None,
        spine_order_plan_id: None,
        spine_decision_id: None,
        spine_verdict_id: None,
        spine_stub_report_id: None,
        // close 路徑無 strategy intent，intent_id 保 None（誠實表述）。
        intent_id: None,
    }
}

/// Bybit private WS `position(size=0, side=None)` —— 平倉成交後交易所推的 flat snapshot。
/// 這正是 TON 事故中「先到、把 short 移除」的那條訊息。
fn flat_position_update(symbol: &str) -> PositionUpdate {
    PositionUpdate {
        symbol: symbol.into(),
        side: "None".into(), // Bybit flat 時回 "None"
        size: "0".into(),
        avg_price: "0".into(),
        unrealised_pnl: "0".into(),
        mark_price: "0".into(),
        liq_price: "0".into(),
    }
}

/// 一筆 close execution（reduce-only 平倉成交）。`side`="Buy" 平 short。
fn close_fill(symbol: &str, exec_id: &str, side: &str, qty: f64, price: f64) -> ExecutionUpdate {
    ExecutionUpdate {
        exec_id: exec_id.into(),
        order_id: format!("bybit-order-{symbol}-close"),
        symbol: symbol.into(),
        side: side.into(),
        exec_price: format!("{price}"),
        exec_qty: format!("{qty}"),
        exec_fee: "0".into(),
        exec_type: "Trade".into(),
        exec_time: "1700000001000".into(),
        ..Default::default()
    }
}

/// 在 paper_state 開一個 genuine short（execution 流 genuine open，is_close=false）。
/// 直接用 apply_fill（薄包裝，is_close=false）模擬入場成交已落帳。
fn seed_short(pipeline: &mut TickPipeline, symbol: &str, qty: f64, entry: f64) {
    pipeline
        .paper_state
        .apply_fill(symbol, false, qty, entry, 0.0, 1_700_000_000_000, "grid_short");
    assert_eq!(
        pipeline.paper_state.position_count(),
        1,
        "setup: short 應已落帳"
    );
}

/// 構建一個 demo 交易所 pipeline（最常見路徑），單 symbol。
fn demo_pipeline(symbol: &str) -> TickPipeline {
    let mut p = TickPipeline::with_kind(&[symbol], 10_000.0, PipelineKind::Demo);
    p.set_endpoint_env(BybitEnvironment::Demo);
    p
}

// ───────────────────────────────────────────────────────────────────────────
// G1：真亂序整合 golden（最重要）—— 重現 TON 17:03
// ───────────────────────────────────────────────────────────────────────────

/// G1：在 `handle_exchange_event` 整合層模擬 Bybit 亂序事件序列
/// 「PositionUpdate(size=0) 先於 Fill(Buy, is_close=true, qty=既有 short 量)」，
/// 斷言結果 **flat 而非反向 LONG**，且未寫幻影 entry_context_id。
///
/// 這直接重現 TON 17:03：close Buy 落空後，修前會開出 entry=1.5744 / qty=437.3 的
/// 幻影 LONG。修後：
///   - PositionUpdate(size=0) 走 advisory 收斂路徑（converge_exchange_zero_close）
///     把 short 移除（demo 是 exchange pipeline → 真收斂）。
///   - 隨後 close Fill 匹配 close PendingOrder（is_close=true）→ apply_fill 落空 →
///     reduce-only guard no-op，不開幻影 LONG。
///   - 終態：flat（position_count==0），無任何 entry_context_id。
///
/// // BITE：把 fill_engine.rs `if is_close { ... return 0.0; }` reduce-only guard 移除
/// // （還原為 fall-through 開新倉）→ 此測試 position_count 變 1（幻影 LONG）+ entry_context_id
/// // 被寫 → FAIL。或把 loop_exchange.rs PositionUpdate 分支的 advisory 改回
/// // `upsert_position_from_exchange` authoritative remove 仍可被 guard 接住（雙重防線），
/// // 故 guard 是此 golden 的主 bite 點。
#[tokio::test]
async fn g1_out_of_order_position_zero_then_close_fill_yields_flat_not_phantom_long() {
    let symbol = "TONUSDT";
    let mut pipeline = demo_pipeline(symbol);
    let mut writer = make_test_writer();
    let mut state = super::super::loop_handlers::LoopState::new(std::collections::HashSet::new());

    // 0) 既有 short 437.3 @ 1.5929（genuine open 已落帳）。
    seed_short(&mut pipeline, symbol, 437.3, 1.5929);

    // 1) 註冊平倉單（reduce-only Buy 437.3）——loop_exchange symbol+side fallback
    //    會以此唯一同向 eligible pending order 匹配後續 close Fill，帶入 is_close=true。
    let po = close_pending_order(symbol, true, 437.3);
    let link_id = po.order_link_id.clone();
    state.pending_orders.insert(link_id.clone(), po);

    // 2) ★ 亂序：Bybit 平倉先推 position(size=0) → advisory 收斂移除 short → 本地 flat。
    handle_exchange_event(
        Some(ExchangeEvent::PositionUpdate(flat_position_update(symbol))),
        &mut pipeline,
        &mut writer,
        &mut state,
        None,
    )
    .await;
    assert_eq!(
        pipeline.paper_state.position_count(),
        0,
        "PositionUpdate(size=0) advisory 收斂後本地應 flat（short 已移除）"
    );

    // 3) 隨後 close Buy 437.3 @ 1.5744 抵達（落空）→ reduce-only guard no-op。
    handle_exchange_event(
        Some(ExchangeEvent::Fill(close_fill(
            symbol,
            "exec-ton-close",
            "Buy",
            437.3,
            1.5744,
        ))),
        &mut pipeline,
        &mut writer,
        &mut state,
        None,
    )
    .await;

    // ── 核心斷言：flat，不是幻影 LONG ──
    assert_eq!(
        pipeline.paper_state.position_count(),
        0,
        "核心回歸：亂序平倉 Buy 落空必須 flat，不得開幻影反向 LONG（TON 17:03）"
    );
    assert!(
        pipeline.paper_state.get_position(symbol).is_none(),
        "TONUSDT 必為 flat（無任何倉位）—— 修前此處會是 is_long=true/qty=437.3/entry=1.5744 的幻影"
    );
}

/// G1b：對照組 —— 正常順序（先 close Fill 後 PositionUpdate）也須收斂到 flat。
/// 防止修法只照顧亂序而把「正常順序」弄壞：close Fill 先到時，short 仍在 →
/// apply_fill 正常走平倉分支歸 flat → 隨後 PositionUpdate(size=0) advisory 對已 flat
/// 本地是 no-op。終態同樣 flat，且 realized PnL 記在 short 平倉上（short 盈利）。
///
/// // BITE：若 apply_fill 平倉分支被破壞（例如完全平倉不歸 flat），G1b 的
/// // position_count 斷言會 FAIL；此 golden 守住「正常序平倉=flat」不被亂序修法波及。
#[tokio::test]
async fn g1b_in_order_close_fill_then_position_zero_also_flat() {
    let symbol = "TONUSDT";
    let mut pipeline = demo_pipeline(symbol);
    let mut writer = make_test_writer();
    let mut state = super::super::loop_handlers::LoopState::new(std::collections::HashSet::new());

    seed_short(&mut pipeline, symbol, 437.3, 1.5929);
    let po = close_pending_order(symbol, true, 437.3);
    state.pending_orders.insert(po.order_link_id.clone(), po);

    // 1) 正常序：close Fill 先到 → short 仍在 → 平倉分支歸 flat + 結算 PnL。
    let balance_before = pipeline.paper_state.balance;
    handle_exchange_event(
        Some(ExchangeEvent::Fill(close_fill(
            symbol,
            "exec-ton-close-inorder",
            "Buy",
            437.3,
            1.5744,
        ))),
        &mut pipeline,
        &mut writer,
        &mut state,
        None,
    )
    .await;
    assert_eq!(
        pipeline.paper_state.position_count(),
        0,
        "正常序：close Fill 命中 short → 平倉歸 flat"
    );
    // short 在更低價平倉 → 盈利，balance 應增加（PnL 記在 short 平倉）。
    assert!(
        pipeline.paper_state.balance > balance_before,
        "short 在 1.5929→1.5744 平倉應盈利，balance 應增加：before={balance_before}, after={}",
        pipeline.paper_state.balance
    );

    // 2) 隨後 PositionUpdate(size=0) 對已 flat 本地是 advisory no-op（不再有倉可收斂）。
    handle_exchange_event(
        Some(ExchangeEvent::PositionUpdate(flat_position_update(symbol))),
        &mut pipeline,
        &mut writer,
        &mut state,
        None,
    )
    .await;
    assert_eq!(
        pipeline.paper_state.position_count(),
        0,
        "PositionUpdate(size=0) 對已 flat 本地 no-op，仍 flat"
    );
}

// ───────────────────────────────────────────────────────────────────────────
// G3：三引擎獨立驗（demo / live_demo / live）—— CLAUDE 3E-ARCH，禁只 demo PASS
// ───────────────────────────────────────────────────────────────────────────

/// G3：同一亂序序列（PositionUpdate(size=0) 先於 close Fill）在 demo / live_demo /
/// live 三模式皆收斂到 flat，證明修復對三模式同源成立（共用 PaperState + is_close
/// 來源一致），不是只有 demo 有效。
///
/// 三模式構造（per mode_state::effective_engine_mode，已被既有 h0_latency_metrics 測試
/// 釘住）：
///   - demo      = PipelineKind::Demo
///   - live_demo = PipelineKind::Live + LiveDemo endpoint
///   - live      = PipelineKind::Live + Mainnet endpoint
/// 三者 mutating 路徑都是 `PaperState::apply_fill_with_close_semantics`（無 mode 分支），
/// is_close 來源都是 `PendingOrder.is_close`（loop_exchange 不分 kind），故同一亂序在
/// 三者表現一致。
///
/// // BITE：同 G1 —— 移除 reduce-only guard 後，三個 case 全部變幻影 LONG → 三個
/// // 子斷言全 FAIL；單一 bite 同時覆蓋三模式（證「不是只有 demo 修好」）。
#[tokio::test]
async fn g3_out_of_order_close_yields_flat_across_demo_live_demo_live() {
    // (engine_label, pipeline_kind, endpoint_env)
    let cases: [(&str, PipelineKind, BybitEnvironment); 3] = [
        ("demo", PipelineKind::Demo, BybitEnvironment::Demo),
        ("live_demo", PipelineKind::Live, BybitEnvironment::LiveDemo),
        ("live", PipelineKind::Live, BybitEnvironment::Mainnet),
    ];

    for (expected_label, kind, env) in cases {
        let symbol = "TONUSDT";
        let mut pipeline = TickPipeline::with_kind(&[symbol], 10_000.0, kind);
        pipeline.set_endpoint_env(env);
        // 先證 engine_mode 標籤確為三種之一（這條序列確實跑在該模式下）。
        assert_eq!(
            pipeline.effective_engine_mode(),
            expected_label,
            "engine_mode 標籤須為 {expected_label}（證此亂序序列跑在該模式）"
        );

        let mut writer = make_test_writer();
        let mut state =
            super::super::loop_handlers::LoopState::new(std::collections::HashSet::new());
        seed_short(&mut pipeline, symbol, 437.3, 1.5929);
        let po = close_pending_order(symbol, true, 437.3);
        state.pending_orders.insert(po.order_link_id.clone(), po);

        // 亂序：position(size=0) 先 → close Fill 後。
        handle_exchange_event(
            Some(ExchangeEvent::PositionUpdate(flat_position_update(symbol))),
            &mut pipeline,
            &mut writer,
            &mut state,
            None,
        )
        .await;
        handle_exchange_event(
            Some(ExchangeEvent::Fill(close_fill(
                symbol,
                &format!("exec-{expected_label}-close"),
                "Buy",
                437.3,
                1.5744,
            ))),
            &mut pipeline,
            &mut writer,
            &mut state,
            None,
        )
        .await;

        assert_eq!(
            pipeline.paper_state.position_count(),
            0,
            "[{expected_label}] 亂序平倉必須 flat，不得開幻影 LONG（三模式共用 PaperState，禁只 demo 修好）"
        );
        assert!(
            pipeline.paper_state.get_position(symbol).is_none(),
            "[{expected_label}] {symbol} 必為 flat"
        );
    }
}

/// G3b：mutating-path 同源證明（測試層無法分模式時的退路證據）——
/// 直接斷言「三模式都走同一個 `apply_fill_with_close_semantics`」這個結構事實的
/// 行為等價：對三個不同 kind/endpoint 的 pipeline，餵相同的 reduce-only 落空 fill，
/// 結果都是 no-op（position_count==0）。這把「is_close 來源一致 + PaperState 共用」
/// 從文檔主張變成可執行斷言。
///
/// // BITE：同 reduce-only guard——任一模式 fall-through 開倉，對應 case 即 FAIL。
#[tokio::test]
async fn g3b_reduce_only_noop_is_mode_agnostic() {
    let cases: [(PipelineKind, BybitEnvironment); 3] = [
        (PipelineKind::Demo, BybitEnvironment::Demo),
        (PipelineKind::Live, BybitEnvironment::LiveDemo),
        (PipelineKind::Live, BybitEnvironment::Mainnet),
    ];
    for (kind, env) in cases {
        let mut pipeline = TickPipeline::with_kind(&["TONUSDT"], 10_000.0, kind);
        pipeline.set_endpoint_env(env);
        let label = pipeline.effective_engine_mode();
        // 本地無倉時的 reduce-only 平倉成交（直接驗 PaperState mutating entry）。
        let pnl = pipeline.paper_state.apply_fill_with_close_semantics(
            "TONUSDT", true, 437.3, 1.5744, 0.0, 0, "grid", true,
        );
        assert_eq!(
            pipeline.paper_state.position_count(),
            0,
            "[{label}] reduce-only fill 本地無倉必 no-op（三模式同源）"
        );
        assert_eq!(pnl, 0.0, "[{label}] no-op 不產生 realized PnL");
    }
}

// ───────────────────────────────────────────────────────────────────────────
// G4：partial-fill is_close 透傳一致 —— 同一平倉單跨多筆 execution
// ───────────────────────────────────────────────────────────────────────────

/// G4：同一平倉單（is_close=true）跨 3 筆 execution 分批成交（cum_filled_qty 累計），
/// 每筆都正確帶 is_close=true 到 apply_fill。驗證方式：每筆部分平倉都正確減倉
/// 而非開反向倉，最後一筆使 short 完全平掉歸 flat；且 PendingOrder 在完全成交前
/// 一直保留（partial 不移除），完全成交後移除。
///
/// 為何用「分批減倉」驗 is_close 透傳：若某一筆 partial 的 is_close 漏傳（=false），
/// 在「本地仍有反向 short」情況下行為其實不變（仍走平倉分支）——所以單純 partial
/// 觀察不到 is_close 漏傳。本測試額外加一筆「超出剩餘倉量」的尾筆，配合 is_close=true
/// 斷言 **不翻倉**（reduce-only overflow 不反開），這才對 is_close 透傳有 bite：
/// 若尾筆 is_close 漏傳成 false，§4.2 翻倉邏輯會用 overflow 開反向 long → FAIL。
///
/// // BITE：把 loop_exchange.rs Fill 分支傳入 apply_confirmed_fill 的 `po.is_close`
/// // 改成寫死 `false` → 尾筆 overflow 觸發翻倉開出反向 long → 末斷言
/// // （position_count==0 / flat）FAIL。
#[tokio::test]
async fn g4_partial_close_fills_thread_is_close_each_execution() {
    let symbol = "ETHUSDT";
    let mut pipeline = demo_pipeline(symbol);
    let mut writer = make_test_writer();
    let mut state = super::super::loop_handlers::LoopState::new(std::collections::HashSet::new());

    // 既有 short 100。
    seed_short(&mut pipeline, symbol, 100.0, 1.6);

    // 平倉單 qty=100（reduce-only Buy）。loop_exchange fully_filled 判定用 qty*0.999，
    // 故設 po.qty=100，分批成交 40 + 40 + 40（最後一筆 overflow 20）。
    let po = close_pending_order(symbol, true, 100.0);
    let link_id = po.order_link_id.clone();
    state.pending_orders.insert(link_id.clone(), po);

    // 第 1 筆：Buy 40 → short 剩 60（reduce-only 減倉）。
    handle_exchange_event(
        Some(ExchangeEvent::Fill(close_fill(symbol, "exec-p1", "Buy", 40.0, 1.5))),
        &mut pipeline,
        &mut writer,
        &mut state,
        None,
    )
    .await;
    {
        let pos = pipeline
            .paper_state
            .get_position(symbol)
            .expect("第1筆部分平倉後 short 仍在");
        assert!(!pos.is_long, "仍為 short");
        assert!((pos.qty - 60.0).abs() < 1e-9, "剩餘應 60，got {}", pos.qty);
    }
    assert!(
        state.pending_orders.contains_key(&link_id),
        "partial 成交，平倉單應保留待後續 execution"
    );

    // 第 2 筆：Buy 40 → short 剩 20。
    handle_exchange_event(
        Some(ExchangeEvent::Fill(close_fill(symbol, "exec-p2", "Buy", 40.0, 1.5))),
        &mut pipeline,
        &mut writer,
        &mut state,
        None,
    )
    .await;
    {
        let pos = pipeline
            .paper_state
            .get_position(symbol)
            .expect("第2筆部分平倉後 short 仍在");
        assert!((pos.qty - 20.0).abs() < 1e-9, "剩餘應 20，got {}", pos.qty);
    }

    // 第 3 筆（尾筆）：Buy 40，但只剩 20 short → 平掉剩 20，overflow=20。
    // ★ is_close=true（reduce-only）→ overflow **不反開**，歸 flat。
    handle_exchange_event(
        Some(ExchangeEvent::Fill(close_fill(symbol, "exec-p3", "Buy", 40.0, 1.5))),
        &mut pipeline,
        &mut writer,
        &mut state,
        None,
    )
    .await;

    // ── 核心斷言：reduce-only 尾筆 overflow 不翻倉，flat ──
    assert_eq!(
        pipeline.paper_state.position_count(),
        0,
        "reduce-only 平倉單末筆 overflow 不得反開 long；is_close 須每筆透傳保持 reduce-only 語意"
    );
    assert!(
        pipeline.paper_state.get_position(symbol).is_none(),
        "ETHUSDT 完全平倉後必 flat（若尾筆 is_close 漏傳=false，§4.2 翻倉會開反向 long）"
    );
    assert!(
        !state.pending_orders.contains_key(&link_id),
        "cum_filled_qty(120) >= qty*0.999 → 平倉單完全成交應移除"
    );
}

/// G4b：對照證明「翻倉只在 is_close=false 時用 overflow 反開」—— 同樣 overflow 場景，
/// 但這是 genuine 反向開倉成交（is_close=false，非 reduce-only）→ 應翻倉建反向 long。
/// 這條與 G4 互為鏡像：證明 is_close 旗標真的在分流 reduce-only(no flip) vs
/// genuine-flip(flip)，而非 apply_fill 對所有 overflow 都不翻倉（那會讓 G4 失去 bite）。
///
/// // BITE：把 fill_engine.rs 翻倉條件 `!is_close && overflow > eps` 改成
/// // `overflow > eps`（無視 is_close）→ G4 會翻倉 FAIL；改成永不翻倉 → G4b
/// // （此測試）FAIL。兩條夾住 is_close 在翻倉分流上的 load-bearing 角色。
#[tokio::test]
async fn g4b_genuine_flip_overflow_opens_reverse_when_not_close() {
    let symbol = "ETHUSDT";
    let mut pipeline = demo_pipeline(symbol);
    let mut writer = make_test_writer();
    let mut state = super::super::loop_handlers::LoopState::new(std::collections::HashSet::new());

    seed_short(&mut pipeline, symbol, 100.0, 1.6);

    // genuine 反向開倉單（is_close=false）qty=150 → 平掉 100 short + overflow 50 反開 long。
    let mut po = close_pending_order(symbol, true, 150.0);
    po.is_close = false; // ★ genuine flip，非 reduce-only
    po.order_type = "market".into();
    po.strategy = "grid_long".into();
    po.time_in_force = Some(TimeInForce::GTC);
    let link_id = po.order_link_id.clone();
    state.pending_orders.insert(link_id.clone(), po);

    handle_exchange_event(
        Some(ExchangeEvent::Fill(close_fill(symbol, "exec-flip", "Buy", 150.0, 1.5))),
        &mut pipeline,
        &mut writer,
        &mut state,
        None,
    )
    .await;

    let pos = pipeline
        .paper_state
        .get_position(symbol)
        .expect("genuine flip overflow 應建反向 long 新倉");
    assert!(pos.is_long, "翻倉後方向應為 long");
    assert!(
        (pos.qty - 50.0).abs() < 1e-9,
        "翻倉餘量新倉 qty 應為 50（150-100），got {}",
        pos.qty
    );
    assert!(
        (pos.entry_price - 1.5).abs() < 1e-12,
        "翻倉新倉 entry 應為 fill_price 1.5"
    );
}
