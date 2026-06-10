---
name: project_2026_06_05_residual_producer_build
description: 接手 Codex 未完成的 residual alpha producer 三件套 lattice 全建成（feature/residual-producer 7 commit，QC/MIT/E1/E2 全鏈審，743 測試綠，已 rebase 到 origin/main(ae14128d) ahead7/behind0 ff-able）；**deploy 阻塞於 Mac→GitHub SSH 逾時**；剩 mlde hook + hidden_oos replay 接線 + flag-on soak
metadata: 
  node_type: memory
  type: project
  originSessionId: 02609da3-dfb2-4b95-913a-0f995648f446
---

# Residual alpha producer 完整建構 (2026-06-05) — reviewed, 未部署

承 [[project_2026_06_04_external_framework_audit_and_self_audit]]。命門：Codex 建了
fail-closed evidence enforcement 格架（SignalSpec/EvidenceManifest/Hidden-OOS-sealed/
residual gate/promotion+LG-5 validators）**但三個 evidence artifact 全無 producer →
整套 inert、對真實候選 100% fail-close**。operator 要求我接手補完。本 session 把
**residual producer** end-to-end 建成。

## 成果：feature/residual-producer（worktree `/private/tmp/wt-residual-producer`，off main@4b97d344）
**5 commit，未 push origin/Linux、未部署**：
- `6cc06005` R-1 compute assembler（`learning_engine/residual_alpha_producer.py`：leak-free 對齊 timestamped 候選報酬+factor → train/eval 切窗(train_end<eval_start)+embargo purge → gate → canonical demo_residual_alpha_report）+ R-2 DB adapter（`ml_training/residual_alpha_producer_db.py`，BTC-only v1）
- `e4bfd54e` R-2 **非重疊 4h bucket 重設**：報酬按 **exit 歸桶**（一筆 trip 只進它的 exit 桶 → MIT CRITICAL「duration-blind embargo leak」結構性消失）+ bucket BTC factor → 解 QC HIGH「round-trip 重疊→非 i.i.d.→PSR sqrt(N) 高估→beta 偽裝過閘」
- `f8ed11f0` **gate 統計修（QC BLOCKING）**：`residual_alpha_gate` 的 `_normal_approx_psr`(丟skew/kurt)/`_deflated_psr`(Bonferroni cliff)/`_probability_of_backtest_overfit`(非CSCV) 是手搓錯公式 → 改呼叫倉內 vetted `dsr_gate.compute_dsr`(真 LdP PSR含skew/kurt + DSR via E[maxSR]) + `pbo_gate` CSCV。E1 實作 + **E2 ACCEPT**（Sharpe convention 親驗 per-period = `promotion_evidence._sharpe`；mutation-back 證測試重校準正當；honor insufficient_observations）
- `5545d712` R-2b cycle orchestrator（`ml_training/residual_alpha_cycle.py`：peers=**同策略參數變體**非跨策略；`n_trials`=變體×symbol×策略 floor **K≥10**，永不用 obs/天數；單配置→診斷性 defer `pbo_not_applicable_single_candidate`）
- `0aa88c64` R-3 attach primitive：env-flag **`OPENCLAW_RESIDUAL_ALPHA_PRODUCER` 預設 OFF**；`attach_residual_reports` 把 report 附到 `learning.mlde_shadow_recommendations.payload`(jsonb，無 migration)
- `0bc2b2f6` **signal_spec producer + hidden_oos sealer（補完三件套）**：`candidate_signal_spec_producer.build_signal_spec`（輸出通過 validator，PIT/hidden_oos 硬寫、residualization 綁 report factor_panel_hash、spec_hash 自洽）+ `candidate_hidden_oos_sealer.build_hidden_oos_state`+`hidden_oos_source_row_fields`（封存保留 OOS 窗；輸出**同時通過** source_contract 的 manifest gate + durable gate，body sha256 一致）
- `2714e26b` attach 同時附 **residual report + signal_spec** 到 payload（hidden_oos 走 replay registry=deploy 階段）

審查鏈：QC+MIT(設計/leak，抓到 embargo leak+重疊+gate壞統計)→E1(gate)→E2(ACCEPT)。**743 passed/31 skipped**（ml_training+learning_engine 全套，rebase 後重測 54 綠）。**已 rebase 到 origin/main(ae14128d)，與其 3 commit drift 零檔案重疊=乾淨 ff**。

## 誠實狀態（不變）
producer 讓晉升閘**可信、會誠實 defer**；以現**單配置** demo 資料正確數學一律 defer
（QC 4e：對的，舊壞公式才假性放行）。**非吐-alpha 機器**；真 alpha 仍須他處來。

