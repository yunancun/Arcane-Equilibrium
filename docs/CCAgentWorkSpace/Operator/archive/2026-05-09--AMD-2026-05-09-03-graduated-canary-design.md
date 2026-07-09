# PA Design Report — AMD-2026-05-09-03 Graduated Canary Default

**日期**：2026-05-09
**Operator Decision**：Decision-1 採納 FA push back
**Amendment 主文**：`docs/governance_dev/amendments/2026-05-09--AMD-2026-05-09-03-graduated-canary-default.md`
**Commit**：`b1891023`

---

## 1. 任務脈絡

Operator 採納 4-agent (PA + FA + QC + MIT) 共識 + FA push back，把 AMD-2026-05-09-02 §2 Option A 的 binary `shadow_mode = fail-closed default` 升級為 5-stage graduated canary default。本報告紀錄 PA-side 設計取捨（amendment 主文未展開的部分）。

---

## 2. PA 為何接受 FA push back

### 2.1 「雞生蛋蛋生雞」死循環的數學形態

22 個 demo 環境 fail-closed default 累加：

| # | Default | 大致 P(pass) |
|---|---|---|
| 1 | cost_gate | 0.6-0.8 |
| 2 | Decision Lease shadow router | 1.0（W-C ON）|
| 3 | executor.shadow_mode true | 0.0（binary block）|
| 4 | Cognitive Modulator default conservative | 0.7 |
| 5 | SM-04 ladder ≥ L1 reduce frequency | 0.9 |
| 6 | Guardian veto | 0.8 |
| 7 | Layer2 manual-only | n/a（不在 hot path）|
| 8 | lambda:True 移除 / shadow_mode_provider missing → fail-closed | conditional on #3 |
| 9 | `_read_shadow_mode` exception fallback | conditional on #3 |
| 10 | OPENCLAW_LEASE_ROUTER 單向 | 1.0 |
| 11 | risk_envelope 默認收縮 | 0.8 |
| 12 | strategy active=false default for new | n/a（不在 active pool）|
| 13 | promotion gate min_observations=200 | 0（無 fill 即無 sample）|
| 14 | DSR/PBO 卡 None evidence | 0（無 sample）|
| 15 | Kelly tier hardcoded | 0.5（保守 tier）|
| 16 | `[40]` realized edge tolerance | 0（無 fill）|
| 17 | `[33]` maker fill-rate target | 0（無 fill）|
| 18 | `[55]` chain coverage | 1.0（W-C 已通）|
| 19 | `[42b]` LOW_SAMPLE | 0 |
| 20 | `[51]` opportunity_positive_n=0 | 0 |
| 21 | funding_arb ADR-0018 退役 | n/a |
| 22 | promotion 卡 P0-EDGE-1 | 0（無 edge 證據）|

關鍵在 #3 — 它是 binary block，使 #8/#9/#13/#14/#16/#17/#19/#20/#22 全鎖死。

P(進入下單路徑) = 0 → 0 fill → P0-EDGE-1 永遠 0 → #3 永遠 true → 死循環。

### 2.2 graduated canary 為何不違反 §二 原則 #6

**原則 #6**「失敗默認收縮」的精神是「不確定時保守」，不是「永不嘗試」。graduated canary 的 fail-closed 邊界從「binary 邊界」變為「stage 邊界 + 觀察期 SLA」：

- Stage transition 失敗 → auto-rollback 至 Stage 0（**stricter**，比當前 binary 更保守）
- Stage 內 SLA breach → 立即 rollback（**fail-fast**）
- Stage 升級需要證據（**evidence-based**，非樂觀 promote）

**對比**當前 binary：
- 失敗 → 保持 binary（無 fail-fast 機制）
- 成功 → 仍保持 binary（無 promote 機制）
- 永遠不會自動止血 / 自動收斂

graduated canary 反而**更嚴格地實踐**原則 #6，因為它有可量化的 rollback trigger，binary 沒有。

### 2.3 不放寬硬不變式 — amendment §3 明文列舉

PA 設計時刻意把「不適用範圍」明文列出，防止下游 IMPL 誤解：
- DOC-08 §12 9 條安全不變量
- SM-04 ladder
- Live boundary 5-gate
- §二 16 原則硬不變式

任何 IMPL 試圖在這些範圍動 fail-closed → E2 + E4 必拒。

---

## 3. 副作用識別清單

