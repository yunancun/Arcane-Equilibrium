# OpenClaw 服务部署指南 / Service Deployment Guide
# 支持平台 / Supported Platforms: Ubuntu (systemd) / macOS (launchd)

---

## 架构概览 / Architecture Overview

OpenClaw 运行两个独立服务：

| 服务 / Service | 说明 / Description | 默认端口 / Default Port |
|---|---|---|
| **Trading API** | FastAPI + Uvicorn，交易控制核心 | 8000 |
| **OpenClaw Gateway** | Node.js，AI 网关（可选） | 18789 |

Trading API 是必需服务；Gateway 为可选（提供 AI 代理中转）。
Trading API 通过 `/openclaw/*` 反向代理自动连接 Gateway（如运行中）。

---

## 环境变量清单 / Environment Variables

### 核心变量 / Core Variables

| 变量 / Variable | 用途 / Purpose | 默认值 / Default | 必需 / Required |
|---|---|---|---|
| `OPENCLAW_SRV_ROOT` | 项目根目录（legacy 别名 / legacy alias）| 自动推导 / Auto-detected | 否（115 历史脚本仍读取；新代码请用 `OPENCLAW_BASE_DIR`） |
| `OPENCLAW_BASE_DIR` | 项目根目录（新代码权威 / Authoritative for new code）| 自动推导 / Auto-detected | 否（推荐设置，Mac 部署必设） |
| `OPENCLAW_API_TOKEN` | API 认证 Token | 无（从文件读取） | 是（或设置文件） |
| `OPENCLAW_API_TOKEN_FILE` | Token 文件路径 | `.secrets/api_token` | 否 |
| `OPENCLAW_GATEWAY_HOST` | Gateway 绑定地址 | `127.0.0.1` | 否 |
| `OPENCLAW_GATEWAY_PORT` | Gateway 端口 | `18789` | 否 |
| `BYBIT_API_HOST` | Bybit API 地址 | `https://api-testnet.bybit.com` | 否 |
| `OLLAMA_BASE_URL` | Ollama 推理地址 | `http://localhost:11434` | 否 |
| `OLLAMA_MODEL` | 默认 Ollama 模型 | `qwen3.5:9b` | 否 |
| `TZ` | 时区 | `Europe/Madrid` | 否 |

### 数据库变量 / Database Variables

| 变量 / Variable | 用途 / Purpose | 默认值 / Default | 必需 / Required |
|---|---|---|---|
| `PG_HOST` | PostgreSQL 地址 | `127.0.0.1` | 否 |
| `PG_PORT` | PostgreSQL 端口 | `5432` | 否 |
| `PG_USER` | PostgreSQL 用户 | `trading_admin` | 否 |
| `PG_PASS` | PostgreSQL 密码 | 从 `.secrets/pg_pass` 读取 | 是（或设置文件） |
| `PG_DB` | PostgreSQL 数据库名 | `trading_ai` | 否 |

### Telegram 通知（可选） / Telegram Notifications (Optional)

| 变量 / Variable | 用途 / Purpose | 默认值 / Default | 必需 / Required |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Telegram Bot Token | 无 | 否 |
| `TELEGRAM_CHAT_ID` | Telegram Chat ID | 无 | 否 |

### AI 供应商密钥（可选） / AI Provider Keys (Optional)

| 变量 / Variable | 用途 / Purpose | 必需 / Required |
|---|---|---|
| `OPENAI_API_KEY` | OpenAI API 密钥 | 否（L2 推理需要） |
| `ANTHROPIC_API_KEY` | Anthropic API 密钥 | 否（L2 推理需要） |
| `PERPLEXITY_API_KEY` | Perplexity 搜索密钥 | 否（搜索降级需要） |

> **安全提醒 / Security Note**: 密钥应通过文件注入或环境变量传递，禁止硬编码。
> 推荐方式：将密钥放在 `settings/secret_files/` 目录下，通过 `lib_trading_env.sh` 自动加载。

---

## 文件路径约定 / File Path Conventions

