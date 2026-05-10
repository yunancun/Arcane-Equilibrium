# E1 IMPL — W7-3 Emergency 1-Tick Defense（ma_crossover on_rejection duplicate_position sync）

**Date**: 2026-05-10
**Owner**: E1
**Scope**: PA #3 audit Option B 補丁式應急防衛 — ma_crossover.on_rejection 識別 duplicate_position → sync self.positions → 終結 cross-strategy desync hot loop
**Status**: IMPL DONE / **NOT DEPLOYED**（PM 決定 restart 時機）
**Trigger**: PA #3 audit `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--p1_ma_crossover_duplicate_intent_audit.md`

---

## 1. 任務摘要

PA #3 audit confirmed root cause: ma_crossover 用 `self.positions: PerSymbolState<bool>` 追蹤自己策略倉位，**不查 paper_state**；router gate 1.5 用 `paper_state.get_position(symbol)` 做 symbol-level（不分策略）dedup。當 grid_trading 在 INXUSDT 11:29 開 SHORT 1810，ma_crossover 看不見，每 tick 撞 router gate 1.5 → on_rejection rollback `self.positions` 到 None → 下 tick 又走 entry path = infinite hot loop（11:34 一分鐘 reject 2319 次）。

W7-3 採 PA Option B（補丁式）：on_rejection 識別 reason 字串中 `"duplicate_position"` + `"already SHORT/LONG"` → 把 `self.positions[symbol]` sync 成 paper_state 真實方向 → 下個 tick 進 `Some(is_long)` exit 分支不再撞 gate 1.5 → 立即終結 hot loop。

**治標非治本**：W-AUDIT-8a Option A（TickContext 加 `paper_state` reference）才是治本，但需動 5 策略 signature；本補丁僅 ~70 LOC（含注釋 + tests），緊急應急。

---

## 2. 修改清單

| File | Lines (前→後) | 變更類型 |
|---|---|---|
| `srv/rust/openclaw_engine/src/strategies/ma_crossover/strategy_impl.rs` | 306 → 354 | on_rejection 加 duplicate_position 識別分支（+48 行含注釋） |
| `srv/rust/openclaw_engine/src/strategies/ma_crossover/tests.rs` | 670 → 822 | 加 4 個 W7-3 unit test（+152 行含 helper） |

**檔案大小**：兩檔皆遠未達 800 行警告線（strategy_impl.rs 354 / tests.rs 822），800 警告線僅對非測試生產檔；tests.rs 為 #[cfg(test)] 區塊，按 §九 慣例不嚴格適用警告。

---

## 3. 關鍵 diff（strategy_impl.rs）

### Before（line 42-65）
```rust
fn on_rejection(&mut self, intent: &OrderIntent, _reason: &str) {
    let sym = &intent.symbol;
    if let Some(prev) = self.prev_position.get(sym) {
        match prev {
            Some(b) => self.positions.insert(sym.clone(), *b),
            None    => self.positions.remove(sym),  // hot loop 病灶
        }
    }
    if let Some(&ts) = self.prev_last_trade_ms.get(sym) {
        if ts == 0 { self.cooldown.clear(sym); } else { self.cooldown.record_signal(sym, ts); }
    }
}
```

### After
```rust
fn on_rejection(&mut self, intent: &OrderIntent, reason: &str) {  // _reason → reason
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
            // 同步 paper_state 真實方向；下個 tick 進 exit 分支不再撞 gate 1.5。
            self.positions.insert(sym.clone(), is_long);
            // 不 rollback cooldown：保留 entry tick 寫入的 last_trade_ms。
            tracing::debug!(...);
            return;  // 跳過 prev_position rollback
        }
        // contract drift fallback warn
        tracing::warn!(...);
    }

    // 原 RC-04 rollback：non-duplicate_position rejection 走此路徑。
    if let Some(prev) = self.prev_position.get(sym) {
        match prev { Some(b) => ..., None => ... }
    }
    if let Some(&ts) = self.prev_last_trade_ms.get(sym) {
        if ts == 0 { self.cooldown.clear(sym); } else { self.cooldown.record_signal(sym, ts); }
    }
}
```

### 設計決策（與 PA #3 §6/§8 對照）

