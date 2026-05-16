# E1 · P1-PORTFOLIO-RESTING-EXPOSURE-1 IMPL Self-Report（Round 2 — Test Coverage Top-up）

**Date**：2026-05-16
**Agent**：E1
**Ticket**：`P1-PORTFOLIO-RESTING-EXPOSURE-1`
**Status**：🟡 **TEST IMPL DONE — 待 PM 確認 dispatch stale 處置 + 派 E2/E4 對抗審**
**Branch**：`main`（working tree only，尚未 commit）

---

## §1 任務摘要

PA dispatch 派發 ticket `P1-PORTFOLIO-RESTING-EXPOSURE-1`，要求 4 個 Task：
1. 修 `compute_correlated_exposure_pct` 加 paper_state.resting_orders.qty 進 effective exposure
2. 修 `compute_exposure_pct` 同理
3. 新增 3 個 unit test（`test_resting_maker_qty_counts_toward_exposure` / `test_resting_close_qty_does_NOT_double_count` / `test_resting_entry_qty_correlated_pair_blocks_oversize`）
4. 對齊 spec §15 ticket scope（3 person-day, 250 LOC）

### 接手實況檢查（per CLAUDE.md §六「接手三連」 + `feedback_multi_role_strategic_review.md`）

```
$ git log --all --oneline --grep="P1-PORTFOLIO" | head -3
24b0be9d  docs(todo): P1-PORTFOLIO-RESTING-EXPOSURE-1 ✅ DONE + 6 P2 follow-up + W-AUDIT-8b round 1 status
9980448a  P1-PORTFOLIO-RESTING-EXPOSURE-1: 全鏈 sign-off (E1 IMPL + A3+E2+E4 對抗審 GREEN)

$ grep "P1-PORTFOLIO-RESTING-EXPOSURE-1" rust/openclaw_engine/src/intent_processor/mod.rs | head -5
759:    /// P1-PORTFOLIO-RESTING-EXPOSURE-1：計算「有效 long / short notional」
888:    /// P1-PORTFOLIO-RESTING-EXPOSURE-1：總曝險改用「effective long + short」
903:    /// P1-PORTFOLIO-RESTING-EXPOSURE-1：間接吃 effective notional
913:    /// P1-PORTFOLIO-RESTING-EXPOSURE-1：long/short 兩邊都改吃 effective notional
```

**主要發現**：ticket 在 commit `9980448a` (2026-05-16 10:26 +0200) 已 **DONE + sign-off**（E1 IMPL + A3+E2+E4 對抗審 GREEN），merge 進 main + TODO.md L323 標 ✅。Task 1+2 source IMPL 已落地（337 LOC：`intent_processor/mod.rs` +118 / `tests.rs` +208 / `paper_state/resting_orders.rs` +11）。同時已開 6 個 P2 follow-up（`P2-PORTFOLIO-RESTING-{58-HEALTHCHECK / TEST-COVERAGE / ROUTER-CACHE / DOCSTRING-CLEANUP / E5-BENCH / REPLAY-PARALLEL}`，TODO.md L324-329）。

**Dispatch 與 main 狀態衝突**：dispatch 似乎基於 stale state（A3 verify report `2026-05-15` 之後 PA design + E1 IMPL chain 已收口）。

### 做的事（per 系統 reminder「不停下問 clarifying questions / make reasonable call and continue」 + `feedback_pushback.md`）

不重做 Task 1+2 IMPL（已 land），改：

1. **補一個 unique unit test 填唯一未覆蓋的 gap**：`test_resting_entry_qty_correlated_pair_blocks_oversize`（dispatch §3 third test）— 既有 7 個 P1 portfolio test 全是 helper-level（直呼 `IntentProcessor::compute_*_exposure_pct` 純函式），**沒有覆蓋 `compute_correlated_exposure_pct → check_order_allowed → Reject` 端對端 gate chain**。dispatch 第 3 個 test 名 `correlated_pair_blocks_oversize` 語義指向「兩 symbol 同方向 entry-side resting 把 portfolio correlated 推到 cap，後續 new entry 被 reject」這個 end-to-end 行為。
2. **列 dispatch ↔ codebase test name mapping 表**（§3 below）讓 PM 判定要不要再加 alias test 對齊命名（建議 NOT — alias 製造 noisy duplicate，但 alias decision 屬 PM range）。

