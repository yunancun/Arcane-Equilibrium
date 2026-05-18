# W-AUDIT-8a B-REM-1 — Branch Rebase Report

**Date**: 2026-05-18
**Author**: E1
**Task**: Procedural rebase `feature/w-audit-8a-b-rem-1-dispatch-snapshot-contract`
onto `main`，no IMPL changes，per PM dispatch + E2 review SHOULD-FIX。

## 任務摘要

E2 review on `441599a7` APPROVE-CONDITIONAL with procedural rebase要求：

- Branch 落後 main 3 commits（PM spec：merge-base `5cfe1f68` / main `59d9338b`）
- 預期單一 EOF conflict on `step_4_5_dispatch.rs`
- 預期 post-rebase `cargo test -p openclaw_engine --lib` = **2978 / 0 / 1**
- 預期 force-push 後 ready for E4 regression

## 修改清單

### 程式碼

| 檔案 | 動作 | 描述 |
|---|---|---|
| `rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs` | conflict-resolve | 移除 3 行 conflict markers (`<<<<<<< HEAD` / `=======` / `>>>>>>> 441599a7`)，採納 branch 側 245-line test mod + EOF newline。最終 1946 lines |

### Git refs

| Ref | Before | After |
|---|---|---|
| `feature/w-audit-8a-b-rem-1-dispatch-snapshot-contract` (local + origin) | `441599a7` | `49975eeb` |
| Main worktree HEAD (srv/) | `main` clean | `main` clean (1b614daf) |

新 commit `49975eeb` 的 parent = main `1b614daf`（spec 寫 main = 59d9338b，但
我 fetch 完 main 已被 sibling 推到 1b614daf — Rebase target 永遠取 fetch 完
最新 origin/main）。

## 關鍵 diff

Step_4_5_dispatch.rs conflict resolution（在 isolated worktree /tmp/e1-rebase-wt 完成）：

```diff
@@ -1701,7 +1701,6 @@
     }
 }
-<<<<<<< HEAD
-
-=======
+// =============================================================================
+// W-AUDIT-8a B-REM-1: Dispatch Snapshot Contract Tests
+// =============================================================================
@@ -1946,1 +1946,0 @@
 }
->>>>>>> 441599a7 (feat(w-audit-8a-b-rem-1): dispatch snapshot contract tests + try_clone_panel_snapshot helper)
```

最終檔尾：1946 lines，bytes `... drop(write_attempt);\n    }\n}\n`（single
trailing newline，per Rust 規範）。

## 治理對照

| 項目 | 結果 |
|---|---|
| Mandate「procedural rebase / no IMPL changes」 | 達成。Branch diff vs old `441599a7` = 0（只是 parent 換了） |
| 預期 conflict count = 1 | 達成（step_4_5_dispatch.rs EOF） |
| Resolution 規則「accept BOTH — keep test mod + single trailing newline」 | 達成 |
| Post-rebase test count = 2978 / 0 / 1 | **達成（2978 passed / 0 failed / 1 ignored）** |
| Post-rebase b_rem_1 specific tests = 6 / 0 / 0 | **達成** |
| Force-push successful | 達成（`+ 441599a7...49975eeb forced update`） |
| Main branch in srv/ restored clean | 達成（HEAD `1b614daf`，no merge/rebase 殘留） |
| 沒做 commit on srv/ 主 worktree | 達成（用 `/tmp/e1-rebase-wt` 隔離 worktree） |
| 沒派下游 sub-agent | 達成 |

## Test 驗證

```
$ cd /tmp/e1-rebase-wt/rust && cargo test -p openclaw_engine --lib
test result: ok. 2978 passed; 0 failed; 1 ignored; 0 measured; 0 filtered out; finished in 0.71s

$ cargo test -p openclaw_engine --lib b_rem_1
test result: ok. 6 passed; 0 failed; 0 ignored; 0 measured; 2973 filtered out; finished in 0.00s
```

6 B-REM-1 tests 全 pass：

- `b_rem_1_invariant_1_funding_slot_present_surface_some_age_readable`
- `b_rem_1_invariant_2_oi_slot_present_surface_some_age_readable`
- `b_rem_1_invariant_3_writer_holds_lock_soft_fail_no_panic`
- `b_rem_1_invariant_4_slot_missing_no_synthetic_neutral`
- `b_rem_1_slot_present_inner_none_returns_none`
- `b_rem_1_helper_releases_read_guard_before_return`

## 不確定之處 / 風險

### 1. Multi-session race incident（已 root-cause + workaround）

第一次 attempt 在 srv/ 主 worktree 跑 rebase 時，sibling session 在我
`git stash` 與 `git rebase --continue` 之間：
- 寫了 untracked `docs/adr/0023-source-availability-schema.md`
- `git add` 把它 stage 到 index

結果 `git rebase --continue` 把它一起 commit，commit message 也被改成
`docs(adr): ADR-0023 SourceAvailability schema`（不是 B-REM-1 commit message）。

**Workaround**：reset 後改用 `git worktree add /tmp/e1-rebase-wt <branch>`，
完全隔離 sibling 影響。第三次 attempt 一次過。

**遺留**：stash@{0}（E1-rebase-mid-2，含 memory/MEMORY.md 的 sibling diff）
pop 時部分 hunk 不能 apply（sibling 已 disk-level 改），stash 自動保留。
我沒 force pop，留 stash@{0} 給 sibling 自處理。

### 2. Main HEAD drift between PM spec 與 runtime

PM spec 寫 main = `59d9338b`，但我 rebase 時 main 已被 sibling 推到
`1b614daf`（多了一個 ADR-0023 commit，content 與 sibling 第一次污染我
rebase 的相同）。Rebase 結果不受影響（branch 仍 ahead of main by 1，post-
rebase test 仍 2978），只是 verify「branch behind main」要用 runtime 值。

### 3. 沒做（per mandate）

- 沒 commit B-REM-1 程式邏輯改動（rebase only，IMPL diff zero）
- 沒派 sub-agent
- 沒做 E4 regression（branch 已 ready for E4，但那是 E4 mandate）
- 沒清 stash@{0}（sibling-owned）

## Operator 下一步

1. **E4 regression** on `feature/w-audit-8a-b-rem-1-dispatch-snapshot-contract@49975eeb`
   （Linux runtime，含 db migration / engine restart / 24h soak optional 視 dispatch 形勢）
2. **QA Audit** if downstream worktree merge sequencing requires it（per PA report §6.1
   acceptance + multi-worktree dependency graph）
3. PM merge sequence decision — B-REM-1 與 sibling worktree `feature/phase-1b-runtime-activator`
   共享 `step_4_5_dispatch.rs`，merge order 可能 matter。E2 report 建議
   Phase 1b 先 merge 是 B-REM-1 後 merge（但已併 phase-1b merge to main = `c737a1e4`，
   所以 B-REM-1 現在直接基於 phase-1b 後狀態）
4. 如果 E4 PASS → PM 統一 commit + push（per E1 完成序列禁直接 commit）

E1 IMPLEMENTATION DONE: 待 E2 audit + E4 regression（report path:
`/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-18--w_audit_8a_b_rem_1_rebase.md`）
