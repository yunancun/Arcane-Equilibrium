# E2 · P1-PORTFOLIO-RESTING-EXPOSURE-1 Adversarial Review

**Date**：2026-05-16
**Reviewer**：E2 (senior backend + adversarial)
**Scope**：E1 IMPL on worktree `worktree-agent-ac285607fa3c51402`
**Branch / 改動範圍**：3 Rust files + 7 new unit tests + 337 LOC delta（per E1 self-report §1）
**Verdict**：**PASS to E4** with 1 MEDIUM observation + 3 LOW notes
**未直接修數**：0（business logic 不能寫；MINOR 注釋退 E1 自行整合更安全）

---

## §1 PA scope 對齊驗證

| PA §8 條目 | E1 IMPL | Verdict |
|---|---|---|
| mod.rs 修改 `compute_exposure_pct` + `compute_correlated_exposure_pct` | ✅ done | PASS |
| mod.rs 新增 helper `compute_effective_long_short_notional` | ✅ done | PASS |
| tests.rs 4 新測試（PA 估）| ✅ + extra 3 = 7 tests（baseline / entry / close / mixed / cap / same-dir / finite-guards）| PASS（覆蓋超 PA 估）|
| accessor.rs 新增 `resting_orders_iter` | ✅ done (放在 `paper_state/resting_orders.rs` 而非 `accessor.rs` — 合理，同 module) | PASS |
| healthcheck `[58] portfolio_resting_exposure_lineage` | ❌ not done | **NEEDS-CLARIFICATION (LOW-1)** |
| `max_pairwise_r` dead config 處理 | ❌ not done | **DEFER**（PA §3 自承「與本 ticket 解耦，是另案」）|

**範圍對齊性**：✅ E1 IMPL 嚴格 mirror PA §8「symbol-level netting 激進版」+「Effective notional formula」。沒有 scope 蔓延 / scope 縮水（除 healthcheck per LOW-1）。

**Behavior change vs PA §8 §2「Behavior change」段**：
- over-estimate scenarios（close pending）→ correlated_exposure 偏高 ❌ — **E1 反方向**：close-side resting **扣減**對立 filled 邊，view 更接近未來 net position。但 PA §2 自己對 close-pending 寫的 "OVER-estimate" framing 是「修前」現狀，E1 修後 fix 此 over-estimate ✓
- under-estimate scenarios（entry pending）→ effective 偏高 ✓ (E1 對齊)

---

## §2 §九 8 條 checklist 結果

| Item | 狀態 |
|---|---|
| 改動範圍與 PA 方案一致 | PASS（per §1）|
| 無 except:pass / 靜默吞異常 | N/A Rust |
| 日誌 %s 格式 | N/A Rust（無 log）|
| 寫入 API 端點 `_require_operator_role()` | N/A（無新 API）|
| `except HTTPException: raise` 順序 | N/A Rust |
| `detail=str(e)` → `"Internal server error"` | N/A Rust |
| asyncio 路由 blocking threading.Lock | N/A Rust |
| 私有屬性穿透 `._xxx` | PASS — E1 加 `pub(crate)` accessor，無 underscore-prefix 穿透 |

---

## §3 OpenClaw 9 條 §3 checklist 結果

