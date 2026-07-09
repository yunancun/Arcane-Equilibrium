# E2 Re-Review — G3-09 Phase B Wave 1 E2-return fix

Date: 2026-04-28
Reviewer: E2 (adversarial)
Worktree: srv/.claude/worktrees/agent-a9002481353677810
Branch: worktree-agent-a9002481353677810
Base HEAD: cf34e96
Fix scope: 5 files (4 Python + CLAUDE.md), 0 Rust (Rust diff vs base = pre-existing Wave 1 work, untouched by this fix)

## Verdict

**PASS to E4** — all 3 E2-return findings (HIGH-1 / MED-1 / LOW-2) addressed cleanly. Zero regression to Wave 1 core. Zero Rust touch by this fix. Fix is a clean, scope-disciplined refactor + 1 row CLAUDE.md addition + 1 fallback hook.

---

## 改動範圍

Fix-only files (5):
- `helper_scripts/db/passive_wait_healthcheck/checks_cost_edge.py` (NEW, 370 LOC, sibling)
- `helper_scripts/db/passive_wait_healthcheck/checks_derived.py` (1304 → 990 LOC)
- `helper_scripts/db/passive_wait_healthcheck/__init__.py` (import + __all__ split)
- `helper_scripts/db/passive_wait_healthcheck/runner.py` (import switch + LOW-2 fallback @ line 153-176)
- `CLAUDE.md` (+1 row §九 singleton table @ line 459: `CostEdgeAdvisorDbSlot`)

Note: `git diff cf34e96 --stat` shows ~711 lines of Rust deltas across 6 files — these are the **prior-reviewed Wave 1 baseline** (commit `adbc92e` E2-reviewed scope), not the fix scope. The fix is purely Python + CLAUDE.md per E1 task brief.

## 3 Findings — Re-verification

### HIGH-1 — checks_derived.py 1304 LOC > 1200 hard cap → **PASS**

Verified:
- `wc -l checks_derived.py = 990` ≤ 1200 ✅ (passes §九 hard cap)
- `wc -l checks_cost_edge.py = 370` ≤ 800 ≤ 1200 ✅ (well below warning line)
- New sibling contains exactly `check_cost_edge_advisor_status` (1 function, lines 50-370)
- `check_h_state_gateway_freshness` + `check_dust_spiral_noise_in_ef` correctly **stay** in checks_derived.py (per E1 spec — avoid scope creep)
- `__init__.py` correctly imports from new sibling (lines 71-78) + adds to `__all__` (line 120)
- `runner.py` import correctly switched (line 73-80) + cursor-block call at line 351
- Pattern mirrors existing checks_engine / checks_strategy / checks_ipc_edge sibling decomposition

Adversarial probe: `grep -rn "check_cost_edge_advisor_status" helper_scripts/db/passive_wait_healthcheck/` returns 12 hits, **all in correct locations** — definition (checks_cost_edge.py:50), 2× import (__init__.py + runner.py), 2× usage (runner.py:172 fallback + 351 cursor), 7× docs/comments. No stale orphan reference left in checks_derived.py.

### MED-1 — CostEdgeAdvisorDbSlot singleton 未登記 §九 表 → **PASS**

Verified:
- `grep "CostEdgeAdvisorDbSlot" CLAUDE.md` = 1 hit @ line 459 ✅
- Row structure mirrors `HStateCacheSlot` row immediately above (same Singleton column / 創建位置 / 導入方式 layout)
- Description correctly explains: late-injected slot pattern, 30s populate-timeout, `Arc<RwLock<Option<Arc<DbPool>>>>` semantics, slot=None → in-memory counter fallback, slot injected → DB INSERT path, Engine restart auto-clear via Arc drop
- Cross-references CLAUDE.md §二 原則 #6 (失敗默認收縮) + 原則 #8 (可審計) — correct governance attribution
- Bilingual: row description in Chinese with English code identifiers (matches §九 row style)

Adversarial probe: row references `rust/openclaw_engine/src/main_boot_tasks.rs` as 創建位置. Verified file exists in worktree (mtime 2026-04-28 01:50). No stale path.

### LOW-2 — healthcheck [30] coverage regression on DB-down → **PASS**

