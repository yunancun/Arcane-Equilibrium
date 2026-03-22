# trading_services
# trading_services

这里存放交易执行层相关服务的部署文件。
This folder stores deployment files related to the trading execution layer.

当前阶段系统状态：
Current system state:

- 交易环境：paper
- Trading environment: paper

- 主交易所：Bybit
- Primary exchange: Bybit

- 辅助交易所：Binance
- Secondary exchange: Binance

- Bybit 模式：read_only
- Bybit mode: read_only

- Binance 模式：read_only
- Binance mode: read_only

- Agent 权限等级：Level 0 / observer
- Agent permission level: Level 0 / observer

- 自动执行：关闭
- Autonomous execution: disabled

当前阶段仅部署骨架服务，不执行真实交易。
At the current stage, only skeleton services are deployed and no real trading is executed.

当前骨架服务包括：
Current skeleton services include:

- bybit_connector
- bybit_connector

- binance_connector
- binance_connector

- pretrade_risk_gate
- pretrade_risk_gate

- audit_logger
- audit_logger
