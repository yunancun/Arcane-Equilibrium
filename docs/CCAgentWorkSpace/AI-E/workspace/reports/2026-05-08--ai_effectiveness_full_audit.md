# AI-E 完整效果審計 — 2026-05-08

**Scope**: AI 棧使用效果 + 開發完成度 + 可接入度 + 實際可用度
**HEAD**: `4e2d2883`（master），最新 AI commit `98b76cce`（2026-05-08 21:58 +0200）
**Runtime**: Linux trade-core engine PID 3854831 / API PID 3854909（uvicorn 4 worker）
**Engine boot**: 2026-05-08T20:01:48Z（~3h 前）
**Ollama**: 2 model 可用（qwen3.5:9b + 27b），sock `/tmp/openclaw/ai_service.sock` listening

---

## §1 Executive Summary

| 維度 | 結論 |
|---|---|
| **代碼完成度** | 高（layer2/5-Agent/MLDE/DreamEngine/CognitiveModulator 共 ~10k+ Python LOC live）|
| **真實可用度** | 低（4 條鏈條只 1 條真活：MLDE shadow → param applications）|
| **L2 雲端 24h 流量** | **0 invocation**（code 接好但 0 key + 0 autonomous scheduler）|
| **L1 Ollama 24h 流量** | 8 cycle × 1 IPC call（StrategistScheduler 5-min cycle）但 **100% delta>30% rejected** |
| **L0 確定性 24h 流量** | 5-Agent state_changes 全 row proof（11 row 同秒 mag014）；真實 L0 執行 = MLDE 88% skip + Strategist delta cap |
| **AI 真實成本** | $0.00（24h+7d+all-time），cost_edge_advisor_log 0 row、ai_usage_log 0 row、ai_invocations 2 row 全 row proof |
| **AI 真實 ROI** | 不可計算（cost=0 / 唯一可量化 attribution = MLDE 對 demo 的 277/2398 真 applied，未 attribute 到 PnL）|
| **本次 audit verdict** | **代碼層 advisory-ready；運營層 advisory-dormant**；要從「會調用 AI」進到「AI 影響交易結果」還缺 5 個前置條件 |

**Top 3 最大紅旗**：
1. **`98b76cce` Tier 2/3 fallback 整套碼好、0 行 production effect**：provider_keys_store 目錄空 + ANTHROPIC_API_KEY/DEEPSEEK_API_KEY/OPENAI_API_KEY env 全 unset + Layer 2 完全靠 manual `POST /trigger`，0 autonomous loop（代碼層完美閉環，運營層 0 contact surface）
2. **5-Agent runtime 是「shadow row proof」非「真活訊息流」**：`agent.messages`/`state_changes`/`ai_invocations` 100% 都是 2026-05-06 同秒寫入的 `agenttodo_mag014_row_proof`，過去 48h 0 真實 agent 訊息事件
3. **Strategist 真活但 0 effective**：5-min cycle 8 次跑、全部 `delta exceeds 30% cap` rejected；Ollama IPC 真接，但 RiskConfig.strategist.max_param_delta_pct=30% 永遠擋下 q4 量化模型的高方差輸出 → AI tuning 名存實亡

---

## §2 Layer routing 真實活躍度（24h + 7d 真實 invocation + cost）