## DEPLOY = 已完成（2026-06-06，bundle→Linux→origin）
- **Mac→GitHub SSH 逾時**（`140.82.112.4:22`）→ 改走 **Mac↔Linux ssh bundle 路徑**：Mac `git bundle create`(7 commit) → `scp trade-core` → Linux `git fetch bundle` + `merge --ff-only`(main ae14128d→**598ed5d4**) → **Linux `git push origin main`**（Linux→GitHub 通）。
- **三端：Linux runtime srv main = origin/main = `598ed5d4`**；Mac worktree 分支同 = 598ed5d4（Mac main 樹仍在 feature/l2-critic，待 GitHub 恢復 fetch）。
- **部署驗證**：Linux py_compile + 全 producer 鏈 import 乾淨；`residual_producer_enabled()=False`（env-flag OFF）；引擎 1+API 2 進程未受擾；**未 restart**（code inert：env-flag OFF + residual_alpha_gate 無 live caller）。**behavior-neutral**。

## 進度更新（2026-06-06，啟動 part 1）
- **mlde hook DONE + 已部署**：`mlde_shadow_advisor.generate_shadow_recommendations` 接 `_maybe_attach_residual_evidence`（env-flag OFF 即 return 0 / fail-soft 絕不中斷 recommendation cycle / 唯讀 conn；附 residual report + signal_spec 到 payload）。11 hook 測試綠。
- **部署推進到 `627b4772`**（Linux main + origin；main 期間被隔壁 watchdog commit 推到 36c3c247，我的 hook 在 Linux 端 rebase onto main 後 ff+push；零檔案重疊）。**hook present:True、引擎 1+API 2 健康、未 restart、env-flag 仍 OFF**。
- **教訓**：deploy 腳本 bug（rebase 後沒先 checkout main 就 ff → merge 自己、push no-op、誤刪 rebased 分支）；第二次先 checkout main 再 ff 才對。Linux main 全程未受損。

## 剩餘 = part 2（深）+ part 3（gated）；part 4 隔壁 session 做
1. **part 2 hidden_oos replay 接線（深，未做）**：source_contract 讀的 `replay_registry_manifest_jsonb`/`oos_label_window`/`durable_hidden_oos_state` 來自 `mlde_demo_applier_evidence_filter` 對 **replay.experiments + durable hos 表 JOIN**（非 payload）→ 必須把 sealer 的 state 寫進 **replay 實驗註冊**（`experiment_registry.register_experiment` 的 manifest_jsonb，commit 進 manifest_hash）+ durable hos 表（可能需 migration）。sealer（state producer）已建好，但此接線是 Codex replay-registration 流深整合，需 Linux + 審慎，**不在 marathon 尾速成**。
2. **part 3 flag-on go-live（gated on part 2）**：(a) 真資料離線預檢（需 runtime env/launcher 取 PG，read-only 跑 build_cycle_residual_reports for grid/ma，確認不報錯）→ (b) 設 `OPENCLAW_RESIDUAL_ALPHA_PRODUCER=1`（runtime env）→ (c) 監看首輪 recommendation cycle（attach 數、defer 理由、無 fail-soft warning）。**現狀即使 flag-on 也會 defer**（part 2 未接 → manifest 缺 sealed hidden_oos → hidden_oos_state_missing）。故 part 3 須在 part 2 後。
（P2 #6 orderLinkId / #7 postmortem / #8 AST = 獨立線，隔壁 session 做）

## 關鍵脈絡
- **多 session 髒樹**：工作隔離在 feature/residual-producer 不擾隔壁 L2-critic/aeg/watchdog WIP（operator 選 worktree）。main 已前進到 ~92cdcc41（殘差分支 off 較舊 4b97d344）。
- Linux 已驗 schema：`market.klines` timeframe='1m'/'4h'、ts/open/close；`mlde_shadow_recommendations` 有 payload jsonb+strategy_name+symbol；demo round-trip **grid~496/ma~238**（策略級夠清 40，其餘 defer）。
- 教訓：**對抗審查抓到我真 bug**（embargo leak/重疊/Sharpe risk），我修了沒辯護——審自己用審 Codex 同把尺。

## PART 2 + PART 3 完成（2026-06-07）— 全鏈審 + 部署 + flag-on go-live

