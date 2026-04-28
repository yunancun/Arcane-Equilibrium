//! F4-1 (2026-04-26): Unit tests for unmatched WS fill audit emission.
//! F4-1（2026-04-26）：未匹配 WS 成交 audit 落地單元測試。
//!
//! MODULE_NOTE (EN): Verifies the `try_emit_unattributed_fill` helper added to
//!   `loop_handlers.rs` correctly routes unmatched live/live_demo/demo WS fills
//!   to `trading_writer` via `TradingMsg::Fill` while skipping paper /
//!   live_testnet (defence-in-depth filter) and failing soft when the writer
//!   channel is absent (None) or saturated (try_send back-pressure).
//! MODULE_NOTE (中): 驗證 `loop_handlers.rs` 新增的 `try_emit_unattributed_fill`
//!   helper 正確將 live/live_demo/demo 的未匹配 WS 成交透過 `TradingMsg::Fill`
//!   送至 `trading_writer`，並在 paper / live_testnet（深層防護過濾）、writer
//!   通道為 None 或飽和（try_send 反壓）時 fail-soft。
//!
//! 涵蓋的合約：
//!   1. live / live_demo / demo → emit + payload 正確
//!   2. paper / live_testnet → skip（不發送）
//!   3. None tx → skip
//!   4. fill_id 前綴 `unattrib-{exec_id}` 可 grep
//!   5. context_id 為 `unattrib-{exec_id}-{ts}` 唯一 + 重發冪等
//!   6. entry_context_id 為空字串（trading_writer 會映射 DB NULL）
//!   7. realized_pnl / fee_rate 為 0（無 entry / 無 TIF context）
//!   8. strategy_name = `"unattributed:bybit_auto"`（ML filter 字首）

// loop_handlers is `mod` (private to event_consumer); access via super::super
// because tests/ is a sibling submodule under event_consumer.
// loop_handlers 在 event_consumer 範圍內為私有 mod；從 tests/ 子模組透過
// super::super 引用同層的 sibling 模組。
use super::super::loop_handlers::{
    engine_mode_emits_unattributed_audit, try_emit_unattributed_fill,
};

/// Helper: build a (tx, rx) pair sized 16 (matches engine production capacity
/// pattern), drain rx after each emit so tests are isolated.
/// 輔助：建立容量 16 的 (tx, rx)，每次 emit 後 drain rx 確保測試彼此獨立。
fn make_chan() -> (
    tokio::sync::mpsc::Sender<crate::database::TradingMsg>,
    tokio::sync::mpsc::Receiver<crate::database::TradingMsg>,
) {
    tokio::sync::mpsc::channel::<crate::database::TradingMsg>(16)
}

// ─────────────────────────────────────────────────────────────────────────
// Engine-mode filter tests / engine_mode 過濾測試
// ─────────────────────────────────────────────────────────────────────────

#[test]
fn test_engine_mode_filter_admits_live() {
    assert!(engine_mode_emits_unattributed_audit("live"));
}

#[test]
fn test_engine_mode_filter_admits_live_demo() {
    assert!(engine_mode_emits_unattributed_audit("live_demo"));
}

#[test]
fn test_engine_mode_filter_admits_demo() {
    assert!(engine_mode_emits_unattributed_audit("demo"));
}

#[test]
fn test_engine_mode_filter_rejects_paper() {
    // PA design §2.2.1: paper has no real WS → must skip.
    // PA design §2.2.1：paper 沒真 WS → 必跳過。
    assert!(!engine_mode_emits_unattributed_audit("paper"));
}

#[test]
fn test_engine_mode_filter_rejects_live_testnet() {
    // No real flow runs on testnet today → exclude per design.
    // testnet 目前無真實流量 → 依設計排除。
    assert!(!engine_mode_emits_unattributed_audit("live_testnet"));
}

#[test]
fn test_engine_mode_filter_rejects_unknown() {
    // Defence-in-depth: any non-allowlisted string → false.
    // 深層防護：任何非白名單字串 → false。
    assert!(!engine_mode_emits_unattributed_audit("unknown"));
    assert!(!engine_mode_emits_unattributed_audit(""));
}

// ─────────────────────────────────────────────────────────────────────────
// try_emit_unattributed_fill: positive cases / 正向測試
// ─────────────────────────────────────────────────────────────────────────

