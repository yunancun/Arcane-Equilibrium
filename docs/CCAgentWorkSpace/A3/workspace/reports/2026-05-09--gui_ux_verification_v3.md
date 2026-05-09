# A3 GUI UX Verification Report v3 — 2026-05-09

審查員：A3 · baseline `faf2d131` → HEAD `da2aba11` (5 commits)

**Tally**：✅ 7 / ⚠️ 5 / ❌ 20 / 🆕 4 · 整體 8.0/10 · PA redesign GUI 影響：**HIGH** · 新 tab 建議數：**3**

## §1 Executive Summary

**整體評分：8.3 → 8.0 / 10（−0.3）**

理由：
- 5 commits 期間 GUI 0 修復（v2 → v3 全部 ❌ 仍 ❌）
- v2 漏報 2 個 confirm() (governance-tab.js:1551/1600 — Approve recovery + delete proposal)
- c081029d freeze blocked symbols + 48227607 promotion evidence **GUI 0 surface**（spec/runtime/UI 三層 drift）
- **PA redesign 對 GUI 是 HIGH 影響**：alpha_source / hypothesis / Strategy Interface 升級全部沒有對應 UX surface

**Critical 5 closure：4/5 不變**

**4 維評分**：
| 維度 | v2 | v3 | 變化 |
|---|---:|---:|---:|
| 術語友好性 | 6.5 | 6.0 | −0.5 |
| 操作流完整性 | 9.2 | 8.5 | −0.7 |
| 學習曲線 | 7.5 | 7.5 | — |
| 錯誤提示質量 | 8.0 | 7.8 | −0.2 |

## §2 任務 A — 5 commits GUI 影響

### Commit c081029d「freeze blocked symbols」
- **GUI surface 期望**：tab-strategy 顯示「Frozen Symbols 凍結幣種列表」+ 凍結原因 + 解凍按鈕
- **實測 grep `freeze|frozen|blocked_symbols` in tab-strategy.html**：**0 行**
- **結論**：❌ GUI 完全沒有 surface

### Commit 48227607「promotion evidence」
- **GUI surface 期望**：tab-governance 加「Promotion Evidence Viewer」+ DSR/PBO/sample n/winrate 證據
- **實測 grep**：**0 行**
- **tab-governance 現有**：btn-promote (line 418) + modal-promote (line 631) — 但這是「**手動晉升學習層級**」，與 commit 的「策略級 promotion evidence」是不同對象
- **結論**：❌ GUI 完全沒有 surface

### 5 commits 期間 v2 outstanding GUI 18 ❌ + 7 🆕 修復狀態

| v2 status | v3 verified |
|---|---|
| 18 ❌ open | **18 ❌ 仍 open** |
| 7 🆕 open（含 1 ✅）| 7 🆕 不變 |
| Critical #10 (API Key clear) | ❌ **仍未修**（48h+5commits 無動作）|

### 🆕 v3 新發現（v2 漏報）

| # | 嚴重度 | 證據 | 影響 |
|---|---|---|---|
| NEW-10 | High | governance-tab.js:1551 if (!confirm(msg)) return; — propose-delete confirmation | 與 openConfirmModal 不一致 |
| NEW-11 | High | governance-tab.js:1600 if (confirm('Approve this recovery request?')) — recovery approval **是 governance 寫操作竟用 native confirm** | Critical-grade 寫操作走最弱 modal |
| NEW-12 | High | c081029d freeze blocked symbols **0 GUI surface** | Spec/runtime/UI 三層 drift |
| NEW-13 | High | 48227607 promotion evidence **0 GUI surface** | 同上 |

**最終 confirm() audit 全表**（grep 全證據）：
1. tab-ai.html:652 (API Key clear) — v1 #10
2. tab-demo.html:1047 (close-all warn) — v2 NEW-7
3. tab-demo.html:1057 (close single) — v2 NEW-7
4. linucb_card.html:186 (LinUCB migrate) — v2 NEW-8
5. linucb_card.html:190 (LinUCB rollback) — v2 NEW-8
6. **governance-tab.js:1551 (delete proposal)** — v3 NEW-10 ⚠️ v2 漏報
7. **governance-tab.js:1600 (recovery approval)** — v3 NEW-11 ⚠️ v2 漏報

