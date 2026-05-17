# E4 Regression Report — Phase 1b runtime activator (use_maker_close)

**Date**：2026-05-18
**Agent**：E4
**Target commit**：`18081551` (`feat(phase-1b): runtime activator IMPL (E1 second-dispatch, post-E2 RETURN)`)
**Branch**：`feature/phase-1b-runtime-activator`
**Upstream chain**：E1 second-dispatch IMPL → E2 second-pass APPROVE (0 new MUST-FIX, agent `a94825cb`) → 本 E4
**Scope**：full Rust + Python regression on Mac + Linux，4 平台/build mode 雙跑非 flaky 確認

---

## §1 Pre-flight：branch + working tree state

| 項 | Value |
|---|---|
| Mac local origin/main HEAD | `5cfe1f68 docs(amd): bump amd-2026-05-15-02 v0.5 -> v0.6` |
| Phase-1b HEAD | `18081551 feat(phase-1b): runtime activator IMPL (E1 second-dispatch, post-E2 RETURN)` |
| Mac main 工作 tree dirty | 2 個 memory file（E2 + PA session WIP，非 PR scope）→ stash 隔離後 checkout phase-1b |
| origin/feature/phase-1b-runtime-activator vs local | == identical（無 sibling drift） |
| Linux trade-core 同步 | ssh fetch + checkout `18081551` 一致 |
| sibling 並行 PR | 0（PA W-AUDIT-8b sweep 主 session 等 panel ≥7.0d，0 file 重疊） |

**Race protocol 5 條全 PASS**（5a stash 隔離 / 5b 0 file 重疊 / 5c HEAD ≡ origin / 5d 不 commit / 5e 不 deploy）。

---

## §2 File scope（PA §3.1 1:1）

| File | Diff | Verified |
|---|---|---|
| `rust/openclaw_engine/src/config/risk_config_advanced.rs` | +11 (RuntimeKnobs 加 `use_maker_close: bool` + `#[serde(default)]` + Default 補 `use_maker_close: false`) | ✅ |
| `rust/openclaw_engine/src/tick_pipeline/pipeline_config.rs` | +24 (apply_risk_snapshot 加 `let _ = self.set_use_maker_close_runtime(snap.runtime.use_maker_close)` + 3 段中文注釋) | ✅ |
| `rust/openclaw_engine/src/tick_pipeline/tests/dual_rail_dispatch.rs` | +108 (3 new tests at lines 343/373/399) | ✅ |
| `rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs` | +1 trailing newline (F1 strip 後復原) | ✅ |
| `settings/risk_control_rules/risk_config.toml` | +3 (`use_maker_close = false` master template) | ✅ |
| `settings/risk_control_rules/risk_config_demo.toml` | +5 (`use_maker_close = true` Phase 2a Demo) | ✅ |
| `settings/risk_control_rules/risk_config_live.toml` | +5 (`use_maker_close = false`) | ✅ |
| `settings/risk_control_rules/risk_config_paper.toml` | +5 (`use_maker_close = false`) | ✅ |

Total +164 / -1451（後者是同 PR 清掉 3 個 stale dispatch packet，本 E4 不審計 doc 部分）。

**0 over-touch**，與 E2 §F1 / PA §3.1 file list 完全一致。

---

## §3 Rust cargo test 結果矩陣（4 platform × 2 build mode × 2 run）

### §3.1 Mac debug build

```
$ cd /Users/ncyu/Projects/TradeBot/srv/rust && cargo test -p openclaw_engine --lib
test result: ok. 2972 passed; 0 failed; 1 ignored; 0 measured; 0 filtered out; finished in 0.73s
```

第 2 跑 `0.70s` 完全一致 → **非 flaky 確認** ✅

### §3.2 Mac release build

```
$ cargo test --release -p openclaw_engine --lib
test result: ok. 2972 passed; 0 failed; 1 ignored; 0 measured; 0 filtered out; finished in 0.72s
```

第 2 跑 `0.70s` 一致 → **非 flaky** ✅

### §3.3 Mac aarch64 release cross-compile

```
$ cargo check --release --target aarch64-apple-darwin -p openclaw_engine --lib
warning: 2 pre-existing warning（unused import + dead code，與本 PR 無關）
Finished `release` profile [optimized] target(s) in 7.94s
```

**0 error**，cross-arch portability green ✅

