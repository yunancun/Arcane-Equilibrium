# 玄衡 TODO — 活躍派工佇列

版本：v58-zh（v57.5 + E 批路線變更 purge + F 批 4 actionable closure 2026-05-21）
日期：2026-05-21
狀態：本檔僅保留 ACTIVE / PENDING / ACTIVE-WATCH 項目；所有歷史 ✅ DONE 詳情已歸檔。**v58 closure 後 working tree clean，路線變更區待 operator 拍板後重填 §-0 / §1 / §14**。

**v58 內容範圍**：
- §-0 路線變更區（空白，待 operator 重填）
- §3 active state（路線中立 milestone）
- §10 P0 active only（4 條：EDGE-1 / LG-3 / OPS-1..4 / P3-SPINE-BENCH；其餘 closure 移 §12.4）
- §11.3 P1 active queue（含 5 條 D/F 衍生 ticket）
- §12.4 closure 完整列表（含 LG-1/2 / P0-HALTSESSION / WATCHDOG-* 等）

**v57.3 → v58 closure trail（2026-05-21）— A+B+C+D+E+F 六批**：

- **A**：TODO 縮 70 行 + 路線變更歸檔
- **B**：13 governance + 9 planning 文件入 git
- **C**：8 P2 sweep follow-up closure（含 D2 healthcheck [66] + ADR-0028/0029 + spec v1.4 AC-20）
- **D**：QA D1 (LG-1/2 P0 closure) + PA D3 (P1 status reverify) + watchdog R2 source land
- **E**：TODO 路線變更區 purge（v4/v4.1/v4.2/v4.3/v4.4/v5.0/v5.2-v5.6 全歸檔 `2026-05-21--todo_v57_5_route_change_purge.md`）+ §10/§11.3/§12.4 closure 重組
- **F**：4 並行 actionable attack — F1 E5 P1-LG1-DEMO-SLA hotpath profile（in-progress）/ F2 FA P1-FUNDING-ARB-SL-GATE-BUG → NOT_A_BUG closure / F3 E1 P2-OBS-WILSON sub-clause（88/88 PASS，待 E2 R2）/ F4 PA P2-CANARY-FILE-SIZE → DEFER 推薦

**Commit chain**：
- A-D: `5cd7b264` / `4f3ae2bb` / `cfb9d243` / `e96d8ebb` / `33ef66f5` / `d5d5ee3c` / `fbe8b8d5` / `7f959673` / `4acf2c01`
- E-F: 待後續 commit

**待 operator 拍板（不主動推）**：
1. **P0-FUNDING-ARB-DECISION-FORCE 升等** — PA D3 建議；FA F2 RCA 後 SL bug NOT_A_BUG，但 funding_arb 整體治理仍開放
2. **Watchdog daemon R2 deploy** — 當前 PID 2936560 仍跑 R1；R2 source 已 land
3. **5 個 V5.2-V5.6 路線檔** — untracked，operator 隔壁敲定後重填 §-0
4. **P1-LG1-DEMO-SLA-VIOLATION** — F1 E5 hot-path profile 完成後 PM 決議 fix path
5. **§11.3 P1 backlog 派工順序** — 6 條 active P1 + 4 條新衍生

## §-0 路線變更區（待 operator 拍板後重填）

**狀態**：v57.5-zh 之前的 v4 / v4.1 / v4.2 / v4.3 / v4.4 / v5.0 / v5.2-v5.6 路線提案已歸檔。

**詳情歸檔**：`docs/archive/2026-05-21--todo_v57_5_route_change_purge.md`（v4.2 RATIFY 全文 + Sprint Banner + Wave Roster T1-T9 + v4.2 dispatch 排程）。

**Untracked 規劃文件**：`srv/2026-05-20--*.md` v5.2-v5.6 系列仍在 Mac working tree，operator 隔壁敲定後重新填入本區。

**Hard precondition**：路線敲定前不啟動任何 V101 / V102 / Track A/B / dispatch wave。當前 in-flight active 工作見 §3 / §10 / §11.3 / §12。

---

## §-1 v56 P0-ENGINE-HALTSESSION-STUCK-FIX → ✅ CLOSED 2026-05-20

Layer A + Layer B 於 2026-05-20 ~02:15 UTC LIVE 並 real-event verified。Halt 觸發根因仍 UNRESOLVED → `P1-HALT-TRIGGER-ROOT-CAUSE-INVESTIGATION-1`。詳情歸檔於 `docs/archive/2026-05-20--todo_v57_3_closure_cleanup_archive.md` §A。

---

## §0 v55 / 之前的完工狀態（一段話留底）

v55（2026-05-19 上半段）operator 授權的 4 條並行軌道全收口：

- **#5 watchdog RCA**（DNS/HTTP transport outage 誤判為 `ENGINE_CRASH`）
- **#6 entry-path RCA**（entry-close 0% maker fill 為 path-specific，非全局 PostOnly 壞）
- **#7 tab-live extract**（tab-live.html 2171→543 LOC，內聯 JS 抽到 tab-live.js 1645 LOC）
- **#9 stress fails RCA + #12 E1 R2 fix**（stress_integration.rs 修 2 helper；35/35 PASS）

關鍵 commit：`9bf4fd62` / `c1f47722` / `d927bf7f`。

**QC P2-ENTRY-PATH critical reframe**：原 QA「entry-close vs risk-exit by ID prefix」拆法是結構性人為造成的；兩者都走同一 `execute_position_close()` 路径。真實是 6 maker attempts / 3 fills = 50% Wilson CI [18.8%, 81.2%] 覆蓋 sim 70.8% → 21pp 偏差非 70pp gap。Sample velocity ~0.44 grid_close/hr → 首個可信 verdict 推到 **T+96h~T+120h（2026-05-22~23 UTC）**。

**v55 衍生 backlog**：見 §11.3 / §12（P1-WATCHDOG-EXIT-CODE-CLARIFY / FA-WATCHDOG-3STRIKE-ESCALATION-POLICY / P2-QA-TEMPLATE-CLOSE-MAKER-SPLIT-FIX / P2-SIM-QUEUE-AWARE-ADJUSTMENT / P2-STRESS-BB-BREAKOUT-FALSE-SQUEEZE-COINCIDENTAL-PASS）。

**Governance flag**：`cargo test --lib` 不覆蓋 tests/ integration crate；建議 sign-off SOP 加 `cargo test -p openclaw_engine --release`（no --lib）。

## 翻譯與歸檔說明

- 本次 v56→v56-zh 改寫：全文中文化 + 嚴格清理 ✅ DONE 詳情。
- 已完成項目（含 commit hash、E2/E4 鏈、AMD 修文記錄）轉存到：
  `docs/archive/2026-05-19--todo_v55_translation_archive.md`
- 上次大規模歸檔已在以下文件累積，本次不再重複收納：
  - `docs/archive/2026-05-15--todo_v21_completion_cleanup_archive.md`
  - `docs/archive/2026-05-15--todo_v24_stale_rows_archive.md`
  - `docs/archive/2026-05-16--todo_v36_completion_cleanup_archive.md`
  - `docs/archive/2026-05-16--close_maker_first_phase_1b_round1_archive.md`
  - `docs/archive/2026-05-16--stage1_demo_a4c_tombstone_cleanup.md`
  - `docs/archive/2026-05-07--todo_v12_agent_openclaw_replan_archive.md`
  - `docs/archive/2026-05-09--w_audit_verified_closed_archive_v3.md`

維護契約：依 `docs/agents/todo-maintenance.md` 將本檔保持為活躍派工佇列；穩定專案脈絡寫進 `README.md`，agent 操作規則寫進 `CLAUDE.md` / `.codex/MEMORY.md`。

---

## §0.0 PM Freeze — Demo-Only Stage 1 + A4-C Tombstone Guard

**狀態**：ACTIVE PM freeze；AMD-2026-05-15-01 持有 rebase 權威。