| Layer | 24h invocation | 7d invocation | 24h cost | 真實證據 |
|---|---|---|---|---|
| **L0 確定性**（rule） | 不可計（無單獨 logging）| 不可計 | $0 | MLDE skip 1941/2041 demo `dedupe`、Strategist delta cap 7 次（過去 50min 都 reject） |
| **L1 Ollama 9B**（IPC `strategist_evaluate`） | ~8 cycle × 1 call = **~8** | ~336 cycle × 1 = **~336** | $0 | engine.log `StrategistScheduler delta exceeds cap` 7 row in 50min；ollama runner alive 16% mem 6.5GB；100% rejected |
| **L1 Ollama 27B**（AnalystAgent） | **0** | **0** | $0 | analyst_agent.py 8 callsite 都需 manual trigger，無 autonomous scheduler；ai_usage_log 0 row |
| **L1.5 Haiku**（Anthropic 廉價 tier） | **0** | **0** | $0 | layer2_engine.py L1 triage 寫好但靠 manual `/trigger`；24h api.log 中 `layer2/trigger` count = 0；唯一 traffic 是 GUI poll `/ollama/status`（1900+ 200 OK in 24h） |
| **L2 Sonnet/Opus/DeepSeek/GPT** | **0** | **0** | $0 | provider_keys_store dir 存在但 0 file；ANTHROPIC/OPENAI/DEEPSEEK_API_KEY env 全 unset；Anthropic SDK + OpenAI SDK 已安裝（98b76cce requirements.txt 加了），但 `is_available()` 因 key 缺 → False；`_resolve_effective_provider` 會 fall through 到 `_l1_triage_local` Ollama |
| **DreamEngine**（本地隨機）| 391/24h MLDE row（mlde_dream_engine） | 隨 hourly cycle | $0（純 numpy）| edge_estimator_scheduler.py:587 `from local_model_tools.dream_engine import persist_dream_insights` real call；shadow recommendations source=`dream_engine` 391 row 24h |

**關鍵 finding**: 24h 總 AI cost = **$0.00**（vs DOC-08 daily cap $2.00 / monthly $150 cap 全未消耗）。`learning.ai_budget_config.platform_hard_cap=$150/月` 設置 31d 沒被觸發過 1 cent。

**總結**：L2 全 dormant。L1 Ollama 純粹被 5-min cycle 拉一下做 sanity check，輸出全被 cap 擋。**真正承擔「AI 學習」load 的是 MLDE shadow_advisor + DreamEngine，這兩者全本地 numpy/SQL，無 LLM 推理**。

---

## §3 5-Agent LLM 真實使用矩陣

| Agent | 行數 | LLM ref count | 真實 invocation 來源 | 24h 真實活動 |
|---|---:|---:|---|---|
| **Scout** | 349 | 0 | `MarketScanner` 技術面 intel only；無 Perplexity/news LLM | agent.messages 全 row proof；無自動 loop |
| **Strategist** | 799 | 2 (`ollama_client` + `judge_edge`) | Rust StrategistScheduler 5-min cycle → IPC `ai_service.sock` → strategist_evaluate handler → llm_call_wrapper.call_ollama_judge_edge | 8 cycle 全 delta>30% rejected = 0 effective tuning |
| **Guardian** | 1458 | 5 (`call_ollama_classify`) | guardian_agent.py:1270 `resp = call_ollama_classify(...)` | 0 trace（無事件 trigger context_classify） |
| **Analyst** | 802 | 8 (`call_ollama_generate`) | analyst_agent.py:603 weekly pattern discovery | 0 invocation（`weekly_report_generator` 4/7 後沒跑） |
| **Executor** | 896 | 0 | `_shadow_mode_provider` provider lambda；無 LLM | shadow=True default（fail-closed）；無 IPC trace |

**ContextDistiller**: **0 callsite 全 codebase**（找不到 `context_distiller*.py` 任何檔；強烈懷疑在 docs / TODO 寫過但未 IMPL）→ V3 報告 ~520 token 預算實測 = N/A。

**CognitiveModulator**: 真活；strategist_cognitive.py L131-232 提供 `set_cognitive_modulator` / `tick_cognitive_modulator` / `apply_decision_thresholds`；StrategistAgent ctor 注入 `_cognitive_modulator`（singleton 來自 strategy_wiring）；`_cognitive_modulator.get_all_params()` 真被 confidence/qty 調整邏輯讀取。**但 24h scan_interval 動態調整 effect 量化 = 不可測**（無 dedicated metric log）。

**DreamEngine**：真活。edge_estimator_scheduler.py:587 hourly cycle 呼 `persist_dream_insights(dsn, engine_mode)`；24h 寫 391 row `mlde_shadow_recommendations source=dream_engine`；零 LLM 成本（純 numpy random + replay metadata 統計）。

---

## §4 可接入度評估（per provider/endpoint）

