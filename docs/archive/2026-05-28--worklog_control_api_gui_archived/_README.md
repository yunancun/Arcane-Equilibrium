# Archive: worklog_control_api_gui — 2026-05-28

> **歸檔日**：2026-05-28
> **來源**：`docs/worklogs/control_api_gui/`（50 檔 = 45 .md + 5 .txt）
> **歸檔理由**：Control API + GUI Operator Console 開發日誌（2026-03-25~04-02），含 Phase 1/2/3 完整工程日誌 + wave4/wave7/wave8 里程碑。Phase 1-3 全 commit 已落入 git history；GUI 當前 SSOT 在 `docs/execution_plan/2026-05-06--gui_openclaw_control_console_plan.md` + `srv/services/control_api/`。30+ 天無讀寫（CLAUDE_REFERENCE.md L83-88 仍引 6 檔，路徑由 P2-8 改寫）。
> **Sign-off**：PM proposal + PA tech plan（同 phase 2 系列）
> **內檔 self-ref 處理**：`2026-03-27--layer2_ai_engine_design_session.md` L115-116 自我引用 + 引同目錄 brainstorm 檔；mv 後檔本身在本 archive，但檔內字串仍是舊路徑——由 P2-8 改寫為相對路徑（或同目錄 anchor）。

## 原 README L916-968 對應段

### worklogs/control_api_gui/ — Control API + GUI 开发日志（2026-03-25 ~ 2026-04-02）

