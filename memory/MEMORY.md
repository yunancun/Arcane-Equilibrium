# Memory Index

## Project context
- [REF-20 Sprint 1+2+3+4 closure — P6 PRODUCTION CLOSED (2026-05-03)](project_2026_05_03_ref20_sprint1_2_closure.md) — Sprint 1 critical security + schema drift (edf33c0) / Sprint 2 §八 evidence + AMD (aa9343c+5184990) / Sprint 3 Track H Decision Lease retrofit (dbcf845b) + Track I Linux deploy / Sprint 4 closure operator override (0ad79f67) = REF-20 P6 CLOSED；24/25 V3 §12 GREEN
- [2026-05-02 codex 4-day audit chain](project_2026_05_02_codex_4day_audit.md) — 162 codex/operator commits cold review；P1-1 retrofit chain E1×3/E2×3/E4×3 closed (e858ae2 + 6cb1c3b)；.codex/ 治理 = option (a) hint mirror only
- [LIVE-AUTH-WATCHER fix (2026-04-27)](project_live_auth_watcher_event_consumer_spawn.md) — Live 8天 snapshot 停寫；watcher respawn 漏接 event_consumer；has_pipeline_spawner=true 驗；P1 stale-cmd-tx 待修
- [OpenClaw 定位决策](project_openclaw_positioning.md) — OpenClaw Gateway=通信+運維層；Rust openclaw_engine=交易大腦；Python=API橋接+GUI only
- [硬件與存儲基礎設施](project_hardware_constraints.md) — 128GB統一記憶體 LLM~54GB，PG只能用4-8GB，40TB NAS via 10GbE
- [未來 Mac 部署目標](project_mac_deployment_target.md) — Apple Silicon Mac（預計 M5 Ultra/Max）；CI tuple `aarch64-apple-darwin` 必含，linux-arm64 非主路徑
- [ML/DL 自主學習架構](project_ml_dl_learning_architecture.md) — v0.4 Teacher-Student+LightGBM+Optuna+3DL
- [Agent P2 動態 SL/TP](project_agent_p2_dynamic_sl_tp.md) — SL/TP 默認 ATR動態, agent_adjust()可覆蓋, P1 max 為硬頂
- [Agent 工作空間系統](project_agent_workspace.md) — docs/CCAgentWorkSpace/ 下 Agent profile/memory/workspace
- [18-agent runtime 接線 (2026-04-25)](project_18_agent_runtime_wired.md) — srv/.claude/agents/ 18 subagent + srv/.claude/skills/ 24 OpenClaw skill + K-Dense 134；雙端 git sync；@-mention / 自動 delegate / --agent 三 pattern
- [Layer 2 AI推理循環 (2026-04-23 更正)](project_layer2_agent_design.md) — 三層 L0/L1/L2；**先前「H1-H5 全 stub」過期**；真正 gap = Layer 2 自主推理 + ExecutorAgent shadow→live 整合
- [5-Agent + H1-H5 Runtime 狀態 (2026-04-23)](project_5agent_runtime_state.md) — ~4552 行代碼 live shadow；Strategist live / Executor shadow 默認；與 Rust hot path 解耦；G-1 真正工作範圍
- [GUI 寫入面盤點](project_gui_write_paths_inventory.md) — 93 endpoints 分類 + Rust trading_mode 是冷參數陷阱 + fake-success 真假判別
- [Phase 5 reframed (2026-04-12)](project_phase5_promotion_edge_crisis.md) — PNL-FIX-1/2 揭露所有策略 gross 負 edge，Phase 5 cost_gate 工作暫停等策略重做
- [Edge 數據隔離 (2026-04-13)](project_edge_data_isolation.md) — 疑似 paper 噪音污染 JS edge 估計的墮落循環，demo/paper edge 分離計算
- [Live 階段狀態](project_live_stage_status.md) — 2026-04-10 起 Live 階段（Demo API key），所有功能按 Live 標準
- [FA-PHANTOM-1 ROOT CAUSE (2026-04-14)](project_fa_phantom_bug.md) — fast_track 誤用 notional/balance 當 margin_util，90% 閾值＜設計上限 100%，**全策略**系統性被全平；非 funding_arb 專屬
- [G-2 FundingArb 結案 NEGATIVE (2026-04-18)](project_g2_funding_arb_monitor.md) — v2 n=13 提前結案 -36.76 bps / 0勝率；demo funding_arb.active=false；待 R-02 Strategist 重評三參數
- [engine_mode 標籤 live_demo 升級 (2026-04-16)](project_engine_mode_tag_live_demo.md) — Live+LiveDemo endpoint 寫 "live_demo" 非 "live"；歷史 43k 條 "live" 其實是 LiveDemo；ML filter 用 IN ('live','live_demo')
- [Paper 預設關閉 (2026-04-16)](project_paper_pipeline_disabled_by_default.md) — OPENCLAW_ENABLE_PAPER=1 才 spawn；預設 drain task + DISABLED marker；3E-ARCH 結構保留；新增負餘額 Gate 1.6
- [P0-6 RCA + Fix Plan (2026-04-17)](project_p06_rca_and_fix_plan.md) — FUP抑制致bybit_sync死鎖+cost_gate冷啟動死循環；修復：startup triage + natural bootstrap
- [Mac=開發 / Linux=Runtime](project_dev_runtime_split.md) — Mac 只做讀碼/寫碼/RCA；engine/python/PG 全在 Linux；Mac 上 engine not_running 是預期
- [decision_outcomes 不是 dead，但有 2 bug (2026-04-21 Linux 驗證後更正)](project_decision_outcomes_not_dead.md) — Writer 活躍、不可刪；但 (1) outcome_* 100% NULL 是 timeframe 字串格式 ('1' vs '1m') 不一致非 klines 稀疏 (2) engine_mode 100% 'paper' 是 INSERT 漏接線；升級 P1 fix（2 新 TODO）；Mac RCA 盲點：不驗證外部資料就採納「情境 3 reframe」
- [Track P 物理層 runtime live (2026-04-21 T4 + 2026-04-22 V2 SWAP)](project_track_p_runtime_live.md) — T4 接線 `e95c779`（2026-04-21）+ V2 SWAP `306993e`（2026-04-22）完成；Priority 6 改呼 `physical_micro_profit_lock_v2` + `ExitConfig`，v1 linear + `PhysLockConfig` + 8 v1 直測整塊退役；engine lib 1843→1835（Mac + Linux release 均驗）；operator 指示先不部署，engine PID 3954769 仍跑 v1，v2 待下次 `--rebuild` 生效
- [多 CC session memory race (2026-04-23)](project_multi_session_memory_race.md) — memory Write 被隔壁 Mac session 誤 revert；協議 = commit-first / 不認識改動禁 revert / 接手三連加 memory log 檢查 / Mac 被 revert 從 Linux+origin 重建不可重做
- [SSH bridge workflow (2026-04-21)](project_ssh_bridge_workflow.md) — Mac CC 為 SSOT 透過 ssh trade-core 遠端觸發 Linux runtime 任務；取代雙 CC session prompt 同步的浪費；Mac 本地允許 fetch + pull --ff-only（禁 merge/rebase/reset）；授權範圍 + 範例 + Linux CC 剩餘職能
- [LinUCB shadow compare 保留 (2026-04-23)](project_linucb_shadow_compare_retention.md) — Phase 4 子任務 4-06 deferred；`linucb_shadow_compare.py` 保留至 Rust warm-start 實裝或 4-06 降級；同次 audit 已刪 backfill_directive_outcomes
- [First-detection deadlock 反模式 (2026-04-24)](project_first_detection_deadlock_pattern.md) — `is_none()` guard + 無過期 auto-clear → symbol 永久 dormant；bb_breakout FIX-26-DEADLOCK-1 確認；查其他策略
- [TODO 10-Agent Audit 重構 (2026-04-24)](project_2026_04_24_todo_refactor.md) — 10 agent 獨立 audit + PA FIX-PLAN（45 findings/6 工作組/4 wave）+ PM Sign-off；舊 TODO 700→新 328 行；3 大 Verified 發現（edge_estimates 1 cell / PostOnly 反向 / Executor shadow hardcoded）
- [edge_estimator_scheduler 停滯→修復 (2026-04-24)](project_edge_scheduler_stalled.md) — ✅ G1-01 同日 operator commits f32629c/abc85c0 + 02:06 --rebuild；現 187 cells / 59 updated/cycle / mtime <30min；JSON 非 `cells{}` nested 而是 strategy::symbol top-level key
- [Agent 追蹤視圖 MVP shipped (2026-04-28)](project_agent_tracker_mvp_shipped.md) — Learning Cockpit 新「AI 团队工作台」5 卡+feed+shadow/live+budget+governance；A 級 UX；branch feature/agent-tracker-mvp HEAD 884531a 已 push；deploy 用 restart_all --keep-auth（純 Python+JS）
- [funding_arb V2 棄策略路徑 (2026-05-02)](project_funding_arb_v2_deprecation_path.md) — BUSDT -10.12 USDT 後 1B+2A+3C 決策：1B demo active=true 收 EDGE-DIAG-2 樣本 / 2A 中期棄策略（QC delta-neutral 數學不成立 + Bybit demo 無 spot lending）/ 3C TOML 改動 commit a19797d (base_ratio 0.4→0.25 + funding_arb 3% override)
- [P0 sqlx hash drift incident (2026-05-02)](project_2026_05_02_p0_sqlx_hash_drift.md) — audit-p1-1 retrofit (e858ae2/6cb1c3b) 改 V028/V030/V031/V032/V034 file 加 Guard 但 DB checksum 沒同步；3C restart 觸發暴露；治本 = repair_migration_checksum binary (3681f83)；治理盲點 = audit closure SOP 漏 engine restart 實測（cargo test PASS ≠ runtime sqlx migrate 驗證）
- [ml_training_maintenance cron 是 weekly Sunday 非 daily (2026-05-09)](project_2026_05_09_ml_training_cron_weekly.md) — Session N+1 baseline 誤判教訓；5 個 audit job (thompson/optuna/cpcv/dl3/weekly_report) UTC weekday=6 才實質執行；ml_parameter_suggestions 需 fills>=80 是業務 gate 非 IPC bug