- Stage 1 promotion evidence **僅限 Demo**：Stage 0 shadow → Stage 0R replay preflight（`eligible_for_demo_canary=true/false`）→ Stage 1 Demo micro-canary（1 策略 × 1 symbol × 7d）。Stage 0R 不是 Stage 1 PASS。
- Paper 不是 active promotion lane。任何計畫 / 命令 / env / 腳本 / runtime 若設 `OPENCLAW_ENABLE_PAPER=1` 為 promotion 用，**BLOCKED**，除非未來 operator 明示重啟 paper 作非 promotion 診斷用途。
- **A4-C tombstone**：`W-AUDIT-8d` BTC→Alt Lead-Lag 退出 active promotion，封存 no-revive（BTC 1m return + xcorr feature shape）。`panel.btc_lead_lag_panel` / `[57]` 僅保 diagnostic；不得作 Stage 0R 候選或 Stage 1 Demo cohort 來源。
- 未來 A4-C 重啟需：materially new predictive variable + preregistered validation + 全新 strategy×symbol Stage 0R packet 且 `eligible_for_demo_canary=true`。
- 當前 active alpha gates：W-AUDIT-8b Stage 0R 已 tombstoned；W-AUDIT-8a C1 transport proof `PASS_C1_PROOF_CANDIDATE`；W-AUDIT-8c source/test + V095 apply + production `allLiquidation.{symbol}` writer revival 已 DONE。writer revival 不蘊含 liquidation 策略可上線。

---

## §1 Sprint Milestone Banner（待 operator 拍板路線後重填）

歸檔詳情見 `docs/archive/2026-05-21--todo_v57_5_route_change_purge.md` §B。

**Live deploy hard precondition**（路線中立，不隨路線變更）：P0-EDGE-1 + P0-LG-3 (Wave 2.4 IMPL) + P0-OPS-1..4 全清 → operator 決議是否啟動 live envelope。LG-1 + LG-2 已 DONE WITH GAP/CAVEAT 2026-05-21 不再 blocker（見 §12.4 closure list）。

---

## §2 架構邊界

- 正式產品：`玄衡 · Arcane Equilibrium`。
- 交易所目標僅 Bybit。
- Rust `openclaw_engine` 是交易 / 風控 / 策略 config / 執行的權威。
- Python/FastAPI 是 control plane / bridge / GUI 後端 / replay+orchestration surface / 本地 5-Agent runtime host。不是交易事實層。
- 標準 GUI = FastAPI console `trade-core:8000/console`（OpenClaw Control Console）。
- 外部 OpenClaw Gateway 僅做通訊 / mobile / supervisor / proposal relay。不是交易 conductor，不是本地 5-Agent runtime，不是第二 GUI。
- 本地 Scout / Strategist / Guardian / Analyst / Executor 留在 TradeBot 內。Cloud L2 呼叫須走一次 supervisor escalation packet + 顯式 budget/model config + durable `agent.ai_invocations` ledger reservation。
- Scanner 是 always-on 基礎設施（市場脈絡 / active-universe attribution / route fitness / opportunity evidence / legacy would-block audit）。不是交易權威，無法 hard-gate opens / closes / live auth / order dispatch。
- `MessageBus` = legacy/advisory trace。權威 agent promotion 須 typed lineage：StrategySignal → StrategistDecision → GuardianVerdict → ExecutionPlan → Decision Lease / idempotency → ExecutionReport。
- Replay 是 advisory / diagnostic。可加速 preflight；不能取代 runtime lineage 或授權 live promotion。
- **Graduated Canary rebase**（AMD-2026-05-15-01 取代 AMD-2026-05-09-03 Stage 1 paper 語意）：alpha-bearing 走 Stage 0 shadow → Stage 0R Replay Preflight（`eligible_for_demo_canary=true/false`，非 Stage 1 PASS）→ Stage 1 Demo micro-canary（1 策略 × 1 symbol × `Environment::Demo` × 7d）→ Stage 2 demo extended ×14d → Stage 3 demo full ×21d → Stage 4 LIVE_PENDING。DOC-08 §12 9 條安全不變量 / SM-04 ladder / Live boundary 5-gate / §二 16 原則硬不變式 4 範圍**仍強制 binary fail-closed**，不被 graduated canary 觸碰。

---

## §3 當前活躍狀態

- W-C MAG-082 Stage 2 **WINDOW_PASS 2026-05-11** 與 W-D MAG-083/MAG-084 **DONE 2026-05-11**：已關閉；proposal / mobile / Stage 3+ / true-live gates 仍另立，被 edge/LG/ops 前置卡。
- A4-C BTC→Alt Lead-Lag active-promotion marker 移除：Step 5b 與 RCA 封存 **GATE-RED / no-revive**；`panel.btc_lead_lag_panel` 留 diagnostic-only。OI-confirmed 5m packet 僅是 replay spec，不改變 eligibility。
- `[55]` 已被 `P1-HEALTHCHECK-55-INVARIANT` source-cleared；`[67]` 經 feature baseline apply 後恢復 PASS；`[4]` phys lock 與 `[Xb]` triangulation 在 `7108035d` 之後 PASS。
- V079 / `learning.strategy_trial_ledger` runtime 已在 `trade-core` 應用（migrations 已到 V090）；觀察到 16,212 ledger rows。舊「V079 未 apply / engine 仍 5/8 binary」敘述已歸檔。
- **業務根因**：5 textbook 策略仍欠持續正 net edge。`P0-EDGE-1`、`P0-LG-1/2/3`、`P0-OPS-1..4`、Alpha Surface Phase C/D、替代 alpha 候選為當前路徑。
- **EDGE-P2-3 Phase 1b**：Round 1 Design/Governance + Worktree B 部署已 CLOSED（細節見 archive 2026-05-16 + 2026-05-19 v55 translation archive）。本 refactor 是 execution-quality optimization（fee saving ~$50-$200/年，per E3 empirical），不解 trading losses root cause；真實治癒走 W-AUDIT-8a/8b/8c alpha source 軸。
- **Trading losses Round 2 — Alpha Source Push**：Option A source/test + W-AUDIT-8c correction + V095 apply 已 DONE。C1 transport proof passed 2026-05-17，writer revival 已上線（`0e8a8ae8` / `bedc40c3`）。
- **2026-05-18 EDGE-P2-3 Phase 1b RUNTIME ACTIVATOR**：RESOLVED via deploy chain CLOSED；engine PID 1143103；`runtime.use_maker_close=true`。AC-A 24h 統計顯著性窗口已通過 INSUFFICIENT_SAMPLE 階段。
- **2026-05-18 W-AUDIT round 2 結局**：
  - W-AUDIT-8b Round 2 RED_FINAL **TOMBSTONED**（4-agent 4/4 APPROVE concur；spec v0.4 + AMD v0.7）
  - W-AUDIT-8a Phase B/C/D Wave 1 **MERGED**（B-REM-1 / B-REM-5 + ADR-0023 / C1-LIQ-WRITER + `[67]`）
- **2026-05-18 multi-agent dispatch race incident**：lesson learned = 不再多 E1 同時並行；single-agent sequential + E2 鏈完才下個（已 enforce）。
- **2026-05-18 Phase 1b parameter calibration**：12H sample 100% timeout_taker fallback → P0 calibration DONE 2026-05-18 13:50 UTC（top cell `G-AB-01-C90` fill 70.8% / +3.37 bps simulated；Grid family `timeout_ms 30s → 90s` deployed）。Phase 2a 14d observation clock reset @ 13:50 UTC。
- **2026-05-19 v55 sprint**：4 軌道 closure（見 §0）。
- **2026-05-19 ~20:00 UTC v56 incident**：engine 7h43m trading-inert（見 §-1）；新 P0 `P0-ENGINE-HALTSESSION-STUCK-FIX`；PA spec 已派；engine PID 2099215 自 20:09:36 起恢復；Phase 1b verification 繼續累積。
- **2026-05-20 operator 補資金**：demo $10k + live $1k 落地。路線提案（v4 / v4.1 / v4.2 / v4.3 / v4.4 / v5.0 / v5.2-v5.6）詳情歸檔；當前待 operator 隔壁拍板後重填 §-0 / §1。業務根因仍為「5 textbook 策略結構性 alpha-deficient」（per QC 2026-05-11 audit）。
- **2026-05-21 v57.4 closure 批 D**：QA D1 + PA D3 obs verify 完成；**LG-1 + LG-2 P0 DONE WITH GAP/CAVEAT**；P1-DATA-1..3-WATCH CLOSED；P1-EDGE-1 CLOSED；PA D3 建議 P1-EDGE-2 升 P0-FUNDING-ARB-DECISION-FORCE 待 operator 拍板；衍生 P1-LG1-DEMO-SLA-VIOLATION + P1-FUNDING-ARB-SL-GATE-BUG。Engine + watchdog 09:58:50 UTC graceful SIGTERM stopped；PM 13:31 UTC restart_all.sh --keep-auth 恢復（engine PID 2934602 / API PID 2934665 / watchdog PID 2936560 with Inert probe）；Phase 2a gap ~3.5h estimated 失 ~1.4 rows。D2 watchdog classifier source-only fix R2 SOURCE LAND（E1→E2→E4 PASS）。
- **2026-05-21 v57.5 closure 批 E+F**：E 批 TODO 路線變更 purge + closure 歸檔（A+B+C+D 全收 §12.4）；F 批 4 並行 attack actionable problems（E5 P1-LG1-DEMO-SLA / FA P1-FUNDING-ARB-SL / E1 P2-OBS-WILSON / PA P2-CANARY-FILE-SIZE）。

