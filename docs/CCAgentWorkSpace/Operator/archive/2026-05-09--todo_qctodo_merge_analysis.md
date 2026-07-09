# PA Merge Analysis — TODO.md (v18) ⇄ QCTODO.md → 統一 v19

**作者**：PA（Project Architect）
**日期**：2026-05-09
**性質**：Read-only merge 分析；PM 寫 merge code，本報告為派工分析依據
**輸入文件**：
- `srv/TODO.md` v18 / 573 行（13-agent v3 audit verification + DUAL-TRACK Track W + Track A）
- `srv/QCTODO.md` 327 行（4-agent loss audit dispatch + Sprint N+0..N+5 + 16 sign-off invariant）
- `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--full_dispatch_engineering_plan.md`（PA DAG + 11 invariant）
- `srv/docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-09--full_dispatch_business_chain_validation.md`（FA chain + 9 invariant）
**讀者**：PM（即派工依據）/ Operator（merge sign-off）
**操作邊界**：本報告純 read-only；不動 TODO.md / QCTODO.md / CLAUDE.md；merge code 由 PM 執行

---

## §0 Executive Summary（給 PM 250 字）

QCTODO 是 4-agent loss audit dispatch 的 6-sprint roadmap + 16 sign-off invariant，**設計上是 TODO v18 的順承擴張，不是替代**。TODO v18 已含 13 agent v3 verification 結果 + Track W (~92h, 7 wave) + Track A (~270-330h, 9 wave) + W-AUDIT-8a SPEC PHASE 接線，但**缺**：(1) Sprint-by-sprint capacity 規劃；(2) FA 業務鏈完整度 milestone（v3 63% → v5 85-89%）；(3) 16 sign-off invariant 完整列表；(4) Cross-Wave Conflict Resolution 4 條；(5) Day-by-Day dispatch plan；(6) D-02 Layer 2 manual SOP；(7) DSR multiple testing K -12 quantification；(8) FA push back 4 條治理記錄。**QCTODO 4 entry 與 TODO v18 重複**（Track W 收 v2 outstanding / Track A 8a/9 / W-AUDIT-6 mid-ground / Decision-2/3）；**5 entry 是 QCTODO 獨有 dispatch detail**（Sprint capacity / 16 invariant / Cross-Wave Conflict / Stage 2 abort gate / DSR K penalty）；**0 entry 衝突需重整**（兩者方向一致，QCTODO 細化 v18 已含框架）。Merge 後新統一 TODO v19 應為 v18 結構保留 + QCTODO 內容整合進 §3 (Active Dispatch Queue) / §4 (Sign-off Pre-flight) / §5 (Sprint Roadmap)，QCTODO archive 至 `docs/archive/2026-05-XX--qctodo_sprint_n0_n5_archive.md`，rm `srv/QCTODO.md`。預估新 TODO v19 ~700-750 行（v18 573 + ~150 sprint dispatch + invariant 細化 - 重疊）。

---

## §1 重複 wave/task identification — QCTODO entry vs TODO v18

逐條對照 QCTODO 中每個 entry，標：✅ 已存在於 TODO v18 / 🆕 QCTODO 獨有 / ⚠️ 衝突 / 📦 細化已含框架

### 1.1 A 群 — 3 候選新策略（A4-A/B/C → W-AUDIT-8b/c/d）

| QCTODO entry | TODO v18 對照 | Verdict | 證據 |
|---|---|---|---|
| **A4-C BTC→Alt Lead-Lag (8d)** Sprint N+1 spec → N+2 IMPL, 7 person-day | TODO v18 §`Reference DUAL-TRACK Wave Definitions` Track A `W-AUDIT-8d` row "R-3 Hypothesis Pipeline first-class" → ⚠️ **TODO v18 用錯 W-AUDIT-8d label**（v18 把 Hypothesis Pipeline 標 8d，QCTODO 把 8d 標 BTC→Alt Lead-Lag）| ⚠️ **labeling 衝突** | TODO v18 line 556 `W-AUDIT-8d` = R-3 Hypothesis Pipeline；QCTODO §2 §A 群 = `A4-C BTC→Alt Lead-Lag (W-AUDIT-8d)`。**衝突 verdict 取 QCTODO labeling**（QCTODO 是後 land 設計，TODO v18 line 556 wave 定義是中間草稿）|
| **A4-B Liquidation Cluster (8c)** Sprint N+2 spec → N+3 IMPL, 1.5 sprint, Rust hot-path | TODO v18 §`Reference DUAL-TRACK Wave Definitions` Track A `W-AUDIT-8c` row = "R-2 Strategist scope expansion (alpha-source orchestrator)" → ⚠️ **同 labeling 衝突** | ⚠️ **labeling 衝突** | TODO v18 line 555 `W-AUDIT-8c` = R-2 Strategist；QCTODO §A 群 `A4-B Liquidation Cluster (W-AUDIT-8c)`。**衝突 verdict 取 QCTODO labeling** |
| **A4-A Funding Skew Directional (8b)** Sprint N+3 spec → N+4 IMPL, 1 sprint | TODO v18 §`Reference DUAL-TRACK Wave Definitions` Track A `W-AUDIT-8b` row = "R-1 Alpha Surface IMPL" → ⚠️ **同 labeling 衝突** | ⚠️ **labeling 衝突** | TODO v18 line 554 `W-AUDIT-8b` = R-1 Alpha Surface IMPL；QCTODO `A4-A (W-AUDIT-8b)` = Funding Skew Directional。**衝突 verdict 取 QCTODO labeling**（QCTODO 經 PA dispatch plan §2.4 + FA §5 對齊）|
| **FA Stage-2 abort gate** | TODO v18 無 | 🆕 **新 governance gate** | QCTODO §A 群尾條：「A4-C 若 Stage 2 demo 14d gross < 0，整個 A 群 8b/c 必須重評，不可連續 IMPL B/A」— 必進 v19 sign-off invariant 14 |

**結論**：A 群 3 條 entry 全部與 TODO v18 wave label 衝突（v18 把 W-AUDIT-8b/c/d 三個 label 對應到 R-1/R-2/R-3 spec 而非 A4-A/B/C 候選策略）。QCTODO labeling 是後對齊正解，merge 時：
- v19 採 QCTODO labeling：8b=A4-A funding skew / 8c=A4-B liquidation cluster / 8d=A4-C BTC→Alt lead-lag
- 原 v18 R-1/R-2/R-3 改名為 8b/c/d 之外的新 label：建議 `W-AUDIT-8e (R-2 orchestrator)` / `8f (R-3 Hypothesis Pipeline)` / `8g (R-4 per-alpha-source live promotion)` / `8a (R-1 Alpha Surface Foundation, 已存在 TODO v18 line 552)` 保持
- 為避免任何 cross-document 引用斷裂，v19 結構必含 **Wave Label Reconciliation table** explicit 重命名清單

### 1.2 B 群 — ML Pipeline 三斷層（A5-M1/M2/M3）

| QCTODO entry | TODO v18 對照 | Verdict | 證據 |
|---|---|---|---|
| **B-M1** decision_features producer 改 intent-only emit + decision_features_evaluations 拆表 V0XX migration, 5 person-day | TODO v18 line 394 `W-AUDIT-4` partial PARTIAL "remaining functional work: ... true INSERT/writer decisions for retained-but-empty tables" + line 422 `P2-AUDIT-VERIFY-3` "W-AUDIT-4 dead schema 真實 fix" | 📦 **TODO v18 有框架，QCTODO 細化** | TODO v18 標 W-AUDIT-4 PARTIAL 等待「true source/writer decisions」；QCTODO B-M1 是該 decision 的 IMPL 派工。merge：v19 把 B-M1 列為 P0-V3 sub-task / 或 W-AUDIT-4b sub-task |
| **B-M2** Fill writer entry_context_id INSERT trigger, 0.5 sprint | TODO v18 無 explicit entry，但 line 394 W-AUDIT-4 "remaining functional work" 涵蓋 | 📦 **新 sub-task 細化** | QCTODO 是 PA report §2.5 dispatch；merge：v19 加 P0-V3-MIT-ROOT-CAUSE 之下 sub-task |
| **B-M3** Governance reject 寫 negative label + class weight handling, 1 sprint | TODO v18 無 explicit entry | 📦 **新 sub-task 細化** | 同 B-M2；merge：v19 加 W-AUDIT-4b 子項 |
| **FA Push back: 6 表 INSERT path 必串行 IMPL** | TODO v18 無 | 🆕 **新 schema 順序治理** | QCTODO §B 群尾條：「feature_baselines first → mlde_edge_training_rows → scorer_predictions → 3 advisor 並行；不可 E1×4 全並行」— 必進 v19 sign-off invariant 5 |

**結論**：B 群 3 條全是 TODO v18 W-AUDIT-4 PARTIAL 標籤下「remaining functional work」的 IMPL 派工細化，merge 時改為 W-AUDIT-4b 三 sub-task：
- W-AUDIT-4b-M1 = decision_features producer 改 intent-only emit
- W-AUDIT-4b-M2 = entry_context_id INSERT trigger
- W-AUDIT-4b-M3 = negative label + class_weight
- 並把 6 表 INSERT path 串行依賴 invariant 加進 §4 sign-off pre-flight

