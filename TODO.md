# OpenClaw TODO — 工作清單（v3 · 單一時間軸版）

**最後更新**：2026-04-24 CEST
**版本**：v3（Wave 線性版；廢除雙軌 P0-P4 章節，P0/P1/P2 降為每項 tag）
**舊版歸檔**：v2 `docs/archive/2026-04-24--todo_v2_dual_axis_snapshot.md`（458 行，Wave+P 雙軌）· v1 `docs/archive/2026-04-24--todo_v1_refactor_snapshot.md`（328 行）· v0 `docs/archive/2026-04-24--todo_snapshot_pre_refactor.md`（700 行）
**簽核**：PM Approved FIX-PLAN v2 → [Sign-off](docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-24--FixPlan_v2_PMApproval.md)
**基礎方案**：[FIX-PLAN v2](docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-24--4.24TodoAudit_FixPlan_v2.md) · [10-Agent audit 索引](docs/audits/2026-04-24--todo_refactor_audit.md)

**Engine**：PID 884467 · mtime 2026-04-24 02:06 · HEAD `1a53400`（待 `--rebuild` 帶 P1-11 FIX-26）
**測試**：engine lib 1980 / 0 fail · pytest 2996
**21d demo 時鐘**：起算 2026-04-16 22:16 → 解鎖 2026-05-07

---

## 🎯 此刻該做什麼（2026-04-24，Wave 1 第 1 天）

**本週 Top 3**（按順序）：

1. **🔴 G1-01** `edge_estimator_scheduler` 恢復 — **Linux 2h 診斷 + 1d 修復**
   - 4 天停滯（edge_estimates.json 僅 1 cell），阻塞 G4 ML / P0-3 邊評 / EDGE-DIAG Phase 3
   - 負責：MIT+E4 / 驗 E2
   - 先做：ssh trade-core 查 scheduler 進程 + flock sentinel + log

2. **🔴 G1-02** `event_consumer/mod.rs` fn 拆分（1696 行 → <1200） — **4-5d**
   - 阻塞 G3 (AI 接線) + G5 (refactor) — Wave 1 主體工時
   - 負責：E1+PA 同 session 緊密 / 驗 E2

3. **✅ G1-05** PostOnly 配置驗證 — **完成 2026-04-24**
   - FA 初審誤判 demo/live 反向；PA + 本次 FA+E1 sub-agent 核實 `strategy_params_{demo,live,paper}.toml` `use_maker_entry` 配置正確（demo/paper=true, live=false 符合原則 #6）
   - FA v1 誤判根因：抓錯欄位（`risk_config.post_only_limit` 是 declared-but-unread GUI 偏好旗，非策略熱路徑）
   - Design intent doc：[`docs/references/2026-04-24--postonly_design_intent.md`](docs/references/2026-04-24--postonly_design_intent.md)
   - 負責：FA+E1 / 驗 E2

**並行可派 sub-agent**：G6-01 healthcheck 補齊（E1/QA，1-2d）· FA L1 / L2 proposal 清算（獨立軌道）

---

## 🔗 依賴關係圖

```
Wave 1（W17/18 · 4/24→5/08）              Wave 2（W19 · 5/08→5/22）            Wave 3（W20-W23 · 5/22→6/12）         Wave 4（W23-W24 · 6/12→6/23）
─────────────────────────────            ────────────────────────            ─────────────────────────────       ──────────────────────────
G1-01 scheduler ──┐                       G3-01 RFC ──→ G3-02 toggle ──┐       EDGE-DIAG Phase 3 ──┐               P0-3 邊評決策 ──┐
                  ├── G4 labels           G3-03 Rust IPC ─────────────┤      Phase 1b exit_features┤               LG-2 H0 block ──┤
G1-02 fn 拆 ──────┼── G3 AI 接線 ──→     G3-04 e2e test ─────────────┤      G2-01 PostOnly 驗（背景→驗）┤         LG-3 pricing ───┤───→ Live
                  ├── G5 main.rs 拆       G4-01 labels 加速 ──→ G4-02 first ONNX ──→ G4-03 canary  ┤               LG-4 supervised┤
G1-05 PostOnly ───┘                       G5-01~06 refactor （並行）                  Phase 2 shadow flip          LG-5 autonomous ─┘
                                          G7 量化（Kelly/EWMA/Hurst/CUSUM）
G6-01~04 healthcheck + Guard              G8 e2e + healthcheck [13-15]                G9 Bybit API 精進（並行）

背景線程（貫穿 Wave 1-4）
──────────────────────
P0-2 21d demo（→ 5/07 解鎖） · PostOnly 1-2w 驗（→ 5/07-08 出結果） · Labels 累積（→ 需 200 pooled）
P1-8 DUST log-only 觀察（04-17 起算）· exit_features 累積 ≥1w（04-26 滿）· BB rebuild 觀察（待 operator）
```

