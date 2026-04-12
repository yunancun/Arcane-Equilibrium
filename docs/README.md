# docs/ — 项目文档目录 (Project Documentation Directory)

本目录存放 OpenClaw / Bybit AI Agent 交易系统的所有工程文档、日志、交接记录和决策备忘。

This directory holds all engineering documents, logs, handoff records, and decision memos for the OpenClaw / Bybit AI Agent trading system.

---

## 强制规则 (Mandatory Rules)

**任何人（包括 AI Agent）向 docs/ 写入或新增文件时，必须遵守以下规则：**

1. **文件必须放到对应分类目录**，不允许直接扔在 `docs/` 根目录
2. **文件名必须遵守命名规范**（见下方"文件命名规范"）
3. **每次新增/移动文件后，必须更新本 README 底部的"文档索引"**
4. **不允许重复文件**：放入前检查是否已有相同内容的文件
5. **日志必须人类可读**：简洁、清晰、有上下文，中文为主 + 英文辅助
6. **禁止纯 JSON dump 或代码输出当日志**：日志是写给人看的

---

## 目录结构 (Directory Structure)

```
docs/
├── README.md                          ← 本文件（目录总览 + 规范 + 文档索引）
│
├── worklogs/                          ← 工作日志（按章节/模块分子目录）
│   ├── chapters_a-g/                  ← A-G 章节：基础层 / 观察者 / 事件层
│   ├── chapters_h-i/                  ← H-I 章节：本地判断内核 / AI 治理 / Decision Lease
│   ├── chapters_j-k/                  ← J-K 章节：Transition Engine / Paper Gate / GitHub 迁移
│   ├── control_api_gui/               ← Control API + GUI Operator Console 开发（2026-03-25~04-02）
│   ├── phase5_arch_rc1/               ← Phase 5 / L3 整改 / ARCH-RC1 开发（2026-04-03~04-07）
│   ├── learning/                      ← L 章节：自动学习管线 / 安全加固
│   └── （顶层文件）                   ← 2026-04-08+ 最新工作日志（直接放根目录）
│
├── handoffs/                          ← 阶段交接文档（按日期+主题分文件夹）
│   └── YYYY-MM-DD_主题名/
│
├── decisions/                         ← 重大架构/设计决策记录 + 治理源文件（DOC/SM/EX .docx）
│
├── architecture/                      ← 架構設計文件（系統層面設計決策）
│
├── audits/                            ← ★ 全系统审计报告（专项 + 综合审计子目录）
│   ├── 2026-04-05_l3_comprehensive/   ← L3 全系统综合审计（12 角色专项报告，2026-04-05）
│   └── （专项审计报告）                ← 按日期命名的专项审计（如 Bybit API 审计）
│                                      ← 注：03-31/04-01 全系统审计报告在 CCAgentWorkSpace/ 对应 Agent 下
│
├── references/                        ← 长期参考文档（规范、合同、规格书）
│   ├── state_dictionary/              ← 状态字典 / 数据字典
│   ├── api_contract/                  ← API 合同 / 路由草案 / 审核报告
│   └── api_stub/                      ← API 骨架代码
│
├── archive/                           ← 已归档/过期文档（DEPRECATED 文件、旧版摘要）
│
├── CCAgentWorkSpace/                  ← Agent 工作空间（profile/memory/workspace per agent）
│
├── execution_plan/                    ← 执行计划（Sprint/Wave 排期、里程碑规划）
│
├── rust_migration/                    ← Rust 迁移文档（迁移规划、进度追踪）
│
└── governance_dev/                    ← 治理开发全部文档
    ├── audits/                        ← ★ 审计报告（Round 1/2 审计 + 合规审计）
    ├── changelogs/                    ← T2.01–T2.23 模组变更日志
    ├── governance_extracts/           ← 治理文件结构化提取（索引/速查/技术规格/实现清单）
    ├── phase0_restart/                ← Phase 0 重启审计
    ├── phase0_takeover/               ← Phase 0 接管（目录/代码/AI 架构/计划）
    ├── phase1_gap_analysis/           ← Phase 1 缺口分析
    ├── phase1_governance_wiring/      ← Phase 1 治理接线
    ├── phase2_execution/              ← Phase 2 治理模组执行（21 模组 + PM/TW 审核）
    ├── phase2_risk_hardening/         ← Phase 2 风控强化
    ├── phase3_bug_fix_hardening/      ← Phase 3 Bug 修复强化
    ├── phase3_integration/            ← Phase 3 治理集成 + 安全审计
    ├── phase4_acceptance/             ← Phase 4 验收（合规/测试/UX/文档/PM）
    ├── phase4_reconciliation_hardening/ ← Phase 4 对账强化
    ├── phase5–12/                     ← Phase 5-12（治理完整性/测试/Demo/REST/事件/执行/打磨）
    └── 2026-03-30--round2_fix_plan*   ← Round 2 修复计划（Batch 7-12）
```

---

## 文件命名规范 (File Naming Convention)

所有文档文件统一使用以下格式：

```
YYYY-MM-DD--功能描述.扩展名
```

带时间戳（同一天有多份文档时）：

```
YYYY-MM-DD--HHmm--功能描述.扩展名
```

规则：
- **日期在前**：便于按时间排序，一目了然
- **双横线 `--` 分隔**：日期与描述之间、时间与描述之间
- **功能描述用下划线连接**：避免空格，保持路径兼容性
- **中文描述优先**：描述部分可以用中文，如 `2026-03-26--api_gui_全量工程报告.md`
- **扩展名保留原格式**：`.md` / `.txt` / `.pdf` / `.py` 均可

---

## 日志分类说明 (Log Categories)

### 1. worklogs/ — 工作日志

**用途**：日常开发过程中的工作记录。简洁、清晰、人类可读。

**组织方式**：按章节或模块分子目录，文件按日期命名。

### 2. handoffs/ — 阶段交接文档

**用途**：一个工程阶段完成后的正式交接记录，供后续开发者或未来的自己快速了解上下文。

**组织方式**：每次交接创建一个子文件夹，命名为 `YYYY-MM-DD_主题名`。

