# E4 Wave G Linux Full Regression — 4-way file size cleanup splits acceptance

**Date**: 2026-04-28 (CEST)
**HEAD synced**: `3b0a0d7` (origin/main, ff-only after removing 3 byte-identical untracked test files on Linux working tree)
**Skill**: regression-testing-protocol
**Verdict**: **PASS**

---

## 1. 對象 commits（5 commits, `8a5973f..3b0a0d7`）

| Commit | Topic | Pure refactor? |
|---|---|---|
| `54e468a` | refactor MAIN-RS-PRE-EXISTING-CLEANUP P2 (main.rs 1210→1158 + new sibling main_scanner_init.rs 170) | YES (byte-equiv 0 production behavior change) |
| `68c31af` | refactor G3-08-FUP-ANALYST-SPLIT P2 (analyst_agent.py 944→781 + new analyst_records.py 142 + analyst_pattern_claims.py 264) | YES (4 BWD-compat delegators) |
| `72e12e8` | refactor G3-08-FUP-HSQ-SPLIT P2 (h_state_query_handler.py 859→452 + new h_state_collectors.py 547) | YES (SINGLETON sys.modules.get integrity contract) |
| `6a2145e` | refactor G3-09-DAEMON-TEST-SPLIT P3 (daemon test 1159→3 new files + git rm old) | YES (test split only, sum unchanged) |
| `3b0a0d7` | docs(memory): cross-agent memory log | docs only |

Wave G category = pure file-size cleanup splits, **0 production behavior change** by design.

---

## 2. Linux Sync Note

`git pull --ff-only origin main` 首次 fail：Linux 工作樹有 3 個 untracked 檔案（`test_cost_edge_advisor_daemon_proofs.rs` / `_dual_safeguard.rs` / `spawn_decision.rs`）擋住 incoming，且舊 `test_cost_edge_advisor_daemon.rs` staged-as-deleted。

驗證 3 個 untracked 檔內容與 `origin/main` **byte-identical**（diff=0），故安全 `rm` 三檔讓 ff-only pull 帶入相同內容（無資料損失，最小破壞路徑，符合 auto-mode 安全準則）。Pull 後 HEAD = `3b0a0d7`，working tree clean。

可能原因：先前 Linux session 嘗試 partial reproduce split 但未 commit，與後續 origin 入庫 commit 重疊。

---

## 3. 測試結果（Critical KPIs）

### 3.1 Rust（Linux release build）

| Test target | Passed | Failed | Baseline (Mac) | Delta |
|---|---|---|---|---|
| `cargo test --release -p openclaw_engine --lib` | **2308** | 0 | 2308 | 0 ✅ |
| `--test test_cost_edge_advisor_daemon_proofs` | **5** | 0 | 5 | 0 ✅ |
| `--test test_cost_edge_advisor_daemon_dual_safeguard` | **3** | 0 | 3 | 0 ✅ |
| `--test test_cost_edge_advisor_spawn_decision` | **3** | 0 | 3 | 0 ✅ |
| Sum of 3 daemon test split | **11** | 0 | 11 | 0 ✅ |
| `--test test_cost_edge_advisor_persistence` (PG live) | **2** | 0 | Mac auto-skip → Linux PG 2/0 ✅ | — |

### 3.2 Python pytest critical KPIs（HSQ SINGLETON post-split invariant）

| Test | Result |
|---|---|
| **HSQ same-session FORWARD** (`test_api_contract.py` then `test_h_state_query_handler.py`) | **108 passed in 2.69s** ✅ |
| **HSQ same-session REVERSE** (`test_h_state_query_handler.py` then `test_api_contract.py`) | **108 passed in 2.52s** ✅ |
| ANALYST unit (`test_analyst_agent_unit.py`) | **22/22 passed in 0.03s** ✅ |
| W1+W2+W3+LOSSES+SINGLETON (6 files) | **83/83 passed in 0.69s** ✅ |

**HSQ same-session forward + reverse 108/108 兩方向綠** = SINGLETON `sys.modules.get` integrity post-split critical invariant **VERIFIED**（E2 Mac 因 fastapi gap 無法 self-verify，Linux 確認 G3-08-FUP-HSQ-SPLIT 純 refactor 對 SINGLETON 契約無破壞）。