**關鍵判讀**：
- Wave 1 必須先完成 G1-01/02/05（P0 三項），G6 並行
- Wave 2 **取決於 G1-02 拆完**（event_consumer 不拆則 G3 Rust handler 加不進）
- Wave 3 Phase 3 **取決於 healthcheck [11] 連續 3d PASS**（被動等待）
- Wave 4 **取決於 P0-2 21d 解鎖 + P0-3 決策會**（事件驅動，非 hard date）

**compact 拆 session 建議**：
- Session A（Wave 1）：G1-01 + G1-05 + G6-01 並行（短 session OK）
- Session B（Wave 1 核心）：G1-02 event_consumer 拆 — **PA+E1 同 session 緊密**（不可拆）
- Session C（Wave 1 末）：G5 refactor 起步 — 可派 2-3 subagent 並行
- Session D（Wave 2）：G3 RFC + 實裝 — PA+E1+E2 鏈
- Session E（Wave 2）：G7 量化 + G4 ML — 獨立軌道
- Session F+（Wave 3-4）：被動觀察 + 決策會

---

## 🕐 接手三連檢查

```bash
# 1. git 狀態 + 領先/落後
git status && git log --oneline -5
git fetch --prune origin && git pull --ff-only origin main 2>/dev/null || echo "divergent, manual fix"

# 2. engine 存活（Mac 透過 ssh）
ssh trade-core "python3 helper_scripts/canary/engine_watchdog.py --data-dir /tmp/openclaw --status"

# 3. healthcheck 一眼看（CLAUDE.md §七 強制）
ssh trade-core "cd ~/BybitOpenClaw/srv && python3 helper_scripts/db/passive_wait_healthcheck.py"

# 若 engine 掛：ssh trade-core "bash helper_scripts/restart_all.sh --rebuild"
```

---

## 🗺️ Wave 時序 + 里程碑

| Wave | 週次 | 日期 | 主軸 | 結束標準 | 狀態 |
|---|---|---|---|---|---|
| **W1** | W17/18 | **4/24→5/08** | G1 edge infra + G6 healthcheck | scheduler live + event_consumer <1200 行 | 🟡 **進行中** |
| **W2** | W19 | 5/08→5/22 | G3 AI 接線 + G5 refactor + G4 ML + G7 量化 | Executor shadow→live + 首個 ONNX + 8 檔 <1200 | ⬜ |
| **W3** | W20-W23 | 5/22→6/12 | EDGE-DIAG Phase 3 + Phase 1b + G2 策略驗 + G8 test | clean n≥200 + shadow agreement ≥95% | ⬜ |
| **W4** | W23-W24 | 6/12→6/23 | P0-3 決策 + LG-2/3/4/5 + G9 Bybit | Live Gate 全綠 | ⬜ |

**Live 最早**：~2026-05-30 中位 / ~2026-05-23 樂觀 / ~2026-06-15 悲觀 / **對外 ~2026-06-01**（PM +10% 緩衝）

---

## ⏩ Wave 1（W17/18 · 4/24→5/08）— 基礎設施解凍【✅ 全部完成】

**狀態（2026-04-24 Mac CC G1-02 接手完成 Step 1+3 後）**：9/9 項完成 ✅；G1-02 Step 1 + Step 3 完成（branch `g1-02-event-consumer-split` 3 commits：`0155c9a` Step 1 / `4635669` docs / `96f9f92` Step 3；Mac + Linux release 1990 passed）；Step 2 loop_handlers 可選精進（mod.rs 1009→~450 理想），無阻塞 Wave 2；**前 9 commit 已 ff-merge 到 main HEAD `f4e7826`**，feature branch 3 commits 待 operator ff-merge。

### G1 Edge 危機根源修復

