# E2 RCA — Phase 1b 4/4 timeout_taker root cause

**Date**: 2026-05-18
**Agent**: E2 (Senior Code Reviewer + Adversarial Auditor)
**Trigger**: PM dispatch following QA 24h post-deploy verification — 4/4 `close_maker_attempt=TRUE` rows all fallback to `timeout_taker`，maker fill 0%
**Elapsed since restart**: T+10.6h post-restart UTC 2026-05-17 23:54:36
**Scope**: 對抗性 root cause analysis；找 fix scope；read-only RCA
**Mandate**: read-only RCA + reporting；不寫 fix code（per E2 role description「does NOT rewrite business logic, returns issues to E1」）

---

## §0 Verdict

**Root cause = STRUCTURAL DESIGN (NOT a bug) — small-n statistical noise at lower-bound of pre-predicted range.**

Confidence: **HIGH** that activator/state-machine/fallback path **all working as designed**. **MEDIUM-HIGH** that 0% fill is **expected behavior** given the strict-passive pricing strategy (`bid - 1 tick` for close-short / `ask + 1 tick` for close-long) on Bybit demo low-liquidity book. Sample n=4 too small for definitive verdict — **INSUFFICIENT_EVIDENCE** for fix-required conclusion.

**NO E1 RETURN. NO ESCALATION. Continue T+24h / T+48h / T+72h monitoring.**

---

## §1 4 fallback rows raw data + 觀察

```
ts                                  symbol     side  exit_reason                 qty      price    role  attempt  fallback_reason
2026-05-18 06:21:33.395+02  ARBUSDT  Buy   grid_close_short            548.6    0.1167   taker t        timeout_taker
2026-05-18 05:47:15.272+02  OPUSDT   Buy   grid_close_short            712.6    0.12868  taker t        timeout_taker
2026-05-18 05:45:35.578+02  ARBUSDT  Buy   grid_close_short            784.7    0.11666  taker t        timeout_taker
2026-05-18 05:09:50.343+02  XRPUSDT  Buy   phys_lock_gate4_giveback    65.2     1.3982   taker t        timeout_taker
```

**orders + state_changes timeline (key proof)**:

| Symbol | PostOnly Limit submitted | Self-cancel ack | Elapsed sec | Market fallback fill | Timeout spec | Filled within timeout? |
|---|---|---|---|---|---|---|
| ARBUSDT | 05:45:01.035 | 05:45:35.490 | **34.46s** | 05:45:35.578 (83ms after cancel) | 30s + 2s grace = 32s | No, ~2s over |
| ARBUSDT | 06:21:00.035 | 06:21:33.310 | **33.28s** | 06:21:33.395 | 32s | No, ~1s over |
| OPUSDT | 05:46:45.006 | 05:47:15.184 | **30.18s** | 05:47:15.272 | 32s | Right at timeout |
| XRPUSDT | 05:09:30.171 | 05:09:50.260 | **20.09s** | 05:09:50.343 | 15s + 2s = 17s (phys_lock_gate4) | No, ~3s over |

All 4 PostOnly limits: `Submitted → Working → Cancelled (reason=self_cancel)` with `filled_qty=NULL, avg_price=NULL`. State machine + cancel + fallback all firing cleanly within ~80-90ms of cancel ack. **0 PostOnly reject, 0 TooManyPending, 0 partial fill.**

Sample bias 觀察：3 of 4 在 UTC 05:00-06:30 asia-pre-open thin liquidity window。可能 sample 集中於 demo 環境最不利時段。

---

## §2 設計 vs actual flow gap

State machine **matches Phase 1b spec §5.2 Race B (maker timeout) exactly**:

1. PostOnly placed at `bid - 1 tick` (close BUY) at submit_ts
2. Bybit accepts → status `Submitted` → `Working` (order resting in book)
3. Sweep at `elapsed ≥ maker_timeout_ms` fires `MakerTimeoutCancel` (`pending_sweep.rs:75-77`)
4. `cancel_by_link_id_raw` sent → Bybit → state changes to `Cancelled (reason=self_cancel)`
5. Within 80-90ms of cancel ack, taker `Market` re-dispatch fills (`close_mf_fb` prefix order_id)
6. fills row written with `close_maker_attempt=TRUE, fallback_reason="timeout_taker"`

**No actual flow gap. Spec acceptance §11 AC-19 14d target is `fill_rate ≥ 30%` — current observation 0/4 is small-n at lower-bound of E3 predicted 15-25%.** Spec §1.2 line 44 explicitly wrote:

> 悲觀 (close-path conservative discount 25-40%): ~0.66 bps per close attempt (assumes close fill rate ≈ 20%, 15-25% range)

i.e. 80%+ timeout rate was a designed-for outcome at small samples.

---

## §3 5 條對抗性假設 verdict

| # | Hypothesis | Verdict | Evidence |
|---|---|---|---|
| **1** | cancel_grace_ms too short | **REFUTED** | `CLOSE_MAKER_CANCEL_ACK_GRACE_MS=2000` (`pending_sweep.rs:34`) — fires AFTER cancel request, not during maker wait. Maker wait window 自己是 `policy.timeout_ms` = 30s/15s (`maker_price.rs:92/97/102`). All 4 rows waited their full configured timeout (30.18-34.46s for 30s policy / 20.09s for 15s policy = 30s/15s + ~2-4s cancel ack RTT). Timeout config empirically aligned with entry-side baseline (45s entry, 30s close — both production-tested orderings). |
| **2** | PostOnly order never placed successfully | **REFUTED** | All 4 close orders have full state chain `Submitted → Working → Cancelled (reason=self_cancel)` in `trading.order_state_changes`. `Working` status = Bybit ack'd as PostOnly resting in book. `filled_qty=NULL` in Cancelled row = literally 0 fills before our cancel fired. Healthcheck [65] = 0 PostOnly_reject_samples + 0 max_pending_samples = NO reject path triggered. |
| **3** | State machine cancels before grace expires | **REFUTED** | `pending_sweep.rs:75-87` logic: `if elapsed_ms ≥ maker_timeout_ms → MakerTimeoutCancel` is the only path that fires cancel from timeout. The 2s `CLOSE_MAKER_CANCEL_ACK_GRACE_MS` (line 34) is the time we wait AFTER sending cancel before dropping the tracker — not a pre-cancel deadline. Cancel logic at 30s+ matches timestamps. `test_classify_close_postonly_uses_short_cancel_grace` (line 378) unit-locks the contract. |
| **4** | Bybit demo PostOnly silent degradation / low liquidity | **VERIFIED** as material contributor | (a) demo entry side baseline 24h: 156 PostOnly entries → **23 filled = 14.7% fill rate** + 133 timeout / abandon. Production-tested same endpoint, same instruments. (b) Pricing: `compute_close_limit_price` places strict-passive 1 tick OUTSIDE inside book (buy at `bid - 1 tick`, sell at `ask + 1 tick`). For fill, BBO must move 1+ tick adversely AND aggressor must hit it within 30s. (c) Spec §1.2 line 44 designed-for assumption: 「close fill rate ≈ 20%, 15-25% range conservative discount」. 0/4 over 24h is at lower edge of CI but consistent. Wilson 95% CI for 4 attempts 0 fills = [0%, 49%], includes 15-25% prediction. |
| **5** | Whitelist 4 rows are specific microstructure (ARBUSDT/OPUSDT/XRPUSDT) sample bias | **INSUFFICIENT_EVIDENCE** | 3 of 4 are grid_close_short on low-mid cap (ARBUSDT ×2, OPUSDT, XRPUSDT phys_lock). 這些是 spec §1.1 line 26 baseline (grid_close_short = 97/203 of 7d demo whitelist closes)。Cannot rule out — but cannot confirm. Need n≥30 across diversified exit_reason × symbol matrix per AC-A SQL. |

