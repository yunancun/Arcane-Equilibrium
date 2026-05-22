//! Sprint 1B AC-7 — Rust ↔ Python cross-language 1e-4 fixture (Option A:
//! subprocess + JSON marker).
//!
//! MODULE_NOTE
//! 模塊用途:
//!   AC-7 spec §AC-7 要求 `engine_cpu_pct` 5 sample window mean / sigma 在 Rust
//!   端與 Python replay 端 1e-4 容差對齊。Sprint 1A-ζ Phase 3b
//!   `tests/test_spike_cross_lang_fixture.py` 已用 3 條 Python 實作互驗
//!   algorithm contract 數位 fingerprint;本 file 是 Rust 端最小 binding:
//!     - 跑 `compute_window_stats` (定義於 `health/mod.rs`)
//!     - println! 輸出 RUST_FIXTURE_JSON marker (mean / sigma)
//!     - Python `tests/test_spike_cross_lang_rust_binding.py` subprocess.run
//!       本 cargo test, parse stdout JSON, 與 Python expected 1e-4 對齊
//!
//! 為什麼 subprocess + JSON 而非 PyO3:
//!   per dispatch packet §Step 1 Option A vs B 決策:
//!     - Option A (subprocess + JSON): 0 新 dep, 0 build complication, spike
//!       scope 「最小 binding」契合
//!     - Option B (PyO3): 需新 crate + maturin build chain; 屬 H-18 全套範圍,
//!       Sprint 2+ carry-over
//!   per spec §5.3 H-18 「全套 binding」延 Sprint 2; 本 IMPL 走 Option A 收口
//!   AC-7 PARTIAL PASS → FULL PASS (Rust binding 真實對齊 Python expected)。
//!
//! 為什麼 spike feature flag 隔絕:
//!   per Sprint 1A-ζ §AC-5.1 規範,所有 cross-lang fixture 必 `--features
//!   spike` 才編譯; production binary (cargo build --release 不帶 spike) 完全
//!   不含本檔 → 0 production code path 污染。
//!
//! 主要 test 函數:
//!   - test_window_stats_fixture_json: 跑 compute_window_stats, 輸出
//!     RUST_FIXTURE_JSON marker, assert Rust 端內驗 expected 值 1e-10 對齊
//!
//! 硬邊界:
//!   - 只在 `--features spike` 編譯; production binary 不含本檔
//!   - 不依賴 IPC / DB / GovernanceHub; 純算術
//!   - JSON 格式必對齊 Python parse regex (RUST_FIXTURE_JSON: {...})

#![cfg(feature = "spike")]

use openclaw_engine::health::compute_window_stats;

/// AC-7 cross-lang fixture: Rust 端 mean / sigma 對齊 Python expected。
///
/// spec §AC-7 sample (對齊 Phase 3b PoC line 40):
///   [10.0, 20.0, 30.0, 25.0, 15.0]
///   mean = 20.0
///   sample_sigma (ddof=1) = sqrt(62.5) ≈ 7.905694150420948
///
/// 輸出 JSON marker (Python parse 用):
///   RUST_FIXTURE_JSON: {"mean": 20.0, "sigma": 7.905694150420948}
///
/// 為什麼 println! 而非 file output:
///   subprocess.run capture_output=True 抓 stdout 是最低 coupling 路徑;
///   不用磁盤臨時檔, 也避免 fixtures/ 目錄污染。
#[test]
fn test_window_stats_fixture_json() {
    let samples = [10.0_f64, 20.0, 30.0, 25.0, 15.0];
    let (mean, sigma) =
        compute_window_stats(&samples).expect("len 5 must return Some");

    // 輸出 JSON marker — Python test subprocess 端 regex parse 此行。
    // 為什麼 print!: --nocapture 才會輸出, Python 端用 `--` `--nocapture` flag
    // 確保 stdout 可見。
    println!(
        "RUST_FIXTURE_JSON: {{\"mean\": {}, \"sigma\": {}}}",
        mean, sigma
    );

    // Rust 端內驗 (1e-10 嚴格,因 Rust naive two-pass 同 Python naive 算法數位
    // 一致)。Python 端用 1e-4 寬容差驗 cross-lang。
    assert!(
        (mean - 20.0).abs() < 1e-10,
        "Rust mean drift: {}, expected 20.0",
        mean
    );
    assert!(
        (sigma - 7.905694150420948).abs() < 1e-10,
        "Rust sigma drift: {}, expected 7.905694150420948",
        sigma
    );
}