---

## §4 活躍派工佇列

**狀態圖示**：✅ DONE / ⏳ PENDING / 🟡 PARTIAL / 🔵 ACTIVE / ⛔ DEFER

### §4.1 Wave Roster — 路線中立 legacy entries（雙軌制 T1-T9 已歸檔）

| 序 | Wave | Owner | 狀態 | 出口條件 |
|---:|---|---|---|---|
| 1 | `W-F` Edge/data quality + Live Gate 基座 | PM→QC/MIT/PA→E1/E4→PM | 🟡 **LG-1+2 DONE 2026-05-21**；LG-3 待 Wave 2.4 IMPL DISPATCH | H0 production caller ✅ / pricing binding ✅ / supervised-live state machine ⏳ |
| 2 | `W-G` Proposal/approval/mobile relay | PM→CC/FA/PA→E1/E2/E4→PM | 🟡 **BACKEND 基座 DONE**（待 mobile relay）| Gateway/console proposal/approval relay；不可直發 order/config/live-auth |
| 3 | `W-AUDIT-4` ML 基座 + dead schema | E1×6 + MIT + E2 + E4 | 🟡 **PARTIAL**（W-AUDIT-4b retained 範圍 see §11.2）| 修正後保留範圍見 §11.2 |
| 4 | `W-AUDIT-8a` Alpha Surface 基座 | PA→E1→E2→E4 + MIT/QC/CC/BB→PM | ✅ Wave 1 MERGED；Wave 2 待路線敲定 | Tier 2-4 routing 待 operator 路線敲定 |
| 5 | `W-AUDIT-8b` A4-A Funding Skew Directional | — | ⛔ **TOMBSTONED 2026-05-18 no-revive** | — |
| 6 | `W-AUDIT-8c` A4-B Liquidation Cluster Reaction | PA→E1→E2/E4→MIT→BB→PM | ✅ writer DONE；策略 launch 待路線敲定 | Stage 0R / design gate 走路線拍板後路徑 |
| 7-10 | `W-AUDIT-8e/8f/8g/8h` (Strategist Orchestrator / Hypothesis Pipeline / Live Promotion Gate / GUI tab) | PA spec→E1 IMPL | 待路線敲定後 re-route | 原映射歸檔；待新路線重組 |
| 11 | `W-AUDIT-10`（R-5）Spec-as-Code + Module Lifecycle SM | PA spec→E1 IMPL | ⛔ **DEFER** 中期 | CI gate spec drift > 7d auto-fail + 模組/表 lifecycle 標頭 |
| 12 | `EDGE-P2-3 Phase 1b` Close-Maker-First Refactor | PA→E1→E2→E4→QA→PM | ✅ **DEPLOY DONE**；Phase 2a observation 中 | Phase 2a 14d clock reset @ 2026-05-18 13:50 UTC；verdict 視窗 T+96-120h（2026-05-22~23 UTC）|

### §4.2 跨 Wave 衝突仲裁（4 條，PA §3.3 必繼承）

| # | 衝突 | 範圍 | 解 |
|---|---|---|---|
| 1 | W-AUDIT-8a Phase A migration ↔ W-AUDIT-6d mid-ground 5 策略改動 | `bb_breakout/mod.rs` / `ma_crossover/strategy_impl.rs` / `bb_reversion/mod.rs` | 序列化：先 6d mid-ground，再 8a Phase A |
| 2 | W-AUDIT-9 T3 shadow_mode_provider stage-aware ↔ ExecutorAgent shadow_mode 接線 | `executor_config_cache.py` / `executor_agent.py` | W-AUDIT-3b 必先 land；T3 結束前 ExecutorAgent shadow=true 不動 |
| 3 | W-AUDIT-8a Phase B+C ↔ W-AUDIT-5b 性能 wave | `tick_pipeline/mod.rs` | Phase B+C 並行於 N+1，5b 性能 catch-up reserved slot |
| 4 | A 群策略候選 ↔ W-AUDIT-9 Stage 1 Demo cohort 選擇 | governance/canary | **RESOLVED 2026-05-16**：Stage 1 為 Demo-only；A4-C tombstoned，不可作 cohort 來源 |
| 5 | TODO `W-AUDIT-8b/8c` ↔ legacy execution_plan `8b/8c` 檔名 | `docs/execution_plan` | **TODO IDs 為 SoT 2026-05-15**：`8b` = A4-A Funding Skew，`8c` = A4-B Liquidation Cluster；舊 `w_audit_8b_strategist...` / `w_audit_8c_hypothesis...` 是 R-2/R-3 alias（現為 `8e/8f`），不可拿來當策略 spec |

---

## §5 Sign-off Delta

完整 Sprint N+0 22-invariant ledger 已歸檔（v21 cleanup archive）。當前 delta：

- ⛔ **A4-C active-promotion marker 已移除 2026-05-16**：Step 5b / RCA 封存 no-revive；只留 tombstone guard 與 diagnostic panel 引用。
- 🟡 **OI-confirmed 5m Stage 0R packet 非 promotional**：定義 `bb_breakout_oi_confirmed_5m` replay 接受規則；read-only feasibility probe 樣本量 < Stage 0R 下限（`n=9` pooled；每 symbol < 100）且 gross 15m 為負，不能作 promotion 證據。
- ⏳ **A 群 alpha-source 不變量**：`declared_alpha_sources()` vs real logic re-check 待新 alpha 候選 land 後再啟。
- 🟡 **W-AUDIT-4b 修正後範圍**：透過 §11.2 retained tables/views/drop scope 維持 active；`P1-WA4B-INSERT-1` 已完成。
- `[55]`、W-AUDIT-3b、F-08 cron、`P0-MIT-LABEL-CLOSE-TAG-1` 細節已歸檔（v36 cleanup archive）；剩餘 edge 風險仍由 `P0-EDGE-1` 追蹤。

---

## §6 當前 W-AUDIT 優先順序

PM/PA/FA 三方交叉檢查後：

1. **True-live 仍 blocked**：被 `P0-EDGE-1`、`P0-LG-1/2/3`、`P0-OPS-1..4` 卡住。v56 `P0-ENGINE-HALTSESSION-STUCK-FIX` 已 CLOSED 2026-05-20；halt trigger 根因 follow-up 走 `P1-HALT-TRIGGER-ROOT-CAUSE-INVESTIGATION-1`。
2. **Stage 1 Demo micro-canary 仍 blocked**（非 active execution）：無 active paper cohort，無 A4-C cohort 候選；launch 需未來 strategy×symbol Stage 0R packet 且 `eligible_for_demo_canary=true` + AMD-2026-05-15-01 內 runtime/lineage/operator gates 全通。
3. **Alpha path**：`W-AUDIT-8b` tombstoned；`W-AUDIT-8c` writer revival DONE；其他 W-AUDIT 8a/8e/8f/8g/8h 路徑待 operator 路線敲定後重組。業務鏈根因為 5 textbook 策略結構性 alpha-deficient（per QC 2026-05-11 audit）。
4. **Runtime blocker 更新**：`[27]`、`[55]`、`[67]` 已 closed；不解鎖 Stage 1 Demo（無綠燈 alpha Stage 0R cohort）；v56 P0 cycle 完整收口；LG-1 + LG-2 DONE 2026-05-21。
5. **Maintenance**：P2 hygiene 排在 alpha / LG / ops gates 之後；2026-05-20 P2 sweep 6 項 closure 已 land（§12.4 列表）。

