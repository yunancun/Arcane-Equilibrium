# AI-E Memory — 工作記憶

## Memory Usage Contract (2026-05-16)

- 本文件保存歷史教訓與角色偏好，不是 active state、TODO 或 runtime ledger。
- 若舊條目與 `TODO.md`、`README.md`、`CLAUDE.md`、`.codex/MEMORY.md`、`docs/agents/context-loading.md`、代碼或 runtime 證據衝突，信任較新的有證據來源並顯式說明衝突。
- 不要靜默刪除舊條目；只追加可復用的 durable lesson。長報告放 `workspace/reports/`，active 進度放 `TODO.md`。

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

## 2026-05-08 完整 AI 棧 audit（本次）

### 三大新發現（更正過期 memory）

1. **MLDE shadow → param applications 已真活**（vs 4/24 audit 過期記錄「ai_usage_log=0」）：
   - 7d shadow 5209 row（mlde_shadow_advisor 437/24h + dream_engine 391/24h + mlde_demo_applier 21）
   - 7d param applications 2398（applied 277=11.5% / skipped 2041=85% / failed 47 / candidate 33 live）
   - dedupe filter 過於激進（1941/2041 = 95% skipped 因 dedupe）
   - decision_features 9.47M / scorer 1.4M / mlde_edge_training 559k / JS 864 全在跑

2. **`98b76cce` (2026-05-08 21:58) cloud L2 整合**：
   - provider_client.py 622 LOC + provider_keys_store.py 397 LOC + layer2_engine.py 3 callsite refactor
   - Anthropic + OpenAI(GPT-4o/o1) + DeepSeek(Chat/Reasoner) 三 provider client_implemented=true
   - Tier 2/3 budget fallback 真接（50% threshold→DeepSeek / 85%→Haiku）
   - Perplexity scout-only（**0 真實 PerplexityClient class**，只是 enum 標記 + UI）
   - 致命 gap：~/BybitOpenClaw/secrets/providers/ 目錄存在 0 file；ANTHROPIC/OPENAI/DEEPSEEK API_KEY env 全 unset
   - layer2_engine 完全靠 manual `POST /paper/layer2/trigger`（0 autonomous scheduler）
   - 結論：**code-ready / operationally-dormant**

3. **engine env 檢查發現 CLAUDE.md §三 過期**：
   - `OPENCLAW_LEASE_ROUTER_GATE_ENABLED=1` 已啟用！（vs CLAUDE.md 說 default OFF / canary ~05-15）
   - `OPENCLAW_AGENT_SPINE_RUNTIME_MODE=shadow` 確認
   - `OPENCLAW_COST_EDGE_ADVISOR` 未設 → daemon disabled → cost_edge_advisor_log 0 row all-time

### 真實 AI 流量（2026-05-08 17:00 取樣）

| Layer | 24h | 7d | cost |
|---|---|---|---|
| L0 | 不可計 | 不可計 | $0 |
| L1 Ollama 9B | ~8 cycle Strategist 全 reject | ~336 cycle | $0 |
| L1 Ollama 27B | 0 | 0 | $0 |
| L1.5/L2 Anthropic/OpenAI/DeepSeek | 0 | 0 | $0 |
| MLDE shadow → params | 469 attempts | 2398 attempts | $0 |
| DreamEngine | 391 row | ~hourly cycles | $0 |

### Strategist 8/8 cycle delta>30% rejected
engine.log 證據：5-min cycle alive，Ollama IPC 真接，但 `RiskConfig.strategist.max_param_delta_pct=30%` 永遠擋下 q4 量化高方差輸出 → AI tuning **0 effective commit**。

### ContextDistiller / Perplexity / 5 ML 訓練腳本 真實狀態
- ContextDistiller: 0 callsite 全 codebase（profile/memory 提到的 spec 未 IMPL）
- Perplexity client class: 不存在（enum + UI + provider_keys 白名單，但無 PerplexityClient impl）
- thompson_sampling 4/6 / cpcv 4/10 / dl3 4/6-4/27 / optuna 4/20 / weekly_report 4/7 — 全 9-32 天無 invoke
- crontab 只 2 個 entry（edge_label_backfill + microstructure_recorder），無 ML training entry

