# E1 IMPL DONE — P1-2 + P2-1 bb_breakout W7-3 + W7-2 propagation (paired wave)

**Date**: 2026-05-11
**Agent**: E1
**Spec source**: PA W7-4 5-strategy systemic position sync audit (`srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--w7_4_5_strategy_position_sync_systemic_audit.md`) §3 P1-2 + P2-1
**Mirror references**:
- P1-2 W7-3 Option B → ma_crossover (`b42731f6`, `srv/rust/openclaw_engine/src/strategies/ma_crossover/strategy_impl.rs:55-91`) + bb_reversion P1-1 propagation (`df0e2269`, `srv/rust/openclaw_engine/src/strategies/bb_reversion/mod.rs:343-424`)
- P2-1 W7-2 Option A → ma_crossover (`22efd9de`, `srv/rust/openclaw_engine/src/strategies/ma_crossover/strategy_impl.rs:253-266`)
- Tests pattern → ma_crossover/tests.rs:678-1006 (W7-3 4-case + W7-2 4-case) + bb_reversion/tests.rs:1252-1382 (P1-1 mirror)
**Branch**: main (staged, NOT committed — pending E2 + A3 adversarial review per CLAUDE.md §八 / `feedback_impl_done_adversarial_review.md`)
**Repo HEAD pre-staging**: `df0e2269` (synced with `origin/main`)

---

## §1 任務摘要 / Task summary

W7-4 5-策略 systemic audit §3 揭露 bb_breakout 缺兩 W7 fix（gap 比 bb_reversion 大）：

- **P1-2** (~35 LOC IMPL): on_rejection W7-3 Option B 1-tick defense missing
- **P2-1** (~30 LOC IMPL): on_tick entry path Option A query missing（完全沒查 ctx.position_state）

PA recommendation §3：「pair P1-2 + P2-1 in same wave」（避免 entry-only 或 reject-only 半套；bb_breakout 需兩 fix 同時才達 ma_crossover/bb_reversion parity）。

bb_breakout 6 concentric gates（squeeze 45min + bandwidth>expansion + vol_ratio>threshold + Donchian breach Hard mode + persistence 60s + confluence score）使 hot loop 歷史 occurrence = 0；**W7 chain consistency 仍有架構價值**（防 future bug + alpha-source 6 strategy 擴充時 trait-level invariant 已就緒）。

範圍：mirror ma_crossover/bb_reversion W7-2/W7-3 pattern 到 `bb_breakout/mod.rs::on_rejection` + `on_tick`，~108 LOC IMPL（P1-2 += 78 / P2-1 += 30 重疊在 mod.rs 內）+ 7 unit tests，**0 跨策略連動**，不 deploy。

---

## §2 修改清單 / Files changed

| File | LOC delta | 變更類型 |
|---|---|---|
| `srv/rust/openclaw_engine/src/strategies/bb_breakout/mod.rs` | +98 / -20 | `on_rejection` 加 W7-3 Option B branch（preserves oi_buffer per EDGE-P2-2 FUP）+ `on_tick` None 分支起點加 W7-2 Option A query；雙語注釋 |
| `srv/rust/openclaw_engine/src/strategies/bb_breakout/tests.rs` | +301 / 0 | 4 W7-3 + 3 W7-2 unit tests + helper `make_paper_position_bbb` |
| **Total** | **+399 / -20** | 2 files (Rust only, 0 Python / 0 SQL / 0 schema) |

LOC sanity（CLAUDE.md §九 800 警告 / 2000 硬限）：
- mod.rs: 932 → **1010** (>800 警告 ⚠️ — pre-existing baseline 932 已超 800，本 PR 加 78 LOC 不破 2000 硬限；E5 在 N+2 backlog 可考慮 topical split)
- tests.rs: 1250 → **1551** (>800 警告 ⚠️ — 同 mod.rs，pre-existing 已超；考慮 N+2 拆 `tests_w7.rs` 或併入 `tests_oi.rs`)

兩檔皆 pre-existing 800-warn 違規，本 PR 屬必要 IMPL/test 路徑（P1-2 + P2-1 W7 chain consistency），無法在本 wave 範圍內 split（等於放大 scope）。建議 E5 在 Sprint N+2 評估 topical split：
- mod.rs：abstract `position_sync.rs` helper（W7-2 + W7-3 sync logic 移出，所有 strategies 共用）→ pair with W-AUDIT-8a 6 strategy 擴充
- tests.rs：拆 `tests_w7.rs`（已 1551 行屬 split candidate）

