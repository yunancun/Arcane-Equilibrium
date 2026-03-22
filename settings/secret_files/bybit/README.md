# bybit
# bybit

这里存放 Bybit 相关敏感凭据。
This folder stores sensitive credentials related to Bybit.

目录结构分为：
The folder structure is divided into:

- read_only：只读权限凭据
- read_only: credentials with read-only permissions

- demo：测试或演练环境凭据
- demo: credentials for testing or demo environments

- live：实盘环境凭据
- live: credentials for live trading environments

每个子目录下应分开保存：
Each subfolder should store separately:

- api_key
- api_key

- api_secret
- api_secret

建议流程：
Recommended workflow:

先准备 read_only，再准备 demo，最后才考虑 live。
Prepare read_only first, then demo, and only later consider live.
