# E2 Adversarial Review — P1-1 stable_id helper compute_spine_ids() 抽出

- **日期**：2026-05-11
- **責任 Agent**：E2（Senior Backend Reviewer + Adversarial Auditor）
- **任務來源**：W-D MAG-084 sign-off §5 P1-1 follow-up (24-48h window)
- **被審 commit**：`b830e3fa` (E1 IMPL DONE by sub-agent a53f2538)
- **E2 inline fix commit**：`e40b2a76` (dead import lint)
- **三端 git HEAD**：Mac local + origin/main + Linux trade-core = `e40b2a76`
- **E2 verdict**：**APPROVED**（1 LOW finding E2 直接修；無 BLOCKER/CRITICAL/HIGH）

---

## 1. 改動範圍 vs PA 方案一致性

| 範圍項 | E1 自評 | E2 grep 驗證 | 結論 |
|---|---|---|---|
| 新檔 `spine_ids.rs` | 100 LOC, SpineIds struct + compute_spine_ids() + compute_filled_report_id() | 100 LOC, all 中文注釋技術詞英文，0 hardcoded path | PASS |
| `runtime_shadow.rs:72-78` (entry triplet) | 改用 helper | diff 嚴格對齊；參數順序 + prefix + suffix 字面一致 | PASS |
| `runtime_shadow.rs:454-457` (fill completion) | 改用 compute_filled_report_id | diff 嚴格對齊；suffix 字面 "shadow_filled" 一致 | PASS |
| `step_4_5_dispatch.rs:638-660` (dispatch mirror) | 改用 helper | diff 嚴格對齊；em / signal_id / verdict_id 三參數順序對 | PASS |
| `tests.rs` +175 LOC | 5 cross-module invariant test | 5 test 已 land 並 PASS | PASS |
| mod.rs 註冊 `pub mod spine_ids` | line 12 | line 11 | PASS |

**改動範圍與 PA 方案一致**，無多改無少改。

---

## 2. CLAUDE.md §九 既有 8 條 checklist

| Item | 狀態 | 備註 |
|---|---|---|
| 改動範圍與 PA 方案一致 | PASS | 見 §1 |
| 沒有 except:pass 或靜默吞異常 | N/A | 純 Rust，無 except 語法 |
| 日誌使用 %s 格式 | N/A | 本任務 0 log 改動 |
| 新 API 端點有 _require_operator_role() | N/A | 純內部 helper，無 API 端點 |
| except HTTPException: raise 在 except Exception 之前 | N/A | 純 Rust |
| detail=str(e) 已改 "Internal server error" | N/A | 純 Rust |
| asyncio 路由中沒有 blocking threading.Lock | N/A | 純 Rust |
| 沒有私有屬性穿透（._xxx）| N/A | Rust，pub struct 顯式公開 |

---

## 3. OpenClaw 9 條特殊 checklist

| Item | 狀態 | 備註 |
|---|---|---|
| 跨平台 grep（/home/ncyu / /Users/[^/]+ 硬編碼）| PASS | spine_ids.rs / runtime_shadow.rs / step_4_5_dispatch.rs / tests.rs diff 0 命中 |
| 雙語/中文注釋（2026-05-05 governance：默認中文）| PASS | spine_ids.rs 全中文注釋，技術詞保留英文（stable_id / sha256 / byte-equal）；既檔英文 module docstring 未動 |
| Rust unsafe 零容忍 | PASS | spine_ids.rs 0 unsafe block |
| unwrap()/expect() 僅限不可恢復場景 | PASS | spine_ids.rs 0 unwrap/expect |
| panic 不在交易路徑 | PASS | helper 不可能 panic（純函數調用 stable_id） |
| 跨語言 IPC schema 一致 | N/A | 純 Rust 內部 helper，無 IPC |
| Migration Guard A/B/C | N/A | 無 SQL migration |
| healthcheck 配對 | N/A | 無「被動等待 Nd」TODO |
| Singleton 登記 §九 表 | N/A | 純函數 + struct，無 singleton |
| 文件大小 800/2000 行 | PASS | spine_ids.rs 100 LOC, runtime_shadow.rs 555 LOC, step_4_5_dispatch.rs ~1804 LOC, tests.rs 1244 LOC 全 < 2000 |
| Bybit API 改動先查字典手冊 | N/A | 無 Bybit API 改動 |