---

## §3 關鍵 diff / Key diff

### `bb_breakout/mod.rs::on_rejection` (替換整個函數)

**Before** (RC-04 + EDGE-P2-2 FUP only — 36 lines):

```rust
fn on_rejection(&mut self, intent: &OrderIntent, _reason: &str) {
    let sym = &intent.symbol;
    let live_oi_buffer = self.symbols.get(sym).map(|s| s.oi_buffer.clone()).unwrap_or_default();
    if let Some(prev) = self.prev_state.get(sym) {
        match prev {
            Some(prev_st) => {
                let mut restored = prev_st.clone();
                restored.oi_buffer = live_oi_buffer;
                self.symbols.insert(sym.to_string(), restored);
            }
            None => { ... }
        }
    }
    if let Some(&ts) = self.prev_last_trade_ms.get(sym) {
        if ts == 0 { self.cooldown.clear(sym); } else { self.cooldown.record_signal(sym, ts); }
    }
}
```

**After** (W7-3 Option B + 原 RC-04 fallback — 90 lines incl. comments):

```rust
fn on_rejection(&mut self, intent: &OrderIntent, reason: &str) {
    let sym = &intent.symbol;

    // W7-3 Option B：duplicate_position 識別 + 立即 sync self.symbols[sym].position。
    if reason.contains("duplicate_position") {
        let existing_is_long = if reason.contains("already LONG") {
            Some(true)
        } else if reason.contains("already SHORT") {
            Some(false)
        } else {
            None
        };

        if let Some(is_long) = existing_is_long {
            // 同步 paper_state 真實方向；下個 tick 進 Some(is_long) exit 分支。
            // 只動 position 欄位，不觸碰 oi_buffer / entry_price / trailing_stop /
            // squeeze_detected_ms（mirror W7-4 §3 P1-2 設計：保 EDGE-P2-2 FUP 既有契約）。
            let st = self.symbols.get_or_init(sym);
            st.position = Some(is_long);
            tracing::debug!(
                target: "strategy_position_sync",
                strategy = "bb_breakout",
                symbol = %sym,
                existing_is_long,
                "bb_breakout.on_rejection: duplicate_position 1-tick defense — \
                 synced PerSymbolState.position to paper_state direction (W7-3 Option B propagation)"
            );
            return;
        }
        tracing::warn!(
            target: "strategy_position_sync",
            strategy = "bb_breakout",
            symbol = %sym,
            reason = %reason,
            "bb_breakout.on_rejection: duplicate_position reason missing \
             'already LONG/SHORT' marker; falling back to RC-04 rollback"
        );
    }

    // 原 RC-04 rollback 完全不變（preserves oi_buffer per EDGE-P2-2 FUP；此處省略）。
    ...
}
```

### `bb_breakout/mod.rs::on_tick` (None 分支起點插入 W7-2 Option A)

**Before** (line 569-571 直接走 squeeze check):

```rust
match current_position {
    None => {
        // FIX-26: Check squeeze exists AND hasn't expired.
        ...
```

**After** (W7-2 Option A branch + 原邏輯):

```rust
match current_position {
    None => {
        // ── W7-2 Option A 治本（P2-1 propagation）── ...
        if let Some(existing) = ctx.position_state {
            let st = self.symbols.get_or_init(sym);
            st.position = Some(existing.is_long);
            tracing::debug!(
                target: "strategy_position_sync",
                strategy = "bb_breakout",
                symbol = %sym,
                existing_is_long = existing.is_long,
                "skip entry: ctx.position_state present (cross-strategy paper_state holding) — \
                 W7-2 Option A treats as cross-strategy desync, sync PerSymbolState.position and skip"
            );
            return vec![];
        }

        // FIX-26: Check squeeze exists AND hasn't expired. ...
```

**重要設計選擇**（per W7-4 §3 P2-1 trade-off）：W7-2 sync 只寫 `position` 欄位，**不**寫 `entry_price` / `trailing_stop` / `squeeze_detected_ms`。
- bb_breakout `entry_price` 是 ATR trailing_stop math 來源（`mod.rs:808-816`）
- 使用 cross-strategy `entry_price` 會 mis-calibrate trailing
- 留 `None` 直到下次 bb_breakout 自己開倉再寫
- `test_bbb_on_tick_entry_price_not_synced_from_paper_state` 顯式回歸此契約

