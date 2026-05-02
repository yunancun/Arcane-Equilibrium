# RFC v2 — LG-5 Live Candidate Evaluation Contract (LIVE-CANDIDATE-EVAL-CONTRACT)

Date: 2026-05-02
Owner: PA
Status: Draft v2, awaiting PM + QC + MIT sign-off (no open question — all decisions made)
Supersedes: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-02--lg5_live_candidate_eval_contract_rfc.md` (v1, kept as history)
Scope: Unifies MIT-S2-2 (P2) + QC-S2-02 (P2) into a single design spec. Design only — no implementation, no Rust touch. SQL migration **V035** spec inline (E1 IMPL-V035 落檔依據)。

---

## §0. Changelog vs v1 (12 must-fix 吸收 + per-strategy + V035)

### QC must-fix (7 items)
| ID | v1 issue | v2 fix | 影響章節 |
|---|---|---|---|
| **MF-Q1** | R1 absolute floor 0.20 與 0.85 ratio 互相矛盾 | floor 改 **0.15** | §3 R1 |
| **MF-Q2** | R2 公式無 clamp, pass `>= 1.0bps` (1σ false positive 高) | 加 `cost_regime_ratio_clamped = clamp(ratio, 0.3, 1.0)`；pass `>= 1.5bps` (~1.5σ); 確認 multiplicative + slippage 相減 | §3 R2 |
| **MF-Q3** | R3 24h n=30 對 crypto fat-tail 不可靠 | window 改 **7d/14d**, n threshold **100**; 加 fat-tail caveat | §3 R3 |
| **MF-Q4** | R4 `1/sqrt(K)` 為占位符 | 採 **Bailey-López-de-Prado simplified SR_0** 公式; 觸發從 ≥3 升 **≥5**; 5↓ fallback `0.25 × demo` worst-case + skip flag | §3 R4 |
| **MF-Q5** | R5 公式 double-count cost (R2 已扣 cost 又加回) | 改用 **demo gross** baseline: `realized_gross_edge_bps_demo = expected_net_bps_demo + (demo_avg_fee_bps + demo_avg_slippage_bps)`，cost_edge_ratio 用此分母 | §3 R5 |
| **MF-Q6** | R6 「7 consecutive rolling days」歧義；R1/R6 floor 重疊 | 7d 解讀為「過去 7 個獨立 daily snapshot 中**每一個** avg_net<0」+ SQL pseudocode; **R1 floor 0.15 = promotion-acceptable; R6 floor 0.10 = catastrophic-broken**, 後者覆蓋前者 | §3 R6 |
| **MF-Q7** | Audit schema 未含 R2/R3/R4 raw input → IMPL-5 retro 不可校準 | §2.3 schema spec 必含 18 欄位 (decided_at_ts / verdict / rule_failures / R2-R4 raw inputs / lease info / payload JSONB) | §2.3 + §13 V035 |

### MIT must-fix (5 items + 1 BLOCKER)
| ID | v1 issue | v2 fix | 影響章節 |
|---|---|---|---|
| **MF-M1** | §11 Q5 文本基於「MIT-S2-1 未 ship、attribution 84.6% 破」前提；現實已 ship 且 24h ratio 55.07% / today 68.97% | §1 + §11 重述: production attribution 已過 R-meta 0.50 binary gate; 真正 block 是 R6 hard veto 對 live regime negative | §1 + §11 (Q5 拍板) |
| **MF-M2** | R-meta + payload 用全局單一 ratio | 改 **per-strategy dict**: `demo_attribution_chain_ratio_by_strategy: dict[str, float]`; R-meta gate per-strategy lookup; 未知 strategy → defer | §2.1 + §3 R-meta |
| **MF-M3** | §2.2 status filter `status='live_candidate'` 引用錯 | 改 `status='candidate' AND application_type='live_promotion_candidate'` | §2.2 |
| **MF-M4 (BLOCKER)** | `learning.governance_audit_log` table 不存在 → audit emission 無 sink | **§13 從零設計 V035 migration spec** (TimescaleDB hypertable + Guard A + 2× Guard C + bilingual comments) | 新 §13 |
| **MF-M5** | LG-5-IMPL-3 healthcheck `[42]` 只驗 audit row 存在, 未驗 attribution drift | 加 `[42b]` (or `[43]`) per-strategy 7d rolling attribution_chain_ratio drift; PASS/WARN/FAIL = 0.50/0.30/0.10; 任一 strategy <0.10 = pipeline-level alert | §6 + §3 R-meta cross-ref |

### Operator-acked structural changes
1. **Per-strategy R-meta**: payload schema + R-meta gate 改 per-strategy。Runtime 0 影響 (operator 系統壓力分析確認 — 5 策略 × 1 float = 80 bytes / candidate, 完全 negligible)。
2. **V035 由 PA 從零設計**: §13 提供完整 PostgreSQL spec; E1 IMPL-V035 直接落 `sql/migrations/V035__governance_audit_log.sql`。
3. **0 open question**: v1 §11 的 8 條 open Q 全部拍板 (見 §11)。

---

## §1. Problem statement (rewritten)

`mlde_demo_applier._insert_live_candidate` (mlde_demo_applier.py:587-622) constructs a live promotion candidate row by copying three fields verbatim from the source demo row:

```
expected_net_bps  <- source_row["expected_net_bps"]   # demo-derived
confidence        <- source_row["confidence"]
sample_count      <- source_row["sample_count"]
```

These three numbers are then visible to GovernanceHub / Operator review as the live promotion's expected economics. **They are not.** They are the *demo* expected economics measured in the demo cost regime, with no live-cost adjustment, no statistical deflation, and no current-regime sanity gate.

### Why demo expected_net_bps is structurally wrong for live (現況校準, 2026-05-02)

1. **Cost regime drift**: Step 2 cold audit healthcheck `[33]` shows demo 7d `maker_like = 27.2%` vs `live_demo` `fee_drop_only = 22.0%`. Live cost regime is materially worse than demo (slower fills, more taker conversion, different rebate tier).
2. **Realized live edge is negative**: `[40]` 24h `avg_net = -17.21bps` over 37 rows. Demo `expected_net_bps = +5–6bps` thresholded by `live_candidate_min_net_bps = 5.0` (mlde_demo_applier.py:49) is **incompatible** with current live realized distribution.
3. **Attribution chain repair shipped (MF-M1 校準)**: MIT-S2-1 attribution chain fix shipped 2026-04-29 (commits `ece31b6` + `45bbe4d` + `5895579`)。Production 實測: 7d 14.96% (含修復前歷史污染) / **24h 55.07% / today 68.97%**。已過 R-meta 0.50 binary gate, **不再** block all live promotions on attribution。真正 block 是 **R6 hard veto** on live regime negative。
4. **No deflation for multiple-testing**: Demo applier emits up to `max_recommendations = 16` candidates per cycle. Each independently evaluated。PSR / DSR not applied. False discovery rate uncontrolled.
5. **Lease has no live-cost re-validation gate**: `GovernanceHub.acquire_lease()` (governance_hub.py:693) only checks authorization-permits-scope. Does not re-evaluate candidate's expected economics against current live cost regime.

### Consequences if not fixed before true live

- Operator approves a candidate showing `+5 bps expected`, executes, realizes `-17 bps avg`. Economic loss attributable to PA letting demo numbers cross the live boundary unmodified.
- Root principle #3 (AI output ≠ command) is technically respected (Decision Lease exists) but the lease is *uninformed* — gate does not re-evaluate the underlying claim.
- Root principle #8 (explainability) is technically met (payload exists) but displayed `expected_net_bps` is misleading evidence.
- Root principle #13 (cost awareness, `cost_edge_ratio ≥ 0.8 → close`) cannot fire because gate uses demo cost ratio.

### Framing (post-MIT-S2-1 ship)

LG-5 RFC v2 is **the governance framework for the post-attribution-repair, live-regime-recovery window** — not a freeze on all promotions. As soon as live-wide regime is no longer R6-vetoed (e.g. `[40]` 7d daily-snapshot avg_net 全部翻正), this contract automatically lets quality candidates through with full re-evaluation.

### MIT + QC convergence

MIT-S2-2 (engineering lens): "fix the data passing" — add `payload.demo_cost_baseline` so live consumer can do its own adjustment.
QC-S2-02 (quant lens): "add a re-evaluation contract" — distribution-shift haircut + PSR/DSR + cost regime alignment.

This RFC unifies both: MIT supplies **necessary metadata** (added to payload), QC supplies **decision rule** (R1–R6 + R-meta below), GovernanceHub becomes **enforcement point**, V035 provides **audit sink**.

---

## §2. Contract interface

### 2.1 Producer side (mlde_demo_applier)

`_insert_live_candidate` MUST emit a payload that includes a new `demo_cost_baseline` sub-object plus existing fields. Source row remains the single source of *demo* truth.

**Required payload additions** (JSONB sub-keys, no SQL schema change to `mlde_param_applications`):

```json
{
  "policy": "live_governed_promotion_candidate",
  "schema_version": "live_candidate_eval_v1",
  "source_demo_recommendation_id": <int>,
  "source_demo_application_id": <int>,
  "application_type": "live_promotion_candidate",
  "patch": { ... },
  "requires": ["GovernanceHub", "DecisionLease", "live_gates"],

  "demo_cost_baseline": {
    "as_of_ts": "<ISO8601>",
    "engine_mode": "demo",
    "maker_fill_rate_7d": <float 0..1>,
    "fee_drop_only_7d": <float 0..1>,
    "avg_realized_net_bps_7d": <float>,
    "avg_realized_fee_bps_7d": <float>,
    "avg_realized_slippage_bps_7d": <float>,
    "sample_count": <int>,
    "source_healthchecks": ["[33]", "[40]"]
  },

  "demo_realized_window": {
    "start_ts": "<ISO8601>",
    "end_ts": "<ISO8601>",
    "n_fills": <int>,
    "n_strategy_fills": <int>,
    "window_days": 7
  },

  "demo_attribution_chain_ratio_by_strategy": {
    "grid_trading": <float 0..1>,
    "ma_crossover": <float 0..1>,
    "bb_breakout": <float 0..1>,
    "bb_reversion": <float 0..1>,
    "funding_arb": <float 0..1>
  },
  "demo_sample_count_strategy_cell": <int>
}
```

**MF-M2 改動**: `demo_attribution_chain_ratio` (single float in v1) → `demo_attribution_chain_ratio_by_strategy` (dict keyed by strategy name)。Producer MUST populate all 5 keys; missing key → strategy treated as 0.0 (defer)。

### 2.2 Consumer side (GovernanceHub)

New method (Python, sits next to `acquire_lease`):

```
GovernanceHub.review_live_candidate(candidate_id: int) -> ReviewVerdict
```

**Inputs (read from DB)**:
- candidate row from `learning.mlde_param_applications` where `engine_mode = 'live'` AND **`status = 'candidate'` AND `application_type = 'live_promotion_candidate'`** (MF-M3 校準)
- candidate row's `payload` JSONB (must satisfy schema_version `live_candidate_eval_v1`; unknown version → reject)
- current live cost regime from healthchecks `[33]` posterior + `[40]` 24h
- current GovernanceHub authorization state
- pending-candidate count for DSR/multiple-testing deflation

**Output**:

```python
@dataclass(frozen=True)
class ReviewVerdict:
    decision: Literal["approve", "reject", "defer"]
    reason: str  # enum below
    rule_failures: list[str]  # ["R1", "R3", ...] empty if approve
    expected_net_bps_demo: float          # echoed
    expected_net_bps_live_adjusted: float | None  # post R2 haircut, None if reject
    expected_net_bps_deflated: float | None       # post R4 SR_0 deflation, None if R4 skipped/inapplicable
    cost_regime_ratio: float | None       # raw, None if R1 fail
    cost_regime_ratio_clamped: float | None  # clamp(0.3, 1.0)
    psr_value: float | None               # None if R3 not computable
    psr_n_samples: int | None             # None if R3 not computable
    psr_skew: float | None
    psr_kurt: float | None
    sr_0_deflation: float | None          # Bailey-LdP simplified SR_0
    v_pending_net_bps: float | None       # variance across pending candidates
    lease_ttl_ms: int | None              # only set on approve
    lease_revoke_triggers: list[str]      # healthcheck ids that auto-revoke
    decided_at_ts: int                    # unix ms
    decided_by: str                       # "GovernanceHub.review_live_candidate.<source>"
    payload_snapshot: dict                # full payload echoed for audit replay
