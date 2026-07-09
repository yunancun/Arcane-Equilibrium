# PM Tier 4 Sign-off — Operator 建議 1-4 並行執行

**日期**：2026-04-26 CEST
**簽核人**：PM (Project Manager + Conductor)
**範圍**：Operator 接續 Tier 3 後請求「按建議 1-4 執行」（G3-08 Phase 1 + G9-02-FUP + EXIT-FEATURES audit + OBSERVER cleanup）
**狀態**：✅ **派發層面 100% 完成 + E2 batch review 6 PASS / 0 退回 + cargo 2198/0**

---

## § 1. 6 commits 完成記錄（git range `da40a88..576a37e`）

| # | Commit | 任務 | Owner | E2 結論 |
|---|---|---|---|---|
| 1 | `eb65e1e` | G9-02-FUP-WS-CLIENT-SPLIT (ws_client.rs 1227→6 sibling, max 355) | E5 | ✅ PASS |
| 2 | `1c7b20e` | G3-08 Phase 1 Sub-task B Python h_state_invalidator + query_handler + reverse IPC route | E1 | ✅ PASS |
| 3 | `deac4bc` | G3-08 Phase 1 Sub-task B E1 memory + workspace report | E1 | ✅ PASS |
| 4 | `c53c3f9` | OBSERVER-PIPELINE-POST-F42FACE-CLEANUP (-228/+679; 新 [19] healthcheck) | E1 | ⚠️ PASS-with-LOW (L-1 cosmetic) |
| 5 | `aa287c4` | G3-08 Phase 1 Sub-task A Rust h_state_cache + ipc_server handlers (5 new + 11 modified) | E1 (worktree) | ✅ PASS |
| 6 | `4689fc8` | PM merge: Sub-task A from worktree (union resolve E1/memory.md) | PM | ✅ ACCEPT |
| 7 | `576a37e` | E2 batch review Tier 4 (6 commits + 8-axis audit + MIT findings) | E2 | (review itself) |

**Tier 4.3 MIT EXIT-FEATURES-WRITER-BUG-1 audit**：findings 由 PM 代落檔（`docs/CCAgentWorkSpace/MIT/workspace/reports/2026-04-26--exit_features_writer_bug_audit.md`），E2 ACCEPT，本 sign-off commit 一併 commit。

## § 2. Test baseline（採集 2026-04-26 ~15:30 CEST）

- engine lib **2198/0**（baseline 2176 → +22：G3-08 Phase 1A h_state_cache 22 new tests）
- pytest h_state Mac+Linux **35/0**（h_state_invalidator 21 + h_state_query_handler 14）
- pytest layer2 chain **136/0**（G3-07 不變）
- healthcheck cron 19→**20 check**（[19] observer_pipeline_alive 加入；首次揭露 silent fail ok=1/5）

## § 3. PM 編排介入記錄

### 介入：worktree branch merge（commit 6 `4689fc8`）
- Tier4.1a (Rust h_state_cache) 在 isolation worktree 跑（per PA design 必要 isolation）
- 完成後 push 到 `worktree-agent-a2e662b283f719faf` branch（origin），不直接 main（origin/main 已被並行 sub-agent 領先 4 commit）
- PM 跑 ssh trade-core `git merge --no-ff origin/worktree-agent-...`：
  - 衝突在 `docs/CCAgentWorkSpace/E1/memory.md`（multi-session memory race per `project_multi_session_memory_race.md`）
  - PM 用 Python regex union 策略 resolve（worktree 短條目 + main 整段 OBSERVER section）
  - cargo test post-merge 2198/0 baseline 不破壞
  - Mac + Linux + origin 三端 sync 完成
- E2 ACCEPT 此 merge：union 0 條目丟失 + commit msg 標明來源 worktree

### 教訓（→ memory）
- worktree harness 不自動 merge — PM 必須手動處理 worktree branch
- E1 memory.md multi-session append 必衝突，預先 plan union resolve
- ssh trade-core git merge 在 SSH bridge 範圍內（非 Mac CC 禁止 merge）

## § 4. MIT EXIT-FEATURES-WRITER-BUG-1 audit 重大發現

### Smoking gun
delta 37 = **STRKUSDT dust spiral 37 個 `fast_track_reduce_half` 半倉 fill (`realized_pnl=0`)**

