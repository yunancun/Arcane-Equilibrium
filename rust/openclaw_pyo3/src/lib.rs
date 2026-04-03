//! MODULE_NOTE:
//! OpenClaw PyO3 Bridge — Rust modules exposed to Python via PyO3.
//! OpenClaw PyO3 橋接 — 通過 PyO3 暴露給 Python 的 Rust 模組。
//!
//! This crate is the single PyO3 entry point. Python imports it as `openclaw_core`.
//! 此 crate 是唯一的 PyO3 入口。Python 以 `openclaw_core` 名稱導入。
//!
//! Contains: ContextDistiller, HedgingEngine (Phase 3 modules).
//! 包含：ContextDistiller、HedgingEngine（Phase 3 模組）。

use pyo3::prelude::*;

mod context_distiller;
mod hedging_engine;

/// OpenClaw Rust core module — PyO3 entry point.
/// OpenClaw Rust 核心模組 — PyO3 入口點。
#[pymodule]
fn openclaw_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    // Context Distiller / 上下文蒸餾器
    m.add_class::<context_distiller::ContextDistiller>()?;
    m.add_class::<context_distiller::NotableEvent>()?;
    // Hedging Engine / 對沖引擎
    m.add_class::<hedging_engine::HedgingEngine>()?;
    m.add_class::<hedging_engine::HedgeRecommendation>()?;
    m.add_class::<hedging_engine::Position>()?;
    Ok(())
}