```
$SRV_ROOT/                                          # 项目根 = $OPENCLAW_BASE_DIR
                                                     # Linux 例: /home/ncyu/BybitOpenClaw/srv
                                                     # Mac   例: /Users/ncyu/Documents/Projects/TradeBot
├── program_code/.../control_api_v1/                 # Trading API 应用目录（uvicorn WorkingDirectory）
│   ├── .venv/                                       # Python 虚拟环境
│   ├── .secrets/api_token                           # API Token 文件
│   └── app/main.py                                  # FastAPI 入口（app.main:app）
├── settings/
│   ├── environment_files/trading_services.env        # 业务环境变量
│   ├── environment_files/basic_system_services.env   # 基础服务变量（PG/Redis）
│   └── secret_files/ai/                              # AI 密钥文件
├── helper_scripts/
│   ├── start_paper_trading.sh                        # Paper Trading 自动启动脚本
│   └── cron_daily_report.sh                          # 每日报告 cron 脚本
└── logs/                                             # 日志目录
```

---

## Ubuntu (systemd)

### 现有服务文件位置 / Existing Service Files

```
~/.config/systemd/user/openclaw-trading-api.service
~/.config/systemd/user/openclaw-gateway.service
```

两个服务均注册为 **user-level systemd unit**（`systemctl --user`），不需要 root 权限。

### 安装 / Installation

1. 复制 service 文件（如果从新机器部署）：

```bash
mkdir -p ~/.config/systemd/user

# Trading API service
cat > ~/.config/systemd/user/openclaw-trading-api.service << 'UNIT'
[Unit]
Description=OpenClaw Trading Control API (Paper Trading Beta)
After=network-online.target openclaw-gateway.service
Wants=network-online.target

[Service]
WorkingDirectory=%h/BybitOpenClaw/srv/program_code/exchange_connectors/bybit_connector/control_api_v1
Environment=OPENCLAW_BIND_HOST=127.0.0.1
ExecStart=%h/BybitOpenClaw/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/.venv/bin/uvicorn app.main:app --host ${OPENCLAW_BIND_HOST} --port 8000
Restart=always
RestartSec=5
TimeoutStopSec=30
TimeoutStartSec=30
Environment=HOME=%h
Environment=TMPDIR=/tmp

[Install]
WantedBy=default.target
UNIT

# 重载 daemon
systemctl --user daemon-reload
systemctl --user enable openclaw-trading-api.service
```

> **说明 / Note**: `%h` 是 systemd 的 home 目录宏，自动替换为当前用户的 `$HOME`。

2. 确保 user lingering 已启用（服务器重启后自动运行用户服务）：

```bash
sudo loginctl enable-linger $(whoami)
```

### 启动 / 停止 / 重启 / Start / Stop / Restart

```bash
# 启动 / Start
systemctl --user start openclaw-trading-api

# 停止 / Stop
systemctl --user stop openclaw-trading-api

# 重启 / Restart
systemctl --user restart openclaw-trading-api

# 查看状态 / Status
systemctl --user status openclaw-trading-api

# Gateway 同理 / Gateway likewise
systemctl --user start openclaw-gateway
systemctl --user stop openclaw-gateway
```

### 日志查看 / View Logs

```bash
# 实时日志 / Live tail
journalctl --user -u openclaw-trading-api -f

# 最近 100 行 / Last 100 lines
journalctl --user -u openclaw-trading-api -n 100

# 今天的日志 / Today's logs
journalctl --user -u openclaw-trading-api --since today

# Gateway 日志 / Gateway logs
journalctl --user -u openclaw-gateway -f
```

### Paper Trading 自动启动 / Auto-start Paper Trading

Paper pipeline 默认禁用。不要把 `start_paper_trading.sh` 作为常规
`ExecStartPost` 自动启动项；只有在 engine 进程环境显式设置
`OPENCLAW_ENABLE_PAPER=1` 时才可手动运行：

```bash
export OPENCLAW_ENABLE_PAPER=1
bash %h/BybitOpenClaw/srv/helper_scripts/start_paper_trading.sh
```

