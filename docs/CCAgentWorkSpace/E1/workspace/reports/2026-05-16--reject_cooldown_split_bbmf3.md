# E1 IMPL — Wave 2 Track E1 reject_cooldown entry/close split (BB-MF-3 P0 prereq)

**日期**：2026-05-16
**Agent**：E1 (Backend Developer)
**任務來源**：PM Wave 2 派發
**對應 spec**：`docs/execution_plan/2026-05-15--edge_p2_3_phase_1b_close_maker_first_spec.md` v1.2 §6.1
**對應 AMD**：`docs/governance_dev/amendments/2026-05-15--AMD-2026-05-15-02-edge-p2-3-phase-1b-close-maker-first.md` v0.3 §8 IMPL Prereq 6
**Branch**：worktree `agent-a06c4b13794d0a5e6` (single E1 instance)

---

## 1. 任務摘要

拆 `grid_trading::GridTrading` struct 既有單一 `reject_cooldown_until_ms` HashMap 為 entry / close 兩條獨立 map，解決 BB-MF-3 silent degradation：當前 entry-side reject 寫入會凍結同 symbol 的 close emission（spec v1.2 §6.1 + AMD §8 prereq 6 升 P0，pre-Phase 2a Demo enable 必 land）。

本 commit **僅完成 prereq plumbing** — 純 helper API + cooldown map split + per-side gate；**不接線生產 close-side dispatcher**（commands.rs 仍 hard-coded market），由 Phase 1b 主軸 IMPL（commands.rs:778-816 / 940 / 1123）在後續 sprint 拼接。

---

## 2. 修改清單

| File | LOC delta | 內容 |
|---|---|---|
| `srv/rust/openclaw_engine/src/strategies/grid_trading/mod.rs` | +73 / -10 | 2 新常量 (`CLOSE_REJECT_COOLDOWN_DEFAULT_MS=60_000` / `CLOSE_REJECT_COOLDOWN_TOO_MANY_PENDING_MS=300_000`) + struct 拆 field + 新 inherent impl `arm_close_cooldown` |
| `srv/rust/openclaw_engine/src/strategies/grid_trading/constructors.rs` | +12 / -3 | 3 ctor sites (`new` / `new_geometric` / `new_adaptive_with_mode`) init 兩條 map |
| `srv/rust/openclaw_engine/src/strategies/grid_trading/position_mgmt.rs` | +98 / -16 | `on_rejection_impl` + `on_post_only_rejected_impl` 寫入 `reject_cooldown_entry_until_ms`；新增 `arm_close_cooldown_impl` 寫入 `reject_cooldown_close_until_ms` 並依 `MakerRejectionCategory` 路由 |
| `srv/rust/openclaw_engine/src/strategies/grid_trading/signal.rs` | +32 / -7 | 拆 gate：早期「兩 side 都 active」short-circuit + per-side entry gate 在 `would_open` 已知後 |
| `srv/rust/openclaw_engine/src/strategies/grid_trading/tests.rs` | +305 / -3 | 8 新 BB-MF-3 unit test + 1 既有 test 加 isolation 斷言 |
| `srv/rust/openclaw_engine/src/strategies/maker_rejection.rs` | +7 / -4 | doc reference 更新（PostOnlyCross variant 注釋）|
| `srv/rust/openclaw_engine/src/bybit_rest_client.rs` | +8 / -3 | doc reference 更新（is_exchange_backoff 注釋）|

**Total**: +495 / -40 across 7 files

---

## 3. 關鍵 diff

### 3.1 mod.rs — 兩條獨立 cooldown map

```rust
// 之前（單一 map）
pub(super) reject_cooldown_until_ms: HashMap<String, u64>,

// 之後（拆 entry + close）
pub(super) reject_cooldown_entry_until_ms: HashMap<String, u64>,
pub(super) reject_cooldown_close_until_ms: HashMap<String, u64>,
```

新常量（CLAUDE.md §五 [策略工具包]）：

```rust
/// EDGE-P2-3 Phase 1b BB-MF-3 (2026-05-16) — close-side reject cooldown
/// 預設時長（取代既有 entry-side reject_cooldown_ms），對應 spec v1.2 §6.1
/// 「其他 reject → 1min」分支。
pub(crate) const CLOSE_REJECT_COOLDOWN_DEFAULT_MS: u64 = 60_000;

/// EDGE-P2-3 Phase 1b BB-MF-3 (2026-05-16) — close-side TooManyPending
/// 帳戶級背壓固定退避時長，對應 spec v1.2 §6.1 表「TooManyPending → 5min」
/// （PM Wave 2b 任務明文；spec §5.4 BB-MF-2 dynamic backoff 屬獨立工作項）。
pub(crate) const CLOSE_REJECT_COOLDOWN_TOO_MANY_PENDING_MS: u64 = 300_000;
```