```

**Reason enum** (拍板, 12 條):
- `"approve_within_envelope"`
- `"reject_schema_unknown"`
- `"reject_cost_regime_drift"` (R1)
- `"reject_haircut_negative"` (R2)
- `"reject_psr_below_floor"` (R3)
- `"reject_dsr_deflated"` (R4)
- `"reject_cost_edge_ratio"` (R5)
- `"reject_hard_veto"` (R6)
- `"reject_attribution_chain_too_broken"` (R-meta, per-strategy)
- `"defer_data_insufficient"`
- `"defer_healthcheck_not_fresh"`
- `"defer_attribution_chain_strategy_unknown"` (R-meta fallback: candidate strategy not in dict)
- `"defer_audit_write_failed"`
- `"defer_lease_acquisition_failed"`
- `"defer_r4_skipped_insufficient_pool"` (R4: pending pool <5)

`defer` is distinct from `reject`: defer means "not enough evidence right now, retry later"; reject means "this candidate is structurally unfit, supersede with new candidate".

### 2.3 Audit emission (MF-Q7 校準 — full schema spec)

Every `review_live_candidate` invocation MUST write one row to **`learning.governance_audit_log`** (V035 - 見 §13)。

**Required columns** (詳 §13 V035 spec):
- `event_type` = `'review_live_candidate'`
- `candidate_id` = candidate row PK
- `decision_lease_id` (NULL if not approved)
- `verdict_decision` ∈ {approve, reject, defer}
- `verdict_reason` (reason enum)
- `rule_failures` TEXT[] (e.g. `{R2, R3}`)
- `expected_net_bps_demo` (raw demo value)
- `expected_net_bps_live_adjusted` (post R2)
- `expected_net_bps_deflated` (post R4 SR_0)
- `cost_regime_ratio` (raw R2 input)
- `cost_regime_ratio_clamped` (clamp(0.3, 1.0))
- `psr_value`, `psr_n_samples`, `psr_skew`, `psr_kurt` (R3 raw)
- `sr_0_deflation`, `v_pending_net_bps` (R4 raw)
- `lease_ttl_ms`, `lease_revoke_triggers` TEXT[]
- `decided_by` 含 trigger source: `'GovernanceHub.review_live_candidate.scheduler'` or `'.operator_manual:<actor_id>'` or `'.bulk_re_evaluation'`
- `payload` JSONB (full ReviewVerdict for forward-compat replay)

**這些欄位是 IMPL-5 7d retro 校準 R2/R3/R4 的必要 raw input** — 任一缺失 IMPL-5 即無法重算 haircut 預測 vs 實際偏差。

**Approve 時**: 同次 transaction 寫 `decision_lease_id` 回 candidate row。
**Reject 時**: 同次 transaction 寫 `applied = false`, `requires_governance = true`, `payload.review_verdict` mirror。

**Fail-closed**: if audit write fails → return `defer` with reason `defer_audit_write_failed`, do NOT issue lease. (Root principle #6 + #8.)

---

## §3. Re-evaluation rules (R1–R6 + R-meta) — 全部拍板

### R1 — Live cost regime check (MF-Q1 校準)

**Rule**:
```
current_live_maker_fill_rate >= candidate_demo_maker_fill_rate * 0.85
AND
current_live_maker_fill_rate >= 0.15  (absolute floor; was 0.20 in v1)
```

**Source**:
- `current_live_maker_fill_rate` = `[33]` posterior measurement on `live_demo` engine, last 24h
- `candidate_demo_maker_fill_rate` = `payload.demo_cost_baseline.maker_fill_rate_7d`

**Rationale**: 0.20 floor 與 0.85 ratio 互相矛盾 (e.g. demo 0.30 × 0.85 = 0.255, 但 floor 0.20 過更鬆); 改 0.15 = promotion-acceptable threshold, 與 R6 floor 0.10 區分 (見 R6)。

### R2 — Distribution-shift haircut (MF-Q2 校準)

**Rule**: Compute live-adjusted expected with clamp:
```
cost_regime_ratio = (live_maker_fill_rate × live_fee_tier_multiplier) /
                    (demo_maker_fill_rate × demo_fee_tier_multiplier)

