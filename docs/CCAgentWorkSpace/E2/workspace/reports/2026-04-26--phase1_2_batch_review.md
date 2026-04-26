# E2 Phase 1+2 Batch Review — 10 commits (df1d629..bd5ce56)

**日期**: 2026-04-26
**範圍**: PM 編排的 Tier 1 quick fixes (5) + Tier 2 G5 refactor (5)
**Audit chain**: CLAUDE.md §八 強制工作鏈
**E2 立場**: 對抗審核 — 找 issue 退回 E1/E5/TW，不代寫業務邏輯

---

## Executive Summary

| # | Commit | Owner | 結論 | Findings |
|---|---|---|---|---|
| 1 | `df1d629` G2-FUP-FUNDING-ARB-PAPER-SYNC | E1 | ✅ PASS | 0 |
| 2 | `0cda2d9` G9-01 Bybit dict + SSOT marker | TW (PM 代 commit) | ⚠️ PASS WITH 1 LOW | 1 LOW (TW memory 與 commit msg 不一致) |
| 3 | `405c05b` G9-03 connectivity_check env var | E1 | ✅ PASS | 0 |
| 4 | `2063386` G5-08 PA design plan | PA | ✅ PASS | 0 (純 doc) |
| 5 | `dbd4c2f` G5-08 PA memory | PA | ✅ PASS | 0 (純 doc) |
| 6 | `c2ca032` EDGE-P1b-FUP-STALE-PEAK-IPC | E1 (PM 代 commit) | ⚠️ PASS WITH 1 LOW | 1 LOW (Python wrapper 缺 negative guard) |
| 7 | `92ea90b` G1-FUP-CALIBRATOR-WARNING | E1 | 🛑 **RETURN E1** | 1 MEDIUM (banner 6/7 → 7/7 已過時) |
| 8 | `a5b6f17` G5-09 tick_pipeline tests split | E5 | ✅ PASS | 0 (commit msg test count 自身 typo, 0 prod 影響) |
| 9 | `35b9d5f` G5-09 memory + report | E5 | ✅ PASS | 0 (純 doc) |
| 10 | `cc4c2d2` G5-FUP-PASSIVE-HEALTH split | E5 | ✅ PASS | 1 LOW (checks_strategy.py 1048 line 86% 利用率) |
| 11 | `bd5ce56` G5-FUP-IPC-MOD-SPLIT | E5 | ✅ PASS | 1 LOW (verify_ipc_token 缺 empty-secret edge test, 既有 gap) |

**Result: 9 PASS / 1 PASS WITH RETURN-CONDITION (commit 7)**

**退回 E1 1 項** (commit 7 banner stale doc)。

---

## §A 跨平台合規（CLAUDE.md §七 ★★）

```bash
# 全 11 commit 跑 grep -E '(/home/ncyu|/Users/[^/]+)':
# 結果：0 matches across all commits — 所有 commit 都過 cross-platform 防線
```

✅ **全 PASS**。所有新代碼無 user-home 硬編碼路徑。

---

## §B 雙語注釋（CLAUDE.md §七 強制）

| commit | 雙語 | 評估 |
|---|---|---|
| df1d629 | TOML disable comment 中 + EN | ✅ |
| 0cda2d9 | SSOT 標記 HTML 注釋雙語 + visible blockquote 雙語 | ✅ |
| 405c05b | MODULE_NOTE / docstring / inline 全雙語 | ✅ 完整 |
| 2063386 | PA design doc 中文為主，技術術語英 | ✅ |
| dbd4c2f | memory 雙語 | ✅ |
| c2ca032 | mod.rs / handlers / tests / ipc_client.py 全雙語 | ✅ 模範 |
| 92ea90b | banner 雙語 + module comment 雙語 | ✅ 但**內容過時**（見 §C） |
| a5b6f17 | mod.rs MODULE_NOTE 雙語 | ✅ |
| 35b9d5f | memory + report 雙語 | ✅ |
| cc4c2d2 | __init__ / runner / shared / db / 9 module 全雙語 | ✅ 模範 |
| bd5ce56 | mod.rs / connection / dispatch / server / engine_routing / protocol / slots 全雙語 | ✅ 模範 |

