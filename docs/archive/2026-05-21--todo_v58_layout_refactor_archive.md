# TODO v58 → v59 Layout Refactor Archive

**歸檔日期**：2026-05-21（UTC）
**動因**：Operator 反映 TODO 散亂；PA G1 + FA G2 並行 audit；PM consolidate 後 rewrite TODO 從 549 → ~310 行。本檔收納所有 v58 → v59 重排被 purge 的歷史 verdict / SOP / closure ledger。

**Refactor authority**：
- PA proposal: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--todo_reorganize_proposal.md`
- FA audit: `docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-21--todo_business_chain_audit.md`

---

## §A v55 一段話留底 + 翻譯歸檔說明

### v55 4 軌道 closure（2026-05-19 上半段）
- #5 watchdog RCA（DNS/HTTP transport outage 誤判為 ENGINE_CRASH）
- #6 entry-path RCA（entry-close 0% maker fill 為 path-specific，非全局 PostOnly 壞）
- #7 tab-live extract（tab-live.html 2171→543 LOC，內聯 JS 抽到 tab-live.js 1645 LOC）
- #9 stress fails RCA + #12 E1 R2 fix（stress_integration.rs 修 2 helper；35/35 PASS）

關鍵 commit：`9bf4fd62` / `c1f47722` / `d927bf7f`。

### QC P2-ENTRY-PATH critical reframe
原 QA「entry-close vs risk-exit by ID prefix」拆法是結構性人為造成的；兩者都走同一 `execute_position_close()` 路径。真實是 6 maker attempts / 3 fills = 50% Wilson CI [18.8%, 81.2%] 覆蓋 sim 70.8% → 21pp 偏差非 70pp gap。Sample velocity ~0.44 grid_close/hr → 首個可信 verdict 推到 T+96h~T+120h（2026-05-22~23 UTC）。

### v55 衍生 backlog
P1-WATCHDOG-EXIT-CODE-CLARIFY ✅ / FA-WATCHDOG-3STRIKE-ESCALATION-POLICY / P2-QA-TEMPLATE-CLOSE-MAKER-SPLIT-FIX ✅ / P2-SIM-QUEUE-AWARE-ADJUSTMENT ✅ / P2-STRESS-BB-BREAKOUT-FALSE-SQUEEZE-COINCIDENTAL-PASS ✅

### Governance flag
`cargo test --lib` 不覆蓋 tests/ integration crate；sign-off SOP 加 `cargo test -p openclaw_engine --release`（no --lib）。

### 翻譯與歸檔說明
- v56→v56-zh 改寫：全文中文化 + 嚴格清理 ✅ DONE 詳情
- 已完成項目（含 commit hash、E2/E4 鏈、AMD 修文記錄）轉存到：
  - `docs/archive/2026-05-19--todo_v55_translation_archive.md`
  - `docs/archive/2026-05-15--todo_v21_completion_cleanup_archive.md`
  - `docs/archive/2026-05-15--todo_v24_stale_rows_archive.md`
  - `docs/archive/2026-05-16--todo_v36_completion_cleanup_archive.md`
  - `docs/archive/2026-05-16--close_maker_first_phase_1b_round1_archive.md`
  - `docs/archive/2026-05-16--stage1_demo_a4c_tombstone_cleanup.md`
  - `docs/archive/2026-05-07--todo_v12_agent_openclaw_replan_archive.md`
  - `docs/archive/2026-05-09--w_audit_verified_closed_archive_v3.md`
  - `docs/archive/2026-05-20--todo_v57_3_closure_cleanup_archive.md`
  - `docs/archive/2026-05-21--todo_v57_5_route_change_purge.md`

---

## §B v58 closure metadata（從 TODO header 移出）

### v57.3 → v58 closure trail（2026-05-21）— A+B+C+D+E+F 六批

- **A**：TODO 縮 70 行 + 路線變更歸檔
- **B**：13 governance + 9 planning 文件入 git
- **C**：8 P2 sweep follow-up closure
- **D**：QA D1 (LG-1/2 P0 closure) + PA D3 (P1 status reverify) + watchdog R2 source land
- **E**：TODO 路線變更區 purge
- **F**：4 並行 actionable attack — F1 E5 P1-LG1-DEMO-SLA / F2 FA P1-FUNDING-ARB-SL-GATE-BUG / F3 E1 P2-OBS-WILSON / F4 PA P2-CANARY-FILE-SIZE

**Commit chain**：
- A-D: `5cd7b264` / `4f3ae2bb` / `cfb9d243` / `e96d8ebb` / `33ef66f5` / `d5d5ee3c` / `fbe8b8d5` / `7f959673` / `4acf2c01`
- E: `9257dc96`
- F: `98de93b4`（F1 verdict）+ `703b6653`（F3+E5 source/reports）

---

## §C §6 W-AUDIT 優先順序歷史 verdict

PM/PA/FA 三方交叉檢查後（2026-05-21 之前）：

1. **True-live 仍 blocked**：被 `P0-EDGE-1`、`P0-LG-1/2/3`、`P0-OPS-1..4` 卡住。v56 `P0-ENGINE-HALTSESSION-STUCK-FIX` 已 CLOSED 2026-05-20。
2. **Stage 1 Demo micro-canary 仍 blocked**：無 active paper cohort，無 A4-C cohort 候選；launch 需 strategy×symbol Stage 0R packet 且 `eligible_for_demo_canary=true`。
3. **Alpha path**：W-AUDIT-8b tombstoned；W-AUDIT-8c writer revival DONE；其他 8a/8e/8f/8g/8h 路徑待 operator 路線敲定後重組。業務鏈根因為 5 textbook 策略結構性 alpha-deficient（per QC 2026-05-11 audit）。
4. **Runtime blocker 更新**：`[27]`、`[55]`、`[67]` 已 closed；LG-1 + LG-2 DONE 2026-05-21。
5. **Maintenance**：P2 hygiene 排在 alpha / LG / ops gates 之後。

### §6.1 A4-C BTC→Alt Lead-Lag Tombstone（2026-05-16）

`W-AUDIT-8d` A4-C 非 active promotion task。active docs 僅保以下 guard：

- 狀態：archived from promotion；diagnostic-only / no-revive（BTC 1m return + xcorr feature shape）
- 保留：`panel.btc_lead_lag_panel`、`[57] btc_lead_lag_panel_health`、歷史 rows
- 不保留：Stage 0R 候選 / Stage 1 Demo cohort 來源 / paper-based promotion 措辭 / threshold-only revive tasks
- 未來重啟：materially new predictive variable + preregistered validation + 全新 strategy×symbol Stage 0R packet 且 `eligible_for_demo_canary=true`

詳細 Step 5b / RCA / PM+QC+MIT verdicts 歸檔於 `docs/execution_plan/2026-05-15--a4c_btc_alt_lead_lag_archive_verdict.md` 與相應 archive。

---

## §D §7 W-AUDIT-6d Mid-Ground 歷史 verdict

詳細 保 6 / 砍 6 ledger 與 DSR K -12 推導已歸檔（v21 cleanup archive）。

**保留 active rule**：6 polishing 項仍 REJECT，未經未來 QC/PM 決議不可重啟；不可新增 per-symbol / per-threshold sweep（會膨脹 DSR trial count）。E2 必 grep blacklist；命中即 reject merge。

---

## §E §8 D-02 Layer 2 SOP

完整 6 步 SOP 見 FA report `2026-05-09--full_dispatch_business_chain_validation.md` §2。摘要：

1. API key 取得：Anthropic Console → Create Key（命名 `openclaw-layer2-manual-7d-trial`，monthly budget $5）
2. 寫入：`echo "sk-ant-xxx..." > $OPENCLAW_SECRETS_ROOT/secret_files/anthropic/api_key && chmod 600`
3. 每日手動觸發 7d：`curl -X POST http://localhost:8000/api/v1/layer2/run_session -d '{"trigger_kind":"manual_daily_probe","scope":"L1_triage","max_cost_usd":0.50}'`
4. 7d 4 指標觀察：cost_today / decisions_assisted / avoided_loss / false_positive_rate
5. Pass：alpha > 2× cost + false_positive < 40% + 0 critical incident；Fail：alpha < cost OR false_positive > 60% OR ≥1 layer2 建議致 > 5 USDT 虧損
6. Fail rollback：`rm api_key && restart_all.sh --keep-auth`

