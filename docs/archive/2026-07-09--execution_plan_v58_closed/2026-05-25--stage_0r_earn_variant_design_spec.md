---
spec: Stage 0R Earn variant — Earn 操作 (Stake / Redeem) 進入真實 stake 前的 replay preflight 設計
date: 2026-05-25
author: PA agent (Sprint 1B Earn Wave C carry-over 仲裁)
phase: Sprint 1B late Pending 3.2 Earn Wave C — STAGE-0R-EARN-VARIANT-DESIGN-DRAFT
status: DRAFT-PA-DESIGN
parent specs:
  - srv/docs/governance_dev/amendments/2026-05-15--AMD-2026-05-15-01-canary-rebase-replay-preflight-demo-micro-canary.md (Stage 0R-4 source)
  - srv/docs/adr/0034-decision-lease-layered-approval-lal.md (LAL 0-4 + Stage 對齊矩陣)
  - srv/docs/governance_dev/amendments/2026-05-22--AMD-2026-05-21-01-autonomy-fully-with-failsafe.md (v2 Layered Autonomy + protected/opt-in)
  - srv/docs/execution_plan/2026-05-21--earn_governance_spec.md (5-gate / IntentProcessor / fail-closed)
  - srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint_1b_earn_first_stake_dispatch_packet.md (Wave A-E IMPL chain)
  - srv/helper_scripts/canary/replay_funding_harvest.py (C10 Stage 0R replay harness 範式參考)
related ADRs:
  - ADR-0031 Earn Macro Onchain framework
  - ADR-0032 Bybit Earn asset movement Guardian
  - ADR-0034 Decision Lease Layered Approval LAL
scope: design / spec / 不寫 code / 不執行 / 不改 schema 實檔
not in scope:
  - Earn replay harness IMPL Python (E1 Wave C 下一步;本 spec 定 spec 不寫 code)
  - operator first stake 執行 (Wave E operator;OP-1 key 重發後 unblock)
  - Bybit Earn first stake $100-200 拍板 (OP-2 已 closed)
  - Stage 1 Demo Earn micro-canary 啟動 (Stage 0R PASS + AC-1~5 全 PASS 後才可)
---
> ⚠️ 归档历史文档 — 非当前权威。active 状态见 repo 根 `TODO.md`；本文件仅供历史/审计参考。（2026-07-18 审计批量补入）


# Stage 0R Earn Variant Design Spec — Earn first stake 前的 Replay Preflight

## §1 Status + Date + Author + Related

| Element | Value |
|---|---|
| Status | DRAFT-PA-DESIGN (waiting QA + MIT + FA cross-ref + PM Phase 3e sign-off) |
| Date | 2026-05-25 |
| Author | PA agent (Sprint 1B Earn Wave C carry-over「Stage 0R Earn variant 仲裁」) |
| Trigger | per `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-24--sprint_1a_1b_completion_audit.md` line 20 / 90「Earn Wave C is still blocked by IntentProcessor Earn branch, OP-1 Bybit key refresh, **Stage 0R Earn variant**, rebuild/deploy, and operator first-stake execution」 |
| Supersedes | 無 (本 spec 為首次 Earn variant 設計;不取代既有 trading-strategy Stage 0R 範式) |
| Related governance | AMD-2026-05-15-01 (Stage 0R-4 source) + ADR-0034 LAL 0-4 + AMD-2026-05-21-01 v2 protected/opt-in scope |

### 1.1 為什麼需要 Earn variant 而非沿用 C10 Stage 0R 範式

| 維度 | C10 funding_harvest Stage 0R 範式 | Earn Stage 0R variant 必要差異 |
|---|---|---|
| 對象 | strategy (生 entry/exit signal 走 IntentProcessor TRADE_ENTRY/TRADE_EXIT) | Earn 操作 (生 stake/redeem 走 IntentProcessor EARN_STAKE/EARN_REDEEM) — IntentType / LeaseScope 完全不同 |
| 風險來源 | strategy alpha 估計失真 (look-ahead / selection bias / DSR / PSR / PBO) | Earn APY 變動風險 + liquidity risk + withdrawal gate + cross-product cannibalize (與 trading 共用 USDT 池) |
| Replay 模擬內容 | tick-by-tick on_tick simulation (Python mirror Rust strategy logic) | 7d cumulative Earn APY accrual + Daily reconciliation 機制驗證 + 不模擬 stake/redeem 動作本身 (動作受 OP-1+OP-2 拍板限定) |
| Stop loss 概念 | strategy 7d PnL bootstrap lower 5% > floor | Earn APY 是穩定 yield (~5-10% APR);無 PnL distribution;改驗 APY drift < 5% + cron 對賬無 mismatch |
| Stage 1 entry condition | strategy demo 7d cohort + 26 entry events + nonzero fills | Earn first stake 拍板 (OP-2 $100-200 flexible only) + 7d 觀察 APY accrual + Daily reconciliation 全綠 |

**核心立場**：Earn 不是 trading strategy;Earn 沒有「alpha edge」可以 replay 驗;Earn 的 Stage 0R 是「驗 governance 機制 + APY accrual 模擬 + 5-gate fail-closed reject path」而非「驗 strategy edge profitability」。

### 1.2 三層 governance 對齊

本 spec 同時對齊三條 governance baseline:

1. **AMD-2026-05-15-01 §3.3 Minimum Sanity Checks** — Earn variant 適用條目 = 「Runtime boundary」(replay 不替代 demo fill-lineage)、「Replay data tier」(historical APY snapshot 非 synthetic);**不適用** = 「Leak / lookahead」(Earn 無 strategy signal 概念)、「DSR / PSR」(Earn APY 是穩定 yield 非統計分佈)、「PBO / bootstrap」(同上)、「Bias / selection」(Earn first stake operator 拍板限定 = 100% bias by design)。
2. **ADR-0034 LAL ↔ Stage 對齊矩陣** — Earn first stake = LAL 0 per-fill (受既有 Guardian + 5-gate);LAL 1 intra-strategy reparam 不適用 (Earn 不是 strategy);LAL 3 new strategy promotion 不適用 (Earn 不是新策略 alpha 升 Stage 4)。Earn first stake 屬 Stage 0R → Stage 1 Demo micro-canary 路徑,但 promotion 對象是「Earn 路徑可用性」非「strategy alpha edge」。
3. **AMD-2026-05-21-01 v2** — Earn first stake 屬 **protected scope (a) Stage LAL 3-4 promotion** 邊界外 (Earn 不是 strategy promotion);但屬 **opt-in scope (g) LAL 1 intra-strategy reparam** 邊界外 (Earn 不是 reparam);屬 **新 sub-scope (o) Earn asset write** (本 spec 主張 = operator approve manual,Level 1+2 兩 level 均 manual,理由 = Earn 是 capital structure 子集,類似 LAL 4 capital structure change 紀律)。