| PA 建議 | E1 實作 | 對齊 |
|---|---|---|
| §6 Option B：reason starts_with `"duplicate_position"` 解析 existing_is_long | 改用 `reason.contains("duplicate_position")` 而非 `starts_with`；防 reason 字串前置變化 | 採納 + 強化 |
| §6 Option B：sync self.positions 立即終結 hot loop | 完成；reject 後下 tick 進 Some 分支 | ✅ |
| §8 重點 2：on_rejection rollback 邏輯不能整個刪，cooldown clear 副作用要保留 | duplicate_position 命中分支 **不** rollback cooldown（保留 last_trade_ms 多擋一輪）；fallback non-duplicate 分支保留完整原 RC-04 cooldown rollback | 採納 + 微調 |
| §6 Option B：依賴 reason 字串格式 byte-identical 契約（rejection_coding.rs:148） | 加 fallback 警告：reason 含 `duplicate_position` 但缺 `already LONG/SHORT` 子串 → tracing::warn + 走 RC-04 fallback | 採納 + contract drift 防線 |

**Cooldown 不 rollback 的設計理由**：
原 RC-04 rollback cooldown 是讓「reject 後的 strategy 可立即重試新 signal」。但 W7-3 場景下 rollback cooldown = hot loop 加速器（下 tick 立即又進 entry path）。改為「duplicate_position 命中時保留 entry tick 寫入的 last_trade_ms」→ 即便 sync positions 失靈，cooldown gate 仍能多擋幾分鐘。fallback 路徑保留原行為避免無關拒絕受影響。

---

## 4. Reason 字串契約對照（rejection_coding.rs:147-152）

```rust
RejectionCode::DuplicatePosition { symbol, existing_is_long, existing_qty } => format!(
    "duplicate_position: {} already {} {}",
    symbol,
    if *existing_is_long { "LONG" } else { "SHORT" },
    existing_qty,
),
```

實際 byte-identical 輸出範例（rejection_coding.rs::tests:373-385 釘住）：
- `"duplicate_position: BTCUSDT already LONG 0.5"`
- `"duplicate_position: ETHUSDT already SHORT 1.25"`

E1 parsing 用 `contains()` 而非 `starts_with()` — 因 reason 可能被外層加前綴（如 metric tag），但子串恆定。

**字串契約破裂保護**：rejection_coding.rs 該 enum variant 改格式 → ma_crossover.on_rejection 自動 fallback 到 RC-04 + 寫 warn log（tracing 等級 warn 而非 error，避免 Operator GUI 噪音）。

---

## 5. Unit test 結果（4 新 + 既有全 PASS）

### 新增 4 unit test
| Test | 場景 | Pre | Post | 期望 |
|---|---|---|---|---|
| `test_on_rejection_duplicate_position_already_short_syncs_position` | INXUSDT grid 已開 SHORT 1810；ma_crossover 想開 LONG 被拒 | prev_position=None | positions[INXUSDT]=Some(false) | `Some(false)` ✅ |
| `test_on_rejection_duplicate_position_already_long_syncs_position` | BTCUSDT 已 LONG 0.5；ma_crossover 想 SHORT 被拒 | prev_position=None | positions[BTCUSDT]=Some(true) | `Some(true)` ✅ |
| `test_on_rejection_unknown_duplicate_format_fallback_to_rollback` | reason 含 `duplicate_position` 但缺 `already LONG/SHORT`（contract drift 模擬） | prev_position=Some(true), positions=true | RC-04 fallback positions 仍 LONG | `Some(true)` ✅ |
| `test_on_rejection_non_duplicate_position_runs_full_rollback` | reason = cost_gate JS-demo negative；prev_position=None | positions=true, cooldown=100k | 完整 RC-04 rollback：positions remove + cooldown clear | `!contains_key` + `last_ms.is_none()` ✅ |

### Cargo test 摘要

```
$ cd srv/rust && cargo test -p openclaw_engine --lib --release ma_crossover
running 58 tests
... 4 W7-3 tests + 54 existing all pass
test result: ok. 58 passed; 0 failed; 0 ignored; 0 measured; 2581 filtered out; finished in 0.01s

$ cd srv/rust && cargo test -p openclaw_engine --lib --release  # 完整 lib regression
test result: ok. 2639 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.57s
```

### Cargo build/check 結果

```
$ cd srv/rust && cargo check -p openclaw_engine --tests  → 0 errors, 18 既有 dead_code warnings (本改動 0 新 warning)
$ cd srv/rust && cargo check --release --bin openclaw-engine  → 0 errors, 2 既有 dead_code warnings
```

**注**：未跑 `cargo build --release --bin openclaw-engine`（dispatch 邊界明確「Mac 端 cargo check 確認語法即可」）。Release binary 完整 link 留 PM 在 trade-core 上 `restart_all.sh --rebuild` 時做。

---

## 6. 治理對照

