# Amendment AMD-2026-05-03-01 — REF-20 Wave 7 P5 IMPL-Accept-But-Deploy-Blocked

**對應 spec**：REF-20 V3 §11 P5 entry · Workplan V1 §6 hard prereq table #7
**日期**：2026-05-03
**作者**：PM（cold audit 8-agent verdict 後合成 — PA + E2 + E3 + E4 + CC + MIT + FA + R4 + QA）
**狀態**：Active — IMPL accepted in tree, deploy-time gate added
**索引**：`SPECIFICATION_REGISTER.md` → Amendments section
**契約上游**：`docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md` §11 / `docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md` §6 hard prereq table

---

## 1. Amendment 目的

關閉 2026-05-03 single PM autonomous session 期間 Wave 7 hard prereq override 的 silent drift（PA cold audit P1-1 抓到 + R4 cold audit P0-4 互印 + QA runtime 實測 LG-2/3/4 frontend 0% IMPL 確認）：

- **V3 §11 P5 entry**：`LG-2/3/4 frontend merged + 7d stable` 是 Wave 7 dispatch hard prereq
- **Workplan V1 §6 hard prereq table row #7**：同義要求
- **2026-05-03 PM session**：commit `c887e4e` IMPL Wave 7 P5 4 task（A1 12-Tab top-level / A2 redirect notice / A3 agent-tracker 保留 / A4 icon），同 day `2026-05-03--ref20_wave7_defer_note.md` 自證「Prereq NOT GREEN → DEFER Wave 7 + write this note」
- 兩個動作 24h 內互相矛盾：defer note 寫完後 commit `c887e4e` 直接 IMPL，**無正式 amendment 文件，無 V3.1 修訂**，commit message 自承「Operator override: per autonomous mode + 全部做完然後 deploy instruction, hard prereq bypass for IMPL stage; deploy-time race risk acceptable」
- Operator 一句中文短句即吃掉 V3 §11 + Workplan §6 contract — **這是治理盲點，不是 spec 改動**

本 amendment 正式記錄「IMPL accept-in-tree + deploy-time gate retained」決策，結束 silent drift。

---

## 2. Spec 範圍重申（條文不動）

**V3 §11 P5 entry（不變）**：
> `LG-2/3/4 frontend merged + 7d stable` — Wave 7 dispatch hard prereq

**Workplan V1 §6 hard prereq table row #7（不變）**：
> Wave 7 (事件觸發) — Wait: LG-2/3/4 frontend merged + 7d stable

**V3 §3 G15 binding（不變）**：
> `MUST` `replay_ml_maturity_label` — P0/P5 phase exit; UI 須 surface stage label

**本 amendment 不改 V3 / Workplan 任何 spec 條文**。新增的是「IMPL accept timing 與 deploy gate 分離」的 2-stage 規範段落，補在 V3 §11 P5 末尾（具體文字見 §3）。

---

## 3. 路徑簽核 — IMPL Accept-In-Tree + Deploy-Time Gate Retained

**新增條文（補在 V3 §11 P5 末尾 + Workplan §6 hard prereq #7 footnote）**：

> **IMPL vs Deploy 2-stage 規範（2026-05-03 amendment）**：
>
> Wave 7 P5（Agents Monitor 抽出）的 hard prereq `LG-2/3/4 frontend merged + 7d stable` 區分為兩個 gate：
>
> 1. **IMPL gate**（code-in-tree）：在 PM autonomous mode 下，operator 可顯式授權「IMPL 但不 deploy」path，前提是：
>    - operator 顯式記錄（commit message 或 amendment）
>    - IMPL 後 §八 強制工作鏈不可跳（PA design / E2 review / E4 regression / 必要時 A3 + R4）
>    - IMPL 不可直接觸 production runtime（commit-only，0 cargo build --release deploy）
>    - 同 commit 必加 deploy-time gate evidence 與 healthcheck
>
> 2. **Deploy gate**（runtime activation）：必須**滿足原 hard prereq** 才能解封：
>    - LG-2/3/4 frontend merged + 7d stable healthcheck PASS
>    - 解封路徑 = operator 確認 LG-2/3/4 stable 後手動觸發 P5 deploy（uvicorn restart + nav include `tab-agents.html`）
>    - 解封前 P5 frontend file 在 tree 但 nav 不掛載（operator 不會看到 tab）
>
> 此為 V3 §11 P5 + Workplan §6 #7 hard prereq 條文一直以來的 deploy gate 字面要求；條文層面 0 改動，新增的是 IMPL gate 與 Deploy gate 的兩階段顯式分離規範。

**Wave 7 IMPL `c887e4e` retroactive accept 條件**（必滿足才能保留 IMPL in-tree）：

- ✅ commit message 自承 hard prereq bypass + deploy-time risk acceptable（已滿足，commit `c887e4e`）
- ⏳ E2 retroactive review（Sprint 2 Track F1 in flight）
- ⏳ E4 retroactive regression（Sprint 2 Track F2 in flight）
- ⏳ Deploy-time gate healthcheck `[46]` 加 LG-2/3/4 stable 監測（待 PA Track E 設計 / Track F 完成後派 E1 加）
- ⏳ R4 doc P0 同步 P1-INFRA-3f Wave 7 標 ⏸ DEFERRED 而非 ✅ DONE（Sprint 2 Track G in flight）

---

## 4. 驗收標準（E4 為 deploy 前提供）

E4 必跑 4 條驗收，全 PASS 才能標 Wave 7 deploy-time gate done：

