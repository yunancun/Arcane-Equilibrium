# OpenClaw 全程序鏈審計總報告 — 2026-04-12

> 本文件合併 12 份角色審計報告 + PA 匯總修復計劃 + PM 最終確認，共 14 份原始報告。
> 生成時間：2026-04-12
> 審計範圍：Rust openclaw_engine + Python 控制層 + GUI + 文檔 + 數據庫 + ML 基座 + Bybit API
> 總發現：58 unique findings（8 P0 · 17 P1 · 28 P2 · 5 P3）

---

## 目錄

1. [PM 最終確認報告](#1-pm-最終確認報告)
2. [PA 匯總修復計劃](#2-pa-匯總修復計劃)
3. [FA — 功能規格驗證 + Gap 分析 + 死代碼](#3-fa--功能規格驗證--gap-分析--死代碼)
4. [AI-E — AI 使用效果與可接入度評估](#4-ai-e--ai-使用效果與可接入度評估)
5. [E5 — 優化 · 精簡 · 性能 · 可讀性評估](#5-e5--優化--精簡--性能--可讀性評估)
6. [E4 — 全範圍測試審計](#6-e4--全範圍測試審計)
7. [E3 — 安全審核](#7-e3--安全審核)
8. [CC — 合規檢查](#8-cc--合規檢查)
9. [QC — 策略算法 · 風控邏輯 · 數學審計](#9-qc--策略算法--風控邏輯--數學審計)
10. [MIT — 數據庫 + ML 基座審計](#10-mit--數據庫--ml-基座審計)
11. [BB — Bybit API 兼容審計](#11-bb--bybit-api-兼容審計)
12. [TW — 文件盤查（4/1-4/12）](#12-tw--文件盤查4142)
13. [R4 — 索引完整性驗證](#13-r4--索引完整性驗證)
14. [A3 — GUI 可用性審計](#14-a3--gui-可用性審計)

---


---

# 1. PM 最終確認報告

> 原始文件：`2026-04-12--full_audit_fix_plan_pm_confirmed.md`

# PM 確認：全程序鏈審計修復計劃
# PM Confirmed: Full Pipeline Audit Fix Plan

---

## PM 簽核（PM Confirmation Header）

- **PM 確認日期**: 2026-04-12
- **審計範圍**: 12 份審計報告（FA/AI-E/E5/E4/E3/CC/QC/MIT/BB/TW/R4/A3），覆蓋安全/風控/策略/性能/測試/文檔/GUI/架構全維度
- **PA 報告位置**: `docs/CCAgentWorkSpace/PA/2026-04-12--consolidated_fix_plan.md`

### 總體評估

系統在 Phase 6 驗收後整體架構健全，三引擎並行、Reconciler 自動降級、漸進放權管線均已通過壓測和端到端驗證。58 條去重後的審計發現中，真正危及 Live 安全的 P0 問題集中在兩個維度：(a) 風控閉環缺口（FastTrack 兩個 action variant 未處理 + price_drop/margin_util 硬編 0 + exec.fast 手續費缺失），(b) 核心模組測試空白（edge_estimates 零測試、REST timeout fail-closed 未驗證、三管線並發無 e2e）。這些問題在 Paper/Demo 模式下影響有限，但 Live 模式下構成真實風險。P1 和 P2 級問題多為代碼質量、文檔衛生和策略參數化，不構成 Live 阻塞但需持續改善。當前所有活躍策略 gross edge 為負（Phase 5 PAUSED），策略重做仍是比審計修復更根本的 Live 前置條件。

### P0 修復是否同意

**同意。** 8 項 P0 全部確認為 Live 阻塞級別，優先級排序合理：

| # | FIX-ID | PM 確認 | 備注 |
|---|--------|---------|------|
| 1 | FIX-10 | **同意 P0** | IPC 安全是 Live 硬前置。panic 方案合理，但建議同時在啟動日誌中明確輸出 "HMAC enforced for Live" 確認訊息 |
| 2 | FIX-03 | **同意 P0** | ReduceToHalf/PauseNewEntries 是 Reconciler escalation 的下游動作，不處理等於 Cautious/Defensive 模式形同虛設 |
| 3 | FIX-04 | **同意 P0** | 閃崩防線完全失效。建議修復時同步清理 PNL-6 TODO（price_drop_pct 死碼決議） |
| 4 | FIX-19 | **同意 P0** | PNL-FIX-2 的 Mainnet 版本，手續費歸零直接影響 PnL 準確性 |
| 5 | FIX-13 | **同意 P0** | 208 行 9 pub fn 零測試，被 scanner + cost_gate 依賴，JSON 解析 + 除零風險 |
| 6 | FIX-14 | **同意 P0** | 硬邊界原則 #5 合規性需要測試驗證 |
| 7 | FIX-15 | **同意 P0** | 3E-ARCH 是核心架構，並發隔離性必須有 e2e 保障 |
| 8 | FIX-09 | **同意 P0** | 1 行修改，defense-in-depth，無理由延後 |

### PM 層面調整與補充

1. **Session 排期與 W22 AI 工作的協調**：PA 建議 4 天完成 P0+P1+核心 P2。PM 確認此排期但調整優先級——W22 Mon-Tue 專注 P0（Session 1+2），Wed 完成核心 P1（Session 3+5），Thu 開始 G-1 AI Agent 工作。P1 Session 4（on_tick 拆分）和 Session 6（測試第二批）可推遲至 W22 Fri 或 W23 初。P2 全部推遲至 W23+。

2. **FIX-04 與 PNL-6 合併**：FIX-04（price_drop/margin_util 硬編 0.0）和 TODO.md 中的 PNL-6（fast_track 死碼決議）是同一問題的兩面。建議在 Session 1 一起解決，避免二次修改 on_tick.rs。

3. **FIX-01/FIX-02 確認為 P2 正確**：AI Agent stub（FIX-01）和 Decision Lease Rust 接入（FIX-02）已有 W22 G-1 排程覆蓋，不應重複排程。PA 將其列為 P2 是正確判斷。

4. **測試基線更新預期**：完成 S1+S2+S3+S6 後，Rust 測試基線應從 1355 提升至 ~1396（+41 tests）。此為 PM 對 W22 結束時的最低期望。

5. **FIX-20（pre_check_order）補充**：PA 列為 P1 "標記 dangerous 或移除"。PM 補充：在 Live 模式下此函數必須被禁用或改為 dry-run 模式（不實際提交訂單）。建議加入 Session 3 一起處理。

6. **文件大小問題（FIX-08）降級確認**：13+ 文件超 1200 行硬上限是 pre-existing 技術債，PA 正確將其列為 P2。但 `on_tick.rs`（FIX-29）拆分因涉及 FastTrack 修復後的同區域代碼，應在 S1 之後儘快完成（Session 4），PM 將其視為 P1-HIGH。

### 簽核

**PM APPROVED** -- 2026-04-12

PA 綜合修復計劃整體質量優秀，去重邏輯清晰，優先級判斷準確，session 拆分務實。批准按調整後排期執行。

---

# 以下為 PA 原始報告全文

---

# PA 綜合修復計劃 — Consolidated Fix Plan
# 日期：2026-04-12
# 來源：12 份審計報告 (FA/AI-E/E5/E4/E3/CC/QC/MIT/BB/TW/R4/A3) 綜合分析
# 確認方法：P0/P1 級發現已逐一代碼驗證

---

## Part 1: 問題總覽

### 去重說明

12 份報告共產生 ~120 條發現，去重合併後剩餘 **58 條唯一問題**。以下為主要重疊：
- FastTrack ReduceToHalf/PauseNewEntries 未處理 → FA #2 = CC = E3-SEC-A01 = E5-D-01（合併為 FIX-03）
- H1-H5 AI 治理層 stub → FA #1 = AI-E = CC 原則 #11/#12/#15（合併為 FIX-01）
- 文件大小違規 → FA #9-11 = CC §2.1 = E5-R-01/R-05 = A3 §八（合併為 FIX-08）
- correlated_exposure_pct = 0.0 → QC-RG-1 = FA 已含在風控閉環（合併為 FIX-05）
- ocEsc 缺單引號 → E3-SEC-E01 = E3-SEC-B03（合併為 FIX-09）
- edge_estimates.rs 零測試 → E4 P0-#1 = FA 已涵蓋（合併為 FIX-13）
- Decision Lease Rust 未使用 → FA #3 = CC 原則 #3（合併為 FIX-02，非阻塞）
- GridTrading grid_levels dead param → QC-RG-3 = FA #8 死 config（合併為 FIX-06）

### 綜合問題表

| ID | 嚴重度 | 來源報告（Agent: 原始發現 ID [原始嚴重度]） | 問題描述 | 影響範圍 | 關鍵文件路徑 |
|----|--------|----------------------------------------------|----------|----------|-------------|
| **FIX-01** | BLOCKER | FA: #1 [BLOCKER] · AI-E: §2.4/§2.5 [Partial] · CC: 原則#11/#12/#15 [PARTIAL] | H1-H5 AI 治理層全 stub，Rust 引擎未接入 AI Agent | 原則 #3/#11/#13 | `ai_service.py`, `strategy_wiring.py` |
| **FIX-02** | MAJOR | FA: #3 [MAJOR] · CC: 原則#3 [PASS with note] | Decision Lease Python 完整但 Rust 引擎未使用 | 原則 #3 部分失效 | `decision_lease_state_machine.py`, `router.rs` |
| **FIX-03** | BLOCKER | FA: #2 [BLOCKER] · E3: SEC-A01 [LOW] · E5: D-01 [Medium] | FastTrack ReduceToHalf/PauseNewEntries 定義但未處理 | 風控閉環缺口 | `fast_track.rs:17-18`, `on_tick.rs:148-161` |
| **FIX-04** | BLOCKER | FA: #2 [BLOCKER] · E3: SEC-A01 [LOW] | fast_track price_drop/margin_util 硬編 0.0 | 閃崩/保證金危機防線失效 | `on_tick.rs:156-159` |
| **FIX-05** | P1 | QC: RG-1 [P1] | correlated_exposure_pct 永遠 0.0 | 組合級風險檢查失效 | `router.rs:179,420` |
| **FIX-06** | P1 | QC: RG-3 [P1] + H5 [P1] | GridTrading grid_levels TOML 配置存儲但不應用 | dead param 違反規則 | `grid_trading.rs:114,434,504` |
| **FIX-07** | P1 | QC: RG-4 [P1] | OU theta clamp 0.001 在非 OU 序列產生巨大間距 | 網格策略失效風險 | `grid_trading.rs` compute_ou_step |
| **FIX-08** | MAJOR | FA: #9/#10/#11 [MAJOR] · CC: §2.1 [FAIL] · E5: R-01/R-05 [High] · A3: §2.3 [MAJOR] | 文件大小違規（13+ 文件超 1200 行硬上限） | 代碼規範 §九 | 見子表 |
| **FIX-09** | HIGH | E3: SEC-E01 [HIGH] + SEC-B03 [MEDIUM] | ocEsc() 缺少單引號轉義 | XSS defense-in-depth 缺口 | `common.js:369-372` |
| **FIX-10** | CRITICAL | E3: SEC-D01 [CRITICAL] | IPC HMAC 認證為可選（Live 模式下應強制） | Live 安全風險 | `ipc_server/mod.rs:497` |
| **FIX-11** | HIGH | E3: SEC-D02 [HIGH] | Auth cookie secure=False | 中間人截取風險 | `legacy_routes.py:322` |
| **FIX-12** | HIGH | E3: SEC-F01 [HIGH] | CSP 使用 unsafe-inline | XSS 防護削弱 | `main_legacy.py:335-343` |
| **FIX-13** | P0 | E4: P0-#1 [P0-CRITICAL] | edge_estimates.rs 零測試（208 行 / 9 pub fn） | JSON 解析無驗證 | `edge_estimates.rs` |
| **FIX-14** | P0 | E4: P0-#2 [P0-CRITICAL] | REST API timeout fail-closed 行為無測試 | 硬邊界合規未驗證 | `bybit_rest_client.rs` |
| **FIX-15** | P0 | E4: P0-#3 [P0-CRITICAL] | 三管線並發寫入無集成測試 | 3E-ARCH 核心未驗證 | e2e tests |
| **FIX-16** | P1 | E4: P1-#4 [P1-HIGH] | startup.rs 零測試（856 行） | 啟動失敗無防護 | `startup.rs` |
| **FIX-17** | P1 | E4: P1-#9 [P1-HIGH] | Config hot-reload + tick 並發無測試 | ArcSwap 安全未驗證 | config/store.rs |
| **FIX-18** | P1 | E4: §四.2 [P1-HIGH] | Price=0.0 tick 行為未測試 | 除零風險 | `on_tick.rs` |
| **FIX-19** | P1 | BB: BB-A4 [P1] [PARSE-ERROR] | execution.fast 缺 execFee → WS 手續費為 0 | Mainnet PNL-FIX-2 同類 | `bybit_private_ws.rs:593-605` |
| **FIX-20** | P1 | BB: BB-A5 [P1] [RISK] | pre_check_order() 使用真正下單端點 | 意外下單風險 | `platform_client.rs:362-370` |
| **FIX-21** | MAJOR | FA: #7 [MAJOR] | 3 個 Rust 孤立模組（1612 行）從未被引用 | 編譯/維護負擔 | `leverage_token_client.rs`, `spot_margin_client.rs`, `batch_order_manager.rs` |
| **FIX-22** | MAJOR | FA: #8 [MAJOR] + #6 [MAJOR] | 4 個 MlSwitches config 欄位未運行時讀取 | 假功能違反規則 | `learning_config.rs:86-106` |
| **FIX-23** | MAJOR | FA: #4 [MAJOR] | FundingArb 策略完整 stub | 5 策略僅 4 活躍 | `funding_arb.rs:124-138` |
| **FIX-24** | P2 | QC: H2 [P2] | RSI 閾值 30/70 硬編碼 | 不可配置化 | `bb_reversion.rs` |
| **FIX-25** | P2 | QC: RG-5 [P2] + H6 [P2] | GridTrading FEE_PCT 硬編碼 vs 動態費率不一致 | 費用計算偏差 | `grid_trading.rs:127` |
| **FIX-26** | P2 | QC: RG-6 [P2] | BbBreakout squeeze 狀態永不過期 | 虛假突破風險 | `bb_breakout.rs` |
| **FIX-27** | P2 | QC: RG-7 [P2] | Kelly 負邊際仍開 1% 倉 | Phase 5 期間額外風險 | `kelly_sizer.rs` |
| **FIX-28** | P2 | QC: RG-2 [P2] | Exchange 模式 leverage 永遠 1.0 | 未讀取 Bybit 實際槓桿 | `router.rs` |
| **FIX-29** | P2 | E5: R-02 [High] | on_tick() 單函數 1187 行 | 可維護性核心風險 | `on_tick.rs:11-1187` |
| **FIX-30** | HIGH | E5: P-01 [High] | on_tick() symbol.clone() 重複 9 次 | 熱路徑堆分配浪費 | `on_tick.rs` |
| **FIX-31** | MEDIUM | E5: P-02 [High] | PriceEvent metadata HashMap 每 tick 分配 | 高頻堆分配 | `price.rs:24`, `ws_client.rs:460` |
| **FIX-32** | MEDIUM | E5: P-04 [Medium] | risk_config().clone() 每 tick 深拷貝 | 不必要的深拷貝 | `on_tick.rs:998` |
| **FIX-33** | MEDIUM | E5: P-05 [Medium] | seen_exec_ids VecDeque 線性搜索 | O(500) 去重 | `event_consumer/mod.rs:580` |
| **FIX-34** | P1 | MIT: ML-1 [P0] | decision_outcomes 無 backfill writer | ML 訓練 VIEW 永空 | DB schema |
| **FIX-35** | P1 | MIT: DB-1 [P0] | V001-V004 DDL 執行狀態不確定 | ML 持久化可能阻塞 | DDL migrations |
| **FIX-36** | MINOR | FA: #15 [MINOR] | delegation_framework.py 562 行未引用 | 孤立代碼 | `delegation_framework.py` |
| **FIX-37** | MINOR | FA: #14 [MINOR] | PIPELINE_BRIDGE/STOP_MANAGER None 殘留 | 清理不完整 | `strategy_wiring.py:285-286` |
| **FIX-38** | P2 | CC: §2.5 [PARTIAL] | 5+ 個未登記 Singleton | 違反 §九 登記規則 | CLAUDE.md §九 |
| **FIX-39** | CRITICAL | A3: §5.1 [CRITICAL] | Danger Zone 操作使用原生 confirm() | 危險操作確認不足 | `tab-risk.html:501` |
| **FIX-40** | CRITICAL | A3: §5.1 [CRITICAL] | 策略刪除使用原生 confirm() | 不可逆操作無二次確認 | `tab-strategy.html:223` |
| **FIX-41** | MAJOR | A3: §1.2 [MAJOR] | index.html/app.js Bearer Token 面板殘留 | 死代碼 + DOM 浪費 | `app.js:2164`, `index.html:38-45` |
| **FIX-42** | MAJOR | A3: §2.1 [MAJOR] | console.html 雙重導航 | UX 認知負擔 | `console.html` |
| **FIX-43** | MAJOR | A3: §2.1 [MAJOR] | tab-trading.html 雙層 iframe 嵌套 | 性能 + 維護負擔 | `tab-trading.html` |
| **FIX-44** | MAJOR | A3: §2.2 [MAJOR] | 大部分 tab 缺少載入失敗狀態 | 用戶無法區分載入中/失敗 | 多個 tab |
| **FIX-45** | MAJOR | A3: §2.2 [MAJOR] | Live tab 30s 刷新偏慢 | 實盤監控延遲 | `tab-live.html` |
| **FIX-46** | MAJOR | A3: §2.3 [MAJOR] | tab-risk.html 信息過載（1390 行） | UX 可用性差 | `tab-risk.html` |
| **FIX-47** | P1 | TW: §4.1 [STALE] | CLAUDE_REFERENCE.md 過時 6 天 | 參考索引不準確 | `CLAUDE_REFERENCE.md` |
| **FIX-48** | P1 | TW: §4.1 [STALE] | KNOWN_ISSUES.md 過時 7 天 | 問題追蹤不準確 | `KNOWN_ISSUES.md` |
| **FIX-49** | P1 | TW: §3.1 [MISSING] | 5 個日期缺失 daily_summary | 違反強制同步規則 | worklogs/ |
| **FIX-50** | P2 | TW: §7.1 [超長文件] | CLAUDE_CHANGELOG.md 2135 行超長 | 超 1200 行硬上限 | `CLAUDE_CHANGELOG.md` |
| **FIX-51** | P2 | TW: §2.1 [DUPLICATE] | 3 個 DEPRECATED 文件未移至 archive | 文件整理 | references/ |
| **FIX-52** | P1 | R4: §四 P1-#5 [P1] | SCRIPT_INDEX.md 覆蓋率 ~11% | 腳本索引嚴重落後 | `SCRIPT_INDEX.md` |
| **FIX-53** | P2 | R4: §一 P1-#1/#2/#3 [P1] | docs/README.md 缺 3 個子目錄索引 | 文檔發現性差 | `docs/README.md` |
| **FIX-54** | P2 | R4: §三.2 P2-#10 [P2] | CHANGELOG 缺 6 個功能 commit | 審計追蹤不完整 | `CLAUDE_CHANGELOG.md` |
| **FIX-55** | P1 | BB: BB-A1+A2+A3 [P1] [API-MISMATCH] | 3 個 API 路徑 MISMATCH（dead code） | 潛在端點錯誤 | `position_manager.rs`, `account_manager.rs` |
| **FIX-56** | P2 | AI-E: §2.3.5 [注意] | Layer2 定價表 last_verified_date 過期 | GUI 顯示過期警告 | `layer2_types.py:334` |
| **FIX-57** | P2 | AI-E: §6.2 #3 [風險提醒] | Python/Rust 雙軌 AI 預算無同步 | 預算感知不一致 | Layer2CostTracker + BudgetTracker |
| **FIX-58** | MINOR | E3: SEC-F05 [LOW] | Unix socket 文件權限未設置 | 訪問控制偏寬 | `ipc_server/mod.rs:400` |

### FIX-08 文件大小違規子表

| 文件 | 行數 | 超標量 | 類型 |
|------|------|--------|------|
| `app.js` | 2608 | +1408 | JS |
| `tab-governance.html` | 2047 | +847 | HTML |
| `governance_routes.py` | 1914 | +714 | Python |
| `governance_hub.py` | 1812 | +612 | Python |
| `signal_generator.py` | 1452 | +252 | Python |
| `risk_config.rs` | 1381 | +181 | Rust |
| `backtest_engine.py` | 1352 | +152 | Python |
| `event_consumer/mod.rs` | 1302 | +102 | Rust |
| `claude_teacher/applier.rs` | 1257 | +57 | Rust |
| `on_tick.rs` | 1228 | +28 | Rust |
| `tab-risk.html` | 1390 | +190 | HTML |
| `live_session_routes.py` | 1203 | +3 | Python |
| `CLAUDE_CHANGELOG.md` | 2135 | +935 | 文檔 |

---

## Part 2: 修復優先級

### P0 (Live 阻塞 — 必須在 Live 前修復)

| ID | 問題 | 理由 |
|----|------|------|
| **FIX-10** | IPC HMAC 認證 Live 模式下應強制 | Live 時本機進程可未認證操控引擎 |
| **FIX-03** | FastTrack ReduceToHalf/PauseNewEntries 未處理 | 風控閉環缺口：Defensive/Reduced 模式無效 |
| **FIX-04** | price_drop/margin_util 硬編 0.0 | 閃崩/保證金危機防線完全失效 |
| **FIX-19** | execution.fast 缺 execFee | Mainnet 填充手續費為 0，PNL-FIX-2 同類問題 |
| **FIX-13** | edge_estimates.rs 零測試 | JSON 解析 + 除零風險，被 scanner/cost_gate 依賴 |
| **FIX-14** | REST timeout fail-closed 無測試 | 硬邊界合規（原則 #5）未驗證 |
| **FIX-15** | 三管線並發無集成測試 | 3E-ARCH 核心架構未端到端驗證 |
| **FIX-09** | ocEsc() 缺單引號轉義 | XSS defense-in-depth（1 行修改） |

### P1 (架構缺陷 — 本週修復)

| ID | 問題 | 理由 |
|----|------|------|
| **FIX-05** | correlated_exposure_pct = 0.0 | 組合級風險（原則 #16）實質失效 |
| **FIX-06** | GridTrading grid_levels dead param | 違反「可調參數禁止假功能」核心規則 |
| **FIX-07** | OU theta clamp 導致巨大間距 | 非 OU 序列上網格策略功能異常 |
| **FIX-11** | Cookie secure=False | 安全最佳實踐，1 行修改 |
| **FIX-16** | startup.rs 零測試 | 啟動邏輯關鍵，856 行完全裸奔 |
| **FIX-17** | Config hot-reload 並發無測試 | ArcSwap 語義正確性未驗證 |
| **FIX-18** | Price=0 tick 未測試 | 除零風險 |
| **FIX-20** | pre_check_order 意外下單風險 | 標記 dangerous 或移除 |
| **FIX-22** | 4 個 MlSwitches dead config | 假功能違反規則，需接線或移除 |
| **FIX-29** | on_tick() 1187 行需拆分 | 超 1200 硬上限 + 可維護性 |
| **FIX-30** | symbol.clone() 重複 9 次 | 熱路徑優化，低風險 |
| **FIX-32** | risk_config 每 tick 深拷貝 | 不必要開銷，低風險刪除 |
| **FIX-39** | Danger Zone 原生 confirm() | 危險操作需自定義 modal |
| **FIX-40** | 策略刪除原生 confirm() | 不可逆操作需二次確認 |
| **FIX-47** | CLAUDE_REFERENCE.md 過時 | 參考索引準確性 |
| **FIX-48** | KNOWN_ISSUES.md 過時 | 問題追蹤準確性 |
| **FIX-52** | SCRIPT_INDEX.md 覆蓋率 11% | 腳本發現性 |

### P2 (質量提升 — W22-W23)

| ID | 問題 |
|----|------|
| **FIX-01** | H1-H5 AI Agent 接入（W22 G-1 已排程） |
| **FIX-02** | Decision Lease Rust 接入（與 FIX-01 一起） |
| **FIX-08** | 文件大小違規 13+ 文件拆分 |
| **FIX-12** | CSP nonce 遷移（長期） |
| **FIX-21** | 3 個孤立 Rust 模組清理 |
| **FIX-23** | FundingArb 策略實現（OC-5） |
| **FIX-24** | RSI 閾值可配置化 |
| **FIX-25** | GridTrading FEE_PCT 動態化 |
| **FIX-26** | BbBreakout squeeze 過期機制 |
| **FIX-27** | Kelly 負邊際返回更小值 |
| **FIX-28** | Exchange leverage 讀取 Bybit 實際值 |
| **FIX-31** | PriceEvent metadata 結構化 |
| **FIX-33** | seen_exec_ids 改 HashSet |
| **FIX-34** | decision_outcomes backfill writer |
| **FIX-35** | DDL 遷移執行確認 |
| **FIX-38** | Singleton 登記更新 |
| **FIX-41** | Bearer Token 面板死代碼清理 |
| **FIX-44** | tab 載入失敗狀態 |
| **FIX-45** | Live tab 刷新間隔調整 |
| **FIX-46** | tab-risk 信息架構優化 |
| **FIX-49** | 5 個 daily_summary 補建 |
| **FIX-50** | CHANGELOG 拆分歸檔 |
| **FIX-51** | DEPRECATED 文件歸檔 |
| **FIX-53** | docs/README.md 索引補充 |
| **FIX-54** | CHANGELOG 缺失 commit 補錄 |
| **FIX-55** | 3 個 API 路徑 MISMATCH 驗證/修正 |
| **FIX-56** | Layer2 定價表更新 |
| **FIX-57** | 雙軌 AI 預算同步 |

### P3 (改善建議 — 排入 backlog)

| ID | 問題 |
|----|------|
| **FIX-36** | delegation_framework.py 清理 |
| **FIX-37** | PIPELINE_BRIDGE/STOP_MANAGER None 清理 |
| **FIX-42** | console 雙重導航重構 |
| **FIX-43** | iframe 嵌套消除 |
| **FIX-58** | Unix socket chmod |
| 硬編碼 confidence 參數化 | QC H1/H3/H4/H7-H9 等 P3 級 |

---

## Part 3: 詳細工作安排

### Session S1: P0 安全與風控修復 (預估 3-4h)

#### S1-A: FIX-10 — IPC Live 模式強制 HMAC

- **文件**: `rust/openclaw_engine/src/ipc_server/mod.rs:497`
- **行號**: 497（`if let Ok(secret) = std::env::var(...)` 塊）
- **修復方案**: 在 `start_server()` 入口處新增 Live pipeline guard：
  ```rust
  // 如果任何 pipeline 是 Live 模式，強制要求 OPENCLAW_IPC_SECRET
  if has_live_pipeline && std::env::var("OPENCLAW_IPC_SECRET").is_err() {
      panic!("OPENCLAW_IPC_SECRET is required when Live pipeline is active");
  }
  ```
  需要將 `PipelineKind` 信息傳入 `start_server()`。
- **負責**: E1
- **驗證**: E2 審查 + E4 新增 1 test（Live mode 無 secret → panic）
- **工作量**: 30min
- **依賴**: 無

#### S1-B: FIX-03 + FIX-04 — FastTrack 完整實現

- **文件**: `rust/openclaw_engine/src/tick_pipeline/on_tick.rs:148-180`
- **修復方案**:
  1. `on_tick.rs:161` 後新增：
     ```rust
     FastTrackAction::ReduceToHalf => { /* 遍歷持倉，發出 reduce_qty = qty/2 的平倉指令 */ }
     FastTrackAction::PauseNewEntries => { self.new_entries_paused = true; /* 在 Open 分支前檢查此標記 */ }
     ```
  2. FIX-04：計算真實 price_drop_pct（比較最新價 vs 最近 N 分鐘最高價）和 margin_utilization_pct（已用保證金/可用保證金）。從 paper_state 或 exchange 餘額數據中提取。
- **負責**: E1
- **驗證**: E2 + E4 新增 4 tests（ReduceToHalf 實際減倉 + PauseNewEntries 阻止開倉 + price_drop 觸發 + margin_util 觸發）
- **工作量**: 2h
- **依賴**: 無

#### S1-C: FIX-09 — ocEsc 單引號轉義

- **文件**: `app/static/common.js:371`
- **修復方案**: 追加 `.replace(/'/g, '&#x27;')`
- **負責**: E1
- **驗證**: E2
- **工作量**: 5min
- **依賴**: 無

#### S1-D: FIX-19 — execution.fast fee 補全

- **文件**: `rust/openclaw_engine/src/bybit_private_ws.rs:593-605` + `event_consumer/mod.rs`
- **修復方案**: 在 event_consumer 處理 execution.fast fill 時，如 exec_fee 為空字串或 0，標記 `fee_pending=true`。觸發一次 REST `/v5/execution/list` 查詢補全手續費。或使用 `fee_rate * exec_qty * exec_price` 估算。
- **負責**: E1a
- **驗證**: E2 + E4 新增 2 tests
- **工作量**: 1h
- **依賴**: 無

### Session S2: P0 測試補全 (預估 4-5h)

#### S2-A: FIX-13 — edge_estimates.rs 測試

- **文件**: `rust/openclaw_engine/src/edge_estimates.rs`（新增 #[cfg(test)] mod tests）
- **修復方案**: 新增 8-10 tests：
  - `test_load_from_str_valid_json` — 正常 JSON 解析
  - `test_load_from_str_empty_json` — 空 JSON `{}` 不 panic
  - `test_load_from_str_malformed_json` — 畸形 JSON → 優雅處理
  - `test_grand_mean_bps_empty_estimates` — 空估計 → 不除零
  - `test_grand_mean_bps_single_strategy` — 單策略正確計算
  - `test_get_strategy_edge_missing` — 不存在的策略 → None
  - `test_get_strategy_edge_present` — 存在的策略 → 正確值
  - `test_load_from_file_not_found` — 文件不存在 → 優雅處理
- **負責**: E4
- **驗證**: E2
- **工作量**: 1h
- **依賴**: 無

#### S2-B: FIX-14 — REST timeout 測試

- **文件**: `rust/openclaw_engine/src/bybit_rest_client.rs`（tests mod）
- **修復方案**: 使用 `mockito` 或 `wiremock` 模擬 HTTP server，設置響應延遲 > timeout → 驗證返回 Error 且不重試。
- **負責**: E4
- **驗證**: E2
- **工作量**: 2h
- **依賴**: 無

#### S2-C: FIX-15 — 三管線並發 e2e

- **文件**: `rust/openclaw_engine/tests/` 新增 `three_pipeline_concurrent_test.rs`
- **修復方案**: 構造 Paper+Demo+Live 三個 TickPipeline 實例，同時發送 tick → 驗證各自 paper_state 獨立、不互相污染。
- **負責**: E4
- **驗證**: E2
- **工作量**: 3h
- **依賴**: 無

### Session S3: P1 風控 + 策略修復 (預估 3h)

#### S3-A: FIX-05 — correlated_exposure_pct 接線

- **文件**: `rust/openclaw_engine/src/intent_processor/router.rs:179,420`
- **修復方案**: 計算同方向持倉的佔比作為 correlated_exposure_pct。具體：
  ```rust
  let same_direction_exposure = positions.iter()
      .filter(|p| p.side == intent.side)
      .map(|p| p.qty * price)
      .sum::<f64>();
  let correlated_exposure_pct = same_direction_exposure / balance * 100.0;
  ```
  將此值傳入 `check_order_allowed()` 替換 0.0。
- **負責**: E1
- **驗證**: E2 + QC 數學驗證 + E4 新增 2 tests
- **工作量**: 1h
- **依賴**: 無

#### S3-B: FIX-06 — GridTrading grid_levels 接線

- **文件**: `rust/openclaw_engine/src/strategies/grid_trading.rs:114,434,504`
- **修復方案**: 將 `DEFAULT_GRID_COUNT` 替換為 `self.params.grid_levels`。確認 `GridTradingParams.grid_levels` 從 TOML 正確加載。修改 `build_levels()` / `rebalance()` 中所有 `DEFAULT_GRID_COUNT` 引用。
- **負責**: E1
- **驗證**: E2 + QC + E4（現有 grid tests 需更新斷言）
- **工作量**: 45min
- **依賴**: 無

#### S3-C: FIX-07 — OU theta 非均值回歸序列處理

- **文件**: `rust/openclaw_engine/src/strategies/grid_trading.rs` compute_ou_step
- **修復方案**: 當 OLS 斜率 b > 0 時，`compute_ou_step()` 返回 `None`（序列不適合 OU 模型），回退到 ±10% adaptive 範圍。
- **負責**: E1
- **驗證**: QC + E4 新增 1 test
- **工作量**: 30min
- **依賴**: 無

#### S3-D: FIX-22 — MlSwitches 死 config 處理

- **文件**: `rust/openclaw_engine/src/config/learning_config.rs:86-106`
- **修復方案**: 二選一：
  - 方案 A（推薦）：在 `tasks.rs` 的 teacher_loop 和 linucb 分支中讀取對應 switch，使其真正生效
  - 方案 B：移除 4 個未使用的 switch 欄位 + 保留 `_placeholder` 註釋
- **負責**: E1
- **驗證**: E2 + E4
- **工作量**: 1h
- **依賴**: 無

### Session S4: P1 代碼重構 — on_tick 拆分 (預估 3-4h)

#### S4-A: FIX-29 + FIX-30 + FIX-32 — on_tick 優化與拆分

- **文件**: `rust/openclaw_engine/src/tick_pipeline/on_tick.rs`
- **修復方案**:
  1. **FIX-30**: 在 `on_tick()` 開頭 `let sym = &event.symbol;`，替換後續 8 處 `.clone()`
  2. **FIX-32**: 刪除 `let risk_config = self.intent_processor.risk_config().clone();`，直接使用 `self.intent_processor.risk_config()` 的引用
  3. **FIX-29**: 提取 7 個子方法：
     - `on_tick_preprocess()` ~100 行
     - `on_tick_fast_track()` ~50 行
     - `on_tick_indicators()` ~80 行
     - `on_tick_signals()` ~100 行
     - `on_tick_strategy_dispatch()` ~350 行（E5 S-01 shared helpers）
     - `on_tick_risk_checks()` ~200 行
     - `on_tick_housekeeping()` ~50 行
  4. 提取 E5 S-02 `push_capped()` 工具函數 + S-03 ID 工廠函數
- **負責**: E1
- **驗證**: E2 + E4（所有 67 tick_pipeline tests 必須繼續 pass）
- **工作量**: 3-4h
- **依賴**: S1-B（FastTrack 修復）先完成

### Session S5: P1 安全 + GUI + 文檔 (預估 2-3h)

#### S5-A: FIX-11 — Cookie secure 動態化

- **文件**: `app/legacy_routes.py:322`
- **修復方案**: `secure=bool(os.environ.get("OPENCLAW_HTTPS", ""))`
- **工作量**: 10min

#### S5-B: FIX-39 + FIX-40 — 危險操作自定義 modal

- **文件**: `app/static/tab-risk.html:501`, `app/static/tab-strategy.html:223`
- **修復方案**: 將原生 `confirm()` 替換為自定義 modal dialog（參考 tab-live.html 的二次確認模式）。策略刪除要求輸入策略名稱確認。
- **工作量**: 1.5h

#### S5-C: FIX-47 + FIX-48 — 文檔更新

- **文件**: `docs/CLAUDE_REFERENCE.md`, `docs/KNOWN_ISSUES.md`
- **修復方案**: 補入 04-07~12 新功能參考；review KNOWN_ISSUES 10 個 OPEN 項狀態
- **工作量**: 1h

#### S5-D: FIX-52 — SCRIPT_INDEX 更新

- **文件**: `helper_scripts/SCRIPT_INDEX.md`
- **修復方案**: 補充 canary/（6 個）、phase4/（3 個）腳本索引
- **工作量**: 30min

### Session S6: P1 測試補全 (預估 3h)

#### S6-A: FIX-16 — startup.rs 可測部分提取

- **文件**: `rust/openclaw_engine/src/startup.rs`
- **修復方案**: 提取 `build_config_stores()`, `validate_startup_config()` 等純函數，新增 5 tests
- **工作量**: 2h

#### S6-B: FIX-17 — Config hot-reload 並發測試

- **修復方案**: 新增 3 tests：spawn 多線程同時 store() + load()，驗證 ArcSwap 語義
- **工作量**: 1h

#### S6-C: FIX-18 — Price=0 邊界測試

- **修復方案**: `tick_pipeline/tests.rs` 新增 2 tests（Price=0 tick 不 panic、不除零）
- **工作量**: 30min

### Session S7: P2 文件拆分批次 (預估 4-5h)

#### S7-A: risk_config.rs 拆分

- **文件**: `rust/openclaw_engine/src/config/risk_config.rs` (1381 行)
- **修復方案**: 默認值函數（~100 個 `fn default_*`）提取到 `config/risk_config_defaults.rs`
- **工作量**: 1h

#### S7-B: governance_routes.py 拆分

- **文件**: `governance_routes.py` (1914 行)
- **修復方案**: 拆為 `governance_auth_routes.py` + `governance_risk_routes.py` + `governance_promotion_routes.py` + 核心
- **工作量**: 2h

#### S7-C: app.js 拆分

- **文件**: `app.js` (2608 行)
- **修復方案**: 拆為 `app-core.js` + `app-actions.js` + `app-config.js`
- **工作量**: 1.5h

### Session S8: P2 策略與 ML 修復 (預估 3h)

#### S8-A: FIX-24/25/26/27 — 策略參數化與修復

- FIX-24: RSI 閾值加入 BbReversionParams (30min)
- FIX-25: GridTrading FEE_PCT 從 config 或 IntentProcessor 注入 (30min)
- FIX-26: BbBreakout 加 squeeze 過期時間 (30min)
- FIX-27: Kelly 負邊際返回 0.1% (15min)

#### S8-B: FIX-34 — decision_outcomes backfill

- **修復方案**: 實現定時 job：掃描 fills → 計算 1m/5m/1h/4h/24h 回報窗口 → 寫入 `trading.decision_outcomes`
- **工作量**: 2h

### Session S9: P2 清理與索引 (預估 2h)

- FIX-21: 3 個孤立 Rust 模組 → `lib.rs` 移除 `pub mod`（或加 `#[cfg(feature = ...)]`）(15min)
- FIX-38: CLAUDE.md §九 Singleton 表更新 (15min)
- FIX-41: app.js connectButton 死代碼清理 (15min)
- FIX-49: 5 個 daily_summary 補建 (30min)
- FIX-50: CHANGELOG 拆分 (30min)
- FIX-51: 3 個 DEPRECATED 文件移至 archive (5min)
- FIX-53: README.md 索引補充 (15min)
- FIX-54: CHANGELOG 缺失 commit 補錄 (15min)
- FIX-56: Layer2 定價表更新 (5min)

---

## Part 4: 並行策略

### 無依賴（可完全並行）

```
S1-A (IPC HMAC)  ─┐
S1-C (ocEsc)     ─┤
S1-D (exec.fast) ─┤── 全部獨立，可同時進行
S2-A (edge tests)─┤
S2-B (REST tests)─┤
S5-A (cookie)    ─┤
S5-C (文檔)      ─┤
S5-D (索引)      ─┘
```

### 有依賴（必須串行）

```
S1-B (FastTrack 完整實現)
  └→ S4-A (on_tick 拆分) — 需先完成 FastTrack 新增代碼，再一起拆分

S3-B (grid_levels 接線) + S3-C (OU theta)
  └→ S8-A (策略參數化) — 同一批策略文件修改

S2-A+B+C (P0 測試)
  └→ S6-A+B+C (P1 測試) — 測試 session 串行避免編譯衝突

S7-A+B+C (文件拆分)
  └→ 依賴 S4-A 完成後再處理 on_tick 相關文件
```

### 最優執行序列

```
Phase 1 (Day 1): S1 全部 + S2-A/B 並行 + S5-A/C/D 並行
Phase 2 (Day 1-2): S2-C + S3 全部 + S5-B
Phase 3 (Day 2): S4-A (on_tick 拆分) + S6 全部
Phase 4 (Day 3): S7 (文件拆分) + S8 + S9
```

---

## Part 5: Session 拆分建議

### Session 1: "P0 安全與風控" (獨立，可立即開始)
- **Scope**: FIX-03/04/09/10/19
- **預期產出**: FastTrack 完整 + IPC Live guard + ocEsc 修復 + exec.fast fee 補全
- **Agent 組合**: E1（主編碼）+ E1a（Bybit 部分）+ E2（審查）+ E4（測試）
- **跨 session 依賴**: 無（獨立）
- **預估時間**: 3-4h
- **Context 友好度**: 集中在 on_tick.rs + ipc_server + common.js + bybit_private_ws，文件數可控

### Session 2: "P0 測試補全" (獨立，可與 S1 並行)
- **Scope**: FIX-13/14/15
- **預期產出**: edge_estimates 10 tests + REST timeout 3 tests + 三管線並發 3 tests
- **Agent 組合**: E4（主測試）+ E2（審查）
- **跨 session 依賴**: 無
- **預估時間**: 4-5h

### Session 3: "P1 風控策略修復" (依賴 S1 完成)
- **Scope**: FIX-05/06/07/22
- **預期產出**: correlated_exposure 接線 + grid_levels 接線 + OU 修復 + ML switches 處理
- **Agent 組合**: E1（編碼）+ QC（數學驗證）+ E2 + E4
- **跨 session 依賴**: 無強依賴，但建議在 S1 後（FastTrack 修復穩定後再改 on_tick 相關）
- **預估時間**: 3h

### Session 4: "P1 on_tick 重構" (依賴 S1+S3 完成)
- **Scope**: FIX-29/30/32 + E5 S-01/S-02/S-03/S-04
- **預期產出**: on_tick 從 1228 行降至 ~800 行，7 子方法 + 3 工具函數
- **Agent 組合**: E1（重構）+ E5（優化指導）+ E2 + E4
- **跨 session 依賴**: **必須在 S1（FastTrack）和 S3 之後**，因為會修改 on_tick 同區域代碼
- **預估時間**: 3-4h

### Session 5: "P1 安全 + GUI + 文檔" (獨立)
- **Scope**: FIX-11/39/40/47/48/52
- **預期產出**: cookie 修復 + 2 個 modal 升級 + 3 份文檔更新
- **Agent 組合**: E1（GUI）+ A3（UX 驗證）+ TW（文檔）+ R4（索引）
- **跨 session 依賴**: 無
- **預估時間**: 2-3h

### Session 6: "P1 測試補全第二批" (建議在 S4 後)
- **Scope**: FIX-16/17/18
- **預期產出**: startup 可測部分 5 tests + hot-reload 並發 3 tests + Price=0 邊界 2 tests
- **Agent 組合**: E4 + E2
- **跨 session 依賴**: 建議在 S4 後（on_tick 結構穩定後再寫新測試）
- **預估時間**: 3h

### Session 7: "P2 文件拆分" (依賴 S4 完成)
- **Scope**: FIX-08 的 risk_config.rs + governance_routes.py + app.js
- **預期產出**: 3 個嚴重超標文件降至 1200 以下
- **Agent 組合**: E1 + E5 + E2 + E4
- **跨 session 依賴**: S4 完成後（on_tick.rs 已拆分，不會衝突）
- **預估時間**: 4-5h

### Session 8: "P2 策略與 ML" (獨立)
- **Scope**: FIX-24/25/26/27/34
- **預期產出**: 4 個策略參數化修復 + decision_outcomes backfill writer
- **Agent 組合**: E1 + QC + E4
- **跨 session 依賴**: 無（不同文件）
- **預估時間**: 3h

### Session 9: "P2 清理與索引" (獨立，低優先級)
- **Scope**: FIX-21/38/41/49/50/51/53/54/56
- **預期產出**: 死代碼清理 + 文檔索引更新
- **Agent 組合**: E1 + TW + R4
- **跨 session 依賴**: 無
- **預估時間**: 2h

### PM 調整後執行時間線

```
Day 1 (W22-Mon):
  ├─ Session 1 (P0 安全風控) ────── AM   [E1+E1a+E2+E4]
  └─ Session 2 (P0 測試) ────────── PM   [E4+E2]         並行

Day 2 (W22-Tue):
  ├─ Session 3 (P1 風控策略) ────── AM   [E1+QC+E2+E4]
  └─ Session 5 (P1 安全+GUI+文檔) ─ PM   [E1+A3+TW+R4]   並行

Day 3 (W22-Wed):
  ├─ Session 4 (P1 on_tick 重構) ── AM   [E1+E5+E2+E4]
  └─ G-1 AI Agent 工作啟動 ──────── PM   [切換焦點]

Day 4-5 (W22-Thu/Fri):
  └─ G-1 AI Agent（Strategist/Guardian 接線）持續

W23 初:
  ├─ Session 6 (P1 測試第二批) ──── 插入
  ├─ Session 7-9 (P2 清理) ──────── 按優先級穿插
  └─ G-1 R-06 全 5 agent 持續
```

**預計 P0 全部 2 天內完成。P1 核心項 3 天。W22 後半轉入 G-1 AI Agent 工作。**

### 新增測試預估

| Session | 新增測試數 |
|---------|-----------|
| S1 | +6 (FastTrack 4 + IPC 1 + exec.fast 1) |
| S2 | +16 (edge 10 + REST 3 + 三管線 3) |
| S3 | +5 (correlated 2 + grid 2 + OU 1) |
| S4 | 0 (重構，現有 67 tests 全 pass) |
| S5 | 0 (GUI/文檔) |
| S6 | +10 (startup 5 + hot-reload 3 + Price=0 2) |
| S8 | +4 (策略修復測試) |
| **合計** | **+41 tests** |

完成後測試基線：**1355 + 41 = ~1396 Rust** / Python 不變。

---

*PA 原始報告由 PA (Project Architect) 角色生成，基於 12 份審計報告綜合分析 + P0/P1 代碼實地驗證*
*PM 確認與簽核由 PM (Project Manager) 完成*
*2026-04-12*


---

# 2. PA 匯總修復計劃

> 原始文件：`docs/CCAgentWorkSpace/PA/2026-04-12--consolidated_fix_plan.md`

# PA 綜合修復計劃 — Consolidated Fix Plan
# 日期：2026-04-12
# 來源：12 份審計報告 (FA/AI-E/E5/E4/E3/CC/QC/MIT/BB/TW/R4/A3) 綜合分析
# 確認方法：P0/P1 級發現已逐一代碼驗證

---

## Part 1: 問題總覽

### 去重說明

12 份報告共產生 ~120 條發現，去重合併後剩餘 **58 條唯一問題**。以下為主要重疊：
- FastTrack ReduceToHalf/PauseNewEntries 未處理 → FA #2 = CC = E3-SEC-A01 = E5-D-01（合併為 FIX-03）
- H1-H5 AI 治理層 stub → FA #1 = AI-E = CC 原則 #11/#12/#15（合併為 FIX-01）
- 文件大小違規 → FA #9-11 = CC §2.1 = E5-R-01/R-05 = A3 §八（合併為 FIX-08）
- correlated_exposure_pct = 0.0 → QC-RG-1 = FA 已含在風控閉環（合併為 FIX-05）
- ocEsc 缺單引號 → E3-SEC-E01 = E3-SEC-B03（合併為 FIX-09）
- edge_estimates.rs 零測試 → E4 P0-#1 = FA 已涵蓋（合併為 FIX-13）
- Decision Lease Rust 未使用 → FA #3 = CC 原則 #3（合併為 FIX-02，非阻塞）
- GridTrading grid_levels dead param → QC-RG-3 = FA #8 死 config（合併為 FIX-06）

### 綜合問題表

| ID | 嚴重度 | 來源報告（Agent: 原始發現 ID [原始嚴重度]） | 問題描述 | 影響範圍 | 關鍵文件路徑 |
|----|--------|----------------------------------------------|----------|----------|-------------|
| **FIX-01** | BLOCKER | FA: #1 [BLOCKER] · AI-E: §2.4/§2.5 [Partial] · CC: 原則#11/#12/#15 [PARTIAL] | H1-H5 AI 治理層全 stub，Rust 引擎未接入 AI Agent | 原則 #3/#11/#13 | `ai_service.py`, `strategy_wiring.py` |
| **FIX-02** | MAJOR | FA: #3 [MAJOR] · CC: 原則#3 [PASS with note] | Decision Lease Python 完整但 Rust 引擎未使用 | 原則 #3 部分失效 | `decision_lease_state_machine.py`, `router.rs` |
| **FIX-03** | BLOCKER | FA: #2 [BLOCKER] · E3: SEC-A01 [LOW] · E5: D-01 [Medium] | FastTrack ReduceToHalf/PauseNewEntries 定義但未處理 | 風控閉環缺口 | `fast_track.rs:17-18`, `on_tick.rs:148-161` |
| **FIX-04** | BLOCKER | FA: #2 [BLOCKER] · E3: SEC-A01 [LOW] | fast_track price_drop/margin_util 硬編 0.0 | 閃崩/保證金危機防線失效 | `on_tick.rs:156-159` |
| **FIX-05** | P1 | QC: RG-1 [P1] | correlated_exposure_pct 永遠 0.0 | 組合級風險檢查失效 | `router.rs:179,420` |
| **FIX-06** | P1 | QC: RG-3 [P1] + H5 [P1] | GridTrading grid_levels TOML 配置存儲但不應用 | dead param 違反規則 | `grid_trading.rs:114,434,504` |
| **FIX-07** | P1 | QC: RG-4 [P1] | OU theta clamp 0.001 在非 OU 序列產生巨大間距 | 網格策略失效風險 | `grid_trading.rs` compute_ou_step |
| **FIX-08** | MAJOR | FA: #9/#10/#11 [MAJOR] · CC: §2.1 [FAIL] · E5: R-01/R-05 [High] · A3: §2.3 [MAJOR] | 文件大小違規（13+ 文件超 1200 行硬上限） | 代碼規範 §九 | 見子表 |
| **FIX-09** | HIGH | E3: SEC-E01 [HIGH] + SEC-B03 [MEDIUM] | ocEsc() 缺少單引號轉義 | XSS defense-in-depth 缺口 | `common.js:369-372` |
| **FIX-10** | CRITICAL | E3: SEC-D01 [CRITICAL] | IPC HMAC 認證為可選（Live 模式下應強制） | Live 安全風險 | `ipc_server/mod.rs:497` |
| **FIX-11** | HIGH | E3: SEC-D02 [HIGH] | Auth cookie secure=False | 中間人截取風險 | `legacy_routes.py:322` |
| **FIX-12** | HIGH | E3: SEC-F01 [HIGH] | CSP 使用 unsafe-inline | XSS 防護削弱 | `main_legacy.py:335-343` |
| **FIX-13** | P0 | E4: P0-#1 [P0-CRITICAL] | edge_estimates.rs 零測試（208 行 / 9 pub fn） | JSON 解析無驗證 | `edge_estimates.rs` |
| **FIX-14** | P0 | E4: P0-#2 [P0-CRITICAL] | REST API timeout fail-closed 行為無測試 | 硬邊界合規未驗證 | `bybit_rest_client.rs` |
| **FIX-15** | P0 | E4: P0-#3 [P0-CRITICAL] | 三管線並發寫入無集成測試 | 3E-ARCH 核心未驗證 | e2e tests |
| **FIX-16** | P1 | E4: P1-#4 [P1-HIGH] | startup.rs 零測試（856 行） | 啟動失敗無防護 | `startup.rs` |
| **FIX-17** | P1 | E4: P1-#9 [P1-HIGH] | Config hot-reload + tick 並發無測試 | ArcSwap 安全未驗證 | config/store.rs |
| **FIX-18** | P1 | E4: §四.2 [P1-HIGH] | Price=0.0 tick 行為未測試 | 除零風險 | `on_tick.rs` |
| **FIX-19** | P1 | BB: BB-A4 [P1] [PARSE-ERROR] | execution.fast 缺 execFee → WS 手續費為 0 | Mainnet PNL-FIX-2 同類 | `bybit_private_ws.rs:593-605` |
| **FIX-20** | P1 | BB: BB-A5 [P1] [RISK] | pre_check_order() 使用真正下單端點 | 意外下單風險 | `platform_client.rs:362-370` |
| **FIX-21** | MAJOR | FA: #7 [MAJOR] | 3 個 Rust 孤立模組（1612 行）從未被引用 | 編譯/維護負擔 | `leverage_token_client.rs`, `spot_margin_client.rs`, `batch_order_manager.rs` |
| **FIX-22** | MAJOR | FA: #8 [MAJOR] + #6 [MAJOR] | 4 個 MlSwitches config 欄位未運行時讀取 | 假功能違反規則 | `learning_config.rs:86-106` |
| **FIX-23** | MAJOR | FA: #4 [MAJOR] | FundingArb 策略完整 stub | 5 策略僅 4 活躍 | `funding_arb.rs:124-138` |
| **FIX-24** | P2 | QC: H2 [P2] | RSI 閾值 30/70 硬編碼 | 不可配置化 | `bb_reversion.rs` |
| **FIX-25** | P2 | QC: RG-5 [P2] + H6 [P2] | GridTrading FEE_PCT 硬編碼 vs 動態費率不一致 | 費用計算偏差 | `grid_trading.rs:127` |
| **FIX-26** | P2 | QC: RG-6 [P2] | BbBreakout squeeze 狀態永不過期 | 虛假突破風險 | `bb_breakout.rs` |
| **FIX-27** | P2 | QC: RG-7 [P2] | Kelly 負邊際仍開 1% 倉 | Phase 5 期間額外風險 | `kelly_sizer.rs` |
| **FIX-28** | P2 | QC: RG-2 [P2] | Exchange 模式 leverage 永遠 1.0 | 未讀取 Bybit 實際槓桿 | `router.rs` |
| **FIX-29** | P2 | E5: R-02 [High] | on_tick() 單函數 1187 行 | 可維護性核心風險 | `on_tick.rs:11-1187` |
| **FIX-30** | HIGH | E5: P-01 [High] | on_tick() symbol.clone() 重複 9 次 | 熱路徑堆分配浪費 | `on_tick.rs` |
| **FIX-31** | MEDIUM | E5: P-02 [High] | PriceEvent metadata HashMap 每 tick 分配 | 高頻堆分配 | `price.rs:24`, `ws_client.rs:460` |
| **FIX-32** | MEDIUM | E5: P-04 [Medium] | risk_config().clone() 每 tick 深拷貝 | 不必要的深拷貝 | `on_tick.rs:998` |
| **FIX-33** | MEDIUM | E5: P-05 [Medium] | seen_exec_ids VecDeque 線性搜索 | O(500) 去重 | `event_consumer/mod.rs:580` |
| **FIX-34** | P1 | MIT: ML-1 [P0] | decision_outcomes 無 backfill writer | ML 訓練 VIEW 永空 | DB schema |
| **FIX-35** | P1 | MIT: DB-1 [P0] | V001-V004 DDL 執行狀態不確定 | ML 持久化可能阻塞 | DDL migrations |
| **FIX-36** | MINOR | FA: #15 [MINOR] | delegation_framework.py 562 行未引用 | 孤立代碼 | `delegation_framework.py` |
| **FIX-37** | MINOR | FA: #14 [MINOR] | PIPELINE_BRIDGE/STOP_MANAGER None 殘留 | 清理不完整 | `strategy_wiring.py:285-286` |
| **FIX-38** | P2 | CC: §2.5 [PARTIAL] | 5+ 個未登記 Singleton | 違反 §九 登記規則 | CLAUDE.md §九 |
| **FIX-39** | CRITICAL | A3: §5.1 [CRITICAL] | Danger Zone 操作使用原生 confirm() | 危險操作確認不足 | `tab-risk.html:501` |
| **FIX-40** | CRITICAL | A3: §5.1 [CRITICAL] | 策略刪除使用原生 confirm() | 不可逆操作無二次確認 | `tab-strategy.html:223` |
| **FIX-41** | MAJOR | A3: §1.2 [MAJOR] | index.html/app.js Bearer Token 面板殘留 | 死代碼 + DOM 浪費 | `app.js:2164`, `index.html:38-45` |
| **FIX-42** | MAJOR | A3: §2.1 [MAJOR] | console.html 雙重導航 | UX 認知負擔 | `console.html` |
| **FIX-43** | MAJOR | A3: §2.1 [MAJOR] | tab-trading.html 雙層 iframe 嵌套 | 性能 + 維護負擔 | `tab-trading.html` |
| **FIX-44** | MAJOR | A3: §2.2 [MAJOR] | 大部分 tab 缺少載入失敗狀態 | 用戶無法區分載入中/失敗 | 多個 tab |
| **FIX-45** | MAJOR | A3: §2.2 [MAJOR] | Live tab 30s 刷新偏慢 | 實盤監控延遲 | `tab-live.html` |
| **FIX-46** | MAJOR | A3: §2.3 [MAJOR] | tab-risk.html 信息過載（1390 行） | UX 可用性差 | `tab-risk.html` |
| **FIX-47** | P1 | TW: §4.1 [STALE] | CLAUDE_REFERENCE.md 過時 6 天 | 參考索引不準確 | `CLAUDE_REFERENCE.md` |
| **FIX-48** | P1 | TW: §4.1 [STALE] | KNOWN_ISSUES.md 過時 7 天 | 問題追蹤不準確 | `KNOWN_ISSUES.md` |
| **FIX-49** | P1 | TW: §3.1 [MISSING] | 5 個日期缺失 daily_summary | 違反強制同步規則 | worklogs/ |
| **FIX-50** | P2 | TW: §7.1 [超長文件] | CLAUDE_CHANGELOG.md 2135 行超長 | 超 1200 行硬上限 | `CLAUDE_CHANGELOG.md` |
| **FIX-51** | P2 | TW: §2.1 [DUPLICATE] | 3 個 DEPRECATED 文件未移至 archive | 文件整理 | references/ |
| **FIX-52** | P1 | R4: §四 P1-#5 [P1] | SCRIPT_INDEX.md 覆蓋率 ~11% | 腳本索引嚴重落後 | `SCRIPT_INDEX.md` |
| **FIX-53** | P2 | R4: §一 P1-#1/#2/#3 [P1] | docs/README.md 缺 3 個子目錄索引 | 文檔發現性差 | `docs/README.md` |
| **FIX-54** | P2 | R4: §三.2 P2-#10 [P2] | CHANGELOG 缺 6 個功能 commit | 審計追蹤不完整 | `CLAUDE_CHANGELOG.md` |
| **FIX-55** | P1 | BB: BB-A1+A2+A3 [P1] [API-MISMATCH] | 3 個 API 路徑 MISMATCH（dead code） | 潛在端點錯誤 | `position_manager.rs`, `account_manager.rs` |
| **FIX-56** | P2 | AI-E: §2.3.5 [注意] | Layer2 定價表 last_verified_date 過期 | GUI 顯示過期警告 | `layer2_types.py:334` |
| **FIX-57** | P2 | AI-E: §6.2 #3 [風險提醒] | Python/Rust 雙軌 AI 預算無同步 | 預算感知不一致 | Layer2CostTracker + BudgetTracker |
| **FIX-58** | MINOR | E3: SEC-F05 [LOW] | Unix socket 文件權限未設置 | 訪問控制偏寬 | `ipc_server/mod.rs:400` |

### FIX-08 文件大小違規子表

| 文件 | 行數 | 超標量 | 類型 |
|------|------|--------|------|
| `app.js` | 2608 | +1408 | JS |
| `tab-governance.html` | 2047 | +847 | HTML |
| `governance_routes.py` | 1914 | +714 | Python |
| `governance_hub.py` | 1812 | +612 | Python |
| `signal_generator.py` | 1452 | +252 | Python |
| `risk_config.rs` | 1381 | +181 | Rust |
| `backtest_engine.py` | 1352 | +152 | Python |
| `event_consumer/mod.rs` | 1302 | +102 | Rust |
| `claude_teacher/applier.rs` | 1257 | +57 | Rust |
| `on_tick.rs` | 1228 | +28 | Rust |
| `tab-risk.html` | 1390 | +190 | HTML |
| `live_session_routes.py` | 1203 | +3 | Python |
| `CLAUDE_CHANGELOG.md` | 2135 | +935 | 文檔 |

---

## Part 2: 修復優先級

### P0 (Live 阻塞 — 必須在 Live 前修復)

| ID | 問題 | 理由 |
|----|------|------|
| **FIX-10** | IPC HMAC 認證 Live 模式下應強制 | Live 時本機進程可未認證操控引擎 |
| **FIX-03** | FastTrack ReduceToHalf/PauseNewEntries 未處理 | 風控閉環缺口：Defensive/Reduced 模式無效 |
| **FIX-04** | price_drop/margin_util 硬編 0.0 | 閃崩/保證金危機防線完全失效 |
| **FIX-19** | execution.fast 缺 execFee | Mainnet 填充手續費為 0，PNL-FIX-2 同類問題 |
| **FIX-13** | edge_estimates.rs 零測試 | JSON 解析 + 除零風險，被 scanner/cost_gate 依賴 |
| **FIX-14** | REST timeout fail-closed 無測試 | 硬邊界合規（原則 #5）未驗證 |
| **FIX-15** | 三管線並發無集成測試 | 3E-ARCH 核心架構未端到端驗證 |
| **FIX-09** | ocEsc() 缺單引號轉義 | XSS defense-in-depth（1 行修改） |

### P1 (架構缺陷 — 本週修復)

| ID | 問題 | 理由 |
|----|------|------|
| **FIX-05** | correlated_exposure_pct = 0.0 | 組合級風險（原則 #16）實質失效 |
| **FIX-06** | GridTrading grid_levels dead param | 違反「可調參數禁止假功能」核心規則 |
| **FIX-07** | OU theta clamp 導致巨大間距 | 非 OU 序列上網格策略功能異常 |
| **FIX-11** | Cookie secure=False | 安全最佳實踐，1 行修改 |
| **FIX-16** | startup.rs 零測試 | 啟動邏輯關鍵，856 行完全裸奔 |
| **FIX-17** | Config hot-reload 並發無測試 | ArcSwap 語義正確性未驗證 |
| **FIX-18** | Price=0 tick 未測試 | 除零風險 |
| **FIX-20** | pre_check_order 意外下單風險 | 標記 dangerous 或移除 |
| **FIX-22** | 4 個 MlSwitches dead config | 假功能違反規則，需接線或移除 |
| **FIX-29** | on_tick() 1187 行需拆分 | 超 1200 硬上限 + 可維護性 |
| **FIX-30** | symbol.clone() 重複 9 次 | 熱路徑優化，低風險 |
| **FIX-32** | risk_config 每 tick 深拷貝 | 不必要開銷，低風險刪除 |
| **FIX-39** | Danger Zone 原生 confirm() | 危險操作需自定義 modal |
| **FIX-40** | 策略刪除原生 confirm() | 不可逆操作需二次確認 |
| **FIX-47** | CLAUDE_REFERENCE.md 過時 | 參考索引準確性 |
| **FIX-48** | KNOWN_ISSUES.md 過時 | 問題追蹤準確性 |
| **FIX-52** | SCRIPT_INDEX.md 覆蓋率 11% | 腳本發現性 |

### P2 (質量提升 — W22-W23)

| ID | 問題 |
|----|------|
| **FIX-01** | H1-H5 AI Agent 接入（W22 G-1 已排程） |
| **FIX-02** | Decision Lease Rust 接入（與 FIX-01 一起） |
| **FIX-08** | 文件大小違規 13+ 文件拆分 |
| **FIX-12** | CSP nonce 遷移（長期） |
| **FIX-21** | 3 個孤立 Rust 模組清理 |
| **FIX-23** | FundingArb 策略實現（OC-5） |
| **FIX-24** | RSI 閾值可配置化 |
| **FIX-25** | GridTrading FEE_PCT 動態化 |
| **FIX-26** | BbBreakout squeeze 過期機制 |
| **FIX-27** | Kelly 負邊際返回更小值 |
| **FIX-28** | Exchange leverage 讀取 Bybit 實際值 |
| **FIX-31** | PriceEvent metadata 結構化 |
| **FIX-33** | seen_exec_ids 改 HashSet |
| **FIX-34** | decision_outcomes backfill writer |
| **FIX-35** | DDL 遷移執行確認 |
| **FIX-38** | Singleton 登記更新 |
| **FIX-41** | Bearer Token 面板死代碼清理 |
| **FIX-44** | tab 載入失敗狀態 |
| **FIX-45** | Live tab 刷新間隔調整 |
| **FIX-46** | tab-risk 信息架構優化 |
| **FIX-49** | 5 個 daily_summary 補建 |
| **FIX-50** | CHANGELOG 拆分歸檔 |
| **FIX-51** | DEPRECATED 文件歸檔 |
| **FIX-53** | docs/README.md 索引補充 |
| **FIX-54** | CHANGELOG 缺失 commit 補錄 |
| **FIX-55** | 3 個 API 路徑 MISMATCH 驗證/修正 |
| **FIX-56** | Layer2 定價表更新 |
| **FIX-57** | 雙軌 AI 預算同步 |

### P3 (改善建議 — 排入 backlog)

| ID | 問題 |
|----|------|
| **FIX-36** | delegation_framework.py 清理 |
| **FIX-37** | PIPELINE_BRIDGE/STOP_MANAGER None 清理 |
| **FIX-42** | console 雙重導航重構 |
| **FIX-43** | iframe 嵌套消除 |
| **FIX-58** | Unix socket chmod |
| 硬編碼 confidence 參數化 | QC H1/H3/H4/H7-H9 等 P3 級 |

---

## Part 3: 詳細工作安排

### Session S1: P0 安全與風控修復 (預估 3-4h)

#### S1-A: FIX-10 — IPC Live 模式強制 HMAC

- **文件**: `rust/openclaw_engine/src/ipc_server/mod.rs:497`
- **行號**: 497（`if let Ok(secret) = std::env::var(...)` 塊）
- **修復方案**: 在 `start_server()` 入口處新增 Live pipeline guard：
  ```rust
  // 如果任何 pipeline 是 Live 模式，強制要求 OPENCLAW_IPC_SECRET
  if has_live_pipeline && std::env::var("OPENCLAW_IPC_SECRET").is_err() {
      panic!("OPENCLAW_IPC_SECRET is required when Live pipeline is active");
  }
  ```
  需要將 `PipelineKind` 信息傳入 `start_server()`。
- **負責**: E1
- **驗證**: E2 審查 + E4 新增 1 test（Live mode 無 secret → panic）
- **工作量**: 30min
- **依賴**: 無

#### S1-B: FIX-03 + FIX-04 — FastTrack 完整實現

- **文件**: `rust/openclaw_engine/src/tick_pipeline/on_tick.rs:148-180`
- **修復方案**:
  1. `on_tick.rs:161` 後新增：
     ```rust
     FastTrackAction::ReduceToHalf => { /* 遍歷持倉，發出 reduce_qty = qty/2 的平倉指令 */ }
     FastTrackAction::PauseNewEntries => { self.new_entries_paused = true; /* 在 Open 分支前檢查此標記 */ }
     ```
  2. FIX-04：計算真實 price_drop_pct（比較最新價 vs 最近 N 分鐘最高價）和 margin_utilization_pct（已用保證金/可用保證金）。從 paper_state 或 exchange 餘額數據中提取。
- **負責**: E1
- **驗證**: E2 + E4 新增 4 tests（ReduceToHalf 實際減倉 + PauseNewEntries 阻止開倉 + price_drop 觸發 + margin_util 觸發）
- **工作量**: 2h
- **依賴**: 無

#### S1-C: FIX-09 — ocEsc 單引號轉義

- **文件**: `app/static/common.js:371`
- **修復方案**: 追加 `.replace(/'/g, '&#x27;')`
- **負責**: E1
- **驗證**: E2
- **工作量**: 5min
- **依賴**: 無

#### S1-D: FIX-19 — execution.fast fee 補全

- **文件**: `rust/openclaw_engine/src/bybit_private_ws.rs:593-605` + `event_consumer/mod.rs`
- **修復方案**: 在 event_consumer 處理 execution.fast fill 時，如 exec_fee 為空字串或 0，標記 `fee_pending=true`。觸發一次 REST `/v5/execution/list` 查詢補全手續費。或使用 `fee_rate * exec_qty * exec_price` 估算。
- **負責**: E1a
- **驗證**: E2 + E4 新增 2 tests
- **工作量**: 1h
- **依賴**: 無

### Session S2: P0 測試補全 (預估 4-5h)

#### S2-A: FIX-13 — edge_estimates.rs 測試

- **文件**: `rust/openclaw_engine/src/edge_estimates.rs`（新增 #[cfg(test)] mod tests）
- **修復方案**: 新增 8-10 tests：
  - `test_load_from_str_valid_json` — 正常 JSON 解析
  - `test_load_from_str_empty_json` — 空 JSON `{}` 不 panic
  - `test_load_from_str_malformed_json` — 畸形 JSON → 優雅處理
  - `test_grand_mean_bps_empty_estimates` — 空估計 → 不除零
  - `test_grand_mean_bps_single_strategy` — 單策略正確計算
  - `test_get_strategy_edge_missing` — 不存在的策略 → None
  - `test_get_strategy_edge_present` — 存在的策略 → 正確值
  - `test_load_from_file_not_found` — 文件不存在 → 優雅處理
- **負責**: E4
- **驗證**: E2
- **工作量**: 1h
- **依賴**: 無

#### S2-B: FIX-14 — REST timeout 測試

- **文件**: `rust/openclaw_engine/src/bybit_rest_client.rs`（tests mod）
- **修復方案**: 使用 `mockito` 或 `wiremock` 模擬 HTTP server，設置響應延遲 > timeout → 驗證返回 Error 且不重試。
- **負責**: E4
- **驗證**: E2
- **工作量**: 2h
- **依賴**: 無

#### S2-C: FIX-15 — 三管線並發 e2e

- **文件**: `rust/openclaw_engine/tests/` 新增 `three_pipeline_concurrent_test.rs`
- **修復方案**: 構造 Paper+Demo+Live 三個 TickPipeline 實例，同時發送 tick → 驗證各自 paper_state 獨立、不互相污染。
- **負責**: E4
- **驗證**: E2
- **工作量**: 3h
- **依賴**: 無

### Session S3: P1 風控 + 策略修復 (預估 3h)

#### S3-A: FIX-05 — correlated_exposure_pct 接線

- **文件**: `rust/openclaw_engine/src/intent_processor/router.rs:179,420`
- **修復方案**: 計算同方向持倉的佔比作為 correlated_exposure_pct。具體：
  ```rust
  let same_direction_exposure = positions.iter()
      .filter(|p| p.side == intent.side)
      .map(|p| p.qty * price)
      .sum::<f64>();
  let correlated_exposure_pct = same_direction_exposure / balance * 100.0;
  ```
  將此值傳入 `check_order_allowed()` 替換 0.0。
- **負責**: E1
- **驗證**: E2 + QC 數學驗證 + E4 新增 2 tests
- **工作量**: 1h
- **依賴**: 無

#### S3-B: FIX-06 — GridTrading grid_levels 接線

- **文件**: `rust/openclaw_engine/src/strategies/grid_trading.rs:114,434,504`
- **修復方案**: 將 `DEFAULT_GRID_COUNT` 替換為 `self.params.grid_levels`。確認 `GridTradingParams.grid_levels` 從 TOML 正確加載。修改 `build_levels()` / `rebalance()` 中所有 `DEFAULT_GRID_COUNT` 引用。
- **負責**: E1
- **驗證**: E2 + QC + E4（現有 grid tests 需更新斷言）
- **工作量**: 45min
- **依賴**: 無

#### S3-C: FIX-07 — OU theta 非均值回歸序列處理

- **文件**: `rust/openclaw_engine/src/strategies/grid_trading.rs` compute_ou_step
- **修復方案**: 當 OLS 斜率 b > 0 時，`compute_ou_step()` 返回 `None`（序列不適合 OU 模型），回退到 ±10% adaptive 範圍。
- **負責**: E1
- **驗證**: QC + E4 新增 1 test
- **工作量**: 30min
- **依賴**: 無

#### S3-D: FIX-22 — MlSwitches 死 config 處理

- **文件**: `rust/openclaw_engine/src/config/learning_config.rs:86-106`
- **修復方案**: 二選一：
  - 方案 A（推薦）：在 `tasks.rs` 的 teacher_loop 和 linucb 分支中讀取對應 switch，使其真正生效
  - 方案 B：移除 4 個未使用的 switch 欄位 + 保留 `_placeholder` 註釋
- **負責**: E1
- **驗證**: E2 + E4
- **工作量**: 1h
- **依賴**: 無

### Session S4: P1 代碼重構 — on_tick 拆分 (預估 3-4h)

#### S4-A: FIX-29 + FIX-30 + FIX-32 — on_tick 優化與拆分

- **文件**: `rust/openclaw_engine/src/tick_pipeline/on_tick.rs`
- **修復方案**:
  1. **FIX-30**: 在 `on_tick()` 開頭 `let sym = &event.symbol;`，替換後續 8 處 `.clone()`
  2. **FIX-32**: 刪除 `let risk_config = self.intent_processor.risk_config().clone();`，直接使用 `self.intent_processor.risk_config()` 的引用
  3. **FIX-29**: 提取 7 個子方法：
     - `on_tick_preprocess()` ~100 行
     - `on_tick_fast_track()` ~50 行
     - `on_tick_indicators()` ~80 行
     - `on_tick_signals()` ~100 行
     - `on_tick_strategy_dispatch()` ~350 行（E5 S-01 shared helpers）
     - `on_tick_risk_checks()` ~200 行
     - `on_tick_housekeeping()` ~50 行
  4. 提取 E5 S-02 `push_capped()` 工具函數 + S-03 ID 工廠函數
- **負責**: E1
- **驗證**: E2 + E4（所有 67 tick_pipeline tests 必須繼續 pass）
- **工作量**: 3-4h
- **依賴**: S1-B（FastTrack 修復）先完成

### Session S5: P1 安全 + GUI + 文檔 (預估 2-3h)

#### S5-A: FIX-11 — Cookie secure 動態化

- **文件**: `app/legacy_routes.py:322`
- **修復方案**: `secure=bool(os.environ.get("OPENCLAW_HTTPS", ""))`
- **工作量**: 10min

#### S5-B: FIX-39 + FIX-40 — 危險操作自定義 modal

- **文件**: `app/static/tab-risk.html:501`, `app/static/tab-strategy.html:223`
- **修復方案**: 將原生 `confirm()` 替換為自定義 modal dialog（參考 tab-live.html 的二次確認模式）。策略刪除要求輸入策略名稱確認。
- **工作量**: 1.5h

#### S5-C: FIX-47 + FIX-48 — 文檔更新

- **文件**: `docs/CLAUDE_REFERENCE.md`, `docs/KNOWN_ISSUES.md`
- **修復方案**: 補入 04-07~12 新功能參考；review KNOWN_ISSUES 10 個 OPEN 項狀態
- **工作量**: 1h

#### S5-D: FIX-52 — SCRIPT_INDEX 更新

- **文件**: `helper_scripts/SCRIPT_INDEX.md`
- **修復方案**: 補充 canary/（6 個）、phase4/（3 個）腳本索引
- **工作量**: 30min

### Session S6: P1 測試補全 (預估 3h)

#### S6-A: FIX-16 — startup.rs 可測部分提取

- **文件**: `rust/openclaw_engine/src/startup.rs`
- **修復方案**: 提取 `build_config_stores()`, `validate_startup_config()` 等純函數，新增 5 tests
- **工作量**: 2h

#### S6-B: FIX-17 — Config hot-reload 並發測試

- **修復方案**: 新增 3 tests：spawn 多線程同時 store() + load()，驗證 ArcSwap 語義
- **工作量**: 1h

#### S6-C: FIX-18 — Price=0 邊界測試

- **修復方案**: `tick_pipeline/tests.rs` 新增 2 tests（Price=0 tick 不 panic、不除零）
- **工作量**: 30min

### Session S7: P2 文件拆分批次 (預估 4-5h)

#### S7-A: risk_config.rs 拆分

- **文件**: `rust/openclaw_engine/src/config/risk_config.rs` (1381 行)
- **修復方案**: 默認值函數（~100 個 `fn default_*`）提取到 `config/risk_config_defaults.rs`
- **工作量**: 1h

#### S7-B: governance_routes.py 拆分

- **文件**: `governance_routes.py` (1914 行)
- **修復方案**: 拆為 `governance_auth_routes.py` + `governance_risk_routes.py` + `governance_promotion_routes.py` + 核心
- **工作量**: 2h

#### S7-C: app.js 拆分

- **文件**: `app.js` (2608 行)
- **修復方案**: 拆為 `app-core.js` + `app-actions.js` + `app-config.js`
- **工作量**: 1.5h

### Session S8: P2 策略與 ML 修復 (預估 3h)

#### S8-A: FIX-24/25/26/27 — 策略參數化與修復

- FIX-24: RSI 閾值加入 BbReversionParams (30min)
- FIX-25: GridTrading FEE_PCT 從 config 或 IntentProcessor 注入 (30min)
- FIX-26: BbBreakout 加 squeeze 過期時間 (30min)
- FIX-27: Kelly 負邊際返回 0.1% (15min)

#### S8-B: FIX-34 — decision_outcomes backfill

- **修復方案**: 實現定時 job：掃描 fills → 計算 1m/5m/1h/4h/24h 回報窗口 → 寫入 `trading.decision_outcomes`
- **工作量**: 2h

### Session S9: P2 清理與索引 (預估 2h)

- FIX-21: 3 個孤立 Rust 模組 → `lib.rs` 移除 `pub mod`（或加 `#[cfg(feature = ...)]`）(15min)
- FIX-38: CLAUDE.md §九 Singleton 表更新 (15min)
- FIX-41: app.js connectButton 死代碼清理 (15min)
- FIX-49: 5 個 daily_summary 補建 (30min)
- FIX-50: CHANGELOG 拆分 (30min)
- FIX-51: 3 個 DEPRECATED 文件移至 archive (5min)
- FIX-53: README.md 索引補充 (15min)
- FIX-54: CHANGELOG 缺失 commit 補錄 (15min)
- FIX-56: Layer2 定價表更新 (5min)

---

## Part 4: 並行策略

### 無依賴（可完全並行）

```
S1-A (IPC HMAC)  ─┐
S1-C (ocEsc)     ─┤
S1-D (exec.fast) ─┤── 全部獨立，可同時進行
S2-A (edge tests)─┤
S2-B (REST tests)─┤
S5-A (cookie)    ─┤
S5-C (文檔)      ─┤
S5-D (索引)      ─┘
```

### 有依賴（必須串行）

```
S1-B (FastTrack 完整實現)
  └→ S4-A (on_tick 拆分) — 需先完成 FastTrack 新增代碼，再一起拆分

S3-B (grid_levels 接線) + S3-C (OU theta)
  └→ S8-A (策略參數化) — 同一批策略文件修改

S2-A+B+C (P0 測試)
  └→ S6-A+B+C (P1 測試) — 測試 session 串行避免編譯衝突

S7-A+B+C (文件拆分)
  └→ 依賴 S4-A 完成後再處理 on_tick 相關文件
```

### 最優執行序列

```
Phase 1 (Day 1): S1 全部 + S2-A/B 並行 + S5-A/C/D 並行
Phase 2 (Day 1-2): S2-C + S3 全部 + S5-B
Phase 3 (Day 2): S4-A (on_tick 拆分) + S6 全部
Phase 4 (Day 3): S7 (文件拆分) + S8 + S9
```

---

## Part 5: Session 拆分建議

### Session 1: 「P0 安全與風控」(獨立，可立即開始)
- **Scope**: FIX-03/04/09/10/19
- **預期產出**: FastTrack 完整 + IPC Live guard + ocEsc 修復 + exec.fast fee 補全
- **Agent 組合**: E1（主編碼）+ E1a（Bybit 部分）+ E2（審查）+ E4（測試）
- **跨 session 依賴**: 無（獨立）
- **預估時間**: 3-4h
- **Context 友好度**: 集中在 on_tick.rs + ipc_server + common.js + bybit_private_ws，文件數可控

### Session 2: 「P0 測試補全」(獨立，可與 S1 並行)
- **Scope**: FIX-13/14/15
- **預期產出**: edge_estimates 10 tests + REST timeout 3 tests + 三管線並發 3 tests
- **Agent 組合**: E4（主測試）+ E2（審查）
- **跨 session 依賴**: 無
- **預估時間**: 4-5h

### Session 3: 「P1 風控策略修復」(依賴 S1 完成)
- **Scope**: FIX-05/06/07/22
- **預期產出**: correlated_exposure 接線 + grid_levels 接線 + OU 修復 + ML switches 處理
- **Agent 組合**: E1（編碼）+ QC（數學驗證）+ E2 + E4
- **跨 session 依賴**: 無強依賴，但建議在 S1 後（FastTrack 修復穩定後再改 on_tick 相關）
- **預估時間**: 3h

### Session 4: 「P1 on_tick 重構」(依賴 S1+S3 完成)
- **Scope**: FIX-29/30/32 + E5 S-01/S-02/S-03/S-04
- **預期產出**: on_tick 從 1228 行降至 ~800 行，7 子方法 + 3 工具函數
- **Agent 組合**: E1（重構）+ E5（優化指導）+ E2 + E4
- **跨 session 依賴**: **必須在 S1（FastTrack）和 S3 之後**，因為會修改 on_tick 同區域代碼
- **預估時間**: 3-4h

### Session 5: 「P1 安全 + GUI + 文檔」(獨立)
- **Scope**: FIX-11/39/40/47/48/52
- **預期產出**: cookie 修復 + 2 個 modal 升級 + 3 份文檔更新
- **Agent 組合**: E1（GUI）+ A3（UX 驗證）+ TW（文檔）+ R4（索引）
- **跨 session 依賴**: 無
- **預估時間**: 2-3h

### Session 6: 「P1 測試補全第二批」(建議在 S4 後)
- **Scope**: FIX-16/17/18
- **預期產出**: startup 可測部分 5 tests + hot-reload 並發 3 tests + Price=0 邊界 2 tests
- **Agent 組合**: E4 + E2
- **跨 session 依賴**: 建議在 S4 後（on_tick 結構穩定後再寫新測試）
- **預估時間**: 3h

### Session 7: 「P2 文件拆分」(依賴 S4 完成)
- **Scope**: FIX-08 的 risk_config.rs + governance_routes.py + app.js
- **預期產出**: 3 個嚴重超標文件降至 1200 以下
- **Agent 組合**: E1 + E5 + E2 + E4
- **跨 session 依賴**: S4 完成後（on_tick.rs 已拆分，不會衝突）
- **預估時間**: 4-5h

### Session 8: 「P2 策略與 ML」(獨立)
- **Scope**: FIX-24/25/26/27/34
- **預期產出**: 4 個策略參數化修復 + decision_outcomes backfill writer
- **Agent 組合**: E1 + QC + E4
- **跨 session 依賴**: 無（不同文件）
- **預估時間**: 3h

### Session 9: 「P2 清理與索引」(獨立，低優先級)
- **Scope**: FIX-21/38/41/49/50/51/53/54/56
- **預期產出**: 死代碼清理 + 文檔索引更新
- **Agent 組合**: E1 + TW + R4
- **跨 session 依賴**: 無
- **預估時間**: 2h

### 執行時間線建議

```
Day 1 (W22-Mon):
  ├─ Session 1 (P0 安全風控) ────── AM   [E1+E1a+E2+E4]
  └─ Session 2 (P0 測試) ────────── PM   [E4+E2]         並行

Day 2 (W22-Tue):
  ├─ Session 3 (P1 風控策略) ────── AM   [E1+QC+E2+E4]
  ├─ Session 5 (P1 安全+GUI+文檔) ─ AM   [E1+A3+TW+R4]   並行
  └─ Session 4 (P1 on_tick 重構) ── PM   [E1+E5+E2+E4]

Day 3 (W22-Wed):
  ├─ Session 6 (P1 測試第二批) ──── AM   [E4+E2]
  └─ Session 7 (P2 文件拆分) ────── PM   [E1+E5+E2+E4]

Day 4 (W22-Thu):
  ├─ Session 8 (P2 策略+ML) ─────── AM   [E1+QC+E4]
  └─ Session 9 (P2 清理索引) ────── PM   [E1+TW+R4]
```

**預計 4 個工作日完成全部 P0+P1+核心 P2 修復。**

### 新增測試預估

| Session | 新增測試數 |
|---------|-----------|
| S1 | +6 (FastTrack 4 + IPC 1 + exec.fast 1) |
| S2 | +16 (edge 10 + REST 3 + 三管線 3) |
| S3 | +5 (correlated 2 + grid 2 + OU 1) |
| S4 | 0 (重構，現有 67 tests 全 pass) |
| S5 | 0 (GUI/文檔) |
| S6 | +10 (startup 5 + hot-reload 3 + Price=0 2) |
| S8 | +4 (策略修復測試) |
| **合計** | **+41 tests** |

完成後測試基線：**1355 + 41 = ~1396 Rust** / Python 不變。

---

*報告由 PA (Project Architect) 角色生成*
*基於 12 份審計報告綜合分析 + P0/P1 代碼實地驗證*
*2026-04-12*


---

# 3. FA — 功能規格驗證 + Gap 分析 + 死代碼

> 原始文件：`docs/CCAgentWorkSpace/FA/2026-04-12--full_chain_audit_report.md`

# FA 全鏈路審計報告 — Full Program Chain Audit
**日期**: 2026-04-12
**審計範圍**: Rust openclaw_engine (121 .rs / 54,952 行) + Python program_code (141,249 行 excl .venv)
**基線**: CLAUDE.md §三 所有宣稱功能 vs 實際代碼

---

## 一、功能規格驗證 — Feature Specification Verification

### 1.1 3E-ARCH 三引擎並行架構

**宣稱**: Paper/Demo/Live 三管線獨立並行，`build_exchange_pipeline()` 按 API key 獨立構建。

**驗證結果**: **PASS**
- `main.rs:202-213` — `build_exchange_pipeline()` 分別為 Live/Demo 構建，Paper 始終啟動
- `main.rs:232-244` — 每管線獨立 `UnboundedChannel` 命令通道
- `startup.rs:149-191` — `PerEngineRiskStores` 三獨立 ConfigStore
- `pipeline_types.rs` — `PipelineKind` enum (Paper/Demo/Live)
- `TradingMode` 已徹底刪除，確認無殘留

### 1.2 StrategyAction Enum

**宣稱**: 策略 `on_tick()` 返回 `Vec<StrategyAction>`，Close 走輕量路徑。

**驗證結果**: **PASS**
- `strategies/mod.rs:61` — `fn on_tick(&mut self, ctx: &TickContext) -> Vec<StrategyAction>`
- 5 策略全部實作 `on_tick()` 返回 `Vec<StrategyAction>`:
  - `ma_crossover.rs:299`
  - `bb_reversion.rs:214`
  - `bb_breakout.rs:242`
  - `grid_trading.rs:630`
  - `funding_arb.rs:124` (stub — 返回 `vec![]`)

### 1.3 Scanner Phase A-D

**宣稱**: ScannerRunner 完整接線，動態 symbol 管理。

**驗證結果**: **PASS**
- `scanner/runner.rs` — `ScannerRunner` 完整實作：REST fetch → score → registry → WS topic change
- `scanner/scorer.rs` — 評分邏輯 + correlation filter
- `scanner/registry.rs` — SymbolRegistry + anti-churn
- `scanner/config.rs` — ScannerConfig TOML
- `main.rs:127-188` — Scanner 完整接線到 startup

### 1.4 Phase 6 Reconciler 自動降級

**宣稱**: Reconciler 從 AUDIT-ONLY 升級為自動動作層，漂移→escalation→恢復。

**驗證結果**: **PASS**
- `position_reconciler/mod.rs` — 完整 MODULE_NOTE 描述 Phase 6 自動降級
- `position_reconciler/escalation.rs` — `ReconcilerState` + `evaluate_actions()` + 升降級
- 5 級分類 (Match/MinorDrift/MajorDrift/Orphan/Ghost) 確認存在

### 1.5 News Pipeline (A2)

**宣稱**: 60s 定時排程器，3 providers → 去重 → severity → fan-out。

**驗證結果**: **PASS**
- `news/mod.rs` — 完整模組：cryptopanic/rss/dedup/severity/router/pipeline
- `tasks.rs:282` — `news_pipeline_enabled` switch 實際 gate 控制
- `news/router.rs` — Guardian/Regime/Learning 三路 fan-out

### 1.6 Claude Teacher Pipeline

**宣稱**: Phase 4 sub-task 4-01，directive fetch/parse/persist。

**驗證結果**: **PASS（結構完整，但需 API key 才能真正運行）**
- `claude_teacher/mod.rs` — 完整子模組：client/parser/writer/applier/consumer_loop/outcome_tracker
- `claude_teacher/consumer_loop.rs` — `TeacherConsumerLoop` 完整實作
- `tasks.rs:217` — IPC handle injection，default-off
- `claude_teacher/applier.rs:477` — `boost_arm` 仍為 stub（4-06 留尾）

### 1.7 LinUCB Contextual Bandit

**宣稱**: 純 Rust 推理層。

**驗證結果**: **PASS**
- `linucb/mod.rs` — 完整子模組：inference/runtime/state_io/schema_hash/arms_v1_15
- `linucb/inference.rs` — ridge-regression LinUCB 推理實作
- `decision_context_producer.rs` — 運行時使用 `LinUcbRuntime::select_for_intent()`

### 1.8 ConfigStore + Hot-Reload

**宣稱**: ArcSwap 熱加載，4 IPC 寫入面。

**驗證結果**: **PASS**
- `config/store.rs` — `ConfigStore<T>` with `ArcSwap`
- `ipc_server/mod.rs` — `set_config_stores()` 注入
- `ipc_server/handlers.rs` — `patch_risk_config` / `patch_learning_config` IPC handlers

### 1.9 Live GUI Phase 1-6

**宣稱**: 完整 Live 操作面板。

**驗證結果**: **PASS（Python 側確認）**
- `live_session_routes.py` (1203 行) — 完整 live session lifecycle
- `live_trust_routes.py` — earned trust engine endpoints
- `settings_routes.py` — API key 管理
- `strategy_wiring.py` — DI wiring for all agents

### 1.10 Multi-Symbol Position Tracking

**宣稱**: 4 策略從單一 `Option<bool>` 改為 `HashMap<String, bool>`。

**驗證結果**: **PASS**
- `strategies/ma_crossover.rs` — `positions: HashMap<String, bool>`
- `strategies/bb_reversion.rs` — 同上
- `strategies/bb_breakout.rs` — 同上
- `strategies/grid_trading.rs` — `active_grids: HashMap<String, ...>`

---

## 二、Gap 分析 — Implementation Gap Analysis

### 2.1 [BLOCKER] AI 治理層 H1-H5 — Rust 引擎完全未接入

**嚴重程度**: BLOCKER（與憲法原則 #3 "AI 輸出 ≠ 即時命令" 矛盾）

**現狀**:
- CLAUDE.md §十 明確標註「H1-H5 AI agent 目前全 stub」
- `ai_service.py:124-128` — 所有 5 個 handler 返回 stub response：
  - `_handle_strategist`: 返回 `action: "hold", confidence: 0.0`
  - `_handle_analyst`: 返回空 analysis
  - `_handle_conductor`: 返回 `maintain_current`
  - `_handle_scout`: 返回空 intel
  - `_handle_guardian`: 返回 `approved` (stub 通過一切！)
- **Rust 引擎根本不調用 `ai_service.sock`** — grep `ai_service|strategist_evaluate|guardian_check` 在 Rust 源碼中零結果
- Python 側 Agent 類存在且接線完整（`strategy_wiring.py` 實例化 Scout/Strategist/Guardian/Analyst/Executor + Conductor），但**僅運行在 Python 管線內**，與 Rust 引擎完全隔離

**影響**:
- Rust 引擎的交易決策完全由確定性策略驅動，無 AI 治理層介入
- 原則 #3 (Decision Lease) 在 Rust 引擎路徑中未執行
- 原則 #13 (AI 資源成本感知) 對 Rust 路徑無效

**文件位置**:
- `ai_service.py:231-260` (stub handlers)
- `strategy_wiring.py:110-269` (Python agent wiring)
- CLAUDE.md §十 路線圖確認 W22-W23 才計劃接入

### 2.2 [BLOCKER] Fast Track ReduceToHalf / PauseNewEntries 未實作

**嚴重程度**: BLOCKER（風控閉環缺口）

**現狀**:
- `fast_track.rs:17-18` — `ReduceToHalf` 和 `PauseNewEntries` 兩個 enum variant 已定義
- `fast_track.rs:46,51` — `evaluate_fast_track()` 會返回這兩個值
- **但 `tick_pipeline/on_tick.rs` 僅處理 `CloseAll`**:
  ```
  on_tick.rs:161: if ft_action == FastTrackAction::CloseAll { ... }
  ```
  `ReduceToHalf` 和 `PauseNewEntries` 被完全忽略（沒有 else if 分支）
- 即使 `CloseAll` 路徑，`price_drop_pct` 和 `margin_utilization_pct` 永遠傳入 `0.0` (`on_tick.rs:158-159`)，
  閃崩和保證金危機分支永遠不會觸發

**影響**:
- Defensive 模式下不會自動減倉
- Reduced 模式下不會暫停新開倉
- 唯一可觸發的風控動作是 `risk_level >= CircuitBreaker` → CloseAll

**文件位置**:
- `fast_track.rs:17-18,46,51`
- `tick_pipeline/on_tick.rs:148-161`

### 2.3 [MAJOR] Decision Lease 系統 — Python 實作完整但 Rust 未使用

**嚴重程度**: MAJOR

**現狀**:
- `decision_lease_state_machine.py` — 9 狀態、20+ 遷移的完整狀態機（553 行）
- `governance_hub.py` — `acquire_lease()` / `release_lease()` 已實作
- `executor_agent.py` — `ExecutorAgent.execute_order()` 調用 `acquire_lease()`
- **但 Rust IntentProcessor 直接處理 Open/Close 而不經過 Decision Lease**
- Rust 引擎的 `intent_processor/router.rs` 有 Guardian/cost_gate/Kelly 門控，但無 lease 概念

**影響**: Rust 引擎路徑缺少 "帶時效、可撤銷" 的決策租約機制

**文件位置**:
- `decision_lease_state_machine.py:1-553`
- `intent_processor/router.rs:209` (cost gate 存在但無 lease)

### 2.4 [MAJOR] FundingArb 策略 — 完整 stub

**嚴重程度**: MAJOR

**現狀**:
- `strategies/funding_arb.rs:6-9` — MODULE_NOTE 明確標註 "Currently stub (on_tick returns vec![])"
- `funding_arb.rs:124-138` — `on_tick()` 返回 `vec![]`（空動作）
- 所有內部邏輯（`compute_edge`, `should_exit` 等）標註 `#[allow(dead_code)]`
- 等待 OC-5 REST wiring + R-06 Python IPC 提供資金費率

**影響**: 5 策略中僅 4 個活躍，FundingArb 佔位但無功能

**文件位置**: `strategies/funding_arb.rs:124-138`

### 2.5 [MAJOR] Phase 5 Cost Gate / James-Stein — 暫停（策略 edge 為負）

**嚴重程度**: MAJOR

**現狀**:
- `edge_estimates.rs` — PH5-WIRE-1 JS shrunk edge cache 代碼完整
- `intent_processor/gates.rs:7-139` — cost gate helper 代碼完整
- `intent_processor/router.rs:209` — Gate 3 cost gate 已接線
- **但**: PNL-FIX-1/2 揭露所有策略 gross edge 為負
  - bb_reversion -0.46 bps / ma_crossover -2.64 bps / grid_trading -0.67 bps
- 代碼保留但等正向 edge 策略接入才有意義

**影響**: Cost gate 機械正確但餵的是污染/負 edge 輸入

**文件位置**:
- `edge_estimates.rs:1-171`
- `intent_processor/gates.rs:7-139`
- CLAUDE.md Phase 5 PAUSED 段落

### 2.6 [MAJOR] Learning Pipeline — 部分實作

**嚴重程度**: MAJOR

**現狀**:
- LinUCB 推理層：完整 (**PASS**)
- Claude Teacher pipeline：結構完整，default-off (**PASS**)
- Decision Context Snapshots：完整寫入通道 (**PASS**)
- **缺失**:
  - LinUCB online update（4-06 warm-start 明確標註 NOT included）
  - `boost_arm` 在 `applier.rs:477` 仍為 stub
  - `linucb_enabled` config switch 從未在運行時代碼中讀取（僅定義+測試）
  - `thompson_enabled` config switch 未使用
  - `scorer_enabled` config switch 未使用
  - `directive_apply_enabled` config switch 未使用

**影響**: Learning 管線建設中，核心骨架在但離 "自動學習" 仍有距離

### 2.7 [MINOR] Claude Teacher `boost_arm` — Stub

**現狀**: `claude_teacher/applier.rs:477-521` — `boost_arm` 明確標註 stub，留給 4-06

**文件位置**: `claude_teacher/applier.rs:477`

---

## 三、死代碼檢驗 — Dead Code Analysis

### 3.1 [MAJOR] Rust 孤立模組 — 3 個模組從未被引用（1,612 行）

| 模組 | 行數 | 說明 |
|------|------|------|
| `leverage_token_client.rs` | 503 | Bybit 槓桿代幣 API 封裝，`lib.rs` 聲明但無任何其他文件引用 |
| `spot_margin_client.rs` | 534 | Bybit 現貨保證金 API 封裝，`lib.rs` 聲明但無引用 |
| `batch_order_manager.rs` | 575 | 批量訂單管理器，`lib.rs` 聲明但無引用 |

**影響**: 1,612 行完全未使用的代碼，增加編譯時間和維護負擔

**文件位置**:
- `leverage_token_client.rs` (全文)
- `spot_margin_client.rs` (全文)
- `batch_order_manager.rs` (全文)

### 3.2 [MAJOR] `Orchestrator::dispatch_tick()` — 生產環境死碼

**現狀**:
- `orchestrator.rs:38` — `dispatch_tick()` 標註 `#[allow(dead_code)]`
- 註釋明確說明 "Not called in production since RC-04 (per-strategy loop in tick_pipeline)"
- 生產環境使用 `tick_pipeline` 直接逐策略循環

**文件位置**: `orchestrator.rs:32-47`

### 3.3 [MAJOR] MlSwitches 死 config — 4 個開關從未在運行時讀取

| Config 欄位 | 文件:行 | 運行時使用 |
|-------------|---------|-----------|
| `linucb_enabled` | `learning_config.rs:86` | 僅在測試中 assert，運行時無人讀取 |
| `thompson_enabled` | `learning_config.rs:89` | 零使用 |
| `scorer_enabled` | `learning_config.rs:106` | 零使用 |
| `directive_apply_enabled` | `learning_config.rs:101` | 零使用 |

**對比**: `news_pipeline_enabled` 和 `teacher_loop_enabled` 確實在運行時被讀取使用

**影響**: Operator 可通過 IPC 修改這些開關值，但引擎不會有任何行為變化（假功能）

**違反規則**: MEMORY.md `feedback_no_dead_params.md` — "Agent 可調參數必須真實被發現/調整/持久化"

### 3.4 [MAJOR] `fast_track::ReduceToHalf` / `PauseNewEntries` — 定義但未處理

**現狀**: enum variant 已定義，`evaluate_fast_track()` 會返回，但 `on_tick.rs` 僅處理 `CloseAll`

**文件位置**: `fast_track.rs:17-18` + `tick_pipeline/on_tick.rs:148-161`

### 3.5 [MINOR] FundingArb 內部邏輯 — 9 處 `#[allow(dead_code)]`

**現狀**: `strategies/funding_arb.rs` 有 9 個 `#[allow(dead_code)]` 標註
- 所有常量 (TOTAL_COST_BPS / DEFAULT_EXPECTED_PERIODS / FUNDING_THRESHOLD / MAX_BASIS_PCT / MAX_HOLD_MS)
- struct 欄位
- `compute_edge()` / `should_exit()` 函數

**文件位置**: `strategies/funding_arb.rs:15-66`

### 3.6 [MINOR] Python `PIPELINE_BRIDGE = None` / `STOP_MANAGER = None`

**現狀**:
- `strategy_wiring.py:285-286` — 兩者設為 None
- `strategy_read_routes.py:369` — `PIPELINE_BRIDGE` 仍被判 None 後返回空
- DEAD-PY-2 清理後的殘留引用

**文件位置**: `strategy_wiring.py:285-286`, `strategy_read_routes.py:369-372`

### 3.7 [MINOR] Python `delegation_framework.py` — 562 行未被引用

**現狀**: 完整的四階段放權框架實作（562 行），但無任何文件 import 它

**文件位置**: `delegation_framework.py` (全文)

### 3.8 [MINOR] Python `backtest_engine.py` — 1,352 行未被運行時引用

**現狀**: 回測引擎，僅在測試中可能使用，非運行時代碼

**文件位置**: `local_model_tools/backtest_engine.py` (全文)

---

## 四、文件大小違規 — File Size Violations

### 4.1 [MAJOR] 超過 1200 行硬上限的源文件

**Rust 源文件**:

| 文件 | 行數 | 超標量 | 說明 |
|------|------|--------|------|
| `config/risk_config.rs` | 1,381 | +181 | Config 定義 + 驗證 + 測試 |
| `event_consumer/mod.rs` | 1,302 | +102 | 事件消費者主體 |
| `claude_teacher/applier.rs` | 1,257 | +57 | Directive 應用器 + 測試 |
| `tick_pipeline/on_tick.rs` | 1,228 | +28 | 核心 tick 處理 |

**Python 源文件**:

| 文件 | 行數 | 超標量 | 說明 |
|------|------|--------|------|
| `governance_routes.py` | 1,914 | +714 | **嚴重超標** — CLAUDE.md 已標記為 pre-existing 留尾 |
| `governance_hub.py` | 1,812 | +612 | GovernanceHub 核心 |
| `signal_generator.py` | 1,452 | +252 | 信號生成器 |
| `backtest_engine.py` | 1,352 | +152 | 回測引擎 |
| `live_session_routes.py` | 1,203 | +3 | Live session 路由 |

### 4.2 [MINOR] 超過 800 行警告線的 Rust 文件

| 文件 | 行數 |
|------|------|
| `ipc_server/handlers.rs` | 1,192 |
| `tick_pipeline/mod.rs` | 1,192 |
| `tick_pipeline/tests.rs` | 1,190 |
| `strategies/grid_trading.rs` | 1,158 |
| `order_manager.rs` | 1,151 |
| `ipc_server/tests.rs` | 1,059 |
| `bybit_rest_client.rs` | 1,054 |
| `database/drift_detector.rs` | 1,010 |
| `ipc_server/mod.rs` | 994 |
| `bybit_private_ws.rs` | 992 |
| `main.rs` | 950 |
| `ws_client.rs` | 923 |
| `event_consumer/tests.rs` | 887 |
| `startup.rs` | 856 |
| `position_manager.rs` | 839 |

---

## 五、其他發現

### 5.1 [INFO] Python Agent 層 vs Rust 引擎 — 雙軌運行確認

Python 側 5-Agent 框架（`multi_agent_framework.py` 1,104 行）已完整實作：
- `ScoutAgent` — 市場情報收集
- `StrategistAgent` — 策略評估（含 H1 ThoughtGate / H3 ModelRouter / H4 Validator）
- `GuardianAgent` — 風控審查
- `AnalystAgent` — 交易分析
- `ExecutorAgent` — 執行代理
- `Conductor` — 編排器
- `MessageBus` — 結構化通信

所有 Agent 在 `strategy_wiring.py:110-269` 中實例化並接線至 MessageBus。
但這套系統**僅運行在 Python GUI/API 管線中**，Rust 引擎的核心交易路徑完全不經過這些 Agent。

### 5.2 [INFO] Earned Trust Engine / Promotion Pipeline — 獨立但就緒

- `earned_trust_engine.py` (EarnedTrustEngine) — 贏得信任引擎，完整
- `promotion_pipeline.py` (PromotionPipeline) — 5 階段漸進放權，完整
- `evolution_engine.py` — 演化引擎，完整
- 三者獨立運行，等待 Agent 層接入

### 5.3 [INFO] `price_drop_pct` / `margin_utilization_pct` 硬編 0 — 已知已標記

`on_tick.rs:149-159` 已有 PNL-4 標記和詳細 tracing::warn，已進入 TODO 追蹤

---

## 六、總結表 — Summary Table

| # | 嚴重性 | 類別 | 發現 | 影響範圍 | 文件位置 |
|---|--------|------|------|----------|----------|
| 1 | BLOCKER | Gap | H1-H5 AI 治理層全 stub，Rust 引擎未接入 | 原則 #3/#13 未執行 | `ai_service.py:231-260` |
| 2 | BLOCKER | Gap | FastTrack ReduceToHalf/PauseNewEntries 未處理 | 風控閉環缺口 | `on_tick.rs:148-161` |
| 3 | MAJOR | Gap | Decision Lease Python 完整但 Rust 未使用 | 原則 #3 部分失效 | `decision_lease_state_machine.py` |
| 4 | MAJOR | Gap | FundingArb 策略完整 stub | 5 策略僅 4 活躍 | `funding_arb.rs:124-138` |
| 5 | MAJOR | Gap | Phase 5 Cost Gate 暫停（策略 edge 負） | 成本感知無效 | `edge_estimates.rs` |
| 6 | MAJOR | Gap | Learning Pipeline 部分實作（4 死 switch） | 學習能力受限 | `learning_config.rs:86-106` |
| 7 | MAJOR | Dead | 3 Rust 孤立模組（1,612 行） | 編譯/維護負擔 | `leverage_token_client.rs` 等 |
| 8 | MAJOR | Dead | 4 MlSwitches config 欄位未運行時讀取 | 假功能違反規則 | `learning_config.rs:86-106` |
| 9 | MAJOR | Size | governance_routes.py 1,914 行 | 超 1200 硬上限 +714 | `governance_routes.py` |
| 10 | MAJOR | Size | governance_hub.py 1,812 行 | 超 1200 硬上限 +612 | `governance_hub.py` |
| 11 | MAJOR | Size | 4 Rust 文件超 1200 行 | §九硬上限違規 | 見 §四.1 表 |
| 12 | MINOR | Gap | boost_arm stub（4-06 留尾） | Teacher 功能不完整 | `applier.rs:477` |
| 13 | MINOR | Dead | Orchestrator::dispatch_tick() 生產死碼 | 維護混淆 | `orchestrator.rs:38` |
| 14 | MINOR | Dead | PIPELINE_BRIDGE/STOP_MANAGER None 殘留 | 清理不完整 | `strategy_wiring.py:285-286` |
| 15 | MINOR | Dead | delegation_framework.py 未被引用 | 562 行孤立代碼 | `delegation_framework.py` |
| 16 | MINOR | Dead | backtest_engine.py 非運行時代碼 | 1,352 行非必要 | `backtest_engine.py` |
| 17 | INFO | Arch | Python Agent 層與 Rust 引擎完全隔離 | 雙軌架構確認 | `strategy_wiring.py` |
| 18 | INFO | Note | price_drop/margin_util 硬編 0 已標記 | PNL-4 追蹤中 | `on_tick.rs:149-159` |

---

## 七、建議優先級

1. **W22 G-1 AI Agent 接入**（BLOCKER #1）：Rust IPC → Python AIService 接入是最高優先級
2. **FastTrack 補完**（BLOCKER #2）：`on_tick.rs` 添加 ReduceToHalf/PauseNewEntries 處理分支
3. **死 config switch 清理**（MAJOR #8）：要麼接線要麼刪除，消滅假功能
4. **孤立模組清理**（MAJOR #7）：從 `lib.rs` 移除 3 個 `pub mod` 聲明
5. **governance_routes.py 拆分**（MAJOR #9）：已知留尾，需排入近期計劃
6. **price_drop_pct/margin_utilization 接線**（INFO #18）：計算閃崩和保證金使用率

---

*報告由 FA (Functional Architect) 角色生成，審計時間 2026-04-12*


---

# 4. AI-E — AI 使用效果與可接入度評估

> 原始文件：`docs/CCAgentWorkSpace/AI-E/2026-04-12--ai_usage_assessment_report.md`

# AI 使用效果評估報告 / AI Usage Assessment Report

**角色**: AI-E (AI Engineer)
**日期**: 2026-04-12
**範圍**: OpenClaw/Bybit AI Agent 交易系統全部 AI/LLM 集成點

---

## 一、AI 集成點總覽 / AI Integration Points Overview

### 1.1 系統 AI 架構（設計 vs 實現）

設計架構宣稱 5 層 AI 治理（H0-H5）+ 5 Agent 系統 + Layer 2 深度推理 + ML/RL 學習管線。以下逐一評估真實狀態。

| 組件 | 狀態 | 說明 |
|------|------|------|
| H0 本地判斷（確定性） | ✅ Production | 純規則邏輯，無 AI 調用 |
| H1 ThoughtGate | ⚠️ Partial | 代碼完整但僅在 Python Agent 鏈中使用，未接入 Rust tick pipeline |
| H2 Budget Gate | ⚠️ Partial | Python Layer2CostTracker 完整；Rust ai_budget 完整但 teacher_loop 默認 OFF |
| H3 ModelRouter | ⚠️ Partial | 路由邏輯完整（l1_9b/l1_27b/l2 三層），但實際 LLM 調用依賴 Ollama 是否在線 |
| H4 Validator | ✅ Production | 純驗證邏輯，代碼完整且有測試覆蓋 |
| H5 Cost Logging | ✅ Production | Layer2CostTracker + Rust BudgetTracker 雙軌，代碼完整 |
| Layer 2 AI Engine | ⚠️ Partial | Claude API 集成代碼完整，但需 ANTHROPIC_API_KEY 才能運行 |
| 5 Agent 系統 | ⚠️ Partial | 框架完整但全部運行在 Shadow 模式 |
| ML 學習管線 | ⚠️ Partial | 代碼完整但缺數據，未投產 |
| 新聞管線 | ✅ Production | Rust 側 3 providers + 60s 排程，已接入 main.rs |

---

## 二、逐組件深度評估 / Detailed Component Assessment

### 2.1 LocalLLMClient 抽象層

**狀態**: ✅ Production — 接口設計完整

- **文件**: `/home/ncyu/BybitOpenClaw/srv/program_code/local_model_tools/local_llm_client.py`
- **ABC 接口**: `LocalLLMClient`（L59-116），定義 `generate()` / `is_available()` / `get_model_info()` / `provider_name`
- **兩個實現**:
  - `OllamaProvider`（L118-168）：包裝 `OllamaClient`，代理所有調用
  - `LMStudioProvider`（L170-252）：OpenAI 兼容 API，`localhost:1234`
- **評級理由**: ABC 清晰，兩個 provider 均可運行。但實際業務代碼大多直接用 `OllamaClient` 而非通過 `LocalLLMClient` 抽象層，抽象層的使用率偏低。

### 2.2 OllamaClient（本地 LLM 推理）

**狀態**: ✅ Production — 唯一真實運行的 LLM 調用入口

- **文件**: `/home/ncyu/BybitOpenClaw/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/ollama_client.py`
- **配置**: 默認模型 `qwen3.5:9b-q4_K_M`（L48），27B 變體 `qwen3.5:27b-q4_K_M`（L497）
- **端點**: `http://127.0.0.1:11434`（Ollama REST API）
- **功能**:
  - `generate()`（L197-238）：單輪 `/api/generate`，支持 `think` 參數控制 CoT
  - `chat()`（L242-287）：多輪 `/api/chat`
  - `classify()`（L291-331）：文本分類（低溫度 0.1，短回答）
  - `judge_edge()`（L333-363）：交易邊際判斷（JSON 輸出）
  - `is_available()`（L126-170）：60s TTL 緩存，1s 超時健康檢查
- **安全**: `max_retries=0`（CLAUDE.md 硬邊界，L63），fail-closed
- **單例**: `get_ollama_client()` + `get_ollama_client_27b()`（L466-498），線程安全
- **評級理由**: 代碼品質高，生產就緒。前提是 Ollama 服務在線且模型已加載。

### 2.3 Layer 2 AI 推理引擎（Claude API 集成）

**狀態**: ⚠️ Partial — 代碼完整但需 API Key 才能運行

#### 2.3.1 Layer2Engine

- **文件**: `/home/ncyu/BybitOpenClaw/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/layer2_engine.py`
- **L1 Triage**（L197-340）：
  - **首選**: Claude Haiku（`claude-haiku-4-5-20251001`，L52）經 Anthropic SDK 調用
  - **回退**: `_l1_triage_local()`（L259-340）通過 Ollama/Qwen 本地推理
  - 這是**真實的 Claude API 調用**（L218-228），不是 stub
- **L2 Agent Loop**（L344-558）：
  - 完整的 Claude messages API + tool_use 循環
  - 8 個工具定義（get_market_state, web_search, submit_recommendation 等）
  - 模型升級 triage（Sonnet → Opus，L562-605）
  - Shadow decision 提交到 paper trading（L609-678）
- **Anthropic Client**（L699-731）：
  - `_get_anthropic_client()` 讀取 `ANTHROPIC_API_KEY` 環境變量
  - **無 key 時返回 None**，L2 session 直接 fail-soft，不會崩潰
  - **真實 SDK 調用**：`import anthropic; anthropic.Anthropic(api_key=...)`（L718-719）

#### 2.3.2 Layer2CostTracker

- **文件**: `/home/ncyu/BybitOpenClaw/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/layer2_cost_tracker.py`
- **硬上限**: `$2.00/天`（L60，DOC-08 §4）
- **自適應預算**: 7 日 ROI 驅動倍率（0.3x - 2.0x），5 個 tier（L66-72）
- **PnL 歸因回填**: `backfill_pnl_attribution()`（L321-333）
- **統一調用記錄**: `record_call()`（L490-553）支持 Ollama/Claude/Perplexity 全 provider
- **持久化**: `runtime/layer2_cost_state.json`，原子寫入（tmp→replace）
- **狀態**: ✅ Production — 完全可用

#### 2.3.3 Layer2 工具系統

- **文件**: `/home/ncyu/BybitOpenClaw/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/layer2_tools.py`
- **8 個工具 schema**（L67-286）：完整的 Anthropic tool_use JSON schema
- **4 層 SearchProvider 降級**:
  1. `PerplexitySearchProvider`（L293-382）：需 `PERPLEXITY_API_KEY`
  2. `LocalLLMWebSearchProvider`（L385-445）：Ollama + web-pilot 腳本
  3. `LocalLLMSearchProvider`（L448-491）：純 Ollama 知識
  4. `WebPilotSearchProvider`（L494-541）：DuckDuckGo (`duckduckgo-search` 庫)
- **SSRF 防護**: `_fetch_url()` 含 IP/域名黑名單（L809-826）
- **狀態**: ✅ Production（工具代碼完整，但 Perplexity 需 API key）

#### 2.3.4 Layer2 API 路由

- **文件**: `/home/ncyu/BybitOpenClaw/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/layer2_routes.py`
- **10 條路由**（L57-435）：trigger / sessions / cost / pricing / adaptive / config / ollama/status
- **GUI**: `tab-ai.html` 完整的 AI Engine 控制台（成本儀表板 + 觸發按鈕 + session 列表）
- **狀態**: ✅ Production

#### 2.3.5 Layer2 類型系統

- **文件**: `/home/ncyu/BybitOpenClaw/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/layer2_types.py`
- **定價表**: Haiku $0.80/$4.00、Sonnet $3.00/$15.00、Opus $15.00/$75.00（L334-353）
  - ⚠️ **注意**: `last_verified_date: "2026-03-27"`，已超 30 天，`is_stale()` 會返回 True
- **模型 ID**: 使用 `claude-haiku-4-5-20251001` / `claude-sonnet-4-6-20250326` / `claude-opus-4-6-20250326`（L51-55）
- **狀態**: ✅ Production

### 2.4 H1-H5 治理層

#### H1 ThoughtGate

- **文件**: `/home/ncyu/BybitOpenClaw/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/h1_thought_gate.py`
- **功能**: AI 調用前確定性閘門 — 預算檢查 + 複雜度評分（閾值 0.3）+ 冷卻期（30s 同 symbol 去重）
- **調用鏈**: `StrategistAgent._evaluate_intel()` → `H1ThoughtGate.check()` → 決定是否調用 Ollama
- **狀態**: ⚠️ Partial — 代碼完整且正確，但只在 Python multi-agent 框架中使用。**Rust tick pipeline 不經過 H1**。

#### H3 ModelRouter

- **文件**: `/home/ncyu/BybitOpenClaw/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/model_router.py`
- **路由邏輯**: complexity < 0.5 → l1_9b / 0.5-0.8 → l1_27b / ≥ 0.8 → l2（後台線程）
- **L2 結果緩存**: TTL 1h / 容量 200 條
- **預算閘控**: 可注入 budget_checker callback
- **狀態**: ⚠️ Partial — 同上，僅在 Python Agent 框架中活躍。

#### H4 Validator

- **文件**: `/home/ncyu/BybitOpenClaw/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/h4_validator.py`
- **驗證項**: confidence 範圍 [0,1] / has_edge 布林 / reason 非空 / action 合法集合
- **狀態**: ✅ Production — 純邏輯驗證，代碼無依賴，完整測試覆蓋。

#### H5 Cost Logging

- **Python 側**: `Layer2CostTracker.record_call()`（詳見 §2.3.2）
- **Rust 側**: `ai_budget::BudgetTracker`（詳見 §2.6）
- **狀態**: ✅ Production — 雙語言雙軌道，代碼完整。

### 2.5 5 Agent 系統

| Agent | 文件 | 狀態 | 說明 |
|-------|------|------|------|
| ScoutAgent | `multi_agent_framework.py:376` | ⚠️ Partial | 產出 IntelObject，框架級消息傳遞正常；但依賴 Python 策略管線（已退場） |
| StrategistAgent | `strategist_agent.py` | ⚠️ Partial | 調用 Ollama `judge_edge()` 評估信號邊際；Shadow 模式下不產出下游 intent |
| GuardianAgent | `guardian_agent.py` | ⚠️ Partial | 5 項風控檢查（槓桿/回撤/相關性/Sharpe/方向衝突）；評估依賴 Qwen 3.5 |
| AnalystAgent | `analyst_agent.py` | ⚠️ Partial | L1 層指標計算正常；L2 層 `analyze_patterns()` 需 Qwen 27B |
| ExecutorAgent | `executor_agent.py:117` | ❌ Stub | 框架存在但 ARCH-RC1 後 Python 執行層已退場，Rust 引擎直接處理 |
| Conductor | `multi_agent_framework.py:642` | ⚠️ Partial | 編排 5 Agent 的消息路由正常，但整體 Agent 系統處於 Shadow 模式 |

**關鍵事實**: 5 Agent 系統的代碼框架完整（MessageBus / AgentRole / IntelObject / TradeIntent / RiskVerdict 全部定義），但在 ARCH-RC1 後 Python 交易執行層已退場（DEAD-PY-2），**所有實際交易決策走 Rust tick pipeline**。Python Agent 系統目前的角色是：
1. StrategistAgent 可通過 Ollama 對信號做 AI 評估（judge_edge），但結果是 advisory 非 binding
2. GuardianAgent 的風控邏輯已被 Rust RiskConfig + Reconciler + ConfigStore 取代
3. AnalystAgent 的 L1 指標計算仍有價值（trade attribution），但 L2 pattern discovery 從未投產

### 2.6 Rust 側 AI 基礎設施

#### 2.6.1 AI Budget Tracker（Rust）

- **文件**: `rust/openclaw_engine/src/ai_budget/`（mod.rs + tracker.rs + config_io.rs + pricing.rs + usage_io.rs）
- **功能**: 月度 USD 預算強制（5 scope：local_total / platform_hard_cap / agent_teacher / agent_analyst / agent_reserve）
- **三段降級**: SoftWarn $80 / HardLimit $95 / Killswitch $100
- **DB 表**: `learning.ai_budget_config` + `learning.ai_usage_log`（V010 遷移）
- **IPC**: `get_ai_budget_status` / `update_ai_budget_config` 兩個 handler
- **狀態**: ✅ Production — 代碼完整，DB schema 已部署，IPC 接線完成。定價表為硬編碼占位（4-17 子任務待換為 DB 表）。

#### 2.6.2 Claude Teacher（Rust）

- **文件**: `rust/openclaw_engine/src/claude_teacher/`（7 個子模塊）
- **完整管線**:
  - `client.rs`：`LlmClient` trait（L78）+ `AnthropicClient`（reqwest HTTP）+ `MockClient`
  - `parser.rs`：嚴格 fail-closed JSON 解析（`adjust_param` / `recommend_action` 等 directive 類型）
  - `writer.rs`：寫入 `learning.teacher_directives` + `learning.experiment_ledger`
  - `consumer_loop.rs`：`TeacherConsumerLoop` 定時拉取 directive
  - `applier.rs`：`DirectiveApplier` 應用 directive（改參數/建議動作）
  - `governance_impl.rs`：治理核心包裝
  - `strategy_ipc_impl.rs`：通過 IPC 發送參數調整到策略
  - `outcome_tracker.rs`：Sharpe 追蹤，directive 執行結果回填
- **安全**:
  - `ANTHROPIC_API_KEY` 不存在 → `LlmClientError::MissingApiKey`（fail-closed）
  - BudgetTracker.record_usage 失敗 → 中止（TeacherError::Budget）
  - 測試覆蓋 mock client / budget failure abort / parser rejection
- **狀態**: ⚠️ Partial — 代碼完整且測試覆蓋良好，但：
  - `teacher_loop_enabled` 默認 OFF（L123, learning_config.rs）
  - 需 `ANTHROPIC_API_KEY` 才能發起真實 LLM 調用
  - Directive → 策略參數調整的完整鏈路需 operator IPC 啟用

#### 2.6.3 LinUCB 上下文 Bandit（Rust）

- **文件**: `rust/openclaw_engine/src/linucb/`（5 個子模塊）
- **功能**:
  - `inference.rs`：ridge-regression UCB 計算（theta = A^{-1}b, UCB = theta^T x + alpha * sqrt(x^T A^{-1} x)）
  - `arms_v1_15.rs`：v1_15 cold-start arm 列舉
  - `state_io.rs`：PG 讀寫 `learning.linucb_state`
  - `runtime.rs`：運行時 arm 選擇（`ArmSelection`）
  - `schema_hash.rs`：feature schema hash（fail-closed 版本校驗）
- **Rust tick pipeline 集成**: `on_tick.rs` 中調用 LinUCB `select_arm()` 進行策略選擇
- **Python 訓練對齊**: `ml_training/linucb_trainer.py` 與 Rust BYTEA 編碼逐 byte 對齊
- **狀態**: ⚠️ Partial — 推理代碼完整，但需要足夠的歷史決策數據填充 A/b 矩陣。Cold-start 狀態下等效隨機選擇。

#### 2.6.4 新聞管線（Rust）

- **文件**: `rust/openclaw_engine/src/news/`（pipeline.rs + mod.rs + 其他子模塊）
- **功能**: 3 providers（CryptoPanic + CoinTelegraph RSS + Google News RSS）→ 去重 → severity 評分 → DB 寫入 → 三路 fan-out（Guardian/Regime/Learning）
- **排程**: `main.rs` 中 60s 定時觸發，受 `learning.switches.news_pipeline_enabled` 開關控制
- **狀態**: ✅ Production — 完整接入生產管線，熱重載 gate 控制。

### 2.7 ML/DL 學習管線

#### 2.7.1 Python ML Training 套件

- **目錄**: `/home/ncyu/BybitOpenClaw/srv/program_code/ml_training/`（21 個 .py 文件）
- **核心組件**:

| 文件 | 功能 | 狀態 |
|------|------|------|
| `scorer_trainer.py` | LightGBM CPCV 訓練 ATR-normalized PnL 預測器 | ⚠️ Partial（代碼完整，需數據） |
| `linucb_trainer.py` | LinUCB 批次重建 A/b 充分統計量 | ⚠️ Partial（需 decision_context_snapshots 數據） |
| `thompson_sampling.py` | NIG 後驗 Thompson Sampling（跨策略分配） | ⚠️ Partial（Phase 3b 僅 Python） |
| `cpcv_validator.py` | 組合清洗交叉驗證 | ⚠️ Partial |
| `label_generator.py` | ATR-normalized PnL 標籤生成 | ⚠️ Partial |
| `calibration.py` | 概率校準（Platt/isotonic placeholder） | ❌ Stub |
| `onnx_exporter.py` | ONNX 導出（ort integration 延後） | ❌ Stub |
| `run_training_pipeline.py` | 端到端管線編排 | ⚠️ Partial（skip_onnx=True 默認） |
| `parquet_etl.py` | Parquet ETL 載入 | ⚠️ Partial |
| `james_stein_estimator.py` | James-Stein 收縮估計（Phase 5 暫停） | ⚠️ Partial（Phase 5 PAUSED） |
| `optuna_optimizer.py` | Optuna 超參數搜索 | ⚠️ Partial |
| `dl3_foundation.py` | DL3 基礎模型框架 | ❌ Stub |
| `dl3_ab_runner.py` | DL3 A/B 測試 | ❌ Stub |
| `dl3_go_no_go.py` | DL3 Go/No-Go 決策 | ❌ Stub |
| `edge_cluster_analysis.py` | Edge 聚類分析 | ⚠️ Partial |
| `realized_edge_stats.py` | 實現 edge 統計 | ⚠️ Partial |
| `weekly_report_generator.py` | 周報生成 | ⚠️ Partial |
| `leakage_check.py` | 數據洩漏檢查 | ⚠️ Partial |
| `linucb_arm_migration.py` | LinUCB arm 遷移 | ⚠️ Partial |
| `linucb_shadow_compare.py` | LinUCB shadow 比較 | ⚠️ Partial |

#### 2.7.2 EvolutionEngine

- **文件**: `/home/ncyu/BybitOpenClaw/srv/program_code/local_model_tools/evolution_engine.py`
- **功能**: 策略參數網格搜索 + BacktestEngine 評估 + TruthSourceRegistry 注入
- **安全**: `is_simulated=True` 強制（L37），原則 7 隔離（不碰 live/paper 配置）
- **狀態**: ⚠️ Partial — 代碼完整，但 Phase 5 暫停後，策略 gross edge 為負，優化無意義。

#### 2.7.3 LearningTierGate（L1-L5 進化）

- **文件**: `/home/ncyu/BybitOpenClaw/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/learning_tier_gate.py`
- **5 級進化**:
  - L1 Post-Trade Review（被動記錄，零成本）— ⚠️ Partial
  - L2 Pattern Discovery（500+ 觀察 + 勝率 > 20%）— 🔲 Not Started（未達解鎖條件）
  - L3 Hypothesis & Experiment — 🔲 Not Started
  - L4 Strategy Evolution — 🔲 Not Started
  - L5 Meta-Learning — 🔲 Not Started（需 6+ 月數據 + operator 批准）
- **狀態**: ⚠️ Partial — 框架代碼完整（晉升邏輯 + 審計 + 線程安全），但只有 L1 在運行。

### 2.8 感知數據平面

- **文件**: `/home/ncyu/BybitOpenClaw/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/perception_data_plane.py`
- **功能**: 統一數據註冊，強制認知層級標注（fact/inference/hypothesis）+ 新鮮度追蹤（FRESH→EXPIRED）
- **狀態**: ⚠️ Partial — 代碼完整，但主要被 Python Agent 系統使用；Rust tick pipeline 有自己的 freshness 檢查。

### 2.9 數據源強制器

- **文件**: `/home/ncyu/BybitOpenClaw/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/data_source_enforcer.py`
- **功能**: 標注 AI 生成數據 vs 交易所原始數據，防止 AI 推斷被當事實使用
- **狀態**: ⚠️ Partial — 同上，主要在 Python Agent 框架中使用。

---

## 三、真實 AI 調用 vs Stub 判定 / Real AI Calls vs Stubs

### 3.1 真實 AI 調用（代碼路徑存在且可運行）

| 調用點 | Provider | 文件:行號 | 前提條件 |
|--------|----------|-----------|----------|
| L1 Triage (Claude) | Anthropic Haiku | `layer2_engine.py:218-228` | ANTHROPIC_API_KEY |
| L1 Triage (本地回退) | Ollama/Qwen 9B | `layer2_engine.py:277-287` | Ollama 在線 |
| L2 Agent Loop | Anthropic Sonnet/Opus | `layer2_engine.py:435-445` | ANTHROPIC_API_KEY |
| Model Upgrade Triage | Anthropic Haiku | `layer2_engine.py:576-585` | ANTHROPIC_API_KEY |
| StrategistAgent edge | Ollama/Qwen 9B | `ollama_client.py:333-363` (`judge_edge`) | Ollama 在線 |
| StrategistAgent classify | Ollama/Qwen 9B | `ollama_client.py:291-331` (`classify`) | Ollama 在線 |
| Perplexity Search | Perplexity API | `layer2_tools.py:306-382` | PERPLEXITY_API_KEY |
| Local LLM Search | Ollama/Qwen 9B | `layer2_tools.py:461-491` | Ollama 在線 |
| Claude Teacher (Rust) | Anthropic (reqwest) | `claude_teacher/client.rs:78-80` | ANTHROPIC_API_KEY |
| Ollama Status (GUI) | Ollama `/api/tags` | `layer2_routes.py:382-409` | Ollama 在線 |

### 3.2 Stub / 未實現 / 默認關閉

| 組件 | 狀態 | 原因 |
|------|------|------|
| ExecutorAgent | ❌ Stub | Python 執行層已退場（DEAD-PY-2） |
| DL3 Foundation/AB/GoNoGo | ❌ Stub | Phase 4+ 計劃，代碼僅框架 |
| ONNX Export | ❌ Stub | ort 集成延後 |
| Calibration (Platt/isotonic) | ❌ Stub | 占位符 |
| Teacher Loop (Rust) | 默認 OFF | `teacher_loop_enabled: false`（learning_config.rs:96） |
| L2-L5 Learning Tiers | 🔲 未達解鎖條件 | 需 500+ 觀察 / 2+ 週 / 正 ROI |
| Strategist Agent (live) | Shadow 模式 | 不產出實際 intent |
| AI Consultation (strategy) | 未接線 | strategy_wiring.py 提到但未實現端到端 |

---

## 四、Agent Profiles（CCAgentWorkSpace）

- **目錄**: `/home/ncyu/BybitOpenClaw/srv/docs/CCAgentWorkSpace/`
- **16 個角色 profile**: PM, PA, FA, E1, E1a, E2, E3, E4, E5, QC, A3, R4, TW, AI-E, QA, CC
- **狀態**: ✅ — 這些是**開發流程角色**（Claude Code 對話中的虛擬角色），非交易 Agent。完整定義在各自的 `profile.md` 中。
- **注意**: 不要混淆這 16 個開發角色與系統內的 5 個交易 Agent（Scout/Strategist/Guardian/Analyst/Executor）。

---

## 五、可接入度分析 / Integration Readiness Assessment

### 5.1 使 H1-H5 完全運行所需的工作

| 層 | 當前差距 | 所需工作量 | 優先級 |
|----|---------|------------|--------|
| H0 | 無差距 | 0 | -- |
| H1 | 僅在 Python Agent 框架中使用 | 如果要在 Rust pipeline 中加入 AI 閘門，需在 `on_tick.rs` 添加 IPC 調用 H1 | P2 |
| H2 | Python 和 Rust 雙軌均工作 | 打通兩側 budget 同步（目前各自獨立） | P2 |
| H3 | 同 H1 | Rust pipeline 加入模型選擇邏輯 | P3 |
| H4 | 完全可用 | 0 | -- |
| H5 | 完全可用 | 0 | -- |

### 5.2 ML 訓練數據管線就緒度

| 數據源 | 狀態 | 說明 |
|--------|------|------|
| K 線 / OHLCV | ✅ | Bybit WS/REST → Postgres，KlineManager 正常 |
| 交易記錄（fills） | ⚠️ | Paper engine 產生 fills，但 PNL-FIX-1/2 揭露歷史數據被污染 |
| 決策上下文快照 | ⚠️ | `decision_context_snapshots` 表已建，`context_writer.rs` 已接線，但需乾淨數據 |
| Feature 提取 | ⚠️ | `parquet_etl.py` 和 `label_generator.py` 代碼就緒，但需重跑 |
| LinUCB state | ⚠️ | PG schema + BYTEA IO 就緒，需批次訓練填充 |
| 新聞數據 | ✅ | 3 providers 已接入，60s 抓取 |

### 5.3 Feature 提取完整度

- **技術指標**: KlineManager → IndicatorEngine（MA/BB/ATR/RSI 等）✅
- **微結構**: observer verdict（資金費率 / 訂單簿深度 / 波動率）✅
- **LinUCB Context**: `FEATURE_NAMES_V1`（`linucb/runtime.rs`）定義了上下文特徵向量 ✅
- **缺失**: DL3 特徵工程（dl3_foundation.py 僅框架）❌

### 5.4 從 Shadow 到 Live AI 決策的路徑

1. **前置條件已滿足**:
   - Ollama 客戶端 ✅
   - Claude API 集成代碼 ✅
   - 成本追蹤與預算控制 ✅
   - AI 輸出驗證 ✅
   - 新聞管線 ✅

2. **需要完成的工作**（按優先級）:
   - **P0**: 策略重做（G-SR-1），當前所有策略 gross edge 為負，AI 優化無意義
   - **P1**: 積累 21+ 天乾淨 paper trading 數據（LG-1，05-01 到期）
   - **P1**: 啟用 `teacher_loop_enabled`，讓 Claude Teacher 開始產出 directive
   - **P2**: LinUCB 批次訓練（需 200+ 乾淨決策數據）
   - **P2**: LightGBM scorer 訓練 + 校準
   - **P3**: AI Agent（G-1 W22-W23）從 Shadow → Advisory → Binding

---

## 六、結論與建議 / Conclusions & Recommendations

### 6.1 整體評估

**AI 基礎設施建設量充足（~15,000 行 AI 相關代碼），但實際投入生產的 AI 功能有限。**

- **已投產**: Ollama 客戶端 + Layer2 API/GUI + 新聞管線 + 成本追蹤 + Rust BudgetTracker
- **代碼完整待啟用**: Claude Teacher + LinUCB + Layer2 Agent Loop + 5 Agent 框架
- **真正的瓶頸不是代碼而是數據**: PNL-FIX-1/2 後所有歷史數據被污染，需要乾淨的 21+ 天重跑

### 6.2 風險提醒

1. **定價表過期**: Layer2Types 的 `last_verified_date` 為 2026-03-27，已超 30 天核實期限，GUI 會顯示過期警告
2. **Python Agent 系統的定位模糊**: ARCH-RC1 後 Python 交易邏輯全退場，但 5 Agent 框架代碼仍在。需明確其角色是 advisory 還是計劃重構為 Rust
3. **雙軌 AI 預算獨立運行**: Python Layer2CostTracker 和 Rust BudgetTracker 各自追蹤，無同步機制，可能導致預算感知不一致

### 6.3 優先行動建議

1. 更新 Layer2 定價表 `last_verified_date`（5 分鐘）
2. 等待策略重做（G-SR-1）完成後，再啟用 ML 訓練管線
3. W22 G-1 AI Agent 啟動時，建議先聚焦 StrategistAgent 的 Ollama judge_edge 接線（已有代碼），而非從零搭建

---

*報告生成工具: Claude Opus 4.6 AI-E 角色*
*代碼庫 commit: 基於 2026-04-12 main 分支*


---

# 5. E5 — 優化 · 精簡 · 性能 · 可讀性評估

> 原始文件：`docs/CCAgentWorkSpace/E5/2026-04-12--optimization_assessment_report.md`

# E5 全程序優化評估報告

**日期**：2026-04-12
**範圍**：Rust `openclaw_engine` (54,952 行) + Python API 層 (145,883 行，排除 venv)
**代碼庫狀態**：1355 Rust tests + 2852 Python tests pass

---

## 一、性能評估 [PERF]

### P-01 [PERF] `on_tick()` 內 `event.symbol.clone()` 重複分配 — **High**

**文件**：`tick_pipeline/on_tick.rs:28,55,77,166,242,261,294,434,1205`

核心熱路徑 `on_tick()` 每 tick 對 `event.symbol` 做 9 次 `.clone()`。在 25 個 symbol、每秒數百 tick 的生產環境中，每 tick 多出 9 次堆分配。`event.symbol` 是 `String`，平均 ~12 字節（"BTCUSDT"~7, "ETHUSDT"~7），每次 clone 觸發 `malloc`。

**建議**：在 `on_tick()` 開頭做一次 `let sym = &event.symbol;`，後續所有 `.insert()` / 構造消息處統一使用 `sym.clone()`（需要所有權的地方）或 `sym`（借用的地方）。對於 HashMap key，考慮使用 `Arc<str>` 或在 PriceEvent 內部使用 `Rc<str>`/`Arc<str>` 替代 `String`，但這影響面大，建議先做 local alias 優化。

**影響估計**：每 tick 減少 ~5-6 次 String clone（保留真正需要所有權的 insert 處）。在 100 tick/s 時約 500 次/s 堆分配消除。

---

### P-02 [PERF] `metadata: HashMap<String, String>` 每 PriceEvent 分配 — **High**

**文件**：`openclaw_types/src/price.rs:24`, `ws_client.rs:460-468`

`PriceEvent` 結構體包含 `metadata: HashMap<String, String>`，WS 解析器每條消息都創建新 HashMap 並 insert 2-3 個 key/value（"type", "side", "qty"）。在高頻 publicTrade 流下（每秒可達數百條），這是大量短命堆分配。

**建議**：
- 方案 A：將 `type`/`side`/`qty` 提升為 PriceEvent 的結構化字段（枚舉 `EventType { Trade, Kline, Ticker, Orderbook, ... }` + `Option<TradeSide>` + `Option<f64> trade_qty`），完全消除 HashMap。
- 方案 B：使用 `SmallVec<[(String,String); 4]>` 替代 HashMap（避免哈希表開銷，4 元素以下棧分配）。
- 方案 C（最小改動）：在 `on_tick()` 入口處用 `metadata.get("type")` 結果做一次 pattern match，將 `bids5`/`asks5` 的 `serde_json::from_str` 提取（on_tick.rs:124,129）改為預解析結構化字段。

**影響估計**：每 tick 省下 1 HashMap + 2-3 String 分配 = 約 4-6 次堆分配。方案 A 可以同時消除 on_tick.rs:73 和 on_tick.rs:94 處的 `metadata.get()` 字符串比較開銷。

---

### P-03 [PERF] `serde_json::from_str` 在 orderbook 熱路徑解析 bids/asks — **Medium**

**文件**：`tick_pipeline/on_tick.rs:122-130`

每個 orderbook tick 都對 metadata 中序列化的 bids5/asks5 做兩次 `serde_json::from_str::<Vec<(f64,f64)>>`。orderbook 更新頻率可達每秒數十次 x 25 symbols。

**建議**：如果實施 P-02 方案 A，可以在 WS 解析層直接存 `Vec<(f64,f64)>` 到結構化字段，避免先序列化到 String 再反序列化回來的雙重開銷。短期可跳過，因 orderbook tick 只有在 `market_data_tx` 存在時才進入此路徑。

---

### P-04 [PERF] `risk_config().clone()` 每 tick 深拷貝完整 RiskConfig — **Medium**

**文件**：`tick_pipeline/on_tick.rs:998`

```rust
let risk_config = self.intent_processor.risk_config().clone();
```
`RiskConfig` 含 ~15 個子結構 + 多個 `HashMap<String, ...>` + `Vec<String>`。每 tick 做一次完整深拷貝供 `evaluate_positions()` 使用。

**建議**：`evaluate_positions()` 只讀取 `risk_config` 的少數字段（limits.*、cascade.*）。改為傳 `&RiskConfig` 引用而非 owned clone。`evaluate_positions` 簽名從 `risk_config: &RiskConfig` 已經是引用了（確認），但調用端仍 clone 出 owned 值再取引用 — 直接用 `self.intent_processor.risk_config()` 返回的引用即可。

**影響估計**：每 tick 省 1 次深拷貝（含多個 HashMap clone），在 100 tick/s 時顯著。

---

### P-05 [PERF] `seen_exec_ids` 使用 VecDeque + 線性搜索去重 — **Medium**

**文件**：`event_consumer/mod.rs:580`

```rust
if seen_exec_ids.iter().any(|id| id == &exec.exec_id) {
```
使用 `VecDeque<String>` 存最多 500 個 exec_id，每次 fill 到來做 O(500) 線性掃描。在高頻成交場景下（例如 grid 策略爆發），每秒可能數十次 fill。

**建議**：改用 `HashSet<String>` + `VecDeque<String>`（HashSet 做 O(1) 查重，VecDeque 維護 FIFO 淘汰），或使用 `IndexSet`。可保持 500 上限的 FIFO 語義。

---

### P-06 [PERF] `subscriptions.contains()` 在 WS 主題管理中是 O(n) — **Low**

**文件**：`ws_client.rs:236`

```rust
if !self.subscriptions.contains(t) {
```
`subscriptions` 是 `Vec<String>`，ScannerRunner 動態添加 topic 時線性搜索整個列表。目前 ~75 topic（25 symbols x 3 streams），尚不構成瓶頸，但隨 symbol 數量擴展會惡化。

**建議**：改用 `HashSet<String>` 維護去重集，`Vec<String>` 僅用於 subscribe 批次發送。或直接用 `IndexSet` 兼顧去重和有序。

---

### P-07 [PERF] `WsClient::process_message` 每條消息全量 JSON 解析 — **Low**

**文件**：`ws_client.rs:342`

每條 WS 消息先解析為 `serde_json::Value`（動態類型），再按 topic 路由手動提取字段。Bybit 公共 WS 可達每秒數百條消息。

**建議**：對高頻消息（publicTrade、tickers），使用帶 `#[serde(rename)]` 的結構體直接 `serde_json::from_str::<BybitTradeMsg>` 反序列化，避免 `Value` 中間層。低頻消息（adl-notice、price-limit、liquidation）保留動態解析即可。

**影響估計**：中等。`serde_json::Value` 做大量小堆分配（每個字段一個 `Value` 節點），結構化反序列化直接寫入棧/堆字段，分配次數可減少 50-70%。但 WS 解析在獨立異步任務中，非 tick 管線瓶頸。

---

### P-08 [PERF] TickContext 構造時 clone indicators + signals — **Medium**

**文件**：`tick_pipeline/on_tick.rs:434-438`

```rust
let ctx = TickContext {
    symbol: event.symbol.clone(),
    indicators: indicators.clone(),
    signals: signals.clone(),
    ...
};
```
`IndicatorSnapshot` 含 ~10 個 Option 包裝的指標結構，`signals` 是 `Vec<Signal>`。每 tick clone 一次傳給策略。

**建議**：`TickContext` 改為持有借用 `&'a IndicatorSnapshot` / `&'a [Signal]`，生命週期綁定到 `on_tick` 作用域。需要修改 Strategy trait 的 `on_tick(&mut self, ctx: &TickContext<'_>)` 簽名。改動面中等但收益顯著。

---

### P-09 [PERF] `intent.clone()` 在 on_tick 的 Open/Close 分支中多次出現 — **Low-Medium**

**文件**：`tick_pipeline/on_tick.rs:582,626,672,822,838`

在 exchange/paper 兩條路徑中，`intent.clone()` 用於構造 `display_intent` 和推入 `recent_intents`。每次 clone 包含 5-6 個 String 字段。大多數 tick 不產生 intent，所以僅在開倉/平倉 tick 觸發，影響有限。

**建議**：`TimestampedIntent` 可以直接持有必要字段的引用或精簡 subset，而非完整 clone。或把 display_intent 構造統一為一個 helper 減少代碼重複（見 S-01）。

---

### P-10 [PERF] DB 寫入器 7 個獨立 buffer 序列 flush — **Low**

**文件**：`database/trading_writer.rs:87-117`

`flush_all()` 函數序列化地依次 flush 7 個 buffer（signals → intents → fills → positions → verdicts → orders → state_changes）。每個 flush 是獨立的 DB 查詢。

**建議**：考慮用 `tokio::join!` 並行 flush 獨立表（它們寫不同表，無依賴）。但需注意 PG 連接池大小限制（單連接不能並發查詢）。如果連接池 ≥ 3，可以至少 3 路並行。風險低。

---

## 二、精簡評估 [SIMPLIFY]

### S-01 [SIMPLIFY] `on_tick()` Exchange vs Paper 路徑大量重複代碼 — **High**

**文件**：`tick_pipeline/on_tick.rs:505-838`（Open 分支），`862-967`（Close 分支）

Exchange mode 和 Paper mode 的 Open 處理邏輯有 ~70% 重複：
- Guardian verdict 持久化（on_tick.rs:518-531 vs 653-666）— 完全相同
- Intent 持久化（on_tick.rs:538-556 vs 689-707）— 完全相同
- display_intent 構造 + recent_intents push（on_tick.rs:582-592 vs 672-686）— 完全相同
- rejection display_intent（on_tick.rs:626-639 vs 822-836）— 完全相同

Close 分支也有 exchange vs paper 重複（on_tick.rs:874-908 vs 910-967）。

**建議**：提取共享邏輯為 helper 方法：
- `persist_verdict(&self, intent, event, verdict_info)`
- `persist_intent(&self, intent, event, approved_qty)`
- `push_recent_intent(&mut self, ts_ms, intent, result_str)`
- `handle_rejection(&mut self, strategy, intent, reason, verdict_info)`

這將把 on_tick.rs 從 1228 行（超 1200 硬上限）降至 ~800-900 行。

---

### S-02 [SIMPLIFY] `recent_intents.len() > 50 { pop_front() }` 重複 9 次 — **Medium**

**文件**：`tick_pipeline/on_tick.rs:589,639,685,835,882,897,906,954,963`

環形緩衝的 push + cap 邏輯重複 9 次（`recent_intents`），另有 `recent_fills` 重複 3 次。

**建議**：封裝為 `fn push_capped<T>(deque: &mut VecDeque<T>, item: T, cap: usize)` 工具函數。或自定義 `RingBuffer<T>` 包裝 VecDeque。

---

### S-03 [SIMPLIFY] `format!("ctx-{}-{}-{}", em, symbol, ts_ms)` 重複構造 ~12 次 — **Medium**

**文件**：`tick_pipeline/on_tick.rs` + `tick_pipeline/commands.rs`

`format!("ctx-{em}-{symbol}-{ts_ms}")`、`format!("intent-{em}-{symbol}-{ts_ms}")`、`format!("vrd-{em}-{symbol}-{ts_ms}")` 等 ID 構造模式反覆出現。

**建議**：提取為 `fn make_context_id(em: &str, symbol: &str, ts_ms: u64) -> String` 等 3 個 ID 工廠函數。減少拼寫錯誤風險，統一 ID 格式。

---

### S-04 [SIMPLIFY] `SystemTime::now().duration_since(UNIX_EPOCH)` 重複 pattern — **Low**

**文件**：多處（event_consumer/mod.rs:91,135,695,728; tick_pipeline/commands.rs:89; dispatch.rs:91-94）

每次取 epoch millis 都寫完整 3 行模式：
```rust
let now_ms = std::time::SystemTime::now()
    .duration_since(std::time::UNIX_EPOCH)
    .map(|d| d.as_millis() as u64)
    .unwrap_or(0);
```

**建議**：提取到 `crate::util::now_ms() -> u64` 全局工具函數（ws_client.rs:425 已有 `fn now_ms()`，但是模塊私有的）。提升為 crate 級公開函數。

---

### S-05 [SIMPLIFY] `flush_signals/intents/fills/...` 7 個近乎相同的函數 — **Low-Medium**

**文件**：`database/trading_writer.rs:131-645`（估計）

7 個 `flush_*` 函數結構完全一致：取 pool → chunk → QueryBuilder → push_values → 解構 enum variant → bind → execute → record success/failure → clear。僅表名、列名、variant 不同。

**建議**：使用宏或泛型 trait 統一。但代碼生成的可讀性與直接展開需權衡。當前直接展開更易 debug，建議保留但加 `// NOTE: pattern shared with flush_signals/intents/fills etc.` 交叉引用。

---

## 三、可讀性評估 [READABILITY]

### R-01 [READABILITY] 4 個文件超 1200 行硬上限 — **High (違規)**

| 文件 | 行數 | 狀態 |
|------|------|------|
| `config/risk_config.rs` | 1381 | 超限 181 行 |
| `event_consumer/mod.rs` | 1302 | 超限 102 行 |
| `claude_teacher/applier.rs` | 1257 | 超限 57 行 |
| `tick_pipeline/on_tick.rs` | 1228 | 超限 28 行 |

另有 6 個文件在 800-1200 警告區間。

**建議**：
- `risk_config.rs`：默認值函數（~100 個 `fn default_*`）提取到子模塊 `risk_config/defaults.rs`。
- `event_consumer/mod.rs`：`run_event_consumer` 函數本體 ~800 行，主事件循環的 exchange event handler（on_tick.rs:572-800）可提取為 `event_consumer/exchange_events.rs` 模塊。
- `on_tick.rs`：實施 S-01 後預計降至 ~900 行。
- `claude_teacher/applier.rs`：待確認內部結構再拆分。

---

### R-02 [READABILITY] `on_tick()` 單函數 1187 行 — **High**

**文件**：`tick_pipeline/on_tick.rs:11-1187`

這是整個系統最關鍵的函數，但單函數體 1187 行極難閱讀和維護。

**建議**：按管線階段拆分為子方法：
1. `on_tick_preprocess()` — 價格更新、turnover、ADL、聚合器（~100 行）
2. `on_tick_fast_track()` — 快速通道 + H0 gate（~50 行）
3. `on_tick_indicators()` — K 線、指標、特徵快照（~80 行）
4. `on_tick_signals()` — 信號評估 + 持久化 + context（~100 行）
5. `on_tick_strategy_dispatch()` — Open/Close 分派（~350 行，含 S-01 重構後）
6. `on_tick_risk_checks()` — 風控 9 項檢查 + 執行（~200 行）
7. `on_tick_housekeeping()` — 統計、快照、canary（~50 行）

每個子方法 50-200 行，符合規範。

---

### R-03 [READABILITY] `run_event_consumer()` 函數包含完整主循環 ~800 行 — **Medium**

**文件**：`event_consumer/mod.rs:31-900+`

一個 async 函數包含所有 setup + 主 select! 循環 + exchange event handling。

**建議**：setup 部分（31-520）已用 `setup.rs` + `dispatch.rs` 做了部分提取。主循環的 exchange event 處理（572-800）可提取到 `event_consumer/exchange_events.rs`。

---

### R-04 [READABILITY] 命名不一致：`shadow_order_tx` vs `ShadowOrderRequest` — **Low**

**文件**：`tick_pipeline/mod.rs:392-416`

`ShadowOrderRequest` 這個名稱源自早期 "paper only + shadow to demo" 架構，但現在同一結構體也用於 exchange mode primary orders（`is_primary=true`）。名稱 "Shadow" 具誤導性。

**建議**：重命名為 `OrderDispatchRequest` 或 `ExchangeOrderRequest`，`shadow_order_tx` 改為 `order_dispatch_tx`。影響面：TickPipeline、dispatch.rs、event_consumer。

---

### R-05 [READABILITY] Python `governance_routes.py` 1914 行 — **High (違規)**

**文件**：`control_api_v1/app/governance_routes.py:1914 行`

已超 1200 行硬上限（§九），且在 CLAUDE.md 留尾中已標記。

**建議**：按功能域拆分：
- `governance_auth_routes.py`（授權相關 ~400 行）
- `governance_risk_routes.py`（風控相關 ~300 行）
- `governance_promotion_routes.py`（6-01~03 漸進放權 ~300 行）
- `governance_routes.py`（剩餘核心 + 路由器注冊 ~900 行）

---

## 四、死重評估 [DEAD-WEIGHT]

### D-01 [DEAD-WEIGHT] `fast_track` price_drop / margin_utilization 硬編碼 0.0 — **Medium**

**文件**：`tick_pipeline/on_tick.rs:157-159`

```rust
let ft_action = crate::fast_track::evaluate_fast_track(
    self.governance.risk.level,
    0.0, // PNL-4 dead input
    0.0, // PNL-4 dead input
);
```

兩個參數永遠為 0.0，`evaluate_fast_track` 中的閃崩和保證金危機分支永遠不會觸發。已標記為 PNL-4 跟進，但持續每 tick 調用仍有 CPU 開銷（函數內有多條 if 比較）。

**建議**：在 PNL-4 修復前，可以短路：如果只有 `risk_level >= CircuitBreaker` 才有意義，直接內聯該檢查，跳過函數調用。或在 `evaluate_fast_track` 內部提前返回（已有，影響小）。

---

### D-02 [DEAD-WEIGHT] `canary_mode` + `CanaryRecord` — **Low**

**文件**：`tick_pipeline/on_tick.rs:1189-1214`, `event_consumer/mod.rs:461-477`

灰度模式（`OPENCLAW_CANARY_MODE`）在系統驗證完畢後（R-07 通過）應已無需保留。每 tick 調用 `maybe_canary_record()`，即使不啟用也有分支判斷 + 5 參數傳遞開銷。

**建議**：如果灰度驗證已完成，可以用 feature flag 編譯排除或刪除。當前保留待確認。

---

### D-03 [DEAD-WEIGHT] `_exchange_event_rx_field` / `_scanner_store` 下劃線前綴 unused 字段 — **Low**

**文件**：`event_consumer/mod.rs:51,60`

EventConsumerDeps 中有 `_exchange_event_rx_field` 和 `_scanner_store` 用下劃線前綴標記未使用，但仍在解構時分配。

**建議**：確認是否為預留接口。如果是死代碼應清除；如果是 Phase 計劃，保留但添加 TODO 標記。

---

## 五、優化優先級排序

| 排名 | ID | 類型 | 影響 | 工作量 | 風險 |
|------|----|------|------|--------|------|
| 1 | R-01 | READABILITY | High | Medium | Low — 純移動代碼 |
| 2 | R-02/S-01 | READABILITY+SIMPLIFY | High | Medium | Low — 提取 helper |
| 3 | P-01 | PERF | High | Low | Very Low — local alias |
| 4 | P-04 | PERF | Medium | Low | Very Low — 刪除 .clone() |
| 5 | P-02 | PERF | High | Medium-High | Medium — PriceEvent 結構變更 |
| 6 | S-02+S-03 | SIMPLIFY | Medium | Low | Very Low |
| 7 | P-05 | PERF | Medium | Low | Very Low |
| 8 | R-05 | READABILITY | High | Medium | Low |
| 9 | P-08 | PERF | Medium | Medium | Low — trait 簽名變更 |
| 10 | S-04 | SIMPLIFY | Low | Low | Very Low |
| 11 | P-07 | PERF | Low | Medium | Low |
| 12 | P-03 | PERF | Medium | Medium | Medium — 依賴 P-02 |
| 13 | P-06 | PERF | Low | Low | Very Low |
| 14 | D-01 | DEAD-WEIGHT | Medium | Low | Very Low |
| 15 | R-04 | READABILITY | Low | Medium | Low — rename 影響面中等 |

---

## 六、總結

### 核心發現

1. **最大瓶頸**：`on_tick()` 1187 行單函數是系統可維護性和性能的核心風險點。每 tick 的 String clone + metadata HashMap + risk_config deep-clone 構成可測量的分配壓力。

2. **合規違規**：4 個 Rust 文件 + 1 個 Python 文件超 1200 行硬上限（§九）。`on_tick.rs` 僅超 28 行，通過 S-01 重構即可解決。`risk_config.rs` 和 `governance_routes.py` 需要結構性拆分。

3. **架構健康**：整體架構設計良好 — sole-owner 無鎖模式（TickPipeline）、try_send 非阻塞通道、batch flush DB 寫入器、JSONL fallback、信號節流（DB-RUN-1/2 已實施 99.6% 降幅）。主要優化空間在熱路徑的微觀分配層面。

4. **DB 層健康**：索引覆蓋充分（V005 遷移定義了 42 個索引）。batch INSERT + ON CONFLICT DO NOTHING 模式正確。未發現 N+1 查詢（Rust 側全部 batch 寫入，Python 側僅讀取）。

5. **WebSocket 層**：自動重連 + 指數退避 + 15s 超時保護 + 分批訂閱（Bybit 10 topic/call 限制）均已實施。`process_message` 的 `serde_json::Value` 動態解析是可選優化點，但不在 tick 管線關鍵路徑上。

### 建議執行計劃

**Phase A（1-2 小時，無功能變更）**：
- P-01 symbol clone 優化
- P-04 刪除 risk_config clone
- S-02 + S-03 提取 helper
- S-04 now_ms 統一

**Phase B（2-4 小時，重構）**：
- R-02 + S-01：on_tick 拆分為 7 子方法
- R-01：risk_config.rs 默認值提取
- P-05：seen_exec_ids 改 HashSet

**Phase C（4-8 小時，結構性變更）**：
- P-02：PriceEvent metadata 結構化
- P-08：TickContext 借用化
- R-05：governance_routes.py 拆分
- R-01：event_consumer/mod.rs 拆分

---

*報告由 E5 Performance Engineer 生成。所有建議均為純優化/重構，不改變功能行為。*


---

# 6. E4 — 全範圍測試審計

> 原始文件：`docs/CCAgentWorkSpace/E4/2026-04-12--full_test_audit_report.md`

# E4 全程式測試審計報告 / Full-Program Test Audit Report

**日期**：2026-04-12
**審計人**：E4 (Test Engineer)
**範圍**：openclaw_engine (lib + e2e) + openclaw_core (lib) + Python tests

---

## 一、測試基線 / Test Baseline

| 套件 | 通過 | 失敗 | 忽略 |
|------|------|------|------|
| `openclaw_engine` lib | **939** | 0 | 0 |
| `openclaw_engine` e2e (integration + stress + reconciler) | **29** | 0 | 0 |
| `openclaw_core` lib | **366** | 0 | 0 |
| Python (pytest collected) | **2895** | 0* | 0 |
| **合計** | **4229** | 0 | 0 |

\* Python 有 2 個 collection error（database_files 權限，非代碼問題）。

---

## 二、模組覆蓋率矩陣 / Coverage Gap Matrix

### openclaw_engine — 按模組測試密度

| 模組 | 代碼行數 | 測試數 | 密度(tests/kLOC) | 嚴重度 | 備註 |
|------|----------|--------|------------------|--------|------|
| `edge_estimates.rs` | 208 | **0** | **0** | **P0-CRITICAL** | 9 pub fn 全無測試，含 JSON 解析/查詢/聚合 |
| `startup.rs` | 856 | **0** | **0** | **P1-HIGH** | 啟動初始化邏輯，依賴外部環境難單測 |
| `tasks.rs` | 488 | **0** | **0** | **P1-HIGH** | 後台任務調度，含 spawner 邏輯 |
| `pipeline_types.rs` | 170 | **0** | **0** | P2-MEDIUM | 純類型定義，風險較低 |
| `main.rs` | 950 | **0** | **0** | P2-MEDIUM | 組裝入口，難單測但 catch_unwind 路徑未驗 |
| `ipc_server/` | 3,245 | 49 | 15.1 | P2-MEDIUM | handlers.rs 1192 行覆蓋尚可 |
| `database/rest_poller.rs` | 158 | **0** | **0** | **P1-HIGH** | REST 輪詢邏輯零測試 |
| `database/quality_writer.rs` | 109 | **0** | **0** | P2-MEDIUM | 品質寫入器零測試 |
| `claude_teacher/applier.rs` | — | **0** | **0** | P2-MEDIUM | 指令應用器零測試 |
| `claude_teacher/client.rs` | — | **0** | **0** | P2-MEDIUM | HTTP client 零測試 |
| `claude_teacher/writer.rs` | — | **0** | **0** | P2-MEDIUM | 寫入器零測試 |
| `claude_teacher/strategy_ipc_impl.rs` | — | **0** | **0** | P2-MEDIUM | IPC 實作零測試 |
| `on_tick.rs` | 1,228 | **0** (inline) | **0** | P2-MEDIUM | 透過 tick_pipeline/tests.rs 間接覆蓋 61 tests |
| `orchestrator.rs` | 233 | 5 | 21.5 | OK | 基本功能覆蓋 |
| `fast_track.rs` | 137 | 8 | 58.4 | OK | 所有 risk level 路徑已覆蓋 |
| `position_manager.rs` | 839 | 12 | 14.3 | P2-MEDIUM | 解析測試為主，業務邏輯測試不足 |
| `paper_state.rs` | 839 | 14 | 16.7 | P2-MEDIUM | 含 B-1 回歸測試 |

### openclaw_engine — 高測試密度模組（良好）

| 模組 | 代碼行數 | 測試數 | 密度 |
|------|----------|--------|------|
| `config/` | 3,734 | 82 | 22.0 |
| `strategies/` | 4,098 | 81 | 19.8 |
| `tick_pipeline/` | 4,320 | 67* | 15.5 |
| `database/` | 5,213 | 63 | 12.1 |
| `scanner/` | 2,289 | 53 | 23.1 |
| `risk_checks.rs` | ~400 | 25 | 62.5 |
| `position_reconciler/` | 1,404 | 32 | 22.8 |
| `intent_processor/` | 1,796 | 36 | 20.1 |

\* tick_pipeline 的 67 tests 包含間接覆蓋 on_tick.rs 邏輯。

### openclaw_core — 所有模組均有測試（良好）

| 模組 | 代碼行數 | 測試數 | 密度 |
|------|----------|--------|------|
| `sm/` | 3,315 | 57 | 17.2 |
| `indicators/` | 1,326 | 35 | 26.4 |
| `signals/` | 1,196 | 30 | 25.1 |
| `h0_gate.rs` | 1,067 | 30 | 28.1 |
| `risk/` | 537 | 22 | 41.0 |
| `klines.rs` | 1,086 | 22 | 20.3 |
| `dream.rs` | 936 | 20 | 21.4 |
| `opportunity.rs` | 861 | 18 | 20.9 |
| `execution.rs` | 346 | 18 | 52.0 |
| `cognitive.rs` | 524 | 13 | 24.8 |
| `cost_gate.rs` | 250 | 11 | 44.0 |
| `guardian.rs` | 314 | 6 | 19.1 |

---

## 三、正常路徑測試評估 / Happy-Path Coverage

### 3.1 策略信號 → 意圖 → 門控 → 訂單 → 成交 → PnL

| 路徑段 | 覆蓋 | 測試位置 | 備註 |
|--------|------|----------|------|
| 策略 `on_tick()` 產生信號 | **PASS** | `strategies/*/tests` (81 tests) | 5 策略各有完整 entry/exit/boundary 測試 |
| Orchestrator 收集 intents | **PASS** | `orchestrator::tests` (5 tests) | dispatch + inactive skip |
| IntentProcessor 門控 | **PASS** | `intent_processor::tests` (36 tests) | cost_gate/guardian/Kelly/D15/governance |
| TickPipeline 訂單執行 | **PASS** | `tick_pipeline::tests` (61 tests) | open/close/fill/stats |
| Paper PnL 計算 | **PASS** | `paper_state::tests` + stress | long/short/accumulate/close |
| 資料庫 fill 寫入 | **PASS** | `database::trading_writer::tests` | batch routing + limits |

**結論**：核心交易管線 happy-path 完整覆蓋。

### 3.2 Kline Bootstrap → 指標 → 信號

| 路徑段 | 覆蓋 | 測試位置 |
|--------|------|----------|
| KlineManager 數據管理 | **PASS** | `klines::tests` (22 tests) |
| IndicatorEngine 計算 | **PASS** | `indicators/tests` (35 tests) |
| SignalEngine 信號生成 | **PASS** | `signals/tests` (30 tests) |

---

## 四、邊界測試評估 / Boundary Tests

### 4.1 已覆蓋的邊界

| 邊界場景 | 測試 | 位置 |
|----------|------|------|
| Zero balance → skip position check | **PASS** | `risk_checks::tests::test_order_zero_balance_position_check` |
| Max positions exceeded | **PASS** | `stress_guardian_rejects_position_count_limit` (e2e) |
| D15 exact boundary allows | **PASS** | `intent_processor::tests::test_d15_global_cap_exact_boundary_allows` |
| D15 cap disabled when zero/negative | **PASS** | 2 tests |
| Entry price zero → no NaN | **PASS** | `rrc1_audit_tests::test_entry_price_zero_does_not_nan` |
| ATR zero → fail-closed | **PASS** | `test_sec11_cost_gate_fail_closed_on_zero_atr` |
| Exactly 5% drop → fast_track | **PASS** | `stress_fast_track_boundary_exactly_5pct_drop` |
| Exactly 90% margin → fast_track | **PASS** | `stress_fast_track_boundary_exactly_90pct_margin` |
| Extreme prices (BTC $1M) | **PASS** | `stress_full_pipeline_extreme_prices` |
| Zero volume ticks | **PASS** | `stress_full_pipeline_zero_volume_ticks` |
| Tiny balance position sizing | **PASS** | `test_position_sizing_tiny_balance` |
| Cooldown exactly at boundary | **PASS** | `event_consumer::cooldown_tests::boundary_at_exactly_cooldown_treated_as_expired` |
| Clock skew (future timestamps) | **PASS** | `future_timestamp_clock_skew_returns_none` |

### 4.2 缺失的邊界測試 **[GAP]**

| 邊界場景 | 嚴重度 | 應新增位置 |
|----------|--------|-----------|
| **Price = 0.0 的 tick** | **P1-HIGH** | `tick_pipeline/tests.rs` — 0 價格可能導致 division by zero |
| **f64::MAX / f64::INFINITY 價格** | P2-MEDIUM | `risk_checks.rs` / `paper_state.rs` |
| **NaN propagation in PnL** | P2-MEDIUM | `paper_state.rs::close_position()` |
| **max_same_direction 正好等於上限** | P2-MEDIUM | `risk_checks.rs` |
| **25 symbols 同時到達 max** | P2-MEDIUM | `orchestrator.rs` — 當前最大壓測 5 symbols |
| **Config 驗證後的邊界值運行** | P2-MEDIUM | 驗證通過的最小/最大值是否能實際運行 |
| **Edge estimates 空 JSON / 畸形 JSON** | **P1-HIGH** | `edge_estimates.rs` — 完全無測試 |
| **Scanner 0 active symbols** | P2-MEDIUM | `scanner/registry.rs` |
| **Notional 正好等於 min_order_notional** | P2-MEDIUM | `intent_processor` |

---

## 五、異常測試評估 / Error Handling Tests

### 5.1 已覆蓋的異常路徑

| 異常場景 | 覆蓋 | 位置 |
|----------|------|------|
| IPC invalid JSON | **PASS** | `ipc_server::tests::test_dispatch_invalid_json` |
| IPC method not found | **PASS** | `ipc_server::tests::test_dispatch_method_not_found` |
| IPC missing version/method | **PASS** | 2 tests |
| Config missing file → defaults | **PASS** | `config::io::tests` |
| Config invalid TOML → error | **PASS** | `config::io::tests` |
| Config validation rollback | **PASS** | `config::store::tests::test_apply_patch_validation_failure_rolls_back` |
| DB pool invalid URL → graceful | **PASS** | `database::pool::tests` |
| DB pool disabled → None | **PASS** | `database::pool::tests` |
| Fallback file rotation | **PASS** | `database::fallback::tests` |
| REST client retCode error | **PASS** | `bybit_rest_client::tests::test_bybit_response_error` |
| REST client deserialization error | **PASS** | `test_deserialize_error_response` |
| WS parse missing fields | **PASS** | `test_parse_kline_item_missing_close`, `test_parse_trade_item_missing_price` |
| Strategy params invalid TOML → defaults | **PASS** | `test_load_strategy_params_invalid_toml_returns_defaults` |
| Submit order invalid side | **PASS** | `event_consumer::tests::test_f_submit_order_invalid_side_rejected` |
| Submit order no price | **PASS** | `test_f_submit_order_no_price_rejected` |
| Submit order while paused | **PASS** | `test_f_submit_order_paused_rejected` |
| Fee charge rejects garbage (NaN/Inf/negative) | **PASS** | `test_paper_state_charge_fee_rejects_garbage` |

### 5.2 缺失的異常測試 **[GAP]**

| 異常場景 | 嚴重度 | 備註 |
|----------|--------|------|
| **REST API timeout 行為** | **P0-CRITICAL** | 硬邊界要求 fail-closed 不重試，但無測試驗證 |
| **WS 斷線重連行為** | **P1-HIGH** | ws_client.rs 有 `test_backoff_calculation`，但無模擬斷線→重連→replay 流程測試 |
| **Live catch_unwind panic recovery** | **P1-HIGH** | main.rs:849 有 catch_unwind，但無測試驗證 panic 後系統行為 |
| **DB 寫入全失敗（PG down）** | P2-MEDIUM | fallback 有測試，但完整 pipeline 在 DB 全掛時的行為未驗 |
| **Config 熱重載期間 tick 到達** | **P1-HIGH** | ArcSwap 語義正確但無並發測試 |
| **IPC socket 連接風暴** | P2-MEDIUM | 大量並發 IPC 請求未壓測 |
| **News pipeline provider 全部失敗** | P2-MEDIUM | scheduler 容錯邏輯未測 |

---

## 六、並發測試評估 / Concurrency Tests

### 6.1 已有的並發測試

| 場景 | 位置 | 方法 |
|------|------|------|
| ConfigStore 並發 patch | `config::store::tests::test_concurrent_patches_serialise` | 多線程寫入 + 斷言版本序列化 |
| Reconciler 原子 risk level | `position_reconciler::tests` | AtomicU8 repr 穩定性測試 |
| Stress 多 symbol 同時 tick | `stress_multi_symbol_5_coins_simultaneous_ticks` | 5 symbols 交替 tick |
| Stress 100 cycle 翻轉 | `stress_100_cycles_rapid_drift_clean_alternation` | 快速升降級 |
| Stress 50 symbols burst | `stress_50_symbols_simultaneous_drift` | 高並發漂移 |

### 6.2 缺失的並發測試 **[GAP]**

| 場景 | 嚴重度 | 備註 |
|------|--------|------|
| **三管線（Paper/Demo/Live）同時寫 shared state** | **P0-CRITICAL** | 3E-ARCH 架構核心，Vec<Sender> 扇出但無三管線同時運行測試 |
| **Scanner symbol 更新時 tick 到達** | **P1-HIGH** | active_symbols 改變可能影響正在處理的 tick |
| **Config hot-reload during on_tick** | **P1-HIGH** | ArcSwap load() vs store() 的語義安全未驗證 |
| **IPC handler 與 tick 並發操作 paper_state** | **P1-HIGH** | 如 import_positions 與 on_tick 同時執行 |
| **多 Provider 同時寫新聞 DB** | P2-MEDIUM | news pipeline 並發寫入 |
| **Reconciler escalation 與 tick fast_track 同時觸發** | P2-MEDIUM | 雙重風控動作衝突 |

---

## 七、回歸測試評估 / Regression Tests

### 7.1 已有回歸測試

| Bug ID | 描述 | 回歸測試 | 位置 |
|--------|------|----------|------|
| **PNL-FIX-1** | 跨 symbol 平倉用錯價格 | **PASS** ✅ | `tick_pipeline/tests.rs:1023` — `test_close_position_at_symbol_market_uses_per_symbol_price` |
| **PNL-FIX-1 fallback** | 無 latest_price 時 fallback | **PASS** ✅ | `tick_pipeline/tests.rs:1083` — `test_close_position_at_symbol_market_fallback_to_entry_when_no_latest_price` |
| **PNL-FIX-2** | 平倉 fee=0 | **PASS** ✅ | `tick_pipeline/tests.rs:1112` — `test_emit_close_fill_charges_real_close_fee` |
| **PNL-FIX-2 validation** | charge_fee 拒絕非法值 | **PASS** ✅ | `tick_pipeline/tests.rs:1174` — `test_paper_state_charge_fee_rejects_garbage` |
| **B-1** | Position import 覆蓋 | **PASS** ✅ | `paper_state.rs:770` — `test_import_positions_seeds_state` |
| **B-2** | execution.fast topic + total_fills | **PASS** ✅ | `bybit_private_ws.rs:788` + `tick_pipeline/tests.rs:494` |
| **3E-ARCH** | emit_close_fill db_mode() | **PASS** ✅ | `tick_pipeline/tests.rs:39` |
| **D6** | 跨引擎故障級聯 | **PASS** ✅ | `event_consumer::tests` — 3 cascade tests |
| **D23** | Reconciler snapshot | **PASS** ✅ | `tick_pipeline/tests.rs:957` |

### 7.2 缺少回歸測試的已知問題 **[GAP]**

| 問題 | 嚴重度 | 備註 |
|------|--------|------|
| **Grid 庫存漂移 P1** | P2-MEDIUM | CLAUDE.md 記載的 grid_trading 問題，無專用回歸測試 |
| **Exchange Kelly P2** | P2-MEDIUM | Kelly 公式用於 exchange 路徑的問題 |
| **fast_track 硬編碼 0 的死碼** | P2-MEDIUM | `price_drop_pct` / `margin_utilization` = 0，唯一可觸發路徑是 CB，無測試驗證此限制 |
| **paper_state.json 三引擎搶寫** | **P1-HIGH** | `with_kind()` 補設 `pipeline_kind` 字段（commit c9d9bc5），但無回歸測試驗證隔離 |

---

## 八、壓力/性能測試評估 / Stress Tests

### 8.1 現有壓力測試（29 e2e tests）

| 類別 | 測試數 | 涵蓋場景 |
|------|--------|----------|
| Fast track 風控觸發 | 8 | flash crash / defensive / boundary |
| 多 symbol 並發 | 2 | 5 coins / rapid alternating |
| 策略壓測 | 5 | whipsaw / extreme / squeeze / grid traversal |
| Guardian 拒絕 | 3 | drawdown / direction / position count |
| 止損觸發 | 4 | hard stop / short / multi-position / boundary |
| PnL 序列 | 3 | long/short/zero-sum |
| 全管線壓測 | 3 | volatile / zero-volume / extreme prices |
| Reconciler 壓測 | 4 | 100-cycle / 50-symbol / rapid handler / performance |
| 10K tick 無 panic | 1 | 10,000 ticks 穩定性 |
| Tick 延遲基準 | 1 | 1000 calls <100ms |

### 8.2 壓力測試缺口

| 缺口 | 嚴重度 | 備註 |
|------|--------|------|
| **25 symbols 滿負載 10K ticks** | P2-MEDIUM | 當前最大 5 symbols / 10K ticks，但設計上限 25 |
| **記憶體增長檢測** | P2-MEDIUM | 長時間運行的 ring buffer / HashMap 增長未檢測 |
| **多策略同時開/平倉風暴** | P2-MEDIUM | 現有壓測策略各自獨立 |

---

## 九、關鍵發現彙總 / Key Findings

### P0-CRITICAL（必須修復）

1. **`edge_estimates.rs` 零測試**（208 行 / 9 pub fn）
   - 文件：`/home/ncyu/BybitOpenClaw/srv/rust/openclaw_engine/src/edge_estimates.rs`
   - 風險：JSON 解析 `load_from_file()` / `load_from_str()` 無驗證，grand_mean_bps() 可能 division by zero
   - 修復：新增 8-10 tests 覆蓋 empty/valid/malformed JSON + boundary values

2. **REST API timeout fail-closed 行為無測試**
   - 文件：`/home/ncyu/BybitOpenClaw/srv/rust/openclaw_engine/src/bybit_rest_client.rs`
   - 風險：硬邊界 #4「timeout → fail-closed 不重試」是架構合規要求，當前僅測 response parsing
   - 修復：mock HTTP client 測試 timeout 路徑

3. **三管線並發寫入無集成測試**
   - 風險：3E-ARCH 核心架構（Paper/Demo/Live 三獨立管線）的並發安全未端到端驗證
   - 修復：新增 e2e 測試模擬三管線同時 tick + 寫 state

### P1-HIGH（應儘快修復）

4. **`startup.rs` 零測試**（856 行）— 啟動初始化，失敗 = 系統無法啟動
5. **`tasks.rs` 零測試**（488 行）— 後台任務調度
6. **`database/rest_poller.rs` 零測試**（158 行）— REST 資料輪詢
7. **WS 斷線重連全流程無測試** — 只測了 backoff 計算
8. **Live catch_unwind 後行為無測試** — panic 恢復是 Live 安全保障
9. **Config hot-reload + tick 並發無測試** — ArcSwap 語義正確性未驗證
10. **Scanner symbol 更新 + tick 並發** — 活躍 symbol 列表變更的 race condition
11. **paper_state.json 三引擎搶寫的回歸測試缺失** — commit c9d9bc5 修復但無回歸

### P2-MEDIUM（計劃中修復）

12. `claude_teacher/` 4 個子模組零測試（applier / client / writer / strategy_ipc_impl）
13. `database/quality_writer.rs` 零測試
14. `position_manager.rs` 測試偏重 parsing，業務邏輯不足
15. Price=0.0 tick 行為未測試
16. f64::MAX / f64::INFINITY 在 risk_checks 中的行為
17. NaN 在 PnL 計算中的傳播
18. fast_track 死碼路徑（price_drop_pct=0）無觀測性測試

---

## 十、測試品質評價 / Quality Assessment

### 優勢

1. **回歸測試紀律優秀**：PNL-FIX-1/2、B-1/B-2 全部有標記明確的回歸測試，帶中英雙語 doc
2. **風控路徑覆蓋完整**：25 risk_checks tests + 32 reconciler tests + 8 fast_track tests = 全路徑
3. **邊界意識強**：zero balance / exact boundary / extreme price 多處覆蓋
4. **壓力測試有深度**：10K tick 穩定性 + 性能基準 + 多 symbol 並發
5. **Config 驗證測試全面**：82 config tests 覆蓋所有驗證規則 + rollback + 並發
6. **策略測試完整**：81 tests，5 策略全覆蓋 entry/exit/params/boundary
7. **中英雙語測試文檔**：符合項目規範

### 弱點

1. **零測試模組過多**：4 個 .rs 文件 + 4 個 claude_teacher 子模組 = 8 個完全零覆蓋
2. **並發測試嚴重不足**：3E-ARCH 三管線架構是核心特性，但並發安全僅 1 個 ConfigStore 測試
3. **異常路徑比例低**：異常測試約佔 15%，正常路徑 70%，邊界 15%，建議異常提升至 25%
4. **無 #[should_panic] / #[ignore] 測試**：沒有任何預期 panic 測試或條件跳過測試
5. **Integration 測試未模擬真實 WS/REST**：所有 e2e 都是構造 PriceEvent 直驅，無網路層模擬

---

## 十一、建議優先修復順序 / Recommended Fix Order

| 優先級 | 工作項 | 預計測試數 | 預計工時 |
|--------|--------|-----------|---------|
| W22-1 | edge_estimates.rs 基本覆蓋 | +10 | 1h |
| W22-2 | REST timeout fail-closed 測試 | +3 | 2h |
| W22-3 | 三管線並發 e2e | +3 | 3h |
| W22-4 | WS 斷線重連模擬 | +5 | 3h |
| W22-5 | startup.rs 可測部分提取 | +5 | 2h |
| W23-1 | catch_unwind 後行為測試 | +3 | 1h |
| W23-2 | Config hot-reload 並發 | +3 | 2h |
| W23-3 | Price=0 / NaN / Inf 邊界 | +8 | 2h |
| W23-4 | rest_poller + quality_writer | +5 | 1h |
| W23-5 | claude_teacher 子模組 | +8 | 3h |

**預計新增**：~53 tests，完成後總計 ~4282，覆蓋率缺口關閉 80%。

---

## 十二、結論 / Conclusion

系統整體測試健康度 **B+**（良好偏上）。核心交易管線（策略→門控→執行→PnL→風控）覆蓋充分，回歸測試紀律模範。主要風險在：(1) `edge_estimates.rs` 完全裸奔且涉及 JSON 解析；(2) 三管線並發安全未端到端驗證；(3) REST timeout fail-closed 這個憲法級要求未測。建議 W22 優先處理 3 個 P0 + 前 2 個 P1，預計 ~10h 工作量可將系統測試評級提升至 **A-**。


---

# 7. E3 — 安全審核

> 原始文件：`docs/CCAgentWorkSpace/E3/2026-04-12--security_audit_report.md`

# E3 全面安全審計報告 / Full-Program Security Audit Report

**日期 / Date**: 2026-04-12
**審計員 / Auditor**: E3 Security Engineer
**範圍 / Scope**: Rust openclaw_engine/core/types/pyo3 + Python control_api_v1 + GUI 靜態文件
**基線 / Baseline**: commit `1961847` (main branch)

---

## 審計摘要 / Audit Summary

| 嚴重等級 | 數量 | 狀態 |
|---------|------|------|
| CRITICAL | 1 | 需立即處理 |
| HIGH | 4 | 建議本周內修復 |
| MEDIUM | 5 | 計劃中修復 |
| LOW | 4 | 可排入迭代 |

**總體評估**：系統安全基礎紮實。Rust 端所有 DB 查詢均使用參數化綁定（sqlx `$N` + `push_bind`），消除 SQL 注入風險。IPC HMAC-SHA256 認證、GUI HttpOnly cookie、CORS 白名單、CSP 頭、rate limiting、constant-time 密碼比對等關鍵安全控制均已到位。下列發現主要集中在 **配置完善度**（IPC 認證非強制）和 **前端 XSS 殘留場景**。

---

## 1. Gate 繞過分析 / Gate Bypass Analysis

### SEC-A01 [LOW] fast_track 閃崩/保證金危機分支為死碼

**文件**: `rust/openclaw_engine/src/tick_pipeline/on_tick.rs:156-160`

```rust
let ft_action = crate::fast_track::evaluate_fast_track(
    self.governance.risk.level,
    0.0, // PNL-4 dead input
    0.0, // PNL-4 dead input
);
```

**描述**: `price_drop_pct` 和 `margin_utilization_pct` 硬編碼為 `0.0`，導致 `fast_track.rs:35-43` 的閃崩偵測（>=5% 跌幅）和保證金危機（>=90% 使用率）兩條 CloseAll 路徑永遠不觸發。唯一可觸發的 CloseAll 是 `risk_level >= CircuitBreaker`。

**風險**: 真實閃崩或保證金危機時，這兩條安全防線無法啟動。已記錄為 PNL-4 待修。

**OWASP**: A04:2021 Insecure Design

**評級**: LOW（已有文檔追蹤，且 CircuitBreaker 路徑仍有效；Live 未上線）

---

### SEC-A02 [INFO] StrategyAction::Close 輕量路徑 — 設計正確

**文件**: `rust/openclaw_engine/src/tick_pipeline/on_tick.rs:841-940`

**結論**: Close 路徑正確跳過 Guardian / cost_gate / Kelly / P1 — 這是 **設計意圖**（平倉降低風險，不增加風險）。保留了：
- 費用計算（fee_rate 正確乘入）
- PG 持久化（emit_close_fill → TradingMsg::Fill）
- 影子訂單（exchange mode 的 dispatch_close_order）
- Kelly 統計更新
- 審計追蹤（recent_intents + recent_fills 環形緩衝）

**安全**: 無繞過問題。Close 不能被策略用於 _開倉_（因為它調用 `close_position_at_symbol_market` 而非 execute_market_fill）。

---

### SEC-A03 [INFO] P1 硬上限 — 實施正確

**文件**: `rust/openclaw_engine/src/intent_processor/router.rs:140-148` (paper) + `:382-388` (exchange)

```rust
let p1_max_qty = if price > 0.0 {
    balance * self.p1_risk_pct / price
} else {
    kelly_qty  // price=0 fallback: no cap — but qty=0 will be caught by PNL-1 below
};
let final_qty = kelly_qty.min(p1_max_qty);
```

**結論**: P1 上限在 paper 和 exchange 兩條路徑中均強制執行，且 `p1_risk_pct` 通過 `set_p1_risk_pct()` 有 clamp(0.001, 0.20) 範圍限制。`price <= 0` 時 PNL-1 的 `!(final_qty > 0.0)` 會攔截。

---

### SEC-A04 [INFO] Guardian 4-check — 完整且不可繞過

**文件**: `rust/openclaw_engine/src/intent_processor/router.rs:17-26` (Gate 1) + `:45-107` (Gate 2)

**結論**: `process()` 和 `process_gates_only()` 兩條路徑均強制通過：
1. Gate 1: governance authorization check (`is_authorized()`)
2. Gate 1.5: 同方向重複倉位阻擋
3. Gate 2: Guardian 4-check（drawdown、持倉數、方向）
4. Gate 2.5: Kelly sizing
5. Gate 2.6: P1 硬上限
6. Gate 2.7: RRC-1 訂單准入（日損/槓桿/曝險）
7. Gate 3: Cost gate（模式感知）

所有 gate 均 fail-closed（返回拒絕，不繼續執行）。

---

## 2. 注入漏洞 / Injection Vulnerabilities

### SEC-B01 [INFO] Rust SQL — 全部參數化（無注入風險）

**文件**: `rust/openclaw_engine/src/database/` 全部 writer + detector 文件

**結論**: 所有 Rust 端 SQL 查詢均使用 sqlx 的 `QueryBuilder::push_bind()` 或 `sqlx::query().bind()` 參數化綁定，包括：
- `trading_writer.rs`: 7 個 flush 函數全部用 `push_values + push_bind`
- `experiment_ledger_pg.rs`: `$1..$15` 參數化 INSERT/UPDATE/SELECT
- `drift_detector.rs`: 純常量 SQL，無用戶輸入
- `context_writer.rs`, `feature_writer.rs`, `quality_writer.rs`: 全部 `push_bind`

**安全**: 無 SQL 注入風險。

---

### SEC-B02 [MEDIUM] Python parquet_etl.py — f-string 格式化 SQL

**文件**: `program_code/ml_training/parquet_etl.py:56,65-72,77-84,93`

```python
conn.execute(f"ATTACH '{db_url}' AS pg (TYPE postgres, READ_ONLY);")
ctx_query = f"""
    COPY (
        SELECT * FROM pg.trading.decision_context_snapshots
        WHERE ts >= '{start_str}' AND ts < '{end_str}'
        ...
```

**描述**: 使用 f-string 格式化 SQL 查詢，db_url 和日期字符串直接插入。

**緩解因素**:
1. 此腳本為離線 ETL 工具（不是 API endpoint）
2. 輸入來源是 `datetime.utcnow()` 計算的日期（非用戶輸入）
3. `db_url` 來自內部配置
4. DuckDB 的 `ATTACH` 是獨立連接，與主 PG 隔離

**風險**: 低（無外部攻擊面），但違反了防禦性編碼原則。

**建議**: 使用 DuckDB 的參數化查詢或至少 validate/sanitize 日期格式。

**OWASP**: A03:2021 Injection

---

### SEC-B03 [MEDIUM] GUI tab-live.html — onclick 中的 symbol 注入點

**文件**: `app/static/tab-live.html:736`

```javascript
<td><button ... onclick="closeLivePosition('${sym}')">平倉</button></td>
```

其中 `sym = ocEsc(p.symbol || '')`。

**描述**: `ocEsc()` 轉義了 `<`, `>`, `&`, `"` 但 **未轉義單引號 `'`**。如果 Bybit 返回的 symbol 中包含單引號（如 `BTCUSDT'); alert('XSS`），可以逃出 onclick 的字符串字面量。

**ocEsc 實現** (`common.js:369-372`):
```javascript
function ocEsc(s) {
  if (s == null) return '';
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  // 缺少: .replace(/'/g, '&#x27;')
}
```

**緩解因素**:
1. Bybit API 的 symbol 格式為 `BTCUSDT`（純字母數字），實際上不可能包含單引號
2. `closeLivePosition()` 使用 `encodeURIComponent(symbol)` 構建 URL，但注入發生在 onclick 屬性中
3. CSP 有 `'unsafe-inline'`，無法阻止 inline event handler 中的腳本

**建議**: `ocEsc()` 追加 `.replace(/'/g, '&#x27;')` 以防禦性完整覆蓋。或改用 `addEventListener` 綁定事件。

**OWASP**: A03:2021 Injection (XSS)

**評級**: MEDIUM（實際可利用性極低，但屬 defense-in-depth 缺口）

---

### SEC-B04 [LOW] IPC 方法路由 — 無注入風險

**文件**: `rust/openclaw_engine/src/ipc_server/mod.rs:656`

**結論**: IPC dispatch 使用 Rust `match method {}` 靜態字符串匹配，只處理白名單方法。未知方法返回 `ERR_METHOD_NOT_FOUND`。`req.params` 透過 `serde_json::Value` 反序列化，類型安全。symbol 等字符串參數用 `as_str()` 提取後直接傳入業務邏輯（不拼接 SQL 或 shell 命令）。無命令注入風險。

---

## 3. 密鑰洩漏 / Secret Management

### SEC-C01 [INFO] API 密鑰日誌 — 未發現洩漏

**結論**: `grep` 掃描 Rust 全部 `tracing::` 調用，未發現任何對 `api_key`、`api_secret`、`secret`、`credential`、`password` 的日誌記錄。REST client 的 credentials 只在 HMAC 簽名時使用，簽名結果也未記錄。

---

### SEC-C02 [INFO] Secret 文件權限 — 實施正確

**文件**: `app/settings_routes.py:157-178`

```python
def _write_key_file(slot, filename, content):
    slot_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(slot_dir, stat.S_IRWXU)      # 700
    path.write_text(content.strip())
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)  # 600
```

**結論**: 目錄 chmod 700，文件 chmod 600，符合安全最佳實踐。`.gitignore` 已排除 `secrets/`、`**/secret_files/`、`*.env`。

---

### SEC-C03 [INFO] Rust secret 文件讀取 — 無路徑遍歷

**文件**: `rust/openclaw_engine/src/bybit_rest_client.rs:735-755`

**結論**: `read_secret_file(slot, name)` 的 slot 來源是硬編碼的 `BybitEnvironment::secret_slot()`（"demo" 或 "live"），name 來源是硬編碼字符串（"api_key", "api_secret", "bybit_endpoint"）。無用戶可控的路徑分量。

---

### SEC-C04 [INFO] Python settings_routes slot 驗證 — 已防護

**文件**: `app/settings_routes.py:384`

```python
if slot not in ALLOWED_SLOTS:
    raise HTTPException(status_code=400, ...)
```

ALLOWED_SLOTS 為硬編碼白名單 `{"demo", "live_demo", "live"}`，path traversal 不可能。

---

## 4. 認證與授權 / Authentication & Authorization

### SEC-D01 [CRITICAL] IPC HMAC 認證為可選（非強制）

**文件**: `rust/openclaw_engine/src/ipc_server/mod.rs:497`

```rust
if let Ok(secret) = std::env::var("OPENCLAW_IPC_SECRET") {
    // ... HMAC auth required
}
// If env var is absent → auth is SKIPPED (backward compatible)
```

**描述**: IPC HMAC-SHA256 認證僅在 `OPENCLAW_IPC_SECRET` 環境變量設置時啟用。如果未設置，任何能連接 Unix domain socket 的進程均可直接發送 IPC 命令，包括：
- `close_all_positions`（全倉平倉）
- `reset_paper_state`（重置餘額）
- `update_risk_config`（修改風控參數）
- `force_governor_tier_tighter` / `_looser`（覆蓋風控等級）
- `set_system_mode`（切換系統模式）

**緩解因素**:
1. Unix domain socket 受文件系統權限保護（通常只有同用戶進程可連接）
2. 代碼註釋明確標記為 "backward-compatible: dev/test mode"
3. G-3 任務已完成 IPC 認證實現

**風險**: 生產部署時如果忘記設置 `OPENCLAW_IPC_SECRET`，所有 IPC 命令均無需認證。Live 模式下這是嚴重風險 — 本機任何同用戶進程可操控交易引擎。

**建議**: 
1. Live 模式下強制要求 `OPENCLAW_IPC_SECRET`（啟動時檢查，缺失則 panic 或拒絕啟動 Live pipeline）
2. 文檔明確標記為 Live 前置條件

**OWASP**: A07:2021 Identification and Authentication Failures

---

### SEC-D02 [HIGH] Auth cookie 的 Secure 標誌為 False

**文件**: `app/legacy_routes.py:322`

```python
resp.set_cookie(
    key="oc_auth_token",
    value=settings.api_token,
    httponly=True,
    samesite="strict",
    secure=False,  # TODO: Set True when HTTPS is enabled
)
```

**描述**: `secure=False` 意味著 cookie 會在 HTTP 明文連接中傳輸。如果系統通過非 HTTPS 的網絡訪問（包括 Tailscale 內的 HTTP），auth token 可能被中間人截取。

**緩解因素**:
1. 系統目前通過 Tailscale（WireGuard 加密隧道）訪問
2. SameSite=Strict 防止 CSRF
3. 代碼有 TODO 標記

**建議**: 當 HTTPS 啟用後立即改為 `secure=True`。或改為根據環境變量動態設置。

**OWASP**: A02:2021 Cryptographic Failures

---

### SEC-D03 [HIGH] GUI 靜態文件無認證保護

**文件**: `app/main_legacy.py` (StaticFiles mount 區域)

**描述**: `/static/` 路徑下的 HTML/JS 文件作為靜態資源掛載，不受 auth middleware 保護。雖然 `common.js` 中的 `ocAuthCheck()` 在頁面加載時做了 async auth 檢查（fetch `/api/v1/auth/check`），但：
1. 靜態 HTML/JS 本身可被未認證用戶下載和閱讀
2. Auth check 是客戶端 JavaScript 實施的，可被繞過
3. 所有 API 端點均需 auth，所以數據本身是安全的

**緩解因素**:
1. 靜態文件不含敏感數據（密鑰、餘額等需通過 API 獲取）
2. 所有寫操作端點有 `Depends(_get_auth_actor)` / `Depends(_require_operator_auth)` 保護
3. Tailscale 限制了網絡可達性

**風險**: 攻擊者可查看 GUI 結構和 JavaScript 邏輯（信息洩露），但無法獲取或修改數據。

**OWASP**: A01:2021 Broken Access Control

**評級**: HIGH（信息洩露 + 攻擊面暴露）

---

### SEC-D04 [INFO] 登錄 brute-force 防護 — 已實施

**文件**: `app/legacy_routes.py:221-303`

**結論**: 
- Rate limit: 5/minute per IP（`@limiter.limit("5/minute")`）
- IP lockout: 5 次失敗 / 15 分鐘窗口 → 429 lockout
- Constant-time comparison: `hmac.compare_digest()` 用於用戶名和密碼
- OOM 防護: `_LOGIN_FAIL_MAX_IPS` 容量上限 + FIFO 淘汰

---

### SEC-D05 [INFO] Execution authority 生命週期 — 設計正確

**結論**: Live session start 時自動授予 execution_authority，stop 時撤銷。SM-1 治理授權完整生命週期（DRAFT→PENDING→ACTIVE→REVOKED）。Live 縮倉監控（5 分鐘輪詢，回撤 ≥15% 自動撤銷）。`_EXECUTION_AUTHORITY_OVERRIDE` 為 in-memory gate，重啟清空（fail-closed）。

---

## 5. XSS 分析 / Cross-Site Scripting Analysis

### SEC-E01 [HIGH] ocEsc() 缺少單引號轉義

**文件**: `app/static/common.js:369-372`

```javascript
function ocEsc(s) {
  if (s == null) return '';
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
```

**描述**: 缺少 `'` → `&#x27;` 的轉義。當 ocEsc 結果用於單引號包裹的 HTML 屬性時（如 `onclick="fn('${ocEsc(val)}')"` — 見 SEC-B03），攻擊者可注入 JavaScript。

**影響範圍**: 搜索所有 `ocEsc` 用於單引號上下文的位置：
- `tab-live.html:736`: `onclick="closeLivePosition('${sym}')"` -- sym 來自 Bybit API
- 其他位置主要用在 `${}` 模板字面量中的 innerHTML，用雙引號包裹或作為文本內容，風險較低

**建議**: 
```javascript
function ocEsc(s) {
  if (s == null) return '';
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#x27;');
}
```

**OWASP**: A03:2021 Injection (XSS)

---

### SEC-E02 [MEDIUM] tab-system.html 確認對話框使用 innerHTML 填充硬編碼 HTML

**文件**: `app/static/tab-system.html:392-393,442-443`

```javascript
$('confirm-title').innerHTML = msg.title;
$('confirm-body').innerHTML = msg.body;
```

**描述**: `CONFIRM_MSGS` 和 `MODE_CONFIRM` 的 title/body 來自 JavaScript 常量對象（硬編碼的 HTML 片段）。目前無用戶輸入注入點。

**風險**: LOW（當前安全，但如果未來重構將用戶數據加入確認消息，可能引入 XSS）

---

### SEC-E03 [MEDIUM] tab-phase4.html 卡片加載模式 — 自源 HTML 注入

**文件**: `app/static/tab-phase4.html:174-203`

```javascript
fetch('/static/cards/teacher_card.html', { credentials: 'same-origin' })
  .then(r => r.ok ? r.text() : '')
  .then(html => {
    tmp.innerHTML = html;
    // ... execute inline scripts
    var ns = document.createElement('script');
    ns.textContent = s.textContent;
    document.body.appendChild(ns);
  });
```

**描述**: 從同源 `/static/cards/` 加載 HTML 片段，設置 innerHTML 並執行內嵌 script。

**緩解因素**:
1. Same-origin fetch（CORS 限制）
2. 加載的 card HTML 是開發者控制的靜態文件
3. CSP `script-src 'self' 'unsafe-inline'` 允許此模式

**風險**: LOW（self-origin 模式本身安全，但 `'unsafe-inline'` CSP 降低了整體防禦深度）

---

### SEC-E04 [INFO] 其他 innerHTML 使用 — 已正確轉義

**文件**: 多個 tab HTML 文件

**結論**: 掃描所有 innerHTML 賦值點：
- `tab-live.html`: 所有 Bybit 數據欄位均通過 `ocEsc()` 轉義（symbol, side, qty, price, orderId 等）
- `tab-ai.html`: strategy 名稱使用 `ocEsc(k)`, Kelly tier 使用 `ocEsc(s.kelly_tier)`
- `linucb_card.html`: regime 使用 `ocEsc(reg)`
- `news_card.html`: 明確聲明 "never innerHTML" 用於用戶內容，使用 `textContent`
- `teacher_card.html`: 使用 `textContent` 用於 directive 欄位（XSS 防護註釋）
- `dl3_card.html`: 使用 `textContent` 用於 model/symbol
- `tab-settings.html`: key_hint 使用 `ocEsc(hint)`，錯誤消息使用 `ocEsc(errMsg)`

**例外**: `ocExplain()` 函數輸出硬編碼的 HTML 解釋文本（非用戶數據），用於 `innerHTML` 是安全的。

---

## 6. 其他 OWASP Top 10 發現 / Other OWASP Findings

### SEC-F01 [HIGH] CSP 使用 'unsafe-inline' 削弱防護

**文件**: `app/main_legacy.py:335-343`

```python
"script-src 'self' 'unsafe-inline' https://unpkg.com; "
"style-src 'self' 'unsafe-inline'; "
```

**描述**: `'unsafe-inline'` 允許所有 inline script/style 執行，使 CSP 對 XSS 的防護大幅削弱。這是因為 GUI 大量使用 inline `<script>` 和 `<style>` 標籤。

**緩解因素**: CSP 仍然阻止了來自未白名單域的腳本加載，`connect-src 'self'` 限制了數據外洩管道。

**建議**: 長期遷移到 nonce-based CSP（`script-src 'nonce-xxx'`），逐步消除 inline scripts。

**OWASP**: A05:2021 Security Misconfiguration

---

### SEC-F02 [MEDIUM] CORS allow_methods 允許 POST 到所有端點

**文件**: `app/main_legacy.py:290-296`

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)
```

**描述**: 當 `OPENCLAW_CORS_ORIGINS` 配置了外部域時，該域的 JavaScript 可以向所有 POST 端點發送帶 cookie 的跨域請求。

**緩解因素**:
1. 默認 `_cors_origin_list` 為空（同源訪問）
2. SameSite=Strict cookie 阻止跨站 cookie 附加
3. 通配符 `*` 已被啟動時強制移除

**風險**: 低（需要 operator 主動配置外部 origins，且 SameSite=Strict 提供額外防線）

---

### SEC-F03 [MEDIUM] 缺少 API 端點級別的 CSRF 保護

**描述**: 除了 SameSite=Strict cookie（瀏覽器層面防護）外，API 端點沒有獨立的 CSRF token 驗證。某些老式瀏覽器或特定攻擊向量可能繞過 SameSite。

**緩解因素**:
1. SameSite=Strict 是現代瀏覽器的有效 CSRF 防護
2. 系統通過 Tailscale 訪問，攻擊面極小
3. 所有寫操作需 auth（`Depends(_get_auth_actor)`）

**建議**: 考慮為高危操作（live session start、全倉平倉、execution authority grant/revoke）加入 CSRF token 或二次確認機制。

**OWASP**: A01:2021 Broken Access Control

---

### SEC-F04 [LOW] Python logger 可能記錄敏感上下文

**文件**: `app/settings_routes.py:419,429`

```python
logger.warning("API key conflict: slot '%s' key matches '%s' slot (actor: %s)", ...)
logger.info("Validating Bybit API key for slot '%s' (actor: %s)", ...)
```

**描述**: 日誌記錄了 slot 名稱和 actor ID，但 **未記錄明文 key/secret**。`_mask_key()` 僅顯示最後 4 字符。驗證結果的錯誤消息 `err_msg` 來自 Bybit API 回應（可能包含部分 key hint）。

**結論**: 當前安全，但建議對 `err_msg` 做截斷/過濾以防未來 Bybit API 回應格式變更洩漏敏感信息。

---

### SEC-F05 [LOW] Unix socket 文件權限未設置

**文件**: `rust/openclaw_engine/src/ipc_server/mod.rs:400-440`（`start_server` 函數）

**描述**: `UnixListener::bind(socket_path)` 創建的 socket 文件繼承 umask 權限，未顯式設置為 0700。同用戶的其他進程可連接。

**緩解因素**: Unix domain socket 已受文件系統所有者保護；結合 HMAC auth（若啟用）可充分防護。

**建議**: 啟動後立即 `chmod(socket_path, 0o600)` 限制 socket 訪問。

---

## 7. 安全控制檢查清單 / Security Controls Checklist

| 控制項 | 狀態 | 備註 |
|--------|------|------|
| SQL 注入防護（Rust） | ✅ 完備 | 全部 sqlx 參數化綁定 |
| SQL 注入防護（Python） | ⚠️ parquet_etl | 離線工具，風險低 |
| XSS 防護 — ocEsc() | ⚠️ 缺單引號 | SEC-E01 |
| XSS 防護 — innerHTML 覆蓋 | ✅ 大部分完備 | news_card/teacher/dl3 使用 textContent |
| IPC HMAC 認證 | ⚠️ 非強制 | SEC-D01 |
| GUI 登錄認證 | ✅ 完備 | HttpOnly cookie + brute-force 防護 |
| API 認證中間件 | ✅ 完備 | Depends() 注入 |
| CORS 配置 | ✅ 安全 | 禁止 * + credentials |
| CSP | ⚠️ unsafe-inline | SEC-F01 |
| Rate limiting | ✅ 完備 | 全局 120/min + 登錄 5/min |
| Secret 文件保護 | ✅ 完備 | chmod 600 + .gitignore |
| 密鑰日誌洩漏 | ✅ 未發現 | 無 credential 記錄 |
| Cookie 安全標誌 | ⚠️ secure=False | SEC-D02 |
| CSRF 防護 | ✅ SameSite=Strict | 可加強 |
| 安全響應頭 | ✅ 完備 | X-Frame, X-XSS, nosniff, CSP |
| 常數時間比較 | ✅ 完備 | HMAC verify_slice / compare_digest |

---

## 8. 建議優先修復順序 / Recommended Fix Priority

1. **SEC-D01** [CRITICAL] — Live 模式強制 IPC secret（啟動時 guard）
2. **SEC-E01** [HIGH] — ocEsc() 追加單引號轉義（1 行修改）
3. **SEC-D02** [HIGH] — Cookie secure 標誌動態化（根據 HTTPS 環境）
4. **SEC-D03** [HIGH] — 靜態文件目錄加 auth middleware（或評估接受風險）
5. **SEC-F01** [HIGH] — CSP nonce 遷移規劃（長期）
6. **SEC-B03** [MEDIUM] — tab-live.html onclick 改用 addEventListener
7. **SEC-B02** [MEDIUM] — parquet_etl 參數化
8. **SEC-F03** [MEDIUM] — 高危操作 CSRF token
9. **SEC-A01** [LOW] — fast_track 死碼修復（PNL-4）
10. **SEC-F05** [LOW] — Unix socket chmod

---

*審計完成 / Audit complete. E3 Security Engineer, 2026-04-12.*


---

# 8. CC — 合規檢查

> 原始文件：`docs/CCAgentWorkSpace/CC/2026-04-12--compliance_audit_report.md`

# CC 合規審計報告 — 2026-04-12

**審計員**：CC（Compliance Checker）
**審計範圍**：CLAUDE.md 16 根原則 + 代碼規範 + 工作流 + 硬邊界
**審計基準**：commit `1392006`（main branch HEAD）
**測試基線**：engine lib 939 + core 366 + e2e 18 + promotion 32 = 1355 / Python 2852 passed 0 fail

---

## 一、16 根原則合規審計

### 原則 #1：單一寫入口 — ✅ PASS

**證據**：所有交易意圖統一通過 `IntentProcessor`（`intent_processor/router.rs`）處理。`process()` 用於 Paper 模式完整執行，`process_gates_only()` 用於 Exchange 模式門禁。訂單派發通過 `order_manager.rs` 的 `place_order()` 單一入口送往 Bybit API。平倉路徑統一經 `close_position_at_symbol_market()` + `emit_close_fill()`。

**發現**：`StrategyAction::Close` 路徑繞過 Guardian/cost_gate/Kelly，但這是設計意圖（降風險不增風險），且仍經 `emit_close_fill` 留完整審計紀錄。符合原則精神。

---

### 原則 #2：讀寫分離 — ✅ PASS

**證據**：Python 層在 DEAD-PY-2 後已**完全無交易邏輯**，僅剩 API 橋接 + GUI 路由 + 輔助工具。所有交易/風控參數 GUI 直寫 Rust ConfigStore（通過 IPC），Python 僅只讀。`RiskConfig` 為純派生視圖，`GuardianConfig` 無獨立狀態（`ARCH-RC1 1C-4 E-Merge-4` 明確記載）。

---

### 原則 #3：AI 輸出 ≠ 即時命令 — ✅ PASS

**證據**：`DecisionLeaseSm` 完整實現於 `openclaw_core/src/sm/lease.rs`，9 狀態 + 20 合法遷移 + 12 禁止遷移 + 5 守衛。`GovernanceCore`（`governance_core.rs`）集成 `DecisionLeaseSm`。`IntentProcessor.process()` Gate 1 即驗 `governance.is_authorized()`，未授權直接 fail-closed 返回。

**注意**：H1-H5 AI 治理層當前全為 stub（CLAUDE.md 確認），待 W22 實現。Decision Lease 機制已就位，但實際 AI→Lease→執行的端到端路徑尚未激活。

---

### 原則 #4：策略不能繞過風控 — ✅ PASS

**證據**：
- `StrategyAction::Open` → 完整治理管線：Gate 1 Governance auth → Gate 1.5 重複檢查 → **Gate 2 Guardian 4-check** → Gate 2.5 Kelly sizing → Gate 3 cost gate → Gate 4 global cap
- `process_gates_only()`（Exchange 路徑）同樣包含 Guardian review（`router.rs:332`）
- Guardian 四項檢查：方向衝突、槓桿上限、回撤限制、持倉數量
- `StrategyAction::Close` 繞過 Guardian 但只減倉不增倉（設計文檔明確標註）

---

### 原則 #5：生存 > 利潤 — ✅ PASS

**證據**：
- fail-closed 遍布代碼：`position_risk_evaluator.rs:56` entry_price=0 → -999%（強制硬止損）
- `intent_processor/gates.rs:137` 負 edge estimate → fail-closed
- `ipc_server` 未初始化時 fail-closed（-32603）
- Session halt + CloseAll 機制（`RiskAction::HaltSession`）
- Reconciler 自動降級：MinorDrift→Cautious→Defensive→CircuitBreaker+CloseAll
- H0 Gate 硬阻斷時仍處理止損（`on_tick.rs:204`："H0 BLOCKED — stops only"）
- Paper paused 時保護性止損繼續運行（`on_tick.rs:309-325`）

---

### 原則 #6：失敗默認收縮 — ✅ PASS

**證據**：
- `_EXECUTION_AUTHORITY_OVERRIDE` 為記憶體內變量，進程重啟自動清零（fail-closed）
- Reconciler 漸進升級：Cautious→Defensive→CircuitBreaker，逐級收緊
- REST 失敗 ≥10 次 → Cautious
- Burst ≥5 → CircuitBreaker + CloseAll
- 冷卻期機制（H0Gate cooldown + PNL-3 boot cooldown）
- System mode gate 阻止不當模式下的交易

---

### 原則 #7：學習 ≠ 改寫 Live — ⚠️ PARTIAL

**證據**：Signal Diamond 設計將信號寫入隔離（僅 Paper 寫，`on_tick.rs:378`）。Per-engine `PerEngineRiskStores` + `StrategyFactory::create_for_engine()` 實現三引擎獨立。

**風險點**：ClaudeTeacher `applier.rs`（1257 行）可透過 IPC 修改策略參數。雖有 `strategy_ipc_impl.rs:213` 的 fail-closed 路徑（IPC timeout/cancelled），但學習平面→Live 平面的寫入隔離邊界需要更強的形式化驗證。當前 AI Agent 層全 stub，待 W22 實現後此項需重新審計。

---

### 原則 #8：交易可解釋 — ✅ PASS

**證據**：
- `emit_close_fill()` 每次平倉寫入完整 Fill 記錄（symbol、qty、price、pnl、fee、reason）到 PG trading_tx
- Guardian verdict（含拒絕）持久化到 `trading.risk_verdicts`
- Intent 記錄（strategy_name、side、qty、price）持久化到 PG
- Signal 記錄（signal_id、strategy_name、direction、confidence）持久化
- DecisionContext（LinUCB arm、新聞快照）寫入 PG
- `recent_intents` / `recent_fills` / `recent_signals` 環形緩衝供 IPC 快照
- Canary mode 全量記錄（schema_version + tick_number + indicators + signals + intents + paper_state）
- PositionSnapshot 每 1000 ticks 發射供 ML 訓練

---

### 原則 #9：交易所災難保護 — ✅ PASS

**證據**：
- **本地止損**：`paper_state.check_stops()` → `stop_manager::check_stops()` 多路徑觸發（H0 blocked / paused / normal tick）
- **交易所條件單**：`event_consumer/mod.rs:260-325` 雙軌止損通道，`server_side_stops` 配置項（default: true），`position_manager.set_trading_stop()` 發送 Bybit `set-trading-stop` API
- 測試覆蓋：`test_dual_rail_broker_sl_long_below_entry`、`test_dual_rail_broker_sl_short_above_entry`、`test_dual_rail_close_orders_no_broker_sl`
- API 失敗時 fail-closed：本地 StopManager 仍生效（`event_consumer/mod.rs:290`）
- 黑天鵝檢測器（`black_swan_detector.rs`）4 信號投票，severity 達標時 warn

---

### 原則 #10：認知誠實 — ✅ PASS

**證據**：
- Phase 5 pause 決策體現了認知誠實：發現所有策略 gross edge 為負後立即暫停（而非掩蓋）
- PNL-FIX-1/2 修復後基線重建，明確記錄「前提已作廢」
- `cost_gate` JS-live 的 fail-closed：無估計 → 阻斷開倉，不猜測

---

### 原則 #11：Agent 最大自主權 — ⚠️ PARTIAL

**證據**：策略通過 `on_tick()` 獨立決策 symbol/方向/timing，Orchestrator 多策略並行，Scanner 動態 symbol 選擇。

**不足**：AI Agent 層（H1-H5）全 stub，Strategist/Guardian/Analyst/Executor/Scout 5 Agent 尚未實現。當前 Agent 自主權僅限於確定性策略的參數範圍內，W22 G-1 計劃中。

---

### 原則 #12：持續進化 — ⚠️ PARTIAL

**證據**：
- LinUCB contextual bandit（`linucb/` 模組）用於策略 arm selection
- Kelly sizer（`ml/kelly_sizer.rs`）基於歷史統計動態 sizing
- ClaudeTeacher（`claude_teacher/`）接收外部 AI 教學
- Feature collector → PG → ML training pipeline 基礎設施就位

**不足**：Phase 5 揭露所有策略 gross 負 edge，學習系統正在學習虧損策略。學習→Live 自動部署（Phase 3 放權框架）尚未實現。

---

### 原則 #13：AI 資源成本感知 — ✅ PASS

**證據**：
- `ai_budget/tracker.rs`：BudgetTracker 實現 5 個 scope（local_total / platform_hard_cap / 3 agent scopes）
- `cost_edge_ratio()` 方法計算 used/limit
- 三段降級閾值基於 `local_total` scope
- `ai_budget/pricing.rs` 定價表（當前 placeholder，4-17 改 PG 表）
- IPC `update_ai_budget_config` 寫入路徑 fail-closed（未初始化 → -32603）
- `intent_processor/gates.rs` Gate 3 cost gate 實際生效

---

### 原則 #14：零外部成本可運行 — ✅ PASS

**證據**：系統設計 L0（確定性）+ L1（Ollama 本地）可完全離線運行。H1-H5 AI 層全 stub 不影響基礎交易功能。BudgetConfig 有 $0 baseline fallback。

---

### 原則 #15：多 Agent 協作 — ⚠️ PARTIAL

**證據**：`multi_agent_framework.py`（1104 行）存在框架代碼。`strategist_agent.py`（1162 行）已有基礎。

**不足**：5 Agent + Conductor 編排尚為 stub，正式對象通信未實現。W22 計劃中。

---

### 原則 #16：組合級風險意識 — ✅ PASS

**證據**：
- Guardian `max_same_direction_positions` 限制（default: 3）
- Portfolio context 傳入 Guardian review（`PortfolioContext { drawdown_pct, positions }`）
- `position_risk_evaluator.rs` 9-check 逐倉評估
- `intent_processor` daily loss tracking（`maybe_reset_daily_balance`）
- Session drawdown monitoring + halt mechanism
- Live 縮倉監控：5% 警告 / 15% 自動平倉

---

## 二、代碼規範合規

### 2.1 文件大小限制 — ❌ FAIL

**800 行警告線（⚠️）以上非測試文件（共 19 個）**：

| 行數 | 文件 | 狀態 |
|------|------|------|
| **1914** | governance_routes.py | ❌ **超硬上限 60%** |
| **1812** | governance_hub.py | ❌ **超硬上限 51%** |
| **1452** | signal_generator.py | ❌ **超硬上限 21%** |
| **1381** | risk_config.rs | ❌ **超硬上限 15%** |
| **1352** | backtest_engine.py | ❌ **超硬上限 13%** |
| **1302** | event_consumer/mod.rs | ❌ **超硬上限 9%** |
| **1257** | claude_teacher/applier.rs | ❌ **超硬上限 5%** |
| **1228** | on_tick.rs | ❌ **超硬上限 2%** |
| **1203** | live_session_routes.py | ❌ **超硬上限 0.25%** |
| 1192 | tick_pipeline/mod.rs | ⚠️ 接近硬上限 |
| 1192 | ipc_server/handlers.rs | ⚠️ 接近硬上限 |
| 1179 | legacy_routes.py | ⚠️ |
| 1164 | strategy_auto_deployer.py | ⚠️ |
| 1162 | strategist_agent.py | ⚠️ |
| 1158 | grid_trading.rs | ⚠️ |
| 1151 | order_manager.rs | ⚠️ |
| 1104 | multi_agent_framework.py | ⚠️ |
| 1086 | klines.rs | ⚠️ |
| 1067 | h0_gate.rs | ⚠️ |

**裁定**：9 個文件超過 1200 行硬上限，其中 `governance_routes.py`（1914 行）最嚴重，CLAUDE.md §三 已標注為 pre-existing 需 refactor。10+ 文件在 800-1200 警告區間。此項 FAIL。

---

### 2.2 雙語注釋 — ✅ PASS

**抽查結果**：
- `on_tick.rs`：每個步驟、分支、修復標記均有中英對照注釋 ✅
- `guardian.rs`：MODULE_NOTE + struct/function docstring 雙語 ✅
- `intent_processor/router.rs`：Gate 描述中英對照 ✅
- `bybit_rest_client.rs`：方法 docstring 雙語 ✅
- `ai_budget/tracker.rs`：MODULE_NOTE 中英完整 ✅
- `live_session_routes.py`：文件頭 MODULE_NOTE 中英 ✅
- 124 個 Rust 文件含 MODULE_NOTE（`Grep` MODULE_NOTE 結果）

---

### 2.3 跨平台兼容性 — ✅ PASS

**路徑硬編碼檢查**：
- Rust 代碼：`grep /home/ncyu` → **零匹配** ✅
- Python 代碼：僅 `bybit_path_policy.py` 存在引用，且為反硬編碼工具（`COMPAT_ROOT = REPO_ROOT # No longer hardcoded`） ✅
- `Path(__file__).parent` 相對路徑廣泛使用 ✅

---

### 2.4 模塊依賴方向 — ✅ PASS

**證據**：
- Python route 文件統一 `from . import main_legacy as base`（18 個文件確認）
- 循環依賴防護：`h1_thought_gate.py` 明確禁止同目錄 import，`governance_routes.py` 用 lazy import 避免循環
- Rust 方面：`openclaw_core` → `openclaw_types` → `openclaw_engine` 依賴方向清晰

---

### 2.5 Singleton 管理 — ⚠️ PARTIAL

**已登記 Singleton（CLAUDE.md §九）**：settings / STORE / app / limiter — 全通過 `base.*` 引用 ✅

**發現的未登記 Singleton**：
- `LeaseTTLConfigManager._instance`（`lease_ttl_config.py:403`）— 雙重鎖 singleton
- `ExperimentLedger` module-level singleton（`experiment_routes.py:66`）
- `PromotionGate._instance`（`governance_routes.py:1719`）— 函數屬性 singleton
- `strategy_ai_routes.py:38` BybitClient lazy singleton
- `strategy_wiring.py:83` 多個 module-level singletons

**裁定**：≥5 個未在 CLAUDE.md §九 singleton 表中登記的 singleton。功能正常但不符合登記規則。

---

## 三、工作流合規

### 3.1 E2+E4 強制工作鏈 — ✅ PASS

**近 30 commit 分析**：
- 修復提交（`fix(*)`）均有具體問題追蹤號（PNL-FIX-1、B-1、B-2、M-1~M-4）
- L3 審計提交存在：`b4efe49 fix(3e-arch): L3 audit — e2e tests, 21 warnings, defensive hardening`
- E2E 測試：18 個 e2e + 32 個 promotion 測試
- 測試基線持續更新：939/366/18/32/2852

---

### 3.2 文檔同步規則 — ✅ PASS

**證據**：
- `CLAUDE_CHANGELOG.md` 持續更新（grep 確認多次 commit 追加）
- CLAUDE.md §三 與實際代碼狀態一致（3E-ARCH / Multi-Symbol / Phase 5 PAUSED 等）
- Worklogs 目錄結構化管理（`docs/worklogs/`、`docs/archive/`）
- TODO.md 追蹤活躍（commit `1a4bd3a` 專門更新 TODO）

---

## 四、硬邊界合規

### 4.1 Live 安全防護 — ✅ PASS

**證據**：
- Live session start 雙重門控：(1) `_require_operator(actor)` 角色認證 + (2) `global_mode` 必須含 "live"（`live_session_routes.py:638-652`）
- `_EXECUTION_AUTHORITY_OVERRIDE` 記憶體內，重啟清零 fail-closed ✅
- System mode gate 在 `on_tick.rs:456-477` 阻止不當模式交易 ✅
- `OPENCLAW_ALLOW_MAINNET` env var 已移除（SEC-17 架構決策），API key 為唯一門控 ✅
- Live 縮倉監控：回撤 ≥5% 警告 / ≥15% 自動撤銷 + 平倉 + 凍結 ✅

---

### 4.2 Fail-Closed 行為 — ✅ PASS

**全系統 fail-closed 路徑確認**：
- Bybit API retCode != 0 → `BybitError::Api` 返回 Err（`bybit_rest_client.rs:37`）
- `is_retryable()` 僅標記可重試，但 **max_retries = 0**（硬邊界），不自動重試 ✅
- IPC 未初始化 → -32603 error code ✅
- entry_price = 0 → -999% 強制硬止損 ✅
- 負 edge estimate → fail-closed 阻斷 ✅
- 授權過期 → 自動拒絕 ✅

---

### 4.3 禁止行為確認 — ✅ PASS

- 繞過 Operator 角色認證直接啟動 live session → `_require_operator()` 阻止 ✅
- 自動修改 trading_mode 為 live → 需 operator 顯式配置 TOML ✅
- `should_call_ai=true` 但未發生 → H1-H5 全 stub，不會出現此矛盾 ✅
- 偽造 AI 調用/交易活動 → 無偽造路徑存在 ✅

---

## 五、綜合評分

| 類別 | 評分 | 說明 |
|------|------|------|
| 根原則 1-6 | ✅ 6/6 PASS | 核心風控架構健全 |
| 根原則 7 | ⚠️ PARTIAL | 學習→Live 隔離需形式化驗證 |
| 根原則 8-10 | ✅ 3/3 PASS | 審計/災難防護/認知誠實 |
| 根原則 11-12 | ⚠️ 2/2 PARTIAL | AI Agent 層 stub，待 W22 |
| 根原則 13-14 | ✅ 2/2 PASS | 成本感知 + 零外部成本 |
| 根原則 15 | ⚠️ PARTIAL | Multi-Agent 框架存在但未激活 |
| 根原則 16 | ✅ PASS | 組合風險監控完備 |
| 文件大小 | ❌ FAIL | 9 文件超 1200 硬上限 |
| 雙語注釋 | ✅ PASS | 覆蓋良好 |
| 跨平台 | ✅ PASS | 無硬編碼路徑 |
| 依賴方向 | ✅ PASS | 無循環 import |
| Singleton | ⚠️ PARTIAL | ≥5 個未登記 |
| E2+E4 | ✅ PASS | 工作鏈執行一致 |
| 文檔同步 | ✅ PASS | 規則遵守 |
| Live 安全 | ✅ PASS | 雙重門控 + fail-closed |
| Fail-Closed | ✅ PASS | 全系統覆蓋 |

**總體評級**：⚠️ **PARTIAL PASS** — 核心安全/風控/審計架構健全，無 P0 阻塞項。主要差距集中在：(1) 文件大小違規（pre-existing，已記錄在案）；(2) AI Agent 層 stub（W22 計劃中）；(3) Singleton 登記不完整。

---

## 六、建議行動項

| 優先級 | 項目 | 說明 |
|--------|------|------|
| P1 | 文件拆分 | `governance_routes.py`（1914行）、`governance_hub.py`（1812行）必須拆分至 1200 以下 |
| P2 | Singleton 登記 | 將 5+ 個未登記 singleton 補入 CLAUDE.md §九 表 |
| P2 | 策略重做 | G-SR-1 / Strategist Agent — 所有策略 gross 負 edge，學習系統正學習虧損 |
| P3 | 學習隔離驗證 | ClaudeTeacher 寫入路徑需形式化邊界定義 |
| P3 | AI Agent 實現 | W22 G-1 完成後重新審計原則 #11/#12/#15 |

---

*審計完成時間：2026-04-12*
*下次計劃審計：W22 末（AI Agent 層實現後）*


---

# 9. QC — 策略算法 · 風控邏輯 · 數學審計

> 原始文件：`docs/CCAgentWorkSpace/QC/2026-04-12--strategy_risk_math_audit_report.md`

# QC 審計報告：策略算法 / 風控邏輯 / 數學正確性
# QC Audit Report: Strategy Algorithms / Risk Control Logic / Math Correctness

**審計日期 / Audit Date**: 2026-04-12
**審計範圍 / Scope**: 5 策略 + IntentProcessor 治理管線 + Guardian + Kelly + 風控檢查 + 16 指標 + 成本門
**審計結論 / Conclusion**: 數學公式整體正確，架構設計嚴謹。發現 **3 個 P1** + **7 個 P2** + **12 個 [HARDCODED]** 需關注。

---

## 一、策略算法審計 / Strategy Algorithm Audit

### 1.1 MaCrossover (`ma_crossover.rs`)

**信號邏輯 / Signal Logic:**
- 快線 = KAMA（自適應），慢線 = SMA(20)。KAMA 缺失時 fallback 到 SMA(20)，此時 fast == slow，永不交叉。 **[正確，fail-safe]**
- ADX < threshold 時跳過，防止在盤整市場假信號。 **[正確]**
- RC-01 Hurst regime filter：僅 `trending` 允許入場，`mean_reverting` / `random_walk` 阻擋。**出場不受此過濾影響。** **[正確，防止在不利 regime 開倉]**
- RC-02 Higher-TF confirmation：用 SMA(50) 的 EMA（alpha=0.003）模擬 4h 趨勢。做多需 bullish，做空需 bearish。**出場不受此過濾影響。** **[正確]**

**Confidence 計算:**
- `compute_entry_confidence`: base=0.45, adx_bonus up to +0.25, regime_bonus +/-0.15, clamp [0.2, 0.9]。 **[合理]**
- `compute_exit_confidence`: base=0.5, adx_bonus up to +0.2, clamp [0.4, 0.8]。 **[合理]**

**問題與發現:**

1. **[HARDCODED] 入場 confidence 參數**: `base=0.45`, `adx_bonus_divisor=100`, `regime_bonus=0.15`, exit `base=0.5`。這些值無法從 TOML 配置，需依賴硬編碼重編譯。**建議：加入 StrategyParams 或至少作為 const。**

2. **[P2] KAMA fallback 靜默退化**: 當 `kama` 為 None 時 fallback 到 `sma_20`，導致 `fast == slow == sma_20`，策略靜默失活而非報錯。建議加 `tracing::debug` 記錄此降級。

3. **[HARDCODED] higher_tf EMA alpha=0.003**: 已在 `MaCrossoverParams` 中可配置（agent_adjustable=true），**此項合規。**

---

### 1.2 BbReversion (`bb_reversion.rs`)

**信號邏輯 / Signal Logic:**
- 入場：`percent_b < 0.0 && RSI < 30.0`（超賣做多）或 `percent_b > 1.0 && RSI > 70.0`（超買做空）。**[正確，雙確認防假信號]**
- 出場：`percent_b in [0.2, 0.8]`（均值回歸目標達成）。**[正確，比精確 0.5 更寬容，適合加密貨幣超調]**
- Hurst regime boost：`mean_reverting` regime 時入場 confidence +0.1。**[正確，均值回歸 regime 提升均值回歸策略信心]**

**問題與發現:**

4. **[HARDCODED] RSI 閾值 30/70**: RSI 超賣/超買閾值硬編碼在 `on_tick` 邏輯中。加密貨幣市場 RSI 動態範圍與傳統市場不同，應可配置。**建議：加入 BbReversionParams（`rsi_oversold`, `rsi_overbought`）。**

5. **[HARDCODED] 出場 %B 區間 [0.2, 0.8]**: 均值回歸目標區間硬編碼。不同市場狀態下最佳出場帶可能不同。**建議：可配置化。**

6. **[HARDCODED] 入場 confidence base=0.6, 出場 base=0.55**: 與 MaCrossover 同類問題，confidence 參數硬編碼。

7. **[HARDCODED] Hurst boost=0.1**: 相同問題。

---

### 1.3 BbBreakout (`bb_breakout.rs`)

**信號邏輯 / Signal Logic:**
- 入場條件：(1) 先檢測 squeeze（`bandwidth < squeeze_bw`），(2) 然後等 expansion（`bandwidth > expansion_bw`），(3) volume_ratio 確認，(4) Donchian 通道突破確認，(5) %B 方向判斷。**[正確，5 重過濾嚴謹]**
- 出場邏輯優先級：ATR trailing stop > Hurst regime shift > %B revert > BW squeeze。**[正確，trailing stop 最高優先]**
- Trailing stop: Chandelier exit，`price - ATR * mult` for long，`price + ATR * mult` for short。止損只單向移動（ratchet）。**[正確]**

**問題與發現:**

8. **[P2] squeeze 狀態未加冷卻/過期**: `was_in_squeeze` 一旦設為 true，永不過期。如果 squeeze 發生在很久以前，expansion 仍可觸發入場。這可能導致在非壓縮擴張場景中的虛假突破。**建議：加 squeeze 過期時間（如 squeeze_max_age_ms）。**

9. **[HARDCODED] 入場 confidence base=0.7, trailing_stop exit=0.7, regime_shift exit=0.6, pctb_revert exit=0.55, bw_squeeze exit=0.45**: 所有 confidence 值硬編碼。

---

### 1.4 GridTrading (`grid_trading.rs`)

**核心邏輯 / Core Logic:**
- 線性 / 幾何兩種網格構建模式。**[數學正確]**
  - 線性：`level[i] = lower + (upper-lower)/(n-1) * i`
  - 幾何：`level[i] = lower * (upper/lower)^(i/(n-1))`
- OU 模型動態間距：σ·sqrt(2/θ)，帶費用地板 `2 * FEE_PCT * mu`。**[數學正確]**
- 自適應範圍：首次 tick ±10% 初始化，之後 OU 模型調整。**[合理]**
- 庫存追蹤 + 健康檢查 + 再平衡機制。**[正確]**

**問題與發現:**

10. **[P1] OU 回歸估計可能為正**: `b = num/den` 的 `theta = (-b).max(0.001)`。如果 OLS 斜率 `b > 0`（非均值回歸序列），theta 被 clamp 到 0.001，產生極大的 `ou_step = sigma * sqrt(2000)`。這可能導致網格間距過寬，完全失去交易能力。**建議：當 b > 0 時返回 None（序列不適合 OU 模型），回退到 ±10% adaptive。**

11. **[HARDCODED] `DEFAULT_GRID_COUNT = 10`**: 雖在 `GridTradingParams` 中有 `grid_levels` 欄位，但 `on_tick` 和 `rebalance` 中使用的是 `DEFAULT_GRID_COUNT` 常量，**TOML 配置的 grid_levels 被存儲但從未應用**。這是 dead param（違反根原則：可調參數禁止假功能）。

12. **[HARDCODED] `FEE_PCT = 0.00055`**: 單邊 taker fee 硬編碼。IntentProcessor 中有動態 `fee_rate()` 查詢，但 GridTrading 的 OU 費用地板使用此硬編碼值。**建議：從 IntentProcessor 或策略參數傳入。**

13. **[HARDCODED] `ADAPTIVE_RANGE_PCT = 0.10` (±10%)**: 自適應範圍固定。

14. **[HARDCODED] `REJECT_BACKOFF_MS = 30_000` (30s)**: 拒絕退避時間固定。

15. **[P2] OU 更新頻率硬編碼 `hist_len % 50 == 0`**: 每 50 個 tick 更新一次 OU 間距，不可配置。

---

### 1.5 FundingArb (`funding_arb.rs`)

**狀態**: 完全 stub，`on_tick()` 返回 `vec![]`。待 OC-5 REST 接線。

**已實現的邏輯審計（dead code）:**
- `compute_edge`: `funding_rate.abs() - amortized_fee`，其中 `amortized_fee = TOTAL_COST_BPS / 10_000 / expected_periods`。**[數學正確]**
- `should_exit`: 4 退出條件（費率翻轉 / 費率太小 / 基差風險 / 最大持倉時間）。**[邏輯正確]**

**問題與發現:**

16. **[HARDCODED] `TOTAL_COST_BPS = 34`, `FUNDING_THRESHOLD = 0.0005`, `MAX_BASIS_PCT = 0.5`, `MAX_HOLD_MS = 72h`**: 全部硬編碼。作為 stub 可接受，上線前必須參數化。

17. **[P2] FundingArb 不是 multi-symbol**: 使用 `position: Option<FundingPosition>` 而非 `HashMap<String, FundingPosition>`。上線前需改為 per-symbol tracking（與其他 4 策略對齊）。

---

## 二、風控邏輯審計 / Risk Control Logic Audit

### 2.1 Guardian 4-Check (`guardian.rs`)

**4 項檢查 / 4 Checks:**
1. Direction conflict（同 symbol 反向持倉）→ risk_score +0.4 → Reject
2. Same-direction position count ≥ `max_same_direction_positions`（默認 3）→ risk_score +0.3 → Reject
3. Leverage cap → >2x 上限 Reject，>1x 但 <2x → Modified（qty×0.5, leverage→2x）
4. Drawdown breach → risk_score +0.35 → Reject

**裁決邏輯**: `risk_score >= 0.3 && 存在 reject-class reason` → Rejected；有修改 → Modified；其餘 → Approved。

**問題與發現:**

18. **[正確] fail-closed 設計**: 所有檢查項累積風險分數，任何嚴重問題直接拒絕。
19. **[正確] Guardian 僅用於 Open 路徑**: `StrategyAction::Close` 繞過 Guardian，因為平倉降低風險。
20. **[RISK-GAP] 修改邏輯不影響 direction_conflict 和 position_count**: 這些始終 Reject。但 leverage_over_cap 的修改（qty×0.5）可能在 Guardian 後被 Kelly/P1 進一步裁剪，邏輯正確。

### 2.2 IntentProcessor 治理管線 (`router.rs`)

**Gate 順序 / Gate Order:**
1. Governance authorization（是否授權）
1.5. Duplicate position check（同方向已有倉位）
2. Guardian 4-check
2.5. Kelly position sizing
2.6. P1 hard cap（2% of balance）
2.7. Order admission risk check（日損/槓桿/持倉/曝險/相關曝險）
   - BLOCKER-3 D15: Global notional cap check
3. Cost gate（confidence + ATR + JS edge estimate）
4. Execute fill（paper）/ Return approved qty（exchange）

**問題與發現:**

21. **[正確] P1 cap 在 Kelly 之後**: `final_qty = kelly_qty.min(p1_max_qty)`，P1 是不可突破的硬上限。
22. **[正確] PNL-1 qty=0 guard**: 防止幽靈倉位。
23. **[正確] SEC-11 ATR=0 fail-closed**: ATR 不可用時拒絕，防止在沒有波動率數據時開倉。

24. **[P1] `correlated_exposure_pct` 永遠傳入 0.0**: 代碼註釋 "Phase C wiring"，但 `check_order_allowed` 的 `correlated_exposure_pct` 始終為 0.0。RiskConfig 的 `correlated_exposure_max_pct`（默認 50%）永遠不會觸發。**這是組合級風險意識的缺口（根原則 #16）。**

25. **[P2] `leverage` 永遠傳入 1.0**: paper/exchange 模式均固定 1.0。Exchange 模式應讀取 Bybit 實際槓桿。

### 2.3 Order Admission Risk Check (`risk_checks.rs`)

**check_order_allowed 5 項檢查:**
1. Daily loss ≥ `daily_loss_max_pct` → reject
2. Leverage > `leverage_max` → reject
3. Single position ≥ `position_size_max_pct` → reject
4. Total exposure ≥ `total_exposure_max_pct` → reject
5. Correlated exposure ≥ `correlated_exposure_max_pct` → reject

**reducing orders 永遠通過**（原則 #5）。**[正確]**

### 2.4 Tick-Level Position Risk Check (`risk_checks.rs`)

**check_position_on_tick 9 層優先級:**
1. Hard stop: `pnl_pct <= -stop_loss_max_pct` → Close
2. Dynamic stop: `compute_dynamic_stop_pct(base, atr, regime, ...)` → Close
3. Take profit（if enforced）: `pnl >= tp_target * regime_mult` → Close
4. Trailing stop: peak-based，需 `min_locked_profit`（R:R floor）→ Close
5. Time stop: `holding_hours >= max * regime_mult` → Close
6. Cost edge ratio: `cost_ratio >= 0.8 && pnl > 0` → Close（suggest）
7. Session drawdown: → Halt
8. Consecutive losses: → Cooldown
9. Daily loss: → Halt

**問題與發現:**

26. **[正確] 優先級正確**: Hard stop > Dynamic stop > TP > Trailing > Time > Cost Edge > Session DD > Consec > Daily。嚴重問題優先處理。
27. **[正確] Trailing stop 有 R:R floor**: `pnl >= min_locked_profit` 才觸發，防止在接近成本時被 trailing 平倉。
28. **[正確] Cost edge ratio 只在盈利時觸發**: `pnl > 0.0` 條件，避免在虧損時因成本比高而強制平倉。

### 2.5 Cost Gate (`gates.rs`)

**三層模式 / Three Profiles:**
- **Paper (Exploration)**: 正 JS 估計 → 檢查門檻；負 JS 估計 → exploration 放行；冷啟動 → exploration 放行
- **Demo (Validation)**: 正 → 檢查門檻；負 → **阻擋**；冷啟動 → 放行（警告）
- **Live (Production)**: 正 → 檢查門檻；負 → **fail-closed**；冷啟動 → **fail-closed**

**門檻公式**: `threshold_bps = fee_bps / max(0.3, win_rate) * 1.3`（30% 安全邊際）
**fee_bps** = `2 * (fee_rate + slippage) * 10_000`（來回成本）

**問題與發現:**

29. **[正確] Live fail-closed**: 無正 JS 估計時拒絕，符合原則 #5（生存 > 利潤）。
30. **[正確] Paper exploration mode**: 允許累積數據以建立估計，避免死循環。
31. **[MATH] 門檻公式合理性**: `fee/wr * 1.3` — 勝率越低門檻越高，要求更大 edge。win_rate clamp 到 [0.3, 1.0]，防止除以接近 0 的值。**[正確]**

### 2.6 Reconciler Escalation/De-escalation

**已在 Phase 6 審計完成 (6-RC-1~10)，此處不重複。確認 27 tests pass。**

---

## 三、數學正確性審計 / Mathematical Correctness Audit

### 3.1 指標計算 / Indicator Computations

| 指標 | 公式 | Kahan 補償 | 驗證結果 |
|------|------|-----------|---------|
| SMA | `sum(window) / period` | **是** | **[正確]** |
| EMA | `price * k + prev * (1-k)`, k = 2/(period+1), seed = SMA(first period) | **是 (seed)** | **[正確]** |
| RSI (Wilder) | `100 - 100/(1+RS)`, RS = avg_gain/avg_loss, Wilder smoothing | **是 (initial)** | **[正確]** |
| Bollinger | mean ± std_mult * stddev(population), %B = (last-lower)/(upper-lower) | **是** | **[正確]** — 使用 population stddev（/N 而非 /N-1），與 TradingView 20-period 一致 |
| ATR (Wilder) | TR series → Kahan initial → Wilder smooth | **是** | **[正確]** |
| MACD | fast_ema - slow_ema, signal = EMA(macd_line, signal_period) | **是** | **[正確]** |
| KAMA | ER = |direction|/volatility, SC = ER*(fast_alpha-slow_alpha)+slow_alpha, kama += SC^2 * (price - kama) | **是** | **[正確]** |
| ADX (Wilder) | +DM/-DM → Wilder smooth → +DI/-DI → DX → Wilder smooth ADX | **是** | **[正確]** |
| Hurst (R/S) | Log-log OLS regression of R/S vs lag, clamp [0, 1] | **是** | **[正確]** |
| EWMA Vol | variance = lambda*prev + (1-lambda)*r^2, ewma = sqrt(variance) | 否（遞推） | **[正確]** — 遞推結構不需要 Kahan |
| Stochastic | %K = (close-lowest)/(highest-lowest)*100, %D = SMA(%K) | **是 (%D)** | **[正確]** |
| Donchian | max(high[window]), min(low[window]) | 否（min/max） | **[正確]** |
| Volume Ratio | current_vol / sma(volume, period) | **是** | **[正確]** |

**[MATH] Bollinger population vs sample stddev**: 使用 population stddev（除以 N 而非 N-1）。技術分析慣例上 Bollinger Bands 使用 population stddev，與 TradingView 一致。**合規。**

### 3.2 Kelly Criterion (`kelly_sizer.rs`)

**公式**: `f* = W - (1-W)/R`，其中 W = win_rate, R = avg_win/avg_loss。**[標準 Kelly 公式，正確]**

**分數 Kelly**:
- < 50 trades: 1/8 Kelly
- < 200 trades: 1/6 Kelly
- >= 200 trades: 1/4 Kelly
- cap at `max_fraction` (default 0.25)

**ATR 波動率調整**: `vol_multiplier = reference_atr_pct / atr_pct`, clamp [0.5, 1.5]。高波動縮量，低波動擴量。**[正確]**

**問題與發現:**

32. **[MATH] 正確**: Kelly 公式無誤。分數 Kelly 極度保守（最大 1/4），防止 overbetting。
33. **[P2] 負 Kelly 仍開倉 1%**: `kelly_full <= 0` 時仍以 `balance * 0.01 / price` 開倉。在 Phase 5 暫停（所有策略 gross 負 edge）的背景下，這導致每次 Kelly 判斷邊際為負時仍開 1% 倉位。**建議：Phase 5 重啟時，負 Kelly 應返回 0 或極小值（如 0.1%）。**

### 3.3 OU 最佳網格間距 (`grid_trading.rs`)

**公式**: `ou_step = sigma * sqrt(2/theta)`，其中：
- theta 由 OLS 回歸 dx_t = a + b*x_{t-1} 的斜率 b 取 `-b`
- sigma = RMS(changes)
- 費用地板 = `2 * FEE_PCT * mu`

**[MATH] 公式正確**（源自 OU 首次穿越時間理論）。但見 #10：當 b > 0 時（非均值回歸序列），theta 被 clamp 到 0.001，產生巨大間距。

### 3.4 PnL 計算

**PNL-FIX-1/2 已修復（2026-04-12）**：
- FIX-1: 5 條 close 路徑從 `event.last_price` 改為 per-symbol 正確價格
- FIX-2: `emit_close_fill` 寫入真實費用而非 0.0

**[正確] 當前 PnL 計算使用 `execute_market_fill_with_rate()` 包含真實費率和滑點。**

### 3.5 Position Sizing

**P1 cap 公式**: `p1_max_qty = balance * p1_risk_pct / price`。默認 `p1_risk_pct = 0.02`（2%）。**[正確]**

**Exposure 計算**: `exposure_pct = sum(position_qty * price) / balance * 100`。**[正確]**

### 3.6 Slippage Tiers

| 24h 成交額 | 滑點 |
|-----------|------|
| >$1B | 1 bps |
| >$100M | 2 bps |
| >$10M | 5 bps |
| >$1M | 15 bps |
| <$1M | 30 bps |

**[合理]** — 分層符合加密貨幣流動性梯度。BTC/ETH 在 1B+ 層，altcoin 在低層。

### 3.7 James-Stein Estimator (`edge_estimates.rs`)

此文件僅是緩存/查詢層，真正的 JS 估計在 Python `james_stein_estimator.py` 中計算。Rust 側正確加載 `shrunk_bps`, `win_rate`, `n_trades`, `std_bps` 並提供 O(1) 查詢。**[正確]**

---

## 四、硬編碼值彙總 / Hardcoded Values Summary

| # | 位置 | 值 | 嚴重性 | 建議 |
|---|------|-----|--------|------|
| H1 | `ma_crossover.rs` L233-242 | confidence base=0.45, regime_bonus=0.15 | P3 | 加入 params |
| H2 | `bb_reversion.rs` L246 | RSI thresholds 30/70 | **P2** | 加入 BbReversionParams |
| H3 | `bb_reversion.rs` L273 | Exit %B range [0.2, 0.8] | P3 | 可配置化 |
| H4 | `bb_breakout.rs` L300 | Entry confidence base=0.7 | P3 | 加入 params |
| H5 | `grid_trading.rs` L114 | DEFAULT_GRID_COUNT=10 | **P1** | 連接 TOML grid_levels |
| H6 | `grid_trading.rs` L127 | FEE_PCT=0.00055 | **P2** | 使用動態費率 |
| H7 | `grid_trading.rs` L130 | ADAPTIVE_RANGE_PCT=0.10 | P3 | 可配置化 |
| H8 | `grid_trading.rs` L126 | REJECT_BACKOFF_MS=30_000 | P3 | 可配置化 |
| H9 | `grid_trading.rs` L671 | OU update frequency (% 50) | P3 | 可配置化 |
| H10 | `funding_arb.rs` L16-24 | All 5 constants | P3 (stub) | 上線前參數化 |
| H11 | `intent_processor/mod.rs` L81 | DEFAULT_P1_RISK_PCT=0.02 | P3 | 已通過 config 可覆蓋 |
| H12 | `volatility.rs` L233-236 | HURST_TRENDING/MEAN_REVERTING thresholds 0.60/0.40 | P3 | 可配置化 |

---

## 五、風控 Gap 彙總 / Risk Gaps Summary

| # | 類型 | 描述 | 嚴重性 |
|---|------|------|--------|
| RG-1 | [RISK-GAP] | `correlated_exposure_pct` 永遠 0.0，相關曝險檢查實質失效 | **P1** |
| RG-2 | [RISK-GAP] | Exchange 模式 leverage 永遠 1.0，未讀取 Bybit 實際槓桿 | P2 |
| RG-3 | [RISK-GAP] | GridTrading `grid_levels` TOML 配置存儲但不應用（dead param） | **P1** |
| RG-4 | [RISK-GAP] | GridTrading OU theta clamp 0.001 在非 OU 序列上產生巨大間距 | **P1** |
| RG-5 | [RISK-GAP] | GridTrading FEE_PCT 硬編碼 vs IntentProcessor 動態費率不一致 | P2 |
| RG-6 | [RISK-GAP] | BbBreakout squeeze 狀態永不過期 | P2 |
| RG-7 | [RISK-GAP] | Kelly 負邊際仍開 1% 倉（Phase 5 pause 期間的額外風險） | P2 |

---

## 六、正面發現 / Positive Findings

1. **Kahan 補償求和全面覆蓋**: 所有指標累加運算使用 Kahan，消除浮點漂移。
2. **RC-04 rejection rollback 一致實現**: 5 策略全部實現 per-symbol 狀態快照+回滾。
3. **StrategyAction::Close 繞過治理**: 平倉不需 Guardian/cost_gate/Kelly/P1，正確反映降風險本質。
4. **P1 hard cap 不可繞過**: `kelly_qty.min(p1_max_qty)` 確保 Kelly 不能超過風控上限。
5. **cost_gate 三級分層**: Paper/Demo/Live 逐級嚴格，符合漸進放權設計。
6. **ATR=0 fail-closed (SEC-11)**: 指標故障時自動阻止開倉。
7. **PNL-1 qty=0 guard**: 防止幽靈倉位。
8. **reducing orders 永遠通過**: 符合原則 #5（生存 > 利潤），不阻擋平倉/減倉。
9. **Trailing stop R:R floor**: 防止在接近成本時被追蹤止損意外平倉。
10. **Per-engine TOML 策略配置**: 三引擎可獨立配置策略參數。

---

## 七、建議行動項 / Recommended Actions

### P0（無）

### P1（3 項）
1. **RG-1**: 接線 `correlated_exposure_pct`（Phase C），或暫時用相同 sector 持倉比例估算
2. **RG-3**: 將 `GridTradingParams.grid_levels` 接線到 `build_levels()`，替換 `DEFAULT_GRID_COUNT`
3. **RG-4**: 當 OU 回歸斜率 b > 0 時 `compute_ou_step()` 返回 None

### P2（7 項）
4. H2: RSI 閾值加入 BbReversionParams
5. H6: GridTrading FEE_PCT 改為動態讀取或從 config 注入
6. RG-2: Exchange 模式從 Bybit API 讀取實際槓桿
7. RG-6: 加 squeeze 過期時間配置
8. RG-7: 負 Kelly 時返回更小值（0.1% 而非 1%）
9. FundingArb multi-symbol 改造
10. KAMA fallback 加 trace log

---

**審計員 / Auditor**: QC (Quality Controller)
**審計級別 / Level**: L2 全模組審計
**測試基線 / Test Baseline**: 939 engine lib + 366 core + 18 e2e + 32 promotion = 1355 Rust / 2852 Python


---

# 10. MIT — 數據庫 + ML 基座審計

> 原始文件：`docs/CCAgentWorkSpace/E1/2026-04-12--ml_db_audit_report.md`

# ML/DB 基礎設施審計報告
# ML/DB Infrastructure Audit Report
# 日期 / Date: 2026-04-12
# 審計員 / Auditor: MIT (ML Infrastructure / Database Engineer)

---

## 一、總結 / Executive Summary

資料庫 schema 設計為 **A 級** — 8 schema、35+ 表、完整索引、TimescaleDB 壓縮/保留策略、sync_commit 分層均已到位。ML 管線代碼基座 **完備但未端到端運行** — LightGBM/Optuna/CPCV/LinUCB/Thompson Sampling/Claude Teacher 全部有實現，但缺乏實際訓練數據積累和真實模型。**最大阻塞**：V001-V015 DDL 遷移文件標記為 "DRAFT — 尚未執行"（V006 除外，已執行），ML 管線的持久化路徑依賴這些表。2026-04-10 修復 session 已完成接線工作（FeatureCollector、Connection Pool、Parquet ETL），但 DDL 執行狀態仍不確定。

Database schema design is **A-tier** — 8 schemas, 35+ tables, complete indexing, TimescaleDB compression/retention, sync_commit tiering all in place. ML pipeline code base is **complete but not end-to-end operational** — LightGBM/Optuna/CPCV/LinUCB/Thompson Sampling/Claude Teacher all implemented, but lack actual training data accumulation and real models. **Biggest blocker**: V001-V015 DDL migration files marked "DRAFT — not yet executed" (except V006), and ML pipeline persistence paths depend on these tables. The 2026-04-10 remediation session completed wiring work but DDL execution status remains uncertain.

---

## 二、資料庫審計 / Database Audit

### 2.1 Schema 結構總覽 / Schema Structure Overview

```
PostgreSQL Database: trading_ai
├── market (11 tables)     — 市場數據：tickers/klines/OB/funding/OI/LSR/liquidations/regime/news
├── trading (9 tables)     — 交易：context/outcomes/signals/intents/verdicts/orders/state_changes/fills/positions
├── agent (3 tables)       — Agent：messages/ai_invocations/state_changes
├── learning (15+ tables)  — 學習：RL/promotion/suggestions/registry/posteriors/CPCV/JS/clusters/
│                            teacher/executions/experiment_ledger/linucb_state/budget/usage/
│                            foundation_model/weekly_review
├── features (2 tables)    — 特徵：online_latest/versions
├── observability (6 tables) — 監控：scorer_predictions/model_performance/drift/baselines/DQ/engine_events
├── risk (3 tables)        — 風險：black_swan_events/votes/correlation_pairs
├── news (reserved)        — 預留
└── public (legacy 11 + views 11) — Grafana 橋接 VIEW + _legacy 表
```

**遷移文件**：V001-V015 共 15 個 SQL 遷移，覆蓋完整。

### 2.2 索引評估 / Index Assessment — Grade: A

**V005 定義了完整索引策略**：

| 類別 / Category | 索引數量 / Count | 設計質量 / Quality |
|-----------------|------------------|--------------------|
| PK (含 TimescaleDB 時間列) | 35+ | **優秀** — 所有 hypertable PK 含 ts 列 |
| `(symbol, ts DESC)` 時間範圍查詢 | 12 | **優秀** — 覆蓋所有高頻查詢 |
| `ts DESC` 單列快速最新查詢 | 10 | **良好** — 高頻表精簡，減少寫入放大 |
| GIN (JSONB) | 2 | **合理** — 只在 decision_context_snapshots |
| Partial indexes | 3 | **優秀** — `WHERE is_active=TRUE`、`WHERE linucb_arm_id IS NOT NULL`、`WHERE outcome_computed_at IS NULL` |
| Composite indexes | 5+ | **良好** — strategy+symbol、decision_type+ts 等 |
| V015 engine_mode 索引 | 8 | **優秀** — 三引擎模式隔離 |

**發現的問題**：
- **無 N+1 風險**：Rust 端全部批量寫入（`QueryBuilder::push_values()`），Python 端走連接池
- **無缺失索引**：常用查詢模式（symbol+ts、strategy+ts、engine_mode+ts）均已覆蓋
- **潛在冗餘**：`idx_market_tickers_ts_desc` 與 PK `(symbol, ts)` 部分重疊，但 TimescaleDB 場景下 ts DESC 單列索引仍有價值（跨 symbol 最新查詢）

### 2.3 外鍵與約束 / Foreign Keys & Constraints — Grade: B+

**設計決策**：TimescaleDB hypertable **不支持外鍵**，因此採用「邏輯 FK + 應用層 CHECK」模式。

| 約束類型 / Type | 數量 / Count | 評價 / Assessment |
|-----------------|-------------|-------------------|
| CHECK constraints | 3 | `news_signals.severity BETWEEN 0 AND 1`、`sentiment`、`confidence` |
| 真實 FK | 2 | `directive_executions → teacher_directives`、`linucb_migrations.rollback_to` |
| 邏輯 FK (文檔化) | 15+ | `context_id` 跨表關聯、`intent_id`、`order_id` 等 |
| UNIQUE constraints | 2 | `model_registry(model_name, version)`、`feature_baselines(symbol, feature_name, valid_from)` |

**風險點**：
- 邏輯 FK 無資料庫級強制，依賴應用層正確性。但考慮 TimescaleDB 限制，這是正確的設計決策
- `trading.decision_outcomes.context_id` 與 `decision_context_snapshots.context_id` 無 FK — 合理（hypertable）

### 2.4 資料保留策略 / Data Retention — Grade: A

**V006 定義了完整的壓縮+保留策略**（已執行）：

| 資料類別 / Category | 壓縮間隔 / Compress | 保留期限 / Retain | 設計合理性 |
|--------------------|---------------------|-------------------|-----------|
| 高頻市場（tickers/OB/trades） | 7d | 90d | **合理** — 50MB/day |
| K 線 | 14d | 365d | **合理** — 回測需要 |
| Funding/OI/LSR | N/A | 180d | **合理** |
| 信號/意圖 | 2d (signals), 14d (intents) | 180d | **合理** — DB-RUN-7 特殊處理 signals |
| 成交/訂單 | 14d | 365d | **合理** — 審計+學習需要 |
| 監控 | N/A | 90d | **合理** — 可再生 |

**DB-RUN-7 特別修復**：`trading.signals` chunk 從 7 天縮到 1 天 + 2 天壓縮，配合寫入節流解決 19GB 未壓縮問題。

### 2.5 synchronous_commit 驗證 / sync_commit Verification — Grade: A

```sql
-- Database default (V006:90)
ALTER DATABASE trading_ai SET synchronous_commit = 'on';

-- Table-level tiering via COMMENT hint:
-- sync_commit=on:  trading.fills, trading.orders (CRITICAL — 不可丟失)
-- sync_commit=off: market.market_tickers, ob_snapshots, trade_agg_1m, trading.signals (高頻可再生)
```

**評價**：分層正確。關鍵交易數據（fills/orders）強一致，高頻市場數據允許丟失。應用層需讀取 COMMENT 並設置 session 級 sync_commit。

### 2.6 連接池配置 / Connection Pool — Grade: B+

**Rust 端（sqlx PgPool）**：
- `pool_max_connections: 20`（預設）
- `pool_min_connections: 2`（預設）
- `acquire_timeout: 5000ms`
- `DbPool` wrapper 帶失敗追蹤和優雅降級
- 無 PG 時引擎正常運行（pool = None，寫入靜默跳過）

**Python 端（psycopg2）**：
- ✅ 2026-04-10 新增 `db_pool.py`：`ThreadedConnectionPool(min=2, max=10)`
- ✅ Dashboard/API 路由已遷移到連接池
- ✅ ML 訓練腳本保持獨立 `psycopg2.connect()`（batch job，正確設計）
- ✅ `/api/v1/health/db` 健康探測端點已加

**改進建議**：
- Rust pool_max_connections=20 對三引擎場景可能偏多（3 engine × 多 writer task），建議監控 `pg_stat_activity` 確認實際使用量

---

## 三、ML 基座達標檢驗 / ML Infrastructure Readiness

### 3.1 特徵提取管線 / Feature Extraction Pipeline — Grade: A-

**已實現**：
- **34 維特徵向量**（`feature_collector.rs`）：16 指標扁平化
  ```
  sma_20, sma_50, ema_12, ema_26, rsi_14, macd, macd_signal, macd_histogram,
  bb_upper/middle/lower/bandwidth/percent_b, atr_14/14_percent, atr_5/5_percent,
  stoch_k/d, kama/kama_efficiency, adx/plus_di/minus_di, hurst, regime_id,
  ewma_vol, vol_regime_id, volume_ratio, donchian_upper/lower/middle/width, price
  ```
- **Ring buffer**：VecDeque 3000 容量（~5 分鐘 in-memory）
- **DB 持久化**：`features.online_latest` UPSERT（per symbol × timeframe）
- **漂移檢測**：PSI + ADWIN，寫入 `observability.drift_events`

**2026-04-10 修復後狀態**：
- ✅ FeatureCollector → mpsc channel → feature_writer 全鏈路已接通
- ✅ tick_pipeline `try_send(snap)` 非阻塞派發
- ⚠️ 需確認 `features.online_latest` 表已在 DB 中創建

### 3.2 訓練數據可用性 / Training Data Availability — Grade: B-

**已寫入 DB 的數據**：

| 數據類型 | 寫入器 | 狀態 |
|---------|--------|------|
| `trading.fills` | Rust `trading_writer.rs` | ✅ 運行中 |
| `trading.signals` | Rust `trading_writer.rs` | ✅ 運行中（DB-RUN-1 節流） |
| `trading.intents` | Rust `trading_writer.rs` | ✅ 運行中 |
| `trading.decision_context_snapshots` | Rust `context_writer.rs` | ✅ 運行中 |
| `market.*` (klines/tickers/etc) | Rust `market_writer.rs` | ✅ 運行中 |
| `features.online_latest` | Rust `feature_writer.rs` | ✅ 2026-04-10 接通 |
| `trading.decision_outcomes` | **無 writer** | ❌ **關鍵缺失** |
| `trading.orders` / `order_state_changes` | **無 writer** | ❌ 中等缺失 |

**最大問題**：`trading.decision_outcomes`（5 個回報窗口 1m/5m/1h/4h/24h + max favorable/adverse excursion）**無 backfill writer**。這是 `learning.scorer_training_features` VIEW 的核心 JOIN 目標 — 沒有 outcomes，ML 訓練 VIEW 的 `WHERE outcome_backfilled = TRUE` 永遠返回空集。

### 3.3 模型服務基礎設施 / Model Serving Infrastructure — Grade: B

**三級降級鏈**（`ml/scorer.rs`）：
1. **Tier 1**: ONNX 模型 → `OnnxModelManager` → `predict(features)` → calibrated_prob
2. **Tier 2**: 無 ONNX → 規則推理（signal confidence 直透）
3. **Tier 3**: 規則失敗 → 固定 confidence = 0.5

**模型部署路徑**：
```
LightGBM 訓練 → scorer_trainer.py → model.pkl
                → onnx_exporter.py → model.onnx (deferred)
                → learning.model_registry (DB row)
Rust 加載 → OnnxModelManager::load(onnx_path) → ArcSwap 熱交換
```

**當前狀態**：Tier 2/3 降級運行，無真實 ONNX 模型。ONNX 導出代碼存在但 `ort` crate 整合推遲。

### 3.4 EvolutionEngine 狀態 / EvolutionEngine Status — Grade: C+

**定位**：Python 離線工具，非 Rust 引擎組件。

**功能**：
- 網格搜索策略參數空間（`ParameterGrid`）
- 使用 `BacktestEngine` 作為評估函數
- `max_combinations` 上限 50（防資源耗盡）
- 結果可注入 `TruthSourceRegistry`

**問題**：
- ⚠️ BacktestEngine 本身是否準確（PNL-FIX-1/2 揭露所有策略 gross edge 為負）
- ⚠️ 不在 Rust 中，不參與實時推理
- ⚠️ W21 決策：保留用於 DL/AI agent 學習，與 PromotionPipeline 分工明確

### 3.5 Teacher-Student 架構 / Teacher-Student Architecture — Grade: B+

**Claude Teacher（Rust，Phase 4）**：
- ✅ `claude_teacher/` 完整模組：client / parser / writer / applier / consumer_loop / outcome_tracker / governance_impl / strategy_ipc_impl
- ✅ LLM 抽象：`LlmClient` trait（AnthropicClient + MockClient）
- ✅ BudgetTracker fail-closed 成本閘
- ✅ PG 持久化：`learning.teacher_directives` + `learning.experiment_ledger`
- ✅ Directive 成效追蹤：`outcome_tracker.rs` 多窗口 PnL + Sharpe
- ⚠️ 真實 Anthropic API 調用需 `ANTHROPIC_API_KEY`，dev 環境不觸發

**Student 側**：
- 策略通過 IPC 接收 directive 並調整參數
- `strategy_ipc_impl.rs` + `governance_impl.rs` 確保治理合規

### 3.6 LightGBM 整合 / LightGBM Integration — Grade: B

**已實現**：
- `scorer_trainer.py`：完整 LightGBM regression 訓練器
  - 預測目標：ATR 歸一化 PnL
  - 支持 CPCV 驗證路徑 + legacy 80/20 split
  - Feature importance 輸出
- `cpcv_validator.py`：4-fold CPCV + per-strategy embargo（24h/4h/8h/72h）
- `calibration.py`：Platt/isotonic 校準（placeholder）
- `onnx_exporter.py`：LightGBM → ONNX 導出

**未實現**：
- ❌ 無真實訓練數據跑過完整管線
- ❌ ONNX 導出整合推遲
- ❌ 校準尚為 placeholder

### 3.7 Optuna 超參數調優 / Optuna HPO — Grade: B

**已實現**：
- `optuna_optimizer.py`：TPE 策略參數優化
  - JournalFileStorage（非 PG，E5-O4 審計決策）
  - 結果寫入 `learning.ml_parameter_suggestions`
  - 獨立 psycopg2 連接（batch job）
- 兩層優化：Layer 1 = Optuna TPE，Layer 2 = Thompson Sampling

**未實現**：
- ❌ 無自動調度（需手動觸發或 cron）
- ❌ Optuna → IPC → Rust hot-reload 路徑未完成

---

## 四、ML 部署階段評估 / ML Deployment Stage Assessment

| 階段 / Stage | 狀態 | 詳細 / Detail |
|-------------|------|---------------|
| **數據收集 / Data Collection** | ✅ | Rust engine 實時寫入 fills/signals/intents/context/market data。market_writer 7 類型批量刷新 |
| **特徵工程 / Feature Engineering** | ✅ | 34-dim feature vector（16 指標），FeatureCollector → DB UPSERT。PSI/ADWIN 漂移檢測 |
| **模型訓練管線 / Model Training Pipeline** | ⚠️ 部分 | LightGBM scorer + CPCV 驗證代碼完備。**阻塞**：decision_outcomes 無 backfill → scorer_training_features VIEW 空 |
| **模型評估 / Model Evaluation** | ⚠️ 部分 | CPCV 框架 + power estimation 已實現。Brier score / calibration error 表已建但無數據 |
| **線上服務 / Online Serving** | ⚠️ 部分 | 3-tier Scorer（ONNX→rule→fixed）框架就緒。OnnxModelManager ArcSwap 熱交換設計好。無真實 ONNX 模型 |
| **A/B 測試 / A/B Testing** | ⚠️ 部分 | DL-3 Foundation Model A/B runner（`dl3_ab_runner.py`）+ Go-No-Go 決策框架。LinUCB shadow compare 工具 |
| **持續學習 / Continuous Learning** | ❌ | Thompson Sampling posteriors 更新代碼有但未自動化。Outcome backfill 不存在。EvolutionEngine 是離線工具非自動化循環 |

### 階段總評 / Overall ML Stage Rating

```
╔══════════════════════════════════════════════════════════════╗
║  ML Maturity Level:  STAGE 2 of 7 — Feature Engineering    ║
║  ────────────────────────────────────────────────────────── ║
║  ✅ Stage 1: Data Collection        — OPERATIONAL          ║
║  ✅ Stage 2: Feature Engineering     — OPERATIONAL          ║
║  ⚠️ Stage 3: Model Training Pipeline — CODE COMPLETE,       ║
║                                        DATA BLOCKED         ║
║  ⚠️ Stage 4: Model Evaluation        — FRAMEWORK ONLY      ║
║  ⚠️ Stage 5: Online Serving          — DEGRADED (Tier 2/3) ║
║  ⚠️ Stage 6: A/B Testing            — TOOLING EXISTS       ║
║  ❌ Stage 7: Continuous Learning     — NOT OPERATIONAL      ║
╚══════════════════════════════════════════════════════════════╝
```

---

## 五、數據完整性 / Data Pipeline Integrity

### 5.1 市場數據 → DB 寫入路徑

```
Bybit WS (public)
  └→ tick_pipeline.rs (on_tick)
       ├→ KlineManager (bar close) ─→ MarketDataMsg::KlineClose ─→ mpsc ─→ market_writer ─→ market.klines
       ├→ 5s timer ─→ MarketDataMsg::TickerSnapshot ─→ mpsc ─→ market_writer ─→ market.market_tickers
       ├→ 1m timer ─→ MarketDataMsg::ObSnapshot ─→ mpsc ─→ market_writer ─→ market.ob_snapshots
       ├→ 1m timer ─→ MarketDataMsg::TradeAgg1m ─→ mpsc ─→ market_writer ─→ market.trade_agg_1m
       └→ regime change ─→ RegimeSnapshot/Transition ─→ mpsc ─→ market_writer ─→ market.regime_*

Bybit REST (poller, 5-15m)
  └→ rest_poller.rs
       ├→ FundingRate ─→ market.funding_rates
       ├→ OpenInterest ─→ market.open_interest
       └→ LongShortRatio ─→ market.long_short_ratio
```

**狀態**：✅ 全部接通，批量刷新（`batch_flush_interval_ms: 2000ms`），JSONL fallback on PG failure。

### 5.2 Fill/Order → DB 寫入路徑

```
IntentProcessor (signal → intent → risk → execute)
  └→ TradingMsg::Fill ─→ mpsc ─→ trading_writer ─→ trading.fills
  └→ TradingMsg::Signal ─→ mpsc ─→ trading_writer ─→ trading.signals
  └→ TradingMsg::Intent ─→ mpsc ─→ trading_writer ─→ trading.intents
  └→ TradingMsg::RiskVerdict ─→ mpsc ─→ trading_writer ─→ trading.risk_verdicts
  └→ TradingMsg::PositionSnapshot ─→ mpsc ─→ trading_writer ─→ trading.position_snapshots

  ❌ TradingMsg::Order → trading.orders       (writer code exists, OMS state machine gap)
  ❌ TradingMsg::OrderStateChange → trading.order_state_changes (same)
```

**關鍵問題**：
- `trading.orders` 和 `order_state_changes` 有 writer code 但 OMS 生命週期管理未完成
- `engine_mode` 欄位（V015）已加入所有寫入消息，三引擎數據正確隔離

### 5.3 特徵計算 → 存儲

```
tick_pipeline → IndicatorEngine → IndicatorSnapshot
  └→ FeatureCollector.capture(snapshot) → FeatureSnapshot
       └→ mpsc::try_send() → feature_writer → features.online_latest (UPSERT)

  └→ DecisionContextMsg.indicators_snapshot (JSONB)
       └→ context_writer → trading.decision_context_snapshots

  ❌ decision_outcomes backfill — 完全缺失
  ❌ features.history — 刻意不建（DB-RUN-4 決策：歷史走 context JSONB）
```

### 5.4 快照持久化 / Snapshot Persistence

```
Rust 引擎狀態快照：
  paper_state.json / pipeline_snapshot_{paper,demo,live}.json
  └→ 本地 JSON 文件（per-engine 隔離，commit c9d9bc5 修復）

ConfigStore 補丁審計：
  └→ observability.engine_events (IPC handler 寫入)

Reconciler 狀態：
  └→ observability.engine_events (reconciler 審計行)
  └→ Arc<AtomicU8> shared risk level (in-memory)
```

---

## 六、關鍵問題與建議 / Critical Issues & Recommendations

### P0 — 阻塞 ML 訓練的關鍵問題

| # | 問題 | 影響 | 建議修復 |
|---|------|------|----------|
| **DB-1** | V001-V004 DDL 標記 "DRAFT — 尚未執行" | ML 持久化全部阻塞 | **確認並執行所有 DDL**（V006 以外的遷移） |
| **ML-1** | `trading.decision_outcomes` 無 backfill writer | `scorer_training_features` VIEW 永遠空集 | 實現 outcome backfill job（定時掃描 fills，計算 1m/5m/1h/4h/24h 回報窗口） |
| **ML-2** | 所有策略 gross edge 為負（PNL-FIX-1/2） | 即使 ML 管線通暢，訓練出的模型也學到負 edge 信號 | **Phase 5 PAUSED 正確** — 先修策略再跑 ML |

### P1 — 重要但不阻塞

| # | 問題 | 影響 | 建議修復 |
|---|------|------|----------|
| **DB-2** | `trading.orders` / `order_state_changes` 無 writer | 訂單生命週期不可重建 | 接通 Rust OMS → trading_writer |
| **ML-3** | ONNX 導出/加載推遲 | Scorer 降級運行（Tier 2/3） | 待有正 edge 策略後實現 |
| **ML-4** | Calibration 為 placeholder | 模型概率無校準 | 待模型訓練完成後實現 |
| **DB-3** | Python ML scripts 用獨立 `psycopg2.connect()` | Batch job 正確但無超時重試 | 可接受，加超時即可 |

### P2 — 改進建議

| # | 問題 | 建議 |
|---|------|------|
| **DB-4** | `pool_max_connections=20` 三引擎場景偏多 | 監控 `pg_stat_activity` 後調整 |
| **ML-5** | Thompson Sampling posteriors 更新未自動化 | 待策略有正 edge 後實現定時更新 |
| **ML-6** | LinUCB warm-start migration (4-06) 未實現 | 待 v1_15 arm 積累足夠數據 |
| **DB-5** | Grafana VIEW 橋接部分指向 `_legacy` 表 | Phase 0b 遷移完成後改指新表 |

---

## 七、ML 管線代碼清單 / ML Pipeline Code Inventory

### Python ML 模組（`program_code/ml_training/`）

| 文件 | 功能 | 行數(估) | 狀態 |
|------|------|----------|------|
| `scorer_trainer.py` | LightGBM CPCV 訓練 | ~250 | ✅ 可運行 |
| `cpcv_validator.py` | 4-fold CPCV + embargo | ~360 | ✅ 可運行 |
| `optuna_optimizer.py` | TPE 超參數優化 | ~600 | ✅ 可運行 |
| `thompson_sampling.py` | NIG Thompson Sampling | ~480 | ✅ 可運行 |
| `james_stein_estimator.py` | JS 跨幣 partial pooling | ~200 | ✅ 可運行 |
| `linucb_trainer.py` | LinUCB batch 重建 A/b | ~300 | ✅ 可運行 |
| `linucb_arm_migration.py` | Warm-start 遷移 | ~200 | ⚠️ Framework |
| `linucb_shadow_compare.py` | Shadow comparison | ~200 | ✅ 可運行 |
| `parquet_etl.py` | DuckDB PG→Parquet ETL | ~150 | ✅ 可運行 |
| `label_generator.py` | ATR-normalized PnL labels | ~150 | ✅ 可運行 |
| `calibration.py` | Platt/isotonic 校準 | ~100 | ⚠️ Placeholder |
| `onnx_exporter.py` | LightGBM → ONNX | ~100 | ⚠️ Deferred |
| `leakage_check.py` | Outcome leakage 防護 | ~100 | ✅ 可運行 |
| `dl3_foundation.py` | TimesFM/Chronos 推理 | ~280 | ✅ 可運行 |
| `dl3_ab_runner.py` | DL-3 A/B 比較 | ~450 | ✅ 可運行 |
| `dl3_go_no_go.py` | DL-3 Go/No-Go 決策 | ~200 | ✅ 可運行 |
| `run_training_pipeline.py` | 端到端編排 | ~170 | ✅ 可運行 |
| `weekly_report_generator.py` | 週度報告 | ~200 | ✅ 可運行 |
| `realized_edge_stats.py` | 邊際分析 | ~150 | ✅ 可運行 |
| `edge_cluster_analysis.py` | 聚類分析 | ~200 | ✅ 可運行 |

### Rust ML 模組

| 路徑 | 功能 | 狀態 |
|------|------|------|
| `ml/scorer.rs` | 3-tier Scorer | ✅ 運行中（Tier 2/3） |
| `ml/model_manager.rs` | ONNX ArcSwap 管理 | ✅ Framework ready |
| `ml/kelly_sizer.rs` | Kelly 倉位 | ✅ 運行中 |
| `linucb/` (5 files) | LinUCB 推理 + state IO | ✅ 運行中 |
| `claude_teacher/` (8 files) | Teacher pipeline | ✅ 運行中（Mock mode） |
| `ai_budget/` | 成本追蹤 + 預算 | ✅ 運行中 |
| `feature_collector.rs` | 34-dim 特徵 | ✅ 接通 |
| `database/drift_detector.rs` | PSI + ADWIN | ✅ 運行中 |
| `database/feature_writer.rs` | UPSERT online_latest | ✅ 接通 |
| `database/context_writer.rs` | Decision context | ✅ 運行中 |

---

## 八、結論 / Conclusion

### 資料庫：設計優秀，執行待確認

Schema 設計體現了深思熟慮的架構決策（TimescaleDB hypertable 分層、邏輯 FK 文檔化、壓縮/保留策略、sync_commit 分層）。索引覆蓋全面，無 N+1 風險。**唯一不確定**：V001-V004 DDL 是否已從 "DRAFT" 狀態執行到位。

### ML：代碼完備率 ~90%，可運行率 ~30%

ML 管線代碼量約 8500+ 行（Python）+ 3000+ 行（Rust），覆蓋從 ETL 到模型服務的完整鏈路。但受以下阻塞：

1. **DDL 執行不確定** → 持久化路徑可能不通
2. **decision_outcomes backfill 缺失** → 訓練 VIEW 空集
3. **所有策略 gross edge 為負** → 即使訓練也學到錯誤信號

**ML 到達 Stage 3（模型訓練）的前提**：
1. 確認 DDL 全部執行
2. 實現 decision_outcomes backfill
3. 至少一個策略達到正 gross edge

**ML 到達 Stage 5（線上服務）的前提**：
1. Stage 3 完成 + ONNX 導出可用
2. 模型通過 CPCV 驗證
3. OnnxModelManager 加載真實模型

---

*報告結束 / End of Report*


---

# 11. BB — Bybit API 兼容審計

> 原始文件：`docs/CCAgentWorkSpace/E1a/2026-04-12--bybit_api_audit_report.md`

# Bybit V5 API 集成審計報告

> **審計角色**: BB (Bybit API Specialist)
> **日期**: 2026-04-12
> **範圍**: Rust `openclaw_engine` 全部 Bybit REST/WS 端點 + Python PyO3 橋接層
> **參照**: Bybit V5 官方文檔 + `docs/references/2026-04-04--bybit_api_reference.md`

---

## 一、審計總結

| 項目 | 統計 |
|------|------|
| REST 端點總數 | 48 |
| WebSocket 連接 | 2（公開 + 私有） |
| **[PASS]** 正確 | 42 |
| **[API-MISMATCH]** 端點路徑/參數不匹配 | 3 |
| **[PARSE-ERROR]** 解析問題 | 1 |
| **[MISSING-HANDLER]** 缺失處理 | 1 |
| **[DEPRECATED]** 使用已棄用端點 | 0 |
| **[NAMING]** 函數命名與功能不匹配 | 1 |
| **[RISK]** 業務邏輯風險 | 1 |

**整體評級**: **B+** — 核心交易路徑（下單/查倉/查餘額/WS 訂閱）全部正確，HMAC 簽名嚴謹，B-2 修復徹底。少數邊緣端點存在問題，但均非交易關鍵路徑。

---

## 二、REST API 端點逐項審計

### 2.1 核心交易端點 — `order_manager.rs`

| 方法 | Bybit 路徑 | HTTP | 結果 | 備註 |
|------|-----------|------|------|------|
| `place_order()` | `/v5/order/create` | POST | **[PASS]** | category/symbol/side/orderType/qty 正確；camelCase body；price 字串化；timeInForce 默認正確（Limit→GTC）；reduceOnly/closeOnTrigger/triggerPrice/triggerDirection/TP/SL 全部正確映射 |
| `cancel_order()` | `/v5/order/cancel` | POST | **[PASS]** | category/symbol/orderId 正確 |
| `cancel_all()` | `/v5/order/cancel-all` | POST | **[PASS]** | 回應解析 `result.list` 正確 |
| `amend_order()` | `/v5/order/amend` | POST | **[PASS]** | orderId/orderLinkId 二擇一校驗正確；qty/price 取整後字串化 |
| `get_active_orders()` | `/v5/order/realtime` | GET | **[PASS]** | category 必填；symbol 可選 |
| `get_order_history()` | `/v5/order/history` | GET | **[PASS]** | limit 默認 50 |
| `get_executions()` | `/v5/execution/list` | GET | **[PASS]** | 解析 execId/execPrice/execQty/execFee/feeCurrency 完整 |

**精度處理**: `validate_and_round()` 使用 `InstrumentInfoCache`，M-1 修復後缺失 spec 時 fail-closed（不再繞過驗證）。qty 用 floor（避免超額），price 用 round。`format_qty()` / `format_price()` 正確去尾零。

### 2.2 批量訂單端點 — `batch_order_manager.rs`

| 方法 | Bybit 路徑 | HTTP | 結果 | 備註 |
|------|-----------|------|------|------|
| `create_batch()` | `/v5/order/create-batch` | POST | **[PASS]** | Bybit 限制 10 筆/批，代碼需調用方控制 |
| `amend_batch()` | `/v5/order/amend-batch` | POST | **[PASS]** | |
| `cancel_batch()` | `/v5/order/cancel-batch` | POST | **[PASS]** | |

### 2.3 持倉端點 — `position_manager.rs`

| 方法 | Bybit 路徑 | HTTP | 結果 | 備註 |
|------|-----------|------|------|------|
| `get_positions()` | `/v5/position/list` | GET | **[PASS]** | 無 symbol 時正確使用 `settleCoin=USDT`（Bybit 要求 symbol 或 settleCoin 二擇一）|
| `set_leverage()` | `/v5/position/set-leverage` | POST | **[PASS]** | 110043（已設置）視為成功，冪等處理正確 |
| `set_trading_stop()` | `/v5/position/trading-stop` | POST | **[PASS]** | TP/SL/trailingStop/activePrice/positionIdx 全部正確；字串化數值 |
| `switch_position_mode()` | `/v5/position/switch-mode` | POST | **[PASS]** | mode: 0=single, 3=hedge 正確 |
| `confirm_pending_mmr()` | `/v5/position/confirm-mmr` | POST | **[API-MISMATCH]** | Bybit V5 實際端點為 `/v5/position/confirm-pending-mmr`，多了 `pending-`。但此端點極少使用（僅 risk limit 變更後），影響低 |
| `set_auto_add_margin()` | `/v5/position/set-auto-add-margin` | POST | **[PASS]** | autoAddMargin: 0/1 正確 |
| `add_margin()` | `/v5/position/add-margin` | POST | **[PASS]** | margin 字串化正確 |
| `get_closed_pnl()` | `/v5/position/closed-pnl` | GET | **[PASS]** | 解析 avgEntryPrice/avgExitPrice/closedPnl 等字段正確 |

### 2.4 帳戶端點 — `account_manager.rs`

| 方法 | Bybit 路徑 | HTTP | 結果 | 備註 |
|------|-----------|------|------|------|
| `refresh_balance()` | `/v5/account/wallet-balance` | GET | **[PASS]** | `accountType=UNIFIED` 正確；解析 totalEquity/totalWalletBalance/totalAvailableBalance + per-coin (equity/walletBalance/availableToWithdraw/unrealisedPnl/cumRealisedPnl) 完整 |
| `refresh_fee_rates()` | `/v5/account/fee-rate` | GET | **[PASS]** | `category=linear` 正確；解析 makerFeeRate/takerFeeRate 正確；默認 fallback 0.00055/0.0002 與 Bybit VIP-0 費率一致 |
| `get_account_info()` | `/v5/account/info` | GET | **[PASS]** | 解析 marginMode/unifiedMarginStatus/smpGroup/isMasterTrader 正確 |
| `set_hedging_mode()` | `/v5/account/set-hedging-mode` | POST | **[API-MISMATCH]** | Bybit V5 可能的正確路徑為 `/v5/account/set-hedging`（無 `-mode` 後綴）。需驗證。此端點在項目中未被調用（dead code），影響為零 |
| `get_borrow_history()` | `/v5/account/borrow-history` | GET | **[PASS]** | currency/limit 參數正確 |
| `repay()` | `/v5/account/repay` | POST | **[API-MISMATCH]** | Bybit V5 UTA 帳戶的還款端點可能不是此路徑。需驗證是否為 `/v5/account/quick-repayment` 或其他。此端點在項目中未被調用（dead code），影響為零 |

### 2.5 平台端點 — `platform_client.rs`

| 方法 | Bybit 路徑 | HTTP | 結果 | 備註 |
|------|-----------|------|------|------|
| `get_transaction_log()` | `/v5/account/transaction-log` | GET | **[PASS]** | |
| `set_margin_mode()` | `/v5/account/set-margin-mode` | POST | **[PASS]** | |
| `get_collateral_info()` | `/v5/account/collateral-info` | GET | **[PASS]** | |
| `set_collateral()` | `/v5/account/set-collateral` | POST | **[PASS]** | |
| `set_dcp()` | `/v5/order/disconnected-cancel-all` | POST | **[PASS]** | timeWindow 正確 |
| `get_dcp_info()` | `/v5/account/dcp-info` | GET | **[PASS]** | 僅 mainnet 支援 |
| `pre_check_order()` | `/v5/order/create` | POST | **[RISK]** | 此方法作為「預檢」使用 `/v5/order/create`（真正的下單端點）。代碼註釋已承認「Bybit 沒有專門的預檢端點」。如果 params 格式正確且帳戶有餘額，此調用**會真正下單**。建議：(a) 在 body 加 `dryRun` 標記（如 Bybit 未來支援），(b) 或移除此方法並改用本地驗證。**目前此方法未在交易路徑中被調用，風險暫低** |
| `inter_transfer()` | `/v5/asset/transfer/inter-transfer` | POST | **[PASS]** | transferId UUID + coin/amount/from/to 正確 |
| `query_transfer_list()` | `/v5/asset/transfer/query-inter-transfer-list` | GET | **[PASS]** | |
| `get_account_coins_balance()` | `/v5/asset/transfer/query-account-coins-balance` | GET | **[PASS]** | |
| `get_coin_info()` | `/v5/asset/coin-info` | GET | **[PASS]** | |
| `apply_demo_funds()` | `/v5/account/demo-apply-money` | POST | **[PASS]** | `utaList` 格式正確（coin + amountStr） |

### 2.6 市場數據端點 — `market_data_client/mod.rs`

| 方法 | Bybit 路徑 | HTTP | 結果 | 備註 |
|------|-----------|------|------|------|
| `get_server_time()` | `/v5/market/time` | GET | **[PASS]** | timeSecond/timeNano 解析正確 |
| `get_klines()` | `/v5/market/kline` | GET | **[PASS]** | interval 格式正確（"1"/"5"/"15"/"60"/"D"/"W"/"M"） |
| `get_mark_price_klines()` | `/v5/market/mark-price-kline` | GET | **[PASS]** | |
| `get_premium_index_klines()` | `/v5/market/premium-index-price-kline` | GET | **[PASS]** | |
| `get_index_price_klines()` | `/v5/market/index-price-kline` | GET | **[PASS]** | |
| `get_tickers()` | `/v5/market/tickers` | GET | **[PASS]** | |
| `get_orderbook()` | `/v5/market/orderbook` | GET | **[PASS]** | limit 默認 50 |
| `get_open_interest()` | `/v5/market/open-interest` | GET | **[PASS]** | 參數名 `intervalTime` 正確（非 `interval`）|
| `get_funding_history()` | `/v5/market/funding/history` | GET | **[PASS]** | startTime/endTime 正確 |
| `get_long_short_ratio()` | `/v5/market/account-ratio` | GET | **[PASS]** | period 參數正確 |
| `get_risk_limit()` | `/v5/market/risk-limit` | GET | **[PASS]** | |
| `get_insurance()` | `/v5/market/insurance` | GET | **[PASS]** | |
| `get_adl_alert()` | `/v5/market/adl-alert` | GET | **[MISSING-HANDLER]** | 此端點可能不存在於 Bybit V5 公開市場數據 API 中。ADL 信息通常通過私有 WS `position` topic 中的 `adlRankIndicator` 字段獲取，或通過持倉列表的 `isReduceOnly` 字段推斷。調用此端點可能返回 retCode != 0。但代碼已有 `into_result()` 錯誤處理，不會 panic。影響：ADL 警報功能可能靜默失敗 |
| `get_recent_trades()` | `/v5/market/recent-trade` | GET | **[PASS]** | |
| `get_historical_volatility()` | `/v5/market/historical-volatility` | GET | **[PASS]** | |
| `get_delivery_price()` | `/v5/market/delivery-price` | GET | **[PASS]** | |
| `get_price_limit()` | `/v5/market/instruments-info` | GET | **[PASS]** | 正確！代碼注釋說明了不使用不存在的 `/v5/market/price-limit`，改為從 instruments-info 的 priceFilter 提取 |

### 2.7 合約信息 — `instrument_info.rs`

| 方法 | Bybit 路徑 | HTTP | 結果 | 備註 |
|------|-----------|------|------|------|
| `refresh()` | `/v5/market/instruments-info` | GET | **[PASS]** | 解析 lotSizeFilter (qtyStep/minOrderQty/maxOrderQty) + priceFilter (tickSize/minPrice/maxPrice) 正確；自動計算 qty_decimals/price_decimals |

### 2.8 現貨保證金 — `spot_margin_client.rs`

| 方法 | Bybit 路徑 | HTTP | 結果 | 備註 |
|------|-----------|------|------|------|
| `get_margin_data()` | `/v5/spot-margin-trade/data` | GET | **[PASS]** | |
| `switch_mode()` | `/v5/spot-margin-uta/switch-mode` | POST | **[PASS]** | |
| `set_leverage()` | `/v5/spot-margin-uta/set-leverage` | POST | **[PASS]** | |
| `get_status()` | `/v5/spot-margin-uta/status` | GET | **[PASS]** | |
| `get_max_borrowable()` | `/v5/spot-margin-uta/max-borrowable` | GET | **[PASS]** | |
| `get_repay_history()` | `/v5/spot-margin-uta/repayment-available-amount` | GET | **[NAMING]** | 函數名 `get_repay_history()` 暗示查詢還款歷史，但實際調用的端點是「可還款金額」查詢。功能語義不匹配。應重命名為 `get_repayment_available()` 或類似名稱。非阻塞 bug，但可能造成維護混淆 |

### 2.9 槓桿代幣 — `leverage_token_client.rs`

| 方法 | Bybit 路徑 | HTTP | 結果 | 備註 |
|------|-----------|------|------|------|
| `get_token_info()` | `/v5/spot-lever-token/info` | GET | **[PASS]** | |
| `get_token_reference()` | `/v5/spot-lever-token/reference` | GET | **[PASS]** | |
| `purchase()` | `/v5/spot-lever-token/purchase` | POST | **[PASS]** | |
| `redeem()` | `/v5/spot-lever-token/redeem` | POST | **[PASS]** | |

---

## 三、WebSocket 審計

### 3.1 公開 WebSocket — `ws_client.rs` + `multi_interval_ws.rs`

| 項目 | 結果 | 詳情 |
|------|------|------|
| **URL** | **[PASS]** | `wss://stream.bybit.com/v5/public/linear`（config 默認值），可通過 TOML 覆蓋 |
| **訂閱格式** | **[PASS]** | `{"op":"subscribe","args":["topic1","topic2",...]}` 正確 |
| **批量限制** | **[PASS]** | 每次 subscribe 最多 10 個 topic（`SUBSCRIBE_BATCH_SIZE=10`），符合 Bybit 限制 |
| **動態訂閱** | **[PASS]** | `WsTopicChange::Subscribe/Unsubscribe` 支援運行時增減 topic，且記錄到重連重播列表 |
| **心跳** | **[PASS]** | `{"op":"ping"}` 每 20s 發送（可配置 `heartbeat_interval_ms`）；Bybit 要求 <=20s |
| **Ping/Pong** | **[PASS]** | 處理 `Message::Ping` 回覆 `Message::Pong`；JSON pong 回應正確忽略 |
| **連接超時** | **[PASS]** | 15s 連接超時（WS-TIMEOUT 修復） |
| **重連** | **[PASS]** | 指數退避 3s base × 2^attempt，上限 60s |
| **取消** | **[PASS]** | `CancellationToken` 在連接/退避/消息循環三個階段都檢查 |

**訂閱 Topic 格式審計**:

| Topic | 格式 | 結果 |
|-------|------|------|
| K 線 | `kline.{interval}.{symbol}` | **[PASS]** — interval: "1"/"5"/"15"/"60" 正確 |
| 行情 | `tickers.{symbol}` | **[PASS]** |
| 訂單簿 | `orderbook.50.{symbol}` | **[PASS]** — 50 檔深度 |
| 成交 | `publicTrade.{symbol}` | **[PASS]** |
| 清算 | `liquidation.{symbol}` | **[PASS]** |
| 價格限制 | `price-limit.{symbol}` | **[PASS]** — 代碼有 parser 但未在 multi_interval_ws 中默認訂閱 |
| ADL 通知 | `adl-notice.{symbol}` | **[PASS]** — 代碼有 parser 但未默認訂閱 |

**消息解析審計**:

| 消息類型 | 解析正確性 | 備註 |
|----------|-----------|------|
| Trade (`p`/`v`/`T`/`S`) | **[PASS]** | 價格/成交量/時間戳/方向全部正確 |
| Kline (`close`/`start`/`volume`/`confirm`) | **[PASS]** | 正確只處理 confirmed K 線；未確認丟棄 |
| Orderbook (`b`/`a` arrays) | **[PASS]** | best bid/ask + mid price + top-5 levels 正確 |
| Ticker (`lastPrice`/`volume24h`/`bid1Price`/`ask1Price`/`turnover24h`) | **[PASS]** | |
| Liquidation (`price`/`side`/`size`/`updatedTime`) | **[PASS]** | |

### 3.2 私有 WebSocket — `bybit_private_ws.rs`

| 項目 | 結果 | 詳情 |
|------|------|------|
| **URL** | **[PASS]** | Demo/LiveDemo: `wss://stream-demo.bybit.com/v5/private`；Testnet: `wss://stream-testnet.bybit.com/v5/private`；Mainnet: `wss://stream.bybit.com/v5/private` |
| **認證格式** | **[PASS]** | `{"op":"auth","args":["api_key","expires","signature"]}` 正確；sign = `HMAC-SHA256(api_secret, "GET/realtime" + expires)` 符合 Bybit 規範；expires = now + 10000ms |
| **認證超時** | **[PASS]** | 10s 超時等待 auth response |
| **訂閱確認檢查** | **[PASS]** | B-2 教訓後新增 subscribe 確認日誌（success=false 時 error 級別），防止 topic 名稱拼寫錯誤被靜默忽略 |
| **Ping** | **[PASS]** | `{"op":"ping"}` 每 20s |
| **重連** | **[PASS]** | 指數退避 3s × 2^attempt，上限 60s |
| **取消** | **[PASS]** | 三個階段（連接前/認證中/消息循環/退避中）均檢查 CancellationToken |

**B-2 修復驗證** (execution.fast vs execution):

| 環境 | 訂閱 Topics | 結果 |
|------|------------|------|
| Demo | `order, execution, position, wallet` | **[PASS]** — 不包含 `execution.fast`（Demo 靜默接受但不推數據） |
| LiveDemo | 同 Demo | **[PASS]** |
| Testnet | 同 Demo | **[PASS]** |
| Mainnet | `order, execution.fast, position, wallet, dcp` | **[PASS]** — 使用 `execution.fast`（~50ms 延遲）+ `dcp` |

**回歸測試**: `test_private_topics_per_environment()` 覆蓋了所有 4 個環境的正確 topic 選擇，包括防止 `fast-execution` typo。

**私有消息解析審計**:

| Topic | 解析字段 | 結果 |
|-------|---------|------|
| `order` | orderId, orderLinkId, symbol, side, orderType, price, qty, cumExecQty, orderStatus, createdTime, updatedTime | **[PASS]** |
| `execution` | execId, orderId, symbol, side, execPrice, execQty, execFee, execType, execTime | **[PASS]** |
| `execution.fast` | 同 execution（少 execFee/execValue/feeRate） | **[PASS]** — serde default 處理缺失字段為空字串 |
| `position` | symbol, side, size, avgPrice, unrealisedPnl, markPrice, liqPrice | **[PASS]** — `avgPrice` / `unrealisedPnl` 有 `alias` 處理 camelCase |
| `wallet` | accountType, coin[].{coin, equity, walletBalance, availableToWithdraw} | **[PASS]** |
| `dcp` | (無數據字段) | **[PASS]** — 僅事件通知 |

**[PARSE-ERROR]**: `execution.fast` 消息**缺少 `execFee` 字段**，但 `ExecutionUpdate.exec_fee` 使用 `serde(default)` 解析為空字串 `""`。下游代碼如果對 `exec_fee` 做 `parse::<f64>()` 將得到 0.0。對於 mainnet live 交易，這意味著通過 WS 推送的 fast-execution 事件**沒有真實手續費**——手續費需要從 REST `/v5/execution/list`（返回完整 `execFee`）或普通 `execution` topic 補全。**此問題與 PNL-FIX-2（`emit_close_fill` 寫 `fee: 0.0`）性質相似**，但因 mainnet 尚未上線，暫無影響。

---

## 四、HMAC 簽名審計

| 項目 | 結果 | 詳情 |
|------|------|------|
| **REST 簽名** | **[PASS]** | `sign_str = timestamp + api_key + recv_window + params`；GET params 排序後序列化；POST body JSON 序列化後簽名。符合 Bybit V5 規範 |
| **WS 簽名** | **[PASS]** | `sign_payload = "GET/realtime" + expires`；HMAC-SHA256(api_secret, sign_payload)。符合 Bybit 規範 |
| **Headers** | **[PASS]** | `X-BAPI-API-KEY`, `X-BAPI-SIGN`, `X-BAPI-TIMESTAMP`, `X-BAPI-RECV-WINDOW` 四個 header 完整 |
| **recv_window** | **[PASS]** | 固定 5000ms，符合 Bybit 推薦值 |
| **GET 參數排序** | **[PASS]** | `sorted_params.sort_by_key(|(k, _)| *k)` 按 key 字母序排列 |

---

## 五、錯誤處理審計

| 項目 | 結果 | 詳情 |
|------|------|------|
| **retCode 檢查** | **[PASS]** | `BybitResponse::into_result()` 統一處理 retCode != 0 |
| **已知 retCode 分類** | **[PASS]** | 0/10001-10006/10010/110001/110009/110012/110043/170210 全部覆蓋 |
| **冪等錯誤** | **[PASS]** | 110043 (LeverageNotModified) + 110001 (OrderNotFound) 標記為 noop |
| **重試策略** | **[PASS]** | 僅 10006 (IpRateLimit) 標記為可重試；其他不重試，符合 fail-closed 原則 |
| **HTTP 超時** | **[PASS]** | `reqwest::Client::builder().timeout(10s)` |
| **無憑證保護** | **[PASS]** | `has_credentials()` 檢查，空 key 時返回 `NoCredentials` 錯誤 |

---

## 六、限流審計

| 項目 | 結果 | 詳情 |
|------|------|------|
| **全局限流追蹤** | **[PASS]** | 從 `X-Bapi-Limit-Status` / `X-Bapi-Limit-Reset-Timestamp` header 讀取 |
| **分組限流** | **[PASS]** | 6 組（Order/Position/Account/Market/Asset/Other），路徑自動分類 |
| **主動退讓** | **[PASS]** | remaining ≤ 10 時等待至 reset_ms + 50ms buffer，上限 2s |
| **WS 批次間隔** | **[PASS]** | 運行時 subscribe 500ms inter-batch gap |

---

## 七、環境配置審計

| 環境 | REST URL | WS Private URL | Secret Slot | 結果 |
|------|---------|----------------|-------------|------|
| Demo | `api-demo.bybit.com` | `stream-demo.bybit.com/v5/private` | demo | **[PASS]** |
| LiveDemo | `api-demo.bybit.com` | `stream-demo.bybit.com/v5/private` | live | **[PASS]** |
| Testnet | `api-testnet.bybit.com` | `stream-testnet.bybit.com/v5/private` | demo | **[PASS]** |
| Mainnet | `api.bybit.com` | `stream.bybit.com/v5/private` | live | **[PASS]** |
| Default | Demo | — | — | **[PASS]** — 安全默認值 |

**Mainnet 安全**: 啟用時有 `tracing::warn!` 警告；LiveDemo 使用 live slot key 連 demo 伺服器，設計合理。

---

## 八、發現問題清單

### P0 — 無

### P1 — 低風險，建議修復

| 編號 | 標籤 | 文件 | 問題 | 建議 |
|------|------|------|------|------|
| BB-A1 | [API-MISMATCH] | `position_manager.rs:329` | `/v5/position/confirm-mmr` 可能應為 `/v5/position/confirm-pending-mmr`。但此端點未在交易路徑中被調用 | 驗證 Bybit 最新 API 文檔後修正 |
| BB-A2 | [API-MISMATCH] | `account_manager.rs:374` | `/v5/account/set-hedging-mode` 可能不是正確路徑。Dead code，從未被調用 | 驗證或刪除 |
| BB-A3 | [API-MISMATCH] | `account_manager.rs:420` | `/v5/account/repay` 可能不是 UTA 帳戶的正確還款路徑。Dead code，從未被調用 | 驗證或刪除 |
| BB-A4 | [PARSE-ERROR] | `bybit_private_ws.rs:593-605` | `execution.fast` topic 缺少 `execFee`，WS 推送的手續費為 `""` → 0.0。Mainnet 上線時需從 REST 補全 | 上線前補全邏輯或使用普通 `execution` topic 覆蓋 |
| BB-A5 | [RISK] | `platform_client.rs:362-370` | `pre_check_order()` 使用真正的 `/v5/order/create`，可能意外下單 | 明確標記為 dangerous 或移除 |
| BB-A6 | [NAMING] | `spot_margin_client.rs:216` | `get_repay_history()` 實際查的是「可還款金額」不是「還款歷史」 | 重命名為 `get_repayment_available()` |
| BB-A7 | [MISSING-HANDLER] | `market_data_client/mod.rs:473` | `/v5/market/adl-alert` 可能不是有效的 Bybit V5 公開端點 | 驗證端點存在性；考慮改用持倉 adlRankIndicator |

### P2 — 觀察項

| 編號 | 項目 | 備註 |
|------|------|------|
| BB-O1 | `execution.fast` 與 `execution` 重複事件 | Mainnet 僅訂閱 `execution.fast` 不訂閱 `execution`——正確避免重複。但 `execution.fast` 欄位不完整，live 交易上線後需確認 fee 補全路徑 |
| BB-O2 | DCP topic 僅 mainnet | 正確行為，demo 會拒絕 `dcp` topic。但 DCP POST 設置(`/v5/order/disconnected-cancel-all`)也僅 mainnet 有效，demo 調用會得到錯誤 |
| BB-O3 | 默認 taker fee 0.00055 | 與 Bybit 2026 VIP-0 linear 費率一致。如 Bybit 調整費率結構需同步更新 |

---

## 九、結論

**核心交易路徑安全**: 下單/查倉/查餘額/WS 訂閱/HMAC 簽名/限流/錯誤處理——全部正確，測試覆蓋充分。

**B-2 修復徹底**: `execution.fast` vs `execution` 的環境差異在代碼（`private_ws_topics()`）和測試（`test_private_topics_per_environment()`）兩層防護，回歸風險極低。

**主要風險**: BB-A4（`execution.fast` 缺少手續費）是 mainnet 上線前唯一需要關注的 P1 問題，因為它可能導致通過 WS 收到的 fill 事件手續費為 0，與 PNL-FIX-2 同類。其他 API-MISMATCH 問題均在 dead code 路徑，不影響運行。

**建議優先級**: BB-A4 > BB-A5 > BB-A1 > BB-A6 > BB-A7 > BB-A2 = BB-A3


---

# 12. TW — 文件盤查（4/1-4/12）

> 原始文件：`docs/CCAgentWorkSpace/TW/2026-04-12--document_audit_report.md`

# TW 文檔審計報告 — 2026-04-12

**審計範圍**: `docs/` 全目錄 + 項目根 `.md` 文件
**時間窗口**: 2026-04-01 ~ 2026-04-12（重點），全量盤查
**文件總數**: 445 個 `.md` 文件 + 38 個 `.txt` 文件 + 若干 `.py`/`.pdf`
**目錄數**: 47 個子目錄

---

## 一、統計總覽

| 目錄 | .md 文件數 | 說明 |
|------|-----------|------|
| `worklogs/control_api_gui/` | 46 | 最大單一目錄，03-26~04-02 時期 |
| `references/` | 35 | 長期參考文檔 |
| `governance_dev/changelogs/` | 23 | T2.01~T2.23 模組變更 |
| `worklogs/phase5_arch_rc1/` | 21 | 04-03~04-07 時期 |
| `worklogs/`（頂層） | 16 | 04-08+ 最新日誌 |
| `CCAgentWorkSpace/` (各Agent) | ~105 | 16 Agent profile/memory/reports |
| `governance_dev/`（含子目錄） | 127 | 已標 DEPRECATED 的 Python 時代治理文檔 |
| `handoffs/` | 17 | API/GUI 交接記錄 |
| `audits/` | 21 | 專項 + L3 綜合審計 |
| `execution_plan/` | 11 | Phase 0-6 + 關鍵路徑 |
| `rust_migration/` | 9 | Rust 遷移階段計劃 |
| `archive/` | 7 | 已歸檔完成項 |
| `architecture/` | 1 | 數據存儲架構 |
| `decisions/` | 2 | 重大決策記錄 |

---

## 二、重複文件檢測

### 2.1 確認重複 [DUPLICATE]

| 文件 | 重複對象 | 建議 |
|------|----------|------|
| `references/2026-04-03--rust_migration_master_plan_v2.md` | 已由 `rust_migration_v3_final.md` 取代（文件自標 DEPRECATED） | [DUPLICATE] 移至 `archive/` |
| `references/2026-04-03--rust_migration_v2.5_consolidated.md` | 已由 `rust_migration_v3_final.md` 取代（文件自標 DEPRECATED） | [DUPLICATE] 移至 `archive/` |
| `references/2026-04-03--data_storage_architecture_optimal_draft_v0.1.md` | 已由 `architecture/DATA_STORAGE_ARCHITECTURE_V1.md` 取代（文件自標 DEPRECATED） | [DUPLICATE] 移至 `archive/` |
| `worklogs/chapters_j-k/2026-03-22--项目总报告_含github核对.txt` | 同名 `.md` 版本已存在 | [DUPLICATE] 刪除 `.txt` 版 |
| `worklogs/chapters_j-k/2026-03-24--work_report_current_dialogue.txt` | 同名 `.md` + `.pdf` 版本已存在（三份） | [DUPLICATE] 保留 `.md`，刪除 `.txt` + `.pdf` |

### 2.2 內容重疊 [MERGE-CANDIDATE]

| 文件組 | 重疊描述 | 建議 |
|--------|----------|------|
| CCAgentWorkSpace 04-01 審計報告 (15份) vs `audits/2026-04-05_l3_comprehensive/` (12份) | 04-01 的 AI-E/CC/E3/E4/E5/FA/TW 報告被 04-05 L3 審計完全覆蓋更新。04-05 報告更全面、更新。 | [MERGE-CANDIDATE] 04-01 報告已過時，建議標注 "superseded by L3 audit 04-05" |
| `references/2026-04-11--3e_arch_session_execution_plan.md` vs `references/2026-04-11--three_engine_parallel_arch_plan.md` | 同日兩份 3E-ARCH 文檔：一份執行計劃，一份遷移計劃。內容互補但有 50%+ 重疊 | [MERGE-CANDIDATE] 合併為單一 `2026-04-11--3e_arch_plan_and_execution.md` |
| `references/2026-04-04--execution_plan_v1.md` vs `references/2026-04-06--phase4_execution_plan_v2.md` vs `execution_plan/phase_*.md` | 三套執行計劃：(1) references 下兩個版本化計劃 (2) execution_plan/ 下分 Phase 的計劃。V2 是否取代 V1？execution_plan/ 是否過時？ | [MERGE-CANDIDATE] V1→V2 應標注取代關係；`execution_plan/` 目錄需與 references 對齊 |
| `governance_dev/audits/2026-03-30--全面審核/` (11份) vs `governance_dev/audits/` 其他審計 | 全面審核 vs 各輪獨立審計，部分內容重複（如合規、缺口分析） | [MERGE-CANDIDATE] 已整體標 DEPRECATED，建議在 DEPRECATED.md 中明確列出 |

### 2.3 CHANGELOG vs CLAUDE.md 重複

`CLAUDE_CHANGELOG.md`（2135 行）與 `CLAUDE.md` 三保持同步，CLAUDE.md 三的每個段落在 CHANGELOG 中都有對應展開條目。**這是設計如此**（CLAUDE.md = 摘要，CHANGELOG = 詳細歷史），不算重複，但 CHANGELOG 體量過大，建議按月或按 Phase 拆分歸檔。

---

## 三、日誌碎片與合併建議

### 3.1 缺失每日摘要 [MISSING]

按 CLAUDE.md 七強制同步規則「當天 worklog 碎片合併為 YYYY-MM-DD--daily_summary.md」：

| 日期 | 碎片數 | daily_summary | 狀態 |
|------|--------|---------------|------|
| 04-03 | 1 | `phase5_arch_rc1/2026-04-03--daily_summary.md` | OK |
| 04-04 | 3 | `phase5_arch_rc1/2026-04-04--daily_summary.md` | OK |
| 04-05 | 0 | `phase5_arch_rc1/2026-04-05--daily_summary.md` | OK |
| 04-06 | 7 | **缺失** | [MISSING] 7 個 session 碎片未合併 |
| 04-07 | 4 | **缺失** | [MISSING] 4 個 session 碎片未合併 |
| 04-08 | 7 | `2026-04-08--daily_summary.md` | OK（碎片保留） |
| 04-09 | 2 | **缺失** | [MISSING] 2 個 worklog 無 daily summary |
| 04-10 | 2 | **缺失** | [MISSING] 2 個 worklog 無 daily summary |
| 04-11 | 1 | `2026-04-11--daily_summary.md` | OK |
| 04-12 | 2 | **缺失** | [MISSING] 2 個 worklog 無 daily summary |

**建議**: 補建 04-06、04-07、04-09、04-10、04-12 的 daily_summary。04-06/07 碎片可回溯合併。

### 3.2 04-06 session 碎片過多

`worklogs/phase5_arch_rc1/` 下 04-06 有 7 個碎片文件，其中 3 個名為 `*_precompact` 暗示已準備壓縮但未執行：
- `session10_r0_r1_remediation.md`
- `session11_p1_6_drift_detector.md`
- `session11_precompact.md` -- 壓縮候選
- `session11_r2_batch.md`
- `session12_precompact.md` -- 壓縮候選
- `session13_precompact.md` -- 壓縮候選
- `session_progress_2.md`

**建議**: 合併為 `2026-04-06--daily_summary.md`，刪除碎片。

### 3.3 Completed TODO 歸檔分散

7 個 `completed_todo_archive` 文件分布在 3 個不同目錄：
- `archive/`（3 份，04-10~11）
- `worklogs/control_api_gui/`（1 份，04-01）
- `worklogs/phase5_arch_rc1/`（3 份，04-03~06）

**建議**: 統一移至 `archive/` 目錄，按日期排列。

---

## 四、過時文檔 [STALE]

### 4.1 描述已刪除功能的文檔

| 文件 | 問題 | 狀態 |
|------|------|------|
| `governance_dev/changelogs/2026-03-29_T2.19_protective_order_manager.md` | ProtectiveOrderManager 已在 DEAD-PY-2 Phase C 全部刪除 | [STALE] |
| `governance_dev/` 全目錄（127 份） | 已標 DEPRECATED（Python 時代治理），但仍有 20+ 文件引用已刪除的 bridge_core / pipeline_bridge / BybitDemoConnector | [STALE] 已妥善標注，無需額外行動 |
| `references/2026-03-25--capability_and_permission_switch_plan_v1.md` | 權限開關計劃，已被 Rust ConfigStore 取代 | [STALE] |
| `references/2026-03-25--gui_operator_console_learning_cockpit_v1_spec.md` | GUI v1 規格，已被 Live GUI P0-P6 大幅改動 | [STALE] |
| `references/2026-04-02--system_status_report.md` | 04-02 系統狀態快照，已被 CLAUDE.md 三多次更新取代 | [STALE] |
| `references/2026-03-27--phase2_audit_fix_roadmap.md` | Phase 2 修復路線圖，Phase 0-5 全部完成 | [STALE] |
| `references/2026-03-27--phase2_round2_strategic_audit_report.md` | 同上 | [STALE] |
| `references/2026-03-27--phase2_strict_audit_report.md` | 同上 | [STALE] |
| `execution_plan/phase_0a.md` ~ `phase_4.md` | Phase 0-4 已全部完成，計劃文件仍保留 | [STALE] 建議移至 archive 或標注完成 |
| `KNOWN_ISSUES.md` | 最後更新 04-05，標題統計 "OPEN 10 / RESOLVED 11"，10 天未更新 | [STALE] 需 review 10 個 OPEN 項是否已解決 |
| `CLAUDE_REFERENCE.md` | 最後更新 04-06，缺少 04-07~12 的新架構記錄（3E-ARCH、StrategyAction、Multi-Symbol、Phase 6 Reconciler 等） | [STALE] 需更新 |

### 4.2 引用已過時概念的活躍文檔

| 文件 | 問題 |
|------|------|
| `references/2026-04-10--signal_diamond_db_todo.md` | 引用 `TradingMode`（已由 `PipelineKind` 取代） |
| `references/2026-04-11--three_engine_parallel_arch_plan.md` | 引用 `TradingMode`（同上） |
| `references/2026-04-11--3e_arch_session_execution_plan.md` | 引用 `TradingMode`（同上） |
| `references/2026-04-03--openclaw_improvement_report_v3_final.md` | 引用 Binance（已決定不考慮 Binance 兼容性） |

### 4.3 遺留格式文件

`worklogs/chapters_a-g/` 和 `chapters_h-i/` 下共 25 個 `.txt` 文件，為項目早期遺留格式。按規範應為 `.md`。
`worklogs/chapters_j-k/` 下有 `.txt` + `.pdf` 與 `.md` 同名重複（見 二.1）。

---

## 五、孤兒文檔 [ORPHAN]

以下文件未被 `docs/README.md`、`CLAUDE.md`、`CLAUDE_REFERENCE.md` 或任何索引鏈接引用：

### 5.1 references/ 下的孤兒

| 文件 | 狀態 |
|------|------|
| `references/math_implementation_notes.md` | [ORPHAN] 無日期、無索引引用 |
| `references/2026-03-30--local_ai_expansion_analysis.md` | [ORPHAN] 未被任何索引引用 |
| `references/2026-03-27--local_trading_logic_audit_and_strategy_plan.md` | [ORPHAN] |
| `references/2026-03-27--full_system_audit_A_to_K.md` | [ORPHAN] 可能被 03-27 時期審計取代 |
| `references/2026-03-27--system_reference_handbook.md` | [ORPHAN] |
| `references/2026-03-27--remote_access_guide.md` | [ORPHAN] 但有實用價值（遠程存取指南） |
| `references/2026-04-04--comprehensive_audit_template_v1.md` | [ORPHAN] 審計模板，CLAUDE.md 八提到但未鏈接 |

### 5.2 CCAgentWorkSpace 空目錄

| Agent | 狀態 |
|-------|------|
| `E1a/workspace/` | [ORPHAN] 無 reports 子目錄，workspace 為空 |
| `QA/workspace/` | [ORPHAN] 無 reports 子目錄，workspace 為空 |

### 5.3 worklogs/ 下的孤兒

| 文件 | 狀態 |
|------|------|
| `worklogs/learning/2026-03-26--L章_自动学习管线与安全加固_完整工程日志.md` | [ORPHAN] learning 目錄僅此一份文件 |
| `worklogs/2026-04-08--arch_rc1_1c_history_archive.md` | [ORPHAN] 與 `archive/2026-04-08--main_docs_1c3_1c4_narrative.md` 內容可能重疊 |

---

## 六、缺失文檔 [MISSING]

### 6.1 有功能但無文檔的模組

| 功能 | 狀態 |
|------|------|
| Phase 6 Reconciler 自動降級 | [MISSING] CLAUDE.md 三有摘要，但無獨立設計文檔（reconciler 行為規則/升降級矩陣等） |
| Live GUI Phase 1-6 | [MISSING] 6 個 Phase 的實施在 CLAUDE.md 三記錄，但無獨立 GUI 設計/用戶指南 |
| A2 NewsPipeline Scheduler | [MISSING] 僅 CLAUDE.md 三有摘要，無獨立文檔 |
| Multi-Symbol Position Tracking | [MISSING] 僅 CLAUDE.md 三有摘要，無設計文檔 |
| StrategyAction Enum | worklogs/2026-04-09 有記錄，但無 references/ 下的設計文檔 |
| PNL-FIX-1/2 根因分析 | [MISSING] CLAUDE.md 三有摘要，memory 有記錄，但無獨立的根因分析文檔 |

### 6.2 索引缺失

| 索引文件 | 問題 |
|----------|------|
| `docs/README.md` | 文檔索引區（底部）引用了 221 個 `.md`，但 04-08~12 新增的 worklogs / audits / references 未全部加入 |
| `CLAUDE_REFERENCE.md` | 最後更新 04-06，缺失 04-07~12 所有新功能的參考記錄 |
| `helper_scripts/SCRIPT_INDEX.md` | 未檢查是否與實際腳本同步（本次審計範圍外） |

---

## 七、文件質量速查

### 7.1 超長文件

| 文件 | 行數 | 建議 |
|------|------|------|
| `CLAUDE_CHANGELOG.md` | 2135 | 超過 1200 行硬上限，建議拆分歸檔（按月或按 Phase） |

### 7.2 governance_dev 整體評估

127 份文件已正確標注 `DEPRECATED.md`，指向 Rust 實現。**無需額外行動**，但建議：
- 長期考慮壓縮為單一 `governance_dev_archive.tar.gz`，減少文件樹噪音
- 短期：`DEPRECATED.md` 中增加「引用已刪除代碼」的警告（ProtectiveOrderManager / bridge_core 等）

---

## 八、優先修復建議（按重要性排序）

### P0 — 立即處理

1. **移動 3 個 DEPRECATED 文件到 archive/**
   - `rust_migration_master_plan_v2.md`
   - `rust_migration_v2.5_consolidated.md`
   - `data_storage_architecture_optimal_draft_v0.1.md`

2. **更新 `CLAUDE_REFERENCE.md`** — 加入 04-07~12 新功能參考（3E-ARCH / StrategyAction / Multi-Symbol / Phase 6 Reconciler / Live GUI / PNL-FIX）

3. **更新 `KNOWN_ISSUES.md`** — Review 10 個 OPEN 項，關閉已解決的

### P1 — 本週處理

4. **補建 5 個缺失 daily_summary** — 04-06 / 04-07 / 04-09 / 04-10 / 04-12

5. **合併 04-06 的 7 個 session 碎片**

6. **統一 completed_todo_archive 到 `archive/`** — 移動 `control_api_gui/` 和 `phase5_arch_rc1/` 下的 4 個歸檔文件

7. **刪除 `.txt`/`.pdf` 重複**
   - `chapters_j-k/2026-03-22--项目总报告_含github核对.txt`
   - `chapters_j-k/2026-03-24--work_report_current_dialogue.txt` + `.pdf`

### P2 — 下個 Sprint 處理

8. **拆分 `CLAUDE_CHANGELOG.md`**（2135 行）為歷史歸檔 + 當前活躍部分

9. **修正 `TradingMode` 引用** — 3 份 04-10/11 文件中的 `TradingMode` 改為 `PipelineKind`

10. **更新 `docs/README.md` 索引** — 補入 04-08~12 新增文件

11. **建立缺失設計文檔** — Phase 6 Reconciler / Live GUI 用戶指南（如需求存在）

### P3 — 長期改善

12. **governance_dev/ 壓縮歸檔** — 127 份已 DEPRECATED 文件可打包

13. **legacy `.txt` 工作日誌** — 25 份 chapters_a-g / chapters_h-i 的 .txt 轉 .md 或標注為 legacy

14. **CCAgentWorkSpace 04-01 報告標注** — 在 15 份報告頂部加 "superseded by L3 audit 2026-04-05"

---

## 九、文件狀態總表

### archive/ (7 files)
- `2026-04-03--system_snapshot_external_analysis.md` — [OK]
- `2026-04-07--claude_md_section3_history_phase0_4.md` — [OK]
- `2026-04-08--main_docs_1c3_1c4_narrative.md` — [OK]
- `2026-04-09--scanner_todo_phase_a_d_spec.md` — [OK]
- `2026-04-10--completed_todo_live_gui_dead_py.md` — [OK]
- `2026-04-11--completed_todo_3e_arch.md` — [OK]
- `2026-04-11--completed_todo_w19_w20_phase6.md` — [OK]

### audits/ (9 files + 12 L3 sub-files)
- `2026-04-04--bybit_api_infra_audit.md` — [OK] 活躍參考
- `2026-04-05_l3_comprehensive/` (12 files) — [OK] 最新全面審計
- `2026-04-06_consolidated_remediation_report.md` — [OK]
- `2026-04-07_e3_r6_directive_applier_security_audit.md` — [OK]
- `2026-04-07_phase4_final_signoff_audit.md` — [OK]
- `2026-04-08--e2_review_1c3_bbc.md` — [OK]
- `2026-04-09--db_rw_ml_pipeline_full_audit.md` — [OK]
- `2026-04-11--3e_arch_e2_multi_role_review.md` — [OK]
- `2026-04-11--3e_arch_phase_g_reaudit.md` — [OK]

### references/ (04-01~12 files)
- `2026-04-02--system_status_report.md` — [STALE] 被 CLAUDE.md 取代
- `2026-04-03--agent_cognitive_adaptation_spec_v1_draft.md` — [OK] CLAUDE.md 引用
- `2026-04-03--agent_param_tuning_design_draft_v0.2.md` — [OK]
- `2026-04-03--data_storage_architecture_optimal_draft_v0.1.md` — [DUPLICATE] 自標 DEPRECATED
- `2026-04-03--llm_abstraction_audit.md` — [OK]
- `2026-04-03--ml_dl_learning_architecture_v0.4.md` — [OK]
- `2026-04-03--openclaw_improvement_report_v3_final.md` — [OK] 含過時 Binance 引用
- `2026-04-03--rust_migration_master_plan_v2.md` — [DUPLICATE] 自標 DEPRECATED
- `2026-04-03--rust_migration_v2.5_consolidated.md` — [DUPLICATE] 自標 DEPRECATED
- `2026-04-03--rust_migration_v3_final.md` — [OK] 權威版本
- `2026-04-04--bybit_api_reference.md` — [OK] 活躍參考（強制查閱）
- `2026-04-04--comprehensive_audit_template_v1.md` — [ORPHAN]
- `2026-04-04--execution_plan_v1.md` — [MERGE-CANDIDATE] 與 V2 關係待釐清
- `2026-04-04--unified_db_ml_news_workplan_draft_v0.1.md` — [OK]
- `2026-04-06--phase4_execution_plan_v2.md` — [OK]
- `2026-04-07--arch_rc1_1c3_scope.md` — [OK] 歷史參考
- `2026-04-07--arch_rc1_1c3a_gap_analysis.md` — [OK]
- `2026-04-07--arch_rc1_1c3c_recon.md` — [OK]
- `2026-04-10--signal_diamond_db_todo.md` — [OK] 含過時 TradingMode 引用
- `2026-04-11--3e_arch_session_execution_plan.md` — [MERGE-CANDIDATE] 與同日 three_engine 重疊
- `2026-04-11--three_engine_parallel_arch_plan.md` — [MERGE-CANDIDATE] 同上

### worklogs/ 頂層 (04-08~12)
- `2026-04-08--daily_summary.md` — [OK]
- `2026-04-08--1c3d_main_body.md` — [OK] 碎片已有 daily summary
- `2026-04-08--1c3e_fmini_handoff.md` — [OK]
- `2026-04-08--arch_rc1_1c_history_archive.md` — [ORPHAN] 可能與 archive/ 重疊
- `2026-04-08--session_gui_fake_success_wave1.md` — [OK]
- `2026-04-08--session_gui_fake_success_wave2_p1_wiring.md` — [OK]
- `2026-04-08--session_progress_1c3f.md` — [OK]
- `2026-04-08--session_progress_post_1c4_wrap.md` — [OK]
- `2026-04-08--session_resume_notes.md` — [OK]
- `2026-04-09--rust_market_scanner_phase_a_d_complete.md` — [OK]
- `2026-04-09--strategy_action_enum_implementation.md` — [OK]
- `2026-04-10--ml_pipeline_remediation_complete.md` — [OK]
- `2026-04-10--signal_diamond_phase1_4_fix_round.md` — [OK]
- `2026-04-11--daily_summary.md` — [OK]
- `2026-04-12--earned_trust_ladder_and_audit_trail_fix.md` — [OK]
- `2026-04-12--gui_metrics_db_fallback_and_display_fixes.md` — [OK]

### 根目錄 .md
- `CLAUDE.md` — [OK] 核心指令文件
- `TODO.md` — [OK] 活躍任務追蹤
- `README.md` — [OK] 項目入口

### execution_plan/
- `phase_0a.md` ~ `phase_4.md` (7 files) — [STALE] Phase 0-4 已完成
- `phase_5.md` — [STALE] Phase 5 暫停
- `phase_6.md` — [OK] 當前/剛完成
- `critical_path.md` — 需檢查是否與 CLAUDE.md 十一致
- `README.md` — [OK]

---

## 十、結論

**整體健康度: 中等偏好**

優勢：
- 主要活躍文檔（CLAUDE.md / CHANGELOG / TODO.md）維護良好
- archive/ 機制運作正常
- governance_dev/ DEPRECATED 標注規範
- 04-08~12 worklogs 品質穩定

主要問題：
- **5 個日期缺失 daily_summary**（違反強制同步規則）
- **3 個已自標 DEPRECATED 的文件未移至 archive/**
- **CLAUDE_REFERENCE.md 過時 6 天**
- **KNOWN_ISSUES.md 過時 7 天**
- **CLAUDE_CHANGELOG.md 超長**（2135 行，超過 1200 行硬上限）
- **references/ 下殘留 7 個孤兒文件**

建議按 P0-P3 優先級逐步修復。P0 項可在 1 個 session 內完成。


---

# 13. R4 — 索引完整性驗證

> 原始文件：`docs/CCAgentWorkSpace/R4/2026-04-12--index_verification_report.md`

# R4 索引完整性驗證報告

**日期**：2026-04-12
**角色**：R4 (Reference/Index Maintainer)
**範圍**：全項目索引文件交叉驗證

---

## 一、docs/README.md 文檔索引

### 1.1 worklogs/chapters_a-g/（11 條目）

| 條目 | 狀態 |
|------|------|
| `2026-03-11--openclaw_bybit_进度日志.txt` | [OK] |
| `2026-03-12--openclaw_bybit_进度日志.txt` | [OK] |
| `2026-03-13--详细工作日志.txt` | [OK] |
| `2026-03-13--三日补充综合日志.txt` | [OK] |
| `2026-03-17--chapter_g_工程记录.txt` | [OK] |
| `2026-03-17--chapter_g_执行清单.txt` | [OK] |
| `2026-03-17--engineering_log.txt` | [OK] |
| `2026-03-19--补充记录1.txt` | [OK] |
| `2026-03-19--当前进度图_校正后.txt` | [OK] |
| `2026-03-19--工作记录_含0317至0319校正与修复.txt` | [OK] |
| `2026-03-19--完整版当前进度图.txt` | [OK] |

**結論**：磁盤 11 文件 = 索引 11 條目，完全匹配。

### 1.2 worklogs/chapters_h-i/（14 條目）

| 條目 | 狀態 |
|------|------|
| 全部 14 條目 | [OK] 磁盤完全匹配 |

**結論**：完全匹配。

### 1.3 worklogs/chapters_j-k/（11 條目）

| 條目 | 狀態 |
|------|------|
| 全部 11 條目 | [OK] 磁盤完全匹配 |

**結論**：完全匹配。

### 1.4 worklogs/control_api_gui/（~50 條目）

| 條目 | 狀態 |
|------|------|
| 全部已索引條目 | [OK] 磁盤文件存在 |
| `2026-03-31--round2_batch_records_archive.md` | [OK] 磁盤存在，索引已收錄 |

**結論**：完全匹配。

### 1.5 worklogs/phase5_arch_rc1/（21 條目）

| 條目 | 狀態 |
|------|------|
| 全部 21 條目 | [OK] 磁盤完全匹配 |

**結論**：完全匹配。

### 1.6 worklogs/learning/（1 條目）

| 條目 | 狀態 |
|------|------|
| `2026-03-26--L章_自动学习管线与安全加固_完整工程日志.md` | [OK] |

**結論**：完全匹配。

### 1.7 worklogs/ 頂層（2026-04-08+）

索引列出 13 個文件。磁盤實際有 16 個文件。

| 條目 | 狀態 |
|------|------|
| 索引已列出的 13 個文件 | [OK] 全部存在 |
| `2026-04-11--daily_summary.md` | [MISSING] 未列入索引 |
| `2026-04-12--earned_trust_ladder_and_audit_trail_fix.md` | [MISSING] 未列入索引 |
| `2026-04-12--gui_metrics_db_fallback_and_display_fixes.md` | [MISSING] 未列入索引 |

**結論**：3 個文件未列入索引（04-11 daily summary + 04-12 兩份 worklog）。

### 1.8 handoffs/

| 條目 | 狀態 |
|------|------|
| `2026-03-25_api_gui_handoff/` | [OK] 目錄存在 |

磁盤還有 `README` 文件，未索引但為自述文件，不計缺失。

### 1.9 decisions/

| 條目 | 狀態 |
|------|------|
| 全部 .md/.txt 文件（4 條） | [OK] |
| 全部 .docx 治理源文件（21 條） | [OK] |

**結論**：完全匹配。

### 1.10 audits/

| 條目 | 狀態 |
|------|------|
| `2026-03-30--bilingual_comment_audit_report.md` | [OK] |
| `2026-04-04--bybit_api_infra_audit.md` | [OK] |
| `2026-04-06_consolidated_remediation_report.md` | [OK] |
| `2026-04-07_e3_r6_directive_applier_security_audit.md` | [OK] |
| `2026-04-07_phase4_final_signoff_audit.md` | [OK] |
| `2026-04-08--e2_review_1c3_bbc.md` | [OK] |
| `2026-04-09--db_rw_ml_pipeline_full_audit.md` | [OK] |
| `2026-04-11--3e_arch_e2_multi_role_review.md` | [MISSING] 未列入索引 |
| `2026-04-11--3e_arch_phase_g_reaudit.md` | [MISSING] 未列入索引 |

**結論**：2 個 04-11 審計報告未列入索引。

### 1.11 audits/2026-04-05_l3_comprehensive/（12 條目）

| 條目 | 狀態 |
|------|------|
| 全部 12 條目 | [OK] |

### 1.12 architecture/

| 條目 | 狀態 |
|------|------|
| `DATA_STORAGE_ARCHITECTURE_V1.md` | [OK] |

### 1.13 references/

索引列出 ~30 個文件。磁盤有 35 個 .md 文件 + 子目錄。

| 未列入索引的文件 | 狀態 |
|------|------|
| `2026-04-06--phase4_execution_plan_v2.md` | [MISSING] 未列入索引 |
| `2026-04-07--arch_rc1_1c3a_gap_analysis.md` | [MISSING] 未列入索引 |
| `2026-04-07--arch_rc1_1c3c_recon.md` | [MISSING] 未列入索引 |
| `2026-04-07--arch_rc1_1c3_scope.md` | [MISSING] 未列入索引 |
| `2026-04-11--3e_arch_session_execution_plan.md` | [MISSING] 未列入索引 |
| `2026-04-11--three_engine_parallel_arch_plan.md` | [MISSING] 未列入索引 |
| `math_implementation_notes.md` | [MISSING] 未列入索引 |

**結論**：7 個文件未列入索引。

### 1.14 CCAgentWorkSpace Agent 表

| 條目 | 狀態 |
|------|------|
| PM / FA / PA / CC / E2 / E3 / E4 / E5 / E1 / E1a / A3 / R4 / TW / AI-E / QA | [OK] 全部目錄存在 |
| `CCAgentWorkSpace/QC/` | [MISSING] 目錄存在但未列入 README Agent 表 |
| `CCAgentWorkSpace/Operator/` | [MISSING] 目錄存在但未列入 README Agent 表 |

**結論**：README 列 15 個 Agent，實際有 17 個目錄（缺 QC、Operator）。CLAUDE_REFERENCE.md 已列出 QC，README 遺漏。

### 1.15 未索引的頂層目錄/文件

| 項目 | 狀態 |
|------|------|
| `docs/archive/` | [MISSING] 7 個歸檔文件，docs/README.md 完全未提及此目錄 |
| `docs/execution_plan/` | [MISSING] 11 個文件（含 README.md），docs/README.md 僅在 references 引用了名字相近的文件但未索引此目錄 |
| `docs/rust_migration/` | [MISSING] 9 個文件（含 README.md），docs/README.md 完全未索引此目錄 |
| `docs/KNOWN_ISSUES.md` | [MISSING] 存在但未列入索引 |
| `docs/CLAUDE_CHANGELOG.md` | [OK] 頂層知名文件，非需索引 |
| `docs/CLAUDE_REFERENCE.md` | [OK] 頂層知名文件，非需索引 |

---

## 二、CLAUDE_REFERENCE.md 驗證

### 2.1 引用的腳本/文件

| 引用 | 狀態 |
|------|------|
| `helper_scripts/maintenance_scripts/bybit_connector/run_i10_canonical_h_chain_recheck.sh` | [OK] |
| `helper_scripts/maintenance_scripts/bybit_connector/run_i10_canonical_decision_lease_recheck.sh` | [OK] |

### 2.2 已知文件名修正表

| 修正項 | 狀態 |
|------|------|
| `bybit_local_risk_envelope_gate.py` | [STALE] .py 源文件不存在（僅殘留 `__pycache__` .pyc），疑似 DEAD-PY-2 已刪除 |
| `bybit_local_trade_eligibility_handoff_builder.py` | [STALE] 同上 |
| `bybit_local_judgment_final_audit_contract_check.py` | [STALE] 同上 |

**結論**：文件名修正表中的 3 個「當前正確名」對應的 .py 源文件均已不存在（僅有 `__pycache__` 殘留）。此表已過時，應標記為歷史記錄或刪除。

### 2.3 CCAgentWorkSpace 審計報告引用

| 引用 | 狀態 |
|------|------|
| 2026-03-31 七份報告 (E3/CC/E4/E5/A3/PM/PA) | [OK] 全部存在 |
| 2026-04-01 十份報告 | [OK] AI-E/CC/E3/E4/E5/FA/TW/R4 存在；Operator/pa_review + pm_execution_plan 存在 |

### 2.4 references/ 引用

| 引用 | 狀態 |
|------|------|
| 所有 2026-03-27 系列 references | [OK] |

### 2.5 角色激活矩陣

| 項目 | 狀態 |
|------|------|
| 16 種任務類型 × 角色映射 | [OK] 完整 |
| QC 角色出現在矩陣中 | [OK] |

### 2.6 Sub-Agent Workspace 路徑對照表

| 項目 | 狀態 |
|------|------|
| 16 個角色路徑 | [OK] 全部路徑正確 |
| 缺少 Operator 和 QC | [OK] 表中有 QC，Operator 非標準 Agent |

### 2.7 最後更新日期

| 項目 | 狀態 |
|------|------|
| 標注 "最後更新：2026-04-06" | [STALE] 實際內容截至 04-06 後未更新，但結構性內容（角色/矩陣/路徑）仍然準確 |

---

## 三、CLAUDE_CHANGELOG.md 驗證

### 3.1 格式一致性

| 項目 | 狀態 |
|------|------|
| 標題格式 `### 標題（YYYY-MM-DD）` | [OK] 一致 |
| 按時間倒序排列 | [OK] |
| 最後更新標注 2026-04-12 | [OK] |

### 3.2 最近 commit 覆蓋度

CHANGELOG 最新條目為 2026-04-12 的 3 個條目（Earned-Trust / Phase 6 PM 驗收 / GUI 指標修復）。

| 未記錄的 commit | 狀態 |
|------|------|
| `1392006` fix(demo-gui): drop localStorage cache | [MISSING] 未記錄 |
| `6ed2299` fix(demo-stop): orphan sweep after close_all | [MISSING] 未記錄 |
| `986d724` feat(session): split paper/demo session controls | [MISSING] 未記錄 |
| `35272d3` fix(ipc): add explicit engine param to all IPC commands | [MISSING] 未記錄 |
| `9853845` fix(paper-metrics): use Rust-authoritative balance/peak | [MISSING] 未記錄 |
| `cbb4e45` fix(pnl): charge close fees + add fast_track observability | [MISSING] 未記錄 |
| `b93b83c` docs(worklog) | [OK] 純文檔 commit，可不記錄 |
| `5d99875` feat(live-trust): Earned-Trust TTL Ladder | [OK] 已記錄 |

**結論**：6 個功能/修復 commit 未記錄在 CHANGELOG 中（均為 04-12 日較晚的 commit）。

---

## 四、SCRIPT_INDEX.md 驗證

### 4.1 helper_scripts/SCRIPT_INDEX.md

索引列出 8 個腳本（含 `db/fresh_start_reset.py`）。磁盤實際有 ~75 個腳本。

| 已列入索引 | 狀態 |
|------|------|
| `restart_all.sh` | [OK] |
| `cron_daily_report.sh` | [OK] |
| `cron_observer_cycle.sh` | [OK] |
| `start_paper_trading.sh` | [OK] |
| `schema_diff.py` | [OK] |
| `golden_dataset_gen.py` | [OK] |
| `db/fresh_start_reset.py` | [OK] |

| 未列入索引的重要腳本 | 狀態 |
|------|------|
| `canary/engine_watchdog.py` | [MISSING] CLAUDE.md 灰度驗證引用的核心腳本 |
| `canary/canary_comparator.py` | [MISSING] |
| `canary/canary_schema.py` | [MISSING] |
| `canary/replay_runner.py` | [MISSING] |
| `canary/rollback_drill.sh` | [MISSING] |
| `canary/test_canary.py` | [MISSING] |
| `phase4/backfill_directive_outcomes.py` | [MISSING] |
| `phase4/dl3_go_no_go.py` | [MISSING] |
| `phase4/weekly_report.py` | [MISSING] |
| `maintenance_scripts/` 整個目錄（~60 腳本）| [MISSING] |

**結論**：索引嚴重過時。僅覆蓋根目錄 7 個腳本 + db/ 1 個。缺失 canary/（6 個）、phase4/（3 個）、maintenance_scripts/（~60 個）。覆蓋率約 8/75 = ~11%。

### 4.2 bybit_connector/docs/SCRIPT_INDEX.md

此為早期歷史索引，存在但未深入驗證（maintenance_scripts 下腳本主要為 legacy H/I/J/K 章節修復腳本）。

---

## 五、Memory 索引（MEMORY.md）驗證

### 5.1 主索引文件引用

| 引用 | 狀態 |
|------|------|
| `project_openclaw_positioning.md` | [OK] |
| `project_arch_rc1_unified_config.md` | [OK] |
| `project_hardware_constraints.md` | [OK] |
| `project_ml_dl_learning_architecture.md` | [OK] |
| `project_agent_p2_dynamic_sl_tp.md` | [OK] |
| `project_agent_workspace.md` | [OK] |
| `project_layer2_agent_design.md` | [OK] |
| `project_engine_consolidation_status.md` | [OK] |
| `project_gui_write_paths_inventory.md` | [OK] |
| `project_phase5_promotion_edge_crisis.md` | [OK] |
| `project_live_stage_status.md` | [OK] |
| `feedback_agent_autonomy.md` | [OK] |
| `feedback_audit_template.md` | [OK] |
| `feedback_cross_platform.md` | [OK] |
| `feedback_minimal_confirmation.md` | [OK] |
| `feedback_new_code_rust_first.md` | [OK] |
| `feedback_no_dead_params.md` | [OK] |
| `feedback_position_sizing.md` | [OK] |
| `feedback_pushback.md` | [OK] |
| `feedback_qa_audit_strategy.md` | [OK] |
| `feedback_risk_changes_scoped.md` | [OK] |
| `feedback_role_definition.md` | [OK] |
| `feedback_rust_authoritative_config.md` | [OK] |
| `feedback_subagent_code_writing_refusal.md` | [OK] |
| `feedback_subagent_first.md` | [OK] |
| `feedback_workflow_e2_e4_mandatory.md` | [OK] |
| `feedback_working_principles.md` | [OK] |
| `reference_remote_access.md` | [OK] |
| `reference_restart_script.md` | [OK] |

### 5.2 歸檔目錄

| 引用 | 狀態 |
|------|------|
| `archive/project_batch9_decisions.md` | [OK] |
| `archive/project_gui_upgrade_plan.md` | [OK] |
| `archive/project_local_strategy_plan.md` | [OK] |
| `archive/project_openclaw_deep_analysis.md` | [OK] |
| `archive/project_rust_cutover_decision.md` | [OK] |
| `archive/project_rust_migration_status.md` | [OK] |

**結論**：全部 29 個活躍記憶文件 + 6 個歸檔文件均存在，無過時條目。

---

## 六、其他索引文件驗證

### 6.1 docs/CCAgentWorkSpace/README.md

| 項目 | 狀態 |
|------|------|
| Agent 目錄索引 | [OK] 列出所有 Agent |
| 使用規範 | [OK] |

### 6.2 docs/execution_plan/README.md

| 項目 | 狀態 |
|------|------|
| 目錄存在，含 11 個文件 | [OK] 但 docs/README.md 未索引此子目錄 |

### 6.3 docs/rust_migration/README.md

| 項目 | 狀態 |
|------|------|
| 目錄存在，含 9 個文件 | [OK] 但 docs/README.md 未索引此子目錄 |

---

## 七、問題總結

### 嚴重度分級

#### P1（索引缺失 — 文件存在但未被任何索引收錄）

1. **docs/README.md 缺失 `docs/archive/` 目錄**（7 個歸檔文件完全無索引）
2. **docs/README.md 缺失 `docs/execution_plan/` 目錄**（11 個文件）
3. **docs/README.md 缺失 `docs/rust_migration/` 目錄**（9 個文件）
4. **docs/README.md 缺失 `docs/KNOWN_ISSUES.md`**
5. **helper_scripts/SCRIPT_INDEX.md 覆蓋率 ~11%**：缺失 canary/（6）、phase4/（3）、maintenance_scripts/（~60）

#### P2（索引落後 — 近期文件未及時更新）

6. **docs/README.md worklogs/ 頂層缺 3 個文件**：04-11 daily_summary + 04-12 兩份 worklog
7. **docs/README.md audits/ 缺 2 個文件**：04-11 兩份 3E-ARCH 審計報告
8. **docs/README.md references/ 缺 7 個文件**：04-06~04-11 期間新增
9. **docs/README.md CCAgentWorkSpace 表缺 QC 和 Operator**
10. **CLAUDE_CHANGELOG.md 缺 6 個功能 commit**（04-12 日較晚的 commit）

#### P3（過時/不準確）

11. **CLAUDE_REFERENCE.md 文件名修正表過時**：3 個「當前正確名」的 .py 文件已被 DEAD-PY-2 刪除
12. **CLAUDE_REFERENCE.md 最後更新日期 04-06**，實際截至今仍未更新

### 數字總結

| 指標 | 數值 |
|------|------|
| 總檢查條目 | ~250+ |
| [OK] | ~225 |
| [MISSING] 未索引 | ~25 |
| [STALE] 過時 | 4 |
| Memory 索引健康度 | 100%（35/35 全部有效） |
| docs/README.md 健康度 | ~90%（主體準確，近期更新落後 + 3 目錄未索引） |
| SCRIPT_INDEX 健康度 | ~11%（嚴重落後） |
| CLAUDE_REFERENCE.md 健康度 | ~95%（僅文件名修正表過時） |
| CLAUDE_CHANGELOG.md 健康度 | ~90%（最新 6 commit 未記錄） |

---

## 八、建議優先修復順序

1. **helper_scripts/SCRIPT_INDEX.md** — 補充 canary/、phase4/、maintenance_scripts/ 子目錄（P1）
2. **docs/README.md** — 新增 archive/、execution_plan/、rust_migration/ 三個子目錄的索引段落（P1）
3. **docs/README.md** — 補充近期（04-11/04-12）的 worklogs、audits、references 條目（P2）
4. **docs/README.md** — CCAgentWorkSpace 表補充 QC 和 Operator（P2）
5. **CLAUDE_REFERENCE.md** — 文件名修正表標記為歷史（DEAD-PY-2 已刪源文件）（P3）
6. **CLAUDE_CHANGELOG.md** — 補充 04-12 日 6 個未記錄 commit（P2）


---

# 14. A3 — GUI 可用性審計

> 原始文件：`docs/CCAgentWorkSpace/A3/2026-04-12--gui_usability_audit_report.md`

# A3 GUI 可用性審計報告 / GUI Usability Audit Report

**審計日期：** 2026-04-12
**審計範圍：** 全部 22 個 HTML 文件 + 3 個 JS 文件（app.js / common.js / governance.js）
**GUI 基礎路徑：** `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/`
**嚴重度定義：** [CRITICAL] 導致功能失效或安全問題 / [MAJOR] 嚴重影響用戶體驗 / [MINOR] 可改進項 / [SUGGESTION] 優化建議

---

## 一、死按鈕檢測 / Dead Button Detection

### 1.1 所有 onclick handler 驗證結果

**結論：所有 onclick handler 均有對應的 JavaScript function 定義。** 經過完整交叉比對（~100 個唯一 onclick 函數名 vs JS/HTML 中的 function 定義），未發現「按鈕指向不存在函數」的死按鈕。

### 1.2 功能性死按鈕（函數存在但功能無效）

**[MAJOR] index.html:38-45 — 隱藏的 Bearer Token 面板殘留**
- `tokenInput` 和 `connectButton` 被隱藏（`display:none`），但 `app.js:2164` 仍在 DOMContentLoaded 時自動 `click()` 這個隱藏按鈕
- `app.js:2167-2178` 的 connectButton click handler 仍會讀取已隱藏的 `tokenInput.value`
- 影響：不影響功能（cookie auth 自動生效），但造成 console 中的 DOM 操作浪費
- 建議：移除 `app.js` 中對 `connectButton`/`tokenInput` 的全部引用，改為直接調用 `loadDashboard()`

**[MAJOR] tab-risk.html:440 — AI 止損建議「採納」按鈕永久 disabled**
- `btn-apply-ai` 按鈕標註「開發中」且 `disabled`
- `applyAIAdvice()` 函數只顯示一個 toast 提示用戶手動調整
- 影響：用戶可能期望此功能可用，看到 disabled 按鈕會困惑
- 建議：要嗎移除此按鈕，要嗎在 AI 返回建議後啟用並自動填充左側表單欄位

**[MINOR] tab-system.html:82-91 — 三個 Quick Action 按鈕標記為只讀**
- `qa-demo`、`qa-feed`、`qa-scanner` 三個按鈕使用 `disabled` + `cursor:not-allowed` + `(只读/RO)` 標記
- 處理方式正確（不會誤導用戶點擊），但佔用了大量水平空間卻無法交互
- 建議：改為小型狀態指示器（純狀態 badge），不使用按鈕樣式

**[MINOR] tab-system.html:77 — Paper Quick Action 缺少 session 狀態感知**
- `qa-paper` 按鈕始終可點擊，但如果 Paper session 已在運行，點擊 `confirmAction('paper')` 會嘗試重複啟動
- 建議：根據 session 狀態動態切換為 Start/Stop，或在 session 活躍時 disable

### 1.3 API 端點驗證

**[MINOR] index.html 的 data-action 按鈕群（enable-spot、arm-demo 等）**
- 這些按鈕（第 148-151 行）調用的 API 端點（`/api/v1/control/demo/`, `/api/v1/control/product-family/`）是舊版 Control Plane API
- 功能上可用，但 index.html 本身作為 entry page 已被 console.html 取代，用戶不太可能直接訪問
- 建議：如果 index.html 不再作為主要入口，考慮重定向到 /console 或標註為 legacy

---

## 二、設計不合理 / Design Issues

### 2.1 頁面結構與導航

**[MAJOR] console.html 雙重導航（Tab Bar + Sidebar Nav Grid）**
- 頂部 Tab Bar 和側邊欄 Navigation Grid 完全重複，均包含相同的 11 個 tab
- 這兩套導航指向相同的 `switchTo()` 函數，功能完全一致
- 影響：浪費了寶貴的側邊欄空間，增加認知負擔
- 建議：側邊欄保留為「狀態面板」，移除 `nav-grid` 導航按鈕區域，釋放空間顯示更多即時狀態信息

**[MAJOR] tab-trading.html 雙層 iframe 嵌套**
- console.html 把每個 tab 加載為 iframe，tab-trading.html 自身又包含兩個 iframe（tab-demo.html、tab-paper.html）
- 造成三層 DOM 嵌套：console → tab-trading → tab-demo/tab-paper
- 影響：(a) 性能開銷；(b) CSS 變量需要三重注入；(c) 貨幣切換需要跨 iframe storage 事件傳播
- 建議：長期重構為 SPA 架構（或至少消除內層 iframe），短期可考慮將 tab-trading 改為直接切換 DOM section

**[MINOR] Charts tab 指向 `/trading`（trading.html）**
- console.html:239 中 Charts tab 的 src 是 `/trading`（657 行的獨立完整頁面含 K 線圖表）
- trading.html 有自己的 header、sidebar，作為 iframe 嵌入時產生二重 header
- 建議：為 iframe 嵌入場景提供無 header 版本（如 `?embed=1` 查詢參數隱藏 header）

### 2.2 載入狀態 / Loading States

**[MAJOR] 大部分 tab 缺少全局載入失敗狀態**
- 多數 tab 的 `loadAll()` 函數在 API 失敗時只是靜默保留 `--` 或 `Loading...` 文本
- 用戶無法區分「正在載入」和「載入失敗」
- 範例：tab-learning.html 的 `loadOverview()` 失敗時，6 個 metric 永遠顯示 `--`
- 建議：(a) 設定 5-10s timeout 後顯示「連接失敗，請檢查引擎狀態」提示；(b) 區分「載入中（動畫）」、「無數據」、「連接失敗（紅色提示 + 重試按鈕）」三種狀態

**[MINOR] tab-live.html 手動刷新間隔不夠靈活**
- Live tab 使用 30s `setInterval` 刷新，對實盤交易來說偏慢
- tab-demo.html 和 tab-paper.html 都是 15s
- 建議：Live tab 刷新間隔降為 10-15s，尤其是持倉和 PnL 數據

### 2.3 信息架構

**[MAJOR] tab-risk.html 信息過載（1390 行）**
- 一個 tab 內包含：Risk Status、Risk Governor、Per-Engine Config、P0/P1/P2 三層配置、Stop Manager（8 個參數）、Position Sizing（6 個參數）、Loss Cooldown、H0 Gate、Dynamic Adjustment、AI 止損建議、AI Risk Context、AI Budget、Danger Zone
- 用戶需要滾動很長才能找到目標設置
- 建議：將 Risk tab 拆分為「Risk Monitor（只讀狀態）」和「Risk Config（可編輯設置）」兩個子 tab

**[MAJOR] tab-governance.html 超大文件（2047 行）**
- 包含 11 個 modal dialog + 大量內聯 JS + HTML
- 違反 CLAUDE.md §九「1200 行硬上限」
- 建議：(a) 將 modal 提取為獨立組件；(b) 將 JS 邏輯拆入 governance.js（當前 governance.js 僅 237 行）

**[MINOR] Live、Demo、Paper 三個 Tab 之間的功能高度重複**
- 三者都有：Account Balance 卡片、PnL Overview、Positions 表格、Fill History、Performance Metrics
- 佈局和欄位幾乎相同，但 CSS class 命名不一致（Paper 用 `oc-metric`，Live 用 `live-metric`）
- 建議：提取共用的 Position/PnL/Fill 組件，三個 tab 引用同一組件 + 配置差異

---

## 三、不清楚的地方 / Unclear UI Elements

### 3.1 缺少 Tooltip 的重要控件

**[MAJOR] tab-risk.html — Position Sizing 中 "P1 Per-Trade Risk" 易混淆**
- 「P1 Per-Trade Risk」這個標籤暗示它是 P1 級別的硬限制（第 254 行），但實際它是可調整的軟參數
- P0/P1/P2 三級架構中，P1 = Global Limits（不可被 AI 覆蓋），但此欄位的實際行為更接近 P2
- 建議：改名為「Per-Trade Risk Budget / 單筆風險預算」，去掉 P1 前綴以免混淆

**[MAJOR] tab-risk.html — ATR Multiplier 含義不直觀**
- 第 210 行：「ATR 止損乘數…設為 0 則禁用 ATR 止損，使用固定百分比。值越大止損越遠」
- 缺少具體數值範例，用戶難以理解 2.0x 和 3.0x 的實際差距
- 建議：在描述中加入範例——「例：BTC ATR=500 USDT 時，2.0x = 距開倉價 1000 USDT 止損」

**[MINOR] tab-risk.html — 三引擎 Tab 選擇器缺乏視覺區分**
- Paper/Demo/Live 三個引擎 tab 按鈕（第 114-125 行）使用相同大小的 `oc-btn`，僅靠顏色深淺區分
- Live 按鈕在未選中時 `opacity:0.55`，與 disabled 狀態視覺相似
- 建議：Live 按鈕使用紅色邊框 + 專用 icon，確保任何時候都能一眼區分

### 3.2 狀態指示器缺少圖例

**[MINOR] tab-system.html — mode-btn-grid 的模式含義**
- `design_only`、`observe_only`、`shadow_only`、`demo_reserved`、`live_reserved` 五個模式
- 雖然每個按鈕有中文描述，但它們之間的關係和升級路徑不夠直觀
- 建議：在模式按鈕區域上方加入一個簡單的流程箭頭圖：設計 → 觀察 → 影子 → Demo → 實盤

**[MINOR] console.html 側邊欄 — Live vs Paper 面板切換不直觀**
- 點擊 Live 面板會切換到 Paper 面板（toggle 行為），違反直覺——用戶可能期望點擊 Live 就看 Live
- 底部的兩個小圓點（`dot-live`、`dot-paper`）是唯一的狀態指示，但太小且無文字標籤
- 建議：改為兩個明確的 tab 按鈕「Live | Paper」，點擊即顯示對應面板（非 toggle）

### 3.3 縮寫說明不足

**[MINOR] 多處使用的縮寫缺少解釋**
- `UPL`（Unrealized Profit/Loss）：console.html:410 使用但無展開
- `ATR`（Average True Range）：tab-risk.html 多處使用
- `H0 Gate`：非標準術語，首次接觸的用戶不知道 H0 是什麼
- `SM-01/SM-02/SM-04/EX-04`：tab-governance.html 使用但無鏈接到解釋
- 建議：為專業術語加上 `title` tooltip 或首次出現時括號展開

---

## 四、可優化的地方 / Optimization Opportunities

### 4.1 冗餘信息顯示

**[MINOR] console.html 側邊欄 — 貨幣切換出現兩次**
- Header 中有一個 `oc-curr-badge`（第 103 行），側邊欄又有一個（第 174 行）
- 功能完全相同，佔用空間
- 建議：保留 header 中的即可，側邊欄的可移除

**[MINOR] tab-risk.html — 止損設置左右雙欄佈局**
- 左側為可編輯輸入框，右側為「當前生效值」只讀顯示（第 231-242 行）
- 但輸入框在頁面載入時已經填入當前值，右側顯示重複
- 建議：改為「修改前/修改後」diff 對比模式——只有用戶修改了值時才顯示差異

### 4.2 缺少自動刷新的地方

**[MINOR] tab-phase4.html — 30s 刷新間隔，卡片內容更新不夠即時**
- Phase 4 Teacher/LinUCB/News/DL3 四個卡片使用 30s 刷新
- 對於新聞管線（News Pipeline）和 DL3，30s 足夠
- 但 Teacher Session 狀態在 session 運行中變化較快
- 建議：Teacher 卡片在 session 活躍時降為 10s 刷新

### 4.3 移動端響應性

**[MAJOR] 大部分 tab 缺少移動端適配**
- console.html 的 `@media (max-width: 860px)` 只是隱藏了 sidebar，但 tab 內容未做響應式
- tab-risk.html 的 `oc-grid-2`/`oc-grid-3` 使用 CSS Grid 有基本響應，但表單在窄屏幕上仍需水平滾動
- tab-live.html 的 positions 表格 9 列在手機上溢出
- 建議：(a) 表格在窄屏使用卡片式佈局（每行變成一張卡片）；(b) 核心操作按鈕固定在底部

### 4.4 數據可視化

**[SUGGESTION] 全系統缺少趨勢圖表**
- PnL 數據僅以數字展示，缺少折線圖/面積圖顯示歷史趨勢
- 持倉/策略狀態缺少時間線視覺化
- trading.html 中已引入 `lightweight-charts`，但其他 tab 未使用
- 建議：在 Paper/Demo/Live tab 的 PnL Overview 區域加入一個小型嵌入式 PnL 趨勢圖（使用已有的 lightweight-charts）

**[SUGGESTION] tab-strategy.html — 策略健康度缺少一覽式指標**
- 策略列表以卡片形式展示，但缺少「系統整體策略健康度」的彙總視圖
- 建議：在頂部加入一行策略分佈餅圖（active/paused/stopped 比例）

---

## 五、反人類設計 / Anti-patterns

### 5.1 危險操作確認機制審計

**[CRITICAL] tab-risk.html:501 — Danger Zone 的「Reset Loss Cooldown」和「Unhalt Session」使用原生 `confirm()` 而非自定義 modal**
- 這兩個操作會：(a) 重置連續虧損保護（允許繼續交易）；(b) 解除熔斷暫停
- 原生 `confirm()` 太簡單，只有 OK/Cancel，無法展示風險説明
- 同一頁面的 Live Engine Risk Config 修改有完善的自定義 modal（第 134-150 行），標準不一致
- 建議：改用與 Live 引擎相同等級的自定義 modal，展示：(a) 當前回撤/虧損狀態 (b) 恢復交易的風險評估 (c) 要求輸入原因

**[CRITICAL] tab-strategy.html:223 — 策略刪除使用原生 `confirm()`**
- 刪除策略是不可逆操作（按鈕標註「永久删除策略（不可撤销）」）
- 但確認方式僅為原生 `confirm()`，沒有二次確認或輸入策略名稱驗證
- 建議：使用自定義 modal，要求用戶輸入策略名稱才能確認刪除（類似 GitHub 刪除 repo 的模式）

**[MAJOR] tab-paper.html:352/365 — Paper 單筆/全部平倉使用原生 `confirm()`**
- Paper 雖然不涉及真實資金，但批量平倉影響策略運行
- 相比之下，Live tab 的平倉（tab-live.html:397-410）使用了完善的自定義 dialog
- 標準不一致
- 建議：統一所有平倉操作為自定義 dialog

### 5.2 不可逆操作警告不足

**[MAJOR] tab-settings.html:95 — 「計劃重啟服務器」多步驟 modal 設計良好，但缺少倒計時可視化**
- 重啟後 10-30 秒內無法監控市場、執行止損
- 雖然有延遲選擇（5/10/15/30/60 分鐘），但一旦確認後用戶無法知道何時重啟
- 建議：確認後在 Settings tab 頂部顯示倒計時橫幅，允許取消計劃重啟

### 5.3 反直覺的控件放置

**[MAJOR] tab-risk.html — 「保存」按鈕位置不一致**
- Stop Manager 的「保存止損設置」按鈕在左側欄底部（第 225 行）
- Position Sizing 的「保存仓位设置」按鈕在右側欄底部（第 318 行）
- 使用者必須分別保存兩組設置，可能遺漏其中一組
- 建議：(a) 在頁面底部加入統一的「Save All Risk Config」按鈕；(b) 或在用戶修改任何欄位後顯示浮動的「有未保存的修改」提醒條

**[MINOR] tab-live.html — 緊急停止按鈕與普通停止按鈕並排**
- `btn-live-start`、`btn-live-stop`、`btn-emergency-stop` 三個按鈕在同一行（第 207-209 行）
- 緊急停止按鈕（紅色）太容易被誤觸，特別是在緊張時
- 建議：緊急停止按鈕移到頁面底部的獨立區域，或增加物理隔離（與普通按鈕至少 40px 間距）

### 5.4 信息過載

**[MAJOR] tab-governance.html — 7 個可折疊區域 + 4 個卡片 + 6 個 modal**
- 首次打開此頁的用戶面臨：Authorization、Risk Governor、Decision Leases、Reconciliation、Paper→Live Gate、Learning Tier、Events Feed、Governance Summary、Incident Timeline、Pending Approvals、Audit Trail
- 大量資訊同時呈現，缺少引導
- 建議：(a) 默認只展示 Authorization + Risk Governor 兩個核心卡片，其餘摺疊；(b) 加入「快速狀態」頂部橫幅：一行文字總結治理健康狀態

---

## 六、跨 Tab 一致性問題 / Cross-Tab Consistency

### 6.1 CSS Class 命名不一致

**[MINOR] 三套不同的 metric 樣式系統**
- `oc-metric` / `oc-metric-val`：大部分 tab 使用（tab-risk, tab-governance 等）
- `live-metric` / `live-metric-val`：tab-live.html 獨用（第 62-81 行）
- `mc` / `mc-val`：console.html sidebar 獨用（第 45-49 行）
- 建議：統一為單一 metric 組件系統，live 特殊主題通過 modifier class 實現

### 6.2 自動刷新間隔不一致

**[MINOR] 各 tab 刷新間隔差異大且無文檔說明**
| Tab | 間隔 | 合理性 |
|-----|------|--------|
| tab-governance | 10s | 合理（事件驅動） |
| tab-paper/demo/risk/strategy/system/monitoring | 15s | 合理 |
| tab-trading | 20s (checkUnifiedStatus) | 偏慢 |
| tab-ai/learning/settings/phase4/live | 30s | Live 偏慢 |

建議：Live tab 改為 10-15s

### 6.3 雙語標籤風格不一致

**[MINOR] 部分 tab 使用「中文 / English」格式，部分只有中文或只有英文**
- tab-live.html：大部分用中文（「持倉 / Positions」、「掛單 / Open Orders」）
- tab-strategy.html：部分只有英文（「Score」、「Reason」、「State」）
- tab-governance.html：混合（「Authorization / 授权」但 table header 純英文）
- 建議：統一為「中文 / English」格式，至少 section 標題層級保持一致

---

## 七、安全相關 UI 問題 / Security-Related UI Issues

**[MINOR] login.html:54 — OpenClaw Gateway 鏈接硬編碼為 Tailscale 域名**
- `https://trade-core.tail358794.ts.net` 是內部 Tailscale 地址
- 違反 CLAUDE.md §七「路徑不硬編碼」原則
- 建議：移除此鏈接或改為相對路徑 `/openclaw/`

**[MINOR] tab-ai.html — API Key 輸入框**
- 六個 AI provider 的 API key 輸入框（第 72-137 行）使用 `type="password"`，保護良好
- 但保存後的狀態 badge（「已配置」/「未配置」）不顯示 key 是否真的有效
- 建議：保存後立即驗證（至少檢查格式），並顯示「已驗證 / 格式錯誤 / 未驗證」狀態

---

## 八、文件大小違規 / File Size Violations

| 文件 | 行數 | 違規 |
|------|------|------|
| app.js | 2608 | **嚴重超標**（硬上限 1200） |
| tab-governance.html | 2047 | **嚴重超標**（硬上限 1200） |
| tab-risk.html | 1390 | **超標**（硬上限 1200） |
| tab-live.html | 1026 | **超警告線**（警告線 800） |
| tab-settings.html | 857 | **超警告線**（警告線 800） |
| tab-system.html | 805 | **超警告線**（警告線 800） |

**建議優先拆分方案：**
1. `app.js` → 拆為 `app-core.js`（連接/渲染）+ `app-actions.js`（按鈕動作）+ `app-config.js`（產品族配置）
2. `tab-governance.html` → 拆出 modal dialog 到獨立文件 + JS 搬入 governance.js
3. `tab-risk.html` → 拆為 `tab-risk-monitor.html`（只讀）+ `tab-risk-config.html`（可編輯）

---

## 九、總結 / Summary

### 嚴重度分佈

| 級別 | 數量 | 說明 |
|------|------|------|
| CRITICAL | 2 | Danger Zone/策略刪除使用原生 confirm() |
| MAJOR | 14 | 設計、信息架構、一致性、響應式 |
| MINOR | 18 | 標籤、tooltip、命名、冗餘 |
| SUGGESTION | 2 | 趨勢圖表、策略健康度 |

### 優先修復建議

1. **P0（立即）**：Danger Zone 操作改用自定義 modal + 策略刪除加輸入確認
2. **P1（本周）**：移除 index.html/app.js 中的 connectButton 死代碼 + 統一平倉確認機制
3. **P2（下兩周）**：文件拆分（app.js + tab-governance.html + tab-risk.html）
4. **P3（長期）**：CSS 組件統一 + 響應式適配 + PnL 趨勢圖表 + SPA 重構消除 iframe 嵌套

---

*審計人：A3 (UX/GUI Auditor)*
*審計方法：靜態代碼分析（全量 onclick 交叉比對、API 端點驗證、CSS 一致性檢查、文件行數統計）*

--- END OF AUDIT ---
