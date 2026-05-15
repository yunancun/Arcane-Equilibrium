# 玄衡 · Arcane Equilibrium
<!-- Git 日志 — 项目入口。主日志见 CLAUDE.md -->

Agentic trading governance system — 自主扫描 650+ 交易对，智能部署策略，**Live_Ready ⚠️**（5 项 live gate 全绿才上真实 live，见下文门控表）。

**软更名口径（2026-05-06）**：
- 正式项目名：**玄衡 · Arcane Equilibrium**。
- **OpenClaw** 保留为控制平面 / Gateway / Console / 通信服务族名称。
- **Bybit** 保留为唯一交易所 adapter / connector 名称。
- 短期不改 `openclaw_engine`、`OPENCLAW_*`、`/tmp/openclaw`、GitHub 仓库名、Linux runtime 路径等运行面名称。

---

## 🖥️ GUI 访问（Tailscale 网络内）

| 地址 | 功能 |
|------|------|
| **[http://trade-core:8000](http://trade-core:8000)** | **OpenClaw Control Console**（唯一 canonical GUI；登录后进入现有 FastAPI 控制台） |
| [http://trade-core:3000](http://trade-core:3000) | Grafana 运营监控仪表盘 |
| [https://trade-core.tail358794.ts.net](https://trade-core.tail358794.ts.net) | OpenClaw Gateway / Tailscale HTTPS 入口（通信与远程入口，不是第二套交易 GUI） |

### OpenClaw Control Console 核心 Tab

| Tab | 内容 |
|-----|------|
| `system` | 系统总览、运行状态、章节状态 |
| `replay` | replay / Stage 0R 诊断与报告入口 |
| `paper` | Paper 状态展示；promotion evidence 已由 AMD-2026-05-15-01 冻结 |
| `demo` | Demo trading / Stage 1 demo micro-canary 目标环境（当前未开放） |
| `live` | Live_Ready 仪表盘、余额/PnL/持仓/成交/API key 管理 |
| `strategy` | 策略部署、scanner、品种管理 |
| `risk` | 风控参数、止损、denylist |
| `governance` | GovernanceHub、授权、Decision Lease、对账 |
| `ai` | Layer2Engine、本地/云模型、成本追踪 |
| `learning` | Learning Cockpit、promotion evidence、ML/feature 状态 |
| `agents` | 本地 5-Agent 只读状态 / proposal relay 入口 |
| `monitoring` | Grafana 与系统健康 |
| `settings` | 参数、环境、维护操作 |

---

## 当前状态

实时面板：[`CLAUDE.md` §三](CLAUDE.md) — HEAD / 5 策略 7d gross PnL / Active gates / 18 Live Blocker 表 / Live target 规划带，全在那里维护。README 不再镜像（避免 ≥3 日 drift；2026-05-06 R4 sweep 把旧 4 日快照移至 `docs/archive/2026-05-06--readme_stale_extract.md`）。

**关键里程碑（2026-05-15）**：Decision Lease 路径 A retrofit 已落地并在 shadow/evidence 语义下运行；`OPENCLAW_LEASE_ROUTER_GATE_ENABLED=1` 不等于真实 live 授权或 Executor order authority。AMD-2026-05-15-01 已冻结 paper promotion，Stage 1 改为未来 green Stage 0R 之后的 Demo micro-canary。

**Active queue**：见 `TODO.md` P0/P1/P2 三层工作流程。完整上下文和硬边界见 `CLAUDE.md`。**领域词汇** → `CONTEXT.md`；**架构决策记录** → `docs/adr/`。

**已关闭并归档**：62-finding remediation Batch A-F、STRKUSDT P0 wave、Wave A-H、旧 Wave 1-3 叙事、4-day codex audit closure、REF-20 Sprint A-D 详细叙事 不再是 active mainline。归档：
- `docs/archive/2026-05-06--{claude_md,todo_completed,readme_stale}_extract.md` ← 本日 R4 sweep
- `docs/archive/2026-05-02--CLAUDE-pre-trim-snapshot.md`
- `docs/archive/2026-05-02--TODO-pre-trim-snapshot.md`
- `docs/archive/2026-04-30--{CLAUDE,TODO,README}-pre-cleanup-snapshot.md`

---

## 项目结构

```
srv/
├── CLAUDE.md                      ← ★ 项目完整上下文（实时状态以此为准）
├── CONTEXT.md                     ← ★ 领域词汇表（domain glossary，2026-05-06 引入）
├── docs/
│   ├── adr/                       ← ★ 14 条架构决策记录（2026-05-06 引入）
│   └── ...                        ← 工程文档（20+ 份日志/审核/设计）
├── program_code/
│   ├── exchange_connectors/
│   │   └── bybit_connector/
│   │       └── control_api_v1/    ← FastAPI 209 /api/v1 + 11 non-api 路由 + 3,700+ 测试
│   │           ├── app/
│   │           │   ├── governance_hub.py         ← ★ 治理中枢（4 SM 编排 + 跨 SM 级联）
│   │           │   ├── governance_routes.py      ← 11 治理 API 端点
│   │           │   ├── governance_hub_live_candidate_review.py ← LG-5 W3 reviewer
│   │           │   ├── lg5_review_consumer_scheduler.py ← LG-5 W3 FUP-1 consumer scheduler（commit `463890d`）
│   │           │   ├── scout_routes.py          ← 5 Scout REST 端点（OpenClaw 推送入口）
│   │           │   ├── paper_trading_routes.py  ← Paper/Demo/Live session 路由
│   │           │   ├── live_routes.py           ← Live 实盘 API 端点
│   │           │   ├── multi_agent_framework.py ← ScoutAgent + MessageBus + Conductor
│   │           │   ├── ollama_client.py         ← Ollama HTTP 客户端（L1 本地推理）
│   │           │   ├── bybit_demo_connector.py  ← 工具函数（round_price/qty，无交易逻辑）
│   │           │   ├── grafana_data_writer.py   ← Grafana 数据写入
│   │           │   ├── telegram_alerter.py      ← Telegram 告警
│   │           │   └── static/                  ← GUI (login + OpenClaw Control Console tabs)
│   │           └── tests/
│   ├── local_model_tools/         ← 策略工具包（HTTP 路由层，无交易逻辑）
│   ├── governance/                ← Phase 2 治理状态机（授权/风控/租约/对账/审计）
│   ├── ai_agents/                 ← H1-H5 AI 治理层
│   ├── risk_control/              ← H0 本地判断
│   └── trade_executor/            ← I 决策租约
├── docker_projects/
│   ├── monitoring_services/       ← Grafana + 5 仪表盘
│   └── trading_services/          ← PostgreSQL
├── rust/                          ← ★ Rust 交易引擎（交易 / 风控 / 策略配置 / 执行权威）
│   ├── Cargo.toml                 ← Workspace: 3 crates
│   ├── openclaw_types/            ← 10 shared types + serde (36 tests)
│   ├── openclaw_core/             ← 24 modules: SM/indicators/signals/risk/backtest (~400 tests)
│   ├── openclaw_engine/           ← 12+ modules: tick pipeline/strategies/paper state/canary (~2400 tests)
│   └── schemas/                   ← Golden JSON schema (10 types)
├── helper_scripts/                ← ★ 详见 helper_scripts/SCRIPT_INDEX.md
│   ├── restart_all.sh             ← 轻量重启（--rebuild 先编译 + --keep-auth 保持授权）
│   ├── stop_all.sh                ← 优雅停止 + maintenance flag
│   ├── clean_restart.sh           ← 交易所平仓 + 重启（不动 DB / paper_state）
│   ├── fresh_start.sh             ← ★ 完整 DB 重置重启（PnL/手续费/胜率清零）
│   ├── start_paper_trading.sh     ← Paper Trading 一键启动
│   ├── cron_observer_cycle.sh     ← Observer 自动化
│   ├── cron_daily_report.sh       ← 日报 → Telegram（UTC 0:00）
│   ├── canary/                    ← 灰度验证 + watchdog
│   ├── db/audit/                  ← 排程 audit 脚本（2026-05-09 3C 7d、2026-05-16 funding_arb 14d）
│   ├── db/fresh_start_reset.py    ← DB 经验数据清理（保留市场/模型）
│   └── maintenance_scripts/       ← 清理 / 检查脚本
└── docs/
    ├── rust_migration/            ← 8 阶段执行文件（R-00~R-07，R-04 last-mile 待补）
    └── worklogs/                  ← Session 工作日志
```

---

## Phase 2 治理模組

21 个治理模组实现，覆盖 4 个核心状态机 + 17 个扩展模组：

| 类别 | 模组 | 规格 |
|------|------|------|
| 核心状态机 | T2.01 授权状态机、T2.02 风控状态机、T2.03 决策租约、T2.04 对账引擎 | SM-01/SM-02/SM-04/EX-04 |
| 扩展模组 | T2.05–T2.23（OMS、审计持久化、Scout Agent、组合风控、事件模型、感知数据面、学习门控等） | EX-01/EX-02/EX-05/EX-06/DOC-01/DOC-06 |

**关键测试基准**（最新数字以 `TODO.md` header 为准）：~6,500 测试通过（Py pytest 3431 + Rs cargo workspace 3132 + sibling 44）· fail-closed 设计 · 线程安全（Py）/ 零锁 single-owner（Rs）· **注释规范**：2026-05-05 起新代码默认中文（旧双语块保留，详 `CLAUDE.md` §七）

---

## 16 条根原则（DOC-01 项目宪法 §5.1–§5.16，不可违背）

详见 [`CLAUDE.md` §二](CLAUDE.md#二16-條根原則doc-01-項目憲法-5151616不可違背)。

**优先级序**：账户生存 > 风控治理 > 系统健康 > 审计可追溯 > 人类终审 > 真实 Net PnL > 自主能力进化

**实施准则**：认知调制 ≠ 能力限制 — Agent 压力下更审慎的方式是提高决策门槛，不是关闭能力。虚拟稀缺性被明确否决。

---

## 治理架构总览

```
[H0 本地门控]     零成本确定性判断（健康/资格/风险包络）— 永远第一道
[SM-01 授权]      8 状态 · 16 转换 · fail-closed · 终态不可回流
[SM-04 风控]      6 级风险（NORMAL→CIRCUIT_BREAK）· 升级自动/降级需审批
[SM-02 决策租约]   9 状态 · TTL 自动到期 · AI→Lease→复核→执行
                  路径 A retrofit 已 land；router gate flag 当前仅是 shadow/evidence 语义
[EX-04 对账引擎]   5 类结果（MATCH/MISMATCH/MISSING）· 触发风控升级（Rust event_consumer 直写 DB）
[EX-06 多Agent]    Local Conductor + Scout/Strategist/Guardian/Analyst/Executor；OpenClaw Gateway 仅外围通信/提案
[EX-05 学习]       L1→L5 五级门控 · 逐级解锁能力 · L5 需 Operator 审批
[EX-07 感知面]     FACT/INFERENCE/HYPOTHESIS 认知标记 · 新鲜度追踪
[DOC-07 审计]      append-only JSONL · 不可修改不可删除 · 自动轮转
```

---

## 治理合规矩阵

正式 SPEC 注册表 → `docs/governance_dev/SPECIFICATION_REGISTER.md`（接入率以那里为准；2026-05-02 旧 91% 数字已过 REF-20 + Decision Lease retrofit 重新校验，移至 `docs/archive/2026-05-06--readme_stale_extract.md`）。

---

## OpenClaw 服务族集成

OpenClaw 现在是玄衡项目内的控制平面服务族名称，不再作为总项目名使用。

> 2026-05-06 定位：现有 FastAPI console 是唯一 OpenClaw Control Console；外部 OpenClaw Gateway 是通信、移动端、上级汇总、proposal/approval relay，不是交易 conductor，也不是第二套 GUI。

当前目标架构：OpenClaw Gateway → `/api/v1/openclaw/*` 聚合/提案/审批 API → 本地 5-Agent + GovernanceHub + Postgres → Rust `openclaw_engine`。OpenClaw 不持有 Bybit key、不直接下单、不直接改 live TOML；所有交易影响动作仍通过 Operator approval、Decision Lease 和 Rust execution authority。

设计与计划：

- `docs/architecture/2026-05-06--openclaw_control_plane_repositioning.md`
- `docs/execution_plan/2026-05-06--openclaw_gateway_development_plan.md`
- `docs/execution_plan/2026-05-06--gui_openclaw_control_console_plan.md`

旧的「OpenClaw Gateway → Scout + MessageBus → PipelineBridge」只保留为历史/legacy advisory trace，不得作为后续 Agent Decision Spine 的权威路径。

外部工具策略以 `CLAUDE.md` §十一 为准（**GitHub Issues active**；Linear historical/passive；Notion frozen；Slack/Coupler/MotherDuck declined）。OpenClaw channel / Telegram / WebChat 只作为 operator 通信入口，不等同于开放 Slack/Coupler/MotherDuck 等工作流集成。

---

## 硬边界（永远不可违背）

README 只保留入口级摘要；完整硬边界以 `CLAUDE.md` §四为准。

- 真实 live 必须同时满足 Python live_reserved、Operator 角色认证、`OPENCLAW_ALLOW_MAINNET=1`、secret slot、signed `authorization.json` 五项 gate。
- `execution_authority` 在 Rust 侧仅是 P0/P1 denylist 字符串常量，不是真实授权逻辑。
- LiveDemo 走 live-grade 控制流；demo endpoint 不放宽 authorization、TTL 或 risk gate。
- Decision Lease 路径 A retrofit 已落地；`OPENCLAW_LEASE_ROUTER_GATE_ENABLED=1` 仅代表 shadow/evidence 线路已启用，不授予真实 live、order authority、Stage 3/4 或 proposal/mobile 放权。
- 禁止手写 `authorization.json`、绕过 Operator auth、自动切 live、伪造 AI/交易活动，或在 Bybit `retCode != 0` 后重试成交路径。

---

## 部署

**跨平台**：项目必须随时可部署至 macOS（路径不硬编码 / LLM 抽象 / systemd→launchd 可迁移 / 无 Linux-only 依赖）。详见 CLAUDE.md §七。

```bash
# API 服务器（Linux: systemd，开机自启；macOS: launchd 可迁移）
systemctl --user status openclaw-trading-api    # 端口 8000
systemctl --user status openclaw-gateway        # OpenClaw + Tailscale HTTPS
systemctl --user status openclaw-watchdog       # 引擎存活监控 + 自动重启

# Grafana
cd docker_projects/monitoring_services && docker compose up -d   # 端口 3000

# 一键启动 Paper Trading
bash helper_scripts/start_paper_trading.sh
```

### Mac dev-only 模式（开发环境，不参与交易）

**使用场景**：Mac 端只做开发（编辑 / build / test / commit / auto-push），Linux trade-core 是唯一 OMS。两端共用同一个 Bybit demo API key —— Mac 跑 engine 会与 Linux 撞单（违反根原则 #1「单一写入口」）。

**启用 dev-only**（重命名 secret slot 让 engine 找不到 credentials → fail-closed）：
```bash
cd "$OPENCLAW_SECRETS_DIR" && for s in demo live read_only; do
  [[ -d "$s" ]] && mv "$s" "$s.dev_disabled_$(date +%Y%m%d)"
done
rm -f "$OPENCLAW_SECRETS_DIR/live/authorization.json"   # 顺便撤 live 签章
```

**还原**（未来想 Mac 跑测试 / 回到 deploy 模式）：
```bash
# 用实际后缀替换 SUFFIX（例如 .dev_disabled_20260421）
cd "$OPENCLAW_SECRETS_DIR" && for s in demo live read_only; do
  [[ -d "$s.dev_disabled_"* ]] && mv "$s.dev_disabled_"* "$s"
done
# authorization.json 需透过 GUI /api/v1/live/auth/renew 重簽（HMAC 与本机 IPC_SECRET 绑定，不能从 Linux copy）
```

效果：Mac engine 即使被误启也无 credentials 可连 Bybit → 0 订单冲突；Linux trade-core 文件分属不同主机，完全不受影响。

---

## 常用脚本 (Common Scripts)

完整清单见 [`helper_scripts/SCRIPT_INDEX.md`](helper_scripts/SCRIPT_INDEX.md)。

### 生命周期 (Lifecycle)

| 脚本 | 用途 | 何时用 |
|------|------|--------|
| `restart_all.sh` | 停+启 Rust 引擎 + API（**不动数据**）。`--rebuild` 先编译 engine binary。`--keep-auth` 保持现有授权。 | 日常：改代码后部署、unstick 卡住的进程 |
| `stop_all.sh` | 优雅停止 + 建 `engine_maintenance.flag`。`rm flag` 或 `restart_all.sh` 恢复。 | 停机维护、手工 debug |
| `clean_restart.sh` | 停 → 交易所平仓 → 归档 runtime → 编译检查 → 重启 → watchdog 验证。**保留 paper_state 与 DB**。 | 清空交易所持仓、解决 runtime snapshot 污染 |
| `fresh_start.sh` ★ | `clean_restart` 全部动作 + **清空 DB 经验数据**。**保留**：市场数据、已训练模型、LinUCB archive。 | 开发阶段结束、需要从零历史冷启动验证 |
| `start_paper_trading.sh` | API 就绪后自动启 Paper Trading 会话。 | 开机自动化 |

### 灰度 / 监控 (Canary & Monitor)

| 脚本 | 用途 |
|------|------|
| `canary/engine_watchdog.py` | 引擎存活检查。`--status` 打 JSON；`--stale-threshold` 设过期秒数。已包装为 `openclaw-watchdog.service` user unit。 |
| `canary/replay_runner.py` | 灰度回放：读 canary JSONL 与 Python 基线比对。 |

### 数据库 / 排程 audit

| 脚本 | 用途 |
|------|------|
| `db/fresh_start_reset.py` | DB 经验数据清理核心。`--report-only`（默认）/`--dry-run`/`--execute --confirm`。 |
| `db/audit/2026-05-09_3c_7d_audit.sh` | 3C deploy 7d 后 5-metric vs prior 7d baseline 对比 |
| `db/audit/2026-05-16_funding_arb_14d_audit.sh` | funding_arb 1B 样本累积 14 天后判断 2A 弃策略 trigger |

### 定时任务 (Cron)

| 脚本 | 用途 |
|------|------|
| `cron_daily_report.sh` | 每日 UTC 0:00 采集 Paper 指标 + Telegram 推送。 |
| `cron_observer_cycle.sh` | 每 5 分钟 Observer 循环 + runtime snapshot 桥接。 |

### 快速对照：选哪个重启？

```
改了代码需部署              → restart_all.sh --rebuild --keep-auth
LG-5 W3 FUP-1 启动 reviewer → restart_all.sh --keep-auth（纯 Python 改动，不需 rebuild）
只想清交易所持仓             → clean_restart.sh --yes
开发告一段落要清 PnL/胜率    → fresh_start.sh --yes
临时停机 debug              → stop_all.sh
```

---

## 参考文件

| 类别 | 位置 |
|------|------|
| 完整项目指令 | `CLAUDE.md` |
| 当前工作计划（P0/P1/P2 三层） | `TODO.md` |
| Decision Lease review agenda | `docs/CCAgentWorkSpace/PM/2026-05-02--decision_lease_review_agenda.md` |
| 审计报告 | `docs/governance_dev/audits/` |
| QC 量化审查 | `docs/CCAgentWorkSpace/QC/workspace/reports/` |
| 工作日志 | `docs/worklogs/` |
| 变更历史 | `docs/CLAUDE_CHANGELOG.md` |
| 治理文件（SPEC 源） | Cowork `01_source_documents/` + `docs/governance_dev/SPECIFICATION_REGISTER.md` |
| Phase 2/3 执行记录 | `docs/governance_dev/phase2_execution/` / `phase3_integration/` |

GitHub: [yunancun/BybitOpenClaw](https://github.com/yunancun/BybitOpenClaw)
