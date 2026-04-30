# OpenClaw TODO — 工作清單（v3 · 單一時間軸版）

**Dust residual prevention**（2026-04-30 19:12 CEST · local verify complete · Linux ff-only sync/no rebuild）：本輪針對 Demo `APEUSDT` 這類「不顯示策略、PNL 長期近 0」持倉完成 RCA + 防線。根因是 exchange-side below-minNotional residue（APEUSDT `size=0.1`、notional 約 `0.016 USDT`，遠低 Bybit `minNotional=5`）在本地 dust reaper evict 後變成 REST-only，GUI 因無 paper owner 顯示 `--`，且 sub-cent PnL 被兩位小數顯示成 `0`。落地內容：1) Demo/Live primary full close 改用 Bybit `qty=0 + reduceOnly + closeOnTrigger`，避免依賴 stale/rounded explicit qty；2) normal `qty=0` 仍 fail-closed，只允許 reduce-only full-close form；3) `risk_close:fast_track_reduce_half` 若 rounded residual 會低於 minNotional 則跳過半倉減倉，避免製造 dust；4) `orphan_frozen` / `DUST_FROZEN` 不再被 paper_state dust reaper 移除；5) Demo API/GUI 會把 REST-only below-minNotional residue 標為 `orphan_frozen`，並以 4 decimals 顯示 tiny nonzero PnL。驗證：Python owner enrichment **34/0**，Rust targeted tests PASS，Rust lib **2381/0**，`cargo check --workspace` PASS，`git diff --check` PASS。本 checkpoint 只做 git/Linux fast-forward source sync；依 operator 指令 Linux 不 rebuild/restart，runtime 等下一次批准 rebuild 才載入。

**Dust residual runtime proof**（2026-04-30 21:10-21:52 CEST · ssh DB verify · commit `f8a245c`）：Linux runtime 已載入 fix 後，`trading.orders` 觀察到 8 筆 Demo/LiveDemo `qty=0` close order 皆 join 到非零 `trading.fills.qty`。關鍵 proof：Demo `APEUSDT` `risk_close:ipc_close_symbol` order `qty=0.0` → fill `qty=0.1` / `strategy_name=orphan_frozen` / `exit_reason=ipc_close_symbol`，且 fill 後無後續 `position_snapshots`；LiveDemo `XAGUSDT` 同路徑 `qty=0.0` → fill `qty=0.001` / `orphan_frozen` / fill 後無後續 snapshot。結論：Bybit full-position close form 在 Demo/LiveDemo runtime 已被真實 close-path 證明可用；歷史殘餘仍需保持 visible `orphan_frozen`，但「下一個 real full-close proof」已完成。報告：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-30--dust_edge_scout_followthrough.md`。

**Strategy edge model batch**（2026-04-30 15:25 CEST · local verify complete · Linux deploy/24h observe next）：本輪按 operator 要求把數學上較穩定、能提高正 edge 機率的 1-4 項做成可部署變更。落地內容：1) 補 TOML→runtime wiring 漏洞，`maker_price_buffer_ticks` 進 MA/BB，grid 的 `maker_price_buffer_ticks` / `reject_cooldown_ms` / `blocked_symbols` / `min_grid_step_bps` / `cost_floor_multiplier` 進 factory；2) maker baseline 三端策略參數對齊，MA/grid/BB maker buffer 可設 0，BBO/tick 缺失仍 fail-closed skip；3) grid OU spacing 加 execution-cost floor，baseline `min_grid_step_bps=22.0` + `cost_floor_multiplier=2.0` + `reject_cooldown_ms=120000`；4) scanner `edge_routing` 加 posterior LCB gate（1σ、min std 20bps），成熟不確定/負 LCB cell 只走 `exploration_only`；5) MA entry 加 ATR-normalized `min_trend_snr=0.75`，只過濾新入場、不影響出場。驗證：`cargo test -p openclaw_engine --lib` **2377/0**、`cargo check --workspace` PASS。工程日誌：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-30--strategy_edge_models_engineering_log.md`。部署後至少觀察 24h，重點看 `[33] maker_fill_rate`、`[38] grid_trading_lifecycle_drift`、`[40] realized_edge_acceptance`；rolling window 會混舊樣本，立即仍紅不等於本批無效。

**Post-deploy edge cutoff observation**（2026-04-30 21:10 CEST cutoff · ssh DB verify · commit `f8a245c`）：cutoff 後 `[33]` 樣本仍小（entry fills n=15），但 maker_like **40.0%**、avg fee **4.13bps**、fee_drop **39.0%**，較 7d rolling healthcheck（maker_like 25.4%、fee_drop 20.6%）改善；by strategy：ma_crossover n=6 maker_like 50.0% / grid_trading n=5 maker_like 40.0% / bb_breakout n=2 maker_like 50.0%。`[38]` cutoff 後 demo/live_demo lifecycle 各 n=1，低於 healthcheck minimum n=5，暫不能判定但 re-entry 0/3 demo、0/2 live_demo；`[40]` cutoff 後 MLDE rows=0，尚無新 post-fee training rows。結論：維持 P0 observation，不用混舊 rolling window 下結論；下一次有效判讀需累積更多 post-cutoff lifecycle/MLDE rows。

**TODO follow-through 1-4**（2026-04-30 22:17 CEST · ssh DB verify）：完成 operator 要求的四項：1) active docs source/runtime drift 校正為 Mac/Linux code-bearing runtime checkpoint `a9fce24`，latest healthcheck SUMMARY WARN；2) G1-04 as-of fee/R:R compute：post-G7-09 5.94d 全窗 entry n=1933 / maker_like 26.28% / fee_drop 21.30%，但 post-2026-04-29 12:27 reload slice n=665 / maker_like **73.23%** / fee_drop **59.32%**，接近 G2-01 目標；R:R mixed，grid_close_short reload slice net +2.96 / RR 1.454，ma_reverse_cross 仍 net -4.79 / RR 1.076 / win rate <40%；3) G8-01 closure：cognitive W1+W2+W3 tests **40/0**，stdlib trace/AST coverage `CognitiveModulator` **76/81 (93.8%)**；4) ML training hygiene：`learning.exit_features` 全期 dust spiral noise **37/1843 = 2.01%**，24h 0，低於 5% 回填門檻，既有 `[26] dust_spiral_noise_in_ef` + `[21] paper_state_dust_inventory` 已覆蓋復發監控，故不做 DB 回填。報告：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-30--todo_followthrough_g1_g8_mlhygiene.md`。

**TODO cleanup / hard-cap follow-through 1-4**（2026-04-30 22:56 CEST · local code cleanup + read-only runtime verify）：本輪按 operator 指示把 TODO 內仍可做的 1-4 一次收斂：1) TODO stale calibration：`G5-FUP-IPC-MOD-SPLIT`、`G1-04-FUP-FINAL-COMPUTE`、`G8-01`、MLDE demo autonomy / healthcheck rows 已完成，舊開放文字降為歸檔；2) §九 hard-cap cleanup：`risk_config_advanced.rs` **1360→960**（新增 `risk_config_slippage.rs` 367）、`paper_trading_routes.py` **1246→1160**（新增 AI-cost router + response helper）、`counterfactual_exit_replay.py` **1216→1119**（CLI help sibling）；3) G3-08 warning-zone cleanup：`multi_agent_framework.py` **966→481**（新增 `multi_agent_conductor.py` 362 lazy re-export）、`analyst_agent.py` **805→764**、`strategist_agent.py` **866→797**、`h_state_query_handler.py` 已是 **452**；4) Read-only readiness：latest Linux healthcheck SUMMARY WARN exit 0，`[13]` PASS（edge_estimates age 0.4h / cells 83）、`[11]` WARN but sample-ready（post-P013 n_rows **864/200**，blocked by replay JSON age 16.5h, not sample count），`[39]` PASS（24h distinct=8），pre-existing `[3]/[19]/[23]/[24]/[26]/[27]` no longer active FAIL. `G7-05` remains **not ready to bind**: `edge_estimates.json` `_meta.grand_mean_bps=-14.78`, validation eligible cells 0, shrunk positive **4/247** only. Verification: targeted Python `py_compile` PASS, MAF/Conductor pytest **102/0**, paper route pytest **81/0**, Rust `cargo fmt --check` PASS, slippage tests **13/0**, risk_config tests **128/0**, `git diff --check` PASS. No rebuild/restart performed.

**TODO final doc calibration**（2026-04-30 23:11 CEST · docs-only · no rebuild/restart）：Operator 要求把最後 doc calibration 做完並 push。校準基線：本 docs-only commit 之前 Mac/Linux source HEAD 均為 `5584785` clean；active code-bearing runtime checkpoint 仍是 `a9fce24`（本輪與上一輪 source cleanup 均未 rebuild/restart）。本 docs-only commit 不應被視為 runtime-bearing checkpoint。Linux watchdog fresh（demo/live alive，paper inactive by design）。最新 cron-wrapper healthcheck（2026-04-30 23:11 CEST）SUMMARY WARN exit 0：WARN `[4]` phys_lock_runtime、`[11]` replay JSON age **17.2h**（sample already **864/200**）、`[33]` maker_fill_rate（7d fee_drop **20.8%**, maker_like **25.6%**）、`[38]` grid lifecycle drift、`[40]` realized edge acceptance；PASS `[13]` edge scheduler fresh、`[14]` grid/ma READY、`[35]`/`[36]`/`[37]` MLDE boundaries、`[39]` strategy cardinality. Stale TODO rows recalibrated：G5 legacy line-count rows now reflect current `main.rs`/`instrument_info.rs`/G5-06 files all <1200；G3-08 warning-zone rows for Analyst/HSQ/Strategist are closed by current line counts；MAF cleanup is reframed as accepted lazy re-export design with `SCOUT_AGENT` already registered in `CLAUDE.md`. Remaining size work is explicitly a separate high-risk wave: `bybit_private_ws.rs` **1413**, `tick_pipeline/commands.rs` **1343**, plus large test files.

**Maintenance cleanup snapshot**（2026-04-29 22:12-22:20 CEST · no rebuild）：本輪按 operator 指示完成 1-4：`G5-08 E1 implementation`、`CHECKS-STRATEGY-SUBSPLIT`、`STRK-FUP-LOOP-HANDLERS-SPLIT`，以及 G3/G3-09 小 FUP（Strategist H1/H3 facade、Executor early-return invalidation、cost_edge_advisor H5 wait warning test）。追加完成剛核出的 hard-cap 小項 `CHECKS-ENGINE-SUBSPLIT`：`checks_engine.py` 1206→1143。本輪僅本地格式/測試 + git 三端同步；未執行 `restart_all.sh --rebuild`、未重啟服務。驗證：`cargo test -p openclaw_engine --lib strategist_scheduler` 32/0、`cargo test -p openclaw_engine --lib event_consumer` 154/0、`cargo test -p openclaw_engine --bin openclaw-engine h_state_timeout_warning_mentions_h5_dependency_and_no_spawn` 1/0、Python unittest `test_executor_agent_unit` + `test_h_state_query_handler` 116/0、healthcheck re-export smoke PASS、targeted `py_compile` PASS、`git diff --check` PASS。剩餘為既有 warning-zone/P3 清理項與 tests/static/GUI 大檔，無本輪已識別的 runtime healthcheck hard-cap 小項。

**最新狀態快照**（2026-04-29 21:20 CEST · W1-T2 close attribution complete deployed · [38] real FAIL · [39] rollover WARN）：W1-T2 producer-side gap 已補完並部署：`5895579` 把 canonical close helper / confirmed fill / external command fill 接到 `build_close_tags_from_legacy()`，close row 寫 normalized `strategy_name` + `exit_reason`；`[38]` 改為兼容 legacy close prefix 與 V033 `exit_reason IS NOT NULL`；`[39]` 改用 1h hard-fail + 24h rollover WARN；Learning tab 殘留「影子/真錢」說明已改成 engine_mode / RiskConfig / Decision Lease / live auth gates。Post-deploy DB 短窗抓到零 PnL `risk_close:ipc_close_symbol` 仍 `exit_reason=NULL`，補丁 `854cae1` 改為 close-prefix 即按 close row 寫 attribution；Linux `trade-core` 已 fast-forward + `restart_all.sh --rebuild --keep-auth`，HEAD `854cae1` clean，engine PID `779344` / API PID `779449`，watchdog `engine_alive=true`。健康檢查：`[38]` 仍 FAIL 但是真訊號（live_demo grid re_entry_rate 0.72、lifetime_ratio 0.35），`[39]` 已降為 WARN（1h distinct=7，24h distinct=22 legacy rows aging out），`[12]`/`[33]`/`[11]` 既有 WARN 不變。未改 live/demo risk config、未停策略、未放寬 live 自動交易；所有 live 自動交易或 live 參數自動放權仍必須經 GovernanceHub / Decision Lease + 既有 5 live gates 批准。報告：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-29--w1_t2_attribution_gap_close.md`。

**Grid risk-policy first wave deployed**（2026-04-29 21:44 UTC / 21:44Z healthcheck baseline）：commit `6fdcc91` 已把 `settings/strategy_params_live.toml` 的 `grid_trading.grid_levels` **10→7**，並同步 demo robust-negative `blocked_symbols` 11 個到 live/live_demo（只阻擋新 grid 入場，平倉/減倉不受影響）。Linux `trade-core` 已 fast-forward + `restart_all.sh --rebuild --keep-auth`，engine PID `794012`、API PID `794081`，watchdog fresh。立即 healthcheck：`[22]` PASS、orders/fills consistency PASS、maker intent shape PASS；`[38]` 仍 FAIL（demo n=37 p50=4.1min re=0.39；live_demo n=98 p50=1.7min re=0.71）屬 24h 舊窗口 baseline，驗收窗口從 `6fdcc91` restart 後起算 6h/24h。未改 `risk_config_live.toml` trailing / partial TP，未停用 grid_trading，未放寬 live 授權。

**前一輪狀態快照**（2026-04-29 20:42 CEST · STRATEGY-NAME-ATTRIBUTION wave W1-T1/T3/T4 deployed · W1-T2 deferred · [38] FAIL real signal）：62-finding remediation Batch A-F 全部完成、push、Linux rebuild/redeploy；Items 1-6 follow-through commit `53bff07` 已推送、Linux fast-forward、release rebuild + restart。MLDE gap fix `67b1160` 已部署：demo-only Shadow/Dream min_samples 預設 3、live_demo/live 保持 5，LinUCB trainer 回寫 `learning.linucb_state.cumulative_reward`。**本輪 STRATEGY-NAME-ATTRIBUTION wave**（操 user 觀察 GUI Learning tab 24h LiveDemo 499 / Demo 290 不對稱觸發；PA 報告 `docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-29--strategy_name_attribution_cleanup_design.md` 推薦方案 A schema migration + new column `exit_reason`）：(a) **Phase 1** `554d3e0` GUI 文案修正（影子/真倉 → Demo 引擎/LiveDemo 引擎成交，移除「只記錄意圖」誤導）+ backend `engine_mode_fills_summary` alias + healthcheck `[38] grid_trading_lifecycle_drift` MIT 設計落地；E2 對抗審查抓 1 HIGH（「LiveDemo 管线尚未启动」事實錯誤，已改「此时段无 LiveDemo 成交」）。(b) **Phase 2A** `45bbe4d` W1-T1 schema scaffolding：V033 ADD COLUMN `exit_reason TEXT NULL` + Guard A/B + idempotent + partial index；`TradingMsg::Fill::exit_reason: Option<String>`；FILL_COLS 22→23；helper `build_close_tags()` + 4 unit tests 拆 sibling `helpers_close_tags.rs` 解 §九 1639 LOC violation（helpers.rs 回 1411 baseline）；cargo lib 2369/0；同 commit 修 `[38]` silent-dead（路線 B：去掉永遠空的 `exit_source` filter，改 `entry_context_id` JOIN + close prefix LIKE，揪出 V021 column never-wired root cause），首跑揭發 **真信號 FAIL** — Live grid p50 lifetime 1.6min vs Demo 9.1min（5.7x 短）+ re-entry 76% + fee_burn 2.20x；對應 `risk_config_live` trailing 2.0% / partial_tp=true vs demo 3.5% / partial_tp=false 物理基礎。(c) **Phase 2B-1** `f89b463` consumer-side：W1-T3 Python `strategist_history.effect` 配 normalized strategy_name + 7 新 pytest + GUI fills passthrough 加 `exit_reason`（agent-tracker.js / strategy_read_routes / live_session_account_routes）；W1-T4 healthcheck dual-syntax（`[6]` TRAILING / `[21]` dust spiral / `[28]` phantom risk_close 升級「strategy_name LIKE OR exit_reason LIKE」7d 0 regression）+ 新 `[39] strategy_name_cardinality_drift`（WARN >10 / FAIL >20 distinct strategy_name in 24h）首跑 FAIL 預期（24 distinct，W1-T2 producer 未落地，待自然降回 PASS）。(d) **W1-T2 deferred**：16 close-path emit points（producer-side dynamic format!() → strategy_name=enum + exit_reason=trace）sub-agent stalled 600s（worktree 部分 +302/-36 LOC 在 11 檔超出 PA spec 5 檔範圍且未 cargo verify），worktree discarded 留下次 wave 切更小 sub-task 重派。**所有 commit Mac/origin/Linux 三端同步 HEAD `f89b463`，trade-core working tree clean，[38]/[39] 雙 FAIL 持續 firing 是 by-design**。Post-deploy 既有 WARN `[12]` + `[33]` + `[11]` 不變。Live 自動交易或 live 參數自動放權仍必須經 GovernanceHub / Decision Lease + 既有 5 live gates 批准。

