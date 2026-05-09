# Track A Dispatch Plan — ADR-0021 R-1..R-5 IMPL Sequencing

**作者**：PA（Project Architect）
**日期**：2026-05-09
**Status**：ADR-0021 Accepted 2026-05-09（operator sign-off via auto-mode dispatch）
**對應上游**：
- `docs/adr/0021-alpha-source-architecture-upgrade.md`（Accepted）
- `docs/execution_plan/2026-05-09--w_audit_8a_alpha_surface_foundation_spec.md`（R-1 SPEC，已 land）
- `docs/execution_plan/2026-05-09--w_audit_8b_strategist_alpha_orchestrator_spec.md`（R-2 IMPL spec，本 plan 同 commit land）
- `docs/execution_plan/2026-05-09--w_audit_8c_hypothesis_pipeline_spec.md`（R-3 IMPL spec）
- `docs/execution_plan/2026-05-09--w_audit_8d_per_alpha_source_promotion_gate_spec.md`（R-4 IMPL spec）
- `docs/execution_plan/2026-05-09--w_audit_8e_spec_as_code_spec.md`（R-5 IMPL spec）
- `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--full_audit_pa_fix_plan_v2.md` §4 §5（dual-track decision + Track A roadmap）
- `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--full_loss_architectural_root_cause_redesign.md`（root cause + R-1..R-5 design intent）
**讀者**：Operator / PM / E1 / E2 / E4 / 全 Track A IMPL agents

---

## §0 Track A 命名 alignment（多 schema 並存說明）

ADR-0021 R-1..R-5 對應的 wave 編號在三套文件中並存，本 dispatch plan 以 PM 任務指定 schema 為 SoT，後續 IMPL agent 以本 plan 為準：

| amendment | redesign report | PA fix plan v2 §5 表 | TODO.md v18 排序 | **本 plan / spec doc 命名** |
|---|---|---|---|---|
| R-1 Alpha Surface Foundation | R-1 | W-AUDIT-8a | W-AUDIT-8b（IMPL 階段）| **W-AUDIT-8a** |
| R-2 Strategist Scope Reframe | R-2 | W-AUDIT-8e | W-AUDIT-8c | **W-AUDIT-8b**（PM 任務指定 b/c/d/e 對應 R-2/3/4/5）|
| R-3 Hypothesis Pipeline | R-3 | W-AUDIT-8f | W-AUDIT-8d | **W-AUDIT-8c** |
| R-4 Per-alpha-source Live Promotion Gate | R-4 | W-AUDIT-8g | W-AUDIT-8e | **W-AUDIT-8d** |
| R-5 Spec-as-Code | R-5 | W-ARCH-3 | W-AUDIT-8f | **W-AUDIT-8e** |

**未來 wave 候選**（ADR-0021 不直接 cover，但 fix plan v2 §5 提及）：
- 候選 alpha source 業務 IMPL（funding skew spread / liquidation cluster / BTC→Alt lead-lag / orderbook imbalance）→ 留給 W-AUDIT-8b/c/d 在 fix plan v2 schema 內，或本 plan 完成後新增 W-AUDIT-8f/8g/8h 命名

PM Sign-off 時 TODO.md v18 dispatch table 應同步本 plan 的 wave 編號。

---

## §1 Executive Summary（給 PM，200 字）

ADR-0021 R-1..R-5 為「玄衡 alpha source 架構升級」5 件 architectural amendment：R-1 升 Strategy interface 為 Alpha Surface 一等公民（已 SPEC PHASE land）；R-2 Strategist 加 alpha-source orchestrator 職責 + propose Hypothesis 通道（不是 reframe，是擴展 — 接受 Push Back 2 修正）；R-3 Hypothesis 升 first-class governance object（接受 Push Back 3：L0+L1 跑 + Push Back 4：W-AUDIT-4b prerequisite）；R-4 Per-alpha-source Live Budget（in-scope-of-Live 細粒度，不 reverse `live_reserved` binary）；R-5 Spec-as-Code 自動化 forcing function（接受 Push Back 5：Spec-Runtime drift 真正 Root Cause 5）。**整 Track A 估 ~82 person-day / 11-13 sprint**（R-1 40pd + R-2 12pd + R-3 26pd + R-4 24pd + R-5 20pd，部分並行）。**Critical path = R-1 Phase A → R-2/R-3 部分並行 → R-4 必後 LG-X baseline**；R-5 全並行不阻塞。**最早第一個 alpha-bearing live promotion**：取決於 LG-X 1-5 baseline 完成時點 + R-1..R-4 IMPL completion 時點，悲觀 8-12 weeks 後。