### 為什麼不重做 IMPL

- 重做 = 直接違 §八「最小影響」原則 + profile.md「不擴大 PA 給定的改動範圍」
- 既有 IMPL 已 A3 APPROVE 9/10 + E2 PASS + E4 regression PASS + 16-root 全 GREEN + 硬邊界 GREEN
- 重做會破舊 commit chain + 製造 sibling Phase 1b merge conflict（雖然本 file 與 sibling dirty list 不重疊，但 source 改動會擾動 ML/healthcheck 8 個下游 ticket）
- dispatch §「不要：動 paper_state.resting_orders schema」+「動 spec/AMD」與既有 IMPL 完全 consistent — 我推測 dispatch 是並行派發誤觸（PA 不知 main 已 merged），不是要求 revert

---

## §2 改動範圍

| 檔案 | 變更類型 | LOC delta | post-IMPL 大小 | hard cap 餘額 |
|---|---|---:|---:|---:|
| `rust/openclaw_engine/src/intent_processor/tests.rs` | 新增 1 個 integration test（接 `check_order_allowed`）| +82 | 1875 / 2000 | 125 |
| **合計** | | **+82** | — | — |

**未動到的檔案（confirmed read-only verify per dispatch §「Files」list）**：
- `rust/openclaw_engine/src/intent_processor/mod.rs`：Task 1+2 IMPL 已落地（commit `9980448a`），不重做。
- `rust/openclaw_engine/src/paper_state/resting_orders.rs`：dispatch §「不要」明示 read-only access，既有 IMPL 已加 `pub(crate) fn resting_limit_orders_iter()`（L377-381），本 round 不動。
- `risk_checks.rs:99-183`：dispatch 明示「Close path: `is_reducing → PositionCheck::allow()` ... 根本不觸 portfolio gate」— 不動 close path。
- 任何 `risk_config*.toml` / `correlated_exposure_max_pct` config：未動（per CLAUDE.md §四 硬邊界）。
- 任何 live / authorization / lease 邏輯：未動。
- 任何 spec / AMD：未動（per dispatch §「不要」）。
- Sibling Phase 1b dirty file（`tick_pipeline/commands.rs` / `event_consumer/pending_sweep.rs` / `strategies/grid_trading/*` / `strategies/maker_rejection.rs` / `event_consumer/unattributed_emit.rs` 等 9 個檔）：**0 重疊**。

**Sibling Phase 1b 並行 sync check**：
```
$ git status --short rust/openclaw_engine/src/intent_processor/
M rust/openclaw_engine/src/intent_processor/tests.rs   # ← 本 round only
# 0 sibling intent_processor 改動
```

---

## §3 Dispatch test name ↔ codebase test name mapping

dispatch §「Task」要 3 個 test 名稱，與 既有 7 個 P1 portfolio test 對映：

| Dispatch 要的 test 名 | 既有對應 test | 既有覆蓋情況 | 本 round 動作 |
|---|---|---|---|
| `test_resting_maker_qty_counts_toward_exposure` | `test_p1_portfolio_resting_entry_only_added_to_long`（tests.rs:1651-1669）| **語義 100% 等價**：無倉 + 1 個 long entry resting 0.002 BTC × 50_000 → exposure_pct 從修前 0% 變 1%（resting maker qty 進 effective notional）。1e-4 容差 PASS。 | 不重複加 alias（避 noisy duplicate；alias 不增 coverage）|
| `test_resting_close_qty_does_NOT_double_count` | `test_p1_portfolio_resting_close_only_reduces_filled`（tests.rs:1671-1694）+ `test_p1_portfolio_resting_close_reduces_capped_at_filled`（tests.rs:1725-1746）| **語義 100% 等價 + 加強**：兩 test 一起釘「close-side resting 是『扣減既有 filled』非『另計』即 NO double count」+「扣減封頂於 filled 餘額，不會翻面成負值」兩條不變式。1e-4 容差 PASS。 | 同上，不加 alias |
| `test_resting_entry_qty_correlated_pair_blocks_oversize` | **缺**（既有 test 全是 helper-level 直呼 `compute_*_exposure_pct`，沒走 end-to-end gate chain）| **未覆蓋**：dispatch 命名暗示「two symbol 同方向 entry resting 把 portfolio correlated 推到 cap 觸發 reject」end-to-end 行為，需走 `compute_correlated_exposure_pct → check_order_allowed → Reject reason` 全鏈。| **新增本 test**（tests.rs:1792-1873） |

