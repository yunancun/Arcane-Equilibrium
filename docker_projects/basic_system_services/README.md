# basic_system_services
# basic_system_services

这里存放交易 AI 系统最基础底层服务的部署文件。
This folder stores deployment files for the most basic underlying services of the trading AI system.

当前主要包括：
The current layer mainly includes:

- PostgreSQL：主业务数据库。
- PostgreSQL: the main business database.

- Redis：缓存、状态和轻量消息服务。
- Redis: cache, state, and lightweight message service.

- Qdrant：向量数据库，用于新闻、情报和 AI 记忆检索。
- Qdrant: vector database for news, intelligence, and AI memory retrieval.

这一层为 OpenClaw、市场数据、交易执行和后续 AI Agent 提供基础支撑。
This layer provides the base support for OpenClaw, market data services, trade execution, and later AI agents.
