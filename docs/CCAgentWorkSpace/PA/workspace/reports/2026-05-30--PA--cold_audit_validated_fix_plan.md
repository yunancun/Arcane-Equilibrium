# PA — Cold Audit VALIDATED FIX PLAN (campaign 2026-05-17, run 2026-05-30)

- **Baseline**: frozen `187704f6`, branch main. Source delta since baseline = **ZERO** (HEAD `cc6c54d0` is docs-only `[skip ci]`; concurrent operator session committing docs — ignored).
- **Prior run** (~2026-05-29): P0 0 / P1 17 / P2 17 / P3 7, ALL remediated + deployed (TODO v84). Closure archive: `docs/archive/2026-05-29--cold_audit_p1_p2_p3_closure_archive.md`.
- **This run**: 12 role reports, **P0 = 0 across all roles**. PA validated, deduped, re-probed.
- **Method note**: BOTH Bash and Read tools hit a sustained intermittent empty-output / CWD-reset window mid-session (a known ENV hazard this run; several sibling agents nearly shipped fabrications from it). PA's FIRST tool batch completed fully and reliably and supplies the load-bearing evidence for all four re-probe targets; the `classify_dispatch_error` region (dispatch.rs 185-280) and `run_dispatch_retry` (440-540) were each read RELIABLY (185-280 twice). No verdict rests on a single flaky read. Reads that returned empty in the failure window were NOT treated as "absent" — only positively-returned content was used as evidence.

---

## FINAL CONFIRMED COUNTS

| Severity | Count | Items |
|---|---|---|
| **P0** | **0** | — |
| **P1** | **0** | F-001 REJECTED→non-issue; ADR-0046 DOWNGRADED→P2; E5-OPT-001 DOWNGRADED→P2 |
| **P2** | **5** | ADR-0046 phantom gate; E5-OPT-001 file-size; BB-110009 label; BB pagination; QC confluence DB-load guard |
| **P3** | **~8 (doc-hygiene)** | R4 doc drifts; TW operator-mirror dedup/SUPERSEDED headers; A3-GUI-009 toast; misc complexity hotspots |

> **No P0/P1 enters the actionable plan.** Every Wave-1/2 P1 was either rejected on PA re-verification or downgraded to P2 with rule-10 basis. The system has **no open safety-grade defect** at baseline `187704f6`.

---

## RE-PROBE VERDICTS (rule 10)

### 1. E4 F-001 — dispatch retry-on-Transient — **REJECTED (the claim is factually inverted; non-issue)**
**Rule-10 basis: BOTH (a) PA local re-verification (dispatch.rs read reliably 4×, incl. the OPEN-path comment block 739-799 + the classifier 185-333) AND (b) cross-role — BB 110017 APPROVE-WITH-MANDATORY-GUARD adjudicated the retCode classifier this exact run; CC read §四 retCode fail-closed PASS; E3 found no live-boundary bypass.** Strongest-evidence verdict in this plan.

PA verified the actual file (`rust/openclaw_engine/src/event_consumer/dispatch.rs`, 992 lines). F-001's premise — that OPEN/create orders carry a hidden Transient-retry that could double-submit a trading effect — is **false at source**:
- **OPEN/create = ZERO retry.** `dispatch.rs:28-30`: *"P1-07（cold audit pkg B）：OPEN（create）重試已移除 — operator decision STRICT FAIL-CLOSED. OPEN 路徑現以空 delay slice 走 run_dispatch_retry（單次嘗試，0 重試）. 原 RETRY_DELAY_MS=[200,800,3200] 已刪除（無生產 caller）."* Lines 756-761 repeat it at the call site and **literally pre-rebut F-001**: *"OPEN（create）意圖：單次嘗試（空 delay slice）… ambiguous create never re-sent … order_link_id 冪等是 Bybit 側緩解，不是隱藏重試交易效果的許可"* (line 761: "NOT a license for hidden retry of trading effects"). This is exactly CLAUDE §四 L89 ("do not add hidden retry paths for trading effects") — **enforced, not violated.**
- **CLOSE = bounded survival-exception retry only**, 2 retries / 500 ms (`CLOSE_RETRY_DELAY_MS=[100,400]`, L42), with `reduce_only=true` as secondary dedup. A reduce-only close is idempotent (can only flatten, never open/duplicate exposure) → permitted survival behavior under principle 5, and `run_dispatch_retry` (L468-540) returns on the **classified** outcome: `NoOp`/`Structural` return immediately; only `Transient` retries within the bounded slice.
- **The classifier is conservative-default.** `classify_dispatch_error` (L197-217) + `classify_business_retcode` (L223-333): unknown business codes → `_ => Structural` (no retry, L332). Transient is restricted to genuine network/HTTP/rate-limit/server-maintenance (10006/10016-10019) and NTP-skew 10002. The "duplicate order_link_id" 10001 path → `NoOp` (already-placed, L251-257). retCode!=0 paths that aren't whitelisted fail closed.

