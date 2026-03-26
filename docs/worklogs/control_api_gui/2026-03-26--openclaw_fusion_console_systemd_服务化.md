# OpenClaw 融合 + 统一控制台 + API 服务化 + 远程访问规划

**日期：** 2026-03-26（晚间）
**分支：** feature/openclaw-bybit-control-api-gui-v1-rc2
**状态：** 248 测试全通过，零回归

---

## 完成内容总览

本轮在 Beta 管线基础上，完成了 OpenClaw 融合评估、统一控制台搭建、API 服务器 systemd 自启动部署。

---

## 一、OpenClaw 架构定位决策

### 背景
评估 OpenClaw（https://openclaw.ai/）在本项目中的定位。OpenClaw 是开源 AI Agent 运行时 + 消息网关（v2026.3.24，Node.js，端口 18789）。

### 结论
> **OpenClaw = 通信层（嘴和耳朵），不是 Agent 大脑**
> **本地 Python Agent = 大脑（决策、感知、执行、学习）**

### 原因
针对用户 4 项核心需求逐一评估：
1. **成本/收益感知** — OpenClaw 每步需 LLM 调用，无法做到零成本本地判断
2. **最佳 AI 运用** — OpenClaw 无 thought_gate / query_budget / model_router，无法按成本智能选择模型
3. **长期自我进化** — OpenClaw 通用记忆不适合结构化交易学习
4. **硬件/基础设施感知** — OpenClaw heartbeat 30 分钟一次，不够实时

### OpenClaw 可复用的零成本功能
| 功能 | 用途 | 成本 |
|------|------|------|
| `message send` | Telegram 告警推送 | 零（不过 AI） |
| `gateway usage-cost` | AI 成本追踪 | 零 |
| Canvas | HTML 仪表盘 | 零 |
| `cron` shell | 定时任务 | 零 |
| `command-logger` hook | 操作审计 | 零 |

### 需 AI 成本的功能（暂缓）
- heartbeat（30min 自检）
- 自然语言聊天
- coding-agent

---

## 二、三层 Agent 架构设计方向（Layer 2 AI 推理循环）

已确定方向，详细设计待后续专项完成：

```
Layer 0: 确定性监控（零成本，持续运行）
  → 现有 H0 + Observer，price tick、freshness、health check
  → 每秒级运行，纯本地计算

Layer 1: 情势评估（轻量 AI，~$0.01/次）
  → 升级版 thought_gate，用 Haiku 级模型快速判断
  → 是否值得深入分析？有无异常需要关注？
  → 每小时 2-6 次

Layer 2: 深度推理（完整 AI Agent 循环，$0.50-2.00/次）
  → 有工具的 Agent：web_search、fetch_url、query_onchain 等
  → 搜索相关新闻、分析基本面、评估多因子
  → 每天 1-10 次，仅高价值场景触发

预估日成本：$1-6（vs 纯 OpenClaw 方案 $50-100）
```

---

## 三、统一控制台（Unified Console）

### 新增文件
- `app/static/console.html` — 统一控制台页面

### 功能
- **左侧边栏：** AI 成本实时显示（今日/30天）、Paper PnL、Session 状态、系统健康（API + OpenClaw Gateway）
- **主区域 Tab 1：** Trading Dashboard（iframe 嵌入 `/static/index.html`，同源无问题）
- **主区域 Tab 2：** OpenClaw Control（因 X-Frame-Options 安全限制无法 iframe 嵌入，改为"新窗口打开"按钮 + Gateway 状态面板）
- 15 秒自动刷新，时钟显示，Token 管理

### AI 成本追踪路由
- `GET /api/v1/paper/ai-cost` — 调用 `openclaw gateway usage-cost --json` 读取 token/成本数据
- 返回：今日成本、30 天累计、token 用量、成本分解、每日明细
- 零额外 AI 开销

### 控制台入口路由
- `GET /console` — 统一控制台入口（在 `main_legacy.py` 中注册）

