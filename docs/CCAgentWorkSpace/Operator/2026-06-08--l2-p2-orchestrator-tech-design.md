# L2 Advisory Mesh — Phase 2 (Orchestrator + Registry + Contracts + Guard + Admission + Adjudication) Technical Design

Date: 2026-06-08
Author: PA (Project Architect)
Status: **E1-READY (design-only)** — no feature code, no migration apply, no DB write, no deploy in this pass. This is the **CC linchpin phase** (no-auto-path-to-live compliance centre). Every assertion grounded in `file:line`.
Owner chain (this phase): PM → **PA (this doc)** → E1/E1a → E2 → **CC (load-bearing stress-tests 5/6/10/15/16/18)** → E3 (E1 write-auth + fail-safe) → E4 → QA → PM.
SSOT design: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-05--l2-advisory-mesh-design-draft.md` (v4-final, 4-review-passed) — §A.1, §B, §C/C.2/C.3, §E, §F/F.1/F.2, §K, §L.
Execution plan: `docs/execution_plan/2026-06-05--l2-advisory-mesh-execution-plan.md` §2 Phase 2 (lines 125-165) + §1 gating ledger + §3 cross-phase invariants.
P1 D3 design (writer interface this phase wires): `docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-08--l2-d3-phase1-tech-design.md`.
Branch `feature/l2-critic-lessons-tools` @ `f1c3c1ca` (P1 D3 landed: V134/V135/V136 + `l2_call_ledger_writer.py` + `l2_secret_redactor.py` + 78 tests).

This document does **not** re-litigate the v4-final design. It grounds every Phase-2 assertion in `file:line`, gives E1 a module-by-module executable spec, and — most importantly — designs the **CC-grep-verifiable carbon-layer invariants** (LANE_DIRECTION, C1, C2, F.2-no-model-adjudication, fail-safe) as **one-line / single-construct properties CC can grep**, not emergent properties of a config lattice.

---

## 0. Read-before-build clearance — every §0 needs-verification item CLEARED with file:line

I read the source before designing. The execution-plan §0 (lines 21-55) binding preconditions for P2, now grounded:

| Item | Finding | Ground |
|---|---|---|
| **Next free migration number** | **P1 already consumed V134/V135/V136** (they are on disk at `f1c3c1ca`). The execution-plan §0 "V13x = next free after V134" is now stale; the real next-free for any P2 table is **V137**. Verified no V137+ exists. | `ls sql/migrations/` → `V134__l2_calls_ledger.sql`, `V135__l2_gate_seam_log.sql`, `V136__l2_provenance_columns.sql` present; `V13[7-9]`/`V14*` = **0 hits**. (P2's `learning.l2_promote_candidates` is a **P5** concern per execution-plan §2 line 286 — **NOT created in P2**; see §L.) |
| **P1 D3 writer interface (the thing P2 wires)** | `L2CallLedgerWriter` is a process-global module-level singleton with **three INSERT-only public entries** and a `get_l2_call_ledger_writer()` accessor. Already registered in singleton SSOT §2.6.1. | `l2_call_ledger_writer.py:99` (class), `:113` `record_l2_call(...)`, `:266` `record_consequential_mark(...)`, `:314` `record_gate_seam(...)`, `:367` `get_l2_call_ledger_writer()`. Registry: `docs/architecture/singleton-registry.md:351`. |
| **Existing manual-trigger flow (the Orchestrator's seam)** | `POST /api/v1/paper/layer2/trigger` → `Layer2Engine.run_session(trigger="manual")`; recommendation → `ShadowDecisionConsumer`; `is_simulated=True` invariant. **The engine already mints a root `l2_reply_id` and writes the D3 ledger per call.** | `layer2_routes.py:234` (`trigger_l2_session`), `:247` `require_scope_and_operator(actor,"ai_budget:write")`; `layer2_engine.py:522` `run_session(...,trigger="manual")`, `:119` `is_simulated=True`, `:352` `writer.record_l2_call(...)`. |
| **D3 write already wired at engine layer** | The engine's `_record_l2_call_to_ledger` (the seam at `:337`) already calls `record_l2_call(...)` with **hardcoded** `capability_id=L2_DEFAULT_CAPABILITY_ID`, `contract_ver=L2_PROMPT_CONTRACT_VER`, `schema_ver=L2_OUTPUT_SCHEMA_VER`. **P2's wiring change = make these registry/contract-driven, not hardcoded.** | `layer2_engine.py:89-92` (the three constants), `:355/:359/:360` (the hardcoded args). |
| **GovernanceHub read-only surface the Orchestrator may call** | `GovernanceHub` exposes **read** projections of tier/capability state with **no trading-lease acquisition**: `get_learning_tier_status()`, `check_learning_tier_capability()` (deprecated RC-11), `set_learning_tier_gate()` (injection, not Orchestrator-callable for raising). The gate itself is injected at boot. | `governance_hub.py:341` `get_learning_tier_status()`, `:314` `check_learning_tier_capability()`, `:293` `set_learning_tier_gate()`. Wiring: `paper_trading_wiring.py:374` `LearningTierGate(...)` → `:376` `GOV_HUB.set_learning_tier_gate(...)`. |
| **`promote_tier` auto-raises L1→L4 with no `approved_by`** (the C1 hazard) | **VERIFIED.** `promote_tier(target_tier, initiator="LearningGate", reason="", approved_by=None)` — only L5 requires `approved_by` (`:550`); L2/L3/L4 emit `AUTO_PROMOTE_*` events with `approved_by=None`. A careless Orchestrator call would silently raise the tier. | `learning_tier_gate.py:520` (def), `:525` (`approved_by: str | None = None`), `:550-553` (only L5 guard), `:570-574` (AUTO_PROMOTE L2/L3/L4 events). |
| **`can_auto_deploy_to_paper=True@all-tiers`** (the C2 no-signal hazard) | **VERIFIED.** `True` at L1-L5; carries **no** auto-vs-manual signal — only "permitted to touch paper/demo lane." | `learning_tier_gate.py:185` (L1), `:196` (L2), `:205` (L3), `:218` (L4), `:231` (L5); property `:660-662`. |
| **`can_modify_live_config=False@all-tiers`** (the live hard line, already in code) | **VERIFIED.** Returns literal `False`, "Immutable across all tiers per EX-05 §8.2". | `learning_tier_gate.py:178` (default field), `:664-671` (property returns `False`). |
| **Operator-scope WRITE precedent (E3-E1 + C1 promote-confirm)** | **Two grounded patterns.** (1) `Depends(_require_operator_auth)` is the documented "standard Depends() target for all write/state-change endpoints." (2) the autonomy switch route `@governance_router.post("/autonomy-level/switch")` adds **TOTP** + advisory-lock + cooldown — the pattern the C1 promote-confirm reuses. | `governance_routes.py:129-152` `_require_operator_auth` (docstring: "standard Depends() target for all write/state-change endpoints"); `governance_autonomy_service.py:598-601` `switch_autonomy_level(..., actor=Depends(_require_operator_auth))`; TOTP `:41-43`, advisory-lock+FOR UPDATE switch `:447` `_perform_autonomy_switch`. |
| **`_AUTONOMY_PATH_MATRIX` (extend, do not fork — §C)** | `list[dict[str,str]]`, rows (a)-(j)+venue, each `{id,path,category,level1,level2}`. The tighten/loosen asymmetry is **already half-present**: kill-criteria (e)/health-degradation (j) = `auto-trigger` both levels (contract); promotions (a)/(c)/(d) = `operator manual` at level1 (expand). | `governance_autonomy_service.py:80` (matrix), `:116-130` (rows), `:120` (e auto-trigger), `:125` (j auto-trigger), `:116/:118/:119` (a/c/d operator manual). |
| **`/cost/reset` + `/cost/pricing` POST exist (E3-E1 targets) — already operator-scope** | **VERIFIED.** Both exist and **already** call `require_scope_and_operator(...,"ai_budget:write")`. So E3-E1 for these two is **confirmation, not new addition**; only the *new* Orchestrator/registry mutation routes need fresh hardening. | `layer2_routes.py:354` `POST /cost/reset`, `:389` `POST /cost/pricing`; the L2-route operator helper `require_scope_and_operator` (`main_legacy.py:554` `current_actor`). |
| **RiskConfig TOML-as-SSOT precedent (registry default TOML)** | TOML SSOT loaded at runtime is the repo norm; `risk_config.toml` is the canonical example. | `settings/risk_control_rules/risk_config.toml` (+ `_paper`/`_live` variants); priority order "runtime RiskConfig TOML > Rust schema" (16-root-principles skill). |
| **`extra="forbid"` unknown-field-reject precedent (registry loader)** | Pydantic `ConfigDict(extra="forbid")` is an existing pattern — reuse for "unknown field → reject load." | `agent_contracts.py:109` `model_config = ConfigDict(extra="forbid")`; also `scanner_advisory_contracts.py`, `strategist_decision_v2.py`. |
| **DOC-08 $2/day envelope (admission budget gate)** | Hard cap `daily_usd_max = 2.0`; the existing `check_daily_budget()` is the budget gate the admission stage reuses. | `settings/risk_control_rules/budget_config.toml:9` (`daily_usd_max = 2.0`); `layer2_cost_tracker.py:24` (DOC-08 §4), `:286` `check_daily_budget()`. |
| **Greenfield check (the ~30% net-new)** | `l2_capability_registry`, `LANE_DIRECTION`, `L2AdvisoryOrchestrator`, an admission stage, a conflict-adjudication table = **0 hits** (greenfield). (The only `debounce` hit is the unrelated `experiment_ledger.py` auto-save.) | grep `l2_capability_registry|LANE_DIRECTION|L2AdvisoryOrchestrator|class.*Admission|class.*Adjudicat` over `control_api_v1/app/*.py` → 0 (excl. `experiment_ledger.py:267` auto-save debounce). |

**Single most important correction to the execution-plan text:** plan §0 (line 23) and design §0 (line 291) say "V134 is next free" / "V13x next free after V134." **That is now stale** — V134/V135/V136 are landed (P1). Any P2 migration is **V137**. But (see §L) **P2 needs no migration** — the registry is TOML-SSOT and admission/adjudication state is in-memory + logged to the **existing** D3 gate-seam log. So the V137 question is **moot for P2 unless the operator reopens DB-backed runtime registry overrides** (then V137; see §L).

---

## A. `L2AdvisoryOrchestrator` singleton — the conductor

### A.1 What it is / is NOT

A runtime **async scheduler/dispatcher singleton** that owns the loop `trigger → admission → capability dispatch → PromptContract → out-of-bound guard → D3 write → result routing (proposal into existing gated pipeline)`. It is the **conductor** (root principle 15), **not** a sixth trading agent. Grounded against the existing manual-trigger flow (`layer2_routes.py:234` → `layer2_engine.py:522 run_session`) + the P1 D3 writer (`l2_call_ledger_writer.py:113`).

**Hard forbiddances (CC will grep each — design them as zero-reference properties):**

| Forbiddance | Why | CC grep target (must be 0 hits in the Orchestrator + its imported advisory-loop modules) |
|---|---|---|
| **No order authority** | root principle 1 (single write entry); L2 has no order path | `IntentProcessor`, `submit_intent`, the Rust IPC order surface (`place_order`, `/v5/order`) |
| **No lease authority (trading scope)** | root principle 3 (AI → lease → human, never direct) | `acquire_lease` for trading scope; lease *trading* authority |
| **No `promote_tier` / autonomy-raiser** [C1] | `promote_tier` auto-raises L1→L4 with no `approved_by` (`learning_tier_gate.py:520/550/570-574`) | `promote_tier`, any `set_autonomy_level`-style raiser, any trust-gate-removal writer |
| **No live-config write** | `can_modify_live_config=False@all-tiers` (`learning_tier_gate.py:664-671`) | `live_execution_allowed`, `max_retries`, `OPENCLAW_ALLOW_MAINNET`, `authorization.json`, `execution_authority`, `system_mode` |
| **No model-adjudication** [F.2] | §F.2 adjudication is table-driven | any code path where a model **output** decides between two proposals (see §G) |

**What it MAY do (read-only):** read GovernanceHub capability/tier projections (`governance_hub.py:341 get_learning_tier_status` / `:314 check_learning_tier_capability`), read lease/risk projections (no acquire). Own `Layer2Engine` as **one** of several executors (cloud-L2 capabilities); local-sentinel/Ollama-only capabilities never touch `Layer2Engine`.

### A.2 The dispatch loop (the load-bearing flow)

```
trigger fires (event | schedule | manual | threshold)
   │
   ▼  [§F.1 ADMISSION — deterministic, in code, BEFORE any model call]
   dedup → debounce → coalesce → budget(check_daily_budget) → tier/posture(derive §C.2)
   │  (anything dropped/coalesced → record_gate_seam(gate_id="admission", verdict, reason))
   ▼  survivors only
   capability dispatch (registry lookup: enabled? min_tier met? model_tier?)
   │  if tier_locked → log tier_locked, NO degraded run
   ▼
   PromptContract (deterministic versioned template — Ollama FORBIDDEN to generate it)
   │  contract_ver + schema_ver resolved from the registry/contract registry
   ▼
   executor (local_sentinel | ollama | cloud_l2 via Layer2Engine.run_session)
   │
   ▼  [§E OUT-OF-BOUND GUARD — deterministic, BEFORE a proposal is formed]
   guard(parsed_output) → verdict ∈ {pass, clamp, reject}
   │
   ▼  [D3 WRITE — P1 writer, MANDATORY, one row per call]
   get_l2_call_ledger_writer().record_l2_call(
       l2_reply_id, capability_id=<registry id>, trigger, created_at, model,
       contract_ver=<contract registry>, schema_ver=<schema registry>,
       system_prompt, input_context, raw_response, parsed_output,
       guard_verdict=<the §E verdict>, fact_inf_assm, tokens/cost/latency)
   │  (+ record_gate_seam per downstream deterministic gate as the artifact flows)
   ▼  [RESULT ROUTING — proposal into EXISTING gated pipeline, NEVER an effect]
   route to the lane-bound applier per §C table:
     neutral → research/hypothesis/replay sinks (existing requires_governance surface)
     contract → deterministic risk governor (advisory INPUT only; governor owns final number)
     expand → MANUAL (loader-enforced; structurally cannot auto-apply) — see §C/LANE_DIRECTION
```

**Why a new singleton (not extend `Layer2Engine`):** `Layer2Engine` is the *worker* for one deep-reasoning session (`layer2_engine.py:193`). The Orchestrator is the *conductor* across capabilities/triggers/budgets/lanes. Conflating them pushes scheduling/gating/fail-safe into the session worker and breaks route-thin discipline. The Orchestrator **owns** `Layer2Engine` as one executor.

**Wiring change from today (the key P2 delta):** today `layer2_engine.py:355/359/360` passes **hardcoded** `L2_DEFAULT_CAPABILITY_ID`/`L2_PROMPT_CONTRACT_VER`/`L2_OUTPUT_SCHEMA_VER` to `record_l2_call`. In P2, when the Orchestrator drives a capability-specific call, it passes the **registry's** `capability_id` + the **contract registry's** `contract_ver`/`schema_ver`. The existing manual-trigger path (`l2.manual_reasoning`) stays as a registered fallback capability — **no regression to the existing D3 wiring**.

### A.3 Singleton registration (mandatory before merge, CLAUDE.md §九)

Add to `docs/architecture/singleton-registry.md` §2.6 (the existing "L2 Advisory Mesh" section; §2.6.1 is already `L2CallLedgerWriter`) using the 12-column format. New §2.6.2:

| field | value |
|---|---|
| name | `L2AdvisoryOrchestrator` (module-level singleton + `get_l2_advisory_orchestrator()`) |
| type_signature | async scheduler/dispatcher singleton; holds registry handle + admission state + executor refs (`Layer2Engine`) |
| location | `control_api_v1/app/<new file>:LINE` (E1 fills) — co-locate near `layer2_engine.py` |
| owner_lifecycle | constructed at control_api boot; lives for process; **no live-trading lifecycle** |
| cross_task_pattern | conductor of the advisory loop; emits D3 writes via `L2CallLedgerWriter` |
| lock_primitive | per-capability in-process admission state (debounce/dedup windows); no DB lock |
| visibility | module-internal; public entries = `dispatch(trigger)` / read-only status |
| caller_chain | trigger surface (event/schedule/manual/threshold) → Orchestrator → executors → D3 |
| health_monitoring | recommend yes (a silent dispatch failure = no advisory; fail-safe = NO_ADVICE) |
| governance_authority | design v4-final §A.1 + this doc + execution plan Phase 2 |
| migration_plan | none (TOML SSOT registry; no DB table in P2) |

Two more sections (§K of this doc): `2.6.3` admission controller, `2.6.4` conflict-adjudication controller.

---

## B. `l2_capability_registry` — schema (TOML SSOT, no `autonomy_level` field)

A capability is the atomic unit the operator enables/tunes. **TOML is SSOT** (mirrors RiskConfig `settings/risk_control_rules/risk_config.toml`); a checked-in default TOML so the system boots with zero external state. **P2 ships NO DB table** for the registry (see §L; runtime overrides, if ever needed, are a future V137 decision).

```jsonc
// one stanza per capability (checked-in default TOML; loader → typed model)
{
  "capability_id": "ml_advisory",          // stable key (P3's first capability)
  "enabled": false,                        // master off-switch — FAIL-CLOSED DEFAULT (ALL caps)
  "min_tier": "L1",                        // LearningTier required (maps to can_*())
  "tier_capability_flag": null,            // optional: bind to a TierCapabilities.can_* flag
  "model_tier": "local_sentinel|ollama|cloud_l2",
  "cloud_model_pref": "sonnet",            // only if model_tier=cloud_l2
  "trigger": {
    "kind": "event|schedule|manual|threshold",
    "spec": "ml:training_complete | watchdog:circuit_broken | cron:*/15 | regime:transition",
    "debounce_secs": 900,                  // §F.1 trailing-edge settle window
    "dedup_key": "capability_id+spec+coarse_subject"   // §F.1 storm-control identity
  },
  "budget": {
    "per_call_usd_cap": 0.50,
    "daily_usd_cap": 1.00,                 // ≤ DOC-08 $2/day (budget_config.toml:9) unless rule-raised
    "tier_gated_spend": true
  },
  // autonomy_level is NOT stored here — DERIVED from (lane + min_tier + Posture). See §C.
  "lane": "research|hypothesis|replay_0r|demo_stage1|risk_tighten|ml_backlog|ops_alert|none",
  "output_schema_ref": "ml_advisory.v1",   // → §D output-schema registry
  "prompt_contract_ref": "ml_advisory.v1", // → §D PromptContract registry
  "out_of_bound_guard_ref": "ml_advisory.guard.v1",
  "novelty_gate": true,
  "consequential_default": false,          // → D3 ledger consequential_at_creation (l2_call_ledger_writer.py:135)
  "quality_metric_ref": "ml_advisory.metric.v1"  // → §O (P5)
}
```

**Loader hard rules (CC stress-test targets; design them as loader-owned assertions):**
- **`enabled` defaults `false`** (fail-closed); a stanza omitting it → `false`.
- **`unknown field → reject load`** — reuse `ConfigDict(extra="forbid")` (`agent_contracts.py:109`). Catches stale v1 configs / drift.
- **`autonomy_level` key present → reject load** [C2-adjacent] — the field is *derived*, never declared; a config declaring it is a drift error.
- **`can_auto_deploy_to_paper` used as a posture gate → reject load** [C2] — it is `True@all-tiers` (`learning_tier_gate.py:185/196/205/218/231`), carries no signal; the loader rejects any stanza that references it as an auto-vs-manual decider.
- **`lane` ∉ the LANE_DIRECTION table keys → reject load** — every lane must resolve a `direction` (§C). There is **no `lane: live` value**.
- **A capability whose `model_tier=cloud_l2` but `tier_capability_flag` resolves `False` at current tier → `tier_locked`, refuse to run** (not "run degraded").

---

## C. ★ `LANE_DIRECTION` typed invariant — the no-auto-path-to-live linchpin (CC stress-test 5)

This is the single most important CC-grep-verifiable construct. It must be a **one-line invariant**, not an emergent property of a strictness lattice. Grounded against the existing asymmetry vocabulary in `_AUTONOMY_PATH_MATRIX` (`governance_autonomy_service.py:80,116-130`): kill-criteria (e)/health-degradation (j) are `auto-trigger` (contract); promotions (a)/(c)/(d) are `operator manual` at level1 (expand).

### C.1 The loader-owned `LANE_DIRECTION` table (single typed truth)

```python
# loader-owned, module-level constant — the ONE place lane→direction is defined.
# CC greps THIS table + STEP-1 to verify "no auto-path to live" in one read.
LANE_DIRECTION: dict[str, str] = {
    "research":     "neutral",
    "hypothesis":   "neutral",
    "ml_backlog":   "neutral",
    "replay_0r":    "neutral",
    "ops_alert":    "neutral",   # alert != remediation
    "risk_tighten": "contract",  # survival-first; auto (bounded by deterministic governor)
    "demo_stage1":  "expand",    # promotion-class → MANUAL under Conservative (§C.3 forward-OOS bar)
    "none":         "neutral",
    # ANY future "risk_loosen" / "*_promote" / live  →  "expand"  → forced human.
    # There is NO "live" key. Live is unreachable from any auto path.
}
```

### C.2 Derived autonomy — STEP-1 is the linchpin

```python
def effective_autonomy(cap) -> Literal["MANUAL","TIER_LOCKED","AUTO_VIA_GATE"]:
    # STEP 1 — DIRECTION GATE (typed, loader-owned, NON-OVERRIDABLE — the CC linchpin):
    if LANE_DIRECTION[cap.lane] == "expand":
        return "MANUAL"          # never auto. full stop. no tier/posture can unlock this.
    # STEP 2 — TIER GATE:
    if current_tier < cap.min_tier or (cap.tier_capability_flag and not flag_value):
        return "TIER_LOCKED"     # refuse, don't degrade
    # STEP 3 — POSTURE MODULATION (can only ADD friction, never remove the gate):
    if posture == "Conservative" and is_promotion_class(cap.lane):  # e.g. demo_stage1
        return "MANUAL"          # §C.3 trust-building
    return "AUTO_VIA_GATE"
    # STEP 3 NEVER reads can_auto_deploy_to_paper (True@all-tiers → no signal). [C2]
    # AUTO_VIA_GATE means "eligible to attempt through the deterministic gate", not "apply now".
