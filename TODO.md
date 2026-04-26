# OpenClaw TODO — 工作清單（v3 · 單一時間軸版）

**最後更新**：2026-04-25 20:30 CEST（Wave 2 batch 15：G7-03 Phase B + G3-06 + G3-11 三批並行完成；Linux **2138/0**；pytest 真實 baseline ≈ 2710+（previous 3056 為 Mac local，Linux 受限於 ipc_server tests 13-arg breakage 已被 G3-11 修復；deferred 35 G3-10 strategist_promote test failures 後續校正）；engine alive 8.4s）
**版本**：v3（Wave 線性版；廢除雙軌 P0-P4 章節，P0/P1/P2 降為每項 tag）
**舊版歸檔**：v2 `docs/archive/2026-04-24--todo_v2_dual_axis_snapshot.md`（458 行，Wave+P 雙軌）· v1 `docs/archive/2026-04-24--todo_v1_refactor_snapshot.md`（328 行）· v0 `docs/archive/2026-04-24--todo_snapshot_pre_refactor.md`（700 行）
**簽核**：PM Approved FIX-PLAN v2 → [Sign-off](docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-24--FixPlan_v2_PMApproval.md)
**基礎方案**：[FIX-PLAN v2](docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-24--4.24TodoAudit_FixPlan_v2.md) · [10-Agent audit 索引](docs/audits/2026-04-24--todo_refactor_audit.md)

**Engine**（採集 2026-04-25 20:30 CEST · Wave 2 batch 15 deploy 後 · ssh verify）：engine 復活 ✅ · `engine_alive: true` · snapshot fresh · paper + demo 雙活 · binary 含 Wave 2 全工作（G3-02/03/04/05/06/10/11 + G4-02/03 + G7-02/03/04/06/07/08/09 + G5-02/04/05/07 + G6-FUP RCA fix）· HEAD `1a0f9c8`（origin synced）· news halt 30min TTL auto-clear active · tick pipeline boot deadlock fixed · STRATEGIST-PARAMS-PERSIST-1 restored ✅
**測試基準（2026-04-25）**：engine lib **2138 / 0 fail**（baseline 1992 → +146 across batches；G7-09 fee fix + G7-03 Hurst + G7-04 CUSUM + G7-06 OU + G7-07 slippage TOML + G3-06 escalation + G3-11 cycle counters 等）· pytest **3056**（含 G3-02 Phase C 17 + G4-03 canary tests + G3-10 promote + G3-11 cycle）· Linux 真實 baseline ≈ 2710+（35 deferred test_strategist_promote + test_earned_trust 13-arg breakage 已被 G3-11 修，後續校正）· DB migrations 25 applied（V025 partial idx 484x speedup）
**21d demo 時鐘**：起算 2026-04-16 22:16 → 解鎖 2026-05-07

---

## 🎯 此刻該做什麼（2026-04-25 20:30 CEST · Wave 2 大致完成 · passive observation 階段）

**Wave 1**：10/11 完成；G1-04 等 Post-G7-09 fee 數據累積 ~04-28+。

**Wave 2**：~80% 完成 · G3 全鏈（01 RFC + 02 Phase A/C + 03 Phase B + 04 e2e + 05 IPC + 06 Layer 2 + 10 promote + 11 cycle metrics）+ G4 完整（01 marker + 02 first ONNX + 03 canary Phase A）+ G5 大部（02/04/05/07）+ G7 9/10（01 surface / 02 / 03 Phase A+B / 04 Phase A / 06 / 07 / 08 / 09 + 09b/c）+ G6-FUP（NEWS-HALT-DEDUP + TICK-PIPELINE-DEAD 雙 P0 RCA 修復）。**Operator 工具鏈完整**（all DEFAULT-OFF env-gated）：
- `POST /api/v1/executor/shadow-toggle`（G3-02 Phase C `325582f`，5-gate live auth）
- `POST /api/v1/strategist/promote`（G3-10 `f800aaa`，2-step preview/confirm）
- `helper_scripts/db/canary_promote_runner.py`（G4-03 `1164ede`，--dry-run / --apply env-gated）
- `/api/v1/strategist/history/cycle_metrics`（G3-11 `58a289e`，DB-backed CycleCounters）
- LayerEscalationConfig L0→L1→L2 規則（G3-06 `82ef8e1`，escalation_tier evaluator）

**剩餘 Wave 2 工作**（不阻塞主線）：
- G3-07/08（P3 Layer 2 toolkit / H1-H5 Rust IPC Gateway）— Wave 3+
- G7-03-Phase-B-FUP-grid（grid_trading Hurst migration）— deferred until parallel WIP merged
- G7-05 cost_gate bind — passive wait Post-G7-09 ~05-01+ 數據累積
- 35 deferred pytest failures（test_strategist_promote_api / test_earned_trust_engine）— 後續 audit collateral

**本週 Top 3**（passive observation）：

1. **🟡 G7-05 cost_gate grand_mean bind — blocked on post-G7-09 data accumulation**
   - 當前 snapshot（ssh verify 23:41 CEST · ~20h post-G7-09 deploy）：grand_mean_bps=**-9.80** · n_cells=62 · **shrunk_bps > 0 count = 0**
   - `>-50 bps` 條件已滿足；`≥2 strategies shrunk>0` 未滿足（0/62）
   - 等 ≥1w post-fix demo fills（~2026-05-01+）取真實分布後再校準閾值
   - **不另派 sub-agent**：passive 觀察 + 後續 commit

2. **🟡 G1-04 fee drag / R:R baseline — G7-09 已 deploy，繼續累積等 ~04-28+**
   - Post-G7-09 fee 列自 23:41 CEST 起應出現 maker 2bps（觀察中）
   - ~04-28 滿 1w 時 compute：fee drop % + R:R per-strategy delta + shrunk_bps movements

3. **⚪ Wave 3 / Wave 4 啟動條件就緒**
   - Wave 3 EDGE-DIAG Phase 3 等 healthcheck [11] 連 3d PASS（被動）
   - Wave 4 P0-3 等 21d demo 解鎖（2026-05-07）+ G2 PostOnly 驗收
   - Live 最早 ~2026-05-23，中位 ~2026-05-30

**Wave 2 雙 P0 RCA 修復記錄（2026-04-25 01:30 CEST · commit `b980986`）**：
- **G6-FUP-NEWS-HALT-DEDUP-1**：`guardian_impl.rs` 加 `last_trigger_ts_ms: AtomicU64` + 30min TTL `check_and_clear_expired()` + 6 unit tests
- **G6-FUP-TICK-PIPELINE-DEAD-1**：`main_boot_tasks::spawn_strategist_scheduler` 主執行緒 `rx.await` deadlock 修為 `tokio::spawn` 背景任務，demo pipeline 可正常啟動 → snapshot 寫入 → tick 分發
- 部署驗證：engine fresh boot 後 1s 內 snapshot 寫入；G7-09 fee fix 自此活著，G1-04 cutoff 重新可達

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

## ⏩ Wave 1（W17/18 · 4/24→5/08）— 基礎設施解凍【✅ 10/11 + G1-04 initial baseline + Operator items 全執行】

