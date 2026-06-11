---
name: spec-compliance
description: FA agent 主用：治理符合性審計、DOC-XX Gap 分析、Wave/Sprint 計劃合規 sign-off、或 PR 觸及 governance/risk/lease/order/audit 路徑與硬邊界字段時必讀。
allowed-tools: Read, Grep, Glob
---

# Spec Compliance（治理規範符合性審計）

> 權威序：runtime RiskConfig TOML > Rust schema > `srv/TODO.md` > 治理文件（`SPECIFICATION_REGISTER.md` 索引）> 本 skill。衝突按權威序執行並在報告標註，不停下等待。
> 即時狀態（策略名單/閾值/端點/baseline 等）以上述 SSOT 為準，本 skill 不寫死。

## 何時觸發

- FA 收到「審計此修改是否符合治理」「Gap 分析」「DOC-XX 是否被違反」
- 任何接觸 governance / risk / lease / order / audit 路徑的 PR 審查
- 新 Wave/Sprint 計劃啟動前的合規 sign-off
- 接 `/operator/...` 或 `execution_authority` / `execution_state` / `live_execution_allowed` 等硬邊界字段時

## 治理文件權威清單

> 治理文件數量 / 清單以 `SPECIFICATION_REGISTER.md` Active 條目為準（operator 多次修訂，本 skill 不寫死數量）；衝突 = 信 register 並在報告標註。

掃描範圍兩處：
- `srv/docs/governance_dev/` — 索引層：
  - `SPECIFICATION_REGISTER.md` ← 所有 DOC-XX 的 SSOT（含 Active/Deprecated 狀態）
  - `COMPREHENSIVE_SPEC_REQUIREMENTS.md` ← 條文展開
  - `DEPRECATED.md` ← 已退役 DOC 黑名單，禁引
- `srv/docs/decisions/` — 正文層：DOC / SM / EX / HIST 系列 `.docx`（operator 維護源）+ `.md`（轉檔給 sub-agent 讀）。`.docx` 位置與清單以 `SPECIFICATION_REGISTER.md` 索引為準。

### .docx → .md 同步 SOP

治理文件為 `.docx`（operator 維護源）+ `.md`（已轉檔給 sub-agent 讀）。**若 operator 修改 .docx 後**：
1. 觸發人工執行 `helper_scripts/maintenance_scripts/governance_docx_to_md.py`（或等價腳本）重轉
2. 比對前後 `.md` 差異，逐條標漂移點
3. 更新 `SPECIFICATION_REGISTER.md` 若有新增 / 撤回 / 重編號
4. 通知所有引 DOC-XX 的 skill / TODO 條目重 audit

未做 step 1 = sub-agent 讀的 `.md` 與 operator 真實意圖漂移。未來可考慮 git pre-commit hook（commit `.docx` 時自動 re-render `.md`）。

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
4. **硬邊界體檢** — 指紋 regex 以 `16-root-principles-checklist` 為唯一正本；用 Grep 工具（pattern=正本 regex，path=改動範圍）執行，有 Bash 環境可等價用 `grep -nE` 掃 diff。任一命中升 BLOCKER，要 operator sign-off。
5. **產出報告** — 寫入執行 agent 自身 workspace 報告目錄：`docs/CCAgentWorkSpace/<agent>/workspace/reports/YYYY-MM-DD--<topic>_compliance.md`，含：審計範圍 / commit / 逐 DOC 表格 / BLOCKER 清單 / 建議修改文件 / Approve|Conditional|Reject。

## 必驗硬邊界（任一觸碰 = 立即 BLOCKER）

硬邊界字段清單與指紋 regex：見 `16-root-principles-checklist`（唯一正本）。

加碼：跨平台路徑硬編碼檢查 — 用 Grep 工具（pattern=`(/home/ncyu|/Users/[^/]+)`，path=改動範圍）執行；新增命中 = 違反 `CLAUDE.md` §七.★★。

## 反模式（見即標）

- 引用已 DEPRECATED.md 的 DOC（用過期條文當依據）
- 「按 DOC-XX」但無檔:行錨點
- 三引擎獨立驗 paper/demo/live 的條文，只驗 paper 就 PASS
- 跳過硬邊界檢查只看業務邏輯
- 16 根原則中 #3（AI→Lease→複核→執行）/ #7（學習≠改寫 Live）/ #11（P0/P1 內最大自主）混淆

## 輸出格式

```markdown
# <agent> 合規審計 — <commit-short> · <date>

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