| Provider | client_implemented | Anthropic SDK 安裝 | API Key 存在 | env 注入 | autonomous scheduler | 可接入度 |
|---|:---:|:---:|:---:|:---:|:---:|---|
| **Anthropic** (Sonnet/Opus/Haiku) | ✅ Yes | ✅ Yes (`anthropic>=0.40.0`) | ❌ key 0 byte | ❌ ANTHROPIC_API_KEY 未 set | ❌ 0 cron / 0 task | **Code-Ready · Operationally-Dormant** |
| **OpenAI** (GPT-4o/o1) | ✅ Yes (`98b76cce`) | ✅ Yes (`openai>=1.55.0`) | ❌ | ❌ | ❌ | **Code-Ready · Operationally-Dormant** |
| **DeepSeek** (Chat/Reasoner) | ✅ Yes (`98b76cce`) | ✅ Yes (sklearn-compat OpenAICompatProvider) | ❌ | ❌ | ❌ | **Code-Ready · Operationally-Dormant** |
| **Perplexity** | ❌ enum 標記 only | ❌ 無 SDK | ❌ | ❌ | ❌ | **Skeleton-Only**（`perception_data_plane.py` SEARCH_PERPLEXITY enum + provider_keys_store 白名單 + tab-ai.html UI 但**無 PerplexityClient class**）|
| **Google Gemini** | ❌ | ❌ | ❌ | ❌ | ❌ | **Skeleton-Only** |
| **Ollama 9B** | ✅ Yes | N/A 本地 | ✅ N/A 不需 | ✅ http://127.0.0.1:11434 | ✅ Rust StrategistScheduler 5min | **Production-Active**（但 100% rejected） |
| **Ollama 27B** | ✅ Yes | N/A | ✅ | ✅ | ❌ 0 scheduler | **Code-Ready · Operationally-Dormant** |
| **LM Studio**（Mac dev shim） | ✅ shim layer | N/A | N/A | ✅ env switch `LOCAL_LLM_PROVIDER=lm_studio` | ❌ | **Code-Ready**（dev only） |

**Tier 2/3 fallback config 落地完整度**（`98b76cce`）：
- `Layer2Config.fallback_tier2_provider=deepseek` / `tier2_threshold=0.5`
- `Layer2Config.fallback_tier3_provider=anthropic` / `tier3_model=haiku` / `tier3_threshold=0.85`
- `_resolve_effective_provider(role='triage'|'agent')` real implementation OK
- 但 daily_spend_pct 永遠 0/$150=0% → 永遠走 base_provider，fallback 從未觸發

---

## §5 實際可用度端到端鏈條（每步 % + 證據）

**鏈條 A：Layer 2 Anthropic L1 Triage（從 trigger → response → cost log）**

| Step | % 可用 | 證據 |
|---|---:|---|
| 1. Trigger 入口 | 100 | `POST /api/v1/paper/layer2/trigger` endpoint 存在；layer2_routes.py:174 |
| 2. ANTHROPIC_API_KEY 注入 | 0 | `os.getenv("ANTHROPIC_API_KEY", "")` 必返回 ""；layer2_engine.py:190 `if not api_key: return None` |
| 3. anthropic SDK call | N/A | 因 key 缺 short-circuit；不會抵達 |
| 4. cost_tracker.record_call | N/A | 不會抵達 |
| 5. learning.ai_usage_log INSERT | N/A | 0 row all-time |
| **端到端可用率** | **0%** | provider_keys_store dir 空 + ANTHROPIC env 0 byte = 即使 GUI 按鈕硬點也只會走 `_l1_triage_local` Ollama fallback |

**鏈條 B：Strategist Ollama 9B（IPC → infer → cost log）**

| Step | % 可用 | 證據 |
|---|---:|---|
| 1. Rust StrategistScheduler 5-min tick | 100 | engine.log 8 cycle in 50min |
| 2. IPC `ai_service.sock` 連接 | 100 | sock listening + 2 LISTENING streams |
| 3. ai_service.py `strategist_evaluate` handler | 100 | dispatch table:80 `strategist_evaluate=15.0` TTL |
| 4. llm_call_wrapper.call_ollama_judge_edge | 100 | guardian/analyst 也用同一 wrapper |
| 5. Ollama qwen3.5:9b 推理 | 100 | runner alive 6.5GB RSS |
| 6. param proposal 回 Rust | 100 | engine.log 看到具體值 17.15/31.85 |
| 7. **delta cap acceptance** | **0** | 8/8 cycle WARN `delta exceeds 30% cap` |
| 8. ai_usage_log INSERT | 0 | 0 row（Rust 端不寫 PG ai_usage_log）|
| **端到端可用率** | **取決於指標**：「Ollama 真被呼叫」=87.5%；「proposal 真被 commit」=**0%** | |

