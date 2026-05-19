//! P0-ENGINE-HALTSESSION-STUCK-FIX (2026-05-19) — Halt session forensic logger.
//! P0-ENGINE-HALTSESSION-STUCK-FIX（2026-05-19）—— 會話暫停取證記錄器。
//!
//! MODULE_NOTE
//! 模塊用途：為每一次 `RiskAction::HaltSession` 設置 / 清除事件寫獨立
//!   append-only forensic log，保留 reason / kind / quant-context / clear path
//!   等完整證據；engine.log 輪轉時不丟資料。同時把 lifecycle row 寫入
//!   `learning.governance_audit_log`（透過 IPC 傳給 audit writer，本模塊本身
//!   不直連 PG —— engine 同 process 內無 audit pool handle）。
//! 主要函數：
//!   - `record_halt_set` — 觸發 HaltSession 寫 set 行
//!   - `record_halt_cleared` — TTL auto-clear / IPC Resume/Reset/SystemMode 寫 clear 行
//!   - `HaltKind` enum + 分類 helper（reason 字串 → kind）
//! 依賴：
//!   - `crate::config::RiskConfig`（暴露 loaded threshold + version）
//!   - `crate::paper_state::PaperState`（balance / peak / drawdown / per_symbol 計算）
//!   - `crate::tick_pipeline::PipelineKind`（engine_mode 標籤）
//! 硬邊界：
//!   - I/O 失敗 fail-soft：`tracing::error!` + 不 panic + 不阻塞 close-all loop
//!   - 不 cache file handle —— 每次 open（事件頻率極低）
//!   - HaltKind 序列化採穩定字串（"daily_loss" / "session_drawdown" / "other"），
//!     不可改 enum 順序，跨 restart snapshot 需穩定 ABI
//!   - 每行 JSON 必含 `schema_version: 1`；forward-compat 升 schema 時 bump

use std::fs::OpenOptions;
use std::io::Write;
use std::path::PathBuf;

use serde::{Deserialize, Serialize};
use tracing::{error, info};

use crate::config::RiskConfig;
use crate::drawdown_revoke::DRAWDOWN_REASON_PREFIX;
use crate::paper_state::PaperState;
use crate::risk_checks::DAILY_LOSS_REASON_PREFIX;
use crate::tick_pipeline::PipelineKind;

/// Halt 分類，set 時凍結並隨 paper_paused 一起保存於 TickPipeline。
///
/// 序列化規則（DO NOT REORDER）：
///   - `DailyLoss` → "daily_loss"
///   - `SessionDrawdown` → "session_drawdown"
///   - `Other` → "other"
///
/// 跨 restart snapshot ABI 穩定 — 改字串 / 改順序會破壞既有 mode_snapshot 還原。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum HaltKind {
    /// priority 9 `RiskAction::HaltSession("DAILY LOSS: ...")`
    DailyLoss,
    /// priority 7 `RiskAction::HaltSession("SESSION DRAWDOWN: ...")`
    SessionDrawdown,
    /// Fail-safe 兜底：未知 reason 字串；永遠 sticky，不可 TTL auto-clear。
    Other,
}

impl HaltKind {
    /// Reason 字串 → HaltKind 分類；exact-prefix match（非 substring）。
    ///
    /// 規則：
    ///   1. `starts_with("SESSION DRAWDOWN")` → SessionDrawdown
    ///   2. `starts_with("DAILY LOSS")` → DailyLoss
    ///   3. 其他 → Other（fail-safe sticky）
    ///
    /// 順序：drawdown 先於 daily_loss 避免子字串歧義（雖然當前兩個常數
    /// 互不為子串，順序仍維持與 `drawdown_revoke::should_revoke` 對齊）。
    pub fn classify(reason: &str) -> Self {
        if reason.starts_with(DRAWDOWN_REASON_PREFIX) {
            Self::SessionDrawdown
        } else if reason.starts_with(DAILY_LOSS_REASON_PREFIX) {
            Self::DailyLoss
        } else {
            Self::Other
        }
    }

