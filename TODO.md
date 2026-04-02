# OpenClaw TODO — 工作計劃清單
# 最後更新：2026-04-02（Batch 9A 確定性自適應風控完成 · 3703 tests）
# 注意：compact 後從此文件恢復工作狀態

---

## 強制工作流程（每 Wave 必須遵守）

```
任何修復/功能 → E1/E1a 並行執行 → E2 代碼審查（必須）→ E4 全量回歸（必須）→ PM 確認 → commit
緊急通道（P0）：跳過 FA/A3/R4，但 E2+E4 絕對不可跳過
最大並行：5 個 E1 Agent 同時修不同文件
15 角色定義詳見 CLAUDE.md §十三
```

---

## 當前測試基準線

```
3703 passed / 24 failed / 17 errors（pre-existing failures 不影響本工作）
路徑：program_code/exchange_connectors/bybit_connector/control_api_v1/ + program_code/local_model_tools/
命令：python3 -m pytest --ignore=database_files -q --tb=no
```

---

## 已完成項目歸檔

所有 Wave 0-7 / Phase 1-3 / April 1 Audit Batch 1-7 / main_legacy 重構 Wave A-D 的完成記錄已歸檔：
→ `docs/worklogs/control_api_gui/2026-04-01--completed_todo_archive.md`

PA 實況檢查報告：
→ `docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-01--reality_check_audit_verification.md`

PM 排程計劃：
→ `docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-01--wave8_execution_plan.md`

---

## ██ Batch 9A — 確定性自適應風控（QC 量化審查驅動，~9h）

> QC 審查報告驅動。確定性適應立即做，統計適應暫緩。E2+E4 強制。

### [x] U-03：追蹤止損利潤約束（QC M1，P0）
- **檔案**：`app/risk_manager.py`（+24 行）
- **修復**：`activation - distance > c_round_pct × 1.5` 約束，自動提高 activation
- **測試**：12 個新測試（`test_trailing_stop_cost_constraint.py`）
- **E1 指派**：E1-Alpha
- ✅ 完成：commit d9b102f（2026-04-02）

### [x] U-04：成本感知入場門檻（QC M2，P0）
- **檔案**：新建 `cost_gate.py`（185 行）+ `pipeline_bridge.py`（+207 行注入）
- **修復**：ATR% < c_round/win_rate×1.3 → 拒絕開倉；fail-open + 每日安全閥
- **測試**：22 個新測試（`test_cost_gate.py`）
- **E1 指派**：E1-Beta
- ✅ 完成：commit d9b102f（2026-04-02）

### [x] U-05：動態參數寫入 round-trip 記錄（QC M4，P0）
- **檔案**：`pipeline_bridge.py` + `analyst_agent.py`
- **修復**：fees_paid 從硬編碼 0→真實值；新增 param_snapshot（ATR/stops/regime/confidence）
- **測試**：16 個新測試（`test_u05_round_trip_fees_params.py`）
- **E1 指派**：E1-Gamma
- ✅ 完成：commit d9b102f（2026-04-02）

### [x] U-09：ATR 快/慢雙窗口（QC S1，P1）
- **檔案**：`indicator_engine.py`（+71 行）+ `pipeline_bridge.py`（ATR 取值修復）
- **修復**：max(ATR_5, ATR_14) 保守估計；修復 ATR 止損死代碼 bug（key "atr" vs "ATR(14)"）
- **測試**：18 個新測試（`test_atr_dual_window.py`）
- **E1 指派**：E1-Delta
- ✅ 完成：commit d9b102f（2026-04-02）

---

## ██ Batch 9B — 學習閉環接通（P0，~8h）

> FA P0-GAP-1/2。業務完成度 52%→~65%。

### [ ] U-01：學習反饋閉環（FA P0-GAP-1）
- **檔案**：`app/strategist_agent.py`
- **修復**：`_apply_pattern_insight()` 接入決策路徑
- **工時**：4h
- **E1 指派**：E1-Alpha

### [ ] U-02：進化參數自動重部署（FA P0-GAP-2）
- **檔案**：`evolution_engine.py` + `strategy_auto_deployer.py`
- **修復**：EvolutionEngine best_params → Deployer；paper/demo 免確認（Operator 決策 2026-04-02）
- **工時**：4h
- **E1 指派**：E1-Beta