cost_regime_ratio_clamped = clamp(cost_regime_ratio, 0.3, 1.0)

expected_net_bps_live_adjusted = expected_net_bps_demo × cost_regime_ratio_clamped
                                 - (live_avg_slippage_bps - demo_avg_slippage_bps)
```

**Pass condition**: `expected_net_bps_live_adjusted >= 1.5 bps` (~1.5σ, was `>= 1.0` ≈ 1σ in v1; 1σ false positive ~16%, 1.5σ 降至 ~7%)。

**Clamp 理由**:
- 下界 0.3: 避免 ratio 暴跌 (e.g. live maker 5% / demo maker 30%) 把 expected_net 直接打到 ~0bps 並讓 candidate 一律 reject — 給 candidate 機會通過 R5/R6 的下游 cost gate。
- 上界 1.0: 永不允許 live "比 demo 還好" 的反向放大 (cost regime 改善應由 fresh demo baseline 反映, 非靠 ratio inflate live expected)。

**Concept-level small-edge validation**: small-edge 域 (demo expected ≤ 5bps), multiplicative + slippage 相減 公式相對 Bayesian shrinkage 誤差 <2 bps (QC pre-RFC 概念驗證)。

### R3 — PSR (Probabilistic Sharpe Ratio) check (MF-Q3 校準)

**Rule**: `PSR(0) >= 0.95` for the demo strategy/cell underlying the candidate.

**Inputs** (window: **7d/14d, NOT 24h**):
- candidate's strategy/cell return distribution from `learning.decision_outcomes` over `payload.demo_realized_window` (window_days = 7, fall back to 14 if 7d sample insufficient)
- benchmark Sharpe = 0 (only require positive expected return)
- skew, kurt, n built into PSR formula (Bailey-López-de-Prado 2012)

**Skip condition**: `n_strategy_fills < 100` → `defer` with `defer_data_insufficient` (was n=30 in v1; crypto fat-tail makes n<100 results unreliable; PSR formula's skew/kurt correction needs adequate sample to estimate higher moments)。

**Fat-tail caveat (註解)**: PSR 內建 skew/kurt 修正, 但 crypto returns 常呈現 kurt > 10 (vs normal 3); n<100 時 kurt 估計極不穩, PSR 結果不可信 → 嚴格 defer。

### R4 — DSR / multiple-testing deflation (MF-Q4 校準)

**Trigger**: ≥**5** candidates simultaneously pending (was ≥3 in v1; <5 無法可靠估計 V_SR)。

**Rule**: Apply Bailey-López-de-Prado simplified SR_0 deflation:

```
K = number of pending candidates (capped at 16 per applier max)
V_pending_net_bps = variance of expected_net_bps_live_adjusted across pending candidates
γ = 0.5772  # Euler-Mascheroni constant
SR_0 = sqrt(V_pending_net_bps) × ((1 - γ) × Φ⁻¹(1 - 1/K) + γ × Φ⁻¹(1 - 1/(K·e)))
expected_net_bps_deflated = expected_net_bps_live_adjusted - SR_0
```

Where `Φ⁻¹` = inverse standard normal CDF; `e` = Euler's number; `V_pending_net_bps` is sample variance across the K pending candidates' R2-adjusted expectations.

**Pass condition** (combined with R2): `expected_net_bps_deflated >= 1.5 bps` (same threshold as R2 post-haircut)。

**Fallback (K < 5)**:
- Default behavior: skip R4, set `expected_net_bps_deflated = expected_net_bps_live_adjusted`, write `r4_skipped_insufficient_pool` to `rule_failures` (informational, not a fail), `decision` 取決於 R1/R2/R3/R5/R6/R-meta。
- Worst-case override (when K=1 and reviewer wants conservative posture): `expected_net_bps_deflated = 0.25 × expected_net_bps_demo` (assume demo is 4× over-stated)。本 RFC 預設**不**啟用 worst-case; 留作 IMPL-2 config flag。

### R5 — cost_edge_ratio gate (CLAUDE.md §二 #13) (MF-Q5 校準)

**Rule** (改用 demo gross 避 double-count):
```
realized_gross_edge_bps_demo = expected_net_bps_demo
                             + (demo_avg_fee_bps + demo_avg_slippage_bps)

realized_cost_bps_live = current_live_avg_fee_bps + current_live_avg_slippage_bps

cost_edge_ratio = realized_cost_bps_live / max(realized_gross_edge_bps_demo, 0.01)
```

**Gate** (band 維持):
- `cost_edge_ratio < 0.5` → pass (full lease TTL)
- `0.5 <= cost_edge_ratio < 0.8` → warn (approve but with shorter lease TTL — see §4)
- `cost_edge_ratio >= 0.8` → fail (`reject_cost_edge_ratio`)

**v1 bug 解釋**: v1 用 `realized_gross_edge_bps_live = expected_net_bps_live_adjusted + realized_cost_bps_live` — 但 `expected_net_bps_live_adjusted` (R2 output) 已經減過 cost (R2 公式內 `- (live_slippage - demo_slippage)`), 再加 `realized_cost_bps_live` 就把 cost double-count 進 gross。改用 demo expected + demo cost 還原 demo gross, 避開此 bug。

Tracks root principle #13 (`cost_edge_ratio >= 0.8 -> close`). Threshold 0.5 / 0.8 from CLAUDE.md §二 + DOC-01 §5.13.

### R6 — Hard veto (MF-Q6 校準)

**Trigger** (任一即 hard veto, 不可被個別 rule pass 覆蓋):
- R1 OR R2 OR R3 OR R4 OR R5 fail
- **`[40]` 7 consecutive daily snapshots `avg_net_bps_after_fee < 0`** (live-wide regime negative)
- **`[33]` 24h `maker_fill_rate < 0.10`** (live cost regime catastrophically broken — 與 R1 floor 0.15 區分: R1 0.15 = promotion-acceptable, R6 0.10 = system-health gate, 後者覆蓋前者)
- `[22]` (trading_pipeline_silent_gap) FAIL — pipeline 本身不健康
- Authorization not currently effective (`get_effective()` returns empty)

**「7 consecutive daily snapshots」解讀** (MF-Q6 校準):
過去 7 個獨立 daily aggregate snapshot 中 **每一個** `avg_net_bps_after_fee < 0`。**不是** 24h rolling 算 7 次 (rolling 包含重疊 sample 不獨立)。

**SQL pseudocode** (供 IMPL-2 落 Python):
```sql
WITH daily_snapshots AS (
  SELECT
    date_trunc('day', ts) AS day,
    AVG(net_bps_after_fee) AS daily_avg_net
  FROM trading.fills
  WHERE engine_mode IN ('live', 'live_demo')
    AND ts >= now() - INTERVAL '7 days'
    AND ts < date_trunc('day', now())  -- 排除今日 partial day
  GROUP BY date_trunc('day', ts)
  ORDER BY day DESC
  LIMIT 7
)
SELECT
  COUNT(*) AS n_snapshots,
  COUNT(*) FILTER (WHERE daily_avg_net < 0) AS n_negative