---

## §2 R-1..R-5 IMPL 依賴關係 DAG

```
                                                       ┌────────────────┐
                                                       │  R-5 W-AUDIT-8e │
                                                       │  Spec-as-Code   │
                                                       │ (全並行不阻)    │
                                                       └────────────────┘

[W-AUDIT-4b]───────┐
INSERT path/cron    │ (Push Back 4 採納，hard prerequisite)
                    │
                    ▼
[W-AUDIT-8a Phase A]──────►[W-AUDIT-8b R-2]
trait + AlphaSurface       Strategist propose
struct land                + AlphaSourceRegistry
       │                            │
       │                            │
       ▼                            ▼
[W-AUDIT-8a Phase B/C/D]    [W-AUDIT-8c R-3]
Tier 2/3/4 panel land       Hypothesis Pipeline
       │                    + Decision Lease/Plan/fills propagate
       │                    + attribution writer rewrite
       │                            │
       └─────────┬──────────────────┘
                 │
                 ▼
        [LG-1..LG-5 baseline]
        H0 production caller
        + pricing binding
        + supervised-live SM
        + monitor + self-aware
                 │
                 ▼
        [W-AUDIT-8d R-4]
        Per-alpha-source LiveBudget
        + GovernanceHub.acquire_alpha_source_budget()
        + Guardian per-alpha veto
                 │
                 ▼
[First per-alpha-source live promotion]
```

---

## §3 Sequencing 表（Sprint 級）

| Sprint | R-1 | R-2 | R-3 | R-4 | R-5 |
|---|---|---|---|---|---|
| **N+0**（current）| Phase A IMPL（trait + AlphaSurface struct + 5 策略 declare）| ─ | ─ | ─ | T1/T2/T3/T4/T7（CI gate Phase 1）|
| **N+1** | Phase B IMPL（funding/oi panel collector）| T1/T2/T5（registry + migration + MessageBus topic）| ─（**等 W-AUDIT-4b**）| ─ | T8/T9（漸進 backfill top 30）|
| **N+2** | Phase C IMPL（liquidation pulse）| T3/T4（propose + Bayesian update）| W-AUDIT-4b 完 → T1/T2 開（migration + state machine）| ─ | T5/T6（auto-extract INDEX/REGISTER）|
| **N+3** | Phase D IMPL（Tier 4 + 5 策略 callsite migration）| T6/T7（GUI + integration test）| T3/T4（pipeline + Analyst L2）| ─ | T10/T11（integration + ADR）|
| **N+4** | （Phase D 收尾 + 7d replay E2E）| **R-2 完成** | T5/T6/T7（L3 + propagate）| ─ | **R-5 完成** |
| **N+5** | **R-1 完成** | ─ | T8/T9/T10（GUI + integration + healthcheck）| ─ | ─ |
| **N+6** | ─ | ─ | **R-3 完成** | （**等 LG-1..LG-5 baseline**）| ─ |
| **N+7** | ─ | ─ | ─ | LG baseline 完 → T1/T2 開 | ─ |
| **N+8** | ─ | ─ | ─ | T3/T4/T5/T6（GovernanceHub + Guardian + IntentProcessor + fill writer）| ─ |
| **N+9** | ─ | ─ | ─ | T7/T8/T9/T10（healthcheck + GUI + integration + ADR）| ─ |
| **N+10** | ─ | ─ | ─ | **R-4 完成** | ─ |
| **N+11+** | （未來 alpha source candidate IMPL：funding skew / liquidation cluster / BTC→Alt lead-lag）| | | | |

