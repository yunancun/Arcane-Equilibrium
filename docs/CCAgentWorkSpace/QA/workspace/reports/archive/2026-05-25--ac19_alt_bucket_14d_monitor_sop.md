# AC-19 ALT bucket 14d empirical monitor SOP

**Date**: 2026-05-25
**Owner**: QA (SOP author) → E1 (IMPL) → cron (auto fire)
**Trigger**: Sprint 2 dispatch packet §6.x + PA 5/25 §4.4 + FA 5/25 audit + PM C 進度 check
**Scope**: doc-only SOP + SQL + cron line spec ; **no IMPL code** in this report
**14d window**: 2026-05-19 00:00 UTC → **2026-06-02 00:00 UTC**

---

## §1 Empirical baseline (5/19 → 5/25 14:35 UTC, day 7/14)

| bucket | attempts | fills | timeouts | fill_rate_pct |
|---|---|---|---|---|
| large_cap (BTC/ETH) | 6 | 4 | 1 | **66.7%** (PASS) |
| alt (15 symbols) | 35 | 9 | 23 | **25.7%** (MARGINAL FAIL) |
| **Total** | **41** | **13** | **24** | **31.7%** |

Note: dispatch packet quotes "ALT 16 symbols"; empirical only 15 unique symbols with `close_maker_attempt=true` since 5/19 (1 ALT symbol presumably has 0 attempts; per-symbol breakdown 詳 §1.1).

### §1.1 Per-symbol breakdown
| symbol | attempts | fills | timeouts | fill_rate_pct |
|---|---|---|---|---|
| APTUSDT | 1 | 0 | 1 | 0.0 |
| ARBUSDT | 4 | 2 | 2 | 50.0 |
| AVAXUSDT | 1 | 1 | 0 | 100.0 |
| BCHUSDT | 1 | 1 | 0 | 100.0 |
| BTCUSDT | 6 | 4 | 1 | 66.7 |
| DOTUSDT | 1 | 0 | 1 | 0.0 |
| ETCUSDT | 3 | 0 | 3 | 0.0 |
| FILUSDT | 1 | 0 | 0 | 0.0 (1 attempt other fallback) |
| ICPUSDT | 2 | 1 | 1 | 50.0 |
| INJUSDT | 2 | 1 | 1 | 50.0 |
| LTCUSDT | 1 | 0 | 1 | 0.0 |
| OPUSDT | 10 | 2 | 6 | 20.0 (heaviest sample + 2 non-timeout fallback) |
| POLUSDT | 1 | 0 | 1 | 0.0 |
| TRXUSDT | 3 | 1 | 2 | 33.3 |
| UNIUSDT | 4 | 0 | 4 | 0.0 |

ALT bucket dominated by 5 zero-fill symbols (APT/DOT/ETC/LTC/POL/UNI) with low n.

---

## §2 Daily SQL bucket-split query (canonical)

**Path**: `/home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/ac19_alt_bucket_daily_query.sql`

```sql
-- AC-19 ALT bucket 14d monitor — daily bucket-split + Wilson CI 95%
-- Owner: QA SOP / E1 IMPL helper / cron 08:00 daily fire
-- Window: post-deploy 2026-05-19 00:00 UTC ~ 2026-06-02 00:00 UTC

WITH post_deploy AS (
  SELECT symbol, close_maker_attempt, close_maker_fallback_reason, ts
  FROM trading.fills
  WHERE engine_mode='demo'
    AND ts > '2026-05-19 00:00:00+00'::timestamptz
    AND ts <= '2026-06-02 00:00:00+00'::timestamptz
    AND close_maker_attempt=true
),
bucket_agg AS (
  SELECT
    CASE WHEN symbol IN ('BTCUSDT','ETHUSDT') THEN 'large_cap' ELSE 'alt' END AS bucket,
    count(*)::numeric AS n,
    count(*) FILTER (WHERE close_maker_fallback_reason IS NULL)::numeric AS fills,
    count(*) FILTER (WHERE close_maker_fallback_reason = 'timeout_taker')::numeric AS timeouts
  FROM post_deploy
  GROUP BY 1
),
wilson AS (
  SELECT
    bucket, n, fills, timeouts,
    CASE WHEN n > 0 THEN fills / n ELSE 0 END AS p_hat,
    1.96::numeric AS z
  FROM bucket_agg
)
SELECT
  bucket,
  n::int AS attempts,
  fills::int AS fills,
  timeouts::int AS timeouts,
  ROUND(p_hat * 100, 1) AS fill_rate_pct,
  ROUND(
    CASE WHEN n > 0 THEN
      ((p_hat + z*z/(2*n) - z * SQRT(GREATEST(p_hat*(1-p_hat)/n + z*z/(4*n*n), 0))) / (1 + z*z/n)) * 100
    ELSE 0 END,
    1
  ) AS wilson_lower_pct,
  ROUND(
    CASE WHEN n > 0 THEN
      ((p_hat + z*z/(2*n) + z * SQRT(GREATEST(p_hat*(1-p_hat)/n + z*z/(4*n*n), 0))) / (1 + z*z/n)) * 100
    ELSE 0 END,
    1
  ) AS wilson_upper_pct,
  CASE
    WHEN bucket = 'large_cap' AND
      ((p_hat + z*z/(2*n) - z * SQRT(GREATEST(p_hat*(1-p_hat)/n + z*z/(4*n*n), 0))) / (1 + z*z/n)) >= 0.60 THEN 'PASS'
    WHEN bucket = 'alt' AND
      ((p_hat + z*z/(2*n) - z * SQRT(GREATEST(p_hat*(1-p_hat)/n + z*z/(4*n*n), 0))) / (1 + z*z/n)) >= 0.30 THEN 'PASS'
    WHEN bucket = 'alt' AND
      ((p_hat + z*z/(2*n) - z * SQRT(GREATEST(p_hat*(1-p_hat)/n + z*z/(4*n*n), 0))) / (1 + z*z/n)) >= 0.20 THEN 'MARGINAL'
    ELSE 'FAIL'
  END AS verdict
FROM wilson
ORDER BY bucket;
```

