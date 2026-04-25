//! Regime detection — Hurst exponent + hysteresis-based label stabilization.
//! Regime 偵測 — Hurst 指數 + 滯回標籤穩定。
//!
//! MODULE_NOTE (EN): G7-03 Phase A wave 2 module. Wraps the existing R/S Hurst
//!   estimator in `openclaw_core::indicators::volatility::hurst` with a typed
//!   `RegimeLabel` enum and a `HysteresisDetector` that requires a configurable
//!   number of consecutive same-side observations before flipping the persisted
//!   regime label. Public surface is the `hurst_label_for_symbol` adapter; the
//!   detector itself is exported for callers that own per-symbol state.
//!   Defaults are gated by `HurstConfig.enabled = false` so this module is a
//!   no-op until Phase B wires it into a strategy / scanner.
//! MODULE_NOTE (中): G7-03 Phase A 第二波模組。包裝 openclaw_core 既有的 R/S
//!   Hurst 估計器，提供類型化的 `RegimeLabel` enum 與 `HysteresisDetector`
//!   滯回器（需連續若干次同向觀察才翻轉持久化的 regime 標籤）。對外 API 為
//!   `hurst_label_for_symbol`，detector 本身亦匯出供持有 per-symbol 狀態的呼叫者。
//!   預設由 `HurstConfig.enabled = false` 鎖住，此模組在 Phase B 接線前完全 no-op。

pub mod hurst;

pub use hurst::{
    compute_hurst, hurst_label_for_symbol, HysteresisDetector, RegimeLabel,
};