| ID | Tag | 項目 | 前置 | 負責修/驗 | 工時 | 完成標準 |
|---|---|---|---|---|---|---|
| **G1-01** | ✅完成 | `edge_estimator_scheduler` 診斷 + 恢復 — operator commit `f32629c` (leader election) + `abc85c0` (graceful shutdown) 已修；2026-04-24 02:06 `--rebuild` 部署；現 cells **59** / mtime <30min | 無 | MIT+E4 / E2 | 完成 2026-04-24 | [G1-01 report](.claude_reports/20260424_122700_g1_01_scheduler_recovery.md) |
| **G1-02** | ✅完成 | `event_consumer/mod.rs` 拆（硬上限 1200）— **Step 1 `pending_sweep` ✅ + Step 3 `bootstrap` ✅ 完成；mod.rs 1762→1009（<1200 ✅）；Mac + Linux release 1990 / 0 failed 雙驗**。Step 2 `loop_handlers`（5 arm 抽，~450 行理想）可選精進，無阻塞 Wave 2 | 無 | E1+PA / E2 | 完成 2026-04-24 | <1200 行 ✅ + test cov ≥95% ✅ + engine lib pass ✅ / [PA plan Step 1-3](docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-24--g1_02_event_consumer_split_plan.md) + [Step 2 detail plan](docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-24--g1_02_step2_loop_handlers_detail_plan.md) + [Step 1 report](.claude_reports/20260424_130953_g1_02_step1_pending_sweep_split.md) + [Step 3 report](.claude_reports/20260424_133541_g1_02_step3_bootstrap_extracted.md)（branch `g1-02-event-consumer-split` commits `0155c9a` + `4635669` + `96f9f92`）|
| **G1-03** | 🟡2/7 完成 | Rust 硬違反 7 檔 refactor — **resting_orders.rs 1367→659 ✅ commit `224699e`** (subagent B, tests 搬 sibling) + **risk_config.rs 1328→908 ✅ commit `e2317ae`** (主 session, advanced sub-configs 抽 sibling)；剩 5 檔：startup 1377 (subagent A 進行中) / main 2062 / instrument_info 1975 / bybit_rest_client 1725 / order_manager 1554。Mac + Linux release 1990/0 failed 雙驗 | G1-02 | E5+E1 / E2+E4 | 部分完成 2026-04-24 / 剩 1-2d | all rust files <1200 lines |
| **G1-04** | 🟠P1 | fee drag / R:R 邊際驗證基線 | PostOnly demo | QC / FA | 1-2d | counterfactual baseline report |
| **G1-05** | ✅完成 | PostOnly 配置驗證 — `use_maker_entry` 配置正確（demo/paper=true, live=false）；FA v1 誤判收回 | 無 | FA+E1 / E2 | 完成 2026-04-24 | [design intent doc](docs/references/2026-04-24--postonly_design_intent.md)（commit `0da10c0`）|
| **G1-06** | ✅完成 | Drawdown auto-revoke 實裝（原則 #5/#6）— `drawdown_revoke.rs` 343 行 + Step 6 HaltSession 接線 + 10 unit tests；engine lib **1990 / 0 failed**（baseline 1980 + 10 新）| 無 | E1 / E2 | 完成 2026-04-24 | [G1-06 report](.claude_reports/20260424_103617_g1_06_drawdown_revoke.md)（commit `d1cdd49`）|

### G6 合規 + 觀察性

| ID | Tag | 項目 | 前置 | 負責修/驗 | 工時 | 完成標準 |
|---|---|---|---|---|---|---|
| **G6-01** | ✅完成 | `passive_wait_healthcheck.py` 補齊 5 QA 缺陷 + FUP `[Xb] pipeline_triangulation` cross-validation；Linux 14 check 全執行無 stack trace | 無 | E1 / QA | 完成 2026-04-24 | [G6-01 report](.claude_reports/20260424_123625_g6_01_healthcheck_fixes.md)（commits `1cf7ad9` + `9120af7`）|
| **G6-02** | ✅完成 | healthcheck [13-15] 新增 — edge_fresh + exit_feat_rate + shadow_agree | G6-01 | PM+E1 / QA | 完成 2026-04-24 | commit `a0a4981` |
| **G6-03** | 🟡部分 | V019/V020 retrofit Guard A — **部署時 sqlx checksum mismatch crash engine，已 revert (`55ed449`)**；`test_schema_guards.sql` 9/9 + TEST 10/11/12 fixtures 保留；V023/V021 既有 Guard A 未動。Guard A 重做為 V024 純新增 migration 留 E1 下次 session | 無 | E1+E2 | 部分完成 2026-04-24 | [G6-03 report](.claude_reports/20260424_123200_g6_03_v019_v020_guard.md)（commits `ff5bf1f` + `309d5b1` + revert `55ed449`）|
| **G6-04** | ✅完成 | CLAUDE.md §三 敘述同步規則（TODO vs runtime） — `docs/lessons.md:30` 條目 + `CLAUDE.md §七「§三 敘述 vs runtime drift 防線」` 規則已收錄 | 無 | TW | 完成 2026-04-24 | [lessons.md:30](docs/lessons.md) + CLAUDE.md §七（commit `d60ad45`）|

### Wave 1 完成標準（Go / No-Go）

- [x] G1-01 scheduler n_cells ≥50（cells **59** / mtime <30min）— healthcheck [13] PASS 待連 3 日累積
- [x] G1-02 event_consumer <1200 行 + engine lib 1980+ pass — **Step 1 + Step 3 完成（mod.rs 1762→1009 ✅ <1200，Mac + Linux release 1990/0 failed）**；Step 2 loop_handlers 可選精進，無阻塞
- [x] G1-05 PostOnly design intent doc 存檔（修正 FA v1 誤判）— `docs/references/2026-04-24--postonly_design_intent.md`（2026-04-24）
- [x] G6-01+02 所有被動等待項附 healthcheck — 5 缺陷修 + [Xb] FUP + [13-15] 新增；6h cron 待 operator 設
- [x] G6-04 CLAUDE.md §三 drift 規則已登 `docs/lessons.md:30` + §七（2026-04-24）
- [ ] 背景：P0-2 時鐘未重置、PostOnly 驗收資料累積中

### Wave 1 收尾通知（給 operator）

**所有 G6 + G1（除 G1-02 E1 實裝）已完成 + main 已含全部 commit**（feature branch `g1-06-drawdown-auto-revoke` 可清理）：

