//! Miscellaneous IPC handlers: engine state snapshot, Phase 4 status card, and
//! scanner observability. These handlers do not send commands to the engine's
//! event-consumer task; they simply read locally-available snapshots or shared
//! registries.
//!
//! MODULE_NOTE (EN): Split out of `handlers.rs` in E5-P1-3 to keep per-domain
//!   files under the §九 800-line warning line. Behaviour is preserved 1:1;
//!   only the hosting module changed. All fn signatures / visibilities match
//!   the pre-split originals so `use handlers::*;` in `mod.rs` keeps working.
//! MODULE_NOTE (中)：E5-P1-3 將 `handlers.rs` 按領域拆分後的「雜項」桶，
//!   覆蓋引擎狀態、Phase 4 狀態卡、與掃描器可觀測性。函數簽名與可見性與
//!   拆分前完全一致，保證 `mod.rs` 的 `use handlers::*;` 不需改動。

use super::super::*;

/// Get current engine state summary.
/// Reads system_mode from pipeline snapshot (set by Python GUI sync).
/// 獲取當前引擎狀態摘要。
/// 從 pipeline 快照讀取 system_mode（由 Python GUI 同步設置）。
pub(in crate::ipc_server) fn handle_get_state(
    id: serde_json::Value,
    config: &Arc<ConfigManager>,
    data_dir: &Arc<std::path::PathBuf>,
) -> JsonRpcResponse {
    let cfg = config.get();
    // ARCH-RC1 1C-1: risk display fields now sourced from RiskConfig::default()
    // placeholder; 1C-2 will replace with live ConfigStore<RiskConfig> snapshot.
    // ARCH-RC1 1C-1：風控展示欄位暫從 RiskConfig::default() 讀；1C-2 改真快照。
    let risk = crate::config::RiskConfig::default();
    // Read system_mode + trading_mode from pipeline snapshot (single read).
    // 從 pipeline 快照一次讀取 system_mode + trading_mode。
    let (system_mode, trading_mode) = {
        let path = data_dir.join("pipeline_snapshot.json");
        let parsed = std::fs::read_to_string(&path)
            .ok()
            .and_then(|c| serde_json::from_str::<serde_json::Value>(&c).ok());
        let sm = parsed
            .as_ref()
            .and_then(|v| {
                v.get("system_mode")
                    .and_then(|s| s.as_str().map(String::from))
            })
            .filter(|s| !s.is_empty())
            .unwrap_or_else(|| "live_reserved".to_string());
        let tm = parsed
            .as_ref()
            .and_then(|v| {
                v.get("trading_mode")
                    .and_then(|t| t.as_str().map(String::from))
            })
            .unwrap_or_else(|| "paper".to_string());
        (sm, tm)
    };
    let state = serde_json::json!({
        "status": "running",
        "system_mode": system_mode,
        "trading_mode": trading_mode,
        "max_open_positions": risk.limits.open_positions_max,
        "max_total_exposure_pct": risk.limits.total_exposure_max_pct,
        "ws_url": cfg.ws_url,
        "config_path": config.file_path().display().to_string(),
    });
    JsonRpcResponse::success(id, state)
}

/// Phase 4 (4-00): Return dashboard skeleton status aggregation.
/// Phase 4 (4-00): 返回儀表板骨架的狀態聚合。
///
/// Each Phase 4 module (Teacher / LinUCB / News / DL-3) reports a traffic-light
/// state. At skeleton stage all modules report "grey" (not started). Subsequent
/// sub-tasks (4-01 ... 4-21) will replace the stub with real status sources.
///
/// 各 Phase 4 模組（Teacher / LinUCB / News / DL-3）回報一個紅黃綠燈狀態。
/// 骨架階段全部回報 "grey"（未啟動）。後續子任務（4-01 ... 4-21）會將 stub
/// 替換為真實狀態源。
///
/// Schema:
///   {
///     "teacher": "grey" | "green" | "yellow" | "red",
///     "linucb":  "grey" | ...,
///     "news":    "grey" | ...,
///     "dl3":     "grey" | ...,
///     "last_update_ms": <unix-millis>
///   }
pub(in crate::ipc_server) fn handle_get_phase4_status(id: serde_json::Value) -> JsonRpcResponse {
    let now_ms = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_millis() as i64)
        .unwrap_or(0);
    let payload = serde_json::json!({
        "teacher": "grey",
        "linucb":  "grey",
        "news":    "grey",
        "dl3":     "grey",
        "last_update_ms": now_ms,
    });
    JsonRpcResponse::success(id, payload)
}

// ---------------------------------------------------------------------------
// Scanner observability handlers (IPC-SCAN-1) / 掃描器可觀測性處理器
// ---------------------------------------------------------------------------

/// IPC-SCAN-1a: Return the current active symbol universe.
/// Fail-soft: returns {"status":"uninitialized"} if scanner not wired.
/// IPC-SCAN-1a：返回當前活躍交易對 universe。
/// Fail-soft：掃描器未接線時返回 {"status":"uninitialized"}。
pub(in crate::ipc_server) fn handle_get_active_symbols(
    id: serde_json::Value,
    registry: &Option<Arc<crate::scanner::registry::SymbolRegistry>>,
) -> JsonRpcResponse {
    let Some(reg) = registry else {
        return JsonRpcResponse::success(
            id,
            serde_json::json!({"status": "uninitialized", "symbols": [], "count": 0}),
        );
    };
    let symbols = reg.snapshot();
    let pinned: Vec<&String> = symbols.iter().filter(|s| reg.is_pinned(s)).collect();
    let dynamic: Vec<&String> = symbols.iter().filter(|s| !reg.is_pinned(s)).collect();
    JsonRpcResponse::success(
        id,
        serde_json::json!({
            "status": "ok",
            "symbols": symbols,
            "count": symbols.len(),
            "pinned": pinned,
            "dynamic": dynamic,
        }),
    )
}

