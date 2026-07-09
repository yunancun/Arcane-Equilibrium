# RFC — LG-5 Live Candidate Evaluation Contract (LIVE-CANDIDATE-EVAL-CONTRACT)

Date: 2026-05-02
Owner: PA
Status: Draft, awaiting PM + QC + MIT sign-off
Scope: Unifies MIT-S2-2 (P2) + QC-S2-02 (P2) into a single design spec. Design only — no implementation, no Rust touch, no SQL migration.
Source findings: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-02--step2_cold_audit_4day_window.md` + Step 2 cold audit (MIT/QC tracks).
Related RFCs: MLDE-6 live promotion contract (2026-05-01), LG-5 constrained autonomous live (2026-05-01). This RFC sits **between** them — MLDE-6 defines payload schema, this RFC defines GovernanceHub re-evaluation logic, LG-5 defines what happens after approval.

---

## 1. Problem statement

`mlde_demo_applier._insert_live_candidate` (mlde_demo_applier.py:587-622) constructs a live candidate row by copying three fields verbatim from the source demo row:

```
expected_net_bps  <- source_row["expected_net_bps"]   # demo-derived
confidence        <- source_row["confidence"]
sample_count      <- source_row["sample_count"]
```

These three numbers are then visible to GovernanceHub / Operator review as the live promotion's expected economics. **They are not.** They are the *demo* expected economics measured in the demo cost regime.

### Why demo expected_net_bps is structurally wrong for live

1. **Cost regime drift**: Step 2 cold audit healthcheck `[33]` shows demo 7d `maker_like = 27.2%` vs `live_demo` `fee_drop_only = 22.0%`. Live cost regime is materially worse than demo (slower fills, more taker conversion, different rebate tier).
2. **Realized live edge is negative**: `[40]` 24h `avg_net = -17.21bps` over 37 rows. The demo `expected_net_bps = +5–6bps` thresholded by `live_candidate_min_net_bps = 5.0` (mlde_demo_applier.py:49) is **incompatible** with current live realized distribution.
3. **Attribution chain partially broken**: MIT-S2-1 reports 84.6% of `decision_outcomes` rows have broken attribution chain → demo `expected_net_bps` itself rests on a partially-broken outcome backfill, before any cost regime adjustment.
4. **No deflation for multiple-testing**: Demo applier emits up to `max_recommendations = 16` candidates per cycle. Each is evaluated independently. PSR / DSR not applied. False discovery rate uncontrolled.
5. **Lease has no live-cost re-validation gate**: `GovernanceHub.acquire_lease()` (governance_hub.py:693) only checks authorization-permits-scope. It does not re-evaluate the candidate's expected economics against current live cost regime.

### Consequences if not fixed before true live

- Operator approves a candidate showing `+5 bps expected`, executes, realizes `-17 bps avg`. Economic loss attributable to PA letting demo numbers cross the live boundary unmodified.
- Root principle #3 (AI output ≠ command) is technically respected (Decision Lease exists) but the lease is *uninformed* — the gate does not re-evaluate the underlying claim.
- Root principle #8 (explainability) is technically met (payload exists) but the displayed `expected_net_bps` is misleading evidence.
- Root principle #13 (cost awareness, `cost_edge_ratio ≥ 0.8 → close`) cannot fire because the gate uses demo cost ratio, not live cost ratio.

### MIT + QC convergence

MIT-S2-2 (engineering lens): "fix the data passing" — add `payload.demo_cost_baseline` so live consumer can do its own adjustment.
QC-S2-02 (quant lens): "add a re-evaluation contract" — distribution-shift haircut + PSR/DSR + cost regime alignment.

This RFC unifies both: MIT supplies the **necessary metadata** (added to payload), QC supplies the **decision rule** (re-evaluation R1–R6 below), GovernanceHub becomes the **enforcement point**.

---

## 2. Contract interface

### 2.1 Producer side (mlde_demo_applier)

`_insert_live_candidate` MUST emit a payload that includes a new `demo_cost_baseline` sub-object plus existing fields. The source row remains the single source of *demo* truth.

**Required payload additions** (JSONB sub-keys, no SQL schema change):

```json
{
  "policy": "live_governed_promotion_candidate",
  "schema_version": "live_candidate_eval_v1",
  "source_demo_recommendation_id": <int>,
  "source_demo_application_id": <int>,
  "application_type": "<existing>",
  "patch": { ... },
  "requires": ["GovernanceHub", "DecisionLease", "live_gates"],

  "demo_cost_baseline": {
    "as_of_ts": "<ISO8601>",
    "engine_mode": "demo",
    "maker_fill_rate_7d": <float 0..1>,
    "fee_drop_only_7d": <float 0..1>,
    "avg_realized_net_bps_7d": <float>,
    "avg_realized_fee_bps_7d": <float>,
    "avg_realized_slippage_bps_7d": <float>,
    "sample_count": <int>,
    "source_healthchecks": ["[33]", "[40]"]
  },

  "demo_realized_window": {
    "start_ts": "<ISO8601>",
    "end_ts": "<ISO8601>",
    "n_fills": <int>,
    "n_strategy_fills": <int>
  },

  "demo_attribution_chain_ratio": <float 0..1>,
  "demo_sample_count_strategy_cell": <int>
}
```

`demo_attribution_chain_ratio` directly references MIT-S2-1 finding (current ~0.154); GovernanceHub uses it as a candidate-quality gate (R-meta below).

### 2.2 Consumer side (GovernanceHub)

New method (Python, sits next to `acquire_lease`):

```
GovernanceHub.review_live_candidate(candidate_id: int) -> ReviewVerdict
```

**Inputs (read from DB)**:
- candidate row from `learning.mlde_param_applications` where `engine_mode = 'live'` AND `status = 'live_candidate'`
- candidate row's `payload` JSONB (must satisfy schema_version `live_candidate_eval_v1`; unknown version → reject)
- current live cost regime from healthchecks `[33]` posterior + `[40]` 24h
- current GovernanceHub authorization state
- pending-candidate count for DSR/multiple-testing deflation

**Output**:

```python
@dataclass(frozen=True)
class ReviewVerdict:
    decision: Literal["approve", "reject", "defer"]
    reason: str  # enum below
    rule_failures: list[str]  # ["R1", "R3", ...] empty if approve
    expected_net_bps_demo: float          # echoed
    expected_net_bps_live_adjusted: float | None  # post R2 haircut, None if reject
    cost_regime_ratio: float | None       # live / demo, None if R1 fail
    psr: float | None                     # None if R3 not computable
    dsr_deflation_factor: float | None    # None if R4 not applied
    lease_ttl_ms: int | None              # only set on approve
    lease_revoke_triggers: list[str]      # healthcheck ids that auto-revoke
    decided_at_ts: int                    # unix ms
    decided_by: str                       # "GovernanceHub.review_live_candidate"