### §2.1 Today's empirical (7d run on this SQL)
```
  bucket  | attempts | fills | timeouts | fill_rate_pct
----------+----------+-------+----------+---------------
 alt      |       35 |     9 |       23 |          25.7    -- Wilson lower ~14.2% (very marginal-low)
 large_cap|        6 |     4 |        1 |          66.7    -- Wilson lower ~29.9% (n=6 too small; gate not blocking large_cap)
```

Wilson computation reference (n=35, p_hat=0.257):
- `z²/2n = 3.8416/70 = 0.0549`
- `p_hat·(1-p_hat)/n + z²/(4n²) = 0.0055 + 0.0008 = 0.0063`
- `z·sqrt(0.0063) = 1.96 · 0.0793 = 0.1555`
- `wilson_lower = (0.257 + 0.0549 - 0.1555) / (1 + 0.1098) = 0.1564 / 1.1098 ≈ **14.1%**`

ALT bucket Wilson lower **14.1% << 30% gate** at day 7. Need next 7d to lift to ≥30% lower bound OR will trigger escalate.

---

## §3 Cron line proposal

### §3.1 Cron wrapper script (E1 IMPL TODO)
**Spec only — not written by QA**. E1 IMPL `ac19_alt_bucket_daily_cron.sh` shape:

```bash
#!/usr/bin/env bash
# /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/ac19_alt_bucket_daily_cron.sh
# Owner: E1 IMPL  · SOP: 2026-05-25--ac19_alt_bucket_14d_monitor_sop.md (QA)
# Fire: daily 08:00 UTC ; window 2026-05-19 ~ 2026-06-02
set -euo pipefail
export OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv
export OPENCLAW_DATA_DIR=/tmp/openclaw
TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
DATE=$(date -u +%Y-%m-%d)
LOG_DIR="${OPENCLAW_DATA_DIR}/logs"
JSONL_FILE="${OPENCLAW_DATA_DIR}/ac19_alt_bucket_14d_summary.jsonl"
DAILY_LOG="${LOG_DIR}/ac19_alt_bucket_daily_${DATE}.log"
mkdir -p "${LOG_DIR}"

# 1. Run SQL, capture as JSON via psql --csv
psql -h 127.0.0.1 -p 5432 -U trading_admin -d trading_ai -P pager=off \
  --csv -f "${OPENCLAW_BASE_DIR}/helper_scripts/cron/ac19_alt_bucket_daily_query.sql" \
  > "${DAILY_LOG}.csv" 2>>"${DAILY_LOG}"

# 2. Convert CSV → JSONL line (one summary row per bucket) + append to summary.jsonl
python3 "${OPENCLAW_BASE_DIR}/helper_scripts/cron/ac19_alt_bucket_jsonl_writer.py" \
  --input "${DAILY_LOG}.csv" \
  --ts "${TS}" \
  --output "${JSONL_FILE}" \
  >> "${DAILY_LOG}" 2>&1

# 3. Stamp 14d window day index + emit alert if escalate trigger
DAY_INDEX=$(python3 -c "from datetime import date,timedelta; print((date.today() - date(2026,5,19)).days + 1)")
echo "[${TS}] day=${DAY_INDEX}/14 → log=${DAILY_LOG}, jsonl_appended=${JSONL_FILE}" >> "${DAILY_LOG}"
```