---

## ██ Batch 9C — 管線連通（P1，~6h）

### [ ] U-06：H0 Gate shadow 模式觀察（FA P1-GAP-3）
- **修復**：shadow 記錄 would-have-blocked 但不攔截，觀察 1 週後切 blocking（Operator 決策 2026-04-02）
- **工時**：1h

### [ ] U-07：Scanner→Deployer 自動接通（FA P1-GAP-5）
- **工時**：2h

### [ ] U-08：Backtest 生產環境啟用（FA P1-GAP-6）
- **工時**：2h

### [ ] U-15：L2 觸發門檻降低 50→20（FA P2-GAP-7）
- **工時**：1h

---

## ██ Batch 9D — 策略 Edge 驗證（P1，~15h）

### [ ] U-10：FundingRateArb 完整成本模型精算（QC S3）
- **修復**：QC 認定唯一有可論證 edge 的策略；精算手續費+滑點+funding rate+basis risk+持倉天數
- **工時**：6h

### [ ] U-11：交易所條件單 SL/TP（FA P1-GAP-4）
- **修復**：Bybit Demo 側掛 SL/TP 條件單（原則 9 雙重防線）
- **工時**：6h

### [ ] U-14：Kelly fraction 計算 + GUI 展示（QC S4）
- **修復**：讓 Operator 直觀看到策略是否值得交易；Agent 根據 Kelly 自動分配資本（Operator 決策 2026-04-02 選項 C）
- **工時**：3h

---

## ██ 延後項（P2-P3，數據積累後啟用）

### [ ] U-12：統計適應硬門檻（200+ trades/regime）
### [ ] U-13：參數空間 step 字段
### [ ] U-16：Walk-forward harness（BacktestEngine 擴展）
### [ ] U-17：Deflated Sharpe Ratio 自動計算
### [ ] U-18：Jump detection（K 線 body > 3σ → 加寬止損）

PM 排程計劃：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-02--adaptive_params_execution_plan.md`
FA 功能規格：`docs/CCAgentWorkSpace/FA/workspace/reports/2026-04-02--adaptive_params_functional_spec.md`
PA 技術方案：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-02--adaptive_params_technical_design.md`
QC 量化審查：`docs/CCAgentWorkSpace/QC/workspace/reports/2026-04-02--adaptive_params_architecture_review.md`

---

## ██ Wave 8A — 安全+正確性（已完成，~11h）

> PA 確認的影響正確性/安全性項目。E2+E4 強制。

### [x] A1：bybit_demo_sync.py 零測試覆蓋（E4 P1）
- **檔案**：`app/bybit_demo_sync.py`（294 LOC）
- **修復**：新建 `tests/test_bybit_demo_sync.py`，覆蓋 sync/retry/error path
- **來源**：E4 審計
- **工時**：3h
- **E1 指派**：E4

### [x] A2：grafana_data_writer.py 零測試覆蓋（E4 P2）
- **檔案**：`app/grafana_data_writer.py`（359 LOC）
- **修復**：新建 `tests/test_grafana_data_writer.py`，mock PostgreSQL 連線
- **來源**：E4 審計
- **工時**：2h
- **E1 指派**：E4

### [x] A3：9 處 assert True 空斷言（E4 P2）
- **檔案**：`tests/test_pipeline_bridge_coverage.py`（3 處）、`tests/test_risk_manager.py`（1 處）、`tests/test_scout_integration.py`（5 處）
- **修復**：替換為有意義的 assertEqual / assertIn / assert mock.called
- **來源**：E4 審計
- **工時**：1h
- **E1 指派**：E4

### [x] A4：CORS allow_credentials=True 安全加固（E3 HIGH，部分修復）
- **檔案**：`app/main_legacy.py`（CORS 配置，line 275-281）
- **現狀**：wildcard `*` 已在啟動時剔除，但 allow_credentials=True + 動態 origins 仍存在
- **修復**：添加啟動時 origin 白名單校驗 + 文檔化允許列表
- **來源**：E3 HIGH-LEGACY-1
- **工時**：1h
- **E1 指派**：E1-Alpha

