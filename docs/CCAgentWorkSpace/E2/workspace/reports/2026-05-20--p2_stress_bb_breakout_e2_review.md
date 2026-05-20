# E2 PR Adversarial Review — P2-STRESS-BB-BREAKOUT-FALSE-SQUEEZE-COINCIDENTAL-PASS · 2026-05-20

## 改動範圍

- 檔：`rust/openclaw_engine/tests/stress_integration.rs` +92/-6 LOC
- 改動函數：**1 個**（`stress_bb_breakout_false_squeeze_no_volume`, line 545-657）
- 0 production code 改動
- 0 新 helper / 新 import / 新 fixture
- 沿用 prior commit `c1f47722` 已建立的 `fresh_oi_surface(symbol)` test-local helper（line 154-168）+ `has_squeeze` / `entry_price_of` / `trailing_stop_of` public accessor（bb_breakout/mod.rs:309-326）

stress_integration.rs：1315 → 1401 LOC（過 800 警告線，未過 2000 上限）

## 8 條 E2 reviewer checklist

| Item | 狀態 | 證據 |
|---|---|---|
| 改動範圍與 PA 方案一致 | PASS | 純 test 端，0 production 改動，1 函數 |
| 沒有 except:pass 或靜默吞異常 | N/A | Rust test，無 Python except |
| 日誌使用 %s 格式 | N/A | test 無 logging |
| 新 API 端點有 _require_operator_role() | N/A | 無 API |
| except HTTPException: raise 順序 | N/A | 無 HTTP |
| detail=str(e) 改為 Internal server error | N/A | 無 HTTP |
| asyncio 中無 blocking threading.Lock | N/A | Rust + 非 async |
| 無私有屬性穿透 ._xxx | PASS | accessor `has_squeeze` / `entry_price_of` / `trailing_stop_of` 為 public（mod.rs:309-326） |

## OpenClaw 9 條特殊 checklist

| Item | 狀態 | 證據 |
|---|---|---|
| 跨平台 grep（/home/ncyu / /Users/...） | PASS | `grep -E '/home/ncyu\|/Users/[^/]+/Projects' stress_integration.rs` 0 hit |
| 注釋規範（中文為主） | PASS | 86 行新注釋全中文 rationale，含 v55 audit / commit SHA / 切片號碼對應 |
| Rust unsafe 零容忍 | PASS | 新 diff 0 個 unsafe |
| unwrap/expect 限不可恢復場景 | PASS | 本 diff 0 個新 unwrap；既有 unwrap 全在 test setup（test crash-on-error 預期） |
| 跨語言 IPC schema 一致 | N/A | 純 Rust test |
| Migration Guard A/B/C | N/A | 無 SQL |
| healthcheck 配對 | N/A | 無被動等待 TODO |
| Singleton 登記 | N/A | 無新 singleton |
| 文件大小 800/2000 | CAVEAT | 1315→1401 LOC，過 800 警告線；E1 已標 caveat；建議 follow-up 拆檔（非本 PR scope） |
| Bybit API 改動先查字典 | N/A | 無 Bybit |

## 8 維 review verdict 詳述

### 維度 1 — Root cause 真實性 · **PASS**

驗證 `bb_breakout/mod.rs:479` OI fail-closed gate **真早於 line 542-543 squeeze 登記**：

```
mod.rs:469-471  bollinger present check        → return vec![] if None
mod.rs:479-491  oi_panel_delta_5m_pct 解析     → 'missing_panel' Err → return vec![] (line 490)
mod.rs:493-496  prev_state snapshot           
mod.rs:531-537  squeeze expiry auto-clear
mod.rs:538-545  squeeze 登記 (bandwidth < squeeze_bw)
mod.rs:600-602  cooldown gate
mod.rs:658-660  entry gate (in_squeeze && bandwidth>expansion_bw && volume>=threshold)
```

