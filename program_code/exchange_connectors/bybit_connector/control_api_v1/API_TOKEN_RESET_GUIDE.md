# OpenClaw API Token 重置指南 / API Token Reset Guide

本文档说明如何设置和重置 OpenClaw Control API 的认证 Token。

This document explains how to set and reset the OpenClaw Control API authentication token.

---

## Token 解析优先级 / Token Resolution Order

系统按以下顺序查找 Token，找到第一个有效值即停止：

1. **环境变量** `OPENCLAW_API_TOKEN`（推荐生产环境使用）
2. **Token 文件**（由 `OPENCLAW_API_TOKEN_FILE` 环境变量指定路径）
3. **默认 Token 文件** `control_api_v1/.secrets/api_token`
4. **自动生成** — 如果以上都没有，系统自动生成一个安全 Token 并保存到默认文件

---

## 方法一：通过环境变量设置（推荐）

最安全的方式，Token 不落盘。

```bash
# 从私有密钥管理器读取 Token；不要在终端打印 Token
# Read the token from a private secret manager; do not print it in the terminal
export OPENCLAW_API_TOKEN="$(security find-generic-password -s openclaw_api_token -w)"

# 启动服务
bash start_local.sh
```

如果使用 `.env` 文件：

```bash
# 生成并写入 .env，文件权限仅 owner 可读写
# Generate into .env with owner-only permissions
umask 077
python3 - <<'PY' >> .env
import secrets
print(f"OPENCLAW_API_TOKEN={secrets.token_urlsafe(32)}")
PY
```

---

## 方法二：通过 Token 文件设置

适合需要持久化但不想用环境变量的场景。

```bash
# 创建 secrets 目录（权限仅 owner）
mkdir -p .secrets && chmod 700 .secrets

# 生成 Token 文件（权限仅 owner 可读写）
python3 -c "import secrets; print(secrets.token_urlsafe(32))" > .secrets/api_token
chmod 600 .secrets/api_token

```

也可以指定自定义路径：

```bash
export OPENCLAW_API_TOKEN_FILE=/path/to/your/secret/token_file
```

---

## 方法三：自动生成（首次启动）

如果没有设置任何 Token，系统会：

1. 自动生成一个 `secrets.token_urlsafe(32)` 的安全 Token
2. 保存到 `.secrets/api_token`（权限 0o600）

**不要依赖启动日志披露 Token。** 首次启动后，如果需要取用 Token，请通过受保护的 Token 文件或密钥管理器读取，不要把 Token 打印到共享终端或日志。

**Do not rely on startup logs to disclose tokens.** After first startup, read the token only from the protected token file or a secrets manager; do not print it into shared terminals or logs.

---

## 重置 Token / Reset Token

### 情况一：忘记了当前 Token

```bash
# 不显示旧 Token；直接生成并替换
# Do not display the old token; generate and replace it
umask 077
python3 -c "import secrets; print(secrets.token_urlsafe(32))" > .secrets/api_token
chmod 600 .secrets/api_token
```

### 情况二：Token 泄露，需要立即更换

```bash
# 1. 生成新 Token
NEW_TOKEN=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")

# 2. 更新 Token 文件
printf '%s\n' "$NEW_TOKEN" > .secrets/api_token
chmod 600 .secrets/api_token

# 3. 或者更新环境变量
export OPENCLAW_API_TOKEN="$NEW_TOKEN"

# 4. 重启服务（Token 在启动时加载）
# 停止当前服务后重新启动
bash start_local.sh

# 5. 用新 Token 测试连接：把 header 放入 0600 临时文件，避免出现在 curl argv
# Test with the new token via a 0600 temp config so it does not appear in curl argv
AUTH_CONFIG=$(mktemp "${TMPDIR:-/tmp}/openclaw-curl-auth.XXXXXX")
chmod 600 "$AUTH_CONFIG"
trap 'rm -f "$AUTH_CONFIG"' EXIT
printf 'header = "Authorization: Bearer %s"\n' "$NEW_TOKEN" > "$AUTH_CONFIG"
curl -s --config "$AUTH_CONFIG" http://localhost:8000/api/v1/system/overview | head -20
```

### 情况三：清除所有认证状态，完全重置

```bash
# 1. 删除 Token 文件
rm -f .secrets/api_token

# 2. 清除环境变量
unset OPENCLAW_API_TOKEN
unset OPENCLAW_API_TOKEN_FILE

# 3. 重启服务 — 系统会自动生成新 Token
bash start_local.sh
# 新 Token 保存到受保护文件；不要依赖日志披露
```

---

## 安全注意事项 / Security Notes

1. **不要把 Token 提交到 Git。** `.secrets/` 目录应在 `.gitignore` 中
2. **Token 文件权限必须是 0o600**（仅 owner 可读写）
3. **secrets 目录权限必须是 0o700**（仅 owner 可访问）
4. **生产环境优先使用环境变量**，避免 Token 落盘
5. **定期轮换 Token** — 建议每 90 天更换一次
6. **Token 泄露后立即更换** — 按上述"情况二"操作

---

## GUI 连接 / GUI Connection

在 GUI 页面顶部的 Token 输入框中粘贴你的 Token，然后点击"连接 / Connect"。

Token 仅在内存中保持，关闭浏览器标签页后自动清除。

---

## 环境变量汇总 / Environment Variables Summary

| 变量名 | 用途 | 默认值 |
|--------|------|--------|
| `OPENCLAW_API_TOKEN` | API 认证 Token | 无（必须设置或使用文件） |
| `OPENCLAW_API_TOKEN_FILE` | Token 文件路径 | `.secrets/api_token` |
| `OPENCLAW_CORS_ORIGINS` | 允许的 CORS 源（逗号分隔） | 空（仅同源） |
| `OPENCLAW_RATE_LIMIT` | 速率限制 | `120/minute` |
