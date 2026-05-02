# OpenClaw TODO — 工作清單（v5 · P0/P1/P2 三層 · 2026-05-02）

**版本**：v5（2026-05-02 重組為 P0/P1/P2 三層工作流程，依 PA + FA + MIT cold panorama 真實全景重組）
**HEAD**: `a7b93d5`（Mac/Linux/origin 同步）· **Engine deployed**: `eaf0c7e`（PRE-LIVE-3，Mac 領先 6 commit 待下次 deploy）
**測試基準**：Mac Rust lib 2404/0 · Rust cargo tests 2560/0 · Python pytest 3262 passed + 1 pre-existing grafana fail orthogonal · LG-5 W3 healthcheck targeted +88/0 · Phase2 route coverage 43/0
**21d demo 時鐘**：2026-04-16 22:16 → 解鎖 **2026-05-07**

**歸檔索引**：
- 4-day codex audit closure 詳細 + Wave 4 Pre-Stage 5 軸線完整表 + Top 10 派發優先序 → `docs/archive/2026-05-02--TODO-pre-trim-snapshot.md`
- 62-finding Batch A-F：`docs/archive/2026-04-29--62finding-batch-A-to-F.md`
- STRKUSDT P0 Wave：`docs/archive/2026-04-29--strkusdt-p0-wave.md`
- Wave A-H 完整敘述：`docs/archive/2026-04-29--wave-A-to-H-narrative.md`
- Wave 1-3 完成表格 + Backlog 完成項：`docs/archive/2026-05-01--completed_waves_1_2_3_and_backlog.md`

---

## 一、真實狀態（2026-05-02 panorama 整合）

5 策略 7d gross 真實 net **-6.98 USDT**（demo）+ **-0.81 USDT**（live_demo）— grid 唯一 +5.77，其它 4 個合計 -11.96。LG-5 W3 FUP-1 sibling CC commit `463890d` 已 land，待下次 deploy 後 reviewer 啟動。Decision Lease 在 Rust 熱路徑 0 觸發是 R-04 last-mile 漏做（PA + FA archaeology 確認），路徑 A 待 retrofit。

**最早 Live target**：~05-23 樂觀 / ~05-30 中位 / ~06-15 悲觀。**panorama 評估悲觀更可能**（5 LG IMPL + Decision Lease retrofit + 18 blocker）。

---

## 二、P0/P1/P2 三層工作流程（5 大組 × 36 條目）

### 🔴 P0 — Live Blocker（必須在真 Live 前完成或正式拒收）

#### P0-EDGE — 策略 edge 層

| ID | 任務 | 等什麼 | 觸發 |
|----|------|--------|------|
| **P0-EDGE-1** | Edge net positive 驗證（5 策略 7d gross 由 -6.98 USDT 翻正）| 21d demo 解鎖 + EDGE-P1b 累積 | 被動觀察至 ~05-10 |
| **P0-EDGE-2** | P0-3 edge decision 會（A 翻正 / B 仍負 / C 部分改善）| EDGE-P1b ≥200 rows + counterfactual_exit_replay 結果 | ~05-15 |

#### P0-LG — Live Gate 實裝（依 P0-EDGE 結果啟動）

| ID | 任務 | 狀態 | ETA |
|----|------|------|-----|
| **P0-LG-1** | LG-1 21d demo 解鎖（passive）| 進行中 | 2026-05-07 |
| **P0-LG-2** | LG-2 H0 blocking IMPL（RFC `5ce777b` → 0% IMPL；過去 24h log 0 H0 blocks，metric collector 未建）| RFC only | P0-EDGE-2 後，1 sprint |
| **P0-LG-3** | LG-3 provider pricing binding IMPL（AccountManager.refresh_fee_rates 在但無 binding contract / staleness HC / startup assertion）| RFC only | 0.5-1 sprint |
| **P0-LG-4** | LG-4 supervised live IMPL（RFC `ec8f0f4` → state machine 0 行）| RFC only | 1.5-2 sprint |
| **P0-LG-5** | LG-5 W3 FUP-1 reviewer 0 emit fix（commit `463890d` 已 land，待 deploy 後驗證 24h `governance_audit_log` 累積）| sibling CC done | 下次 deploy |