### §6.1 A4-C BTC→Alt Lead-Lag Tombstone（2026-05-16）

`W-AUDIT-8d` A4-C 非 active promotion task。active docs 僅保以下 guard：

- 狀態：archived from promotion；diagnostic-only / no-revive（BTC 1m return + xcorr feature shape）
- 保留：`panel.btc_lead_lag_panel`、`[57] btc_lead_lag_panel_health`、歷史 rows（供未來 Hypothesis Pipeline 探索）
- 不保留：Stage 0R 候選 / Stage 1 Demo cohort 來源 / paper-based promotion 措辭 / threshold-only revive tasks
- 未來重啟：materially new predictive variable + preregistered validation + 全新 strategy×symbol Stage 0R packet 且 `eligible_for_demo_canary=true`

詳細 Step 5b / RCA / PM+QC+MIT verdicts 歸檔於 `docs/execution_plan/2026-05-15--a4c_btc_alt_lead_lag_archive_verdict.md` 與相應 archive。

---

## §7 W-AUDIT-6d Mid-Ground

詳細 保 6 / 砍 6 ledger 與 DSR K -12 推導已歸檔（v21 cleanup archive）。

**保留 active rule**：6 polishing 項仍 REJECT，未經未來 QC/PM 決議不可重啟；不可新增 per-symbol / per-threshold sweep（會膨脹 DSR trial count）。

---

## §8 D-02 Layer 2 手動 7d 試運行 SOP（Operator 自執行）

完整 6 步 SOP 見 FA report `2026-05-09--full_dispatch_business_chain_validation.md` §2。摘要：

1. **API key 取得**：Anthropic Console → Create Key（命名 `openclaw-layer2-manual-7d-trial`，monthly budget $5）
2. **寫入**：`echo "sk-ant-xxx..." > $OPENCLAW_SECRETS_ROOT/secret_files/anthropic/api_key && chmod 600`
3. **每日手動觸發 7d**：`curl -X POST http://localhost:8000/api/v1/layer2/run_session -d '{"trigger_kind":"manual_daily_probe","scope":"L1_triage","max_cost_usd":0.50}'`
4. **7d 4 指標觀察**：cost_today / decisions_assisted / avoided_loss / false_positive_rate
5. **Pass**：alpha > 2× cost + false_positive < 40% + 0 critical incident；**Fail**：alpha < cost OR false_positive > 60% OR ≥1 layer2 建議致 > 5 USDT 虧損
6. **Fail rollback**：`rm api_key && restart_all.sh --keep-auth`

**FA constraint**（invariant 15）：D-02 SOP 不可自動化為 cron / event-trigger（會違 ADR-0020 manual+supervisor-only）。預期 +2-5 USDT/week alpha；7d < 1 USDT/week 不值人工成本 → 建議 abort。

---

## §9 Dormant D-XX 區（FA §5.2 必 explicit + reason）

| D-XX | 描述 | 狀態 | 原因 | 最早重啟 |
|---|---|---|---|---|
| D-13 | Cognitive Modulator | DORMANT | 3-Tier `consecutive_loss/weekly_pnl` 數據源未接齊 + alpha 無依賴 | Sprint N+8+ |
| D-14 | DreamEngine 完整自主進化 | DORMANT | Foundation Model + L4 跨策略 meta-learning（ADR-0020 限 manual）；Foundation Model 未 ready | long-tail |
| D-15 | OpportunityTracker 全 Agent 注入 | DORMANT | 不影響 supervised live；Sprint N+5 可選 | Sprint N+5 可選 |
| D-16 | openclaw_core 9 模組 sunset cleanup | DORMANT | ADR-0015 已標 permanent sunset candidates；其中 7 模組已被 `P2-DEAD-RUST-CLEANUP-1`（2026-05-18 commit `449f628b`）清除，餘 2 待 PA 下 sprint 確認 | Sprint N+6+ |
| D-17 | Layer 2 自主推理循環自動觸發 | **PERMANENT DORMANT** | ADR-0020 manual+supervisor-only by design | **不解** |

**FA constraint**：靜默漏寫 = 6 個月後 lobby 重新 review；explicit 標 dormant + reason + earliest reactivate = 防 strategy drift。

---

## §10 P0 — True-Live Blockers（active only）

| ID | 狀態 | 任務 | 接收條件 |
|---|---|---|---|
| `P0-EDGE-1` | 🔴 ACTIVE | Edge net-positive 決議 | 策略 edge 須 net-positive 或限定 supervised path；根因連到 `P0-MIT-LABEL-CLOSE-TAG-1` 1-day fix（最高 ROI）|
| `P0-LG-3` | ⚠️ **SPEC READY 10d, Wave 2.4 IMPL DISPATCH PENDING** | Live authorization / lease / drawdown / revoke / operator approval 全顯式且測過 | spec v2 final `2026-05-11--lg_3_spec_v2_final.md`（26 caveats incorporated）；V### 號需 PA refresh（V094 已被 W-AUDIT-8c 佔用→V099/V100）；E1×7 IMPL dispatch 待 operator 拍板路線後派 |
| `P0-OPS-1..4` | 🔴 ACTIVE | HTTPS / credential rotation / legal+ToS / first-day runbook | True-live 前置 |
| `P3-AGENT-SPINE-BENCH` | ⏳ scheduled N+3 | emit_entry_lineage / emit_fill_completion bench harness | E5：當前只有 tick_pipeline hot_path_baseline；補 1000×100 sample SLA monitoring |

**P0 closure 已歸檔到 §12.4 列表**：P0-ENGINE-HALTSESSION-STUCK-FIX / P3-SPINE-COUNTER-CACHE-ALIGN / LG-1 / LG-2 / P0-LG-1 / P0-LG-2 / P0-PHASE-1B-PARAM-CALIBRATION-1。詳情走 `docs/archive/2026-05-20--todo_v57_3_closure_cleanup_archive.md` + QA D1 report 2026-05-21。

---

## §11 P1 — 下個工程佇列

### §11.1 Sprint N+0 Active

已標完成歸檔於 v21 cleanup archive。當前活躍工作從 §10 / §11.2 / §11.3 開始。

### §11.2 W-AUDIT-4b 修正後保留範圍（invariant 19）

| ID | 物件 | 修正後分類 | Owner | 備註 |
|---|---|---|---|---|
| `P1-WA4B-INSERT-2` | `learning.cost_edge_advisor_log` | retained INSERT table / row-growth 已驗 | E1 | Writer live at `cost_edge_advisor/mod.rs`；2026-05-14 runtime 6091 rows。當前 demo `[cost_edge].enabled=false` → rows 為 `Disabled` / `ratio=NULL`；ratio-present rows 需另立 config 決議 |
| `P1-WA4B-INSERT-3` | `observability.drift_events` | retained INSERT table / readiness gated | E1 | Writer 在 `drift_detector.rs` 並在 `tasks.rs` spawn；依賴 active `feature_baselines` 與配置的 ADWIN burn-in（預設 30d）。不可未經 operator 同意移除 burn-in |
| `P1-WA4B-VIEW-1` | `learning.mlde_edge_training_rows` | companion VIEW | E1/MIT | 唯讀投影，非 INSERT 路徑。合約掛 ML training-data healthcheck |
| `P1-WA4B-VIEW-2` | `learning.scorer_training_features` | companion VIEW | E1/MIT | 唯讀投影；full unbounded count 成本高，請用 bounded/metadata probe |
| `P1-WA4B-DROP-1` | `learning.scorer_predictions` | dropped / no-DDL target | E1/MIT | V069 已 drop；無 producer 接線目標，除非未來 spec 重建 |

`P1-WA4B-INSERT-1` 完成細節歸檔於 v36 cleanup archive。

### §11.3 P1 — 其他活躍