---

## §C 範圍嚴守（scope-creep audit）

| commit | 範圍預期 | 實際 | 評估 |
|---|---|---|---|
| df1d629 | paper TOML active=false | 1 file | ✅ no creep |
| 0cda2d9 | dict path fix + SSOT | 2 file (dict + TW memory) | ✅ no creep |
| 405c05b | connectivity_check env var | 1 file | ✅ no creep |
| 2063386 | PA design plan | 1 file | ✅ no creep |
| dbd4c2f | PA memory | 1 file | ✅ no creep |
| c2ca032 | 8 wire fields IPC | 8 files | ✅ no creep — 每個檔對應 EDGE-P1b-FUP scope |
| 92ea90b | calibrator stderr warning | 1 file | ⚠️ 範圍 OK 但 commit 6 引入後 banner 已過時 |
| a5b6f17 | tests.rs split | 13 files (1 del + 12 add) | ✅ 0 production touched |
| 35b9d5f | memory + report | 2 files | ✅ no creep |
| cc4c2d2 | passive_wait_healthcheck split | 10 files | ✅ shim 36 行 + 9 module |
| bd5ce56 | ipc_server/mod.rs split | 9 files | ✅ 6 sibling + 2 file `tracing` macro re-import + handlers/teacher.rs / handlers_config.rs（commit message 已說明） |

---

## §D SQL Guard（CLAUDE.md §七 V023 postmortem）

✅ 本 batch 0 新 SQL migration（V025 是先前 G7-08 commit `743cfa9`，非本範圍）。

無 Guard A/B/C 規則應用。

---

## §E Hot-path 保留（G5 refactor 三件 — bd5ce56 / cc4c2d2 / a5b6f17）

### bd5ce56 (ipc_server/mod.rs split) — 最關鍵

