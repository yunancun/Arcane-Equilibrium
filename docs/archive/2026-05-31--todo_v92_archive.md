# TODO v92 Archive — Closed / Historical Extraction (2026-05-31)

**Date**: 2026-05-31
**Scope**: 把 `srv/TODO.md` 內已 CLOSED / DONE / SOURCE DONE / DEPLOYED 且不影響未來 gate 的明細，以及過時的 version-increment / runtime-snapshot / sprint-phase 歷史段落抽出 active queue，存於本檔。Active TODO 縮為 active-only dispatch queue（active P0/P1/P2 + acceptance + next action + safety dashboard + watch/schedule/SSOT）。
**Maintenance basis**: `docs/agents/todo-maintenance.md`「DONE lifecycle」— DONE detail 停止幫助 immediate handoff 即歸檔；保留短 active marker（若 affects future gate）+ archive 連結；不刪 acceptance / 不藏 blocker。
**保守原則**: 模稜兩可（可能仍 active）的條目一律留在 active TODO，未移此處。
**前一份 TODO archive**: `docs/archive/2026-05-29--cold_audit_p1_p2_p3_closure_archive.md`（cold-audit P1/P2/P3）+ `docs/archive/2026-05-21--todo_v60_archive.md`（v60 重構）。

> ⚠️ **本檔僅為歷史細節歸檔，非 active 派工來源。** Active dispatch queue 永遠是 `srv/TODO.md`。任何 closed item 若標 `affects future gate / no-revive / no-reopen`，active TODO 保留短 marker，本檔保存完整明細。

---

## Index

- §A — Version-increment 歷史（v75–v91 增量段落；v92 保留在 active TODO）
- §B — Runtime snapshot lineage（舊 PID/deploy 健康快照；最新 v87 deploy 快照保留在 active §0）
- §C — Sprint Phase Banner 已 DONE 的歷史 phase 行
- §D — §3 已 CLOSED workflow（A / D / E / F …）
- §E — §6 P1 queue 已 CLOSED / SOURCE DONE / DEPLOYED 明細
- §F — §7 Operator checklist 已 DONE 行
- §G — §8 Backlog cluster 已 CLOSED 條目
- §H — §9 Cascade Pending 已 CLOSED 條目
- §I — §15 衝突仲裁已 WITHDRAWN / OBSOLETED 條目
- §J — §-1 歷史 closure 摘要全文（>14d 滾出 active window 的明細）
- §K — Commit map（本歸檔涉及的主要 commit）

---

## §A — Version-increment 歷史（v75–v91）

> active TODO 版本行只保留 **v92**（當前戰略決策 context：autonomy 凍結 / alpha 成本牆 / alpha 重定向）。以下 v75–v91 增量段落為歷史，移此。

**v91 增量（2026-05-31 M4 GovernanceHub lease provider seam）**：source checkpoint commit `ec11544a` 已推 `origin/main` 並 fast-forward 到 Linux `trade-core`。M4 Stage 1 新增 `GovernanceHubDecisionLeaseProvider` + CLI `--acquire-governance-leases`：writeback 可顯式 opt-in 經 GovernanceHub IPC bridge 取 Decision Lease；`run_production_stage1()` 接受 provider seam；V103 `learning.hypotheses.decision_lease_draft_id` 仍是 UUID，所以非 UUID-compatible lease 會立即 release `FAILED` 並 fail-closed 不 INSERT。**重要實證/限制**：Linux direct lease preflight（無 DB writeback；若取得會立刻 release FAILED）目前 `fail_closed`，未取得 active lease；且既有 Rust/Python Decision Lease ID 形式為 `lease:<12hex>`，與 M4 DRAFT UUID column 不兼容。故本輪是安全 source seam + fail-closed guard，**尚不能宣稱 production DRAFT writeback 可用**；下一步需二選一設計：調整 M4 schema/bridge 以保存 canonical string lease ID，或提供 UUID-compatible writeback lease 映射並補 Rust IPC handler/active lease path。驗證：Mac `python3 -m pytest helper_scripts/m4/tests -q` 98/98、`py_compile` PASS、CLI `--dry-run --acquire-governance-leases` PASS、`git diff --check` PASS；Linux 同 commit M4 tests 98/98、`py_compile` PASS、CLI dry-run PASS、PG no-writeback artifact `/tmp/openclaw/empirical/m4_stage1_governance_provider_no_writeback_20260531.json` PASS（source counts klines=104520 / fills=426 / liquidations=92069 / funding=176；22 candidates；5 selected exploratory→PG draft；writeback_enabled=false；n_drafts=0）；direct lease preflight fail-closed PASS（0 hypothesis INSERT）。本輪 Python helper/source-only，未 rebuild/restart runtime。

**v90 增量（2026-05-31 A2 maker-fill feasibility diagnostic）**：source checkpoint commit `0731d57b` 已推 `origin/main` 並 fast-forward 到 Linux `trade-core`。新增 `helper_scripts/reports/alpha_candidate_stage0r/a2_maker_fill_feasibility.py` + smoke：read-only `market.liquidations` 產生 BTC/ETH A2 cascade triggers，join `market.market_tickers` BBO，估算 trigger 後 60s PostOnly passive entry offset touch rate；只輸出 `reject` / `draft_only` / `observe_more`，不下單、不寫庫、不改 TOML。Linux PG artifact `/tmp/openclaw/empirical/a2_maker_fill_feasibility_20260531.json`（data window 2026-05-18 00:52:28+02 → 2026-05-31 16:19:47+02）：n_qualifying_triggers=108，primary offset 1bp eligible=108 / fills=53 / touch_fill_rate=49.07%（Wilson 95% 39.84%..58.37%）→ verdict=`reject`（<50% gate）；offset sweep：0bp 77/108=71.30%（optimistic top-of-book touch，queue priority not modeled）、2bp 34/108=31.48%、5bp 16/108=14.81%；skip_counts={}。驗證：Mac A2 smoke PASS、A3 smoke PASS、candidate Stage0R smoke PASS、py_compile PASS、`git diff --check` PASS；Linux A2 smoke PASS、A2 PG artifact PASS。**結論**：A2 執行層仍不足以翻案 Stage1/Demo，除非後續另行批准 0bp top-of-book + queue-priority 實證；P0-EDGE next executable 改為 A1 basis accumulation、M4 真 GovernanceHub lease/writeback wiring，或另找新候選。

**v89 增量（2026-05-31 A3/M4 empirical source sync）**：commit `6b654ef2` 已推 `origin/main` 並 fast-forward 到 Linux `trade-core`，Mac/origin/Linux source 三端一致。**A3 BTC/ETH cointegration pairs DRAFT precheck source land**：新增 `helper_scripts/reports/alpha_candidate_stage0r/a3_pairs_precheck.py` + smoke，read-only `market.klines` 對齊 BTC/ETH，計 OLS hedge ratio、Engle-Granger proxy residual AR(1) half-life、shift(1) z-score next-bar replay、two-leg fee-adjusted net edge；只輸出 `reject` / `draft_only` / `observe_more`，不產生 Stage0/Demo/order activation。Linux PG empirical artifact `/tmp/openclaw/empirical/a3_pairs_precheck_20260531.json`：60d 5m aligned bars=14154，verdict=`reject`，corr=0.5297 < 0.75，ADF-like t=-0.8327 > -2.8，half-life=4110.8 bars > 288，n_trades=177，avg_net=-24.28bps，fee_gate=false；**A3 當前不能作 P0-EDGE 新候選翻案**。**M4 Stage1 Linux PG no-writeback empirical DONE**：`pattern_miner_stage_1.py --no-dry-run --symbols BTCUSDT,ETHUSDT --lookback-days 30 --max-drafts 5 --out /tmp/openclaw/empirical/m4_stage1_20260531.json`（第一次因 env 缺 `POSTGRES_HOST` fail-closed，顯式 `POSTGRES_HOST=127.0.0.1` 後 PASS）；source counts：klines=104518 / fills=428 / liquidations=90504 / funding=176；n_candidates=22；selected=5 exploratory；PG status 映射全為 `draft`；writeback_enabled=false；n_drafts=0。驗證：Mac `candidate_stage0r_smoke` PASS、A3 smoke PASS、M4 tests 96/96、M4 `--out` dry-run PASS、py_compile PASS、`git diff --check` PASS；Linux A3 smoke PASS、M4 tests 96/96、A3 PG artifact PASS、M4 PG artifact PASS。**未做/未宣稱**：未接真 GovernanceHub IPC lease acquire/release；未開 M4 writeback；未 rebuild/restart runtime（Python helper/source-only）。

**v88 增量（2026-05-31 M4 Stage 1 source sync）**：M4 Pattern Miner Stage 1 已由 branch `feature/m4-stage1-production-draft-runner` fast-forward 進 `main`（code checkpoint `b25f9048`），把 dry-run scaffold 推到 **non-dry-run source read + candidate compute + gated DRAFT writeback**：新增 `helper_scripts/m4/stage1_production_runner.py`，復用既有 kline/fills/liquidations/funding loader SQL，生成 shift(1) leak-free cross-correlation + funding/liquidation event-window candidates；`pattern_miner_stage_1.py --no-dry-run` 可讀 PG 計算，預設不寫庫；`--enable-writeback` 必須每個 DRAFT row 提供一個真實 `decision_lease_draft_id` UUID，否則 fail-closed 不 INSERT。**重要 schema 修正**：V100 `learning.hypotheses.status` enum 不含 `exploratory`，所以 `exploratory` 只保留為 analysis lane，寫庫統一映射為 PG status `draft`；`draft_writer` 直接拒絕 `status_candidate='exploratory'`，避免首次 production INSERT 因 CHECK enum 失敗；歷史 `GovernanceHubInterface.acquire_lease()` random UUID stub 改為 NotImplemented fail-closed。驗證：`python3 -m pytest helper_scripts/m4/tests -q` 96/96、CLI dry-run PASS、`--no-dry-run` 無 PG env fail-closed exit 2、`compileall` PASS、`git diff --check` PASS、`cargo test -p openclaw_core m4_miner --lib` 46/46（existing ATR deprecation warnings only）。**未做/未宣稱**：尚未接真 GovernanceHub IPC lease acquire/release；尚未 Linux PG non-dry-run empirical；尚未 rebuild/restart runtime。

