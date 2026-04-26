# E2 Tier 5 Batch Review — 2026-04-26

## Scope

7 commits (`af48ee1..f2ed286`) covering 3 sequential PM-dispatched tasks:

| # | Commit | Task | Owner |
|---|---|---|---|
| 1 | `af48ee1` | EXIT-FEATURES-WRITER-BUG-1-FIX main (10 files / +755 / -19) | E1 |
| 2 | `83456e5` | EXIT-FEATURES-FIX regression-guard (1 file / +18 / -13) | E1 |
| 3 | `00a9679` | EXIT-FEATURES-FIX docs (E1 memory + workspace report) | E1 |
| 4 | `5943337` | G3-08-PHASE-1C-WIRING (5 files / +340 / -9) | E1 |
| 5 | `deee78e` | G3-08-PHASE-1C E1 memory append | E1 |
| 6 | `9120948` | G3-08 Phase 2 H1+H3 接入 (6 files / +1822 / -192) | E1 |
| 7 | `f2ed286` | G3-08 Phase 2 E1 memory | E1 |

Time-order verified (oldest 5943337 15:43 → newest f2ed286 16:01); af48ee1 parent = `deee78e` (Phase 1C done first, then EXIT-FEATURES, then Phase 2 H1+H3). 3 tasks are sequential **NOT** cohesive.

## 8-Axis Audit Result

