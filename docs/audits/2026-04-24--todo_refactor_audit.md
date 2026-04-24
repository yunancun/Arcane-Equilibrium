# TODO 全面重構 Audit — 2026-04-24

**審計類型**：8 角色並行 audit（PM / QA / FA / PA / CC / QC / AIE / MIT）
**執行方式**：主會話派發 5 個並行 sub-agent（跨角色合併），主會話交叉驗證 + 關鍵差異親驗
**觸發**：Operator 指令「TODO 太亂、信息量太大，需要重新校準、重構工作安排、重點關注 Edge / AI / ML / 多 Agent」
**產出**：本 audit + 新 TODO.md（帶指針回指向本檔）+ CLAUDE.md §三 更新 + memory 新增項

---

## 一、整體結論（Executive Summary）

### 1.1 系統當前真實狀態

| 維度 | 狀態 | 證據 |
|---|---|---|
| **代碼實作度** | **誠實**（8/10 claim 完全符合 commit note） | CC+QC agent 逐項驗證 10 個關鍵 claim，僅 model_registry.py 430 行 vs `~295` 聲稱、WS-RETIRE 17 tests vs 11 聲稱 兩處行數誤差 |
| **Runtime 部署度** | **部分**（多項 commit 完成但未 `--rebuild`） | P1-11 FIX-26-DEADLOCK-1 / RUST-DOUBLE-PREFIX-1 / STRATEGIST-SCHED-CHANNEL-PAPER-ORPHAN-1 / RESTART-ALL-UVICORN-LOG-1 / EDGE-SCHEDULER-LEADER-1 / SCHEDULER-FAILURE-OBSERVABILITY-1 全部「待 `--rebuild` 生效」 |
| **策略 Edge** | **結構性負**（所有活躍策略 gross edge 負） | demo grid_trading 747 exits / −$43.36 / fee drag 74% · demo ma_crossover 135 exits / −$11.90 / 不對稱 2.54× · live_demo ma_crossover +$0.79（邊界但脆弱，樣本 102 不顯著） |
| **ML 管線** | **60% 完成 + 資料瓶頸** | 架構 ≥80%（training pipeline / registry / shadow writer 全實作），但 max slice `grid BLURUSDT 47/200 labels` + **`edge_estimates.json` 實際僅 1 cell** + mtime `2026-04-20 23:50`（3+ 天 stale！與 CLAUDE.md「162 cells」嚴重不一致） |
| **AI 層** | **80% 完成 + 接線 Gap** | H1-H5 middleware 完整（≥1,000 行全實作，非 stub）· 5-Agent ~4,415 行實作 · StrategistAgent live shadow=False / ExecutorAgent shadow=True 默認 · **Gap A**：ExecutorAgent→Rust IPC SubmitOrder receiver **未實裝** · **Gap B**：Layer 2 升級條件未量化 + 工具箱缺 `query_onchain/check_derivatives` |
| **多 Agent 協作** | **80% 代碼 / 50% 閉環** | 5 Agent 都 real（非 stub），但 Executor 回路未接 Rust → shadow log only / Path A（Rust strategist）與 Path B（Python ExecutorAgent）衝突仲裁機制未定義 |

### 1.2 三大核心危機（用戶特別關心）

#### 危機 1：Edge 結構性負（FA 結論）
**事實**：
- grid gross −0.8 bps/RT，fee 5.4 bps/RT → **net −6.2 bps/RT**
- PostOnly 最樂觀（50% maker fill）net = −4.7 bps/RT → **仍負**
- 只有 gross 從 −0.8 翻到 +2.0 bps 才有機會 net 正，**需策略層改進**
- `missing_edge_fallback_bps=10.0` 只是 Gate 1 繞行對照實驗，phys_lock 在負 edge 環境本質上只能「減損失」非「累積正利」

**推論**：EDGE-DIAG-1 Phase 2 實測 +11.95 bps clean signal 雖方向對但 magnitude 低於 FM 預測（+250-450 bps）10-40 倍，實際是 v1 linear proxy 對 v2 non-linear 的**樂觀估計上界**。真實可鎖利有限。