**v87 增量（2026-05-31 PM sync+deploy）**：(1) **WIP 全收束**：逐檢 dirty worktree 16 檔（role memory/report/operator mirror/feedback memory + `claude_teacher` budget gate），commit `7c854065`；連同本地未推 `be8734a5` / `78153db1` 推至 `origin/main`；再落 `b130c113` TODO checkpoint + `aa92be52` unused reconciler wrapper cleanup。Mac/origin/Linux source 三端一致 `aa92be52b31b3955fb38ae37f7fb0e98be6cd3e3`，main worktree clean，其他登記 worktree clean。(2) **驗證**：`git diff --check`；`cargo test -p openclaw_engine claude_teacher --lib -- --nocapture` 64/64；`cargo test -p openclaw_engine test_build_confluence_config_invalid_weights_falls_back_to_default --lib -- --nocapture` 1/1；`cargo test -p openclaw_engine --lib` 3690 passed / 1 ignored；`cargo test -p openclaw_engine --bin openclaw-engine test_{risk_level,reconciler_label}...` 4/4；`cargo build --release -p openclaw_engine` PASS。(3) **Linux deploy**：`trade-core` atomic rebuild/restart DONE twice as source advanced（`helper_scripts/build_then_restart_atomic.sh`，帶 cargo PATH）；current engine PID `968350`，binary SHA `30adb40cc4dfbc9649c7b338a785932b30bd6c50cc5cfe28fd700a32e5a939a1`，`/proc/PID/exe` SHA == disk SHA；API healthz 200；watchdog `engine_alive=true`，demo/live snapshots fresh；paper snapshot intentionally archived/stale (`disabled=true`, reason=`paper archived 2026-05-23; use Replay Stage 0R + Demo micro-canary`)；engine log 0 panic/backtrace/fatal，C4 notification fail-safe watcher started；TeacherConsumerLoop remains DEFAULT-OFF with BudgetTracker initialized。(4) **DB migration state**：engine boot logged `OPENCLAW_AUTO_MIGRATE=0`（deliberate）；runtime `_sqlx_migrations` now `max=115 / count=108 / version104=true` and `learning.supervised_live_audit` exists. Release build remaining warnings are existing lib/test hygiene (btc_lead_lag unused import, SingleWatcher held provider fields, ma_crossover helper, bin-test private interface), not the removed tasks wrapper.

**v86 增量（2026-05-31 PM 1-4 收口）**：(1) **LG-3 integration 收口**：`feature/lg3-t1` + `feature/lg3-t4` 已整合到 `integration/pm-1-4`；V104 真實 Linux rollback dry-run 首輪抓出 Guard C 對 timestamptz hypertable 誤讀 `integer_interval` 的 blocker，已改為 Timescale `time_interval`/epoch 檢查，重跑 `ROLLBACK` dry-run double-apply 0 ERROR + `V104: all guards PASS` x2，未污染 `_sqlx_migrations`。(2) **Reconciler pagination 續完**：`get_positions(category, None)` 全量掃描改 `settleCoin=USDT` + `limit=200` + `nextPageCursor` 迴圈 + cursor 不前進/超頁 fail-closed；single-symbol point query 不變；D2 ghost converge audit 改標 `confirmed=false` / `dispatched-not-confirmed`，字典補 cursor contract，`BybitApiError::Other` 兩個 dispatch/sync callsite 已顯式分類。(3) **GUI/QC fix pack**：Earn Wave D pending 顯 warn 不顯完整成功；Settings/System config/paper action 不再 truthy 就翻綠；strategy confluence DB/TOML 髒權重先 validate，非法退回既有 verified defaults。(4) **Reports/memory triage**：未批量提交 2026-05-30 raw audit/memory WIP；有矛盾/過期素材（MIT V104 approve 漏 time_interval、E4 first-pass vs deepdive、root PM report wrong location 等）保留在原 dirty worktree，canonical closure report = `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-31--pm_1_4_integration_closure.md`。

**v85 增量（2026-05-30 PM 接手推進）**：(1) **deploy 矛盾解除**：以 build commit `ec995160`（basis rebuild tree）祖先實證 D1/D2/btclag/C4/gap-clean/4-track **全已隨 basis rebuild 編譯進 PID 251791 binary**（部署 binary `e9f01569` 是 /proc/exe 內容 SHA 非 git commit，不可對它做 ancestry）；D2+btclag「DEPLOY BATCHED」標記修正為 DEPLOYED。(2) **🔴 LG-3 V104 幻覺修正（重要 — 自我糾錯）**：先前同日 commit `d9128e22` 誤把「V104 migration 已存在已 apply」寫入帳本，實為 classifier-cancel 期殘留幻覺讀取（違 CLAUDE §四 不可 fake evidence）；PA reality-check + 主會話親驗（`git log --all -S supervised_live_audit -- '*.sql' '*.rs'` 全空 / `sql/migrations/` V103→V106 跳號 / T1 src grep=0）證 **V104 從未存在 = free hole 要全新寫**；紅線反轉 + 新增 Gate 2b（E1 寫真檔後 MIT 重跑 idempotency dry-run）；commit `8d1890a8` forward-fix。(3) **A2 LCS fade QC 審結 = REVISE/HOLD 不推進 Stage1**（avg_net −2.45bps 負 / 證據 0/3 / alpha 執行可達性可疑）→ P0-EDGE-1 closure path (ii) 受挫。(4) **C4 incident-policy dispatch trigger PA spec DONE**（280 行，E1 IMPL 可隨時派）。(5) 清空 E1 reconciler worktree（撞 session-limit 0 代碼成果）。

**v84（前輪）**：v83 + 2026-05-29 cold-audit Wave3/Wave4/P3 全閉環 + 歸檔 + Linux rebuild/deploy。
**v84 增量**：cold audit **全 17 P1 + 15/17 P2 + 7/7 P3 source DONE + Linux runtime DEPLOYED**。Wave3 `7909ca3d`（GUI/async truthfulness + guardian config + SoT docs）+ Wave4 `dc2a15aa`（剩餘 P2 + ML-maturity 設計 ticket）+ P3 `f2b020e5`（7 P3 cleanup）+ 歸檔 `faaa72e2`。8 條 cold-audit 明細已歸檔出 active queue → `docs/archive/2026-05-29--cold_audit_p1_p2_p3_closure_archive.md`。**P2-06 + P2-07 design-complete impl-deferred**（pkgE report，無 migration）。**Linux rebuild+restart DONE 2026-05-29 ~13:57 local**：第一次 `--rebuild` 撞 cargo-not-on-PATH（non-interactive ssh）→ 帶 `PATH=$HOME/.cargo/bin` 重跑成功；engine PID 27582 + snapshot fresh + API healthz 200 + watchdog reset-failed→active。sqlx 啟動 migrate clean。

**v83 增量**：cold audit 修復進入 source checkpoint，但**未 runtime deploy/rebuild**。Wave1 commit `b93d3210` 覆蓋 PkgA/PkgB（live-auth signing-key truthfulness 等）；Wave2 commit `11b9531f` 覆蓋 PkgC/PkgD（edge cost gate / paper→demo promotion freeze / AI route enum 等）。P1-11 `learning.close_maker_audit` reclassified：canonical evidence = V094 `trading.fills.close_maker_*` columns，缺 dedicated table 是 stale spec/TODO artifact，**不建 dead table**。

**v82 增量**：operator 指示解 #2 + #3 完成。**#3 V114 sqlx record DONE**：AUTO_MIGRATE=1 → restart → migrator `Applied(1)` "all guards PASS" → `_sqlx_migrations` version=114 success=t → AUTO_MIGRATE 還原 0。**#2 M11 register-only DONE + DEPLOYED**（commit `d696b1f2` + `1f33301a`，三端 `1f33301a`）。E2 register-only review APPROVE-WITH-CONDITIONS deploy clearance YES；MEDIUM-1 + LOW-1 已修。

**v81 增量**：operator 指示 `restart_all --rebuild --keep-auth` 已執行（02:12 UTC，cargo release 38.84s，engine PID 2248770 + API alive，新 binary 含 Packet C dead-code 模組）。`[48]` PASS（M11 cron）+ `[50]` PASS + `[56]` 不再 FAIL；殘 FAIL = `[74]` + `[16] strategist_cycle_fresh`（pre-existing DB 髒參數 `ma_crossover` confluence weight sum 73≠65；非 Packet C 造成）。三端同步 `58f9519a`。

**v80 增量**：只讀 cold audit 全鏈完成；報告 `2026-05-17--cold_audit_pm_final.md` + PA validated plan。未把 10 個 rejected/downgraded/unproven raw findings 寫入 TODO。PM final-final recheck 已對齊 Mac/origin/Linux `3004edb4`。

**v79 增量**：operator 拍板 `M11.a / PC.B hybrid / 全 10 Qs PA defaults / EA email lettre / BB ATR defer C4 / Q-C 雙路徑 / Q-D 1 attempt / Q-E defer / Q-F dyn / Q-G C4 spec`。Wave 2 全鏈綠：4 E1 IMPL（C1 dispatchers + C2 V114/audit + C3 providers + M11 cron）+ E1 email RealSmtpTransport(lettre rustls openssl=0) + 3 fix round。Review：E2-M11 APPROVE-WITH-CONDITIONS + E2 full Rust APPROVE-WITH-CONDITIONS + E4 regression PASS 3575/3575 + MIT V114 三輪 R3 APPROVE。M11 cron live + `[48]` FAIL→PASS。

**Session markers (v75–v78)**:
- **Session (v75)**：parallel session — runbook v1.0 4-patch + 14d soak D+1。
- **Session (v76)**：本 session 上半 — Wave 5 Packet C SOURCE LAND + 三端同步 + Linux rebuild + A 級 ssh sweep + operator menu [1]-[5]。
- **Session (v77)**：本 session 下半 — Sprint 2 grill-me + PA cross-verify 5 lock decision + hybrid 方案 C ratified。
- **Session (v78)**：Sprint 2 Wave 1 dispatch 4 agent 並行完成 + drift discovery cascade：
  - **PA A M11 schedule** ✅ — 推薦 **Daily 04:00 UTC**（Stage A single-manifest smoke heartbeat 模式）。
  - **PA B Tournament Activation Protocol** ✅ — spec land + 預估激活時點 Sprint 4-5 (~2026-08-09)；1 mid-strong push back acknowledged（N=5/M=15 無 empirical anchor）。
  - **PA C Packet C dispatcher design** ✅ — 5 commit 切片 + 10 條 operator 必答決策 + PA C push back Q5「完整 wire」建議改 hybrid C1+C2+C3 進 Sprint 2 + C4+C5 拉 Sprint 3。
  - **E1 W2-B IMPL** ✅ **NO-OP closure** — disk + git history 證明 W2-B 已於 2026-05-25 `817de10a` IMPL DONE + E2 R2/R3 APPROVE (`aeb8a84b`+`a605af57`) + E4 regression PASS (`fa466361`+`9a82c6d3`)。
  - **4 層 drift discovery**：(1) v76 menu「+ 2FA」描述錯；(2) Q4 grid+ma vs A1/A2 → hybrid C；(3) W2-B 早於 3 天 land 但 v77 + PA report 都認 pending；(4) PM ssh sanity keyword 漏 cron 名 `ac19_alt_bucket_daily_cron`。