**Critical path 長度**：~11 sprint = ~22 weeks ≈ 5-6 月（樂觀）

**並行加速可能**：
- R-5 全 wave 並行不阻塞（substrate work）
- R-1 Phase B/C/D 內部分並行（Phase B + C 並行於 Phase A 後）
- R-2 部分 sub-task 可在 R-1 Phase A land 後立即開
- R-3 在 W-AUDIT-4b PASS 後立即開（不等 R-2 完成；R-2 propose 通道 + R-3 register 是 forward dependency）

**Critical path 最樂觀壓縮**：R-3 不等 R-2 完成 + R-1 Phase B 與 R-2 部分 sub-task 並行 → ~8-9 sprint = 4-5 月

---

## §4 並行 / 串行細節

### 4.1 R-1 Phase 內部 DAG

```
Phase A ──┬─→ Phase B ──┐
          │             ├─→ Phase D
          └─→ Phase C ──┘
```

- Phase A 必先（trait 升級）
- Phase B + C 並行（不同 collector / 不同 PG 表 / 不同 IPC slot）
- Phase D 必後 B + C

### 4.2 R-2 與 R-1 並行

R-2 依賴 R-1 Phase A（trait + AlphaSurface struct + AlphaSourceTag enum land），不依賴 Phase B/C/D。

| R-2 sub-task | 何時可開 | 依賴 |
|---|---|---|
| R2-T1 alpha_source_registry.py | R-1 Phase A 完 | AlphaSourceTag enum |
| R2-T2 V### migration | 並行 R2-T1 | 無 |
| R2-T3 propose_hypothesis() | 串行 R2-T1 | Registry exists |
| R2-T4 RegimeStrategyAffinity | 並行 R2-T3 | 無 |
| R2-T5 MessageBus topic | 並行 R2-T1 | 無 |
| R2-T6 GUI tab | 並行 R2-T2..T4 | 無 |
| R2-T7 Integration test | 串行 R2-T1..T5 | 全前置 |

**最早開始時點**：R-1 Phase A land 後（Sprint N+0 末或 N+1 初）

### 4.3 R-3 與 R-2 forward dependency

R-3 不等 R-2 完成；R-3 是「Hypothesis as first-class object」，R-2 是「Strategist propose 通道」。

| R-3 sub-task | 何時可開 | 依賴 |
|---|---|---|
| R3-T1 V### migration learning.hypotheses | W-AUDIT-4b PASS | attribution writer chain 修復 |
| R3-T2 alter Decision Lease/Plan/fills | 串行 R3-T1 | hypotheses table exists |
| R3-T3 hypothesis_pipeline.py | 並行 R3-T1（mock DB）| 無 |
| R3-T4 Analyst L2 | 並行 R3-T3 | 無 |
| R3-T5 Analyst L3 | 串行 R3-T4 | L2 PatternInsight |
| R3-T6 propagate 接線 | 串行 R3-T2 | alter migration land |
| R3-T7 attribution writer rewrite | 串行 R3-T6 | propagate 完 |
| R3-T8 GUI Hypothesis Lab | 並行 | 無 |
| R3-T9 Integration test | 串行 R3-T1..T8 | 全前置 |
| R3-T10 healthcheck | 並行 | 無 |

**Critical issue**：R-3 等 W-AUDIT-4b 是 hard prerequisite（Push Back 4 採納）。如 W-AUDIT-4b INSERT path 揭新 schema 設計 → R-3 slip +20h。

### 4.4 R-4 與 LG-X baseline 串行

R-4 必後 LG-1..LG-5 baseline IMPL 完成（H0 production caller / pricing binding / supervised-live SM / monitor / self-aware）。

