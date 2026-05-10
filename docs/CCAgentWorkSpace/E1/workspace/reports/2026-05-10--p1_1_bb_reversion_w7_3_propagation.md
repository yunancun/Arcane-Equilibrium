# E1 IMPL DONE — P1-1 bb_reversion on_rejection W7-3 Option B 1-tick defense propagation

**Date**: 2026-05-10
**Agent**: E1
**Spec source**: PA W7-4 5-strategy systemic position sync audit (`srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--w7_4_5_strategy_position_sync_systemic_audit.md`) §3 P1-1
**Mirror reference**: ma_crossover W7-3 Option B (commit `b42731f6`, `srv/rust/openclaw_engine/src/strategies/ma_crossover/strategy_impl.rs:55-91` + tests `:678-1006`)
**Sibling reference**: W7-5 on_fill+import_positions pattern (commit `bb7cb293`)
**Branch**: main (staged, NOT committed — pending E2 + A3 adversarial review per CLAUDE.md §八 / `feedback_impl_done_adversarial_review.md`)
**Repo HEAD pre-staging**: `4ac9c5b5` (synced with `origin/main`)

---

## §1 任務摘要 / Task summary

W7-4 5-策略 systemic position sync audit 揭露 W7 chain 是 **partial systemic fix**：

- W7-3 Option B (on_rejection duplicate_position 1-tick defense) 只在 ma_crossover land (`b42731f6`)
- bb_reversion **缺** W7-3 1-tick defense（W7-2 Option A + W7-5 on_fill/import 已 land，殘留 1-tick race window）
- bb_breakout 缺 W7-3 + W7-2（Sprint N+2 work，本 PR 不 touch）

P1-1 範圍：mirror ma_crossover W7-3 pattern 到 `bb_reversion/mod.rs::on_rejection`，~30 LOC IMPL + 4 unit tests，**0 跨策略連動**，不 deploy。

---

## §2 修改清單 / Files changed

| File | LOC delta | 變更類型 |
|---|---|---|
| `srv/rust/openclaw_engine/src/strategies/bb_reversion/mod.rs` | +61 / -3 | `on_rejection` 加 W7-3 Option B branch + 雙語注釋；`_reason` 取消前綴改 `reason` |
| `srv/rust/openclaw_engine/src/strategies/bb_reversion/tests.rs` | +132 / 0 | 4 W7-3 unit tests + helper `make_test_intent_w73` |
| **Total** | **+193 / -3** | 2 files (Rust only, 0 Python / 0 SQL / 0 schema) |

LOC sanity（CLAUDE.md §九 800 警告 / 2000 硬限）：
- mod.rs: 640 → **698** (< 800 警告 ✓)
- tests.rs: 1250 → **1382** (< 2000 硬限 ✓)

---

## §3 關鍵 diff / Key diff

### `bb_reversion/mod.rs::on_rejection` (替換整個函數)

**Before** (RC-04 only — 23 lines):

```rust
fn on_rejection(&mut self, intent: &OrderIntent, _reason: &str) {
    let sym = &intent.symbol;
    if let Some(prev) = self.prev_position.get(sym) {
        match prev {
            Some(b) => { self.positions.insert(sym.clone(), *b); }
            None => { self.positions.remove(sym); }
        }
    }
    if let Some(&ts) = self.prev_last_trade_ms.get(sym) {
        if ts == 0 {
            self.cooldown.clear(sym);
        } else {
            self.cooldown.record_signal(sym, ts);
        }
    }
}
```

**After** (W7-3 Option B + 原 RC-04 fallback — 80 lines incl. comments):

