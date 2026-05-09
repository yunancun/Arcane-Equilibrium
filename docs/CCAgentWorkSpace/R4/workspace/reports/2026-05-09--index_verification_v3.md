# R4 文檔索引核實 v3 — 2026-05-09

基準：baseline `faf2d131` → HEAD `da2aba11`，5 commits

**Tally：✅ 8 / ⚠️ 4 / ❌ 6 / 🆕 3 · 索引完整度 ~64%（v2 92% → 急速回退）· PA redesign 索引登記建議: ADR-0021 + ARCH-04 + 索引條目（雙登記）**

## §1 Executive Summary — 5 commits 期間索引維護完全停滯

| 維度 | v2 | v3 | Δ |
|---|---|---|---|
| 整體索引完整度 | ~92% LOW | **~64% HIGH** | **-28%** |
| 5 commits 期間新文檔索引登記 | — | **0/30+ 新文件登記** | 重大失誤 |
| v2 殭屍引用 v2-N1 | ❌ 檔不存在 | ✅ 兩檔均實存 | closed |
| 殭屍引用「補檔」是否同步索引 | — | **❌ `_v2.md` 未在 docs/README 登記** | NEW |
| PA redesign 索引登記 | — | **❌ docs/README + SPEC + CLAUDE.md + CONTEXT 全 0 登記** | CRITICAL NEW |
| ADR-0021 是否應建 | — | **🆕 推薦立即建** | NEW |

5 commits 期間新增 ~95 reports，**docs/README 完全沒新增登記**（v2 92% → 急速回退至 ~64%）。

## §2 5 commits 索引同步審計

### A.1 5 commits 是否同步 docs/README ❌ 完全失誤

5 commits 期間共產生 **30+ 新 reports**，**0 個** 在 docs/README 索引內登記。

**詳細分類**：
| 類別 | 文件數 | docs/README 登記 |
|---|---|---|
| Operator mirrors（含 PA redesign） | ~24 | 0 |
| PM workspace reports | ~25 | 0 |
| 各 agent verification v1/v2 | 24 | 0 |
| W-AUDIT-6/7 子項 reports | ~17 | 0 |
| Top-level summary | 2 | 0 |
| Archive v1 + v2 | 2 | 1 (v1) / 0 (v2) |
| **TOTAL** | **~95+** | **1 / 95+ ≈ 1.1%** |

**判定**：CLAUDE.md §七「強制同步規則」違反。

### A.2 SPECIFICATION_REGISTER 新登記 ⚠️

- **strategist skill (`c2ab7b1a`)**：c2ba改的是 Rust→Python prompt skill name 注入，不是新 OpenClaw `.claude/skills/<name>/SKILL.md`。建議 SPECIFICATION_REGISTER 加 Amendments 條 `AMD-2026-05-09-03 Strategist Wide-Adjustment Skill`
- **promotion evidence push (`48227607`)**：影響 SM-04 + V079 schema migration。建議 `AMD-2026-05-09-04 Demo→LivePending Promotion Evidence Push`（對應 SM-04 + LG-X-01）

### A.3 v2 殭屍引用 errata 狀態 ⚠️

| 檔案 | 實存？ | docs/README 登記？ | TODO/summary 引用？ |
|---|---|---|---|
| `2026-05-09--w_audit_verified_closed_archive.md` | ✅ | ✅ line 820 | ✅ |
| `2026-05-09--w_audit_verified_closed_archive_v2.md` | ✅ | **❌ 漏登** | ✅ TODO + summary |

**結論**：v2-N1 partial closed；docs/README 應在 line 820 後補 v2 條目。

## §3 PA redesign 索引登記

### B.1 索引登記檢查

| 索引 SoT | 應登記 | 實際 | 狀態 |
|---|---|---|---|
| `docs/README.md` | ✅ 應加 PA report + Operator mirror 兩條 | ❌ 0 條 | CRITICAL |
| `SPECIFICATION_REGISTER.md` ARCH 區塊 | ✅ 應加 ARCH-04 | ❌ 未加 | HIGH |
| `CLAUDE.md` §十 | ⚠️ 視 operator sign-off | ❌ 未加 | MEDIUM |
| `CONTEXT.md` | ✅ 應加 5 詞條 | ❌ 0 詞條 | HIGH |
| `docs/adr/` | ✅ 強烈推薦建 ADR-0021 | ❌ 未建 | CRITICAL |

PA redesign 涉及 **項目史上單一最大架構重定向**，索引登記 0/5 是嚴重 governance gap。

### B.2 ADR-0021 是否應建 — **強烈推薦立即建**

ADR 三條件：
1. **可逆**：✅ R-1..R-5 漸進升級
2. **Surprising**：✅ Strategy interface breaking change + LG governance model 反轉
3. **Real trade-off**：✅ vs「先修 88」path / vs `_REGIME_STRATEGY_PREFERENCES` hardcoded / vs ADR-0020 Layer2 manual

**建議標題**：`ADR-0021: Alpha Source Architecture Upgrade — Strategy Interface, Strategist Scope, Hypothesis Pipeline, Per-Alpha-Source Promotion`

### B.3 ARCH-04 SPECIFICATION_REGISTER 條目（在 ARCH-03 後）

```
| ARCH-04 | Alpha Source Architecture Upgrade | docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--full_loss_architectural_root_cause_redesign.md + docs/adr/0021-alpha-source-architecture-upgrade.md | 🟠 Proposed | R-1..R-5 architectural amendments. Pending operator/PM sign-off. |
```

