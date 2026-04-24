# AI-E Memory — 工作記憶

## 項目上下文（2026-04-24 刷新）

- 當前 Phase：Live_Ready ⚠ / Phase 5 PAUSED（demo ≥21d 穩定中，最早 2026-05-07 解鎖 P0-3 Phase 5 edge 重評）
- Runtime：Linux trade-core engine PID 912616 + uvicorn PID 912671（4 workers），demo mode alive age ~22s
- AI 模組代碼：Python 10,959 行（15 模組）+ Rust 8,942 行（7 子系統）= 19,901 行
- AI 相關 API routes：39 個 live（curl 實測）
- Ollama：qwen3.5:9b-q4_K_M + qwen3.5:27b-q4_K_M 雙 model available

## 工作記憶

### 2026-04-24 審計關鍵發現（更正 memory 過期敘述）

1. **memory 過期校正**：先前 memory `project_layer2_agent_design.md` 敘述「H1-H5 全 stub」**過期**。實測 H0/H1/H2/H3/H4/H5 全 live 且 H1/H3/H4 已從 strategist_agent.py 拆分為獨立模組。
2. **CLAUDE.md §三 2026-04-23 audit 更正確認**：5-Agent 代碼並非 stub（4552 行 live）。Strategist shadow=False、Guardian/Analyst live、**Executor `_shadow_mode=True` 默認（executor_agent.py:482 + strategy_wiring.py:467 ExecutorConfig()）**、Scout live 但只有 MarketScanner 技術面 intel。
3. **新發現 假功能 / dormant 清單**：
   - Layer 2 Claude Agent Loop：只由 `POST /api/v1/paper/layer2/trigger` 手動觸發 + ANTHROPIC_API_KEY 未設 → 從未在 runtime autonomous 跑
   - Rust TeacherConsumerLoop：DEFAULT-OFF Phase 4.1 契約（teacher_loop_enabled=false）
   - Rust edge_predictor：2965 行 ONNX use_edge_predictor=false + shadow_mode=true 全 dormant
   - Rust ml::kelly_sizer：set_kelly_config 無 runtime caller = dead
   - Rust ml::scorer：null backend default（無 ONNX 注入）
   - Rust ml::registry：3 rows 全 canary_status=shadow
   - ScoutAgent：新聞/宏觀/事件日曆 全 stub；Rust news pipeline 不 route 到 Python Scout
   - Combine Layer Shadow Writer：shadow_enabled=false dormant
4. **真實 runtime live 證據**：
   - engine.log 01:06/01:11/01:16 連續 3 次 StrategistScheduler 5-min cycle WARN（proposed param delta >30% rejected）= Ollama 9B 真的被 IPC 呼叫但 proposal 被擋
   - BudgetTracker init + LinUcbRuntime cold-start 成功 log entry
   - Ollama 2 models available（qwen3.5 9B + 27B）
5. **PG learning schema 實測（driving insight）**：
   - decision_features 6.19M rows / scorer_training_features 532k rows / exit_features 244 rows / james_stein_estimates 624 rows（ETL + EdgeEstimator 活躍）
   - ai_usage_log=0 / teacher_directives=0 / strategist_applied_params=0 / experiment_ledger=0 / pattern_insights=0 / linucb_state=0 / rl_transitions=0 / ml_parameter_suggestions=0 / decision_shadow_exits=0 / model_registry=3 全 shadow
6. **成熟度分布**：Production-grade 2 / Live 13 / Shadow 5 / Skeleton 3 / Dormant 5 / Dead 2
7. **原則 13 合規度**：~85%（Rust 端 ai_usage_log=0 rows 是新 gap）

### 架構決策記錄

- H1/H3/H4 已從 strategist_agent.py 拆分為獨立模組（`h1_thought_gate.py` 185 / `model_router.py` 292 / `h4_validator.py` 103）— 4/01 P3-AI-2 標記的拆分問題已部分解決
- `local_llm_factory.py` 提供 LM Studio shim（LOCAL_LLM_PROVIDER env 切換）— Mac Operator 可不裝 Ollama 跑 Layer 2
- `llm_call_wrapper.py` E5-P1-4 抽取 call_ollama_judge_edge / call_ollama_generate — StrategistAgent + AnalystAgent 通用
- `agent_audit_bridge.py` E5-FN-3-FUP 5 Agent audit callback 接入（根原則 #8「交易可解釋」）
- Rust StrategistScheduler（1612 行）取代 Python FastAPI scheduler（避 uvicorn --workers=4 4 個競爭 scheduler）
- Rust ai_service_client + AI Service（Python ai_service.py）雙端 IPC 架構 live，5 handler
- cost_tracker.record_ollama_call 已 deprecated → delegate record_call（4/01 P2-AI-3 已修）

### Session 注意事項（交叉驗證教訓）

- **不採信 CLAUDE.md / memory 敘述 — 以代碼 grep + runtime 實測為準**（本次發現 memory 多處敘述與實測不符）
- Mac dev 側無法直驗 Rust runtime（engine 只跑 Linux）；必經 `ssh trade-core` + PG 連線確認真實狀態
- PG 連線：設 `PGPASSWORD` 後 `psql -h 127.0.0.1 -U trading_admin -d trading_ai`（socket 不通需 TCP）— **密碼從 `settings/database_credentials*.toml` 或 env file 讀取，禁止寫入 memory/docs/report**
- API 實測：`curl http://127.0.0.1:8000/api/v1/...` 大部需 auth token（401）；/layer2/ollama/status + /openapi.json 免 auth

## 報告索引

| 日期 | 任務 | 文件位置 |
|------|------|---------|
| 2026-04-01 | AI 使用效果與開發情況評估（舊基準）| docs/CCAgentWorkSpace/AI-E/workspace/reports/2026-04-01--ai_effectiveness_audit.md |
| 2026-04-24 | AI 使用效果、接入度、開發完成度評估（本次）| docs/CCAgentWorkSpace/AI-E/workspace/reports/2026-04-24--ai_effectiveness_audit.md |