新 public API（`impl GridTrading` inherent block）：

```rust
pub fn arm_close_cooldown(
    &mut self,
    symbol: &str,
    ts_ms: i64,
    category: &crate::strategies::maker_rejection::MakerRejectionCategory,
) {
    self.arm_close_cooldown_impl(symbol, ts_ms, category);
}
```

### 3.2 position_mgmt.rs — `arm_close_cooldown_impl` 路由邏輯

```rust
let cooldown_ms: Option<u64> = match category {
    // spec §5.3 Race C：PostOnlyCross close 走 market，不 arm cooldown。
    MakerRejectionCategory::PostOnlyCross => None,
    // spec §6.1 + PM Wave 2b 任務：TooManyPending close → 5min 固定。
    MakerRejectionCategory::TooManyPending => {
        Some(super::CLOSE_REJECT_COOLDOWN_TOO_MANY_PENDING_MS)
    }
    // 其他 reject 類別走 1min default（per spec §6.1 表）。
    MakerRejectionCategory::FokCancel
    | MakerRejectionCategory::SelfCancel
    | MakerRejectionCategory::Other(_) => Some(super::CLOSE_REJECT_COOLDOWN_DEFAULT_MS),
};
```

### 3.3 signal.rs — gate 拆分

```rust
// 早期 short-circuit：兩 side cooldown 都 active 時整個 tick 無動作（性能優化）
if let (Some(&entry_until), Some(&close_until)) = (
    self.reject_cooldown_entry_until_ms.get(sym),
    self.reject_cooldown_close_until_ms.get(sym),
) {
    if ctx.timestamp_ms < entry_until && ctx.timestamp_ms < close_until {
        return vec![];
    }
}

// ... cross detection ...

// per-side gate（在 would_open 已知後）
if would_open {
    if let Some(&entry_until) = self.reject_cooldown_entry_until_ms.get(sym) {
        if ctx.timestamp_ms < entry_until {
            return vec![];  // 僅阻擋 Open，close emission 不受影響
        }
    }
}
```

### 3.4 8 新 BB-MF-3 test

| # | Test name | 驗證對象 |
|---|---|---|
| 1 | `test_entry_reject_does_not_freeze_close_path` | PM Step 4 #1：entry cooldown active 時 close 仍可發 |
| 2 | `test_close_reject_does_not_freeze_entry_path` | PM Step 4 #2：close cooldown active 時 entry 仍可發 |
| 3 | `test_close_too_many_pending_5min_cooldown` | PM Step 4 #3 + spec §6.1 TooManyPending → 5min |
| 4 | `test_close_postonly_cross_no_cooldown_immediate_market` | PM Step 4 #4 + spec §5.3 Race C |
| 5 | `test_close_default_reject_categories_1min_cooldown` | spec §6.1 「其他 reject → 1min」（FokCancel + SelfCancel + Other）|
| 6 | `test_grid_short_circuits_when_both_cooldowns_active` | signal.rs short-circuit safety + entry expired 後 close 路徑恢復 |
| 7 | `test_cooldown_isolation_multi_symbol` | multi-symbol regression coverage |
| 8 | `test_arm_close_cooldown_saturating_add_overflow_safe` | i64 overflow safety（saturating_add）|

加更新既有 `test_g7_09c_post_only_reject_callback_arms_cooldown`：加 isolation 斷言確認 entry reject 不污染 close map。

---

## 4. 治理對照

### 4.1 CLAUDE.md §四 硬邊界

| 邊界 | 本 IMPL 影響 |
|---|---|
| `max_retries=0` | 不觸（純 cooldown plumbing）|
| `live_execution_allowed` / `execution_authority` / `system_mode` | 不觸 |
| `live_reserved` / `OPENCLAW_ALLOW_MAINNET=1` / authorization.json | 不觸 |
| `decision_lease_emitted` | 不觸 |

### 4.2 CLAUDE.md §七 跨平台兼容性 ★★

- ✅ 0 hardcoded `/Users/ncyu` / `/home/ncyu` 路徑（grep 驗）
- ✅ LocalLLMClient 抽象 / 服務遷移 / 依賴管理 — 不觸（純 Rust strategy 內部）

### 4.3 CLAUDE.md §七 注釋規範（2026-05-05 governance）

- ✅ 新代碼注釋默認只寫中文（無新加 bilingual mandate）
- ✅ 既有中英對照塊不主動清理（僅修改 doc reference 時更新）
- ✅ MODULE_NOTE / docstring / inline / SAFETY 不變量都中文表達

### 4.4 CLAUDE.md §九 文件大小