```

**Reason enum**:
- `"approve_within_envelope"`
- `"reject_schema_unknown"`
- `"reject_cost_regime_drift"` (R1)
- `"reject_haircut_negative"` (R2)
- `"reject_psr_below_floor"` (R3)
- `"reject_dsr_deflated"` (R4)
- `"reject_cost_edge_ratio"` (R5)
- `"reject_hard_veto"` (R6)
- `"reject_attribution_chain_too_broken"` (R-meta)
- `"defer_data_insufficient"`
- `"defer_healthcheck_not_fresh"`

`defer` is distinct from `reject`: defer means "not enough evidence right now, retry later"; reject means "this candidate is structurally unfit, supersede with new candidate".

### 2.3 Audit emission

Every `review_live_candidate` invocation MUST write one row to `learning.governance_audit_log` (or whichever audit sink is canonical at implementation time — to be confirmed by E1) with:
- candidate_id, verdict.decision, verdict.reason, full ReviewVerdict JSON
- if approve: also write `decision_lease_id` back to the candidate row
- if reject: also write `applied = false`, `requires_governance = true`, `payload.review_verdict` mirror

Fail-closed: if audit write fails → return `defer` with reason `defer_audit_write_failed`, do NOT issue lease. (Root principle #6.)

---

## 3. Re-evaluation rules (R1–R6 + R-meta)

### R1 — Live cost regime check

**Rule**:
```
current_live_maker_fill_rate >= candidate_demo_maker_fill_rate * 0.85
AND
current_live_maker_fill_rate >= 0.20  (absolute floor; QC to confirm)
```

**Source**:
- `current_live_maker_fill_rate` = `[33]` posterior measurement on `live_demo` engine, last 24h
- `candidate_demo_maker_fill_rate` = `payload.demo_cost_baseline.maker_fill_rate_7d`

**Rationale**: If live can't reproduce at least 85% of demo's maker capture rate, demo's expected_net_bps is structurally over-stated. The 0.20 absolute floor prevents approving anything when live is in a degraded mode regardless of demo baseline.

**Open**: 0.85 ratio + 0.20 floor are PA initial proposal — QC must confirm with cost-regime distribution analysis on `[33]` rolling history.

### R2 — Distribution-shift haircut

**Rule**: Compute live-adjusted expected:
```
cost_regime_ratio = (live_maker_fill_rate × live_fee_tier_multiplier) /
                    (demo_maker_fill_rate × demo_fee_tier_multiplier)