**PART 2（hidden_oos sealer → replay 註冊接線）DONE + 部署**。隔離 worktree `/private/tmp/wt-residual-p2`（branch `feature/residual-hidden-oos-wiring`，off 627b4772）。
- **調查結論（推翻臆測）**：`experiment_registry.register_experiment` 早就呼 `_extract_alpha_hidden_oos_v049_fields`(:948) + `_persist_hidden_oos_state_registry`(:1067)，會寫 `replay.experiments` + `learning.hidden_oos_state_registry`。**無需 migration**——V049（alpha 欄）+ **V132**（hos durable 表，Guard A + CHECK）兩檔都已在 branch。**唯一真 gap**：sealer 出 nested `calibration_window/candidate_window`，但 `_extract`/`_persist` 讀 flat `calibration_train_window_start/_end`+`candidate_window_start/_end` → 餵進去會 `..._missing`。且**無 alpha-candidate 自動註冊 caller**（register 只 2 個 HTTP route 達）。
- **改動（2 檔）**：①`candidate_hidden_oos_sealer.build_hidden_oos_state` 加 4 flat key（純加性，split_hash byte-identical 凍結 `ebbb40…`）②新 `ml_training/residual_hidden_oos_bridge.py`：`partition_round_trips_by_oos`（strict `exit<oos_start` leak carve-out）+ `register_residual_candidate_experiment`（3-窗 carve-out → 非OOS算 residual → 衍生 ISO 三窗（**不用 report.fit_window，那是 float-string，`_parse_manifest_datetime` 回 None**）→ seal → 組 manifest+request → `run_register_in_pg_xact`）。**顯式呼叫、env-flag OFF、無生產 caller=行為中性**。
- **審查鏈全 PASS**：PA 設計 → E1 → **E2 對抗（mutation probe）退回 3 MED** → E1 修 → re-E2 PASS → **MIT 抓到 E2 漏的真 HIGH-1 PIT leak**（MED-2 的 OOS filter 只套在 window-label，沒套到 `evaluate_cell` 的獨立 re-bucket；`load_btc_klines` 用 bar **open**-time clamp 但 4h bar 的 **close** 越過 oos_start → 非對齊 oos_start 時 straddle bucket 洩進 residual）→ E1 修（DATA 層 `_bucket_admissible` 過濾 rts+klines，one source of truth）→ re-E2 + re-MIT 確認 leak CLOSED → **E4 PASS**（770/31，0 回歸；baseline 真相：36c3c247=743、627b4772=746、HEAD=770，+24=新測；skip-set byte-identical）。QA skip（行為中性 primitive 無生產 caller，理由記錄）。
- **部署**：bundle（Mac→GitHub fetch 仍逾時）→ Linux rebase onto 最新 main(9caf95ae)+ff+push。**origin/main = Linux main = `d5ec22d5`**（3 commit；零檔案重疊；py_compile OK；未 restart=inert）。

**PART 3 flag-on go-live DONE**（operator 選「flag-on + 立即觀察一輪」）。
- **離線預檢（唯讀，真 PG）**：demo round-trip 45d：**grid_trading 1524 / ma_crossover 634**（真名=task 給的，非 memory 短名）/funding_arb 112/bb_breakout 37/bb_reversion 36。`build_cycle_residual_reports` 0.12s 無錯：grid aligned=156 train/eval=108/47、ma aligned=133 train/eval=93/40，**兩者 single_config_defer / pbo_not_applicable_single_candidate**（誠實 defer，對的）。`attach_residual_reports` attached 2/2、report+signal_spec 都附、無 fail-soft。
- **flag-on 機制（坑）**：cron wrapper + restart_all **都只 grep allowlist**（POSTGRES_* / 特定 OPENCLAW_*），**不讀任意 OPENCLAW_***。所以 flag **加進 basic_system_services.env 對 cron/API 都 inert**。正確位置 = **crontab inline env**（cron 唯一傳任意 env 的途徑）。已 surgical 編輯 crontab ml_training_maintenance 行加 `OPENCLAW_RESIDUAL_ALPHA_PRODUCER=1`（48→48 行、flag 唯一、備份 `/tmp/crontab_pre_residual.bak`）→ 每日 03:17 UTC cron 生效，無需 restart。
- **立即觀察一輪**（standalone `generate_shadow_recommendations` demo）：**residual_attached=7/7、inserted=7、無 fail-soft warning、1.43s**。log "residual evidence attached to 7/7"。
- **回滾**：`crontab /tmp/crontab_pre_residual.bak`（或刪該行 flag）。Linux `/tmp/residual_observe_cycle.py`+`residual_precheck.py` 留作再監看工具。
- **誠實狀態（不變）**：現單配置 demo（無參數變體、N_eff 低）下**正確數學一律 defer**；買到「可信、會誠實 defer 的閘」，**非吐 alpha**。

