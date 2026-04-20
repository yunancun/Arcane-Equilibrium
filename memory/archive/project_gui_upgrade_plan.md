---
name: GUI Upgrade Plan
description: Next session priority — GUI overhaul with login auth, 10 panels, unified token management
type: project
---

## GUI 大改计划（下一轮对话重点）

### 认证方案（已搭好基础设施）
- 凭证文件: `/home/ncyu/BybitOpenClaw/secrets/gui_auth.env`（GUI_USERNAME + GUI_PASSWORD，在 srv/ 外面的统一 secrets 目录）
- 用户填好后重启服务即可
- 后端需新增: `POST /api/v1/auth/login` 接收 username/password → 返回 Bearer token
- 前端需新增: 登录页面（username + password 输入框）→ 成功后 token 存 localStorage
- 登录后所有页面（/gui, /console, 策略面板）自动使用 token
- 不再需要手动复制粘贴 Bearer token

### 10 个面板待建
G1 策略管理面板: 策略列表/状态/激活停止, K线图, 指标可视化, 信号历史
G2 StopManager 面板: 追踪持仓, 止损配置, 触发历史
G3 Pipeline Bridge 面板: tick 统计, 意图提交历史, 管线健康指标
G4 Regime 可视化: 当前市场 regime, 共识方向, 加权得分仪表盘
G5 Grid Trading 专属面板: 网格可视化, 库存状态, 边界健康
G6 Funding Rate 面板: 当前费率, delta-neutral 持仓, 套利损益
G7 Telegram 配置面板: 告警状态, 发送统计, 测试按钮
G8 AI 咨询面板: L2 引擎状态, 咨询接口
G9 实时 PnL 图表: 余额曲线, 策略分 PnL, 手续费分解
G10 整体 UI 升级: 统一暗色主题, 响应式布局, Tab 导航重构, 登录页

### Token 统一管理
- 当前问题: index.html 和 console.html 各自管理 token，互不相通
- 解决方案: 统一 login 页面 → token 存 localStorage → 所有页面共享
- console.html 的 OpenClaw 状态通过 /openclaw/ 代理读取（已搭好）

### 远程访问（已配好）
- Trading GUI: http://trade-core:8000
- OpenClaw: https://trade-core.tail358794.ts.net
- 详见 memory/reference_remote_access.md
