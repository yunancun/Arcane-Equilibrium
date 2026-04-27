# PA Report — G8-01-FUP-REGRET-DREAM-WIRING P2 — ESCALATE TO MAIN SESSION

**Date**: 2026-04-28 CEST
**Mode**: PA design + direct E1 + sanity test (3-role 合一, per main session authorization)
**Verdict**: **ESCALATE — concept needs design first** (per task §3 escalation rule)
**Outcome**: NO code change in this worktree. Recommend RFC scope reframe before E1 lands wiring.

---

## §1 TL;DR (≤200 字)

`tick_cognitive_modulator` 把 `regret_data={}` 與 `dream_data={}` 餵給 `CognitiveModulator.update(...)`，但 grep 證實兩者的 producer (`OpportunityTracker` / `DreamEngine`) **皆為已刪除 dead code（RC-11 Cat A 2026-04-12 archive）**。Production code 0 caller / 0 class definition / 0 import — 純 docstring + Rust roadmap (`R02-9 core/dream.rs`) 未動工。Modulator `_compute_confidence_floor` / `_compute_scan_interval` / `_compute_stoploss_mult` 對 `regret`/`dream` 的所有分支因此**結構性不可達**（無論餵什麼 placeholder）。Per task §3：「若 producer 完全不存在 (confirm dead concept) → 退回主會話 stop，標 ticket 為「concept needs design first」並 escalate」。**不在 P2 prep-gate scope 內 fabricate heuristic 餵假資料**（會違反 `feedback_no_dead_params`「Agent 可調參數必須真實被發現/調整/持久化」精神 + 原則 #10 認知誠實）。建議 RFC reframe → 二選一路徑（remove placeholders / new design wave）。

---

## §2 Investigation Trail (per task §1-§3)

### §2.1 Modulator API expectation grep (task step 1)

`cognitive_modulator.py:69-110` `update(...)` signature:
```python
def update(
    self,
    *,
    consecutive_losses: int = 0,
    weekly_net_pnl: float = 0.0,
    regret_data: dict[str, Any] | None = None,
    dream_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
```

Schema expectation (per `_compute_*` consumer code):
- `regret_data["net_regret_direction"]` ∈ `{"overtrading", "undertrading", "balanced"}` — drives `_compute_confidence_floor:119-122` + `_compute_scan_interval:160-168`.
- `dream_data["global"]["stoploss_multiplier"]` (or `dream_data["_meta"]["stoploss_multiplier"]`) — float; drives `_compute_stoploss_mult:147-155` blend.
- `dream_data["global"]["confidence"]` — float ≥0.6 gates dream-blend (else bypass).

Docstring authority (`cognitive_modulator.py:84-85`):
> `regret_data: From OpportunityTracker.get_regret_summary(). May be empty dict.`
> `dream_data: From DreamEngine.get_insights(). May be empty dict.`

### §2.2 Producer grep — both classes are dead concepts (task step 2)

```bash
$ grep -rn "class OpportunityTracker\|class DreamEngine" --include="*.py"
# 0 hits in production code
```

Cross-ref `docs/archive/2026-04-12--changelog_archive_pre_0408.md:575`:
> **RC-11** Category A dead code 刪除：4 files / 1,003 行
> (shadow_decision_tracker, dream_engine, opportunity_tracker, strategy_health_monitor)

So OpportunityTracker + DreamEngine **were implemented historically** (per the V1.1+R1 spec at `docs/references/2026-04-03--agent_cognitive_adaptation_spec_v1_draft.md` §3 lines 469-739 + §4 lines 775-1102, ~577 LOC class designs alone). They were **deleted in 2026-04-12** as dead code (no consumer at the time), leaving CognitiveModulator as orphan.

Rust roadmap planned re-implementation (`docs/rust_migration/02--core_upper.md:68`):
> [ ] R02-9：core/dream.rs — DreamEngine

→ Not yet done; opportunity.rs not even a roadmap row in the parsed plan.

### §2.3 Existing live producer survey for proxy candidates (task step 2 deeper)