### 1.3 C 群 — Promotion Gate + Dormant Unlock

| QCTODO entry | TODO v18 對照 | Verdict | 證據 |
|---|---|---|---|
| **C-A6** DSR/PBO/CPCV evidence pipeline 自動化 + trial_sharpes 持久化（V079 已 land）, 2 person-day | TODO v18 line 371 `P0-V3-DSR-PBO-EVIDENCE-CRON` "SOURCE/TEST CLOSED 2026-05-09; RUNTIME PENDING" + line 565 `P0-V3-V079-NOT-APPLIED` ACTIVE | ✅ **已存在 TODO v18 P0 entry** | merge：v19 把 P0-V3-DSR-PBO-EVIDENCE-CRON + P0-V3-V079-NOT-APPLIED 拉進 Sprint N+0 派工，加 owner + ETA = N+0 W2 |
| **C-D-05-wire** set_promotion_pipeline() singleton init, 0.5 person-day | TODO v18 無 explicit entry，但隱含於 W-AUDIT-6 SOURCE/TEST CLOSED 後的 wire-up 工作 | 📦 **新 sub-task 細化** | merge：v19 加 W-AUDIT-6c runtime apply 之下 sub-task |
| **C-D-02** Layer 2 manual 7d 試運行 (operator 自決) | TODO v18 line 419 `P2-AUDIT-LAYER2-7c` "DONE-BY-DECISION — autonomous Layer2 loop sunset" + ADR-0020 manual+supervisor only | ✅ **已存在 TODO v18 governance decision** | QCTODO §6 D-02 SOP 是 ADR-0020 manual mode 的 operator-level operating procedure，不是新 TODO entry。merge：v19 §6 加 D-02 SOP（從 QCTODO + FA report §2 整合），標 operator 自決，不混入 dispatch queue |

### 1.4 D 群 — Architectural Wave

| QCTODO entry | TODO v18 對照 | Verdict | 證據 |
|---|---|---|---|
| **W-AUDIT-8a Alpha Surface Foundation Phase A→D** Sprint N+0 → N+2, ~40 person-day | TODO v18 line 342 (Dispatch Order Rank 15) `W-AUDIT-8a Alpha Surface Foundation` SPEC PHASE 2026-05-09 / Phase A target Sprint N+0 (~40 person-day, 4 phases) | ✅ **完全已存在 TODO v18** | merge：v19 把 line 342 內容保留 + 加 QCTODO Phase A→D 細部 dispatch（PA report §2.1）|
| **W-AUDIT-9 Graduated Canary Foundation T1-T7** Sprint N+0 IMPL, 1.5-2 sprint | TODO v18 line 553 Track A `W-AUDIT-9` = "Graduated Canary Foundation (5-stage canary, supersedes AMD-02 §2 binary fail-closed)" operator 已啟動（AMD-2026-05-09-03 起）| ✅ **已存在 TODO v18 Track A wave** | merge：v19 把 W-AUDIT-9 wave 從 line 553 一句話擴張為 7 sub-task DAG（PA report §2.2）|
| **W-AUDIT-8e (R-2)** Strategist Alpha Source Orchestrator | TODO v18 line 555 `W-AUDIT-8c` = R-2 → ⚠️ **labeling 衝突如 §1.1** | ⚠️ **labeling 衝突重命名** | merge：v19 W-AUDIT-8c → 重命名為 W-AUDIT-8e（R-2 orchestrator） |
| **W-AUDIT-8f (R-3)** Hypothesis Pipeline + W-AUDIT-4 ML 6 dead schema 併入 | TODO v18 line 556 `W-AUDIT-8d` = R-3 → ⚠️ **labeling 衝突** | ⚠️ **labeling 衝突重命名** | merge：v19 W-AUDIT-8d → 重命名為 W-AUDIT-8f（R-3 Hypothesis Pipeline + W-AUDIT-4 併入）|
| **W-AUDIT-8g (R-4)** Per-alpha-source Live Promotion Gate | TODO v18 line 557 `W-AUDIT-8e` = R-4 → ⚠️ **labeling 衝突** | ⚠️ **labeling 衝突重命名** | merge：v19 W-AUDIT-8e → 重命名為 W-AUDIT-8g（R-4 per-alpha-source live promotion gate）|
| **W-AUDIT-10 (R-5)** Spec-as-Code + Module Lifecycle SM | TODO v18 line 558 `W-AUDIT-8f` = R-5 Spec-as-Code → ⚠️ **labeling 衝突** | ⚠️ **labeling 衝突重命名** | merge：v19 W-AUDIT-8f → 重命名為 W-AUDIT-10（R-5）|
| **FA Push back D-08e promote** Sprint N+4（與 Track W 收尾並行）| TODO v18 無 explicit promote 時序 | 🆕 **新 sprint 排程 fine-tune** | FA report §6 critique 4；merge：v19 加 §5 Sprint Roadmap 對應 row |

### 1.5 W-AUDIT-6 Mid-Ground 保 6 / 砍 6

| QCTODO entry | TODO v18 對照 | Verdict | 證據 |
|---|---|---|---|
| **保 6 子項清單** | TODO v18 line 340 `W-AUDIT-6` SOURCE/TEST CLOSED 2026-05-09（DSR/PBO + Kelly + funding_arb + per_trade_risk + ma_crossover R:R + bb_breakout 5m + W-AUDIT-6c VaR/CVaR/EVT 全 closed） | ⚠️ **狀態衝突 / 兩個來源** | TODO v18 已標 W-AUDIT-6 SOURCE/TEST CLOSED；QCTODO §保 6 是 PA report §2.3 提出再做 6 子項的 mid-ground。**這是兩個不同 wave**：v18 W-AUDIT-6 = 之前 closed source/test work；QCTODO 保 6 = mid-ground 新 batch 加 audit + sweep + Kelly tier config 化。merge：v19 把 v18 line 340 W-AUDIT-6 status 維持「之前已 source/test closed」+ 新加 `W-AUDIT-6d` (mid-ground 6 保子項)entry |
| **砍 6 子項清單（E2 grep blacklist）** | TODO v18 無 explicit grep blacklist | 🆕 **新 governance E2 check** | QCTODO §砍 6：「E2 grep blacklist 命中即 reject merge」— ma_crossover 5m 反向 / bb_breakout Donchian 5m sweep / grid expansion / funding_arb v3 retry / strategy_params hardcoded / cost_gate per-strategy。merge：v19 加 §3 Dispatch Rules section 「W-AUDIT-6d mid-ground 砍 6 grep blacklist」 |
| **DSR K -12 量化結論** | TODO v18 無 | 🆕 **新治理量化記錄** | QCTODO 「保 6 K +3 trial / 砍 6 K -15 trial / Net K -12」+「mu_0 從 ~2.83 降至 ~2.27」。merge：v19 加 §4 sign-off invariant 16 |

**結論**：W-AUDIT-6 是 v18 已 closed wave；QCTODO 提的「保 6 / 砍 6」是 mid-ground 新 wave，名 W-AUDIT-6d。**這是新 wave 不是衝突**，但 v19 必清楚標 W-AUDIT-6 (closed) vs W-AUDIT-6d (mid-ground active)。

### 1.6 E 群 — Operator-decide-only（已拍板）

| QCTODO entry | TODO v18 對照 | Verdict | 證據 |
|---|---|---|---|
| **A2-followup G3-08 OPENCLAW_H_STATE_GATEWAY=1 enable ✅ DONE 2026-05-09 17:27 UTC** | TODO v18 line 414 `P2-STRUCT-1` "HStateCache + CostEdgeAdvisor late-inject slot enablement" 仍 ACTIVE | ⚠️ **狀態 outdated** | TODO v18 P2-STRUCT-1 還沒標 DONE，但 QCTODO 已驗證 cost_edge_advisor daemon spawned（commit dddc5dc1）。merge：v19 把 P2-STRUCT-1 status 改 DONE 2026-05-09 17:27 UTC + commit dddc5dc1 evidence |
| **Decision-2 W-AUDIT-6 mid-ground confirmed 保 6 / 砍 6** | TODO v18 line 314-317 `P0-DECISION-AUDIT-2` "DONE 2026-05-09 — shadow_mode TOML × 3 設計意圖鎖定" | 📦 **TODO v18 有 P0-DECISION-AUDIT-2 但不是同一 decision** | TODO v18 P0-DECISION-AUDIT-2 處理的是 shadow_mode TOML × 3 設計意圖鎖定（FA push back #2），不是 W-AUDIT-6 mid-ground 保 6 / 砍 6 verdict。**這是兩個不同 decision**，merge：v19 加 P0-DECISION-AUDIT-6 = W-AUDIT-6 mid-ground verdict (operator confirmed) |
| **Decision-3 W-AUDIT-4 併入 R-3 (W-AUDIT-8f) confirmed** | TODO v18 line 363 `P0-DECISION-AUDIT-4` "DONE 2026-05-09 — 5 策略 verdict 採納" | 📦 **TODO v18 有 P0-DECISION-AUDIT-4 但不是同一 decision** | TODO v18 P0-DECISION-AUDIT-4 處理的是 5 策略 verdict（grid CONDITIONAL ORDIUSDT 等），不是 W-AUDIT-4 ML 基座併入 W-AUDIT-8f Hypothesis Pipeline。merge：v19 加 P0-DECISION-AUDIT-7 = W-AUDIT-4 併入 R-3 confirmed |

