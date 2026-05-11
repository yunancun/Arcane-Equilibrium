// V083-FIX-1（2026-05-11）：close 路徑 entry_context_id resolver helper 單元測試。
// 驗證 helper 的 4 條 invariant：
//   1. paper_state 有真 id → 回真 id
//   2. paper_state 缺 → 回 synthetic
//   3. paper_state 留空字串 → 回 synthetic
//   4. synthetic id pattern 嚴格 well-formed（cron backfill 識別點）
//
// 設計動機詳 PA design report：
// `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--p1_v083_ipc_close_fix_design.md`

use super::*;

/// helper 在 paper_state 已 set entry_context_id 時應回真 id 字串，
/// 不退到 synthetic fallback。
#[test]
fn test_resolve_real_id_when_present() {
    let mut pipeline = TickPipeline::with_balance(&["BTCUSDT"], 1_000.0);
    // 必先建立倉位，set_entry_context_id 才不 no-op（accessor.rs:202-209
    // 對「無倉位」是 silent skip，這也是真 id 寫不進去的歷史地雷）。
    pipeline
        .paper_state
        .apply_fill("BTCUSDT", true, 0.1, 50_000.0, 0.0, 1_000, "ma_crossover");
    pipeline
        .paper_state
        .set_entry_context_id("BTCUSDT", "ctx-real-123");

    let resolved = pipeline.resolve_close_entry_context_id("BTCUSDT", 1_700_000_000_000);
    assert_eq!(resolved, "ctx-real-123");
}

/// helper 在 paper_state 完全沒倉位（典型 engine restart 後 in-memory map
/// 全清）時應回 well-formed synthetic id，避免下游 V083 NOT NULL CHECK
/// reject + batch buffer 卡死。
#[test]
fn test_resolve_synthetic_when_missing() {
    let pipeline = TickPipeline::with_balance(&["BTCUSDT"], 1_000.0);
    // 沒 set entry_context_id，paper_state.get_entry_context_id → None
    let resolved = pipeline.resolve_close_entry_context_id("BTCUSDT", 1_700_000_000_000);
    assert_eq!(resolved, "orphan_recovery_ctx:BTCUSDT:1700000000000");
}

/// helper 在 paper_state 有倉位但 entry_context_id 為空字串（orphan-adopted
/// position 的初始狀態，owner_attribution.rs:213 `String::new()`）時應回
/// synthetic，與「完全無倉位」case 行為一致 — accessor.rs:216-221 用
/// `.filter(|p| !p.entry_context_id.is_empty())` 把空字串視為 None。
#[test]
fn test_resolve_synthetic_when_empty_string() {
    let mut pipeline = TickPipeline::with_balance(&["BTCUSDT"], 1_000.0);
    // 建倉但不 set entry_context_id（position.entry_context_id 預設空）。
    pipeline
        .paper_state
        .apply_fill("BTCUSDT", true, 0.1, 50_000.0, 0.0, 1_000, "ma_crossover");
    // accessor.rs:202-205 對 empty string 是 no-op；無論 set 或不 set，
    // get_entry_context_id 都應回 None → helper 回 synthetic。
    pipeline.paper_state.set_entry_context_id("BTCUSDT", "");

    let resolved = pipeline.resolve_close_entry_context_id("BTCUSDT", 1_700_000_000_000);
    assert_eq!(resolved, "orphan_recovery_ctx:BTCUSDT:1700000000000");
}

/// Synthetic id pattern 必須嚴格 `orphan_recovery_ctx:{symbol}:{ts_ms}` —
/// P2 cron backfill (`edge_label_backfill.py`) 將以此 prefix 為識別點，
/// 用 (symbol, ts_ms) 反查 entry fill → UPDATE 真 entry's context_id。
/// 任何 prefix 改變都會破第三波 P2 backfill 鏈，E2 review 必查此 invariant。
#[test]
fn test_synthetic_pattern_well_formed() {
    let pipeline = TickPipeline::with_balance(&["ETHUSDT"], 1_000.0);
    let resolved = pipeline.resolve_close_entry_context_id("ETHUSDT", 1_700_000_099_999);

    // Prefix invariant
    assert!(
        resolved.starts_with("orphan_recovery_ctx:"),
        "synthetic id must start with cron-backfill prefix: {resolved}",
    );

    // 三段結構：prefix : symbol : ts_ms
    let parts: Vec<&str> = resolved.split(':').collect();
    assert_eq!(parts.len(), 3, "synthetic id must have exactly 3 colon-separated parts: {resolved}");
    assert_eq!(parts[0], "orphan_recovery_ctx");
    assert_eq!(parts[1], "ETHUSDT");
    // ts_ms 必為可 parse 的 u64（cron backfill SQL 會 cast）
    assert_eq!(
        parts[2].parse::<u64>().expect("ts_ms must be parseable u64"),
        1_700_000_099_999_u64,
    );
}