## Working principles & autonomy
- [Agent 自主權偏好](feedback_agent_autonomy.md) — 用戶只設global止盈止損，Agent自主決定策略/參數/時機/倉位
- [最少確認偏好](feedback_minimal_confirmation.md) — 不要反復問yes，自主執行，只在真正高風險才確認
- [主動 push back](feedback_pushback.md) — operator 錯了/含糊時必須直接指出+提替代方案，協作者≠執行者
- [Position Sizing 偏好](feedback_position_sizing.md) — 3% risk/trade, 25 symbols, 動態qty
- [四條核心工作原則](feedback_working_principles.md) — 誠實報告測試/簡潔輸出/對抗性驗證/多角色工作流不可跳過
- [風險參數修改必須限定範圍](feedback_risk_changes_scoped.md) — 只改被要求的參數，不連帶重設
- [關閉 Adaptive Thinking](feedback_disable_adaptive_thinking.md) — 不使用延伸思考模式，直接輸出，Operator 明確要求
- [Edge 分析用 demo 不用 paper](feedback_demo_over_paper_for_edge.md) — 累積/驗證/edge 估計取 demo fills；paper 失真無參考價值
- [Demo 放寬 / Live 收緊政策 (2026-04-28)](feedback_demo_loose_live_strict_policy.md) — Demo 是學習資料源可放寬 cost_gate；Live 永遠 fail-closed；核心是「平衡虧損與盈利」非「一味保守」；EDGE-DIAG-2 確立決策啟發式 + 反模式
- [MICRO-PROFIT-FIX-1 設計意圖](feedback_micro_profit_fix_intent.md) — 語意應為「有微利就套（net>0）」，不是「cost_edge_ratio gate 下是否套現」
- [LiveDemo 不因 endpoint 降級](feedback_live_no_degradation_by_endpoint.md) — LiveDemo 是 Live 管線走 demo endpoint，目的是測 live 可靠性；authorization/TTL/風控門控須按 Live 嚴格標準，不得降級
- [中文輸出偏好](feedback_chinese_output.md) — 面向 operator 的對話輸出以中文為主（2026-04-15）；英文只留技術名詞/代碼/commit
- [三環境風控 config 獨立](feedback_env_config_independence.md) — paper/live/demo risk_config*.toml 故意分開，禁「純衛生」合併（2026-04-19）
- [Shell 指令必須抗貼上](feedback_shell_paste_safety.md) — 給 operator 手貼的 shell 一律單行 one-liner，禁 heredoc / 多行 for / 複雜變數注引號；複雜邏輯寫檔案（2026-04-21）
- [Rolling-window breach look-ahead bias (2026-04-24)](feedback_indicator_lookahead_bias.md) — `rolling(N).max()` 含 current bar → breach=「current 是 N-bar max」必然 mean-revert；任何 sweep/研究必並列 leak-free shift(1) 對比
- [V### migration PG dry-run mandatory (2026-05-05)](feedback_v_migration_pg_dry_run.md) — Mac mock pytest + static review cannot catch PG runtime semantic (PL/pgSQL constraints, empirical reflection function output, schema drift); V055 5-round loop 教訓：必先 Linux PG empirical query 再 E1 IMPL 設計
- [注釋默認只寫中文 (2026-05-05)](feedback_chinese_only_comments.md) — 新代碼注釋默認只寫中文（廢除舊 bilingual mandate）；原有中英對照不主動清，修改時移除英文只保留中文；E2 不再要求英文版；token + LOC 成本顯著降低
- [GUI sign-off SOP 必跑 node --check (2026-05-09)](feedback_gui_node_check_sop.md) — 前端 JS / inline-JS 變動 sign-off 強制 `node --check`；靜態 brace/paren/bracket diff = 0 不能代替；W-AUDIT-7c Round 1 governance-tab.js lexical scope shadow 證明 brace count 是盲區
- [GitHub Actions cost policy (2026-05-09)](feedback_github_actions_cost.md) — Private repo 2000min/月免費；macOS 10x 倍率；macOS 不再 push-trigger，僅 PR + 週一 cron；同步寫入 `.codex/MEMORY.md`

## Workflow & roles
- [強制工作鏈與審計模板](feedback_workflow_audit_chain.md) — E1→E2→E4→PM 不可跳過；策略改動加 QA Audit；L1/L2/L3 分級模板
- [主會話角色：PM+Conductor](feedback_role_definition.md) — 主會話=PM+Conductor合一，sub-agent只做執行/審查/研究
- [強制先評估 sub-agent 拆分](feedback_subagent_first.md) — 收到任務先思考能否拆成後台並行 sub-agent
- [Sub-agent 可寫碼（2026-04-18 驗證通過）](feedback_subagent_code_writing_refusal.md) — 2026-04-07 refuse pattern 已解除，2/2 probe 成功；E1 可派並行 sub-agent 寫碼
- [Meta-doc 改動用 git commit --only 隔絕 index race](feedback_git_commit_only_for_metadoc.md) — CLAUDE.md/TODO.md/docs/memory 等 meta-doc 必用 `git commit --only <file>`；multi-session 下 `git add + commit` 不安全（2026-04-23 同 session 吸收 operator WIP 兩次）
- [多角色 adversarial review (2026-04-24)](feedback_multi_role_strategic_review.md) — 關鍵決策派 QC+FA+FM+PM 並行獨立 review；實證 EDGE-DIAG-1 Phase 2 catch 3 個 unique blind spots
- [派 sub-agent 前 fetch + 查遠端 branch (2026-04-24)](feedback_fetch_before_dispatch.md) — Multi-agent 派發前必 `git fetch` + `git branch -r | grep <topic>`；G6-01 被重派教訓（隔壁已開 feature branch 做完）
- [Sub-agent IMPL DONE 必走 A3+E2 對抗性核驗 (2026-05-09)](feedback_impl_done_adversarial_review.md) — 高風險 IMPL（GUI / IPC / 寫操作 / 共用 helper）sub-agent 自評 IMPL DONE 不接受單獨 sign-off；強制派 A3+E2 並行核驗；E4 regression 不能取代；W-AUDIT-7c 三方獨立 catch governance-tab.js SyntaxError 救 prod GUI 案例

## Code & architecture rules
- [Rust 為唯一交易參數權威](feedback_rust_authoritative_config.md) — 所有交易/風控/模型參數GUI直寫Rust，Python僅只讀
- [新代碼必須 Rust 優先](feedback_new_code_rust_first.md) — 新獨立模組用 Rust+PyO3 寫，不增加 Python 遷移債務
- [跨平台兼容性準則](feedback_cross_platform.md) — 必須隨時可部署 Mac，路徑不硬編碼/LLM抽象/服務可遷移
- [可調參數禁止假功能](feedback_no_dead_params.md) — Agent可調參數必須真實被發現/調整/持久化
- [restart_all --rebuild 範圍](feedback_restart_rebuild_flag_scope.md) — 2026-04-14 後 --rebuild 同時重建 engine binary + PyO3；部署 Rust fix 直接 --rebuild 即可
- [restart_all.sh bind host safe tailnet default (2026-05-09)](feedback_restart_bind_host_default.md) — ssh non-interactive 不讀 .bashrc/.profile；script 層用 auto 解析 Tailscale IPv4，否則 loopback；禁止 `0.0.0.0`

## References
- [Remote Access 配置](reference_remote_access.md) — Tailscale: Trading GUI / OpenClaw URLs
- [重啟腳本](reference_restart_script.md) — `bash helper_scripts/restart_all.sh` 一鍵重啟引擎+API
- [外部整合工具入口 (2026-04-29)](reference_external_tools.md) — **Linear-only active**；Notion frozen 不維護；Drive passive；Coupler/Slack/MotherDuck declined；完整 SOP CLAUDE.md §十二
- ARCH-RC1 統一 Config 契約（3-Config + StrategyParams，ArcSwap 熱重載）→ `docs/references/2026-04-15--arch_rc1_unified_config_contract.md`（2026-04-15 遷出記憶庫）

## External tool authority
- [外部工具權威邊界 (2026-04-29)](feedback_external_tool_authority.md) — **Linear-only active** posture；Notion frozen / Drive passive / Coupler+Slack+MotherDuck declined；看到 declined MCP 不要重新評估啟用

> Archived stale memories moved to `archive/` (Phase 1-era / completed migrations / superseded plans / merged originals).