```

### C.3 The CC-grep-verifiable properties (designed as single constructs)

| CC stress-test | Property | How CC greps it (one read, not a lattice trace) |
|---|---|---|
| **5/10 — no auto-path to live (THE linchpin)** | STEP-1 `if LANE_DIRECTION[lane]=="expand": return MANUAL` is checked **first**, before any tier/posture logic, and is the **only** path for `expand` lanes. **No `lane:"live"` key exists.** | grep the `LANE_DIRECTION` table (one constant) + the `effective_autonomy` STEP-1 (one `if` at the top of one function). Assert: (a) no `"live"` key; (b) STEP-1 returns MANUAL for `expand` with **zero** subsequent re-entry. A loader-rejects test: a config with `lane:"live"` or an `autonomy_level` key fails to load. |
| **(loader reject)** | The loader **rejects** (i) a config declaring `autonomy_level`, (ii) a config auto-applying an `expand` lane, (iii) a config using `can_auto_deploy_to_paper` as a posture gate. | grep the loader for the three reject branches; a parametrized test feeds each bad config → `reject load`. |
| **16 — C2 no `can_auto_deploy_to_paper` branch** | The Orchestrator/applier has **zero** branch on `can_auto_deploy_to_paper` to decide demo auto-vs-manual. | grep Orchestrator + applier for `can_auto_deploy_to_paper` used in an `if` → must be **0** (it may be *read for display* only, never branched on for posture). |

**Why this is strictly simpler AND safer:** the `expand→MANUAL` rule is **one `if` at the top of one function** referencing **one loader-owned constant** — CC verifies "mostly automatic is safe under root principle 5" by reading two constructs, not by reasoning about a strictness lattice. There is **no `autonomy_level` field to misconfigure** (the most dangerous v1 knob is deleted). The `expand→MANUAL` for `demo_stage1` is reinforced by the §C.3 forward-OOS bar in the deterministic applier (B2, design lines 594-633 — **applier-owned, P3/P4, not P2**, but the lane is typed here).

---

## D. PromptContract + output-schema registry

**Both input and output are schema'd. The prompt is a deterministic, versioned template — Ollama is FORBIDDEN from generating prompts** (it would stack hallucination, destroy D3 attribution, break the §D.4 fault-localization replay). Grounded: today `layer2_engine.py:89-90` already carries fixed `L2_PROMPT_CONTRACT_VER="l2_contract.v1"` / `L2_OUTPUT_SCHEMA_VER="l2_schema.v1"`; P2 generalizes these into a **versioned registry keyed by `prompt_contract_ref`/`output_schema_ref`** (§B).

A `PromptContract` (versioned) declares: `role`, `task`, **echoed output-schema**, `constraints` (advisory-not-decision + governance + fact/inference/assumption discipline), `few_shot`, `uncertainty_rule`, plus a **structured-label context block** (the only place free text enters; it is pre-extracted via `ContextDistiller`, **not** model-authored — design §E.1 lines 804-814).

**Ollama is allowed in exactly two seams** (design lines 806-810): (1) input extraction (unstructured → structured fields; reuse `ContextDistiller`); (2) output NL rendering (structured → prose, **on human trigger only**). It is **never** the prompt author and **never** the validator.

`contract_ver` + `schema_ver` are written into **every** D3 row — wire through `record_l2_call(..., contract_ver=<registry>, schema_ver=<registry>)` (`l2_call_ledger_writer.py:121-122`). Worked PromptContract/output-schema examples (`ml_advisory.v1` etc.) are in design §E.2 (lines 822-980) — **those concrete capability contracts are P3, not P2**; P2 ships the **registry mechanism + the deterministic-template discipline + the wiring**, with `l2.manual_reasoning` (the existing one) as the seed registered contract.

**CC/E2 grep target:** no code path where Ollama (or any model) generates a prompt template — the template comes from the versioned registry only; Ollama touches only the `ContextDistiller` extraction seam and the on-demand NL render.

---

## E. Deterministic out-of-bound guard (runs BEFORE a proposal is formed)

The guard is **deterministic** and runs **before** a proposal is formed — it catches hallucinated parameters (leverage 50x / size 80% / negative cost) **without human eyes** (design §E.1 lines 816-818). Verdict ∈ `{pass, clamp, reject}` is logged to D3 via the **already-existing** `guard_verdict` ledger column (`l2_call_ledger_writer.py:129` / `agent.l2_calls.guard_verdict`, V134).

**Guard registry** keyed by `out_of_bound_guard_ref` (§B). Each guard is a pure deterministic function `guard(parsed_output, context) -> GuardResult{verdict, clamped_output, kinds_hit}`. Generic clauses P2 ships (capability-specific clauses are P3):
- **range clamps**: leverage / size / cost fields clamped to deterministic bounds; out-of-range → `clamp` (and the clamped value is what proceeds) or `reject` if structurally invalid (e.g. negative cost).
- **schema conformance**: parsed_output failing the `output_schema_ref` schema → `reject` (→ `parsed_output=NULL` in D3, `l2_call_ledger_writer.py:128`).
- **"no inventing data"**: any field referencing a data axis not in `available_signal_axes` → `reject` (design §E.2 `ml_advisory.guard` line 869).

**Defense-in-depth split (design line 984):** the guard catches *form* (a hallucinated parameter shape); the deterministic math gate (P3/P4) catches *substance* (is the alpha real). The guard is the cheap structural net **before** the model output ever becomes a proposal.

**CC/E2 grep target:** the guard runs **before** `record_l2_call` writes `parsed_output`, and a `reject` verdict means the proposal is **never** routed to an applier (it is logged-and-dropped). The guard is deterministic — no model call inside it.

---

## F. Trigger admission — §F.1 storm-control (deterministic, in code, before any model call)

The Orchestrator owns a **deterministic admission stage** before any model call, with the exact order **dedup → debounce → coalesce → budget → tier/posture** (design §F.1 lines 1023-1048). All in code, all per-capability-configurable via `trigger.debounce_secs`/`dedup_key` (§B). Genuinely net-new (greenfield: `experiment_ledger.py:267` debounce is unrelated auto-save).

| Stage | Rule | Logged to (gate-seam) |
|---|---|---|
| **1. Dedup** | `dedup_key = capability_id + spec + coarse_subject`; a trigger matching an in-flight/recently-served key in the window is **dropped** (no model call). Mirrors the watchdog `emit_restart_skipped_if_new` precedent (PA memory 2026-06-05). | `record_gate_seam(gate_id="admission", verdict="reject", details={reason:"trigger_deduped"})` |
| **2. Debounce** | trailing-edge: wait `debounce_secs` for the burst to settle, fire **once** on latest state. A regime flapping 3×/min → one advisory. | `details={reason:"debounced"}` |
| **3. Coalesce** | multiple related triggers in-window → **one** call with a batched context block (when the PromptContract supports a list input). One reasoning call, one cost, one provenance row. | `details={reason:"coalesced", batch:[...]}` |
| **4. Budget** | `check_daily_budget()` (`layer2_cost_tracker.py:286`) + per-capability `daily_usd_cap` (§B); **per-capability hard daily ceiling** → on hit, degrade to **NO_ADVICE** for that capability. | `details={reason:"budget_exceeded"}` |
| **5. Tier/Posture** | `effective_autonomy(cap)` (§C.2): `TIER_LOCKED` → refuse; `MANUAL` → route to human inbox, no auto-call; `AUTO_VIA_GATE` → proceed. | n/a (proceeds or refuses) |

**The iron storm-control invariant (E5/AI-E + CC stress-test):** a trigger storm **cannot blow the DOC-08 $2/day envelope even with debounce OFF** — because stage 4 (budget) is a **hard** gate downstream of dedup/debounce/coalesce, and the per-capability daily ceiling degrades to NO_ADVICE. Suppressed volume is **always** logged with a `trigger_decision` reason (the §O metric reads it: a capability that triggers a lot but is mostly deduped is a demote candidate — design line 1047). **Grounding:** the budget hard cap is `budget_config.toml:9` (`daily_usd_max = 2.0`), and `check_daily_budget()` already returns `(allowed, remaining)` and is the gate `layer2_routes.py:251` already uses on the manual path.

---

## G. Conflict adjudication — §F.2 fixed precedence table (NO model adjudication)

Two conflict classes; both resolve **toward the deterministic / more-conservative side** (root principles 4, 6), **never by a model arbitrating** (design §F.2 lines 1050-1082). This is a **fixed precedence table**, designed so CC can grep that **no model output ever adjudicates two proposals**.

### G.1 The fixed precedence table (table-driven, deterministic)

**(a) L2 advisory vs deterministic governor/gate — strict precedence `deterministic > advisory`:**
- risk-tighten: governor applies the **stricter** of {its own deterministic number, L2's suggestion clamped to [floor, current]}. L2 can only ever *pull tighter*, never *relax*.
- any gate (DSR/PBO/leak/FDR): a gate `reject` **always** beats an L2 `recommend` (Alpha Evidence Governance, CLAUDE.md). **The model never overrides a failed quantitative gate.**

**(b) Cross-capability conflict — fixed precedence, no model adjudication:**
1. **Direction precedence:** `contract` (tighten/defensive) **always wins over** `expand` (loosen/promote) on the same target. (ML says "promote X" but regime-risk says "tighten now" → tighten wins, promotion **deferred + logged**, not killed.)
2. **Same-direction, different magnitude:** take the **stricter** value (root principle 6).
3. **Orthogonal targets:** no conflict — both proceed through their own gates.
4. **Unresolvable / novel** (table doesn't cover) → **NO auto-apply**, escalate to the human inbox with both recommendations + provenance. **Fail-closed.**

Every adjudication is logged to the **existing** gate-seam log (`record_gate_seam`, `l2_call_ledger_writer.py:314`) with the losing recommendation + reason, so §D.4 forensics + §M feedback can later turn a recurring bad adjudication into a deterministic rule.

### G.2 The CC-grep-verifiable property (designed as a table + zero-model construct)

| CC stress-test | Property | How CC greps it |
|---|---|---|
| **6 — no model-adjudication path** | Adjudication is a **pure function over a fixed precedence table** (`PRECEDENCE: dict`); a gate `reject` always beats an L2 `recommend`; `contract` always beats `expand`. **No code path passes two proposals to a model and uses the model's output to pick a winner.** | grep the adjudication module: (a) the precedence is a literal table/dict, not a model call; (b) **zero** model-invocation (`run_session` / LLM client) inside the adjudication function; (c) the `gate reject > L2 recommend` and `contract > expand` rules are literal comparisons. A test: feed a (gate-reject, L2-recommend) pair → result is always the gate reject, with **no** LLM call made. |

---

## H. Fail-safe state machine — the iron rule

L2 failure **always** degrades to the deterministic baseline — **never blocks, never unsafe** (design §F lines 988-1019). Reuses the layered-autonomy Conservative/Standard + notification-failsafe + cooling precedent (`governance_autonomy_service.py` advisory-lock+TOTP+cooldown, V114).

```
HEALTHY ──call fails──> RETRY ──exhausted──> DEGRADE_OLLAMA ──Ollama gone/not permitted──>
NO_ADVICE ──repeated failure / guard storm──> TRIPPED (per-capability, cooling timer) ──systemic──>
GLOBAL_CONSERVATIVE (force posture → Conservative; reuse autonomy switch + notify→1h→Defensive + 7d cooling, V114)
   ▲                                                                                          │
   └──────────────────────────── N consecutive ok ───────────────────────────────────────────┘