| ID | 優先級 | 任務 | 備註 |
|---|---:|---|---|
| `P1-EDGE-2` (funding_arb) | 3 | ⚠️ **PA D3 建議升 P0-FUNDING-ARB-DECISION-FORCE**（待 operator 拍板）| PA 親跑 5/16 audit script = `INSUFFICIENT`（n=18<30，net_bps -49.74）+ funding_arb 14d fills=0 dormant + 1 fill 6.29% loss/notional 經 FA F2 RCA = **非 SL gate failure**（dyn_stop floor 6.25% + anti-cluster + slippage 預期範圍；audit script `SL_HARD_CAP_PCT=0.03` 是 stale 2026-05-02 期望值，W-AUDIT-6 已移除 override）|
| `P1-LG-5` | 4 | LG-5 reviewer maturity watch — PA D3 STILL_ACTIVE（不可降）| source 活躍；過去 14d daily fire 4-43 reviews/day；7d 共 66 review_live_candidate 全 verdict=defer **是設計正確訊號**（5 textbook 策略 EV negative per QC 2026-05-11 audit）；維持 watch 至首個 verdict ≠ defer 出現 |
| `P1-EDGE-P2-3-PH1B-DYNAMIC-BACKOFF-FOLLOWUP` | 4 | spec §5.4 完整 dynamic backoff state machine IMPL（per-symbol exp + cascade global pause）| Phase 1b 初版（`27f02a07`）取 per-symbol 5min 固定避 scope creep；Phase 2a Demo PASS 後另開 PR；PA 估 ~130 LOC |
| `P1-WATCHDOG-NETOUTAGE-SPARSE-LOG-OQ` | 4 | **NEW 2026-05-21 (D2 R2 OQ-NETOUTAGE-2)**：sparse-log scenario ratio gate 盲區 | E1 R2 推薦 defer；上游 mtime filter 提供部分保護；觀察 canary NETWORK_OUTAGE event 頻率後決定 |
| `P2-LG1-DEMO-SLO-CARVEOUT` | 4 | **降 P1→P2 obs ticket 2026-05-21（F1 E5 verdict）**：demo H0 max=2454μs **NOT_A_BUG** — 80% platform-level jitter（OS scheduler + cache miss + Instant::now vDSO）；H0Gate.check avg=4.86ns 純算術 | 推薦選項 B：SLA 文檔改「p99 < 1ms / max ≤ 5ms over 1M ticks」+ 加 HdrHistogram p99/p999 metric (~130 LOC Rust + Grafana panel)；LG-1 closure §1 evidence row 4 加 caveat「known platform jitter floor; not algorithmic」；0 blocker。E5 report `2026-05-21--p1_lg1_demo_sla_violation_hotpath_audit.md` |
| ~~`P1-FUNDING-ARB-SL-GATE-BUG`~~ | — | ✅ **CLOSED 2026-05-21**（FA F2 RCA verdict: NOT_A_BUG）| 80% Hypothesis (c) audit script `SL_HARD_CAP_PCT=0.03` stale；W-AUDIT-6 已移 override；6.29% 在 dyn_stop 6.25% floor + anti-cluster + slippage 預期內。**新衍生**：`P3-AUDIT-SCRIPT-STALE-CONST`（audit script SL 動態讀 TOML）+ `P2-DYN-STOP-FLOOR-SENTINEL`（5 策略 dyn_stop floor 加 sentinel test）。FA report inline §6 OQ-3..5 |
| `P1-HALT-TRIGGER-ROOT-CAUSE-INVESTIGATION-1` | 3 | v56 P0 closure 未解 root cause：drawdown 10.2% vs 25% threshold 觸發 halt 數學不通 | forensic `halt_audit.log` armed；passive wait 下次自然事件；不主動 push |
| `P1-LEASE-1` | 3 | **升 P1 from P2**（2026-05-20）：清掃 terminal `lease.rs:303` `objects` entries + HashMap `lease_id_to_idx` leak | **依賴 P0-LG-3 Wave 2.4 IMPL DISPATCH 完成後**才排專案（否則觸碰 Decision Lease 核心干擾 LG-3 IMPL 前置）；spec 需 5 元素（terminal state / hashmap 同步 / audit-preserve prune / 觸發時機 / Python `_lease_sm` 對等同步）；工時 ~4-6h IMPL + 對抗 chain |
| `P2-CANARY-FILE-SIZE-REFACTOR` | 5 | **F4 PA verdict 2026-05-21 DEFER**：等下次 800 LOC bulk 治理 wave 或 inert_probe/classifier 內部演進到 700+ LOC trigger | PA option B private subpackage `_engine_watchdog/`（6 module）+ slim CLI facade；0 caller/test/doc 改動；估 11h；機會成本 vs P0-FUNDING-ARB / LG-3 不經濟；保留 backlog 持續 P5 |
| `P3-AUDIT-SCRIPT-STALE-CONST` | 6 | **NEW 2026-05-21（F2 FA 衍生 OQ-3）**：`audit/2026-05-16_funding_arb_14d_audit.py:71` `SL_HARD_CAP_PCT=0.03` 改為動態讀 `risk_config_demo.toml` 或標 STALE_REFERENCE | 小 polish；防未來 audit 重複指控；E1 ~30min |
| `P2-DYN-STOP-FLOOR-SENTINEL` | 5 | **NEW 2026-05-21（F2 FA 衍生 OQ-4）**：5 策略 dyn_stop floor `base = limits.stop_loss_max_pct × dynamic_stop.base_ratio = 25 × 0.25 = 6.25%` 加 sentinel test | 防未來 base_ratio drift 帶來 SL gate semantic 改變；E4 ~30min |

> v55 衍生：`FA-WATCHDOG-3STRIKE-ESCALATION-POLICY` 待 FA 設計後分配優先級。

歸檔的 P1 條目（P1-DATA-1..3-WATCH / P1-EDGE-1 / P1-WATCHDOG-NETOUTAGE-CLASSIFIER-FIX / P1-WATCHDOG-EXIT-CODE-CLARIFY）見 §12.4 已完成列表。

### §11.4 P0-MICRO-PROFIT — 微利根因治本路徑（2026-05-11 QC audit 拍板）

**背景**：QC 2026-05-11 audit verdict — 「為何盈利都是超微利潤」+「能否放大」。判定：當前 5 textbook 策略 7d EV<0（-17.82 bps demo）；**任何 sizing 槓桿 L>1 必放大虧損**（數學常數）。先修 alpha，再談 size。

**5 root cause + 占比**：
1. **Alpha 結構性缺失（~60%）** — 5 textbook 策略 post-publication decay
2. **Account size × 0.1% TOML 物理上限（~20%）** — $591 × 0.1% = $0.59/trade 設計上限
3. **Fee drag（~10%）** — 10.4% taker remnant + PostOnly missed-trade
4. **Signal target tight 設計（~5%）** — grid 22bps / bb 1-2σ / ma sub-1ATR
5. **Slippage + queue position adverse selection（~5%）**

**治本路徑**：W-AUDIT-8b tombstoned；W-AUDIT-8c writer revival DONE；其他 W-AUDIT-8a/8d/8e/8f 條目待 operator 路線敲定後 re-route（歸檔詳情見 `docs/archive/2026-05-21--todo_v57_5_route_change_purge.md` §E）。

**Total ETA = 12-17 sprint（3-4 月）— 真實 gross 轉正最早窗口**（路線中立估算）。

**Operator 5 zero/small cost action（2026-05-11 拍板）**：
1. ✅ DONE：修 `feedback_position_sizing` memory drift（3% → 註明 SSOT 0.1%/0.05%）
2. ⏳ PASSIVE wait：等 7d 重測 §3 [40]
3. ⏳ INFO gathering：Bybit fee tier 距 VIP1 還差多少 30d trading volume（被動 ROI ~0.5-1 bps RT）
4. ⏳ PASSIVE wait：TONUSDT 30d evidence → P1-CONDITIONAL-WATCH freeze 決議（2026-06-09 收口）
5. ✅ DEFER 記錄：D/E sizing 槓桿等 ML calibration N≥200 — 寫入 backlog 防過早 commit

**11 sizing 槓桿全 REJECT in current EV<0 state**（A/B/E/F = REJECT；C/I = CONDITIONAL；D = NEUTRAL；G/H/K = DEFER；J = APPROVE 被動）。

**Operator 守則**：
- 看見 memory「3%」**不要**直接套到 TOML（先讀 risk_config_*.toml SSOT）
- 任何「升 TOML sizing」提案在 EV<0 條件下 = 災難（先修 alpha）
- 信 config，不信 memory（per `math-model-audit` S1）

**Source**：`docs/CCAgentWorkSpace/QC/workspace/reports/2026-05-11--p1_micro_profit_amplification_math_analysis.md`

### §11.5 EDGE-P2-3 Phase 1b — Final Dispatch Plan 摘要

