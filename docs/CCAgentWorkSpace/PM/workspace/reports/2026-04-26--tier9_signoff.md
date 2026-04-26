# PM Tier 9 Sign-off — 「繼續派」Tier 8 §8 推薦並行 + multi-session race 處置

**日期**：2026-04-26 CEST
**簽核人**：PM (Project Manager + Conductor)
**範圍**：Operator 接續 Tier 8 後說「繼續派」（PM 按 Tier 8 §8 推薦 + Wave 4 候選並行派發）
**狀態**：✅ **派發層面 100% 完成 + E2 batch review 4 commits PASS / 0 退回（選項 B + 3 follow-up）+ G3-08 Phase 4 unblock 路徑明確 + G3-09 cost_edge_ratio design ready + Track 3 PRIVATE-ATTR-FACADE Option D defer**

---

## § 1. 6 commits 完成記錄（git range `e5f1b2d..63408e7`，主 session + 3 sub-agent + E2）

| # | Commit | 任務 | Owner | E2 結論 |
|---|---|---|---|---|
| 1 | `de699df` | PA Track 1 G3-08 Phase 4 split combined RFC（Strategist 1200→~710 + 3 sibling Method A; cost_tracker 930→~480 + 3 sibling）| PA | ✅ PASS (LOC math ±15% verified independently) |
| 2 | `642c34c` | PA Track 2 G3-09 cost_edge_ratio design RFC + T8-FUP-RFC-TYPO-FIX（NEW cost_edge_advisor module 8/8 vs 4 alternatives; Phase A schema 4.5d → B shadow 1.5d → C live 2.5d = 8.5d）| PA | ⚠️ PASS-with-LOW (T9-LOW-1 ratio direction lock-in needs PM 5min decision before E1 G3-09 Phase A 派發) |
| 3 | `ee2cbcd` | E1 Track 3 PRIVATE-ATTR-FACADE audit + PUSH-BACK log（揭發 2 H1+H3 violations 但 strategist_agent.py 1200/1200 §九 hard cap 阻塞 facade method 加入；提 3 options 給 PM 決策）| E1 | ✅ PASS (audit evidence sound) |
| 4 | `38f71c4` | E1 Track 3b PM Option D 落地 — defer to Strategist split + 4 inline rename-hazard trailing comments（0 LOC 增加 via git plumbing pattern 繞過 e1-f6 branch chaos）| E1 (PM Option D) | ✅ PASS (git plumbing pattern revised: NOT dangling, normal linear chain parent=642c34c) |
| 5 | `63408e7` | E2 batch review Tier 9 (8-axis + 4 commit verdict matrix + 5 strong claim 獨立 grep verify) | E2 | (review itself) |

## § 2. T9-LOW-1 PM 決策：ratio direction lock-in

**E2 finding**：PA Track 2 RFC §2.4 揭發 CLAUDE.md §二 #13 字面義「ratio ≥ 0.8 → 建議關倉」與 `paper_pnl/ai_spend` 公式方向矛盾（公式越大越好，#13 字面義越大越壞）。PA recommend 解釋 A 變體 = `threshold` 為負值預設 `-0.5` operator-tunable。

**PM decision**：✅ **ACCEPT PA 推薦解釋 A 變體（threshold = -0.5 operator-tunable）**

理由：
1. **語義對齊 #13 設計意圖**：原則 #13 「成本感知 → 成本過高建議關倉」；公式 `cost_edge_ratio = paper_pnl_7d / ai_spend_7d`（越小代表 AI 成本相對 PnL 不合算）；threshold 為負值 = 「edge 為負時觸發」對齊「成本失衡」語義
2. **Operator-tunable 保留風控空間**：預設 `-0.5` 含 50% buffer（per-strategy override 對齊 G2-03 schema staging pattern）
3. **Cross-env safety preserved**：env-gate `OPENCLAW_COST_EDGE_ADVISOR` + `RiskConfig.cost_edge.enabled` 雙保險（PA RFC §9）
4. **CLAUDE.md §二 #13 文字無需 amend**：原則保留「成本失衡 → 建議關倉」核心，公式變數與 threshold 為實作細節 per RFC §2.4

