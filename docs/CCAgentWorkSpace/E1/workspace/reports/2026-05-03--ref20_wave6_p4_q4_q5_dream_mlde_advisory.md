# E1 Report — REF-20 Wave 6 Batch 6B (P4-Q4 + P4-Q5)

**Date:** 2026-05-03
**Owner:** E1
**Branch:** main (uncommitted; awaiting E2 + E4 + MIT review)
**Sign-off detail:** `.claude_reports/20260503_153000_ref20_wave6_batch6b_p4_q4_q5.md`

## TL;DR

順序執行 P4-Q4 (DreamEngine `generate_replay_candidates()` API surface-add) + P4-Q5 (MLDE `rank_and_veto_replay_candidates()` advisory veto chain) — Wave 6 P4 advisory chain 完成。0 既有 module mutation (NOT fork)；V043 `replay.mlde_replay_veto_log` migration land (reserved → land per ledger v1.5)；pytest 12/12 PASS (9 mandatory + 3 bonus defensive)；既有 70/70 regression PASS.

## 修改摘要

| 檔 | 動作 | 變動 |
|---|---|---|
| `program_code/local_model_tools/dream_engine.py` | Edit | Surface-add Q4 (404→954 LOC); ReplayIntent / ReplayCandidate dataclass + generate_replay_candidates() module-level helper |
| `program_code/ml_training/mlde_shadow_advisor.py` | Edit | Surface-add Q5 (398→812 LOC); RankedCandidate / RankAndVetoGateInputs / VetoReasonLiteral + rank_and_veto_replay_candidates() helper |
| `sql/migrations/V043__replay_mlde_replay_veto_log.sql` | Create | 260 LOC; Guard A + 3 CHECK constraints |
| `sql/migrations/REF-20_RESERVATION.md` | Edit | V043 reserved → land + revision history v1.5 |
| `program_code/local_model_tools/tests/test_dream_engine_replay_candidates.py` | Create | 6/6 PASS (5 mandatory + 1 bonus) |
| `program_code/ml_training/tests/test_mlde_replay_veto.py` | Create | 6/6 PASS (4 mandatory + 2 bonus) |

## 設計選點 (供 E2 / MIT review)

1. **NOT fork**：surface-add 至既有 module — caller `from local_model_tools.dream_engine import ...` / `from ml_training.mlde_shadow_advisor import ...` 即可。0 環境變數新增 / 0 sys.path 改動。對齊 V3 §11 P4「MLDE / DreamEngine are called by Replay as advisory participants; they are not rewritten into replay-only tools」。
2. **Pure compute**：兩函式 0 trading.* / learning.* / replay.* 寫；caller (replay_routes.py POST /run) 自行決定送入 V036 verified insert function 或下游 gate 拒絕。
3. **Advisory only** (V3 §11 P4 KPI)：rank_and_veto 不從 candidate 集合移除被 veto 候選；只 emit veto_reason + advisory_summary。硬拒絕由 calibration_gate.py + V036 verified insert function 負責。
4. **Gate-by-data-availability**：PBO / DSR `gate_inputs` None 時對應 gate 自動跳過 (非 fail-closed)。
5. **5 veto reason allowlist** 與 V043 `chk_replay_mlde_veto_reason` 對齊。
6. **Reproducibility**：dream_engine seed 由 SHA-256 over canonical bytes derive (避 PYTHONHASHSEED 隨機化)；同 intent + 同 seed → 同 candidate 集 (test 2 驗)。

## Ambiguities → 詳見 sign-off report §5

- A. 兩檔 LOC 過 800 警告 (dream_engine 954 / mlde_shadow_advisor 812) — 建議 PA / PM accept governance exception + 開 P2-REF20-W6-REFACTOR ticket
- B. V043 是否設 FK 至 V045.run_state — 我採不設 (與 V045 同 fixture-vs-migration 順序處理；veto row 可獨立 subprocess 生命週期持久化)
- C. cost_edge_ratio 方向 — 我採 edge ÷ cost (語意上「edge 主導 cost」當有 0.8 倍以上才有意義)；test 2 數值對齊。請 QC 確認 V3 §12 #24 方向定義
- D. ConfidenceLiteral 4-value vs V3 execution_confidence 3-value — 4→3 mapping 由 caller 在持久化前處理；本函式保留 high/medium 區分能力供下游 ranker

## Pytest output

```
12 passed in 0.03s (5 Q4 + 4 Q5 mandatory + 3 bonus)
70 passed in 0.05s (regression — local_model_tools/tests/ + test_mlde_shadow_advisor.py)
```

## Cross-reference

- Workplan SoT: `docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md` §4 Wave 6 R20-P4-Q4 + R20-P4-Q5
- V3 contract: `docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md` §11 P4 + §12 #6 / #17 / #24
- Migration ledger: `sql/migrations/REF-20_RESERVATION.md` row V043 + revision history v1.5
- Sign-off: `.claude_reports/20260503_153000_ref20_wave6_batch6b_p4_q4_q5.md` (本檔詳述)