#### P0-GOV — 治理 / 可審計層紅線

| ID | 任務 | 狀態 |
|----|------|------|
| **P0-GOV-1** ⚠️ | **Decision Lease 路徑 A retrofit**（Rust `acquire_lease()` facade + router gate + Python IPC 轉呼 + bundled audit writer fix）| 2026-05-02 三方 review 完成 ✅ AMD-2026-05-02-01；retrofit pending：~2.5-3 E1 task，派發 2026-05-15 P0-EDGE-2 後並行 LG-2/3，必在 LG-4 IMPL 前完。E4 驗收 AC-1~5（SM-02 transition coverage / 6-element auth fill rate / lease_id flow / weekly audit / agent schema row count）。詳 `docs/governance_dev/amendments/2026-05-02--SM-02_R04_retrofit_path_a.md` |
| **P0-GOV-2** | agent schema all-time 0 rows（`agent.messages` / `state_changes` / `ai_invocations`）— DOC-01 #8/#15 violation；MessageBus DB sink 接線 | **bundled with P0-GOV-1**（PA push back 採納；retrofit 同 sprint，AC-5 驗收條件）|
| **P0-GOV-3** | SOP「sign-off 必檢 `git status --porcelain` clean」gate（LG-5 漏洞同類防線）| CLAUDE.md §七 已加，需新 PR review template |
| **P0-GOV-4** | Live credential rotation 7 步（PG password + Grafana admin + 6 commit history 清理）| 2 day work，Live 前必 |

#### P0-OPS — 運維紅線

| ID | 任務 | 狀態 |
|----|------|------|
| **P0-OPS-1** | HTTPS deploy + Cookie secure G-4（PRE-LIVE-2 source not landed，3d 工時）| 0% IMPL |
| **P0-OPS-2** | KYC / 地理禁區 / Bybit ToS 合規確認（0 governance entry）| Operator 法律確認 |
| **P0-OPS-3** | Disaster runbook + Live first-day SOP（dust clear SOP only，缺完整 first-day playbook）| 1d work |

#### P0-DATA — 資料正確性紅線（跨 wave prerequisite）

| ID | 任務 | 阻塞下游 | 狀態 |
|----|------|---------|------|
| **P0-DATA-INDICATOR-SWEEP** | ✅ **DONE 2026-05-03** · 5 策略 indicator leak-free sweep verdict = **5/5 PASS**（QC quant 主審 + E3 adversarial 副審 + PM 補位驗證 `compute_indicators` body @ `on_tick_helpers.rs:453` 證據鏈完整：`get_ohlcv → buffer().ohlcv_arrays(n)` 只從 closed-bar buffer，不含 currently-forming bar）。**真因排查**：5 策略 net -6.98 USDT 不是 indicator leak，最便宜解釋為 strategy logic / cost / maker fill 三者（[33] maker 36.6% / [40] slippage -92bps）。**P0-EDGE-1/2 可繼續使用現有 edge 估計，無需重算**。**REF-20 V3 §3 G6 + §7 P2 precondition 解封**。Verdict 報告：`docs/audits/2026-05-03--P0-DATA-INDICATOR-SWEEP_verdict.md`。Follow-up（升 P2）：L-01 streaming integration test（綁 REF-20 P2b fixture）+ L-02 feature_version 硬編碼 v1.0 fix。 | （已解除）| ✅ DONE |

---

### 🟠 P1 — Important（Live 質量 / 在 LG IMPL 前後完成）

#### P1-FAKE — Fake-live wiring 修

