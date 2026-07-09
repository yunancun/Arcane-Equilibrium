# PM Tier 8 Sign-off — 「@PM 派發並行」G3-08 Phase 3 COMPLETE 里程碑

**日期**：2026-04-26 CEST
**簽核人**：PM (Project Manager + Conductor)
**範圍**：Operator 接續 Tier 7 後說「@PM 派發並行」（PM 按 Tier 7 §7 Phase 3 ready-to-deploy 推薦 + T7 follow-up 並行派發）
**狀態**：✅ **派發層面 100% 完成 + 4 task PASS / 0 退回（選項 B + 3 follow-up）+ G3-08 Phase 3 COMPLETE + G3-09 cost_edge_ratio 解阻**

---

## § 1. 7 commits 完成記錄（git range `13412db..2e02afb`）

| # | Commit | 任務 | Owner | E2 結論 |
|---|---|---|---|---|
| 1 | `8cd257e` | E1 Track 1 G3-08 Phase 3 Sub-task 3-1 H2 budget integration (4 Python files; pytest +12; absorbed Track 2 in-flight H4 edits to shared `h_state_query_handler.py`) | E1 | ✅ PASS (per Tier 8 batch `84da817`) |
| 2 | `cf39415` | E1 Track 1 memory append (Tier 8 Track 1 lessons) | E1 | ✅ PASS |
| 3 | `71faf4c` | E1 Track 2 G3-08 Phase 3 Sub-task 3-2 H4 validator integration + silent gap fix (validation_pass counter; **strategist_agent.py 1200/1200 §九 hard cap exact-touch**) | E1 | ⚠️ PASS-with-MEDIUM (G3-08-PHASE-4-STRATEGIST-SPLIT MUST 開作 Phase 4 hard pre-condition) |
| 4 | `79a808a` | PA Track 3 T7-FUP-DUST-SQL-DEVIATION-DOC RFC §7.4 amend + Deviation Log §13 (E1 SQL deviation as improved spec) | PA | ⚠️ PASS-with-LOW (T8-FUP-RFC-TYPO-FIX optional PA ~2min) |
| 5 | `84da817` | E2 batch review Tier 8 Tracks 1-3 (8-axis + 4 commit verdict matrix + multi-track absorb pattern verified) | E2 | (review itself) |
| 6 | `d1a2252` | E1 Track 4 G3-08 Phase 3 Sub-task 3-3 H5 cost_logging integration (5 files; pytest +15; **Phase 3 COMPLETE; G3-09 unblocked**) | E1 | ⚠️ PASS-with-LOW (G3-08-PHASE-4-COST-TRACKER-SPLIT LOW; layer2_cost_tracker.py 930 LOC 警告區 +130) |
| 7 | `2e02afb` | E2 Track 4 supplemental review (single commit; 7 adversarial points all PASS; verified H5CostStats parity / dual hook race / SSOT / metadata drop / lockless-read pattern) | E2 | (review itself) |

## § 2. Phase 3 COMPLETE 里程碑（G3-08 全鏈狀態）

| Phase | 狀態 | Commits |
|---|---|---|
| **Phase 1A** Rust h_state_cache types/poller/handler | ✅ 完成 | `aa287c4` (5 new files + 22 unit tests) |
| **Phase 1B** Python h_state_invalidator + query_handler | ✅ 完成 | `1c7b20e` + `deac4bc` (4 new files + 35 unit tests + reverse IPC route) |
| **Phase 1C** wiring + healthcheck [20] | ✅ 完成 | `5943337` + `deee78e` (strategy_wiring + CLAUDE.md §九 + healthcheck) |
| **Phase 2** H1 ThoughtGate + H3 ModelRouter | ✅ 完成 | `9120948` + `f2ed286` (h1_thought_gate + model_router + query_handler v0→v1; +61 pytest) |
| **Phase 2 FUP** H3 schema align (Rust H3RouteStats rename) | ✅ 完成 | `4b30f5e` (Tier 7 Track 1; cargo lib 2210→2212) |
| **Phase 3 Sub-task 3-1** H2 budget integration | ✅ 完成 | `8cd257e` (Tier 8 Track 1; pytest +12) |
| **Phase 3 Sub-task 3-2** H4 validator + silent gap fix | ✅ 完成 | `71faf4c` (Tier 8 Track 2; pytest +13) |
| **Phase 3 Sub-task 3-3** H5 cost_logging | ✅ 完成 | `d1a2252` (Tier 8 Track 4; pytest +15; **G3-09 unblocked**) |
| **Phase 4** 5-Agent state events (Strategist/Guardian/Analyst/Executor/Scout) | ⬜ next | hard pre-condition: G3-08-PHASE-4-STRATEGIST-SPLIT 完成 |

