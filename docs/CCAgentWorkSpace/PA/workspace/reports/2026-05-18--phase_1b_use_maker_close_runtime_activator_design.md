# PA Design — Phase 1b `use_maker_close` Runtime Activator (Option A vs B)

**Author**: PA (Project Architect)
**Date**: 2026-05-18
**Triggered by**: PM main-session dispatch following E2 BLOCKER RCA
**Upstream evidence**: `srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-18--phase_1b_0_attempt_rca.md`
**Scope**: design + IMPL ticket draft + AMD wording patch; no business code.
**Verdict**: **APPROVE E2 recommendation — proceed with Option A (TOML), with one critical correction to sibling-pattern claim**.

---

## 1. Pre-decision adversarial finding (must read before option choice)

E2 RCA §"Fix proposal — Option A" claims:

> Sibling pattern: H0Gate shadow_mode at `pipeline_ctor.rs:80-93`
> Wire into `apply_risk_snapshot` / `sync_risk_config_if_changed` (RMW pump in `pipeline_config.rs`)

**Fact check — sibling claim is partially WRONG, fix-design must compensate.** Grep + line-by-line read shows:

| Layer | shadow_mode TOML→ runtime | use_maker_close TOML→ runtime (proposed) |
|---|---|---|
| Schema field | `RuntimeKnobs.h0_shadow_mode` (risk_config_advanced.rs:366) | NEW `RuntimeKnobs.use_maker_close` |
| TOML defined? | Yes (paper=true / demo=false / live=false) | NO — will be ADD |
| `apply_risk_snapshot` reads? | **NO** (pipeline_config.rs:97-109 only sets `max_open_positions / max_total_exposure_pct / allowed_categories`; comment says "RMW preserves shadow_mode" — meaning RMW does NOT touch shadow_mode) | (must wire from scratch) |
| IPC patch reads? | Yes (event_consumer/handlers/risk.rs:313-319) | optional later — not blocker |
| Boot-time seed from TOML? | **NO clear path found** — set_risk_store calls apply_risk_snapshot which does not touch shadow_mode | (must wire) |

**Implication**: The "sibling pattern" E2 references is partially aspirational. The pipeline_ctor.rs:76-93 comment claims `apply_risk_snapshot` performs the RMW pump for `h0_shadow_mode`, but **the actual code body does not include it** — `h0_shadow_mode` reaches `H0Gate.set_shadow_mode()` only via the IPC handler path (RRC-1-A3). This is a pre-existing latent gap (separate to this ticket; not in PA scope to fix unless operator wants follow-up).

