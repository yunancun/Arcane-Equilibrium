# AI-E AI 成本盈利證據審計 — 2026-07-09（read-only）

**範圍**：AI 成本 ledger / cost_edge_ratio 取證、L2 推理 ROI 評估、flag-off/dormant AI 能力盤點（含 WP1-WP7）。
**運行時**：Linux trade-core engine PID 1561777（build_sha `54d5fbf99`，build 2026-07-05T16:25:47Z，boot 2026-07-09 06:28）；control API PID 3771536（uvicorn 4 workers，07-05 起）；ALR consumer PID 1925314。Linux HEAD `a71b5ed93`（07-09 22:42）。
**邊界**：read-only 全程遵守——零修復/零 config/零 deploy/零 restart/零 auth 變更；Linux 僅 ssh read-only 命令。
**定價查證（2026-07-09 WebSearch 官方+多源一致）**：Haiku 4.5 $1/$5、Sonnet 4.6 $3/$15、Opus 4.8 $5/$25 per MTok；Sonnet 5 intro $2/$10 至 2026-08-31 後轉 $3/$15；cache read −90%、Batch −50%。與 `settings/ai_pricing.yaml` 及 runtime `layer2_cost_state.json`（last_verified 2026-06-29）三軸一致。

## DOC-08 KPI 快照

| 指標 | 當前值 | 目標 | 達標? | 改進建議 |
|---|---|---|---|---|
| 每日 AI 成本 | **$0**（FACT：`learning.ai_usage_log` 0 row all-time；`agent.ai_invocations` cost_usd 合計 $0；`layer2_cost_state.json` daily_spend={}） | < $2.00 | 名義達標（L2 仍零流量；L1 本地 $0） | L2 消費決策屬 PM/operator（F6 承 07-03） |
| L1 Ollama 延遲 | **首次可量測**：success-only avg 7,021ms（min 4,251 / max 8,004）；全樣本 P50 8,008ms 為 8s timeout 右截斷（98% 樣本≥8s → 真 P50 > 8s） | < 3s | **FAIL（≥2.3x 超標）** | 見 N1（timeout/keep_alive/模型層級三選） |
| AI ROI | 未定義（分母 $0；分子=0 可歸因 edge：applied 7d=0、L2 0 call） | ≥ 0.5 | 不可裁 | 恢復 fills→L1 apply 迴圈（上游 P0 envelope，非 AI-E 職權） |
| cost_edge_ratio 等級 F 率 | 不可量測但**已 armed**：advisor 07-05 起 Disabled→WarmUp（6,483 row），ratio all-time non-null=0（WarmUp 需 data_days≥3，$0 spend 下結構性停留） | < 5% | 不可裁（vacuous 合規，fail-closed 正確） | 無行動需要；L2 首筆 spend 後自動進入可量測 |

**一句總結**：本輪最大變化=2026-07-04「冷審計 R2」一天內closed 上輪 F1/F2/F3/F8 四項（daily 腿/雙保險 armed/writer 默認 ON/flock），KPI 觀測腿首次真通水；通水後立刻暴露新 HIGH——L1 judge_edge 98% 撞 8s timeout 牆（728/743 fail），DOC-08 3s SLA 即使成功樣本也全數超標。L2 全史仍 $0/0 call=凍結槓桿；WP1-WP7 全部 source-contract DONE + P1 債已修但零 runtime 消費者。

## Findings（全量，含 severity + confidence）