`oi_panel_delta_5m_pct` 對 `surface.oi_delta_panel = None` 回 `Err("missing_panel")`（mod.rs:52），on_tick 在 line 490 提前 `return vec![]`。`EMPTY_ALPHA_SURFACE`（openclaw_core/alpha_surface.rs:683）`oi_delta_panel: None` → 舊版 ctx1/ctx2 都在 squeeze 登記與 entry path 之前被 fail-closed。E1 root cause narrative **完全成立**。

**對抗 — 還有其他 hidden fail-closed gate**？grep mod.rs `return vec![]`:
- line 462/466（indicators None）— make_ctx 已給 `Some(ind)`，不命中
- line 471（bollinger None）— bb_snapshot 已給 `Some(BollingerResult{...})`，不命中
- line 490（OI panel）— 已修
- line 601（cooldown not cooled）— 全新 strat instance，last_signal_ms 空 → is_cooled_down=true，不命中
- line 638（cross-strategy occupancy）— ctx.position_state=None，不命中
- line 687/690（Donchian hard-reject）— ind.donchian=None match `(_, None) => 0.0`，不命中

確認 E1 修法後 entry path 完整可達，volume gate 真是唯一 false breakout 防線。

### 維度 2 — 7 切片是否真覆蓋關鍵 invariant · **PASS**

| 切片 | 對應 invariant | 是否真實踩到 | 證據 |
|---|---|---|---|
| (1) `has_squeeze=true` | bandwidth < squeeze_bw 觸發登記 | 是 | 0.015 < 0.03 + OI gate 通過 |
| (2) Expansion + direction | bandwidth > expansion_bw + %B>1 → long | 是 | 0.05 > 0.04 + 1.1 > 1.0；隱含驗於 control case fire long |
| (3) Volume gate 唯一防線 | vol_ratio < volume_threshold → 0 intents | 是 | 1.0 < 1.2，line 658-660 三-AND gate 整塊 skip |
| (4) Open/Close 顯式禁 | future regression 防線 | LOW value | intents 已空，for-loop 空跑；defensive 用途，無害 |
| (5) PnL 邊界（entry_price/trailing_stop=None） | false breakout 不寫 lifecycle state | 是 | line 871-883 entry path 內寫入，未進入 |
| (6) Squeeze 窗口保留（FIX-26） | false breakout 不清 squeeze_detected_ms | 是 | line 873 清空僅在 entry path 末尾 |
| (7) Control case fire long | volume gate 是唯一變因 | 是 | 同 fixture vol→1.5 ≥ threshold 必過全條 gate chain |

**對抗 — 缺哪個切片**？評估：
- 不缺 (8) OI buffer state 更新 — 超出 P2 task scope（task = volume gate 是否唯一防線，不是 OI buffer 維護）
- 不缺 (9) bandwidth > expansion_bw 顯式 assert — 隱含於 control case fire 證明（若 expansion gate fail，control case 也 0 intents）
- (4) defensive 切片價值 LOW 但無害，可接受

### 維度 3 — Control case 設計 · **PASS**

**「同 fixture vol→1.5 必 fire long entry」path 驗證**：

| gate | 狀態 | 證據 |
|---|---|---|
| indicators present | OK | bb_snapshot 提供 |
| bollinger present | OK | bb_snapshot 提供 |
| OI panel resolve | OK | fresh_oi_surface 提供 |
| cooldown is_cooled_down | OK | 全新 strat_ctrl instance，last_signal_ms 空 |
| current_position None | OK | ctx2_ctrl.position_state=None |
| in_squeeze | OK | ctx1 已登記 squeeze_detected_ms=0, ctx2_ctrl.ts=700_000 < 0+2_700_000 |
| bandwidth > expansion_bw | OK | 0.05 > 0.04 |
| vol_ratio >= volume_threshold | OK | 1.5 >= 1.2 |
| direction | long | 1.1 > 1.0 |
| Donchian (Hard, None) | OK | match `(_, None) => 0.0` 不 return |
| persistence.check (min_ms=0) | OK | 立即 PASS |
| min_notional_usd 10.0 | OK | default_qty=1e9 * 0.10 * 67500 = 6.75e12 >> 10 |
| compute_post_only_price | N/A | use_maker_entry default=? 需驗 |