---

## macOS (launchd)

### plist 文件位置 / Plist File Location

倉庫提供 4 個 launchd plist 範本（對應 Linux systemd 單元）：

```
~/Library/LaunchAgents/com.openclaw.trading-api.plist       # FastAPI uvicorn
~/Library/LaunchAgents/com.openclaw.gateway.plist           # Node.js OpenClaw Gateway
~/Library/LaunchAgents/com.openclaw.engine.plist            # Rust openclaw-engine 主進程
~/Library/LaunchAgents/com.openclaw.engine-watchdog.plist   # Python 存活監控
```

### 占位符 / Placeholders

plist 範本使用兩個占位符，安裝時用 `sed` 替換為實際絕對路徑：

| 占位符 | 含義 | 替換來源 |
|---|---|---|
| `__HOME__` | 用戶家目錄（log 路徑、PATH） | `$HOME`（e.g. `/Users/ncyu`） |
| `__BASE__` | repo 根目錄（binary、WorkingDirectory） | `$OPENCLAW_BASE_DIR`（e.g. `/Users/ncyu/Documents/Projects/TradeBot`） |

Gateway plist 只用 `__HOME__`（Node 模組裝在 npm-global，不參考 repo 根）。

### 安裝 / Installation

1. 設定 `OPENCLAW_BASE_DIR` 指向 repo 絕對路徑（若尚未設）：

```bash
export OPENCLAW_BASE_DIR="$(pwd)"  # 在 repo 根執行
```

2. 複製 plist 範本並 sed 替換占位符：

```bash
mkdir -p ~/Library/LaunchAgents ~/Library/Logs/openclaw

for plist in com.openclaw.trading-api com.openclaw.gateway \
             com.openclaw.engine com.openclaw.engine-watchdog; do
  cp "helper_scripts/deploy/${plist}.plist" ~/Library/LaunchAgents/
  sed -i '' "s|__BASE__|$OPENCLAW_BASE_DIR|g" ~/Library/LaunchAgents/${plist}.plist
  sed -i '' "s|__HOME__|$HOME|g" ~/Library/LaunchAgents/${plist}.plist
done
```

3. **先跑 preflight（必做）**：

```bash
bash "$OPENCLAW_BASE_DIR/helper_scripts/deploy/launchd_preflight.sh"
```

preflight 會 fail-closed 驗證：
- plist 是否仍有 `__BASE__` / `__HOME__` 未替換占位符
- `openclaw_database_url` / `ipc_secret.txt` 是否存在且非 placeholder
- `OPENCLAW_BASE_DIR` 是否指向有效 `srv` 根

4. 載入服務（依賴順序：engine → watchdog → api → gateway）：

```bash
launchctl load ~/Library/LaunchAgents/com.openclaw.engine.plist
launchctl load ~/Library/LaunchAgents/com.openclaw.engine-watchdog.plist
launchctl load ~/Library/LaunchAgents/com.openclaw.trading-api.plist
launchctl load ~/Library/LaunchAgents/com.openclaw.gateway.plist
```

**注意**：IPC secret / DB URL 等機敏值**不要**寫在 plist 或 launchd 全局環境裡；只注入 0600 secret file 的路徑：

```bash
umask 077
printf 'postgresql://redacted@127.0.0.1:5432/trading_ai\n' \
  "$(awk -F= '$1=="POSTGRES_PASSWORD"{print substr($0, index($0,$2))}' "$OPENCLAW_SECRETS_ROOT/environment_files/basic_system_services.env")" \
  > "$OPENCLAW_SECRETS_ROOT/environment_files/openclaw_database_url"
launchctl setenv OPENCLAW_IPC_SECRET_FILE "$OPENCLAW_SECRETS_ROOT/environment_files/ipc_secret.txt"
launchctl setenv OPENCLAW_DATABASE_URL_FILE "$OPENCLAW_SECRETS_ROOT/environment_files/openclaw_database_url"
# setenv 後需 unload + load 讓 agent 重讀 file path；不要用 setenv 傳 secret 值。
```