| Axis | Status | Notes |
|---|---|---|
| **A** 跨平台 (`/home/ncyu` / `/Users/[^/]+`) | **PASS** | 7/7 commits 0 hit (production + docs) |
| **B** 雙語注釋 (MODULE_NOTE / docstring / 中英對照) | **PASS** | 11/11 modified files have ≥5 中 markers + MODULE_NOTE; PA spec §10.2 prompt template fully reflected |
| **C** 範圍嚴守 (PA design plan ↔ E1 changes) | **PASS** | EXIT-FEATURES-FIX cohesive 1+2 per MIT §5 (A1+A3+B1) / G3-08 1C exactly per PA §10.1 step 7-8 + 附錄 A / Phase 2 H1+H3 only (Phase 3 H2/H4/H5 + Phase 4 5-Agent untouched) |
| **D** SQL Guard (V### migration) | **PASS** | 0 new migration in this batch (last is V025 pre-existing); EXIT-FEATURES-FIX has no schema change per MIT §5 path 1+2 design |
| **E** Hot-path & architecture | **PASS-with-FOLLOWUP** | RCA-A layered Gate 1+2 covers all dust spiral scenarios; RCA-B partial_reduce_tag exact-match safer than MIT B1 `realized_pnl==0`; G3-08 1C condition-spawn pattern correct; Phase 2 hooks fire-and-forget no blocking |
| **F** Test coverage | **PASS** | engine lib `2210/0` (baseline 2198 + 12 EXIT-FEATURES); integration `12/0`; pytest `75/0` (G3-08 Phase 2 17+22+22 = 61 new + 14 prior); strategist regression `36/36` |
| **G** PA design plan 對齊 | **PASS-with-MEDIUM** | EXIT-FEATURES → MIT §5 cohesive 1+2 ✅; G3-08 1C → PA §10.1 step 7-8 ✅; Phase 2 → PA §10.2 ✅; **H3 schema mismatch** between Python keys + Rust H3RouteStats fields (G308P2-MED-1) |
| **H** MIT audit 對齊 | **PASS** | E1 採 A1+A3+B1' (modified B1 using exact tag match) > MIT recommended; healthcheck [3] 24h grace acknowledged; ML-TRAINING-DATA-HYGIENE-1 P2 ticket scope-split correct (not in this PR) |

## Per-Commit Audit

### Commit 1: `af48ee1` EXIT-FEATURES-WRITER-BUG-1-FIX main — **PASS-with-LOW**

**Diff stats**: 10 files / +755 / -19. Span: `risk_config.rs` schema (+46), `risk_config_tests.rs` (+103), `event_consumer/bootstrap.rs` (+23), `on_tick/helpers.rs` (+133), `on_tick/step_0_fast_track.rs` (+85), `pipeline_helpers.rs` (+20), test files (+341 across 3), `risk_config_live.toml` (+9). Demo + paper TOML inherit `ft_dust_qty_floor_usd` default via serde — TOML symmetry preserved.

**RCA-A 修法 audit**:
1. **Gate 1 (USD floor)** — `step_0_fast_track.rs:317-326`. Active in ALL branches via `if ft_dust_qty_floor_usd > 0.0 || ft_min_notional_ratio > 0.0`. Closes the legacy `entry_notional == 0` fail-open hole that drove the STRKUSDT 37-halve dust spiral. ✅ correct design.
2. **Gate 2 (ratio floor)** — Inactive on `entry_notional <= 0` (no baseline). Falls through to Gate 1 protection only. ✅ ratio gate pre-FIX behaviour preserved for genuine legacy real positions.
3. **`ft_dust_qty_floor_usd` schema** — `risk_config.rs:374-394` `[serde(default = "default_ft_dust_qty_floor_usd")]` + validate `[0, 100_000]` + reject NaN/Inf. ✅ hot-reloadable via `patch_risk_config`.
4. **Bootstrap `migrate_legacy_entry_notional`** — `event_consumer/bootstrap.rs:291-313`. Idempotent (touches only `entry_notional <= 0.0 && qty > 0`). ✅ defence-in-depth.
5. **Stale tick fall-through** — `last_price <= 0.0 → return true`. Position not halved on stale data; re-evaluates next tick. ✅ correct safety semantics.

**RCA-B 修法 audit**:
1. **`is_partial_reduce_tag`** — `on_tick/helpers.rs:74-78`. Exact-match `close_tag == "risk_close:fast_track_reduce_half"`. ✅ no false positives on PHYS-LOCK / strategy exit / hard stop / etc.
2. **`emit_close_fill` gate** — `pipeline_helpers.rs:217-236`. `if !is_partial_reduce_tag(close_tag) → emit EF`. ✅ trading.fills still written (operator visibility, PnL accounting); only EF writer skips. PHYS-LOCK FullClose / hard stop / TP / strategy exit all `close_position*` → full close → still emit EF (verified by 3 regression tests).
3. **MIT §5 path 2 B1 vs E1 B1' variant** — MIT proposed `if realized_pnl == 0 → skip`. E1 chose `if is_partial_reduce_tag(close_tag) → skip`. **E1's variant is more precise** because zero-PnL edge cases on full closes still emit EF correctly (e.g. break-even close still wants EF for ML signal of "neutral round-trip"). ✅ improvement over MIT recommendation.

**Findings**:
- **LOW (T5.1-LOW-1)**: `on_tick/helpers.rs` is 1315 lines, exceeding §九 1200 hard cap. Pre-existing 1182 + af48ee1 +133. `cargo lib 2210/0` proves no functional regression but file-size policy violated. **ACCEPT-with-FOLLOWUP** per Tier 4 G9-02 ws_client.rs methodology (hot-path surgical change, sibling pattern feasible: `helpers/{tags.rs, phys_lock.rs, shadow.rs}`). Recommend PM open `EXIT-FEATURES-FIX-FUP-HELPERS-RS-SPLIT` ticket (~0.5d, Wave 4 G5 refactor).
- **PASS** on cross-platform (af48ee1 0 hit `/home/ncyu` `/Users/[^/]+`).

### Commit 2: `83456e5` EXIT-FEATURES-FIX regression-guard — **PASS**

Follow-up to af48ee1 — RUST-DOUBLE-PREFIX-1 regression guard `no_new_literal_risk_close_phys_lock_outside_helpers_rs` caught a bare `"risk_close:phys_lock_gate4_giveback"` literal in the new test `..._phys_lock_full_close_still_emits_ef`. E1 swapped to `"risk_close:halt_session_drawdown"` (semantically equivalent for RCA-B coverage: full-close path must continue to emit EF; partial-reduce is the only category that skips). exit_source maps to `HaltSession` not `Physical`. ✅ test intent preserved.

### Commit 3: `00a9679` EXIT-FEATURES-FIX E1 memory + workspace report — **PASS**

`docs/CCAgentWorkSpace/E1/memory.md` +29 lines + workspace report `2026-04-26--exit_features_writer_bug_fix.md` +51. Pure docs; no code. ✅ standard E1 memory pattern.

### Commit 4: `5943337` G3-08-PHASE-1C-WIRING — **PASS-with-LOW**

**Diff stats**: 5 files / +340 / -9. `CLAUDE.md` +2 (singleton table), `strategy_wiring.py` +82, `checks_derived.py` +237 ([20] check + [19] note), `runner.py` +24 (19→20), `__init__.py` +2 imports.

**Architecture audit**:
1. **`strategy_wiring.py:507-588` condition spawn** — Mirrors G3-03 ExecutorConfigCache pattern (commit `c80d75c`) but resource flow flipped: G3-03 Python pulls Rust config, G3-08 Python pushes hint. ✅ DEFAULT-OFF env=0 zero overhead (`is_gateway_enabled() ↔ "1"` strict eq → singleton stays None → `invalidate_async()` no-op early return). Race: env flipped between `is_gateway_enabled()` + `init_h_state_invalidator()` → `_H_STATE_INVALIDATOR = None` (debug log). ✅ clean fail-closed.
2. **CLAUDE.md §九 singleton table** — +2 rows (`_H_STATE_INVALIDATOR/_LOCK` + `HStateCacheSlot`). Format aligned with existing entries (path, init pattern, runtime semantics, Phase 1 dormant note). ✅ correct registry.
3. **healthcheck [20]** — `checks_derived.py:474-820`. Pure-Python (no DB cursor / no live IPC roundtrip). Three-state ladder: env=0 PASS-skip / env=1 verify 3 invariants (route registered + modules importable + stub canonical) → PASS / invariant 3 fail WARN / invariant 1 or 2 fail FAIL. ✅ aligns with [16] strategist_cycle_fresh "log-tail-parse" philosophy (cron without HMAC secret coupling).
4. **runner.py 19→20** — Description bump + invocation order after [19]. ✅ docstring + execution path consistent.

**Smoke test independent run**:
- `OPENCLAW_H_STATE_GATEWAY=unset` → PASS (Phase 1 dormant by design)
- `OPENCLAW_H_STATE_GATEWAY=1` post-9120948 → WARN (`stub no longer Phase 1 shape, version=1, h_states_keys=2`) — see Finding T5.2-LOW-1.

**Findings**:
- **LOW (T5.2-LOW-1)**: [20] expected `version=0 + h_states={}` (Phase 1 stub). Commit 9120948 (15 minutes after 5943337) upgraded `build_h_state_full_response()` to `version=1 + real H1+H3 snapshots` when env=1. **[20] env=1 path now permanently WARN** unless operator updates expected values. E1's WARN message ("Phase 2-4 progress? update [20] expectations") correctly absorbs the case but **[20] expected values should be synced**. This is the same time-hazard pattern from Phase 1+2 batch review (commit B invalidates commit A doc within 19min, but commit msg's "Banner removable" action not executed). Recommend PM open `G3-08-PHASE-1C-FUP-CHECK20-SYNC` ticket (~10min — bump expected version 0→1 + h_states_keys 0→2 + add Phase 3-4 evolution note).