| R-4 sub-task | 何時可開 | 依賴 |
|---|---|---|
| R4-T1 V### migration | LG baseline 全 PASS | LG substrate |
| R4-T2 live_budget_manager.py | 並行 R4-T1（mock DB）| 無 |
| R4-T3 acquire_alpha_source_budget() | 串行 R4-T2 | manager exists |
| R4-T4 Guardian per-alpha veto | 串行 R4-T3 | API exists |
| R4-T5 IntentProcessor inject | 串行 R4-T3 | API exists |
| R4-T6 fill writer update_realized() | 串行 R4-T5 | propagation chain |
| R4-T7 healthcheck | 並行 | 無 |
| R4-T8 GUI Live Budget Inventory | 並行 | 無 |
| R4-T9 Integration test | 串行 R4-T1..T8 | 全前置 |
| R4-T10 ADR + SPECIFICATION_REGISTER | 並行 | 無 |

**最早開始時點**：LG-1..LG-5 baseline 全 PASS（從 CLAUDE.md §三 Active Blockers 看，LG-2/LG-3 仍未 IMPL）

### 4.5 R-5 全並行

R-5 是 substrate work，不依賴 R-1..R-4 任何進度。可即刻啟動。

| R-5 sub-task | 何時可開 | 依賴 |
|---|---|---|
| R5-T1 V### migration | Sprint N+0 開始 | 無 |
| R5-T2 spec_runtime_drift_check.py | 並行 | 無 |
| R5-T3 GitHub Actions | 並行 | 無 |
| R5-T4 pre-commit hook | 並行 | 無 |
| R5-T5/T6 auto-extract | Phase 3 | manual baseline 對齊 |
| R5-T7 healthcheck | 並行 | 無 |
| R5-T8/T9 backfill | Phase 2（漸進）| 無 |
| R5-T10 Integration test | 串行 R5-T2/T3/T4 | CI gate IMPL |
| R5-T11 ADR + W-AUDIT-1 reframe | Phase 4 | 無 |

---

## §5 跨 R 依賴鏈總結

### 5.1 Hard prerequisite（不可繞）

| 子依賴 | 鎖定關係 |
|---|---|
| W-AUDIT-4b | → R-3 hard prerequisite（Push Back 4 採納）|
| R-1 Phase A | → R-2 hard prerequisite（trait 簽名 + AlphaSourceTag enum）|
| LG-1..LG-5 baseline | → R-4 hard prerequisite（substrate）|
| R-1 Phase D | → R-4 hard prerequisite（5 策略 callsite migration 完成才有 alpha_source_id 全鏈路）|
| R-3 完成 | → R-4 hard prerequisite（originating_hypothesis_id 全鏈路 propagate 才能 acquire_alpha_source_budget）|

### 5.2 Soft prerequisite（可繞但 degraded）

| 子依賴 | 處理 |
|---|---|
| R-1 Phase B（Tier 2 panel）| R-2 IMPL 不阻；7d integration test 才需要真實 panel |
| R-2 完成 | R-3 不等；R-2 propose + R-3 register 是 forward dependency |
| R-3 完成 | R-4 等（不能繞，per-alpha-source budget 需 hypothesis_id propagate）|

### 5.3 並行能開的（無依賴）

- R-5 全 wave 從 Sprint N+0 即可開
- R-1 Phase B/C 可並行於 Phase A 收尾（最後 sprint 內）
- R-2 部分 sub-task（R2-T2/T5）可並行 R2-T1

---

## §6 與既有 Track W wave 衝突分析

### 6.1 W-AUDIT-3b（ExecutorAgent runtime smoke）

| R | 衝突狀況 | Mitigation |
|---|---|---|
| R-1 | **無衝突** | R-1 在 Rust strategies / TickContext / 5 策略，不碰 ExecutorAgent |
| R-2 | **無衝突** | R-2 在 Strategist Python，不碰 Executor |
| R-3 | **無衝突** | R-3 在 Analyst + DB schema |
| R-4 | **協同**（per fix plan v2 push back 1）| W-AUDIT-9 T3 改 `executor_config_cache.py` `_read_shadow_mode` stage-aware；W-AUDIT-3b 必先 land；R-4 fail-closed default 對 budget alpha_source_id 無 ACTIVE → reject 不碰 ExecutorAgent shadow_mode 邏輯 |
| R-5 | **無衝突** | R-5 substrate |

