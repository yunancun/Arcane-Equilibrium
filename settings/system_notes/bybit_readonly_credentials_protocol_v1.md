# bybit_readonly_credentials_protocol_v1
# bybit_readonly_credentials_protocol_v1

这里定义 Bybit 只读凭据的读取规范。
This document defines the credential loading protocol for Bybit read-only mode.

当前阶段原则：
Current stage principles:

- 只读凭据只能从文件读取。
- Read-only credentials must be loaded from files only.

- 不应把真实凭据硬编码进代码。
- Real credentials must not be hardcoded into code.

- 不应把真实凭据写入 README 或普通配置文件。
- Real credentials must not be written into README files or normal config files.

默认路径（相对 repo 根 / relative to repo root）：
Default paths (relative to `$OPENCLAW_BASE_DIR`):

- api_key_file:    `$OPENCLAW_BASE_DIR/settings/secret_files/bybit/read_only/api_key`
- api_secret_file: `$OPENCLAW_BASE_DIR/settings/secret_files/bybit/read_only/api_secret`

在 Linux 預設部署下 `$OPENCLAW_BASE_DIR = $HOME/BybitOpenClaw/srv`；
在 macOS 非 $HOME 部署可指向任意絕對路徑（例如
`/Users/ncyu/Documents/Projects/TradeBot`）。
On Linux default, `$OPENCLAW_BASE_DIR = $HOME/BybitOpenClaw/srv`; on macOS
non-$HOME deployments, it may point to any absolute path.

只读模式下必须满足：
Read-only mode must satisfy:

- mode = read_only
- mode = read_only

- write_enabled = false
- write_enabled = false

- 凭据存在即可，不要求当前阶段已填入真实值
- credentials must exist, but do not need to contain real values at the current stage

后续真实接入前要求：
Requirements before real integration later:

- 确认 Bybit API key 的权限确实为只读
- Confirm the Bybit API key permissions are truly read-only

- 先在 connector status 中反映凭据状态
- First reflect credential state in connector status

- 再尝试真实 API 连通验证
- Then attempt real API connectivity validation