---

## 4. 對抗反問結果

### Q1：byte-equal invariant 真覆蓋驗證 — 9 對 assert 是否 toy fixture？

**A**：是 white-box equivalence test fixture（fixed signal_id="sig-cohort-A-2002" / verdict_id="vrd-cohort-A-2002"），但設計合理：

- 對 deterministic sha256-based hash 函數，同 input 必同 output 的數學性質
- white-box 設計：test 直接 mirror pre-fix 字面複製代碼結構（legacy_decision_a / legacy_decision_b），assert helper 與 legacy A 與 legacy B **三方相等**
- **意涵**：只要 helper 內部 `stable_id(prefix, parts)` 呼叫的 prefix 字串、parts 順序、suffix 字面與舊代碼字面一致 → **任意 input 必 byte-equal**
- 9 對 assert breakdown：helper vs legacy_a (3) + helper vs legacy_b (3) + legacy_a vs legacy_b (3) = 9
- 額外 boundary test (line 1199-1244) 跑空字串 / 512-char / unicode / cross-engine_mode

**Verdict**：fixture 是 toy 但**證據結構是充分的**。不要求 fuzz 真實 input。

### Q2：helper 抽出 byte-equal preserve 真做到？

**A**：E2 對比三方 diff：

| Pre-fix runtime_shadow:72-80 | Helper compute_spine_ids | Pre-fix step_4_5_dispatch:638-660 |
|---|---|---|
| `stable_id("decision", &[em, signal_id])` | `stable_id("decision", &[em, signal_id])` ✓ | `stable_id("decision", &[em, signal_id])` ✓ |
| `stable_id("plan", &[em, decision_id, verdict_id])` | `stable_id("plan", &[em, decision_id, verdict_id])` ✓ | `stable_id("plan", &[em, spine_decision_id, verdict_id_for_dispatch])` ✓ |
| `stable_id("report", &[em, order_plan_id, "shadow_planned"])` | `stable_id("report", &[em, order_plan_id, "shadow_planned"])` ✓ | `stable_id("report", &[em, spine_order_plan_id, "shadow_planned"])` ✓ |

`compute_filled_report_id` vs pre-fix runtime_shadow:454-461：
- Pre: `stable_id("report", &[em, order_plan_id, "shadow_filled"])`
- Helper: `stable_id("report", &[em, order_plan_id, "shadow_filled"])` ✓

**全部嚴格 byte-equal preserve**。0 漂移風險。

### Q3：5 test 真 cross-module 還是只是 spine_ids.rs 內部 unit test？

**A**：嚴格說 5 test 是 **white-box helper equivalence test**，不是 strict cross-module integration test：

- test 寫在 `agent_spine/tests.rs`（不是 spine_ids.rs 內部 `#[cfg(test)] mod`）→ 跨 module ✓
- 但 test 仍只 call `compute_spine_ids` + `stable_id` 字面（不從 `emit_entry_lineage()` 或 `step_4_5_dispatch` 入口進入）
- **未覆蓋情境**：callsite 改錯（如 step_4_5_dispatch 端 wire 參數順序倒序）

**緩解**：
1. tests.rs line 615-953 sibling functional tests 跑完整 `emit_entry_lineage` / `emit_fill_completion_lineage` 路徑
2. cargo test 2780→2785 baseline 0 regression → sibling tests 已驗證 callsite wiring 對
3. E2 對 step_4_5_dispatch.rs:638-660 diff 直接 verify 參數順序對齊

