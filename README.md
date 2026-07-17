# 玄衡 · Arcane Equilibrium
<!-- Git 日志 — 项目入口。主日志见 CLAUDE.md -->

Agentic trading governance system — 自主扫描 650+ 交易对，智能部署策略，**Live_Ready ⚠️**（5 项 live gate 全绿才上真实 live，见下文门控表）。

**软更名口径（2026-05-06）**：
- 正式项目名：**玄衡 · Arcane Equilibrium**。
- **OpenClaw** 保留为 Control Console、本地 API、Rust engine 与既有运行面标识；外部 OpenClaw Gateway 已于 2026-07-16 退役并移除。
- **Bybit** 仍是目前唯一 active live execution 交易所 adapter / connector；Binance 仅 market-data-only（ADR-0033/0040）。AMD-2026-07-11-01 已授权开发 IBKR `stock_etf_cash` readonly / paper / shadow / tiny-live / live **capability**（production caller、TWS/Gateway、Rust authority、IPC、GUI、inactive deploy），但默认 inactive，绝不等于 broker login、API/socket contact 或下单授权。真实 contact/effect 必须有 Rust 验证的、限时且 commit/account/session-bound `ibkr_activation_envelope_v1`；credential/session 本身永不 auto-activate。IBKR margin / short / options / CFD / transfer / account-management write 与 Python authority 仍禁止。
- 短期不改 `openclaw_engine`、`OPENCLAW_*`、`/tmp/openclaw`、GitHub 仓库名、Linux runtime 路径等运行面名称。

---

## 🖥️ GUI 访问（Tailscale 网络内）

