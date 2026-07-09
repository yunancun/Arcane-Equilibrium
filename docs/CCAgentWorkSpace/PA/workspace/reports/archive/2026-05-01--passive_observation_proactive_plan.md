# PA Report — Passive Observation Proactive Plan + TODO Archive Audit

**Date**: 2026-05-01  
**Author**: PA (Project Architect)  
**Scope**: 21-day passive observation window (2026-05-01 → 2026-05-22) — TODO v4 archive integrity audit + Wave 4 Pre-Stage proactive task plan  
**Trigger**: Operator 質疑 PM 從 TODO v3 (713 行) → v4 (197 行) 過程：(a) 砍掉內容是否全為已完成 (b) passive observation 期間沒真正規劃可主動推進的工作  
**Inputs read**:
- `srv/TODO.md` (v4, 197 lines)
- `srv/docs/archive/2026-05-01--completed_waves_1_2_3_and_backlog.md` (329 lines — completed archive)
- `srv/docs/archive/2026-04-30--TODO-pre-cleanup-snapshot.md` (713 lines — full v3 snapshot)
- `srv/CLAUDE.md` §三/§四/§八/§十/§十二

---

## Executive Summary

**5 lines**:
1. 規劃 **34 個任務**，分 5 軸線；共估 **~28-35 PA/E1 工作日**（含並行壓縮可在 21d 內完成 ~70%）。
2. 關鍵 unblock：**Wave 4 LG-2/3/4/5 PA RFC** 必須 P0-3 (~05-15) 之前寫好，否則 outcome A/C 啟動時又要等 RFC 設計（多 3-5d 阻塞）。
3. 立即可派發、不等 P0-3 的工作有 **11 項**，多數獨立並行。
4. TODO 歸檔審計：v4 確實漏了 6 條 active 條目（operator 已知）+ 額外發現 3 條（**G7-04 CUSUM Phase B/C wiring**、**G7-01 Kelly router wiring deferred**、**4-06/MLDE-2 已完成但 v4 未明標**）；建議 6+3 條補回 TODO，2 條維持歸檔。
5. 風險：LG-2/3/4/5 PA RFC 若 P0-3 outcome B (edge 仍負)，**部分 RFC 內容作廢但保留作為 dead-code-prevention 學習材料**；風險可控。

---

## Section A — TODO 歸檔完整性審計

### A.1 Operator 已找到的 6 條（驗證 + 補救建議）

| # | 條目 | v3 位置 | v4 狀態 | 仍 active? | 建議處置 |
|---|------|--------|---------|-----------|---------|
| 1 | **EDGE-P2 Phase B**（Liquidation signal P3，前置 OI 驗收已完）| L532 backlog | 消失 | ✅ Active（OI 驗收 2026-04-20 已完，等資源派發）| **補回 TODO Backlog** P3 |
| 2 | **EDGE-P2-3 Phase 2+**（live endpoint / funding_arb PostOnly P3）| L533 backlog | 消失 | ✅ Active（前置 Phase 1b ~05-10）| **補回 TODO Backlog** P3，依賴 EDGE-P1b |
| 3 | **G4-05**（ExitConfig.shadow_enabled flip + 24h 觀察 P2）| 隱含於 EDGE-P2-flip 但 ID 不同 | 消失 | 🟡 部分重疊 EDGE-P2-flip | **不補**：與 EDGE-P2-flip 等價（後者 v4 仍在），G4-05 為 PA 視角的 architectural framing；確認交付 = EDGE-P2-flip 即可 |
| 4 | **依賴關係圖**（Wave 1→2→3→4 ASCII）| L146-160 | 消失 | ⚠️ 仍 useful 但已過時（Wave 1-3 已完）| **補回**：簡化 Wave 4 依賴圖（只畫 P0-3 → LG-2/3/4/5 + MLDE-6）|
| 5 | **Wave 時序表**（W17-W24 週次）| L199-205 | 消失 | ⚠️ 仍 useful（providing strategic horizon）| **補回**：壓縮為 Wave 4 timing only（W21-W24 + Live target） |
| 6 | **EDGE-DIAG-2 留尾被動**（PostOnly maker fill rate / bb_breakout 1m bandwidth）| L69 「此刻該做什麼」尾段 | 消失 | ✅ Active 觀察項 | **補回 TODO**：合併進 v4 §「Active Observation Gates」備註欄 |

