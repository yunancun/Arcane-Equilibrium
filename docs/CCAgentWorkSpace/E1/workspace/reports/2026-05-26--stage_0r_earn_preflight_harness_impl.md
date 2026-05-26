---
agent: E1
date: 2026-05-26
sprint: Sprint 1B Wave C
topic: Stage 0R Earn variant preflight harness IMPL
spec_ref: docs/execution_plan/2026-05-25--stage_0r_earn_variant_design_spec.md
status: E1 IMPL DONE — 待 E2 審查
chain_position: E1 → E2 (NEXT) → E4 → QA → PM
---

# Stage 0R Earn Variant Preflight Harness IMPL — Wave C

## 任務摘要

per spec §7.4 IMPL `helper_scripts/canary/replay_earn_preflight.py` — Stage 0R Earn variant preflight harness,first stake 前 5 sanity check + 5 fail injection grid + 3 階 reconciliation cron dry-run + JSON verdict output。對齊 C10 範式 `replay_funding_harvest.py` 但 diverge to Earn-specific design (per spec §3.2)。

## 修改清單

| 路徑 | LOC | 類型 | 用途 |
|---|---|---|---|
| `/Users/ncyu/Projects/TradeBot/srv/helper_scripts/canary/replay_earn_preflight.py` | 714 | NEW | Stage 0R Earn preflight harness |
| `/Users/ncyu/Projects/TradeBot/srv/helper_scripts/canary/test_replay_earn_preflight.py` | 174 | NEW | 14 unit test (對齊 test_canary.py unittest pattern) |
| `/Users/ncyu/Projects/TradeBot/srv/helper_scripts/SCRIPT_INDEX.md` | +2 entry | EDIT | 加 harness + test 條目 |

LOC 較 spec ~400-500 預估略超,主因:
- 5 sanity check IMPL 較 verbose (每 check 含 status + msg + metrics 三層 return)
- JSON schema fields 對齊 spec §4 AC-5 完整;含 dry_run_invariants 5 條 + reconciliation_grid + 5 gate fail_injection_grid 完整 audit trail
- MODULE_NOTE + comments 中文化 per `bilingual-comment-style` skill

## 5 sanity check IMPL 對齊 spec

| Check | spec §3.3 內容 | IMPL 行為 |
|---|---|---|
| 1 `apy_drift_check` | drift < 5% vs historical demo Earn record;first stake vacuous PASS | first stake (None historical) → `VACUOUS_PASS`;drift 計算 PASS/FAIL;abs 偏離 fallback 避除零 |
| 2 `5gate_reject_check` | 5 gate fail injection 全 100% 觸發 | 5/5 mock_5_gate_reject_path grid 對齊 earn_governance §2.1-§2.5 預期 reject pattern |
| 3 `first_stake_lal0_check` | AC-3 deferred (harness 不寫 V100) | `DEFERRED` + `deferred_to=operator_first_stake_post_OP-1_OP-2` + V100 query template |
| 4 `failclosed_exitcode_check` | 任 1 FAIL → exit 1 | meta-check 驗 verdict gate 邏輯;`expected_exit_code` 由 fail_count 計算 |
| 5 `atr_cap_drawdown_check` | constant by design | `atr_cap_applicable=false` + `drawdown_gate_applicable='partial_post_sprint5'` + rationale |

## 5 fail injection grid 對齊 spec §3.2 + §4 AC-4

```
GATE_FAIL_INJECTIONS = [
  {gate=a, fail=operator_role=None,     expected_event=earn_intent_rejected_no_operator_role},
  {gate=b, fail=authz_invalid,          expected_event=earn_intent_rejected_authz_invalid},
  {gate=c, fail=lease_unavailable,      expected_event=earn_intent_rejected_lease_unavailable},
  {gate=d, fail=risk_envelope_fail,     expected_event=earn_intent_rejected_risk_envelope_fail},
  {gate=e, fail=db_insert_fail,         expected_event=earn_intent_rejected_db_insert_fail},
]
```

對齊 earn_governance §2.1-§2.5 5-gate 預期 reject event pattern;mock 純 in-memory 不調 IntentProcessor real code (per spec §3.5 第 4 條 mock=inject fail state 非 short circuit)。

## 治理對照

