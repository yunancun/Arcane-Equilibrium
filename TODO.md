# OpenClaw TODO — 工作清單（v4 · 精簡版 · 2026-05-01）

**版本**：v4（2026-05-01 精簡清理；Wave 1-3 + Backlog 完成項歸檔）
**歸檔索引**：
- 62-finding Batch A-F：[docs/archive/2026-04-29--62finding-batch-A-to-F.md](docs/archive/2026-04-29--62finding-batch-A-to-F.md)
- STRKUSDT P0 Wave：[docs/archive/2026-04-29--strkusdt-p0-wave.md](docs/archive/2026-04-29--strkusdt-p0-wave.md)
- Wave A-H 完整敘述：[docs/archive/2026-04-29--wave-A-to-H-narrative.md](docs/archive/2026-04-29--wave-A-to-H-narrative.md)
- Wave 1-3 完成表格 + Backlog 完成項：[docs/archive/2026-05-01--completed_waves_1_2_3_and_backlog.md](docs/archive/2026-05-01--completed_waves_1_2_3_and_backlog.md)
- Pre-trim TODO snapshot（2026-04-29 前）：[docs/archive/2026-04-29--TODO-pre-trim-snapshot.md](docs/archive/2026-04-29--TODO-pre-trim-snapshot.md)

**Runtime/source（2026-05-01 23:17 CEST · Linux redeployed to `eaf0c7e`）**：`restart_all.sh --rebuild --keep-auth` completed on `trade-core` after ff-only pull；Rust engine PID **2455097** + API uvicorn PID **2455171** + engine_watchdog PID **3450754** + openclaw-gateway PID **3973441** alive。watchdog `engine_alive=true`，paper/demo/live snapshots fresh；API `/api/v1/strategy/prelive/edge-gates` returns 401 unauthenticated rather than 404（route loaded）。manual wrapper healthcheck SUMMARY **WARN** exit 0；no DB migration apply / strategy-risk param change / live auth mutation performed，`--keep-auth` preserved existing authorization.
**測試基準**：Mac Rust lib **2394/0** · Rust CUSUM targeted **17/0** · Python maker/attribution **9/0** · MLDE pytest **5/0**（shadow advisor/dream targeted）· G4 canary pytest **21/0** · Healthcheck targeted Python **45/0**（F7 43/0 + counterfactual [11] 2/0）· Scanner/API targeted pytest **15/0** · GUI performance metric contract **10/0** · Paper metrics **23/0** · Live endpoint actual-engine **17/0** · PRE-LIVE-3 edge gate trend tests **5/0** · Phase2 route coverage standalone **43/0** · static JS syntax check **10 scripts**
**21d demo 時鐘**：2026-04-16 22:16 → 解鎖 **2026-05-07**

---

## 🚨 4-day Codex Audit Findings（2026-05-02 · CC cold review）— **優先於 Wave 4 推進**

主 CC 4 月 28 → 5 月 1 缺席（限額），codex / operator 提交 162 commit / 581 檔 / +64k LOC（22 個 Co-Authored-By Claude，139 個非 Claude）。CC 5 月 2 cold audit 後發現以下治理 / 測試 / governance 破口，**需在繼續 Wave 4 軸線前修完 P1 條目**：

### 🟥 P1（治理紅線 + stale 測試，今日內修）

| ID | 問題 | 證據 | Owner | Acceptance |
|----|-----|------|-------|-----------|
| **AUDIT-2026-05-02-P1-1** | ✅ DONE 2026-05-02：5 SQL migration（V028/V030/V031/V032/V034）retrofit Guard A/B + V031 view shape-guard。Chain：E1 r1 → E2 r1 RETURN 3 finding → E1 r2 → E2 r2 PASS → E4 r2 FAIL（V031 view 非 idempotent against V034-extended 53-col state）→ E1 r3 Option B shape-guard → E2 r3 PASS → E4 r3 Linux production `trading_ai` PASS（V031 NOTICE-skip × 2、fixture 20/20、view col=53 preserved、audit OK、healthcheck WARN baseline 0 new FAIL）。Commit `e858ae2`（r1+r2）+ `6cb1c3b`（r3）| same | @E1 → @E2 → @E4 | DONE |
| **AUDIT-2026-05-02-P1-2** | ✅ DONE 2026-05-02：stale 回歸測試 grep target 改至 `event_consumer/status_report.rs`；測試 PASS。Commit `e858ae2` | same | CC 直接修 | DONE |

### 🟧 P2（hygiene + 治理澄清，本週內）

| ID | 問題 | Owner | Acceptance |
|----|-----|-------|-----------|
| **AUDIT-2026-05-02-P2-1** | ✅ DONE 2026-05-02：`.gitignore` 加 `.coverage*` / `htmlcov/` / `coverage.xml`；`git rm --cached .coverage` 完成。Commit `e858ae2` | CC 直接修 | DONE |
| **AUDIT-2026-05-02-P2-2** | 6 個 `chore(worktree): preserve XXX` + 6 個 `merge: preserve worktree agent XXX` —— sub-agent worktree 直接吸收 main，conflict 解法（含 `PA/memory.md` + `cost_edge_advisor/mod.rs`）無人審 | @PA review | spot-check `13051e2` 等合併 conflict 解；發現實質問題回報 |
| **AUDIT-2026-05-02-P2-3** | 單一 commit `b46660a` 加 13.6k 行（含 2466 行 audit + 2077 行 inventory TSV + 大量 Rust），E2/E4 對單 commit 審查近乎不可能；後續 codex 提交需強制拆 PR-sized commit | operator 決定 / TODO 警示 | 在 §七 加「單 commit 上限」規則 or 接受並 flag |
| **AUDIT-2026-05-02-P2-4** | ✅ DONE 2026-05-02：operator 選 (a)，CLAUDE.md §十二 補述「`.codex/` 平行目錄角色」確立 = 純 codex session 提示鏡像，不擁有治理權，衝突以 `.claude/agents/` + CLAUDE.md 為準 | — | — |