### A.2 PA 額外發現（v4 未列出但 v3 在的 active 條目）

| # | 條目 | v3 位置 | v4 狀態 | 仍 active? | 建議處置 |
|---|------|--------|---------|-----------|---------|
| 7 | **G7-04 Phase B/C wiring**（CUSUM consumer hook）| L526「Phase A schema landed」隱含；archive L146「Phase A ✅」明寫 | v4 backlog 缺 | ✅ Active（schema landed，consumer hook 待）| **補回 TODO Backlog** P2 deferred；條件「G4 labels 累積 + EDGE-P1b 驗收後」|
| 8 | **G7-01 Kelly router wiring (callsites)**（surface ready，等 G4 labels work）| v3 backlog 隱含 | v4 backlog L110 "G7-01 wiring" 在 ✅ | 已在 v4 | **無需補**（PM 已留下） |
| 9 | **STRATEGIST-AUTO-PROMOTE**（自動晉升規則 P2-01 後）| L525 backlog | 消失 | 🟡 Long-term P3（未阻塞）| **補回 TODO Backlog** P3，標 deferred-long-term |
| 10 | **STRK-FUP-HEALTHCHECK-PRE-EXISTING**（5 pre-existing pipeline FAIL 觀察）| L624 backlog | 消失 | ✅ Active（PA Wave 4 / G3-08+ scope 觀察項，非阻塞）| **補回 TODO Backlog** P2，條件「F7 deploy 後 6-12h 觀察期完成」實際已滿足，可派 PA design |
| 11 | **ORPHAN-ADOPT-1 Phase 2B**（Strategist would_take 終仲裁）| L536 backlog | 消失 | 🟡 P3 conditional（前置 G-1 R-02）| **補回 TODO Backlog** P3 |
| 12 | **IP-DEDUP-1**（IntentProcessor 去抖 P4 conditional）| L537 backlog | 消失 | 🟡 P4 conditional（觸發條件 P0-3 後 edge 仍負 + 高重發率）| **補回 TODO Backlog** P4，與 P0-3 outcome B 綁定 |
| 13 | **G-2 FundingArb 重評**（三參數重評 R-02 Strategist 在線）| L535 backlog | v4 backlog L123 在 ✅ | 已在 v4 | **無需補** |
| 14 | **G-7 ClaudeTeacher 啟用**（21d demo + G-3 後）| L548 backlog | 消失 | 🟡 P2-P3（21d 解鎖 ~05-07）| **補回 TODO Backlog** P2-P3，21d 解鎖後重評 |
| 15 | **G-10 Calibration.py isotonic**（ECE < 0.05）| L549 backlog | v4 L119 G-10 在 ✅ | 部分在 v4 | 確認 v4 「G-6/G-7/G-8/G-10」聚合行覆蓋此項，可不單獨補 |
| 16 | **TIER4-MIT-AUDIT-GREP-SNIPPET**（下次 audit 嚴謹度）| L617 backlog | v4 L116 在 ✅ | 已在 v4 | **無需補** |

### A.3 v4 確實已完成保留在 archive 的（驗證 ✓）

archive `2026-05-01--completed_waves_1_2_3_and_backlog.md` 涵蓋：
- Wave 1 G1-01~06 + G6-01~05 ✓
- Wave 2 G3-01~11 + G3-08-Phase 1A~4 + G4-01~03 + G5-01~09 + G7-01~09c ✓
- Wave 3 W1~W5 + Sign-off + G2-02/05/06 + G8-01/02 + G9-01~05 + EDGE-P1b/P2-flip/P1b-FUP-* + Observer cleanup ✓
- Backlog 完成項 60+ 條 ~~struck-through~~ ✓
- MLDE-0~5 ✓