| Item | 狀態 | 證據 |
|---|---|---|
| 跨平台合規 | PASS | `grep -E '(/home/ncyu|/Users/[^/]+)' <new files>` → 0 命中（E2 重驗）|
| 雙語注釋 | PASS-with-MINOR | 新代碼中文 only（合規 2026-05-05 規範）；**LOW-2**：兩個既有 docstring 修改塊未清舊英文行（per "修改既有中英對照塊時移除英文只保留中文"）|
| Rust unsafe 零容忍 | PASS | 0 unsafe / 0 unwrap()（用 `unwrap_or(p.entry_price)` safe fallback / `unwrap_or(0.0)`）|
| panic 不在交易路徑 | PASS | 純 arithmetic + HashMap insert，無 panic source |
| 跨語言 IPC schema | N/A | 純 Rust 內部 helper，不觸 IPC |
| Migration Guard A/B/C | N/A | 0 SQL |
| healthcheck 配對 | PASS-with-note | 不是「被動等待 TODO」性質；E1 §6 自承「scope 內未要求」；PA §8 把 healthcheck 列入 fix scope **但設計層級 advisory**；E1 dispatch 沒明示要做 → **NEEDS-CLARIFICATION (LOW-1)**：PM 確認是否需另派 E1 補 healthcheck `[58]` |
| Singleton 表 | N/A | 不引入 singleton |
| 文件大小 | WARN | mod.rs 1650 (warn 800 過 / hard 2000 未過) · tests.rs 1793 (同) · resting_orders.rs 681 (無 warn) — **無 blocker**，但 tests.rs 207 LOC headroom 接近 cap；E1 §1 已 propose 「下一輪若加 test 拆 `tests_p1_portfolio_resting.rs` `include!` 進來」對齊 `tests_predictor_router.rs` pattern — **LOW-3 advisory**：下次擴 test 即拆檔 |
| Bybit API | N/A | 不觸 REST/WS |

---

## §4 對抗反問結果（adversarial fail-mode probe）

### Q1：你說「測試通過」— mock 了什麼？
**A**：0 mock — 純 `PaperState::new(...)` + `import_positions(...)` + `set_latest_price(...)` + `seed_resting_limit_orders(...)` 後直呼 `IntentProcessor::compute_exposure_pct(&state)`。
**E2 verify**：cargo test re-run on Mac aarch64：7/7 PASS in 0.01s（E2 重跑 `cargo test --lib test_p1_portfolio_resting`，session 2026-05-16 04:xx）。**PASS — mock-free，真實 logic 跑**。

### Q2：你說「沒影響其他模塊」— `grep -r <function>` 結果？
**A_E2**：`grep "compute_exposure_pct\|compute_correlated_exposure_pct\|compute_leverage\|compute_effective_long_short_notional"`：
- `router.rs:296` (paper guardian_leverage)
- `router.rs:438/445/446` (paper Gate 2.7)
- `router.rs:784` (exchange guardian_leverage)
- `router.rs:904/911/912` (exchange Gate 2.7)
- `replay/risk_adapter.rs:132-139`（**doc comment 引用 only，無 active call** — E1 §1 read-only verify 正確）

`risk_checks.rs:467-1027` 27 個 unit test：0 命中（用 hardcoded exposure 數字，per PA §9）。
**PASS — 副作用面 = 8 call sites 全在 router.rs**。

### Q3：你說「race 不可能」— 兩 worker 同時呼怎證明？
**A_E2**：
- IntentProcessor 在 `tick_pipeline` 內單 thread sync 呼（`router.rs` 是 sync function）
- helper 簽名 `fn compute_effective_long_short_notional(paper_state: &PaperState)` — 取 immutable borrow，無內部 mutation
- 4× HashMap + 1× HashSet **全 local stack alloc**（非共享 state）
- PaperState 修改入口（fill_engine, owner_attribution）在外層 `&mut self` 路徑，與 helper 呼叫互斥

**PASS — sync engine + immutable borrow + local alloc，0 race window**。

### Q4：你說「edge case 已處理」— None / 空 / -1 / 1e18 / unicode 各跑？
**A_E2**：