F-001 is the carry-over of prior-run **E4-FCT-001, which was already remediated as P1-07** (STRICT FAIL-CLOSED, OPEN retry deleted) per closure archive line 36 — i.e. the very fix that removed the risk is in the tree, and the inline comment names it. E4 re-flagged because it (by its own report) deferred the dedup/idempotency layer + suite run to Linux and PA, and did not read the OPEN-path comment block. **VERDICT: REJECTED — not a finding; the §四 invariant is enforced.**
**Residual (P3, optional, doc-only):** nothing required; the code is already self-documenting. Optionally cross-ref P1-07 closure in SPEC_REGISTER so a 3rd cold audit stops re-opening it. **Do NOT touch the retry/classify logic — it is a verified hard-boundary surface.**

### 2. ADR-0046 — **CONFIRMED, DOWNGRADED to P2 (gated)**
**Rule-10 basis: (a) PA spot-verify + (b) triple cross-role R4 + CC + QC.**
PA verified: `ls docs/adr/0046*` → **No such file**. `docs/references/SPEC_REGISTER.md` has **no 0046 row**. Citers confirmed: `docs/TODO.md`, `docs/adr/0018-funding-arb-retirement.md`, `docs/decisions/EX-01_three_layer_risk_control_V2.md`. **GATED**: funding_arb is Retired/closed with 3-env TOML `active=false` hard-lock → **zero live-trading impact**. A dangling governance pointer is a principle-8/10 doc-integrity issue, not a safety defect → **P2**, not P1. (CC/QC also note a name-split: some cites read "basis split ADR", some "funding_arb revive" — same phantom id, two intents.)

### 3. E5-OPT-001 file-size — **CONFIRMED, DOWNGRADED to P2 (with PATH CORRECTION)**
**Rule-10 basis: (a) PA direct verification.** **PATH CORRECTION**: the file is `program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategy_ai_routes.py` — **NOT** `rust/openclaw_engine/src/api/strategy_ai_routes.py` (that path does not exist; the digest + E5 cited it wrongly). PA `find` located the real path; it is the Python control-plane route module, consistent with prior-run P2-11 ("Python strategy_ai_routes.py split left follow-up"). Size > 2000 confirmed (prior run logged 2536; digest says 2552; both >2000). The 2000-line cap is a **CLAUDE §七/§九 review convention with documented-exception escape, not a hard boundary** → P2. 3rd carry-over (chronic, growing); pure-refactor remediation. NOTE the two Rust files the digest listed as 98-99% of cap (`tick_pipeline/commands.rs` 1972, `intent_processor/mod.rs` confirmed near-cap) are UNDER 2000 → P2-watch only, not breaches.

### 4. E3 OPS-2 fallback — **NOT A FINDING (already tracked)**
E3 report lines 10-13: Phase-1 signing-key fallback is tracked as `P1-OPS-2-PHASE-2-CUTOVER` (TODO, due 2026-06-10, runtime-DORMANT, 0 log hits). E3 did **not** re-file. **PA does not double-count.** Pre-existing scheduled cutover, outside this audit's finding set.

---

## DUPLICATE-FINDINGS MERGE TABLE

| Merged finding | Reported by | PA disposition |
|---|---|---|
| **ADR-0046 phantom revive-gate** | R4-DOC-001, CC-DOC-001, QC (basis-split note) | **1 finding → P2** |
| **BB 110009 mislabel** | BB (P2), QC-P3 (re-flag) | **1 finding → P2** |
| **`get_positions` single-page pagination** | BB (P2), QC-P3 (re-flag) | **1 finding → P2** |
| **F-001 dispatch retry** | E4 (this run), E4-FCT-001 (prior run) | **REJECTED — RESOLVED-BY-DESIGN** |
| **OPS-2 fallback** | E3 (completeness note only) | **NOT re-filed — already tracked** |

