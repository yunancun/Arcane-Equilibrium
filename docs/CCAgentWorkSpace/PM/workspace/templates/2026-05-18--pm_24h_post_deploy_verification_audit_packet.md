# PM 24h Post-Deploy Verification Audit Packet

**Date**: 2026-05-{{DAY}}（dispatch 時間）
**Trigger**: 24h after Phase 1b RUNTIME ACTIVATOR fix deploy + restart
**Scope**: 全鏈 post-deploy verification — Phase 1b runtime / W-AUDIT-8c liquidation revival / W-AUDIT-8b panel / 3-Gate / fix plan v1.x update
**Author**: Main session PM + Conductor
**Status**: TEMPLATE — pending operator dispatch authorization

> **Fill-in markers**: `{{...}}` 在 dispatch 前必填或留 placeholder by agent。

---

## §1 Dispatch Conditions

**Prerequisites all met before dispatch**:
- [ ] Phase 1b RUNTIME ACTIVATOR feature branch (`feature/phase-1b-runtime-activator`) E2 review APPROVED + E4 regression PASS + QA deploy readiness GREEN
- [ ] Operator authorized `restart_all.sh --rebuild` on Linux
- [ ] Engine pid changes confirmed (post-restart timestamp `{{RESTART_TS}}`)
- [ ] 24h elapsed since restart
- [ ] AMD v0.5 land (`23e6b6b2`)

---

## §2 Agent Owner

**Recommended**: **QA** agent (full-system end-to-end integration acceptance role per CLAUDE.md §八)

**Alternative**: PM main session does it directly (no sub-agent dispatch) if QA agent unavailable.

---

## §3 Audit Scope — 8 sections

### §3.1 Phase 1b Runtime Activator Verification

Verify `use_maker_close` is actually ON in Demo runtime post-deploy.

```sql
-- AC-1: maker_attempt rate ≥25% on demo whitelist closes (per spec §4.3 conservative)
SELECT engine_mode, fill_role,
       COUNT(*) FILTER (WHERE close_maker_attempt=TRUE) AS attempts,
       COUNT(*) FILTER (WHERE liquidity_role IN ('maker','taker')) AS close_total,
       ROUND(100.0 * COUNT(*) FILTER (WHERE close_maker_attempt=TRUE)
             / NULLIF(COUNT(*) FILTER (WHERE exit_reason IS NOT NULL), 0), 2) AS attempt_pct
  FROM trading.fills
 WHERE ts > NOW() - INTERVAL '24 hours'
   AND engine_mode IN ('demo','live_demo')
   AND exit_reason IN ('grid_close_short','grid_close_long','bb_mean_revert',
                       'ma_reverse_cross','bw_squeeze','pctb_revert')
 GROUP BY engine_mode, fill_role;

-- AC-2: fallback_reason distribution non-NULL on attempt=TRUE
SELECT close_maker_fallback_reason, COUNT(*)
  FROM trading.fills
 WHERE ts > NOW() - INTERVAL '24 hours'
   AND close_maker_attempt = TRUE
 GROUP BY 1 ORDER BY 2 DESC;

-- AC-3: 0% maker_attempt on negative whitelist (risk_close:halt_session)
SELECT engine_mode, exit_reason, close_maker_attempt, COUNT(*)
  FROM trading.fills
 WHERE ts > NOW() - INTERVAL '24 hours'
   AND exit_reason LIKE 'risk_close:%' OR exit_reason = 'halt_session'
 GROUP BY 1,2,3 ORDER BY 4 DESC;
```

**Acceptance**:
- AC-1 attempt_pct ≥25% on demo+live_demo whitelist closes
- AC-2 fallback_reason non-NULL ≥90% on attempt=TRUE rows
- AC-3 negative whitelist 0% attempt rate

### §3.2 Healthcheck [62][63][64][65] Pass

Run per Phase 1b spec §11 + AMD v0.5 §3 Rollout Posture:

```bash
ssh trade-core "python3 helper_scripts/canary/healthchecks/{62,63,64,65}.py --report"
```

**Acceptance**: all 4 healthchecks PASS with Wilson 95% CI lower bound ≥ threshold

### §3.3 W-AUDIT-8c Liquidation Revival 24h Health

```sql
-- 24h liquidation rows growth + WS uptime + side mapping
SELECT COUNT(*) AS rows_24h, MAX(ts) AS latest_ts, NOW() - MAX(ts) AS latest_age,
       COUNT(*) FILTER (WHERE side = 'Buy') AS buy_long_liquidation,
       COUNT(*) FILTER (WHERE side = 'Sell') AS sell_short_liquidation
  FROM market.liquidations
 WHERE ts > NOW() - INTERVAL '24 hours';

-- C1 v2 probe artifact freshness
ls -la /tmp/openclaw/audit/liquidation_topic_probe/liquidation_topic_probe_v2_latest.{md,json}
```

