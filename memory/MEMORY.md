# Memory Index

> 索引條目一行 ≤250 字;細節在 topic 檔(超長舊條目已於 2026-06-10 全文歸檔進各 topic 檔的 `[index-archive]` 節)。
> 治理(2026-06-11 起,R4 巡檢;2026-08-01 修訂):Project context 索引 ≤40 條,超限新增前必先 MERGE(優先級:主題重疊>敘事弧相同>最舊已完結,以 git log 對 topic 檔的最後實質更新日期為代理;archive 守恆);heat 機制已廢(2026-08-01:欄位從未被回填,治理不得引用死數據);被推翻的結論不原地改寫 → topic 檔「演變軌跡」節(日期+轉變+原因+證據 PR#/日期)。

## Project context
- [框架健檢 23/23 CONFIRMED+全項優化裁決 (2026-08-01)](project_2026_08_01_framework_health_audit.md) — 主訴 session 久+用量飛耗→8 線調查:月 cache_read 10.86B、subagent 佔 output 65%、AIML S2 弧佔 70.6%、五結構性 loop 全 CONFIRMED;operator 裁全項+三級模型分級;四 fw-* lane 落地;wave2 待辦見 topic 檔
- [reconcile Path B advisory-first 弧 (2026-07-12~17)](project_2026_07_12_reconcile_pathb_arc.md) — 對賬鈕三層壞→Path B 真對賬 source-landed(cap 永不 freeze;arming 待 P2);unit-env 漂移修 PR#22;OOM P0(PR#27/#31 部署,streaming PR#43-56);哨兵[95]+manifest PR#24/#30;topic 檔
- [ultracode 全審弧 (06-14 冷審→07-11 修復→07-24 run0)](project_2026_07_11_ultracode_audit_remediation.md) — 06-14 冷審無 P0,P1=AUTH-1(已修)/PROFIT-1/SCHEMA-1(見 cold_audit topic 檔);07-11 九項修復上 main;07-24 run0:9C+92 債,首二項收口(PR#115/117),adaptive_shadow 不可退;topic 檔
- [profit-first 自主 loop(承 maker-nogo)(2026-07-08~10)](project_2026_07_08_profit_first_autonomy_loop.md) — 自跑 discover→admit→execute→review→learn;07-09 R3 推翻候選統計(偽複製)→07-10 dedup+n_eff 重跑=零合格(7/7 VETO),loop 回 discover 段;零 order/fill proof;topic 檔
- [AIML-V2:S1_CLOSED→S2 source chain (2026-07-28)](project_2026_07_21_aiml_s0_adoption_gate.md) — 07-22 ADOPTED;S2 七 predicates 全 SOURCE_READY(PR#151 `a7c36775d`)→BLOCKED_OPERATOR_ACTION_PACKET_READY;runtime 仍 inactive;W5 receipts=`5be472193`;topic 檔
- [IBKR stock/ETF full live-capability 軸 (2026-06-29~;08-01 對時)](project_2026_07_08_ibkr_stock_etf_readonly.md) — AMD-2026-07-11-01=development 全授權+活化分離;正本=IBKR_TODO.md+PROGRESS.md(帳本至 R29;W0-W6 DONE_SOURCE_SECURED,W7 4/5);runtime dormant;細節 topic 檔
- [maker-first 做市執行軸 fill_sim 雙窗判 NO-GO (2026-07-06)](project_2026_07_06_maker_first_nogo.md) — fill_sim 3400萬筆雙窗 0/172 格淨正,break-even 需 maker≤0.4bps(VIP0=+2bps)=infra-tier 鎖;不賺錢=無方向 alpha+執行 edge 被費用鎖,非缺 AI;dormant=M12 router;仍開:新上市寬價差;topic 檔
- [盈利研判 R3+修復包全上線 (2026-07-09~10;承 R2 06-13)](project_2026_07_09_profit_diagnosis_roi_map.md) — 30d true net −406 USDT fee-dominated(live=0);71k 重跑=FALSE_KILL 證偽(7/7 VETO 零翻正);E2E-1 真 call $0.0149 後復原 disabled;#2/#3 雙 descoped-GO(僅儀器/$0 管線);topic 檔
- [五 repo 借用評估+P0/P1/P2 全落地 (2026-06-11~12)](project_2026_06_11_five_repo_subagent_token_eval.md) — P0-P2:rtk hook/SessionStart 路由/四態契約;L2 PG 記憶 dormant+告警 sink+BB 哨兵+polymarket 軸(flag-OFF);owed rtk CLA/bge-m3(V138+V139 已 apply,cron 已復原);topic 檔
- [BG subagent「卡死」根因三層+SOP shipped (2026-06-11)](project_2026_06_11_bg_subagent_idle_kill_rootcause.md) — ①desktop 900s idle-pause 殺光 BG agent②唯一 liveness=subagents/agent-*.jsonl mtime③限額單往返 5m38s 假死;SOP+agent-wave(resumeFromRunId)shipped;topic 檔
- [L2 P4 全鏈 shipped+P2p 哨兵 shipped (2026-06-10~11)](project_2026_06_10_l2_p4_ratify_p2p_shipped.md) — P4 merged main(dormant 三重關);V138 prod apply 完成(PG head=150);P2p owed=Telegram creds;watchdog 告警 no-op;教訓:migration/healthcheck 號=git 外全局命名空間;topic 檔
- [L2 Mesh P1-P3b DEPLOYED+E2E-1 終態 (2026-06-10→07-10)](project_2026_06_08_l2_d3_phase1_green.md) — TODO row P1-L2-ADVISORY-MESH-E2E-1=DONE_WITH_CONCERNS(07-10 真 model call 達成後 L2 復原 fully disabled;殘=fence-parsing sink follow-up 新 ticket);細節在 topic 檔
- [幽靈倉位 fill 記帳 bug 修復+部署 (2026-06-08)](project_2026_06_08_phantom_position_fill_fix.md) — demo TON 幻影倉根因=PositionUpdate/Fill 無序雙寫競態;修=apply_fill 唯一 mutator+reduce-only fail-closed+reconciler 幻影偵測軸;全鏈綠+原子部署;剩:告警僅 DB 可查/LiveDemo 缺 authorization.json
- [Residual alpha producer 全完成+部署+flag-on (2026-06-05~08)](project_2026_06_05_residual_producer_build.md) — PART1-3 部署(producer/sealer/mlde hook/replay bridge),06-07 上 main flag-on,cron 03:17;PART4 deployed flag-OFF,活化=operator 決策;topic 檔
- [外部框架借鑒+代碼級自審 (2026-06-04)](project_2026_06_04_external_framework_audit_and_self_audit.md) — 評 RD-Agent/AlphaAgent/QuantaAlpha;自審揭 overclaim:beta_quant.py 是 /tmp 蒸發腳本、新策略不過 DSR/PBO;定位=上游發現弱下游治理強;非-OHLCV 特徵已 live 可離線搜;RevolutX 僅借 orderLinkId ~5行
- [被攔信號反事實+H2 cascade fade 雙 NO-GO (2026-06-03)](project_2026_06_03_blocked_signal_and_cascade_fade_nogo.md) — 兩線同根因 down-beta 偽裝:grid_short α≈0、cascade fade 全 |t|<1.3;跌勢 regime 短 bias=趨勢 beta→強制中性化;Dream 指控證偽;pg_stat n_live_tup 不可靠須 count(*)
- [AEG trend/listing infra 部署 (2026-06-02)](project_2026_06_02_aeg_trend_listing_infra_deployed.md) — V125 alpha 儲存+daily-kline backfill 14505根+Gate-B 隔離 listing 探針(R-0 zero-leak)三端同步;24h 真捕捉 operator-timed;教訓:post-deploy 真連線 smoke>mock(抓 parquet 崩潰)
- [Rust/Python 邊界+精簡通盤審計 (2026-06-01~02)](project_2026_06_01_rust_python_boundary_simplification_audit.md) — 邊界0誤置;P0-P4+async 10 commits 完成;**SM end-state=Option 2(Rust唯一權威)**;教訓:socket 中斷後 agent 自標 completed 不可信;細節在topic檔
- [6 週無 edge 根因調查 (2026-06-01)](project_2026_06_01_fail_closed_gate_stack_root_cause.md) — runtime 推翻 gate-棘輪論:cost_gate 拒 90.5% 全真負 0 誤殺;真問題=已實現 edge 普遍負(無入場 alpha/exit-policy/成本);教訓:代碼審計易過度歸因 gate,runtime 查驗擋排序錯
- [A1 funding_short_v2 結構性 DOA (2026-05-31)](project_2026_05_31_funding_short_structural_doa.md) — probe #1 reject 主因 missing_basis_asof 93%;**BB 06-31 更正:正側 cap 是 IR floor 指紋非結構封頂,A1=regime-dormant 非永久 DOA**;真 viability 問題=160% break-even 門檻(QC 範疇)
- [Layered Autonomy with Fail-Safe 設計 (2026-05-22)](project_2026_05_22_layered_autonomy_with_failsafe.md) — AMD-2026-05-21-01 v2;Autonomy Toggle+三路通知 fail→SM-04+7d cooling;CC APPROVE A 級;Wave 5 cascade IMPL PENDING
- [OpenClaw 定位决策](project_openclaw_positioning.md) — Gateway=通信+運維;Rust openclaw_engine=交易大腦;Python=API橋接+GUI only
- [硬件與存儲基礎設施](project_hardware_constraints.md) — 128GB 統一記憶體 LLM~54GB,PG 4-8GB,40TB NAS via 10GbE
- [未來 Mac 部署目標](project_mac_deployment_target.md) — Apple Silicon(預計 M5);CI 必含 aarch64-apple-darwin
- [ML/DL 自主學習架構](project_ml_dl_learning_architecture.md) — v0.4 Teacher-Student+LightGBM+Optuna+3DL
- [Agent P2 動態 SL/TP](project_agent_p2_dynamic_sl_tp.md) — 默認 ATR 動態,agent_adjust() 可覆蓋,P1 max 硬頂
- [Agent 工作空間系統](project_agent_workspace.md) — docs/CCAgentWorkSpace/ 下 profile/memory/workspace
- [agent runtime 接線 (2026-04-25;08-01 更正)](project_18_agent_runtime_wired.md) — srv/.claude/agents 22 subagent+28 skills(08-01 實測);根 .claude=真目錄,內含 agents/skills/workflows 三 symlink 子項→srv/.claude+本地 settings.local.json(「無雙端」不再成立);演變軌跡在 topic 檔
- [Layer 2 AI 推理循環 (2026-04-23 更正)](project_layer2_agent_design.md) — L0/L1/L2 三層;真 gap=L2 自主推理+Executor shadow→live
- [GUI 寫入面盤點](project_gui_write_paths_inventory.md) — 93 endpoints;Rust trading_mode 冷參數陷阱;fake-success 判別
- [Edge 數據隔離 (2026-04-13)](project_edge_data_isolation.md) — paper 噪音污染 edge 估計;demo/paper 分離計算
- [Live 階段狀態](project_live_stage_status.md) — 2026-04-10 起 Live 階段(Demo API key),功能按 Live 標準
- [engine_mode 標籤 live_demo (2026-04-16)](project_engine_mode_tag_live_demo.md) — Live+LiveDemo 寫 "live_demo";歷史 43k "live" 實為 LiveDemo;ML filter IN ('live','live_demo')
- [Paper 預設關閉 (2026-04-16)](project_paper_pipeline_disabled_by_default.md) — OPENCLAW_ENABLE_PAPER=1 才 spawn;Gate 1.6 負餘額
- [Mac=開發/Linux=Runtime](project_dev_runtime_split.md) — Mac 讀寫碼/RCA;engine/PG 全 Linux;Mac engine not_running 預期
- [多 CC session memory race (2026-04-23)](project_multi_session_memory_race.md) — 協議=commit-first/不認識改動禁 revert/被 revert 從 Linux+origin 重建
- [SSH bridge workflow (2026-04-21;07-14/16 演變)](project_ssh_bridge_workflow.md) — Mac 只 fetch+pull --ff-only;07-14 main 直推禁→feature branch→PR→gh merge;**07-16 main 全史 filter-repo 重寫:此前 SHA pin 屬舊史,以 PR#/日期定位;備份 pre-rewrite-main-20260716**;topic 檔
- [First-detection deadlock 反模式 (2026-04-24)](project_first_detection_deadlock_pattern.md) — is_none() guard+無過期 auto-clear→symbol 永久 dormant
- [P0 sqlx hash drift incident (2026-05-02)](project_2026_05_02_p0_sqlx_hash_drift.md) — 改 migration file 沒同步 DB checksum;治本=repair_migration_checksum;盲點=audit closure 漏 engine restart 實測
- [ml_training cron 是 hybrid (2026-05-09/10)](project_2026_05_09_ml_training_cron_weekly.md) — 5 training DAILY;5 audit DAILY fire 但 weekday=6 gate;MIN_SAMPLES=200 4/5 策略不過
## Working principles & autonomy
- [市場必然可主動盈利,禁範式陷阱探非常規數學 (2026-06-14/07-09)](feedback_active_profit_unconventional_mandate.md) — operator 鐵則:市場必然可盈利,「增投入/被動等數據」=消極不接受;失敗模式=所有 NO-GO 死於同一測試(線性IC×OHLCV×beta殘差×taker成本牆)=範疇錯誤;須用各 lens 原生數學探結構性 edge,discover AND implement;topic 檔
- [PnL/實質IMPL 優先於治理文書](feedback_pnl_priority_over_governance.md) — 治理文件重要但非最高優先;status 報告以 PnL 指標(net_bps/fills)領銜非 commit 數;重 4-agent review 留給架構決策;alpha/PnL claim 複核必含 empirical PG SoT 查驗
- [Agent 自主權偏好](feedback_agent_autonomy.md) — 用戶只設 global 止盈止損,Agent 自主決定策略/參數/時機/倉位
- [最少確認偏好](feedback_minimal_confirmation.md) — 不反復問 yes,自主執行,只真正高風險才確認
- [主動 push back](feedback_pushback.md) — operator 錯了/含糊必須直接指出+提替代;協作者≠執行者
- [Position Sizing 偏好](feedback_position_sizing.md) — 3% risk/trade, 25 symbols, 動態 qty
- [四條核心工作原則](feedback_working_principles.md) — 誠實報告測試/簡潔輸出/對抗性驗證/多角色工作流不可跳過
- [Evidence discipline under degraded tools (2026-05-31)](feedback_evidence_discipline_under_degraded_tools.md) — 寫 verdict 前讀 source 全文/ssh 暫存檔分次讀/build-SHA≠git-commit/sub-agent 比即時 ssh 解讀可靠
- [風險參數修改必須限定範圍](feedback_risk_changes_scoped.md) — 只改被要求的參數,不連帶重設
- [模型/effort 三級分級 (2026-08-01)](feedback_model_effort_tiering.md) — operator 裁決:T1 opus/high=PM,E1,E1a,E2,E3,CC,QC,MIT,PA;T2 opus/low=E4,FA,OPS,E5,QA,AI-E,BB,IB;T3 sonnet/medium=TW,R4,A3;thinking 治理改 per-lane effort;subagent 委派需上限非鼓勵;取代兩條已退役鐵則
- [Edge 分析用 demo 不用 paper](feedback_demo_over_paper_for_edge.md) — edge 估計取 demo fills;paper 失真
- [Demo 放寬/Live 收緊 (2026-04-28)](feedback_demo_loose_live_strict_policy.md) — Demo=學習源可放寬;Live 永遠 fail-closed;核心是平衡虧損與盈利
- [MICRO-PROFIT-FIX-1 意圖](feedback_micro_profit_fix_intent.md) — 「有微利就套(net>0)」非 cost_edge_ratio gate
- [LiveDemo 不因 endpoint 降級](feedback_live_no_degradation_by_endpoint.md) — 授權/TTL/風控按 Live 嚴格標準
- [中文輸出偏好](feedback_chinese_output.md) — 對 operator 中文為主;英文留技術名詞/代碼/commit
- [三環境風控 config 獨立](feedback_env_config_independence.md) — paper/live/demo toml 故意分開,禁純衛生合併
- [Shell 指令抗貼上](feedback_shell_paste_safety.md) — 給 operator 的 shell 一律單行;複雜邏輯寫檔案
- [測試 fixture 禁硬編日期 (2026-07-12)](feedback_test_fixture_wallclock_timebomb.md) — 日期腐化型 time-bomb 兩例(decision_packet/agent_governance):commit 當日綠隔日紅;fixture 一律相對時鐘或凍結時鐘;E4 見「無 diff 轉紅」先查日期腐化
- [Rolling-window look-ahead bias (2026-04-24)](feedback_indicator_lookahead_bias.md) — rolling(N).max() 含 current bar 必然 mean-revert;研究必並列 shift(1) 對比
- [V### migration PG dry-run mandatory (2026-05-05/28)](feedback_v_migration_pg_dry_run.md) — 先 Linux PG empirical;double-apply 是 load-bearing gate
- [注釋默認只寫中文 (2026-05-05)](feedback_chinese_only_comments.md) — 新注釋只中文;觸碰時移英文留中文
- [GUI sign-off 必跑 node --check (2026-05-09)](feedback_gui_node_check_sop.md) — brace diff=0 不能代替
- [GitHub Actions cost policy (2026-05-09)](feedback_github_actions_cost.md) — 2000min/月;macOS 10x 僅 PR+週一 cron

## Workflow & roles
- [強制工作鏈與審計模板](feedback_workflow_audit_chain.md) — E1→E2→E4→PM 不可跳過;策略改動加 QA Audit
- [主會話角色:PM+Conductor](feedback_role_definition.md) — 主會話=PM+Conductor;sub-agent 只執行/審查/研究
- [Sub-agent silent-failure 5步審計](feedback_subagent_code_writing_refusal.md) — sub-agent 自報成功可能實際沒做/被 idle-kill;5步查驗(2026-04-07 refuse-pattern 已於 04-18 解除,留史)
- [governance continuation 的 delta 協議 (2026-07-26)](feedback_governance_continuation_delta_protocol.md) — continuation 一輪一次且必須在做完工作後呼叫;空呼叫或 scope 漂移即判 BLOCKED_NO_DELTA 且該 admission 終結,需 release→重建 contract→acquire
- [Meta-doc 用 git commit --only](feedback_git_commit_only_for_metadoc.md) — CLAUDE/TODO/docs/memory 必用 --only;multi-session 下 add+commit 不安全
- [多角色 adversarial review (2026-04-24/05-28)](feedback_multi_role_strategic_review.md) — 關鍵決策派並行獨立 review;grill-me+獨立 agent cross-verify
- [派工前 fetch+查遠端 branch+log-grep ticket (2026-04-24/05-28/06-10)](feedback_fetch_before_dispatch.md) — TODO Banner 可 stale 數天;dispatch prompt 留 NO-OP exit;commit 批次前也 re-fetch(branch 可被並行宣告 SUPERSEDED);救援=detached worktree+cherry-pick;topic 檔
- [IMPL DONE 必走 A3+E2 對抗核驗 (2026-05-09)](feedback_impl_done_adversarial_review.md) — 高風險 IMPL 自評不接受單獨 sign-off

## Code & architecture rules
- [Rust 為唯一交易參數權威](feedback_rust_authoritative_config.md) — GUI 直寫 Rust,Python 僅只讀
- [新代碼必須 Rust 優先](feedback_new_code_rust_first.md) — 新獨立模組 Rust(standalone binary+IPC,非 PyO3),不增 Python 債
- [跨平台兼容性準則](feedback_cross_platform.md) — 隨時可部署 Mac;路徑不硬編碼
- [可調參數禁止假功能](feedback_no_dead_params.md) — 參數必須真實被發現/調整/持久化
- [restart_all --rebuild 範圍](feedback_restart_rebuild_flag_scope.md) — --rebuild 只重建 engine binary(cargo build;PyO3 2026-04-20 已移除)
- [FastAPI Depends × importlib.reload/purge 凍結規則](feedback_fastapi_depends_reload_freeze.md) — ①reload main 後必同步 reload route module 否則 Depends frozen callable→401;②del sys.modules['app.X'] 被 CPython 父包屬性捷徑架空,正解=就地刷新 env 派生態非依賴 del/reload;topic 檔
- [restart bind host safe default (2026-05-09)](feedback_restart_bind_host_default.md) — auto 解析 Tailscale IPv4 否則 loopback;禁 0.0.0.0

## References
- [GitHub main PR merge gates (2026-07-21)](reference_pr_merge_gates.md) — Codex bot auto-review 每 PR 且未解 thread 阻 merge;threads 常是真 P1 要讀+修+resolve;[skip ci] 在 PR HEAD 擋 required check;--merge --match-head-commit;governed pytest 只能 Linux 跑;topic 檔
- [ultracode 全盤審計編排設置 (2026-06-10;07-24 治理版配方)](reference_ultracode_full_audit.md) — openclaw-full-audit.js+conductor skill;默認 report-only;07-24 起=context_artifact 嵌入 runner+沙箱 shim+admission_now_ms;surfaces 勿含 runtime/bybit/ibkr(debt 必炸);配方 topic 檔
- [Remote Access 配置](reference_remote_access.md) — Tailscale: Trading GUI / OpenClaw URLs
- [重啟腳本](reference_restart_script.md) — bash helper_scripts/restart_all.sh
- [外部工具權威邊界+整合入口 (2026-04-29)](feedback_external_tool_authority.md) — current authority=GitHub Issues active,Linear historical/passive unless explicitly reopened;Notion frozen,其餘 declined;看到 declined MCP 不重新評估啟用;[入口清單](reference_external_tools.md)
- ARCH-RC1 統一 Config 契約 → `docs/references/2026-04-15--arch_rc1_unified_config_contract.md`
- [GUI 大修基線備份+設計正本 (2026-07-09/10)](reference_gui_redesign_baseline_2026_07_09.md) — git tag gui-baseline-2026-07-09=回滾錨點;07-10 裁決:玄衡儀認可+雙主題真目標+Phase 0 放行;正本入 docs/execution_plan/gui_redesign/(四規格+tokens.css 雙主題);next=Phase 0 §9 chain;topic 檔

> Archived stale memories: topic 檔全留原地、可按名 recall(archive 守恆)。**2026-07-06 R4**:Project context 63→40,移出 23 條已完結/被取代/低召回 index 行(topic 檔未刪)。早期 Phase 1-era/completed migrations/superseded plans 原已移 `archive/`。**2026-07-09 R4(subagent 逐行核實)**:+3 新軸(profit-first loop/AI-ML 路線圖/IBKR)−3 merge-out(sprint_n0/v58_alpha_pivot/fincept,topic 檔留原地)=Project context 維持 40;修 profit_diagnosis「operator-hand」終態已超越、PyO3 索引(--rebuild/rust-first,PyO3 2026-04-20 移除)、owed V138+V139=已 apply·cron=已復原;索引 2 孤兒(fastapi_depends/pnl_priority);topic 側:paper=archived 非 disabled/gui TradingMode→PipelineKind/layer2 路徑+L2-mesh shipped/README symlink 拓撲/trim 三胖檔(fail_closed_gate 60→33·residual_producer 127→37·aeg 45→36)。**2026-08-01 框架健檢 R4**:heat 條款廢除(MERGE 代理=git log 日期);冷審 06-14 行併入 ultracode 全審弧行(+框架健檢新行=維持 40);24 超限行壓回 ≤250+16 死 SHA pin 清除(filter-repo 遺留);退役 subagent_first/disable_adaptive_thinking 兩鐵則→archive/(model_effort_tiering 取代);ibkr_p1_secret_slot_loader 併入 ibkr 主檔;fincept/ref20/a_group_triage/sprint_n0/v58 五孤兒檔移 archive/;External tool authority section 併入 References。
