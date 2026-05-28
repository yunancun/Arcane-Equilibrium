# GUI 三层架构实现 + 登录系统 + Bybit Demo Trading
# GUI Three-Layer Implementation + Login System + Bybit Demo Trading

**日期 / Date**: 2026-03-27
**状态 / Status**: 已完成

---

## 一、三层 GUI 架构

### Layer 1: Grafana 运营监控
- **部署**: Docker (`trading_grafana`)，端口 3000
- **数据源**: PostgreSQL (trading_ai) + FastAPI JSON API
- **5 个仪表盘**: 系统总览 / 交易 PnL / AI 成本 / 持仓订单 / 行情风控
- **数据写入**: `grafana_data_writer.py` 每 30 秒写入 4 张表
  - `paper_pnl_snapshots`: 余额 / PnL / 手续费
  - `market_tickers`: BTC/ETH 实时价格
  - `system_health`: K线管理器 + 管线桥接器状态
  - `trade_executions`: 成交记录（增量写入）
- **访问**: `http://trade-core:3000` (admin/<REDACTED>) 或 console 内 iframe

### Layer 2: TradingView K线图表
- **技术**: TradingView Lightweight Charts v4.1.0 (CDN)
- **功能**: K线图 + 成交量 + 信号标记 + 指标面板 + 策略列表 + PnL + 信号历史
- **访问**: console 内 📊 K线图表 tab
- **数据**: 从 FastAPI 实时拉取（/strategy/klines, /strategy/signals 等）

### Layer 3: Bybit Demo Trading
- **连接器**: `bybit_demo_connector.py`
- **API**: `https://api-demo.bybit.com` (V5)
- **双重执行**: 每个 OrderIntent 同时提交到 Paper Engine + Bybit Demo
- **Demo 余额**: 50K USDT + 50K USDC + 1 BTC + 1 ETH
- **路由**: /strategy/demo/status, /strategy/demo/balance, /strategy/demo/positions
- **验证**: 可在 bybit.com Demo Trading 模式查看订单

---

## 二、统一控制台

### 入口
`http://trade-core:8000` → 自动重定向到 `/console`

### 4 个 Tab
1. **控制台 / Dashboard** — 主控面板（runtime summary, chapter status, paper trading）
2. **📊 K线图表 / Charts** — TradingView 图表 + 信号 + 策略
3. **📈 监控 / Grafana** — Grafana 仪表盘 iframe
4. **OpenClaw** — OpenClaw Gateway 控制

---

## 三、登录认证系统

### 后端
- `POST /api/v1/auth/login`: 验证 username/password → 返回 Bearer token
- 凭证读取: `/home/ncyu/BybitOpenClaw/secrets/gui_auth.env`
- 常数时间比较: `hmac.compare_digest`

### 前端
- `login.html`: 统一登录页（暗色主题 + 🦞 Logo）
- 所有页面 (/trading, /console, /gui) 无 token 自动跳转到 /login
- Token 存 localStorage，所有页面共享
- 登出按钮清除 token + 跳转

---

## 四、Grafana 数据写入器

- `grafana_data_writer.py`: 守护线程，每 30 秒写入
- 连接 PostgreSQL (trading_postgres:5432/trading_ai)
- 依赖: psycopg2-binary（已安装到 venv）
- 在 phase2_strategy_routes.py 单例初始化时启动

---

## 五、新建文件

| 文件 | 用途 |
|------|------|
| `app/static/login.html` | 统一登录页 |
| `app/static/trading.html` | TradingView K线图表页 |
| `app/grafana_data_writer.py` | Grafana PostgreSQL 数据写入器 |
| `app/bybit_demo_connector.py` | Bybit Demo Trading 连接器 |
| `docker_projects/monitoring_services/docker-compose.yml` | Grafana 容器 |
| `docker_projects/monitoring_services/init_trading_schema.sql` | 数据库 schema |
| `docker_projects/monitoring_services/provisioning/` | Grafana 数据源配置 |
| `docker_projects/monitoring_services/dashboards/*.json` | 5 个仪表盘 |

---

## 六、访问地址汇总

| URL | 功能 |
|-----|------|
| `http://trade-core:8000` | 统一控制台（需登录） |
| `http://trade-core:8000/login` | 登录页 |
| `http://trade-core:8000/trading` | K线图表（独立页） |
| `http://trade-core:3000` | Grafana (admin/<REDACTED>) |
| `https://trade-core.tail358794.ts.net` | OpenClaw Gateway |
