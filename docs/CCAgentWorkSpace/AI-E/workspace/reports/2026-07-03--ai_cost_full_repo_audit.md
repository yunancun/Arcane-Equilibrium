# AI-E 全倉 AI 成本/ROI/模型分配審計 — 2026-07-03

**範圍**：srv/ 全倉（rust engine / control_api / GUI / helper_scripts / .claude / 治理文檔）+ Linux trade-core read-only 親證（engine PID 2368227，2026-07-03 01:02 啟動；control API PID 1038429）。
**邊界**：read-only；零修復、零 runtime 動作、零 auth/config 變更。
**定價查證**：2026-07-03 WebSearch 官方多源一致 — Opus 4.8 $5/$25、Sonnet 4.6 $3/$15、Haiku 4.5 $1/$5 per MTok；新發布 Sonnet 5（intro $2/$10 至 2026-08-31，之後 $3/$15）、Fable 5 / Mythos 5（$10/$50）。

## DOC-08 KPI 快照

| 指標 | 當前值 | 目標 | 達標? | 改進建議 |
|---|---|---|---|---|
| 每日 AI 成本 | $0（ai_usage_log=0 row all-time；ai_invocations=2 synthetic row，latest 2026-05-06） | < $2.00 | 名義達標 = dead-AI 假合規 | 先修 F3 writer 默認關，才有真量測 |
| L1 Ollama 延遲 | 不可量測（writer env-gate OFF + L1 loop 自 06-24 idle） | < 3s | 不可裁 | 設 OPENCLAW_AGENT_EVENT_STORE_ENABLED=1（operator） |
| AI ROI | 0/0 數學未定義（分子分母皆 0） | ≥ 0.5 | 不可裁 | 恢復 L1 流量（根因在 fills 斷流，見 F4） |
| cost_edge_ratio 等級 F 率 | 不可量測（advisor 42,385 row 全 Disabled/B_shadow，ratio all-time NULL） | < 5% | 不可裁 | risk_config_demo.toml [cost_edge] enabled 仍 false（F2） |

**總結一句**：AI 三層棧本輪 $0 成本、$0 產出。L1（唯一真活躍層）自 2026-06-24 起零 apply——根因不在 AI 棧，在 demo fills 斷流（envelope refresh 死循環）餓死 MIN_FILLS=30 gate。四項 DOC-08 KPI 全部因觀測腿斷 + 流量歸零而不可裁。

## Findings（全量）

### F1 [HIGH][FACT][high] DOC-08 $2/日硬上限在 Rust 自主路徑仍無 enforcement 腿（06-14 F1 未修）
- 證據：runtime `learning.ai_budget_config` 5 rows 全 monthly（agent_teacher 60/local_total 100/platform_hard_cap 150，updated 2026-04-06）；`tracker.rs` 全 scope monthly；`budget_config.toml:30 daily_usd_max=2.0` 由 `config/budget_config.rs:83` 解析但全 engine src 零 runtime 消費者（唯一引用=ipc_server/tests/config.rs:224）。
- 影響：teacher kill-switch 一開，單日可燒到 monthly cap 而不觸任何 daily 邊界；`daily_usd_max` 是假功能參數（違 feedback_no_dead_params）。dormant（loop 現關）故非 CRITICAL。
- 修向：BudgetTracker 加 daily 窗（usage_io date_trunc('day') 腿）+ 讓 daily_usd_max 真被 check_and_record 消費。
- 進展註記：pre-call gate 已落地（claude_teacher/mod.rs:157 check_budget_pre_call + BudgetExceededPreCall）→ 06-13 Item 1b「後審記帳」已閉，但 gate 基準仍是 monthly。

### F2 [HIGH][FACT][high] 原則 13 cost_edge_ratio≥0.8 關倉鐵則雙腿全 dormant，且無 re-arm 追蹤
- 證據：(a) advisor：env `OPENCLAW_COST_EDGE_ADVISOR=1`（engine environ 親證）但 `risk_config_demo.toml:499 [cost_edge] enabled=false` → 雙保險第二腿關 → `cost_edge_advisor_log` 42,385 row（7d 9,773）全 status=Disabled/phase=B_shadow、ratio non-null=0 all-time。(b) 交易級 attention_tax：`budget_config.toml:7 cost_edge_max_ratio=100.0`（Phase 5 臨時禁用，註釋承諾「JS 轉正後降回 0.8」）——Phase 5 已於 05-31 凍結，無任何 re-arm ticket。
- 雙向裁決：原 0.8 觸發即關倉（觀測 ratio 9-18）是負淨貢獻控制，禁用本身有據；缺陷=「臨時禁用永久化 + 無重估迴路」與「advisor 永不出 B_shadow」，鐵則全時不可執行。
- 修向：advisor 至少開 demo enabled=true 觀測（0 交易影響，Phase B observation only）；attention_tax 建 re-arm 條件檢查點。

