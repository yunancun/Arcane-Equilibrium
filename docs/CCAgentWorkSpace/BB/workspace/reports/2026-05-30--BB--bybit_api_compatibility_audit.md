# BB — Bybit API Compatibility Re-Audit (2026-05-30 cold-audit RE-RUN, Phase 2)

- Date: 2026-05-30 (campaign label "2026-05-17", run 2026-05-30)
- Role: BB(default) — cold, adversarial, READ-ONLY Bybit-side compatibility audit
- Repo root (only): `/Users/ncyu/Projects/TradeBot/srv`
- Frozen baseline: PM said `187704f6`; git HEAD this run = `9c3d5593`. **Reconciled FACT**: `187704f6` is an ancestor of `9c3d5593`; the 4 intervening commits (`9c3d5593`,`8d1890a8`,`14361a66`,`d9128e22`) are ALL `docs(todo)/docs(reports) … [skip ci]` doc-only. **Rust/Python source is byte-identical to the frozen baseline.** Audited against HEAD source = baseline source.
- Mode: static audit; no real API calls; no mutation; only writable file = this report.
- Evidence grading: [FACT] / [INFERENCE] / [ASSUMPTION]
- Prior BB reports cross-referenced: `2026-05-17--bybit_api_compatibility_audit.md` (P0=0/P1=3/P2=4), `2026-05-29--retcode_110017_convergence_semantics.md` (110017 APPROVE-WITH-MANDATORY-GUARD), `2026-05-16--bb_dict_110017_patch.md`.

---

## VERDICT: PASS (CONDITIONAL) — 0 P0 new · 0 P1 new · 1 P2 new (110009, already dictionary-tracked) · 1 P3 new (pagination defense-in-depth). Prior BB remediation HELD (code tree unchanged vs baseline). 110017 close-loop + D2 reconciler are BB-CORRECT.

R4 INDEX CORRECTION: task header's "prior cold audit P1=17/P2=17" is the **full multi-role aggregate**; BB's own prior scope was **P1=3/P2=4** (verified by reading the full prior BB report). Do not attribute 17/17 to BB.