### 3. decisions/ — 决策记录

**用途**：记录重大架构或设计决策的背景、选项、结论和理由。

**格式建议**：
```markdown
# 决策：<标题>
日期：YYYY-MM-DD
状态：已决定 / 待讨论 / 已废弃

## 背景 (Context)
## 选项 (Options)
## 结论 (Decision)
## 影响 (Consequences)
```

### 4. audits/ — 全系统审计报告

**用途**：全系统审计报告归档。按月份分子目录（March31、April01 等），每次审计产出多角色报告；专项审计报告（如 Bybit API 审计）直接以日期命名放根目录。

### 5. references/ — 长期参考文档

**用途**：不随版本频繁变化的规范性文档，如 API 合同、状态字典规格书、部署规范等。

---

## 日志书写原则 (Writing Principles)

1. **简单清晰明了**：一段话能说清的不写两段，一句话能说清的不写一段
2. **人类可读优先**：写给人看，不是给程序解析的。用自然语言，避免纯 JSON dump
3. **中文为主，英文辅助**：正文用中文，专有名词保留英文原文（如 Decision Lease、compile_state）
4. **事实与推断分开**：明确标注哪些是确认的事实，哪些是推测或假设
5. **带上下文**：说清"为什么做"而不仅仅是"做了什么"
6. **避免冗余**：代码里能看到的不用在日志里重复，git log 能查到的不用抄一遍

---

## 文档索引 (Document Index)

### worklogs/chapters_a-g/ — A-G 章节工作日志（2026-03-11 ~ 2026-03-19）

| 文件 | 内容 |
|------|------|
| `2026-03-11--openclaw_bybit_进度日志.txt` | 03-11 项目启动，基础层搭建进度 |
| `2026-03-12--openclaw_bybit_进度日志.txt` | 03-12 继续基础层开发 |
| `2026-03-13--详细工作日志.txt` | 03-13 详细工作记录 |
| `2026-03-13--三日补充综合日志.txt` | 03-11~13 三日补充综合回顾 |
| `2026-03-17--chapter_g_工程记录.txt` | G 章工程记录（Revision 2） |
| `2026-03-17--chapter_g_执行清单.txt` | G 章执行清单（Revision 2） |
| `2026-03-17--engineering_log.txt` | 03-17 工程日志 |
| `2026-03-19--补充记录1.txt` | 03-19 补充记录 |
| `2026-03-19--当前进度图_校正后.txt` | 进度图校正版 |
| `2026-03-19--工作记录_含0317至0319校正与修复.txt` | 03-17~19 校正与修复工作记录 |
| `2026-03-19--完整版当前进度图.txt` | 完整版进度图（校正后） |

### worklogs/chapters_h-i/ — H-I 章节工作日志（2026-03-20 ~ 2026-03-22）

| 文件 | 内容 |
|------|------|
| `2026-03-20--openclaw_工作记录.txt` | 03-20 H-I 章节开始 |
| `2026-03-20--超详细续接总报告.txt` | 超详细续接总报告 |
| `2026-03-20--h0_本地判断核心蓝图_v1.txt` | H0 本地判断核心蓝图 v1 |
| `2026-03-20--h_i_本地执行内核讨论备份.txt` | H-I 本地执行内核讨论备份 |
| `2026-03-22--0320工作报告_新对话接手版.txt` | 03-20 工作报告（供新对话接手） |
| `2026-03-22--a-i_接手摘要.txt` | A-I 全量接手摘要 |
| `2026-03-22--h_i_正式完工对账报告.txt` | H-I 正式完工对账报告 |
| `2026-03-22--h_i_兼容性对账清单.txt` | H-I 兼容性对账清单（新对话首步验证） |
| `2026-03-22--全量整合总报告.txt` | 全量整合总报告 |
| `2026-03-22--全量整合总报告_重新导出.txt` | 全量整合总报告（重新导出版） |
| `2026-03-22--晚_工程记录.txt` | 03-22 晚间工程记录（Fix H-I） |
| `2026-03-22--晚_新对话接手指示.txt` | 新对话接手指示 |
| `2026-03-22--晚_新对话接手prompt.txt` | 新对话接手 Prompt |
| `2026-03-22--晚_h1_no_call_semantics_patch.txt` | H1 no-call 语义补丁 bundle |

### worklogs/chapters_j-k/ — J-K 章节 + GitHub 迁移（2026-03-22 ~ 2026-03-24）