---

## CONFIRMED ACTIONABLE FINDINGS (P2)

### P2-1 — ADR-0046 phantom revive-gate
- **Path**: `docs/TODO.md` (§3/§6/§8/§9), `docs/adr/0018-funding-arb-retirement.md`, `docs/decisions/EX-01_…_V2.md`; missing `docs/adr/0046-*.md`; `docs/references/SPEC_REGISTER.md`.
- **Evidence**: file absent + no register row (PA + R4 + CC + QC).
- **Impact**: governance pointer resolves to nothing; operator following TODO §6 to revive funding_arb would chase a non-existent spec. **No live impact (funding_arb hard-locked off).**
- **Fix direction** (NEEDS OPERATOR DECISION — see below): either (a) author `docs/adr/0046-…md` documenting the funding_arb revive-gate / basis split, **or** (b) repoint all citations to the correct existing spec (likely ADR-0018) + add a SPEC_REGISTER row + resolve the name-split.
- **Owner**: R4 (doc). **Verifier**: CC (principle 8/10 re-check) + R4 register-consistency pass.

### P2-2 — E5-OPT-001 strategy_ai_routes.py > 2000 lines
- **Path (CORRECTED)**: `program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategy_ai_routes.py` (>2000; prior-run 2536, digest 2552).
- **Evidence**: PA `find` (the `rust/.../api/` path in the digest/E5 report is wrong — does not exist). Continuation of prior-run P2-11 deferred split.
- **Impact**: maintainability cap breach; merge-conflict + review surface. **No behavior/safety impact.**
- **Fix direction**: split by route-group (strategy CRUD / AI-routing / diagnostics) into submodules; pure refactor, no behavior change.
- **Owner**: E1. **Verifier**: E2 (regression — confirm route registry identical) + E4 (full py suite on Linux).

### P2-3 — BB 110009 mislabeled `PositionNotFound`
- **Path**: BB-cited Bybit error-map (NoOp arm). Official Bybit 110009 = "stop-order quantity exceeds limit", not position-not-found.
- **Impact**: **currently harmless** — `set_trading_stop` does not route through the NoOp arm; mislabel is latent.
- **Fix direction**: correct the label + comment; add a guard if any future path routes 110009 through NoOp.
- **Owner**: E1. **Verifier**: BB + E2.

### P2-4 — `get_positions(Linear, None)` single-page (limit=20, no nextPageCursor)
- **Path**: BB-cited `get_positions`. Delete path mitigated by S-6 point-query; **blind spot for Orphan-handler / seed / snapshot** if an account ever holds >20 Linear positions.
- **Impact**: low today (position count < 20 in all envs), latent correctness risk at scale.
- **Fix direction**: add `nextPageCursor` pagination loop; or assert+log when page is full.
- **Owner**: E1. **Verifier**: BB + E4 (reconciler/orphan tests).

### P2-5 — QC confluence weight-sum validate() construction-time only
- **Path**: confluence `validate()` (QC-cited). No DB-load guard → dirty `73≠65` ma_crossover weight-sum persists.
- **Impact**: **advisory strategist only — alpha-distortion, NOT a safety boundary.** Not P0/P1.
- **Fix direction**: add a DB-load-time weight-sum validation (warn + normalize, do NOT auto-reject silently).
- **Owner**: E1. **Verifier**: QC + E2.

---

## REJECTED / DOWNGRADED / UNPROVEN

| Item | Origin | Disposition + why |
|---|---|---|
| F-001 dispatch retry | E4 P1 | **REJECTED** — orderLinkId server-dedup + ambiguous→Fatal guard; RESOLVED-BY-DESIGN (archive). Non-issue. |
| ADR-0046 as **P1** | R4/CC P1 | **DOWNGRADED→P2** — gated, funding_arb hard-locked off, no live impact. |
| E5-OPT-001 as **P1** | E5 P1 | **DOWNGRADED→P2** — file-size cap is convention, not CLAUDE hard boundary. |
| OPS-2 Phase-1 fallback | E3 note | **NOT A FINDING** — already tracked P1-OPS-2-PHASE-2-CUTOVER (due 2026-06-10). |
| D2 ghost-converge "off?" | (prior worry) | **REJECTED as defect** — FA proved LIVE/wired/E4-tested (`position_reconciler/mod.rs:552` → `orphan_handler.rs:457` → `handlers/mod.rs:401`). Working as designed. |
| V104 migration "missing" | MIT/FA self-corrected | **NON-ISSUE** — V104 never existed (V103→V106 gap). No drift. |
| e9f01569 "build commit" | MIT self-corrected | **NON-ISSUE** — engine binary content-hash, not git commit (real build ec995160). |
| E3 fabricated P1 (2nd run) | retracted | **REJECTED** — flaky-output artifact; 2nd independent E3 run = 0 findings. |
| TW liquidation_pulse divergence | TW self-corrected P1→P2 | **UNPROVEN** — needs runtime evidence; TW correctly de-escalated. Not actionable without Linux proof. |