### §3.4 Linux trade-core release

```
$ ssh trade-core "bash -l -c 'cd ~/BybitOpenClaw/srv/rust && cargo test --release -p openclaw_engine --lib 2>&1 | tail -5'"
test result: ok. 2972 passed; 0 failed; 1 ignored; 0 measured; 0 filtered out; finished in 0.66s
```

第 2 跑 `0.64s` 一致 → **跨平台 ≡ Mac + 非 flaky 雙重確認** ✅

### §3.5 3 個新 use_maker_close test 個別 focused run

```
$ cargo test -p openclaw_engine --lib test_use_maker_close
test tick_pipeline::tests::dual_rail_dispatch::test_use_maker_close_toml_activates_on_demo ... ok
test tick_pipeline::tests::dual_rail_dispatch::test_use_maker_close_toml_rejected_on_live_and_paper ... ok
test tick_pipeline::tests::dual_rail_dispatch::test_use_maker_close_hot_reload_within_one_tick ... ok
test result: ok. 3 passed; 0 failed; 0 ignored; 0 measured; 2970 filtered out; finished in 0.00s
```

### §3.6 dual_rail_dispatch module 整體 release

```
$ cargo test --release -p openclaw_engine --lib dual_rail_dispatch
test result: ok. 24 passed; 0 failed; 0 ignored; 0 measured; 2949 filtered out; finished in 0.00s
```

既有 21 個 dispatch test + 3 個新 use_maker_close test = 24，**全 PASS、無命名空間衝突** ✅

---

## §4 Baseline 對照 + delta attribution

| 項 | 值 | 來源 |
|---|---|---|
| **Rust release baseline** | 2969 / 0 / 1 | TODO.md line 11 `b867e452` restored Linux cargo baseline 2026-05-17 |
| **Phase 1b 新增** | +3 tests | 3 個 use_maker_close test (§3.5 確認) |
| **預測 phase-1b HEAD** | 2972 / 0 / 1 | 2969 + 3 |
| **Mac release 實測** | 2972 / 0 / 1 | §3.2 ✅ |
| **Linux release 實測** | 2972 / 0 / 1 | §3.4 ✅ |
| **Mac debug 實測** | 2972 / 0 / 1 | §3.1 ✅ |
| **E2 verdict** | 2972 / 0 / 1 | E2 inline §F2（與本 E4 100% 對齊）|

**0 unexplained delta**。預測 == 實測 == E2 verify 三方一致。

---

## §5 Python pytest 結果（Mac + Linux）

### §5.1 Mac

```
$ PYTHONPATH=... python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/
8 failed, 4090 passed, 8 skipped, 423 warnings in 76.12s
```

### §5.2 Linux

```
$ ssh trade-core "bash -l -c 'cd ~/BybitOpenClaw/srv && python3 -m pytest program_code/.../control_api_v1/tests/ -q 2>&1 | tail -10'"
9 failed, 4121 passed, 10 skipped, 431 warnings in 86.83s
```

### §5.3 Failed 全部 pre-existing 非 phase-1b regression

| Test | Cause | 在 main 上跑 |
|---|---|---|
| `test_replay_subtab_static_assets.py::test_console_strategy_group_order_and_labels_are_operator_clear` | GUI static assertion | ✅ main 同 FAIL |
| `test_replay_subtab_static_assets.py::test_development_tab_covers_v001_to_v063` | GUI static assertion | ✅ main 同 FAIL |
| `test_replay_subtab_static_assets.py::test_demo_and_live_tabs_have_risk_shortcuts` | GUI static assertion | ✅ main 同 FAIL |
| `test_replay_subtab_static_assets.py::test_demo_and_live_fill_history_show_strategy` | GUI static assertion | ✅ main 同 FAIL |
| `test_replay_subtab_static_assets.py::test_strategy_identity_colors_are_shared_across_console_surfaces` | GUI static assertion | ✅ main 同 FAIL |
| `test_replay_subtab_static_assets.py::test_demo_and_live_fill_history_has_paged_subtabs` | GUI static assertion | ✅ main 同 FAIL |
| `test_openclaw_agent_control_static.py::test_tab_agents_mounts_openclaw_control_surface` | GUI static `/static/js/openclaw-agent-control.js?v=...mag018-v1` 找不到 | ✅ main 同 FAIL |
| `test_replay_routes_safe_query_audit.py::test_case2_pg_kill_simulation_returns_200_degraded` | **flaky** — solo run PASS / suite run FAIL（test ordering dep）| ✅ solo PASS confirmed |
| Linux 多 1 個 `test_grafana_data_writer.py::TestGrafanaDataWriterLifecycle::test_start_sets_running` | Linux-specific lifecycle race（Mac 不命中）| — platform timing |