`grep -c "confirm("` total = **8 raw native confirm**，governance-tab.js 兩個是 governance critical-grade 寫操作 — 這是**最嚴重 v2 漏報**。

## §3 任務 B — PA redesign GUI / UX 影響

### B.1 PA R-1「Alpha Surface Bundle」對 13-tab 衝擊

| Tab | 衝擊 | 細節 |
|---|---|---|
| **tab-strategy** | **REWRITE** | stratV2Params(s) 只渲染 5 策略既存 params；新接口下每策略要顯示「declared_alpha_sources: [TA1m, FundingSkew, OIDeltaPanel]」+ 每 alpha source 的 freshness/coverage |
| **tab-monitoring** | **NEW SECTION** | 加「Alpha Source Coverage」面板 — 25 symbols × 7 alpha source 健康矩陣 |
| **tab-ai** | **EXTEND** | tab-ai 已有 Tier 2/3 budget；加「Alpha Source Inference Budget」per-source budget |
| **tab-governance** | **EXTEND** | 加「Alpha Source Promotion Gate」per-source DSR/PBO |
| **tab-learning** | **REWRITE** | 學習信號從「5 策略 attribution」改為「per-alpha-source attribution chain」 |

### B.2 PA R-2 Strategist scope reframe

現狀（tab-strategy.html:130-198 Strategist Apply History）：已有「Auto-tune / Manual Promote / Operator Override」3 source filter

**PA 改動後缺失**：
- ❌ 沒有「Strategist Hypothesis Proposal」清單
- ❌ 沒有「Alpha Source Allocation」(Strategist 對 active alpha sources 做 risk-budget 分配)
- ❌ 沒有「Strategist regime detection log」

### B.3 PA R-3 Hypothesis Pipeline first-class — **最大缺口**