| Commit | 任務 |
|---|---|
| `040a02a` | Wave 1 收尾 TODO 更新 |
| `a0a4981` | G6-02 [13-15] new checks |
| `309d5b1` | G6-03 FUP test fixtures |
| `9120af7` | G6-01 FUP [Xb] cross-validation |
| `7908164` | G1-02 PA plan |
| `1cf7ad9` | G6-01 healthcheck 5 fix |
| `d1cdd49` | G1-06 drawdown auto-revoke |
| `0da10c0` | G1-05 PostOnly doc |
| `ff5bf1f` | G6-03 V019/V020 Guard A |
| `d60ad45` | G6-04 §三 drift rule |

**Operator 下一步**：
1. ~~merge feature branch → main~~ ✅ 已完成（ff-merge + push 到 origin/main `040a02a`）
2. ~~ssh deploy~~ ✅ 已完成 — engine PID `1099327` / binary mtime 2026-04-24 12:52 / paper+demo alive / total_ticks 5000+ / cost_gate normal warmup（**G6-03 V019/V020 retrofit 撤回**因 sqlx checksum mismatch；engine 第一次 rebuild 啟動失敗 → revert `55ed449` → 第二次啟動成功）
3. 設 6h cron `passive_wait_healthcheck.py`（CLAUDE.md §七 強制）
4. （可選）清理 feature branch：`git branch -D g1-06-drawdown-auto-revoke && git push origin --delete g1-06-drawdown-auto-revoke fix/g6-01-healthcheck-5-defects`
5. **下一 session**：(a) G1-02 Step 2+3 E1 實裝（3-5h；bootstrap 優先更機械，或按 PA plan 原序 loop_handlers→bootstrap；詳 [Step 1 report §4/§5](.claude_reports/20260424_130953_g1_02_step1_pending_sweep_split.md)）(b) G6-03 重做為 V024 純新增 migration（避免 sqlx checksum trap）

6. ⚠️ **engine 停擺診斷（新發現 2026-04-24 13:00 UTC）**：Mac CC 接手 G1-02 時 ssh trade-core 實測 `pgrep openclaw_engine` = 0 process + `rust/target/release/openclaw_engine` 不存在（本 TODO §三 line 156 敘述的 PID `1099327` / binary 12:52 已過期）；watchdog 回 `engine_alive: false`（paper 2.6h / demo 2.5min / live 5d stale）。uvicorn 4 workers 仍 alive（PID `1095536`），所以 scheduler + healthcheck 繼續工作但 trading engine 不 tick。可能原因：(a) operator 手動 `cargo clean` 準備 rebuild (b) engine crash 未留 maintenance.flag (c) 別的 session 意外 kill。**Operator 確認並 `--rebuild` 恢復**（可同步帶入 G1-02 Step 1 + 先前 pending P1-11 FIX-26-DEADLOCK-1）

---

## ⏩ Wave 2（W19 · 5/08→5/22）— AI 接線 + 架構合規

### G3 AI 多 Agent 接線（5-Agent → Rust 補全）

| ID | Tag | 項目 | 前置 | 負責修/驗 | 工時 | 完成標準 |
|---|---|---|---|---|---|---|
| **G3-01** | 🔴P0 | ExecutorAgent ConfigStore + IPC RFC 設計 | G1-02 | PA / E2 | 1d | RFC doc + PA 簽核 |
| **G3-02** | 🔴P0 | ExecutorAgent shadow→live toggle 實裝（IPC `patch_executor_config`） | G3-01 | E1+PA / E2+E4 | 2-3d | e2e test shadow→live + Rust receive |
| **G3-03** | 🔴P0 | Rust `intent_processor` IPC handler（接 Python SubmitOrder） | G3-02 | E1 / E2+E4 | 2d | Rust can receive Python intent IPC |
| **G3-04** | 🟠P1 | ExecutorAgent shadow→live e2e 整合測試 | G3-03 | E4 / QA | 2d | QA 端到端驗證 pass |
| **G3-05** | 🟡P2 | EDGE-DIAG-1-FUP-SHADOW-ENABLED-IPC（升 P2） | 無 | E1+E2 | 1d | `shadow_enabled` hot-reload works |
| **G3-06** | 🟡P2 | Layer 2 autonomous 升級規則（L0→L1→L2 criteria） | G3-02 | AI-E+PA / E2 | 2-3d | 量化升級觸發條件 code |
| **G3-07** | 🟡P3 | Layer 2 工具箱補全（query_onchain / check_derivatives） | G3-06 | E1 | 2-3d | tool unit + e2e |
| **G3-08** | 🟡P3 | H1-H5 → Rust IPC Gateway | G3-03 | E1+PA / E2 | 3-5d | Rust query H1-H5 state |
| **G3-09** | 🟡P3 | `cost_edge_ratio` 原則 #13 演算法 | G3-08 | AI-E+E1 / E2 | 2d | cost_gate active when ratio ≥0.8 |
| **G3-10** | 🟡P2 | STRATEGIST-PROMOTE-TRIGGER-1（手動 API + IPC） | G3-02 | E1+E2 | 1d | POST /api/v1/strategist/promote |

### G4 ML 管線解凍

