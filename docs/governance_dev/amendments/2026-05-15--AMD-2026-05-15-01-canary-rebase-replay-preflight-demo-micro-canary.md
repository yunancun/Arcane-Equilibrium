# Amendment AMD-2026-05-15-01 — Canary Rebase: Replay Preflight + Demo Micro-Canary

**對應 spec**: W-AUDIT-9 · SM-05 · DOC-01 §5.5/§5.6/§5.11 · DOC-08 §12 · ARCH-04
**修訂對象**: AMD-2026-05-09-03 graduated canary default + AMD-2026-05-10-04 TOML drift SOP
**Supersedes**:
- AMD-2026-05-09-03 §2.2/§2.3 中 `Stage 1 = Environment::Paper × 7d`
- AMD-2026-05-09-03 §6.2 中 Stage 1 paper worst-case reasoning
- AMD-2026-05-10-04 §2.1/§2.2/§3.1 中「Sprint N+1 W3 paper Stage 1 cohort」啟動流程
- A4-C spec/report 中把 D+12 paper edge report 當 promotion gate 的字面語義

**日期**: 2026-05-15
**作者**: PM applying operator-approved PM+PA+FA decision
**狀態**: Accepted — planning authority; source/runtime follow-up gates remain required
**索引**: `docs/governance_dev/SPECIFICATION_REGISTER.md` Amendments section
**TODO 連結**: W-AUDIT-9 · W-AUDIT-8d A4-C · P1-W-AUDIT-3b-SMOKE · P1-HEALTHCHECK-55-INVARIANT

---

## 1. Executive Decision

Paper is no longer an admissible promotion evidence lane.

`Environment::Paper × 7d` is removed from W-AUDIT-9 Stage 1. The replacement is:

1. **Stage 0R Replay Preflight** — no orders, no runtime authority, advisory only.
2. **Stage 1 Demo micro-canary** — 1 strategy × 1 symbol × `Environment::Demo` × 7d, small position envelope, strict rollback.

Stage numbering remains otherwise unchanged:

| Stage | Revised meaning | Promotion authority |
|---|---|---|
| Stage 0 | Shadow / fail-closed baseline | none |
| Stage 0R | Replay Preflight sanity gate | `eligible_for_demo_canary=true/false` only; never `Stage 1 PASS` |
| Stage 1 | Demo micro-canary, 1 strategy × 1 symbol × 7d | empirical demo evidence only |
| Stage 2 | Demo extended single/cohort stage, 14d | must enter from Stage 1 demo evidence |
| Stage 3 | Demo full-universe stage, 21d | must enter from Stage 2 demo evidence |
| Stage 4 | LIVE_PENDING | operator + live boundary 5-gate + supervised-live SM |

---

## 2. Removed Path

### 2.1 Removed: Stage 1 Paper Cohort

The old Stage 1 definition is invalid:

> 1 strategy × 1 symbol × `Environment::Paper` × 7d

Reasons:

- Current runtime posture keeps paper disabled by default (`OPENCLAW_ENABLE_PAPER != 1`).
- Paper does not exercise the demo/live exchange path, order lifecycle, real fee source, slippage, Bybit reject shape, Decision Lease timing, or fill-lineage pressure.
- A paper PASS can create false confidence while leaving the exact demo canary risk unmeasured.

### 2.2 Blocked: `OPENCLAW_ENABLE_PAPER=1`

Any plan, script, env file, restart, or operator runbook that sets `OPENCLAW_ENABLE_PAPER=1` for promotion evidence is **BLOCKED**.

Allowed residual use is narrow: legacy diagnostics may stay read-only and explicitly marked non-promotional. They cannot unblock demo, live_demo, mainnet, Stage 1, Stage 2, or A4-C promotion.

---

## 3. New Stage 0R — Replay Preflight

Stage 0R is inserted between Stage 0 and Stage 1 as a **preflight**, not as a numbered promotion stage.

### 3.1 Scope

Replay Preflight may use the existing replay engine, historical/counterfactual panels, and offline report tooling to answer:

- leak / lookahead sanity
- bias / selection-bias sanity
- DSR / PSR / PBO / bootstrap sanity
- regime and symbol-cohort sanity
- A4-C lead-lag decay sanity (`N=60/120/300` or successor spec)

### 3.2 Output Contract

Stage 0R output is a boolean plus evidence packet:

```text
eligible_for_demo_canary = true | false
reasons = [...]
evidence_refs = [...]
```

Stage 0R must not emit:

- `Stage 1 PASS`
- `auto_promote`
- `canary_stage_log.to_stage = 1`
- any order, fill, strategy/risk TOML mutation, or live/demo auth mutation

### 3.3 Minimum Sanity Checks

The preflight must fail closed if any of the following is missing or failing:

| Check | Required result |
|---|---|
| Leak / lookahead | PASS; rolling/window features use strict prior-bar/prior-tick semantics |
| Bias / selection | PASS or explicit QC waiver; no cherry-picked symbol-only promotion |
| DSR / PSR | Sane under deflated K and skew/kurt-aware PSR where applicable |
| PBO / bootstrap | No high-PBO or unstable bootstrap lower-tail rejection |
| Replay data tier | ML/training surfaces exclude synthetic-only replay rows |
| Runtime boundary | No claim that replay substitutes for demo fill-lineage, Decision Lease, or exchange-path evidence |

