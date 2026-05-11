# E1-B Report — P0 Option A-Lite：bb_reversion paper_state SSoT 重構

**日期**：2026-05-11
**Agent**：E1-B（Backend Developer）
**Task**：PA P0 Option A-Lite 之 E1-B（bb_reversion 完整 SSoT 改造）
**Spec**：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--p0_option_a_position_state_ssot_refactor.md` §3.2 #1 + §4.1 + §8.1 + §9
**Commit**：`6cdfe0dc` on branch `worktree-agent-ae33b896804323f52`

---

## 1. 任務摘要

22:08 May 10 watchdog Auto restart 引爆 cross-strategy mass scalp，bb_reversion 是 root carrier。Phase 0 hot-fix (commit 77a52796) 加 owner_strategy gate 止血。本次 E1-B 做完整 SSoT 改造：

- **移除** `self.positions: PerSymbolState<bool>` 與 `self.prev_position: HashMap<String, Option<bool>>` 兩個 field
- **重寫** `on_tick` entry/exit match：直接以 `ctx.position_state.filter(|p| p.owner_strategy == self.name())` 為 self 視角依據
- **完全清除** W7-2 Option A entry sync 區段（root trigger）+ W7-3 Option B on_rejection duplicate_position sync + W7-5 part 1+2 on_fill / import_positions sync
- **化簡** on_rejection 為純 cooldown rollback（保留 `prev_last_trade_ms` 哨兵語意）
- **移除** Phase 0 stop-bleed gate（owner_strategy match 後變多餘）
- **更新** ~52 tests（refactor 2 個 entry→exit 雙 tick test + 4 個 funding_rate test；刪除 9 個 W7-* sync 驗證 test；新增 6 個 P0 Option A-Lite acceptance test）

---

## 2. 修改清單

| 檔 | 改動 | 主要內容 |
|---|---|---|
| `rust/openclaw_engine/src/strategies/bb_reversion/mod.rs` | -229 / +65（net -164 LOC）| 移 `positions` + `prev_position` field；重寫 on_tick `owns_self` match；化簡 on_rejection；刪 Phase 0 gate；on_fill explicit no-op；import_positions 用 trait default |
| `rust/openclaw_engine/src/strategies/bb_reversion/tests.rs` | -348 / +201（net -147 LOC）| 刪 9 W7-* tests；新增 6 P0 acceptance tests；refactor 2 雙 tick exit tests；4 funding_rate tests 移 `s.positions.clear()` |
| `rust/openclaw_engine/src/strategies/bb_reversion/params.rs` | 不動 | PA spec 已預期 |

**合計**：2 檔，-577 / +266（net -311 LOC）。

---

## 3. 關鍵 diff（要點）

### 3.1 struct 欄位清理

```rust
// 移除
pub(crate) positions: PerSymbolState<bool>,
prev_position: HashMap<String, Option<bool>>,

// 保留（cooldown rollback 用，與 positions 解耦）
prev_last_trade_ms: HashMap<String, u64>,
```

### 3.2 on_tick match 重寫

```rust
// AFTER
let owns_self = ctx
    .position_state
    .filter(|p| p.owner_strategy == self.name())
    .map(|p| p.is_long);

