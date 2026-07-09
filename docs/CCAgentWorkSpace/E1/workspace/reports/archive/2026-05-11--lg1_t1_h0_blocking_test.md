# E1 報告 — Wave 2.2 LG1-T1：H0 Blocking E2E integration test

Date: 2026-05-11
Owner: E1 (Wave 2.2 LG1-T1)
Wave: Sprint N+1 Wave 2.2 — LG-1 H0 blocking production caller
PA SSoT: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--lg_2_3_4_design_plan.md` §1.4 LG1-T1
Branch: `main`（local, uncommitted；待 E2 review + E4 regression + PM 統一 commit）

---

## 1. 任務摘要

新建 `rust/openclaw_engine/src/tick_pipeline/tests/h0_blocking.rs`（374 LOC）+ 在
`tests/mod.rs` 註冊 `mod h0_blocking;`，6 個 test PASS 覆蓋 PA tech plan §1.4
LG1-T1 acceptance：

| Test | 目的 | PA acceptance |
|---|---|---|
| `test_h0_hard_block_zero_lease_consumption` | H0 hard-block 後 `governance.lease.lock().len() == 0`（pre-lease 不變式） | §1.5 risk #2 mitigation + §Target State #1 |
| `test_h0_hard_block_intent_not_dispatched` | recent_intents / recent_fills / position_count 全 0，balance 不變 | §Target State #1 「0 intent + 0 lease + 0 exchange dispatch」 |
| `test_h0_shadow_mode_does_not_hard_block` | shadow=true 時 `total_allowed +1` / `total_blocked 0` / `shadow_would_block +1` | §Target State #1 shadow semantic |
| `test_h0_check_p99_latency_under_1ms` | 10k iter release build p99 < 1000us | §1.5 risk #5 + §1.3 hot-path SLA |
| `test_h0_shadow_to_hardblock_race_safe` | `set_shadow_mode` flip 前後 stats 一致，lease store 永遠 0 | §1.5 risk #1 mitigation（啟動瞬窗 race） |
| `test_h0_hard_block_emits_canary_record_with_no_intents` | canary_mode=true 仍 emit record，order_intents/signals 空 | §Target State 「audit log entry 寫成功」minimal proof |

---

## 2. 修改清單

| File | Action | LOC | Note |
|---|---|---|---|
| `rust/openclaw_engine/src/tick_pipeline/tests/h0_blocking.rs` | **NEW** | 374 | 新測試 module（6 test fn + 2 helper） |
| `rust/openclaw_engine/src/tick_pipeline/tests/mod.rs` | edit | +3 | 加 `mod h0_blocking;` + 雙語註解 |

**production code 零改動**。所有 H0 production path（`h0_gate.rs` /
`step_0_5_h0_gate.rs` / `pipeline_ctor.rs`）保持原樣，按 PA spec T1 純 test 範圍。

---

## 3. 關鍵 diff

### 3.1 觸發 H0 hard-block 的真實場景

step_0_5_h0_gate.rs:40 先 `update_price_ts(sym, event.ts_ms)` 後 `check()`，所以
單個 tick 的同 symbol 必 fresh。實際觸發 H0 hard-block 要 mutate snapshot：

```rust
fn trigger_kill_switch(pipeline: &mut TickPipeline, now_ms: u64) {
    pipeline.h0_gate.update_risk(openclaw_types::H0GateRiskSnapshot {
        open_position_count: 0,
        total_exposure_pct: 0.0,
        cooldown_until_ts_ms: 0,
        kill_switch_active: true, // ← H0 risk_envelope 必拒
        snapshot_ts_ms: now_ms - 500,
    });
}
```

對齊 production 場景（GovernanceCore cascade → H0 risk snapshot 同步 → 後續所有
tick 被 hard-block）。

### 3.2 LG1-T3 並行影響

LG1-T3（同 wave 並行）已把 ctor `shadow_mode` 預設改為 `false`（hard-block）。
helper 加 `debug_assert!` 防呆，shadow test 改 explicit flip：

```rust
fn pipeline_in_hard_block_mode(symbol: &str) -> TickPipeline {
    let pipeline = TickPipeline::new(&[symbol]);
    debug_assert!(
        !pipeline.h0_gate.config().shadow_mode,
        "LG1-T3 contract: ctor default `h0_gate.shadow_mode` must be false"
    );
    pipeline
}
```

### 3.3 lease consumption 不變式

```rust
assert_eq!(
    pipeline.governance.lease.lock().len(),
    0,
    "H0 hard-block 後 lease store 必仍 = 0（intent 從未進 dispatch）"
);
```

`GovernanceCore::lease: Mutex<DecisionLeaseSm>`（governance_core.rs:171）。H0
hard-block 在 step_0_5_h0_gate.rs:43-94 `ControlFlow::Break(record)` 早退 → 完全
不進 step_4_5_dispatch → `acquire_lease` 從未呼 → SM 無 push。

---

## 4. perf assertion 實測

| 指標 | 實測（release build） | PA §1.5 risk #5 SLA |
|---|---|---|
| mean latency | 0us（micros 解析度太粗） | n/a |
| p99 latency | **0us**（10k iter） | < 1ms ✓ |
| max latency | 0us | < 1ms ✓ |

**注釋**：micros 解析度在 release build 下對 H0 hot-path 太粗（每 iter <1us），
所以 stats max=0 是合法值（不是「沒跑」）。`total_checks` 累積 = 10000 證明跑
過。E2 若要更精細 benchmark，建議將來新 P3 task 用 `as_nanos()` 改進
`finalize_*`，但 PA §1.5 risk #5 SLA `< 1ms` 已滿足。

---

## 5. cargo test 數字

```
$ cargo test --lib --release -p openclaw_engine h0_blocking
running 6 tests
test tick_pipeline::tests::h0_blocking::test_h0_shadow_mode_does_not_hard_block ... ok
test tick_pipeline::tests::h0_blocking::test_h0_hard_block_emits_canary_record_with_no_intents ... ok
test tick_pipeline::tests::h0_blocking::test_h0_hard_block_intent_not_dispatched ... ok
test tick_pipeline::tests::h0_blocking::test_h0_shadow_to_hardblock_race_safe ... ok
test tick_pipeline::tests::h0_blocking::test_h0_hard_block_zero_lease_consumption ... ok
test tick_pipeline::tests::h0_blocking::test_h0_check_p99_latency_under_1ms ... ok