| ID | Tag | 項目 | 前置 | 負責修/驗 | 工時 | 完成標準 |
|---|---|---|---|---|---|---|
| **G4-01** | 🟠P1 | Labels pooled 加速（per-strategy pool） | `PipelineConfig.symbol` Optional commit | MIT+E1 / E2 | 1-2d | labels ≥200 pooled |
| **G4-02** | 🟠P1 | `run_training_pipeline.py` 首跑 grid_trading | G4-01 | MIT / E4 | 4h | 首個 ONNX artifact + registry row |
| **G4-03** | 🟡P2 | model_registry canary rules + auto-promote draft | G4-02 | E1+E2 | 2d | `/api/v1/ml/model_promote` route live |
| **G4-04** | 🟡P2 | edge_estimator_scheduler healthcheck [13] | G1-01 | E1 / QA | 0.5d | cron 每 1h check mtime |
| **G4-05** | 🟡P2 | `ExitConfig.shadow_enabled` flip ON + 24h 觀察 | G3-05 | PM+MIT / QA | passive 24h | healthcheck [8] decision_shadow_exits 有 row |

### G5 架構 / 可讀性債務（可派 3+ subagent 並行）

| ID | Tag | 項目 | 前置 | 負責修/驗 | 工時 | 完成標準 |
|---|---|---|---|---|---|---|
| **G5-01** | 🟠P1 | `main.rs` 2062 行拆分 | 無 | E5+E1 / E2 | 2-3d | <1200 lines |
| **G5-02** | 🟠P1 | `live_session_routes.py` 1449 行拆 | 無 | E5+E1 / E2 | 1-2d | <1200 lines |
| **G5-03** | 🟠P1 | `instrument_info.rs` 1975 行拆 | 無 | E5+E1 / E2 | 1-2d | <1200 lines |
| **G5-04** | 🟡P2 | `ai_service.py` 1258 行拆 | 無 | E5+E1 / E2 | 1d | <1200 lines |
| **G5-05** | 🟡P3 | `bb_reversion.rs` 1143 行 sibling 拆 | 無 | E5 | 1h | <1200 lines |
| **G5-06** | 🟡P2 | 其他 5 檔（bybit_rest_client / order_manager / startup / resting_orders / risk_config） | 無 | E5+E1 / E2+E4 | 5-8d 全部 | all <1200 |

### G7 量化 / 統計方法論（新增，from QC）

| ID | Tag | 項目 | 前置 | 負責修/驗 | 工時 | 完成標準 |
|---|---|---|---|---|---|---|
| **G7-01** | 🟠P1 | Kelly 分級 tier boundaries 參數化（50/200 dividers TOML） | 無 | QC+E1 / FA | 1d | TOML config 生效 |
| **G7-02** | 🟠P1 | EWMA Vol lambda 參數化（per-timeframe） | 無 | QC+E1 | 0.5d | λ configurable |
| **G7-03** | 🟠P1 | Hurst + Hysteresis 整合（6-period lag） | 無 | QC / FA+MIT | 2-3d | R/S analysis live |
| **G7-04** | 🟠P1 | CUSUM 策略衰減監控 | 無 | QC+E1 | 1-2d | σ-based slack/threshold |
| **G7-05** | 🟠P1 | cost_gate grand_mean bind condition | G1-01 | QC+E1 / FA | 2-3h | bind when grand_mean > -50 bps ∧ ≥2 strategies shrunk>0 |
| **G7-06** | 🟡P2 | Grid OU σ residual-based 修正 | 無 | QC / E1+E2 | 1d | σ = sqrt(Σ(Δx-mean)²/n) |
| **G7-07** | 🟡P2 | Slippage / confluence 硬編碼清理 → TOML | 無 | QC+E1 / FA | 2-3d | 8 檔硬編碼移除 |

### Wave 2 完成標準

- [ ] G3-01~04 ExecutorAgent shadow→live e2e pass
- [ ] G4-02 第一個 ONNX artifact 進 registry
- [ ] G5-01~06 所有 Rust / Python 檔 <1200 行
- [ ] G7 量化配置化完成

---

## ⏩ Wave 3（W20-W23 · 5/22→6/12）— Edge 穩定 + ML canary

### EDGE-DIAG-1 Phase 3 部署 + Phase 1b（前置條件嚴格）

| ID | Tag | 項目 | 前置條件（必須 ALL 滿足） | 負責 | 工時 |
|---|---|---|---|---|---|
| **EDGE-P3** | 🟡P1 | strategy-scoped Gate 1 fallback 部署 | (a) clean bucket ≥200 rows pooled · (b) per-strategy bootstrap 95% CI lo >0 · (c) orphan_frozen clean ≥20 rows · **(d) healthcheck [11] 連 3d PASS** | PM+FA+QC / E2 | 2d |
| **EDGE-P1b** | 🟡P1 | `exit_features` 累積 ≥1w + 7 維閾值 bind | W19 起算，預計 5/03 滿週 | PM+QC / E4 | passive 7d |
| **EDGE-P2-flip** | 🟡P2 | Track L shadow flip + P1-10 並行 | EDGE-P1b | QC+PM / E2 | passive 7d |

