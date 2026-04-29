//! Track P 物理層退場特徵 / Track P physical-layer exit features
//!
//! 共享型別：供 T3 (physical_micro_profit_lock v1 in `risk_checks`) 與 T4
//! (combine_layer + `on_tick` builder) 使用。
//! Shared types used by T3 (v1 `risk_checks::physical_micro_profit_lock`) and
//! T4 (combine_layer + `on_tick` builder) in the DUAL-TRACK-EXIT-1 Track P
//! skeleton.
//!
//! ## 模組佈局（EXIT-FEATURES-SPLIT-1, 2026-04-21）
//!
//! 本目錄 (`exit_features/`) 於 2026-04-21 由單一 1317 行 `exit_features.rs`
//! 拆出，以遵守 §七 1200 行硬上限、並讓型別 / 邏輯 / 建構器各自有獨立檔案
//! 與測試表面。外部呼叫仍走 `crate::exit_features::…`（本 `mod.rs` 的
//! `pub use` re-export 提供向後相容）。
//!
//! This directory was split from a single 1317-line `exit_features.rs` on
//! 2026-04-21 to honour §七's 1200-line hard cap and give types / logic /
//! builder each their own file and test surface. External callers keep using
//! `crate::exit_features::…` — the `pub use` re-exports below preserve
//! backward compatibility.
//!
//! ```text
//! exit_features/
//! ├── mod.rs        # 頂層 doctrine + pub use re-exports（本檔）
//! │                 #                                     (this file)
//! ├── core.rs       # ExitFeatures + PhysicalDecision (types)
//! ├── v2.rs         # ExitConfig + non_linear_giveback_fn
//! │                 # + physical_micro_profit_lock_v2
//! └── builder.rs    # build_exit_features_for_tick (T4 wiring helper)
//! ```
//!
//! ## Phase 1b Track P (a+b+c+e) — 2026-04-21
//!
//! The module exposes the **non-linear giveback** variant of the physical
//! micro-profit lock as a pure function (`physical_micro_profit_lock_v2` in
//! [`v2`]) so the same 4-gate logic can be replayed offline / used by the
//! Combine Layer without pulling in `risk_checks.rs` state. The legacy
//! linear-threshold version (`risk_checks::physical_micro_profit_lock` +
//! `PhysLockConfig`) remains wired into `check_position_on_tick` Priority 6
//! unchanged; the next wave (`TRACK-P-V2-SWAP-1`) swaps Priority 6 to consume
//! `ExitConfig` here.
//!
//! 本模組將 `physical_micro_profit_lock_v2`（含非線性 giveback 閾值）以 pure
//! fn 形式曝露於 [`v2`] 子模組，讓相同 4 Gate 邏輯可離線重放 / 供 Combine
//! Layer 使用而無需 `risk_checks.rs` 狀態。舊線性閾值版
//! (`risk_checks::physical_micro_profit_lock` + `PhysLockConfig`) 仍在
//! Priority 6 運作；下一波 (`TRACK-P-V2-SWAP-1`) 再替換為讀取本模組
//! `ExitConfig`。

pub mod builder;
pub mod core;
pub mod v2;

// Backward-compatible re-exports so `crate::exit_features::ExitFeatures`,
// `crate::exit_features::ExitConfig`, etc. continue to resolve exactly as
// before the split. Keep each symbol on its own `pub use` line to make
// additions/removals diff-friendly and to surface the external API surface
// in one glance at the top of this file.
// 向後相容 re-export：外部繼續以 `crate::exit_features::…` 訪問，與拆分前一致。
pub use crate::exit_features::builder::build_exit_features_for_tick;
pub use crate::exit_features::core::{ExitFeatures, PhysicalDecision};
pub use crate::exit_features::v2::{physical_micro_profit_lock_v2, ExitConfig};

// `non_linear_giveback_fn` stays `pub(crate)` — only v2 tests + the lock fn
// itself reach for it, no external consumer. Re-export intentionally omitted
// so the crate-private surface does not accidentally leak via `crate::exit_features::…`.
// `non_linear_giveback_fn` 保持 `pub(crate)`：僅 v2 tests + lock fn 本身使用，
// 無外部 consumer。刻意不 re-export，避免 crate-private 介面外洩。