---

## §B — Runtime snapshot lineage（舊 PID/deploy 健康快照）

> active TODO §0 只保留 **最新 v87 deploy 健康快照**（engine PID 968350 / SHA `30adb40...` / healthz 200 / `_sqlx_migrations` max=115 count=108 version104=true）。以下舊 deploy 快照 + PID lineage 移此。

- ⚠️ **PM 接手 re-verify 2026-05-29 13:05 UTC（15:05 CEST）— 機器今日有維護重啟窗口**：`last -x` 證 trade-core 今日 **graceful `shutdown`（非 crash/panic）down ~7h（05:37–12:33 CEST = 03:37–10:33 UTC）**，12:36 CEST 開機後當前 boot（uptime 2:28）。影響：(1) demo/live engine + pipeline 該 ~7h 離線 → demo evidence 累積今日缺一段（P0-EDGE-1 / AC-19 ALT bucket / Stage 0R 樣本當日 gap，非 IMPL 問題）；(2) reboot 清空 `/tmp/openclaw/` → cron heartbeat sentinel 全失，僅高頻 panel_aggregator/wave9 已自重建。**crontab 6 cron 全仍裝**（ml_training 03:17 / replay_key_rotation 09:00 / feature_baseline 04:41 / ac19 08:00 / pg_dump 03:00 / m11_replay_runner 04:00 CEST）→ `[77]/[78]/[79]/[80]/[11]` WARN 為 reboot 後 transient，次日各自 fire 自癒。持久 artifact 全存活（`~/pg_backups/trading_ai_2026-05-29.dump` 03:05 CEST 5GB fresh / git / DB）。**PM 已手動 re-fire `feature_baseline_writer_cron.sh`（鏡像 cron env）→ sentinel 15:08 重建 → [78] 回 PASS + baseline 刷新**。engine PID 27582 deploy 仍 intact（binary mtime 13:37 未變，watchdog ActiveEnter 13:58 CEST auto-recover）。穩定性無虞（graceful shutdown = operator/maintenance，非 OOM/panic）。
- ✅ **Engine/API/watchdog alive（2026-05-30 basis-infra+gap-cleanup deploy）** — engine **PID 251791**（`build_then_restart_atomic.sh` flock atomic，`/proc/exe SHA == e9f01569...`，含 gap-cleanup risk.rs split + **basis_panel writer** + 先前 4-track）；demo+live alive；`/api/v1/healthz` **200**；**0 panic / C4 fail-safe dormant / 110017 loop 仍 fixed / basis_panel live（25 sym / 60s flush / latest age ~36s，A1 forward-accumulation 已啟動）**。**V115 applied**（`_sqlx_migrations` max=115 success=true，AUTO_MIGRATE 1→0 已還原）。**PID lineage**：27582(13:57 cold-audit)→113386(15:51 110017 D1)→191366(晚間 4-track)→251791(2026-05-30 basis+gap-cleanup)→**968350(2026-05-31 v87)**。
- ✅ **Engine/API/watchdog alive（13:57 cold-audit deploy，已被 15:51 110017 fix 取代）** — full `restart_all.sh --rebuild --keep-auth`（帶 `PATH=$HOME/.cargo/bin`）；engine PID 27582（mtime 2026-05-29 13:37，cold-audit Wave1-4+P3）；uvicorn PID 27689 4 workers。sqlx 啟動 migrate clean。
- ⚠️ **deploy 教訓**：non-interactive ssh 不載入 `~/.cargo/bin`；`restart_all.sh --rebuild` 在 build 前已 stop services，故 cargo-not-found 會讓 services 短暫全停 → 必帶 `env PATH=$HOME/.cargo/bin:$PATH`（建議 restart_all.sh 內部 source cargo env 作後續 hardening）。
- ✅ **Migration/register drift clean** — `repair_migration_checksum --verify` 2026-05-28 11:34 UTC：`parsed_files=105 / db_rows=105 / drift_count=0`；V099/V100/V109/V113 row 均存在且 checksum 對齊。
- ✅ **Wave 5 V099 physical state** — `system.autonomy_level_config` seed `CONSERVATIVE / system_default / cold_start_default_conservative`；`system.autonomy_level_switch_audit` 18 columns；ENUM values `CONSERVATIVE, STANDARD`；24h cooldown query uses `idx_autonomy_audit_switched_at_utc` Index Only Scan。
- ✅ **Wave 5 Packet B route/UI load + TOTP source backend** — `GET /api/v1/governance/autonomy-level/state` unauth HTTP 401；`autonomy-posture.js` deployed behind GUI auth boundary；TOTP verifier source + tests land；runtime secret file `/home/ncyu/BybitOpenClaw/secrets/vault/autonomy_totp.json` currently missing, switch remains fail-closed and Level 2 remains P0-EDGE evidence-gated。
- ✅ **OPS `[80]` pg_dump freshness fixed** — manual wrapper run 2026-05-28：`/home/ncyu/pg_backups/trading_ai_2026-05-28.dump` 4.6G / md5 `aaca62b0b45262038213f2357383bc97` / governance audit insert；Python freshness 7/7 PASS + `verify_pg_dump.sh` 5/5 PASS；03:00 UTC daily cron installed。
- ✅ **OPS-1 shadow cutover check** — `helper_scripts/canary/healthchecks/csrf_shadow_zero_verify.sh` on `/tmp/openclaw` 近 7d：`verdict=PASS scanned_logs=15 csrf_shadow=0`。
- ⚠️ **Passive healthcheck not green** — 2026-05-28 13:45 UTC ssh trade-core exit 1：FAIL `[48] replay_manifest_registry_growth`, `[74] close_maker_reject_samples`, `[56] live_pipeline_active` (`authorization_json_missing`)；`[80] pg_dump_freshness` direct checker PASS。Ssh 真因分流（2026-05-28）：
  - `[48]` = `replay.experiments` total=23 last_age=407h（M11 register-only cron 已裝後自癒，後續 fire 即綠）。
  - `[74]` = demo 7d `close_maker_attempt=TRUE` 17 rows fallback_reason 分布：`postonly_reject` ×3 / `timeout_taker` ×10 / NULL ×4；**0 row** matches `rate_limit_*` 或 `EC_ReachMaxPendingOrders` = 結構性無法被 demo 流量觸發；gate 軟化屬治理改動 → 入 evidence queue 等 pilot 放量。
  - `[56]` = Operator-only signed `/auth/renew` flow，不可手寫 `authorization.json`；agent 不動。
  - 三條皆不反轉 OPS-1 closure。

---

## §C — Sprint Phase Banner 已 DONE 的歷史 phase 行

> active TODO §2 banner 只保留 active：autonomy 凍結 (Layered Autonomy v2 Wave 5 partial) / alpha mainline (業務 Sprint 2 Alpha Tournament)。以下已 DONE 的歷史 phase 行移此。

```
Sprint 1A-α     DESIGN-DONE / IMPL-PENDING (W0-1.5, 2026-05-21 PM-signed)              v5.7 12 prefix + PM signoff
Sprint 1A-修補  DESIGN-DONE / IMPL-PENDING (D+0~D+5, 2026-05-21)                       v5.8 16 CR + Wave 2.5 paperwork
Sprint 1A-β     DESIGN-DONE / IMPL-PENDING (2026-05-21 PM-signed)                      M1 LAL/M3/M6/M7/M11 + V106/V107/V110/V112/V113 spec + 6 runbook
Sprint 1A-γ     DESIGN-DONE / IMPL-PENDING (2026-05-21 PM-signed)                      M2/M4/M8/M9/M10 + V105/V108/V109/V111 + V103 EXTEND + 3 ADR
Sprint 1A-δ     DESIGN-DONE / TRAIT-STUB-IMPL ✅ FEATURE-LIVE (2026-05-21+ 25)         M5/M12/M13 trait stub (277/393/151+test 495 LOC) + 25 cargo test PASS
Sprint 1A-ε     DESIGN-DONE / IMPL-PENDING (2026-05-21 PM-signed)                      R4 cross-ADR 5C+4H + TW CHANGELOG/CONTEXT + MIT V099-V116 + E5 Mac CI + A3 Wizard
Sprint 1A-ζ     ✅ MAC-SOURCE-DONE + PG-LIVE / LAL+REPLAY-RUNTIME-NOT-PROVEN (2026-05-22)
Sprint 1A-ε P1+P2  ✅ DONE (2026-05-22)                                                  E3 sandbox_admin + PA 5 spec patch + N1/N2/N3
Sprint 1B early IMPL  ✅ SOURCE-CLOSED + FEATURE-LIVE / PARTIAL (2026-05-22+25)         C10 PnL + IntentType + Earn IntentProcessor source-land
Sub-IMPL M3 pre-readiness  ✅ DONE (2026-05-22)                                          4 並行 Track + M3 dispatch gate OPEN
Sub-IMPL M3 metric emitter scaffold  ✅ PASS WITH 5 CARRY (2026-05-22 PM Phase 3e)      6 Track + 8 AC + 51/51 integration
Sprint 4+ §4.1 + Stage A-F + Sprint 5+ Wave 1  ✅ ALL CLOSED (2026-05-23 PM-signed)      Wave A/B + V100/V101/V102 + B-2/B-3 + Stage E Linux deploy
```

**狀態語言（保留供參）**：
- DESIGN-DONE = spec/ADR/runbook/schema spec 文件 land 通過 PM signoff
- IMPL-PENDING = 對應 Rust/Python/SQL 實作未開始
- RUNTIME-NOT-APPLIED = no longer true for V099/V109/V113 as of 2026-05-28；trading_ai 主 PG `_sqlx_migrations` max=115 / count=108 / drift_count=0。Future Sprint2 migrations still require normal Linux PG empirical dry-run + sqlx register discipline.

---

## §D — §3 已 CLOSED workflow