| 文件 | 内容 |
|------|------|
| `2026-03-22--项目总报告_含github核对.md` | 项目总报告（含 GitHub 核对，md 版） |
| `2026-03-22--项目总报告_含github核对.txt` | 项目总报告（含 GitHub 核对，txt 版） |
| `2026-03-22--夜间_最终整合总报告.txt` | 夜间最终整合总报告 |
| `2026-03-22--夜间_github迁移与诊断报告.txt` | GitHub 迁移与夜间诊断报告 |
| `2026-03-22--夜间_新对话接手prompt_github版.txt` | 新对话接手 Prompt（GitHub 工作流版） |
| `2026-03-24--工程总报告_结构迁移完成.txt` | 工程总报告：结构迁移完成 + 新工作流 |
| `2026-03-24--交接日志.txt` | 03-24 晚交接日志 |
| `2026-03-24--新对话启动prompt.txt` | 新对话启动 Prompt |
| `2026-03-24--work_report_current_dialogue.txt` | 当前对话工作报告（txt） |
| `2026-03-24--work_report_current_dialogue.md` | 当前对话工作报告（md） |
| `2026-03-24--work_report_current_dialogue.pdf` | 当前对话工作报告（pdf） |

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
| `2026-03-31--full_day_complete_engineering_log.md` | ★★★★ 2026-03-31 全天完整工程日誌（整合版）：7-Agent 全系統審計 · P0 CRITICAL×4 修復 · Wave 0-3 全系列 · H0 Gate Day 1-3 · Wave 4 Sprint 4a-4e · Wave 5a Position Sizing + 5b Paper/Demo 同步 · Wave 5 Sprint H鏈接通 · Wave 6 Sprint 0+1a+1b+2 + Cleanup · Phase 2 Batch 2A+2B，2624 tests |
| `2026-04-01--phase2_batch2c_completion.md` | ★★★ Phase 2 Batch 2C 完成：接通 _register_pattern_claims 雙路徑 + backtest_routes.py API + 決策權重集成 · Git 分歧解決（rebase）· 3103 tests |
| `2026-04-01--wave7_demo_sync_spot_category_pinned.md` | ★★★ Wave 7：Paper 內部平倉 Demo 同步 + stop_session 自動清倉 + Spot 品類全鏈路（Scanner+策略+Position）+ demo_reserved 解鎖 + GUI 品類標籤 + BTC/ETH 釘選幣種 |
| `2026-04-01--wave7a_spot_symbol_category.md` | ★★★ Wave 7a Spot 品類啟用 + 方案 A/B symbol-category 映射：SPOT-1~5 全通 + _symbol_category_map 雙向注入 + SymbolCategoryRegistry 啟動填充，3103→3161 tests |
| `2026-04-01--phase3_full_completion_and_wave7b.md` | ★★★★ Wave 7b Inverse 品類（INV-1~5）+ Phase 3 全完成（3A ExperimentLedger/Routes/EvolutionEngine + 3B TruthSourceRegistry持久化/AnalystAgent觀測/auto_seed + 3C EvolutionScheduler週進化/小時清理/GUI dashboard）· 3103→3330 tests |
| `2026-04-01--governance_auth_restart_fix_and_order_unblock.md` | ★★ GovernanceHub 重啟後授權丟失根因診斷與修復：5 層診斷（state.json→audit→bridge stats→auth NONE）· get_status() auth_pending_approval 修復 · /session/reauth 端點 · startup 自動補授 · 首筆 FARTCOINUSDT 訂單解封成交 |
| `2026-04-01--main_legacy_refactor_wave_a_to_e.md` | ★★★★ main_legacy.py 重構全記錄：5265→407 行（-92%），Wave A-E 共拆出 11 模塊，monkey-patch 延遲查找修復，E5 審查 build_review_queue bug 修復，§14 約定建立，3005 tests 零回歸 |
| `2026-04-01--completed_todo_archive.md` | ★★ TODO 已完成項目歸檔：Wave 0-7 / Phase 1-3 / Audit Batch 1-7 / main_legacy 重構全部完成記錄 |
| `2026-04-01--wave8_pa_reality_check_and_parallel_fix.md` | ★★★★ Wave 8 工作日誌：PA 69 項實況檢查 + 6 軌道×2 批並行修復 38/39 項 + strategist 拆分 + on_tick/mutator 拆分 + now_ms 統一 + +148 測試 |
| `2026-04-02--batch9a_deterministic_adaptive_risk.md` | ★★★ Batch 9A 確定性自適應風控：QC 量化審查驅動 · ATR 雙窗口 + 成本感知入場門檻 + 追蹤止損成本約束 + round-trip 真實費用 · 修復 ATR 止損死代碼 bug · +66 測試 · 3703 passed |

### worklogs/phase5_arch_rc1/ — Phase 5 / L3 整改 / ARCH-RC1 開發日誌（2026-04-03 ~ 2026-04-07）

| 文件 | 内容 |
|------|------|
| `2026-04-03--daily_summary.md` | ★★★★ 2026-04-03 日匯總（12 Sessions · 28 Commits）：文檔治理 + Phase 0-3 全覽 + Rust R-00~R-04 |
| `2026-04-03--completed_todo_archive_batch9a_wave8_xp.md` | TODO 已完成歸檔：Batch 9A + Wave 8A-8D + XP-1~4（路線圖定稿清理） |
| `2026-04-04--daily_summary.md` | ★★★★ 2026-04-04 日匯總：V2 策略功能全面啟用（P0 緊急修復）+ Bybit API 基礎設施 |
| `2026-04-04--td01_td02_td03_file_split.md` | Session 3：TD-01/02/03 Python 大文件拆分（Phase 1 前置技術債清零） |
| `2026-04-04--session4_bybit_api_audit.md` | ★★★ Session 4：BB+E5+PA 三角色聯合審計 Bybit V5 API 層 + 完整 API 字典手冊 |
| `2026-04-04--session5_bybit_full_integration.md` | ★★★ Session 5：9 項 API 整合改進 + 3 新模組 + Demo→Live 對齊（PM+PA+FA+BB 四角色） |
| `2026-04-04--completed_todo_archive_phase0123_rust.md` | TODO 已完成歸檔：Phase 0-3（26 項）+ Rust R-00~R-06（7 項）|
| `2026-04-05--daily_summary.md` | ★★★★ 2026-04-05 日匯總（3 Sessions）：Phase 1 Full Rust 數據管線（G1-G4）+ Phase 2/3a/3b ML 基礎設施 + EXT-1 Exchange-as-Truth + RRC-1 設計 + 風控 GUI 補齊 + Demo 架構完成 |
| `2026-04-06--session10_r0_r1_remediation.md` | ★★★ Session 10：L3 414 findings → 63 tracker + R0 Week 1（7 P0 修復）+ R1 Wave 1（WP-B Security + WP-MIT DB/ML + idle writer） |
| `2026-04-06--session11_p1_6_drift_detector.md` | Session 11：WP-MIT P1-6 drift_detector PG 接線（fetch_active_baselines / DriftMonitorState / PSI 滑動窗口） |
| `2026-04-06--session11_r2_batch.md` | ★★★ Session 11：R1 收尾 + R2 批次（多項 L3 整改繼續推進） |
| `2026-04-06--session11_precompact.md` | Session 11 Pre-Compact 快照：453 engine + 411 core + 35 ml_training · 0 failures |
| `2026-04-06--session12_precompact.md` | Session 12 Pre-Compact 快照：474 engine + 413 core + 35 ml_training · 0 failures |
| `2026-04-06--session13_precompact.md` | ★★★★ Session 13：I-22 event_consumer 拆分 + FA-GAP-2/4 接線（cost_ratio/Kelly ATR%）+ per-symbol 真實費率 + SEC-11 fail-closed + FA-GAP-8/9 dead code 清除 |
| `2026-04-06--completed_todo_archive_l3_phases.md` | TODO 已完成歸檔：L3 整改 + Phase 0/1/2/3 + Rust 遷移已驗收項（Session 11 後清理） |
| `2026-04-06--session_progress_2.md` | Session 進度快照（Session 2）|
| `2026-04-07--session_arch_rc1_1a_1b.md` | ARCH-RC1 1A + 1B：ConfigStore 單一寫入口 + StrategyParams JSON 接線 |
| `2026-04-07--session_arch_rc1_1c1_1c2.md` | ARCH-RC1 1C-1 + 1C-2：IPC patch 接線 + hot-reload ArcSwap |
| `2026-04-07--session_arch_rc1_1c2_complete.md` | ARCH-RC1 1C-2 完成：IPC 全鏈路驗收 |
| `2026-04-07--session_phase4_1_complete.md` | Phase 4-1 完成日誌 |
| `2026-04-07--session_phase4_complete.md` | Phase 4 全量完成日誌 |