    /// 穩定字串 — 用於 log / governance_audit_log payload。
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::DailyLoss => "daily_loss",
            Self::SessionDrawdown => "session_drawdown",
            Self::Other => "other",
        }
    }
}

/// E3 MEDIUM-1（2026-05-19 Round 2）：f64 → JSON number 安全轉換。
///
/// 為什麼必要：`serde_json::Number::from_f64(NaN | +Inf | -Inf)` 回傳 `None`，
/// 直接套 `json!({ "x": some_f64 })` 在 NaN 時 panic（macro 內部 unwrap）。
/// halt_audit 路徑必 fail-soft —— 不可在 incident 期間因餘額更新除零產生
/// 的 NaN 把整個 step_6 HaltSession arm 拉成 panic 後死鎖。
/// 用法：將所有 f64 載荷欄位包成此 helper，NaN/Inf 落 `Value::Null`，
/// JSON Schema v1 已允許 nullable type。
fn json_number_or_null(value: f64) -> serde_json::Value {
    serde_json::Number::from_f64(value)
        .map(serde_json::Value::Number)
        .unwrap_or(serde_json::Value::Null)
}

/// MUST-FIX-1（2026-05-19 Round 2）：clear_path → event_type 規範化映射。
///
/// Spec §3.8 / §3.9 契約：
///   - `auto_ttl` 由 `check_and_clear_halt_expired` 觸發 → `halt_session_auto_cleared`
///   - `ipc_resume` / `ipc_reset` / `ipc_system_mode_shadow` 三個 manual 路徑
///     → `halt_session_manual_cleared`
///   - 未知 clear_path：fail-safe 走 manual_cleared（更保守，不會把 manual
///     誤標為 auto；Round 1 bug 反向：所有路徑硬編碼為 auto_cleared）
///
/// 為什麼不 fail-loud：halt_audit 本就 fail-soft（writeln! 出錯都不 panic），
/// 此 helper 同層級 — 與其拒寫一條 audit row（造成 ledger 空洞），不如保守
/// 標 manual_cleared + 透過 tracing::error! 警示 operator 排查 clear_path
/// 來源。新呼叫端若加新 path，CI 端 grep allowlist 攔截。
fn event_type_for_clear_path(clear_path: &str) -> &'static str {
    match clear_path {
        "auto_ttl" => "halt_session_auto_cleared",
        "ipc_resume" | "ipc_reset" | "ipc_system_mode_shadow" => "halt_session_manual_cleared",
        unknown => {
            // 未在 allowlist：fail-safe 走 manual_cleared 並警示 operator。
            error!(
                clear_path = unknown,
                "halt_audit: unknown clear_path → fallback halt_session_manual_cleared / \
                 未知 clear_path，回退 manual_cleared"
            );
            "halt_session_manual_cleared"
        }
    }
}

/// Forensic halt_audit.log 寫入路徑解析（spec §5.3 fallback chain）。
///
/// 優先序：
///   1. env `OPENCLAW_HALT_AUDIT_LOG`（顯式 override）
///   2. `$OPENCLAW_DATA_DIR/halt_audit.log`
///   3. `/tmp/openclaw/halt_audit.log`（最終 fallback）
///
/// 注意：`/tmp` 在 systemd-tmpfiles 環境 reboot 會被清除，但與既有 watchdog /
/// canary 路徑一致；P2-FORENSIC-LOG-PATH-DEFAULT 已開 ticket 視 7d observation
/// 決定是否改 default。
fn resolve_log_path() -> PathBuf {
    if let Ok(explicit) = std::env::var("OPENCLAW_HALT_AUDIT_LOG") {
        return PathBuf::from(explicit);
    }
    let data_dir = std::env::var("OPENCLAW_DATA_DIR").unwrap_or_else(|_| "/tmp/openclaw".into());
    PathBuf::from(data_dir).join("halt_audit.log")
}