### N1 [HIGH][FACT+INFERENCE][high] L1 judge_edge 98% timeout 牆——首次量測即 SLA FAIL
- FACT：`agent.ai_invocations` provider=ollama 743 row（2026-07-05→07-09，purpose 全=strategist_edge_eval，model=l1_9b）；success=false 728 / true 15（98% fail）；fail 樣本 latency 緊聚 ~8,008ms、`text_len=0 error_len=16`、response_hash=空串 SHA；success 全部集中 2026-07-09（15/182 當日），latency 4,251-8,004ms。
- 機制（FACT）：`ollama_client.py:362 judge_edge timeout=timeout or 8`（硬編 8s，:330 同款）；Python OllamaClient 默認 30s 不適用此路徑；Rust IPC strategist_evaluate 15s 不是牆。
- 根因候選（INFERENCE, med）：qwen3.5:9b-q4 在共享主機上 100-token JSON 生成 >8s；`ollama_client.py` 全檔無 keep_alive 參數 → Ollama 默認 5min 驅逐 vs strategist 5min 週期存在 cold-load 競態（每次調用都可能重載模型）。07-09 突現 15 成功與當日 engine 重啟/調用節奏變化相關，read-only 無法終判。
- 影響：L1 edge-judge 腿有效產出率 2%；~180 call/day × 8s ≈ 24 min/day 阻塞等待後 98% 落回 L0 heuristic（strategist_edge_eval.py:278 fallback，fail-open 到本地啟發式，無交易中斷）。等於「AI 判斷」名存實亡但白耗延遲。
- 修向（供 PM 裁）：三選一或組合——(a) judge timeout 8→20-30s 實測真延遲分佈再定；(b) 顯式 keep_alive 常駐 9B；(c) 依 DOC-08 模型分配原則降級此 yes/no 任務至更小模型。任何修改屬 E1 職權。
- 可重跑證據：`ssh trade-core "psql -h 127.0.0.1 -U trading_admin -d trading_ai -Atc \"SELECT success,count(*),percentile_cont(0.5) WITHIN GROUP (ORDER BY latency_ms) FROM agent.ai_invocations WHERE provider='ollama' GROUP BY success\""`

### N2 [closure][FACT][high] 上輪 F1/F2/F3/F8 全部已修且入 runtime（2026-07-04 冷審計 R2 波次）
- F1 daily 腿：commit `4e30b983b`（07-04 23:02）BudgetTracker 補 daily_usd HashMap + UTC 日窗 + `daily_cap_rejection()`，caller=claude_teacher/mod.rs:206 pre-call gate；`git merge-base --is-ancestor 4e30b983b 54d5fbf99`=true → **在運行 binary 內**。daily_usd_max=2.0（budget_config.toml:30）不再是假功能參數。
- F2 雙腿 armed：(a) `risk_config_demo.toml:519-524 [cost_edge] enabled=true`（07-04 operator 裁決 D5）→ advisor 07-05 01:49 Uninitialized→WarmUp（engine.log 07-09 06:28:29 本 boot 亦 WarmUp）；(b) attention_tax `cost_edge_max_ratio` 100.0→**0.2** + min_profit_to_close_pct 0.3（MICRO-PROFIT-FIX-1 設計值回歸，budget_config.toml:14）——「臨時禁用永久化」風險解除。
- F3 writer：commit `b23a2e459`（07-04 17:57）`agent_event_store.py:99` 默認 OFF→ON（顯式 "0" 可 opt-out）；07-05 API 重啟後 ai_invocations 真通水（742 ollama row）。三輪審計懸案（05-09 E.1 起）終閉。
- F8 跨進程鎖：commit `4753f6e7c`（07-04 22:38）Layer2CostTracker `_state_lock` flock 互斥（layer2_cost_tracker.py:191-203）。
- 另 `e76b81686` 對 cost_edge_ratio 三同名三義做五處方向消歧註釋（06-14 F12 命名債緩解）。

### N3 [MEDIUM][FACT][high] cost_edge advisor 出 Disabled 進 WarmUp，但 $0 spend 下結構性停留
- `cost_edge_advisor_log` 43,053 row：Disabled 36,570 + WarmUp 6,483（07-05 01:49 起，1,439 row/24h）；ratio non-null **all-time=0**；最新 row（07-09 22:52）data_days=0/ai_spend_7d=0/paper_pnl_7d=0。
- WarmUp 出口=data_days≥3（advisor.rs:105 註釋 ADAPTIVE_MIN_DAYS=3，源自 Python Layer2CostTracker H5）；`layer2_cost_state.json` adaptive.data_days=0、last_recalculated_ms=0 → L2 零 spend 期間 ratio 永為 None。裁決：fail-closed 正確行為（無資料絕不 trigger），非缺陷；「等級 F<5%」KPI 仍 vacuous。heartbeat 寫入稅持續（~1.4k row/day 無分析價值，同 06-14 F15）。

