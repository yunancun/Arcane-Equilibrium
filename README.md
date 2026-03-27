# OpenClaw / Bybit AI Agent Trading System
<!-- Git 日志 — 项目入口。主日志见 CLAUDE.md -->

AI Agent 自动交易系统 — 自主扫描 650+ 交易对，智能部署策略，双重执行（Paper + Bybit Demo）。

---

## 🖥️ GUI 访问（Tailscale 网络内）

| 地址 | 功能 |
|------|------|
| **[http://trade-core:8000](http://trade-core:8000)** | **统一控制台**（登录后进入 4 Tab 视图） |
| [http://trade-core:3000](http://trade-core:3000) | Grafana 运营监控仪表盘 |
| [https://trade-core.tail358794.ts.net](https://trade-core.tail358794.ts.net) | OpenClaw Gateway |

### 统一控制台 Tab

| Tab | 内容 |
|-----|------|
| 控制台 / Dashboard | 系统状态 + Paper Trading + 章节状态 |
| 📊 K线图表 / Charts | TradingView K线 + 信号标记 + 策略面板 |
| 📈 监控 / Grafana | PnL 曲线 + 交易记录 + 系统健康 |
| OpenClaw | OpenClaw Gateway 控制 |

---

## 当前状态 (2026-03-27)

```
系统模式:     read_only（不变）
执行权限:     disabled / not_granted（不变）
测试:         644 全通过
API 路由:     111 条
信号规则:     8 条（4入场 + 2退出 + 1regime + 1divergence）
策略:         5 类（Grid + MA + BB Reversion + BB Breakout + FundingRate Delta-Neutral）
市场扫描:     650+ 交易对每 5 分钟全扫描
自动部署:     最优 5 品种自动匹配策略
执行模式:     双重执行（Paper Engine + Bybit Demo sandbox）
```

**已完成**: A-L + 策略工具包 + 管线桥接 + 全系统审核 + GUI 三层 + 自主交易 Agent

---

## 项目结构

```
srv/
├── CLAUDE.md                      ← ★ 项目完整上下文
├── docs/                          ← 工程文档（20+ 份日志/审核/设计）
├── program_code/
│   ├── exchange_connectors/
│   │   └── bybit_connector/
│   │       └── control_api_v1/    ← FastAPI 109 路由 + 426 测试
│   │           ├── app/
│   │           │   ├── pipeline_bridge.py       ← 管线桥接器
│   │           │   ├── stop_manager.py          ← 止损管理器（→ local_model_tools）
│   │           │   ├── bybit_demo_connector.py  ← Bybit Demo 连接器
│   │           │   ├── grafana_data_writer.py   ← Grafana 数据写入
│   │           │   ├── telegram_alerter.py      ← Telegram 告警
│   │           │   └── static/                  ← GUI (login/console/trading)
│   │           └── tests/
│   ├── local_model_tools/         ← 策略工具包 + 218 测试
│   │   ├── kline_manager.py       ← K线聚合 + REST 引导
│   │   ├── indicator_engine.py    ← 7 指标协调
│   │   ├── signal_generator.py    ← 8 信号规则
│   │   ├── strategies/            ← 5 策略
│   │   ├── stop_manager.py        ← Hard/Trailing/Time Stop + ATR 仓位
│   │   └── strategy_orchestrator.py
│   ├── ai_agents/                 ← H1-H5 AI 治理层
│   ├── risk_control/              ← H0 本地判断
│   └── trade_executor/            ← I 决策租约
├── docker_projects/
│   ├── monitoring_services/       ← Grafana + 5 仪表盘
│   └── trading_services/          ← PostgreSQL
└── helper_scripts/
    ├── start_paper_trading.sh     ← 一键启动
    ├── cron_observer_cycle.sh     ← Observer 自动化
    └── maintenance_scripts/       ← 清理 / 检查脚本
```

---

## 核心设计原则

1. **Net PnL** — 扣除 AI 成本、手续费、滑点后的净收益
2. **本地先做** — H0 确定性判断，AI 只做高价值部分
3. **AI 输出 ≠ 即时命令** — Decision Lease 带时效、可撤销
4. **权限按表现赢得** — 不自动升级
5. **先系统健康后市场判断**
6. **失败默认收缩** — fail-closed

---

## 硬边界

```python
system_mode            = "read_only"
execution_state        = "disabled"
execution_authority    = "not_granted"
live_execution_allowed = False
```

---

## 部署

```bash
# API 服务器（systemd，开机自启）
systemctl --user status openclaw-trading-api    # 端口 8000
systemctl --user status openclaw-gateway        # OpenClaw + Tailscale HTTPS

# Grafana
cd docker_projects/monitoring_services && docker compose up -d   # 端口 3000

# 一键启动 Paper Trading
bash helper_scripts/start_paper_trading.sh
```

---

GitHub: [yunancun/BybitOpenClaw](https://github.com/yunancun/BybitOpenClaw)
