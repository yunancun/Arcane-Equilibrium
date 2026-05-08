# Amendment AMD-2026-05-09-01 - SM-05 Executor Shadow-Mode Polling Design Draft

**對應 spec**: proposed SM-05 · DOC-01 §5.3 / §5.6 / §5.10 / §5.11 · EX-06
**日期**: 2026-05-09
**作者**: PM
**狀態**: Draft / BLOCKED by `P0-DECISION-AUDIT-2`
**索引**: `SPECIFICATION_REGISTER.md` Amendments section
**TODO 連結**: `W-AUDIT-3` / `P1-AUDIT-RUNTIME-3` / `F-spec-SM05`

---

## 1. Purpose

This draft closes the narrow W-AUDIT-3 documentation gap for
`ExecutorConfigCache.shadow_mode_provider()` polling behavior.

It does **not** decide the unresolved authority question:

- Option A: `executor.shadow_mode=true` is a temporary W-A demo fail-close
  posture; after `P0-EDGE-1`, demo may flip to `false` to enable supervised
  shadow-to-submit promotion.
- Option B: the local 5-Agent Executor path is permanently shadow-only
  observation; real order submission always flows through Rust `tick_pipeline`.

That decision remains `P0-DECISION-AUDIT-2` and must be operator-selected
before this draft can become active SM-05 authority policy or before F-01
removes the `ExecutorAgent` fail-closed fallback.

---

## 2. Current Implementation Facts

Confirmed source behavior as of 2026-05-09:

1. Rust `RiskConfig.executor.shadow_mode` is the source of truth for the
   Python `ExecutorAgent` submit-vs-shadow decision.
2. Python `ExecutorConfigCache` is a read-only cache of the Rust
   `executor` sub-config, fetched through IPC method `get_risk_config`.
3. Polling starts only when lifecycle wiring calls `start_polling()`.
   The singleton getter does not auto-start polling.
4. The cache performs an eager first poll, then repeats every
   `OPENCLAW_EXECUTOR_CACHE_POLL_SEC` seconds.
5. Poll interval default is `10.0s`; values below `0.5s` are clamped.
6. Cache engine selection is `OPENCLAW_ENGINE_MODE`, then
   `OPENCLAW_EXECUTOR_CACHE_ENGINE`, then `paper`.
7. Before first successful IPC fetch, the cache snapshot is fail-closed:
   `shadow_mode=True`.
8. If IPC fails before first success, the cache keeps the fail-closed default.
9. If IPC fails after first success, the cache retains the last known good
   snapshot.
10. Missing or malformed `executor` schema is treated as a failed fetch by the
    poller; the cache does not silently convert malformed data into live submit.
11. `ExecutorAgent._read_shadow_mode(engine)` catches provider exceptions and
    fails closed to `shadow_mode=True`, so submit is suppressed on provider
    failure.
12. `ExecutorAgent.get_executor_snapshot()` and `get_stats()` call the provider
    outside `self._lock` to avoid lock inversion with `ExecutorConfigCache`.

---

## 3. Draft SM-05 Requirements

Until `P0-DECISION-AUDIT-2` is resolved, SM-05 is limited to these
implementation invariants:

1. `ExecutorConfigCache` is a Python read mirror, not a writable authority.
2. Cache miss, IPC failure, schema failure, or provider exception must not
   enable order submission.
3. Provider calls from `ExecutorAgent` must stay outside `ExecutorAgent` locks.
4. The cache may retain a last known good snapshot after transient IPC failure,
   but it may not invent a `shadow_mode=false` value.
5. `lambda: True` in `ExecutorAgent.__init__` is an unresolved F-01 fallback,
   not final SM-05 authority semantics.
6. TOML values `risk_config_{paper,demo,live}.toml [executor].shadow_mode`
   remain effective runtime policy until the operator resolves
   `P0-DECISION-AUDIT-2`.
7. `shadow_mode=false` is never a live authorization grant by itself. Live
   still requires the existing live gate chain, signed authorization, secrets,
   Decision Lease, risk gates, and Rust execution authority.

---

## 4. Known Unsettled Edge

`governance_lease_bridge.shadow_short_circuit_acquire()` currently treats a
`shadow_mode_provider` exception as non-shadow, so the lease path does not hide
real lease failures behind a shadow bypass. The later Executor submit path still
fails closed to shadow if the provider raises.

This means a provider exception can surface a lease attempt while the order
submit remains suppressed. That behavior is acceptable only as a transitional
diagnostic posture. Final SM-05 must choose one of:

- Option A: make provider injection fail-loud for production `ExecutorAgent`
  wiring and remove the `lambda: True` fallback.
- Option B: formally declare the 5-Agent Executor path shadow-only and keep
  lease bypass semantics as observation, not submit authority.

---

## 5. Acceptance Before Active SM-05

SM-05 may be promoted from Draft to Active only after:

1. Operator resolves `P0-DECISION-AUDIT-2`.
2. F-01 implementation matches that decision.
3. E2 confirms no hidden path can turn provider failure into submit authority.
4. E4 regression covers provider success, pre-init failure, post-init failure,
   malformed schema, and explicit per-engine lookup.
5. TODO and CLAUDE wording are updated from "draft / blocked" to the selected
   authority model.

---

## 6. Boundary

This amendment is documentation only. It does not rebuild, restart, mutate
runtime env, change TOML risk config, enable true live, grant Executor order
authority, alter scanner evidence semantics, unlock MAG-083, or sign MAG-084.

---

*OpenClaw / Arcane Equilibrium Governance Amendment - AMD-2026-05-09-01*