#### 危機 2：交易頻率過高、金額過小（PA 結論）
**事實**：
- grid demo 747 exits/24h（~31 筆/h）看似過高，但**實測 min gap 120.3s / avg 471.8s** → cooldown 60s × 2x trend boost 生效，頻率本身不算過度
- 但 fee per RT $0.054 vs gross −0.008/RT → **頻率再降也救不了負 gross edge**（PnL 和 fee 等比降）
- Memory 設計：3% risk/trade × 25 symbols 動態 qty → **實際倉位 $5-15/筆**（過小致單筆絕對 PnL 微小，fee 佔比放大）

**推論**：問題不是「頻率過高」而是「每筆邊際太薄，被 fee 吃掉」。PostOnly 改善 1.5-3 bps 不夠，**需策略層補 5+ bps gross edge**。

#### 危機 3：Learning Pipeline 半殼運行（MIT 結論）
**事實**：
- `learning.decision_features` 已累積 1.65M rows ✅
- `edge_estimator_scheduler` 每小時 cycle + backfill，但 **`settings/edge_estimates.json` 只有 1 cell（grid_trading::ORDIUSDT shrunk_bps −45.73）** + mtime 3+ 天前
- `run_training_pipeline.py` 6 stages 完整實作 ✅ 但 max slice **grid BLURUSDT 47/200 labels**
- `learning.model_registry` 骨架 ready ✅ 但 table 空（待訓練輸出）
- `shadow_exit_writer` 完全接線 ✅ 但 `shadow_enabled=false`（dormant）
- Teacher / LinUCB / Bayesian / RL 全休眠（5% 完成度）

**推論**：ML 鏈路「生產端到消費端」其實有一整條斷點：
1. `edge_estimates.json` 只寫進 1 個 cell 是**嚴重 bug 或 scheduler 異常**（應有 ≥100 cells 才正常）
2. Labels 累積速率遠低於預期（14/day/2 slice vs 原估 90-200/day）
3. ONNX 訓練未曾真跑（registry 空）
4. shadow_exit_writer 從未 flip on（無法驗證 Path A vs Path B 一致性）

### 1.3 TODO / CLAUDE.md 主要失真點（需更正）

| # | 失真項 | 真相 | 更正優先級 |
|---|---|---|---|
| 1 | CLAUDE.md §三 說 `edge_estimates.json 162/162 cells` | 實際檔案 1 cell，mtime 3+ 天前 | 🔴 P0 |
| 2 | TODO `model_registry.py ~295 LOC` | 實際 430 行 | 🟡 P2（誤差但非致命）|
| 3 | TODO `bybit_private_ws_status_writer.rs 11 unit tests` | 實際 17 tests | 🟡 P2 |
| 4 | CLAUDE.md §三 `shadow_enabled=false ... flip TOML 即啟` | 同 `missing_edge_fallback_bps` 類似 claim，已由 FUP-IPC 部分修正（EDGE-DIAG-1-FUP-SHADOW-ENABLED-IPC 待辦）| 🟡 P2 |
| 5 | TODO `FIX-01 H1-H5 AI Agent 接入` 記為待做 | H1-H5 middleware 代碼 100% 完整，真正缺的是 ExecutorAgent→Rust IPC SubmitOrder 接線 | 🟠 P1（描述錯誤導致優先級誤判）|
| 6 | `layer2_tools.py 906 行` 未被 E2 標記 | 超過 CLAUDE.md §九 800 行警告線 | 🟡 P2 |

---

## 二、整體工作流程圖（依賴 / 前置 / 交疊）

### 2.1 依賴關係圖（按實際阻塞分層）

