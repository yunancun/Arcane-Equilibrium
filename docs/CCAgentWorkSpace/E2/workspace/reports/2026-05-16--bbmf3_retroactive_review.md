# E2 Retroactive Adversarial Review — BB-MF-3 reject_cooldown entry/close split

**對象**：commit `27f02a07` 內 `rust/openclaw_engine/src/strategies/grid_trading/` 5 files：
- `mod.rs` +73 / -19 LOC（struct field 拆兩 map + arm_close_cooldown public API）
- `constructors.rs` +12 LOC（3 constructor 初始化兩 map）
- `position_mgmt.rs` +98 / -38 LOC（on_post_only_rejected_impl + arm_close_cooldown_impl）
- `signal.rs` +32 / -8 LOC（cooldown gate 拆 entry/close + short-circuit optimization）
- `tests.rs` +305 / -1 LOC（8 new BB-MF-3 unit test）
- `maker_rejection.rs` doc comment 不動（commit body 自陳述「sibling preserved revert」）

**Scope**：EDGE-P2-3 Phase 1b BB-MF-3 P0 — 拆 `reject_cooldown_until_ms` 為 entry/close 兩條獨立 map，預防「entry reject 凍結 close path silent degradation」反模式
**Review 模式**：retroactive — sibling 12-agent audit session 多次 stash race silently dropped Wave 2b IMPL；commit body 自承 multi-session race recovery；CC cross-validation 確認 E2 0 dispatch
**Verdict**：**APPROVE-CONDITIONAL → PASS to E4** · 0 BLOCKER / 0 HIGH / 2 MEDIUM / 2 LOW / 1 P2

---

## 一、改動範圍 vs PA spec 核對

### Scope claim per spec v1.2 §6.1 + AMD-2026-05-15-02 §8 IMPL Prereq 6
1. **Field 拆分**：`reject_cooldown_until_ms` 拆為 `reject_cooldown_entry_until_ms` + `reject_cooldown_close_until_ms`
2. **路由規則**：
   - PostOnlyCross close → no-op（spec §5.3 Race C，走 market）
   - TooManyPending close → 5min 固定（spec §6.1 + PM Wave 2b 明文）
   - FokCancel / SelfCancel / Other close → 1min default（spec §6.1）
3. **Public API**：`arm_close_cooldown(symbol, ts, category)`（Phase 1b dispatcher 接線 target）
4. **8 BB-MF-3 unit test** 驗 entry/close cooldown 隔離不變式

### Diff 實測
- `mod.rs:141-152` 新 constant `CLOSE_REJECT_COOLDOWN_DEFAULT_MS=60000` + `CLOSE_REJECT_COOLDOWN_TOO_MANY_PENDING_MS=300000` ✅
- `mod.rs:235-255` field 拆兩 map + 詳註釋 ✅
- `mod.rs:474-481` `arm_close_cooldown` public API（不在 Strategy trait，僅 GridTrading 自身 impl）✅
- `position_mgmt.rs:172` `on_rejection_impl` 寫 entry map ✅
- `position_mgmt.rs:220` `on_post_only_rejected_impl` 寫 entry map ✅
- `position_mgmt.rs:248-291` `arm_close_cooldown_impl` 新 helper（PostOnlyCross no-op / TooManyPending 5min / 其他 1min）✅
- `signal.rs:157-172` early short-circuit gate **only when both sides active** ✅
- `signal.rs:286-302` 新 entry cooldown gate **after** would_open known ✅
- `constructors.rs` 3 constructor 各 +2 init line ✅
- `tests.rs:1387-...` 8 new test：
  - #1 test_entry_reject_does_not_freeze_close_path ✅
  - #2 test_close_reject_does_not_freeze_entry_path ✅
  - #3 test_close_too_many_pending_5min_cooldown ✅
  - #4 test_close_postonly_cross_no_cooldown_immediate_market ✅
  - #5 test_close_default_reject_categories_1min_cooldown ✅
  - #6 test_grid_short_circuits_when_both_cooldowns_active ✅
  - #7 test_cooldown_isolation_multi_symbol ✅
  - #8 test_arm_close_cooldown_saturating_add_overflow_safe ✅

✅ Claim 與 diff 一致，8 test 全在 mod tests 內。

---

## 二、Root cause 分析（對抗視角）