### B.4 CONTEXT.md 新詞條（5 條）

加新「Alpha source taxonomy」section：
- **Alpha Surface Bundle**：data-rich strategy input
- **AlphaSourceTag**：declared dependency on alpha source
- **AlphaSourceRegistry**：tracking active/observing/deprecated/sunset alpha sources
- **Hypothesis (governance object)**：first-class governance object at parity with Decision Lease
- **Per-alpha-source Live Promotion Gate**：replacement for system-wide live_reserved

## §4 對抗性 Push Back

### 4.1 對「c2ab7b1a 應加 EX/SM 條目」push back
c2ab7b1a 不是新 OpenClaw skill；是 Rust strategist_scheduler 把 skill payload 注入 Python AIService prompt。SPECIFICATION_REGISTER 不需新 SM/EX，需 Amendments AMD-2026-05-09-03。

### 4.2 對「48227607 對應 SM-02？」push back
48227607 影響 PromotionGate（SM-04），**不對應 SM-02**。建議 AMD-2026-05-09-04 對應 SM-04 + LG-X-01。

### 4.3 對「PA redesign 是否需 ADR-0021 + ARCH-04」push back
R-1..R-5 是當前項目最大 architectural pivot。**不建 ADR + 不登記 SPECIFICATION_REGISTER 是嚴重 governance gap**。即使 operator 還未拍板，PA report 已 land = 進入 governance discussion plane，必登記。

ADR-0021 應立即建（即使狀態 = `Proposed / Pending Operator Decision`）。

### 4.4 v2 verification land 後 docs/README 為何反而退化
**根因**：5 commits 期間沒任何 R4 dispatch 觸發。屬「索引維護是 pull-model 而非 push-model」結構性問題。

### 4.5 對 PA redesign 報告本身 push back（架構審計視角）

**PA report 內部一致性 OK**。但 R4 視角發現 **2 個對 governance 的潛在 stale risk**：

- **R-3「Decision Lease + ExecutionPlan + fills propagate originating_hypothesis_id」**：當前 V050 schema 已含 decision_lease_id placeholder。R-3 加 originating_hypothesis_id 需新 V### migration + Guard A/B/C + Linux PG dry-run。建議 ADR-0021 明文「R-3 需 V### migration」。
- **R-4「替換 LG-2/3/4/5 整 system 放權」**：LG-X-02..05 在 SPECIFICATION_REGISTER 是 🔴 Active Gap / 🟡 Design 狀態。R-4 等同 deprecate LG-X-02..05 設計。需在 ADR-0021 明文「supersedes LG-X-02..05 設計部分」+ 在 SPECIFICATION_REGISTER LG-X-02..05 條目加 `Superseded by ARCH-04 R-4 (proposed)` 標記。

## §5 必修清單（按優先序）

### CRITICAL（同 commit 修）

1. **`docs/README.md`**：line 819-820 之間插入 5 commits 期間 30+ 新 reports 索引 section（仿 line 162「W-AUDIT-1 index addendum」格式）
2. **`docs/README.md` line 820 後**：補 `_v2.md` archive 條目
3. **建 `docs/adr/0021-alpha-source-architecture-upgrade.md`**：狀態標 `Proposed / Pending Operator Decision`
4. **`SPECIFICATION_REGISTER.md`**：ARCH 區塊加 ARCH-04 + Amendments 加 AMD-2026-05-09-03/04；LG-X-02..05 加 supersedes 警告
5. **`CONTEXT.md`**：加「Alpha source taxonomy」section（5 詞條）

### HIGH（可下次 sprint）

6. **`CLAUDE.md` §十「關鍵文件指針」**：待 PM sign-off PA redesign 後加引用
7. **`CLAUDE.md` §五 架構總覽**：待 PA redesign 進入 active sprint 後更新流水線描述

### MEDIUM

8. **R4 SOP**：建立「v2 verification land 必觸發 R4 doc sync」自動化或 PM checklist
9. **DEPRECATED.md**：當 ADR-0021 進入 Accepted 狀態，把 `_REGIME_STRATEGY_PREFERENCES` + LG-X-02..05 system-wide promotion 加廢棄條目

## §6 R4 對抗性自我修正 vs v2

| v2 判斷 | v3 重審結論 |
|---|---|
| 索引完整度 ~92% | 5 commits 期間完全失維 → 真實 ~64% |
| v2-N1 殭屍引用 (HIGH) | partial closed（v1 補檔），但補檔時漏登 v2 條目 → derivative drift |
| W-AUDIT-1 closure 達成反駁要求 | 仍真，但 **v2 verification land 後沒接同等 doc sync 流程** = governance forcing function 不持續 |
| 「殘留弱項不阻 W-AUDIT-1」| 雖不阻 W-AUDIT-1，但**新阻 v2 verification + PA redesign + 5 commits 收口的 governance compliance** |

---

**R4 VERIFICATION v3 DONE** · ✅ 8 / ⚠️ 4 / ❌ 6 / 🆕 3 · 索引完整度 ~64% · PA redesign 索引登記建議: ADR-0021 + ARCH-04 + 索引條目 + CONTEXT 5 詞條 + AMD-2026-05-09-03/04（雙登記，CRITICAL 同 commit 補）