### 🟨 P3（代碼品質 + 文檔噪音，下個維護週期）

| ID | 問題 | Owner |
|----|-----|-------|
| **AUDIT-2026-05-02-P3-1** | `is_legacy_close_tag` 在 `tick_pipeline/commands.rs` 兩處重複（line ~205 / ~575）→ 抽 helper | @E1 next maintenance |
| **AUDIT-2026-05-02-P3-2** | `Add execution-aware edge model gates` (`1644701`) 改 3 份 `strategy_params*.toml` + `scanner_config.toml` 無 QC sign-off；`Relax scanner demo gates` (`2e06735`) 改 `immature_negative_*` 無 QC retro-review | @QC retro audit |
| **AUDIT-2026-05-02-P3-3** | TODO 大量 churn（4 天 ~30 commit 都是 `Document X` / `Refresh Y` / `Calibrate Z`）→ §三 / TODO 雜訊；CLAUDE.md §三 有 drift 風險 | next archive sweep |

### P2 Wave + LG-5 RFC（2026-05-02 · 完成）

**P2 wave commit `1f3acc5`**：4 fast-win fix（MIT-S2-6 / E3-S2-P2-1 / E3-S2-P2-2 / PA-DRY-1）+ §九 LOC 1200→1500 governance change。Chain：E1 batch → E2 PASS（0 RETURN, 3 informational nits accepted）→ E4 Linux PASS（cargo lib 2404/0 / cargo tests 2560/0 / pytest 3262 passed + 1 pre-existing grafana fail orthogonal / focused 27/0）。