### Pre-fix 反模式
原 `reject_cooldown_until_ms` 單一 HashMap → entry path PostOnly reject 寫入 → `signal.rs` 早期 gate `ctx.timestamp_ms < until` 整個 tick return vec![] → **同 symbol 的 close emission 被同條件凍結** = "BB-MF-3 silent degradation"。

✅ 真解 root cause（拆兩 map 物理隔離）。

### Spec §5.3 Race C 路由
PostOnlyCross close 表示「掛價瞬間被吃」→ 立即 fallback to market 是 correct routing；不進 close cooldown 防止「未進場錯誤的 cooldown」。✅

### Spec §6.1 TooManyPending 5min 固定
PM 任務明文「TooManyPending close → 5min 固定」；spec §5.4 dynamic backoff（1s exp → 60s 上限 + global cascade）是 BB-MF-2 獨立工作項；**本 prereq 不實作 dynamic backoff** 是合理 scope cut。✅

---

## 三、**MEDIUM-1** — Production dispatcher 0 caller（dead-API plumbing）

### 對抗 grep 結果

```bash
grep -rnE 'arm_close_cooldown' rust/openclaw_engine/src/ | grep -v 'grid_trading/'
# 0 hit
```

`arm_close_cooldown` public API + `arm_close_cooldown_impl` helper + `reject_cooldown_close_until_ms` field **完全沒被 production caller 觸發**：
- `event_consumer/loop_exchange.rs:384` 對 Bybit `rejectReason` 跑 `classify(&order.reject_reason)` 拿 `MakerRejectionCategory`，但 **不呼 strategy callback**（只記 audit log）
- `tick_pipeline/commands.rs` / `event_consumer/dispatch.rs` / 任何 strategy_runner 都無 `arm_close_cooldown` 觸發路徑
- Strategy trait `mod.rs:182` `on_post_only_rejected` callback **本身也只在 grid_trading.rs trait impl 內**，無 event_consumer→strategy callback wiring 完成

### 問題分析

**WP-13 同型 partial-fix-marked-complete**：BB-MF-3 commit body 自陳述「8 new BB-MF-3 unit tests verify entry/close cooldown isolation」+ E1 self-report 「commit `15e67220`」— 但 **production wiring 並未完成**：
- 沒有 caller 觸發 `arm_close_cooldown`
- 沒有 caller 觸發 `on_post_only_rejected`（trait callback wiring 未接 event_consumer）
- 純 plumbing + 8 unit test 驗 helper 邏輯，但**生產環境 entry/close 隔離不變式無 runtime exercising**

### 對抗反問
1. 「8 test PASS 但 production 0 caller — 你說 `entry/close 隔離不變式` 在 runtime 被哪個路徑保證？」
2. 「`on_post_only_rejected` trait callback 從 commit `e7d4b9c2` (EDGE-P2-3 Phase 1B-3) 開始有 method definition，但 event_consumer loop_exchange.rs:384 拿到 classify result 後**只 audit log 不呼 strategy**；callback 本身是 dead-API。」
3. 「commit message body 是否 transparent 標 'plumbing-only prereq, no production wiring this commit'？」 — 答：是的，mod.rs:468-473 註釋寫「本 prereq commit 僅完成『資料欄位 + 寫入 helper + 隔離測試』，close path 真正進 cooldown gate 的接線留給 Phase 1b 主軸 IMPL（預期 close emission 處檢查此 map，cooldown 期內走 market fallback）」 + position_mgmt.rs:264 註釋同型 ✅

### 嚴重性 = MEDIUM
與 WP-13 partial fix 不同：BB-MF-3 commit body **明確自承** prereq plumbing-only / 主軸 IMPL 留 follow-up；治理透明 — 接受為 "Phase 1b prereq" valid pattern。但 review 必標：**dead-API 在 Phase 1b 主軸 wave 必補 wiring，否則 8 test PASS = false confidence**。

### 建議
- 開 follow-up ticket `P1-BBMF3-WIRE-1`：Phase 1b 主軸 dispatcher 接 `arm_close_cooldown(symbol, ts, category)` from event_consumer 拒絕路徑 + close emission 查 `reject_cooldown_close_until_ms` map
- E4 regression 必驗：production close path 在 close cooldown active 時走 market fallback（unit test 已驗 helper，但 production cooldown gate 路徑須 integration test）

---

## 四、**MEDIUM-2** — `signal.rs:157-172` short-circuit gate 邏輯改變需 invariant 加固