**鏈條 C：MLDE shadow_advisor → param application（demo 真活）**

| Step | % 可用 | 證據 |
|---|---:|---|
| 1. edge_estimator_scheduler 觸發（hourly leader）| 100 | leader.lock 存在 |
| 2. mlde_shadow_advisor.generate_recommendations | 100 | 7d 5209 row |
| 3. mlde_demo_applier 24h 469 attempts | 100 | 24h `created_by=mlde_demo_applier` 行 |
| 4. dedupe filter | 88 skip | 1941/2041 = `reason=dedupe` |
| 5. IPC engine.sock apply | 95 | 30/2398 = "Not connected" 錯誤 |
| 6. status=applied 真寫入 RiskConfig | 100 | 277 row 真 commit |
| 7. PnL attribution 跡象 | **0** | mlde_param_applications 無 close_pnl_bps 欄位；無 attribution writer |
| **端到端可用率** | **applied=true rate 11.5%（277/2398）；attribution=0%** | |

**鏈條 D：CostEdgeAdvisor（DOC-08 §3 Gate 13 應該 fire 但從未 fire）**

| Step | % 可用 | 證據 |
|---|---:|---|
| 1. Rust slot 預留 | 100 | `cost_edge_advisor_slot_handle = ipc_server.cost_edge_advisor_slot()` (main.rs:458) |
| 2. env-gated spawn | 0 | `OPENCLAW_COST_EDGE_ADVISOR=1` 未設；engine env grep 不到（cost_edge_advisor_boot.rs:145 disabled log） |
| 3. daemon spawn | 0 | 不會抵達 |
| 4. ratio = ai_spend_7d/paper_pnl_7d 計算 | 0 | 不會抵達 |
| 5. learning.cost_edge_advisor_log INSERT | 0 | all-time 0 row（confirmed） |
| **端到端可用率** | **0%** | 原則 13「cost_edge_ratio ≥ 0.8 建議關倉」**從未 fire** |

---

## §6 cost_edge_ratio + Modulator + Distiller dead/alive

| 模組 | dead/alive | 證據 | 復活路徑 |
|---|---|---|---|
| **CostEdgeAdvisor** | **dead-by-env**（code-ready, env-gated OFF） | OPENCLAW_COST_EDGE_ADVISOR 未設 + cost_edge_advisor_log 0 row all-time | 1. set env=1 + restart 2. 確認 daemon spawn log 3. 等 7d 累積 ai_spend > 0（先要 L2 通流）才有意義 |
| **CognitiveModulator** | **alive**（真接 + 真讀） | strategist_cognitive.py:174 `params = agent._cognitive_modulator.get_all_params()` 真被 apply_decision_thresholds 用；test_cognitive_modulator_coverage 存在 | 已活；只缺「scan_interval 動態調整對 Scout→Strategist 調用次數的 effect」**dedicated metric log**（AI-E profile 點名觀察項）|
| **DreamEngine** | **alive**（真寫 24h 391 row） | edge_estimator_scheduler:587 hourly call；shadow_recommendations 24h source=dream_engine 391 | 已活；零 LLM 成本（純隨機）；Modulator 經由 `mlde_shadow_advisor.generate_recommendations()` 接消化 |
| **ContextDistiller** | **does-not-exist** | `find -name "*distiller*"` 全 codebase 0 hit；profile/memory 提到的「V3 報告 ~450 tokens」是 **hypothetical spec 未 IMPL** | 1. 確認設計（spec 路徑）2. IMPL（PA → E1 → E2 → E4）3. 注入 layer2_engine.run_session prompt 構建處 |
| **HStateCache**（Rust slot 對等的 ContextDistiller） | **dead-by-env** | `OPENCLAW_H_STATE_GATEWAY=1` 未設（CLAUDE.md §五 P1-FAKE-3）| 同 CostEdgeAdvisor |
| **Layer2Engine autonomous loop** | **dead-by-design**（only manual trigger） | layer2_routes.py 唯一寫入點 `POST /trigger`；無 cron / 無 asyncio.create_task | 設計 autonomous scheduler（hourly cycle / event-driven）|