**結論**：W-AUDIT-3b 必先 land（per fix plan v2 PM push back 1），但只與 W-AUDIT-9 T3 衝突，**與 R-1..R-5 全無衝突**。

### 6.2 W-AUDIT-9（Graduated Canary Foundation）

| R | 衝突狀況 | Mitigation |
|---|---|---|
| R-1 | **協同** | W-AUDIT-9 graduated canary 是 R-1 alpha source candidate（W-AUDIT-8b/c/d 候選 IMPL）的 deploy substrate |
| R-2 | **無衝突** | R-2 不碰 canary stage |
| R-3 | **無衝突** | R-3 不碰 canary stage |
| R-4 | **協同強** | per-alpha-source budget 可 leverage W-AUDIT-9 5-stage canary（per ADR-0021 §「Decision」每個 alpha source 走自己的 5-stage canary）|
| R-5 | **協同** | LIFECYCLE 4 stage 與 canary 5-stage 對應（LIFECYCLE active = canary stage 4 / observing = stage 1-3）|

**結論**：R-1..R-5 與 W-AUDIT-9 全無衝突，部分 R-1/R-4 是協同關係（不阻塞）。

### 6.3 W-AUDIT-4b（label_close_tag NULL writer fix + 6 表 INSERT path）

| R | 衝突狀況 | Mitigation |
|---|---|---|
| R-1 | **無衝突** | R-1 不依賴 attribution writer |
| R-2 | **soft 依賴** | R-2 用 fallback prior，不嚴格依賴 attribution_chain 修復 |
| R-3 | **hard prerequisite**（Push Back 4 採納）| W-AUDIT-4b 必先 land；不修 attribution writer chain，hypothesis pipeline 設計再完美仍無 evidence 餵 |
| R-4 | **無衝突** | R-4 不依賴 attribution writer |
| R-5 | **無衝突** | R-5 substrate |

**結論**：W-AUDIT-4b 是 R-3 的 hard prerequisite；W-AUDIT-4b 卡住 → R-3 不能開。

### 6.4 W-AUDIT-6（bb_reversion + portfolio_var review）

| R | 衝突狀況 | Mitigation |
|---|---|---|
| R-1..R-5 | **正交** | W-AUDIT-6 不重寫策略；R-1..R-5 不重寫策略 |

**結論**：W-AUDIT-6 完全並行。

### 6.5 W-AUDIT-7（GUI/AI/Layer2）

| R | 衝突狀況 | Mitigation |
|---|---|---|
| R-1 | **無衝突** | |
| R-2 | **GUI 補位** | R-2 加 alpha_sources tab（13→14 tab）；W-AUDIT-7 處理既有 13 tab；不衝突 |
| R-3 | **GUI 補位** | R-3 加 hypothesis_lab tab（14→15 tab）|
| R-4 | **GUI 補位** | R-4 加 live_budgets tab（15→16 tab）|
| R-5 | **無衝突** | |

**結論**：R-2/R-3/R-4 累加 13→16 tab；A3 v2 NEW-7/8 已建議 13→15 tab 擴展；本 plan 累加到 16 tab，A3 必 review。

### 6.6 W-AUDIT-1（doc sync wave）

| R | 衝突狀況 | Mitigation |
|---|---|---|
| R-5 | **reframe** | per ADR-0021 + fix plan v2 §5 表，W-AUDIT-1 從 manual doc sync reframe 為「automated doc sync via R-5 spec-as-code substrate」|

**結論**：W-AUDIT-1 在 R-5 land 後升級為 substrate-driven。

---

## §7 PM Sign-off 必查 5 點

