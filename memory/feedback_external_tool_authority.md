---
name: 外部工具權威邊界守則
description: Linear / Notion / Coupler / Drive 的 mirror-only 角色；git 永遠是 source of truth
type: feedback
---

**規則**：外部 MCP 工具（Linear / Notion / Coupler.io / Google Drive）在 OpenClaw 工作流中為 *view layer / artifact store / ETL output*，永不擁有交易參數 / 代碼 / 政策的權威。任何衝突一律以 git `srv/` 為準。

**Why:** Operator 2026-04-29 同步加裝 4 個 MCP，立即面臨「這些工具可以決定什麼？」的歧義。若不明訂邊界，會出現:
1. Operator 在 Linear 改 issue 描述 → 與 git 中 `remediation_tracking.md` 漂移
2. Notion 報告比 git 新 → CC session 採信 Notion 而非 git
3. Coupler.io 把 Sheets 數據回灌 PG → 違反 §四 「PG 寫入由 trading_writer 獨家治理」
4. Drive 上的 PDF 比 docs/ markdown 新 → 內部審計兩個版本

**How to apply:**
- 每個 Wave / Batch sign-off：先 commit 進 git，再更新 Linear，再加 Notion 條目（順序不可逆）
- 任何 audit / RFC：先寫 `docs/`，PM accept 後才加 Notion mirror（Notion 不創新內容）
- Coupler.io 永遠 read-only out；發現 dataflow 寫回 PG 立即停
- Drive 永遠 binary-only；發現 markdown 漂移到 Drive 立即清
- Mac CC SSOT 守則仍生效：CLAUDE.md / TODO.md / memory 用 `git commit --only` 提交，避免 Linear / Notion 寫入打斷 git index
- 任何外部工具不發布：secrets / API keys / authorization tokens / runtime engine state（PID / snapshot freshness / fill rates）— 後者屬敏感商業資訊，需 operator 顯式授權才能 share

**完整 SOP**：CLAUDE.md §十二 + Notion [External-Tool Workflow](https://www.notion.so/350dcd3b1eff8122a033d01823988db0)