Verified (option A: env-gate sentinel fallback):
- `runner.py` lines 153-176: `except Exception as e:` block on `_get_conn()` failure correctly:
  1. Prints `[FATAL] DB connect failed: {e}` (operator visibility)
  2. Calls `check_cost_edge_advisor_status(cur=None)` — Phase A code path (pure filesystem, no DB cursor)
  3. Prints result with explicit `(db-down fallback)` annotation in slot label
  4. Inner `try/except Exception as ce` wraps the sentinel call so a sentinel-side raise can't break the DB-fail exit path (defense in depth, fail-soft)
  5. Returns exit code 2 (DB connect error, unchanged contract)

Code-trace smoke (executed locally on Mac, Python 3.9):
- env=0 (unset) → `check_cost_edge_advisor_status(cur=None)` → `PASS | OPENCLAW_COST_EDGE_ADVISOR=unset (≠'1') — env=0 dormant by design...`
- env=1 (Python 3.9 lacks tomllib) → returns `WARN | tomllib unavailable...` — graceful degrade, not crash

The Phase A code path early-returns at lines 228-233 of `checks_cost_edge.py` when `cur is None`:
```python
if cur is None:
    return ("PASS", f"env=1 + [cost_edge].enabled={enabled} ... (Phase A invariants; no DB cursor for Inv 3/4)")
```
This correctly preserves the env=1 invariant verification path that Phase A originally provided OUTSIDE the cursor block.

Adversarial probe: what if Phase B Inv 3/4 silently masks Phase A invariant FAIL? Confirmed not possible — Phase A invariants 1+2 are evaluated BEFORE the `if cur is None` early-return, so a TOML-missing or module-files-missing FAIL is reported regardless of whether `cur` is provided.

---

## §九 8-条 checklist — fix files

| Item | Status |
|---|---|
| 改動範圍與 PA 方案一致 | ✅ E1 task brief 5 files, fix touches exactly those 5 |
| 沒有 except:pass 或靜默吞異常 | ✅ all except blocks return tagged WARN/FAIL with msg |
| 日誌使用 %s 格式（非 f-string） | ✅ N/A — only `print()` to stdout (cron-style sentinel), not logger |
| 新 API 端點有 _require_operator_role() | ✅ N/A — no API endpoints touched |
| except HTTPException: raise 在 except Exception 之前 | ✅ N/A — no HTTPException handlers |
| detail=str(e) 已改為 "Internal server error" | ✅ N/A — no FastAPI raise |
| asyncio 路由中沒有 blocking threading.Lock | ✅ N/A — pure synchronous cron sentinel |
| 沒有私有屬性穿透（._xxx） | ✅ no `._private` access in fix files |

## OpenClaw 9 條 §3 checklist — fix files

| Item | Status |
|---|---|
| 跨平台 `/home/ncyu` `/Users/[^/]+` grep | ✅ 0 hits in fix files |
| 雙語注釋（MODULE_NOTE / docstring / inline 中英） | ✅ checks_cost_edge.py has full bilingual MODULE_NOTE (EN+中) + bilingual docstring + inline 雙語 comments (6+ MODULE_NOTE/模組 hits) |
| Rust unsafe / unwrap / panic | ✅ N/A — fix is Python only |
| 跨語言 IPC schema | ✅ N/A — no IPC change |
| Migration Guard A/B/C | ✅ N/A — V026 is in prior Wave 1 baseline (untracked in this diff), not fix scope |
| healthcheck 配對 | ✅ this fix IS the healthcheck cleanup; [30] slot preserved + db-down sentinel added |
| Singleton §九 表登記 | ✅ MED-1 fix added `CostEdgeAdvisorDbSlot` row |
| 文件大小 800 / 1200 | ✅ checks_derived 990 (clean), checks_cost_edge 370 (well under warn), runner 473 (clean) |
| Bybit API 改動 | ✅ N/A — no Bybit touch |

## 對抗反問結果

1. **Q: HIGH-1 split 真綠？是否漏 import / 漏 reference？**
   A: `grep -rn check_cost_edge_advisor_status` 12 hits 全部對的位置。`__init__.py` __all__ 加了。runner.py 兩處 (cursor + db-down fallback) 都從新 sibling import。**驗 PASS**.