### `bb_breakout/tests.rs` 新加 4 W7-3 + 3 W7-2 tests + helper

| Test | 場景 | 契約 |
|---|---|---|
| **P1-2 W7-3 #1** `test_bbb_on_rejection_duplicate_position_already_short_syncs_position` | reason "already SHORT" | `position = Some(false)` + **oi_buffer 不被觸碰** (EDGE-P2-2 FUP 契約) |
| **P1-2 W7-3 #2** `test_bbb_on_rejection_duplicate_position_already_long_syncs_position` | reason "already LONG" | `position = Some(true)` |
| **P1-2 W7-3 #3** `test_bbb_on_rejection_unknown_duplicate_format_fallback_to_rollback` | reason 含 "duplicate_position" 但無 "already LONG/SHORT" | fallback → prev_state rollback (entry_price/trailing_stop 還原) |
| **P1-2 W7-3 #4** `test_bbb_on_rejection_non_duplicate_position_runs_full_rollback` | reason "cost_gate" | 完整 RC-04 rollback：symbols.remove + cooldown clear |
| **P2-1 W7-2 #1** `test_bbb_on_tick_skips_entry_when_paper_state_has_other_strategy_position` | squeeze + breakout + ctx.position_state=Some(SHORT) | 0 actions + position sync false |
| **P2-1 W7-2 #2** `test_bbb_on_tick_proceeds_entry_when_paper_state_is_none` | ctx.position_state=None + valid breakout | 1 entry intent (baseline) |
| **P2-1 W7-2 #3** `test_bbb_on_tick_entry_price_not_synced_from_paper_state` | sync 後 entry_price 必 None | 防 mis-calibrate trailing_stop trade-off 契約 |

Helper `make_paper_position_bbb(symbol, is_long) -> PaperPosition`（mirror ma_crossover/tests.rs:836-854 的 `make_paper_position`）。

注：PA report §3 P1-2 列「2 unit tests」+ P2-1 列「3 unit tests」；E1 mirror ma_crossover 4-case 結構處理 P1-2（including unknown format fallback + non-duplicate full rollback），治理一致性 > spec 字面數。

---

## §4 治理對照 / Governance compliance

| CLAUDE.md 條文 | 對應 |
|---|---|
| §七 跨平台兼容 | `grep -nE '/home/ncyu\|/Users/ncyu' bb_breakout/{mod.rs,tests.rs}` 0 hits ✓ |
| §七 注釋默認中文 | 2026-05-05 governance change：新注釋僅中文（W7-3/W7-2/EDGE-P2-2 FUP 等技術名詞使用 ASCII）✓ |
| §七 SQL migration Guard A/B/C | N/A (0 SQL change) |
| §七 被動等待 TODO healthcheck | N/A (純 IMPL，無 passive wait) |
| §七 Sign-off git status clean | `git status --porcelain` 顯示 2 staged file 屬本 PR；scanner mod.rs + scanner_config.toml + panel_aggregator/ 為隔壁 session WIP（不接觸，per multi-session race protocol）✓ |
| §八 強制工作鏈 E1→E2→E4→QA→PM | E1 IMPL DONE → 等 E2 + A3 並行核驗 → E4 regression → PM commit ✓ |
| §九 LOC 800/2000 | mod.rs 1010 (>800 ⚠️ pre-existing) / tests.rs 1551 (>800 ⚠️ pre-existing)，<2000 硬限 ✓ — E5 N+2 backlog topical split candidate |
| §九 Singleton 登記 | N/A (0 新 singleton) |
| 硬約束 max_retries=0 / live_execution_allowed | N/A (策略內 logic only，無 risk_config / authority 改動) |
| `feedback_workflow_audit_chain.md` | E1 不 commit；stage only 等 E2/A3 → E4 → PM ✓ |
| `feedback_impl_done_adversarial_review.md` | 高風險 IMPL（共用 trait method override + ctx.position_state 注入路徑）強制派 A3+E2 並行核驗，E4 regression 不取代 ✓ |

### Pattern 一致性 vs ma_crossover / bb_reversion 對照