Gateway plist 模板只保留非敏感运行元数据；供应商密钥放 OS Keychain、secret manager 或 0600 文件，由服务 wrapper 读取；不要把供应商密钥、占位 key 或 secret 值写入 plist / launchd 全局环境。
Gateway plist templates only keep non-sensitive runtime metadata; provider keys belong in OS Keychain, a secret manager, or 0600 files read by a service wrapper, not in plist files or global launchd env.

### 启动 / 停止 / 重启 / Start / Stop / Restart

```bash
# 启动 / Start
launchctl start com.openclaw.trading-api

# 停止 / Stop
launchctl stop com.openclaw.trading-api

# 重启 / Restart（需先 stop 再 start）
launchctl stop com.openclaw.trading-api && launchctl start com.openclaw.trading-api

# 完全卸载再重载（配置变更后）
launchctl unload ~/Library/LaunchAgents/com.openclaw.trading-api.plist
launchctl load ~/Library/LaunchAgents/com.openclaw.trading-api.plist

# 查看状态 / Status
launchctl list | grep openclaw
```

### 日志查看 / View Logs

```bash
# 实时日志 / Live tail
tail -f ~/Library/Logs/openclaw/trading-api-stdout.log
tail -f ~/Library/Logs/openclaw/trading-api-stderr.log

# 最近 100 行 / Last 100 lines
tail -n 100 ~/Library/Logs/openclaw/trading-api-stderr.log
```

> **提示 / Tip**: 建议创建日志目录 `mkdir -p ~/Library/Logs/openclaw`。

---

## 依赖服务 / Dependency Services

### PostgreSQL

Trading API 通过 Grafana data writer 和 Demo sync 连接 PostgreSQL。

| 平台 / Platform | 安装方式 / Installation |
|---|---|
| Ubuntu | `sudo apt install postgresql` 或 Docker |
| macOS | `brew install postgresql@16` |

```bash
# 验证连接 / Verify connection
psql -h 127.0.0.1 -U trading_admin -d trading_ai -c "SELECT 1;"
```

### Ollama（L1 本地推理 / Local Inference）

Trading API 使用 Ollama 进行本地 AI 推理（Qwen 3.5 9B/27B）。