| Candidate proxy source | Maps to | Verdict |
|---|---|---|
| H1ThoughtGate `_h1_local_stats` (`budget_skip` / `complexity_skip` / `cooldown_skip` / `ai_calls_allowed`) | regret? | ✗ rejection counter ≠ semantic regret. "AI was filtered" is hot-path budget control, not "we should have traded but did not". |
| Strategist `evaluations_rejected` / `intel_evaluated` ratio | regret direction? | ⚠️ heuristic stretch. High ratio could mean "overtrading prevented" (consistent with `direction="overtrading"`) but mapping is **fabricated** — original spec defines `net_regret_direction` from per-symbol virtual PnL of skipped trades (OpportunityTracker §3.5 of spec), not Strategist gate stats. Wrong granularity (per-strategy not per-skip). |
| AnalystAgent `analyze_trade` outcome stream | regret? | ✗ closed-position outcomes; "regret" in spec = **virtual PnL of opportunities NOT taken**. Different signal. |
| ML model_registry `canary_status` + `verdict` | dream insights? | ✗ Phase 1a dormant (zero rows per CLAUDE.md §三). Even if populated, registry tracks **ML model promotion lifecycle**, not strategy parameter Monte Carlo simulation. Spec's DreamEngine = "閒置蒙特卡洛模擬" (idle Monte Carlo on recent candles), structurally different. |
| `strategist_edge_eval.py:211` `getattr(modulator, "last_dream_summary", None)` | dream? | ✗ never set anywhere; legacy hopeful getattr pattern. |

**Conclusion**: Zero production producer mappable to either `regret_data` or `dream_data` schema **without fabricating an arbitrary heuristic mapping that violates the original SPEC semantics**.

### §2.4 Wiring mode selection (task step 3)

Task step 3 lists 3 candidate modes for each. PA evaluation:

**Regret modes**:
- (a) Strategist looks at H4 validator missed-opportunity → ✗ H4 validator is `validate_ai_output(...)` structural check, not opportunity tracker (per `h4_validator.py` + spec).
- (b) Analyst trade outcome vs expected → ✗ wrong granularity (closed trades, not skipped opportunities).
- (c) H1 thought_gate rejection log → ✗ semantic mismatch (per §2.3).

**Dream modes**:
- (a) Scout exploratory mode signal → ✗ Scout has no exploratory mode flag (`scout_agent.py` is daemon thread, no epsilon-greedy state machine).
- (b) ML registry canary stage → ✗ dormant + wrong semantic (model promotion ≠ strategy MC simulation).
- (c) Explicit epsilon-greedy schedule → ✗ none exists in production.

**All 6 candidate paths fail**. PA recommendation per task §3 final clause: escalate.

---

## §3 Three Key Findings (per task §7 ≤200 字 deliverable)

1. **`modulator.update()` signature**: takes 4 kwargs `consecutive_losses: int`, `weekly_net_pnl: float`, `regret_data: dict|None`, `dream_data: dict|None`. Schema for regret = `{"net_regret_direction": "overtrading"|"undertrading"|"balanced"}`; dream = `{"global": {"stoploss_multiplier": float, "confidence": float}}` with `confidence > 0.6` gate. Matches LOSSES-WIRING assumption ✅ — `update()` does accept these params; no signature mismatch.

2. **Regret source reality**: 0 producer in production. `OpportunityTracker` was implemented per spec `docs/references/2026-04-03--agent_cognitive_adaptation_spec_v1_draft.md` §3 (~262 LOC), then **deleted 2026-04-12 as RC-11 Cat A dead code** (`docs/archive/2026-04-12--changelog_archive_pre_0408.md:575`). No live proxy maps cleanly to `net_regret_direction` semantic (skipped-opportunity virtual PnL, not gate rejection ratio).

3. **Dream source reality**: 0 producer. Same fate as regret — `DreamEngine` ~315 LOC implemented + deleted RC-11 + Rust roadmap `R02-9 core/dream.rs` planned but not started. `model_registry` (the closest live concept) tracks ML model promotion not strategy MC simulation; orthogonal semantic.

---

## §4 Recommended Path Forward (RFC reframe options)

PA recommends operator + main session pick **one of three**:

### Option A — Remove placeholders entirely (smallest scope, ~30 LOC)
- Drop `regret_data` + `dream_data` parameters from `CognitiveModulator.update(...)`.
- Drop `_compute_stoploss_mult(dd)` (becomes pure `_BASE_STOPLOSS_MULT` constant).
- Drop `direction` branches in `_compute_confidence_floor` + `_compute_scan_interval`.
- Update `tick_cognitive_modulator` call site (drop 2 kwargs).
- Pros: closes RFC §3.1 acknowledged limitation by **removing the limitation itself**; no fake data. Aligns with `feedback_no_dead_params`.
- Cons: loses the cognitive adaptation surface area envisioned in V1.1 spec; future re-implementation needs to re-add params.