| 文件 | 内容 |
|------|------|
| `2026-03-25--jk收口_单独接手文件.txt` | J-K 收口完成版接手文件 |
| `2026-03-25--jk收口_完整工程记录.txt` | J-K 收口完成版完整工程记录 |
| `2026-03-25--g到k详细复盘与程序总表.txt` | G~K 详细复盘与程序总表 |
| `2026-03-25--新对话工作方式与带入文件清单.txt` | 新对话工作方式与带入文件清单 |
| `2026-03-25--新对话启动prompt.txt` | 新对话启动 Prompt |
| `2026-03-26--api_gui_全量工程报告.md` | API + GUI 全量工程报告 |
| `2026-03-26--paper_trading_engine_完整工程日志.md` | Paper Trading Engine 完整工程日志（引擎核心 + 14 路由 + GUI + 43 测试） |
| `2026-03-26--beta_pipeline_shadow_decision_metrics.md` | Beta 管线完善：实时行情 + 自动桥接 + 影子决策管线 + 性能指标（248 测试，73 路由） |
| `2026-03-26--brainstorm_openclaw_agent_architecture.md` | Brainstorm 留档：OpenClaw 定位（通信层非大脑）+ Agent 智能化架构讨论 |
| `2026-03-26--openclaw_fusion_console_systemd_服务化.md` | OpenClaw 融合 + 统一控制台 + systemd 服务化 + 远程访问方案规划 |
| `2026-03-26--brainstorm_layer2_ai_reasoning_engine.md` | Brainstorm：Layer 2 AI 推理引擎设计（三层架构 + Agent 循环 + 工具箱 + 成本控制） |
| `2026-03-27--layer2_ai_engine_design_session.md` | Layer 2 设计工作记录：搜索 Provider 方案调研决策 + 4 层降级体系 + 模型升级判断 + 自适应预算 + PnL 归因 |
| `2026-03-27--phase1_risk_framework_implementation.md` | Phase 1 早期工程日志：S1-S5 安全修复 + 三层 P0/P1/P2 风控 + 8 路由（327→369） |
| `2026-03-27--phase1_complete_engineering_log.md` | Phase 1 中期工程日志（第 1-2 轮审核后） |
| `2026-03-27--phase1_final_audited_engineering_log.md` | ★ Phase 1 最终审核版：4 轮审核 + 25 问题修复 + 405 测试 + 93 路由 |
| `2026-03-27--pre_phase1_audit_fixes.md` | Pre-Phase1 代码审核：metrics 完全重写 + SSRF 防护 + 成本追踪 race fix + adaptive 强制执行 |
| `2026-03-27--phase2_local_strategy_toolkit_engineering_log.md` | ★ Phase 2 完整工程日志：K线管理器 + 6 指标 + 信号生成器 + 4 策略 + 编排器 + 11 路由 + 严格审核修复（620 测试） |
| `2026-03-27--phase3_pipeline_bridge_engineering_log.md` | Phase 3 工程日志：管线桥接器 + 止损管理器 + 信号增强 + 策略增强（640 测试） |
| `2026-03-27--full_system_audit_fix_engineering_log.md` | ★ 全系统审核修复工程日志：7C+19H+28M+16L + 路径统一 + I章去重 + mutator 3x→1x |
| `2026-03-27--roadmap_B_to_I_engineering_log.md` | ★ 路线图 B-I 实现：cron+加权共识+volume+Grid几何+多TF+tick防护+持久化+Delta-Neutral套利（641测试） |
| `2026-03-27--full_day_session_summary.md` | ★★ 完整工作日总结：13 commits + 644 测试 + 20 新文件 + GUI 待做清单 |
| `2026-03-27--gui_three_layer_implementation.md` | GUI 三层架构：Grafana + TradingView + Bybit Demo + 登录系统 + 统一控制台 |
| `2026-03-27--autonomous_agent_scanner_deployer.md` | ★ 自主交易 Agent：市场扫描器 650 符号 + 策略自动部署 + Demo 同步 + 登录系统 |
| `2026-03-27--session2_audit_fix_and_agent_autonomy.md` | Session 2 总结：GUI三层 + Demo + 自主Agent + R1-R5修复 + 第4轮审核7C+10H |
| `2026-03-27--session3_remaining_audit_fixes.md` | Session 3：残留审核全修（时间戳6处+浮点容差+TIF执行+Kahan求和+401刷屏+volume动态+测试修复=646测试） |
| `2026-03-27--gui_10tab_restructure.md` | ★ GUI 10-Tab 全面重构：common.js+8新Tab+双层解释+三层信息密度+99 API端点覆盖 |
| `2026-03-27--session4_gui_10tab_professional_console.md` | ★★ Session 4 完整日志：6 commits+17 files+3964 行+多供应商AI+可编辑风控+中文状态+确认弹窗 |
| `2026-03-27--remote_access_and_security_hardening.md` | 远程访问配置 + 安全加固：Tailscale + secrets 权限 + API key 硬编码消除 |
| `2026-03-27--session5_pipeline_launch_and_openclaw_analysis.md` | Session 5：管线启动验证 + OpenClaw 能力深挖 + systemd 自动重启确认 + Paper Trading 169 单 |
| `2026-03-28--session6_halfday_data_analysis_and_fixes.md` | ★ Session 6：半天数据分析（胜率0%根因）+ 4项修复（扫描器过滤+置信度0.55+.orig stub+3张DB表） |
| `2026-03-28--session7_system_audit_and_fixes.md` | ★★ Session 7：系统全面审核（8模块/12问题）+ 5项修复（市场流自动重启+unknown regime保护+trend cap+时间驱动+confidence对齐），646 测试通过 |
| `2026-03-28--session8_functional_audit_report.md` | ★★★ Session 8：A-J 全面功能审核（25h/684fill/胜率0%）+ E1/G1/H1 三项修复（自动学习/连续亏损暂停/ATR止损接入），428 测试通过 |
| `2026-03-28--session9_bug_fixes_and_verification.md` | ★★ Session 9：3项 bug 修复（net_realized_pnl字段/active_count+1/on_fill仓位同步链路）+ 18个验证测试，664 测试通过 |
| `2026-03-28--session10_ai_cost_and_double_stop_fix.md` | ★★ Session 10：2项修复（total_ai_cost汇总/双重止损防护）+ 7个验证测试，664 测试通过 |
| `2026-03-28--session11_regime_aware_stops.md` | ★★★ Session 11：regime感知止损/止盈/时间三维调整（REGIME_STOP/TP/TIME_MULTIPLIERS）+ 8个验证测试，33+428 测试通过 |
| `2026-03-29--session12_data_analysis_and_bug_fixes.md` | ★★★ Session 12：数据分析发现 0% 胜率根因（fill碎片化+注意力税误关仓），修复 F1/F2/E1a/E1b + GUI G1-G6（活跃订单/价格精度/Demo对比/学习系统），432 测试通过 |
| `2026-03-31--gui_tab_restructure_ollama_optimization.md` | ★★ GUI Tab 重构（Paper+Demo合并+实盘占位）+ Ollama 优化（9B/27B分配+think=False 4x提速+edge filter修复）+ 后台市场流常驻 + 周报时间表调整 |
| `2026-03-31--position_sizing_dynamic_qty_rebalancer.md` | ★★ Position Sizing 重構：3% risk/trade + 25 symbols + 動態 qty（每單重算）+ 智能資本再分配（弱倉自動平倉讓位新機會）|
| `2026-03-31--wave4_p2p3_security_audit_fixes.md` | ★★ Wave 4 P2/P3 批次：5 Sprint · P2-NEW-1~9 + FA-2/3/4 + P3-TECH-1~3（安全補齊 + 端點矩陣完整覆蓋 + NaN/inf 邊界值 + event loop 阻塞修復），2555 tests |
| `2026-03-31--paper_demo_sync_fixes.md` | ★★★ Paper/Demo 同步修復：10 項分歧根源分析 · 3 CRITICAL 修復（止損同步+失敗標記+對賬參數名）· qty 統一四捨五入 · 對賬引擎首次真正運行 |
| `2026-03-31--full_day_complete_engineering_log.md` | ★★★★ 2026-03-31 全天完整工程日誌（整合版）|
| `2026-03-31--round2_batch_records_archive.md` | Round 2 Batch 3-12 + Session 8-12 歸檔（CLAUDE_REFERENCE.md L83 引用） |
| `2026-04-01--phase2_batch2c_completion.md` | ★★★ Phase 2 Batch 2C 完成：接通 _register_pattern_claims 雙路徑 + backtest_routes.py API + 決策權重集成 · Git 分歧解決（rebase）· 3103 tests |
| `2026-04-01--wave7_demo_sync_spot_category_pinned.md` | ★★★ Wave 7：Paper 內部平倉 Demo 同步 + stop_session 自動清倉 + Spot 品類全鏈路 |
| `2026-04-01--wave7a_spot_symbol_category.md` | ★★★ Wave 7a Spot 品類啟用 + 方案 A/B symbol-category 映射 |
| `2026-04-01--phase3_full_completion_and_wave7b.md` | ★★★★ Wave 7b Inverse 品類（INV-1~5）+ Phase 3 全完成 |
| `2026-04-01--governance_auth_restart_fix_and_order_unblock.md` | ★★ GovernanceHub 重啟後授權丟失根因診斷與修復 |
| `2026-04-01--main_legacy_refactor_wave_a_to_e.md` | ★★★★ main_legacy.py 重構全記錄：5265→407 行（-92%）|
| `2026-04-01--wave8_pa_reality_check_and_parallel_fix.md` | ★★★★ Wave 8 工作日誌：PA 69 項實況檢查 + 6 軌道×2 批並行修復 |
| `2026-04-02--batch9a_deterministic_adaptive_risk.md` | ★★★ Batch 9A 確定性自適應風控 |

## Supersedes

歷史 phase 完結；當前 SSOT：
- GUI：`docs/execution_plan/2026-05-06--gui_openclaw_control_console_plan.md`
- API：`srv/services/control_api/` 代碼 + `docs/references/2026-04-04--bybit_api_reference.md`
- Phase 1-3 工程實現已在 git history

## Cross-ref

- 順向：`docs/README.md` § "Phase Packet Archive Index"
- 逆向：`docs/_indexes/path_redirects.md` Executed phase 2 段
- 仍引本歸檔的活檔（P2-8 全部改寫）：
  - `docs/CLAUDE_REFERENCE.md` L83-88（6 entries）
  - `docs/references/2026-03-27--system_reference_handbook.md` L216 區段
  - `docs/governance_dev/changelogs/2026-03-29_T2.23_orig_file_cleanup.md` L106 self-ref
  - `docs/audits/2026-04-12--full_program_chain_audit.md` 多處（不改內文，文末加 footer NOTE）
  - `docs/references/2026-04-02--system_status_report.md` L26650+ ~50 entries（auto-generated manifest，下次 `regen_doc_inventory.py` 自動更新）