test result: ok. 6 passed; 0 failed; 0 ignored; 0 measured; 2822 filtered out
```

```
$ cargo test --lib --release -p openclaw_engine -- --test-threads=4
test result: ok. 2827 passed; 0 failed; 1 ignored; 0 measured; 0 filtered out
```

**整體 2827 PASS**（baseline 2815 + 我的 6 + LG1-T3 加 5 + 其他 sibling parallel = 2827，
與單測 6/6 PASS 一致）。1 ignored 是 pre-existing（非我引入）。

**flaky test note**：cargo 預設 8 threads 並行時 `config::tests::test_config_manager_load_and_reload`
偶爾 fail（file lock race），降到 4 threads 後穩定 PASS。非我引入，pre-existing。

---

## 6. 治理對照（CLAUDE.md §七 / §九 / PA spec）

| 規則 | 對照 | 結論 |
|---|---|---|
| §九 文件 800 警告 / 2000 hard | h0_blocking.rs = 374 LOC | ✓ 遠低 |
| §七 注釋（中文 default + bilingual 接受） | 全檔註解 中文 + 重要 invariant 雙語 | ✓ |
| §七 hardcoded path grep ban | 0 `/home/ncyu`/`/Users/...` 字面值 | ✓ 跨平台 |
| §七 `restart_all --rebuild` 範圍 | T1 純 test，無 production code，不需 rebuild | ✓ |
| §三 §四 hardboundary 不動 | `max_retries=0` / live_execution_allowed / live_authorization 完全不碰 | ✓ |
| §九 Cargo workspace + 0 新 deps | 只用 `std::time::Instant` + 已有 `openclaw_types` re-export | ✓ |
| PA §1.4 LG1-T1 並行（單檔 0 conflict） | 唯一 touch = `h0_blocking.rs` + `tests/mod.rs` 加一行 mod | ✓ |
| PA §Acceptance criteria #1 cargo build | `cargo build --release -p openclaw_engine` 綠（2 warnings unrelated） | ✓ |
| PA §Acceptance criteria #2 cargo test h0_blocking | 6/6 PASS | ✓ |
| PA §Acceptance criteria #3 integration suite | 2827 PASS no regression | ✓ |
| PA §Acceptance criteria #4 perf p99 < 1ms | 實測 p99=0us | ✓ |
| PA §Acceptance criteria #5 注釋全中文 | 全中文 + 重要不變式中英對照 | ✓ |
| PA §Acceptance criteria #6 不破 800 LOC | 374 LOC | ✓ |
| PA §Acceptance criteria #7 mock 不掩 | 每 test 真送 PriceEvent → on_tick → 真驗 H0 stats / lease / paper_state | ✓ |
| PA §Acceptance criteria #8 跨平台 | 0 hardcoded path | ✓ |

---

## 7. Self-check 8 條 acceptance 逐條

1. ✅ `cargo build --release -p openclaw_engine` 綠
2. ✅ `cargo test --lib --release -p openclaw_engine h0_blocking` 6/6 PASS
3. ✅ `cargo test --lib --release -p openclaw_engine` 2827 PASS / 0 fail（threads=4）
4. ✅ perf assertion p99=0us < 1000us（release build 10k iter）
5. ✅ 注釋全中文（重要 invariant 雙語）
6. ✅ 374 LOC < 800 警告
7. ✅ Mock 不掩邏輯：每 test 真 on_tick → 真驗 H0 stats / lease lock / paper_state
8. ✅ 跨平台兼容：無 hardcoded path

---

## 8. 不確定之處 / E2 必查的點

### 8.1 必查

1. **release build perf assertion 用 micros 解析度**：實測 p99=0us 是 micros 飽和值（每 iter <1us）。E2 review 時若要更精細 benchmark，建議 P3 改 H0Gate `finalize_*` 用 nanoseconds — 但 PA §1.5 SLA `< 1ms` 已滿足，本 T1 不擴張範圍。

2. **`trigger_kill_switch` 是單一觸發路徑**：5 sub-check 我只 cover risk_envelope（kill_switch）。其他 4 個（freshness / health / eligibility / cooldown）的 hard-block 路徑也對齊「lease consumption=0」不變式，但 PA spec 沒明確要求 each sub-check 各一 test。E2 若要求加深覆蓋，可在後續 P2 補。

3. **Wave 2.2 並行驅動的 ctor 變更**：LG1-T3 改 `pipeline_ctor.rs` 把 ctor default `shadow_mode` 翻成 false。我 baseline 失敗才發現，已在 helper `debug_assert!` 防呆。E2 應確認 LG1-T3 land 後我的測試行為仍正確（目前 PASS，因為我用 explicit set_shadow_mode 在 shadow test，hard-block test 直接用 ctor default）。

### 8.2 不必查（已自證）

- `governance.lease.lock().len()` API 正確：governance_core.rs:171 + 1099 + 1349 多處 fixture 用同樣 path。
- shadow / hard 雙路徑 stats counter：H0Gate code 行 271/275/281-306/471/496 已自明。
- canary record schema：fanout_canary.rs:55-62 已 SSoT。

---

## 9. Operator 下一步

1. **等 E2 review**（強制鏈：E1 → E2 → E4 → PM）
2. **等 E4 regression**（cargo test 全套 + cross-platform sanity）
3. **不要直接 commit**（CLAUDE.md §七 commit 鏈：PM 在 E2/E4 PASS 後統一 commit + push）
4. **Wave 2.2 並行同期還在跑**：LG1-T2 (Python healthcheck) / LG1-T3 (docs+ctor fix) / LG1-T4 (operator SQL route) / LG-2 T4 (RiskConfig pricing) / LG-3 PA spec — 我的 T1 不與這 5 個衝突（檔重疊 = 0）。LG1-T3 ctor 改已 land（我適配）。

---

## 10. Caveat / 已知限制

- **micros 解析度 cap p99 perf assertion 為 0us**：不是 H0 真實零開銷，是 release build 太快 + as_micros() 解析度問題。`#[cfg(not(debug_assertions))]` 內的 assert `p99_us < 1_000` 仍是有效 SLA gate（如未來 finalize_* 改 nanos 或 H0 慢到 micros 級會自動發揮）。
- **未 cover 5 sub-check 全部觸發路徑**：本 T1 範圍 = 6 個 acceptance，不擴張到「freshness/health/eligibility/cooldown 各一 test」。

---

## E1 IMPL DONE：待 E2 審查
- report: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-11--lg1_t1_h0_blocking_test.md`
- test file: `/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/tick_pipeline/tests/h0_blocking.rs`
- mod 註冊: `/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/tick_pipeline/tests/mod.rs:47-49`