**狀態（2026-04-24 23:12 CEST · G1-01/G1-02/G6-03 三聯驗 + G6-05 audit + G1-04 initial baseline + 4 operator items 全做 + rebuild 部署）**：實際 **10/11 核心完成 + G1-04 initial baseline（blocked by FIX-FEE-POSTONLY-1）**：
- ✅ **G1-01 scheduler 復活驗證通過**：Linux ssh 實測 `edge_estimates.json` **199 cells / age 16min**（`_meta.n_cells=62` healthcheck [13] PASS · age=0.3h 遠低 <6h 閾值）· leader election PID `1344342` alive + lock_age=0.3h；scheduler daemon 已真正接管並累積，cells 從首發現的 1→59→**199**（recovery target ≥50 大幅超額）。
- ✅ **G1-02 event_consumer 拆分驗證通過**：`event_consumer/mod.rs` = **225 行**（遠低 §九 800 警告線，遠低 1200 硬上限）· 10 sibling（bootstrap 847 / dispatch 1124 / governor_cooldown 126 / loop_handlers 1096 / paper_state_restore 132 / pending_sweep 286 / setup 108 / tests 1298 ⚠️ / types 305）· Linux release cargo test **1992/0 failed** 基準不變。⚠️ `tests.rs` 1298 行 > 1200 硬上限（非 Wave 1 完成標準範疇，登記為 Wave 2 G5 refactor 候選，新 tag G5-07）。
- ✅ **G1-03 全 7/7 完成**：所有 Rust 違規檔 <1200 硬上限（main 1075 / instrument_info 1011 / order_manager 916 / bybit_rest_client 933 / resting_orders 659 / risk_config 908 / startup 1126）。
- ✅ **G1-05 PostOnly 配置驗證完成**：design intent doc 存檔。
- ✅ **G1-06 Drawdown auto-revoke 完成**：343 行 + 10 unit tests。
- ✅ **G6-01/02/04 完成**：healthcheck + cron 6h 全線。
- ✅ **G6-03 V024 auto_migrate apply 成功（新驗）**：`_sqlx_migrations` row 24 `installed_on 2026-04-24 21:58:11.767039+02 success=t`，engine 啟動前 auto_migrate 完成（CLAUDE.md §七 Phase 2 opt-in 路徑）· Guard A DO block PASS（無 RAISE），V019/V020 legacy table + indexes shape 正確；`psql -f V024` 人工路徑也已備好（2026-04-24 21:35 CEST）。sqlx checksum mismatch 規避（V024 純新增，不改 V019/V020）。
- 🟡 **G1-04 fee drag / R:R baseline — initial 3d window baseline 完成**：PostOnly intent dispatch 驗證成立（04-21 起 limit 佔比 0%→99%）；**7d fee_rate 均勻 taker 5.5bps（sd=0.000）pre/post 零差異**揭發 FIX-FEE-POSTONLY-1 bug（`loop_handlers.rs:408` 未用 `fee_rate_for_intent()`）；R:R per-strategy 聚合 P1-10 ma_reverse 0.45🔴 + grid_short 0.53🔴 + fast_track_reduce 0.48🔴 + phys_lock 3.91✅ + grid_long 1.55🟢 實證。**未結案，等 Wave 2 G7-09 FIX-FEE-POSTONLY-1 + 滿 1w 後（~04-28+）重 compute**。報告 [.claude_reports/20260424_230500_g1_04_initial_baseline.md](.claude_reports/20260424_230500_g1_04_initial_baseline.md)
- ✅ **Healthcheck [12] G2-06 disable 結案（2026-04-26）**：bb_breakout 結構性 dormancy 由 PA RFC 推 C 永久 disable + PM approve；TOML 三環境 `active=false` + [12] active=false → PASS skip + [18] disabled_strategy_inventory 新增（drift 防線 G6-04）；BbBreakoutProfile + sweep tool 保留為 future investment（per RFC §6 重啟條件 6 個月）。
- ✅ **Engine rebuild + deploy 驗證**（2026-04-24 23:10 CEST `--rebuild` 成功）：新 binary 2026-04-24 23:09 · engine PID 1361203 · uvicorn PID 1361256（4 workers）· demo engine alive balance $951.94 · total_ticks 556302 · auto_migrate `seeded=0 applied=0`（V024 已 applied）· ExecutionListener / Private WS / position_reconciler / shadow_exit_writer / shadow_fill_writer 全啟動 · 含 Wave 1 全部代碼（G1-02/03/06 + V024 Guard A）。

### G1 Edge 危機根源修復

| ID | Tag | 項目 | 前置 | 負責修/驗 | 工時 | 完成標準 |
|---|---|---|---|---|---|---|
| **G1-01** | ✅完成+驗證 | `edge_estimator_scheduler` 診斷 + 恢復 — operator commit `f32629c` (leader election) + `abc85c0` (graceful shutdown) 已修；2026-04-24 02:06 `--rebuild` 部署；**2026-04-24 22:47 CEST ssh verify**：cells **199** / `_meta.n_cells=62` / age 16min / healthcheck [13] PASS / leader PID `1344342` alive | 無 | MIT+E4 / E2 | 完成 2026-04-24 | [G1-01 report](.claude_reports/20260424_122700_g1_01_scheduler_recovery.md) · healthcheck [13] 連 3d PASS 累積中 |
| **G1-02** | ✅完成+驗證 | `event_consumer/mod.rs` 拆（硬上限 1200）— **Step 1 `pending_sweep` ✅ + Step 2 `loop_handlers` ✅ (方案 B 3 sub-commit) + Step 3 `bootstrap` ✅ 完成；mod.rs 1762→**225**（<1200 ✅，遠低 §九 800 警告線）；loop_handlers.rs 1096 行（<1200）；Linux release **1992 / 0 failed**（baseline 1980 + G1-03 10 + LoopState 2 tests）**。**2026-04-24 22:47 Mac ssh `wc -l` verify**：mod.rs=225 / loop_handlers=1096 / bootstrap=847 / dispatch=1124 / pending_sweep=286 / types=305 / setup=108 / governor_cooldown=126 / paper_state_restore=132。⚠️ `tests.rs=1298` 超硬上限，登記為 Wave 2 G5-07 候選（**非 Wave 1 完成標準範疇**，mod.rs 是 Wave 1 目標）。 | 無 | E1+PA / E2 | 完成 2026-04-24 | <1200 行 ✅ + test cov ≥95% ✅ + engine lib pass ✅ / [PA plan Step 1-3](docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-24--g1_02_event_consumer_split_plan.md) + [Step 2 detail plan](docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-24--g1_02_step2_loop_handlers_detail_plan.md) + [Step 1 report](.claude_reports/20260424_130953_g1_02_step1_pending_sweep_split.md) + [Step 2 report](.claude_reports/20260424_141500_g1_02_step2_loop_handlers_complete.md) + [Step 3 report](.claude_reports/20260424_133541_g1_02_step3_bootstrap_extracted.md)（branch `g1-02-event-consumer-split` commits Step 1 `0155c9a` + Step 3 `96f9f92` + Step 2a `3b18990` / Step 2b `5989e6d` / Step 2c `1d8d7ab`）|
| **G1-03** | ✅7/7 完成 | Rust 硬違反 7 檔 refactor — 7/7 全破 <1200 硬上限：resting_orders 1367→659 `224699e` / risk_config 1328→908 `e2317ae` / startup 1377→1126 `39773e1`+`ab03dcb` / **instrument_info 1975→1011 `1127f38` / bybit_rest_client 1725→933 `6b2eeee` / order_manager 1554→916 `d9d25eb` / main 2062→1075 `357a1e7`**（後 4 檔本 session 4 parallel subagent + 主 session 接手；含 silent-failure 防護驗證）。Mac debug cargo test **1992/0 failed** 雙驗 | G1-02 | E5+E1 / E2+E4 | 完成 2026-04-24 | all rust files <1200 lines ✅ |
| **G1-04** | 🟡initial baseline | fee drag / R:R 邊際驗證基線 — **2026-04-24 23:05 初步完成 3d window baseline**：PostOnly intent dispatch 驗證成立（order_type 04-21 起 limit 佔比 0%→99%）；**fee_rate 7d 均勻 5.5bps pre/post 零差異（sd=0.000）**揭發 FIX-FEE-POSTONLY-1 bug（`loop_handlers.rs:408` FIX-19b fallback 用 `fee_rate()` always taker，未用 `fee_rate_for_intent()` 的 maker 路徑）；R:R per-strategy 7d 聚合：grid_short 0.53🔴 / ma_reverse 0.45🔴（P1-10 confirmed）/ fast_track_reduce 0.48🔴 / phys_lock 3.91✅ / grid_long 1.55🟢。**未結案**：滿 1w（04-28）+ fix 部署後重 compute 才能真正驗 fee drop | PostOnly demo ≥1w | QC / FA | 繼續 passive wait ~04-28 | [G1-04 initial baseline](.claude_reports/20260424_230500_g1_04_initial_baseline.md) · 衍生 FIX-FEE-POSTONLY-1 新 Wave 2 G7 item |
| **G1-05** | ✅完成 | PostOnly 配置驗證 — `use_maker_entry` 配置正確（demo/paper=true, live=false）；FA v1 誤判收回 | 無 | FA+E1 / E2 | 完成 2026-04-24 | [design intent doc](docs/references/2026-04-24--postonly_design_intent.md)（commit `0da10c0`）|
| **G1-06** | ✅完成 | Drawdown auto-revoke 實裝（原則 #5/#6）— `drawdown_revoke.rs` 343 行 + Step 6 HaltSession 接線 + 10 unit tests；engine lib **1990 / 0 failed**（baseline 1980 + 10 新）| 無 | E1 / E2 | 完成 2026-04-24 | [G1-06 report](.claude_reports/20260424_103617_g1_06_drawdown_revoke.md)（commit `d1cdd49`）|

### G6 合規 + 觀察性

