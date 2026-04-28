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
//!        awaits the trading_writer channel. Channel saturation no longer
//!        silently drops rows: the caller (which already runs inside a tokio
//!        select! arm async block) blocks until trading_writer drains. Real
//!        production channel capacity is 4096 (tasks.rs:404) so blocking is
//!        only a back-pressure signal, not a hot-path concern.
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
//!     2. `try_emit_unattributed_fill(...).await` 構造 audit row 並等待
//!        trading_writer channel。通道飽和**不再** silently drop row：caller
//!        本身已在 tokio select! arm 的 async block 中執行，因此 await 只是
//!        對 trading_writer 提供背壓訊號。Production channel capacity = 4096
//!        （tasks.rs:404），實務上不會因 audit row 排隊滿而阻塞 hot path。
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

/// F4-1 audit-row builder + back-pressure aware send. Returns `true` when a row
/// was queued to trading_writer; `false` when (a) engine_mode is paper /
/// live_testnet (skip by design) or (b) `order_tx` is `None` (writer disabled
/// in test fixture). Channel saturation no longer returns false — instead, the
/// `.await` blocks until trading_writer drains (back-pressure handled normally;
/// see F4-RETURN Issue 2 fix 2026-04-26). Channel-closed (sender error) → false.
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
/// F4-1 audit row 構造 + 反壓送出。回傳 `true` 表已排入 trading_writer 佇列；
/// `false` 表 (a) engine_mode 為 paper / live_testnet（依設計跳過）、(b) `order_tx`
/// 為 None（測試 fixture 停用 writer）。通道飽和不再回 `false` — 改由 `.await`
/// 阻塞直到 trading_writer 排空（背壓正常處理；F4-RETURN Issue 2 fix
/// 2026-04-26）。Channel 關閉（sender error） → `false`。
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
    };
    // F4-RETURN Issue 2 (2026-04-26): use send().await for back-pressure.
    // Production channel capacity is 4096 (tasks.rs:404) so this only blocks
    // when trading_writer is genuinely behind (DB slow / saturated). Channel
    // closed (sender error) → false; caller logs `audit_emitted=false` and
    // moves on (real WS reconnect re-emits; fill_id PK keeps DB idempotent).
    // F4-RETURN Issue 2（2026-04-26）：改用 send().await 提供背壓。
    // Production channel capacity = 4096（tasks.rs:404），實際只在
    // trading_writer 真的落後時（DB 慢 / 飽和）阻塞。Channel 關閉 → 回 false；
    // caller 記 `audit_emitted=false` 後繼續（WS 重連重發；DB PK 保冪等）。
    tx.send(msg).await.is_ok()
}