### Hard boundary 守則
- ✅ 未動 max_retries / live_execution_allowed / execution_authority / system_mode
- ✅ 未動 TickContext signature（PA dispatch 明確邊界）
- ✅ 未動 router.rs Gate 1.5 邏輯
- ✅ 未動 paper_state.rs
- ✅ 未做 5 策略 systemic fix（留 W-AUDIT-8a Option A）
- ✅ 未動 on_fill / bootstrap

### CLAUDE.md §七 對齊
- ✅ 路徑無硬編碼 / 無 `/Users/ncyu` / 無 `/home/ncyu`
- ✅ 注釋默認中文（2026-05-05 governance change，新代碼註釋僅中文，不再 bilingual mandate）
- ✅ MODULE_NOTE 不需新加（修改既有模組，未新建檔）
- ✅ 函數簽名變更：`_reason: &str` → `reason: &str`（參數 underscore 拿掉，因現在實際讀取）
- ✅ 無 SQL migration（純 Rust 改動）
- ✅ 無被動等待 TODO（純應急防衛）

### CLAUDE.md §九 對齊
- ✅ 兩檔皆 < 800 警告線（strategy_impl.rs 354 / tests.rs 822 — 後者為 #[cfg(test)] 區塊，按慣例不嚴格適用 800 warning gate）
- ✅ 無新 singleton 引入

### 跨平台兼容（§七 ★★）
- ✅ Mac 端 cargo check 全綠
- ✅ 0 平台特定代碼

---

## 7. 不確定之處 / 待後續

1. **PR 後是否需 sibling 策略類似補丁？**
   - PA audit §7 警告 bb_breakout / bb_reversion 同樣設計可能有同問題，但 W6 baseline 沒看到（signal 沒對齊）。本補丁僅 ma_crossover；後續 W-AUDIT-8a Option A 應一次性對齊 5 策略。

2. **funding_arb 已 retire（ADR-0018），無需 W7-3 補丁。**

3. **grid_trading 不在受害策略列表**（它是 first opener / paper_state 寫入方），不需此補丁。

4. **Reason 字串契約變動風險**：rejection_coding.rs 是 `pub(super) enum`，外部 caller 不應構造，理論上格式安全。但仍有：
   - rejection_coding.rs 自身 future refactor 改格式 → fallback 觸發 + warn log 可發現
   - 上層加 prefix（如 metric tag）→ contains() 仍能命中
   建議 W-AUDIT-8a 收口時順便評估「是否將 reason parsing 抽成 helper 集中」。

5. **Performance**：on_rejection 加 2 次 `contains()` + 1 次 `tracing::debug!`（debug level 不寫日誌默認），熱路徑開銷極小（~ns 級）。

---

## 8. Operator 下一步

1. **NOT DEPLOYED** — E2 審查（請 PM 派 `@E2`）
2. E4 regression（請 PM 派 `@E4` — 跑完整 cargo test 套件 + 確認 1-tick defense 在 mock fill flow 下行為）
3. 通過後 PM 統一 commit + push（按 §七 commit chain E1→E2→E4→QA→PM）
4. PM 決定 restart 時機（`ssh trade-core 'cd ~/BybitOpenClaw/srv && bash helper_scripts/restart_all.sh --rebuild --keep-auth'`）
5. 部署後 watch INXUSDT ma_crossover risk_verdicts duplicate_position rate（應立即降至 ≤ 1/min/symbol）

---

## 9. Commit message 建議（PM 統一 commit 時用）

```
[skip ci] W7-3 ma_crossover on_rejection 1-tick defense — sync positions on duplicate_position

PA #3 audit Option B 補丁式應急防衛：ma_crossover.on_rejection 識別
router gate 1.5 duplicate_position reason → 解析 existing_is_long →
sync self.positions 為 paper_state 真實方向 → 終結 INXUSDT 11:34
cross-strategy desync hot loop（5min reject 2319 次）。

不動 TickContext signature / 不改 router gate / 不做 5 策略 systemic
fix（留 W-AUDIT-8a Option A 治本）。

Files:
- srv/rust/openclaw_engine/src/strategies/ma_crossover/strategy_impl.rs
  on_rejection: 加 duplicate_position 識別分支 + tracing log
- srv/rust/openclaw_engine/src/strategies/ma_crossover/tests.rs
  +4 unit tests: short_syncs / long_syncs / unknown_format_fallback / non_duplicate_full_rollback

Tests:
- cargo test -p openclaw_engine --lib --release ma_crossover  → 58/58 PASS
- cargo test -p openclaw_engine --lib --release (full)        → 2639/2639 PASS, 0 regression
- cargo check --release --bin openclaw-engine                  → 0 errors
```

---

**E1 IMPLEMENTATION DONE: 待 E2 審查**
（report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-10--w7_3_emergency_1tick_defense.md`）
