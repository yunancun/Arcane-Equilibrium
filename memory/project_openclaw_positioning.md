---
name: OpenClaw 定位决策（已更新至 Rust 引擎時代）
description: OpenClaw Gateway 在交易系统中的角色：通信+运维层，非交易 Agent 大脑。贸易逻辑自 2026-04-11 起完全在 Rust openclaw_engine，Python 仅为 API 桥接+GUI。
type: project
originSessionId: 189878ce-df95-4b97-a566-ea1b4e395fe9
---
## 决策结论（2026-03-26 定方向，2026-04-12 更新至 Rust 时代）

OpenClaw Gateway 不是交易 Agent 的大脑。**当前交易 Agent 核心 = Rust `openclaw_engine`（paper/demo/live 三引擎）。**

**OpenClaw Gateway 角色 = 嘴巴 + 耳朵（通信与运维层）**

### 原因（不变）
1. 交易决策循环需要毫秒级、零成本、确定性 — OpenClaw 每步都调 LLM，太慢太贵
2. 成本感知需要精细控制（H1 thought_gate / H2 query_budget / H3 model_router）— OpenClaw 没有
3. 结构化交易学习需要量化追踪 — OpenClaw 的 markdown 记忆不够用
4. 硬件/基础设施感知需要秒级实时监控 — OpenClaw heartbeat 是 30 分钟

### 当前代码层级（2026-04-12）

| 层级 | 职责 | 语言 |
|------|------|------|
| `rust/openclaw_engine` | 交易决策、风控、策略、Paper/Demo/Live 执行 | Rust |
| Python Control API | GUI 路由、IPC 桥接、API 接口（仅读写代理） | Python |
| OpenClaw Gateway | Telegram 告警、AI 成本追踪、Canvas 仪表板入口 | OpenClaw |

**⚠️ "所有交易逻辑在 Python" 已作废（2026-04-11 DEAD-PY-2 完成）**  
Python 已清除全部交易逻辑（~4500 行），仅剩 API 桥接 + GUI 路由 + 辅助工具。

### OpenClaw 零成本可复用的功能（不变）
- `message send` → Telegram 告警（纯转发，不经 AI）
- `gateway usage-cost` → AI 成本追踪（内建，直接读）
- Canvas (port 18790) → 仪表盘入口页面
- `command-logger` hook → 命令审计日志
- `cron` → 定时 shell 任务（不触发 AI 的模式）

**Why:** OpenClaw 是通用助手，交易 Agent 需要专用精细控制（Rust 引擎提供）。
**How to apply:** 所有交易决策逻辑在 Rust `openclaw_engine`。Python 仅作只读 IPC 调用（`get_*`，禁止 `update_*` 直写）。OpenClaw Gateway 仅用于通信、运维、成本追踪、和 Operator 交互。
