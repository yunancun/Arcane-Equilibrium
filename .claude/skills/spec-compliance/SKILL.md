---
name: spec-compliance
description: 對照 22 份 OpenClaw 治理文件做 Gap 分析；提交前/PR 審查/Wave 計劃合規性審查時使用。FA agent 主用。
allowed-tools: Read, Grep, Glob
---

# Spec Compliance（治理規範符合性審計）

> **優先序**：runtime RiskConfig TOML > Rust schema > CLAUDE.md > 治理 .md > memory > 本 skill
> **衝突時向 PM / operator push back，不單方面執行 skill 內 SOP**

> **S3 上層 drift 防線**：本 skill 引用上層（CLAUDE.md / DOC-XX / SM-XX / EX-XX）為 extract；原文修改後可能漂移，發現不一致以原文為準。

## 何時觸發

- FA 收到「審計此修改是否符合治理」「Gap 分析」「DOC-XX 是否被違反」
- 任何接觸 governance / risk / lease / order / audit 路徑的 PR 審查
- 新 Wave/Sprint 計劃啟動前的合規 sign-off
- 接 `/operator/...` 或 `execution_authority` / `execution_state` / `live_execution_allowed` 等硬邊界字段時

## 治理文件權威清單

掃描範圍 `srv/docs/governance_dev/`：
- `SPECIFICATION_REGISTER.md` ← 所有 DOC-XX 的 SSOT（含 Active/Deprecated 狀態）
- `COMPREHENSIVE_SPEC_REQUIREMENTS.md` ← 條文展開
- `DEPRECATED.md` ← 已退役 DOC 黑名單，禁引

DOC-XX 速查（以 SPECIFICATION_REGISTER.md 為準，本表僅快速方向）：
- DOC-01 Core Risk Doctrine（硬止損 §5.9 / position sizing / risk limits）
- DOC-02 Scanning & Monitoring（5-min interval / rate limiting）
- DOC-03 Market Regime Detection
- DOC-04 Agent Learning Evolution（tier advancement criteria）
- DOC-06 Change Audit Log（append-only JSONL）
- DOC-07 Audit Persistence
- DOC-08 Incident Response（§12 9 條安全不變量）
- DOC-09+ ... 詳查 SPECIFICATION_REGISTER.md

對照 `srv/CLAUDE.md` §二（16 條根原則）+ §四（硬邊界）+ §七（代碼/文檔規範）。

## 審計工作流（5 步）

1. **載入 SSOT** — Read `SPECIFICATION_REGISTER.md` + `COMPREHENSIVE_SPEC_REQUIREMENTS.md` + `DEPRECATED.md`。
2. **抽取改動面** — `git diff <base>...HEAD` 列影響檔；map 到對應 DOC-XX（risk path → DOC-01/08，audit path → DOC-06/07，learning path → DOC-04）。
3. **逐條對照** — 每個 DOC 條文標 ✅ 符合 / ⚠️ 部分 / ❌ 違反 / ➖ 不適用，附證據（檔:行）。
4. **硬邊界體檢** — `grep -nE '(execution_state|execution_authority|live_execution_allowed|decision_lease_emitted|max_retries|OPENCLAW_ALLOW_MAINNET)' <diff>` 任一命中升 BLOCKER，要 operator sign-off。
5. **產出報告** — `docs/CCAgentWorkSpace/FA/workspace/reports/YYYY-MM-DD--<topic>_compliance.md`，含：審計範圍 / commit / 逐 DOC 表格 / BLOCKER 清單 / 建議修改文件 / Approve|Conditional|Reject。

## 必驗硬邊界（任一觸碰 = 立即 BLOCKER）

```
execution_state · execution_authority · live_execution_allowed
decision_lease_emitted · max_retries · OPENCLAW_ALLOW_MAINNET
authorization.json HMAC 路徑 · live_reserved global mode
```

加碼：`grep -E '(/home/ncyu|/Users/[^/]+)' <diff>` — 跨平台路徑硬編碼新增 = 違反 §七.★★。

## 反模式（見即標）

- 引用已 DEPRECATED.md 的 DOC（用過期條文當依據）
- 「按 DOC-XX」但無檔:行錨點
- 三引擎獨立驗 paper/demo/live 的條文，只驗 paper 就 PASS
- 跳過硬邊界檢查只看業務邏輯
- 16 根原則中 #3（AI→Lease→複核→執行）/ #7（學習≠改寫 Live）/ #11（P0/P1 內最大自主）混淆

## 輸出格式

```markdown
# FA 合規審計 — <commit-short> · <date>

審計範圍：<files / scope>
基準：commit `<sha>`

## DOC 對照表
| DOC-ID | 標題 | 狀態 | 證據 | 備註 |
|---|---|---|---|---|
| DOC-01 §5.9 | Hard stop-loss | ✅ | risk_engine.py:142 | ATR 倍數合理 |
| DOC-08 §12.3 | Pre-trade replay | ❌ | strategy_X.py:89 | 缺 audit 對象 |

## BLOCKER
（若無寫「無」）

## 16 根原則
評分 N/16，違反編號 + 證據

## 建議
判定：Approve / Conditional / Reject
建議修改：<具體 file:line + 改法>
```
