# Amendment AMD-2026-05-09-04 - Demo→LivePending Promotion Evidence Push

**對應 spec**: SM-04 Risk Governor · LG-X-01 Live Promotion Gate · DOC-01 §5.5 / §5.7 · ADR-0021 (proposed) · V079 schema migration
**日期**: 2026-05-09
**作者**: PM
**狀態**: Active
**索引**: `SPECIFICATION_REGISTER.md` Amendments section
**TODO 連結**: `P0-EDGE-1` / `P0-LG-3` supervised-live gate / `W-AUDIT-6c` portfolio tail risk

---

## 1. Decision Summary

Operator-authorized commit `48227607` introduces:

1. A **promotion_evidence producer** in `edge_estimator` hourly cycle that
   pushes `selection_bias` + `tail_risk` evidence into the
   `learning.strategy_trial_ledger` table.
2. A new schema **V079 migration** persisting `trial_sharpes` per strategy
   per symbol as cross-section trial samples.
3. SM-04 Risk Governor + LG-X-01 Live Promotion Gate evidence collection
   wiring — promotion gate now reads from a real evidence ledger instead of
   in-memory transient state.

This amendment records planning authority + closes the long-standing
governance gap **「DSR/PBO module Implemented but not Wired」**, while
explicitly limiting the new wiring's claim to **cross-section consistency
test**, NOT a true PBO over N strategy variants.

---

## 2. 為什麼選 hourly cycle push 而非 on-demand pull

### 2.1 Edge estimator hourly cycle 已是穩定 cron 節點

`edge_estimator` scheduler 每小時跑一次，由 `flock` leader election 保護
（CLAUDE.md §九 singleton table）。把 promotion evidence push 掛在已有
cycle 上：

- 不引入新 background thread / 新 leader election
- evidence 寫入頻率與 edge estimate 刷新節奏對齊（避免 promotion gate
  讀到「邊界 edge」+「過期 evidence」的不一致快照）
- 失敗模式單一：edge estimator 死則 evidence push 同步死，下游 promotion
  gate 改讀 `LOW_SAMPLE`，**fail-closed 而非 fail-open**

### 2.2 為什麼 schema 寫 `learning.strategy_trial_ledger` 而非 in-memory

被否決的替代方案：把 trial_sharpes 留在 promotion gate process 的 in-memory
deque。否決理由：

- promotion 決策 **必須 audit trail-able**（§二 原則 8 「交易可解釋」），
  in-memory state 重啟即丟，違反 audit chain reconstruction
- promotion gate process 可能跨 worker / 跨重啟，in-memory 無法 share；
  PG ledger 是唯一能讓多 reader 看一致 evidence 的 SoT
- V079 migration 已附 Guard A/B/C（CLAUDE.md §七 SQL migration 規範）

### 2.3 為什麼 evidence 包 `selection_bias` + `tail_risk` 兩條

`selection_bias` 對應「strategy 在 N symbol 上的 Sharpe 分散度是否符合
random sampling 期望」 —— catch 「同一策略只在 1-2 個 symbol 撈到正
Sharpe」這類 cherry-picking。

`tail_risk` 對應「最差 N% percentile 的 PnL 是否仍可承受」 —— catch
「平均 Sharpe 好但長尾 catastrophic」這類藏雷。

兩條合起來覆蓋 promotion gate 最常踩的兩類 illusion，**但仍不是完整
W-AUDIT-6c portfolio tail risk**（後者要看 cross-strategy + cross-symbol
correlated drawdown），完整版留待 R-3 Hypothesis Pipeline IMPL。

---

## 3. trial_sharpes 持久化語義（QC NEW-V3-2 push back 採納）

**重要範圍限制**：`trial_sharpes` 在 V079 schema 是 **per-symbol Sharpe
as cross_section trial sample**，是同一策略在 N 個 symbol 上的
Sharpe 一致性測試。這 **不是** 對 N 個 strategy variant 跑 PBO（Probability
of Backtest Overfitting）。

QC 在 v3 review 給的 push back（NEW-V3-2）採納：

- 真 PBO 需要 N variant × M backtest fold 的雙維度 deflation；當前 schema
  只有 1 strategy × N symbol cross-section
- 把 `trial_sharpes` 標榜為 PBO 是 evidence overclaim，違反 §二 原則 10
  「認知誠實」