**結論**：archive 完整性 OK，**漏掉的全是 active 條目**（v3 backlog 表中沒打 ~~strikethrough~~ 的條目被 PM 同時砍掉）。共 **9 條真正漏 active**（含 operator 6 條 + PA 新發現 3 條：#7/#9/#10/#11/#12/#14）。

### A.4 v4 多寫 / 誤留檢查

掃 v4 全文，**沒發現誤留已完成項**。v4 backlog 表 23 行皆為 active 或 conditional 觸發未到。**OK**。

### A.5 結論

- **歸檔內容無誤**（已完成項全在 archive）
- **active 條目 v4 漏 9 條** — 詳列於 §A.1+A.2，建議補回 TODO Backlog 表
- **架構性內容（依賴圖/時序表）漏 2 個** — 建議補簡化版

---

## Section B — Wave 4 Pre-Stage 工作計畫（5 軸線）

### B.1 軸線 1：Wave 4 LG-2/3/4/5 PA Design（最重要 · 必須 P0-3 前完成）

**戰略意義**：P0-3 (~05-15) 若 outcome A/C，LG-2/3/4/5 立即啟動。**現在不寫 RFC 等到 05-15 後再寫 = 浪費 3-5d 阻塞**。即使 outcome B (edge 仍負)，RFC 仍是 dead-code-prevention 的學習材料 + 未來重啟時免重做。

| ID | RFC 任務 | PA RFC 工時 | E1 impl 工時 | E2/E4 review 強度 | 前置依賴 | 完成 gate |
|----|---------|------------|--------------|------------------|---------|----------|
| **LG-2-RFC** | H0 Gate blocking verification（shadow→blocking）— acceptance criteria / test plan / rollback / metrics | 1.5d | 1d | 中（P0 路徑必驗）| P0-3 outcome A/C；DOC-08 §12 安全不變量 9 條 | RFC `2026-05-XX--lg2_h0_blocking_rfc.md` 含：(1) shadow→blocking flip SOP (2) 5 個 metrics threshold（block_rate / false_positive / latency / lease consumption / fail-closed verify count）(3) rollback path（IPC `set_h0_mode=shadow`）(4) E2E test plan 含 mock blocked intent (5) 16 根原則對照 |
| **LG-3-RFC** | Provider pricing table 正式綁定 — 對照 `bybit_api_reference.md` 寫 binding spec | 1d | 0.5d | 低（純 config binding）| `docs/references/2026-04-04--bybit_api_reference.md`；`G7-07 SlippageConfig` ✅ 已完 | RFC 含：(1) Bybit V5 fee tier table mapping（taker/maker per category）(2) instrument_info IPC pull period 與 stale handling (3) fail-closed when stale > N min (4) test：assert pricing != None at startup |
| **LG-4-RFC** | M 章 Supervised Live Gate — operator approval flow / risk limits / kill switch | 2d | 1.5d | 高（涉 §四 硬邊界）| LG-2-RFC + LG-3-RFC | RFC 含：(1) operator approval RPC schema (2) per-symbol & total daily risk limit override flow (3) kill switch（API + IPC dual path）(4) authorization.json renew tie-in (5) audit log schema 鏡 SM-04 (6) 16 根原則 #1/#2/#5/#9/#11 對照 |
| **LG-5-RFC** | N 章 Constrained Autonomous Live — agent autonomy boundaries / escalation triggers | 2d | 1d | 高（agent autonomy 是 §四 硬邊界邊緣）| LG-4-RFC | RFC 含：(1) 自主邊界 spec：strategy switch / param adjust 範圍 / position size cap (2) escalation trigger（drawdown / agree_rate drop / cost_edge_ratio spike）(3) 自主動作 lease TTL（短於 supervised）(4) 16 根原則 #11 + 衍生「認知調製 ≠ 能力限制」對照 |
| **MLDE-6-RFC** | Live promotion contract design（advisory→proposal→demo patch→live candidate）| 1d | 1.5d | 高（live + autonomy 雙風險）| MLDE-5 ✅ 完成；GovernanceHub spec | RFC 含：(1) advisory→proposal schema 升級（含 confidence / window / counterfactual）(2) operator review UI requirements (3) demo patch → live candidate gate sequence (4) rollback path (5) 16 根原則 #3/#7/#11 對照 |