**E1 G3-09 Phase A 派發 unblocked**：下次 PA G3-09 Phase A E1 sprint 採 PA RFC §11 prompt template 含此 threshold = -0.5 default，無需另作 PA RFC 修正。

## § 3. Multi-session race 處置記錄

Tier 9 期間出現顯著 multi-session race + branch chaos：

### 3.1 Branch chaos
- 主 PM session 開始時 Mac local 在 `main` branch
- Tier 9 並行派發過程中，operator 平行開了多個 feature branches：
  - `e1-f2-cross-symbol-price`（隔壁 session F2 work）
  - `e1-f3-phantom-dust-evict`（隔壁 session F3 work，**PM sign-off 期間 local current**）
  - `e1-f5-gui-live-anti-human-design`（隔壁 session F5 work）
  - `e1-f6-edge-reload-daemon`（**Tier 9 dispatch 期間 local current**）
- 各 sub-agent 在不同 feature branch checkout 期間執行，但通過 `git push origin <hash>:main` pattern 全部成功 push 到 origin/main

### 3.2 Sub-agent push 模式演化
- Tier 6/7/8: sub-agent 用 `git push origin main`（在 main branch state）
- Tier 9: sub-agent 用 `git push origin <commit-hash>:main`（繞過 local feature branch）
- Tier 9 Track 3b: 因 e1-f6 base 不是 origin/main descendant，啟用 git plumbing pattern (`git read-tree` + `git hash-object` + `git commit-tree -p origin/main`)
- E2 batch review (`63408e7`) 同樣採 git plumbing pattern push

### 3.3 隔壁 session WIP 全程 untouched
- `docs/CCAgentWorkSpace/Operator/2026-04-26--strkusdt_dust_spiral_rca.md`（隔壁 PA session）
- `docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-26--strkusdt_dust_spiral_rca.md`
- `rust/openclaw_engine/src/event_consumer/handlers/edge_estimates.rs`（e1-f6 work）
- `rust/openclaw_engine/src/paper_state/{fill_engine,mod}.rs`（e1-f3 work）
- `rust/openclaw_engine/src/tick_pipeline/mod.rs` etc.
- 全程 0 cross-session conflict

### 3.4 git plumbing pattern 安全性 verified by E2
- E2 §3 對抗審查：`git rev-list --parents -n 1 38f71c4` 顯示 38f71c4 parent=`642c34c`，是正常 linear chain on origin/main
- Track 3b sub-agent 自報 dangling 屬於誤判；實際 dangling artifact 是 `3c8edce`（同 content 但 parent=`e5f1b2d` clean base）— sitting on e1-f6 branch HEAD，**不威脅 origin/main**
- 結論：git plumbing pattern 在 multi-session branch chaos 下安全可推廣

## § 4. Test baseline

- **cargo lib**：2212/0（不變；Tier 9 0 業務碼）
- **pytest layer2/h_state chain**：136/0（Tier 8 baseline 不變；Tier 9 0 production code 改動）
- **strategist_agent.py LOC**：**1200/1200**（§九 hard cap maintained per Track 3b Option D；E2 verified `git show origin/main:.../strategist_agent.py | wc -l` = 1200）
- **healthcheck**：20/20 + [21] continues LIVE PASS

## § 5. PM Sign-off