### OpenClaw Canvas 对接
- `~/.openclaw/canvas/index.html` → iframe 指向 `http://127.0.0.1:8000/console`
- 注意：Canvas 主要供 OpenClaw 移动端 companion app 使用，浏览器中 `/canvas/` 路径展示的是 OpenClaw SPA

---

## 四、API 服务器 systemd 自启动

### 问题
用户每次需手动运行 `uvicorn app.main:app --host 0.0.0.0 --port 8000`，重启后服务消失。

### 解决方案
创建 systemd 用户服务，参照已有的 `openclaw-gateway.service` 模式。

### 服务文件
`~/.config/systemd/user/openclaw-trading-api.service`

```ini
[Unit]
Description=OpenClaw Trading Control API (Paper Trading Beta)
After=network-online.target openclaw-gateway.service

[Service]
WorkingDirectory=/.../control_api_v1
ExecStart=/.../control_api_v1/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
```

### 管理命令
```bash
systemctl --user status openclaw-trading-api   # 查看状态
systemctl --user restart openclaw-trading-api   # 重启
systemctl --user stop openclaw-trading-api      # 停止
journalctl --user -u openclaw-trading-api -f    # 查看日志
```

### 注意
- 绑定 `127.0.0.1`（仅本地访问），远程访问需通过 SSH 隧道或其他安全方案

---

## 五、远程访问方案（待实施）

### 问题
API 服务器绑定 `127.0.0.1:8000`，无法从远程设备访问控制台。

### 推荐方案对比

| 方案 | 安全性 | 复杂度 | 适用场景 |
|------|--------|--------|----------|
| **SSH 隧道** | 最高 | 最低 | 个人使用，临时访问 |
| **Tailscale** | 很高 | 低 | 多设备长期使用，免开端口 |
| **Cloudflare Tunnel** | 很高 | 中 | 需域名访问，自带 HTTPS + Access 认证 |
| **Caddy 反向代理** | 中 | 中 | 需公网端口 + HTTPS 证书 |

### SSH 隧道用法（最简方案）
```bash
# 从远程机器执行
ssh -L 8000:127.0.0.1:8000 ncyu@服务器IP
# 然后浏览器打开 http://localhost:8000/console

# 后台持久运行
ssh -fNL 8000:127.0.0.1:8000 ncyu@服务器IP

# 添加 alias 到 ~/.bashrc
alias trading='ssh -fNL 8000:127.0.0.1:8000 ncyu@服务器IP && echo "http://localhost:8000/console"'
```

### 后续考虑
- 如果需要移动端访问，Tailscale 或 Cloudflare Tunnel 更合适
- 无论哪种方案，API 层已有 Bearer Token 认证 + 速率限制，安全基础已就绪
- 如果选择绑定 `0.0.0.0`，需同步部署 HTTPS（Caddy/Nginx + Let's Encrypt）+ CSP 安全头

---

## 数据汇总

| 指标 | 数值 |
|------|------|
| 总路由 | **75 条**（47 main_legacy + 24 paper_routes + 4 静态/控制台） |
| 总测试 | **248 个，全部通过** |
| systemd 服务 | 2 个（openclaw-gateway + openclaw-trading-api） |
| 新增/修改文件 | console.html（修复 iframe）+ systemd 服务文件 |

---

## 安全不变量确认

```
system_mode             = read_only        ✅ 未变
execution_state         = disabled         ✅ 未变
execution_authority     = not_granted      ✅ 未变
decision_lease_emitted  = false            ✅ 未变
API 绑定                = 127.0.0.1 only   ✅ 仅本地
```

---

## 下一步

1. **远程访问方案选定与实施** — SSH 隧道 / Tailscale / Cloudflare Tunnel
2. **Layer 2 AI 推理循环设计与实现** — 三层架构详细设计
3. **Telegram 告警通道** — 接 OpenClaw channels
4. **自动循环 cron** — observer cycle → shadow decision → paper order → fill tick
5. **Beta 运行数据积累** → M 章
