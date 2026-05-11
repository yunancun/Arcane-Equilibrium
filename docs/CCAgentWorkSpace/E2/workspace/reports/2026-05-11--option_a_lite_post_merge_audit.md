# E2 Adversarial Audit — P0 Option A-Lite Post-Merge Review

**Date**: 2026-05-11
**Agent**: E2 (Senior Backend Reviewer + Adversarial Auditor)
**Object**: HEAD `dc8b7ffe` (5 worktree merge chain post Phase 0 `77a52796`)
**Mode**: read-only adversarial audit
**Time budget**: ≤30 min
**Verdict**: **PASS to E4** · 0 BLOCKER · 0 HIGH · 2 MEDIUM (tech debt) · 2 LOW · 1 WATCH

---

## 1. 範圍

5 並行 E1 IMPL + 主 session sequential merge：

| E1 | Commit | 範圍 |
|---|---|---|
| E1-A | `f579e479` | ma_crossover full SSoT (-371 LOC net) |
| E1-B | `6cdfe0dc` | bb_reversion full SSoT (-311 LOC net) |
| E1-C | `cbbd9c40` | bb_breakout partial SSoT (entry_price/trailing_stop/squeeze/oi_buffer 保留) |
| E1-D | `07045e99` | grid_trading cross_strategy_holds gate (+208 LOC，net_inventory 0 動) |
| E1-E | `0427346f` / `ebbcc038` | funding_arb dormant align (+17 LOC net) |

HEAD `dc8b7ffe` = main post-merge state。

---

## 2. 8 Audit Angle 對抗性結論

### A. test count 對齊驗證 — PASS

| 策略 | main HEAD focused test | E1 報告 claim | Align |
|---|---|---|---|
| ma_crossover | 63 | E1-A: 63 | ✓ |
| bb_reversion | 46 | E1-B: 46 | ✓ |
| bb_breakout | 84 | E1-C: 84 | ✓ |
| grid_trading | 50 | E1-D: 50 | ✓ |
| funding_arb | 42 | E1-E: 42 | ✓ |
| **Total full lib** | **2794** | E1-B baseline | ✓ |

各 worktree pre-merge 數字 (2792-2801) 變動可解釋（各 E1 加 acceptance test + worktree baseline drift）。Main post-merge = 2794 因為最終 sibling merge = E1-B。**沒 test shadow / 沒掉 test**。

### B. Phase 0 patch 全清驗證 — PASS

```bash
grep -rn 'PHASE-0\|Phase 0\|PHASE-0-STOP-BLEED' bb_reversion/ → 0 hit
```

E1-B SSoT 完整改造後 Phase 0 gate 已被 owner_strategy match 取代（bb_reversion/mod.rs:465-481）。

### C. W7-2/W7-3/W7-5 active code 死絕驗證 — PASS

5 SSoT 策略 active `self.positions` = 0 hit (扣注釋 + tests file)
5 SSoT 策略 active `prev_position` (excl `prev_last_trade_ms` cooldown rollback) = 0 hit
`import_positions` override 只 grid_trading + bb_breakout 保留 = PA spec exception (net_inventory / entry_price 重建)

```bash
grep -rn '\bself\.positions\b' strategies/{ma_crossover,bb_reversion,bb_breakout,funding_arb}/ | grep -v '//\|tests' → 0 hit
grep -rn '\bprev_position\b' strategies/ | grep -v 'prev_last_trade_ms\|//\|tests' → 0 hit
grep -rn 'fn import_positions' strategies/ → 3 hits (mod.rs default + grid_trading override + bb_breakout override)
```

### D. cross-strategy gate semantics 一致性 — PASS

| 策略 | gate 邏輯 | 位置 |
|---|---|---|
| ma_crossover | `ctx.position_state.filter(\|p\| p.owner_strategy == self.name())` | strategy_impl.rs:187 |
| bb_reversion | 同上 | mod.rs:467 |
| bb_breakout | 同上 (+ `if pos.owner_strategy == self.name()` in import_positions:338) | mod.rs:549 |
| funding_arb | 同上 | funding_arb.rs:398 |
| grid_trading | 3-owner whitelist `{grid_trading, bybit_sync, orphan_adopted}` | signal.rs:170-187 |

4 SSoT 策略結構完全一致：
1. `let owned = ctx.position_state.filter(|p| p.owner_strategy == self.name())`
2. match 三分支：`Some(_)` exit / `None if is_some()` cross-strategy skip / `None` entry