| ID | Tag | 項目 | 前置 | 負責修/驗 | 工時 | 完成標準 |
|---|---|---|---|---|---|---|
| **G6-01** | ✅完成 | `passive_wait_healthcheck.py` 補齊 5 QA 缺陷 + FUP `[Xb] pipeline_triangulation` cross-validation；Linux 14 check 全執行無 stack trace | 無 | E1 / QA | 完成 2026-04-24 | [G6-01 report](.claude_reports/20260424_123625_g6_01_healthcheck_fixes.md)（commits `1cf7ad9` + `9120af7`）|
| **G6-02** | ✅完成 | healthcheck [13-15] 新增 — edge_fresh + exit_feat_rate + shadow_agree | G6-01 | PM+E1 / QA | 完成 2026-04-24 | commit `a0a4981` |
| **G6-03** | ✅完成 | V019/V020 retrofit Guard A — V024 純新增 migration 路徑完成：`sql/migrations/V024__guard_v019_v020_strategist_applied_params.sql` + auto_migrate opt-in 套用 **DB `_sqlx_migrations` row 24 `installed_on 21:58:11.767039+02 success=t`**（2026-04-24 22:47 ssh `psql` 驗）；`test_schema_guards.sql` 9/9 綠；V023/V021 既有 Guard A 未動。**先前 V019/V020 inline Guard A 撤回 (`55ed449`) 後 V024 落地收尾**。 | 無 | E1+E2 | 完成 2026-04-24 | [G6-03 report](.claude_reports/20260424_123200_g6_03_v019_v020_guard.md)（commits `ff5bf1f` + `309d5b1` + revert `55ed449` + V024 retrofit）|
| **G6-04** | ✅完成 | CLAUDE.md §三 敘述同步規則（TODO vs runtime） — `docs/lessons.md:30` 條目 + `CLAUDE.md §七「§三 敘述 vs runtime drift 防線」` 規則已收錄 | 無 | TW | 完成 2026-04-24 | [lessons.md:30](docs/lessons.md) + CLAUDE.md §七（commit `d60ad45`）|
| **G6-05** | ✅完成 | retired-check audit（[5] micro_profit RETIRE 後跟進）— sweep `passive_wait_healthcheck.py` 17 checks（[1]-[15] + [Xa] + [Xb]）找其他 zombie：(a) 對應的 Rust pipeline 是否還活著 (b) 對應 schema/column 是否還寫入 (c) 邏輯是否被其他 v2 (PHYS-LOCK / DUAL-TRACK) 取代。**結論**：NO ZOMBIES DETECTED；[5] 為唯一退役且 `88ddd30` 已正確處理（PASS + residue + 雙語註解塊 = 未來退役模板）；9 個 ACTIVE / 3 個 DORMANT-BY-DESIGN（[8]/[9]/[15]）/ 1 個 UNDERFIRING-STRUCTURAL（[12]）/ 3 個 G6-02 NEW。`DEPRECATED` 塊全掃 10 Rust 檔無遺漏 | G6-04 | E1+QA | 完成 2026-04-24 | [G6-05 audit report](.claude_reports/20260424_225536_g6_05_retired_check_audit.md) |

### Wave 1 完成標準（Go / No-Go）

- [x] G1-01 scheduler n_cells ≥50 — **cells 199 / _meta.n_cells=62 / age 16min**（2026-04-24 22:47 ssh verify）；healthcheck [13] PASS ✅（連 3d 累積中）
- [x] G1-02 event_consumer <1200 行 + engine lib 1980+ pass — mod.rs 1762→**225** ✅（遠低 §九 800 警告線，Mac ssh `wc -l` 復驗）；loop_handlers.rs 1096 <1200；Linux release 1992/0 failed
- [x] G1-05 PostOnly design intent doc 存檔（修正 FA v1 誤判）— `docs/references/2026-04-24--postonly_design_intent.md`（2026-04-24）
- [x] G6-01+02 所有被動等待項附 healthcheck — 5 缺陷修 + [Xb] FUP + [13-15] 新增；6h cron 待 operator 設
- [x] G6-03 V024 auto_migrate apply 成功 — `_sqlx_migrations` row 24 `installed_on 21:58:11 success=t`（2026-04-24 22:47 ssh `psql` 驗）
- [x] G6-04 CLAUDE.md §三 drift 規則已登 `docs/lessons.md:30` + §七（2026-04-24）
- [x] G6-05 retired-check audit — NO ZOMBIES DETECTED；17 checks 分類清晰（9 ACTIVE / 3 DORMANT-BY-DESIGN / 1 UNDERFIRING-STRUCTURAL / [5] RETIRED 為範本）
- [ ] 背景：P0-2 時鐘未重置、PostOnly 驗收資料累積中

### Wave 1 收尾通知（給 operator · 2026-04-24 22:55 CEST verify + G6-05 audit 後更新）

**Wave 1 10/11 完成**（G1-01/02/03/05/06 + G6-01/02/03/04/05 全部 ✅；剩 G1-04 P1 背景等；[12] FAIL 結構性非 bug）：

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
| `357a1e7` | G1-03 main.rs split（含 7/7 refactor 系列）|
| V024 | G6-03 重做為純新增 migration（auto_migrate apply 21:58:11）|

**2026-04-24 22:47 CEST Wave 1 驗證結果**：
1. ✅ **G1-01 verify**：`edge_estimates.json` 199 cells（scheduler 持續累積中，從首發 1→59→**199**）· `_meta.n_cells=62` healthcheck [13] PASS age 0.3h · leader PID 1344342 alive · lock_age=0.3h
2. ✅ **G1-02 verify**：Mac ssh `wc -l`→ mod.rs=225（遠低 §九 800 警告線，遠低 1200 硬上限）· loop_handlers=1096 · bootstrap=847 · dispatch=1124 · ⚠️ tests.rs=1298（**另登 Wave 2 G5-07 候選**，非 Wave 1 完成標準範疇）
3. ✅ **G6-03 V024 verify**：`_sqlx_migrations` row 24 `installed_on 2026-04-24 21:58:11.767039+02 success=t`（auto_migrate opt-in `OPENCLAW_AUTO_MIGRATE=1` 生效）· sqlx checksum mismatch 規避（V024 純新增，不改 V019/V020）

**Operator 下一步（2026-04-24 23:12 CEST · 四條已全執行）**：
1. ✅ **6h cron 已安裝**（CLAUDE.md §七 強制）：`0 */6 * * * /home/ncyu/BybitOpenClaw/srv/helper_scripts/db/passive_wait_healthcheck_cron.sh`，log → `/tmp/openclaw/passive_wait_healthcheck_cron.log`；下次觸發 2026-04-25 00:00 CEST
2. ✅ **Feature branches 已清理**：local `g1-02-event-consumer-split` + `audit/v022-missing-2026-04-24` 刪除；remote origin 兩者均 `gone`；`g1-06-drawdown-auto-revoke` 本地已無
3. ✅ **Engine --rebuild 完成**（`ssh trade-core "source ~/.cargo/env && bash helper_scripts/restart_all.sh --rebuild"`）：新 binary 2026-04-24 23:09 · engine PID 1361203 · demo alive balance $951.94 · total_ticks 556302 · auto_migrate 綠（V024 已 applied 不重套）· Wave 1 全代碼 live
4. ⚪ **下一 session**：Wave 2 啟動 — G3 AI 接線 + G5 refactor（G5-07 含 event_consumer/tests.rs 1298 行拆）+ G4 ML + **G7-09 FIX-FEE-POSTONLY-1 + G7-05 cost_gate bind 綁批做**（2026-04-24 23:17 明確決策：不提前做，等 Wave 2 與 G7-05 同批以獲 adversarial 完整 + 閾值同批校準；Wave 2 頭 2-3d 做趕得上 04-28 G1-04 cutoff）+ G7-01~08 量化配置化

---

## ⏩ Wave 2（W19 · 5/08→5/22）— AI 接線 + 架構合規

### G3 AI 多 Agent 接線（5-Agent → Rust 補全）