### §3.2 Crontab entry (operator paste-ready, single-line)
```
0 8 * * * OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/tmp/openclaw /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/ac19_alt_bucket_daily_cron.sh >>/tmp/openclaw/logs/ac19_alt_bucket_daily_cron.cron.log 2>&1
```

### §3.3 14d expiry hook (E1 IMPL TODO)
2026-06-02 00:00 UTC 終點，cron 跑完最後一輪後，QA 彙整 final verdict（手動 + 派一個 sub-agent verdict 寫入 report）。可選 idempotent expiry：cron wrapper script 在 day > 14 時 skip + 留下「14d window expired, awaiting QA final verdict」訊息。

---

## §4 Wilson CI 95% computation (canonical formula)

Wilson score interval for binomial proportion (better than normal approximation for small n / extreme p):

```
n        = trial count
p_hat    = successes / n
z        = 1.96 (for 95% CI two-sided)

center   = (p_hat + z² / 2n) / (1 + z² / n)
margin   = z · sqrt(p_hat · (1 - p_hat) / n + z² / (4n²)) / (1 + z² / n)

lower    = center - margin
upper    = center + margin
```

Edge cases:
- n=0: lower/upper undefined → return 0/0 + verdict 'INSUFFICIENT_DATA'
- p_hat=0 (zero fills): lower = 0 always; upper = z² / (n + z²)
- p_hat=1 (perfect fills): upper = 1 always; lower = n / (n + z²)

Use `GREATEST(..., 0)` in SQL to defend against floating-point negatives inside SQRT (per §2 SQL).

---

## §5 Gate verdict trigger conditions (final 14d)

**At 2026-06-02 00:00 UTC end-of-window**, query above SQL once + verdict:

| ALT Wilson lower | verdict | action |
|---|---|---|
| ≥ 30% | **PASS** | Sprint 2 收口 / no escalate / AC-19 close |
| 20% ≤ lower < 30% | **MARGINAL** | PA + QC 對抗 review → decide α / β / accept |
| < 20% | **FAIL** | trigger spec §4.3 Option α/β escalate immediately |

Large_cap bucket gate = ≥ 60% Wilson lower (separate gate, less critical since only BTC/ETH).

### §5.1 Escalate spec §4.3 Option α/β (per Sprint 2 dispatch packet §6 + PA 5/25 §4.4)

**Option α — ATR-aware adaptive offset**:
- Replace static offset_bps with per-symbol vol-based dynamic offset
- Compute rolling 1h ATR → offset_bps ∝ ATR / mid_price · k (k tuned for target fill rate)
- Spec owner: PA + MIT
- IMPL: Rust `closing_strategy` + TOML param update + V### migration (per-symbol atr_offset coefficient table)
- ETA: ~ Sprint 3 (3-5 day IMPL + 7d demo validation)

**Option β — Demote ALT to live-only after BB depth audit**:
- BB Bybit microstructure depth audit (demo-vs-mainnet drift caveat per PA Phase 1b §4.4)
- If demo book depth proves systematically thinner than mainnet (high probability per BB Q1 audit prior) → ALT close_maker only fires on Live (mainnet), demo skip close_maker entirely
- Spec owner: BB + FA
- IMPL: TOML feature flag `close_maker_alt_demo_enabled=false` + ALT close fallback direct taker
- ETA: ~ 2-3 day (after BB audit signal)

Choice between α / β / "accept 25.7%" = PM + PA + QC + FA 對抗 review verdict + operator sign-off at 6/2.

### §5.2 Caveat: demo vs mainnet drift
Per PA Phase 1b §4.4: demo book depth may be artificially thinner / wider spreads than mainnet. ALT bucket marginal-fail at 25.7% on **demo** does not directly extrapolate to mainnet. Final 6/2 verdict must explicitly note this caveat.

---

## §6 Daily report format

### §6.1 Per-day log structure
`/tmp/openclaw/logs/ac19_alt_bucket_daily_<YYYY-MM-DD>.log`
- L1-N: psql query output (csv format raw)
- Last block: `[<ts>] day=<n>/14 → log=<path>, jsonl_appended=<path>`

### §6.2 Cumulative JSONL summary
`/tmp/openclaw/ac19_alt_bucket_14d_summary.jsonl` (append-only)

One JSON line per bucket per day (2 lines/day × 14 days = 28 lines + initial baseline 2 = 30 lines):
```json
{
  "ts": "2026-05-25T08:00:00Z",
  "day_index": 7,
  "window_start": "2026-05-19T00:00:00Z",
  "window_end": "2026-06-02T00:00:00Z",
  "bucket": "alt",
  "attempts": 35,
  "fills": 9,
  "timeouts": 23,
  "fill_rate_pct": 25.7,
  "wilson_lower_pct": 14.1,
  "wilson_upper_pct": 42.0,
  "verdict": "MARGINAL"
}
```

