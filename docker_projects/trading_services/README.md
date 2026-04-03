# trading_services

这里存放交易执行层相关服务的部署文件。
This folder stores deployment files related to the trading execution layer.

当前阶段系统状态：
Current system state:

- 交易环境：demo_only（Paper + Bybit Demo）
- Trading environment: demo_only (Paper + Bybit Demo)

- 主交易所：Bybit（专攻）
- Primary exchange: Bybit (exclusive focus)

- Bybit 模式：demo_only
- Bybit mode: demo_only

- Binance：已排除当前开发范围，仅作为超长期可能方向保留
- Binance: excluded from current scope, retained only as long-term possibility

- Agent 权限等级：Level 0 / observer
- Agent permission level: Level 0 / observer

- 自动执行：关闭
- Autonomous execution: disabled

当前阶段仅部署骨架服务，不执行真实交易。
At the current stage, only skeleton services are deployed and no real trading is executed.

当前骨架服务包括：
Current skeleton services include:

- bybit_connector
- pretrade_risk_gate
- audit_logger