| 項目 | ma_crossover | bb_reversion | bb_breakout (本 PR) | 一致 |
|---|---|---|---|---|
| **W7-3 reason contract parse** | `contains("duplicate_position")` + `contains("already LONG/SHORT")` | 同 | 同 | ✓ |
| **W7-3 sync target field** | `self.positions.insert(sym, is_long)` (HashMap<String,bool>) | `self.positions.insert(sym, is_long)` (PerSymbolState<bool>) | `self.symbols.get_or_init(sym).position = Some(is_long)` (PerSymbolState<BbBreakoutPerSymbolState>) | ✓ (容器不同但語義一致) |
| **W7-3 cooldown 不 rollback** | 設計：保留 entry tick last_trade_ms 配合 cooldown gate | 同 | 同 | ✓ |
| **W7-3 fallback to RC-04** | unknown format → tracing::warn + RC-04 path | 同 | 同 | ✓ |
| **W7-3 oi_buffer 不觸碰** | N/A (ma_crossover 無 OI state) | N/A (bb_reversion 無 OI state) | **✓ 顯式只動 .position 欄位** (preserves EDGE-P2-2 FUP) | ✓ + 增強 |
| **W7-3 return early** | duplicate_position match → return | 同 | 同 | ✓ |
| **W7-3 log target** | (無 target) | `target: "strategy_position_sync"` (W7-4 §5 logging rec) | 同 bb_reversion (W7-4 §5 logging rec) | ✓ + 增強 (與 bb_reversion 對稱) |
| **W7-2 entry query** | `if let Some(existing) = ctx.position_state { ... return vec![]; }` | 同 | 同 | ✓ |
| **W7-2 entry_price NOT cross-sync** | (ma_crossover 不寫 entry_price) | (bb_reversion 不寫 entry_price) | **✓ 顯式設計：不寫 entry_price** (避 mis-calibrate trailing) | ✓ + 顯式 trade-off |

---

## §5 不確定之處 / Uncertainties

1. **LOC 800-warn 雙超**：mod.rs (932→1010) + tests.rs (1250→1551) 兩檔 pre-existing 已超 800，本 PR 加 W7 IMPL 加重但不破 2000 硬限。E2 抉擇：
   - **(A)** 接受 pre-existing baseline exception（CLAUDE.md §九 clause）+ N+2 backlog topical split ticket
   - **(B)** 本 PR 同時拆 `tests_w7.rs`（tests.rs 拆減約 200 LOC，主檔 ~1350 行）
   - 我傾向 **(A)** — split 等於放大 scope（W7-1/W7-3 W7-5 既有 test 也要動，跨 PR risk），N+2 W-AUDIT-8a 6 strategy 擴充時統一拆更乾淨；P1-1 (df0e2269) 也採用相同 (A) 路徑

2. **Helper 命名 `make_paper_position_bbb`**：tests.rs 新增 helper，與 ma_crossover/tests.rs:836 `make_paper_position` 命名相似但分離。E2 可決定：
   - **(A)** 保留各 strategy local helper（更清晰，避 helper drift）
   - **(B)** 抽 `strategies::common::test_helpers::make_paper_position` 共用
   - 我傾向 **(A)** — 與 W7-1/W7-3 既有 ma_crossover/bb_reversion 設計一致（都有 local helper）；統一抽到 common 屬 N+2 W5 (P3-deferred-trait-level helper) scope

3. **W7-2 sync 後 squeeze_detected_ms 保留**：test #3 顯式驗證 W7-2 sync 不觸碰 `squeeze_detected_ms`。設計上：squeeze 觀察狀態（squeeze 階段 line 506 寫的）跨 W7-2 sync 應保留，下次 bb_breakout 自己開倉時可繼續用。E2 可確認此決策對 squeeze regime semantics 是否正確（理論上 cross-strategy 開倉不影響 bb_breakout 對市場 squeeze 觀察，但屬 grey area）。

4. **bb_breakout PerSymbolState container API**：`self.symbols.get_or_init(sym)` 與 `self.symbols.get(sym)` 的 read-vs-write API 需注意—W7-2 在 None 分支起點呼 `get_or_init` 會建一筆空 entry（即使 ctx.position_state 是 None 但有 squeeze 仍 OK）。**測試已驗證**（test #2 baseline regression PASS）。E2 仍可審視 PerSymbolState 的 get_or_init 副作用是否與其他狀態欄位（特別 oi_buffer maintenance line 530）衝突。