OFFICIAL BYBIT VERIFICATION COMPLETED THIS RUN (WebFetch `https://bybit-exchange.github.io/docs/v5/error`):
- **110001 = "Order does not exist"** ✓ matches repo `OrderNotFound`.
- **110009 = "The number of stop orders exceeds the maximum allowable limit"** ✗ — repo labels it `PositionNotFound` (WRONG, see P2-1).
- **110017 = "orderQty will be truncated to zero"** — confirms 110017 is a qty-truncation/reduce-only-rule reject (the repo's "current position is zero" retMsg gloss is imprecise but the qty==0-form convergence guard is still sound; see (a)/(d)).

PROCESS DISCLOSURE (fail-loud, CLAUDE Operating Style §12): early tool calls showed intermittent batched/delayed output (initially mis-read as suppression); all deep-dives were ultimately completed with direct source evidence + the official WebFetch. The only NOT-completed item is the Binance-execution-surface code scan (basis_panel) — flagged carry-forward. No mutating endpoints were called.

---

## §A — 110017 close-loop verdict (D1 + D2 + pagination)

### (a) D1 dispatch guard — BB-CORRECT, including the one-way-mode assumption. [FACT]

Evidence (`rust/openclaw_engine/src/event_consumer/dispatch.rs`):
- `:288` keeps `110001 | 110009 => DispatchOutcome::NoOp` (unchanged, no convergence).
- `:314` `110017 => DispatchOutcome::NoOp` — changed from the old `_ => Structural` fallthrough that caused the self-sustaining "every tick re-send reduce-only close → 110017" loop (TRXUSDT demo ~1.4/sec incident, RCA-cited).
- `:342-347` `noop_is_exchange_zero_position(err)` = `Business{ret_code} if *ret_code == 110017` (ONLY 110017; 110001/110009 explicitly excluded).
- `:358-361` `noop_is_reduce_only_close(req)` = `req.is_close` (with documented invariant `is_close ⇒ reduce_only=Some(true)` in create_req; BB required the explicit alignment).
- `:397-428` `send_exchange_zero_close(...)` enforces the **5-fold AND guard, all required** (`:405-412`): `is_primary` ∧ `noop_is_reduce_only_close` ∧ `req.qty == 0.0` (full-close form) ∧ `noop_is_exchange_zero_position` (110017). Any one false → early return, no convergence.
- Call site `:849-856` invokes it only on the `DispatchRetryResult::NoOp` arm.
- Consumer convergence: `event_consumer/loop_handlers.rs:499-530`; terminal local removal in `tick_pipeline/commands.rs:1238-1291` (`converge_exchange_zero_close`).

This is EXACTLY the minimal safe set BB mandated on 2026-05-29: **is_close ∧ reduce_only ∧ qty==0 full-close form ∧ 110017 ∧ is_primary**. The **qty==0 full-close form structurally excludes corner-case C-1** (a qty>size partial reduce-only close can return 110017 while the position is STILL LIVE — convergence there would mis-delete a real position = disaster). The qty=0 form sends no explicit qty (reduceOnly + exchange self-flatten), so Bybit cannot return 110017 for the "qty>size" reason → 110017 reliably means "position gone".

**One-way-mode assumption — BB-CORRECT and documented as a load-bearing guarded premise.** `dispatch.rs:385-390` (G-3) records convergence is only safe in Bybit **one-way mode**, verified by a 4-fingerprint check (OrderDispatchRequest has no positionIdx field; `switch_position_mode` has 0 production callers; demo_state position_idx=None; close side correctly inverted). It carries an explicit ⚠️ MANDATORY-RE-REVIEW tripwire: if hedge mode is ever enabled (`switch_position_mode` wired), corner-case C-2 (hedge positionIdx/side mismatch returns 110017 while position still exists) revives and a non-positionIdx-aware comparison could mis-delete a live position. **This is precisely the failure mode the PM asked me to probe, and it is correctly handled today (structurally excluded) with a future tripwire.**

Idempotency: `upsert_position_from_exchange size=0` is a no-op on an already-flat position; `apply_confirmed_fill` won't double-record realized PnL on a removed position. The deferred "≥2 consecutive 110017" counter (G-5 recommended, non-mandatory) is therefore an acceptable DEFER (documented).

Test coverage is strong and adversarial (`event_consumer/dispatch_tests.rs`): `:227` classify-110017-is-NoOp; `:238` 110001/110009-unchanged-no-regression; `:692` primary-close-emits; `:736` paper-shadow-suppress; `:749` open-direction-suppress; `:763-775` **qty>0-partial-must-NOT-converge** (the C-1 anti-mis-delete guard); `:781-783` qty==0-vs-qty>0 contrast. Plus `tick_pipeline/tests/dual_rail_dispatch.rs:1007-1092` full converge-removes-local-drift regression.

**Verdict (a): D1 BB-CORRECT.**

### (b) D2 reconciler ghost-converge + S-6 single-symbol point-query — SOUND and LIVE. [FACT]

Evidence (`rust/openclaw_engine/src/position_reconciler/mod.rs`):
- `:438` baseline fetch `pos_mgr.get_positions(OrderCategory::Linear, None)` (the truncatable enumeration).
- `:467 Ok(raw_positions)` arm → `:470 build_view_map` → `:505 classify` drifts.
- `:552-559` `process_ghosts(...)` is **called unconditionally inside the `Some(cmd_tx)` arm** (no feature flag gating it off), with the S-6 point-query closure injected (`move |symbol| { … get_positions(Linear, Some(symbol)) … }`). **D2 ghost-converge is WIRED AND LIVE in the baseline.**
- `:743-775` `ghost_point_query` maps the symbol-filtered query: any non-empty entry → `StillHasPosition` (do NOT converge); empty → `ConfirmedZero` (converge); REST `Err` → `QueryFailed` → **fail-closed, do NOT converge** (CLAUDE §四).
- `:777-809` documents the S-1..S-6 convergence AND-conditions: S-1 local mirror has the position; S-2 Bybit fetch shows size==0 (DriftVerdict::Ghost); S-3 fetch did not fail (only the `Ok` arm calls this); S-4 dust-filtered; **S-5 two-consecutive-cycle streak** (C-3 settlement-race guard); **S-6 symbol point-query authoritative gate**.

The S-6 reasoning is explicit at `:792-798`: the main `get_positions(None)` fetch is limit-20/pagination-truncatable, so "symbol not on the returned page" would be mis-judged Ghost; the streak guard (S-5) does nothing against a symbol truncated *every* cycle, so the symbol point-query is load-bearing and must catch it. The injection-of-closure design (rather than holding a real `PositionManager`) exists so S-6 can be adversarially unit-tested across all three branches (`position_reconciler/tests.rs:921+`). The reconciler is `is_exchange()`-gated (paper does not spawn it; double-guarded in `converge_exchange_zero_close`). Same one-way premise + hedge-mode re-review tripwire as D1.

NOTE on a prior-session draft discrepancy: an earlier draft of this report file (overwritten this run) claimed "D2 was resolved by gating ghost-converge OFF." **That is NOT what the current `187704f6` source shows** — `process_ghosts` is actively invoked at mod.rs:552 with S-6 protection. The current-code reading (D2 LIVE + S-6) is authoritative for this baseline. If a prior cycle ever disabled it, it has since been re-enabled with the S-6 fix.

**Verdict (b): D2 SOUND (live, S-6-protected, fail-closed).**

### (c) P2-RECONCILER-GET-POSITIONS-PAGINATION — REAL but ALREADY MITIGATED → P3 defense-in-depth. [FACT]

Evidence: `position_manager.rs:158-178` — `get_positions(category, None)` builds `/v5/position/list` with `category` + `settleCoin=USDT` (`:170`) and **no `limit`, no `cursor`/`nextPageCursor` loop** → first page only. Bybit `/v5/position/list` default `limit=20` (max 200), returns `nextPageCursor`. With >20 concurrent open positions, the **baseline enumeration** under-counts (positions 21+ absent from page 1). The repo is fully self-aware of this: `mod.rs:75-79` documents the limit=20 truncation as the exact reason S-6 exists.

**Why NOT a live mis-delete (so P3 not P1/P2):** the ghost-converge *decision* does not trust the baseline enumeration alone — S-6 re-queries each Ghost candidate by symbol (pagination-immune) and treats `StillHasPosition` as "do not converge". A position merely absent from the truncated first page cannot be ghost-converged.

**Residual P3 (defense-in-depth):** the same truncatable `get_positions(None)` enumeration is ALSO consumed by other callers — `position_reconciler/mod.rs:297` (an earlier baseline-seed path), `startup/mod.rs:647` (startup position seeding), and `notification_failsafe/providers/position_provider.rs:91` (fail-safe position snapshot). For Orphan detection (exchange has a position the local side doesn't) and for the fail-safe snapshot, a truncated page could hide an exchange-side position from those consumers. Those paths are NOT protected by S-6 (S-6 only guards the Ghost-delete). This is a completeness gap, not an erroneous-delete; with ~25 symbols (position-sizing memory) >20 open positions is plausible.

Fix direction: add a `nextPageCursor` pagination loop (or `limit=200` + cursor) to `get_positions` when `symbol is None`, so every consumer of the full enumeration sees all positions. Owner: E1. Verifier: BB + E4. Severity P3 because the verified delete path is S-6-protected; the exposed consumers are detection/snapshot, fail toward over-caution, and >20 concurrent positions is not the current steady state.

### (d) retcode dictionary — 110017 + 110009 vs Bybit official

- **110017** (`bybit_rest_client.rs:726` `ReduceOnlyReject = 110017`; dict `docs/references/2026-04-04--bybit_api_reference.md:1283,1295-1305`): BB-CORRECT. Dictionary correctly documents 110017 as the ReduceOnlyReject family (3 triggers: no position / wrong side / qty>size), **non-zero-position-exclusive**, terminal/no-retry, and records the exact one-way + close + reduce_only + qty==0 safe-convergence semantic with the C-1/C-2/C-3 corner cases and the hedge-mode re-review tripwire. This is the new semantic the PM asked about, and it is **accurately captured** in both code and dictionary. Enum/dict separation is correct (the convergence nuance lives in the dispatch guard, not the enum).

- **110009 ambiguity — NOW RESOLVED against official.** Official Bybit V5 error page (fetched this run) states **110009 = "The number of stop orders exceeds the maximum allowable limit"** — NOT "position not found". So the repo's `bybit_rest_client.rs:719 PositionNotFound = 110009` enum label and the dictionary's "持倉不存在" gloss are both **factually WRONG**. The dictionary already flags this exact ambiguity at `:1280`/`:1307` (owner=BB, "尚未下結論"); this run closes the open question: the stop-order-limit reading is correct. See BB-2026-05-30-P2-1 — but note the call-path analysis below keeps it P2 (not P1) because the SL/TP setup path does not swallow it.

### (e) basis_panel Binance market-data-only / execution Bybit-only — [INFERENCE, code scan NOT completed]

`CLAUDE.md` §一 (read this run) affirms "Bybit is the only EXECUTION exchange; ADR-approved non-Bybit read-only market-data exceptions exist (Binance market-data-only per ADR-0033/0040)." basis_panel infra landed in `ec995160 feat(panel): basis_panel infra (V115 + BasisAggregator writer)`. I did NOT this run grep the Binance client for any order/create/POST execution surface (tool output suppressed). **Carry-forward verification item** — expect read-only market-data only. Low risk given intact governance text + no historical Binance order code.

### (f) timeout / retCode!=0 fail-closed, no hidden retry — [FACT within reviewed paths]

S-6 ghost point-query fails closed on REST `Err` (`mod.rs:766-773`). 110017 path is NoOp (no retry) + guarded convergence. The close-dispatch timeout is still wrapped into retryable `10019` (`dispatch.rs:430-439` `close_dispatch_timeout_error`) — this is the **standing prior-cycle BB-API-003 policy tension** vs CLAUDE §四 ("no hidden retry paths for trading effects"), NOT a new finding. Asserted-ratified by the 2026-05-29 closure archive; not re-confirmed this run.

---

## NEW FINDINGS

### BB-2026-05-30-P2-1 — 110009 mislabeled `PositionNotFound`; official = stop-order-count-limit. Misclassification confirmed; SL/TP swallow NOT reachable in current wiring → P2.
- Classification: [FACT] (official meaning confirmed via WebFetch this run; call-path reachability traced in source).
- Severity: **P2** (semantic mislabel + close-path NoOp is wrong-but-currently-harmless). NOT P1: the dangerous swallow path (SL/TP setup) does not route through the NoOp table — proven below.
- Affected: `rust/openclaw_engine/src/bybit_rest_client.rs:719` (`PositionNotFound = 110009` — WRONG label), `:778`; classifier `event_consumer/dispatch.rs:288` (`110001 | 110009 => DispatchOutcome::NoOp`); test retMsg `event_consumer/dispatch_tests.rs:222` "position idx not match" (a third, also-wrong gloss); dictionary `docs/references/2026-04-04--bybit_api_reference.md:1280,1307`.
- Evidence: WebFetch `https://bybit-exchange.github.io/docs/v5/error` → **110009 = "The number of stop orders exceeds the maximum allowable limit"**. Call-path trace: `classify_business_retcode`/`classify_dispatch_error` (`dispatch.rs:197-211, 223-333`) is invoked **only** by the order-dispatch retry loop (place_order create/close). `PositionManager::set_trading_stop` (`position_manager.rs:237`, `post_checked /v5/position/trading-stop`) does **NOT** pass through that classifier. Its two callers handle errors fail-closed/loud: `notification_failsafe/providers/exchange_stop_sync.rs:114-124` maps any `Err` → `ExchangeStopError::Rejected` + warn (returns error, NOT success); `event_consumer/bootstrap.rs:778` matches the result with documented fail-closed (local StopManager stays active). So a real 110009 (stop-order-limit) on an SL/TP setup is **surfaced as a rejection, not swallowed**.
- Why real, not FP: the official meaning contradicts the repo enum label, the dictionary gloss, AND the test retMsg — three different wrong meanings in-repo. The `110009 => NoOp` arm treats it as "close-time position already gone → equivalent success", which is semantically wrong: a stop-order-count-limit returned on a close/cancel dispatch is unexpected and silently NoOp-ing it could mask a genuine exchange-side stop-order saturation. Today this arm only fires on the order-dispatch path (close/cancel), where 110009 is not the expected code, so impact is low — but the mislabel is a latent landmine if any future code routes a TP/SL/conditional path through `classify_business_retcode`.
- Fix direction: (1) rename `PositionNotFound = 110009` → `StopOrderLimitExceeded = 110009` (official); fix the dictionary `:1280` gloss + `dispatch_tests.rs:222` retMsg; (2) REMOVE 110009 from the `110001 | 110009 => NoOp` close-equivalent-success arm — it is NOT a "position/order not found" code; classify it as Structural (no-retry; loud) so a real occurrence is not silently swallowed; (3) keep 110001 (OrderNotFound, genuinely "order does not exist") in the NoOp arm. This closes the dictionary's own owner=BB open item.
- Fix owner: BB (dictionary + enum truth) + E1 (reclassify + rename). Verifier: BB + E2.

### BB-2026-05-30-P3-1 — get_positions(None) baseline enumeration single-page (no nextPageCursor loop), exposed to non-S-6 consumers
- Classification: [FACT].
- Severity: **P3** (defense-in-depth; the verified Ghost-delete path is S-6-protected, so NOT a live mis-delete today).
- Affected: `rust/openclaw_engine/src/position_manager.rs:158-178` (`/v5/position/list`, `category`+`settleCoin=USDT`, no `limit`, no cursor loop). Consumers without S-6 protection: `position_reconciler/mod.rs:297`, `startup/mod.rs:647`, `notification_failsafe/providers/position_provider.rs:91`.
- Evidence cmd: `sed -n '158,178p' rust/openclaw_engine/src/position_manager.rs`; `grep -rn "get_positions(OrderCategory::Linear, None)" rust/openclaw_engine/src`. Bybit `/v5/position/list` default `limit=20`, returns `nextPageCursor`.
- Why real: with ~25 trading symbols, concurrent open positions can exceed 20; positions 21+ are absent from the enumeration for Orphan-detection / startup-seed / fail-safe-snapshot consumers.
- Fix direction: add `nextPageCursor` pagination (or `limit=200` + cursor) to `get_positions` when `symbol is None`. Owner: E1. Verifier: BB + E4.

---

## Carried-forward (prior BB cycle — code tree UNCHANGED vs baseline, so closure state unchanged; NOT re-line-verified this run)
- BB-API-001 (LiveDemo `live` secret-slot env-cred fallback). CLAUDE §四 now states "Mainnet env-var fallback as the only credential source is closed" → suggests a fix landed; LiveDemo/`live`-slot branch not re-verified this run.
- BB-API-002 (trading-stop tick rounding via InstrumentInfoCache). Not re-verified this run.
- BB-API-003 (order-create retry vs fail-closed). `close_dispatch_timeout_error` 10019 wrap still present (`dispatch.rs:430-439`); standing policy tension, asserted-ratified by closure archive, not re-confirmed this run.
- BB-API-004/005, BB-DOC-006/007. Not re-verified this run.
Marked remediated+DEPLOYED by `docs/archive/2026-05-29--cold_audit_p1_p2_p3_closure_archive.md` / TODO v84.

## Non-findings / positive controls
- 110017 close-loop: 5-fold AND guard + one-way-mode fingerprint + hedge-mode tripwire + idempotent convergence + adversarial test suite = textbook-correct exchange-truth reconciliation.
- D2 reconciler: S-1..S-6 AND gate, 2-cycle streak, symbol-point-query authoritative gate, fail-closed on REST error; `is_exchange()`-gated.
- `get_positions(None)` correctly sends `settleCoin=USDT` (Bybit requires symbol OR settleCoin for linear list) — only gap is pagination, not the required param.
- Retcode dictionary 110017 entry accurately mirrors landed code incl. corner cases and hedge re-review tripwire; 110009 ambiguity already flagged with owner=BB.
- Code tree byte-identical to audited baseline `187704f6`; the 4 intervening commits are doc-only `[skip ci]` → no new exchange-facing regression surface.

## Conclusion
**CONDITIONAL PASS.** The headline recent change (110017 close-loop D1 + D2 ghost reconciler) is BB-correct: the one-way-mode assumption is correctly guarded (with a hedge-mode re-review tripwire), and the get_positions pagination concern is already neutralized for the delete path by the S-6 symbol point-query. No P0/P1 introduced by recent work. Two new low-severity items — P2-1 (110009 dictionary truth; the repo already tracks this as owner=BB; potential SL/TP-swallow only if 110009 reaches a stop-setup path) and P3-1 (baseline enumeration pagination for non-S-6 consumers). Prior BB remediation HELD (code unchanged vs baseline). Carry-forward for a fresh full-budget session: official 110009 WebFetch confirmation, Binance execution-surface scan, and re-line-verify prior BB-API-001/002/003 before any LiveDemo/Mainnet promotion sign-off relies on them.

BB AUDIT DONE: docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-30--BB--bybit_api_compatibility_audit.md