### 雙因 root cause
- **RCA-A 主因**：`step_0_fast_track.rs:317` MICRO-PROFIT-FIX-1 fail-open `if entry_notional <= 0.0 { return true; }` 對 legacy/restored dust 倉位失效，每 60s 半倉 × 37 次直到 float epsilon
- **RCA-B 併發因**：`pipeline_helpers.rs:217 try_emit_exit_feature_row` 對 partial reduce 也寫 EF row（**污染 ML training set 37 個 noise label**）

### Collateral 揭發
- ML training data hygiene 風險：歷史 `learning.exit_features` 中可能多達 N% 是 dust spiral noise
- engine restart 後 dust 倉位 entry_notional=0 → fast_track ReduceToHalf 觸發 spiral
- MICRO-PROFIT-FIX-1 防護需第二層 dust qty floor 或 dust eviction 路徑

### 推薦修復（→ Backlog ticket）
- 路徑 1 (RCA-A): `step_0_fast_track.rs:315-340` 加 dust qty floor 或 eviction
- 路徑 2 (RCA-B): `pipeline_helpers.rs:217` 加 condition `if realized_pnl == 0 → 跳過 EF emit`
- E1 cohesive PR 1+2 修，預計 healthcheck [3] 自動 PASS

## § 5. Wave progress

### Wave 2 G3 series（更新後）
- ✅ G3-01 ~ G3-07：全完成
- ✅ G3-08 PA design + Phase 1（Rust + Python）：本 session 完成（**Sub-task C 接線 + healthcheck [20] 留下次 session**）
- ⬜ G3-09：解阻於 G3-08 Phase 3 H5 接入（~3-4 sessions 後）

### Wave 4 G9 series（全完成）
- ✅ G9-01/02/03/04/05 + G9-02-FUP-WS-CLIENT-SPLIT 全完成

## § 6. PM Sign-off

```
pm_approval:
  tier4_dispatch: ✅ COMPLETE (5 件 + 1 PM merge: G3-08 Phase 1A+B / G9-02-FUP / EXIT audit / OBSERVER)
  tier4_e2_review: ✅ APPROVED (6 PASS + 0 退回; 3 LOW future polish)

  test_baseline:
    cargo_lib: 2198/0 (baseline 2176 +22)
    pytest_h_state: 35/0
    pytest_layer2_chain: 136/0
    healthcheck: 19 → 20 (新 [19] observer_pipeline_alive)

  e2_review_results:
    g3_08_phase1a: PASS (race risk 反駁 PA §14.1 #1 / 45-site mechanical extension 合理)
    g3_08_phase1b: PASS (DEFAULT-OFF / IPC route / HANDLER_TTLS 2.0s)
    g9_02_fup: PASS (5 hot-path byte-identical 全驗證)
    observer_cleanup: PASS-with-LOW (L-1 BRIDGE_RC overshadow cosmetic)
    pm_merge: ACCEPT (union 0 條目丟失)
    mit_audit: ACCEPT (5 hypothesis 完整 / 雙因 RCA grep 獨立驗證)

  pm_intervention_log:
    worktree_merge: PM ssh trade-core git merge --no-ff + Python regex union resolve E1 memory conflict

  follow_up_tickets_added: 9
    P1: EXIT-FEATURES-WRITER-BUG-1-FIX (cohesive 1+2 PR, 3-5h)
    P1: G3-08 Phase 1 Sub-task C (strategy_wiring + healthcheck [20], 0.5d)
    P1: G3-08 Phase 2-4 E1 implementation (next 3 sessions, ~9d)
    P2: PAPER-STATE-DUST-RESTORE-AUDIT (PA + E1, 0.5-1d)
    P2: ML-TRAINING-DATA-HYGIENE-1 (MIT + E1, 1-2d)
    P3: MICRO-PROFIT-FIX-1-HEALTHCHECK (G6 wave)
    P3: TIER4-OBSERVER-LOW-1 (cron BRIDGE_RC overshadow polish)
    P3: TIER4-AI-SERVICE-DISPATCH-SPLIT (ai_service_dispatch.py 868 @ §九 800 警告)
    P3: TIER4-MIT-AUDIT-GREP-SNIPPET (MIT H1 reject 補 grep)

  wave3_impact: 0 (所有 Tier 4 改動 DEFAULT-OFF env-gated 或純 Python; 不觸動 engine PID 2033577)
  live_target: 2026-05-30 中位 ±7d (不變)

  pm_signature: PM (Project Manager + Conductor)
  pm_timestamp: 2026-04-26 15:30 CEST
```