expected_net_bps_live_adjusted = expected_net_bps_demo × cost_regime_ratio
                                 - (live_avg_slippage_bps - demo_avg_slippage_bps)
```

**Pass condition**: `expected_net_bps_live_adjusted >= 1.0 bps` (positive after haircut, with safety margin above zero).

**Open**: Exact functional form (multiplicative vs additive vs blended) is QC's call. PA proposes multiplicative-with-slippage-correction as starting point; QC retro 7d post-deploy (LG-5-IMPL-5) validates whether realized live net matches the prediction within tolerance.

### R3 — PSR (Probabilistic Sharpe Ratio) check

**Rule**: `PSR(0) >= 0.95` for the demo strategy/cell underlying the candidate.

**Inputs**: candidate's strategy/cell return distribution (n = `demo_realized_window.n_strategy_fills`), benchmark Sharpe = 0 (we only require positive expected return).

**Rationale**: QC-S2-07 pre-LG-5 requirement. If PSR(0) < 0.95, the demo "edge" is statistically indistinguishable from noise and must not be promoted regardless of mean.

**Skip condition**: if `n_strategy_fills < 30`, return `defer` with `defer_data_insufficient` (do not approve, do not reject).

### R4 — DSR / multiple-testing deflation

**Rule**: If ≥3 candidates are simultaneously pending (status = `live_candidate`, decision_lease_id IS NULL, created within last 24h), deflate every pending candidate's expected:
```
K = number of pending candidates (capped at 16 per applier max)
deflation_factor = 1 / sqrt(K)  # PA initial; QC to refine with proper DSR formula
expected_net_bps_live_deflated = expected_net_bps_live_adjusted × deflation_factor
```
Pass condition (combined with R2): `expected_net_bps_live_deflated >= 1.0 bps`.

**Open**: Use Bailey-López-de-Prado DSR or a simpler Bonferroni-style correction? QC's call. PA's `1/sqrt(K)` is placeholder.

### R5 — cost_edge_ratio gate (CLAUDE.md §二 #13)

**Rule**:
```
realized_cost_bps_live = current_live_avg_fee_bps + current_live_avg_slippage_bps
realized_gross_edge_bps_live = expected_net_bps_live_adjusted + realized_cost_bps_live
cost_edge_ratio = realized_cost_bps_live / max(realized_gross_edge_bps_live, 0.01)