| ID | 任務 | 來源 |
|----|------|------|
| **P1-FAKE-1** | ExecutorAgent `shadow_mode_provider` `lambda: True` fail-close default fix（G3-03 Phase B 名為 wired 實際仍 shadow）| PA panorama |
| **P1-FAKE-2** | H0_GATE singleton 0 production caller wire（DOC-02 spec 死於 wiring，LG-2 IMPL 前提）| FA-H2 |
| **P1-FAKE-3** | HStateCache + CostEdgeAdvisor 兩 late-inject slot 啟用（env-gated `OPENCLAW_H_STATE_GATEWAY=1` / `OPENCLAW_COST_EDGE_ADVISOR_*` 未設）| PA panorama |

#### P1-EDGE — Edge 層支撐

| ID | 任務 | 觸發 |
|----|------|------|
| **P1-EDGE-1** | ma_crossover ATR-SNR 後仍 net negative 重評（demo -5.09 / live_demo -1.60）| G2-02 ~05-03 後 |
| **P1-EDGE-2** | bb_breakout live_demo 14d 0 fires diagnosis（FIX-26-DEADLOCK-1 是否漏覆其它策略）| 即時可派 |
| **P1-EDGE-3** | funding_arb V2 棄策略 14d audit | 2026-05-16 cron |
| **P1-EDGE-4** | BUSDT 110017 reject loop 治本（24h slippage live_demo -92 bps；event_consumer/dispatch 加 net pos pre-check）| ASAP |

#### P1-DATA — 數據完整性

| ID | 任務 | 狀態 |
|----|------|------|
| **P1-DATA-1** | MLDE training row 84.6% `attribution_chain_ok=false`（MIT-S2-1） | sibling CC LG5-W3-FUP-2 in flight |
| **P1-DATA-2** | `learning.exit_features.est_net_bps` 100% NULL（FA-H6） | edge_estimator P1-7 C labels 47/200 累積中 + writer 路徑修 |
| **P1-DATA-3** | maker fill rate live_demo 7d 36.6% < 40% PASS 線（healthcheck 假綠） | 重設 baseline 或修 strategist post-only |
| **P1-DATA-4** | LG5-W3-FUP-2 attribution_chain_ok writer gap diagnosis | sibling CC in flight |

#### P1-TIME — 時間驅動里程碑

| 日期 | 任務 | 觸發腳本 / 條件 |
|------|------|----------------|
| **~05-03** | G2-02 ma_crossover counterfactual replay（1w post-G7-09 demo 數據累積）| `ma_crossover_counterfactual_replay.py`；若結論支持 → 派 G2-03-FUP-CALLER-WIRE P1 |
| **~05-07/08** | G2-01 PostOnly 1-2w 驗收（[33] ≥60% fee_drop）| 自動觀察；若 <60% → P2-COND-1 G2-04 grid disable 決策會 |
| **~05-09** | 3C deploy 7d audit（5 metric vs prior 7d baseline）| `bash helper_scripts/db/audit/2026-05-09_3c_7d_audit.sh` |
| **~05-10** | EDGE-P1b 累積 ≥200 rows（grid 1030 / ma 493 READY）| 跑 `exit_threshold_calibrator.py`；manual approve flow |
| **~05-15** | P0-3 邊評決策會 | PM+FA+PA+QC：edge positive/mixed/still negative → LG-2/3/4/5 or dual-track |
| **~05-16** | funding_arb V2 1B 樣本累積 14 天彙總 | `bash helper_scripts/db/audit/2026-05-16_funding_arb_14d_audit.sh`；n≥30 且 net bps 顯著負 → 2A 觸發棄策略 |
| **~05-22+** | Wave 4 實裝 | 依 P0-3 決策路徑啟動 P0-LG-2/3/4 + P0-GOV-1 retrofit |
| **~05-30±7d** | Live target | PM W2 sign-off 目標（中位 estimate） |

#### P1-INFRA — Pre-Live 基礎設施