### [x] A5：executor_agent.py 動態異常字串洩漏內部信息（FA P2）
- **檔案**：`app/executor_agent.py`（line 366, 415）
- **問題**：`error=f"Execution error: {e}"` 可能洩漏 Python 內部異常
- **修復**：改為固定字串 + server-side logger.error 記錄完整異常
- **來源**：FA FA-11
- **工時**：30m
- **E1 指派**：E1-Alpha

### [x] A6：symbol 欄位格式驗證不統一（E3 LOW，部分修復）
- **檔案**：`app/paper_trading_routes.py`、`app/backtest_routes.py`、`app/evolution_routes.py`、`app/layer2_routes.py`
- **現狀**：`phase2_strategy_routes.py` 有 `_SYMBOL_PATTERN` regex，其他 routes 僅 max_length
- **修復**：抽出共用 validator，應用至所有 route models
- **來源**：E3 LOW
- **工時**：1h
- **E1 指派**：E1-Beta

### [x] A7：cost_tracker 方法名不一致（AI-E P2）
- **檔案**：`app/strategist_agent.py`（line 441 `record_call` vs line 975 `record_ollama_call`）
- **修復**：統一為一個方法名，全域搜尋替換
- **來源**：AI-E P2-AI-3
- **工時**：30m
- **E1 指派**：E1-Beta

### [x] A8：MessageBus send() lock 內同步執行 subscriber callback（CC 確認）
- **檔案**：`app/multi_agent_framework.py`（lines 314-320）
- **問題**：所有 subscriber callback 在 `self._lock` 持有期間被調用，慢 handler 阻塞一切
- **修復**：lock 內複製 subscriber list → lock 外逐一調用，或改用 asyncio.Queue
- **來源**：CC 審計 + test_message_bus_load ISSUE-2
- **工時**：2h
- **E1 指派**：E1-Gamma

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

## ██ Wave 8B Sprint 1 — 核心重複消除（Week 2，~18h）

### [x] B1：now_ms() 11 處定義 + 712 處 inline（E5 #17，最嚴重重複）
- **問題**：11 個獨立 `def now_ms()` + 712 處 `int(time.time() * 1000)` inline
- **修復**：建立 `utils/time_utils.py` 導出 `now_ms()`，全域替換
- **⚠️ 影響面最大**：建議分批 PR + CI 全量測試
- **工時**：4h
- **E1 指派**：E1-Alpha

### [x] B2：compile_state / stable_compile_state ~124 行重複（E5 #16）
- **檔案**：`app/state_compiler.py`、`app/main.py`
- **修復**：抽出共用 `_do_compile(state)` 底層函數
- **工時**：2h
- **E1 指派**：E1-Beta

### [x] B3：on_tick 150 行過長（E5 #21）
- **檔案**：`app/pipeline_bridge.py:384-533`
- **修復**：拆為 `_tick_market_data()`、`_tick_strategies()`、`_tick_risk()` 等子方法
- **工時**：2h
- **E1 指派**：E1-Gamma

### [x] B4：submit_order.mutator 346 行 + tick.mutator 280 行（E5 NEW-R2/R3）
- **檔案**：`app/paper_trading_engine.py`
- **修復**：各拆為 3-4 個語義子函數
- **工時**：4h
- **E1 指派**：E1-Delta

### [x] B5：verify_operator_identity 20 處相同 pattern（E5 #18）
- **檔案**：`app/control_ops.py`（7）、`app/learning_records.py`（7）、`app/learning_auto_pipeline.py`（3）、`app/pnl_ops.py`（2）
- **修復**：抽出 decorator 或 middleware 統一處理
- **工時**：2h
- **E1 指派**：E1-Alpha

### [x] B6：compile_state 每次讀寫 3x O(n) list scan（E5 #28）
- **檔案**：`app/state_compiler.py:528-552`
- **修復**：加入快取機制（dirty flag + memoize），寫入時標記 dirty
- **工時**：2h
- **E1 指派**：E1-Beta

### [x] B7：trading.html 完全獨立 auth/API 實現（E5 #37）
- **檔案**：`app/static/trading.html`
- **修復**：遷移至 common.js 共用 ocApi()，刪除獨立 api() / getToken()
- **工時**：2h
- **E1 指派**：E1a-Alpha

---

## ██ Wave 8B Sprint 2 — 測試+前端統一（Week 3，~15.5h）

### [x] B8：:root CSS 變量 4 處重複定義（E5 #35）
- **修復**：統一至 styles.css，其他文件移除重複 :root
- **工時**：1h
- **E1 指派**：E1a-Alpha