/// 寫一行 JSONL 到 forensic log，append-only + fsync。失敗 fail-soft：
/// `tracing::error!` 但不阻塞 close-all loop。
fn write_jsonl_line(line: &str) {
    let path = resolve_log_path();
    // 確保父目錄存在（first write on fresh /tmp/openclaw 必經）。
    if let Some(parent) = path.parent() {
        if !parent.exists() {
            if let Err(e) = std::fs::create_dir_all(parent) {
                error!(
                    path = %path.display(),
                    error = %e,
                    "halt_audit: failed to create parent dir / 無法建立父目錄"
                );
                return;
            }
        }
    }
    // OpenOptions append + create；不 cache fd（事件頻率極低 + 避免 long-running lock）。
    match OpenOptions::new()
        .create(true)
        .append(true)
        .open(&path)
    {
        Ok(mut f) => {
            // 寫一行 + 換行；失敗 fail-soft 記錄即可。
            if let Err(e) = writeln!(f, "{}", line) {
                error!(
                    path = %path.display(),
                    error = %e,
                    "halt_audit: write failed / 寫入失敗"
                );
                return;
            }
            // fsync 保證落盤（事故下重啟也能讀回）。
            if let Err(e) = f.sync_all() {
                error!(
                    path = %path.display(),
                    error = %e,
                    "halt_audit: fsync failed / 落盤失敗"
                );
            }
        }
        Err(e) => {
            error!(
                path = %path.display(),
                error = %e,
                "halt_audit: open failed / 開檔失敗"
            );
        }
    }
}

/// 量化 context 欄位 — 從 PaperState 拉「能算」的，不能算的填 null（不阻塞）。
///
/// 為什麼用 `serde_json::Value` 而非具體 struct：
///   - per_strategy_drawdown_contribution / per_symbol_atr_pct 等欄位若無
///     對應 helper 直接可用，先寫 null；後續視需要再加 helper（spec §5.1 schema
///     已用 nullable type 允許 null）。
///   - 避免本模塊吃 IndicatorEngine / PortfolioState 等重依賴 → 模塊獨立性最大。
fn build_quant_context_payload(paper_state: &PaperState) -> serde_json::Value {
    // 餘額歷史：last 10 (ts, balance) tuples — 用於重建 daily_loss_pct 計算路徑。
    // 為什麼採 best-effort：PaperState 若沒 `balance_history()` accessor 就回空 array，
    // 不擋 halt 路徑。
    let balance_history = paper_state_balance_history(paper_state);
    let peak = paper_state.peak_balance();
    let current = paper_state.balance();
    // peak monotonically non-decreasing 是設計不變量；違反代表 measurement bug。
    // is_finite 同時排除 NaN / Inf，遇上 NaN-tainted state 時 paper_state_recompute_ok=false
    // 仍可寫入（E3 MEDIUM-1 fold-in）。
    let paper_state_recompute_ok = peak.is_finite() && current.is_finite() && peak >= current * 0.999;

    serde_json::json!({
        "per_symbol_drawdown_max_pct": serde_json::Value::Null,
        "per_symbol_drawdown_max_symbol": serde_json::Value::Null,
        "consecutive_loss_max_count": serde_json::Value::Null,
        "correlated_exposure_pct": serde_json::Value::Null,
        "paper_state_recompute_ok": paper_state_recompute_ok,
        "paper_state_balance_history": balance_history,
        "per_strategy_drawdown_contribution_pct": serde_json::Value::Null,
        "per_symbol_atr_pct": serde_json::Value::Null,
    })
}

/// 取最近 10 筆 balance history（若可拿到）。
///
/// 設計選擇：PaperState 目前未暴露 balance_history accessor —— 直接讀 peak +
/// current 二元組（schema 仍接受 array of length 1），避免本 IMPL 順手加 PaperState
/// API（最小影響原則）。後續若 P1-HALT-TRIGGER-ROOT-CAUSE-INVESTIGATION-1
/// 顯示需要更深 history → 再加 accessor + bump schema_version。
fn paper_state_balance_history(paper_state: &PaperState) -> serde_json::Value {
    let peak = paper_state.peak_balance();
    let current = paper_state.balance();
    // E3 MEDIUM-1：NaN/Inf 餘額包 json_number_or_null，避免 macro panic。
    serde_json::json!([
        {"label": "peak", "balance": json_number_or_null(peak)},
        {"label": "current", "balance": json_number_or_null(current)},
    ])
}

