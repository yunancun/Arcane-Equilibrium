# Sprint N+0 HIGH-5 12h Watch Sign-off Report (DRAFT)

**Date**: 2026-05-10
**Watch window**: 09:23 UTC start → 21:30 UTC sign-off (12h passive forward observation)
**Author**: PM
**Status**: DRAFT — 21:30 UTC 跑 healthcheck 填數值後 land
**Predecessor**: Sprint N+0 closure HEAD `b6ed4975`

---

## §1 Sign-off Verdict

**Status**: ⏳ PENDING / ✅ APPROVE / ❌ REJECT （21:30 UTC 後選定）

**Conditional Notes**:
- W7-3 Option B 補丁 (commit `b42731f6`) PR ready NOT DEPLOYED — 隨 sign-off + dispatch fire 同次 restart deploy
- W7-1 + W2 trait skeleton (commit `c9fb0b8f`) PR ready NOT DEPLOYED — 同上

---

## §2 HIGH-5 Watch 3 Metric 驗收

### Metric 1: chain_integrity（已提早 sign-off per MIT chain integrity replay）
- **Status**: ✅ CLOSED EARLY
- **Evidence**: MIT replay 揭露 fills.entry_context_id → decision_features.context_id chain pre+post V083 都 100%（n=331 + 10, 0 orphan）；memory v1 「0.5%→100%」是 mock baseline 誤讀，**真實全期均 100%**
- **Report**: `srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-10--chain_integrity_historical_replay.md`

### Metric 2: [40] avg_net forward trajectory ≥ 5 bps
- **Status**: ⏳ PENDING（21:30 UTC fill）
- **Baseline (Sprint N+0 closure 09:23 UTC)**: +8.75 bps（從 -17.82 翻正）
- **Current (12h post-restart)**: TBD bps（21:30 UTC 跑）
  ```sql
  PG_PASS=$(awk -F= '/^POSTGRES_PASSWORD=/{print $2}' $SECRETS/basic_system_services.env)
  PGPASSWORD=$PG_PASS psql -h 127.0.0.1 -U trading_admin -d trading_ai -c \
    "SELECT engine_mode, COUNT(*) n, ROUND(AVG(net_edge_bps proxy)::numeric,2) avg_net FROM trading.fills f JOIN trading.decision_outcomes o USING(context_id) WHERE f.ts > '2026-05-10 09:23:00 UTC' AND engine_mode IN ('demo','live_demo') GROUP BY engine_mode;"
  ```
- **Verdict**: PASS (≥ +5 bps) / WARN (+0 to +5 bps) / FAIL (< 0 bps) — TBD

### Metric 3: TONUSDT cell isolate（不擴散）
- **Status**: ⏳ PENDING（21:30 UTC fill）
- **Baseline**: TONUSDT n=10 avg=-31.23 bps（Sprint N+0 closure）
- **Current**: TBD per cohort symbol
  ```sql
  PGPASSWORD=$PG_PASS psql -h 127.0.0.1 -U trading_admin -d trading_ai -c \
    "SELECT symbol, COUNT(*) n, ROUND(AVG(net_edge_bps proxy)::numeric,2) avg_net FROM trading.fills f JOIN trading.decision_outcomes o USING(context_id) WHERE strategy_name='grid_trading' AND f.ts > '2026-05-10 09:23:00 UTC' AND engine_mode IN ('demo','live_demo') GROUP BY symbol ORDER BY 3 ASC;"
  ```
- **Verdict**: PASS (TONUSDT 仍是唯一負 cell) / WARN (1 額外 symbol 進負) / FAIL (≥2 額外 symbol 進負，擴散)

---

## §3 Sprint N+0 Final Snapshot

| 項 | 值 |
|---|---|
| Commit chain HEAD | `b6ed4975` (Sprint N+0 closure) → `bf66f1b2` (Sprint N+1 D+0 readiness) |
| V### land | V80 + V82 + V83 + V84 (4 migration sqlx success=t) |
| Engine restart | 2026-05-10 09:23 UTC |
| 22 sign-off invariant | 14 ✅ / 6 DEFER / 2 PARTIAL / 0 FAIL |
| 4-agent final review | CC A 93.3% / QC APPROVE 3 push back / MIT APPROVE FULL / BB APPROVE |
| ADR / AMD land | ADR-0022 / ARCH-04 / AMD-2026-05-09-03 / AMD-2026-05-10-03 / AMD-2026-05-10-04 |
| ML cron 5 jobs | install + status=ok 真實 fire (lightgbm via venv + optuna install) |
| Critical realities | 5 textbook 策略結構性 alpha-deficient 維持; P0-EDGE-1 pending Phase B/C/D + A 群 |

