//! V033 W1-T1 strategy attribution cleanup — `build_close_tags` helper.
//! V033 W1-T1 策略歸因清理 — `build_close_tags` helper。
//!
//! ## Split rationale (HELPERS-CLOSE-TAGS-SPLIT, 2026-04-29)
//!
//! `helpers.rs` baseline 1411 LOC was already above the 800-line warn line
//! (CLAUDE.md §九). Adding `build_close_tags` + 4 unit tests in W1-T1 brought
//! it to 1639 LOC, exceeding the 1200-line hard cap and the §九 pre-existing
//! "baseline + 5 LOC" exception clause (1416 LOC ceiling). To stay compliant
//! without altering logic, the W1-T1 helper and its tests live in this
//! dedicated file. W1-T2 then added the legacy-tag normalizer in the same
//! sibling module; the parent `mod.rs` re-exports
//! `build_close_tags_from_legacy` for close emitters.
//!
//! ## 拆檔理由（HELPERS-CLOSE-TAGS-SPLIT，2026-04-29）
//!
//! `helpers.rs` baseline 1411 LOC 已逾 800 行警戒線（CLAUDE.md §九）。W1-T1
//! 加入 `build_close_tags` + 4 unit tests 後達 1639 LOC，越過 1200 行硬上限
//! 與「baseline + 5 LOC」例外條款上限 1416。為維持合規且 **不改 logic**，將
//! W1-T1 helper 與其 tests 拆至本 sibling 檔案；W1-T2 後同檔新增 legacy-tag
//! normalizer。父 `mod.rs` 透過 `pub(crate) use` re-export
//! `build_close_tags_from_legacy` 供 close emitter 呼叫。
//!
//! ## Upstream design / 上游設計
//!
//! PA design report: `docs/CCAgentWorkSpace/PA/workspace/reports/
//! 2026-04-29--strategy_name_attribution_cleanup_design.md` §4 W1-T1.
//!
//! Pairs with V033 SQL migration `sql/migrations/V033__fills_exit_reason.sql`
//! (Guard A/B + partial index `idx_fills_exit_reason_prefix`) and the
//! `TradingMsg::Fill::exit_reason` field added in `database/mod.rs`.
//!
//! ## W1-T2 integration note / W1-T2 接入備註
//!
//! Close emitters now call `build_close_tags_from_legacy`, which converts the
//! pre-existing `strategy_close:*` / `risk_close:*` tags into the V033
//! `(strategy_name, exit_reason)` DB contract. The legacy close tag still feeds
//! in-memory recent fills and exit-feature classification.
//!
//! close emitter 現已呼叫 `build_close_tags_from_legacy`，將既有
//! `strategy_close:*` / `risk_close:*` tag 轉為 V033 DB 契約；legacy close
//! tag 仍保留給 recent fills 與 exit-feature 分類。