#[tokio::test]
async fn test_emit_for_live_engine_mode_writes_audit_row() {
    let (tx, mut rx) = make_chan();
    let emitted = try_emit_unattributed_fill(
        "live",
        "exec-AAA",
        1_700_000_000_000,
        "order-123",
        "ETHUSDT",
        "Buy",
        0.05,
        2_500.0,
        -0.001,
        Some(&tx),
    ).await;
    assert!(emitted, "live should emit audit row");
    let msg = rx.try_recv().expect("audit row queued to writer channel");
    match msg {
        crate::database::TradingMsg::Fill {
            fill_id,
            ts_ms,
            order_id,
            symbol,
            side,
            qty,
            price,
            fee,
            fee_rate,
            realized_pnl,
            strategy_name,
            context_id,
            entry_context_id,
            engine_mode,
            exit_source,
            liquidity_role,
            ..
        } => {
            assert_eq!(fill_id, "unattrib-exec-AAA");
            assert_eq!(ts_ms, 1_700_000_000_000);
            assert_eq!(order_id, "order-123");
            assert_eq!(symbol, "ETHUSDT");
            assert_eq!(side, "Buy");
            assert!((qty - 0.05).abs() < 1e-9);
            assert!((price - 2_500.0).abs() < 1e-9);
            // Maker rebate (negative fee) preserved verbatim — proves we don't
            // truncate or sanitize on emit. Bybit returns negative fee for
            // PostOnly maker fills.
            // Maker rebate（負費）原樣保留 — 證明 emit 不截斷或清洗。
            // Bybit 對 PostOnly maker 成交回傳負費。
            assert!((fee - (-0.001)).abs() < 1e-9, "fee preserved verbatim");
            assert_eq!(fee_rate, 0.0, "fee_rate=0 (TIF unknown)");
            assert_eq!(realized_pnl, 0.0, "realized_pnl=0 (no entry leg)");
            assert_eq!(strategy_name, "unattributed:bybit_auto");
            assert_eq!(context_id, "unattrib-exec-AAA-1700000000000");
            assert_eq!(entry_context_id, "", "empty → DB NULL via trading_writer");
            assert_eq!(engine_mode, "live");
            assert!(
                exit_source.is_none(),
                "not a Combine-Layer-routed exit fill"
            );
            assert_eq!(liquidity_role.as_deref(), Some("unknown"));
        }
        _ => panic!("expected TradingMsg::Fill, got other variant"),
    }
}

#[tokio::test]
async fn test_emit_for_live_demo_engine_mode_writes_audit_row() {
    let (tx, mut rx) = make_chan();
    let emitted = try_emit_unattributed_fill(
        "live_demo",
        "exec-LD-1",
        1_700_000_001_000,
        "order-LD-1",
        "DOGEUSDT",
        "Sell",
        100.0,
        0.085,
        0.0001,
        Some(&tx),
    ).await;
    assert!(emitted, "live_demo should emit audit row");
    let msg = rx.try_recv().expect("audit row queued");
    if let crate::database::TradingMsg::Fill {
        engine_mode,
        fill_id,
        strategy_name,
        ..
    } = msg
    {
        assert_eq!(engine_mode, "live_demo");
        assert_eq!(fill_id, "unattrib-exec-LD-1");
        assert_eq!(strategy_name, "unattributed:bybit_auto");
    } else {
        panic!("expected TradingMsg::Fill");
    }
}

#[tokio::test]
async fn test_emit_for_demo_engine_mode_writes_audit_row() {
    let (tx, mut rx) = make_chan();
    let emitted = try_emit_unattributed_fill(
        "demo",
        "exec-D-1",
        1_700_000_002_000,
        "order-D-1",
        "SOLUSDT",
        "Buy",
        1.0,
        100.0,
        0.0055,
        Some(&tx),
    ).await;
    assert!(emitted, "demo should emit audit row");
    let msg = rx.try_recv().expect("audit row queued");
    if let crate::database::TradingMsg::Fill {
        engine_mode, ..
    } = msg
    {
        assert_eq!(engine_mode, "demo");
    } else {
        panic!("expected TradingMsg::Fill");
    }
}

// ─────────────────────────────────────────────────────────────────────────
// try_emit_unattributed_fill: negative cases / 反向測試
// ─────────────────────────────────────────────────────────────────────────

