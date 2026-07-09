# E1 — W1-T4 Healthcheck Dual-Syntax + [39] Cardinality Drift

**Date**: 2026-04-29 20:31 CEST
**Wave**: PA W1-T4（PA report `2026-04-29--strategy_name_attribution_cleanup_design.md`）
**Status**: ✅ Implementation done · 待 E2 審查 · 主會話統一 commit 第三波

完整內容見：`.claude_reports/20260429_203100_e1_w1t4_healthcheck_dual_syntax.md`

## 範圍

- 4 個 LIKE-based check dual-syntax 升級：`checks_ipc_edge.py` [6] TRAILING STOP；`checks_engine.py` [21] dust spiral fast_track + [28] phantom risk_close；`checks_ipc_edge.py` [4] phys_lock 按 PA §6.2 不改；[5] COST EDGE 已死不改
- 新增 [39] strategy_name_cardinality_drift 至 `checks_execution.py`（PA §6.1 推薦 checks_strategy.py 但該檔 1239 LOC pre-existing >1200，依 §九 治理改放 sibling）
- 接線 `__init__.py` + `runner.py`（cursor block 在 [38] 後）

## 驗證

- Mac py_compile 6 檔全綠
- Mac mock test [39] 5/5（PASS/WARN/FAIL/edge/except 5 path）全綠
- trade-core ad-hoc SQL：24h distinct strategy_name = **24** → [39] 預期首跑 FAIL
- trade-core dual-syntax compat：[6] old=2/new=2 / [21] old=0/new=0 / [28] old=0/new=0 → **delta=0 0 regression**
- trade-core 既有 baseline healthcheck 跑過（27 check 狀態與 CLAUDE.md §三 一致）

## 不確定 / 留尾

- [4] phys_lock 不改 dual-syntax 嚴格遵守 PA §6.2，task push back「保險建議加」未採納（理由：phys_lock reason ∈ static enum-like 已 clean）
- [28] `exit_reason IS NOT NULL` 範圍可能過寬（見 .claude_reports §6.3）
- 主會話 commit + push trade-core 後 first-run cron 才能驗 [39] full chain

## 治理對照

- §七 雙語注釋 ✅ / §九 1200 cap ✅（checks_engine.py +2 在 baseline+5 條款內）/ §四 5 live 硬邊界 0 觸碰 ✅ / PA §6.1 [39] 必加 ✅ / PA §6.2 升級 ✅

E1 IMPLEMENTATION DONE: 待 E2 審查