/// V033 (2026-04-29) — strategy attribution cleanup (W1-T1 of PA design report
/// `2026-04-29--strategy_name_attribution_cleanup_design.md`).
///
/// Build the (strategy_name, exit_reason) pair for a close fill, splitting the
/// previously-overloaded strategy_name into:
///
/// 1. `strategy_name` — an enum-like aggregation key (5 entry strategies +
///    one special system path for cross-symbol HALT close):
///      - "ma_crossover" / "bb_reversion" / "bb_breakout" / "grid_trading" /
///        "funding_arb" — when `entry_strategy` matches one of the 5 known
///        entry-path strategies.
///      - "risk_close:halt_session" — special-case for HALT_SESSION (R-A5
///        in PA §5.4): `RiskAction::HaltSession` closes EVERY open position
///        irrespective of which strategy opened them, so the per-position
///        entry strategy is not the right aggregation key. Fallback prefix
///        `risk_close:halt_session` keeps healthcheck `[12]/[Xa]` LIKE
///        patterns intact and signals to GUI that this is a system close.
///      - For unknown `entry_strategy` (defensive fallback): pass through
///        verbatim so we never silently drop the attribution. Caller code
///        SHOULD only pass one of the 6 well-known values; passing anything
///        else is a regression and `passive_wait_healthcheck [38]` will
///        catch it via 24h cardinality drift detector (W1-T4).
///
/// 2. `exit_reason` — the free-text close trace previously dumped into
///    strategy_name (e.g. "TRAILING STOP: peak X% - current Y% = ...",
///    "phys_lock_gate4_giveback", "ma_reverse_cross"). Always
///    `Some(reason.to_string())` for close path; entry path SHOULD NOT call
///    this helper.
///
/// **Special case `unattributed:bybit_auto`**: this audit path does NOT go
/// through `build_close_tags`; `unattributed_emit::try_emit_unattributed_fill`
/// constructs the Fill row directly with `strategy_name="unattributed:bybit_auto"`
/// and `exit_reason=None`. See `event_consumer/unattributed_emit.rs:168`.
///
/// W1-T2 integration: close emitters call
/// `build_close_tags_from_legacy(close_tag, owner_strategy)` below. This lower
/// helper remains the strict constructor for already-normalized
/// `(entry_strategy, reason)` inputs.
///
/// V033（2026-04-29）— 策略歸因清理（PA 設計報告 W1-T1）。
/// 建構 close fill 的 (strategy_name, exit_reason) pair，將先前被當作 trace
/// 的 strategy_name 拆成兩個欄位：
///
/// 1. strategy_name — enum-like 聚合鍵（5 個入場策略 + 一個 HALT 系統路徑）。
///    halt_session 是 R-A5 特例：HaltSession 平所有倉，per-position 入場
///    策略不是正確的聚合鍵 → 用 "risk_close:halt_session" fallback prefix。
///    未知 entry_strategy 則 verbatim passthrough（防衛性，healthcheck [38]
///    cardinality drift detector 會在 24h 內 catch regression）。
///
/// 2. exit_reason — 自由文字退場 trace。close path 永遠 Some(...)；entry path
///    不應呼叫此 helper。
///
/// 特例：unattributed:bybit_auto 不走此 helper（見 unattributed_emit.rs:168）。
///
/// W1-T2 接入：close emitter 呼叫下方
/// `build_close_tags_from_legacy(close_tag, owner_strategy)`；本 helper 保持為
/// 已正規化 `(entry_strategy, reason)` input 的嚴格 constructor。
pub(crate) fn build_close_tags(entry_strategy: &str, reason: &str) -> (String, Option<String>) {
    // 5 known entry-path strategies (rust/openclaw_engine/src/strategies/{ma_crossover,
    // bb_reversion, bb_breakout, grid_trading, funding_arb}.rs::name()). Listed
    // explicitly rather than via .contains() so a typo at any caller site
    // surfaces here as the wrong attribution rather than silent passthrough.
    // 5 個已知入場策略（顯式列舉以防 caller typo 被靜默 passthrough）。
    const KNOWN_ENTRY_STRATEGIES: &[&str] = &[
        "ma_crossover",
        "bb_reversion",
        "bb_breakout",
        "grid_trading",
        "funding_arb",
    ];

    // R-A5 (PA §5.4): HALT_SESSION closes every open position regardless of
    // which strategy opened it; per-position entry attribution is not the
    // right aggregation key here. Use fallback prefix so healthcheck [12]/[Xa]
    // LIKE 'risk_close:%' patterns continue to match and GUI/operator can
    // distinguish a system-wide halt from a per-strategy exit.
    // R-A5：HALT_SESSION 平所有倉，per-position 入場策略不是聚合鍵；用
    // fallback prefix 讓 healthcheck LIKE 'risk_close:%' 仍命中並標明系統 close。
    if reason.starts_with("halt_session") || reason.starts_with("risk_close:halt_session") {
        return (
            "risk_close:halt_session".to_string(),
            Some(reason.to_string()),
        );
    }

    // Known 5 entry strategies → emit canonical lowercase enum value.
    // 已知 5 入場策略 → 輸出 canonical lowercase enum 值。
    if KNOWN_ENTRY_STRATEGIES.contains(&entry_strategy) {
        return (entry_strategy.to_string(), Some(reason.to_string()));
    }

    // Defensive fallback: unknown entry_strategy. Pass through verbatim so the
    // attribution is preserved (no silent drop), but healthcheck [38] cardinality
    // drift detector (W1-T4) will catch any new entry-strategy-name regression
    // within 24h.
    // 防衛性 fallback：未知 entry_strategy verbatim passthrough，healthcheck [38]
    // 24h cardinality drift 檢測會 catch regression。
    (entry_strategy.to_string(), Some(reason.to_string()))
}

/// Convert the pre-W1-T2 close tag shape into the V033 two-field DB contract.
///
/// Legacy close paths still call the common emitters with tags such as
/// `strategy_close:grid_close_long`, `risk_close:TRAILING STOP ...`, or
/// `risk_close:fast_track`. This helper strips the legacy envelope into
/// `exit_reason`, then uses the pre-close owner strategy when available to
/// produce the normalized `strategy_name`.
///
/// When no owner snapshot is available, strategy-driven reasons are inferred
/// from their stable reason prefix; unknown risk/manual paths preserve the
/// legacy tag as `strategy_name` while still writing `exit_reason`, so we never
/// silently lose attribution.
///
/// 將 W1-T2 前的 close tag 形狀轉成 V033 兩欄契約。舊路徑仍傳入
/// `strategy_close:*` / `risk_close:*`；本 helper 將 envelope 拆到
/// `exit_reason`，並優先用平倉前 position owner strategy 作正規化
/// `strategy_name`。缺 owner 時只對穩定策略退場 reason 做推斷；未知手動 /
/// 風控路徑保留舊 tag 作 attribution，同時仍寫 exit_reason。
pub(crate) fn build_close_tags_from_legacy(
    close_tag: &str,
    owner_strategy: Option<&str>,
) -> (String, Option<String>) {
    let reason = close_reason_from_legacy_tag(close_tag);
    let entry_strategy = owner_strategy
        .filter(|s| !s.trim().is_empty())
        .or_else(|| infer_entry_strategy_from_reason(reason))
        .unwrap_or(close_tag);
    build_close_tags(entry_strategy, reason)
}

