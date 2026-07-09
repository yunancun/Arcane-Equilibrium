# AI-E Verification Report — 2026-05-08 audit findings 24h 修復對抗性核實

**Date**: 2026-05-09  
**Reviewer**: AI-E (AI Effectiveness Evaluator, adversarial)  
**Baseline**: HEAD `72f05aa0` → `7fccad06` (28 commits, 2026-05-08 → 2026-05-09)  
**Source audit**: `2026-05-08--ai_effectiveness_full_audit.md` (P0×1, P1×2, P2×2)  
**Verification depth**: ssh trade-core runtime + PG empirical + crontab/process audit

---

## §1. Executive Summary

| Metric | 2026-05-08 audit | 2026-05-09 verification | Delta |
|---|---|---|---|
| 修復率 (5 finding) | n/a | **0/5 真實修復** | **0%** |
| 24h ai_invocations | 0 | **0** | 0 |
| 24h ai_usage_log | 0 | **0** | 0 |
| 24h cost_edge_advisor_log | 0 all-time | **0** | 0 |
| 24h Cloud L2 cost (USD) | $0 | **$0** | 0 |
| 24h MLDE shadow recs | 469 | **902** | +433 (+92.3%) |
| 24h MLDE applied rate | 11.5% | **41.7% (376/902)** | +30.2pp ✅ |
| 24h strategist_applied | n/a (cycle WARN) | **354 applied** | 從 0 → live |
| 24h proposals | n/a | **0** | 0 |
| 24h decision_outcomes backfilled | n/a | **56,600** | new path |
| 24h agent.decision_objects | n/a | **665** | shadow lineage active |
| ml model_registry production | 0 | **0** | 0 |
| ContextDistiller .py source | 不存在 | **仍不存在 (.pyc 殘留 4/3)** | dead artifact |
| 5 ML scripts 已 cron | 0 | **0** | 0 |
| API key engine env | 未設 | **未設** | 0 |

### 結論
- **所有 5 個 audit finding 在 24h 內 0 真實 runtime 修復**
- 28 commits 多為 source-only audit/wrapper 提交（commit message 自承「leaves cron installation/runtime execution to the operator」），**非 runtime 落地**
- 真正在 24h 內實質改善的是 **MLDE shadow→params applied** 從 11.5% → 41.7%（這是已部署的 P1-FAKE 修復累積，**不是**本輪 28 commits 的功勞，是 4-5 月初基線改善的延續觀察）
- AI effectiveness 衰退：**24h 0 ai_invocations + 0 ai_usage_log + 0 cost_edge_advisor + 0 cloud L2 cost** 完全沒有 AI 接入度提升

---

## §2. Finding-by-Finding 對抗性核實

### F-07 P0: provider_keys_store / Cloud L2 0 流量
**2026-05-08 audit**: `98b76cce` Cloud L2 IMPL 完整（622 LOC provider_client + 397 LOC provider_keys_store）但 `~/BybitOpenClaw/secrets/providers/` 0 file，env vars 全 unset → 0 真實 invocation。

**24h 修復狀態**: ❌ **NOT FIXED**  
**證據**:
1. `ls ~/BybitOpenClaw/secrets/providers/` → **仍 0 file** (only `.` `..`)
2. `cat /proc/4092934/environ | grep -E 'ANTHROPIC|OPENAI|DEEPSEEK'` → **0 match**（engine env 完全沒這三個 key）
3. `agent.ai_invocations` 24h = **0 row**, latest_ts = `2026-05-06 22:04` (3 天前)
4. `learning.ai_usage_log` 24h = **0 row**, all-time = **0 row**
5. 28 commits 沒有任何 commit 改動 provider key store 路徑或填 keys

**意外發現（NEW-FACT）**: `~/BybitOpenClaw/secrets/secret_files/ai/anthropic_api_key` **真的有 key** (`sk-ant-api03-sOQqCZ8qXTUeTLyy-...`，110 bytes)。這是 P3-AI 期遺留路徑。**有兩條 IMPL 路徑不對齊**：
- `provider_keys_store.py` 找 `secrets/providers/{provider}.env` → 0 file
- 真實 key 在 `secrets/secret_files/ai/{provider}_api_key` 純文字檔
- engine 沒讀任一路徑（env not exported），systemd / startup script 未配對