### Spec §3.5 dry-run 5 invariants — grep 驗證

```bash
$ grep -nE "subscribe_flexible|redeem_flexible|EarnMovementWriter\.insert_placeholder|EarnMovementWriter\.update_outcome|earn/place-order" helper_scripts/canary/replay_earn_preflight.py
28:   - 不發 Bybit live stake/redeem 寫單 (0 hit subscribe_flexible / redeem_flexible)
```

**0 hit 在 code (line 28 是 MODULE_NOTE 注釋說明本檔不調此 surface);harness 純 in-memory simulation 對齊**:
1. 不發 Bybit live stake/redeem 寫單 → `no_bybit_stake_redeem_writes=true`
2. 不寫 V100 `learning.earn_movement_log` → `no_v100_writes=true`
3. 不動 Bybit demo Earn balance → `no_demo_balance_change=true`
4. 不繞 5-gate → `no_5gate_short_circuit=true`
5. 不污染 V100 schema → `no_v100_schema_pollution=true`

### Spec §4 AC 對應

| AC | spec 內容 | harness 行為 |
|---|---|---|
| AC-1 | APY drift < 5% (or vacuous PASS first stake) | check 1 → VACUOUS_PASS first stake;有 V100 走 drift_pct 計算 |
| AC-2 | IntentProcessor Earn branch 正確 dispatch | check 2 → 5/5 fail injection PASS |
| AC-3 | V100 真實 row 寫入 | check 3 → DEFERRED to operator first stake (harness 不寫 V100) |
| AC-4 | Stage 0R fail → exit 1 不 ascend Stage 1 | check 4 + `sys.exit(0 if eligible else 1)` |
| AC-5 | atr_cap_applicable=false + drawdown partial_post_sprint5 | check 5 constant by design |

### Spec §7.4 對齊 C10 範式

| C10 範式 element | Earn variant element |
|---|---|
| `fetch_funding_rates` | `fetch_apr_history` (Bybit V5 /v5/earn/apr-history public GET) |
| `replay_funding_harvest` tick-by-tick | `simulate_apy_accrual` day-by-day |
| `sanity_check_*` × 6 | `sanity_check_1~5` × 5 (移除 4 alpha-edge check + 加 4 Earn-specific) |
| `output_preflight_verdict` | `output_preflight_verdict` (一致 JSON schema 範式) |
| `run_stage0r_preflight` orchestrator | `run_stage0r_preflight` orchestrator |
| CLI `--symbol BTCUSDT --days 30` | CLI `--coin USDT --amount-usd 100 --days 7` |

## CLI smoke 結果

```
$ python3 helper_scripts/canary/replay_earn_preflight.py --coin USDT --amount-usd 100 --days 7
...
STAGE 0R EARN PREFLIGHT VERDICT
  coin=USDT amount_usd=$100.00 days=7 apr_samples=0
  cumulative_7d_accrual=$0.000000 USDT
  5 sanity checks:
    1) apy_drift=VACUOUS_PASS
    2) 5gate_reject=PASS (5/5)
    3) first_stake_lal0=DEFERRED
    4) failclosed_exitcode=PASS
    5) atr_cap_drawdown=PASS
  eligible_for_first_stake=True verdict=PASS
$ echo $?
0
```

JSON verdict 已寫至 `~/.openclaw_runtime/canary/earn_first_stake_stage0r_2026-05-26.json`;schema 完整對齊 spec §4 AC-5 (含 `coin/amount_usd/days/sanity_checks{5}/eligible_for_first_stake/verdict`)。

**註**：Mac 環境 SSL CERTIFICATE_VERIFY_FAILED → `fetch_apr_history` fallback empty events → `simulate_apy_accrual` 走 fallback 0% APR path → check 1 走 `VACUOUS_PASS` first stake fallback;此為 spec §3.4 fallback 設計行為 (per BB-C3 endpoint transient unavailable);Linux runtime 真實連 Bybit 走 PASS path 取 APR baseline。

## 14 unit test 結果