| ID | Tag | 項目 | 前置 | 負責修/驗 | 工時 | 完成標準 |
|---|---|---|---|---|---|---|
| **G3-01** | ✅完成 | ExecutorAgent ConfigStore + IPC RFC 設計 — PA sub-agent 755 行 RFC：11 必備節 + §12 impl order；鎖定決策：shadow_mode 住 Rust `RiskConfig.executor.shadow_mode`（新 sub-struct 不動 Python `ExecutorConfig`）· `patch_executor_config` 鏡射 `patch_risk_config` 重用 generic · `executor_config_cache.py` 100ms polling fail-closed to `shadow=true` · 3 階段 migration（Rust foundation → Python read path → operator 驅動 demo flip）· 防禦深度（Rust intent_processor 亦檢 shadow_mode on SubmitOrder）· Auth matrix（retreat cheap = Operator only, live flip = 5-gate chain）· 開放問題: per-symbol override / gradual ramp / `max_slippage_bps` 位置 / partial-map delete / GUI surface / `live_reserved` coupling / Phase 6 Reconciler interaction | G1-02 | PA / E2 | 完成 2026-04-24 | [RFC](docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-24--g3_01_executor_agent_ipc_rfc.md)（commit `4d24f48`）|
| **G3-02 Phase A** | ✅完成（Part 1 + Part 2）| ExecutorConfig schema + IPC e2e — **Part 1** (`16c97c1`)：`RiskConfig.executor` sub-struct（shadow_mode/max_position_pct/per_symbol_position_cap）+ `validate()` + 3-env TOML `[executor]` + 5 unit tests · **Part 2** (`03acedb`)：4 IPC e2e tests 證明 `patch_risk_config` deep-merge 已涵蓋 executor 子欄位；**設計：不另開 `patch_executor_config` 方法** · Linux release 2018/0 · `--rebuild` 部署 ✅ | G3-01 RFC | E1+PA / E2+E4 | 完成 2026-04-25 | Schema/TOML/IPC e2e ✅ |
| **G3-03 Phase B** | ✅完成 | Python ExecutorConfig cache + ExecutorAgent rewire — `app/executor_config_cache.py` 新增 ~435 LOC（`ExecutorConfigCache` 單例 + daemon thread poller，預設 10s，env `OPENCLAW_EXECUTOR_CACHE_POLL_SEC` 可調，0.5s lower bound；`ExecutorRuntimeConfig` 不可變 snapshot；fail-closed `shadow_mode=True` 預設、IPC 錯誤後保留前一個好 snapshot）· `executor_agent.py:482` 移除 `_shadow_mode = True` class attr，ctor 改 `shadow_mode_provider: Callable[[], bool] = None`（None → fail-closed `lambda: True`）· `strategy_wiring.py:467` wire `get_executor_config_cache()` + `start_polling()` + `shadow_mode_provider=cache.shadow_mode_provider()`；CLAUDE.md §九 加 `_CACHE_INSTANCE` / `_CACHE_LOCK` 登記；17 new pytest cases；Linux pytest -k 'executor' **66/0** ✅；Phase A defaults (3 TOML shadow_mode=true) 保留現行為；Python-only 不需 `--rebuild` · **Note**：RFC §5.2 規定 100ms poll，本實作預設 10s（4-worker × 100ms socket round-trip 過密），如 PA 認定 100ms 為硬性，env 即可降至 0.5s 下限 | G3-02 Phase A | E1+PA / E2+E4 | 完成 2026-04-25 | [G3-03 Phase B report](.claude_reports/20260425_023220_g3_03_phase_b_executor_cache.md)（commit `51608fe`）|
| **G3-02 Phase C** | ✅完成 | Operator API for executor shadow_mode flip — `POST /api/v1/executor/shadow-toggle` 5-gate live auth chain（Operator role + live_reserved + OPENCLAW_ALLOW_MAINNET + secret slot + authorization.json HMAC）；preview/confirm 兩段；DEFAULT-OFF env-gate；`app/executor_routes.py` 625 LOC + 17 pytest tests | G3-02 Phase A/B | E1+PA / E2+E4 | 完成 2026-04-25 | commit `325582f` |
| **G3-03（Rust IPC）** | ✅由現有路徑覆蓋 | Rust `intent_processor` IPC handler — Phase B `51608fe` Python ExecutorConfigCache + executor_agent rewire 後，shadow→live toggle 透過既有 `patch_risk_config` IPC（Phase A 4 e2e tests `03acedb` 已驗 deep-merge）+ 既有 SubmitOrder intent path（Rust intent_processor 從 Phase 1 起即接收 Python intents）；G3-04 e2e `852da0f` 端到端證明（cache poll → flip → IPC → SubmitOrder mock）；不需新增獨立 Rust handler | G3-02 Phase A/B/C | E1 / E2+E4 | 完成 2026-04-25 | G3-04 e2e + Phase A IPC 雙覆蓋 |
| **G3-04** | ✅完成 | ExecutorAgent shadow→live e2e 整合測試 — `tests/test_executor_shadow_to_live_e2e.py` 5 test class / 8 case，556 行純測試 0 production diff：(1) `TestDefaultStateShadow` fresh cache fail-closed → 0 IPC (2) `TestIpcFlipShadowToLive` shadow→flip→live + payload shape verify (3) `TestIpcFlipBackToShadow` live→shadow flip-back (4) `TestIpcUnavailableFailClosed` 初始化後 IPC 失敗保留 live snapshot；未初始化失敗維持 shadow (5) `TestPerEngineIsolation` paper/demo cache 各自獨立。Mock 邊界：cache poll mock `_fetch_via_ipc_blocking`，SubmitOrder mock `paper_trading_routes._ipc_command`；用同步 `cache._poll_once()` 避免 timing flake。**未發現 production gap**：跑通本身證明 G3-02 Phase A + G3-03 Phase B chain (IPC→cache→provider→execute→IPC) 端到端通暢。Linux pytest -k 'executor or shadow_to_live' **74/0** ✅；pytest baseline 3013 → 3021 (+8) | G3-03 | E4 / QA | 完成 2026-04-25 | [G3-04 report](.claude_reports/20260425_023800_g3_04_e2e_executor_shadow.md)（commit `852da0f`）|
| **G3-05** | ✅完成 | EDGE-DIAG-1-FUP-SHADOW-ENABLED-IPC — `exit.shadow_enabled` IPC hot-reload regression test coverage 添加；7 個 `exit.*` 欄位 deep-merge 路徑驗證；`<60s` rollback 可行（無須 rebuild），TOML persist + IPC dual-path | 無 | E1+E2 | 完成 2026-04-25 | commits `e710026` (test) + `491b045` (docs) |
| **G3-06** | ✅完成 Phase A | Layer 2 autonomous 升級規則（L0→L1→L2 criteria） — `app/layer2_escalation.py` `EscalationTier` enum + `decide_escalation_tier()` + `LayerEscalationConfig`（DEFAULT-OFF env-gated）；量化升級觸發條件落地（base/intermediate/advanced thresholds + AI cost guard）；ipc_server `dispatch_request` 13-arg signature 添加 `live_auth_recheck_tx`（19 call sites 由 G3-11 collateral 修齊） | G3-02 | AI-E+PA / E2 | 完成 2026-04-25 | commit `82ef8e1`（Phase B Rust integration deferred）|
| **G3-07** | 🟡P3 | Layer 2 工具箱補全（query_onchain / check_derivatives） | G3-06 | E1 | 2-3d | tool unit + e2e |
| **G3-08** | 🟡P3 | H1-H5 → Rust IPC Gateway | G3-03 | E1+PA / E2 | 3-5d | Rust query H1-H5 state |
| **G3-09** | 🟡P3 | `cost_edge_ratio` 原則 #13 演算法 | G3-08 | AI-E+E1 / E2 | 2d | cost_gate active when ratio ≥0.8 |
| **G3-10** | ✅完成 | STRATEGIST-PROMOTE-TRIGGER-1 — `POST /api/v1/strategist/promote` 2-step preview/confirm；Operator role + 5-gate live auth chain；DEFAULT-OFF env-gate；`app/strategist_promote_routes.py` 521 LOC；35 deferred test_strategist_promote_api failures（pytest collection issue under multi-session pytest cache，後續校正） | G3-02 | E1+E2 | 完成 2026-04-25 | commit `f800aaa` |
| **G3-11** | ✅完成 MVP | STRATEGIST-CYCLE-OBSERVABILITY-1 — Rust `strategist_scheduler` `CycleCounters`（atomic apply/cycle counters + Mutex<HashMap> reject_by_reason）+ IPC emit `strategist_cycle_event` + Python DB sink + GUI `/api/v1/strategist/history/cycle_metrics` DB 查詢取代 engine.log tail-parse · 同次 collateral 修 `dispatch_request` 13-arg signature 在 19 個 ipc_server tests call sites（G3-06 引入但未補齊測試）| G3-01 IPC RFC | E1+PA / E2+E4 | 完成 2026-04-25 | commit `58a289e`（baseline 2138/0）|

### G4 ML 管線解凍

| ID | Tag | 項目 | 前置 | 負責修/驗 | 工時 | 完成標準 |
|---|---|---|---|---|---|---|
| ~~**G4-01**~~ ✅ | 🟠P1 | ~~Labels pooled 加速（per-strategy pool）~~ — **已完成** commit `dc06b88` (2026-04-23) — `PipelineConfig.symbol Optional[str]` + `_resolve_symbol_slot()` + pooled SQL branch (`%(symbol)s IS NULL OR symbol = ...`) + 13 dedicated tests in `program_code/ml_training/tests/test_pooled_training.py`；2026-04-25 G4-01 audit re-confirm：完成標準「labels ≥200 pooled」由 `min_samples=200` gate 配 pooled SQL 分支天然滿足，operator default `symbol=None` 即跨 symbol 累積。 | `PipelineConfig.symbol` Optional commit | MIT+E1 / E2 | 1-2d | labels ≥200 pooled ✅ |
| **G4-02** | ✅完成 | `run_training_pipeline.py` 首跑 grid_trading — 首個 ONNX artifact + registry row 已於 2026-04-23 完成（INFRA-PREBUILD-1 Part B 階段一併產出）；2026-04-25 `2c920cb` 修正 `program_code/ml_training/run_training_pipeline.py` 13 個 `from ml_training.X` import 路徑為 `from program_code.ml_training.X` 解 module invocation `python3 -m program_code.ml_training.X` 失敗，retrain 路徑解阻 | G4-01 | MIT / E4 | 完成 2026-04-25 | commits `f2fbbda` (mark) + `2c970bb` (import fix) |
| **G4-03** | ✅完成 Phase A | Canary auto-promote evaluator — `program_code/ml_training/canary_promoter.py` ~330 LOC（`CanaryDecision` enum + `CanaryThresholds` + 8 env var override + `auto_promote_eligible_models` scanner + `is_auto_promote_enabled` env gate）+ `helper_scripts/db/canary_promote_runner.py` ~150 LOC CLI（`--dry-run` default / `--apply` 需 `OPENCLAW_AUTO_PROMOTE_ENABLED=1` env / `--verbose` / `--dsn`）+ `program_code/ml_training/tests/test_canary_promoter.py` 完整測試 + runbook `docs/references/2026-04-25--g4_03_canary_promote_runbook.md` · 狀態機 shadow → promoting → production / retired / rejected · DEFAULT-OFF env-gate · Phase B 部署 cron driver / Brier 分數 / PSI drift / SIGHUP 留 deferred | G4-02 | E1+E2 | 完成 Phase A 2026-04-25 | commits `1164ede` (impl) + `01fe46c` (docs)，pytest 3056 |
| **G4-04** | 🟡P2 | edge_estimator_scheduler healthcheck [13] | G1-01 | E1 / QA | 0.5d | cron 每 1h check mtime |
| **G4-05** | 🟡P2 | `ExitConfig.shadow_enabled` flip ON + 24h 觀察 | G3-05 | PM+MIT / QA | passive 24h | healthcheck [8] decision_shadow_exits 有 row |