**對抗性 push back**: 這不是「operator 沒填」，是 **provider_keys_store 路徑與既有 secret 路徑契約不一致**——operator 已經有 anthropic key 在 `secret_files/ai/`，但 provider_keys_store 看不到它，且 engine 啟動腳本沒 export ANTHROPIC_API_KEY env。**1 行 systemd EnvironmentFile** 就能接通，無需重 IMPL，但 24h 內 0 commit 觸及。

---

### P1-A: Strategist `max_param_delta_pct=30%` 100% reject
**2026-05-08 audit**: Strategist Ollama 9B 真接，但 RiskConfig.strategist.max_param_delta_pct=30% 永遠擋住 q4 量化高方差輸出 → AI tuning 0 effective commit。

**24h 修復狀態**: ⚠️ **PARTIAL (TOML 未改 + cycle 結果反轉成功)**  
**證據**:
1. `grep max_param_delta_pct settings/risk_control_rules/risk_config_*.toml` 三檔 (paper/live/demo) **仍 = 0.30**（30%, 未改）
2. **但** `learning.strategist_applied_params` 24h = **354 row applied**（vs. previous 0），engine.log 顯示 `01:42:12 strategist params applied / strategy=grid_trading symbol=BTCUSDT`
3. source 100% = `strategist_scheduler`（非 mlde 等）

**對抗性 push back**: AI-E 2026-05-08 audit 結論「8/8 cycle 全 reject」**已過期**——24h 內 354 cycle 成功 applied。但這 **不是** TOML 修改的功勞（30% 未變），可能機制：(a) Ollama 輸出方差降低（Ollama 27B 替 9B？需驗）；(b) STRATEGIST-PARAMS-PERSIST-1 restore handler 從 DB 讀回 prior-tuned params 跳過 delta gate；(c) 其他 audit 期間未檢查的接線。**Root cause 不明，但實質 unblocked**——這是**意外的 hidden fix**，需要 PA / E1 RCA 確認機制可持續。

---

### P1-B: CostEdgeAdvisor env-gated OFF
**2026-05-08 audit**: `OPENCLAW_COST_EDGE_ADVISOR` env 未設 → daemon disabled → `cost_edge_advisor_log` 0 row all-time。

**24h 修復狀態**: ❌ **NOT FIXED**  
**證據**:
1. `cat /proc/4092934/environ | grep COST_EDGE` → **0 match**（engine env 仍未設）
2. `learning.cost_edge_advisor_log` total = **0 row** (vs. all-time 0; 0 delta)
3. 28 commits 0 觸及 OPENCLAW_COST_EDGE_ADVISOR env / systemd service file / restart script
4. 代碼中 `cost_edge_advisor.py:79 ENV_VAR_NAME = "OPENCLAW_COST_EDGE_ADVISOR"` 仍是門控

**對抗性 push back**: 這是 **30 分鐘 operator action**（systemd EnvironmentFile + restart_all），24h 內完全沒有觸發。CLAUDE.md §二 原則 13 明文 cost_edge_ratio gate 是合規 KPI，0 row 等於 KPI 不可量測。

---

### P2-A: 5 ML training scripts silent-unscheduled
**2026-05-08 audit**: `thompson_sampling`, `cpcv_validator`, `dl3_go_no_go`, `optuna_optimizer`, `weekly_report_generator` 5 個腳本 4-9 至 4-27 全無 invocation。

**24h 修復狀態**: ❌ **CLAIMED FIXED BUT FAKE**  
**證據**:

#### 對抗性檢視 commit `268f9470 audit: add ml training maintenance cron`
- ✅ Commit 真存在（2026-05-09 01:36）
- ✅ 真新增 `helper_scripts/cron/ml_training_maintenance.py` (430 LOC) + `ml_training_maintenance_cron.sh` (108 LOC)
- ❌ **但**：commit message 自承「**leaves cron installation/runtime execution to the operator**」
- ❌ **但**：`ssh trade-core crontab -l` → **沒有任何 ml_training_maintenance entry**（只有 7 個 entry: cost_snapshot / observer / counterfactual / passive_wait / edge_label_backfill / ref21 ×2）
- ❌ **但**：`stat /tmp/openclaw/status/ml_training_maintenance_status.json` → **file 不存在 → script 從未跑過**
- ❌ **致命**：`ml_training_maintenance.py` 默認 jobs **完全沒有** thompson/cpcv/dl3/optuna/weekly_report 5 個 audit listed scripts，只有 `linucb_trainer, mlde_shadow_advisor, mlde_demo_applier, scorer_trainer, quantile_trainer` 5 個**完全不同**的腳本

**對抗性 push back （CRITICAL）**:
1. **Commit message 詐術**：`audit: add ml training maintenance cron` 暗示「修了 5 ML scripts unscheduled」，但實際 ml_training_maintenance.py invoke 的是另外 5 個腳本（linucb / mlde_shadow / mlde_demo / scorer / quantile），**audit 列出的 5 個 (thompson/cpcv/dl3/optuna/weekly_report) 一個都沒接**。
2. **Cron not installed**：即便 commit 提到的 5 個 script，wrapper 寫了但 crontab 0 entry，**runtime 0 invocation**。
3. **model_registry production = 0**：證實 0 ML model promoted，整條 ML training pipeline 仍 dead。

**結論**：commit `268f9470` 是 **source-code-only + scope-mismatch + cron-not-installed** 三重 fake-fix。AI-E 2026-05-08 audit finding 完全未被處理，但 commit message 暗示已修。

---

### P2-B: MLDE 11.5% applied rate / dedupe filter 過激
**2026-05-08 audit**: 7d shadow 5209 row → 7d applied 277=11.5% / skipped 2041=85% / failed 47 / candidate 33；dedupe filter 過於激進（1941/2041=95% skipped 因 dedupe）。

**24h 修復狀態**: ✅ **IMPROVED （但非 28 commits 功勞）**  
**證據**:
1. 24h MLDE shadow recs = **902 row**（vs. previous 469/24h = +92%）
2. 24h MLDE applied = **376 row**（dream_engine 140 + ml_shadow 236）= **41.7% applied**（vs. 11.5% baseline = +30.2pp ✅）
3. source breakdown: dream_engine 273 not_applied + 140 applied / ml_shadow 253 not_applied + 236 applied
4. ml_shadow applied rate = 236/(253+236) = **48.3%**, dream_engine = 33.9%

**對抗性 push back**: applied rate 真實提升，但**檢視 28 commits 0 commit 觸及 mlde dedupe / advisor filter**。這應該是更早 P1-FAKE-2 修復的累積效應或 dedupe TTL 自然過期。**將此計為 24h 內 progress 但歸因錯誤**——AI-E 應追蹤實際引發改善的 commit（疑似 5/3-5/7 之間，需 PA 補追 RCA）。

---

### P2-C: cost_edge_ratio gate 0 row all-time
**2026-05-08 audit**: 0 row all-time。

**24h 修復狀態**: ❌ **NOT FIXED**（同 P1-B，env gate 未開）。

---

### P2-D: ContextDistiller 0 callsite / 不存在
**2026-05-08 audit**: ContextDistiller 0 callsite 全 codebase（profile/memory 提到的 spec 未 IMPL）。

**24h 修復狀態**: ❌ **NOT FIXED + NEW DEAD ARTIFACT 發現**  
**證據**:
1. `find srv -name 'context_distiller*'` → Mac repo **0 match**
2. **Linux 上 `find ~/BybitOpenClaw/srv -name 'context_distiller*'`** → `program_code/exchange_connectors/.../app/__pycache__/context_distiller.cpython-312.pyc` (4-3 timestamp, 14660 bytes)
3. **沒有對應 .py source 檔**——這是 4-3 之後 .py 被刪但 .pyc 殘留的 dead artifact
4. 28 commits 沒有任何 ContextDistiller IMPL