**5 H buckets 全 wired**：H1 (ThoughtGate) + H2 (BudgetTracker) + H3 (ModelRouter) + H4 (Validator) + H5 (CostLogger) — Rust h_state_cache poller 全部 5 buckets serialize/deserialize round-trip 通過 schema parity tests。

## § 3. Test baseline（採集 2026-04-26 ~18:30 CEST）

- **cargo lib**：2212/0（Tier 7 baseline 不變；Phase 3 純 Python）+ h_state_cache 17/0 + Rust H5CostStats schema parity verified
- **pytest layer2/h_state chain**：96 → **136/0**（baseline 96 + Tier 8 累計 +40：Track 1 +12 H2 + Track 2 +13 H4 + Track 4 +15 H5）
- **Linux pytest 4 control_api_v1 suites**：188/0
- **healthcheck cron**：20/20 alive；[21] paper_state_dust_inventory continues LIVE PASS
- **Smoke env=0**：全 5 sub-task dormant PASS-skip（version=0, h_states={}）
- **Smoke env=1**：h_states keys ⊇ {h1, h2, h3, h4, h5}（Phase 3 5-bucket 全 wire verified）

## § 4. Track 詳情

### Track 1 — E1 Sub-task 3-1 H2 budget integration (commits `8cd257e` + `cf39415`)

按 PA Phase 3 §4 ready-to-deploy prompt template 落地。

| Aspect | 結果 |
|---|---|
| `get_h2_snapshot()` 3 fields | ✅ 對齊 Rust H2BudgetState (types.rs:58-72): daily_remaining_usd / hard_cap_usd / adaptive_multiplier |
| `record_claude_cost` invalidate hook | ✅ 末尾 `_invalidate_h_state_async("h2.budget_consumed")` fire-and-forget，不阻塞 hot-path |
| Multi-track absorb pattern | ✅ Track 1 commit absorbed Track 2 in-flight H4 edits to `h_state_query_handler.py` + `test_h_state_query_handler.py`（E2 grep cross-diff 驗證 TRUE）|
| Phase 3 5-bucket wiring | Track 1 落地 H2 bucket → query_handler 5-tuple 結構備好 |
| `--rebuild` needed | ❌ 純 Python；下次 uvicorn restart 即生效 |

### Track 2 — E1 Sub-task 3-2 H4 validator + silent gap fix (commit `71faf4c`)

按 PA Phase 3 §5 ready-to-deploy prompt template 落地 + PA Track 3 audit 揭發的 H4 silent gap fix。

| Aspect | 結果 |
|---|---|
| H4 silent gap fix | ✅ `validation_pass` counter 從 PA 揭發的 0 hits → **13 hits**（init / pass branch counter / pass branch invalidate_async / get_h4_snapshot / docstring）|
| `_safe_snapshot_self` sibling helper | ✅ H4 stateless validator 用 sibling helper（vs H1/H3/H2 共用 `_safe_snapshot`）— 設計 trade-off 可接受 |
| `with_h4=False` 預設 | ✅ 對齊 Track 1 H2 default-off pattern（同時測「Phase 2 deploy without 3-2 land silent skip」場景）|
| **strategist_agent.py LOC** | ⚠️ **1200/1200**（exactly at §九 hard limit；E2 spot-check readability 1180-1200 + 945-970 NOT degraded）|
| Hard pre-condition for Phase 4 | 🔴 G3-08-PHASE-4-STRATEGIST-SPLIT MUST 完成 才能派 Phase 4 Strategist sub-task |

### Track 3 — PA T7-FUP-DUST-SQL-DEVIATION-DOC RFC §7.4 amend (commit `79a808a`)