**Status**：Round 1（Design + Governance）closure + 30+ commit timeline + 4-agent verdict + IMPL Prereq status + next-round scope → 歸檔 `docs/archive/2026-05-16--close_maker_first_phase_1b_round1_archive.md`。Phase 1b main source/test 完成於 `ea4ceca6`；V094 Linux apply + engine-only deploy/restart 完成 2026-05-17。

**仍 active**：
1. ❌ `P0-EDGE-1` — `[40]` negative realized edge 仍 active
2. ⛔ `W-AUDIT-8b Stage 0R` — **TOMBSTONED**（細節歸檔）
3. ✅ `W-AUDIT-8a C1` — v2 24h proof technical PASS + writer revival DONE 2026-05-17
4. ✅ `P1-WAVE-3-5-LINUX-MIGRATION-BACKLOG` — DONE 2026-05-16
5. ✅ `P1-BBMF3-WIRE-1` — source/test + V094 apply + engine-only rebuild/restart DONE 2026-05-17
6. ✅ `W-AUDIT-8c` — source/test 修正 + V095 dry-run/MIT re-sign + Linux apply + writer revival DONE 2026-05-17。策略 launch/promotion 仍 future gate

**Runtime kickoff status**（精簡）：
- V094 Linux migration/deploy 授權 → deploy-chain regression → post-deploy healthcheck → PM sign-off：✅ DONE 2026-05-17
- Phase 1b runtime activation：✅ **DEPLOY DONE 2026-05-17 23:54 UTC**（engine PID 1143103）
- Calibration sweep + Rust timeout deploy：✅ **DONE 2026-05-18 13:50 UTC**（engine PID 1506208；grid family timeout 30s→90s）
- **Phase 2a 14d observation clock 已 reset @ 2026-05-18 13:50 UTC**；24h post-deploy AC-A SQL verification target ~2026-05-19 13:50 UTC
- Cross-wave consistency check pending（QA recommendation #3）
- Outstanding anomaly investigations（low-priority parallel SD agent 2026-05-18 dispatch）：SD-1 A axis（offset_bps）dead-variable / SD-2 PS family（phys_lock_gate4_stale_roc_neg）100% n_skip / 0 fill — 報告 `2026-05-18--phase_1b_calibration_sweep_anomalies_sd_report.md`
- 後續：24h AC-A real verdict → if PASS 繼續 Phase 2a 14d / if FAIL revert timeout 90s→30s 或 PA tune-further；Phase 2b LiveDemo / operator + AMD live carve-out / Phase 3 Mainnet 仍 future gate
- **v56 incident 衝擊**：2026-05-19 ~12:27-20:09 UTC 7h43m trading-inert 中斷 Phase 1b verification；engine 自 20:09:36 起新 PID 2099215 恢復，sample 繼續累積（n=13 起）。verdict 視窗（T+96h~T+120h，2026-05-22~23 UTC）不受影響但 sample velocity 有缺口。

### §11.6 12-Agent Full System Audit WPs（2026-05-16）— follow-ups

- **Source**：`srv/2026-05-16--full-system-audit-fix-plan.md`（PA consolidated + PM sign-off）
- **Wave 1-4 source/test**：完成並歸檔於 v36 cleanup archive

**剩餘 active follow-up**：
- WP-11 Phase 2 residual → §12 P2 backlog
- WP-12 ONNX 仍 deferred；rule-based fallback 為當前行為
- PA audit drift hardening → `P2-PA-CALLPATH-GREP-RULE`（已 DONE）
- LOC follow-up → `P2-COMMON-JS-LOC`（DONE）、`P2-TAB-LIVE-LOC`（DONE via JS extract）

---

## §12 P2 — 維護 backlog

### §12.1 Active backlog（3 項 deferred — operator push back rationale）

| ID | 任務 | 觸發 | Deferred 理由（2026-05-20 sweep） |
|---|---|---|---|
| `P2-LEASE-1` | ⬆️ **升 P1** 2026-05-20（見 §11.3 `P1-LEASE-1`）| 長期 soak 出現 memory growth 或 high-volume live 前 | operator 拍板升 P1；依賴 P0-LG-3 Wave 2.4 IMPL DISPATCH 完成；歷史 P2 級觸發條件保留作 reference |
| `P2-AUDIT-DEAD-CODE` | openclaw_core 9 模組 sunset（D-16 dormant）| ADR-0015 + AMD-2026-05-09-02 accept；Sprint N+6+ | **ADR-0015 治理硬不變式**：D-16 dormant 觀察期未跑完，提前 sunset 破壞觀察協議；保留待 Sprint N+6+；E5 2026-05-20 zombie inventory 確認 commit `449f628b` 已清乾淨 7 modules，剩餘 sunset 在觀察期 |
| `P2-WP05-CSP-UNSAFE-INLINE` | 🟡 SRI 部分 DONE 2026-05-18；完整 CSP nonce-based refactor 待 live-gate 前 P1 | live-gate 前 | §10 P0-OPS-1..4（HTTPS / cred rotation / legal）尚未做完；HTTP 環境下 nonce-based CSP 防護無實效；保留待 live-gate prereq 完成後升 P1 |

### §12.2 2026-05-20 P2 sweep 結算 — 6 項 DONE → §12.4 列表

詳情歸檔於 `docs/archive/2026-05-20--todo_v57_3_closure_cleanup_archive.md` §C。本次 sweep 包括：QA-TEMPLATE-CLOSE-MAKER-SPLIT-FIX / STRUCT-2 zombie inventory / AUDIT-VERIFY-3 V069 drop verify / ENTRY-CLOSE-MAKER analysis / STRESS-BB-BREAKOUT-FALSE-SQUEEZE / SIM-QUEUE-AWARE-ADJUSTMENT。Commit chain `12dcdcbc` + `e2d213b5` + `a39dd11b` + `c3f25496`。

### §12.3 2026-05-20~21 P2 sweep 衍生 follow-up（從 FA P2-ENTRY-CLOSE-MAKER 分析衍生）

| ID | 來源 | 任務 | 優先 | 狀態 |
|---|---|---|---|---|
| `P1-OBS-PLACEMENT-BBO-V094` | FA OBS-1 | 補 placement-time BBO 進 V094 audit `details` JSONB（append-only schema-compat） | P1 | ⏳ Phase 1b 14d freeze 後 |
| `P1-OBS-PRE-STOPOUT-RATE` | FA OBS-2 | 新 healthcheck `66_close_maker_pre_stopout_rate.py`（FA round 1 #5 緩解未掛 AC） | P1 | ✅ DONE 2026-05-21（E1 R1+R2 / E2 R1 RETURN + R2 APPROVE-COND / E4 regression；slot [71]→[66] 防 passive_wait 碰撞）|
| `P1-OBS-FILL-RATE-STRATIFY` | FA OBS-3 | `62_close_maker_fill_rate.py` 加 `--stratify {hour,dow,both,none}` flag | P1 | ✅ DONE 2026-05-21（同上）|
| `P1-SPEC-DEAD-ENUM-ADR` | FA SPEC-1 | V094 fallback_reason 3 dead enum 寫 ADR reservation note；不 sunset | P1 | ✅ DONE 2026-05-21（ADR-0028 Accepted-pending-commit）|
| `P2-EVID-TRADE-TAPE-ADR` | FA EVID-1 | ADR：`market.public_trades` + `market.orderbook_l2_snapshot` 寫盤策略（PA+MIT 起草） | P2 | ✅ DONE 2026-05-21（ADR-0029 Proposed；故意不 finalize schema 等 MIT calibration；6 步 dispatch 路徑 per PA report）|
| `P2-EVID-A-AXIS-IMPL-CHECK` | FA EVID-2 | offset_bps 變量是否進入 cross 判定（25% probability IMPL bug） | P2 | ✅ AUDIT DONE 2026-05-21（FA verdict：**IMPL WIRED FOR LOG ONLY** — 100% silent dead；升級為 OQ-C4-1..5 5 條 follow-up；建議 sweep prune A axis + spec v1.4 mark deprecated）|
| `P2-SPEC-PHYS-LOCK-AUDIT` | FA SPEC-2 | Phase 1b spec §4.3 補 `phys_lock_gate4_stale_roc_neg` audit | P2 | ✅ AUDIT DONE 2026-05-21（FA verdict：**spec PRESENT but incomplete** — emit point v2.rs:359 production wiring 完整；spec §4.3 缺 observability SLA；建議 v1.4 加 §4.3.1 + [72] healthcheck + per-reason kill-switch）|
| `P2-SPEC-HOUR-DISTRIBUTION-AC` | FA OQ-5 | spec v1.4 加 secondary AC | P2 | ✅ DONE 2026-05-21（TW v1.3→v1.4 加 AC-20 hour distribution ≥ 18h cover + ≥ 3 attempts；secondary AC，違反僅 WARN）|