**Acceptance**:
- rows_24h ≥ 100 (per BB rate expectation)
- latest_age < 30min (WS stable)
- side mapping: Buy=long liquidation / Sell=short liquidation correct (per BB approved 2026-05-17)
- C1 probe artifact within last 24h freshness

### §3.4 W-AUDIT-8b Panel Days + Round 2 Status

```sql
SELECT EXTRACT(EPOCH FROM (to_timestamp(MAX(snapshot_ts_ms)/1000.0)
                          -to_timestamp(MIN(snapshot_ts_ms)/1000.0)))/86400 AS days
  FROM panel.funding_rates_panel;
```

**Acceptance**:
- panel ≥7.0d ✅
- Round 2 4-agent review verdict consensus available (`{{4AGENT_VERDICT_PATH}}`)

### §3.5 Engine Watchdog + IPC Liveness

```bash
ssh trade-core "python3 helper_scripts/canary/engine_watchdog.py --data-dir /tmp/openclaw --stale-threshold 45 --status"
```

**Acceptance**:
- demo + live engine alive
- snapshot age < 45s
- paper engine = expected dead (per `project_paper_pipeline_disabled_by_default`)

### §3.6 3-Gate Status Update

| Gate | Pre-fix | Post-fix Expected | Verified? |
|---|---|---|---|
| P0-EDGE-1 [40] negative edge | ❌ ACTIVE | Still ACTIVE (alpha 結構性) | {{P0_EDGE_1_STATUS}} |
| W-AUDIT-8b Stage 0R | 🟡 Round 2 preliminary RED | RED_FINAL post-4-agent review | {{W_AUDIT_8B_STATUS}} |
| W-AUDIT-8a C1 sign-off | ✅ technical PASS + revival LANDED | Stable 24h+ | {{W_AUDIT_8A_C1_STATUS}} |

### §3.7 Fix Plan v1.x Patch

Update `docs/execution_plan/2026-05-16--trading_losses_root_cause_and_fix_plan_v1.md`:
- §9.1 Phase 1b RUNTIME ACTIVATOR — mark RESOLVED + post-fix measured `attempt_pct`
- §9.2 W-AUDIT-8b Round 2 — RED_FINAL verdict + AMD §8 wording revision link
- §9.4 Tier 2 Roadmap — update Phase 2a observation reset trigger timestamp
- §8 Changelog — add v1.2 row

### §3.8 Operator Follow-up Checklist

| Action | Priority | Owner |
|---|---|---|
| Confirm Phase 2a 14d observation clock starts at `{{RESTART_TS}} + 2h verification`（不是 restart 本身）| P0 | Operator |
| Schedule Phase 2a → 2b transition (≈ 14d later) | P1 | Operator |
| Restart B-REM-1 + C1-LIQ-WRITER single-agent IMPL dispatch | P1 | PM main |
| Restart PA Phase 2c LiveDemo Counterfactual harness spec finalize | P1 | PM main |
| W-AUDIT-8a Wave 1 dispatch packet preparation | P1 | PM main |
| phys_lock Live AMD v0.2 operator self-review | P2 | Operator |

---

## §4 Output Schema

QA report written to `docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-{{DAY}}--phase_1b_24h_post_deploy_verification.md`:

1. §1 Executive Summary（1 sentence each section PASS/RETURN/RED_FLAG）
2. §2 AC-1/2/3 raw data + verdict
3. §3 Healthcheck [62][63][64][65] full output
4. §4 W-AUDIT-8c 24h growth + Side mapping verify
5. §5 W-AUDIT-8b panel days + Round 2 verdict
6. §6 Engine watchdog snapshot
7. §7 3-Gate status table
8. §8 Fix plan v1.x patch diff
9. §9 Operator follow-up checklist
10. §10 QA sign-off + recommendation: PASS to Phase 2a → 2b transition, or RETURN to fix-plan loop

---

## §5 Boundaries

- **Read-only verification + reporting** — 不動 production config / runtime
- 不 enable any new feature / strategy launch
- 不 mutate `risk_config_live.toml`
- 不 enable any paper pipeline
- 不 dispatch downstream agents (operator does)

---

## §6 Estimated Time

**Total ETA**: 1-2 hours QA execution + 30min PM consolidation = ~2-3 hours from dispatch trigger to operator-actionable verdict.

---

**Template END**. Dispatch trigger: operator authorization post-{{RESTART_TS}} + 24h.
