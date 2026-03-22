# Local Private Layout

当前 Git 仓库根目录对应旧的 srv 目录骨架。
The current Git repository root corresponds to the old srv skeleton.

真实私有内容不在本仓库中，统一放在：
Real private material is not stored in this repository, and should live under:

- ~/BybitOpenClaw/secrets/

建议本地布局：
Recommended local layout:

- ~/BybitOpenClaw/secrets/
- ~/BybitOpenClaw/srv/

其中：
Where:

- srv/ 用于代码、文档、模板、去敏配置
- srv/ is for code, docs, templates, and redacted config
- secrets/ 用于真实密钥与本地私有配置
- secrets/ is for real secrets and local private config
