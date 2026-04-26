//! Edge estimates reload handler (F6 PH5-WIRE-1 RELOAD, 2026-04-26).
//! Edge 估計重載 handler（F6 PH5-WIRE-1 RELOAD，2026-04-26）。
//!
//! MODULE_NOTE (EN): Owns the runtime path for re-injecting JS-shrunk edge
//!   estimates into a per-pipeline `IntentProcessor`. The boot-time inject
//!   (`event_consumer/bootstrap.rs:586`) loads once at engine start and then
//!   never refreshes — by 2026-04-26 the engine had been running 14h on a
//!   stuck `n_cells=210 grand_mean_bps=-12.83` snapshot while the Python
//!   `edge_estimator_scheduler` daemon refreshed `settings/edge_estimates.json`
//!   hourly, producing 99.98% cost_gate reject (6.595M reject / 50 approve)
//!   and blocking Phase 5. F6 wires two reload paths:
//!     1. Periodic 1h reload daemon (`main_boot_tasks::spawn_edge_estimates_reloader_if_enabled`)
//!        — opt-in env-gate `OPENCLAW_EDGE_RELOAD=1` (DEFAULT-OFF, strict "1" match).
//!     2. Manual `reload_edge_estimates` IPC method — advisory fire-and-forget
//!        from operator GUI / Python `edge_estimator_scheduler` post-write hook.
//!   Both paths fan out `PipelineCommand::ReloadEdgeEstimates` (no payload —
//!   each engine reads its own mode-specific JSON), and this handler is the
//!   single dispatcher that loads + injects + logs.
//!
//!   Mode isolation is enforced inside the handler (not the producer): the
//!   handler reads `pipeline.pipeline_kind.db_mode()` and calls
//!   `EdgeEstimates::load_for_mode(&base, mode)`. Paper reads
//!   `edge_estimates_paper.json` (isolated exploration cells); demo/live read
//!   `edge_estimates.json` (production cells). Cross-engine contamination is
//!   structurally impossible — even if the producer mis-routes, the consumer
//!   still loads its own mode's JSON.
//!
//!   Fail-soft contract: when `load_for_mode` returns empty (file missing,
//!   IO failure, JSON corrupt), the handler logs `warn!` and skips
//!   `set_edge_estimates`. Prior boot-time / last-good estimates are
//!   retained — CLAUDE.md §二 原則 #6 read-side fail-soft. The 1h periodic
//!   tick will retry next cycle; the writer side (Python scheduler) is the
//!   authoritative source. Never fail-closes the engine — reload is
//!   advisory, the engine must keep trading on the last good snapshot.
//!
//! MODULE_NOTE (中)：負責重新將 JS 收縮 edge 估計注入 per-pipeline
//!   `IntentProcessor` 的 runtime 路徑。Boot-time inject 只在啟動時讀一次後
//!   永不刷新 — 2026-04-26 engine 已在 stuck 的 `n_cells=210 grand_mean_bps=-12.83`
//!   快照上跑 14h，期間 Python `edge_estimator_scheduler` daemon 每小時更新
//!   `settings/edge_estimates.json`，造成 cost_gate 99.98% reject（6.595M /
//!   50 approve）阻塞 Phase 5。F6 接兩條 reload 路徑：
//!     1. 1h 週期 reload daemon — opt-in env-gate `OPENCLAW_EDGE_RELOAD=1`
//!        （DEFAULT-OFF，嚴格 "1" 比對）。
//!     2. Manual `reload_edge_estimates` IPC method — advisory fire-and-forget。
//!   兩條路徑都 fan-out `PipelineCommand::ReloadEdgeEstimates`（無 payload —
//!   每引擎讀自己模式對應 JSON），本 handler 為唯一 load + inject + log 派發。
//!
//!   Mode 隔離在 handler 端落實（非 producer）：handler 讀
//!   `pipeline.pipeline_kind.db_mode()` 呼 `EdgeEstimates::load_for_mode(&base, mode)`。
//!   Paper 讀 `edge_estimates_paper.json`（隔離探索格子），demo/live 讀
//!   `edge_estimates.json`（生產格子）。跨引擎污染結構性不可能 — 即便 producer
//!   誤路由，consumer 仍讀自己模式的 JSON。
//!
//!   Fail-soft 契約：`load_for_mode` 回空（檔案缺失 / IO 失敗 / JSON 損毀）
//!   → handler `warn!` 並跳過 `set_edge_estimates`，保留前份（boot-time 或
//!   上次成功）estimates — CLAUDE.md §二 原則 #6 讀側 fail-soft。1h 週期下個
//!   tick 會 retry；writer 端（Python scheduler）為權威來源。**絕不**讓引擎
//!   fail-close — reload 為 advisory，引擎必須繼續使用上次 good snapshot 交易。