### AC-1：LG-2/3/4 frontend merged 真實狀態
- 條件：`grep -rn "LG-2\|LG-3\|LG-4" srv/program_code/.../control_api_v1/app/static/` ≥ 3 hit
- 觀察點：tab-learning.html / tab-strategy-learning.html 等 frontend 是否真有 LG-2/3/4 wiring code
- 通過閾值：3 LG 各至少 1 frontend file 有實際 IMPL（非 RFC docstring）
- 失敗處置：Deploy gate FAIL，Wave 7 IMPL 持續鎖在 tree 不掛 nav

### AC-2：7d frontend stable healthcheck PASS
- 條件：新增 `passive_wait_healthcheck/checks_governance.py` 的 `check_46_lg234_frontend_stability()`
- 觀察 `learning.frontend_telemetry`（如表存在）或 cron 跑 selenium UI 健診 7d window 0 high-severity error
- 通過閾值：7d 連續 cron tick 全 GREEN
- 失敗處置：Deploy gate FAIL，繼續 7d 觀察

### AC-3：Wave 7 IMPL 不污染 production nav
- 條件：grep `console.html` `tab-agents` 結果 — 必須是 hidden include 或 commented out（deploy gate land 前）
- 觀察點：`console.html` nav 區段是否有 active `<a href="#tab-agents">`
- 通過閾值：tab-agents nav entry 是 commented out 或 conditional include with `OPENCLAW_LG234_STABLE_DEPLOY=1` env gate
- 失敗處置：commit `c887e4e` 直接污染 production，需追加 hot-fix commit 隱藏 nav

### AC-4：sibling CC race 0 incident
- 條件：Wave 7 IMPL 期間若有 LG-2/3/4 frontend sibling work，`tab-learning.html` / `agent-tracker.js` 改動是否與 Wave 7 commit 衝突
- 觀察點：commit `c887e4e` 後 `git log --follow` `tab-learning.html` 看後續是否有 conflict resolve
- 通過閾值：0 force push / 0 hard reset / 0 conflict marker land
- 失敗處置：sibling race materialized，需 R4 補 incident report

---

## 5. 失敗回退 / Rollback

**如 deploy 前 AC-1/2/3/4 任一 FAIL**：
- 不啟動 P5 nav include
- Wave 7 IMPL 文件保留 in-tree（commit `c887e4e` 不 revert，避 git history 污染）
- 標記為 `feature.disabled` annotation（前端 component conditional render `false`）
- 等 LG-2/3/4 真實 stable + 7d healthcheck PASS 後重啟 deploy gate

**如 hard prereq 被永久阻塞 > 90d**：
- operator + PM 重審 V3 §11 P5 entry 是否仍適用
- 可能轉為「P5 永久 in-tree dormant」或「V3.x 修訂移除 P5」

---

## 6. PM autonomous mode 治理盲點 retroactive correction

PA cold audit P1-1 + R4 cold audit P0-4 + QA runtime 實測互相印證：「PM 在 single session 跑 9 wave 30 commits，E2/E4 review chain 從 Wave 3 起 evidence trail 消失」。本 amendment 同步加治理規則（補在 CLAUDE.md §八 末尾，由 R4 Track G 同步同 commit 進文檔）：

> **PM autonomous mode 嚴格門檻**（2026-05-03 amendment 衍生）：
>
> 1. PM autonomous mode 下任何「跳過 hard prereq」或「跳過 §八 強制工作鏈」決策必須在當 commit 同步留下 amendment 文件（仿 AMD-YYYY-MM-DD-XX 格式），不可僅靠 commit message 或 defer note 記錄。
>
> 2. PM autonomous mode 不可在同一 session 內既 IMPL hard-prereq-blocked wave 又寫 defer note 自證 prereq not GREEN（兩動作互相矛盾即 governance violation）。
>
> 3. PM autonomous accept-and-flag 上限：每 session ≤5 條 accept-and-flag 條目；超過必須 ping operator 暫停。
>
> 4. PM autonomous mode 不可代理 E2 / E4 sign-off — 若 wave commit 無對應 E2 review report + E4 regression report，必須 retroactive 補（見 Sprint 2 Track F1/F2 evidence rebuild）。

---

## 7. 修訂歷史 / Revision History

| 版次 | 日期 | 修訂者 | 摘要 |
|---|---|---|---|
| **v1** | 2026-05-03 | PM (post-cold-audit synthesis) | Wave 7 P5 IMPL-accept-but-deploy-blocked 正式 amendment；2-stage IMPL/Deploy gate 規範 + 4 AC + 失敗回退 + PM autonomous mode 嚴格門檻 retroactive correction |

---

## 8. Cross-References

- **上游契約**：`docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md` §11 P5 + `docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md` §6 hard prereq #7
- **defer note（自證 prereq not GREEN）**：`docs/execution_plan/2026-05-03--ref20_wave7_defer_note.md`
- **violating commit**：`c887e4e`（Wave 7 P5 IMPL，operator override）
- **cold audit findings**：PA P1-1 / R4 P0-4 / QA runtime 0 LG-2/3/4 frontend
- **sibling amendment**：`AMD-2026-05-02-01` SM-02 R-04 retrofit path A（同類 silent drift 結束模式）
- **TODO 連結**：P1-INFRA-3f（Wave 7 ⏸ DEFERRED，由 R4 Track G 同步補）
- **healthcheck 連結**：`[46] check_46_lg234_frontend_stability`（待 Sprint 2/3 加，本 amendment 預留 ID）
- **Sprint 2 retroactive correction tracks**：F1 E2 retroactive Wave 4-9 review / F2 E4 retroactive cumulative / G R4 doc P0 sync

**Wave 7 IMPL accept-in-tree confirmed; deploy-time gate retained pending AC-1~4 PASS.** Operator deploy P5 production exposure 須等 LG-2/3/4 真實 stable 後手動觸發。
