# E4 Regression — G3-08 Phase 4 Sub-task 4-1 Strategist agent_state events (commit c8a4a55)

**Date**: 2026-04-27 CEST
**Main HEAD**: `c8a4a55`（Mac local ahead origin/main `c077e8c` by 1，**未 push**）
**Verdict**: **PASS**

## Summary

純 Python snapshot accessor + h_state aggregation hook。0 Rust diff 預期 cargo lib baseline 不動。E2 PASS_WITH_NITS 後 forward 到 E4。

| 引擎 | passed | failed | baseline | delta |
|---|---|---|---|---|
| Mac pytest 4 必要 suite (run 1) | **142** | 0 | n/a | 全綠 |
| Mac pytest 4 必要 suite (run 2) | **142** | 0 | n/a | 兩遍同綠 = 非 flaky |
| Linux cargo lib (run 1) | **2252** | 0 | 2252 | 對齊 STRKUSDT P0 wave baseline ✅ |
| Linux cargo lib (run 2) | **2252** | 0 | 2252 | 兩遍同綠 |

## Test breakdown

4 必要 suite 142 passed:
- `test_strategist_agent.py`: 含 +7 TestStrategistSnapshot tests（snapshot accessor 邊界）
- `test_h_state_query_handler.py`: 含 +9 跨 3 個 TestCase（_collect_agent_snapshots / TestStrategistAgentStateIntegration / TestStrategistAgentStateIncludeFilter / TestCollectAgentSnapshotsDefensive）
- `test_strategist_audit_wiring.py`: 2 既有
- `test_batch7_conductor_strategist.py`: 24 既有

## Stash isolation

**操作**：`git stash push -u -m "G3-09 in-flight Rust WIP (E4 isolate)" -- rust/`
- Stash 前：rust/ 25 modified + 3 new (cost_edge_advisor/) — G3-09 Phase A in-flight
- Stash 後：rust/ 全 clean，main HEAD = c8a4a55
- Pop 後：rust/ 25 modified + 3 new 全部還原，HEAD 仍 c8a4a55，stash dropped 無衝突 ✅

非 rust/ 的 unstaged 改動（helper_scripts/db/*、TOML × 3、E1 memory.md）保留在 working tree，不影響 cargo / pytest 結果。

## F-section grep verification（patch path migration）

| 檢查項 | 預期 | 實測 | OK? |
|---|---|---|---|
| `if inv is None` short-circuit in h_state_invalidator.py | 1 hit | line 347 ✓ | ✅ |
| `def get_strategist_snapshot` 主檔（strategist_agent.py） | 1 hit | line 802 ✓ | ✅ |
| `def get_strategist_snapshot` sibling（strategist_*.py） | 0 hits | 0 ✓ | ✅ |
| `_collect_agent_snapshots` def + caller in h_state_query_handler.py | 1 def + 1 call | line 406 def / line 737 call ✓ | ✅ |
| Strategist agent_state hook comments | 中英對照 line 79/82/800 | confirmed ✓ | ✅ |

## Mock 審查

- 4 必要 suite mock 範圍合 §五.5.1：fire-and-forget IPC boundary（h_state_invalidator.invalidate_async）、time-source、ai_service.get_ollama_client（外部 IO）
- 0 mock 業務邏輯 / snapshot 計算
- TestSafeSnapshotDefensive 系列驗 fail-closed（method missing / non-callable / non-dict / raises → returns None）— 與 §二 原則 #6（失敗默認收縮）一致

## 浮點 / SLA

- 浮點 N/A（純 snapshot accessor + dict aggregation，無 indicator 計算）
- SLA N/A（fire-and-forget hint，hot-path Rust h_state_cache poller 仍 10s 排程主導）

## Broader scan (Mac dev-only)

`pytest tests/ -k "strategist or h_state or layer2"`: 29 collection errors `ModuleNotFoundError: fastapi` — **全 pre-existing Mac dev-only 環境 gap**（CLAUDE.md §七，與 E4 memory 2026-04-27 cost_tracker_split / strategist_split 同 pattern）。0 net new fail。

## Push back / WARN（不阻塞）

1. **strategist_agent.py 829 LOC ⚠️ 警告線（§九 800 警告，1200 hard cap）**：E2 已 PASS（接近警告線 +29），下個 refactor wave 可考慮抽 50-100 行降回 < 800 緩衝。本 commit 在 §九 警告區但未越 hard cap，可放行。
2. **c8a4a55 未 push origin**：Mac local ahead by 1，origin HEAD = c077e8c。E4 task 設計階段允許（純 Python 0 Rust diff，Linux 端跑 origin/main HEAD baseline 等同跑 c8a4a55 baseline）。PM merge chain 完成後再 push。
3. **E2 LOW/NIT 5 條（task 描述）**：本 E4 階段不修，由 PM 決定是否進 G3-08 Phase 4 follow-up。

## 教訓

1. **Stash isolation 模式對 multi-agent in-flight branch 必跑**：本次 G3-09 Phase A 並行（agent ab0c139a1cd84908c）的 Rust 半成品改動若不 stash，cargo 會編譯失敗 / 跑出 false negative。`git stash push -u -- rust/` 精準隔離 Rust 子樹保留其他 unstaged（helper_scripts/db、TOML），完成後 pop 還原。**未來凡 Mac 主樹有跨 agent in-flight 改動時必跑此模式**，否則任意 E4 跑 Linux cargo 都會中毒。
2. **Patch path migration grep verify 模板再驗一輪**：本次 4-1 新增 `_collect_agent_snapshots`，grep 0 sibling hit + 1 主檔 def + 1 caller 完美 — 此模板從 cost_tracker_split (2026-04-27 memory) 沿用至今 3/3 PR 全綠，建議列入 E4 SOP。

## 報告位置

- E4 workspace: 本檔
- claude_report: N/A（本次走 E4 workspace 報告即可）

## Stash log

```
$ git stash push -u -m "G3-09 in-flight Rust WIP (E4 isolate)" -- rust/
Saved working directory and index state On main: G3-09 in-flight Rust WIP (E4 isolate)

$ git status --short  # post-stash
 M docs/CCAgentWorkSpace/E1/memory.md
 M helper_scripts/db/passive_wait_healthcheck/__init__.py
 M helper_scripts/db/passive_wait_healthcheck/checks_derived.py
 M helper_scripts/db/passive_wait_healthcheck/runner.py
 M settings/risk_control_rules/risk_config_demo.toml
 M settings/risk_control_rules/risk_config_live.toml
 M settings/risk_control_rules/risk_config_paper.toml

$ git stash pop  # post-regression
Dropped refs/stash@{0} (2f0fb9ad77701479388af941b34d547d78fe0959)
# rust/ 25 modified + 3 new untracked 全部還原，HEAD 仍 c8a4a55
```

## Linux cargo tail

```
test result: ok. 2252 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.52s
```
（run 1 + run 2 同數）