| ID | 任務 | 觸發 |
|----|------|------|
| **P1-INFRA-1** | Slack alert channel go/no-go（pre-live ~2 週評估） | ~2026-05-15 |
| **P1-INFRA-2** | PRE-LIVE-4 災難恢復演練（drawdown auto-revoke / liquidation buffer / auth expire 三 scenario）| LG-2 RFC 後 |
| **P1-INFRA-3** | **REF-20 Paper Replay Lab wave**（4 輪 7-agent audit + V3 P0 commit baseline + UX subdoc V1 + Implementation Workplan V1 全 land；indicator sweep 5/5 PASS 已解 G6）— **9-Wave / 76-task** breakdown 完成（PA + FA + QC + A3 + E3 五份子報告合成）；總工時 12-14 sprint（不含 P5 LG 等期）。Wave 1 立刻可開（P0 docs/scaffold 9 task 並行）。詳：`docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md`（總文檔 SoT）+ `docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md`（V3 contract）+ `docs/execution_plan/2026-05-02--ref20_ux_subdoc_v1.md`（UX SoT）+ PA 子報告 `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-03--ref20_v3_implementation_breakdown.md`。 | Wave 1 派發 |
| **P1-INFRA-3a** | REF-20 Wave 1 P0 docs amendment + scaffold 設計（9 task 並行：REF-19/20 v2 amendment + replay_runner binary scaffold + ReplayProfile cfg gate design + UX subdoc accept + V### reservation + INSERT path grep + source distinct + signing key plan + crate boundary review） | 立刻可開（無 prereq） |
| **P1-INFRA-3b** | REF-20 Wave 2 P1 frontend IA + P2a foundation（13 task；P1-U1 sub-tab shell 必先 land 後其他並行；P2a-S1/S2/S3 signing/route auth） | UX subdoc operator accept |
| **P1-INFRA-3c** | REF-20 Wave 3-4 P2a 收尾 + P2b runner（11 task；3-PR DB role REVOKE/GRANT sequence + ReplayProfile::Isolated + Mac policy + symbol grep CI） | V### reserved (R20-P0-T5) |
| **P1-INFRA-3d** | REF-20 Wave 5 P3a/P3b/Regime quant calibration（13 task；half-life + bootstrap + NumPyro hierarchical + CUSUM + Kupiec + PSR + warmup） | LG5-FUP-2 deploy + decision_outcomes timeframe fix + 21d unlock (2026-05-07) |
| **P1-INFRA-3e** | REF-20 Wave 6 P4 advisory（8 task；DreamEngine API + MLDE veto + DSR + PBO + cost gate + applier source filter + safe_query mirror） | P3b green |
| **P1-INFRA-3f** | REF-20 Wave 7 P5 Agents Monitor 抽出（4 task；12-Tab top-level + 90d redirect notice + agent-tracker.js 行為保留） | LG-2/3/4 frontend merged + 7d stable |
| **P1-INFRA-3g** | REF-20 Wave 8 P6 demo handoff（7 task；typed confirm `HANDOFF <experiment_id>` + cooldown 30s + 雙 actor + idempotency + audit row + DB UNIQUE） | P4 green + AMD-2026-05-02-01 lease retrofit deploy |
| **P1-INFRA-3h** | REF-20 Wave 9 14d gradient + closure（continuous `replay_no_live_mutation` + 7d/14d KPI 採集 + PM Wave 9 sign-off） | P6 deploy |

---

### 🟡 P2 — Maintenance / Backlog（條件觸發或下個維護週期）

#### P2-AUDIT — 4-day codex audit Step 2 follow-up（部分 in flight）