**Verdict**：5 個新 test + sibling functional tests + diff verify 構成 test pyramid 充分證據。不要求 strict cross-module integration test。

### Q4：cargo test baseline 真不退化？

**E2 重跑 `cargo test --release --lib`**：
```
test result: ok. 2785 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.56s
```

**2785 PASS 與 E1 報告一致**。Baseline 2780 → 2785 (+5 new spine_ids tests, 0 regression) 驗證通過。

### Q5：paper_shadow 第 3 處 callsite 是否真覆蓋？

**A**：E2 全 repo grep 所有 stable_id callsite：

```bash
grep -rn 'stable_id(' rust/openclaw_engine/src/ | grep -v spine_ids.rs | grep -v tests.rs
```

結果：
- `event_consumer/types.rs:108/117/126`：注釋（///），不是真實 callsite
- `agent_spine/events.rs:280` (edge_id) / `:334` (transition_id)：單檔內部，不字面跨 module 複製
- `agent_spine/events.rs:395`：stable_id 函數本體定義
- `agent_spine/runtime_shadow.rs:302`：注釋

**結論**：no remaining literal stable_id("decision"/"plan"/"report") callsite outside helper。

PA 原文「paper shadow path」實際不存在獨立 paper-only callsite（paper engine_mode 在 emit_entry_lineage 開頭 `matches!(engine_mode, "demo" | "live_demo")` short-circuit）。E1 reality-check grep 後解讀第 3 處為 `emit_fill_completion_lineage` 是**正確的**。

**E1 沒漏改第 3 處**。

### Q6：silent id drift 防護機制評估

| 機制 | 是否實裝 | E2 評估 |
|---|---|---|
| Helper 內部 invariant（spine_ids.rs module docstring）| 是 | line 12-23 明文 3 條不變式：deterministic / cross-callsite byte-equal / suffix 隔離 |
| 5 test catch helper 內部漂移 | 是 | byte-equal assert 失敗會立刻 cargo test red |
| spine_ids.rs docstring 明文「禁字面複製」 | 是 | line 26-27：「後續所有 Spine id 計算路徑必透過本 module 落地」 |
| CI/grep rule 防止未來新 callsite 字面複製 | **否** | 沒 lint rule / regression test 攔截 |
| debug_assert! 或 proptest invariant | **否** | helper 自身無 runtime invariant assertion |

**未來 future-proof 評估**：當前 5 test + docstring 文字約束已足以 catch **helper 內部漂移**；但「他人在新 callsite 字面複製 stable_id("decision"/...) 邏輯」**未自動攔截**。

**建議（LOW priority，非 BLOCKER）**：
1. E2 future PR review 加 grep rule `grep -E 'stable_id\("(decision|plan|report)"' --exclude-dir=spine_ids.rs --exclude-dir=tests.rs` 偵測新字面複製
2. 或加 CI hook 同樣 grep

**Verdict**：當前防護機制對「P1-1 修復範圍」充分，future-proof gap 是 LOW 非 P1-1 scope。

### Q7：雙語注釋政策驗證（2026-05-05 governance change：默認中文）

**spine_ids.rs 注釋 audit**：
- Module docstring (line 1-29)：全中文，技術詞英文（stable_id / sha256 / byte-equal / helper / invariant）✓
- SpineIds struct doc (line 39-49)：全中文，技術詞英文 ✓
- compute_spine_ids fn doc (line 51-66)：全中文，技術詞英文 ✓
- compute_filled_report_id fn doc (line 81-94)：全中文，技術詞英文 ✓

**runtime_shadow.rs / step_4_5_dispatch.rs 改動處注釋**：全中文（line 65-67 + line 454-456 + line 626-636）✓

**符合 2026-05-05 governance change**。

### Q8：三端 git 同步

- Mac local HEAD：`e40b2a76` ✓
- origin/main HEAD：`e40b2a76` ✓
- Linux trade-core HEAD：`e40b2a76` (post fast-forward pull) ✓