| 副作用 | 風險 | 緩解 |
|---|---|---|
| `RiskConfig.executor` schema 升級觸發 IPC schema break | 中 | Backward compat：legacy `shadow_mode` 字段保留，新增 `canary_stage` 為 SoT；E4 必跑 IPC schema regression |
| `shadow_mode_provider` 改為 stage-aware 後，5-Agent 鏈 / Promotion Pipeline / cost_edge_advisor / Cognitive Modulator 多處 caller 行為改變 | 中-高 | E2 必查 `grep shadow_mode_provider` 所有 caller；amendment §3.5 列明僅適用 alpha-bearing pathway，其他 caller 不受影響 |
| GUI Settings tab 顯示 cohort / stage / rollback metric live → 增加 IPC 流量 | 低 | poll interval 同 risk_config 既有 polling（10s）；不新增 hot path |
| `governance.canary_stage_log` append-only 表長期會大 | 低 | 設 7d / 30d retention（與其他 governance audit 表一致）；hourly aggregation view |
| Stage 1 paper cohort 若選的 strategy 是 ma_crossover 等 W-AUDIT-6 verdict REVISE 的策略 → 浪費 7d 觀察期 | 中 | Settings tab GUI 顯示策略 ranking；operator 拍板必看當前 W-AUDIT-6 verdict（PA + QC 預先 sign-off candidate list） |
| Stage 4 LIVE_PENDING 與 LG-X-04 supervised-live state machine 重疊 | 低 | amendment §2.2 明列 Stage 4 須滿足 LG-X-04 + 5-gate live boundary 全部 |
| Layer2 escalation proposal 階段 stage-aware（amendment §3.5）— 但 ADR-0020 仍 manual + supervisor only | 低 | amendment §6.4 明列 Layer2 不參與 stage transition automation |
| AMD-2026-05-09-01 SM-05 polling design 與本 amendment 互動 | 低 | AMD-2026-05-09-01 §3 invariants 完全保留；polling 行為不變 |

---

## 4. E1 派發設計（amendment §5.3 已詳）

7 個 sub-task，4-way parallel + 2 sequential：

```
T1 Rust schema      ─┐
T2 V### migration   ─┼─→ T3 shadow_mode_provider stage-aware ─┐
T6 Decision Lease   ─┘                                          │
                                                                ├─→ T7 E4 regression
T2 + T1 ─→ T4 healthcheck [58]                                 │
T1 + T2 ─→ T5 GUI surface ─────────────────────────────────────┘
```

PA 預估 sprint estimate：
- T1 (Rust schema) ≈ 0.6 task
- T2 (PG migration) ≈ 0.5 task（含 Linux dry-run）
- T3 (shadow_mode_provider stage-aware) ≈ 0.8 task
- T4 (healthcheck [58]) ≈ 0.4 task
- T5 (GUI surface) ≈ 1.0 task
- T6 (Decision Lease scope) ≈ 0.4 task
- T7 (E4 regression) ≈ 0.7 task

合計 ≈ 4.4 task ≈ 1.5-2 sprint（取決於 E1 並行度與 E5 優化深度）。

---

## 5. E2 重點審查 3 點（amendment §7 已詳）

1. `shadow_mode` legacy `false` 配 `canary_stage=0` 必 reject；`shadow_mode_provider` exception path 仍 fail-closed 至 Stage 0（不是 Stage 1）— break 即雞蛋死循環復活
2. `canary_stage_log.decision_lease_id` for `manual_promote` 必填 NOT NULL constraint 在 PG 層強制（不只 application 層）
3. healthcheck `[58]` 對 SM-04 ≥ L3 escalate 必 hard FAIL → 觸 stage = 0 rollback；不可降為 WARN

---

## 6. 與 R-1..R-5 architectural redesign 的關係

PA 2026-05-09 audit redesign report（`2026-05-09--full_loss_architectural_root_cause_redesign.md`）提出 R-1..R-5 5 個 architectural amendment proposal：
- R-1 Alpha Surface Foundation
- R-2 Strategist scope reframe
- R-3 Hypothesis Pipeline first-class
- R-4 Per-alpha-source Live Promotion Gate
- R-5 Spec-as-Code + Module Lifecycle

**AMD-2026-05-09-03 是 R-1 的 enabling foundation**：R-1 後新 alpha source 必走完整 5-stage canary，故 5-stage 機制必先 ready。本 amendment 不取代 R-1..R-5（R-1 仍是新 architectural amendment），但**必須先於 R-1 IMPL land**。

R-2/R-3 與 graduated canary 互動：
- R-3 Hypothesis Pipeline 升 EVIDENCE_GATE 時必 read 對應 cohort canary stage
- R-2 Strategist propose alpha source 時，proposal 必標明預期進入哪個 stage

R-4 Per-alpha-source Live Promotion Gate **是 graduated canary 的延伸**：把「整 system 5-stage」進一步細分為「per-alpha-source 5-stage」。本 amendment 是 baseline；R-4 是 generalize。

R-5 Spec-as-Code 與本 amendment 相容：healthcheck `[58]` + `canary_stage_metric_registry` 是 spec-as-code 的具體 instance（每 metric 必有 SQL + threshold + rationale）。

---

## 7. 完成

PA DESIGN DONE: report path: srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--AMD-2026-05-09-03-graduated-canary-design.md