### 3.4 Acceleration Rule

When a task would otherwise wait 24h/72h/96h, PM may ask whether replay can accelerate **preflight sanity**. Replay cannot accelerate wall-clock demo evidence, fill-lineage evidence, or Stage 1/2 empirical promotion windows.

---

## 4. Revised Stage 1 — Demo Micro-Canary

### 4.1 Stage 1 Definition

Stage 1 is now:

> 1 strategy × 1 symbol × `Environment::Demo` × 7d

This is the first stage that may produce promotion evidence. It must start from:

1. Stage 0 baseline intact.
2. Stage 0R `eligible_for_demo_canary=true`.
3. Operator-approved cohort.
4. W-AUDIT-3b runtime smoke PASS.
5. `[55]` fill-lineage invariant evidence available.
6. Valid Decision Lease / Guardian / SM-04 / StopManager boundaries.

### 4.2 Small Position Envelope

Stage 1 must not raise risk sizing. The canary envelope is the most conservative of:

- current demo RiskConfig limits,
- the strategy/symbol canary cap,
- exchange minNotional / qty-step feasibility,
- any LG-2 provider-pricing freshness cap.

If exchange minNotional would force size above the canary cap, the correct behavior is **no order / fail closed**, not cap override.

### 4.3 Demo Evidence Requirements

Stage 1 can only be considered complete after the 7d demo window produces real demo-path evidence:

- nonzero eligible strategy decisions for the cohort,
- nonzero fill / reject / no-fill accounting with reconstructable lineage,
- Decision Lease or explicit deny lineage for every executable intent,
- Guardian verdict lineage,
- ExecutionReport / fill evidence for every filled order,
- no boundary violation,
- rollback metrics below trip thresholds.

### 4.4 Strict Rollback

Any of the following rolls Stage 1 back to Stage 0:

- SM-04 escalate ≥ L3,
- invalid/expired relevant authorization boundary,
- Decision Lease IPC failure rate above the configured Stage 1 threshold,
- Guardian hard veto unexpectedly bypassed,
- pricing/fee source missing where required,
- `[55]` fill-lineage invariant FAIL,
- `[58]` canary stage invariant FAIL,
- realized-edge hard FAIL for the cohort after minimum sample maturity,
- order/fill evidence cannot be reconstructed.

---

## 5. Stage 2 Entry Condition

Stage 2 numbering and broad meaning stay unchanged, but entry condition is narrowed:

> Stage 2 must be entered from Stage 1 **demo empirical evidence**.

Not admissible as Stage 2 entry evidence:

- Stage 0R replay preflight,
- A4-C paper-edge report,
- paper fills / paper PnL,
- synthetic replay rows,
- static code review alone,
- low-sample realized edge without lineage.

Stage 2 can still use replay reports as supporting diagnostics, but the promotion decision must cite the Stage 1 demo canary evidence packet.

---

## 6. A4-C Rebase

A4-C BTC→Alt Lead-Lag remains a valid alpha candidate, but its promotion path changes:

- The D+12 paper edge report is downgraded to **diagnostic/read-only**.
- A4-C must pass Stage 0R replay preflight before demo canary.
- A4-C promotion requires Stage 1 demo micro-canary evidence.
- Any A4-C spec text that says paper evidence can promote to demo must be amended.

The old `OPENCLAW_ENABLE_PAPER=1` producer fence remains useful as a blocking signal: production/demo runtime must not enable paper as a promotion workaround.

---

## 7. Required Pre-Launch Gates

Before any demo Stage 1 canary starts:

| Gate | Required evidence |
|---|---|
| W-AUDIT-3b runtime smoke | `ssh trade-core` RouterLeaseGuard Drop test + fail-closed pytest + runtime proof |
| `[55]` fill-lineage invariant | `chains_with_lease > 0` plus fill evidence availability; no known silent-drop blocker |
| `[58]` canary invariant | active and PASS/WARN-free for the target stage config |
| Stage 0R replay preflight | `eligible_for_demo_canary=true` with evidence refs |
| Cohort approval | operator-approved strategy × symbol; no funding_arb or retired/frozen strategy |
| Risk envelope | no TOML risk raise; small-position cap documented |

---

## 8. Non-Goals

This amendment does not:

- approve true-live, LiveDemo relaxation, Mainnet, Stage 3, or Stage 4,
- mutate live auth,
- weaken DOC-08 §12, SM-04, Guardian, Decision Lease, StopManager, or the live boundary 5-gate,
- authorize `OPENCLAW_ENABLE_PAPER=1`,
- make replay a substitute for runtime lineage.

---

## 9. Sign-Off

| Role | Date | Status |
|---|---|---|
| Operator | 2026-05-15 | Accepted execution request |
| PM | 2026-05-15 | Implementing governance rebase |
| PA | 2026-05-15 | Prior PM+PA+FA analysis approved by operator |
| FA | 2026-05-15 | Prior PM+PA+FA analysis approved by operator |

PM sign-off remains conditional on Step 3 runtime smoke and Step 4 `[55]` fill-lineage invariant evidence before any demo canary launch.