### worklogs/ — 頂層工作日志（2026-04-08+）

| 文件 | 内容 |
|------|------|
| `2026-04-10--signal_diamond_phase1_4_fix_round.md` | ★★★ Signal Diamond Phase 1-4 + Fix Round 完整工程記錄：V015 Migration + Rust DB Writers + ModeState + IPC mode-aware + state swap + AddMode/SwitchMode IPC · 850 tests |
| `2026-04-10--ml_pipeline_remediation_complete.md` | ML Pipeline 整改完成日誌：Rust 學習寫入路徑 + per-mode 數據隔離驗收 |
| `2026-04-09--rust_market_scanner_phase_a_d_complete.md` | ★★★ Rust 市場掃描器 Phase A-D 完整工程日誌：ScannerRunner 全接線 + D2/D3 動態 symbol + QC/FA + IPC-SCAN-1 |
| `2026-04-09--strategy_action_enum_implementation.md` | StrategyAction Enum 完整實現日誌：策略出場死鎖修復 + QC/FA 審查 + 4 findings 全修（P1 grid drift, P2 exchange Kelly, P2 funding_arb, P2 集成測試）· 830 tests |
| `2026-04-08--daily_summary.md` | ★★★★ 2026-04-08 日匯總：1C-3 / 1C-3-F / 1C-4 全量完成 |
| `2026-04-08--arch_rc1_1c_history_archive.md` | ★ ARCH-RC1 1A→1C-4 commit 敘事歸檔（1C-3 分 E/F 兩期完整記錄） |
| `2026-04-08--1c3d_main_body.md` | ARCH-RC1 1C-3-D 主體實現日誌 |
| `2026-04-08--1c3e_fmini_handoff.md` | ARCH-RC1 1C-3-E → 1C-3-F 交接快照 |
| `2026-04-08--session_gui_fake_success_wave1.md` | GUI fake-success 盤點 Wave 1 |
| `2026-04-08--session_gui_fake_success_wave2_p1_wiring.md` | GUI fake-success Wave 2 + P1 wiring |
| `2026-04-08--session_progress_1c3f.md` | 1C-3-F session 進度 |
| `2026-04-08--session_progress_post_1c4_wrap.md` | 1C-4 wrap 後 session 進度 |
| `2026-04-08--session_resume_notes.md` | Session 恢復筆記 |

### worklogs/learning/ — L 章学习系统开发日志（2026-03-26）

| 文件 | 内容 |
|------|------|
| `2026-03-26--L章_自动学习管线与安全加固_完整工程日志.md` | L 章自动学习管线 + 安全加固全量工程日志（含审核包设计、96 测试、8 项安全修复） |

### handoffs/ — 阶段交接文档

| 路径 | 内容 |
|------|------|
| `2026-03-25_api_gui_handoff/` | Control API v1 + GUI v1 阶段交接（含 12 份文档 + source_docs） |

### decisions/ — 架构/设计决策记录 + 治理源文件

| 文件 | 内容 |
|------|------|
| `2026-04-01--symbol_category_mapping_design.md` | Symbol→Category 映射策略決策：方案 B 運行時映射（短期）+ 方案 A SymbolCategoryRegistry 批量填充（長期），雙層架構設計 |
| `2026-03-17--工程一审修改建议报告_终稿.md` | Revision 2 工程一审修改建议报告（md 终稿） |
| `2026-03-17--工程一审修改建议报告_终稿.txt` | Revision 2 工程一审修改建议报告（txt 终稿） |
| `2026-03-20--关于h和i部分的核心设计讨论.txt` | H-I 核心设计讨论（AI 成本均衡 / 本地计算 / 延迟框架 / 设备容错） |
| **治理源文件（.docx，Operator 原始治理规格）** | |
| `DOC-NAV_...治理文件导航_V3.docx` | 治理文件导航 V3（13 份文件总入口） |
| `DOC-01_...项目宪法与根原则_V2.docx` | 项目宪法：16 条根原则（§5.1–§5.16） |
| `DOC-02_...边界定义_V2.docx` | 系统边界定义（H0 <1ms SLA、执行权限、数据平面） |
| `DOC-03_...字段级与状态级规范_V1.1.docx` | 字段级与状态级规范 |
| `DOC-04_...Agent能力蓝图_V2.docx` | Agent 能力蓝图（A-J 十大能力目标） |
| `DOC-05_...真相源与所有权矩阵_V1.1.docx` | 真相源与所有权矩阵 |
| `DOC-06_...变更治理_V2.docx` | 变更治理流程 |
| `DOC-07_...审计事故与熔断政策_V1.1.docx` | 审计/事故/熔断政策 |
| `DOC-08_...实施桥梁_V1.docx` | 实施桥梁（AI 成本上限 $2/天、provider 配置） |
| `SM-01_...授权状态机规范_V1.docx` | SM-01 授权状态机规范 |
| `SM-02_...决策租约状态机规范_V1.docx` | SM-02 决策租约状态机规范 |
| `SM-03_...执行状态机规范_V1.1.docx` | SM-03 OMS 执行状态机规范 |
| `SM-04_...风控状态机规范_V1.docx` | SM-04 风控状态机规范 |
| `EX-01_...风控边界定义_V2.docx` | 风控边界定义 |
| `EX-02_...OMS与执行正式边界定义_V1.docx` | OMS 与执行正式边界定义 |
| `EX-03_...控制平面正式边界定义_V1.docx` | 控制平面正式边界定义 |
| `EX-04_...对账正式边界定义_V1.docx` | 对账正式边界定义 |
| `EX-05_...学习边界定义_V2.docx` | 学习边界定义 |
| `EX-06_...多Agent编排正式边界定义_V1.docx` | 多 Agent 编排正式边界定义 |
| `EX-07_...感知平面正式边界定义_V1.docx` | 感知/数据平面正式边界定义 |
| `HIST-01_...核心设计总纲_V1.docx` | 历史参考：核心设计总纲 |
| `HIST-02_...治理设计交付包_V1.docx` | 历史参考：治理设计交付包 |