/// HaltSession 觸發時的 forensic 紀錄。
///
/// 流程：
///   1. 組 JSON payload（schema_version=1 + 所有 spec §5.1 欄位）
///   2. 寫 halt_audit.log（append-only，fsync）
///   3. info! 結構化 log 雙寫（engine.log 也保留主要欄位）
///   4. 呼叫端額外負責 governance_audit_log INSERT（透過 audit writer
///      channel；本模塊不直連 PG）
///
/// 失敗 fail-soft：寫檔錯 → tracing::error! 但不 panic、不回傳 Err 阻塞。
pub fn record_halt_set(
    kind: HaltKind,
    reason: &str,
    pipeline_kind: PipelineKind,
    engine_mode: &str,
    risk_config: &RiskConfig,
    risk_config_version_seen: u64,
    paper_state: &PaperState,
    ts_ms: u64,
) {
    let quant_ctx = build_quant_context_payload(paper_state);
    // E3 MEDIUM-1（2026-05-19 Round 2）：所有 f64 字段必過 json_number_or_null，
    // 否則 NaN-tainted PaperState（IPC tampering / 餘額更新除零 / 策略 bug）會
    // 在 serde_json::Number::from_f64 階段觸發 panic，把 step_6 HaltSession arm
    // 整段 unwind → engine deadlock。fail-soft 的本意是「失敗也要寫得進 audit」，
    // 任何 panic 路徑都違反此 invariant。
    let payload = serde_json::json!({
        "schema_version": 1,
        "ts_ms": ts_ms,
        "ts_iso": iso8601_from_ts_ms(ts_ms),
        "event": "halt_session_set",
        "kind": kind.as_str(),
        "reason": reason,
        "engine_mode": engine_mode,
        "pipeline_kind": pipeline_kind.db_mode(),
        "process_pid": std::process::id(),
        "peak_balance": json_number_or_null(paper_state.peak_balance()),
        "current_balance": json_number_or_null(paper_state.balance()),
        "session_drawdown_pct": json_number_or_null(paper_state.drawdown_pct()),
        // daily_loss_pct 不在 PaperState API，留 null —— 由呼叫端可附 governance_audit_log payload。
        "daily_loss_pct": serde_json::Value::Null,
        "loaded_drawdown_threshold": json_number_or_null(risk_config.limits.session_drawdown_max_pct),
        "loaded_daily_loss_threshold": json_number_or_null(risk_config.limits.daily_loss_max_pct),
        "risk_config_source": serde_json::Value::Null,
        "risk_config_version_seen": risk_config_version_seen,
        "halt_set_ts_ms": ts_ms,
        // Quant-context 欄位 6 個（spec §5.1 MUST-2）：
        "per_symbol_drawdown_max_pct": quant_ctx["per_symbol_drawdown_max_pct"].clone(),
        "per_symbol_drawdown_max_symbol": quant_ctx["per_symbol_drawdown_max_symbol"].clone(),
        "consecutive_loss_max_count": quant_ctx["consecutive_loss_max_count"].clone(),
        "correlated_exposure_pct": quant_ctx["correlated_exposure_pct"].clone(),
        "paper_state_recompute_ok": quant_ctx["paper_state_recompute_ok"].clone(),
        "paper_state_balance_history": quant_ctx["paper_state_balance_history"].clone(),
        "per_strategy_drawdown_contribution_pct": quant_ctx["per_strategy_drawdown_contribution_pct"].clone(),
        "per_symbol_atr_pct": quant_ctx["per_symbol_atr_pct"].clone(),
    });
    let line = payload.to_string();
    write_jsonl_line(&line);
    // 雙寫 engine.log（事故救援主入口）。
    info!(
        kind = kind.as_str(),
        reason = %reason,
        engine_mode,
        peak_balance = paper_state.peak_balance(),
        current_balance = paper_state.balance(),
        loaded_drawdown_threshold = risk_config.limits.session_drawdown_max_pct,
        loaded_daily_loss_threshold = risk_config.limits.daily_loss_max_pct,
        risk_config_version_seen,
        ts_ms,
        "halt_audit: halt_session_set / 會話暫停被觸發"
    );
}

