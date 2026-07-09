# 2026-04-27 · G3-08 Phase 4 — Layer2CostTracker 4-sibling Split

**Agent**: E1
**RFC**: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-26--g3_08_phase4_split_plan.md` §6.4 (Method A)
**Worktree**: `/Users/ncyu/Projects/TradeBot/srv/.claude/worktrees/agent-af8001f13a3d3940b`
**Status**: ✅ DONE — 待 E2 審查 → E4 回歸

## 任務
PM Tier 8 sign-off `e5f1b2d` follow-up #2：拆 `layer2_cost_tracker.py` 930→~480 LOC，
解 §七 800 警告 + 預先閃過 §九 1200 hard cap（G3-09 cost_edge_ratio 預期 +50-100 LOC）。

## 執行（Method A）
1. NEW `app/layer2_cost_recording.py` 405 LOC — 9 cost-write fn（record_claude_cost /
   record_search_cost / _add_daily_* / _sync_to_rust_budget /
   _increment_daily_session_count / record_call / record_ollama_call / reset_today_costs）。
   `_invalidate_h_state_async` import 隨 `record_*` 路徑遷此。
2. NEW `app/layer2_adaptive.py` 207 LOC — 3 fn（recalculate_adaptive /
   get_adaptive_state / get_cost_edge_ratio），G3-09 future hook 在 docstring 標註。
3. NEW `app/layer2_h_state_snapshots.py` 190 LOC — get_h2_snapshot / get_h5_snapshot，
   完整 53 + 82 LOC 雙語 docstring + Rust struct line ref 保留。
4. 主檔 `app/layer2_cost_tracker.py` 930 → **540 LOC**：14 method 委派至 sibling（1-line
   delegator）；保留 ctor / persistence / daily budget / session / pricing / config /
   cost summary / ollama_stats / check_*。
5. 測試 patch path 升級 4 site（line 384/417/552/587）+ 1 docstring：
   `app.layer2_cost_tracker._invalidate_h_state_async` →
   `app.layer2_cost_recording._invalidate_h_state_async`。
   `test_h_state_query_handler.py` 0 site 無需動。

## 驗證（Mac dev）
- pytest test_layer2.py: 82/82 cost-tracker pass + 12 TestLayer2Routes deselected
  (fastapi 缺失 Mac env 既有問題)。
- pytest test_h_state_query_handler.py: 52/52 pass。
- pytest test_layer2_escalation.py: 21/21 pass。
- pytest test_strategist_agent.py: 41/41 pass。
- 共 **196/196 cost-tracker-relevant test 全綠**。
- Smoke：import + ctor + 4 snapshot accessor 全綠。
- 3 production callsite（layer2_engine.py:65 / layer2_routes.py:42 /
  strategy_wiring.py:161）import 不變。

## E4 須在 Linux 跑
- fastapi available 環境跑 12 個 TestLayer2Routes；
- cargo test --release -p openclaw_engine --lib：應仍 2212/0（純 Python 變更，不應影響）。

## 高風險警告（E2 必查 3 點，per RFC §10）
1. ★ `_sync_to_rust_budget` daemon-thread fire-and-forget pattern bit-for-bit 一致
   （threading + asyncio 動態 import 保留）。
2. ★ `record_claude_cost` dual H state hint emit order：H2 → H5（Sub-task 3-3 RFC §6 +
   §8.2 thread safety contract）。
3. ★ Test patch path 4 site 升級全 grep verified；docstring legacy 提及亦更新。

## Commit
本 worktree 4 file change + 1 test file 為 1 commit（per prompt 規定）。
未 commit — 等 E2 + E4 → PM 統一 commit + push（CLAUDE.md §七 強制鏈
E1→E2→E4→QA→PM）。

## 不確定之處
- Mac fastapi 缺失導致 12 routes test deselect — 純 dev env gap，與本拆分無關。
- 順手 docstring/comment 雙語補全（per skill `bilingual-comment-style`），未動業務邏輯。
- TYPE_CHECKING import 防循環（sibling 不在 runtime path 引 Layer2CostTracker class）。