**歸檔索引**（已結案敘述歸檔，不再放 TODO 頭部）：
- 62-finding Batch A-F：see [`docs/archive/2026-04-29--62finding-batch-A-to-F.md`](docs/archive/2026-04-29--62finding-batch-A-to-F.md) （commits `bc3fa70` + `6539e4e` + `5db4e29` PUSHED）
- STRKUSDT P0 Wave：see [`docs/archive/2026-04-29--strkusdt-p0-wave.md`](docs/archive/2026-04-29--strkusdt-p0-wave.md) （F1 `af48ee1` + F2-F7 6 PR PUSHED）
- Wave A-H 完整敘述：see [`docs/archive/2026-04-29--wave-A-to-H-narrative.md`](docs/archive/2026-04-29--wave-A-to-H-narrative.md) （Three-Axes / Wave A Prep-Gate / Wave B / Wave E / Wave F / Wave G / Wave H 全部 commit + Sign-off path 對應表）
- Pre-trim TODO snapshot（817 行原文）：see [`docs/archive/2026-04-29--TODO-pre-trim-snapshot.md`](docs/archive/2026-04-29--TODO-pre-trim-snapshot.md)

**版本**：v3（Wave 線性版；廢除雙軌 P0-P4 章節，P0/P1/P2 降為每項 tag）
**舊版歸檔**：v2 `docs/archive/2026-04-24--todo_v2_dual_axis_snapshot.md`（458 行，Wave+P 雙軌）· v1 `docs/archive/2026-04-24--todo_v1_refactor_snapshot.md`（328 行）· v0 `docs/archive/2026-04-24--todo_snapshot_pre_refactor.md`（700 行）
**簽核**：PM Approved FIX-PLAN v2 → [Sign-off](docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-24--FixPlan_v2_PMApproval.md) · **Wave 3 Final** → [Wave 3 Sign-off](docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-26--wave3_final_signoff.md)
**基礎方案**：[FIX-PLAN v2](docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-24--4.24TodoAudit_FixPlan_v2.md) · [10-Agent audit 索引](docs/audits/2026-04-24--todo_refactor_audit.md)

**Runtime（2026-04-30 23:11 CEST · ssh verify）**：docs-only calibration base before this commit was Mac/Linux source HEAD `5584785` clean；current code-bearing runtime checkpoint remains `a9fce24`（source cleanup/doc calibration 未 rebuild/restart，所以 runtime 不代表載入 `5584785` 後續 source-only/code-split 變更，也不代表本 docs-only commit）。Runtime PIDs from latest verified checkpoint: engine **1529433**, API **1591455**, watchdog alive, gateway **3973441**；Linux watchdog fresh（demo/live alive，paper inactive by design）。Latest cron-wrapper healthcheck (2026-04-30 23:11 CEST) SUMMARY WARN exit 0：WARN `[4]` phys_lock_runtime, `[11]` replay JSON age, `[33]` maker_fill_rate, `[38]` grid lifecycle drift, `[40]` realized edge acceptance；PASS `[13]` edge scheduler fresh, `[14]` exit_features accumulation, `[35]` MLDE data contract, `[36]` advisory boundary, `[37]` demo applier, `[39]` strategy cardinality.

**測試基準（2026-04-29 ML/Dream Demo Autonomy local 後）**：Mac Rust lib **2361/0** · scanner subset **61/0** · DB writer **3/0** · tick attribution helper **16/0** · maker_price **10/0** · `cargo check --bins` PASS · `cargo check openclaw_core` PASS · Python maker/attribution pytest **9/0** · MLDE targeted pytest **63/0** · `python3 -m compileall` targeted PASS · `git diff --check` PASS · healthcheck local registry now includes `[35]`/`[36]`/`[37]`（numbered [1]-[37] skip [17] + [Xa]/[Xb]；無 [0]）· DB migrations expected through V032。2026-04-29 20:21 follow-up：MLDE threshold/reward targeted pytest **24/0** + applier/healthcheck pytest **20/0** + targeted compileall PASS；Linux `[34]`-`[37]` PASS after `67b1160` no-rebuild restart and manual LinUCB retrain.
**21d demo 時鐘**：起算 2026-04-16 22:16 → 解鎖 2026-05-07
**Wave 3 healthcheck**：cron-wrapper runtime 已包含 `[1]`-`[40]`（仍無 `[0]`、skip `[17]`，含 `[Xa]`/`[Xb]`；F7 `[22]`-`[29]`、cost/execution `[30]`-`[34]`、MLDE `[35]`-`[37]`、edge/lifecycle `[38]`-`[40]` 均已在 2026-04-30 23:11 CEST cron log 出現）。被動等待 TODO 以該 cron wrapper log 為 ground truth；直接跑 `.py` 若缺 DB env 會有 credentials false negative。

---

## 🎯 此刻該做什麼（2026-04-30 CEST · docs calibrated · runtime checkpoint a9fce24）

**新主線：62-finding full audit remediation**（operator 2026-04-28 指示：接手剛完成 audit，後續全數修理 62 findings）：
- 權威 audit：`docs/audit/final_record_zh.md` + `docs/audit/final_summary.md`
- PM 排期：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-28--audit_62_findings_remediation_schedule.md`
- 總量：62 findings（P1=29 / P2=29 / P3=4 / P0=0），但含 live-release blockers
- 批次順序：Batch A Live write boundary freeze ✅ committed/pushed/deployed → Batch B Critical auth/secrets/API exposure ✅ committed/pushed/deployed → Batch C Trading record durability ✅ committed/pushed/deployed → Batch D Risk/config fail-closed ✅ committed/pushed/deployed → Batch E Operator/runtime ownership ✅ committed/pushed/deployed → Batch F ML/agent autonomy readiness ✅ committed/pushed/deployed
- Linux deploy 實況：`af9d552` 後，`restart_all.sh --rebuild --keep-auth` 成功重建；engine PID **447123**，API PID **447192**，watchdog `engine_alive=true` + demo/live snapshots fresh。
- Post-deploy gate：`[22] trading_pipeline_silent_gap` RCA 已處理並部署；root cause = demo/LiveDemo fee-rate endpoint unsupported response 只在 startup seed default，週期刷新失敗後沒有 re-seed，2h staleness window 後 cost_gate fail-closed。`bdd3177` 在 periodic refresh 遇 demo unsupported response 時重新注入保守 fee defaults（mainnet/testnet 與非 demo error 不放寬）。最新 `passive_wait_healthcheck.py`：SUMMARY WARN，WARN `[12]` + `[33]` + `[11]`；`[22]` + `[27]` + `[32]` 已清。
- Live gate：live pipeline 拒絕啟動是預期保護，原因為 signed authorization schema v1 vs expected v2；需 Operator 經 `/api/v1/live/auth/renew` 或 renew-review 重新簽署，不可手寫 `authorization.json`。
- PM gate：Batch A 必須先做；每個 implementation batch 必經 `PM -> PA -> E1/E1a -> E2 -> E4 -> QA -> PM`，涉及 live/auth/security 加 `CC/E3/BB` gate；不得用單一大 patch 關 62 條
- Preflight：開工前先處理 branch/worktree ownership、Linux watchdog paper stale drift、建立 62-ID tracking matrix、保存 Linux regression baseline

**Post-Wave-H operator hotfixes**（3 commits `cdc2699` + `20baabe` + `85a4e2d`）：
- ✅ **EDGE-DIAG-2-FUP fee-postonly-2** (`cdc2699`) — Rust strategy-open Fill 改用 TIF-aware `fee_rate_for_intent`；DB column drift 修；其他 fee_rate(symbol) 5 close-path call sites 驗安全；已隨 `af9d552` `--rebuild --keep-auth` deploy
- ✅ **`restart_all.sh --keep-auth` flag** (`20baabe`) — authorization.json 跨 planned deploy 保留；crash/watchdog/systemd 路徑不變；§四 Gate #5 hot-rate verify 5 min re-check 不變
- ✅ **CLAUDE.md EDGE-DIAG-2 drift fix** (`85a4e2d`) — healthcheck `[31]` + `feedback_demo_loose_live_strict_policy.md` 兩項早在 `8a5973f` 隨檔交付，drift 是 PM Sign-off 漏勾

**§九 governance 戰況**：✅ 2026-04-30 22:56 CEST 再收斂 6 個 real code-bearing size drift：`risk_config_advanced.rs` 1360→960（`risk_config_slippage.rs`）、`paper_trading_routes.py` 1246→1160（AI-cost route split）、`counterfactual_exit_replay.py` 1216→1119（help split）、`multi_agent_framework.py` 966→481（Conductor split）、`analyst_agent.py` 805→764、`strategist_agent.py` 866→797。2026-04-29 maintenance 已收斂：`strategist_scheduler/mod.rs` 1819→427、`event_consumer/loop_handlers.rs` 1481→1188、`checks_strategy.py` 1239→924、`checks_engine.py` 1206→1143。2026-04-30 doc calibration confirmed old G5 rows are stale: `main.rs` **1162**, `instrument_info.rs` **1008**, `bybit_rest_client.rs` **933**, `order_manager.rs` **924**, `startup/mod.rs` **1162**, `paper_state/resting_orders.rs` **670**, `risk_config.rs` **1134** are all <1200. Remaining >1200 code-bearing files are high-risk exchange/runtime files `bybit_private_ws.rs` **1413** and `tick_pipeline/commands.rs` **1343**; remaining >1200 tests are `intent_processor/tests.rs` **2375** and `paper_state/tests.rs` **1668** plus Python control-plane test files. These require a dedicated wave, not opportunistic cleanup.

**NOW ACTIONABLE**（時間驅動 / 等候 / 餘工）：
1. **ML-DREAM-EDGE-UNBLOCK-2026-04-29（local complete · demo autonomous / live-governed）** — completion report 已寫入 `docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-29--ml_dream_edge_unblock_completion.md`，demo autonomy report `docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-29--mlde_demo_autonomous_applier.md`。已落地：A) V031 `learning.mlde_edge_training_rows` + `learning.mlde_shadow_recommendations`；B) LinUCB trainer 改讀 valid attribution + post-fee reward，scheduler 每輪以 `demo_live_demo` 合併訓練一次，避免 shared `learning.linucb_state` 被 per-mode 覆蓋；C) ML shadow advisor 產 `rank`/`veto` advisory；D) DreamEngine / OpportunityTracker producers 接入 CognitiveModulator；E) EdgeEstimatorScheduler 每小時 fail-open 執行 MLDE 任務；F) V032 `learning.mlde_param_applications` + `mlde_demo_applier`，demo 可 bounded apply strategy/risk/leverage patches，參數均從 env + Rust `get_param_ranges`/RiskConfig current snapshot 推導，後續 agent 可調；G) healthcheck `[35]` learning data contract + `[36]` shadow recommendation / live lease boundary + `[37]` demo applier audit/live lease boundary。2026-04-29 follow-through 補 `[37]` no-eligible no-op audit row（`status=skipped` + deduped fingerprint），讓「無合格 recommendation」被審計而非 24h rows=0 誤報。仍不可做：live/live_demo 自動交易或 live 參數自動放權，必須另走 GovernanceHub + Decision Lease + 5 live gates。後續：runtime deploy 後觀察 `[35]`/`[36]`/`[37]`、advisory rows、LinUCB pulls、`learning.mlde_param_applications`；rich `mlde_arm_id` 已供 shadow 分析，Rust LinUCB active arm-space 仍是 `v1_15`，若要 production active arm 切到 richer shape 需單獨 arm-space migration。
2. **STRATEGY-EDGE-REPAIR-2026-04-29（策略虧損主線包）** — implementation complete; Linux deployed at `53bff07`. 以 post-fee `net_bps_after_fee` 為主指標，PNL / winrate 僅作參考；修後樣本從 **2026-04-29 12:27:53 CEST** live maker-entry reload 後切分。已落地：`[34]` attribution chain、grouped per-binding fee refresh、maker unsafe fallback skip、scanner `edge_routing`、scanner snapshots、grid robust-negative `blocked_symbols`、bb_breakout demo volume threshold 1.2。後續只追 `[33]` maker_like / fee_drop / reject-rate 和 2026-05-07/08 G2-01 settlement，不把此輪虧損處理變成繼續加風控。
3. **G2-01 PostOnly follow-through** — `[33] maker_fill_rate` 已實裝並 cron 監控；2026-04-30 23:11 CEST rolling 7d fee_drop **20.8%** / maker_like **25.6%**，仍低於 ≥60% 目標，05-07/08 結算若未改善需進 G2-04 disable/策略調整決策。2026-04-29 follow-through 補 `trading.orders.time_in_force` persistence + `trading.intents.details` maker metadata（`time_in_force` / `post_only` / `maker_timeout_ms` / `limit_price`），讓 [33] 的 PostOnly diagnostics 不再被空 TIF 欄拖住。
4. **Fee-refresh RCA follow-through** — `[22]` cleared after `bdd3177` deploy；items 1-6 follow-through 已修 demo only-stale 問題並部署：fee refresh task 改 grouped binding，啟動已看到 `engine=demo env=Demo` + `engine=live env=LiveDemo` 註冊；post-restart DB query 已無 fee-stale verdict。下一個自然驗證點是首個 1h periodic refresh log 對每個 demo endpoint binding 都出現 `conservative defaults re-seeded`，且 >2h 不再出現 fee-rate staleness cost_gate self-lock。
5. **bb_breakout Phase 2 threshold tuning** — `[12]` 目前 WARN：7d entries=1，已脫離永久 dormant 但仍低量。2026-04-29 5m 14d sweep 已跑：24/84 combos 達 ≥20 signals；最佳 5m fwd6 (30min) raw mean 約 +8bps，但 t-stat 0.62（遠低 95% 與 Bonferroni 門檻），高樣本組多為負；結論是不切 runtime timeframe，保留 demo 1m 作可觀察/學習樣本，後續交由 MLDE/Dream read-only sweep 累積。
6. **Live auth renewal** — 若要恢復 LiveDemo/live pipeline，Operator 需經 API renew schema v2 授權；這是 Batch A live gate 強化後的預期行為。注意：Live pipeline 能啟動 ≠ ML/Dream/Agent 可以 live 自動交易，後者仍需 GovernanceHub 批准。
7. **G3-09 Phase C Wave 1 impl** — operator 「等時間長一些再看」；PA RFC `90d1a2e` ready
8. **Phase B observation period launch** — bundled with Phase C (operator decision (C))
9. **Maintenance backlog** 等下次 wave：
   - G3-08-FUP-MAF-SPLIT-CLEANUP-A P4：lazy re-export 仍保留（Scout 首入場 partial-import 風險尚在）；Conductor 已拆出，非 immediate blocker
   - SINGLETON-POLLUTION-PHASE2-ROUTES P4 (Mac-only)

**Time-driven**: G2-02 ma_crossover dual-track (~05-03), G2-01 PostOnly acceptance (~05-07/08), P0-3 edge decision (~05-15). G1-04 as-of compute artifact is complete; do not re-open it unless a new full-window comparison is explicitly requested.

**EDGE-DIAG-2 留尾被動**: (ii) PostOnly maker fill rate 待 ≥1w demo 資料驗（cdc2699 deploy 後 `trading.fills.fee_rate` 也會反映正確 TIF，兩條訊號互驗） (iv) demo bb_breakout 1m bandwidth 結構性問題等下次 sweep / 升 5m timeframe

詳：[Wave H Sign-off](docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-28--wave_h_signoff.md)

---

## 🗂️ 上波索引（已歸檔 · 完整敘述見 archive）

完整敘述（commits + Sign-off + commit message + post-Wave-H operator hotfixes）見 [`docs/archive/2026-04-29--wave-A-to-H-narrative.md`](docs/archive/2026-04-29--wave-A-to-H-narrative.md)。下方僅留 Wave 名 + Sign-off 報告路徑供查找：

### 各 Wave PM Sign-off 報告路徑

- **Wave H**（2026-04-28 深夜 · 6 commits `dbba235..0a50c6c` · 3-way active warn cleanup splits + 2 inline fixes）— [Sign-off](docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-28--wave_h_signoff.md)
- **Wave G**（2026-04-28 深夜 · 5 commits `8a5973f..3b0a0d7` · 4-way file size cleanup splits · §九 1200 hard cap 全清）— [Sign-off](docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-28--wave_g_signoff.md)
- **Wave F**（2026-04-28 深夜 · 3 commits `739af3c..22e8482` · engine `--rebuild` deploy + SINGLETON sibling fix · operator decision (C) defer Phase B observation）— [Sign-off](docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-28--wave_f_partial_signoff.md)
- **Wave E**（2026-04-28 深夜 · 8 commits `decf712..3788498` · cost_edge_advisor_boot split + Phase C PA RFC + SINGLETON-POLLUTION fix）— [Sign-off](docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-28--wave_e_signoff.md)
- **Wave B**（2026-04-28 晚 · 10 commits `cf34e96..dbe2477` · G3-09 Phase B Wave 1 + G8-01 W2 + W3，含 1 hotfix round）— [Sign-off](docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-28--wave_b_signoff.md)
- **Wave A Prep-Gate Trio**（2026-04-28 早 · 5 commits `82347a5..a6bf090` · sticky-ts + LOSSES-WIRING + spawn-test）— [Sign-off](docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-28--wave_a_prep_gate_signoff.md)
- **Three-Axes Wave**（2026-04-27 23:55 · 5 commits `6e466c8..7c32d1f` · MAF-SPLIT P1 + G8-01 W1 + G3-09 daemon test）— [Sign-off](docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-27--three_axes_wave_signoff.md)
- **Phase 4 5-Agent state events + G3-09 Phase A**（2026-04-27 21:30 · 6 commits + 5 sequential merges `c8a4a55..b67b0a8` · env=1 H_state 10-bucket envelope live · 解阻 G8-01 + G3-09 Phase B/C）— [Sign-off](docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-27--phase4_complete_signoff.md)

---

## 🎯 Wave 3 status（2026-04-26 04:30 CEST · 派發層面 100% 完成 · passive observation）

**Wave 1**：✅ 全完成（G1-01/02/03/05/06 + G6-01~05；2026-04-24 收尾）。

**Wave 2**：✅ 主軸完成（G3 全鏈 / G4 完整 / G5 大部 / G7 9/10 / G6-FUP 雙 P0 RCA）。剩餘 active blocker 主要是 G7-05 cost_gate bind passive wait；G3-07 / G3-08 core 已完成，僅留 cosmetic/low-priority follow-up。

**Wave 3**：✅ **派發層面 100% 完成**（5 波 6 commits c1142d2→df882ad）：
- W2（c1142d2 + 8946e47）：4-agent audit + G2-02 counterfactual + G8-02 parity + grid G7-09c Phase 2
- W3（55801fe）：G2-06 bb_breakout disable 落地 + 3 PA RFC（EDGE-P1b/P2-flip/G2-03）
- W4（60fdf74）：EDGE-P1b 4/4 + EDGE-P2-flip T1+T3 + G2-03 4/4 schema staging
  - ⚠️ **G2-03 schema-only landing**：`_with_override` **0 production caller**（per FA 2026-04-26 H2 audit）；`position_risk_evaluator.rs:117` + `step_6_risk_checks.rs:200` 仍呼 thin wrapper（per_strategy=None）→ ma_crossover SL/TP override 寫值對 production 路徑 **0 影響**；real binding 須 G2-02 ~05-03 結論 + **G2-03-FUP-CALLER-WIRE P1 派發**才生效（已在 Backlog L401）
  - ⚠️ **EDGE-P1b 7 維 IPC bind 真實 6/7 維**：`stale_peak_ms` (dim 5) + `shadow_enabled` 不在 IPC `update_risk_config` 7 字段（per FA 2026-04-26 H1 audit）→ calibrator 算 percentile 但無法純 IPC 寫，需 TOML edit + reload_risk_config 雙步驟；新 backlog ticket **EDGE-P1b-FUP-STALE-PEAK-IPC** 追蹤閉合
- W5（9cfdd52）：EDGE-P2-flip T2（healthcheck [15] per-strategy）+ G2-FUP-IPC-LEGACY-MS-FIX P1
- Sign-off（df882ad）：PM Wave 3 Final Sign-off + CLAUDE.md §十一 update + rebuild 部署成功

**Wave 3 全工 runtime 驗證**（post-rebuild healthcheck）：
- ✅ [12] bb_breakout disabled by G2-06（active=false in TOML）; fill check skipped
- ✅ [18] disabled inventory: bb_breakout, funding_arb (active count=3: bb_reversion, grid_trading, ma_crossover)
- ✅ [14] per-strategy 切片: grid_trading=282[READY] / ma_crossover=146[GROWING] / bb_reversion=7[SPARSE] / orphan_frozen=3[SPARSE] (READY_frac=63%)
- ✅ [15] Phase 1a dormant by design（shadow_enabled=false, agreement evaluation deferred）
- ✅ IPC HMAC unit test Linux 3 passed in 0.03s（軌 2 100% legacy fail auth fix verified）
- ⚠️ [11] WARN counterfactual：sample count 已滿（latest post-P013 n=864/200），仍因 replay JSON age 17.2h 等 fresh artifact + PASS streak
- 🔴 [16] FAIL strategist_cycle_fresh fresh-boot expected（rebuild 後 1min healthcheck，每 5min cycle，6h cron 自然 PASS）

**剩餘 Wave 3 被動等待**（自然解鎖，無派發必要）：
- 2026-04-30: EDGE-P3 [11] 樣本量已滿（post-P013 n=864/200）；仍需 replay JSON freshness / 連續 PASS 條件轉綠後才可部署 Gate 1 fallback
- ~05-01~05-03: G2-02 真實 1w post-G7-09 數據 → counterfactual 雙軌驗證
- **~05-02**: G1-04 滿 1w post-G7-09 fix（deploy 04-24 23:41）→ **G1-04-FUP-FINAL-COMPUTE P1 派發**（QC+FA fee drop + R:R baseline final compute）
- **~05-06**: GRID-LIFECYCLE-DRIFT 7d 觀察期 → [38] grid_trading_lifecycle_drift 結論（lifetime / fee burn / re-entry 三指標）；觸發 = GUI Learning tab 24h LiveDemo 157 vs Demo 63（2.5x），物理基礎 = `risk_config_live` trailing 2.0% / partial_tp=true vs demo 3.5% / partial_tp=false；**[38] 修後 (`45bbe4d` 路線 B + entry_context_id JOIN) 首跑揭發真信號 FAIL — Live grid p50 lifetime 1.6min vs Demo 9.1min（5.7x 短）+ re-entry 76% + fee_burn ratio 2.20x，MIT in-message audit 2026-04-29 設計**；observation 已不需等 7d，可加速 PA RFC 評估 grid_trading live config（縮 levels / 暫停 5 robust 負 cells AAVE/GALA/ENA/DOGE/FARTCOIN / live 改 trailing 2.5~3.0% / 暫停 partial_tp）
- **2026-04-29 21:45 CEST RFC ready**：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-29--grid_risk_policy_rfc.md`。最新 DB 證據修正原假設：live_demo close reason 主要是 `strategy_close:grid_close_*`，不是 trailing；`partial_tp_enabled` 目前 Rust 僅 schema/validation 無 runtime consumer。RFC 推薦第一波只改 `settings/strategy_params_live.toml`：copy demo 11 個 `blocked_symbols` + `grid_levels 10→7`；trailing/partial TP 暫不動。
- ✅ STRATEGY-NAME-ATTRIBUTION-W1-T2 producer-side gap 已完成（`5895579` + hotfix `854cae1`）；latest [39] PASS（1h distinct=2-3，24h distinct=8），舊「~05-13 重派」文字已歸檔為 RCA。
- ~05-07: P0-2 21d demo 解鎖 + G2-01 PostOnly 驗收
- ~05-10: EDGE-P1b per-strategy ≥200 rows → calibrator manual approve flow
- ~05-15: P0-3 邊評決策會（PM + FA + PA + QC）

