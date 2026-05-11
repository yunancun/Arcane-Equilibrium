# E1-A — P0 Replay Tier A T1 + T2 + T2.5 IMPL DONE（2026-05-11）

**Owner**：E1-A
**Trigger**：PA Tier A design `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--p0_replay_engine_counterfactual_fix_design.md`；operator 拍板 ship。
**Scope**：T1（is_pinned wire）+ T2（position_state wire）+ T2.5（ReplayPosition.owner_strategy add）
**Branch**：main HEAD `17d95d67`（base） → 本次 IMPL 改動本地 unstaged，待 E2 審查後與 E1-B / E1-C / E1-D 一同 push。
**16 原則合規**：16/16；**§四 5 硬邊界觸碰**：0；**forbidden_guard 違反**：0。

---

## 1 任務摘要

按 PA Tier A §3.3 設計修 `runner.rs build_tick_context` + `risk_adapter.rs ReplayPosition` + `apply_fill.rs apply_fill_open`，把三個 hardcoded 點轉為 caller-injected：

- **T1**：`is_pinned: true` → caller 由 `scanner_timeline.is_active_at(symbol, ts_ms)` 推算；無 timeline 保留 true（synthetic walker baseline）。
- **T2**：`position_state: None` → caller 由 `ReplayPaperSnapshot.get_position(symbol)` 映射為 stack-local `PaperPosition` borrow；無倉位 None。
- **T2.5**：`ReplayPosition` 加 `owner_strategy: String` field；`apply_fill_open` 寫 `intent.strategy.clone()`；fresh open path 對齊 production first-write-wins 語義。

`build_replay_position_borrow()` 新增 helper 把 ReplayPosition 構造成 stack-local PaperPosition；per-iteration NLL borrow 釋放後不衝突 `paper_snapshot.as_mut()`。

---

## 2 修改清單

| 檔 | 變動 | LOC delta |
|---|---|---|
| `rust/openclaw_engine/src/replay/risk_adapter.rs` | `ReplayPosition` 加 `owner_strategy: String`；同檔 1 test seed 補欄位 | +11 / -0 |
| `rust/openclaw_engine/src/replay/apply_fill.rs` | `apply_fill_open` 簽名加 `owner_strategy: &str`；fresh open path 寫入；callsite 傳 `&intent.strategy` | +10 / -2 |
| `rust/openclaw_engine/src/replay/runner.rs` | `build_tick_context` 簽名加 `is_pinned: bool` + `position_state: Option<&'a PaperPosition>`；caller `execute_adapter_pipeline` 推算注入；新增 `build_replay_position_borrow` helper | +69 / -5 |
| `rust/openclaw_engine/src/replay/runner_tests.rs` | 3 個 ReplayPosition test seed 補 owner_strategy；新加 4 個 sanity test | +141 / -0 |

**Total**：~224 LOC（PA estimate ~110-140 LOC + 80 LOC sanity test）。

---

## 3 關鍵 diff

### 3.1 ReplayPosition struct 加 owner_strategy（risk_adapter.rs）

```rust
#[derive(Debug, Clone)]
pub struct ReplayPosition {
    pub symbol: String,
    pub is_long: bool,
    pub qty: f64,
    pub entry_price: f64,
    /// Sprint N+1 D+1 Tier A T2.5：策略歸屬，鏡射 `PaperPosition.owner_strategy`。
    /// 由 `apply_fill_open` 從 `OrderIntent.strategy` 寫入。
    pub owner_strategy: String,
}
```

### 3.2 apply_fill_open 簽名 + fresh open 寫 owner_strategy（apply_fill.rs）

```rust
pub(super) fn apply_fill_open(
    &mut self,
    symbol: &str,
    is_long: bool,
    qty: f64,
    fill_price: f64,
    fee: f64,
    owner_strategy: &str,  // ← T2.5 新參數
) {
    // ...
    snap.positions.push(ReplayPosition {
        symbol: symbol.to_string(),
        is_long,
        qty,
        entry_price: fill_price,
        owner_strategy: owner_strategy.to_string(),  // ← 寫入
    });
}
```

Caller in `process_open_intent`：
```rust
self.apply_fill_open(
    &intent.symbol,
    intent.is_long,
    partial.filled_qty,
    fill_price,
    fee,
    &intent.strategy,  // ← OrderIntent.strategy
);
```

