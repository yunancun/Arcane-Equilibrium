# Wave 5 最終派發計劃（PM+PA+FA+CC 四方合議）

**日期**：2026-03-31
**CC 評級**：條件通過（Sprint 0 兩個 BLOCKER 修復後啟動）
**Wave 5 目標**：2600+ tests，業務完整度 32% → ~45%

---

## 兩個 BLOCKER（Sprint 0，並行執行）

### G-05【原則 3 硬違反】executor_agent.py 缺少 acquire_lease()
- 位置：`executor_agent.py` `execute_order()` 第 281 行
- 修復：`__init__()` 新增 `governance_hub` 參數；`execute_order()` 插入 `acquire_lease()` fail-closed 邏輯
- 指派：E1-Alpha（2h）

### G-01【DOC-08 §12 安全不變量】每日硬上限 $15.0 → $2.0
- 位置：`layer2_types.py:58` + `tab-ai.html:335/426/441` + `tests/test_layer2.py:201`
- 修復：5 處改值，layer2_types DEFAULT_DAILY_HARD_CAP_USD = 2.0
- 指派：E1-Beta（1h）

---

## Sprint 結構

### Sprint 0（~6h 含 E2+E4）

```
E1-Alpha: G-05（2h）‖ E1-Beta: G-01（1h）
  ↓ 均完成
E2 審查（1.5h）→ E4 回歸（1.5h）
目標：≥ 2555 tests
```

### Sprint 5a（~15h 含 E2+E4）

```
E1-Alpha: 5a-1 Scout intel 鏈路確認（1.5h）
         5a-2 H0 Gate warn-only→blocking（1h）
         5a-4 Strategist shadow=False 驗證（1.5h）

E1-Beta:  5a-3 H1 ThoughtGate MVP（3h）
         5a-5 H2 預算門控接入（1.5h）
         5a-6 H3 ModelRouter 路由（2h）

（完全並行）↓ 均完成
E2 審查（2h）→ E4 回歸（2h）
目標：≥ 2575 tests
```

### Sprint 5b（~13h 含 E2+E4）

```
E1-Gamma: 5b-1 H4 輸出驗證（1.5h）
         5b-2/6 H5 CostLogger + ROI disclaimer（2.5h）

E1-Delta: 5b-3 apply_ai_consultation 替換（2h）
         5b-4 ScoutWorker 後台線程（3h）

E4 直接:  5b-5 原則 14 集成測試（1.5h）

（完全並行）↓ 均完成
E2 審查（1.5h）→ E4 回歸（2h）
目標：≥ 2600 tests
```

---

## CC 強制執行要求

1. H1 Ollama 超時 → 走 `_heuristic_evaluate()`，不可 allow-all（原則 6）
2. Sprint 5b 所有 AI ROI API 回應加 `roi_basis: "paper_simulation_only"`（原則 10）
3. Sprint 5b 後 E4 補充 Mock Ollama 崩潰全流程測試（原則 14）

---

## PA 架構警示

- ExecutorAgent 注入 governance_hub 後，所有初始化調用點必須同步更新（phase2_strategy_routes.py + 測試文件）
- H1 Ollama 調用：`_handle_intel()` 是同步方法（MessageBus 回調），不可用 await，使用同步 HTTP 或 threading.Thread
- B-MVP-1（Scout→bus.send）已確認代碼存在，5a-1 是追蹤確認而非重新實現

---

## 工時總計

| Sprint | E1 工時 | 含 E2+E4 | 測試目標 |
|--------|---------|---------|---------|
| Sprint 0 | 3h | ~6h | ≥ 2555 |
| Sprint 5a | ~10.5h | ~15h | ≥ 2575 |
| Sprint 5b | ~9.5h | ~13h | ≥ 2600 |
| **Wave 5 合計** | **~23h** | **~34h** | **≥ 2600** |