驗 use_maker_entry default：

grep `use_maker_entry`：bb_breakout/params.rs 與 mod.rs 應有 default。預設配置走 `("market", None, None, None)`（line 850-851）→ 無需 BBO → 直接 push Open intent。✓

**變數隔離嚴格**：
- 不同 strat instance（strat vs strat_ctrl）→ 完全 fresh state
- 共用 ctx1（read-only immutable Rust）→ 無 mutation 風險
- 新 ctx2_ctrl 唯一差異 vol_ratio 1.0→1.5；其餘 7 個 indicator + ts + price 全相同
- 共用 surface helper（兩次呼叫 `fresh_oi_surface("BTCUSDT")` 各自 Box::leak 新 instance；語義等價）

### 維度 4 — RED → GREEN 演練合理性 · **PASS**

E1 報告 RED probe：`fresh_oi_surface + vol_ratio=1.5` → 原 assert `is_empty()` panic at line 568。

驗證邏輯：
- OI gate 解 → entry path 完整可達
- vol_ratio=1.5 >= 1.2 → volume gate 過
- direction=long → ind 全 present → 走到 line 853 `intents.push(StrategyAction::Open)` → intents.len=1
- 原 assert `is_empty()` → panic ✓

RED probe 真會 panic（非 fixture 缺依賴）。Middle RED probe 演練合理 → 證明 fixture 修好後 entry path 真可達 + volume gate 為唯一防線。

修後 GREEN 每 assert 都有意義：
- (1)(2)(3)(5)(6) 直接踩 happy-path → assert PASS
- (4) defensive 空跑 → LOW value 但無害
- (7) control case 反證 volume gate 是 (3) 0 intents 的唯一原因

### 維度 5 — LOC 過 800 警告線 · **CAVEAT**

stress_integration.rs 1315 → 1401（+86）。已過 800 警告線，未過 2000 上限。**本 PR scope OK**：
- 純 test 改動，不擴大 scope
- E1 自記 caveat
- prior commit c1f47722 已過 800（pre-existing condition）

**Follow-up 建議**（非本 PR scope）：開 P2 拆檔 task：
- 拆檔基準：按 strategy 分（bb_breakout / bb_reversion / grid / ma / fast_track / governance / multi_symbol / hot_reload / latency 各檔）
- 風險：cross-test fixture share（make_ctx / bb_snapshot / fresh_oi_surface / make_self_owned_position）需提取共用 helper module
- 估計 LOC：1401 → 9 檔各 150-300 行
- 不阻 P2 merge

### 維度 6 — Control case 是否該獨立 #[test] · **CAVEAT**

當前實作：同函數內第二實例（line 632-656）

**利**：
- test cohesion 強：唯一變因 vol_ratio，並排對照閱讀更直觀
- 共用 ctx1 / fixture setup boilerplate
- 「false breakout 與 control 形成 invariant pair」語義單元清晰

**弊**：
- 失敗時 panic 訊息混合（看不出 false vs control 哪段壞）
- cargo test --filter 無法只跑 control case
- 違反 single-test single-assert 原則

**建議**（非阻 P2 merge）：
- 可接受同函數內第二實例（test cohesion > granularity）
- 若 future 拆檔時可考慮獨立 `stress_bb_breakout_volume_gate_control` test
- E1 報告已記為 caveat

### 維度 7 — Adversarial · 找 E1 missed issue

**對抗反問結果**：