### 1.7 16 Sign-off Invariant（PA 11 + FA 9 deduplicate）

QCTODO §5 列 16 個 + 4 個追蹤項 = 20 條 invariant。逐條對照 TODO v18：

| Invariant # | 內容摘要 | TODO v18 對照 | Verdict |
|---|---|---|---|
| 1 | W-AUDIT-9 7 sub-task 全 land + [58] PASS | TODO v18 無 sign-off invariant section | 🆕 |
| 2 | W-AUDIT-8a Phase A trait 升級 land + 5 策略 byte-identical replay PASS | 同上 | 🆕 |
| 3 | W-AUDIT-6 mid-ground 6 保 land + 砍 6 grep blacklist 0 命中 | 同上 | 🆕 |
| 4 | W-AUDIT-9 Stage 1 cohort active + 7d wall-clock 觀察未提前升 | 同上 | 🆕 |
| 5 | W-AUDIT-4b 6 表 INSERT path 已串行 IMPL | 同上 | 🆕 |
| 6 | DOC-08 §12 9 條安全不變量未違反 | TODO v18 反覆引用 DOC-08 §12 但無 sign-off check | 🆕 |
| 7 | live boundary 5-gate 在 stage active 期間未繞 | TODO v18 line 28-37 CLAUDE.md §四 引用 | 🆕 |
| 8 | §二 16 根原則合規（especially 1/4/5/6/9） | TODO v18 反覆引用 §二 16 原則 | 🆕 |
| 9 | shadow_mode_provider exception path fail-closed Stage 0 (不是 Stage 1) | TODO v18 line 393 P1-AUDIT-RUNTIME-3 "F-01 source/test removed unconditional lambda:True" | 📦 已含 IMPL invariant，無 sign-off check |
| 10 | W-AUDIT-9 Stage 0 binary fail-closed 不變式保留 | TODO v18 line 27 "Per AMD-2026-05-09-03 ... live default = Stage 0 (binary fail-closed unchanged)" | 📦 已含 doc，無 sign-off check |
| 11 | canary_stage_log.decision_lease_id for manual_promote PG NOT NULL 強制 | TODO v18 無 | 🆕 |
| 12 | healthcheck [58] 對 SM-04 ≥ L3 escalate 必 hard FAIL → stage = 0 rollback | TODO v18 無 [58] healthcheck entry | 🆕 |
| 13 | A 群 3 新策略 IMPL 後 declared_alpha_sources() 與真實邏輯對齊 | TODO v18 無 | 🆕 |
| 14 | W-AUDIT-8b/c/d sequence 必含 Stage 2 abort gate | TODO v18 無 | 🆕 |
| 15 | D-02 Layer 2 manual SOP 不違反 ADR-0020 | TODO v18 line 419 P2-AUDIT-LAYER2-7c referencing ADR-0020 | 📦 已含 ADR-0020 治理，無 sign-off check |
| 16 | W-AUDIT-6 mid-ground 砍 6 polishing 的 K -12 trial DSR penalty 量化結論記入 sign-off report | TODO v18 無 | 🆕 |
| 17 (追) | F-08 5 ML cron crontab 安裝 + 24h 真 fire 驗 | TODO v18 line 565 `P0-V3-CRON-NOT-INSTALLED` ACTIVE | 📦 已存在但無 sign-off invariant 形式 |
| 18 (追) | v2-NEW-1 strategist cap 30%→50% 補 ADR-0021 | TODO v18 line 566 `P0-V3-ADR-0021-ARCH-04` ACTIVE | 📦 已存在但無 sign-off invariant 形式 |
| 19 (追) | 6 表 0 INSERT 18 天無變動 owner + ETA | TODO v18 無明確 escalation P1 entry | 🆕 |
| 20 (追) | W-AUDIT-3b runtime smoke 已從 Linux 驗 | TODO v18 line 540 Track W `W-AUDIT-3b` ETA sprint 1 但無 verification gate | 📦 已存在 wave，無 sign-off check |

**結論**：20 條 invariant 中 11 條 🆕 全新；9 條 📦 細化或 sign-off form 不存在。merge：v19 必加 **§4 Sign-off Pre-flight Checklist** 完整列 16 條 + 4 追蹤條（QCTODO §5 整原文搬入 + 對齊現有 TODO v18 entries 的 cross-ref）。

### 1.8 6-Sprint Roadmap N+0..N+5

QCTODO §1 列完整 sprint capacity + critical path + business chain milestone：

| Sprint | QCTODO content | TODO v18 對照 | Verdict |
|---|---|---|---|
| N+0 W1-W2 | 5 active + 1 stand-by, FOUNDATION HEAVY | TODO v18 無 sprint-by-sprint 規劃 | 🆕 |
| N+1 W3-W4 | 4/6, ALPHA SURFACE PANEL WIRING | 同上 | 🆕 |
| N+2 W5-W6 | 5 active + 1 stand-by, A4-C IMPL + 8a Phase D + Stage 2 demo | 同上 | 🆕 |
| N+3 W7-W8 | 4/6, A4-B IMPL + R-2 spec + Stage 3 demo full | 同上 | 🆕 |
| N+4 W9-W10 | 4/6, R-3 spec + A4-A IMPL + 8e IMPL | 同上 | 🆕 |
| N+5 W11-W12 | 5 active + 1 stand-by, R-3 IMPL + R-4 spec + first per-alpha-source supervised live | 同上 | 🆕 |

**最早 supervised live 規劃帶**：QCTODO 給 4 個概率帶（6/15 30% / 6/30 40% / 7/15 25% / 8/15 5%）。TODO v18 line 449 只有 "2026-06-15 Supervised live target (悲觀帶)" 一句話。

**Stand-by 啟用條件**：QCTODO §1 列 5 條（T3 翻車 / Phase A byte-diff fail / mid-G 與 Phase A deadline / E1 health incident / 平時跑 W-AUDIT-2/-5）— TODO v18 無 stand-by 概念。

**結論**：6-sprint roadmap 全 🆕 新內容，merge：v19 加 **§5 Sprint Roadmap N+0..N+5** section（QCTODO §1 整原文搬入）。

### 1.9 Cross-Wave Conflict Resolution

QCTODO §3 列 4 條 cross-wave conflict：

| 衝突 # | QCTODO content | TODO v18 對照 | Verdict |
|---|---|---|---|
| **#1** 8a Phase A migration ↔ W-AUDIT-6 mid-ground 5 策略改動同 file overlap → 序列化（先 6 mid-G 再 8a Phase A） | TODO v18 無 cross-wave conflict section | 🆕 |
| **#2** W-AUDIT-9 T3 shadow_mode_provider stage-aware ↔ ExecutorAgent shadow_mode 接線 → T3 land 後 stage-aware reload | 同上 | 🆕 |
| **#3** W-AUDIT-8a Phase B+C ↔ W-AUDIT-5 性能 wave 同 tick_pipeline/mod.rs → Phase B+C 並行於 N+1，W-AUDIT-5 catch-up 在 N+1 reserved slot | 同上 | 🆕 |
| **#4** A 群 3 新策略 ↔ W-AUDIT-9 Stage 1 cohort 選擇 → A4-C 用 Stage 1 paper cohort 入場驗 stage 機制 | 同上 | 🆕 |

**結論**：全 🆕，merge：v19 加 **§3 Active Dispatch Queue** 之下 sub-section "Cross-Wave Conflict Resolution"。

### 1.10 Risk Mitigation 表（PA §3.4 摘要）

QCTODO §7 列 5 條 risk + mitigation：

| Risk | TODO v18 對照 | Verdict |
|---|---|---|
| W-AUDIT-9 T3 stage-aware exception path 翻車 | 無 | 🆕 |
| W-AUDIT-8a Phase A byte-diff fail | 無 | 🆕 |
| W-AUDIT-6 mid-ground 與 8a Phase A 撞牆 | 無 | 🆕 |
| MIT V### Linux PG dry-run fail | TODO v18 line 380 reference CLAUDE.md §七 V055 但無 entry-level | 📦 已含 doc 引用但無 risk table |
| Stage 1/2 強行 promote | 無 | 🆕 |

**結論**：4 條 🆕 + 1 條 📦，merge：v19 加 **§6 Push Back / Risk** section（QCTODO §7 + FA push back 整合）。

---

## §2 TODO v18 既有 wave/task identification

對照 TODO v18 已有 wave / task / Reference section，分類為「保留進新 v19 / closed 可 archive / 與 QCTODO 對應 reconcile」：

### 2.1 Closed entries（不需進新 TODO，archive）