FROM daily_snapshots;
-- R6 hard veto fires when n_snapshots = 7 AND n_negative = 7
-- 若 n_snapshots < 7 (data gap) → defer with defer_data_insufficient
```

**R1 vs R6 floor 區分明文** (拍板):
- **R1 floor 0.15** = promotion-acceptable threshold (per-candidate gate; 個別 candidate 允許通過的最低 maker_fill 條件)
- **R6 floor 0.10** = catastrophic-broken / system-health gate (system-wide hard veto; 整個 live 環境差到無法承載任何 candidate)
- **覆蓋順序**: R6 先檢查; R6 fire → 全部 reject_hard_veto; R6 not fire → 個別 candidate 走 R1。

→ `decision = "reject"`, `reason = "reject_hard_veto"`. Cannot be overridden by individual rule passes.

### R-meta — Attribution chain quality (per-strategy, MF-M2 校準)

**Rule**:
```
strategy = candidate.strategy_name
attribution_dict = payload.demo_attribution_chain_ratio_by_strategy
if strategy not in attribution_dict:
    return defer(reason="defer_attribution_chain_strategy_unknown")
ratio_for_strategy = attribution_dict[strategy]
if ratio_for_strategy < 0.50:
    return defer(reason="reject_attribution_chain_too_broken", rule_failures=["R-meta"])