### §12.3a P2 sweep 衍生新增 follow-up（C 批 2026-05-21 完成後派生）

| ID | 來源 | 任務 | 優先 |
|---|---|---|---|
| `P2-OBS-PRE-STOPOUT-WILSON-SUBCLAUSE` | E2 R2 MEDIUM-D1 deferred | `66_close_maker_pre_stopout_rate.py` 補 Wilson upper bound sub-clause（mirror [62] AC-18 風格）；E2 已接受 raw rate 設計，但 min_sample=30 對 0.10 boundary 不 conservative | P2 |
| `P1-SWEEP-A-AXIS-PRUNE` | FA C4 verdict + SD-1 | 下一輪 phase_1b sweep 把 A axis (`offset_bps` 0/+1/+2) collapse 到 1-value；可省 ~58 cells × ~17ms；spec v1.4 mark `offset_bps` as deprecated config field | P1 |
| `P2-PHYS-LOCK-72-HEALTHCHECK` | FA C6 OQ-C6-2 | 新 standalone healthcheck（slot 待 PA 分配，建議 [68]/[69]/[76]）監測 `phys_lock_gate4_stale_roc_neg` trigger rate vs `gate4_giveback`；daily cron | P2 |
| `P2-FALLBACK-DEAD-ENUM-90D-AUDIT` | ADR-0028 §6 cadence | 90d 後（2026-08-21）re-audit V094 `close_maker_fallback_reason` 3 dead variants；確認仍 dead-by-design 非 missing-data；若 EngineShutdownSafety 仍 0 → confirm；FastEscalate/NotAttempted 須 ops scenario sim 驗 emit path | P2 |

### §12.4 已完成 P2 條目（細節歸檔於 2026-05-19 v55 translation archive / 2026-05-20 v57.3 archive）

- `P2-DEAD-SCHEMA-DROP-1` ✅
- `P2-DEAD-RUST-CLEANUP-1` ✅
- `P2-PERCEPTION-DEPRECATE-1` ✅
- `P2-H0-DISPLAY-LABEL-1` ✅
- `P2-ORDERS-INTENT-ID-WRITER-GAP-1` ✅
- `P2-WP05-FUP-1` ✅ 32/32 全收
- `P2-COMMON-JS-LOC` ✅
- `P2-ENTRY-PATH-0PCT-MAKER-FILL-RCA` ✅
- `P2-TAB-LIVE-LOC` ✅ via `P2-TAB-LIVE-JS-EXTRACT`
- `P2-CROSSTAB-I18N` ✅
- `P2-STOCHASTIC-LEAK` ✅
- `P2-START-LOCAL-HELPER` ✅
- `P2-PA-CALLPATH-GREP-RULE` ✅
- 5 個 `P2-PORTFOLIO-RESTING-*` follow-up ✅
- `P2-QA-TEMPLATE-CLOSE-MAKER-SPLIT-FIX` ✅ 2026-05-20
- `P2-STRUCT-2` ✅ 2026-05-20
- `P2-AUDIT-VERIFY-3` ✅ 2026-05-20
- `P2-ENTRY-CLOSE-MAKER-REAL-FILL-FIX` ✅ ANALYSIS 2026-05-20
- `P2-STRESS-BB-BREAKOUT-FALSE-SQUEEZE-COINCIDENTAL-PASS` ✅ 2026-05-20
- `P2-SIM-QUEUE-AWARE-ADJUSTMENT` ✅ 2026-05-20
- `P1-EDGE-1` (ma_crossover/grid blocked_symbols freeze) ✅ CLOSED 2026-05-21（PA D3 reverify；freeze registry permanent + static guard + RFC counterfactual SOP 三位一體 commit `c081029d`；7d new fills=0）
- `P1-DATA-1..3-WATCH` ✅ CLOSED 2026-05-21（PA D3 DOWNGRADE_TO_OPTIONAL；row-rolloff 14d 穩定）
- `P1-WATCHDOG-EXIT-CODE-CLARIFY` ✅ DONE 2026-05-20（commit `dc33eb2d` + `232c3aff`；exit codes 語意分區）
- `P1-WATCHDOG-NETOUTAGE-CLASSIFIER-FIX` ✅ SOURCE DONE 2026-05-21（E1 R1→E2 R1 RETURN→E1 R2→E2 R2 APPROVE→E4 PASS；207/207；4-gate classifier + AMBIGUOUS guard；commit `7f959673`；deploy 待 operator 決定 watchdog daemon 重啟時機）
- `P0-ENGINE-HALTSESSION-STUCK-FIX` ✅ DONE 2026-05-20 ~02:15 UTC（Layer A `6cf476c4` + Layer B `fec63743/8ad70090`；Halt trigger 根因仍 UNRESOLVED → P1-HALT-TRIGGER-ROOT-CAUSE-INVESTIGATION-1；歸檔 §A）
- `P3-SPINE-COUNTER-CACHE-ALIGN` ✅ DONE 2026-05-20（commit `879e3852`；21/21 tests pass；待 Linux rebuild）
- `LG-1` H0 production caller ✅ DONE 2026-05-21 PASS WITH 1 KNOWN GAP（H0 wired 18M+ ticks；fail-closed never fired 5h window；衍生 `P1-LG1-DEMO-SLA-VIOLATION`）
- `LG-2` Provider pricing binding ✅ DONE 2026-05-21 PASS WITH 1 CAVEAT（startup assertion fire；tick path 0 caller BY-DESIGN per spec §2.4）
- `P0-LG-1` / `P0-LG-2` 與 LG-1 / LG-2 同 closure 2026-05-21
- `P1-FUNDING-ARB-SL-GATE-BUG` ✅ CLOSED 2026-05-21（FA F2 RCA NOT_A_BUG；audit script `SL_HARD_CAP_PCT=0.03` stale；衍生 `P3-AUDIT-SCRIPT-STALE-CONST` + `P2-DYN-STOP-FLOOR-SENTINEL`）

完成的 Sprint N+2 P2 條目（`P2-N2-1..4`）歸檔於 v36 cleanup archive。
歷史 P0-PHASE-1B-PARAM-CALIBRATION-1 等已歸檔於 v55 translation archive。

---

## §13 Push Back / Risk 治理記錄（不可漏失，FA §5.6）

### PA Push Back（已 RESOLVED 2026-05-09 operator (a)）
- **原 risk**：Sprint N+0 5/5 HOT capacity = 任一 E1 故障 = 阻塞 critical path
- **Operator 拍板 (a)**：提供 1 stand-by E1，Sprint N+0 capacity 升 6 並行（5 active + 1 stand-by）
- **記錄**：v19 §0 Sprint Banner / §5.4 invariant 22 / §6 Day 0-3 dispatch

### FA Push Back（採納，記入治理）
1. Track W vs Track A 預算 — Track W 92h 是 supervised live 前置門檻（合規 / 安全 / 可觀測 baseline），**不能被 Track A lobby 取代**
2. D-02 SOP 預期上限 +2-5 USDT/week；7d < 1 USDT/week 不值人工 fixed cost → 建議 abort
3. A/B/C 候選預期 +3-7% 業務鏈是中位估，新 alpha source **0% PASS 率歷史不支持「三都 PASS」樂觀情境**
4. W-AUDIT-6d 砍 6 polishing 是 DSR 數學意義 right move（K -12），不是省工時妥協

### 4-agent loss audit cross-fact-check（撤銷的 stale belief）
- **QC v2-NEW-4 Donchian「runtime contaminated」過期 belief**：MIT 校核 + PM 直接驗證確認 runtime 自 `75741eff`（2026-04-28）起 leak-free 11 天；`ad14db07` 僅補 regression test。後續 audit / push back 不可再引此 finding 為 active runtime issue。

---

## §14 排程