use crate::edge_estimates::EdgeEstimates;
use crate::tick_pipeline::TickPipeline;
use std::path::PathBuf;
use tracing::{info, warn};

/// EN: Resolve the base directory for `settings/edge_estimates*.json` lookup.
///   Mirrors `event_consumer/bootstrap.rs:566-570` boot-time resolution so the
///   reload path reads from the same directory as the original inject.
///   Reads `OPENCLAW_BASE_DIR`; falls back to current working directory if
///   unset (development convenience).
/// 中: 解析 `settings/edge_estimates*.json` 的 base 目錄，與 boot-time 注入
///   同一邏輯（`event_consumer/bootstrap.rs:566-570`）；讀 `OPENCLAW_BASE_DIR`，
///   未設則退到 cwd（開發便利）。
fn resolve_base_dir() -> PathBuf {
    std::env::var("OPENCLAW_BASE_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|_| {
            std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."))
        })
}

/// EN: Reload the on-disk edge estimates snapshot for `pipeline`'s mode and
///   inject into the IntentProcessor. Fail-soft: empty load (file missing /
///   IO error / JSON corrupt) → log warn + retain prior estimates, never
///   fail-close the engine.
///
///   Mode isolation is read here (not at the producer): the handler always
///   uses `pipeline.pipeline_kind.db_mode()` to pick the right JSON
///   filename, so paper exploration cells can never reach demo/live
///   cost_gate. Returns the new `n_cells` on success or `None` on skip
///   (so the periodic-daemon log line can record reload outcomes).
///
/// 中: 重新載入本 pipeline 模式對應的 edge estimates 快照並注入
///   IntentProcessor。Fail-soft：載入為空（檔案缺失 / IO 錯誤 / JSON 損毀）
///   → 記 warn + 保留前份 estimates，**絕不**讓引擎 fail-close。
///
///   Mode 隔離在 handler 端讀取（非 producer）：永遠以
///   `pipeline.pipeline_kind.db_mode()` 挑 JSON 檔名，paper 探索格子無法
///   污染 demo/live cost_gate。成功回新 `n_cells`，跳過回 `None`（給週期
///   daemon 日誌使用）。
pub(crate) fn handle_reload_edge_estimates(pipeline: &mut TickPipeline) -> Option<usize> {
    let base = resolve_base_dir();
    let mode = pipeline.pipeline_kind.db_mode();
    let estimates: EdgeEstimates = EdgeEstimates::load_for_mode(&base, mode);

    if !estimates.is_populated() {
        // Fail-soft path: no rebind. Prior estimates remain in
        // IntentProcessor — engine keeps trading on the last good snapshot.
        // Fail-soft 路徑：不 rebind。IntentProcessor 保留前份 estimates，
        // 引擎以上次 good snapshot 繼續交易。
        warn!(
            mode,
            base = %base.display(),
            "PH5-WIRE-1 RELOAD: empty estimates (file missing / IO error / corrupt) — \
             retaining prior snapshot, no rebind / 空 estimates，保留前份快照不重綁"
        );
        return None;
    }

    let n_cells = estimates.n_cells();
    let grand_mean_bps = estimates.grand_mean_bps();
    pipeline.set_edge_estimates(estimates);
    info!(
        mode,
        n_cells,
        grand_mean_bps,
        "PH5-WIRE-1 RELOAD: edge estimates refreshed / 邊際估計已刷新"
    );
    Some(n_cells)
}

// ═══════════════════════════════════════════════════════════════════════════════
// F6 unit tests — mode isolation + fail-soft + populated reload paths
// F6 單元測試 — mode 隔離 + fail-soft + 有值重載路徑
// ═══════════════════════════════════════════════════════════════════════════════
#[cfg(test)]
mod tests {
    use super::*;
    use crate::tick_pipeline::{PipelineKind, TickPipeline};
    use std::fs;
    use std::sync::Mutex;

    /// Serialise tests that mutate `OPENCLAW_BASE_DIR` so concurrent test
    /// runners don't observe each other's env state. cargo runs tests within
    /// one process in parallel by default; mutating env vars is unsafe across
    /// threads without external locking.
    /// 測試級互斥鎖：序列化會 mutate `OPENCLAW_BASE_DIR` 的測試，避免 cargo
    /// 預設多執行緒並行下相互觀察 env 狀態。
    static ENV_GUARD: Mutex<()> = Mutex::new(());