✅ **patch_risk_config deep-merge byte-identical** — handlers_config.rs 邏輯保留，僅加 `use tracing::{info, warn};` 行
✅ **EDGE-P1b 8 exit_* fields** — handlers/risk.rs 邏輯不動，僅加 `use tracing::info;` 行（commit 6 c2ca032 已加 8 wire fields，commit 11 不重複）
✅ **HMAC verify_ipc_token byte-identical** — 從 mod.rs 搬到 connection.rs，邏輯保留 + 加 4 unit tests
✅ **accept loop byte-identical** — server.rs run() 與 pre-split mod.rs::run() 對應 fn body 一致
✅ **dispatch_request 完整保留** — 從 mod.rs 搬到 dispatch.rs，所有 dispatch arm 完整：update_risk_config、patch_risk_config、reload_risk_config、restore_exit_config_defaults
✅ **Re-export 完整** — mod.rs facade `pub use` (4 type) + `pub(crate) use` (10+ types) + `pub(in crate::ipc_server) use handlers::*` — 確保 handlers/* 用 `super::super::*` 仍解析所有 pre-split 名稱

**對抗反問結果**：
- Q: 「呼叫端零修改？」→ A: grep 確認 main.rs / main_boot_tasks.rs / main_pipelines.rs 仍用 `IpcServer / PerEngineRiskStores / EngineCommandChannels / JsonRpcRequest/Response`，全部從 `pub use` 解析。✅
- Q: 「macro 為何不能 re-export？」→ A: Rust macro_rules! re-export 從 glob `super::super::*` 不繼承，需 `#[macro_use]` 或顯式 `pub use crate::module::macro;` — handlers/teacher.rs + handlers_config.rs 直接 `use tracing::{info, warn};` 是 cleanest fix。✅

### cc4c2d2 (passive_wait_healthcheck split)

✅ **17+ check SQL byte-identical** — 隨機抽 `check_close_fills_24h` 對照 pre/post，SQL/exit code/return tuple 字節級一致
✅ **invocation order preserved** — runner.py 13 cursor-block check + 6 post-conn-close check，順序與 pre-split byte-identical
✅ **cron exit code 不變** — 0 (PASS/WARN) / 1 (≥1 FAIL) / 2 (DB error) 三種 path 完整
✅ **cron path stable** — shim 36 行 sys.path prepend 處理 cron 絕對路徑場景；`from passive_wait_healthcheck import main` 透過 `__init__.py` re-export
✅ **19 check_*** 全部在 `__init__.py.__all__` 列出（3 engine + 6 ipc_edge + 7 strategy + 3 derived）
✅ **Linux cron 12:40 跑 19 check 都跑通**：17 PASS / 1 WARN [11] / 1 FAIL [3]（pre-existing exit_features_writer 議題）

### a5b6f17 (tick_pipeline/tests.rs split)

✅ **120 test attributes pre = post** — pre-split tests.rs 120 個 #[test] / #[tokio::test] / #[serial]，post-split sibling 11 file 加總亦 120
✅ **0 production touched** — 13 file changed, 全部 `tick_pipeline/tests/` directory + 老 tests.rs 刪除
✅ **shared helper relocation** — make_event / make_signal 在 mod.rs 用 `pub(super)`；sibling 用 `super::make_event`
✅ **on_tick_helpers 路徑 super::super::on_tick_helpers** — 從 sibling 上兩層 = tick_pipeline，正確
✅ **cargo lib post-batch 2166 / 0 failed** — 對應 commit 11 (bd5ce56) 預期 2161 + 4 (verify_ipc_token) + 1 (c2ca032 stale_peak_ms) = 2166

---

## §F 測試覆蓋

| metric | baseline | post-batch | diff | 預期 |
|---|---|---|---|---|
| engine lib (cargo test --release -p openclaw_engine --lib) | 2161 | **2166** | +5 | ✅ +1 EDGE-P1b stale_peak_ms (c2ca032) + 4 verify_ipc_token (bd5ce56) |
| pytest ipc/risk_config/risk_view | 130 | **130** | 0 | ✅（PM 任務描述 `c2ca032` commit msg 確認） |
| cron healthcheck 19 check | 17/2W/0F | 17/1W/1F | — | ⚠️ [3] FAIL pre-existing per task description |

**Verified Linux runtime**: cargo lib 2166 / 0 failed (12:55 CEST post-bd5ce56)
**Verified cron**: 19 check 全部跑出（12:40 CEST log）

---

## §G PM 代 commit 風險（commit 2 + commit 6）

### commit 2 (0cda2d9) G9-01 — TW system reminder 誤判 → PM 代 commit

✅ **PM commit message 誠實標明**：「TW G9-01 to audit lineage」+ 「Code↔dict drift verified: Rust position_manager.rs:307-335 already uses correct /v5/position/confirm-pending-mmr」
✅ **獨立 grep 驗證 PM 聲明**：position_manager.rs:307-335 確實使用 `confirm-pending-mmr`；Python 0 usage（grep 完整 src tree 0 hits）
✅ **TW memory 也記錄 incident 並標 G9-01 修正項**

⚠️ **LOW finding (0cda2d9-LOW-1)**：TW memory 第 6 行寫「未檢驗 code↔dict drift。建議 PM 後續派 E1 grep position_manager.rs:327 確認」— 但 PM commit message 已 grep 驗證並標明「Code↔dict drift verified」，**TW memory 與 commit message 不一致**。
- 影響：未來 TW agent 接手讀本 memory 可能誤以為 drift 仍未驗證
- 0 production 影響（純 doc inconsistency）
- **建議**：下次 TW 接手時 update memory 第 6 行 strikethrough 或補注「PM 0cda2d9 commit 已驗證 drift, 此項已 close」

### commit 6 (c2ca032) EDGE-P1b-FUP-STALE-PEAK-IPC — E1 留 staging dir → PM 代 commit

✅ **PM commit message 誠實標明**：「PM apply staging → in-place + commit (E1 sub-agent 將改動留 staging dir 等 review；PM 經確認 cargo + pytest 已 PASS 後代 commit)」
✅ **獨立 grep 驗證 8 site 全改到**：tick_pipeline/mod.rs ✅ event_consumer/handlers/mod.rs ✅ event_consumer/handlers/risk.rs ✅ ipc_server/handlers/risk.rs ✅ 4 個 handlers_paper_cmd_tests.rs ✅ exit_config_ipc_tests.rs ✅ ipc_client.py ✅
✅ **u64 → i64 cast 安全性**：default 60_000、validate() 拒 < 0 + apply_patch 原子 fail-closed → 任何極端值都 fail-closed
✅ **restore_exit_config_defaults 7→8 同步**：fields_restored array +1 / baseline_values +1 / toml_only_fields_skipped 從 2 → 1 (only shadow_enabled remains)
✅ **+1 dedicated round-trip test (`test_ipc_risk_update_apply_exit_stale_peak_ms_round_trip`)**：u64 wire ⇒ i64 schema lossless cast / version bump / additive merge / shadow_enabled unchanged 五點驗證
✅ **既有 round-trip test 適配**：`stale_peak_ms is TOML-only` → 改為 `stale_peak_ms None in patch must keep prior value`，文字契約對齊新 IPC 路徑

⚠️ **LOW finding (c2ca032-LOW-1)**：Python `EngineIPCClient.update_risk_config` typed wrapper 對 `exit_stale_peak_ms: int | None = None` 沒做 `< 0` 預檢。
- 路徑：caller 傳 -1 → Python 包進 params dict → JSON 編碼 -1 → Rust `optional_u64` (`as_u64()`) 對負數返回 None → silent ignore 該欄位（has_any 仍可能 true 因其他欄位）
- 但**仍 fail-closed**：不會把錯值套用，只是 caller 可能誤以為「IPC 成功 = 該欄位已更新」
- 既有 design pattern：所有 7 個 `exit_*` fields 用 `optional_f64` 也有同樣 silent-ignore 行為，**非本 commit 引入的 regression**
- 建議：未來 P3 ticket 統一 IPC handler 改「存在但 cast fail = error」而非 silent None

---

## Findings 詳述

### 🛑 RETURN E1 — commit 7 (92ea90b) banner stale doc

**File**: `helper_scripts/research/exit_threshold_calibrator.py:171-197`

**Issue**:
- commit 7 (12:17 CEST) 加的 stderr banner 寫「IPC bind only covers 6/7 dimensions」
- commit 6 (c2ca032, 12:36 CEST) 加 `exit_stale_peak_ms` 進 IPC schema → calibrator 現已 7/7 IPC bind
- **commit 6 commit message 明示「Banner removable once IPC schema extended to cover dim 5」但 PM 代 commit 漏改**
- banner 第 173 行 / 184-186 行 / 188-191 行內容**全部過時**：
  - 「6 dims only」→ 應為「7 dims wired, only shadow_enabled remains TOML-only」
  - 「stale_peak_ms (dim 5: time_since_peak_ms) NOT in IPC schema」→ 已加入 IPC schema
  - 「These 2 fields require TWO-STEP write」→ 應改為「Only `shadow_enabled` requires TWO-STEP write」

**Evidence chain**:
1. commit 7 commit msg：「Tracking ticket EDGE-P1b-FUP-STALE-PEAK-IPC (P2, ~05-10 deadline)」
2. commit 6 commit msg：「本 fix 鏡射既有 7 個 exit_* 字段 pattern，新增第 8 個 wire field：exit_stale_peak_ms」
3. commit 6 commit msg：「不處理 shadow_enabled（單獨 P3 ticket）」→ 確認剩餘 TOML-only field 只有 shadow_enabled
4. ipc_server/handlers/risk.rs:316-323 (post c2ca032)：`toml_only_fields_skipped` array 從 2 element 縮為 1 element (only shadow_enabled)
5. exit_threshold_calibrator.py:188-189 banner 仍寫「These 2 fields require TWO-STEP write」與 (4) 矛盾

**嚴重性**: MEDIUM — calibrator banner 是 operator-facing contract message，stale message 會誤導 operator 以為 stale_peak_ms 仍需 TWO-STEP write。
- 不是 CRITICAL（沒影響真實 IPC 路徑、calibrator 功能正常）
- 不是 LOW（直接面向 operator 行為決策）

**建議修法（PM 派 E1 修，E2 不直接動因為這是 operator-facing 業務文檔）**:

選項 A — **完全移除 banner**（最乾淨）：
- 刪除 lines 153-197 (banner 注釋 + APPLY_WARNING_BANNER constant)
- 刪除 lines 1018-1027 (--apply 入口印 banner 邏輯)
- 留一個 1-2 行 inline comment 在 `--apply` 入口記錄 EDGE-P1b-FUP-STALE-PEAK-IPC 已閉合（reference c2ca032）

選項 B — **更新 banner 為 7/7 reflect closed**：
```
WARNING: 1 field (shadow_enabled) is TOML-only

7 dims computed by this calibrator now ALL covered by IPC `update_risk_config`:
  1-4. est_net_bps / peak_pnl_pct / atr_pct / giveback_atr_norm
  5.   time_since_peak_ms → ExitConfig.stale_peak_ms (IPC-wired since c2ca032)
  6-7. price_roc_short / entry_age_secs

Only `shadow_enabled` (binary Phase 1a/2 toggle) remains TOML-only:
  1. Manual edit `settings/risk_config_demo.toml` [exit] section
  2. Run reload_risk_config IPC OR engine --rebuild
```

**推薦：選項 A** — 純移除（commit 6 已閉合 EDGE-P1b-FUP-STALE-PEAK-IPC，banner 設計初衷已達成）

### ⚠️ LOW (1) — commit 2 (0cda2d9) TW memory inconsistency
- 詳 §G commit 2 段
- 0 production 影響

### ⚠️ LOW (2) — commit 6 (c2ca032) Python wrapper 缺 negative guard
- 詳 §G commit 6 段
- 既有 design pattern, 非本 commit 引入

### ⚠️ LOW (3) — commit 8 (a5b6f17) commit message test count typo
- commit message 寫各 sibling 13/6/7/11/12/14/11/3/14/12/13 = 126 個 test
- 實際 grep -c 各 sibling 14/4/7/12/12/15/7/3/15/12/13 (含 #[tokio::test] / #[serial]) — pre/post 都是 120
- 0 production 影響（commit message 自身 typo）

### ⚠️ LOW (4) — commit 10 (cc4c2d2) checks_strategy.py 1048 line 86% 利用率
- 8 個 check（[10][11][12][13][14][15][16] + [Xb] 雖 Xb 在 derived 已分出）合計 1048 行
- 86% 接近 §九 1200 硬上限
- 未來新加 check 可能突破上限
- 0 立即影響，但下個 G6-04 wave 建議再拆（按 check ID 切到 sibling）

### ⚠️ LOW (5) — commit 11 (bd5ce56) verify_ipc_token 缺 empty-secret edge test
- 4 unit tests cover：valid HMAC ✅ / wrong token ✅ / invalid hex ✅ / wrong secret ✅
- 缺：empty secret / empty token / ts < 0 / extreme ts edge cases
- 既有 G-3 / SEC-08 design 問題，非本 commit 引入
- 建議：未來 SEC hardening ticket 補

---

## E2 直接 fix（typo / lint / dead import）

**0 處 fix** — 本 batch 所有 fix 候選都涉及 operator-facing 業務文檔（commit 7 banner）或既有 design pattern issue（commit 6 / 11 LOW），不適合 E2 直接動。**全退回 PM 編排 E1 後續處理**。

---

## 結論 + 推薦

**E2 verdict**: 9/10 PASS. **commit 7 (92ea90b) 退回 PM/E1 修 banner**（建議選項 A 完全移除）。

**PM 後續動作**:
1. **立即**派 E1 fix commit 7 banner（選項 A 完全移除 + 1-2 行 reference c2ca032 的 inline comment 替代）
2. **next session** TW 接手時 fix 0cda2d9-LOW-1 memory（更新「未檢驗 drift」改為「c2ca032 已驗證」）
3. **P3 future ticket**：統一 IPC handler 對 cast fail 的處理（c2ca032-LOW-1 統一 design pattern fix）
4. **G6-04 next wave**：再拆 checks_strategy.py 1048 行（按 check ID 切到 sibling）
5. **SEC hardening future ticket**：補 verify_ipc_token empty-secret / extreme ts edge tests（bd5ce56-LOW-1）

**整體判定**：除 commit 7 banner stale 外，本 batch 9 個 commit **可進入 E4 回歸**。commit 7 fix 後重新 E2 → E4 chain。

---

## Appendix：commit 順序時序與依賴

```
12:15:36 df1d629 G2-FUP-FUNDING-ARB-PAPER-SYNC (E1, paper TOML)
12:17:07 92ea90b G1-FUP-CALIBRATOR-WARNING (E1, banner) ← stale by 12:36 c2ca032
12:18:44 405c05b G9-03 connectivity_check env var (E1)
12:20:11 0cda2d9 G9-01 Bybit dict + SSOT marker (TW, PM 代 commit)
12:24:37 2063386 G5-08 PA design plan (PA)
12:25:32 dbd4c2f G5-08 PA memory (PA)
12:36:03 c2ca032 EDGE-P1b-FUP-STALE-PEAK-IPC (E1, PM 代 commit) — invalidates 92ea90b banner
12:36:49 a5b6f17 G5-09 tick_pipeline tests split (E5)
12:37:26 cc4c2d2 G5-FUP-PASSIVE-HEALTH split (E5)
12:43:45 35b9d5f G5-09 memory + report (E5)
12:53:54 bd5ce56 G5-FUP-IPC-MOD-SPLIT (E5)
```

**關鍵時序問題**：12:17 commit 7 (banner) → 12:36 commit 6 (close IPC gap) → commit 6 commit msg 已寫 "Banner removable" 但 PM 漏執行該動作。**這是 PM batch 編排的時序 hazard**：兩個邏輯耦合的 commit 因被分派給不同 E1 sub-agent + 順序提交，第二個 commit 完成沒回頭 invalidate 第一個 commit 的 stale doc。

**PM 改進建議**：對於這類「commit B 應 invalidate commit A doc」的依賴對，PM 編排時：
- 選項 A：合併兩 commit 同次 push（同 E1 sub-agent 順序執行兩個改動）
- 選項 B：commit B 完成後手動補 patch 移除 commit A 的 stale doc（如本案，banner 應在 commit 6 同時刪）
- 選項 C：commit A 設計時加 TODO 標記「remove on EDGE-P1b-FUP-STALE-PEAK-IPC close」+ 後續 ticket 提醒

---

## E2 完成簽收

- **檢視 commit 數**：10 個（不含本 review commit）
- **§A-G 7 軸 audit**：全跑
- **退回項**：1 個 MEDIUM (commit 7 banner stale)
- **E2 直接 fix**：0 處
- **驗證 metric**：cargo lib 2166 / 0 failed ✅；cron healthcheck 19 check 全跑通 ✅
- **PM Sign-off**：PASS to E4 for 9/10 commits；commit 7 fix 後重 E2 → E4