### 報告
| 日期 | 任務 | 文件位置 | 行數 |
|------|------|---------|------|
| 2026-05-08 | 完整 AI 棧 effect/dev/接入度/可用度 audit | docs/CCAgentWorkSpace/AI-E/workspace/reports/2026-05-08--ai_effectiveness_full_audit.md | 278 |

### advisory-active prerequisite（最低可行 = 1+2+4+6 共 ~1d 工作量）
1. GUI 寫 ANTHROPIC_API_KEY（trivial / operator）
2. Manual Layer2 trigger 1 次驗端到端（5min / operator）
3. Strategist max_param_delta_pct 30→50%（1d / E1+E2+E4）
4. OPENCLAW_COST_EDGE_ADVISOR=1 + restart（30min / operator）
5. attribution writer 修 84.6% chain failed（1-2 sprint / E1+MIT）
6. 5 ML 訓練腳本 cron 化（0.5d / operator）
7. AI advisory ROI 月報自動產出（1 sprint / E1+AI-E）
8. Layer2 autonomous loop（1 sprint / E1）
9. ContextDistiller IMPL（1 sprint / PA+E1）

## 2026-05-09 24h verification of 2026-05-08 audit findings

### 修復率：0/5 真實修復 + 28 commits 0% runtime activation

**所有 5 個 audit finding 24h 內 0 真實 runtime 修復**：
1. **F-07 P0 Cloud L2 0 流量**：providers/ 仍 0 file，engine env 仍無 ANTHROPIC/OPENAI/DEEPSEEK_API_KEY，ai_invocations 24h=0
2. **P1-A Strategist max_param_delta_pct=30%**：TOML 未改，但意外發現 24h 354 applied（hidden fix 機制不明，需 RCA）
3. **P1-B CostEdgeAdvisor env-gate**：env 仍未設，cost_edge_advisor_log 仍 0 row all-time
4. **P2-A 5 ML scripts unscheduled**：commit `268f9470` source-only fake-fix，crontab 0 entry，且 ml_training_maintenance.py 默認 jobs (linucb/mlde_shadow/mlde_demo/scorer/quantile) **不是** audit 所指 5 個 (thompson/cpcv/dl3/optuna/weekly_report)
5. **P2-D ContextDistiller**：仍不存在 + Linux 4-3 .pyc dead artifact

### 真實 24h 數值對比

| 指標 | 2026-05-08 | 2026-05-09 | 結論 |
|---|---|---|---|
| ai_invocations 24h | 0 | 0 | dormant |
| ai_usage_log 24h | 0 | 0 | dormant |
| cost_edge_advisor 24h | 0 (all-time) | 0 (all-time) | dormant |
| Cloud L2 cost 24h | $0 | $0 | 0 |
| MLDE shadow 24h | 469 | 902 | +92% organic |
| MLDE applied rate | 11.5% | 41.7% | +30.2pp organic |
| strategist_applied 24h | 0 (8/8 reject) | 354 | hidden fix |
| ml model_registry production | 0 | 0 | dead |

### 5 個 NEW-ISSUE
- NEW-1 P1: API key 路徑契約不一致（provider_keys_store vs secret_files/ai/）
- NEW-2 P0: commit 268f9470 fake-fix（cron not installed + scope mismatch）
- NEW-3 P1: ContextDistiller dead .pyc (Linux 4-3 殘留)
- NEW-4 P2: Strategist applied 機制 RCA 待
- NEW-5 P2: agent.ai_invocations writer path audit gap (Ollama L1 不寫表？)