| TODO v18 entry | Status | Archive 去處 |
|---|---|---|
| W-A Executor fake-live runtime smoke | DONE 2026-05-07 | `docs/archive/2026-05-09--w_audit_verified_closed_archive_v3.md` |
| W-B Runtime decision-spine lineage wiring | DONE 2026-05-08 | 同上 |
| W-E OpenClaw read-only observability expansion | DONE 2026-05-07 | 同上 |
| P1-FAKE-1 / P1-OPENCLAW-3 / P1-OPENCLAW-6/7 / P1-AGENT-OBS-1 / P1-AGENT-RUNTIME-1 / P1-DATA-4 | DONE | 同上（merge tag 2026-05-09） |
| P0-DECISION-AUDIT-1..5 | DONE | 同上 |
| P0-NEW-ISSUE-1 LiveDemo auth restored | DONE 2026-05-09 | 同上 |
| P0-NEW-VULN-1/2 | DONE 2026-05-09 | 同上 |
| P0-AUDIT-NEW-LG-X-05 | DONE 2026-05-09 | 同上 |
| P0-V2-NEW-1/2/3 | DONE 2026-05-09 | 同上 |
| W-AUDIT-1 docs sync | DONE 2026-05-09 | 同上 |
| W-AUDIT-2 security IMPL | DONE 2026-05-09（V078 applied + lease_transitions 103 rows） | 同上 |
| W-AUDIT-6 SOURCE/TEST CLOSED 2026-05-09 | CLOSED | 不 archive，移到 `Reference 2026-05-09 v2/v3 verification` 索引 |
| W-AUDIT-7 4/5 critical close | CLOSED partial | 同上 |
| P2-MIG-1/2 / P2-SEC-1 / P2-REPLAY-1 / P2-PYDANTIC-1 / P2-RUST-1 / P2-AUDIT-VERIFY-1/2/5/6/7 / P2-AUDIT-VAR-6c / P2-AUDIT-LAYER2-7c | DONE | archive |

**結論**：~30 closed entries 可 archive 到 `docs/archive/2026-05-XX--todo_v18_closed_entries_archive.md`，新 v19 不背 closed entry 包袱。

### 2.2 ACTIVE / PARTIAL entries（必進新 TODO v19）

| TODO v18 entry | Status | 新 v19 建議 |
|---|---|---|
| `W-C` New MAG-082 Stage 2 evidence window | ACTIVE 2026-05-08 | v19 §3 Active Dispatch Queue 第一條（保 v18 status row）|
| `W-D` MAG-083 / MAG-084 | BLOCKED after W-C PASS | 同上 |
| `W-F` Edge/data quality + Live Gate foundation | ACTIVE | 同上 |
| `W-G` Proposal/approval/mobile relay | BACKEND FOUNDATION DONE | 保 v18 status |
| `W-AUDIT-3` ExecutorAgent fake-live (mount W-A/W-B) | PARTIAL 2026-05-09 | v19 §3 + ref Track W `W-AUDIT-3b` runtime smoke |
| `W-AUDIT-4` ML 基座 + dead schema (mount W-F-1) | PARTIAL 2026-05-09 | v19 §3 + 加 W-AUDIT-4b sub-tasks（QCTODO B-M1/M2/M3 + cron install + V079 apply）|
| `W-AUDIT-5` 性能/結構 (split 5a + 5b) | ACTIVE 2026-05-09 | v19 §3 保 5a remaining (F-20) + 5b deferred |
| `W-AUDIT-6` 策略 + DSR/PBO promotion gate | SOURCE/TEST CLOSED 2026-05-09 | v19 §3 加 W-AUDIT-6c runtime apply pending + 加新 W-AUDIT-6d mid-ground sub-tasks |
| `W-AUDIT-7` AI 棧 + GUI/UX 收口 | ACTIVE 2026-05-09 | v19 §3 保 status，remaining F-07 + F-cea-env |
| `W-AUDIT-8a` Alpha Surface Foundation (R-1) | SPEC PHASE 2026-05-09 / Phase A target Sprint N+0 | v19 §3 改 IMPL phase-by-phase（QCTODO §1 sprint mapping）|
| **P0 entries (12 條)**：P0-AGENT-1/2/3/4 / P0-EDGE-1 / P0-LG-1/2/3 / P0-OPS-1/2/3/4 / P0-V3-MIT-ROOT-CAUSE / P0-V3-V079-NOT-APPLIED / P0-V3-CRON-NOT-INSTALLED / P0-V3-PA-SPEC-FIX / P0-V3-ADR-0021-ARCH-04 / P0-V3-ENGINE-RESTART | ACTIVE | v19 §3 P0 table 全保 + 加 P0-V3-MIT-ROOT-CAUSE owner + ETA |
| **P1 entries**：P1-DATA-1/2/3 / P1-EDGE-1/2 / P1-REPLAY-1/2 / P1-LG-5 / P1-AUDIT-* | mixed | v19 §3 P1 table 保 + close 已 DONE 條目 |
| **P2 entries**：P2-LEASE-1 / P2-STRUCT-1（QCTODO 標 DONE 但 v18 標 ACTIVE）/ P2-STRUCT-2 / P2-AUDIT-* / P2-AUDIT-VERIFY-3/4 / P2-AUDIT-QC-STAND-ALONE | mixed | v19 §3 P2 table 保 + close P2-STRUCT-1 (G3-08 已 DONE 2026-05-09 17:27 UTC) |

### 2.3 與 QCTODO 對應 reconcile entries

| TODO v18 entry | QCTODO 對照 | Reconcile action |
|---|---|---|
| `W-AUDIT-3b` (Track W) | QCTODO §5 sign-off invariant 20 / FA chain Sprint N+0 | merge 後 v19 §3 Track W `W-AUDIT-3b` 條目 + 加 sign-off invariant link |
| `W-AUDIT-4b` (Track W) | QCTODO B 群 + FA business chain Sprint N+1 | merge 後 v19 §3 Track W `W-AUDIT-4b` 加 sub-tasks B-M1/M2/M3 + 串行依賴 |
| `W-AUDIT-6c` (Track W) | QCTODO 保 6 #4 portfolio VaR/CVaR/EVT promotion gate ✅ | 已 done in v18 |
| `W-AUDIT-6d` (新) | QCTODO 保 6（除 #5/#6 已 done）+ 砍 6 grep blacklist | 新 v19 §3 Track W `W-AUDIT-6d` mid-ground entry |
| `W-AUDIT-7c` (Track W) | QCTODO 無對應 | 保 v18 entry |
| `W-AUDIT-1d` (Track W) | QCTODO 無對應 | 保 v18 entry |
| `W-AUDIT-5b` (Track W) | QCTODO 無對應 | 保 v18 entry（FA chain Sprint N+3 提及） |
| `W-AUDIT-8a/b/c/d/e/f/g` (Track A) | QCTODO §A 群 + §D 群 + §1 sprint roadmap | merge 後 labeling reconcile（§1.1, §1.4） |
| `W-AUDIT-9` (Track A) | QCTODO §1 sprint roadmap N+0 critical path + §5 invariant 1 | v19 §3 Track A `W-AUDIT-9` 加 7 sub-task DAG |
| `W-AUDIT-10` (R-5 重命名) | QCTODO §D 群 W-AUDIT-10 | merge 後 v19 §3 Track A `W-AUDIT-10` 取代 v18 `W-AUDIT-8f` |
| `W-ARCH-3` (Track A) | QCTODO 無對應 | 保 v18 entry |

---

## §3 Gap Analysis

### 3.1 TODO v18 有但 QCTODO 沒（保留 vs archive）

| TODO v18 entry | QCTODO mention? | Action |
|---|---|---|
| W-A/W-B/W-C/W-D/W-E/W-F/W-G (Wave Rank 1-7) | QCTODO 不重複（focus 在 Track W/A）| 保 v19 §3，標 DONE 為 archive 候選 |
| W-AUDIT-1/2 source-closed | QCTODO 不重複 | DONE，archive |
| W-AUDIT-3/4/5/6/7 partial/closed | QCTODO 部分對應（4/6 提到，3/5/7 不提）| 保 v19 §3 對應 sub-task，PARTIAL 條目併入 W-AUDIT-3b/4b/6d |
| **P0-AGENT-1..4** (W-C 24h MAG-082/083/084 chain) | QCTODO 不重複（沒提 W-C）| 保 v19 §3 P0 table（critical baseline）|
| **P0-EDGE-1** (Edge net-positive decision) | QCTODO §1 sprint roadmap 提「first per-alpha-source supervised live」隱含解 P0-EDGE-1 雞蛋死循環 | 保 v19 §3 P0 + 加 cross-ref Sprint N+5 milestone |
| **P0-LG-1/2/3** (H0 production caller / pricing binding / supervised-live state machine) | QCTODO 不重複 | 保 v19 §3 P0 |
| **P0-OPS-1..4** (HTTPS / cred rotation / legal / runbook) | QCTODO 不重複 | 保 v19 §3 P0 |
| **P0-V3-* 6 條 ACTIVE** | QCTODO §2 C 群 + §3 conflict 部分對應 | 保 v19 §3 P0，加 sprint owner + ETA |
| **P1 / P2 entries 大部分** | QCTODO 不重複 | 保 v19 §3 P1/P2 |
| **Schedule table** | QCTODO §1 sprint roadmap 取代 sprint-level 規劃；TODO v18 schedule table 有 calendar dates | 保 v19 §7 Schedule（calendar dates，與 sprint roadmap 並存）|
| **Dispatch Rules** | QCTODO 無 | 保 v19 §8 Dispatch Rules（v18 line 454-466 整原文）|
| **Handoff Checks** | QCTODO 無 | 保 v19 §8 Handoff Checks |
| **Reference sections (2026-05-08 / 2026-05-09 / v2 / v3)** | QCTODO §8 補新 reference | 保 v19 §9 References，加 QCTODO 提到的 reports |