### [x] B9：console.html getToken() 重複 stub（E5 #36，部分修復）
- **修復**：刪除 deprecated stub，統一由 common.js 處理
- **工時**：30m
- **E1 指派**：E1a-Alpha

### [x] B10：phase2_strategy_routes 30% 覆蓋率（E4 P2）
- **檔案**：`app/phase2_strategy_routes.py`（1625 LOC）
- **修復**：增加 40+ route 測試，覆蓋 error path + state transition
- **工時**：4h
- **E1 指派**：E4

### [x] B11：WS 斷線 + stop-loss 交互未測試（E4 P1）
- **修復**：新建整合測試模擬 WS 斷線場景
- **工時**：3h
- **E1 指派**：E4

### [x] B12：tab-governance innerHTML 審查（E3 MEDIUM，部分修復）
- **現狀**：ocEsc() 已廣泛使用（52+ 處），剩餘 innerHTML 為靜態字串
- **修復**：逐一確認剩餘 innerHTML 確實為靜態
- **工時**：1h
- **E1 指派**：E1a-Beta

### [x] B13：Evolution→Deploy 自動化循環斷開（FA P2-FA-3）
- **檔案**：`evolution_engine.py`、`strategy_auto_deployer.py`
- **問題**：兩模組完全無交叉引用
- **修復**：evolution_engine 輸出 best_params → auto_deployer 消費並更新策略
- **工時**：4h
- **E1 指派**：E1-Gamma

### [x] B14：_ollama_stats lazy init 無觀測性（FA FA-10）
- **檔案**：`app/layer2_cost_tracker.py`
- **修復**：初始化時 emit log + 暴露 /api/v1/ai/stats 端點
- **工時**：1h
- **E1 指派**：E1-Delta

### [x] B15：ollama_client.is_available() 仍同步 1s（AI-E P2，部分修復）
- **檔案**：`app/ollama_client.py:146`
- **修復**：改為 `asyncio.to_thread()` 包裝，或用 async httpx
- **工時**：1h
- **E1 指派**：E1-Delta

---

## ██ Wave 8C — 架構改進（Week 4，~28.5h）

### [x] C1：strategist_agent.py 1068 行 God-class（AI-E P3）
- **修復**：拆為 strategist_core.py + h1_thought_gate.py + h4_validator.py + l2_evaluator.py
- **工時**：6h
- **E1 指派**：E1-Alpha

### [x] C2：H3 ModelRouter 非獨立模組（FA P2-FA-5）
- **修復**：從 strategist_agent 抽出 model_router.py
- **⚠️ 可與 C1 合併為一個 PR**
- **工時**：3h
- **E1 指派**：E1-Alpha

### [ ] C3：L5 meta-learning 未實現（CC 原則 12，deferred）
- **修復**：設計 meta_learning_engine.py — 分析 L3/L4 結果趨勢，自動調參
- **⚠️ 需先出 FA 功能規格 + PA 技術方案**
- **工時**：8h
- **E1 指派**：E1-Beta

### [x] C4：Regime-aware 策略選擇（FA P2-FA-2，部分修復）
- **現狀**：regime 已觀測/記錄，但未用於策略篩選
- **修復**：ThoughtGate 中加入 regime→strategy 映射表
- **工時**：3h
- **E1 指派**：E1-Beta

### [x] C5：EvolutionEngine object.__setattr__ 繞過 frozen dataclass（AI-E P2）
- **檔案**：`evolution_engine.py:122`
- **修復**：改為非 frozen dataclass 或用 InitVar 模式
- **工時**：1h
- **E1 指派**：E1-Gamma

### [x] C6：AnalystAgent L2 閾值 200 偏高（AI-E P2）
- **檔案**：`app/analyst_agent.py:124`
- **修復**：降為 50 並加 env 覆寫（`ANALYST_L2_MIN_OBS`）
- **工時**：30m
- **E1 指派**：E1-Gamma

### [x] C7：Backtest equity_curve 8640 raw float（FA P3）
- **檔案**：`backtest_engine.py`
- **修復**：加 `downsample_factor` 參數，預設回傳 500 點 + 支援分頁
- **工時**：2h
- **E1 指派**：E1-Gamma