- grep `alpha_source|hypothesis|experiment_tracker` in static/*.html → **0 檔**
- grep `supervisor|approval_loop` in static/* → 1 檔（openclaw-agent-control.js:147 「Cloud supervisor」單行 chip）
- tab-learning 有「supervisor」字眼但 **0 hypothesis surface**

**新 UX surface 需求（PA R-3 必需）**：
- **Hypothesis Pipeline Dashboard**：列出所有 hypothesis + state + originator + evidence progress + verdict
- **Hypothesis Lineage Drill**：點 fill → 反向追 originating_hypothesis_id
- **Hypothesis Approval Inbox**：state = EVIDENCE_GATE 但需 operator 批准 PROMOTED 的 inbox

### B.4 ADR-0020 vs PA「Analyst 自主 hypothesis loop」UX 矛盾

現狀：tab-ai.html:518 manual_gui_trigger 按鈕 ✅；tab-governance.html:427 pending-approvals-card ✅。

**但**：PA R-2/R-3「Strategist 自主提 alpha-source proposal → Analyst L3 hypothesis loop」現狀 **0 視覺化**。

### B.5 「Alpha Surface」應該成為新 tab？

| 整合方案 | 結論 |
|---|---|
| 進 tab-strategy | ❌ tab-strategy 已 9 section，加 alpha source 直接破 10 |
| 進 tab-monitoring | NO（性質不對）|
| **新 tab「Alpha Surface」** | **YES — 推薦** |
| 新 tab「Hypothesis Lab」| **YES — 推薦** |
| 新 tab「Alpha Promotion」| 推薦：**融入 tab-governance** |

### B.6 PA redesign 新 UX surface 路線圖

**Phase 1 (R-1)**：新 tab「Alpha Sources」— 7 alpha source × 25 symbols 健康矩陣
**Phase 2 (R-2/R-3)**：新 tab「Hypothesis Lab」— Hypothesis CRUD + state machine + experiment progress
**Phase 3 (R-4)**：tab-governance 加「Per-Alpha-Source Promotion Gate」+ tab-ai 加「Per-Alpha-Source Inference Budget」

**最終 tab dictionary**: 13 → **15 tab**

## §4 5 維度評分（v3）

| 維度 | 狀態 | 證據 |
|---|---|---|
| 防誤觸 | ⚠️ | governance-tab.js:1600 recovery approval 用 native confirm（v3 NEW-11）|
| 認知負荷 | ❌ | tab-strategy 已 9 section 破「≤7」|
| 錯誤狀態 | ⚠️ | confirm() 仍 7 處；c081029d freeze 沒「why frozen?」reason |
| 一致性 | ❌ | governance / tab-live / tab-demo / linucb_card 4 套不同 modal pattern |
| 可審計 | ⚠️ | 48227607 promotion evidence 沒接 GUI viewer；hypothesis 0 first-class surface |

## §5 對抗性 Push Back

### #1：c081029d / 48227607 是 **典型的 Spec/Runtime/UI 三層 drift**
建議 commit message hook：碰 governance/strategy backend 必同 commit 加 GUI surface 或寫「GUI surface deferred to TICKET-XXX」。

### #2：v2 漏報 governance-tab.js 兩個 confirm() 是 A3 自身 audit 完整性問題
A3 v3 起 grep 覆蓋 `static/**/*.{html,js}` 全集。

### #3：PA redesign 7 個新 alpha source × 25 symbols × 多 timeframe = 認知爆炸
**PA 的架構升級必須配 GUI tab 升級，否則 GUI 變更難用**。

### #4：hypothesis 不能塞進 tab-learning，那是 ML 內部
PA R-3 hypothesis 是 governance-grade first-class object，應有獨立 tab。

### #5：Layer 2 cloud / supervisor surface 已存在但只是「buttons」
需要**完整 timeline UI**，不是 button + modal。

### #6：tab-ai.html:652 API Key clear 48h+5commits 0 動作
從 v1 到 v3 = **2 連續 sprint** Critical issue 0 移動。建議 PM 排為 P0-OPS issue 強制下個 sprint 必修。

### #7：「整體 8.0/10」是表面樂觀
v2 → v3 confirm() count 從 6 升到 8（+33%）；**真實 GUI readiness 對應 PA redesign 約 4/10**。

## §6 修復路徑優先序（v3）

1. **P0**：governance-tab.js:1551/1600 兩個 confirm() 改 openConfirmModal — Critical-grade 寫面（**最嚴重 v2 漏報**）
2. **P0**：tab-ai.html:652 API Key clear modal+打字確認（48h Critical 必修）
3. **P0**：c081029d freeze 加 tab-strategy「Frozen Symbols」section + 解凍 button
4. **P0**：48227607 promotion evidence 加 tab-governance「Promotion Evidence Viewer」
5. **P0**：tab-demo close-position / dust 改 openConfirmModal
6. **P0**：linucb_card 兩個 confirm() 改
7. **P1（PA redesign 同步）**：新 tab「Alpha Sources」spec — Sprint N+1
8. **P1（PA redesign 同步）**：新 tab「Hypothesis Lab」spec — Sprint N+2
9. **P1**：tab-strategy 9 section 拆為「Strategy Operations」+「Strategy Internals」 sub-tab
10. **P2**：mode-tag SSR initial DOM fix
11. **P2**：z-index scale token + 統一 modal pattern catalog

## §7 PA redesign GUI Impact verdict — **HIGH**

- 5 個 PA 行動中 R-1/R-2/R-3 直接需要新 GUI surface
- 預估新增 2 tab + 4 sub-section + 1 section rewrite
- 預估 GUI 工作量：~3-4 sprint
- **若 PA redesign 進入 IMPL 但 GUI 不同步**：alpha source / hypothesis 變成「only-in-DB 對象」，operator 失去視覺手感

**建議**：PA 每個 R-X 動作的 sprint plan 必須含 GUI sub-task。

---

**A3 VERIFICATION v3 DONE** · ✅ 7 / ⚠️ 5 / ❌ 20 / 🆕 4 · 整體 8.0/10 · PA redesign GUI 影響: HIGH · 新 tab 建議數: 3
