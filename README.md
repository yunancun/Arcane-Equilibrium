# srv
# srv

这是交易 AI 系统的主根目录。
This is the main root folder of the trading AI system.

这里存放整个系统的核心结构，包括容器部署、配置文件、数据、数据库文件、日志、程序代码、研究记录、脚本、备份和历史归档。
This folder contains the core structure of the whole system, including container deployment, configuration files, data, database files, logs, program code, research records, scripts, backups, and historical archives.

主要子目录说明：
Main subfolder overview:

- docker_projects：存放 Docker Compose 项目和服务部署文件。
- docker_projects: stores Docker Compose projects and service deployment files.

- settings：存放系统配置、策略规则、风控规则、AI 提示词和说明文档。
- settings: stores system settings, strategy rules, risk control rules, AI prompt templates, and human-readable notes.

- stored_data：存放行情数据、交易数据、信号数据、回测结果和资金追踪数据。
- stored_data: stores market data, trading data, signal data, backtest results, and fund tracking data.

- database_files：存放 PostgreSQL、Redis、向量数据库和 Grafana 的持久化数据文件。
- database_files: stores persistent data files for PostgreSQL, Redis, vector database, and Grafana.

- log_files：存放系统日志、Docker 日志、行情日志、AI 日志、交易执行日志和审计日志。
- log_files: stores system logs, Docker logs, market logs, AI logs, trade execution logs, and audit logs.

- program_code：存放交易系统、AI Agent、数据处理和报表相关代码。
- program_code: stores code for the trading system, AI agents, data processing, and reports.

- research_notes：存放研究笔记、实验记录和市场观察。
- research_notes: stores research notes, experiment records, and market observations.

- helper_scripts：存放部署、备份、维护和测试脚本。
- helper_scripts: stores deployment, backup, maintenance, and testing scripts.

- backup_files：存放本地备份、备份记录和 NAS 同步记录。
- backup_files: stores local backups, backup records, and NAS sync records.

- old_archive：存放旧日志、旧回测、旧报表和旧导出文件。
- old_archive: stores old logs, old backtests, old reports, and old exported files.

这个根目录应尽量保持整洁和稳定，因为它是整个项目的主入口。
This root folder should remain clean and stable because it is the main entry point of the whole project.