| ID | 描述 | Owner |
|----|------|-------|
| **P2-AUDIT-1** | PA-DRY-1（`is_legacy_close_tag` `commands.rs:203/576` 重複 4 行）| @E1 |
| **P2-AUDIT-2** | PA-SCRIPT-PROC-1（4 script Linux-only `/proc/<pid>/cwd` 違跨平台）| @E1 |
| **P2-AUDIT-3** | PA-TEST-WATCHER-SLOT-1（無 e2e 測試斷言 watcher respawn 寫 / teardown 清 `live_cmd_slot`）| @E1+@E4 |
| **P2-AUDIT-4** | MIT-S2-2/3/4/6（demo→live promotion contract / regret_summary ceiling / V031 view scaling / opp_tracker noise）| @E1 |
| **P2-AUDIT-5** | QC-S2-01/02/04/09（scanner posterior LCB hardcoded / promotion distribution shift / TOML triple-env 違反 / PRE-LIVE-3 thresholds RFC 缺）| @QC + @PA |
| **P2-AUDIT-6** | E3-S2-P2-1/P2-2 exception leak；E3-S2-P3-1 file mode 0600 | @E1 |

詳述 → `docs/archive/2026-05-02--TODO-pre-trim-snapshot.md` § Top P2 / P3 backlog

#### P2-CODEX — 4-day codex window 殘存

| ID | 描述 | Owner |
|----|------|-------|
| **P2-CODEX-1** | 12 個 worktree merge 無人審（含 `PA/memory.md` + `cost_edge_advisor/mod.rs` conflict 解法）| @PA spot-check |
| **P2-CODEX-2** | 單 commit 13.6k LOC governance（`b46660a`）— §七 加「單 commit 上限」規則 or 接受並 flag | operator 決定 |
| **P2-CODEX-3** | hygiene fix（AUDIT-2026-05-02-P3-1/2/3）→ 已併入 P2-AUDIT-1/5 + 本次 archive sweep | DONE |

#### P2-STRUCT — 結構債

| ID | 描述 | 觸發 |
|----|------|------|
| **P2-STRUCT-1** | `decision_outcomes` outcome_* 100% NULL（timeframe 字串 bug）+ engine_mode 100% 'paper'（INSERT 漏接線）| memory `decision_outcomes_not_dead` |
| **P2-STRUCT-2** | LG5-CONSUMER-SPLIT P3（`governance_hub_live_candidate_review.py` 1496/1500 LOC near cap）| 下一輪維護 |
| **P2-STRUCT-3** | LG5-W2-FUP-PA-RFC-§4（`authorization.json.scope.lease_scopes` 加 `LIVE_CANDIDATE_APPLY:*` 條目；當前 empty-fallback=True latent rug-pull）| 下個 batch |
| **P2-STRUCT-4** | LinUCB shadow compare deferred to Rust warm-start | 條件觸發 |
| **P2-STRUCT-5** | G3-09 Phase C deferred（PA RFC ready，operator 決定「等時間長一些」）| Phase B observation 累積 |
| **P2-STRUCT-6** | G3-08-FUP-* split P2/P4（Analyst / HSQ / MAF / SINGLETON-POLLUTION）| 下一輪維護 |
| **P2-STRUCT-7** | 殭屍代碼盤點：`governance_hub.py` 部分 deprecated / `paper_trading_engine.py` retired / `pipeline_bridge` retired / `linucb_shadow_compare` 保留 / `apply_ai_consultation` deprecated stub | 下個 audit cycle |
| **P2-STRUCT-8** | Mac/Linux 6 commit gap → 下次 deploy window 一次 rebuild | 下次 deploy |

#### P2-COND — 條件觸發 backlog（保留）