cost_edge_ratio < 0.5  -> pass
0.5 <= cost_edge_ratio < 0.8 -> warn (approve but with shorter lease TTL)
cost_edge_ratio >= 0.8 -> fail (reject_cost_edge_ratio)
```

Tracks root principle #13 (`cost_edge_ratio >= 0.8 -> close`). Threshold 0.5 / 0.8 from CLAUDE.md §二 + DOC-01 §5.13.

### R6 — Hard veto

Any of:
- R1 OR R2 OR R3 OR R4 OR R5 fail
- `[40]` 24h `avg_net_bps_after_fee < 0` for 7 consecutive rolling days (live-wide regime is negative)
- `[33]` 24h `maker_fill_rate < 0.10` (live cost regime catastrophically broken)
- `[22]` (trading_pipeline_silent_gap) FAIL — pipeline itself unhealthy
- Authorization not currently effective (`get_effective()` returns empty)

→ `decision = "reject"`, `reason = "reject_hard_veto"`. Cannot be overridden by individual rule passes.

### R-meta — Attribution chain quality

**Rule**: `payload.demo_attribution_chain_ratio >= 0.50`.

**Source**: MIT-S2-1 finding — current ratio ~0.154 means 84.6% of demo outcomes have broken attribution chains. Until MIT fixes attribution writer, demo expected_net_bps is itself unreliable.

**Behavior**:
- `< 0.50` → `decision = "defer"`, `reason = "reject_attribution_chain_too_broken"` (use `defer` not `reject` because it's not the candidate's fault — it's the upstream data plane).
- This rule is intentionally conservative; relax once MIT-S2-1 ships and ratio recovers.

---

## 4. Lease design (post-approve)

When `decision = "approve"`, GovernanceHub then calls `acquire_lease()` with:

```python
acquire_lease(
    intent_id = f"live_candidate_{candidate_id}",
    scope = f"LIVE_CANDIDATE_APPLY:{target_surface}:{target_name}",
    ttl_seconds = lease_ttl_ms / 1000,
)
```

**Lease TTL policy** (set by `review_live_candidate`):
- Default: `lease_ttl_ms = 6 * 3600 * 1000` (6h)
- If R5 returned `warn` (cost_edge_ratio in 0.5–0.8 band): `lease_ttl_ms = 1 * 3600 * 1000` (1h)
- If R3 PSR in [0.95, 0.97]: shorten to 2h
- Hard cap: `lease_ttl_ms <= 6 * 3600 * 1000`

**lease_revoke_triggers** (auto-revoke if any healthcheck flips FAIL during lease lifetime):
- `[22] trading_pipeline_silent_gap`
- `[33] maker_fill_rate` (ratio drop > 30% from candidate baseline)
- `[40] realized_edge_acceptance` (live regime turns negative)
- `[42] live_candidate_eval_contract` (new healthcheck — see §6 LG-5-IMPL-3)

Revocation MUST emit `governance_audit_log` row with `event_type = lease_auto_revoked` + the trigger healthcheck id.

**Persistence**: candidate row's `decision_lease_id` is written immediately after `acquire_lease()` returns non-None. If `acquire_lease()` returns None (post-approve), revert verdict to `defer` with reason `defer_lease_acquisition_failed` and emit audit row.

---

## 5. Backward compat / migration path

### 5.1 No SQL schema change

`payload` is JSONB; new sub-keys (`demo_cost_baseline`, `demo_realized_window`, etc.) added by producer in LG-5-IMPL-1. Consumer in LG-5-IMPL-2 fail-closed on missing keys → `defer_data_insufficient`. No `V###` migration needed.

### 5.2 Pending candidate handling

Per Step 2 audit, ~24 pending live candidates already in `learning.mlde_param_applications`. After contract lands:

1. **Hold**: All existing candidates with `payload.schema_version != "live_candidate_eval_v1"` are automatically `defer` (treated as "missing baseline").
2. **Bulk re-evaluate**: After LG-5-IMPL-1 + LG-5-IMPL-2 deploy, run a one-off re-evaluation script (`helper_scripts/learning/lg5_re_evaluate_pending.py` — to be written by E1 in LG-5-IMPL-2) that:
   - For each pending candidate, look up the demo source row (`source_demo_recommendation_id`)
   - Synthesize `demo_cost_baseline` retroactively from `[33]`/`[40]` history at candidate creation time
   - Call `review_live_candidate(candidate_id)` once
   - Mark `defer`/`reject`/`approve` accordingly