### CCAgentWorkSpace（各 Agent workspace/reports）— ★★★ 2026-03-31 七Agent全系统审计

| Agent | 文件（CCAgentWorkSpace/<Agent>/workspace/reports/） | 内容 |
|-------|------|------|
| E3 | `2026-03-31--e3_security_audit.md` | E3 安全审计：3 CRITICAL / 5 HIGH / 6 MEDIUM / 5 LOW |
| CC | `2026-03-31--cc_compliance_check.md` | CC 合规检查：11/16 原则完全合规，B 级 |
| E4 | `2026-03-31--e4_testing_report.md` | E4 测试评估：71 文件/2480 用例 |
| E5 | `2026-03-31--e5_optimization_report.md` | E5 优化评估：49 项 |
| A3 | `2026-03-31--a3_gui_usability_report.md` | A3 GUI 可用性：6.2/10 |
| PM | `2026-03-31--pm_review.md` | ★ PM 整合审核：71 项去重，~110h 工时 |
| PA | `2026-03-31--pa_review.md` | ★ PA 技术复验：4 CRITICAL 确认属实 |

双语注释审计：`audits/2026-03-30--bilingual_comment_audit_report.md`

### CCAgentWorkSpace（各 Agent workspace/reports）— ★★★ 2026-04-01 十Agent全系统审计

| Agent | 文件（CCAgentWorkSpace/<Agent>/workspace/reports/） | 内容 |
|-------|------|------|
| AI-E | `2026-04-01--ai_effectiveness_audit.md` | AI-E AI 效果审计 |
| CC | `2026-04-01--compliance_check.md` | CC 合规检查：16 条根原则逐一验证 |
| E3 | `2026-04-01--security_audit.md` | E3 安全审计 |
| E4 | `2026-04-01--testing_audit.md` | E4 测试评估 |
| E5 | `2026-04-01--optimization_audit.md` | E5 优化评估 |
| FA | `2026-04-01--functional_gap_audit.md` | FA 功能缺口审计 |
| TW | `2026-04-01--documentation_quality_audit.md` | TW 文档品质审计 |
| R4 | `2026-04-01--document_index_audit.md` | R4 文档索引审计 |
| Operator | `2026-04-01--pa_review.md` | PA 技术复验 |
| Operator | `2026-04-01--pm_execution_plan.md` | PM 执行计划 |

### audits/2026-04-05_l3_comprehensive/ — L3 全系统综合审计（2026-04-05，12 角色专项报告）

注：这批审计文件是 2026-04-05 L3 审计轮次产出，因当时未遵守命名规范（无日期前缀），现统一归入此子目录。

| 文件 | 内容 |
|------|------|
| `audit_A3_gui_usability_report.md` | A3 GUI 可用性审计报告 |
| `audit_AIE_effectiveness_report.md` | AI-E AI 效果评估报告 |
| `audit_BB_bybit_api_report.md` | BB Bybit API 专项审计报告 |
| `audit_CC_compliance_report.md` | CC 合规审计报告 |
| `audit_E3_security_report.md` | E3 安全审计报告 |
| `audit_E4_test_coverage_report.md` | E4 测试覆盖报告 |
| `audit_E5_optimization_report.md` | E5 优化评估报告 |
| `audit_FA_functional_spec_report.md` | FA 功能规格审计报告 |
| `audit_MIT_database_ml_report.md` | MIT 数据库 + ML 专项报告 |
| `audit_QC_math_algorithm_report.md` | QC 数学算法审计报告 |
| `audit_R4_index_verification_report.md` | R4 文档索引完整性审计报告 |
| `audit_TW_document_inventory_report.md` | TW 文档盘点审计报告 |

### audits/（专项审计报告）

| 文件 | 内容 |
|------|------|
| `2026-03-30--bilingual_comment_audit_report.md` | 双语注释全量审计报告（评级 9.5/10，100% 覆盖） |
| `2026-04-04--bybit_api_infra_audit.md` | ★ Bybit API 基础设施专项审计：REST/WS 端点覆盖度、SDK 对接质量、IPC 接口审核 |
| `2026-04-06_consolidated_remediation_report.md` | ★ L3 全系统审计 63 问题整改追踪报告：11 工作包 · 4 波执行 · R0-R3 整改记录 |
| `2026-04-07_e3_r6_directive_applier_security_audit.md` | E3 R6 Directive Applier 安全审计（Phase 4 前置） |
| `2026-04-07_phase4_final_signoff_audit.md` | Phase 4 最终验收审计报告 |
| `2026-04-08--e2_review_1c3_bbc.md` | E2 代码审查：ARCH-RC1 1C-3 BBC（Build-Before-Commit 验收） |
| `2026-04-09--db_rw_ml_pipeline_full_audit.md` | DB 读写 + ML 管线全量审计（Signal Diamond Phase 1 前置）|

### architecture/ — 架構設計文件

| 文件 | 内容 |
|------|------|
| `DATA_STORAGE_ARCHITECTURE_V1.md` | ★ 數據存儲架構 V1：PG + TimescaleDB 方案 · 8 Schema · 存儲精簡 97%（5.6→0.17 GB/day）· 冷存儲 NAS 策略 |