| File | 改前 LOC | 改後 LOC | 警告線 800 | 硬上限 2000 |
|---|---|---|---|---|
| `mod.rs` | ~470 | ~543 | OK | OK |
| `tests.rs` | 1389 | 1694 | ⚠️ 過 800（pre-existing；已超 800 線屬 EDGE-P2-3 系列累積）| OK |
| `signal.rs` | 396 | 421 | OK | OK |
| `position_mgmt.rs` | 234 | 332 | OK | OK |
| `constructors.rs` | 234 | 246 | OK | OK |

`tests.rs` 1694 > 800 警告線，但仍遠低於 2000 硬上限。**Pre-existing baseline exception clause**（CLAUDE.md §九 Baseline 原則）：tests.rs 在本 wave 開工前已 1389（pre-existing > 800），本 wave 接受 +305 LOC = 1694（≤ 2000 硬上限）。E2 review 標警告即可，不阻 merge。

### 4.5 AMD-2026-05-15-02 §8 IMPL Prereq 6

> **`reject_cooldown` entry/close 拆分升 P0 priority pre-Phase 2a Demo enable 必 land（BB-MF-3）**

✅ Cooldown 拆分完成；entry/close 兩條獨立 map；per-side gate 解 silent degradation；8 unit test 鎖隔離不變式。

---

## 5. Test 結果

### 5.1 Cargo 命令

```bash
cd /Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine
cargo build --release                # ✅ 0 errors
cargo test --lib --release strategies::grid_trading::tests  # ✅ 60/0
cargo test --lib --release           # ✅ 2903 passed / 1 failed (pre-existing) / 1 ignored
cargo build --release --bin openclaw-engine  # ✅ green
cargo test --release --bin openclaw-engine   # ✅ 59/0
rustfmt --check (7 changed files)    # ✅ clean
```

### 5.2 Regression 對照

| 維度 | 改前 baseline | 改後 | Delta |
|---|---|---|---|
| `cargo test --lib` total passed | 2895 | 2903 | **+8 new BB-MF-3 test** |
| `cargo test --lib` failed | 1 | 1 | 0 (same pre-existing OU stochastic test, identical sigma=0.34168122199887635) |
| `cargo test --lib` ignored | 1 | 1 | 0 |
| `cargo test --lib strategies::grid_trading::tests` | 52 | 60 | +8 BB-MF-3 |
| `cargo test --bin openclaw-engine` | 59 | 59 | 0 |

**0 functional regression**。Pre-existing fail (`test_wp03_residual_sigma_synthetic_ou_convergence` in `grid_helpers.rs`) 是 OU 殘差 sigma 統計收斂測試，stochastic 失敗值前後 byte-identical，與本 commit 完全無關。

---

## 6. 不確定之處 / push back

1. **Spec §5.4 dynamic backoff vs PM 任務 5min 固定**：spec v1.2 §5.4 (BB-MF-2)
   規定 TooManyPending close 應 per-symbol dynamic backoff (1s exp → 60s 上限
   + 10-symbol 同時觸發升級 global pause 5min)；PM Wave 2b 任務明文「TooManyPending
   close → reject_cooldown_close_until_ms 5 min（per spec §6.1 + AMD §6）」。
   兩者衝突；本 IMPL 取 **PM 任務明文（5min 固定）**，避免 scope creep（dynamic
   backoff per-symbol BackoffState + global cascade 是 ~50 LOC state machine +
   ~80 LOC integration test 的獨立工作項）。**E2 / PM 確認**：dynamic backoff
   後續 sprint 另開 ticket 實作？或本任務應 scope-in？memory log 標獨立工作項。

2. **`on_post_only_rejected` Strategy trait method 是 dead code**：compiler warning
   揭露生產 wiring 缺失。本 commit 保留現狀（拆 cooldown 使其準備好 Phase 1b
   接線），不主動 wire production dispatcher。**E2 確認**：是否本 commit 應同步
   接 production wiring（dispatch.rs 或 event_consumer），或留 Phase 1b 主軸？
   本 commit 取保守：scope creep 禁止。

3. **integration test 位置**：PM 任務 Step 4 提及「Integration test (in
   `tick_pipeline/tests/`)：`test_cooldown_isolation_entry_close`」。但
   `tick_pipeline/tests/` 不在 src tree 內（src/tick_pipeline/tests/ 是 unit-level
   inline）；event_consumer/tests/ 也沒有 cooldown 系列 file。本 commit 把
   integration-grade 測試（multi-symbol regression `test_cooldown_isolation_multi_symbol`）
   inline 進 `grid_trading/tests.rs`（與 60 個既有 grid 測試對齊）。**E2 / E4 確認**：
   是否要創建獨立 `event_consumer/tests/cooldown_isolation_tests.rs` 模組（即使
   現在沒有對應 production wiring）？或 inline 即可？