### 對抗性教訓
1. **commit message 暗示 ≠ runtime 修復**——`audit:` prefix commits 大部分自承「leave operator activation」但 24h 內 operator 0 activation
2. **DOC-08 4 KPI 全部因 0 流量無法量測**——dead-AI 假合規
3. **AI-E profile.md 應廢止未 IMPL spec 引用**（ContextDistiller, 雙進程 AI 路徑等）
4. **5/8 audit 結論「Strategist 8/8 reject」、「MLDE 11.5% applied」已過期**——需 24h 重採樣

### 報告
| 日期 | 任務 | 文件 | 行數 |
|---|---|---|---|
| 2026-05-09 | 24h verification of 2026-05-08 audit | docs/CCAgentWorkSpace/AI-E/workspace/reports/2026-05-09--ai_effectiveness_verification.md | 264 |

## 2026-05-09 v2 verification (34 commits since 455d796e baseline)

### v1 9 finding 在 v2 的 verdict
- ✅ 1 (NEW-3 ContextDistiller dead .pyc → 35f81a7b 加 source 解決)
- ⚠️ 1 (P2-D ContextDistiller IMPL ✓ / runtime-dormant by AMD §4 design)
- ❌ 7 (F-07 / P1-A degradation / P1-B / P2-A / P2-C / NEW-1 / NEW-2 / NEW-4 / NEW-5)
- 1 個 commit 偽進步：a904e273 「cron verified」是 edge_label_backfill 不是 5 ML scripts

### v2 NEW critical 發現
1. **a0bbde58 fake-fix from runtime view**: TOML 改 0.50 但 engine 啟動 15:52:49 比 commit 16:08:42 早 15 分鐘，runtime 仍跑 30% cap（engine.log 14:23 UTC 直證 cap_pct=30.0%）
2. **AMD-2026-05-09-02 §4 spec lock-in**: Layer2 永久 manual-only by design = Cloud L2 永久 ≈0 流量 = AI-E DOC-08 4 KPI 中 3 個本質不可量測
3. **Strategist applied 衰減**: v1 354 → v2 221 (-37.6%)，否定 v1 hidden fix 假設
4. **commits 分類**: 34 commits 中只有 1 個真實 AI IMPL (35f81a7b)；ai_invocations 24h 仍 0、latest_ts 仍 2026-05-06 (3 天無寫)
5. **profile.md 過期 spec**: ContextDistiller token 預算 / 雙進程 AI 路徑 / DreamEngine 零成本 三條 unmeasurable，建議廢止

### DOC-08 4 KPI v2 verdict
- 每日 AI 成本 < $2.00: $0 = dead-AI 假合規
- L1 Ollama 延遲 < 3s: 不可量測 (24h 0 ai_invocations 寫入)
- AI ROI ≥ 0.5: 數學未定義 (X/0)
- cost_edge_ratio 等級 F < 5%: 不可量測 (cost_edge_advisor_log all-time 0)

### 對 v1 self-correction
v1 樂觀「Strategist 354 applied / MLDE 41.7%」結論在 v2 不持續；v1 NEW-4 hidden fix 假設被否定（v2 衰減證明是 Ollama 自然分布變化非 hidden mechanism）。

### 報告
| 日期 | 任務 | 文件 | 行數 |
|---|---|---|---|
| 2026-05-09 v2 | v1 修復對抗性嚴苛核實 | docs/CCAgentWorkSpace/AI-E/workspace/reports/2026-05-09--ai_effectiveness_verification_v2.md | 363 |

## 2026-05-09 v3 verification (5 commits faf2d131..da2aba11 + PA redesign cross-check)

### 5 commits AI 影響 verdict
- c2ab7b1a strategist wide skill: 純 prompt engineering，仍 Ollama L1 9B，0 Cloud L2 cost；ai_invocations 不同步（writer path 漏接）；engine 未 rebuild 仍跑舊 0.30 cap
- 48227607 promotion evidence: 純 numpy 統計（DSR/PBO/CSCV）不需 LLM；V079 在 PG 未 apply
- da2aba11 F-08 cron: source +511 LOC 但 cron 仍未 install（第 3 次 source-only fix）
- c081029d / ad14db07: 0 AI 影響