**LG-5-RFC PA design**：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-02--lg5_live_candidate_eval_contract_rfc.md` — LIVE-CANDIDATE-EVAL-CONTRACT spec（解 MIT-S2-2 + QC-S2-02 同向 finding）。8 章 / R1-R6 + R-meta 7 條 evaluation rule / 5 個 IMPL sub-task wave。需 PM + QC + MIT 三方 sign-off 才進 implementation。

**待 deploy**：本次 commit 只更新源碼 + 文檔，engine 仍跑舊代碼。下次 deploy window 跑 `ssh trade-core "bash helper_scripts/restart_all.sh --rebuild --keep-auth"` 一次 promote Rust Fix 4 + Python Fix 1/2/3。E4 Step 8 baseline opp_24h noise 50/50 待 deploy 後 24h 重測，預期 noise 比例 < 50%。

### Step 2 結果（2026-05-02 · PA + MIT + QC + E3 並行 cold audit DONE）

**裁決**：**1 P1 + 12 P2 + 15 P3** — **不需 stabilization wave**（criterion ≥3 P1 觸發），繼續 PRE-LIVE-3 邊緣觀察軸線。但 1 個 P1 是 **operator 必修的 historical credential leak**。

| Audit | P1 | P2 | P3 | 結論 |
|-------|----|----|----|------|
| **PA** 架構 | 0 | 1 | 4 | 0 drift；commands.rs / scanner/scorer.rs LOC 破 1200 (P2)；`is_legacy_close_tag` 重複 (P3) |
| **MIT** ML/DB | 0 | 4 | 5 | MLDE 真接線到 Production(demo)/Shadow(live)；84.6% training row attribution_chain broken (P2) |
| **QC** 量化 | 0 | 5 | 4 | 1644701 score B 數學健全；min_trend_snr=0.75 三 env 一致疑違 `feedback_env_config_independence` (P2) |
| **E3** 安全 | **1** | 2 | 2 | 🚨 PG password + Grafana admin password **2026-03-27 起在 git history 6 個 commit 裡 public exposed**（codex `bc3fa70` 已 forward-fix env-var 路徑，但歷史值未清） |

### 🟡 E3-S2-P1-1（operator 評：repo 是 private，問題不大，正式上線前統一改）

**Status**：**RECORDED-FOR-LATER**（2026-05-02 operator 決定）— GitHub `yunancun/BybitOpenClaw` 是 private repo；Codex `bc3fa70` 2026-04-29 已 forward-fix 改 `${VAR:?}` env-var prompt；**歷史 commit 裡的明文值留著，正式 live 上線前統一輪換**。

**Leaked secrets inventory**（live 上線前須輪換）：

| # | 類型 | 值（長度） | 首次洩漏 | 最後 forward-fix | 影響檔 |
|---|------|----------|----------|------------------|--------|
| 1 | PostgreSQL `trading_admin` 密碼 | 20 字符 alphanumeric `(....)` 格式 — 與當前 Linux `settings/environment_files/basic_system_services.env` 內 `POSTGRES_PASSWORD` 完全相同（即從未輪換） | `d9580f9` 2026-03-27 | `bc3fa70` 2026-04-29（grafana postgres.yml 改 `${GRAFANA_POSTGRES_PASSWORD}`） | `docker_projects/monitoring_services/provisioning/datasources/postgres.yml` |
| 2 | Grafana admin 密碼 | `<REDACTED>` (12 字符) | `d9580f9` 2026-03-27 | `bc3fa70` 2026-04-29（docker-compose 改 `${GF_SECURITY_ADMIN_PASSWORD:?}`） | `docker_projects/monitoring_services/docker-compose.yml` |

**6 個受影響 commit**：`d9580f9` (2026-03-27) → `350c929` → `186e495` → `c31aef4` → `dbe2477` → `bc3fa70`

**Live 上線前必做（rotation checklist）**：
1. 生新 PG 密碼 → `ALTER USER trading_admin WITH PASSWORD 'NEW_VALUE'`
2. 生新 Grafana admin 密碼 → 對應 docker secret 更新
3. 同步更新 Linux `settings/environment_files/basic_system_services.env` 的 `POSTGRES_PASSWORD` + `GF_SECURITY_ADMIN_PASSWORD`（後者目前是 prompt 格式不存值）
4. 同步更新 Mac dev env files
5. Restart Linux engine + API + Grafana 讓新密碼生效
6. **可選**：`git filter-repo` 重寫 history 移除歷史值（private repo 風險低，operator 視情況決定）
7. 更新本 TODO entry 標 ROTATED + 日期

### Top P2 / P3 backlog（next maintenance wave）

| ID | Sev | Owner | 描述 |
|----|-----|-------|------|
| ~~PA-LOC-GOV-1~~ | ✅ DROPPED 2026-05-02 | — | operator 決定 §九 1200→1500 硬上限；`commands.rs` 1343 + `scanner/scorer.rs` 1437 都 ≤1500，新規下合規 |
| **PA-DRY-1** | P3 | E1 | `is_legacy_close_tag` `commands.rs:203/576` 重複 4 行 |
| **PA-SCRIPT-PROC-1** | P3 | E1 | `restart_all.sh` 等 4 script 用 Linux-only `/proc/<pid>/cwd`，Mac 違 §七.★★ 跨平台 |
| **PA-TEST-WATCHER-SLOT-1** | P3 | E1+E4 | 無 e2e 測試斷言 watcher respawn 寫 / teardown 清 `live_cmd_slot` |
| **MIT-S2-1** | P2 | QA+MIT | 84.6% MLDE training row `attribution_chain_ok=false`，rec 由小樣本驅動；可能與 [40] low row count 同源 |
| **MIT-S2-2** | P2 | CC+PM RFC | demo→live promotion candidates `expected_net_bps` 沿用 demo cost regime，未經 governance re-eval；MLDE 上 live 前須有 contract |
| **MIT-S2-3** | P2 | E1 | regret_summary undertrading +5%/cycle 無絕對 ceiling，僅靠 sample_count=0 stay safe |
| **MIT-S2-4** | P2 | E1 (defer) | V031 view 545ms/cycle，scaling 風險；建議 materialized view |
| **MIT-S2-6** | P3 | E1 | `opportunity_tracker.persist_regret_summary` always insert n=0 row → ~48 noise row/day |
| **QC-S2-01** | P2 | QC | scanner posterior LCB `min_std=20bps` 硬編碼無實證；對低變異 cell 過悲觀 |
| **QC-S2-02** | P2 | CC+PM RFC | demo→live promotion 不重評 distribution shift（cost regime 不同）→ 與 MIT-S2-2 同向 |
| **QC-S2-04** | P2 | PA | `min_trend_snr=0.75` 三 env 一致，違 `feedback_env_config_independence` |
| **QC-S2-09** | P3 | operator+RFC | PRE-LIVE-3 thresholds `[33]≥60% / [38]≥0.5x / [40]>0bps` 缺 RFC 數學依據 |
| **E3-S2-P2-1/P2-2** | P2 | E1 | 兩個新 endpoint 仍走 `detail=f"...{exc}"` exception 字串外洩（拓展 baseline MEDIUM-A inventory 11→13） |
| **E3-S2-P3-1** | P3 | E1 (defer) | `secret_env::var_or_file` 不驗 file mode 0600 |

完整 finding 與 recommendation 在 4 個 `.claude_reports/20260502_*_step2_*.md`。

### LG-5 Wave 3 Sign-off 後 follow-ups（2026-05-02 dispatch）

| ID | Sev | Owner | 描述 |
|----|-----|-------|------|
| **LG5-W3-FUP-1** | HIGH | @E1 | Wire `review_live_candidate` consumer 進 scheduler — 每 N 分鐘 poll `learning.mlde_param_applications` pending candidates 然後 call。當前 `[42]` FAIL：27 unaudited candidates 無人 call。Healthcheck 沒這個 wire 上 永遠 FAIL。 |
| **LG5-W3-FUP-2** | HIGH | @MIT | Investigate `attribution_chain_ok` writer gap — grid 13.5% / ma 15.2% 在 7d 內 86%+ row 缺；對齊 Step 2 MIT-S2-1。Read-only diagnosis 找 root cause + 提 fix plan（fix 後續派 E1）。 |
| **LG5-W2-FUP-PA-RFC-§4** | P2 deferred | @PA next batch | RFC v2 §4 scope binding requirement — `authorization.json.scope.lease_scopes` 加 `LIVE_CANDIDATE_APPLY:*` 條目；當前 empty-fallback=True 是 latent rug-pull 風險。**operator 2026-05-02 決定下個 batch 處理，不阻 W3 deploy** |
| **LG5-CONSUMER-SPLIT** | P3 backlog | @E1 future | governance_hub_live_candidate_review.py 1496/1500 LOC near cap；下一輪維護抽 atomic helper module |

### 接手後 Step 2 計劃（P1 修完才執行 — 已 DONE）

派 `@PA + @MIT + @QC + @E3` 並行 cold review 過去 4 天非 docs commit，**不依賴 commit message 自述**：
- **PA**：架構債（live_authorization.rs +106 / strategist_scheduler 抽 slot 是否完整 / position_reconciler 接線正確）
- **MIT**：ML pipeline maturity（MLDE 是真 producer-consumer 還是只有 writer / V031-V034 schema 是否 leakage-safe / scanner_snapshots 行累積實測）
- **QC**：1644701 / 2e06735 / 67b1160 策略參數變動是否合理（OU grid floor / MA ATR-SNR / scanner posterior LCB / immature_negative thresholds）
- **E3**：secret leak 全掃 + `.codex/` 是否含敏感資訊

audit 結果決定：≥3 個 P1 → 整週 stabilization wave；≤1 個 P1 → 接 PRE-LIVE-3 後續邊緣觀察軸線。

---

## 此刻該做什麼（2026-05-01 · passive observation phase）

**當前狀態**：Strategy Edge Models + Dust Residual Prevention deployed & proven；Scanner market judgement + five-strategy context deployed；MLDE demo autonomy active。Wave 4 pre-stage Rank 4-7 source/RFC checkpoint landed in `ec8f0f4`；`b283fda` calibrated `[22]` maker-working/rejected-only semantics；`25d8e54` landed G8-05 AI Cost ROI Monitor static UI and LG-5 constrained autonomous live RFC；`be8fe37` exposed Rust scanner context to Python/Scout/MLDE surfaces（V034 migration file landed but not applied to runtime DB）；`569e06b` unified Demo/Paper/Live GUI performance metric contract；current checkpoint completes PRE-LIVE-3 [33]/[38]/[40] read-only trend API, Live trend cards, and readiness checklist。
下一個需要 implementation 的 wave 是 Wave 4（等 P0-3 ~05-15 決策後啟動）。
目前主要工作是：觀察、時間等待、3 個時間點的決策。最新 P0 hygiene：`[27]` 21:39 wrapper false-FAIL 已由 `4abb36a` 重校準：只有 **Approved risk verdicts >0 且 0 persisted intents** 才 FAIL；signal-only / rejected-only window 轉 WARN。22:02 wrapper 中 `[27]` 是 WARN（demo 有 22 個 recent verdict，但 approved=0，全被 risk/cost gates 拒絕；Guardian alive），不是 writer wedge。`[11]` 的 864→413 是 rolling 2d replay 舊 exits 滾出，`2674e14` 已把 false-red 改為 WARN。

### 時間驅動里程碑

| 日期 | 觸發點 | 動作 |
|------|-------|------|
| **~05-03** | G2-02：1w post-G7-09 demo 數據累積完成 | 跑 `ma_crossover_counterfactual_replay.py`；若結論支持 → 派 G2-03-FUP-CALLER-WIRE P1 |
| **~05-07** | P0-2 21d demo 解鎖 + G2-01 PostOnly 1-2w 驗收 | 若 [33] fee_drop ≥60% → PASS；否則 G2-04 grid disable 決策會 |
| **~05-10** | EDGE-P1b：per-strategy ≥200 rows（grid 1030 / ma 493 READY）| 跑 `exit_threshold_calibrator.py`；manual approve flow |
| **~05-15** | P0-3 邊評決策會 | PM+FA+PA+QC：edge positive/mixed/still negative → LG-2/3/4/5 or dual-track |
| **~05-22+** | Wave 4 實裝 | 依 P0-3 決策路徑啟動 LG-2/3/4/5 |
| **~05-30±7d** | Live target | PM W2 sign-off 目標 |

### Active Observation Gates

| Gate | 現況（2026-05-01 22:36 CEST） | 目標 | 結論時間 |
|------|------------------------------|------|---------|
| [22] trading pipeline silent gap | WARN：fills stale 82.3m / fills_1h=0；gap_context orders_1h=2 / working_maker_orders_1h=2 / risk_30m=4 / approved_30m=1 / rejected_30m=3；maker no-fill not writer wedge | distinguish writer/order push wedge vs unfilled maker working orders | 校準完成，持續觀察 |
| [16] strategist cycle fresh | last cycle 11.3min ago；within 30-min backoff window | <30min backoff tolerated | transient observe |
| [33] maker_fill_rate | 7d rolling 27.2%；fee_drop 22.0%；PostOnly still diluted by pre-reload | ≥60% fee_drop | ~05-07/08 |
| [38] grid lifecycle drift | demo p50 7.9min vs live_demo 3.2min；lifetime_ratio 0.41 WARN；live re_entry_rate 0.48 | lifetime ≥0.5x | ~05-06 再看 |
| [40] realized edge acceptance | 24h MLDE rows=39，avg_net -17.97bps，maker_like 27.2%，fee_drop 22.0% | net_bps_after_fee>0 | 等累積 |
| [41] scanner market-gate confirmation | events=1260 / cells=69 / scoreable=0，gate 已 fire 但 label 未足 | gate blocked cells later negative | 等 label 累積 |
| [27] intents counter freeze | demo stale 88.3m / intents_30m=0 / verdicts_30m=1 / approved_verdicts_30m=0 / dcs_30m=1080；risk/cost gates rejected all attempts | approved verdicts with 0 intents 才 FAIL | 持續觀察 |
| [11] counterfactual clean window | n=413/200，cf_fired=46，grid=16，ma=22，orphan=2，json_age=16.6h；rolling 2d window shrink expected，WARN not FAIL after `2674e14` | fresh replay + 3d WARN/PASS streak；criteria grid/ma/orphan 達標 | 本週 |

**EDGE-DIAG-2 留尾觀察**：(ii) PostOnly maker fill rate 待 ≥1w demo 累積 (iv) demo bb_breakout 1m bandwidth 結構性問題等 5m 升級或 MLDE sweep；不阻塞主路徑。

---

## 🚀 Wave 4 Pre-Stage 主動工作計畫（2026-05-01 → 05-22 · 21d）

**戰略**：passive observation **不是閒置，是準備密集期**。等待 G2-02/G2-01/EDGE-P1b/P0-3 數據結論的同時，平行推進 5 軸線可主動工作。詳細 PA RFC：[`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-01--passive_observation_proactive_plan.md`](docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-01--passive_observation_proactive_plan.md)（34 任務 / 5 軸線 / ~28-35d 工時 / 21d 並行壓縮 ~70% 可消化）

### 軸線 1：Wave 4 LG-2/3/4/5 + MLDE-6 PA RFC（必須 P0-3 前完成）

| ID | 任務 | PA 工時 | 前置 | 完成 gate |
|----|-----|--------|------|----------|
| **LG-2-RFC** | ✅ RFC landed：[`2026-05-01--lg2_h0_blocking_verification_rfc.md`](docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-01--lg2_h0_blocking_verification_rfc.md)（`5ce777b`） | 1.5d | DOC-08 §12 | 5 metrics threshold + rollback IPC + E2E mock blocked intent + 16 根原則對照 |
| **LG-3-RFC** | ✅ RFC landed：[`2026-05-01--lg3_provider_pricing_binding_rfc.md`](docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-01--lg3_provider_pricing_binding_rfc.md)（`5ce777b`） | 1d | G7-07 SlippageConfig ✅ | Bybit V5 fee tier mapping + IPC pull period + fail-closed when stale > N min |
| **LG-4-RFC** | ✅ RFC landed：[`2026-05-01--lg4_supervised_live_gate_rfc.md`](docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-01--lg4_supervised_live_gate_rfc.md)（`ec8f0f4`） | 2d | LG-2/3 RFC | approval RPC schema + per-symbol/daily risk override + dual-path kill switch + audit log mirror SM-04 |
| **LG-5-RFC** | ✅ RFC landed：[`2026-05-01--lg5_constrained_autonomous_live_rfc.md`](docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-01--lg5_constrained_autonomous_live_rfc.md)（`25d8e54`） | 2d | LG-4 RFC | 自主邊界 spec + escalation trigger + lease TTL + 16 根原則 #11 對照 |
| **MLDE-6-RFC** | ✅ RFC landed：[`2026-05-01--mlde6_live_promotion_contract_rfc.md`](docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-01--mlde6_live_promotion_contract_rfc.md)（`5ce777b`） | 1d | MLDE-5 ✅ + GovernanceHub | version-aware schema + operator review UI + rollback path + 16 根原則 #3/#7/#11 |

**軸線 1 總計**：PA 7.5d / E1 5.5d。21d window 1 PA agent 並行可完成。

### 軸線 2：條件性可獨立進行（不需等 P0-3）

| ID | 任務 | 工時 | 派工 |
|----|-----|------|------|
| **G4-03 Phase B** canary auto-promote 部署（cron driver + Brier + PSI drift + SIGHUP） | ✅ source landed `ec8f0f4`；default dry-run / apply env-gated / no cron installed | PA + E1 + E2/E4 |
| **G7-04 Phase B/C wiring** CUSUM consumer hook（Phase A schema landed） | ✅ dormant source hook landed `ec8f0f4`；hot path not enabled | PA + E1 + E2 |
| **G8-05** AI cost ROI 監控面板（GUI，G3-09 已備數據源） | ✅ static UI landed `25d8e54`；AI tab reads nested Layer2 cost/adaptive fields + 7d ROI panel | E1 |
| **STRK-FUP-HEALTHCHECK-PRE-EXISTING** 5 silent-dead pipeline 修（[3]/[19]/[23]/[24]/[26]/[27]） | ✅ broader RFC landed `ec8f0f4`；implementation split remains [3]/[19]/[23]/[24]/[26] | PA + E1×3 |
| **LEARNING-COCKPIT-NO-IPC** 8 endpoint 改 Python state_store（IPC traffic drop ≥80%） | 3d | PA + E1 + E2 |
| **MLDE-SCANNER-CONTEXT** scanner trend/fitness → Python/Scout/MLDE/Dream surface | ✅ source landed `be8fe37`；V034 migration file landed / runtime DB apply not performed | E1 + E2 |
| **G3-08-FUP-ANALYST-SPLIT** P2 + **HSQ-SPLIT** P2（鏡 Strategist split pattern） | 1.5d × 2 | E1 + E2 |
| **G3-08-FUP-MAF-SPLIT-CLEANUP-A** P4 + **SINGLETON-POLLUTION** P4 | 0.75d + 1.5d | E1 + E2 |

**軸線 2 總計**：~17.5d 工時；最大並行 4 並行壓縮 ~7d。

### 軸線 3：Pre-Live 基礎設施

| ID | 任務 | 工時 | 觸發點 |
|----|-----|------|--------|
| **PRE-LIVE-1** Slack alert 決策 framework（go/no-go + routing rules）| 0.5d + operator | 2026-05-15 ±3d |
| **PRE-LIVE-2** HTTPS deploy（解 G-4 Cookie secure 阻塞，Tailscale cert / LE 雙 path）| 3d | live 前必完 |
| **PRE-LIVE-3** Dashboard 強化（[33]/[38]/[40] 趨勢 + AI cost ROI + Live readiness）| ✅ complete + redeployed：G8-05 AI cost ROI `25d8e54`；canonical Demo/Paper/Live performance grid `569e06b`；`eaf0c7e` adds `/api/v1/strategy/prelive/edge-gates` + Live [33]/[38]/[40] trend cards + readiness checklist，loaded on runtime 2026-05-01 23:17 CEST | 配合 G8-05 |
| **PRE-LIVE-4** 災難恢復演練（drawdown auto-revoke + liquidation buffer + auth expire 三 scenario） | 1.5d | LG-2 RFC 後 |

### 軸線 4：P0-3 決策會準備（~05-15）

| ID | 任務 | 工時 |
|----|-----|------|
| **P03-PREP-1** Edge decision protocol（criteria + evidence templates + 三分支執行路徑）| 1.5d |
| **P03-PREP-2** P0-3-01 報告 outline（counterfactual_exit_replay 12 章節骨架，~05-13 填資料）| 0.5d outline + ~05-13 fill |
| **P03-PREP-3** 各 agent pre-meeting briefs（PM/FA/PA/QC 4 agent × 0.5d 並行）| 2d 並行 |
| **P03-PREP-4** Adversarial review playbook（5 round prompt template）| 0.5d |

### 軸線 5：Documentation / Test / Maintenance

| ID | 任務 | 工時 |
|----|-----|------|
| **DOC-1** Live trading first-day SOP runbook | 1.5d |
| **DOC-2** Wave 4 deploy runbook（LG-2/3/4/5 順序 + 回滾） | 1d |
| **TEST-1** E2E live gate tests（mock Bybit mainnet ≥10 cases） | 2d |

### 派發優先序（Top 10 立即可派）

| Rank | 任務 | 派發 | 工時 | 為何優先 |
|------|------|-----|------|---------|
| 1 | ✅ **LG-2-RFC** | PA | done | `5ce777b` landed H0 blocking verification RFC |
| 2 | ✅ **MLDE-6-RFC** | PA | done | `5ce777b` landed live promotion contract RFC |
| 3 | ✅ **LG-3-RFC** | PA | done | `5ce777b` landed provider pricing binding RFC |
| 4 | ✅ **STRK-FUP-HEALTHCHECK** | PA + E1×2 | done for RFC | `ec8f0f4` landed broader silent-dead RFC；[3]/[19]/[23]/[24]/[26] implementation remains future split |
| 5 | ✅ **G7-04 Phase B/C** CUSUM wiring | PA + E1 | done for dormant hook | `ec8f0f4` landed pure downside-CUSUM evaluator + orchestrator filter hook；hot path not enabled |
| 6 | ✅ **G4-03 Phase B** canary 部署 | PA + E1 | done for source | `ec8f0f4` landed Brier/PSI gates + dry-run cron wrapper；cron/apply/SIGHUP remain opt-in |
| 7 | ✅ **LG-4-RFC** | PA | done | `ec8f0f4` landed supervised live gate approval/risk/kill-switch/audit RFC |
| 8 | ✅ **G8-05** AI cost ROI GUI | E1 | done | `25d8e54` landed AI tab ROI monitor + field compatibility fix |
| 9 | **PRE-LIVE-2** HTTPS deploy | PA + E1 | 3d | 解 G-4；live trade 前必完 |
| 10 | ✅ **LG-5-RFC** | PA | done | `25d8e54` landed constrained autonomous live RFC |

**節奏**：W21 D1-D3 已完成 Rank 1+2+3 + Rank 4 `[27]` 校準；`ec8f0f4` 完成 Rank 4 broader RFC + Rank 5+6+7；`b283fda` 完成 `[22]` 校準；`25d8e54` 完成 Rank 8+10；`be8fe37` 補 scanner context Python/Scout/MLDE surface；`569e06b` 補 PRE-LIVE-3 的 canonical performance metrics 基礎；current checkpoint 完成 PRE-LIVE-3 [33]/[38]/[40] trend charts + readiness checklist。Rank 9 HTTPS deploy 需另行 runtime/deploy 風險確認；下一個安全非 deploy 項可接 P03-PREP-1 / DOC-1 / TEST-1 / PRE-LIVE-1。

### Wave 4 依賴圖（簡化）

```
P0-3 決策（~05-15）
   ├─ A 翻正 → LG-2/3/4/5 全推 → Live target ~05-22~05-30
   ├─ C 部分改善 → LG-2/3 + 部分 LG-4 → Live target slipped
   └─ B 仍負 → DUAL-TRACK + 策略重做 → Live target deferred