---

## §7 AI 學習回路真實性 verdict

| 學習回路 | 真假 | 過去 7d/30d attribution 證據 |
|---|---|---|
| **Online fine-tune**（任何模型權重更新） | ❌ 假 | LightGBM ONNX 4/24 後從未重訓；model_registry 只 3 row（4/24）；scorer_trainer.py 4/25 後 0 invoke |
| **Retrieval cache**（embeddings / vector store） | ❌ 不存在 | 無 chromadb / faiss / pgvector callsite；layer2_engine 無 cache 持久化 |
| **MLDE shadow → param feedback loop** | ✅ **真**（part-only） | 7d 5209 shadow + 277 真 applied + 33 live_promotion candidate；但 `decision_outcomes` PnL feedback 仍 timeframe 字串不一致 → 大部分 outcome NULL |
| **DreamEngine replay seed 學習** | ✅ **真**（無 LLM） | 24h 391 row dream_engine source；evidence_source_tier=`real_outcome` |
| **Edge estimator JS（James-Stein）** | ✅ **真** | learning.james_stein_estimates 864 row（all-time），continuous update；7d 真活 |
| **LinUCB（contextual bandit）** | ⚠️ partial | linucb_state 15 row 自 4/24 後 LinUcbRuntime cold-start 真活；experiment_ledger=0 / archive=0 → 探索-利用閉環未閉 |
| **過去 7d/30d 對交易結果的 attribution** | ❌ **不可量化** | mlde_param_applications 表無 close_pnl_bps 欄位；attribution writer 仍 84.6% `attribution_chain_ok=false`（CLAUDE.md §三 #11）；FA-H6 `est_net_bps` 100% NULL |

**Verdict**：**有「學習資料層」但無「學習 → 交易結果 attribution 層」**。系統有 6.7M decision_features + 1.4M scorer_features + 559k mlde_edge_training_rows + 864 JS estimates + 5209/7d shadow recommendations，**這些都是真資料**，**但沒辦法說「過去 7d 因為 ML 推理多賺/少賠 N USDT」** — 因為 attribution writer 缺 84.6% chain。

---

## §8 Token cost ROI + 預期 cloud L2 啟用 cost projection

**現狀（真實）**：
- 24h cost: $0.00（L2 全 dormant）
- 7d cost: $0.00
- 30d cost: $0.00
- ROI = (攻擊 PnL + 防禦價值) / AI 總花費 = 不可計算（除以 0）

**若 cloud L2 啟用後預期成本**（按 `98b76cce` 設計 + 假設 daily 推理量）：

| 假設場景 | 配置 | 預估 daily cost | 月成本 | DOC-08 cap |
|---|---|---:|---:|---|
| L1 Triage all（24/24h trigger）| Anthropic Haiku × 100 trigger × 1k tokens | $0.025 | $0.75 | $2/day OK |
| L1 + 5x L2 Sonnet 深度推理 | Sonnet × 5 × 10k tokens | $0.15 | $4.5 | OK |
| 全力 advisory（hourly L1 + 3x daily L2）| 24×Haiku + 3×Sonnet | $0.05 + $0.09 = $0.14 | $4.2 | OK |
| 同上 + DeepSeek tier2 fallback | 50% spend > $0.075 → DeepSeek（10x cheaper） | $0.07 | $2.1 | OK |
| Stress 場景（Strategist 每 5min 調 L2）| 288 × Sonnet × 5k = $4.32 | $4.32 | $130 | **超 $2 daily cap** |

**結論**：
- **DOC-08 daily $2 cap 在合理使用下完全 ok**（即使 5 個 sonnet 深度 + 100 haiku triage 也只用 $0.18/day = 9% cap）
- **超 cap 風險點**：Strategist 每 5min 調 L2（這正是現在 Ollama 路線的場景；若直接搬到 cloud 會 disaster）
- **Tier 2/3 fallback 設計合理**：DeepSeek-Chat 約 $0.27/M input vs Sonnet $3/M（11x 便宜），50% threshold 自動切換是好機制