```rust
fn on_rejection(&mut self, intent: &OrderIntent, reason: &str) {
    let sym = &intent.symbol;

    // W7-3 Option B：duplicate_position 識別 + 立即 sync self.positions。
    if reason.contains("duplicate_position") {
        let existing_is_long = if reason.contains("already LONG") {
            Some(true)
        } else if reason.contains("already SHORT") {
            Some(false)
        } else {
            None
        };

        if let Some(is_long) = existing_is_long {
            self.positions.insert(sym.clone(), is_long);
            tracing::debug!(
                target: "strategy_position_sync",
                strategy = "bb_reversion",
                symbol = %sym,
                existing_is_long,
                "bb_reversion.on_rejection: duplicate_position 1-tick defense — \
                 synced self.positions to paper_state direction (W7-3 Option B propagation)"
            );
            return;
        }
        tracing::warn!(
            target: "strategy_position_sync",
            strategy = "bb_reversion",
            symbol = %sym,
            reason = %reason,
            "bb_reversion.on_rejection: duplicate_position reason missing \
             'already LONG/SHORT' marker; falling back to RC-04 rollback"
        );
    }

    // 原 RC-04 rollback 完全不變（此處省略，與 Before 相同）
    ...
}
```

### `bb_reversion/tests.rs` 新加 4 W7-3 tests + helper

| Test | 場景 | 契約 |
|---|---|---|
| `test_bbr_on_rejection_duplicate_position_already_short_syncs_position` | reason "already SHORT" | `self.positions[sym] = Some(false)` |
| `test_bbr_on_rejection_duplicate_position_already_long_syncs_position` | reason "already LONG" | `self.positions[sym] = Some(true)` |
| `test_bbr_on_rejection_unknown_duplicate_format_fallback_to_rollback` | reason 含 "duplicate_position" 但無 "already LONG/SHORT" | fallback → prev_position rollback (Some(true) 保留) |
| `test_bbr_on_rejection_non_duplicate_position_runs_full_rollback` | reason "cost_gate" | 完整 RC-04 rollback：positions remove + cooldown clear |

Helper `make_test_intent_w73(symbol, is_long) -> OrderIntent` 命名加 `_w73` 後綴避免與 W7-5 區段 `make_intent_bbr` drift。

注：PA report §3 P1-1 列「3 PASS case + 既有 regression」；E1 mirror ma_crossover 4-case 結構（including unknown format fallback + non-duplicate full rollback），治理一致性 > spec 字面。

---

## §4 治理對照 / Governance compliance

| CLAUDE.md 條文 | 對應 |
|---|---|
| §七 跨平台兼容 | `grep '/home/ncyu\|/Users/ncyu'` 0 hits ✓ |
| §七 注釋默認中文 | 2026-05-05 governance change：新注釋僅中文（W7-3 標記用 ASCII 名詞 "Option B" / "duplicate_position" 屬技術名詞）✓ |
| §七 SQL migration Guard A/B/C | N/A (0 SQL change) |
| §七 被動等待 TODO healthcheck | N/A (純 IMPL，無 passive wait) |
| §七 Sign-off git status clean | `git status --porcelain` 顯示 2 staged file 屬本 PR；1 untracked QC report 不屬本 scope ✓ |
| §八 強制工作鏈 E1→E2→E4→QA→PM | E1 IMPL DONE → 等 E2 + A3 並行核驗 → E4 regression → PM commit ✓ |
| §九 LOC 800/2000 | mod.rs 698 < 800 / tests.rs 1382 < 2000 ✓ |
| §九 Singleton 登記 | N/A (0 新 singleton) |
| 硬約束 max_retries=0 / live_execution_allowed | N/A (策略內 logic only，無 risk_config / authority 改動) |
| `feedback_workflow_audit_chain.md` | E1 不 commit；stage only 等 E2/A3 → E4 → PM ✓ |
| `feedback_impl_done_adversarial_review.md` | 高風險 IMPL（共用 trait method override）強制派 A3+E2 並行核驗，E4 regression 不取代 ✓ |

### Pattern 一致性 vs ma_crossover 對照

| 項目 | ma_crossover | bb_reversion (本 PR) | 一致 |
|---|---|---|---|
| reason contract parse | `contains("duplicate_position")` + `contains("already LONG/SHORT")` | 同 | ✓ |
| sync target field | `self.positions.insert(sym.clone(), is_long)` (HashMap<String, bool>) | `self.positions.insert(sym.clone(), is_long)` (PerSymbolState<bool>，pass-through API) | ✓ |
| cooldown 不 rollback | 設計：保留 entry tick last_trade_ms 配合 cooldown gate 多擋一輪 | 同 | ✓ |
| fallback to RC-04 | unknown format → tracing::warn + RC-04 path | 同 | ✓ |
| return early | duplicate_position match → return（不走 RC-04） | 同 | ✓ |
| log target | tracing::debug + symbol/existing_is_long | 加 `target: "strategy_position_sync"` 對齊 PA report §5 logging recommendation | ✓ + 增強 |
| log strategy field | (ma_crossover 無；策略名隱含於 module path) | `strategy = "bb_reversion"` field（W7-4 logging recommendation） | bb_reversion 略增強，便於 grep `target: strategy_position_sync` |