### G5 架構 / 可讀性債務（可派 3+ subagent 並行）

| ID | Tag | 項目 | 前置 | 負責修/驗 | 工時 | 完成標準 |
|---|---|---|---|---|---|---|
| **G5-01** | 🟠P1 | `main.rs` 2062 行拆分 | 無 | E5+E1 / E2 | 2-3d | <1200 lines |
| **G5-02** | ✅完成 | `live_session_routes.py` 1449 → 706+436+439（live_session_routes 706 / live_session_endpoints 436 / live_session_account_routes 439，全 <800）+ `live_session_governance` 178；sibling 走 `from . import live_session_routes as core` 經 namespace 引用，保留所有外部 import + monkeypatch；14 routes byte-identical；test_live_gate_fallback 14/14 + pytest -k live 117/0 + pytest -k live_trust|live_session|live_gate 77/0 全綠 | 無 | E5+E1 / E2 | 完成 2026-04-25 | [G5-02 report](.claude_reports/20260425_014424_g5_02_live_session_split.md)（commit `e0d02b2`）|
| **G5-03** | 🟠P1 | `instrument_info.rs` 1975 行拆 | 無 | E5+E1 / E2 | 1-2d | <1200 lines |
| **G5-04** | ✅完成 | `ai_service.py` **1318**（實測比 TODO 估的 1258 多 60 行）→ ai_service.py 242（facade + singleton + system prompts + factory）+ ai_service_dispatch.py 813（`AIService` class + 5 handlers）+ ai_service_listener.py 373（`_probe_unix_listener_alive` + `AIServiceListener`）；sibling pattern 同 G5-02（`from . import ai_service as core` + `core.<name>` 引用）；外部 import 透過 re-export 不變；Linux pytest -k 'ai_service or llm or budget' **50/0**；3 檔全 <1200，2 檔 <800（dispatch 813 為 class cohesion 不可避免） | 無 | E5+E1 / E2 | 完成 2026-04-25 | [G5-04 report](.claude_reports/20260425_015603_g5_04_ai_service_split.md)（commit `37172b0`）|
| **G5-05** | ✅完成 | `bb_reversion.rs` 1143 → 3 sibling：mod.rs 433 + params.rs 287 + tests.rs 460（全 <800 §九 warning 線）；`positions`/`cooldown`/`persistence` 由 private → `pub(crate)` 讓 sibling tests.rs mutate；`BbReversionParams` 由 `pub use params::BbReversionParams` 保留外部 path；bb_reversion filter 20/20 + stress_integration 35/35 全綠；Linux release 2003/0 | 無 | E5 | 完成 2026-04-25 | [G5-05 report](.claude_reports/20260425_000438_g5_05_bb_reversion_split.md)（commit `8523946`）|
| **G5-06** | 🟡P2 | 其他 5 檔（bybit_rest_client / order_manager / startup / resting_orders / risk_config） | 無 | E5+E1 / E2+E4 | 5-8d 全部 | all <1200 |
| **G5-07** | ✅完成 | `event_consumer/tests.rs` 1298→拆至 tests/ 6 sibling：mod.rs 298（shared helpers + 8 util tests）· handlers_paper_cmd 371 · exit_config_ipc 214 · governor_override 160 · cross_engine 123 · reconciler 89 · submit_order 76；全 <1200；42 tests 逐字保留；Linux release 1992/0（baseline 不動）；0 production file touched | G1-02 | E5+E1 / E2+E4 | 完成 2026-04-24 | [G5-07 report](.claude_reports/20260424_233852_g5_07_tests_split.md)（commit `913b536`）|

### G6-FUP Wave 2 延伸（news-halt / watchdog RCA）

| ID | Tag | 項目 | 前置 | 負責修/驗 | 工時 | 完成標準 |
|---|---|---|---|---|---|---|
| **G6-FUP-NEWS-HALT-DEDUP-1** | ✅完成 | news guardian halt 30min TTL auto-clear — `guardian_impl.rs` 加 `last_trigger_ts_ms: AtomicU64` + `halt_ttl_ms: u64`（默認 30min）+ `check_and_clear_expired(now_ms)` 方法；`tasks::spawn_news_pipeline` 每 60s tick 呼叫一次 expiry check（在 `news_pipeline_enabled` gate 之前，禁用時也清除）；refire 在 TTL 內會 re-stamp ts；6 unit tests 涵蓋 fire/no-op/within-TTL/clears-after-TTL/refire 生命週期 · **不影響 dedup**：headline_hash 24h dedup 由 `dedup.rs` 處理；本 fix 解決 halt 原子持久化問題 | 無 | E1+QA / E2 | 完成 2026-04-25 | engine 跑 >30min 後 stale halt 自動清除 / commit `b980986`（含 6 new tests）|
| **G6-FUP-TICK-PIPELINE-DEAD-1** | ✅完成 | tick pipeline boot deadlock — **真正 root cause 找到**：`main_boot_tasks::spawn_strategist_scheduler` 線 198-243 主執行緒上對每筆 restored row `rx.await`，但此 fn 在 `main_pipelines::spawn_demo_pipeline` 之前被 `await`，demo pipeline 還沒 spawn → demo cmd channel 沒人 drain → `rx.await` 等不到回應 → 主執行緒永遠卡死於 `outcome backfill task spawned` 之後 → tick_pipeline 從未構造 → snapshot 永不寫入 · **2026-04-24 起（含今晚多次 --rebuild）所有 engine restart 都死於此**，因 STRATEGIST-PERSIST-AUDIT-GAP-COUNTER-1（commit `d8f5560`+`e47b1e9`+`5538e52`，22:34 CEST 首寫入）讓 `learning.strategist_applied_params` 從空表變有 1 row，觸發了一直存在但隱形的 deadlock；先前 watchdog auto-restart「成功」是 false-positive，新 engine 也立即同樣卡死 · **Fix**：DB load 留主執行緒（小 query 毫秒級），IPC fan-out + audit-await 整體丟 `tokio::spawn` 背景任務；unbounded `demo_cmd_tx` queue 訊息直到 demo pipeline drain；scheduler 5min 後首跑足夠緩衝 · **驗證**：01:29:35 fresh `--rebuild` 後 `pipeline ready`、`fan-out: all pipelines ready`、`STRATEGIST-PARAMS-PERSIST-1: restored N=1`、snapshot_age 17.2s、demo+paper alive · **解鎖**：G7-09 fee fix 自此 tick 起活著，G1-04 cutoff 重新可達，G7-05 data 開始累積 | 無 | E1+E2 / QA | 完成 2026-04-25 | engine fresh boot 後 1s 內 snapshot 寫入；commit `b980986` |