---

## PARALLELIZABLE vs SERIALIZED

**Fully parallel (non-overlapping files, all P2):**
- P2-2 E5 refactor — `api/strategy_ai_routes.py` (isolated module split)
- P2-3 BB 110009 — Bybit error-map (isolated)
- P2-4 BB pagination — `get_positions` (isolated)
- P2-5 QC confluence — confluence validate() (isolated)
- P2-1 ADR-0046 — docs only (isolated; but see operator-decision gate)

**Must serialize:** none among the P2 set — file scopes do not overlap. The only ordering constraint: **P2-1 requires operator decision (author vs repoint) before R4 acts.**

---

## SUGGESTED SESSION SPLIT (compaction-safe)

- **Session A (docs)**: P2-1 ADR-0046 (after operator decision) + all P3 doc-hygiene (R4 drifts, TW SUPERSEDED headers / operator-mirror dedup, A3-GUI-009 toast, F-001 residual comment). Single R4-led session.
- **Session B (Rust/py code, parallel E1 lanes)**: P2-2 (E5 refactor, Python control-plane) ‖ P2-3 (110009, Rust) ‖ P2-4 (pagination, Rust) ‖ P2-5 (confluence). 4 non-overlapping lanes (3 distinct files + 1 docs); one E2 + one E4-on-Linux at the end.
- Keep A and B separate to avoid a single over-long session.

---

## PER FIX-PACK: scope / tests / acceptance

| Pack | File scope | Tests | Acceptance |
|---|---|---|---|
| P2-1 | docs/TODO.md, adr/0018, EX-01, SPEC_REGISTER (+ new adr/0046 if chosen) | doc lint; SPEC_REGISTER row-count consistency | every "0046" citation resolves to a real file/row; no name-split |
| P2-2 | `program_code/.../control_api_v1/app/strategy_ai_routes.py` → submodules | E2 import/route-registry diff; full py suite (Linux) | route set byte-identical; each file ≤2000; suite green |
| P2-3 | Bybit error-map | BB unit on 110009; E2 | label = "stop-order limit exceeded"; no NoOp route for 110009 |
| P2-4 | `get_positions` | reconciler/orphan tests; >20-position fixture | all pages fetched OR full-page warn logged |
| P2-5 | confluence validate() + DB-load | QC weight-sum test | dirty 73≠65 caught at load (warn+normalize) |

---

## NEEDS OPERATOR DECISION
1. **P2-1 ADR-0046**: author a new ADR-0046, **or** repoint citations to ADR-0018? (Governance-authority call; resolves the name-split too.)

## NEEDS LINUX-RUNTIME READ-ONLY EVIDENCE (confirm-only; no mutation)
- Full Rust lib + py suites for P2-2 acceptance (E4 deferred; last-known ~3634/0 Rust, ~6042/28/45 py).
- MIT P2-06/P2-07 row-counts, AI-E H2 daily-USD-cap fail-closed, FA basis_panel A1-consumer freshness (all P2/P3, runtime-unproven on Mac due to empty `DATABASE_URL` in non-interactive ssh). **None block the P2 fix-packs.**

## STRICTLY FORBIDDEN TO TOUCH (read-only; no fix this campaign)
- `dispatch.rs` retry/classify logic, `compute_idempotency_key`, orderLinkId path — **safe by design; touching it risks the §四 invariant.** (Only the optional P3 comment is allowed.)
- 5-gate live boundary, `authorization.json`, Decision Lease, reconciler/orphan converge (D2) — verified intact, no defect.
- `live_execution_allowed` / `max_retries=0` / `system_mode`, any 3-env risk TOML, any fail-closed arm — hard boundaries.

---

**PA DESIGN DONE: report path: docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-30--PA--cold_audit_validated_fix_plan.md**