---

## §2 Scope + 適用範圍

### 2.1 In Scope (適用 Stage 0R Earn variant)

| 場景 | Stage 0R Earn variant 必跑 |
|---|---|
| **first stake** (Sprint 1B Wave E OP-2 $100-200 Flexible only) | ✅ 必跑 — 首次 stake 走 production binary 前必 PASS preflight |
| **後續 stake** ($> $100 增量;Sprint 5+) | ✅ 必跑 — 每次新增 stake 前 7d replay APY accrual + Daily reconciliation 對賬 |
| **redeem** (任意金額;Sprint 5+) | ✅ 必跑 — 但 sanity check 子集 (略 APY accrual 部分,加 withdrawal gate latency 模擬) |
| **APY 重大變動觸發 reparam** (Sprint 5+) | ✅ 必跑 — 對齊 LAL 1 intra-strategy reparam pattern (Earn product 切換 / amount 重 sizing) |

### 2.2 Out of Scope (跳過條件 — skip preflight)

| 場景 | Skip preflight 理由 |
|---|---|
| **dust amount** (stake / redeem ≤ $10) | Bybit Earn minimum stake 通常 $10;dust amount 走 fail-closed reject 邏輯 (per earn_governance §2.4 Gate (d) 子檢查 4),不需 preflight |
| **stable APY 7d 內** (Δ APY < 0.5% 連續 7d) | APY 穩定且 cumulative accrual 已在既有 Daily reconciliation 對賬範圍;preflight 不增信號 |
| **emergency redeem** (margin headroom < 30% 觸發 auto-redeem) | 已有 earn_governance §2.4 子檢查 3 強制 redeem;preflight 反而延遲止血;Stage 0R fail-closed reject 不適用 emergency |
| **Daily reconciliation cron 自身** | cron 是 read-only audit;不寫 stake/redeem;不需 preflight |
| **read-only APR query** | Read-only 不觸 5-gate;不需 preflight |

### 2.3 Skip 條件決策樹

```
新 Earn 操作 (stake / redeem / reparam) 觸發
├─ amount ≤ $10 dust → SKIP (走 §2.4 子檢查 4 fail-closed)
├─ margin emergency redeem → SKIP (走 §2.4 子檢查 3 強制 redeem)
├─ stable APY 7d Δ < 0.5% → SKIP (Daily reconciliation 覆蓋)
├─ read-only query → SKIP (無 5-gate 邊界)
└─ 其他 (first stake / 增量 stake / redeem / reparam) → 走 Stage 0R Earn preflight
```

### 2.4 Sprint 1B Wave C 範圍鎖定

本 spec **首批 IMPL 範圍** 鎖定 first stake only:
- Wave C E1 IMPL `helper_scripts/canary/replay_earn_preflight.py` 只支援 first stake;
- 後續 stake / redeem / reparam variant **defer Sprint 5+** (per OP-3 flexible-only 拍板 + Sprint 1B 過短限定);
- Skip 條件邏輯也鎖 first stake (其他 variant 的 skip 邏輯 spec defer Sprint 5+ 對齊)。

---

## §3 Earn Replay Harness Design

### 3.1 核心設計 thesis

**Earn replay harness 不模擬 stake/redeem 動作本身**,而是模擬:
1. **APY accrual time series** — 用 Bybit 公開 `/v5/earn/apr-history` 7d historical APY + first stake amount → 計算 cumulative accrual USDT
2. **Daily reconciliation 機制 dry-run** — mock Bybit balance vs mock local V100 row → 觸發 3 階 cascade (Notice / Warn / Degraded) 各一次驗 routing
3. **5-gate fail-closed reject path 模擬** — 各 reject path (Gate a/b/c/d/e fail) 觸 1 次驗 IntentProcessor Earn branch 不誤放行
4. **不發 Bybit live 寫單** — 100% read-only + simulation;對齊 C10 範式 (replay_funding_harvest.py line 25-28 「不發 Bybit live 寫單」邊界)

### 3.2 對齊 C10 範式的關鍵差異 (mirror + diverge)

| 維度 | C10 範式 (replay_funding_harvest.py) | Earn variant |
|---|---|---|
| Public endpoint | `/v5/market/funding/history` + `/v5/market/kline` × 2 (perp + spot) | `/v5/earn/apr-history` × 1 (歷史 APY 採樣) + `/v5/earn/product` × 1 (產品列表 + 當前 APR) |
| Simulation core | tick-by-tick on_tick (1m bar × 43200 bar / 30d) | day-by-day cumulative accrual (1 row per day × 7d) |
| Sanity checks 數量 | 6 (leak / bias / DSR / PSR / PBO / runtime boundary) | **5** (drift / 5-gate reject path / cron dry-run / liquidity / runtime boundary) — 移除 leak/bias/DSR/PSR/PBO 4 條 (對 Earn 不適用),新增 4 條 Earn-specific |
| Verdict gate | `eligible_for_demo_canary = all 6 PASS` | `eligible_for_first_stake = all 5 PASS` (Earn 變體命名) |
| Output JSON path | `funding_harvest_stage0r_<date>.json` | `earn_first_stake_stage0r_<date>.json` |
| Output dir | `$OPENCLAW_DATA_DIR/canary/` | `$OPENCLAW_DATA_DIR/canary/` (共用 dir,檔名前綴 earn_) |
| Execution mode | `python helper_scripts/canary/replay_funding_harvest.py --symbol BTCUSDT --days 30` | `python helper_scripts/canary/replay_earn_preflight.py --coin USDT --amount-usd 100 --days 7` |

### 3.3 Replay harness 5 sanity check

#### Check 1: APY Accrual Drift

**目的**:replay 7d cumulative Earn APY accrual vs Bybit demo Earn record drift < 5%。