match owns_self {
    Some(_is_long) => {
        // Exit — paper_state 確認本策略持倉
        if bb.percent_b >= self.exit_pctb_lower && bb.percent_b <= self.exit_pctb_upper {
            intents.push(StrategyAction::Close { /* ... */ });
            self.cooldown.record_signal(ctx.symbol, ctx.timestamp_ms);
        }
    }
    None if ctx.position_state.is_some() => {
        // cross-strategy 持倉 — skip 全路徑（entry + exit），杜絕 mass close
        tracing::debug!(strategy = "bb_reversion", ...);
        return intents;
    }
    None => {
        // Entry — 無人持倉，按既有 reversion 訊號邏輯
        // signal/persistence/ma_pair/confluence 邏輯保留
        // 移除 self.positions.insert eager mutation
    }
}
```

### 3.3 on_rejection 化簡

```rust
// AFTER — 純 cooldown rollback，無 W7-3 duplicate_position 解析
fn on_rejection(&mut self, intent: &OrderIntent, _reason: &str) {
    let sym = &intent.symbol;
    if let Some(&ts) = self.prev_last_trade_ms.get(sym) {
        if ts == 0 { self.cooldown.clear(sym); }
        else { self.cooldown.record_signal(sym, ts); }
    }
}
```

### 3.4 新 acceptance test

```rust
#[test]
fn bb_reversion_does_not_close_grid_position_on_pctb_zone() {
    let mut s = BbReversion::new();
    s.min_persistence_ms = 0;
    let pp = make_paper_position_bbr_with_owner("BTC", true, "grid_trading");
    let mut ctx = ctx_bb(0.5, 50.0, 0); // bb.percent_b 在 exit zone [0.2, 0.8] 內
    ctx.position_state = Some(&pp);

    let intents = s.on_tick(&ctx, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);

    let close_count = intents.iter().filter(|a| matches!(a, StrategyAction::Close { .. })).count();
    assert_eq!(close_count, 0, "bb_reversion 必不平 grid_trading 的倉");
    assert!(intents.is_empty(), "cross-strategy 持倉應 skip 全路徑");
}
```

---

## 4. 治理對照

- **CLAUDE.md §二 原則 4（策略不能繞過風控）/ 原則 6（失敗默認收縮）**：移除 W7-2 sync 後策略不再自行猜測 cross-strategy 倉位方向 → 從根源杜絕 mass close；cross-strategy 持倉時 strategy 主動 backoff（skip entry + skip exit），符合「失敗默認收縮」。
- **CLAUDE.md §七 注釋規範**（2026-05-05 governance change 默認中文）：本次新加注釋全中文，未動原中英對照塊。
- **CLAUDE.md §九 文件大小限制（800 警告 / 2000 硬上限）**：mod.rs 縮至約 543 LOC（< 800）；tests.rs 1235 LOC（< 2000）。
- **PA spec §3.2 #1 規定**：完整移除 self.positions field + W7-2 sync block + Phase 0 gate；保留 cooldown / persistence / ma_pair / confluence / exit_zone logic。
- **PA spec §9 grep 驗收**：`self\.positions\|prev_position` non-test scope = 0 hits ✓ / `PHASE-0-STOP-BLEED` = 0 hits ✓ / test count 2794 ≥ 2785 baseline ✓。
- **PA spec §5.3 acceptance test**：`bb_reversion_does_not_close_grid_position_on_pctb_zone` 已加入 ✓。

---

## 5. 不確定之處

1. **Multi-worktree race 風險**：本任務在 `worktree-agent-ae33b896804323f52` worktree 工作。sibling worktree（推測 E1-A 改 ma_crossover）曾把我的初版改動 stash 走（"E1-B bb_reversion leaked changes"），需 stash pop 恢復。E2 review 時請確認最終 commit `6cdfe0dc` 內容無漏。
2. **`AlphaSurface` import 警告**：tests.rs 內 import 沒清掉（與 mod.rs 維持一致），cargo 不報 warning。若 E5 後續優化建議清。
3. **Helper 抽 strategies/common 屬 E1-F scope**：本次內聯 `make_paper_position_bbr_with_owner` + `make_paper_position_bbr_for_self_exit` 兩個 helper 在 tests.rs；與 E1-D / E1-E 重複 pattern。PA §8.1 E1-F aggregator 處理抽出 reuse helper，E1-B 不擴張。
4. **Phase 0 commit 77a52796 已 deployed PID 1872218（per PA spec 背景說明）**：本次完整 SSoT 改造移除 Phase 0 gate；但 Phase 0 patch 已在 production，本 commit 的 `--rebuild` 部署會把 Phase 0 一併替換為 owner_strategy match。
5. **Multi-strategy E1 整合依賴**：sibling E1-A (ma_crossover) / E1-D (grid_trading) / E1-E (funding_arb) / E1-F (aggregator) 必須一起 merge 才能完整 build 整個 binary。E1-B 單獨 cargo test PASS (2794) 是因為我的 worktree 內 5 個策略只有 bb_reversion 被改，其他 ma_crossover/bb_breakout/grid_trading/funding_arb 仍是改造前 W7 family 結構（會跟其他並行 E1 改完後不一致）；PM merge 階段需處理 worktree 整合。

---

## 6. Operator 下一步

1. **E2 對 commit `6cdfe0dc` 進行 adversarial review**：重點驗 §9 spec：
   - exit gate owner_strategy 必查（match Some 分支必只在 owner=self 時進入）
   - 無 self.positions 殘留代碼（grep 全綠）
   - on_rejection 化簡正確（哨兵 0 → clear / non-zero → record_signal）
   - 新 acceptance test 覆蓋 cross-strategy skip + self-exit baseline
2. **E4 regression**：cargo test --release -p openclaw_engine --lib 重跑（baseline 2794），acceptance test `bb_reversion_does_not_close_grid_position_on_pctb_zone` 必 PASS。
3. **等其他 E1 完成（E1-A ma_crossover / E1-D grid_trading / E1-E funding_arb / E1-C bb_breakout）後 PM 處理 multi-worktree merge**。
4. **deploy 走 PA spec §8.3 Wave 3 atomic**：bb_reversion + ma_crossover atomic（changeset 最大）；先確認所有 worktree merge clean。

---

## 7. 驗證結果

| 項 | 結果 |
|---|---|
| `cargo build --release -p openclaw_engine --lib` | PASS (14.79s, 18 unrelated warnings) |
| `cargo test --release -p openclaw_engine --lib bb_reversion` | **46/46 PASS** |
| `cargo test --release -p openclaw_engine --lib` | **2794 PASS / 0 fail** |
| grep `\bself\.positions\b\|\bself\.prev_position\b` non-test | 0 hits |
| grep `PHASE-0-STOP-BLEED` | 0 hits |
| Commit | `6cdfe0dc` pushed to `worktree-agent-ae33b896804323f52` |

---

**E1 IMPLEMENTATION DONE: 待 E2 審查**
**Report path: srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-11--option_a_lite_e1_b_bb_reversion.md**