| ID | Workflow | Closure |
|---|---|---|
| **A** | 22 fail-closed 1e-3 invariant Option (c) AMD-09-03 附錄 | ✅ **PA + FA + TW + QC + R4 ALL DONE 2026-05-27** — PA design + FA CONDITIONAL APPROVE + TW §9 附錄 +143 LOC (C1-C6) + QC math PASS + [81] SQL 155 LOC + R4 APPROVE-WITH-MINOR-CASCADE-GAP（7/7 internal PASS / 2 D+1 docs/README+SPEC_REG cascade gap）；C7 cluster center + R4 2 gap defer D+1；pending = E4 regression + operator sign-off |
| **D** | AMD-2026-05-25-01 商業化邊界 cascade | ✅ **CLOSED 2026-05-27** — PA Workflow D cascade 完成 6 files；report `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-27--workflow_d_amd_25_01_cascade.md` |
| **E** | AMD-2026-05-25-02 v5.5 reframe cascade | ✅ **CLOSED 2026-05-27** — PA Workflow E cascade 完成；report `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-27--workflow_e_amd_25_02_cascade.md` |
| **F** | funding_arb (D) 3C TOML deprecation cascade | ✅ **FULLY CLOSED 2026-05-26** — Phase 1 PA spec ✅ + Phase 2 TW (AMD-26-01 + 5 primary + 19 secondary) ✅ + R4 Pass A APPROVE-WITH-DRIFT ✅ + R4 Pass B APPROVE ✅；3 LOW carry-over defer D+7 |

> active TODO §3 保留：Workflow **B**（ADR-0046 basis split，active）、Earn Wave C（operator-gated）、Layered Autonomy v2 Wave 5（partial）、Sprint 2 Alpha Tournament（active）。

---

## §E — §6 P1 queue 已 CLOSED / SOURCE DONE / DEPLOYED 明細

> active TODO §6 保留 active marker（short pointer）；以下完整明細移此。**affects-future-gate 的條目**（如 OPS-2 Phase 2 cutover、110017 D2 pagination/audit、basis-panel/A1 wire、Packet C C4/incident-trigger/C5）**仍保留在 active TODO**，未移此。

### 110017 close-loop 治本鏈（DEPLOYED + VERIFIED）

- `P1-110017-POSITION-DRIFT-CLOSE-LOOP` — ✅ **治本 DONE + DEPLOYED + VERIFIED 2026-05-29**（commit `caf008b6`，三端 `5bf8085c`，Linux atomic deploy engine PID 113386 SHA-verified）。**根因**：13:57 cold-restart reload「本地 qty=2907 / Bybit 已平」TRXUSDT drift 倉；110017 被分類 `Structural`（no-retry、不收斂）→ PHYS-LOCK 每 tick 重發 reduce-only close ~1.4/sec 自持迴圈（demo only，無真錢）。**修法**：`dispatch.rs` 110017 `Structural`→`NoOp` + guard（`is_primary ∧ reduce_only ∧ qty==0 全平 form ∧ 110017`，per BB APPROVE-WITH-MANDATORY-GUARD）+ 消費端 `converge_exchange_zero_close` 復用 `upsert_position_from_exchange(size=0)` 移本地倉（0 record_trade/realized/Kelly 污染）。chain 全綠：PA RCA → E1 r1+r2 → BB APPROVE-mandatory-guard → E2 APPROVE-WITH-CONDITIONS → E4 PASS（lib 3609/0）。部署驗證：classify 確認（new engine start 15:51:17 後 0 筆 110017 reject）；loop 確認停（TRXUSDT orders last 60s=0，position removed）。ref RCA `2026-05-29--phys_lock_zero_position_close_loop_rca.md` + BB `2026-05-29--retcode_110017_convergence_semantics.md`。
- `P2-110017-D2-RECONCILE-QTY-GT-ZERO-DRIFT` — ✅ **SOURCE DONE 2026-05-29 commit `a5e1ded1` / DEPLOYED 2026-05-30**（隨 basis rebuild；`a5e1ded1` 為 build commit `ec995160` 祖先，PID 251791 binary 已含）。D2 = position_reconciler `DriftVerdict::Ghost` 週期收斂：新 `PipelineCommand::ConvergeExchangeZero` → 復用 D1 `converge_exchange_zero_close` + audit→`engine_events`。全鏈綠 PA→E1(r1+r2)→BB(RETURN 1 CRITICAL→re-APPROVE)→E2 APPROVE-WITH-CONDITIONS→E4 PASS(lib 3619/0)。BB CRITICAL 攔截：主 fetch `get_positions(None)` 無分頁（Bybit limit=20）→ 持倉>20 時 page2+ 真倉誤判 Ghost→誤刪真倉含 live money；E1 加 S-6 單-symbol point-query gate 修畢。2 follow-up（pagination 修法 B + audit removed_position 語意）已在 active TODO（pagination/audit 兩 P2/P3 SOURCE DONE on `integration/pm-1-4`，pending BB/E2/E4 review）。ref D2 spec + BB report `2026-05-29--d2_reconcile_ghost_exchange_truth.md`。
- `P3-BTCLEADLAG-FENCE-TEST-DRIFT` — ✅ **DONE 2026-05-29 commit `af92e2ca` / 真生產 bug（非 test drift）** — git -S 證 test 斷言來自 2026-05-23 archive policy（a4c spec v1.5 §6.2 reference impl = `should_spawn=diagnostic_enabled`），但 source `should_spawn_btc_lead_lag_producer` 內部仍讀 ENABLE_PAPER → PAPER=1 真 spawn（main.rs 印「ignored」warn 掩蓋）→ producer 違 archive policy 在 paper 真 spawn。E1 修 source（gate 僅 diagnostic flag），E2 確認方向對 + demo/live 無 regression，E4 PASS（drift test FAIL→PASS，9/9）。✅ DEPLOYED 2026-05-30（隨 basis rebuild PID 251791）。LOW follow-up：main.rs btc_lead_lag tracing var 近-dead 清理。
- `P3-SESSION-CLEANUP-FA-AUDIT-FOLLOWUPS` — ✅ **DONE + DEPLOYED 2026-05-30 commit `46e0e825`** — 3 LOW 結構債全解（E1→E2 APPROVE→E4 PASS）：(G1) `risk.rs` 822→605 — C4 escalate handler + 4 helper pure-move 出 `handlers/notification_failsafe_escalate.rs`（caller re-export 零改，byte-equivalent，cargo --lib count 不變）；(G2) `main.rs` btc_lead_lag tracing var 保留 + 中文註釋標 observability-非-決策；(G3) `single_watcher.rs` 註解對齊 §2.4。隨 basis-infra deploy（PID 251791）生效。

### OPS-1 series（CLOSED）

- `P1-OPS-1-E1-DISPATCH` — ✅ **IMPL DONE 2026-05-27 commit `65e78437`** round 1；ref `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-27--ops_1_https_secure_cookie_impl.md`
- `P1-OPS-1-E1-ROUND-2` — ✅ **CLOSED 2026-05-28 commit `22466a81` supersedes `07027493`** — original round 2 8 fix + A3 R2/R3/R4 close：CSRF 403 friendly toast + auto reload, cert trust runbook + install hint, CSRF/CSP shadow 7d + `csrf_shadow_zero_verify.sh` PASS 0；target tests 34/34 PASS；Linux runtime repo pulled
- `P1-OPS-1-PROXY-HEADER-SPOOF-RISK` — ✅ **CLOSED 2026-05-27 by E2 verify PASS** — `auth_routes_common.py:60-94` `_proxy_headers_trusted()` env gate fail-closed verified；偽造 X-Forwarded-Proto 無效；regression batch B 10/10 PASS

### OPS-2 series（CLOSED；Phase 2 cutover + 3 carry-over follow-ups 仍在 active TODO）

- `P1-OPS-2-SECRET-SPLIT` — ✅ **IMPL DONE 2026-05-27 commit `65e78437`** Phase 1 — E1 477 LOC (Rust 371 + Python 74 + Bash 32) + 24/24 cargo + 8/8 pytest + 10/10 batch B + cross-lang HMAC `1b2b18d7...` byte-identical 三端 + 5 PA hidden risk mitigation；E2 APPROVE-CONDITIONAL 0 BLOCKER/HIGH；A3 8.0/10；CC 16/16 + 9/9 + 4/4 hard gate；Mainnet env-var fallback closed 紀律 reconcile PASS。ref E1 + E2 + A3 + CC reports
- `P1-OPS-2-RUNBOOK` — ✅ **CLOSED 2026-05-27 PA draft v0.9** — `docs/runbooks/credential_rotation.md` 495 行 / 12 章 / Emergency RTO ≤5-7min / 4 audit SQL
- `P1-OPS-2-RUNBOOK-V1.0-PATCH` — ✅ **CLOSED 2026-05-28** — PA delivered 4-patch v1.0：(1) §4.2.1 quote box Phase 1 backward-compat note (2) §10.1.1 `grep -c ops2_secret_split_phase1_fallback ...=0` invariant + AC table (3) §10.5 cross-lang HMAC sanity check（pinned hex `1b2b18d7...8b78fc`）(4) §13 6-sub Phase 2 cutover SOP；495→687 行（+192）；ref `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-28--ops_2_runbook_v1_0_patch.md`
- `P1-OPS-2-CI-FLAKINESS-TEST-LOCK` — ✅ **DONE 2026-05-29 source / E2 2-round APPROVE / Linux flake verify carry-over** — E1 把 openclaw_engine lib crate 內 12 個分散 env-test mutex 合併成單一 `crate::test_env_lock::guard()`。E2 round 1 抓 1 HIGH（真 race = `bybit_private_ws_status_writer` 無鎖 `remove_var("OPENCLAW_BASE_DIR")` vs Group A `edge_estimates` 持鎖 set_var 重疊）；E1 round 2 修畢；E2 round 2 APPROVE「HIGH closed / zero residual」。Mac `cargo test --lib` 3598/0 ×3。無新依賴（未引 serial_test，RP14）。carry-over：Linux 並發 --lib flake 驗證（≥5 輪）留低交易維護窗口跑（cfg(test)-only 不影響 release）。
- `P3-OPS-2-CI-FLAKINESS-BIN-CRATE-LOCK` — ✅ **DONE 2026-05-29 commit `af92e2ca`** — bin crate（main.rs）新 `#[cfg(test)] test_env_lock`；main_boot_tasks + live_auth_watcher_tests 改用 bin 共用鎖。E2 APPROVE + E4 PASS（bin 67/67）。
- `P1-OPS-2-RESTART-ALL-CP-ATOMIC` — ✅ **DONE 2026-05-29 / E2 APPROVE** — `restart_all.sh:157-168` OPS-2 Phase 1 seed 由裸 `cp` 改 write-to-tmp（`.tmp.$$`）→ chmod 600 → `mv -f` atomic rename，fail 則 `rm -f tmp; exit 1`。E2 empirical 3-path 驗 atomic 成立 + chmod-before-mv 消除 644 窗口 + first-seed guard 正確。`bash -n` PASS。
- `P2-OPS-2-GITLEAKS` — ✅ **SOURCE DONE 2026-05-29 / E2 APPROVE / install + FP-tuning = operator follow-up** — E1 交付 4 物（版控內，未動 `.git/hooks/`）：`helper_scripts/git_hooks/pre-commit`（gitleaks 在 PATH → `gitleaks protect --staged --redact` 有 finding exit 1；缺工具 → 中文 WARN + exit 0 warn-and-pass）+ `install_git_hooks.sh`（`git rev-parse` 定位 repo root，無硬編碼，refuse-clobber + `--force` + .bak backup）+ `.gitleaks.toml`（`[extend] useDefault=true` + allowlist 排除 cross-lang HMAC test fixture `1b2b18d7…`）+ SCRIPT_INDEX 條目。E2 APPROVE。operator follow-up：`brew install gitleaks` + Linux 裝 + 跑 install + 首次實跑收集 FP 調 allowlist。

