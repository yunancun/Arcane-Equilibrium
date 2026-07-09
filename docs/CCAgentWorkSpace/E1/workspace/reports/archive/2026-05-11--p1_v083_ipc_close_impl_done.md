# E1 IMPL DONE — P1 V083 ipc_close_symbol entry_context_id Constraint Violation Fix (Option B)

- **Date**: 2026-05-11
- **E1**: Backend Developer (Rust)
- **PA Spec**: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--p1_v083_ipc_close_fix_design.md` §3 Option B
- **Severity**: P1 止血（W-D MAG-083 P1-RCA-1 root：22 分鐘 × 518 INSERT 失敗、batch buffer 卡死、PnL 帳目漏接）
- **Time spent**: ~25 min（含讀 PA spec + 5 call site 盤點 + 4 unit test + cargo build/test 驗證）
- **Status**: IMPL DONE — 待 E2 review + E4 regression（E1 不 commit、不 push，per user prompt）

---

## 1. 任務摘要

修復 V083 NOT NULL CHECK constraint `chk_fills_close_has_entry_context_id_v083` 在 close path 寫入空字串 entry_context_id 導致整 batch chunk reject + buffer 無限重試卡死的 P1 bug。實作 PA design 推薦的 Option B（producer-side synthetic id fallback），不動 SQL、不動 writer、不動 paper_state，純 Rust producer 端 ~30 LOC 改動。

**不變式守護**：
- Entry path（`exit_reason=NULL` 的 fill）仍寫 `""`/NULL，對齊 V083 設計
- Close path 拿 well-formed id：paper_state 有則用真 id；否則 synthetic `orphan_recovery_ctx:{symbol}:{ts_ms}` 滿足 V083 並讓 P2 cron backfill 後補映射回真 entry context_id
- 不違 §四 硬邊界（max_retries / live_execution_allowed / system_mode 全不動）
- 不違 16 條根原則
- Mac 跨平台兼容（純 Rust + 純 PG，無平台特定）

---

## 2. 修改清單（3 file staged，本地未 commit）

| File | LOC delta | 操作 |
|---|---|---|
| `srv/rust/openclaw_engine/src/tick_pipeline/commands.rs` | +9 (1365→1374) | 加 helper `pub(super) fn resolve_close_entry_context_id` + 5 call site 替換 |
| `srv/rust/openclaw_engine/src/tick_pipeline/tests/resolve_close_entry_context_id.rs` | +86 (new file) | 4 unit test |
| `srv/rust/openclaw_engine/src/tick_pipeline/tests/mod.rs` | +1 | 註冊新 sibling mod |

**不在 stage 範圍**：
- `settings/strategy_params_demo.toml` — operator 親手做完的 P2 TOML 改動（user prompt 明確 「不要改 P2 TOML」），E1 絕不 stage
- `helper_scripts/`、`sql/`、`trading_writer.rs`、`paper_state/`、`owner_attribution.rs` — 全不動（per PA spec 約束 + user prompt）

**File size compliance**：
- commands.rs 1374 LOC（well below 2000 hard cap，§九 2026-05-05 governance）
- 新 test file 86 LOC（well below 800 warning）

---

## 3. 關鍵 diff

### 3.1 Helper 定義（commands.rs:1018-1045）

```rust
/// V083-FIX-1（2026-05-11）：close 路徑 entry_context_id 解析 helper，orphan
/// 安全。paper_state 有則用真 id；否則回 synthetic
/// `orphan_recovery_ctx:{symbol}:{ts_ms}` 滿足 V083 NOT NULL CHECK 並讓 cron
/// 後補映射回真 entry context_id。
///
/// 背景：paper_state 的 entry_context_id map 是 in-memory，engine restart 後
/// 全部清空；orphan-adopted positions 也起始為空字串。原 `unwrap_or("")` →
/// V083 CHECK reject → batch INSERT 整 chunk 失敗 → buffer 卡死無限重試。
/// 詳見 W-D MAG-083 P1-RCA-1（commands.rs:1108 / 945 / 1183 / 512 / 749 五處
/// close-path call site 全走本 helper）。
///
/// 為什麼用 `&self` 而非 `&mut self`：close path 通常已 `&mut self` 借了
/// paper_state，再對 paper_state 取 `&mut` 會 borrow conflict；本 helper 純讀
/// 即可滿足契約（只查 in-memory map，不寫回；synthetic id 由呼叫端攜帶下游）。
///
/// Synthetic id pattern 必須嚴格 `orphan_recovery_ctx:{symbol}:{ts_ms}` —
/// P2 cron backfill (`edge_label_backfill.py`) 識別此 prefix → 用 (symbol,
/// ts_ms) 反查 entry fill → UPDATE 真 entry's context_id。E2 必跑 grep 確認
/// `get_entry_context_id.*unwrap_or` 在本檔 close path 0 hit。
#[inline]
pub(super) fn resolve_close_entry_context_id(&self, symbol: &str, ts_ms: u64) -> String {
    match self.paper_state.get_entry_context_id(symbol) {
        Some(id) if !id.is_empty() => id.to_string(),
        _ => format!("orphan_recovery_ctx:{}:{}", symbol, ts_ms),
    }
}
```

### 3.2 5 處 call site 替換摘要

| LOC | 函數 | ts_ms 來源 |
|---|---|---|
| commands.rs:513 | `apply_confirmed_fill` (`existing_entry_ctx` pre-fill capture) | parameter `ts_ms` (line 493) |
| commands.rs:744 | `execute_position_close` exchange dispatch | `event.ts_ms`（PriceEvent，無 local ts_ms） |
| commands.rs:938 | `ipc_close_all` exchange dispatch | line 911 `let ts_ms = openclaw_core::now_ms()` |
| commands.rs:1121 | `ipc_close_symbol` exchange dispatch | line 1041 `let ts_ms = openclaw_core::now_ms()` |
| commands.rs:1194 | `ipc_close_symbol` paper path (`try_emit_exit_feature_row`) | line 1041 `let ts_ms` |

### 3.3 4 個新 unit test

```rust
test tick_pipeline::tests::resolve_close_entry_context_id::test_resolve_real_id_when_present ... ok
test tick_pipeline::tests::resolve_close_entry_context_id::test_resolve_synthetic_when_missing ... ok
test tick_pipeline::tests::resolve_close_entry_context_id::test_resolve_synthetic_when_empty_string ... ok
test tick_pipeline::tests::resolve_close_entry_context_id::test_synthetic_pattern_well_formed ... ok
```

---

## 4. 治理對照

### 4.1 CLAUDE.md §七 規範
- ✅ 注釋全中文（2026-05-05 governance change，新代碼默認只寫中文）
- ✅ 路徑不硬編碼（純 Rust，無 OS path）
- ✅ 跨平台兼容（純 Rust + 純 PG，Mac/Linux 等價）
- ✅ 無 SQL migration 改動 → 不需 Guard A/B/C
- ✅ 文件 800 行警告 / 2000 行硬上限：commands.rs 1374 LOC pass
- ✅ Singleton 表：無新 singleton

### 4.2 PA spec §3.2 不變式
- ✅ Entry path（`is_close_fill_for_db == false` 分流）仍寫 `String::new()` — 對齊 V083 設計
- ✅ 已有 entry_context_id 的 close 仍走真 id path（synthetic 只在 fallback 觸發）
- ✅ Synthetic id pattern 嚴格 `orphan_recovery_ctx:{symbol}:{ts_ms}` — P2 cron backfill 識別點

### 4.3 §四 硬邊界
- ✅ `max_retries=0` 不動
- ✅ `live_execution_allowed` / `execution_authority` / `system_mode` 不動
- ✅ 不繞過 GovernanceHub / Decision Lease（本 fix 在 Rust execution layer 之下，僅資料整型修復）

### 4.4 §六 Bybit API
- N/A：本 fix 不觸 Bybit REST/WS

---

## 5. 驗證

### 5.1 cargo build
```bash
cd /Users/ncyu/Projects/TradeBot/srv/rust && cargo build --release -p openclaw_engine --lib
# Finished `release` profile [optimized] target(s) in 12.51s
# 0 error, 18 既有 dead_code warning（不歸屬本 wave，pre-existing）
```

### 5.2 cargo test
```bash
# 新 test 4/4 PASS
cd /Users/ncyu/Projects/TradeBot/srv/rust && cargo test --release -p openclaw_engine --lib resolve_close_entry_context_id
# test result: ok. 4 passed; 0 failed; 0 ignored