**軸線 1 總計**：PA 7.5d / E1 5.5d。PA 可在 21d window 內並行完成（1 PA agent 處理）。

### B.2 軸線 2：條件性可獨立進行的工作（不需等 P0-3）

| ID | 任務 | 派工路徑 | ETA | 阻塞? | 完成標準 |
|----|-----|---------|-----|-------|---------|
| **G4-03 Phase B** | Canary auto-promote 部署 — cron driver / Brier / PSI drift / SIGHUP；DEFAULT-OFF env-gated 已完，需部署 + 觀察 | PA design 0.5d → E1 1.5d → E2/E4 0.5d | 3d 工作量 | ❌ 獨立 | cron 跑 7d，0 false promote；PSI drift 偵測一次 |
| **G7-04 Phase B/C wiring** | CUSUM consumer hook（schema landed Phase A，consumer 待）| PA RFC 0.5d → E1 1d → E2 0.5d | 2d | ❌ 獨立（前置 Phase A ✅）| Hurst-CUSUM regime detector 在 strategy_orchestrator 接線；6 unit tests |
| **G8-05 AI cost ROI 監控面板** | GUI work，獨立；G3-09 已完成 cost_edge_advisor 為依賴源 | E1 1.5d（純 GUI）→ E2 0.5d | 2d | ❌ 獨立 | tab-strategy.html 加 ROI panel；後端 endpoint 從 `learning.cost_edge_advisor_log` aggregate |
| **MLDE-6 PA design**（同軸線 1）| 已列軸線 1 | — | — | — | — |
| **LEARNING-COCKPIT-NO-IPC** | Learning 8 端點走 Python state_store（避 IPC 過載）| PA design 0.5d → E1 2d → E2/E4 0.5d | 3d | ❌ 獨立 | 8 endpoint 改 read state_store；IPC traffic drop ≥80%（可量測） |
| **STRK-FUP-HEALTHCHECK-PRE-EXISTING** | 5 pre-existing pipeline FAIL silent-dead 修復（[3]/[19]/[23]/[24]/[26]/[27]）| PA RFC 1d → E1 2-3d/pipeline → E2/E4 0.5d ea | 拆 5 子任務，可並行 ≤3 | ❌ 獨立但容量大 | 各 healthcheck 連 3d PASS；commit msg + .claude_report |
| **G3-08-FUP-ANALYST-SPLIT** P2 | analyst_agent.py 874 行 → <800（鏡 Strategist split pattern）| E1 1d → E2 0.5d | 1.5d | ❌ 獨立 | <800 行 + targeted pytest 全綠 |
| **G3-08-FUP-HSQ-SPLIT** P2 | h_state_query_handler.py >800 → <800（拆 collectors sibling）| E1 1d → E2 0.5d | 1.5d | ❌ 獨立 | <800 + 36 pytest 全綠 |
| **G3-08-FUP-MAF-SPLIT-CLEANUP-A** P4 | bottom-of-file eager re-export 替代 PEP 562（cosmetic） | E1 0.5d → E2 0.25d | 0.75d | ❌ 獨立 | 雙語 docstring drift 修；scout_agent.py SCOUT_AGENT singleton 表登記 |
| **SINGLETON-POLLUTION-PHASE2-ROUTES** P4 (Mac-only) | Mac dev session pollution cleanup | E1 1d → E2 0.5d | 1.5d | ❌ 獨立 | Mac pytest singleton race 0 |
| **G5-09-FUP-TYPO** P3 | commit msg `a5b6f17` test count typo | TW 5min | 0.1d | ❌ 獨立 | next commit cycle 修 |

**軸線 2 總計**：~17.5d 工作量；最大並行壓縮後 ~7d 完成（4 並行）。

### B.3 軸線 3：Pre-Live 基礎設施（CLAUDE.md §十二 ~05-15 Slack 評估點）