```

**Source**: MIT-S2-1 production attribution measurement, sliced per-strategy (5 keys).

**Behavior**:
- **MIT-S2-1 已 ship 2026-04-29** — 24h 全局 ratio 55.07%, today 68.97%。Per-strategy production 預期 ≥0.50 對大多數 strategy 已成立。
- `< 0.50` (per-strategy) → `defer` (use `defer` not `reject`: 非 candidate 的錯, 是該 strategy 的 upstream attribution data; 給時間恢復)。
- 候選的 strategy 不在 dict (新策略 / 未注入) → `defer` with `defer_attribution_chain_strategy_unknown` (producer side bug, 非 quant 問題)。

**Cross-ref to MF-M5**: healthcheck `[42b]`/`[43]` per-strategy 7d rolling drift 監控本欄位變動; 任一 strategy <0.10 = pipeline-level alert (見 §6 IMPL-3)。

---

## §4. Lease design (post-approve)

When `decision = "approve"`, GovernanceHub then calls `acquire_lease()` with:

```python
acquire_lease(
    intent_id = f"live_candidate_{candidate_id}",
    scope = f"LIVE_CANDIDATE_APPLY:{target_surface}:{target_name}",
    ttl_seconds = lease_ttl_ms / 1000,
)
```

**Lease TTL policy** (set by `review_live_candidate`):
- Default: `lease_ttl_ms = 6 * 3600 * 1000` (6h)
- If R5 returned `warn` (cost_edge_ratio in 0.5–0.8 band): `lease_ttl_ms = 1 * 3600 * 1000` (1h)
- If R3 PSR in [0.95, 0.97]: shorten to 2h
- Hard cap: `lease_ttl_ms <= 6 * 3600 * 1000`
- First 30 days post-deploy: 全局 cap to 2h (learning period; 拍板 — 見 §11 Q6)

**lease_revoke_triggers** (auto-revoke if any healthcheck flips FAIL during lease lifetime):
- `[22] trading_pipeline_silent_gap`
- `[33] maker_fill_rate` (ratio drop > 30% from candidate baseline)
- `[40] realized_edge_acceptance` (live regime turns negative)
- `[42] live_candidate_eval_contract` (new healthcheck — see §6 LG-5-IMPL-3)
- `[42b] / [43] attribution_chain_drift` (any strategy <0.10)

Revocation MUST emit `governance_audit_log` row with `event_type = 'lease_auto_revoke'` + the trigger healthcheck id.

**Persistence**: candidate row's `decision_lease_id` written immediately after `acquire_lease()` returns non-None. If `acquire_lease()` returns None (post-approve), revert verdict to `defer` with reason `defer_lease_acquisition_failed` and emit audit row.

---

## §5. Backward compat / migration path

### 5.1 SQL schema change

**One new migration**: V035 (governance_audit_log table, new) — 詳 §13。**`mlde_param_applications` 不變動** (所有 candidate-side 改動透過 JSONB `payload`)。

### 5.2 Pending candidate handling

Per Step 2 audit, ~24 pending live candidates already in `learning.mlde_param_applications`. After contract lands:

1. **Hold**: All existing candidates with `payload.schema_version != "live_candidate_eval_v1"` automatically `defer` (treated as "missing baseline").
2. **Bulk re-evaluate**: After LG-5-IMPL-1 + LG-5-IMPL-2 deploy, run `helper_scripts/learning/lg5_re_evaluate_pending.py` (LG-5-IMPL-2 deliverable):
   - For each pending candidate, look up demo source row (`source_demo_recommendation_id`)
   - Synthesize `demo_cost_baseline` retroactively from `[33]`/`[40]` history at candidate creation time
   - Synthesize `demo_attribution_chain_ratio_by_strategy` from MIT-S2-1 historical per-strategy snapshots
   - Call `review_live_candidate(candidate_id)` once with `decided_by = 'GovernanceHub.review_live_candidate.bulk_re_evaluation'`
   - Mark `defer`/`reject`/`approve` accordingly
3. **Don't auto-promote any**: Even synthesized-baseline `approve` verdicts must be re-confirmed by Operator before Decision Lease grants live execution (LG-5 RFC envelope still applies).

### 5.3 Compatibility with MLDE-6 RFC

MLDE-6 (2026-05-01 RFC) defines candidate **schema** (`mlde_live_promotion_v1`). This RFC's `live_candidate_eval_v1` payload extension is **superset-compatible** — same top-level keys (`patch`, `rollback_patch`, `evidence_window`, `counterfactual`) plus this RFC's `demo_cost_baseline` block + `demo_attribution_chain_ratio_by_strategy`。MLDE-6's `MLDE6-T1` validator must accept the additional sub-keys (deferred to MLDE6-T1 implementation; this RFC adds the additions to MLDE-6's required-fields list).

### 5.4 LG-5 RFC (constrained autonomous live) alignment

LG-5 RFC (2026-05-01) defines the post-approval autonomy envelope. This RFC's `review_live_candidate` is the **gatekeeper before** LG-5's `lease_limited_autonomous_session` state. LG-5's `escalation_triggers` list amended to include:
- `review_live_candidate verdict expired beyond candidate window`
- `[42b] attribution_chain_drift FAIL`

---

## §6. Implementation breakdown (sub-tasks for next wave)

| ID | Scope | Owner | Files | Parallel? |
|---|---|---|---|---|
| **LG-5-IMPL-V035** | New SQL migration: `learning.governance_audit_log` table per §13 spec (TimescaleDB hypertable + Guard A + 2× Guard C + bilingual COMMENTs); idempotent local `psql -f V035 ... × 2` 無 RAISE | E1 | `sql/migrations/V035__governance_audit_log.sql` (new) | yes (independent — no code dep) |
| **LG-5-IMPL-1** | Producer: `mlde_demo_applier._insert_live_candidate` adds `payload.demo_cost_baseline` + `demo_realized_window` + `demo_attribution_chain_ratio_by_strategy` (per-strategy dict, 5 keys); pulls source data from `[33]`/`[40]` healthcheck snapshot + `learning.decision_outcomes` aggregation (per-strategy slice) | E1 | `program_code/ml_training/mlde_demo_applier.py` | yes (independent) |
| **LG-5-IMPL-2** | Consumer: `GovernanceHub.review_live_candidate()` Python implementation per §3 全部 7 條規則 + ReviewVerdict full-schema audit emission per §2.3; `lg5_re_evaluate_pending.py` one-off backfill script | E1 | `governance_hub.py` (or sibling new file `governance_hub_live_candidate_review.py` if LOC budget tight); `helper_scripts/learning/lg5_re_evaluate_pending.py` (new) | **blocked on V035 + IMPL-1** |
| **LG-5-IMPL-3** | Healthcheck `[42] live_candidate_eval_contract` + `[42b]/[43] attribution_chain_drift`: `[42]` verifies `review_live_candidate` called on every new live candidate within 1h with audit row visible; `[42b]` per-strategy 7d rolling attribution_chain_ratio drift (PASS/WARN/FAIL = 0.50/0.30/0.10; any strategy <0.10 = pipeline-level alert) | E1 | `helper_scripts/db/passive_wait_healthcheck.py` (add `check_42_*()` + `check_42b_*()`); `docs/healthchecks/` (new doc) | **blocked on IMPL-2 audit emission** |
| **LG-5-IMPL-4** | Tests: unit (R1–R6 + R-meta + audit fail-closed + lease TTL band logic + V035 schema fixture) + integration (full path: demo applier → live candidate row → GovernanceHub.review → ReviewVerdict → V035 audit log) | E4 | `tests/learning/test_lg5_live_candidate_eval_contract.py` (new); existing MLDE6 test extension; `sql/migrations/tests/test_v035_guards.sql` (optional — V035 guard fixture, mirror V031/V032 style; **not blocking**) | **blocked on V035 + IMPL-1 + IMPL-2** |
| **LG-5-IMPL-5** | QC retro: 7d after deploy, query V035 raw inputs (cost_regime_ratio_clamped / psr_value / sr_0_deflation / v_pending_net_bps), compare R2 haircut prediction vs realized live `[40]` net_bps. Validate haircut formula. If systematic bias > 2bps, raise QC RFC to refine R2 | QC | analysis report only | **blocked on IMPL-1..4 + 7d wall clock** |

---

## §7. Acceptance gate

This RFC requires **PM + QC + MIT** sign-off before LG-5-IMPL-* dispatch:

- **PM**: confirms scope fits Wave priority, agrees with parallelization plan (V035 + IMPL-1 並行 wave 1 → IMPL-2/3 wave 2 等), accepts bulk re-evaluation of 24 pending candidates approach。
- **QC**: confirms R1 0.15 floor / R2 clamp + 1.5bps / R3 n=100 / R4 Bailey-LdP simplified SR_0 / R5 demo-gross 公式 / R6 daily snapshot 解讀 + SQL。
- **MIT**: confirms (1) MIT-S2-1 attribution shipped; (2) per-strategy ratio dict 可從 production attribution log 切片產出; (3) §13 V035 schema 與 MIT 規劃中的 governance_audit_log 一致 (若 MIT 已有 prior plan)。

**Sign-off output**: PM updates Linear issue (62-finding tracker) referencing this RFC v2 path + verdict.

---

## §8. Out of scope (explicit)

- **MLDE training pipeline redesign**: MIT-S2-1 attribution chain repair 已 ship。本 RFC 不再 block on it。
- **Healthcheck threshold redefinition**: `[33]`/`[38]`/`[40]` thresholds are QC-S2-09 RFC scope。本 RFC consumes their current outputs.
- **Rust `live_authorization.rs` schema v2 changes**: schema is stable. 本 RFC 在 Python GovernanceHub 層運作。
- **Live execution path** (`IntentProcessor`, `bybit_rest_client`): unchanged.
- **Operator approval UI**: MLDE-6 `MLDE6-T2` covers read/review API route. 本 RFC adds `ReviewVerdict` JSON to whatever surface that route exposes.
- **Strategy params TOML / risk_config TOML**: untouched.
- **`learning.mlde_param_applications` SQL schema**: untouched (all changes ride in `payload` JSONB)。

---

## §9. Side-effect analysis (PA E1 dispatch warning)

For E2 review when LG-5-IMPL-2 lands:

1. **GovernanceHub LOC budget** (governance_hub.py 已 large — verify pre-existing baseline before adding `review_live_candidate`). 預估 +400 LOC; if pushes past 1500 hard cap (CLAUDE.md §九, 2026-05-02 governance change 已升 1500), 拆 `governance_hub_live_candidate_review.py` sibling。E2 must check.
2. **Lock contention risk**: `acquire_lease` holds `self._lock` for full validate+create flow (governance_hub.py:712). `review_live_candidate` MUST NOT hold the lock during DB reads (R1–R6 require fetching healthcheck rows + pending-count queries). Pattern: read → compute verdict → only acquire lock for the final `acquire_lease()` call.
3. **Audit write failure mode**: per §2.3, if audit write fails, return `defer` not `approve`. E2 must confirm exception handling does not silently swallow audit failures (root principle #6 + #8).
4. **V035 hypertable chunk size**: 7 days chunk_time_interval (見 §13)。governance_audit_log 寫入頻率 ~低 (only on `review_live_candidate` invocations + lease auto-revoke + bulk re-eval); 7d chunk 應產生 ~10K row / chunk 量級, 完全 ok。E2 不需特別關注 chunk 大小 unless production rate 超預期。
5. **Per-strategy dict cache**: producer 每 cycle 拉 5 strategy 的 attribution ratio 加進 payload。MIT 端產生 attribution log 已 per-strategy slice; producer 直接 SQL aggregate, 0 額外 IPC。

---

## §10. Root-principle check (16 conditions, abridged)

| # | Principle | Verdict |
|---|---|---|
| 1 | Single write entry | Preserved — review_live_candidate does not write orders, only verdicts + audit |
| 2 | Read/write separation | Preserved — verdict computation reads only |
| 3 | AI output ≠ command | **Strengthened** — adds re-evaluation between AI proposal and Lease |
| 4 | Strategy cannot bypass risk | Preserved — R1–R6 are additive to existing Guardian path |
| 5 | Survival > profit | **Strengthened** — R6 hard veto blocks promotion when system regime is negative |
| 6 | Fail-closed | **Strengthened** — defer on any uncertainty (audit failure, missing schema, insufficient samples) |
| 7 | Learning ≠ rewriting Live | Preserved — applier still cannot self-promote; new gate adds quality filter |
| 8 | Explainability | **Strengthened** — ReviewVerdict + rule_failures + decided_at_ts + V035 audit row |
| 9 | Exchange disaster guard | Untouched |
| 10 | Cognitive honesty | **Strengthened** — explicitly distinguishes demo evidence from live expected |
| 11 | Agent autonomy within hard boundaries | Preserved — agents can still propose; gate is automated, not operator-only |
| 12 | Continuous evolution | Preserved — R5/R-meta auto-soften as regime improves / attribution recovers |
| 13 | Cost awareness | **Strengthened** — R5 explicitly enforces cost_edge_ratio at promotion gate |
| 14 | Zero external cost runnable | Untouched |
| 15 | Multi-agent collaboration | Preserved — verdict observable by all agents via DB |
| 16 | Portfolio risk awareness | Future extension — R4 multi-testing handles per-candidate but not portfolio correlation; flagged as backlog (LG-6 scope) |

**Hard boundary (CLAUDE.md §四)**: untouched. `live_execution_allowed` / `max_retries` / `OPENCLAW_ALLOW_MAINNET` / `live_reserved` / `authorization.json` not modified by this RFC.

---

## §11. Closed design questions (v1 §11 全部拍板, 0 open)

| v1 Q# | Question | v2 拍板 |
|---|---|---|
| Q1 | R1 thresholds (0.85 ratio + 0.20 floor) | **R1 ratio 0.85 維持; floor 改 0.15 (MF-Q1)。** Per-strategy 細化留 LG-6 scope。 |
| Q2 | R2 haircut formula | **Multiplicative + slippage 相減 + clamp(0.3, 1.0) (MF-Q2)。** Bayesian shrinkage 留 IMPL-5 retro 後 QC RFC。 |
| Q3 | R3 PSR(0) threshold = 0.95 | **0.95 維持; window 改 7d/14d; n threshold 100 (MF-Q3)。** |
| Q4 | R4 deflation factor | **採 Bailey-López-de-Prado simplified SR_0 (MF-Q4); trigger ≥5; <5 fallback skip (informational)。** |
| Q5 | R-meta threshold = 0.50 (MIT-S2-1 未 ship) | **MIT-S2-1 已 ship 2026-04-29; production 24h 55.07%/today 68.97% 已過 0.50。改 per-strategy dict (MF-M2)。R-meta 不再 effectively block all promotions。** |
| Q6 | Lease TTL default = 6h | **Default 6h 維持; 但 first 30 days post-deploy 全局 cap 2h (learning period)。** |
| Q7 | Audit sink canonical name | **`learning.governance_audit_log` (V035 新建, MF-M4)。詳 §13。** |
| Q8 | Bulk re-evaluation 24 candidates 數據 gap | **接受 fail-closed: 數據不足即 defer; potentially-valid candidates 失於 data gap 是合理代價 (符合根原則 #6)。 PM 拍板 accept。** |

---

## §12. Cross-references

- MIT-S2-2 source finding: Step 2 cold audit (path TBD by MIT)
- QC-S2-02 source finding: Step 2 cold audit (path TBD by QC)
- QC review of v1: (path supplied by PM in sign-off block)
- MIT review of v1: (path supplied by PM in sign-off block)
- MLDE-6 prior RFC: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-01--mlde6_live_promotion_contract_rfc.md`
- LG-5 prior RFC: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-01--lg5_constrained_autonomous_live_rfc.md`
- LG-5 v1 RFC (本 v2 supersedes): `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-02--lg5_live_candidate_eval_contract_rfc.md`
- Step 2 cold audit: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-02--step2_cold_audit_4day_window.md`
- Producer code: `srv/program_code/ml_training/mlde_demo_applier.py:587-622`
- Consumer code: `srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/governance_hub.py:693-750`
- Existing migrations as reference: `srv/sql/migrations/V031__*.sql`, `srv/sql/migrations/V032__*.sql`, `srv/sql/migrations/V033__*.sql`, `srv/sql/migrations/V034__*.sql`
- CLAUDE.md hard boundary: `srv/CLAUDE.md` §四
- CLAUDE.md root principles: `srv/CLAUDE.md` §二 (true SoT: `srv/docs/decisions/DOC-01_..._V2.md`)
- CLAUDE.md SQL migration 規範 (Guard A/B/C): `srv/CLAUDE.md` §七