**Combined verdict**: **DESIGN IS WORKING. Sample too small to assert pathology. Predicted 15-25% fill rate with 0/4 observation is within statistical noise at small n.**

---

## §4 建議 fix scope — **NO CODE FIX RECOMMENDED AT THIS TIME**

Per E2 role mandate: 不寫業務代碼 + 若小樣本則 verdict 標 INSUFFICIENT_EVIDENCE + 建議 T+24h re-dispatch。**This is not an E1 RETURN scenario.**

### Recommendation order：

1. **NO fix to E1.** Path is functioning per spec §5.2 Race B + §5.5 mandatory fallback to taker (AC-18 = 4/4 = 100% fallback rate, **passing AC-18 threshold ≥ 95%**).
2. **Continue monitoring per QA T+24h / T+48h / T+72h re-dispatch schedule** (QA report §7.2).
3. **If T+72h n≥30 and `fill_rate < 15%` Wilson upper bound** → THEN consider follow-up parameter tuning (NOT code-level fix):

   | Option | 改動 | 預期影響 | Scope |
   |---|---|---|---|
   | **Tune-1** | `buffer_ticks: 1 → 0` in `close_maker_price_policy()` (`maker_price.rs:90, 95, 100`) — place AT inside book instead of 1 tick OUTSIDE | +5-15% fill rate uplift；風險 +PostOnly reject volume（Bybit may reject as PostOnlyCross when BBO moves mid-flight）| ~3 LOC config + ~30 LOC test for buffer=0 path |
   | **Tune-2** | extend `timeout_ms: 30_000 → 45_000` (match entry-side baseline) | 提升 maker fill 機率；風險 close exposure window 長 = §二 #5 生存 > 利潤 trade-off | ~1 LOC + ~10 LOC test |
   | **Tune-3** | tighter `tick spread guard` (currently 50 bps `CLOSE_MAKER_SPREAD_GUARD_BPS`, `maker_price.rs:55`) — skip maker on wide-spread books | reduce timeout_taker rate by avoiding hopeless attempts | ~1 LOC + ~5 LOC test |

4. **Either way it is a PA config-tuning ticket, not an E1 IMPL ticket** — spec §1.2 already predicted 15-25% fill rate; if production lands in that range, no code defect.

---

## §5 Re-verification SQL（T+72h or n≥30）

### Primary AC-A 7d demo close-maker fill rate at n≥30 + Wilson CI

```sql
WITH attempts AS (
  SELECT exit_reason, symbol,
         COUNT(*) FILTER (WHERE close_maker_attempt) AS n_attempts,
         COUNT(*) FILTER (WHERE close_maker_attempt AND liquidity_role='maker') AS n_fills,
         COUNT(*) FILTER (WHERE close_maker_attempt AND close_maker_fallback_reason='timeout_taker') AS n_timeout_taker,
         COUNT(*) FILTER (WHERE close_maker_attempt AND close_maker_fallback_reason='postonly_reject') AS n_postonly_reject
    FROM trading.fills
   WHERE engine_mode='demo' AND ts > NOW() - INTERVAL '7 days'
   GROUP BY exit_reason, symbol
)
SELECT exit_reason, COUNT(DISTINCT symbol) AS sym_count,
       SUM(n_attempts) AS attempts,
       SUM(n_fills) AS fills,
       ROUND(SUM(n_fills)::numeric / GREATEST(SUM(n_attempts),1) * 100, 1) AS fill_rate_pct,
       SUM(n_timeout_taker) AS to_taker,
       SUM(n_postonly_reject) AS po_reject
  FROM attempts GROUP BY exit_reason ORDER BY attempts DESC;
```

**Pass gate**: fill_rate_pct ≥ 15% per exit_reason at n≥30 (AC-19 conservative lower bound) → continue.
**Investigate gate**: fill_rate < 5% at n≥30 → tuning ticket per §4.