#[tokio::test]
async fn test_no_emit_for_paper_engine_mode() {
    // Paper has no real WS. emit must be skipped even when channel is wired.
    // Paper 無真 WS。即使通道已接，仍必須跳過。
    let (tx, mut rx) = make_chan();
    let emitted = try_emit_unattributed_fill(
        "paper",
        "exec-PAPER-1",
        1_700_000_003_000,
        "order-P-1",
        "BTCUSDT",
        "Buy",
        0.001,
        50_000.0,
        0.0275,
        Some(&tx),
    ).await;
    assert!(!emitted, "paper must NOT emit audit row");
    assert!(
        rx.try_recv().is_err(),
        "no message should be in writer channel"
    );
}

#[tokio::test]
async fn test_no_emit_for_live_testnet_engine_mode() {
    let (tx, mut rx) = make_chan();
    let emitted = try_emit_unattributed_fill(
        "live_testnet",
        "exec-T-1",
        1_700_000_004_000,
        "order-T-1",
        "BTCUSDT",
        "Buy",
        0.01,
        50_000.0,
        0.0275,
        Some(&tx),
    ).await;
    assert!(!emitted, "live_testnet must NOT emit audit row");
    assert!(rx.try_recv().is_err());
}

#[tokio::test]
async fn test_no_emit_when_order_tx_is_none() {
    // None tx (test fixture / writer disabled) → fail-soft no-op.
    // None tx（測試 fixture / writer 停用）→ fail-soft no-op。
    let emitted = try_emit_unattributed_fill(
        "live",
        "exec-NONE",
        1_700_000_005_000,
        "order-N-1",
        "ETHUSDT",
        "Buy",
        0.05,
        2_500.0,
        0.0,
        None,
    ).await;
    assert!(!emitted, "None tx → returns false (fail-soft)");
}

#[tokio::test]
async fn test_emit_idempotent_via_fill_id_prefix() {
    // Two emits with same exec_id → both produce identical fill_id, both reach
    // the channel (PK conflict resolution handled at DB layer via ON CONFLICT
    // (fill_id, ts) DO NOTHING — see trading_writer.rs:332).
    // 同 exec_id 兩次 emit → 兩個 fill_id 完全相同；PK 衝突由 DB 層
    // ON CONFLICT (fill_id, ts) DO NOTHING 解決（trading_writer.rs:332）。
    let (tx, mut rx) = make_chan();
    let emit1 = try_emit_unattributed_fill(
        "live",
        "exec-DUP",
        1_700_000_006_000,
        "ord-D",
        "BTCUSDT",
        "Buy",
        0.001,
        50_000.0,
        0.0,
        Some(&tx),
    ).await;
    let emit2 = try_emit_unattributed_fill(
        "live",
        "exec-DUP",
        1_700_000_006_000,
        "ord-D",
        "BTCUSDT",
        "Buy",
        0.001,
        50_000.0,
        0.0,
        Some(&tx),
    ).await;
    assert!(emit1 && emit2, "both emits should succeed (channel not full)");
    let m1 = rx.try_recv().expect("first row");
    let m2 = rx.try_recv().expect("second row");
    let id1 = match m1 {
        crate::database::TradingMsg::Fill { fill_id, .. } => fill_id,
        _ => panic!(),
    };
    let id2 = match m2 {
        crate::database::TradingMsg::Fill { fill_id, .. } => fill_id,
        _ => panic!(),
    };
    assert_eq!(id1, id2, "same exec_id → same fill_id (DB PK dedup)");
    assert_eq!(id1, "unattrib-exec-DUP");
}