### [x] C8：max_pending_intents=50 無並發壓力測試（CC 部分修復）
- **修復**：新建 test_strategist_stress.py 模擬 100 並發 intent
- **工時**：2h
- **E1 指派**：E4

### [x] C9：market_data_dispatcher 測試覆蓋不足（E4 P2，部分修復）
- **修復**：新建專用 test_market_data_dispatcher.py
- **工時**：2h
- **E1 指派**：E4

### [x] C10：requirements.txt 僅 7 項（E3 LOW）
- **修復**：生成 requirements.lock（pip freeze），加入 CI pip-audit
- **工時**：1h
- **E1 指派**：E1-Delta

---

## ██ Wave 8D — 文檔清理（隨時穿插，~1.25h）

### [x] D1：COMPREHENSIVE_SPEC_REQUIREMENTS.md 100% 重複（TW）
- **檔案**：`docs/governance_dev/COMPREHENSIVE_SPEC_REQUIREMENTS.md`（649 行）
- **修復**：刪除，留指向 `audits/2026-03-31--spec_requirements_287.md` 的 pointer
- **工時**：10m

### [ ] D2：CLAUDE.md section 3 約 409 行歷史記錄（TW）
- **修復**：歸檔至 `docs/archive/claude_md_section3_history.md`
- **工時**：20m

### [x] D3：3/31 報告路徑不規範（R4）
- **檔案**：`CCAgentWorkSpace/A3/E3/E4/E5` 下 March 31 報告
- **修復**：mv 至 `workspace/reports/`
- **工時**：10m

### [x] D4：.DS_Store 殘留（R4）
- **修復**：`git rm --cached` + 加入 `.gitignore`
- **工時**：5m

### [x] D5：decisions/ .docx 索引不完整（R4，部分修復）
- **修復**：逐一核對並補齊 README 條目
- **工時**：30m

---

## ██ 已知待辦（已文件化，非緊急）

### Intent 被拒時策略內部狀態不回退（P2 · 已修復 2026-04-01）
- ✅ 已修復：`on_intent_rejected()` callback + `_history_ref` 回調機制
- 歸檔：docs/worklogs/control_api_gui/2026-04-01--completed_todo_archive.md

### Grid 策略同一 tick 產生大量重複 intent（P2 · 已修復 2026-04-01）
- ✅ 已修復：60 秒 cooldown + `_last_emit_ts_ms` 防重複
- 歸檔：docs/worklogs/control_api_gui/2026-04-01--completed_todo_archive.md

### Paper-Demo 差異校準系統（長期）

Paper 與 Demo 是「內部模擬 + 外部驗證」雙軌架構，差異本身是系統健康度信號。

**短期（現狀維持）：**
- 現有 fail-open + DIVERGED 日誌 + 雙遍歷清倉已處理分歧，無需改動

**中期 — GUI 差異可視化：**
- [ ] tab-trading.html 明確標示「Paper 數據」vs「Demo 數據」來源
- [ ] 新增 Paper-Demo 差異率儀表板卡片
- [ ] 對賬引擎 reconcile() 結果在 GUI 可視化

**長期 — 自動滑點模型校準：**
- [ ] 累積 Demo 實際成交數據到 PostgreSQL
- [ ] 定期用 Demo 實際滑點反推 Paper SLIPPAGE_TIERS 準確度
- [ ] 費率校準：Paper 硬編碼費率 vs Demo 實際費率

---

## ██ 後續大方向

```
Phase 4（5+21天）：
  Paper Trading 穩定運行 21 天觀察期
  Live 前置條件核驗 + Supervised Live Gate（M 章）

M 章：Supervised Live Gate（需先積累 paper trading 數據）
N 章：Constrained Autonomous Live

Live 前置條件（M/N 前必須核驗）：
  - Paper Trading 穩定運行至少 21 天
  - H0 Gate 確定性門控已實施並驗證 ✅
  - 風控框架實測驗證 + 回測引擎驗證策略 alpha
  - provider pricing table 正式綁定
  - authority grant contract + execution adapter contract
  - 遠程訪問安全方案（HTTPS + CSP）
```

---

## ██ OpenClaw 深度整合（後續開發，非緊急）