### PostOnly order placement audit（verify pricing is right vs BBO）

```sql
SELECT o.symbol, o.side, o.qty, o.price AS limit_px, o.ts AS submit_ts,
       osc.to_status, osc.reason, EXTRACT(EPOCH FROM (osc.ts - o.ts)) AS hold_sec
  FROM trading.orders o
  JOIN trading.order_state_changes osc
    ON o.order_id = osc.order_id AND osc.to_status = 'Cancelled'
 WHERE o.engine_mode = 'demo'
   AND o.time_in_force = 'PostOnly'
   AND o.strategy_name LIKE '%_close:%'
   AND o.ts > NOW() - INTERVAL '7 days'
 ORDER BY o.ts DESC LIMIT 30;
```

---

## §6 是否需要 PA spec amendment / BB cross-check

**Spec amendment: NO at current sample.** Spec §1.2 line 44 already named the 15-25% conservative range. Spec §11.7 AC-19 already sets 30% target with 「< 30% → Phase 2b BLOCKED + spec 修訂或 reject」 — i.e. the spec itself prepared for this case as a 14d gate, not a deploy-blocker.

**BB cross-check: OPTIONAL but recommended.** If T+72h still 0% or near-0% maker fill, dispatch BB (Bybit Exchange Spec) to:

1. Confirm whether `bid - 1 tick` PostOnly behaviors on Bybit demo are systematically lower fill rate than mainnet (demo book depth thinner, organic taker flow lower).
2. Check Bybit V5 demo endpoint quirk re: PostOnly fills in low-volume hours UTC 05:00-06:30 (3 of 4 fallback rows in this 1.5h window — possible Bybit demo asia-pre-open thin liquidity coincidence).
3. Verify whether `reduceOnly=true` (assumed used in close path) interacts with PostOnly fill priority on demo.

**PA ticket: NEEDED for spec wording update** at next monthly amendment cycle (NOT blocking):

- Spec §10.1 Phase 2a should explicitly note that AC-19 30% target is a **14d cumulative** floor, not 24h/7d primary gate.
- Spec §11 AC-A primary SQL scope should narrow to `engine_mode = 'demo'` only until LiveDemo Phase 2b ticket lights up (per QA §6.3 — `engine_mode IN ('demo','live_demo')` currently dilutes signal because live_demo TOML 仍 disabled).

---

## §7 5/5 Multi-session race check

- ✅ fetch ahead — origin/main 已同步
- ✅ no foreign WIP touched — 6 個 memory.md uncommitted edits 全部保留原狀
- ✅ no sibling push collision — read-only RCA
- ✅ read-only — 0 file write to rust/openclaw_engine/src/ or TOML or migrations
- ✅ no review-window drift — 24h fix-plan v1.x 對齊

---

## §8 Conclusion

**Root cause confidence**: HIGH that activator + state machine + fallback functioning per spec §5.2/§5.5; MEDIUM-HIGH that 0/4 fill rate is small-n statistical noise within spec §1.2 predicted 15-25% close-fill range (entry-side 24h baseline 14.7% PostOnly fill = same demo low-liquidity floor).

**Fix scope = NONE at n=4**; if T+72h n≥30 still <5% fill rate, PA tuning ticket on:
- `buffer_ticks 1→0` (`maker_price.rs:90/95/100`, ~3 LOC config)
- 或 `timeout_ms 30→45` (~1 LOC)

**PA spec amendment**: not blocking; minor wording cleanup re AC-A scope (demo-only vs `IN(demo, live_demo)`) at next AMD cycle.

**BB cross-check**: optional if pattern persists past T+72h to confirm Bybit demo PostOnly behavior vs mainnet.

---

## §10 Status Update Post-Operator P0 Override (added by main session 2026-05-18 ~11:00 UTC)