---

## §6 測試結果 / Test results

```
$ cargo test --release -p openclaw_engine --lib strategies::bb_breakout::
running 83 tests
... (all 83 PASS)
test result: ok. 83 passed; 0 failed; 0 ignored; 0 measured; 2623 filtered out; finished in 0.00s
```

**7 新加 W7-3 + W7-2 tests 全 PASS**：
- P1-2 W7-3 #1-#4：`test_bbb_on_rejection_*` ✓ (4/4)
- P2-1 W7-2 #1-#3：`test_bbb_on_tick_*` ✓ (3/3)

**既有 76 tests 0 regression**：W7-5 on_fill+import (2 tests) / W7-3 既有 oi_buffer preserve (1 test) / FIX-26-DEADLOCK-1 + P1-11 (~12 tests) / Donchian mode (~7 tests) / OI confluence + FUP (~10 tests) / EDGE-P2-3 PostOnly + G7-09c BBO (~6 tests) / classic squeeze→breakout entry/exit (~10 tests) / W-AUDIT-6 5m timeframe (~5 tests) / params + validate (~10 tests) 全綠。

```
$ cargo test --release -p openclaw_engine --lib strategies::
test result: ok. 398 passed; 0 failed; 0 ignored; 0 measured; 2308 filtered out; finished in 0.01s
```

**全 strategies 398/398 PASS**（ma_crossover / bb_breakout / bb_reversion / grid_trading / funding_arb / common / confluence / maker_rejection / params / registry 全綠）— 證明 bb_breakout 改動 0 跨策略副作用。對比 P1-1 (df0e2269) 後的 391 → 398（+7 即本 PR 新加），數字一致。

```
$ cargo build --release -p openclaw_engine
Finished `release` profile [optimized] target(s) in 24.28s
```

**Build green** — 18 lib + 2 bin warnings 全 pre-existing dead_code（`reconciler_label_for_env` / `risk_level_from_u8` / `make_intent` 等），與本 PR 無關。

---

## §7 不確定之處的進一步說明 / Multi-session race compliance

當前 working tree 有 3 個非本 PR 變動（隔壁 session WIP）：
- `M rust/openclaw_engine/src/scanner/mod.rs`
- `M settings/risk_control_rules/scanner_config.toml`
- `?? rust/openclaw_engine/src/panel_aggregator/`

per CLAUDE.md §七 multi-session race protocol + `feedback_git_commit_only_for_metadoc.md`：
- E1 **不接觸** 隔壁 session uncommitted file
- 只 stage 本 PR 的 2 file（`bb_breakout/mod.rs` + `bb_breakout/tests.rs`）
- 不執行 commit + push（per `feedback_workflow_audit_chain.md`：E1 IMPL DONE 後等 E2 + A3 + E4 sign-off → PM 統一 commit）

`git diff --cached --stat` 顯示僅 2 PR file staged：
```
 .../src/strategies/bb_breakout/mod.rs              | 118 ++++++--
 .../src/strategies/bb_breakout/tests.rs            | 301 +++++++++++++++++++++
 2 files changed, 399 insertions(+), 20 deletions(-)
```

---

## §8 Operator 下一步 / Operator next steps

### 立即（D+0+1 dispatch 同 wave）

1. **PM 派 E2 + A3 並行核驗**（per `feedback_impl_done_adversarial_review.md`）：
   - **E2**：reason-string contract conformance (vs `rejection_coding.rs:147-152`) + pattern 一致性 vs ma_crossover/bb_reversion + borrow checker (PerSymbolState get_or_init 副作用) + LOC budget 抉擇 (mod.rs/tests.rs >800) + W7-2 entry_price not-cross-sync 設計 review
   - **A3**：cross-strategy desync race window 邏輯獨立核驗 + W7-2/W7-3 layered defense 契約 review + bb_breakout 6-gate interaction with W7-2 skip (是否影響 confluence/persistence state) + oi_buffer preservation 跨 W7-3 path 驗證
   - **E4**：regression suite verify (cargo test --release -p openclaw_engine 全 lib + 整合) + bb_breakout 整合測試 (G7-09c PostOnly + EDGE-P2-2 OI confluence path)