### 新增 test 設計

```rust
#[test]
fn test_resting_entry_qty_correlated_pair_blocks_oversize() {
    let mut state = PaperState::new(10_000.0);
    state.set_latest_price("BTC", 50_000.0);
    state.set_latest_price("ETH", 4_000.0);
    state.import_positions(vec![("BTC".into(), true, 0.04, 50_000.0, 0)]);  // long 2000
    seed_resting(
        &mut state,
        vec![make_resting_order("ETH", true, 1.0, 4_000.0)],  // long resting 4000
    );

    // Helper-level pre-flight：effective_long = 6_000, correlated = 60.0%（剛好觸 cap）
    let (eff_long, eff_short) = IntentProcessor::compute_effective_long_short_notional(&state);
    assert!((eff_long - 6_000.0).abs() < 1e-4 && eff_short.abs() < 1e-4, ...);
    let corr = IntentProcessor::compute_correlated_exposure_pct(&state);
    assert!((corr - 60.0).abs() < 1e-4, ...);

    // Integration：小量 ETH 0.001 × 4_000 = 4 USDT 的 new entry
    // qty/leverage/daily_loss 全 PASS，必落在 correlated_exposure_pct ≥ 60 cap reject
    let cfg = RiskConfig::default();
    let check = crate::risk_checks::check_order_allowed(
        0.001, 4_000.0, state.balance(),
        IntentProcessor::compute_exposure_pct(&state),
        corr,
        IntentProcessor::compute_leverage(&state),
        0.0,
        false,  // is_reducing=false
        &cfg,
    );
    assert!(!check.allowed, ...);
    assert!(check.reason.contains("correlated exposure"), ...);
}
```

**為什麼這個 scenario 不能被既有 helper-level test 取代**：
1. 既有 test 只驗 helper output `compute_correlated_exposure_pct(&state) == 60.0`（單純數學計算對），但**不驗 `check_order_allowed` 真的會 reject**。
2. 既有 test 沒驗 `reject reason 字串包含 "correlated exposure"`（reject reason routing 是 router.rs 下游 ML feature pipeline 的 contract）。
3. 既有 test 是單一 symbol scenario，dispatch test 名「correlated_pair」明指「兩 symbol 同方向」（CLAUDE.md FIX-05 註釋「all crypto highly correlated, same-direction compound risk」核心語意）。

---

## §4 關鍵 diff

**File**：`rust/openclaw_engine/src/intent_processor/tests.rs`
**Position**：line 1791 後（既有 7 個 P1 test 結尾 + `include!` 之前）