## § 7. Backlog 新增（→ TODO.md）

### P1 立即可派
1. **EXIT-FEATURES-WRITER-BUG-1-FIX**（3-5h，E1）— RCA-A 路徑 1 (A1+A3 dust qty floor + restart-time eviction) + RCA-B 路徑 2 (B1 emit_close_fill 跳過 partial reduce) cohesive PR；healthcheck [3] 自動 PASS 為完成標準
2. **G3-08 Phase 1 Sub-task C**（0.5d，主 PM agent 編排）— strategy_wiring.py 加 init_invalidator_singleton + CLAUDE.md §九 singleton 表加 _H_STATE_INVALIDATOR + HStateCacheSlot + 新 healthcheck [20] check_h_state_gateway_freshness；G3-08 Phase 1 完整收尾
3. **G3-08 Phase 2 H1+H3 接入**（3d，E1 next session）— H1 ThoughtGate + H3 ModelRouter emit hook + Rust DashMap state 真實 stats

### P2
4. **PAPER-STATE-DUST-RESTORE-AUDIT**（0.5-1d，PA design + E1 audit）— `paper_state::restore_from_db` dust handling 邏輯 audit + 是否 startup-time evict（MIT §6 follow-up #1）
5. **ML-TRAINING-DATA-HYGIENE-1**（1-2d，MIT + E1）— SQL 量化全期 `learning.exit_features` dust spiral noise 比例 + 補回填 SQL 移除歷史 noise label（MIT §6 follow-up #5）

### P3 LOW（不阻 sign-off）
6. **MICRO-PROFIT-FIX-1-HEALTHCHECK**（G6 wave）— `passive_wait_healthcheck` 加 dedicated check 偵測 fast_track dust spiral 復發
7. **TIER4-OBSERVER-LOW-1**（30min，E1）— cron_observer_cycle.sh:76-79 BRIDGE_RC overshadow at exit cosmetic fix
8. **TIER4-AI-SERVICE-DISPATCH-SPLIT**（G5 wave）— ai_service_dispatch.py 868 進 §九 800 警告區
9. **TIER4-MIT-AUDIT-GREP-SNIPPET**（30min，MIT）— H1 reject 補 grep snippet 證據（E2 已獨立驗證屬實）

## § 8. Wave 3 影響：**0**

所有 Tier 4 改動 **DEFAULT-OFF env-gated** 或純 Python；不觸動 engine PID 2033577；passive observation 主軸不變：
- EDGE-P3 [11] 96%+ ETA ~04-27 滿 200 → ~04-30 連 3d PASS（不變）
- G2-02 雙軌驗證 ~05-01~05-03（不變）
- G2-01 PostOnly 1-2w 驗收 ~05-07/08（不變）
- EDGE-P1b per-strategy ≥200 rows ~05-10（不變）
- P0-3 邊評決策會 ~05-15（不變）
- **Live target ~2026-05-30 中位 ±7d（不變）**

## § 9. 下一步（next session）

### 立即可派（按 ROI 排序）
1. **EXIT-FEATURES-WRITER-BUG-1-FIX**（P1，3-5h）— 最高 ROI，healthcheck [3] 立即從 FAIL→PASS + 清 ML training data 污染源頭
2. **G3-08 Phase 1 Sub-task C**（P1，0.5d）— G3-08 Phase 1 完整收尾，啟用 OPENCLAW_H_STATE_GATEWAY=1 dogfood
3. **G3-08 Phase 2 H1+H3 接入**（P1，3d）— Phase 1 Sub-task C 完成後立即派

### 被動等待中（不變）
4. EDGE-P3 ETA ~04-30 / G2-02 ~05-03 / G2-01 ~05-07 / EDGE-P1b ~05-10 / P0-3 ~05-15

### 並行 P2 wave
5. PAPER-STATE-DUST-RESTORE-AUDIT（PA design）+ ML-TRAINING-DATA-HYGIENE-1（MIT + E1）

---

**PM Sign-off DONE — Tier 4 派發層面 100% 完成 + E2 PASS + cargo 2198/0** — 2026-04-26 15:30 CEST