2. **PM commit** (E2 + A3 + E4 全 PASS 後)：建議 commit message：

```
E1(P1-2 + P2-1): bb_breakout W7-3 + W7-2 propagation paired wave

Mirror ma_crossover W7-3 (b42731f6) + W7-2 (22efd9de) chain to bb_breakout.
Closes both layers (entry-side trigger + reject-side defense) per W7-4
systemic audit §3 P1-2 + P2-1 paired-wave recommendation.

- bb_breakout/mod.rs::on_rejection (P1-2): parse duplicate_position reason,
  sync PerSymbolState.position to paper_state direction, skip RC-04 rollback.
  Preserves oi_buffer (EDGE-P2-2 FUP) + entry_price/trailing_stop/squeeze
  (avoid mis-calibration). Fallback to RC-04 on contract drift.
- bb_breakout/mod.rs::on_tick (P2-1): query ctx.position_state at entry
  None branch start, sync .position + skip when present. entry_price NOT
  cross-strategy synced (preserves trailing_stop math integrity per
  W7-4 §3 P2-1 trade-off).
- 7 unit tests mirror ma_crossover/tests.rs:678-1006 pattern (4 W7-3 +
  3 W7-2). Helper make_paper_position_bbb local to bb_breakout/tests.rs.
- tracing::debug target "strategy_position_sync" per W7-4 §5 logging rec
  (consistent with bb_reversion P1-1 propagation df0e2269)
- 0 cross-strategy side effect (398/398 strategies tests PASS; +7 new)

NOT a deploy — PM bundles with W7 chain restart_all --rebuild --keep-auth
in same Sprint N+1 D+0/D+1 deploy window. P1-2 + P2-1 close bb_breakout
to ma_crossover/bb_reversion parity (W7-4 §1 verdict A — full W7 coverage
becomes 3/5 strategies; grid_trading + funding_arb stay by-design A).

Refs: PA W7-4 audit (2026-05-10) §3 P1-2 + P2-1 | mirror b42731f6 W7-3
      + 22efd9de W7-2 + df0e2269 P1-1 bb_reversion W7-3 propagation
Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
```

### 中期（Sprint N+1 D+1+ / N+2）

3. **W7 chain consistency 收尾**（per W7-4 §3）：
   - W7-4 verdict 表 update：bb_breakout C → A（full coverage post P1-2 + P2-1）
   - PA 寫 D+1 follow-up note：W7 5-strategy systemic coverage 3/5 strategies A + 2/5 by-design A → systemic audit closure (no remaining P1/P2 from §3)
4. **ma_crossover logging target 統一**（P3，繼承 P1-1 unresolved）：對齊 bb_reversion + bb_breakout 的 `target: "strategy_position_sync"` field，補回 ma_crossover W7-3 IMPL；Sprint N+2 backlog
5. **LOC 800-warn pre-existing 處理**（E5 N+2 backlog）：
   - mod.rs：abstract `position_sync.rs` helper（W7-2 + W7-3 sync logic 移出，所有 strategies 共用）→ pair with W-AUDIT-8a 6 strategy 擴充
   - tests.rs：拆 `tests_w7.rs`（已 1551 行屬 split candidate）
6. **Trait-level invariant strengthening**（P3 RFC, Sprint N+3）：per W7-4 §4 Option 1（doc 強化）/ Option 2（compile-time helper `should_skip_for_cross_strategy_holding`）/ Option 3（trait-level 不可 override `should_proceed_to_entry`）

### 不要做 / Do NOT

- **不 deploy** 本 PR 單獨 — PM bundle W7-2 (`22efd9de`) + W7-5 (`bb7cb293`) + P1-1 bb_reversion (`df0e2269`) + 本 P1-2/P2-1 同 restart_all --rebuild --keep-auth window，避免多次 engine restart blast radius
- **不擴大** 範圍 — trait-level invariant + LOC topic split 留 N+2/N+3 follow-up
- **不 commit** by E1 — 等 E2 + A3 並行核驗 + E4 regression PASS 後 PM 統一 commit + push
- **不接觸** 隔壁 session WIP（scanner/* + panel_aggregator/）— per multi-session race protocol

---

E1 IMPLEMENTATION DONE: 待 E2 + A3 並行核驗（report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-11--p1_2_p2_1_bb_breakout_w7_propagation.md`）