```
                    ┌─────────────────────────────────────────┐
                    │  Operator 決策樞紐（不可省略）                │
                    │  • 21d demo 觀察期解鎖                    │
                    │  • Phase 5 edge 重評 Go/NoGo            │
                    │  • ExecutorAgent live 授權                │
                    │  • 下架策略（grid disable） 決策            │
                    └──────┬──────────────────────┬───────────┘
                           │                      │
        ┌──────────────────┼──────────────────────┼──────────────────────┐
        │                  │                      │                      │
     ┌──▼──────┐     ┌────▼──────────┐     ┌────▼──────────┐    ┌─────▼───────┐
     │ EDGE 軸  │     │ 資料累積軸     │     │ AI/Agent 軸    │    │ 架構 / 清尾軸 │
     │ (危機 1) │     │ (危機 3)       │     │ (危機 3)        │    │              │
     └──┬──────┘     └────┬──────────┘     └────┬──────────┘    └─────┬───────┘
        │                  │                      │                      │
  ╔═════▼═════╗     ╔═════▼═════════╗     ╔═════▼═══════════╗    ╔═════▼══════╗
  ║ 當下最關鍵  ║     ║ 當下最關鍵      ║     ║ 當下最關鍵        ║    ║ 當下最關鍵   ║
  ║           ║     ║                ║     ║                  ║    ║             ║
  ║ A1 禁 Grid ║     ║ B1 edge_      ║     ║ C1 ExecutorAgent ║    ║ D1 部署待    ║
  ║ (實測負)   ║     ║ estimates     ║     ║ IPC 接線          ║    ║ rebuild 項   ║
  ║           ║     ║ RCA +修        ║     ║ (shadow→live)    ║    ║             ║
  ╚═══════════╝     ╚═══════════════╝     ╚══════════════════╝    ╚═════════════╝
         │                  │                      │
  ┌──────┴──────┐    ┌─────┴──────┐         ┌─────┴──────────┐
  │             │    │            │         │                │
  ▼             ▼    ▼            ▼         ▼                ▼
 A2 ma_cross   A3  B2 加速      B3 dry-run C2 Layer 2 升級   C3 StrategistAgent
 R:R 修復     PostOnly labels    ONNX E2E   規則+工具          promote API
 (SL/TP定制)  1w驗證  (10x rate) (首模型)   (daemon+2 tools)   (觸發器)
         │                  │                      │
         └─────────┬────────┘                      │
                   │                               │
             ┌─────▼──────────────────────────────▼─────────────────┐
             │  Phase 5 重啟候選（edge 翻正後）                        │
             │  • cost_gate re-bind                                 │
             │  • Track L ML shadow                                 │
             │  • Phase 2/3/4 Dual-Track 推進                       │
             └──────────────────┬──────────────────────────────────┘
                                │
                   ┌────────────▼────────────┐
                   │  Live (最早 ~2026-05-23) │
                   │  依賴 5 gate 全綠         │
                   └─────────────────────────┘
```

### 2.2 被動等待項目（時間 + 條件 gated，非主動推進）

| 項目 | 時鐘起算 | 解鎖條件 | healthcheck |
|---|---|---|---|
| P0-2 LG-1 Demo 21d 觀察 | 2026-04-16 22:16 | 21d 零事故 + LG-2/3 + provider pricing | watchdog/engine_alive ✅ |
| EDGE-DIAG-1 Phase 3 | Phase 2 完成 2026-04-24 | `post-P013-clean` n≥200 + grid ≥50 cf + ma ≥50 cf + orphan ≥20 | `check [11]` ✅ cron 每日 06:00 UTC |
| P1-7 C ONNX training | edge_label_backfill daemon ON | max slice labels ≥200 | `check [2]` label_backfill ratio ✅ |
| P1-6 DEMO-BYBIT-SYNC-ORPHAN 1w | 2026-04-17 | orphan 消化 / P1-8 retriage 起效 | 需補 check（gap） |
| EDGE-P2-3 PostOnly 1w 驗證 | 2026-04-21 20:44 | maker fill rate 實測 + fee 降幅 + demo net edge 改善 | 需補 check（gap） |
| bb_breakout FIX-26 post-deploy | `--rebuild` 後 | 24h 首次 fill | `check [12]` ✅（已新增）|