### G2 策略驗證 + 決策

| ID | Tag | 項目 | 前置 | 負責 | 工時 |
|---|---|---|---|---|---|
| **G2-01** | 🟠P1 | P1-10 PostOnly 1-2w 驗證（passive） | PostOnly demo 04-21 部署 | PM+QC+FA / E4 | passive ≥1w（04-21~05-07 出結果）|
| **G2-02** | 🟠P1 | ma_crossover R:R 對稱性 counterfactual | EDGE-P2 結果 | QC+FA / E2 | 2-3d |
| **G2-03** | 🟡P2 | ma_crossover SL/TP 策略層定制（Option B） | G2-02 驗收 | E1+FA / E2+E4 | 2-3d |
| **G2-04** | 🔴P0 | **Grid disable 決策會**（若 PostOnly 後仍負 edge） | G2-01 + P0-3 輸入 | PM+FA 決策 | 1h 會議 |
| **G2-05** | 🟠P1 | bb_breakout FIX-26-DEADLOCK-1 rebuild 驗證 | operator rebuild | MIT / QA [12] | 6h+ 觀察 |

### G8 測試 / Healthcheck 擴展（新增，QA+AI-E）

| ID | Tag | 項目 | 前置 | 負責 | 工時 |
|---|---|---|---|---|---|
| **G8-01** | 🟠P1 | e2e 認知自適應測試（80+ coverage） | G3-04 | QA+E4 / E2 | 2-3d |
| **G8-02** | 🟠P1 | Python↔Rust parity test（decision agree ≥95%） | G3-03 | QA+E4 / E2 | 1-2d |
| **G8-03** | 🟠P1 | 灰度驗收自動化（shadow metrics） | EDGE-P2 flip | QA / E2 | 2-3d |
| **G8-04** | 🟡P2 | healthcheck DAG 線性化（依賴清晰） | G6-02 | QA | 1d |
| **G8-05** | 🟡P2 | AI cost ROI 監控面板（from AI-E） | G3-09 | AI-E+E1a / QA | 1-2d |

### Wave 3 完成標準

- [ ] EDGE-P3 前 4 條件全滿足，Gate 1 fallback 部署
- [ ] exit_features ≥1000 rows
- [ ] G2-01 PostOnly 驗收：fee drop ≥60% 或決策策略下架
- [ ] G2-02 ma R:R ≤1.5× 或 SL/TP Option B 定制
- [ ] bb_breakout 復活（fill count > 0）或正式 disable

---

## ⏩ Wave 4（W23-W24 · 6/12→6/23）— Live Gate + P0-3 決策

### P0-3 Phase 5 Edge 重評（決策點）

| ID | Tag | 項目 | 前置 | 負責 | 工時 |
|---|---|---|---|---|---|
| **P0-3-01** | 🔴P0 | counterfactual_exit_replay 完整分析報告 | Phase 2 result + G2 完成 | MIT+PM / FA | 2d |
| **P0-3-02** | 🔴P0 | Edge 重評決策會（3 分支：翻正/仍負/部分改善） | P0-3-01 | PM+FA+PA+QC | 1d 會議 |

**outcome 分支**：
- A. edge 翻正 → cost_gate 重啟 + Track P Phase 1b 解凍 → LG-2~5 推進
- B. edge 仍負 → DUAL-TRACK 全力 + 策略重做 + 部分策略下架
- C. 結構性改善 → Phase 5 部分接線

### Live Gate（5 項全綠）

| ID | Tag | 項目 | 前置 | 負責 | 工時 |
|---|---|---|---|---|---|
| **LG-2** | 🔴P0 | H0 Gate blocking 驗證（shadow → blocking） | P0-3 | E1+PM / E2 | 1d |
| **LG-3** | 🔴P0 | provider pricing table 正式綁定 | P0-3 | E1 | 0.5d |
| **LG-4** | 🔴P0 | M 章 Supervised Live Gate | P0-3 | E1 | 1d |
| **LG-5** | 🔴P0 | N 章 Constrained Autonomous Live | LG-2/3/4 | E1+PM | 0.5d |
| **G-4** | 🟡P2 | Cookie `secure=True`（HTTPS 部署後） | HTTPS | E1 | 0.5d |

### G9 Bybit API 精進（新增，from BB，並行執行）

| ID | Tag | 項目 | 前置 | 負責 | 工時 |
|---|---|---|---|---|---|
| **G9-01** | 🟡P2 | Bybit API 字典 confirm-mmr 路徑修正 + SSOT 標記 | 無 | BB+TW | 2h |
| **G9-02** | 🟡P2 | WS 容錯強化（handler not found 強制重連） | 無 | BB+E1 / E2 | 1-2h |
| **G9-03** | 🟡P2 | `bybit_public_connectivity_check.py` 環境變數化 | 無 | BB+E1 / E2 | 1h |
| **G9-04** | 🟡P2 | `bybit_private_ws_smoke_test` 環境感知或刪除 | 無 | BB+E1+PM / E2 | 1-2h |
| **G9-05** | 🟡P3 | L-2~5 字典補錄（參數名稱 / 缺失欄位） | 無 | BB+TW | 2-3h |