### N4 [HIGH][FACT][high] L1 Strategist 調參迴圈仍全停（07-03 F4 未變，第 15 天）
- `strategist_applied_params` max(applied_at)=2026-06-24 19:17、7d=0（all-time 21,623）；engine.log 07-09 strategist 174 行全 RICH-INPUT surface（cells=236 validated=0 usable=0）。
- 上游根因不變：`trading.fills` 7d=100 筆（realized_pnl 合計 −6.48 USDT demo）<< MIN_FILLS=30/pair gate；30d=1,055 筆 −150.72 USDT（demo lane，非 alpha claim，regime 不標——負值且非推廣證據）。judge_edge 調用（N1）與 param-apply 是兩條腿：前者活著（但 98% timeout），後者餓死。
- 依賴 P0-STANDING-DEMO envelope/order-capable 解鎖自癒；AI 進化迴圈與交易迴圈同鎖。

### N5 [MEDIUM][FACT][high] Cloud L2 = 凍結槓桿持續（07-03 F6 未變）
- 全史 0 billable call：`ai_usage_log` 0 row、`teacher_directives` 0 row、layer2_cost_state daily_spend={}、sessions=[]。
- 供給側全就緒：engine env 三 key present（ANTHROPIC/OPENAI/DEEPSEEK，親證 /proc/1561777/environ）；`~/BybitOpenClaw/secrets/providers/` 三 .env 在位；TeacherConsumerLoop spawned `enabled_at_boot=false`（engine.log 07-09 06:28:19，唯一開關=IPC set_teacher_loop_enabled，operator-gated）；Python 觸發仍 manual-only（ADR-0020）。
- N2 之後 daily $2 gate 已有 Rust enforcement 腿 → 「teacher 啟用前置件」之一已備；06-13 O1/O2 攻性提案（L2 假設生成 ~$0.05/day）至今 0 消費。$2/day 預算頭寸閒置滿 3 個月。決策屬 PM/operator，AI-E 僅列 evolution-blocker。

### N6 [MEDIUM][FACT][high] L2 memory recall 原樣 dormant（07-03 F7 未變）
- `to_regclass('agent.l2_call_ledger')`=NULL（表不存在）；兩進程 environ 皆無 `OPENCLAW_L2_MEMORY_RECALL`；99 條 bge-m3 1024d embedded 教訓 0 召回。

### N7 [MEDIUM][FACT][high] MLDE shadow 量持續低位
- `mlde_shadow_recommendations` 24h=111 / 7d=467（max ts 07-09 21:56 fresh）；vs 06-13 基線 347/24h −68%，vs 07-03 60/24h 回升 +85%。同 N4 饑餓根因，非 AI 棧故障。

### N8 [INFO][FACT][high] WP1-WP7 證據閉環：source-contract DONE + P1 債已修，零 runtime 消費者（全 dormant by design）
| WP | 模組（program_code/ml_training/） | source 狀態 | runtime 接線 |
|---|---|---|---|
| WP1 ProofPacket | proof_packet_contract.py | DONE；P1 malformed `sha256:` ref 已修（`_SHA256_PREFIXED_RE` :48 嚴格 64-hex，`798843f23` 2026-07-07） | 0 caller |
| WP2 PIT manifest | pit_dataset_manifest.py + _builder.py | DONE | 0 caller |
| WP3 registry serving | registry_serving_contract.py + model_registry.py | DONE；P2 trio 持久化已原子化（同 commit） | 0 caller |
| WP4 advisory/Dream hardening | advisory_review_packet.py | DONE；P1 truthy external-contact alias 已修（`_is_forbidden_external_contact_key` :274-294 no-contact guard） | 0 caller |
| WP5 Demo mutation envelope | demo_mutation_envelope.py + applier_mapping.py | DONE（799 行契約） | 0 caller |
| WP6 reward ledger | reward_ledger.py | DONE | 0 caller |
| WP7 learning-effect review | learning_effect_review.py | DONE | 0 caller |
- 佐證：七包內零 `OPENCLAW_` env flag、`program_code` 非-ml_training/非-tests 零 import、Rust 零引用 → 精確定性=「無接線」而非「flag-off」；與 memory 索引「STOP_SOURCE_CLOSURE_COMPLETE_WAIT_RUNTIME」一致。成本影響 $0。

