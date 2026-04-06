//! LinUCB contextual bandit — pure Rust inference layer.
//! LinUCB 上下文 bandit — 純 Rust 推理層。
//!
//! MODULE_NOTE (EN): Phase 4 sub-task 4-04. Implements ridge-regression LinUCB
//!   inference (theta = A^{-1} b, UCB = theta^T x + alpha * sqrt(x^T A^{-1} x))
//!   plus PG state IO with feature_schema_hash fail-closed and v1_15 cold-start
//!   arm enumeration. Warm-start migration is sub-task 4-06 and intentionally
//!   NOT included here.
//! MODULE_NOTE (中): Phase 4 子任務 4-04。實作 ridge-regression LinUCB 推理
//!   (theta = A^{-1} b, UCB = theta^T x + alpha * sqrt(x^T A^{-1} x))，
//!   加上 PG state IO（feature_schema_hash fail-closed）與 v1_15 cold-start
//!   arm 列舉。Warm-start 遷移屬於子任務 4-06，本模組刻意不實作。
//!
//! Math reference / 數學參考: docs/references/math_implementation_notes.md Entry 01 §1.3

pub mod arms_v1_15;
pub mod inference;
pub mod schema_hash;
pub mod state_io;

pub use arms_v1_15::v1_15_arm_ids;
pub use inference::{compute_theta, compute_ucb, select_arm, update, ArmState, LinUcbConfig};
pub use schema_hash::compute_feature_schema_hash;
pub use state_io::{load_arms, upsert_arm, LinUcbIoError};