### 7.1 命名 alignment 接受
PM 接受本 plan 的 wave 編號 schema（W-AUDIT-8a/8b/8c/8d/8e 對應 R-1/R-2/R-3/R-4/R-5），同時 TODO.md v18 dispatch table 對齊更新。

### 7.2 Critical path 接受
~11 sprint 樂觀 / 11-13 sprint 中位 estimate；PM 接受最早第一個 alpha-bearing live promotion 在 8-12 weeks 後（不前置到 supervised live 6/15-7/15 規劃帶）。

### 7.3 Hard prerequisite 接受
- W-AUDIT-4b → R-3
- LG-1..LG-5 baseline → R-4
- R-1 Phase A → R-2
- R-1 Phase D → R-4
- R-3 完成 → R-4

PM 確認任何前置卡住，後續 R 自然 slip，不可 force land。

### 7.4 16-tab 擴展接受
13 → 14 (alpha_sources) → 15 (hypothesis_lab) → 16 (live_budgets) GUI tab 擴展；A3 必 review；CLAUDE.md §五 同次 commit 補。

### 7.5 ADR-0021 status 對齊
ADR-0021 已 Accepted；R-1..R-5 IMPL 完成各自補 References + completion commit hash。

---

## §8 衝突點與 Mitigation 總結

### 8.1 R 內衝突（無）

R-1/R-2/R-3/R-4/R-5 之間無「同檔案改動」衝突；R-2/R-3/R-4/R-5 各自在不同 Python module / DB schema / CI infrastructure。

### 8.2 R 與 Track W 衝突（部分）

| R | 衝突 wave | 性質 | Mitigation |
|---|---|---|---|
| R-1 | 無 | ─ | ─ |
| R-2 | W-AUDIT-7（GUI tab 累加）| 協同 | A3 review；本 plan 累加到 16 tab |
| R-3 | W-AUDIT-4b | hard prerequisite | W-AUDIT-4b 必先 land |
| R-3 | W-AUDIT-7（GUI tab）| 協同 | 同上 |
| R-4 | LG-1..LG-5 baseline | hard prerequisite | LG 必先 land |
| R-4 | W-AUDIT-7（GUI tab）| 協同 | 同上 |
| R-4 | W-AUDIT-9 graduated canary | 協同強 | per-alpha-source budget leverage 5-stage canary |
| R-5 | W-AUDIT-1 doc sync | reframe | W-AUDIT-1 升級為 substrate-driven |

### 8.3 衝突點 Risk + Fallback

| Risk | 機率 | Mitigation | Fallback |
|---|---|---|---|
| W-AUDIT-4b INSERT path 揭新 schema 設計問題 | 高 | Push Back 4 採納，W-AUDIT-4b 必先 PASS；R-3 spec land 先，IMPL 等 | R-3 IMPL slip +20h |
| LG-X baseline 仍未 IMPL（CLAUDE.md §三 P0-LG-1/2/3 仍 active）| 高 | R-4 必後 baseline；不可繞 | R-4 IMPL slip 至 baseline 完 |
| W-AUDIT-9 T3 與 W-AUDIT-3b 衝突未解 | 中 | per fix plan v2 PM push back 1，W-AUDIT-3b 必先 | R-4 不受影響（R-4 不碰 ExecutorAgent shadow_mode）|
| GUI tab 13→16 累加破 CLAUDE.md §五 mental model | 中 | A3 v2 NEW-7/8 已建議擴展；本 plan + ADR 同次 commit 補 | 漸進 reframe；CLAUDE.md §五 隨 wave land 更新 |

---

## §9 IMPL Resource Estimate

### 9.1 Person-day per R（spec 級 estimate）

| R | 本 plan estimate | spec doc estimate | 差異 |
|---|---:|---:|---|
| R-1 | 40 person-day | 40 person-day（W-AUDIT-8a §6.1）| 一致 |
| R-2 | 12 person-day | 12 person-day（W-AUDIT-8b §3）| 一致 |
| R-3 | 26 person-day | 26 person-day（W-AUDIT-8c §3）| 一致 |
| R-4 | 24 person-day | 24 person-day（W-AUDIT-8d §3）| 一致 |
| R-5 | 20 person-day | 20 person-day（W-AUDIT-8e §3）| 一致 |
| **總計** | **122 person-day** | | |