```

Plus the deterministic out-of-bound guard (§E) runs at **every** proposal regardless of state.

**The iron-rule invariant (CC/E3 stress-test — the design's load-bearing safety claim):**
> There is **no path** from any fail-safe state to "block the trading/risk deterministic baseline" or "auto-apply to live." The worst case is **NO_ADVICE = the system behaves exactly as it does today without L2.**

**How CC/E3 verifies it (under fault injection):**
- `NO_ADVICE` and `TRIPPED` and `GLOBAL_CONSERVATIVE` all leave the deterministic trading/risk paths **untouched** — they only stop L2 from emitting advice and (for GLOBAL_CONSERVATIVE) force the **already-existing** Conservative posture (which is *more* conservative, never live-enabling).
- grep: **no** fail-safe transition writes `live_execution_allowed` / `OPENCLAW_ALLOW_MAINNET` / calls `promote_tier` / `acquire_lease` (trading). Every fail-safe state is a **subtraction** of L2 capability, never an addition.
- E3 fault-injection test: kill cloud L2 → DEGRADE_OLLAMA; kill Ollama → NO_ADVICE; assert trading/risk deterministic baseline still runs and **no** live-enabling write occurred.

---

## I. CC-linchpin invariants (designed grep-verifiable) — the compliance summary

This consolidates the CC stress-tests this phase owns (execution-plan §2 lines 134-156; design §L lines 1610-1662). **Each is designed as a single grep-able construct, not an emergent property.**

| Invariant | Design construct (single, grep-able) | Ground / CC grep |
|---|---|---|
| **C1 — Orchestrator zero `promote_tier`/autonomy-raiser** (stress-test 15) | The Orchestrator + (future §O P5) modules **import nothing** that raises tier and **call** no `promote_tier`. The §O promote-candidate (P5) writes only a read-only inbox row; the **real** promote runs only from the operator route. | `promote_tier` auto-raises L1→L4 with `approved_by=None` (`learning_tier_gate.py:520/550/570-574`). CC grep: Orchestrator module + advisory-loop imports → **0** hits for `promote_tier` / autonomy-raiser. The only caller of `promote_tier` is inside the operator route. |
| **C2 — no branch on `can_auto_deploy_to_paper`** (stress-test 16) | Demo auto-vs-manual is decided **solely** by `LANE_DIRECTION` + STEP-3 + (P3/P4) the §C.3 forward-OOS bar. The loader **rejects** a config using `can_auto_deploy_to_paper` as a posture gate. | `True@all-tiers` (`learning_tier_gate.py:185/196/205/218/231`). CC grep: Orchestrator/applier → **0** `if can_auto_deploy_to_paper` branches for posture (read-for-display allowed). |
| **E3-E1 — every Orchestrator/registry WRITE = operator-scope** (stress-test 18) | Every new mutation route uses `actor = Depends(_require_operator_auth)` (or `require_scope_and_operator(...,"ai_budget:write")` for the L2-cost family); reads stay read-only and cannot mutate. The C1 promote-confirm (P5) reuses the **TOTP-gated** `/autonomy-level/switch` pattern. | `_require_operator_auth` is the "standard Depends() target for all write/state-change endpoints" (`governance_routes.py:129-152`). The L2-cost write family already uses `require_scope_and_operator` (`layer2_routes.py:247`). TOTP precedent: `governance_autonomy_service.py:598-601`. CC grep: every new POST/PUT route in the Orchestrator/registry surface has an operator-scope Depends; no write reachable from a read-only surface. |
| **F.2 — no model-adjudication** (stress-test 6) | §G fixed precedence table; zero LLM call inside the adjudication function. | See §G.2. |
| **fail-safe iron rule** (CC/E3) | §H — every fail-safe state subtracts L2 capability; worst case NO_ADVICE; no live-enabling write in any transition. | See §H. |
| **single write entry / AI≠command** (principles 1, 3) | Orchestrator has no order path; output → deterministic gate → (proposal) → human for live. `is_simulated=True` preserved (`layer2_engine.py:119`). | grep: no `IntentProcessor`/`submit_intent`/order IPC in the Orchestrator. |
| **live hard line** (principle 7) | No `lane:"live"` value; `expand→MANUAL` structural; `can_modify_live_config=False@all-tiers` already in code. | `learning_tier_gate.py:664-671`; §C.1 LANE_DIRECTION has no `live` key. |

---

## J. Reuse vs new —逐項 ground-confirmed

| Build | Decision | Ground (file:line) |
|---|---|---|
| LearningTier L1-L5 scaffold + `can_*()` flags + `can_modify_live_config=False` | **REUSE** | `learning_tier_gate.py:165-234` (TierCapabilities), `:660/:664` (flags); wired `paper_trading_wiring.py:374/376`. |
| `_AUTONOMY_PATH_MATRIX` Conservative/Standard + TOTP switch | **REUSE + EXTEND** (add L2 lanes as rows; don't fork) | `governance_autonomy_service.py:80,116-130` (matrix), `:598-601` (TOTP switch route). |
| Operator-scope WRITE auth (E3-E1 + C1 confirm) | **REUSE** | `governance_routes.py:129` `_require_operator_auth`; `layer2_routes.py:247` `require_scope_and_operator`. |
| P1 D3 writer (the thing P2 wires) | **REUSE** | `l2_call_ledger_writer.py:113/266/314/367`. |
| `Layer2Engine` session worker (one Orchestrator executor) | **REUSE** | `layer2_engine.py:193` (class), `:522` `run_session`. |
| `ContextDistiller` (input extraction) / `layer2_critic` (Ollama self-verify) | **REUSE** | design §E.1/§G.2 (P3 wiring); precedent confirmed in design §0. |
| `check_daily_budget()` + DOC-08 cap (admission stage 4) | **REUSE** | `layer2_cost_tracker.py:286`; `budget_config.toml:9`. |
| `ConfigDict(extra="forbid")` (registry loader unknown-field-reject) | **REUSE** | `agent_contracts.py:109`. |
| RiskConfig TOML-as-SSOT pattern (registry default TOML) | **REUSE** | `settings/risk_control_rules/risk_config.toml`. |
| `agent.l2_calls.guard_verdict` / gate-seam log (guard + adjudication logging) | **REUSE** | V134 `guard_verdict` col + V135 gate-seam (`l2_call_ledger_writer.py:129/314`). |
| **`L2AdvisoryOrchestrator` singleton** | **NEW** | greenfield (0 hits). |
| **`l2_capability_registry` + default TOML + loader** | **NEW** | greenfield. |
| **`LANE_DIRECTION` typed table + STEP-1 loader enforcement** | **NEW** | greenfield (the CC linchpin). |
| **PromptContract + output-schema registry (versioned)** | **NEW** (generalizes the existing fixed `l2_contract.v1`/`l2_schema.v1`) | `layer2_engine.py:89-90` (the seed constants). |
| **Out-of-bound guard registry** | **NEW** | greenfield (writes the existing `guard_verdict` col). |
| **Trigger admission stage (dedup/debounce/coalesce/budget/tier)** | **NEW** | greenfield. |
| **Conflict adjudication controller (fixed precedence)** | **NEW** | greenfield. |
| **Auto/scheduled/threshold trigger surface** | **NEW** (L2 is manual-only today) | `layer2_routes.py:234` is the only trigger today. |

**Net P2 framing (confirmed):** ~70% is **wiring** the already-wired `LearningTierGate L1-L5` (`learning_tier_gate.py:165-234`) + `_AUTONOMY_PATH_MATRIX` (`governance_autonomy_service.py:80`) + the P1 D3 writer + the operator-auth pattern + the budget gate; ~30% is **net-new** (Orchestrator, registry, LANE_DIRECTION, contract registry, guard registry, admission, adjudication). **No new trading authority, no new live path.**

---

## K. Singleton registration (mandatory before merge)

Three new singletons → `docs/architecture/singleton-registry.md` §2.6 (extends the existing "L2 Advisory Mesh" section; §2.6.1 is already `L2CallLedgerWriter`, line 351). Follow the §3.1 pre-registration discipline + the 12-column format (`:39-44`):

- **§2.6.2 `L2AdvisoryOrchestrator`** — the conductor (§A.3 row above).
- **§2.6.3 admission controller** (`L2TriggerAdmissionController` or Orchestrator-internal state) — owns per-capability debounce/dedup/coalesce windows. If implemented as Orchestrator-internal state (not a separate singleton), note it as "internal state of §2.6.2, no separate binding" — E1 decides; either is registerable.
- **§2.6.4 conflict-adjudication controller** (`L2ConflictAdjudicator`) — the fixed-precedence pure-function holder (stateless; may be a module of pure functions rather than a mutable singleton — if stateless, it needs **no** singleton row, only a §4.1 note; E1 decides).

**E2 must check** (singleton-registry §3.2): each new mutable singleton is registered before merge; stateless pure-function modules are exempt but should be noted.

---

## L. Migration requirement judgment — **P2 needs NO migration** (V137 reserved-not-used)

**Determination: P2 ships ZERO DB migration.** Grounded reasoning per surface:

- **Registry = TOML SSOT** (§B). The checked-in default TOML is the source of truth (mirrors RiskConfig `settings/risk_control_rules/risk_config.toml`). All capabilities `enabled=false` by default. **No DB table in P2.**
- **Admission/adjudication state = in-memory + logged.** Debounce/dedup/coalesce windows are per-capability in-process state (no persistence needed — a restart cleanly re-arms). Suppressed-volume + adjudication outcomes are logged to the **already-existing** `learning.l2_gate_seam_log` (V135, landed P1) via `record_gate_seam(...)` — **no new table.**
- **Guard verdicts** write the **already-existing** `agent.l2_calls.guard_verdict` column (V134, landed P1). **No new column.**
- **The C1 promote-candidate inbox** (`learning.l2_promote_candidates`) is a **P5** concern (execution-plan §2 line 286 puts it in Phase 5; design §O.4 line 2066). **Not P2. Do not create it here.**

**If — and only if — the operator later decides the registry needs DB-backed runtime overrides** (a "RiskConfig TOML > runtime DB override" mirror, design §B line 412), that override table would be **V137** (verified next-free: V134/V135/V136 on disk, V137+ absent). That is **out of P2 scope** as designed; flag as an operator decision (§N). If V137 is ever taken, it owes a **Linux PG dry-run + double-apply idempotency** per `feedback_v_migration_pg_dry_run.md` — but **P2 as specified does not reach that bar.**

**Verdict: no V137 migration in P2.** The next-free number is **V137** (reserved-not-used).

---

## M. E1 acceptance mapping — what each role verifies

Maps each P2 deliverable to execution-plan §2 Phase-2 acceptance bullets (lines 133-159) + the gating-ledger C1/C2/F.2/E3-E1 rows (lines 69-76) + §3 cross-phase invariants (lines 326-342). **Route handlers parse→call→format only; business logic below (CLAUDE.md §七).**

| Deliverable | E1 builds | E2 reviews | **CC verifies (load-bearing)** | E3 verifies | E4 / dry-run |
|---|---|---|---|---|---|
| **A. `L2AdvisoryOrchestrator`** | conductor loop (§A.2); owns `Layer2Engine` as one executor; wires `record_l2_call` with registry/contract-driven `capability_id`/`contract_ver`/`schema_ver` (not hardcoded); registered §2.6.2 | route-thin; no order/lease imports; D3 write per call | **15: zero `promote_tier`/autonomy-raiser refs** (grep) | no order/lease/live-config write under any state | Mac+Linux test pass |
| **B. `l2_capability_registry` + TOML + loader** | typed model + checked-in default TOML (all `enabled=false`); `extra="forbid"`; reject `autonomy_level`/`can_auto_deploy_to_paper`-as-posture/`lane:"live"` | unknown-field reject; fail-closed default | **16: loader rejects bad configs**; `enabled=false` default | — | — |
| **C. `LANE_DIRECTION` + derived autonomy** | loader-owned table (no `live` key) + STEP-1 `expand→MANUAL` first & non-overridable | one-line invariant, not lattice | **5/10: no auto-path to live** (grep table + STEP-1); a `lane:"live"`/`autonomy_level` config fails to load | — | 3E-ARCH (paper/demo/live verified independently) |
| **D. PromptContract + schema registry** | versioned deterministic templates; Ollama forbidden to generate; `contract_ver`/`schema_ver`→every D3 row | template from registry only | no model generates a prompt template (grep) | — | — |
| **E. Out-of-bound guard registry** | deterministic guard before proposal; verdict→`guard_verdict` (V134) | guard pre-proposal; deterministic (no model inside) | reject → never routed to applier | — | — |
| **F. Trigger admission (§F.1)** | dedup→debounce→coalesce→budget(`check_daily_budget`)→tier; per-cap daily ceiling→NO_ADVICE; suppressed volume logged | order correct; storm-control | storm can't blow DOC-08 $2/day even debounce-off; `trigger_decision` logged | (E5/AI-E budget stress) | — |
| **G. Conflict adjudication (§F.2)** | fixed precedence table; `gate reject > L2 recommend`; `contract > expand`; unresolved→escalate no-auto-apply | table-driven | **6: no model-adjudication path** (grep) | — | — |
| **H. Fail-safe SM** | HEALTHY→RETRY→DEGRADE_OLLAMA→NO_ADVICE→TRIPPED→GLOBAL_CONSERVATIVE | every state subtracts L2 capability | iron rule: no fail-safe→block-baseline / auto-live (grep) | **fail-safe never blocks under fault injection** | — |
| **(write endpoints)** | new Orchestrator/registry mutation routes = `Depends(_require_operator_auth)`; reads read-only | parse→call→format | **18: every WRITE operator-scope** (grep) | **E1: every write rejects non-operator; no write from read-only surface** | — |
| **Singletons** | §2.6.2/2.6.3/2.6.4 registered (or stateless-noted) | registered before merge | — | — | — |

**Cross-phase invariants CC re-checks (every phase, 3E-ARCH independently — execution-plan §3 lines 326-342):** L2 touches **none** of `live_execution_allowed`/`max_retries`/`OPENCLAW_ALLOW_MAINNET`/`authorization.json`/`execution_authority`/`system_mode`/lease trading authority; `can_modify_live_config=False@all-tiers` (`learning_tier_gate.py:664-671`); single write entry (no order path); AI≠command; survival>profit (LANE_DIRECTION typed asymmetry); AI cost≥edge (per-cap + tier-gated budget, DOC-08 cap).

---

## N. Open items for operator (do not block E1 start; resolve before dependent work)

1. **[OPEN — operator decision] DB-backed runtime registry overrides?** P2 as designed = **TOML SSOT, no DB table, no V137**. If the operator wants live runtime overrides (RiskConfig-style "TOML > runtime DB"), that is a **V137** addition (out of current P2 scope; owes Linux PG dry-run). **PA recommendation: TOML-only for P2** (simplest, fail-closed, no migration risk) — runtime overrides can be a later increment if a real need surfaces. **Needs operator confirm to lock "no DB registry in P2."**
2. **[OPEN — execution-plan §4, carried] Auto-trigger cadence vs DOC-08 $2/day** — per-capability daily cloud envelope; may a high-ROI capability exceed $2/day "by rule"? P2 ships the **hard** per-capability ceiling + admission backstop; the override *policy* is an operator call. (Does not block P2 — all caps ship `enabled=false`.)
3. **[OPEN — execution-plan §4, carried] §F.1 debounce defaults per trigger class** — regime-transition vs anomaly vs `ml:training_complete`; operator/E5 tune vs cost. (Default values in TOML; tunable.)

---

## O. Residual Linux-verify / owed items

- **None block P2 design or E1 start** (P2 is Python control-plane + TOML; no migration, no PG semantic, no Rust/IPC).
- **E4 owes** the standard Mac+Linux test regression for the new modules (no migration dry-run owed, since P2 ships no migration — unless N.1 reopens V137).
- **3E-ARCH** (CLAUDE.md): the no-auto-path-to-live + fail-safe invariants must be verified **independently** for paper/demo/live posture (CC, not "only-paper-PASS") — but since L2 cannot reach live structurally, "live" verification is the **negative** (proving the auto-loop cannot touch it), not a live exercise.

---

## P. Side-effect / hard-boundary checklist (PA discipline)

1. **Other modules importing the changed surface?** P2 adds new modules (Orchestrator, registry, LANE_DIRECTION, contract/guard registries, admission, adjudication) + a **wiring change** to `layer2_engine.py` (registry/contract-driven `capability_id`/`contract_ver`/`schema_ver` instead of the hardcoded `:355/:359/:360`). The existing manual-trigger path stays as the seed `l2.manual_reasoning` capability — **no regression**; the existing D3 wiring (`layer2_engine.py:352`) keeps working. No existing import breaks.
2. **Mocked functions?** The Orchestrator/admission/adjudication are new; tests verify **intent** (no-auto-path-to-live, fail-safe subtracts capability, storm can't blow budget, no model adjudicates), not only behavior (CLAUDE.md Operating Style 9).
3. **asyncio/threading boundary?** The Orchestrator is async (drives `run_session` which is async, `layer2_engine.py:522`); the D3 writer does sync PG INSERT via the existing pool (`l2_call_ledger_writer.py:109`) — same pattern P1 already ships; no new asyncio/thread mixing introduced.
4. **API response schema change?** New **write** routes (operator-scope) for capability enable/disable/budget; new **read** routes for registry/admission status. The existing `/trigger`, `/cost/*`, `/config`, `/sessions` routes (`layer2_routes.py`) are **unchanged**. No breaking response-schema change to existing routes.
5. **Rust ↔ Python IPC schema?** **None in P2.** No live table, no engine change. The R2-5 live-provenance hop (which would touch Rust) is deferred (P1 doc §C). P2 is Python control-plane + TOML only.

**Hard boundaries (CLAUDE.md §四) — all honored:**
- No `live_execution_allowed` / `max_retries` / `system_mode` / `OPENCLAW_ALLOW_MAINNET` / `authorization.json` / `execution_authority` touch. ✔
- No new live path; `expand→MANUAL` loader-enforced; the auto-loop structurally cannot reach the live row. ✔
- Orchestrator has no order/lease/`promote_tier` authority (C1). ✔
- `can_modify_live_config=False@all-tiers` already in code, untouched. ✔
- Single write entry (principle 1): L2 has no order path; proposals reach effects only via existing deterministic appliers/gates. ✔
- All new WRITE endpoints operator-scope (E3-E1). ✔
- New singletons registered before merge. ✔
- Rust-first N/A (P2 is control-plane orchestration over the existing advisory surface; the trading-truth layer stays Rust and is untouched). ✔

---

## Q. Verdict

**E1-READY (design-only).** No code, no migration apply, no DB write, no deploy was performed.

**Reuse-vs-new conclusion:** ~70% wiring of the already-wired `LearningTierGate L1-L5` (`learning_tier_gate.py:165-234`) + `_AUTONOMY_PATH_MATRIX` (`governance_autonomy_service.py:80`) + the landed P1 D3 writer (`l2_call_ledger_writer.py`) + the operator-auth pattern (`governance_routes.py:129`) + the budget gate (`layer2_cost_tracker.py:286`); ~30% net-new (Orchestrator / registry / `LANE_DIRECTION` / contract registry / guard registry / admission / adjudication) — all greenfield (0 hits). **No new trading authority, no new live path.**

**The CC-grep-verifiable carbon-layer design:** every linchpin is a **single construct**, not an emergent property — LANE_DIRECTION is one loader-owned table + one STEP-1 `if` (no `live` key); C1 is "0 `promote_tier` refs in the Orchestrator module"; C2 is "0 `can_auto_deploy_to_paper` posture branches" + loader-reject; F.2 is "0 model calls inside the table-driven adjudicator"; the fail-safe iron rule is "every state subtracts L2 capability, 0 live-enabling writes." CC verifies each by reading one or two constructs.

**Migration:** **P2 needs NO migration.** Registry = TOML SSOT; admission/adjudication = in-memory + logged to the existing V135 gate-seam log; guard verdicts use the existing V134 `guard_verdict` column; the C1 promote-inbox is P5. Next-free number is **V137** (reserved-not-used) — taken **only if** the operator reopens DB-backed runtime registry overrides (§N.1).

**Residual Linux-verify open items:** none block P2/E1 (no migration, no PG semantic, no Rust/IPC). E4 owes standard Mac+Linux test regression for the new modules.

**Explicit verdict: E1-ready, conditional on one operator confirm** — lock **"P2 ships TOML-SSOT registry, no DB table, no V137"** (§N.1). Everything else is design-decided and grounded. CC owns the load-bearing audit (stress-tests 5/6/10/15/16/18); E3 owns write-auth + fail-safe-under-fault.

PA DESIGN DONE: report path: srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-08--l2-p2-orchestrator-tech-design.md