**剩餘 / follow-up**：①API in-process `edge_estimator_scheduler` 路徑要 honor flag 需 `restart_all.sh` allowlist 加 `OPENCLAW_RESIDUAL_ALPHA_PRODUCER`（小 code change，未做；cron 路徑已足覆蓋 evidence 流）②可被動驗下一輪 03:17 cron 的 status JSON③真 V132 CHECK reject / 真 drar JOIN / OPENCLAW_ENGINE_BINARY_SHA gate 仍 Linux-owed（PART 2 為 primitive 無生產 caller，未實際撞）④未來 OOS open 做真 promotion 時要在 `[oos_start-embargo, oos_start)` 加 purge band（MIT MED-2，promotion-time gate）。
- **教訓**：①**別讓兩個 mutation-probe agent（E2+MIT）並行同 worktree**——edit/revert 互相 race（E2 OBS-2 file desync + MIT pycache flake 都是症狀；幸最終都 PASS 且 MIT restore 到 committed blob，我事後查 git diff 確認乾淨）②cron 的「env」是 crontab inline 非 env file（wrapper 用 grep allowlist）③MIT 抓到 E2 mutation-probe 漏的 leak=多角色鏈真價值。

## Follow-up 處理（2026-06-07，operator 要求嘗試解決）
- **#2 cron path 驗證 = RESOLVED**：直跑真 cron python 入口 `ml_training_maintenance.py --jobs mlde_shadow_advisor --shadow-engine-modes demo`（flag ON），status JSON = `residual_attached=7, recommendations=7, inserted=7, status=ok`，log "residual evidence attached to 7/7"。真 cron 路徑確實 honor flag。
- **#3 = 揭露真 latent gap（重要）**：查 runtime PG `_sqlx_migrations` **max_applied_version=130**（113 applied）；**V131(drar=learning.demo_residual_alpha_reports)、V132(hos=learning.hidden_oos_state_registry)、V133(L2 鄰)全 PENDING 未套用**。**V049(replay.experiments) 已套**（5 alpha 欄全在）。意涵：①flag-on 的 **payload attach 路徑不需 durable 表→完全可用**（已證 7/7）②PART 2 bridge 的 **durable hos 寫入 + source_contract 的 drar/hos JOIN 在 V131/V132 套用前非功能性**——但 bridge **無生產 caller**、JOIN 缺表時 graceful defer（`*_missing` PENDING_SCHEMA），**無 active 路徑壞**。**套用 = operator-timed engine-restart auto-migrate（OPENCLAW_AUTO_MIGRATE=1）**：會一次套 131/132/133（sqlx 順序套，無法只套殘差的而跳過鄰 session V133）→ 涉跨 session 協調 + 引擎重啟（破壞性，memory 有 bind-host/sqlx-drift 前科）→ **不可單方現在做**；手動 psql 套會 sqlx checksum drift（P0 前科）禁。**建議**：operator 排程 auto-migrate restart 套 131/132/133（殘差 durable 表 + L2），restart 前可選 dry-run V131/V132。
- **#1 API in-process scheduler（edge_estimator_scheduler）= 理性 DEFER**：該 scheduler **每小時**（interval_s=3600 ×demo/live_demo）跑 generate_shadow_recommendations。enable flag = 每天 ~48 次重算 residual（report 日級變動慢）→ **冗餘成本、零 outcome 改變（現全 defer）**，且需改 `restart_all.sh` allowlist + API restart。若未來要開應**配 freshness throttle** 非裸 flip。cron daily 已足夠驗證+行使路徑。
- **#4 OOS-open purge band = SKIP（無 consumer）**：無 OOS-open flow（bridge 只 seal、open 是未來 feature）→ 現在實作=speculative，違「no speculative implementation」。等真 promotion-time open flow 再做（MIT MED-2 已記）。
- **淨結論**：flag-on 的 active 路徑（payload）完全可用且已驗；durable 路徑（bridge/drar/hos）的唯一阻塞 = V131/V132 未套用（operator-timed restart）+ bridge 無 caller（未來 PART）。誠實：現資料全 defer，套不套 durable 表都不改 outcome，只影響「未來真 alpha 出現時 durable evidence 鏈是否就緒」。