**注**：fix plan v2 §5 Track A 估算 ~270-330 person-day 是含**整個** Track A（含 future alpha source candidate IMPL W-AUDIT-8b/c/d 在 fix plan v2 schema 內）；本 plan 只 cover R-1..R-5 IMPL（122 person-day），future candidates 是另計。

### 9.2 Sprint distribution（並行最樂觀）

| Sprint | Active sub-tasks | 並行 sub-agent count |
|---|---|---:|
| N+0 | R-1 Phase A + R-5 T1/T2/T3/T4/T7 | 8-10 |
| N+1 | R-1 Phase B + R-2 T1/T2/T5 + R-5 T8/T9 | 10-12 |
| N+2 | R-1 Phase C + R-2 T3/T4 + R-3 T1/T2/T3/T4 + R-5 T5/T6 | 12-14 |
| N+3 | R-1 Phase D + R-2 T6/T7 + R-3 T5/T6/T7/T8 + R-5 T10/T11 | 12-14 |
| N+4 | R-1 7d replay + R-3 T9/T10 | 6-8 |
| N+5 | R-1 完成 / R-3 完成 | 2-4 |
| N+6 | （等 LG baseline）| 0-2 |
| N+7-N+10 | R-4 全 sub-task | 6-10 |

**並行峰值**：~14 sub-agent（Sprint N+2/N+3）

---

## §10 PM 接收後 5 步動作

1. **PM Sign-off** ADR-0021 升 Accepted（已完成於 commit 同次）
2. **TODO.md v18 dispatch table 同步**：W-AUDIT-8b/8c/8d/8e/8f 對應 wave 編號 alignment
3. **派 R-5 T1/T2/T3/T4/T7 並行**（即刻可開，無 prerequisite）
4. **派 R-1 Phase A IMPL**（已 SPEC PHASE，IMPL 接續）
5. **W-AUDIT-4b operator action 跟進**（R-3 unblock 前提）+ **LG-1..LG-5 baseline operator action 跟進**（R-4 unblock 前提）

---

## §11 結語

ADR-0021 R-1..R-5 **不是「修 5 個 TA 策略」也不是「重寫 88 finding patch」**：是把架構從 **TA-only 高速公路 + 風控 forcing function only** 升級為 **多 alpha source 並行 highway + alpha-side governance forcing function**。

R-1（Alpha Surface Foundation）+ R-3（Hypothesis Pipeline）是 **alpha discovery 的真實 architectural primitive**。
R-2（Strategist scope expansion）+ R-4（Per-alpha-source live budget）是 **alpha governance 的 forcing function**。
R-5（Spec-as-Code）是 **整個治理層的 drift 防線**，不直接 produce alpha 但保 R-1..R-4 不退化。

**最早第一個 alpha-bearing live promotion**：取決於 W-AUDIT-4b（R-3 prerequisite）+ LG-1..LG-5 baseline（R-4 prerequisite）+ R-1..R-4 IMPL completion 三件齊備。**悲觀 8-12 weeks 後**（中位 6/30 ~ 7/15 supervised live 規劃帶之外，落在 6/15 之外的 alpha-source 級 promotion）。

如果 R-1 Phase A 在 Sprint N+0 PASS（trait 升級 + AlphaSurface struct + 5 策略 declare 0 行為變化），整個 Track A 可以漸進推進；如果 Phase A E2E byte-diff 不過或 lifetime 編譯爆炸 → R-1 spec 必須 redesign，後續 R-2..R-4 全 slip。

---

**報告路徑**：`srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--track_a_dispatch_plan.md`

**結論性報告同步至**：`srv/docs/CCAgentWorkSpace/Operator/`（PM 收到後處理）

`PA DESIGN DONE: report path: srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--track_a_dispatch_plan.md`