### 3.3 build_tick_context 簽名 + caller wire（runner.rs）

```rust
fn build_tick_context<'a>(
    event: &'a MarketEvent,
    inputs: &'a ReplayTickInputs,
    is_pinned: bool,                                          // ← T1
    position_state: Option<&'a crate::paper_state::PaperPosition>,  // ← T2
) -> crate::tick_pipeline::TickContext<'a> {
    crate::tick_pipeline::TickContext {
        // ... 14 unchanged fields ...
        position_state,
        is_pinned,
    }
}
```

Caller (`execute_adapter_pipeline` line ~1005)：
```rust
let is_pinned = self
    .scanner_timeline
    .as_ref()
    .map(|tl| tl.is_active_at(&event.symbol, event.ts_ms))
    .unwrap_or(true);

let stack_pp_opt: Option<crate::paper_state::PaperPosition> = self
    .paper_snapshot
    .as_ref()
    .and_then(|snap| snap.get_position(&event.symbol))
    .map(|rp| build_replay_position_borrow(rp, event.ts_ms));
let pp_ref: Option<&crate::paper_state::PaperPosition> = stack_pp_opt.as_ref();

let ctx = build_tick_context(event, &tick_inputs, is_pinned, pp_ref);
```

### 3.4 build_replay_position_borrow helper（runner.rs 新加）

```rust
fn build_replay_position_borrow(
    rp: &crate::replay::risk_adapter::ReplayPosition,
    event_ts_ms: i64,
) -> crate::paper_state::PaperPosition {
    crate::paper_state::PaperPosition {
        symbol: rp.symbol.clone(),
        is_long: rp.is_long,
        qty: rp.qty,
        entry_price: rp.entry_price,
        best_price: rp.entry_price,
        entry_fee: 0.0,
        entry_ts_ms: event_ts_ms.max(0) as u64,
        unrealized_pnl: 0.0,
        entry_context_id: String::new(),
        owner_strategy: rp.owner_strategy.clone(),
        entry_notional: rp.qty * rp.entry_price,
        max_favorable_pnl_pct: 0.0,
        peak_reached_ts_ms: 0,
    }
}
```

---

## 4 治理對照

| 規範 | 對齊 |
|---|---|
| CLAUDE.md §一 玄衡定位 | ✅ replay isolated subprocess |
| §二 16 原則 | ✅ 16/16（生存>利潤 / 失敗收縮 / 認知誠實 / 持續進化 / 組合級風險） |
| §四 硬邊界 5 條 | ✅ 0 觸碰（live_execution / lease emit / max_retries / OPENCLAW_ALLOW_MAINNET / live_reserved） |
| §五 架構總覽 | ✅ replay subprocess，不動 main pipeline |
| §七 跨平台 | ✅ 0 硬編碼路徑（grep `/home/ncyu` `/Users/[a-z]+` 0 hit） |
| §七 注釋（2026-05-05 中文默認） | ✅ 新增注釋全中文，未碰原英文段不主動清 |
| §七 SQL migration | N/A（無 SQL 改動） |
| §八 工作流 | ✅ E1-A IMPL → E2 review → E4 regression → PM commit |
| §九 文件大小 2000 | ✅ runner.rs 1230 / risk_adapter.rs 573 / apply_fill.rs 750 / runner_tests.rs 1467 全在 2000 以下 |
| forbidden_guard / V3 §6.2 | ✅ proof_4 acceptance PASS（detail §5） |
| V3 §12 #10/#11/#14 | ✅ proof_1/4/5 + R5-T7 proof_7/proof_8 全 PASS |

---

## 5 forbidden_guard / V3 §6.2 對齊驗證

### 5.1 PaperPosition import 合規

PA spec §5.1 已釐清：`crate::paper_state::PaperPosition` 是 `paper_state::containers.rs` 的 pure data struct（`#[derive(Debug, Clone, Serialize, Deserialize)]`）；與被 forbid 的 `PaperState`（DB writer + 全域 mutable + IPC subscriber）是同 module 不同 layer。`TickContext` 在 production tick_pipeline/mod.rs:32 即已 import 同 type，replay 引用對稱合理。

實證：
- **proof_4_forbidden_path_trip_via_env_aborts_run**：PASS（forbidden_guard::enforce_at_runtime 環境變數 trip 仍正確觸發 AbortedForbidden）
- **proof_1_happy_path_synthetic_fixture**：PASS（baseline byte-equal 不破）
- **proof_5_baseline_vs_candidate_two_runs**：PASS（parameter delta scenario 不破）