**ROI 計算公式**：在 L2 真有流量後，**第一個月不要算 ROI**，因為：
1. 沒有 baseline pre-L2 PnL
2. attribution chain 84.6% NULL，無法 isolate AI 貢獻
3. 真正可比較需要：(a) 開 L2 advisory 30d (b) 同期 paper L0-only 對照組 (c) 對照 net edge bps

---

## §9 Top 5 AI ROI 紅旗

| # | Finding | 嚴重 | Cost | 建議 |
|---|---|---|---|---|
| 1 | **provider_keys_store 目錄空 + ANTHROPIC_API_KEY env 0 byte** = `98b76cce` 整個 PR 對 production 0 effect；只有「GUI 顯示得了 store key」這個能力 | 🔴 P0 | $0 浪費（0 token used）但 **資源規劃浪費**（10/8 commit 把碼接好但 5 月 8 日 0 流量）| Operator 透過 GUI 寫一次 ANTHROPIC_API_KEY，啟用 L1 Triage 試運行 7d；先別開 L2 全力 |
| 2 | **Strategist 8/8 cycle 全 delta>30% rejected** — Ollama 真被 IPC 但 q4 量化高方差輸出永遠超 cap | 🟠 P1 | 0 effect | 提高 max_param_delta_pct 到 50% **或** 改用 Ollama 27B（更穩定）**或** 改為「Strategist propose → Guardian validate」軟接受 |
| 3 | **CostEdgeAdvisor env-gated OFF** — 原則 13 從未 fire；無「ratio ≥ 0.8 建議關倉」訊號 | 🟠 P1 | dormant | `OPENCLAW_COST_EDGE_ADVISOR=1` + restart；先觀察 7d ratio 真實值，再考慮 fire policy |
| 4 | **5 ML 訓練腳本（thompson/optuna/cpcv/dl3/weekly_report）全 0 cron**：4/6-4/27 後 9-32 天無 invoke | 🟡 P2 | 訓練資料積壓 | 至少 weekly_report 應 sunday 03:00 cron；optuna sweep weekly；其他按需 |
| 5 | **MLDE 7d 11.5% applied rate（277/2398）+ 30 IPC fail + 17 PG transaction error** | 🟡 P2 | engine.sock 連接不穩 | 增 IPC retry / fix transaction abort root cause；提高 dedup 智慧度（1941 dedupe / 7d 過於激進） |

---

## §10 「AI 給玄衡帶來什麼真實價值」誠實答案 + advisory-active prerequisite

### 誠實答案

**現在（2026-05-08）AI 帶給玄衡的真實價值**：

✅ **真實有的**：
1. **MLDE shadow recommendations 7d 5209 row**（mlde_shadow_advisor + dream_engine）作為 demo 環境「替代假設探索層」 — 雖然 88% skip 但有 277 真 applied，是少數真活的「AI 影響策略參數」回路
2. **DreamEngine 24h 391 row** 純本地隨機 + replay 統計，零 LLM 成本，提供 counterfactual scenario seeds → 給 Modulator 用
3. **CognitiveModulator** 真活，真調整 confidence/qty thresholds（雖然量化效果無 dedicated metric）
4. **Strategist Ollama IPC 鏈路真通**：Rust → ai_service.sock → llm_call_wrapper → Ollama 9B；驗證了「本地 LLM 接入」這個基礎能力
5. **decision_features 9.47M / scorer_features 1.4M** 學習資料層真在累積（雖然 attribution chain 缺，這些 feature 仍可離線重訓）

❌ **假的或不存在**：
1. **Layer 2 雲端推理對 production 0 contact**（98b76cce 漂亮地接好，0 流量）
2. **5-Agent 真實訊息流 0**（agent.messages/state_changes 全 row proof）
3. **AI 對交易結果的 attribution 0%**（attribution writer 84.6% chain failed + FA-H6 NULL）
4. **ContextDistiller 不存在**（profile/memory 提到的 V3 ~450 tokens spec 是 future plan）
5. **CostEdgeAdvisor 從未 fire**（原則 13 名存實亡，因 spec 0 row all-time）
6. **5 ML 訓練腳本** 9-32 天無 invoke（thompson/optuna/cpcv/dl3/weekly_report）

