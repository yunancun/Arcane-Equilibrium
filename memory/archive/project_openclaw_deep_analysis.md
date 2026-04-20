---
name: OpenClaw 深度潛力分析決策
description: 2026-04-03 分析 OpenClaw 未開發能力，確定 6 項可行整合 + 排除 Canvas/ClawHub，新增 WebSocket 自建方案
type: project
---

## 決策結論（2026-04-03）

### 確認可行（已加入 TODO.md OC-1~6）
1. **Webhook 告警通道** — 零 AI 成本，Python POST → OpenClaw → Telegram（最高優先）
2. **Telegram 通道配置** — OC-1 前置，當前 channels=0
3. **多通道分級告警** — P0/P1/P2/P3 分流到不同通道
4. **MCP PostgreSQL** — Operator 自然語言查交易數據，按需 AI 成本
5. **Cron 健康心跳** — 等 --exec flag（GitHub #24597/#29907），否則用系統 crontab 繞過
6. **Sub-agent 回測** — 週頻，coding-agent skill 已 ready

### 已排除
- **Canvas A2UI** — A2UI push 是 WIP 未完成；手機端前台限制不實用；現有 FastAPI GUI 已夠用
- **ClawHub Skills** — 金融系統安全考量，不跑未審計第三方代碼

### 替代決策
- **WS-1 WebSocket/SSE** — 取代 Canvas 實時推送需求，在 FastAPI 上自建，延遲 <100ms，完全自主可控

**Why:** OpenClaw 最大未開發價值在通信層深化（告警分級 + Operator 態勢感知），而非替代本地 GUI 或交易邏輯。
**How to apply:** OC-1~2 優先做（Telegram 告警），其餘按需排期。GUI 實時化走自建 WebSocket。