> 2026-04-03 PM/PA/FA 聯合分析結論。OpenClaw 定位不變（通信+運維層，不碰交易決策）。
> Canvas A2UI 已評估排除（A2UI push 是 WIP 未完成 + 手機端前台限制不實用）。
> ClawHub Skills 已評估排除（金融系統安全考量，不跑未審計第三方代碼）。

### [ ] OC-1：Webhook 告警通道（優先級：高 · 預估 1-2 天 · 零 AI 成本）
- **目標**：Python 偵測異常 → HTTP POST → OpenClaw webhook → Telegram 即時推送
- **場景**：Bybit WS 斷線 / 單筆虧損超閾值 / 服務健康異常 / 風控觸發
- **優勢**：OpenClaw 已處理 Telegram 認證/重試/格式化，比自寫 Bot 簡單
- **前置**：需先配置 Telegram 通道（`openclaw channels add --channel telegram`）

### [ ] OC-2：Telegram 通道配置（優先級：高 · 預估 0.5 天 · 零 AI 成本）
- **目標**：配置 OpenClaw Telegram 通道，啟用消息推送能力
- **當前**：`openclaw channels list` 顯示 0 個通道
- **依賴**：OC-1 依賴此項

### [ ] OC-3：多通道分級告警（優先級：中 · 預估 1 天 · 零 AI 成本）
- **目標**：按優先級分流告警到不同通道
- **方案**：P0（帳戶安全）→ Telegram 緊急群 / P1（風控）→ Telegram 常規群 / P3（調試）→ Slack/Discord
- **依賴**：OC-2 完成後

### [ ] OC-4：MCP PostgreSQL 接入（優先級：中 · 預估 1 天 · 按需 AI 成本）
- **目標**：Operator 在 Telegram 用自然語言查交易數據（「最近 7 天哪個策略勝率最高？」）
- **方案**：OpenClaw MCP → PostgreSQL 直連 → AI 整合回答
- **成本**：每次查詢一次 LLM 調用，Operator 主動觸發，低頻可接受
- **不碰交易決策**，純態勢感知

### [ ] OC-5：Cron 精細化健康心跳（優先級：低 · 待 OpenClaw --exec flag 發佈）
- **目標**：5 分鐘心跳推送系統健康狀態到 Telegram（announce 模式）
- **阻塞**：當前 cron 每次觸發仍需一次 LLM turn，成本不可接受
- **等待**：GitHub Issue #24597 / #29907（--exec flag 直接跑 shell 不經 LLM）
- **替代**：可用系統 crontab + 直接調 Telegram Bot API 繞過 OpenClaw

### [ ] OC-6：Sub-agent 異步回測（優先級：低 · 預估 2 天 · 週頻 AI 成本）
- **目標**：週日 Evolution 網格搜索 spawn 為 OpenClaw sub-agent 後台執行
- **方案**：coding-agent skill（已 ready）→ 委派 Claude Code 跑 BacktestEngine
- **成本**：每週一次 LLM session，可接受

---

## ██ GUI 實時推送優化（後續開發，非緊急）

### [ ] WS-1：FastAPI WebSocket/SSE 實時推送（優先級：中 · 預估 1-2 天）
- **目標**：將現有 30 秒 JS 輪詢改為服務端推送，延遲降至 <100ms
- **範圍**：PnL 數據 / 持倉狀態 / 價格更新 / 風控狀態
- **方案**：FastAPI 原生 WebSocket 端點（`@app.websocket("/ws/live")`）
- **優勢**：完全自主可控 / 零外部依賴 / FastAPI 原生支持
- **評估背景**：評估 OpenClaw Canvas A2UI 後決定不採用（A2UI push WIP 未完成 + 手機前台限制），自建 WebSocket 是更直接的路徑
- **依賴**：無，可獨立排期

---

## ██ 依賴關係圖

```
Wave 8A（安全+正確性 · 11h · 本週）
  └─→ Wave 8B Sprint 1（核心重複消除 · 18h · Week 2）
       ⚠️ B1 (now_ms) 應在 B3/B4/B5 前完成
       └─→ Wave 8B Sprint 2（測試+前端統一 · 15.5h · Week 3）
            └─→ Wave 8C（架構改進 · 28.5h · Week 4）
                 ⚠️ C1+C2 可合併
                 ⚠️ C3 需先出 FA 規格

Wave 8D（文檔清理 · 1.25h · 隨時穿插，無依賴）
```