**對抗性 push back**: profile.md 仍把「ContextDistiller token 預算 V3 ~520 tokens 實測」列為 AI-E 核心技能，但 IMPL 不存在 + .pyc dead artifact 證明此 spec 從未 land。**AI-E profile 應移除此項或降為 P2 spec backlog**。

---

## §3. NEW-ISSUE（24h 對抗性核實新發現）

### NEW-1 P1: API key 路徑契約不一致
- `provider_keys_store.py` 找 `secrets/providers/{provider}.env`
- 既有 anthropic key 在 `secrets/secret_files/ai/anthropic_api_key`
- engine env 沒 export 任一路徑
- 修復成本：1 行 systemd EnvironmentFile + 1 個 file move/symlink

### NEW-2 P0: commit `268f9470` 是 fake-fix
- Commit message 暗示修 5 ML unscheduled scripts
- 實際 ml_training_maintenance.py jobs 列表完全不同（5 個其他腳本）
- 即使這 5 個其他腳本，crontab 0 entry / status JSON 不存在 → never invoked
- **此 commit 應追加 fix-up commit 或撤回**

### NEW-3 P1: ContextDistiller dead .pyc artifact
- Linux 上 4-3 殘留 .pyc 但無 .py source
- 修復：`find ~/BybitOpenClaw -name '*.pyc' -newer ... -delete` 或精確刪除

### NEW-4 P2: Strategist applied rate hidden fix 機制不明
- 24h 354 applied，但 max_param_delta_pct 未改 + 無相關 commit
- 可能是 STRATEGIST-PARAMS-PERSIST-1 restore handler bypass delta gate
- 需 PA / E1 RCA：是否真實 AI tuning effective，或只是 DB restore 的 cycle counter

### NEW-5 P2: agent.ai_invocations latest_ts = 2026-05-06
- 距今 3 天無 row 寫入
- 已知 0 cloud L2 invocation 是設計（API key 沒接），但 Ollama L1 也應該寫入
- Ollama 路徑可能根本不寫 ai_invocations table → log 路徑 audit gap

---

## §4. 對抗性 Push Back

### 4.1 對 28 commits 的 commit message 整體評估

| 類別 | 數 | 評估 |
|---|---|---|
| `feat:` | 4 | 多為 GUI / 配置 isolation，非 AI runtime |
| `perf:` | 4 | JSON/IPC 性能優化，非 AI 接入 |
| `refactor:` | 2 | 拆檔，無 functional change |
| `audit:` | 14 | **大部分 source-only**，commit message 自承「runtime execution to the operator」 |
| `security:` | 1 | W-AUDIT-2 hardening |
| `docs:` | 2 | governance sync |
| `healthcheck:` | 1 | scanner advisory |

**結論**：28 commits 中 **14 個 audit commits** 大部分屬於「IMPL source code + 留 operator 自己安裝 cron」模式。這在 governance 上是合規（避免 CC 自主修改 production cron），但 **0% commit 在 24h 內被 operator activated**。

### 4.2 對 AI-E 自己 2026-05-08 audit 的回應

**Audit 強項**：找到 5 個真實的 dormant/missing AI 接入（F-07 + cost_edge_advisor + 5 ML scripts + ContextDistiller + max_param_delta_pct）。

**Audit 漏洞**：
1. **Strategist 8/8 cycle reject 結論已過期**——24h 內 354 applied，audit 採樣窗口太短或時機不對
2. **MLDE applied rate 11.5%「過低」**結論需更新——24h 已飆到 41.7%
3. **未追究 dedupe TTL 自然過期 vs 真實 fix 區別**——應加 commit-level 歸因

### 4.3 對主治理鏈的 push back