| ID | 任務 | 派工路徑 | ETA | 前置 | 完成標準 |
|----|-----|---------|-----|------|---------|
| **PRE-LIVE-1 Slack alert decision** | Live 前 2w 評估純 alert channel；決策 framework：alert routing rules / mobile notification / authentication scope | PM+PA 0.5d 評估 + spec → operator 決策 | 0.5d + 待 operator | 2026-05-15 ±3d 評估點 | 決策文件 `docs/decisions/2026-05-XX--slack_alert_decision.md`（go/no-go 含理由）|
| **PRE-LIVE-2 HTTPS deploy** | 解 G-4 Cookie secure=True 阻塞；需 Tailscale cert / Let's Encrypt 選擇；nginx config | PA design 1d → E1 1.5d → E2 0.5d | 3d | Tailscale cert 可用性 | HTTPS endpoint 通；G-4 cookie secure=True 部署成功 |
| **PRE-LIVE-3 Dashboard 強化** | [33]/[38]/[40] 趨勢可視化 + AI cost ROI + Live readiness checklist | E1 2d 純 GUI → E2 0.5d | 2.5d | G8-05 已完（軸線 2）| Dashboard 加 3 chart + 1 readiness checklist；operator 審核 PASS |
| **PRE-LIVE-4 災難恢復演練** | Pre-live tabletop 模擬 P0/P1 gate 觸發 — drawdown auto-revoke / liquidation buffer / authorization expire | PA design 0.5d → operator 演練 1d | 1.5d | LG-2 RFC（軸線 1）| 演練報告 `.claude_reports/YYYYMMDD_disaster_recovery_drill.md`；3 scenario 全 PASS |

**軸線 3 總計**：~7.5d 工作量；可在 W21-W22 並行進行。

### B.4 軸線 4：P0-3 決策會準備（~05-15）

| ID | 任務 | 派工路徑 | ETA | 完成標準 |
|----|-----|---------|-----|---------|
| **P03-PREP-1 Edge decision protocol** | decision criteria / evidence templates / 三分支執行路徑 framework 文件 | PM+PA 1d → FA review 0.5d | 1.5d | `docs/decisions/2026-05-15--p0_3_edge_decision_protocol.md` |
| **P03-PREP-2 P0-3-01 報告 outline** | counterfactual_exit_replay 完整分析報告 outline；資料未到先寫骨架 | MIT 0.5d outline → 等資料填充 | 0.5d outline + ~05-13 填充 | outline 含 12 章節 + 6 hypothesis 預設 |
| **P03-PREP-3 各 agent pre-meeting briefs** | PM/FA/PA/QC pre-meeting brief（各自視角的 evidence + 立場）| 4 agent 各 0.5d | 0.5d × 4 = 2d 並行 | 4 brief 在 `docs/CCAgentWorkSpace/<NAME>/workspace/reports/2026-05-14--p0_3_pre_meeting_brief.md` |
| **P03-PREP-4 Adversarial review playbook** | 模擬決策會 adversarial round（FA challenge PM、QC challenge FA）| PM+PA 0.5d | 0.5d | playbook 含 5 round prompt template |

**軸線 4 總計**：~4.5d 工作量；W21-W22 鋪設，~05-13/14 收尾。

### B.5 軸線 5：Documentation / Test / Maintenance

| ID | 任務 | 派工路徑 | ETA | 完成標準 |
|----|-----|---------|-----|---------|
| **DOC-1 Live trading first-day SOP** | 第一天 live 起航 runbook：order check / position monitoring / kill switch / escalation | TW 1d → PM review 0.5d | 1.5d | `docs/runbooks/2026-05-XX--live_first_day_sop.md` |
| **DOC-2 Wave 4 deploy runbook** | LG-2/3/4/5 部署順序 + 回滾路徑 | TW 0.5d → PA review 0.5d | 1d | `docs/runbooks/2026-05-XX--wave4_deploy.md` |
| **TEST-1 E2E live gate tests** | 對 mock Bybit mainnet 跑 LG-2/3/4/5 e2e；驗 5 hard gate 全綠 | E4 2d | 2d | mock test suite ≥10 cases；CI 通過 |
| **MAINT-1 G3-08-FUP-MAF-SPLIT-CLEANUP-A** P4 | （同軸線 2）| — | — | — |
| **MAINT-2 SINGLETON-POLLUTION-PHASE2-ROUTES** P4 | （同軸線 2）| — | — | — |
| **MAINT-3 TIER4-MIT-AUDIT-GREP-SNIPPET** P3 | 下次 MIT audit 補嚴謹度 | MIT 0.5h | 0.1d | next audit cycle 補 |