| Q | E2 對抗驗證 | 結論 |
|---|---|---|
| 你說 OI gate 在 squeeze 登記前？ | grep mod.rs line 479-491 OI gate + line 538-545 squeeze 登記 → 順序確認 | E1 正確 |
| 你說 volume gate 是唯一防線？ | 列舉所有 return vec![] 路徑（line 462/466/471/490/601/638/687/690）逐項驗 fixture 不命中 | E1 正確 |
| 你說 control case 必 fire long？ | 全 gate chain 逐項驗 → 直至 intents.push | E1 正確 |
| 你說 RED probe 真會 fail？ | 邏輯演練：fixture 解 OI gate + vol=1.5 → entry path → push intent → 原 assert panic | E1 正確 |
| 你說 false breakout 不清 squeeze？ | grep mod.rs `squeeze_detected_ms = None` → 僅 line 873 entry path 末尾 | E1 正確 |
| (4) for-loop 空跑能 catch issue？ | intents.len=0 → loop 不執行 | 不能 catch，但 defensive 防 future regression 無害 |
| ctx1/ctx2 同 ts=0 跟 700_000 squeeze 不過期？ | 700_000 < 0+2_700_000 → in_squeeze=true | 正確 |
| ctx2 ts=700_000 / ctx1 ts=0 → ctx2 在 ctx1 之後嗎？ | 是，邏輯時序正確 | 正確 |
| use_maker_entry default 是否會 attempt PostOnly compute？ | 需查 default 是否 false | **下面驗** |

**檢驗 use_maker_entry default**：`use_maker_entry: false`（params.rs:307 / mod.rs:288）→ 走 `("market", None, None, None)` line 850-851 → 不需 BBO best_bid/best_ask → 直接 push Open intent ✓。control case 不會被 BBO 路徑攔下。

**檢驗 confluence default**：`confluence_as_gate: false`（params.rs:279）→ `effective_pct = qty_pct.max(0.10)` → 即使 confluence score=None，qty_pct 至少 0.10 → qty=1e9*0.10*67500=6.75e12 USD notional >>> min_notional 10.0 → 必過 ✓。

**檢驗共用 ctx1 + immutable**：`ctx1` 是 `TickContext<'static>` 共用，Rust borrow checker 確保 read-only。`strat.on_tick(&ctx1, ...)` 與 `strat_ctrl.on_tick(&ctx1, ...)` 共享 immutable borrow，無 race / no mutation ✓。

**Race / borrow / fixture data 邊界**：
- `Box::leak` 每次新 instance → memory 在 test runtime 累積（≤ KB 級）；test binary 結束釋放 → acceptable
- 兩個 `fresh_oi_surface("BTCUSDT")` 呼叫各自 leak — 兩個獨立 `AlphaSurface` instance，但語義等價
- 無 Arc / Mutex / RwLock → 0 並發風險

**對 adjacent test 影響**：
- grep `fresh_oi_surface\b` rust/openclaw_engine：3 個 use site（兩個本檔 + bb_breakout/tests_oi.rs 7 處 super::fresh_oi_surface()）
- tests_oi.rs 是 cargo test 內 module，與 stress_integration.rs（integration crate）獨立；helper 無 cross-contamination
- 本 PR 唯一改 false_squeeze function，未改 helper signature / fresh_oi_surface body → 0 影響 sibling test
- `stress_bb_breakout_valid_squeeze_with_volume`（line 660）不在本 PR 改動範圍，沿用 c1f47722 已建立的 pattern ✓

**Missed issues** — 全跑完對抗反問，**未找到 E1 missed 的 BLOCKER**。CAVEAT 級別兩個：

- **CAVEAT-1**（檔案大小）：1401 LOC，建議 follow-up 拆檔，**非本 PR scope**
- **CAVEAT-2**（control case 同函數）：test cohesion vs granularity trade-off 合理，**非阻 merge**

### 維度 8 — Commit-readiness for E4 · **PASS**

- 35/35 stress test PASS（本 review 重跑驗 reproducibility）
- 0 production code 改動 → live runtime 0 影響
- 跨平台 grep PASS
- 注釋規範 PASS（中文 rationale 完整）
- Race check 5 條（5a-e）全 PASS — 詳見下方