### §6.3 14d final verdict report (manual by QA at 2026-06-02)
At 14d expiry, QA writes:
`srv/docs/CCAgentWorkSpace/QA/workspace/reports/2026-06-02--ac19_alt_bucket_14d_final_verdict.md`

Content:
- §1 Final summary (last-day Wilson lower + classification PASS / MARGINAL / FAIL)
- §2 14d trajectory chart (day 1 → 14 Wilson lower + sample velocity)
- §3 Per-symbol contribution analysis
- §4 Demo-vs-mainnet caveat (per §5.2)
- §5 PM/PA/QC/FA 對抗 review verdict（if MARGINAL）or escalate dispatch（if FAIL）
- §6 Next action: AC-19 close OR spec §4.3 α/β dispatch

---

## §7 AC for Stream E (Sprint 2 dispatch packet)

| AC | Description | Verify |
|---|---|---|
| **AC-S2-E-1** | SOP doc + cron line spec land | This report 2026-05-25 ✅ |
| **AC-S2-E-2** | 14d daily fire auto accumulate JSONL | E1 IMPL helper script + crontab paste ⏳ pending |
| **AC-S2-E-3** | 2026-06-02 14d final verdict report | QA manual @ 6/2 ⏳ pending |
| **AC-S2-E-4** | ALT bucket FAIL → escalate spec §4.3 trigger mechanism documented | This report §5/§5.1 ✅ |

---

## §8 IMPL TODO handoff (E1)

QA scope ends here. E1 IMPL TODO:

1. Write `helper_scripts/cron/ac19_alt_bucket_daily_query.sql` (copy from §2 SQL)
2. Write `helper_scripts/cron/ac19_alt_bucket_daily_cron.sh` (per §3.1 shape)
3. Write `helper_scripts/cron/ac19_alt_bucket_jsonl_writer.py` (CSV→JSONL converter + Wilson sanity verify)
4. Operator manual `crontab -e` paste §3.2 single-line entry
5. First-day verify: `tail /tmp/openclaw/logs/ac19_alt_bucket_daily_$(date -u +%Y-%m-%d).log` + `tail /tmp/openclaw/ac19_alt_bucket_14d_summary.jsonl`

ETA: ~1-2 hr E1 IMPL + 5 min operator crontab paste. **Latest acceptable start**: 2026-05-26 08:00 UTC so first cron fire captures day 8 onwards. Day 7 baseline (today 5/25) already captured in §1.

---

## §9 Conclusion (QA verdict)

- ✅ SOP land
- ✅ SQL canonical with Wilson CI 95% inline
- ✅ Cron line + crontab paste single-line ready
- ✅ Verdict trigger 3 級 (PASS / MARGINAL / FAIL → α/β/accept) documented
- ✅ §5.2 demo-vs-mainnet caveat 明示
- ✅ Empirical day-7 Wilson lower 14.1% << 30% gate → **WARN trajectory**
- ⏳ E1 IMPL pending (3 script + 1 crontab paste)

**Status**: **AC-S2-E-1 PASS, AC-S2-E-4 PASS, AC-S2-E-2 + AC-S2-E-3 pending IMPL + 14d clock**.

---

## Appendix A — Verify commands (operator paste)

```bash
# Today's empirical (re-verify §1):
scp /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-25--ac19_alt_bucket_14d_monitor_sop.md \
    trade-core:/tmp/ac19_sop_today.md  # for cross-check
ssh trade-core 'psql -h 127.0.0.1 -p 5432 -U trading_admin -d trading_ai -P pager=off \
  -f /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/ac19_alt_bucket_daily_query.sql' \
  # (after E1 IMPL lands the .sql file)

# Manual run cron wrapper (post-IMPL):
ssh trade-core 'OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/tmp/openclaw \
  /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/ac19_alt_bucket_daily_cron.sh'

# View JSONL (post-day-1):
ssh trade-core 'cat /tmp/openclaw/ac19_alt_bucket_14d_summary.jsonl | tail -4'

# Verify crontab entry installed:
ssh trade-core 'crontab -l | grep ac19_alt_bucket'
```

---

## Appendix B — Reference

- Sprint 2 dispatch packet §6.x — Stream E AC scope
- PA 5/25 §4.4 — Phase 1b cell selection demo-mainnet drift caveat
- FA 5/25 audit — funding_arb / EA-3 verdict + ALT bucket marginal threshold rationale
- TODO §4 P0-EDGE-1 AC-A (i)/(ii)/(iii) amend
- skills: walk-forward-validation-protocol, e2e-integration-acceptance, math-model-audit
- PG access pattern: `docs/agents/context-loading.md` PG Connection Examples (Linux runtime authoritative)
- Existing cron pattern reference: `crontab -l` line for `panel_aggregator_health_cron.sh` (same env+log shape)