grid_trading 3-owner whitelist 是 PA spec exception (BLOCKER #2)，文檔註明。

### E. PaperPosition test helper 重複 antipattern — MEDIUM tech debt

5 策略 8 個 helper 內聯：

| 策略 | Helper(s) | 簽名類型 |
|---|---|---|
| ma_crossover/tests.rs | `make_paper_position(symbol, is_long, owner)` | 參數化 |
| ma_crossover/tests_a1_a2_maker.rs | `make_paper_position_a1(symbol, is_long, owner)` | 參數化（重複） |
| bb_reversion/tests.rs | `make_paper_position_bbr_with_owner(s, l, o)` + `make_paper_position_bbr_for_self_exit(s, l)` | 1 參數化 + 1 hard-code |
| bb_breakout/tests.rs | `make_owned_paper_position(s, l)` + `make_cross_strategy_paper_position(s, l)` | 2 hard-code |
| grid_trading/tests.rs | `make_paper_position_grid(symbol, is_long, owner)` | 參數化 |
| funding_arb.rs | `make_position(...)` | 多參數 |

PA spec §8.1 E1-F aggregator scope 預期抽 common helper，5 個 E1 都明確 push back 未抽。**不阻當前 deploy**，留 E1-F follow-up wave。

### F. memory.md 5 sections lossless merge — PASS

| E1 | Memory section line | Heading |
|---|---|---|
| E1-A | 8063 | `## 2026-05-11 P0 Option A-Lite E1-A — ma_crossover ...` |
| E1-B | 7982 | `## 2026-05-11 — P0 Option A-Lite E1-B：bb_reversion ...` |
| E1-C | 8028 | `## 2026-05-11 P0 Option A-Lite E1-C — bb_breakout ...` |
| E1-D | 7917 | `## 2026-05-11 P0 Option A-Lite E1-D grid_trading ...` |
| E1-E | 7944 | `## 2026-05-11 — P0 Option A-Lite Wave 1 E1-E：funding_arb ...` |

5 個 section 內容均存。Heading format 不規範化 (`—` 分隔 / `Wave 1` 中綴差異) = **MEDIUM**。不阻 deploy；follow-up 統一格式。

### G. cargo build warning 0 new — PASS

main HEAD warning count = 18 (= E1-A 報告對齊 + E1-B/C/D/E 報告也標 "18 pre-existing")

`method 'make_intent' is never used` 警告 (helpers.rs:26)：
- baseline `git show 77a52796:.../tests.rs` 有 2 次 `s.make_intent()` 調用
- main HEAD `.../tests.rs` 仍 2 次調用
- 是 `pub(super)` cross-test-mod visibility 邊界引起的 pre-P0 baseline issue

0 P0 改造引入新 warning。

### H. per-tick performance 0 regression — PASS

各策略 per-tick ctx.position_state read count：

| 策略 | reads per tick | 形式 |
|---|---|---|
| ma_crossover | 2 (filter + is_some) | borrow |
| bb_reversion | 2-3 (filter + is_some + log map) | borrow |
| bb_breakout | 2 (filter + is_some) | borrow |
| funding_arb | 2-3 (filter + is_some + log map) | borrow |
| grid_trading | 2 (filter + log map) | borrow |

ctx.position_state 由 `step_4_5_dispatch.rs:304-306` 預 inject (`Option<&PaperPosition>`)，策略無新增 HashMap query。**0 性能 regression**。

---

## 3. PA §9 三條必查

| # | 必查 | 結論 |
|---|---|---|
| 1 | exit gate `owner_strategy == self.name()` 必查 (5 策略) | **PASS** — 4 SSoT 策略 explicit filter，grid_trading 用 3-owner whitelist 為例外 |
| 2 | bb_breakout entry_price/trailing_stop/squeeze_detected_ms/oi_buffer 保留 | **PASS** — `grep -cE` bb_breakout/mod.rs = 85 hits |
| 3 | grid_trading net_inventory 不被砍 | **PASS** — mod.rs 12 + signal.rs 11 + position_mgmt.rs 10 = 33 hits |

---

## 4. CLAUDE.md §九 8 條 + OpenClaw 9 條

§九 8 條全 PASS（Rust code，多數 N/A；無 except:pass / 無 f-string log / 0 私有屬性穿透）。

OpenClaw 9 條：
- 跨平台 grep `/home/ncyu\|/Users/` = 0 hits ✓
- 雙語注釋（2026-05-05 默認中文）符合 ✓
- 0 unsafe block ✓
- 0 新 unwrap 在交易路徑（bb_breakout:841/850 pre-P0 baseline，has `is_none()` short-circuit）✓
- 0 SQL change / 0 migration / 0 healthcheck wire / 0 新 singleton ✓
- 文件大小：5 mod.rs 全 <2000；tests files 部分 >800 <2000 warn (各 E1 報告明標 acceptable) ✓

---

## 5. 對抗反問結果

| Q | A 評估 |
|---|---|
| 「測試通過 — mock 了什麼？真實邏輯有跑嗎？」 | 5 E1 acceptance test 直驗 cross-strategy owner gate (e.g. `test_bbb_does_not_close_cross_strategy_position_on_exit_signal`)，非 happy-path mock |
| 「沒副作用 — grep 結果？」 | 跨平台 grep 0 hits / active self.positions 0 hits / active prev_position 0 hits |
| 「race 不可能 — 兩 worker 證明？」 | step_4_5_dispatch.rs 預 inject ctx.position_state，5 策略 borrow read-only，無共享可變 state |
| 「edge case 已處理？」 | `position_state = None` baseline 既有 path / `is_some()` 預檢 / owner empty string 不可能 (IntentProcessor 寫入 strategy name 非空) |
| 「規格一致 — PA 第幾行？」 | E1-A:strategy_impl.rs:187-194 = PA §3.2 #1 / E1-B:mod.rs:465-481 = PA §3.2 #1 / E1-C:mod.rs:549-565 = PA §3.2 #2 / E1-D:signal.rs:170-187 = PA §3.2 #3 / E1-E:funding_arb.rs:396-432 = PA §3.2 #4 |

---

## 6. Findings

| 嚴重性 | 位置 | 描述 | 建議 |
|---|---|---|---|
| **MEDIUM** | strategies/{ma_crossover,bb_reversion,bb_breakout,grid_trading,funding_arb}/tests*.rs | 5 策略 8 個 PaperPosition test helper 內聯，簽名混合 hard-code owner 與參數化 | Follow-up E1-F aggregator wave 抽 `strategies/common/mod.rs::make_paper_position()`；其他變體 delegate；不阻 deploy |
| **MEDIUM** | E1 memory.md heading format | A/C/D vs B/E heading 不規範化 | 統一 `## YYYY-MM-DD P0 Option A-Lite E1-X — <短描述>`；不阻 deploy |
| **LOW** | E1-E commit `0427346f` 文檔 | 報告自承「sandbox denied git push」但 main HEAD 已含此 commit | Backfill push status 已 confirmed；不阻 |
| **LOW** | `make_intent` dead code warning (helpers.rs:26) | pre-P0 baseline `pub(super)` visibility 邊界 | E5 lint cleanup wave；不阻 |
| **WATCH** | PA §6.1 Phase 0 hot-fix #1 (`exit_pctb [0.2,0.8] → [0.45,0.55]`) 未採用 | Phase 0 commit `77a52796` 只實作 owner_strategy gate；exit_pctb 寬縮跳過 | Acceptable — owner_strategy gate 已治本 cross-strategy mass close；exit_pctb 寬度只影響**自家持倉** textbook mean-reversion 過早 exit (策略質量 issue 非 BLOCKER)；留策略 calibration wave |

**0 BLOCKER · 0 HIGH** — current deploy 不需 RETURN to E1。

---

## 7. 結論

**PASS to E4**

5 E1 並行 IMPL + 主 session merge 完成 P0 Option A-Lite SSoT 重構：

1. PA spec §9 三條必查全 PASS
2. CLAUDE.md §九 8 條 + OpenClaw 9 條全綠
3. 8 個 audit angle 結論 = 6 PASS + 2 MEDIUM tech debt (E1-F aggregator 未完成 + heading format)
4. 對抗反問 5 條全 PASS（非 happy-path mock；grep 驗證；race-free borrow；edge case 已處理；PA spec line-by-line 對齊）
5. 0 業務邏輯 bug / 0 race / 0 leakage / 0 shortcut / 0 spec drift

Initial 12:55 fill `grid_close_short` 回歸 +$0.133 net + 0 個 bb_mean_revert cross-close 與 audit 結論一致：P0 Option A-Lite 達設計目的，從根源杜絕 cross-strategy mass scalp。

PA 副作用清單 BLOCKER #1-3 (bb_breakout 4 fields / grid_trading net_inventory / on_external_close cleanup) 5 E1 IMPL 均正確保留；副作用 #4-7 經 audit 確認 acceptable trade-off 且實作正確。

---

## 8. Follow-up（不阻 deploy）

1. **E1-F aggregator wave**：抽 `strategies/common/mod.rs::make_paper_position()` helper，5 策略 8 個內聯 helper delegate；同次 trait doc 重寫 (PA §8.1)
2. **memory.md heading 規範化**：unified format `## YYYY-MM-DD P0 Option A-Lite E1-X — <短描述>`
3. **E5 lint cleanup**：18 pre-existing warning 處理（包括 `make_intent` dead code）
4. **策略 calibration wave**：bb_reversion `exit_pctb_lower/upper` 評估縮窄到 textbook [0.45, 0.55]（策略質量 issue，非 P0 mass close issue）

---

E2 REVIEW DONE: PASS to E4 · report path: `srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-11--option_a_lite_post_merge_audit.md`