### Option B — Re-implement minimal `OpportunityTracker` + `DreamEngine` per existing SPEC (large scope, ~600 LOC + tests, 3-5d)
- Restore the two classes from `docs/references/2026-04-03--agent_cognitive_adaptation_spec_v1_draft.md` §3 + §4.
- Wire Scout → `OpportunityTracker.record_skipped(...)` (per spec line 721).
- Add OpportunityTracker daemon + `update_virtual_pnl(...)` per spec.
- Add DreamEngine `run_cycle(recent_candles, current_params)` daemon (~2-7d cron per spec).
- Pros: closes the loop properly; matches original architectural intent.
- Cons: scope explosion vs P2 prep-gate; needs new PA RFC + multi-wave plan; competes with G3-09 / G2-02 / EDGE-DIAG Phase 3 critical path.

### Option C — Defer indefinitely with explicit comment (zero LOC, doc-only)
- Update `tick_cognitive_modulator` docstring: "regret_data/dream_data placeholders are awaiting OpportunityTracker/DreamEngine re-implementation per Rust roadmap R02-9 + Python SPEC `docs/references/2026-04-03--agent_cognitive_adaptation_spec_v1_draft.md`. Until then `_compute_stoploss_mult` returns base, `direction` branches no-op."
- Add TODO ticket `G8-01-FUP-REGRET-DREAM-DEFERRED P3` with explicit dependency on R02-9 OR new Python re-impl wave.
- Pros: honest, zero code risk, preserves future option.
- Cons: leaves cognitive adaptation surface dormant — modulator behavior reduced to `consecutive_losses` + `weekly_net_pnl` only.

**PA recommendation**: **Option C** (defer with explicit doc) for this Wave; **Option B** opened as Wave-N future work tied to either (a) R02-9 Rust port readiness OR (b) operator/PM decision to bring back the Python SPEC. Option A risks losing optionality and forces a re-add later.

---

## §5 Hard Boundary Compliance (per skill 16-root-principles-checklist)

This investigation **made zero code changes**. All boundaries vacuously satisfied:

| Boundary | Status | Note |
|---|---|---|
| `live_execution_allowed` / `decision_lease_emitted` / `max_retries=0` | ✅ untouched | Investigation only. |
| Rust IPC schema | ✅ untouched | No change. |
| `OPENCLAW_ALLOW_MAINNET` / `authorization.json` | ✅ untouched | No change. |
| Principle #1 / #3 / #4 / #5 / #6 / #11 | ✅ | No execution path modification. |
| Principle #10 (認知誠實) | ✅ enforced | Refusing to fabricate heuristic that masquerades as `OpportunityTracker`/`DreamEngine` output. Honest "concept dead" verdict per task §3 escalation rule. |
| `feedback_no_dead_params` | ✅ enforced | Avoiding "fake input → fake modulation" anti-pattern; surfaced the dead-concept reality instead of papering over it. |

---

## §6 Verification (per task §4)

- ✅ W1 commit `aca7ee3` 6 sanity tests (`test_strategist_cognitive_w1_fix.py`) — green at HEAD `e106c5d` (worktree base).
- ✅ LOSSES-WIRING `aced662` 8 sanity tests (`test_g8_01_fup_losses_wiring.py`) — green.
- Combined `pytest test_strategist_cognitive_w1_fix.py test_g8_01_fup_losses_wiring.py -q` → **14 passed in 0.05s**.
- 0 schema / 0 IPC / 0 hard boundary touched (no code change written).

---

## §7 Status

- ⏸️ **NOT IMPLEMENTED** in worktree (correct outcome per task §3 escalation rule).
- ✅ Investigation complete: producers confirmed dead concepts post-RC-11.
- ✅ Three options laid out for main session decision (A remove / B re-implement / C defer).
- ✅ PA recommendation: **Option C (defer + explicit doc) for this wave**; reopen Option B when R02-9 Rust port is scheduled or operator commits to a Python re-implementation wave.
- ⏸️ NOT committed (worktree clean except for this report file).

---

## §8 Refs

- Task RFC §3 escalation rule (this task instructions).
- PA RFC `docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-27--g8_01_cognitive_e2e_design.md` §3.1 acknowledged limitation.
- LOSSES-WIRING report `docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-28--g8_01_fup_losses_wiring.md`.
- Cognitive SPEC `docs/references/2026-04-03--agent_cognitive_adaptation_spec_v1_draft.md` (V1.1 + R1, 5 角色審查通過).
- RC-11 deletion `docs/archive/2026-04-12--changelog_archive_pre_0408.md:575`.
- Rust roadmap `docs/rust_migration/02--core_upper.md:68` (R02-9 dream.rs planned).
- `feedback_no_dead_params` memory entry.
