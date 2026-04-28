# E2 Adversarial Review — G3-09-PHASE-B-FUP-STICKY-TS

- **Date**: 2026-04-28
- **Reviewer**: E2 (adversarial)
- **Worktree**: `srv/.claude/worktrees/agent-aeb618f0d004b3366`
- **Branch**: `worktree-agent-aeb618f0d004b3366` (uncommitted)
- **Base**: `82347a5` (origin/main)
- **PA report**: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-28--g3_09_phase_b_fup_sticky_ts.md`
- **Verdict**: **PASS to E4** (0 BLOCKER / 0 HIGH / 0 MED / 0 LOW)

---

## 1. Scope

| File | +/- LOC | Nature |
|---|---|---|
| `rust/openclaw_engine/src/cost_edge_advisor/mod.rs` | +51 / -2 | daemon body sticky enforce match arm + bilingual docstring + warn! log adds `triggered_at_ms` field |
| `rust/openclaw_engine/src/cost_edge_advisor/advisor.rs` | +24 / -16 | module doc + Trigger constructor inline comment realigned with daemon ownership |
| `rust/openclaw_engine/src/cost_edge_advisor/types.rs` | +9 / -4 | `triggered_at_ms` field doc realigned |
| `rust/openclaw_engine/tests/test_cost_edge_advisor_daemon.rs` | +210 / -0 | 1 builder + 2 sticky tests + section docstring |
| `docs/CCAgentWorkSpace/PA/memory.md` | +53 / 0 | PA log only |

Net production code: **+62** (≈ 25 LOC bilingual docstring + ≈ 37 LOC actual logic). Test code: **+210**. Within operator's 80 LOC production cap.

---

## 2. Three primary adversarial judgments

### 2.1 4-arm `match (prev_status, new_state.status)` exhaustive? ✅ CONFIRMED

```rust
(Trigger, Trigger)        => preserve     // contiguous
(_, Trigger)              => record       // entering (covers Disabled/Stale/Anomaly/WarmUp/OK/Uninitialized → Trigger)
(Trigger, _)              => clear        // leaving (covers Trigger → Disabled/Stale/Anomaly/WarmUp/OK/Uninitialized)
_                         => no-op        // non-Trigger → non-Trigger
```

Rust pattern-match exhaustiveness compiler check passes (`cargo build --release --tests` clean). All 7 variants of `CostEdgeAdvisorStatus` (Uninitialized / Disabled / WarmUp / OK / Trigger / Stale / Anomaly) covered in both `prev` and `new` slots. No silent fallthrough.

### 2.2 `prev_status` source + race window? ✅ NO RACE

`mod.rs:202` `let mut prev_status = ...` and `mod.rs:215` `let mut sticky_triggered_at_ms` are both **task-local** in the daemon's spawned future — single owner, no `Arc`/`Mutex`/`RwLock` shared with any other thread. `prev_status` is updated at `mod.rs:311` `prev_status = new_state.status` immediately before `advisor.store_state(new_state)` at `:312`. Next loop iteration reads its own previous-cycle write — no cross-thread visibility issue.

The shared mutation point is `advisor.store_state` (parking_lot::RwLock); IPC handlers read `state()` independently. Sticky logic happens **before** store_state and is decided entirely from task-local `prev_status` — IPC reads can never observe a torn state where `triggered_at_ms` and `status` disagree.

### 2.3 `evaluate()` pure-fn behavior preserved? ✅ CONFIRMED

`git diff` on `advisor.rs` shows only docstring changes inside the function body comments + module doc; **zero signature / control-flow / arithmetic mutation**. The 32 existing `src/cost_edge_advisor/tests.rs` cases continue to pass (lib 2290/0 unchanged). Pure-fn property therefore intact: sticky semantics live exclusively in the daemon, not in the function under test by 32 unit tests.

---

## 3. Verification (Mac)

| Command | Result |
|---|---|
| `cargo build --release -p openclaw_engine --tests` | clean, 0 errors, no new warnings |
| `cargo test --release -p openclaw_engine --test test_cost_edge_advisor_daemon` | **8 / 0 failed** (was 6, +2 sticky tests both green; sub-second shutdown test still passes) |
| `cargo test --release -p openclaw_engine --lib` | **2290 / 0 failed** (Phase A baseline preserved bit-for-bit) |
| `grep -E '/home/ncyu|/Users/[a-zA-Z]+'` 4 modified files | **0 hits** (no hardcoded user paths) |

---

## 4. CLAUDE.md §九 8-checklist

| Item | Verdict | Note |
|---|---|---|
| 改動範圍與 PA 方案一致 | ✅ | mod.rs daemon body / advisor.rs + types.rs docstring / 1 builder + 2 sticky tests — exactly as PA §3 stat |
| 無 `except:pass` / 靜默吞異常 | ✅ | Pure Rust task; no exception swallowing |
| 日誌 `%s` 格式 | ✅ | `tracing::warn!`/`info!` field syntax (Rust idiomatic); new `triggered_at_ms` field added cleanly |
| 寫入 API 端點有 `_require_operator_role()` | N/A | No new HTTP/IPC write surface |
| `except HTTPException: raise` 在 `except Exception` 之前 | N/A | No FastAPI |
| `detail=str(e)` → "Internal server error" | N/A | No HTTP routes |
| asyncio 路由無 blocking threading.Lock | ✅ | sticky logic is task-local, no lock; existing `parking_lot::RwLock` for state already audited Phase A |
| 無私有屬性穿透 (`._xxx`) | ✅ | All access via `.state()` / `.store_state()` public API |

---

## 5. OpenClaw 9-checklist (`pr-adversarial-review` §3)

| # | Item | Verdict | Note |
|---|---|---|---|
| 1 | 跨平台 grep `/home/ncyu` / `/Users/[a-zA-Z]+` | ✅ | 0 hits in 4 modified files |
| 2 | 雙語注釋 (CLAUDE.md §七 + `bilingual-comment-style`) | ✅ | mod.rs sticky block / advisor.rs module + Trigger constructor inline / types.rs `triggered_at_ms` field doc / test section header — all paragraphs configured EN + 中文 |
| 3 | Rust unsafe 零容忍 / unwrap 限不可恢復 / panic 不在交易路徑 | ✅ | 0 unsafe, 0 unwrap; tests use `assert!`/`assert_eq!` only |
| 4 | 跨語言 IPC schema 一致 + serde 型別安全 | ✅ | `ipc_server/handlers/cost_edge_advisor.rs:55` already exposes `triggered_at_ms: i64` — sticky semantics now correctly populates the wire field; existing IPC test `:140` continues to assert the field shape |
| 5 | Migration Guard A/B/C | N/A | 0 SQL migration |
| 6 | healthcheck 配對 (被動等待 TODO) | ✅ | 既有 `[30] cost_edge_advisor_status` schema sentinel 仍綠；sticky 強化既有欄位語意，未引入新被動等待 |
| 7 | Singleton 登記 §九 表 | N/A | `CostEdgeAdvisor` 是 per-IPC `Arc` clone (not process-global singleton) |
| 8 | 文件大小 800/1200 行 | ✅ | mod.rs 317 / advisor.rs 176 / types.rs 292 — all far below 800 warn line; test 802 lines (test files exempt from production §九 limit) |
| 9 | Bybit API 改動先查字典手冊 | N/A | 0 Bybit API touch |

---

## 6. Adversarial probes

1. **Q: Could `Trigger → Stale` (rare transition) leave sticky state inconsistent?**
   A: `Stale` is its own status variant (`CostEdgeAdvisorStatus::Stale`), so `(Trigger, Stale)` matches the third arm `(Trigger, _)` → sticky cleared to 0. Next cycle if cache becomes fresh and ratio re-triggers, `(Stale, Trigger)` matches second arm → fresh `now_ms` recorded. ✅ Correct semantics — Trigger episode ended when freshness was lost.

2. **Q: Could a daemon restart (engine restart) lose sticky timestamp mid-Trigger episode?**
   A: Yes — daemon task-local state is destroyed on restart; next spawn starts with `sticky_triggered_at_ms = 0` and `prev_status = Uninitialized`. First post-restart cycle hits `(Uninitialized, Trigger)` → second arm → records fresh `now_ms`. So a restart resets the "episode start" to the post-restart wall-clock. PA §8 acknowledges this is acceptable since Phase B `last_trigger_ms` is a rolling counter, not a long-term audit ledger; long-term audit would belong to V026 INSERT path (Phase B Wave 1 scope). ✅ Documented limitation, not a defect.

3. **Q: Two-test race robustness — what if test machine is slow and daemon misses a cycle?**
   A: `sticky_triggered_at_ms_preserved_across_contiguous_trigger_cycles` uses `Instant::now() < hard_deadline` with 1.2s ceiling and 100ms cadence (target ≥3 cycles, ceiling allows up to 12 cycles). Slow CI gets >3 samples; very slow CI hits the deadline assert with a useful diagnostic. ✅ Robust.

4. **Q: First-test wall-clock window race?**
   A: `before_spawn_ms = now_ms()` taken **before** `spawn_cost_edge_advisor`; `after_first_ms = now_ms()` taken **after** the loop confirms Trigger state landed. Daemon's internal `unix_now_ms()` call sits strictly between these two, so `triggered_at_ms ∈ [before_spawn_ms, after_first_ms]` is guaranteed barring system clock regression (test infra never does this). ✅ Tight + correct.

5. **Q: IPC consumer breakage from sticky behavior?**
   A: `ipc_server/handlers/cost_edge_advisor.rs` already exposes `triggered_at_ms` (line 55) — Phase A handler test (`:140`) asserts the field shape, sticky semantics merely populates it correctly across cycles instead of overwriting. Healthcheck `[30]` is a schema sentinel checking field presence; sticky upgrade doesn't break it. ✅ Backward compatible.

6. **Q: Does sticky logic interact with `is_stale` correctly?**
   A: `evaluate()` returns `Stale` status when `is_stale=true`, regardless of ratio. `Stale` is not `Trigger`, so sticky flow `(Trigger, Stale)` clears the timestamp (Trigger episode ended). When freshness returns, `(Stale, Trigger)` records a fresh entry — matches the semantic "an interrupted episode is a new episode after staleness". ✅ Correct.

7. **Q: Phase B compatibility — does sticky `triggered_at_ms` actually serve the `last_trigger_ms` rolling counter use case?**
   A: PA §8 distinguishes `triggered_at_ms` (current contiguous Trigger run entry, 0 when not Trigger) from `last_trigger_ms` (24h rolling last Trigger transition, persists post-Trigger). Two fields are orthogonal; this PR provides the first; Phase B Wave 1 (V026 + INSERT path) will add the second. Sticky semantics on `triggered_at_ms` is **necessary** for Wave 1 dedup analytics ("once per episode" requires knowing where episode begins). ✅ Aligned.

---

## 7. Findings

**0 BLOCKER / 0 HIGH / 0 MED / 0 LOW.**

PA self-acknowledged limitation (§8): daemon-restart resets sticky episode boundary. This is by-design (no shared/persistent state in scope; Phase B Wave 1 V026 INSERT path will provide the audit ledger). Not a defect for Phase A advisory-only path.

---

## 8. PM forwarding instruction

**Action: Forward to E4 for regression on Linux release profile.**

E4 verification list:
1. `ssh trade-core "cd ~/BybitOpenClaw/srv/rust && cargo test --release -p openclaw_engine --lib"` — expect **2290 passed / 0 failed** (matches baseline; sticky lives in integration test, not lib).
2. `ssh trade-core "cd ~/BybitOpenClaw/srv/rust && cargo test --release -p openclaw_engine --test test_cost_edge_advisor_daemon"` — expect **8 passed / 0 failed** (was 6 + 2 new sticky tests).
3. (Optional) `ssh trade-core "cd ~/BybitOpenClaw/srv && python3 helper_scripts/db/passive_wait_healthcheck.py 2>&1 | grep '\[30\]'"` — expect `[30] cost_edge_advisor_status` PASS-skip (env=0 default; sticky upgrade doesn't change schema sentinel behavior).

Backlog tickets (non-blocking):
- PA G3-09 Phase B Wave 1 RFC (`docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-27--g3_09_phase_b_shadow_dryrun_design.md`) §3.1: add 1-line note documenting `triggered_at_ms` (sticky entry) vs `last_trigger_ms` (24h rolling) semantic split per PA §8.
- No new TODO ticket required; sticky enforcement is a prep-gate self-closing within this PR.

---

## 9. Verdict

**PASS to E4** — 0 finding. Sticky logic is minimal, task-local, exhaustive in match coverage, properly bracketed between `evaluate()` (pure) and `store_state()` (shared write surface), and verified by two adversarial integration tests covering both sticky properties (entering + contiguous preservation). Phase A advisory-only behavior is bit-for-bit preserved (lib 2290/0). Code quality matches "senior + adversarial standard" (CLAUDE.md §八 work principle 4).
