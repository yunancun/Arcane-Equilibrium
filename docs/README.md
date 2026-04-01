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
│   ├── control_api_gui/               ← Control API + GUI Operator Console 开发
│   └── learning/                      ← L 章节：自动学习管线 / 安全加固
│
├── handoffs/                          ← 阶段交接文档（按日期+主题分文件夹）
│   └── YYYY-MM-DD_主题名/
│
├── decisions/                         ← 重大架构/设计决策记录 + 治理源文件（DOC/SM/EX .docx）
│
├── audit/                             ← ★ 全系统审计报告（按月份分目录）
│   ├── March31/                       ← 2026-03-31 七Agent全系统审计（8 份报告）
│   └── April01/                       ← 2026-04-01 十Agent全系统审计（10 份报告）
│
├── references/                        ← 长期参考文档（规范、合同、规格书）
│   ├── state_dictionary/              ← 状态字典 / 数据字典
│   ├── api_contract/                  ← API 合同 / 路由草案 / 审核报告
│   └── api_stub/                      ← API 骨架代码
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

### 4. audit/ — 全系统审计报告

**用途**：全系统审计报告归档。按月份分子目录（March31、April01 等），每次审计产出多角色报告。

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

### worklogs/control_api_gui/ — Control API + GUI 开发日志（2026-03-25 ~ 2026-03-26）

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

### audit/March31/ — ★★★ 2026-03-31 七Agent全系统审计（7 份报告 + 1 份双语注释审计）

| 文件 | 内容 |
|------|------|
| `E3_security_audit_2026-03-31.md` | E3 安全审计：3 CRITICAL / 5 HIGH / 6 MEDIUM / 5 LOW（gate 绕过 · 注入 · 密钥泄漏） |
| `CC_compliance_check_2026-03-31.md` | CC 合规检查：11/16 原则完全合规，B 级，1 硬违规，9 缺口 |
| `E4_testing_report_2026-03-31.md` | E4 测试评估：71 文件/2480 用例，pipeline_bridge 15%，governance_routes 10% |
| `E5_optimization_report_2026-03-31.md` | E5 优化评估：49 项（3 Critical · 14 High · 22 Medium · 10 Low），含性能/重复/可读性 |
| `A3_gui_usability_report_2026-03-31.md` | A3 GUI 可用性：6.2/10，工程师视角设计，术语友好化建议 |
| `PM_review_2026-03-31.md` | ★ PM 整合审核：71 项去重，P0-P3 批次计划，~110h 工时，依赖图 |
| `PA_review_2026-03-31.md` | ★ PA 技术复验：4 CRITICAL 确认属实，1 误报，6 架构层补充问题 |
| `bilingual_comment_audit_report.md` | TW 双语注释审计报告（模块级双语覆盖评估） |

### audit/April01/ — ★★★ 2026-04-01 十Agent全系统审计（10 份报告）

| 文件 | 内容 |
|------|------|
| `AI-E_ai_effectiveness_audit_2026-04-01.md` | AI-E AI 效果审计：AI 使用效率/成本分析/模型分配评估/Ollama 优化建议 |
| `CC_compliance_check_2026-04-01.md` | CC 合规检查：16 条根原则逐一验证 + 硬边界合规状态 |
| `E3_security_audit_2026-04-01.md` | E3 安全审计：认证授权/注入/密钥管理/OWASP 安全扫描 |
| `E4_testing_report_2026-04-01.md` | E4 测试评估：测试覆盖/回归/边界用例/并发测试评估 |
| `E5_optimization_report_2026-04-01.md` | E5 优化评估：代码精简/性能/可读性评估建议 |
| `FA_functional_gap_audit_2026-04-01.md` | FA 功能缺口审计：功能规格验证/Gap 分析/业务逻辑审查 |
| `TW_documentation_quality_2026-04-01.md` | TW 文档与注释品质审计：双语注释/MODULE_NOTE 规范评估 |
| `R4_document_index_audit_2026-04-01.md` | R4 文档索引审计：文档目录完整性/交叉引用准确性 |
| `PA_review_2026-04-01.md` | PA 技术复验：架构决策/可行性评估/副作用识别 |
| `PM_execution_plan_2026-04-01.md` | PM 执行计划：优先级整合/批次计划/风险管理 |

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
