//! Governance module — M1 Decision Lease LAL state machine namespace.
//!
//! MODULE_NOTE
//! 模塊用途：M1 Decision Lease Layered Approval (LAL) 治理層的 Rust skeleton。
//!   Sprint 1A-ζ Phase 2 Track A IMPL：LAL Tier 0/1 state machine + ADR-0034
//!   Decision 6 RETIRED blocker query path stub。Tier 2/3/4 stub 留給 Sprint 4+。
//! 主要 sub-module：
//!   - `lal`：LalTier enum / from_i32 / numeric_value / state transition Tier 0 → 1
//!     + Tier 0 fill RETIRED blocker query stub。
//! 依賴：
//!   - V112 sandbox migration（governance.lease_lal_tiers + lease_lal_assignments + MV）
//!   - V113 placeholder（learning.decay_signals）— RETIRED blocker query 目標
//! 硬邊界：
//!   - ADR-0034 line 41「數字越大越嚴」對齊矩陣是 LAL 0-4 single source of truth；
//!     numeric_value() 必嚴格遞增。
//!   - Tier 0 fill query 必走 RETIRED blocker（per ADR-0034 Decision 6）；
//!     RETIRED → fail-closed reject fill + audit log；LAL 4 manual override 也禁用。
//!   - Tier 2/3/4 transition 在本 Sprint 1A-ζ spike 範圍外；未 IMPL 走 unimplemented!()。

pub mod lal;