```
Input:
  - historical APY series (7d 採樣 from /v5/earn/apr-history) ⇒ daily APR list
  - first stake amount USDT (per OP-2 $100-200)
  - 7d 採樣窗口 boundary

Simulation:
  daily_accrual_usdt = stake_amount * (apr / 365.0)
  cumulative_7d_usdt = sum(daily_accrual_usdt for 7d)

Drift check:
  if has historical demo Earn record (V100 row):
    drift_pct = abs((cumulative_7d - demo_record) / cumulative_7d) * 100
    PASS if drift_pct < 5%
  else (first stake, 0 V100 row):
    vacuous PASS (對齊 C10 sanity_check_replay_data_tier vacuous PASS pattern)
```

**為什麼 5% 而非 1% (C10)**:Earn APY 是 Bybit 動態調整 (per BB-C3 caveat Bybit Dynamic Settlement Frequency System);5% 容許正常 APR 波動 (~10% APR 變 ±0.5%);1% 過嚴會 false reject。

#### Check 2: 5-Gate Reject Path Coverage

**目的**:逐 Gate (a/b/c/d/e) 模擬 1 次 fail 觸發 IntentProcessor Earn branch 走 fail-closed reject path,驗 governance 5-gate 機制完整。

```
For each gate in [a, b, c, d, e]:
  inject fail state (mock operator_role=None / authz_invalid / lease_unavailable /
                    risk_envelope_fail / DB INSERT fail)
  simulate submit_intent(intent_type='earn_stake', payload=mock_payload)
  assert verdict == 'rejected'
  assert audit_log event_type matches expected reject pattern
  log: gate=<a/b/c/d/e> reject_event=<expected_event_type> result=<PASS/FAIL>
```

PASS = 5 個 reject path 全 100% 觸發 + audit event 對齊 earn_governance §2.1-§2.5 預期值。

#### Check 3: Daily Reconciliation Cron Dry-Run

**目的**:模擬 3 階 cascade (Notice / Warn / Degraded) 各觸 1 次,驗 cron 路徑 routing 正確。

```
For each severity in [Notice, Warn, Degraded]:
  inject diff_usdt = severity-trigger value (0.005 / 0.5 / 5.0 cumulative 3d)
  call EarnReconciliationCron.run_once(mock_balance_source, mock_movement_reader)
  assert outcome.severity == expected_severity
  assert outcome.rows_updated >= 0
  log: severity=<Notice/Warn/Degraded> trigger_diff=<value> result=<PASS/FAIL>
```

PASS = 3 階各觸 1 次 + severity 對齊 + 連續 3d cumulative 觸 Degraded 升 alert path。

#### Check 4: Liquidity / Withdrawal Gate Latency

**目的**:Earn redeem 通常需 1-7d processing;模擬 redeem 假想時間延遲,驗 caller 不誤判 immediate availability。

```
Simulate:
  redeem_request_ts_ms = now
  expected_withdrawal_ts_ms = now + 1-7d (per Bybit FlexibleSaving liquidity tier)
  assert harness 不假設 redeem 動作後 balance 即時可用
  assert spec 文字明示 redeem latency (per Bybit doc)
```

**為什麼 LOW priority 但 mandatory**:Sprint 1B first stake 是 stake 不 redeem,但 spec 必明示 redeem path 後續加入時的 latency 假設;避免 Sprint 5+ 加入後 caller 預期 immediate redeem availability 走 race condition。

#### Check 5: Runtime Boundary

**目的**:replay 不 claim 替代 demo fill-lineage / Decision Lease / Guardian path;harness 純 simulation,不寫 V100 / 不發 Bybit Earn order。

```
RUNTIME_BOUNDARY_CHECK_PASS_BY_DESIGN = True
return "PASS", "earn replay harness 純 simulation;不寫 V100 / 不發 Bybit Earn order / 不 claim 替代 demo Earn fill-lineage"
```

對齊 C10 範式 `sanity_check_runtime_boundary` 設計 by design pass。

### 3.4 Historical APY 資料源 spec

| 來源 | 規格 |
|---|---|
| Endpoint | `/v5/earn/apr-history` (public GET;不需 secret slot) |
| 採樣窗口 | 7d (對齊 Stage 1 Demo micro-canary 7d 窗口) |
| 採樣頻率 | Bybit V5 預設 1 sample/h × 24 × 7 = 168 samples (足夠 daily aggregation) |
| Fallback | 若 endpoint return empty (Bybit Earn 產品下架 / 維護) → harness fail-closed return `eligible_for_first_stake=False` + reason `apr_history_empty` |
| Cache | harness 內 in-memory only;不持久化 PG (per §3.5 dry-run boundary) |
| Rate limit | Asset group 5 req/s (per BB §5.1 verify);harness 一次性 fetch 不持續 poll |

### 3.5 Dry-run mode 嚴格不變量

Earn replay harness 必滿足:
1. **不發 stake/redeem 寫單** — 0 hit `subscribe_flexible` / `redeem_flexible` /POST `/v5/earn/place-order`
2. **不寫 V100 `learning.earn_movement_log`** — 0 hit `EarnMovementWriter.insert_placeholder` / `update_outcome`
3. **不動 demo balance** — Bybit demo Earn balance 在 harness run 前後一致 (operator 可在 Bybit Web UI 自行驗)
4. **不繞 5-gate** — harness mock 5-gate fail path 但不繞過 IntentProcessor Earn branch real code path (mock 是 inject fail state,不是 short circuit)
5. **不污染 V100 schema** — 不建 shadow table / 不 ALTER schema;純 in-memory + JSON output

---

## §4 Acceptance Criteria

### 4.1 AC-1: APY Drift < 5%

| Element | Spec |
|---|---|
| Verify path | Harness output JSON `apy_drift_check == 'PASS'` + `drift_pct < 5.0` (or vacuous PASS for first stake 0 V100 row) |
| Verification owner | QA + MIT |
| Empirical evidence | `python helper_scripts/canary/replay_earn_preflight.py --coin USDT --amount-usd 100 --days 7` → JSON output `earn_first_stake_stage0r_<date>.json` |
| Failure path | `apy_drift_check == 'FAIL'` → harness exit code = 1 → operator 收 alert + 不 unblock Stage 1 Demo micro-canary |

### 4.2 AC-2: IntentProcessor Earn Branch 正確 Dispatch