### 24h KPI v3
- ai_invocations 24h = 0（latest 2026-05-06 = 3+ 天無寫）
- cost_edge_advisor_log all-time = 0
- strategist_applied 24h = 213（v1 354 → v2 221 → v3 213 持續衰減）
- mlde_shadow_recos 24h = 1076 / mlde_param_apply 24h = 514（活躍）
- experiment_ledger / pattern_insights all-time = 0（PA Analyst L2-L5 dormant 主張證實）

### PA redesign cross-check verdict: PARTIAL AGREE
- ✅ Strategist 是 dict 微調器（c2ab7b1a 反證再次確認）
- ✅ Strategist 應 reframe 為 alpha-source orchestrator
- ✅ Analyst L2-L5 dormant（runtime 0 row 證實）
- ✅ ADR-0020 manual-only 是 source true
- ⚠️ PA 隱含「需要 Cloud L2 autonomous loop」假設不成立（Ollama 27B 足夠）
- ⚠️ PA Layer 2 解封路徑與 ADR-0020 細節矛盾，需澄清為「Layer 1 autonomous + Layer 2 manual escalation」
- AI-E 對 ADR-0020 fail-closed verdict: 合理選擇（ai_invocations writer path 漏接前 + cost cap runtime 未 tested 前，autonomous loop 是 governance 災難）

### v3 NEW findings
- E.1 P0: ai_invocations writer path 完全沒接 Strategist L1 9B 流量（grep 證實）→ DOC-08 KPI 測量點選錯
- E.2 P1: V079 promotion_evidence migration 未 apply
- E.3 P1: experiment_ledger / pattern_insights 0 row（Analyst L2 trigger 不 spawn）
- E.4 P1: ContextDistiller IMPL ✓ 但 ADR-0020 manual-only → runtime-dormant by design
- E.5 P2: 5 commits 全 source-only，engine PID 298034 啟動 15:52 早於所有 commit ts

### 對 v2 self-correction
- v2「dead-AI 假合規」結論需 nuance：實際是「writer path 不覆蓋 L1」非「AI 真死」
- 真實活躍 AI 量: Strategist 5-min × 4 strategy × 24h × 5 agents ≈ 數百次/天 + mlde 1076/24h
- 修 E.1 writer path 後 4 KPI 自動 unblock

### 報告
| 日期 | 任務 | 文件 | 行數 |
|---|---|---|---|
| 2026-05-09 v3 | 5 commits + PA redesign cross-check | docs/CCAgentWorkSpace/AI-E/workspace/reports/2026-05-09--ai_effectiveness_verification_v3.md | ~290 |

## 2026-05-21 — v5.8 13-module LLM cost executability audit
- File: workspace/reports/2026-05-21--v58_executability_audit.md
- Verdict: GO-WITH-CONDITIONS (6 conditions + new ADR-0041 ContextDistiller v4)
- Top finding: ContextDistiller token 從 v5.7 700-900 → v5.8 1,110-1,430 → L1 9B P50 直接撞 DOC-08 3s SLA（不是 P95 邊緣）
- Y2 LLM cost peak: $1,340-2,560/年 = 月 $112-213 vs DOC-08 月 $60 cap = 1.9-3.5x 超 cap
- M4 + M11 + M8 占 Y2 新增 LLM cost 72%（黑洞集中）
- v5.8 §3/§4 工時表 2,780-3,930 hr 仍 0 字 LLM cost — 與 v5.7 audit 同性質 finding 但 module 數量 +13 倍放大
- ADR roster gap：0034-0040 七個 ADR 但漏掉 ContextDistiller v4 = governance 盲點
- Must-fix 6 條（§5）：ADR-0041 補入 1A-β / 工時表加 LLM cost 欄 / M4 Cowork review path 釘 / M11 narrative policy 釘 / writer path 修 / DOC-08 cap 重估