| 平台 / Platform | 安装方式 / Installation |
|---|---|
| Ubuntu | `curl -fsSL https://ollama.com/install.sh \| sh` |
| macOS | `brew install ollama` 或从 [ollama.com](https://ollama.com) 下载 |

```bash
# 拉取模型 / Pull models
ollama pull qwen3.5:9b
ollama pull qwen3.5:27b

# 验证运行 / Verify
curl http://localhost:11434/api/tags
```

### Redis（可选 / Optional）

当前系统不强依赖 Redis。如需启用：

```bash
# Ubuntu
sudo apt install redis-server

# macOS
brew install redis
```

---

## 端口配置 / Port Configuration

| 服务 / Service | 端口 / Port | 协议 / Protocol | 说明 / Description |
|---|---|---|---|
| Trading API (uvicorn) | 8000 | HTTP | 主控制 API + GUI |
| OpenClaw Gateway | 18789 | HTTP | AI 网关（loopback only） |
| PostgreSQL | 5432 | TCP | 数据库 |
| Ollama | 11434 | HTTP | 本地 AI 推理 |
| Redis | 6379 | TCP | 缓存（可选） |
| Grafana | 3000 | HTTP | 监控面板（可选） |

> **安全提醒 / Security Note**: Trading API 默认绑定 `127.0.0.1:8000`。
> 远程访问请优先通过 Tailscale Serve / 反向代理转发；如需直接监听 Tailscale
> 接口，显式设置 `OPENCLAW_BIND_HOST=<tailscale-100.x-ip>`，不要默认暴露
> `0.0.0.0`。Gateway 绑定 loopback，不对外暴露。

---

## 启动顺序 / Startup Order

```
1. PostgreSQL          — 数据库就绪（Grafana writer 依赖）
2. Ollama              — 本地推理就绪（L1 推理依赖，fail-open）
3. OpenClaw Gateway    — AI 网关就绪（可选，fail-open）
4. Trading API         — 主服务启动
   ├── _startup_integrity_check()   — 验证硬依赖（GovernanceHub/Engine/RiskManager）
   ├── SymbolCategoryRegistry       — 背景 daemon thread 填充（非阻塞）
   ├── ExperimentLedger auto-seed   — 背景自动填充假设（fail-open）
   └── EvolutionScheduler           — 背景进化排程器（fail-open）
5. start_paper_trading.sh          — 激活 Paper Trading session + 策略
```

systemd `After=` 指令确保 Trading API 在 Gateway 之后启动。
launchd 无原生依赖排序，但 Trading API 对 Gateway 的连接为 fail-open（Gateway 不可用不阻塞启动）。

---

## Cron 任务 / Cron Jobs

```bash
# 每日报告（UTC 0:00）/ Daily report
0 0 * * * /path/to/helper_scripts/cron_daily_report.sh >> /path/to/logs/daily_report.log 2>&1
```

macOS 上可用 launchd plist 替代 cron（参见 `com.openclaw.daily-report.plist` 示例）。

---

## 故障排查 / Troubleshooting

### Trading API 启动失败 / Startup Failure

```bash
# 检查 Python 虚拟环境 / Check venv
.venv/bin/python -c "import fastapi; print(fastapi.__version__)"

# 手动启动排查 / Manual start for debugging
cd program_code/exchange_connectors/bybit_connector/control_api_v1
.venv/bin/uvicorn app.main:app --host "${OPENCLAW_BIND_HOST:-127.0.0.1}" --port 8000 --log-level debug
```

### API Token 问题 / Token Issues

```bash
# 验证 Token 文件存在 / Verify token file
test -s .secrets/api_token && stat -f '%Sp %N' .secrets/api_token 2>/dev/null || stat -c '%A %n' .secrets/api_token

# 测试认证：把 header 放入 0600 临时文件，避免 token 出现在 curl argv
# Test auth: put the header in a 0600 temp config so the token is not exposed in curl argv
AUTH_CONFIG=$(mktemp "${TMPDIR:-/tmp}/openclaw-curl-auth.XXXXXX")
chmod 600 "$AUTH_CONFIG"
trap 'rm -f "$AUTH_CONFIG"' EXIT
printf 'header = "Authorization: Bearer %s"\n' "$(cat .secrets/api_token)" > "$AUTH_CONFIG"
curl -s --config "$AUTH_CONFIG" http://127.0.0.1:8000/api/v1/system/health
```

### 启动后 Paper Trading 未激活 / Paper Trading Not Active After Start

```bash
# 手动执行启动脚本 / Run startup script manually
export OPENCLAW_ENABLE_PAPER=1
bash helper_scripts/start_paper_trading.sh
```

---

## systemd 与 launchd 对照表 / Comparison

| 功能 / Feature | systemd | launchd |
|---|---|---|
| 配置文件 / Config | `.service` (INI) | `.plist` (XML) |
| 安装位置 / Location | `~/.config/systemd/user/` | `~/Library/LaunchAgents/` |
| 加载 / Load | `systemctl --user daemon-reload` | `launchctl load <plist>` |
| 启动 / Start | `systemctl --user start <name>` | `launchctl start <label>` |
| 自动重启 / Auto-restart | `Restart=always` | `<KeepAlive><true/></KeepAlive>` |
| 日志 / Logs | `journalctl --user -u <name>` | `tail -f ~/Library/Logs/...` |
| 开机自启 / Auto-start | `enable` + `loginctl enable-linger` | 放入 `~/Library/LaunchAgents/` 即可 |
| 依赖排序 / Ordering | `After=` / `Wants=` | 无原生支持（需脚本内等待） |
| 环境变量 / Env vars | `Environment=` 指令 | `<EnvironmentVariables>` 字典 |