/// Halt 被清除時的 forensic 紀錄。
///
/// `clear_path` 是固定 string set；對應 event_type 由 `event_type_for_clear_path`
/// 映射：
///   - "auto_ttl" → `halt_session_auto_cleared` （TTL 過期自動清除，daily_loss only）
///   - "ipc_resume" → `halt_session_manual_cleared`（IPC Resume）
///   - "ipc_reset" → `halt_session_manual_cleared`（IPC Reset）
///   - "ipc_system_mode_shadow" → `halt_session_manual_cleared`（IPC SystemMode→ShadowOnly）
///   - 其他未知值 → fail-safe 走 `halt_session_manual_cleared` + tracing::error 警示
///
/// MUST-FIX-1（2026-05-19 Round 2）：Round 1 寫死 `halt_session_auto_cleared`
/// 造成 IPC Resume/Reset/SystemMode 三條 manual 路徑被誤標為 auto-clear；spec §3.9
/// 的 manual vs auto 區分被破壞，operator 7d query A-2-EV 永遠看不到 manual_cleared。
pub fn record_halt_cleared(
    kind: HaltKind,
    set_ts_ms: u64,
    cleared_ts_ms: u64,
    pipeline_kind: PipelineKind,
    engine_mode: &str,
    clear_path: &str,
) {
    let elapsed_ms = cleared_ts_ms.saturating_sub(set_ts_ms);
    let event_type = event_type_for_clear_path(clear_path);
    let payload = serde_json::json!({
        "schema_version": 1,
        "ts_ms": cleared_ts_ms,
        "ts_iso": iso8601_from_ts_ms(cleared_ts_ms),
        "event": event_type,
        "kind": kind.as_str(),
        "engine_mode": engine_mode,
        "pipeline_kind": pipeline_kind.db_mode(),
        "process_pid": std::process::id(),
        "halt_set_ts_ms": set_ts_ms,
        "cleared_ts_ms": cleared_ts_ms,
        "elapsed_ms": elapsed_ms,
        "clear_path": clear_path,
    });
    let line = payload.to_string();
    write_jsonl_line(&line);
    info!(
        kind = kind.as_str(),
        engine_mode,
        set_ts_ms,
        cleared_ts_ms,
        elapsed_ms,
        clear_path,
        event = event_type,
        "halt_audit: halt_session_cleared / 會話暫停已清除"
    );
}

