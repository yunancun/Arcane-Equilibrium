//! F4-1 unmatched-fill audit emitter (split from loop_handlers.rs).
//! F4-1 未匹配 WS 成交 audit emitter（從 loop_handlers.rs 抽出）。
//!
//! MODULE_NOTE (EN): Hosts the helper that turns an unmatched exchange WS Fill
//!   into a `TradingMsg::Fill` audit row tagged `unattributed:bybit_auto`. Used
//!   by `loop_handlers::handle_exchange_event` only — kept separate so the
//!   `loop_handlers.rs` file stays under the §九 1200-line hard limit and the
//!   audit emitter can be unit-tested without dragging the rest of the loop
//!   handler code into the test surface.
//!
//!   Behaviour:
//!     1. `engine_mode_emits_unattributed_audit(em)` whitelists the three
//!        production engine modes (`live` / `live_demo` / `demo`); paper /
//!        live_testnet / unknown → false (paper has no real WS in production
//!        but the filter is still kept as defence-in-depth so a future paper
//!        WS hookup never accidentally lands audit rows).
//!     2. `try_emit_unattributed_fill(...).await` constructs the audit row and
//!        does a BOUNDED `send_timeout(500ms)` into the trading_writer channel.
//!        ENGINE-CRASH-FIX A1 (2026-06-15): the previous unbounded
//!        `send().await` could block this `select!` arm INDEFINITELY when the
//!        4096-cap channel filled behind a slow PG flush, freezing the tick
//!        atomic + health snapshot this same task updates and tripping the
//!        tick-stale watchdog into SIGTERMing a live engine. Under backpressure
//!        the audit emit is now dropped (fill remains DB-idempotent via PK + WS
//!        reconnect re-emits) — see `try_emit_unattributed_fill` rationale.
//!     3. `fill_id` is `unattrib-{exec_id}` so the same exec_id replayed by
//!        WS reconnect collapses to one DB row via the (fill_id, ts) PK +
//!        ON CONFLICT DO NOTHING in trading_writer.rs:332.
//!
//!   Healthcheck [23] orders⊇fills consistency note (E2 round-1 follow-up):
//!   Audit rows emitted by this helper have `context_id=NULL`-shaped semantics
//!   (no entry leg) and have **no corresponding `trading.orders` row** because
//!   the source is a Bybit auto-action (funding payment / dust scrub /
//!   auto-补单) that never went through OpenClaw's PendingOrder pipeline.
//!   `[23] check_orders_fills_consistency` will count these as "fills missing
//!   orders". This is **audit-by-design**, not a bug — the missing-order count
//!   contributed by `unattributed:%` rows is the legitimate signal that an
//!   external bybit_auto fill landed. The check should treat
//!   `strategy_name LIKE 'unattributed:%'` rows as expected-missing (or
//!   surface them as a separate metric) rather than alerting.
//!
//! MODULE_NOTE (中): 將未匹配交易所 WS Fill 轉成 `unattributed:bybit_auto`
//!   標籤的 `TradingMsg::Fill` audit row。`loop_handlers::handle_exchange_event`
//!   是唯一 caller — 抽出獨立模組以使 `loop_handlers.rs` 維持在 §九 1200 行
//!   硬上限以下，且 audit emitter 可獨立單測（不需要把整段 loop handler 邏輯
//!   拖進測試 surface）。
//!
//!   行為摘要：
//!     1. `engine_mode_emits_unattributed_audit(em)` 白名單三種 production
//!        engine mode（`live` / `live_demo` / `demo`）；paper / live_testnet /
//!        unknown → false（paper 在 production 沒接真 WS，但 filter 保留作
//!        深層防護，避免未來 paper 接 WS 時意外落 audit row）。
//!     2. `try_emit_unattributed_fill(...).await` 構造 audit row 並對
//!        trading_writer channel 做 **有界** `send_timeout(500ms)`。
//!        ENGINE-CRASH-FIX A1（2026-06-15）：先前無界 `send().await` 在
//!        4096-cap channel 因 PG flush 緩慢塞滿時會「無限期」阻塞此 select! arm，
//!        凍結同一 task 更新的 tick atomic + health snapshot，誘使 tick-stale
//!        watchdog 對活著的 live 引擎發 SIGTERM。背壓下改為丟棄此 audit emit
//!        （fill 由 PK 冪等 + WS 重連重發保留）— 詳見 `try_emit_unattributed_fill`。
//!     3. `fill_id` 為 `unattrib-{exec_id}`，WS 重連重發同 exec_id 由 DB
//!        (fill_id, ts) PK + ON CONFLICT DO NOTHING（trading_writer.rs:332）
//!        合併為單行，保證冪等。
//!
//!   Healthcheck [23] orders⊇fills 對應說明（E2 第一輪 review follow-up）：
//!   本 helper 落的 audit row 因 source 是 Bybit 自主動作（funding payment /
//!   dust scrub / auto-补单），**從未經過 OpenClaw 的 PendingOrder pipeline**，
//!   所以 `trading.orders` **無對應 row**。`[23] check_orders_fills_consistency`
//!   會把這些 row 統計為「fills missing orders」。這是 **audit-by-design**，
//!   不是 bug — `unattributed:%` row 貢獻的 missing-order 計數本身就是
//!   「外部 bybit_auto fill 落地」的合法 signal。Healthcheck 應將
//!   `strategy_name LIKE 'unattributed:%'` 的 row 視為預期 missing（或拆成
//!   獨立 metric），而非觸發 alert。