### 對抗讀
Pre-fix signal.rs 邏輯：
```rust
if let Some(&until) = self.reject_cooldown_until_ms.get(sym) {
    if ctx.timestamp_ms < until { return vec![]; }  // ← 整 tick 略過 cross 偵測
}
```

Post-fix signal.rs:157-172：
```rust
if let (Some(&entry_until), Some(&close_until)) = (
    self.reject_cooldown_entry_until_ms.get(sym),
    self.reject_cooldown_close_until_ms.get(sym),
) {
    if ctx.timestamp_ms < entry_until && ctx.timestamp_ms < close_until {
        return vec![]; // 兩 side 都 active 才 short-circuit
    }
}
```

### 對抗反問
1. 「pre-fix 是『entry **或** close cooldown active 就 short-circuit』；post-fix 是『entry **且** close cooldown active 才 short-circuit』 — 行為改變」
2. 「行為改變 desired：post-fix 修了 silent degradation；但 invariant 需明確驗 ` SAFETY 不變量：entry-only / close-only cooldown 不在此處 short-circuit，必延後到 would_open 已知後 per-side gate 處理；違反 = 回到 BB-MF-3 silent degradation 反模式` — 註釋寫了，但 invariant test 是否覆？」
3. 「test #6 test_grid_short_circuits_when_both_cooldowns_active 驗的是 **兩 side active 才 short-circuit** 部分；invariant 反向驗 **單 side active 不可 short-circuit** 是 test #1 + #2 隱式驗 — 但 test 不直接 grep 「short-circuit not triggered」，間接靠 intent 數量 > 0 推斷」

### 嚴重性 = MEDIUM
邏輯改動正確，註釋 invariant 寫了；test 覆蓋是「行為導向」非「invariant 導向」（不直驗 short-circuit fn 入口 / 出口 hit count）。未來 refactor signal.rs 容易回退（短路條件改回 `||` 也能 pass test #1/#2，因為改回後沒進入 short-circuit 而是進 per-side gate）。

### 建議
- 直驗 short-circuit 路徑被 hit：unit test 加 「兩 side active → expect short-circuit path executed」 mock + assert cross_detection_called == false（需 strategy 內加 instrumentation）
- 或：spec test plan v1.2 §6.1 doc 加 invariant 描述 + test case enumeration（短期）

---

## 五、其他 finding

### LOW-1 — `arm_close_cooldown` public API 不在 Strategy trait
**位置**：`mod.rs:464-481` `impl GridTrading { pub fn arm_close_cooldown(...) }`
**內容**：commit body 自承「不放在 Strategy trait（避免影響 4 個非 grid 策略 default impl 與 Box<dyn> dispatcher）；Phase 1b 主軸如需擴及他策略另議」
**對抗反問**：「Bybit 110017 ReduceOnlyReject + maker_rejection.classify 是 cross-strategy 機制；4 個非 grid 策略（bb_breakout / bb_reversion / ma_crossover / funding_arb）也會吃 maker close reject — 為什麼不擴至 trait？」
**答**：trait default impl no-op 是 safer，但限制 close-maker-first wave 範圍只 grid_trading（spec v1.2 §3.1 確認 Phase 1b 主軸 scope 是 grid_trading）；future wave 擴 trait OK acceptable。
**建議**：commit body 已標「Phase 1b 主軸如需擴及他策略另議」— LOW 不阻 merge。
**嚴重性**：LOW — 設計選擇透明。

### LOW-2 — test #6 (short-circuit) 後半段 cross-strategy invariant 隱晦
**位置**：tests.rs line ~1640-1660 (test_grid_short_circuits_when_both_cooldowns_active 後半)
**內容**：test #6 第二階段「entry cooldown expired (150_000 ≥ 100_000) → close emission 應發送」— 但 commit body 標「本 prereq commit 不接線生產 close cooldown gate；close emission 依舊發送」 → close cooldown active 不會擋 close emission（因為 production gate 未接）。

**對抗反問**：「test #6 驗了 close 在 close-cooldown-active 時仍 emit — 因為 production gate 未接線；當 Phase 1b 主軸接線後，test #6 第二階段 expect 會反轉嗎？」
**答**：是的。test #6 是「當前 plumbing-only」行為驗證；Phase 1b 主軸接線後需 update test expectation（close emission 在 cooldown active 時走 market fallback）

**建議**：test 註釋明標「本階段測試是 plumbing-only state；Phase 1b dispatcher 接線後本 case expectation 反轉」