### F3 [HIGH][FACT][high] L1 AI 調用觀測 writer 默認 OFF——DOC-08 KPI 量測點斷的直接根因（E.1/NEW-5 懸案終判）
- 證據：`agent_event_store.py:94-95 self.enabled=_env_enabled("OPENCLAW_AGENT_EVENT_STORE_ENABLED")`（default "0"）；control API PID 1038429 environ 親證無此 var → 每次 `_record_strategist_invocation`（ai_service_dispatch.py:553，WP-04 ef6ea79f 2026-05-16 落地，含 provider=ollama/tier=L1/latency_ms）短路。`agent.ai_invocations` 2 row all-time（皆 2026-05-06 synthetic row_proof），而 strategist L1 真調用持續至 06-24（applied 21,623 row）。
- 影響：L1 延遲/調用量/成本 KPI 永遠空表；05-09 v3 以來三輪審計追的「writer path 漏接」實為 env 默認關——代碼早已在，一個 env var 之遙。
- 修向：operator 在 API service env 設 `OPENCLAW_AGENT_EVENT_STORE_ENABLED=1`（注意先評估 PA 警告的行量：僅 ai_invocations 腿約每 5min 數行，遠低於 messages 腿 4.3M/day 風險）。

### F4 [HIGH][FACT+INFERENCE][high] L1 Strategist 調參迴圈自 2026-06-24 全停——AI 棧唯一活躍層歸零
- 證據：`strategist_applied_params` max(applied_at)=2026-06-24 19:17；今日 engine.log 127 條 strategist 行全為 RICH-INPUT surface（cells=216 validated=0 usable=0），0 條 ollama/proposal/apply；`trading.fills` 7d=78 筆、top pair flash_dip_buy|BTCUSDT=8 筆 << evaluate.rs:357 `HAVING count(*)>=30` → gather_strategy_metrics 空 → 5-min cycle 每輪 Ok(0) 早退，Ollama 零調用。
- 根因鏈（INFERENCE，high）：demo envelope refresh source-drift 死循環（TODO v738）→ 零 probe/order → fills 斷流 → MIN_FILLS gate 餓死 L1。AI 棧本身無故障；Ollama 服務 live（bge-m3 + qwen3.5 9b 親證）。
- 影響（以凍結進化價值計）：AI 進化迴圈（L1 tuning + MLDE 訓練素材）與交易迴圈同鎖死；恢復 fills 前任何 AI 效果改進都無載體。
- 修向：非 AI-E 職權——上游 P0-STANDING-DEMO-ENVELOPE-REFRESH 解鎖後自癒；可考慮 healthcheck 加「applied_params 停更 >48h」告警。

### F5 [MEDIUM][FACT][high] MLDE shadow 產出量較 06-13 基線衰減 ~83%
- 證據：`mlde_shadow_recommendations` 24h=60 / 7d=642（06-13 基線 347/24h、3,444/7d）；max ts 2026-07-03 12:45（仍 fresh）。同 F4 饑餓根因。

### F6 [MEDIUM][FACT][high] Cloud L2 雙路徑 key/開關錯位——$2/日預算頭寸 100% 閒置持續 ~3 個月
- 證據：Rust engine environ 有 ANTHROPIC/OPENAI/DEEPSEEK 三 key + TeacherConsumerLoop spawned DEFAULT-OFF（engine.log 01:02:43「flip via set_teacher_loop_enabled」）；Python API 進程 environ 三 key 全無，但 `~/BybitOpenClaw/secrets/providers/` 三 .env 檔在（05-10，provider_keys_store 路徑契約已對齊，NEW-1 閉）；觸發仍 manual-only（risk-tab.js:548 POST /paper/layer2/trigger）。`learning.ai_usage_log`=0 row all-time。
- 裁決：dormant by governance（ADR-0020）非 bug；但 06-13 O1/O2 攻性建議（L2 假設生成 ~$0.05/天）至今零消費，L2 能力=凍結槓桿。列 evolution-blocker 供 PM 裁。

### F7 [MEDIUM][FACT][high] L2 memory recall 永久 dormant：l2_call_ledger 表不存在
- 證據：`to_regclass('agent.l2_call_ledger') IS NULL = t`；兩進程 environ 皆無 `OPENCLAW_L2_MEMORY_RECALL`。99 條 embedded 教訓（bge-m3 1024d）0 召回。06-14 F7 原樣未動。

### F8 [MEDIUM][FACT][high] Layer2CostTracker 跨進程預算競態（fail-open under concurrency，dormant）
- 證據：`layer2_cost_tracker.py:170 threading.RLock`（進程內）+ `layer2_cost_state.json` atomic tmp→replace，無 fcntl/flock；uvicorn --workers 4（restart_all.sh:870，親證 4+ 子進程）→ 各 worker 各持 tracker 副本，daily cap check-then-write 非跨進程原子：並發時可雙批過 cap，last-writer-wins 亦可丟記帳。
- 影響：manual-only 觸發下實際並發概率低；一旦 Layer2 autonomous 化（任何形式），$2 cap 名義上限變 ~$8 或記帳漏記。新發現（歷輪未列）。
- 修向：跨進程 file lock 或把 cost state 收斂單 worker/DB。