2. **Q: 為何 `check_h_state_gateway_freshness` 沒一起搬？**
   A: E1 task brief explicitly stated "per E2 spec E1 自決" — 避免 scope creep。checks_derived.py 砍到 990 LOC 已 well under cap，沒必要再搬。新 sibling 純 single-purpose（cost_edge）更清晰。**驗合理**.

3. **Q: LOW-2 fallback 在 DB-down 時真的會跑嗎？**
   A: runner.py:152 `_get_conn()` 在 except 區塊外面，DB 連線失敗會 raise exception 進入 except 區塊（line 153）。然後立即 print FATAL + 呼叫 sentinel + return 2。Code path 直線、無 short-circuit、無 silent skip。**驗 PASS**.

4. **Q: Phase A invariants 在 cur=None fallback 真的執行？**
   A: Phase A invariants 1 (TOML parse + [cost_edge] section) 在 line 142-200，全部在 `if cur is None:` (line 228) 之前。invariant 2 (Rust module files exist) 在 202-216，也在 cur is None 之前。所以 env=1 + cur=None 仍會 verify 兩個 Phase A 不變量。**驗 PASS**.

5. **Q: 0 production behavior change？**
   A: `git diff cf34e96 -- rust/` 顯示 711 行 Rust delta 是**先前** Wave 1 work（mtime 01:13-01:28 + commits messages prove it），fix 本身不碰 Rust。Python 重構是 pure file-move + import-rewire；function semantics byte-identical（同 signature，同 body except DB-down branch added in runner）。**0 production behavior change confirmed**.

6. **Q: Wave 1 核心仍在？**
   A: V026 migration / sticky_ts / 5-arg shim / persistence test 都在 untracked / 已 staged files (Rust mtime 01:13-01:28)，fix 不動。SSH 確認 Linux origin HEAD `528805d` 含全 Wave 1 commits（22c57dc test / 9303a3b sticky / 00682ef Phase A / af66ac1 integration）。**驗 PASS**.

7. **Q: 無新 regression？**
   A: pytest helper_scripts/db = 45 passed / 8 failed。8 failed 全部 `TestSignalsWriterFreshness` + `TestIntentsCounterFreeze` — `git stash push` 後再跑同樣 8 failed → **驗證為 pre-existing baseline failures**，與 fix 無關。**驗 PASS**.

8. **Q: §九 + OpenClaw 9 條本次引入新違規？**
   A: 無。Fix 改善 §九（HIGH-1 文件大小 + MED-1 singleton 表 + LOW-2 healthcheck 配對），無新違反。**驗 PASS**.

## Findings

| Severity | Location | Description | Action |
|---|---|---|---|
| (none) | — | All 3 prior E2-return findings addressed; no new findings | PASS |

## E5 / FA / TW 後續 ticket（非 blocker）

無新建議。原 review 中提到的 MED-2 main.rs / LOW-1 main_boot_tasks.rs follow-up tickets 不在本次 fix 範圍（per task brief「不需修」）。

## Commit message readiness

Fix 範圍乾淨，可寫一個簡潔 commit：

```
fix(g3-09-pb1): address E2-return findings — split + singleton + db-down sentinel

- HIGH-1: extract check_cost_edge_advisor_status from checks_derived.py
  (1304 → 990 LOC) into sibling checks_cost_edge.py (370 LOC) per
  CLAUDE.md §九 1200-line hard cap
- MED-1: register CostEdgeAdvisorDbSlot in CLAUDE.md §九 singleton table
  (mirrors HStateCacheSlot row pattern)
- LOW-2: preserve [30] env-gate invariant verification on DB-down by
  invoking check_cost_edge_advisor_status(cur=None) in runner.py DB-fail
  exception handler (Phase A code path, pure filesystem)

Pure Python + docs change (5 files); 0 Rust touch (Wave 1 baseline
unchanged). pytest helper_scripts/db: 45 passed / 8 pre-existing
failures (TestSignalsWriterFreshness + TestIntentsCounterFreeze,
unrelated baseline; verified via git stash).
```

Ready for commit + push.

---

## Summary

PASS to E4. Fix is scope-disciplined (5 files exactly), addresses all 3 E2-return findings cleanly, introduces zero new violations, regresses zero pre-existing tests, and touches zero Rust (Wave 1 core untouched per fix-only diff). No blocker.