### references/ — 长期参考文档

| 文件 | 内容 |
|------|------|
| **state_dictionary/** | |
| `状态字典_数据字典_v1_最终版.md` | 状态字典 / 数据字典 V1 最终版（1149 行） |
| `状态字典_v1_rc2_伴随补丁.md` | 状态字典 V1 RC2 伴随补丁 |
| **api_contract/** | |
| `control_api_v1_最终定稿.md` | Control API V1 最终定稿（1008 行） |
| `control_api_v1_rc2_最终候选版.md` | Control API V1 RC2 最终候选版 |
| `control_api_v1_rc2_审核报告.md` | Control API V1 RC2 审核报告 |
| `fastapi_openapi_v1_rc2_路由草案.md` | FastAPI / OpenAPI V1 RC2 路由草案 |
| `后端实现清单_v1_rc2.md` | 后端实现清单 V1 RC2 |
| **api_stub/** | |
| `control_api_v1_rc2_fastapi_stub.py` | FastAPI 骨架代码（553 行） |
| **根目录** | |
| `2026-03-25--capability_and_permission_switch_plan_v1.md` | 能力与权限开关规划 V1（md） |
| `2026-03-25--capability_and_permission_switch_plan_v1.pdf` | 能力与权限开关规划 V1（pdf） |
| `2026-03-25--gui_operator_console_learning_cockpit_v1_spec.md` | GUI Operator Console + Learning Cockpit V1 规格书 |
| `2026-03-27--layer2_ai_reasoning_engine_implementation_plan.md` | Layer 2 AI 推理引擎完整实现计划（4 层搜索降级 + 模型升级 + 自适应预算 + 9 路由 + GUI 集成） |
| `2026-03-27--local_trading_logic_audit_and_strategy_plan.md` | 本地交易逻辑审查报告：安全审查 + 本地覆盖缺口 + 盈利可能性评估 + ABCD 策略补齐计划 |
| `2026-03-27--phase1_risk_framework_and_agent_autonomy_design.md` | ★ 全品类风控框架完整设计：三层优先级 P0/P1/P2 + Bybit V5 全 6 品类 + 对抗性止损 + AI 注意力税 + Agent 自主交易 |
| `2026-03-27--phase2_strict_audit_report.md` | ★ Phase 2 严格审核报告：8 CRITICAL + 15 HIGH + 25 MEDIUM + 19 LOW，全 CRITICAL/HIGH 已修复 |
| `2026-03-27--phase2_audit_fix_roadmap.md` | Phase 2 审核修复工程路线图：已完成项 + 待完善项 + 架构级待定 |
| `2026-03-27--system_reference_handbook.md` | ★ 系统参考手册（从 CLAUDE.md 移出的参考性内容：能力目标/API路由/安全加固/产品族/订单类型/风控/部署/历史编号） |
| `2026-03-27--phase2_round2_strategic_audit_report.md` | Phase 2 第二轮审核：实战适用性（策略盈利性/管线连通性/数据质量/风控集成/信号可靠性） |
| `2026-03-27--full_system_audit_A_to_K.md` | ★★ 全系统审核 A-K：569 文件 63,874 行，7 CRITICAL + 19 HIGH + 28 MEDIUM + 16 LOW |
| `2026-03-27--remote_access_guide.md` | 远程访问完整指南：Tailscale 安装配置 + Bybit Demo 访问地址 + secrets 权限加固 |
| `2026-03-22--local_private_layout.md` | 本地私有布局说明：Git 仓库 vs 本地私有目录结构（secrets/srv 分离） |
| `2026-03-30--local_ai_expansion_analysis.md` | 本地 AI 擴展用途分析（Ollama/Qwen 3.5 應用場景，DOC-08 依據） |
| `2026-04-03--openclaw_improvement_report_v3_final.md` | ★★★★ 外部全面改善建議報告 V3 Final：五輪三人審批 34 項修正 · Agent 自主化架構 + 雙層決策 + 四階段放權 + 10 新模組 + 5 策略 V2 + L0-L2 路徑 + Claude API 整合 |
| `2026-04-03--agent_cognitive_adaptation_spec_v1_draft.md` | V1.1+R1 · Agent 認知自適應規範：CognitiveModulator（L0 決策門檻調製）+ OpportunityTracker（遺憾追蹤）+ DreamEngine（閒置蒙特卡洛模擬）— 五角色審查通過，Phase 1 並行組 B |
| `2026-04-03--rust_migration_master_plan_v2.md` | V2 草稿（歸檔）· Rust 遷移總方案初版 |
| `2026-04-03--rust_migration_v2.5_consolidated.md` | V2.5 整合版（歸檔）· 六路缺口修復後 |
| `2026-04-03--rust_migration_v3_final.md` | ★★★★ V3-FINAL · Rust 遷移正式執行依據：五角色三輪審查 · 32,500 行 Rust · 14 週路線圖 · 分級浮點容差 · 四層測試 · 回滾計劃 · 21 項嚴格論證修正 |
| `2026-04-02--system_status_report.md` | 系統狀態報告（2026-04-02）：引擎健康度、測試基準線、已知問題彙整 |
| `2026-04-03--agent_param_tuning_design_draft_v0.2.md` | Agent 參數調整設計草稿 V0.2：策略參數 JSON 介面 · Agent 自主調參機制 · AGT-1 技術規格 |
| `2026-04-03--data_storage_architecture_optimal_draft_v0.1.md` | 數據存儲架構最優方案草稿 V0.1：PG + TimescaleDB · 分區策略 · 冷熱分層 |
| `2026-04-03--llm_abstraction_audit.md` | LLM 抽象層審計：LocalLLMClient ABC 介面覆蓋度 · Ollama 耦合殘留 · 跨平台兼容性評估 |
| `2026-04-03--ml_dl_learning_architecture_v0.4.md` | ★ ML/DL 學習架構 V0.4：Teacher-Student + LightGBM + Optuna + 3 DL 場景 · 三方審查完成 |
| `2026-04-10--signal_diamond_db_todo.md` | ★★ Signal Diamond DB TODO 歸檔：多引擎數據分離 5 Phase 規劃 · Phase 1-4 ✅ + 審計備註 · Phase 5 待實施 |
| `2026-04-04--bybit_api_reference.md` | ★★ Bybit API 字典手冊：REST/WS 全端點速查 · V5 API 分類覆蓋 · 開發必讀 |
| `2026-04-04--comprehensive_audit_template_v1.md` | 全面審查模板 V1：L1/L2/L3 三級審計流程 · 5 路並行 9 角色 + DL/DB 專項 |
| `2026-04-04--execution_plan_v1.md` | ★ 融合方案執行計劃 V1：DB + ML/DL + 新聞 Agent 20 週路線圖 · Phase 0-6 詳細規格 |
| `2026-04-04--unified_db_ml_news_workplan_draft_v0.1.md` | 統一 DB + ML + 新聞 Agent 工作計劃草稿 V0.1：融合方案 v0.5 設計文件 · 67 項修正後版本 |

### governance_dev/ — 治理开发文档

> 注意：governance_dev/ 下早期文件使用大寫命名（如 `T2_EXECUTION_SUMMARY.md`），
> 晚於 2026-03-31 的新文件必須遵循 `YYYY-MM-DD--描述.md` 命名規範。

#### governance_dev/audits/ — ★ 审计报告

| 文件 | 内容 |
|------|------|
| `2026-03-30--round2_cold_functional_audit.md` | ★★★ Round 2 冷酷功能审核（任务 1/2/3：32% 完成度 + 架构融合 + Paper Trading 路线图） |
| `2026-03-30--governance_compliance_audit.md` | 治理合规审计（EX-05/06/07/DOC-01~08，合规度 ~65%） |
| `2026-03-30--pipeline_bridge_paper_engine_audit.md` | PipelineBridge + PaperTradingEngine 代码级审计（治理 gate 验证 + 止损验证 + 学习回调验证） |
| `2026-03-31--gap_analysis_287_specs.md` | ★ 287 条治理规格 Gap 分析报告（76% 已实施：67A + 18B + 8C + 2D） |
| `2026-03-31--spec_requirements_287.md` | 287 条规格完整列表（Markdown 版，与 Gap 分析配套） |
| `2026-03-31--spec_requirements_287.json` | 287 条规格完整列表（JSON 机器可读版） |
| `2026-03-31--gap_analysis_findings.json` | Gap 分析发现结果（JSON 结构化输出） |
| `2026-03-31--gap_analysis_file_reference.md` | Gap 分析文件引用索引 |
| `2026-03-31--development_roadmap_v2.md` | 4-Phase 开发路线图 V2（基于 Gap 分析制定） |
| `2026-03-31--phase0_round2.5_audit_report.md` | Phase 0 Round 2.5 审计报告（2 P0 + 1 P1 修复 + 287 spec Gap 分析） |

#### governance_dev/audits/2026-03-30--全面審核/ — ★★★ 全系统冷酷功能审核（9 Batch）

| 文件 | 内容 |
|------|------|
| `00_審查計劃總綱.md` | 审查计划总纲 + 进度追踪（9 Batch，A-I） |
| `01_A_即時問題診斷.md` | ★★★ P0 根因分析：MA_Cross metadata falsy + FundingRate 错误 symbol（10/10 策略全失效） |
| `02_B_交易核心路徑.md` | 交易核心路径验证（B1-B7：状态机/Fill/PnL/round_trip 均正确） |
| `03_C_風控框架.md` | 风控框架验证（P1：drawdown gate 无强制执行；其余 C2-C8 均正确） |
| `04_D_學習系統.md` | 学习系统验证（E1 路径代码就绪，因 0 fills 未实际运行） |
| `05_E_AI治理層.md` | AI 治理层验证（H0/Decision Lease 完整；AI 调用合法跳过） |
| `06_F_掃描器策略部署.md` | 扫描器与策略部署验证（5min 周期、40% 过滤、WS 动态订阅均正确） |
| `07_G_GUI_API端點.md` | GUI 与 API 端点验证（所有关键端点存在，数据源正确） |
| `08_H_測試健康度.md` | 测试健康度（2,166 通过；P0 bug 路径无测试覆盖） |
| `09_I_代碼品質.md` | 代码品质扫描（无 TODO/FIXME/silent except；硬编码值均有注释） |
| `99_審查總結與修復清單.md` | ★★★ 审查总结：3 个问题（P0×2 + P1×1）+ 修复方案 + 系统健康全景 |

#### governance_dev/2026-03-30 Round 2 修复计划

| 文件 | 内容 |
|------|------|
| `2026-03-30--round2_fix_plan_batches_7_12.md` | ★★ Batch 7-12 完整技术规格（Conductor + Guardian + Perception + Analyst + L2 + Paper→Live） |
| `2026-03-30--round2_fix_plan_EXECUTIVE_SUMMARY.md` | 修复计划管理摘要（缺口分析 + 策略 + 风险） |
| `2026-03-30--round2_fix_plan_QUICK_REFERENCE.md` | 修复计划开发速查（批次清单 + 依赖图 + 成本） |
| `2026-03-30--ROUND2_FIX_PLAN_INDEX.md` | 修复计划导航索引 |
| `2026-03-30--round2_pragmatic_fix_plan.md` | Round 2 务实修复计划（优先级排序 + 实施策略） |

#### governance_dev/ — 规格提取与287条治理规格（根目录文件）

| 文件 | 内容 |
|------|------|
| `README.md` | governance_dev 子目录自述文件 |
| `COMPREHENSIVE_SPEC_REQUIREMENTS.md` | 287 条治理规格完整列表（Markdown 版） |
| `COMPREHENSIVE_SPEC_REQUIREMENTS.json` | 287 条治理规格完整列表（JSON 机器可读版） |
| `SPECIFICATION_EXTRACTION_SUMMARY.md` | 规格提取摘要（13 份 .docx → 287 条结构化提取过程） |
| `SPECIFICATION_REGISTER.md` | 规格登记册（DOC/SM/EX 文件版本追踪） |
| `EXTRACTION_VALIDATION.txt` | 提取验证报告（规格数量/覆盖度/交叉引用校验） |
| `QUICK_START_REFERENCE.txt` | 治理开发快速入门参考 |

#### governance_dev/governance_extracts/ — 治理规格提取（5 份参考文档）

| 文件 | 内容 |
|------|------|
| `GOVERNANCE_DOCUMENTATION_INDEX.md` | 治理文档索引（13 份规格文件导航） |
| `GOVERNANCE_IMPLEMENTATION_CHECKLIST.md` | 治理实现清单（需求→代码映射 + 完成度追踪） |
| `GOVERNANCE_QUICK_REFERENCE.md` | 治理速查手册（16 根原则 + 状态机速览） |
| `OPENCLAW_GOVERNANCE_SUMMARY.md` | 治理综合摘要（13 份文件结构化总结） |
| `OPENCLAW_TECHNICAL_SPEC.md` | 技术规格总结（22 份治理规格集） |

#### governance_dev/changelogs/ — T2.01–T2.23 模组变更日志（23 份）

每份治理模组的实现变更日志，命名格式 `2026-03-29_T2.XX_模组名.md`。

#### governance_dev/phase2_execution/ — Phase 2 治理模組执行记录

| 文件 | 内容 |
|------|------|
| `T2_EXECUTION_SUMMARY.md` | ★ Phase 2 执行总览：21 模组矩阵 + 关键指标 |
| `T2_PM_QUALITY_AUDIT_REPORT.md` | Phase 2 PM 品质审核报告（T2.01–T2.23，整体 4/5，0 个 P0 blocker） |
| `T2_TW_COMMENT_AUDIT_REPORT.md` | Phase 2 TW 注释品质审核报告（评级 9.5/10，100% 双语覆盖） |
| `T2_TEST_RESULTS.md` | T2 测试套件执行报告（1485 测试） |
| `PM_FA_FULL_COMPLIANCE_AUDIT.md` | PM + FA 完整合规审计 |
| `PM_T0_ENGINEERING_AUDIT.md` | PM T0 工程审计 |
| `REVIEW_T2_CODE_QUALITY.md` | T2 代码质量审查 |
| `DOCUMENTATION_REVIEW_T2.07-LATEST.md` | T2.07+ 文档审查 |
| `FIXTURE_REFACTOR_SUMMARY.md` | 测试 Fixture 重构总结 |
| `TEST_FIXTURE_OVERVIEW.md` | 测试 Fixture 重构概览 |

#### governance_dev/phase3_integration/ — Phase 3 治理集成

| 文件 | 内容 |
|------|------|
| `PHASE3_WORK_PLAN.md` | Phase 3 工作计划（从 72% 到可安全交易） |
| `T3.01_FA_INTEGRATION_DESIGN.md` | FA 集成设计 |
| `T3_GOVERNANCE_INTEGRATION_GUIDE.md` | Phase 3 治理集成指南 |
| `PHASE3_CODE_REVIEW_REPORT.md` | Phase 3 代码审查报告 |
| `SECURITY_AUDIT_PHASE3.md` | Phase 3 安全审计报告 |
| `2026-03-30_TW_ENGINEERING_AUDIT_REPORT.md` | TW 工程审计报告 |
| `REVIEW_GOVERNANCE_GUI.md` | GUI 治理集成审查（PASS） |

#### governance_dev/phase4_acceptance/ — Phase 4 验收

| 文件 | 内容 |
|------|------|
| `T4.01_CC_COMPLIANCE_MATRIX.md` | CC 合规矩阵 |
| `T4.02_E4_TEST_COVERAGE_REPORT.md` | E4 测试覆盖报告 |
| `T4.03_A3_UX_REVIEW_REPORT.md` | A3 UX 审查报告 |
| `T4.04_R4_DOCUMENT_AUDIT_REPORT.md` | R4 文档审计报告 |
| `T4.05_PM_FINAL_ACCEPTANCE_REPORT.md` | PM 最终验收报告 |
| `T4.06_PM_GUI_GOVERNANCE_PLAN.md` | PM GUI 治理计划 |
| `TEST_REPORT_GOVERNANCE_E4.md` | E4 测试工程师验收报告 |

#### governance_dev/phase1–12 其他阶段 — 各阶段任务书 + PM 验收 + FA 缺口审计

每阶段通常包含：`PHASE*_TASK_BOOK`, `PHASE*_PM_ACCEPTANCE_REPORT`, `FA_GAP_AUDIT_REPORT`。
详见各子目录。

---

### CCAgentWorkSpace/ — Agent 獨立工作空間（2026-03-31 新增）

15 個 Agent 角色各自的獨立工作空間。每個 Agent 有 `profile.md`（角色定位）、`memory.md`（工作記憶）、`workspace/`（報告存檔）。

| 目錄 | Agent | 層次 |
|------|-------|------|
| `CCAgentWorkSpace/PM/` | Project Manager | 管理層 |
| `CCAgentWorkSpace/FA/` | Functional Auditor | 管理層 |
| `CCAgentWorkSpace/PA/` | Project Architect | 管理層 |
| `CCAgentWorkSpace/CC/` | Compliance Checker | 質量保證層 |
| `CCAgentWorkSpace/E2/` | Code Reviewer | 質量保證層 |
| `CCAgentWorkSpace/E3/` | Security Auditor | 質量保證層 |
| `CCAgentWorkSpace/E4/` | Test Engineer | 質量保證層 |
| `CCAgentWorkSpace/E5/` | Optimization Engineer | 質量保證層 |
| `CCAgentWorkSpace/E1/` | Backend Developer | 執行層 |
| `CCAgentWorkSpace/E1a/` | Frontend Developer | 執行層 |
| `CCAgentWorkSpace/A3/` | UX Auditor | 專項審查層 |
| `CCAgentWorkSpace/R4/` | Document Auditor | 專項審查層 |
| `CCAgentWorkSpace/TW/` | Technical Writer | 專項審查層 |
| `CCAgentWorkSpace/AI-E/` | AI Effectiveness Evaluator | 分析層 |
| `CCAgentWorkSpace/QA/` | Quality Assurance | 分析層 |