use tracing::warn;

// F4-RETURN Issue 1 (2026-04-26): module split out of loop_handlers.rs to keep
// loop_handlers under the §九 1200-line hard ceiling. Public surface is
// re-exported via `loop_handlers` so existing callers (`tests/unattributed_fill_tests.rs`
// + line 697 of loop_handlers itself) keep their import path.
// F4-RETURN Issue 1（2026-04-26）：從 loop_handlers.rs 抽出獨立模組，使
// loop_handlers 維持在 §九 1200 行硬上限以下。對外介面在 loop_handlers
// 透過 `pub(super) use` 重出，既有 caller 引用路徑不變。

// ─────────────────────────────────────────────────────────────────────────────
// F4-1 (2026-04-26): unmatched-fill audit emitter.
// F4-1（2026-04-26）：未匹配 WS 成交的 audit emitter。
// ─────────────────────────────────────────────────────────────────────────────

/// Engine modes that should emit an `unattributed:bybit_auto` audit row when an
/// exchange WS fill arrives with no matching `PendingOrder`. Paper never gets
/// real WS fills (it has no exchange binding) so it is excluded by design — the
/// emit branch is also a defence-in-depth guard against future regression that
/// might route paper into this code path. `live_testnet` is excluded because no
/// real flow runs on testnet today and audit-row schema budget is reserved for
/// the three production modes.
/// 應落 `unattributed:bybit_auto` audit row 的 engine mode（未匹配 WS 成交時）。
/// Paper 不接真 WS（無交易所綁定）依設計排除；emit 分支同時兼具防止未來 paper
/// 誤走此路徑的深層守護。`live_testnet` 也排除（目前無真實流量）。
#[inline]
pub(super) fn engine_mode_emits_unattributed_audit(em: &str) -> bool {
    matches!(em, "live" | "live_demo" | "demo")
}