---

## §13. V035 governance_audit_log migration spec (PA 從零設計)

**Purpose**: 供 LG-5-IMPL-V035 直接落 `srv/sql/migrations/V035__governance_audit_log.sql`。本節是 spec, **非實作** — E1 IMPL-V035 照寫即可, 無需設計餘地。

### 13.1 Design decisions

- **Table name**: `learning.governance_audit_log` (schema=learning per existing convention; mirror V031/V032/V033/V034)
- **Hypertable**: TimescaleDB `create_hypertable()` with `chunk_time_interval = INTERVAL '7 days'` (governance audit volume 低; 7d chunk 適合 retention + query 平衡)
- **PK strategy**: `BIGSERIAL` (audit row count 不會 hot enough to need UUID; serial 簡單可 grep)
- **Hot-path indexes**: 2 indexes (candidate_id+ts DESC + event_type+ts DESC) — 對應 §6 IMPL-3 healthcheck `[42]` 主查詢 (per-candidate latest verdict) 與 IMPL-5 retro (event_type aggregate)
- **Guard A**: 強制 (CREATE TABLE 前驗 schema 存在 + table 已存在時驗必要欄位完整)
- **Guard B**: 不需要 (本 migration 是 fresh CREATE, 無 ALTER COLUMN; 後續 retrofit 才加)
- **Guard C**: 強制 對 2 個 hot-path index 比對 `pg_get_indexdef()`
- **Bilingual comments**: 每欄 `COMMENT ON COLUMN` 中英對照 (CLAUDE.md §七)
- **Idempotency**: 本地 `psql -f V035 ... × 2` 第二次無 RAISE (Guard A no-op + IF NOT EXISTS table + IF NOT EXISTS hypertable)

### 13.2 Full SQL spec (E1 IMPL-V035 直接落檔)