fn close_reason_from_legacy_tag(close_tag: &str) -> &str {
    close_tag
        .strip_prefix("strategy_close:")
        .or_else(|| close_tag.strip_prefix("risk_close:"))
        .or_else(|| close_tag.strip_prefix("stop_trigger:"))
        .or_else(|| close_tag.strip_prefix("ipc_close:"))
        .unwrap_or(close_tag)
}

fn infer_entry_strategy_from_reason(reason: &str) -> Option<&'static str> {
    if reason.starts_with("grid_close_") {
        Some("grid_trading")
    } else if reason == "ma_reverse_cross" {
        Some("ma_crossover")
    } else if reason == "bb_mean_revert" {
        Some("bb_reversion")
    } else if matches!(reason, "trailing_stop" | "pctb_revert" | "bw_squeeze") {
        Some("bb_breakout")
    } else if reason.starts_with("funding_arb_exit") {
        Some("funding_arb")
    } else {
        None
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    // ─────────────────────────────────────────────────────────────────────
    // V033 (2026-04-29) — build_close_tags contract tests.
    // PA design report `2026-04-29--strategy_name_attribution_cleanup_design.md`
    // §4 W1-T1 step (d). Pin the 5-enum + halt_session + fallback rules so the
    // 16-emit-point W1-T2 wave can rely on this helper without surprises.
    // V033（2026-04-29）— build_close_tags 契約測試。
    // 固化 5 enum + halt_session + fallback 規則，讓 W1-T2 16 emit 點可信賴。
    // ─────────────────────────────────────────────────────────────────────

    #[test]
    fn test_build_close_tags_grid() {
        // grid_trading entry → enum-like strategy_name; reason verbatim into
        // exit_reason. Pin contract for both grid_close_short and grid_close_long.
        // grid_trading 入場 → enum-like strategy_name；reason verbatim 進
        // exit_reason。固化 grid_close_short / grid_close_long 兩種。
        let (sn, er) = build_close_tags("grid_trading", "grid_close_short");
        assert_eq!(sn, "grid_trading", "strategy_name must be canonical enum");
        assert_eq!(
            er.as_deref(),
            Some("grid_close_short"),
            "reason must thread verbatim into exit_reason"
        );

        let (sn2, er2) = build_close_tags("grid_trading", "grid_close_long");
        assert_eq!(sn2, "grid_trading");
        assert_eq!(er2.as_deref(), Some("grid_close_long"));
    }

    #[test]
    fn test_build_close_tags_ma() {
        // ma_crossover entry → "ma_reverse_cross" reason. Companion test to
        // grid case to confirm all 5 known entries route the same way.
        // ma_crossover 入場 → "ma_reverse_cross"；確認 5 已知入場路由一致。
        let (sn, er) = build_close_tags("ma_crossover", "ma_reverse_cross");
        assert_eq!(sn, "ma_crossover");
        assert_eq!(er.as_deref(), Some("ma_reverse_cross"));

        // Risk-driven exit dynamic format is the cardinality root cause being
        // cleaned up. Pin that complex format strings still thread cleanly into
        // exit_reason without escaping/truncation.
        // 風控驅動退場的動態格式正是 cardinality 爆炸的根源；固化複雜字串
        // 仍能正確 verbatim 進 exit_reason，無 escape / truncation。
        let dyn_reason =
            "TRAILING STOP: peak 8.46% - current 6.46% = 2.00% >= distance 2.00% (locked 6.46% >= floor 5.78%)";
        let (sn3, er3) = build_close_tags("ma_crossover", dyn_reason);
        assert_eq!(
            sn3, "ma_crossover",
            "dynamic reason must not pollute strategy_name"
        );
        assert_eq!(er3.as_deref(), Some(dyn_reason));
    }

    #[test]
    fn test_build_close_tags_unknown_strategy() {
        // Unknown entry_strategy → defensive fallback: pass through verbatim.
        // Healthcheck [38] cardinality drift (W1-T4) will catch any new entry
        // strategy name within 24h via DISTINCT count > 10/20 threshold.
        // 未知 entry_strategy → 防衛性 fallback verbatim passthrough。
        // healthcheck [38] 24h cardinality drift 會 catch 新策略名 regression。
        let (sn, er) = build_close_tags("custom_unknown_strat", "some_reason");
        assert_eq!(
            sn, "custom_unknown_strat",
            "unknown entry preserves attribution rather than silently dropping"
        );
        assert_eq!(
            er.as_deref(),
            Some("some_reason"),
            "reason must still thread to exit_reason on fallback path"
        );

        // Defensive: known-but-mistyped entry name (e.g. capitalisation) lands
        // in fallback path — caller is expected to pass canonical lowercase.
        // Healthcheck [38] catches this within 24h.
        // 防衛性：known-but-mistyped 入場名走 fallback；caller 應傳 canonical
        // lowercase；healthcheck [38] 24h 內 catch。
        let (sn2, _) = build_close_tags("Grid_Trading", "grid_close_long");
        assert_eq!(
            sn2, "Grid_Trading",
            "case-sensitive: capitalisation drift falls through fallback (caller bug)"
        );
    }

    #[test]
    fn test_build_close_tags_halt_session() {
        // R-A5 (PA §5.4): HaltSession closes every open position; per-position
        // entry attribution is not the right key. Special-case prefix
        // "risk_close:halt_session" is returned regardless of entry_strategy
        // (caller passes whatever was on the position; helper overrides for
        // halt path so aggregation lines up).
        // R-A5：HaltSession 平所有倉；per-position 入場非聚合鍵。
        // halt path 強制 prefix "risk_close:halt_session"，忽略 entry_strategy。
        let (sn, er) = build_close_tags("ma_crossover", "halt_session_drawdown_3pct");
        assert_eq!(
            sn, "risk_close:halt_session",
            "halt_session reason → fallback prefix regardless of entry"
        );
        assert_eq!(
            er.as_deref(),
            Some("halt_session_drawdown_3pct"),
            "full halt reason threads to exit_reason"
        );

        // Also accept "risk_close:halt_session_*" pre-prefixed reasons (some
        // caller paths may pass pre-wrapped form). Idempotent on prefix.
        // 也接受 "risk_close:halt_session_*" 已 wrap 的 reason — caller 可能
        // 預前綴傳入；對 prefix idempotent。
        let (sn2, er2) =
            build_close_tags("grid_trading", "risk_close:halt_session_consecutive_loss");
        assert_eq!(sn2, "risk_close:halt_session");
        assert_eq!(
            er2.as_deref(),
            Some("risk_close:halt_session_consecutive_loss")
        );

        // Boundary: bare "halt_session" without suffix.
        // 邊界：純 "halt_session" 無 suffix。
        let (sn3, er3) = build_close_tags("bb_breakout", "halt_session");
        assert_eq!(sn3, "risk_close:halt_session");
        assert_eq!(er3.as_deref(), Some("halt_session"));
    }

    #[test]
    fn test_build_close_tags_from_legacy_uses_owner_strategy() {
        let (sn, er) = build_close_tags_from_legacy(
            "risk_close:TRAILING STOP: peak 8.46% - current 6.46%",
            Some("grid_trading"),
        );
        assert_eq!(sn, "grid_trading");
        assert_eq!(
            er.as_deref(),
            Some("TRAILING STOP: peak 8.46% - current 6.46%"),
            "legacy risk_close envelope must move to exit_reason"
        );
    }

    #[test]
    fn test_build_close_tags_from_legacy_infers_strategy_reason() {
        let (sn, er) = build_close_tags_from_legacy("strategy_close:grid_close_long", None);
        assert_eq!(sn, "grid_trading");
        assert_eq!(er.as_deref(), Some("grid_close_long"));

        let (sn2, er2) = build_close_tags_from_legacy("strategy_close:ma_reverse_cross", None);
        assert_eq!(sn2, "ma_crossover");
        assert_eq!(er2.as_deref(), Some("ma_reverse_cross"));

        let (sn3, er3) = build_close_tags_from_legacy(
            "strategy_close:funding_arb_exit: rate=-0.001 basis=0.500%",
            None,
        );
        assert_eq!(sn3, "funding_arb");
        assert_eq!(
            er3.as_deref(),
            Some("funding_arb_exit: rate=-0.001 basis=0.500%")
        );
    }

    #[test]
    fn test_build_close_tags_from_legacy_halt_and_unknown() {
        let (sn, er) = build_close_tags_from_legacy("risk_close:halt_session", None);
        assert_eq!(sn, "risk_close:halt_session");
        assert_eq!(er.as_deref(), Some("halt_session"));

        let (sn2, er2) = build_close_tags_from_legacy("risk_close:ipc_close_symbol", None);
        assert_eq!(
            sn2, "risk_close:ipc_close_symbol",
            "unknown no-owner risk paths preserve legacy attribution"
        );
        assert_eq!(er2.as_deref(), Some("ipc_close_symbol"));
    }
}