| ID | 觸發條件 | Tag |
|---|---|---|
| **G2-03-FUP-CALLER-WIRE** | wire step_6_risk_checks caller chain，真實啟用 SL/TP override | G2-02 ~05-03 後 |
| **G2-04** | Grid disable 決策會 | G2-01 若 fee_drop <60% |
| **G8-03** | 灰度驗收自動化（shadow metrics）| EDGE-P2 flip 後 |
| **EDGE-P2-flip** | combine layer shadow flip | EDGE-P1b + 7d ≥95% agree |
| **EDGE-P2-3 Phase 2+** | live endpoint / funding_arb PostOnly | EDGE-P1b ~05-10+ |
| **G2-03 binding** | ma_crossover SL/TP 真實啟用 | G2-02 結論 + G2-03-FUP-CALLER-WIRE |
| **G7-03-Phase-B-FUP-grid** | grid_trading HysteresisDetector 遷移 | parallel WIP merge 後 |
| **G7-01 wiring** | Kelly router callsites | G4 labels work |
| **G3-06 Phase B** | Layer 2 autonomous Rust integration | 條件待確認 |
| **STRATEGIST-AUTO-PROMOTE** | 自動晉升規則 | P2-01 穩定後 |
| **ORPHAN-ADOPT-1 Phase 2B** | Strategist `would_take` 終仲裁 | G-1 R-02 |
| **IP-DEDUP-1** | IntentProcessor 去抖 | P0-3 後 edge 仍負 + 高重發率 |
| **G-7 ClaudeTeacher 啟用** | consumer_loop.rs enabled | 21d demo + G-3 後 ~05-07+ |
| **G9-02-FUP-COOLDOWN** | WS force reconnect cooldown 評估 | DEFAULT-ON 後 1-2w passive |
| **G8-01-FUP-REGRET-DREAM-DEFERRED** | OpportunityTracker + DreamEngine rebuild | 長期未定 |
| **G2-FUP-FUNDING-ARB-PAPER-SYNC-LOW-1** | TW memory.md 補 commit msg 一致性 | 下次 TW 接手 |
| **T6-FUP-PA-MEMORY-INDEX-SYNC** | PA Track 3 dust audit memory.md 條目補錄 | 下次 PA 接手 |
| **G5-09-FUP-TYPO** | commit `a5b6f17` commit msg test count typo | 下次 commit msg edit cycle |
| **TIER4-MIT-AUDIT-GREP-SNIPPET** | MIT EXIT-FEATURES audit H1 補 grep snippet 嚴謹度 | 下次 audit |
| **OC-1~6** | Webhook / Telegram 多通道 / MCP PostgreSQL | Phase 5+ |
| **WS-1** | FastAPI WebSocket/SSE 實時推送（替代 30s 輪詢）| 中優先 |
| **4-Conditional** | PairsTrading / Beta / Kalman / Jump detection | post-live |
| **G-6/G-7/G-8/G-10** | Edge JS retrain / ClaudeTeacher / cost_gate credibility / isotonic | P1-7B / 21d+G-3 |
| **QoL-2** | Demo AI cost 追蹤 GUI（硬編碼 N/A）| G3-08 |
| **G7-05** | cost_gate grand_mean bind | grand_mean>-50bps ∧ eligible cells>0 ∧ ≥2 strategy shrunk>0 |
| **G-2 FundingArb 重評** | 三參數重評 | R-02 Strategist 在線 |
| **EDGE-P2 Phase B** | Liquidation signal | Phase A OI 驗收 ✅ 已完，Phase B deferred |

---

## 三、Active Observation Gates