| Aspect | 結果 |
|---|---|
| §7.4 SQL spec 改寫 | ✅ 對齊 E1 commit `8241133` 實裝（add `FILTER (WHERE realized_pnl=0)` + drop `partial_reduce_real_count`）|
| §13 Deviation Log | ✅ 含 Tier 7 Track 2 reference + E2 T7-LOW-1 評為 improvement + Linux production cron LIVE PASS confirmation + amend commit hash |
| 不動 §1-§6 + §8-§12（結論部分）| ✅ Recommend Option B 結論未被誤改 |
| 純 doc amend | ✅ 不動 helper_scripts/ |

### Track 4 — E1 Sub-task 3-3 H5 cost_logging integration (commit `d1a2252`) **Phase 3 COMPLETE**

按 PA Phase 3 §6 ready-to-deploy prompt template 落地，在 Track 1 修過的 `layer2_cost_tracker.py` 上疊加。

| Aspect | 結果 |
|---|---|
| `get_h5_snapshot()` 4 fields | ✅ 對齊 Rust H5CostStats (types.rs:167-178): ai_spend_7d_usd / paper_pnl_7d_usd / cost_edge_ratio / data_days |
| Metadata drop | ✅ 從 `get_cost_edge_ratio` 6-key 結果丟 `roi_basis/roi_disclaimer` 2 keys（H5 hot-path consumers don't need metadata；`get_cost_edge_ratio` remains SSOT for principle 10 markers）|
| Dual invalidate hook | ✅ `record_claude_cost` 末尾兩條 hint (`h2.budget_consumed` + `h5.claude_cost_recorded`) fire-and-forget；E2 verified race-safe（daemon-thread + Rust handler 0 ordering contract + test set comparison）|
| `record_search_cost` hook | ✅ 加單一 `h5.search_cost_recorded`（Sub-task 3-1 刻意未加，3-3 範圍）|
| `_FakeCostTracker` opt-in `with_h5=False` 預設 | ✅ 對齊 Track 1 H2 / Track 2 H4 default-off pattern |
| `test_both_raise_drops_both_keys_version_zero` rename | ✅ → `test_all_raise_drops_all_keys_version_zero`（5 桶皆 raise invariant 升級）|
| **layer2_cost_tracker.py LOC** | ⚠️ **930**（超 §七 800 警告線 +130；未超 §九 1200 hard cap）|
| **G3-09 cost_edge_ratio 解阻** | ✅ Rust hot-path 可 DashMap shard lookup `cost_edge_ratio` ≤1ms p99 |

## § 5. PM Sign-off

