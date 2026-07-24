# Memory Index

> 索引條目一行 ≤250 字;細節在 topic 檔(超長舊條目已於 2026-06-10 全文歸檔進各 topic 檔的 `[index-archive]` 節)。
> 治理(2026-06-11 起,R4 巡檢):Project context 索引 ≤40 條,超限新增前必先 MERGE(優先級:主題重疊>敘事弧相同>heat 最低/最舊已完結;archive 守恆);topic 檔 frontmatter 可選 `heat:`(被召回/引用 +1,合併取 sum);被推翻的結論不原地改寫 → topic 檔「演變軌跡」節(日期+轉變+原因+證據 SHA)。

## Project context
- [reconcile Path B advisory-first 弧 (2026-07-12)](project_2026_07_12_reconcile_pathb_arc.md) — 手動對賬鈕三層壞+escalation 三重死→Path B 建真兩側 demo↔api-demo:v1`c2cb45fc5`+v2`497ebb4b2`(引擎 dust-freeze+orders/fills scope)source-landed,advisory cap 永不 freeze(runtime 實證阻過早 auth-freeze),arming 待 Phase 2(engine rebuild+operator 清 dust+shadow MATCH+CC audited diff);**unit-env 漂移家族:07-12 API 已修(PID3536174;07-14 23:55 起 durable user unit openclaw-trading-api.service 接管=enabled+linger+var env+journald,api.log 停更,topic 檔 07-15 節);07-15 watchdog unit 零 PG env→audit 直寫 chronic skip(帳由 bridge 兜住未丟),修上 main PR#22(unit 模板+resolve_dsn 第4步推導備援),runtime 一行 apply 待 operator;同日揭 trade-core OOM 風暴 P0(cron python 全量物化 79-85GB 單進程/kernel 16 kills/引擎被殺;**疊加機 flock PR#27+OOM-victim 自標 PR#31 both source-landed 且 Linux 已 pull 部署,flock 反疊加 runtime 鐵證=SKIP log**;引擎 adj=200 降負需 operator root=user manager DefaultOOMScoreAdjust,MemoryMax 不可安全定值→真解 P2 streaming 代碼修;家族 12+20 檔遷移+跨週期驗實例≤1 待 follow-up/operator)**;UNKNOWN-1 定案 engine=demo 對 pair;reconcile 抓到真引擎 intraday dust-evict bug;logrotate drift 哨兵 [95] 上線 PR#24+manifest 治理入口 PR#30 收口刷新窗漏洞(installer 兩段式 receipt,[95] 只認 applied:true;trade-core 已 apply,PASS)(07-15);**07-16 深夜~07-17 P2 streaming 修復波上 main(p0a-p0d:PR#43/44/46/50/52/54/56——sealed-horizon 全量物化→candidate-scoped 投影+streaming JSONL 已拆;p0-oom-* 4 支線 in-flight)**;topic 檔
- [ultracode 全審弧 (07-11 修復部署+07-24 run0)](project_2026_07_11_ultracode_audit_remediation.md) — 07-11:4C/2R/8seam,9項`6b7ad5ca8`上main+引擎重部署,6/7/Q4併main(V157 pending);**07-24 run0(`wf_749b4f8c-2ea`,head=runtime=`7d78765a2`):9C/1L/3D/1R+5seam+92債,首要=S1 P1 fix branch `aiml-s1-closure-p1p2-fixes` 未併(併前禁 SSHSIG)+TODO落後3PR;adaptive子集會漏4/9 confirmed→`adaptive_shadow`默認不可退;QC:PROFIT-1仍在+DSR缺√Var縮放=K≥2必block;正本報告+decision_view 在 PM reports 2026-07-24**;topic檔
- [profit-first 自主 loop(承 maker-nogo 拒「剩 operator-hand」)(2026-07-08)](project_2026_07_08_profit_first_autonomy_loop.md) — TradeBot 自跑 discover→admit→execute→review→learn(spec `docs/agents/profit-first-autonomy-loop.md`);**07-09 R3 推翻候選統計**(NEAR 5058=2 distinct entry 偽複製)→ **07-10 dedup+n_eff 管線上線 `1a3ecdd57`,重跑裁決候選榜=零合格**(7/7 VETO,gate=淨止損)——loop 回 discover 段等真候選;零 order/fill proof;無 live/無降 Cost Gate;演變軌跡在 topic 檔
- [AI/ML roadmap→AIML-V2 S0 adopted](project_2026_07_21_aiml_s0_adoption_gate.md) — 07-21 source gate+Codex 3 P1 全修；07-22 Linux 發 `PROGRAM_ADOPTED`（PR#106-108,275/275）；仍 source-only、九 authority=false，非 runtime/trading；topic 內鏈保留 WP1-WP7 舊弧
- [IBKR stock/ETF full live-capability 軸 (2026-06-29~07-16)](project_2026_07_08_ibkr_stock_etf_readonly.md) — AMD-2026-07-11-01 Accepted=development 全授權+活化分離(margin/short/options/cfd/transfer 永久 denied;真實接觸需 envelope+Operator 活化紀錄);**W0-W4+W-CI 全 DONE 且 R8(07-16)8 鏡頭對抗審計 CONFIRMED**(INV-1 HOLDS=production 零 permit 放行路徑;測試鏈 211/74+287/34/2/9/201 本地複現全綠);**工程正本=repo 根 `IBKR_TODO.md` v2(§5.5 日誌 R9-R30,工期 2.5-4 週)+ loop 協議 v2(並行 manifest/記帳 checklist/反空轉/死亡三分類)+ 帳本 PROGRESS.md R0-R8,校準 PR#45(新史 merge `e67e5ac2c`)**;**W5-S0∥S1 已收口(07-16 R9/R10,PR#48 `c48689acb`/PR#49 `dbc234bbd`(新史):CI 三洞閉+E3-F1/F2 CLOSED+四 row contracts,IB 現勘全 CONFIRMED)**,下一=R11 W5-S2(消化;S3 前置=IB 哨兵/exec_time 兩 blocking)→W8a/W9a carve(EA1-EA3 前置=W3-W5+W8a+W9a);**D2 已裁採用+澄清 #3 acknowledged(07-16,PR#47 新史 `70e802ead`)**=W5+W8a+W9a 齊即開 EA1-EA4(每步仍逐一活化);runtime 教科書式 dormant(07-16 復核);教訓:Actions spending 耗盡=全分支 runner='' 假死非代碼問題;topic 檔含演變軌跡
- [maker-first 做市執行軸 fill_sim 雙窗判 NO-GO (2026-07-06)](project_2026_07_06_maker_first_nogo.md) — 承 profit 弧補執行軸。fill_sim 3400萬筆L1雙窗**0/172格淨正**,break-even需maker≤0.4bps(VIP0是+2bps費用非rebate)=infra-tier鎖。**不賺錢=無方向alpha+執行edge被費用鎖,非缺AI**;真dormant=M12自適應router(成本削減非alpha)。仍開:新上市寬價差niche/infra-tier。SHA `5d1622994`;細節topic檔
- [全盤冷酷審計 ultracode 12軸+seam (2026-06-14)](project_2026_06_14_cold_audit.md) — 凍結 `976d420e`;無P0/CRITICAL,live 5-gate實證fail-closed;confirmed P1:AUTH-1 live RiskConfig繞5-gate(**07-06已修**見maker-nogo topic PA節)/PROFIT-1 cost_gate雙重扣成本/SCHEMA-1無column contract test/PERF三項。教訓:Workflow args必傳真JSON物件非字串;細節在topic檔
- [盈利研判 R3+修復包全上線 (2026-07-09~10;承 R2 06-13)](project_2026_07_09_profit_diagnosis_roi_map.md) — 30d true net **−406 USDT** fee-dominated(live=0);修復包 operator 批 1/2/3 後三端同步 `1a3ecdd57`:**71k 重跑=FALSE_KILL_HAMMERED**(7/7 VETO/0 翻正,gate=淨止損,候選榜零合格)/PROFIT-1 證實但追認不修(硬邊界優先)/E2E-1 真 call 達成 $0.0149 後 L2 復原 disabled(fence-sink follow-up)/Gate-B auto-capture 活化 cap=5/funding 結算窗 event study REJECT;**07-10 #2/#3 研究輪雙 descoped-GO**:#2 僅作 R1 重放儀器(cell 拯救死:60d net −7.20 符號翻轉、markout n=1、bb_rev 無 maker knob;死線 07-19=L1 21d 滾動)/#3 僅作 $0 研究管線非 PnL 線(P(GO)≤15%、breadth=唯一槓桿、demo cap 76h 截 h=14d);未動:執行衛生/TradFi×IBKR;R2 NO-GO 作歷史成立;topic 檔
- [五 repo 借用評估+P0/P1/P2 全落地 (2026-06-11~12)](project_2026_06_11_five_repo_subagent_token_eval.md) — P0/P1 `4587f65f`+P2 `131bd560..5e3820f3`:rtk hook/SessionStart路由/四態契約;L2 PG記憶dormant+告警sink+BB哨兵+polymarket軸(flag-OFF)。owed(operator-gated):rtk CLA/bge-m3(V138+V139 已apply→PG head=150;cron 已復原34條);細節topic檔
- [BG subagent「卡死」根因三層+SOP shipped (2026-06-11)](project_2026_06_11_bg_subagent_idle_kill_rootcause.md) — ①desktop 900s idle-pause殺光in-flight BG agent不可復活;②唯一liveness信號=subagents/agent-*.jsonl mtime;③限額API單往返5m38s假死。SOP shipped `558ded55`(駐留等收/TaskStop三前置/續作棒)+agent-wave workflow(resumeFromRunId零浪費重放);Linux repo=`~/BybitOpenClaw/srv`;細節在topic檔
- [L2 P4 全鏈 shipped+P2p 哨兵 shipped (2026-06-10~11)](project_2026_06_10_l2_p4_ratify_p2p_shipped.md) — P4 merged main `ddaafda1`(dormant三重關,MIT+QC+三線E1→E2→E4 GREEN);V138 prod apply 已完成(PG head=150)。教訓:migration/healthcheck號=git看不見的全局命名空間。P2p merge `661699e5`owed=Telegram creds;watchdog告警仍靜默no-op;細節在topic檔
- [L2 Mesh P1-P3b DEPLOYED+owed 五項 DONE (2026-06-10)](project_2026_06_08_l2_d3_phase1_green.md) — **current authority 2026-07-05**:active L2 tail 在 `TODO.md` `P1-L2-ADVISORY-MESH-E2E-1`;E2E-1 需 operator 批准一次 true model call 後復原 disabled,不得視為全閉;細節在topic檔
- [幽靈倉位 fill 記帳 bug 修復+部署 (2026-06-08)](project_2026_06_08_phantom_position_fill_fix.md) — demo TON 幻影倉根因=PositionUpdate/Fill 無序雙寫競態;修=apply_fill 唯一 mutator+reduce-only fail-closed+reconciler 幻影偵測軸;全鏈綠+原子部署(commit 74b2e264→origin bdf15e4f);剩:告警僅 DB 可查/LiveDemo 缺 authorization.json(既有)
- [Residual alpha producer 全完成+部署+flag-on (2026-06-05~08)](project_2026_06_05_residual_producer_build.md) — PART1-3部署:producer+signal_spec+hidden_oos sealer+mlde hook+replay bridge,06-07上main `OPENCLAW_RESIDUAL_ALPHA_PRODUCER=1` cron daily 03:17;PART4 gap-closure deployed flag-OFF,活化=operator決策;細節在topic檔
- [外部框架借鑒+代碼級自審 (2026-06-04)](project_2026_06_04_external_framework_audit_and_self_audit.md) — 評 RD-Agent/AlphaAgent/QuantaAlpha;自審揭 overclaim:beta_quant.py 是 /tmp 蒸發腳本、新策略不過 DSR/PBO;定位=上游發現弱下游治理強,grep beta=0;非-OHLCV 特徵已 live 可離線搜;RevolutX 僅借 orderLinkId ~5行
- [被攔信號反事實+H2 cascade fade 雙 NO-GO (2026-06-03)](project_2026_06_03_blocked_signal_and_cascade_fade_nogo.md) — 兩線同根因 down-beta 偽裝:blocked grid_short demeaned-α≈0、cascade fade 280 事件全 |t|<1.3;BTC 17d −13.9% regime 任何短 bias=趨勢 beta→強制 beta 中性化;Dream「噪音公式」指控證偽=過度警報(Option A cd01eb92);pg_stat n_live_tup 不可靠須 count(*)
- [AEG trend/listing infra 部署 (2026-06-02)](project_2026_06_02_aeg_trend_listing_infra_deployed.md) — V125 alpha 儲存+daily-kline backfill 14505 根+Gate-B 隔離 listing 探針(R-0 zero-leak)三端同步 c1c017b0;24h 真捕捉 operator-timed;教訓:post-deploy 真連線 smoke>mock(抓 parquet COPY-TO-? 崩潰)
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
- [18-agent runtime 接線 (2026-04-25)](project_18_agent_runtime_wired.md) — srv/.claude/agents 18 subagent+25 skill;根目錄 .claude=symlink→srv/.claude(單副本,無雙端)
- [Layer 2 AI 推理循環 (2026-04-23 更正)](project_layer2_agent_design.md) — L0/L1/L2 三層;真 gap=L2 自主推理+Executor shadow→live
- [GUI 寫入面盤點](project_gui_write_paths_inventory.md) — 93 endpoints;Rust trading_mode 冷參數陷阱;fake-success 判別
- [Edge 數據隔離 (2026-04-13)](project_edge_data_isolation.md) — paper 噪音污染 edge 估計;demo/paper 分離計算
- [Live 階段狀態](project_live_stage_status.md) — 2026-04-10 起 Live 階段(Demo API key),功能按 Live 標準
- [engine_mode 標籤 live_demo (2026-04-16)](project_engine_mode_tag_live_demo.md) — Live+LiveDemo 寫 "live_demo";歷史 43k "live" 實為 LiveDemo;ML filter IN ('live','live_demo')
- [Paper 預設關閉 (2026-04-16)](project_paper_pipeline_disabled_by_default.md) — OPENCLAW_ENABLE_PAPER=1 才 spawn;Gate 1.6 負餘額
- [Mac=開發/Linux=Runtime](project_dev_runtime_split.md) — Mac 讀寫碼/RCA;engine/PG 全 Linux;Mac engine not_running 預期
- [多 CC session memory race (2026-04-23)](project_multi_session_memory_race.md) — 協議=commit-first/不認識改動禁 revert/被 revert 從 Linux+origin 重建
- [SSH bridge workflow (2026-04-21;07-15/07-16 演變)](project_ssh_bridge_workflow.md) — Mac SSOT 經 ssh trade-core 觸發 Linux;Mac 允許 fetch+pull --ff-only(禁 merge/rebase/reset);**2026-07-14 起 main 直推被 pre-push hook 禁:改走 feature branch(`HEAD:refs/heads/agent/<topic>`)→exact-head PR→gh merge**(實證 PR#17);07-16 CI 成本收斂「非必要不CI」:push-to-main path-filter(before...sha 精確 diff,棄 --all)+rust-cache 四 job(ci.yml;07-16 R8 審計核正,21b6ca66a[舊 84b5a3d90] commit body 明文四);**07-16 23:46 main 全史 git-filter-repo 重寫(secret purge:3 憑證 revoke/rotate+gateway/Grafana 退役 PR#53,attest PR#55)——重寫前一切 SHA pin 屬舊史,以 PR#/日期/subject 定位;舊史備份 ref `pre-rewrite-main-20260716`(Mac+Linux)**
- [First-detection deadlock 反模式 (2026-04-24)](project_first_detection_deadlock_pattern.md) — is_none() guard+無過期 auto-clear→symbol 永久 dormant
- [P0 sqlx hash drift incident (2026-05-02)](project_2026_05_02_p0_sqlx_hash_drift.md) — 改 migration file 沒同步 DB checksum;治本=repair_migration_checksum;盲點=audit closure 漏 engine restart 實測
- [ml_training cron 是 hybrid (2026-05-09/10)](project_2026_05_09_ml_training_cron_weekly.md) — 5 training DAILY;5 audit DAILY fire 但 weekday=6 gate;MIN_SAMPLES=200 4/5 策略不過
## Working principles & autonomy
- [市場必然可主動盈利,禁範式陷阱探非常規數學 (2026-06-14/07-09)](feedback_active_profit_unconventional_mandate.md) — operator 鐵則:市場必然可盈利,「增投入/被動等數據」=消極不接受。失敗模式=所有 NO-GO 死於同一測試(線性IC×OHLCV×beta殘差×taker成本牆=只為方向taker預測)→誤判整個市場(範疇錯誤)。須用各 lens 原生數學(做市/統計套利/Hawkes/資訊論/delta-carry/跨所)探結構性·機械性 edge,discover AND implement;07-09 姿態再強化:挫折→換思路+外部學習,audit 永不空手(unlock+learn+EXT 軸);細節在topic檔
- [PnL/實質IMPL 優先於治理文書](feedback_pnl_priority_over_governance.md) — 治理文件重要但非最高優先;status 報告以 PnL 指標(net_bps/fills)領銜非 commit 數;重 4-agent review 留給架構決策;alpha/PnL claim 複核必含 empirical PG SoT 查驗
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
- [測試 fixture 禁硬編日期 (2026-07-12)](feedback_test_fixture_wallclock_timebomb.md) — 日期腐化型 time-bomb 兩例(decision_packet/agent_governance):commit 當日綠隔日紅;fixture 一律相對時鐘或凍結時鐘;E4 見「無 diff 轉紅」先查日期腐化
- [Rolling-window look-ahead bias (2026-04-24)](feedback_indicator_lookahead_bias.md) — rolling(N).max() 含 current bar 必然 mean-revert;研究必並列 shift(1) 對比
- [V### migration PG dry-run mandatory (2026-05-05/28)](feedback_v_migration_pg_dry_run.md) — 先 Linux PG empirical;double-apply 是 load-bearing gate
- [注釋默認只寫中文 (2026-05-05)](feedback_chinese_only_comments.md) — 新注釋只中文;觸碰時移英文留中文
- [GUI sign-off 必跑 node --check (2026-05-09)](feedback_gui_node_check_sop.md) — brace diff=0 不能代替
- [GitHub Actions cost policy (2026-05-09)](feedback_github_actions_cost.md) — 2000min/月;macOS 10x 僅 PR+週一 cron

## Workflow & roles
- [強制工作鏈與審計模板](feedback_workflow_audit_chain.md) — E1→E2→E4→PM 不可跳過;策略改動加 QA Audit
- [主會話角色:PM+Conductor](feedback_role_definition.md) — 主會話=PM+Conductor;sub-agent 只執行/審查/研究
- [強制先評估 sub-agent 拆分](feedback_subagent_first.md) — 收任務先想能否拆後台並行
- [Sub-agent silent-failure 5步審計](feedback_subagent_code_writing_refusal.md) — sub-agent 自報成功可能實際沒做/被 idle-kill;5步查驗(2026-04-07 refuse-pattern 已於 04-18 解除,留史)
- [Meta-doc 用 git commit --only](feedback_git_commit_only_for_metadoc.md) — CLAUDE/TODO/docs/memory 必用 --only;multi-session 下 add+commit 不安全
- [多角色 adversarial review (2026-04-24/05-28)](feedback_multi_role_strategic_review.md) — 關鍵決策派並行獨立 review;grill-me+獨立 agent cross-verify
- [派工前 fetch+查遠端 branch+log-grep ticket (2026-04-24/05-28/06-10)](feedback_fetch_before_dispatch.md) — TODO Banner 可 stale 數天;dispatch prompt 留 NO-OP exit;commit 批次前也 re-fetch(branch 可被並行 session 中途宣告 SUPERSEDED),救援=detached worktree+cherry-pick+push HEAD:main
- [IMPL DONE 必走 A3+E2 對抗核驗 (2026-05-09)](feedback_impl_done_adversarial_review.md) — 高風險 IMPL 自評不接受單獨 sign-off

## Code & architecture rules
- [Rust 為唯一交易參數權威](feedback_rust_authoritative_config.md) — GUI 直寫 Rust,Python 僅只讀
- [新代碼必須 Rust 優先](feedback_new_code_rust_first.md) — 新獨立模組 Rust(standalone binary+IPC,非 PyO3),不增 Python 債
- [跨平台兼容性準則](feedback_cross_platform.md) — 隨時可部署 Mac;路徑不硬編碼
- [可調參數禁止假功能](feedback_no_dead_params.md) — 參數必須真實被發現/調整/持久化
- [restart_all --rebuild 範圍](feedback_restart_rebuild_flag_scope.md) — --rebuild 只重建 engine binary(cargo build;PyO3 2026-04-20 已移除)
- [FastAPI Depends × importlib.reload/purge 凍結規則](feedback_fastapi_depends_reload_freeze.md) — 兩陷阱:①reload main 後必同步 reload route module 否則 Depends(current_actor) frozen callable 指舊 fn→401;②`del sys.modules['app.X']` 被 CPython 父包屬性捷徑架空、清理形同虛設(2026-07-10 `dbc6a936c`),正解=就地刷新 env 派生態(settings/STORE 重建)非依賴 del/reload
- [restart bind host safe default (2026-05-09)](feedback_restart_bind_host_default.md) — auto 解析 Tailscale IPv4 否則 loopback;禁 0.0.0.0

## References
- [GitHub main PR merge gates (2026-07-21)](reference_pr_merge_gates.md) — Codex bot(`chatgpt-codex-connector`)auto-review 每 PR 且 threads 阻 merge(「base branch policy prohibits」常=未解 thread/pending check,非真 block);Codex threads 常是真 P1 要讀+修+resolve;`[skip ci]` 在 PR HEAD commit 會擋 required check;`--admin` 被禁用 `--merge --match-head-commit`;governed capture-command 在 Mac 跑不了 pytest(HOME 隔離)→ 測試 attestation 需 Linux
- [ultracode 全盤審計編排設置 (2026-06-10;07-24 治理版配方)](reference_ultracode_full_audit.md) — saved workflow `openclaw-full-audit.js`+conductor skill;默認 report-only;**07-24 起調用=compiler 產 context_artifact 嵌入 scriptPath runner+沙箱 shim(無 crypto/TextEncoder/時鐘)+admission_now_ms;surfaces 勿含 runtime/bybit/ibkr 家族(debt 必炸);配方全文在 topic 檔**
- [Remote Access 配置](reference_remote_access.md) — Tailscale: Trading GUI / OpenClaw URLs
- [重啟腳本](reference_restart_script.md) — bash helper_scripts/restart_all.sh
- [外部整合工具入口 (2026-04-29)](reference_external_tools.md) — **superseded posture**; current authority=GitHub Issues active, Linear historical/passive unless explicitly reopened;Notion frozen;其餘 declined
- ARCH-RC1 統一 Config 契約 → `docs/references/2026-04-15--arch_rc1_unified_config_contract.md`
- [GUI 大修基線備份+設計正本 (2026-07-09/10)](reference_gui_redesign_baseline_2026_07_09.md) — git tag `gui-baseline-2026-07-09`(@d077949fc)=回滾錨點;**2026-07-10 裁決:玄衡儀主張認可(暖調近黑+青銅+朱印+衡樑)+雙主題真目標+Phase 0 放行**;正本全入 repo `docs/execution_plan/gui_redesign/`(working doc+四規格+tokens.css 雙主題+Live 樣品,`a35ec287b`);next=Phase 0 按 §9 role chain 派發;IBKR 交接 prompt

## External tool authority
- [外部工具權威邊界 (2026-04-29)](feedback_external_tool_authority.md) — **superseded posture**; current authority=GitHub Issues active, Linear historical/passive unless explicitly reopened;看到 declined MCP 不重新評估啟用

> Archived stale memories: topic 檔全留原地、可按名 recall(archive 守恆)。**2026-07-06 R4**:Project context 63→40,移出 23 條已完結/被取代/低召回 index 行(topic 檔未刪)。早期 Phase 1-era/completed migrations/superseded plans 原已移 `archive/`。**2026-07-09 R4(subagent 逐行核實)**:+3 新軸(profit-first loop/AI-ML 路線圖/IBKR)−3 merge-out(sprint_n0/v58_alpha_pivot/fincept,topic 檔留原地)=Project context 維持 40;修 profit_diagnosis「operator-hand」終態已超越、PyO3 索引(--rebuild/rust-first,PyO3 2026-04-20 移除)、owed V138+V139=已 apply·cron=已復原;索引 2 孤兒(fastapi_depends/pnl_priority);topic 側:paper=archived 非 disabled/gui TradingMode→PipelineKind/layer2 路徑+L2-mesh shipped/README symlink 拓撲/trim 三胖檔(fail_closed_gate 60→33·residual_producer 127→37·aeg 45→36)。