| Element | Spec |
|---|---|
| Verify path | 5-gate reject path 5 個 fail injection 100% 觸 EARN_STAKE/EARN_REDEEM branch (走 bybit_earn_client 而非 trading bybit_rest_client) |
| Verification owner | E1 (B6 IntentProcessor Earn branch IMPL) + E2 (adversarial review) + QA (empirical 5 fail injection) |
| Empirical evidence | Harness output JSON `gate_reject_path_coverage == { 'gate_a': 'PASS', ..., 'gate_e': 'PASS' }` (5/5 all PASS) |
| Failure path | 任 1 gate fail injection 走 trading branch 而非 Earn branch → harness exit code = 1 → block IMPL closure |

### 4.3 AC-3: V100 `learning.earn_movement_log` 真實 Row 寫入

| Element | Spec |
|---|---|
| Verify path | **operator first stake 後** (非 harness;harness 不寫 V100),Linux PG empirical query `SELECT COUNT(*) FROM learning.earn_movement_log WHERE direction='stake' AND created_at > now() - INTERVAL '1 hour'` ≥ 1 |
| Verification owner | QA + Operator |
| Empirical evidence | Linux PG query output ≥ 1 row + row content check (engine_mode='live_demo' / amount_usdt=100~200 / governance_approval_id NOT NULL / bybit_response_payload not empty) |
| Failure path | 0 row → V100 writer code path 漏 dispatch → MUST fix before OP-2 first stake count as DONE |
| **重要**:harness 自身**不驗 AC-3** (per §3.5 dry-run 不寫 V100);AC-3 由 operator first stake 真實寫入後驗 |

### 4.4 AC-4: Stage 0R Fail → Fail-Closed Reject 不 Ascend Stage 1