### 2.3 去重合併（去掉重複 TODO）

| 併入項 | 被併入 | 理由 |
|---|---|---|
| ~~P1-19 BACKFILL-LABELS-STALLED-1~~ | P1-10 STRATEGY-ASYMMETRY-1 | RCA 2026-04-22 證明是 P1-10 症狀（fee drag → 少入場 → 少 label） |
| ~~FIX-01 H1-H5 AI Agent 接入~~ | 新 C-1 ExecutorAgent IPC 接線 | H1-H5 代碼已 100%，真正缺 ExecutorAgent→Rust SubmitOrder handler |
| ~~P1-12 BB-REVERSION-BLOCKED-1~~ | P1-11 BB-BREAKOUT/REVERSION-DORMANT-1 | 2026-04-24 gap audit 已正式合併 |
| ~~G-6 ML edge 噪音~~ | P1-7 B 已解 | 2026-04-19 ✅ |
| ~~2-11 actual training~~ | P1-7 C 同源 | 同一工作 |
| ~~FIX-02 Decision Lease Rust 接入~~ | 保留但降 P3（ExecutorAgent IPC 先做，Lease 次層）| 順序邏輯 |

---

## 三、Sub-agent 分角色關鍵 findings

### 3.1 PM+QA（Overall Dependency / Workflow）
**Top 5 現在就能做**：
1. EDGE-DIAG-1-FUP-SHADOW-ENABLED-IPC（~5 LoC + 1 test，0.5h）
2. STRATEGIST-HISTORY-OBSERVABILITY-1 GUI（backend `6faa3cb` live，待前端 tab）
3. STRATEGIST-PROMOTE-TRIGGER-1（API + IPC command，~1d）
4. bb_breakout_post_deadlock_fix 部署（`--rebuild` 後 healthcheck [12] 驗證）
5. TODO ↔ CLAUDE.md 同步規則文件化（避免敘述漂移）

**工作流程 5 問題**：
- A. TODO 與 CLAUDE.md 敘述不同步（edge_estimates 162 cells 即典型例）
- B. 被動等待 TODO 前置條件不明（如 LG-2/3 沒有具體定義）
- C. 重複 TODO 未合併（P1-19/10、FIX-01/ExecutorAgent）
- D. 決策 pending 無 decision maker 指派（P0-3 / EDGE-DIAG-1 Phase 3 strategy-scope）
- E. 跨平台測試邊界不清（Mac dev-only 不含 engine）

### 3.2 FA+PA（Edge / Financial / Performance）
**Top 3 現在就做**：
1. **P0 禁 phys_lock fallback + Grid disable 測試**（1d，每日減虧 $30+，確認 phys_lock 無用）
2. **P1 ma_crossover R:R 修復**（Option B 策略層 SL/TP 定制，3d，潛在 +10 bps 邊際改善）
3. **P1 PostOnly 滿 1 週 + fill rate 驗證**（7d，定量 maker vs taker 收益）

**核心判斷**：
- **Grid 無救**：gross −0.8 bps 結構性負，PostOnly 全部成功 net 仍 −1.8 bps/RT
- **ma_crossover 勝率 64% 但不對稱 2.54×**，問題在 trailing_distance 3.5% 過寬（ATR 1-1.5%）
- **phys_lock 在負 edge 環境設計上不可能有效**，等 edge 翻正才有意義
- **EDGE-DIAG-1 +11.95 bps 不值得興奮**：90% 來自 vacuum 污染，真實 signal 遠低預測

### 3.3 CC+QC（Code Reality Check）
**10 個 Claim 逐項驗證**：8 ✅ / 1 ⚠️ (Part B 行數誤差) / 1 ⚠️ (WS-RETIRE tests 數誤差) / 0 ❌

