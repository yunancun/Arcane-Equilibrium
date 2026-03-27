# OpenClaw / Bybit AI Agent Trading System

AI Agent 自动交易系统 — 以 OpenClaw 为中枢、Bybit 为主交易所。

---

## 当前状态 (2026-03-27)

```
系统模式:     read_only（不变）
执行权限:     disabled / not_granted（不变）
测试:         620 全通过
API 路由:     104 条
```

**已完成章节**: A-L 全部 + Paper Trading Engine + Layer 2 AI 推理引擎 + 全品类风控框架 + Phase 2 本地策略工具包

**下一步**: 远程安全访问 → Telegram 告警 → 自动循环 cron → Beta 数据积累 → M 章（Supervised Live）

---

## 项目结构

```
srv/
├── CLAUDE.md                  ← ★ 项目完整上下文（章节树/架构/原则/状态）
├── docs/                      ← 工程文档（日志/交接/决策/参考）
│   └── README.md              ← 文档目录规范 + 索引
├── program_code/
│   ├── exchange_connectors/
│   │   └── bybit_connector/
│   │       ├── control_api_v1/    ← Control API（FastAPI，104 路由）
│   │       │   ├── app/           ← 路由 + 业务逻辑
│   │       │   └── tests/         ← 428 测试
│   │       └── ...                ← Observer / H0-H5 / I1-I10 / J / K
│   ├── local_model_tools/         ← Phase 2 本地策略工具包
│   │   ├── kline_manager.py       ← Tick→OHLCV K线聚合
│   │   ├── indicator_engine.py    ← 指标计算协调器
│   │   ├── indicators/            ← SMA/EMA/RSI/BB/MACD/ATR/Stochastic
│   │   ├── signal_generator.py    ← 信号规则引擎
│   │   ├── strategies/            ← MA Crossover / BB / Funding Rate / Grid
│   │   ├── strategy_orchestrator.py ← 策略编排器
│   │   └── tests/                 ← 192 测试
│   └── ai_agents/                 ← AI Agent 模块
├── docker_projects/           ← Docker Compose 部署
├── settings/                  ← 配置 / 规则 / AI 提示词
├── stored_data/               ← 行情 / 交易 / 回测数据
├── database_files/            ← PostgreSQL / Redis 持久化
├── log_files/                 ← 系统日志
├── helper_scripts/            ← 部署 / 维护脚本
└── research_notes/            ← 研究笔记
```

---

## 核心设计原则

1. **Net PnL** — 扣除 AI API 成本、手续费、滑点后的净收益
2. **本地先做** — 确定性判断本地执行（H0），AI 只做高价值部分
3. **AI 输出 ≠ 即时命令** — AI → Decision Lease → 本地复核 → 执行
4. **权限按表现赢得** — 不按时间自动升级
5. **先系统健康后市场判断** — 系统不健康时不行动
6. **失败默认收缩** — fail-closed，不猜测

---

## 关键文档导航

| 文档 | 用途 |
|------|------|
| `CLAUDE.md` | 项目完整上下文（章节树、架构、原则、当前状态） |
| `docs/README.md` | 文档目录规范 + 全量索引 |
| `docs/references/2026-03-27--phase2_strict_audit_report.md` | Phase 2 审核报告 |
| `docs/references/2026-03-27--phase1_risk_framework_and_agent_autonomy_design.md` | 全品类风控框架设计 |

---

## 硬边界

```python
system_mode            = "read_only"      # 不可改
execution_state        = "disabled"        # 不可改
execution_authority    = "not_granted"     # 不可改
live_execution_allowed = False             # 不可改
```

---

## 部署

```bash
# API 服务器（systemd 用户服务）
systemctl --user status openclaw-trading-api
# 绑定 127.0.0.1:8000，远程访问通过 SSH 隧道
```

---

GitHub: [yunancun/BybitOpenClaw](https://github.com/yunancun/BybitOpenClaw)