| Element | Spec |
|---|---|
| Verify path | 注入任 1 sanity check FAIL (e.g. drift > 5%) → harness exit code = 1 → Stage 1 Demo micro-canary launcher (Wave E operator script) refuse to start |
| Verification owner | E1 (harness exit code + Stage 1 launcher gate) + QA (5 fail injection × 5 sanity check 25 case grid) |
| Empirical evidence | Harness exit code = 1 + 任 1 check status='FAIL' → 對應 launcher script grep harness output `eligible_for_first_stake` field; `False` ⇒ launcher abort + audit `event_type='stage_0r_earn_fail_closed_reject'` |
| Failure path | Harness exit 0 但 sanity check FAIL → bug → harness exit 邏輯漏條件 (E2 review 重點 #1) |

### 4.5 AC-5: ATR Cap / Drawdown Gate 對 Earn 適用否

| Element | Spec |
|---|---|
| 結論 | **不適用** ATR cap;**部分適用** drawdown gate |
| 理由 ATR cap | ATR (Average True Range) 是 trading strategy 用 volatility-based position sizing 工具;Earn 是 staking yield,amount 由 operator OP-2 拍板 fixed $100-200,不走 ATR-based sizing |
| 理由 drawdown gate 部分適用 | Earn 不會 negative PnL (staking yield ≥ 0);但 redeem latency × spot price drop 期間有 unrealized opportunity cost;Sprint 5+ 加 cross-product portfolio drawdown gate (Earn + trading 合計 drawdown) 觸發 emergency redeem |
| Verification owner | FA (cross-product risk review) + QC (Earn risk model) |
| Empirical evidence | Harness output JSON `atr_cap_applicable=false` + `drawdown_gate_applicable='partial_post_sprint5'` + spec §6.4 cross-ref |
| Failure path | 若 spec 漏明示 → reviewer 誤判 Earn 受 ATR 限制 → false reject 阻 first stake → block IMPL closure |

### 4.6 5 AC 全 PASS verdict gate

```
eligible_for_first_stake = (
  AC-1 == PASS
  AND AC-2 == PASS
  AND (AC-3 == 'deferred_to_operator_first_stake')  # harness 不驗,deferred
  AND AC-4 == PASS
  AND AC-5 == PASS (constant by design)
)
```

5/5 PASS → harness exit 0 + JSON `eligible_for_first_stake=True` → operator 收綠燈 + 走 Wave E first stake execution。

任 1 FAIL → harness exit 1 + JSON `eligible_for_first_stake=False` + `reasons` 列具體 FAIL → 不 unblock Wave E。

---

## §5 5-Gate Inheritance for Earn

### 5.1 Protected scope (a)-(f) 對 Earn 適用性

per AMD-2026-05-21-01 v2 protected scope 6 條:

| # | Protected item | Earn 適用 | 理由 |
|---|---|---|---|
| (a) Stage LAL 3-4 promotion | ⬛ **N/A** | Earn 不是 strategy promotion;Earn first stake 不對齊 LAL 3 new strategy promotion path |
| (b) 5-gate live boundary | ✅ **適用** | Earn 走 IntentProcessor → 5-gate (a)-(e) 完整 fail-closed;但 Earn 走 demo endpoint 時 mainnet env-var 不適用 (per earn_governance §4.2 條件 A) |
| (c) Copy Trading enable | ⬛ N/A | Earn 與 Copy Trading 無關 |
| (d) Auto-Allocator activation | ⬛ N/A | Earn 不走 Auto-Allocator (Sprint 1B 沒接;Sprint 5+ 才考慮 Earn-trading dual-objective allocator) |
| (e) Kill criteria | ✅ **適用** | Earn 連續 3 次失敗 / 連續 3d reconciliation mismatch → 自動 disable (per earn_governance §5.3 + §6.4) |
| (f) ADR-debt land | ⬛ N/A | Earn 不依賴 ADR-debt land path |

### 5.2 Opt-in scope (g)-(n) 對 Earn 適用性

| # | Opt-in item | Earn 適用 | 理由 |
|---|---|---|---|
| (g) LAL 1 intra-strategy reparam | ⬛ N/A | Earn 不是 strategy reparam |
| (h) LAL 2 cross-strategy reweight | ⬛ N/A | Earn 不走 cross-strategy reweight |
| (i) M2 always-on overlay | ⬛ N/A | Earn 不走 overlay |
| (j) M3 Tier 1+2 health degradation | ✅ **適用** | Earn 屬 health 監控對象 (per earn_governance §5.4 healthcheck `[earn-1]/[earn-2]/[earn-3]`);HEALTH_DEGRADED 時 Earn 自動 freeze |
| (k) M6 ≤30% reward weight adjustment | ⬛ N/A | Earn 不在 reward weight 範圍 |
| (l) M7 demote enforced 14d × 50% | ⬛ N/A | Earn 不是 strategy demote (Earn 沒 decay signal) |
| (m) M8 anomaly active trigger Y2 | ⚠️ **部分適用** | Earn 不直接觸 M8 anomaly;但 Earn cross-product 與 trading 共用 USDT 池,trading anomaly 可能誤觸 Earn risk;Sprint 5+ Earn-trading anomaly cross-trigger 需 spec |
| (n) M10 capital tier evaluation | ⚠️ **部分適用** | Earn 屬 capital structure 子集;capital tier evaluation 包括 Earn allocation ratio;Sprint 5+ M10 spec 需含 Earn tier |

### 5.3 新 sub-scope (o) Earn Asset Write 設計提議

per AMD-2026-05-21-01 v2 三維度並列 + §1.2 (3) thesis:

| Element | 設計 |
|---|---|
| Sub-scope 名稱 | **(o) Earn asset write** (stake / redeem 動 demo / live balance) |
| Level 1 (Conservative) 處置 | ✅ **operator approve manual** (預設 — 對齊 v1 protected scope 紀律) |
| Level 2 (Standard) 處置 | ✅ **operator approve manual** (例外保留 — 理由:Earn 是 capital structure 子集,類似 venue change `(b) PM Path B`,operator 一次性 stake/redeem click 不算 forgetfulness 痛點;Sprint 5+ 才評估 Earn auto with fail-safe path) |
| 對應 LAL | LAL 0 per-fill (每筆 stake/redeem 走 Guardian + 5-gate;不對齊 LAL 1 reparam / LAL 3 new strategy promotion) |
| 對應 Stage | Stage 0R Earn variant (本 spec) → Stage 1 Demo Earn micro-canary 7d (Wave E first stake) |
| 設計理由 | Earn 動 USDT 主帳本;失敗則 governance 完整性破損 (per earn_governance §2.5);保留 operator click 防止 LAL 1+2 evidence-gated auto path 誤動主帳本 |

**為什麼 Level 1+2 都 manual**:
- Earn 不是 strategy 沒 alpha edge 可累積 Wilson CI 證據觸發 auto-approve
- Earn first stake 階段 V100 行 0 條;沒有 30+ approval 證據累積基礎 (AMD-2026-05-21-01 §Decision 2.2 樣本 N ≥ 30 hard floor)
- Earn 動主帳本失敗 → undo 範圍小 (per ADR-0034 §Decision 5 fills 不可逆;Earn redeem 1-7d latency 內也不可逆)
- 保守設計對齊 operator 2026-05-22 Q1 「protected scope operator click 仍為 priority 5 sub-scope」立場

### 5.4 整體 gate 對應流程

```
Earn first stake intent
├─ [Gate a] Operator role auth ───────────────────────── FAIL → fail-closed reject
├─ [Gate b] Signed authorization.json (含 earn-write scope) FAIL → fail-closed + cancel_token shutdown
├─ [Gate c] Decision Lease acquired (LAL 0 per-fill) ─── FAIL → fail-closed reject
├─ [Gate d] Guardian Risk Envelope (5 sub-check) ─────── FAIL → fail-closed + lease release
├─ [Gate e] Audit log INSERT placeholder (V100 row) ──── FAIL → fail-closed + lease release + alert
├─ Bybit Earn API call (subscribe_flexible) ──────────── retCode != 0 → fail-closed + UPDATE outcome
└─ [Stage 0R Earn preflight] (本 spec)
   ├─ 5 sanity check 全 PASS → unlock Stage 1 Demo micro-canary 7d
   └─ 任 1 check FAIL → block Wave E + audit + alert
```

---

## §6 Earn-Specific Risk

### 6.1 APY 變動 Risk

| Element | Spec |
|---|---|
| Risk source | Bybit Earn rate adjustment (動態 APR;BB-C3 Dynamic Settlement Frequency System 2025-10-30) |
| Impact | replay APY 採樣窗口 7d 內 APR 變動 > 5% → Stage 0R AC-1 trigger FAIL |
| Mitigation | (a) Sanity check 1 drift threshold 5% 容許正常波動;(b) Daily reconciliation cron UTC 02:00 catch 真實 APR 對賬差異;(c) Sprint 5+ 加 APY tracker dashboard 監控動態變化 |
| Audit field | `expected_apr_bps` (per EarnIntentPayload) + `apr_at_time` (V100 row) + `apr_drift_pct` (harness output) |

### 6.2 Liquidity Risk

| Element | Spec |
|---|---|
| Risk source | Bybit FlexibleSaving 設計上 liquidity tier (small balance 即時 redeem;large balance 1-7d processing) |
| Impact | Sprint 1B first stake $100-200 在 small balance tier;immediate redeem 假設成立但需 operator awareness |
| Mitigation | (a) Sanity check 4 Liquidity / Withdrawal Gate Latency 明示 redeem 1-7d latency;(b) earn_governance §1.4 第 5 條「Earn 收益 < 5% / 年 ≪ trading margin 風險;不為了 APR 保留 stake」;(c) Sprint 5+ 加大額 stake 前必 spec liquidity tier 邊界 |
| Audit field | `liquidity_tier` (V100 row 新加 column;Sprint 5+) + `withdrawal_processing_days_estimated` (Daily reconciliation 計入) |

### 6.3 Withdrawal Gate Risk

| Element | Spec |
|---|---|
| Risk source | Bybit Earn redemption 通常 1-7d processing;期間 stake amount 不可動 (impacts margin headroom) |
| Impact | margin emergency 觸發 auto-redeem 仍需 1-7d 真實到帳;期間 trading margin 仍 < 30% headroom |
| Mitigation | (a) earn_governance §2.4 子檢查 3 margin headroom < 30% 拒 stake (預防);(b) Daily reconciliation 監控 pending redeem 計入 trading margin 估算 (Sprint 5+);(c) Stage 0R Sanity check 4 明示 redeem latency assumption |
| Audit field | `redeem_request_ts_ms` + `expected_completion_ts_ms` (V100 row;Sprint 5+ 新加) |

### 6.4 Cross-Product Cannibalize Risk (Earn ↔ Trading USDT 池共用)

| Element | Spec |
|---|---|
| Risk source | Earn stake = USDT 主帳本減少;Trading 開倉 margin 計算只看主帳本不看 Earn balance;若 Earn 過大可能 starve trading margin |
| Impact | 過度 Earn stake → trading 5 策略可用 margin 不足 → strategy 拒開倉 → 失 trading edge 機會 |
| Mitigation | (a) earn_governance §1.4 第 3 條「Earn 收益 < 5% / 年 ≪ trading margin 風險」哲學;(b) Sprint 5+ M10 capital tier evaluation 含 Earn allocation ratio (per §5.2 (n) opt-in 部分適用);(c) Daily Earn cap (per earn_governance §2.4 子檢查 1) 限 stake amount |
| Audit field | `trading_margin_headroom_at_stake_ts` (V100 row;Sprint 5+ 新加) + `earn_allocation_ratio` (Daily reconciliation cron output) |

### 6.5 Bybit Demo Endpoint 與 Live Endpoint 差異 Risk

| Element | Spec |
|---|---|
| Risk source | Bybit demo 雖支援 Earn API (per BB v57-C4 verdict (a)),但 demo Earn balance + APR 與 live 不完全一致;demo 可能用 mock APR |
| Impact | Demo Stage 1 micro-canary 7d 結果 ≠ live 7d 結果;Wave E operator first stake 走 live_demo 走 demo endpoint,actual live stake 仍需 LIVE_PENDING 五門 |
| Mitigation | (a) earn_governance §4.5 finalize 結果條件 A 採納;(b) Daily reconciliation cron 對賬源 = Bybit endpoint (demo 用 demo / live 用 live);(c) Stage 0R replay 用 live `/v5/earn/apr-history` 為 baseline (demo 不可靠) |
| Audit field | `bybit_env` ('demo' / 'live') + `endpoint_used` (V100 row) |

### 6.6 Earn-specific risk summary table

| # | Risk | Severity | Mitigation gate |
|---|---|---|---|
| 1 | APY 變動 | MEDIUM | Stage 0R Check 1 (drift 5%) + Daily reconciliation |
| 2 | Liquidity (small balance) | LOW | Sprint 5+ liquidity tier spec |
| 3 | Withdrawal gate (1-7d) | LOW | Stage 0R Check 4 + Sprint 5+ M10 |
| 4 | Cross-product cannibalize | MEDIUM | earn_governance §1.4 + Sprint 5+ M10 |
| 5 | Demo vs live endpoint drift | LOW | Stage 0R 用 live apr-history baseline + Daily reconciliation env-aware |

---

## §7 IMPL Roadmap

### 7.1 階段鏈

```
[PA] Stage 0R Earn variant design spec land (本 spec, ~6 hr) ← CURRENT
   ↓
[QA + MIT + FA] 三方 cross-ref review (parallel, ~3-5 hr 各)
   ↓
[E1] IMPL Wave C — helper_scripts/canary/replay_earn_preflight.py Python (~4-6 hr)
   ↓
[E2] Adversarial review (~2-3 hr)
   ↓
[E4] Regression (cargo test PASS + pytest integration test) (~1-2 hr)
   ↓
[QA] Stage 0R Earn variant acceptance (5 AC 逐條驗 empirical) (~2-3 hr)
   ↓
[PM] Phase 3e sign-off (Sprint 1B Earn Wave C closure) (~1 hr)
   ↓
[Operator] OP-1 Bybit Web UI key 重發 (≥ asset:earn scope, +30-60 min)
   ↓
[Operator] First stake execution $100-200 Flexible USDT 走 Wave E (~10-30 min)
   ↓
[Operator + QA] V100 earn_movement_log row 1 條驗 + 7d Stage 1 Demo micro-canary 啟動
```

### 7.2 PA 工作 (本 spec, ~6 hr)

- ✅ 本 spec land (`docs/execution_plan/2026-05-25--stage_0r_earn_variant_design_spec.md`)
- ⬜ PA verdict cross-ref (本 spec 自身);PA 視角 verdict 預計 = ✅ APPROVE (本 spec 起草階段已 cross-ref C10 範式 + earn_governance + AMD-2026-05-15-01 + ADR-0034 + AMD-2026-05-21-01 v2)

### 7.3 QA + MIT + FA cross-ref (parallel, ~3-5 hr 各)

| 角色 | 範圍 + 必驗點 | Report 路徑 |
|---|---|---|
| **QA** | AC-1~5 testability + harness exit code 邏輯 + 5 fail injection grid + dry-run boundary | `srv/docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-25--stage_0r_earn_variant_review.md` |
| **MIT** | §3 sanity check 設計 + APY accrual math + Daily reconciliation cron dry-run + V100 row schema 對齊 | `srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-25--stage_0r_earn_variant_review.md` |
| **FA** | §5 5-gate inheritance + §6 Earn-specific risk + AMD-2026-05-21-01 v2 protected/opt-in 對齊 + §5.3 新 sub-scope (o) governance 路徑 | `srv/docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-25--stage_0r_earn_variant_review.md` |

3/3 ✅ APPROVE → spec status DRAFT-PA-DESIGN → SPEC-FINAL → E1 IMPL Wave C dispatch ready。

### 7.4 E1 IMPL Wave C (~4-6 hr)

**檔案**:`/Users/ncyu/Projects/TradeBot/srv/helper_scripts/canary/replay_earn_preflight.py`

```python
"""
MODULE_NOTE
模塊用途:Stage 0R Earn variant preflight harness — first stake 前 5 sanity check
   per docs/execution_plan/2026-05-25--stage_0r_earn_variant_design_spec.md §3。

主要類/函數:
   - fetch_apr_history: Bybit V5 /v5/earn/apr-history (public GET)
   - simulate_apy_accrual: 7d cumulative accrual (day-by-day)
   - sanity_check_*: 5 條獨立檢查
   - mock_5_gate_reject_path: 5 fail injection coverage
   - mock_daily_reconciliation_cron: 3 階 cascade dry-run
   - output_preflight_verdict: 寫 earn_first_stake_stage0r_<date>.json

依賴:urllib (無第三方);可選 numpy (drift 計算 fallback)。

硬邊界:
   - 不發 Bybit live stake/redeem 寫單
   - 不寫 PG V100 / 不改既有 cron 邏輯 (pure read-only simulation)
   - 5 sanity check 全 PASS 才出 eligible_for_first_stake=true

per docs/execution_plan/2026-05-25--stage_0r_earn_variant_design_spec.md §3.4
"""
```

對齊 C10 範式 `replay_funding_harvest.py` 結構:
- `fetch_*` REST helper
- `_simulate_*` core math
- `sanity_check_*` 5 條獨立檢查
- `output_preflight_verdict` JSON output
- `run_stage0r_preflight` orchestrator
- CLI `main()` 接 `--coin USDT --amount-usd 100 --days 7`

### 7.5 E2 adversarial review (~2-3 hr)

| Review 重點 | 預期 finding |
|---|---|
| Exit code 邏輯 (AC-4) | harness 若任 1 sanity check FAIL 必 exit 1;不可 exit 0 |
| Mock 5-gate reject path 完整性 | 5 個 fail injection 各觸 1 次;不可 only mock 部分 |
| Dry-run 邊界 (§3.5 5 不變量) | grep 0 hit `subscribe_flexible` / `redeem_flexible` / `EarnMovementWriter.insert_placeholder` |
| Cron dry-run 不污染 production cron | mock cron 走獨立 in-memory state;不觸 production tokio scheduler |
| APY drift math | `daily_accrual = stake * (apr / 365.0)` 公式正確 |

### 7.6 E4 regression (~1-2 hr)

- cargo workspace 全 test PASS (Earn Wave B 既有 30+ test 不 regress)
- pytest integration test PASS (新 harness 5 sanity check unit test)
- harness CLI smoke `python helper_scripts/canary/replay_earn_preflight.py --coin USDT --amount-usd 100 --days 7` exit 0 (預期 first stake AC-1 vacuous PASS + 其他 4 PASS)

### 7.7 QA Stage 0R Earn variant acceptance (~2-3 hr)

5 AC 逐條驗:
- AC-1: harness CLI run 1 次取 JSON `apy_drift_check`
- AC-2: harness mock 5 fail injection grid 5 case 全 PASS (E2 review 完成後 E4 unit test 覆蓋)
- AC-3: deferred to Wave E operator first stake;harness 不驗
- AC-4: 5 fail injection × 5 sanity check 25 case grid 注 1 個 FAIL 驗 exit code = 1
- AC-5: harness JSON `atr_cap_applicable=false` + `drawdown_gate_applicable='partial_post_sprint5'`

### 7.8 PM Phase 3e sign-off (~1 hr)

- ✅ PA spec land + QA/MIT/FA 3/3 APPROVE
- ✅ E1 IMPL DONE + E2 APPROVE + E4 regression PASS
- ✅ QA 5 AC acceptance verdict
- → PM 仲裁 Sprint 1B Pending 3.2 Earn Wave C closure status
- → 同時 sign-off OP-1 Bybit key 重發為 operator action (PM 不能代執行)

### 7.9 Operator OP-1 Bybit key 重發 (~30-60 min)

(per TODO line 103 D+1 operator OP-1 拍板 2026-05-23)

```
Bybit Web → API management → 既有 key edit
查 "Last edited" 日期 < 2026-04-09 → 重發 key 加 asset:earn scope
3 端同步 (Linux secret slot / Mac dev / 生 paper test)
```

### 7.10 Operator first stake execution (~10-30 min)

(per OP-2 first stake $100-200 + OP-3 Flexible only)

```
GUI Earn governance tab → type-to-confirm $100-200 USDT FlexibleSaving
→ 5-gate 全 PASS → IntentProcessor EARN_STAKE branch → bybit_earn_client.subscribe_flexible
→ V100 earn_movement_log INSERT placeholder → Bybit API ack → UPDATE outcome
→ Linux PG empirical query SELECT * FROM learning.earn_movement_log ORDER BY created_at DESC LIMIT 1
→ AC-3 PASS
```

---

## §8 Open Questions (Operator 拍板項)

### 8.1 OQ-1: Stage 0R Earn variant 是否強制 first stake 前必跑?

**選項**:
- (a) **強制必跑** (建議) — 對齊 AMD-2026-05-15-01 §3 Stage 0R 是 preflight,first stake = Stage 1 Demo 啟動 = preflight 必先 PASS
- (b) opt-in only — operator 可繞 preflight 直接 first stake (但需 cancel cascade alert)

**PA 建議**:(a) 強制。理由 = Stage 0R 設計初衷 = fail-closed preflight,opt-in 弱化機制價值;且 first stake 是首次驗 IntentProcessor Earn branch + V100 writer + 5-gate,真實 stake 前必 preflight。

### 8.2 OQ-2: Sprint 5+ stake / redeem / reparam variant 何時 IMPL?

**選項**:
- (a) Sprint 1B Wave C 同 first stake variant 一起 IMPL (~ +6-10 hr)
- (b) **defer Sprint 5+** (建議) — Sprint 1B 鎖定 first stake;Sprint 5+ 加 stake / redeem / reparam variant

**PA 建議**:(b) defer。理由 = Sprint 1B 過短;先 first stake 真實寫入 V100 後再評估 stake / redeem / reparam variant 必要性;避免 over-engineering。

### 8.3 OQ-3: AC-3 是 harness 必驗還是 deferred 到 operator first stake?

**選項**:
- (a) deferred (本 spec 立場) — harness 不寫 V100 不能驗;operator first stake 後 PG query 驗
- (b) harness mock V100 writer 驗 INSERT path (但違 §3.5 §dry-run 邊界)

**PA 建議**:(a) deferred。理由 = harness dry-run 邊界硬約束 (per §3.5 第 2 條);違邊界會污染 V100;真實 first stake 後 PG query 才是 SSOT。

### 8.4 OQ-4: §5.3 新 sub-scope (o) Earn asset write 提案是否採納?

**選項**:
- (a) **採納** (建議) — 對齊 AMD-2026-05-21-01 v2 三維度並列 + Level 1+2 都 manual 紀律
- (b) 視為 protected scope (b) 5-gate live boundary 子集 (不新建 sub-scope)

**PA 建議**:(a) 採納。理由 = (b) 5-gate live boundary 是 trading-specific (live_reserved / mainnet env);Earn 是 asset write 不全等於 trading;明示 sub-scope (o) 對齊 governance trail。

### 8.5 OQ-5: §3.3 Check 1 drift threshold 5% 是否合理?

**選項**:
- (a) **5%** (本 spec 立場) — 容許 Bybit 動態 APR 波動;對應 BB-C3 Dynamic Settlement
- (b) 1% 嚴格 (對齊 C10 sanity_check_replay_data_tier 1%) — 但對 Earn 過嚴 false reject
- (c) 10% 寬鬆 — 但無 noise floor 信號弱

**PA 建議**:(a) 5%。理由 = Bybit Earn APR ~10% 動態 ± 0.5% 範圍;5% 容許正常波動且仍能 catch 結構性 drift。

### 8.6 OQ-6: Stage 0R Earn variant 走 demo endpoint 還是 live endpoint?

**選項**:
- (a) **live endpoint** (建議) — 用 live `/v5/earn/apr-history` 為 baseline;demo 可能用 mock APR 不可靠
- (b) demo endpoint — 對齊 demo Stage 1 Demo micro-canary 7d 窗口;但 demo APR 可能 mock 失真

**PA 建議**:(a) live。理由 = `/v5/earn/apr-history` 是 read-only public endpoint 不需 secret slot;走 live 取真實 APR baseline;Stage 0R replay vs Stage 1 demo 走不同 env 不影響 (replay 是 baseline simulation;demo 是 real fill-lineage)。

### 8.7 OQ-7: Stage 0R Earn variant fail 後 retry 政策?

**選項**:
- (a) **不自動 retry** (本 spec 立場) — 對齊 C10 範式 + AMD-2026-05-22 §Decision 2.3 fail-safe FAIL 不自動 retry
- (b) 自動 retry 1 次 (避免 transient network error 阻 first stake)

**PA 建議**:(a) 不 retry。理由 = AMD-2026-05-22 §Decision 2.3 「(b) gate FAIL 後自動 retry (可能 amplify systemic risk)」明示為反模式;operator 手動 trigger re-evaluation 才是新一輪。

### 8.8 OQ-8: Stage 0R Earn variant 結果 JSON 是否需鏡像至 governance.audit_log?

**選項**:
- (a) **鏡像** (建議) — Stage 0R 是 governance preflight,結果應 audit trail;對齊 earn_governance §2.5 鏡像至 governance.audit_log 範式
- (b) 不鏡像 — Stage 0R 是 advisory not authority,純 JSON file 不 audit

**PA 建議**:(a) 鏡像。理由 = AMD-2026-05-15-01 §3.4 「PM 可問 replay 能否加速 preflight」preflight 結果是 governance artifact;但 audit_log 由 Wave E 操作員 first stake 時 attach,不由 harness 自動寫 (避違 §3.5 dry-run 邊界);harness 只生 JSON,操作員 first stake 走 GUI 提交時 GUI 後端 attach JSON ref 到 audit row。

---

## §9 Cross-References

- AMD-2026-05-15-01 (Stage 0R-4 baseline): `docs/governance_dev/amendments/2026-05-15--AMD-2026-05-15-01-canary-rebase-replay-preflight-demo-micro-canary.md`
- ADR-0034 LAL ↔ Stage 對齊矩陣: `docs/adr/0034-decision-lease-layered-approval-lal.md`
- AMD-2026-05-21-01 v2 Layered Autonomy: `docs/governance_dev/amendments/2026-05-22--AMD-2026-05-21-01-autonomy-fully-with-failsafe.md`
- earn_governance spec (5-gate + IntentProcessor): `docs/execution_plan/2026-05-21--earn_governance_spec.md`
- Earn first stake dispatch packet (Wave A-E IMPL chain): `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint_1b_earn_first_stake_dispatch_packet.md`
- C10 Stage 0R replay harness (範式): `helper_scripts/canary/replay_funding_harvest.py`
- C10 dispatch packet (Stage 0R 對齊): `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint_1b_c10_funding_harvest_stage1_demo_dispatch_packet.md`
- IntentProcessor Earn branch (已 IMPL Wave B): `rust/openclaw_engine/src/intent_processor/mod.rs:110/124/157/239-246`
- Bybit Earn client (已 IMPL Wave B): `rust/openclaw_engine/src/bybit_earn_client.rs` (601 LOC, 5 endpoint)
- EarnMovementWriter (已 IMPL Wave B): `rust/openclaw_engine/src/database/earn_movement_writer.rs` (679 LOC)
- EarnReconciliationCron (已 IMPL Wave B): `rust/openclaw_engine/src/cron/earn_reconciliation.rs` (742 LOC)
- V100 schema (earn_movement_log 10 column): `sql/migrations/V100__m4_hypothesis_base_table.sql`

---

## §10 Sign-off

| Role | Source | Date | Status |
|---|---|---|---|
| PA | 本 spec 起草 (Sprint 1B Earn Wave C carry-over Stage 0R Earn variant 仲裁) | 2026-05-25 | ✅ DRAFT-DESIGN-DONE |
| QA | testability + AC-1~5 + harness 5 fail injection grid review | TBD (Wave C) | 🟡 PENDING |
| MIT | §3 sanity check 設計 + APY accrual math + V100 row schema 對齊 | TBD (Wave C) | 🟡 PENDING |
| FA | §5 5-gate inheritance + §6 Earn-specific risk + §5.3 sub-scope (o) | TBD (Wave C) | 🟡 PENDING |
| E1 | Wave C IMPL replay_earn_preflight.py owner | TBD (Wave C) | 🟡 PENDING |
| E2 | Wave C adversarial review | TBD (Wave C) | 🟡 PENDING |
| E4 | Wave C regression | TBD (Wave C) | 🟡 PENDING |
| PM | Phase 3e Sprint 1B Earn Wave C closure sign-off | TBD (Wave C) | 🟡 PENDING |
| Operator | OP-1 Bybit key 重發 + Wave E first stake execution + AC-3 V100 row 1 條驗 | TBD (Wave E) | 🟡 PENDING |

---

*OpenClaw / Arcane Equilibrium Sprint 1B Earn Wave C Stage 0R Earn Variant Design Spec — 對齊 AMD-2026-05-15-01 Stage 0R + ADR-0034 LAL + AMD-2026-05-21-01 v2 protected/opt-in + earn_governance §1-§13 + C10 範式 (`helper_scripts/canary/replay_funding_harvest.py`)*
