# E4 Regression — G3-08 Phase 4 Strategist Split (commit 6fac0ca)

**Date**: 2026-04-27 15:12 CEST
**Worktree**: `srv/.claude/worktrees/agent-ad7ef0f891ff580d9`
**HEAD**: `6fac0ca`
**Verdict**: **PASS**

## Summary

純 Python file structure refactor (1200→792 + 3 NEW sibling 369/224/169)，Rust 0 觸碰。

| 引擎 | passed | failed | baseline | delta |
|---|---|---|---|---|
| Mac pytest 4 必要 suite (run 1) | **126** | 0 | n/a | 全綠 |
| Mac pytest 4 必要 suite (run 2) | **126** | 0 | n/a | 兩遍同綠 = 非 flaky |
| Mac pytest broader strategist/h_state/layer2 | 301 | 15* | n/a | *15 fail = `httpx` 缺套件 Mac dev-only pre-existing，base commit 0611de0 同 fail 已驗 |
| Linux cargo lib (run 1) | **2252** | 0 | 2252 | 對齊 ✅ |
| Linux cargo lib (run 2) | **2252** | 0 | 2252 | 兩遍同綠 |

## Files split

| 檔案 | LOC | <1200 §九 hard cap |
|---|---|---|
| strategist_agent.py | 792 | ✅ (was 1200, 主目標達成) |
| strategist_edge_eval.py (NEW) | 369 | ✅ |
| strategist_weights.py (NEW) | 224 | ✅ |
| strategist_cognitive.py (NEW) | 169 | ✅ |

## Mock + 浮點 + SLA

- Mock 0 變動（純 file structure refactor）
- 浮點 N/A（無 indicator 改動）
- SLA N/A（無 hot-path 改動）

## Push back / WARN（不阻塞）

1. strategist_agent.py 792 接近 §九 800 警告線（差 8 行）— 下個 refactor wave 抽多 50-100 行可進 ≤700 緩衝區
2. 30 個 fastapi/httpx 缺套件 collection error / fail 為 Mac dev-only pre-existing（CLAUDE.md §七）
3. 5 個 `record_ollama_call` DeprecationWarning（pre-existing，建議下次切 `record_call(provider='ollama', ...)`）

## 教訓

1. Mac dev-only pre-existing failures 識別三步驟：grep ModuleNotFoundError → checkout base 跑同 test 驗 → 引用 CLAUDE.md §七 — ≤2min 即可 disambiguate split 引入 vs pre-existing。

## 報告位置

- claude_report: `.claude_reports/20260427_151252_e4_regression_strategist_split.md`
- E4 workspace: 本檔
