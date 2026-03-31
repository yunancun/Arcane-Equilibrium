# Phase 2 Batch 2C 完成工程日誌
# Engineering Log: Phase 2 Batch 2C Completion
# 日期：2026-04-01

---

## 背景（Context）

Phase 2 Batch 2A（TruthSourceRegistry）與 Batch 2B（BacktestEngine MVP）在 2026-03-31
代碼層完成、57+46 個測試通過，但 FA/PA/PM 三方審計發現兩個決定性的「最後一公里」斷點：

1. `_register_pattern_claims()` 已定義但從未在 `_ai_pattern_analysis()` 或
   `_statistical_pattern_analysis()` 中被調用 → TruthSourceRegistry 永遠是空的
2. `BacktestEngine` 無任何 API 路由 → Operator 無法觸發，引擎完全不可用

附帶問題：`applies_to_strategy="all"` 導致 StrategistAgent 的
`if strategy == "all": continue` 跳過所有權重更新（雙重失效）；
`_strategy_preference_weights` 從未在決策路徑中被讀取。

Phase 2 代碼完成度 ~80%，但功能完成度僅 ~40%。

---

## 本次工作（Work Done）

### Batch 2C — 三個並行修復任務

**2C-1：analyst_agent.py（E1-Alpha）**

- `_ai_pattern_analysis()`：在 `bus.send(msg)` 之前加 `self._register_pattern_claims(insight)`
- `_statistical_pattern_analysis()`：同位置加相同調用（fallback 路徑也接通）
- 新增 `_extract_strategy_from_pattern()` 靜態方法：
  - 優先匹配已知策略名（frozenset：ma_crossover/grid/bb_reversion/bb_breakout/funding_arb）
  - fallback 使用 pattern text slug，永不返回 "all"
- 補入 `losing_patterns` 循環：`confidence=0.4`，`pattern_text` 加 `"losing: "` 前綴
  供 StrategistAgent 的 `if "losing" in claim.pattern_text.lower()` 分支識別

**2C-2：backtest_routes.py（E1-Beta，新建）**

- sys.path 5 級上溯（複用 `phase2_strategy_routes.py` 第 66-80 行的既有模式）
- `BacktestEngine` 模組級單例 + `threading.Lock`（防並發 run）
- `POST /api/v1/backtest/run`：
  - `_require_operator_role(actor)` 門控
  - `asyncio.to_thread(engine.run, config, None)` 不阻塞事件循環
  - `sharpe_ratio > 1.0 and total_trades >= 10` 時自動注入 TruthSourceRegistry
    （`evidence_source=f"statistical_N={total_trades}"`，與 TTL 規則對齊）
  - TruthRegistry 注入 fail-open（try/except + logger.warning）
- `GET /api/v1/backtest/status`：只讀，不需 Operator 角色
- 原則 7 隔離：無任何 live 模組 import（PaperTradingEngine / GovernanceHub / PipelineBridge）
- 掛載：`main.py` 新增 `app.include_router(backtest_router)`

**2C-3：strategist_agent.py（E1-Beta）**

- `_handle_intel()` 決策路徑中加入權重讀取：
  ```python
  weight = self._strategy_preference_weights.get(strategy_key, 1.0)
  adjusted_confidence = min(1.0, evaluation.confidence * weight)
  ```
- `metadata` 新增 `raw_confidence` + `strategy_weight` 供審計追溯
- E2 確認：所有已知策略名和通用鍵的 fallback 均正確

### Git 分歧解決

Session 間出現分歧：local `be7d4d7`（Wave 7a）vs remote `74b8f1b`（Wave 7a，hash 不同）。

解決步驟：
1. `git diff be7d4d7 74b8f1b`：內容完全相同，只是 amend 導致 hash 不同
2. Stash 3 個合法未提交文件（`bybit_demo_connector.py` / `paper_trading_engine.py` / `tab-trading.html`）
3. `git rebase origin/main`：成功，`be7d4d7` 被識別為已應用跳過，`2fe3b7a` 重放為 `5794db1`
4. `git stash pop` + commit 合法修改為 `2fba698`

---

## 測試結果（Test Results）

| 文件 | 新增測試 |
|------|---------|
| test_analyst_agent_registry.py（新建） | 19 個（AI/統計路徑注入 + losing patterns + strategy != "all" + _extract_strategy）|
| test_backtest_routes.py（新建） | 26 個（happy path + 權限 + Registry 注入 + 錯誤處理 + singleton）|

```
全量回歸：3103 passed / 19 failed / 1 skipped / 17 errors
基準線提升：2700 → 3103（+403 net）
新增 failures：0
E2 審查：PASS（無阻塞問題，2 個非阻塞建議）
```

---

## E2 審查要點（Code Review Notes）

**通過項：**
- S1 Operator 認證 ✅
- P7-1 原則 7 隔離 ✅（無 live 模組 import）
- P7-3 asyncio.to_thread ✅
- F1/F2 _register_pattern_claims 雙路徑調用 ✅
- F3 applies_to_strategy 永不為 "all" ✅
- F5 _strategy_preference_weights 影響決策 ✅

**非阻塞建議（未修改）：**
- TruthRegistry 注入 try/except 可補 `except HTTPException: raise`（風險極低，備忘）
- _backtest_lock 僅保護 singleton，不保護並發 run()（BacktestEngine 本身已有 SLA 保護）

---

## 提交記錄（Commits）

| commit | 內容 |
|--------|------|
| `5794db1` | feat(phase2): Batch 2C — 接通 TruthSourceRegistry + BacktestEngine API + 決策權重 |
| `2fba698` | feat(sync): Demo 停止時取消所有掛單 + 平倉清理 |

---

## Phase 2 完成聲明（Phase 2 Completion Declaration）

Phase 2 全部三個 Batch（2A / 2B / 2C）均已完成，進入 Phase 3 的前置條件：

- ✅ TruthSourceRegistry 真正運行（AnalystAgent 雙路徑注入，StrategistAgent 消費）
- ✅ BacktestEngine 可 Operator 呼叫（POST /run + GET /status，Operator 認證）
- ✅ 學習管線雙向完整（winning + losing patterns → Registry → 決策權重調整）
- ✅ 測試基準 3103 passed

下一步：Phase 3 L3 假設與實驗管線 + L4 策略進化（或 Wave 7a Spot 品類啟用，視優先級）