## 2026-06-11 — 工具登記：Claude Code session token 用量分析腳本可用
- `helper_scripts/analyze_token_usage.py`（改編自 obra/superpowers，MIT，stdlib-only 唯讀）：按主會話／subagent 分桶統計 input/output/cache token 與估算成本；一行用法 `python3 helper_scripts/analyze_token_usage.py --recent 2 --top 15` 即出最近 2 個 session 分桶明細 + 全 session 合計 + 按 agentType 聚合 top-N（AI 團隊 token 成本歸因可直接取數；subagent 口徑=agent transcript 權威，非 toolUseResult 末次 call 低估值）。

## 2026-06-13 — AI 成本盈利證據 (read-only, Linux runtime 親證, engine PID 3607315)
- **每日 AI 成本 = $0 (FACT)**：`agent.ai_invocations` 全史僅 2 row 皆 `provider=row_proof/synthetic_no_model_call` $0 (latest 2026-05-06)；`learning.ai_usage_log` 0 row/$0；billable(cost>0)=0；teacher_directives=0。L2 paid 路徑全史 0 billable call。達標 <$2 但=dead-AI 假合規。
- **重大 posture 變化**：engine env 三把 paid key 全 **present 非空** (ANTHROPIC len108/OPENAI len164/DEEPSEEK len35) + `OPENCLAW_COST_EDGE_ADVISOR=1`。但 ClaudeTeacher loop `tasks.rs:289 AtomicBool::new(false)` 硬編 boot-disabled，唯一開啟=IPC `set_teacher_loop_enabled` (operator)；key 在場不自動觸發付費。安全鎖=runtime kill-switch 非 missing-key。Item 1b 前審 pre-call cap gap 仍未修(post-call accounting)。
- **cost_edge_ratio 仍不可量測**：`cost_edge_advisor_log` 已活(41207 row, 1440/24h=每分鐘) 但全史 `status=Disabled/phase=B_shadow/data_days=0/ratio=NULL/ai_spend_7d=0/paper_pnl_7d=0` → heartbeat 非真 ratio 計算。DOC-08「等級 F<5%」KPI 結構性不可裁。
- **真實 AI = 免費本地**：MLDE shadow 347/24h(3444/7d)、strategist_applied 276/24h(738/7d) 皆 fresh；Ollama bge-m3+qwen3.5 9b/27b live。L1 ROI 分母=$0 → ROI 數學未定義(X/0)。
- **dormant AI 能力**：ClaudeTeacher loop(default-off)、cost_edge_advisor(B_shadow 永不算 ratio)、L2 memory recall(99 seed row=59 incident+40 rule 全 embedded 1024d 但 `OPENCLAW_L2_MEMORY_RECALL` 不在 env=default 0 連 shadow 都未開)、Layer2 paid(key 在場但 loop off + manual-only)。

