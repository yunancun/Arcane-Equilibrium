# 全盤冷酷審計 — Stage 4 PM Final Adjudication

**AUDIT_DATE**: 2026-06-14 ｜ **凍結 SHA**: `976d420e`（三端同步 main）
**輸入**: PA validated fix plan [2026-06-14--cold_audit_validated_fix_plan.md](../../PA/workspace/reports/2026-06-14--cold_audit_validated_fix_plan.md)
**裁決人**: 主會話 PM + Conductor ｜ **模式**: report-only（無 commit / 無 deploy / 無 code mutation）

---

## 1. 裁決總綱

**冷酷審計通過——系統無 P0/CRITICAL 可達缺陷，live 執行 5-gate 邊界實證 fail-closed。** 但揭出 **1 條 P1 級 authority 不對稱（live config 繞 5-gate）** 與 **1 條 P1 系統性 schema-drift 盲區**，加上盈利線的 cost_gate 雙重扣成本（佐證前輪 profit-diagnosis）。對抗複核把 7 條 seam 中 2 條 refuted、3 條降 LOW，只 2 條升 HIGH——說明首輪 seam critic 找對了縫隙，但多數縫隙背後另有 gate（健康訊號：防線比文檔宣稱的更厚）。

**本輪嚴格 report-only：以下無一項在未經 operator 批准前動手。** 治理鏈：合規/架構面走 `PM→CC→FA→PA→PM`，已在 audit 中完成；落地需 `PM→PA→E1→E2→E4` 標準鏈，**E2/E4 不跳**。

---

## 2. 逐項裁決（對照 16 原則 / dispatch protocol / drift / operator-gate）

### 接受為 P1（需 operator 介入後派工）

| ID | 裁決 | 16 原則對照 | operator 前置 |
|---|---|---|---|
| **P1-AUTH-1** live RiskConfig 繞 5-gate | **ACCEPT — 真 authority 不對稱**。非 CRITICAL（需 operator role+scope、寫 V014 audit、AI 路 demo-pinned），但違 #4/#5 與 Hard Boundary 精神。 | #4 mutation 不繞風控授權；#5 survival>profit；#6 不確定趨保守 | **YES — 先裁 intent**：pre-auth 放寬 live config 是刻意？否則修閘對齊 `all_five_live_gates_ok` |
| **P1-PROFIT-1** cost_gate 雙重扣成本 | **ACCEPT 但不可直接翻**。盈利相關，異質 corroboration 前輪 profit-diagnosis。 | #5 #12 證據演進；#13 AI 成本須證 edge | **YES — 批 QC/MIT read-only replay 量化誤拒帶**（修前置，避免翻閘放負期望單） |
| **P1-SCHEMA-1** sqlx 無 contract test | **ACCEPT — 系統性，drift 已實證**（M4 抓 5 column）。 | #8 可重構；#12 證據演進 | **YES — CI ephemeral PG 涉 Actions 成本**（feedback_github_actions_cost 2000min/月） |
| **P1-PERF-1/2/3** 熱路徑三項 | **ACCEPT 但 PERF-1/2 須 bench 證量級**，不憑文獻值/不憑推斷 sign-off（feedback_impl_done_adversarial_review）。 | 無原則衝突；屬 system health | NO（PA 批 scope 即可派 E1，但 bench 數據是 sign-off gate） |

### 接受為 P2/P3（PA 批 scope 後常規鏈，多數無需 operator）
- P2 全列接受（見 PA §2）。**dirty 8 檔的 fix-before-commit（P2-DIRTY-1/2/3 + docstring 中文化）綁定一條鐵則**：closed_pnl + m4 工作**走完 E1→E2→E4 再 commit**，不得以「審計說讀模型 CLEAN」為由跳過 fail-closed 分支補測與 m4 fan-out 修復。
- P3 doc/hygiene + seam 降級 + latent debt 全列接受為清債/記錄，非阻塞。

