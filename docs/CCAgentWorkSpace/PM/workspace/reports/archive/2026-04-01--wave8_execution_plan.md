# PM 排程計劃 — Wave 8 修復排程
# 日期：2026-04-01
# 來源：PA 實況檢查報告（69 項交叉驗證 → 29 確認 + 10 部分修復 = 39 項待處理）

---

## 一、排程總覽

| Wave | 主題 | 項數 | 預估工時 | 建議時間 |
|------|------|------|---------|---------|
| Wave 8A | 安全+正確性 | 8 | ~11h | 本週（Week 1） |
| Wave 8B | 代碼質量+測試 | 15 | ~33.5h | Week 2-3 |
| Wave 8C | 架構改進 | 10 | ~28.5h | Week 3-4 |
| Wave 8D | 文檔清理 | 6 | ~1.25h | 隨時穿插 |
| **合計** | | **39** | **~74h** | **4 週** |

---

## 二、Wave 8A — 安全+正確性（本週，~11h）

> 影響正確性/安全性的項目。E2+E4 強制。

| # | 來源 | 問題 | 修復方式 | E1 指派 | 工時 |
|---|---|---|---|---|---|
| A1 | E4 | bybit_demo_sync.py 294 LOC 零測試 | 新建 test_bybit_demo_sync.py，覆蓋 sync/retry/error | E4 | 3h |
| A2 | E4 | grafana_data_writer.py 359 LOC 零測試 | 新建 test_grafana_data_writer.py，mock PG | E4 | 2h |
| A3 | E4 | 9 處 assert True 空斷言 | 替換為有意義的 assertEqual/assertIn | E4 | 1h |
| A4 | E3 | CORS allow_credentials=True（部分修復） | origin 白名單校驗 + 文檔化 | E1-Alpha | 1h |
| A5 | FA | executor_agent.py error=f"...{e}" 洩漏 | 固定字串 + server-side log | E1-Alpha | 30m |
| A6 | E3 | symbol 格式驗證不統一（部分修復） | 共用 _SYMBOL_PATTERN validator | E1-Beta | 1h |
| A7 | AI-E | cost_tracker 方法名不一致 | 統一為 record_call，全域替換 | E1-Beta | 30m |
| A8 | CC | MessageBus send() lock 內同步 callback | lock 內複製 list → lock 外調用 | E1-Gamma | 2h |

### Wave 8A 工作鏈
```
E4（A1+A2+A3）‖ E1-Alpha（A4+A5）‖ E1-Beta（A6+A7）‖ E1-Gamma（A8）— 4 路並行
  ↓ 全部完成
E2 代碼審查
  ↓
E4 全量回歸
  ↓
PM 確認 + commit: fix(quality): Wave 8A — 安全+正確性修復
```

---

## 三、Wave 8B — 代碼質量+測試（Week 2-3，~33.5h）

> 核心重複消除 + 測試覆蓋 + 前端統一。分兩個 Sprint。

### Sprint 8B-1：核心重複消除（~18h）

| # | 來源 | 問題 | 修復方式 | E1 指派 | 工時 |
|---|---|---|---|---|---|
| B1 | E5 #17 | now_ms() 11 定義 + 712 inline | 建立 utils/time_utils.py，全域替換 | E1-Alpha | 4h |
| B2 | E5 #16 | compile_state/stable_compile_state 重複 | 抽出共用 _do_compile() | E1-Beta | 2h |
| B3 | E5 #21 | on_tick 150 行 | 拆為子方法 | E1-Gamma | 2h |
| B4 | E5 R2/R3 | mutator 346+280 行 | 各拆 3-4 子函數 | E1-Delta | 4h |
| B5 | E5 #18 | verify_operator_identity 20 處 | decorator 或 middleware | E1-Alpha | 2h |
| B6 | E5 #28 | compile_state O(n) scans | dirty flag + memoize | E1-Beta | 2h |
| B7 | E5 #37 | trading.html 獨立 auth/API | 遷移至 common.js | E1a-Alpha | 2h |

### Sprint 8B-2：測試+前端統一（~15.5h）

| # | 來源 | 問題 | 修復方式 | E1 指派 | 工時 |
|---|---|---|---|---|---|
| B8 | E5 #35 | :root CSS 4 處 | 統一至 styles.css | E1a-Alpha | 1h |
| B9 | E5 #36 | getToken() 重複 stub | 刪除 deprecated stub | E1a-Alpha | 30m |
| B10 | E4 | phase2_strategy_routes 30% | 增加 40+ 測試 | E4 | 4h |
| B11 | E4 | WS 斷線 + stop-loss 未測試 | 整合測試 | E4 | 3h |
| B12 | E3 | tab-governance innerHTML（部分修復） | 審查剩餘 innerHTML | E1a-Beta | 1h |
| B13 | FA | Evolution→Deploy 循環斷開 | 輸出 best_params → deployer | E1-Gamma | 4h |
| B14 | FA | _ollama_stats 無觀測性 | log + /api/v1/ai/stats | E1-Delta | 1h |
| B15 | AI-E | ollama_client.is_available() 仍同步 | asyncio.to_thread 包裝 | E1-Delta | 1h |