### 3.2 QCTODO 有但 TODO v18 沒（merge 進新 TODO 哪個 section）

| QCTODO 獨有 entry | merge 進 v19 哪個 section |
|---|---|
| Sprint N+0..N+5 6-sprint roadmap | §5 Sprint Roadmap（新 section） |
| 5 active + 1 stand-by capacity 規劃 + stand-by 啟用條件 | §5 Sprint Roadmap |
| 16 sign-off invariant + 4 追蹤條 | §4 Sign-off Pre-flight Checklist（新 section） |
| Cross-Wave Conflict Resolution 4 條 | §3 Active Dispatch Queue / Cross-Wave Conflict（新 sub-section） |
| Day 0-3 Dispatch by E1 slot | §3 Active Dispatch Queue / Day-by-Day（新 sub-section） |
| Day 3-5 / 5-7 / 12-14 / 14-15 review chain | 同上 |
| D-02 Layer 2 manual 7d SOP | §6 D-02 SOP（新 section） |
| W-AUDIT-6 mid-ground 保 6 / 砍 6 + 砍 6 grep blacklist | §3 Active Dispatch Queue 加 W-AUDIT-6d entry + §3 Dispatch Rules 加 grep blacklist |
| DSR K -12 量化結論 | §4 sign-off invariant 16 |
| FA Push back 4 條治理記錄（Track W vs Track A 預算 / D-02 SOP 上限 / A/B/C 預期 / 砍 6 是 right move） | §6 Push Back / Risk |
| Risk Mitigation 表 5 條 | §6 Push Back / Risk |
| FA Stage-2 abort gate（A4-C 14d 後 fail 整 A 群 8b/c 重評）| §4 sign-off invariant 14 |
| QCTODO 維護規則 | v19 不需要（v19 取代 QCTODO） |
| **PM Sign-off Banner with operator confirmation** | v19 §0 banner 加（v19 是 merge 後成果，不是 sign-off 報告） |

### 3.3 兩者都有但 framing 不同（採哪個）

| 議題 | TODO v18 framing | QCTODO framing | merge verdict |
|---|---|---|---|
| **W-AUDIT-8b/c/d wave label** | R-1 / R-2 / R-3 (line 554-556) | A4-A / A4-B / A4-C 候選新策略 | 取 QCTODO labeling（PA dispatch plan §2.4 + FA report §5 兩端對齊） |
| **W-AUDIT-6 status** | SOURCE/TEST CLOSED 2026-05-09（line 340） | mid-ground 保 6 / 砍 6 還沒做 | **兩個是不同 wave**：v19 保 v18 W-AUDIT-6 closed status + 加新 W-AUDIT-6d mid-ground entry |
| **A2-followup G3-08 status** | line 414 P2-STRUCT-1 ACTIVE | DONE 2026-05-09 17:27 UTC | 取 QCTODO（已 verified daemon spawned）|
| **First per-alpha-source supervised live ETA** | line 449 "2026-06-15 Supervised live target (悲觀帶)" | Sprint N+5 W11-W12（~12 weeks event-driven）+ 4 概率帶（30/40/25/5） | 取 QCTODO 概率帶 framing（更準確 + event-driven）|
| **Layer 2 自主推理循環** | line 419 P2-AUDIT-LAYER2-7c "DONE-BY-DECISION — autonomous Layer2 loop sunset" | §6 D-02 manual 7d SOP（不違反 ADR-0020）| 兩者一致；merge：v19 §6 加 SOP 詳細 |
| **DSR/PBO/CSCV pipeline** | line 371 P0-V3-DSR-PBO-EVIDENCE-CRON SOURCE/TEST CLOSED 2026-05-09; RUNTIME PENDING | §C 群 C-A6 Sprint N+0 IMPL 2 person-day | 取 QCTODO IMPL 派工（owner + ETA） |
| **5 active vs 6 並行 capacity** | TODO v18 無 | 5 active + 1 stand-by | 取 QCTODO（operator 拍板 (a)）|

---

## §4 Unified TODO Outline 建議（v19）

給 PM 一份建議的統一 TODO 結構。預估 ~700-750 行。

### §0 Banner

```
# 玄衡 TODO — Active Dispatch Queue

Version: v19
Date: 2026-05-XX
Status: TODO v18 (13-agent v3 verification + DUAL-TRACK Track W/A) merge QCTODO (4-agent loss audit dispatch + Sprint N+0..N+5)
        operator 拍板 (a) 提供 stand-by E1，Sprint N+0 capacity = 5 active + 1 stand-by
        QCTODO archived to docs/archive/2026-05-XX--qctodo_sprint_n0_n5_archive.md
PM Sign-off: Claude Opus 4.7 (Conductor, 主會話 PM) — 2026-05-XX UTC
Operator Sign-off: cloud@ncyu.me — 2026-05-XX

This file is the active work queue only. Historical closures, stale observation
tables, and superseded OpenClaw/Gateway assumptions are archived in:
- docs/archive/2026-05-07--todo_v12_agent_openclaw_replan_archive.md
- docs/archive/2026-05-09--w_audit_verified_closed_archive.md
- docs/archive/2026-05-09--w_audit_verified_closed_archive_v2.md
- docs/archive/2026-05-09--w_audit_verified_closed_archive_v3.md
- docs/archive/2026-05-XX--qctodo_sprint_n0_n5_archive.md (新)
- docs/archive/2026-05-XX--todo_v18_closed_entries_archive.md (新)
```

### §1 Architecture Boundary

沿用 v18 line 11-37 整段（OpenClaw Gateway / Bybit only / Rust authority / Local 5-Agent / Scanner always-on / MessageBus legacy / Replay advisory）。

### §2 Latest State

merge v18 line 39-194 既有 ACTIVE state + QCTODO §1 milestone：

- v18 既有 Latest State（不變動歷史里程碑陳述）
- 加 **QCTODO milestone**：4-agent loss audit dispatch closure（PM Sign-off banner from QCTODO §9）
- 加 **A2-followup G3-08 ✅ DONE 2026-05-09 17:27 UTC commit dddc5dc1**（QCTODO §1）
- 加 **PA Push Back resolved (a) stand-by E1 採納**（QCTODO §7 + §9）

### §3 Active Dispatch Queue

合併 v18 Dispatch Order (line 322-342) + DUAL-TRACK Wave Definitions (line 538-558) + QCTODO §2-§4：

#### 3.1 Wave Label Reconciliation

```
v18 → v19 重命名表：
- W-AUDIT-8b (R-1 Alpha Surface IMPL) → W-AUDIT-8b (A4-A Funding Skew Directional)
                                       ；R-1 Alpha Surface Foundation 是 W-AUDIT-8a 整 wave，
                                       無需獨立 IMPL row（已 SPEC PHASE 2026-05-09）
- W-AUDIT-8c (R-2 Strategist scope expansion) → W-AUDIT-8c (A4-B Liquidation Cluster Reaction)
                                              + 新 W-AUDIT-8e (R-2 Strategist Alpha Source Orchestrator)
- W-AUDIT-8d (R-3 Hypothesis Pipeline) → W-AUDIT-8d (A4-C BTC→Alt Lead-Lag)
                                       + 新 W-AUDIT-8f (R-3 Hypothesis Pipeline + W-AUDIT-4 併入)
- W-AUDIT-8e (R-4 Per-alpha-source supervised promotion) → 新 W-AUDIT-8g (R-4)
- W-AUDIT-8f (R-5 Spec-as-Code) → 新 W-AUDIT-10 (R-5)
- 新 W-AUDIT-6d (mid-ground 保 6 / 砍 6) — 新 sub-wave，v18 W-AUDIT-6 SOURCE/TEST CLOSED 不變
```

#### 3.2 Dispatch Order Table

| Rank | Wave | Owner Chain | Target | Exit Criteria |
|---:|---|---|---|---|
| 1-7 | (沿用 v18 Rank 1-7：W-A..W-G)（W-A/W-B/W-E DONE archive 候選；W-C/W-D/W-F/W-G ACTIVE/BLOCKED）| | | |
| 8 | `W-AUDIT-1` Docs sync | DONE 2026-05-09 archive | | |
| 9 | `W-AUDIT-2` Security IMPL | DONE 2026-05-09 archive | | |
| 10 | `W-AUDIT-3` ExecutorAgent fake-live | PARTIAL（並行 Track W `W-AUDIT-3b`） | | |
| 11 | `W-AUDIT-4` ML 基座 + dead schema | PARTIAL（並行 Track W `W-AUDIT-4b`） | | |
| 12 | `W-AUDIT-5` 性能/結構 | ACTIVE remaining 5a/5b | | |
| 13 | `W-AUDIT-6` 策略 + DSR/PBO promotion gate | SOURCE/TEST CLOSED（並行 Track W `W-AUDIT-6c/6d`）| | |
| 14 | `W-AUDIT-7` AI + GUI/UX | ACTIVE remaining F-07 + F-cea-env | | |
| 15 | `W-AUDIT-8a` Alpha Surface Foundation (R-1) | SPEC PHASE → IMPL Phase A→D Sprint N+0..N+2（從 QCTODO §1 + PA dispatch §2.1 細化）| | |