### 駁回 / 降級（防止未證實猜測誤入 TODO）
- **E3 submit_paper_order「live IPC 寫路徑」** → **REFUTED**：純 paper_state 模擬、0600 socket + HMAC 握手、不通真錢。**不入修復隊列**，僅留防呆 assertion 建議（P3）。
- **QC strategy_name 幻影 strategy** → **REFUTED**：find_strategy_mut 註冊表解析 fail-closed 已測。**不入修復隊列**，optional comment（P3）。
- **CC IPC method registry「2-of-53 gate 缺口」** → **降 LOW**：registry vestigial（debug_assert-only、release 編譯掉、readonly 從不 runtime 讀），非 enforcement 面。**不作安全修**，僅 docstring 去誤導（P3）。
- **MIT ML 決策層斷線/frozen** → **latent by-design**（shadow-only 刻意）：非缺陷，但成熟度誠實性須在 doc 標明「shadow，0 live 決策影響」，不標 active。

### drift / runtime-docs 一致性裁決
- TODO.md §0 Runtime 快照宣稱（engine PID 3607315 / sqlx head=139 / agent_memory 99）本輪**未由審計 runtime 親探**（多軸 read-only/無 Bash），標為 owed 補證——但無證據顯示其失真。
- README/SCRIPT_INDEX/MEMORY drift（P2-R4-1/P2-TW-1/P3）屬文檔層，與代碼安全無關，歸 R4/TW 清債。

---

## 3. 派工建議（operator 批准後啟動，附 owner / 並行-序列 / session 拆分）

**Wave A（operator-gated 前置，並行）**：
- A1: PM→operator 裁 P1-AUTH-1 intent（決策題，非派工）
- A2: QC/MIT read-only replay 量化 P1-PROFIT-1 誤拒帶（read-only，可即派）
- A3: Linux read-only 核 crontab（P2-AIE-2）+ runtime 補證（owed 清單）

**Wave B（A 完成後，可並行多 worktree）**：
- B1: E1(Rust+Python) 修 P1-AUTH-1（intent=修閘時）→ E2 → E3 複審 → E4
- B2: E1 修 P1-SCHEMA-1（CI + audit_migrations + 高價值路徑 query! 宏）→ E2 → E4（CI 成本對齊）
- B3: E1 修 P1-PERF-1/2/3（**先 bench**）→ E2 → E4
- B4: E1 完成 dirty 8 檔 fix-before-commit（P2-DIRTY-1/2/3 + 中文化）→ E2 → E4 → commit

**Wave C（清債，低優先，可批量）**：P2 其餘 + P3 doc/hygiene + seam 降級防呆。

**session 拆分防 compact**：Wave B 每條 P1 獨立 session（Rust 改動 context 大）；後台 wave 防殺 SOP（PM.md §八，駐留等收 / TaskStop 三前置 / agent-wave resumeFromRunId）適用。

---

## 4. 嚴禁動手項（未批准前）
- 任何 P1/P2 代碼修復、CI 改動、cost_gate 閘調整、live config 閘加固。
- 動 8 dirty 檔（除非走完整鏈）。
- commit / push / deploy / rebuild / restart / migration apply / 任何 runtime mutation。
- 解凍 V5.8 M1-M13 / 改 risk·strategy TOML / 動 live·demo·paper auth。

---

## 5. TODO 更新（已確認可執行可追蹤項；連結報告非貼全文）
新增 §audit-2026-06-14 至 TODO.md，登記 P1-AUTH-1 / P1-PROFIT-1 / P1-SCHEMA-1 / P1-PERF-* + dirty fix-before-commit，連結本報告與 PA plan。未證實猜測（refuted/latent）留 PA 報告 §3-4 附錄，不入 TODO。

---

## 6. 審計元數據（誠實披露）
- **執行瑕疵**：Stage 2 首輪 workflow args 誤傳為 JSON 字串 → 退回默認 10 軸、baseline=null、focus 未注入；**已由 Stage 2.5 補完 E4/TW + 8 dirty 檔 deep-dive + 7 seam re-probe（args 正確傳物件）**修正。最終覆蓋 = 12 軸全到位 + dirty 靶區 + seam 帶證據升格。
- **資源**：Stage 2 = 35 agent / 3.58M token / 16min；Stage 2.5 = 22 agent / 2.15M token / 24.5min。合計 57 agent / ~5.7M token。
- **對抗強度達標**：雙向（refute + negative-space + seam critic）、可達性第三視角（高危類）、粒度不壓縮、不為對抗而對抗（refuted 須帶反證）——四要件齊備。