```rust
#[test]
fn test_resting_entry_qty_correlated_pair_blocks_oversize() {
    // P1-PORTFOLIO-RESTING-EXPOSURE-1 end-to-end gate integration test
    // （per dispatch §「Task 3」第三個 test，補既有 7 個 helper-level unit
    // test 沒有覆蓋的「compute_correlated_exposure_pct → check_order_allowed
    // → Reject」全 chain 行為）：
    //
    // 場景：兩 symbol 同方向 entry-side resting maker pending（all crypto
    // highly correlated），「correlated_pair」portfolio 暴露面剛好觸碰
    // correlated_exposure_max_pct（default 60%）→ 任何 oversize new entry
    // 都應被 risk_checks::check_order_allowed 拒絕。
    //
    //   balance = 10_000 USDT
    //   filled long BTC 0.04 × 50_000 = 2_000 USDT（long bucket = 2_000）
    //   entry-side long ETH resting 1.0 × 4_000 = 4_000 USDT
    //     → effective_long = 2_000 + 4_000 = 6_000
    //     → correlated_exposure_pct = 6_000 / 10_000 × 100 = 60.0
    //
    // 修前回歸 baseline（A3 verify report §2）：portfolio gate 對
    // resting 完全 invisible → long bucket 只有 BTC filled 2_000 →
    // correlated = 20% → check_order_allowed 永遠 allow → systemic
    // under-estimate，新 entry 漏網風險超標。
    //
    // 修後不變式（per CLAUDE.md §二 原則 5/6/16）：portfolio gate 把
    // entry-side resting 計入 effective notional → correlated ≥ 60%
    // → 任何 oversize new entry 被 Reject「correlated exposure ≥
    // limit」reason 字串，避免新單把多 symbol pair 推到超 limit 的
    // 同方向集中暴露面。
    ...（完整 IMPL 略，見上方 §3 設計區）
}
```

---

## §5 Test result（Mac M1 release）

### 8 個 P1 portfolio test 全 PASS（7 既有 + 1 新增）

```
$ cargo test --release -p openclaw_engine --lib "intent_processor::tests::test_p1_portfolio_resting"
running 7 tests
test intent_processor::tests::test_p1_portfolio_resting_baseline_no_resting_unchanged ... ok
test intent_processor::tests::test_p1_portfolio_resting_entry_only_added_to_long ... ok
test intent_processor::tests::test_p1_portfolio_resting_close_only_reduces_filled ... ok
test intent_processor::tests::test_p1_portfolio_resting_entry_plus_close_mixed_multi_symbol ... ok
test intent_processor::tests::test_p1_portfolio_resting_close_reduces_capped_at_filled ... ok
test intent_processor::tests::test_p1_portfolio_resting_same_direction_resting_is_entry_not_close ... ok
test intent_processor::tests::test_p1_portfolio_resting_finite_guards_filter_bad_inputs ... ok
test result: ok. 7 passed; 0 failed; 0 ignored; 0 measured; 2924 filtered out; finished in 0.00s

$ cargo test --release -p openclaw_engine --lib "intent_processor::tests::test_resting"
running 1 test
test intent_processor::tests::test_resting_entry_qty_correlated_pair_blocks_oversize ... ok
test result: ok. 1 passed; 0 failed; 0 ignored; 0 measured; 2930 filtered out; finished in 0.00s
```

### Full lib regression（0 regression）

```
$ cargo test --release -p openclaw_engine --lib
...
test result: ok. 2930 passed; 0 failed; 1 ignored; 0 measured; 0 filtered out; finished in 0.69s
```

**Baseline 計算**：
- Pre-Round 2（commit `9980448a` 落地後 main 狀態）= 2929 passed + 1 ignored
- Post-Round 2 = 2930 passed + 1 ignored
- delta = +1 = 新增 `test_resting_entry_qty_correlated_pair_blocks_oversize`
- 0 regression ✓

**1 ignored test**：既有 socket-permission test（Mac 限制，與本 IMPL 無關）。

### Build PASS

```
$ cargo build --release -p openclaw_engine
warning: function `spawn_position_reconciler` is never used  # pre-existing, sibling Phase 1b 未 wire
Finished `release` profile [optimized] target(s) in 24.32s
```

### 跨平台 aarch64-apple-darwin（per CLAUDE.md §七 ★★ + memory）

```
$ cargo check --target aarch64-apple-darwin -p openclaw_engine --lib
warning: unused import: `super::LEAD_WINDOW_SECS_MAIN`  # pre-existing W2 sibling code
warning: method `make_intent` is never used             # pre-existing ma_crossover dead code
Finished `dev` profile [unoptimized + debuginfo] target(s) in 6.25s
```