**4 follow-up tickets 狀態**（W4/W5 衍生 → Backlog）：
- ✅ ~~G2-FUP-IPC-LEGACY-MS-FIX P1~~（W5 軌 2 修，Linux unit test verified）
- 🟠 G2-03-FUP-CALLER-WIRE P1（等 G2-02 ~05-03 後派 wire caller chain）
- ✅ ~~EDGE-P1b-FUP-STALE-PEAK-IPC P2~~（`c2ca032` completed；shadow_enabled remains TOML-only by design）
- ✅ ~~G5-FUP-IPC-MOD-SPLIT P2~~（`bd5ce56` completed；old open mention was stale）
- ✅ ~~G1-FUP-CALIBRATOR-WARNING P3~~（`92ea90b` + `f633a5a` completed；banner removed after ticket stale）

**本週 Top 3**（passive observation，無主動派發）：

1. **🟡 [16] strategist_cycle_fresh 6h 監控** — rebuild 後 fresh-boot expected，下個 cron tick 應 PASS；如真 wedged → P1 escalate
2. **🟡 [11] counterfactual clean window freshness** — sample count 已超標（post-P013 n=864/200），目前 WARN 原因是 replay JSON age 17.2h；連續 PASS 後 EDGE-P3 才解鎖
3. **🟡 G7-05 cost_gate grand_mean bind** — read-only check 2026-04-30：grand_mean_bps=-14.78、eligible validation cells=0、shrunk_bps>0 **4/247**；仍不足以 bind，先保持 passive

**Live target**：~2026-05-30 中位 ±7d（PM W2 sign-off 不變）

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
| **W1** | W17/18 | **4/24→5/08** | G1 edge infra + G6 healthcheck | scheduler live + event_consumer <1200 行 | ✅ **全完成**（G1-04 + 背景 passive 觀察中）|
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
| ~~**G1-04**~~ | ✅ as-of compute complete 2026-04-30 | fee drag / R:R 邊際驗證基線 — **2026-04-24 23:05 initial 3d baseline 完成**：揭 FIX-FEE-POSTONLY-1 bug → **G7-09 fix deploy 2026-04-24 23:41 (`872478a`)**；**2026-04-27 21:30 verify ~3d post-fix accumulation**：1022 fills / 13 strategies / avg_fee 5.34bps / sd 0.9137（vs pre-fix uniform 5.50/0）→ fix 在 work but maker_pct 僅 **2.84%**。**2026-04-30 operator as-of compute**：full 5.94d post-G7-09 window maker_like 26.28% / fee_drop 21.30%，但 post-2026-04-29 12:27 reload slice maker_like **73.23%** / fee_drop **59.32%**；R:R mixed，ma_reverse_cross still net negative。This closes the G1-04 compute artifact; G2-01 acceptance remains separate around 2026-05-07/08. | Completed as-of artifact | QC / FA | see Backlog row | [Initial baseline](.claude_reports/20260424_230500_g1_04_initial_baseline.md) · [Follow-through report](docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-30--todo_followthrough_g1_g8_mlhygiene.md) |
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
| **G3-03 Phase B** | ✅完成 | Python ExecutorConfig cache + ExecutorAgent rewire — `app/executor_config_cache.py` 新增 ~435 LOC（`ExecutorConfigCache` 單例 + daemon thread poller，預設 10s，env `OPENCLAW_EXECUTOR_CACHE_POLL_SEC` 可調，0.5s lower bound；`ExecutorRuntimeConfig` 不可變 snapshot；fail-closed `shadow_mode=True` 預設、IPC 錯誤後保留前一個好 snapshot）· **`shadow_mode_provider` live at `program_code/exchange_connectors/bybit_connector/control_api_v1/app/executor_agent.py:145-186`**，取代原 hardcoded `_shadow_mode = True` class attr（CLAUDE.md §二 原則 #3 fix · per G3-03 Phase B implementation） — ctor 改 `shadow_mode_provider: Callable[[], bool] = None`（None → fail-closed `lambda: True`）· `strategy_wiring.py:467` wire `get_executor_config_cache()` + `start_polling()` + `shadow_mode_provider=cache.shadow_mode_provider()`；CLAUDE.md §九 加 `_CACHE_INSTANCE` / `_CACHE_LOCK` 登記；17 new pytest cases；Linux pytest -k 'executor' **66/0** ✅；Phase A defaults (3 TOML shadow_mode=true) 保留現行為；Python-only 不需 `--rebuild` · **Note**：RFC §5.2 規定 100ms poll，本實作預設 10s（4-worker × 100ms socket round-trip 過密），如 PA 認定 100ms 為硬性，env 即可降至 0.5s 下限 | G3-02 Phase A | E1+PA / E2+E4 | 完成 2026-04-25 | [G3-03 Phase B report](.claude_reports/20260425_023220_g3_03_phase_b_executor_cache.md)（commit `51608fe`）|
| **G3-02 Phase C** | ✅完成 | Operator API for executor shadow_mode flip — `POST /api/v1/executor/shadow-toggle` 5-gate live auth chain（Operator role + live_reserved + OPENCLAW_ALLOW_MAINNET + secret slot + authorization.json HMAC）；preview/confirm 兩段；DEFAULT-OFF env-gate；`app/executor_routes.py` 625 LOC + 17 pytest tests | G3-02 Phase A/B | E1+PA / E2+E4 | 完成 2026-04-25 | commit `325582f` |
| **G3-03（Rust IPC）** | ✅由現有路徑覆蓋 | Rust `intent_processor` IPC handler — Phase B `51608fe` Python ExecutorConfigCache + executor_agent rewire 後，shadow→live toggle 透過既有 `patch_risk_config` IPC（Phase A 4 e2e tests `03acedb` 已驗 deep-merge）+ 既有 SubmitOrder intent path（Rust intent_processor 從 Phase 1 起即接收 Python intents）；G3-04 e2e `852da0f` 端到端證明（cache poll → flip → IPC → SubmitOrder mock）；不需新增獨立 Rust handler | G3-02 Phase A/B/C | E1 / E2+E4 | 完成 2026-04-25 | G3-04 e2e + Phase A IPC 雙覆蓋 |
| **G3-04** | ✅完成 | ExecutorAgent shadow→live e2e 整合測試 — `tests/test_executor_shadow_to_live_e2e.py` 5 test class / 8 case，556 行純測試 0 production diff：(1) `TestDefaultStateShadow` fresh cache fail-closed → 0 IPC (2) `TestIpcFlipShadowToLive` shadow→flip→live + payload shape verify (3) `TestIpcFlipBackToShadow` live→shadow flip-back (4) `TestIpcUnavailableFailClosed` 初始化後 IPC 失敗保留 live snapshot；未初始化失敗維持 shadow (5) `TestPerEngineIsolation` paper/demo cache 各自獨立。Mock 邊界：cache poll mock `_fetch_via_ipc_blocking`，SubmitOrder mock `paper_trading_routes._ipc_command`；用同步 `cache._poll_once()` 避免 timing flake。**未發現 production gap**：跑通本身證明 G3-02 Phase A + G3-03 Phase B chain (IPC→cache→provider→execute→IPC) 端到端通暢。Linux pytest -k 'executor or shadow_to_live' **74/0** ✅；pytest baseline 3013 → 3021 (+8) | G3-03 | E4 / QA | 完成 2026-04-25 | [G3-04 report](.claude_reports/20260425_023800_g3_04_e2e_executor_shadow.md)（commit `852da0f`）|
| **G3-05** | ✅完成 | EDGE-DIAG-1-FUP-SHADOW-ENABLED-IPC — `exit.shadow_enabled` IPC hot-reload regression test coverage 添加；7 個 `exit.*` 欄位 deep-merge 路徑驗證；`<60s` rollback 可行（無須 rebuild），TOML persist + IPC dual-path | 無 | E1+E2 | 完成 2026-04-25 | commits `e710026` (test) + `491b045` (docs) |
| **G3-06** | ✅完成 Phase A | Layer 2 autonomous 升級規則（L0→L1→L2 criteria） — `app/layer2_escalation.py` `EscalationTier` enum + `decide_escalation_tier()` + `LayerEscalationConfig`（DEFAULT-OFF env-gated）；量化升級觸發條件落地（base/intermediate/advanced thresholds + AI cost guard）；ipc_server `dispatch_request` 13-arg signature 添加 `live_auth_recheck_tx`（19 call sites 由 G3-11 collateral 修齊） | G3-02 | AI-E+PA / E2 | 完成 2026-04-25 | commit `82ef8e1`（Phase B Rust integration deferred）|
| ~~**G3-07**~~ | ✅ 完成 2026-04-26 | Layer 2 工具箱補全 — commits `ac6c09a` + `31fa96c`：591 行 sibling + 36 unit tests + 1 e2e (mark slow real network)；`query_onchain`（funding_rate / OI / liquidations_24h, free tier）+ `check_derivatives`（mark_price / funding / oi_24h_change_pct, Bybit V5 PUBLIC）；DEFAULT-OFF env-gated × 2 + HTTP 5s timeout env-overridable；fail-closed 4 層 gate；Linux pytest 三檔 136/0；E2 6/6 ACCEPT | G3-06 | E1 | 完成 2026-04-26 | E2 batch review `a5ef805` ✅ |
| ~~**G3-08 PA design + Phase 1A+B**~~ | ✅ 完成 2026-04-26 commits `7564d07` (PA design) + `aa287c4` (Phase 1A Rust h_state_cache, isolation worktree merge `4689fc8`) + `1c7b20e` + `deac4bc` (Phase 1B Python invalidator + query_handler + reverse IPC route) | Phase 1A: h_state_cache/{mod,types,poller,tests}.rs 5 new + ipc_server/handlers/h_state.rs + main_boot_tasks env-gate + dispatch.rs +18 → 590 行；22 unit tests; engine lib 2176→**2198/0** ✅ · Phase 1B: app/{h_state_invalidator,h_state_query_handler}.py + tests 4 new ~1040 lines; 35 unit tests Mac+Linux; IPC route ai_service_dispatch.py:120 ✅ · DEFAULT-OFF env `OPENCLAW_H_STATE_GATEWAY=1` 嚴格 "1" 比對；Sub-task C (strategy_wiring + healthcheck [20]) 留 G3-08-PHASE-1C-WIRING backlog；Phase 2-4 (~9d) 留 G3-08-PHASE-234-IMPL backlog | G3-03 | PA + E1+E2 | 完成 2026-04-26 | report `2026-04-26--g3_08_h1_h5_ipc_gateway_design.md` + tier4_signoff |
| ~~**G3-09 cost_edge_ratio (PA design)**~~ | ✅ 完成 2026-04-26 commit `642c34c` (Tier 9 Track 2) | PA RFC NEW cost_edge_advisor module (8/8 vs 4 alternatives)；Phase A schema 4.5d → B shadow 1.5d → C live 2.5d；§11 self-contained E1 Phase A prompt template ready；PM T9-LOW-1 ACCEPT threshold = -0.5 negative operator-tunable (per §2.4 ratio direction lock-in) | 完成 2026-04-26 | ✅ |
| ~~**G3-09-PHASE-A-SCHEMA impl**~~ | ✅ 完成 2026-04-27 commit `00682ef` | cost_edge_advisor module ~1338 LOC Rust (mod/types/advisor/tests + IPC handler) + 21 modified Rust + 3 TOML [cost_edge] + 3 Python healthcheck [30]; PM Tier 9 T9-LOW-1 threshold = -0.5 lock-in; env-gate dual safeguard; cargo lib 2252 → **2290 / 0 failed** (+38 tests); E2 PASS (0 finding) / E4 PASS Mac 2290/0 兩遍 + Linux baseline; 0 trade impact (advisory only); 解阻 G3-09 Phase B/C | PA design 完成 + PM ratio direction decision | ✅ | 完成 2026-04-27 (Sign-off `2026-04-27--phase4_complete_signoff.md`) |
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
| ~~**G5-01**~~ | ✅ 完成/校準 2026-04-30 | `main.rs` 2062→**1162**（<1200；G1-03 commit `357a1e7` 完成，doc calibration 重新 `wc -l` 核實） | 無 | E5+E1 / E2 | 完成 | ✅ |
| **G5-02** | ✅完成 | `live_session_routes.py` 1449 → 706+436+439（live_session_routes 706 / live_session_endpoints 436 / live_session_account_routes 439，全 <800）+ `live_session_governance` 178；sibling 走 `from . import live_session_routes as core` 經 namespace 引用，保留所有外部 import + monkeypatch；14 routes byte-identical；test_live_gate_fallback 14/14 + pytest -k live 117/0 + pytest -k live_trust|live_session|live_gate 77/0 全綠 | 無 | E5+E1 / E2 | 完成 2026-04-25 | [G5-02 report](.claude_reports/20260425_014424_g5_02_live_session_split.md)（commit `e0d02b2`）|
| ~~**G5-03**~~ | ✅ 完成/校準 2026-04-30 | `instrument_info.rs` 1975→**1008**（<1200；G1-03 commit `1127f38` 完成，doc calibration 重新核實） | 無 | E5+E1 / E2 | 完成 | ✅ |
| **G5-04** | ✅完成 | `ai_service.py` **1318**（實測比 TODO 估的 1258 多 60 行）→ ai_service.py 242（facade + singleton + system prompts + factory）+ ai_service_dispatch.py 813（`AIService` class + 5 handlers）+ ai_service_listener.py 373（`_probe_unix_listener_alive` + `AIServiceListener`）；sibling pattern 同 G5-02（`from . import ai_service as core` + `core.<name>` 引用）；外部 import 透過 re-export 不變；Linux pytest -k 'ai_service or llm or budget' **50/0**；3 檔全 <1200，2 檔 <800（dispatch 813 為 class cohesion 不可避免） | 無 | E5+E1 / E2 | 完成 2026-04-25 | [G5-04 report](.claude_reports/20260425_015603_g5_04_ai_service_split.md)（commit `37172b0`）|
| **G5-05** | ✅完成 | `bb_reversion.rs` 1143 → 3 sibling：mod.rs 433 + params.rs 287 + tests.rs 460（全 <800 §九 warning 線）；`positions`/`cooldown`/`persistence` 由 private → `pub(crate)` 讓 sibling tests.rs mutate；`BbReversionParams` 由 `pub use params::BbReversionParams` 保留外部 path；bb_reversion filter 20/20 + stress_integration 35/35 全綠；Linux release 2003/0 | 無 | E5 | 完成 2026-04-25 | [G5-05 report](.claude_reports/20260425_000438_g5_05_bb_reversion_split.md)（commit `8523946`）|
| ~~**G5-06**~~ | ✅ 完成/校準 2026-04-30 | 原列 5 檔已全 <1200：`bybit_rest_client.rs` **933**、`order_manager.rs` **924**、`startup/mod.rs` **1162**、`paper_state/resting_orders.rs` **670**、`config/risk_config.rs` **1134**。Current residual >1200 已改列 §九 dedicated wave：`bybit_private_ws.rs` / `tick_pipeline/commands.rs` / tests。 | 無 | E5+E1 / E2+E4 | 完成 | ✅ |
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
| **G7-05** | 🟡passive wait | cost_gate grand_mean bind condition — 2026-04-30 read-only check：`edge_estimates.json` age 0.84h / `_meta.n_cells=83` / populated cells=247 / `grand_mean_bps=-14.78` / validation eligible cells=0 / shrunk_bps>0 **4/247**。雖 `grand_mean > -50bps` 已滿足，但 validation 全部 insufficient、positive shrunk 極少，仍 **不 ready to bind**；保持 passive，等 validation eligible cells + strategy-sliced positive evidence 再派 bind code。| G1-01 + G7-09 | QC+E1 / FA | 2-3h（post-data） | bind when grand_mean > -50 bps ∧ validation eligible cells >0 ∧ ≥2 strategy-sliced shrunk>0 + post-fix threshold validated |
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
- [x] G5-01~07 listed refactor rows are complete/recalibrated — `main.rs` **1162**、`instrument_info.rs` **1008**、G5-06 原 5 檔均 <1200；remaining >1200 code-bearing files are now separate §九 dedicated-wave residuals (`bybit_private_ws.rs` / `tick_pipeline/commands.rs`), not stale G5 rows
- [x] G7 量化配置化完成 — 9/10（G7-01 surface ready / 02 / 03 Phase A+B 3/4 / 04 Phase A / 06 / 07 / 08 / 09 + 09b/09c Phase 1）；G7-05 passive wait Post-G7-09 數據 ~05-01+
- [x] **雙 P0 RCA 修復**（額外完成）：G6-FUP-NEWS-HALT-DEDUP-1 + G6-FUP-TICK-PIPELINE-DEAD-1（commit `b980986`）解 engine "crashloop" 假象

