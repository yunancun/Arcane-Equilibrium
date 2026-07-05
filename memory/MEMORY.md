# Memory Index

> 索引條目一行 ≤250 字;細節在 topic 檔(超長舊條目已於 2026-06-10 全文歸檔進各 topic 檔的 `[index-archive]` 節)。
> 治理(2026-06-11 起,R4 巡檢):Project context 索引 ≤40 條,超限新增前必先 MERGE(優先級:主題重疊>敘事弧相同>heat 最低/最舊已完結;archive 守恆);topic 檔 frontmatter 可選 `heat:`(被召回/引用 +1,合併取 sum);被推翻的結論不原地改寫 → topic 檔「演變軌跡」節(日期+轉變+原因+證據 SHA)。

## Project context
- [demo「大量虧損」根因 grid-in-trend×BTC+4.5% (2026-06-15)](project_2026_06_15_demo_loss_rootcause_grid_trend.md) — operator 問昨晚至今大虧根因。4-verifier 對抗複核(信心 HIGH):**根因=grid_trading down-beta × BTC+4.5% 漲行情**(opens Sell40/Buy3,grid_close_short 平空 -39.83,成交量 4x;同靜態代碼 06-12 開多賺、06-15 開空虧,方向由市場定非配置改),走早於 ADPE 的 EDGE-DIAG-2 低樣本探索分支放行。**純 demo 零真錢**(net~-80,37% 是手續費,0.9% 餘額,已了結)。**初步 ADPE 主假設被推翻**:ADPE all_flat no-op、explore-gate 僅 12 筆/8 分窗在峰值外、IPC auth bug 全失敗=decorative。順帶揭:無 demo 損失熔斷/ADPE IPC auth bug(**2026-06-15 已修 `3e31d87a`**:真因=cron 未注入 `OPENCLAW_IPC_SECRET_FILE` 非 ipc_lever;ADPE 現可 demo actuate)/**引擎 06-15 crash 4 次不入 audit_events**(更正初報「零 crash」)/grid trend-stop None fail-open。細節在 topic 檔
- [全盤冷酷審計 ultracode 12軸+seam (2026-06-14)](project_2026_06_14_cold_audit.md) — 凍結 976d420e;**無 P0/CRITICAL**,live 5-gate 實證 fail-closed;confirmed P1:**AUTH-1 live RiskConfig 繞 5-gate**(patch_risk_config engine=live 只需 operator+scope 無 all_five_live_gates,違 #4/#5,operator 先裁 intent)/PROFIT-1 cost_gate 雙重扣成本(異質佐證 profit-diagnosis 拒 99.97%,不可直接翻先 replay)/SCHEMA-1 sqlx 全 runtime-checked 無 column contract test(M4 已抓 5 滑過)/PERF 三項;seam 7→2 refuted+1 降 LOW(防線比文檔厚);dirty 8 檔讀模型 CLEAN 但 fix-before-commit;教訓:Workflow args 必傳真 JSON 物件非字串(首輪退默認 10 軸);TODO §5 登 6 條 AUDIT-2026-06-14-*;細節在 topic 檔
- [盈利研判 ultracode+/loop:搜索空間根因再確認+Rank7全NO-GO (2026-06-13~14)](project_2026_06_13_profit_diagnosis_searchspace_reconfirm.md) — 不賺錢=搜索空間問題非執行(OHLCV+TA net alpha=0,n=159萬,正PnL=down-beta副產品;cost_gate拒99.97%全真負0誤殺;realized近平偏正=空轉非虧損)。/loop 自主推進跑 Rank7 桶C 另類數據軸 $0 離線螢幕:funding+OI+LSR/liq-cascade 雙 NO-GO(down-beta 偽裝),Polymarket NEEDS-DATA;雙對抗複核(QC 攻無alpha→HOLDS/PA 攻延後→HOLDS,親 grep 證偽「縮虧解鎖被擋單」)。iteration3 跑 Polymarket calibration gate=WELL-CALIBRATED(Brier 0.052/skill +0.79)→PARK-CONFIRMED但拆:價格目標子軸KILL(odds是spot機械衍生不可能lead perp)、事件/監管子軸(ETF/SEC/FOMC)值得$0累積3-6月。**loop終態:profit搜索徹底窮盡(4軸全驗),現無廉價近期lever(四重確認);剩餘全operator-hand(啟cron/flip flag/部署/付費),主會話一個都沒自動執行(守read/write分離+survival-first)**;細節在 topic 檔
- [五 repo 借用評估+P0/P1/P2 全落地 (2026-06-11~12)](project_2026_06_11_five_repo_subagent_token_eval.md) — **P0/P1 `4587f65f`+P2 `131bd560..5e3820f3`**(四波 agent 鏈全綠):P0=rtk hook 全鏈/SessionStart 路由/25 description/四態契約;P2=L2 PG 記憶層 dormant(V139+蒸餾管線+seed+pgvector 緩裝,flag-OFF)/告警耐久 sink+redactor/BB 公告哨兵(alert-only)/polymarket 軸(artifact-only)/analyze_token_usage/mnemopi 試點;**owed(operator-gated):rtk#2399 簽 CLA、V138+V139 prod apply、三 cron 一鍵激活、bge-m3 pull**;細節在 topic 檔
- [BG subagent「卡死」根因三層+SOP shipped (2026-06-11)](project_2026_06_11_bg_subagent_idle_kill_rootcause.md) — ①desktop 900s idle-pause 殺光 in-flight BG agent(兩波 2 秒實證,不可復活);②output-stub/worktree mtime 判死=必誤殺,**唯一信號=subagents/agent-*.jsonl mtime**;③限額日 API 單往返 5m38s 假死。**路線 B 拍板,SOP shipped `558ded55`**:CLAUDE§八+PM.md 正本(駐留等收/TaskStop 三前置/續作棒)+E1 checkpoint+`agent-wave` workflow(resumeFromRunId 零浪費重放);**三端同步完 `7712ec80`**(增量 14 檔 worktree 重放+E1 memory union 解衝突;殭屍指針出清;Linux repo=`~/BybitOpenClaw/srv`)
- [L2 P4 全鏈 shipped+P2p 哨兵 shipped (2026-06-10~11)](project_2026_06_10_l2_p4_ratify_p2p_shipped.md) — **P4 merged main `ddaafda1`(06-11,dormant 三重關)**:MIT 7 項+QC sign-off+三線 E1→E2(抓 **V137/[82] 被 P5-SM 撞號**→改 V138+[83]-[87])→PM stage0r 三向映射裁決→E4 GREEN(scratch-DB E2E 全鏈+wiring 釘子);owed=V138 prod apply(operator-gated)。教訓:**migration/healthcheck 號=git 看不見的全局命名空間**;前台 Agent 串行=turn 不落地最穩。P2p merge `661699e5`;owed=Telegram creds(operator 後補)→probe→installer。**watchdog 告警現仍靜默 no-op**
- [half_life 測試 2F 修復+Linux 測試 lane 拓撲 (2026-06-10)](project_2026_06_10_half_life_scipy_lane_fix.md) — 根因=系統 python 無 scipy 靜默降級(日期/seed/容差假說全偽);importorskip 守衛 landed main `5421897e`;runtime scipy 1.17.1 已裝→7p un-skip 實證;ledger 歸屬=producer-gate 非 4661/8;教訓:重依賴測試 FAIL 先查 env lane
- [三端同步+ops2 merge+多 session 髒樹清理 (2026-06-10)](project_2026_06_10_triend_sync_ops2_merge.md) — ops2 cutover 4 commits merge main(零衝突,代碼靜止待重啟,rotation 09-08 不變);Mac 髒樹 60 檔分桶:stale L2_TODO/aeg WIP 進 rescue branch `rescue/mac-dirty-2026-06-10`(`1689b153`),17 檔孤檔文檔入庫 main;Mac 切回 main;教訓:fork memory 檔判方向看誰引用更晚的 commit SHA
- [Agents/Skills 全面修訂+memory 壓實+多視角驗證 (2026-06-10)](project_2026_06_10_agents_skills_revamp.md) — 42 檔 +740/−999 字面化模型適配+hot-facts+canonical 正本表;**根目錄 .claude=symlink→srv/.claude 單副本**;memory 壓實 41,323→3,200 行(archive 守恆,R4>300 行巡檢);PM 多視角對抗驗證(E2∥E3∥E5+合議)+報告契約;**三端同步完 main `02c80f3b`**(worktree 重放;E1 補 main 側條目;gitignore 白名單 workflows);Mac 仍在 superseded 分支僅指針未切
- [A 組 triage + OPS-2 cutover 全鏈 + P5-SM 監測重設計 (2026-06-10)](project_2026_06_10_a_group_triage.md) — OPS-2 cutover 全鏈完成,**已 merge main(06-10,代碼靜止待重啟;rotation due 09-08 不變)**(E1→E2×2→E4→CC A-→BB 0FLAG→PM signoff;branch 4 commits);AC19 alt FAIL;TONUSDT watch 關;P5-SM 新 gate S1-S5(雙邊 divergence 結構性不可達=鐵則);TODO v123;教訓:psql 2>/dev/null 吞 error 須交叉檢核/base-vs-HEAD 全套 diff 抓漏掃/跳角色前先讀 owner 行
- [L2 Mesh P1-P3b DEPLOYED+owed 五項 DONE (2026-06-10)](project_2026_06_08_l2_d3_phase1_green.md) — topic 原文保留部署/owed 歷史；**current authority correction 2026-07-05**: active L2 tail 在 `TODO.md` row `P1-L2-ADVISORY-MESH-E2E-1`，historical ledger/reference 已移至 `docs/archive/2026-06-05--l2_advisory_mesh_todo.md`；E2E-1 仍需 operator 明確批准一次 true model call 後復原 disabled，不得按本舊索引視為全閉。
- [幽靈倉位 fill 記帳 bug 修復+部署 (2026-06-08)](project_2026_06_08_phantom_position_fill_fix.md) — demo TON 幻影倉根因=PositionUpdate/Fill 無序雙寫競態;修=apply_fill 唯一 mutator+reduce-only fail-closed+reconciler 幻影偵測軸;全鏈綠+原子部署(commit 74b2e264→origin bdf15e4f);剩:告警僅 DB 可查/LiveDemo 缺 authorization.json(既有)
- [Odysseus AI workspace 部署於開發 Mac (2026-06-08)](project_2026_06_08_odysseus_mac_deploy.md) — PewDiePie self-hosted AI native 裝 ~/Projects/odysseus,loopback-only 加固;**ssh trade-core 靠 Tailscale MagicDNS,Tailscale 斷=SSH 斷**,承 [[project_ssh_bridge_workflow]]
- [P2 #6/#7/#8 orderLinkId/postmortem/AST (2026-06-06;06-07 已生效)](project_2026_06_06_p2_orderlinkid_postmortem_ast.md) — #6 110072 close-only idempotent `a59a7f60`+#7 postmortem 分類器 `e0dc2a14` **已於 2026-06-07 全量 rebuild+restart 生效**(V131-133 同次 apply);10001-dup 對齊 follow-up `7ccf8451`;#8 AST defer(解凍 gate 剩 schema freeze);github:22→ssh-over-443 繞過
- [Residual alpha producer 全完成+部署+flag-on (2026-06-05~08)](project_2026_06_05_residual_producer_build.md) — PART 1-3 全完成部署:producer+signal_spec+hidden_oos sealer+mlde hook+PART 2 replay bridge,**06-07 上 main 部署,`OPENCLAW_RESIDUAL_ALPHA_PRODUCER=1` cron daily 03:17,attach 7/7**;PART 4 gap-closure(多因子+permutation+Stage0R preflight orchestrator)deployed **flag-OFF**,真實活化=operator 決策(STAGE0R flag+cron job+Linux flag-ON 驗);單配置 demo 誠實 defer 非吐 alpha
- [引擎自愈 bind-host 宕機事故 (2026-06-05)](project_2026_06_05_engine_selfheal_bindhost_incident.md) — 引擎掛 20h 根因=OPENCLAW_BIND_HOST=0.0.0.0 卡 watchdog 重啟;close-all 全走 Rust IPC,引擎掛=GUI 零平倉路徑;watchdog 自愈雙 bug 修 072b8e20;仍開:canary_events.jsonl 無告警消費者
- [FinceptTerminal 評估 (2026-06-04)](project_2026_06_04_fincept_terminal_eval.md) — 數據終端非執行引擎,AGPL 不能抄;唯 3 值得:Polymarket/Kalshi 免費 API 獨立信號軸/finagent Reflexion 思路/MCP ToolDef;edge 來自新數據軸非套框架;待 operator 拍 A/B/C
- [外部框架借鑒+代碼級自審 (2026-06-04)](project_2026_06_04_external_framework_audit_and_self_audit.md) — 評 RD-Agent/AlphaAgent/QuantaAlpha;自審揭 overclaim:beta_quant.py 是 /tmp 蒸發腳本、新策略不過 DSR/PBO;定位=上游發現弱下游治理強,grep beta=0;非-OHLCV 特徵已 live 可離線搜;RevolutX 僅借 orderLinkId ~5行
- [被攔信號反事實+H2 cascade fade 雙 NO-GO (2026-06-03)](project_2026_06_03_blocked_signal_and_cascade_fade_nogo.md) — 兩線同根因 down-beta 偽裝:blocked grid_short demeaned-α≈0、cascade fade 280 事件全 |t|<1.3;BTC 17d −13.9% regime 任何短 bias=趨勢 beta→強制 beta 中性化;Dream「噪音公式」指控證偽=過度警報(Option A cd01eb92);pg_stat n_live_tup 不可靠須 count(*)
- [接手審計+AEG-S2/funding-tilt 設計 (2026-06-03)](project_2026_06_03_v58_archive_audit_s2_design.md) — V5.8 歸檔完整性 3 塊 PASS;P5 soak total 空轉陷阱發現;funding-tilt 全 harness=NO-GO-C(carry_cost_ratio 3.64/DSR 0/82% down-beta;第 5 候選同根因);主路回 listing fade
- [AEG trend/listing infra 部署 (2026-06-02)](project_2026_06_02_aeg_trend_listing_infra_deployed.md) — V125 alpha 儲存+daily-kline backfill 14505 根+Gate-B 隔離 listing 探針(R-0 zero-leak)三端同步 c1c017b0;24h 真捕捉 operator-timed;教訓:post-deploy 真連線 smoke>mock(抓 parquet COPY-TO-? 崩潰)
- [Rust/Python 邊界+精簡通盤審計 (2026-06-01~02 全鏈)](project_2026_06_01_rust_python_boundary_simplification_audit.md) — 邊界 0 誤置/非膨脹;P0-P4+async-infra 10 commits 完成(SM contract test/共用庫/route 拆分/place_order mainnet guard/replay 半切);D 關閉=保留 dormant 能力;SM end-state=Option 2(Rust 唯一權威);P5 step-i Rust `a99bfa1d`+E1b comparator `e6aa5e37` 完成,**soak gate 卡監測重設計**;教訓:socket 中斷後 agent 自標 completed 不可信
- [6 週無 edge 根因調查 (2026-06-01)](project_2026_06_01_fail_closed_gate_stack_root_cause.md) — runtime 推翻 gate-棘輪論:cost_gate 拒 90.5% 全真負 0 誤殺;真問題=已實現 edge 普遍負(無入場 alpha/exit-policy/成本);教訓:代碼審計易過度歸因 gate,runtime 查驗擋排序錯
- [DB schema 衛生清理 (2026-06-01)](project_2026_06_01_db_schema_hygiene_cleanup.md) — 真浪費=909MB damaged/legacy 備份表;「全庫零讀」要查 code+pg_depend 兩層(view 層 grep 會漏);V126 已清(909MB 回收)
- [A1 funding_short_v2 結構性 DOA (2026-05-31)](project_2026_05_31_funding_short_structural_doa.md) — probe #1 reject 主因 missing_basis_asof 93%;**BB 06-31 更正:正側 cap 是 IR floor 指紋非結構封頂,A1=regime-dormant 非永久 DOA**;真 viability 問題=160% break-even 門檻(QC 範疇)
- [V5.8 alpha pivot — 凍結 autonomy 主攻 alpha (2026-05-31)](project_2026_05_31_v58_alpha_pivot.md) — operator 拍板凍 M1/M2/M6/M8/M9 active-IMPL,解凍 gate=首個 net+ candidate stage0_ready(M7 例外);成本牆:6 週多候選死於 edge 1-3bps<成本 11-27bps,翻牆僅事件驅動大 move 或低 turnover 多日;R-2b 驗 multi-day 成本逃逸機制成立但 edge 未證;最快路徑=歷史 kline backfill 而非等 Q4
- [Layered Autonomy with Fail-Safe 設計 (2026-05-22)](project_2026_05_22_layered_autonomy_with_failsafe.md) — AMD-2026-05-21-01 v2;Autonomy Toggle+三路通知 fail→SM-04+7d cooling;CC APPROVE A 級;Wave 5 cascade IMPL PENDING
- [REF-20 Sprint 1-4 closure (2026-05-03)](project_2026_05_03_ref20_sprint1_2_closure.md) — P6 PRODUCTION CLOSED;24/25 V3 §12 GREEN
- [codex 4-day audit chain (2026-05-02)](project_2026_05_02_codex_4day_audit.md) — 162 commits cold review;P1-1 retrofit closed;.codex/=hint mirror only
- [LIVE-AUTH-WATCHER fix (2026-04-27)](project_live_auth_watcher_event_consumer_spawn.md) — watcher respawn 漏接 event_consumer 已修;P1 stale-cmd-tx 待修
- [OpenClaw 定位决策](project_openclaw_positioning.md) — Gateway=通信+運維;Rust openclaw_engine=交易大腦;Python=API橋接+GUI only
- [硬件與存儲基礎設施](project_hardware_constraints.md) — 128GB 統一記憶體 LLM~54GB,PG 4-8GB,40TB NAS via 10GbE
- [未來 Mac 部署目標](project_mac_deployment_target.md) — Apple Silicon(預計 M5);CI 必含 aarch64-apple-darwin
- [ML/DL 自主學習架構](project_ml_dl_learning_architecture.md) — v0.4 Teacher-Student+LightGBM+Optuna+3DL
- [Agent P2 動態 SL/TP](project_agent_p2_dynamic_sl_tp.md) — 默認 ATR 動態,agent_adjust() 可覆蓋,P1 max 硬頂
- [Agent 工作空間系統](project_agent_workspace.md) — docs/CCAgentWorkSpace/ 下 profile/memory/workspace
- [18-agent runtime 接線 (2026-04-25)](project_18_agent_runtime_wired.md) — srv/.claude/agents 18 subagent+25 skill;根目錄 .claude=symlink→srv/.claude(單副本,無雙端)
- [Layer 2 AI 推理循環 (2026-04-23 更正)](project_layer2_agent_design.md) — L0/L1/L2 三層;真 gap=L2 自主推理+Executor shadow→live
- [5-Agent+H1-H5 Runtime (2026-04-23)](project_5agent_runtime_state.md) — ~4552 行 live shadow;Strategist live/Executor shadow 默認
- [GUI 寫入面盤點](project_gui_write_paths_inventory.md) — 93 endpoints;Rust trading_mode 冷參數陷阱;fake-success 判別
- [Phase 5 reframed (2026-04-12)](project_phase5_promotion_edge_crisis.md) — PNL-FIX-1/2 揭全策略 gross 負 edge,cost_gate 工作暫停
- [Edge 數據隔離 (2026-04-13)](project_edge_data_isolation.md) — paper 噪音污染 edge 估計;demo/paper 分離計算
- [Live 階段狀態](project_live_stage_status.md) — 2026-04-10 起 Live 階段(Demo API key),功能按 Live 標準
- [FA-PHANTOM-1 (2026-04-14)](project_fa_phantom_bug.md) — fast_track 誤用 notional/balance 當 margin_util→全策略被全平
- [G-2 FundingArb 結案 NEGATIVE (2026-04-18)](project_g2_funding_arb_monitor.md) — v2 n=13 提前結案 −36.76bps/0 勝率;demo active=false
- [engine_mode 標籤 live_demo (2026-04-16)](project_engine_mode_tag_live_demo.md) — Live+LiveDemo 寫 "live_demo";歷史 43k "live" 實為 LiveDemo;ML filter IN ('live','live_demo')
- [Paper 預設關閉 (2026-04-16)](project_paper_pipeline_disabled_by_default.md) — OPENCLAW_ENABLE_PAPER=1 才 spawn;Gate 1.6 負餘額
- [P0-6 RCA (2026-04-17)](project_p06_rca_and_fix_plan.md) — FUP 抑制致 bybit_sync 死鎖+cost_gate 冷啟動死循環;修=startup triage
- [Mac=開發/Linux=Runtime](project_dev_runtime_split.md) — Mac 讀寫碼/RCA;engine/PG 全 Linux;Mac engine not_running 預期
- [decision_outcomes 2 bug (2026-04-21)](project_decision_outcomes_not_dead.md) — Writer 活躍不可刪;timeframe '1' vs '1m' 不一致+engine_mode INSERT 漏接線
- [Track P 物理層 runtime live (2026-04-21/22)](project_track_p_runtime_live.md) — T4+V2 SWAP 完成;Priority 6 呼 physical_micro_profit_lock_v2
- [多 CC session memory race (2026-04-23)](project_multi_session_memory_race.md) — 協議=commit-first/不認識改動禁 revert/被 revert 從 Linux+origin 重建
- [SSH bridge workflow (2026-04-21)](project_ssh_bridge_workflow.md) — Mac SSOT 經 ssh trade-core 觸發 Linux;Mac 允許 fetch+pull --ff-only(禁 merge/rebase/reset)
- [LinUCB shadow compare 保留 (2026-04-23)](project_linucb_shadow_compare_retention.md) — 4-06 deferred;保留至 Rust warm-start 實裝
- [First-detection deadlock 反模式 (2026-04-24)](project_first_detection_deadlock_pattern.md) — is_none() guard+無過期 auto-clear→symbol 永久 dormant
- [TODO 10-Agent Audit 重構 (2026-04-24)](archive/project_2026_04_24_todo_refactor.md) — 45 findings/4 wave;TODO 700→328 行
- [edge_estimator_scheduler 修復 (2026-04-24)](project_edge_scheduler_stalled.md) — G1-01 已修;JSON 是 strategy::symbol top-level key 非 nested
- [Agent 追蹤視圖 MVP (2026-04-28)](project_agent_tracker_mvp_shipped.md) — Learning Cockpit AI 团队工作台;deploy 用 restart_all --keep-auth
- [funding_arb V2 棄策略路徑 (2026-05-02)](project_funding_arb_v2_deprecation_path.md) — 1B 收樣本/2A 中期棄(delta-neutral 數學不成立)/3C TOML a19797d
- [P0 sqlx hash drift incident (2026-05-02)](project_2026_05_02_p0_sqlx_hash_drift.md) — 改 migration file 沒同步 DB checksum;治本=repair_migration_checksum;盲點=audit closure 漏 engine restart 實測
- [ml_training cron 是 hybrid (2026-05-09/10)](project_2026_05_09_ml_training_cron_weekly.md) — 5 training DAILY;5 audit DAILY fire 但 weekday=6 gate;MIN_SAMPLES=200 4/5 策略不過
- [Sprint N+0 closure / N+1 D+0 readiness (2026-05-10)](project_2026_05_10_sprint_n0_closure.md) — N+0([n0 檔]):attribution_chain_ok 0.5%→100%;[40] avg_net −17.82→+8.75bps;5 textbook 策略 alpha-deficient 不變;HEAD b6ed4975。N+1([project_2026_05_10_sprint_n1_d0_readiness.md]):25 項 land HEAD bf66f1b2;W7-3/W7-1 PR ready NOT DEPLOYED

## Working principles & autonomy
- [市場必然可主動盈利,禁範式陷阱探非常規數學 (2026-06-14)](feedback_active_profit_unconventional_mandate.md) — operator 鐵則:市場必然可主動盈利,「增加投入/被動等數據」=消極不接受。我被抓失敗模式=所有 NO-GO 都死於同一測試(線性 IC×OHLCV×beta 殘差×taker 成本牆=只為方向性 taker 預測設計),窮盡那一角落卻誤判整個市場無 edge(範疇錯誤)。須用各 lens 原生數學(做市/統計套利/Hawkes/資訊論/delta-carry/跨所),偏結構性·機械性 edge(非靠預測),discover AND implement
- [Agent 自主權偏好](feedback_agent_autonomy.md) — 用戶只設 global 止盈止損,Agent 自主決定策略/參數/時機/倉位
- [最少確認偏好](feedback_minimal_confirmation.md) — 不反復問 yes,自主執行,只真正高風險才確認
- [主動 push back](feedback_pushback.md) — operator 錯了/含糊必須直接指出+提替代;協作者≠執行者
- [Position Sizing 偏好](feedback_position_sizing.md) — 3% risk/trade, 25 symbols, 動態 qty
- [四條核心工作原則](feedback_working_principles.md) — 誠實報告測試/簡潔輸出/對抗性驗證/多角色工作流不可跳過
- [Evidence discipline under degraded tools (2026-05-31)](feedback_evidence_discipline_under_degraded_tools.md) — 寫 verdict 前讀 source 全文/ssh 暫存檔分次讀/build-SHA≠git-commit/sub-agent 比即時 ssh 解讀可靠
- [風險參數修改必須限定範圍](feedback_risk_changes_scoped.md) — 只改被要求的參數,不連帶重設
- [關閉 Adaptive Thinking](feedback_disable_adaptive_thinking.md) — 不使用延伸思考,直接輸出(operator 明確要求)
- [Edge 分析用 demo 不用 paper](feedback_demo_over_paper_for_edge.md) — edge 估計取 demo fills;paper 失真
- [Demo 放寬/Live 收緊 (2026-04-28)](feedback_demo_loose_live_strict_policy.md) — Demo=學習源可放寬;Live 永遠 fail-closed;核心是平衡虧損與盈利
- [MICRO-PROFIT-FIX-1 意圖](feedback_micro_profit_fix_intent.md) — 「有微利就套(net>0)」非 cost_edge_ratio gate
- [LiveDemo 不因 endpoint 降級](feedback_live_no_degradation_by_endpoint.md) — 授權/TTL/風控按 Live 嚴格標準
- [中文輸出偏好](feedback_chinese_output.md) — 對 operator 中文為主;英文留技術名詞/代碼/commit
- [三環境風控 config 獨立](feedback_env_config_independence.md) — paper/live/demo toml 故意分開,禁純衛生合併
- [Shell 指令抗貼上](feedback_shell_paste_safety.md) — 給 operator 的 shell 一律單行;複雜邏輯寫檔案
- [Rolling-window look-ahead bias (2026-04-24)](feedback_indicator_lookahead_bias.md) — rolling(N).max() 含 current bar 必然 mean-revert;研究必並列 shift(1) 對比
- [V### migration PG dry-run mandatory (2026-05-05/28)](feedback_v_migration_pg_dry_run.md) — 先 Linux PG empirical;double-apply 是 load-bearing gate
- [注釋默認只寫中文 (2026-05-05)](feedback_chinese_only_comments.md) — 新注釋只中文;觸碰時移英文留中文
- [GUI sign-off 必跑 node --check (2026-05-09)](feedback_gui_node_check_sop.md) — brace diff=0 不能代替
- [GitHub Actions cost policy (2026-05-09)](feedback_github_actions_cost.md) — 2000min/月;macOS 10x 僅 PR+週一 cron

## Workflow & roles
- [強制工作鏈與審計模板](feedback_workflow_audit_chain.md) — E1→E2→E4→PM 不可跳過;策略改動加 QA Audit
- [主會話角色:PM+Conductor](feedback_role_definition.md) — 主會話=PM+Conductor;sub-agent 只執行/審查/研究
- [強制先評估 sub-agent 拆分](feedback_subagent_first.md) — 收任務先想能否拆後台並行
- [Sub-agent 可寫碼 (2026-04-18 驗證)](feedback_subagent_code_writing_refusal.md) — refuse pattern 已解除;E1 可派並行寫碼
- [Meta-doc 用 git commit --only](feedback_git_commit_only_for_metadoc.md) — CLAUDE/TODO/docs/memory 必用 --only;multi-session 下 add+commit 不安全
- [多角色 adversarial review (2026-04-24/05-28)](feedback_multi_role_strategic_review.md) — 關鍵決策派並行獨立 review;grill-me+獨立 agent cross-verify
- [派工前 fetch+查遠端 branch+log-grep ticket (2026-04-24/05-28/06-10)](feedback_fetch_before_dispatch.md) — TODO Banner 可 stale 數天;dispatch prompt 留 NO-OP exit;commit 批次前也 re-fetch(branch 可被並行 session 中途宣告 SUPERSEDED),救援=detached worktree+cherry-pick+push HEAD:main
- [IMPL DONE 必走 A3+E2 對抗核驗 (2026-05-09)](feedback_impl_done_adversarial_review.md) — 高風險 IMPL 自評不接受單獨 sign-off

## Code & architecture rules
- [Rust 為唯一交易參數權威](feedback_rust_authoritative_config.md) — GUI 直寫 Rust,Python 僅只讀
- [新代碼必須 Rust 優先](feedback_new_code_rust_first.md) — 新獨立模組 Rust+PyO3,不增 Python 債
- [跨平台兼容性準則](feedback_cross_platform.md) — 隨時可部署 Mac;路徑不硬編碼
- [可調參數禁止假功能](feedback_no_dead_params.md) — 參數必須真實被發現/調整/持久化
- [restart_all --rebuild 範圍](feedback_restart_rebuild_flag_scope.md) — --rebuild 同時重建 engine+PyO3
- [restart bind host safe default (2026-05-09)](feedback_restart_bind_host_default.md) — auto 解析 Tailscale IPv4 否則 loopback;禁 0.0.0.0

## References
- [ultracode 全盤審計編排設置 (2026-06-10)](reference_ultracode_full_audit.md) — saved workflow `srv/.claude/workflows/openclaw-full-audit.js`+conductor skill `ultracode-full-audit`;默認 report-only,fix 需顯式 args;非 ultracode 降級 PM 順序鏈
- [Remote Access 配置](reference_remote_access.md) — Tailscale: Trading GUI / OpenClaw URLs
- [重啟腳本](reference_restart_script.md) — bash helper_scripts/restart_all.sh
- [外部整合工具入口 (2026-04-29)](reference_external_tools.md) — **superseded posture**; current authority=GitHub Issues active, Linear historical/passive unless explicitly reopened;Notion frozen;其餘 declined
- ARCH-RC1 統一 Config 契約 → `docs/references/2026-04-15--arch_rc1_unified_config_contract.md`

## External tool authority
- [外部工具權威邊界 (2026-04-29)](feedback_external_tool_authority.md) — **superseded posture**; current authority=GitHub Issues active, Linear historical/passive unless explicitly reopened;看到 declined MCP 不重新評估啟用

> Archived stale memories moved to `archive/` (Phase 1-era / completed migrations / superseded plans / merged originals).
