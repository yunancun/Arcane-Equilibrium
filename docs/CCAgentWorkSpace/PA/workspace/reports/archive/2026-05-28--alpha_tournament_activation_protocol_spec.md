# PA Report — Alpha Tournament Activation Protocol Spec

**Date**: 2026-05-28
**Owner**: PA
**Ticket**: TODO v77 `P2-ALPHA-TOURNAMENT-ACTIVATION-SPEC`
**ETA budget**: 2-3 hr / actual: ~1.5 hr

---

## Deliverable

- **Spec path**: `srv/docs/execution_plan/specs/2026-05-28--alpha_tournament_activation_protocol.md`
- **Status**: SPEC-FINAL / IMPL-DEFERRED（runner code 不在本 spec 範圍 per operator mandate）

---

## Spec Summary

14 sections + §14 PA push-back self-audit。核心：

1. activation layer = SSOT (2026-05-26) 之上的「何時啟動 tournament 排名」gate；不取代 scoring + 5-gate + output lane。
2. C1 池 ≥ N=5 + C2 每策略 n_settled ≥ M=15（AND）→ activation。
3. Hysteresis 凍結：池 < N-1=4 自動回 Stage 0R direct path。
4. §4-§7 metric / K / X / re-entry penalty 全 slot 預留，標 `[future-iteration]`，待 activation 觸發後 PA + QC 拍板。
5. Sprint 2 hybrid 方案 C 三軌語意明確：A1+A2 主軌進池 / grid+ma 對照軌不計池 / bb_breakout+bb_reversion 30 天 catch-up 暫不計池。
6. 激活時點推估 ~Sprint 4-5（2026-08 至 2026-09）。

---

## 16 Root Principles Compliance

本 spec 為純 governance ladder，無 code / runtime / migration / 寫入面變動：

- 原則 1（單一寫入口）/ 2（讀寫分離）：無變動。
- 原則 3（AI ≠ 命令）：強化 — activation 後晉級 ≠ trading authority，仍須 Decision Lease + Guardian + 5-gate。
- 原則 4（不繞風控）：強化 — §5 晉級 invariant 明確不繞 5-gate。
- 原則 7（學習 ≠ 改寫 Live）：強化 — tournament 排名是 evidence input，不直接觸 live。
- 原則 11（P0/P1 邊界內自主）：強化 — activation = governance signal，未授任何超 P1 權限。
- 硬邊界（5-gate / live_reserved / OPENCLAW_ALLOW_MAINNET）：無觸碰。

**評級**：A 級（16/16 完全合規 + 硬邊界 0 觸碰）。

---

## Key Decisions（不重議，operator 拍板）

- N=5（pool size threshold）
- M=15（per-strategy n_settled threshold）
- N-1=4（hysteresis freeze threshold）

任何閾值未來變更走 AMD amendment（per spec §11）。

---

## Decisions Made by PA（spec 內 deferred 但本報告紀錄推理）

| 決策 | rationale |
|---|---|
| Hysteresis N vs N-1=4 而非 N vs N | 避免 N=5 邊界震盪導致 tournament on/off 抖動；下行 1 grace |
| 對照軌 grid+ma 不計池 | per SSOT §3 B0 baseline-only；計入會把 N=5 灌水且違反「不做 textbook 拯救 engineering」立場 |
| funding_arb retired 不計池 | per AMD-2026-05-26-01 升格 Retired closed |
| Re-entry 90 天 / 2 次 cap | 推估 slot 值；防 yo-yo 震盪；但本身為 `[future-iteration]` |
| 預估激活 ~Sprint 4-5 | 基於 A1-A5 IMPL pace + demo accumulation rate；誠實標「最早合理」非承諾 |

---

## Push-Back 自評（5 條最強反對 + mitigation）

詳見 spec §14。摘要：

1. **N=5 / M=15 無 empirical anchor** → AMD path 開放 + 凍結不傷 trading。
2. **M=15 vs SSOT n≥30 不一致** → 分層分工（跨策略可比 vs single-strategy edge）。
3. **對照軌排除讓 N=5 難達** → 凍結 fallback 不傷 + 可改 N=4。
4. **activation 拍板早 → 目標管理反模式** → §13 Non-Goals + Sprint dispatch reminder。
5. **30+ slot = dead spec** → governance ladder ≠ implementation spec；operator mandate。

**最強 push-back**：#1（無 empirical anchor）。但 mitigation sufficient — 凍結期內 trading 不受影響 + 6-9 月窗口足夠 amend。

---

## Follow-up（PM 收尾）

1. 本 spec land 後，PM 在 SSOT (`2026-05-26--alpha_tournament_ssot_spec.md`) §9 cross-document pointer 加本 spec link。
2. `docs/README.md` index 加本 spec。
3. TODO v77 `P2-ALPHA-TOURNAMENT-ACTIVATION-SPEC` ticket 引用本 spec + 標 SPEC-FINAL。
4. Sprint 2 dispatch packet（PM 收尾）加 reminder：tournament 不激活，內部走 Stage 0R direct path。

---

## Hand-off

無下游 E1 / E2 / E4 派發。本 spec 是 governance ladder permanent doc，激活觸發後（~Sprint 4-5）再開新 PA ticket 拍板 §4-§7 slot 值 + runner code 設計。

---

PA DESIGN DONE: report path: srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-28--alpha_tournament_activation_protocol_spec.md
