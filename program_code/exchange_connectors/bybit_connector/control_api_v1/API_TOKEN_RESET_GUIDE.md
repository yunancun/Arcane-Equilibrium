# OpenClaw API Token 重置指南 / API Token Reset Guide

本文档说明如何设置、查看和重置 OpenClaw Control API 的认证 Token。

This document explains how to set, view, and reset the OpenClaw Control API authentication token.

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
# 生成一个安全的随机 Token
export OPENCLAW_API_TOKEN=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")

# 查看当前 Token
echo $OPENCLAW_API_TOKEN

# 启动服务
bash start_local.sh
```

如果使用 `.env` 文件：

```bash
# 生成并写入 .env
echo "OPENCLAW_API_TOKEN=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')" >> .env
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

# 查看当前 Token
cat .secrets/api_token
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
3. 在 stderr 输出 Token 值和文件路径

**首次启动后请立即记录 Token 值。**

---

## 重置 Token / Reset Token

### 情况一：忘记了当前 Token

```bash
# 如果用的是文件方式，直接查看
cat .secrets/api_token

# 如果用的是环境变量，检查环境
echo $OPENCLAW_API_TOKEN
```

### 情况二：Token 泄露，需要立即更换

```bash
# 1. 生成新 Token
NEW_TOKEN=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")

# 2. 更新 Token 文件
echo "$NEW_TOKEN" > .secrets/api_token
chmod 600 .secrets/api_token

# 3. 或者更新环境变量
export OPENCLAW_API_TOKEN="$NEW_TOKEN"

# 4. 重启服务（Token 在启动时加载）
# 停止当前服务后重新启动
bash start_local.sh

# 5. 用新 Token 测试连接
curl -s -H "Authorization: Bearer $NEW_TOKEN" http://localhost:8000/api/v1/system/overview | head -20
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
# 新 Token 会打印在 stderr 输出中
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