### Wave 8B 工作鏈
```
Sprint 8B-1：
  E1-Alpha（B1+B5）‖ E1-Beta（B2+B6）‖ E1-Gamma（B3）‖ E1-Delta（B4）‖ E1a-Alpha（B7）
  → E2 → E4 → commit: refactor: Wave 8B Sprint 1 — 核心重複消除

Sprint 8B-2（Sprint 8B-1 完成後）：
  E1a-Alpha（B8+B9）‖ E4（B10+B11）‖ E1a-Beta（B12）‖ E1-Gamma（B13）‖ E1-Delta（B14+B15）
  → E2 → E4 → commit: feat: Wave 8B Sprint 2 — 測試+前端統一
```

**⚠️ 關鍵依賴：B1（now_ms 統一）應在 B3/B4/B5 前完成，避免新代碼引入 inline pattern。**

---

## 四、Wave 8C — 架構改進（Week 3-4，~28.5h）

> 新功能型需求 + 架構拆分。

| # | 來源 | 問題 | 修復方式 | E1 指派 | 工時 |
|---|---|---|---|---|---|
| C1 | AI-E | strategist_agent.py 1068 行 | 拆為 core + h1 + h4 + l2 | E1-Alpha | 6h |
| C2 | FA | H3 ModelRouter 非獨立模組 | 抽出 model_router.py | E1-Alpha | 3h |
| C3 | CC | L5 meta-learning 未實現 | 設計 meta_learning_engine.py | E1-Beta | 8h |
| C4 | FA | Regime-aware 策略選擇 | ThoughtGate regime→strategy 映射 | E1-Beta | 3h |
| C5 | AI-E | EvolutionEngine object.__setattr__ | 改為非 frozen 或 InitVar | E1-Gamma | 1h |
| C6 | AI-E | AnalystAgent L2 閾值 200 偏高 | 降為 50 + env 覆寫 | E1-Gamma | 30m |
| C7 | FA | Backtest equity_curve 過大 | downsample + 分頁 | E1-Gamma | 2h |
| C8 | CC | max_pending_intents 無壓力測試 | stress test 100 並發 | E4 | 2h |
| C9 | E4 | market_data_dispatcher 測試不足 | 專用測試文件 | E4 | 2h |
| C10 | E3 | requirements.txt 僅 7 項 | pip freeze + CI pip-audit | E1-Delta | 1h |

### Wave 8C 工作鏈
```
E1-Alpha（C1+C2）‖ E1-Beta（C3+C4）‖ E1-Gamma（C5+C6+C7）‖ E4（C8+C9）‖ E1-Delta（C10）
  → E2 → E4 → CC（C3 原則 12 驗收）
  → commit: feat: Wave 8C — 架構拆分+新功能

⚠️ C1+C2 可合併為一個 PR。
⚠️ C3 需先出設計文檔再編碼。
⚠️ B13 完成後 C4 效果更佳。
```

---

## 五、Wave 8D — 文檔清理（隨時穿插，~1.25h）

| # | 來源 | 問題 | 修復方式 | 指派 | 工時 |
|---|---|---|---|---|---|
| D1 | TW | COMPREHENSIVE_SPEC 100% 重複 | 刪除 + pointer | TW | 10m |
| D2 | TW | CLAUDE.md section 3 過長 | 歸檔至 archive/ | TW | 20m |
| D3 | R4 | 3/31 報告路徑不規範 | mv 至 workspace/reports/ | R4 | 10m |
| D4 | R4 | .DS_Store 殘留 | git rm --cached + .gitignore | R4 | 5m |
| D5 | R4 | decisions/ .docx 索引不完整 | 逐一核對補齊 | R4 | 30m |
| D6 | E5 | _write_audit_fields 重複 | 與 B5 合併處理 | -- | -- |

---

## 六、風險提示

1. **B1 全域替換 now_ms（712 處）** — 影響面最大，建議分批 PR + CI 全量測試
2. **C3 L5 meta-learning** — 全新功能，需先 FA 功能規格 + PA 技術方案
3. **B4 mutator 拆分** — paper_trading_engine 核心路徑，需增量式重構
4. **C1 strategist 拆分** — 1068 行拆 4 文件，需確保 H1-H4 路徑不斷裂

---

## 七、建議排程

```
Week 1:  Wave 8A (11h) + Wave 8D (1.25h)
Week 2:  Sprint 8B-1 (18h)
Week 3:  Sprint 8B-2 (15.5h)
Week 4:  Wave 8C (28.5h)
```

---

PM 簽核：2026-04-01