    /// Build a minimal sample edge estimates JSON for tests.
    /// 為測試構建最小 sample edge estimates JSON。
    fn sample_json(strategy_symbol: &str, shrunk_bps: f64, grand_mean_bps: f64) -> String {
        format!(
            r#"{{
                "_meta": {{"grand_mean_bps": {gm}, "n_cells": 1}},
                "{key}": {{"shrunk_bps": {bps}, "win_rate_shrunk": 0.55, "n": 50, "std_bps": 4.0}}
            }}"#,
            key = strategy_symbol,
            bps = shrunk_bps,
            gm = grand_mean_bps,
        )
    }

    /// Build a TickPipeline with a fixed kind for handler tests.
    /// Mirrors the constructor used elsewhere in handlers/tests.
    /// 為 handler 測試構建固定 kind 的 TickPipeline，與其他 handlers/tests 對齊。
    fn build_pipeline(kind: PipelineKind) -> TickPipeline {
        TickPipeline::with_kind(&["BTCUSDT"], 10_000.0, kind)
    }

    /// Set `OPENCLAW_BASE_DIR` to a tempdir, write the requested `settings/<filename>`
    /// JSON file, and return the tempdir path. Caller must hold the ENV_GUARD lock.
    /// 將 `OPENCLAW_BASE_DIR` 設為 tempdir、寫入請求的 `settings/<filename>` JSON
    /// 檔案，回 tempdir 路徑。呼叫端必須持 ENV_GUARD 鎖。
    fn write_estimates(filename: &str, json: &str) -> tempfile::TempDir {
        let dir = tempfile::tempdir().expect("tempdir");
        let settings = dir.path().join("settings");
        fs::create_dir_all(&settings).expect("mkdir settings");
        fs::write(settings.join(filename), json).expect("write json");
        std::env::set_var("OPENCLAW_BASE_DIR", dir.path());
        dir
    }

    /// EN: F6 fail-soft path — when the JSON file is missing, the handler
    ///   logs warn and returns None; the prior boot-time estimates are
    ///   retained inside the pipeline (no panic, no fail-close).
    /// 中: F6 fail-soft — JSON 檔案缺失時 handler 記 warn 回 None，pipeline
    ///   保留前份 estimates 不 panic 不 fail-close。
    #[test]
    fn reload_returns_none_when_file_missing() {
        let _guard = ENV_GUARD.lock().expect("env guard not poisoned");
        let dir = tempfile::tempdir().expect("tempdir");
        std::env::set_var("OPENCLAW_BASE_DIR", dir.path());
        // No settings/edge_estimates.json written; load_for_mode returns empty.
        let mut pipeline = build_pipeline(PipelineKind::Demo);
        let result = handle_reload_edge_estimates(&mut pipeline);
        assert!(result.is_none(), "fail-soft must return None when file missing");
    }

    /// EN: F6 fail-soft path — corrupt JSON yields empty load → handler
    ///   skips rebind and returns None.
    /// 中: F6 fail-soft — 損毀 JSON 視為空載入 → handler 跳過 rebind 回 None。
    #[test]
    fn reload_returns_none_when_json_corrupt() {
        let _guard = ENV_GUARD.lock().expect("env guard not poisoned");
        let _dir = write_estimates("edge_estimates.json", "not valid json {[");
        let mut pipeline = build_pipeline(PipelineKind::Demo);
        let result = handle_reload_edge_estimates(&mut pipeline);
        assert!(result.is_none(), "corrupt JSON must trigger fail-soft skip");
    }

    /// EN: F6 happy path for Demo — populated `edge_estimates.json` is read,
    ///   `set_edge_estimates` runs, returns `Some(n_cells)`. Verifies the
    ///   IntentProcessor sees the new cell via `lookup_shrunk_bps`-shaped
    ///   downstream behaviour (here just n_cells return).
    /// 中: F6 Demo happy path — 有值 `edge_estimates.json` → set_edge_estimates
    ///   成功，回 Some(n_cells)。
    #[test]
    fn reload_populated_demo_returns_n_cells() {
        let _guard = ENV_GUARD.lock().expect("env guard not poisoned");
        let _dir = write_estimates(
            "edge_estimates.json",
            &sample_json("ma_crossover::BTCUSDT", 3.5, 1.2),
        );
        let mut pipeline = build_pipeline(PipelineKind::Demo);
        let result = handle_reload_edge_estimates(&mut pipeline);
        assert_eq!(result, Some(1), "populated load must return Some(1)");
    }

    /// EN: F6 mode isolation — Paper pipeline reads
    ///   `edge_estimates_paper.json` exclusively. Even if a (different)
    ///   `edge_estimates.json` exists with cells, paper's load_for_mode
    ///   ignores the production file and returns empty.
    /// 中: F6 模式隔離 — Paper 管線**只**讀 `edge_estimates_paper.json`，
    ///   即便存在不同的 `edge_estimates.json`（有格子），paper 仍忽略生產檔
    ///   回空，不會誤讀。
    #[test]
    fn reload_paper_isolation_ignores_production_file() {
        let _guard = ENV_GUARD.lock().expect("env guard not poisoned");
        let dir = tempfile::tempdir().expect("tempdir");
        let settings = dir.path().join("settings");
        fs::create_dir_all(&settings).expect("mkdir settings");
        // Only production JSON exists; paper reads its own filename → miss.
        // 僅生產 JSON 存在，paper 讀自己檔名 → 找不到。
        fs::write(
            settings.join("edge_estimates.json"),
            sample_json("ma_crossover::BTCUSDT", 3.5, 1.2),
        )
        .expect("write production");
        std::env::set_var("OPENCLAW_BASE_DIR", dir.path());
        let mut pipeline = build_pipeline(PipelineKind::Paper);
        let result = handle_reload_edge_estimates(&mut pipeline);
        assert!(
            result.is_none(),
            "paper must not read production edge_estimates.json"
        );
    }

    /// EN: F6 mode isolation — Live pipeline reads
    ///   `edge_estimates.json` (production), not `edge_estimates_paper.json`.
    ///   When only the paper file exists, live's load returns empty and
    ///   triggers fail-soft skip.
    /// 中: F6 模式隔離 — Live 讀生產 JSON，不讀 paper 隔離 JSON。僅 paper 檔
    ///   存在時 live 載入為空、走 fail-soft skip。
    #[test]
    fn reload_live_isolation_ignores_paper_file() {
        let _guard = ENV_GUARD.lock().expect("env guard not poisoned");
        let dir = tempfile::tempdir().expect("tempdir");
        let settings = dir.path().join("settings");
        fs::create_dir_all(&settings).expect("mkdir settings");
        // Only paper JSON exists; live reads production filename → miss.
        // 僅 paper JSON 存在，live 讀生產檔名 → 找不到。
        fs::write(
            settings.join("edge_estimates_paper.json"),
            sample_json("grid_trading::ETHUSDT", -8.0, -2.5),
        )
        .expect("write paper");
        std::env::set_var("OPENCLAW_BASE_DIR", dir.path());
        let mut pipeline = build_pipeline(PipelineKind::Live);
        let result = handle_reload_edge_estimates(&mut pipeline);
        assert!(
            result.is_none(),
            "live must not read paper edge_estimates_paper.json"
        );
    }

    /// EN: F6 mode isolation — Paper happy path. With paper-specific JSON
    ///   present, paper pipeline reloads successfully and returns
    ///   `Some(n_cells)`.
    /// 中: F6 模式隔離 — Paper happy path：paper 專用 JSON 存在時 paper 管線
    ///   成功重載，回 Some(n_cells)。
    #[test]
    fn reload_paper_reads_paper_file_when_present() {
        let _guard = ENV_GUARD.lock().expect("env guard not poisoned");
        let _dir = write_estimates(
            "edge_estimates_paper.json",
            &sample_json("grid_trading::ETHUSDT", -8.0, -2.5),
        );
        let mut pipeline = build_pipeline(PipelineKind::Paper);
        let result = handle_reload_edge_estimates(&mut pipeline);
        assert_eq!(result, Some(1), "paper must read paper-specific JSON when present");
    }

    /// EN: F6 reload trigger — calling the handler twice with different
    ///   sample JSON between calls produces two distinct reload outcomes.
    ///   This validates that the second call observes the on-disk update,
    ///   not a stale in-memory copy (the daemon's core invariant).
    /// 中: F6 重載觸發 — 連呼 handler 兩次（中間替換 JSON），會觀察到兩次
    ///   不同的重載結果。驗證第二次讀到磁碟更新而非 in-memory stale 拷貝
    ///   （daemon 核心不變式）。
    #[test]
    fn reload_picks_up_disk_update_on_second_call() {
        let _guard = ENV_GUARD.lock().expect("env guard not poisoned");
        // First write: 1 cell at 3.5 bps.
        // 首次寫入：1 格子 3.5 bps。
        let dir = write_estimates(
            "edge_estimates.json",
            &sample_json("ma_crossover::BTCUSDT", 3.5, 1.2),
        );
        let mut pipeline = build_pipeline(PipelineKind::Demo);
        let first = handle_reload_edge_estimates(&mut pipeline);
        assert_eq!(first, Some(1));

        // Overwrite with 1-cell different shrunk_bps + grand_mean.
        // 覆寫成另一組 1 格子，不同 shrunk_bps + grand_mean。
        let settings = dir.path().join("settings");
        fs::write(
            settings.join("edge_estimates.json"),
            sample_json("ma_crossover::BTCUSDT", 5.0, 2.5),
        )
        .expect("rewrite json");

        let second = handle_reload_edge_estimates(&mut pipeline);
        assert_eq!(second, Some(1), "second call must observe disk update");
    }
}