### 達 advisory-active 的 prerequisite 清單

要從現狀（codebase advisory-ready, runtime advisory-dormant）進到 **「AI 真實對 demo 帶來可量化價值」**：

| # | Prerequisite | 工作量 | 阻塞層 |
|---|---|---|---|
| 1 | **GUI 寫入 ANTHROPIC_API_KEY**（透過 tab-ai.html，1 分鐘）| trivial | operator |
| 2 | **Layer2 Trigger 1 次 manual L1 triage** 驗端到端鏈路 | 5min | operator |
| 3 | **Strategist max_param_delta_pct 從 30%→50%**（或換 27B 模型）| 1d | E1+E2+E4 |
| 4 | **OPENCLAW_COST_EDGE_ADVISOR=1**（env + restart）| 30min | operator |
| 5 | **attribution writer 修 84.6% chain failed**（FA-H6 + MIT-S2-1）| 1-2 sprint | E1 + MIT |
| 6 | **5 ML 訓練腳本 cron 化**（至少 weekly_report sunday + scorer monthly）| 0.5d | operator |
| 7 | **「AI advisory ROI 月報」自動產出**（基於 cost vs realized edge bps）| 1 sprint | E1 + AI-E |
| 8 | **Layer2 autonomous loop**（hourly L1 triage cron）| 1 sprint | E1 |
| 9 | **ContextDistiller IMPL**（profile spec → code）| 1 sprint | PA + E1 |

**最低可行 advisory-active**（達成最少 cost、能驗 AI 真實貢獻）= 1+2+4+6（共 ~1d operator + 0.5d code 工作量）。其餘為 advisory-mature 進階。

---

## 附錄 A: 工具方法

- **DB query**：`ssh trade-core "set -a; source ~/BybitOpenClaw/secrets/environment_files/.env.postgres; set +a; psql -h 127.0.0.1 -U trading_admin -d trading_ai -c '...'"`
- **engine env**：`/proc/$ENGINE_PID/environ` tr `\0\n` 拿 OPENCLAW_* / API key var
- **engine log**：`/tmp/openclaw/engine.log` 3.4MB / `api.log` 183KB（24h roll over）
- **provider_keys path**：`~/BybitOpenClaw/secrets/providers/`（dir 存在 0 file = 0 key）
- **Ollama**：`curl -sf http://127.0.0.1:11434/api/tags` 直查 model list

## 附錄 B: 關鍵 commit 與檔案

- `98b76cce`（2026-05-08 21:58）— provider_client + provider_keys_store + tier 2/3 fallback
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/provider_client.py` 622 LOC
- `.../layer2_engine.py` 826 LOC（3 callsite refactored）
- `.../layer2_types.py` PricingTable +6 + Layer2Config +6 fallback fields
- `.../provider_keys_store.py` 397 LOC
- `.../scout_agent.py` 349 / `strategist_agent.py` 799 / `guardian_agent.py` 1458 / `analyst_agent.py` 802 / `executor_agent.py` 896 = 4304 LOC

## 附錄 C: 與過往 audit 對比

| 日期 | AI 真實 cost | L2 真活 | MLDE 真活 | CostEdgeAdvisor |
|---|---|---|---|---|
| 2026-04-01 | $0 | ❌ | ❌（apply_count=0）| ❌ |
| 2026-04-24 | $0 | ❌ | ⚠️ MLDE shadow 仍 0 row | ❌（0 row all-time）|
| **2026-05-08 (本次)** | $0 | ❌ | ✅ **7d 5209 shadow + 277 applied** | ❌（0 row all-time）|

**最大進步**: MLDE pipeline 4/01 → 5/08 從 0 row 進步到 7d 5209 推薦 + 277 真 applied = **真實 AI 學習回路 4 月 24 日 → 5 月 8 日才開始活**。
**最大未變**: AI 雲端 cost 從 4/01 至今全 $0；CostEdgeAdvisor 永遠 0 row；attribution writer 永遠 84.6% NULL。
