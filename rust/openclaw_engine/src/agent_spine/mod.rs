//! Agent Decision Spine contracts and adapters.
//!
//! MAG-031 starts the spine as a shadow-only typed seam. MAG-032 adds the
//! durable store contracts and writer surface without wiring runtime authority.

pub mod config;
pub mod contracts;
pub mod events;
pub mod signal_adapter;
pub mod store;

#[cfg(test)]
mod tests;