**FA constraint**（invariant 15）：D-02 SOP 不可自動化為 cron / event-trigger（會違 ADR-0020 manual+supervisor-only）。預期 +2-5 USDT/week alpha；7d < 1 USDT/week 不值人工成本 → 建議 abort。

---

## §F §11.4 P0-MICRO-PROFIT QC verdict 全文

**背景**：QC 2026-05-11 audit verdict — 「為何盈利都是超微利潤」+「能否放大」。判定：當前 5 textbook 策略 7d EV<0（-17.82 bps demo）；任何 sizing 槓桿 L>1 必放大虧損（數學常數）。先修 alpha，再談 size。

### 5 root cause + 占比
1. **Alpha 結構性缺失（~60%）** — 5 textbook 策略 post-publication decay
2. **Account size × 0.1% TOML 物理上限（~20%）** — $591 × 0.1% = $0.59/trade 設計上限
3. **Fee drag（~10%）** — 10.4% taker remnant + PostOnly missed-trade
4. **Signal target tight 設計（~5%）** — grid 22bps / bb 1-2σ / ma sub-1ATR
5. **Slippage + queue position adverse selection（~5%）**

### Operator 5 zero/small cost action（2026-05-11 拍板）
1. ✅ DONE：修 `feedback_position_sizing` memory drift（3% → 註明 SSOT 0.1%/0.05%）
2. ⏳ PASSIVE wait：等 7d 重測 §3 [40]
3. ⏳ INFO gathering：Bybit fee tier 距 VIP1 還差多少 30d trading volume（被動 ROI ~0.5-1 bps RT）
4. ⏳ PASSIVE wait：TONUSDT 30d evidence → P1-CONDITIONAL-WATCH freeze 決議（2026-06-09 收口）
5. ✅ DEFER 記錄：D/E sizing 槓桿等 ML calibration N≥200