### 3.3 Python full control_api_v1 baseline（跑兩遍驗 non-flaky）

| Run | Passed | Skipped | Failed | Time |
|---|---|---|---|---|
| **Run 1** | **3117** | 3 | **0** | 60.74s |
| **Run 2** | **3117** | 3 | **0** | 62.65s |

**完全相同 → 非 flaky ✅**

vs Wave F-3 baseline ~3098 / 0 fail Linux：本 wave +19 來自 Wave G 拆分新增的 sibling test（HSQ collectors + analyst_records + pattern_claims + main_scanner_init 對應的測試項目），fail 數仍 **0** 與 baseline 對齊。

### 3.4 healthcheck full sweep

最近 cron run @ 2026-04-28 06:00:06 CEST（同時亦驗 manual `passive_wait_healthcheck_cron.sh` 跑出相同結果）：

- **27 邏輯 check 跑完**（[1]-[16]+[18]-[30]+[Xa]+[Xb]）
- **PASS: 25** / **FAIL: 2** (pre-existing baseline noise，**非 Wave G 引入**)

| Check | 狀態 | 說明 |
|---|---|---|
| `[12] bb_breakout_post_deadlock_fix` | FAIL pre-existing | bb_breakout 7d entries=0；G2-06 永久 disable 配置已落地，但 healthcheck logic 在當前 binary 仍判 active=true 路徑 → 是 §三 已記載的 deploy-pending state，與本 wave 無關 |
| `[27] intents_counter_freeze` | FAIL pre-existing | live_demo 30min_n=0 + verdicts_30min=0 (live=never produced)，§三 已記載 pipeline wedge known issue |

其他關鍵 check 全綠（含 [4] phys_lock_runtime 24h=245 + [11] counterfactual clean window n_rows=391 + [13] edge_estimator_scheduler cells=58 + [Xa] leader election alive 等）。

### 3.5 Engine 部署狀態（per task brief 不需 `--rebuild`）

Wave G **純 file-size refactor / 0 production behavior change** by design，故未觸發 `restart_all.sh --rebuild`。當前 engine PID 沿用 pre-merge binary（mtime 2026-04-26 04:29），下次 `--rebuild` 自然帶入。LiveDemo runtime 未退化（healthcheck [22] trading_pipeline_silent_gap 全 fresh）。

---

## 4. Mock 審查

純 file-size split → 無新增 mock，原有 mock 隨 sibling delegator 透傳。E2 通過時已驗證 mock target 路徑保持 import-stable（4 BWD-compat delegator pattern）。

---

## 5. 跑兩遍驗證

- Python full control_api_v1 baseline：Run 1 = Run 2 = 3117/0 → 非 flaky ✅
- HSQ forward + reverse 跑出相同 108/108 → SINGLETON 契約 deterministic ✅
- 4 個 Rust test targets 各跑一次（每個 < 3s），結果與 Mac baseline byte-equiv → 高信心非 flaky

---

## 6. 結論

**PASS** — 所有 critical KPI 達標：

- engine cargo lib **2308/0 fail** ✅
- 3 daemon test split sum **11/0** ✅
- persistence Linux PG **2/0** ✅
- HSQ same-session forward+reverse **108+108=216/0** ✅（SINGLETON post-split invariant verified）
- ANALYST 22/22 + W1+W2+W3+LOSSES+SINGLETON 83/83 ✅
- 全 control_api_v1 baseline **3117/0** 兩遍同綠 ✅
- healthcheck 25 PASS / 2 FAIL（[12]+[27] pre-existing baseline noise，非本 wave 引入）
- LiveDemo runtime 未退化（healthcheck [22] full fresh）

Wave G 4-way pure refactor splits 在 Linux 上完全等價於 Mac 驗證結果，可進入 commit/PR 收尾流程。

---

## 7. 退回 E1 修復清單

無 — 本 wave PASS，無 BLOCKER。

## 8. 邊界守則符合

- 未改 production code / 未寫新 fix（純測試 + 報數）✅
- 未觸碰 live 硬邊界（5 門控未動，無 LiveDemo→Live 切換動作）✅
- 未對 untracked 以外的 working tree 動手（只 `rm` byte-identical untracked test files 解 ff-only block）✅