| 地址 | 功能 |
|------|------|
| **[http://trade-core:8000](http://trade-core:8000)** | **OpenClaw Control Console**（唯一 canonical GUI；登录后进入现有 FastAPI 控制台） |

> 2026-07-16 安全面收敛：外部 OpenClaw Gateway、其代理/服务入口，以及
> Grafana 容器、仪表盘与数据写入链路均已退役并移除；它们不再是部署或访问端点。
>
> **同日深夜 main 历史经 `git-filter-repo` 全量重写（secret purge）**：三凭证已
> revoke/rotate 并从全部可写分支/标签清除（attest：PR#55）。**2026-07-16 23:46 之前
> 记录在任何文档/memory/报告中的 commit SHA 均属旧史**，请以 PR 编号/日期/subject 在
> 新史定位（`git log --grep`）；旧史本地备份 ref `pre-rewrite-main-20260716`（Mac+Linux，
> 永不 push）。

### OpenClaw Control Console 核心 Tab

| Tab | 内容 |
|-----|------|
| `system` | 系统总览、运行状态、章节状态 |
| `edge-gates` | Pre-live / edge readiness gates |
| `stock-etf` | Stock/ETF IBKR capability console：readonly/paper/shadow/tiny-live/live-capable implementation（AMD-2026-07-11-01）；默认 inactive，GUI 不授權 broker contact/order |
| `paper` | Paper Archive 状态展示；不再启用为 promotion lane，legacy artifacts 仅作 replay diagnostics / fixture infrastructure |
| `demo` | Demo trading / Stage 1 demo micro-canary 目标环境（当前未开放） |
| `live` | Live_Ready 仪表盘、余额/PnL/持仓/成交/API key 管理 |
| `replay` | replay / Stage 0R 诊断与报告入口 |
| `strategy` | 策略部署、scanner、品种管理 |
| `charts` | 圖表 / 交易视图（`/trading?embed=1` 内嵌） |
| `risk` | 风控参数、止损、denylist |
| `earn` | Earn 理财 / first-stake GUI（governance group，5-gate 对映后端 9-gate，typed-confirm 带 amount） |
| `governance` | GovernanceHub、授权、Decision Lease、对账 |
| `ai` | Layer2Engine、本地/云模型、成本追踪 |
| `learning` | Learning Cockpit、promotion evidence、ML/feature 状态 |
| `agents` | 本地 5-Agent 只读状态与治理记录 |
| `monitoring` | 内建系统健康、运行状态与非 Grafana 监控 |
| `development` | 開發與維護工具入口 |
| `settings` | 参数、环境、维护操作 |

> Tab 表以 `console.html` nav 定义为 SoT（2026-07-04 TW per R4 对齐：补 `stock-etf`/`charts`，移除已下架的 `phase4`；排序对齐 GUI group core/trading/edge/governance/intelligence/ops）。

> **GUI 大修 baseline（2026-07-09 · 回滚/对比锚点）**：改版前的 Console GUI 已冻结快照在 git tag `gui-baseline-2026-07-09`（commit `d077949fc`，61 files / 36,337 lines）。**回滚**：`git checkout gui-baseline-2026-07-09 -- program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/`；**对比**：`git diff gui-baseline-2026-07-09 -- <path>`。清单 + 便携镜像（`gui-baseline-2026-07-09-static.tar.gz`，sha256 `d6a15818…`）见 `docs/archive/2026-07-09--gui_baseline_pre_redesign_manifest.md`。改版设计正本 → `docs/execution_plan/gui_redesign/GUI-DESIGN-WORKING-DOC.md`（「玄衡仪」视觉主张；Phase 0/1/2 迁移实质完成、双主题上线；cutover 待 operator Linux 批验）；深度规格索引 `docs/execution_plan/gui_redesign/design/01-13`。

> **玄衡壳迁移状态（2026-07-12）**：18 个原生 view 已迁入新玄衡壳 `shell.html`（`iframe:false` + flag opt-in，保留 legacy iframe 回滚后备）；双主题（玄夜/帛昼）上线（OS 偏好默认 + `data-theme` toggle 持久）。**新壳仍是 flag opt-in；`console.html`（`/console`）仍是 served canonical GUI**；迁移实质完成，**cutover 待 operator Linux 批验**（帛昼真渲染 / 三态真值 / cutover = NEEDS-LINUX）。baseline tag `gui-baseline-2026-07-09` 回滚锚不变。

---

## 当前状态

实时面板：[`TODO.md`](TODO.md) — active blockers、P0/P1/P2 queue、runtime evidence、schedule 和 handoff checks 均在那里维护。README 不再镜像动态状态（避免 drift）。

**关键里程碑（2026-05-15 / 2026-05-23 / 2026-07-11 口径收敛）**：Decision Lease 路径 A retrofit 已落地并在 shadow/evidence 语义下运行；`OPENCLAW_LEASE_ROUTER_GATE_ENABLED=1` 不等于真实 live 授权或 Executor order authority。AMD-2026-05-15-01 已冻结 legacy crypto paper promotion；2026-05-23 起 paper engine 口径为长期 Archive / replay infrastructure，Stage 1 改为未来 green Stage 0R 之后的 Demo micro-canary。AMD-2026-07-11-01 取代 ADR-0048/旧 AMD 中相冲突的 IBKR capability-development 限制：`stock_etf_cash` 可完整实现至 live-capable，但仍非 active/live、不会因 credential/session 自动启用；实际 IBKR contact/order 另需 Rust-validated activation envelope 与人工 session/activation。

**Context loading**：稳定入口见本 README；当前工作状态见 `TODO.md`；agent 启动路由见 `docs/agents/context-loading.md`；开发 multi-agent 的 trust / dispatch / closure 正本见 `docs/agents/development-agent-governance.md`；TODO 维护标准见 `docs/agents/todo-maintenance.md`。**领域词汇** → `CONTEXT.md`；**架构决策记录** → `docs/adr/`。

**Alpha evidence governance（2026-05-31）**：ADR-0047 / AMD-2026-05-31-01 規定 Alpha-Edge S1-Sx promotion evidence 必須 math-primary。Bull data 可用但必須標籤化；Bybit market API 是 raw state input，不是 prediction oracle；新聞 / X / Reddit 只可作旁證，不能覆蓋 quantitative gate。同日 **v5.9 thesis-shift**（`CHANGELOG.md`）：凍結 v5.8 autonomy 模組 active-IMPL（M7 例外；解凍 gate = 首個 net+ candidate `stage0_ready`），當前主線 = AEG（Alpha-Edge Evidence Program，`TODO.md` §2）。

**已关闭并归档**：62-finding remediation Batch A-F、STRKUSDT P0 wave、Wave A-H、旧 Wave 1-3 叙事、4-day codex audit closure、REF-20 Sprint A-D 详细叙事 不再是 active mainline。归档：
- `docs/archive/2026-05-06--{claude_md,todo_completed,readme_stale}_extract.md` ← 本日 R4 sweep
- `docs/archive/2026-05-02--CLAUDE-pre-trim-snapshot.md`
- `docs/archive/2026-05-02--TODO-pre-trim-snapshot.md`
- `docs/archive/2026-04-30--{CLAUDE,TODO,README}-pre-cleanup-snapshot.md`

---

## 项目结构

```
srv/
├── CLAUDE.md                      ← ★ Claude 操作記憶（人格 / 邊界 / 工作流）
├── .codex/MEMORY.md               ← ★ Codex 操作記憶（Codex-specific rules）
├── TODO.md                        ← ★ Active dispatch queue（實時工作狀態）
├── IBKR_TODO.md                   ← ★ IBKR stock/ETF live-capability 工程總綱（W0-W11 + EA 活化跑道；活化另由 AMD-2026-07-11-01 把關）
├── memory/                        ← ★ Claude 跨-session 記憶（MEMORY.md 索引 + topic 檔；Mac ~/.claude 經 symlink 指向此處）
├── CONTEXT.md                     ← ★ 领域词汇表（domain glossary，2026-05-06 引入）
├── docs/
│   ├── adr/                       ← ★ 架构决策记录系列（目前至 ADR 0050；精确清单见 docs/_indexes）
│   └── ...                        ← 工程文档（20+ 份日志/审核/设计）
├── program_code/
│   ├── exchange_connectors/
│   │   └── bybit_connector/
│   │       └── control_api_v1/    ← FastAPI 控制平面（约 200+ /api/v1 + non-api 路由 + 测试套件；精确数以代码/CI 为准）
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
│   │           │   ├── telegram_alerter.py      ← Telegram 告警
│   │           │   └── static/                  ← GUI (login + OpenClaw Control Console tabs)
│   │           └── tests/
│   ├── local_model_tools/         ← 策略工具包 stub-shim（计算已收编 Rust，仅保留 import 表面）
│   ├── ai_agents/                 ← H1-H5 AI 治理层（冷路径 5-Agent host）
│   ├── learning_engine/           ← 学习管线（Observation→Lesson→Hypothesis→Experiment→Verdict）
│   ├── ml_training/               ← ML/DL 训练（Teacher-Student + LightGBM + Optuna）
│   ├── broker_connectors/         ← IBKR source-only skeleton（display-only，ADR-0048；非 runtime connector）
│   └── market_data_processor/     ← 市场数据清洗 / 加工
│   ↳ 旧 governance/ · risk_control（H0）· trade_executor（Decision Lease）已迁移至 Rust
│     （openclaw_core: governance_core.rs · h0_gate.rs · sm/risk_gov.rs），Python 目录已删除
├── docker_projects/
│   ├── monitoring_services/       ← 仅保留 PostgreSQL 初始交易 schema（bootstrap 相容）
│   └── trading_services/          ← PostgreSQL
├── rust/                          ← ★ Rust 交易引擎（交易 / 风控 / 策略配置 / 执行权威）
│   ├── Cargo.toml                 ← Workspace: 5 crates（另含 openclaw_alr_fit_verifier 隔離驗證器、openclaw_fake_tws dev-only harness）
│   ├── openclaw_types/            ← shared types + serde 契約（含 ibkr_*/stock_etf_* 型別陣；精确测试数以 CI 为准）
│   ├── openclaw_core/             ← 18 modules: SM/indicators/signals/risk/m4_miner（core 模組測試，精确数以 cargo workspace CI 为准；backtest/portfolio 为 reserved-library，未接 API；7 legacy 模块 per ADR-0015 已退役）
│   ├── openclaw_engine/           ← 60+ modules: tick pipeline/strategies/paper state/canary/news/earn（engine 模組測試，精确数以 cargo workspace CI 为准）
│   └── schemas/                   ← Golden JSON schema (10 types)
├── helper_scripts/                ← ★ 详见 helper_scripts/SCRIPT_INDEX.md
│   ├── restart_all.sh             ← 轻量重启（--rebuild 先编译 + --keep-auth 保持授权）
│   ├── stop_all.sh                ← 优雅停止 + maintenance flag
│   ├── clean_restart.sh           ← 交易所平仓 + 重启（不动 DB / paper_state）
│   ├── fresh_start.sh             ← ★ 完整 DB 重置重启（PnL/手续费/胜率清零）
│   ├── start_paper_trading.sh     ← Legacy Paper diagnostic 启动入口（promotion lane frozen）
│   ├── cron_observer_cycle.sh     ← Observer 自动化
│   ├── cron_daily_report.sh       ← 日报 → Telegram（UTC 0:00）
│   ├── canary/                    ← 灰度验证 + watchdog
│   ├── cron/lib/                  ← ★ cron 共用正本：flock 反叠加锁 + OOM-victim 自标（2026-07-15/16 OOM 风暴修复；新 cron 必须接入）
│   ├── research/                  ← $0 只读研究管线（cost_gate_learning_lane 等；无 order authority）
│   ├── db/audit/                  ← 排程 audit 脚本（2026-05-09 3C 7d、2026-05-16 funding_arb 14d）
│   ├── db/fresh_start_reset.py    ← DB 经验数据清理（保留市场/模型）
│   └── maintenance_scripts/       ← 清理 / 检查脚本
└── docs/
    ├── archive/2026-07-09--rust_migration_completed/  ← 8 阶段执行文件（R-00~R-07；2026-07-09 迁移完结归档）
    └── worklogs/                  ← Session 工作日志（顶层现役；2026-04 历史已归档 archive/2026-07-09--worklogs_2026-04/）
```

---

## Phase 2 治理模組

21 个治理模组实现，覆盖 4 个核心状态机 + 17 个扩展模组：

| 类别 | 模组 | 规格 |
|------|------|------|
| 核心状态机 | T2.01 授权状态机、T2.02 风控状态机、T2.03 决策租约、T2.04 对账引擎 | SM-01/SM-02/SM-04/EX-04 |
| 扩展模组 | T2.05–T2.23（OMS、审计持久化、Scout Agent、组合风控、事件模型、感知数据面、学习门控等） | EX-01/EX-02/EX-05/EX-06/DOC-01/DOC-06 |

**关键测试基准**（精确数字以 `TODO.md` header / CI 为准，README 不再镜像以避免 drift）：约 6,500+ 测试通过（Py pytest + Rs cargo workspace + sibling）· fail-closed 设计 · 线程安全（Py）/ 零锁 single-owner（Rs）· **注释规范**：2026-05-05 起新代码默认中文（旧双语块保留，详 `CLAUDE.md` §七）

---

## 16 条根原则（DOC-01 项目宪法 §5.1–§5.16，不可违背）

详见 `CLAUDE.md` §二 Root Principles。

**终极目标**：持续真实 Net PnL（长周期复利）。风控 = 损失削减，是 Net PnL 的组成部分而非对立面。**护栏排序（按所防损失的不可逆性，是达成目标的手段而非并列目标）**：账户生存 > 风控治理 > 系统健康 > 审计可追溯 > 人类终审 > 自主能力进化；fail-closed 硬边界不因任何短期 PnL 论证而放松（详见 `CLAUDE.md` §二 Ultimate objective 段）

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
[EX-06 多Agent]    Local Conductor + Scout/Strategist/Guardian/Analyst/Executor；不依赖已退役的外部 Gateway
[EX-05 学习]       L1→L5 五级门控 · 逐级解锁能力 · L5 需 Operator 审批
[EX-07 感知面]     FACT/INFERENCE/HYPOTHESIS 认知标记 · 新鲜度追踪
[DOC-07 审计]      append-only JSONL · 不可修改不可删除 · 自动轮转
```

---

## 治理合规矩阵

正式 SPEC 注册表 → `docs/governance_dev/SPECIFICATION_REGISTER.md`（接入率以那里为准；2026-05-02 旧 91% 数字已过 REF-20 + Decision Lease retrofit 重新校验，移至 `docs/archive/2026-05-06--readme_stale_extract.md`）。

---

## OpenClaw 服务族集成

OpenClaw 现在是玄衡项目内既有 Control Console、本地 API、Rust engine 与
运行面标识，不再作为总项目名使用。

> 2026-07-16 安全决策：外部 OpenClaw Gateway、`/openclaw/*` 反向代理及其
> 服务/GUI 集成已退役并移除。既有 FastAPI console 仍是唯一 OpenClaw
> Control Console。

当前保留架构：受认证的 FastAPI Control Console → 本地只读
`/api/v1/openclaw/*` 控制/监控 API → 本地 5-Agent + GovernanceHub +
PostgreSQL → Rust `openclaw_engine`。Python GUI 与本地 Agent 不持有 Bybit
key、不直接下单、不直接改 live TOML；所有交易影响动作仍通过 Operator
approval、Decision Lease 和 Rust execution authority。

以下 2026-05-06 文件仅保留为历史设计记录，不定义当前可部署 Gateway：

- `docs/architecture/2026-05-06--openclaw_control_plane_repositioning.md`
- `docs/execution_plan/2026-05-06--openclaw_gateway_development_plan.md`
- `docs/execution_plan/2026-05-06--gui_openclaw_control_console_plan.md`

旧 Gateway relay 与「Scout + MessageBus → PipelineBridge」只保留为
historical/legacy advisory trace，不得作为部署说明或后续 Agent Decision
Spine 的权威路径。

外部工具策略以 `CLAUDE.md` External Tools + `docs/agents/issue-tracker.md`
為準（**GitHub Issues active**；Linear historical/passive；Notion frozen；
Slack/Coupler/MotherDuck declined）。Telegram 等独立通知通道不属于已退役
Gateway，也不等同于开放其他工作流集成。

---

## 硬边界（永远不可违背）

README 只保留入口级摘要；完整硬边界以 `CLAUDE.md` §四为准。

- 真实 live 必须同时满足 Python live_reserved、Operator 角色认证、`OPENCLAW_ALLOW_MAINNET=1`、secret slot、signed `authorization.json` 五项 gate。
- `execution_authority` 在 Rust 侧仅是 P0/P1 denylist 字符串常量，不是真实授权逻辑。
- LiveDemo 走 live-grade 控制流；demo endpoint 不放宽 authorization、TTL 或 risk gate。
- Decision Lease 路径 A retrofit 已落地；`OPENCLAW_LEASE_ROUTER_GATE_ENABLED=1` 仅代表 shadow/evidence 线路已启用，不授予真实 live、order authority、Stage 3/4 或 proposal/mobile 放权。
- IBKR `stock_etf_cash` 仅有 live-capable **开发**授权（AMD-2026-07-11-01），默认 inactive：任何真实 broker 接触（含 readonly）需 Rust 验证的限时 `ibkr_activation_envelope_v1` + authenticated Operator 活化纪录（nonce 原子消费）；margin/short/options/CFD/transfer/account-write 永久 denied；credential/session 永不 auto-activate；Python/GUI 永不成为 IBKR order/risk/activation authority。
- 禁止手写 `authorization.json`、绕过 Operator auth、自动切 live、伪造 AI/交易活动，或在 Bybit `retCode != 0` 后重试成交路径。

---

## 部署

**跨平台**：项目必须随时可部署至 macOS（路径不硬编码 / LLM 抽象 / systemd→launchd 可迁移 / 无 Linux-only 依赖）。详见 `CLAUDE.md` Code And Docs Rules。

```bash
# API 服务器（Linux: systemd，开机自启；macOS: launchd 可迁移）
systemctl --user status openclaw-trading-api      # 端口 8000（runtime 手管 user unit，2026-07-14 起接管；不在 repo systemd/ 内）
systemctl --user status openclaw-watchdog         # 引擎存活监控 + 自动重启
systemctl --user status openclaw-listing-collector # 上市探针 collector

# 注意：Rust engine 无独立 unit——裸进程活在 watchdog cgroup 内（restart watchdog 会连坐引擎）；
# repo helper_scripts/systemd/ 内的 engine unit 为未安装模板。

# Paper runtime is Archive/diagnostic only; do not start it for canary evidence.
```

外部 Gateway 与 Grafana stack 已于 2026-07-16 移除，不存在对应启动命令。

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
| `start_paper_trading.sh` | Legacy Paper diagnostic 会话启动入口；promotion lane 已冻结。 | 仅未来 operator 明确重开时使用 |

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
| `cron/lib/cron_flock.sh` + `cron/lib/cron_oom_victim.sh` | ★ 全 cron 共用正本：flock 反叠加锁（stale-lock 叠加机根治）+ OOM victim 自标（hog `oom_score_adj=800` >> 引擎 200）。新增 cron 必须取锁后接入两者。 |

### 快速对照：选哪个重启？

```
改了代码需部署              → restart_all.sh --rebuild --keep-auth
纯 Python/API 改动            → restart_all.sh --api-only（不需 rebuild、不动引擎）
只想清交易所持仓             → clean_restart.sh --yes
开发告一段落要清 PnL/胜率    → fresh_start.sh --yes
临时停机 debug              → stop_all.sh
```

---

## 参考文件

| 类别 | 位置 |
|------|------|
| Claude 操作記憶 | `CLAUDE.md` |
| Agent context loading | `docs/agents/context-loading.md` |
| TODO maintenance standard | `docs/agents/todo-maintenance.md` |
| 当前工作计划（P0/P1/P2 三层） | `TODO.md` |
| Decision Lease review agenda | `docs/CCAgentWorkSpace/PM/2026-05-02--decision_lease_review_agenda.md` |
| 审计报告 | `docs/archive/2026-07-09--governance_dev_phase_history/audits/` |
| QC 量化审查 | `docs/CCAgentWorkSpace/QC/workspace/reports/` |
| 工作日志 | `docs/worklogs/` |
| 变更历史 | `docs/CLAUDE_CHANGELOG.md` |
| IBKR 工程總綱 / loop 协议 / 帐本 | `IBKR_TODO.md`（根目录） / `docs/agents/ibkr-live-capability-loop.md` / `docs/execution_plan/ibkr_live_capability/PROGRESS.md` |
| profit-first 自主 loop | `docs/agents/profit-first-autonomy-loop.md` + `docs/agents/profit-first-fast-demo-promotion-loop.md` |
| 主题证据导航（历史 initiative 索引） | `docs/_indexes/initiative_index.md` |
| Claude 跨-session 记忆索引 | `memory/MEMORY.md` |
| GUI 改版设计正本 | `docs/execution_plan/gui_redesign/GUI-DESIGN-WORKING-DOC.md` |
| 治理文件（SPEC 源） | Cowork `01_source_documents/` + `docs/governance_dev/SPECIFICATION_REGISTER.md` |
| Phase 2/3 执行记录 | `docs/archive/2026-07-09--governance_dev_phase_history/phase2_execution/` / `phase3_integration/` |

GitHub: [yunancun/Arcane-Equilibrium](https://github.com/yunancun/Arcane-Equilibrium)（旧仓名 BybitOpenClaw 已弃用；Linux runtime 本地路径仍为 `~/BybitOpenClaw/srv`）