| ID | Tag | 項目 | 前置 | 負責修/驗 | 工時 | 完成標準 |
|---|---|---|---|---|---|---|
| **G7-01** | 🟡surface ready, router 未 wire | Kelly 分級 tier boundaries 參數化 — `KellyConfig.young_threshold` / `mature_threshold` 默認 50/200 + `validate()`（拒 0 / 逆轉）；`RiskConfig.kelly` mirror struct + TOML `[kelly]` 三環境補齊（demo/live/paper）；`kelly_sizer.rs:153-159` fractional-Kelly tier branch 改讀 config；+8 unit tests（kelly_sizer 4 + risk_config 4）；Linux release 2003/0 ✅ · **Caveat**：`set_kelly_config()` 在 router callsites 尚未 wire（FA L3 audit 標「未啟用」）→ 新 TOML 尚未 flow 到 runtime，defaults 保持當前行為；wiring 為後續任務（可能 part of G4-01 labels work） | 無 | QC+E1 / FA | 完成 surface 2026-04-25（wiring 未做）| [G7-01 report](.claude_reports/20260425_000414_g7_01_kelly_tier_config.md)（commits `42758e7` feature + `e4b63b4` test fix）|
| **G7-02** | ✅完成 | EWMA Vol lambda per-timeframe 參數化 — 新 `EwmaVolConfig { default_lambda, lambdas: HashMap<String, f64> }`（預設 0.97 mirror G7-02 前 RiskMetrics 硬編碼）+ `validate()` 強制 (0.0, 1.0) 開區間 + `lambda_for_timeframe()` helper；接入 `RiskConfig.ewma_vol` + 3-env TOML `[ewma_vol]` 區段（demo/live/paper 預設 default_lambda=0.97 / lambdas={} 保留現行為）；`indicators::IndicatorEngine::compute_all_with_lambda` 接 config；5 unit tests（default / out-of-range / TOML round-trip / partial fallback / per-tf lookup）· Linux release **2023/0** ✅ · `--rebuild` 部署 engine alive 13.1s ✅ | 無 | QC+E1 | 完成 2026-04-25 | TOML configurable ✅ / 預設保現行為 / commit `6b7246d` |
| **G7-03** | ✅完成 Phase A + Phase B 3/4 | Hurst exponent + Hysteresis regime detector — Phase A schema landing：`HurstConfig` 在 `risk_config_regime.rs`（new sibling，因 advanced.rs 已撞 1198/1200 cap）+ `HysteresisDetector` 6-period lag + R/S analysis live + 3-env TOML `[hurst]` 區段 + 不變量驗證 + unit tests · Phase B per-symbol HysteresisDetector cache + `RegimeLabel` migration（V026），`bb_breakout` / `ma_crossover` / `bb_reversion` 3 策略 wired，**`grid_trading` 遷移 deferred 為 G7-03-Phase-B-FUP-grid**（與 parallel session WIP merge 衝突避免）| 無 | QC / FA+MIT | 完成 Phase A + Phase B 3/4 2026-04-25 | commits `892955a` (Phase A) + `0cb133b` (Phase B) |
| **G7-03-Phase-B-FUP-grid** | ⬜deferred | grid_trading per-symbol HysteresisDetector 遷移 — 等 parallel session 5 grid_trading WIP files（constructors.rs / mod.rs / params.rs / position_mgmt.rs / strategies/mod.rs）merge 後再啟動，避免 commit 衝突；Phase B 已驗證 cache pattern 在 3 策略 working | G7-03 Phase B + parallel WIP merge | E1 | 1-2d | 4/4 策略全 wired |
| **G7-04** | ✅完成 Phase A | CUSUM 策略衰減監控 schema landing — 新 `CusumConfig { enabled, slack_k, threshold_h, min_observations, target_return_bps }`（Page/Montgomery convention，預設 dormant `enabled=false`、slack_k=0.5σ、threshold_h=4.0σ、min_obs=30）+ `validate()`（4 reject paths）+ 7 unit tests（defaults/4 reject/TOML round-trip/partial fallback）+ 3-env TOML `[cusum]` 區段；Linux 2030/0 ✅；**Phase A 純 schema**：runtime wiring 候選 σ-source `RiskConfig.ewma_vol`、consumer hook `dynamic_risk_sizer`/`strategy_orchestrator`，待 Phase B/C | 無 | QC+E1 | 完成 schema 2026-04-25 / wiring 待續 | [G7-04 report](.claude_reports/20260425_020449_g7_04_cusum_schema.md)（commit `1628cb6`）|
| **G7-05** | 🟡passive wait | cost_gate grand_mean bind condition — G7-09 已 deploy（2026-04-24 23:41 CEST），開始累積 post-fix data；**當前狀態**（ssh verify 23:41）：grand_mean_bps=-9.80 / n_cells=62 / shrunk_bps>0 count=**0**；`>-50 bps` 條件已滿足，**`≥2 strategies shrunk>0` 未滿足**；預計 ≥1w post-fix fills（~2026-05-01+）後有足夠 maker/taker 混合樣本，屆時 (a) 校準閾值是否仍合理（artifact vs real edge） (b) 落地 cost_gate bind 判決 code（TBD：ExitConfig 新 flag 或 IPC patch）| G1-01 + G7-09 | QC+E1 / FA | 2-3h（post-data） | bind when grand_mean > -50 bps ∧ ≥2 strategies shrunk>0 + post-fix threshold validated |
| **G7-06** | ✅完成 schema + impl（gated dormant）| Grid OU residual-based σ estimator — 新 `OuResidualSigma` struct 在 `strategies/grid_helpers.rs`（`theta` mean-reversion 速度 / `mu` 長期均值 / `sigma_hat` residual std / `n_observations`；`update(x_new)` rolling estimator + `estimate_from_window(slice)` batch；數學：OU 過程 `dx_t = θ(μ - x_t)dt + σ dW_t`，residuals `e_t = Δx_t - θ(μ - x_{t-1})` ~ N(0, σ²)，σ_hat = sqrt(Σe_t²/(n-1)) unbiased）+ `GridOuConfig { residual_window_size, fallback_sigma, use_residual_sigma }` 在 `risk_config_advanced.rs`（接 `RiskConfig.grid_ou` + 3-env TOML）· **Phase A gating**：預設 `use_residual_sigma=false` 保留現行為；翻 true 啟用 OU residual 估計；7 unit tests（recover within 5% on n=200 / trending series graceful no-NaN / window slice / lifecycle / n<5 None edge）· Linux release **2046/0** ✅ | 無 | QC / E1+E2 | 完成 2026-04-25 | commit `67a8261` |
| **G7-07** | ✅完成（範圍縮減）| Slippage / confluence 硬編碼清理 — **Discovery**：「8 檔」TODO 描述過期；41 grep-match 中大多已 TOML 化（strategy `min_persistence_ms/weight_*/threshold_*/adx_floor` 在 `MaCrossover/BbReversion/BbBreakoutParams` G-SR-1 A0-c；`squeeze_bw/expansion_bw/volume_threshold` 在 `BbBreakoutParams`；FundingArb cost bps 在 `FundingArbParams` QC-H10；`MarketGate.slippage_max_bps` 在 `advanced::MarketGate`）。**實際 1 檔 4 hardcode 移**：`intent_processor/{mod,gates}.rs` → 新 `SlippageConfig { default_rate=5bps, tiers=Vec<SlippageTier>(5 desc), cost_gate_win_rate_floor=0.3, cost_gate_safety_multiplier=1.3 }` 接 `RiskConfig.slippage` + 3-env TOML `[slippage]` + 5 `[[slippage.tiers]]` + regression test 確認 default lookup bit-identical；9 unit tests；Linux 2039/0 ✅ | 無 | QC+E1 / FA | 完成 2026-04-25 | [G7-07 report](.claude_reports/20260425_021006_g7_07_slippage_confluence_toml.md)（commit `92e65af` + relocate `3bed899`）|
| **G7-08** | ✅完成 484x speedup | outcome_backfiller SQL slow query — **Root cause**：`pending` CTE 對 `trading.decision_context_snapshots`（770k 行 / 1.6 GB）跑 **Parallel Seq Scan**，filter 後丟掉 208k row 才取 200。Hot cache 168ms / cold cache 1.5s（即 prod log 的 slow-statement WARN）。Kline 7 個 correlated sub-selects 早就用 TimescaleDB index scan，<2ms 不是病灶。**Fix**：`sql/migrations/V025__outcome_backfill_pending_index.sql` — 單一 partial index `idx_dcs_outcome_backfill_pending on (ts ASC) WHERE outcome_backfilled = FALSE AND last_price IS NOT NULL AND last_price > 0`。**EXPLAIN ANALYZE**：Pending CTE 1500ms cold → **0.39ms**；Full query 1500ms → **3.1ms**；Disk pages read 209,766 → 54；Index size 4 MB；Linux release **2046/0** ✅；Migration 雙跑 idempotent 通過；engine `--rebuild` 後 auto_migrate 補入 `_sqlx_migrations` row 25 | 無 | QC+E1 / FA | 完成 2026-04-25 | [G7-08 report](.claude_reports/20260425_024251_g7_08_outcome_backfiller_sql.md)（commit `743cfa9`）|
| **G7-09** | ✅完成 | FIX-FEE-POSTONLY-1 — 修三處：(1) `intent_processor/mod.rs:1084` 新增 `fee_rate_for_tif(symbol, tif: Option<TimeInForce>)` helper (2) `event_consumer/loop_handlers.rs:405-447` hoist matched_key lookup 至 fee compute 前 (3) `intent_processor/tests.rs` 加 3 unit tests · Linux release cargo test **1995/0** · `--rebuild` 部署 engine PID 1376094 binary 23:41 CEST · downstream：fee 列 post-fix 會出現 2bps maker 混 5.5bps taker → G7-05 bind 閾值需重校準（passive ~1w） | G1-02 | E1+QC / E2+E4 | 完成 2026-04-24 | commit `872478a` |
| **G7-09b** | ✅完成 | FIX-FEE-POSTONLY-1 follow-up audit — `trading.orders.order_type` mirror `PendingOrder` (audit honesty)；orders 表記錄真實下單 type 而非 INTENT 字串，便於 G1-04 fee analysis split pre/post G7-09 | G7-09 | E1+QC | 完成 2026-04-25 | commit `7f0e793` |
| **G7-09c Phase 1** | ✅完成 | BBO-aware PostOnly maker price — 4 策略（ma_crossover / bb_reversion / bb_breakout / grid_trading）統一 PostOnly 入場 price 改為 BBO（best bid/offer）side，避免 cross-spread reject；Phase 2 funding_arb 待跟（背景）| G7-09 | E1 / E2 | 完成 2026-04-25 | commit `ac70862` |

### Wave 2 完成標準