### 11 sizing 槓桿全 REJECT
in current EV<0 state（A/B/E/F = REJECT；C/I = CONDITIONAL；D = NEUTRAL；G/H/K = DEFER；J = APPROVE 被動）。

### Operator 守則
- 看見 memory「3%」**不要**直接套到 TOML（先讀 risk_config_*.toml SSOT）
- 任何「升 TOML sizing」提案在 EV<0 條件下 = 災難（先修 alpha）
- 信 config，不信 memory（per `math-model-audit` S1）

**Source**：`docs/CCAgentWorkSpace/QC/workspace/reports/2026-05-11--p1_micro_profit_amplification_math_analysis.md`

---

## §G §11.5 EDGE-P2-3 Phase 1b 摘要

**Status**：Round 1（Design + Governance）closure + 30+ commit timeline + 4-agent verdict + IMPL Prereq status + next-round scope → 歸檔 `docs/archive/2026-05-16--close_maker_first_phase_1b_round1_archive.md`。Phase 1b main source/test 完成於 `ea4ceca6`；V094 Linux apply + engine-only deploy/restart 完成 2026-05-17。

**仍 active（彼時）**：
1. ❌ `P0-EDGE-1` — `[40]` negative realized edge 仍 active
2. ⛔ `W-AUDIT-8b Stage 0R` — TOMBSTONED（細節歸檔）
3. ✅ `W-AUDIT-8a C1` — v2 24h proof technical PASS + writer revival DONE 2026-05-17
4. ✅ `P1-WAVE-3-5-LINUX-MIGRATION-BACKLOG` — DONE 2026-05-16
5. ✅ `P1-BBMF3-WIRE-1` — source/test + V094 apply + engine-only rebuild/restart DONE 2026-05-17
6. ✅ `W-AUDIT-8c` — source/test 修正 + V095 dry-run/MIT re-sign + Linux apply + writer revival DONE 2026-05-17