**Decision impact**: Option A must NOT just copy the H0 wiring (since H0's TOML→RMW is broken). Option A IMPL must explicitly add the read path inside `apply_risk_snapshot` so use_maker_close does not inherit H0's bug. The IMPL ticket below makes this explicit.

---

## 2. Option decision — **Option A (TOML)**, with PA enforcement clauses

### 2.1 Comparison

| Criterion | Option A (TOML `runtime.use_maker_close`) | Option B (env `OPENCLAW_USE_MAKER_CLOSE=1`) | Option C considered (IPC handler / ArcSwap-only) |
|---|---|---|---|
| Hot-reload | Yes (file watcher → ConfigStore version bump → tick-top sync) | No (boot only) | Yes |
| Per-env independence | Yes (per `feedback_env_config_independence`) | Possible but ugly | Yes |
| Audit trail | Yes (TOML + git) | No (env var ephemeral) | Possible if IPC writes back TOML |
| Cold-boot semantics preserved | Yes (default = false in TOML if absent) | Yes | Yes |
| Kill-switch path (per AMD §3 line 86) | Yes — direct match | No | Partial |
| `feedback_v_migration_pg_dry_run` impact | None (no schema) | None | None |
| Demo-only enforcement | Centralised in `set_use_maker_close_runtime` (already in commands.rs:91-103) | Same | Same |
| Sibling discovery / pattern reuse | Pattern exists for `maker_kpi_config` and `risk_config` snapshots — clean copy | n/a | n/a |
| Effort | ~50 LOC + tests | ~10 LOC | ~30 LOC |
| Reviewer cognitive load | Low (1 file pair + 1 TOML line × 3 envs) | Low | Medium (cross-handler design) |

### 2.2 Verdict — Option A

**APPROVED** with the following PA enforcement clauses on top of E2's recommendation:

1. **Demo-only writer-side hardening**: even if `risk_config_live.toml` or `risk_config_paper.toml` accidentally sets `runtime.use_maker_close = true`, the `apply_risk_snapshot` path MUST call `set_use_maker_close_runtime(toml_value)` (NOT direct field assignment) so the existing Demo-only guard at commands.rs:91-103 vetoes Live/Paper.
2. **Cold-default behaviour preserved**: if the new field is absent from TOML, serde must default to `false` (`#[serde(default)]`). No `default_true()` (mirrors AMD §3 line 82 "cold-boot default = false").
3. **Boot-seed determinism**: `set_risk_store` already calls `apply_risk_snapshot` at line 46 — so first-tick value is deterministic from TOML, no race window.
4. **Hot-reload**: must propagate via the existing `sync_risk_config_if_changed` path (already called from `on_tick` top); no new tick-top hook required.
5. **No IPC handler in this ticket** (deferred to follow-up if operator wants live toggle UI; AMD §3 kill-switch is satisfied by TOML reload alone).

### 2.3 Why not Option B

- Env-var pattern non-governance-friendly (per `feedback_env_config_independence` + AMD §3 kill-switch table that explicitly says "TOML hot-reload → 1 tick").
- AMD §3 line 86 explicitly names "TOML hot-reload" as primary kill-switch mechanism. Env var contradicts AMD wording.
- Cannot ArcSwap; engine restart required for flip, broken Phase 2a observation loop.

### 2.4 Why not Option C (IPC-only)

- Loses durable record across restart. Phase 2a observation period of 14d implies ≥1 likely restart event — IPC-only setup means re-arming after each restart.
- Adds new IPC schema surface unnecessarily when TOML pattern is established.

---

## 3. E1 IMPL ticket (prompt-ready)

### 3.1 Files to touch + LOC estimate

| File | Change | LOC |
|---|---|---|
| `srv/rust/openclaw_engine/src/config/risk_config_advanced.rs` | Add `use_maker_close: bool` to `RuntimeKnobs` (line 360-367) with `#[serde(default)]` → defaults `false` | +6 |
| `srv/rust/openclaw_engine/src/tick_pipeline/pipeline_config.rs` | Inside `apply_risk_snapshot` add explicit call: `let _ = self.set_use_maker_close_runtime(snap.runtime.use_maker_close);` (after H0 block ~line 109, before paper_state block) | +5 |
| `srv/settings/risk_control_rules/risk_config_demo.toml` | Append in `[runtime]` block (line 168-171): `use_maker_close = true` | +1 |
| `srv/settings/risk_control_rules/risk_config_live.toml` | Append in `[runtime]` block: `use_maker_close = false` (explicit per `feedback_env_config_independence`) | +1 |
| `srv/settings/risk_control_rules/risk_config_paper.toml` | Append in `[runtime]` block: `use_maker_close = false` | +1 |
| `srv/settings/risk_control_rules/risk_config.toml` (master/template if used) | Append `use_maker_close = false` (paper-equivalent) | +1 |
| `srv/rust/openclaw_engine/src/tick_pipeline/tests/dual_rail_dispatch.rs` | Add 2 new tests (see §3.3) | +60 |
| `srv/rust/openclaw_engine/src/config/risk_runtime_projection.rs` | Decision: leave alone (projection has h0_shadow_mode for startup/watcher; this field is consumed inside engine, not external — no need to expose) | 0 |

**Total**: ~75 LOC core + ~60 LOC tests = **~135 LOC**.

### 3.2 Exact change patterns

**risk_config_advanced.rs:359-390** — extend `RuntimeKnobs`:

```
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RuntimeKnobs {
    #[serde(default = "default_boot_cooldown_ms")]
    pub boot_cooldown_ms: u64,
    #[serde(default = "default_signals_heartbeat_ms")]
    pub signals_heartbeat_ms: u64,
    #[serde(default = "default_true")]
    pub h0_shadow_mode: bool,
    // NEW (AMD-2026-05-15-02 §3 runtime activation layer; PA design 2026-05-18):
    // Cold-default false. Only honoured on Demo pipeline (the engine-side
    // `set_use_maker_close_runtime` rejects flip-true on Live/Paper).
    // 為 AMD §3 提供 runtime 啟動層；cold-default false；Demo-only enforcement
    // 由 `set_use_maker_close_runtime` 兜底（live/paper TOML 即使誤填 true 也
    // 不會生效）。
    #[serde(default)]
    pub use_maker_close: bool,
}
```

Note: `Default for RuntimeKnobs` (line 376-384) must extend with `use_maker_close: false`.

**pipeline_config.rs apply_risk_snapshot** — insert after line 109 (H0 block ends), before "// 4. ARCH-RC1 ... E-Merge-1":

```
// AMD-2026-05-15-02 §3 runtime activation layer (Phase 1b close-maker-first):
// honour `runtime.use_maker_close` from TOML. Pipe through
// `set_use_maker_close_runtime` (NOT direct field assignment) so the existing
// Demo-only guard (commands.rs:91-103) rejects accidental Live/Paper TOML drift.
// Hot-reload: this runs on every version-bump path via sync_risk_config_if_changed.
// AMD-2026-05-15-02 §3 runtime 啟動層：把 TOML `runtime.use_maker_close` 透過
// `set_use_maker_close_runtime` 路由（保留 commands.rs:91-103 的 Demo-only
// 守衛），TOML 改值 → ConfigStore 版本上升 → 下一個 on_tick 立即生效。
let _ = self.set_use_maker_close_runtime(snap.runtime.use_maker_close);
```

**TOML edits**: append inside existing `[runtime]` blocks. Demo TOML block today reads:

```toml
[runtime]
boot_cooldown_ms = 60000
signals_heartbeat_ms = 60000
h0_shadow_mode = false
```

Add `use_maker_close = true` on demo; `= false` on live/paper/master.

### 3.3 Test additions (dual_rail_dispatch.rs)

Two new tests required, both placed near existing `test_close_maker_runtime_enable_surface_is_demo_only_and_default_false` (line 321-336):

**Test 1 — TOML activation propagates on Demo:**

```rust
#[test]
fn test_use_maker_close_toml_activates_on_demo() {
    // Build a Demo pipeline, set a RiskConfig store containing
    // runtime.use_maker_close = true, verify use_maker_close() flips true after
    // set_risk_store (which calls apply_risk_snapshot synchronously).
    // 構造 Demo 管線，注入帶 `runtime.use_maker_close = true` 的 RiskConfig
    // store，驗證 set_risk_store 後 use_maker_close() 為 true。
    let mut demo = TickPipeline::with_kind(&["BTCUSDT"], 10_000.0, PipelineKind::Demo);
    assert!(!demo.use_maker_close()); // cold default
    let mut cfg = crate::config::RiskConfig::default();
    cfg.runtime.use_maker_close = true;
    let store = std::sync::Arc::new(crate::config::ConfigStore::new(cfg));
    demo.set_risk_store(store);
    assert!(demo.use_maker_close(), "Demo TOML true must activate");
}
```

**Test 2 — TOML drift on Live/Paper is rejected by writer guard:**

```rust
#[test]
fn test_use_maker_close_toml_rejected_on_live_and_paper() {
    // Even if TOML accidentally sets use_maker_close=true on Live or Paper,
    // the set_use_maker_close_runtime guard must reject and leave flag false.
    // 即使 Live/Paper TOML 誤填 use_maker_close=true，
    // set_use_maker_close_runtime 守衛仍必須拒絕並保留 flag=false。
    for kind in [PipelineKind::Live, PipelineKind::Paper] {
        let mut p = TickPipeline::with_kind(&["BTCUSDT"], 10_000.0, kind);
        let mut cfg = crate::config::RiskConfig::default();
        cfg.runtime.use_maker_close = true;
        let store = std::sync::Arc::new(crate::config::ConfigStore::new(cfg));
        p.set_risk_store(store);
        assert!(!p.use_maker_close(), "{kind:?} must hard-block TOML drift");
    }
}
```

**Test 3 (optional but recommended) — hot-reload propagation within 1 tick:**

Patch the ConfigStore (bump version), drive one `on_tick`, assert `use_maker_close()` reflects new value. Mirrors h0_shadow_mode hot-reload test if one exists. ~30 LOC.

### 3.4 Acceptance criteria

| AC | Definition | Verification |
|---|---|---|
| AC-A1 | Demo pipeline boots with `use_maker_close()` returning the TOML value | Test 1 |
| AC-A2 | Live + Paper pipelines reject TOML drift; `use_maker_close()` stays false | Test 2 |
| AC-A3 | TOML edit + ConfigStore version bump → next on_tick flips state | Test 3 (or runtime smoke) |
| AC-A4 | Cold default (TOML missing field entirely) = false | `#[serde(default)]` + serde default test |
| AC-A5 | Existing `test_close_maker_runtime_enable_surface_is_demo_only_and_default_false` still GREEN | cargo test |
| AC-A6 | Existing dual_rail_dispatch tests using `set_use_maker_close_for_test(true)` still GREEN | cargo test (no API change to that helper) |
| AC-A7 | post-deploy on Linux: within 2h of restart, `attempt_pct >= 25%` on Demo whitelist closes (E2 verification SQL §verification protocol) | E2 SQL run by QA |

### 3.5 Risk identification + edge cases

| Risk | Severity | Mitigation |
|---|---|---|
| R1: `RuntimeKnobs` Default block missed (compile passes but boot panics on missing field) | Medium | E1 MUST update both struct field AND `impl Default for RuntimeKnobs` (line 376-384) |
| R2: existing TOMLs do NOT carry the new field; older deployment using old TOML breaks | Low | `#[serde(default)]` returns false, equivalent to cold default. Append-only; no breaking change. |
| R3: live_demo pipeline (Live with demo endpoint) — is `pipeline_kind` Live or Demo? Behaviour ambiguous. | **Medium** | Check `PipelineKind` enum + `with_kind` callsites. Note: the live_demo endpoint binding does NOT change `pipeline_kind`; it is a `Live` PipelineKind bound to demo endpoint via `set_endpoint_env`. **Therefore Demo-only guard at commands.rs:92 rejects live_demo.** AMD §3 Phase 2b explicitly says "live_demo `use_maker_close = true` per-策略" — there is an **AMD-vs-code conflict** here. → see §3.6 below |
| R4: dispatch interactions with stop_request_tx / cancel_token race | Low | Existing skip-path gate at commands.rs:117 already routes risk_close to market; AMD §2.3 negative whitelist remains canonical. No new path created. |
| R5: silent activator on Stage 0 (Phase 2a not yet armed) — flag flips before code is in production | Mitigated | E2 RCA proves binary contains all Phase 1b code at PID 1066422 mtime 2026-05-17 23:13 (post `ea4ceca6`). Activation is the ONLY missing piece. |
| R6: AMD §3 Phase 2b says live_demo enables but current commands.rs:92 Demo-only guard would BLOCK | **HIGH** | See §3.6 — defer-decision; do NOT widen in this ticket. PA recommends Phase 2a Demo only this round; Phase 2b live_demo enablement is a separate IMPL ticket. |

### 3.6 Critical AMD-vs-code conflict (must flag to PM)

**Finding**: `commands.rs:92` rejects everything except `PipelineKind::Demo`. But AMD-2026-05-15-02 §3 Rollout Posture explicitly lists:

| Phase | Env | TOML |
|---|---|---|
| Phase 2a Demo | demo | `use_maker_close = true` |
| Phase 2b LiveDemo | **live_demo** | `use_maker_close = true` per-策略 |

`live_demo` runs on a `PipelineKind::Live` (Live pipeline kind bound to demo endpoint via `set_endpoint_env`). With current commands.rs:92, Phase 2b will hit hard-block reject when AMD says it should be active. **This is a separate latent defect not part of the current ticket, but must be queued.**

**PA recommendation**: This IMPL ticket targets **Phase 2a Demo only**. Phase 2b widening (adding live_demo via `effective_engine_mode() == "live_demo"` check in `set_use_maker_close_runtime`) requires separate AMD wording clarification + PM sign-off. **DO NOT widen in this ticket**.

### 3.7 Effort estimate

- IMPL: **2-3 person-hours** (135 LOC + run cargo test locally)
- E2 re-review: 30-45 min
- E4 regression: 30 min (full cargo test pass)
- QA deploy readiness check: 30 min
- Operator `restart_all.sh --rebuild` + 4h observation: ~5h wall

---

## 4. AMD §3.1 wording patch (proposal)

**Note**: The AMD has no explicitly-numbered `§3.1`. The E2 RCA reference "AMD §3.1 cold-default" maps to the **§3 Rollout Posture** section, line 82 of the AMD:

### 4.1 Current wording (AMD line 82)

```
**Rust struct cold-boot default**: `use_maker_close = false`（§5.6 fail-safe）。
```

### 4.2 Proposed revision (PA Wave 3c amendment patch)

Replace line 82 with:

```
**Rust struct cold-boot default**: `use_maker_close = false`（§5.6 fail-safe）。

**Runtime activation layer**：`RuntimeKnobs.use_maker_close` field on `RiskConfig`
（per `risk_config_advanced.rs` §RuntimeKnobs）。三環境 TOML 獨立配置 per
`feedback_env_config_independence`：

| 環境 | TOML 預設 | Demo-only writer guard |
|---|---|---|
| `risk_config_demo.toml` | `use_maker_close = true`（Phase 2a 啟用） | bypass（Demo 是 enforce 唯一允許者）|
| `risk_config_live.toml` | `use_maker_close = false` | 強制 reject（即使誤填 true 也 false）|
| `risk_config_paper.toml` | `use_maker_close = false` | 強制 reject（同上）|

TOML field absent → serde default `false`（與 Rust struct cold-boot 對齊）。
Activation 路徑：`set_risk_store` → `apply_risk_snapshot` → `set_use_maker_close_runtime`，
boot-time 一致 + tick-top hot-reload（ConfigStore 版本號變化下個 on_tick 生效）。

**Phase 2b live_demo 啟用**（per Rollout table）：`commands.rs:92` 當前 Demo-only
guard 需另開 IMPL ticket 升級為「Demo OR live_demo endpoint」；本 AMD 不在此回
patch，留 Phase 2b 啟用前單獨補件。
```

### 4.3 Rationale

1. **Closes E2's "missing activation layer" gap** explicitly named in RCA §"AMD spec gap".
2. **Documents three-env independence** explicitly so future operators/agents do not unilaterally merge configs (per `feedback_env_config_independence`).
3. **Pre-flags Phase 2b live_demo conflict** so AMD authors / sub-agents do not silently widen `commands.rs:92` thinking the AMD already authorises it.

### 4.4 AMD revision bump

**Recommend**: bump v0.4 → **v0.5** (changelog `2026-05-18`, author `PA per main-session post-E2 BLOCKER RCA`).

Rationale: wording change is non-numerical (no AC change, no rollout-phase change). However it adds explicit runtime activation surface where AMD previously had a gap. Per AMD's own §12 changelog discipline ("v0.4 = Wave 3a 4-agent re-review consolidation" — sub-patch level), this revision = v0.5 = "Wave 4 post-E2 BLOCKER patch — runtime activation layer explicit + Phase 2b conflict flagged".

**Sub-condition**: requires PM sign-off (AMD revision bumps are PM authority); CC compliance scan not required (no schema / no hard-boundary touch). PA does not write the AMD edit — propose patch text here and PM/operator applies.

---

## 5. Chain handoff sequence + ETA

| Step | Owner | Inputs | Outputs | ETA |
|---|---|---|---|---|
| 1 | PA (this report) | E2 RCA + code reads | option A approved + IMPL ticket + AMD patch proposal | DONE 2026-05-18 |
| 2 | PM | this report | dispatch E1 (single worktree, no parallelism — narrow scope) + sign off AMD v0.5 patch | 10 min |
| 3 | E1 | dispatch packet | `RuntimeKnobs.use_maker_close` field + apply_risk_snapshot wiring + 3 TOML edits + 2-3 unit tests | 2-3h |
| 4 | E2 | E1 diff | adversarial review — focus on (a) `set_use_maker_close_runtime` call path, (b) `#[serde(default)]` semantics, (c) demo/live/paper TOML invariance | 30-45 min |
| 5 | E4 | E1 diff + binary | `cargo test -p openclaw_engine` full pass; verify existing dual_rail tests GREEN | 30 min |
| 6 | QA | E1+E2+E4 sign-off | deploy readiness gate; produce verification SQL runbook for post-restart 2h check | 30 min |
| 7 | Operator | QA OK | `restart_all.sh --rebuild` on Linux; engine pid changes; ts marker for Phase 2a clock reset | 5-10 min wall |
| 8 | QA | post-restart 2h | run E2 RCA §verification protocol SQL — confirm `attempt_pct >= 25%` on Demo whitelist closes | 2h wall + 30 min |
| 9 | PM | all above | declare Phase 1b RUNTIME ACTIVE; Phase 2a 14d observation clock reset to step 8 timestamp | 5 min |

**Total ETA from PA approve → maker_attempt rate ≥ 25% verified**: ~6-8h wall (3-4h IMPL/review + 2h post-restart observation + 30min QA verify).

**Phase 2a 14d observation period reset trigger**: **step 8** (QA verification SQL run, NOT step 7 restart). Reason: restart alone does not prove activation; only the SQL passing AC-A7 (≥25% attempt rate on demo whitelist closes within first 2h) marks t=0 for the 14d clock per AMD §3 Phase 2a definition ("7d primary + 7d extended observation"). Calendar starts when **observation evidence** begins flowing, not when binary restarts.

---

## 6. Risk + edge cases (top-level summary)

### 6.1 Critical risk — top-1

**Phase 2b live_demo blocker (R6 from §3.5)**: AMD §3 promises Phase 2b enablement on live_demo, but current `commands.rs:92` Demo-only guard will REJECT live_demo (LiveDemo runs as `PipelineKind::Live` with demo endpoint). If this ticket lands without addressing it, Phase 2b will require a second IMPL+restart cycle. **Mitigation in this ticket**: explicit AMD §4.2 wording change (above) flagging the conflict; defer Phase 2b widening to a separate ticket per `feedback_demo_loose_live_strict_policy`. Do NOT broaden Demo-only guard in this ticket.

### 6.2 Other risks

- R3 (live_demo guard) — addressed via §3.6 + §6.1 deferral.
- R5 (silent activator) — mitigated; E2 RCA proves binary path is wired.
- Schema drift / migration impact — none (config struct only; no V### migration).
- Cross-platform — none; pure TOML + Rust, no path/OS coupling.

### 6.3 16-principle compliance (delta)

| Principle | Status | Note |
|---|---|---|
| #1 Single write entry | UNCHANGED | Close path still routes through `execute_position_close → OrderDispatchRequest → order_dispatch_tx` |
| #4 No bypass of risk | UNCHANGED | Negative whitelist (risk_close/halt_session/etc) preserved at commands.rs:117 gate above maker compute |
| #6 Fail-default conservative | **STRENGTHENED** | TOML missing field → false; live/paper hardware veto; AMD wording made explicit |
| #7 Learning ≠ live mutation | UNCHANGED | No ML pipeline touched; flag is execution-quality-only |
| #15 Multi-agent | UNCHANGED | No new agent comm / no new topic |

No hard-boundary touch (per CLAUDE.md §四 Hard Boundaries). No `live_execution_allowed` / `OPENCLAW_ALLOW_MAINNET` / `authorization.json` interaction.

---

## 7. Acceptance + verification protocol (cross-ref E2 SQL)

E2 RCA §"Verification protocol" SQL queries are authoritative for post-deploy gate. Reproduced here for QA:

```sql
-- AC-A7 verification: confirm maker_attempt rate >= 25% within 2h post-restart on Demo whitelist closes
SELECT engine_mode, fill_role,
       COUNT(*) FILTER (WHERE close_maker_attempt=TRUE) AS attempts,
       COUNT(*) FILTER (WHERE liquidity_role IN ('maker','taker')) AS close_total,
       ROUND(100.0 * COUNT(*) FILTER (WHERE close_maker_attempt=TRUE)
             / NULLIF(COUNT(*) FILTER (WHERE exit_reason IS NOT NULL), 0), 2) AS attempt_pct
  FROM trading.fills
 WHERE ts > NOW() - INTERVAL '2 hours'
   AND engine_mode IN ('demo','live_demo')
   AND exit_reason IN ('grid_close_short','grid_close_long','bb_mean_revert',
                       'ma_reverse_cross','bw_squeeze','pctb_revert')
 GROUP BY engine_mode, fill_role;
```

**Pass criteria** (PA enforcement on E2's spec):
1. `engine_mode='demo'` row: `attempt_pct >= 25%` (per AMD §4.3 conservative gate)
2. `engine_mode='live_demo'` row: still 0% (Phase 2b not yet enabled — confirms R6 deferral works as designed)
3. `fallback_reason` distribution: non-NULL on every attempt=TRUE row that didn't fill at PostOnly limit; values must come from the V094 enum allowlist

**Trigger Phase 2a 14d clock reset**: AC-A7 PASS on **demo** engine_mode within 2h. live_demo zero is expected.

---

## 8. PA sign-off

**Decision**: **APPROVE Option A** with PA enforcement clauses §2.2 1-5.

**Critical findings appended on top of E2**:
1. Sibling H0Gate pattern is partially BROKEN — fix design adds explicit `apply_risk_snapshot` call rather than relying on RMW preservation.
2. AMD-vs-code Phase 2b live_demo conflict — flagged + deferred + AMD wording patched.
3. Activator IMPL must call `set_use_maker_close_runtime`, NOT direct field set — preserves Demo-only veto layer.

**E1 dispatch**: ready. Total core LOC ~75 + tests ~60 = ~135 LOC, 2-3 person-hours.

**AMD v0.5 patch**: proposed in §4 above. PM applies after E1 IMPL lands (don't patch AMD ahead of IMPL — keeps git churn sequential).

**Phase 2a 14d clock**: reset at QA step 8 (AC-A7 SQL pass on demo), NOT at step 7 (restart).

**Top-1 critical risk**: Phase 2b live_demo blocker (R6) — addressed by explicit deferral + AMD wording flag.

---

**PA DESIGN DONE**

Report path: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-18--phase_1b_use_maker_close_runtime_activator_design.md`