### OPS-3 / OPS-4 series（CLOSED；operator deploy residual 仍在 active TODO §0/§1）

- `P1-OPS-3-OPERATOR-CONFIRM-5` — ✅ **CLOSED 2026-05-26 sequential confirmation** — C-1 Spain (EU member, MiCA-compliant, NOT in 16 restricted) ✅ / C-2 ≥ Advanced L2 ✅ / C-3 2 demo keys + 33d TTL ⚠ pending OP-1 a-f mainnet reissue / C-4 defer Spanish tax planning to first Live + 30d (~2026-10) / C-5 accept Earn risks, first stake $100-200 USDT Flexible only ✅；signoff doc `srv/docs/governance_dev/2026-05-26--bybit_compliance_signoff.md`
- `P1-OPS-4-GAP-A-WATCHDOG-SYSTEMD` — ✅ **IMPL DONE 2026-05-27 commit `65e78437`** — `helper_scripts/systemd/openclaw-watchdog.service` (Restart=always + StartLimitBurst=10/600s) + install_watchdog_service.sh；E2 APPROVE-WITH-MINOR；RTO ≤5min 數學成立
- `P1-OPS-4-GAP-F-ENGINE-SYSTEMD` — ✅ **IMPL DONE 2026-05-27 commit `65e78437`** — `helper_scripts/systemd/openclaw-engine.service` (Restart=on-failure + RestartSec=10 + StartLimitBurst=5/300s) + install_engine_service.sh；E2 APPROVE-WITH-MINOR
- `P1-OPS-4-GAP-A-F-MINOR-FIX` — ✅ **CLOSED 2026-05-27 commit `07027493`** — 4 fix in-place: Requires=空值刪除 + verify warn/error 區分 + root user guard exit 12 + README reset-failed 提示；bash -n PASS
- `P1-OPS-4-GAP-B-PG-RESTORE-DRILL` — ✅ **IMPL DONE 2026-05-27** chain round 1+2+3 — MIT 3/3 deliverable: `srv/helper_scripts/db/post_restore_validation.sql` (330 LOC / 9 query / 8/9 PASS Linux SSH empirical) + `srv/docs/runbooks/pg_restore_drill_sop.md` (572 LOC / 10 章 / 7 scenario estimates median 14h worst 22.5h) + `srv/docs/CCAgentWorkSpace/MIT/workspace/templates/pg_restore_drill_report_template.md` (239 LOC) + cite `repair_migration_checksum.rs`；4/9 invariant re-verify mandatory I1/I2/I7/I8。**注意**：first qualifying restore drill 仍是 operator-gated hand-action（active TODO §0/§1 殘留）。
- `P1-OPS-4-GAP-D-PG-DUMP-CRON` — ✅ **IMPL DONE 2026-05-27** chain round 1+2+3 — E1 6/6 deliverable: `install_pg_dump_cron.sh` (132 LOC w/ MED-3 `_validate_cron_env_value`) + `trading_ai_pg_dump_cron.sh` (181 LOC EXCLUDE evaluations + governance_audit_log INSERT 2/4 event_type + retention 30d) + `verify_pg_dump.sh` (129 LOC) + `V113__governance_audit_log_pg_dump_event_types.sql` (Guard A/B) + `check_pg_dump_freshness.py` (662 LOC w/ MED-1 `_platform_guard()` + MED-2 heartbeat cross-check) + `passive_wait_healthcheck/{__init__,checks_cron_heartbeat,runner}.py` wire；E2 r1+r2 + E4 r1+r2 + QA E2E 全 GREEN。daily 03:00 UTC cron installed 2026-05-28 + `[80]` direct 7/7 PASS。

### Wave 5 Packet C（DONE 切片；C4/incident-trigger/C5 wire 仍在 active TODO）

- `P1-PACKET-C-3WAY-DISPATCHER-WIRE-DISPATCH` — ✅ **C1+C2+C3 IMPL DONE + 全 review chain 綠 (v79 2026-05-28) / C4+C5 defer Sprint 3** — operator 拍 PC.B hybrid + 全 10 Qs PA defaults + EA(lettre)。**C1 dispatchers**：slack(Incoming Webhook) + email(Gmail SMTP App Password + RealSmtpTransport lettre 0.11 rustls openssl=0) + console_banner(vault file 持久化直到 ack) + three_way(NotificationDispatcher impl)。**C2**：V114 `observability.notification_failsafe_events` 17-col hypertable（GRANT-before-compression + nested EXCEPTION idempotent，MIT R3 三跑 EXIT0 deploy-ready）+ PgAuditEmitter + ack stub。**C3**：wall_clock + RestPositionProvider + BybitExchangeStopSync + SharedFailsafeWatcher(single shared, claim-before-await 並發 guard)。Review 全綠：E2 full Rust APPROVE-WITH-CONDITIONS（0 BLOCKER）+ E4 3575/3575 PASS + MIT V114 R3 APPROVE。Secret fail-closed（缺檔 disable，同 TOTP pattern）。ref PA spec `docs/execution_plan/specs/2026-05-28--packet_c_3way_dispatcher_wire_spec.md`。
- `P1-PACKET-C-HIGH1-BANNER-CHANNEL-WEIGHT` — ✅ **DONE 2026-05-29 commit `3423f0f7`** — PA ruling：banner = last-resort visibility 非 delivery；`AllFail` = Slack ∧ Email 兩 push 全 false（banner 不計判定仍進 failed 清單供 audit）；無需 AMD amendment。E1 修 `three_way.rs compute_outcome` push-weighted AllFail + T3/T4/T5 翻轉 + T3b 邊界 test；E2 APPROVE（8 組合全對）+ E4 PASS（lib 3610/0）。不需 deploy（failsafe 未 runtime-wire）。解鎖 C4 前置(1)。ref `2026-05-29--packetc_high1_banner_channel_weight_ruling.md`。
- `P1-WAVE5-PACKET-C-E2-E4-INTEGRATION` — 🟡 **ENGINE INTEGRATION SOURCE LAND + LINUX REBUILD DONE 2026-05-28**（前一輪狀態快照；現已被 v87 deploy + C4 source-land 取代）— commit `920f8299` lands `openclaw_engine::notification_failsafe` module (1099 LOC inc 14 mock tests + 5 trait seam)；整條 chain 已接 observe AllFail → 1h timer → SM-04 → active_lock_profit → ExchangeStopSync → audit emit。`DEFAULT_TIMEOUT_MS=3_600_000` compile-time hard-coded。`cargo test -p openclaw_engine --lib` 3482/3482 PASS。Linux 16:18 UTC restart_all --rebuild engine PID 2044407。Minimal slice 不接 pipeline_ctor。**後續**：C4 pipeline wire 已 SOURCE DONE 2026-05-29 commit `a8ba146c`（active TODO 追蹤 incident-trigger + C5）。
- `P2-PACKET-C-C4-PIPELINE-WIRE` — ✅ **SOURCE DONE 2026-05-29 commit `a8ba146c` / DEPLOYED 2026-05-30 / 半 wire dormant** — C4 把 fail-safe 接進 runtime（修正母 spec fossil model：用 in-band `PipelineCommand::NotificationFailsafeEscalate` 非不存在的 `Arc<RwLock<TickPipeline>>`）+ ATR 注入（kline_manager atr14）+ exchange sync 走既有 `stop_request_tx`（無新 client，RP1）+ paper 雙 noop + single-shared watcher + 3 e2e test。全鏈綠：PA spec → E1 → E2 APPROVE-WITH-CONDITIONS → BB APPROVE-WITH-GUARD（set_trading_stop 安全：誤平結構不可能，Bybit 拒單 fail-closed）→ E4 PASS（lib 3623/0）→ QA ACCEPT-WITH-CONDITIONS（0 誤升/0 誤打 stop）。**誠實：C4 = 機制 live 但 incident-trigger 未接 → escalate dormant**（active TODO `P2-INCIDENT-POLICY-DISPATCH-TRIGGER` 追蹤）。
- `P2-M11-REPLAY-RUNNER-SCHEDULE-PROPOSAL` — ✅ **PROPOSAL DONE 2026-05-28 + INSTALLED + LIVE 2026-05-28** — proposal land + Operator mirror；PA A 推薦 cadence Daily 04:00 UTC；`[48]` healthcheck cron 首次成功 fire 後 ≤24h 內變 PASS。✅ INSTALLED + LIVE 2026-05-28（commit `b43481f7`；smoke run + `[48]` FAIL→PASS）。
- `P2-M11-SMOKE-ZOMBIE-DESIGN-FIX` — ✅ **DONE + DEPLOYED 2026-05-29**（修法 a register-only）— commit `d696b1f2`(wrapper) + `1f33301a`(wave9 allowlist + install echo)；三端 `1f33301a`。smoke 移除 run dispatch 保留 register（run 是 zombie 唯一源）。deployed wrapper dry-run 驗：`/replay/run` 3 hits 全註釋 + 0 run_state running + experiments fresh row + [48]/[50] PASS。E2 APPROVE-WITH-CONDITIONS deploy clearance YES；2 follow-up 修畢。首例 zombie `6532fc38` operator cleanup。殘 follow-up（Sprint 3 Phase A OQ-2）：`m11_*` event_type enum migration 停 `audit_write_failed` piggyback + PA proposal §4.2 register+run→register-only deviation 文字回簽（active TODO 追蹤）。