## 2026-06-13 — AI 盈利研判（守+攻，read-only Linux 親證 engine PID 3607315）
- **守**：6 leak/frozen/unrealized 診斷。核心=已實現端每策略 latest-cell runtime_bps 全負（bb_breakout -11.4/grid -12.5/ma -8.0/funding_arb -24.4，0 validation_passed cell 全系統，n≥30 cell 僅 4 仍負）→ cost_gate 拒單是真負非誤殺（承接 MIT 7d 942360 reject/0 false-kill）。AI 成本=$0 → ROI 數學未定義；DOC-08「達標<$2」=dead-AI 假合規。L1（MLDE/strategist fresh）只在微調負 edge 搜索空間（paradigm blocker）。L2 三 key present 但 boot-disabled+manual-only=0% 激活。memory recall 99 row embedded 但 default-0 dormant。cost_edge_advisor 41226 row 全 B_shadow/ratio=NULL → CLAUDE「ratio≥0.8 關倉」鐵則永不觸發。
- **攻**：5 機會。O1★=L2 自主 alpha-source 發現（換軌：AI 生成假設過 P3b math gate，非微調，$0.05/天 << $2 cap）；O2★=L2 事件解讀軸（listing fade/公告/Polymarket 原始流 live 但缺 AI 解讀層）；O3=開 memory recall shadow 轉研究效率複利；O4=修 cost_edge_advisor 出 B_shadow 上風控腿；O5★=範式拷問 OHLCV+技術指標是否到天花板（5 候選全死同根因 down-beta+成本牆=搜索空間結構問題非執行問題，換軌另類數據軸）。
- 成本牆數學：Sonnet 4.6 $3/$15-per-MTok，一次 8K-in/2K-out≈$0.054 → $2 cap 下理論 ~37 次/天深度推理，實跑 0 → L2 預算頭寸 100% 閒置。所有 AI 翻牆機會須過確定性 math gate（LLM 永不驗 alpha），AI 只做生成/解讀/預篩。~~報告 `workspace/reports/2026-06-13--AI-E--profit_research_守攻.md`~~ **【2026-07-04 TW per R4 更正：該報告檔全域不存在（lineage gap，已由 07-03 AI-E 自審記錄，見下方 2026-07-03 條）；本條結論本身有效，僅移除失效報告指針】**。

## 2026-06-14 — 全倉 AI 成本審計（read-only, Linux engine PID 3795194 已重啟, 11 findings）
- **新 HIGH (F1)**：DOC-08 $2/天硬上限在 Rust BudgetTracker **完全無 daily 腿**（只 monthly local_total $100 / platform_hard_cap $150，usage_io date_trunc('month')）。Python Layer2CostTracker 有 $2/day 但是 manual-only 路徑；Rust autonomous(ClaudeTeacher) 路徑與 daily cap 各管各=雙腦。kill-switch 一開 daily 防線缺失。
- **定價多軸 drift (F2/F8/F10)**：Rust ai_pricing.yaml(2026-04-06) sonnet-4-5/opus-4-6 $15/$75 vs Python PricingTable(2026-04-16) sonnet-4-6/opus-4-7 $5/$25 → 同 opus 差 3x；現行官方=Opus4.8 $5/$25/Sonnet4.6 $3/$15/Haiku4.5 $1/$5。tasks.rs:270 硬編 claude-sonnet-4-5(stale)。真名(opus-4-8)呼 Rust 會 fail-closed 誤拒。
- **cost_edge_ratio 三同名三義 (F3)**：DOC-08§5.2/skill=cost/edge(高壞,≥0.8關倉) vs cost_edge_advisor.py/Rust advisor=edge/cost(高好,≤threshold Trigger) vs tracker.rs=used/limit(burn). CLAUDE 鐵則 enforcement 腿(F4)全 NULL(advisor 41500 row 全 Disabled/B_shadow,06-13→06-14 +274 heartbeat 仍 0 真 ratio)。
- **死 cron (F5)**：crontab daily_cost_snapshot.sh 在 repo/Linux/SCRIPT_INDEX 三處皆無+log 不存在→每日成本快照採集腿斷。crontab 已增至 9+ 條(L2 distill PIPELINE=1+EMBED_BACKFILL=1 已 cron 化, m11_replay, polymarket)。
- **持續 (F6/F7)**：ai_invocations 仍 2 row/0 billable(L1 IPC 不寫表,writer 只接 cloud);L2 memory recall B3 wiring(5dfce536)source-ready 但 agent.l2_call_ledger 表不存在=L2 從未 fire,99 embedded 教訓 0 召回。DreamEngine 0 LLM import 親證零成本。
- 盲區：/proc/PID/environ 本審權限拒(無法直讀 engine env flag,改用 DB 證 dormant);L1 latency P50/P95 數值未量(ai_invocations 不覆蓋 L1);bybit_thought_gate 56檔9658LOC 僅查 wiring(接 layer2 manual 路徑)未逐檔審。
- ~~報告 `workspace/reports/2026-06-14--AI-E--full_repo_cost_audit.md`~~ **【2026-07-04 TW per R4 更正：該報告檔全域不存在（lineage gap，同 06-13 條；07-03 AI-E 自審已記）；11 findings 結論本身有效，僅移除失效報告指針】**。

