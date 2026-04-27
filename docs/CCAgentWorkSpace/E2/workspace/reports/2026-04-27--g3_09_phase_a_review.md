# E2 Adversarial Review — G3-09 Phase A cost_edge_advisor (commit 00682ef)

- **Date**: 2026-04-27
- **Reviewer**: E2 (adversarial)
- **Commit**: `00682ef` on main
- **Source RFC**: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-26--g3_09_cost_edge_ratio_design.md`
- **E1 Report**: `docs/CCAgentWorkSpace/E1/workspace/reports/2026-04-27--g3_09_phase_a_cost_edge_advisor.md`
- **Verdict**: **PASS to E4** (0 BLOCKER / 0 HIGH / 0 MED / 0 LOW finding)

---

## 1. Scope reviewed

- 6 new Rust files (`cost_edge_advisor/{mod,types,advisor,tests}.rs` + `config/risk_config_cost_edge.rs` + `ipc_server/handlers/cost_edge_advisor.rs`)
- 21 modified Rust (`lib.rs`, `config/{mod,risk_config}.rs`, `ipc_server/{slots,server,connection,dispatch,mod,handlers/mod}.rs`, 6 `ipc_server/tests/*.rs`, `main.rs`, `main_boot_tasks.rs`)
- 3 TOML (paper/demo/live `risk_config_*.toml` `[cost_edge]` section)
- 3 Python healthcheck (`passive_wait_healthcheck/{__init__,checks_derived,runner}.py`)

Total: 27 files / ~1338 LOC new + 21 modified.

---

## 2. Three primary adversarial judgments

### 2.1 advisory-only **真的 zero trade impact**？ ✅ CONFIRMED

`grep -rn "cost_edge_advisor\|CostEdgeAdvisor" rust/openclaw_engine/src/` outside the module returns hits only in:
- `lib.rs:22` (pub mod export)
- `main.rs:503-515` (boot wiring)
- `main_boot_tasks.rs:19-538` (spawn fn)
- `ipc_server/{slots,server,connection,dispatch,mod}.rs` (slot type wiring)
- `ipc_server/handlers/{mod,cost_edge_advisor}.rs` (read-only IPC)

**0 hits** in `intent_processor/`, `cost_gate/`, `combine_layer/`, `exits/`, `strategies/`. Daemon writes only `advisor.state` (RwLock); IPC handler is read-only; no DB INSERT (Phase A defers audit pool wiring per E1 5.4).

**env=0 zero-overhead**: `is_advisor_env_enabled()` strict-equality `"1"` check; if false, `spawn_cost_edge_advisor_if_enabled` returns early before allocating Arc, slot stays `None`, IPC handler returns structured `Uninitialized` payload without lock contention.

### 2.2 Threshold direction (PM lock-in -0.5) ✅ CONFIRMED

`advisor.rs:106` `Some(r) if r <= threshold => trigger(...)` — matches PA RFC §2.4 variant A.
`risk_config_cost_edge.rs:113` default = `-0.5` matches PM Tier 9 T9-LOW-1.
TOML defaults verified: paper/demo `-0.5`, live `-0.3` (more conservative per RFC §8.2).
`validate()` rejects NaN/Inf and out-of-range `[-100.0, 100.0]` (operator typo guard).

### 2.3 Slot ID drift [22] → [30] ✅ LEGITIMATE

`grep -n 'results.append' helper_scripts/db/passive_wait_healthcheck/runner.py` shows [22]-[29] all occupied by F7 (STRKUSDT P0 wave, 2026-04-26). [30] is the next free slot. NOTE annotation present in `runner.py:404-406` and `checks_derived.py:925-926` documenting RFC drift; PA backlog ticket recommended (E1 5.2) to update RFC §6.2 / §10.x.

---

## 3. PA RFC §11 high-risk warnings (3) audit

| # | RFC warning | Verdict |
|---|---|---|
| 1 | daemon poll_interval 10s align with H state cache poller | ✅ `DEFAULT_POLL_INTERVAL = Duration::from_secs(10)` matches `h_state_cache` cadence per `mod.rs:96` |
| 2 | env-gate dual safeguard | ✅ `OPENCLAW_COST_EDGE_ADVISOR=1` (strict `=="1"`) AND `RiskConfig.cost_edge.enabled=true` (advisor.rs:79 short-circuit when `!cfg.enabled`) — independent rollback paths |
| 3 | ratio direction `<=` not `>=` | ✅ Verified in advisor.rs:106 + tests (`evaluate_trigger_at_exact_threshold_boundary`) |

---

## 4. CostEdgeAdvisorStatus 7-status enum coverage

| Status | Trigger condition | Test coverage |
|---|---|---|
| Uninitialized | daemon never spawned / pre-first-poll | ✅ tests.rs |
| Disabled | `cfg.enabled == false` (short-circuit) | ✅ `evaluate_disabled_when_cfg_off_regardless_of_ratio`, `evaluate_disabled_short_circuits_even_when_stale` |
| WarmUp | `ratio = None` (data_days < 3) | ✅ `evaluate_warm_up_when_ratio_none_with_low_data_days` |
| OK | `ratio > threshold` | ✅ tests.rs |
| Trigger | `ratio <= threshold` | ✅ `evaluate_trigger_at_exact_threshold_boundary` + threshold-positive tests |
| Stale | `is_stale == true` (Python crash / poller stuck) | ✅ `evaluate_stale_preserves_prev_ratio_in_echo`, `evaluate_stale_when_ratio_none_still_stale` |
| Anomaly | NaN / Inf | ✅ tests.rs (NaN + Inf + NEG_INFINITY) |

`cargo test -p openclaw_engine --lib cost_edge`: **43 / 0 failed** (32 advisor + 5 schema + 5 IPC + 1 pre-existing `test_cost_edge_ratio_calc`).

---

## 5. CLAUDE.md §九 8-checklist

| Item | Verdict | Note |
|---|---|---|
| 改動範圍與 PA 方案一致 | ✅ | Phase A scope only; Phase B/C deferred |
| 無 `except:pass` / 靜默吞異常 | ✅ | Daemon `tokio::select!` cancellation-safe; healthcheck explicit `except Exception` with reason |
| 日誌 `%s` 格式 | ✅ | `tracing::info!`/`warn!` use `field = value` syntax (Rust idiomatic) |
| 寫入 API 端點有 `_require_operator_role()` | N/A | Read-only IPC; advisor state mutation is daemon-only (no Operator IPC write surface) |
| `except HTTPException: raise` 在 `except Exception` 之前 | N/A | No new FastAPI handlers |
| `detail=str(e)` → "Internal server error" | N/A | No new HTTP routes |
| asyncio 路由無 blocking threading.Lock | ✅ | `parking_lot::RwLock` is sync but used outside `.await` in daemon; IPC slot uses `tokio::sync::RwLock` |
| 無私有屬性穿透 (`._xxx`) | ✅ | All access via `.state()` / `.store_state()` public API |

---

## 6. OpenClaw 9-checklist (§3 of pr-adversarial-review skill)

| # | Item | Verdict |
|---|---|---|
| 1 | 跨平台 grep `/home/ncyu` / `/Users/[^/]+` | ✅ 0 hits in new code |
| 2 | 雙語注釋 | ✅ All mod/fn/struct/variant/impl have MODULE_NOTE EN/中 + docstring EN/中 |
| 3 | Rust unsafe 零容忍 / unwrap 限不可恢復 / panic 不在交易路徑 | ✅ 0 unsafe, 0 unwrap on hot path; tests use `.expect("...")` only |
| 4 | 跨語言 IPC schema 一致 + serde 型別安全 | ✅ `CostEdgeAdvisorState` serde with `#[serde(default)]` forward-compat; `as_str()` byte-stable for wire |
| 5 | Migration Guard A/B/C | N/A — 0 SQL migration |
| 6 | healthcheck 配對 (被動等待 TODO) | ✅ `[30] cost_edge_advisor_status` paired with G3-09 Phase A schema landing |
| 7 | Singleton 登記 §九 表 | N/A — `CostEdgeAdvisor` is per-IPC `Arc` clone (not process-global singleton) |
| 8 | 文件大小 800/1200 行 | ✅ max 433 lines (tests.rs); E1 explicitly avoided extending advanced.rs at 1297 by creating sibling `risk_config_cost_edge.rs` |
| 9 | Bybit API 改動先查字典手冊 | N/A — 0 Bybit API touch |

---

## 7. Adversarial probes

1. **Q: Why `parking_lot::RwLock` not `tokio::RwLock` for advisor state?**
   A: Documented in `mod.rs:120-127` — critical section is sync (`state.clone()` / `state = new_state`), no `.await` inside; `parking_lot` is faster and avoids unnecessary async overhead. ✅ Justified.

2. **Q: Audit emit on every poll cycle (撐爆 audit log)?**
   A: `mod.rs:225-252` emits **only when `new_state.status != prev_status`** (transition guard). Trigger gets `warn!` level with full context; other transitions get `info!`. Steady-state cycles produce 0 log. ✅ Correct.

3. **Q: Race between H state cache slot population and advisor daemon?**
   A: Two-stage spawn at `main_boot_tasks.rs:492-541`. Stage 1 injects advisor handle into IPC slot (immediately). Stage 2 polls h_state_cache_slot every 100ms up to 10s; if never populated, warns + returns without spawning daemon. **No race**: advisor IPC always returns `Uninitialized` until daemon's first `store_state` cycle. ✅ Safe.

4. **Q: 45 dispatch_request test fixtures — sample 3-5 random sites?**
   A: Spot-checked `tests/dispatch.rs`, `tests/config.rs`, `tests/strategy.rs`. All add `&empty_cost_edge_advisor_slot()` as the **last** parameter, matching production `dispatch.rs:77` signature. `cargo check` passes. ✅ Consistent.

5. **Q: NaN/Inf in TOML triggering Anomaly OR validate failure?**
   A: TOML round-trip via `serde_json` accepts NaN/Inf in JSON but TOML format itself does not allow `nan`/`inf` literals. `validate()` rejects NaN/Inf at config load time → engine refuses to start. ✅ Defense-in-depth.

6. **Q: Cross-env config independence (memory `feedback_env_config_independence`)?**
   A: 3 TOML files independently configured (paper/demo: `enabled=false threshold=-0.5`, live: `enabled=false threshold=-0.3`). E1 chose demo as canonical advisor source per RFC §8.2 + memory `feedback_demo_over_paper_for_edge`. ✅ Compliant.

7. **Q: Hot-reload semantics if operator IPC patches `cost_edge.enabled = true`?**
   A: `risk_config.load()` is `ArcSwap` — daemon picks up change on next 10s tick. Schema validate runs on patch. Status transitions Disabled → WarmUp/OK/Trigger as evaluation cycle re-runs. ✅ Live-toggleable.

---

## 8. Findings

**0 BLOCKER / 0 HIGH / 0 MED / 0 LOW.**

All E1 self-reported caveats (5.1-5.5 in E1 report) are **acknowledged limitations** rather than defects:
- 5.1 Mac py3.10 tomllib — by-design fallback, Linux 3.12 production path unaffected
- 5.2 RFC slot drift [22] → [30] — already self-corrected with NOTE annotations
- 5.3 G3-08+G3-09 env-gate co-dependency — fail-soft warn already in place at `main_boot_tasks.rs:511-518`
- 5.4 Phase B/C extension surface — explicitly out of scope
- 5.5 Daemon integration test deferred to E4 — within E4 regression scope

---

## 9. PM forwarding instruction

**Action: Forward to E4 for regression on Linux release profile**.

E4 verification list:
1. `ssh trade-core "cd ~/BybitOpenClaw/srv/rust && cargo test --release -p openclaw_engine --lib"` — expect ≥ 2290 passed / 0 failed
2. `ssh trade-core "cd ~/BybitOpenClaw/srv && python3 helper_scripts/db/passive_wait_healthcheck.py 2>&1 | grep '\[30\]'"` — expect `[30] cost_edge_advisor_status` PASS-skip (env=0 default)
3. (Optional) operator manual `OPENCLAW_COST_EDGE_ADVISOR=1` toggle smoke + restart engine + observe IPC `get_cost_edge_advisor_status` returns `Disabled` (because RiskConfig flag still false → dual safeguard).

Backlog tickets (non-blocking):
- PA: update RFC §6.2 / §10.x slot reference [22] → [30]
- E1 follow-up: integration test `daemon spawn → poll → state transition → audit emit` for E4 regression hardening

---

## 10. Verdict

**PASS to E4** — adversarial review found 0 BLOCKER / 0 HIGH / 0 MED / 0 LOW. E1 self-report is unusually thorough; self-corrected RFC slot drift and §九 1200 cap proactively. Code quality matches "senior + adversarial standard" (CLAUDE.md §八 work principle 4).