| Gate | 真實狀態（PA SQL panorama） | 目標 | 結論時間 |
|------|---------------------------|------|---------|
| `[22]` trading pipeline silent gap | WARN：fills stale；rejected-only 風險／cost gates 拒絕視為 WARN（`b283fda` 校準）| distinguish writer/order push wedge vs unfilled maker working orders | 持續觀察 |
| `[16]` strategist cycle fresh | last cycle 11.3min ago；within 30-min backoff window | <30min backoff tolerated | transient observe |
| `[33]` maker fill rate | 7d rolling **27.2%**（CLAUDE.md drift） / **36.6%** (PA SQL ground truth)；fee_drop 22.0% | ≥60% fee_drop | ~05-07/08 |
| `[38]` grid lifecycle drift | demo p50 7.9min vs live_demo 3.2min；lifetime_ratio 0.41 WARN；live re_entry_rate 0.48 | lifetime ≥0.5x | ~05-06 再看 |
| `[40]` realized edge acceptance | 24h MLDE rows=37-39，avg_net **-17~-18 bps**；slippage live_demo 24h **-92.47 bps** (BUSDT loop) | net_bps_after_fee>0 | 等累積 + edge 翻正 |
| `[41]` scanner market-gate confirmation | events=1260 / cells=69 / scoreable=0，gate 已 fire 但 label 未足 | gate blocked cells later negative | 等 label 累積 |
| `[27]` intents counter freeze | demo stale 88.3m / intents_30m=0 / verdicts_30m=1 / approved_verdicts_30m=0；risk/cost gates rejected all | approved verdicts with 0 intents 才 FAIL | 持續觀察 |
| `[11]` counterfactual clean window | n=413/200, cf_fired=46，rolling 2d window shrink expected，WARN not FAIL after `2674e14` | fresh replay + 3d WARN/PASS streak；criteria grid/ma/orphan 達標 | 本週 |
| `[42]/[42b]` LG-5 reviewer | 0 audit row 累積（sibling CC FUP-1 commit `463890d` 已 land）| >0 row/24h | 下次 deploy 後 |

**規則**：任何背景項連續 3 次 healthcheck FAIL = 中止被動等待，轉人工介入。

---

## 四、Healthcheck 清單（`passive_wait_healthcheck.py` 已實裝）

**Ground truth**：cron-wrapper output；裸 `python3 helper_scripts/db/passive_wait_healthcheck.py` 在非互動 SSH 可能缺 DB env；接手請用 wrapper。

| # | 項目 | 對應 |
|---|------|------|
| [1] | close_fills_24h | P0-2 engine 活性 |
| [2] | label_backfill | P1-7 C labels |
| [3] | exit_features_writer | EDGE-P1b 寫入面 |
| [4] | phys_lock_runtime | TRACK-P-V2 |
| [6] | trailing_stop_fire | — |
| [7] | edge_estimates_freshness | G1-01 / G4-04 |
| [8] | shadow_exits_24h | EDGE-P2-flip 前 baseline |
| [9] | model_registry_freshness | G4-03 |
| [10] | intents_writer_ratio | G2-01 |
| [11] | counterfactual_clean_window_growth | EDGE-P3 |
| [12] | bb_breakout_post_deadlock_fix | G2-06 disabled → PASS skip |
| [13] | edge_estimator_scheduler_fresh | G1-01 |
| [14] | exit_features_accumulation_rate | EDGE-P1b per-strategy |
| [15] | shadow_exit_agreement_phase2 | EDGE-P2 flip |
| [16] | strategist_cycle_fresh | G3 Strategist runtime |
| [18] | disabled_strategy_inventory | G2-06 drift 防線 |
| [19] | observer_pipeline_alive | G9-04 |
| [20] | h_state_gateway_freshness | G3-08 |
| [21] | paper_state_dust_inventory | Dust prevention |
| [22] | trading_pipeline_silent_gap | F7 |
| [23] | orders_fills_consistency | F7 |
| [24] | signals_writer_freshness | F7 |
| [25] | dust_qty_distribution | F7 |
| [26] | dust_spiral_noise_in_ef | EXIT-FEATURES fix |
| [27] | intents_counter_freeze | F7 |
| [28] | phantom_fills_attribution | F7 |
| [29] | reconciler_paper_state_divergence | deferred Rust handler |
| [30] | cost_edge_advisor_status | G3-09 Phase B |
| [31] | edge_diag_2_strategy_diversity | EDGE-DIAG-2 |
| [32] | maker_entry_intent_drift | G2-01 guard |
| [33] | maker_fill_rate | G2-01 PostOnly target ≥60% |
| [34] | intent_signal_attribution | STRATEGY-EDGE-REPAIR |
| [35] | MLDE data contract | MLDE demo autonomy |
| [36] | MLDE advisory/live lease boundary | MLDE demo autonomy |
| [37] | MLDE demo applier audit | MLDE demo autonomy |
| [38] | grid_trading_lifecycle_drift | GRID-LIFECYCLE-DRIFT |
| [39] | strategy_name_cardinality_drift | STRATEGY-NAME-ATTRIBUTION |
| [40] | realized_edge_acceptance | post-deploy edge observation |
| [41] | scanner_market_gate_confirmation | scanner market judgement 後驗 |
| [42] | lg5_review_audit_lag | LG-5 W3 IMPL-3（sibling CC FUP-1 deploy 後啟動）|
| [42b] | lg5_attribution_drift | 同上 |
| [Xa] | leader_election_health | G1-01 |
| [Xb] | pipeline_triangulation | G6-01 |