## 2026-06-14 — P2 ai_pricing 雙副本 fix 規格（design-only, read-only）
- **雙副本根因確認**：(a) Rust `settings/ai_pricing.yaml`(2026-04-06) 鍵=**真名 model-id**(claude-sonnet-4-5/claude-opus-4-6/claude-haiku-4-5-20251001) 漏現行 opus-4-8/sonnet-4-6；fail-CLOSED(unknown→compute_cost Err→check_and_record Err→拒呼叫)。(b) Python `layer2_types.py:474-492 PricingTable` 鍵=**tier alias**(haiku/sonnet/opus)+model_id 僅裝飾(sonnet-4-6/opus-4-7 stale)；fail-OPEN(`layer2_cost_recording.py:104-106` unknown tier→warn→退 sonnet 定價，永不拒)。兩套鍵空間不交集=本質上不是同一張表。
- **真名呼叫被拒的精確機制**：tasks.rs:270 + consumer_loop 8 處 + client.rs 硬編 `claude-sonnet-4-5`(stale)，此名碰巧在 YAML 內所以現不拒；但 API 端 claude-sonnet-4-5 可能已退役 404，且一旦改成真名 claude-sonnet-4-6/claude-opus-4-8，YAML 無此鍵→Rust fail-closed 拒。第三 bug：`_sync_to_rust_budget` 傳 model=alias("sonnet")給 Rust record_ai_usage→Rust 按真名鍵查→必 None→fail-closed，Python/Rust 同步腿鍵空間不通。
- **官方定價(2026-06-14 WebSearch 多源一致)**：Opus 4.8 $5/$25、Sonnet 4.6 $3/$15、Haiku 4.5 $1/$5 per MTok；cache write 1.25x(5m)/2x(1h) 基礎 input、cache read 0.1x；Batch 50%。當前 schema 無 cache 欄=cache token 全按基礎 input 計(高估,保守安全)。
- **SSOT 建議**：YAML 為唯一真名定價權威；Python PricingTable 改為 alias→model-id 映射層+從 YAML 載價(消除硬編值);tasks.rs/consumer_loop 硬編改讀 config 真名。詳見報告/本次輸出。

## 2026-07-03 — 全倉 AI 成本審計（read-only，engine PID 2368227）
- **懸案終判**：agent.ai_invocations 空表根因=`OPENCLAW_AGENT_EVENT_STORE_ENABLED` 默認 "0" 且 API service env 未設（PID 1038429 environ 親證）——writer 代碼 WP-04 05-16 早已落地，一個 env var 之遙。L1 Strategist 自 06-24 全停（applied max=06-24 19:17），根因=demo fills 斷流（7d=78 筆，top pair 8<HAVING 30）非 AI 棧故障。定價三軸已對齊且 07-03 官方複驗仍準；tasks.rs 硬編已修（env-override 默認 sonnet-4-6）；pre-call budget gate 已落地。仍開：F1 daily 腿缺（ai_budget_config 全 monthly）、F2 advisor [cost_edge] enabled=false（42,385 row 全 Disabled/ratio NULL）、l2_call_ledger 表不存在。新發現：Layer2CostTracker 跨進程無鎖（4 workers，autonomous 化前必修）；memory 索引的 06-13/06-14 兩份 AI-E 報告全域不存在（lineage gap）。新模型情報：Sonnet 5 intro $2/$10 至 08-31（較 4.6 省 33%）、Fable 5 $10/$50，YAML 無鍵 fail-closed。報告 `workspace/reports/2026-07-03--ai_cost_full_repo_audit.md`。