### F9 [MEDIUM][FACT][high] AI-E 報告 lineage gap：memory 引用的 06-13/06-14 兩份報告全域不存在
- 證據：memory.md 索引 `2026-06-13--AI-E--profit_research_守攻.md`、`2026-06-14--AI-E--full_repo_cost_audit.md`；Mac repo、Linux checkout、git 全史（--all --diff-filter=AD）皆無此檔。結論條目在 memory 但證據檔斷鏈——違反本角色完成序列的可追溯要求。本報告已將關鍵數據重新親證落盤。

### F10 [LOW][FACT][high] 每日成本快照採集腿不存在（06-14 F5 以「刪 cron」而非「補實現」收場）
- 證據：crontab 5 entries 無 cost snapshot；helper_scripts 無對應腳本。AI spend=$0 下影響極低；F3 修後可再議。

### F11 [LOW][FACT][high] DOC-08 內文 stale：L1 寫「Ollama 7B」（實際 9B/27B）、L2 per-call 估價基於退役定價
- 證據：DOC-08 §1:35-37。治理正本自身漂移，extract 防線（skill S3）反向失效風險。

### F12 [LOW][FACT][med] cost_edge_ratio 三同名三義未收斂（06-14 F3 殘留）
- DOC-08 §5.2 cost/edge（高壞）vs advisor trigger_threshold=-0.5 edge/cost（高好）vs tracker burn used/limit。命名債，誤讀成本按讀改頻率計。

### F13 [INFO][FACT][high] GUI AI tab ROI tiles 永久 "--"（誠實空顯示，非 fake-success）
- tab-ai.html:89-92 roi-spend/roi-ratio 依賴空表。另 :929 adaptive_base_daily_usd 默認 8 無風險（check_daily_budget 取 min，hard cap 2.0 恆束）。

### F14 [INFO][FACT][high] 上輪修復閉環確認（PASS 面）
- 定價三軸對齊且 2026-07-03 官方複驗仍準：ai_pricing.yaml=layer2_types.py=官方（Opus4.8 $5/$25、Sonnet4.6 $3/$15、Haiku4.5 $1/$5）；tasks.rs:283 env-override 默認 claude-sonnet-4-6（真名，YAML active）；殘留 claude-sonnet-4-5 全在 #[cfg(test)]；Python unknown-tier fail-closed（layer2_cost_recording.py:104-110）+ _sync_to_rust_budget MODEL_IDS 真名正規化（:125-128）；max_param_delta_pct=0.50；provider key 檔案在位。
- 新模型情報：Sonnet 5 intro $2/$10（至 08-31）較現 pinned Sonnet 4.6 便宜 33%——teacher loop 若啟用前可評估換軌 + YAML 補條目（現缺 sonnet-5/fable-5/mythos-5 鍵，fail-closed 安全但擋採用）。claude-sonnet-4-6 是否已進退役期未經 API models list 核實（ASSUMPTION）。

### F15 [INFO][FACT][high] 零成本承諾複驗
- DreamEngine 0 LLM import（dream_engine.py 親證）；CognitiveModulator scan 300-3600s 界內；cost_edge_advisor heartbeat ~1.4k row/day 純 Disabled 噪音寫入 PG（42,385 row 零分析價值，schema/存儲小稅）。

## 盲區（negative-space，給 PA re-probe）
1. bybit_thought_gate 56 檔僅查 wiring 未逐檔審（同 06-14）——體量 vs 本輪聚焦取捨。
2. Anthropic console 實際賬單無法訪問——$0 結論基於 DB+env+loop-off 三角證，key 出系統外使用不可證偽。
3. L1 latency P50/P95 無真值——writer OFF + 流量 0，雙重不可量測。
4. ContextDistiller ~520 token 預算 spec 至今 0 runtime 樣本可驗。
5. Rust→Python IPC AI 路徑端到端延遲（profile 條目）無流量可測。
6. LM Studio lane（Mac dev）行為未實測。
7. analyze_token_usage.py 開發側 token 稅本輪未重跑量化。
8. cost_edge_advisor_log 表膨脹率/索引健康未量化。

## 下輪建議（依優先序）
1. operator 一行 env：`OPENCLAW_AGENT_EVENT_STORE_ENABLED=1`（F3，解鎖全部 KPI 量測）。
2. F1 daily 腿：BudgetTracker 補 daily 窗消費 daily_usd_max（teacher 啟用前置件）。
3. F2 advisor demo enabled=true（觀測零風險）+ attention_tax re-arm 檢查點掛 TODO。
4. F8 跨進程鎖（Layer2 autonomous 化前置件）。
5. Sonnet 5 intro 定價評估 + YAML 補鍵（08-31 前有 33% 窗口）。

— AI-E, 2026-07-03
