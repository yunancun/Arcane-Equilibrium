# AI-E Verification v3 — 5 Commits AI Impact + PA Redesign Cross-Check

**日期**：2026-05-09 17:00 UTC
**baseline**：`faf2d131` → HEAD `da2aba11`（5 commits）
**v2 reference**：`docs/CCAgentWorkSpace/AI-E/workspace/reports/2026-05-09--ai_effectiveness_verification_v2.md`
**PA redesign**：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--full_loss_architectural_root_cause_redesign.md`
**模式**：對抗性嚴苛 cross-check；不採信 commit message，只信 runtime + PG 直查

---

## Executive Summary（一段）

5 commits 全為 source-only / source+test，**0 個 commit 改變 AI runtime 流量結構**。Engine PID 298034 啟動於 15:52，5 commits 全部 17:01-18:41 提交 — runtime 仍跑 commit 前的舊 binary。**24h ai_invocations = 0、cost_edge_advisor_log all-time = 0、ai_invocations latest = 2026-05-06 22:04（3+ 天無寫）**，與 v2 完全一致。

**對 PA redesign 的 AI-E verdict：PARTIAL AGREE**。PA 主張的 4 個 AI/Layer2 claim 全部 source-true：(1) Strategist 在當前架構是 dict[str,float] 微調器 ✅；(2) Strategist scope 應重定義為 alpha-source orchestrator ✅；(3) Layer 2 ADR-0020 manual-only by design ✅；(4) Analyst L2-L5 dormant ✅。但 PA 「需要 Cloud L2 autonomous loop 才能孵化 alpha」的隱含假設與 ADR-0020 fail-closed 衝突；從 AI cost / governance 視角，operator 選擇 manual-only **合理**（Cloud L2 autonomous loop 在當前 ai_invocations writer 架構漏寫的情況下會盲飛），不是過度保守。

---

## A. 5 Commits AI 影響（commit-by-commit verdict）

### A.1 `c2ab7b1a strategist: teach wide adjustment skill`

**diff 結構**：
- Python `ai_service_dispatch.py` +86 LOC：`_build_strategist_prompt` 加 `normal_delta_pct` / `max_delta_pct` 參數，prompt text 加 `Strategist Skill: Wide Parameter Adjustment` block
- Rust `strategist_scheduler/evaluate.rs` +81 LOC：`build_strategist_eval_payload` 包 `strategist_skill: {name, normal_delta_pct, max_delta_pct, description}` 進 IPC payload
- Test：1 Rust unit test（pure JSON assert，不調 LLM）

**LLM-driven？** **NO**。完全是 prompt engineering。Ollama L1 9B 仍然是執行體，只是 prompt 加了「教 LLM 如何分辨 30% 範圍 vs 30%-50% 範圍」的指令。**不接 Layer 2，不接 Cloud LLM，不增 cost**。

**ai_invocations 同步？** **NO**。grep 證實 `ai_service_dispatch.py` / `ai_service.py` / Rust strategist_scheduler **0 個 record_ai_invocation 調用**。Strategist L1 9B 流量永遠不會寫 `agent.ai_invocations` table（v2 NEW-5 仍 active）。

**runtime 生效？** **NO**。Engine PID 298034 啟動 15:52 早於 commit ts 17:40 共 1h48min。5-min cycle 仍跑舊 binary 的 hardcoded `max_delta_pct=0.30`，新 wide_skill_range guidance **未進 prompt**。

**verdict**：✅ commit message 自承「no runtime reload, provider call, DB write, or live auth mutation」— 誠實 source-only。但 PA 與 Operator 的 mental model 是「Strategist 已能用 30%-50% 範圍」， runtime 還沒拿到。需 `restart_all --rebuild` 才生效。

### A.2 `48227607 learning: push promotion evidence from edge cycle`

**diff 結構**：
- New `program_code/ml_training/promotion_evidence.py` +558 LOC（DSR/Sharpe/PBO/CSCV 計算）
- New `sql/migrations/V079__promotion_evidence_trial_ledger.sql` +67 LOC
- `edge_estimator_scheduler.py` +120 LOC wire `_run_promotion_evidence_push`

**需要 LLM 推理？** **NO**。完全是 numpy-based 統計：
- `_sharpe()`, `_dsr_*()`, `_pbo_*()`, `_cscv_*()` 全純數學
- grep `program_code/ml_training/promotion_evidence.py` 對 `ollama|claude|anthropic|deepseek|llm` 命中 0
- DSR (Bailey & Lopez de Prado deflated Sharpe) 是封閉式公式
- PBO (Probability of Backtest Overfitting) 是 CSCV-based 統計
- 完全不需要 LLM「解釋」這些 score；統計閾值由 governance 預定（min DSR, max PBO threshold）

**runtime 生效？** **NO**。
- V079 在 PG 中**未 apply**（`SELECT version FROM _sqlx_migrations WHERE version >= 75` 顯示最高 78）
- promotion_evidence push 路徑會 fail-soft on missing `learning.strategy_trial_ledger` table
- Engine PID 298034 啟動 15:52 早於 commit 18:03，新 wire 不在 binary 裡

**verdict**：✅ commit message 自承「source/test level only」— 誠實。AI-E 補充：DSR/PBO 數學完全不需 Cloud LLM；任何 PA-style「Cloud LLM 來解釋 promotion evidence」設計都是過度設計，本地 numpy 已足。

### A.3 `da2aba11 audit: correct f08 ml cron scope`

**diff 結構**：
- `helper_scripts/cron/ml_training_maintenance.py` +511 LOC：`CORE_JOBS` (5 ops) + `AUDIT_JOBS` (5 v2 audit-required: thompson/optuna/cpcv/dl3/weekly_report)
- 加 `_weekly_audit_due()` 限 weekday
- 加 `--force-audit-jobs` flag

**LLM-driven？** **NO**。grep 0 LLM keyword。全是 Python orchestration + module entry point dispatch。

**cron installed？** **NO**。Linux crontab 直查（filter comments）：8 active entries，仍無 `ml_training_maintenance` 或 `ml_training_maintenance_cron.sh`。本 commit 仍是 source-only fix，operator 0 activation 自 v1 audit 算起 2 天內均未做。

**verdict**：✅ commit message 自承「W-AUDIT-4 partial until runtime cron installation and row evidence are verified」— 誠實 source-only。**但這是 v1 NEW-2 P0 fake-fix issue 第 3 次 source-only 修復**（v1 268f9470 / v2 a904e273 / v3 da2aba11）。三次 commit 0 cron 安裝。

### A.4 `c081029d governance: freeze blocked symbol lists`

**LLM 影響**：0。governance freeze + JSON registry + static guard test，純 governance hygiene。

**verdict**：✅ AI-E 不適用。

### A.5 `ad14db07 strategy: guard bb breakout donchian snapshots`

**LLM 影響**：0。indicator look-ahead bias guard，pure Rust regression test。

**verdict**：✅ AI-E 不適用。

---

## B. 24h Real AI Flow vs v2

| 指標 | v2 (16:35) | v3 (17:00) | Delta | verdict |
|---|---|---|---|---|
| `ai_invocations` 24h | 0 | 0 | 0 | dormant 持續 |
| `ai_invocations` all-time | (~2) | 2 | 0 | latest 2026-05-06 22:04（3 天無寫） |
| `cost_edge_advisor_log` 24h | 0 | 0 | 0 | dormant 持續 |
| `cost_edge_advisor_log` all-time | 0 | 0 | 0 | env 仍未設 |
| `mlde_shadow_recommendations` 24h | (~902) | 1076 | +174 | 自然漂移 |
| `mlde_param_applications` 24h | (~514) | 514 | 0 | 持平 |
| `strategist_applied` 24h | 221 | 213 | -3.6% | 自然漂移；v1→v2→v3 = 354→221→213 持續衰減否定 v1「hidden fix」假設 |
| Cloud L2 24h cost | $0 | $0 | 0 | providers/ 仍 0 file |
| `experiment_ledger` all-time | 未測 | 0 | - | **NEW finding：hypothesis pipeline runtime 0 production** |
| `pattern_insights` all-time | 未測 | 0 | - | **NEW finding：Analyst L2 pattern claims runtime 0 production** |

**24h ai cost: $0**（與 v1/v2 一致；Cloud L2 0 keys）
**24h ai_invocations: 0**（與 v2 一致；Strategist L1 9B 流量仍不寫此表）

---

## C. PA Redesign Cross-Check（AI-E 視角）

### C.1 PA Claim 1：「Strategist 在當前架構就是 dict[str, float] 微調器」

**Source verification**：
- `strategist_agent.py:128` `_REGIME_STRATEGY_PREFERENCES: Dict[str, Dict[str, float]]` — 4 regime × 5 strategy hardcoded weight ✅ confirmed
- 本次 commit c2ab7b1a 加 `strategist_skill: wide_parameter_adjustment` 但本質仍是「教 LLM 在 ±50% 內調 dict[str, float]」 — **進一步證實 PA claim**
- LLM call payload 由 `build_strategist_eval_payload`（Rust）→ Ollama L1 9B → 回 dict[param, value] 給 Rust apply
- 沒有任何 code path 讓 Strategist：
  - 提議新 alpha source（`grep AlphaSourceRegistry / propose_alpha_source` = 0 hit）
  - 改變 strategy 數量
  - 跨 strategy 設計新組合
  - 提議 new TickContext 字段
- v2 Strategist 8/8 cycle delta>30% rejected（v2 Memory）+ v3 strategist_applied 持續衰減 213/24h 也支持 PA：能調的範圍越來越窄 / 樣本越來越少

**AI-E verdict on PA Claim 1**：✅ **AGREE**。本次 c2ab7b1a 「wide skill range」commit 是這個結構性問題的代表性失敗 — 加了 prompt engineering 教 LLM 用 50% 而非 30%，但本質仍是 dict 微調。**這個 commit 在 PA 的視角下是反證**：架構越強化 prompt engineering，越遠離 alpha-source orchestrator。

### C.2 PA Claim 2：「Strategist scope 應重定義為 alpha-source orchestrator」

**Source feasibility check from AI-E**：
PA 提的 R-2 動作（Strategist scope reframe + AlphaSourceRegistry）需要哪些 AI capability：
- L0（rule-based）：alpha source registry CRUD、active/observing/deprecated/sunset state machine — **足夠**
- L1（Ollama 27B）：「ranging regime + funding 散度 1.8σ → 提議 funding-skew-spread alpha source」這類「pattern → hypothesis」推理 — **足夠**（Ollama 27B 已有，本地 0 成本）
- L1.5（Haiku/Perplexity）：sentiment / 跨資產新聞收集 — Perplexity 仍 0 IMPL，Haiku 是可選增強
- L2（Cloud Claude/DeepSeek/OpenAI）：複雜統計模型設計 / 跨領域 alpha factor 構造 — 對 alpha proposal 是 **加分項，非必需**

**AI-E verdict on PA Claim 2**：✅ **AGREE 但 push back PA 隱含假設**。PA 在 R-2 寫「Strategist Layer 2 解封路徑：alpha-source proposal 是合適的 Layer 2 cloud reasoning 場景」— 暗示需要 Cloud L2 才能做 alpha-source orchestrator。**這個假設不成立**：Ollama 27B 對「regime + funding skew → propose funding spread strategy」這類推理綽綽有餘（zero-shot pattern → hypothesis 是 LLM 強項）。Cloud L2 應只當「冷啟動 / 跨領域罕見 case 升級」用，不是 R-2 的前置條件。

### C.3 PA Claim 3：「Analyst L2-L5 全 dormant，且 ADR-0020 把 Layer 2 永久標 manual + supervisor-only by design」

**Source verification**：
- ADR-0020 `0020-layer2-manual-supervisor-only.md` 直查：「Layer2 must not run as an autonomous trading loop」「The planned hourly Layer2 autonomous loop is sunset unless a future ADR explicitly reverses」 ✅
- Analyst L2 source 存在：`analyst_pattern_claims.py` + `experiment_ledger.py` IMPL CRUD 完整
- **但 runtime 0 production**：
  - `learning.experiment_ledger` 0 rows all-time
  - `learning.pattern_insights` 0 rows all-time
  - PA 主張正確：source ✅ wired but runtime ❌ silent

**ADR-0020 與 PA 主張「Analyst hypothesis-experiment loop」衝突分析**：
- ADR-0020 鎖的是 **Layer 2 (cloud LLM)** 不能跑 autonomous trading loop
- PA 主張的是 **Analyst (本地 L0+L1)** 的 hypothesis-experiment loop
- **兩者 NOT 衝突**：本地 L0+L1 跑 Hypothesis Pipeline 完全不違反 ADR-0020；Cloud L2 仍 manual。
- 但 PA report 在 R-2 / Layer 4 寫的「Layer 2 alpha-source proposal loop」會違反 ADR-0020 — **這是 PA report 的細節矛盾**，需 PA 自己澄清是「Layer 2 cloud autonomous」還是「Layer 1 本地 autonomous + Layer 2 manual escalation」

**AI-E verdict on PA Claim 3**：✅ **AGREE source claim**；⚠️ **PA report 在 R-2 對 Layer 2 解封的暗示應澄清為 "Layer 1 autonomous + Layer 2 manual escalation"**，否則跟 ADR-0020 直接衝突。

### C.4 ADR-0020 fail-closed 從 AI cost / governance 視角是合理還是過度保守？

**AI-E 對抗性分析**：

**支持 ADR-0020 manual-only 的理由（合理選擇）**：
1. **Cloud L2 流量 24h $0 是 dead-AI 假合規**（v2 verdict），但 ADR-0020 manual-only 的「假合規」比 autonomous loop 的「真失控」損失小 4-5 個量級
2. 當前 `agent.ai_invocations` writer path **完全沒接 Strategist L1 9B 流量**（grep 證實）— 在 writer path 修好前，autonomous loop 會盲飛無 cost tracking → 違反 §二 原則 13 (AI cost 感知)
3. Cloud L2 cost 上限 DOC-08 ＄2/日 在 autonomous loop 下會被 5-min cycle × 3 agents × prompt 大小 trivially 觸頂
4. ADR-0020 fail-closed 防止「ANTHROPIC_API_KEY 一旦設了就無上限燒錢」的災難

**反對 ADR-0020 manual-only 的理由（過度保守）**：
1. PA 主張的 R-2 alpha-source orchestrator 是合理用例，但 PA 也承認可降為 Layer 1 本地（見 C.2 push back）
2. Layer 2 manual + supervisor 確實意味著 24/7 alpha discovery 不可能（依賴 operator 線上）
3. v2 KPI 中 3 個 (cost / latency / ROI) 因 Layer 2 0 流量永久不可量測 → DOC-08 framework 本身需重新設計

**AI-E verdict on Operator's choice**：**合理，不是過度保守**。理由：
- 在 ai_invocations writer path 全棧接通前 + cost_edge_advisor_log 寫入流暢前 + Cloud L2 keys 存在期間有 budget cap 自動執行前，autonomous Layer 2 是 governance 災難
- ADR-0020 為這 3 個前置條件爭取了時間
- 但 AI-E push back：ADR-0020 應有 **explicit unblock conditions**（不只是「future ADR」），例如「條件：(1) ai_invocations writer 100% 覆蓋 L0/L1/L1.5/L2 + (2) BudgetTracker 真接 layer2_engine + (3) cost cap 自動 fail-closed runtime tested」

### C.5 PA Layer 4 「W-AUDIT-4 ML 基座 應併入 R-3 Hypothesis Pipeline」從 AI-E 視角

PA 主張 W-AUDIT-4 (5 ML 腳本 + feature_baselines + outcome backfill) **不要單獨做**，併入 Hypothesis Pipeline。

**AI-E supporting 證據**：
- v3 da2aba11 是 W-AUDIT-4 F-08 第 3 次 source-only patch，cron 仍未裝 — 證實 ML 腳本散裝化是治理失敗模式
- experiment_ledger 0 rows / pattern_insights 0 rows = 沒有 hypothesis 來解釋特徵 → MLDE 訓練在做什麼？只是「特徵 → outcome」黑箱統計
- 這跟 PA 「修 5 個 OHLCV 策略仍 gross negative」結論同源：**沒有 hypothesis frame，ML 訓練永遠是「對歷史 fit 但無泛化邏輯」**

**AI-E verdict**：✅ **AGREE PA Layer 4 重排**。

---

## D. v2 → v3 KPI Delta

| KPI | v2 verdict | v3 verdict | 變化 |
|---|---|---|---|
| 每日 AI 成本 < $2 | $0 dead-AI 假合規 | $0 dead-AI 假合規 | 持平 |
| L1 Ollama 延遲 < 3s | 不可量測 | 不可量測 | 持平 |
| AI ROI ≥ 0.5 | X/0 未定義 | X/0 未定義 | 持平 |
| cost_edge_ratio F < 5% | 不可量測 | 不可量測 | 持平 |

**全部 4 KPI 連續 v1→v2→v3 全綠（dead-AI 假合規）**。AI-E 建議 DOC-08 KPI framework 重新設計，加入「KPI 可量測性」前置條件（writer path 真覆蓋 L0/L1/L1.5/L2）。

---

## E. v3 NEW Findings（不在 v2）

### E.1 P0 — Strategist L1 9B 流量永遠不會寫 ai_invocations table（v2 NEW-5 升級）
- v2 NEW-5 提出懷疑，v3 證實：grep `record_ai_invocation` 在 `ai_service_dispatch.py` / `ai_service.py` / Rust strategist_scheduler **全部 0 hit**
- 寫入點僅 guardian_agent / strategist_edge_eval / analyst_agent / openclaw_supervisor_policy
- 結果：DOC-08 KPI 用 `ai_invocations` 度量 Strategist Ollama 流量是錯的測量點
- 修復方向：`AIService.evaluate_strategist` 收 Ollama response 後 call `record_ai_invocation(provider='ollama', model='qwen3.5:9b', tier='l1', purpose='strategist_evaluate', ...)`
- 影響：實質 8/8 5-min cycle Ollama 流量 24h ~288 invocations × 5 agents 都不在 ai_invocations table 裡

### E.2 P1 — V079 promotion_evidence trial_ledger migration 未 apply
- 48227607 commit V079 sql 兩端存在但 PG 中無 strategy_trial_ledger 表
- promotion_evidence push 即使 wire 也會 fail-soft on missing table
- 修復方向：(a) auto migrate `OPENCLAW_AUTO_MIGRATE=1` + restart 或 (b) 手動 `bash helper_scripts/linux_bootstrap_db.sh --apply`

### E.3 P1 — experiment_ledger / pattern_insights 全 0 row 但 source IMPL 完整
- 證實 PA Claim 3 主張「Analyst L2-L5 dormant」runtime 真實
- 修復方向：Analyst L2 IMPL trigger（5-min cycle 或 24h cycle）真接 `record_observation()` → experiment_ledger INSERT
- Notes：本地 L0+L1 跑 hypothesis pipeline 不違反 ADR-0020

### E.4 P1 — ContextDistiller v2 NEW-3 closed (35f81a7b) 但 layer2_engine 是 ADR-0020 manual-only
- ContextDistiller IMPL 完整 + layer2_engine.py 真 import 真調 `distill_for_prompt()`
- 但 Layer 2 ADR-0020 manual-only → ContextDistiller 永遠 runtime-dormant by design
- AI-E 不建議廢 ContextDistiller（manual escalation 用得到），但 profile.md 「token 預算」spec 仍不可量測

### E.5 P2 — c2ab7b1a wide_skill_range commit runtime 未生效
- Engine PID 298034 啟動 15:52，commit 17:40 → 18:41 全部在 engine 啟動後
- 5 commits 均 source-only/source+test，無 `restart_all --rebuild` deploy
- Operator 期望 Strategist 開始用 50% 範圍是 wishful thinking，runtime 仍跑舊 0.30 hardcoded

---

## F. 對 AI-E 自身的 self-correction（v3 vs v2）

### F.1 v2 「Strategist applied 衰減 354→221 (-37.6%) 否定 hidden fix 假設」延伸驗證
- v3 strategist_applied 24h = 213，v2→v3 從 221 →213 (-3.6%)
- 趨勢：v1 354 → v2 221 → v3 213
- v2「自然漂移非 hidden mechanism」假設成立
- 但 v3 NEW finding E.1 揭示：strategist_applied 寫入的是 `learning.strategist_applied_params`（commit log 級表），不是 `agent.ai_invocations`（AI invocation 級表）。兩者是不同維度的紀錄
- **AI-E v2 結論「ai_invocations 24h=0 = dead-AI」需 nuance**：實際是「ai_invocations writer path 不覆蓋 L1 9B Strategist 流量」，runtime AI 確實活躍（strategist_applied 24h 213 + mlde 1076）

### F.2 v2 「ContextDistiller IMPL ✓ / runtime-dormant by AMD §4 design」確認
- v3 grep 證實 ContextDistiller 在 layer2_engine 真 wire 但 layer2_engine 是 ADR-0020 manual-only → runtime-dormant 結論 hold
- 但 source 不是 dead .pyc（v1 NEW-3）已 close

### F.3 v2 結論「DOC-08 4 KPI 因 0 流量永久不可量測」需澄清
- 真相：4 KPI 因「測量點選錯」永久不可量測，不是「AI 真死」
- 真實活躍 AI 量：Strategist L1 9B 5-min × 4 strategy/cycle × 24h × 5 agents ≈ 數百次/天 / mlde 1076/24h
- 修復 E.1 ai_invocations writer path 後 4 KPI 自動 unblock

---

## G. AI-E v3 推薦行動排序

### G.1 立刻可做（無新代碼，operator 5min）
1. `bash helper_scripts/restart_all.sh --rebuild --keep-auth` deploy 5 commits 進 runtime
2. apply V079 migration: `OPENCLAW_AUTO_MIGRATE=1` 重啟，或 `bash helper_scripts/linux_bootstrap_db.sh --apply`

### G.2 短期 1 sprint（修 KPI 測量）
3. **E.1 fix**：`AIService.evaluate_strategist` 包 `record_ai_invocation` adapter
4. 加 record_ai_invocation 到 ai_service.py / ai_service_dispatch.py / ai_service_guardian.py
5. cron 化 ml_training_maintenance（W-AUDIT-4 F-08 第 4 次嘗試）

### G.3 中期 2-3 sprint（PA R-2 / R-3 IMPL，AI-E 視角）
6. Analyst L2 trigger 真 spawn → experiment_ledger / pattern_insights 開始有 INSERT
7. AlphaSourceRegistry Python class（PA R-2 spec phase）
8. Strategist `propose_alpha_source()` Ollama 27B-driven（不是 Cloud L2，避 ADR-0020）

### G.4 長期 4-5 sprint（PA Layer 3 升級）
9. AlphaSurface bundle Rust IMPL (PA R-1)
10. Hypothesis Pipeline first-class (PA R-3，併 W-AUDIT-4)
11. ADR-0020 加 explicit unblock conditions

---

## H. 一段直白話給 PM

5 commits 中只有 c2ab7b1a 有「prompt engineering 級」AI 改動，其餘 4 個對 AI 流量影響為 0。**5 commits 全部 source-only**，runtime AI 流量 24h vs v2 完全持平。

PA redesign 的 Strategist / Analyst / ADR-0020 claim 在 source 層**全部成立**。但 PA 隱含主張「需要 Cloud L2 autonomous loop 才能孵化 alpha」**從 AI-E 視角不成立** — Ollama 27B 對 alpha-source proposal 推理足夠，Cloud L2 manual escalation 是合理治理選擇（避免 cost 災難 + 寫入 path 漏接時的盲飛）。

**最大 AI 治理 gap 不是 Cloud L2 沒接，是 ai_invocations writer path 漏接 L1 9B 全部 Strategist 流量 + experiment_ledger 0 row** — 這兩個修好，DOC-08 KPI framework 自動有意義，PA Layer 4 W-AUDIT-4 併入 R-3 也有 measurement basis。

當前 88 finding 患 PA 自己診斷的「修 5 個 TA 策略」近視 + 我（AI-E）診斷的「測 KPI 但測量點選錯」雙重盲區。下個 sprint 不應再加 commit 修 5 策略 / Strategist prompt，應修「治理 instrumentation」（writer path + hypothesis ledger trigger）。

---

**AI-E VERIFICATION v3 DONE**