```
pm_approval:
  tier8_dispatch: ✅ COMPLETE (4 task: Sub-task 3-1 H2 + 3-2 H4 + Track 3 RFC amend + 3-3 H5)
  tier8_e2_review: ✅ APPROVED (選項 B: 4 task PASS + 3 follow-up)

  test_baseline:
    cargo_lib: 2212/0 (Tier 7 baseline 不變; Phase 3 純 Python)
    rust_h_state_cache: 17/0
    pytest_layer2_h_state_chain: 96 → 136/0 (累計 +40: Track 1 +12 + Track 2 +13 + Track 4 +15)
    pytest_linux_4_suites: 188/0
    healthcheck: 20/20 + [21] paper_state_dust_inventory continues LIVE PASS
    smoke_env_0: dormant PASS-skip
    smoke_env_1: h_states keys ⊇ {h1, h2, h3, h4, h5} (Phase 3 5-bucket 全 wire verified)

  e2_review_results:
    t8_track1_h2: PASS (multi-track absorb pattern verified, get_h2_snapshot 3 fields 對齊 Rust)
    t8_track2_h4: PASS-with-MEDIUM (strategist_agent.py 1200/1200 §九 hard cap exact-touch; H4 silent gap 從 0 → 13 hits)
    t8_track3_rfc_amend: PASS-with-LOW (T8-FUP-RFC-TYPO-FIX optional)
    t8_track4_h5: PASS-with-LOW (layer2_cost_tracker.py 930 LOC; 7 adversarial points all PASS; G3-09 unblocked)
    e2_recommendation: 選項 B (不退回, 3 follow-up tickets)

  pm_decision: ACCEPT 選項 B (對齊 Tier 3-7 慣例)

  pm_intervention_log: 0 (Tier 8 全 4 sub-agents 直 push 0 PM intervention; multi-track absorb pattern 自動處理 shared file overlap)

  parallel_dispatch_pattern:
    track_count: 4 (3 parallel + 1 serial; Track 4 dispatched after Track 1 land per PA §3.3 file overlap)
    file_overlap_handling: multi-track absorb pattern (Track 1 commit absorbed Track 2 shared file edits via git commit --only)
    isolation_used: 0
    rebase_count: 0 (atomic merges throughout)

  multi_session_coordination:
    qa_session_intersection: 0 (QA last commit `7e83159` 在 Tier 7 內; Tier 8 期間 QA 未動)
    pa_session_intersection: 1 (隔壁 PA session 創建 docs/CCAgentWorkSpace/Operator/2026-04-26--strkusdt_dust_spiral_rca.md + PA/workspace 對應 + memory.md modified, Tier 8 全程不動 per memory rule)
    multi_session_safe: TRUE (zero cross-session conflict throughout 7 commits)

  follow_up_tickets_added: 3 (E2 推薦)
    MEDIUM: G3-08-PHASE-4-STRATEGIST-SPLIT (PA-led ≥0.5d, MUST 完成 才能派 Phase 4 Strategist sub-task; strategist_agent.py 1200/1200 hard cap)
    LOW: G3-08-PHASE-4-COST-TRACKER-SPLIT (plan ahead with Strategist split; layer2_cost_tracker.py 930 在警告區但未超 hard cap)
    LOW: T8-FUP-RFC-TYPO-FIX (PA ~2min optional)

  ticket_completed_marks: 4
    ✅ G3-08-PHASE-3-SUB-TASK-3-1 H2 budget integration (commit 8cd257e)
    ✅ G3-08-PHASE-3-SUB-TASK-3-2 H4 validator integration + silent gap fix (commit 71faf4c)
    ✅ G3-08-PHASE-3-SUB-TASK-3-3 H5 cost_logging integration (commit d1a2252)
    ✅ T7-FUP-DUST-SQL-DEVIATION-DOC (commit 79a808a)

  milestone_unblocks:
    g3_08_phase_3_complete: ✅ (5 H buckets H1+H2+H3+H4+H5 全 wired)
    g3_09_cost_edge_ratio: ✅ unblocked (H5 cost_logging live; Rust hot-path can DashMap lookup ≤1ms p99)
    g3_08_phase_4: ⏳ blocked on G3-08-PHASE-4-STRATEGIST-SPLIT (hard pre-condition)

  wave3_impact: 0 (Phase 3 純 Python observability extension; engine PID 2033577 unchanged; cargo unchanged)
  rebuild_needed: NO (Track 1+2+4 全 Python; uvicorn restart 即生效, env=0 dormant deploy zero overhead, env=1 啟用需 OPENCLAW_H_STATE_GATEWAY=1)
  live_target: 2026-05-30 中位 ±7d (不變)

  pm_signature: PM (Project Manager + Conductor)
  pm_timestamp: 2026-04-26 18:30 CEST
```

## § 6. Backlog 新增（→ TODO.md）

### 標完成（移自之前 backlog）

- **G3-08-PHASE-3-SUB-TASK-3-1 H2 budget integration**（P1）→ ✅ commit `8cd257e`
- **G3-08-PHASE-3-SUB-TASK-3-2 H4 validator integration**（P1）→ ✅ commit `71faf4c`
- **G3-08-PHASE-3-SUB-TASK-3-3 H5 cost_logging integration**（P1）→ ✅ commit `d1a2252`
- **T7-FUP-DUST-SQL-DEVIATION-DOC**（LOW）→ ✅ commit `79a808a`

### 新增 follow-up（per E2 推薦選項 B）

1. **G3-08-PHASE-4-STRATEGIST-SPLIT**（🟠MED，PA-led ≥0.5d）— Phase 4 5-Agent state events 派發前 hard pre-condition；strategist_agent.py 1200/1200 §九 hard cap exact-touch，Phase 4 Strategist sub-task 加任何 LOC 必先拆檔
2. **G3-08-PHASE-4-COST-TRACKER-SPLIT**（🟢LOW，plan ahead with Strategist split）— layer2_cost_tracker.py 930 LOC 在 §七 800 警告區 +130；未超 §九 1200 hard cap，但 Phase 4 + G3-09 cost_edge_ratio 後續工作會繼續加 LOC，建議與 Strategist split 同 wave 處理
3. **T8-FUP-RFC-TYPO-FIX**（🟢LOW，PA ~2min optional）— Track 3 RFC §7.4 amend 中發現的 typo（E2 標 optional）

