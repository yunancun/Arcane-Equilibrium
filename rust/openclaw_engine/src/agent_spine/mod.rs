//! Agent Decision Spine contracts and adapters.
//!
//! MAG-031 starts the spine as a shadow-only typed seam. The module converts
//! existing strategy outputs into typed `StrategySignal` objects and then
//! downgrades them to the current legacy `trading.signals` persistence shape
//! until MAG-032 lands the durable spine store.

pub mod config;
pub mod contracts;
pub mod signal_adapter;

#[cfg(test)]
mod tests;