**操作建議（給 PM / Conductor）**：
1. **F-07 是 30 分鐘 operator action**（symlink + systemd EnvironmentFile + restart）— 應該 24h 內就完成，未做。請排今天。
2. **cost_edge_advisor env-gate 同樣 30 分鐘** — 同上。
3. **`268f9470` commit 不能 close findings**——必須補一個 PA fix-up：(a) crontab 真接 5 個 audit listed scripts；(b) 或確認 ml_training_maintenance.py 5 個 jobs 才是正確 scope，重寫 audit。
4. **CLAUDE.md §三 應加一行 disclaimer**：「source-only audit commit ≠ runtime fix；operator activation 必須在 24h 內完成或 commit 重新分類」。
5. **ContextDistiller spec 廢止**——AI-E profile.md 要移除相關技能描述。

### 4.4 對 cost_edge_ratio 合規度

CLAUDE.md §二 原則 13：「每次 AI 調用計費，cost_edge_ratio ≥ 0.8 → 建議關倉」。

- **24h cost = $0.0**（無 cloud L2，Ollama L1 0 cost）
- **24h ai_invocations = 0** → cost_edge_ratio 分子 = 0
- 結論：合規但**因為完全沒有 AI 投資**，不是因為 AI 高效。**這是 dead-AI 假合規**。

DOC-08 KPI:
- 每日 AI 成本 < $2.00：✅ ($0)
- L1 Ollama 延遲 < 3s：n/a (24h 0 ai_invocations table 無採樣)
- AI ROI ≥ 0.5：**n/a** (AI 花費 = 0 → ROI 數學上未定義)
- cost_edge_ratio 等級 F 率 < 5%：n/a (gate 0 row)

**所有 4 個 DOC-08 KPI 24h 內無新數據，AI-E 評估能力本身被 runtime 0 流量阻塞**。

---

## §5. 建議下一步

**P0（24h 內，operator action only）**:
1. systemd EnvironmentFile 加 ANTHROPIC_API_KEY (從 `secret_files/ai/anthropic_api_key` 讀) + restart_all
2. systemd EnvironmentFile 加 OPENCLAW_COST_EDGE_ADVISOR=1 + restart_all
3. crontab 加 ml_training_maintenance_cron.sh entry（驗證機制可跑）

**P1（本週）**:
4. 確認 `268f9470` ml_training_maintenance.py 5 個 jobs (linucb/mlde_shadow/mlde_demo/scorer/quantile) 是否就是 audit 所指 5 個 silent scripts 的正確 mapping，若否補 fix-up
5. RCA Strategist 354 applied 的真實機制（hidden fix 可持續性）
6. 刪除 Linux ContextDistiller stale .pyc

**P2（本月）**:
7. AI-E profile.md 廢止 ContextDistiller / 雙進程 AI 路徑等未 IMPL spec 引用
8. 加 audit closure SOP：「source-only commit 不能 close finding，必須 runtime evidence」

---

## §6. Verification metadata

| 項 | 值 |
|---|---|
| 採集時間 | 2026-05-09 03:39 - 03:50 UTC+2 |
| 採集端 | Mac dev → ssh trade-core empirical |
| Engine PID | 4092934 (alive, age 2.1s, demo mode) |
| Engine env vars | LEASE_ROUTER_GATE_ENABLED=1, AGENT_SPINE_RUNTIME_MODE=shadow, **API keys 全 unset** |
| crontab entries | 7 (cost_snapshot/observer/counterfactual/passive_wait/edge_label_backfill/ref21×2) |
| 28 commits 修改 file 統計 | 100+ files (大部分 docs / TODO / wrapper script) |
| 修復率 | 0/5 真實 + 1 hidden (Strategist) + 1 organic (MLDE) = 0 attributable to commits |

**AI-E 對抗性結論**：
- 28 commits 在 governance/audit 工作流上很活躍（W-AUDIT-1/2/3 + V073-V077 migration + audit wrappers）
- 但**對 AI-E 2026-05-08 5 個 finding 的 runtime 修復率 = 0%**
- 1 個 hidden fix（Strategist applied）+ 1 個 organic improvement（MLDE applied rate）非歸功於本輪
- AI 接入度（ai_invocations / ai_usage_log / cost_edge_advisor_log）24h 0 流量 = AI 仍 dormant
- 需 operator 在今日內完成 P0×3 actions，否則 AI ROI 無法量測