3. **Don't auto-promote any**: Even synthesized-baseline `approve` verdicts must be re-confirmed by Operator before Decision Lease grants live execution (LG-5 RFC envelope still applies).

### 5.3 Compatibility with MLDE-6 RFC

MLDE-6 (2026-05-01 RFC) defines candidate **schema** (`mlde_live_promotion_v1`). This RFC's `live_candidate_eval_v1` payload extension is **superset-compatible** — same top-level keys (`patch`, `rollback_patch`, `evidence_window`, `counterfactual`) plus this RFC's `demo_cost_baseline` block. MLDE-6's `MLDE6-T1` validator must accept the additional sub-keys (deferred to MLDE6-T1 implementation; this RFC adds the `demo_cost_baseline` requirement to MLDE-6's required-fields list).

### 5.4 LG-5 RFC alignment

LG-5 RFC (2026-05-01) defines the post-approval autonomy envelope. This RFC's `review_live_candidate` is the **gatekeeper before** LG-5's `lease_limited_autonomous_session` state. LG-5's `escalation_triggers` list should be amended to include `review_live_candidate verdict expired beyond candidate window`.

---

## 6. Implementation breakdown (sub-tasks for next wave)

| ID | Scope | Owner | Files | Parallel? |
|---|---|---|---|---|
| **LG-5-IMPL-1** | Producer: `mlde_demo_applier._insert_live_candidate` adds `payload.demo_cost_baseline` + `demo_realized_window` + `demo_attribution_chain_ratio`; pulls source data from `[33]`/`[40]` healthcheck snapshot + `learning.decision_outcomes` aggregation | E1 | `program_code/ml_training/mlde_demo_applier.py` | yes (independent) |
| **LG-5-IMPL-2** | Consumer: `GovernanceHub.review_live_candidate()` Python implementation + `lg5_re_evaluate_pending.py` one-off backfill script | E1 | `program_code/exchange_connectors/bybit_connector/control_api_v1/app/governance_hub.py` (or sibling new file `governance_hub_live_candidate_review.py` if LOC budget tight); `helper_scripts/learning/lg5_re_evaluate_pending.py` (new) | **blocked on LG-5-IMPL-1 schema** |
| **LG-5-IMPL-3** | Healthcheck `[42] live_candidate_eval_contract`: verifies `review_live_candidate` is being called on every new live candidate within 1h, with audit row visible in `governance_audit_log`; emits FAIL if any candidate older than 1h has no verdict | E1 | `helper_scripts/db/passive_wait_healthcheck.py` (add `check_42_*()` function); `docs/healthchecks/` (new doc) | **blocked on LG-5-IMPL-2 audit emission** |
| **LG-5-IMPL-4** | Tests: unit (R1–R6 + R-meta + audit fail-closed + lease TTL band logic) + integration (full path: demo applier → live candidate row → GovernanceHub.review → ReviewVerdict → audit log) | E4 | `tests/learning/test_lg5_live_candidate_eval_contract.py` (new); existing MLDE6 test extension | **blocked on LG-5-IMPL-1 + LG-5-IMPL-2** |
| **LG-5-IMPL-5** | QC retro: 7d after deploy, compare R2 haircut prediction vs realized live `[40]` net_bps. Validate haircut formula. If systematic bias > 2bps, raise QC RFC to refine R2 | QC | analysis report only | **blocked on LG-5-IMPL-1..4 + 7d wall clock** |

### Parallelization recommendation for PM