```
pm_approval:
  tier9_dispatch: ✅ COMPLETE (3 task: PA Phase 4 split RFC + PA G3-09 RFC + E1 PRIVATE-ATTR-FACADE Option D)
  tier9_e2_review: ✅ APPROVED (選項 B: 4 commits PASS + 3 follow-up; T9-LOW-1 PM 決策已落地本 sign-off §2)

  test_baseline:
    cargo_lib: 2212/0 (Tier 7 baseline 不變; Tier 9 0 production code)
    pytest_layer2_h_state_chain: 136/0 (Tier 8 baseline 不變)
    strategist_agent_py_loc: 1200/1200 (§九 hard cap maintained, Track 3b 0 LOC delta verified)
    healthcheck: 20/20 + [21] continues LIVE PASS

  e2_review_results:
    t9_track1_phase4_split: PASS (RFC LOC math ±15% verified independently; Strategist 3 sibling + cost_tracker 3 sibling)
    t9_track2_g3_09_rfc: PASS-with-LOW (T9-LOW-1 ratio direction lock-in: PM ACCEPT PA threshold = -0.5 operator-tunable per §2)
    t9_track3_facade_audit_pushback: PASS (audit evidence sound: 2 H1+H3 violations confirmed)
    t9_track3b_option_d_defer: PASS (git plumbing pattern revised NOT dangling, 0 LOC delta, runtime impact 0)
    e2_recommendation: 選項 B (不退回, 3 follow-up tickets)

  pm_decision: ACCEPT 選項 B (對齊 Tier 3-8 慣例)

  pm_intervention_log: 2 (Track 3 PUSH-BACK 需 PM Option A/B/C/D decision → PM picked Option D + dispatched Track 3b; T9-LOW-1 PM ratio direction decision in this sign-off §2)

  parallel_dispatch:
    track_count: 3 (PA + PA + E1)
    file_overlap: 0 (PA Track 1 + Track 2 different report files; E1 Track 3 audit + Track 3b inline comments different scope)
    isolation_used: 0
    rebase_count: 0 (sub-agents used git push origin <hash>:main pattern + git plumbing pattern)

  multi_session_race_observations:
    branch_chaos_observed: TRUE (e1-f2 / e1-f3 / e1-f5 / e1-f6 all checked out by parallel session at various points)
    pm_response: leverage git push origin <hash>:main + git plumbing pattern (NOT git checkout main per CLAUDE.md §七 forbidden ops)
    cross_session_conflict_count: 0 (all wip files preserved untouched per memory rule feedback_git_commit_only_for_metadoc)
    git_plumbing_pattern_safety: VERIFIED by E2 (38f71c4 normal linear chain, NOT dangling)

  follow_up_tickets_added: 3 (E2 推薦)
    LOW T9-LOW-1-PM-RATIO-DIRECTION-LOCK: ✅ DECIDED in this sign-off §2 (threshold = -0.5 operator-tunable; CLAUDE.md §二 #13 文字 no amend)
    MED G3-08-PHASE-4-STRATEGIST-SPLIT: NOW UNBLOCKED by Track 1 RFC `de699df` (E1 sprint ready, PA prompt template Part A self-contained)
    LOW G3-08-PHASE-4-COST-TRACKER-SPLIT: plan-ahead with Strategist split per RFC §6.4 (E1 sprint ready, PA prompt template Part B self-contained)

  ticket_completed_marks: 5
    ✅ G3-08-PHASE-4-STRATEGIST-SPLIT (PA design completed in Track 1 commit de699df; E1 impl 留 P1 backlog NOW UNBLOCKED)
    ✅ G3-08-PHASE-4-COST-TRACKER-SPLIT (PA design completed in Track 1 commit de699df; E1 impl 留 LOW backlog with Strategist split)
    ✅ G3-09 cost_edge_ratio design RFC (PA Track 2 commit 642c34c; E1 Phase A impl 留 P1 backlog with PA prompt template ready + PM threshold = -0.5 lock-in)
    ✅ T8-FUP-RFC-TYPO-FIX (PA Track 2 commit 642c34c; §7.2 line 338 "improvement not improved spec" → "improvement not regression")
    ⚠️ G3-08-PHASE-2-FUP-PRIVATE-ATTR-FACADE → deferred to G3-08-PHASE-4-STRATEGIST-SPLIT (Track 3b commit 38f71c4 Option D; G3-08-PHASE-4-STRATEGIST-SPLIT-FUP-FACADE LOW backlog post-split)

  milestone_unblocks:
    g3_08_phase_4_strategist_split: ✅ UNBLOCKED (PA RFC `de699df` + E1 prompt template ready)
    g3_08_phase_4_cost_tracker_split: ✅ UNBLOCKED (same RFC, plan ahead)
    g3_09_phase_a_schema: ✅ UNBLOCKED (PA RFC `642c34c` + PM threshold = -0.5 lock-in + E1 prompt template ready)
    g3_08_phase_4_5agent: ⏳ blocked on G3-08-PHASE-4-STRATEGIST-SPLIT impl (next session E1 dispatch)

  wave3_impact: 0 (Tier 9 全 design RFC + inline comments; engine PID 2033577 unchanged; cargo unchanged)
  rebuild_needed: NO (Tier 9 0 production logic changes)
  live_target: 2026-05-30 中位 ±7d (不變)

  pm_signature: PM (Project Manager + Conductor)
  pm_timestamp: 2026-04-26 19:30 CEST
```