4. **`arm_close_cooldown` 不放 Strategy trait**：避免影響 4 個非 grid 策略
   default impl（會逼每個策略寫 4-line no-op）+ 影響 `Box<dyn Strategy>`
   dispatcher signature。Phase 1b 主軸 IMPL 若要擴及他策略另議。**E2 確認**：
   設計選擇是否合理？

5. **`reject_cooldown_close_until_ms` 在本 commit 沒有 production read 點**：
   close path 仍 hard-coded market（commands.rs:778-816 屬 EDGE-P2-3 Phase 1b
   主軸 IMPL scope，等 3-gate）。本 commit 完成「資料欄位 + 寫入 helper +
   隔離測試」；close path 真正進 cooldown gate 的接線留給 Phase 1b 主軸 IMPL
   commit。**E2 確認**：dead-code-by-design 是否需 `#[allow(dead_code)]` 標註？
   當前 lib build 0 dead_code warning（因 tests.rs 全 exercise）。

---

## 7. Operator 下一步

1. **E2 senior + adversarial review**：
   - 設計選擇驗：trait vs inherent impl / 5min fixed vs dynamic backoff
   - signal.rs gate 拆分邏輯驗：M-2 + G7-09c entry-side tight loop 防護不變式
   - test 隔離斷言驗：8 new test + 1 updated 是否覆蓋 BB-MF-3 silent degradation 反模式
2. **E4 regression**：
   - lib + binary 測試 baseline 對齊（2903 + 59）
   - rustfmt --check 7 changed files
   - 無新 hardcoded path / 無 unsafe code
3. **PM 同步**：等 E2 + E4 sign-off 後，PM 統一 commit + push（per CLAUDE.md §七
   E1→E2→E4→QA→PM 強制工作鏈）；本 E1 IMPL 不 self commit。
4. **後續工作項追蹤**：spec §5.4 dynamic backoff per-symbol exp + global pause
   cascade 屬獨立 P1 backlog 工作項，建議開 ticket
   `P1-BBMF-2-DYNAMIC-BACKOFF-1` 等 Phase 1b 主軸 IMPL 後再排。

---

## 8. 雙語注釋抽樣

### MODULE_NOTE 位置

- `mod.rs::reject_cooldown_close_until_ms` field doc — 中文說明 spec §6.1 路由
  規則 + 預期 wiring 時點 + Phase 1b prereq 範圍邊界
- `position_mgmt.rs::arm_close_cooldown_impl` — 中文 SAFETY 不變量（saturating_add
  防 i64 溢出 + PostOnlyCross no-op fall-back to market 設計理由）
- `signal.rs` per-side gate — 中文 SAFETY 不變量（entry-only / close-only 不在
  short-circuit 處理；違反 = 回到 BB-MF-3 silent degradation 反模式）

### 8 新 test 注釋

每個 test 開頭 doc-comment 中文說明：
- 對應 spec / AMD 段落
- 驗證的不變量
- 預期行為 + 失敗時的真實後果

---

## 9. Commit 建議（PM 統一執行）

**禁止 `[skip ci]`**（Rust code change，CI 必跑）。

```
fix(reject_cooldown): split entry/close cooldown maps (BB-MF-3 P0, Wave 2b)

EDGE-P2-3 Phase 1b prereq 6 (AMD-2026-05-15-02 §8): split single
reject_cooldown_until_ms HashMap into reject_cooldown_entry_until_ms +
reject_cooldown_close_until_ms to prevent entry-side reject from freezing
same-symbol close path (silent degradation).

Changes:
- grid_trading struct: split cooldown field + add inherent
  arm_close_cooldown(sym, ts_ms, category) public API
- maker_rejection routing: TooManyPending close → 5min fixed (spec §6.1);
  PostOnlyCross close → no-op (spec §5.3 Race C, fall back to market);
  others → 1min default
- signal.rs gate: replace unified early-return with two-side short-circuit
  + per-side entry gate after would_open known (close emission unaffected
  by entry cooldown)
- 8 new unit tests covering isolation, routing, multi-symbol, overflow
- doc reference updates in maker_rejection.rs / bybit_rest_client.rs

Acceptance:
- cargo build --release green
- cargo test --lib --release: 2903 passed (baseline 2895 + 8 new) /
  1 failed (pre-existing OU stochastic, unrelated) / 1 ignored
- cargo test --bin openclaw-engine: 59/0
- rustfmt --check clean on 7 changed files
- 0 hardcoded paths

NOT in scope (per task minimal scope + spec §5.4 BB-MF-2 separate work):
- Production close-side dispatcher wiring (commands.rs:778-816 hard-coded
  market remains; Phase 1b main IMPL scope)
- Per-symbol dynamic exp backoff + global cascade (spec §5.4 BB-MF-2)
- Strategy trait extension (arm_close_cooldown is grid-only inherent impl)
- Integration test in event_consumer/tests/ (no production dispatcher yet)
```