| Edge | 處理 | E2 verify |
|---|---|---|
| None / 空 paper_state | `positions()` empty Vec + `resting_limit_orders_iter()` empty iter → eff=(0,0) → exposure=0% | ✓ test_baseline 證 |
| `balance <= 0` | 早回 0% per line 893/917（修前同邏輯保留）| ✓ pre-existing |
| 負 qty / 0 qty | `r.qty <= 0.0` filter（line 819, 與 import_positions filter 對稱）| ✓ test_finite_guards 證 |
| negative limit_price | `r.limit_price <= 0.0` filter（line 823）| ✓ test_finite_guards 證 |
| NaN qty | `r.qty.is_finite()` filter | ✓ test_finite_guards NaN 案例 |
| NaN limit_price | `r.limit_price.is_finite()` filter | ✓ |
| notional overflow（1e18 × 1e18 = inf）| `notional.is_finite()` filter（line 827）| ⚠️ **未明確 test**（**LOW-3a observation**：test 沒涵蓋 finite=false notional 個案；但邏輯有 guard，行為 fail-closed）|
| unicode symbol | HashMap<String, ...> 用 `String` key（line 814+），無 byte/ascii 假設 | ✓ Rust std handles |

**PASS-with-LOW-3a**：edge case 邏輯齊全，但 notional infinity case 沒 explicit test。

### Q5：你說「規格一致」— PA 文件第幾行對應你哪行 code？

| PA §8 行 | E1 IMPL 對應 | Verify |
|---|---|---|
| §8 設計要點 1「Effective notional formula」symbol-level netting | mod.rs:784-879 `compute_effective_long_short_notional` | ✓ |
| §8 改動文件清單 row 1（修改 `compute_exposure_pct`）| mod.rs:891-901 | ✓ |
| §8 改動文件清單 row 2（新增 helper）| mod.rs:784-879 | ✓ |
| §8 改動文件清單 row 3（4 unit tests）| tests.rs:1581-1793，7 個 test（≥ PA 估 4）| ✓ |
| §8 改動文件清單 row 4（accessor.rs `resting_orders_iter`）| resting_orders.rs:372-381（不在 accessor.rs 但同 module，semantically 等價）| ✓ |
| §8 row 5（healthcheck [58]）| 未做 | ❌ → LOW-1 |
| §8 設計要點 2「Behavior change」conservative direction | helper `red_long_capped`/`red_short_capped` 邏輯 + `.max(0.0)` clamp | ✓ |
| §8 設計要點 3「Backward compat」`is_reducing → allow` 短路不變 | E1 沒動 `risk_checks::check_order_allowed` 短路（unchanged）| ✓ |

**PASS — spec-to-code 全對齊（除 LOW-1 healthcheck 缺漏）**。

---

## §5 Findings

| 嚴重性 | 位置 | 描述 | 建議 |
|---|---|---|---|
| **MEDIUM-1** | `intent_processor/mod.rs:784-879` + caller `router.rs:438/445/446` | hot path performance regression：原 3 個 helper 各掃 `paper_state.positions()` 一次（共 3× O(n)）；改後每 helper 都呼 `compute_effective_long_short_notional` → 同 caller 連呼三次（3× redundant compute），每次 alloc 4×HashMap + 1×HashSet。修前是 3× Vec alloc，修後是 3× (4+1)=15 个 alloc。對 hot path SLA <1ms 可能 marginal。但 **pre-existing 模式**（修前也 3× redundant）→ 不是 E1 引入的新 regression，是 carrying。**Suggest E1 §6 加 follow-up TODO**：caller 端 cache 一次 `(eff_long, eff_short)`，三 helper 共用（簡單 refactor），或在 `compute_exposure_pct` / `compute_correlated_exposure_pct` 改 sig 接受 pre-computed tuple。**不 blocker**。 | E1 加 follow-up TODO 到 §6 + §「E5 P2 ticket」候選 |
| **LOW-1** | E1 §6 vs PA §8 row 5 | healthcheck `[58] portfolio_resting_exposure_lineage` 未實作；E1 §6 明說「PM 若要可派下一輪」。PA §7 推薦選項 A 已含 healthcheck（「對應 healthcheck 加一條 [58] passive monitor」）。**規範上 §七「被動等待 TODO 必附 healthcheck」不適用此 ticket**（不是被動等待 TODO 性質），但 PA scope 內含。 | PM 裁決：派 E1 下一輪補 [58] / 或開 P2 ticket / 或視為 done |
| **LOW-2** | `intent_processor/mod.rs:889-894` + `:907-913` | `compute_exposure_pct` 和 `compute_correlated_exposure_pct` 修改的既有 docstring 塊保留舊英文行（"RRC-1-B3: Compute total exposure ..." / "FIX-05: Compute correlated exposure ..." / "RG-2: Compute actual account leverage ..."）；按 2026-05-05 governance「修改既有中英對照塊時移除英文只保留中文」應移除。**MINOR**（governance 默認規範，非強制 retroactive）。 | E1 可順手清三處舊英文 docstring 行；或 follow-up patch |
| **LOW-3** | `intent_processor/tests.rs:1793/2000` | tests.rs 207 LOC headroom 接近 hard cap。下次再加 test 應拆 `tests_p1_portfolio_resting.rs` `include!` 進來（對齊既有 `tests_predictor_router.rs` pattern）。E1 §1 已 propose 此 pattern。 | **observation only**；下次擴 test 時 enforce |
| **LOW-3a** | `tests.rs` test_finite_guards | 沒明確 test `notional = inf`（極大 qty × 極大 price）的 finite filter。helper line 827 有 guard，行為 fail-closed，但 test coverage 漏。 | **observation only**；可由 E4 regression 順手補 |