**關鍵發現**：
- FIX-26-DEADLOCK-1 expiry guard + saturating_add 對稱 + 7 regression tests ✅
- shadow_exit_writer.rs 存在 + ExitConfig.shadow_enabled default=false ✅
- passive_wait_healthcheck 12 checks 全在，[11]+[12] 都存在 ✅
- main_legacy.py 468 行 + 5 legacy_routes 1558 行 ✅ 符合 CLAUDE.md
- `layer2_tools.py 906 行` 超過 800 警告線（CLAUDE.md §九）

### 3.4 AIE（AI Layer / Agent）
**Top 3 優先級**：
1. **ExecutorAgent IPC→Rust 對接**（3-4d，5-Agent 閉環的最後一哩）
2. **Layer 2 升級規則量化 + 工具箱**（5-7d，`query_onchain/check_derivatives` + 自動 daemon）
3. **StrategistAgent promote API**（2-3d，scheduler 已有 method，缺 trigger）

**實作度**：
- H1-H5 middleware: 95-100%
- Layer 2 engine: 60%（框架完整，自主升級邏輯缺）
- 5-Agent 代碼: 80%（Executor 限 50%）
- ClaudeTeacher: 100% 代碼 / enabled=false 等啟用
- LinUCB: 代碼 1281 行完整實作，Phase 4 deferred
- **FIX-01 描述錯誤** — H1-H5 已 100%，真正缺 ExecutorAgent IPC

### 3.5 MIT（ML/DL Pipeline）
**Top 3 即時行動**：
1. **加速 label 累積**（1-2 週，3-5x rate via batch_limit 調整 + 多 slice 並行）
2. **dry-run ONNX E2E**（3-5d，用既有 demo 資料跑 full pipeline 驗證）
3. **healthcheck 覆蓋擴充**（2d，加 [13][14][15] label/edge/training freshness）

**資料層實情**：
- `edge_estimates.json` **僅 1 cell**（grid_trading::ORDIUSDT, shrunk_bps −45.73, n=3），mtime 2026-04-20 23:50 — **與 CLAUDE.md「162 cells + grand_mean −14.97 bps」嚴重不一致**，建議作為**新 P0 任務**調查 scheduler 為何停寫
- 最大 slice（grid BLURUSDT）47/200 labels，ETA 22 天
- model_registry table 空，shadow_exit_writer dormant
- Teacher/LinUCB/Bayesian/RL 全休眠

---

## 四、原 TODO 對照：所有項目去向

### 4.1 活躍項目對應表（原 ID → 新編號）