- 真 PBO 留待 ADR-0021 R-3 **Hypothesis Pipeline as First-Class Governance
  Object** 實裝後，由 Hypothesis 物件持有 variant ledger + fold result，
  在 promotion gate 上層做 deflation

當前 amendment 範圍：把 V079 + producer 定位為 **cross-section consistency
gate**（catch single-symbol cherry-pick），不冒充 PBO。

---

## 4. Implementation Facts

Confirmed source behavior as of `48227607` (2026-05-09):

1. V079 migration 在 `learning` schema 建 `strategy_trial_ledger` table，
   key 是 `(strategy_name, symbol, snapshot_at)`，附 Guard A/B/C。
2. `edge_estimator_scheduler` 每小時 cycle 末尾呼叫
   `promotion_evidence_producer.push()`。
3. Producer 計算 `selection_bias` + `tail_risk` 兩條 evidence，寫入
   `strategy_trial_ledger`。
4. SM-04 Risk Governor / LG-X-01 promotion gate 在評審 promotion
   candidate 時 SELECT 最近 N 小時 ledger row 作為 evidence input。
5. Ledger SELECT 失敗 / 樣本不足 → promotion gate 標 `LOW_SAMPLE` →
   fail-closed 拒絕 promote，不放行。
6. `trial_sharpes` column 持久化 per-symbol Sharpe array，不是
   per-variant Sharpe array（範圍限制見 §3）。

---

## 5. Authority Boundary

1. evidence producer 只 **寫** `learning.strategy_trial_ledger`；不寫
   `trading.fills` / `replay.simulated_fills` / `mlde_*` / authorization
   等 fact 物件。
2. SM-04 / LG-X-01 promotion gate 是唯一 reader；其他 module（GUI / ML
   training / Dream Engine）若 SELECT 此 table 必須只讀（§七 讀寫分離）。
3. evidence ledger 是 **promotion gate 的 evidence input**，不是 live
   authorization grant；promotion 仍需 supervised gate（`P0-LG-3`）+
   Decision Lease + Rust execution authority。
4. `trial_sharpes` 範圍限定為 cross-section consistency；任何下游 doc /
   GUI / report 不得把它表述為 PBO 結果（§二 原則 10）。
5. V079 schema 在 `learning` namespace；不污染 `trading.*` / `replay.*`
   / `governance.*` namespace。

---

## 6. Supersedes

| 舊狀態 | 新狀態 |
|---|---|
| 「DSR/PBO module Implemented but not Wired」 | DSR/PBO module 的 cross-section consistency 部分已 wired 進 SM-04 + LG-X-01；真 PBO 仍 pending R-3 Hypothesis Pipeline IMPL |
| Promotion gate 用 in-memory transient state | Promotion gate 讀 `learning.strategy_trial_ledger` PG ledger（audit-traceable） |
| trial_sharpes 為 ephemeral（重啟即丟） | trial_sharpes 在 V079 schema 持久化（per-symbol Sharpe array） |

---

## 7. References

- Source commit: `48227607`
- Schema migration: `sql/migrations/V079__*.sql`
- Predecessor amendment: `docs/governance_dev/amendments/2026-05-09--operator_decision_audit_closure.md` (AMD-2026-05-09-02)
- Sibling amendment: `docs/governance_dev/amendments/2026-05-09--strategist_wide_adjustment_skill.md` (AMD-2026-05-09-03)
- Architecture amendment proposal: ADR-0021 (proposed) — Alpha Source Architecture Upgrade
- QC v3 push back: NEW-V3-2 — trial_sharpes 是 cross-section 不是 PBO
- TW v3 verification: `docs/CCAgentWorkSpace/TW/workspace/reports/2026-05-09--doc_verification_v3.md`
- R4 v3 verification: `docs/CCAgentWorkSpace/R4/workspace/reports/2026-05-09--index_verification_v3.md`

---

## 8. Non-Goals

This amendment does not:

- write or renew live authorization;
- flip any TOML `executor.shadow_mode` value;
- claim full PBO over strategy variants (cross-section only);
- delete code;
- rebuild, restart, or deploy;
- approve true live, MAG-083, or MAG-084;
- replace W-AUDIT-6c portfolio tail risk full IMPL;
- bypass Guardian veto over promotion candidates.

---

*OpenClaw / Arcane Equilibrium Governance Amendment - AMD-2026-05-09-04*