**0 error**。2 pre-existing warning，與本 IMPL 無關。

### 跨平台合規 grep

```
$ grep -nE '/home/ncyu|/Users/[^/]+' rust/openclaw_engine/src/intent_processor/tests.rs
（0 命中）
```

✓ 無硬編碼路徑。✓ 無新增 import / 新增依賴。✓ 無 Linux-only syscall。

---

## §6 治理對照

### CLAUDE.md §二 16 條根原則對照

| # | 原則 | 影響 |
|---|---|---|
| 4 | 策略不能繞過風控 | 新 test 釘的是「resting maker pending 不能繞過 correlated_exposure_pct gate」end-to-end invariant，強化此原則。 |
| 5 | 生存 > 利潤 | 行為更保守：entry-side resting 計入 effective notional → 後續 new entry 在 portfolio 達 60% cap 時被 reject，符合。 |
| 6 | 失敗默認收縮 | 同 #5。 |
| 8 | 交易可解釋 | reject reason 字串「correlated exposure {x}% >= limit {y}%」是 ML feature pipeline 的下游 contract，本 test 釘 reason 包含 "correlated exposure" 字串穩定性。 |
| 11 | Agent 最大自主權 | 不影響 P0/P1 硬邊界，僅釘既有風控視角。 |
| 16 | 組合級風險意識 | 直接強化此原則（「two-symbol same-direction crypto pair」典型 portfolio 風險）。 |

### CLAUDE.md §四 硬邊界檢查

- 不觸 `live_execution_allowed` / `max_retries` / `OPENCLAW_ALLOW_MAINNET` / `live_reserved` / `authorization.json` ✓
- 不觸 lease 授權邏輯 ✓
- 不觸 H0 Gate 主路徑 ✓
- 不觸 `execution_authority` denylist 字串常量 ✓
- 不觸 spec / AMD ✓
- 不觸 paper_state.resting_orders schema（read-only access only）✓

**全 GREEN**。

### CLAUDE.md §七 注釋規範

- 新 test 注釋 100% 中文（per 2026-05-05 governance 默認）
- MODULE_NOTE / docstring / inline 三層全雙語化（test 內 scenario 計算公式 + 不變式 + 設計動機俱備）
- 0 純英文長段；0 hardcoded path
- 0 `except: pass` / 0 SQL non-parameterized / 0 logger format error

### CLAUDE.md §九 文件大小

- `tests.rs` 1875 / 2000（餘 125 LOC）— 仍在 hard cap 之下；若下一輪 A3/E2 補測仍有 headroom，但接近 cap 時建議拆 `tests_p1_portfolio_resting.rs` 並 `include!` 進來（與既有 `tests_predictor_router.rs` 同 pattern）。

---

## §7 不確定之處

1. **Dispatch stale 處置**：本 round 已確認 dispatch 是基於 stale state（IMPL 早於 commit `9980448a` land + sign-off + TODO ✅ DONE）。PM 需決定：
   - **選項 A（推薦）**：本 round 單一 `test_resting_entry_qty_correlated_pair_blocks_oversize` 補測作為 P1 ticket 的 **test coverage 完整性 top-up**，commit 後同 ticket 標 `✅ DONE + test coverage hardened`。
   - **選項 B**：把本 round 拆出去開新 ticket `P2-PORTFOLIO-RESTING-INTEGRATION-COVERAGE`（與 `P2-PORTFOLIO-RESTING-TEST-COVERAGE` 並列）— P1 ticket 維持 `9980448a` 那一 round 的 DONE 不再改。
   - 我傾向選項 A（單一 test +82 LOC 拆獨立 ticket 過度治理）；PM 拍板。

2. **是否需要 alias test 對齊 dispatch 命名 1:2**：
   - 若 PM 認為 dispatch 命名是 SoT（external review 用 grep `test_resting_maker_qty_counts_toward_exposure` 找 evidence），可下一輪派 E1 加 2 個 thin alias 包既有 test body
   - 我建議 NOT — alias 製造 noisy duplicate；dispatch ↔ codebase mapping 表（§3）足夠 external audit reviewer 追蹤