### 5.2 7 條 forbidden surface 檢查

| Surface | T1 | T2 | T2.5 |
|---|---|---|---|
| Decision Lease acquire/release | not touched | not touched | not touched |
| IPC server start | not touched | not touched | not touched |
| WS client start | not touched | not touched | not touched |
| Exchange dispatch | not touched | not touched | not touched |
| DB writer channel use | not touched | not touched | not touched |
| Live/demo config mutate | not touched | not touched | not touched |
| Advisory write outside PL/pgSQL | not touched | not touched | not touched |

### 5.3 cargo test 驗證鏈

```
$ cargo test --release -p openclaw_engine --lib                              → 2804 passed (+4 sanity); 0 failed
$ cargo test --release -p openclaw_engine --lib replay                       → 113 passed; 0 failed
$ cargo test --release -p openclaw_engine --test replay_forbidden_guard_acceptance --features replay_isolated  → 4 passed; 0 failed
$ cargo test --release -p openclaw_engine --test replay_runner_e2e --features replay_isolated                 → 6 passed; 0 failed (proof_1..5 incl byte-equal)
$ cargo test --release -p openclaw_engine --test replay_runner_e2e_param_delta --features replay_isolated     → 2 passed; 0 failed (R5-T7 cross-language proof_7/8)
$ cargo test --release -p openclaw_engine --test replay_profile_acceptance --features replay_isolated         → 5 passed; 0 failed
$ cargo test --release -p openclaw_engine --test replay_mac_policy_acceptance --features replay_isolated      → 4 passed; 0 failed
$ cargo test --release -p openclaw_engine --test replay_manifest_signer_xlang_consistency --features replay_isolated → 8 passed; 0 failed
```

**Baseline**：2800 passed → **Post-IMPL**：2804 passed（+4 sanity）；regression 0。

### 5.4 cargo build replay_runner binary

```
$ cargo build --release --bin replay_runner --features replay_isolated → Finished release in 14.08s ✓
```

---

## 6 4 個新加 sanity test 內容

| Test name | 驗證 |
|---|---|
| `build_replay_position_borrow_preserves_owner_strategy` | T2.5 helper 把 ReplayPosition.owner_strategy 對齊寫進 stack-local PaperPosition |
| `build_replay_position_borrow_clamps_negative_ts` | event_ts_ms < 0 → clamped to 0u64（對齊 build_tick_context） |
| `build_tick_context_threads_is_pinned_and_position_state` | T1+T2 雙路徑：(true, Some) / (false, None) 均正確透傳 |
| `replay_position_owner_strategy_default_empty_string` | T2.5 backward-compat：空字串作為 first-write-wins 初始值 |

---

## 7 不確定之處 + Operator 決定點

1. **`build_replay_position_borrow` 與 production `PaperPosition` field 預設值差**：production `PaperState.proactive_mirror_insert` 等 path 寫入完整 `unrealized_pnl / max_favorable_pnl_pct / peak_reached_ts_ms` 等 runtime track field；replay 沒有真實源，全 0/空。**Tier A acceptance 不要求 strategy 讀這些 field**（entry path 只看 symbol / is_long / owner_strategy），所以可行；但若 strategy 未來改讀 `unrealized_pnl` 等 → 需 enhance helper。**接受 trade-off**。

2. **Lifetime 設計**：`stack_pp_opt` 在 per-iteration local scope；`pp_ref: Option<&PaperPosition>` 借自它，`ctx` 借 pp_ref，`strategy.on_tick(&ctx)` 完 `ctx` drop，pp_ref / stack_pp_opt 隨之 drop。下一 iteration 重建。cargo test 已驗（無 borrow checker fail），E2 review 仍建議再過一次。

3. **next E1 dispatch**：E1-C T5 per-symbol price anchor 將動同 `risk_adapter.rs` ReplayPaperSnapshot struct（加 `latest_price_by_symbol: HashMap<String, f64>`）；E1-A 已先 land struct field add T2.5，E1-C rebase 加新 HashMap field 不應衝突。E1-D acceptance test 需等 E1-A/B/C 全 land。

---

## 8 Operator 下一步