#### 3.3 Track W Wave Definitions（沿用 v18 + Sprint slot）

| Wave | 內容 | Sprint slot | ETA |
|---|---|---|---|
| `W-AUDIT-3b` | ExecutorAgent runtime smoke + fail-closed metrics（必先 land 避 W-AUDIT-9 衝突） | N+0 | sprint 1 |
| `W-AUDIT-4b` | V079 DB apply + cron install + label_close_tag NULL writer fix + B-M1/M2/M3 串行 IMPL | N+0..N+1 | sprint 1-2 |
| `W-AUDIT-6c` | portfolio tail risk gate runtime apply | N+2 | sprint 2 |
| `W-AUDIT-6d` (新) | 5 策略 mid-ground 保 6 子項（ma_crossover audit / bb_breakout 5m sweep / bb_reversion ma pair / Kelly tier config / DSR/PBO done / funding_arb retire done）+ 砍 6 grep blacklist | N+0 | sprint 1 |
| `W-AUDIT-7c` | API Key clear modal + Settings 拆 sub-tab + GUI a11y 補齊 | N+2-N+3 | sprint 2-3 |
| `W-AUDIT-1d` | docs/README index sync + ADR-0021 草擬 | N+0 | sprint 1 |
| `W-AUDIT-5b` | H-8 H-9 sunset + runner.rs split bin/server-side | N+1（reserved slot） | sprint 3 |

#### 3.4 Track A Wave Definitions（labeling 重命名後）

| Wave | 內容 | Sprint slot | Person-day | 狀態 |
|---|---|---|---|---|
| `W-AUDIT-8a` | Alpha Surface Foundation Phase A→D | N+0..N+2 | ~40 | SPEC PHASE done @ commit c13c811e |
| `W-AUDIT-9` | Graduated Canary Foundation 7 sub-task | N+0..N+1 | 1.5-2 sprint | SPEC done via AMD-2026-05-09-03 |
| `W-AUDIT-8b` (A4-A) | Funding Skew Directional | N+3 spec → N+4 IMPL | 1 sprint | spec phase pending |
| `W-AUDIT-8c` (A4-B) | Liquidation Cluster Reaction | N+2 spec → N+3 IMPL | 1.5 sprint | spec phase pending（BB review WS topic）|
| `W-AUDIT-8d` (A4-C) | BTC→Alt Lead-Lag | N+1 spec → N+2 IMPL | 7 person-day | spec phase pending |
| `W-AUDIT-8e` (R-2) | Strategist Alpha Source Orchestrator | N+3 spec → N+4 IMPL | 2-3 sprint | defer 8a Phase A done |
| `W-AUDIT-8f` (R-3) | Hypothesis Pipeline first-class（含 W-AUDIT-4 併入）| N+4 spec → N+5 IMPL | 2-3 sprint | defer 8a Phase B done + Decision-3 confirmed |
| `W-AUDIT-8g` (R-4) | Per-alpha-source Live Promotion Gate | N+5 spec → N+7+ IMPL | 2 sprint | defer 1-2 alpha source Stage 3 PASS |
| `W-AUDIT-10` (R-5) | Spec-as-Code + Module Lifecycle SM | N+5 spec → N+6+ IMPL | 1-2 sprint | 中期 |
| `W-ARCH-3` | Spec drift 收口（EX-06 §6.3 / LG-X-02..05 supersedes）| N+0 | sprint 1 | (沿用 v18) |

#### 3.5 Cross-Wave Conflict Resolution（QCTODO §3 整原文）

整 4 條衝突原文 + file overlap + 解決方案。

#### 3.6 Day 0-3 / Day 3-5 / Day 5-7 / Day 12-14 / Day 14-15 Dispatch（QCTODO §4 整原文）

5 active E1 + 1 stand-by E1 + ops 並行 Day-by-Day。

#### 3.7 P0 — True-Live Blockers Table

沿用 v18 line 344-372（P0-AGENT-1..4 / P0-EDGE-1 / P0-LG-1/2/3 / P0-OPS-1..4 / P0-DECISION-AUDIT-1..5 / P0-NEW-ISSUE/VULN / P0-V2-NEW / P0-V3-* 6 條）。

加新 entry：
- `P0-DECISION-AUDIT-6` DONE 2026-05-09 — W-AUDIT-6 mid-ground verdict (operator confirmed 保 6 / 砍 6 + DSR K -12)
- `P0-DECISION-AUDIT-7` DONE 2026-05-09 — W-AUDIT-4 ML 基座併入 W-AUDIT-8f (R-3 Hypothesis Pipeline) confirmed

P2-STRUCT-1 status flip ACTIVE → DONE 2026-05-09 17:27 UTC。

#### 3.8 P1 — Next Engineering Queue

沿用 v18 line 374-397（P1-FAKE-1 / P1-OPENCLAW-3..7 / P1-AGENT-OBS-1 / P1-AGENT-RUNTIME-1 / P1-DATA-1..4 / P1-EDGE-1/2 / P1-REPLAY-1/2 / P1-LG-5 / P1-AUDIT-DOCS-1 / P1-AUDIT-SEC-2 / P1-AUDIT-RUNTIME-3 / P1-AUDIT-ML-4 / P1-AUDIT-PERF-5 / P1-AUDIT-STRATEGY-6 / P1-AUDIT-AI-UX-7）。

#### 3.9 P2 — Maintenance Backlog

沿用 v18 line 399-427（P2-MIG / P2-SEC / P2-REPLAY / P2-PYDANTIC / P2-RUST / P2-LEASE / P2-STRUCT / P2-AUDIT-* / P2-AUDIT-VERIFY / P2-AUDIT-VAR-6c / P2-AUDIT-LAYER2-7c / P2-AUDIT-DEAD-CODE / P2-AUDIT-QC-STAND-ALONE）。

P2-STRUCT-1 標 DONE 2026-05-09 17:27 UTC（A2-followup G3-08）。

### §4 Sign-off Pre-flight Checklist

**整 QCTODO §5 原文搬入 v19**，包括：
- 結構 invariant 5 條
- 安全 invariant 5 條
- 治理 invariant 6 條
- 監督 / record 追蹤 4 條（17-20）
- git status clean 強制（CLAUDE.md §七 P0-GOV-3）

每條 invariant 加 cross-ref 至 v19 §3 對應 wave / P0/P1 entry。

### §5 Sprint N+0..N+5 Roadmap

**整 QCTODO §1 原文搬入 v19**：
- 6-sprint capacity table（5 active + 1 stand-by 規格）
- Critical path
- Business chain milestone（FA chain 63→89%）
- Stand-by E1 啟用條件 5 條
- 最早 supervised live 規劃帶 4 概率（6/15 30% / 6/30 40% / 7/15 25% / 8/15 5%）

### §6 D-02 Layer 2 Manual 7d SOP / Push Back / Risk

#### 6.1 D-02 SOP

整 QCTODO §6 + FA report §2 6 step（API key / 寫入 / Manual trigger / 4 metric / Pass-Fail / Rollback）。

#### 6.2 PA Push Back（已 RESOLVED）

operator 拍板 (a) stand-by E1 採納（QCTODO §7 整原文）。

#### 6.3 FA Push Back（已採納，記入治理）

4 條：Track W vs Track A 預算 / D-02 SOP 上限 / A/B/C 預期 / 砍 6 是 right move。

#### 6.4 Risk Mitigation 表

QCTODO §7 + PA report §3.4 整 7 條 risk + 觸發 + 對應。

### §7 Schedule

沿用 v18 line 429-453 calendar dates table（不變動 calendar），加：
- 2026-05-XX merge v18 + QCTODO → v19 closure
- 2026-05-XX..2026-08-XX Sprint N+0..N+5 event-driven
- 2026-06-15 / 6-30 / 7-15 / 8-15 supervised live 4 概率帶

### §8 Dispatch Rules / Handoff Checks

沿用 v18 line 454-475（規則 + Mac/Linux ssh handoff command）。

加 QCTODO §砍 6 grep blacklist 規則（W-AUDIT-6d sub-wave）：
```
- W-AUDIT-6d 砍 6 grep blacklist：E2 review 必跑 grep -rE
  "(ma_crossover_5m_reverse|bb_breakout_donchian_5m_sweep|grid_trading_symbol_expansion|funding_arb_v3_ma_retry|strategy_params_hardcoded_dynamic_sweep|cost_gate_per_strategy_individual_tune)"
  命中 → reject merge
```

### §9 References

整 v18 line 477-573 所有 reference + QCTODO §8 references：

#### 2026-05-08 Full Audit Fix Plan
（沿用 v18 line 477-483）

#### 2026-05-09 Adversarial Verification Chain
- v1 verification（PM sign-off summary + 12 reports + verified-closed archive v1）
- v2 verification（同上 v2）
- v3 verification（同上 v3）+ PA fix plan v2 DUAL-TRACK
- 4-agent loss audit dispatch（PA full dispatch engineering plan + FA business chain validation + PA architectural redesign + QC/MIT/PA/FA worklog）