**Runtime kickoff status**：
- V094 Linux migration/deploy 授權 → deploy-chain regression → post-deploy healthcheck → PM sign-off：✅ DONE 2026-05-17
- Phase 1b runtime activation：✅ DEPLOY DONE 2026-05-17 23:54 UTC（engine PID 1143103）
- Calibration sweep + Rust timeout deploy：✅ DONE 2026-05-18 13:50 UTC
- Phase 2a 14d observation clock reset @ 2026-05-18 13:50 UTC
- Outstanding anomaly investigations：SD-1 A axis offset_bps dead-variable / SD-2 PS family phys_lock_gate4_stale_roc_neg 100% n_skip / 0 fill
- v56 incident 衝擊：2026-05-19 ~12:27-20:09 UTC 7h43m trading-inert；engine 20:09:36 起新 PID 2099215 恢復

---

## §H §11.6 12-Agent Full System Audit WPs（2026-05-16）— follow-ups

**Source**：`srv/2026-05-16--full-system-audit-fix-plan.md`（PA consolidated + PM sign-off）
**Wave 1-4 source/test**：完成並歸檔於 v36 cleanup archive

**剩餘 active follow-up（彼時）**：
- WP-11 Phase 2 residual → §12 P2 backlog
- WP-12 ONNX 仍 deferred；rule-based fallback 為當前行為
- PA audit drift hardening → `P2-PA-CALLPATH-GREP-RULE`（已 DONE）
- LOC follow-up → `P2-COMMON-JS-LOC`（DONE）、`P2-TAB-LIVE-LOC`（DONE via JS extract）

---

## §I §12.2/§12.3 P2 sweep 結算

2026-05-20 P2 sweep 6 項 DONE：詳情歸檔於 `docs/archive/2026-05-20--todo_v57_3_closure_cleanup_archive.md` §C。包括：QA-TEMPLATE-CLOSE-MAKER-SPLIT-FIX / STRUCT-2 zombie inventory / AUDIT-VERIFY-3 V069 drop verify / ENTRY-CLOSE-MAKER analysis / STRESS-BB-BREAKOUT-FALSE-SQUEEZE / SIM-QUEUE-AWARE-ADJUSTMENT。Commit chain `12dcdcbc` + `e2d213b5` + `a39dd11b` + `c3f25496`。

2026-05-20~21 P2 sweep 衍生 follow-up（從 FA P2-ENTRY-CLOSE-MAKER 分析衍生）— 全 8 條 closure 詳情見 v59 TODO §10 closure index。

---

## §J §13 Push Back / Risk 治理記錄

### PA Push Back（已 RESOLVED 2026-05-09 operator (a)）
- **原 risk**：Sprint N+0 5/5 HOT capacity = 任一 E1 故障 = 阻塞 critical path
- **Operator 拍板 (a)**：提供 1 stand-by E1，Sprint N+0 capacity 升 6 並行（5 active + 1 stand-by）

### FA Push Back（採納，記入治理）
1. Track W vs Track A 預算 — Track W 92h 是 supervised live 前置門檻
2. D-02 SOP 預期上限 +2-5 USDT/week；7d < 1 USDT/week 不值人工成本 → 建議 abort
3. A/B/C 候選預期 +3-7% 業務鏈是中位估
4. W-AUDIT-6d 砍 6 polishing 是 DSR 數學意義 right move（K -12）

### 4-agent loss audit cross-fact-check（撤銷的 stale belief）
- QC v2-NEW-4 Donchian「runtime contaminated」過期 belief：MIT 校核 + PM 直接驗證確認 runtime 自 `75741eff`（2026-04-28）起 leak-free 11 天；`ad14db07` 僅補 regression test。

---

## §K §16 References 歷史 dump（53 行 → 移出主 TODO）