### Wave 4 完成標準 → LIVE

- [ ] P0-3 決策產生具體執行路徑（A/B/C 三選一）
- [ ] LG-2/3/4/5 全綠
- [ ] 5 項硬邊界全綠 → operator 簽 `authorization.json` → Live 開啟

---

## 🔄 背景線程（獨立於 Wave，持續運行）

這些**不阻塞主路徑**，跟著 Wave 並行進行。每項都有對應 healthcheck 6h cron 監控。

| 項目 | 類型 | 起算/結束 | 狀態 | Healthcheck | 若 FAIL |
|---|---|---|---|---|---|
| **P0-2** 21d demo 時鐘 | 時間被動 | 2026-04-16 → 2026-05-07 | 🟡 進行中 ~8d | [0] engine_alive + [1] 0 crash | 時鐘重置 |
| **P1-10** PostOnly 1-2w 驗證 | 資料被動 | 2026-04-21 → 05-07/08 | 🟡 累積中 | [3] maker_fill_rate | 驗收失效→G2-04 決策 |
| **EDGE-DIAG** exit_features 累積 | 資料被動 | 2026-04-19 → 04-26 滿週 | 🟡 累積中 | [14] exit_features_rate | 延後 Phase 1b |
| **P1-7 C** labels pooled ≥200 | 資料被動 | 持續累積 | 🟡 47→200 ETA 3-5d | [10] label 速率 | G4-02 延後 |
| **P1-8 FUP** DUST-EVICTION 觀察 | log 被動 | 2026-04-17 → 04-24 滿週 | 🟡 ~7d | dust log count | 觀察到新 pattern 才提案 |
| **P1-11** bb_breakout rebuild 後觀察 | 部署被動 | 待 operator rebuild | ⬜ | [12] fill rate recover | 結構性 dormancy confirmed |

**規則（CLAUDE.md §七）**：任何背景項連續 3 次 healthcheck FAIL = 中止被動等待，轉人工介入。

---

## 📦 Backlog（條件觸發，非當前 Wave）

| # | 項目 | 觸發條件 | Tag | 備註 |
|---|---|---|---|---|
| **STRATEGIST-AUTO-PROMOTE** | 自動晉升規則 | P2-01 穩定後 | 🟡P3 | 默認關，可選 |
| **EDGE-P2 Phase B** | Liquidation signal | Phase A OI 驗收後 | 🟡P3 | OI 2026-04-20 已完 |
| **EDGE-P2-3 Phase 2+** | live endpoint / funding_arb PostOnly | Phase 1b | 🟡P3 | ML integration 前置 |
| **Phase 5 補強** | Symbol Embedding / Regime LSTM / JS+Scorer | P0-3 判決 | 🟢P3-P4 | 取決於 P0-3 outcome |
| **G-2 FundingArb 重評** | 三參數重評 | R-02 Strategist 在線 | 🟡P3 | G-1 AI Agent 推進後 |
| **ORPHAN-ADOPT-1 Phase 2B** | Strategist `would_take` 終仲裁 | G-1 R-02 | 🟡P3 | |
| **IP-DEDUP-1** | IntentProcessor 去抖 | P0-3 後 edge 仍負 + 高重發率 | ⚫P4 | 條件觸發 |
| **4-06** | LinUCB live warm-start | v1→v2 遷移 | ⚫P4 | memory archive |
| **OC-4** | MCP PostgreSQL 自然語言 | Phase 5+ | ⚫P4 | |
| **G-6** | Edge JS 滾動重訓 | P1-7 B 解 | ⚫P4 | 自然解鎖 |
| **G-8** | cost_gate 可信度 | EDGE-P3-1 Stage 2 | ⚫P4 | |
| **4-Conditional** | PairsTrading / Beta Hedging / Kalman / Mac遷移 / Jump detection | post-live | ⚫P4 | 未來功能 |
| **G-7** | ClaudeTeacher 啟用 | 21d demo + G-3 | 🟡P2-P3 | consumer_loop.rs enabled |
| **G-10** | Calibration.py isotonic | run_training_pipeline 輸出 | 🟡P2-P3 | ECE < 0.05 |
| **LLM-ABC-MIGRATION-1** | ✅ 2026-04-20 完成 | — | ✅ | FA 驗 |
| **QoL-2** | Demo AI cost 追蹤 | G3-08 | 🟡P2 | GUI 硬編碼 'N/A' |
| **DUST-EVICTION GUI** | GUI 曝光 orphan_frozen | P1-8 觀察完 | 🟡P2 | 日報 |
| **LEARNING-COCKPIT-NO-IPC** | Learning 8 端點走 Python state_store | G-7/G-10 後 | 🟡P2 | 設計債 |
| **STRATEGIST-PERSIST-AUDIT-GAP-COUNTER-1** | Phase 5+ 硬依賴 | G3-02 | 🟡P2 | FA H2 |
| **STRATEGIST-TUNE-TARGET-CONFIG-1** | 運行時可配置 | Phase 5+ | 🟡P2 | |
| **STRATEGIST-HISTORY GUI** | ✅ 2026-04-24 完成 | — | ✅ | tab-strategy.html 折疊 sub-panel（summary KPI + 3 filter + list 50 行 + Diff/7d Effect 展開） |