| 日期 | 工作 | Gate |
|---|---|---|
| 2026-05-21~ | 路線變更區待 operator 拍板後重填 §14 詳細排程 | 路線中立 milestone 留下方 |
| 2026-05-22~23 | Phase 2a 14d observation verdict 視窗（T+96-120h from 2026-05-18 13:50 UTC clock reset）| 24h post-deploy AC-A SQL verification 已過；待 verdict |
| 2026-06-15 | Supervised live 樂觀帶（業務鏈 75%+）| conditional on P0-LG-1/2/3 + P0-OPS-1..4 + Track A demo Sharpe > 1.0 |
| 2026-06-30 | Supervised live 中位帶（業務鏈 80%+）| ~40% probability per FA |
| 2026-07-15 | Supervised live 悲觀帶（業務鏈 85%+）| ~25% probability per FA |

---

## §15 派工規則 + Handoff 檢查

### 派工規則
- PM-first triage for every wave
- 實作工作：`PM → PA → E1/E1a → E2 → E4 → QA → PM`，跳過角色需 explicit justify
- 安全 / 部署 / runtime：`PM → E3 → BB（若涉交易所）→ PM`
- 量化 / 資料決議：`PM → QC → MIT → AI-E（若涉模型成本）→ PM`
- 每個 green checkpoint 提交 subject + body，push origin，再以 fast-forward 同步 Linux
- 非 CI-relevant commit（doc / governance / TODO update / report land）加 `[skip ci]` 保 CI 額度
- 不可 rebuild / restart / 動 live auth / 改 scanner evidence contract / 解鎖 executor shadow / 啟 lease-router / 新增 OpenClaw write/proposal 路徑，除非 operator 顯式授權
- W-AUDIT-6d 砍 6 子項：E2 必 grep blacklist；命中即 reject merge
- **新增（v55 governance flag）**：sign-off SOP 加 `cargo test -p openclaw_engine --release`（no --lib）以覆蓋 tests/ integration crate

### Handoff 檢查

```bash
git -C /Users/ncyu/Projects/TradeBot/srv status --short --branch
ssh trade-core "cd ~/BybitOpenClaw/srv && git status --short --branch"
ssh trade-core "python3 helper_scripts/canary/engine_watchdog.py --data-dir /tmp/openclaw --status"
ssh trade-core "cd ~/BybitOpenClaw/srv && bash helper_scripts/db/passive_wait_healthcheck.sh --quiet"
```

---

## §16 References

### 4-Agent Loss Audit（2026-05-09）
- **PA dispatch plan**：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--full_dispatch_engineering_plan.md`（commit `d3bf7be2`，689 行）
- **PA architectural redesign**：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--full_loss_architectural_root_cause_redesign.md`
- **PA merge analysis**：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--todo_qctodo_merge_analysis.md`
- **FA business chain validation**：`docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-09--full_dispatch_business_chain_validation.md`（commit `5a2dee98`）
- **FA dormant alpha inventory**：`docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-09--full_loss_dormant_alpha_features_inventory.md`
- **FA merge advice**：`docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-09--todo_qctodo_merge_business_chain_advice.md`
- **4-agent loss audit worklog**：`docs/worklogs/2026-05-09--4_agent_loss_audit_and_5_actions.md`
- **QCTODO archived**：`docs/archive/2026-05-09--qctodo_sprint_n0_n5_archive.md`

### Spec / Amendment
- **W-AUDIT-8a spec**：`docs/execution_plan/2026-05-09--w_audit_8a_alpha_surface_foundation_spec.md`（commit `c13c811e`）
- **AMD-2026-05-09-02**（5 P0-DECISION-AUDIT closure）：`docs/governance_dev/amendments/2026-05-09--operator_decision_audit_closure.md`
- **AMD-2026-05-09-03**（Graduated Canary Default）：`docs/governance_dev/amendments/2026-05-09--AMD-2026-05-09-03-graduated-canary-default.md`（commit `b1891023`）
- **AMD-2026-05-15-01**（Canary Rebase Replay Preflight + Demo Micro-Canary）：`docs/governance_dev/amendments/2026-05-15--AMD-2026-05-15-01-canary-rebase-replay-preflight-demo-micro-canary.md`
- **AMD-2026-05-15-02 v0.7**（EDGE-P2-3 Phase 1b Close-Maker-First + Runtime Activation Layer + W-AUDIT-8b tombstone clause）：`docs/governance_dev/amendments/2026-05-15--AMD-2026-05-15-02-edge-p2-3-phase-1b-close-maker-first.md`
- **EDGE-P2-3 Phase 1b spec v1.3**：`docs/execution_plan/2026-05-15--edge_p2_3_phase_1b_close_maker_first_spec.md`
- **V094 hybrid schema migration spec**：`docs/execution_plan/2026-05-15--v094_close_maker_first_audit_schema_spec.md`
- **Round 1 Closure Archive**：`docs/archive/2026-05-16--close_maker_first_phase_1b_round1_archive.md`
- **W-AUDIT-8b Funding Skew Directional spec v0.4 tombstone**：`docs/execution_plan/2026-05-15--w_audit_8b_funding_skew_directional_spec.md`
- **v56 P0 Engine HaltSession TTL spec**：`docs/execution_plan/2026-05-19--engine_haltsession_ttl_and_watchdog_inert_probe_spec.md`（~600-1000 LOC，PA drafting，ETA 2-3h from 2026-05-19 20:30 UTC）
- **ADR-0015** openclaw_core sunset / **ADR-0017** scanner authority retirement / **ADR-0018** funding_arb retire / **ADR-0020** Layer 2 manual+supervisor-only / **ADR-0022** strategist cap / **ADR-0023** SourceAvailability schema

### Close-Maker-First 3-agent Verdicts（2026-05-15 round 1 — Spec）
- **PM verdict**：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-15--close_maker_first_pm_verdict.md`
- **PA verdict + spec outline**：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-15--close_maker_first_pa_verdict.md`
- **FA verdict + AC**：`docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-15--close_maker_first_fa_verdict.md`

### Close-Maker-First 4-agent AMD Adversarial Review（2026-05-15 round 2 — AMD）
- **QC**：`docs/CCAgentWorkSpace/QC/workspace/reports/2026-05-15--amd_2026_05_15_02_4agent_review_qc.md`
- **FA round 2**：`docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-15--amd_2026_05_15_02_4agent_review_fa.md`
- **BB**：`docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-15--amd_2026_05_15_02_4agent_review_bb.md`
- **MIT**：`docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-15--amd_2026_05_15_02_4agent_review_mit.md`
- **Consolidated 4-agent summary**：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-15--amd_2026_05_15_02_4agent_review_consolidated.md`

### v56 P0 incident
- **E2 RCA verdict**：`docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-19--engine_watchdog_respawn_loop_and_trading_inert_rca.md`
- **PA spec（drafting）**：`docs/execution_plan/2026-05-19--engine_haltsession_ttl_and_watchdog_inert_probe_spec.md`

### Adversarial Verification
- **v3 PM Sign-off summary**：`2026-05-09--audit_fix_verification_v3_summary.md`
- **v2 PM Sign-off summary**：`2026-05-09--audit_fix_verification_v2_summary.md`
- **v1 PM Sign-off summary**：`2026-05-09--audit_fix_verification_summary.md`
- **PA Fix Plan v2（DUAL-TRACK）**：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--full_audit_pa_fix_plan_v2.md`
- **2026-05-08 12-Agent Full Audit + PA Fix Plan**：`2026-05-08--full_audit_fix_plan.md`
- **Verified-closed archives**：`docs/archive/2026-05-09--w_audit_verified_closed_archive_{,v2,v3}.md`

### Bybit / API
- **Bybit API 字典/審計**：`docs/references/2026-04-04--bybit_api_reference.md` · `docs/audits/2026-04-04--bybit_api_infra_audit.md`

### Process
- **Operator G3-08 enable evidence**：commit `dddc5dc1` restart_all.sh wire + 2026-05-09 17:27 UTC engine.log `cost_edge_advisor spawned env=1 phase=B_shadow`

### v55 翻譯歸檔
- **歷史 ✅ DONE 詳情**：`docs/archive/2026-05-19--todo_v55_translation_archive.md`（本次同步建立，收納 v37-v55 之 carry-forward 全文 + §11 / §12 已完成 commit chain）