**Wave 1 (parallel)**:
- LG-5-IMPL-1 (producer) — single E1, single file, ~150 LOC delta
- (none other parallel safe — IMPL-2/3/4 all need IMPL-1's schema)

**Wave 2 (parallel after IMPL-1 lands)**:
- LG-5-IMPL-2 (consumer + backfill script) — single E1, ~400 LOC across 2 files
- LG-5-IMPL-4 (test scaffold + R1–R6 unit shells using mock payloads) — single E4 can start in parallel using LG-5-IMPL-1's schema as fixture spec, fill in real integration after IMPL-2 lands

**Wave 3 (after IMPL-2 lands)**:
- LG-5-IMPL-3 (healthcheck) — single E1, ~50 LOC delta
- LG-5-IMPL-4 (integration tests) — finish

**Wave 4 (7d wall-clock gate)**:
- LG-5-IMPL-5 (QC retro)

Estimated total wall clock: 2–3 days for IMPL-1..4 land + 7d for IMPL-5 retro.

---

## 7. Acceptance gate

This RFC requires **PM + QC + MIT** sign-off before LG-5-IMPL-* dispatch:

- **PM**: confirms scope fits Wave priority, agrees with parallelization plan, accepts the bulk re-evaluation of 24 pending candidates approach.
- **QC**: confirms R2 haircut formula, R3 PSR threshold (0.95), R4 deflation method (1/sqrt(K) vs DSR), R5 cost_edge_ratio bands (0.5/0.8). Open to QC redlines.
- **MIT**: confirms the new payload metadata can be sourced reliably from current data plane (MIT-S2-1 attribution still 84.6% broken — does R-meta's `>= 0.50` threshold hold for any current candidate, or does this RFC effectively block all live promotions until MIT-S2-1 ships? If yes, that's the right answer; if no, R-meta needs softening).

**Sign-off output**: PM updates Linear issue (62-finding tracker) referencing this RFC path + verdict.

---

## 8. Out of scope (explicit)

- **MLDE training pipeline redesign**: MIT-S2-1 attribution chain repair is a separate wave. This RFC does not block on it (R-meta defers candidates rather than depending on attribution being fixed).
- **Healthcheck threshold redefinition**: `[33]`/`[38]`/`[40]` thresholds are QC-S2-09's RFC scope. This RFC consumes their current outputs.
- **Rust `live_authorization.rs` schema v2 changes**: schema is stable. This RFC operates at the Python GovernanceHub layer.
- **Live execution path** (`IntentProcessor`, `bybit_rest_client`): unchanged. This RFC only gates whether a candidate becomes an Operator-reviewable proposal with a Decision Lease.
- **Operator approval UI**: MLDE-6's `MLDE6-T2` covers the read/review API route. This RFC adds the `ReviewVerdict` JSON to whatever surface that route exposes.
- **Strategy params TOML / risk_config TOML**: untouched.
- **`learning.mlde_param_applications` SQL schema**: untouched (all changes ride in `payload` JSONB).

---

## 9. Side-effect analysis (PA E1 dispatch warning)

For E2 review when LG-5-IMPL-2 lands:

1. **GovernanceHub LOC budget** (governance_hub.py is already large — verify pre-existing baseline before adding `review_live_candidate`. If add would push past 1500 LOC hard cap (CLAUDE.md §九), split into `governance_hub_live_candidate_review.py` sibling). E2 must check.
2. **Lock contention risk**: `acquire_lease` holds `self._lock` for the full validate+create flow (governance_hub.py:712). `review_live_candidate` MUST NOT hold the lock during DB reads (R1–R6 require fetching healthcheck rows + pending-count queries). Pattern: read → compute verdict → only acquire lock for the final `acquire_lease()` call.
3. **Audit write failure mode**: per §2.3, if audit write fails, return `defer` not `approve`. E2 must confirm exception handling does not silently swallow audit failures (root principle #6 + #8).

---

## 10. Root-principle check (16 conditions, abridged)

| # | Principle | Verdict |
|---|---|---|
| 1 | Single write entry | Preserved — review_live_candidate does not write orders, only verdicts + audit |
| 2 | Read/write separation | Preserved — verdict computation reads only |
| 3 | AI output ≠ command | **Strengthened** — adds re-evaluation between AI proposal and Lease |
| 4 | Strategy cannot bypass risk | Preserved — R1–R6 are additive to existing Guardian path |
| 5 | Survival > profit | **Strengthened** — R6 hard veto blocks promotion when system regime is negative |
| 6 | Fail-closed | **Strengthened** — defer on any uncertainty (audit failure, missing schema, insufficient samples) |
| 7 | Learning ≠ rewriting Live | Preserved — applier still cannot self-promote; new gate adds quality filter |
| 8 | Explainability | **Strengthened** — ReviewVerdict + rule_failures + decided_at_ts + audit row |
| 9 | Exchange disaster guard | Untouched |
| 10 | Cognitive honesty | **Strengthened** — explicitly distinguishes demo evidence from live expected |
| 11 | Agent autonomy within hard boundaries | Preserved — agents can still propose; gate is automated, not operator-only |
| 12 | Continuous evolution | Preserved — R5/R-meta auto-soften as regime improves / attribution recovers |
| 13 | Cost awareness | **Strengthened** — R5 explicitly enforces cost_edge_ratio at promotion gate |
| 14 | Zero external cost runnable | Untouched |
| 15 | Multi-agent collaboration | Preserved — verdict observable by all agents via DB |
| 16 | Portfolio risk awareness | Future extension — R4 multi-testing handles per-candidate but not portfolio correlation; flagged as open |

**Hard boundary (CLAUDE.md §四)**: untouched. `live_execution_allowed` / `max_retries` / `OPENCLAW_ALLOW_MAINNET` / `live_reserved` / `authorization.json` not modified by this RFC.

---

## 11. Open design questions (need QC / MIT cross-review)

1. **R1 thresholds (0.85 ratio + 0.20 floor)**: PA's initial proposal. QC must validate against `[33]` rolling distribution. May need different thresholds per strategy class.
2. **R2 haircut formula**: multiplicative `expected × cost_regime_ratio` is simplest. Alternatives: Bayesian shrinkage with prior = live regime, or empirical haircut from regression of live realized vs demo expected. QC's call.
3. **R3 PSR(0) threshold = 0.95**: borrowed from QC-S2-07 pre-LG-5 requirement. Needs QC re-affirmation given current sample sizes (`[40]` 24h n=37 — likely insufficient for tight PSR; may need 7d or 14d window).
4. **R4 deflation factor**: `1/sqrt(K)` is placeholder. Bailey-López-de-Prado DSR is more rigorous but needs more historical data. QC to choose final form.
5. **R-meta threshold = 0.50**: aggressive given current ratio ~0.154. **This effectively blocks all live promotions until MIT-S2-1 ships.** Is that intended? PA recommends YES (defer-not-reject is correct fail-closed posture); MIT must confirm timeline for attribution fix and whether interim ratio of e.g. 0.30 should be acceptable.
6. **Lease TTL default = 6h**: borrowed from LG-5 RFC envelope. Could shorten to 2h for first 30 days post-deploy as a learning period. Open for PM/Operator preference.
7. **Audit sink canonical name**: PA assumes `learning.governance_audit_log` exists; LG-5-IMPL-2 must verify or pick correct table during implementation.
8. **Bulk re-evaluation race**: 24 pending candidates re-evaluated retroactively need synthetic `demo_cost_baseline` from historical `[33]`/`[40]`. If history is insufficient (e.g. candidate created before `[33]` was collected), defer with `defer_data_insufficient`. Acceptable per fail-closed posture, but PM should confirm we're OK losing potentially-valid candidates to data gap.

---

## 12. Cross-references

- MIT-S2-2 source finding: Step 2 cold audit (path TBD by MIT)
- QC-S2-02 source finding: Step 2 cold audit (path TBD by QC)
- MLDE-6 prior RFC: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-01--mlde6_live_promotion_contract_rfc.md`
- LG-5 prior RFC: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-01--lg5_constrained_autonomous_live_rfc.md`
- Step 2 cold audit: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-02--step2_cold_audit_4day_window.md`
- Producer code: `srv/program_code/ml_training/mlde_demo_applier.py:587-622`
- Consumer code: `srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/governance_hub.py:693-750`
- CLAUDE.md hard boundary: `srv/CLAUDE.md` §四
- CLAUDE.md root principles: `srv/CLAUDE.md` §二 (true SoT: `srv/docs/decisions/DOC-01_..._V2.md`)

---

End of RFC.