### Commit 5: `deee78e` G3-08 Phase 1C E1 memory — **PASS**

`docs/CCAgentWorkSpace/E1/memory.md` +35 lines (Phase 1C retrospective + 9 lessons). Pure docs.

### Commit 6: `9120948` G3-08 Phase 2 H1+H3 接入 — **PASS-with-MEDIUM**

**Diff stats**: 6 files / +1822 / -192. `h1_thought_gate.py` +94, `model_router.py` +172, `h_state_query_handler.py` +268 (Phase 1 stub → Phase 2 real H1+H3 pull), test files +1142 (test_h1_thought_gate +315 / test_model_router +366 / test_h_state_query_handler +461 modified+upgraded).

**Architecture audit**:
1. **`h1_thought_gate.py` invalidate_async hooks** — On each branch (budget/complexity/cooldown skip + ai_call_allowed pass) fire-and-forget `invalidate_async("h1.<reason>")`. Hook placement at **public method exits** in `check()` not in `_check_budget()` / `_check_cooldown()` private helpers. ✅ correct boundary placement.
2. **`h1_thought_gate.get_h1_snapshot()`** — Pure-read; returns `total_decisions / ai_calls_allowed / budget_skip / complexity_skip / cooldown_skip / cooldown_dict_size / budget_remaining_pct`. Acquires only `_h1_local_lock` (no cross-module locking). budget_remaining_pct fail-open per `_check_budget()` semantics on tracker error. ✅ correct.
3. **`model_router.py` invalidate_async hooks** — In `_record_route()` (called from `route()` exit branches) + `check_l2_cache` hit/expired branches + `_store_l2_result`. ✅ all hooks fire-and-forget at public method exits.
4. **`model_router.get_h3_snapshot()`** — Pure-read; acquires `_routing_lock` then `_l2_cache_lock` (consistent ordering). Returns 10 keys (see Finding T5.3-MED-1).
5. **`h_state_query_handler.build_h_state_full_response`** — Phase 1 stub → Phase 2 lazy-imports `strategy_wiring` + pulls `STRATEGIST_AGENT._h1_gate.get_h1_snapshot()` + `STRATEGIST_AGENT._model_router.get_h3_snapshot()`. Schema version 0 → 1 when populated. env=0 / singleton-not-wired / snapshot-raise paths fall back to empty shell + version=0. include filter honoured per bucket. ✅ never-raises contract preserved via `_safe_snapshot`.
6. **`_safe_snapshot` defensive helper** — Try-except fallback on attr-missing / method-missing / non-callable / non-dict return / any raise. ✅ broad except justified by IPC handler contract (must NOT crash on snapshot bug).
7. **DEFAULT-OFF env=0 H1/H3 behavior** — singleton stays None → invalidate_async no-op + module-level early return. `h_state_invalidator.invalidate_async(reason)` on env=0 path: 1 dict lookup + 1 if-None branch ≈ <1µs. ✅ zero overhead claim valid.
8. **Strategist regression** — 36/36 PASS (test_strategist_agent.py). H1/H3 modifications additive (new local stats + invalidate_async hooks + get_*_snapshot methods); existing `check()` / `route()` semantics unchanged. ✅ no business logic regression.