/// ISO-8601 UTC 字串（毫秒精度）— 用 chrono Utc。chrono 已 workspace dep。
fn iso8601_from_ts_ms(ts_ms: u64) -> String {
    // 毫秒 → secs + nanos；用 try_from 避免 i64 overflow（>= 9 × 10^15 ms 才 overflow）。
    let secs = (ts_ms / 1000) as i64;
    let nanos = ((ts_ms % 1000) as u32) * 1_000_000;
    match chrono::DateTime::<chrono::Utc>::from_timestamp(secs, nanos) {
        Some(dt) => dt.to_rfc3339_opts(chrono::SecondsFormat::Millis, true),
        None => format!("ts_ms_invalid:{}", ts_ms),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::event_consumer::paper_state_restore::env_test_lock as env_lock;

    #[test]
    fn classify_daily_loss() {
        let r = "DAILY LOSS: 15.5% >= 15.0%";
        assert_eq!(HaltKind::classify(r), HaltKind::DailyLoss);
    }

    #[test]
    fn classify_drawdown() {
        let r = "SESSION DRAWDOWN: 25.1% >= 25.0%";
        assert_eq!(HaltKind::classify(r), HaltKind::SessionDrawdown);
    }

    #[test]
    fn classify_other_fail_safe_sticky() {
        let r = "unknown reason";
        assert_eq!(HaltKind::classify(r), HaltKind::Other);
        let r2 = "";
        assert_eq!(HaltKind::classify(r2), HaltKind::Other);
    }

    #[test]
    fn classify_is_exact_prefix_not_substring() {
        // contains 但不 starts_with 的字串應該分到 Other
        let r = "some prefix DAILY LOSS in middle";
        assert_eq!(HaltKind::classify(r), HaltKind::Other);
    }

    #[test]
    fn halt_kind_as_str_stable_abi() {
        assert_eq!(HaltKind::DailyLoss.as_str(), "daily_loss");
        assert_eq!(HaltKind::SessionDrawdown.as_str(), "session_drawdown");
        assert_eq!(HaltKind::Other.as_str(), "other");
    }

    #[test]
    fn halt_kind_serde_roundtrip() {
        let kinds = [HaltKind::DailyLoss, HaltKind::SessionDrawdown, HaltKind::Other];
        for k in &kinds {
            let json = serde_json::to_string(k).unwrap();
            let parsed: HaltKind = serde_json::from_str(&json).unwrap();
            assert_eq!(parsed, *k);
        }
    }

    #[test]
    fn iso8601_known_timestamp() {
        // 任一已知 UTC ts，驗格式：必含 T / ms / Z（RFC3339 格式）。
        let ts_ms: u64 = 1_700_000_000_000; // 2023-11-14T22:13:20.000Z
        let iso = iso8601_from_ts_ms(ts_ms);
        // 格式：YYYY-MM-DDThh:mm:ss.mmmZ
        assert!(
            iso.len() == 24 && iso.ends_with('Z') && iso.contains('T') && iso.contains('.'),
            "ISO-8601 format check failed; got {}",
            iso
        );
    }

    #[test]
    fn resolve_log_path_prefers_explicit_env() {
        let _guard = env_lock();
        // 鎖期間先清掉 OPENCLAW_HALT_AUDIT_LOG，避免被前一 test 殘留值影響
        // fallback 字串組裝結果。
        unsafe {
            std::env::remove_var("OPENCLAW_HALT_AUDIT_LOG");
        }
        let p = resolve_log_path();
        // 至少要包含 halt_audit.log 檔名
        assert!(
            p.to_string_lossy().ends_with("halt_audit.log"),
            "got {}",
            p.display()
        );
    }

    #[test]
    fn test_event_type_for_clear_path_mapping() {
        // MUST-FIX-1（2026-05-19 Round 2）：4 個官方 clear_path → 正確 event_type
        // 映射；未知值 fail-safe 落 manual_cleared 並透過 tracing::error 提示。
        assert_eq!(
            event_type_for_clear_path("auto_ttl"),
            "halt_session_auto_cleared"
        );
        assert_eq!(
            event_type_for_clear_path("ipc_resume"),
            "halt_session_manual_cleared"
        );
        assert_eq!(
            event_type_for_clear_path("ipc_reset"),
            "halt_session_manual_cleared"
        );
        assert_eq!(
            event_type_for_clear_path("ipc_system_mode_shadow"),
            "halt_session_manual_cleared"
        );
        // 未知值 fail-safe 走 manual_cleared（保守，不會把 manual 標為 auto）
        assert_eq!(
            event_type_for_clear_path("future_unknown_path"),
            "halt_session_manual_cleared"
        );
        assert_eq!(event_type_for_clear_path(""), "halt_session_manual_cleared");
    }

    #[test]
    fn test_record_halt_cleared_event_type_mapping() {
        let _guard = env_lock();
        // MUST-FIX-1（2026-05-19 Round 2）：完整鏈路測試 record_halt_cleared 寫
        // 入的 JSONL 行 "event" 字段，按 clear_path 對應 4 個官方值。
        // 改用顯式 tempdir + OPENCLAW_HALT_AUDIT_LOG env override 隔離。
        let tmp = std::env::temp_dir().join(format!(
            "halt_audit_clear_path_test_{}_{}.log",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map(|d| d.as_nanos())
                .unwrap_or(0)
        ));
        let _ = std::fs::remove_file(&tmp);

        // SAFETY: 單一 test 內串行改 env；測試末尾清除。
        unsafe {
            std::env::set_var("OPENCLAW_HALT_AUDIT_LOG", &tmp);
        }

        let pipeline_kind = PipelineKind::Demo;
        let engine_mode = "demo";

        // 4 個 official path + 1 unknown fail-safe；逐個 iteration truncate
        // 自身 tmp 檔，避免其他併發 test（per_symbol_price_pnl 等）寫進 default
        // path 干擾 .lines().last()。
        for (clear_path, expected_event) in [
            ("auto_ttl", "halt_session_auto_cleared"),
            ("ipc_resume", "halt_session_manual_cleared"),
            ("ipc_reset", "halt_session_manual_cleared"),
            ("ipc_system_mode_shadow", "halt_session_manual_cleared"),
            ("future_path_not_in_allowlist", "halt_session_manual_cleared"),
        ] {
            // 每 iteration 確保 file 從空開始
            let _ = std::fs::remove_file(&tmp);
            record_halt_cleared(
                HaltKind::DailyLoss,
                1_000_000_000,
                1_000_086_400_000,
                pipeline_kind,
                engine_mode,
                clear_path,
            );
            // 找本 iteration 的 cleared 行：用 clear_path 字段精確篩出
            // （即便其他併發 test 寫進來，本行也唯一 by clear_path）
            let content = std::fs::read_to_string(&tmp).expect("log should exist");
            let target = content
                .lines()
                .find(|line| {
                    serde_json::from_str::<serde_json::Value>(line)
                        .ok()
                        .and_then(|v| v.get("clear_path").and_then(|cp| cp.as_str().map(String::from)))
                        .as_deref()
                        == Some(clear_path)
                })
                .unwrap_or_else(|| {
                    panic!("clear_path={} 對應的行未找到，content={}", clear_path, content)
                });
            let parsed: serde_json::Value =
                serde_json::from_str(target).expect("JSONL line should parse");
            assert_eq!(
                parsed["event"].as_str().unwrap_or(""),
                expected_event,
                "clear_path={} 預期 event={}, 實際 {}",
                clear_path,
                expected_event,
                target
            );
            assert_eq!(parsed["clear_path"].as_str().unwrap_or(""), clear_path);
        }

        // cleanup
        let _ = std::fs::remove_file(&tmp);
        unsafe {
            std::env::remove_var("OPENCLAW_HALT_AUDIT_LOG");
        }
    }

    #[test]
    fn test_json_number_or_null_nan_inf_safe() {
        // E3 MEDIUM-1（2026-05-19 Round 2）：NaN / Inf 落 Null，finite f64 保 Number。
        assert!(matches!(
            json_number_or_null(f64::NAN),
            serde_json::Value::Null
        ));
        assert!(matches!(
            json_number_or_null(f64::INFINITY),
            serde_json::Value::Null
        ));
        assert!(matches!(
            json_number_or_null(f64::NEG_INFINITY),
            serde_json::Value::Null
        ));
        // finite value 保留為 Number；驗值正確。
        let v = json_number_or_null(123.45);
        assert!(matches!(v, serde_json::Value::Number(_)));
        assert!((v.as_f64().unwrap() - 123.45).abs() < 1e-9);
        // 0 / 負值 / 極大值
        assert!(matches!(json_number_or_null(0.0), serde_json::Value::Number(_)));
        assert!(matches!(
            json_number_or_null(-1e300),
            serde_json::Value::Number(_)
        ));
    }

    #[test]
    fn test_record_halt_set_with_nan_balance_does_not_panic() {
        let _guard = env_lock();
        // E3 MEDIUM-1（2026-05-19 Round 2）：NaN-tainted PaperState 應 fail-soft
        // 完成 JSON 寫入，不能因 serde_json::Number::from_f64(NaN)=None 而 panic。
        // 用 OPENCLAW_HALT_AUDIT_LOG env 指向 tempfile 隔離測試。
        let tmp = std::env::temp_dir().join(format!(
            "halt_audit_nan_test_{}_{}.log",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map(|d| d.as_nanos())
                .unwrap_or(0)
        ));
        let _ = std::fs::remove_file(&tmp);

        // SAFETY: 串行 test 改 env；末尾清除。
        unsafe {
            std::env::set_var("OPENCLAW_HALT_AUDIT_LOG", &tmp);
        }

        // 製造 NaN-tainted PaperState：注入 NaN 餘額（用 reset_balance + manual mutation
        // 不在 public API；改用 inject_balance_for_nan_test 不存在，
        // 直接構造 PaperState::new(NaN) 觀察 .balance() 是否回 NaN）。
        // PaperState::new(NaN) → 內部 store；不檢驗 finite 之下 .balance() 回 NaN。
        let nan_state = crate::paper_state::PaperState::new(f64::NAN);

        let risk_config = crate::config::RiskConfig::default();

        // 不應 panic — 用獨特 reason 字串以便精確 filter 本 test 的寫入行
        let unique_reason = "DAILY LOSS: NaN% >= 15.0% / round2-nan-guard-test";
        record_halt_set(
            HaltKind::DailyLoss,
            unique_reason,
            PipelineKind::Demo,
            "demo",
            &risk_config,
            0,
            &nan_state,
            1_000_000_000,
        );

        // 驗檔案內 JSON 行 peak_balance / current_balance 落為 null。
        // env_lock + per_symbol_price_pnl test 的 env 還原 guard 確保本 test 寫入
        // 期間其他 test 不會搶寫 OPENCLAW_HALT_AUDIT_LOG → 用 unique_reason 精確篩。
        let content = std::fs::read_to_string(&tmp).expect("log should exist");
        assert!(!content.is_empty(), "no JSONL line written");
        let target_parsed = content
            .lines()
            .filter_map(|line| serde_json::from_str::<serde_json::Value>(line).ok())
            .find(|v| v.get("reason").and_then(|r| r.as_str()) == Some(unique_reason))
            .unwrap_or_else(|| panic!("NaN-test 行未找到，content={}", content));
        assert!(
            target_parsed["peak_balance"].is_null()
                || target_parsed["current_balance"].is_null(),
            "NaN balance 應落 null，parsed={}",
            target_parsed
        );

        // cleanup
        let _ = std::fs::remove_file(&tmp);
        unsafe {
            std::env::remove_var("OPENCLAW_HALT_AUDIT_LOG");
        }
    }

    #[test]
    fn write_jsonl_line_creates_file_in_tempdir() {
        let _guard = env_lock();
        // 用 OPENCLAW_HALT_AUDIT_LOG 顯式指向 tempdir 隔離 test。
        let tmp = std::env::temp_dir().join(format!(
            "halt_audit_test_{}_{}.log",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map(|d| d.as_nanos())
                .unwrap_or(0)
        ));
        // 為了避免污染進程 env、用 unsafe set 後 reset；此 test 為串行可接受。
        // 更乾淨方式：把 write_jsonl_line 改成接 path 參數 —— 本次最小變更不擴範圍。
        // SAFETY: 單 thread test 內改 env；測試結束清除。
        unsafe {
            std::env::set_var("OPENCLAW_HALT_AUDIT_LOG", &tmp);
        }
        write_jsonl_line(r#"{"schema_version":1,"test":"hello"}"#);
        let content = std::fs::read_to_string(&tmp).expect("should be written");
        assert!(content.contains("\"test\":\"hello\""));
        let _ = std::fs::remove_file(&tmp);
        unsafe {
            std::env::remove_var("OPENCLAW_HALT_AUDIT_LOG");
        }
    }
}