| 原 TODO 項 | 狀態 | 新編號 | 分類 |
|---|---|---|---|
| P0-2 LG-1 21d demo | 被動等待 | **W-1** | 觀察 |
| P0-3 Phase 5 edge 重評 | 決策 pending | **D-1** | 決策 |
| DUAL-TRACK-EXIT-1 Phase 1a/1b/2/3/4 | 多階段活躍 | **M-1** (主軸) | 活躍 |
| EDGE-DIAG-1 Phase 3 | 被動等待 | **W-2** | 觀察 |
| EDGE-DIAG-1-FUP-SHADOW-ENABLED-IPC | 現在就做 | **B-1** | 立即 |
| P1-6 DEMO-BYBIT-SYNC-ORPHAN | 被動等待 | **W-3** | 觀察 |
| P1-7 A/B ✅ + C | 半解+阻塞 | **M-2** | 活躍 |
| P1-10 STRATEGY-ASYMMETRY-1 | 邊際危機 | **E-1** | 活躍（Edge 軸）|
| P1-11 BB-BREAKOUT/REVERSION-DORMANT-1 | 待部署 | **D-2** | 部署 |
| P1-13 SAMPLE-FLOOR-GAP-1 | 守衛 | **M-2 sub** | 活躍 |
| P1-14 EDGE-ESTIMATE-BIND-BLOCKED-1 | 阻塞 | **E-1 sub** | 等 E-1 解 |
| STRATEGIST-HISTORY-OBSERVABILITY-1 GUI | 現在就做 | **B-2** | 立即 |
| STRATEGIST-PROMOTE-TRIGGER-1 | 現在就做 | **A-3** | 活躍（AI 軸）|
| STRATEGIST-AUTO-PROMOTE-CRITERIA-1 | Phase 5+ | **A-3 sub** | 活躍（延後）|
| STRATEGIST-TUNE-TARGET-CONFIG-1 | P3 | 歸 **backlog** | Backlog |
| STRATEGIST-PERSIST-AUDIT-GAP-COUNTER-1 | P2 | **D-3** | 部署 |
| STRATEGIST-PERSIST-INTEGRATION-TEST-1 | P3 | **backlog** | Backlog |
| LG-2 H0 Gate blocking | 條件等待 | **W-4** | 觀察 |
| LG-3 provider pricing | 條件等待 | **W-5** | 觀察 |
| LG-4/5 M/N 章 | W24 | **W-6** | 觀察 |
| G-4 Cookie secure=True | W24 | **X-1** | 長期 |
| G-7 ClaudeTeacher | W23 | **A-4** | 活躍（AI 軸）|
| G-10 Calibration.py | W23 | **M-3** | 活躍（ML 軸）|
| QoL-2 Demo AI cost GUI | 依賴 G-1 H1-H5 | **A-5** | 活躍（AI 軸）|
| DUST-EVICTION GUI | P1-8 FUP | **X-2** | 長期 |
| LEARNING-COCKPIT-NO-IPC-1 | 設計債 | **X-3** | 長期 |
| EDGE-P2-2 Phase B Liquidation | 待 A 驗 | **E-2 sub** | Edge 軸延後 |
| EDGE-P2-3 Phase 2+ (c) live endpoint | 待 demo 1w | **E-3** | 活躍（Edge 軸）|
| ORPHAN-ADOPT-1 Phase 2B | 前置 G-1 R-02 | **A-6** | 活躍（AI 軸）|
| G-2 FundingArb 三參數重評 | 前置 G-1 R-02 | **A-6 sub** | 活躍（AI 軸）|
| Phase 5 補強 DL-1/DL-2 etc. | 等 D-1 判決 | **M-4** | 活躍（ML 軸）|
| E5-P1-5-FUP / E5-P2-4c bb_reversion | 邊緣拆分 | **X-4** | 長期 |
| E5-FN-2-PLAN-N-FUP (a)(c) | 部署後 | **X-5** | 長期 |
| IP-DEDUP-1 | 觸發後 | **backlog** | Backlog |
| WP-F GUI / WP-E4 / WP-E5 / WP-I | 長尾 | **backlog** | Backlog |
| 2-11 actual training | 併入 P1-7 C = M-2 | 併 | 併入 |
| 4-06 LinUCB live warm-start | Phase 5+ | **backlog** | Backlog |
| OC-4 MCP PostgreSQL | 長期 | **backlog** | Backlog |
| G-8 cost_gate 可信度 | EDGE-P3-1 後 | **backlog** | Backlog |
| Phase 4-Conditional 4-1~4-10 | 觸發後 | **backlog** | Backlog |
| RUST-DOUBLE-PREFIX-1 | runtime 待 rebuild | **D-4** | 部署 |
| STRATEGIST-SCHED-CHANNEL-PAPER-ORPHAN-1 | runtime 待 rebuild | **D-5** | 部署 |
| RESTART-ALL-UVICORN-LOG-1 | runtime 待 rebuild | **D-6** | 部署 |
| EDGE-SCHEDULER-LEADER-1 | runtime 待 rebuild | **D-7** | 部署 |
| SCHEDULER-FAILURE-OBSERVABILITY-1 | runtime 待 rebuild | **D-8** | 部署 |
| RAISE: **EDGE-ESTIMATES-STALE-1** | ← 新發現 | **E-0** | 新增 P0 |

### 4.2 已歸檔確認（歸檔不再列活躍）