---

## ⏩ Wave 3（W20-W23 · 5/22→6/12）— Edge 穩定 + ML canary

### EDGE-DIAG-1 Phase 3 部署 + Phase 1b（前置條件嚴格）

| ID | Tag | 項目 | 前置條件（必須 ALL 滿足） | 負責 | 工時 |
|---|---|---|---|---|---|
| **EDGE-P3** | 🟡P1 passive | strategy-scoped Gate 1 fallback 部署 | (a) clean bucket ≥200 rows pooled 已滿（2026-04-30 [11] post-P013 n_rows=864/200）· (b) per-strategy bootstrap 95% CI lo >0 仍需 fresh replay artifact · ~~(c) orphan_frozen clean ≥20 rows~~ → **(c') 已修：orphan_adopted ≥20 rows**（MIT 2026-04-26 audit）· (d) healthcheck [11] 連 3d PASS 尚未滿：latest [11] WARN 原因為 replay JSON age 17.2h，不是 sample count。 | PM+FA+QC / E2 | 2d (passive) |
| **EDGE-P1b** | ✅ schema landed / passive 等資料 | `exit_features` 累積 ≥1w + 7 維閾值 bind（7 維 confirm: est_net_bps / peak_pnl_pct / atr_pct / giveback_atr_norm / time_since_peak_ms / price_roc_short / entry_age_secs）— **2026-04-26 W4 軌 1 完成 schema landing**（PA RFC + E1 4/4 子任務）：(T1) calibrator `helper_scripts/research/exit_threshold_calibrator.py` 1067 行 dry-run 預設 + per-strategy stratification + cohort filter (T2) summary `exit_features_summary.py` 825 行 distribution + sample sufficiency (T3) IPC `restore_exit_config_defaults` Rust handler +332 行 + ipc_server dispatch (T4) healthcheck [14] per-strategy 切片升級。**等資料**：~05-10 達 per-strategy ≥200 rows（當前 grid 282 / ma 146）→ 派 calibrator manual approve flow（不自動 IPC 寫風控值）。Push back: stale_peak_ms + shadow_enabled 不在 IPC 7 字段 → 標 toml_only_fields_skipped。 | passive ≥1w + per-strategy ≥200 rows | PM+QC / E4 | 完成 schema 2026-04-26 + passive |
| **EDGE-P2-flip** | ✅ tooling landed / passive 等 EDGE-P1b | Combine Layer shadow flip（**RFC 2026-04-26 confirmed flip 範圍 = `RiskConfig.exit.shadow_enabled`，非 ExecutorAgent shadow_mode**；acceptance = healthcheck [15] 24h ≥95% agreement + per-strategy ≥95%；IPC patch 直接 flip 非灰度；manual revert 90s SOP）— **2026-04-26 W4 軌 2 + W5 軌 1 完成 tooling**：(T1) `helper_scripts/canary/edge_p2_flip_dry_run.py` 829 行 5/5 pre-flight smoke (T2) healthcheck [15] per-strategy 切片升級 + `shadow_disagreement_breakdown.py` 592 行 disagreement_reason 分佈報告 (T3) `helper_scripts/operator/edge_p2_{flip,revert}.sh` paste-safe SOP shell。Mac + Linux 真機 dry-run 全 PASS。**等 EDGE-P1b** + manual operator approve flip 觸發。 | EDGE-P1b 完成 + healthcheck [15] 連 7d ≥95% agreement | QC+PM / E2 | 完成 tooling 2026-04-26 + passive |

### G2 策略驗證 + 決策

| ID | Tag | 項目 | 前置 | 負責 | 工時 |
|---|---|---|---|---|---|
| **G2-01** | 🟠P1 passive | P1-10 PostOnly 1-2w 驗證 — passive ~05-07/08 出結果（fee drop ≥60% 或下架）；healthcheck [33] maker_fill_rate cron 監控中（2026-04-30 23:11：7d fee_drop 20.8% / maker_like 25.6%，仍低於 ≥60% 目標） | PostOnly demo 04-21 部署 | PM+QC+FA / E4 | passive ≥1w（04-21~05-07 出結果）|
| **G2-02** | ✅ tool landed / passive 等資料 | ma_crossover R:R 對稱性 counterfactual — **2026-04-26 W2 完成 (c) 並行**：E1 寫 `helper_scripts/research/ma_crossover_counterfactual_replay.py` 822 行（從 trading.fills self-INNER-JOIN，realized_pnl GROSS，公式 cf_net_bps = (realized_pnl/notional*10000) - 2*scenario_fee_bps；含 partial-close caveat docstring）。E1 push back: PM SQL spec 7 欄位錯，採 V017 FILL-CONTEXT-LINKAGE-1 真實 schema。**等 ~05-01~05-03** 真實 1w post-G7-09 demo 數據 → ~05-03 跑 tool 雙軌驗證（理論值 fee=2bps + realized）→ G2-03-FUP-CALLER-WIRE 觸發 | tool ready / 等真實數據 | QC+FA / E2 | 完成 tool 2026-04-26 + passive |
| **G2-03** | ✅ schema staging / 等 G2-02 binding | ma_crossover SL/TP 策略層定制 (Option B)— **2026-04-26 W4 軌 3 完成 schema landing（PA RFC §6 + E1 4/4 子任務 isolation 主樹）**：(T1) `risk_config_per_strategy.rs` 191 行 StrategyOverride 加 4 pct 字段（stop_loss_max_pct / take_profit_max_pct / trailing_activation_pct / trailing_distance_pct，per PA RFC §2.1 — pct 型，非 ATR/bps 混合 PM prompt 錯誤）+ validate (T2) `risk_checks.rs` +140 行 effective_*_max_pct helpers + check_position_on_tick_with_override（**0 production caller，schema-only landing**）(T3) 3 環境 TOML `[per_strategy.ma_crossover]` commented schema (T4) `g2_03_bind_ma_sltp.sh` 256 行 + `g2_03_bind_helper.py` 405 行 binding SOP shell wrapper。E2 staging marker 確認；E1 push back PM prompt schema spec drift（採 PA RFC 為準）。**衍生 G2-03-FUP-CALLER-WIRE P1**：等 G2-02 ~05-03 後派 wire caller chain（step_6_risk_checks）真實啟用 SL/TP override。 | schema 完成 / 等 G2-02 + G2-03-FUP wire | E1+FA / E2+E4 | 完成 schema 2026-04-26 + caller wire passive |
| **G2-04** | 🔴P0 passive | **Grid disable 決策會**（若 PostOnly 後仍負 edge） | G2-01 + P0-3 輸入 | PM+FA 決策 | 1h 會議 (~05-08) |
| **G2-05** | ✅完成（觸發 G2-06）| bb_breakout FIX-26-DEADLOCK-1 rebuild 驗證 — **2026-04-26 ssh healthcheck [12] verify**：FAIL 7d entries=0；FIX-26-DEADLOCK-1 已在 binary（22:34 + 01:30 多次 rebuild）排除 deadlock 殘留 → **結構性 dormancy CONFIRMED**，觸發 G2-06 | operator rebuild | MIT / QA [12] | 完成 2026-04-26 |
| ~~**G2-06**~~ | ✅完成（disabled） | bb_breakout 結構性 dormancy 處置 — **2026-04-26 PA RFC `2026-04-26--g2_06_bb_breakout_disposal_rfc.md` 推 C 永久 disable** + PM approve；落地：(a) `[bb_breakout].active=false` 三環境 TOML（demo/paper/live） (b) healthcheck [12] active=false 時 PASS skip (c) 新增 [18] disabled_strategy_inventory（CLAUDE.md §三 G6-04 drift 防線）(d) BbBreakoutProfile + sweep tool 保留為 future investment（per §6 重啟條件）。MIT 推 5m / QC 推 C / PA 推 C dominated strategy 分析（B ROI 不利、F2 signals≠edge 未驗證、Wave 3 主軸擠壓）。重啟需新 PA RFC + 5m timeframe 升級。 | G2-05 | E1 / E2 / E4 | 完成 2026-04-26 | E1 Report `2026-04-26--g2_06_bb_breakout_disable_landing.md` |

### G8 測試 / Healthcheck 擴展（新增，QA+AI-E）

| ID | Tag | 項目 | 前置 | 負責 | 工時 |
|---|---|---|---|---|---|
| ~~**G8-01**~~ | ✅ 完成 2026-04-30 | e2e 認知自適應測試（80+ coverage）— W1 dead-path production fix + W2 `CognitiveModulator` 22-case unit suite + W3 StrategistAgent integration suite 已存在並通過；本輪 operator follow-through 實測 `test_cognitive_modulator_coverage.py` + `test_strategist_cognitive_integration.py` + `test_strategist_cognitive_w1_fix.py` **40/0**，stdlib trace/AST coverage `CognitiveModulator` **76/81 (93.8%)**；`strategist_cognitive.py` integration helper covered on hot paths（51/76 executable AST statements），regret/dream producer branches按 PA Option C deferred。 | 完成 | ✅ | report `2026-04-30--todo_followthrough_g1_g8_mlhygiene.md` |
| ~~**G8-02**~~ | ✅ 完成 2026-04-26 | Python↔Rust parity test（decision agree ≥95%）— **W2 完成（commit c1142d2）**：`tests/test_executor_decision_parity.py` 311 行 + `executor_parity_cases.yaml` 661 行 70 case (30 golden + 40 synthetic_handcrafted)；Linux pytest 5 passed / 2 skipped (G3-08 deferred)，agree=70/70 (100%)。E1 push back: PA 提的 3 decision points 中只 shadow_mode runtime wired (per_symbol_cap + max_pct G3-08 future work)，TestExecutorDecisionParityDeferred skip marker 標 gap。E2 揭發 synthetic_replay 命名誤導 → rename synthetic_handcrafted。 | G3-03 ✅ | QA+E4 / E2 | 完成 2026-04-26 |
| **G8-03** | 🟠P1 deferred | 灰度驗收自動化（shadow metrics）— EDGE-P2 flip 後派；staged rollout vs simple flip / shadow metrics（agree_rate / decision_lag / pnl_diff） | EDGE-P2-flip 觸發後 | QA / E2 | 2-3d (post-EDGE-P2 flip) |
| ~~**G8-04**~~ | ⬇降 backlog | ~~healthcheck DAG 線性化~~ — **PA 2026-04-26 降級**：17 check 平鋪可讀、無假 PASS 觸發；待 false PASS/FAIL 真出問題再啟 | — | QA | — |
| **G8-05** | 🟡P2 | AI cost ROI 監控面板（from AI-E） | G3-09 | AI-E+E1a / QA | 1-2d |

### Wave 3 完成標準（**派發層面 5/5 ✅，被動等待自然解鎖**）

- [x] **bb_breakout PA RFC 結論 + 落地** — ✅ G2-06 disable deployed（PA RFC 選 C 永久 disable，三環境 TOML active=false + [12] disabled-skip + [18] inventory）
- [x] **G8-02 Python↔Rust parity test** — ✅ 70 case agree=70/70 (100%)（W2 commit c1142d2）
- [x] **EDGE-P1b schema bind 工具鏈** — ✅ schema landed（calibrator + summary + IPC restore + healthcheck [14] per-strategy）等資料 ~05-10
- [x] **EDGE-P2-flip tooling** — ✅ tooling landed（dry-run + SOP shell + healthcheck [15] per-strategy + breakdown tool）等 EDGE-P1b 觸發
- [x] **G2-03 SL/TP Option B schema staging** — ✅ schema landed (StrategyOverride 4 pct + risk_checks helpers + 3 TOML + bind SOP)，等 G2-02 ~05-03 後 G2-03-FUP-CALLER-WIRE
- [x] **G2-02 counterfactual tool** — ✅ tool landed，等真實 1w post-G7-09 ~05-01~05-03
- [x] **G2-FUP-IPC-LEGACY-MS-FIX P1** — ✅ ipc_client.py:786 ms→s + 3 unit test PASS（W5 衍生 hotfix）
- [ ] **EDGE-P3 4 條件全滿** — sample count 已滿（[11] n=864/200），但 latest [11] 因 replay JSON age 17.2h 仍 WARN；等 fresh replay + 連續 PASS
- [ ] **G2-01 PostOnly 驗收** — passive ~05-07/08
- [ ] **G2-02 雙軌驗證** — passive ~05-01~05-03（理論值 + realized）

### Wave 3 派發完成記錄（5 波 6 commits · 2026-04-26）

| 波 | commit | 內容 | 狀態 |
|---|---|---|---|
| W1（派發起點）| c1142d2 | 4-agent audit (PA/MIT/QC/FA) + W2 PM 派發整合 + G2-02 counterfactual + G8-02 parity + TODO EDGE-P3 (c) bug 修 + G8-04 降 backlog | ✅ |
| W1.5（隔壁 session sync）| 8946e47 | grid_trading G7-09c Phase 2 reject_cooldown_ms（FIX-G7-09C-PHASE2-WIRE-1B3）+ 18-agent runtime memory 索引 | ✅ |
| W3 | 55801fe | G2-06 bb_breakout disable 4 子任務（TOML + healthcheck [12]/[18] + meta-doc + Rust comment）+ PA 3 RFC（EDGE-P1b/P2-flip/G2-03）+ E2/E4 review | ✅ |
| W4 | 60fdf74 | EDGE-P1b 4/4（calibrator + summary + IPC restore + healthcheck [14]）+ EDGE-P2-flip T1+T3（dry-run + SOP shell）+ G2-03 4/4（schema + risk_checks + TOML + bind SOP）+ E2/E4 review | ✅ |
| W5 | 9cfdd52 | EDGE-P2-flip T2（healthcheck [15] per-strategy + breakdown tool）+ G2-FUP-IPC-LEGACY-MS-FIX P1（ipc_client.py:786 ms→s）+ E2/E4 review | ✅ |
| Sign-off | df882ad | PM Wave 3 Final Sign-off + CLAUDE.md §十一 update + rebuild 部署成功記錄 | ✅ |

### Rebuild 部署驗證（2026-04-26 04:29 CEST）
- engine PID 2033577（restart_all --rebuild 完成；含 Wave 1+2+3 全工 + grid G7-09c Phase 2 + G2-06 disable + EDGE-P1b IPC + G2-03 schema + risk_checks helpers）
- uvicorn PID 2033662（4 workers）
- engine lib **2161 / 0 fail**（baseline 1980 → +181 across waves）
- demo + paper 雙活，snapshot age 8.6s
- post-rebuild healthcheck **17 PASS / 1 WARN / 1 FAIL**：[12] disabled / [18] inventory / [14] per-strategy / [15] dormant / [13] edge_estimator 全綠；[11] 75% passive；[16] fresh-boot expected（6h cron 自然 PASS）

### 4-agent audit 報告索引：
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
| **P0-3-01** | 🔴P0 | counterfactual_exit_replay 完整分析報告 | Phase 2 result + G2 完成 + MLDE-1 dataset | MIT+PM / FA | 2d |
| **P0-3-02** | 🔴P0 | Edge 重評決策會（3 分支：翻正/仍負/部分改善） | P0-3-01 | PM+FA+PA+QC | 1d 會議 |

**outcome 分支**：
- A. edge 翻正 → cost_gate 重啟 + Track P Phase 1b 解凍 → LG-2~5 推進
- B. edge 仍負 → DUAL-TRACK 全力 + 策略重做 + 部分策略下架
- C. 結構性改善 → Phase 5 部分接線

**2026-04-29 reframe**：P0-3 仍是 live promotion / Phase 5 放權 gate，但不再阻塞 demo ML/Dream 訓練。負 edge demo 樣本可用於 veto/ranking/parameter repair；live 自動交易仍必須等 P0-3 + GovernanceHub contract。

### ML/Dream Edge Unblock（demo-first / live-governed）

| ID | Tag | 項目 | 前置 | 負責 | 工時 |
|---|---|---|---|---|---|
| ~~**MLDE-0**~~ | ✅完成 | GovernanceHub live-autonomy boundary documented/enforced：demo autonomy allowed; live auto-trading / live param auto-apply still requires GovernanceHub + Decision Lease + 5 live gates | Operator decision 2026-04-29 | ✅ | report `2026-04-29--mlde_demo_autonomous_applier.md` |
| ~~**MLDE-1**~~ | ✅完成 | Learning Data Contract landed and monitored by `[35]`; latest `[35]` PASS (7d MLDE rows 2464, linucb_ready 281) | STRATEGY-EDGE-REPAIR `ece31b6` | ✅ | `[35]` |
| ~~**MLDE-2**~~ | ✅完成 | LinUCB intent-arm/reward loop landed for demo/read-only; richer `mlde_arm_id` available for shadow analysis, active Rust arm-space migration deferred separately | MLDE-1 | ✅ | report `2026-04-29--ml_dream_edge_unblock_completion.md` |
| ~~**MLDE-3**~~ | ✅完成 | ML shadow advisor/scorer advisory path landed; latest `[36]` PASS (24h advisory rows 525, live_applied_without_lease=0) | MLDE-1 | ✅ | `[36]` |
| ~~**MLDE-4**~~ | ✅完成 | DreamEngine + OpportunityTracker read-only producers integrated with CognitiveModulator; demo/read-only edge repair producers active | MLDE-1 | ✅ | report `2026-04-29--ml_dream_edge_unblock_completion.md` |
| ~~**MLDE-5**~~ | ✅完成 | Demo A/B bounded applier landed with audit rows; latest `[37]` PASS (24h rows 172, demo_applied 18, failed 0, live_applied_without_lease=0) | MLDE-2 + MLDE-3/4 | ✅ | `[37]` |
| **MLDE-6** | 🟡live-governed boundary | Live promotion contract remains a governance gate, not an implementation blocker: advisory → operator-review proposal → demo patch → live candidate; live candidate still requires GovernanceHub approval + lease + rollback | P0-3 + operator approval | PM+CC+E3+PA / E2+QA | condition-triggered |

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
| ~~**G9-01**~~ | ✅ 完成 2026-04-26 | Bybit API 字典 confirm-mmr 路徑修正 + SSOT 標記 — commit `0cda2d9`（PM 代 commit；TW + Rust grep 雙驗 `position_manager.rs:307-335` 已是 confirm-pending-mmr，純字典 drift fix）| — | TW (PM proxy) | 完成 |
| ~~**G9-02**~~ | ✅ 完成 2026-04-26 commit `6990668` | WS unknown-handler force reconnect — 新 sibling `ws_unknown_handler_guard.rs` 483 行 + 10 unit tests；DEFAULT-OFF env-gate `OPENCLAW_WS_FORCE_RECONNECT_ON_UNKNOWN_ENABLED=1`；閾值 60s 滑窗 unique≥3 OR total≥5 → trigger；metrics `unknown_handler_total` + `forced_reconnect_total`；Auth phase 不啟（防風暴）；engine lib 2166→**2176/0**；E2 ACCEPT 4 + 1 ACCEPT-with-FOLLOWUP（**MED-1: ws_client.rs 1136→1227 過 §九 1200 hard cap 27 行 → 開 G9-02-FUP-WS-CLIENT-SPLIT**）+ 1 OPEN-FOLLOW-UP（cooldown 監控 1-2 週後決定）| 無 | BB+E1 / E2 | 完成 2026-04-26 |
| ~~**G9-03**~~ | ✅ 完成 2026-04-26 | `bybit_public_connectivity_check.py` 環境變數化 — commit `405c05b`（OPENCLAW_BYBIT_PUBLIC_BASE_URL env var fallback default 保留；Linux 真網路三 env 驗證 mainnet/testnet/demo lastPrice 各異 PASS）| — | E1 | 完成 |
| ~~**G9-04**~~ | ✅ 完成 2026-04-26 commit `c7d7179` | smoke_test 選項 B 刪除 v1（-164 lines）— v1 完全孤立 0 caller（grep 雙端驗證）+ Rust `bybit_private_ws_status_writer.rs` 已取代 observer 面向價值 (WS-RETIRE-1)；揭發 v2 + dead caller `bybit_ws_smoke_to_postgres.py` + `bybit_full_readonly_observer_cycle.py` 9 dead path（**cron 5min silent fail 3 天被 noise wrapper 吞**）→ 開 OBSERVER-PIPELINE-POST-F42FACE-CLEANUP P2 ticket | 無 | E1 | 完成 2026-04-26 |
| ~~**G9-05**~~ | ✅ 驗證型完成 2026-04-26 | L-2~5 字典補錄 PUSH-BACK — TW 確認字典手冊章節編號 §1.X（無 L-2~L-5）+ 盡責盤點 §1.2~§1.5 真實**無 drift**；發現 `set_trading_stop` 9 vs Bybit V5 真實 16+ fields 是 simplified subset 非 drift；E2 CLOSE-PASS（BB 不需 re-audit）| 無 | TW | 驗證完成（no drift found）|

### Wave 4 完成標準 → LIVE

- [ ] P0-3 決策產生具體執行路徑（A/B/C 三選一）
- [ ] LG-2/3/4/5 全綠
- [ ] 5 項硬邊界全綠 → operator 簽 `authorization.json` → Live 開啟

---

## 🔄 背景線程（獨立於 Wave，持續運行）

這些**不阻塞主路徑**，跟著 Wave 並行進行。每項都有對應 healthcheck 6h cron 監控。

| 項目 | 類型 | 起算/結束 | 狀態 | Healthcheck | 若 FAIL |
|---|---|---|---|---|---|
| **P0-2** 21d demo 時鐘 | 時間被動 | 2026-04-16 → 2026-05-07 | 🟡 進行中；2026-04-30 watchdog demo/live fresh | Linux watchdog + [1] close_fills_24h + [22] trading_pipeline_silent_gap | 真 dead/stale 才重評時鐘 |
| **P1-10** PostOnly 1-2w 驗證（=G2-01）| 資料被動 | 2026-04-21 → 05-07/08 | 🟡 累積中；2026-04-30 23:11 [33] 7d fee_drop **20.8%** / maker_like **25.6%**，仍低於 ≥60% | [10] intents_writer_ratio + [33] maker_fill_rate（7d fee_bps mix + per-strategy slices；target fee_drop ≥60%） | 驗收失效→G2-04 決策 |
| **EDGE-DIAG** exit_features 累積（=EDGE-P1b）| 資料被動 | 2026-04-19 → 05-10 per-strategy ≥200 | 🟢 2026-04-30 23:11 [14] this_week=1623；grid **1030 [READY]** / ma **493 [READY]** / READY_frac=94% | [14] per-strategy tier | 延後 Phase 1b bind until remaining approval/gate criteria |
| **EDGE-P3** clean window ≥200 | 資料被動 | 2026-04-22 → fresh replay + 連 3d PASS | 🟢 sample count 已滿：latest [11] post-P013 n_rows **864/200 (432%)**；🟡 latest verdict 仍 WARN，原因是 replay JSON age **17.2h** | [11] counterfactual_clean_window_growth | 延後 Gate 1 fallback 到 fresh replay + PASS streak |
| **G2-02** ma_crossover 1w post-G7-09 demo | 資料被動 | 2026-04-25 → 05-03 | 🟡 tool ready；等 2026-05-03 左右真實 1w post-G7-09 data | trading.fills 過去 1w fee_bps mix maker/taker | tool ready 等資料 |
| **G2-03 binding** 等 G2-02 → G2-03-FUP-CALLER-WIRE | 條件被動 | G2-02 結論後 → ~05-03 | ⬜ | (G2-02 完成觸發) | schema-only staging 持續 |
| **EDGE-P2-flip** 等 EDGE-P1b → operator manual flip | 條件被動 | EDGE-P1b 完成後 ~05-10+ | ⬜ | [15] shadow_exit_agreement_phase2 | tooling ready 等觸發 |
| **P1-7 C** labels pooled ≥200 | 資料被動 | 持續累積 | 🟢 2026-04-30 [14] grid **1030 [READY]** / ma **493 [READY]**；pooled label/data gate no longer the active blocker | [10] intents_writer_ratio + [14] per-strategy | G4-02 已完成；future gating is promotion/readiness, not pooled row count |
| **GRID-LIFECYCLE-DRIFT** grid_trading lifecycle 漂移觀察 | 資料被動 | 2026-04-29 → 05-06（7d）| 🔴 **confirmed real signal**（2026-04-29 W1-T2 後最新：demo n=40 p50=4.8min fee_burn=0.24 re_entry=0.41；live_demo n=98 p50=1.7min fee_burn=0.45 re_entry=0.72）| [38] grid_trading_lifecycle_drift（lifetime ratio < 0.5x WARN / < 0.3x FAIL；fee burn > 0.8 abs WARN / > 1.5 FAIL；same-symbol re-entry > 0.5 WARN / > 0.7 FAIL）| **RFC ready**：PA `2026-04-29--grid_risk_policy_rfc.md` 推薦 copy demo robust-negative `blocked_symbols` 到 live + `grid_levels 10→7`；不建議第一波動 trailing（非主 close reason）/ partial TP（目前無 runtime consumer）|
| ~~**STRATEGY-NAME-ATTRIBUTION-W1-T2** producer-side 16 close-path emit points~~ | 完成 | Completed by `5895579` + hotfix `854cae1`; close helper / confirmed fill / external command fill now write normalized `strategy_name` + `exit_reason` | ✅ latest [39] PASS（1h distinct=2-3，24h distinct=8） | [39] strategy_name_cardinality_drift | 舊 stalled-subagent row 歸檔；若 cardinality 再 drift 由 [39] 重新觸發 |

**規則（CLAUDE.md §七）**：任何背景項連續 3 次 healthcheck FAIL = 中止被動等待，轉人工介入。

**Wave 3 被動解鎖時刻表**（事件驅動，per FA H2 audit 文案釐清）：
- **2026-04-30 🟡**: EDGE-P3 [11] sample count **864/200 (432%)**，但 latest verdict WARN（replay JSON age 17.2h）；Gate 1 fallback 部署仍等 fresh replay artifact + PASS streak
- ~05-03: G2-02 真實 1w post-G7-09 demo 數據 → counterfactual 雙軌驗證 → **觸發 G2-03-FUP-CALLER-WIRE 派發**（解鎖 G2-03 真實 binding）
- ~05-07/08: P0-2 21d 解鎖 + G2-01 PostOnly 1-2w 驗收 → 若 fee drop ≥60% 通過，否則 G2-04 disable 決策會
- ~05-10: EDGE-P1b per-strategy ≥200 rows → calibrator manual approve flow 派發（**含 EDGE-P1b-FUP-STALE-PEAK-IPC 必先閉合**才能純 IPC bind dim 5）
- ~05-15: P0-3 邊評決策會（PM + FA + PA + QC）→ Phase 5 重啟 / 部分接線 / DUAL-TRACK 全力 三選一
- ~05-22~05-30: LG-2/3/4/5 + Live gate check
- **~2026-05-30 中位 ±7d**: Live target（PM W2 sign-off 不變）

---

## 📦 Backlog（條件觸發，非當前 Wave）

| # | 項目 | 觸發條件 | Tag | 備註 |
|---|---|---|---|---|
| **STRATEGIST-AUTO-PROMOTE** | 自動晉升規則 | P2-01 穩定後 | 🟡P3 | 默認關，可選 |
| ~~**G2-FUP-FUNDING-ARB-PAPER-SYNC**~~ | ✅ 完成 2026-04-26 commit `df1d629` | paper TOML active=true→false + 雙語 G2-FUP comment block；三環境 grep 驗 demo/live/paper 全 active=false | 完成 2026-04-26 | ✅ |
| ~~**G2-FUP-IPC-LEGACY-MS-FIX**~~ | ✅完成 W5 commit `9cfdd52` | `app/ipc_client.py:786` ms→s + 3 unit test PASS Linux verified | 完成 2026-04-26 | ✅ |
| ~~**EDGE-P1b-FUP-STALE-PEAK-IPC**~~ | ✅ 完成 2026-04-26 commit `c2ca032` | exit_stale_peak_ms 第 8 維加入 IPC schema（鏡射既有 7 個 exit_* pattern）+ deep-merge regression test；cargo 2161→2162 + pytest 130/0；shadow_enabled 仍 TOML-only（單獨 P3 ticket）；PM apply staging→in-place 代 commit | 完成 2026-04-26 | ✅ |
| ~~**G5-FUP-IPC-MOD-SPLIT**~~ | ✅ 完成 2026-04-26 commit `bd5ce56` | mod.rs 1251→138 行（89% reduction）+ 6 sibling（connection 251 / dispatch 572 / engine_routing 143 / protocol 105 / server 291 / slots 90）全 <800；hot-path patch_risk_config + EDGE-P1b 8 exit_* + HMAC verify_ipc_token byte-identical；4 verify_ipc_token unit tests +；Mac+Linux 2166/0 | 完成 2026-04-26 | ✅ |
| ~~**G1-FUP-CALIBRATOR-WARNING**~~ | ✅ 完成 2026-04-26 commit `92ea90b` + fixup `f633a5a` | banner stderr print + 4 雙語 reference comment 替代（commit `c2ca032` close ticket 後 banner stale，E2 batch review RETURN，fixup option A 完全移除 banner）| 完成 2026-04-26 | ✅ |
| **G2-03-FUP-CALLER-WIRE** | G2-03 `check_position_on_tick_with_override` 0 production caller（W4 軌 3 staging marker）；G2-02 counterfactual 結論定後派 E1 wire caller chain（step_6_risk_checks）真實啟用 SL/TP override | G2-02 完成 ~05-03 | 🟠P1 | E1 1d 工時；G2-03 schema 已 staging |
| **EDGE-P2 Phase B** | Liquidation signal | Phase A OI 驗收後 | 🟡P3 | OI 2026-04-20 已完 |
| **EDGE-P2-3 Phase 2+** | live endpoint / funding_arb PostOnly | Phase 1b | 🟡P3 | ML integration 前置 |
| **Phase 5 補強** | Superseded by MLDE-3/4：ML shadow scorer + Dream read-only edge repair。P0-3 只作 promotion gate，不阻塞 demo 訓練 | MLDE-1 起跑 | 🟠P1 | 併入 ML-DREAM-EDGE-UNBLOCK |
| **G-2 FundingArb 重評** | 三參數重評 | R-02 Strategist 在線 | 🟡P3 | G-1 AI Agent 推進後 |
| **ORPHAN-ADOPT-1 Phase 2B** | Strategist `would_take` 終仲裁 | G-1 R-02 | 🟡P3 | |
| **IP-DEDUP-1** | IntentProcessor 去抖 | P0-3 後 edge 仍負 + 高重發率 | ⚫P4 | 條件觸發 |
| ~~**4-06 / MLDE-2**~~ | ✅ Demo/read-only LinUCB intent-arm/reward loop landed under MLDE-2; later live warm-start / active arm-space migration remains condition-triggered after P0-3 + governance approval | MLDE-1 | ✅ | see MLDE section |
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
| ~~**G5-08 PA design**~~ | ✅ 2026-04-26 commit `2063386` + memory `dbd4c2f` | strategist_scheduler/mod.rs 1770→Method A 4-sibling design plan（cycle_counters 250 / validation 220 / evaluate 370 / tests 250 + persist 446 不動 + mod.rs ~280）+ E1 prompt template；E1 工時估 5-6.5h 全鏈 | 完成 2026-04-26 | ✅ |
| ~~**G5-09 tick_pipeline tests split**~~ | ✅ 2026-04-26 commits `a5b6f17` + `35b9d5f` | tick_pipeline/tests.rs 3524→11 sibling + mod.rs aggregator（max maker_kpi_hot_reload 652 < §九 800 警告）；126 tests 全 PASS（90 拆分 + 36 inline）；0 production touched；Linux release 2162/0 | 完成 2026-04-26 | ✅ |
| ~~**G5-FUP-PASSIVE-HEALTH split**~~ | ✅ 2026-04-26 commit `cc4c2d2` | passive_wait_healthcheck.py 2294→9 modules Python package（max checks_strategy 1048 < §九 1200；shim 36 行保 cron path）；19 check cron PASS；SQL invariance 100%（29 SQL call sites pre/post 一致）| 完成 2026-04-26 | ✅ |
| ~~**G5-08 E1 implementation**~~ | ✅ 完成 2026-04-29（本輪 maintenance cleanup，no rebuild） | `strategist_scheduler/mod.rs` 1819→426；新增 `cycle_counters.rs` 119 / `evaluate.rs` 428 / `tests.rs` 881，`persist.rs` 437 保留；`PairMetrics` / `CycleCounters` / `load_latest_applied_params` re-export 保持外部路徑；targeted `cargo test -p openclaw_engine --lib strategist_scheduler` 32/0。 | 完成 | ✅ |
| ~~**EXIT-FEATURES-WRITER-BUG-1**~~ | ✅ 已由 `EXIT-FEATURES-WRITER-BUG-1-FIX` 關閉；2026-04-29 healthcheck `[3] exit_features_writer` PASS（exit_features_24h=105 vs close_fills=105）。此舊「立即可派」描述保留作 RCA 指針，不再作 active work。 | 完成 2026-04-26 | ✅ | fix commits `af48ee1` + `83456e5` + `00a9679` |
| **G2-FUP-FUNDING-ARB-PAPER-SYNC-LOW-1** (TW memory) | E2 batch review 揭發：TW memory.md 與 commit msg 不一致（次要） | 下次 TW 接手 | 🟢P3 | TW 5min |
| ~~**EDGE-P1b-FUP-NEGATIVE-GUARD**~~ | ✅ 完成 2026-04-26 commit `d8385e6` | `ipc_client.py update_risk_config` 加 `exit_stale_peak_ms` negative-value guard + 6 unit tests; Tier 6 Track 1 quick-win batch | 完成 2026-04-26 | ✅ |
| **G5-09-FUP-TYPO** | E2 batch review 揭發：commit `a5b6f17` commit msg test count 自身 typo（0 production 影響） | 下次 commit msg edit cycle | 🟢P3 | 5min |
| ~~**AGENT-HEARTBEAT-SCOUT-WIRE**~~ | ✅ 完成 2026-04-30 commit `f8a245c`：`strategy_wiring_scanner._scan_and_produce_intel()` 在 no-opportunity 與 successful intel 兩條 completed scan path 都呼叫 `ScoutAgent.record_scan()`，讓 production ScoutWorker 30-min cycle 刷新 `_last_heartbeat_ms` / `scans_completed` / h_state invalidation。新增 `test_strategy_wiring_scanner.py` 2 個 hermetic tests（fake MarketScanner / ScoutWorker / ScoutAgent，無 thread / 無 exchange）。驗證：new pytest 2/0、`test_agent_heartbeat_contract.py` 36/0、targeted `py_compile` PASS；Linux API-only reload applied（uvicorn PID `1591455`，engine PID `1529433` unchanged）。報告 `docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-30--dust_edge_scout_followthrough.md`。 | 完成 | ✅ | n/a |
| ~~**CHECKS-STRATEGY-SUBSPLIT**~~ | ✅ 完成 2026-04-29（本輪 maintenance cleanup，no rebuild） | `passive_wait_healthcheck/checks_strategy.py` 1239→924；新增 `checks_strategy_breakout.py` 165 + `checks_strategy_counterfactual.py` 188；`checks_strategy` 保留 re-export，runner / package import path 不變；targeted `py_compile` PASS。 | 完成 | ✅ |
| ~~**CHECKS-ENGINE-SUBSPLIT**~~ | ✅ 完成 2026-04-29（本輪 hard-cap 小項，no rebuild） | `passive_wait_healthcheck/checks_engine.py` 1206→1143；新增 `checks_engine_reconciler.py` 78 承接 `[29] check_reconciler_paper_state_divergence`；`checks_engine` 保留 re-export，runner / package import path 不變；targeted `py_compile` + re-export smoke PASS。 | 完成 | ✅ |
| ~~**VERIFY-IPC-TOKEN-EMPTY-SECRET**~~ | ✅ 完成 2026-04-29 | `verify_ipc_token` 對 empty secret fail-closed，並補 matching-empty-secret token regression test；targeted cargo `verify_ipc_token` 5/0。 | SEC-08 maintenance | ✅ |
| ~~**G3-08-PHASE-1C-WIRING**~~ | ✅ 完成 2026-04-26 commits `5943337` + `deee78e` | strategy_wiring.py condition spawn `_H_STATE_INVALIDATOR` (+82) + CLAUDE.md §九 +2 rows + 新 healthcheck `[20] check_h_state_gateway_freshness` 3-state verdict (env=0 PASS-skip / env=1 verify 3 invariants); G3-08 Phase 1 全完 (A+B+C); Mac+Linux 雙端綠 (35/35 pytest no regression); E2 PASS-with-LOW (FUP: [20] expected sync) | Phase 1A+B ✅ | 完成 2026-04-26 | ✅ |
| ~~**G3-08-PHASE-2-H1-H3**~~ | ✅ 完成 2026-04-26 commits `9120948` + `f2ed286` | h1_thought_gate.py +149 (get_h1_snapshot + invalidate_async hook fire-and-forget) + model_router.py +169 (get_h3_snapshot + invalidate per-branch) + h_state_query_handler.py 改寫 (schema v0→v1 真實 H1+H3 stats); 新 +61 pytest tests (35→96/0); Strategist regression 69/69; Smoke env=0 empty + env=1 real 雙路徑驗證 PASS; E2 PASS-with-MEDIUM (T5.3-MED-1 H3 schema mismatch + MED-2 私有屬性穿透; runtime impact=0; 4 follow-up tickets) | G3-08 Phase 1A+B+C ✅ | 完成 2026-04-26 | ✅ |
| ~~**G3-08-PHASE-3-H2-H4-H5 PA sub-task split**~~ | ✅ 完成 2026-04-26 commit `c6ed0b3` (PA Track 3) | Pattern B 推薦 3 sub-tasks (3-1 H2 並行 / 3-2 H4 並行 / 3-3 H5 串行)；ETA 3.5d wall-clock；3 self-contained E1 prompt templates ready-to-deploy；H4 silent gap + file overlap + strategist_agent §九 預警 全 E2 verified | G3-08-PHASE-2-H1-H3 ✅ | 完成 2026-04-26 | ✅ |
| ~~**G3-08-PHASE-3-SUB-TASK-3-1 H2 budget integration**~~ | ✅ 完成 2026-04-26 commit `8cd257e` + memory `cf39415` (Tier 8 Track 1) | 4 Python files; pytest +12; get_h2_snapshot 3 fields 對齊 Rust H2BudgetState; multi-track absorb pattern (吸收 Track 2 in-flight H4 edits to shared h_state_query_handler.py) | 完成 2026-04-26 | ✅ |
| ~~**G3-08-PHASE-3-SUB-TASK-3-2 H4 validator integration**~~ | ✅ 完成 2026-04-26 commit `71faf4c` (Tier 8 Track 2) | 2 Python files (strategist_agent + test); pytest +13; H4 silent gap fix (validation_pass counter 0→13 hits); **strategist_agent.py 1200/1200 §九 hard cap exact-touch** → 開 G3-08-PHASE-4-STRATEGIST-SPLIT P1 backlog | 完成 2026-04-26 | ✅ |
| ~~**G3-08-PHASE-3-SUB-TASK-3-3 H5 cost_logging integration**~~ | ✅ 完成 2026-04-26 commit `d1a2252` (Tier 8 Track 4) | 5 files; pytest +15; **Phase 3 COMPLETE** (5 H buckets 全 wired); **G3-09 cost_edge_ratio 解阻** (Rust DashMap lookup ≤1ms p99); layer2_cost_tracker.py 930 LOC §七 800 警告區 +130 → 開 G3-08-PHASE-4-COST-TRACKER-SPLIT LOW backlog | 完成 2026-04-26 | ✅ |
| ~~**G3-08-PHASE-4-STRATEGIST-SPLIT (PA design)**~~ | ✅ 完成 2026-04-26 commit `de699df` (Tier 9 Track 1) | PA RFC Method A 3 NEW sibling: edge_eval ~280 + weights ~140 + cognitive ~110 + 主檔 ~710；2 self-contained E1 prompt templates ready (Part A + Part B) | 完成 2026-04-26 | ✅ |
| ~~**G3-08-PHASE-4-STRATEGIST-SPLIT impl**~~ | ✅ 完成 2026-04-27 commit `6fac0ca` (E1 worktree) → merged `afce487` | strategist_agent.py 1200 → 792 LOC + 3 NEW sibling (edge_eval 369 / weights 224 / cognitive 169); 16 BWD-compat 1-line delegators + 4 noqa F401 re-export blocks; E2 PASS_WITH_NITS (0 CRITICAL/HIGH/MED, 2 NIT) / E4 PASS Mac 126/0 + Linux 2252/0 兩遍 non-flaky | 完成 2026-04-27 | ✅ |
| ~~**G3-08-PHASE-4-COST-TRACKER-SPLIT (PA design)**~~ | ✅ 完成 2026-04-26 commit `de699df` (Tier 9 Track 1 same RFC) | PA RFC Method A 3 NEW sibling: cost_recording ~210 + adaptive ~120 + h_state_snapshots ~150 + 主檔 ~480；2 self-contained E1 prompt templates ready | 完成 2026-04-26 | ✅ |
| ~~**G3-08-PHASE-4-COST-TRACKER-SPLIT impl**~~ | ✅ 完成 2026-04-27 commit `73c1f3d` (E1 worktree) → merged `c077e8c` | layer2_cost_tracker.py 930 → 540 LOC + 3 NEW sibling (cost_recording 405 / adaptive 207 / h_state_snapshots 190); 14 delegators + 4 test patch site upgrade; E2 PASS_WITH_NITS (3 NIT cosmetic) / E4 PASS Mac 196/0 + Linux 2252/0; LOC drift +382 investigated and confirmed 0 padding (RFC formula 漏估雙語 docstring); 解阻 G3-09 Phase A | 完成 2026-04-27 | ✅ |
| ~~**G3-08-PHASE-4-STRATEGIST-SPLIT-FUP-FACADE**~~ | ✅ 完成 2026-04-29（本輪 maintenance cleanup，no rebuild） | `StrategistAgent.get_h1_snapshot()` / `get_h3_snapshot()` public facade added；`h_state_collectors.py` 改走 `_safe_snapshot_self(strategist, "...")`，不再讀 `_h1_gate` / `_model_router` private attr；`test_h_state_query_handler` fixture 同步；Python unittest 116/0。 | 完成 | ✅ |
| ~~**G3-08-PHASE-4-5AGENT**~~ | ✅ **PHASE 4 COMPLETE** 2026-04-27 commits `c8a4a55` (4-1 Strategist) → `8144b51` merge (4-2 Guardian) → `1d55c99` (4-3 Analyst) → `64fae22` (4-4 Executor) → `b67b0a8` (4-5 Scout) | PA RFC `340c78b` 1415 LOC design + 5 self-contained E1 prompt templates；ALL 5 sub-task E1+E2+E4 全鏈 PASS；env=1 + `/api/v1/h_state/full` 回 **10-bucket envelope** (5 H {h1,h2,h3,h4,h5} + 5 Agent {strategist 11/guardian 8/analyst 5/executor 9/scout 5})；Linux post-merge cargo lib **2290/0** + pytest **289/0**；Wave I-b G3-09 Phase A 並行落地 (commit `00682ef`)；解阻 G8-01 認知自適應 e2e + G3-09 Phase B/C；FUP backlog 8 tickets filed (詳下) | 完成 2026-04-27 | ✅ |
| ~~**G3-09-PHASE-A-SCHEMA impl**~~ | ✅ 完成 2026-04-27 commit `00682ef` | cost_edge_advisor module ~1338 LOC Rust (mod/types/advisor/tests + IPC handler) + 21 modified Rust + 3 TOML [cost_edge] + 3 Python healthcheck [30]; PM Tier 9 T9-LOW-1 threshold = -0.5 lock-in (per RFC §2.4 變體 A); env-gate dual safeguard (OPENCLAW_COST_EDGE_ADVISOR=1 + RiskConfig.cost_edge.enabled=true); cargo lib 2252 → **2290 / 0 failed** (+38 tests); E2 PASS (0 finding any level) / E4 PASS Mac 2290/0 兩遍 + Linux baseline; 0 trade impact (advisory only); 解阻 G3-09 Phase B/C | 完成 2026-04-27 | ✅ |
| ~~**G3-08-FUP-MAF-SPLIT**~~ | ✅ 完成 2026-04-27 commits `b8b5150` (impl) + `d190acb` (docs) | multi_agent_framework.py 1190 → **966** (hard cap 1200 餘裕 10→234) + scout_agent.py NEW 297；**PEP 562 lazy re-export** 解循環 import（PA RFC §3 eager 原方案撞 cycle，E1 §5.1 解釋偏離）；0 strategy_wiring / 0 test 改；6 套 286 pytest 全綠；E2 PASS_WITH_NITS（2 LOW NIT + 2 INFO → G3-08-FUP-MAF-SPLIT-CLEANUP P3）；Linux post-merge 2290/0 不變 | 完成 2026-04-27 | ✅ |
| ~~**G3-09-PHASE-A-DAEMON-INTEGRATION-TEST**~~ | ✅ 完成 2026-04-27 commit `af66ac1`（升 P3→P1 prereq 後完成） | `tests/test_cost_edge_advisor_daemon.rs` NEW 593 LOC / 6 cases / 5 proofs (daemon spawn → Ok / Trigger 轉換 / env-gate strict "1" / RiskConfig dual safeguard / 100ms cadence ≤10% mean error / cancel drain <1s)；Mac --release 2.09s 三遍非 flaky；Linux 6/0；0 production diff；Phase B Wave 0 prereq 達成；E2 PASS（2 INFO → G3-09-PHASE-B-FUP-STICKY-TS P2 + G3-09-PHASE-B-FUP-SPAWN-TEST P3） | 完成 2026-04-27 | ✅ |
| ~~**G8-01 W1 (CognitiveModulator dead-path fix)**~~ | ✅ 完成 2026-04-27 commit `aca7ee3` | PA RFC `2026-04-27--g8_01_cognitive_e2e_design.md` 揪 2 BLOCKER bug：BUG-A `get_current_params()` method 不存在 (try/except 靜默吞 → 永遠 default)；BUG-B `modulator.update(...)` production 0 caller (`update_count` permanent 0)；W1 修：method rename 2 處 (`strategist_cognitive.py:160` + `strategist_edge_eval.py:191`) + `_handle_intel` 每 N=10 intel 呼 `tick_cognitive_modulator(self)` (unconditional pre-return)；6 new sanity tests + 171 strategist regression 全綠；E2 PASS to E4（0 CRITICAL/HIGH/MED, 2 LOW）；W2 ≥85% cov + W3 integration ≥5 case PA RFC deferred → 開新 ticket | 完成 2026-04-27 | ✅ W1 |
| ~~**G8-01 W2 — CognitiveModulator ≥85% line cov**~~ | ✅ 完成/核驗 2026-04-29 | 既有 `test_cognitive_modulator_coverage.py` 已落地 26 unit cases（PA RFC §3.2 原 22 case 擴充）；本輪 targeted pytest `26 passed`。本機缺 `pytest-cov`/`coverage.py`，未重新產 coverage report；既有 Wave B sign-off 記錄 W2 100% cov。 | W1 ✅ | ✅ |
| ~~**G8-01 W3 — StrategistAgent integration ≥5 case**~~ | ✅ 完成/核驗 2026-04-29 | 既有 `test_strategist_cognitive_integration.py` 已落地 8 integration scenarios（超過 min 5）；本輪連同 LOSSES-WIRING targeted pytest `42 passed`。 | W1 ✅ | ✅ |
| ~~**G8-01-FUP-LOSSES-WIRING**~~ | ✅ 完成 2026-04-28 commit `aced662` | Hybrid Option 1（in-process callback）：Analyst.set_strategist_loss_callback + invoke in analyze_trade fail-open；Strategist.record_trade_outcome(net_pnl) + 2 new stats key；strategy_wiring lambda 綁；breakeven `<= 0` per PM (align `feedback_micro_profit_fix_intent`)；3 檔 +194 LOC + 1 test ~330 LOC（8 cases）；Mac 86 + Linux 199 全綠；E2 PASS to E4（2 LOW: PA docstring nit / breakeven decision ratified）；3 PA-flagged 風險全清（lambda closure 安全 / breakeven 對稱 / Analyst→Strategist callback 在 lock 外 fire 0 ABBA）；regret/dream `{}` 待 G8-01-FUP-REGRET-DREAM-WIRING | 完成 2026-04-28 | ✅ |
| ~~**G3-09-PHASE-B-FUP-STICKY-TS**~~ | ✅ 完成 2026-04-28 commit `9303a3b` | **Design A** (daemon enforce sticky)：mod.rs daemon body 加 task-local `sticky_triggered_at_ms` + 4-arm match `(prev_status, new_state.status)` 在 `evaluate()` 後 `store_state()` 前；non-Trigger→Trigger 抓 `now_ms` / Trigger→Trigger 保留 / Trigger→非 Trigger 清零；mod.rs +49 / advisor.rs +8 / types.rs +5 production = +62 net + 174 test；Mac+Linux cargo lib **2290/0** 不變；daemon test 6→8（+2 sticky）；E2 PASS（0 finding：rustc exhaustive 4-arm + sticky/prev_status daemon task-local 0 race + evaluate() pure 不變）；Phase B Wave 1 `last_trigger_ms` rolling counter 可直接讀本欄 | 完成 2026-04-28 | ✅ |
| ~~**G3-09-PHASE-B-FUP-SPAWN-TEST**~~ | ✅ 完成 2026-04-28 commit `22c57dc` | 3 cases A/B/C（env unset → slot None+IPC Uninitialized / env=1+RiskConfig=false → slot Some+IPC Disabled / env=1+RiskConfig=true → slot Some+IPC live OK）；wrapper-reproduction pattern（spawn_cost_edge_advisor_if_enabled `pub(crate)` 不能直呼，wrapper 鏡 L457/495/526 + handler L33-44 with bilingual MODULE_NOTE line-anchor parity）；test file +357 LOC (593→1159)；0 production diff；Mac+Linux daemon test 6→11（+5 含 sticky）；E2 PASS to E4（2 LOW + 1 INFO：1159 LOC > 800 → split FUP / wrapper L500-522 H5 slot wait loop 未 cover → P3 / merge order sticky-first then spawn-test 已採） | 完成 2026-04-28 | ✅ |
| ~~**G3-08-FUP-MAF-SPLIT-CLEANUP**~~ | ✅ Recalibrated 2026-04-30 | Lazy PEP 562 re-export is the accepted design because Scout first-import still has partial-import risk; `scout_agent.py` bilingual note now states PEP 562 explicitly, and `SCOUT_AGENT` is registered in `CLAUDE.md` singleton table. No eager re-export action remains. | 完成/校準 | ✅ |
| ~~**G3-09-DAEMON-TEST-SPLIT**~~ | ✅ 完成 2026-04-30 | cost_edge_advisor daemon tests 已拆為 3 檔且全低於 §九 800 warning：`test_cost_edge_advisor_daemon_proofs.rs` 534 LOC / `test_cost_edge_advisor_daemon_dual_safeguard.rs` 380 LOC / `test_cost_edge_advisor_spawn_decision.rs` 479 LOC；本輪移除 proofs 檔殘留的 sticky/spawn-decision 重複段，對應 coverage 保留在專用檔。 | 完成 | ✅ |
| ~~**G3-09-FUP-CASE-D-H5-WAIT**~~ | ✅ 完成 2026-04-29（本輪 maintenance cleanup，no rebuild） | H5 cache-slot timeout warning text lifted to constant and covered by `h_state_timeout_warning_mentions_h5_dependency_and_no_spawn`；targeted `cargo test -p openclaw_engine --bin openclaw-engine h_state_timeout_warning_mentions_h5_dependency_and_no_spawn` 1/0。 | 完成 | ✅ |
| ~~**G8-01-FUP-REGRET-DREAM-WIRING**~~ | ✅ **ESCALATED → Option C deferred** 2026-04-28 PA report `docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-28--g8_01_fup_regret_dream_wiring.md` | PA grep 揭：**regret/dream concept 完全 dead**。歷史 `OpportunityTracker` (~262 LOC per V1.1+R1 SPEC §3) + `DreamEngine` (~315 LOC per §4) 兩個 producer 在 2026-04-12 RC-11 dead code 清理時刪除（1003 LOC removed, archive `2026-04-12--changelog_archive_pre_0408.md:575`）。`modulator.update()` 真實 signature 確認接 `regret_data: dict\|None=None` + `dream_data: dict\|None=None`（LOSSES-WIRING 假設正確）但 caller 永遠傳 None。6 candidate proxies (H4 missed-opp / Analyst trade outcome / H1 reject log / Scout explore / ML registry / epsilon-greedy) 全 fail semantic match。PA 推 Option C：defer + open new P3 ticket（避免破壞 V1.1 SPEC API + 不擴 scope）。0 production diff. **W2 ≥85% cov 影響**：regret/dream-only branches 屬 deferred-unreachable，W2 派發時需告知 cov 計算 exclude（或加 `# pragma: no cover`） | 完成 2026-04-28 | ✅ Escalated |
| **G8-01-FUP-REGRET-DREAM-DEFERRED** | 🟢P3 — 替代 P2 LOSSES-FUP，per PA Option C：未來重新實作 OpportunityTracker + DreamEngine（per existing V1.1+R1 SPEC `docs/references/2026-04-03--agent_cognitive_adaptation_spec_v1_draft.md` §3 + §4）需新 PA RFC（~3-5d 含 ~600 LOC 含 tests）；OR 接受 modulator 在 regret/dream 維度永遠 base value（ROI 評估）；OR 看 Rust roadmap R02-9 `core/dream.rs` `docs/rust_migration/02--core_upper.md:68` 是否優先 | 長期未定 | 🟢P3 | PA RFC + E1+E2+E4 ~3-5d (if pursued) |
| ~~**G3-09-PA-DOCSTRING-CLARIFY**~~ | ✅ 已完成/核驗 2026-04-29 | `strategy_wiring.py` lambda capture comment 已改為正確描述 Python free-variable lookup 會動態反映 global reassignment；本輪確認 TODO v3 舊狀態過期。 | LOSSES-WIRING doc maintenance | ✅ |
| ~~**G3-08-FUP-ANALYST-SPLIT**~~ | ✅ Closed by 2026-04-30 cleanup | `analyst_agent.py` is now **764** LOC (<800 warning line) after doc/note compaction; no sibling split needed. | 完成 | ✅ |
| ~~**G3-08-FUP-HSQ-SPLIT**~~ | ✅ Closed by 2026-04-30 cleanup | `h_state_query_handler.py` is **452** LOC; prior “approaching 900” row was stale. | 完成 | ✅ |
| ~~**G3-08-FUP-STRATEGIST-DELEGATOR-SLIM**~~ | ✅ Closed by 2026-04-30 cleanup | `strategist_agent.py` is now **797** LOC (<800 warning line). Delegator slimming is no longer a size-driven task; hook-placement LOW remains only an opportunistic micro-nit if the file is touched later. | 完成/校準 | ✅ |
| ~~**G3-08-FUP-EXECUTOR-EARLY-RETURN-LOW1**~~ | ✅ 完成 2026-04-29（本輪 maintenance cleanup，no rebuild） | Executor `_handle_approved_intent` early returns now fire h_state invalidation hints for empty / deduped / invalid payload; added 3 regression tests; Python unittest 116/0。 | 完成 | ✅ |
| ~~**G3-09-PHASE-A-PA-RFC-SLOT-UPDATE**~~ | ✅ 完成 2026-04-30 | PA RFC `2026-04-26--g3_09_cost_edge_ratio_design.md` §6.2 healthcheck slot 已同步為 [30]，並補明 [22] 已由 F7 `trading_pipeline_silent_gap` 占用。 | 完成 | ✅ |
| ~~**G3-09-PHASE-A-DAEMON-INTEGRATION-TEST**（duplicate placeholder）~~ | ✅ — 同條已升 P1 prereq + 完成於本 wave commit `af66ac1`（見上方 ✅ row） | — | — | ✅ |
| ~~**G1-04-FUP-FINAL-COMPUTE**~~ | ✅ as-of compute complete 2026-04-30 | Operator requested immediate compute before the nominal 05-01/02 full-week mark. Result: post-G7-09 full window is 5.94d and diluted by pre-reload samples (entry n=1933 / maker_like 26.28% / fee_drop 21.30%). More relevant post-2026-04-29 12:27 reload slice: entry n=665 / maker_like **73.23%** / avg_fee **3.424bps** / fee_drop **59.32%**; ma_crossover fee_drop 66.37%, grid 57.60%. R:R remains mixed: post-reload grid_close_short n=129 net +2.96 RR 1.454, grid_close_long n=43 net +0.33 RR 1.381, ma_reverse_cross n=104 net -4.79 RR 1.076, phys_lock n=37 RR 0.798. This closes the requested G1-04 compute artifact; G2-01 settlement still waits 2026-05-07/08. | 完成 | QC + FA + PM | report `2026-04-30--todo_followthrough_g1_g8_mlhygiene.md` | ✅ |
| ~~**G9-02-FUP-WS-CLIENT-SPLIT**~~ | ✅ 完成 2026-04-26 commit `eb65e1e` | ws_client.rs 1227→6 sibling (max maker_kpi_hot_reload 不存在; max sibling parsers 355) + mod.rs 142 < 300 理想線 + 71% peak reduction；hot-path 5 條全 byte-identical (WS-TIMEOUT FA-1 risk #2 / subscribe HashSet O(1)+10-batch+500ms / process_message ShouldReconnect / BackoffConfig 雙路徑 / ForceReconnect close-frame)；cargo lib 2176/0 不變；E2 PASS | E2 MED-1 → 立即可派 | 完成 2026-04-26 | ✅ |
| ~~**OBSERVER-PIPELINE-POST-F42FACE-CLEANUP**~~ | ✅ 完成 2026-04-26 commit `c53c3f9` | -228/+679 (9 files; 刪 v2 + dead caller `bybit_ws_smoke_to_postgres.py` + observer_cycle.py 9→8 path 修 + cron wrapper noise pattern 移除 + cron-time env var fix `export OPENCLAW_SRV_ROOT` + 新 healthcheck `[19] observer_pipeline_alive` 雙軸三態 + `OPENCLAW_OBSERVER_PIPELINE_OPTIONAL=1` opt-out)；**首次揭露 silent fail ok=1/5** (PM accept 真實狀態暴露)；E2 PASS-with-LOW (L-1 cosmetic BRIDGE_RC overshadow → TIER4-OBSERVER-LOW-1) | G9-04 揭發 | 完成 2026-04-26 | ✅ |
| ~~**G3-07-FUP-ENV-NAMESPACE**~~ | ✅ 完成 2026-04-30 | `layer2_tools_g3_07.bybit_public_base_url()` 對齊 production file-based env：`OPENCLAW_BYBIT_PUBLIC_BASE_URL` exact URL override → legacy/test `OPENCLAW_BYBIT_ENV` → `live/bybit_endpoint` file (`demo`→live_demo / `mainnet`→mainnet / `testnet`) → safe demo fallback；新增 env/url/file endpoint tests；targeted pytest PASS。 | 完成 | ✅ |
| ~~**G3-07-FUP-PYTEST-MARK**~~ | ✅ 完成 2026-04-26 commit `d8385e6` | `conftest.py pytest_configure` 註冊 slow + e2e markers + `TestCheckDerivativesE2E` 加 e2e decorator; Tier 6 Track 1 | 完成 2026-04-26 | ✅ |
| **G9-02-FUP-COOLDOWN** | E2 batch review OPEN-FOLLOW-UP: G9-02 force reconnect cooldown — 既有 `BackoffConfig` 3-60s 退避有基礎保護；DEFAULT-ON 後監控 1-2 週再決定是否加 cooldown | DEFAULT-ON 後 1-2 週 passive | 🟢LOW-PASSIVE | E1 1-2h（如需）|
| ~~**EXIT-FEATURES-WRITER-BUG-1-FIX**~~ | ✅ 完成 2026-04-26 commits `af48ee1` + `83456e5` + `00a9679` | RCA-A: `step_0_fast_track.rs:315-340` layered Gate 1 (USD floor 1.0 USD) + Gate 2 (ratio gate when entry_notional>0) + bootstrap `migrate_legacy_entry_notional` (idempotent) + new `RiskConfig.limits.ft_dust_qty_floor_usd` schema · RCA-B: `is_partial_reduce_tag()` exact-match helper (`risk_close:fast_track_reduce_half`) + `emit_close_fill` gate before EF emit (trading.fills 仍寫只 EF skip) · engine lib 2198→**2210/0** (+12) + integration 12/0 + 17 new tests · MIT §5 對齊 (A1+A3+B1') · healthcheck [3] 預期 ~2026-04-27 07:37 後自然 PASS (24h grace period for 歷史 37 noise label age out) · E2 PASS-with-LOW (FUP: helpers.rs 1315 §九) | MIT audit ✅ | 完成 2026-04-26 | ✅ |
| ~~**EXIT-FEATURES-FIX-FUP-HELPERS-RS-SPLIT**~~ | ✅ 完成 2026-04-30 | `tick_pipeline/on_tick/helpers.rs` 1411→336；PHYS-LOCK / shadow-exit wrapper tests 移至 sibling `helpers/phys_lock_wrapper_tests.rs` 1078 LOC；static guard allowlist 同步新測試檔；`cargo fmt --check` + `cargo test -p openclaw_engine --lib phys_lock_wrapper_tests` 22/0。 | 完成 | ✅ |
| ~~**G3-08-PHASE-1C-FUP-CHECK20-SYNC**~~ | ✅ 完成 2026-04-26 commit `d8385e6` | [20] healthcheck expected value 升 Phase 2（version=1 + h_states ⊇ {h1,h3}）+ set diff WARN 邏輯 Phase 3-4 friendly; Tier 6 Track 1 | 完成 2026-04-26 | ✅ |
| ~~**G3-08-PHASE-2-FUP-H3-SCHEMA-ALIGN PA design**~~ | ✅ 完成 2026-04-26 commit `306b549` | PA Track 2 A/B/C decision; recommend Option B (Rust rename + 加 fields 對齊 Python，5/5 評分 vs A 1/5 / C 3/5)；E1 impl 留 P1 backlog；Phase 3 unblock path: yes | 完成 2026-04-26 | ✅ |
| ~~**G3-08-PHASE-2-FUP-H3-SCHEMA-ALIGN E1 impl**~~ | ✅ 完成 2026-04-26 commit `4b30f5e` (Tier 7 Track 1) | Rust H3RouteStats rename 6 + add 3 fields per PA Option B; cargo lib 2210→2212; +2 schema parity tests; 10/10 key 對齊 (E2 grep verified); 0 production consumer; Python 0 改動; **Phase 3 unblock** | 完成 2026-04-26 | ✅ |
| ~~**T7-FUP-DUST-SQL-DEVIATION-DOC**~~ | ✅ 完成 2026-04-26 commit `79a808a` (Tier 8 Track 3) | RFC §7.4 amend + §13 Deviation Log added；E1 SQL deviation 兩項 documented as improvement (FILTER on COUNT DISTINCT + drop partial_reduce_real_count) | 完成 2026-04-26 | ✅ |
| ~~**T8-FUP-RFC-TYPO-FIX**~~ | ✅ 完成 2026-04-26 commit `642c34c` (Tier 9 Track 2 lumped) | RFC §7.2 line 338 "improvement not improved spec" → "improvement not regression" (1 word, 業務內容不變) | 完成 2026-04-26 | ✅ |
| ~~**G3-08-PHASE-2-FUP-PRIVATE-ATTR-FACADE**~~ | ✅ Closed 2026-04-29 by `G3-08-PHASE-4-STRATEGIST-SPLIT-FUP-FACADE` | E1 audit 原揭 2 H1+H3 private-attr violations；Strategist split 後本輪加 `StrategistAgent.get_h1_snapshot()` / `get_h3_snapshot()` facade，collector 改走 public self access。 | 完成 | ✅ |
| ~~**PAPER-STATE-DUST-RESTORE-AUDIT** → **PAPER-STATE-DUST-INVENTORY-MONITOR**~~ | ✅ 全鏈完成 2026-04-26 (PA design `dd4d64a` + E1 impl Tier 7 Track 2 commit `8241133`) | new healthcheck `[21] paper_state_dust_inventory` 三態 verdict per PA §7.4; 14 unit tests Mac+Linux green; **Linux cron 16:09 UTC LIVE PASS** `dust_spiral_count=0 — Gate 1 USD floor suppressing as designed`; supersedes MICRO-PROFIT-FIX-1-HEALTHCHECK | 全鏈完成 | ✅ | n/a |
| ~~**ML-TRAINING-DATA-HYGIENE-1**~~ | ✅ 完成 2026-04-30 | SQL 量化全期 `learning.exit_features` dust spiral noise：total rows=1843, noise rows=37, ratio **2.01%** (<5% 回填門檻), noise_24h=0, all historical noise confined to 2026-04-26 07:37-08:13 CEST `demo/orphan_frozen/STRKUSDT` after the EXIT-FEATURES fix grace window. Decision: no backfill migration needed; existing healthchecks `[26] dust_spiral_noise_in_ef` (total + 24h delta) and `[21] paper_state_dust_inventory` (runtime recurrence) already cover復發監控。 | 完成 | ✅ | report `2026-04-30--todo_followthrough_g1_g8_mlhygiene.md` |
| ~~**MICRO-PROFIT-FIX-1-HEALTHCHECK**~~ | ✅ Superseded by **PAPER-STATE-DUST-INVENTORY-MONITOR** (Tier 7 Track 2, 2026-04-26) — 新 `[21] paper_state_dust_inventory` SQL 更廣（`LIKE 'risk_close:fast_track%'` vs MIT exact `= 'risk_close:fast_track_reduce_half'`）+ 三態 PASS/WARN/FAIL verdict（vs MIT 二態 `> 5 → FAIL`）+ 加 `engine_mode IN ('demo','live','live_demo')` filter 排除 paper noise；MIT §6 #6 narrower spec 完全被涵蓋 | superseded | 🟢P3 | n/a |
| ~~**PAPER-STATE-DUST-INVENTORY-MONITOR**~~ | ✅ 完成 2026-04-26 (Tier 7 Track 2) | E1 落地 PA Track 3 §7.4 ready-to-deploy SQL 為新 healthcheck `[21] paper_state_dust_inventory`：純 SELECT FROM trading.fills，三態 verdict（PASS/WARN/FAIL），supersede MICRO-PROFIT-FIX-1-HEALTHCHECK；14/14 unit tests 綠（`helper_scripts/db/test_paper_state_dust_inventory.py`），Mac smoke argparse description 顯示 21 checks + `[21]` 在 cursor block list；cross-env safe by design (per PA §8) | PA Track 3 audit `dd4d64a` | 🟢P3 | 完成 2026-04-26 | ✅ |
| ~~**TIER4-OBSERVER-LOW-1**~~ | ✅ 完成 2026-04-26 commit `d8385e6` | aggregate-exit log 保留 OBSERVER_RC + BRIDGE_RC 完整對 (cron exit code 語意 byte-identical); Tier 6 Track 1 pivot | 完成 2026-04-26 | ✅ |
| ~~**T6-FUP-WARN-ZONE-FILES-SPLIT**~~ | ✅ 完成 2026-04-30 | `checks_derived.py` 990→444，抽出 `checks_derived_observer.py` 199 / `checks_derived_h_state.py` 274 / `checks_derived_ml_hygiene.py` 108；`ipc_client.py` 901→749，抽出 `ipc_client_sync.py` 128 + `ipc_client_risk_config.py` 57，保留原 import/re-export surface；targeted py_compile、IPC pytest 9/0、healthcheck unittest 39/0、re-export smoke PASS。 | 完成 | ✅ |
| **T6-FUP-PA-MEMORY-INDEX-SYNC** | E2 Tier 6 LOW: PA Track 3 dust audit (`dd4d64a`) memory.md 索引條目未追加；PA 下次 audit 接手時補 | 下次 PA 接手 | 🟢LOW | PA 10min |
| ~~**TIER4-AI-SERVICE-DISPATCH-SPLIT**~~ | ✅ 完成 2026-04-30 | `ai_service_dispatch.py` 868→727；Guardian L1 handler + parser 抽至 `ai_service_guardian.py` 169，`AIService._handle_guardian()` / `_parse_guardian_response()` 保留 thin delegator；targeted py_compile + `test_p1_audit_smoke.py` 11/0 + `test_h_state_query_handler.py` 90/0。 | 完成 | ✅ |
| **TIER4-MIT-AUDIT-GREP-SNIPPET** | E2 Tier 4 review LOW-3: MIT EXIT-FEATURES audit H1 reject 缺 grep snippet 證據（E2 已獨立驗證屬實，下次補完整 audit doc 嚴謹度） | 下次 audit | 🟢P3 | MIT 30min |
| ~~**STRK-FUP-LOOP-HANDLERS-SPLIT**~~ | ✅ 完成 2026-04-29（本輪 maintenance cleanup，no rebuild） | `event_consumer/loop_handlers.rs` 1481→1188；新增 `status_report.rs`（H0/status/checkpoint/scanner diff/kline bootstrap/dust reaper）+ `execution_fill_helpers.rs`（fill role/slippage helpers）；targeted `cargo test -p openclaw_engine --lib event_consumer` 154/0。 | 完成 | ✅ |
| ~~**STRK-FUP-MEMORY-CONFLICT-RESOLVED**~~ | ✅ 完成 2026-04-27（merge F6 + F7 兩處 docs/CCAgentWorkSpace/E1/memory.md union conflict 採 `git merge -X theirs` 自動 resolve；audit trail 完整保留） | 完成 | ✅ | n/a |
| ~~**STRK-FUP-BASELINE-UPDATE**~~ | ✅ 完成 2026-04-27（TODO L9-L10 + CLAUDE.md §十一 baseline 2161 → 2252 已更新，per PM Sign-off §5.3）| 完成 | ✅ | n/a |
| ~~**STRK-FUP-F7-CRON-CD-CHECK**~~ | ✅ 完成 2026-04-29 commits `030ef2d` + `0e9e257` + `f0d21b9` + `af9d552`：cron wrapper 先捕捉本次 healthcheck 輸出到 temp file，再 grep `[22]`-`[29]`；缺任一 ID 會寫 `[FAIL]` 並 exit 1。Linux 手動驗證 `bash helper_scripts/db/passive_wait_healthcheck_cron.sh` exit=0，log 末尾 `[OK] F7 cron self-check saw [22]-[29] in current run`。 | 完成 | ✅ | n/a |
| ~~**STRK-FUP-HEALTHCHECK-PRE-EXISTING**~~ | ✅ Closed 2026-04-30 by runtime observation: latest healthcheck has `[3]` PASS, `[19]` PASS, `[23]` PASS, `[24]` PASS, `[26]` PASS, `[27]` PASS. Remaining WARNs are current edge/strategy quality checks (`[4]`, `[11]`, `[33]`, `[38]`, `[40]`), not the original silent-dead pipeline set. | 觀察閉合 | ✅ | no code change needed |
| ~~**LIVE-RECONCILER-STALE-CMD-TX**~~ | ✅ 完成 2026-04-28 Batch A / SW-002：reconciler 改用 per-dispatch `LiveCmdSenderSlot` snapshot；strategist promote 加 `with_promote_cmd_slot()` 動態讀 watcher-rotated live sender；edge reload 原 slot-aware path 保持並由 release tests 驗證。| Batch A fixed | ✅ | 驗證見 `docs/audit/remediation_tracking.md` Batch A Verification Notes |
| ~~**G2-01-FUP-MAKER-FILL-CHECK**~~ | ✅ 完成 2026-04-29 commits `030ef2d` + `0e9e257` + `f0d21b9` + `af9d552`：新增 `[33] maker_fill_rate` dedicated check（7d demo/live_demo entry fills、fee_drop from 5.5bps taker to 2.0bps maker、limit/order diagnostics、per-strategy slices）；補 unit tests。Linux healthcheck 實測 WARN：entry_fills=1402，avg_fee=5.44bps，fee_drop **1.8%**（target ≥60%），maker_like **29/1402 = 2.1%**，limit_order_rows **15.5%**，postonly_order_rows 0%（orders writer 未持久化 TIF，已在 check docstring 註明）。 | 完成 | ✅ | n/a |

---

## 📊 Healthcheck 清單（`passive_wait_healthcheck.py` 已實裝）

**CLAUDE.md §七 強制**：被動等待 TODO 必附 healthcheck · 每 6h cron 跑 · 連續 3 FAIL → 中止等待。

**Runtime ground-truth**：cron-wrapper output is authoritative. As of 2026-04-30 23:11 CEST it prints checks `[1]`-`[40]`（skip `[17]`，含 `[Xa]`/`[Xb]`，無 `[0]`）；源於 `helper_scripts/db/passive_wait_healthcheck/runner.py`。舊 stale 映射（原列 [0] engine_alive / [1] engine_crash / [2] synthetic_owner_retriage / [3] maker_fill_rate / [4] IPC hotpatch / [8] decision_shadow_exits）不再作 runtime truth。

| # | 項目 | SQL / 檢查 | 對應 Wave TODO |
|---|---|---|---|
| [1] | close_fills_24h | demo 24h close_fills 數量（≥10 PASS） | P0-2 21d engine 活性間接指標 |
| [2] | label_backfill | labels_24h vs close_fills ratio + join_linkage | P1-7 C labels |
| [3] | exit_features_writer | exit_features_24h vs close_fills delta（==0 PASS）| EDGE-P1b 寫入面 |
| [4] | phys_lock_runtime | phys_lock_* fire 24h/7d count | TRACK-P-V2-SWAP-1 verify |
| [5] | micro_profit_fire | RETIRED（306993e 後 v1 退役，residue 監控）| — |
| [6] | trailing_stop_fire | TRAILING STOP fire 7d count | — |
| [7] | edge_estimates_freshness | n_cells + mtime | G1-01 / G4-04 |
| [8] | shadow_exits_24h | decision_shadow_exits row count（dormant by `shadow_enabled=false`）| EDGE-P2-flip 觸發前 baseline |
| [9] | model_registry_freshness | train_date per slot | G4-03 |
| [10] | intents_writer_ratio | orders vs intents per-mode | G2-01 / P1-7 C |
| [11] | counterfactual_clean_window_growth | clean n ≥200 | EDGE-P3 auto-gate |
| [12] | bb_breakout_post_deadlock_fix | fill count recover（G2-06 disabled → PASS skip 2026-04-26）| G2-05 / G2-06 |
| [13] | edge_estimator_scheduler_fresh | `edge_estimates.json` mtime <6h + cells ≥50 | G1-01 / G4-04（G6-02 commit `a0a4981`）|
| [14] | exit_features_accumulation_rate | 週 row count + per-strategy tier（READY/GROWING/SPARSE）| EDGE-P1b / EDGE-DIAG（G6-02 `a0a4981`）|
| [15] | shadow_exit_agreement_phase2 | Python vs Rust decision agree rate ≥95% | EDGE-P2 flip（G6-02 `a0a4981`）|
| [16] | strategist_cycle_fresh | scheduler 4MB log tail cycle 活動 | G3-08 / Strategist runtime |
| [18] | disabled_strategy_inventory | active=false strategies list（always PASS，drift防線 G6-04）| G2-06（2026-04-26）|
| [19] | observer_pipeline_alive | observer cycle ok N/5 + age | OBSERVER-PIPELINE-POST-F42FACE-CLEANUP / STRK-FUP-HEALTHCHECK-PRE-EXISTING |
| [20] | h_state_gateway_freshness | env=0 dormant skip / env=1 H state cache version + h_states 集合 | G3-08 Phase 1C / Phase 2+ |
| [21] | paper_state_dust_inventory | `COUNT(*) FILTER realized_pnl=0 FROM trading.fills WHERE strategy LIKE 'risk_close:fast_track%' AND last 1h AND engine_mode IN demo/live/live_demo`；三態 PASS/WARN/FAIL（0=PASS / 1-10+<3sym=WARN / >10 OR ≥3sym=FAIL）| PAPER-STATE-DUST-INVENTORY-MONITOR（Tier 7 Track 2，supersedes MICRO-PROFIT-FIX-1-HEALTHCHECK）|
| [22] | trading_pipeline_silent_gap | fills/intents/orders/risk_verdicts/DCS 多軸 staleness + 1h count；2026-04-29 `bdd3177` RCA fix deployed（demo fee periodic re-seed）| STRKUSDT P0 wave F7 |
| [23] | orders_fills_consistency | 30min pairs_missing_orders / total_missing_orders（FUP-23 SQL exclude `unattributed:%`）| STRKUSDT P0 wave F7 + STRK-FUP-HEALTHCHECK-PRE-EXISTING |
| [24] | signals_writer_freshness | trading.signals hours_stale + rows_24h | STRKUSDT P0 wave F7 + 2026-04-19 outage RCA |
| [25] | dust_qty_distribution | 24h fills sub_micro vs normal bucket pct | STRKUSDT P0 wave F7 |
| [26] | dust_spiral_noise_in_ef | learning.exit_features dust spiral noise total + 24h delta | STRKUSDT P0 wave F7 + EXIT-FEATURES-WRITER-BUG-1-FIX |
| [27] | intents_counter_freeze | demo + live_demo + live intents 30min count + staleness | STRKUSDT P0 wave F7 |
| [28] | phantom_fills_attribution | 1h risk_close + qty<1e-3 + pnl=0 fills | STRKUSDT P0 wave F7 |
| [29] | reconciler_paper_state_divergence | reconciler vs paper_state divergence（deferred-no-ipc placeholder，等 Rust handler）| STRK-FUP-F7-CRON-CD-CHECK |
| [30] | cost_edge_advisor_status | env=0 dormant skip / env=1 cost_edge_advisor TOML + DB freshness + trigger frequency | G3-09 Phase B |
| [31] | edge_diag_2_strategy_diversity | 6h demo Approved strategy diversity（非 grid exploration 是否有流量）| EDGE-DIAG-2 |
| [32] | maker_entry_intent_drift | demo maker-enabled strategies recent entry intents 不得為 market；restart-aware window | PostOnly execution-shape drift / G2-01 guard |
| [33] | maker_fill_rate | 7d demo/live_demo entry fills fee_drop（5.5bps taker→2.0bps maker target ≥60%）+ per-strategy slices | G2-01-FUP-MAKER-FILL-CHECK |
| [34] | intent_signal_attribution | 30min demo/live_demo/live strategy intents 必須有 non-empty `signal_id` 並 join 到 `trading.signals`，且 context_id 一致 | STRATEGY-EDGE-REPAIR-2026-04-29 |
| [Xa] | leader_election_health | edge_scheduler.leader.lock fd alive + lock_age | EDGE-SCHEDULER-LEADER-1（`f32629c`）|
| [Xb] | pipeline_triangulation | close_fills/labels/intents 三角比 | G6-01 FUP cross-validation |

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