---

## §5 不確定之處 / Uncertainties

1. **Reason 字串 logging target**：本 PR 加了 `tracing::debug!(target: "strategy_position_sync", ...)` 對齊 PA report §5 logging recommendation（"Add `tracing::debug!` with target `strategy_position_sync` to all 5 strategies' on_rejection duplicate_position branch"）。**ma_crossover 既有 W7-3 IMPL 沒這個 target**（commit `b42731f6` 只用 `tracing::debug!` 無 target）。E2 抉擇：
   - **(A)** 接受 bb_reversion 增強 logging（PA recommendation 兌現），ma_crossover 留 follow-up Sprint N+2 P3 統一加 target
   - **(B)** 撤回 bb_reversion 的 target field，純 mirror ma_crossover 既有 pattern
   - 我傾向 **(A)** — PA §5 已 endorse + grep handle 對 future hot-loop forensics 有正面價值；trade-off 是 pattern 暫時不對稱（ma_crossover 待補）

2. **Helper 命名 `make_test_intent_w73`**：tests.rs 已有 W7-5 區段的 `make_intent_bbr` helper。為避免 helper drift / 兩個用途混淆，新加 `make_test_intent_w73`（顯式 W7-3 後綴）。E2 可決定：
   - **(A)** 保留兩個 helper（更清晰）
   - **(B)** 重構統一成單一 `make_intent_bbr_min`（更精簡）
   - 我傾向 **(A)** — W7-5 helper 帶 `order_type: "limit"` 對 W7-5 fill semantics 有意；W7-3 helper 用 `"market"` 對 reject path 中性。混用會讓 fill 測試誤用 market intent。

3. **Trait signature drift**：`Strategy::on_rejection(&mut self, _intent: &OrderIntent, _reason: &str)` trait default 用 underscore prefix；override 後 `intent: &OrderIntent, reason: &str`（無 prefix）正確（已使用兩個 param）。bb_reversion 之前也是 `intent: &OrderIntent, _reason: &str`（reason 未用），本 PR 改為 `reason: &str`（match ma_crossover）。**這 0 行為改動，純 lint compliance**。

4. **bb_breakout P1-2 + P2-1 不在本 scope**：明確按 prompt 排除，留 next dispatch 或 N+2。但 P1-2 spec 提到 "preserve oi_buffer per EDGE-P2-2 FUP"，這是 bb_breakout-specific 細節，bb_reversion 無對應狀態，本 PR 不需處理。

---

## §6 測試結果 / Test results

```
$ cargo test --release -p openclaw_engine --lib strategies::bb_reversion::
running 47 tests
... (all 47 PASS)
test result: ok. 47 passed; 0 failed; 0 ignored; 0 measured; 2652 filtered out; finished in 0.00s
```

**4 新加 W7-3 tests 全 PASS**：
- `test_bbr_on_rejection_duplicate_position_already_short_syncs_position` ✓
- `test_bbr_on_rejection_duplicate_position_already_long_syncs_position` ✓
- `test_bbr_on_rejection_unknown_duplicate_format_fallback_to_rollback` ✓
- `test_bbr_on_rejection_non_duplicate_position_runs_full_rollback` ✓

**既有 43 tests 0 regression**：W7-2 Option A (3 tests) / W7-5 on_fill+import (2 tests) / W-AUDIT-6d MA pair gate (10 tests) / G7-09c BBO PostOnly (4 tests) / Phase B Hurst (4 tests) / EDGE-P1-2 funding (5 tests) / param_ranges + validate (5 tests) / classic entry/exit/limit (10 tests) 全綠。