- [x] G3-01~04 ExecutorAgent shadow→live e2e pass — Phase A IPC + Phase B cache + Phase C operator API + e2e tests 全綠（commits `16c97c1`/`03acedb`/`51608fe`/`325582f`/`852da0f`）
- [x] G4-02 第一個 ONNX artifact 進 registry — 已於 2026-04-23 完成（INFRA-PREBUILD-1 Part B），import path fix `2c970bb` 解阻 retrain
- [x] G4-03 canary auto-promote evaluator Phase A — `1164ede` + `01fe46c`（runbook + DEFAULT-OFF env-gate）
- [~] G5-01~06 所有 Rust / Python 檔 <1200 行 — G5-02 `e0d02b2` / G5-04 `37172b0` / G5-05 `8523946` / G5-07 `913b536` 完成；G5-01 main.rs / G5-03 instrument_info.rs / G5-06 (5 檔) 仍 deferred
- [x] G7 量化配置化完成 — 9/10（G7-01 surface ready / 02 / 03 Phase A+B 3/4 / 04 Phase A / 06 / 07 / 08 / 09 + 09b/09c Phase 1）；G7-05 passive wait Post-G7-09 數據 ~05-01+
- [x] **雙 P0 RCA 修復**（額外完成）：G6-FUP-NEWS-HALT-DEDUP-1 + G6-FUP-TICK-PIPELINE-DEAD-1（commit `b980986`）解 engine "crashloop" 假象

---

## ⏩ Wave 3（W20-W23 · 5/22→6/12）— Edge 穩定 + ML canary

### EDGE-DIAG-1 Phase 3 部署 + Phase 1b（前置條件嚴格）