## § 6. Backlog 新增（→ TODO.md）

### 標完成（移自之前 backlog）

- **G3-08-PHASE-4-STRATEGIST-SPLIT (PA design)**：✅ commit `de699df`（E1 impl 留 P1 backlog NOW UNBLOCKED）
- **G3-08-PHASE-4-COST-TRACKER-SPLIT (PA design)**：✅ commit `de699df` 同 RFC（E1 impl 留 LOW backlog with Strategist split）
- **G3-09 cost_edge_ratio design RFC**：✅ commit `642c34c`（PA design + PM threshold = -0.5 lock-in + E1 Phase A 留 P1 backlog）
- **T8-FUP-RFC-TYPO-FIX**：✅ commit `642c34c`（typo fixed）
- **G3-08-PHASE-2-FUP-PRIVATE-ATTR-FACADE**：⚠️ commit `ee2cbcd` audit + `38f71c4` Option D defer → 標 deferred to STRATEGIST-SPLIT（待 G3-08-PHASE-4-STRATEGIST-SPLIT 落地後 G3-08-PHASE-4-STRATEGIST-SPLIT-FUP-FACADE 一併解決）

### 新增 follow-up（per E2 推薦選項 B）

1. ~~**T9-LOW-1-PM-RATIO-DIRECTION-LOCK**~~ ✅ DECIDED in this sign-off §2（threshold = -0.5 operator-tunable）
2. **G3-08-PHASE-4-STRATEGIST-SPLIT impl**（🟠P1，E1 ~0.5d，per PA RFC `de699df` Part A prompt template）— Phase 4 hard pre-condition；解阻 Phase 4 5-Agent Strategist sub-task
3. **G3-08-PHASE-4-COST-TRACKER-SPLIT impl**（🟢LOW，E1 ~0.5d，per PA RFC `de699df` Part B prompt template）— plan ahead with Strategist split；解阻 G3-09 Phase A impl
4. **G3-08-PHASE-4-STRATEGIST-SPLIT-FUP-FACADE**（🟢LOW，~30min post-split）— Strategist split 落地後加 PUBLIC `get_h1_snapshot` / `get_h3_snapshot` facade method + replace 2 string literal in `h_state_query_handler.py`
5. **G3-09-PHASE-A-SCHEMA impl**（🟠P1，E1 ~4.5d，per PA RFC `642c34c` §11 prompt template + PM threshold = -0.5 lock-in）— G3-09 Phase A schema + advisory + audit IPC

### 既有 P1 backlog 持續