**Findings**:
- **MEDIUM (T5.3-MED-1) — H3 schema mismatch (DORMANT)**:
  - Python `model_router.get_h3_snapshot()` keys: `total_routes / l1_9b_count / l1_27b_count / l1_5_count / l2_count / budget_denied_count / l2_cache_hit / l2_cache_expired / l2_cache_stored / cache_size`.
  - Rust `H3RouteStats` (PA §5.2 + `h_state_cache/types.rs:78-92`) fields: `l1_9b / l1_27b / l1_5 / l2 / cache_size / cache_hit / cache_expired`.
  - **0/7 Rust fields match Python keys** (Python has `_count` suffix + extra `total_routes / budget_denied_count / l2_cache_stored` not in Rust).
  - **Runtime impact = 0**: Rust still uses `StubHStateFetcher` (production at `main_boot_tasks.rs:385`). Phase 2 deliberately keeps Rust on stub (PA §10.2 +Phase 2 prompt template line 105 `parked here as RealHStateFetcher stub`).
  - **Future-blocking**: When Phase 3+ wires real EngineIPCClient fetcher, Rust serde will silently default all H3 fields to 0 due to key mismatch (forward-compat unknown fields ignored). **Silent regression latent in schema contract**.
  - **Fix paths**:
    - **A (Python rename)**: `total_routes/l1_9b_count/cache_*` → drop `_count`/`l2_` prefixes, align Python keys to Rust schema. Cheap (model_router.py only).
    - **B (Rust serde rename)**: Add `#[serde(rename = "l1_9b_count")]` to each Rust field. Less invasive but PA §5.2 schema becomes 2-vocabulary.
    - **C (PA spec update)**: Update PA §5.2 H3RouteStats to match Python's expanded keys (add total_routes/budget_denied_count/l2_cache_stored to Rust struct + drop `_count` from Python or align both sides).
  - Recommend PM open `G3-08-PHASE-2-FUP-H3-SCHEMA-ALIGN` ticket (~30min, before Phase 3 lands real fetcher). PA-led design decision (A vs B vs C) is preferred ownership.