/// F4-1 audit-row builder + bounded backpressure-safe send. Returns `true` when
/// a row was queued to trading_writer; `false` when (a) engine_mode is paper /
/// live_testnet (skip by design), (b) `order_tx` is `None` (writer disabled in
/// test fixture), or (c) the bounded `send_timeout(500ms)` failed under
/// backpressure (channel full ≥500ms) or because the channel is closed.
/// ENGINE-CRASH-FIX A1 (2026-06-15): the send is now bounded, NOT an unbounded
/// `.await` — an indefinitely-blocking send on this select! arm froze the tick
/// atomic + health snapshot and tripped the tick-stale watchdog into SIGTERMing
/// a live engine. The drop-on-backpressure is safe (see fn body rationale).
///
/// Strategy_name is hard-coded to `"unattributed:bybit_auto"` so that ML
/// pipelines can filter via `WHERE strategy_name NOT LIKE 'unattributed:%'`
/// without per-source enumeration (future LIVE auto-actions inherit the same
/// prefix). `entry_context_id = ""` → NULL in DB (per trading_writer L318);
/// realized_pnl = 0 because we can't reconstruct an entry to compute PnL
/// against. fee_rate = 0 because TimeInForce is unknown without PendingOrder.
///
/// fill_id is `unattrib-{exec_id}` so dedup against `seen_exec_set` (line 409
/// in loop_handlers.rs) already prevents duplicate emit on WS reconnect; fill_id
/// collision with any future legitimate fill_id is impossible because Bybit
/// exec_id never starts with `unattrib-`.
///
/// **Healthcheck [23] orders⊇fills**: rows emitted here intentionally do **not**
/// have a corresponding `trading.orders` row (source is bybit_auto, not an
/// OpenClaw PendingOrder). The healthcheck's missing-order count from
/// `unattributed:%` rows is the legitimate audit signal, not a bug. See
/// MODULE_NOTE for full context.
///
/// F4-1 audit row 構造 + 有界反壓送出。回傳 `true` 表已排入 trading_writer 佇列；
/// `false` 表 (a) engine_mode 為 paper / live_testnet（依設計跳過）、(b) `order_tx`
/// 為 None（測試 fixture 停用 writer）、(c) 有界 `send_timeout(500ms)` 在背壓
/// （通道滿 ≥500ms）或通道關閉時失敗。ENGINE-CRASH-FIX A1（2026-06-15）：送出
/// 改為有界，**不再**無界 `.await` — 此 select! arm 無限阻塞會凍結 tick atomic
/// + health snapshot 並誘發 tick-stale watchdog 對 live 引擎發 SIGTERM。背壓下
/// 丟棄是安全的（見函數體論證）。
///
/// strategy_name 固定為 `"unattributed:bybit_auto"`，ML pipeline 用
/// `WHERE strategy_name NOT LIKE 'unattributed:%'` 即可過濾，未來 LIVE
/// 自主動作沿用相同前綴。entry_context_id="" → DB NULL（trading_writer L318
/// 規則）；realized_pnl=0 因為無 entry 可計算 PnL；fee_rate=0 因 TimeInForce
/// 在無 PendingOrder 下不可知。
///
/// fill_id 為 `unattrib-{exec_id}`，搭配 `seen_exec_set`（loop_handlers.rs
/// line 409）已避免 WS 重連重發；與未來合法 fill_id 衝突不可能（Bybit exec_id
/// 不會以 `unattrib-` 起首）。
///
/// **Healthcheck [23] orders⊇fills**：本 helper 落的 row 依設計**沒有**對應
/// `trading.orders` row（source = bybit_auto，非 OpenClaw PendingOrder）。
/// Healthcheck 從 `unattributed:%` row 統計到的 missing-order 數量是合法
/// audit signal，不是 bug。詳見模組頂部 MODULE_NOTE。
#[allow(clippy::too_many_arguments)]
pub(super) async fn try_emit_unattributed_fill(
    engine_mode: &str,
    exec_id: &str,
    exec_ts_ms: u64,
    order_id: &str,
    symbol: &str,
    side: &str,
    qty: f64,
    price: f64,
    fee: f64,
    order_tx: Option<&tokio::sync::mpsc::Sender<crate::database::TradingMsg>>,
) -> bool {
    // Defence-in-depth filter: only live / live_demo / demo are eligible.
    // Paper / live_testnet → skip (paper has no real WS by design).
    // 深層防護過濾：僅 live / live_demo / demo 可落 audit。
    // Paper / live_testnet → 跳過（paper 依設計無真 WS）。
    if !engine_mode_emits_unattributed_audit(engine_mode) {
        return false;
    }
    let tx = match order_tx {
        Some(t) => t,
        // None = test fixture or writer disabled — fail-soft no-op.
        // None = 測試 fixture 或 writer 停用 — fail-soft no-op。
        None => return false,
    };
    let msg = crate::database::TradingMsg::Fill {
        // fill_id prefix `unattrib-` makes audit rows visually distinguishable
        // and grep-friendly while preserving dedup via Bybit-globally-unique
        // exec_id suffix. trading.fills PK is (fill_id, ts) so reuse is idempotent.
        // fill_id 加 `unattrib-` 前綴：肉眼可辨、grep 易找；後綴 Bybit 全局
        // 唯一 exec_id 保留 dedup；trading.fills PK (fill_id, ts) 重發冪等。
        fill_id: format!("unattrib-{}", exec_id),
        ts_ms: exec_ts_ms,
        order_id: order_id.to_string(),
        symbol: symbol.to_string(),
        side: side.to_string(),
        qty,
        price,
        fee,
        // fee_rate unknown without PendingOrder TIF context; set 0.
        // fee_rate 在缺少 PendingOrder TIF 上下文時不可知；設 0。
        fee_rate: 0.0,
        reference_price: None,
        reference_ts_ms: None,
        reference_source: None,
        slippage_bps: None,
        liquidity_role: Some("unknown".to_string()),
        fill_latency_ms: None,
        // realized_pnl=0 because there is no entry leg to compute against.
        // Bybit auto-actions (funding payment / dust scrub) are tracked
        // separately via wallet ledger; this audit row only marks the WS
        // fill arrival, not a position event.
        // realized_pnl=0 因無 entry leg 可計算對沖；funding/dust 等 Bybit
        // 自主動作由錢包帳本另記，此 audit row 僅標記 WS fill 抵達，
        // 並非倉位事件。
        realized_pnl: 0.0,
        strategy_name: "unattributed:bybit_auto".to_string(),
        // context_id is non-NULL fill scoped to this single audit emission.
        // context_id 為非 NULL 的單筆 audit 範圍 ID。
        context_id: format!("unattrib-{}-{}", exec_id, exec_ts_ms),
        // Empty → trading_writer L318 maps to DB NULL (no entry linkage).
        // 空字串 → trading_writer L318 對應 DB NULL（無 entry 關聯）。
        entry_context_id: String::new(),
        engine_mode: engine_mode.to_string(),
        // exit_source NULL: this is not a Combine-Layer-routed exit fill.
        // exit_source NULL：非 Combine Layer 路由的退場 fill。
        exit_source: None,
        // V033 (2026-04-29): unattributed audit row carries no exit reason —
        // strategy_name="unattributed:bybit_auto" already encodes the audit
        // path; there is no underlying close decision to trace.
        // V033（2026-04-29）：unattributed audit row 無退場原因 —
        // strategy_name="unattributed:bybit_auto" 已標 audit path，無底層 close 決策可追溯。
        exit_reason: None,
        // V094: unattributed exchange fills are not close-maker attempts.
        // V094：未歸因交易所 fill 不是 close-maker attempt。
        details: None,
        close_maker_attempt: false,
        close_maker_fallback_reason: None,
        // V145：未歸因 fill 無 mid@submit reference，恆 None。
        maker_markout_bps: None,
    };
    // ENGINE-CRASH-FIX A1 (2026-06-15): bounded send 取代無限阻塞 send().await。
    // 為什麼 fail-open drop 在此安全（survival > audit）：
    //   此 helper 跑在 demo/live event_consumer 的 select! arm 內，與 watchdog
    //   讀的 health snapshot + tick atomic「同一個 async task」。先前
    //   F4-RETURN Issue 2 的無界 `tx.send().await` 在 trading_writer 因 PG 慢而
    //   塞滿 4096-cap channel 時會「無限期」阻塞此 task → snapshot + tick 凍結
    //   → tick-stale watchdog（45s/120s）對「活著的 live 引擎」發 SIGTERM →
    //   市價平倉（11 天 ~21 起事故，root cause）。改為 500ms 有界 send：
    //   通道未滿時行為與舊路徑逐位元組相同（仍排入佇列）；只有在背壓真正發生
    //   （通道滿且 500ms 內未排空）時才放棄這一筆 *audit emit*。
    //   丟棄 audit emit 安全：fill 在 DB 以 (fill_id, ts) PK + ON CONFLICT DO
    //   NOTHING 冪等（trading_writer.rs），且 WS 重連會重發同 exec_id；因此
    //   「丟一筆審計排隊」遠優於「凍結交易迴圈」。Timeout/Full/Closed 三種
    //   失敗一律回 false（鏡像舊的 channel-closed → audit_emitted=false 路徑），
    //   caller 記錄後繼續。
    let send_start = std::time::Instant::now();
    let result = tx
        .send_timeout(msg, std::time::Duration::from_millis(500))
        .await;
    let elapsed = send_start.elapsed();
    // C3 instrumentation：熱路徑背壓觀測。送出超過 ~200ms 即代表 trading_writer
    // 已落後到危險區間（接近 channel-fill horizon），在 prod log 留證據。
    if elapsed.as_millis() > 200 {
        warn!(
            elapsed_ms = elapsed.as_millis() as u64,
            "unattributed audit send slow — trading_tx backpressure \
             / unattributed audit 送出緩慢 — trading_tx 背壓"
        );
    }
    match result {
        Ok(()) => true,
        Err(e) => {
            // 有界 send 失敗 = 背壓（Timeout/Full）或寫入器已退出（Closed）。
            // 一律丟棄此 audit emit 並回 false（見上方安全論證）；單調遞增
            // 丟棄計數供 operator / healthcheck 觀測。1Hz 節流避免 log flood。
            let total = UNATTRIB_AUDIT_DROPPED.fetch_add(1, std::sync::atomic::Ordering::Relaxed) + 1;
            if should_emit_drop_warn() {
                warn!(
                    total_dropped = total,
                    elapsed_ms = elapsed.as_millis() as u64,
                    error = %e,
                    "unattributed audit dropped under trading_tx backpressure \
                     (warn 1Hz sampled) — fill stays DB-idempotent via PK + WS \
                     reconnect re-emits / unattributed audit 因 trading_tx 背壓丟棄"
                );
            }
            false
        }
    }
}