### basis-panel infra（DEPLOYED；A1 wire 仍在 active TODO）

- `P2-BASIS-PANEL-INFRA` — ✅ **DONE + DEPLOYED 2026-05-30 commit `ec995160`/`e63a00e0`** — `panel.basis_panel`（V115 hypertable，14d retention）+ `BasisAggregator` writer（panel_aggregator/basis.rs，mirror funding_curve，60s flush，`basis_pct=(last/index-1)*100` signed，fail-closed index≤0，latest-value cache sparse）+ Python `[66]` freshness wire。全鏈綠：PA spec → MIT V115 Linux-PG double-apply dry-run PASS → E1(r1+r2) → E2(RETURN dead-pub-fn→APPROVE) → E4 PASS（lib 3634/0）。DEPLOYED：V115 applied + engine PID 251791 + basis_panel live 25 sym / 60s flush。**A1 consumer wire = `P2-A1-RUNNER-WIRE-TO-BASIS`（active TODO，trigger basis_panel 累積 ≥14d ~2026-06-13）**。

### Earn Wave C/D（CLOSED 切片；OP-blocked + Wave D Rust HMAC 仍在 active TODO）

- `P1-EARN-WAVE-C-FIRST-STAKE-RUNTIME` source-layer — **SOURCE-LAYER FULLY CLOSED 2026-05-26 / OPERATOR-BLOCKED on OP-1** — IntentProcessor Earn branch ✅ + OPENCLAW_ALLOW_MAINNET=1 ✅ + earn_routes.py 1221 LOC (6 endpoint + 5-gate + HMAC sig verify) + tab-earn.html 516 + earn-tab.js 750 + replay_earn_preflight.py 799 + test 27+14 PASS。**仍阻 7 OP hand action + Wave D Rust IPC**（active TODO 追蹤）；PG `learning.earn_movement_log` still 0 rows。

### funding_arb deprecation cascade（CLOSED；D+7 carry-over 仍在 active TODO）

- `P1-LG-3-AC-CORRECTION` — ✅ **CLOSED 2026-05-26 / VERIFIED 2026-05-27** — PA delivered (1) spec v2 amendment 83 行 (V094→V104 1:1 + V099/V100 移除 + §2.4A wording drift 移除) (2) V104 scaffold 378 行 `srv/docs/execution_plan/specs/2026-05-26--v104-lg3-supervised-live-audit-migration.md` (10 章 + 21 col + 4 CHECK + hypertable + Guard A/B/C + 4-step PG dry-run) (3) TODO §1 row reframe applied；2026-05-27 PA verify pass：3/3 drift FULLY COVERED + sql/migrations/ empirical V104 FREE。**注意**：此為 P0-LG-3 的 AC-correction 子任務 closure；P0-LG-3 主條目（現 SOURCE INTEGRATED / runtime not deployed）仍在 active TODO §1。
- `P1-FUNDING-ARB-DEPRECATION-CASCADE` — ✅ **FULLY CLOSED 2026-05-26** Phase 1+2 + R4 Pass A+B APPROVE — PA spec (551 行) + TW AMD-26-01 (372 行) + 5/5 primary + 19/19 secondary + R4 Pass A APPROVE-WITH-DRIFT + R4 Pass B APPROVE 0 dangling；commits `6a20b9ea` + `e913adbf` 三端同步；3 LOW carry-over defer D+7（active TODO `P3-WORKFLOW-F-D7-CARRYOVER` 追蹤）。
- `P1-EDGE-2` (funding_arb) — ✅ **ARCHIVE-READY 2026-05-26 per AMD-2026-05-26-01** — operator chose (D) 3C TOML deprecation closure；funding_arb V2 Retired closed；ADR-0018 status 升格；strategy roster 5→4 textbook。**no-revive**：revive 須走 AMD amendment + ADR-0046 Accepted + 5-gate + Stage 0R replay preflight。ref `P1-FUNDING-ARB-DEPRECATION-CASCADE` + AMD-2026-05-26-01 §3+§4。

### Reclassified spec-drift / won't-implement（NOT-A-BUG，no-revive）

- `P1-LEARNING-CLOSE-MAKER-AUDIT-TABLE-MISSING` — ✅ **CLOSED AS SPEC-DRIFT / NOT-A-BUG 2026-05-29** — PA Package C call-path proof: writer/readers/healthchecks use V094 `trading.fills.close_maker_attempt` + `close_maker_fallback_reason`; `learning.close_maker_audit` has 0 source writer/reader and would be dead schema. **No migration; no table creation（no-revive）**。ref `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-29--cold_audit_pkgC_evidence_promotion_spec.md` §3 + commit `11b9531f`。
- `P2-WATCHDOG-STATUS-JSON-WRITER` — ✅ **CLOSED won't-implement 2026-05-29（PA 證 vestigial）** — grep 全 repo 0 consumer open/stat `watchdog_status.json`；watchdog 設計本不寫此檔（`--status` 即時算後 print stdout，落檔的是 `watchdog_state.json`/`canary_events.jsonl`/`watchdog.log`）；engine-liveness file-observability 已由 `pipeline_snapshot.json` + `--status` 覆蓋。runbook GAP-H 降 RESOLVED。doc-only close，0 code。**no-revive**。
- `P3-HYGIENE-OPTION-E-FD-INHERIT-CORNER-CASE` — ✅ **CLOSED 2026-05-29 ALREADY-FIXED（stale duplicate）** — `restart_all.sh:555` engine spawn 已含 `0<&- 200<&-`（commit `5e8302f7` 2026-05-25）；`build_then_restart_atomic.sh` Phase 5 透過 `--engine-only` 走同一 spawn。ticket 與修復同日，stale 重複非真 gap。

### 2026-05-25 早期 closure 批（commit-linked，feature/source closed）

- `P1-OP1-IP-WHITELIST-CORRECTION` — ✅ **OPERATOR-DECIDED 2026-05-25** — 選項 (b) Bybit "no IP restriction"；OP-1-d 觸發含 OP-1
- `P1-ENV-OPENCLAW-ALLOW-MAINNET-SET` — ✅ **FULLY CLOSED 2026-05-25** by `a51c1a1f` + `a775b5b9` + `a7ada6cf` + `ae7b207c`；env count 12→13 / persistence verify across restart
- `P1-C10-SYNTHETIC-SPOT-CLOSE-PNL-FALLBACK` — ✅ **SOURCE-LAYER CLOSED 2026-05-25** commit `015b9735` + E2/E4 round 2 PASS
- `P1-INTENTTYPE-DIRECTION-MISMATCH` + `-V2` — ✅ **CLOSED 2026-05-25** commit `015b9735` + `bbb21c56`
- `P1-SPRINT-1B-C10-CLOSURE-GAPS` — ✅ **SOURCE/FEATURE CLOSED 2026-05-25** full chain done；7d demo observation → 2026-06-01
- `P1-ENGINE-BINARY-SPRINT-1A-IMPL-DEPLOY` — ✅ **FULLY CLOSED 2026-05-25 01:18 UTC** by Hygiene Option E A+B 並行；PID 350616 → ... → 374287；proc SHA match disk
- `W-S4-AC1B-HEALTHCHECK` — ✅ **CLOSED-VERIFY 2026-05-25 recheck** — 6 health domain × 30min 全 PASS
- `P1-V107-SQL-GUARD-A-LOGIC-DRIFT` — ✅ **CLOSED 2026-05-22** by `c706c49c`；sandbox Round 1+2 PASS
- `P1-PG-CHECKSUM-ALIGNMENT-DECISION-2-C` — ✅ **CLOSED-VERIFY 2026-05-28** for current landed SQL set；trading_ai `_sqlx_migrations` max=113/count=105；`repair_migration_checksum --verify drift_count=0`
- `P1-SANDBOX-SQLX-METADATA-ALIGNMENT` — ✅ **FULLY CLOSED 2026-05-24** Round 1+2；sandbox V100+ checksum 對齊 trading_ai 主 DB sha256

> active TODO §6 保留的 active P1/P2/P3（未移）：`P2-RECONCILER-GET-POSITIONS-PAGINATION`、`P3-110017-D2-AUDIT-REMOVED-SEMANTICS`、`P3-110017-CONVERGE-AUDIT-OBSERVABILITY`、`P3-110017-BB-DOC-FOLLOWUPS`、`P1-OPS-2-PHASE-2-CUTOVER`、`P1-OPS-2-14D-SOAK-OBSERVE`、`P1-OPS-2-DRY-RUN`、`P0-OPS-4-GAP-B-D-OPERATOR-DEPLOY`、`P3-OPS-4-PG-DUMP-EVENT-EXTEND`、`P2-OPS-4-GAP-B-D-UNIT-TEST-GAP`、`P1-WAVE5-TOTP-BACKEND`(deferred)、`P1-SPRINT2-STAGE0R-REPLAY-PREFLIGHT-DISPATCH`、`P1-A1A2-STAGE0R-RUNNER-IMPL`、`P2-A1-RUNNER-WIRE-TO-BASIS`、`P3-MARKET-TICKERS-INDEX-MARK-DEAD-PERSISTENCE`、`P3-BB-STRATEGIES-30D-CATCH-UP-CLOCK`、`P2-INCIDENT-POLICY-DISPATCH-TRIGGER`、`P2-PACKET-C-C5-GUI-BANNER-ACK-ROLE`、`P1-OPS-2-HOTRELOAD`、`P2-OPS-2-AUDIT-ENDPOINT`、`P2-OPS-2-CRON-DRIFT`、`P2-OPS-2-RUNBOOK-HEALTHCHECK-SQL`、`P3-OPS-2-RUNBOOK-EMERGENCY-AUDIT-CONTRACT`、`P1-EARN-WAVE-C-FIRST-STAKE-RUNTIME`(OP-blocked)、`P2-EARN-WAVE-D-CONTRACT-INTEGRATION-TEST`、`P1-EARN-WAVE-D-RUST-HMAC-CANONICAL-FORM`、`P1-OP1-BYBIT-ENDPOINT-FILE-MISCONFIG`、`P3-WORKFLOW-F-D7-CARRYOVER`、`P1-LG-5`、`P1-HALT-TRIGGER-ROOT-CAUSE-INVESTIGATION-1`、`P1-LEASE-1`、`P1-EDGE-P2-3-PH1B-DYNAMIC-BACKOFF-FOLLOWUP`、`P1-INTENTYPE-FIELD-VISIBILITY-DEFER`、`P3-SUB-AGENT-HYGIENE-SOP-CARGO-TEST-AFTER-ATOMIC`、`COLD-AUDIT-V80-CLOSURE`(pointer)。

