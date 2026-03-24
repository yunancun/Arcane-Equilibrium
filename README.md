# srv

这是交易 AI 系统的主根目录。  
This is the main root folder of the trading AI system.

这里存放整个系统的核心结构，包括容器部署、配置文件、数据、数据库文件、日志、程序代码、研究记录、脚本、备份和历史归档。  
This folder contains the core structure of the whole system, including container deployment, configuration files, data, database files, logs, program code, research records, scripts, backups, and historical archives.

---

## 当前最重要的项目导航入口 / Most Important Current Project Navigation

如果当前接手的是 **OpenClaw / Bybit** 项目，请优先阅读以下文档，而不是直接依赖更早的旧总报告。  
If you are taking over the **OpenClaw / Bybit** project, read the following documents first instead of relying directly on older historical reports.

### 1. 顶层导航索引 / Top-level navigation index
- `program_code/exchange_connectors/bybit_connector/docs/OPENCLAW_BYBIT_TOP_LEVEL_INDEX_2026-03-25.md`

用途：  
Purpose:
- 这是当前最推荐的顶层入口。  
- It is the recommended top-level entry point right now.
- 它会告诉你应该先看哪些文档、哪些 builder / runner / runtime latest 最重要。  
- It tells you which docs, builders, runners, and runtime latest artifacts matter most.
- 它也会明确提醒：**J/K 做完不等于 execution 放权**。  
- It also explicitly warns that **J/K being done does not mean execution authority is opened**.

### 2. 本轮总工程记录 / Current round work report
- `program_code/exchange_connectors/bybit_connector/docs/WORK_REPORT_2026-03-25_JK_FUNCTIONAL_CLOSEOUT.md`

用途：  
Purpose:
- 这是 2026-03-24 晚到 2026-03-25 凌晨这一轮 J/K 集中收口的总工程记录。  
- This is the integrated work report for the concentrated J/K closeout round from the 2026-03-24 night session into the 2026-03-25 early-morning session.
- 它解释了本轮到底做了什么、最终结论是什么、哪些边界不能误读。  
- It explains what was done in the round, what the final conclusions are, and which boundaries must not be misread.

### 3. J / K 章节功能收口基线 / J/K functional closeout baselines
- `program_code/exchange_connectors/bybit_connector/docs/J_FUNCTIONAL_CLOSEOUT_BASELINE_2026-03-25.md`
- `program_code/exchange_connectors/bybit_connector/docs/K_FUNCTIONAL_CLOSEOUT_BASELINE_2026-03-25.md`
- `program_code/exchange_connectors/bybit_connector/docs/JK_STAGE_STATUS_BASELINE_2026-03-25.md`

用途：  
Purpose:
- 这些文档定义了 J/K 当前“做完”的严格含义。  
- These docs define the strict current meaning of J/K being “done”.
- 它们是判断章节是否真正收口、但又没有误开 execution 的最佳入口。  
- They are the best entry points for checking whether a chapter is truly closed out without accidentally treating execution as open.

---

## 当前权威章节状态（OpenClaw / Bybit） / Current Authoritative Chapter Status (OpenClaw / Bybit)

### I 章 / Chapter I
- **canonical closed**
- 正确解释：**shadow-only decision-lease control plane closed**
- 不是 live-execution ready

- **canonical closed**
- Correct interpretation: **shadow-only decision-lease control plane closed**
- It is not live-execution ready

### J 章 / Chapter J
- **functionally closed for this round**
- 严格解释：`functional_closeout_ready_shadow_only`
- 仍是 **shadow / skeleton-only**
- execution remains closed

- **functionally closed for this round**
- Strict interpretation: `functional_closeout_ready_shadow_only`
- It remains **shadow / skeleton-only**
- execution remains closed

### K 章 / Chapter K
- **functionally closed for this round**
- 严格解释：`functional_closeout_ready_design_only_gate_closed`
- 仍是 **design-only gate closed**
- paper/live execution remain closed

- **functionally closed for this round**
- Strict interpretation: `functional_closeout_ready_design_only_gate_closed`
- It remains **design-only gate closed**
- paper/live execution remain closed

### 当前最重要的全局边界 / Most important current global boundary
- `system_mode = read_only`
- `execution_state = disabled`

禁止误读：  
Forbidden misreadings:
- “J 做完了，所以 execution 打开了”  
- “J is done, so execution is open”
- “K 做完了，所以 demo gate 可以打开了”  
- “K is done, so the demo gate may open now”
- “K capability 都补齐了，所以 paper execution ready 了”  
- “K capability chains are complete, so paper execution is ready”

---

## OpenClaw / Bybit 推荐阅读顺序 / Recommended Reading Order for OpenClaw / Bybit

如果时间有限，建议按以下顺序阅读：  
If time is limited, read in this order:

1. `OPENCLAW_BYBIT_TOP_LEVEL_INDEX_2026-03-25.md`
2. `WORK_REPORT_2026-03-25_JK_FUNCTIONAL_CLOSEOUT.md`
3. `J_FUNCTIONAL_CLOSEOUT_BASELINE_2026-03-25.md`
4. `K_FUNCTIONAL_CLOSEOUT_BASELINE_2026-03-25.md`
5. `JK_STAGE_STATUS_BASELINE_2026-03-25.md`
6. 再回看 2026-03-24 的 canonical baseline / chapter closure baseline 作为历史兼容背景  
   Then revisit the 2026-03-24 canonical baselines / chapter closure baselines as compatibility background.

---

## 主要子目录说明 / Main Subfolder Overview

- `docker_projects`：存放 Docker Compose 项目和服务部署文件。  
  `docker_projects`: stores Docker Compose projects and service deployment files.

- `settings`：存放系统配置、策略规则、风控规则、AI 提示词和说明文档。  
  `settings`: stores system settings, strategy rules, risk control rules, AI prompt templates, and human-readable notes.

- `stored_data`：存放行情数据、交易数据、信号数据、回测结果和资金追踪数据。  
  `stored_data`: stores market data, trading data, signal data, backtest results, and fund tracking data.

- `database_files`：存放 PostgreSQL、Redis、向量数据库和 Grafana 的持久化数据文件。  
  `database_files`: stores persistent data files for PostgreSQL, Redis, vector database, and Grafana.

- `log_files`：存放系统日志、Docker 日志、行情日志、AI 日志、交易执行日志和审计日志。  
  `log_files`: stores system logs, Docker logs, market logs, AI logs, trade execution logs, and audit logs.

- `program_code`：存放交易系统、AI Agent、数据处理和报表相关代码。  
  `program_code`: stores code for the trading system, AI agents, data processing, and reports.

- `research_notes`：存放研究笔记、实验记录和市场观察。  
  `research_notes`: stores research notes, experiment records, and market observations.

- `helper_scripts`：存放部署、备份、维护和测试脚本。  
  `helper_scripts`: stores deployment, backup, maintenance, and testing scripts.

- `backup_files`：存放本地备份、备份记录和 NAS 同步记录。  
  `backup_files`: stores local backups, backup records, and NAS sync records.

---

## 最终提醒 / Final Reminder

这个根目录应尽量保持整洁和稳定，因为它是整个项目的主入口。  
This root folder should remain clean and stable because it is the main entry point of the whole project.

对于 OpenClaw / Bybit 项目，今后默认应从 **顶层导航索引** 开始，而不是直接从旧总报告开始。  
For the OpenClaw / Bybit project, future maintenance should default to the **top-level navigation index** first, rather than starting directly from older historical reports.