```
$ cargo test --release -p openclaw_engine --lib strategies::
test result: ok. 391 passed; 0 failed; 0 ignored; 0 measured; 2308 filtered out; finished in 0.01s
```

**全 strategies 391/391 PASS**（ma_crossover / bb_breakout / bb_reversion / grid_trading / funding_arb / common / confluence / maker_rejection / params / registry 全綠）— 證明 bb_reversion 改動 0 跨策略副作用。

```
$ cargo build --release -p openclaw_engine
Finished `release` profile [optimized] target(s) in 24.19s
```

**Build green** — 2 warning (`#[warn(dead_code)] reconciler_label_for_env / pre-existing` 與本 PR 無關)。

---

## §7 Operator 下一步 / Operator next steps

### 立即（D+0 dispatch 同 wave）

1. **PM 派 E2 + A3 並行核驗**（per `feedback_impl_done_adversarial_review.md`）：
   - **E2**：reason-string contract conformance（vs `rejection_coding.rs:147-152`）+ pattern 一致性 vs ma_crossover + borrow checker + LOC budget
   - **A3**：跨策略 desync race window 邏輯獨立核驗 + W7-2/W7-3 layered defense 契約 review
   - **E4**：regression suite verify (cargo test --release -p openclaw_engine 全 lib + 整合)
2. **PM commit** (E2 + A3 + E4 全 PASS 後)：建議 commit message：

```
E1(P1-1): bb_reversion W7-3 Option B 1-tick defense propagation

Mirror ma_crossover W7-3 (b42731f6) duplicate_position 1-tick defense
to bb_reversion.on_rejection. Closes residual 1-tick race window left
by W7-2 Option A entry path query (W7-4 systemic audit §3 P1-1).

- bb_reversion/mod.rs::on_rejection: parse duplicate_position reason,
  sync self.positions to paper_state direction, skip RC-04 rollback
  (preserves cooldown for second-tier hot loop defense)
- 4 unit tests mirror ma_crossover/tests.rs:678-810 pattern
- tracing::debug target "strategy_position_sync" per W7-4 §5 logging rec
- 0 cross-strategy side effect (391/391 strategies tests PASS)

NOT a deploy — PM bundles with W7 chain restart_all --rebuild --keep-auth
in same Sprint N+1 D+0 deploy window (W7-2 + W7-5 + this P1-1 land
together avoiding 3-restart blast radius).

Refs: PA W7-4 audit (2026-05-10) §3 P1-1 | mirror b42731f6 W7-3
Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
```

### 中期（Sprint N+1 D+0+1 / N+2）

3. **W7-3 Option B propagation 收尾**（per W7-4 §3）：
   - **P1-2**: bb_breakout `on_rejection` W7-3 1-tick defense (~35 LOC)
   - **P2-1**: bb_breakout `on_tick` entry path Option A query (~30 LOC)
   - 建議 N+2 W5 paired wave bundle（P1-2 + P2-1 同 commit，避免 entry-only 或 reject-only 半套）
4. **ma_crossover logging target 統一**（P3）：對齊本 PR 的 `target: "strategy_position_sync"` field，補回 ma_crossover W7-3 IMPL；Sprint N+2 backlog
5. **Trait-level invariant strengthening**（P3 RFC, Sprint N+3）：per W7-4 §4 Option 1（doc 強化）/ Option 2（compile-time helper `should_skip_for_cross_strategy_holding`）/ Option 3（trait-level 不可 override `should_proceed_to_entry`）

### 不要做 / Do NOT

- **不 deploy** 本 PR 單獨 — PM bundle W7-2 (`22efd9de`) + W7-5 (`bb7cb293`) + 本 P1-1 同 restart_all --rebuild --keep-auth window，避免 3 次 engine restart blast radius
- **不擴大** 範圍 — bb_breakout / trait-level invariant 留 follow-up
- **不 commit** by E1 — 等 E2 + A3 並行核驗 + E4 regression PASS 後 PM 統一 commit + push

---

E1 IMPLEMENTATION DONE: 待 E2 + A3 並行核驗（report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-10--p1_1_bb_reversion_w7_3_propagation.md`）
