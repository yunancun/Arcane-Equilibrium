# OpenClaw TODO — 工作清單（v3 · 單一時間軸版）

**最後更新**：2026-04-25 02:35 CEST（Wave 2 batch 8：G3-03 Phase B Python ExecutorConfigCache + G7-06 Grid OU σ 完成；Linux baseline **2046/0**；engine alive）
**版本**：v3（Wave 線性版；廢除雙軌 P0-P4 章節，P0/P1/P2 降為每項 tag）
**舊版歸檔**：v2 `docs/archive/2026-04-24--todo_v2_dual_axis_snapshot.md`（458 行，Wave+P 雙軌）· v1 `docs/archive/2026-04-24--todo_v1_refactor_snapshot.md`（328 行）· v0 `docs/archive/2026-04-24--todo_snapshot_pre_refactor.md`（700 行）
**簽核**：PM Approved FIX-PLAN v2 → [Sign-off](docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-24--FixPlan_v2_PMApproval.md)
**基礎方案**：[FIX-PLAN v2](docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-24--4.24TodoAudit_FixPlan_v2.md) · [10-Agent audit 索引](docs/audits/2026-04-24--todo_refactor_audit.md)

**Engine**（採集 2026-04-25 01:30 CEST · 雙 P0 RCA fix 部署後 · ssh verify）：engine 復活 ✅ · `engine_alive: true` · snapshot_age **17.2s**（< 45s 閾值）· paper alive 18.3s / demo alive 17.2s · binary 2026-04-25 01:29 CEST 含 G7-09 + G6-FUP fixes · HEAD `b980986` · `pipeline ready — 5 strategies (ma_crossover, bb_reversion, bb_breakout, grid_trading + 1) on 5 symbols (BTCUSDT/ETHUSDT/SOLUSDT/XRPUSDT/DOGEUSDT) balance 951.94` · `fan-out: all pipelines ready, starting tick distribution` · `STRATEGIST-PARAMS-PERSIST-1 restored N=1 tuned params from DB` ✅（背景任務無阻主線） · G7-09 fill fee path 自此 tick 起活著，post-fix maker 2bps 列開始累積
**測試基準（2026-04-25）**：engine lib **2046 / 0 fail**（前述 + G7-06 7）· pytest **3013**（前 2996 + G3-03 Phase B 17 new executor cache tests）
**21d demo 時鐘**：起算 2026-04-16 22:16 → 解鎖 2026-05-07

---

## 🎯 此刻該做什麼（2026-04-24 23:41 CEST · Wave 2 第一批 deploy 後）

**Wave 1 進度**：10/11 完成；剩 G1-04 P1 背景（依賴 PostOnly demo 累積 + **G7-09 已 deploy** 需 ~1w 後 compute）。

**Wave 2 進度**：14/若干 完成（前述 12 + G3-03 Phase B ✅ + G7-06 ✅）；G7-05 blocked on data（~05-01+）；G3-04 / G3-05~10 / G4-01~03 / G7-03/08 未開工。G3-02 Phase C (operator IPC flip + auth) 待 G3-04 e2e 通過後解鎖。

**本週 Top 4**（按順序）：

1. **✅ Wave 2 三合一 deploy（2026-04-24 23:41 CEST）**
   - G5-07 `913b536`：event_consumer/tests.rs 1298→tests/ 6 sibling，最大 371（全 <1200）
   - G3-01 `4d24f48`：ExecutorAgent ConfigStore + IPC RFC 755 行（PA sub-agent）
   - G7-09 `872478a`：FIX-FEE-POSTONLY-1，`loop_handlers.rs:405-447` hoist matched_key，新增 `fee_rate_for_tif(symbol, tif)`，3 unit tests（PostOnly=maker / GTC=taker / None=taker race safety）
   - Linux release cargo test **1995/0**（baseline 1992 + G7-09 3 tests）
   - `--rebuild` 部署 engine PID 1376094 / binary 23:41 / WS demo auth success / 4 topics subscribed