```sql
-- V035__governance_audit_log.sql
-- Purpose / 目的:
--   Create learning.governance_audit_log to sink GovernanceHub.review_live_candidate
--   verdicts, lease grants, lease auto-revokes, bulk re-evaluation events, and audit
--   write failures. Required by LG-5 Live Candidate Evaluation Contract RFC v2 §2.3
--   for full-schema raw input emission (R2/R3/R4 IMPL-5 retro 校準依據).
--
-- 建立 learning.governance_audit_log 作為 GovernanceHub.review_live_candidate 評估
-- 結果, lease 授予/自動撤銷, 批量重評, audit 寫入失敗事件的彙總表。LG-5 Live Candidate
-- Evaluation Contract RFC v2 §2.3 規定 — 必含 R2/R3/R4 raw input, 供 IMPL-5 7d retro 校準。
--
-- Migration order: V034 → V035 (no inter-migration dep beyond schema=learning existence).
-- Idempotency: local psql -f V035 ... × 2 → 第二次無 RAISE (Guard A no-op; CREATE IF NOT EXISTS).
-- Guard A: enforced (table existence + required columns validation).
-- Guard B: N/A (fresh CREATE, no ALTER COLUMN).
-- Guard C: enforced (2 hot-path indexes via pg_get_indexdef compare).

-- ─────────────────────────────────────────────────────────────────────────────
-- Guard A: validate schema=learning exists; if table already exists, validate
-- required columns present; missing column → RAISE EXCEPTION (mirror V031/V032
-- retrofit pattern per CLAUDE.md §七).
--
-- Guard A: 驗 schema=learning 存在; 若 table 已存在則驗必要欄位俱在; 缺即 RAISE。
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
    v_schema_exists BOOLEAN;
    v_table_exists BOOLEAN;
    v_missing_cols TEXT[] := ARRAY[]::TEXT[];
    v_required_cols TEXT[] := ARRAY[
        'id', 'ts', 'event_type', 'candidate_id', 'decision_lease_id',
        'verdict_decision', 'verdict_reason', 'rule_failures',
        'expected_net_bps_demo', 'expected_net_bps_live_adjusted', 'expected_net_bps_deflated',
        'cost_regime_ratio', 'cost_regime_ratio_clamped',
        'psr_value', 'psr_n_samples', 'psr_skew', 'psr_kurt',
        'sr_0_deflation', 'v_pending_net_bps',
        'lease_ttl_ms', 'lease_revoke_triggers',
        'decided_by', 'payload'
    ];
    v_col TEXT;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM information_schema.schemata WHERE schema_name = 'learning'
    ) INTO v_schema_exists;

    IF NOT v_schema_exists THEN
        RAISE EXCEPTION 'V035 Guard A: schema "learning" does not exist; run earlier migrations first';
    END IF;

    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'learning' AND table_name = 'governance_audit_log'
    ) INTO v_table_exists;

    IF v_table_exists THEN
        FOREACH v_col IN ARRAY v_required_cols LOOP
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'learning'
                  AND table_name = 'governance_audit_log'
                  AND column_name = v_col
            ) THEN
                v_missing_cols := array_append(v_missing_cols, v_col);
            END IF;
        END LOOP;

        IF array_length(v_missing_cols, 1) > 0 THEN
            RAISE EXCEPTION
                'V035 Guard A: learning.governance_audit_log exists but missing required columns: %',
                array_to_string(v_missing_cols, ', ');
        END IF;

        RAISE NOTICE 'V035 Guard A: learning.governance_audit_log already exists with all required columns; CREATE TABLE will no-op';
    END IF;
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- Main table / 主表
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS learning.governance_audit_log (
    id BIGSERIAL,
    ts TIMESTAMPTZ NOT NULL DEFAULT now(),
    event_type TEXT NOT NULL CHECK (event_type IN (
        'review_live_candidate',
        'lease_grant',
        'lease_auto_revoke',
        'bulk_re_evaluation',
        'audit_write_failed'
    )),
    candidate_id BIGINT NULL REFERENCES learning.mlde_param_applications(id),
    decision_lease_id TEXT NULL,
    verdict_decision TEXT NULL CHECK (
        verdict_decision IS NULL OR verdict_decision IN ('approve', 'reject', 'defer')
    ),
    verdict_reason TEXT NULL,
    rule_failures TEXT[] NOT NULL DEFAULT '{}',

    -- R2 raw inputs / R2 原始輸入
    expected_net_bps_demo DOUBLE PRECISION NULL,
    expected_net_bps_live_adjusted DOUBLE PRECISION NULL,
    expected_net_bps_deflated DOUBLE PRECISION NULL,
    cost_regime_ratio DOUBLE PRECISION NULL,
    cost_regime_ratio_clamped DOUBLE PRECISION NULL,

    -- R3 raw inputs / R3 原始輸入
    psr_value DOUBLE PRECISION NULL,
    psr_n_samples INT NULL,
    psr_skew DOUBLE PRECISION NULL,
    psr_kurt DOUBLE PRECISION NULL,

    -- R4 raw inputs / R4 原始輸入
    sr_0_deflation DOUBLE PRECISION NULL,
    v_pending_net_bps DOUBLE PRECISION NULL,

    -- Lease info / 租約資訊
    lease_ttl_ms INT NULL,
    lease_revoke_triggers TEXT[] NOT NULL DEFAULT '{}',

    -- Provenance / 來源
    decided_by TEXT NOT NULL,

    -- Forward-compat replay payload / 前向相容重放載荷
    payload JSONB NULL,

    PRIMARY KEY (id, ts)
);

-- ─────────────────────────────────────────────────────────────────────────────
-- TimescaleDB hypertable / TimescaleDB 超表
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
        PERFORM create_hypertable(
            'learning.governance_audit_log',
            'ts',
            chunk_time_interval => INTERVAL '7 days',
            if_not_exists => TRUE
        );
        RAISE NOTICE 'V035: learning.governance_audit_log converted to hypertable (7d chunks)';
    ELSE
        RAISE NOTICE 'V035: TimescaleDB extension not present; skipping hypertable conversion (table remains regular)';
    END IF;
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- Hot-path indexes / 熱路徑索引
-- ─────────────────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_gov_audit_candidate_ts
    ON learning.governance_audit_log (candidate_id, ts DESC)
    WHERE candidate_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_gov_audit_event_type_ts
    ON learning.governance_audit_log (event_type, ts DESC);

-- ─────────────────────────────────────────────────────────────────────────────
-- Guard C: validate hot-path index definitions match expected shape.
-- Guard C: 比對熱路徑索引定義是否符合預期; 任一 mismatch 即 RAISE。
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
    v_idx_def TEXT;
    v_expected_candidate_substring TEXT := 'CREATE INDEX idx_gov_audit_candidate_ts ON learning.governance_audit_log USING btree (candidate_id, ts DESC) WHERE (candidate_id IS NOT NULL)';
    v_expected_event_substring TEXT := 'CREATE INDEX idx_gov_audit_event_type_ts ON learning.governance_audit_log USING btree (event_type, ts DESC)';
BEGIN
    -- Check idx_gov_audit_candidate_ts
    SELECT pg_get_indexdef(c.oid)
    INTO v_idx_def
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'learning'
      AND c.relname = 'idx_gov_audit_candidate_ts';

    IF v_idx_def IS NULL THEN
        RAISE EXCEPTION 'V035 Guard C: idx_gov_audit_candidate_ts not found after CREATE INDEX';
    END IF;

    IF position(v_expected_candidate_substring IN v_idx_def) = 0 THEN
        RAISE EXCEPTION
            'V035 Guard C: idx_gov_audit_candidate_ts definition mismatch. Expected substring: %, actual: %',
            v_expected_candidate_substring, v_idx_def;
    END IF;

    -- Check idx_gov_audit_event_type_ts
    SELECT pg_get_indexdef(c.oid)
    INTO v_idx_def
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'learning'
      AND c.relname = 'idx_gov_audit_event_type_ts';

    IF v_idx_def IS NULL THEN
        RAISE EXCEPTION 'V035 Guard C: idx_gov_audit_event_type_ts not found after CREATE INDEX';
    END IF;

    IF position(v_expected_event_substring IN v_idx_def) = 0 THEN
        RAISE EXCEPTION
            'V035 Guard C: idx_gov_audit_event_type_ts definition mismatch. Expected substring: %, actual: %',
            v_expected_event_substring, v_idx_def;
    END IF;

    RAISE NOTICE 'V035 Guard C: both hot-path indexes validated';
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- Bilingual column comments / 中英欄位註解
-- ─────────────────────────────────────────────────────────────────────────────
COMMENT ON TABLE learning.governance_audit_log IS
'GovernanceHub audit log for live candidate review verdicts, lease grants/revokes, bulk re-evaluations, and audit failures. Full schema per LG-5 RFC v2 §2.3 + §13. / GovernanceHub 活動審計表 — live candidate 評估, lease 授予/撤銷, 批量重評, audit 失敗。';

COMMENT ON COLUMN learning.governance_audit_log.id IS
'Auto-incremented primary key. / 自增主鍵。';

COMMENT ON COLUMN learning.governance_audit_log.ts IS
'Event timestamp (UTC). Hypertable partition key (7d chunks). / 事件時間戳; hypertable 分區鍵 (7天 chunk)。';

COMMENT ON COLUMN learning.governance_audit_log.event_type IS
'Event category: review_live_candidate / lease_grant / lease_auto_revoke / bulk_re_evaluation / audit_write_failed. / 事件類別。';

COMMENT ON COLUMN learning.governance_audit_log.candidate_id IS
'FK to learning.mlde_param_applications.id. NULL allowed for events not tied to a single candidate (e.g. bulk re-eval batch aggregate, audit write failure with unknown candidate). / mlde_param_applications.id 外鍵; 批量事件 / audit 失敗時可為 NULL。';

COMMENT ON COLUMN learning.governance_audit_log.decision_lease_id IS
'GovernanceHub-issued lease ID if verdict=approve. NULL otherwise. / 若 approve, 為 GovernanceHub 簽發的 lease ID; 否則 NULL。';

COMMENT ON COLUMN learning.governance_audit_log.verdict_decision IS
'review_live_candidate verdict: approve / reject / defer. NULL for non-review events. / 評估結果。';

COMMENT ON COLUMN learning.governance_audit_log.verdict_reason IS
'Reason enum from ReviewVerdict (e.g. approve_within_envelope, reject_cost_regime_drift, defer_data_insufficient). See LG-5 RFC v2 §2.2. / 評估理由列舉值; 詳 LG-5 RFC v2 §2.2。';

COMMENT ON COLUMN learning.governance_audit_log.rule_failures IS
'Array of rule IDs that failed (e.g. {R2, R3}). Empty array on approve. / 失敗規則 ID 陣列; approve 時為空。';

COMMENT ON COLUMN learning.governance_audit_log.expected_net_bps_demo IS
'R2 input: demo expected_net_bps as copied from source demo row (no adjustment). / R2 輸入: 從 demo 來源逐字複製的 expected_net_bps (未調整)。';

COMMENT ON COLUMN learning.governance_audit_log.expected_net_bps_live_adjusted IS
'R2 output: post-haircut live-adjusted expected_net_bps = demo × cost_regime_ratio_clamped - slippage_diff. / R2 輸出: haircut 後的 live 調整 expected_net_bps。';

COMMENT ON COLUMN learning.governance_audit_log.expected_net_bps_deflated IS
'R4 output: post-Bailey-LdP-SR_0 deflated expected_net_bps. NULL if R4 skipped (K<5). / R4 輸出: Bailey-LdP SR_0 deflation 後; K<5 跳過時為 NULL。';

COMMENT ON COLUMN learning.governance_audit_log.cost_regime_ratio IS
'R2 raw: live_maker_fill × live_fee_mult / demo_maker_fill / demo_fee_mult (un-clamped). / R2 原始: live/demo 成本制度比 (未 clamp)。';

COMMENT ON COLUMN learning.governance_audit_log.cost_regime_ratio_clamped IS
'R2 raw: clamp(cost_regime_ratio, 0.3, 1.0). Used directly in haircut formula. / R2 原始: clamp(0.3, 1.0) 後值; 直接用於 haircut。';

COMMENT ON COLUMN learning.governance_audit_log.psr_value IS
'R3 output: Probabilistic Sharpe Ratio against benchmark SR=0. NULL if R3 skipped (n<100). / R3 輸出: PSR(0); n<100 跳過時 NULL。';

COMMENT ON COLUMN learning.governance_audit_log.psr_n_samples IS
'R3 input: n_strategy_fills used to compute PSR (from payload.demo_realized_window). / R3 輸入: PSR 計算使用的 n。';

COMMENT ON COLUMN learning.governance_audit_log.psr_skew IS
'R3 raw: sample skewness fed into PSR Bailey-LdP correction. / R3 原始: 樣本偏度。';

COMMENT ON COLUMN learning.governance_audit_log.psr_kurt IS
'R3 raw: sample kurtosis fed into PSR Bailey-LdP correction. / R3 原始: 樣本峰度。';

COMMENT ON COLUMN learning.governance_audit_log.sr_0_deflation IS
'R4 raw: Bailey-LdP simplified SR_0 deflation magnitude (in bps). / R4 原始: Bailey-LdP SR_0 deflation 量 (bps)。';

COMMENT ON COLUMN learning.governance_audit_log.v_pending_net_bps IS
'R4 raw: variance of expected_net_bps_live_adjusted across K pending candidates. / R4 原始: K 個 pending 候選 R2 輸出的方差。';

COMMENT ON COLUMN learning.governance_audit_log.lease_ttl_ms IS
'Issued lease TTL in milliseconds (only set on approve). / 授予的 lease TTL (毫秒); approve 時填寫。';

COMMENT ON COLUMN learning.governance_audit_log.lease_revoke_triggers IS
'Healthcheck IDs that auto-revoke this lease if they FAIL during lease lifetime. / 自動撤銷 lease 的 healthcheck ID 陣列。';

COMMENT ON COLUMN learning.governance_audit_log.decided_by IS
'Trigger source: GovernanceHub.review_live_candidate.scheduler / .operator_manual:<actor> / .bulk_re_evaluation. / 觸發來源。';

COMMENT ON COLUMN learning.governance_audit_log.payload IS
'Full ReviewVerdict JSON snapshot for forward-compat replay. May contain fields not yet promoted to columns. / 完整 ReviewVerdict JSON 快照; 為未來欄位演化保留。';
```