/// IPC-SCAN-1b: Return full scanner status — active universe + last scan summary.
/// Fail-soft: returns {"status":"uninitialized"} if scanner not wired.
/// IPC-SCAN-1b：返回完整掃描器狀態 — 活躍 universe + 最後掃描摘要。
/// Fail-soft：掃描器未接線時返回 {"status": "uninitialized"}。
pub(in crate::ipc_server) fn handle_get_scanner_status(
    id: serde_json::Value,
    registry: &Option<Arc<crate::scanner::registry::SymbolRegistry>>,
) -> JsonRpcResponse {
    let Some(reg) = registry else {
        return JsonRpcResponse::success(id, serde_json::json!({"status": "uninitialized"}));
    };
    let symbols = reg.snapshot();
    let pinned: Vec<&String> = symbols.iter().filter(|s| reg.is_pinned(s)).collect();
    let dynamic: Vec<&String> = symbols.iter().filter(|s| !reg.is_pinned(s)).collect();

    let last_scan_json = match reg.last_scan() {
        None => serde_json::json!(null),
        Some(scan) => {
            // Top 10 candidates with key fields for GUI display. `scan.candidates`
            // is active-universe context, so rank it here for presentation.
            // 前 10 候選供 GUI 顯示。`scan.candidates` 是 active-universe context，
            // 因此在展示層重新按分數排序。
            let mut ranked_candidates = scan.candidates.clone();
            ranked_candidates.sort_by(|a, b| {
                b.final_score
                    .partial_cmp(&a.final_score)
                    .unwrap_or(std::cmp::Ordering::Equal)
            });
            let top_candidates: Vec<serde_json::Value> = ranked_candidates
                .iter()
                .take(10)
                .map(|c| {
                    serde_json::json!({
                        "symbol": c.symbol,
                        "final_score": (c.final_score * 10.0).round() / 10.0,
                        "best_strategy": format!("{:?}", c.best_strategy),
                        "market_regime": c.market_regime,
                        "trend_phase": c.trend_phase,
                        "trend_score": c.trend_score,
                        "range_score": c.range_score,
                        "shock_score": c.shock_score,
                        "crowding_score": c.crowding_score,
                        "reversal_risk_score": c.reversal_risk_score,
                        "f_ma": c.f_ma,
                        "f_grid": c.f_grid,
                        "f_bbrv": c.f_bbrv,
                        "f_bkout": c.f_bkout,
                        "f_funding_arb": c.f_funding_arb,
                        "sector": c.sector,
                        "edge_bonus": c.edge_bonus,
                        "edge_n": c.edge_n,
                    })
                })
                .collect();
            serde_json::json!({
                "scan_ts_ms": scan.scan_ts_ms,
                "duration_ms": scan.scan_duration_ms,
                "added": scan.added,
                "removed": scan.removed,
                "rejected_count": scan.rejected_count,
                "top_candidates": top_candidates,
            })
        }
    };

    JsonRpcResponse::success(
        id,
        serde_json::json!({
            "status": "ok",
            "active_symbols": symbols,
            "active_count": symbols.len(),
            "pinned": pinned,
            "dynamic": dynamic,
            "last_scan": last_scan_json,
        }),
    )
}

// ---------------------------------------------------------------------------
// G3-11 STRATEGIST-CYCLE-OBSERVABILITY-1 / 策略師排程器 cycle 計數器 IPC
// ---------------------------------------------------------------------------

/// G3-11 (2026-04-25, MVP slice): return the StrategistScheduler cycle
/// metrics snapshot — apply count, per-reason reject tally, last cycle ts,
/// last apply ts. Replaces the GUI footer's engine.log tail-parse fallback
/// with a structured pull. DB sink (`learning.strategist_cycle_events`) is
/// deliberately deferred — see TODO §G3-11 downgrade rationale.
///
/// Fail-soft: returns `{"status":"scheduler_unavailable"}` when the
/// scheduler isn't bound (Demo engine unbound / fresh boot path / unit
/// tests not wiring counters).
///
/// G3-11：返回 scheduler cycle metrics 快照 — apply count + per-reason
/// reject tally + last_ts。取代 GUI footer engine.log tail-parse fallback。
/// Fail-soft：scheduler 未綁返回 status=scheduler_unavailable。
pub(in crate::ipc_server) fn handle_get_strategist_cycle_metrics(
    id: serde_json::Value,
    counters: &Option<Arc<crate::strategist_scheduler::CycleCounters>>,
) -> JsonRpcResponse {
    let Some(c) = counters else {
        return JsonRpcResponse::success(
            id,
            serde_json::json!({
                "status": "scheduler_unavailable",
                "apply_count": 0,
                "cycle_count": 0,
                "last_cycle_ts_ms": 0,
                "last_apply_ts_ms": 0,
                "reject_by_reason": {},
            }),
        );
    };
    let snap = c.snapshot();
    JsonRpcResponse::success(
        id,
        serde_json::json!({
            "status": "ok",
            "apply_count": snap.apply_count,
            "cycle_count": snap.cycle_count,
            "last_cycle_ts_ms": snap.last_cycle_ts_ms,
            "last_apply_ts_ms": snap.last_apply_ts_ms,
            "reject_by_reason": snap.reject_by_reason,
        }),
    )
}