**三端同步驗證 PASS**。

---

## 5. Findings

| 嚴重性 | 位置 | 描述 | 動作 |
|---|---|---|---|
| **LOW** | `runtime_shadow.rs:24` | `use super::events::{stable_id, ...}` 中 `stable_id` 在 P1-1 helper 抽出後變 dead import（cargo build 釋出 `warning: unused import: stable_id`） | **E2 直接修** commit `e40b2a76` |
| INFO | events.rs:280 edge_id / :334 transition_id | 仍字面構造但屬單檔 constructor 內部，不跨 module，不在 P1-1 scope | **無動作**（可未來 P2 propagate helper，如別 module 有需求） |
| INFO | CI/lint rule 防 future literal copy | spine_ids.rs docstring 明文禁止但無 grep CI hook 自動攔截 | **無動作**（LOW future-proof gap，建議 future P2 加 grep CI rule） |

---

## 6. E2 直接修動作清單

1. **`runtime_shadow.rs:24` dead import 修復**：移除 `stable_id,` from `use super::events::{...}`
   - commit `e40b2a76`
   - cargo build 18→17 warnings（消除 `unused import: stable_id`）
   - cargo test --lib spine_ids 5 PASS (baseline 2780→2785 不變)
   - 三端 push + ssh pull sync

---

## 7. 結論

**Verdict**：**APPROVED** ✓

P1-1 stable_id helper 抽出實作：
- 嚴格 byte-equal preserve（runtime_shadow + step_4_5_dispatch + fill completion 三方參數順序對齊）
- 5 個 white-box equivalence test 充分（配合 sibling functional tests + cargo test 2785 PASS）
- 跨平台 + 中文注釋 + Rust 安全代碼合規
- 三處 callsite 真實覆蓋（paper_shadow 不存在獨立 callsite 已 reality-check）
- 三端 git 同步

**1 LOW finding（dead import）E2 直接修 inline**，commit `e40b2a76` push 三端。

**進入 E4 回歸**：純 Rust 重構，pytest sibling 0 改動；建議 E4 只跑 Rust cargo test --release --lib（含 21 integration test crates）即可。

PASS to E4.

---

## 8. 完成判定回報摘要

1. **Verdict**：APPROVED
2. **byte-equal invariant 真覆蓋驗證**：9 對 assert 是 white-box equivalence fixture（fixed signal_id/verdict_id），但對 deterministic sha256 hash 函數「同 input 必同 output」+ helper 內部 callsite 結構與舊字面字面對等 → **任意 input 必 byte-equal**。fixture 是 toy 但證據結構充分。
3. **helper 抽出 preserve 結論**：PASS（runtime_shadow + step_4_5_dispatch + fill_completion 三方參數順序 + prefix + suffix 字面嚴格對齊）
4. **5 test cross-module 真假**：白盒對等性 cross-module test（不是 strict integration）。配合 sibling functional tests + 2785 baseline 0 regression 構成 test pyramid 充分證據。
5. **cargo test baseline 重跑結果**：2785 PASS, 0 failed（與 E1 報告一致）
6. **paper_shadow 第 3 處 callsite 真覆蓋**：是 — PA 原文 phrasing「paper shadow path」實際不存在獨立 callsite（paper engine_mode short-circuit），E1 reality-check 後解讀第 3 處為 `emit_fill_completion_lineage` 正確。E2 grep 全 repo 0 remaining literal stable_id callsite。
7. **silent id drift 防護機制評估**：對 P1-1 scope 充分（helper 內部 invariant + 5 test catch）。Future-proof gap = 無 CI grep rule 防新字面複製，LOW priority 非 P1-1 scope。
8. **三端 git log 同步**：Mac local + origin/main + Linux trade-core 全 = `e40b2a76` ✓

---

E2 REVIEW DONE: APPROVED · report path: docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-11--p1_1_stable_id_helper_e2_review.md
