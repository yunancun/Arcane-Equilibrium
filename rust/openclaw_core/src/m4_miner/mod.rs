// MODULE_NOTE
// 模塊用途：M4 Pattern Miner Stage 1 — Rust hot-path 統計 hypothesis miner。
//   從 5 source（kline / fills / liquidations / funding / unlocks stub）的 in-memory
//   slice 算 leak-free rolling cross-correlation + event-window forward return shift，
//   產出 PatternDraft 候選給 Python 端寫入 learning.hypotheses 表（V100+V103 EXTEND）。
//
// 主要類/函數：
//   - types::PatternDraft / StatisticalResult / EventWindowResult
//   - feature_engineering::shift1_rolling_mean / shift1_rolling_std / shift1_rolling_pct_change
//   - cross_correlation::pearson_corr / spearman_corr
//   - event_window::detect_funding_flip / detect_liquidation_cascade / detect_large_funding_spike
//   - bonferroni::K_TOTAL / correct_p_value / is_significant_after_correction
//   - tick_window::TickWindowAggregator（hot-path 1m bar 聚合）
//
// 依賴：openclaw_types（shared types）+ serde + chrono。
//   為什麼不引 polars / sqlx / rayon / statrs：scaffold 階段 keep dep clean，
//   後續 Sprint 3 接 cron wire-up + 1M+ row 真實 batch 後再評估 polars 必要性。
//   目前用 pure Rust slice 操作 — algorithm correctness 不變、build cost 0。
//
// 硬邊界（per W1-B spec §0 + §2 + §5）：
//   I-1: 所有 rolling stat 必 .shift(1)（leak-free）— 由 feature_engineering 強制
//   I-2: 黑名單 method 禁用（HMM / Markov-switching / GARCH）— 本 module 不引入
//   I-3: K_TOTAL = 2500，α_corrected = 2e-5 — bonferroni 模組 hard-code
//   I-4: Event-window N >= 30 硬 gate — event_window 模組強制
//   I-5: 不寫 PG INSERT（DRAFT writeback 在 Python 端，本 module 只產 struct）
//
// 與 Python orchestrator 介接：
//   Sprint 2 scaffold 階段：Rust 不啟 PyO3 binding，Python 用獨立實裝 + 對齊 SSOT；
//   Sprint 3+ 接 cron 時可加 PyO3 將 hot-path 算法 expose 給 Python。
//   Cross-language fixture（per W1-B spec §5.3）由 srv/tests/test_m4_cross_language_fixture.py
//   走 OHLCV parquet 並列驗 Rust / Python / PG 三套對齊（max diff < 1e-4）。

pub mod bonferroni;
pub mod cross_correlation;
pub mod event_window;
pub mod feature_engineering;
pub mod tick_window;
pub mod types;

// Re-export 主要 public API 給其他 crate（如 openclaw_engine）或 Python PyO3 binding。
pub use bonferroni::{correct_p_value, is_significant_after_correction, BONFERRONI_K_TOTAL};
pub use cross_correlation::{pearson_corr, spearman_corr};
pub use event_window::{
    detect_funding_flip_events, detect_large_funding_spike_events, detect_liquidation_cascade_events,
    event_window_forward_shift, event_window_sample_gate,
};
pub use feature_engineering::{
    shift1_rolling_mean, shift1_rolling_pct_change, shift1_rolling_std, validate_leak_free_pattern,
};
pub use tick_window::TickWindowAggregator;
pub use types::{
    EventType, EventWindowResult, EventWindowVerdict, ForwardWindow, PatternDraft,
    StatisticalResult,
};