### 4-Agent Loss Audit（2026-05-09）
- PA dispatch plan：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--full_dispatch_engineering_plan.md`（commit `d3bf7be2`）
- PA architectural redesign：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--full_loss_architectural_root_cause_redesign.md`
- PA merge analysis：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--todo_qctodo_merge_analysis.md`
- FA business chain validation：`docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-09--full_dispatch_business_chain_validation.md`（commit `5a2dee98`）
- FA dormant alpha inventory：`docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-09--full_loss_dormant_alpha_features_inventory.md`
- FA merge advice：`docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-09--todo_qctodo_merge_business_chain_advice.md`
- 4-agent loss audit worklog：`docs/worklogs/2026-05-09--4_agent_loss_audit_and_5_actions.md`
- QCTODO archived：`docs/archive/2026-05-09--qctodo_sprint_n0_n5_archive.md`

### Spec / Amendment（歷史）
- W-AUDIT-8a spec：`docs/execution_plan/2026-05-09--w_audit_8a_alpha_surface_foundation_spec.md`
- AMD-2026-05-09-02（5 P0-DECISION-AUDIT closure）
- AMD-2026-05-09-03（Graduated Canary Default）
- W-AUDIT-8b Funding Skew Directional spec v0.4 tombstone
- v56 P0 Engine HaltSession TTL spec：`docs/execution_plan/2026-05-19--engine_haltsession_ttl_and_watchdog_inert_probe_spec.md`

### Close-Maker-First 3-agent Verdicts（2026-05-15 round 1 — Spec）
- PM verdict / PA verdict + spec outline / FA verdict + AC

### Close-Maker-First 4-agent AMD Adversarial Review（2026-05-15 round 2 — AMD）
- QC / FA round 2 / BB / MIT / Consolidated 4-agent summary

### v56 P0 incident
- E2 RCA verdict：`docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-19--engine_watchdog_respawn_loop_and_trading_inert_rca.md`
- PA spec：`docs/execution_plan/2026-05-19--engine_haltsession_ttl_and_watchdog_inert_probe_spec.md`

### Adversarial Verification
- v3 PM Sign-off summary / v2 / v1
- PA Fix Plan v2（DUAL-TRACK）
- 2026-05-08 12-Agent Full Audit + PA Fix Plan
- Verified-closed archives

### Bybit / API
- Bybit API 字典/審計：`docs/references/2026-04-04--bybit_api_reference.md` · `docs/audits/2026-04-04--bybit_api_infra_audit.md`

### Process
- Operator G3-08 enable evidence：commit `dddc5dc1` restart_all.sh wire + 2026-05-09 17:27 UTC engine.log `cost_edge_advisor spawned env=1 phase=B_shadow`

### v55 翻譯歸檔
- 歷史 ✅ DONE 詳情：`docs/archive/2026-05-19--todo_v55_translation_archive.md`

---

## §L §12.4 27 條 P2 closure detail（保留 ID + commit）

- P2-DEAD-SCHEMA-DROP-1 ✅
- P2-DEAD-RUST-CLEANUP-1 ✅
- P2-PERCEPTION-DEPRECATE-1 ✅
- P2-H0-DISPLAY-LABEL-1 ✅
- P2-ORDERS-INTENT-ID-WRITER-GAP-1 ✅
- P2-WP05-FUP-1 ✅ 32/32 全收
- P2-COMMON-JS-LOC ✅
- P2-ENTRY-PATH-0PCT-MAKER-FILL-RCA ✅
- P2-TAB-LIVE-LOC ✅ via P2-TAB-LIVE-JS-EXTRACT
- P2-CROSSTAB-I18N ✅
- P2-STOCHASTIC-LEAK ✅
- P2-START-LOCAL-HELPER ✅
- P2-PA-CALLPATH-GREP-RULE ✅
- 5 個 P2-PORTFOLIO-RESTING-* follow-up ✅
- P2-QA-TEMPLATE-CLOSE-MAKER-SPLIT-FIX ✅ 2026-05-20
- P2-STRUCT-2 ✅ 2026-05-20
- P2-AUDIT-VERIFY-3 ✅ 2026-05-20
- P2-ENTRY-CLOSE-MAKER-REAL-FILL-FIX ✅ ANALYSIS 2026-05-20
- P2-STRESS-BB-BREAKOUT-FALSE-SQUEEZE-COINCIDENTAL-PASS ✅ 2026-05-20
- P2-SIM-QUEUE-AWARE-ADJUSTMENT ✅ 2026-05-20

---

**Maintenance contract**：依 `docs/agents/todo-maintenance.md` 將 active 派工佇列保持精煉；本歸檔不再回收進 active。
