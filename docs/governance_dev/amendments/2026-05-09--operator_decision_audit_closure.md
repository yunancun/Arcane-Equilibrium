# Amendment AMD-2026-05-09-02 - Operator Decision Audit Closure

**對應 spec**: SM-05 · DOC-01 §5.3/§5.6/§5.10/§5.11 · ADR-0015 · ADR-0018 · ADR-0020
**日期**: 2026-05-09
**作者**: PM
**狀態**: Accepted / F-01 source implemented for SM-05
**索引**: `SPECIFICATION_REGISTER.md` Amendments section
**TODO 連結**: `P0-DECISION-AUDIT-2` / `P0-DECISION-AUDIT-4` / `P0-DECISION-AUDIT-5`

---

## 1. Decision Summary

The operator decision audit is closed by selecting the PA-recommended paths.
This amendment records planning authority only; it does not mutate runtime
state, live authorization, strategy risk config, or order authority.

| ID | Selected path | Implementation implication |
|---|---|---|
| `P0-DECISION-AUDIT-2` | Option A | `executor.shadow_mode=true` is the W-A demo fail-closed posture. The local 5-Agent Executor path is not permanently shadow-only, but `shadow_mode=false` may be used only after `P0-EDGE-1` plus supervised promotion gates. |
| `P0-DECISION-AUDIT-4` | Option ii | Keep grid conditional to ORDIUSDT; revise `ma_crossover`; reject `bb_breakout` 1m and redesign as 5m; retire `funding_arb`; pair `bb_reversion` with MA confirmation. |
| `P0-DECISION-AUDIT-5` | Option i + ii | Treat the nine legacy `openclaw_core` modules as permanent sunset candidates; keep Layer2 as GUI/manual supervisor workflow by design, not an autonomous loop. |

---

## 2. SM-05 Authority Boundary

The selected SM-05 policy is:

1. Rust `RiskConfig.executor.shadow_mode` remains the source of truth for
   Python Executor submit-vs-shadow behavior.
2. `shadow_mode=true` is fail-closed and safe for W-A/W-C evidence collection.
3. `shadow_mode=false` is a promotion state, not a live authorization grant.
4. Promotion requires positive edge scope, supervised-live gates, Decision
   Lease, risk gates, signed live authorization where applicable, and Rust
   execution authority.
5. F-01 has removed the unconditional `lambda: True` fallback in
   `ExecutorAgent`; production construction remains wired to the explicit
   `ExecutorConfigCache.shadow_mode_provider()`, and unavailable provider reads
   fail closed.

---

## 3. Strategy Verdict

The W-AUDIT-6 implementation queue is unblocked with these verdicts:

- `grid`: conditional keep for ORDIUSDT only.
- `ma_crossover`: revise R:R, trailing/TP, and promotion criteria.
- `bb_breakout`: reject 1m; redesign 5m before any promotion.
- `funding_arb`: retire from new strategy promotion and remove from active
  RiskConfig schema in the W-AUDIT-6 cleanup pass.
- `bb_reversion`: keep only when paired with MA confirmation.

The 2026-05-16 `funding_arb` audit remains useful as a verification artifact,
not as the decision gate for retirement.

---

## 4. Structural Sunset

The nine legacy `openclaw_core` modules named in `P2-AUDIT-DEAD-CODE` are
permanent sunset candidates. W-AUDIT-5 may remove them after a source-reference
audit and green tests.

Layer2 remains a manual/operator escalation lane through the GUI/supervisor
flow. An hourly autonomous Layer2 loop is not part of the active roadmap unless
a new ADR reverses this decision.

---

## 5. Non-Goals

This amendment does not:

- write or renew live authorization;
- flip any TOML `shadow_mode` value;
- change strategy/risk config files;
- delete code;
- rebuild, restart, or deploy;
- approve true live, MAG-083, or MAG-084.

---

*OpenClaw / Arcane Equilibrium Governance Amendment - AMD-2026-05-09-02*
