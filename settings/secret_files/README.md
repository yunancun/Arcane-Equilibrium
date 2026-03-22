# secret_files
# secret_files

这里存放交易系统相关的敏感凭据文件。
This folder stores sensitive credential files related to the trading system.

当前主要预留给：
This folder is currently reserved mainly for:

- Bybit 凭据
- Bybit credentials

- Binance 凭据
- Binance credentials

重要规则：
Important rules:

- 不要把真实 API key 和 secret 写进代码文件。
- Do not place real API keys or secrets directly into code files.

- 不要把真实 API key 和 secret 写进 README。
- Do not place real API keys or secrets into README files.

- 真实凭据应分别放在 api_key 和 api_secret 文件中。
- Real credentials should be placed separately into api_key and api_secret files.

- read_only、demo、live 应严格分开管理。
- read_only, demo, and live credentials should be managed strictly separately.