---

## §F — §7 Operator checklist 已 DONE 行

- **D+0 NEW (2026-05-26)** confirm AMD-2026-05-25-01 + AMD-2026-05-25-02 — ✅ **DONE 2026-05-27**（兩 AMD operator APPROVE；Workflow D + E cascade completed）
- **D+1-D+2** AMD-21-01 v2 Layered Autonomy 最終 sign-off + Wave 5 Packet A/B kickoff — ✅ **DONE 2026-05-28**（operator APPROVE 三 AMD 同輪；Packet A V099 + Packet B API/GUI posture landed）
- **D+3** P0-FUNDING-ARB-DECISION-FORCE 升等拍板 — ✅ **CLOSED 2026-05-26 operator chose (D)**（cascade Workflow F NEW）

> active TODO §7 保留的 operator action（未移）：D+0 canary rename commit（已 cf61d1f0）、D+2-D+3 OP-1 a-f mainnet key 重發 / OP-2 Stage 0R Earn variant 仲裁 / OP-3 first stake、D+5 P0 gates closure ETA、W12 Sprint 2 Alpha Tournament 派發、W18-21 Sprint 4 first Live。

---

## §G — §8 Backlog cluster 已 CLOSED 條目

### §8.1 Cluster 1 — Independent Parallel — ✅ **6/6 全 CLOSED 2026-05-27**
1. **Workflow A** — ✅ PA design + FA pre-verify CONDITIONAL APPROVE + TW AMD-09-03 §9 patch +143 LOC + QC math sanity PASS + [81] SQL prototype；pending = E4 + R4 + operator sign-off
2. **Workflow D** — ✅ AMD-25-01 cascade 6 files
3. **Workflow E** — ✅ AMD-25-02 cascade 6 files
4. **Workflow F** — ✅ CLOSED 2026-05-26 funding_arb deprecation
5. **Workflow J** — ✅ CLOSED 2026-05-27 by PA inline CORRECTION
6. **OPS [78]** — ✅ CLOSED 2026-05-27 by E3 (crontab now installed)

### §8.5 PA Condition Follow-up（C2 closed）
- **C2** ADR-0030 4-gate threshold 副帳場景 verify — ✅ **CLOSED 2026-05-27 by AMD-2026-05-25-02 §4.2** — 副帳 Y2+ enable 條件 = ADR-0030 4-gate + AMD-25-02 Gate 5 Moat 共 5-gate 全 PASS；framework 已 lock，無 verify work

> active TODO §8 保留：§8.2 Cluster 2（Workflow B Phase 1/2/3）、§8.3 Cluster 3 殘留 operator-gated（OP-1/OP-2/OP-3 + P0 gates ETA）、§8.4 Sprint 2 Alpha Tournament dispatch、§8.5 C3/C4 未完 condition follow-up。

---

## §H — §9 Cascade Pending 已 CLOSED 條目

| 來源 | Cascade 目標 | Owner | Closure |
|---|---|---|---|
| **AMD-2026-05-25-01** | docs/README AMD list / SPECIFICATION_REGISTER count / TODO §8 Stream 2 cleanup / AMD-04+05 supersede markers | PA Workflow D | ✅ **CLOSED 2026-05-27** — operator APPROVE 2026-05-27；AMD-25-01 Status Active；docs/README + SPECIFICATION_REGISTER 已 land entry；TODO 無 Stream 2 active task 殘留；report `2026-05-27--workflow_d_amd_25_01_cascade.md` |
| **AMD-2026-05-25-02** | docs/README AMD list / SPECIFICATION_REGISTER count / AMD-25-01 §3.2 cross-ref / ADR-0030 cross-ref / AMD Status Active / TODO §8.5 C2 cleanup | PA Workflow E | ✅ **CLOSED 2026-05-27** Cascade 完成；report `2026-05-27--workflow_e_amd_25_02_cascade.md` |
| **drift audit 2026-05-25** | TODO active state update + v5.8 文檔 patches (DONE 10 patches) | PM | ✅ Cascade 完成 |
| **operator decision 2026-05-26 (D) funding_arb deprecation** (Workflow F) | (1) PA spec 551 行 (2) TW AMD-26-01 372 行 + 5 primary + 19 secondary (3) R4 Pass A APPROVE-WITH-DRIFT (4) R4 Pass B APPROVE | PA → TW → R4 | ✅ **CLOSED 2026-05-26** Cascade 完成；3 LOW carry-over defer D+7 |

> active TODO §9 保留：**AMD-2026-05-21-01 v2 Wave 5**（🟡 partial — Packet C engine integration + runtime TOTP enrollment 殘留）+ **ADR-0046 (Proposed)**（Sprint 1A-δ/ε 平行 land）。

---

## §I — §15 衝突仲裁已 WITHDRAWN / OBSOLETED 條目

| # | 衝突 | 解 |
|---|---|---|
| 1 | LG-3 IMPL DISPATCH ↔ P0-FUNDING-ARB-DECISION-FORCE | ❌ **WITHDRAWN 2026-05-26 / VERIFIED 2026-05-27** — FALSE dep（LG-3 supervised live SM 為所有策略 supervised live activation gate，與 funding_arb retired/active 解耦 per AMD-2026-05-26-01）。真衝突 = V### 號占用（LG-3 取 V104 FREE per 2026-05-27 empirical）+ v56 P0 Layer B + 24h gate ~2026-05-30。ref `P1-LG-3-AC-CORRECTION`（CLOSED） |
| 5 | Workflow B Phase 2 V117 ↔ funding_arb V2 active timing | ❌ **OBSOLETED 2026-05-26 per AMD-2026-05-26-01** — funding_arb V2 Retired closed；V117 重新 framed 為 ADR-0046 future redesign slot 的 V3 schema 預留；revive 須走 AMD amendment + ADR-0046 Accepted + 5-gate + Stage 0R replay preflight |

> active TODO §15 保留 active 衝突仲裁：#2（engine STOPPED ↔ verdict 視窗）、#3（W-AUDIT-9 canary ↔ ExecutorAgent shadow）、#4（Sprint 1A 順序 ↔ cross-V### dep）、#6（Cluster 並行 ↔ multi-session race）、#7（Sprint 2 Stream B V108/V109/V111 ↔ Wave-X2 V099 collision）。

---

## §J — §-1 歷史 closure 摘要全文（>14d 滾出 active window 的明細）

> active TODO §-1 保留最近 ≤14d 的 closure 摘要（2026-05-29~31）；以下 2026-05-28 及更早的逐日 closure 明細移此。

- **2026-05-28 D+2 PM takeover continuation — runbook v1.0 land + 14d soak D+1 observation**：
  - `P1-OPS-2-RUNBOOK-V1.0-PATCH` CLOSED — PA delivered 4-patch v1.0；495→687 行（+192）。
  - `P1-OPS-2-14D-SOAK-OBSERVE` D+1 ssh trade-core empirical：engine.log 0 / api.log 0 hits of `ops2_secret_split_phase1_fallback` ✅；AC (a) PASS；AC (b) `/auth/renew` 0 次（OP-1 operator-blocked）。Phase 2 D+14 = 2026-06-10 unchanged。
  - 3 P2/P3 carry-over land from PA out-of-scope obs：`P2-OPS-2-RUNBOOK-HEALTHCHECK-SQL` (MED)；`P3-OPS-2-RUNBOOK-EMERGENCY-AUDIT-CONTRACT` (LOW)；non-blocker first-day live。
- **2026-05-28 D+2 P0 收口 + Wave 5 Packet A/B runtime land（commits `0100da7c` + `22466a81` + `a07a08c0` + DB hand-action）**：
  - Engine/API/user watchdog recovered；healthz 200；system-level unit install still operator/sudo hand-action。
  - Migration/register drift closed：V109/V113 register 補登；V099 physical apply + `_sqlx_migrations` register；`repair_migration_checksum --verify drift_count=0`。
  - OPS-1 enforcing-ready gaps closed：CSRF 403 friendly toast + reload；cert trust runbook + install hint；7d shadow + `csrf_shadow_zero_verify.sh` PASS 0。
  - Wave 5 Packet B landed/deployed：autonomy state/eligibility/status/switch API + GUI Autonomy Posture；switch remains fail-closed on missing TOTP backend and P0-EDGE evidence。
  - Passive healthcheck still FAIL on `[48]/[74]/[56]`（轉 OPS residual / evidence queue，不反轉 OPS-1 closure）。
- **2026-05-28 D+2 follow-up Wave5/OPS reality check**：TOTP source backend landed with fail-closed file verifier; runtime secret missing。Packet C source E2/E4 green（`risk_gov` 27/27; `openclaw_engine --lib` 3468/3468）but engine integration still absent。5 ADR sync done: ADR-0034/0040/0042/0044/0045。OPS `[80]` pg_dump fixed at runtime; daily 03:00 UTC cron installed。
- **2026-05-27 D+1 OPS-4 GAP B+D FULLY CLOSED via 3-round IMPL chain + E2/E4 r1+r2 + QA E2E + engine dead discovery**：
  - Round 1 commit `1392c9e1` PA spec amend (449→695) + E1 4/6 deliverable + MIT 1/3 (post_restore_validation.sql 330 LOC)
  - Round 2 commit `261d3956` E1 round 2 (check_pg_dump_freshness.py 616 LOC + passive_wait wire) + MIT round 2 (pg_restore_drill_sop.md 572 LOC + template 239 LOC)
  - Round 3 commit `cf710dc7` MIT Q3 P0 BUG fix (ts→created_at) + E1 3 MED fix + PA mini-patch spec §10.B.1
  - E2 r1 APPROVE-WITH-CONDITION (3 MED) → r2 APPROVE；E4 r1 YELLOW → r2 GREEN 雙重 confirm
  - QA E2E APPROVE-CONDITIONAL commit `b548c10d`: 5-gate 5/5 + 9 invariant 9/9 + FA 6/15 PASS-AUTOMATIC
  - 3 hidden risks QA empirical surfaced：(1) V099 deployment gap (2) V113 sqlx register drift (3) 🔴 engine + watchdog PROCESS DEAD 8h33m — 升 P0；2026-05-28 三項均已收口/降為 OP residual
  - 3 端 sync Mac/origin/Linux HEAD `b548c10d`