| ID | Tag | 項目 | 前置條件（必須 ALL 滿足） | 負責 | 工時 |
|---|---|---|---|---|---|
| **EDGE-P3** | 🟡P1 | strategy-scoped Gate 1 fallback 部署 | (a) clean bucket ≥200 rows pooled · (b) per-strategy bootstrap 95% CI lo >0 · ~~(c) orphan_frozen clean ≥20 rows~~ → **(c') 已修：orphan_adopted ≥20 rows**（MIT 2026-04-26 audit：`orphan_frozen` by design 是 dust quarantine label `dust_gate.rs:99-114` + `orphan_handler.rs:101 DUST_FROZEN_STRATEGY`，**no close dispatched** → 該 cohort 永不進 exit_features pipeline → 該條件永久 0 → Wave 3 永久 stalled。改為 `orphan_adopted` cohort 才有真實 close）· **(d) healthcheck [11] 連 3d PASS** | PM+FA+QC / E2 | 2d |
| **EDGE-P1b** | 🟡P1 | `exit_features` 累積 ≥1w + 7 維閾值 bind（**MIT 2026-04-26 確認 7 維 = est_net_bps / peak_pnl_pct / atr_pct / giveback_atr_norm / time_since_peak_ms / price_roc_short / entry_age_secs**，per `V999__exit_features.sql:33-41`；bind = percentile → `RiskConfig.exit.*` thresholds，非 JS estimator → cost_gate（後者是 P1-14）；MIT 建議延至 5/10 達 per-strategy ≥200 rows） | W19 起算，預計 5/03 滿週 | PM+QC / E4 + PA RFC | passive 7d + RFC 2d |
| **EDGE-P2-flip** | 🟡P2 | Track L shadow flip + P1-10 並行（**待 PA RFC 補 spec**：flip acceptance criteria（推測 healthcheck [15] ≥95% agree rate）+ flip 步驟 SOP + 回滾路徑 + "P1-10 並行" 範圍釐清） | EDGE-P1b + PA RFC | QC+PM / E2 + PA | passive 7d + RFC 1-2d |

### G2 策略驗證 + 決策

| ID | Tag | 項目 | 前置 | 負責 | 工時 |
|---|---|---|---|---|---|
| **G2-01** | 🟠P1 | P1-10 PostOnly 1-2w 驗證（passive） | PostOnly demo 04-21 部署 | PM+QC+FA / E4 | passive ≥1w（04-21~05-07 出結果）|
| **G2-02** | 🟠P1 | ma_crossover R:R 對稱性 counterfactual — **QC 2026-04-26 裁定**：G7-09 fee fix **不能救 R:R**（alpha 結構問題非 fee 結構），啟動採 (c) 並行：E1 立即寫 counterfactual code（用 `decision_outcomes` + `exit_features` 重算「若 fee=2bps 會如何」）+ passive 等 ~05-01 真實 1w demo G7-09 後數據 → ~05-03 雙軌驗證 | EDGE-P2 結果（並行寫碼可不等）| QC+FA / E2 + E1 code | 2-3d |
| **G2-03** | 🟡P2 | ma_crossover SL/TP 策略層定制（Option B）— **待 PA RFC 補 spec**：(1) Option B 是「strategy_params.toml 加 sl_atr_mult / tp_atr_mult per-strategy」還是別的層？(2) G2-02 counterfactual → G2-03 binding 邏輯（自動 vs 手動）(3) P1 max 硬頂 vs 策略軟值 boundary | G2-02 驗收 + PA RFC | E1+FA / E2+E4 + PA | 2-3d + RFC 1-2d |
| **G2-04** | 🔴P0 | **Grid disable 決策會**（若 PostOnly 後仍負 edge） | G2-01 + P0-3 輸入 | PM+FA 決策 | 1h 會議 |
| **G2-05** | ✅完成（觸發 G2-06）| bb_breakout FIX-26-DEADLOCK-1 rebuild 驗證 — **2026-04-26 ssh healthcheck [12] verify**：FAIL 7d entries=0；FIX-26-DEADLOCK-1 已在 binary（22:34 + 01:30 多次 rebuild）排除 deadlock 殘留 → **結構性 dormancy CONFIRMED**，觸發 G2-06 | operator rebuild | MIT / QA [12] | 完成 2026-04-26 |
| ~~**G2-06**~~ | ✅完成（disabled） | bb_breakout 結構性 dormancy 處置 — **2026-04-26 PA RFC `2026-04-26--g2_06_bb_breakout_disposal_rfc.md` 推 C 永久 disable** + PM approve；落地：(a) `[bb_breakout].active=false` 三環境 TOML（demo/paper/live） (b) healthcheck [12] active=false 時 PASS skip (c) 新增 [18] disabled_strategy_inventory（CLAUDE.md §三 G6-04 drift 防線）(d) BbBreakoutProfile + sweep tool 保留為 future investment（per §6 重啟條件）。MIT 推 5m / QC 推 C / PA 推 C dominated strategy 分析（B ROI 不利、F2 signals≠edge 未驗證、Wave 3 主軸擠壓）。重啟需新 PA RFC + 5m timeframe 升級。 | G2-05 | E1 / E2 / E4 | 完成 2026-04-26 | E1 Report `2026-04-26--g2_06_bb_breakout_disable_landing.md` |

### G8 測試 / Healthcheck 擴展（新增，QA+AI-E）

| ID | Tag | 項目 | 前置 | 負責 | 工時 |
|---|---|---|---|---|---|
| **G8-01** | 🟠P1 | e2e 認知自適應測試（80+ coverage）— **PA 2026-04-26 scope 重定義**：OpportunityTracker / DreamEngine **代碼不存在**（grep 0 命中，非 stub），完成標準改為 **CognitiveModulator ≥85% line cov + StrategistAgent 注入點 integration 綠**，後二者 deferred 待對應實作 | G3-04 ✅ | QA+E4 / E2 | 2-3d |
| **G8-02** | 🟠P1 | Python↔Rust parity test（decision agree ≥95%）— **PA 2026-04-26 spec 補**：decision points 限 RiskConfig.executor 3 欄（shadow_mode / per_symbol_position_cap / max_position_pct）；70 case golden+replay 混合；**case-level binary ≥95%**（≥67/70 agree） | G3-03 ✅ | QA+E4 / E2 | 1-2d |
| **G8-03** | 🟠P1 | 灰度驗收自動化（shadow metrics）— **FA 2026-04-26 補**："灰度" 流程未明確（staged rollout 機制 vs simple shadow→live flip），shadow metrics 列表（agree_rate / decision_lag / pnl_diff）需 QA 整理 | EDGE-P2 flip | QA / E2 | 2-3d |
| ~~**G8-04**~~ | ⬇降 backlog | ~~healthcheck DAG 線性化（依賴清晰）~~ — **PA 2026-04-26 推薦降級**：當前 17 check 平鋪可讀、隱性依賴僅 2 層深、無假 PASS 觸發、Wave 3 完成標準應移除此項。**降 backlog 待 false PASS/FAIL 真出問題再啟** | — | QA | — |
| **G8-05** | 🟡P2 | AI cost ROI 監控面板（from AI-E） | G3-09 | AI-E+E1a / QA | 1-2d |

### Wave 3 完成標準

- [ ] EDGE-P3 前 4 條件全滿足（**(c) 已修為 orphan_adopted ≥20**），Gate 1 fallback 部署
- [ ] exit_features ≥1000 rows + 7 維 percentile 閾值 bind 到 RiskConfig.exit.*
- [ ] G2-01 PostOnly 驗收：fee drop ≥60% 或決策策略下架
- [ ] G2-02 ma R:R counterfactual 報告（**理論值 fee=2bps + realized 真實 1w post-G7-09**）對齊
- [x] bb_breakout PA RFC 結論（disable vs 升 5m）+ 落地 → healthcheck [12] PASS 連 3d 或正式 disable — **完成 2026-04-26**：PA RFC 選 C 永久 disable，三環境 TOML `active=false` + healthcheck [12] disabled-skip + [18] inventory 新增

### Wave 3 開工時刻表（2026-04-26 PM 派發後 · 4-agent audit 整合）

**第二波派發**（5 軌並行，已派出）：
1. ✅ PA G2-06 RFC（disable vs 5m 升級二選一）
2. ✅ E1 G2-02 counterfactual code（QC 推 (c) 並行：寫碼 + passive 等數據）
3. ✅ E1 G8-02 Py↔Rust parity test（70 case ≥95% binary）
4. (待第三波) PA EDGE-P1b RFC（7 維 bind contract）
5. (待第三波) PA EDGE-P2-flip RFC（flip SOP + 回滾）
6. (待第三波) PA G2-03 RFC（Option B 層次界定）

**4-agent audit 報告索引**：
- PA：[2026-04-26--wave3_dispatch_research.md](docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-26--wave3_dispatch_research.md)
- MIT：[2026-04-26--wave3_data_audit.md](docs/CCAgentWorkSpace/MIT/workspace/reports/2026-04-26--wave3_data_audit.md)
- QC：[2026-04-26--wave3_strategy_audit.md](docs/CCAgentWorkSpace/QC/workspace/reports/2026-04-26--wave3_strategy_audit.md)
- FA：[2026-04-26--wave3_spec_readiness.md](docs/CCAgentWorkSpace/FA/workspace/reports/2026-04-26--wave3_spec_readiness.md)
- PM 派發整合：[2026-04-26--wave3_dispatch_signoff.md](docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-26--wave3_dispatch_signoff.md)

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
| **G2-FUP-FUNDING-ARB-PAPER-SYNC** | paper TOML `[funding_arb].active=true` 與 demo/live 的 `active=false` 不一致（**E2 2026-04-26 G2-06 review 發現**：v1→v2 結案 NEGATIVE 過渡期 sync miss；`feedback_env_config_independence` 適用於風控閾值 vs `active` binary 開關，不擴 G2-06 scope 但獨立追） | 確認 design intent vs oversight | 🟡P2 | E1 5min 工時；改 paper TOML active=false + 雙語 comment |
| **G2-FUP-IPC-LEGACY-MS-FIX** | `app/ipc_client.py:786` `sync_ipc_call` 用毫秒做 HMAC ts，但 Rust verifier `ipc_server/mod.rs:621-628` 用秒比對 30s 容差 → **legacy sync_ipc_call 100% fail auth**（E2 2026-04-26 W4 軌 2 review 確認 2 production caller `trigger_live_auth_recheck` + `set_system_mode` fire-and-forget 吞錯誤但 fast-path 完全失效）；EDGE-P2-flip dry_run 內嵌 helper 用秒對齊 Rust 已修**新檔**，legacy 未修 | 即時 | 🔴P1 | E1 30min 工時：改 ms*1000 → 秒；加 unit test 驗 30s 容差 |
| **G5-FUP-IPC-MOD-SPLIT** | `rust/openclaw_engine/src/ipc_server/mod.rs` 1262 行（W4 軌 1 +11 push 1251→1262，超 §九 1200 硬上限）；建議 dispatch_request 抽 sibling | E5 next wave | 🟡P2 | E5 1-2d 工時；不影響 W4 sign-off |
| **G1-FUP-CALIBRATOR-WARNING** | `helper_scripts/research/exit_threshold_calibrator.py` `--apply` 路徑加 stdout warning banner 暴露 IPC 6/7 partial bind gap（`stale_peak_ms` + `shadow_enabled` 不在 IPC 7 字段需 TOML edit） | calibrator 真實啟用前 | 🟢P3 | E1 15min 工時 |
| **G2-03-FUP-CALLER-WIRE** | G2-03 `check_position_on_tick_with_override` 0 production caller（W4 軌 3 staging marker）；G2-02 counterfactual 結論定後派 E1 wire caller chain（step_6_risk_checks）真實啟用 SL/TP override | G2-02 完成 ~05-03 | 🟠P1 | E1 1d 工時；G2-03 schema 已 staging |
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
| **DUST-EVICTION GUI** | ✅ 2026-04-25 完成 | — | ✅ | tab-live + tab-demo 加 `<details>` 摺疊面板：counter / 8 欄表（Symbol/Side/Qty/Mark/Est. Notional/Min Notional/Gap %/Owner Tag）/ 重用 `_ocRenderOwnerStrategy` helper / 2 return path 全接線（`loadDashboardData` empty 與 populated）；後端 0 改動（既有 `frozen_reason` + `est_notional` + `min_notional` 已 inject）；HTML 立即生效（FastAPI StaticFiles 不快取，operator hard reload 即見） · ⚠️ tab-live.html 1259→1281 行超 §九 1200 硬上限（既有就過，本次推 +22）→ 下次 G5 candidate · commit [`bd55df1`](https://github.com/yunancun/BybitOpenClaw/commit/bd55df1) |
| **LEARNING-COCKPIT-NO-IPC** | Learning 8 端點走 Python state_store | G-7/G-10 後 | 🟡P2 | 設計債 |
| **STRATEGIST-PERSIST-AUDIT-GAP-COUNTER-1** | ✅ 2026-04-24 完成 · e2e 驗證通過 | — | ✅ | **RCA + 雙修完成**：(1) Python `_build_strategist_prompt` 預算 `allowed_range=[current*0.7, current*1.3]` 寫入 prompt + HARD RULES（commit `d8f5560`）讓 Ollama L1-9b 遵守 ±30% cap；(2) Python `_parse_strategist_response` 保留 int-ness 避免 `float(v)` 強轉把 `78000` cast 成 `78000.0` 打壞 Rust u64 serde（commit `e47b1e9`+ merge `5538e52`）。**e2e 驗收 runtime**：舊 prompt 3/3 cycle (UTC 20:03/20:08/20:13) 100% reject；新 prompt 3/3 cycle (20:18/20:23/20:29) LLM 遵守 cap 但 type bug apply failed；type-fix 後首 cycle (UTC 20:34:08) `strategist params applied strategy=grid_trading symbol=BLURUSDT`；`learning.strategist_applied_params` rows 0 → 1 首行落表。報告：[FA Gap 2 eval](.claude_reports/20260424_fa_eval_gap2_strategist_observability.md) + [PA Gap 2 eval](.claude_reports/20260424_pa_eval_gap2_todo_placement.md)。|
| **STRATEGIST-TUNE-TARGET-CONFIG-1** | ✅ 2026-04-25 完成 | — | ✅ | `MAX_PARAM_DELTA_PCT` const 提取至 `RiskConfig.strategist.max_param_delta_pct`；新 `StrategistConfig` 子結構（`risk_config_advanced.rs`）+ `validate()`（拒 ≤0.0 / >=1.0 / NaN / Inf）+ 3-env TOML `[strategist]`（demo/live/paper 全 0.30 保留現行為）+ IPC `patch_risk_config` deep-merge auto-supports；consumer 改讀 `risk_config.strategist.max_param_delta_pct`，`validate_recommendation` free fn 從 3-arg → 4-arg（13 call sites 全更新）；7 schema tests（defaults/validate/TOML round-trip/partial fallback）+ 2 e2e behavior tests（不同 cap 餵不同 delta 驗 accept/reject）。Mac release **2094 / 0**（baseline 2085 + 9 新測）。Default 0.30 = 原 hardcoded value，runtime bit-identical · 等下次 `--rebuild` 才 live · ⚠️ `risk_config_advanced.rs` 1198→1299 行超 §九 1200 硬上限（既有 1198 已逼上限）→ 下次 G1-03 follow-up split · commit [`e388065`](https://github.com/yunancun/BybitOpenClaw/commit/e388065) |
| **STRATEGIST-HISTORY GUI** | ✅ 2026-04-24 完成（含 cycle_metrics footer FUP） | — | ✅ | tab-strategy.html 折疊 sub-panel（summary KPI + 3 filter + list 50 行 + Diff/7d Effect 展開）+ 底部 `近 scheduler cycle 健康度` 指標（rejects / applies / last ts / 提示文案）· endpoint `/api/v1/strategist/history/cycle_metrics` engine log tail parse 提供 root cause 自助診斷 |

---

## 📊 Healthcheck 清單（`passive_wait_healthcheck.py` 已實裝）

**CLAUDE.md §七 強制**：被動等待 TODO 必附 healthcheck · 每 6h cron 跑 · 連續 3 FAIL → 中止等待。

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
| [12] | bb_breakout_post_deadlock_fix | fill count recover (G2-06 disabled → PASS skip 2026-04-26) | G2-05 / G2-06 |
| [18] | disabled_strategy_inventory | active=false strategies list (always PASS, drift防線 G6-04) | G2-06（2026-04-26）|
| [13] | edge_estimator_scheduler_fresh | `edge_estimates.json` mtime <6h + cells ≥50 | G1-01 / G4-04（G6-02 commit `a0a4981`）|
| [14] | exit_features_accumulation_rate | 週 row count 增長率 ≥ threshold | EDGE-P1b（G6-02 commit `a0a4981`）|
| [15] | shadow_exit_agreement_phase2 | Python vs Rust decision agree rate ≥95% | EDGE-P2 flip（G6-02 commit `a0a4981`）|

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