- **MEDIUM (T5.3-MED-2) — 私有屬性穿透** (CLAUDE.md §九 E2 必查 #8):
  - `h_state_query_handler.py:247-249` uses `getattr(strategist, "_h1_gate", None)` + `getattr(strategist, "_model_router", None)` → directly reading StrategistAgent **private** attributes (underscore prefix is Python convention for "internal").
  - PA design §5.1 spec line 397-405 expects PUBLIC facade pattern: `STRATEGIST_AGENT.get_h1_stats_snapshot()` + `STRATEGIST_AGENT.get_h3_route_stats_snapshot()`. E1 deviated from PA spec by skipping the facade layer.
  - **Functional impact = 0** (`_safe_snapshot` defensive on missing attr). **Code quality / contract violation**: subsequent E1 / refactor working on `strategist_agent.py` could rename `_h1_gate` → `_thought_gate` without realising h_state_query_handler depends on the exact name.
  - **Recommend RETURN to E1**: add public facade methods on `StrategistAgent`:
    ```python
    def get_h1_stats_snapshot(self) -> dict:
        return self._h1_gate.get_h1_snapshot()

    def get_h3_route_stats_snapshot(self) -> dict:
        return self._model_router.get_h3_snapshot()
    ```
    Then update `h_state_query_handler.py:247-249` to call `getattr(strategist, "get_h1_stats_snapshot", None)` / `get_h3_route_stats_snapshot`. Aligns with PA §5.1 spec naming + closes §九 #8 violation.

- **LOW (T5.3-LOW-1)**: `model_router.py:_record_route` line ~256-261 has redundant f-string — `counter_key = f"l1_9b_count" if tier == "l1_9b" else f"l1_27b_count" if ...`. The f-prefix has no placeholder; functionally equivalent to plain string but lints flag as `f-string without any placeholders`. Cosmetic only; **E2 directly fixes** in single `cd srv && git commit` together with this report (or PM accepts as-is, future polish).

### Commit 7: `f2ed286` G3-08 Phase 2 E1 memory — **PASS**

`docs/CCAgentWorkSpace/E1/memory.md` +50 lines (Phase 2 retrospective + 8 lessons). Pure docs.

## Summary Table

| Task | Verdict | LOW | MEDIUM | HIGH | CRITICAL | Action |
|---|---|---|---|---|---|---|
| **T5.1 EXIT-FEATURES-FIX** (af48ee1+83456e5+00a9679) | **PASS-with-LOW** | 1 (helpers.rs 1315 §九 violation, ACCEPT+FUP) | 0 | 0 | 0 | PASS to E4 / QA / PM Sign-off |
| **T5.2 G3-08-PHASE-1C-WIRING** (5943337+deee78e) | **PASS-with-LOW** | 1 ([20] expected sync after 9120948) | 0 | 0 | 0 | PASS to E4 / QA / PM Sign-off |
| **T5.3 G3-08 Phase 2 H1+H3** (9120948+f2ed286) | **PASS-with-MEDIUM** | 1 (redundant f-string) | 2 (T5.3-MED-1 H3 schema mismatch dormant; T5.3-MED-2 private-attr leakage CLAUDE §九 #8) | 0 | 0 | RETURN to E1 for T5.3-MED-2 facade fix; OR PASS-with-FOLLOWUP if PM accepts as future polish |
| **Total** | 7 commits | **3 LOW** | **2 MEDIUM** | 0 HIGH | 0 CRITICAL | — |

## E2 自行修補（直接修，不退回 E1）

僅明顯 lint / typo / 既有 dead import — 本批次 E2 未直接修任何代碼。redundant f-string (T5.3-LOW-1) 屬模糊邊界（不算 lint 錯誤，但 ruff PLF0901 / W1309 會報），E2 留給 PM 決定是否強制修。

## 退回 E1 修復清單（優先序）

1. **T5.3-MED-2 (CLAUDE §九 #8 violation)** — `h_state_query_handler.py:247-249` 私有屬性穿透。建議 E1 加 public facade method `StrategistAgent.get_h1_stats_snapshot() / get_h3_route_stats_snapshot()` 並改 h_state_query_handler 呼叫公有 method。對齊 PA §5.1 spec naming. ETA ~15min.

   **若 PM 接受 deferred to follow-up ticket** → 改 ACCEPT-with-FOLLOWUP，建議 PM 開 `G3-08-PHASE-2-FUP-PRIVATE-ATTR-FACADE` (P2)。

## ACCEPT-with-FOLLOWUP（PM 開新 ticket，不退回 E1）

1. **T5.1-LOW-1 helpers.rs 1315 §九 violation** — Hot-path 抽 helper surgical 不可隨便拆，ACCEPT 對齊 G9-02 ws_client.rs 1227 方法論. PM 開 `EXIT-FEATURES-FIX-FUP-HELPERS-RS-SPLIT` (~0.5d, Wave 4 G5 refactor).
2. **T5.2-LOW-1 healthcheck [20] expected sync** — env=1 環境永遠 WARN 至 expectations 更新. PM 開 `G3-08-PHASE-1C-FUP-CHECK20-SYNC` (~10min) 升 expected `version=0→1` + `h_states_keys=0→2` + Phase 3-4 evolution note.
3. **T5.3-MED-1 H3 schema mismatch (DORMANT)** — Phase 3+ 接 real fetcher 時 silent regression 風險. PM 開 `G3-08-PHASE-2-FUP-H3-SCHEMA-ALIGN` (~30min, before Phase 3).

## 最終推薦

- **T5.1 EXIT-FEATURES-FIX (3 commits)** — **PASS to E4 / QA / PM Sign-off**. RCA-A + RCA-B 修法完整對齊 MIT §5 推薦 + B1' 改良；engine lib 2210/0 + integration 12/0；helpers.rs §九 violation accept-with-followup.
- **T5.2 G3-08-PHASE-1C-WIRING (2 commits)** — **PASS to E4 / QA / PM Sign-off**. condition spawn / DEFAULT-OFF / healthcheck [20] / CLAUDE.md §九 全達標；[20] expected sync follow-up minor.
- **T5.3 G3-08 Phase 2 H1+H3 (2 commits)** —
  - **選項 A**: **RETURN to E1** for T5.3-MED-2 facade fix (~15min); after re-E2 → PASS. **嚴格遵守 §九 #8 必查項**.
  - **選項 B**: **PASS-with-FOLLOWUP** if PM accepts T5.3-MED-2 as deferred. CLAUDE.md §九 #8 違規屬 contract 失誤但 functional impact = 0 (defensive `_safe_snapshot`)；ACCEPT 但 PM 必開 follow-up ticket.

**E2 推薦 PM 採選項 B**（T5.3 PASS-with-FOLLOWUP）— 理由：
- T5.3-MED-2 functional impact = 0 (defensive snapshot)
- E1 採 lazy-import 設計避免 bootstrap circular，已 commit 1822 行 + 61 tests，重派 review cycle 開銷 > 簡單 facade fix
- PA §5.1 命名建議實作為 `get_h1_stats_snapshot()` 與 PA design plan 對齊度更高，後續 ticket 一併處理
- 對齊既往 G2-02 / G9-02-MED-1 / Tier 4 OBSERVER 等 ACCEPT-with-FOLLOWUP 慣例

**3 個 task 全綠 PASS to QA**（with 3 follow-up tickets for PM backlog）.

## Verification Commands Run

```bash
# §A 跨平台 grep
ssh trade-core "git show <commit> | grep -E '(/home/ncyu|/Users/[^/]+)'" → 7/7 0 hit

# §F engine lib + integration
ssh trade-core "cargo test --release -p openclaw_engine --lib"
  → 2210 passed; 0 failed
ssh trade-core "cargo test --release -p openclaw_engine --test micro_profit_fix_integration"
  → 12 passed; 0 failed

# §F pytest H1/H3/h_state_query_handler
ssh trade-core "pytest test_h1_thought_gate.py test_model_router.py test_h_state_query_handler.py"
  → 75 passed in 0.08s

# §F strategist regression
ssh trade-core "pytest test_strategist_agent.py"
  → 36 passed in 0.09s

# §G [20] healthcheck smoke (env=0 + env=1)
OPENCLAW_H_STATE_GATEWAY=unset python3 -c "...check_h_state_gateway_freshness()..."
  → ('PASS', 'Phase 1 dormant by design')
OPENCLAW_H_STATE_GATEWAY=1 python3 -c "..."
  → ('WARN', 'stub no longer Phase 1 shape, version=1, h_states_keys=2')
  (Confirms T5.2-LOW-1 finding)

# §九 file size
wc -l 11 modified files
  → on_tick/helpers.rs 1315 (>1200, T5.1-LOW-1 finding)
  → strategy_wiring.py 1015 (warn-zone, pre-existing)
  → checks_derived.py 817 (warn-zone boundary, pre-existing + 5943337/c53c3f9)

# §B 雙語
grep -c '中\|MODULE_NOTE\|G3-08\|EXIT-FEATURES' on each file
  → 11/11 ≥5 markers
```

## End-of-Review Statement

`PASS to E4 / QA / PM Sign-off` for T5.1 + T5.2; T5.3 **PM 決選項 A (RETURN E1) vs B (ACCEPT-with-FOLLOWUP)**. E2 推薦選項 B + 3 follow-up tickets.