1. 派 **E2 review**：
   - 驗 PaperPosition stack-local borrow lifetime（per-iteration NLL）
   - nm symbol audit（mac strip + linux 重跑）
   - cargo test full regression
2. 派 **E4 regression**：跑 R5-T7 cross-language parameter delta + proof_1/4/5 byte-equal
3. 等 E1-B / E1-C / E1-D 完成後 PM 統一 commit + push
4. 跑 Tier A acceptance：Option 2 ON/OFF + Phase 0 ON/OFF + A-Lite 4-combo replay

---

## 9 完成序列

- [x] PA spec 讀完（§T1 + §T2 + §T2.5 + §5 forbidden_guard）
- [x] E1 profile + memory 讀完（注意 multi-session race；不主動 push 等 PM 統一）
- [x] IMPL T1 + T2 + T2.5 + helper（runner.rs + risk_adapter.rs + apply_fill.rs）
- [x] 4 個 ReplayPosition test seed 補 owner_strategy
- [x] 4 個 sanity test 加 runner_tests.rs
- [x] cargo build replay_runner --features replay_isolated PASS
- [x] cargo test --lib replay 113 passed / 全 lib 2804 passed
- [x] forbidden_guard acceptance 4/4 + replay_runner_e2e 6/6 + R5-T7 2/2 + profile 5/5 + mac_policy 4/4 + xlang signer 8/8 全 PASS
- [x] 跨平台 grep `/home/ncyu` / `/Users/[a-z]+` 0 hit
- [x] §九 2000 LOC cap 全綠
- [x] IMPL DONE report 寫
- [ ] E2 review（pending）
- [ ] E4 regression（pending）
- [ ] PM 統一 commit + push（pending E1-B/C/D 全完成）

---

## E1 memory 追加（建議行）

```
## Sprint N+1 D+1 P0 Replay Tier A E1-A T1+T2+T2.5 IMPL DONE（2026-05-11）

**觸發**：PA `2026-05-11--p0_replay_engine_counterfactual_fix_design.md` Tier A 派發；operator 拍板 ship。

**範圍**：T1 is_pinned wire + T2 position_state wire + T2.5 ReplayPosition.owner_strategy add；3 檔 +1 test 檔；~224 LOC（含 ~80 LOC sanity test）。

**關鍵設計決定**：
1. PaperPosition stack-local borrow：`build_replay_position_borrow` helper 把 ReplayPosition 構造成 owned PaperPosition value，借 `Option<&PaperPosition>` 餵 ctx；per-iteration NLL 自動釋放後不衝突 paper_snapshot.as_mut() mutable borrow。
2. owner_strategy first-write-wins：對齊 production；同向加倉不覆寫，減倉只 net qty。
3. is_pinned fallback：無 timeline 時保留 true，與 synthetic walker proof_1/4/5 byte-equal baseline 對齊。

**驗證**：
- cargo build replay_runner --features replay_isolated PASS
- cargo test --lib：baseline 2800 → post-IMPL 2804 (+4 sanity)；0 regression
- replay-specific: 113 passed (lib replay) / 4 (forbidden_guard acceptance) / 6 (e2e proof_1..5) / 2 (R5-T7 xlang) / 5 (profile) / 4 (mac_policy) / 8 (xlang signer)
- forbidden_guard / V3 §6.2 全綠；§四 5 硬邊界 0 觸碰；16 原則 16/16
- 跨平台 grep / 文件大小 / 注釋默認中文 全綠

**核心教訓**：
1. PaperPosition 從 paper_state::containers 引出當 pure data struct 用，與 production TickContext 對稱；forbidden_guard 禁的是 mutate side。
2. `build_replay_position_borrow` 是 stack-local owned 值，`Option<&T>` 借它，lifetime per-iteration NLL — 避免 owned by-value 進 TickContext 的 ABI 改動。
3. test seed 全 ReplayPosition callsite 需更新 owner_strategy（rust E0063 强制），這是 struct add field 的 expected blast radius。
4. UTF-8 中文標點（`，`）與 ASCII `,` 在 Edit tool old_string 不可互換；必先 od/Read 對齊原文字節再 Edit。

**完整報告**：`srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-11--replay_tier_a_e1_a_runner_position_state.md`
```

---

E1-A IMPLEMENTATION DONE: 待 E2 審查（report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-11--replay_tier_a_e1_a_runner_position_state.md`）