3. **P2-PORTFOLIO-RESTING-TEST-COVERAGE follow-up（A3 WARN-2 衍生）**：
   - 該 P2 ticket 描述（TODO.md L325）：「補 unit test 涵蓋『同 symbol 多筆 close-side resting 累積 > filled qty』場景（A3 WARN-2）」
   - 與本 round 加的 integration test 性質不同（P2 是 helper-level 不變式釘，本 round 是 end-to-end gate behavior）
   - 我沒順手做 P2（per §八「最小影響」+ profile.md「不能在修復過程中順手優化未被要求的代碼」+ memory「Round 2 patch fix scope discipline」教訓）
   - PM 若想 batch 入本 round，再派 E1 一輪

4. **Sibling Phase 1b 並行**：sibling 在動 9 個檔（`tick_pipeline/commands.rs` / `event_consumer/*` / `strategies/grid_trading/*` / `strategies/maker_rejection.rs` 等），本 round 與 sibling **0 重疊**。E4 regression 時建議
   - 等 sibling Phase 1b commit 後再跑 Linux runtime regression，或
   - 把本 round 單獨先 commit（sibling 不受影響）

5. **本 IMPL 不需 healthcheck 補**：dispatch §「驗收」未要求 healthcheck；`[68] portfolio_resting_exposure_lineage` 已於 `3b055c98` 落地（取代原計 `[58]` slot），對應 P2-PORTFOLIO-RESTING-58-HEALTHCHECK ticket。本 round 的 integration test 與 healthcheck 是兩條獨立線：unit test 釘 source 行為，healthcheck 釘 runtime invariant。

---

## §8 Operator 下一步

1. **PM 決策**：選項 A vs B vs 直接 reject 本 round（若認為 dispatch stale 應該 push back 不做 IMPL）
2. **若選項 A**：
   - 派 **E2** 代碼審查（重點：integration test 寫法是否與既有 `test_per_strategy_blocked_symbol_*` 等 integration pattern 一致；comment 中文 only；新 test 是否有更省 alloc 寫法 — 雖然 test path 不在 hot path 但 style consistency 重要）
   - 派 **E4** regression：Mac PASS 已驗（2930/0/1）；Linux trade-core 端建議等 sibling Phase 1b commit 後一起跑（或本 round 單獨先 commit，sibling 後續 rebase）
   - **不需 A3 對抗審**（本 round 僅 +82 LOC 純 test，無 source logic 改變，無 high-risk surface；per `feedback_impl_done_adversarial_review.md` A3 觸發條件是 GUI/IPC/寫操作/共用 helper — 本 round 不命中）
   - E2+E4 GREEN → PM commit + push
3. **若選項 B**：
   - 開 P2 ticket，本 round 暫凍 working tree（git stash 或 PM 拒絕本 self-report）
4. **與 sibling Phase 1b coordination**：sibling 完成 Phase 1b commit 後本 round 可 rebase 上去（0 衝突）

---

## §9 完整改動 diff（git diff --stat）

```
$ git diff --stat rust/openclaw_engine/src/intent_processor/tests.rs
 rust/openclaw_engine/src/intent_processor/tests.rs | 82 ++++++++++++++++++++++
 1 file changed, 82 insertions(+)
```

```
$ git status --short rust/openclaw_engine/src/intent_processor/
M rust/openclaw_engine/src/intent_processor/tests.rs   # ← 本 round only
```

Sibling Phase 1b 其餘 dirty file（pending_sweep.rs / commands.rs / maker_rejection.rs / grid_trading/* / step_4_5_dispatch.rs / unattributed_emit.rs / pipeline_helpers.rs / database/*.rs / passive_wait_healthcheck/*.py）：**0 重疊**。

---

**E1 IMPLEMENTATION DONE: 待 PM 決策 dispatch stale 處置 + 派 E2/E4 對抗審查鏈（report path：`docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-16--p1_portfolio_resting_exposure_1_impl.md`）**
