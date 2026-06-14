# 全盤冷酷審計 — Stage 0 Baseline Freeze

**AUDIT_DATE**: 2026-06-14
**Conductor**: 主會話 (PM + Conductor)
**模式**: ultracode 已啟用（operator 本輪輸入含 ultracode）→ 五階段全鏈執行
**Active model**: Opus 4.8 (1M context) — 頂級模型，編排與收斂由主迴圈直接承擔
**審計類型**: 工程質量冷酷對抗審計（openclaw-full-audit，找問題：bug/合規/安全；對偶 profit-diagnosis 已於 2026-06-13 跑過）

---

## 1. 三端 Git SHA（凍結錨）

| 端 | SHA | branch | 狀態 |
|---|---|---|---|
| Mac (dev) `~/Projects/TradeBot/srv` | `976d420e9a868b0fe4600e1c613bd127a347b654` | main | HEAD |
| origin/main | `976d420e9a868b0fe4600e1c613bd127a347b654` | main | 同步 |
| Linux runtime `trade-core:~/BybitOpenClaw/srv` | `976d420e9a868b0fe4600e1c613bd127a347b654` | main | 同步 |

**三端完全同步**：Mac HEAD = origin/main = Linux runtime，0/0 ahead-behind。
最近提交：`976d420e chore(v58): add pause readiness handoff [skip ci]`

---

## 2. Dirty worktree 快照（審計可信度關鍵）

### Mac dirty = 20 項
**已追蹤代碼改動（8 檔，與 Linux 完全相同）— ⚠️ load-bearing：**
```
 M helper_scripts/m4/sources/fills_loader.py
 M helper_scripts/m4/tests/test_source_loader_schema.py
 M program_code/exchange_connectors/bybit_connector/control_api_v1/app/closed_pnl_pagination.py
 M program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/tab-demo.html
 M program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/tab-live.js
 M program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_bybit_closed_pnl_route.py
 M program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_closed_pnl_pagination.py
 M program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_live_closed_pnl_route.py
```
**docs/memory 改動（未追蹤報告 + 既有 memory 修改）：**
```
 M docs/CCAgentWorkSpace/{AI-E,BB,MIT,PA}/memory.md
 M memory/MEMORY.md
?? docs/CCAgentWorkSpace/AI-E/workspace/reports/2026-06-13--AI-E--ai_cost_profit_evidence.md
?? docs/CCAgentWorkSpace/AI-E/workspace/reports/2026-06-13--AI-E--profit_research_守攻.md
?? docs/CCAgentWorkSpace/Operator/2026-06-13--PA--profit_opportunity_map_roi.md
?? docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-13--PA--profit_opportunity_map_roi.md
?? docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-13--profit-diagnosis-FINAL-adjudication.md
?? docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-13--profit-diagnosis-stage0-freeze.md
?? memory/project_2026_06_13_profit_diagnosis_searchspace_reconfirm.md
```

### Linux dirty = 8 項
**= Mac 的 8 個代碼檔完全相同**（closed_pnl_pagination 功能 + m4 fills_loader，三端碼層一致的 in-flight 工作）。

> **⚠️ 審計紀律**：上述 8 個代碼檔在 Mac/Linux 皆 dirty（未提交於 `976d420e`）。任一 finding 若 affected line 落在這 8 檔，**所指為 working-tree 未提交狀態**，非凍結 SHA。各軸讀的是磁碟工作樹（disk working tree），因此會看到這些未提交改動——finding 須據實標明「working-tree (uncommitted)」。

---

## 3. E4 測試基線錨（回歸對照）

**BASELINE: 2026-06-11 passed=4728 failed=66**
- scope = `control_api_v1/tests --ignore=replay`，Mac mac_dev CSRF-enforcement lane
- Linux 系統 python 同套 4730/66
- Rust Linux 4665/0
- branch feat/l2-p4-integration @ ddaafda1（已 merge 入 main）
- **66 failed 全為 pre-existing CSRF env-lane**（FAILED 名單與 4618 基線 byte-identical），非回歸——審計若見此 66 失敗，屬已知環境 lane 差異，不計入新缺陷。
- 本批新套件 SCOPED-BASELINE（mac_dev lane）：learning_engine=543/0/0/0；canary 全目錄=427+9subtests；research=266/0/1s/0；cron=139；memory=39；db-l2+v140=36；hc 鄰接=164。

---

## 4. Active SoT 清單

- **代碼/治理 SSOT**: `srv/` git @ `976d420e`
- **Active 狀態權威**: `TODO.md` v160（2026-06-13）— 主線 P0-EDGE-1 Alpha-Edge 體制證據治理；V5.8 13 模組 active-IMPL 凍結中
- **不變量**: CLAUDE.md §二（16 root principles）+ §四（5-gate live boundary + hard boundaries）
- **域詞彙**: CONTEXT.md / docs/adr/*
- **角色基準**: `.claude/agents/*.md` + skills（16-root-principles / owasp / spec-compliance / ...）
- **runtime 現實**: Linux engine rebuild+restart 2026-06-07（main d5ec22d5 基底）；2026-06-13 V138/V139/V140 + L2 cron + embedding backfill activation；engine PID 3607315 alive；P5-SM 48h soak PASS 2026-06-13；sqlx head=139；agent_memory rows=99/embedding dims=1024

---

## 5. 本輪審計範圍與規則

- **scope**: srv/ 全倉（工作樹現狀，含上述 8 dirty 代碼檔）
- **runtime 納入**: 是（MIT/AI-E 可經 `ssh trade-core` read-only 取 runtime/DB 證據）
- **允許 ssh 範圍**: read-only only（git status/rev-parse、psql SELECT/healthcheck、ls/cat 證據檔）；**禁** deploy/rebuild/restart/migration apply/任何 mutation
- **本輪禁止事項**: 預設 report-only（`fix=false`）；不 commit/push；不改業務碼；不動 V5.8 凍結；不解凍任何 active-IMPL；不碰 8 dirty 檔
- **報告命名**: `{AUDIT_DATE}--cold_audit_<phase>.md`，置 PM/PA workspace reports（遵 CLAUDE docs 放置規則，不放 repo 根目錄）

---

## 6. 移交 Stage 2

baseline 摘要將以 `args.baseline` 注入 workflow `openclaw-full-audit`，對齊每軸 affected-line 至凍結 SHA `976d420e`，並警示 8 dirty 代碼檔為 working-tree 狀態。

12 軸：CC / FA / E3 / BB / QC / MIT / AI-E / E4 / E5 / A3 / R4 / TW（全鏈深審）
focus：按軸靶向注入（authority chain / 5-gate 可繞性 / tunable-vs-hardcoded / migration-vs-DB / AI truthfulness / GUI fake-success / 測試盲區 / 代碼級死代碼），non-範圍上限。