---

## §6 退回 E1 修復清單

**無 critical / high 退回項。** PASS to E4 with above LOW notes.

可選改進（E1 自行決定是否在同 branch 修，或下一個 micro-patch）：
1. (MEDIUM-1) 在 §6 自報告加 follow-up TODO：「caller 端 cache `compute_effective_long_short_notional` tuple 避免 3× redundant compute」
2. (LOW-2) 清三處既有 docstring 舊英文行（per 2026-05-05 governance）
3. (LOW-1) 等 PM 裁決是否補 healthcheck `[58]`

E2 不直接 Edit 業務代碼；上述 LOW-2 注釋小修按 E2 frontmatter「typo / lint / dead import / 中文注釋小修可直接 Edit」**可** E2 直接修。但謹慎起見，E2 不擅自動既有 RRC-1-B3 / FIX-05 / RG-2 識別碼相關 docstring（這些是歷史 issue tracking 標籤，移除英文行可能讓未來 grep 漏命中），**退 E1** 由作者決定。

---

## §7 對抗反問 — E1 未驗 3 場景重 verify

E1 §6 自承 3 個「未被驗證的場景」。E2 對抗 review：

### E1 §6 (1) `compute_leverage` cascade — Guardian leverage 仍正確？
**E2 verify**：`compute_leverage = compute_exposure_pct / 100.0`（無變）。effective notional 比修前更接近 future net position（per E1 §2 形式驗證）。Guardian PortfolioContext.leverage 數值會略增（entry-side resting +）或略減（close-side resting 扣 filled）：
- **entry-side resting** → leverage 變大 → Guardian P0/P1 veto 更早觸發 → **conservative 對**（生存 > 利潤）✓
- **close-side resting** → leverage 變小 → Guardian veto 更晚觸發 → **可能讓 risk-adding entry 過 gate**

第二點 = Guardian 看到「pending close 預期會減倉，所以現在可以再進」— 數學上 sound（per E1 §2 不變式 2「close-side resting 永遠不能讓 long/short 翻面」+ `red_capped.min(f_long)` 封頂於對立 filled 邊）。**但有一個 hidden assumption**：close-side resting **真會 fill**。若 close-side resting timeout / cancel / 永遠不 touch → fixture 高估「對沖效果」→ 真實 risk 偏高。