**Multi-session race reconciliation**: while this E2 RCA was being written, 隔壁 session 已 commit `eebda658` v48 with `P0-PHASE-1B-PARAM-CALIBRATION-1` row (added §10 P0 True-Live Blockers) per **operator instruction「12H 後做 calibration，然後三端同步」**。Memory `feedback_pnl_priority_over_governance.md` 也同期 land (originSessionId `f72e23f5-4eba-4338-890a-26dfa94d90d7`)。

**Reconciliation between E2 technical verdict and operator P0 priority**:

| 視角 | Verdict | Schedule | 為何不矛盾 |
|---|---|---|---|
| E2 statistical (this report) | NO BUG / NO E1 RETURN / n=4 too small for definitive conclusion | wait T+72h n≥30 才動 | technical correctness at code level |
| Operator PnL-priority (v48 + memory) | 100% timeout fallback = $0 fee saving = does NOT move PnL | calibration ASAP post-12H window (~2026-05-18 11:54 UTC) | operator priority lens elevates parameter tuning to P0; PA spec design = "calibrate fast, don't wait for n=30" |

**Final SoT** = TODO v48 + `P0-PHASE-1B-PARAM-CALIBRATION-1` row (6-step dispatch sequence: PA spec → E1 replay → sweep → operator pilot → E4 → QA → merge+restart). Acceptance: ≥1 viable parameter cell with `maker_fill_rate ≥ 25%` AND `expected_fee_saving_bps ≥ 0.5`. Owner: PA → E1 → E2 → E4 → QA. Est: ~3-5 person-day.

**E2 technical findings preserved as input** to the calibration sweep:
- **Tune-1 buffer_ticks 1→0** 對應 v48 calibration 的 `buffer_ticks 1 → {2, 3, 4}` (note: v48 試的是 *寬* 一點而非 0，因為 0 會增 PostOnly reject volume — direction 反向但同 spec dimension)
- **Tune-2 timeout_ms 30→45** 對應 v48 `timeout {30s→60s/90s grid, 15s→45s/60s phys_lock}`
- **Tune-3 spread guard** 仍是 valid additional axis — v48 sweep 應 include
- §5 Re-verification SQL 仍可用為 calibration 後驗證 SQL

**No revert / no override of v48**. This report is preserved as the **statistical-rigor companion** to v48's PnL-priority calibration plan. Future PA spec design for the calibration sweep should cite both this report's §3 假設 verdict + v48 P0 row owner chain.

**Lesson**: operator preference per `feedback_pnl_priority_over_governance.md` = PnL improvement framing trumps "wait for statistical certainty" when the path is parameter tuning (not architectural change). Future E2 RCA on PnL-impacting issues 必含 "does this move PnL?" judgment + 不必要堅持 n≥30 阻 calibration（calibration sweep 自己會生 sample）。

---

## §9 References

- **QA report (T+10.6h)**: `srv/docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-18--phase_1b_24h_post_deploy_verification_update.md`
- **QA report (T+18min)**: `srv/docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-18--phase_1b_24h_post_deploy_verification.md`
- **Spec**: `srv/docs/execution_plan/2026-05-15--edge_p2_3_phase_1b_close_maker_first_spec.md` (v1.3+, §5 state machine + §11 acceptance)
- **AMD v0.7**: `srv/docs/governance_dev/amendments/2026-05-15--AMD-2026-05-15-02-edge-p2-3-phase-1b-close-maker-first.md`
- **PA activator design**: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-18--phase_1b_use_maker_close_runtime_activator_design.md`
- **E1 IMPL commit**: `18081551 feat(phase-1b): runtime activator IMPL`
- **Healthcheck source**: `helper_scripts/canary/healthchecks/62_close_maker_fill_rate.py` + `63_close_maker_fallback_audit.py` + `64_close_maker_rate_limit_pause_duration.py` + `65_reject_sample_healthcheck.py`
- **Note**: E2 agent inline finding 因 sub-agent context system-reminder 限制未直接寫檔，main session 落地此檔（content 等同 E2 agent inline output，零失真）