## 完整 rebuild+restart + 三端同步（2026-06-07，operator 指示）
operator 拍板做完整 rebuild+restart → 解掉上面 #3 的 durable 表阻塞。流程（survival>profit，逐閘驗證）：
- **migration dry-run 閘（專案硬規則）**：V131/V132/V133 在 runtime PG single+double-apply 全程 ROLLBACK → 全 PASS（txn-safe：無 CONCURRENTLY/hypertable；V133 僅 `CREATE EXTENSION IF NOT EXISTS pg_trgm`）。
- **rebuild+restart**：`restart_all.sh --rebuild --keep-auth --require-clean-build-window`（AUTO_MIGRATE 暫設 1→restart→**revert 0**，env file 有備份）。engine release build **41.82s** OK、新 binary、engine PID **160870** / API PID **161085**、demo ticking、watchdog pause/resume OK。
- **migration 套用**：sqlx **130→133**（applied_count 113→116）；**V131(drar=learning.demo_residual_alpha_reports)、V132(hos=learning.hidden_oos_state_registry)、V133(agent_lessons+pg_trgm) 全 applied** → PART 2 bridge 的 durable 路徑 + source_contract drar/hos JOIN **現在 runtime 可用**（bridge 仍無生產 caller=latent）。同次部署 main 累積的 #6 Rust/#7 Python/L2/watchdog/SM 全套（engine 自 June-3 起首次 rebuild）。
- **TODO v120**（`8cd4da1f`）：header + Runtime row + #6/#7/#8/push-only row + residual DONE row 全更新（修掉「June-3 binary/待 rebuild/V131-133 未套用」stale 敘述）。
- **三端同步**：Mac origin/main = Linux main = origin/main = **`8cd4da1f`**（TODO 走 bundle Mac→Linux ff→push；Mac origin/main ref update-ref 同步，working tree 仍 l2-critic 屬正常 dev 狀態）。
- **坑/教訓**：①`git bundle create` 需 **ref** 不能用裸 SHA（`ae14128d..main` 才行，`d5ec22d5 --not 627` 報空 bundle）②cron 的「env」= crontab inline（wrapper 只 grep POSTGRES_*）③全量 restart 依 caveat 會 revert operator-env flag → **任何 RUNNING soak（P5-SM-OPTION2）已被結束，owning session 須查驗/重啟**（已在 TODO header 標警）④`--keep-auth` 保留 live auth；demo lane 續收。
- **殘留**：`/private/tmp/wt-residual-p2`（feature branch + PA design report 未 commit）保留；Linux `/tmp/{residual_observe_cycle,residual_precheck,v132_check}.py` + `crontab_pre_residual.bak` 留作監看/回滾工具。

## 對抗性 gap 審計：vs 2026-06-04 P0（MIT+QC 雙獨立，runtime-DB 坐實，2026-06-08）
operator 要求對照 [[project_2026_06_04_external_framework_audit_and_self_audit]] 的 P0（β殘差化接進自主晉升閘 auto-veto beta-masquerade）查「是否全部修復就位/無gap/可運行/真實有效」。MIT+QC 並行（read-only）+ **查 Linux runtime DB** 收斂同一誠實結論：
- **裁定 = P0 ACHIEVED-but-INERT（armed-but-never-fired）**：
  - ✅ **數學真實**：`residual_alpha_gate._fit_factor_beta` 真 OLS lstsq train-fit→eval 扣 beta（不扣 intercept 防兩面陷阱）；vetted `DsrGate.compute_dsr`(skew/kurt)+`pbo_gate` CSCV（非舊手搓）；n_trials=變體×sym×策略 floor K≥10；非重疊 exit-keyed bucket 結構性消重疊（比 HAC 更乾淨）。`test_beta_trap_raw_positive_but_residual_fails` 直擊證明會否決 5-killed-candidate 純 beta profile。
  - ✅ **拓樸無 bypass**：LG-5 `lg5_review_consumer_scheduler` 只是 thin dispatcher→呼 `governance_hub_live_candidate_review`（殘差 hard pre-gate 排在 R1-R6 之前 :1342-1370）。06-04「grep beta=0 in lg5 scheduler」真但**誤導**——beta 閘在它呼叫的 review consumer 內，非 scheduler。唯一 live-promotion lease writer residual-gated；mlde_demo_applier producer 端也 gated（`should_create_live_candidate` :500-501 需 promotion_ready + `_consume_hidden_oos_state` 需 sealed row）。候選**進不來+過不了**。
  - ❌ **真實 GATING = defer-by-ABSENCE（crux）**：**runtime DB 實查**：`learning.demo_residual_alpha_reports`=**0 rows**、`learning.hidden_oos_state_registry`=**0 rows**、19,305 mlde_shadow_recommendations **0/19305** 帶 replay_experiment_id/manifest_hash。每候選死在第一道 DB 檢查 `source_replay_experiment_id_missing`（PENDING_SCHEMA），**殘差數學從未成為任何真候選的 deciding factor**。殘差只在 cron payload + precheck 算（診斷）。