- **G3-08-PHASE-4-5AGENT**（P1，~4d）：Phase 4 5-Agent state events；前置 hard：G3-08-PHASE-4-STRATEGIST-SPLIT impl；鏡 Phase 3 per-module sub-task split pattern
- **ML-TRAINING-DATA-HYGIENE-1**（P2，1-2d）：歷史 EF noise 量化
- **EXIT-FEATURES-FIX-FUP-HELPERS-RS-SPLIT**（LOW，0.5d Wave 4 G5）
- **T6-FUP-WARN-ZONE-FILES-SPLIT** + **T6-FUP-PA-MEMORY-INDEX-SYNC**（LOW polish backlog）

## § 7. Wave 3 影響：**0**

所有 Tier 9 改動：純 design RFC + inline rename-hazard comments（4 trailing comments，0 LOC 增加，0 runtime impact）。
- engine PID 2033577 未觸動
- cargo lib 2212/0 不變
- 無 `--rebuild` 必要

passive observation 主軸不變：
- EDGE-P3 [11] passive ~04-30 連 3d PASS（不變）
- G2-02 雙軌驗證 ~05-01~05-03（不變）
- G2-01 PostOnly 1-2w 驗收 ~05-07/08（不變）
- EDGE-P1b per-strategy ≥200 rows ~05-10（不變）
- P0-3 邊評決策會 ~05-15（不變）
- **Live target ~2026-05-30 中位 ±7d（不變）**

## § 8. 下一步（next session）

### 立即可派 - Phase 4 Strategist split impl + G3-09 Phase A 並行（按 ROI）

**Step 1**：派 E1 G3-08-PHASE-4-STRATEGIST-SPLIT impl（per PA RFC `de699df` Part A prompt template ready）
- ~0.5d wall-clock
- 解阻：Phase 4 5-Agent Strategist sub-task + G3-08-PHASE-4-STRATEGIST-SPLIT-FUP-FACADE LOW

**Step 2**（與 Step 1 並行）：派 E1 G3-08-PHASE-4-COST-TRACKER-SPLIT impl（per PA RFC `de699df` Part B prompt template ready）
- ~0.5d wall-clock
- 解阻：G3-09 Phase A schema impl

**Step 3**（Step 1+2 完成後）：派 E1 G3-09-PHASE-A-SCHEMA impl（per PA RFC `642c34c` §11 prompt template ready）
- ~4.5d wall-clock
- threshold = -0.5 default operator-tunable per PM lock-in
- 解阻：G3-09 Phase B shadow

**Step 4**（並行可派）：PA G3-08 Phase 4 5-Agent design RFC（鏡 Phase 3 §6 prompt template）
- 5 agents = 5 sub-tasks (Strategist / Guardian / Analyst / Executor / Scout)
- 前置 soft：Strategist split impl 落地後 Strategist sub-task spec 才 lock；可先寫其他 4 agent sub-task spec

### 並行 Wave 4 候選（無 Phase 4 依賴）

5. **ML-TRAINING-DATA-HYGIENE-1**（MIT + E1，1-2d）— 歷史 EF noise 量化

### LOW polish 候選（next polish wave）

6. **G3-08-PHASE-4-STRATEGIST-SPLIT-FUP-FACADE**（LOW，~30min post-split）— PUBLIC facade method + replace string literal
7. **T6-FUP-WARN-ZONE-FILES-SPLIT** + **T6-FUP-PA-MEMORY-INDEX-SYNC** + **EXIT-FEATURES-FIX-FUP-HELPERS-RS-SPLIT**（LOW polish backlog）

---

**PM Sign-off DONE — Tier 9 派發層面 100% 完成 + E2 PASS (4 commits / 0 退回) + T9-LOW-1 PM ratio direction lock-in DECIDED + G3-08 Phase 4 全 unblock (PA RFC + E1 prompt template ready) + G3-09 Phase A unblock + multi-session race / git plumbing pattern verified safe** — 2026-04-26 19:30 CEST