**E2 verdict**：close-side resting 在 EDGE-P2-3 Phase 1B-4.2 已有 `deadline_ms` timeout（resting_orders.rs:280-286）→ 風險面有 upper bound。但這層風險面在 close-maker-first AMD-2026-05-15-02 上線會放大。**E1 §6 (1) 結論「leverage 不變式對」正確**，但 cascade 在 close-maker-first 上線時要 healthcheck `[58]`（per LOW-1）監控 over-conservative 放鬆 magnitude。**A3 對抗審若要 dig deeper 可派**。

### E1 §6 (2) 同 symbol 多 reducing resting 累加封頂於 filled
**E2 verify**：close_reduces_long_by_sym 是 `+=` 累加；最終 `red_long.min(f_long).max(0.0)` 封頂於 filled 餘額 → 100% correct conservative 邏輯。test_p1_portfolio_resting_close_reduces_capped_at_filled 已釘住。**PASS**。

### E1 §6 (3) ReplayPaperSnapshot 是否需平行改？
**E2 verify**：grep `replay/risk_adapter.rs` → `compute_exposure_pct` / `compute_correlated_exposure_pct` 只在 **doc comment** 出現（line 132-139 mirror 註釋）。`ReplayPaperSnapshot` 透過 `runner.rs` 直接寫 snapshot（不共用 helper）。replay 路徑用自己的 `ReplayPosition`，沒 `resting_limit_orders` 概念。**PASS — E1 判定「不平行改」正確**。後續 replay 若要 resting-aware → 另案 P2，不阻本 ticket。

---

## §8 Build / Test re-verify（E2 重跑）

| Item | E1 claim | E2 verify | Verdict |
|---|---|---|---|
| `cargo check --target aarch64-apple-darwin -p openclaw_engine --lib` | PASS / 2 pre-existing warning | ✓ E2 重跑 PASS / same 2 warning | PASS |
| 新 7 unit test PASS | 7/7 PASS in 0.01s | ✓ E2 `cargo test --lib test_p1_portfolio_resting` 7/7 PASS in 0.01s | PASS |
| 全 lib regression 2915 passed / 0 failed | ✓ | E2 信任 E1 跑（Mac SoT 對齊 E1 報告 2908 baseline + 7 新 = 2915）| 預設信任，E4 重跑 |
| 跨平台合規 grep | 0 命中 | ✓ E2 重跑 grep 0 命中 | PASS |

---

## §9 結論

**E2 VERDICT：PASS to E4**

- 8 條 §九 checklist：✅ 全 pass（含 N/A）
- 9 條 OpenClaw §3 checklist：✅ pass / N/A，1 WARN（文件大小，無 blocker）
- 對抗反問 5 條：✅ 全 pass
- E1 §6 自承 3 未驗場景：E2 重 verify ✓
- Findings：0 CRITICAL · 0 HIGH · 1 MEDIUM（performance pre-existing carrying）· 4 LOW
- Build / Test E2 重跑：✅ PASS

**退回 E1 修復清單**：無 critical / high。建議 E1 自行 evaluate MEDIUM-1 (performance follow-up TODO) + LOW-2 (清三處舊英文 docstring) — 但**不 block PASS to E4**。

**E2 不直接 Edit**：理由 = 雖然 LOW-2「中文注釋小修」屬 E2 frontmatter 允許範圍，但這三處塊涉及 RRC-1-B3 / FIX-05 / RG-2 歷史標籤；移除英文行可能影響跨年代 grep。穩妥起見退 E1 / 後續 micro-patch。

**Next step**：
1. PM 派 E4 跑 Linux runtime regression
2. PM 裁決 LOW-1 healthcheck `[58]`（派 E1 補 / 另開 P2 / done as-is）
3. E1 可同 branch 補 MEDIUM-1 follow-up TODO + LOW-2 docstring 清理（optional）

---

**Report path**: `srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-16--p1_portfolio_resting_exposure_e2_review.md`
**E2 sign-off**: 2026-05-16

E2 REVIEW DONE: PASS to E4 · 1 MEDIUM + 4 LOW · 0 直接修