### 既有 P1 backlog 持續

- **G3-08-PHASE-4-5AGENT**（P1，~4d）：Phase 4 5-Agent state events；**前置 hard**: G3-08-PHASE-4-STRATEGIST-SPLIT；推 Pattern B（鏡 Phase 3 per-module sub-task split）
- **G3-09 cost_edge_ratio (P3)**：✅ unblocked（H5 cost_logging live）；可派 PA design RFC + E1 落地
- **G3-08-PHASE-2-FUP-PRIVATE-ATTR-FACADE**（P2，1-2h）：`h_state_query_handler` PUBLIC facade refactor
- **EXIT-FEATURES-FIX-FUP-HELPERS-RS-SPLIT**（LOW，0.5d Wave 4 G5）：helpers.rs 1315 split sibling
- **T6-FUP-WARN-ZONE-FILES-SPLIT**（LOW，1d Wave 4 G5）：checks_derived 869 + ipc_client 899 split sibling
- **T6-FUP-PA-MEMORY-INDEX-SYNC**（LOW，10min PA）
- **ML-TRAINING-DATA-HYGIENE-1**（P2，1-2d）

## § 7. Wave 3 影響：**0**

所有 Tier 8 改動：
- Track 1+2+4：純 Python observability extension（H2/H4/H5 snapshot accessors + invalidate hooks + query_handler 5-bucket wiring）；engine PID 2033577 未觸動；cargo 未動
- Track 3：純 doc amend
- env=0 dormant deploy zero overhead；env=1 啟用需 operator 設 `OPENCLAW_H_STATE_GATEWAY=1` env var + uvicorn restart（無 cargo `--rebuild`）

passive observation 主軸不變：
- EDGE-P3 [11] passive ~04-30 連 3d PASS（不變）
- G2-02 雙軌驗證 ~05-01~05-03（不變）
- G2-01 PostOnly 1-2w 驗收 ~05-07/08（不變）
- EDGE-P1b per-strategy ≥200 rows ~05-10（不變）
- P0-3 邊評決策會 ~05-15（不變）
- **Live target ~2026-05-30 中位 ±7d（不變）**

## § 8. 下一步（next session）

### 立即可派 - Phase 4 啟動前置（按 ROI）

**Step 1**：派 PA G3-08-PHASE-4-STRATEGIST-SPLIT（MEDIUM ≥0.5d）— hard pre-condition
1. PA design Strategist split RFC（Phase 4 sub-task 派發前必先 lock 拆檔方案）
2. 同時可派 G3-08-PHASE-4-COST-TRACKER-SPLIT（LOW）一起做（plan ahead pattern）

**Step 2**：派 PA G3-08 Phase 4 5-Agent sub-task split design（鏡 Phase 3 §6 prompt template）
- 5 agents = 5 sub-tasks（Strategist / Guardian / Analyst / Executor / Scout）
- 評估並行 vs 序列（Strategist + Guardian + Analyst 互依度評估）
- 寫 5 self-contained E1 prompt templates

**Step 3**：派 PA G3-09 cost_edge_ratio design RFC（H5 解阻後可開工）
- 演算法 design + Rust hot-path integration
- 與 H5 snapshot 的 read 路徑

### 並行 Wave 4 候選（無 Phase 4 依賴）

4. **G3-08-PHASE-2-FUP-PRIVATE-ATTR-FACADE**（P2，1-2h）— h_state_query_handler PUBLIC facade refactor
5. **ML-TRAINING-DATA-HYGIENE-1**（MIT + E1，1-2d）— 歷史 EF noise 量化

### LOW polish 候選

6. **T8-FUP-RFC-TYPO-FIX**（LOW，PA ~2min）
7. **T6-FUP-WARN-ZONE-FILES-SPLIT** + **T6-FUP-PA-MEMORY-INDEX-SYNC** + **EXIT-FEATURES-FIX-FUP-HELPERS-RS-SPLIT**（LOW polish backlog）

---

**PM Sign-off DONE — Tier 8 派發層面 100% 完成 + E2 全 PASS (4 task / 0 退回) + G3-08 Phase 3 COMPLETE 里程碑 + G3-09 cost_edge_ratio 解阻 + Phase 4 ready (待 Strategist split)** — 2026-04-26 18:30 CEST