並行（不依賴 P0-3）：
   軸線 1 RFC（即使 outcome B 也是 dead-code-prevention 學習材料）
   軸線 2 G4-03 / G7-04 / G8-05 / LEARNING-COCKPIT / 各 split
   軸線 3 PRE-LIVE-1~4
   軸線 4 P0-3 決策會準備（必做）
   軸線 5 DOC + E2E test
```

### Wave 4 時序

| Phase | 週次 | 日期 | 主軸 |
|-------|------|------|------|
| **Pre-Stage** | W21-W22 | 05-01→05-15 | 軸線 1 RFC + 軸線 2 wiring + 軸線 3 infra + 軸線 4 prep |
| **Decision** | ~W22 末 | ~05-15 | P0-3 決策會（A/B/C 分支）|
| **Implementation** | W23-W24 | 05-15→05-30 | LG-2/3/4/5 E1 落地 + e2e tests |
| **Live** | ~W24 末 | ~05-30±7d | Live target 中位 |

### 風險（Top 5）

| 風險 | 緩解 |
|------|------|
| LG-2/3/4/5 RFC 若 P0-3 outcome B → 部分作廢 | RFC 仍是 dead-code-prevention 學習材料；文件結構保留下次重啟免重做 |
| MLDE-6 RFC 若 P0-3 影響 advisory schema | 寫成 version-aware schema with feature flag |
| STRK-FUP 5 silent-dead 連鎖驚喜 | PA design phase 全 5 個 RCA 完成才派 E1 |
| G4-03 Phase B PSI drift 假陽/假陰 | DEFAULT-OFF env-gated；observation only，不 auto-promote |
| 並行 sub-agent 衝突（軸線 1+2 同動 strategy_wiring）| PA 派發前 git fetch + grep；重疊則加 isolation: worktree |

---

## ⏳ G3-09 Phase C（deferred）

PA RFC `2026-04-28--g3_09_cost_edge_advisor_phase_c_rfc.md` ready；operator 決定「等時間長一些」；Phase B observation period 與 Phase C 綁定。

### Maintenance backlog（P4，機會性清理）

- G3-08-FUP-MAF-SPLIT-CLEANUP-A P4：lazy re-export 已接受設計，掃 Scout 首入場 risk 後可清
- SINGLETON-POLLUTION-PHASE2-ROUTES P4（Mac-only）

---

## 背景線程（獨立持續，每 6h cron 監控）

| 項目 | 狀態 | 解鎖條件 |
|------|------|---------|
| P0-2 21d demo 時鐘 | 進行中 | 2026-05-07 |
| [33] PostOnly 驗收（G2-01）| 累積中 | ~05-07/08 出結果 |
| EDGE-P1b exit_features 累積 | grid/ma READY | ~05-10 calibrator |
| EDGE-P3 clean window freshness | fresh rolling replay；[11] WARN（criteria 未達，非資料倒退） | fresh replay + 3d WARN/PASS；grid/ma/orphan criteria 達標 |
| [22] pipeline silent gap semantics | `b283fda` calibrated to WARN on Working PostOnly maker orders or rejected-only risk/cost gates；22:29 wrapper SUMMARY WARN | continue observe; FAIL only for unexplained cliff |
| [27] intents freeze semantics | signal-only/pre-gate WARN；approved verdict + zero intent 才 FAIL（`4abb36a`）；22:29 CEST rejected-only WARN（approved=0） | 連續 wrapper 觀察，若出現 approved_verdicts_30m>0 且 intents_30m=0 才人工介入 |
| G2-03 binding | 等 G2-02 結論 | ~05-03 觸發 |
| EDGE-P2-flip | 等 EDGE-P1b | ~05-10+ |
| GRID-LIFECYCLE-DRIFT | real signal FAIL；RFC deployed，觀察 14d rolling | ~05-06 再評 |

**規則**：任何背景項連續 3 次 healthcheck FAIL = 中止被動等待，轉人工介入。

---

## Wave 4（6/12→6/23，P0-3 決策後啟動）

### P0-3 Phase 5 Edge 重評

| ID | Tag | 項目 | 前置 |
|----|-----|------|------|
| **P0-3-01** | P0 | counterfactual_exit_replay 完整分析報告 | G2 完成 + MLDE dataset |
| **P0-3-02** | P0 | Edge 重評決策會（A 翻正/B 仍負/C 部分改善） | P0-3-01 |

**outcome 分支**：A. edge 翻正 → LG-2~5 推進 · B. edge 仍負 → DUAL-TRACK + 策略重做 · C. 結構性改善 → Phase 5 部分接線

### ML/Dream Live Governed Boundary

| ID | Tag | 項目 |
|----|-----|------|
| **MLDE-6** | RFC landed `5ce777b` / impl: P0-3 後 | Live promotion contract design（advisory→proposal→demo patch→live candidate）；live 仍需 GovernanceHub + Decision Lease |

### Live Gates（5 項，P0-3 後）

| ID | Tag | 項目 |
|----|-----|------|
| **LG-2** | P0 | H0 Gate blocking 驗證（shadow→blocking）；RFC landed `5ce777b` |
| **LG-3** | P0 | Provider pricing table 正式綁定；RFC landed `5ce777b` |
| **LG-4** | P0 | M 章 Supervised Live Gate；RFC landed `ec8f0f4` |
| **LG-5** | P0 | N 章 Constrained Autonomous Live；RFC landed `25d8e54` |
| **G-4** | P2 | Cookie secure=True（HTTPS 部署後）|

---

## Backlog（條件觸發，非當前 Wave）

| # | 項目 | 觸發條件 | Tag |
|---|------|---------|-----|
| **G2-03-FUP-CALLER-WIRE** | wire step_6_risk_checks caller chain，真實啟用 SL/TP override | G2-02 ~05-03 後 | P1 |
| **G2-04** | Grid disable 決策會 | G2-01 若 fee_drop <60% | P0 |
| **G8-03** | 灰度驗收自動化（shadow metrics）| EDGE-P2 flip 後 | P1 |
| **EDGE-P2-flip** | combine layer shadow flip | EDGE-P1b + 7d ≥95% agree | P1 |
| **EDGE-P2 Phase B** | Liquidation signal | Phase A OI 驗收 ✅ 已完 | P3 |
| **EDGE-P2-3 Phase 2+** | live endpoint / funding_arb PostOnly | EDGE-P1b ~05-10+ | P3 |
| **G2-03 binding** | ma_crossover SL/TP 真實啟用 | G2-02 結論 + G2-03-FUP-CALLER-WIRE | P1 |
| **G7-03-Phase-B-FUP-grid** | grid_trading HysteresisDetector 遷移 | parallel WIP merge 後 | deferred |
| **G7-01 wiring** | Kelly router callsites | G4 labels work | deferred |
| **G3-06 Phase B** | Layer 2 autonomous Rust integration（Phase A `82ef8e1` 已 land Python `EscalationTier`，Rust 端整合 deferred）| 條件待確認 | P3 deferred |
| **STRATEGIST-AUTO-PROMOTE** | 自動晉升規則 | P2-01 穩定後 | P3 deferred-long |
| **ORPHAN-ADOPT-1 Phase 2B** | Strategist `would_take` 終仲裁 | G-1 R-02 | P3 |
| **IP-DEDUP-1** | IntentProcessor 去抖 | P0-3 後 edge 仍負 + 高重發率 | P4 |
| **G-7 ClaudeTeacher 啟用** | consumer_loop.rs enabled | 21d demo + G-3 後 ~05-07+ | P2-P3 |
| **G9-02-FUP-COOLDOWN** | WS force reconnect cooldown 評估 | DEFAULT-ON 後 1-2w passive | LOW |
| **G8-01-FUP-REGRET-DREAM-DEFERRED** | OpportunityTracker + DreamEngine rebuild（per V1.1+R1 SPEC §3+4）| 長期未定 | P3 |
| **G2-FUP-FUNDING-ARB-PAPER-SYNC-LOW-1** | TW memory.md 補 commit msg 一致性 | 下次 TW 接手 | P3 |
| **T6-FUP-PA-MEMORY-INDEX-SYNC** | PA Track 3 dust audit memory.md 條目補錄 | 下次 PA 接手 | LOW |
| **G5-09-FUP-TYPO** | commit `a5b6f17` commit msg test count typo | 下次 commit msg edit cycle | P3 |
| **TIER4-MIT-AUDIT-GREP-SNIPPET** | MIT EXIT-FEATURES audit H1 補 grep snippet 嚴謹度 | 下次 audit | P3 |
| **OC-4** | MCP PostgreSQL 自然語言查詢 | Phase 5+ | P4 |
| **4-Conditional** | PairsTrading/Beta/Kalman/Jump detection | post-live | P4 |
| **G-6/G-7/G-8/G-10** | Edge JS retrain / ClaudeTeacher / cost_gate credibility / isotonic | P1-7B / 21d+G-3 | P4 |
| **QoL-2** | Demo AI cost 追蹤 GUI（硬編碼 N/A）| G3-08 | P2 |
| **G7-05** | cost_gate grand_mean bind | grand_mean>-50bps ∧ eligible cells>0 ∧ ≥2 strategy shrunk>0 | P1 passive |
| **G-2 FundingArb 重評** | 三參數重評 | R-02 Strategist 在線 | P3 |

---

## Healthcheck 清單（`passive_wait_healthcheck.py` 已實裝）

**Ground truth**：cron-wrapper output；最近 post-fix 手跑 wrapper 2026-05-01 21:32 CEST SUMMARY WARN exit 0，checks [1]-[41]（skip [17]，含 [Xa]/[Xb]）。裸 `python3 helper_scripts/db/passive_wait_healthcheck.py` 在非互動 SSH 可能缺 DB env；接手請用 wrapper。

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
| [Xa] | leader_election_health | G1-01 |
| [Xb] | pipeline_triangulation | G6-01 |

---

## 接手三連檢查

```bash
git status && git log --oneline -5
ssh trade-core "python3 helper_scripts/canary/engine_watchdog.py --data-dir /tmp/openclaw --status"
ssh trade-core "cd ~/BybitOpenClaw/srv && bash helper_scripts/db/passive_wait_healthcheck.sh --quiet"
```

---

## 工作流程速查

```
角色鏈：E1/E1a 並行（≤5）→ E2（強制）→ E4（強制）→ PM 確認 → commit + push
```

部署：`ssh trade-core "bash helper_scripts/restart_all.sh --rebuild"`

---

**簽核鏈**：PA 核實 → PM Sign-off → commit/push → Linux pull
**下一決策點**：~05-03 G2-02 ma_crossover 數據可用
