# 远程访问 + 安全加固工程日志
# Remote Access + Security Hardening Engineering Log

**日期 / Date**: 2026-03-27
**状态 / Status**: 已完成

---

## 一、远程访问配置

### Trading GUI
- **URL**: `http://trade-core:8000`
- uvicorn 绑定从 `127.0.0.1` 改为 `0.0.0.0`
- 通过 Tailscale WireGuard 加密访问，无需 HTTPS
- systemd service: `~/.config/systemd/user/openclaw-trading-api.service`
- 永久生效，重启自动恢复

### OpenClaw Gateway
- **URL**: `https://trade-core.tail358794.ts.net`
- 使用 OpenClaw 原生 `--tailscale serve` 功能（自动 HTTPS）
- 配置: `--port 18789 --token <REDACTED> --tailscale serve`
- `~/.openclaw/openclaw.json` 中 `bind=loopback` + `allowedOrigins` 包含 HTTPS 域名
- MacBook Pro 设备已配对（`~/.openclaw/devices/paired.json`）

### OpenClaw 反向代理
- `http://trade-core:8000/openclaw/*` → `http://127.0.0.1:18789/*`
- FastAPI 路由在 `main.py` 中实现
- 用于 console.html 的 OpenClaw 状态检测（HTTP 层面）
- WebSocket 连接直接走 `wss://trade-core.tail358794.ts.net`（Tailscale HTTPS）

---

## 二、安全加固

### secrets 目录权限收紧
- 路径: `/home/ncyu/BybitOpenClaw/secrets/`（在 git 仓库外）
- 所有目录: `chmod 700`（仅 owner 可进入）
- 所有文件: `chmod 600`（仅 owner 可读写）
- 14 个目录 + 28 个文件全部锁定

### API Key 硬编码消除
- **问题**: `openclaw-gateway.service` 中 OPENAI_API_KEY 和 ANTHROPIC_API_KEY 明文写在 service 文件里
- **修复**: 改用 `EnvironmentFile=/home/ncyu/BybitOpenClaw/secrets/secret_files/ai/gateway_api_keys.env`
- 新建 `gateway_api_keys.env`，从已有 secret_files 读取 key 生成
- systemd service 文件中零明文 API key

### GUI 认证模板
- 新建: `/home/ncyu/BybitOpenClaw/secrets/gui_auth.env`
- 包含 GUI_USERNAME + GUI_PASSWORD 模板
- 用户已填写，下一轮 GUI 升级时实装后端认证

### secrets 文件夹整理
- 删除: `Perplexity：.txt`（重复文件）
- 移动: `Perpelexity.env` → `secret_files/ai/perplexity_api_key`
- 移动: `PerplexityAgent.env` → `secret_files/ai/perplexity_agent_example`

---

## 三、当前 secrets 目录结构

```
/home/ncyu/BybitOpenClaw/secrets/        (700)
├── gui_auth.env                          ← GUI 登录凭证
├── Ai.txt                                ← AI key 笔记（旧格式，待清理）
├── BB.txt                                ← Bybit key 笔记（旧格式，待清理）
├── secret_files/
│   ├── ai/
│   │   ├── openai_api_key
│   │   ├── anthropic_api_key
│   │   ├── perplexity_api_key
│   │   ├── perplexity_agent_example
│   │   └── gateway_api_keys.env          ← systemd EnvironmentFile 引用
│   ├── bybit/
│   │   ├── read_only/api_key + api_secret  (有内容)
│   │   ├── live/ + demo/                   (空占位)
│   │   └── README.md
│   └── binance/
│       ├── live/ + demo/ + read_only/      (空占位)
│       └── README.md
├── compose_env/trading_services.env
├── environment_files/trading_services.env + basic_system_services.env
└── service_configs/bybit_connector_config.json
```

---

## 四、关键配置文件位置（不在 git 内）

| 文件 | 用途 |
|------|------|
| `~/.config/systemd/user/openclaw-trading-api.service` | Trading API 服务 |
| `~/.config/systemd/user/openclaw-gateway.service` | OpenClaw Gateway 服务 |
| `~/.openclaw/openclaw.json` | OpenClaw 主配置 |
| `~/.openclaw/devices/paired.json` | 已配对设备 |
| `/home/ncyu/BybitOpenClaw/secrets/` | 所有密钥统一目录 |