### 13.3 Optional fixture test

**Not blocking** RFC v2 ship — 可在 IMPL-V035 階段補。

If E1 chooses to add fixture test, place at `srv/sql/migrations/tests/test_v035_guards.sql` mirroring V031/V032 retrofit fixture style with 3 cases per guard (pass / fail / no-op):
- Guard A pass: schema exists, table absent → CREATE proceeds
- Guard A fail: schema absent → RAISE
- Guard A no-op: schema + table + all columns exist → NOTICE only
- Guard C pass: index def matches → NOTICE
- Guard C fail: pre-existing wrong-shape index → RAISE
- Guard C no-op: index already correct → NOTICE

---

## §14. Implementation order (PM 派發建議)

**Wave 1** (parallel, blocked by nothing — V035 + IMPL-1 並行 wave; 估 ~0.5 day):
- **LG-5-IMPL-V035** (E1, single E1, ~250 LOC SQL — 直接從 §13 落檔; 無設計餘地)
- **LG-5-IMPL-1** (E1, single E1, ~150 LOC Python — producer payload schema; 與 V035 完全 independent)

**Wave 2** (parallel, after Wave 1 lands; 估 ~1.5 day):
- **LG-5-IMPL-2** (E1, single E1, ~400 LOC across 2 files — `governance_hub.py` 或 sibling `governance_hub_live_candidate_review.py` + bulk re-eval script `lg5_re_evaluate_pending.py`)
- **LG-5-IMPL-4** (E4, single E4, can start fixture/unit shells using §13 V035 fixture + §3 R-rule fixtures from RFC pseudocode; 整合測試 wait IMPL-2)

**Wave 3** (parallel, after Wave 2 lands; 估 ~0.5 day):
- **LG-5-IMPL-3** (E1, single E1, ~80 LOC Python healthcheck — `[42]` audit-row-exists + `[42b]` per-strategy attribution drift)
- **LG-5-IMPL-4** finish (integration tests against real V035 + IMPL-2)

**Wave 4** (7d wall-clock gate after Wave 3 deploy):
- **LG-5-IMPL-5** (QC, analysis report only)

**Total wall clock estimate**: ~2.5 days IMPL-V035 → IMPL-4 land + 7d 等待 IMPL-5 retro。

**並行性 summary**:
- V035 + IMPL-1 fully parallel (different files, different domains: SQL vs Python producer)
- IMPL-3 + IMPL-4-finish 在 IMPL-2 之後 fully parallel
- 唯一序列瓶頸: V035/IMPL-1 → IMPL-2 (consumer 需 schema + producer 寫的真實 payload)

**Risk for E2 review** (3 重點, per profile.md output 標準):
1. **GovernanceHub LOC budget**: E2 必驗 IMPL-2 後 governance_hub.py 是否 ≤1500 LOC; 若超則拒, 要求 split 至 sibling file (governance_hub_live_candidate_review.py)。
2. **Lock contention**: E2 必驗 `review_live_candidate` 不在 `self._lock` 持鎖期間做 DB read; pattern 必須是 read → compute → 短暫 lock for `acquire_lease()` only。
3. **Audit fail-closed**: E2 必驗 audit write failure path 真的回 `defer` 而非 silently swallow; 對應 root principle #6 + #8。

---

## §15. References (cross-link with §12)

- **PM v1 review**: (path supplied in PM sign-off block)
- **QC v1 review**: (path supplied in QC sign-off block, 7 must-fix MF-Q1..Q7)
- **MIT v1 review**: (path supplied in MIT sign-off block, 5 must-fix MF-M1..M5 + V035 BLOCKER)
- **LG-5 RFC v1** (本 v2 supersedes): `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-02--lg5_live_candidate_eval_contract_rfc.md`
- **MLDE-6 prior RFC**: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-01--mlde6_live_promotion_contract_rfc.md`
- **LG-5 prior RFC** (constrained autonomous live): `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-01--lg5_constrained_autonomous_live_rfc.md`
- **Step 2 cold audit**: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-02--step2_cold_audit_4day_window.md`
- **CLAUDE.md hard boundary**: `srv/CLAUDE.md` §四
- **CLAUDE.md root principles**: `srv/CLAUDE.md` §二 (true SoT: `srv/docs/decisions/DOC-01_..._V2.md`)
- **CLAUDE.md SQL migration 規範**: `srv/CLAUDE.md` §七 (Guard A/B/C, idempotency)
- **MIT-S2-1 attribution chain repair commits** (referenced in MF-M1 校準): `ece31b6` + `45bbe4d` + `5895579` (2026-04-29 production deploy)

---

## Sign-off block (預留, 不主動填)

```
[ ] PM Sign-off
    Reviewer: <name>
    Date: <YYYY-MM-DD>
    Verdict: approve / conditional / reject
    Notes:
    Linear issue updated: <NCY-link>

[ ] QC Sign-off
    Reviewer: <name>
    Date: <YYYY-MM-DD>
    Verdict: approve / conditional / reject
    R1-R6 + R-meta 公式 ack: yes / no
    Notes:

[ ] MIT Sign-off
    Reviewer: <name>
    Date: <YYYY-MM-DD>
    Verdict: approve / conditional / reject
    V035 schema ack: yes / no
    Per-strategy dict 可從 attribution log 切片產出 ack: yes / no
    Notes:
```

---

End of RFC v2.