**Structural verification**: `git diff main..HEAD --name-only --diff-filter=AM` 過濾 `.py` 命中 = **0**。phase-1b 沒動任何 .py 檔，所以 9 failed 不可能是新 regression。

---

## §6 PA adversarial catch + Demo-only guard 完整性驗證

### §6.1 PA §3.2 enforcement clause 1（setter call）

```rust
// pipeline_config.rs:131
let _ = self.set_use_maker_close_runtime(snap.runtime.use_maker_close);
```

驗證 `grep -n "set_use_maker_close_runtime\|use_maker_close.*PipelineKind::Demo"`：

- pipeline_config.rs:131 命中（apply_risk_snapshot 路徑）
- commands.rs:84 + 91 + 105 命中（setter 本體 + getter）

**setter call 在位**，不是直接寫 `self.use_maker_close = snap.runtime.use_maker_close` ✅

### §6.2 commands.rs:91-103 Demo-only guard

```rust
pub fn set_use_maker_close_runtime(&mut self, enabled: bool) -> bool {
    if enabled && self.pipeline_kind != PipelineKind::Demo {
        tracing::warn!(
            kind = %self.pipeline_kind,
            "close-maker runtime enable rejected outside Demo pipeline \
             / close-maker runtime 啟用僅允許 Demo pipeline"
        );
        self.use_maker_close = false;
        return false;
    }
    self.use_maker_close = enabled;
    true
}
```

`git diff main..HEAD -- commands.rs` = empty（lines 91-103 unchanged，與 E2 §"Demo-only guard 完整" 一致）✅

### §6.3 4 TOML 數值 vs AMD v0.6 §3 Rollout Posture

| TOML | Value | AMD line | Match |
|---|---|---|---|
| `risk_config.toml` (master) | `false` | line 84 cold-default | ✅ |
| `risk_config_demo.toml` | `true` | line 89 Phase 2a Demo | ✅ |
| `risk_config_live.toml` | `false` | line 86 Phase 0 NOT Live | ✅ |
| `risk_config_paper.toml` | `false` | line 86 Phase 0 NOT Paper | ✅ |

**4-env TOML 正確對齊 AMD v0.6** ✅

### §6.4 serde default + RuntimeKnobs Default 雙路徑

```rust
// risk_config_advanced.rs:371
#[serde(default)]
pub use_maker_close: bool,

// line 390 impl Default for RuntimeKnobs
use_maker_close: false,
```

兩條 path 都 false → TOML 缺欄位也 fail-safe false ✅

---

## §7 Test 3 ArcSwap hot-reload 邏輯驗證

讀 `dual_rail_dispatch.rs:399-444`：

| Phase | 操作 | Assert | 驗證點 |
|---|---|---|---|
| 0 cold | `RiskConfig::default()` + `set_risk_store` | `!demo.use_maker_close()` | ctor 預設 false ✅ |
| 1 patch | `next.runtime.use_maker_close = true; store.replace(next, PatchSource::Operator)` | `store.version() == v0 + 1` + `!demo.use_maker_close()` | 版本號上升但 pipeline 還沒 sync ✅ |
| 2 tick | `demo.on_tick(make_event(...))` → sync_risk_config_if_changed → apply_risk_snapshot → set_use_maker_close_runtime(true) | `demo.use_maker_close()` + `risk_config_version_seen == store.version()` | 1 tick 內 flip true + version 同步 ✅ |

**AMD §3 「TOML hot-reload → 1 tick」契約成立**，textbook-clean ✅

---

## §8 Mock / Anti-pattern 審查