**軸線 5 總計**：~4.5d 工作量。

### B.6 Gantt / 時序壓縮

```
              W21          W22          W23          W24
              05-01→05-08  05-08→05-15  05-15→05-22  05-22+
              ─────────────────────────────────────────────
軸線 1 (PA)   LG-2 RFC─→LG-3─→LG-4─→LG-5─→MLDE-6
軸線 2 (E1×3) G4-03B  G7-04  G8-05  L-COCKPIT  STRK-PRE  
              SPLITS (Analyst/HSQ/MAF)
軸線 3        Slack-eval(05-15) | HTTPS | Dashboard | Drill
軸線 4 (PM+)        Protocol─→Briefs─→ P0-3 (~05-15)
軸線 5 (TW+E4)              SOP / runbook / E2E tests
              ─────────────────────────────────────────────
時間里程碑    05-03 G2-02   05-07/08 G2-01    05-15 P0-3   05-22+ Wave 4 launch
              05-10 EDGE-P1b
```

**並行壓縮**：合理調度下，軸線 1+2 大部分可在 W21-W22 完成；軸線 3+4 在 W22-W23 完成；軸線 5 在 W23 完成。21d window 可消化 ~70% 工作量。

---

## Section C — 派發優先序（Top 10 立即可派發）

按 **impact × ROI × blocker chain** 排序：

| Rank | 任務 | 派發 agent | 工時 | 為何優先 |
|------|------|-----------|------|---------|
| 1 | **LG-2-RFC** H0 blocking verification | PA | 1.5d | P0-3 outcome A/C 立即解阻；不寫等於 05-15 後阻塞 3-5d |
| 2 | **MLDE-6-RFC** Live promotion contract | PA | 1d | live autonomy 邊界，與 LG-4/5 雙耦合；先寫可避 LG-4 RFC scope creep |
| 3 | **LG-3-RFC** Provider pricing | PA | 1d | 純 config binding；low-risk；解 LG-4/5 前置 |
| 4 | **STRK-FUP-HEALTHCHECK-PRE-EXISTING** [3]/[24] 修復（可獨立 2 子任務）| PA design + E1×2 並行 | 2-3d | 5 個 silent-dead 修復是 audit 信任度問題；現時 cron 已能偵測 |
| 5 | **G7-04 Phase B/C wiring** CUSUM consumer | PA RFC + E1 | 2d | Phase A schema landed 已 5d；不接 wiring 等於 dead schema |
| 6 | **G4-03 Phase B** canary auto-promote 部署 | PA + E1 + E2/E4 | 3d | ML pipeline canary 是 Wave 4 LG 前提；現在跑 7d 才能在 P0-3 提供 PSI drift 數據 |
| 7 | **LG-4-RFC** Supervised Live Gate | PA | 2d | 涉 §四 硬邊界；風險最高，最需要 RFC 早寫 + adversarial review |
| 8 | **G8-05** AI cost ROI 監控面板 | E1 純 GUI | 2d | operator 訊息密度提升；可配合 P0-3 決策會用 |
| 9 | **PRE-LIVE-2** HTTPS deploy | PA + E1 | 3d | 解 G-4 阻塞；live trade 前必須完成 |
| 10 | **LG-5-RFC** Constrained Autonomous Live | PA | 2d | 等 LG-2/3/4 RFC 落地後寫；W22 中段派發 |

**派發節奏建議**：
- **W21 D1-D3** (~05-01~05-03)：併發派 Rank 1+2+3+4（PA × 1 + E1 × 1）
- **W21 D4-D7** (~05-04~05-07)：Rank 5+6+8（PA × 1 + E1 × 2 並行）
- **W22 D1-D5** (~05-08~05-12)：Rank 7+9+10（PA × 1 + E1 × 1）
- **W22 D6-W23** (~05-13~05-19)：軸線 4 P0-3 prep + 軸線 5 docs + e2e tests