| 歸檔項 | 歸檔日期 | 歸檔位置 |
|---|---|---|
| P0-13 ATR-SCALE-BUG-1 / P0-14 EDGE-ESTIMATES-MISS-1 / P0-15 COST-EDGE-DEPRECATION | 2026-04-24 | `docs/archive/2026-04-24--completed_todo_batch.md` |
| 2026-04-21 批次 14 項 | 2026-04-21 | `docs/archive/2026-04-21--completed_todo_batch.md` |
| 2026-04-20 批次 14 項 | 2026-04-20 | `docs/archive/2026-04-20--completed_todo_batch.md` |
| Step 0 衍生新 TODO 5/5 | 2026-04-22 | `docs/archive/2026-04-22--step_0_derived_todo_batch.md` |
| P1-19 BACKFILL-LABELS-STALLED-1 (duplicate P1-10) | 結案 2026-04-22 | RCA `docs/worklogs/2026-04-22--backfill_labels_stalled_rca.md` |
| P1-12 BB-REVERSION-BLOCKED-1 | 2026-04-24 結案併入 P1-11 | — |
| G-2 v2 NEGATIVE | 2026-04-18 結案 | `memory/project_g2_funding_arb_monitor.md` |

---

## 五、新 TODO 編號體系（單一字母 + 數字）

```
E-*  Edge 軸（現行最危急，策略邊際/fee/結構）
A-*  AI / Agent 軸（多 Agent 閉環 / Layer 2 自主）
M-*  ML / DL 軸（資料累積 / 訓練 / registry）
D-*  部署軸（待 --rebuild 已 push 項）
B-*  立即可做軸（低成本 quick win）
W-*  被動觀察軸（時間/條件 gated）
X-*  長期工程債軸（非當週）
backlog  長尾/條件觸發
```

**順序建議**：先 **D-系列**（一次 `--rebuild` 全部生效）→ 接 **E-0 + E-1 + A-1**（現在最急）→ **B-系列** 穿插（1-2 天低成本 quick win）→ **A-2 / M-2 加速**（2 週內 ML 首 ONNX + 5-Agent 閉環）→ **W-系列** 背景監控 → **E-3 / E-1 結論** → **D-1 Phase 5 重評** → **M-系列後續** / Live Gate。

---

## 六、8 角色交叉驗證矩陣

| Finding | PM | QA | FA | PA | CC | QC | AIE | MIT |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| 策略 gross edge 結構性負 | ✓ | — | **✓✓** | **✓✓** | — | — | — | ✓ |
| Grid disable 建議 | ✓ | — | **✓✓** | ✓ | — | — | — | — |
| ExecutorAgent IPC 未接線 | ✓ | ✓ | — | — | ✓ | ✓ | **✓✓** | ✓ |
| edge_estimates.json stale 1 cell | **✓✓** | ✓ | — | — | — | ✓ | — | **✓✓** |
| Layer 2 升級規則缺 | ✓ | — | — | — | — | — | **✓✓** | — |
| H1-H5 非 stub 已 100% | ✓ | ✓ | — | — | ✓ | ✓ | **✓✓** | — |
| Track P v2 已部署 | ✓ | — | ✓ | — | **✓✓** | ✓ | — | — |
| `layer2_tools.py` 超 800 行 | — | — | — | — | **✓✓** | ✓ | ✓ | — |
| TODO/CLAUDE.md 敘述漂移 | **✓✓** | **✓✓** | — | — | ✓ | ✓ | ✓ | ✓ |
| ONNX 首 artifact 未產 | ✓ | — | — | — | — | — | — | **✓✓** |
| Teacher/LinUCB/Bayesian/RL dormant | — | — | — | — | — | — | ✓ | **✓✓** |
| PostOnly 救不了負 edge | — | — | **✓✓** | **✓✓** | — | — | — | — |

`✓✓` = 該角色深度揭露 / `✓` = 該角色次要佐證 / `—` = 該角色無直接結論

---

## 七、8 角色建議排序（現在最該做的事）

經 8 角色獨立建議去重 + 優先級統一：