---

## §4 Sprint N+1 D+0 Pre-dispatch Readiness（已 land HEAD `bf66f1b2`）

**25 項提前準備全完成**：詳 memory `project_2026_05_10_sprint_n1_d0_readiness.md`

**Code change PR ready (NOT DEPLOYED)**：
- W7-3 Option B (`b42731f6`)
- W7-1 + W2 trait skeleton (`c9fb0b8f`)

**Specs / RFC**：
- W2 A4-C v1.2 / W1 Phase B v1.1 / W6-1 RFC verdict draft / W6-3a-b enum / W5 三 P1

**Audits / Reviews**：
- CC A- 92.0% APPROVE-CONDITIONAL
- E3 ALL PASS (5 hard gate 全綠)
- R4 8 fix land

---

## §5 Sign-off + Dispatch Fire 流程（21:30 UTC 後）

### §5.1 IF metric 2/3 PASS：APPROVE → dispatch fire
1. **Deploy** (~5 min): `ssh trade-core "cd ~/BybitOpenClaw/srv && git pull --ff-only origin main && bash helper_scripts/restart_all.sh --rebuild --keep-auth 2>&1 | tail -30"`
2. **5 min validation**: ma_crossover INXUSDT reject < 5/min + chains_with_lease > 0 + bad_report_quality = 0 + engine_alive
3. **Dispatch fire 9 wave 並行** (per dispatch v3.7 §4 Schedule D+1):
   - W7-2 (ma_crossover entry path + bb_reversion 同 pattern, ~25 LOC)
   - W7-4 (PA + E1 5 策略 systemic audit, 1 day)
   - W7-5 (E1 on_fill + bootstrap, ~20 LOC)
   - W6 RFC verdict 三角 sign-off (PA + QC + MIT 各 1.5h verify + 1h sync)
   - W6 V086 IMPL (E1, two TEXT column + 30-90s in-migration backfill)
   - W1 IMPL Rust panel_aggregator WS-first (3 E1 sub-agent)
   - W2 IMPL v1.2 (E1 lead-lag producer + V088 + ma/grid 接 BtcAltLeadLag paper-only)
   - W4 RouterLeaseGuard Drop test (E4, ~40 LOC)
   - W5 三 P1 IMPL (W5-E1-A/B/C, ~1460 LOC, V089/V090)
4. **Memory persist**: update `project_2026_05_10_sprint_n0_closure.md` + `project_2026_05_10_sprint_n1_d0_readiness.md` + MEMORY.md

### §5.2 IF metric 2 FAIL（avg_net < 0）：CONDITIONAL APPROVE + rollback W2 trait skeleton only
- W7-3 + W7-1 仍 deploy（修 hot loop bug）
- W2 trait skeleton 不 deploy（避免 paper IMPL 在 negative edge baseline 跑誤導 evidence）
- 24h 觀察看 avg_net 是否回升 → re-evaluate

### §5.3 IF metric 2/3 FAIL severe：REJECT + 全 rollback
- `git revert b42731f6 c9fb0b8f --no-edit && git push origin main`
- ssh trade-core restart_all --rebuild --keep-auth
- N+0 closure 須 reframe + Sprint N+1 dispatch v3.7 重審

---

## §6 Risk Assessment

- ma_crossover INXUSDT hot loop 已自然 cool down (last 30min 1 reject)；W7-3 deploy 仍價值（防止 cross-strategy desync 重燃）
- 4 策略 (ma_crossover/bb_breakout/bb_reversion/funding_arb) 12h 0 fill — funding_arb dormant by design；其他 3 待 W6-7 [61] silence healthcheck land 後監測
- HIGH-5 metric 2 forward trajectory 受 ML cron 5 jobs daily fire 影響（grid 374 PASS gate, 4/5 策略 sample 不過 200 gate per MIT W6 RFC Q4）

---

## §7 PM Sign-off Statement（21:30 UTC 填）

PM 確認：
- [ ] HIGH-5 watch 3 metric 全 verify
- [ ] CC + E3 + R4 + QC + MIT + BB pre-check 全 land
- [ ] 25 項 D+0 提前準備清單全 ready
- [ ] Deploy SOP + dispatch fire SOP + rollback plan 全備齊
- [ ] Operator final approval

**Final verdict**: ⏳ PENDING

**Signed**: PM @ 2026-05-10 21:30 UTC TBD

---

**End of draft**. 21:30 UTC 跑 healthcheck → 填 §2 數值 + §1 verdict + §7 PM sign-off → land final report → trigger §5 dispatch fire 流程。
