# 自主交易 Agent：市场扫描器 + 策略自动部署 + Demo 同步 + 登录系统
# Autonomous Agent: Market Scanner + Auto-Deployer + Demo Sync + Login System

**日期 / Date**: 2026-03-27（晚间 session）
**状态 / Status**: 已完成

---

## 一、市场扫描器 (MarketScanner)

- 每 5 分钟扫描 Bybit 全市场 linear perpetuals（~650 个交易对）
- 过滤：最低 $5M 日成交量 + 最低 $0.01 价格 + 仅 USDT 对
- 分类评分：funding_arb / grid / trend / reversion / breakout
- 评分依据：funding rate / 波动率 / 价格变动 / 成交量
- 首次扫描结果：650 个符号 → 10 个机会

## 二、策略自动部署器 (StrategyAutoDeployer)

- 接收扫描结果，自动创建对应策略实例
- 最大 5 个同时交易品种（可配置）
- 自动添加新品种到 KlineManager + 引导历史 K线
- 自动注册到编排器 + 激活
- 首次部署：5 个 MA_Crossover 策略（SIRENUSDT, WHITEWHALEUSDT, CUSDT, BSBUSDT, STGUSDT）

## 三、Bybit Demo 修复

- Demo connector 确认正常（手动测试下单成功）
- 问题定位：不是 connector bug，是策略太谨慎（regime 过滤 + 冷却期），intent 产生少
- Demo 数据同步器 (BybitDemoSync)：每 60 秒拉取成交/持仓/余额写入 PostgreSQL

## 四、登录系统

- `POST /api/v1/auth/login`：username/password → Bearer token
- `login.html`：统一登录页
- 所有页面 (/trading, /console, /gui) 无 token 自动跳转 /login
- 凭证存储：`/home/ncyu/BybitOpenClaw/secrets/gui_auth.env`

## 五、Bybit AI 调研结论

- TradeGPT：无 API，仅 UI + Telegram Bot，无法程序化接入
- AI Trading Skills：是 V5 API 包装，我们已在使用相同 API
- 结论：不值得接入，我们自己的 L2 AI 推理引擎更适合

## 六、新建文件

| 文件 | 用途 |
|------|------|
| `local_model_tools/market_scanner.py` | 市场扫描器 |
| `local_model_tools/strategy_auto_deployer.py` | 策略自动部署器 |
| `app/bybit_demo_sync.py` | Bybit Demo 数据同步器 |
| `app/grafana_data_writer.py` | Grafana PostgreSQL 写入器 |
| `app/bybit_demo_connector.py` | Bybit Demo 连接器 |
| `app/telegram_alerter.py` | Telegram 告警 |
| `app/static/login.html` | 登录页 |
| `app/static/trading.html` | TradingView K线页 |