---

## Section D — TODO.md 修補建議（具體 patch）

### D.1 Backlog 表補回 9 行（建議 patch position：v4 line 124 之前）

```markdown
| **EDGE-P2 Phase B** | Liquidation signal P3（前置 OI 驗收已完）| Phase A OI 驗收後 | P3 |
| **EDGE-P2-3 Phase 2+** | live endpoint / funding_arb PostOnly | EDGE-P1b ~05-10+ | P3 |
| **G7-04 Phase B/C wiring** | CUSUM consumer hook（Phase A schema landed） | EDGE-P1b 後 | P2 deferred |
| **STRATEGIST-AUTO-PROMOTE** | 自動晉升規則 | P2-01 穩定後 | P3 deferred-long |
| **STRK-FUP-HEALTHCHECK-PRE-EXISTING** | 5 pre-existing pipeline silent-dead 修（[3]/[19]/[23]/[24]/[26]/[27]）| F7 deploy 後 6h 已過 | P2 |
| **ORPHAN-ADOPT-1 Phase 2B** | Strategist `would_take` 終仲裁 | G-1 R-02 | P3 |
| **IP-DEDUP-1** | IntentProcessor 去抖 | P0-3 後 edge 仍負 + 高重發率 | P4 |
| **G-7 ClaudeTeacher 啟用** | 21d demo + G-3 後 | 21d ~05-07+ | P2-P3 |
| **EDGE-DIAG-2 留尾被動觀察** | (ii) PostOnly maker fill rate 1w demo (iv) bb_breakout 1m bandwidth 結構性 | passive accumulation | observation |
```

### D.2 Wave 4 章節補簡化依賴圖（建議 patch position：v4 line 96 之後）

```markdown
### Wave 4 依賴關係圖（簡化）

```
P0-3 決策（~05-15）
   ├─ A 翻正 → LG-2/3/4/5 全推 → Live target ~05-22~05-30
   ├─ C 部分改善 → LG-2/3 + 部分 LG-4 → Live target slipped
   └─ B 仍負 → DUAL-TRACK + 策略重做 → Live target deferred

並行（不依賴 P0-3）：
   MLDE-6 RFC → Live promotion contract
   G4-03 Phase B → canary auto-promote 7d 累積
   G7-04 Phase B/C → CUSUM consumer wiring
   PRE-LIVE-2 HTTPS → 解 G-4 阻塞
```

### Wave 4 時序

| Wave | 週次 | 日期 | 主軸 |
|---|---|---|---|
| Pre-Stage | W21-W22 | 05-01→05-15 | LG/MLDE-6 RFC + 軸線 2 wiring + 軸線 3 infra |
| Decision | ~W22 末 | ~05-15 | P0-3 決策會（A/B/C 分支）|
| Implementation | W23-W24 | 05-15→05-30 | LG-2/3/4/5 E1 落地 + e2e tests |
| Live | ~W24 末 | ~05-30±7d | Live target 中位 |
```

### D.3 「此刻該做什麼」加 active observation 留尾備註

v4 line 41 後加一行：

```markdown
**EDGE-DIAG-2 留尾觀察**：(ii) PostOnly maker fill rate 待 ≥1w demo 累積 (iv) demo bb_breakout 1m bandwidth 結構性問題等 5m 升級或 MLDE sweep；不阻塞主路徑。
```

### D.4 MLDE-6 升級為 active

v4 line 86 (Wave 4 「ML/Dream Live Governed Boundary」段) 把 MLDE-6 從「Wave 4 啟動」升為「Wave 4 Pre-Stage now」：

```markdown
| **MLDE-6** | live-governed | Live promotion contract design | RFC: now (W21) / impl: P0-3 後 |
```

---

## Section E — 風險清單

### E.1 Per-task 風險（Top 5）

