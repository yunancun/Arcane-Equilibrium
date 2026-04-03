//! OpenClaw Core — Rust modules exposed to Python via PyO3
//! OpenClaw 核心 — 通過 PyO3 暴露給 Python 的 Rust 模組

use pyo3::prelude::*;

mod context_distiller;
mod hedging_engine;

/// OpenClaw Rust core module / OpenClaw Rust 核心模組
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