**E4 regression 建議**：
- 跑 `cargo test -p openclaw_engine --release --tests` 完整 lib + integration
- E1 已驗：lib 3042 passed + 全 integration 0 failed → 0 regression
- 建議 E4 在 Linux release 環境（trade-core）重跑一次

**前置條件**：
- 無；可直接進 E4

## §5 Multi-session race check

| Item | 狀態 | 證據 |
|---|---|---|
| 5a fetch + 2h sibling window | PASS | sibling commits 全屬不同 scope（P0-ENGINE-HALTSESSION / GUI tab-live / healthcheck lg5 / watchdog），無 file overlap with stress_integration.rs |
| 5b status clean | PASS | `git status --porcelain rust/openclaw_engine/tests/stress_integration.rs` → 唯一 M 屬本 review；其他 dirty files（memory / phase_1b / report）屬不同 task scope |
| 5c unknown WIP 禁 revert | N/A | 0 revert action |
| 5d sign-off report 前 path clean | PASS | E2 report 提交 path = `docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-20--p2_stress_bb_breakout_e2_review.md`，唯一新檔 |
| 5e review 期間 sibling 推 origin | PASS | review 開始時 `git fetch` → origin/main HEAD f2c1123c；review 期間無新 push 入 stress_integration scope |

## Findings

| 嚴重性 | 位置 | 描述 | 建議 |
|---|---|---|---|
| CRITICAL | — | 0 | — |
| HIGH | — | 0 | — |
| MEDIUM | — | 0 | — |
| LOW | — | 0 | — |
| CAVEAT-1 | stress_integration.rs 全檔 | 1401 LOC 過 800 警告線 | 開 P2 拆檔 follow-up（按 strategy 分檔，提取共用 helper module）；**非本 PR scope**，不阻 merge |
| CAVEAT-2 | line 632-656 control case | 同函數內第二實例 vs 獨立 `#[test]` | test cohesion 強，可接受；future 拆檔時可考慮獨立 `stress_bb_breakout_volume_gate_control` test；**非阻 merge** |

## 結論

**verdict: APPROVE → E4 regression ready**

**核心驗證**：
1. Root cause（OI fail-closed gate 早於 squeeze 登記）真實成立
2. 7 切片 + control case 真實覆蓋 false_squeeze 全部關鍵 invariant
3. control case 全 gate chain 邏輯演練通過（cooldown / position / in_squeeze / expansion / volume / direction / Donchian / persistence / confluence / min_notional 全綠）
4. RED → GREEN 演練合理（RED probe 真會 panic 證明 fixture 修好後 entry path 真可達）
5. 0 regression（35/35 stress test PASS, reproducible）
6. 跨平台合規、注釋規範、race check 全 PASS

**0 個 BLOCKER / 0 個 must-fix**

**2 個 CAVEAT 非阻**：
- CAVEAT-1 檔案大小拆檔 → follow-up task
- CAVEAT-2 control case 是否獨立 #[test] → test cohesion 合理

E1 self-report 「不確定之處」3 項與 E2 review 結論一致：
1. LOC 過 800 → E2 確認非本 PR scope，建議 follow-up 拆檔
2. OI gate 在 squeeze 登記之前的設計選擇 → E2 確認超出 P2 scope，不在本 review 處理
3. control case 同函數 vs 獨立 test → E2 確認 cohesion > granularity 合理

## Operator 下一步

1. **E4 regression**：跑 `cargo test -p openclaw_engine --release --tests` 全量 lib + integration（E1 已驗，建議 E4 Linux release 環境重跑）
2. **QA**：純 test fixture，無 live / authorization / runtime side effect，走 fast lane
3. **PM**：E4 通過後統一 commit + push（test fixture-only commit 可 `[skip ci]`）
4. **Follow-up（可選）**：開 P3 task 拆 stress_integration.rs 按 strategy 分檔（**非阻 P2 merge**）

