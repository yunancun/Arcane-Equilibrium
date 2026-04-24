---
name: 多角色 adversarial review for high-stakes decisions
description: operator 在關鍵決策（策略促升/phase gating/退場層設計/撤換 core）偏好 QC+FA+FM+PM 並行獨立 review，PM 主 session 匯總 ranked recommendation
type: feedback
originSessionId: 25389af3-8301-4de1-aa7d-c7b1230b551b
---
高影響面決策（系統級 live behavior change / 策略 promote / phase gating / 退場層設計 / 撤換核心組件）— operator 傾向派 QC + FA + FM + PM 並行 adversarial review，各獨立視角 report findings，PM 主 session 匯總 ranked recommendation + kill-switch + timeline。

**Why**：單一 agent 視角有 blind spot；多角色平行 catch 不同維度漏洞。實證：

**(1) 2026-04-24 EDGE-DIAG-1 Phase 2 評估 session**：
- **QC** 獨立發現 CLAUDE.md §三「ExitConfig hot-reload 可調」claim false（IPC handler 無 exit.* 欄位）→ 衍生 EDGE-DIAG-1-FUP-IPC 新 P2 debt
- **FA** 獨立發現 MICRO-PROFIT vacuum hypothesis（H3）+ `risk_close:fast_tr` category-error + `bb_reversion` positive signal 是 design mismatch red flag 非勝利
- **FM** 獨立發現 outlier-driven mean（top 3 groups ≈ 50% of pooled +223 bps）+ v1→v2 bias 估計（clean cf_fired 預測 35-70 實際 37 ✓ / magnitude 預測 +250-450 實際 +12 ✗）
- 3 blind spots 各自 unique；單 agent 派發會全漏。PM 匯總排序 C+D > A > B reject 三角色 unanimous

**(2) 2026-04-24 P1-11 BB-BREAKOUT/REVERSION-DORMANT-1 收尾 audit**（QC/MIT/PM/PA/FA 5 角色 / 3 並行 agent）：
- **E2 code+test agent** 獨立發現：mod.rs:492 entry path 用 naked `+` 與新 saturating_add 不對稱（W）+ 4 個邊界測試漏（F：overflow / expiry=0 / exact-boundary / on_external_close interaction）+ Python `>` 應 `>=` parity（W）
- **FA stats+data agent** 獨立發現：sd 用 `ddof=0` 應 `ddof=1`（小 n bias 7-15%）+ `|t|>1.96` 大樣本近似不適 n<30（n=20 t_crit=2.09）+ Bonferroni 64 combos 沒一個達 ~3.5 + cluster-SE 5 強相關 symbols + **Donchian look-ahead bias** 證偽 F3「-3.20 顯著」（leak-free 下變 -0.45）
- **PM doc+process agent** 獨立發現：CLAUDE.md §三 engine lib 測試數沒更新 1939→1976 + 缺 §七 healthcheck 違規 + CHANGELOG 漏記
- 主 session self-audit 已修 3 bug（F1 wording / F2 stats / B3 Python parity），但**5 FAIL + 6 WARN 全部都是 multi-role audit 才浮現**；F3 被 retract 是因 FA agent 抓到 look-ahead bias，主 session 連同 self-audit 都漏了
- 結論：multi-role 不只用於 strategic decisions，**research/implementation 收尾 closeout 也應派**，否則 false-positive findings 會落地進 TODO/CLAUDE.md/Rust code

**How to apply**：
- **觸發場景**：策略 live 化 / 退場層 design change / Phase promotion / policy change / 撤換核心組件；「要不要改 runtime 行為」的決策
- **角色分工**：
  - QC: code correctness / deployment risk / reversibility / test coverage / 21d 穩定性影響
  - FA: trading semantics / per-strategy fit / business-logic correctness / historical context
  - FM: statistical validity / sample size / outlier handling / bias magnitude
  - PM (主 session): 根原則 5/6/7 對齊 / timeline / kill-switch / ranked recommendation
- **流程**：3 並行 sub-agents → 主 session 收 findings → PM synthesis + operator communicate → 若 BLOCKER 派 E1 rework → FA/QC round 2 re-review 確認 BLOCKER 真解（避免只修表面）
- **小 scope 跳過**：single flag / no-runtime-change / 純 doc 改動不需此流程，單 agent 即可
- **與 CLAUDE.md §八 E1/E2/E4 鏈關係**：本流程在 E1 實作前 — 先策略 review 決定要不要做 + 怎麼做，再派 E1 實作。完成後 E2/E4 審查 code layer。