| 風險 | 任務 | 嚴重性 | 緩解 |
|------|------|--------|------|
| **R1** LG-2/3/4/5 RFC 若 P0-3 outcome B (edge 仍負) → 部分 RFC 內容作廢 | LG-2/3/4/5 PA RFC | 中 | (1) 作廢 RFC 仍是 dead-code-prevention 學習材料 (2) 文件結構保留，下次重啟時免重做 (3) PA 工時 7.5d 投入回報率仍 > 0（從 P0-3 後阻塞 3-5d 比較）|
| **R2** MLDE-6 RFC 若 P0-3 outcome 影響 advisory→proposal schema | MLDE-6 RFC | 低-中 | RFC 寫成「version-aware schema with feature flag」，不同 outcome 可切不同 advisory 行為 |
| **R3** STRK-FUP-HEALTHCHECK-PRE-EXISTING 修 5 個 silent-dead 中發現 root cause 連鎖（一個修了揭發另一個）| 軸線 2 STRK-FUP | 中 | PA design phase 先全 5 個 RCA 完成才派 E1；避免 implementation-time 連鎖驚喜 |
| **R4** G4-03 Phase B canary 7d 觀察期 PSI drift 假陽性 / 假陰性 | 軸線 2 G4-03 | 中 | DEFAULT-OFF env-gated；observation 期間不 auto-promote；只記錄 metrics |
| **R5** PRE-LIVE-2 HTTPS deploy Tailscale cert 過期 / Let's Encrypt rate limit | 軸線 3 PRE-LIVE-2 | 低 | 雙 path：Tailscale magic-DNS cert（preferred） + Let's Encrypt fallback；提前 1w 申請 cert |

### E.2 Cross-cutting 風險

- **RC-1 並行 sub-agent 衝突**：軸線 1 PA RFC + 軸線 2 拆 ANALYST/HSQ split 同時動 strategy_wiring → **緩解**：PA 派發前 `git fetch + grep -r isolation worktree`，重疊則加 isolation：worktree per memory `feedback_fetch_before_dispatch`
- **RC-2 PM 工時超載**：21d 內派 34 任務，PM Sign-off chain 容易塞車 → **緩解**：拆批 sign-off（每 5-7 任務 1 batch），不 1-1 順序
- **RC-3 多 session memory race**：多 CC session 並行寫 memory.md / TODO.md → **緩解**：`git commit --only <file>` per memory `feedback_git_commit_only_for_metadoc`，且 RFC 報告寫在 PA workspace 不污染 main TODO

### E.3 Operator 角色風險

- **RO-1 P0-3 決策會 operator 缺席**：~05-15 是日期不是 hard cutoff，operator 出差/延後 → **緩解**：軸線 4 prep 完成後即可開會，operator 隨時可觸發；軸線 1 RFC 不依賴會議，獨立完成
- **RO-2 Slack alert 決策延後**：純 alert channel 是低成本但 operator 可能繼續 declined → **緩解**：軸線 3 PRE-LIVE-1 寫成「decision framework」而非「實作」；operator 可在最後一刻決策

---

## Closing

**核心訊息**：21d passive observation **不是閒置**，是準備密集期。本計畫提案 **34 任務 / 5 軸線**，最大並行壓縮可在 21d 內完成 ~70%；剩餘 30% 在 P0-3 outcome 揭曉後啟動。

**最關鍵 3 行動**：
1. 立即派 LG-2-RFC（PA × 1，1.5d）— 解 P0-3 後最大阻塞
2. 立即派 STRK-FUP-HEALTHCHECK-PRE-EXISTING design（PA × 1，1d）— 解 5 個 silent-dead 信任債
3. 立即派 G4-03 Phase B 部署（E1 × 1，3d）— 跑 7d canary 才能在 P0-3 提供 PSI drift 證據

**TODO 修補**：建議派 PM 補回 9 行 backlog active 條目 + 簡化 Wave 4 依賴圖 + 時序表（具體 patch 見 §D）。

**簽核**：等 operator + PM 審核，再派發優先序 Top 10。

---

PA DESIGN DONE: report path: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-01--passive_observation_proactive_plan.md`