#[tokio::test]
async fn test_emit_back_pressure_blocks_then_succeeds_when_drained() {
    // F4-RETURN Issue 2 (2026-04-26): semantics changed from try_send fail-soft
    // to send().await back-pressure. Test design:
    //   1. First emit fills the only channel slot.
    //   2. Run two concurrent futures via tokio::join!:
    //      (a) the second emit (which will block waiting for slot)
    //      (b) a delayed drainer that frees the slot after 20ms
    //      The emit must complete only after the drainer ran (proves blocking).
    //   3. Wrap (2) in tokio::time::timeout(200ms) to fail-fast on regression
    //      that silently drops the row (would return immediately not blocked).
    //   4. Hold rx until end-of-test so channel never closes mid-test.
    // F4-RETURN Issue 2（2026-04-26）：語意從 try_send fail-soft 變為
    // send().await 背壓。設計：
    //   1. 首發填滿唯一 slot。
    //   2. tokio::join! 同時跑 (a) 第二發（會阻塞）+ (b) 20ms 後 drain。
    //      第二發必須在 drainer 跑完後才完成（證明真阻塞）。
    //   3. 200ms timeout fail-fast 防 regression 退回 silent drop。
    //   4. rx 保留到測試末端，避免中途 channel 關閉。
    let (tx, mut rx) = tokio::sync::mpsc::channel::<crate::database::TradingMsg>(1);

    // (1) Fill the only slot.
    let r1 = try_emit_unattributed_fill(
        "live",
        "exec-SAT-1",
        1_700_000_007_000,
        "ord-S",
        "BTCUSDT",
        "Buy",
        0.001,
        50_000.0,
        0.0,
        Some(&tx),
    )
    .await;
    assert!(r1, "first emit fits");

    // (2) Race blocking emit against a delayed drain.
    let drain_start = std::time::Instant::now();
    let result = tokio::time::timeout(
        std::time::Duration::from_millis(200),
        async {
            let drainer = async {
                tokio::time::sleep(std::time::Duration::from_millis(20)).await;
                let _ = rx.recv().await;
            };
            let emit = try_emit_unattributed_fill(
                "live",
                "exec-SAT-2",
                1_700_000_007_001,
                "ord-S2",
                "BTCUSDT",
                "Buy",
                0.001,
                50_000.0,
                0.0,
                Some(&tx),
            );
            let (_, r2) = tokio::join!(drainer, emit);
            r2
        },
    )
    .await
    .expect("emit completes within 200ms after drain (back-pressure path)");
    let elapsed = drain_start.elapsed();

    assert!(result, "second emit succeeds after drain");
    // Sanity check: emit must have waited at least ~15ms (drainer slept 20ms);
    // if it returned immediately we'd be back to silent-drop semantics.
    // Allow generous slack (15ms) for tokio scheduler jitter.
    // 健全性：emit 必須至少等 ~15ms（drainer 睡 20ms）；若立即返回即 regression。
    assert!(
        elapsed >= std::time::Duration::from_millis(15),
        "emit must have blocked while channel was full (elapsed={:?})",
        elapsed
    );
}

#[tokio::test]
async fn test_emit_returns_false_when_channel_closed() {
    // F4-RETURN Issue 2 (2026-04-26): when the receiver is dropped (channel
    // closed), send().await returns Err and emit returns false. This is the
    // graceful shutdown / never-spawned-writer case.
    // F4-RETURN Issue 2（2026-04-26）：receiver 被 drop（通道關閉）時，
    // send().await 回 Err，emit 回 false。涵蓋優雅關閉 / writer 未啟動情境。
    let (tx, rx) = tokio::sync::mpsc::channel::<crate::database::TradingMsg>(1);
    drop(rx); // close the channel
    let r = try_emit_unattributed_fill(
        "live",
        "exec-CLOSED",
        1_700_000_007_500,
        "ord-CLOSED",
        "BTCUSDT",
        "Buy",
        0.001,
        50_000.0,
        0.0,
        Some(&tx),
    )
    .await;
    assert!(!r, "closed channel → false (not silent panic)");
}

#[tokio::test]
async fn test_emit_strategy_name_matches_ml_filter_prefix() {
    // ML pipeline filter is `WHERE strategy_name NOT LIKE 'unattributed:%'`.
    // Our string must begin with that prefix or the filter misses these rows
    // and they pollute training data.
    // ML pipeline 過濾使用 `WHERE strategy_name NOT LIKE 'unattributed:%'`。
    // 字串若不以該前綴起首，過濾失效，會污染訓練資料。
    let (tx, mut rx) = make_chan();
    try_emit_unattributed_fill(
        "demo",
        "exec-MLF",
        1_700_000_008_000,
        "ord-M",
        "BTCUSDT",
        "Buy",
        0.001,
        50_000.0,
        0.0,
        Some(&tx),
    ).await;
    if let Some(crate::database::TradingMsg::Fill { strategy_name, .. }) = rx.try_recv().ok() {
        assert!(
            strategy_name.starts_with("unattributed:"),
            "strategy_name '{}' must begin with 'unattributed:' for ML filter to work",
            strategy_name
        );
    } else {
        panic!("expected TradingMsg::Fill");
    }
}