### P2 — §九 LOC 警告（不阻 merge）
- tests.rs: 1018 → 1322 LOC（+305 from 1017）— 警告線 800 + 但 < 2000 cap；屬 pre-existing 高 LOC test file 增量
- mod.rs: ~480 LOC（含 +73 LOC 拆 map + 註釋）
- position_mgmt.rs: ~290 LOC（含 +98 LOC arm_close_cooldown_impl）

P2 ticket：tests.rs 達 1322 → 建議拆 module 分子文件（per E2 wave 2.2 lesson 6 + W-AUDIT-7c memory 同型）

---

## 六、對抗 7 checklist

| Item | Verdict |
|---|---|
| 1. Root cause vs 表面 patch | ✅ 真解 root cause（拆 map 物理隔離）|
| 2. Lexical scope shadow | ✅ `entry_until` / `close_until` 命名分明 |
| 3. Race condition | ✅ entry/close map 各自 HashMap，無 cross-mutation；on_tick 是 strategy single-thread caller |
| 4. Backward compat | ⚠️ field rename `reject_cooldown_until_ms` → `reject_cooldown_entry_until_ms` — 但 field 是 `pub(super)` not external API；grep 確認 caller 內部僅 grid_trading/ 路徑 ✅ |
| 5. Perf regression | ✅ 兩 HashMap lookup 替代一 HashMap lookup，O(1) constant；可忽略 |
| 6. Test 強度 | ✅ 8 new test 覆 spec §6.1 dispatch table + 隔離不變式 + saturating overflow + multi-symbol isolation；MEDIUM-2 提示需加 invariant-direct test |
| 7. Comment / citation accuracy | ✅ commit body cite「spec v1.2 §6.1 / AMD-2026-05-15-02 §8 IMPL Prereq 6 / §5.3 Race C / §5.4 BB-MF-2」全準確；spec doc 路徑可查；無 fabricated |
| 8. §九 singleton 表 | N/A — 無新 singleton |
| 9. 跨檔影響面 | ⚠️ MEDIUM-1 dead-API（無 production caller） |
| 10. 新引入 issue | MEDIUM 2 / LOW 2 / P2 1 |

---

## 七、Multi-session race incident（治理層面）

commit body 明標「sibling 12-agent audit session repeatedly stashed + silently dropped this work (3 race events 2026-05-16 01:35-01:48)」；E1 從 dropped stash refs `0a9d86d2` / `8460bd3f` recovery — 此屬 multi-session race 治理問題，**不影響本 review verdict**（recovered 代碼正確）但需 PM 補記：
- 多 CC session memory race（per memory project_multi_session_memory_race）SOP 是否需強化「stash 不可 silently drop other session WIP」？
- Wave 2b recovery 是 fragile path（依賴 git stash ref ttl）；建議 multi-agent dispatch SOP 加「stash discovery + cross-session diff」preflight

---

## 八、結論

**APPROVE-CONDITIONAL → PASS to E4** · 0 BLOCKER / 0 HIGH / 2 MEDIUM / 2 LOW / 1 P2

BB-MF-3 真解 root cause（entry/close cooldown 物理隔離），8 unit test 覆蓋 spec §6.1 dispatch table；commit body 透明標「plumbing-only prereq」是 acceptable governance pattern。

### Pushback（建議補 follow-up，不阻 merge）
1. **MEDIUM-1** — 開 `P1-BBMF3-WIRE-1` follow-up ticket：Phase 1b 主軸接 `arm_close_cooldown` from event_consumer + close emission 查 `reject_cooldown_close_until_ms`
2. **MEDIUM-2** — short-circuit invariant 加 invariant-direct test（或 spec v1.2 §6.1 test plan 明標）

### Follow-up（不阻 merge）
- **LOW-1** — `arm_close_cooldown` 未來擴 Strategy trait 評估（cross-strategy maker reject）
- **LOW-2** — test #6 註釋明標「Phase 1b 接線後 expectation 反轉」
- **P2** — tests.rs LOC 1322 → 拆 module 分子文件

### Multi-session race
- PM 補記 multi-session race protocol（per memory project_multi_session_memory_race）+ SOP 強化「stash 不可 silently drop other session WIP」

### Retroactive caveat
commit `27f02a07` 自承 E2 review chain breach（multi-session race 中 sibling session 修了/驗了 BB-MF-3 但 silently dropped；27f02a07 是 recovery commit）。本 retroactive verdict APPROVE-CONDITIONAL；治理 chain breach 需 PM 補救路徑 + multi-session race SOP 強化。