- **2026-05-27 D+0 Wave 4 closure（6 sub-agent / commit `07027493`）**：E1 OPS-1 round 2 ✅ 8 fix + bonus（33→48 test PASS）；E1 OPS-4 minor ✅ 4/4 fix；R4 Workflow A ✅ APPROVE-WITH-MINOR-CASCADE-GAP；MIT OPS-4 GAP-B+D ⚠️ PARTIAL；E1 Wave 5 Packet A V099 ✅ 369 行 + D1-D19 PG empirical/對抗 PASS；E1 Wave 5 Packet C Rust SM-04 ✅ +349 LOC + 3469+423+27 cargo test PASS。
- **2026-05-27 D+0 Wave 1-3 大規模並行 closure（22 sub-agent / 三波 / commits `bcf0e401` → `0459d451` → `65e78437`）**：Wave 1 (4 並行) PA Workflow A design 323 行 / PA Workflow J inline CORRECTION / E3 OPS [78] reconcile / PA P0-LG-3 verify 3/3 drift FULLY COVERED + V104 FREE。Wave 2 (9 並行) FA Workflow A pre-verify CONDITIONAL APPROVE 22/22 / PA Workflow D+E cascade / MIT V104 9/9 PASS + LG-3 IMPL gate (2) UNBLOCKED / E1 OPS-1 1242 LOC / E1 OPS-2 SECRET-SPLIT Phase 1 477 LOC / E1 OPS-4 systemd 2 unit。Wave 3 (8 並行 review) A3 OPS-1 6.0/10 / A3 OPS-2 8.0/10 / E2 OPS-1 RETURN 2 HIGH / E2 OPS-2 APPROVE-CONDITIONAL / CC OPS-2 APPROVE-CONDITIONAL hard gate / TW Workflow A AMD-09-03 §9 patch / QC Workflow A math PASS。3 AMD operator APPROVE 2026-05-27。
- **2026-05-26 §1 P0 advance — LG-3 AC correction + OPS-2 SECRET-SPLIT design**：P0-LG-3 AC correction ✅ PA spec v2 amendment 83 行 + V104 scaffold 378 行；P1-OPS-2-SECRET-SPLIT design ✅ PA 484 行 spec。
- **2026-05-26 OPS-3 5/5 operator confirm sequential closure + Workflow F Phase 1+2**：C-1~C-5 sequential signoff ✅；Workflow F FULLY CLOSED ✅；Linux atomic rebuild+restart engine PID 1228870；3 端 git sync HEAD `e913adbf`。
- **2026-05-26 §1 4 P0 並行推進 + operator funding_arb (D) closure**：5 sub-agent fan-out（PA OPS-1 spec / E3 OPS-2 audit / BB OPS-3 audit / PA OPS-4 runbook / PA LG-3 verify）；EDGE-1 SSH empirical 0/3 AC paths；operator chose (D)；§6 加 16 新 P1/P2 entries。
- **2026-05-25 V1→V5.8 drift audit closure** ✅（8 errors corrected + 10 真實 unresolved + 2 AMD proposed + ADR-0046 proposed + canary [67]→[80] rename + 4 commit 三端 sync HEAD `cf61d1f0`；PM+PA+FA 三方 APPROVED-CONDITIONAL；ref active §10 SSOT 指針）。
- **2026-05-26 Alpha Tournament SSOT 補洞**：`docs/execution_plan/2026-05-26--alpha_tournament_ssot_spec.md` land。
- **2026-05-25 v64 消歧義 + Day -1 派工 + EA-4 P0-EDGE-1 AC amend + E1 H-3 push back**。
- **2026-05-25 governance lesson**：sub-agent audit report 引用 file path / line range 必驗實際 code 對齊。
- **2026-05-25 PA Day -1 3 spec land + EA-3 verdict overturn**：commit `e1993ec6`。
- **2026-05-25 EA-1 Phase 1b sweep chain** (4 sub-agent round)：Round 1 揭 harness IMPL bug → Round 2 Option A 1-LOC fix → QA verify ENDORSE 46/8/27。
- **2026-05-25 H-1 atomic deploy verify ✅ DONE**：build_then_restart_atomic.sh 7-phase flock + restart_all.sh --require-clean-build-window land。
- **2026-05-25 H-2 cron restore ✅ DONE + EA-2 N/A confirmed**：PM atomic apply 10/13 enabled + 3 defer。
- **2026-05-25 Sprint 2 Day 0 業務派發 readiness 確認 + PM 3 decision 拍板**：PA dispatch packet `2026-05-25--sprint_2_business_dispatch_packet.md`。
- **2026-05-25 PM recheck**：C10 PnL + IntentType + Earn Wave C source gaps progressed。
- **2026-05-23 Sprint 4+ §4.1 + Stage A→F + Sprint 5+ Wave 1 ALL CLOSED** (19 commit chain `011fd5f9 → 22a07294`)：詳情 `docs/archive/2026-05-23--sprint_4plus_5plus_wave1_closure.md`。
- **2026-05-22 Sub-IMPL: M3 emitter scaffold ✅ PASS WITH 5 CARRY** + Layered Autonomy v2 設計 DONE + CC APPROVE A 級。
- **2026-05-21 closure**：v5.7 12 prefix DESIGN-DONE + v5.8 16 CR + Sprint 1A-α/β/γ/δ/ε PM signoff 全 land；詳情 `docs/archive/2026-05-21--sprint_1a_alpha_repair_closure.md`。
- **Incident marker 2026-05-21**：09:58 UTC engine + watchdog SIGTERM；13:31 UTC PM restart_all.sh --keep-auth 恢復；Phase 2a sample velocity gap ~3.5h。

> active TODO §-1 保留 ≤14d window（2026-05-29 全盤閉環核實 + gap audit / 2026-05-29 4-track 衝刺 / 2026-05-29 110017 治本 / 2026-05-29 runtime recovery / 2026-05-29 PM 接手 LG-3 ARMED + P2/P3 cleanup / 2026-05-29 health-freeze / 2026-05-30 7-gap + basis-panel DEPLOYED），以及指向本 archive + 既有 archive 的「詳細歷史」連結。

---

## §K — Commit map（本歸檔涉及的主要 commit）

| Commit | 範圍 | 狀態 |
|---|---|---|
| `cf61d1f0` | V1→V5.8 drift audit closure 4-commit（canary [67]→[80] rename） | DONE 2026-05-25 |
| `015b9735` / `bbb21c56` | C10 synthetic close PnL + IntentType direction mismatch | CLOSED 2026-05-25 |
| `e913adbf` (chain `6a20b9ea→`) | funding_arb (D) deprecation cascade Phase 1+2 | FULLY CLOSED 2026-05-26 |
| `65e78437` | OPS-1 round 1 + OPS-2 SECRET-SPLIT Phase 1 + OPS-4 systemd（Wave 2 IMPL） | DONE 2026-05-27 |
| `bcf0e401` → `0459d451` → `65e78437` | Wave 1-3 大規模並行 closure（22 sub-agent） | DONE 2026-05-27 |
| `07027493` | Wave 4 closure（OPS-1 round 2 + OPS-4 minor，6 sub-agent） | DONE 2026-05-27 |
| `b548c10d` | OPS-4 GAP B+D QA E2E closure | DONE 2026-05-27 |
| `1392c9e1` / `261d3956` / `cf710dc7` | OPS-4 GAP B+D 3-round IMPL chain | DONE 2026-05-27 |
| `0100da7c` / `22466a81` / `a07a08c0` | P0 收口 + Wave 5 Packet A V099 + Packet B API/GUI posture | DONE 2026-05-28 |
| `b43481f7` | M11 replay runner Daily 04:00 UTC cron install | INSTALLED 2026-05-28 |
| `920f8299` | notification_failsafe module (1099 LOC + 5 trait seam) | SOURCE 2026-05-28 |
| `d696b1f2` / `1f33301a` | M11 smoke zombie register-only fix + wave9 allowlist | DEPLOYED 2026-05-29 |
| `caf008b6` (三端 `5bf8085c`) | P1-110017 治本 fix（Structural→NoOp + converge） | DEPLOYED+VERIFIED 2026-05-29 |
| `a5e1ded1` | 110017 D2 reconcile Ghost converge + S-6 point-query gate | DEPLOYED 2026-05-30 (隨 basis rebuild) |
| `3423f0f7` | Packet C HIGH-1 banner channel weight (AllFail push-weighted) | DONE 2026-05-29 |
| `af92e2ca` | btc_lead_lag 生產 bug fix + bin-crate test lock | DEPLOYED 2026-05-30 |
| `a8ba146c` | Packet C C4 pipeline wire（in-band PipelineCommand + ATR + 半 wire dormant） | DEPLOYED 2026-05-30 (隨 basis rebuild) |
| `b93d3210` / `11b9531f` / `7909ca3d` / `dc2a15aa` / `f2b020e5` | cold-audit Wave1-4 + P3（詳見 `2026-05-29--cold_audit_p1_p2_p3_closure_archive.md`） | DONE 2026-05-29 |
| `46e0e825` | FA-audit 3 LOW followups（risk.rs 822→605 split 等） | DEPLOYED 2026-05-30 |
| `ec995160` / `e63a00e0` | basis-panel infra（V115 hypertable + BasisAggregator writer） | DEPLOYED 2026-05-30 |
| `7c854065` / `be8734a5` / `78153db1` / `b130c113` / `aa92be52` | v87 WIP 收束 + TODO checkpoint + reconciler wrapper cleanup | DEPLOYED 2026-05-31 (PID 968350 SHA `30adb40...`) |
| `b25f9048` | M4 Stage 1 production runner（non-dry-run source read + gated DRAFT writeback） | SOURCE 2026-05-31 |
| `6b654ef2` | A3 pairs precheck + M4 Stage1 Linux PG no-writeback empirical | SOURCE 2026-05-31 |
| `0731d57b` | A2 maker-fill feasibility diagnostic | SOURCE 2026-05-31 |
| `ec11544a` | M4 GovernanceHub lease provider seam（fail-closed，UUID column vs `lease:<id>` mismatch 未解） | SOURCE 2026-05-31 (v91 checkpoint) |

---

**返回 active TODO**：`/Users/ncyu/Projects/TradeBot/srv/TODO.md`