2. **🟡 G7-05 cost_gate grand_mean bind — blocked on post-G7-09 data accumulation**
   - 當前 snapshot（ssh verify 23:41 CEST）：grand_mean_bps=**-9.80** · n_cells=62 · **shrunk_bps > 0 count = 0**
   - `>-50 bps` 條件已滿足（-9.80 > -50）；`≥2 strategies shrunk>0` **未滿足**（0/62）
   - Post-G7-09 預期：fee 列由全 taker 5.5bps → 混合（PostOnly maker 2bps + Market/GTC taker 5.5bps）→ net edge 上升 → 部分策略 shrunk_bps 可能跨 0
   - 需等 ≥1w post-fix demo fills（~2026-05-01+）取真實分布後再校準閾值 + 接活 cost_gate bind 判決
   - **不另派 sub-agent**：要 passive 觀察 + 後續 commit

3. **🟡 G1-04 fee drag / R:R baseline — G7-09 已 deploy，繼續累積等 ~04-28+**
   - Post-G7-09 fee 列自 23:41 CEST 起開始出現 maker 2bps（觀察中）
   - ~04-28 滿 1w 時 compute：fee drop % + R:R per-strategy delta + shrunk_bps movements

4. **⚪ Wave 2 後續（可派 sub-agent）**
   - G3-02/03/04 ExecutorAgent shadow→live toggle 實裝 + Rust IPC handler + e2e test（前置 G3-01 RFC ✅）
   - G5-02/04/05 剩餘拆分（live_session_routes.py 1449 / ai_service.py 1258 / bb_reversion.rs 1143）
   - G7-01/02/03/04 量化配置化（Kelly / EWMA / Hurst / CUSUM）
   - G4-01 Labels pooled 加速（等 PipelineConfig.symbol Optional commit）

**並行可派 sub-agent**：G3-02 實裝（需 E1+PA 鏈，主 session 啟動）· G5-02/G5-04 Python 拆（獨立軌道）· G7-01~04 量化並行