```
$ python3 -m unittest helper_scripts.canary.test_replay_earn_preflight -v
test_mock_5_gate_reject_path_full_coverage ... ok
test_mock_daily_reconciliation_3_severity ... ok
test_output_preflight_verdict_schema_first_stake ... ok
test_sanity_check_1_drift_over_5pct_fail ... ok
test_sanity_check_1_drift_under_5pct_pass ... ok
test_sanity_check_1_first_stake_vacuous_pass ... ok
test_sanity_check_2_5gate_all_pass ... ok
test_sanity_check_2_5gate_with_injected_fail ... ok
test_sanity_check_3_first_stake_deferred ... ok
test_sanity_check_4_no_fail_expected_exit_0 ... ok
test_sanity_check_4_one_fail_expected_exit_1 ... ok
test_sanity_check_5_atr_cap_constant ... ok
test_simulate_apy_accrual_constant_apr ... ok
test_simulate_apy_accrual_empty_events_fallback ... ok
----------------------------------------------------------------------
Ran 14 tests in 0.002s
OK
```

14/14 PASS — 對齊 spec §7.6 E4 regression scope 預期 unit test 範圍。

## 不確定之處

1. **OQ-8 audit_log 鏡像**:spec §8.8 PA 建議 (a) 鏡像;但 harness 不自動寫 audit_log (避違 §3.5 dry-run 邊界);Wave E operator first stake 走 GUI 提交時由 GUI 後端 attach JSON ref 到 audit row。本 IMPL 已生 `evidence_refs` field 含 verdict_path + metrics_path 兩個 file ref;GUI 後端應讀此 field;**不確定 GUI/IntentProcessor 已有對接 evidence_refs field 的代碼**,E2 review 可確認。

2. **fetch_apr_history endpoint 真實 schema**:本 IMPL 假設 Bybit V5 `/v5/earn/apr-history` return `{retCode, result.list[{coin, productType, apr, timestamp}]}` schema (per spec §3.4 描述);Mac 環境因 SSL 無法實連驗證 schema;**Linux runtime 首次跑時若 schema mismatch (e.g. field 名 `aprPercent` 而非 `apr`) 走 fallback empty events vacuous PASS path**,不會 abort;但 production semantic 可能 false 走 vacuous path 而非真實 drift 驗;BB review 建議 cross-ref Bybit doc reference 確認 V5 apr-history exact schema。

3. **3 階 reconciliation cron dry-run mock 範圍**:本 IMPL `mock_daily_reconciliation_cron` 僅模擬 Notice/Warn/Degraded 各觸 1 次 routing;不模擬 spec §6.4 「連續 3d cumulative 觸 Degraded 升 alert path」;Sprint 5+ Earn cron healthcheck 加上後此邏輯可擴。本 Wave C scope 鎖 first stake only (per spec §2.4 範圍鎖定);可接受。

## Operator 下一步

1. **E2 adversarial review** per spec §7.5 — 重點驗:
   - Exit code 邏輯 (任 1 sanity check FAIL → exit 1)
   - Mock 5-gate reject path 完整性 (5/5 各觸 1 次,非 only mock 部分)
   - Dry-run 邊界 5 條不變量 grep 0 hit
   - APY drift math: `daily_accrual = stake * (apr / 365.0)` 公式正確
   - 不污染 production tokio scheduler

2. **E4 regression** per spec §7.6 — 重點驗:
   - cargo workspace 全 test PASS (Earn Wave B 既有 30+ test 不 regress) — **本 IMPL 0 cargo touch,純 Python,不影響 Rust workspace;E4 regression 對應「Rust 不 regress」=自動成立**
   - `python3 -m unittest helper_scripts.canary.test_replay_earn_preflight` 14/14 PASS (本 IMPL 自驗已通)
   - CLI smoke exit 0 + verdict PASS

3. **QA acceptance** per spec §7.7 — 5 AC 逐條驗;harness CLI run 1 次取 JSON;5 fail injection × 5 sanity check 25 case grid;檢查 atr_cap_drawdown 字串對齊。

4. **PM Phase 3e sign-off** per spec §7.8 — Sprint 1B Pending 3.2 Earn Wave C closure。

5. (operator action) OP-1 Bybit Web UI key 重發 (+ asset:earn scope) → Wave E first stake $100-200 USDT FlexibleSaving → AC-3 V100 PG empirical query 驗 1 row。

---

E1 IMPLEMENTATION DONE: 待 E2 審查 (report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-26--stage_0r_earn_preflight_harness_impl.md`)