#### Active Dispatch Documents（QCTODO §8 整原文）
- PA full dispatch plan: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--full_dispatch_engineering_plan.md` commit d3bf7be2
- FA business chain validation: `srv/docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-09--full_dispatch_business_chain_validation.md` commit 5a2dee98
- PA architectural redesign: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--full_loss_architectural_root_cause_redesign.md` commit ad59765b
- W-AUDIT-8a spec: `srv/docs/execution_plan/2026-05-09--w_audit_8a_alpha_surface_foundation_spec.md` commit c13c811e
- AMD-2026-05-09-03 graduated canary: `srv/docs/governance_dev/amendments/2026-05-09--AMD-2026-05-09-03-graduated-canary-default.md` commit b1891023
- AMD-2026-05-09-02 W-AUDIT-6 5 策略 verdict: `srv/docs/governance_dev/amendments/2026-05-09--AMD-2026-05-09-02-...md`
- restart_all.sh G3-08 wire commit dddc5dc1
- This merge analysis: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--todo_qctodo_merge_analysis.md`

---

## §5 PM 重寫 TODO 必含 anchors（不能因 merge 漏掉）

PM 寫 v19 時必保留以下 anchors。任一漏掉 = cross-ref 斷裂 = v19 不可用。

### 5.1 文件路徑 anchors（必保留 + 命名格式）

| Anchor | 路徑 | 來源 |
|---|---|---|
| TODO v18 archive | `srv/docs/archive/2026-05-XX--todo_v18_closed_entries_archive.md` | 新加（PM 寫 v19 同 commit） |
| QCTODO archive | `srv/docs/archive/2026-05-XX--qctodo_sprint_n0_n5_archive.md` | 新加（PM 寫 v19 同 commit）|
| v18 §三 archive | `docs/archive/2026-05-07--todo_v12_agent_openclaw_replan_archive.md` | v18 line 9 引用 |
| W-AUDIT verified-closed v1 | `docs/archive/2026-05-09--w_audit_verified_closed_archive.md` | v18 line 114 引用 |
| W-AUDIT verified-closed v2 | `docs/archive/2026-05-09--w_audit_verified_closed_archive_v2.md` | v18 line 121 引用 |
| W-AUDIT verified-closed v3 | `docs/archive/2026-05-09--w_audit_verified_closed_archive_v3.md` | v18 line 5 引用 |
| 12-Agent Audit Fix Plan | `srv/2026-05-08--full_audit_fix_plan.md` | v18 line 105/479 引用 |
| Verification summary v1 | `srv/2026-05-09--audit_fix_verification_summary.md` | v18 line 111/487 引用 |
| Verification summary v2 | `srv/2026-05-09--audit_fix_verification_v2_summary.md` | v18 line 117/498 引用 |
| Verification summary v3 | `srv/2026-05-09--audit_fix_verification_v3_summary.md` | v18 line 516 引用 |
| 4-agent worklog | `srv/docs/worklogs/2026-05-09--4_agent_loss_audit_and_5_actions.md` commit ad59765b | QCTODO §8 引用 |
| W-AUDIT-8a spec | `srv/docs/execution_plan/2026-05-09--w_audit_8a_alpha_surface_foundation_spec.md` commit c13c811e | TODO v18 line 342 + QCTODO §8 引用 |
| AMD-2026-05-09-03 | `srv/docs/governance_dev/amendments/2026-05-09--AMD-2026-05-09-03-graduated-canary-default.md` commit b1891023 | TODO v18 line 27 + QCTODO §8 引用 |
| AMD-2026-05-09-02 | `srv/docs/governance_dev/amendments/2026-05-09--AMD-2026-05-09-02-...md` | TODO v18 line 140/314/363 + QCTODO §8 引用 |
| AMD-2026-05-09-01 | `srv/docs/governance_dev/amendments/2026-05-09--AMD-2026-05-09-01-...md` | TODO v18 line 393 引用 |
| AMD-2026-05-02-01 | `srv/docs/governance_dev/amendments/2026-05-02--SM-02_R04_retrofit_path_a.md` | v18 §三 + line 360 引用 |
| AMD-2026-05-03-01 | `srv/docs/governance_dev/amendments/2026-05-03--ref20_wave7_p5_impl_accept_deploy_blocked.md` | TODO v18 reference 引用 |
| ADR-0015 | openclaw_core sunset | TODO v18 line 364/419 引用 |
| ADR-0017 | (W-AUDIT-1 series) | TODO v18 line 141 引用 |
| ADR-0018 | funding_arb retirement | v18 line 275/441 引用 |
| ADR-0020 | Layer2 manual+supervisor only | v18 line 364/418/441 + QCTODO §6 引用 |
| ADR-0021 | (新加) v2-NEW-1 strategist cap freedom-not-gate rationale | TODO v18 line 545/566 + QCTODO sign-off invariant 18 |
| W-C operator auth file | `docs/governance_dev/2026-05-08--w_c_lease_router_authorized.md` | TODO v18 line 88 + CLAUDE.md §三 引用 |
| OpenClaw repositioning | `docs/architecture/2026-05-06--openclaw_control_plane_repositioning.md` | CLAUDE.md §一 引用 |
| Issue tracker | `docs/agents/issue-tracker.md` | CLAUDE.md §十一 引用 |
| Triage labels | `docs/agents/triage-labels.md` | CLAUDE.md §十一 引用 |
| Domain docs | `docs/agents/domain.md` | CLAUDE.md §十一 引用 |

### 5.2 命名格式 anchors（PM 必沿用）

```
# Wave label format
W-A / W-B / ... / W-G              ← Rank 1-7 historical wave
W-AUDIT-1 / W-AUDIT-2 / ... / W-AUDIT-7  ← 12-Agent Audit (closed/partial)
W-AUDIT-3b / W-AUDIT-4b / W-AUDIT-6c / W-AUDIT-6d / W-AUDIT-7c / W-AUDIT-1d / W-AUDIT-5b  ← Track W (~92h)
W-AUDIT-8a / 8b / 8c / 8d / 8e / 8f / 8g / 9 / 10 / W-ARCH-3  ← Track A (~270-330h)

# P0 label format
P0-AGENT-1..4 / P0-EDGE-1 / P0-LG-1/2/3 / P0-OPS-1..4
P0-DECISION-AUDIT-1..5 (DONE) + 6/7 (新加 from QCTODO)
P0-NEW-ISSUE-1 (DONE) / P0-NEW-VULN-1/2 (DONE) / P0-AUDIT-NEW-LG-X-05 (DONE)
P0-V2-NEW-1/2/3 (DONE)
P0-V3-MIT-ROOT-CAUSE / P0-V3-V079-NOT-APPLIED / P0-V3-CRON-NOT-INSTALLED / P0-V3-PA-SPEC-FIX / P0-V3-ADR-0021-ARCH-04 / P0-V3-ENGINE-RESTART  ← ACTIVE

# P1 / P2 沿用 v18

# Sub-task format (QCTODO 派工)
A4-A / A4-B / A4-C  ← 候選新策略 (mapped to W-AUDIT-8b/c/d)
B-M1 / B-M2 / B-M3  ← ML 三斷層 (mapped to W-AUDIT-4b sub-tasks)
C-A6 / C-D-05-wire / C-D-02  ← Promotion + Dormant
T1..T7              ← W-AUDIT-9 7 sub-task
Phase A/B/C/D       ← W-AUDIT-8a 4 phase

# E1 slot format
@E1-A / @E1-B / @E1-C / @E1-D / @E1-E  ← 5 active
@E1-F                                   ← 1 stand-by

# Sprint format
N+0 W1-W2 / N+1 W3-W4 / ... / N+5 W11-W12

