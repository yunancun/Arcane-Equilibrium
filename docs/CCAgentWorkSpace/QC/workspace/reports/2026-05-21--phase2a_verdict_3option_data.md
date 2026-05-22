# Phase 2a 14d Verdict 三選一數據摘要

**Date**: 2026-05-21 (D+0) · **Owner**: QC · **Operator clock-trigger**: 2026-05-22~23 UTC
**Purpose**: operator D+1-D+2 拍板用 — 三選一決議（calibration r2 / accept 35% / Phase 2b LiveDemo）

**Sources verified**:
- QA D1 T+72h: `docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-21--lg1_lg2_7d_closure_phase2a_t72h_verify.md`
- PA D3 reverify: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--p1_data_lg5_edge_status_reverify.md`
- Phase 1b calibration spec: `docs/execution_plan/2026-05-18--phase_1b_calibration_sweep_spec.md`
- QC 2026-05-11 micro-profit analysis: `docs/CCAgentWorkSpace/QC/workspace/reports/2026-05-11--p1_micro_profit_amplification_math_analysis.md`

---

## 1. 當前 Phase 2a 數據快照（T+72h, per QA D1）

### 1.1 樣本健康度
- **n_samples**: **28 rows** since 2026-05-18 13:50 UTC clock reset (close_maker_attempt=TRUE)
- **velocity**: 0.39 rows/h（過去 72h）；後 24h 加速到 0.46 rows/h（v56 incident 後恢復）
- **14d projection**: ~140 rows total（若 engine 立即 restart，目前 09:58 UTC STOPPED）
- **n≥50 cell criteria**: PASS projection（floor 達標，但 upper-end 168/env/7d 目標 38% 達成）

### 1.2 AC FAIL deviation（含 Wilson CI）

| AC | Spec gate | Actual T+72h | Deviation | Projection |
|---|---|---|---|---|
| **AC-1** maker_fill ≥60% (WARN 65%) | 60% | **35.71%** (10/28 actual maker) | **-24.29 ppt absolute / -40% relative**；Wilson 95% lower ≈ 18-22% | **FAIL** strong |
| **AC-2** fallback (timeout_taker + postonly_reject) ≤30% | 30% | **64.29%** (18/28) | **+34.29 ppt 反向**（spec 上限的 2.14×）| **FAIL** strong |
| **AC-4** per-strategy 5 close exit_reason 各 ≥10 條 | 5 cells × 10 rows | **4 cells**: grid_close_short=18 / ma_reverse_cross=6 / grid_close_long=3 / phys_lock_gate4_giveback=1 | 缺第 5 cell + 3/4 cell 在 10 條 floor 下 | **FAIL** structural |
| AC-19 14d close_maker_fill ≥30% (secondary) | 30% | 35.71% | +5.71 ppt | PASS marginal |
| AC-20 14d UTC hour ≥18 buckets + per ≥3 rows | 18 buckets | 16 buckets / 11 under 3 | -2 buckets + 11 hour-deficient | WARN (secondary) |

### 1.3 calibration r2 actual

- **未獨立計算為 Phase 2a AC** — calibration sweep 81-cell × Wilson CI 是 Phase 1b spec §4.1 標準，AC-1/2/4 為 14d observation gate，r² 不在當前 verdict trigger 中
- **Phase 1b spec 的「calibration r2」referent**：PASS gate `maker_fill_rate ≥ 25% + fee_saving_wilson_ci_low ≥ 0` 是 sweep 簡化版（無傳統 r² metric）
- **若 operator 問的 r² 是 RealizedEdgeAcceptance 的 model fit**：runtime `[40]` healthcheck 顯示 24h MLDE rows=8460 / **avg_net=0.02 bps (target >5)** / win_rate=0.1% — r² 等價量 ≈ 0（near-zero predictive power）

### 1.4 5 textbook 策略 demo 表現

**RUNTIME-FETCH-NEEDED** — per-strategy fresh 7d avg_net snapshot 未在 docs 內現成。**間接證據（已驗）**：
- **整體 7d demo gross**: −26.44 USDT (PA 12-agent audit C-2, per QC 2026-05-11)
- **整體 7d demo avg_net**: **−17.82 bps**（PA 同源）
- **24h MLDE rows aggregate** `[40]`：8460 rows / avg_net=**0.02 bps** / win_rate 0.1% (per PA D3 2026-05-21 healthcheck dump)
- **per-strategy attribution chain (3d)**：ma_crossover 99.98% / grid 15.03% (4-leg lifecycle settled=29/193) / bb_reversion 100% n=3 / bb_breakout `[12]` post-deadlock FAIL 7d entries=0 / funding_arb 14d fills=0 dormant
- **Stage 0R W2 BTC-alt lead-lag**（2026-05-15 reference）：pooled avg_net **−3.56 bps**, t=−1.53, PSR(0)=0.054, DSR=0
- **AC-A 標準**（P0-EDGE-1）：≥3 個策略 demo 7d avg_net > 5 bps Wilson CI lower > 0 — **0/5 達標**（per QC 2026-05-11 verdict 持續）

> **若需 fresh per-strategy 7d，operator 跑**:
> ```bash
> ssh trade-core "psql -U trading_admin -d trading_ai -c \"SELECT strategy_name, COUNT(*) n, ROUND(AVG((realized_pnl/qty/price)*10000)::numeric,2) avg_net_bps FROM trading.fills WHERE engine_mode IN ('demo','live_demo') AND ts > NOW() - INTERVAL '7 days' AND exit_reason IS NOT NULL GROUP BY 1 ORDER BY 2 DESC;\""
> ```

---

## 2. 三選一評估

### (a) Calibration r2 重新校準

**機制**：重跑 Phase 1b calibration sweep（81-cell pruned matrix, axes A=offset_bps × B=buffer_ticks × C=timeout_ms × D=spread_guard_bps）找 ≥1 viable cell（maker_fill ≥25% + fee_saving_bps ≥0.5 + adverse_selection_proxy ≤ taker baseline）。

**支持數據**:
- Phase 1b calibration spec 已 ready；E1 IMPL ~750-1000 LOC harness 估 2 pd
- E2 RCA hypothesis: buffer_ticks=0 inside book + timeout 60-90s 預估 maker_fill 25-40%（spec §1.5 prior）
- PASS prior probability ~60-70%（per spec §1.5 + §7.5 PnL leverage analysis）

**Pros**:
- 真正修數據根因（不只貼標籤）；calibration sweep 不改架構，純 parameter tuning
- 即使部分 cell FAIL，sweep 自己會產 sample（不浪費觀察期）
- Adversarial selection proxy gate 嚴防把 fee saving 換到 fill price 損失上

**Cons**:
- 3-5 pd labor + 1d wall-clock pilot hold = 4-6 day timeline
- **不解 alpha deficit** — calibration 只能提升 maker_fill_rate 改善 fee drag（execution layer），與「AC-A: 3 策略 demo 7d avg_net > 5 bps」是 orthogonal cost vs alpha 兩軸（QC 2026-05-15 AMD review §3 明寫 maker fee saving ≠ alpha）
- v48 寬向 vs E2 內側向衝突方向都試 → result 可能 ambiguous（per PA push-back §10.1）
- **calibration cost saving ~$50-200/year × 65% prob ≈ $30-130 EV upside** — 對 demo edge 為 $-26.44/week baseline，比例 < 2-5%

**對 P0-EDGE-1**: **無實質影響**（cost layer 不救 alpha；P0-EDGE-1 closure 仍需 Sprint 2 Alpha Tournament + R-1/R-2/R-3 alpha path）

**對 Sprint 4**: 不解阻塞；calibration unlock 後 Phase 2a 仍需重跑 14d observation 確認 AC-1/2/4 達標

**對「5 策略 alpha-deficient」假設**: **零 implication** — calibration 不觸 alpha 假設；甚至若 maker fill 改善後 net 仍 0，反而 confirm alpha 是真根因（cost 不是）

**何時可重新評估**: Sprint 1A-δ 內（D+5~D+10）sweep PASS → 24h pilot → re-enter Phase 2a 14d 新時鐘 ≈ 2026-06-08

**風險**:
- **False positive 風險低-中**：PASS prior 60-70% 但 demo book 系統性 thinner than mainnet（§3.4 caveat）→ pilot 24h 仍可能 false positive
- **False negative 風險低**：sweep FAIL → architectural escalate（Option α ATR-aware offset / Option β demote to live-only）path 已 spec
- **Lock-in 風險低**：calibration 是 hot-reload override，cold-boot default 仍 baseline + use_maker_close=false fail-safe

---

### (b) Accept 35% 降低 threshold

**機制**：將 AC-1 maker_fill gate 從 60% (WARN 65%) 降到 35%，AC-2 fallback gate 從 30% 升到 65%；本質是「接受 demo 當前 regime 為 baseline，spec gate amend」。

**支持數據**:
- Phase 1b spec v1.3 footnote (per QA D1 §4.3) 承認 fee saving 0.5-2.0 bps range；60% maker fill = +1.5bps 與 §1.2 lower bound 自相矛盾
- 35.71% > 30% AC-19 secondary gate ✅
- Demo regime 與 mainnet 系統性差異（depth thinner per BB cross-check, calibration spec §3.4）；60% gate 可能本來就 demo 不可達

**Pros**:
- 即時可決議（無 IMPL labor）；解鎖 Phase 2a 14d normal 進度
- Spec gate 自洽（footnote 已 admit 60% 過嚴）
- 為 Phase 2b LiveDemo 留出時間配額（不被 calibration 沖掉）

**Cons**:
- **降 gate 不檢驗根因**：35% maker fill 意味 65% taker fallback；每筆 close 仍多吃 ~3.5 bps fee = baseline edge drag 不改
- **設置 precedent**：未來其他 AC FAIL 時 operator inbox 易選「降 gate」path；governance ratchet 朝寬鬆滑（per CLAUDE.md §二 #6「失敗默認收縮」原則衝突）
- **AC-4 cell coverage gap 仍未解**（4/5 cells、3/4 cell <10 條）— accept 35% 只改 maker_fill 不改 cell coverage
- **Adversarial review 標 RED**：QC skill `walk-forward-validation-protocol` 反模式條：「樣本不足但降閾值通過 = 偽陽性」— 即使非樣本不足，降 threshold to fit observation 屬同類偏差

**對 P0-EDGE-1**: **負面** — 此選項把 cost gate（AC-1/2）降寬給 alpha 缺失提供掩蓋空間；AC-A 仍需 3 策略 avg_net > 5 bps Wilson lower > 0，不變

**對 Sprint 4**: **加速 ~5 day**（無 IMPL）但 P0-EDGE-1 仍卡

**對「5 策略 alpha-deficient」假設**: **負面 implication** — 降 cost gate 等於減少 noise floor，alpha 信號更難從 cost noise 中分離（measurement bias 加大）

**何時可重新評估**: 14d Phase 2a 結束 ~2026-06-01；但 AC-1/2 寬化後重評難判斷是「真改善」還是「gate 寬鬆假象」

**風險**:
- **False positive 高**：AC-1/2 PASS 後系統認為「執行 OK」，但實際 65% taker fallback 持續吃 fee → P0-EDGE-1 measurement 被污染
- **False negative 低**：35% 是 observed baseline，降到此值 PASS prob ≈ 100%
- **Lock-in 風險高**：spec amend 後 governance ratchet 朝寬鬆方向；後續 calibration 改善有 fill rate 後反而無 gate 推力升回 60%；CLAUDE.md §二 #6 紅旗

---

### (c) Phase 2b LiveDemo 直接前進（跳過剩餘 Phase 2a）

**機制**：放棄 Phase 2a 剩 11d 觀察期 + AC-1/2/4 gate，直接進 Phase 2b LiveDemo Stage（7d livedemo counterfactual gate per spec §10）。

**支持數據**:
- Phase 1b 28 rows demo 已累積；LiveDemo 走 Live-grade control flow + Demo endpoint，可能呈現不同 maker_fill 行為（mainnet depth 假設驗證）
- Per AMD-2026-05-15-01 graduated canary：Stage 0R → Stage 1 demo → Stage 2 demo 14d → Stage 3 demo 21d → Stage 4 LIVE_PENDING；**Phase 2b LiveDemo 不在這條 ladder**（Phase 2 系列是 Phase 1b 的 post-deploy verification path，與 Stage 0R-4 是平行系列）

**Pros**:
- 進度跳躍（若 LiveDemo demo book 不同性質 → 提供 mainnet 環境 proxy 信息）
- 規避 Phase 2a 14d wait（節省 ~11d）

**Cons**:
- **違 spec §10 Phase 1b ladder**：Phase 2a 14d 是 Phase 2b LiveDemo 7d 的 prereq，spec 設計上 14d demo PASS → 才 promote to LiveDemo
- **違 CLAUDE.md 硬邊界**：「Paper is not an active promotion evidence lane unless a future explicit operator decision reopens it. **Stage 1 alpha-bearing promotion is Demo-only after a green Stage 0R replay preflight**」— Phase 2a Demo gate FAIL 跳級 = bypass governance ratchet
- **LiveDemo 不放鬆 authorization/TTL/risk/audit**（CLAUDE.md §四 hard boundary）— 但 Phase 2a FAIL 直接進 LiveDemo = 等於 LiveDemo 收 28 rows demo FAIL 樣本的繼承負擔
- **AC-4 cell coverage gap 仍未解** — LiveDemo 7d 樣本量同等級或更小（live-grade rate-limit），AC-4 在 LiveDemo 比 Demo 更不可能達標
- **EX-01 §6.2 + SM-04**：Phase 2a FAIL projection 是 negative signal；越級 promote 在 SM-04 state ladder 是「跨級恢復禁止」反模式（NORMAL/CAUTIOUS/REDUCED/DEFENSIVE/CIRCUIT_BREAKER 漸進）

**對 P0-EDGE-1**: **負面** — alpha 缺失不被測量改善 endpoint 解決；LiveDemo 改變 endpoint 不改變策略 EV<0

**對 Sprint 4**: **無實質加速** — P0-EDGE-1 + LG-3 + OPS-1..4 仍卡；LiveDemo PASS 後仍要解 4 條 P0

**對「5 策略 alpha-deficient」假設**: **負面 implication** — 在 alpha 已知 deficit 下推進 stage = governance 上對 alpha 缺失「視而不見」的決策 trail；未來 alpha 修補仍需 Sprint 2 Alpha Tournament 走 Stage 0/0R/1/2/3 重新累積

**何時可重新評估**: LiveDemo 7d 結束 ~2026-05-28；但回頭仍要面對 Phase 2a/AC-1/2/4 gate 邏輯（沒消失，只被推遲）

**風險**:
- **False positive 中**：LiveDemo endpoint 換到 mainnet-like depth → maker_fill 可能假性改善（depth ≠ alpha）
- **False negative 中**：LiveDemo 7d 又 FAIL → 整 Phase 2a/2b 流程信譽損失（governance ratchet 反向）
- **Lock-in 風險最高**：跳級設 precedent → 後續其他 stage gate FAIL 都可援例跳；CLAUDE.md §二 #6 + §五 hard boundary 直接違背

---

## 3. QC Verdict

**建議**: **(a) Calibration r2 重新校準**

**信心**: **中-高**（70%）

**核心理由**:
1. **唯一不違 governance 的選項**：(b) 降 gate 違 CLAUDE.md §二 #6「失敗默認收縮」；(c) 跳級違 spec §10 ladder + CLAUDE.md hard boundary + SM-04 跨級恢復禁止
2. **唯一檢驗根因的選項**：calibration sweep 提供 81-cell empirical evidence → 若 sweep FAIL → 知道根因不是 parameter tuning 而是架構 → escalate 路徑（Option α/β/γ）已 spec
3. **adverse selection proxy gate 強制條件**：calibration spec §4.1 PASS gate 含 `adverse_selection_proxy_bps ≤ pre-Phase-1b taker baseline` 防止 buffer=0 cell 帶來 informed taker hit
4. **EV 算數**：sweep cost 3-5 pd × ~65% PASS prob → +$30-130/year fee saving 直接 EV；不解 alpha 但消除執行成本 noise → P0-EDGE-1 alpha 估計更乾淨

**主要反方論點**:
1. **「calibration 不救 alpha，是 cost 改善 ≤ alpha deficit 的擠牙膏」** — 對。但 (b)/(c) 連 cost 都不救還新增 governance debt。在 alpha 修補真實 ETA 3-4 個月（per QC 2026-05-11 verdict）的窗口內，cost-saving incremental work 是「不傷大局的小進步」，比放棄 ratchet 強
2. **「Phase 2a 14d 給 alpha 信號 SNR 時間累積，calibration 中斷此累積」** — calibration sweep 純 replay harness 不需停 demo runtime；sweep 與 demo 累積可並行。Phase 2a 觀察期不被打斷
3. **「calibration sweep 80% 在 5 textbook 策略上做執行優化，但這 5 策略 already alpha-deficient，等於擦亮殭屍策略」** — 部分對。但 Sprint 2 Alpha Tournament 候選策略上線後同樣需 cost layer 健全；calibration evidence + harness 是 reusable infra。投資不浪費

**若 operator 選 (a)，下個 decision 點**: D+5~D+10 sweep 結果出 → PA 寫 cell selection report → 24h pilot → Phase 2a 重啟 clock ~2026-06-08 verdict
**若 operator 選 (b)**: 立即 spec amendment（QC RED 拒絕簽 — 違 governance 原則）；Phase 2a 14d 自然到 ~2026-06-01
**若 operator 選 (c)**: 立即進 Phase 2b LiveDemo（QC RED 拒絕簽 — 違 spec §10 + CLAUDE.md hard boundary）；7d 到 ~2026-05-28，回 P0-EDGE-1 仍卡