// ENGINE-CRASH-FIX A1 (2026-06-15): 模組級單調丟棄計數 + 1Hz warn 節流。
// 為什麼 module-level static：此 emit helper 是 leaf fn，無持有 handle 可掛
// 計數；canary_writer 用 Arc<AtomicU64> 因其有 handle struct，這裡用 static
// 等價且零接線成本。計數單調遞增方便 operator / 未來 healthcheck 觀測累計丟棄。
static UNATTRIB_AUDIT_DROPPED: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
static UNATTRIB_DROP_LAST_WARN_MS: std::sync::atomic::AtomicU64 =
    std::sync::atomic::AtomicU64::new(0);

/// 每 1000ms 至多回傳一次 true（跨所有呼叫），用 CAS 序列化 — 換到時間戳的
/// 執行緒取得發 warn 權。鏡像 canary_writer::should_emit_warn 模式，避免持續
/// 背壓下 warn 本身成為 log flood。
fn should_emit_drop_warn() -> bool {
    const WARN_THROTTLE_MS: u64 = 1000;
    let now_ms = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_millis() as u64)
        .unwrap_or(0);
    let last = UNATTRIB_DROP_LAST_WARN_MS.load(std::sync::atomic::Ordering::Relaxed);
    if now_ms.saturating_sub(last) < WARN_THROTTLE_MS {
        return false;
    }
    UNATTRIB_DROP_LAST_WARN_MS
        .compare_exchange(
            last,
            now_ms,
            std::sync::atomic::Ordering::Relaxed,
            std::sync::atomic::Ordering::Relaxed,
        )
        .is_ok()
}