# Healthcheck id format
[14] [33] [37] [38] [40] [41] [42] [42b] [42c] [43] [45] [50] [51] [54] [55] [56]  ← 既存
[58] graduated_canary_stage_invariant   ← 新加 W-AUDIT-9 T4
[Xc] ml_training_cron_active            ← 新加 P0-V3-CRON
```

### 5.3 Cross-reference anchors（PM 必保留 v18 → v19 引用）

| 引用源 | 引用內容 | v19 必保留 |
|---|---|---|
| CLAUDE.md §三 W-AUDIT-1 sync `b91487f2` | latest state evidence source | v19 §2 Latest State 沿用 |
| CLAUDE.md §四 5-gate live boundary | hard fail 條件 | v19 §3 P0 + §4 sign-off invariant 7 引用 |
| CLAUDE.md §五 13-tab GUI dictionary | system/replay/paper/demo/live/strategy/risk/governance/ai/learning/agents/monitoring/settings | v19 不直接引用，但 W-AUDIT-7c 涉及 |
| CLAUDE.md §九 file size 800/2000 | E2 必查 | v19 §3 Dispatch Rules + W-AUDIT-5b 引用 |
| CLAUDE.md §九 singleton table | strategy_wiring entries | v19 §3 W-AUDIT-4b / W-AUDIT-6d 涉及 |
| DOC-08 §12 9 條安全不變量 | Pre-trade audit / Lease / fills / 風控降級 / Authorization 過期 / Mainnet env / Bybit retCode / Reconciler 對賬 / Operator 角色 | v19 §4 sign-off invariant 6 引用 |
| §二 16 根原則 | 認知誠實 / Agent 自主 / 失敗收縮 / etc | v19 §4 sign-off invariant 8 引用 |
| EarnedTrust T0/T1/T2/T3 | session 級 authorization TTL | v19 §3 LG-X 系列引用 |

### 5.4 Healthcheck id 引用 anchors（PM 必保留）

v18 + QCTODO 引用以下 healthcheck id（共 17 條）：
```
[14] data_writer_health_evidence
[33] maker_fill_rate
[37] historical_fail_recovery
[38] grid_lifecycle_drift
[40] realized_edge_acceptance
[41] scanner_market_gate_confirmation
[42] LG-5 reviewer base
[42b] settled_eligible_strategies_ratio
[42c] attribution_drift_low_sample
[43] label_backfill_freshness
[45] pricing_binding
[50] (REF-20 sentinel)
[51] scanner_opportunity_shadow_acceptance
[54] (P1-OPENCLAW-6/7 backend foundation)
[55] agent_decision_spine_lineage
[56] live_pipeline_active
[58] graduated_canary_stage_invariant  ← 新加 W-AUDIT-9 T4
```

PM v19 必含完整 healthcheck id reference，不可漏其中任何一條。

### 5.5 Commit hash 引用 anchors（PM 必保留）

v18 + QCTODO 引用以下 commit hash（共 24 條）：
```
b91487f2  ← W-AUDIT-1 sync source
b91487f2  ← W-AUDIT-1 evidence source
3d6f62dd  ← W-B Linux trade-core deploy
503eeb33  ← W-C runtime active
72f05aa0..7fccad06  ← 24h Fix Sprint 28 commits
da2dba25  ← W-AUDIT-3 PARTIAL F-17 patch
e858ae2 + 6cb1c3b  ← audit-p1-1 retrofit
3681f83  ← repair_migration_checksum binary
e95c779  ← Track P T4
306993e  ← V2 SWAP
75741eff  ← Donchian compute_all 修復原 commit
ad14db07  ← Donchian regression test 補
6d3ea046  ← bb_breakout 5m IMPL
cc6476dd  ← portfolio VaR/CVaR/EVT IMPL
edf33c0  ← Sprint 1 critical security
aa9343c + 5184990  ← Sprint 2 §八 evidence + AMD
dbcf845b  ← Sprint 3 Track H Decision Lease retrofit
0ad79f67  ← Sprint 4 closure operator override
e97a333b  ← lease audit BYPASS audit row IMPL
862e79b7  ← W-AUDIT-2 V078 deployment commit
276a9b17  ← P1-OPENCLAW-6/7 backend foundation
c49125f1  ← P1-OPENCLAW-3 deployment
34211ab4  ← edge_label_backfill_cron deployment
dddc5dc1  ← A2-followup G3-08 wire (QCTODO 新加)
c13c811e  ← W-AUDIT-8a spec
b1891023  ← AMD-2026-05-09-03 graduated canary
d3bf7be2  ← PA full dispatch plan (QCTODO §8)
5a2dee98  ← FA business chain validation (QCTODO §8)
ad59765b  ← PA architectural redesign + 4-agent worklog (QCTODO §8)
ad14db07/c2ab7b1a/48227607/c081029d/da2aba11  ← v3 5 commits (P0-V2-NEW-1/2/3 source/test)
```

PM v19 必保留所有 commit hash 引用，不可省略。

### 5.6 Operator 拍板 / Sign-off anchors（必明文記入）

```
2026-05-08 operator-authorized   ← W-C lease router gate flag flip + Linux deploy
2026-05-09 operator UTC          ← QCTODO sign-off (a) stand-by E1 採納
2026-05-09 operator UTC          ← AMD-2026-05-09-02 5 策略 verdict 採納 (Option ii)
2026-05-09 operator UTC          ← AMD-2026-05-09-03 5-stage graduated canary
2026-05-09 17:27 UTC             ← G3-08 enable verified daemon spawned
```

### 5.7 Schema / Migration anchors

| Migration | 用途 | v19 必保留 |
|---|---|---|
| V054 | lease_transitions Python migration | v18 P2-MIG-1 引用 |
| V065 | openclaw.* ledger | v18 line 61 引用 |
| V066 | replay finalize byte-size CHECK + replay_report enum | v18 line 408 引用 |
| V067 | PID reuse guard (replay_runner) | v18 P2-REPLAY-1 引用 |
| V068/V070/V071 | reclassification COMMENT (W-AUDIT-4) | v18 line 130 引用 |
| V069 | observability cleanup | v18 line 339 引用 |
| V072 | feature_baseline_writer guard | v18 line 174-179 引用 |
| V073/V074 | wrappers + retention | v18 line 339 引用 |
| V075/V076/V077 | guards + archive CHECK trigger | v18 line 339 引用 |
| V078 | lease_transitions BYPASS check | v18 line 366 引用 |
| V079 | strategy_trial_ledger + promotion_pipeline reports | v18 line 371 + QCTODO §C 群 引用 |
| V080 | governance_canary_stage（新加 W-AUDIT-9 T2）| QCTODO §1 §4 + PA dispatch §2.2 引用 |
| V0XX (TBD) | hypothesis_pipeline + W-AUDIT-4 hypothesis_id link（W-AUDIT-8f IMPL Sprint N+5）| PA dispatch §5 引用 |
| V0XX (TBD) | decision_features_evaluations 拆表 | QCTODO §B 群 B-M1 引用 |
| V0XX (TBD) | feature_baselines / oi_delta_panel / liquidations W-AUDIT-8a Phase B/C migration | PA dispatch §2.1 引用 |

PM v19 必保留所有 migration 引用 + 新加 V080 / 新增 hypothesis_pipeline / decision_features_evaluations / W-AUDIT-8a Phase B/C migration TBD 標記。

---

## §6 結語

本 merge analysis verdict：

1. **方向一致**：QCTODO 與 TODO v18 方向一致，**QCTODO 是 v18 順承擴張不是替代**
2. **3 類 entry merge 規則**：
   - ✅ **TODO v18 已含 framework + QCTODO 細化** = merge 進對應 wave，加 Sprint slot + person-day
   - 🆕 **QCTODO 全新 entry** = merge 進新 §4/§5/§6 section
   - ⚠️ **labeling 衝突** = 採 QCTODO labeling（W-AUDIT-8b/c/d → A4-A/B/C 候選新策略；R-1/R-2/R-3/R-4/R-5 改名 W-AUDIT-8a/8e/8f/8g/10）
3. **v19 預估規模**：~700-750 行（v18 573 + ~150 sprint dispatch 細化 + 16 sign-off invariant + Cross-Wave Conflict + D-02 SOP - 重疊歸併 / 30 closed entries archive）
4. **Operator 拍板 (a) stand-by E1** 必入 v19 banner + §3 Day-by-Day + §5 Sprint Roadmap
5. **PM 寫 v19 必含 5 類 anchors**：文件路徑 / 命名格式 / cross-ref / healthcheck id / commit hash / migration / operator sign-off — 任一漏 = cross-ref 斷裂

**PM 推薦 commit 流程**：
```
1. 讀本 merge analysis report
2. 寫 srv/TODO.md v19（按 §4 Outline 重組）
3. 同 commit 內：
   - mv srv/QCTODO.md → docs/archive/2026-05-XX--qctodo_sprint_n0_n5_archive.md
   - 新加 docs/archive/2026-05-XX--todo_v18_closed_entries_archive.md（30 closed entries 移出）
4. commit message 模板：
   "chore(todo): merge QCTODO into TODO v19 with sprint roadmap + 16 sign-off invariant
    
    - QCTODO archived to docs/archive/2026-05-XX--qctodo_sprint_n0_n5_archive.md
    - 30 v18 closed entries archived to docs/archive/2026-05-XX--todo_v18_closed_entries_archive.md
    - Wave label reconcile: 8b/c/d → A4-A/B/C; R-1..R-5 → 8a/8e/8f/8g/10
    - 16 sign-off invariant (PA 11 + FA 9 deduplicate) merged into §4 Pre-flight Checklist
    - 6-sprint roadmap (N+0..N+5) merged into §5 Sprint Roadmap
    - Cross-Wave Conflict + Day-by-Day + Risk Mitigation merged into §3/§6
    - PA Push Back resolved (a) stand-by E1; FA push back 4 採納 in §6
    - operator sign-off 2026-05-09 captured in §0 banner
    - Archived QCTODO original at commit hash <PA dispatch d3bf7be2 / FA chain 5a2dee98>"
5. push to origin / Linux fast-forward
```

**最後 push back 給 PM**：v19 規模 ~700-750 行已逼近「TODO 自身衛生」上限。建議 v19 land 後 1-2 sprint 內若 §3 closed entries 多到 ~30+，再啟動 v20 archive cycle，避免 v19 膨脹。

---

**報告路徑**：`srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--todo_qctodo_merge_analysis.md`

**結論性報告同步至**：`srv/docs/CCAgentWorkSpace/Operator/`（PM 收到後處理）

**PA DESIGN DONE: report path: srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--todo_qctodo_merge_analysis.md**