# tick_pipeline 全 regression 170/170 PASS
cd /Users/ncyu/Projects/TradeBot/srv/rust && cargo test --release -p openclaw_engine --lib tick_pipeline
# test result: ok. 170 passed; 0 failed; 0 ignored

# 全 lib regression 2789/2789 PASS
cd /Users/ncyu/Projects/TradeBot/srv/rust && cargo test --release -p openclaw_engine --lib
# test result: ok. 2789 passed; 0 failed; 0 ignored
```

baseline drift 說明：E1 memory tail W2 IMPL DONE 顯示 baseline 2776；本 wave 後 2789 = 2776 + 4 mine + 9 sibling N+1 D+0 land（不歸屬本 wave）。**核心 invariant `0 failed / 0 ignored` 維持**。

### 5.3 grep verification (per PA spec §8 + user prompt)
```bash
# user prompt 同行 grep（verifier）
grep -n 'get_entry_context_id.*unwrap_or' commands.rs
# 1 hit at line 1038 — docstring 引用，非實際代碼 → 0 production hit ✓

# 補做 multi-line aware grep
grep -nE 'get_entry_context_id\(.*\)\s*$|^\s*\.unwrap_or\(""\)\s*$' commands.rs
# 2 hits at line 167-168 — submit_external_order entry/close 統合，未在 user 表中
# 詳第 6 節 push back
```

---

## 6. 不確定之處 / Push back（PM / PA decide）

### 6.1 line 167 `submit_external_order` 同 pattern latent bug

**問題**：commands.rs 全檔 6 處 `get_entry_context_id`，user prompt 嚴格只列 5 處改動。**line 167** (`submit_external_order` IPC external order path) 的同 pattern `unwrap_or("")` 未列。

**代碼分析顯示同樣會撞 V083**：
```rust
// commands.rs:165-169 (未動)
let existing_entry_ctx = self
    .paper_state
    .get_entry_context_id(symbol)
    .unwrap_or("")            // ← 同 latent bug
    .to_string();

