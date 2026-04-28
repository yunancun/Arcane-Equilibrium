---
name: 外部工具權威邊界守則（Linear-only active posture）
description: 2026-04-29 operator 決定：Linear 唯一 active workflow tool；其他 connector 凍結 / 待命 / 拒絕；git 永遠是 source of truth
type: feedback
---

**規則**：外部 MCP 工具在 OpenClaw 工作流中**只有 Linear 是 active**。Notion = frozen 快照不維護；Drive = passive on-demand；Coupler.io / Slack / MotherDuck = declined 不啟用。任何衝突一律以 git `srv/` 為準。

**Why this exists（2026-04-29）**：

Operator 同步加裝 5 個 MCP（Linear / Notion / Coupler.io / Google Drive / MotherDuck），加上 engineering plugin pack 內附的 Slack 等。經評估後簡化為 **Linear-only active**：
- Single-operator project，Slack/Notion 的「團隊協作 / share」紅利拿不到
- Linux trade-core 128 GB unified mem，本機 DuckDB / psql 完整覆蓋 Coupler / MotherDuck 的分析 use case
- 多一個 mirror = 多一個 silent drift 點；歷史教訓：`decision_outcomes` timeframe 字串格式不一致 → 100% NULL

**核心邊界**：

1. **Linear** = 62-finding remediation tracker / 鏡像 `docs/audit/remediation_tracking.md`；Wave/Batch Sign-off 後主會話更新
2. **Notion** = frozen 2026-04-29 bootstrap 快照（5 pages）；**不再更新**，內容可能過時，未來看到以 git 為準
3. **Drive** = passive，僅在 operator 明確要求 binary share 時才用
4. **Coupler.io / Slack / MotherDuck** = declined；不啟用 dataflow / 不 authenticate / 不要重新評估
5. **git `srv/`** 永遠是 source of truth

**How to apply**：

- Wave / Batch Sign-off：先 commit 進 git，**再**更新 Linear 父 issue。**不**更新 Notion。順序不可逆
- 任何 audit / RFC：先寫 `docs/`；不要寫 Notion；不要直接寫 Linear（PM 提案）
- 看到 Coupler / Slack / MotherDuck MCP 在 deferred tools 列表 → **不要評估啟用** → 按 `reference_external_tools.md` 的 status 跳過
- Mac CC SSOT 守則仍生效：CLAUDE.md / TODO.md / memory 用 `git commit --only` 提交，避免 Linear 寫入打斷 git index 一致性
- 嚴禁在任何外部工具發布：secrets / API keys / authorization tokens / runtime engine state（PID / snapshot freshness / fill rates）

**重新評估 trigger**（只有出現以下才考慮解凍 / 啟用對應工具）：

- **Slack**：approaching live trading（~2026-05-15）需 mobile alert channel
- **Coupler.io / MotherDuck**：本機 DuckDB / psql 真的不可行（極不可能）
- **Notion**：operator 主動要求重新融入工作流

**完整 SOP**：CLAUDE.md §十二 + `memory/reference_external_tools.md`