**⚠️ Engine "crashloop" 解密（2026-04-24 23:55 CEST）**：不是 crash 是 news guardian halt 持久化 + watchdog false-positive。`guardian_impl.rs:84` store session_halted=true 後無自動 reset 路徑；同一個 headline_hash `8ce179191752ac22` 每分鐘被 news pipeline re-fire，engine 持續 halt，snapshot 不更新，watchdog `snapshot_age > 45s` 判 crash → auto-restart 新 engine → 同一 headline 又 halt → 死循環。**修復方向**（G6-FUP-NEWS-HALT-DEDUP 列入 Wave 2 G6，見下表）：(a) news pipeline dedup by headline_hash — 同一 headline 只 fire 一次 halt (b) halt TTL 或 stale-headline auto-clear (c) watchdog 改判「session_halted=true 時 snapshot 不更新是預期行為」 · **不影響 G7-09 部署**：binary 含 G7-09 代碼，halt 清除後就生效。

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
- 🔴 **Healthcheck [12] FAIL 結構性已確認非新 bug**：bb_breakout 7d entries=0 — FIX-26-DEADLOCK-1 (`bcc5401`+`63957ad`) **已在 binary**，排除部署嫌疑。**根因 = P1-11 F1 結構性 1m bandwidth 永不達 expansion_bw=0.04**，屬 bb_breakout profile/timeframe 不匹配範疇（Wave 2+3 G2-05/G2-06 profile 調整或 5m timeframe 範圍）。本 session 不修。
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
| **G3-02** | 🔴P0 | ExecutorAgent shadow→live toggle 實裝（IPC `patch_executor_config`） | G3-01 | E1+PA / E2+E4 | 2-3d | e2e test shadow→live + Rust receive |
| **G3-03** | 🔴P0 | Rust `intent_processor` IPC handler（接 Python SubmitOrder） | G3-02 | E1 / E2+E4 | 2d | Rust can receive Python intent IPC |
| **G3-04** | 🟠P1 | ExecutorAgent shadow→live e2e 整合測試 | G3-03 | E4 / QA | 2d | QA 端到端驗證 pass |
| **G3-05** | 🟡P2 | EDGE-DIAG-1-FUP-SHADOW-ENABLED-IPC（升 P2） | 無 | E1+E2 | 1d | `shadow_enabled` hot-reload works |
| **G3-06** | 🟡P2 | Layer 2 autonomous 升級規則（L0→L1→L2 criteria） | G3-02 | AI-E+PA / E2 | 2-3d | 量化升級觸發條件 code |
| **G3-07** | 🟡P3 | Layer 2 工具箱補全（query_onchain / check_derivatives） | G3-06 | E1 | 2-3d | tool unit + e2e |
| **G3-08** | 🟡P3 | H1-H5 → Rust IPC Gateway | G3-03 | E1+PA / E2 | 3-5d | Rust query H1-H5 state |
| **G3-09** | 🟡P3 | `cost_edge_ratio` 原則 #13 演算法 | G3-08 | AI-E+E1 / E2 | 2d | cost_gate active when ratio ≥0.8 |
| **G3-10** | 🟡P2 | STRATEGIST-PROMOTE-TRIGGER-1（手動 API + IPC） | G3-02 | E1+E2 | 1d | POST /api/v1/strategist/promote |
| **G3-11** | 🟡P2→⚪P3（2026-04-24 降）| STRATEGIST-CYCLE-OBSERVABILITY-1 — Rust `strategist_scheduler` 加 `CycleCounters`（reject/apply/last_ts per reason）+ IPC emit `strategist_cycle_event` + Python DB sink `learning.strategist_cycle_events` + GUI `/api/v1/strategist/history/cycle_metrics` 切 DB 查詢（取代 engine.log tail-parse，解 416MB log + engine restart + rotation 觀測盲區）· **降級理由**：PERSIST-AUDIT-GAP-COUNTER-1 已解（`strategist_applied_params` 有真實 rows 可查）+ GUI footer log tail-parse 在 ANSI-escape fix 後夠用 80% 場景；專屬 observability table 屬錦上添花，可延後不影響主線 | G3-01 IPC RFC | E1+PA / E2+E4 | 2-3d | endpoint 回 DB row（非 log parse）+ reject/apply count 可 cross-validate `strategist_applied_params` + healthcheck [16] `strategist_cycle_fresh`（last_ts <10min）PASS / 來源：[FA 報告](.claude_reports/20260424_fa_eval_gap2_strategist_observability.md) + [PA 報告](.claude_reports/20260424_pa_eval_gap2_todo_placement.md) |

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
| **G7-03** | 🟠P1 | Hurst + Hysteresis 整合（6-period lag） | 無 | QC / FA+MIT | 2-3d | R/S analysis live |
| **G7-04** | ✅完成 Phase A | CUSUM 策略衰減監控 schema landing — 新 `CusumConfig { enabled, slack_k, threshold_h, min_observations, target_return_bps }`（Page/Montgomery convention，預設 dormant `enabled=false`、slack_k=0.5σ、threshold_h=4.0σ、min_obs=30）+ `validate()`（4 reject paths）+ 7 unit tests（defaults/4 reject/TOML round-trip/partial fallback）+ 3-env TOML `[cusum]` 區段；Linux 2030/0 ✅；**Phase A 純 schema**：runtime wiring 候選 σ-source `RiskConfig.ewma_vol`、consumer hook `dynamic_risk_sizer`/`strategy_orchestrator`，待 Phase B/C | 無 | QC+E1 | 完成 schema 2026-04-25 / wiring 待續 | [G7-04 report](.claude_reports/20260425_020449_g7_04_cusum_schema.md)（commit `1628cb6`）|
| **G7-05** | 🟡passive wait | cost_gate grand_mean bind condition — G7-09 已 deploy（2026-04-24 23:41 CEST），開始累積 post-fix data；**當前狀態**（ssh verify 23:41）：grand_mean_bps=-9.80 / n_cells=62 / shrunk_bps>0 count=**0**；`>-50 bps` 條件已滿足，**`≥2 strategies shrunk>0` 未滿足**；預計 ≥1w post-fix fills（~2026-05-01+）後有足夠 maker/taker 混合樣本，屆時 (a) 校準閾值是否仍合理（artifact vs real edge） (b) 落地 cost_gate bind 判決 code（TBD：ExitConfig 新 flag 或 IPC patch）| G1-01 + G7-09 | QC+E1 / FA | 2-3h（post-data） | bind when grand_mean > -50 bps ∧ ≥2 strategies shrunk>0 + post-fix threshold validated |
| **G7-06** | ✅完成 schema + impl（gated dormant）| Grid OU residual-based σ estimator — 新 `OuResidualSigma` struct 在 `strategies/grid_helpers.rs`（`theta` mean-reversion 速度 / `mu` 長期均值 / `sigma_hat` residual std / `n_observations`；`update(x_new)` rolling estimator + `estimate_from_window(slice)` batch；數學：OU 過程 `dx_t = θ(μ - x_t)dt + σ dW_t`，residuals `e_t = Δx_t - θ(μ - x_{t-1})` ~ N(0, σ²)，σ_hat = sqrt(Σe_t²/(n-1)) unbiased）+ `GridOuConfig { residual_window_size, fallback_sigma, use_residual_sigma }` 在 `risk_config_advanced.rs`（接 `RiskConfig.grid_ou` + 3-env TOML）· **Phase A gating**：預設 `use_residual_sigma=false` 保留現行為；翻 true 啟用 OU residual 估計；7 unit tests（recover within 5% on n=200 / trending series graceful no-NaN / window slice / lifecycle / n<5 None edge）· Linux release **2046/0** ✅ | 無 | QC / E1+E2 | 完成 2026-04-25 | commit `67a8261` |
| **G7-07** | ✅完成（範圍縮減）| Slippage / confluence 硬編碼清理 — **Discovery**：「8 檔」TODO 描述過期；41 grep-match 中大多已 TOML 化（strategy `min_persistence_ms/weight_*/threshold_*/adx_floor` 在 `MaCrossover/BbReversion/BbBreakoutParams` G-SR-1 A0-c；`squeeze_bw/expansion_bw/volume_threshold` 在 `BbBreakoutParams`；FundingArb cost bps 在 `FundingArbParams` QC-H10；`MarketGate.slippage_max_bps` 在 `advanced::MarketGate`）。**實際 1 檔 4 hardcode 移**：`intent_processor/{mod,gates}.rs` → 新 `SlippageConfig { default_rate=5bps, tiers=Vec<SlippageTier>(5 desc), cost_gate_win_rate_floor=0.3, cost_gate_safety_multiplier=1.3 }` 接 `RiskConfig.slippage` + 3-env TOML `[slippage]` + 5 `[[slippage.tiers]]` + regression test 確認 default lookup bit-identical；9 unit tests；Linux 2039/0 ✅ | 無 | QC+E1 / FA | 完成 2026-04-25 | [G7-07 report](.claude_reports/20260425_021006_g7_07_slippage_confluence_toml.md)（commit `92e65af` + relocate `3bed899`）|
| **G7-08** | 🟡P2 | outcome_backfiller SQL slow query 優化（PG resource）— **症狀**：1.5s slow query 反覆觸發，PG CPU/IO spike；**範圍**：(a) `EXPLAIN ANALYZE` 找熱點 query（`outcome_backfiller_runner.py` 系列）(b) 加 partial / composite index 或重寫 query (c) 確認 timeframe `'1m'` fix（`5e2981d`）後 backfill volume 是否仍對 PG 造成壓力；**前置**：confirm 反覆觸發來源（cron 頻率 / engine path），可能是 backfill 自然壓力非 bug | 無 | QC+E1 / FA | 1-2d | slow query <500ms p95 OR 觸發頻率降低 |
| **G7-09** | ✅完成 | FIX-FEE-POSTONLY-1 — 修三處：(1) `intent_processor/mod.rs:1084` 新增 `fee_rate_for_tif(symbol, tif: Option<TimeInForce>)` helper，既有 `fee_rate_for_intent` delegate 進同一選擇點 (2) `event_consumer/loop_handlers.rs:405-447` hoist matched_key lookup 至 fee compute 前，取 `PendingOrder.time_in_force` 後用新 helper，race (Fill 先於 OrderUpdate) → TIF=None → taker fallback 保本 (3) `intent_processor/tests.rs` 加 3 unit tests（PostOnly=maker / GTC=taker / None=taker race safety）· Linux release cargo test **1995/0**（baseline 1992 + 3 new）· `--rebuild` 部署 engine PID 1376094 binary 23:41 CEST · **downstream cascade**：fee 列 post-fix 會出現 2bps maker 混 5.5bps taker → grand_mean_bps 會變，G7-05 bind 閾值需重校準（passive ~1w）· **historical 資料不可逆**：pre-872478a 所有 fills 鎖 5.5bps；baseline 分析需 split pre/post commit ts | G1-02 | E1+QC / E2+E4 | 完成 2026-04-24 | demo fills fee_rate 開始出現 maker 2bps 列（觀察中）· engine lib 1995 / 0 failed · commit `872478a` |

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
| **G2-06** | 🟠P1 | bb_breakout threshold 重 calibrate（G2-05 後 7d 仍 0 fills 觸發）— **觸發**：FIX-26-DEADLOCK-1 已在 binary（21:58）+ healthcheck [12] 仍 FAIL ≥7d → 結構性 1m bandwidth mis-scale 確認（squeeze_bw=0.03 100% 觸發 / expansion_bw=0.04 永不達），非 deadlock 殘留；**範圍**：(a) 用 P1-11 Phase 1 sweep 工具 `helper_scripts/research/bb_breakout_threshold_sweep.py` 重跑 1m 30d data 找正常 trigger rate（squeeze 5-15% / expansion 30-60%）的 bw 區間 (b) 評估升 5m timeframe 替代（profile mismatch 結構解決）(c) 用 `BbBreakoutProfile::Aggressive` enum 已有的 helper 落 TOML 而非 hardcode；**前置**：G2-05 結論為 dormancy 非 deadlock；**避免**：直接調 conservative profile（會掩蓋 root cause）| G2-05 | QC+MIT+E1 / FA | 2-3d | sweep report + TOML threshold update + healthcheck [12] PASS 連 3d |

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
| **STRATEGIST-PERSIST-AUDIT-GAP-COUNTER-1** | ✅ 2026-04-24 完成 · e2e 驗證通過 | — | ✅ | **RCA + 雙修完成**：(1) Python `_build_strategist_prompt` 預算 `allowed_range=[current*0.7, current*1.3]` 寫入 prompt + HARD RULES（commit `d8f5560`）讓 Ollama L1-9b 遵守 ±30% cap；(2) Python `_parse_strategist_response` 保留 int-ness 避免 `float(v)` 強轉把 `78000` cast 成 `78000.0` 打壞 Rust u64 serde（commit `e47b1e9`+ merge `5538e52`）。**e2e 驗收 runtime**：舊 prompt 3/3 cycle (UTC 20:03/20:08/20:13) 100% reject；新 prompt 3/3 cycle (20:18/20:23/20:29) LLM 遵守 cap 但 type bug apply failed；type-fix 後首 cycle (UTC 20:34:08) `strategist params applied strategy=grid_trading symbol=BLURUSDT`；`learning.strategist_applied_params` rows 0 → 1 首行落表。報告：[FA Gap 2 eval](.claude_reports/20260424_fa_eval_gap2_strategist_observability.md) + [PA Gap 2 eval](.claude_reports/20260424_pa_eval_gap2_todo_placement.md)。|
| **STRATEGIST-TUNE-TARGET-CONFIG-1** | 運行時可配置 | Phase 5+ | 🟡P2 | 同上 root cause — MAX_PARAM_DELTA_PCT 硬寫 `strategist_scheduler/mod.rs:48 = 0.30`，若 LLM 暫難約束，可先放寬或 per-param 配置 |
| **STRATEGIST-HISTORY GUI** | ✅ 2026-04-24 完成（含 cycle_metrics footer FUP） | — | ✅ | tab-strategy.html 折疊 sub-panel（summary KPI + 3 filter + list 50 行 + Diff/7d Effect 展開）+ 底部 `近 scheduler cycle 健康度` 指標（rejects / applies / last ts / 提示文案）· endpoint `/api/v1/strategist/history/cycle_metrics` engine log tail parse 提供 root cause 自助診斷 |

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
