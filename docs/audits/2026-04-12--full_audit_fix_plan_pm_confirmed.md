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