### N9 [INFO][FACT][high] ALR P2-4 challenger lane：確定性 $0，非 LLM 消費者
- `ml_training.alr_event_consumer` 進程 live（PID 1925314）；alr_* 10 模組 grep 零 ollama/anthropic/llm 引用 → 純統計管線，AI 成本 $0。本角色 07-09 早前已出 `CHALLENGER_RESEARCH_ONLY` design 裁決（同目錄 2026-07-09--alr_p2_4_challenger_design.md）。

### N10 [INFO][FACT][high] 其餘 dormant AI 能力盤點（本輪親證）
- **L2 Advisory Mesh capability registry**（settings/l2_capability_registry.toml）：3 stanza（ml_advisory.diagnose_leak/.interpret_result/.hypothesize）**全 enabled=false** fail-closed；P3b hypothesize 另 blocked on QC B1。
- **DreamEngine**：`local_model_tools/dream_engine.py` 零 LLM/HTTP import（grep 空）→ 零 API 成本承諾複驗 PASS。
- **cost snapshot cron**：crontab 34 entries 中 0 條 cost snapshot（07-03 F10 未變，$0 spend 下 LOW）。
- **ai_pricing.yaml**：仍無 sonnet-5/fable-5/mythos-5 鍵（fail-closed 安全但擋採用）；Sonnet 5 intro $2/$10 窗口至 08-31（較 pinned sonnet-4-6 省 33%）持續流逝（07-03 F14 建議未動）。
- 歷史 dormant 未重驗（沿用舊輪結論，本輪未取證）：Rust edge_predictor/kelly_sizer/scorer ONNX、Perplexity client、Combine Layer shadow writer。

### N11 [INFO][FACT][med] L2 推理 ROI 終評
- 公式 ROI=(攻擊 PnL+防禦價值)/AI 總花費 = (0+不可量測)/$0 → 未定義。全史 L2 0 call → 無 edge 歸因樣本；L1 本輪唯一「產出」=15 次成功 edge 判斷（0 param apply、0 可歸因交易）→ AI 可歸因 edge=0。
- 對照：系統唯一活躍盈利探索（profit-first NEARUSDT 候選 avg net 64.98bps/5058 筆，TODO 正本）為確定性 Cost Gate lane，AI 三層零貢獻、也零成本。結論不變：AI 棧目前既不燒錢也不賺錢；瓶頸在交易迴圈解鎖與 L2 消費決策，不在成本控制（成本控制腿本輪反而首次齊備）。

## Gaps（本輪取不到）
1. Anthropic console 實際賬單——外部不可訪問；$0 結論基於 DB+state 檔+loop-off 三角證，key 出系統外使用不可證偽。
2. L1 真延遲分佈右截斷——98% 樣本被 8s timeout censor，真 P50/P95 不可知（僅知 >8s）。
3. 15 次成功為何集中 07-09——read-only 無法做 Ollama 側負載/keep_alive 實驗。
4. CognitiveModulator scan_interval 對調用次數影響、ContextDistiller ~520 token 預算、Rust→Python IPC 端到端延遲對比——均無流量/無 runtime 樣本。
5. L0 攔截決策的錯失價值雙向淨額——ai_invocations 無 L0 fallback 結果記錄，無法量化。
6. bybit_thought_gate 56 檔逐檔審——體量取捨，沿用 wiring 級結論。

## 下輪建議（依優先序）
1. N1 三選一決策交 PM：timeout 實測校準 / keep_alive 常駐 / 模型降級（先以 (a) 取真延遲分佈再裁 (b)(c)）。
2. teacher loop 若啟用：前置件已備 daily 腿——建議同窗補 YAML sonnet-5 鍵並評估 intro 定價換軌（08-31 前）。
3. ai_invocations 已通水——下輪可首次做 7d 滾動 L1 延遲 trend + 成功率 trend。
4. cost_edge_advisor heartbeat 寫入稅（~1.4k row/day 無分析價值）可評估降頻或 WarmUp 期免寫。

— AI-E, 2026-07-09