| Check | 結果 |
|---|---|
| 3 new tests mockall 使用 | 0（純 real `TickPipeline::with_kind` / `ConfigStore::new` / `set_risk_store` / `on_tick` / `RiskConfig::default()` / `store.replace`） |
| `set_use_maker_close_for_test` 繞過 setter | 0（3 個新 test 不用此 helper，全走真實 set_risk_store + on_tick chain） |
| 業務邏輯 100% 真跑 | ✅ Demo-only guard / serde default / ArcSwap version bump / 1-tick sync 全鏈真執行 |
| Deleted tests | 0（**沒刪測試使測試通過**） |
| Assertion value tampering | 0（assertion message 全是 AMD spec 語義） |
| Anti-pattern hit | **0** |

**Mock 審查 PASS**，per regression-testing-protocol §5 OK pattern。

---

## §9 跑兩遍非 flaky 確認

| Engine | Run 1 | Run 2 | 一致 | 非 flaky |
|---|---|---|---|---|
| Mac debug lib | 2972/0/1 @ 0.73s | 2972/0/1 @ 0.70s | ✅ | ✅ |
| Mac release lib | 2972/0/1 @ 0.72s | 2972/0/1 @ 0.70s | ✅ | ✅ |
| Linux release lib | 2972/0/1 @ 0.66s | 2972/0/1 @ 0.64s | ✅ | ✅ |

3 個雙跑 100% 一致 → **新 3 test 非 flaky，既有 2969 test 也非 flaky**（time 變動 ≤ 0.04s 是 incremental cache 效應）。

---

## §10 跨語言一致性 / SLA

| 項 | 結果 |
|---|---|
| Cross-language Python↔Rust 一致性 | **N/A** — `use_maker_close` 是 Rust SSoT runtime flag，無 Python dual implementation |
| SLA hot path | **N/A** — 3 new test 是 ArcSwap hot-reload 整合 test（boot-time + 1-tick latency 驗證），非 tick hot path |
| H0 Gate < 1ms / Tick path < 0.3ms / IPC < 5ms | 不適用本 PR scope |

---

## §11 Verdict

### **REGRESSION-PASS → QA deploy readiness ready → operator `restart_all.sh --rebuild` READY**

| 維度 | 結果 |
|---|---|
| Mac Rust debug lib（雙跑）| 2972 / 0 / 1 ✅ |
| Mac Rust release lib（雙跑）| 2972 / 0 / 1 ✅ |
| Mac aarch64 release cross-compile | 0 err / 2 pre-existing warn ✅ |
| Linux Rust release lib（雙跑）| 2972 / 0 / 1 ✅ |
| 3 new use_maker_close tests | 3 / 0 / 0 ✅ |
| dual_rail_dispatch module | 24 / 0 / 0 ✅ |
| Mac Python pytest | 4090 / 8 pre-existing / 8 skipped — **0 phase-1b regression** ✅ |
| Linux Python pytest | 4121 / 9 pre-existing / 10 skipped — **0 phase-1b regression** ✅ |
| Baseline delta attribution | 2969 → +3 → 2972（0 unexplained）✅ |
| PA adversarial catch 落地 | pipeline_config.rs:131 setter call ✅ |
| Demo-only guard 完整 | commands.rs:91-103 diff = empty ✅ |
| 4 TOML 對齊 AMD v0.6 §3 | 全部 match ✅ |
| ArcSwap hot-reload Test 3 | textbook-clean 3-phase ✅ |
| Mock / anti-pattern | 0 hit ✅ |
| 非 flaky 雙跑 | Mac × 2 + Linux × 2 全 PASS ✅ |
| Race protocol 5 條 | 全 PASS ✅ |

### Recommendation to PM

1. **QA gate**：可進 e2e-integration-acceptance（QA 階段）驗 Phase 6 hard gates（業務鏈完整 + 跨模塊一致）。
2. **Operator deploy**：QA 通過後 PM 派 operator 在 Linux trade-core 跑 `bash helper_scripts/restart_all.sh --rebuild`，Phase 2a Demo runtime 啟動。
3. **24h watch**：per AMD v0.6 §3 Phase 2a 計劃，24h 後驗 `attempt_pct >= 25%` on Demo whitelist closes（QA SQL verification）。
4. **沒有 BLOCKER**。
5. **不必開新 P2 ticket**——本 PR 是 Phase 1b 整合 IMPL，後續 Phase 2b live_demo 啟用是獨立 AMD wording + IMPL ticket（per PA §3.6 critical flag）。

---

**E4 REGRESSION DONE: PASS** · report path: `srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-18--phase_1b_runtime_activator_full_regression.md`
