# V3 -> V5.8 Route Coverage Audit

**Date**: 2026-05-25  
**Owner**: PM  
**Scope**: v3 through v5.8 planning documents, v5.7/v5.8 active execution plan, PM final verdict, and TODO v64 active overlay.  
**Question**: Does the final v5.8 execution plan cover all route changes and the resulting development plan, or are there still omissions?

---

## 1. Executive Verdict

**Verdict**: **MOSTLY COVERED AS AN INTEGRATED ROUTE, NOT SELF-CONTAINED IN THE SINGLE v5.8 FILE.**

If "v5.8 execution plan" means only:

- `docs/execution_plan/2026-05-20--execution-plan-v5.8.md`

then the answer is **NO**: it is not a standalone complete final development plan. The file explicitly says v5.8 **does not supersede v5.7** and is the autonomy track layered on top of v5.7. Therefore, any check that reads v5.8 alone will miss v5.7 Sprint 1A/1B, C10, Earn, five-strategy roster, and several post-2026-05-21 runtime decisions.

If "final route" means the active integrated route:

- `docs/execution_plan/2026-05-20--execution-plan-v5.7.md`
- `docs/execution_plan/2026-05-20--execution-plan-v5.8.md`
- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-21--v58_pm_final_verdict.md`
- `TODO.md` v64 active overlay

then the answer is **YES for strategic route coverage**, with **active implementation/runtime gaps tracked outside v5.8**. I did not find an unaccounted strategic route change from v3-v5.8 that requires stopping or redesigning the current route. I did find several items that must remain explicit overlays because they happened after v5.8 or were intentionally deferred.

---

## 2. Source Map

### Historical route files reviewed

| Version | File | Route status |
|---|---|---|
| v3 | `docs/archive/2026-05-21--srv_root_cleanup/2026-05-20--lean-direct-alpha-capture-v3.md` | Superseded. Direct alpha/cash urgency framing. |
| v4 | `docs/archive/2026-05-21--srv_root_cleanup/2026-05-20--dual-track-architecture-v4.md` | Superseded. Dual-track ASDS + Direct Exploit. |
| v4.1 | `docs/archive/2026-05-21--srv_root_cleanup/2026-05-20--dual-track-architecture-v4.1.md` | Superseded. Reviewer corrections. |
| v4.2 | `docs/archive/2026-05-21--srv_root_cleanup/2026-05-20--dual-track-architecture-v4.2.md` | Superseded. Second audit corrections. |
| v4.3 | `docs/archive/2026-05-21--srv_root_cleanup/2026-05-20--commercial-evidence-sprint-v4.3.md` | Superseded. Commercial evidence sprint; IP-sale path later retracted. |
| v4.4 | `docs/archive/2026-05-21--srv_root_cleanup/2026-05-20--execution-plan-v4.4.md` | Superseded by v5.0. Copy/bootstrap path. |
| v5.0 | `docs/archive/2026-05-21--srv_root_cleanup/2026-05-20--execution-plan-v5.0.md` | Superseded. 11-round audit truth; killed NLE/LCS. |
| v5.2 | `docs/archive/2026-05-21--srv_root_cleanup/2026-05-20--execution-plan-v5.2.md` | Superseded. Adaptive strategy lab. |
| v5.3 | `docs/archive/2026-05-21--srv_root_cleanup/2026-05-20--execution-plan-v5.3.md` | Superseded. Engineering/gate corrections. |
| v5.4 | `docs/archive/2026-05-21--srv_root_cleanup/2026-05-20--execution-plan-v5.4.md` | Superseded. Two-account/copy route. |
| v5.5 | `docs/archive/2026-05-21--srv_root_cleanup/2026-05-20--execution-plan-v5.5.md` | Superseded. Self-trading primary. |
| v5.6 | `docs/archive/2026-05-21--srv_root_cleanup/2026-05-20--execution-plan-v5.6.md` | Superseded by v5.7. Bybit framework + Earn + macro/on-chain. |
| v5.7 | `docs/execution_plan/2026-05-20--execution-plan-v5.7.md` | Active dispatch-of-record for Sprint 1A. |
| v5.8 | `docs/execution_plan/2026-05-20--execution-plan-v5.8.md` | Active autonomy expansion; supplements v5.7. |

### Active state files reviewed

| File | Relevance |
|---|---|
| `TODO.md` | Active v64 dispatch/runtime overlay. |
| `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-21--v58_pm_final_verdict.md` | PM integrated verdict for v5.7 + v5.8. |
| `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-25--sprint_1a_1b_recheck.md` | Current implementation/runtime reality referenced by TODO v64. |

---

## 3. Route Change Coverage Matrix

| Route change | Origin | Final handling | Coverage verdict |
|---|---|---|---|
| Stop building academic ASDS first; prioritize direct alpha and cashflow urgency | v3 | Preserved as self-trading primary, five-strategy portfolio, Alpha Tournament, C10/Earn first practical deliverables | Covered |
| NLE/LCS as first lean alpha candidates | v3/v4.2/v4.3 | Explicitly killed by v5.0 audit: LCS insufficient data/no precedent; NLE fee/no-edge. v5.8 M4/M10 may rediscover similar candidates only as DRAFT/new-source evidence, not as committed route | Covered as rejected, not missing |
| Dual-track ASDS + Direct Exploit | v4-v4.2 | Superseded by v4.3/v5.x. Track/factory framing replaced by self-trading/adaptive discovery | Covered as superseded |
| Commercial evidence sprint / monetization / IP sale | v4.3-v4.4 | IP sale retracted by v4.4; later v5.x locks no content/subscription monetization and Copy Trading evidence-gated only | Covered as rejected/deferred |
| Copy Trading subaccount as early path | v4.4-v5.4 | v5.5+ changed to single-account self-trading primary; Copy Trading only evidence-gated/moat-gated Y1/Y2 decision | Covered |
| Accept realistic retail ceiling / stop fantasy layering | v5.0 | v5.6/v5.7 honest APR, Y1/Y2 outcome, and P0 gates preserve this | Covered |
| Aggressive but long-lasting/adaptive learning route | v5.2 | v5.8 M1-M13 autonomy expansion is exactly this layer | Covered |
| Engineering underestimation / paper-gate governance issue | v5.3 | v5.7 Sprint split + v5.8 §3.5 true hours, GUI/TW/MIT/A3/AI cost add-backs | Covered |
| Two-account Copy architecture | v5.4 | Superseded by v5.5 single-account full stack; Copy infra later only if evidence gate passes | Covered as rejected |
| Self-trading primary + Copy Trading evidence gate | v5.5 | v5.6/v5.7/v5.8 preserve it | Covered |
| Bybit Primary + Earn cash management + macro/on-chain framework | v5.6 | v5.7 corrects Earn APR, Earn movement governance, macro/on-chain counterfactual-only Y1, existing liquidation writer | Covered |
| v5.6 engineering precision drift fixes | v5.7 | v5.7 is active dispatch-of-record | Covered |
| 13-module autonomy expansion | v5.8 | v5.8 contains M1-M13, but only as design/phase plan. Several implementations are explicitly deferred | Covered as design, not implementation complete |
| Missing M14/M15/M16 from PM verdict | PM verdict | TODO v64 §5.2 records disposition: M14 hot-swap deferred v5.9; M15 folded into M6 acceptance; M16 folded into M1/LAL acceptance | Covered outside main v5.8 file |
| Sprint 2 naming ambiguity | TODO v64 | v64 disambiguates support sprints from v5.8 business Sprint 2 | Covered outside main v5.8 file |
| 2026-05-25 runtime hygiene/proc-exe/Earn/Phase 2a changes | TODO v64 | Active runtime overlay, not in v5.8 because it post-dates v5.8 | Covered outside main v5.8 file |

---

## 4. Actual Omissions / Gaps

These are not "lost strategy route" omissions, but they are real planning/documentation gaps if someone treats v5.8 as the only final plan.

### Gap A: v5.8 is not standalone

v5.8 says:

- Status: design complete, supplements v5.7
- Supersedes: none
- v5.7 remains dispatch-of-record for Sprint 1A

Therefore the final plan must be read as **v5.7 + v5.8**, not v5.8 alone.

**Impact**: Anyone dispatching from only v5.8 will miss C10, Earn, v5.7 Sprint 1A/1B, and five-strategy income assumptions.

**Recommendation**: Add a short "Route Authority" appendix to v5.8 or create v5.8.1 that says: "Authoritative plan = v5.7 + v5.8 + TODO active overlay."

### Gap B: M14/M15/M16 disposition is not in the v5.8 module roster

PM final verdict originally found three missing autonomy surfaces:

- M14 strategy hot-swap
- M15 capacity-aware sizing
- M16 cross-strategy correlation re-sizing

TODO v64 resolves them:

- M14 defer to v5.9
- M15 fold into M6 acceptance
- M16 fold into M1/LAL acceptance

**Impact**: Not a blocker, but hidden if only v5.8 is read.

**Recommendation**: v5.8 appendix or v5.8.1 should add "Non-module dispositions" so future audits do not re-open this.

### Gap C: Post-v5.8 runtime overlays are not in v5.8

TODO v64 has active state that post-dates v5.8:

- business Sprint 2 not started
- Phase 2a/P0-EDGE-1 verdict path changed
- runtime hygiene/proc-exe drift and build-lock follow-up
- Earn first stake still blocked by operator/key/endpoint/IP actions
- C10 7d demo observation runs until 2026-06-01
- close-maker/edge snapshot/cron follow-ups

**Impact**: Not a v5.8 design miss, but a live execution miss if the plan is read without TODO.

**Recommendation**: Treat TODO v64 as the active execution overlay; do not backport all runtime deltas into v5.8 unless creating v5.8.1.

### Gap D: V### schema status is mixed design/spec/runtime

v5.8 explains V105-V116 as spec/reserve work. TODO v64 shows the live PG state has advanced for some migrations, while several remain design/spec or later work.

**Impact**: This is easy to misread as "all migrations planned = all migrations implemented." They are not the same.

**Recommendation**: Keep each V### item tagged with one of: SPEC, SQL-LANDED, PG-APPLIED, RUNTIME-PROVEN.

### Gap E: Business Sprint 2 has not started

v5.8 §4 business Sprint 2 is:

- Alpha Tournament
- M4 stage 1
- M10 Tier A
- M8 read-only

TODO v64 marks it **NOT STARTED** and blocked by P0-EDGE-1 Phase 2a verdict plus runtime hygiene.

**Impact**: The project is not yet at the core v5.8 "new source / Alpha Tournament" loop. The path exists, but effects are not achieved yet.

**Recommendation**: Before claiming v5.8 route is operational, dispatch business Sprint 2 only after P0-EDGE-1 decision and runtime hygiene closure.

---

## 5. Higher-Level Product Reality Check

The current route still matches the real project need:

1. **Profit realism**: v5.0 killed unsupported NLE/LCS/aggressive layering, v5.7/v5.8 retain honest APR and live gates.
2. **Survival**: Bybit primary, no withdrawal keys, off-exchange buffer, 5-gate live boundary, P0 blockers remain explicit.
3. **Near-term practical build**: C10, Earn, sensors, and governance are front-loaded instead of chasing speculative full autonomy first.
4. **Long-term autonomy**: M1-M13 cover the intended 21-32 month path to 90-95% autonomy.
5. **Learning loop**: M4/M10/M11 provide a path to new alpha without reviving killed candidates by hand-waving.

The real concern is not strategic coverage. The real concern is **execution discipline**:

- Do not treat DESIGN-DONE as IMPL-DONE.
- Do not treat source-landed as runtime-proven.
- Do not let post-v5.8 TODO overlays drift outside the dispatch chain.
- Do not re-open killed v3 candidates unless M4/M10 produces fresh DRAFT evidence and preregistration.

---

## 6. PM Decision

**No immediate redesign required.**

The final route should be represented as:

```text
Route-of-record = v5.7 dispatch plan
                + v5.8 autonomy expansion
                + 2026-05-21 PM final verdict dispositions
                + TODO v64 active runtime/dispatch overlay
```

The single v5.8 file is **not** sufficient as the only source of truth. The safest next documentation action is either:

1. create `v5.8.1` as a route-authority appendix, or
2. add a compact appendix to v5.8 pointing to v5.7 + PM verdict + TODO v64 and listing M14/M15/M16 + post-v5.8 overlays.

Until then, no route-changing omission is blocking, but there is a **documentation authority gap** that can cause future dispatch mistakes.