| # | 項 | 軸 | 理由 | 工期 |
|---|---|---|---|---|
| **1** | **E-0 edge_estimates.json RCA** | Edge/ML | 3+ 天停寫 + 僅 1 cell 是 scheduler 故障或 DB schema 問題，需診斷 | 0.5-1d |
| **2** | **D-(1..8) `--rebuild` 統一部署** | Deploy | 6-8 個 commit 全 push 未部署 + FIX-26-DEADLOCK-1 關鍵；一次 rebuild 解多 | 2h |
| **3** | **E-1 Grid disable + ma_crossover SL/TP 修復** | Edge | FA/PA 結論 Grid 無救；ma_crossover R:R 修復潛在 +10 bps | 3-5d |
| **4** | **B-1 EDGE-DIAG-1-FUP-SHADOW-ENABLED-IPC** | 基礎設施 | ~5 LoC + 1 test，Phase 2 shadow 啟動前置 | 0.5h |
| **5** | **A-1 ExecutorAgent→Rust IPC 接線** | AI | 5-Agent 閉環最後一哩，FIX-01 實際應指向此 | 3-4d |
| **6** | **M-1 加速 label 累積（10x rate）** | ML | 當前 ETA 22 天不可接受，需 1-2 週加速 | 1-2d 實作 + 等自然 |
| **7** | **A-2 Layer 2 升級規則 + 工具箱** | AI | Layer 2 框架 ✅ 缺量化規則 + query_onchain/check_derivatives | 5-7d |
| **8** | **M-2 dry-run ONNX E2E** | ML | 用既有資料驗證 6 stages 管線，預見 schema/precision 問題 | 2-3d |
| **9** | **B-2 STRATEGIST-HISTORY GUI** | 基礎設施 | Backend ✅，GUI 待補 | 2-3h |
| **10** | **B-3 STRATEGIST-PROMOTE-TRIGGER API** | AI | scheduler method ✅，API/IPC 待補 | 1d |

**長期（~W25+）**：A-3 自動 promote / A-4 Teacher 啟用 / M-3 Calibration / M-4 Phase 5 DL-1/2/Regime LSTM

---

## 八、新 TODO 設計原則（避免重蹈亂局）

1. **單一字母 + 數字編號體系**：`E-1 / A-1 / M-1 / D-1 / B-1 / W-1 / X-1 / backlog`
2. **每項含指針回本 audit**：`docs/audits/2026-04-24--todo_refactor_audit.md §X`
3. **現行 `--rebuild` / `commit` / `push` 狀態明示**：避免「commit=完成」混淆
4. **被動等待必附 healthcheck id**：違 CLAUDE.md §七 「被動等待必附 check」則打回
5. **軸內項目依賴箭頭**：單一 chunk 內前置關係清楚
6. **每週維護**：每週一 sprint 起頭 15min audit pass，把新發現補入對應軸

---

## 九、歸檔動作（本 audit 同 commit 執行）

- [x] 原 TODO.md 700 行完整快照 → `docs/archive/2026-04-24--todo_snapshot_pre_refactor.md`
- [x] 本 audit 寫入 `docs/audits/2026-04-24--todo_refactor_audit.md`
- [x] 新 TODO.md 生成（~200-300 行，大幅瘦身）
- [x] README.md §當前狀態 更新（edge_estimates stale + Phase 5 仍 PAUSED + Live_Ready 狀態）
- [x] CLAUDE.md §三 更新（edge_estimates 162 cells claim 更正 → 1 cell / stale）
- [x] memory 新增 `project_edge_estimates_stale_rca.md`（RCA pending）
- [x] memory 新增 `project_executor_agent_ipc_gap.md`（Gap A 真相）
- [x] memory 新增 `project_strategy_edge_structural_negative.md`（FA 結論：Grid 無救）
- [x] MEMORY.md index 加 3 行
- [x] commit + push（單次，含所有 meta-doc 改動）

---

**本 audit 狀態：COMPLETE — 用於驅動新 TODO.md 重構 + 隨附 commit**
**生效日期：2026-04-24**
**下輪回顧：下次 weekly sprint 起頭（~2026-05-01）**