### 📅 排程提醒

| 日期 | 任務 | 觸發腳本 | Acceptance |
|---|---|---|---|
| **2026-05-09**（週六）| 3C deploy 7 天後對比 audit：5 metric vs prior 7d baseline | `bash helper_scripts/db/audit/2026-05-09_3c_7d_audit.sh` | exit 0（all metrics expected direction）→ PA review；exit 1 → operator 決策 base_ratio 是否續收緊或回退 |
| **2026-05-16**（週六）| funding_arb 1B 樣本累積 14 天彙總，判斷 2A 棄策略 trigger | `bash helper_scripts/db/audit/2026-05-16_funding_arb_14d_audit.sh` | n≥30 且 net bps 顯著負 → 2A 觸發棄策略；n<30 → 續收 |
| **REF-20 Wave 1 派發 checkpoint**（立刻）| Wave 1 P0 docs/scaffold 9 task 並行派發（PA / E1 / E1a / E3 / A3 / PM 多 owner，全 docs only 無 runtime risk）— 詳 `docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md` §4 Wave 1 表 | 9 task 全 PM sign-off | Wave 1 exit → 啟 Wave 2 P1 IA + P2a foundation |
| **REF-20 Wave 5 prereq watch**（持續，~05-15 至 ~05-25）| 觀察 LG5-W3-FUP-2 attribution writer deploy + decision_outcomes timeframe '1' vs '1m' fix + demo 21d unlock（2026-05-07）三條件 | 三條件全 GREEN | Wave 5 P3a/P3b 才能啟（量化 calibration） |

> 為什麼不用 `/schedule` remote agent：DB 在 trade-core localhost，遠端 cloud agent 沒 SSH/Tailscale。改寫腳本進 repo + TODO 提醒，operator（或 CC session）到日期 ssh 跑一行即可。
> Refs：`memory/project_2026_05_02_p0_sqlx_hash_drift.md` / `memory/project_funding_arb_v2_deprecation_path.md`

---

## 五、接手三連檢查

```bash
git status && git log --oneline -5
ssh trade-core "python3 helper_scripts/canary/engine_watchdog.py --data-dir /tmp/openclaw --status"
ssh trade-core "cd ~/BybitOpenClaw/srv && bash helper_scripts/db/passive_wait_healthcheck.sh --quiet"
```

---

## 六、工作流程速查

```
角色鏈：E1/E1a 並行（≤5）→ E2（強制）→ E4（強制）→ PM 確認 → commit + push
P0 快速通道：PA → E1（≤5）→ E2 → E4 → PM（可省 FA / E5 / E3 / CC）
sign-off 前必檢：git status --porcelain clean（P0-GOV-3 強制）
```

部署：`ssh trade-core "bash helper_scripts/restart_all.sh --rebuild --keep-auth"`（C 改動 commit 後跑此命令一次性 promote 所有 ahead-of-deploy commit + LG-5 reviewer 啟動）

---

**簽核鏈**：PA 核實 → PM Sign-off（必檢 git status clean）→ commit/push → Linux pull
**下一決策點**：~05-03 G2-02 ma_crossover 數據可用 + Decision Lease P0-GOV-1 三方 review 會