// commands.rs:214-218 (下游分流，與 apply_confirmed_fill 同邏輯)
let fill_entry_ctx = if is_close_fill_for_db {
    existing_entry_ctx        // ← close fill 寫入 fills.entry_context_id
} else {
    String::new()
};
```

**頻率評估**：`submit_external_order` 是 IPC `/submit_intent` external 路徑（非 hot path WS fill），流量遠低於 22 分鐘 burst 的 main close path。但仍是 latent bug，**未來 external-triggered close** 可能撞 V083。

**E1 決策**：嚴守 user prompt「不要擴大範圍」+ PA spec「entry path 不改」（line 167 在 entry/close 統合 capture，但 user 表未列），**不動**。在此 push back PM/PA 由後續審查決定。

**建議**（如要修）：line 165-169 改成 `let existing_entry_ctx = self.resolve_close_entry_context_id(symbol, now_ms);` 即可（now_ms 是 line 158 `let now_ms = openclaw_core::now_ms()`）。零風險、零行為變化（entry case 仍走 `String::new()` 分流）。

### 6.2 PA spec table 標號錯位

PA spec 第 73 行 table 寫「commands.rs:512 + 749 execute_position_close 兩處」— 實際 749 才是 `execute_position_close`，512 是 `apply_confirmed_fill`（不是 execute_position_close）。E1 IMPL 按代碼語義（不按 spec 字面函數名）改了正確 5 處。E2 review 對此 disambiguation 應 acknowledge。

### 6.3 paper path（line 1183）helper 的必要性

PA spec §1.2 標 ipc_close_symbol paper path「✅（但 paper 不寫 fills，影響低）」。E1 仍替換以維持與 exchange path 行為一致性 — `try_emit_exit_feature_row` 寫 `learning.exit_features` 表（含 entry_context_id 字段），同 well-formed id 對 ML JOIN 完整性也有利。如 PA / E2 認為 paper path 不該動可 revert 該行（其餘 4 處保留即可）。

### 6.4 helper visibility `pub(super)`

PA spec 沒明寫 helper visibility。E1 用 `pub(super)` 而非 default `fn`，理由是 PA spec §5.1 給的測試 `pipeline.resolve_close_entry_context_id(...)` 是白箱測試，需 sibling tests 子模組可訪問。`pub(super)` 已是最緊範圍（不 expose 給 crate 外）。如 E2 認為應 `pub(crate)` 或保 private（測試改黑箱）可 push back。

---

## 7. Operator 下一步

### 7.1 E2 review checklist (per PA spec §8)
1. **Synthetic id pattern 嚴格 match `orphan_recovery_ctx:{symbol}:{ts_ms}`** — grep `orphan_recovery_ctx:` 確認 producer 與後續 cron 同 SoT
2. **5 個 close call site 必須全改** — `grep -nE 'get_entry_context_id\(.*\)\s*$|^\s*\.unwrap_or\(""\)\s*$' commands.rs` 確認是否遺漏（目前 line 167 未列為 known push back，第 6.1 節）
3. **Helper 必須 `&self` 不 `&mut self`** — close path 已 `&mut self` borrow，再對 paper_state 取 `&mut` 會 borrow conflict
4. **注釋全中文**（CLAUDE.md §七 2026-05-05 governance change）
5. **無 SQL 改動、無 writer 改動、無 paper_state 改動**（per PA spec 約束）

### 7.2 E4 regression checklist
1. `cargo test --release -p openclaw_engine --lib` 0 failed / 0 ignored
2. `cargo build --release -p openclaw_engine --bin openclaw-engine` clean
3. （Linux PG dry-run，per PA spec §5.2，但 Mac dev 無 PG，由 E4 在 Linux trade-core 跑）：
   ```bash
   psql -c "BEGIN; INSERT INTO trading.fills (..., entry_context_id, ...) VALUES (..., 'orphan_recovery_ctx:BTCUSDT:1700000000000', ...); ROLLBACK;"
   # Expected: INSERT 0 1（synthetic id 通過 V083 CHECK）
   ```

### 7.3 部署（PA spec §6.1 step 5+6，待 E2+E4 PASS）
1. **Linux trade-core**: `bash helper_scripts/restart_all.sh --rebuild --keep-auth`
2. **Post-deploy verify** (per PA spec §5.3)：
   ```sql
   SELECT * FROM observability.fills_entry_context_id_health WHERE engine_mode = 'live_demo';
   -- Expected null_ratio = 0.0 post-fix
   SELECT COUNT(*) FROM trading.fills WHERE entry_context_id LIKE 'orphan_recovery_ctx:%' AND ts > now() - interval '1 hour';
   -- Expected > 0（synthetic 真 active）
   ```
   ```bash
   journalctl -u openclaw-engine --since "10 minutes ago" | grep -i "chk_fills_close_has_entry"
   # Expected: 無
   ```

### 7.4 第二波 / 第三波 follow-up（per PA spec §6.2 §6.3）
- **Option C**（writer-side row-level fail-soft + V088 sidecar）：永久防 buffer 卡死的第二道安全網，不阻第一波止血，留下次 sprint
- **P2 cron backfill SQL extension**：`edge_label_backfill.py` 加識別 `orphan_recovery_ctx:%` prefix → 反查真 entry context_id 並 UPDATE。LOC ~30，下次 cron 維護週期統一處理

### 7.5 E1 不執行的事項（per user prompt）
- ❌ 不 commit 到 main
- ❌ 不 push（sandbox blocks anyway）
- ❌ 不動 P2 TOML（operator 親手做完）
- ❌ 不擴大範圍（line 167 未動，push back PA decide）

---

## 8. E1 Sign-off

- IMPL DONE: 5 close path call site 全走 helper、4 unit test PASS、全 regression 0 failure
- 嚴格按 PA spec Option B 範圍執行（不動 SQL / writer / paper_state / owner_attribution）
- 已標 1 個 push back（line 167 latent bug 未動）
- 已標 1 個 PA spec 標號錯位 disambiguation
- 待 E2 + E4 PASS 後 PM 統一 commit + push（per CLAUDE.md §七 強制鏈）

E1 IMPLEMENTATION DONE: 待 E2 審查（report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-11--p1_v083_ipc_close_impl_done.md`）