---

## 📊 Healthcheck 清單（15 + 新增 [13-15]）

**CLAUDE.md §七 強制**：被動等待 TODO 必附 healthcheck · 每 6h cron 跑 · 連續 3 FAIL → 中止等待。

### 現有（12 個，`passive_wait_healthcheck.py` 已實裝）

| # | 項目 | SQL / 檢查 | 對應 Wave TODO |
|---|---|---|---|
| [0] | engine_alive | last 24h PID activity | P0-2 21d |
| [1] | engine_crash count | COUNT last 24h | P0-2 21d |
| [2] | synthetic_owner_retriage | row count growth | P1-6 |
| [3] | maker_fill_rate | PostOnly fill rate | G2-01 |
| [4] | IPC hotpatch | last applied ts <5min | G3-05 |
| [7] | edge_estimates_freshness | n_cells + mtime | G1-01 / G4-04 |
| [8] | decision_shadow_exits | row count | G4-05 |
| [9] | model_registry_freshness | train_date per slot | G4-03 |
| [10] | intents_writer_ratio | orders vs intents per-mode | — |
| [11] | counterfactual_clean_window_growth | clean n ≥200 | EDGE-P3 auto-gate |
| [12] | bb_breakout_post_deadlock_fix | fill count recover | G2-05 |

### 新增（Wave 1 G6-02 補齊，3 個）

| # | 項目 | SQL / 檢查 | 對應 Wave TODO |
|---|---|---|---|
| **[13]** | edge_estimator_scheduler_fresh | `edge_estimates.json` mtime <6h + cells ≥50 | G1-01 / G4-04 強制 |
| **[14]** | exit_features_accumulation_rate | 週 row count 增長率 ≥ threshold | EDGE-P1b |
| **[15]** | shadow_exit_agreement_phase2 | Python vs Rust decision agree rate ≥95% | EDGE-P2 flip |

---

## 📚 已完成歸檔索引

| 日期 | 歸檔 | 內容 |
|---|---|---|
| 2026-04-24 | `docs/archive/2026-04-24--completed_todo_batch.md` | P0-13/14/15 三連 · P1-11 Phase 1 · EDGE-DIAG 1+2+4 |
| 2026-04-24 | `docs/archive/2026-04-24--todo_v2_dual_axis_snapshot.md` | v2 458 行（雙軌混用，本次重組前快照） |
| 2026-04-24 | `docs/archive/2026-04-24--todo_v1_refactor_snapshot.md` | v1 328 行（10-Agent Round 1 重構版）|
| 2026-04-24 | `docs/archive/2026-04-24--todo_snapshot_pre_refactor.md` | v0 700 行（重構前舊版） |
| 2026-04-23 | `docs/archive/` | DEDUP-PY-RUST A+B+C+D · INFRA-PREBUILD-1 A+B |
| 2026-04-22 | `docs/archive/2026-04-22--step_0_derived_todo_batch.md` | TRACK-P-V2-SWAP · TICK-PIPELINE-MOD-SPLIT |
| 2026-04-21 | `docs/archive/2026-04-21--completed_todo_batch.md` | TRACK-P-T4-WIRING + 14 項 |
| 更早 | `docs/archive/` | 按日期批次 |

---

## ⚙️ 工作流程速查

```
角色鏈：E1/E1a 並行（≤5）→ E2 審查（強制）→ E4 回歸（強制）→ PM 確認 → commit + push
詳見 CLAUDE.md §八 · 16 Agent 定義 docs/CLAUDE_REFERENCE.md
```

**部署**：
- 改碼 → `ssh trade-core "bash helper_scripts/restart_all.sh --rebuild"`
- 清倉 → `ssh trade-core "bash helper_scripts/clean_restart.sh --yes"`
- 全重 → `ssh trade-core "bash helper_scripts/fresh_start.sh --yes"`
- 停機 → `ssh trade-core "bash helper_scripts/stop_all.sh"`

**SSH bridge（Mac → Linux）**：Mac = SSOT，透過 `ssh trade-core` 遠端觸發 Linux runtime；Mac 本地僅 `git fetch / pull --ff-only`，禁 merge/rebase/reset。

**Bybit API**：先讀 `docs/references/2026-04-04--bybit_api_reference.md`，新端點同步字典。
**風控參數**：必須透過 IPC `patch_risk_config` 單一通道。
**被動等待**：必附 `passive_wait_healthcheck.py` check（CLAUDE.md §七）。

---

**簽核鏈**：PA 核實 → PM Sign-off → commit/push → Linux pull → Wave 1 開工
**下一步（2026-04-24 立即）**：G1-01 Linux 診斷 scheduler + G1-02 PA/E1 啟動 event_consumer 拆分規劃