- **根因 3-gap（其實一條鏈，皆「未接線」非 regression，6.5 設計本就 defer 為未來 PART）**：①[HIGH] `register_residual_candidate_experiment`（PART 2 bridge）**0 生產 caller**（orphan）→ 無 sealed hidden_oos 產出 ②[HIGH] drar durable 表 live path 不寫（mlde 附報走 read-only payload-only；`promotion_evidence._persist_residual_alpha_report` 只在 evidence 已帶 report 時寫）③[HIGH] 候選 row 無 replay lineage（0/19305）。
- **次要 gap**：④[MED] **BTC-only partial residualization**——cycle `required_factors=("btc",)`，gate/producer 支援 `("btc","market")` 但 cycle 沒接；對 BTC 中性但裸吃 sector/**funding-carry** beta 的候選理論可假性過閘（funding-tilt 候選正死於 carry beta，BTC-price beta 抓不到）=殘差 false-promote 主向量 ⑤[MED] 無 permutation test、PSR 內核 Φ-based（小樣本厚尾略樂觀，已 min-30 守衛）⑥[MED] 單配置 demo→PBO 不適用→即使①②③接好仍誠實 defer，需多參數變體 ⑦[LOW] selection_bias_validator 仍 dormant（非 residual 閘所需）。
- **operator 4 criteria**：修復就位=**PARTIAL**（數學/拓樸/enforcement ✓、evidence-production ✗）；無gap=**否**（3 HIGH 未接線 + 3 MED）；可運行=**PARTIAL**（單元 70 測綠 + fail-closed defer 已 runtime 驗；端到端 gating 跑不起來=0 evidence row）；真實有效=**「不會誤放」YES production-grade /「真正用殘差裁決真候選」NOT YET**。
- **誠實一句**：有一個正確、fail-closed 可信、拓樸無 bypass 的 beta-masquerade veto 閘，但部署 runtime 上它**從未對真候選用殘差數學做過一次 PASS/FAIL**——因 durable 證據由無 caller 的碼產出（0/0/0）。安全（不誤放），但尚非設計意圖的 deciding factor。**「現資料全 defer」一半因閘正確拒（單配置 PBO 不適用），一半因 evidence 從未產出（bridge 無 caller）**。
- **啟用路徑（INERT→ACTIVE，皆 operator-gated 新工作）**：①接 `register_residual_candidate_experiment` 生產 caller（Stage-0R preflight / operator CLI，flag-ON）+ bridge 流程內封 drar（PA 2026-06-06 design 已備 spec）②cycle 升 `("btc","market")`+funding factor 閉 partial-residualization ③補 permutation test ④產多配置 demo 讓 PBO 適用。前置②未做前即使①接好仍 defer。

## PART 4 — 全部修掉、走完整鏈、部署 flag-OFF（2026-06-08，operator「全部修掉走完整鏈、真實啟用評估後決定」）
operator 要求把上面審計的 gap 全修、走完整 PM→PA→E1→E2→MIT→E4，**真實啟用（flag-on）留待 evaluate 後決定**。已部署 **flag-OFF、behavior-neutral**：origin/main=Linux main=**`14e94532`**（5 commit rebase onto bdf15e4f，pure Python 無 rebuild）。worktree `/private/tmp/wt-residual-act`（branch `feature/residual-activation`）。
- **PA 關鍵 ruling（推翻 A1-lite）**：原設計的「re-bucket 自己 fills 當 PBO peers」=**invalid PBO=theater，REJECT**。DSR(用 n_trials count)/beta-residual/permutation 皆 peer-independent 可單配置跑；**PBO 為 fail-closed-required→PBO 缺=整體 defer**，故「假 peers vs None」outcome 相同→唯有 A-full（真 Rust variant replay）才有 genuine PBO。**修正方向：orchestrator 接好讓殘差/DSR/beta/permutation 在真候選上 RUN（閉 defer-by-absence），PBO 誠實 defer（`candidate_oos_returns=None`→既有 `missing_cpcv_returns→defer_data`，不偽造 peers、不加 verdict literal）；A-full 留為未來 PART P3。**
- **P1（B+C，commit ccdf8223+0633ac2f，全鏈 PASS）**：①Gap B `bucketed_multi_factor`+PIT **funding-carry factor**（`market.funding_rates.ts<=bucket_end`，MIT 親驗 8h settlement 全落 4h 邊界；`net_pnl_bps` 不含 funding→factor 抓的是 funding-regime 共動非裸 carry）+ market basket（`pit_active_symbols` survivorship-correct）→ cycle 升多因子（**default 仍 `("btc",)`=behavior-neutral**）②Gap C **sign-flip permutation**（model-free α≠0 null，非重疊 bucket→exchangeability 成立、非冗餘於 Φ-based DSR，conjunctive→deflate false-promote，default OFF）。MIT 確認無新 false-promote、leak-free；E4 baseline 794→827。
- **P2（Gap A orchestrator + Gap D，commit 7b5d92e9+9cdc24b0+14e94532，全鏈 PASS 含 MIT 抓 2 真 HIGH）**：新 `residual_stage0r_preflight.py` 6 步 flow（多因子 evaluate→**真 net_side（per-symbol）**→Gap D selection_bias K≥10 pre-gate→bridge register 寫 replay.experiments+sealed hidden_oos→drar→**stamp lineage + 把 report 寫進 rec payload**）；新 cron job `_run_residual_preflight`（**OPTIONAL_JOBS 非 DEFAULT**）+ CLI；**triple-OFF**（新 flag `OPENCLAW_RESIDUAL_STAGE0R_PREFLIGHT` + 既有 PRODUCER flag + job-absence）。
  - **deciding-factor 起初 NOT MET（E2 抓）**：orchestrator 沒寫 `payload.demo_residual_alpha_report`→source_contract 第一 gate 讀不到→`residual_alpha:not_dict`=defer-by-absence relabeled。**修：stamp UPDATE 同時 `jsonb_set` 把 captured report 寫進 payload（pass+defer 都寫，hash-identical manifest/drar）**→真候選 defer 時走 `residual_alpha:passes_not_true`=**殘差數學成為 deciding factor**（E2 親驗 before/after）。
  - **MIT Linux-empirical 抓 2 真 prod-breaker（Mac 抓不到）**：HIGH-1 **PG jsonb 丟負零 `-0.0→0.0`**（registry hash 算 PRE-jsonb、source_contract 算 POST-jsonb→`-0.0` beta/residual_mean〔正是 defer/weak cohort〕→hash mismatch→閘破）→修 `_normalize_zeros` 進 `to_dict()` 單一 chokepoint（MIT 真 PG round-trip 親證 pre==post、負控制漂移）；HIGH-2 **net_side 是 strategy-wide 非 per-symbol**（`grid::RAVEUSDT` 全策略 short 但該 symbol long→funding sign 反→**放大 carry=false-promote 向量**）→修 per-symbol filter（MIT 親證 RAVEUSDT→+1）。
- **誠實狀態（部署後）**：閘**接好後對真候選會 RUN 殘差/DSR/beta/permutation**（不再 defer-by-absence），但**現單配置 demo→PBO 不適用→誠實 defer**（正確、不誤放）；genuine PBO 需 A-full（Rust variant replay，未建=未來 PART）。**fail-closed 可信 production-grade；多配置 alpha 出現前仍會 defer**。E4 baseline 794→**855/31**（+61=新測、0 回歸、skip-set 不變）。
- **真實啟用＝operator 決策（未做）**：set `OPENCLAW_RESIDUAL_STAGE0R_PREFLIGHT=1`（+既有 `OPENCLAW_RESIDUAL_ALPHA_PRODUCER=1` 已在 crontab）+ 把 `residual_preflight` 加進 cron JOBS。啟用前 Linux-owed：flag-ON 真寫一輪驗（+1 replay.experiments/+1 sealed hidden_oos/+drar-if-pass/+stamp 1 rec、首筆 sealed 確認 `-0.0`/net_side 對）；signal_spec producer + hidden_oos sealer 仍 pass-through/0-sealed。**現狀全 inert、未啟用。**
- **教訓**：①**MIT Linux-empirical 是必要的**——PG jsonb `-0.0` drop + per-symbol net_side 兩個真 prod-breaker Mac pure-core 抓不到，全鏈+真 PG 才擋下②**別偽造 PBO peers**（PA ruling，invalid CSCV=theater）③deciding-factor 要追到「真候選端到端是否真用殘差數學裁決」非「evidence 表有沒有寫」（E2 抓 not_dict relabeled）。

## PART 4 後續：multi-factor 在真資料根本不算 bug（2026-06-09，read-only eval 抓到 → 修 → 部署）
operator 卡 usage 後要求「繼續做完+三端同步」。我做**真資料 read-only eval**（no-op capturing register_fn = 零寫入，跑 multi-factor gate 於真 demo 候選）→ 抓到 **deploy 後仍然假活的真 bug**：`_load_multi_factor_inputs:367` `basket = sorted(set(active))[:N]` **按字母序**取 basket → 真 PG 上選到 `0GUSDT`/`1000000BABYDOGEUSDT`… 等**零 4h klines 的冷門 symbol**（60/60 bars=0）→ market 因子空 → `market_buckets=0` → btc/market(/funding) 多因子閘**在真資料上永遠 `no_aligned_buckets`、根本不算**（btc-only 正常）。synthetic 測試直接餵 klines、從不打真 DB symbol selection → 漏掉。**修（commit `6c1b015f`，鏈 E1→E2→E4 PASS，859/31）**：新 `load_liquid_basket_symbols`（read-only count(*) query，按 4h-bar 數=流動性 rank，與 `pit_active_symbols` 交集→**survivorship 保持**：PIT-active 已要求 delisted_at>exit_ts 故每個成員必有窗內 bars，只重排不改集合）。**真 Linux 親驗（read-only 零寫入）**：basket 60/60 bars>0、market_buckets=113、閘產出真 report（grid_trading::BTCUSDT raw −13.70bps、**residual +12.44bps**〔扣 funding beta −63.38 後殘差竟轉正！說明 grid 的虧主要是 carry 曝險非純負 alpha〕、verdict=fail〔單配置誠實〕）。三端同步 **`6c1b015f`**。**教訓④：synthetic 測試過 ≠ 真資料能算；DB-selection/真資料路徑必須 read-only 真 PG eval 才驗得出（no-op register_fn 是零寫入跑真計算的好工具）。** TODO v121 的「gate 接好對真候選會 RUN 殘差數學」**修完才真正成立**（修前是 no_aligned_buckets）。**仍 flag-OFF inert、真實活化待 operator。**


---

## [index-archive 2026-06-10] 原 MEMORY.md 索引條目全文(壓縮索引前歸檔,內容為當時點狀態)

- [Residual alpha producer 完整建構 (2026-06-05)](project_2026_06_05_residual_producer_build.md) — 接手 Codex 命門缺口（evidence 格架建好但**三 artifact 全無 producer→inert**），把 **residual producer** end-to-end 建成於 **`feature/residual-producer`**（worktree `/private/tmp/wt-residual-producer`，off main@4b97d344，**5 commit 6cc06005/e4bfd54e/f8ed11f0/5545d712/0aa88c64，未 push/未部署**）。對抗審查抓到我**真 bug**並修：MIT CRITICAL duration-blind embargo leak（→改非重疊 4h bucket 按 exit 歸桶）、QC HIGH 重疊非 i.i.d.、**QC BLOCKING gate 三統計手搓錯**（_normal_approx_psr/_deflated_psr/非CSCV pbo→改呼叫倉內 vetted dsr_gate/pbo_gate，E1 實作+E2 ACCEPT，Sharpe convention 親驗 per-period 對）。R-2b orchestrator（變體 peers+n_trials K≥10+單配置診斷 defer）+R-3 attach primitive（env-flag OPENCLAW_RESIDUAL_ALPHA_PRODUCER OFF）。79 測試綠。**誠實：讓閘可信會誠實 defer，現單配置 demo 一律 defer（QC 對的），非吐-alpha**。**剩餘已驗未完成：signal_spec producer（只 validator/pass-through 無構造）、hidden_oos sealer（零 state='sealed' 寫入）、mlde hook（attach_residual_reports 零 caller）+ deploy**。承 [[project_2026_06_04_external_framework_audit_and_self_audit]]

---

## [2026-06-10 更正] 全部缺口已關閉+部署+flag-on(取代上文「剩餘未完成」)

TODO v121 核驗:signal_spec producer/hidden_oos sealer/mlde hook+PART 2 replay bridge 已全部完成並於 2026-06-07 隨 main 全量 rebuild+restart 部署(V131/V132/V133 同次 auto-migrate 套用);PART 3 flag-on=`OPENCLAW_RESIDUAL_ALPHA_PRODUCER=1` 進 crontab(cron daily 03:17),首輪 attach 7/7 無 fail-soft。PART 4 gap-closure(多因子 btc/market/funding-carry residualization+sign-flip permutation+`residual_stage0r_preflight.py` orchestrator)2026-06-08 部署 **flag-OFF**(triple-OFF inert),真實活化=operator 決策(set OPENCLAW_RESIDUAL_STAGE0R_PREFLIGHT+cron job+活化前 Linux flag-ON 真寫一輪驗)。誠實狀態不變:單配置 demo→PBO 不適用→誠實 defer,非吐 alpha。#8 AST 解凍 gate 剩 schema freeze(merge+deploy 已達成)。
